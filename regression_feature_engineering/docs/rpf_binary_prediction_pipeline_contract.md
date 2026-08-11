# RPF Binary Prediction Pipeline Contract

## Purpose

Define the production-oriented RPF binary walk-forward pipeline target:
stable next-batch binary prediction using causal RPF features, train-only
feature selection, optional causal sequence embeddings, and CatBoost as the
final classifier.

## Current Status

Status: `implemented_tabular_plus_opt_in_cnn_stability_in_progress`.

The current implemented path is chronological RPF classification with an
optional causal sequence branch:

```text
RPF features
-> train-only ElasticNet selector
-> optional causal CNN embeddings
-> CatBoost classifier
-> explicit decision policy
-> signal
```

The CNN sequence branch is opt-in with
`--sequence-embedding-mode causal_cnn_v1`. The default remains `none` so
previous tabular-only runs are reproducible.

## Scope

First benchmark:

```text
asset: BTCUSDT
root:  8h/B
targets:
  target_cls_extreme_up_ge_2x_down_hvol_v2
  target_cls_extreme_down_ge_2x_up_hvol_v2
```

The classifier also accepts these user-facing aliases:

```text
classification_cls_extreme_up_ge_2x_down_hvol_v2
classification_cls_extreme_down_ge_2x_up_hvol_v2
```

The active command remains:

```bash
python -m regression_feature_engineering.walkforward.classify
```

## Source Of Truth

- Current state: `current_feature_state.md`
- Current summary: `rpf_current_experiment_summary.md`
- Binary classifier runner:
  `regression_feature_engineering/walkforward/classification/`
- Binary experiment doc: `rpf_binary_classification_experiment.md`
- Overfit protocol: `rpf_overfit_control_protocol.md`
- Feature scaling contract: `feature_scaling_contract.md`

## What This Does Not Decide

This doc does not promote a model, choose final CNN architecture, choose final
thresholds, or authorize EMA/gate/bank experiments. It defines the causal
pipeline contract for the next implementation phases.

## Core Rule

All rows may describe the past. Only labeled eligible rows may teach or score
the model.

Use only labeled, non-embargo rows for:

- ElasticNet fitting;
- CatBoost fitting;
- CNN supervised loss;
- validation scoring;
- threshold and decision-policy optimization;
- prediction-batch scoring;
- Optuna objective metrics.

Use all causal continuous rows only for:

- CNN sequence context;
- rolling feature state;
- causal normalization state;
- sequence buffers;
- embedding generation.

The prediction batch must never influence training, scaling, feature
selection, CNN training, CatBoost training, or threshold selection.

## Fold Contract

One fold is:

```text
[ Train batches ][ Validation batches ][ Prediction batch ]
```

Inside each fold:

1. Train rows fit scalers, ElasticNet, CNN parameters, and CatBoost.
2. Validation rows control early stopping, threshold checks, and fold-local
   model decisions.
3. Train plus validation may be refit after decisions are frozen.
4. Prediction rows are unseen and used only for final fold scoring.

All scaler statistics are fit only on labeled eligible training rows for the
decision being made. Refit-on-train-plus-validation is allowed only after
validation decisions are frozen and before prediction scoring.

## Model Architecture Target

Target architecture:

```text
RPF features
   |-- ElasticNet branch -> stable tabular feature selection
   |-- CNN branch        -> causal short-sequence embeddings
   v
Selected RPF features + CNN embeddings
   v
CatBoost classifier
   v
P(target = 1)
   v
Threshold
   v
Final signal
```

ElasticNet is a selector only. It decides which current-row RPF columns
CatBoost may see.

Default refit rule: validation selects the ElasticNet feature mask, threshold,
and early-stopping behavior. The final train+validation refit keeps that
validation-selected mask, refits scaler statistics on train+validation for
those columns, and refits CatBoost before scoring the prediction batch.
Rerunning ElasticNet on train+validation is diagnostic-only because it changes
the feature boundary after threshold calibration.

CNN is a sequence encoder only. It may read causal context rows, but supervised
loss is computed only for labeled eligible anchor rows. The implemented
`causal_cnn_v1` branch builds left-padded sequences ending at the anchor row,
so no future rows are included in an embedding.

CatBoost is the final prediction model. It consumes selected current-row RPF
features plus frozen CNN embeddings.

## Optuna Contract

One Optuna trial must execute a complete walk-forward backtest:

1. Suggest parameters.
2. Run all selected folds.
3. Use validation inside each fold for model decisions.
4. Score prediction batches only after fold decisions are frozen.
5. Aggregate prediction-batch metrics into one stability-aware score.
6. Return that prediction-batch score to Optuna.

Validation is not the final Optuna objective because validation is used inside
each fold. Prediction batches are the trial scoring surface. A later holdout
slice remains required after tuning because prediction batches used by Optuna
become tuning evidence.

The active Optuna command surface for this contract is:

```bash
python -m regression_feature_engineering.walkforward.classify_optuna
```

It is chronological-only. It does not expose EMA gates, EMA-regime windows,
learned gates, signal banks, or decision banks.

The active objective is:

```text
stable_prediction_quality
```

This objective is maximized from prediction-batch evidence. It rewards
base-rate-adjusted decision quality and penalizes:

- zero-positive prediction windows;
- whole-batch-positive prediction windows;
- high-FPR windows;
- high-decision-cost windows;
- low threshold-pass rate;
- very low or excessive signal rate;
- unnecessary selected-feature count.

The decision rule is selected on validation rows as:

```text
decision_threshold
decision_policy
optional max_signals_per_batch
```

The implemented CLI argument is:

```text
--decision-policy threshold_only|causal_signal_budget|batch_topk_offline
```

Policy meanings:

```text
threshold_only
  Live-safe. Each row fires independently when probability >= threshold.
  Positive max-signal caps are not supported by the CLI because they would be
  ignored. Use `--max-signals-grid 0` for uncapped thresholding.

causal_signal_budget
  Live-safe if rows are processed in timestamp order. Rows fire when they pass
  threshold until the per-batch budget is exhausted. It does not sort future
  rows by probability.

batch_topk_offline
  Diagnostic only. It ranks the full prediction batch by probability and keeps
  the top N rows that pass threshold. It does not use labels, but it is not
  live-safe row-by-row because future rows inside the same batch affect whether
  the current row fires.
```

Every trial, window row, and score row now records:

```text
decision_policy
decision_policy_live_safe
selected_max_signals
```

Only `threshold_only` and `causal_signal_budget` are eligible for promotion.
`batch_topk_offline` is allowed only for diagnostic/offline ranking studies.

When `stable_prediction_quality` is active, validation threshold/cap selection
uses the stable quality scorer rather than pure validation decision cost. This
keeps the validation decision layer aligned with the prediction trial objective
and discourages ultra-sparse decisions that miss high-target windows.

When this objective is active, failed stability gates do not flatten the score
to a constant sentinel value. The trial still records statuses such as
`rejected:window_stability`, but Optuna receives the continuous penalized score
so it can learn which failed trials are less bad. Older validation objectives
still use hard rejection sentinels because they do not include stability
penalties internally.

## Stability Gates

Aggregate prediction metrics are not enough. Every trial must also report
window-level stability:

```text
threshold pass window rate
zero-positive window count/rate
all-positive window count/rate
high-FPR window count/rate
high-decision-cost window count/rate
high-target-positive window count/rate
missed high-target-positive window count/rate
low-target-positive all-positive window count/rate
per-window max FPR
per-window max decision cost
```

The current classifier exposes these controls:

```text
--min-threshold-pass-rate
--max-prediction-zero-positive-window-rate
--max-prediction-all-positive-window-rate
--prediction-all-positive-rate-threshold
--max-prediction-high-fpr-window-rate
--max-prediction-window-false-positive-rate
--max-prediction-high-cost-window-rate
--max-prediction-window-decision-cost-per-row
--prediction-high-target-positive-rate-threshold
--min-prediction-high-target-window-recall
--min-prediction-high-target-window-signal-rate
--max-prediction-missed-high-target-window-rate
--prediction-low-target-positive-rate-threshold
--max-prediction-low-target-all-positive-window-rate
```

Configs that alternate between no positives and whole-batch positives are
rejected before holdout, even if aggregate prediction metrics look acceptable.
The target-aware gates specifically address the 2026-06-18 UP failure mode:
high-positive holdout batches received no signals, while one low/mixed batch
received whole-batch firing.

## Decision Metrics

Every trial records base-rate-aware decision metrics:

```text
pr_auc
precision
precision_lift
recall
f1/fbeta
mcc
brier
signal_count
selected_max_signals
predicted_positive_rate
```

Precision lift is:

```text
precision / prediction_batch_positive_rate
```

It directly answers whether predicted positives beat the local batch base
rate. This is more useful than plain precision when the positive rate drifts
across prediction batches.

## Implementation Phases

1. **Chronological tabular stability**
   - Status: implemented initial.
   - ElasticNet selector plus CatBoost on chronological windows.
   - Stability gates written to `trials.parquet`.

2. **Objective stabilization**
   - Status: implemented initial.
   - Run small two-target Optuna searches with `stable_prediction_quality`,
     stability gates, and reserved holdout.
   - Do not use EMA/gates/banks.

3. **Decision-policy explicitness**
   - Status: implemented initial.
   - `threshold_only`, `causal_signal_budget`, and `batch_topk_offline`
     are exposed in code and artifacts.
   - Offline batch-top-k is marked as non-live-safe.

4. **CNN sequence fixture**
   - Status: implemented initial.
   - Build synthetic tests where all rows can form causal sequences but only
     labeled eligible anchor rows contribute supervised loss and scoring.

5. **CNN embedding branch**
   - Status: implemented initial.
   - Fit CNN on train anchors only; score validation/prediction anchors with
     frozen CNN embeddings.

6. **ElasticNet + CNN + CatBoost integration**
   - Status: implemented initial.
   - Concatenate selected scaled RPF features and CNN embeddings. CatBoost
     remains the final classifier.

## Current Rejected Evidence

The 2026-06-16/17 DOWN chronological holdout attempt rejected itself before
holdout:

```text
run:
test_output/rpf_clean_classification/20260616_223950_classification_cls_extreme_down_ge_2x_up_hvol_v2

status: rejected:threshold_constraints
prediction precision / recall: 0.336 / 0.087
prediction FPR: 0.108
zero-positive windows: 27
all-positive windows: 3
```

This failure is the reason stability gates are now part of the classifier
contract.
