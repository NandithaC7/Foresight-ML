"""
gan.py — class-conditional DCGAN (64x64) for training-only augmentation (research).

  * Trained ONLY on train-split images; 12 conditions = produce x spoilage.
  * Generated images are written to artifacts/experiments/gan/generated/ with a
    manifest marking them synthetic; they are never used for val/test.
  * Memorisation check: for each generated image, L2 distance (64x64 pixels) to
    its nearest training image of the same condition, compared with the
    nearest-neighbour distance between distinct training images.

Usage:
  .venv/bin/python ml/experiments/gan.py train --minutes 10
  .venv/bin/python ml/experiments/gan.py generate --per-class 40
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml"))
from common import PRODUCE_CLASSES, SPOILAGE_CLASSES, load_split_rows, pick_device, save_json, seed_everything  # noqa: E402

OUT = ROOT / "artifacts/experiments/gan"
NZ, NC, RES = 100, len(PRODUCE_CLASSES) * len(SPOILAGE_CLASSES), 64


class G(nn.Module):
    def __init__(self, ngf=64):
        super().__init__()
        self.emb = nn.Embedding(NC, 50)
        self.net = nn.Sequential(
            nn.ConvTranspose2d(NZ + 50, ngf * 8, 4, 1, 0, bias=False), nn.BatchNorm2d(ngf * 8), nn.ReLU(True),
            nn.ConvTranspose2d(ngf * 8, ngf * 4, 4, 2, 1, bias=False), nn.BatchNorm2d(ngf * 4), nn.ReLU(True),
            nn.ConvTranspose2d(ngf * 4, ngf * 2, 4, 2, 1, bias=False), nn.BatchNorm2d(ngf * 2), nn.ReLU(True),
            nn.ConvTranspose2d(ngf * 2, ngf, 4, 2, 1, bias=False), nn.BatchNorm2d(ngf), nn.ReLU(True),
            nn.ConvTranspose2d(ngf, 3, 4, 2, 1, bias=False), nn.Tanh())

    def forward(self, z, c):
        return self.net(torch.cat([z, self.emb(c)], 1)[:, :, None, None])


class D(nn.Module):
    def __init__(self, ndf=64):
        super().__init__()
        self.emb = nn.Embedding(NC, RES * RES)
        self.net = nn.Sequential(
            nn.Conv2d(4, ndf, 4, 2, 1, bias=False), nn.LeakyReLU(0.2, True),
            nn.Conv2d(ndf, ndf * 2, 4, 2, 1, bias=False), nn.BatchNorm2d(ndf * 2), nn.LeakyReLU(0.2, True),
            nn.Conv2d(ndf * 2, ndf * 4, 4, 2, 1, bias=False), nn.BatchNorm2d(ndf * 4), nn.LeakyReLU(0.2, True),
            nn.Conv2d(ndf * 4, ndf * 8, 4, 2, 1, bias=False), nn.BatchNorm2d(ndf * 8), nn.LeakyReLU(0.2, True),
            nn.Conv2d(ndf * 8, 1, 4, 1, 0, bias=False))

    def forward(self, x, c):
        return self.net(torch.cat([x, self.emb(c).view(-1, 1, RES, RES)], 1)).view(-1)


def cond(r):
    return PRODUCE_CLASSES.index(r["produce_class"]) * 2 + SPOILAGE_CLASSES.index(r["source_label"])


def load_train(args):
    rows = load_split_rows(args.manifest, "train")
    X = np.stack([np.asarray(Image.open(Path(args.cache) / f"{r['sha256']}.jpg").convert("RGB").resize((RES, RES), Image.BICUBIC),
                             dtype=np.float32) / 127.5 - 1 for r in rows])
    return torch.from_numpy(X).permute(0, 3, 1, 2), torch.tensor([cond(r) for r in rows])


def train(args):
    seed_everything(args.seed)
    dev = pick_device()
    X, C = load_train(args)
    g, d = G().to(dev), D().to(dev)
    og = torch.optim.Adam(g.parameters(), 2e-4, betas=(0.5, 0.999))
    od = torch.optim.Adam(d.parameters(), 2e-4, betas=(0.5, 0.999))
    bce = nn.BCEWithLogitsLoss()
    hist, t_end, ep = [], time.time() + args.minutes * 60, 0
    zfix = torch.randn(NC * 4, NZ, device=dev)
    cfix = torch.arange(NC, device=dev).repeat_interleave(4)
    while time.time() < t_end and ep < args.max_epochs:
        ep += 1
        perm = torch.randperm(len(X))
        ld, lg = [], []
        for i in range(0, len(X) - 63, 64):
            idx = perm[i:i + 64]
            x = X[idx].to(dev); c = C[idx].to(dev)
            if torch.rand(1).item() < 0.5:
                x = x.flip(3)
            z = torch.randn(len(x), NZ, device=dev)
            fake = g(z, c)
            lossd = bce(d(x, c), torch.full((len(x),), 0.9, device=dev)) + bce(d(fake.detach(), c), torch.zeros(len(x), device=dev))
            od.zero_grad(); lossd.backward(); od.step()
            lossg = bce(d(fake, c), torch.ones(len(x), device=dev))
            og.zero_grad(); lossg.backward(); og.step()
            ld.append(lossd.item()); lg.append(lossg.item())
        hist.append({"epoch": ep, "loss_d": float(np.mean(ld)), "loss_g": float(np.mean(lg))})
        print(hist[-1], flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    torch.save({"g": g.state_dict(), "d": d.state_dict(), "epochs": ep, "seed": args.seed}, OUT / "cdcgan.pt")
    g.eval()
    with torch.no_grad():
        s = g(zfix, cfix).cpu()
    grid = ((s.permute(0, 2, 3, 1).numpy() + 1) * 127.5).clip(0, 255).astype(np.uint8)
    sheet = np.concatenate([np.concatenate(list(grid[r * 4:(r + 1) * 4]), 1) for r in range(NC)], 0)
    Image.fromarray(sheet).save(OUT / "samples_grid_rows_by_condition.png")
    save_json({"history": hist, "epochs": ep, "minutes_budget": args.minutes, "train_images": len(X),
               "resolution": RES, "conditions": [f"{p}/{s}" for p in PRODUCE_CLASSES for s in SPOILAGE_CLASSES],
               "label_smoothing_real": 0.9, "optimizer": "Adam 2e-4 betas(0.5,0.999)", "batch": 64, "seed": args.seed},
              OUT / "train_summary.json")


def generate(args):
    seed_everything(args.seed + 1)
    dev = pick_device()
    g = G().to(dev); g.load_state_dict(torch.load(OUT / "cdcgan.pt", map_location="cpu")["g"]); g.eval()
    X, C = load_train(args)
    Xf = X.reshape(len(X), -1).numpy()
    gen_dir = OUT / "generated"; gen_dir.mkdir(parents=True, exist_ok=True)
    rows, nn_gen = [], []
    for c in range(NC):
        with torch.no_grad():
            s = g(torch.randn(args.per_class, NZ, device=dev), torch.full((args.per_class,), c, device=dev)).cpu()
        same = Xf[(C == c).numpy()]
        for k, im in enumerate(s):
            dist = np.sqrt(((same - im.reshape(-1).numpy()) ** 2).sum(1)).min()
            nn_gen.append(float(dist))
            arr = ((im.permute(1, 2, 0).numpy() + 1) * 127.5).clip(0, 255).astype(np.uint8)
            p = gen_dir / f"gan_c{c:02d}_{k:03d}.jpg"
            # Upsampled to the cache resolution so the ViT pipeline can read it; detail is still 64x64.
            Image.fromarray(arr).resize((256, 256), Image.BICUBIC).save(p, quality=95)
            rows.append({"path": str(p), "produce_class": PRODUCE_CLASSES[c // 2], "source_label": SPOILAGE_CLASSES[c % 2],
                         "provenance": "synthetic_cdcgan_train_only", "condition": c, "seed": args.seed + 1,
                         "nn_l2_to_train_same_condition": round(float(dist), 3)})
    with open(OUT / "generated_manifest.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    # baseline: NN distance between distinct real training images (same condition), sampled
    rng = np.random.default_rng(0)
    nn_real = []
    for i in rng.choice(len(Xf), 300, replace=False):
        same = np.where((C == C[i]).numpy())[0]; same = same[same != i]
        nn_real.append(float(np.sqrt(((Xf[same] - Xf[i]) ** 2).sum(1)).min()))
    save_json({"generated": len(rows), "per_class": args.per_class,
               "nn_l2_generated_to_train": {"mean": float(np.mean(nn_gen)), "min": float(np.min(nn_gen)), "median": float(np.median(nn_gen))},
               "nn_l2_train_to_train": {"mean": float(np.mean(nn_real)), "min": float(np.min(nn_real)), "median": float(np.median(nn_real))},
               "interpretation": "If generated NN distances were far below real-real NN distances, that would suggest memorisation. "
                                 "Real-real distances are small because TR-6 has 17 near-identical views per session."},
              OUT / "generation_summary.json")
    print(open(OUT / "generation_summary.json").read())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["train", "generate"])
    ap.add_argument("--manifest", default=str(ROOT / "artifacts/dataset/v1/split_manifest.csv"))
    ap.add_argument("--cache", default=str(ROOT / "artifacts/cache/srgb_256"))
    ap.add_argument("--minutes", type=float, default=10)
    ap.add_argument("--max-epochs", type=int, default=200)
    ap.add_argument("--per-class", type=int, default=40)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    {"train": train, "generate": generate}[a.cmd](a)
