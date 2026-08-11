# RPF Overfit Control Protocol

## Purpose

Define the RPF walk-forward protocol used to search for stable, good-quality
binary predictions without overfitting to validation windows or repeatedly
reused prediction batches.

## Current Status

Status: implemented as the active protocol for
`python -m regression_feature_engineering.walkforward.classify`.

The classifier now supports:

- train-only ElasticNet feature selection feeding CatBoost;
- train-only ElasticNet candidate prefiltering for practical runtime;
- prediction-batch trial scoring through `--trial-objective-split prediction`;
- reserved untouched holdout replay through `--holdout-steps`.

## Scope

Primary scope:

```text
asset: BTCUSDT
root: 8h/B
targets:
  target_cls_extreme_up_ge_2x_down_hvol_v2
  target_cls_extreme_down_ge_2x_up_hvol_v2
features: regression_path_features_v1
model: ElasticNet selector -> CatBoost classifier
```

## Source Of Truth

- Classifier CLI: `regression_feature_engineering/walkforward/classification/cli.py`
- Fold runner: `regression_feature_engineering/walkforward/classification/runner.py`
- Selector policy: `regression_feature_engineering/walkforward/policy.py`
- Metrics: `regression_feature_engineering/walkforward/classification/metrics.py`
- Binary experiment doc: `rpf_binary_classification_experiment.md`
- Scaling contract: `feature_scaling_contract.md`

Trusted references:

- scikit-learn `TimeSeriesSplit`: time-ordered splits are required where
  ordinary cross-validation would train on future data; its `gap` parameter
  excludes samples before the test set.
- CatBoost `eval_set`: validation data is used for overfitting detection,
  best-iteration selection, and metric monitoring.
- CatBoost overfitting detector: training can stop before the requested tree
  count when validation evidence stops improving.
- Optuna `create_study`: optimization direction must be explicit and aligned
  with the selected metric.

## What This Does Not Decide

This document does not promote a model. It defines how future evidence must be
collected so that promotion evidence is not contaminated by validation or
tuning reuse.

## Split Roles

Every fold has these roles:

```text
Train
-> fit selector scaler
-> fit ElasticNet selector
-> fit CatBoost validation model

Validation
-> CatBoost early stopping / best iteration
-> threshold selection
-> validation sanity gates

Prediction batch
-> out-of-sample fold score for grid/Optuna tuning

Reserved holdout windows
-> final replay only after best tuning config is selected
```

Validation is allowed to build the fold model. Prediction batches are allowed
to select a run config. Reserved holdout windows are not allowed to affect
feature selection, threshold selection, CatBoost parameters, ElasticNet
parameters, or config selection.

## Why Holdout Is Required

Once `--trial-objective-split prediction` is used, prediction batches become
tuning evidence. They are better than validation for trial scoring because
validation already influenced early stopping and threshold choice, but they are
not final proof after repeated grid/Optuna search.

Therefore every serious run must reserve recent windows:

```text
--n-steps 50
--holdout-steps 20
```

This means:

```text
30 tuning prediction windows -> choose best trial
20 untouched holdout windows -> replay selected best trial once
```

The classifier writes separate holdout artifacts:

```text
holdout_summary.json
holdout_window_metrics.parquet
holdout_validation_scores.parquet
holdout_prediction_scores.parquet
holdout_selected_features.parquet
```

These files are confirmation evidence only.

## Overfit Controls

Use these controls before interpreting any signal quality:

- `--trial-objective-split prediction`
  - grid/Optuna rows are scored on prediction batches, not validation;
- `--holdout-steps`
  - final untouched replay is written separately;
- restricted threshold grid
  - avoid sweeping every 0.05 threshold when false positives are the main risk;
- `--min-validation-recall`
  - prevents a validation threshold from selecting "never trade";
- `--min-validation-predicted-positive-rate`
  - prevents a threshold from passing by suppressing all positives;
- `--min-prediction-unique` and `--min-prediction-std`
  - rejects collapsed probabilities;
- `--elasticnet-prefilter-features-choices`
  - keeps ElasticNet runtime practical without using validation or prediction
    rows.

The classifier treats failed validation-threshold constraints as rejected
trials. They must not be considered accepted configs and must not trigger
holdout replay. Long runs also write `*.partial.parquet` artifacts after each
trial so an interrupted run still leaves structured evidence.

## Recommended First Stable Run

Use one focused feature scope, a small threshold grid, and a reserved holdout:

```bash
export PY="/media/przem/linux_data/conda/envs/ml_env/bin/python"
export READINESS_RUN="$(ls -td test_output/rpf_clean_walkforward/*_readiness_* | head -1)"
export FEATURE_ABLATION="group_structural_room+liquidity_volume_pressure+interaction_confluence"

for TARGET in \
  target_cls_extreme_up_ge_2x_down_hvol_v2 \
  target_cls_extreme_down_ge_2x_up_hvol_v2
do
  "$PY" -m regression_feature_engineering.walkforward.classify \
    --asset BTCUSDT \
    --root 8h/B \
    --target-col "$TARGET" \
    --base-run "$READINESS_RUN" \
    --feature-ablation "$FEATURE_ABLATION" \
    --feature-policy elasticnet_logistic_v1 \
    --model-family catboost \
    --window-mode chronological_recent \
    --n-steps 50 \
    --holdout-steps 20 \
    --max-configs 8 \
    --log-every-windows 5 \
    --objective-metric validation_decision_cost \
    --trial-objective-split prediction \
    --threshold-mode validation_sweep \
    --threshold-grid 0.55,0.60,0.65,0.70 \
    --fp-cost 5 \
    --fn-cost 1 \
    --min-validation-recall 0.05 \
    --min-validation-predicted-positive-rate 0.01 \
    --max-validation-false-positive-rate 0.35 \
    --iterations-choices 100,200 \
    --depth-choices 2 \
    --learning-rate-choices 0.01 \
    --l2-leaf-reg-choices 30,100 \
    --early-stopping-rounds-choices 20 \
    --od-wait-choices 20 \
    --elasticnet-c-choices 0.03,0.1 \
    --elasticnet-l1-ratio-choices 0.5 \
    --elasticnet-max-features-choices 80 \
    --elasticnet-min-selected-features 20 \
    --elasticnet-coef-epsilon-choices 1e-8 \
    --elasticnet-prefilter-features-choices 160 \
    --task-type CPU
done
```

Use CPU for this selector-first experiment unless CatBoost fit time becomes
dominant. Current timing evidence shows ElasticNet selection is the expensive
step; CatBoost fitting on selected panels is usually short.

## Promotion Gate

A config is not useful unless all of these hold on tuning windows and then
remain acceptable on reserved holdout windows:

- status is `ok`;
- predicted-positive rate is not near zero;
- precision improves versus naive positive firing;
- false-positive rate is materially lower than ungated baselines;
- recall is not collapsed below the configured minimum;
- probability dispersion does not collapse;
- selected features are not entirely unstable across folds;
- holdout decision cost does not materially degrade versus tuning evidence.

Do not promote from AUC. AUC remains a diagnostic rank metric only. For trading
decisions, false positives, precision, recall, predicted-positive rate, and
decision cost are the primary evidence.

## Next Research Loop

1. Run the recommended two-target command.
2. Compare `trials.parquet` against `holdout_summary.json`.
3. Inspect window-level failures in `holdout_window_metrics.parquet`.
4. Inspect selected-feature stability in `holdout_selected_features.parquet`.
5. If holdout fails, reduce search space or tighten threshold constraints
   before adding gates.
6. If holdout fails, keep work on the chronological classifier objective and
   feature-selection contract. EMA/regime, signal-bank, decision-bank, and
   learned-gate experiments are deferred unless a new plan explicitly reopens
   them.
