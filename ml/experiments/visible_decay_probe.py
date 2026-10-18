"""
visible_decay_probe.py — "visible decay" image-level model trained on HUMAN labels.

Labels: 165 definite human decisions (annotated_has_decay=1 / annotated_no_visible_decay=0)
from Foresight-TR6-plus/unet-annotation/human_visible_decay_labels.csv; 15 'ambiguous' excluded.
Each image keeps its split-v1 partition (train 102 / val 34 / test 29 at export time).

Model: logistic regression on the 768-d CLS embedding of the DEPLOYED ViT-B/16
(frozen; same preprocessing as the API). C selected on validation macro-F1 from a
fixed grid; test evaluated once. Baseline: the deployed spoilage head (p_spoiled >= 0.5)
used directly as a visible-decay predictor.

Outputs: artifacts/experiments/visible_decay/{probe.json, results.json, predictions.csv, *.png}
         and backend/models/visible_decay_probe.json (numpy-only parameters for the API).

Usage: .venv/bin/python ml/experiments/visible_decay_probe.py
"""
from __future__ import annotations

import csv
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml")); sys.path.insert(0, str(ROOT / "ml/evaluate"))
from common import build_transforms, classification_metrics, pick_device, save_json  # noqa: E402
from evaluate_vit import load_model  # noqa: E402

LABELS = ROOT / "Foresight-TR6-plus/unet-annotation/human_visible_decay_labels.csv"
RUN = ROOT / "artifacts/runs/vit_b16_primary"
OUT = ROOT / "artifacts/experiments/visible_decay"
NAMES = ["no_visible_decay", "visible_decay"]


def wilson(k, n, z=1.96):
    if n == 0:
        return [None, None]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [float(c - h), float(c + h)]


def main():
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    OUT.mkdir(parents=True, exist_ok=True)
    rows = [r for r in csv.DictReader(open(LABELS)) if r["visible_decay"] in ("0", "1")]
    dev = pick_device()
    model, cfg, ck = load_model(RUN, dev)
    tf = build_transforms(cfg["mean"], cfg["std"], train=False)
    feats, pspoil = [], []
    with torch.no_grad():
        for i in range(0, len(rows), 32):
            x = torch.stack([tf(Image.open(ROOT / "artifacts/cache/srgb_256" / f"{r['sha256']}.jpg").convert("RGB")) for r in rows[i:i + 32]]).to(dev)
            z = model.backbone(x)
            feats.append(z.cpu().numpy())
            pspoil.append(model.head_spoil(z).softmax(1)[:, 1].cpu().numpy())
    X, ps = np.concatenate(feats), np.concatenate(pspoil)
    y = np.array([int(r["visible_decay"]) for r in rows])
    sp = np.array([r["split"] for r in rows])
    idx = {s: np.where(sp == s)[0] for s in ("train", "val", "test")}

    # model selection on validation only
    sweep, best = [], None
    for C in (0.001, 0.01, 0.1, 1.0, 10.0):
        sc = StandardScaler().fit(X[idx["train"]])
        clf = LogisticRegression(C=C, max_iter=5000, class_weight="balanced").fit(sc.transform(X[idx["train"]]), y[idx["train"]])
        pv = clf.predict_proba(sc.transform(X[idx["val"]]))
        f1 = classification_metrics(y[idx["val"]], pv.argmax(1), pv, NAMES)["macro_f1"]
        sweep.append({"C": C, "val_macro_f1": f1})
        if best is None or f1 > best[0] + 1e-12:
            best = (f1, C, sc, clf)
    f1v, C, sc, clf = best

    res = {"labels_file": str(LABELS.relative_to(ROOT)), "n_definite": int(len(y)),
           "n_by_split": {s: {"n": int(len(v)), "visible_decay": int(y[v].sum())} for s, v in idx.items()},
           "features": f"CLS embedding of deployed {cfg['backbone']} ({RUN.name}@epoch{ck['epoch']}), frozen",
           "classifier": "StandardScaler + LogisticRegression(class_weight=balanced)", "C_grid_val": sweep, "C_selected": C}
    for split in ("val", "test"):
        v = idx[split]
        pp = clf.predict_proba(sc.transform(X[v]))
        m = classification_metrics(y[v], pp.argmax(1), pp, NAMES)
        k = int((pp.argmax(1) == y[v]).sum())
        res[f"probe_{split}"] = m | {"accuracy_95ci_wilson": wilson(k, len(v))}
        pb = np.stack([1 - ps[v], ps[v]], 1)
        mb = classification_metrics(y[v], (ps[v] >= 0.5).astype(int), pb, NAMES)
        kb = int(((ps[v] >= 0.5).astype(int) == y[v]).sum())
        res[f"spoilage_head_as_decay_{split}"] = mb | {"accuracy_95ci_wilson": wilson(kb, len(v))}
    # all-definite agreement of the dataset folder label with human visible decay
    dl = np.array([r["source_label"] == "Spoiled" for r in rows]).astype(int)
    res["dataset_label_vs_human"] = {"agreement": float((dl == y).mean()), "n": int(len(y)),
                                     "spoiled_labelled_with_visible_decay": f"{int(((dl == 1) & (y == 1)).sum())}/{int((dl == 1).sum())}",
                                     "not_spoiled_labelled_with_visible_decay": f"{int(((dl == 0) & (y == 1)).sum())}/{int((dl == 0).sum())}"}
    res["note"] = ("Test set is small (n=%d); treat the confidence intervals as the primary uncertainty. "
                   "Labels are a single annotator's image-level judgements; no pixel masks were drawn." % len(idx["test"]))
    save_json(res, OUT / "results.json")

    # predictions for all definite images (train rows are in-sample)
    allp = clf.predict_proba(sc.transform(X))[:, 1]
    with open(OUT / "predictions.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["annotation_id", "split", "produce", "dataset_label", "human_visible_decay", "p_visible_decay_probe", "p_spoiled_head"])
        for r, a, b in zip(rows, allp, ps):
            w.writerow([r["annotation_id"], r["split"], r["produce_class"], r["source_label"], r["visible_decay"], f"{a:.4f}", f"{b:.4f}"])

    # numpy-only parameters for the backend
    probe = {"name": "visible-decay-probe", "version": f"probe_C{C}_on_{RUN.name}@epoch{ck['epoch']}",
             "backbone_checkpoint": RUN.name, "backbone_epoch": ck["epoch"], "feature": "backbone CLS embedding (pre-dropout)",
             "mean": sc.mean_.tolist(), "scale": sc.scale_.tolist(), "coef": clf.coef_[0].tolist(), "intercept": float(clf.intercept_[0]),
             "threshold": 0.5, "classes": NAMES, "trained_on": f"{len(idx['train'])} human image-level labels (train split)",
             "test_metrics": {k: res["probe_test"][k] for k in ("n", "accuracy", "macro_f1", "roc_auc", "accuracy_95ci_wilson")}}
    save_json(probe, OUT / "probe.json")
    (ROOT / "backend/models").mkdir(exist_ok=True)
    shutil.copy(OUT / "probe.json", ROOT / "backend/models/visible_decay_probe.json")

    # figures
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.2))
    for ax, key, title in ((axes[0], "probe_test", "Visible-decay probe (human labels)"), (axes[1], "spoilage_head_as_decay_test", "Spoilage head used as decay check")):
        cm = np.array(res[key]["confusion_matrix"])
        ax.imshow(cm, cmap="Greens")
        for a in range(2):
            for b in range(2):
                ax.text(b, a, cm[a, b], ha="center", va="center", color="white" if cm[a, b] > cm.max() / 2 else "black")
        ax.set_xticks([0, 1], ["no decay", "decay"]); ax.set_yticks([0, 1], ["no decay", "decay"])
        ax.set_xlabel("predicted"); ax.set_ylabel("human label")
        ax.set_title(f"{title}\nacc {res[key]['accuracy']:.3f}, macro-F1 {res[key]['macro_f1']:.3f}", fontsize=8)
    fig.suptitle(f"Test split (n = {len(idx['test'])}): agreement with human visible-decay labels", fontsize=9)
    fig.tight_layout(); fig.savefig(OUT / "test_confusions.png", dpi=140); plt.close(fig)
    prods = sorted({r["produce_class"] for r in rows})
    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    x = np.arange(len(prods))
    for j, (lab, col) in enumerate((("Spoiled", "#C1622E"), ("Not_spoiled", "#7A8FB0"))):
        vals = []
        for p in prods:
            sel = [r for r in rows if r["produce_class"] == p and r["source_label"] == lab]
            vals.append(sum(int(r["visible_decay"]) for r in sel) / len(sel) if sel else 0)
        ax.bar(x + (j - 0.5) * 0.4, vals, 0.4, color=col, label=f"dataset label: {lab.replace('_', ' ')}")
    ax.set_xticks(x, [p.replace("Indian_Gooseberry", "Gooseberry") for p in prods]); ax.set_ylim(0, 1.05)
    ax.set_ylabel("share judged 'visible decay' by human"); ax.legend(fontsize=7)
    ax.set_title("Human visible-decay judgements vs TR-6 folder labels (165 definite images)", fontsize=9)
    fig.tight_layout(); fig.savefig(OUT / "human_vs_dataset_label.png", dpi=140); plt.close(fig)
    print(json.dumps({k: res[k] for k in ("n_by_split", "C_selected", "dataset_label_vs_human")}, indent=1))
    for k in ("probe_val", "probe_test", "spoilage_head_as_decay_val", "spoilage_head_as_decay_test"):
        print(k, "acc %.3f mF1 %.3f AUC %s CI %s" % (res[k]["accuracy"], res[k]["macro_f1"], res[k].get("roc_auc"), res[k]["accuracy_95ci_wilson"]))


if __name__ == "__main__":
    main()
