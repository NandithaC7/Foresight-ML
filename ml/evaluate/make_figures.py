"""
make_figures.py — build every figure and table from saved result files.
Nothing is hand-entered: a figure whose inputs are missing is skipped and
listed under "skipped" in artifacts/report/figures_index.json.

Usage: .venv/bin/python ml/evaluate/make_figures.py
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml"))
from common import PRODUCE_CLASSES, SPOILAGE_CLASSES  # noqa: E402

A = ROOT / "artifacts"
PRIMARY = A / "runs/vit_b16_primary"
FIG, TAB = A / "report/figures", A / "report/tables"
FIG.mkdir(parents=True, exist_ok=True); TAB.mkdir(parents=True, exist_ok=True)
made, skipped = [], []
plt.rcParams.update({"figure.dpi": 130, "font.size": 9, "axes.spines.top": False, "axes.spines.right": False})
C1, C2, C3, C4 = "#2F6B4F", "#C1622E", "#7A8FB0", "#B59A3C"


def load(p):
    p = Path(p)
    return json.loads(p.read_text()) if p.exists() else None


def fig(name, fn, *needs):
    if not all(Path(n).exists() for n in needs):
        skipped.append({"figure": name, "missing": [str(Path(n).relative_to(ROOT)) for n in needs if not Path(n).exists()]})
        return
    f = fn()
    f.tight_layout(); f.savefig(FIG / f"{name}.png"); plt.close(f); made.append(f"figures/{name}.png")


def write_table(name, header, rows):
    with open(TAB / f"{name}.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(header); w.writerows(rows)
    md = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    md += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    (TAB / f"{name}.md").write_text("\n".join(md) + "\n")
    made.append(f"tables/{name}.md")


f3 = lambda v: "–" if v is None else f"{v:.4f}"  # noqa: E731

# ---------------- 1-2 training curves ----------------
def curves_loss():
    h = load(PRIMARY / "history.json"); e = [r["epoch"] for r in h]
    f, ax = plt.subplots(figsize=(5, 3.2))
    ax.plot(e, [r["train_loss"] for r in h], "o-", c=C1, label="train (augmented)")
    ax.plot(e, [r["val_loss"] for r in h], "s-", c=C2, label="validation")
    ax.set_xlabel("epoch"); ax.set_ylabel("loss = CE_type + CE_spoilage"); ax.legend(); ax.set_title("ViT-B/16 primary: loss")
    return f


def curves_f1():
    h = load(PRIMARY / "history.json"); e = [r["epoch"] for r in h]
    f, ax = plt.subplots(figsize=(5, 3.2))
    ax.plot(e, [r["val_type_macro_f1"] for r in h], "o-", c=C1, label="val produce macro-F1")
    ax.plot(e, [r["val_spoil_macro_f1"] for r in h], "s-", c=C2, label="val spoilage macro-F1")
    ax.plot(e, [r["train_spoil_acc"] for r in h], "^--", c=C3, label="train spoilage accuracy")
    best = max(h, key=lambda r: r["val_composite_macro_f1"])["epoch"]
    ax.axvline(best, ls=":", c="grey"); ax.text(best, ax.get_ylim()[0], " selected", fontsize=7, va="bottom")
    ax.set_xlabel("epoch"); ax.set_ylabel("score"); ax.legend(fontsize=7); ax.set_title("ViT-B/16 primary: validation metrics")
    return f


fig("01_training_loss", curves_loss, PRIMARY / "history.json")
fig("02_validation_macro_f1", curves_f1, PRIMARY / "history.json")
TEST = PRIMARY / "eval/test_clean_0_none.json"


def cm_plot(key, names, title):
    def _f():
        m = np.array(load(TEST)[key]["confusion_matrix"])
        f, ax = plt.subplots(figsize=(4.6 if len(names) > 2 else 3.4, 4 if len(names) > 2 else 3))
        ax.imshow(m, cmap="Greens")
        for i in range(len(names)):
            for j in range(len(names)):
                ax.text(j, i, m[i, j], ha="center", va="center", color="white" if m[i, j] > m.max() / 2 else "black", fontsize=8)
        short = [n.replace("Indian_Gooseberry", "Gooseberry").replace("_", " ") for n in names]
        ax.set_xticks(range(len(names)), short, rotation=35, ha="right"); ax.set_yticks(range(len(names)), short)
        ax.set_xlabel("predicted"); ax.set_ylabel("true"); ax.set_title(title, fontsize=9)
        return f
    return _f


fig("03_confusion_produce_test", cm_plot("type", PRODUCE_CLASSES, "Test confusion — produce type"), TEST)
fig("04_confusion_spoilage_test", cm_plot("spoil", SPOILAGE_CLASSES, "Test confusion — spoilage"), TEST)


def per_class():
    t = load(TEST)
    names = PRODUCE_CLASSES + [f"spoil:{s}" for s in SPOILAGE_CLASSES]
    vals = [t["type"]["per_class"][c] for c in PRODUCE_CLASSES] + [t["spoil"]["per_class"][c] for c in SPOILAGE_CLASSES]
    x = np.arange(len(names)); w = 0.27
    f, ax = plt.subplots(figsize=(7, 3.2))
    for k, (m, c) in enumerate((("precision", C1), ("recall", C3), ("f1", C2))):
        ax.bar(x + (k - 1) * w, [v[m] for v in vals], w, color=c, label=m)
    ax.set_xticks(x, [n.replace("Indian_Gooseberry", "Gooseberry") for n in names], rotation=30, ha="right")
    ax.set_ylim(0.5, 1.01); ax.legend(fontsize=7, ncol=3); ax.set_title("Test per-class precision / recall / F1")
    return f


fig("05_per_class_metrics_test", per_class, TEST)


def roc():
    from sklearn.metrics import roc_curve
    rows = list(csv.DictReader(open(PRIMARY / "eval/test_clean_0_none_predictions.csv")))
    y = [r["true_spoil"] == "Spoiled" for r in rows]; s = [float(r["p_spoiled"]) for r in rows]
    fpr, tpr, _ = roc_curve(y, s)
    f, ax = plt.subplots(figsize=(3.6, 3.4))
    ax.plot(fpr, tpr, c=C2, label=f"AUC = {load(TEST)['spoil']['roc_auc']:.3f}"); ax.plot([0, 1], [0, 1], ":", c="grey")
    ax.set_xlabel("false positive rate"); ax.set_ylabel("true positive rate"); ax.legend(); ax.set_title("Test ROC — Spoiled")
    return f


fig("06_roc_spoilage_test", roc, PRIMARY / "eval/test_clean_0_none_predictions.csv")

# ---------------- robustness ----------------
ROB = sorted((PRIMARY / "eval").glob("test_*.json")) if (PRIMARY / "eval").exists() else []
rob = [load(p) for p in ROB]


def robustness():
    f, axes = plt.subplots(1, 3, figsize=(10, 3.2), sharey=True)
    clean = load(TEST)["spoil"]["macro_f1"]
    for ax, kind in zip(axes, ("gaussian", "salt_pepper", "speckle")):
        for den, c, mk in (("none", C2, "o"), ("median", C3, "s"), ("dncnn", C1, "^")):
            pts = sorted((r["level"], r["spoil"]["macro_f1"]) for r in rob
                         if r["corruption"] == kind and r["denoiser"].split(":")[0] == den)
            if pts:
                ax.plot([0] + [p[0] for p in pts], [clean] + [p[1] for p in pts], marker=mk, c=c, label=den)
        ax.set_title(kind); ax.set_xlabel("noise level (σ or p)")
    axes[0].set_ylabel("test spoilage macro-F1"); axes[0].legend(fontsize=7, title="denoiser", title_fontsize=7)
    f.suptitle("Noise robustness of ViT-B/16 (deterministic corruptions of the test set)", fontsize=9)
    return f


if any(r["corruption"] != "clean" for r in rob):
    fig("07_noise_robustness", robustness, TEST)
else:
    skipped.append({"figure": "07_noise_robustness", "missing": ["corrupted test evaluations"]})

DN = A / "experiments/dncnn/dncnn_results.json"


def psnr_ssim():
    d = load(DN)["paired_val_quality"]
    f, axes = plt.subplots(1, 2, figsize=(8, 3.2))
    for ax, met in zip(axes, ("psnr", "ssim")):
        for kind, ls in (("gaussian", "-"), ("salt_pepper", "--")):
            rows = [r for r in d if r["corruption"] == kind]
            for name, c in (("noisy", C2), ("median", C3), ("dncnn", C1)):
                ax.plot([r["level"] for r in rows], [r[f"{name}_{met}"] for r in rows], ls, marker="o", c=c,
                        label=f"{name} ({kind})")
        ax.set_xlabel("noise level"); ax.set_ylabel(met.upper())
    axes[1].legend(fontsize=6)
    f.suptitle("Denoising quality on validation images (synthetic noise, clean reference known)", fontsize=9)
    return f


fig("08_denoising_psnr_ssim", psnr_ssim, DN)

# ---------------- ablation ----------------
ABL = [
    ("E0a colour-hist + LogReg", A / "experiments/baselines/probe_colorhist.json", "probe"),
    ("E0b frozen ViT-B + LogReg", A / "experiments/baselines/probe_vit_frozen.json", "probe"),
    ("E1 ViT-S/16 no aug", A / "runs/vit_s16_noaug/eval/test_clean_0_none.json", "run"),
    ("E2 ViT-S/16 conv aug", A / "runs/vit_s16_aug/eval/test_clean_0_none.json", "run"),
    ("E3 ViT-S/16 conv aug + GAN", A / "runs/vit_s16_aug_gan/eval/test_clean_0_none.json", "run"),
    ("E4 ViT-B/16 conv aug (primary)", TEST, "run"),
]


def abl_rows():
    out = []
    for name, p, kind in ABL:
        d = load(p)
        if not d:
            out.append((name, None, None, None, None)); continue
        if kind == "probe":
            out.append((name, d["type"]["test"]["macro_f1"], d["spoil"]["test"]["macro_f1"], d["spoil"]["test"]["accuracy"],
                        d["spoil"]["test"].get("roc_auc")))
        else:
            out.append((name, d["type"]["macro_f1"], d["spoil"]["macro_f1"], d["spoil"]["accuracy"], d["spoil"].get("roc_auc")))
    return out


def ablation():
    rows = [r for r in abl_rows() if r[1] is not None]
    f, ax = plt.subplots(figsize=(7, 3.4))
    y = np.arange(len(rows))
    ax.barh(y - 0.2, [r[1] for r in rows], 0.4, color=C1, label="produce macro-F1")
    ax.barh(y + 0.2, [r[2] for r in rows], 0.4, color=C2, label="spoilage macro-F1")
    for i, r in enumerate(rows):
        ax.text(r[2] + 0.003, i + 0.2, f"{r[2]:.3f}", va="center", fontsize=7)
    ax.set_yticks(y, [r[0] for r in rows]); ax.set_xlim(0.5, 1.04); ax.invert_yaxis()
    ax.legend(fontsize=7, loc="lower center", bbox_to_anchor=(0.5, 1.06), ncol=2, frameon=False); ax.set_title("Ablation on the same held-out test split", pad=24)
    return f


if any(Path(p).exists() for _, p, _ in ABL):
    fig("09_ablation_comparison", ablation, TEST)

# ---------------- K-means ----------------
def kmeans_plot(space):
    def _f():
        d = np.load(A / f"experiments/kmeans/{space}_2d.npz")
        f, axes = plt.subplots(1, 2, figsize=(9, 3.8))
        axes[0].scatter(*d["xy"].T, c=d["cluster"], cmap="tab10", s=4); axes[0].set_title("K-means clusters (k=6)")
        for t, c in enumerate(PRODUCE_CLASSES):
            m = d["yt"] == t
            axes[1].scatter(*d["xy"][m].T, s=4, label=c.replace("Indian_", ""))
        axes[1].legend(fontsize=6, markerscale=3); axes[1].set_title("true produce labels")
        for ax in axes:
            ax.set_xlabel("PC1"); ax.set_ylabel("PC2")
        f.suptitle(f"K-means on {space} features (train split, PCA projection)", fontsize=9)
        return f
    return _f


for sp in ("vit_frozen", "colorhist"):
    fig(f"10_kmeans_{sp}", kmeans_plot(sp), A / f"experiments/kmeans/{sp}_2d.npz")

GAN = A / "experiments/gan/train_summary.json"


def gan_curves():
    h = load(GAN)["history"]
    f, ax = plt.subplots(figsize=(5, 3))
    ax.plot([r["epoch"] for r in h], [r["loss_d"] for r in h], c=C1, label="discriminator")
    ax.plot([r["epoch"] for r in h], [r["loss_g"] for r in h], c=C2, label="generator")
    ax.set_xlabel("epoch"); ax.set_ylabel("BCE loss"); ax.legend(); ax.set_title("Conditional DCGAN training (train split only)")
    return f


fig("11_gan_losses", gan_curves, GAN)


def split_dist():
    s = load(A / "dataset/v1/split_summary.json")["per_stratum"]
    keys = list(s.keys())
    f, ax = plt.subplots(figsize=(8, 3.3))
    x = np.arange(len(keys)); bottom = np.zeros(len(keys))
    for sp, c in (("train", C1), ("val", C3), ("test", C2)):
        v = np.array([s[k][sp] for k in keys]); ax.bar(x, v, bottom=bottom, color=c, label=sp); bottom += v
    ax.set_xticks(x, [k.replace("Indian_Gooseberry", "Gooseberry").replace("Not_spoiled", "NS").replace("Spoiled", "S") for k in keys],
                  rotation=40, ha="right")
    ax.set_ylabel("unique images"); ax.legend(); ax.set_title("Session-grouped 60/20/20 split per produce/label stratum")
    return f


fig("12_split_distribution", split_dist, A / "dataset/v1/split_summary.json")
LAT = A / "report/evidence/latency_benchmark.json"


def latency():
    d = load(LAT)
    f, ax = plt.subplots(figsize=(5, 3))
    ax.hist(d["samples_ms"], bins=30, color=C1)
    ax.set_xlabel("end-to-end /api/analyze latency (ms)"); ax.set_ylabel("requests")
    ax.set_title(f"API latency (median {np.median(d['samples_ms']):.0f} ms, n={len(d['samples_ms'])}, {d['device']})", fontsize=8)
    return f


fig("13_api_latency", latency, LAT)

# ---------------- tables ----------------
ss = load(A / "dataset/v1/split_summary.json")
if ss:
    rows = [[k, v["train"], v["val"], v["test"], v["train"] + v["val"] + v["test"]] for k, v in ss["per_stratum"].items()]
    rows.append(["TOTAL", ss["split_counts"]["train"], ss["split_counts"]["val"], ss["split_counts"]["test"], ss["eligible_samples"]])
    write_table("T1_dataset_split", ["produce/label", "train", "val", "test", "total"], rows)
    write_table("T1b_exclusions", ["reason", "unique contents"], [[k, v] for k, v in ss["exclusions"].items()]
                + [["leakage: " + k, v] for k, v in ss["leakage_checks"].items()])
cfgp = load(PRIMARY / "config.json")
if cfgp:
    keys = ["backbone", "img_size", "batch_size", "lr", "head_lr", "weight_decay", "epochs", "warmup_epochs", "patience",
            "aug", "lambda_type", "lambda_spoil", "seed", "device", "best_epoch", "epochs_run"]
    write_table("T2_hyperparameters_primary", ["hyperparameter", "value"], [[k, cfgp.get(k)] for k in keys])
t = load(TEST)
if t:
    rows = []
    for head, names in (("type", PRODUCE_CLASSES), ("spoil", SPOILAGE_CLASSES)):
        for c in names:
            pc = t[head]["per_class"][c]
            rows.append([head, c, f3(pc["precision"]), f3(pc["recall"]), f3(pc["f1"]), pc["support"]])
        rows.append([head, "MACRO", "", "", f3(t[head]["macro_f1"]), t[head]["n"]])
        rows.append([head, "ACCURACY", "", "", f3(t[head]["accuracy"]), t[head]["n"]])
    write_table("T3_test_metrics_primary", ["head", "class", "precision", "recall", "F1", "support"], rows)
if any(Path(p).exists() for _, p, _ in ABL):
    write_table("T4_ablation", ["experiment", "produce macro-F1", "spoilage macro-F1", "spoilage accuracy", "spoilage ROC-AUC"],
                [[r[0]] + [f3(v) for v in r[1:]] if r[1] is not None else [r[0], "not run", "", "", ""] for r in abl_rows()])
if rob:
    rows = [[r["corruption"], r["level"], r["denoiser"].split(":")[0], f3(r["type"]["macro_f1"]), f3(r["spoil"]["macro_f1"]),
             f3(r["spoil"]["accuracy"])] for r in sorted(rob, key=lambda r: (r["corruption"] != "clean", r["corruption"], r["denoiser"], r["level"]))]
    write_table("T5_noise_robustness", ["corruption", "level", "denoiser", "produce macro-F1", "spoilage macro-F1", "spoilage acc"], rows)
km = [load(A / f"experiments/kmeans/kmeans_{s}.json") for s in ("colorhist", "vit_frozen")]
rows = []
for d in km:
    if d:
        for k, v in d["alignment"].items():
            rows.append([d["space"], k, f3(v["ARI_produce"]), f3(v["NMI_produce"]), f3(v["ARI_spoilage"]), f3(v["NMI_spoilage"])])
if rows:
    write_table("T6_kmeans_alignment", ["features", "k_split", "ARI produce", "NMI produce", "ARI spoilage", "NMI spoilage"], rows)
dn = load(DN)
if dn:
    write_table("T7_denoising_quality", ["corruption", "level", "PSNR noisy", "PSNR median", "PSNR DnCNN", "SSIM noisy", "SSIM median", "SSIM DnCNN"],
                [[r["corruption"], r["level"], *(f"{r[k]:.2f}" for k in ("noisy_psnr", "median_psnr", "dncnn_psnr")),
                  *(f"{r[k]:.3f}" for k in ("noisy_ssim", "median_ssim", "dncnn_ssim"))] for r in dn["paired_val_quality"]])
sens = load(A / "runs/vit_s16_aug_daysplit/eval/test_clean_0_none.json")
base = load(A / "runs/vit_s16_aug/eval/test_clean_0_none.json")
if sens and base:
    write_table("T8_split_sensitivity", ["split (ViT-S/16, conv aug)", "test n", "produce macro-F1", "spoilage macro-F1", "spoilage ROC-AUC"],
                [["session-grouped (v1)", base["spoil"]["n"], f3(base["type"]["macro_f1"]), f3(base["spoil"]["macro_f1"]), f3(base["spoil"].get("roc_auc"))],
                 ["day-grouped (sensitivity)", sens["spoil"]["n"], f3(sens["type"]["macro_f1"]), f3(sens["spoil"]["macro_f1"]), f3(sens["spoil"].get("roc_auc"))]])

json.dump({"made": made, "skipped": skipped}, open(A / "report/figures_index.json", "w"), indent=2)
print(f"made {len(made)} outputs; skipped {len(skipped)}")
for s in skipped:
    print("  skipped", s)
