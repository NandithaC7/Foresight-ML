"""
package_tr6plus_v1_1.py — build Foresight-TR6-plus-dataset-v1.1.0 (metadata-only).

Starts from the unchanged v1.0.0 package directory and ADDS:
  ml_splits/        split manifests + summaries used to train/evaluate the Foresight model
  derived/noise-pilot-v1/   manifest + summaries of the 120 noise derivatives (images NOT included)
  synthetic/gan/    manifest + quality checks of 480 GAN images (images NOT included)
  reports/validation_rerun_2026-10-15.*   re-run of the extension validator
  docs/DATASET_CARD.md, CHANGELOG.md, SHA256SUMS.txt, VERSION=1.1.0
No TR-6 image, noisy image or GAN image is packaged. Absolute workstation paths are sanitised.
v1.0.0 files are not modified.
"""
import hashlib
import json
import re
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "releases/Foresight-TR6-plus-dataset-v1.0.0"
NAME = "Foresight-TR6-plus-dataset-v1.1.0"
OUT = ROOT / "releases" / NAME
ABS = re.compile(re.escape(str(ROOT)) + r"/?")
TEXT = {".csv", ".json", ".md", ".txt", ".py", ".xml"}


def sanitise(p: Path):
    if p.suffix in TEXT:
        t = p.read_text(encoding="utf-8")
        t2 = ABS.sub("", t).replace("/private/tmp/", "<tmp>/")
        if t2 != t:
            p.write_text(t2, encoding="utf-8")


def add(src, dst):
    dst = OUT / dst
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(src, dst)
    sanitise(dst)


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(SRC, OUT)
    A = ROOT / "artifacts"
    T6 = ROOT / "Foresight-TR6-plus"
    for f in ("split_manifest.csv", "split_summary.json", "conflicting_labels.csv"):
        add(A / "dataset/v1" / f, f"ml_splits/session_grouped_v1/{f}")
    for f in ("split_manifest.csv", "split_summary.json"):
        add(A / "dataset/v1_daygroup_sensitivity" / f, f"ml_splits/day_grouped_sensitivity/{f}")
    add(ROOT / "ml/data/make_splits.py", "scripts/make_splits.py")
    add(T6 / "manifests/derived/noise_pilot_v1_manifest.csv", "derived/noise-pilot-v1/noise_pilot_v1_manifest.csv")
    for f in ("generation_summary.json", "disk_estimate.json"):
        add(T6 / "reports/noise-pilot-v1" / f, f"derived/noise-pilot-v1/{f}")
    add(T6 / "config/noise_generation.json", "derived/noise-pilot-v1/noise_generation.json")
    add(T6 / "scripts/generate_noise_dataset.py", "derived/noise-pilot-v1/generate_noise_dataset.py")
    gm = OUT / "synthetic/gan/generated_manifest.csv"
    add(A / "experiments/gan/generated_manifest.csv", "synthetic/gan/generated_manifest.csv")
    gm.write_text(gm.read_text().replace("artifacts/experiments/gan/generated/", ""), encoding="utf-8")
    for f in ("train_summary.json", "generation_summary.json", "quality_checks.json"):
        add(A / "experiments/gan" / f, f"synthetic/gan/{f}")
    add(ROOT / "ml/experiments/gan.py", "synthetic/gan/gan.py")
    ev = ROOT / "releases/final_review/evidence/tr6plus_validation_rerun_2026-10-15"
    add(ev / "validation_report.json", "reports/validation_rerun_2026-10-15.json")
    add(ev / "validation_report.md", "reports/validation_rerun_2026-10-15.md")
    add(ROOT / "docs/DATASET_CARD.md", "docs/DATASET_CARD.md")
    (OUT / "VERSION").write_text("1.1.0\n")
    (OUT / "CHANGELOG.md").write_text("""# Changelog

## 1.1.0 (2026-10-15)
Added (metadata only; no images):
- `ml_splits/session_grouped_v1/`: content-level, duplicate-aware, capture-session-grouped 60/20/20 split of the 5,335
  eligible sRGB contents (3,177 / 1,087 / 1,071), conflict report, split summary with leakage checks. Seed 42.
- `ml_splits/day_grouped_sensitivity/`: stricter day-grouped split used only for a sensitivity analysis.
- `derived/noise-pilot-v1/`: manifest (SHA-256 per derivative) and summaries for 120 noise derivatives
  (24 pilot sources x 5 transforms; Gaussian sigma 8/20, salt-and-pepper 1%/4%, speckle var 0.04).
  The derivative JPEGs are NOT included; regenerate deterministically with `generate_noise_dataset.py`
  (verified: an independent regeneration reproduced all 120 SHA-256 hashes).
- `synthetic/gan/`: manifest and quality checks for 480 class-conditional DCGAN images (64x64, train split only).
  Images NOT included. They are synthetic and must never be used as evaluation data.
- `reports/validation_rerun_2026-10-15.*`: validator re-run (PASS, 0 errors, 96/96 pilot hashes recomputed).
- `docs/DATASET_CARD.md`.

Unchanged from 1.0.0: annotation status (0 human-reviewed masks; 12 proposal-only), all v1.0.0 manifests and reports.
""")
    with (OUT / "README.md").open("a") as f:
        f.write("""

## Version 1.1.0 additions

See `CHANGELOG.md`. v1.1.0 adds the machine-learning split manifests used by the Foresight model, the manifest of a
120-image noise-derivative pilot and of 480 GAN images (both **without** image files), and a validator re-run.
Integrity: every file is listed with its SHA-256 in `SHA256SUMS.txt`.
""")
    files = sorted(p for p in OUT.rglob("*") if p.is_file() and p.name != "SHA256SUMS.txt")
    for p in files:
        sanitise(p)
    leaks = [str(p.relative_to(OUT)) for p in files if p.suffix in TEXT and (str(ROOT) in p.read_text(errors="ignore") or "/Users/" in p.read_text(errors="ignore"))]
    images = [str(p.relative_to(OUT)) for p in files if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".tif", ".bmp")]
    sums = [f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(OUT)}" for p in files]
    (OUT / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n")
    zp = ROOT / "releases" / f"{NAME}.zip"
    if zp.exists():
        zp.unlink()
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(OUT.rglob("*")):
            if p.is_file():
                z.write(p, f"{NAME}/{p.relative_to(OUT)}")
    zsha = hashlib.sha256(zp.read_bytes()).hexdigest()
    (ROOT / "releases" / f"{NAME}.zip.sha256").write_text(f"{zsha}  {NAME}.zip\n")
    rel = {"package": NAME, "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "zip_filename": f"{NAME}.zip",
           "zip_bytes": zp.stat().st_size, "zip_sha256": zsha, "package_file_count": len(files) + 1,
           "absolute_path_leaks": leaks, "image_files_in_package": images, "source_images_included": 0,
           "derived_or_synthetic_images_included": 0, "human_complete_annotations": 0,
           "ieee_dataport_uploaded": False, "doi_assigned": False,
           "result": "pass" if not leaks and not images else "fail"}
    (ROOT / "releases" / f"{NAME}.release.json").write_text(json.dumps(rel, indent=2))
    print(json.dumps(rel, indent=2))


if __name__ == "__main__":
    main()
