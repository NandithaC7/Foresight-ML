# Not included in Foresight-TR6-plus-dataset-v1.0.0

This package is a derived metadata and code resource. The following are intentionally absent.

## Original TR-6 content (obtain from Figshare)

- All sRGB and thermal IR-fusion JPEG images (~21,626 files, ~19.8 GiB)
- All methane `.txt` files (18 files, 26,928 measurement records)
- `TR-6/README.txt` and other files from the original tree
- `TR-6.zip` from Figshare (20,388,430,589 bytes, MD5 `cdbcc4a667051aa35d46c2de71a723d9`)

Canonical source: https://doi.org/10.6084/m9.figshare.30783827.v1

Do **not** upload those binaries with this IEEE DataPort item unless you separately confirm that re-hosting is wanted. Figshare lists CC BY 4.0, which would allow redistribution with attribution; this v1.0.0 release still does not re-host them.

## Pixel derivatives of TR-6 (local only)

- `annotations/masks/tr6p_*.png` (12 proposal rasters)
- `reports/calibration-overlays/`
- `reports/calibration-previews/`
- Audit contact sheets (`contact-sheet-*.jpg`)
- Pilot review contact sheets

## Noise-augmented images

The pipeline lives under `future/noise-augmentation/`. No noisy copies were generated for this release.

## Secrets, local tools, and private files

- Label Studio `.env`, SQLite, and `SECRET_KEY`
- `.label-studio-venv/`
- Local login credentials
- Absolute workstation paths

## Claims this package does not make

- Newly collected fruit images
- Completed human segmentation ground truth
- Verified specimen IDs or RGB–thermal–methane pairs
- Independently verified spoilage labels
- Trained models or experimental metrics
- An IEEE DataPort DOI (not assigned until you submit)
