# RPF Binary Classification Experiment

## Purpose

Define the first RPF-native classification target and command surface.

## Current Status

Status: experimental runner implemented with validation-selected decision
threshold support.

Command:

```bash
python -m regression_feature_engineering.walkforward.classify
```

Outputs:

```text
test_output/rpf_clean_classification/
```

## Scope

First upside target:

```text
target_cls_extreme_up_ge_2x_down_hvol_v2
```

Positive class rule:

```text
target_reg_distance_up_extreme_hvol_v2 > 0
and
target_reg_distance_up_extreme_hvol_v2 >= 2 * target_reg_distance_down_extreme_hvol_v2
```

Symmetric downside target:

```text
target_cls_extreme_down_ge_2x_up_hvol_v2
```

Positive class rule:

```text
target_reg_distance_down_extreme_hvol_v2 > 0
and
target_reg_distance_down_extreme_hvol_v2 >= 2 * target_reg_distance_up_extreme_hvol_v2
```

This is a directional classification target, not a distance-size regression
target.

## Source Of Truth

- Runner: `regression_feature_engineering/walkforward/classify.py`
- RPF features: `data/htf_multiasset/{asset}/regression_path_features_v1/{root_id}/1m/`
- Labels: `distance_horizon_vol_v2`
- Window source: existing clean RPF `frozen_windows.parquet`

## What This Does Not Decide

This experiment does not replace the four hvol v2 regression targets. It tests
whether a cleaner directional event target is easier to predict than bounded
share regression.

## Metrics

Each run writes validation and prediction metrics:

```text
logloss
brier
accuracy
balanced_accuracy
precision
recall
f1
auc
positive_rate
predicted_positive_rate
prob_mean
prob_std
prob_unique
false_positive_rate
false_negative_rate
false_discovery_rate
decision_cost
decision_cost_per_row
utility
utility_per_row
selected_threshold
```

CatBoost still trains with `Logloss`. The model-selection objective can now be
set separately:

```text
validation_logloss
validation_decision_cost
validation_false_positive_rate
validation_precision
validation_fbeta
validation_balanced_accuracy
```

For trading-decision experiments, prefer:

```bash
--threshold-mode validation_sweep
--objective-metric validation_decision_cost
--fp-cost 5
--fn-cost 1
--min-validation-recall 0.10
--min-validation-predicted-positive-rate 0.02
```

The threshold is selected from validation predictions only, then applied
unchanged to prediction batches.

## First Command

```bash
PY="/media/przem/linux_data/conda/envs/ml_env/bin/python"
READINESS_RUN="$(ls -td test_output/rpf_clean_walkforward/*_readiness_* | head -1)"

"$PY" -m regression_feature_engineering.walkforward.classify \
  --asset BTCUSDT \
  --root 8h/B \
  --base-run "$READINESS_RUN" \
  --target-col target_cls_extreme_up_ge_2x_down_hvol_v2 \
  --feature-ablation only_structural_room \
  --n-steps 15 \
  --max-configs 12 \
  --task-type GPU
```

## Interpretation

For this experiment, a useful run should beat naive class baselines through:

- validation logloss;
- prediction AUC;
- prediction balanced accuracy;
- non-collapsed probability dispersion.

If `only_structural_room` works, compare focused groups before trying all RPF
features.

## Cost-Sensitive 15-Step Comparison

Use this to compare objective choices without changing the 12 CatBoost configs:

```bash
PY="/media/przem/linux_data/conda/envs/ml_env/bin/python"
READINESS_RUN="$(ls -td test_output/rpf_clean_walkforward/*_readiness_* | head -1)"
FEATURE_ABLATION="group_structural_room+liquidity_volume_pressure+interaction_confluence"

for TARGET in \
  target_cls_extreme_up_ge_2x_down_hvol_v2 \
  target_cls_extreme_down_ge_2x_up_hvol_v2
do
  for OBJECTIVE in \
    validation_logloss \
    validation_decision_cost \
    validation_precision \
    validation_fbeta \
    validation_balanced_accuracy
  do
    "$PY" -m regression_feature_engineering.walkforward.classify \
      --asset BTCUSDT \
      --root 8h/B \
      --target-col "$TARGET" \
      --base-run "$READINESS_RUN" \
      --feature-ablation "$FEATURE_ABLATION" \
      --n-steps 15 \
      --max-configs 12 \
      --objective-metric "$OBJECTIVE" \
      --threshold-mode validation_sweep \
      --fp-cost 5 \
      --fn-cost 1 \
      --fbeta-beta 0.5 \
      --min-validation-recall 0.10 \
      --min-validation-predicted-positive-rate 0.02 \
      --iterations-choices 400,800 \
      --depth-choices 2,3 \
      --learning-rate-choices 0.01,0.02 \
      --l2-leaf-reg-choices 10,30 \
      --early-stopping-rounds-choices 100 \
      --od-wait-choices 100 \
      --task-type GPU
  done
done
```
