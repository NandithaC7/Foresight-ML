#!/usr/bin/env python3
"""Generate reproducible noisy derivatives of TR-6 images.

Never writes to the original TR-6 tree. Derived files are synthetic and must
not be treated as independent test specimens. Inherited labels remain unverified.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


PRODUCE = ("Banana", "Carrot", "Guava", "Indian_Gooseberry", "Mango", "Tomato")
MODALITIES = ("srgb", "thermal_ir_fusion")
JPEG_EXPANSION = 1.6
SAFETY_FACTOR = 2.0


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def stable_int(text):
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], 16)


def content_split(content_id, split_seed):
    bucket = stable_int("%s|split|%s" % (split_seed, content_id)) % 100
    if bucket < 70:
        return "train"
    if bucket < 85:
        return "val"
    return "test"


def transform_seed(base_seed, content_id, name, severity):
    return stable_int("%s|%s|%s|%s" % (base_seed, content_id, name, severity)) % (2**32)


def load_stored_rgb(path):
    with Image.open(path) as image:
        stored = image.convert("RGB")
        array = np.array(stored)
        width, height = stored.size
    return array, width, height


def apply_gaussian(array, rng, sigma):
    noise = rng.normal(0.0, sigma, array.shape)
    return np.clip(array.astype(np.float32) + noise, 0, 255).astype(np.uint8)


def apply_salt_pepper(array, rng, amount):
    out = array.copy()
    mask = rng.random(array.shape[:2])
    pepper = mask < (amount / 2.0)
    salt = mask > (1.0 - amount / 2.0)
    out[pepper] = 0
    out[salt] = 255
    return out


def apply_speckle(array, rng, variance):
    noise = rng.normal(0.0, np.sqrt(variance), array.shape)
    return np.clip(array.astype(np.float32) * (1.0 + noise), 0, 255).astype(np.uint8)


def apply_transform(array, spec, seed):
    rng = np.random.default_rng(seed)
    name = spec["name"]
    params = spec["params"]
    if name == "gaussian":
        return apply_gaussian(array, rng, params["sigma"])
    if name == "salt_pepper":
        return apply_salt_pepper(array, rng, params["amount"])
    if name == "speckle":
        return apply_speckle(array, rng, params["variance"])
    raise ValueError("Unknown transform %s" % name)


def select_sources(pilot_rows, per_stratum):
    grouped = defaultdict(list)
    for row in pilot_rows:
        grouped[(row["produce_type"], row["apparent_modality"])].append(row)
    selected = []
    for produce in PRODUCE:
        for modality in MODALITIES:
            stratum = grouped[(produce, modality)]
            selected.extend(stratum[:per_stratum])
    return selected


def estimate_bytes(sources, transforms_by_modality):
    total = 0
    for row in sources:
        n = len(transforms_by_modality[row["apparent_modality"]])
        total += int(float(row.get("size_bytes") or 0) * n * JPEG_EXPANSION)
    return total


def attach_source_size(sources, master_by_id):
    for row in sources:
        master = master_by_id.get(row["record_id"], {})
        row["size_bytes"] = master.get("size_bytes", "0")
        row["existing_path_label"] = master.get("existing_path_label", "unknown")
        row["duplicate_group_id"] = master.get("duplicate_group_id", "none")
        row["source_directory"] = master.get("source_directory", "unknown")
        row["label_status"] = master.get("label_status", "unlabeled")
    return sources


def save_jpeg(array, path, quality):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(array).save(path, format="JPEG", quality=quality, subsampling=0)


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def comparison_sheet(dataset, pairs, out_path, thumb_h=220):
    tiles = []
    labels = []
    for source_path, variants in pairs:
        with Image.open(source_path) as original:
            stored = original.convert("RGB")
            scale = thumb_h / stored.height
            thumb = stored.resize((max(1, int(stored.width * scale)), thumb_h), Image.Resampling.BILINEAR)
        row_tiles = [thumb]
        row_labels = ["clean original"]
        for caption, derived_path in variants:
            with Image.open(derived_path) as derived:
                image = derived.convert("RGB")
                scale = thumb_h / image.height
                row_tiles.append(image.resize((max(1, int(image.width * scale)), thumb_h), Image.Resampling.BILINEAR))
                row_labels.append(caption)
        tiles.append(row_tiles)
        labels.append(row_labels)
    if not tiles:
        return
    col_w = max(im.width for row in tiles for im in row) + 8
    row_h = thumb_h + 28
    sheet = Image.new("RGB", (col_w * len(tiles[0]), row_h * len(tiles) + 24), "white")
    draw = ImageDraw.Draw(sheet)
    draw.text((8, 6), "Clean originals vs synthetic noisy derivatives. Derivatives are not independent specimens.", fill="black")
    y = 24
    for row_tiles, row_labels in zip(tiles, labels):
        x = 0
        for image, caption in zip(row_tiles, row_labels):
            sheet.paste(image, (x + 4, y + 18))
            draw.text((x + 4, y + 2), caption, fill="black")
            x += col_w
        y += row_h
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path, quality=90)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--output-name", default="noise-pilot-v1")
    parser.add_argument("--source-set", choices=("pilot_sample", "pilot"), default="pilot_sample")
    parser.add_argument("--per-stratum", type=int, default=None)
    parser.add_argument("--estimate-only", action="store_true")
    parser.add_argument("--seed", default=None)
    args = parser.parse_args()

    workspace = args.workspace.resolve()
    dataset = args.dataset.resolve()
    config_path = args.config or (workspace / "config" / "noise_generation.json")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    seed = args.seed or config["selection_seed"]
    split_seed = config["split_seed"]
    quality = int(config["jpeg_quality"])
    per_stratum = args.per_stratum
    if per_stratum is None:
        per_stratum = config["pilot"]["images_per_produce_modality"] if args.source_set == "pilot_sample" else 8

    master = read_csv(workspace / "manifests" / "master_manifest.csv")
    master_by_id = {row["record_id"]: row for row in master}
    pilot = read_csv(workspace / "manifests" / "pilot_manifest.csv")
    if args.source_set == "pilot":
        sources = attach_source_size(pilot, master_by_id)
    else:
        sources = attach_source_size(select_sources(pilot, per_stratum), master_by_id)

    transforms = config["transforms"]
    derived_count = sum(len(transforms[row["apparent_modality"]]) for row in sources)
    estimated = estimate_bytes(sources, transforms)
    disk = shutil.disk_usage(workspace)
    estimate = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_set": args.source_set,
        "source_images": len(sources),
        "derived_images": derived_count,
        "estimated_output_bytes": estimated,
        "estimated_output_mb": round(estimated / (1024 * 1024), 2),
        "disk_free_bytes": disk.free,
        "disk_free_gb": round(disk.free / (1024 ** 3), 2),
        "safety_factor": SAFETY_FACTOR,
        "enough_free_space": disk.free > estimated * SAFETY_FACTOR,
        "note": "Estimate uses source JPEG sizes times %.1f. Actual noisy JPEGs may be larger because noise reduces compressibility." % JPEG_EXPANSION,
    }
    reports = workspace / "reports" / args.output_name
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "disk_estimate.json").write_text(json.dumps(estimate, indent=2), encoding="utf-8")
    print(json.dumps(estimate, indent=2))
    if args.estimate_only:
        return
    if not estimate["enough_free_space"]:
        raise SystemExit("Refusing to generate: free disk %.2f GB is below 2x the %.2f MB estimate." % (
            estimate["disk_free_gb"], estimate["estimated_output_mb"]
        ))

    out_root = workspace / "derived-data" / args.output_name
    image_root = out_root / "images"
    manifest_path = workspace / "manifests" / "derived" / ("%s_manifest.csv" % args.output_name.replace("-", "_"))
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    comparison_pairs = []
    fieldnames = [
        "derived_id", "source_pilot_id", "source_record_id", "source_content_id",
        "source_relative_path", "source_sha256", "source_directory", "produce_type",
        "apparent_modality", "inherited_source_label", "label_independently_verified",
        "label_status", "duplicate_group_id", "split", "transformation", "severity",
        "parameters_json", "seed", "derived_relative_path", "derived_sha256",
        "width", "height", "is_synthetic", "usable_as_independent_test_specimen",
        "processing_status", "error", "generated_at",
    ]

    for source in sources:
        source_path = dataset / source["original_relative_path"]
        split = content_split(source["content_id"], split_seed)
        try:
            array, width, height = load_stored_rgb(source_path)
            if (width, height) != (int(source["width"]), int(source["height"])):
                raise ValueError("Decoded size %sx%s differs from manifest %sx%s" % (
                    width, height, source["width"], source["height"]
                ))
        except Exception as exc:
            rows.append({
                "derived_id": "",
                "source_pilot_id": source["pilot_id"],
                "source_record_id": source["record_id"],
                "source_content_id": source["content_id"],
                "source_relative_path": source["original_relative_path"],
                "source_sha256": source["sha256"],
                "source_directory": source.get("source_directory", ""),
                "produce_type": source["produce_type"],
                "apparent_modality": source["apparent_modality"],
                "inherited_source_label": source.get("existing_path_label", "unknown"),
                "label_independently_verified": "false",
                "label_status": source.get("label_status", "unlabeled"),
                "duplicate_group_id": source.get("duplicate_group_id", "none"),
                "split": split,
                "transformation": "",
                "severity": "",
                "parameters_json": "",
                "seed": "",
                "derived_relative_path": "",
                "derived_sha256": "",
                "width": source["width"],
                "height": source["height"],
                "is_synthetic": "true",
                "usable_as_independent_test_specimen": "false",
                "processing_status": "failed",
                "error": repr(exc),
                "generated_at": now,
            })
            continue

        variants = []
        for spec in transforms[source["apparent_modality"]]:
            seed_value = transform_seed(seed, source["content_id"], spec["name"], spec["severity"])
            derived_id = "tr6n_%s_%s_%s" % (source["pilot_id"], spec["name"], spec["severity"])
            rel = Path(source["apparent_modality"]) / source["produce_type"] / ("%s.jpg" % derived_id)
            dest = image_root / rel
            status = "ok"
            error = ""
            digest = ""
            try:
                noisy = apply_transform(array, spec, seed_value)
                if noisy.shape[:2] != (height, width):
                    raise ValueError("Derived array shape changed")
                save_jpeg(noisy, dest, quality)
                with Image.open(dest) as check:
                    check.verify()
                with Image.open(dest) as check:
                    if check.size != (width, height):
                        raise ValueError("Saved JPEG dimensions changed")
                digest = sha256_file(dest)
            except Exception as exc:
                status = "failed"
                error = repr(exc)
            rows.append({
                "derived_id": derived_id,
                "source_pilot_id": source["pilot_id"],
                "source_record_id": source["record_id"],
                "source_content_id": source["content_id"],
                "source_relative_path": source["original_relative_path"],
                "source_sha256": source["sha256"],
                "source_directory": source.get("source_directory", ""),
                "produce_type": source["produce_type"],
                "apparent_modality": source["apparent_modality"],
                "inherited_source_label": source.get("existing_path_label", "unknown"),
                "label_independently_verified": "false",
                "label_status": source.get("label_status", "unlabeled"),
                "duplicate_group_id": source.get("duplicate_group_id", "none"),
                "split": split,
                "transformation": spec["name"],
                "severity": spec["severity"],
                "parameters_json": json.dumps(spec["params"], sort_keys=True),
                "seed": str(seed_value),
                "derived_relative_path": str(Path("derived-data") / args.output_name / "images" / rel),
                "derived_sha256": digest,
                "width": str(width),
                "height": str(height),
                "is_synthetic": "true",
                "usable_as_independent_test_specimen": "false",
                "processing_status": status,
                "error": error,
                "generated_at": now,
            })
            if status == "ok":
                variants.append(("%s_%s" % (spec["name"], spec["severity"]), dest))
        if source["pilot_id"] in {"tr6p_001", "tr6p_009", "tr6p_065", "tr6p_073"} and variants:
            comparison_pairs.append((source_path, variants))

    write_csv(manifest_path, rows, fieldnames)
    if comparison_pairs:
        comparison_sheet(
            dataset,
            comparison_pairs,
            reports / "clean_vs_noisy_comparison.jpg",
        )
    summary = {
        "generated_at": now,
        "output_name": args.output_name,
        "source_images": len(sources),
        "derived_rows": len(rows),
        "ok": sum(row["processing_status"] == "ok" for row in rows),
        "failed": sum(row["processing_status"] == "failed" for row in rows),
        "manifest": str(manifest_path.relative_to(workspace)),
        "image_root": str(image_root.relative_to(workspace)),
        "disk_estimate": estimate,
        "checkpoint_status": "no_trained_checkpoint_found",
        "source_dataset_untouched": True,
    }
    (reports / "generation_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("source_images", "derived_rows", "ok", "failed", "manifest")}, indent=2))


if __name__ == "__main__":
    main()
