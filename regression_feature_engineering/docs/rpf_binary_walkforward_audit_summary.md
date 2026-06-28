# RPF Binary Walk-Forward Audit Summary

## Purpose

Summarize what was actually built and learned from RPF-native binary
walk-forward prediction work, so future runs do not repeat failed branches.

## Current Status

Status: `research_active_not_promoted`.

No RPF binary UP/DOWN model is promoted.

The useful outcome so far is not a profitable or stable predictor. The useful
outcome is a clearer pipeline and a narrower list of failure modes:

- the RPF binary data path works;
- chronological tuning plus reserved holdout works;
- train-only ElasticNet feature selection works mechanically;
- optional causal CNN embeddings work mechanically;
- DOWN has some false-positive-control evidence;
- UP still has weak live-safe ranking quality;
- decision policies are now explicit in code and artifacts;
- batch-top-k signal caps are diagnostic only, not live-safe row-by-row trading
  decisions.

The active next path is no longer another widened probability-threshold
classifier run. It is:

```bash
python -m regression_feature_engineering.walkforward.rank_signal
```

That command trains CatBoostRanker on continuous UP/DOWN relevance grouped by
`batch_id` and applies a validation-calibrated causal signal budget in timestamp
order. The classifier artifacts in this document are historical baselines and
failure diagnostics for the ranked-signal branch.

## Scope

This audit covers RPF-native binary classification for:

```text
asset: BTCUSDT
root:  8h/B
feature set: regression_path_features_v1
```

Active binary targets:

```text
classification_cls_extreme_up_ge_2x_down_hvol_v2
classification_cls_extreme_down_ge_2x_up_hvol_v2
```

Older docs and artifacts may use historical aliases:

```text
target_cls_extreme_up_ge_2x_down_hvol_v2
target_cls_extreme_down_ge_2x_up_hvol_v2
```

## Source Of Truth

- Active process doc: `rpf_binary_walkforward_process.md`
- Pipeline contract: `rpf_binary_prediction_pipeline_contract.md`
- Current experiment summary: `rpf_current_experiment_summary.md`
- Current feature state: `current_feature_state.md`
- Active binary command: `regression_feature_engineering/walkforward/classify_optuna.py`
- Active ranked-signal command: `regression_feature_engineering/walkforward/rank_signal.py`
- Ranked-signal contract: `rpf_ranked_signal_plan.md`
- Active binary package: `regression_feature_engineering/walkforward/classification/`
- Main artifacts: `test_output/rpf_clean_classification/`
- Main Optuna artifacts: `test_output/rpf_clean_classification_optuna/`

## What This Does Not Decide

This audit does not promote a model, choose final feature scopes, or authorize
EMA/gate/bank experiments. It records what the completed work means.

## What Was Built

The active binary walk-forward stack is:

```text
RPF features
-> exact timestamp,batch_id label join
-> chronological train / validation / prediction windows
-> optional train-only ElasticNet-logistic feature selector
-> optional causal CNN sequence embeddings
-> CatBoostClassifier
-> validation-selected decision rule
-> prediction-window scoring
-> optional reserved holdout replay
```

Implemented artifact outputs include:

```text
trials.parquet
window_metrics.parquet
prediction_scores.parquet
validation_scores.parquet
selected_features.parquet
holdout_summary.json
holdout_window_metrics.parquet
holdout_prediction_scores.parquet
holdout_selected_features.parquet
report.md
```

The code now separates fixed-grid classification and Optuna classification:

```text
python -m regression_feature_engineering.walkforward.classify
python -m regression_feature_engineering.walkforward.classify_optuna
```

## Experiment History

### Early Fixed-Grid Runs

Early fixed-grid runs proved plumbing and exposed unstable target behavior.
They are not decision evidence.

Examples:

```text
test_output/rpf_clean_classification/20260612_190751_classification_cls_extreme_up_ge_2x_down_hvol_v2
test_output/rpf_clean_classification/20260612_203257_classification_cls_extreme_down_ge_2x_up_hvol_v2
```

Observed pattern:

- UP often had poor precision versus high base positive rate;
- DOWN sometimes showed better ranking but unstable recall/FPR;
- AUC alone was misleading and was demoted to a diagnostic metric.

### Regime / Trend / Label Diagnostics

The following diagnostics were created and remain useful for explaining why
global metrics were unstable:

```text
test_output/rpf_clean_classification/ohlcv_trend_quality_analysis/
test_output/rpf_clean_classification/regime_target_quality_analysis/
test_output/rpf_clean_classification/label_quality_correlation_analysis/
```

Main conclusion:

- prediction quality changes materially by trend/path regime and label
  composition;
- global UP-vs-DOWN comparison is not enough;
- labels and regimes explain some failures, but they did not produce a simple
  promoted gate.

### EMA / Gate / Bank Branches

These branches were explored and then abandoned for the active path:

```text
EMA200 post-hoc gates
EMA-regime train/validation banks
learned regime gates
signal banks
separate decision banks
```

Reason:

- they added complexity before the plain chronological binary pipeline had a
  stable live-safe decision layer;
- EMA did not reliably improve both precision and recall;
- signal/decision banks did not produce usable gate evidence;
- some runs were interrupted or rejected before holdout.

Keep those artifacts for reproducibility only.

## Main Optuna Evidence

### DOWN Best Holdout

Run:

```text
test_output/rpf_clean_classification_optuna/20260618_031616_classification_classification_cls_extreme_down_ge_2x_up_hvo
```

Holdout:

```text
precision:            0.375
base positive rate:   0.202
precision lift:       1.86
recall:               0.163
FPR:                  0.069
cost / row:           0.443
AUC:                  0.512
PR AUC:               0.313
TP / FP / FN / TN:    158 / 263 / 812 / 3567
```

Interpretation:

- best current binary evidence;
- false positives are controlled better than UP;
- still sparse and not promoted;
- signal quality is useful but not enough alone.

### UP First CNN-Cap Holdout

Run:

```text
test_output/rpf_clean_classification_optuna/20260618_173826_classification_classification_cls_extreme_up_ge_2x_down_hvo
```

Holdout:

```text
precision:            0.514
base positive rate:   0.552
precision lift:       0.93
recall:               0.126
FPR:                  0.146
cost / row:           0.810
AUC:                  0.393
PR AUC:               0.556
TP / FP / FN / TN:    333 / 315 / 2315 / 1837
```

Interpretation:

- rejected;
- precision was below the base positive rate;
- validation looked cleaner than holdout, proving overfit/regime drift risk.

### UP Target-Aware Stability Run

Run:

```text
test_output/rpf_clean_classification_optuna/20260618_202138_classification_classification_cls_extreme_up_ge_2x_down_hvo
```

Tuning result:

```text
status:               rejected:window_stability
precision:            0.670
precision lift:       1.43
recall:               0.172
FPR:                  0.074
cost / row:           0.585
missed high-target:   5 / 8
```

Interpretation:

- aggregate precision/FPR looked better;
- model was too sparse and missed too many high-UP windows;
- correctly rejected before holdout.

### UP Stable-Threshold Fix Run

Run:

```text
test_output/rpf_clean_classification_optuna/20260622_070618_classification_classification_cls_extreme_up_ge_2x_down_hvo
```

Tuning result:

```text
status:               rejected:window_stability
precision:            0.529
precision lift:       1.13
recall:               0.256
FPR:                  0.200
cost / row:           0.881
missed high-target:   2 / 8
low all-positive:     1 / 9
```

Interpretation:

- missed high-UP windows improved;
- false positives became too high;
- failure moved from under-firing to over-firing.

### UP No-Unlimited-Caps Run

Run:

```text
test_output/rpf_clean_classification_optuna/20260622_092243_classification_classification_cls_extreme_up_ge_2x_down_hvo
```

Tuning:

```text
status:               ok
precision:            0.539
precision lift:       1.15
recall:               0.237
FPR:                  0.178
cost / row:           0.831
missed high-target:   0 / 8
zero windows:         1 / 20
low all-positive:     0 / 9
```

Holdout:

```text
precision:            0.547
base positive rate:   0.511
precision lift:       1.07
recall:               0.237
FPR:                  0.204
cost / row:           0.890
AUC:                  0.463
PR AUC:               0.465
missed high-target:   1 / 3
zero windows:         1 / 10
low all-positive:     0
TP / FP / FN / TN:    290 / 240 / 936 / 934
```

Interpretation:

- removing `max_signals=0` fixed a real instability source;
- holdout was produced and window stability passed;
- precision lift is weak;
- AUC and PR AUC show weak ranking quality;
- not promoted.

## Critical Correction

Positive `max_signals_per_batch` under `batch_topk_offline` is a batch-top-k
offline decision rule:

```text
predict every row in the batch
rank the whole batch by probability
keep the top N rows that pass threshold
```

This is diagnostic only for row-by-row trading because future rows in the same
prediction batch affect whether the current row fires. It does not leak labels,
but it is not a live-safe trading decision policy.

Therefore:

```text
batch_topk_offline = diagnostic only
threshold_only = live-safe
causal_signal_budget = live-safe when rows are processed in timestamp order
```

As of 2026-06-22, the classifier exposes these as `--decision-policy` choices
and writes both `decision_policy` and `decision_policy_live_safe` into trial,
window, validation-score, and prediction-score artifacts.

This correction means the best UP capped result cannot be treated as a
promotion candidate.

## What We Actually Have

We have:

- a technically working binary RPF walk-forward framework;
- exact RPF/label joins;
- chronological prediction-window scoring;
- train-only ElasticNet selector;
- optional causal CNN embeddings;
- CatBoost classifier integration;
- reserved holdout replay;
- useful per-window metrics and selected-feature artifacts;
- one DOWN holdout with useful but sparse false-positive control;
- UP experiments that mostly show weak ranking and regime instability.

We do not have:

- a promoted UP model;
- a promoted DOWN model;
- a promoted live-safe capped signal policy;
- evidence that adding more CatBoost capacity will fix UP;
- evidence that EMA/gates/banks should be reopened now.

## Main Failure Modes

1. **UP ranking is weak on holdout**
   - AUC below random in the latest UP holdout;
   - probabilities often nearly flat around `0.50`;
   - threshold-only behavior is poor.

2. **Validation/holdout mismatch**
   - validation precision can look good while holdout precision/lift degrades.

3. **Capped reports can look better than live-safe decisions**
   - positive `max_signals_per_batch` relies on whole-batch ranking.

4. **Regime dependence is real**
   - label/trend/regime diagnostics show that performance changes by window
     context;
   - no simple EMA or learned gate has solved this yet.

5. **DOWN is more promising than UP**
   - DOWN has the best current precision lift and FPR control;
   - still sparse and not production-ready.

## Decision

Stop running more capped UP searches as if they are promotable.

The next engineering step is not another broad Optuna run. The decision layer
has been made explicit:

```text
threshold_only
causal_signal_budget
batch_topk_offline
```

Now replay existing best configurations under live-safe policies before testing
more feature scopes or targets.

## Next Work

1. Add live-safe `threshold_only` replay for the best UP and DOWN configs.
2. Add `causal_signal_budget` replay only if we still need signal caps.
3. Compare replay against existing `batch_topk_offline` diagnostics.
4. If UP live-safe replay remains weak, stop this UP feature-scope branch and
   test a different feature scope or target definition.
5. Keep DOWN as the more promising branch, but require live-safe replay before
   promotion.
