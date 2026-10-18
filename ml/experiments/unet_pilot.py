"""
unet_pilot.py — PILOT U-Net for fruit + visible-decay segmentation from human polygons.

Reads polygons drawn in the local Label Studio project "Foresight U-Net decay" (read-only),
rasterises them (channel 0 = fruit, channel 1 = decay) at the annotation image size, trains a
small U-Net (ImageNet ResNet-18 encoder) on TRAIN-split images only, and evaluates on
the annotated TEST-split images. With a handful of masks this demonstrates the pipeline;
metrics are reported per image and are not a validated benchmark.

Loss: L = 0.5 * BCEWithLogits + 0.5 * soft Dice (per channel).
Outputs: artifacts/experiments/unet_pilot/{unet_pilot.pt, results.json, test_overlays.png, masks/}
         and backend/models/unet_pilot.pt

Usage: .venv/bin/python ml/experiments/unet_pilot.py [--steps 400]
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as Fnn
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml"))
sys.path.insert(0, str(ROOT / "backend"))
from common import pick_device, save_json, seed_everything  # noqa: E402
from unet_model import UNetResNet18  # noqa: E402  (shared with the backend)

WS = ROOT / "Foresight-TR6-plus"
OUT = ROOT / "artifacts/experiments/unet_pilot"
SIZE = 256
MEAN, STD = np.array([0.485, 0.456, 0.406], np.float32), np.array([0.229, 0.224, 0.225], np.float32)


def load_polygons():
    db = sqlite3.connect(f"file:{WS}/.labelstudio-data/label_studio.sqlite3?mode=ro", uri=True)
    pid = db.execute("select id from project where title = 'Foresight U-Net decay'").fetchone()[0]
    man = {r["annotation_id"]: r for r in csv.DictReader(open(WS / "unet-annotation/unet_annotation_manifest.csv"))}
    out = []
    for data, res in db.execute("select t.data, c.result from task t join task_completion c on c.task_id=t.id "
                                "where t.project_id=? and c.was_cancelled=0", (pid,)):
        aid = list(json.loads(data).values())[0].split("/")[-1].rsplit(".", 1)[0]
        polys = [(it["value"]["polygonlabels"][0], it["value"]["points"]) for it in json.loads(res) if it["type"] == "polygonlabels"]
        if any(l == "fruit" for l, _ in polys):
            out.append((man[aid], polys))
    return out


def rasterise(m, polys):
    w, h = int(m["width"]), int(m["height"])
    masks = []
    for lab in ("fruit", "decay"):
        im = Image.new("L", (w, h), 0)
        d = ImageDraw.Draw(im)
        for l, pts in polys:
            if l == lab and len(pts) >= 3:
                d.polygon([(x / 100 * w, y / 100 * h) for x, y in pts], fill=255)
        masks.append(im)
    return masks


def to_tensor(img):
    a = (np.asarray(img.convert("RGB").resize((SIZE, SIZE), Image.BILINEAR), np.float32) / 255 - MEAN) / STD
    return torch.from_numpy(a).permute(2, 0, 1)


def mask_tensor(ms):
    return torch.from_numpy(np.stack([np.asarray(m.resize((SIZE, SIZE), Image.NEAREST), np.float32) / 255 for m in ms]))


def dice_iou(pred, gt):
    inter = (pred & gt).sum(); s = pred.sum() + gt.sum(); u = (pred | gt).sum()
    return (float(2 * inter / s) if s else 1.0), (float(inter / u) if u else 1.0)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--steps", type=int, default=400); ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--mask-source", choices=["human", "auto"], default="human")
    a = ap.parse_args()
    seed_everything(a.seed); dev = pick_device()
    OUT.mkdir(parents=True, exist_ok=True); (OUT / "masks").mkdir(exist_ok=True)
    if a.mask_source == "human":
        data = [(m, ("polys", p)) for m, p in load_polygons()]
    else:  # machine-generated masks gated by human image-level decisions (see auto_masks.py)
        man = {r["annotation_id"]: r for r in csv.DictReader(open(WS / "unet-annotation/unet_annotation_manifest.csv"))}
        lab = [r for r in csv.DictReader(open(WS / "unet-annotation/human_visible_decay_labels.csv")) if r["visible_decay"] in ("0", "1")]
        data = [(man[r["annotation_id"]], ("auto", r["annotation_id"])) for r in lab]
    items = []
    for m, (kind, src) in data:
        img = Image.open(ROOT / m["image_path"]).convert("RGB")
        if kind == "polys":
            fm, dm = rasterise(m, src); polys = src
        else:
            am = OUT / "auto_masks"
            fm, dm = Image.open(am / f"{src}_fruit.png"), Image.open(am / f"{src}_decay.png"); polys = []
        fm.save(OUT / "masks" / f"{m['annotation_id']}_fruit.png"); dm.save(OUT / "masks" / f"{m['annotation_id']}_decay.png")
        items.append({"m": m, "img": img, "x": to_tensor(img), "y": mask_tensor([fm, dm]),
                      "n_decay_polys": sum(l == "decay" for l, _ in polys)})
    train = [it for it in items if it["m"]["split"] == "train"]
    test = [it for it in items if it["m"]["split"] in ("test", "val")]
    print(f"annotated images: {len(items)} (train {len(train)}, eval {len(test)})", flush=True)
    if len(train) < 2:
        raise SystemExit("Need at least 2 annotated TRAIN-split images with polygons.")
    net = UNetResNet18(pretrained=True).to(dev)
    opt = torch.optim.AdamW(net.parameters(), lr=3e-4, weight_decay=1e-4)
    X = torch.stack([it["x"] for it in train]); Y = torch.stack([it["y"] for it in train])
    t0, hist = time.time(), []
    for step in range(1, a.steps + 1):
        idx = torch.randint(0, len(X), (8,))
        x, y = X[idx].clone(), Y[idx].clone()
        if torch.rand(1) < 0.5: x, y = x.flip(3), y.flip(3)
        if torch.rand(1) < 0.5: x, y = x.flip(2), y.flip(2)
        k = int(torch.randint(0, 4, (1,)))
        x, y = torch.rot90(x, k, (2, 3)), torch.rot90(y, k, (2, 3))
        x = x * (1 + 0.15 * (torch.rand(len(x), 1, 1, 1) - 0.5))  # brightness jitter
        x, y = x.to(dev), y.to(dev)
        logit = net(x)
        p = torch.sigmoid(logit)
        dice = 1 - (2 * (p * y).sum((2, 3)) + 1) / (p.sum((2, 3)) + y.sum((2, 3)) + 1)
        loss = 0.5 * Fnn.binary_cross_entropy_with_logits(logit, y) + 0.5 * dice.mean()
        opt.zero_grad(); loss.backward(); opt.step()
        if step % 50 == 0:
            hist.append({"step": step, "loss": float(loss)}); print(hist[-1], flush=True)
    net.eval()
    per = []
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    show = test if test else train[:3]
    fig, axes = plt.subplots(len(show), 3, figsize=(7.5, 2.6 * len(show)), squeeze=False)
    for r, it in enumerate(show):
        with torch.no_grad():
            pr = torch.sigmoid(net(it["x"][None].to(dev)))[0].cpu().numpy() > 0.5
        gt = it["y"].numpy() > 0.5
        df, jf = dice_iou(pr[0], gt[0]); dd, jd = dice_iou(pr[1], gt[1])
        cov_gt = float(gt[1].sum() / max(gt[0].sum(), 1)); cov_pr = float((pr[1] & pr[0]).sum() / max(pr[0].sum(), 1))
        per.append({"annotation_id": it["m"]["annotation_id"], "produce": it["m"]["produce_class"], "split": it["m"]["split"],
                    "fruit_dice": df, "fruit_iou": jf, "decay_dice": dd, "decay_iou": jd,
                    "decay_coverage_gt_pct": round(100 * cov_gt, 1), "decay_coverage_pred_pct": round(100 * cov_pr, 1)})
        base = np.asarray(it["img"].resize((SIZE, SIZE)), np.float32) / 255
        def ov(mk):
            o = base.copy(); o[mk[0]] = 0.6 * o[mk[0]] + 0.4 * np.array([0.18, 0.42, 0.31]); o[mk[1]] = 0.4 * o[mk[1]] + 0.6 * np.array([0.9, 0.3, 0.1]); return o
        axes[r, 0].imshow(base); axes[r, 1].imshow(ov(gt)); axes[r, 2].imshow(ov(pr))
        axes[r, 0].set_title(f"{it['m']['annotation_id']} ({it['m']['produce_class']})", fontsize=7)
        axes[r, 1].set_title("human mask", fontsize=7); axes[r, 2].set_title(f"U-Net: decay Dice {dd:.2f}", fontsize=7)
        for ax in axes[r]: ax.axis("off")
    fig.suptitle("PILOT U-Net — " + ("held-out annotated images" if test else "TRAIN images (no held-out masks)") + " (green fruit, orange decay)", fontsize=8)
    fig.tight_layout(); fig.savefig(OUT / "test_overlays.png", dpi=130); plt.close(fig)
    mean = lambda k: float(np.mean([p[k] for p in per])) if per else None  # noqa: E731
    res = {"status": ("PILOT — trained on very few human masks; demonstrates the pipeline, not a validated model" if a.mask_source == "human" else
                      "PILOT — trained on MACHINE-GENERATED masks (colour/darkness heuristics gated by human image-level decay decisions); "
                      "metrics measure agreement with those machine masks, not with human-drawn ground truth"),
           "mask_source": a.mask_source,
           "n_annotated": len(items), "n_train": len(train), "n_eval": len(test),
           "eval_images_are_held_out": bool(test), "train_ids": [it["m"]["annotation_id"] for it in train],
           "steps": a.steps, "train_seconds": round(time.time() - t0, 1), "input_size": SIZE, "loss": "0.5 BCE + 0.5 soft Dice",
           "encoder": "ResNet-18 (ImageNet weights)", "history": hist, "per_image": per,
           "mean": {k: mean(k) for k in ("fruit_dice", "fruit_iou", "decay_dice", "decay_iou")}}
    save_json(res, OUT / "results.json")
    torch.save({"state_dict": net.state_dict(), "size": SIZE, "mean": MEAN.tolist(), "std": STD.tolist(),
                "channels": ["fruit", "decay"], "n_train_masks": len(train), "status": "pilot", "mask_source": a.mask_source,
                "eval_mean": res["mean"], "n_eval": len(test)}, OUT / "unet_pilot.pt")
    shutil.copy(OUT / "unet_pilot.pt", ROOT / "backend/models/unet_pilot.pt")
    print(json.dumps({k: res[k] for k in ("n_annotated", "n_train", "n_eval", "mean")}, indent=1))


if __name__ == "__main__":
    main()
