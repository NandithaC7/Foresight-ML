#!/usr/bin/env python3
"""Validate Foresight-TR6+ manifests, source references and annotations."""

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image


ALLOWED_STATUSES = {"pending", "pending_review", "annotated", "reviewed", "excluded"}
ALLOWED_PROPOSAL_STATUSES = {"", "none", "proposal_only"}
ALLOWED_LS_STATUSES = {"", "not_imported", "unsubmitted", "submitted", "cancelled"}
HUMAN_COMPLETE_STATUSES = {"annotated", "reviewed"}
INCOMPLETE_HUMAN_STATUSES = {"pending", "pending_review"}
PROPOSAL_COCO = "annotations/coco_annotations.json"
HUMAN_COCO = "annotations/human_coco_annotations.json"
ALLOWED_MASK_VALUES = {0, 1, 2, 255}
PRODUCE = {"Banana", "Carrot", "Guava", "Indian_Gooseberry", "Mango", "Tomato"}
MODALITIES = {"srgb", "thermal_ir_fusion"}


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(8 * 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--hash-mode", choices=("none", "pilot", "all"), default="pilot")
    args = parser.parse_args()

    dataset = args.dataset.resolve()
    workspace = args.workspace.resolve()
    errors = []
    warnings = []
    checks = Counter()

    def error(code, message, path=""):
        errors.append({"severity": "error", "code": code, "path": path, "message": message})

    def warning(code, message, path=""):
        warnings.append({"severity": "warning", "code": code, "path": path, "message": message})

    if not dataset.is_dir():
        error("dataset_missing", "Source dataset directory does not exist", str(dataset))
    if dataset == workspace or dataset in workspace.parents:
        error("workspace_location", "Extension workspace must not be inside the source dataset", str(workspace))

    master_path = workspace / "manifests" / "master_manifest.csv"
    pilot_path = workspace / "manifests" / "pilot_manifest.csv"
    annotations_path = workspace / "annotations" / "annotation_records.csv"
    coco_path = workspace / "annotations" / "coco_annotations.json"
    calibration_path = workspace / "manifests" / "calibration_batch.csv"
    for required in (master_path, pilot_path, annotations_path, coco_path, calibration_path):
        if not required.is_file():
            error("required_file_missing", "Required extension file is missing", str(required))
    if errors:
        raise SystemExit(json.dumps(errors, indent=2))

    master = read_csv(master_path)
    pilot = read_csv(pilot_path)
    annotation_records = read_csv(annotations_path)
    calibration = read_csv(calibration_path)
    coco = json.loads(coco_path.read_text(encoding="utf-8"))
    checks["master_records"] = len(master)
    checks["pilot_records"] = len(pilot)
    checks["annotation_records"] = len(annotation_records)
    checks["calibration_records"] = len(calibration)

    if len(master) != 21653:
        error("master_count", "Expected 21,653 audited records, found %d" % len(master))
    record_ids = [row["record_id"] for row in master]
    if len(record_ids) != len(set(record_ids)):
        error("master_record_id_duplicate", "Master record IDs are not unique")
    master_by_record = {row["record_id"]: row for row in master}
    master_by_path = {row["original_relative_path"]: row for row in master}
    if len(master_by_path) != len(master):
        error("master_path_duplicate", "Master manifest contains duplicate relative paths")

    source_files_seen = 0
    for row in master:
        relative = Path(row["original_relative_path"])
        if relative.is_absolute() or ".." in relative.parts:
            error("unsafe_relative_path", "Original path must be safe and relative", row["original_relative_path"])
            continue
        source = dataset / relative
        if not source.is_file():
            error("source_missing", "Referenced source file is missing", row["original_relative_path"])
            continue
        source_files_seen += 1
        try:
            if source.stat().st_size != int(row["size_bytes"]):
                error("size_mismatch", "Source byte size differs from manifest", row["original_relative_path"])
        except ValueError:
            error("invalid_size", "Manifest size is not an integer", row["original_relative_path"])
        if row["source_directory"] == "Normal":
            if row["spoilage_label"] != "unknown" or row["label_status"] != "unlabeled":
                error("normal_has_spoilage_label", "Normal record must remain spoilage-unlabeled", row["original_relative_path"])
        if row["label_independently_verified"] != "false":
            error("unsupported_verified_label", "No inherited spoilage label is independently verified", row["original_relative_path"])
        for unknown_field in ("specimen_id", "capture_id", "view_id", "cross_modal_group_id"):
            if row[unknown_field] != "unknown":
                error("invented_identifier", "%s must remain unknown" % unknown_field, row["original_relative_path"])
    checks["source_paths_found"] = source_files_seen

    duplicate_groups = defaultdict(list)
    for row in master:
        if row["duplicate_group_id"] != "none":
            duplicate_groups[row["duplicate_group_id"]].append(row)
    for group_id, rows in duplicate_groups.items():
        hashes = {row["sha256"] for row in rows}
        if len(hashes) != 1:
            error("duplicate_group_hash_mismatch", "Duplicate group has multiple hashes", group_id)
        declared = {int(row["duplicate_member_count"]) for row in rows}
        if declared != {len(rows)}:
            error("duplicate_member_count", "Declared duplicate count differs from rows", group_id)
        labels = {row["existing_path_label"] for row in rows if row["existing_path_label"] in ("Spoiled", "Not_spoiled")}
        expected_conflict = len(labels) > 1
        if any((row["cross_label_conflict"] == "true") != expected_conflict for row in rows):
            error("conflict_flag_mismatch", "Cross-label conflict flag is inconsistent", group_id)
    checks["duplicate_groups"] = len(duplicate_groups)
    checks["cross_label_conflict_groups"] = sum(
        any(row["cross_label_conflict"] == "true" for row in rows)
        for rows in duplicate_groups.values()
    )

    if len(pilot) != 96:
        error("pilot_count", "Expected 96 pilot records, found %d" % len(pilot))
    if len({row["pilot_id"] for row in pilot}) != len(pilot):
        error("pilot_id_duplicate", "Pilot IDs are not unique")
    if len({row["content_id"] for row in pilot}) != len(pilot):
        error("pilot_content_duplicate", "Pilot contains exact duplicate content references")
    strata = Counter((row["produce_type"], row["apparent_modality"]) for row in pilot)
    expected_strata = {(produce, modality) for produce in PRODUCE for modality in MODALITIES}
    if set(strata) != expected_strata:
        error("pilot_strata", "Pilot does not cover all produce × modality strata")
    for key in expected_strata:
        if strata[key] != 8:
            error("pilot_stratum_count", "%s/%s has %d records, expected 8" % (key[0], key[1], strata[key]))
    if len(calibration) != 12:
        error("calibration_count", "Expected 12 calibration records, found %d" % len(calibration))
    calibration_strata = Counter((row["produce_type"], row["apparent_modality"]) for row in calibration)
    if set(calibration_strata) != expected_strata or any(value != 1 for value in calibration_strata.values()):
        error("calibration_strata", "Calibration batch must contain one image per produce × modality")
    if not {row["pilot_id"] for row in calibration}.issubset({row["pilot_id"] for row in pilot}):
        error("calibration_not_in_pilot", "Calibration batch contains records outside pilot")

    pilot_by_id = {row["pilot_id"]: row for row in pilot}
    for row in pilot:
        master_row = master_by_record.get(row["record_id"])
        if not master_row:
            error("pilot_master_link", "Pilot record does not link to master", row["pilot_id"])
            continue
        if master_row["source_directory"] != "Normal":
            error("pilot_source", "Pilot must reference Normal-tree content", row["pilot_id"])
        if master_row["canonical_content_reference"] != "true":
            error("pilot_not_canonical", "Pilot must use canonical content reference", row["pilot_id"])
        if master_row["cross_label_conflict"] != "false" or row["cross_label_conflict"] != "false":
            error("pilot_conflict", "Cross-label conflict entered pilot", row["pilot_id"])
        if row["spoilage_label"] != "unknown":
            error("pilot_spoilage_label", "Pilot must remain spoilage-unlabeled", row["pilot_id"])
        if row["annotation_status"] != "pending":
            warning("pilot_status_changed", "Pilot manifest status is not pending; ensure annotation ledger agrees", row["pilot_id"])
        source = dataset / row["original_relative_path"]
        try:
            with Image.open(source) as image:
                if image.size != (int(row["width"]), int(row["height"])):
                    error("pilot_dimension_mismatch", "Decoded dimensions differ from pilot manifest", row["pilot_id"])
                image.verify()
        except Exception as exc:
            error("pilot_image_invalid", repr(exc), row["pilot_id"])
    checks["pilot_unique_content"] = len({row["content_id"] for row in pilot})

    hash_targets = []
    if args.hash_mode == "pilot":
        hash_targets = pilot
    elif args.hash_mode == "all":
        hash_targets = master
    for row in hash_targets:
        path_key = "original_relative_path"
        source = dataset / row[path_key]
        if source.is_file():
            digest = sha256_file(source)
            if digest != row["sha256"]:
                error("hash_mismatch", "Recomputed SHA-256 differs from manifest", row[path_key])
    checks["hashes_recomputed"] = len(hash_targets)

    if len(annotation_records) != len(pilot):
        error("annotation_ledger_count", "Annotation ledger must have one row per pilot image")
    if {row["pilot_id"] for row in annotation_records} != set(pilot_by_id):
        error("annotation_ledger_ids", "Annotation ledger IDs do not match pilot IDs")

    coco_images = coco.get("images", [])
    coco_annotations = coco.get("annotations", [])
    coco_categories = {category.get("id") for category in coco.get("categories", [])}
    if coco_categories != {1, 2}:
        error("coco_categories", "COCO categories must be IDs 1 and 2")
    if len(coco_images) != len(pilot):
        error("coco_image_count", "COCO image count differs from pilot")
    coco_by_pilot = {image.get("ftr6plus_pilot_id"): image for image in coco_images}
    coco_image_ids = {image.get("id") for image in coco_images}
    if len(coco_image_ids) != len(coco_images):
        error("coco_image_id_duplicate", "COCO image IDs are not unique")
    for pilot_id, row in pilot_by_id.items():
        image = coco_by_pilot.get(pilot_id)
        if not image:
            error("coco_missing_image", "Pilot image missing from COCO", pilot_id)
            continue
        if (int(image.get("width", -1)), int(image.get("height", -1))) != (int(row["width"]), int(row["height"])):
            error("coco_dimension_mismatch", "COCO dimensions differ from pilot", pilot_id)

    annotations_by_image = Counter()
    annotation_ids = set()
    for annotation in coco_annotations:
        annotation_id = annotation.get("id")
        if annotation_id in annotation_ids:
            error("coco_annotation_id_duplicate", "Duplicate COCO annotation ID", str(annotation_id))
        annotation_ids.add(annotation_id)
        image_id = annotation.get("image_id")
        annotations_by_image[image_id] += 1
        if image_id not in coco_image_ids:
            error("coco_unknown_image", "Annotation references unknown image", str(annotation_id))
        if annotation.get("category_id") not in {1, 2}:
            error("coco_unknown_category", "Annotation category must be 1 or 2", str(annotation_id))
        image = next((item for item in coco_images if item.get("id") == image_id), None)
        if not image:
            continue
        width, height = image["width"], image["height"]
        bbox = annotation.get("bbox")
        if not isinstance(bbox, list) or len(bbox) != 4:
            error("coco_bbox", "Annotation bbox must contain x,y,width,height", str(annotation_id))
        else:
            x, y, box_width, box_height = bbox
            if box_width <= 0 or box_height <= 0 or x < 0 or y < 0 or x + box_width > width + 1 or y + box_height > height + 1:
                error("coco_bbox_bounds", "Annotation bbox lies outside image", str(annotation_id))
        segmentation = annotation.get("segmentation")
        if isinstance(segmentation, list):
            for polygon in segmentation:
                if len(polygon) < 6 or len(polygon) % 2:
                    error("coco_polygon", "Polygon must contain at least three coordinate pairs", str(annotation_id))
                    continue
                xs, ys = polygon[0::2], polygon[1::2]
                if min(xs) < 0 or max(xs) > width or min(ys) < 0 or max(ys) > height:
                    error("coco_polygon_bounds", "Polygon lies outside image", str(annotation_id))
        elif isinstance(segmentation, dict):
            if segmentation.get("size") != [height, width]:
                error("coco_rle_size", "RLE dimensions differ from image", str(annotation_id))
        else:
            error("coco_segmentation", "Segmentation must be polygon list or RLE object", str(annotation_id))
        area = annotation.get("area")
        if not isinstance(area, (int, float)) or not math.isfinite(area) or area <= 0:
            error("coco_area", "Annotation area must be positive and finite", str(annotation_id))

    status_counts = Counter()
    missing_annotations = 0
    proposal_only = 0
    human_complete = 0
    for row in annotation_records:
        pilot_id = row["pilot_id"]
        status = row["annotation_status"]
        status_counts[status] += 1
        if status not in ALLOWED_STATUSES:
            error("annotation_status", "Unsupported annotation status", pilot_id)
            continue
        proposal_status = (row.get("proposal_status") or "").strip()
        if proposal_status not in ALLOWED_PROPOSAL_STATUSES:
            error("proposal_status", "Unsupported proposal status", pilot_id)
        ls_status = (row.get("label_studio_status") or "").strip()
        if ls_status not in ALLOWED_LS_STATUSES:
            error("label_studio_status", "Unsupported Label Studio status", pilot_id)
        human_file = (row.get("human_annotation_file") or row.get("annotation_file") or "").strip()
        if status in HUMAN_COMPLETE_STATUSES:
            human_complete += 1
            if not human_file or human_file == PROPOSAL_COCO:
                error(
                    "completed_without_human_annotation",
                    "Completed status must point to a human export, not %s" % PROPOSAL_COCO,
                    pilot_id,
                )
        if status in INCOMPLETE_HUMAN_STATUSES:
            missing_annotations += 1
            if human_file == PROPOSAL_COCO:
                error(
                    "proposal_used_as_human_annotation",
                    "Proposal COCO must not be recorded as the human annotation file",
                    pilot_id,
                )
        if status == "excluded" and not row["exclusion_reason"].strip():
            error("excluded_without_reason", "Excluded image requires a reason", pilot_id)
        if proposal_status == "proposal_only":
            proposal_only += 1
            proposal_raster = (row.get("proposal_raster_path") or "").strip()
            if proposal_raster:
                mask_path = workspace / proposal_raster
                if not mask_path.is_file():
                    error("proposal_mask_missing", "Proposal raster path does not exist", pilot_id)
                else:
                    with Image.open(mask_path) as mask:
                        pilot_row = pilot_by_id[pilot_id]
                        if mask.size != (int(pilot_row["width"]), int(pilot_row["height"])):
                            error("proposal_mask_dimension_mismatch", "Proposal raster dimensions differ from image", pilot_id)
                        values = set(mask.convert("L").getdata())
                        if not values.issubset(ALLOWED_MASK_VALUES):
                            error("proposal_mask_values", "Proposal raster contains unsupported values: %s" % sorted(values), pilot_id)
        human_raster = (row.get("raster_mask_path") or "").strip()
        if status in HUMAN_COMPLETE_STATUSES and human_raster:
            mask_path = workspace / human_raster
            if not mask_path.is_file():
                error("mask_missing", "Human raster mask path does not exist", pilot_id)
            else:
                with Image.open(mask_path) as mask:
                    pilot_row = pilot_by_id[pilot_id]
                    if mask.size != (int(pilot_row["width"]), int(pilot_row["height"])):
                        error("mask_dimension_mismatch", "Raster mask dimensions differ from image", pilot_id)
                    values = set(mask.convert("L").getdata())
                    if not values.issubset(ALLOWED_MASK_VALUES):
                        error("mask_values", "Raster mask contains unsupported values: %s" % sorted(values), pilot_id)
    checks["missing_pending_annotations"] = missing_annotations
    checks["proposal_only_records"] = proposal_only
    checks["human_complete_records"] = human_complete
    checks["proposal_coco_annotations"] = len(coco_annotations)
    human_coco_path = workspace / HUMAN_COCO
    human_coco_count = 0
    if human_coco_path.is_file():
        human_coco = json.loads(human_coco_path.read_text(encoding="utf-8"))
        human_coco_count = len(human_coco.get("annotations", []))
        if human_coco.get("info", {}).get("origin") != "label_studio_human":
            warning(
                "human_coco_origin",
                "Human COCO export should set info.origin=label_studio_human",
                HUMAN_COCO,
            )
    checks["human_coco_annotations"] = human_coco_count
    if coco_annotations and human_coco_count == 0:
        warning(
            "proposal_coco_not_ground_truth",
            "%d polygons in %s are Python proposals only and must not be exported as completed ground truth"
            % (len(coco_annotations), PROPOSAL_COCO),
            PROPOSAL_COCO,
        )
    if missing_annotations:
        warning(
            "annotations_pending",
            "%d pilot images still need human Label Studio annotation" % missing_annotations,
            "annotations/annotation_records.csv",
        )

    validation = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": str(dataset),
        "workspace": str(workspace),
        "hash_mode": args.hash_mode,
        "result": "pass" if not errors else "fail",
        "checks": dict(checks),
        "annotation_status_counts": dict(status_counts),
        "errors": errors,
        "warnings": warnings,
    }
    reports = workspace / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "validation_report.json").write_text(json.dumps(validation, indent=2), encoding="utf-8")
    markdown = [
        "# Foresight-TR6+ Validation Report",
        "",
        "Result: **%s**" % validation["result"].upper(),
        "",
        "- Master records: %d" % checks["master_records"],
        "- Source paths found: %d" % checks["source_paths_found"],
        "- Pilot records: %d" % checks["pilot_records"],
        "- Calibration records: %d" % checks["calibration_records"],
        "- Unique pilot content IDs: %d" % checks["pilot_unique_content"],
        "- Source hashes recomputed: %d" % checks["hashes_recomputed"],
        "- Proposal-only COCO polygons: %d" % checks["proposal_coco_annotations"],
        "- Human Label Studio COCO polygons: %d" % checks["human_coco_annotations"],
        "- Proposal-only ledger rows: %d" % checks["proposal_only_records"],
        "- Human-complete ledger rows: %d" % checks["human_complete_records"],
        "- Pending human annotations: %d" % checks["missing_pending_annotations"],
        "- Errors: %d" % len(errors),
        "- Warnings: %d" % len(warnings),
        "",
        "Python proposals in annotations/coco_annotations.json are not ground truth.",
        "Human exports must be written to annotations/human_coco_annotations.json.",
    ]
    (reports / "validation_report.md").write_text("\n".join(markdown) + "\n", encoding="utf-8")

    checksum_path = workspace / "checksums" / "extension_files_sha256.txt"
    skip_parts = {
        ".label-studio-venv",
        ".labelstudio-data",
        "__pycache__",
        ".git",
        "releases",
    }
    checksum_lines = []
    for path in sorted(path for path in workspace.rglob("*") if path.is_file()):
        if path == checksum_path or any(part in skip_parts for part in path.parts):
            continue
        checksum_lines.append("%s  %s" % (sha256_file(path), path.relative_to(workspace)))
    checksum_path.parent.mkdir(parents=True, exist_ok=True)
    checksum_path.write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")

    print(json.dumps(validation, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
