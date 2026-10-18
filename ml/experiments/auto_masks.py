"""
auto_masks.py — MACHINE-GENERATED masks for the pilot U-Net (not human ground truth).

fruit : pixels that differ from the plain background (colour distance to the border
        median) AND are saturated; largest connected component, holes filled.
decay : dark pixels (HSV value < 0.38) inside the fruit, ONLY for images a human
        judged 'annotated_has_decay'; empty for 'annotated_no_visible_decay'.
        'ambiguous' images are skipped.
Writes artifacts/experiments/unet_pilot/auto_masks/<id>_{fruit,decay}.png (annotation-image size)
and auto_masks_preview.png.
"""
import csv
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts/experiments/unet_pilot/auto_masks"


def masks_for(img: Image.Image, has_decay: bool):
    a = np.asarray(img.convert("RGB"), np.float32) / 255
    hsv = np.asarray(img.convert("HSV"), np.float32) / 255
    s, v = hsv[..., 1], hsv[..., 2]
    b = np.concatenate([a[:8].reshape(-1, 3), a[-8:].reshape(-1, 3), a[:, :8].reshape(-1, 3), a[:, -8:].reshape(-1, 3)])
    dist = np.linalg.norm(a - np.median(b, 0), axis=-1)
    fruit = ((dist > 0.18) & (s > 0.16)) | (s > 0.30)
    fruit = ndi.binary_opening(fruit, iterations=2)
    lab, n = ndi.label(fruit)
    if n:
        fruit = lab == (np.argmax(ndi.sum(fruit, lab, range(1, n + 1))) + 1)
    fruit = ndi.binary_fill_holes(ndi.binary_closing(fruit, iterations=4))
    decay = np.zeros_like(fruit)
    if has_decay:
        decay = fruit & (v < 0.38)
        decay = ndi.binary_opening(decay, iterations=1) & ndi.binary_erosion(fruit, iterations=3)
    return fruit, decay


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = [r for r in csv.DictReader(open(ROOT / "Foresight-TR6-plus/unet-annotation/human_visible_decay_labels.csv"))
            if r["visible_decay"] in ("0", "1")]
    man = {r["annotation_id"]: r for r in csv.DictReader(open(ROOT / "Foresight-TR6-plus/unet-annotation/unet_annotation_manifest.csv"))}
    prev = []
    for r in rows:
        img = Image.open(ROOT / man[r["annotation_id"]]["image_path"]).convert("RGB")
        f, d = masks_for(img, r["visible_decay"] == "1")
        Image.fromarray((f * 255).astype(np.uint8)).save(OUT / f"{r['annotation_id']}_fruit.png")
        Image.fromarray((d * 255).astype(np.uint8)).save(OUT / f"{r['annotation_id']}_decay.png")
        if r["visible_decay"] == "1" and len(prev) < 8 and r["produce_class"] not in [p[0] for p in prev]:
            prev.append((r["produce_class"], img, f, d))
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, len(prev), figsize=(2.2 * len(prev), 3))
    for ax, (p, img, f, d) in zip(np.atleast_1d(axes), prev):
        o = np.asarray(img.resize((256, int(256 * img.height / img.width))), np.float32) / 255
        fs = np.asarray(Image.fromarray(f).resize(o.shape[1::-1])); ds = np.asarray(Image.fromarray(d).resize(o.shape[1::-1]))
        o[fs] = 0.65 * o[fs] + 0.35 * np.array([0.18, 0.42, 0.31]); o[ds] = 0.4 * o[ds] + 0.6 * np.array([0.9, 0.3, 0.1])
        ax.imshow(o); ax.set_title(p, fontsize=7); ax.axis("off")
    fig.suptitle("Machine-generated masks (green fruit, orange dark/decay region) — not human ground truth", fontsize=8)
    fig.tight_layout(); fig.savefig(OUT.parent / "auto_masks_preview.png", dpi=130); plt.close(fig)
    print(len(rows), "images masked")


if __name__ == "__main__":
    main()
