"""
dncnn.py — DnCNN residual denoiser experiment (research only, not in the app path).

x_hat = y - R_theta(y). Trained on synthetic clean/noisy pairs cut from TRAIN
split images only (Gaussian sigma sampled from a range plus salt-and-pepper).
PSNR/SSIM are reported on VAL images where the clean reference is known.

Usage:
  .venv/bin/python ml/experiments/dncnn.py train --out artifacts/experiments/dncnn --minutes 12
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml"))
from common import IMG_SIZE, corrupt, load_split_rows, pick_device, save_json, seed_everything  # noqa: E402


class DnCNN(nn.Module):
    def __init__(self, depth: int = 17, width: int = 64, channels: int = 3):
        super().__init__()
        layers = [nn.Conv2d(channels, width, 3, padding=1), nn.ReLU(inplace=True)]
        for _ in range(depth - 2):
            layers += [nn.Conv2d(width, width, 3, padding=1, bias=False), nn.BatchNorm2d(width), nn.ReLU(inplace=True)]
        layers += [nn.Conv2d(width, channels, 3, padding=1)]
        self.net = nn.Sequential(*layers)

    def forward(self, y):  # predicts the residual (noise) R(y)
        return self.net(y)


def load_dncnn(path: Path, device):
    ck = torch.load(path, map_location="cpu", weights_only=False)
    m = DnCNN(**ck["arch"])
    m.load_state_dict(ck["state_dict"])
    return m.to(device).eval()


def load_224(cache, rows):
    return [np.asarray(Image.open(Path(cache) / f"{r['sha256']}.jpg").convert("RGB")
                       .resize((IMG_SIZE, IMG_SIZE), Image.BILINEAR), dtype=np.float32) / 255.0 for r in rows]


def psnr(a, b):
    mse = np.mean((a - b) ** 2)
    return float(10 * np.log10(1.0 / max(mse, 1e-12)))


def train(args):
    seed_everything(args.seed)
    device = pick_device()
    rng = np.random.default_rng(args.seed)
    train_imgs = load_224(args.cache, load_split_rows(args.manifest, "train"))
    val_rows = load_split_rows(args.manifest, "val")
    val_rows = [val_rows[i] for i in np.random.default_rng(0).choice(len(val_rows), 60, replace=False)]
    val_imgs = load_224(args.cache, val_rows)
    net = DnCNN(args.depth, args.width).to(device)
    prior_steps = 0
    if args.init_from:  # resume: continue training an existing checkpoint
        ck = torch.load(args.init_from, map_location="cpu", weights_only=False)
        net.load_state_dict(ck["state_dict"]); prior_steps = int(ck.get("steps", 0))
    opt = torch.optim.Adam(net.parameters(), lr=args.lr)
    P, B = args.patch, args.batch_size
    hist, t_end, step = [], time.time() + args.minutes * 60, 0
    while time.time() < t_end and step < args.max_steps:
        clean = np.stack([train_imgs[i][y:y + P, x:x + P] for i, y, x in zip(
            rng.integers(0, len(train_imgs), B), rng.integers(0, IMG_SIZE - P, B), rng.integers(0, IMG_SIZE - P, B))])
        noisy = clean.copy()
        for k in range(B):
            if rng.random() < 0.7:
                noisy[k] = clean[k] + rng.normal(0, rng.uniform(0.02, 0.2), clean[k].shape)
            else:
                m = rng.random(clean[k].shape[:2]); p = rng.uniform(0.01, 0.1)
                noisy[k][m < p / 2] = 0; noisy[k][(m >= p / 2) & (m < p)] = 1
        noisy = np.clip(noisy, 0, 1)
        c = torch.from_numpy(clean).permute(0, 3, 1, 2).to(device)
        n = torch.from_numpy(noisy).permute(0, 3, 1, 2).float().to(device)
        loss = ((n - net(n)).clamp(0, 1) - c).pow(2).mean()  # L = mean((x_hat - x)^2)
        opt.zero_grad(); loss.backward(); opt.step(); step += 1
        if step % 100 == 0:
            hist.append({"step": step, "train_mse": float(loss.item())})
            print(hist[-1], flush=True)
    args.out.mkdir(parents=True, exist_ok=True)
    torch.save({"state_dict": net.state_dict(), "arch": {"depth": args.depth, "width": args.width},
                "steps": prior_steps + step, "resumed_from": args.init_from, "patch": P, "noise_train": "gaussian sigma~U(0.02,0.2) p=0.7, else s&p p~U(0.01,0.1)"},
               args.out / "dncnn.pt")
    # paired validation PSNR / SSIM on val images (clean reference known)
    from skimage.metrics import structural_similarity as ssim
    net.eval()
    rows = []
    for kind, levels in (("gaussian", [0.05, 0.1, 0.2]), ("salt_pepper", [0.02, 0.05, 0.1])):
        for lvl in levels:
            m = {"noisy_psnr": [], "dncnn_psnr": [], "median_psnr": [], "noisy_ssim": [], "dncnn_ssim": [], "median_ssim": []}
            for i, im in enumerate(val_imgs):
                pil = Image.fromarray((im * 255).round().astype(np.uint8))
                noisy = np.asarray(corrupt(pil, kind, lvl, 1000 + i), dtype=np.float32) / 255.0
                with torch.no_grad():
                    x = torch.from_numpy(noisy).permute(2, 0, 1)[None].to(device)
                    den = (x - net(x)).clamp(0, 1)[0].permute(1, 2, 0).cpu().numpy()
                from PIL import ImageFilter
                med = np.asarray(Image.fromarray((noisy * 255).round().astype(np.uint8)).filter(ImageFilter.MedianFilter(3)),
                                 dtype=np.float32) / 255.0
                for name, arr in (("noisy", noisy), ("dncnn", den), ("median", med)):
                    m[f"{name}_psnr"].append(psnr(arr, im))
                    m[f"{name}_ssim"].append(float(ssim(arr, im, channel_axis=2, data_range=1.0)))
            rows.append({"corruption": kind, "level": lvl, "n_val_images": len(val_imgs),
                         **{k: float(np.mean(v)) for k, v in m.items()}})
            print(rows[-1], flush=True)
    save_json({"history": hist, "steps": prior_steps + step, "steps_this_session": step, "resumed_from": args.init_from, "lr": args.lr, "minutes_budget": args.minutes, "paired_val_quality": rows,
               "note": "Synthetic noise on clean val images; not real sensor noise."}, args.out / "dncnn_results.json")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["train"])
    ap.add_argument("--manifest", default=str(ROOT / "artifacts/dataset/v1/split_manifest.csv"))
    ap.add_argument("--cache", default=str(ROOT / "artifacts/cache/srgb_256"))
    ap.add_argument("--out", type=Path, default=ROOT / "artifacts/experiments/dncnn")
    ap.add_argument("--depth", type=int, default=17)
    ap.add_argument("--width", type=int, default=64)
    ap.add_argument("--patch", type=int, default=64)
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--minutes", type=float, default=12)
    ap.add_argument("--max-steps", type=int, default=100000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--init-from", default=None)
    a = ap.parse_args()
    train(a)
