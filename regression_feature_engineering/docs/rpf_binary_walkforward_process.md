# RPF Binary Walk-Forward Process

## Purpose

Define the active, repeatable process for building stable RPF-native binary
UP/DOWN prediction pipelines.

## Current Status

Status: `research_active_not_promoted`.

The active command surface is:

```bash
python -m regression_feature_engineering.walkforward.classify_optuna
```

The implemented pipeline is:

```text
RPF features
-> train-only ElasticNet feature selection
-> optional causal CNN embeddings
-> CatBoost classifier
-> validation-selected threshold and max_signals_per_batch
-> prediction-batch scoring
```

The latest useful UP run improved precision and false-positive rate on tuning
windows, but it was correctly rejected before holdout because high-target UP
windows were still missed too often. The latest useful DOWN run improved
false-positive control on holdout, but it remains sparse and is not promoted.

## Scope

Current benchmark:

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

Historical aliases such as `target_cls_extreme_up_ge_2x_down_hvol_v2` may
appear in older reports. New commands should use the `classification_cls_*`
target names.

## Source Of Truth

- Pipeline contract: `rpf_binary_prediction_pipeline_contract.md`
- Experiment evidence: `rpf_current_experiment_summary.md`
- Current detailed state: `current_feature_state.md`
- Classifier command: `regression_feature_engineering/walkforward/classify_optuna.py`
- Classification package: `regression_feature_engineering/walkforward/classification/`
- Latest readiness windows:
  `test_output/rpf_clean_walkforward/20260612_190354_readiness_btcusdt_8h_b_target_reg_direction_extreme_up_sha_2d5c0524`

## What This Does Not Decide

This document does not promote a model, choose final parameters, or reopen EMA
gates, learned gates, signal banks, decision banks, or old Stage-1 HTF
walk-forward paths.

## Active Loop

Use this loop for each target independently.

1. **Readiness**
   - Use the latest frozen RPF readiness windows unless feature roots or labels
     changed.
   - Verify the readiness run has `frozen_windows.parquet`.

2. **Small target-specific search**
   - Use `classify_optuna`.
   - Use chronological recent windows.
   - Use `--n-steps 30 --holdout-steps 10` while iterating on objective logic.
   - Keep EMA, signal-bank, decision-bank, and learned-gate paths disabled.

3. **Tuning decision**
   - Read `trials.parquet`.
   - A useful tuning candidate must improve prediction-batch quality and pass
     window stability gates.
   - If every trial is `rejected:window_stability`, do not run holdout from it.

4. **Holdout confirmation**
   - Only trust `holdout_summary.json` after a candidate passes tuning
     stability.
   - Holdout must beat base positive rate by precision lift and must not rely
     on one lucky batch.

5. **Widening**
   - Only widen to `50/20` or more after the smaller run improves the failure
     mode it was designed to test.
   - Do not widen unchanged failed configurations.

## Evidence Collected

### DOWN

Best current DOWN holdout evidence:

```text
run:
test_output/rpf_clean_classification_optuna/20260618_031616_classification_classification_cls_extreme_down_ge_2x_up_hvo

precision:              0.375
precision lift:         1.86
recall:                 0.163
FPR:                    0.0687
decision cost / row:    0.443
TP / FP / FN / TN:      158 / 263 / 812 / 3567
```

Interpretation: CNN embeddings plus per-batch signal caps materially reduced
false positives versus the previous tabular DOWN holdout. It is still sparse,
so it is useful evidence, not promotion.

### UP

Prior UP CNN-cap holdout:

```text
run:
test_output/rpf_clean_classification_optuna/20260618_173826_classification_classification_cls_extreme_up_ge_2x_down_hvo

precision:              0.514
base positive rate:     0.552
precision lift:         0.93
recall:                 0.126
FPR:                    0.146
decision cost / row:    0.810
```

Interpretation: rejected. Precision was below base rate on holdout.

Target-aware UP tuning rerun:

```text
run:
test_output/rpf_clean_classification_optuna/20260618_202138_classification_classification_cls_extreme_up_ge_2x_down_hvo

status:                 rejected:window_stability
reason:                 too_many_missed_high_target_windows
precision:              0.670
precision lift:         1.43
recall:                 0.172
FPR:                    0.0743
decision cost / row:    0.585
missed high-target:     5 / 8
```

Interpretation: closer, because precision, lift, FPR, and cost improved on the
tuning windows. Still rejected correctly because it missed too many high-UP
windows.

Target-aware UP CPU rerun after stable-threshold fix:

```text
run:
test_output/rpf_clean_classification_optuna/20260622_070618_classification_classification_cls_extreme_up_ge_2x_down_hvo

best status:            rejected:window_stability
reason:                 too_many_low_target_all_positive_windows
precision:              0.529
precision lift:         1.13
recall:                 0.256
FPR:                    0.200
decision cost / row:    0.881
missed high-target:     2 / 8
zero-positive windows:  8 / 20
low-target all-positive: 1 / 9
```

Interpretation: the stable-threshold fix reduced missed high-UP windows from
`5/8` to `2/8`, so it moved in the intended direction. The tradeoff was too
many false positives and one low-target all-positive window. The immediate
issue is signal caps: `max_signals=0` means unlimited signals in the current
code, not zero signals.

Target-aware UP no-unlimited-caps rerun:

```text
run:
test_output/rpf_clean_classification_optuna/20260622_092243_classification_classification_cls_extreme_up_ge_2x_down_hvo

tuning status:          ok
tuning precision:       0.539
tuning precision lift:  1.15
tuning recall:          0.237
tuning FPR:             0.178
tuning cost / row:      0.831
tuning missed high:     0 / 8
tuning zero windows:    1 / 20
tuning low all-positive:0 / 9

holdout status:         pass window stability
holdout precision:      0.547
holdout precision lift: 1.07
holdout recall:         0.237
holdout FPR:            0.204
holdout cost / row:     0.890
holdout missed high:    1 / 3
holdout zero windows:   1 / 10
holdout low all-positive:0
```

Interpretation: removing unlimited signal caps fixed the immediate stability
failure and produced a holdout. The holdout is still weak: precision lift is
only `1.07`, false-positive rate is high, and cost per row is worse than the
best earlier sparse UP candidate. This is progress in process reliability, not
model promotion.

Post-run live-safety audit:

```text
holdout AUC:              0.463
holdout PR AUC:           0.465
holdout base positive:    0.511
probability std:          very small in several holdout batches
threshold-only 0.40/0.45: predicts 2160/2400 rows positive, FPR ~0.995
threshold-only 0.50:      precision 0.374, FPR 0.307, cost/row 1.171
threshold-only >=0.55:    zero signals
```

The positive signal cap improved the report by selecting top rows inside the
whole prediction batch. That is useful for diagnosis, but it is not live-safe
for row-by-row trading because future rows in the same batch affect the current
row's rank. Treat all positive `max_signals_per_batch` results as exploratory
unless they are run under `causal_signal_budget`.

As of 2026-06-22, decision policy is explicit in the classifier:

```text
--decision-policy threshold_only
--decision-policy causal_signal_budget
--decision-policy batch_topk_offline
```

`threshold_only` and `causal_signal_budget` write
`decision_policy_live_safe=true`. `batch_topk_offline` writes
`decision_policy_live_safe=false` and is diagnostic only.

## Current Code Fix Validation

After the target-aware UP rerun, the threshold/cap selector was corrected:

- before: `stable_prediction_quality` trials selected validation thresholds by
  pure validation decision cost;
- now: `stable_prediction_quality` trials select validation thresholds by the
  stable quality score;
- the score now includes an explicit recall term.

The 2026-06-22 CPU rerun validated the direction of this fix: high-target
misses dropped, but false-positive and all-positive instability increased.
The following no-unlimited-caps rerun validated that `max_signals=0` was a real
instability source. Do not widen from this result yet because holdout precision
lift and false-positive control are still weak.

## Next Work

Do not run another capped UP search as the next step. Live-safe decisions are
now separated from offline diagnostics:

```text
threshold_only
causal_signal_budget
batch_topk_offline
```

`threshold_only` and `causal_signal_budget` are eligible for promotion.
`batch_topk_offline` is diagnostic only and must be labeled that way in reports.

Next, rerun the current best UP and DOWN configurations under live-safe
policies and compare them against the existing cap-based exploratory reports.
If live-safe precision lift remains near `1.0` or AUC remains below random,
stop that feature-scope branch and test a different feature scope or target
definition.

## Pass/Fail Interpretation

The next run is useful if it reduces:

```text
prediction_missed_high_target_window_rate
prediction_zero_positive_window_rate
prediction_decision_cost_per_row
```

It should not increase:

```text
prediction_low_target_all_positive_window_rate
prediction_all_positive_window_rate
prediction_high_fpr_window_rate
```

If the best trial still fails only on missed high-target windows, the next
change should search a more recall-friendly UP feature scope or signal policy.
If it passes tuning stability, then run the corresponding holdout confirmation
and inspect `holdout_summary.json`.

If live-safe replay fails, do not add more CatBoost capacity. The limiting
problem is probability/ranking quality, not threshold search.

## Specialist Signal Objective

As of 2026-06-22, the binary classifier has a second stable objective:

```text
stable_signal_quality
```

This objective is for the current model-bank direction. It assumes the useful
model may fire in only a minority of batches, but those active batches should
be precise and should repeat in short regimes rather than appear as isolated
one-off spikes.

The fold pipeline remains unchanged and leak-safe:

```text
train batches
-> train-only ElasticNet selector and scaler
-> optional causal CNN trained only on train/train+validation rows
-> CatBoost classifier
-> validation-selected threshold
-> refit on train+validation
-> prediction batch scoring
```

`stable_signal_quality` scores the prediction batches by:

```text
precision lift
precision
low false-positive rate
low false-discovery rate
active-window precision
repeated active-window precision
active-batch rate
repeated active-batch rate
low signal churn
low all-positive / high-FPR / high-cost window rates
```

Recall is only a weak anti-dead-model term. This matches the current trading
interpretation: a sparse model can be useful if it repeatedly emits clean
signals, while high recall with noisy false positives is not useful.

Window reports now include persistence diagnostics:

```text
prediction_active_signal_window_count
prediction_active_signal_window_rate
prediction_active_signal_run_count
prediction_active_signal_run_length_mean
prediction_active_signal_run_length_max
prediction_repeated_active_signal_window_count
prediction_repeated_active_signal_window_rate
prediction_isolated_active_signal_window_count
prediction_signal_churn_rate
prediction_active_signal_window_precision_mean
prediction_repeated_active_signal_window_precision_mean
```

Use these fields before deciding whether a configuration belongs in a future
UP or DOWN specialist model bank.
