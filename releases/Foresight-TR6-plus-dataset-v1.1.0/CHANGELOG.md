# Changelog

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
