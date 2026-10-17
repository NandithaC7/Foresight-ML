"""
xai_extended.py — additional attention-rollout analyses on REAL model inference.

Outputs (artifacts/experiments/xai/):
  class_gallery.png        one correct test example per produce x spoilage stratum
  failure_cases.png        representative false negatives / false positives (spoilage)
  stability.json           explanation stability: Spearman correlation between the
                           rollout map of an image and of (a) a horizontally flipped
                           copy (map flipped back) and (b) a mildly noised copy
                           (Gaussian sigma=0.02), versus maps of two different images
  gallery_index.csv        sample ids, labels, predictions and probabilities shown
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml")); sys.path.insert(0, str(ROOT / "ml/evaluate")); sys.path.insert(0, str(ROOT / "ml/experiments"))
from common import IMG_SIZE, PRODUCE_CLASSES, SPOILAGE_CLASSES, build_transforms, corrupt, load_split_rows, pick_device, save_json  # noqa
from evaluate_vit import load_model  # noqa
from xai_rollout import overlay, rollout  # noqa

RUN = ROOT / "artifacts/runs/vit_b16_primary"
OUT = ROOT / "artifacts/experiments/xai"


def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from scipy.stats import spearmanr
    dev = pick_device()
    model, cfg, _ = load_model(RUN, dev)
    tf = build_transforms(cfg["mean"], cfg["std"], train=False)
    rows = {r["sample_id"]: r for r in load_split_rows(ROOT / "artifacts/dataset/v1/split_manifest.csv", "test")}
    preds = list(csv.DictReader(open(RUN / "eval/test_clean_0_none_predictions.csv")))
    cache = ROOT / "artifacts/cache/srgb_256"
    img = lambda sid: Image.open(cache / f"{rows[sid]['sha256']}.jpg").convert("RGB")  # noqa: E731
    index = []

    def panel(items, fname, title):
        fig, axes = plt.subplots(2, len(items), figsize=(2.2 * len(items), 5.2))
        for j, (p, tag) in enumerate(items):
            im = img(p["sample_id"]); m, prob = rollout(model, tf(im)[None].to(dev))
            small = im.resize((IMG_SIZE, IMG_SIZE))
            axes[0, j].imshow(small); axes[1, j].imshow(overlay(small, m[0]))
            axes[0, j].set_title(f"{tag}\n{p['true_type'].replace('Indian_Gooseberry','Gooseberry')}\n"
                                 f"true {p['true_spoil'].replace('_',' ')}\npred {p['pred_spoil'].replace('_',' ')} "
                                 f"p(sp)={prob[0,1]:.2f}", fontsize=6.5)
            for ax in axes[:, j]:
                ax.axis("off")
            index.append({"figure": fname, "tag": tag, "sample_id": p["sample_id"], "source": rows[p["sample_id"]]["source_relative_path"],
                          "true_type": p["true_type"], "pred_type": p["pred_type"], "true_spoil": p["true_spoil"],
                          "pred_spoil": p["pred_spoil"], "p_spoiled": f"{prob[0,1]:.4f}"})
        fig.suptitle(title, fontsize=9); fig.tight_layout(); fig.savefig(OUT / fname, dpi=140); plt.close(fig)

    rng = np.random.default_rng(7)
    gallery = []
    for t in PRODUCE_CLASSES:
        for s in SPOILAGE_CLASSES:
            c = [p for p in preds if p["true_type"] == t and p["true_spoil"] == s and p["pred_spoil"] == s]
            gallery.append((c[rng.integers(len(c))], f"{t[:6]}/{'S' if s == 'Spoiled' else 'NS'}"))
    panel(gallery, "class_gallery.png", "Attention rollout — one correctly classified TEST image per produce × spoilage stratum")
    fn = [p for p in preds if p["true_spoil"] == "Spoiled" and p["pred_spoil"] == "Not_spoiled"]
    fp = [p for p in preds if p["true_spoil"] == "Not_spoiled" and p["pred_spoil"] == "Spoiled"]
    pick = [(fn[i], "FN") for i in rng.choice(len(fn), 5, replace=False)] + [(fp[i], "FP") for i in rng.choice(len(fp), min(5, len(fp)), replace=False)]
    panel(pick, "failure_cases.png", "Attention rollout — test false negatives (FN: Spoiled→Not spoiled) and false positives (FP)")
    # page-width versions (<= 6 images per panel) of the same selections, for the reports
    panel(gallery[:6], "class_gallery_part1.png", "Attention rollout — correct TEST predictions (Banana, Carrot, Guava)")
    panel(gallery[6:], "class_gallery_part2.png", "Attention rollout — correct TEST predictions (Indian Gooseberry, Mango, Tomato)")
    panel(pick[:5], "failure_cases_fn.png", "Attention rollout — TEST false negatives (labelled Spoiled, predicted Not spoiled)")
    panel(pick[5:], "failure_cases_fp.png", "Attention rollout — TEST false positives (labelled Not spoiled, predicted Spoiled)")
    if "--figures-only" in sys.argv:
        with open(OUT / "gallery_index.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(index[0].keys())); w.writeheader(); w.writerows(index)
        return

    # stability
    sample = [preds[i] for i in rng.choice(len(preds), 150, replace=False)]
    flip_r, noise_r, other_r, pred_same_flip, pred_same_noise = [], [], [], 0, 0
    maps = []
    for k, p in enumerate(sample):
        im = img(p["sample_id"])
        m0, pr0 = rollout(model, tf(im)[None].to(dev))
        mf, prf = rollout(model, tf(im.transpose(Image.FLIP_LEFT_RIGHT))[None].to(dev))
        mn, prn = rollout(model, tf(corrupt(im, "gaussian", 0.02, 500 + k))[None].to(dev))
        flip_r.append(spearmanr(m0[0].ravel(), mf[0][:, ::-1].ravel()).statistic)
        noise_r.append(spearmanr(m0[0].ravel(), mn[0].ravel()).statistic)
        pred_same_flip += int(pr0[0].argmax() == prf[0].argmax()); pred_same_noise += int(pr0[0].argmax() == prn[0].argmax())
        maps.append(m0[0])
    for k in range(len(maps) - 1):
        other_r.append(spearmanr(maps[k].ravel(), maps[k + 1].ravel()).statistic)
    res = {"n_images": len(sample), "method": "Spearman rank correlation of 14x14 rollout maps",
           "flip_consistency": {"mean": float(np.mean(flip_r)), "median": float(np.median(flip_r)), "p10": float(np.percentile(flip_r, 10))},
           "gaussian_0.02_consistency": {"mean": float(np.mean(noise_r)), "median": float(np.median(noise_r)), "p10": float(np.percentile(noise_r, 10))},
           "different_image_baseline": {"mean": float(np.mean(other_r)), "median": float(np.median(other_r))},
           "spoilage_prediction_unchanged_flip": pred_same_flip / len(sample),
           "spoilage_prediction_unchanged_noise": pred_same_noise / len(sample)}
    save_json(res, OUT / "stability.json")
    with open(OUT / "gallery_index.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(index[0].keys())); w.writeheader(); w.writerows(index)
    print(res)


if __name__ == "__main__":
    main()
