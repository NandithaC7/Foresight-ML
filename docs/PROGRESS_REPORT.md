# Foresight — progress report (2026-10-15)

> **Update 2026-10-16:** superseded where it conflicts by `releases/final_review/`. Completed since this file was written:
> - a controlled 3-seed ablation (real only 0.914 ± 0.006, conventional augmentation 0.928 ± 0.007, + GAN 0.919 ± 0.018 test spoilage macro-F1; no GAN benefit)
> - a 3-seed day-grouped split (0.830 ± 0.007, i.e. −0.098 vs the session split)
> - DnCNN v2 (3,821 steps)
> - frontend Vitest tests (7/7)
> - the TR-6+ noise pilot (120 derivatives) and the v1.1.0 metadata package


Status key: **VERIFIED** means it was tested with saved evidence. **MEASURED** means the result comes from a recorded run. **IMPLEMENTED** means the code runs but was not separately verified. **BLOCKED / NOT RUN** means it was not done, with the reason given.

## What works now
| Component | Status | Evidence |
|---|---|---|
| TR-6 audit re-run (identical to the prior audit) | VERIFIED | `dataset-preparation/tr6-audit/output_rerun_2026-10-15/` |
| Duplicate-aware, session-grouped 60/20/20 split (5,335 eligible sRGB; 3,177 / 1,087 / 1,071) | VERIFIED | `artifacts/dataset/v1/`, tests M01–M07 |
| ViT-B/16 two-head classifier, trained and selected on validation | MEASURED | `artifacts/runs/vit_b16_primary/` |
| FastAPI backend serving the real checkpoint (validation, errors, CORS, SQLite history, PDF, XAI) | VERIFIED | 23 backend tests, E2E 11/11 |
| React UI wired to real inference, with model status, warnings, error states and XAI | VERIFIED | build, browser checks in `docs/TEST_REPORT.md` |
| Noise robustness, median and DnCNN denoising, GAN, K-means, XAI, ablations, split sensitivity | MEASURED | `docs/EXPERIMENT_LOG.md`, 14 figures, 8 tables |

## Actual test metrics (held-out test split, n = 1,071, scored once)
| Task | Accuracy | Macro-F1 | ROC-AUC |
|---|---|---|---|
| Produce type (6 classes) | 1.0000 | 1.0000 | 1.000 |
| Spoilage (Spoiled vs Not_spoiled) | **0.9608** | **0.9536** | **0.9893** |

- **Spoiled class:** precision 0.981, **recall 0.894**. 36 spoiled items were missed, 27 of them Indian Gooseberry. Six fresh items were flagged as spoiled.
- **Through the live API:** on 60 full-resolution held-out originals, produce was correct 60/60 and spoilage 57/60.

### Why these numbers are optimistic
- Train and test share physical specimens: TR-6 has no specimen IDs.
- 49 of 64 test sessions share a capture day with a training session.
- The day-grouped sensitivity run lowered a ViT-S model's spoilage macro-F1 from **0.879 to 0.812**.
- All images are lab photos on a plain background. Real phone photos are untested.
- Produce-type classification is close to trivial on this data.

## Decisions made (and why)
- **Spoilage labels:** taken from `Classified` folders. 170 conflicting contents (all thermal) were **excluded**, not tie-broken. `Normal`-only contents were treated as unlabeled.
- **Modality:** sRGB only, because the app receives phone photos. Thermal and methane data have no verified pairing to the RGB images.
- **Grouping unit:** the inferred capture session (17 views of one fruit, ≤300 s apart). This was chosen over date grouping because Carrot/Not_spoiled has only 2 capture days, which makes a day-level 60/20/20 split infeasible. The date-level risk is instead quantified with the day-grouped sensitivity split.
- **Ablations use ViT-S/16 instead of ViT-B:** ViT-B trains at about 4 minutes per epoch on the M5, against about 1 minute for ViT-S. The ViT-B primary was kept for deployment.
- **UI:** the existing design was kept. Content that implied things the system does not do was changed:
  - fake "Apple 98% / Orange 94%" detections
  - a hard-coded "1.2 MB" file size and an "85%" fallback
  - shelf-life days
  - "detects every item in the frame"
  - About-page claims about YOLO, shelf-life regression and an LLM layer
- **Mock simulator:** kept for UI development only. It is **off by default** and labelled "DEMO MOCK DATA" on every output.

## Incomplete or blocked
| Item | Status | What is needed |
|---|---|---|
| U-Net decay segmentation | BLOCKED | Human-reviewed decay masks: 0 exist, and the 12 existing masks are proposals only. |
| Shelf-life regression | DISABLED | Measured time-to-endpoint labels. |
| YOLOv8 multi-item detection | NOT RUN | Multi-item images with bounding boxes. |
| CVAT setup | NOT DONE | Installing CVAT and doing annotation work. The Label Studio workflow is preserved. |
| GAN benefit claim | NOT CLAIMED | The +0.011 over the stable baseline is within single-seed noise. Needs 3+ seeds. |
| Augmentation ablation | INCONCLUSIVE | The ViT-S + augmentation run was unstable. Rerun at lr 2e-5 with 3 seeds. |
| DnCNN | UNDER-TRAINED | Only 1,065 steps, and it loses to a median filter on PSNR and SSIM. Needs a much longer run. |
| Multi-seed mean ± std, calibration (ECE), day-grouped ViT-B | NOT RUN | Time budget. |
| Third-party deployment | NOT DONE | Needs a host with ~1.5 GB RAM for the backend, plus a static host for `dist/`. |
| Paper (discussion, SDG, team table) | NOT WRITTEN | The figures and tables it would draw on are ready. |

## Files and where things are
- Docs: `docs/DATASET_CARD.md`, `docs/MODEL_CARD.md`, `docs/EXPERIMENT_LOG.md`, `docs/TEST_REPORT.md`
- Figures and tables: `artifacts/report/figures/*.png` (14 figures), `artifacts/report/tables/T1–T8.md/.csv`, and the index `artifacts/report/figures_index.json`
- Deployed checkpoint: `backend/models/foresight_vit.pt`, a copy of `artifacts/runs/vit_b16_primary/best.pt` (343 MB)
- Unchanged: `dataset/TR-6`, the prior audit output, `Foresight-TR6-plus/` (including Label Studio annotations) and `releases/`

## Launch
```bash
cd backend && ../.venv/bin/uvicorn main:app --port 8000
cd frontend && npm run dev        # open http://localhost:5173
```
