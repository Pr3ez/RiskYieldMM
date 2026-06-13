# RPF Walk-Forward Optimization Report

## Purpose

Explain how the current clean RPF-native walk-forward optimization and
backtesting path works, step by step.

## Current Status

The active RPF optimizer is implemented under
`regression_feature_engineering/walkforward/` and is launched with:

```bash
python -m regression_feature_engineering.walkforward.optimize
```

The current optimization scope is intentionally narrow:

- optimize walk-forward window geometry;
- optimize CatBoost hyperparameters;
- keep feature policy fixed;
- keep RPF feature formulas fixed;
- keep the target fixed unless a separate run is started for another target.

The first clean target is:

```text
target_reg_direction_extreme_up_share_hvol_v2
```

The latest readiness run shown by the user completed successfully:

```text
run:        test_output/rpf_clean_walkforward/20260604_102448_readiness_btcusdt_8h_b_target_reg_direction_extreme_up_sha_2d5c0524
features:   2,530
batches:    5,856
windows:    20
valid rows: 1,405,427
```

## Scope

This report covers clean RPF optimization for:

```text
asset:   BTCUSDT
root:    8h/B
target:  target_reg_direction_extreme_up_share_hvol_v2
source:  regression_path_features_v1
labels:  distance_horizon_vol_v2
```

The optimizer is target-agnostic and can later be run for:

```text
target_reg_distance_up_extreme_hvol_v2
target_reg_distance_up_mean_high_hvol_v2
target_reg_distance_down_mean_low_hvol_v2
target_reg_distance_down_extreme_hvol_v2
target_reg_direction_extreme_up_share_hvol_v2
target_reg_direction_mean_up_share_hvol_v2
```

## Source Of Truth

- CLI: `regression_feature_engineering/walkforward/optimize.py`
- Data loading: `regression_feature_engineering/walkforward/data.py`
- Window planning: `regression_feature_engineering/walkforward/windows.py`
- Fixed train-only feature policy: `regression_feature_engineering/walkforward/policy.py`
- CatBoost model boundary: `regression_feature_engineering/walkforward/model.py`
- Metrics and collapse rules: `regression_feature_engineering/walkforward/metrics.py`
- Default config: `regression_feature_engineering/configs/rpf_clean_walkforward_v1.json`
- Reset contract: `clean_rpf_walkforward_reset.md`

## What This Does Not Decide

This report does not promote a model, feature family, target, or final
hyperparameter set. It documents how the current optimizer works so the next
runs are interpreted correctly.

## Important Bash Detail

Set the Python executable before using commands that start with `$PY`:

```bash
export PY="/media/przem/linux_data/conda/envs/ml_env/bin/python"
```

Verify it is not empty:

```bash
echo "$PY"
"$PY" --version
```

If `$PY` is empty and the command starts with unquoted `$PY`, Bash expands:

```bash
$PY -m regression_feature_engineering.walkforward.optimize
```

into:

```bash
-m regression_feature_engineering.walkforward.optimize
```

and the shell correctly fails with:

```text
-m: command not found
```

Do not paste placeholder text such as:

```bash
--base-run test_output/rpf_clean_walkforward/<readiness_run_id>
```

In Bash, `<readiness_run_id>` is treated as input redirection, which caused:

```text
bash: readiness_run_id: No such file or directory
```

Use either the actual run directory:

```bash
READINESS_RUN="test_output/rpf_clean_walkforward/20260604_102448_readiness_btcusdt_8h_b_target_reg_direction_extreme_up_sha_2d5c0524"
```

or select the latest readiness run automatically:

```bash
READINESS_RUN="$(ls -td test_output/rpf_clean_walkforward/*_readiness_* | head -1)"
```

Then pass:

```bash
--base-run "$READINESS_RUN"
```

## Data Contract

The clean optimizer does not use the old Stage-1 merged feature root as its
command surface.

It reads RPF features directly from the active per-asset RPF feature root. For
the first benchmark this is:

```text
data/htf_multiasset/btcusdt/regression_path_features_v1/8h_b/1m/
```

It reads labels directly from the matching hvol v2 label root. For the first
benchmark this is:

```text
data/htf_multiasset/btcusdt/htf_4class_labels_reg_distance_horizon_vol_v2/1m/
```

Model feature columns come only from the RPF manifest `feature_columns`.
Diagnostic columns such as `rpf_align_*` are excluded from model features.

Rows are valid only when all of these are true:

- feature batch and label batch both exist;
- `timestamp,batch_id` match exactly;
- `target_reg_distance_valid_v2=true`;
- selected target column is non-null;
- selected target column is finite;
- selected model features are non-null and finite after fixed selection and
  clipping.

There is no stale fill, no as-of fill across missing batches, and no numeric
batch-id continuity assumption.

## Sparse Window Logic

Readiness builds a dense available-position index from actual feature/label
batch intersections.

For every available prediction batch, the window is:

```text
train batches -> validation batches -> embargo gap -> prediction batch
```

The counts are by available batch position, not by numeric `batch_id`.

Example with current defaults:

```text
lookback_batches = 120
val_batches      = 10
embargo_batches  = 0
```

That means each prediction step uses:

- `120` previous available batches for training;
- next `10` available batches for validation and early stopping;
- no embargo gap by default;
- one next available batch as prediction/backtest output.

The frozen windows are written to:

```text
frozen_windows.parquet
```

Later stages replay those windows from the previous stage unless the stage is
`geometry`.

Only `readiness` and `geometry` need to scan the full feature/label batch
intersection. `baseline_probe`, `core_model`, `sampling`, and `confirmation`
reuse the base run's `frozen_windows.parquet` and do not rescan the full RPF
root just to plan windows.

When the batch index is built, parquet scans ignore stray extra columns outside
the expected schema. Required columns such as `timestamp`, `batch_id`, the
selected target, and `target_reg_distance_valid_v2` are still mandatory.

Readiness also builds `label_window_index.parquet` from:

```text
label_window_start
label_window_end
label_window_batch_id
target_reg_distance_horizon_minutes_v2
```

The stage fails if train label windows overlap validation rows, validation
label windows overlap prediction rows, or `embargo_batches=0` while labels
cross their own source batch. Self-contained labels are required before a zero
embargo run is considered safe.

## What Is Optimized Now

Only these groups are optimized now.

### Window Geometry

Stage: `geometry`

Optuna may tune:

```text
lookback_batches
val_batches
embargo_batches
```

This decides how much history trains each fold, how large the validation split
is, and whether there is a gap before the prediction batch.

### Core CatBoost Hyperparameters

Stages: `baseline_probe`, `core_model`

Optuna may tune:

```text
iterations
depth
learning_rate
l2_leaf_reg
early_stopping_rounds
od_wait
```

`baseline_probe` is a small first pass to avoid immediately launching a heavy
study with a model that collapses to constant predictions.

`core_model` uses locked geometry and tunes model capacity more seriously.

### CatBoost Sampling And Regularization

Stage: `sampling`

Optuna may tune:

```text
bootstrap_type
bagging_temperature
subsample
random_strength
border_count
```

Conditional rules are enforced:

- `bagging_temperature` is valid only with `bootstrap_type=Bayesian`;
- `subsample` requires `bootstrap_type=Bernoulli` or `Poisson`;
- `Poisson` is GPU-only.

## What Is Not Optimized Now

The following are fixed during the current pass:

```text
feature_source
feature_policy
feature_ablation
RPF feature formulas
RPF feature lookbacks
target formula
asset/root scope
```

The config records this explicitly:

```json
"optimization_scope": {
  "tune_window_geometry": true,
  "tune_catboost_hyperparameters": true,
  "tune_feature_policy": false
}
```

The clean CLI rejects `--stage feature_policy`.

If `--base-run` points to an older readiness directory, the optimizer may load
old locked window/model state from that run, but the fixed feature contract is
always taken from the current config file. This prevents stale exploratory
configs such as `target_specific_v2/max_features=300` from silently replacing
the current `all_manifest_features` policy. When this happens the terminal logs:

```text
[rpf-wf] fixed_policy_override old_policy=target_specific_v2 new_policy=all_manifest_features old_features=300 new_features=all
```

## Fixed Feature Policy During Training

The clean optimizer defaults to all model-facing RPF features listed in the
manifest. It does not run target-specific Spearman filtering, feature count
capping, dedupe filtering, or train-quantile clipping.

Current fixed policy:

```text
policy:        all_manifest_features
feature count: all manifest feature_columns, currently 2,530 for BTCUSDT 8h/B
max_features:  0, meaning no feature-count cap
```

For explicit panel-confirmation runs, the fixed policy may be:

```text
policy: frozen_panel
source: selected_panel_<n>.json from regression_feature_engineering.walkforward.panel_select
```

This still is not Optuna feature-policy tuning. The panel is selected before
the walk-forward run, frozen to JSON, and consumed through:

```bash
--frozen-panel-path test_output/rpf_feature_panels/<run_id>/selected_panel_<n>.json
```

`feature_ablation` is a fixed manifest mask, not train-time feature selection.
The default is:

```text
feature_ablation: all
```

Later controlled ablation runs can use values such as
`only_volatility_state`, `minus_volatility_state`, or
`group_volatility_state+structural_room`.

For each fold:

1. Start from manifest model feature columns.
2. Use every listed model feature, or every feature listed in the frozen panel.
3. Do not rank, drop, dedupe, or cap features during the walk-forward run.
4. Do not compute train-quantile clip bounds.
5. Let `frame_to_numpy` drop rows only if target or selected feature values are
   null or nonfinite.

This is the intended current behavior because the RPF backtest should first
evaluate the full engineered feature surface before any feature-selection
policy is introduced.

## Per-Window Backtest Flow

For every frozen window in a trial:

1. Load explicit train batch ids.
2. Load explicit validation batch ids.
3. Load one prediction batch id.
4. Join feature and label rows exactly by `timestamp,batch_id`.
5. Filter valid target rows.
6. Use all manifest model features.
7. Convert Polars frames to NumPy matrices.
8. Fit `CatBoostRegressor` on train rows.
9. Use validation rows as CatBoost `eval_set`.
10. Use `use_best_model=True`.
11. Apply early stopping with the configured values.
12. Predict validation rows.
13. Predict the held-out prediction batch.
14. Store validation and prediction arrays for aggregate metrics.

The prediction batch is the walk-forward backtest batch. It is never used for
training or early stopping.

## Trial Scoring

Each Optuna trial aggregates validation predictions across the selected
windows, then computes validation metrics.

CatBoost training uses:

```text
loss_function = RMSE
eval_metric   = RMSE
eval_set      = validation rows
```

Early stopping is driven by validation RMSE through CatBoost's eval metric.

Optuna config selection also uses validation RMSE only. The stored objective is:

```text
objective_metric = validation_rmse
objective_direction = minimize
objective_value = validation_rmse
```

The Optuna study runs with `direction="minimize"`, so the best trial is the
lowest validation RMSE. Spearman, Pearson, direction accuracy, calibration, and
tail metrics are still recorded for diagnostics, but they do not choose the best
trial in the current pass.

Finite categorical stages use Optuna `GridSampler`, not TPE, so explicit
choice lists are tested without repeating the same parameter tuple. This is
important for `geometry`, `baseline_probe`, and `core_model`, where the search
space is made from fixed CLI choices.

The current implementation also uses prediction-batch metrics as a safety gate
for collapse rejection. It does not positively rank trials by prediction
metrics, but it rejects a trial if prediction output collapses.

Collapse rejection defaults:

```text
pred_unique <= 10
pred_std <= 1e-6
spearman_null_reason == constant_prediction
collapsed_window_rate > 0.25
prediction_to_target_std_ratio < 0.10
prediction_pred_unique_min <= 1
no prediction rows
selected features below minimum
```

`confirmation` records the same collapse fields, but does not use them to
select another config. It is a replay/report stage.

If rejected, the trial objective value is forced to:

```text
1e9
```

This is why the tiny one-trial smoke was marked:

```text
rejected:low_prediction_unique
```

That was correct behavior because the prediction batch had one unique
prediction value.

## Metrics Written

Every trial writes validation and prediction versions of:

```text
rows
mae
rmse
median_abs_error
r2
pearson
spearman
spearman_null_reason
bias
target_mean
pred_mean
target_std
pred_std
target_unique
pred_unique
target_p50
pred_p50
target_p95
pred_p95
p95_coverage_ratio
tail_rows
tail_mae
tail_rmse
direction_accuracy_0p5
balanced_direction_accuracy_0p5
calibration_error_0p5
high_confidence_rows
high_confidence_accuracy
```

Every trial also writes naive RMSE baselines for validation and prediction:

```text
baseline_constant_0p5_rmse
baseline_train_target_mean_rmse
baseline_validation_target_mean_rmse
baseline_previous_prediction_batch_mean_rmse
model_rmse_minus_train_mean_baseline
beats_train_mean_baseline
```

Per-window collapse and under-dispersion diagnostics are written both to
`window_metrics.parquet` and aggregated into `trials.parquet`:

```text
prediction_pred_unique_min
prediction_pred_std_min
prediction_pred_std_mean
collapsed_window_count
collapsed_window_rate
prediction_to_target_std_ratio
prediction_mean_bias
```

Every model stage also writes `window_metrics.parquet` with per-window
validation/prediction metrics, timestamp ranges, train/validation/prediction
row counts, target distributions, selected feature count, and CatBoost best
iteration diagnostics. Readiness writes a window-level label-safety table to the
same artifact path.

For the share target, the most important diagnostics are:

- `spearman`;
- `pred_std`;
- `pred_unique`;
- `direction_accuracy_0p5`;
- `balanced_direction_accuracy_0p5`;
- `calibration_error_0p5`;
- `high_confidence_accuracy`;
- `spearman_null_reason`.

## Stage Artifacts

Every stage writes under:

```text
test_output/rpf_clean_walkforward/{run_id}/
```

Common artifacts:

```text
events.jsonl
stage_status.json
trials.parquet
window_metrics.parquet
best_config.json
locked_{stage}_config.json
frozen_windows.parquet
report.md
```

Readiness also writes:

```text
readiness.json
batch_index.parquet
label_window_index.parquet
```

Readiness records feature family counts, manifest integrity, target zero/one
rates, and train/validation/prediction target drift for every frozen window.

`trials.parquet` contains both the full `config_json` and flat audit columns
for the active tuple, including `lookback_batches`, `val_batches`,
`embargo_batches`, `iterations`, `depth`, `learning_rate`, `l2_leaf_reg`,
`early_stopping_rounds`, `od_wait`, `feature_ablation`, and
`feature_count_mode`. It also records `ablation_feature_count`.

The terminal also prints concise progress lines:

```text
[rpf-wf] stage_start ...
[rpf-wf] readiness_done ...
[rpf-wf] trial_start ...
[rpf-wf] trial_done ...
[rpf-wf] stage_best ...
[rpf-wf] stage_done ...
```

## Current Stage Details

### Stage 1: Readiness

Command:

```bash
READINESS_RUN="$(
  "$PY" -m regression_feature_engineering.walkforward.optimize \
    --stage readiness \
    --asset BTCUSDT \
    --root 8h/B \
    --target-col target_reg_direction_extreme_up_share_hvol_v2 \
    --config regression_feature_engineering/configs/rpf_clean_walkforward_v1.json \
    --n-steps 20 \
  | tee /tmp/rpf_readiness.log \
  | awk '/stage_done/ {for (i=1; i<=NF; i++) if ($i ~ /^run=/) {sub(/^run=/, "", $i); print $i}}'
)"
```

Simpler command using your completed run:

```bash
READINESS_RUN="test_output/rpf_clean_walkforward/20260604_102448_readiness_btcusdt_8h_b_target_reg_direction_extreme_up_sha_2d5c0524"
```

Optimizes:

```text
nothing
```

Validates and writes:

```text
RPF manifest
label root
target existence
feature/label batch intersection
valid target row count
target distribution
frozen sparse windows
```

### Stage 2: Baseline Probe

Command:

```bash
"$PY" -m regression_feature_engineering.walkforward.optimize \
  --stage baseline_probe \
  --asset BTCUSDT \
  --root 8h/B \
  --target-col target_reg_direction_extreme_up_share_hvol_v2 \
  --config regression_feature_engineering/configs/rpf_clean_walkforward_v1.json \
  --base-run "$READINESS_RUN" \
  --iterations-choices 400,800,1200 \
  --depth-choices 3,4 \
  --learning-rate-choices 0.005,0.01,0.02 \
  --l2-leaf-reg-choices 100,200,300 \
  --early-stopping-rounds-choices 50,100,150 \
  --od-wait-choices 50,100,150 \
  --n-steps 1 \
  --n-trials 18 \
  --task-type GPU
```

Optimizes:

```text
iterations
depth
learning_rate
l2_leaf_reg
early_stopping_rounds
od_wait
```

Does not optimize:

```text
window geometry
feature policy
feature formulas
```

Purpose:

```text
Find a non-collapsing baseline CatBoost setting before heavier geometry and
model-capacity runs.
```

### Stage 3: Geometry

Set base run:

```bash
BASELINE_RUN="$(ls -td test_output/rpf_clean_walkforward/*_baseline_probe_* | head -1)"
```

Command:

```bash
"$PY" -m regression_feature_engineering.walkforward.optimize \
  --stage geometry \
  --asset BTCUSDT \
  --root 8h/B \
  --target-col target_reg_direction_extreme_up_share_hvol_v2 \
  --config regression_feature_engineering/configs/rpf_clean_walkforward_v1.json \
  --base-run "$BASELINE_RUN" \
  --lookback-choices 80,120,160,180 \
  --val-choices 8,10,12 \
  --embargo-choices 0 \
  --n-steps 15 \
  --n-trials 12 \
  --task-type GPU
```

Optimizes:

```text
lookback_batches
val_batches
embargo_batches
```

Uses:

```text
baseline model params from the base run
fixed feature policy from config
```

Output:

```text
best_config.json
locked_geometry_config.json
frozen_windows.parquet
```

### Stage 4: Core Model

Set base run:

```bash
GEOMETRY_RUN="$(ls -td test_output/rpf_clean_walkforward/*_geometry_* | head -1)"
```

Command:

```bash
"$PY" -m regression_feature_engineering.walkforward.optimize \
  --stage core_model \
  --asset BTCUSDT \
  --root 8h/B \
  --target-col target_reg_direction_extreme_up_share_hvol_v2 \
  --config regression_feature_engineering/configs/rpf_clean_walkforward_v1.json \
  --base-run "$GEOMETRY_RUN" \
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

Optimizes:

```text
iterations
depth
learning_rate
l2_leaf_reg
early_stopping_rounds
od_wait
```

Locks:

```text
window geometry from geometry stage
fixed feature policy from config
```

### Stage 5: Sampling

Set base run:

```bash
CORE_RUN="$(ls -td test_output/rpf_clean_walkforward/*_core_model_* | head -1)"
```

Command:

```bash
"$PY" -m regression_feature_engineering.walkforward.optimize \
  --stage sampling \
  --asset BTCUSDT \
  --root 8h/B \
  --target-col target_reg_direction_extreme_up_share_hvol_v2 \
  --config regression_feature_engineering/configs/rpf_clean_walkforward_v1.json \
  --base-run "$CORE_RUN" \
  --bootstrap-type-choices None,Bayesian,Bernoulli \
  --bagging-temperature-choices 0.25,0.5,1.0 \
  --subsample-choices 0.66,0.8,0.9 \
  --random-strength-choices 1,5,10 \
  --border-count-choices 64,128,254 \
  --n-steps 15 \
  --n-trials 18 \
  --task-type GPU
```

Optimizes:

```text
bootstrap_type
bagging_temperature
subsample
random_strength
border_count
```

Locks:

```text
geometry
core CatBoost params
fixed feature policy
```

### Stage 6: Confirmation

Set base run:

```bash
SAMPLING_RUN="$(ls -td test_output/rpf_clean_walkforward/*_sampling_* | head -1)"
```

Command:

```bash
"$PY" -m regression_feature_engineering.walkforward.optimize \
  --stage confirmation \
  --asset BTCUSDT \
  --root 8h/B \
  --target-col target_reg_direction_extreme_up_share_hvol_v2 \
  --config regression_feature_engineering/configs/rpf_clean_walkforward_v1.json \
  --base-run "$SAMPLING_RUN" \
  --n-steps 100 \
  --n-trials 1 \
  --task-type GPU
```

Optimizes:

```text
nothing
```

Purpose:

```text
Replay the locked config over a longer frozen walk-forward window and inspect
prediction metrics as confirmation evidence.
```

Current implementation note: confirmation is still implemented through the same
Optuna stage wrapper, so use `--n-trials 1` to avoid repeated identical trials.

## How To Inspect Results

Latest run:

```bash
export RUN="$(ls -td test_output/rpf_clean_walkforward/* | head -1)"
echo "$RUN"
```

Stage status:

```bash
python - <<'PY'
import json, os
from pathlib import Path
run = Path(os.environ["RUN"])
print(json.dumps(json.loads((run / "stage_status.json").read_text()), indent=2)[:4000])
PY
```

Trials:

```bash
python - <<'PY'
import os
from pathlib import Path
import polars as pl
run = Path(os.environ["RUN"])
df = pl.read_parquet(run / "trials.parquet")
cols = [c for c in [
    "trial_number",
    "status",
    "objective_value",
    "validation_spearman",
    "validation_rmse",
    "prediction_spearman",
    "prediction_pred_std",
    "prediction_pred_unique",
] if c in df.columns]
print(df.select(cols).sort("objective_value").head(20))
PY
```

Events:

```bash
tail -n 20 "$RUN/events.jsonl"
```

Frozen windows:

```bash
python - <<'PY'
import os
from pathlib import Path
import polars as pl
run = Path(os.environ["RUN"])
print(pl.read_parquet(run / "frozen_windows.parquet").select([
    "step_idx",
    "pred_batch_id",
    "train_batch_count",
    "val_batch_count",
]).tail(10))
PY
```

## Interpretation Rules

Use validation metrics to choose among trials in the same stage.

Use prediction metrics to detect collapse and confirm final behavior.

Do not compare runs that used different:

- target columns;
- root IDs;
- number of frozen windows;
- prediction batch windows;
- feature-policy config;
- RPF feature materialization state.

Do not promote from one-step baseline-probe results. One-step probe is only a
collapse and plumbing check.

## Current Known Gaps

The current clean runner is usable, but these debug improvements are still
worth adding later:

- persist per-window selected feature lists;
- persist per-window clip bounds;
- persist validation and prediction row-level outputs;
- add a dedicated non-Optuna confirmation command;
- add same-window HTF baseline reporting outside the RPF optimizer.
