#!/usr/bin/env python3
"""Build Foresight-TR6+ manifests and an annotation pilot from TR-6 audit outputs.

The script never writes to the source dataset and never copies source images.
Only small review contact sheets are derived from selected pilot images.
"""

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps


PRODUCE = ("Banana", "Carrot", "Guava", "Indian_Gooseberry", "Mango", "Tomato")
MODALITIES = ("srgb", "thermal_ir_fusion")
MASTER_FIELDS = (
    "record_id",
    "content_id",
    "source_dataset",
    "original_relative_path",
    "source_path_relative_to_workspace",
    "sha256",
    "size_bytes",
    "extension",
    "source_directory",
    "produce_type",
    "apparent_modality",
    "existing_path_label",
    "spoilage_label",
    "label_origin",
    "label_independently_verified",
    "label_status",
    "filename_timestamp",
    "timestamp_status",
    "width",
    "height",
    "image_format",
    "color_mode",
    "file_read_status",
    "file_validation_status",
    "duplicate_group_id",
    "duplicate_member_count",
    "cross_source_duplicate",
    "cross_label_conflict",
    "canonical_content_reference",
    "specimen_id",
    "capture_id",
    "view_id",
    "cross_modal_group_id",
    "segmentation_pilot_eligible",
    "spoilage_supervision_eligible",
)


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows, fieldnames=None):
    rows = list(rows)
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def stable_rank(seed, value):
    return hashlib.sha256(("%s|%s" % (seed, value)).encode("utf-8")).hexdigest()


def bool_text(value):
    return "true" if value else "false"


def select_stratum(candidates, count, seed):
    """Select deterministically while preferring dimension and date diversity."""
    if len(candidates) < count:
        raise ValueError("Need %d candidates, found %d" % (count, len(candidates)))
    selected = []
    selected_paths = set()
    selected_dates = Counter()

    by_dimensions = defaultdict(list)
    for row in candidates:
        by_dimensions[(row["width"], row["height"])].append(row)
    for dimension in sorted(by_dimensions):
        ranked = sorted(
            by_dimensions[dimension],
            key=lambda row: stable_rank(seed, "dimension|" + row["original_relative_path"]),
        )
        choice = ranked[0]
        selected.append(choice)
        selected_paths.add(choice["original_relative_path"])
        selected_dates[choice["filename_timestamp"][:10] or "unknown"] += 1
        if len(selected) == count:
            return selected

    remaining = [row for row in candidates if row["original_relative_path"] not in selected_paths]
    remaining.sort(
        key=lambda row: (
            selected_dates[row["filename_timestamp"][:10] or "unknown"],
            stable_rank(seed, "date|" + row["original_relative_path"]),
        )
    )
    while len(selected) < count:
        best = min(
            remaining,
            key=lambda row: (
                selected_dates[row["filename_timestamp"][:10] or "unknown"],
                stable_rank(seed, "fill|" + row["original_relative_path"]),
            ),
        )
        selected.append(best)
        selected_paths.add(best["original_relative_path"])
        selected_dates[best["filename_timestamp"][:10] or "unknown"] += 1
        remaining.remove(best)
    return selected


def make_contact_sheet(rows, dataset_root, output_path, title):
    cell_width, cell_height = 280, 225
    columns = 4
    sheet_rows = math.ceil(len(rows) / columns)
    canvas = Image.new("RGB", (columns * cell_width, 42 + sheet_rows * cell_height), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text((12, 12), title, fill="black")
    for index, row in enumerate(rows):
        x = (index % columns) * cell_width
        y = 42 + (index // columns) * cell_height
        path = dataset_root / row["original_relative_path"]
        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            image.thumbnail((cell_width - 16, 170))
            canvas.paste(image, (x + 8, y + 8))
        draw.text((x + 8, y + 184), "%s | %s" % (row["produce_type"], row["apparent_modality"]), fill="black")
        draw.text((x + 8, y + 200), Path(row["original_relative_path"]).name[:39], fill="black")
    canvas.save(output_path, format="JPEG", quality=84)


def relative_source_path(workspace, dataset_root, original_relative_path):
    return str((Path("..") / dataset_root.name / original_relative_path).as_posix())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--audit-output", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--seed", default="20261012")
    parser.add_argument("--per-produce-modality", type=int, default=8)
    args = parser.parse_args()

    dataset_root = args.dataset.resolve()
    audit_output = args.audit_output.resolve()
    workspace = args.workspace.resolve()
    if not dataset_root.is_dir():
        raise SystemExit("Missing dataset: %s" % dataset_root)
    if dataset_root == workspace or dataset_root in workspace.parents:
        raise SystemExit("Workspace must not be inside the source dataset")

    for directory in ("manifests", "annotations", "imports", "reports", "checksums"):
        (workspace / directory).mkdir(parents=True, exist_ok=True)

    inventory = read_csv(audit_output / "file_inventory.csv")
    duplicate_members = read_csv(audit_output / "exact_duplicate_files.csv")
    duplicate_by_path = {row["path"]: row for row in duplicate_members}
    hash_members = defaultdict(list)
    for row in inventory:
        if row["sha256"]:
            hash_members[row["sha256"]].append(row)

    canonical_path_by_hash = {}
    for digest, members in hash_members.items():
        canonical = min(
            members,
            key=lambda row: (
                0 if row["source"] == "Normal" else 1,
                0 if row["source"] == "root" else 1,
                row["path"],
            ),
        )
        canonical_path_by_hash[digest] = canonical["path"]

    master = []
    for source_row in inventory:
        path = source_row["path"]
        digest = source_row["sha256"]
        duplicate = duplicate_by_path.get(path, {})
        conflict = duplicate.get("cross_label", "False") == "True"
        path_label = source_row["label"]
        is_classified_label = source_row["source"] == "Classified" and path_label in ("Spoiled", "Not_spoiled")
        if is_classified_label:
            spoilage_label = path_label
            label_origin = "inherited_from_directory_name"
            label_status = "inherited_conflicting" if conflict else "inherited_unverified"
        else:
            spoilage_label = "unknown"
            label_origin = "unavailable"
            label_status = "unlabeled"
        is_image = source_row["modality"] in MODALITIES
        canonical = bool(digest and canonical_path_by_hash.get(digest) == path)
        pilot_eligible = (
            is_image
            and source_row["source"] == "Normal"
            and source_row["validation_status"] == "valid"
            and not conflict
            and canonical
            and source_row["produce"] in PRODUCE
        )
        record_digest = hashlib.sha256(path.encode("utf-8")).hexdigest()
        master.append({
            "record_id": "tr6r_" + record_digest,
            "content_id": ("tr6c_" + digest) if digest else "unknown",
            "source_dataset": "TR-6",
            "original_relative_path": path,
            "source_path_relative_to_workspace": relative_source_path(workspace, dataset_root, path),
            "sha256": digest,
            "size_bytes": source_row["size_bytes"],
            "extension": source_row["extension"],
            "source_directory": source_row["source"],
            "produce_type": source_row["produce"] or "unknown",
            "apparent_modality": source_row["modality"],
            "existing_path_label": path_label or "unknown",
            "spoilage_label": spoilage_label,
            "label_origin": label_origin,
            "label_independently_verified": "false",
            "label_status": label_status,
            "filename_timestamp": source_row["timestamp_from_filename"] or "unknown",
            "timestamp_status": "parsed_from_filename_unverified" if source_row["timestamp_from_filename"] else "unknown",
            "width": source_row["width"] or "unknown",
            "height": source_row["height"] or "unknown",
            "image_format": source_row["format"] or "unknown",
            "color_mode": source_row["color_mode"] or "unknown",
            "file_read_status": source_row["read_status"],
            "file_validation_status": source_row["validation_status"],
            "duplicate_group_id": duplicate.get("duplicate_group", "none"),
            "duplicate_member_count": duplicate.get("member_count", "1"),
            "cross_source_duplicate": bool_text(duplicate.get("cross_source", "False") == "True"),
            "cross_label_conflict": bool_text(conflict),
            "canonical_content_reference": bool_text(canonical),
            "specimen_id": "unknown",
            "capture_id": "unknown",
            "view_id": "unknown",
            "cross_modal_group_id": "unknown",
            "segmentation_pilot_eligible": bool_text(pilot_eligible),
            "spoilage_supervision_eligible": "false",
        })

    master_path = workspace / "manifests" / "master_manifest.csv"
    write_csv(master_path, master, MASTER_FIELDS)

    exclusions = []
    conflict_groups = defaultdict(list)
    for row in master:
        if row["cross_label_conflict"] == "true":
            conflict_groups[row["duplicate_group_id"]].append(row)
    for group_id, rows in sorted(conflict_groups.items()):
        labels = sorted({row["existing_path_label"] for row in rows if row["existing_path_label"] != "unknown"})
        exclusions.append({
            "content_id": rows[0]["content_id"],
            "duplicate_group_id": group_id,
            "reason_code": "cross_label_exact_duplicate_conflict",
            "observed_labels": ";".join(labels),
            "affected_record_count": len(rows),
            "affected_paths": ";".join(sorted(row["original_relative_path"] for row in rows)),
            "decision": "exclude_from_spoilage_supervision_and_pilot_pending_provenance",
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        })
    write_csv(workspace / "manifests" / "exclusion_log.csv", exclusions)

    candidates = [
        row for row in master
        if row["segmentation_pilot_eligible"] == "true"
        and row["produce_type"] in PRODUCE
        and row["apparent_modality"] in MODALITIES
    ]
    by_stratum = defaultdict(list)
    for row in candidates:
        by_stratum[(row["produce_type"], row["apparent_modality"])].append(row)

    selected = []
    for produce in PRODUCE:
        for modality in MODALITIES:
            key = (produce, modality)
            chosen = select_stratum(
                by_stratum[key],
                args.per_produce_modality,
                "%s|%s|%s" % (args.seed, produce, modality),
            )
            selected.extend(chosen)
    selected.sort(key=lambda row: (PRODUCE.index(row["produce_type"]), MODALITIES.index(row["apparent_modality"]), row["filename_timestamp"], row["original_relative_path"]))

    pilot_rows = []
    annotation_rows = []
    coco_images = []
    label_studio_tasks = []
    for index, row in enumerate(selected, 1):
        pilot_id = "tr6p_%03d" % index
        pilot = {
            "pilot_id": pilot_id,
            "record_id": row["record_id"],
            "content_id": row["content_id"],
            "original_relative_path": row["original_relative_path"],
            "source_path_relative_to_workspace": row["source_path_relative_to_workspace"],
            "sha256": row["sha256"],
            "produce_type": row["produce_type"],
            "apparent_modality": row["apparent_modality"],
            "spoilage_label": "unknown",
            "spoilage_label_status": "not_used_for_pilot",
            "cross_label_conflict": row["cross_label_conflict"],
            "filename_timestamp": row["filename_timestamp"],
            "width": row["width"],
            "height": row["height"],
            "selection_seed": args.seed,
            "selection_method": "canonical Normal content; conflict-free; dimension-aware deterministic date diversity",
            "annotation_status": "pending",
            "fruit_mask_required": "true",
            "visible_defect_mask": "conditional_if_visually_identifiable",
        }
        pilot_rows.append(pilot)
        annotation_rows.append({
            "pilot_id": pilot_id,
            "content_id": row["content_id"],
            "annotation_status": "pending",
            "annotator_id": "",
            "reviewer_id": "",
            "annotation_file": "",
            "raster_mask_path": "",
            "fruit_instance_count": "",
            "visible_defect_instance_count": "",
            "image_quality": "",
            "exclusion_reason": "",
            "annotation_started_at": "",
            "annotation_completed_at": "",
            "reviewed_at": "",
            "notes": "",
        })
        coco_images.append({
            "id": index,
            "file_name": row["source_path_relative_to_workspace"],
            "width": int(row["width"]),
            "height": int(row["height"]),
            "ftr6plus_pilot_id": pilot_id,
            "ftr6plus_content_id": row["content_id"],
            "produce_type": row["produce_type"],
            "apparent_modality": row["apparent_modality"],
            "spoilage_label": None,
        })
        label_studio_tasks.append({
            "id": index,
            "data": {
                "image": "/data/local-files/?d=TR-6/" + row["original_relative_path"],
                "pilot_id": pilot_id,
                "content_id": row["content_id"],
                "relative_path": row["original_relative_path"],
                "produce_type": row["produce_type"],
                "apparent_modality": row["apparent_modality"],
            },
            "meta": {
                "annotation_status": "pending",
                "cross_label_conflict": False,
                "spoilage_label": "unknown",
            },
            "annotations": [],
        })

    write_csv(workspace / "manifests" / "pilot_manifest.csv", pilot_rows)
    write_csv(workspace / "annotations" / "annotation_records.csv", annotation_rows)

    coco_template = {
        "info": {
            "description": "Foresight-TR6+ pilot annotation template; contains no ground-truth annotations",
            "version": "0.1-pilot",
            "created": datetime.now(timezone.utc).isoformat(),
            "selection_seed": args.seed,
            "annotation_status": "pending",
        },
        "licenses": [],
        "images": coco_images,
        "annotations": [],
        "categories": [
            {"id": 1, "name": "fruit_visible_region", "supercategory": "fruit"},
            {"id": 2, "name": "visible_defect_region", "supercategory": "fruit_condition"},
        ],
    }
    (workspace / "imports" / "pilot_coco_template.json").write_text(
        json.dumps(coco_template, indent=2), encoding="utf-8"
    )
    (workspace / "annotations" / "coco_annotations.json").write_text(
        json.dumps(coco_template, indent=2), encoding="utf-8"
    )
    (workspace / "imports" / "label_studio_tasks.json").write_text(
        json.dumps(label_studio_tasks, indent=2), encoding="utf-8"
    )
    calibration_rows = []
    calibration_ids = set()
    for produce in PRODUCE:
        for modality in MODALITIES:
            row = next(
                item for item in pilot_rows
                if item["produce_type"] == produce and item["apparent_modality"] == modality
            )
            calibration_rows.append(row)
            calibration_ids.add(row["pilot_id"])
    write_csv(workspace / "manifests" / "calibration_batch.csv", calibration_rows)
    calibration_tasks = [
        task for task in label_studio_tasks
        if task["data"]["pilot_id"] in calibration_ids
    ]
    (workspace / "imports" / "calibration_label_studio_tasks.json").write_text(
        json.dumps(calibration_tasks, indent=2), encoding="utf-8"
    )

    available_summary = []
    groups = defaultdict(list)
    for row in master:
        if row["apparent_modality"] in MODALITIES and row["produce_type"] in PRODUCE:
            groups[(row["source_directory"], row["produce_type"], row["apparent_modality"])].append(row)
    for key, rows in sorted(groups.items()):
        available_summary.append({
            "source_directory": key[0],
            "produce_type": key[1],
            "apparent_modality": key[2],
            "file_records": len(rows),
            "unique_content_hashes": len({row["sha256"] for row in rows}),
            "cross_label_conflict_records": sum(row["cross_label_conflict"] == "true" for row in rows),
            "pilot_eligible_canonical_records": sum(row["segmentation_pilot_eligible"] == "true" for row in rows),
        })
    write_csv(workspace / "reports" / "available_images_by_produce_modality.csv", available_summary)

    pilot_summary = []
    pilot_groups = defaultdict(list)
    for row in pilot_rows:
        pilot_groups[(row["produce_type"], row["apparent_modality"])].append(row)
    for key, rows in sorted(pilot_groups.items()):
        pilot_summary.append({
            "produce_type": key[0],
            "apparent_modality": key[1],
            "selected_images": len(rows),
            "unique_dates": len({row["filename_timestamp"][:10] for row in rows}),
            "dimensions": ";".join(sorted({"%sx%s" % (row["width"], row["height"]) for row in rows})),
            "annotation_status_pending": sum(row["annotation_status"] == "pending" for row in rows),
        })
    write_csv(workspace / "reports" / "pilot_summary.csv", pilot_summary)

    for modality in MODALITIES:
        review_rows = []
        for produce in PRODUCE:
            options = [row for row in pilot_rows if row["produce_type"] == produce and row["apparent_modality"] == modality]
            review_rows.extend(options[:2])
        make_contact_sheet(
            review_rows,
            dataset_root,
            workspace / "reports" / ("pilot_review_%s.jpg" % modality),
            "Foresight-TR6+ pilot review: %s (no annotations)" % modality,
        )

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_dataset": str(dataset_root),
        "audit_output": str(audit_output),
        "workspace": str(workspace),
        "master_manifest_records": len(master),
        "image_records": sum(row["apparent_modality"] in MODALITIES for row in master),
        "unique_image_content_ids": len({
            row["content_id"] for row in master if row["apparent_modality"] in MODALITIES
        }),
        "cross_label_conflict_groups": len(exclusions),
        "pilot_size": len(pilot_rows),
        "pilot_per_produce_modality": args.per_produce_modality,
        "pilot_source_directory": "Normal",
        "pilot_spoilage_labels_used": False,
        "pilot_cross_label_conflicts": sum(row["cross_label_conflict"] == "true" for row in pilot_rows),
        "calibration_batch_size": len(calibration_rows),
        "annotation_status_counts": dict(Counter(row["annotation_status"] for row in annotation_rows)),
        "selection_seed": args.seed,
        "source_images_copied": 0,
        "derived_review_contact_sheets": 2,
    }
    (workspace / "reports" / "build_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )

    checksum_lines = []
    for path in sorted(path for path in workspace.rglob("*") if path.is_file()):
        if path == workspace / "checksums" / "extension_files_sha256.txt":
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        checksum_lines.append("%s  %s" % (digest, path.relative_to(workspace)))
    (workspace / "checksums" / "extension_files_sha256.txt").write_text(
        "\n".join(checksum_lines) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
