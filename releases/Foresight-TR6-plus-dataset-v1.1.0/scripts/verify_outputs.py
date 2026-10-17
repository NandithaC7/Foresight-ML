#!/usr/bin/env python3
"""Consistency checks for TR-6 audit outputs; does not modify the dataset."""

import argparse
import csv
import json
from pathlib import Path


def count_rows(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    dataset = args.dataset.resolve()
    output = args.output.resolve()

    assert dataset.is_dir()
    assert output.is_dir()
    assert dataset != output and dataset not in output.parents

    summary = json.loads((output / "audit_summary.json").read_text(encoding="utf-8"))
    assert summary["dataset_path"] == str(dataset)
    assert summary["file_count"] == count_rows(output / "file_inventory.csv")
    assert summary["methane_file_count"] == count_rows(output / "methane_files.csv")
    assert summary["valid_images"] + summary["corrupt_or_invalid_images"] == sum(summary["image_counts"].values())
    assert count_rows(output / "representative_image_samples.csv") == 36
    assert len(list(output.glob("contact-sheet-*.jpg"))) == 3
    assert (output / "audit_report.md").stat().st_size > 0
    assert (output / "errors.csv").exists()

    actual_dataset_files = sum(1 for path in dataset.rglob("*") if path.is_file())
    assert actual_dataset_files == summary["file_count"]
    assert not list(dataset.rglob("audit_*.json"))
    assert not list(dataset.rglob("audit_report.md"))
    print("verification_ok")
    print("dataset_files=%d" % actual_dataset_files)
    print("output_files=%d" % sum(1 for path in output.rglob("*") if path.is_file()))


if __name__ == "__main__":
    main()
