#!/usr/bin/env bash
# Controlled augmentation / GAN ablation (v2): ViT-S/16, 3 conditions x 3 seeds.
# Fixes the v1 issue (lr 5e-5 made the conventional-aug run unstable) by using the
# primary model's LR (2e-5 backbone / 2e-4 heads). Everything else is held constant:
# split v1, backbone, batch 32, max 10 epochs, patience 4, selection on val composite macro-F1.
# The GAN images are the same 480 train-only samples for every seed (GAN seed 42).
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
S=vit_small_patch16_224.augreg_in21k_ft_in1k
COMMON="--backbone $S --epochs 10 --patience 4 --batch-size 32 --lr 2e-5 --head-lr 2e-4"
log() { echo "[$(date +%H:%M:%S)] $*"; }
for seed in 42 43 44; do
  for cond in noaug aug gan; do
    id=abl2_${cond}_s${seed}
    if [ -f artifacts/runs/$id/eval/test_clean_0_none.json ]; then log "skip $id (done)"; continue; fi
    case $cond in
      noaug) extra="--aug none" ;;
      aug)   extra="--aug conventional" ;;
      gan)   extra="--aug conventional --extra-train-csv artifacts/experiments/gan/extra_train.csv" ;;
    esac
    log "train $id"
    $PY ml/train/train_vit.py --run-id $id $COMMON $extra --seed $seed 2>&1 | grep -E "early stop|best val|Traceback|Error" || true
    $PY ml/evaluate/evaluate_vit.py --run artifacts/runs/$id --split test 2>&1 | grep -v Warn
  done
done
log "ABLATION_V2_DONE"
