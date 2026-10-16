"""
extra_analyses.py — supplementary measured analyses for the final reports.

  gan_quality   : label consistency of GAN images under the primary ViT-B classifier,
                  within-condition diversity (mean pairwise L2 at 64x64) for generated
                  vs real train images, and a nearest-neighbour visual (generated vs
                  closest real train image).
  noise_profile : estimated intrinsic noise sigma (skimage.restoration.estimate_sigma,
                  wavelet MAD) of ORIGINAL full-resolution test images, centre 512 crop,
                  to compare real sensor noise with the synthetic corruption levels; and
                  a figure of clean / noisy / median / DnCNN for one test image.
  resources     : parameter counts, checkpoint sizes, CPU vs MPS single-image latency,
                  backend process resident memory.
"""
from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml")); sys.path.insert(0, str(ROOT / "ml/evaluate")); sys.path.insert(0, str(ROOT / "ml/experiments"))
from common import IMG_SIZE, PRODUCE_CLASSES, SPOILAGE_CLASSES, build_transforms, corrupt, load_split_rows, pick_device, save_json  # noqa
from evaluate_vit import load_model  # noqa

A = ROOT / "artifacts"
RUN = A / "runs/vit_b16_primary"
MAN = A / "dataset/v1/split_manifest.csv"


def gan_quality():
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    dev = pick_device(); model, cfg, _ = load_model(RUN, dev)
    tf = build_transforms(cfg["mean"], cfg["std"], train=False)
    gen = list(csv.DictReader(open(A / "experiments/gan/generated_manifest.csv")))
    per = {}
    for i in range(0, len(gen), 64):
        chunk = gen[i:i + 64]
        x = torch.stack([tf(Image.open(r["path"]).convert("RGB")) for r in chunk]).to(dev)
        with torch.no_grad():
            lt, ls = model(x)
        for r, t, s in zip(chunk, lt.argmax(1).cpu(), ls.argmax(1).cpu()):
            k = f"{r['produce_class']}/{r['source_label']}"
            d = per.setdefault(k, {"n": 0, "type_match": 0, "spoil_match": 0})
            d["n"] += 1; d["type_match"] += int(PRODUCE_CLASSES[t] == r["produce_class"]); d["spoil_match"] += int(SPOILAGE_CLASSES[s] == r["source_label"])
    tot = {k: sum(v[k] for v in per.values()) for k in ("n", "type_match", "spoil_match")}
    # diversity at 64x64
    train = load_split_rows(MAN, "train")
    cache = A / "cache/srgb_256"
    rng = np.random.default_rng(0)
    div = {}
    nn_pairs = []
    for k in sorted(per):
        p, s = k.split("/")
        g = np.stack([np.asarray(Image.open(r["path"]).convert("RGB").resize((64, 64), Image.BICUBIC), np.float32) / 127.5 - 1
                      for r in gen if r["produce_class"] == p and r["source_label"] == s])
        realrows = [r for r in train if r["produce_class"] == p and r["source_label"] == s]
        real = np.stack([np.asarray(Image.open(cache / f"{r['sha256']}.jpg").convert("RGB").resize((64, 64), Image.BICUBIC), np.float32) / 127.5 - 1
                         for r in [realrows[i] for i in rng.choice(len(realrows), min(40, len(realrows)), replace=False)]])
        pw = lambda X: float(np.mean([np.linalg.norm(X[i] - X[j]) for i in range(len(X)) for j in range(i + 1, len(X))]))  # noqa
        div[k] = {"generated_mean_pairwise_l2": pw(g), "real_mean_pairwise_l2": pw(real)}
        div[k]["ratio_generated_to_real"] = div[k]["generated_mean_pairwise_l2"] / div[k]["real_mean_pairwise_l2"]
        # nearest real for the first generated sample of this condition
        allreal = np.stack([np.asarray(Image.open(cache / f"{r['sha256']}.jpg").convert("RGB").resize((64, 64), Image.BICUBIC), np.float32) / 127.5 - 1 for r in realrows])
        j = int(np.argmin(((allreal - g[0]) ** 2).sum((1, 2, 3))))
        nn_pairs.append((k, g[0], allreal[j]))
    fig, axes = plt.subplots(2, len(nn_pairs), figsize=(1.5 * len(nn_pairs), 3.4))
    for c, (k, gimg, rimg) in enumerate(nn_pairs):
        axes[0, c].imshow(((gimg + 1) / 2).clip(0, 1)); axes[1, c].imshow(((rimg + 1) / 2).clip(0, 1))
        axes[0, c].set_title(k.replace("Indian_Gooseberry", "Goose.").replace("Not_spoiled", "NS").replace("Spoiled", "S"), fontsize=6)
        for ax in axes[:, c]: ax.axis("off")
    axes[0, 0].text(-10, 32, "GAN", rotation=90, va="center", fontsize=7); axes[1, 0].text(-10, 32, "nearest\nreal", rotation=90, va="center", fontsize=7)
    fig.suptitle("Generated sample (top) vs its nearest real TRAIN image by pixel L2 (bottom), 64×64", fontsize=8)
    fig.tight_layout(); fig.savefig(A / "experiments/gan/nearest_neighbour_check.png", dpi=150); plt.close(fig)
    res = {"label_consistency_by_primary_vit": {"overall_type_match": tot["type_match"] / tot["n"], "overall_spoil_match": tot["spoil_match"] / tot["n"],
                                                "per_condition": per, "note": "Primary ViT-B (trained on real data only) applied to GAN images; agreement with the conditioning label."},
           "diversity_64px": div,
           "mean_diversity_ratio": float(np.mean([v["ratio_generated_to_real"] for v in div.values()]))}
    save_json(res, A / "experiments/gan/quality_checks.json")
    print(json.dumps({k: res[k] for k in ("mean_diversity_ratio",)}), res["label_consistency_by_primary_vit"]["overall_type_match"], res["label_consistency_by_primary_vit"]["overall_spoil_match"])


def noise_profile():
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    from skimage.restoration import estimate_sigma
    rows = load_split_rows(MAN, "test")
    rng = np.random.default_rng(1)
    out = {}
    for p in PRODUCE_CLASSES:
        sel = [r for r in rows if r["produce_class"] == p]
        sel = [sel[i] for i in rng.choice(len(sel), min(20, len(sel)), replace=False)]
        sig_full, sig_224 = [], []
        for r in sel:
            im = Image.open(ROOT / "dataset/TR-6" / r["source_relative_path"]).convert("RGB")
            w, h = im.size
            crop = np.asarray(im.crop((w // 2 - 256, h // 2 - 256, w // 2 + 256, h // 2 + 256)), np.float32) / 255
            sig_full.append(float(estimate_sigma(crop, channel_axis=-1, average_sigmas=True)))
            small = np.asarray(Image.open(A / "cache/srgb_256" / f"{r['sha256']}.jpg").convert("RGB").resize((IMG_SIZE, IMG_SIZE)), np.float32) / 255
            sig_224.append(float(estimate_sigma(small, channel_axis=-1, average_sigmas=True)))
        out[p] = {"n": len(sel), "sigma_fullres_centre512_mean": float(np.mean(sig_full)), "sigma_model_input_224_mean": float(np.mean(sig_224))}
    allf = [v["sigma_fullres_centre512_mean"] for v in out.values()]; alls = [v["sigma_model_input_224_mean"] for v in out.values()]
    res = {"method": "skimage.restoration.estimate_sigma (wavelet MAD), pixel scale [0,1]", "per_produce": out,
           "overall_fullres_mean": float(np.mean(allf)), "overall_model_input_mean": float(np.mean(alls)),
           "synthetic_gaussian_levels_evaluated": [0.05, 0.1, 0.2],
           "interpretation": "Intrinsic noise of TR-6 photos is far below the synthetic stress levels; robustness results are stress tests, not measurements of TR-6 sensor noise."}
    save_json(res, A / "experiments/noise_profile.json")
    # visual: one test image under each corruption with denoisers
    sys.path.insert(0, str(ROOT / "ml/experiments"))
    from dncnn import load_dncnn
    dev = pick_device(); net = load_dncnn(A / "experiments/dncnn/dncnn.pt", dev)
    r = rows[17]
    clean = Image.open(A / "cache/srgb_256" / f"{r['sha256']}.jpg").convert("RGB").resize((IMG_SIZE, IMG_SIZE))
    def dn(im):
        x = torch.from_numpy(np.asarray(im, np.float32) / 255).permute(2, 0, 1)[None].to(dev)
        with torch.no_grad(): y = (x - net(x)).clamp(0, 1)
        return Image.fromarray((y[0].permute(1, 2, 0).cpu().numpy() * 255).round().astype(np.uint8))
    conds = [("gaussian", 0.1), ("salt_pepper", 0.05), ("speckle", 0.3)]
    fig, axes = plt.subplots(len(conds), 4, figsize=(8, 6.2))
    for i, (k, l) in enumerate(conds):
        noisy = corrupt(clean, k, l, 99)
        for j, (name, im) in enumerate((("clean", clean), (f"{k} {l}", noisy), ("median 3×3", noisy.filter(ImageFilter.MedianFilter(3))), ("DnCNN", dn(noisy)))):
            axes[i, j].imshow(im); axes[i, j].set_title(name, fontsize=7); axes[i, j].axis("off")
    fig.suptitle(f"Noise components and denoising on a test image ({r['produce_class']}/{r['source_label']})", fontsize=8)
    fig.tight_layout(); fig.savefig(A / "experiments/noise_examples.png", dpi=140); plt.close(fig)
    print(json.dumps({k: res[k] for k in ("overall_fullres_mean", "overall_model_input_mean")}))


def resources():
    out = {}
    for name, run in (("ViT-B/16 primary", RUN), ("ViT-S/16 ablation", A / "runs/vit_s16_noaug")):
        m, cfg, _ = load_model(run, torch.device("cpu"))
        out[name] = {"parameters": int(sum(p.numel() for p in m.parameters())), "checkpoint_mb": round((run / "best.pt").stat().st_size / 1e6, 1)}
        tf = build_transforms(cfg["mean"], cfg["std"], train=False)
        x = tf(Image.new("RGB", (256, 341), (150, 120, 60)))[None]
        for dev in ("cpu", "mps"):
            if dev == "mps" and not torch.backends.mps.is_available(): continue
            mm = m.to(dev); xx = x.to(dev); ts = []
            with torch.no_grad():
                for i in range(25):
                    t0 = time.perf_counter(); mm(xx)
                    if dev == "mps": torch.mps.synchronize()
                    if i >= 5: ts.append((time.perf_counter() - t0) * 1000)
            out[name][f"single_image_latency_ms_{dev}_median"] = float(np.median(ts))
    pid = subprocess.run(["pgrep", "-f", "uvicorn main:app"], capture_output=True, text=True).stdout.split()
    rss = [int(l.split()[0]) for l in subprocess.run("ps -axo rss,command | grep 'uvicorn main:app' | grep -v grep", shell=True, capture_output=True, text=True).stdout.splitlines() if l.strip()]
    if rss:  # largest matching process = the Python server, not its shell wrapper
        out["backend_process_rss_mb"] = round(max(rss) / 1024, 1)
    out["hardware"] = "Apple M5, 16 GB unified memory; torch " + torch.__version__
    out["note"] = "Single-image forward pass only (no decode/resize). Measured while other training jobs may share the GPU."
    save_json(out, A / "experiments/resources.json"); print(json.dumps(out, indent=1))


if __name__ == "__main__":
    {"gan_quality": gan_quality, "noise_profile": noise_profile, "resources": resources}[sys.argv[1]]()
