"""
baselines_kmeans.py — simple baselines (E0) and K-means exploration.

Feature spaces (both documented, neither fitted on val/test):
  colorhist : HSV 3-D histogram, 8x8x8 bins, L1-normalised (512-d)
  vit_frozen: CLS embedding of the ImageNet-pretrained ViT-B/16 (NOT fine-tuned
              on TR-6), 768-d

Commands:
  features  --space colorhist|vit_frozen   -> artifacts/experiments/features/<space>.npz
  probe     --space ...                    -> logistic-regression baseline per head
                                              (C chosen on val; test scored once)
  kmeans    --space ...                    -> K-means fitted on TRAIN only; k chosen
                                              by train silhouette; ARI/NMI vs labels
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml"))
from common import (PRODUCE_CLASSES, SPOILAGE_CLASSES, IMG_SIZE, classification_metrics,  # noqa: E402
                    load_split_rows, save_json)

MANIFEST = ROOT / "artifacts/dataset/v1/split_manifest.csv"
CACHE = ROOT / "artifacts/cache/srgb_256"
FEAT_DIR = ROOT / "artifacts/experiments/features"
OUT = ROOT / "artifacts/experiments"


def colorhist(path):
    im = Image.open(path).convert("RGB").resize((IMG_SIZE, IMG_SIZE)).convert("HSV")
    a = np.asarray(im).reshape(-1, 3) // 32
    h = np.bincount(a[:, 0] * 64 + a[:, 1] * 8 + a[:, 2], minlength=512).astype(np.float32)
    return h / h.sum()


def extract(space):
    out = {}
    if space == "vit_frozen":
        import timm
        import torch
        from common import build_transforms, norm_stats, pick_device
        name = "vit_base_patch16_224.augreg2_in21k_ft_in1k"
        dev = pick_device()
        m = timm.create_model(name, pretrained=True, num_classes=0).to(dev).eval()
        tf = build_transforms(*norm_stats(name), train=False)
    for split in ("train", "val", "test"):
        rows = load_split_rows(MANIFEST, split)
        paths = [CACHE / f"{r['sha256']}.jpg" for r in rows]
        if space == "colorhist":
            X = np.stack([colorhist(p) for p in paths])
        else:
            feats = []
            with torch.no_grad():
                for i in range(0, len(paths), 64):
                    x = torch.stack([tf(Image.open(p).convert("RGB")) for p in paths[i:i + 64]]).to(dev)
                    feats.append(m(x).cpu().numpy())
            X = np.concatenate(feats)
        out[f"X_{split}"] = X
        out[f"yt_{split}"] = np.array([PRODUCE_CLASSES.index(r["produce_class"]) for r in rows])
        out[f"ys_{split}"] = np.array([SPOILAGE_CLASSES.index(r["source_label"]) for r in rows])
    FEAT_DIR.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(FEAT_DIR / f"{space}.npz", **out)
    print(space, {k: v.shape for k, v in out.items() if k.startswith("X")})


def probe(space):
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    d = np.load(FEAT_DIR / f"{space}.npz")
    res = {"space": space, "model": "StandardScaler + LogisticRegression", "selection": "C by val macro-F1"}
    for head, names in (("type", PRODUCE_CLASSES), ("spoil", SPOILAGE_CLASSES)):
        best = None
        for C in (0.01, 0.1, 1.0, 10.0):
            clf = make_pipeline(StandardScaler(), LogisticRegression(C=C, max_iter=3000))
            clf.fit(d["X_train"], d[f"y{head[0]}_train"])
            pv = clf.predict_proba(d["X_val"])
            f1 = classification_metrics(d[f"y{head[0]}_val"], pv.argmax(1), pv, names)["macro_f1"]
            if best is None or f1 > best[0]:
                best = (f1, C, clf)
        f1v, C, clf = best
        pt = clf.predict_proba(d["X_test"])
        res[head] = {"C": C, "val_macro_f1": f1v,
                     "test": classification_metrics(d[f"y{head[0]}_test"], pt.argmax(1), pt, names)}
        print(space, head, "C", C, "val mF1 %.4f" % f1v, "test mF1 %.4f acc %.4f" % (
            res[head]["test"]["macro_f1"], res[head]["test"]["accuracy"]))
    save_json(res, OUT / "baselines" / f"probe_{space}.json")


def kmeans(space):
    from sklearn.cluster import KMeans
    from sklearn.decomposition import PCA
    from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score, silhouette_score
    from sklearn.preprocessing import StandardScaler
    d = np.load(FEAT_DIR / f"{space}.npz")
    sc = StandardScaler().fit(d["X_train"])
    pca = PCA(n_components=50, random_state=42).fit(sc.transform(d["X_train"]))
    Z = {s: pca.transform(sc.transform(d[f"X_{s}"])) for s in ("train", "test")}
    sweep = []
    for k in range(2, 13):
        km = KMeans(k, n_init=10, random_state=42).fit(Z["train"])
        sweep.append({"k": k, "inertia": float(km.inertia_),
                      "silhouette_train": float(silhouette_score(Z["train"], km.labels_, random_state=42,
                                                                 sample_size=min(2000, len(Z["train"]))))})
    k_best = max(sweep, key=lambda r: r["silhouette_train"])["k"]
    res = {"space": space, "preprocessing": "StandardScaler + PCA(50), both fitted on train",
           "k_selection": "max train silhouette over k=2..12 (labels not used)", "sweep": sweep, "k_selected": k_best,
           "alignment": {}}
    combo = lambda s: d[f"yt_{s}"] * 2 + d[f"ys_{s}"]  # noqa: E731
    for k in sorted({k_best, 6, 12}):
        km = KMeans(k, n_init=10, random_state=42).fit(Z["train"])
        for s in ("train", "test"):
            lab = km.labels_ if s == "train" else km.predict(Z[s])
            res["alignment"][f"k{k}_{s}"] = {
                "ARI_produce": float(adjusted_rand_score(d[f"yt_{s}"], lab)),
                "NMI_produce": float(normalized_mutual_info_score(d[f"yt_{s}"], lab)),
                "ARI_spoilage": float(adjusted_rand_score(d[f"ys_{s}"], lab)),
                "NMI_spoilage": float(normalized_mutual_info_score(d[f"ys_{s}"], lab)),
                "NMI_produce_x_spoilage": float(normalized_mutual_info_score(combo(s), lab)),
            }
        if k == 6:
            lab = km.labels_
            res["k6_train_composition"] = {int(c): {PRODUCE_CLASSES[t]: int(((lab == c) & (d["yt_train"] == t)).sum())
                                                    for t in range(6)} for c in range(6)}
    res["note"] = "Clusters are exploratory and are not ground-truth classes."
    # 2-D projection for plotting
    p2 = PCA(n_components=2, random_state=42).fit(Z["train"])
    km6 = KMeans(6, n_init=10, random_state=42).fit(Z["train"])
    (OUT / "kmeans").mkdir(parents=True, exist_ok=True)
    np.savez_compressed(OUT / "kmeans" / f"{space}_2d.npz",
                        xy=p2.transform(Z["train"]), cluster=km6.labels_, yt=d["yt_train"], ys=d["ys_train"])
    save_json(res, OUT / "kmeans" / f"kmeans_{space}.json")
    print(space, "k*", k_best, {k: round(v["NMI_produce"], 3) for k, v in res["alignment"].items()})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["features", "probe", "kmeans"])
    ap.add_argument("--space", choices=["colorhist", "vit_frozen"], required=True)
    a = ap.parse_args()
    {"features": extract, "probe": probe, "kmeans": kmeans}[a.cmd](a.space)
