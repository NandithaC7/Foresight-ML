#!/usr/bin/env bash
# DnCNN continuation (v2): resume the 1,065-step v1 checkpoint for 30 more minutes at lr 5e-4,
# then re-run the 9 corrupted-test evaluations as a separate "dncnn2" denoiser condition.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
until grep -q DAYSPLIT_V2_DONE artifacts/daysplit_v2.log 2>/dev/null; do sleep 30; done
echo "[$(date +%H:%M:%S)] dncnn v2 training"
$PY ml/experiments/dncnn.py train --out artifacts/experiments/dncnn_v2 --minutes 30 --lr 5e-4 --init-from artifacts/experiments/dncnn/dncnn.pt | tail -8
D=dncnn2:artifacts/experiments/dncnn_v2/dncnn.pt
for l in 0.05 0.1 0.2; do $PY ml/evaluate/evaluate_vit.py --run artifacts/runs/vit_b16_primary --split test --corruption gaussian --level $l --denoiser $D --tag test_gaussian_${l}_dncnn2; done
for l in 0.02 0.05 0.1; do $PY ml/evaluate/evaluate_vit.py --run artifacts/runs/vit_b16_primary --split test --corruption salt_pepper --level $l --denoiser $D --tag test_salt_pepper_${l}_dncnn2; done
for l in 0.1 0.3 0.5; do $PY ml/evaluate/evaluate_vit.py --run artifacts/runs/vit_b16_primary --split test --corruption speckle --level $l --denoiser $D --tag test_speckle_${l}_dncnn2; done
echo "[$(date +%H:%M:%S)] DNCNN_V2_DONE"
