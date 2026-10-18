"""
shelf_life_proxy.py — PROXY shelf-life regressor: "days until the TR-6 'Spoiled' label".

TR-6 has no measured time-to-endpoint labels. Each produce series is photographed over
consecutive days and its folder label switches from Not_spoiled to Spoiled at a known
date, so a proxy target can be derived:
    target_days = max(0, (first Spoiled capture of that produce - capture time) / 1 day)
This is a PROXY derived from dataset labels, not independently observed remaining shelf life.

Model: ridge regression on the frozen 768-d CLS embedding of the deployed ViT-B/16
(alpha selected on validation MAE); predictions clipped to [0, max train target].
Split v1 (train/val/test) is reused; the test set is evaluated once.
Outputs: artifacts/experiments/shelf_life_proxy/{results.json, predictions.csv, *.png}
         backend/models/shelf_life_proxy.json (numpy-only parameters)
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml")); sys.path.insert(0, str(ROOT / "ml/evaluate"))
from common import PRODUCE_CLASSES, build_transforms, pick_device, save_json  # noqa: E402
from evaluate_vit import load_model  # noqa: E402

RUN = ROOT / "artifacts/runs/vit_b16_primary"
OUT = ROOT / "artifacts/experiments/shelf_life_proxy"


def main():
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler
    OUT.mkdir(parents=True, exist_ok=True)
    rows = [r for r in csv.DictReader(open(ROOT / "artifacts/dataset/v1/split_manifest.csv")) if r["split"] in ("train", "val", "test")]
    ts = lambda r: dt.datetime.fromisoformat(r["capture_timestamp"])  # noqa: E731
    onset = {p: min(ts(r) for r in rows if r["produce_class"] == p and r["source_label"] == "Spoiled") for p in PRODUCE_CLASSES}
    y = np.array([max(0.0, (onset[r["produce_class"]] - ts(r)).total_seconds() / 86400) for r in rows], np.float32)
    dev = pick_device()
    model, cfg, ck = load_model(RUN, dev)
    tf = build_transforms(cfg["mean"], cfg["std"], train=False)
    feats = []
    with torch.no_grad():
        for i in range(0, len(rows), 64):
            x = torch.stack([tf(Image.open(ROOT / "artifacts/cache/srgb_256" / f"{r['sha256']}.jpg").convert("RGB")) for r in rows[i:i + 64]]).to(dev)
            feats.append(model.backbone(x).cpu().numpy())
    X = np.concatenate(feats)
    sp = np.array([r["split"] for r in rows])
    tr, va, te = (np.where(sp == s)[0] for s in ("train", "val", "test"))
    sc = StandardScaler().fit(X[tr])
    cap = float(y[tr].max())
    mae = lambda a, b: float(np.mean(np.abs(a - b)))  # noqa: E731
    sweep, best = [], None
    for alpha in (1, 10, 100, 1000, 10000):
        reg = Ridge(alpha=alpha).fit(sc.transform(X[tr]), y[tr])
        e = mae(np.clip(reg.predict(sc.transform(X[va])), 0, cap), y[va])
        sweep.append({"alpha": alpha, "val_mae_days": e})
        if best is None or e < best[0]:
            best = (e, alpha, reg)
    _, alpha, reg = best
    pred = np.clip(reg.predict(sc.transform(X)), 0, cap)

    def metrics(idx):
        e = pred[idx] - y[idx]
        ss = float(((y[idx] - y[idx].mean()) ** 2).sum())
        return {"n": int(len(idx)), "mae_days": float(np.mean(np.abs(e))), "rmse_days": float(np.sqrt(np.mean(e ** 2))),
                "r2": float(1 - (e ** 2).sum() / ss) if ss else None,
                "mae_not_yet_spoiled_days": float(np.mean(np.abs(e[y[idx] > 0]))) if (y[idx] > 0).any() else None}
    base = np.array([np.mean(y[tr][[rows[i]["produce_class"] == rows[j]["produce_class"] for i in tr]]) for j in range(len(rows))])
    res = {"target": "PROXY: days until the produce series' first TR-6 'Spoiled' capture (0 once spoiled); not measured shelf life",
           "spoilage_label_onset": {p: v.isoformat() for p, v in onset.items()},
           "target_range_days": [float(y.min()), float(y.max())], "model": "StandardScaler + Ridge on frozen deployed ViT-B/16 CLS embedding",
           "alpha_grid_val": sweep, "alpha_selected": alpha, "clip_days": [0, cap],
           "val": metrics(va), "test": metrics(te),
           "baseline_test_mae_days_per_produce_mean": float(np.mean(np.abs(base[te] - y[te]))),
           "per_produce_test": {p: {"n": int(sum(rows[i]["produce_class"] == p for i in te)),
                                    "mae_days": float(np.mean([abs(pred[i] - y[i]) for i in te if rows[i]["produce_class"] == p]))} for p in PRODUCE_CLASSES},
           "limitations": ["Each produce is a single storage series of a few specimens; the model can learn date-specific appearance.",
                           "Target is derived from the dataset's folder labels, which are date-based and not independently verified.",
                           "Same specimens appear in train and test (no specimen IDs)."]}
    save_json(res, OUT / "results.json")
    with open(OUT / "predictions.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["sample_id", "split", "produce", "label", "target_days", "pred_days"])
        for r, a, b in zip(rows, y, pred):
            w.writerow([r["sample_id"], r["split"], r["produce_class"], r["source_label"], f"{a:.2f}", f"{b:.2f}"])
    save_json({"name": "shelf-life-proxy", "version": f"ridge_a{alpha}_on_{RUN.name}@epoch{ck['epoch']}", "backbone_checkpoint": RUN.name,
               "mean": sc.mean_.tolist(), "scale": sc.scale_.tolist(), "coef": reg.coef_.tolist(), "intercept": float(reg.intercept_),
               "clip": [0, cap], "target": res["target"], "test_metrics": res["test"]}, OUT / "shelf_life_proxy.json")
    shutil.copy(OUT / "shelf_life_proxy.json", ROOT / "backend/models/shelf_life_proxy.json")
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(8.5, 3.4))
    cols = dict(zip(PRODUCE_CLASSES, ["#C9A227", "#E07B39", "#6A994E", "#386641", "#F4A259", "#BC4749"]))
    for p in PRODUCE_CLASSES:
        idx = [i for i in te if rows[i]["produce_class"] == p]
        axes[0].scatter(y[idx], pred[idx], s=8, c=cols[p], label=p.replace("Indian_", ""))
    axes[0].plot([0, cap], [0, cap], ":", c="grey"); axes[0].set_xlabel("proxy target (days to 'Spoiled' label)"); axes[0].set_ylabel("predicted days")
    axes[0].legend(fontsize=6); axes[0].set_title(f"Test: MAE {res['test']['mae_days']:.2f} d, R² {res['test']['r2']:.2f}", fontsize=8)
    axes[1].hist(pred[te] - y[te], bins=40, color="#2F6B4F"); axes[1].set_xlabel("residual (days)"); axes[1].set_title("Test residuals", fontsize=8)
    fig.suptitle("PROXY shelf-life regression (days until TR-6 'Spoiled' label)", fontsize=9)
    fig.tight_layout(); fig.savefig(OUT / "pred_vs_target.png", dpi=140); plt.close(fig)
    print(json.dumps({k: res[k] for k in ("target_range_days", "alpha_selected", "val", "test", "baseline_test_mae_days_per_produce_mean")}, indent=1))


if __name__ == "__main__":
    main()
