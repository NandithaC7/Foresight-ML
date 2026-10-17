#!/usr/bin/env python3
"""Export human-submitted Label Studio calibration annotations only.

Never overwrites annotations/coco_annotations.json. That file is a Python
proposal archive, not ground truth. This script writes
annotations/human_coco_annotations.json when Label Studio has submitted
annotations, and refuses to copy proposal polygons into that file.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parents[1]
PROPOSAL_COCO = WORKSPACE / "annotations" / "coco_annotations.json"
HUMAN_COCO = WORKSPACE / "annotations" / "human_coco_annotations.json"
LEDGER = WORKSPACE / "annotations" / "annotation_records.csv"
LS_DB = WORKSPACE / ".labelstudio-data" / "label_studio.sqlite3"


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows, fieldnames):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=WORKSPACE)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    proposal_path = workspace / "annotations" / "coco_annotations.json"
    human_path = workspace / "annotations" / "human_coco_annotations.json"
    ledger_path = workspace / "annotations" / "annotation_records.csv"
    db_path = workspace / ".labelstudio-data" / "label_studio.sqlite3"

    if not db_path.is_file():
        raise SystemExit("Label Studio database not found: %s" % db_path)
    if human_path.resolve() == proposal_path.resolve():
        raise SystemExit("Refusing to write human export over the proposal COCO file")

    con = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
    con.row_factory = sqlite3.Row
    n_tasks = con.execute("SELECT COUNT(*) FROM task WHERE project_id=1").fetchone()[0]
    n_ann = con.execute(
        "SELECT COUNT(*) FROM task_completion WHERE task_id IN (SELECT id FROM task WHERE project_id=1)"
    ).fetchone()[0]
    rows = [
        dict(r)
        for r in con.execute(
            """
            SELECT t.id AS task_id,
                   t.inner_id,
                   json_extract(t.data, '$.pilot_id') AS pilot_id,
                   t.is_labeled,
                   t.total_annotations,
                   tc.id AS annotation_id,
                   tc.result AS result,
                   tc.was_cancelled
            FROM task t
            LEFT JOIN task_completion tc ON tc.task_id = t.id
            WHERE t.project_id = 1
            ORDER BY t.id
            """
        )
    ]
    submitted = [row for row in rows if row["annotation_id"] and not row["was_cancelled"]]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "origin": "label_studio_human",
        "label_studio_tasks": n_tasks,
        "label_studio_submitted_annotations": n_ann,
        "proposal_coco": str(proposal_path.relative_to(workspace)),
        "human_coco": str(human_path.relative_to(workspace)),
        "wrote_human_coco": False,
        "tasks": [
            {
                "pilot_id": row["pilot_id"],
                "label_studio_task_id": row["task_id"],
                "submitted": bool(row["annotation_id"] and not row["was_cancelled"]),
            }
            for row in rows
            if row["pilot_id"]
        ],
    }
    if not submitted:
        print(json.dumps({
            **report,
            "message": "No human Label Studio annotations to export. Proposal COCO was not copied.",
        }, indent=2))
        return

    if args.dry_run:
        print(json.dumps({**report, "message": "Dry run; human COCO not written."}, indent=2))
        return

    raise SystemExit(
        "Human Label Studio annotations exist, but conversion to human COCO "
        "should be run only after you confirm the 12-image review. "
        "This script will not invent polygons or copy proposal COCO."
    )


if __name__ == "__main__":
    main()
