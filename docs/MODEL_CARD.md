# Model card — Foresight ViT (`vit_b16_primary@epoch9`)

Status: **MEASURED** on the held-out test split. **VERIFIED** to serve through the API and UI (see `docs/TEST_REPORT.md`).

## What it is
- **Architecture:** a pretrained ViT-B/16 (`timm` `vit_base_patch16_224.augreg2_in21k_ft_in1k`, ImageNet-21k → 1k), fine-tuned end to end.
  The CLS embedding `z` (768-d) goes through dropout 0.1 and then two linear heads:
  - `p_type = softmax(W_type z + b_type)` gives produce type over 6 classes.
  - `p_spoil = softmax(W_sp z + b_sp)` gives Not_spoiled / Spoiled.
- **Attention:** `Attention(Q,K,V) = softmax(QKᵀ/√d_k)·V`, with 12 heads, d_k = 64, and 12 blocks over 196 patches plus the CLS token.
- **Loss:** `L = λ_type·CE(y_type, p_type) + λ_sp·CE(y_sp, p_spoil)` with λ = 1, 1, where `CE(y,p) = −Σ_k y_k log p_k`.
- **No regression head:** TR-6 has no measured time-to-endpoint labels, so no Huber or MSE term is used and the model produces no shelf-life output.
- **Checkpoint:** `artifacts/runs/vit_b16_primary/best.pt`, copied to `backend/models/foresight_vit.pt` (343 MB, SHA-256 prefix `49c40d4f65f94311`).
- **Run artefacts:** `config.json`, `history.json`/`history.csv`, `train_log.txt` and `val_predictions_best.csv` are next to the checkpoint.

## Training (one run, seed 42)
| Hyperparameter | Value | Justification |
|---|---|---|
| Input | 224×224 RGB; EXIF-corrected, shorter side 256, then resized to 224² | Matches the pretrained resolution. A resize keeps the whole fruit in frame. |
| Normalisation | mean = std = 0.5 | Taken from the pretrained checkpoint config, not fitted on TR-6 |
| Optimiser | AdamW, weight decay 0.01 | Standard choice for transformer fine-tuning |
| Learning rate | backbone 2e-5, heads 2e-4 | A conservative backbone LR (spec range 1e-5–5e-5). Newly initialised heads learn 10× faster. |
| Schedule | 1 epoch linear warm-up, then cosine decay per step | Smooth schedule for a pretrained transformer |
| Batch / epochs | 16 / up to 12 (all 12 ran) | Fits 16 GB unified memory (~20 img/s training on Apple M5 MPS) |
| Early stopping | patience 4 on validation composite macro-F1 | Never triggered: epoch 6 and epoch 9 each set a new best |
| Augmentation (train only) | resize 240 → random crop 224, H/V flip, ±15° rotation, brightness/contrast ±0.15 | No hue or saturation jitter, because colour is a spoilage cue |
| Selection | best `mean(val macro-F1_type, val macro-F1_spoil)` | The test split is never read during training |
| Gradient clipping | 1.0 | Stability |

The training data was 3,177 images, with 1,087 for validation. The run took 54.7 min on an Apple M5 (MPS), with torch 2.14.1 and timm 1.0.30.
The selected checkpoint is **epoch 9** (val produce macro-F1 1.000, val spoilage macro-F1 0.9716).
Only one seed was run, so no between-seed variance is reported.

## Held-out test results (n = 1,071, evaluated once after selection)
| Head | Accuracy | Macro-F1 | Weighted-F1 | ROC-AUC |
|---|---|---|---|---|
| Produce type (6) | 1.0000 | 1.0000 | 1.0000 | 1.000 (OvR macro) |
| Spoilage (2) | **0.9608** | **0.9536** | 0.9603 | **0.9893** |

| Spoilage class | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| Not_spoiled | 0.9527 | 0.9918 | 0.9718 | 731 |
| Spoiled | 0.9806 | **0.8941** | 0.9354 | 340 |

The spoilage confusion matrix (rows are true labels: Not_spoiled, Spoiled) is `[[725, 6], [36, 304]]`.

**Error analysis:** 42 of 1,071 test images are wrong.
- 33 are Indian Gooseberry: 27 of 102 Spoiled are missed, and 6 of 170 Not_spoiled are flagged as Spoiled.
- 7 are Tomato Spoiled (7 of 34 missed), and 2 are Mango Spoiled (2 of 34 missed).
- Banana, Carrot and Guava have no errors.
- The missed "Spoiled" gooseberries look visually fresh (`artifacts/experiments/xai/rollout_incorrect.png`). This is consistent with date-based folder labels that come before visible decay.

**Latency:** inference alone takes 14 ms per image when batched on MPS. End-to-end `/api/analyze` with a ~1.9 MB full-resolution upload has a median of **91 ms** (`artifacts/report/evidence/latency_benchmark.json`).

## Intended use and limits
- This is an educational prototype that gives a visual estimate for a **single** item from one of the 6 supported produce types. It is **not a food-safety guarantee.**
- **The metrics are optimistic for real use:**
  - Train and test share physical specimens, and 49 of 64 test sessions share a capture day with training.
  - The day-grouped sensitivity run (Table T8) shows how much this matters.
  - Images are lab photos with a plain background. Real phone photos have **not** been evaluated.
- Confidences are **uncalibrated** softmax scores, and the model is very confident even when it is wrong. The UI labels the ring "not-spoiled score", not "freshness".
- **Out-of-distribution inputs:** a photo of something else will still be mapped to one of the 6 classes. A warning is shown only when produce confidence is below 0.60, which is a heuristic that has not been validated.
- **UI tier thresholds are heuristics, not validated:** p(spoiled) ≥ 0.5 is shown as "Spoiled", and 0.30–0.50 is shown as "Uncertain".
- There is no shelf-life, no decay segmentation and no multi-item detection.

## Explainability
- **Method:** attention rollout (head-mean, +I, row-normalised, multiplied across 12 layers). It is returned with every API result and shown in the UI.
- **Faithfulness check** (`artifacts/experiments/xai/xai_summary.json`, n = 240 test images):
  - Occluding the top-20% rollout patches lowers the predicted-class probability by **0.192** on average.
  - Occluding 20% random patches lowers it by **0.020**.
  - Wilcoxon p = 2.3×10⁻³⁰.
  - The medians are close to 0 because most predictions are saturated.
- Rollout is an approximation: it ignores the MLP blocks and value vectors. It is a diagnostic, not proof of correctness.
