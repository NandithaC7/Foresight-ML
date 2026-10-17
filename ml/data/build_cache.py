"""
build_cache.py — decode each eligible sRGB image once into a small derived copy.

The 4000x3000 source JPEGs are too slow to decode every epoch. This writes an
EXIF-orientation-corrected copy whose shorter side is 256 px to
artifacts/cache/srgb_256/<sha256>.jpg (derived data, outside the source tree,
not for redistribution). Sources are opened read-only. Resumable: existing
cache files are skipped.

Usage:
  python ml/data/build_cache.py --manifest artifacts/dataset/v1/split_manifest.csv \
      --dataset dataset/TR-6 --out artifacts/cache/srgb_256 --workers 8
"""
from __future__ import annotations

import argparse
import csv
import json
from multiprocessing import Pool
from pathlib import Path

from PIL import Image, ImageOps

SHORT_SIDE = 256


def process(job):
    src, dst = job
    if Path(dst).exists():
        return "skipped"
    with Image.open(src) as im:
        im.draft("RGB", (im.width // 8 or 1, im.height // 8 or 1))  # fast JPEG DCT downscale
        im = ImageOps.exif_transpose(im).convert("RGB")
        w, h = im.size
        s = SHORT_SIDE / min(w, h)
        im = im.resize((max(1, round(w * s)), max(1, round(h * s))), Image.BICUBIC)
        im.save(dst, "JPEG", quality=95)
    return "written"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--dataset", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    rows = [r for r in csv.DictReader(args.manifest.open()) if r["split"] in ("train", "val", "test")]
    jobs = [(str(args.dataset / r["source_relative_path"]), str(args.out / f"{r['sha256']}.jpg")) for r in rows]
    with Pool(args.workers) as pool:
        res = pool.map(process, jobs, chunksize=16)
    stats = {k: res.count(k) for k in set(res)}
    (args.out / "cache_info.json").write_text(json.dumps(
        {"short_side": SHORT_SIDE, "exif_transpose": True, "resample": "bicubic", "jpeg_quality": 95,
         "files": len(jobs), **stats}, indent=2))
    print(stats)


if __name__ == "__main__":
    main()
