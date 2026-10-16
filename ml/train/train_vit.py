"""
train_vit.py — fine-tune a pretrained ViT with two heads (produce type, spoilage).

Loss: L = lambda_type * CE(y_type, p_type) + lambda_spoil * CE(y_spoil, p_spoil)
Selection: best validation composite = mean(macro-F1_type, macro-F1_spoilage);
early stopping on that composite. The test split is never read here.

Example:
  .venv/bin/python ml/train/train_vit.py --run-id vit_b16_e1 \
      --backbone vit_base_patch16_224.augreg2_in21k_ft_in1k --epochs 12
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import platform
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml"))
from common import (PRODUCE_CLASSES, SPOILAGE_CLASSES, IMG_SIZE, ForesightViT, TR6Dataset,  # noqa: E402
                    build_transforms, classification_metrics, load_split_rows, norm_stats,
                    pick_device, save_json, seed_everything)


def run_epoch(model, loader, device, opt=None, sched=None, lam=(1.0, 1.0), max_batches=None):
    train = opt is not None
    model.train(train)
    ce = nn.CrossEntropyLoss()
    tot, n = 0.0, 0
    yt_all, ys_all, pt_all, ps_all, ids = [], [], [], [], []
    with torch.set_grad_enabled(train):
        for b, (x, yt, ys, sid) in enumerate(loader):
            if max_batches and b >= max_batches:
                break
            x, yt, ys = x.to(device), yt.to(device), ys.to(device)
            lt, ls = model(x)
            loss = lam[0] * ce(lt, yt) + lam[1] * ce(ls, ys)
            if train:
                opt.zero_grad(set_to_none=True)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                opt.step()
                sched.step()
            tot += loss.item() * x.size(0)
            n += x.size(0)
            yt_all += yt.tolist(); ys_all += ys.tolist(); ids += list(sid)
            pt_all.append(lt.softmax(1).detach().cpu()); ps_all.append(ls.softmax(1).detach().cpu())
    pt, ps = torch.cat(pt_all).numpy(), torch.cat(ps_all).numpy()
    mt = classification_metrics(yt_all, pt.argmax(1), pt, PRODUCE_CLASSES)
    ms = classification_metrics(ys_all, ps.argmax(1), ps, SPOILAGE_CLASSES)
    return {"loss": tot / max(n, 1), "type": mt, "spoil": ms,
            "composite_macro_f1": (mt["macro_f1"] + ms["macro_f1"]) / 2,
            "_preds": (ids, yt_all, pt, ys_all, ps)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--manifest", default=str(ROOT / "artifacts/dataset/v1/split_manifest.csv"))
    ap.add_argument("--cache", default=str(ROOT / "artifacts/cache/srgb_256"))
    ap.add_argument("--out-root", default=str(ROOT / "artifacts/runs"))
    ap.add_argument("--backbone", default="vit_base_patch16_224.augreg2_in21k_ft_in1k")
    ap.add_argument("--epochs", type=int, default=12)
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--head-lr", type=float, default=2e-4)
    ap.add_argument("--weight-decay", type=float, default=0.01)
    ap.add_argument("--warmup-epochs", type=float, default=1.0)
    ap.add_argument("--patience", type=int, default=4)
    ap.add_argument("--aug", choices=["none", "conventional"], default="conventional")
    ap.add_argument("--freeze-backbone", action="store_true", help="linear-probe baseline")
    ap.add_argument("--extra-train-csv", default=None, help="CSV path,produce_class,source_label (train-only synthetic)")
    ap.add_argument("--lambda-type", type=float, default=1.0)
    ap.add_argument("--lambda-spoil", type=float, default=1.0)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--device", default="auto")
    ap.add_argument("--max-batches", type=int, default=None, help="pilot/dry-run limit")
    args = ap.parse_args()

    seed_everything(args.seed)
    device = pick_device(args.device)
    out = Path(args.out_root) / args.run_id
    out.mkdir(parents=True, exist_ok=True)
    mean, std = norm_stats(args.backbone)

    train_rows = load_split_rows(args.manifest, "train")
    val_rows = load_split_rows(args.manifest, "val")
    extra = None
    if args.extra_train_csv:
        extra = [(Path(r["path"]), PRODUCE_CLASSES.index(r["produce_class"]),
                  SPOILAGE_CLASSES.index(r["source_label"]), "synthetic:" + Path(r["path"]).name)
                 for r in csv.DictReader(open(args.extra_train_csv))]
    tr_ds = TR6Dataset(train_rows, args.cache, build_transforms(mean, std, True, args.aug), extra)
    va_ds = TR6Dataset(val_rows, args.cache, build_transforms(mean, std, False))
    g = torch.Generator().manual_seed(args.seed)
    tr_dl = DataLoader(tr_ds, args.batch_size, shuffle=True, num_workers=args.workers, generator=g,
                       persistent_workers=args.workers > 0, drop_last=True)
    va_dl = DataLoader(va_ds, 64, shuffle=False, num_workers=args.workers, persistent_workers=args.workers > 0)

    model = ForesightViT(args.backbone, pretrained=True).to(device)
    if args.freeze_backbone:
        for p in model.backbone.parameters():
            p.requires_grad = False
    head_params = list(model.head_type.parameters()) + list(model.head_spoil.parameters())
    groups = [{"params": head_params, "lr": args.head_lr}]
    if not args.freeze_backbone:
        groups.append({"params": model.backbone.parameters(), "lr": args.lr})
    opt = torch.optim.AdamW(groups, weight_decay=args.weight_decay)
    steps_per_epoch = min(len(tr_dl), args.max_batches or len(tr_dl))
    total, warm = steps_per_epoch * args.epochs, int(steps_per_epoch * args.warmup_epochs)
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: (s + 1) / max(1, warm) if s < warm else 0.5 * (1 + math.cos(math.pi * (s - warm) / max(1, total - warm))))

    config = {**vars(args), "device": str(device), "img_size": IMG_SIZE, "mean": mean, "std": std,
              "produce_classes": PRODUCE_CLASSES, "spoilage_classes": SPOILAGE_CLASSES,
              "n_train": len(tr_ds), "n_train_real": len(train_rows), "n_val": len(va_ds),
              "manifest_sha256": hashlib.sha256(Path(args.manifest).read_bytes()).hexdigest(),
              "torch": torch.__version__, "python": platform.python_version(), "platform": platform.platform(),
              "selection_metric": "val composite macro-F1 = mean(type macro-F1, spoilage macro-F1)",
              "scheduler": "linear warm-up then cosine decay (per step)",
              "started_at": dt.datetime.now().isoformat(timespec="seconds")}
    import timm
    config["timm"] = timm.__version__
    save_json(config, out / "config.json")

    history, best, bad_epochs = [], -1.0, 0
    log = open(out / "train_log.txt", "a")
    for ep in range(1, args.epochs + 1):
        t0 = time.time()
        tr = run_epoch(model, tr_dl, device, opt, sched, (args.lambda_type, args.lambda_spoil), args.max_batches)
        va = run_epoch(model, va_dl, device, max_batches=args.max_batches)
        rec = {"epoch": ep, "seconds": round(time.time() - t0, 1),
               "train_loss": tr["loss"], "val_loss": va["loss"],
               "train_type_acc": tr["type"]["accuracy"], "train_spoil_acc": tr["spoil"]["accuracy"],
               "val_type_acc": va["type"]["accuracy"], "val_spoil_acc": va["spoil"]["accuracy"],
               "val_type_macro_f1": va["type"]["macro_f1"], "val_spoil_macro_f1": va["spoil"]["macro_f1"],
               "val_composite_macro_f1": va["composite_macro_f1"]}
        history.append(rec)
        line = json.dumps(rec)
        print(line, flush=True); log.write(line + "\n"); log.flush()
        save_json(history, out / "history.json")
        if va["composite_macro_f1"] > best:
            best, bad_epochs = va["composite_macro_f1"], 0
            torch.save({"state_dict": model.state_dict(), "config": config, "epoch": ep,
                        "val_metrics": {"type": va["type"], "spoil": va["spoil"],
                                        "composite_macro_f1": va["composite_macro_f1"]}}, out / "best.pt")
            ids, yt, pt, ys, ps = va["_preds"]
            with open(out / "val_predictions_best.csv", "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["sample_id", "true_type", "pred_type", "p_type_max", "true_spoil", "pred_spoil", "p_spoiled"])
                for i in range(len(ids)):
                    w.writerow([ids[i], PRODUCE_CLASSES[yt[i]], PRODUCE_CLASSES[pt[i].argmax()], f"{pt[i].max():.4f}",
                                SPOILAGE_CLASSES[ys[i]], SPOILAGE_CLASSES[ps[i].argmax()], f"{ps[i][1]:.4f}"])
        else:
            bad_epochs += 1
            if bad_epochs >= args.patience:
                print(f"early stop at epoch {ep}", flush=True); log.write(f"early stop at epoch {ep}\n")
                break
    config["finished_at"] = dt.datetime.now().isoformat(timespec="seconds")
    config["best_val_composite_macro_f1"] = best
    config["best_epoch"] = max(history, key=lambda r: r["val_composite_macro_f1"])["epoch"]
    config["epochs_run"] = len(history)
    save_json(config, out / "config.json")
    with open(out / "history.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(history[0].keys()))
        w.writeheader(); w.writerows(history)
    print("best val composite macro-F1", best)


if __name__ == "__main__":
    main()
