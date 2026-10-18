"""
analysis.py — collect every fact used by the final-review documents from saved artefacts,
compute derived statistics, draw the additional figures and export data tables.

Writes:
  releases/final_review/figures/*.png        (copied + newly drawn figures)
  releases/final_review/data/*.csv|json      (supporting data for every document)
  releases/final_review/build/facts.json     (single source for build_reports.py)
Nothing is hand-entered: every number is read from a run/eval/evidence file.
"""
from __future__ import annotations

import collections
import csv
import json
import re
import shutil
import statistics
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
A = ROOT / "artifacts"
FR = ROOT / "releases/final_review"
FIG, DATA, EVID = FR / "figures", FR / "data", FR / "evidence"
for d in (FIG, DATA, EVID):
    d.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "ml"))
from common import PRODUCE_CLASSES, SPOILAGE_CLASSES  # noqa: E402

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
plt.rcParams.update({"figure.dpi": 140, "font.size": 9, "axes.spines.top": False, "axes.spines.right": False})
C = {"noaug": "#7A8FB0", "aug": "#2F6B4F", "gan": "#C1622E", "day": "#B59A3C"}
COND_LABEL = {"noaug": "real only (no aug)", "aug": "real + conventional aug", "gan": "real + conv. aug + GAN"}


def J(p):
    p = Path(p)
    return json.loads(p.read_text()) if p.exists() else None


def rel(p):
    return str(Path(p).relative_to(ROOT))


def macro_pr(m):
    pc = m["per_class"].values()
    return float(np.mean([v["precision"] for v in pc])), float(np.mean([v["recall"] for v in pc]))


def metric_row(m):
    mp, mr = macro_pr(m)
    return {"accuracy": m["accuracy"], "macro_precision": mp, "macro_recall": mr, "macro_f1": m["macro_f1"],
            "weighted_f1": m.get("weighted_f1"), "roc_auc": m.get("roc_auc", m.get("roc_auc_ovr_macro")), "n": m["n"]}


def read_preds(p):
    return list(csv.DictReader(open(p)))


manifest = {r["sample_id"]: r for r in csv.DictReader(open(A / "dataset/v1/split_manifest.csv"))}
day_manifest = {r["sample_id"]: r for r in csv.DictReader(open(A / "dataset/v1_daygroup_sensitivity/split_manifest.csv"))}
F: dict = {}

# ------------------------------------------------------------------ dataset
audit_new = J(ROOT / "dataset-preparation/tr6-audit/output_rerun_2026-10-15/audit_summary.json")
audit_old = J(ROOT / "dataset-preparation/tr6-audit/output/audit_summary.json")
diff = [k for k in audit_new if k not in ("generated_at", "elapsed_seconds", "dataset_path", "contact_sheets") and audit_new[k] != audit_old.get(k)]
split = J(A / "dataset/v1/split_summary.json")
daysplit = J(A / "dataset/v1_daygroup_sensitivity/split_summary.json")
dist = collections.Counter()
for r in manifest.values():
    if r["split"] in ("train", "val", "test"):
        dist[(r["split"], "type", r["produce_class"])] += 1
        dist[(r["split"], "spoil", r["source_label"])] += 1
_order = {}
for t in PRODUCE_CLASSES:
    ns = [r["capture_timestamp"] for r in manifest.values() if r["split"] in ("train", "val", "test") and r["produce_class"] == t and r["source_label"] == "Not_spoiled"]
    sp = [r["capture_timestamp"] for r in manifest.values() if r["split"] in ("train", "val", "test") and r["produce_class"] == t and r["source_label"] == "Spoiled"]
    _order[t] = {"not_spoiled_first": min(ns), "not_spoiled_last": max(ns), "spoiled_first": min(sp), "spoiled_last": max(sp),
                 "all_not_spoiled_before_all_spoiled": max(ns) < min(sp)}
F["label_date_order"] = _order
F["dataset"] = {
    "audit": {k: audit_new[k] for k in ("file_count", "total_gib", "valid_images", "corrupt_or_invalid_images", "image_counts", "methane_file_count",
                                        "methane_record_count", "duplicate_groups", "duplicate_excess_copies", "cross_label_duplicate_groups",
                                        "unique_image_hashes", "classified_images_exactly_duplicated_in_normal",
                                        "normal_image_hashes_not_represented_in_classified", "verified_cross_modal_pairs")},
    "audit_rerun_fields_differing_from_prior": diff, "audit_elapsed_s": audit_new["elapsed_seconds"],
    "split": split, "daysplit": {k: daysplit[k] for k in ("split_counts", "split_fractions_actual", "leakage_checks", "day_grouping_fallback_to_session_strata")},
    "class_distribution": {sp: {"type": {c: dist[(sp, "type", c)] for c in PRODUCE_CLASSES}, "spoil": {c: dist[(sp, "spoil", c)] for c in SPOILAGE_CLASSES}}
                           for sp in ("train", "val", "test")},
}

# ------------------------------------------------------------------ primary model
P = A / "runs/vit_b16_primary"
pcfg, phist, ptest = J(P / "config.json"), J(P / "history.json"), J(P / "eval/test_clean_0_none.json")
ppred = read_preds(P / "eval/test_clean_0_none_predictions.csv")
import hashlib  # noqa: E402
F["primary"] = {
    "config": pcfg, "history": phist, "best_epoch": pcfg["best_epoch"],
    "train_minutes": round(sum(h["seconds"] for h in phist) / 60, 1),
    "test_type": metric_row(ptest["type"]), "test_spoil": metric_row(ptest["spoil"]),
    "test_spoil_per_class": ptest["spoil"]["per_class"], "test_type_per_class": ptest["type"]["per_class"],
    "cm_spoil": ptest["spoil"]["confusion_matrix"], "cm_type": ptest["type"]["confusion_matrix"],
    "batched_latency_ms": ptest["mean_batched_latency_ms_per_image"],
    "checkpoint": rel(P / "best.pt"), "deployed_checkpoint": "backend/models/foresight_vit.pt",
    "checkpoint_mb": round((P / "best.pt").stat().st_size / 1e6, 1),
    "deployed_sha256": hashlib.sha256((ROOT / "backend/models/foresight_vit.pt").read_bytes()).hexdigest(),
    "run_sha256": hashlib.sha256((P / "best.pt").read_bytes()).hexdigest(),
}
assert F["primary"]["deployed_sha256"] == F["primary"]["run_sha256"], "deployed checkpoint differs from run checkpoint"

# session-level (cluster) bootstrap of test metrics
from sklearn.metrics import accuracy_score, f1_score  # noqa: E402
sess = [manifest[p["sample_id"]]["session_id"] for p in ppred]
yt = np.array([p["true_spoil"] == "Spoiled" for p in ppred]).astype(int)
yp = np.array([p["pred_spoil"] == "Spoiled" for p in ppred]).astype(int)
by_s = collections.defaultdict(list)
for i, s in enumerate(sess):
    by_s[s].append(i)
keys = sorted(by_s)
rng = np.random.default_rng(0)
boot_f1, boot_acc, boot_rec = [], [], []
for _ in range(2000):
    idx = np.concatenate([by_s[keys[k]] for k in rng.integers(0, len(keys), len(keys))])
    boot_f1.append(f1_score(yt[idx], yp[idx], average="macro")); boot_acc.append(accuracy_score(yt[idx], yp[idx]))
    m = yt[idx] == 1
    boot_rec.append((yp[idx][m] == 1).mean() if m.any() else np.nan)
ci = lambda v: [float(np.nanpercentile(v, 2.5)), float(np.nanpercentile(v, 97.5))]  # noqa: E731
F["primary"]["bootstrap"] = {"method": "cluster bootstrap over test capture sessions (64 sessions), 2000 resamples, seed 0",
                             "spoil_macro_f1_95ci": ci(boot_f1), "spoil_accuracy_95ci": ci(boot_acc), "spoiled_recall_95ci": ci(boot_rec),
                             "n_sessions": len(keys)}
# calibration (spoilage head)
ps = np.array([float(p["p_spoiled"]) for p in ppred]); conf = np.maximum(ps, 1 - ps); corr = (yp == yt)
bins = np.linspace(0.5, 1.0, 11); ece, rel_rows = 0.0, []
for lo, hi in zip(bins[:-1], bins[1:]):
    m = (conf > lo) & (conf <= hi) if lo > 0.5 else (conf >= lo) & (conf <= hi)
    if m.any():
        ece += m.mean() * abs(corr[m].mean() - conf[m].mean())
        rel_rows.append({"bin": f"{lo:.2f}-{hi:.2f}", "n": int(m.sum()), "mean_conf": float(conf[m].mean()), "accuracy": float(corr[m].mean())})
wrong_conf = conf[~corr]
F["primary"]["calibration"] = {"ece_10bin": float(ece), "bins": rel_rows, "n": int(len(conf)),
                               "share_of_errors_with_conf_ge_0.9": float((wrong_conf >= 0.9).mean()), "n_errors": int((~corr).sum()),
                               "mean_conf_correct": float(conf[corr].mean()), "mean_conf_wrong": float(conf[~corr].mean())}
# error by stratum
err = []
for t in PRODUCE_CLASSES:
    for s in SPOILAGE_CLASSES:
        rows = [p for p in ppred if p["true_type"] == t and p["true_spoil"] == s]
        w = [p for p in rows if p["pred_spoil"] != s]
        err.append({"produce": t, "label": s, "n": len(rows), "errors": len(w), "error_rate": len(w) / len(rows) if rows else 0})
F["primary"]["errors_by_stratum"] = err
with open(DATA / "primary_errors_by_stratum.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(err[0])); w.writeheader(); w.writerows(err)
shutil.copy(P / "eval/test_clean_0_none.json", DATA / "primary_test_metrics.json")
shutil.copy(P / "eval/test_clean_0_none_predictions.csv", DATA / "primary_test_predictions.csv")
shutil.copy(P / "history.csv", DATA / "primary_training_history.csv")
shutil.copy(P / "config.json", DATA / "primary_config.json")

# ------------------------------------------------------------------ baselines
F["baselines"] = {}
for sp in ("colorhist", "vit_frozen"):
    d = J(A / f"experiments/baselines/probe_{sp}.json")
    F["baselines"][sp] = {"C_type": d["type"]["C"], "C_spoil": d["spoil"]["C"], "val_spoil_macro_f1": d["spoil"]["val_macro_f1"],
                          "test_type": metric_row(d["type"]["test"]), "test_spoil": metric_row(d["spoil"]["test"])}


# ------------------------------------------------------------------ ablations
def run_info(rd, manifest_name="v1"):
    rd = Path(rd)
    cfg, hist, te = J(rd / "config.json"), J(rd / "history.json"), J(rd / "eval/test_clean_0_none.json")
    if not (cfg and hist):
        return None
    best = max(hist, key=lambda r: r["val_composite_macro_f1"])
    out = {"run": rel(rd), "backbone": cfg["backbone"], "lr": cfg["lr"], "head_lr": cfg["head_lr"], "batch": cfg["batch_size"],
           "aug": cfg["aug"], "extra": bool(cfg.get("extra_train_csv")), "seed": cfg["seed"], "n_train": cfg["n_train"],
           "n_train_real": cfg.get("n_train_real"), "n_val": cfg["n_val"], "epochs_run": len(hist), "best_epoch": best["epoch"],
           "best_val_spoil_macro_f1": best["val_spoil_macro_f1"], "best_val_composite": best["val_composite_macro_f1"],
           "val_spoil_curve": [h["val_spoil_macro_f1"] for h in hist], "train_seconds": round(sum(h["seconds"] for h in hist), 1),
           "manifest": rel(cfg["manifest"]) if str(cfg["manifest"]).startswith(str(ROOT)) else cfg["manifest"], "complete": te is not None}
    if te:
        out.update({"test_spoil": metric_row(te["spoil"]), "test_type": metric_row(te["type"]), "cm_spoil": te["spoil"]["confusion_matrix"],
                    "latency_ms": te["mean_batched_latency_ms_per_image"]})
        pr = read_preds(rd / "eval/test_clean_0_none_predictions.csv")
        out["spoiled_recall_by_produce"] = {}
        for t in PRODUCE_CLASSES:
            m = [p for p in pr if p["true_type"] == t and p["true_spoil"] == "Spoiled"]
            out["spoiled_recall_by_produce"][t] = sum(p["pred_spoil"] == "Spoiled" for p in m) / len(m)
    return out


F["ablation_v1"] = {k: run_info(A / f"runs/{k}") for k in ("vit_s16_noaug", "vit_s16_aug", "vit_s16_aug_gan", "vit_s16_aug_daysplit")}
v2 = {}
for rd in sorted(A.glob("runs/abl2_*")):
    m = re.match(r"abl2_(noaug|aug|gan)_s(\d+)", rd.name)
    info = run_info(rd)
    if info:
        info["cond"] = m.group(1); v2[rd.name] = info
day2 = {rd.name: run_info(rd) for rd in sorted(A.glob("runs/day2_aug_s*")) if run_info(rd)}
F["ablation_v2_runs"] = v2
F["daysplit_v2_runs"] = day2


def summarize(runs):
    done = [r for r in runs if r.get("complete")]
    if not done:
        return None
    g = lambda f: [f(r) for r in done]  # noqa: E731
    ms = lambda v: {"mean": float(np.mean(v)), "std": float(np.std(v, ddof=1)) if len(v) > 1 else None, "values": v}  # noqa: E731
    return {"n_seeds": len(done), "seeds": [r["seed"] for r in done],
            "test_spoil_macro_f1": ms(g(lambda r: r["test_spoil"]["macro_f1"])), "test_spoil_accuracy": ms(g(lambda r: r["test_spoil"]["accuracy"])),
            "test_spoil_macro_precision": ms(g(lambda r: r["test_spoil"]["macro_precision"])), "test_spoil_macro_recall": ms(g(lambda r: r["test_spoil"]["macro_recall"])),
            "test_spoil_auc": ms(g(lambda r: r["test_spoil"]["roc_auc"])), "test_type_macro_f1": ms(g(lambda r: r["test_type"]["macro_f1"])),
            "best_val_spoil_macro_f1": ms(g(lambda r: r["best_val_spoil_macro_f1"])), "best_epoch": g(lambda r: r["best_epoch"]),
            "epochs_run": g(lambda r: r["epochs_run"]), "train_minutes": ms(g(lambda r: r["train_seconds"] / 60)),
            "latency_ms": ms(g(lambda r: r["latency_ms"])), "n_train": done[0]["n_train"],
            "cm_spoil_sum": np.sum([r["cm_spoil"] for r in done], axis=0).tolist(),
            "spoiled_recall_by_produce": {t: float(np.mean([r["spoiled_recall_by_produce"][t] for r in done])) for t in PRODUCE_CLASSES}}


F["ablation_v2_summary"] = {c: summarize([r for r in v2.values() if r["cond"] == c]) for c in ("noaug", "aug", "gan")}
F["daysplit_v2_summary"] = summarize(list(day2.values()))
# paired seed differences
pairs = {}
for a, b in (("aug", "noaug"), ("gan", "aug"), ("gan", "noaug")):
    d = []
    for s in (42, 43, 44):
        ra, rb = v2.get(f"abl2_{a}_s{s}"), v2.get(f"abl2_{b}_s{s}")
        if ra and rb and ra["complete"] and rb["complete"]:
            d.append(ra["test_spoil"]["macro_f1"] - rb["test_spoil"]["macro_f1"])
    pairs[f"{a}_minus_{b}"] = {"per_seed": d, "mean": float(np.mean(d)) if d else None, "min": min(d) if d else None, "max": max(d) if d else None}
dd = []
for s in (42, 43, 44):
    ra, rb = day2.get(f"day2_aug_s{s}"), v2.get(f"abl2_aug_s{s}")
    if ra and rb and ra.get("complete") and rb.get("complete"):
        dd.append(ra["test_spoil"]["macro_f1"] - rb["test_spoil"]["macro_f1"])
pairs["day_minus_session_aug"] = {"per_seed": dd, "mean": float(np.mean(dd)) if dd else None}
F["ablation_pairs"] = pairs
abl_rows = []
for k, r in list(v2.items()) + list(day2.items()) + [(k, v) for k, v in F["ablation_v1"].items() if v]:
    if r.get("complete"):
        abl_rows.append({"run": k, "cond": r.get("cond", "daysplit" if "day" in k else "v1"), "seed": r["seed"], "lr": r["lr"], "aug": r["aug"],
                         "gan_images": r["extra"], "n_train": r["n_train"], "epochs_run": r["epochs_run"], "best_epoch": r["best_epoch"],
                         "best_val_spoil_mf1": round(r["best_val_spoil_macro_f1"], 4), "test_spoil_mf1": round(r["test_spoil"]["macro_f1"], 4),
                         "test_spoil_acc": round(r["test_spoil"]["accuracy"], 4), "test_spoil_macro_P": round(r["test_spoil"]["macro_precision"], 4),
                         "test_spoil_macro_R": round(r["test_spoil"]["macro_recall"], 4), "test_spoil_auc": round(r["test_spoil"]["roc_auc"], 4),
                         "test_type_mf1": round(r["test_type"]["macro_f1"], 4), "train_min": round(r["train_seconds"] / 60, 1)})
if abl_rows:
    with open(DATA / "ablation_all_runs.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(abl_rows[0])); w.writeheader(); w.writerows(abl_rows)

# ------------------------------------------------------------------ split leakage comparison (no training)
def leakage_for(assign_file, assign_content, label):
    """assign_*: split per raw file path / per content sample_id."""
    elig = [r for r in manifest.values() if r["split"] in ("train", "val", "test")]
    out = {"split_scheme": label}
    if assign_file is not None:  # raw-file level: exact byte duplicates across splits
        files = [(p, r["sha256"]) for r in elig for p in r["all_source_paths"].split(";")]
        train_h = {h for p, h in files if assign_file[p] == "train"}
        test = [(p, h) for p, h in files if assign_file[p] == "test"]
        out["test_items"] = len(test)
        out["test_with_exact_duplicate_in_train_pct"] = 100 * sum(h in train_h for _, h in test) / len(test)
    else:
        out["test_with_exact_duplicate_in_train_pct"] = 0.0
    sp = {r["sample_id"]: assign_content[r["sample_id"]] for r in elig}
    train_sess = {r["session_id"] for r in elig if sp[r["sample_id"]] == "train"}
    train_day = {(r["produce_class"], r["capture_timestamp"][:10]) for r in elig if sp[r["sample_id"]] == "train"}
    test = [r for r in elig if sp[r["sample_id"]] == "test"]
    out["test_contents"] = len(test)
    out["test_with_same_session_in_train_pct"] = 100 * sum(r["session_id"] in train_sess for r in test) / len(test)
    out["test_with_same_produce_day_in_train_pct"] = 100 * sum((r["produce_class"], r["capture_timestamp"][:10]) in train_day for r in test) / len(test)
    return out


_rng = np.random.default_rng(42)
_elig = [r for r in manifest.values() if r["split"] in ("train", "val", "test")]
_files = sorted(p for r in _elig for p in r["all_source_paths"].split(";"))
_u = _rng.random(len(_files)); _af = {p: ("train" if u < .6 else "val" if u < .8 else "test") for p, u in zip(_files, _u)}
_first = {}
for r in _elig:  # content split induced by the raw-file split: use the Classified copy's assignment
    _first[r["sample_id"]] = _af[r["source_relative_path"]]
_u2 = _rng.random(len(_elig)); _ac = {r["sample_id"]: ("train" if u < .6 else "val" if u < .8 else "test") for r, u in zip(_elig, _u2)}
_day_assign = {}
for sid, r in day_manifest.items():
    _day_assign[sid] = r["split"]
F["split_leakage"] = [
    leakage_for(_af, _first, "random split of raw sRGB files (Classified + Normal copies), seed 42"),
    leakage_for(None, _ac, "random split of de-duplicated contents (no grouping), seed 42"),
    leakage_for(None, {r["sample_id"]: r["split"] for r in _elig}, "session-grouped split v1 (used for all main results)"),
    leakage_for(None, _day_assign, "day-grouped sensitivity split"),
]
with open(DATA / "split_leakage_comparison.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["split_scheme", "test_items", "test_contents", "test_with_exact_duplicate_in_train_pct",
                                      "test_with_same_session_in_train_pct", "test_with_same_produce_day_in_train_pct"], extrasaction="ignore")
    w.writeheader(); w.writerows(F["split_leakage"])

# ------------------------------------------------------------------ robustness, denoising
rob = []
for p in sorted((P / "eval").glob("test_*.json")):
    d = J(p)
    if d["corruption"] == "clean":
        continue
    rob.append({"corruption": d["corruption"], "level": d["level"], "denoiser": d["denoiser"].split(":")[0],
                "spoil_macro_f1": d["spoil"]["macro_f1"], "spoil_acc": d["spoil"]["accuracy"], "spoil_auc": d["spoil"]["roc_auc"],
                "type_macro_f1": d["type"]["macro_f1"], "file": rel(p)})
F["robustness"] = rob
with open(DATA / "noise_robustness.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rob[0])); w.writeheader(); w.writerows(rob)
F["dncnn_v1"] = J(A / "experiments/dncnn/dncnn_results.json")
F["dncnn_v2"] = J(A / "experiments/dncnn_v2/dncnn_results.json")
F["noise_profile"] = J(A / "experiments/noise_profile.json")

# ------------------------------------------------------------------ GAN, kmeans, xai, resources
F["gan"] = {"train": J(A / "experiments/gan/train_summary.json"), "generation": J(A / "experiments/gan/generation_summary.json"),
            "quality": J(A / "experiments/gan/quality_checks.json")}
F["gan"]["train"].pop("history", None)
F["kmeans"] = {s: J(A / f"experiments/kmeans/kmeans_{s}.json") for s in ("vit_frozen", "colorhist")}
F["xai"] = {"faithfulness": J(A / "experiments/xai/xai_summary.json"), "stability": J(A / "experiments/xai/stability.json"),
            "gallery": read_preds(A / "experiments/xai/gallery_index.csv")}
F["resources"] = J(A / "experiments/resources.json")

# ------------------------------------------------------------------ test evidence
for f in ("pytest_final.log", "e2e_smoke.log", "e2e_smoke_final.json", "latency_benchmark.json", "frontend_build.log", "ui_contract_check.json"):
    if (A / "report/evidence" / f).exists():
        shutil.copy(A / "report/evidence" / f, EVID / f)
log = (EVID / "pytest_final.log").read_text()
F["tests"] = {"pytest_summary": log.strip().splitlines()[-1].strip("= ").strip(),
              "pytest_cases": re.findall(r"^(\S+::\S+) (PASSED|FAILED|SKIPPED|ERROR)", log, re.M),
              "e2e": J(EVID / "e2e_smoke_final.json"), "latency": J(EVID / "latency_benchmark.json"), "ui_contract": J(EVID / "ui_contract_check.json"),
              "build_tail": (EVID / "frontend_build.log").read_text().strip().splitlines()[-4:]}
F["tests"]["latency"].pop("samples_ms", None) if False else None

# ------------------------------------------------------------------ TR-6+
T6 = ROOT / "Foresight-TR6-plus"
ann = collections.Counter(r.get("annotation_status", "?") for r in csv.DictReader(open(T6 / "annotations/annotation_records.csv")))
noise_man = list(csv.DictReader(open(T6 / "manifests/derived/noise_pilot_v1_manifest.csv"))) if (T6 / "manifests/derived/noise_pilot_v1_manifest.csv").exists() else []
rel_json = J(ROOT / "releases/Foresight-TR6-plus-dataset-v1.0.0.release.json")
zip_sha = hashlib.sha256((ROOT / "releases/Foresight-TR6-plus-dataset-v1.0.0.zip").read_bytes()).hexdigest()
F["tr6plus"] = {
    "build_summary": J(T6 / "reports/build_summary.json"),
    "validation_original": {k: v for k, v in J(T6 / "reports/validation_report.json").items() if k not in ("errors", "warnings")},
    "validation_rerun": J(EVID / "tr6plus_validation_rerun_2026-10-15/validation_report.json"),
    "annotation_status_counts": dict(ann),
    "calibration": J(T6 / "reports/calibration_annotation_summary.json"),
    "noise_pilot": {"summary": J(T6 / "reports/noise-pilot-v1/generation_summary.json"), "n_rows": len(noise_man),
                    "by_modality_transform": dict(collections.Counter(f"{r['apparent_modality']}/{r['transformation']}/{r['severity']}" for r in noise_man)),
                    "by_split": dict(collections.Counter(r["split"] for r in noise_man)), "ok": sum(r["processing_status"] == "ok" for r in noise_man),
                    "bytes": sum((T6 / r["derived_relative_path"]).stat().st_size for r in noise_man if (T6 / r["derived_relative_path"]).exists()),
                    "is_synthetic_all": all(r["is_synthetic"] == "true" for r in noise_man),
                    "independent_test_specimen_any": any(r["usable_as_independent_test_specimen"] == "true" for r in noise_man)},
    "release": rel_json, "zip_sha256_recomputed": zip_sha, "zip_sha256_matches": zip_sha == rel_json["zip_sha256"],
    "licence": J(ROOT / "releases/Foresight-TR6-plus-dataset-v1.0.0/reports/licence_evidence.json"),
}
v = F["tr6plus"]["validation_rerun"]
F["tr6plus"]["validation_rerun"] = {k: v[k] for k in v if k not in ("errors", "warnings")} | {"n_errors": len(v.get("errors", [])), "warnings": v.get("warnings", [])}

# ------------------------------------------------------------------ figures: copy existing
COPY = {"split_distribution.png": A / "report/figures/12_split_distribution.png", "primary_training_loss.png": A / "report/figures/01_training_loss.png",
        "primary_validation_metrics.png": A / "report/figures/02_validation_macro_f1.png", "primary_confusion_produce.png": A / "report/figures/03_confusion_produce_test.png",
        "primary_confusion_spoilage.png": A / "report/figures/04_confusion_spoilage_test.png", "primary_per_class.png": A / "report/figures/05_per_class_metrics_test.png",
        "primary_roc_spoilage.png": A / "report/figures/06_roc_spoilage_test.png", "denoising_psnr_ssim_v1.png": A / "report/figures/08_denoising_psnr_ssim.png",
        "kmeans_vit_frozen.png": A / "report/figures/10_kmeans_vit_frozen.png", "kmeans_colorhist.png": A / "report/figures/10_kmeans_colorhist.png",
        "gan_losses.png": A / "report/figures/11_gan_losses.png", "api_latency.png": A / "report/figures/13_api_latency.png",
        "gan_samples_grid.png": A / "experiments/gan/samples_grid_rows_by_condition.png", "gan_nearest_neighbour.png": A / "experiments/gan/nearest_neighbour_check.png",
        "xai_correct.png": A / "experiments/xai/rollout_correct.png", "xai_incorrect.png": A / "experiments/xai/rollout_incorrect.png",
        "xai_class_gallery.png": A / "experiments/xai/class_gallery.png", "xai_failure_cases.png": A / "experiments/xai/failure_cases.png",
        "xai_class_gallery_part1.png": A / "experiments/xai/class_gallery_part1.png", "xai_class_gallery_part2.png": A / "experiments/xai/class_gallery_part2.png",
        "xai_failure_fn.png": A / "experiments/xai/failure_cases_fn.png", "xai_failure_fp.png": A / "experiments/xai/failure_cases_fp.png",
        "noise_examples.png": A / "experiments/noise_examples.png",
        "human_vs_dataset_label.png": A / "experiments/visible_decay/human_vs_dataset_label.png",
        "shelf_life_proxy.png": A / "experiments/shelf_life_proxy/pred_vs_target.png", "unet_pilot_overlays.png": A / "experiments/unet_pilot/test_examples.png",
        "unet_auto_masks_preview.png": A / "experiments/unet_pilot/auto_masks_preview.png", "visible_decay_test_confusions.png": A / "experiments/visible_decay/test_confusions.png", "ablation_v1_bars.png": A / "report/figures/09_ablation_comparison.png"}
for k, src in COPY.items():
    shutil.copy(src, FIG / k)

# ------------------------------------------------------------------ figures: new
def save(fig, name):
    fig.tight_layout(); fig.savefig(FIG / name); plt.close(fig)


# robustness incl. dncnn2
fig, axes = plt.subplots(1, 3, figsize=(10.5, 3.3), sharey=True)
clean = ptest["spoil"]["macro_f1"]
for ax, kind in zip(axes, ("gaussian", "salt_pepper", "speckle")):
    for den, col, mk in (("none", "#C1622E", "o"), ("median", "#7A8FB0", "s"), ("dncnn", "#2F6B4F", "^"), ("dncnn2", "#B59A3C", "D")):
        pts = sorted((r["level"], r["spoil_macro_f1"]) for r in rob if r["corruption"] == kind and r["denoiser"] == den)
        if pts:
            ax.plot([0] + [p[0] for p in pts], [clean] + [p[1] for p in pts], marker=mk, c=col,
                    label={"dncnn": "DnCNN v1 (1,065 steps)", "dncnn2": "DnCNN v2 (resumed)"}.get(den, den))
    ax.set_title(kind.replace("_", " & ")); ax.set_xlabel("noise level (σ or p)")
axes[0].set_ylabel("test spoilage macro-F1"); axes[0].legend(fontsize=7, title="denoiser", title_fontsize=7)
fig.suptitle("Noise robustness of the deployed ViT-B/16 on deterministic corruptions of the test split", fontsize=9)
save(fig, "noise_robustness.png")

# calibration
cal = F["primary"]["calibration"]
fig, ax = plt.subplots(figsize=(4, 3.6))
ax.plot([0.5, 1], [0.5, 1], ":", c="grey")
ax.plot([b["mean_conf"] for b in cal["bins"]], [b["accuracy"] for b in cal["bins"]], "o-", c="#2F6B4F")
for b in cal["bins"]:
    ax.annotate(str(b["n"]), (b["mean_conf"], b["accuracy"]), fontsize=6, xytext=(3, -8), textcoords="offset points")
ax.set_xlabel("mean confidence (max softmax)"); ax.set_ylabel("observed accuracy")
ax.set_title(f"Spoilage head reliability (test), ECE = {cal['ece_10bin']:.3f}", fontsize=9)
save(fig, "primary_calibration.png")

# error by stratum
fig, ax = plt.subplots(figsize=(7.5, 3.2))
lab = [f"{e['produce'].replace('Indian_Gooseberry', 'Gooseberry')}\n{'S' if e['label'] == 'Spoiled' else 'NS'}" for e in err]
ax.bar(range(len(err)), [100 * e["error_rate"] for e in err], color=["#C1622E" if e["label"] == "Spoiled" else "#7A8FB0" for e in err])
for i, e in enumerate(err):
    ax.text(i, 100 * e["error_rate"] + 0.5, f"{e['errors']}/{e['n']}", ha="center", fontsize=6.5)
ax.set_xticks(range(len(err)), lab, fontsize=7); ax.set_ylabel("spoilage error rate (%)")
ax.set_title("Primary model test errors by produce × label (S = Spoiled, NS = Not spoiled)", fontsize=9)
save(fig, "primary_errors_by_stratum.png")

# ablation v2
S2 = F["ablation_v2_summary"]
if any(S2.values()):
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.6))
    conds = [c for c in ("noaug", "aug", "gan") if S2[c]]
    for i, c in enumerate(conds):
        vals = S2[c]["test_spoil_macro_f1"]["values"]
        axes[0].bar(i, np.mean(vals), color=C[c], alpha=0.85, yerr=np.std(vals, ddof=1) if len(vals) > 1 else 0, capsize=4)
        axes[0].scatter([i] * len(vals), vals, c="k", s=12, zorder=3)
        axes[0].text(i, np.mean(vals) + 0.012, f"{np.mean(vals):.3f}", ha="center", fontsize=8)
    if F["daysplit_v2_summary"]:
        vals = F["daysplit_v2_summary"]["test_spoil_macro_f1"]["values"]; i = len(conds)
        axes[0].bar(i, np.mean(vals), color=C["day"], alpha=0.85, yerr=np.std(vals, ddof=1) if len(vals) > 1 else 0, capsize=4)
        axes[0].scatter([i] * len(vals), vals, c="k", s=12, zorder=3); axes[0].text(i, np.mean(vals) + 0.012, f"{np.mean(vals):.3f}", ha="center", fontsize=8)
        conds_l = [COND_LABEL[c] for c in conds] + ["conv. aug,\nday-grouped split"]
    else:
        conds_l = [COND_LABEL[c] for c in conds]
    axes[0].set_xticks(range(len(conds_l)), [c.replace(" + ", "\n+ ") for c in conds_l], fontsize=7)
    axes[0].set_ylim(0.75, 1.0); axes[0].set_ylabel("test spoilage macro-F1"); axes[0].set_title("ViT-S/16, mean ± SD over seeds (dots = seeds)", fontsize=9)
    for r in v2.values():
        axes[1].plot(range(1, len(r["val_spoil_curve"]) + 1), r["val_spoil_curve"], c=C[r["cond"]], alpha=0.7, lw=1.2)
    for c in conds:
        axes[1].plot([], [], c=C[c], label=COND_LABEL[c])
    axes[1].legend(fontsize=7); axes[1].set_xlabel("epoch"); axes[1].set_ylabel("validation spoilage macro-F1"); axes[1].set_title("Validation curves, every run", fontsize=9)
    save(fig, "ablation_v2_comparison.png")
    fig, axes = plt.subplots(1, len(conds) + (1 if F["daysplit_v2_summary"] else 0), figsize=(3 * (len(conds) + 1), 3))
    items = [(COND_LABEL[c], S2[c]["cm_spoil_sum"]) for c in conds] + ([("day-grouped split (aug)", F["daysplit_v2_summary"]["cm_spoil_sum"])] if F["daysplit_v2_summary"] else [])
    for ax, (t, m) in zip(np.atleast_1d(axes), items):
        m = np.array(m); ax.imshow(m, cmap="Greens")
        for a in range(2):
            for b in range(2):
                ax.text(b, a, m[a, b], ha="center", va="center", color="white" if m[a, b] > m.max() / 2 else "black", fontsize=8)
        ax.set_xticks([0, 1], ["NS", "S"]); ax.set_yticks([0, 1], ["NS", "S"]); ax.set_xlabel("predicted"); ax.set_ylabel("true"); ax.set_title(t, fontsize=8)
    fig.suptitle("Spoilage confusion matrices summed over seeds (test split of the respective manifest)", fontsize=9)
    save(fig, "ablation_v2_confusions.png")
    fig, ax = plt.subplots(figsize=(7.5, 3.2)); x = np.arange(len(PRODUCE_CLASSES)); w = 0.8 / max(1, len(conds))
    for i, c in enumerate(conds):
        ax.bar(x + (i - (len(conds) - 1) / 2) * w, [S2[c]["spoiled_recall_by_produce"][t] for t in PRODUCE_CLASSES], w, color=C[c], label=COND_LABEL[c])
    ax.set_xticks(x, [t.replace("Indian_Gooseberry", "Gooseberry") for t in PRODUCE_CLASSES]); ax.set_ylabel("Spoiled recall (mean over seeds)")
    ax.set_ylim(0, 1.05); ax.legend(fontsize=7); ax.set_title("Recall of the Spoiled class per produce type (test)", fontsize=9)
    save(fig, "ablation_v2_spoiled_recall.png")

# GAN label consistency
q = F["gan"]["quality"]["label_consistency_by_primary_vit"]["per_condition"]
fig, ax = plt.subplots(figsize=(8, 3.2)); ks = list(q); x = np.arange(len(ks))
ax.bar(x - 0.2, [q[k]["type_match"] / q[k]["n"] for k in ks], 0.4, color="#2F6B4F", label="produce type matches condition")
ax.bar(x + 0.2, [q[k]["spoil_match"] / q[k]["n"] for k in ks], 0.4, color="#C1622E", label="spoilage matches condition")
ax.set_xticks(x, [k.replace("Indian_Gooseberry", "Goose.").replace("/Not_spoiled", "\nNS").replace("/Spoiled", "\nS") for k in ks], fontsize=7)
ax.set_ylim(0, 1.05); ax.set_ylabel("fraction of 40 GAN images"); ax.legend(fontsize=7, loc="upper left")
ax.set_title("GAN label consistency: deployed ViT-B (trained on real images only) applied to generated images", fontsize=9)
save(fig, "gan_label_consistency.png")

json.dump(F, open(FR / "build/facts.json", "w"), indent=1, default=float)
json.dump(F, open(DATA / "all_facts.json", "w"), indent=1, default=float)
print("facts written;", "ablation v2 runs complete:", sum(r["complete"] for r in v2.values()), "/ 9; day2:", len(day2),
      "; dncnn_v2:", F["dncnn_v2"] is not None, "; figures:", len(list(FIG.glob("*.png"))))
