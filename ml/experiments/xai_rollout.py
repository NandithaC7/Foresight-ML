"""
xai_rollout.py — attention-rollout explanations for the fine-tuned ViT.

Rollout (Abnar & Zuidema 2020): for each block take the softmax attention,
average heads, add identity, row-normalise, multiply through the layers; the
CLS->patch row gives a 14x14 relevance map.

Outputs (artifacts/experiments/xai/):
  * panels of correct and incorrect TEST spoilage predictions with overlays
  * a deletion sanity check: mask the top-20% rollout patches vs 20% random
    patches and compare the drop in the predicted-class probability. A larger
    drop for rollout patches is weak evidence that the map is faithful.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml"))
sys.path.insert(0, str(ROOT / "ml" / "evaluate"))
from common import IMG_SIZE, SPOILAGE_CLASSES, build_transforms, load_split_rows, pick_device, save_json  # noqa: E402
from evaluate_vit import load_model  # noqa: E402


def rollout(model, x):
    blocks, attns, hooks = model.backbone.blocks, [], []
    for b in blocks:
        b.attn.fused_attn = False
        hooks.append(b.attn.attn_drop.register_forward_hook(lambda m, i, o: attns.append(o.detach())))
    with torch.no_grad():
        lt, ls = model(x)
    for h in hooks:
        h.remove()
    for b in blocks:
        b.attn.fused_attn = True
    n = attns[0].shape[-1]
    maps = []
    for bi in range(x.shape[0]):
        r = torch.eye(n, device=x.device)
        for a in attns:
            a = a[bi].mean(0) + torch.eye(n, device=x.device)
            r = (a / a.sum(-1, keepdim=True)) @ r
        m = r[0, 1:].cpu().numpy()
        maps.append(m.reshape(14, 14))
    return np.stack(maps), ls.softmax(1).cpu().numpy()


def overlay(img, m):
    m = (m - m.min()) / (m.max() - m.min() + 1e-8)
    h = np.asarray(Image.fromarray((m * 255).astype(np.uint8)).resize(img.size, Image.BILINEAR), dtype=np.float32) / 255
    color = np.stack([np.clip(1.5 * h, 0, 1), np.clip(1.5 * h - 0.5, 0, 1), np.zeros_like(h)], -1)
    return Image.fromarray(((0.55 * np.asarray(img, dtype=np.float32) / 255 + 0.45 * color) * 255).clip(0, 255).astype(np.uint8))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", type=Path, default=ROOT / "artifacts/runs/vit_b16_primary")
    ap.add_argument("--out", type=Path, default=ROOT / "artifacts/experiments/xai")
    ap.add_argument("--n-deletion", type=int, default=240)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    dev = pick_device()
    model, cfg, _ = load_model(a.run, dev)
    tf = build_transforms(cfg["mean"], cfg["std"], train=False)
    rows = {r["sample_id"]: r for r in load_split_rows(ROOT / "artifacts/dataset/v1/split_manifest.csv", "test")}
    preds = list(csv.DictReader(open(a.run / "eval" / "test_clean_0_none_predictions.csv")))
    cache = ROOT / "artifacts/cache/srgb_256"
    load = lambda sid: Image.open(cache / f"{rows[sid]['sha256']}.jpg").convert("RGB")  # noqa: E731

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    rng = np.random.default_rng(42)
    correct = [p for p in preds if p["true_spoil"] == p["pred_spoil"]]
    wrong = [p for p in preds if p["true_spoil"] != p["pred_spoil"]]
    for name, group in (("correct", correct), ("incorrect", wrong)):
        if not group:
            continue
        pick = [group[i] for i in rng.choice(len(group), min(8, len(group)), replace=False)]
        fig, axes = plt.subplots(2, len(pick), figsize=(2.3 * len(pick), 5))
        axes = np.array(axes).reshape(2, -1)
        for j, p in enumerate(pick):
            img = load(p["sample_id"]).resize((IMG_SIZE, IMG_SIZE))
            m, _ = rollout(model, tf(load(p["sample_id"]))[None].to(dev))
            axes[0, j].imshow(img); axes[1, j].imshow(overlay(img, m[0]))
            axes[0, j].set_title(f"{p['true_type'][:10]}\ntrue {p['true_spoil'][:3]} pred {p['pred_spoil'][:3]}\n"
                                 f"p(sp)={float(p['p_spoiled']):.2f}", fontsize=7)
            for ax in axes[:, j]:
                ax.axis("off")
        fig.suptitle(f"Attention rollout — {name} test spoilage predictions (diagnostic only)", fontsize=9)
        fig.tight_layout(); fig.savefig(a.out / f"rollout_{name}.png", dpi=130); plt.close(fig)

    # deletion sanity check
    sample = [preds[i] for i in rng.choice(len(preds), min(a.n_deletion, len(preds)), replace=False)]
    drops_top, drops_rand = [], []
    mean = torch.tensor(cfg["mean"]).view(3, 1, 1)
    for p in sample:
        x = tf(load(p["sample_id"]))
        m, prob = rollout(model, x[None].to(dev))
        c = int(prob[0].argmax())
        order = np.argsort(-m[0].ravel())
        k = int(0.2 * 196)
        variants = []
        for idx in (order[:k], rng.choice(196, k, replace=False)):
            xx = x.clone()
            for t in idx:
                r, cc = divmod(int(t), 14)
                xx[:, r * 16:(r + 1) * 16, cc * 16:(cc + 1) * 16] = (mean - mean) / torch.tensor(cfg["std"]).view(3, 1, 1)
            variants.append(xx)
        with torch.no_grad():
            _, ls = model(torch.stack(variants).to(dev))
            pp = ls.softmax(1).cpu().numpy()[:, c]
        drops_top.append(float(prob[0, c] - pp[0])); drops_rand.append(float(prob[0, c] - pp[1]))
    from scipy.stats import wilcoxon
    stat = wilcoxon(drops_top, drops_rand)
    res = {"method": "attention rollout (head mean, +I, row-normalised)", "n_images": len(sample),
           "occlusion": "top-20% rollout patches vs random 20% patches replaced by the per-channel mean pixel",
           "mean_drop_top_rollout": float(np.mean(drops_top)), "mean_drop_random": float(np.mean(drops_rand)),
           "median_drop_top_rollout": float(np.median(drops_top)), "median_drop_random": float(np.median(drops_rand)),
           "wilcoxon_p": float(stat.pvalue),
           "n_test_correct": len(correct), "n_test_incorrect": len(wrong),
           "limitations": ["Rollout ignores MLP blocks and value vectors; it is an approximation.",
                           "Explanations are qualitative diagnostics, not proof of correctness.",
                           "No reviewed decay masks exist, so overlap with true decay regions cannot be measured."]}
    save_json(res, a.out / "xai_summary.json")
    print(res)


if __name__ == "__main__":
    main()
