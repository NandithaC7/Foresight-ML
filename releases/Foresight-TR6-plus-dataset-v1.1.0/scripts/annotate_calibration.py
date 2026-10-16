#!/usr/bin/env python3
"""Computer-assisted fruit outlines for the 12-image calibration batch.

Masks are derived from the stored JPEG pixels and visually reviewed as overlays.
They are not independently verified ground truth and must not be marked reviewed
until a human inspects them. Defect polygons are not auto-generated.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps


WORKSPACE = Path(__file__).resolve().parents[1]
DATASET = Path(__file__).resolve().parents[2] / "TR-6"
OVERLAY_DIR = WORKSPACE / "reports" / "calibration-overlays"
MASK_DIR = WORKSPACE / "annotations" / "masks"
PREVIEW_DIR = WORKSPACE / "reports" / "calibration-previews"

CALIBRATION = [
    {"pilot_id": "tr6p_001", "coco_id": 1, "produce": "Banana", "modality": "srgb",
     "rel": "Normal/Banana/sRGB_images/20250911_101508.jpg"},
    {"pilot_id": "tr6p_009", "coco_id": 9, "produce": "Banana", "modality": "thermal_ir_fusion",
     "rel": "Normal/Banana/IR_fusion_images/20250915_093303_29.1C_30.5C.jpg"},
    {"pilot_id": "tr6p_017", "coco_id": 17, "produce": "Carrot", "modality": "srgb",
     "rel": "Normal/Carrot/sRGB_images/20250725_171408.jpg"},
    {"pilot_id": "tr6p_025", "coco_id": 25, "produce": "Carrot", "modality": "thermal_ir_fusion",
     "rel": "Normal/Carrot/IR_fusion_images/20250725_170448_25.4C_28.3C.jpg"},
    {"pilot_id": "tr6p_033", "coco_id": 33, "produce": "Guava", "modality": "srgb",
     "rel": "Normal/Guava/sRGB_images/20250625_135610.jpg"},
    {"pilot_id": "tr6p_041", "coco_id": 41, "produce": "Guava", "modality": "thermal_ir_fusion",
     "rel": "Normal/Guava/IR_fusion_images/20250625_085941_27.5C_29.0C.jpg"},
    {"pilot_id": "tr6p_049", "coco_id": 49, "produce": "Indian_Gooseberry", "modality": "srgb",
     "rel": "Normal/Indian_Gooseberry/sRGB_images/20250725_171131.jpg"},
    {"pilot_id": "tr6p_057", "coco_id": 57, "produce": "Indian_Gooseberry", "modality": "thermal_ir_fusion",
     "rel": "Normal/Indian_Gooseberry/IR_fusion_images/20250729_132753_29.5C_31.3C.jpg"},
    {"pilot_id": "tr6p_065", "coco_id": 65, "produce": "Mango", "modality": "srgb",
     "rel": "Normal/Mango/sRGB_images/20250920_123146.jpg"},
    {"pilot_id": "tr6p_073", "coco_id": 73, "produce": "Mango", "modality": "thermal_ir_fusion",
     "rel": "Normal/Mango/IR_fusion_images/20250920_162228_31.2C_32.8C.jpg"},
    {"pilot_id": "tr6p_081", "coco_id": 81, "produce": "Tomato", "modality": "srgb",
     "rel": "Normal/Tomato/sRGB_images/20250726_165434.jpg"},
    {"pilot_id": "tr6p_089", "coco_id": 89, "produce": "Tomato", "modality": "thermal_ir_fusion",
     "rel": "Normal/Tomato/IR_fusion_images/20250725_083842_27.3C_28.3C.jpg"},
]

# Visual review decisions. Defects are withheld unless a localized physical
# boundary is clearly identifiable; ripening spots, stem scars and thermal
# palette variation are not treated as defects.
REVIEW = {
    "tr6p_001": {
        "quality": "annotatable",
        "notes": "Clear banana silhouette including stem. Brown patches treated as ripening/bruising texture, not a separately delineable defect.",
        "review_needed": "Confirm exclusion of ripening spots from defect class.",
    },
    "tr6p_009": {
        "quality": "ambiguous",
        "notes": "Banana silhouette is visible but the thermal edge is soft and haloed. Fruit mask placed at the strongest stable transition. No physical defect boundary.",
        "review_needed": "Confirm fruit/background cutoff on the diffuse thermal halo.",
    },
    "tr6p_017": {
        "quality": "annotatable",
        "notes": "Clear carrot on white background. Pale surface variation looks like normal carrot skin. No localized defect annotated.",
        "review_needed": "Confirm pale patches are not defects.",
    },
    "tr6p_025": {
        "quality": "ambiguous",
        "notes": "Purple thermal core is distinct, but a warm halo makes the physical edge uncertain. Mask follows the strong purple/orange transition, excluding the outer halo. No defect.",
        "review_needed": "Confirm whether the halo should be inside the fruit mask.",
    },
    "tr6p_033": {
        "quality": "annotatable",
        "notes": "Clear guava including calyx. Speckling treated as normal surface texture. No localized defect annotated.",
        "review_needed": "Confirm calyx inclusion and that speckling is not a defect.",
    },
    "tr6p_041": {
        "quality": "ambiguous",
        "notes": "Low-contrast thermal guava with a fuzzy boundary and visible calyx bump. Mask follows the strongest silhouette. No physical defect boundary.",
        "review_needed": "Confirm low-contrast thermal outline, especially at the calyx.",
    },
    "tr6p_049": {
        "quality": "annotatable",
        "notes": "Clear Indian gooseberry. Tiny dark marks treated as lenticels/normal marks, not defects.",
        "review_needed": "Confirm small dark marks are not defects.",
    },
    "tr6p_057": {
        "quality": "ambiguous",
        "notes": "Low fruit/background contrast in thermal rendering. Fruit remains visible as a darker disk; outline is uncertain. No physical defect annotated.",
        "review_needed": "Confirm whether this thermal outline is repeatable enough to keep.",
    },
    "tr6p_065": {
        "quality": "annotatable",
        "notes": "Clear mango including stem. Yellowing treated as ripening color. Small dark marks not confidently separable from normal blemishes, so no defect polygon.",
        "review_needed": "Confirm small dark marks should remain unannotated as defects.",
    },
    "tr6p_073": {
        "quality": "ambiguous",
        "notes": "Mango body and stem are darker than the table. Outline placed on the strongest dark-to-background transition; table/halo excluded. No physical defect annotated.",
        "review_needed": "Confirm thermal mango versus table and stem inclusion.",
    },
    "tr6p_081": {
        "quality": "annotatable",
        "notes": "Clear tomato. Brown/yellow region at the top is the calyx/stem scar and is included in the fruit mask, not as a defect.",
        "review_needed": "Confirm stem-scar/calyx handling.",
    },
    "tr6p_089": {
        "quality": "annotatable",
        "notes": "Tomato thermal disk is visible against the background. Edge is slightly soft; mask follows the round silhouette. No physical defect boundary.",
        "review_needed": "Confirm thermal disk boundary, including the warmer upper rim.",
    },
}


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows, fieldnames):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def as_gray(mask):
    return Image.fromarray((mask.astype(np.uint8) * 255)).convert("L")


def gaussian_rgb(rgb, radius):
    image = Image.fromarray(rgb).filter(ImageFilter.GaussianBlur(radius=radius))
    return np.array(image).astype(np.float32)


def morphology(mask, close_size, open_size):
    image = as_gray(mask)
    if close_size >= 3:
        image = image.filter(ImageFilter.MaxFilter(close_size))
        image = image.filter(ImageFilter.MinFilter(close_size))
    if open_size >= 3:
        image = image.filter(ImageFilter.MinFilter(open_size))
        image = image.filter(ImageFilter.MaxFilter(open_size))
    return np.array(image) > 127


def connected_components(mask):
    h, w = mask.shape
    labels = np.zeros((h, w), dtype=np.int32)
    parent = [0]
    current = 0

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for y in range(h):
        row = mask[y]
        prev = labels[y - 1] if y else None
        for x in range(w):
            if not row[x]:
                continue
            neighbors = []
            if x and row[x - 1]:
                neighbors.append(labels[y, x - 1])
            if y and prev[x]:
                neighbors.append(prev[x])
            if x and y and mask[y - 1, x - 1]:
                neighbors.append(prev[x - 1])
            if y and x + 1 < w and mask[y - 1, x + 1]:
                neighbors.append(prev[x + 1])
            neighbors = [n for n in neighbors if n]
            if not neighbors:
                current += 1
                parent.append(current)
                labels[y, x] = current
            else:
                root = neighbors[0]
                labels[y, x] = root
                for n in neighbors[1:]:
                    union(root, n)
    remap = {}
    next_id = 1
    areas = {}
    out = np.zeros_like(labels)
    for y in range(h):
        for x in range(w):
            lab = labels[y, x]
            if not lab:
                continue
            root = find(lab)
            if root not in remap:
                remap[root] = next_id
                areas[next_id] = 0
                next_id += 1
            cid = remap[root]
            out[y, x] = cid
            areas[cid] += 1
    return out, areas


def keep_largest(mask):
    labels, areas = connected_components(mask)
    if not areas:
        return mask
    largest = max(areas, key=areas.get)
    return labels == largest


def fill_holes(mask):
    inv = ~mask
    labels, areas = connected_components(inv)
    h, w = mask.shape
    border = set()
    border.update(labels[0].tolist())
    border.update(labels[-1].tolist())
    border.update(labels[:, 0].tolist())
    border.update(labels[:, -1].tolist())
    border.discard(0)
    filled = mask.copy()
    for lab, area in areas.items():
        if lab not in border:
            filled[labels == lab] = True
    return filled


def otsu(values):
    hist, _ = np.histogram(values, bins=256, range=(float(values.min()), float(values.max())))
    total = values.size
    sum_all = np.dot(np.arange(256), hist)
    sum_b = 0.0
    w_b = 0.0
    max_var = -1.0
    threshold = 0
    for i, count in enumerate(hist):
        w_b += count
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += i * count
        m_b = sum_b / w_b
        m_f = (sum_all - sum_b) / w_f
        var = w_b * w_f * (m_b - m_f) ** 2
        if var > max_var:
            max_var = var
            threshold = i
    vmin, vmax = float(values.min()), float(values.max())
    return vmin + (threshold / 255.0) * (vmax - vmin)


def working_size(width, height, max_side=1000):
    long_side = max(width, height)
    if long_side <= max_side:
        return width, height, 1.0
    scale = max_side / float(long_side)
    return max(1, int(round(width * scale))), max(1, int(round(height * scale))), scale


def srgb_mask(rgb):
    h, w, _ = rgb.shape
    work_w, work_h, _ = working_size(w, h)
    small = np.array(Image.fromarray(rgb).resize((work_w, work_h), Image.Resampling.BILINEAR)).astype(np.float32)
    border = np.concatenate([
        small[:8, :, :].reshape(-1, 3),
        small[-8:, :, :].reshape(-1, 3),
        small[:, :8, :].reshape(-1, 3),
        small[:, -8:, :].reshape(-1, 3),
    ], axis=0)
    bg = np.median(border, axis=0)
    dist = np.linalg.norm(small - bg, axis=2)
    mx = small.max(axis=2)
    mn = small.min(axis=2)
    sat = np.where(mx > 1e-6, (mx - mn) / mx, 0.0)
    value = mx / 255.0
    score = dist + 80.0 * sat
    shadow = (value < (bg.max() / 255.0) * 0.90) & (sat < 0.17) & (dist < 72)
    score = np.where(shadow, score * 0.12, score)
    thresh = max(otsu(score.ravel()), 32.0)
    mask = score > thresh
    mask = morphology(mask, close_size=7, open_size=5)
    mask = keep_largest(mask)
    mask = mask & ~shadow
    mask = keep_largest(mask)
    mask = fill_holes(mask)
    mask = morphology(mask, close_size=5, open_size=0)
    return mask, (w / float(work_w), h / float(work_h))


def _thermal_score(rgb):
    blurred = gaussian_rgb(rgb, radius=2.2)
    luma = 0.299 * blurred[:, :, 0] + 0.587 * blurred[:, :, 1] + 0.114 * blurred[:, :, 2]
    h, w = luma.shape
    ch, cw = max(10, h // 8), max(10, w // 8)
    corners = np.concatenate([
        luma[:ch, :cw].ravel(),
        luma[:ch, -cw:].ravel(),
        luma[-ch:, :cw].ravel(),
        luma[-ch:, -cw:].ravel(),
    ])
    bg_luma = float(np.median(corners))
    local = np.array(
        Image.fromarray(luma.astype(np.uint8)).convert("L").filter(ImageFilter.GaussianBlur(radius=16))
    ).astype(np.float32)
    return (bg_luma - luma) + 0.45 * (local - luma)


def _mask_quality(mask):
    frac = float(mask.mean())
    if frac < 0.025 or frac > 0.58:
        return None
    ys, xs = np.where(mask)
    bw = int(xs.max() - xs.min()) + 1
    bh = int(ys.max() - ys.min()) + 1
    compactness = float(mask.sum()) / float(bw * bh)
    touches = (
        int(mask[0].any())
        + int(mask[-1].any())
        + int(mask[:, 0].any())
        + int(mask[:, -1].any())
    )
    if mask[:, 0].any() and mask[:, -1].any():
        return None
    return compactness * 2.2 + (0.28 - abs(frac - 0.28)) - 0.4 * touches


def thermal_mask(rgb):
    score = _thermal_score(rgb)
    thresh0 = max(otsu(score.ravel()), 4.0)
    best = None
    best_key = -1e9
    for step in range(28):
        mask = score > (thresh0 + step * 1.4)
        mask = morphology(mask, close_size=9, open_size=5)
        mask = keep_largest(mask)
        mask = fill_holes(mask)
        mask = morphology(mask, close_size=7, open_size=0)
        key = _mask_quality(mask)
        if key is None:
            continue
        if key > best_key:
            best_key = key
            best = mask
    if best is None:
        mask = score > thresh0
        mask = morphology(mask, close_size=9, open_size=5)
        mask = keep_largest(mask)
        mask = fill_holes(mask)
        best = mask
    return best, (1.0, 1.0)


def trace_contour(mask):
    """Moore-neighbor boundary walk; object is kept on the left."""
    padded = np.pad(mask.astype(np.uint8), 1, mode="constant")
    h, w = mask.shape
    start = None
    for y in range(1, h + 1):
        row = padded[y]
        for x in range(1, w + 1):
            if row[x] and not padded[y, x - 1]:
                start = (x, y)
                break
        if start is not None:
            break
    if start is None:
        return []
    deltas = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]
    contour = []
    x, y = start
    direction = 0
    for _ in range(h * w):
        contour.append((x - 1, y - 1))
        found = False
        search = (direction + 6) % 8
        for step in range(8):
            idx = (search + step) % 8
            nx = x + deltas[idx][0]
            ny = y + deltas[idx][1]
            if padded[ny, nx]:
                x, y = nx, ny
                direction = idx
                found = True
                break
        if not found:
            break
        if (x, y) == start and len(contour) > 8:
            break
    if len(contour) >= 3 and contour[0] != contour[-1]:
        contour.append(contour[0])
    return contour


def rdp(points, epsilon):
    if len(points) < 3:
        return points
    start, end = np.array(points[0], dtype=float), np.array(points[-1], dtype=float)
    line = end - start
    length = np.linalg.norm(line)
    if length < 1e-6:
        dists = [np.linalg.norm(np.array(p) - start) for p in points]
        idx = int(np.argmax(dists))
        if dists[idx] <= epsilon:
            return [points[0], points[-1]]
        return rdp(points[: idx + 1], epsilon)[:-1] + rdp(points[idx:], epsilon)
    unit = line / length
    max_dist = -1.0
    idx = 0
    for i, p in enumerate(points[1:-1], 1):
        vec = np.array(p, dtype=float) - start
        dist = abs(unit[0] * vec[1] - unit[1] * vec[0])
        if dist > max_dist:
            max_dist = dist
            idx = i
    if max_dist <= epsilon:
        return [points[0], points[-1]]
    return rdp(points[: idx + 1], epsilon)[:-1] + rdp(points[idx:], epsilon)


def polygon_area(xs, ys):
    return 0.5 * abs(sum(xs[i] * ys[(i + 1) % len(xs)] - xs[(i + 1) % len(xs)] * ys[i] for i in range(len(xs))))


def clip_polygon(points, width, height):
    clipped = []
    for x, y in points:
        clipped.append((
            float(min(max(x, 0.0), width - 1e-3)),
            float(min(max(y, 0.0), height - 1e-3)),
        ))
    return clipped


def bbox_from_polygon(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    return [x0, y0, x1 - x0, y1 - y0]


def draw_overlay(rgb, fruit_poly, quality, title, out_path, display_rotate_cw=False):
    image = Image.fromarray(rgb).convert("RGBA")
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay, "RGBA")
    if fruit_poly:
        draw.polygon(fruit_poly, fill=(46, 134, 222, 70), outline=(20, 90, 180, 255))
        for x, y in fruit_poly[:: max(1, len(fruit_poly) // 40)]:
            draw.ellipse((x - 2, y - 2, x + 2, y + 2), fill=(20, 90, 180, 255))
    composed = Image.alpha_composite(image, overlay).convert("RGB")
    if display_rotate_cw:
        composed = composed.rotate(-90, expand=True)
    caption = Image.new("RGB", (composed.width, composed.height + 36), "white")
    caption.paste(composed, (0, 36))
    cdraw = ImageDraw.Draw(caption)
    cdraw.text((8, 10), "%s | %s | fruit only | no defect" % (title, quality), fill="black")
    caption.save(out_path, quality=88)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate unverified calibration proposals only.")
    parser.add_argument(
        "--overwrite-proposals",
        action="store_true",
        help="Required to replace existing proposal masks/COCO. Never writes human annotations.",
    )
    args = parser.parse_args()
    existing = sorted((MASK_DIR).glob("tr6p_*.png")) if MASK_DIR.exists() else []
    if existing and not args.overwrite_proposals:
        raise SystemExit(
            "Refusing to overwrite existing proposal masks in %s. "
            "These files are proposal_only, not ground truth. "
            "Pass --overwrite-proposals only if you intend to replace proposals."
            % MASK_DIR
        )
    OVERLAY_DIR.mkdir(parents=True, exist_ok=True)
    MASK_DIR.mkdir(parents=True, exist_ok=True)
    coco_path = WORKSPACE / "annotations" / "coco_annotations.json"
    coco = json.loads(coco_path.read_text(encoding="utf-8"))
    coco["info"]["description"] = (
        "Foresight-TR6+ calibration annotations. Computer-assisted fruit outlines "
        "from stored JPEG pixels; defect masks omitted unless visually identifiable. "
        "Status is annotated, not reviewed."
    )
    coco["info"]["version"] = "0.1-calibration"
    coco["info"]["created"] = datetime.now(timezone.utc).isoformat()
    coco["info"]["annotation_status"] = "calibration_annotated_pending_review"
    coco["annotations"] = []

    annotation_id = 1
    results = []
    for item in CALIBRATION:
        path = DATASET / item["rel"]
        with Image.open(path) as image:
            stored = image.convert("RGB")
            width, height = stored.size
            rgb = np.array(stored)
        if item["modality"] == "srgb":
            work_mask, scale_xy = srgb_mask(rgb)
            epsilon = 1.6
        else:
            work_mask, scale_xy = thermal_mask(rgb)
            epsilon = 4.5
        contour = trace_contour(work_mask)
        if len(contour) < 8:
            raise SystemExit("Failed to trace contour for %s (n=%d)" % (item["pilot_id"], len(contour)))
        simplified = rdp(contour, epsilon)
        if simplified[0] != simplified[-1]:
            simplified.append(simplified[0])
        if len(simplified) < 4:
            simplified = list(contour)
            if simplified[0] != simplified[-1]:
                simplified.append(simplified[0])
        scaled = [(p[0] * scale_xy[0], p[1] * scale_xy[1]) for p in simplified]
        polygon = clip_polygon(scaled, width, height)
        mask = np.array(
            Image.fromarray((work_mask.astype(np.uint8) * 255)).resize((width, height), Image.Resampling.NEAREST)
        ) > 127
        xs = [p[0] for p in polygon]
        ys = [p[1] for p in polygon]
        area = polygon_area(xs, ys)
        bbox = bbox_from_polygon(polygon)
        decision = REVIEW[item["pilot_id"]]
        coco["annotations"].append({
            "id": annotation_id,
            "image_id": item["coco_id"],
            "category_id": 1,
            "segmentation": [[coord for point in polygon for coord in point]],
            "area": float(area),
            "bbox": [float(v) for v in bbox],
            "iscrowd": 0,
            "ftr6plus_pilot_id": item["pilot_id"],
            "ftr6plus_class": "fruit_visible_region",
        })
        annotation_id += 1
        raster = Image.fromarray(np.where(mask, 1, 0).astype(np.uint8)).convert("L")
        raster_rel = "annotations/masks/%s.png" % item["pilot_id"]
        raster.save(WORKSPACE / raster_rel)
        overlay_name = "%s_%s_%s.jpg" % (item["pilot_id"], item["produce"], item["modality"])
        draw_overlay(
            rgb,
            polygon,
            decision["quality"],
            "%s %s %s" % (item["pilot_id"], item["produce"], item["modality"]),
            OVERLAY_DIR / overlay_name,
            display_rotate_cw=item["modality"] == "srgb",
        )
        results.append({
            "pilot_id": item["pilot_id"],
            "produce": item["produce"],
            "modality": item["modality"],
            "width": width,
            "height": height,
            "polygon_points": len(polygon),
            "area": round(area, 1),
            "mask_fraction": round(float(mask.mean()), 4),
            "quality": decision["quality"],
            "defect_count": 0,
            "overlay": str((OVERLAY_DIR / overlay_name).relative_to(WORKSPACE)),
            "raster_mask_path": raster_rel,
        })
        print(item["pilot_id"], width, height, "points", len(polygon), "frac", round(float(mask.mean()), 4), decision["quality"])

    coco_path.write_text(json.dumps(coco, indent=2), encoding="utf-8")

    records_path = WORKSPACE / "annotations" / "annotation_records.csv"
    records = read_csv(records_path)
    now = datetime.now(timezone.utc).isoformat()
    by_pilot = {row["pilot_id"]: row for row in CALIBRATION}
    result_by_id = {row["pilot_id"]: row for row in results}
    for row in records:
        pid = row["pilot_id"]
        if pid not in by_pilot:
            continue
        decision = REVIEW[pid]
        result = result_by_id[pid]
        row["annotation_status"] = "annotated"
        row["annotator_id"] = "cursor-agent-calibration-assist"
        row["reviewer_id"] = ""
        row["annotation_file"] = "annotations/coco_annotations.json"
        row["raster_mask_path"] = result["raster_mask_path"]
        row["fruit_instance_count"] = "1"
        row["visible_defect_instance_count"] = "0"
        row["image_quality"] = decision["quality"]
        row["exclusion_reason"] = ""
        row["annotation_started_at"] = now
        row["annotation_completed_at"] = now
        row["reviewed_at"] = ""
        row["notes"] = decision["notes"] + " Requires human review: " + decision["review_needed"]
    write_csv(records_path, records, list(records[0].keys()))

    (WORKSPACE / "reports" / "calibration_annotation_summary.json").write_text(
        json.dumps({
            "generated_at": now,
            "batch_size": 12,
            "annotated": 12,
            "excluded": 0,
            "defect_masks": 0,
            "status": "annotated_pending_human_review",
            "label_studio_available": False,
            "coordinate_space": "stored JPEG pixels without EXIF transpose",
            "srgb_exif_orientation": 6,
            "images": results,
            "review": REVIEW,
        }, indent=2),
        encoding="utf-8",
    )
    print("wrote", coco_path)
    print("overlays", OVERLAY_DIR)


if __name__ == "__main__":
    main()
