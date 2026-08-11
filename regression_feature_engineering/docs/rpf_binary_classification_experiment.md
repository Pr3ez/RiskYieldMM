# RPF Binary Classification Experiment

## Purpose

Define the first RPF-native classification target and command surface.

## Current Status

Status: experimental runner implemented with validation-selected decision
threshold support. Exploratory 15-step and 50-step runs have completed for
both UP and DOWN binary targets. The current conclusion is regime-dependent:
keep both targets and evaluate when each should be trusted.

Command:

```bash
python -m regression_feature_engineering.walkforward.classify
```

Outputs:

```text
test_output/rpf_clean_classification/
trials.parquet
window_metrics.parquet
validation_scores.parquet
prediction_scores.parquet
best_config.json
report.md
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
- RPF features: the canonical RPF feature root defined in `data_contract.md`
- Labels: `distance_horizon_vol_v2`
- Window source: existing clean RPF `frozen_windows.parquet`

## What This Does Not Decide

This experiment does not replace the four hvol v2 regression targets. It tests
whether a cleaner directional event target is easier to predict than bounded
share regression and whether it can become a trading-decision layer after
regime gating.

## Metrics

Each run writes validation and prediction metrics:

```text
logloss
brier
accuracy
balanced_accuracy
precision
precision_lift
recall
f1
fbeta
mcc
positive_rate
predicted_positive_rate
signal_count
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
pr_auc
```

`auc` is still stored in `trials.parquet` as a secondary rank diagnostic, but
it is not a promotion metric for these binary trading targets. The useful
metrics are thresholded decision metrics plus base-rate-aware quality:
precision, precision lift over local positive rate, recall, MCC, PR AUC,
false-positive rate, predicted-positive rate, signal count, and decision cost.

CatBoost still trains with `Logloss`. The threshold-selection objective is
chosen on validation predictions:

```text
validation_logloss
validation_decision_cost
validation_false_positive_rate
validation_precision
validation_precision_lift
validation_fbeta
validation_balanced_accuracy
validation_pr_auc
validation_mcc
stable_prediction_quality
stable_signal_quality
```

For trading-decision experiments, prefer:

```bash
--threshold-mode validation_sweep
--decision-policy causal_signal_budget
--max-signals-grid 0,5,10,20,40,80
--objective-metric stable_prediction_quality
--trial-objective-split prediction
--fp-cost 5
--fn-cost 1
--min-validation-recall 0.10
--min-validation-predicted-positive-rate 0.02
--min-threshold-pass-rate 0.80
--max-prediction-zero-positive-window-rate 0.50
--max-prediction-all-positive-window-rate 0.10
--prediction-all-positive-rate-threshold 0.95
--max-prediction-high-fpr-window-rate 0.20
--max-prediction-window-false-positive-rate 0.50
--max-prediction-high-cost-window-rate 0.20
--max-prediction-window-decision-cost-per-row 1.50
```

For specialist signal-bank experiments, prefer the stricter precision and
persistence objective:

```bash
--objective-metric stable_signal_quality
--trial-objective-split prediction
--threshold-mode validation_sweep
--decision-policy threshold_only
--fp-cost 8
--fn-cost 1
--fbeta-beta 0.5
--min-validation-precision 0.60
--max-validation-false-positive-rate 0.15
--min-threshold-pass-rate 0.70
--max-prediction-zero-positive-window-rate 0.85
--max-prediction-all-positive-window-rate 0.05
--max-prediction-high-fpr-window-rate 0.20
--max-prediction-window-false-positive-rate 0.20
--max-prediction-high-cost-window-rate 0.30
```

Use `--decision-policy batch_topk_offline` only for diagnostic/offline ranking
studies. It ranks the full prediction batch and is not live-safe row by row.

The decision pair `(threshold, max_signals_per_batch)` is selected from
validation predictions only, then applied unchanged to prediction batches.
`max_signals_per_batch=0` means unlimited thresholding; positive values keep
only the highest-probability rows in the current batch that pass the threshold.
When `--objective-metric stable_prediction_quality` is active, validation
threshold/cap selection uses the same stable quality scorer rather than pure
validation decision cost. This prevents validation from winning only by
choosing overly sparse no-signal decisions.

The active Optuna command surface is:

```bash
python -m regression_feature_engineering.walkforward.classify_optuna
```

It is chronological-only and uses `stable_prediction_quality` by default. That
score is computed from prediction batches and penalizes zero-positive windows,
whole-batch-positive windows, high-FPR windows, high-cost windows, unstable
threshold passes, missed high-target-positive windows, low-target whole-batch
firing, low/excessive signal rate, and excessive selected-feature count.
`stable_signal_quality` is the specialist-signal objective. It still uses the
same leak-safe fold pipeline, but it weights precision lift, low false-positive
rate, repeated active prediction batches, low signal churn, and active-window
precision above recall. Use it when the goal is a bank of sparse high-precision
models rather than one classifier that tries to cover every positive label.
Validation is used inside each fold for early stopping,
best-iteration selection, and threshold selection; prediction batches judge
the trial. A later untouched confirmation window is still required after
tuning because those prediction batches become the tuning evidence.
Use `--holdout-steps` for serious runs. The classifier reserves the latest
holdout windows, tunes on the earlier selected windows, and writes
`holdout_summary.json`, `holdout_window_metrics.parquet`,
`holdout_prediction_scores.parquet`, and `holdout_selected_features.parquet`
for confirmation-only evidence.

Current runner versions also write row-level validation and prediction scores.
`prediction_scores.parquet` is the required input for exact regime-gate joins
by `timestamp,batch_id`.

Current runner versions also write prediction-window stability metrics to
`trials.parquet` and `best_config.json`:

```text
prediction_zero_positive_window_rate
prediction_all_positive_window_rate
prediction_high_fpr_window_rate
prediction_high_cost_window_rate
prediction_high_target_window_rate
prediction_missed_high_target_window_rate
prediction_low_target_all_positive_window_rate
prediction_false_positive_rate_max
prediction_decision_cost_per_row_max
prediction_window_stability_pass
prediction_window_stability_reason
```

These metrics are mandatory for interpreting trading-decision experiments.
A run that alternates between zero-positive windows and whole-batch-positive
windows is rejected before holdout even if aggregate prediction cost looks
acceptable.

The target-aware stability fields were added after the UP CNN-cap holdout:
validation looked clean, but several high-UP-base-rate holdout batches received
no signals and one mixed batch fired across the whole batch. Future UP runs
must use these fields instead of judging only aggregate precision and FPR.

## ElasticNet Feature Selection With CatBoost Prediction

The active classifier supports a chronological recent-window dynamic feature
selection experiment:

```text
model_family = catboost
feature_policy = elasticnet_logistic_v1
```

This is not a gate and does not use special batch selection. ElasticNet is used
only as a fold-local selector; CatBoost remains the prediction model. For each
walk-forward step:

1. Load the normal recent train, validation, and prediction batches from the
   frozen window file.
2. Compute selector mean/std from train rows only.
3. Optionally prefilter ElasticNet candidates by train-only standardized
   class separation.
4. Fit sparse logistic ElasticNet on scaled train rows.
5. Freeze the nonzero coefficient feature list for that fold.
6. Fit CatBoost on the selected train columns with validation as eval set.
7. Score validation rows for early stopping and threshold selection.
8. Freeze the validation-selected feature mask by default.
9. Refit the selector scaler on train+validation rows for that frozen mask.
10. Refit CatBoost on the same selected train+validation scaled columns using the
   validation model's best iteration.
11. Score the prediction batch with the refit CatBoost model.
12. Select the decision threshold and optional per-batch signal cap from
    validation predictions only and apply that frozen decision pair unchanged
    to prediction rows.

The previous `train_val_reselect` behavior, which reruns ElasticNet on
train+validation, remains available only as an explicit diagnostic mode. It is
not the default because it can change the feature mask after threshold
calibration.

The run writes:

```text
selected_features.parquet
```

This file stores selector coefficients, ranks, train-only means/stds, and drop
reasons per fold. For prefiltered runs it also stores
`elasticnet_prefilter_rank`, `elasticnet_prefilter_score`, and
`below_elasticnet_prefilter` drop reasons. It is selector evidence, not final
prediction-model coefficients.

## Optional Causal CNN Embeddings

The classifier supports an opt-in sequence embedding branch:

```bash
--sequence-embedding-mode causal_cnn_v1
```

When enabled, each fold trains a small 1D CNN on scaled training rows only.
The CNN emits embedding columns that are appended to the ElasticNet-selected
RPF columns before CatBoost. It is not an ensemble and does not vote with
CatBoost; CatBoost remains the final classifier.

The first implementation uses left-padded causal sequences ending at the
anchor row:

```text
row t embedding = rows <= t only
```

Validation and prediction labels are never used to fit the CNN. For the
prediction model, the CNN is refit on train+validation only after validation
decisions are frozen.

Recommended smoke flags before a heavy run:

```bash
--sequence-embedding-mode causal_cnn_v1
--sequence-length 16
--sequence-embedding-dim 8
--sequence-conv-channels 16
--sequence-kernel-size 3
--sequence-epochs 1
--sequence-max-train-rows 4000
--sequence-device cpu
```

Only widen epochs, embedding size, or train rows after the one-window smoke
shows non-collapsing predictions and acceptable runtime.

The CNN branch should not blindly consume the same feature panel as the
ElasticNet tabular selector. The current post-hoc diagnostic is documented in
`rpf_cnn_feature_diagnostic.md` and written by:

```bash
python -m regression_feature_engineering.walkforward.cnn_feature_diagnostic
```

The first diagnostic result says useful CNN inputs should be a separate
fast-changing panel dominated by `15m`, `1h`, and `4h`
`structural_room`, `temporal_memory_transforms`, `spike_breakout`,
`interaction_confluence`, and `acceptance_persistence` features. Slow
`12h`/`1d` regime/context features should stay primarily in the tabular
CatBoost branch unless a controlled A/B run proves otherwise.

Use the diagnostic panel with:

```bash
--sequence-panel-path test_output/rpf_cnn_feature_diagnostics/<run>/selected_cnn_panel_160.json
```

Do not use `--candidate-panel-path` for this test unless the intent is also to
narrow the ElasticNet tabular candidate universe. The intended combined model
is:

```text
ElasticNet-selected tabular features + CNN embeddings from diagnostic sequence panel -> CatBoost
```

Use this first on plain chronological windows. Do not combine it with
`ema_regime_bank`; EMA-regime selection is abandoned for the active path. Also
do not combine it with learned gates, signal banks, or decision banks until
the chronological comparison is understood.

Long runs write partial artifacts after every completed or errored trial:

```text
trials.partial.parquet
window_metrics.partial.parquet
validation_scores.partial.parquet
prediction_scores.partial.parquet
selected_features.partial.parquet
```

These files are intended for interrupted-run review only. Finished runs still
write the canonical non-partial artifact names.

First smoke command:

```bash
"$PY" -m regression_feature_engineering.walkforward.classify \
  --asset BTCUSDT \
  --root 8h/B \
  --target-col target_cls_extreme_up_ge_2x_down_hvol_v2 \
  --base-run "$READINESS_RUN" \
  --feature-ablation all \
  --feature-policy elasticnet_logistic_v1 \
  --model-family catboost \
  --n-steps 3 \
  --holdout-steps 0 \
  --max-configs 2 \
  --objective-metric validation_decision_cost \
  --trial-objective-split prediction \
  --threshold-mode validation_sweep \
  --fp-cost 5 \
  --fn-cost 1 \
  --iterations-choices 200 \
  --depth-choices 2 \
  --learning-rate-choices 0.01 \
  --l2-leaf-reg-choices 30 \
  --early-stopping-rounds-choices 50 \
  --od-wait-choices 50 \
  --elasticnet-c-choices 0.03,0.1 \
  --elasticnet-l1-ratio-choices 0.5 \
  --elasticnet-max-features-choices 120 \
  --elasticnet-coef-epsilon-choices 1e-8 \
  --elasticnet-prefilter-features-choices 160 \
  --task-type CPU
```

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

- validation decision cost or logloss, depending on the run goal;
- prediction false-positive rate;
- prediction precision and recall;
- prediction predicted-positive rate;
- non-collapsed probability dispersion.

If `only_structural_room` works, compare focused groups before trying all RPF
features.

Do not interpret global UP versus DOWN metrics as a target-selection decision.
The current evidence shows each side works or fails under different regimes.
The correct comparison surface is:

```text
target x objective x feature_ablation x regime_bucket
```

## Current Stability-Gated Command Shape

Use this for the next small chronological check before any long run:

```bash
PY="/media/przem/linux_data/conda/envs/ml_env/bin/python"
READINESS_RUN="$(ls -td test_output/rpf_clean_walkforward/*_readiness_* | head -1)"
FEATURE_ABLATION="group_structural_room+liquidity_volume_pressure+interaction_confluence"

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
    --n-steps 20 \
    --holdout-steps 0 \
    --max-configs 4 \
    --objective-metric validation_decision_cost \
    --trial-objective-split prediction \
    --threshold-mode validation_sweep \
    --decision-policy causal_signal_budget \
    --threshold-grid 0.45,0.50,0.55,0.60 \
    --max-signals-grid 0,5,10,20,40,80 \
    --fp-cost 5 \
    --fn-cost 1 \
    --fbeta-beta 0.5 \
    --min-validation-recall 0.03 \
    --min-validation-predicted-positive-rate 0.01 \
    --min-threshold-pass-rate 0.80 \
    --max-prediction-zero-positive-window-rate 0.50 \
    --max-prediction-all-positive-window-rate 0.10 \
    --prediction-all-positive-rate-threshold 0.95 \
    --max-prediction-high-fpr-window-rate 0.20 \
    --max-prediction-window-false-positive-rate 0.50 \
    --max-prediction-high-cost-window-rate 0.20 \
    --max-prediction-window-decision-cost-per-row 1.50 \
    --iterations-choices 100,200 \
    --depth-choices 2 \
    --learning-rate-choices 0.01 \
    --l2-leaf-reg-choices 30 \
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

If a target has at least one `ok` trial with acceptable window stability, rerun
that narrowed configuration with `--n-steps 50 --holdout-steps 20`. If all
trials are rejected, adjust feature scope or model class before increasing
runtime.

not:

```text
single global UP score versus single global DOWN score
```

## Cost-Sensitive Holdout Comparison

Use this to compare objective choices without changing the focused
ElasticNet/CatBoost config surface. The first `30` selected windows are tuning
evidence and the latest `20` windows are holdout replay evidence:

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
      --feature-policy elasticnet_logistic_v1 \
      --model-family catboost \
      --n-steps 50 \
      --holdout-steps 20 \
      --max-configs 8 \
      --objective-metric "$OBJECTIVE" \
      --trial-objective-split prediction \
      --threshold-mode validation_sweep \
      --threshold-grid 0.55,0.60,0.65,0.70 \
      --fp-cost 5 \
      --fn-cost 1 \
      --fbeta-beta 0.5 \
      --min-validation-recall 0.10 \
      --min-validation-predicted-positive-rate 0.02 \
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
done
```

## Current Evidence

Fifty-step validation-logloss runs using
`group_structural_room+liquidity_volume_pressure+interaction_confluence`
produced these selected artifacts:

```text
UP:
test_output/rpf_clean_classification/20260612_190751_classification_cls_extreme_up_ge_2x_down_hvol_v2/

DOWN:
test_output/rpf_clean_classification/20260612_203257_classification_cls_extreme_down_ge_2x_up_hvol_v2/
```

The UP run was conservative: low predicted-positive rate and low recall. It
was not globally strong, but its errors are regime-dependent. In actual up
batches the model can be clean when it fires; in actual down batches, UP false
positives are concentrated and harmful.

The DOWN run had stronger global ranking in some checks, but it also changes
materially by trend/path regime. It should not be promoted globally without
stability evidence across regimes.

The 15-step cost-sensitive objective sweep is stored under:

```text
test_output/rpf_clean_classification_objective_15step/
```

The recomputed summary is:

```text
test_output/rpf_clean_classification_objective_15step/objective_15step_summary_recomputed.csv
```

## Regime And Label Diagnostics

Regime-quality diagnostics join selected 50-step prediction-window metrics to
BTCUSDT OHLCV context:

```text
test_output/rpf_clean_classification/regime_target_quality_analysis/true50_regime_quality_report.md
```

Label/performance diagnostics join selected 50-step prediction-window metrics
to aggregated hvol v2 label stats:

```text
test_output/rpf_clean_classification/label_quality_correlation_analysis/true50_label_quality_correlation_report.md
```

These diagnostics are post-hoc. They are allowed to explain failures and guide
feature/gate design, but same-batch labels and actual prediction-batch returns
are not live-tradable inputs.

Current interpretation:

- keep both binary targets;
- evaluate by trend, volatility/range, structural location, and label-derived
  research buckets;
- use live-safe regime diagnostics before judging trading usefulness;
- optimize false-positive control without collapsing all predicted positives.

The historical gate design is tracked in `rpf_regime_gated_prediction_plan.md`;
it is not the next active command path.
