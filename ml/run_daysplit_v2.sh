#!/usr/bin/env bash
# Day-grouped split sensitivity at the controlled ablation-v2 configuration (ViT-S/16, conventional aug,
# lr 2e-5/2e-4, batch 32, <=10 epochs, patience 4), seeds 42-44. Paired with abl2_aug_s{42,43,44}
# which use the identical configuration on the session-grouped split v1.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
until grep -q ABLATION_V2_DONE artifacts/ablation_v2.log 2>/dev/null; do sleep 30; done
S=vit_small_patch16_224.augreg_in21k_ft_in1k
M=artifacts/dataset/v1_daygroup_sensitivity/split_manifest.csv
for seed in 42 43 44; do
  id=day2_aug_s${seed}
  if [ -f artifacts/runs/$id/eval/test_clean_0_none.json ]; then continue; fi
  echo "[$(date +%H:%M:%S)] train $id"
  $PY ml/train/train_vit.py --run-id $id --backbone $S --epochs 10 --patience 4 --batch-size 32 --lr 2e-5 --head-lr 2e-4 \
      --aug conventional --seed $seed --manifest $M 2>&1 | grep -E "early stop|best val|Traceback|Error" || true
  $PY ml/evaluate/evaluate_vit.py --run artifacts/runs/$id --split test --manifest $M 2>&1 | grep -v Warn
done
echo "[$(date +%H:%M:%S)] DAYSPLIT_V2_DONE"
