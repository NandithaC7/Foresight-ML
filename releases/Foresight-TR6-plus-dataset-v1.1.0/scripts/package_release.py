#!/usr/bin/env python3
"""Assemble Foresight-TR6+ publication package v1.0.0.

Does not copy original TR-6 images, methane text, pixel derivatives, secrets,
or absolute local paths. Does not upload anything.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


VERSION = "1.0.0"
PACKAGE_NAME = f"Foresight-TR6-plus-dataset-v{VERSION}"
ABS_ROOT = "<foresight-workspace>"
ABS_WORKSPACE = f"{ABS_ROOT}/Foresight-TR6-plus"
ABS_DATASET = f"{ABS_ROOT}/TR-6"
ABS_AUDIT = f"{ABS_ROOT}/dataset-preparation/tr6-audit/output"
FORBIDDEN_SUFFIXES = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".tif",
    ".tiff",
    ".bmp",
    ".env",
    ".sqlite",
    ".sqlite3",
    ".pth",
    ".pt",
    ".ckpt",
    ".bin",
    ".npy",
    ".npz",
}
FORBIDDEN_NAME_PARTS = (
    ".label-studio-venv",
    ".labelstudio-data",
    "node_modules",
    "__pycache__",
    ".DS_Store",
)
SECRET_PATTERNS = (
    re.compile(r"SECRET_KEY\s*="),
    re.compile(r"foresight-" + r"calibration-local"),
    re.compile(r"chnandu" + r"joshi"),
)
ABS_PATH_RE = re.compile(r"/(?:Users|home)/[A-Za-z0-9._-]+/")
SCRIPT_WORKSPACE_RE = re.compile(
    r'Path\("<Foresight-TR6-plus-workspace>"\)'
)
SCRIPT_DATASET_RE = re.compile(r'Path\("<TR-6-root>"\)')


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def sanitize_text(text: str) -> str:
    text = text.replace(ABS_AUDIT, "<tr6-audit-output>")
    text = text.replace(ABS_WORKSPACE, "<Foresight-TR6-plus-workspace>")
    text = text.replace(ABS_DATASET, "<TR-6-root>")
    text = text.replace(ABS_ROOT, "<foresight-workspace>")
    text = text.replace("<local-user-home>", "<local-user-home>")
    return text


def sanitize_python_script(text: str) -> str:
    text = SCRIPT_WORKSPACE_RE.sub('Path(__file__).resolve().parents[1]', text)
    text = SCRIPT_DATASET_RE.sub(
        'Path(__file__).resolve().parents[2] / "TR-6"', text
    )
    return sanitize_text(text)


def copy_sanitized_text(src: Path, dest: Path, python: bool = False):
    text = src.read_text(encoding="utf-8")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if python:
        dest.write_text(sanitize_python_script(text), encoding="utf-8")
        dest.chmod(dest.stat().st_mode | stat.S_IEXEC)
    else:
        dest.write_text(sanitize_text(text), encoding="utf-8")


def copy_json_sanitized(src: Path, dest: Path):
    payload = json.loads(src.read_text(encoding="utf-8"))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        sanitize_text(json.dumps(payload, indent=2)) + "\n", encoding="utf-8"
    )


def is_true(value: str) -> bool:
    return str(value).strip().lower() == "true"


def build_duplicate_groups(master_rows):
    groups = defaultdict(list)
    for row in master_rows:
        group_id = row["duplicate_group_id"]
        if group_id and group_id != "none":
            groups[group_id].append(row)
    out = []
    for group_id, members in sorted(groups.items()):
        first = members[0]
        labels = sorted(
            {
                m["spoilage_label"]
                for m in members
                if m["spoilage_label"] and m["spoilage_label"] != "unknown"
            }
        )
        produce = sorted({m["produce_type"] for m in members})
        sources = sorted({m["source_directory"] for m in members})
        canonical = next(
            (m["original_relative_path"] for m in members if is_true(m["canonical_content_reference"])),
            members[0]["original_relative_path"],
        )
        out.append(
            {
                "duplicate_group_id": group_id,
                "content_id": first["content_id"],
                "sha256": first["sha256"],
                "size_bytes": first["size_bytes"],
                "member_count": len(members),
                "cross_source_duplicate": first["cross_source_duplicate"],
                "cross_label_conflict": first["cross_label_conflict"],
                "produce_types": ";".join(produce),
                "observed_labels": ";".join(labels),
                "source_directories": ";".join(sources),
                "canonical_path": canonical,
                "member_paths": ";".join(m["original_relative_path"] for m in members),
            }
        )
    return out


def build_modality_inventory(master_rows):
    buckets = defaultdict(
        lambda: {
            "file_count": 0,
            "unique_content_ids": set(),
            "image_count": 0,
            "cross_label_conflict_files": 0,
            "size_bytes": 0,
        }
    )
    for row in master_rows:
        key = (
            row["source_directory"],
            row["produce_type"],
            row["spoilage_label"],
            row["apparent_modality"],
        )
        bucket = buckets[key]
        bucket["file_count"] += 1
        bucket["unique_content_ids"].add(row["content_id"])
        if row["image_format"] and row["image_format"] != "unknown":
            bucket["image_count"] += 1
        if is_true(row["cross_label_conflict"]):
            bucket["cross_label_conflict_files"] += 1
        bucket["size_bytes"] += int(row["size_bytes"] or 0)
    rows = []
    for key, bucket in sorted(buckets.items()):
        rows.append(
            {
                "source_directory": key[0],
                "produce_type": key[1],
                "spoilage_label": key[2],
                "apparent_modality": key[3],
                "file_count": bucket["file_count"],
                "unique_content_ids": len(bucket["unique_content_ids"]),
                "image_count": bucket["image_count"],
                "cross_label_conflict_files": bucket["cross_label_conflict_files"],
                "size_bytes": bucket["size_bytes"],
            }
        )
    return rows


def build_annotation_status(records, proposal_index):
    issues = {row["pilot_id"]: row.get("known_issue", "") for row in proposal_index}
    out = []
    for row in records:
        out.append(
            {
                "pilot_id": row["pilot_id"],
                "content_id": row["content_id"],
                "annotation_status": row["annotation_status"],
                "proposal_status": row.get("proposal_status", ""),
                "label_studio_status": row.get("label_studio_status", ""),
                "human_annotation_file": row.get("human_annotation_file", ""),
                "proposal_coco_path": row.get("proposal_coco_path", ""),
                "proposal_raster_path": row.get("proposal_raster_path", ""),
                "fruit_instance_count": row.get("fruit_instance_count", ""),
                "visible_defect_instance_count": row.get("visible_defect_instance_count", ""),
                "image_quality": row.get("image_quality", ""),
                "label_studio_project_id": row.get("label_studio_project_id", ""),
                "label_studio_task_id": row.get("label_studio_task_id", ""),
                "known_issue": issues.get(row["pilot_id"], ""),
                "notes": row.get("notes", ""),
            }
        )
    return out


def run_validate_extension(workspace: Path, dataset: Path) -> dict:
    script = workspace / "scripts" / "validate_extension.py"
    cmd = [
        sys.executable,
        str(script),
        "--dataset",
        str(dataset),
        "--workspace",
        str(workspace),
        "--hash-mode",
        "none",
    ]
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        cmd, cwd=str(workspace), env=env, capture_output=True, text=True
    )
    report_path = workspace / "reports" / "validation_report.json"
    report = {}
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
        "report": report,
    }


def scan_package(root: Path) -> dict:
    errors = []
    warnings = []
    files = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        suffix = path.suffix.lower()
        if suffix in FORBIDDEN_SUFFIXES:
            errors.append(f"forbidden binary suffix: {rel}")
        if any(part in rel for part in FORBIDDEN_NAME_PARTS):
            errors.append(f"forbidden path component: {rel}")
        if path.stat().st_size == 0:
            warnings.append(f"empty file: {rel}")
        text_ok = suffix in {
            ".md",
            ".txt",
            ".csv",
            ".json",
            ".py",
            ".xml",
            ".cff",
        } or path.name in {"VERSION", "LICENSE"}
        if text_ok:
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                errors.append(f"non-utf8 text file: {rel}")
                continue
            for match in ABS_PATH_RE.finditer(text):
                snippet = text[max(0, match.start() - 8) : match.start()]
                if "https://" in snippet or "http://" in snippet:
                    continue
                errors.append(f"absolute local path in {rel}: {match.group(0)}")
                break
            for pattern in SECRET_PATTERNS:
                if pattern.search(text):
                    errors.append(f"secret or private credential pattern in {rel}")
        files.append(
            {
                "path": rel,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return {"errors": errors, "warnings": warnings, "files": files}


def zip_directory(source: Path, zip_path: Path):
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(p for p in source.rglob("*") if p.is_file()):
            archive.write(path, arcname=f"{source.name}/{path.relative_to(source).as_posix()}")


def inspect_zip(zip_path: Path, package_name: str) -> dict:
    errors = []
    names = []
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            names.append(info.filename)
            if info.filename.startswith("/") or info.filename.startswith("\\"):
                errors.append(f"absolute zip member: {info.filename}")
            if ".." in Path(info.filename).parts:
                errors.append(f"parent-path zip member: {info.filename}")
            if not info.filename.startswith(package_name + "/") and info.filename != package_name:
                errors.append(f"member outside package prefix: {info.filename}")
            lower = info.filename.lower()
            if any(lower.endswith(suffix) for suffix in FORBIDDEN_SUFFIXES):
                errors.append(f"forbidden zip member: {info.filename}")
            if any(part in info.filename for part in FORBIDDEN_NAME_PARTS):
                errors.append(f"forbidden zip member: {info.filename}")
    return {"errors": errors, "member_count": len(names), "members": names}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--audit-output", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, default=None)
    parser.add_argument("--release-root", type=Path, default=None)
    parser.add_argument("--version", default=VERSION)
    parser.add_argument("--skip-source-validate", action="store_true")
    args = parser.parse_args()

    workspace = args.workspace.resolve()
    audit = args.audit_output.resolve()
    dataset = (args.dataset or workspace.parent / "TR-6").resolve()
    version = args.version
    package_name = f"Foresight-TR6-plus-dataset-v{version}"
    release_root = (args.release_root or workspace.parent / "releases").resolve()
    package_dir = release_root / package_name
    zip_path = release_root / f"{package_name}.zip"

    if package_dir.exists():
        shutil.rmtree(package_dir)
    package_dir.mkdir(parents=True)

    source_validation = {"skipped": True}
    if not args.skip_source_validate and dataset.is_dir():
        source_validation = run_validate_extension(workspace, dataset)
        source_validation["skipped"] = False

    pub = workspace / "publication"
    docs_src = workspace / "docs"
    (package_dir / "docs").mkdir(parents=True, exist_ok=True)

    # Root documentation
    shutil.copy2(pub / "README.md", package_dir / "README.md")
    shutil.copy2(pub / "DATA_DICTIONARY.md", package_dir / "DATA_DICTIONARY.md")
    shutil.copy2(pub / "LICENSE_AND_ATTRIBUTION.md", package_dir / "LICENSE_AND_ATTRIBUTION.md")
    shutil.copy2(pub / "CITATION.md", package_dir / "CITATION.md")
    shutil.copy2(pub / "NOT_INCLUDED.md", package_dir / "NOT_INCLUDED.md")
    shutil.copy2(pub / "IEEE_DATAPORT_SUBMISSION.md", package_dir / "IEEE_DATAPORT_SUBMISSION.md")
    shutil.copy2(pub / "REMAINING_SOURCE_QUESTIONS.md", package_dir / "docs" / "REMAINING_SOURCE_QUESTIONS.md")
    (package_dir / "VERSION").write_text(version + "\n", encoding="utf-8")

    # Protocol and design docs
    shutil.copy2(docs_src / "annotation_protocol.md", package_dir / "docs" / "annotation_protocol.md")
    shutil.copy2(docs_src / "dataset_extension_design.md", package_dir / "docs" / "dataset_extension_design.md")
    shutil.copy2(pub / "calibration_label_studio_guide.md", package_dir / "docs" / "calibration_label_studio_guide.md")
    shutil.copy2(pub / "manual_annotation_steps.md", package_dir / "docs" / "manual_annotation_steps.md")
    shutil.copy2(docs_src / "data_dictionary.md", package_dir / "docs" / "workspace_data_dictionary.md")

    # Manifests
    manifests = package_dir / "manifests"
    manifests.mkdir(parents=True)
    master_src = workspace / "manifests" / "master_manifest.csv"
    shutil.copy2(master_src, manifests / "master_manifest.csv")
    shutil.copy2(workspace / "manifests" / "pilot_manifest.csv", manifests / "pilot_manifest.csv")
    shutil.copy2(workspace / "manifests" / "calibration_batch.csv", manifests / "calibration_batch.csv")
    shutil.copy2(workspace / "manifests" / "exclusion_log.csv", manifests / "label_conflict_report.csv")
    shutil.copy2(audit / "file_inventory.csv", manifests / "file_inventory.csv")
    shutil.copy2(audit / "exact_duplicate_files.csv", manifests / "duplicate_group_members.csv")
    shutil.copy2(audit / "methane_files.csv", manifests / "methane_files.csv")
    shutil.copy2(audit / "methane_issues.csv", manifests / "methane_issues.csv")
    shutil.copy2(
        audit / "methane_normal_classified_correspondence.csv",
        manifests / "methane_normal_classified_correspondence.csv",
    )
    shutil.copy2(audit / "image_summary.csv", manifests / "image_summary.csv")
    shutil.copy2(
        audit / "classified_normal_exact_duplicates.csv",
        manifests / "classified_normal_exact_duplicates.csv",
    )
    shutil.copy2(
        audit / "image_correspondence_summary.csv",
        manifests / "image_correspondence_summary.csv",
    )
    shutil.copy2(audit / "inferred_image_sessions.csv", manifests / "inferred_image_sessions.csv")
    shutil.copy2(
        audit / "probable_session_correspondence.csv",
        manifests / "probable_session_correspondence.csv",
    )
    shutil.copy2(audit / "directory_summary.csv", manifests / "directory_summary.csv")
    shutil.copy2(audit / "extension_summary.csv", manifests / "extension_summary.csv")
    shutil.copy2(audit / "produce_modality_summary.csv", manifests / "produce_modality_summary.csv")
    shutil.copy2(audit / "errors.csv", manifests / "errors.csv")

    master_rows = read_csv(master_src)
    dup_rows = build_duplicate_groups(master_rows)
    write_csv(
        manifests / "duplicate_groups.csv",
        dup_rows,
        [
            "duplicate_group_id",
            "content_id",
            "sha256",
            "size_bytes",
            "member_count",
            "cross_source_duplicate",
            "cross_label_conflict",
            "produce_types",
            "observed_labels",
            "source_directories",
            "canonical_path",
            "member_paths",
        ],
    )
    write_csv(
        manifests / "modality_inventory.csv",
        build_modality_inventory(master_rows),
        [
            "source_directory",
            "produce_type",
            "spoilage_label",
            "apparent_modality",
            "file_count",
            "unique_content_ids",
            "image_count",
            "cross_label_conflict_files",
            "size_bytes",
        ],
    )

    annotation_records = read_csv(workspace / "annotations" / "annotation_records.csv")
    proposal_index = read_csv(workspace / "annotations" / "proposal_index.csv")
    write_csv(
        manifests / "annotation_status.csv",
        build_annotation_status(annotation_records, proposal_index),
        [
            "pilot_id",
            "content_id",
            "annotation_status",
            "proposal_status",
            "label_studio_status",
            "human_annotation_file",
            "proposal_coco_path",
            "proposal_raster_path",
            "fruit_instance_count",
            "visible_defect_instance_count",
            "image_quality",
            "label_studio_project_id",
            "label_studio_task_id",
            "known_issue",
            "notes",
        ],
    )

    # Annotations: protocol records only; no PNG masks
    ann = package_dir / "annotations"
    ann.mkdir()
    shutil.copy2(workspace / "annotations" / "annotation_records.csv", ann / "annotation_records.csv")
    shutil.copy2(workspace / "annotations" / "proposal_index.csv", ann / "proposal_index.csv")
    shutil.copy2(workspace / "annotations" / "coco_annotations.json", ann / "coco_annotations.json")
    shutil.copy2(workspace / "annotations" / "PROPOSAL_ONLY.md", ann / "PROPOSAL_ONLY.md")
    (ann / "MASKS_EXCLUDED.md").write_text(
        "Raster proposal masks (annotations/masks/tr6p_*.png) are pixel "
        "derivatives of TR-6 and are excluded from this package.\n",
        encoding="utf-8",
    )

    # Imports
    imports = package_dir / "imports"
    imports.mkdir()
    for name in (
        "label_studio_config.xml",
        "calibration_label_studio_tasks.json",
        "label_studio_tasks.json",
        "pilot_coco_template.json",
    ):
        copy_sanitized_text(workspace / "imports" / name, imports / name)

    # Config
    cfg = package_dir / "config"
    cfg.mkdir()
    copy_json_sanitized(workspace / "config" / "build_config.json", cfg / "build_config.json")

    # Scripts
    scripts = package_dir / "scripts"
    scripts.mkdir()
    for name in (
        "build_extension.py",
        "validate_extension.py",
        "annotate_calibration.py",
        "export_label_studio_calibration.py",
        "prepare_calibration_review.py",
        "package_release.py",
    ):
        copy_sanitized_text(workspace / "scripts" / name, scripts / name, python=True)
    copy_sanitized_text(
        workspace.parent / "dataset-preparation" / "tr6-audit" / "audit_tr6.py",
        scripts / "audit_tr6.py",
        python=True,
    )
    copy_sanitized_text(
        workspace.parent / "dataset-preparation" / "tr6-audit" / "verify_outputs.py",
        scripts / "verify_outputs.py",
        python=True,
    )

    # Future noise pipeline (code only)
    future = package_dir / "future" / "noise-augmentation"
    future.mkdir(parents=True)
    shutil.copy2(pub / "future_noise_README.md", future / "README.md")
    copy_sanitized_text(
        workspace / "scripts" / "generate_noise_dataset.py",
        future / "generate_noise_dataset.py",
        python=True,
    )
    copy_json_sanitized(
        workspace / "config" / "noise_generation.json",
        future / "noise_generation.json",
    )

    # Reports
    reports = package_dir / "reports"
    reports.mkdir()
    copy_json_sanitized(
        workspace / "reports" / "validation_report.json", reports / "validation_report.json"
    )
    copy_sanitized_text(
        workspace / "reports" / "validation_report.md", reports / "validation_report.md"
    )
    copy_json_sanitized(
        workspace / "reports" / "build_summary.json", reports / "build_summary.json"
    )
    copy_sanitized_text(
        workspace / "reports" / "calibration_task_status.md",
        reports / "calibration_task_status.md",
    )
    copy_json_sanitized(
        workspace / "reports" / "calibration_annotation_summary.json",
        reports / "calibration_annotation_summary.json",
    )

    audit_summary = json.loads((audit / "audit_summary.json").read_text(encoding="utf-8"))
    audit_summary["dataset_path"] = "<TR-6-root>"
    audit_summary["contact_sheets"] = [
        "EXCLUDED_FROM_PACKAGE/" + Path(item).name
        for item in audit_summary.get("contact_sheets", [])
    ]
    write_json(reports / "audit_summary.json", json.loads(sanitize_text(json.dumps(audit_summary))))
    copy_sanitized_text(audit / "audit_report.md", reports / "audit_report.md")

    licence_evidence = {
        "retrieved_at": "2026-10-15",
        "method": "GET https://api.figshare.com/v2/articles/30783827",
        "article_id": 30783827,
        "title": "TriModal Ripeness 6",
        "doi": "10.6084/m9.figshare.30783827.v1",
        "license": {
            "value": 1,
            "name": "CC BY 4.0",
            "url": "https://creativecommons.org/licenses/by/4.0/",
        },
        "authors": [
            "Bagyammal T",
            "Yogini Aishwaryaa P T S",
            "Krishna Deepak",
            "Devika Unnikrishnan",
        ],
        "figshare_file": {
            "name": "TR-6.zip",
            "id": 60094544,
            "size": 20388430589,
            "computed_md5": "cdbcc4a667051aa35d46c2de71a723d9",
        },
        "local_readme_licence_statement": "none",
        "v1_policy": "Original images and pixel derivatives are not included in this package.",
    }
    write_json(reports / "licence_evidence.json", licence_evidence)

    status_counts = Counter(row["annotation_status"] for row in annotation_records)
    proposal_counts = Counter(row.get("proposal_status") or "none" for row in annotation_records)
    ls_counts = Counter(row.get("label_studio_status") or "" for row in annotation_records)

    file_count_summary = {
        "package": package_name,
        "generated_at": utc_now(),
        "source_tr6_files_audited": len(master_rows),
        "source_images_audited": sum(
            1 for row in master_rows if row["image_format"] not in ("", "unknown")
        ),
        "unique_image_hashes": len(
            {
                row["sha256"]
                for row in master_rows
                if row["image_format"] not in ("", "unknown")
            }
        ),
        "duplicate_groups": len(dup_rows),
        "label_conflict_groups": sum(1 for row in dup_rows if is_true(row["cross_label_conflict"])),
        "pilot_images": 96,
        "calibration_images": 12,
        "annotation_status_counts": dict(status_counts),
        "proposal_status_counts": dict(proposal_counts),
        "label_studio_status_counts": dict(ls_counts),
        "human_complete_annotations": sum(
            1 for row in annotation_records if row["annotation_status"] in {"annotated", "reviewed"}
        ),
        "source_images_included_in_package": 0,
        "pixel_derivatives_included_in_package": 0,
        "noise_images_included_in_package": 0,
    }
    write_json(reports / "file_count_summary.json", file_count_summary)
    write_json(
        reports / "release_output.json",
        {
            "package": package_name,
            "zip_filename": f"{package_name}.zip",
            "checksum_filename": f"{package_name}.zip.sha256",
            "source_images_included": 0,
            "human_complete_annotations": file_count_summary["human_complete_annotations"],
            "result": "pending",
            "ieee_dataport_uploaded": False,
            "doi_assigned": False,
            "note": "The ZIP SHA-256 is recorded in the sibling .sha256 file so that the checksum covers the archive.",
        },
    )

    package_validation = {
        "generated_at": utc_now(),
        "package": package_name,
        "result": "pending",
        "source_validate_extension": {
            "skipped": source_validation.get("skipped"),
            "returncode": source_validation.get("returncode"),
            "report_result": source_validation.get("report", {}).get("result"),
            "human_complete_records": source_validation.get("report", {})
            .get("checks", {})
            .get("human_complete_records"),
            "proposal_only_records": source_validation.get("report", {})
            .get("checks", {})
            .get("proposal_only_records"),
        },
        "errors": [],
        "warnings": [],
        "forbidden_binaries": 0,
        "absolute_local_paths": 0,
        "ieee_dataport_uploaded": False,
        "doi_assigned": False,
    }
    write_json(reports / "package_validation.json", package_validation)

    scan = scan_package(package_dir)
    inventory_path = manifests / "package_file_inventory.csv"
    write_csv(inventory_path, scan["files"], ["path", "size_bytes", "sha256"])
    scan = scan_package(package_dir)
    write_csv(inventory_path, scan["files"], ["path", "size_bytes", "sha256"])
    scan = scan_package(package_dir)

    source_ok = source_validation.get("skipped") or source_validation.get("returncode") == 0
    package_ok = not scan["errors"] and source_ok
    package_validation.update(
        {
            "result": "pass" if package_ok else "fail",
            "package_file_count": len(scan["files"]),
            "package_bytes": sum(item["size_bytes"] for item in scan["files"]),
            "errors": scan["errors"],
            "warnings": scan["warnings"],
            "forbidden_binaries": sum(1 for err in scan["errors"] if "forbidden" in err),
            "absolute_local_paths": sum(1 for err in scan["errors"] if "absolute local path" in err),
        }
    )
    write_json(reports / "package_validation.json", package_validation)

    if not package_ok:
        print(json.dumps(package_validation, indent=2))
        raise SystemExit("package validation failed; ZIP not written")

    write_json(
        reports / "release_output.json",
        {
            "package": package_name,
            "zip_filename": f"{package_name}.zip",
            "checksum_filename": f"{package_name}.zip.sha256",
            "package_file_count": len(scan["files"]),
            "package_bytes": sum(item["size_bytes"] for item in scan["files"]),
            "source_images_included": 0,
            "human_complete_annotations": file_count_summary["human_complete_annotations"],
            "result": "pass",
            "ieee_dataport_uploaded": False,
            "doi_assigned": False,
            "note": "The ZIP SHA-256 is recorded in the sibling .sha256 file so that the checksum covers the archive.",
        },
    )

    zip_directory(package_dir, zip_path)
    zip_info = inspect_zip(zip_path, package_name)
    if zip_info["errors"]:
        raise SystemExit("zip inspection failed: " + "; ".join(zip_info["errors"]))

    zip_sha = sha256_file(zip_path)
    checksum_path = release_root / f"{package_name}.zip.sha256"
    checksum_path.write_text(f"{zip_sha}  {zip_path.name}\n", encoding="utf-8")

    local_sidecar = {
        "package": package_name,
        "unpacked_dir": str(package_dir),
        "zip_path": str(zip_path),
        "checksum_path": str(checksum_path),
        "zip_filename": zip_path.name,
        "checksum_filename": checksum_path.name,
        "zip_bytes": zip_path.stat().st_size,
        "zip_sha256": zip_sha,
        "package_file_count": len(scan["files"]),
        "package_bytes": sum(item["size_bytes"] for item in scan["files"]),
        "zip_member_count": zip_info["member_count"],
        "source_images_included": 0,
        "human_complete_annotations": file_count_summary["human_complete_annotations"],
        "result": "pass",
        "ieee_dataport_uploaded": False,
        "doi_assigned": False,
    }
    write_json(release_root / f"{package_name}.release.json", local_sidecar)
    print(json.dumps(local_sidecar, indent=2))


if __name__ == "__main__":
    main()
