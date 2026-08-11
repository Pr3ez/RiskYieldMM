# Clean RPF Walk-Forward Reset

## Purpose

Define the clean RPF-native walk-forward optimizer as the source of truth for
RPF model optimization.

## Current Status

The clean optimizer is implemented under
`regression_feature_engineering/walkforward/`. It is RPF-only: it loads
`regression_path_features_v1` directly, joins `distance_horizon_vol_v2` labels
by exact `timestamp,batch_id`, freezes sparse windows, and writes one stage
artifact tree under `test_output/rpf_clean_walkforward/`.

The first clean target is:

```text
target_reg_direction_extreme_up_share_hvol_v2
```

Binary classification experiments use the separate clean command surface:

```text
python -m regression_feature_engineering.walkforward.classify
```

The active binary targets are:

```text
target_cls_extreme_up_ge_2x_down_hvol_v2
target_cls_extreme_down_ge_2x_up_hvol_v2
```

They are experimental decision-layer targets. They must be evaluated together
and by regime; they are not a replacement for the six continuous hvol v2
regression/share targets listed below.

First real readiness passed on 2026-06-04 for `BTCUSDT 8h/B`: `2,530` RPF
model features, `5,856` available feature/label batch intersections,
`1,405,427` valid target rows, and `5` frozen windows were written under
`test_output/rpf_clean_walkforward/`.

A one-trial low-iteration baseline-probe smoke also completed and was correctly
rejected for `low_prediction_unique`. That verifies the training path and
collapse gate, but it is not model-quality evidence.

Old outputs under `test_output/stage1_regression_*` are historical and
exploratory. They may be used for comparison notes, but they are not the command
surface for RPF optimization.

## Scope

This reset covers clean RPF optimization for `BTCUSDT 8h/B` first. The code is
target-agnostic and can later run the six `distance_horizon_vol_v2` regression
targets:

```text
target_reg_distance_up_extreme_hvol_v2
target_reg_distance_up_mean_high_hvol_v2
target_reg_distance_down_mean_low_hvol_v2
target_reg_distance_down_extreme_hvol_v2
target_reg_direction_extreme_up_share_hvol_v2
target_reg_direction_mean_up_share_hvol_v2
```

## Source Of Truth

- CLI: `python -m regression_feature_engineering.walkforward.optimize`
- Package: `regression_feature_engineering/walkforward/`
- Default config: `regression_feature_engineering/configs/rpf_clean_walkforward_v1.json`
- Feature manifest authority: each RPF root `manifest.json` `feature_columns`
- Feature artifact example:
  `data/htf_multiasset/btcusdt/regression_path_features_v1/8h_b/1m/`
- Label artifact example:
  `data/htf_multiasset/btcusdt/htf_4class_labels_reg_distance_horizon_vol_v2/1m/`

## What This Does Not Decide

This document does not promote any RPF feature family or choose final CatBoost
hyperparameters. Promotion still requires validation-selected walk-forward
evidence.

## Data Contract

The clean runner loads only RPF features:

- read feature columns from RPF `manifest.json` `feature_columns`;
- exclude diagnostic `rpf_align_*` columns from model features;
- load label batches from the matching `distance_horizon_vol_v2` label root;
- exact join features and labels by `timestamp,batch_id`;
- require `target_reg_distance_valid_v2=true`;
- require the selected target to be non-null and finite;
- count sparse windows by available batch positions, not numeric batch-id
  continuity;
- never stale-fill missing feature or label batches.

The optimizer currently supports only:

```text
feature_source=regression_only
feature_policy=all_manifest_features
```

HTF-only is a separate baseline report, not part of clean RPF optimization.
The feature policy is fixed during the current optimization pass. Optuna may
not tune selected-feature count, Spearman threshold, dedupe threshold, clipping
quantiles, stability segments, or tail quantile yet. The current fixed policy
uses every model-facing column listed in the RPF manifest.

## Package Layout

```text
regression_feature_engineering/walkforward/
  data.py       RPF manifest, feature/label batch loading, exact joins
  windows.py    sparse-safe train/validation/prediction windows
  policy.py     fixed all-manifest feature policy and optional historical target-specific policy
  model.py      CatBoostRegressor params, early stopping, diagnostics
  metrics.py    standard and bounded-share target metrics
  optimize.py   staged Optuna CLI
  reports.py    JSON, parquet, Markdown, and event outputs
  config.py     clean optimizer config parsing
  classify.py   binary UP/DOWN RPF classifier and threshold/objective sweeps
```

## Stage Order

1. `readiness`
   - validates feature root, label root, target column, manifest counts, batch
     intersection, target distribution, and frozen sparse windows;
   - writes `readiness.json`, `batch_index.parquet`, `frozen_windows.parquet`,
     `stage_status.json`, `events.jsonl`, `trials.parquet`, and `best_config.json`.

2. `baseline_probe`
   - one-step Optuna probe for non-collapsing CatBoost basics;
   - tunes `iterations`, `depth`, `learning_rate`, `l2_leaf_reg`,
     `early_stopping_rounds`, and `od_wait`;
   - rejects constant or low-unique prediction collapse.

3. `geometry`
   - locks baseline model params;
   - tunes `lookback_batches`, `val_batches`, and `embargo_batches`.

4. `core_model`
   - locks window geometry and fixed feature policy;
   - tunes CatBoost model capacity and regularization.

5. `sampling`
   - locks previous stages;
   - tunes safe conditional CatBoost sampling params.

6. `confirmation`
   - runs locked configs on longer frozen windows;
   - uses prediction metrics only as confirmation, never as Optuna selection.

Every stage prints concise `[rpf-wf]` terminal events and writes the same
process state to `events.jsonl` for later debugging.

## Metrics And Rejection

CatBoost trains with `loss_function=RMSE` and `eval_metric=RMSE`. Optuna
selects configs by minimizing validation RMSE. Prediction metrics are used only
for collapse checks and final confirmation.

Finite categorical stages use Optuna `GridSampler`, so explicit choice lists
are not sampled with duplicate parameter tuples.

Every trial records standard metrics:

```text
MAE, RMSE, R2, Pearson, Spearman, bias
```

For bounded share targets it also records:

```text
target_std
pred_std
target_unique
pred_unique
spearman_null_reason
direction_accuracy_0p5
balanced_direction_accuracy_0p5
calibration_error_0p5
high_confidence_accuracy
```

Trials are rejected when prediction collapses:

```text
pred_unique <= min_prediction_unique
pred_std <= min_prediction_std
spearman_null_reason == constant_prediction
collapsed_window_rate > max_collapsed_window_rate
prediction_to_target_std_ratio < min_prediction_to_target_std_ratio
prediction_pred_unique_min <= 1
validation rows == 0
selected_features < min_selected_features
```

Every trial also compares model RMSE with naive baselines:

```text
constant_0p5
train_target_mean
validation_target_mean
previous_prediction_batch_mean
```

Promotion requires beating the train-target-mean baseline before direction or
rank metrics are interpreted as useful.

Each stage writes `window_metrics.parquet`. Readiness also writes
`label_window_index.parquet` and fails if label-window metadata shows
train/validation/prediction overlap.

## First Commands

Readiness:

```bash
/media/przem/linux_data/conda/envs/ml_env/bin/python \
  -m regression_feature_engineering.walkforward.optimize \
  --stage readiness \
  --asset BTCUSDT \
  --root 8h/B \
  --target-col target_reg_direction_extreme_up_share_hvol_v2 \
  --config regression_feature_engineering/configs/rpf_clean_walkforward_v1.json \
  --n-steps 20
```

One-step baseline probe:

```bash
/media/przem/linux_data/conda/envs/ml_env/bin/python \
  -m regression_feature_engineering.walkforward.optimize \
  --stage baseline_probe \
  --asset BTCUSDT \
  --root 8h/B \
  --target-col target_reg_direction_extreme_up_share_hvol_v2 \
  --config regression_feature_engineering/configs/rpf_clean_walkforward_v1.json \
  --base-run test_output/rpf_clean_walkforward/<readiness_run_id> \
  --n-steps 1 \
  --n-trials 18 \
  --task-type GPU
```

Geometry:

```bash
/media/przem/linux_data/conda/envs/ml_env/bin/python \
  -m regression_feature_engineering.walkforward.optimize \
  --stage geometry \
  --asset BTCUSDT \
  --root 8h/B \
  --target-col target_reg_direction_extreme_up_share_hvol_v2 \
  --config regression_feature_engineering/configs/rpf_clean_walkforward_v1.json \
  --base-run test_output/rpf_clean_walkforward/<baseline_probe_run_id> \
  --lookback-choices 80,120,160,180 \
  --val-choices 8,10,12 \
  --embargo-choices 0 \
  --n-steps 15 \
  --n-trials 12 \
  --task-type GPU
```

Core model, using the geometry run as the base:

```bash
/media/przem/linux_data/conda/envs/ml_env/bin/python \
  -m regression_feature_engineering.walkforward.optimize \
  --stage core_model \
  --asset BTCUSDT \
  --root 8h/B \
  --target-col target_reg_direction_extreme_up_share_hvol_v2 \
  --config regression_feature_engineering/configs/rpf_clean_walkforward_v1.json \
  --base-run test_output/rpf_clean_walkforward/<geometry_run_id> \
  --iterations-choices 400,800,1200 \
  --depth-choices 3,4 \
  --learning-rate-choices 0.005,0.01,0.02 \
  --l2-leaf-reg-choices 100,200,300 \
  --early-stopping-rounds-choices 50,100,150 \
  --od-wait-choices 50,100,150 \
  --n-steps 15 \
  --n-trials 18 \
  --task-type GPU
```

## Promotion Gate

The first clean target is not promoted unless the confirmation run shows:

- validation RMSE is stable across windows and improves over the previous
  locked stage;
- prediction RMSE does not degrade on the longer confirmation run;
- prediction RMSE beats the train-target-mean baseline;
- prediction Spearman is not null;
- direction accuracy beats the `0.5` baseline;
- no constant prediction collapse;
- early-stopping diagnostics are recorded;
- `events.jsonl`, `trials.parquet`, `window_metrics.parquet`, and
  `best_config.json` are sufficient to reproduce the selected run.
