#!/usr/bin/env python3
"""Create local review aids for the 12-image calibration batch.

This script creates thumbnails and non-binding review guidance only. It does
not create masks, change annotation status, or mark any record as reviewed.
"""

import argparse
import csv
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps


GUIDANCE = {
    "tr6p_001": (
        "annotatable_candidate",
        "Fruit outline and attached stem are clear; exclude cast shadow.",
        "Several dark surface patches are possible defect candidates, but require human confirmation at native resolution.",
    ),
    "tr6p_009": (
        "ambiguous_candidate",
        "Banana silhouette is visible but boundary is thermally diffuse, especially near the shadow/stem.",
        "Do not create a defect mask from thermal color variation alone.",
    ),
    "tr6p_017": (
        "annotatable_candidate",
        "Carrot outline is clear; exclude the surrounding shadow.",
        "Small marks are not confidently distinguishable from normal surface texture.",
    ),
    "tr6p_025": (
        "annotatable_candidate",
        "Thermal carrot silhouette has strong contrast and a repeatable boundary.",
        "No defensible visible-defect region identified from this rendering.",
    ),
    "tr6p_033": (
        "annotatable_candidate",
        "Guava outline and attached calyx are clear; exclude shadow.",
        "Mottling may be normal texture; no defect should be drawn without human confirmation.",
    ),
    "tr6p_041": (
        "ambiguous_candidate",
        "Guava silhouette is visible but edge contrast is diffuse in places.",
        "Central thermal variation is not a visible physical defect.",
    ),
    "tr6p_049": (
        "annotatable_candidate",
        "Indian Gooseberry outline and small attached stem are clear.",
        "A small dark surface spot is visible but its defect status requires human confirmation.",
    ),
    "tr6p_057": (
        "ambiguous_candidate",
        "Indian Gooseberry has low thermal contrast and an uncertain lower/right boundary.",
        "No visible-defect mask recommended from this rendering.",
    ),
    "tr6p_065": (
        "annotatable_candidate",
        "Mango outline and attached stem are clear; exclude shadow.",
        "Several marks are visible; classify as defects only if boundaries and abnormality are defensible at native resolution.",
    ),
    "tr6p_073": (
        "annotatable_candidate",
        "Mango thermal silhouette is sufficiently distinct for a fruit mask.",
        "Thermal color variation alone is not a defect.",
    ),
    "tr6p_081": (
        "annotatable_candidate",
        "Tomato outline is clear; include fruit surface but exclude cast shadow.",
        "The central stem scar/calyx area is normal anatomy, not automatically a defect.",
    ),
    "tr6p_089": (
        "ambiguous_candidate",
        "Tomato silhouette is visible but some thermal boundary regions are soft.",
        "No defensible visible-defect region identified from this rendering.",
    ),
}


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    dataset = args.dataset.resolve()
    workspace = args.workspace.resolve()
    rows = read_csv(workspace / "manifests" / "calibration_batch.csv")

    cell_width, cell_height = 300, 250
    columns = 4
    sheet_rows = math.ceil(len(rows) / columns)
    canvas = Image.new("RGB", (columns * cell_width, 48 + sheet_rows * cell_height), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text((12, 14), "Foresight-TR6+ calibration batch (review aid only; no masks)", fill="black")
    review_rows = []
    for index, row in enumerate(rows):
        x = (index % columns) * cell_width
        y = 48 + (index // columns) * cell_height
        source = dataset / row["original_relative_path"]
        with Image.open(source) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            image.thumbnail((cell_width - 16, 185))
            canvas.paste(image, (x + 8, y + 8))
        draw.text((x + 8, y + 199), "%s | %s" % (row["pilot_id"], row["produce_type"]), fill="black")
        draw.text((x + 8, y + 215), row["apparent_modality"], fill="black")
        draw.text((x + 8, y + 231), Path(row["original_relative_path"]).name[:40], fill="black")
        suggested, boundary_note, defect_note = GUIDANCE[row["pilot_id"]]
        review_rows.append({
            "pilot_id": row["pilot_id"],
            "produce_type": row["produce_type"],
            "apparent_modality": row["apparent_modality"],
            "suggested_disposition_for_human_review": suggested,
            "boundary_guidance": boundary_note,
            "defect_guidance": defect_note,
            "human_confirmation_required": "true",
            "mask_created": "false",
            "annotation_status_changed": "false",
        })

    report_dir = workspace / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    canvas.save(report_dir / "calibration_review_sheet.jpg", format="JPEG", quality=86)
    with (report_dir / "calibration_pre_review.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(review_rows[0].keys()))
        writer.writeheader()
        writer.writerows(review_rows)
    print("prepared_review_images=%d" % len(rows))
    print("masks_created=0")
    print("annotation_statuses_changed=0")


if __name__ == "__main__":
    main()
