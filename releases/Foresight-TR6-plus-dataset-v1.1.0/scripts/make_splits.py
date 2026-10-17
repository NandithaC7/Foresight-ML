"""
make_splits.py — duplicate-aware, session-grouped 60/20/20 split for TR-6.

Reads the audit file inventory (SHA-256 per file) and produces a content-level
manifest. Original files are only read, never modified.

Rules (documented in docs/DATASET_CARD.md):
  * One row per unique image content (SHA-256). Exact byte duplicates (e.g. the
    Classified/ copy and its Normal/ copy) collapse to one sample, so duplicates
    can never land in different partitions.
  * Spoilage label = folder label under Classified/. If one content appears under
    both Spoiled and Not_spoiled it is `inherited_conflicting` and excluded from
    spoilage supervision (no arbitrary tie-break).
  * Normal/-only contents carry no spoilage label -> `unlabeled`, excluded.
  * Primary model scope is RGB (sRGB) because the deployed app receives phone
    photos; thermal IR-fusion contents are recorded but excluded from this model.
  * Group unit = inferred capture session: images of the same produce/label
    folder whose filename timestamps are <=300 s apart on the same date (each
    session is normally 17 views of one fruit). Specimen IDs are not provided
    by TR-6 and are NOT invented.
  * Sessions are shuffled with a fixed seed inside each (produce, label)
    stratum and assigned 60/20/20 by session count.

  * --group-unit day (sensitivity analysis only): all sessions of the same
    produce/label on the same calendar date form one group, so no capture day
    is shared between partitions; strata with <3 dates fall back to sessions.

Usage:
  python ml/data/make_splits.py \
      --inventory dataset-preparation/tr6-audit/output_rerun_2026-10-15/file_inventory.csv \
      --out artifacts/dataset/v1 --seed 42
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import hashlib
import json
import random
import re
from pathlib import Path

SESSION_GAP_SECONDS = 300
SPLIT_FRACTIONS = (0.6, 0.2, 0.2)
PRODUCE_CLASSES = ["Banana", "Carrot", "Guava", "Indian_Gooseberry", "Mango", "Tomato"]
SPOILAGE_CLASSES = ["Not_spoiled", "Spoiled"]
TS_RE = re.compile(r"(\d{8})_(\d{6})")


def parse_ts(path: str) -> dt.datetime | None:
    m = TS_RE.search(Path(path).name)
    if not m:
        return None
    return dt.datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")


def assign_sessions(rows: list[dict]) -> None:
    """Cluster rows (already one stratum) into sessions by timestamp gap."""
    rows.sort(key=lambda r: (r["_ts"], r["sha256"]))
    current, prev = None, None
    for r in rows:
        ts = r["_ts"]
        if prev is None or ts.date() != prev.date() or (ts - prev).total_seconds() > SESSION_GAP_SECONDS:
            current = f"{r['produce_class']}|{r['source_label']}|{r['modality']}|{ts.isoformat()}"
        r["session_id"] = current
        prev = ts


def split_sessions(session_ids: list[str], rng: random.Random) -> dict[str, str]:
    ids = sorted(session_ids)
    rng.shuffle(ids)
    n = len(ids)
    n_val = max(1, round(n * SPLIT_FRACTIONS[1]))
    n_test = max(1, round(n * SPLIT_FRACTIONS[2]))
    n_train = n - n_val - n_test
    if n_train < 1:
        raise ValueError(f"Too few sessions ({n}) for a 3-way split")
    out = {}
    for i, s in enumerate(ids):
        out[s] = "train" if i < n_train else ("val" if i < n_train + n_val else "test")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inventory", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--group-unit", choices=["session", "day"], default="session")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    inv = list(csv.DictReader(args.inventory.open()))
    images = [r for r in inv if r["modality"] in ("srgb", "thermal_ir_fusion")]
    bad = [r for r in images if r["validation_status"] != "valid"]

    by_hash: dict[str, list[dict]] = collections.defaultdict(list)
    for r in images:
        if r["validation_status"] == "valid":
            by_hash[r["sha256"]].append(r)

    samples, conflicts = [], []
    for h, occ in sorted(by_hash.items()):
        produces = {o["produce"] for o in occ}
        modalities = {o["modality"] for o in occ}
        cls_labels = {o["label"] for o in occ if o["source"] == "Classified"}
        canonical = sorted(occ, key=lambda o: (o["source"] != "Classified", o["path"]))[0]
        row = {
            "sample_id": "tr6s_" + h[:16],
            "source_relative_path": canonical["path"],
            "all_source_paths": ";".join(sorted(o["path"] for o in occ)),
            "source_dataset": "TR-6",
            "sha256": h,
            "content_group_id": "tr6c_" + h[:16],
            "duplicate_copies": len(occ),
            "produce_class": produces.pop() if len(produces) == 1 else "conflict",
            "modality": modalities.pop() if len(modalities) == 1 else "conflict",
            "width": canonical["width"],
            "height": canonical["height"],
            "capture_timestamp": "",
            "annotation_status": "pending",
            "mask_path": "",
            "bbox_path": "",
            "specimen_id": "",
            "session_id": "",
            "split": "excluded",
            "derived_from": "",
            "transformation": "none",
            "parameters": "",
            "seed": args.seed,
            "notes": "",
        }
        ts = parse_ts(canonical["path"])
        row["_ts"] = ts
        row["capture_timestamp"] = ts.isoformat() if ts else ""
        if len(cls_labels) > 1:
            row["source_label"] = "conflict"
            row["label_status"] = "inherited_conflicting"
            row["exclusion_reason"] = "conflicting_spoilage_labels"
            conflicts.append(row)
        elif len(cls_labels) == 1:
            row["source_label"] = cls_labels.pop()
            row["label_status"] = "dataset_provided_folder_label"
            row["exclusion_reason"] = ""
        else:
            row["source_label"] = ""
            row["label_status"] = "unlabeled"
            row["exclusion_reason"] = "no_spoilage_label_normal_only"
        if not row["exclusion_reason"]:
            if row["produce_class"] not in PRODUCE_CLASSES:
                row["exclusion_reason"] = "produce_label_conflict"
            elif row["modality"] != "srgb":
                row["exclusion_reason"] = "modality_out_of_scope_thermal"
            elif ts is None:
                row["exclusion_reason"] = "no_timestamp_for_grouping"
        samples.append(row)

    eligible = [s for s in samples if not s["exclusion_reason"]]
    strata: dict[tuple, list[dict]] = collections.defaultdict(list)
    for s in eligible:
        strata[(s["produce_class"], s["source_label"])].append(s)

    rng = random.Random(args.seed)
    fallback_strata: list[str] = []
    for key in sorted(strata):
        rows = strata[key]
        assign_sessions(rows)
        dates = {r["capture_timestamp"][:10] for r in rows}
        use_day = args.group_unit == "day" and len(dates) >= 3
        gkey = (lambda r: f"{key[0]}|{key[1]}|{r['capture_timestamp'][:10]}") if use_day else (lambda r: r["session_id"])
        if args.group_unit == "day" and not use_day:
            fallback_strata.append(f"{key[0]}/{key[1]}")
        assignment = split_sessions(sorted({gkey(r) for r in rows}), rng)
        for r in rows:
            r["split"] = assignment[gkey(r)]

    # Sessions for excluded thermal rows are not needed; leave blank.
    fields = [k for k in samples[0].keys() if not k.startswith("_")]
    with (args.out / "split_manifest.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for s in sorted(samples, key=lambda s: (s["split"], s["produce_class"], s["source_relative_path"])):
            w.writerow(s)
    with (args.out / "conflicting_labels.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["sample_id", "sha256", "produce_class", "modality", "all_source_paths"],
                           extrasaction="ignore")
        w.writeheader()
        for s in conflicts:
            w.writerow(s)

    # ---- summary + leakage checks ----
    counts = collections.Counter((s["split"], s["produce_class"], s["source_label"]) for s in eligible)
    sess = collections.defaultdict(set)
    for s in eligible:
        sess[s["session_id"]].add(s["split"])
    hash_split = collections.defaultdict(set)
    for s in eligible:
        hash_split[s["sha256"]].add(s["split"])
    day_split = collections.defaultdict(set)
    for s in eligible:
        day_split[(s["produce_class"], s["capture_timestamp"][:10])].add(s["split"])
    test_sessions = {s["session_id"] for s in eligible if s["split"] == "test"}
    train_days = {(s["produce_class"], s["capture_timestamp"][:10]) for s in eligible if s["split"] == "train"}
    test_sess_sharing_day = {sid for sid in test_sessions
                             if (sid.split("|")[0], sid.split("|")[3][:10]) in train_days}

    split_totals = collections.Counter(s["split"] for s in eligible)
    n_el = len(eligible)
    summary = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "inventory": str(args.inventory),
        "inventory_sha256": hashlib.sha256(args.inventory.read_bytes()).hexdigest(),
        "seed": args.seed,
        "session_gap_seconds": SESSION_GAP_SECONDS,
        "group_unit": args.group_unit,
        "day_grouping_fallback_to_session_strata": fallback_strata,
        "target_fractions": dict(zip(["train", "val", "test"], SPLIT_FRACTIONS)),
        "image_files_in_inventory": len(images),
        "invalid_image_files": len(bad),
        "unique_image_contents": len(samples),
        "exclusions": dict(collections.Counter(s["exclusion_reason"] for s in samples if s["exclusion_reason"])),
        "conflicting_contents": len(conflicts),
        "conflicting_by_produce_modality": dict(collections.Counter(
            f"{c['produce_class']}/{c['modality']}" for c in conflicts)),
        "eligible_samples": n_el,
        "split_counts": {k: split_totals[k] for k in ("train", "val", "test")},
        "split_fractions_actual": {k: round(split_totals[k] / n_el, 4) for k in ("train", "val", "test")},
        "sessions_per_split": dict(collections.Counter(
            next(iter(v)) for v in sess.values())),
        "per_stratum": {f"{p}/{l}": {sp: counts[(sp, p, l)] for sp in ("train", "val", "test")}
                        for p in PRODUCE_CLASSES for l in SPOILAGE_CLASSES},
        "leakage_checks": {
            "content_hash_in_multiple_splits": sum(1 for v in hash_split.values() if len(v) > 1),
            "session_in_multiple_splits": sum(1 for v in sess.values() if len(v) > 1),
            "produce_days_shared_across_splits": sum(1 for v in day_split.values() if len(v) > 1),
            "test_sessions_sharing_calendar_day_with_train": len(test_sess_sharing_day),
            "test_sessions_total": len(test_sessions),
        },
        "limitations": [
            "TR-6 provides no specimen IDs; each produce appears to be photographed as a small number of "
            "specimens over consecutive days, so specimen identity is shared across partitions.",
            "Session grouping keeps the 17 near-identical views of one capture together, but sessions from "
            "the same produce/day can still fall in different partitions (see leakage_checks).",
            "Spoiled/Not_spoiled are dataset folder labels that follow capture date; they were not independently verified.",
        ],
    }
    (args.out / "split_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: summary[k] for k in ("eligible_samples", "split_counts", "split_fractions_actual",
                                             "exclusions", "leakage_checks")}, indent=2))


if __name__ == "__main__":
    main()
