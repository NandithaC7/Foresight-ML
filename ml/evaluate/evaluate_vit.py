"""
evaluate_vit.py — evaluate a saved checkpoint on a split, optionally under a
deterministic corruption and optional denoiser. Used once on the test split
after model selection; corrupted copies are generated in memory (never written
into training data).

Examples:
  .venv/bin/python ml/evaluate/evaluate_vit.py --run artifacts/runs/vit_b16_e1 --split test
  .venv/bin/python ml/evaluate/evaluate_vit.py --run artifacts/runs/vit_b16_e1 --split test \
      --corruption gaussian --level 0.1 --denoiser median
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import sys
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml"))
from common import (PRODUCE_CLASSES, SPOILAGE_CLASSES, IMG_SIZE, ForesightViT, build_transforms,  # noqa: E402
                    classification_metrics, corrupt, load_split_rows, pick_device, save_json)


def load_model(run: Path, device):
    ck = torch.load(run / "best.pt", map_location="cpu", weights_only=False)
    cfg = ck["config"]
    m = ForesightViT(cfg["backbone"], pretrained=False)
    m.load_state_dict(ck["state_dict"])
    return m.to(device).eval(), cfg, ck


def make_denoiser(name: str | None, device):
    if not name or name == "none":
        return None
    if name == "median":
        return lambda im: im.filter(ImageFilter.MedianFilter(3))
    if name.split(":", 1)[0] in ("dncnn", "dncnn2"):
        from dncnn import load_dncnn  # noqa
        net = load_dncnn(Path(name.split(":", 1)[1]), device)

        def f(im):
            x = torch.from_numpy(np.asarray(im, dtype=np.float32) / 255.0).permute(2, 0, 1)[None].to(device)
            with torch.no_grad():
                y = (x - net(x)).clamp(0, 1)
            return Image.fromarray((y[0].permute(1, 2, 0).cpu().numpy() * 255).round().astype(np.uint8))
        return f
    raise ValueError(name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", type=Path, required=True)
    ap.add_argument("--split", default="test", choices=["val", "test"])
    ap.add_argument("--manifest", default=str(ROOT / "artifacts/dataset/v1/split_manifest.csv"))
    ap.add_argument("--cache", default=str(ROOT / "artifacts/cache/srgb_256"))
    ap.add_argument("--corruption", default="clean")
    ap.add_argument("--level", type=float, default=0.0)
    ap.add_argument("--denoiser", default="none")
    ap.add_argument("--tag", default=None)
    ap.add_argument("--device", default="auto")
    ap.add_argument("--batch-size", type=int, default=64)
    args = ap.parse_args()

    sys.path.insert(0, str(ROOT / "ml" / "experiments"))
    device = pick_device(args.device)
    model, cfg, ck = load_model(args.run, device)
    tf = build_transforms(cfg["mean"], cfg["std"], train=False)
    den = make_denoiser(args.denoiser, device)
    rows = load_split_rows(args.manifest, args.split)

    ids, yt, ys, pts, pss = [], [], [], [], []
    batch, latencies = [], []

    def flush():
        x = torch.stack([b[0] for b in batch]).to(device)
        t0 = time.perf_counter()
        with torch.no_grad():
            lt, ls = model(x)
            pt, ps = lt.softmax(1).cpu(), ls.softmax(1).cpu()
        latencies.append((time.perf_counter() - t0) / len(batch))
        for (_, r), a, b in zip(batch, pt, ps):
            ids.append(r["sample_id"]); yt.append(PRODUCE_CLASSES.index(r["produce_class"]))
            ys.append(SPOILAGE_CLASSES.index(r["source_label"])); pts.append(a.numpy()); pss.append(b.numpy())
        batch.clear()

    for r in rows:
        im = Image.open(Path(args.cache) / f"{r['sha256']}.jpg").convert("RGB")
        if args.corruption != "clean":
            seed = int(hashlib.sha256(f"{r['sha256']}|{args.corruption}|{args.level}".encode()).hexdigest()[:8], 16)
            im = corrupt(im, args.corruption, args.level, seed)
        if den is not None:
            im = den(im.resize((IMG_SIZE, IMG_SIZE), Image.BILINEAR))
        batch.append((tf(im), r))
        if len(batch) == args.batch_size:
            flush()
    if batch:
        flush()

    pt, ps = np.stack(pts), np.stack(pss)
    tag = args.tag or f"{args.split}_{args.corruption}_{args.level:g}_{args.denoiser.split(':')[0]}"
    res = {
        "run": str(args.run.relative_to(ROOT)) if args.run.is_absolute() else str(args.run),
        "split": args.split, "corruption": args.corruption, "level": args.level, "denoiser": args.denoiser,
        "checkpoint_epoch": ck["epoch"], "backbone": cfg["backbone"], "device": str(device),
        "type": classification_metrics(yt, pt.argmax(1), pt, PRODUCE_CLASSES),
        "spoil": classification_metrics(ys, ps.argmax(1), ps, SPOILAGE_CLASSES),
        "mean_batched_latency_ms_per_image": float(np.mean(latencies) * 1000),
        "note": "Confidence values are softmax scores, not calibrated probabilities.",
    }
    res["composite_macro_f1"] = (res["type"]["macro_f1"] + res["spoil"]["macro_f1"]) / 2
    out_dir = args.run / "eval"
    save_json(res, out_dir / f"{tag}.json")
    with open(out_dir / f"{tag}_predictions.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["sample_id", "true_type", "pred_type", "p_type_max", "true_spoil", "pred_spoil", "p_spoiled"])
        for i in range(len(ids)):
            w.writerow([ids[i], PRODUCE_CLASSES[yt[i]], PRODUCE_CLASSES[pt[i].argmax()], f"{pt[i].max():.4f}",
                        SPOILAGE_CLASSES[ys[i]], SPOILAGE_CLASSES[ps[i].argmax()], f"{ps[i][1]:.4f}"])
    print(f"{tag}: type acc={res['type']['accuracy']:.4f} mF1={res['type']['macro_f1']:.4f} | "
          f"spoil acc={res['spoil']['accuracy']:.4f} mF1={res['spoil']['macro_f1']:.4f} "
          f"AUC={res['spoil'].get('roc_auc', float('nan')):.4f}")


if __name__ == "__main__":
    main()
