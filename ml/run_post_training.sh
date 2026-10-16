#!/usr/bin/env bash
# Everything that runs after the primary model is selected. Logs to artifacts/post_training.log.
# Order = priority: test evaluation, backend install, XAI, robustness, K-means/probe, DnCNN, ViT-S ablations.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
RUN=artifacts/runs/vit_b16_primary
log() { echo "[$(date +%H:%M:%S)] $*"; }

log "1. primary test evaluation (clean, untouched test split)"
$PY ml/evaluate/evaluate_vit.py --run $RUN --split test
mkdir -p backend/models
cp $RUN/best.pt backend/models/foresight_vit.pt
cp $RUN/eval/test_clean_0_none.json backend/models/foresight_vit_test_metrics.json

log "2. XAI"
$PY ml/experiments/xai_rollout.py --run $RUN

log "3. noise robustness (no denoiser, median)"
for d in none median; do
  for l in 0.05 0.1 0.2; do $PY ml/evaluate/evaluate_vit.py --run $RUN --split test --corruption gaussian --level $l --denoiser $d; done
  for l in 0.02 0.05 0.1; do $PY ml/evaluate/evaluate_vit.py --run $RUN --split test --corruption salt_pepper --level $l --denoiser $d; done
  for l in 0.1 0.3 0.5; do $PY ml/evaluate/evaluate_vit.py --run $RUN --split test --corruption speckle --level $l --denoiser $d; done
done

log "4. frozen-ViT features, linear probe, K-means"
for c in features probe kmeans; do $PY ml/experiments/baselines_kmeans.py $c --space vit_frozen; done

log "5. DnCNN"
$PY ml/experiments/dncnn.py train --minutes 10
for l in 0.05 0.1 0.2; do $PY ml/evaluate/evaluate_vit.py --run $RUN --split test --corruption gaussian --level $l --denoiser dncnn:artifacts/experiments/dncnn/dncnn.pt; done
for l in 0.02 0.05 0.1; do $PY ml/evaluate/evaluate_vit.py --run $RUN --split test --corruption salt_pepper --level $l --denoiser dncnn:artifacts/experiments/dncnn/dncnn.pt; done
for l in 0.1 0.3 0.5; do $PY ml/evaluate/evaluate_vit.py --run $RUN --split test --corruption speckle --level $l --denoiser dncnn:artifacts/experiments/dncnn/dncnn.pt; done

log "6. ViT-S/16 ablations (same split, same budget)"
S=vit_small_patch16_224.augreg_in21k_ft_in1k
ABL="--backbone $S --epochs 10 --patience 4 --batch-size 32 --lr 5e-5 --head-lr 5e-4"
$PY ml/train/train_vit.py --run-id vit_s16_aug $ABL --aug conventional
$PY ml/train/train_vit.py --run-id vit_s16_noaug $ABL --aug none
$PY - <<'EOF'
import csv
rows = list(csv.DictReader(open("artifacts/experiments/gan/generated_manifest.csv")))
with open("artifacts/experiments/gan/extra_train.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["path", "produce_class", "source_label"]); w.writeheader()
    for r in rows: w.writerow({k: r[k] for k in ("path", "produce_class", "source_label")})
EOF
$PY ml/train/train_vit.py --run-id vit_s16_aug_gan $ABL --aug conventional --extra-train-csv artifacts/experiments/gan/extra_train.csv
$PY ml/train/train_vit.py --run-id vit_s16_aug_daysplit $ABL --aug conventional --manifest artifacts/dataset/v1_daygroup_sensitivity/split_manifest.csv
for r in vit_s16_aug vit_s16_noaug vit_s16_aug_gan; do $PY ml/evaluate/evaluate_vit.py --run artifacts/runs/$r --split test; done
$PY ml/evaluate/evaluate_vit.py --run artifacts/runs/vit_s16_aug_daysplit --split test --manifest artifacts/dataset/v1_daygroup_sensitivity/split_manifest.csv

log "7. figures and tables"
$PY ml/evaluate/make_figures.py
log "DONE"
