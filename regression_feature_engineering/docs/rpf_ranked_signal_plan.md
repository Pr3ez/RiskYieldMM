# RPF Ranked-Signal Plan

## Purpose

Define the active replacement for widening the RPF binary probability
classifier.

The ranked-signal workflow asks a narrower question:

```text
Which rows in the next prediction batch are worth signaling with low false
positives and repeated active batches?
```

It does not try to maximize global binary classification quality.

## Current Status

Status: `dual_target_active_candidate_ready_for_smoke`.

Candidate runner:

```bash
python -m regression_feature_engineering.walkforward.rank_signal
```

Adaptive router:

```bash
python -m regression_feature_engineering.walkforward.rank_signal_router
```

Dual-target tracking:

```text
rpf_dual_target_tracking.md
```

Output root:

```text
test_output/rpf_ranked_signal/
test_output/rpf_ranked_signal_router/
```

The old commands remain available but are now historical diagnostics for this
research branch:

```text
python -m regression_feature_engineering.walkforward.classify
python -m regression_feature_engineering.walkforward.classify_optuna
```

EMA gates, learned gates, signal banks, and decision banks remain abandoned or
deferred unless a new plan explicitly reopens them.

The active row-rule output mode for new side-symmetric experiments is:

```text
--row-rule-gate-output-mode active_candidate
```

The older mode remains for reproducing historical DOWN-only artifacts:

```text
--row-rule-gate-output-mode active_down_candidate
```

Do not use `active_down_candidate` for new dual-target conclusions.

## Scope

First benchmark:

```text
asset: BTCUSDT
root: 8h/B
feature set: regression_path_features_v1
sides: up, down
```

This plan covers RPF-native ranked-signal experiments only. It does not cover
old HTF features, EMA gates, learned gates, signal banks, decision banks, or
production trading execution.

## Source Of Truth

- Candidate command: `regression_feature_engineering/walkforward/rank_signal.py`
- Adaptive router command:
  `regression_feature_engineering/walkforward/rank_signal_router.py`
- Current state: `current_feature_state.md`
- Binary audit baseline: `rpf_binary_walkforward_audit_summary.md`
- Feature panels: `rpf_feature_evidence_panel_workflow.md`
- CNN panel diagnostics: `rpf_cnn_feature_diagnostic.md`

## What This Does Not Decide

This document does not promote a model, choose a final side, choose final
thresholds, or claim RPF features are predictively useful. It defines the next
leak-safe implementation path and its acceptance checks.

## Model Contract

Per fold:

```text
RPF features
-> train-only scaler
-> ElasticNet relevance feature selector
-> optional causal sequence memory features
-> CatBoostRanker grouped by batch_id
-> validation-calibrated threshold
-> causal timestamp-order signal budget
-> prediction-batch metrics
```

The ranker uses continuous side relevance:

```text
up_relevance   = up_extreme / (up_extreme + down_extreme + 1e-12)
down_relevance = down_extreme / (up_extreme + down_extreme + 1e-12)
```

The binary `2x` target is used only for signal-quality metrics:

```text
UP:   up_extreme > 0 and up_extreme >= 2 * down_extreme
DOWN: down_extreme > 0 and down_extreme >= 2 * up_extreme
```

Rows are grouped by:

```text
group_id = batch_id
```

Pools are sorted by:

```text
batch_id, timestamp
```

## Leak-Safety Rules

- Feature/label joins are exact on `timestamp,batch_id`.
- ElasticNet feature selection uses train rows only.
- Tabular and sequence scalers fit on train rows only.
- Sequence windows end at the anchor row.
- Validation rows calibrate threshold and signal budget.
- Prediction rows are never used for feature selection, scaler fitting, ranker
  fitting, or threshold selection.
- The ranker is not refit on train+validation in v1, because raw rank scores can
  shift and invalidate validation-selected thresholds.
- Live decisions never sort the full prediction batch by future-known score.
  They process rows in timestamp order and stop after
  `max_signals_per_batch`.

Full-batch top-k ranking is allowed only as a diagnostic and must be marked
non-live-safe.

## Adaptive Router Contract

The router is the active adaptive path. For each prediction fold and side, it
trains a small fixed candidate pool, evaluates candidates on validation
batches, selects the best passing branch, and scores the unseen prediction
batch.

Default candidate set:

```text
UP:   none, small ROCKET 16/32/64 kernels
DOWN: none, diagnostic small ROCKET 16/32/64 kernels
```

Default validation gates:

```text
min_validation_signal_count = 3
min_validation_precision_lift = 1.10
max_validation_false_discovery_rate = 0.60
min_validation_active_window_rate = 0.10
max_validation_zero_signal_window_rate = 0.90
```

Tie-break order:

```text
ranked_signal_quality
precision_lift
lower false_discovery_rate
lower sequence_feature_count
```

Router artifacts:

```text
candidate_validation_metrics.parquet
selected_candidates.parquet
router_window_metrics.parquet
router_prediction_scores.parquet
router_decisions.parquet
block_summary.parquet
side_summary.json
conflict_diagnostics.parquet
```

Prediction metrics are never allowed to choose candidates. If no candidate
passes validation gates, that side emits no signal for the prediction batch.

Use `--window-end-offset-steps` to evaluate older chronological slices instead
of always selecting the latest windows.

## Sequence Modes

Supported modes:

```text
none
causal_rocket_v1
causal_cnn_v1
```

`none` is the first ranker baseline.

`causal_rocket_v1` is the preferred first sequence-memory A/B because it is
deterministic and cheaper than a trainable CNN.

`causal_cnn_v1` remains available as a controlled comparison, but previous
classifier runs showed that CNN embeddings can improve precision while
worsening coverage and stability.

## Objective

Primary trial score:

```text
ranked_signal_quality
```

Formula:

```text
score =
  2.0 * max(0, precision_lift - 1)
+ 1.0 * precision
+ 0.6 * active_window_rate
+ 0.6 * high_target_window_capture_rate
- 1.5 * false_discovery_rate
- 1.0 * zero_signal_window_rate
- 1.0 * missed_high_target_window_rate
- 0.5 * high_false_positive_window_rate
- 0.25 * selected_feature_count / 160
```

Promotion diagnostics:

```text
precision
precision_lift
false positives
false-positive rate
active-window rate
zero-signal-window rate
high-target-window capture rate
missed-high-target-window rate
decision cost per row
decision cost per signal
```

AUC, PR AUC, NDCG, and full-batch top-k are diagnostics only.

## Artifacts

Each run writes:

```text
events.jsonl
stage_status.json
trials.parquet
window_metrics.parquet
prediction_scores.parquet
rank_decisions.parquet
selected_features.parquet
sequence_diagnostics.parquet
best_config.json
holdout_summary.json
holdout_window_metrics.parquet
holdout_prediction_scores.parquet
report.md
```

## First Smoke Commands

Use the latest readiness run:

```bash
export PY="/media/przem/linux_data/conda/envs/ml_env/bin/python"
export READINESS_RUN="$(ls -td test_output/rpf_clean_walkforward/*_readiness_* | head -1)"
export UP_PANEL="$(ls -td test_output/rpf_feature_panels/*up_ge_2x_down*/selected_panel_160.json | head -1)"
export DOWN_PANEL="$(ls -td test_output/rpf_feature_panels/*down_ge_2x_up*/selected_panel_160.json | head -1)"
```

UP smoke:

```bash
"$PY" -m regression_feature_engineering.walkforward.rank_signal \
  --asset BTCUSDT \
  --root 8h/B \
  --side up \
  --base-run "$READINESS_RUN" \
  --tabular-panel-path "$UP_PANEL" \
  --sequence-mode none \
  --n-steps 5 \
  --holdout-steps 0 \
  --n-trials 2 \
  --train-batches-choices 20 \
  --val-batches-choices 5 \
  --iterations-choices 5,10 \
  --depth-choices 2 \
  --learning-rate-choices 0.03 \
  --l2-leaf-reg-choices 30 \
  --random-strength-choices 1 \
  --elasticnet-alpha-choices 0.01,0.03 \
  --elasticnet-l1-ratio-choices 0.5 \
  --elasticnet-prefilter-features-choices 80 \
  --elasticnet-max-features-choices 20 \
  --elasticnet-min-features 5 \
  --elasticnet-coef-eps-choices 1e-8 \
  --threshold-quantile-grid 0.95 \
  --max-signals-grid 5 \
  --task-type CPU
```

DOWN smoke:

```bash
"$PY" -m regression_feature_engineering.walkforward.rank_signal \
  --asset BTCUSDT \
  --root 8h/B \
  --side down \
  --base-run "$READINESS_RUN" \
  --tabular-panel-path "$DOWN_PANEL" \
  --sequence-mode none \
  --n-steps 5 \
  --holdout-steps 0 \
  --n-trials 2 \
  --train-batches-choices 20 \
  --val-batches-choices 5 \
  --iterations-choices 5,10 \
  --depth-choices 2 \
  --learning-rate-choices 0.03 \
  --l2-leaf-reg-choices 30 \
  --random-strength-choices 1 \
  --elasticnet-alpha-choices 0.01,0.03 \
  --elasticnet-l1-ratio-choices 0.5 \
  --elasticnet-prefilter-features-choices 80 \
  --elasticnet-max-features-choices 20 \
  --elasticnet-min-features 5 \
  --elasticnet-coef-eps-choices 1e-8 \
  --threshold-quantile-grid 0.95 \
  --max-signals-grid 5 \
  --task-type CPU
```

## First Real A/B

Run the no-sequence ranker first:

```text
sequence_mode = none
n_steps = 30
holdout_steps = 10
n_trials = 8-12
```

Only then compare:

```text
sequence_mode = causal_rocket_v1
```

using the same windows, panels, and trial budget.

Do not widen CatBoost or sequence ranges until the ranker baseline beats the
previous classifier branch on held-out windows.

Completed no-sequence baseline on 2026-06-22:

```text
UP run:   test_output/rpf_ranked_signal/20260622_212507_rank_signal_btcusdt_8h_b_up/
DOWN run: test_output/rpf_ranked_signal/20260622_213040_rank_signal_btcusdt_8h_b_down/
```

Baseline evidence:

| Side | Best tuning precision | Best tuning lift | Holdout precision | Holdout lift | Holdout signals | Holdout TP/FP |
|---|---:|---:|---:|---:|---:|---:|
| UP | `0.500` | `1.070` | `0.680` | `1.331` | `25` | `17/8` |
| DOWN | `0.578` | `1.575` | `0.432` | `2.185` | `74` | `32/42` |

Next controlled test:

```text
sequence_mode = causal_rocket_v1
tabular_panel = same side-specific evidence panel used by the baseline
sequence_panel = side-specific CNN diagnostic panel
n_steps = 30
holdout_steps = 10
n_trials = 8
```

Purpose:

- test whether causal short-sequence summaries improve high-target capture or
  precision lift over the no-sequence baseline;
- keep the same windows and narrow parameter ranges so any improvement is
  attributable to sequence memory, not a changed search shape;
- reject ROCKET if it increases false positives, lowers holdout lift, or only
  increases signal count without improving precision.

Completed causal ROCKET A/B on 2026-06-22:

```text
UP run:   test_output/rpf_ranked_signal/20260622_214036_rank_signal_btcusdt_8h_b_up/
DOWN run: test_output/rpf_ranked_signal/20260622_214751_rank_signal_btcusdt_8h_b_down/
```

Holdout comparison:

| Side | Mode | Precision | Lift | Active windows | High-target capture | Signals | TP/FP |
|---|---|---:|---:|---:|---:|---:|---:|
| UP | `none` | `0.680` | `1.331` | `0.500` | `0.571` | `25` | `17/8` |
| UP | `causal_rocket_v1` | `0.568` | `1.111` | `0.900` | `0.714` | `37` | `21/16` |
| DOWN | `none` | `0.432` | `2.185` | `0.900` | `0.750` | `74` | `32/42` |
| DOWN | `causal_rocket_v1` | `0.139` | `0.702` | `0.800` | `0.250` | `36` | `5/31` |

Decision:

- reject `causal_rocket_v1` for DOWN in this setup;
- do not widen ROCKET globally;
- keep no-sequence as the current DOWN baseline;
- treat UP ROCKET as diagnostic only: it improves active-window coverage and
  high-target capture, but precision and lift degrade because false positives
  double.

Next decision-control test:

```text
UP:
  mode = causal_rocket_v1
  freeze around best UP ROCKET shape
  vary only threshold_quantile and max_signals_per_batch

DOWN:
  mode = none
  freeze around best DOWN no-sequence shape
  vary only threshold_quantile and max_signals_per_batch
```

Purpose:

- UP: test whether stricter signal emission keeps ROCKET's better
  high-target capture while recovering precision and lift.
- DOWN: test whether the no-sequence DOWN baseline can reduce false positives
  without losing its strong holdout lift.

Candidate grids:

```text
UP threshold_quantile: 0.95,0.975,0.99
UP max_signals:        1,2,3

DOWN threshold_quantile: 0.95,0.975,0.99
DOWN max_signals:        1,3,5
```

This is intentionally a decision-control run, not a new model search.

Completed decision-control run on 2026-06-22:

```text
UP run:   test_output/rpf_ranked_signal/20260622_221932_rank_signal_btcusdt_8h_b_up/
DOWN run: test_output/rpf_ranked_signal/20260622_222610_rank_signal_btcusdt_8h_b_down/
```

Holdout comparison:

| Side | Mode | Threshold q | Max signals | Precision | Lift | Signals | TP/FP | FPR | Cost/row |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| UP | `none` | `0.95` | `5` | `0.680` | `1.331` | `25` | `17/8` | `0.00681` | `0.5204` |
| UP | `rocket_control` | `0.95` | `1` | `0.556` | `1.088` | `9` | `5/4` | `0.00341` | `0.5171` |
| DOWN | `none` | `0.90` | `10` | `0.432` | `2.185` | `74` | `32/42` | `0.02182` | `0.2721` |
| DOWN | `none_control` | `0.95` | `1` | `0.444` | `2.246` | `9` | `4/5` | `0.00260` | `0.2067` |

Decision:

- UP decision-control is rejected as a replacement for the no-sequence UP
  baseline because precision and lift degraded too much.
- DOWN decision-control is the current best precision-control candidate. It
  preserves lift and high-target capture while sharply reducing false-positive
  rate and cost per row. Recall is very low, so this is a specialist signal
  candidate, not a broad classifier.

UP ROCKET diagnosis:

- full ROCKET used `128` kernels and appended `384` sequence features after the
  ElasticNet tabular selector;
- those sequence features were not selected by ElasticNet before CatBoost;
- holdout offline top-k diagnostics show ROCKET worsened UP score ordering:
  no-sequence top-5 precision averaged about `0.90`, while full ROCKET averaged
  about `0.68`;
- next test should reduce sequence branch size instead of widening it.

Next longer diagnostic:

```text
n_steps = 50
holdout_steps = 20

UP no-sequence confirmation:
  freeze around current no-sequence UP baseline
  vary only threshold/budget

UP small ROCKET:
  freeze around current ROCKET UP shape
  vary rocket_kernels = 16,32,64
  vary threshold/budget

DOWN no-sequence/control confirmation:
  freeze around current DOWN control shape
  vary only threshold/budget
```

Purpose:

- check whether the current 10-window holdout evidence survives a larger
  `20`-window holdout;
- identify whether ROCKET failed because the sequence branch was too wide;
- keep model, window, and selector shapes narrow so the run remains
  interpretable.

Completed longer diagnostic on 2026-06-23:

| Side | Mode | Run | Holdout precision | Holdout lift | Signals | TP/FP | Active windows | High-target capture |
|---|---|---|---:|---:|---:|---:|---:|---:|
| UP | `none` | `20260622_224229_rank_signal_btcusdt_8h_b_up` | `0.571` | `1.036` | `21` | `12/9` | `0.350` | `0.267` |
| UP | `small_rocket` | `20260623_000231_rank_signal_btcusdt_8h_b_up` | `0.765` | `1.386` | `17` | `13/4` | `0.450` | `0.467` |
| DOWN | `none_control` | `20260623_002707_rank_signal_btcusdt_8h_b_down` | `0.459` | `2.274` | `37` | `17/20` | `0.650` | `0.571` |

Decision:

- UP full ROCKET was too noisy, but small ROCKET with `32` kernels improved the
  larger holdout. This becomes the current UP candidate.
- UP no-sequence did not survive the larger holdout strongly enough.
- DOWN remains a no-sequence problem for now. ROCKET stays rejected for DOWN.
- Neither side is production-promoted; both still need a second confirmation
  with the side-specific winning shapes and narrower decision controls.

## Prior Baselines To Beat

Best completed classifier evidence:

```text
DOWN holdout precision:         0.375
DOWN holdout precision lift:    1.86
UP holdout: rejected; precision below local base rate
```

Minimum useful evidence:

```text
precision_lift > 1.20
active_window_rate >= 0.15
zero_signal_window_rate <= 0.85
missed_high_target_window_rate improves versus 1.0
false-positive rate does not exceed prior same-side baseline
```

## Adaptive Router Result

First completed `default_v1` router run:

```text
run: test_output/rpf_ranked_signal_router/20260623_020631_rank_signal_router_btcusdt_8h_b/
windows: 240
prediction batches: 5617..5856
```

Summary:

| Side | Precision | Base Rate | Lift | Signals | TP/FP | Active Windows | High-Target Capture |
|---|---:|---:|---:|---:|---:|---:|---:|
| UP | `0.400` | `0.396` | `1.010` | `185` | `74/111` | `0.346` | `0.239` |
| DOWN | `0.508` | `0.375` | `1.354` | `244` | `124/120` | `0.346` | `0.308` |

Router branch selection worked mechanically and adapted over time, but the
validation metrics did not reliably predict next-batch precision. Validation
quality to prediction precision correlation was approximately `-0.035` for UP
and `0.013` for DOWN. Treat this router run as plumbing plus longer-span
evidence, not as a promotable signal.

Next ranked-signal work should tighten candidate validation/gating before
running more broad chronological sweeps.

Implemented stricter router gate controls after the first 240-window result:

```text
--min-validation-active-batch-count
--min-validation-lift-positive-batch-rate
--min-validation-median-active-precision-lift
--max-validation-median-active-false-discovery-rate
```

Purpose: avoid selecting a candidate from one aggregate validation score when
the validation signal is concentrated in too few validation batches. The next
router run should first use these gates on a smaller chronological slice before
another full 240-window run.

Strict-gate test result:

```text
run: test_output/rpf_ranked_signal_router/20260623_102707_rank_signal_router_btcusdt_8h_b/
windows: 120
batches: 5737..5856
```

| Side | Precision | Base Rate | Lift | Signals | TP/FP | Active Windows |
|---|---:|---:|---:|---:|---:|---:|
| UP | `0.417` | `0.430` | `0.969` | `12` | `5/7` | `0.042` |
| DOWN | `0.200` | `0.333` | `0.600` | `15` | `3/12` | `0.042` |

Compared with the previous loose router on the same `5737..5856` windows,
strict gates reduced signals sharply and did not improve precision. This exact
gate setting is rejected. The next candidate-selection improvement should not
be simply "stricter aggregate gates"; it needs a better validation-to-prediction
reliability test or a different candidate objective.

Root-cause inspection after the strict-gate rejection:

```text
UP active precision vs true prediction-batch base-rate correlation:   ~0.842
DOWN active precision vs true prediction-batch base-rate correlation: ~0.777
UP lag-1 batch base-rate autocorrelation:                             ~0.014
DOWN lag-1 batch base-rate autocorrelation:                           ~-0.045
UP median row-selection lift on active windows:                       ~1.00
DOWN median row-selection lift on active windows:                     ~1.017
```

Interpretation:

- current precision mostly comes from whether the whole prediction batch is
  favorable;
- the router does not know that future batch base rate;
- the model fires at similar rates in favorable and unfavorable batches;
- validation quality does not monotonically predict next-batch quality;
- the current row-level ranker is not yet producing stable row-level edge.

Required before another modeling sweep:

- persist router selected features;
- persist validation row scores and validation per-batch metrics;
- persist sequence diagnostics;
- add a separate batch-regime diagnostic/modeling stage that asks whether the
  next batch positive-rate regime can be predicted at all from live-safe RPF
  state.

Prepared diagnostic router output after this inspection:

```text
candidate_validation_scores.parquet
candidate_validation_window_metrics.parquet
selected_features.parquet
sequence_diagnostics.parquet
```

These artifacts are required for the next run because they let us inspect:

- whether validation score scale transfers into prediction;
- whether selected ElasticNet features are stable or rotating;
- which sequence branches add useful context versus noise;
- whether candidate validation failures are caused by one bad validation batch
  or broad instability.

Diagnostic loose-router rerun with these artifacts:

```text
run: test_output/rpf_ranked_signal_router/20260623_111705_rank_signal_router_btcusdt_8h_b/
windows: 120
batches: 5737..5856
```

This rerun reproduced the previous loose-router result on the same windows:

| Side | Precision | Base Rate | Lift | Signals | TP/FP | Active Windows |
|---|---:|---:|---:|---:|---:|---:|
| UP | `0.439` | `0.430` | `1.021` | `98` | `43/55` | `0.358` |
| DOWN | `0.500` | `0.333` | `1.500` | `116` | `58/58` | `0.333` |

Candidate-level prediction transfer:

| Side | Candidate | Precision | Lift | Decision |
|---|---:|---:|---:|---|
| DOWN | `down_rocket_16_diag_v1` | `0.583` | `1.568` | keep |
| DOWN | `down_none_v1` | `0.548` | `1.559` | keep |
| DOWN | `down_rocket_64_diag_v1` | `0.417` | `1.373` | optional diagnostic |
| DOWN | `down_rocket_32_diag_v1` | `0.000` | `0.000` | remove |
| UP | `up_none_v1` | `0.500` | `1.130` | keep |
| UP | `up_rocket_64_v1` | `0.600` | `1.121` | keep |
| UP | `up_rocket_32_v1` | `0.250` | `0.824` | remove |
| UP | `up_rocket_16_v1` | `0.290` | `0.781` | remove |

Validation metrics still overstate next-batch quality. Examples:

- `up_none_v1`: validation lift around `2.01`, prediction lift `1.13`;
- `up_rocket_16_v1`: validation lift around `1.56`, prediction lift `0.78`;
- `down_rocket_32_diag_v1`: validation lift around `1.71`, prediction lift
  `0.00`.

Conclusion: the next router candidate set should be pruned before another long
run. The main defect is validation-to-prediction transfer, not missing output
artifacts or random ElasticNet feature rotation.

Implemented transfer-fix path:

```text
selection_mode: prequential_reliability_v1
candidate_set:  pruned_reliability_v1
```

The old router remains available as:

```text
selection_mode: validation_only
candidate_set:  default_v1
```

`prequential_reliability_v1` changes candidate selection as follows:

- current validation remains a sanity check;
- every candidate is shadow-scored on the prediction batch;
- candidate reliability is computed only from prior matured prediction windows;
- current prediction metrics are written but cannot select the current
  candidate;
- insufficient reliability history emits no signal.

2026-06-23 row-lift correction:

- the older 120-window prequential run showed that global candidate precision
  lift is not enough;
- reliability now separates:
  - `window_selection_lift`: whether a branch fires in higher-base batches;
  - `selected_window_row_lift`: whether selected rows beat the base rate inside
    those active batches;
  - `selected_window_row_lift_lcb`: Wilson lower-bound version used as the
    active row-edge gate;
- default active gate:
  `--reliability-min-selected-window-row-lift-lcb 1.05`;
- optional side-specific overrides:
  `--up-reliability-min-selected-window-row-lift-lcb`,
  `--down-reliability-min-selected-window-row-lift-lcb`,
  `--up-reliability-min-precision-lift-lcb`,
  `--down-reliability-min-precision-lift-lcb`.

This prevents a branch from passing just because it fired in easier batches.
The branch must also show a historical row-level edge within the same kind of
active windows.

## Batch-State Gate

The row-lift gated run showed a remaining failure mode: the ranker can still
fire into a prediction batch with no positive rows for the selected side. The
active fix is a two-stage, selective-prediction style gate before row decisions:

```text
train-only batch-state model
-> validation sanity metrics
-> prediction-batch prefix evidence
-> allow/suppress side for this batch
-> row ranker decisions only if gate passes
```

Implemented mode:

```text
--batch-state-gate-mode logistic_prefix_v1
```

Contract:

- train labels define whether each past batch had enough side opportunity:
  `batch_positive_rate >= --batch-state-gate-min-positive-rate`;
- the gate trains a fold-local logistic model from train batch prefix summaries;
- prediction uses only the first `--batch-state-gate-prefix-rows` rows of the
  current prediction batch;
- all decisions before the prefix are suppressed;
- if the gate probability is below
  `--batch-state-gate-probability-threshold`, the whole side is suppressed for
  that prediction batch;
- current prediction labels are written for diagnostics only and never used by
  the current gate decision.

Research basis:

- selective classification / reject option: accept fewer predictions when
  confidence is insufficient;
- financial meta-labeling: use a secondary layer to filter false positives from
  a primary signal;
- concept drift / prequential evaluation: trust must adapt from chronological
  historical outcomes, not shuffled validation.

Active pruned candidates:

```text
UP:   up_none_v1, up_rocket_64_v1
DOWN: down_none_v1, down_rocket_16_diag_v1
```

Optional diagnostic:

```text
down_rocket_64_diag_v1 via --include-diagnostic-candidates
```

New reliability artifacts:

```text
candidate_prediction_window_metrics.parquet
candidate_reliability_state.parquet
candidate_selection_audit.parquet
reliability_block_summary.parquet
batch_regime_diagnostics.parquet
candidate_prediction_scores.parquet  # only with --write-candidate-prediction-scores
```

### Experimental Specialist Entry

The first explicit specialist entry mode is:

```text
--specialist-entry-mode down_none_validation_quiet_v1
```

It exists because `down_none_v1` showed high-quality sparse shadow signals when
validation produced no candidate signals. This mode is intentionally narrow:

```text
candidate = down_none_v1
selection_mode = prequential_reliability_v1
validation candidate signal count = 0
batch_state_gate_passed = true
```

It does not use current prediction labels. It uses only validation state and the
prediction-time-safe batch-state gate. Final row decisions still come from the
normal causal signal-budget policy. Treat this mode as experimental until it
survives both older-block and latest-block replay.

Replay status:

- older `120`-window replay:
  `test_output/rpf_ranked_signal_router/20260623_174040_rank_signal_router_btcusdt_8h_b/`;
  DOWN produced `11` signals, `11` TP / `0` FP, precision `1.0`;
- latest `120`-window replay:
  `test_output/rpf_ranked_signal_router/20260623_180640_rank_signal_router_btcusdt_8h_b/`;
  DOWN produced `23` signals, `3` TP / `20` FP, precision `0.1304`.

Conclusion: `down_none_validation_quiet_v1` is not a promotable general entry
rule. It captures one older sparse cluster but fails latest transfer. Keep it
as diagnostic evidence only. The next ranked-router work should explain the
regime difference between older true-positive clusters and latest false-positive
clusters before adding another threshold or candidate sweep.

### Transfer Diagnostic

The active diagnostic command is:

```bash
python -m regression_feature_engineering.walkforward.rank_signal_transfer_diagnostic
```

It compares completed router runs without retraining models and writes:

```text
candidate_transfer_table.parquet
safe_context_features.parquet
active_window_comparison.parquet
transfer_report.md
```

Contract:

- `safe_context_features.parquet` contains only prediction-time-safe fields:
  validation metrics, candidate fail reasons, batch-state gate outputs,
  threshold/score summaries, selected feature count, sequence feature count,
  prior reliability, and prior batch-regime diagnostics;
- current prediction outcomes such as TP/FP counts, precision, precision lift,
  base rate, and `candidate_good/bad` are excluded from safe context;
- `candidate_transfer_table.parquet` includes post-hoc labels and is diagnostic
  only.

First completed run:

```text
run: test_output/rpf_ranked_signal_transfer_diagnostic/20260623_183857_rank_signal_transfer_diagnostic/
rows: 960 candidate/window rows
safe-context leak check: pass
active candidate windows: 157
good candidate windows: 47
bad candidate windows: 86
```

`context_meta_router_v1` remains deferred. The next step is separator analysis
on `safe_context_features.parquet` joined to post-hoc labels, not direct
meta-router deployment.

### Transfer Separator Analysis

The separator command is:

```bash
python -m regression_feature_engineering.walkforward.rank_signal_transfer_separator
```

It consumes a completed transfer diagnostic run and writes:

```text
feature_separation.parquet
candidate_separator_summary.parquet
separator_report.md
```

First completed run:

```text
run: test_output/rpf_ranked_signal_transfer_separator/20260623_185104_rank_signal_transfer_separator/
input: test_output/rpf_ranked_signal_transfer_diagnostic/20260623_183857_rank_signal_transfer_diagnostic/
active good/bad rows: 133
safe features tested: 69
separator rows: 403
```

Main finding:

- candidate-specific separators are much stronger than global separators;
- `context_meta_router_v1` should be candidate-conditioned;
- do not use one global validation/reliability threshold for all branches;
- next implementation should be a dry-run meta-router simulator over existing
  transfer rows before modifying live router selection.

First smoke command:

```bash
"$PY" -m regression_feature_engineering.walkforward.rank_signal_router \
  --asset BTCUSDT \
  --root 8h/B \
  --base-run "$READINESS_RUN" \
  --up-tabular-panel-path "$UP_PANEL" \
  --up-sequence-panel-path "$UP_SEQ_PANEL" \
  --down-tabular-panel-path "$DOWN_PANEL" \
  --down-sequence-panel-path "$DOWN_SEQ_PANEL" \
  --candidate-set pruned_reliability_v1 \
  --selection-mode prequential_reliability_v1 \
  --outer-window-count 40 \
  --evaluation-block-size 10 \
  --reliability-lookback-windows 20 \
  --reliability-min-history-windows 10 \
  --reliability-min-signals 5 \
  --reliability-min-active-windows 2 \
  --reliability-min-selected-window-row-lift-lcb 1.05 \
  --task-type CPU \
  --thread-count 8 \
  --log-every-windows 5
```

### Meta-Router Simulator

The artifact-only simulator command is:

```bash
python -m regression_feature_engineering.walkforward.rank_signal_meta_router_simulator
```

It is the required bridge between transfer diagnostics and live
`context_meta_router_v1`. It fits simple candidate-specific context rules from
one matured source block and replays them on another block without changing
router code or using current-window prediction labels as inputs.

First completed simulator run:

```text
run: test_output/rpf_ranked_signal_meta_router_simulator/20260623_205856_rank_signal_meta_router_simulator/
diagnostic input: test_output/rpf_ranked_signal_transfer_diagnostic/20260623_183857_rank_signal_transfer_diagnostic/
rules trained from: older block
replayed on: latest block
```

Result:

- UP remained sparse and clean on latest: `3` signals, `3` TP, `0` FP.
- DOWN did not transfer as a side-router: `38` latest signals, `9` TP,
  `29` FP.
- The failure is concentrated in `down_none_v1`; `down_rocket_16_diag_v1`
  stayed sparse and clean in candidate acceptance.

Conclusion:

- Do not deploy the first meta-router rules as live routing.
- Next run should test a conservative allow-list that excludes or heavily
  rejects `down_none_v1`, then compare against the simulator and reliability
  router on the same older/latest blocks.

Conservative allow-list replay:

```bash
"$PY" -m regression_feature_engineering.walkforward.rank_signal_meta_router_simulator \
  --diagnostic-run test_output/rpf_ranked_signal_transfer_diagnostic/20260623_183857_rank_signal_transfer_diagnostic \
  --candidate-names up_none_v1,up_rocket_64_v1,down_rocket_16_diag_v1 \
  --train-source-block older \
  --test-source-block latest \
  --min-train-good-rows 2 \
  --min-train-bad-rows 2 \
  --min-train-signals 3
```

Completed run:

```text
run: test_output/rpf_ranked_signal_meta_router_simulator/20260623_210014_rank_signal_meta_router_simulator/
older DOWN: 3 signals, 3 TP, 0 FP
older UP:   9 signals, 9 TP, 0 FP
latest DOWN: 2 signals, 2 TP, 0 FP
latest UP:   3 signals, 3 TP, 0 FP
```

Interpretation: the conservative allow-list removes the `down_none_v1`
transfer failure but is very sparse. Before promoting this into live router
selection, replay it on another chronological block or add an explicit
candidate-exclusion option to `rank_signal_router`.

Live router support:

```text
--candidate-name-allowlist up_none_v1,up_rocket_64_v1,down_rocket_16_diag_v1
```

The flag filters the expanded fixed candidate set after `--candidate-set`
construction. When omitted, router behavior is unchanged. The immediate next
live run should use this flag with `pruned_reliability_v1` to test whether the
artifact-only result survives actual fold retraining and routing.

Completed live allow-list run:

```text
run: test_output/rpf_ranked_signal_router/20260623_210606_rank_signal_router_btcusdt_8h_b/
candidate allow-list: up_none_v1, up_rocket_64_v1, down_rocket_16_diag_v1
selection mode: prequential_reliability_v1
result: zero final UP/DOWN decisions
```

Interpretation:

- The candidate allow-list works mechanically.
- `prequential_reliability_v1` is too strict for sparse candidates and rejected
  every side-window.
- Validation-only shadow selection on the same artifacts was still noisy:
  DOWN precision `0.466`, UP precision `0.464`.

Follow-up diagnostic on the same live artifacts:

```text
transfer diagnostic: test_output/rpf_ranked_signal_transfer_diagnostic/20260623_212043_rank_signal_transfer_diagnostic/
meta-rule simulator: test_output/rpf_ranked_signal_meta_router_simulator/20260623_212049_rank_signal_meta_router_simulator/
```

Context-rule replay result:

```text
latest DOWN: 9 signals, 6 TP, 3 FP, precision 0.667, lift 2.000
latest UP:   17 signals, 14 TP, 3 FP, precision 0.824, lift 1.916
```

Next required implementation: add a live `context_rule_v1` selection mode that
uses candidate-specific prediction-safe context rules. Candidate allow-listing
alone should not be rerun as the active transfer fix.

Implementation status:

- `rank_signal_router` supports `--selection-mode context_rule_v1`.
- `--context-rule-path` accepts a simulator run directory or
  `meta_router_rules.parquet`.
- Candidate selection uses rule pass/fail and margin, not the old reliability
  gate.
- Existing `validation_only` and `prequential_reliability_v1` behavior is
  unchanged.

Smoke:

```text
run: test_output/rpf_ranked_signal_router/20260623_212951_rank_signal_router_btcusdt_8h_b/
outer windows: 5
UP: 2 signals, 2 TP, 0 FP
DOWN: 0 signals
```

Next run: replay `context_rule_v1` over the latest 120-window block using the
same conservative allow-list and context-rule artifact.

Completed 120-window replay:

```text
run: test_output/rpf_ranked_signal_router/20260623_213215_rank_signal_router_btcusdt_8h_b/
selection mode: context_rule_v1
outer windows: 120
```

Result:

```text
UP:   17 signals, 14 TP, 3 FP, precision 0.824, lift 1.916
DOWN: 9 signals, 6 TP, 3 FP, precision 0.667, lift 2.000
conflicts: 0
```

This confirms that live context-rule selection is materially different from
plain `prequential_reliability_v1`: it emits sparse decisions and preserves
precision on the latest block. The next validation should test the same frozen
rules on shifted/older chronological blocks before any further tuning.

Shifted older-block replay:

```text
run: test_output/rpf_ranked_signal_router/20260623_214859_rank_signal_router_btcusdt_8h_b/
selection mode: context_rule_v1
window_end_offset_steps: 240
prediction batches: 5497..5616
outer windows: 120
```

Result:

```text
UP:   24 signals, 9 TP, 15 FP, precision 0.375, lift 1.199
DOWN: 0 signals
conflicts: 0
```

Decision: the frozen context rules are not chronologically stable yet. The
latest-block result remains useful evidence that sparse context routing can
work, but the offset-240 replay rejects promotion. Next work should train and
evaluate context-rule banks across multiple chronological blocks, using only
prior matured blocks for each forward test block.

Rule-bank diagnostic command:

```bash
python -m regression_feature_engineering.walkforward.rank_signal_rule_bank
```

Contract:

- each `--block-run name=path` is one chronological router block;
- candidate prediction metrics from the current test block are never used to
  train that test block's rules;
- rules are fit from prior matured blocks only;
- outputs are diagnostic artifacts under:
  `test_output/rpf_ranked_signal_rule_bank/{run_id}/`.

First three-block result:

```text
blocks: offset240 -> middle -> latest
all-prior run:    test_output/rpf_ranked_signal_rule_bank/20260623_221017_rank_signal_rule_bank/
rolling-one run:  test_output/rpf_ranked_signal_rule_bank/20260623_221037_rank_signal_rule_bank/
```

All-prior training failed the latest transition:

```text
latest UP:   113 signals, 56 TP, 57 FP, precision 0.496
latest DOWN: 0 signals
```

Rolling-one-block training preserved the useful middle-to-latest rules:

```text
latest UP:   17 signals, 14 TP, 3 FP, precision 0.824, lift 1.916
latest DOWN: 9 signals, 6 TP, 3 FP, precision 0.667, lift 2.000
```

Decision: recent-block adaptation is a better hypothesis than accumulated
all-prior rules, but the evidence is still too thin. Add at least one older
block and rerun the rolling rule bank before changing the live router.

Four-block rolling rule-bank result:

```text
offset360 router: test_output/rpf_ranked_signal_router/20260623_221301_rank_signal_router_btcusdt_8h_b/
rule bank:        test_output/rpf_ranked_signal_rule_bank/20260623_221856_rank_signal_rule_bank/
```

Caveat:

```text
offset360 evaluated only 40 windows, batches 5457..5496.
```

The active readiness run has `400` frozen windows, so a `120`-window request at
`window_end_offset_steps=360` can only return the oldest `40` windows. Full
120-window offset360 validation requires a longer readiness run.

Rolling-one-block forward results:

```text
offset360 -> offset240:
  DOWN 12 signals, 12 TP, 0 FP, precision 1.000, lift 2.193
  UP    8 signals,  4 TP, 4 FP, precision 0.500, lift 1.599

offset240 -> middle:
  DOWN  6 signals, 3 TP, 3 FP, precision 0.500, lift 1.198
  UP   10 signals, 8 TP, 2 FP, precision 0.800, lift 2.209

middle -> latest:
  DOWN  9 signals,  6 TP, 3 FP, precision 0.667, lift 2.000
  UP   17 signals, 14 TP, 3 FP, precision 0.824, lift 1.916
```

Overall:

```text
DOWN precision 0.778, lift 1.934, 27 signals
UP precision 0.743, lift 2.017, 35 signals
```

Decision: rolling recent-block context rules are promising enough to validate
properly, but not enough to wire into the live router yet. Next run should use
longer readiness windows so each chronological block has the same 120-window
length.

Full-size four-block validation:

```text
readiness: 520 windows
rule bank: test_output/rpf_ranked_signal_rule_bank/20260623_232201_rank_signal_rule_bank/
blocks:
  offset360 5377..5496
  offset240 5497..5616
  middle    5617..5736
  latest    5737..5856
```

Result:

```text
offset360 -> offset240:
  DOWN precision 0.444, lift 0.974, FDR 0.556
  UP   precision 0.435, lift 1.391, FDR 0.565

offset240 -> middle:
  DOWN precision 0.710, lift 1.701, FDR 0.290
  UP   precision 0.408, lift 1.127, FDR 0.592

middle -> latest:
  DOWN precision 0.434, lift 1.302, FDR 0.566
  UP   precision 0.707, lift 1.644, FDR 0.293
```

Overall:

```text
DOWN: 93 signals, precision 0.527, lift 1.310, FDR 0.473
UP:   130 signals, precision 0.546, lift 1.483, FDR 0.454
```

Decision: full-size rolling context rules are not clean enough. They beat base
rate overall but allow too many false positives. Do not wire this objective
into the live router. Next version should add conservative train-rule gates:
minimum train precision, minimum train lift, maximum train FDR, and optionally
maximum accepted active-rate before a rule is eligible for forward replay.

Conservative rule eligibility is now implemented in `rank_signal_rule_bank`.

Additional gate options:

```text
--rule-min-train-signals
--rule-min-train-precision
--rule-min-train-precision-lcb
--rule-min-train-lift
--rule-max-train-fdr
--rule-max-train-active-rate
--rule-lcb-z
```

Side-specific override options are also implemented:

```text
--up-rule-min-train-signals
--up-rule-min-train-precision
--up-rule-min-train-precision-lcb
--up-rule-min-train-lift
--up-rule-max-train-fdr
--up-rule-max-train-active-rate
--up-rule-lcb-z

--down-rule-min-train-signals
--down-rule-min-train-precision
--down-rule-min-train-precision-lcb
--down-rule-min-train-lift
--down-rule-max-train-fdr
--down-rule-max-train-active-rate
--down-rule-lcb-z
```

Calibrated sparse conservative result:

```text
run: test_output/rpf_ranked_signal_rule_bank/20260623_233251_rank_signal_rule_bank/
```

Compared with permissive full-size rule-bank:

```text
DOWN permissive: precision 0.527, lift 1.310, FDR 0.473, signals 93
DOWN gated:      precision 0.536, lift 1.332, FDR 0.464, signals 84

UP permissive:   precision 0.546, lift 1.483, FDR 0.454, signals 130
UP gated:        precision 0.630, lift 1.710, FDR 0.370, signals 81
```

Decision: train-rule eligibility gates help, but unevenly. UP becomes much
cleaner. DOWN remains too noisy. Next implementation should support
side-specific rule gates or a separate DOWN context separator before any live
router wiring.

Side-specific sparse-UP / strict-DOWN replay:

```text
run: test_output/rpf_ranked_signal_rule_bank/20260623_234159_rank_signal_rule_bank/
```

Policy:

```text
UP:
  min signals 3
  min precision 0.65
  min precision LCB 0.35
  min lift 1.40
  max FDR 0.35
  max active rate 0.50

DOWN:
  min signals 10
  min precision 0.65
  min precision LCB 0.50
  min lift 1.40
  max FDR 0.35
  max active rate 0.50
```

Result:

```text
DOWN: 31 signals, precision 0.710, lift 1.764, FDR 0.290
UP:   81 signals, precision 0.630, lift 1.710, FDR 0.370
```

Decision: side-specific gates are the current correct rule-bank direction. UP
can continue as a sparse conservative replay. DOWN can be made cleaner by
requiring more mature train signals and a stronger precision LCB, but this
suppresses two of three replay blocks. The next research/code step should be a
DOWN-specific separator or objective that can recover useful DOWN regimes
without reintroducing the high-FDR blocks.

DOWN-focused separator diagnostic:

```text
run: test_output/rpf_ranked_signal_transfer_separator/20260624_161310_rank_signal_transfer_separator/
candidate: down_rocket_16_diag_v1
source diagnostic: test_output/rpf_ranked_signal_transfer_diagnostic/20260623_212043_rank_signal_transfer_diagnostic/
```

Result:

```text
active good/bad rows: 81
tested safe features: 57
top separator: reliability_precision
top best AUC: 0.703
direction: lower_good
secondary separator: batch_state_gate_probability
best AUC: 0.698
direction: lower_good
```

Decision: current safe-context fields do not provide a strong, intuitive DOWN
separator. The strict DOWN rule gate remains the safest diagnostic. The next
DOWN improvement should add/test better live-safe context features or a
side-specific objective; simply loosening the current rule bank is expected to
restore high false discovery.

Enriched safe-context extension:

`rank_signal_transfer_diagnostic` now adds validation score-shape,
validation-batch stability, and train-only selected-feature profile fields to
`safe_context_features.parquet`.

Validation result:

```text
two-block enriched:
  diagnostic: test_output/rpf_ranked_signal_transfer_diagnostic/20260624_162157_rank_signal_transfer_diagnostic/
  separator:  test_output/rpf_ranked_signal_transfer_separator/20260624_162157_rank_signal_transfer_separator/
  top feature: reliability_precision
  best AUC: 0.703

four-block enriched:
  diagnostic: test_output/rpf_ranked_signal_transfer_diagnostic/20260624_162103_rank_signal_transfer_diagnostic/
  separator:  test_output/rpf_ranked_signal_transfer_separator/20260624_162115_rank_signal_transfer_separator/
  top feature: threshold / validation_score_q95
  best AUC: about 0.599
```

Decision: these additional aggregate context fields do not produce a stable
DOWN separator. The next implementation should move away from aggregate router
metadata and toward causal market/RPF regime context or row-level context
conditioning for DOWN.

## Prior RPF Context Diagnostic

`rank_signal_transfer_diagnostic` now supports causal prior-RPF context:

```text
--rpf-prior-context
--rpf-prior-context-lookbacks 20,60
--rpf-prior-context-max-features-per-family 24
```

Contract:

```text
For pred_batch_id=N, prior context can use only available RPF batches with
batch_id < N. It cannot summarize the current prediction batch.
```

Four-block diagnostic:

```text
test_output/rpf_ranked_signal_transfer_diagnostic/20260624_163148_rank_signal_transfer_diagnostic/
```

Result:

```text
safe context rows: 1440
safe context cols: 301
prior RPF cols: 168
```

DOWN separator:

```text
test_output/rpf_ranked_signal_transfer_separator/20260624_163220_rank_signal_transfer_separator/
candidate: down_rocket_16_diag_v1
top feature: prior_rpf_l20_regime_calendar_state_std_mean
best AUC: 0.605
```

UP separator:

```text
test_output/rpf_ranked_signal_transfer_separator/20260624_163242_rank_signal_transfer_separator/
candidates: up_none_v1, up_rocket_64_v1
top feature: score_mean
best AUC: 0.730 overall
up_rocket_64_v1 score_mean best AUC: 0.770
```

Planning decision:

- prior RPF family context did not solve DOWN transfer;
- UP has usable sparse separator structure;
- DOWN must remain strict until a stronger row-level or side-specific context
  objective is available;
- do not add more candidates until the existing UP/DOWN asymmetry is explained
  by a stable prediction-safe context.

## Row-Level DOWN Diagnostic

Added:

```bash
python -m regression_feature_engineering.walkforward.rank_signal_row_diagnostic
```

Purpose:

```text
Analyze only rows where a candidate/router fired a signal.
Use post-hoc labels only to mark TP versus FP.
Use prediction-time-safe model score fields and same-row RPF feature-family
summaries as separator inputs.
```

Safety:

```text
row_safe_context_features.parquet excludes target_binary, target_relevance,
signal_tp, signal_fp, and signal_outcome.
```

First DOWN result:

```text
run:
  test_output/rpf_ranked_signal_row_diagnostic/20260624_185848_rank_signal_row_diagnostic/

candidate:
  down_rocket_16_diag_v1

source:
  candidate_prediction_scores

rows:
  169 signals, 75 TP, 94 FP
```

Top separators:

```text
rank_score:
  best AUC 0.688, higher_good

row_rpf_structural_room_mean_abs:
  best AUC 0.646, higher_good

row_rpf_cross_asset_context_positive_rate:
  best AUC 0.620, higher_good
```

Middle-to-latest replay evidence:

```text
cross_asset_context_mean_abs >= ~0.299:
  latest 9 signals, 6 TP, 3 FP, precision 0.667

interaction_confluence_mean >= ~0.135:
  latest 11 signals, 7 TP, 4 FP, precision 0.636
```

Planning decision:

- row-level context is more useful for DOWN than aggregate batch/router
  context, but still sparse;
- next experiment should be a row-filter rule bank that trains on prior
  matured signal rows and replays on the next chronological block;
- do not loosen DOWN candidate gates until the row-filter replay proves stable
  across more than one transition.

## Row-Filter Rule Bank

Added:

```bash
python -m regression_feature_engineering.walkforward.rank_signal_row_rule_bank
```

Purpose:

```text
Use completed row diagnostics to learn simple row-level TP/FP filters from
prior matured signal rows and replay them on the next chronological block.
```

Critical rule:

```text
Do not union unlimited eligible row rules.
Use --max-rules-per-candidate, default 1, so a broad collection of filters
cannot accept every signal row and hide the effect.
```

First corrected replay:

```text
run:
  test_output/rpf_ranked_signal_row_rule_bank/20260624_192814_rank_signal_row_rule_bank/

source:
  test_output/rpf_ranked_signal_row_diagnostic/20260624_185848_rank_signal_row_diagnostic/
```

Learned from middle block:

```text
row_rpf_cross_asset_context_mean >= 0.3012844470752333

train:
  10 accepted rows
  10 TP / 0 FP
  precision 1.000
  lift 2.041
```

Replayed on latest block:

```text
9 signals
6 TP / 3 FP
precision 0.667
FDR 0.333
```

Planning decision:

- this is the first useful DOWN row-filter transfer result;
- it is still sparse and based on one transition only;
- next validation must generate row diagnostics across more chronological
  blocks and replay this row-filter rule-bank workflow across multiple
  transitions before any router integration.

## Row-Rule Selection Update

The broader three-block replay showed that the original row-rule score could
overfit threshold coincidences.

Failed broad replay:

```text
run:
  test_output/rpf_ranked_signal_row_rule_bank/20260624_193146_rank_signal_row_rule_bank/

selector:
  rule_score

overall:
  25 signals, 9 TP, 16 FP, precision 0.360
```

Fix:

```text
new selector:
  --rule-selection-score directional_lcb_v1

uses:
  train precision lower bound
  train accepted-row support
  train false-discovery penalty
  train feature-level AUC direction agreement
```

Improved broad replay:

```text
run:
  test_output/rpf_ranked_signal_row_rule_bank/20260624_193705_rank_signal_row_rule_bank/

offset240 -> middle:
  row_rpf_rejection_chop_max_abs <= 0.9583333333333334
  precision 0.619

middle -> latest:
  row_rpf_cross_asset_context_mean >= 0.3012844470752333
  precision 0.667

overall:
  30 signals, 19 TP, 11 FP, precision 0.633
```

Next implementation direction:

- keep `rank_signal` and router candidate branches unchanged;
- validate `directional_lcb_v1` over more chronological blocks;
- if it remains useful, add a shadow router mode that applies matured
  row-filter rules to candidate signal rows before final decisions;
- current prediction labels must only update future row-rule history after
  maturity.

## Four-Block Row-Rule Validation

The four-block validation used fresh router blocks with non-empty candidate
prediction scores:

```text
offset360, offset240, middle, latest
```

Artifacts:

```text
row diagnostic:
  test_output/rpf_ranked_signal_row_diagnostic/20260624_233918_rank_signal_row_diagnostic/

row-rule replay:
  test_output/rpf_ranked_signal_row_rule_bank/20260624_233936_rank_signal_row_rule_bank/
```

Result:

```text
offset360 -> offset240: precision 0.513
offset240 -> middle:    precision 0.660
middle -> latest:       precision 0.286
overall:                precision 0.489
```

This invalidates `directional_lcb_v1` as a final selector. It helped two
transitions but failed badly on the most recent one.

All-eligible replay showed better middle-trained latest rules existed:

```text
unsupervised_factor_layer_positive_rate >= 1.0:
  latest precision 0.611

structural_room_mean_abs >= 0.411443:
  latest precision 0.560
```

Next implementation direction:

- add row-rule shadow scoring for every eligible rule;
- persist per-rule matured next-block performance;
- select current row rules using prior matured rule/family reliability;
- keep current block labels out of current block selection;
- do not add new model candidates until row-rule reliability is tested.

## Row-Rule Prequential Reliability

Implemented in:

```bash
python -m regression_feature_engineering.walkforward.rank_signal_row_rule_bank
```

New mode:

```text
--row-rule-selection-mode prequential_reliability_v1
```

New artifacts:

```text
row_rule_bank_shadow_rule_acceptance.parquet
row_rule_bank_rule_reliability.parquet
row_rule_bank_selection_audit.parquet
```

Selection contract:

```text
shadow-score all eligible rules on the next block
do not use current block labels for current selection
after maturity, update prior rule reliability
select future rules only from prior matured reliability
```

First validation:

```text
run:
  test_output/rpf_ranked_signal_row_rule_bank/20260624_235147_rank_signal_row_rule_bank/

input diagnostic:
  test_output/rpf_ranked_signal_row_diagnostic/20260624_233918_rank_signal_row_diagnostic/

key:
  feature_direction

warmup:
  no_signal
```

Result:

```text
latest raw candidate precision:
  0.395

latest static directional_lcb_v1:
  0.286

latest prequential reliability:
  0.423
```

Status:

```text
implemented_unvalidated for promotion
validated_plumbing for artifacts and no-current-label selection
validated_signal only weakly; needs more chronological blocks
```

Next experiment:

- collect at least 6-8 non-overlapping router blocks with
  candidate_prediction_scores;
- rerun row diagnostic across all blocks;
- rerun prequential reliability with `no_signal` warmup;
- inspect block-by-block precision lift and selected rule families.

## Eight-Block Reliability Result

Completed 8 non-overlapping 60-window router blocks:

```text
offsets:
  420, 360, 300, 240, 180, 120, 60, 0

row diagnostic:
  test_output/rpf_ranked_signal_row_diagnostic/20260627_125952_rank_signal_row_diagnostic/
```

Raw DOWN candidate:

```text
811 signals
354 TP / 457 FP
precision 0.436
```

Feature-direction row reliability:

```text
run:
  test_output/rpf_ranked_signal_row_rule_bank/20260627_131037_rank_signal_row_rule_bank/

filtered:
  69 signals
  40 TP / 29 FP
  precision 0.580

same selected-block raw precision:
  0.448

lift:
  1.30x
```

Family-direction row reliability:

```text
run:
  test_output/rpf_ranked_signal_row_rule_bank/20260627_131053_rank_signal_row_rule_bank/

filtered:
  116 signals
  66 TP / 50 FP
  precision 0.569

same selected-block raw precision:
  0.459

lift:
  1.24x
```

Planning decision:

- prefer `feature_direction` reliability for now;
- use `family_direction` as a coverage diagnostic, not the active gate;
- next implementation should integrate feature-direction row reliability as a
  shadow gate in the ranked-signal router and compare routed decisions with and
  without row filtering on the same blocks;
- keep this path DOWN-specific until UP is separately validated.

Implementation note:

```text
row_rule_bank now emits:
  row_rule_bank_fold_comparison.parquet
  row_rule_bank_overall_comparison.parquet

These compare filtered row-rule decisions against raw candidate decisions on
the same test blocks.

## Router Shadow Row-Rule Gate

The row-rule filter is now available inside `rank_signal_router` as a shadow
comparison mode:

```bash
--row-rule-gate-mode prequential_reliability_v1
```

Default scope:

```text
side: down
candidate: down_rocket_16_diag_v1
key: feature_direction
block size: 60 router windows
```

Contract:

- normal router outputs are unchanged;
- candidate prediction scores are written when the row gate is enabled;
- the row gate builds `block000`, `block001`, ... chronological source blocks
  from the selected router windows;
- eligible row rules are trained on prior blocks only;
- all eligible rules are shadow-scored on the next block;
- future rule selection uses prior matured shadow reliability only;
- current prediction labels do not select current rules.

New shadow artifacts:

```text
row_rule_gate_signal_rows.parquet
row_rule_gate_rules.parquet
row_rule_gate_rule_reliability.parquet
row_rule_gate_selection_audit.parquet
row_rule_gate_decisions.parquet
row_rule_gate_fold_comparison.parquet
row_rule_gate_overall_comparison.parquet
```

Next acceptance check:

- run the integrated router shadow gate over a long chronological slice;
- require `row_rule_gate_overall_comparison.parquet` to reproduce the
  diagnostic eight-block improvement direction;
- keep it shadow-only unless filtered precision/lift beats same-block raw
  candidate decisions with acceptable signal retention.

Completed integrated validation:

```text
run:
  test_output/rpf_ranked_signal_router/20260627_133550_rank_signal_router_btcusdt_8h_b/

row-rule gate:
  feature_direction
  down_rocket_16_diag_v1
  480 windows
  60-window blocks
```

Outcome:

```text
filtered:
  69 signals
  40 TP / 29 FP
  precision 0.580

same-block raw:
  487 signals
  218 TP / 269 FP
  precision 0.448

lift:
  1.295x
```

Planning decision:

- row-rule filtering is validated as an integrated shadow gate for DOWN;
- normal router-selected DOWN decisions remain weak at about `0.403`
  precision over this run;
- next implementation should add an active, audit-preserving output mode that
  can use the row-rule-filtered `down_rocket_16_diag_v1` decisions directly.

Active output mode has been added:

```bash
--row-rule-gate-output-mode active_down_candidate
```

It writes:

```text
row_rule_active_prediction_scores.parquet
row_rule_active_decisions.parquet
row_rule_active_window_metrics.parquet
row_rule_active_block_summary.parquet
row_rule_active_side_summary.json
```

This is still DOWN-only in v1. It uses the configured `down_rocket_16_diag_v1`
candidate rows and the mature row-rule gate. Raw router decisions and shadow
gate artifacts remain separate for audit.

First active-output validation:

```text
run:
  test_output/rpf_ranked_signal_router/20260627_150157_rank_signal_router_btcusdt_8h_b/

active row-rule DOWN:
  69 signals
  40 TP / 29 FP
  precision 0.580
  FDR 0.420

normal router DOWN:
  precision 0.403

same-block raw candidate:
  precision 0.448
```

Planning decision:

- active row-rule output is the current best DOWN path;
- next work should validate this active path over more chronological history
  and inspect whether the last two blocks still degrade;
- do not reopen broad candidate/model tuning until the active row-rule path is
  stress-tested.

Prepared longer readiness:

```text
run:
  test_output/rpf_clean_walkforward/20260627_162728_readiness_btcusdt_8h_b_target_reg_direction_extreme_up_sha_2d5c0524/

windows:
  1000

prediction batch range:
  4857..5856
```

Next stress test should use `outer-window-count=960` and
`row-rule-gate-block-size=60`, producing `16` equal chronological blocks.
```

960-window stress-test result:

```text
run:
  test_output/rpf_ranked_signal_router/20260627_162925_rank_signal_router_btcusdt_8h_b/

active row-rule DOWN:
  144 signals
  55 TP / 89 FP
  precision 0.382
  FDR 0.618
  precision lift vs full DOWN base rate 0.981x

same-block raw candidate:
  795 signals
  326 TP / 469 FP
  precision 0.410
```

Decision:

- the active row-rule path is not robust over 960 windows;
- the 480-window improvement was local, not promotable;
- the immediate failure is stale reliability from using all prior matured
  shadow history;
- the next active fix is recency-limited row-rule reliability.

Implemented next option:

```text
--row-rule-gate-reliability-lookback-folds N
```

Default `0` keeps all prior matured folds for backward compatibility. A
positive value uses only the last `N` matured row-rule folds when computing
prequential rule reliability. The first follow-up tests should compare
`N=3` and `N=5` on the same 960-window span.

Follow-up result:

```text
lookback=3:
  111 signals, 55 TP / 56 FP
  precision 0.495
  FDR 0.505
  lift vs full DOWN base 1.272x

lookback=5:
  116 signals, 49 TP / 67 FP
  precision 0.422
  FDR 0.578
  lift vs full DOWN base 1.085x
```

Next planned run:

```text
--row-rule-gate-reliability-lookback-folds 3
--row-rule-gate-reliability-min-precision-lcb 0.55
--row-rule-gate-reliability-max-fdr 0.35
```

Reason: post-hoc replay on the completed `lookback=3` artifacts indicates
that the stricter reliability gate would keep `38` signals with `24 TP / 14 FP`
and `0.632` precision, while removing the weakest early-block transfers.

Strict reliability run result:

```text
run:
  test_output/rpf_ranked_signal_router/20260627_202223_rank_signal_router_btcusdt_8h_b/

active DOWN row-rule output:
  38 signals
  24 TP / 14 FP
  precision 0.632
  FDR 0.368
  lift vs full DOWN base 1.622x
  lift vs raw gate-signal rows 1.556x
```

Planning implication:

- keep this configuration as the current DOWN specialist candidate;
- do not broaden the model stack until chronological transfer is tested;
- next runs should replay the same strict rule settings on older or offset
  960-window slices.

Offset transfer result:

```text
offset=0 latest:
  38 signals, 24 TP / 14 FP, precision 0.632

offset=480:
  15 signals, 6 TP / 9 FP, precision 0.400

offset=960:
  9 signals, 0 TP / 9 FP, precision 0.000
```

The strict rule gate is not promotable as-is. The failed older windows came
from a lower-direction liquidity pressure rule, while latest successful strict
signals used higher-direction rules. The router now supports:

```text
--row-rule-gate-allowed-directions higher_good
```

Next validation should replay offset `0`, `480`, and `960` with this direction
filter.

Direction-filter replay result:

```text
offset=0:
  38 signals, 24 TP / 14 FP, precision 0.632

offset=480:
  25 signals, 13 TP / 12 FP, precision 0.520

offset=960:
  19 signals, 7 TP / 12 FP, precision 0.368
```

Planning decision:

- `higher_good` is better than any-direction, but still not transferable;
- older offset `960` remains below the local DOWN base rate;
- do not promote this specialist gate;
- next step is a safe-context comparison of good active blocks versus the bad
  `4657..4716` block before adding another production rule.

Implemented safe-context diagnostic:

```bash
python -m regression_feature_engineering.walkforward.rank_signal_context_diagnostic
```

Latest diagnostic run:

```text
test_output/rpf_ranked_signal_context_diagnostic/20260628_044337_rank_signal_context_diagnostic/
```

The diagnostic writes:

```text
context_rows.parquet
specialist_block_outcomes.parquet
good_bad_context_comparison.parquet
context_report.md
```

Contract:

- `context_rows.parquet` contains only pre-maturity context;
- `specialist_block_outcomes.parquet` contains TP/FP/precision labels and must
  not be used for current-window routing;
- good/bad comparison is for designing the next conservative rule, not for
  silently promoting a threshold.

Current result:

```text
active blocks: 6
good blocks:   3
bad blocks:    2

bad repeated context:
  row_rpf_rejection_chop_mean_abs higher_good

good repeated context:
  liquidity_volume_pressure higher_good
  one rank_score higher_good block
```

Next planned implementation:

- add a context/family policy that can suppress `rejection_chop` rules unless
  their safe reliability context is materially stronger than the bad examples;
- replay the same offset `0`, `480`, and `960` blocks;
- promote only if the older offset no longer underperforms the local base rate.

Implemented family filter controls:

```text
--row-rule-gate-allowed-families
--row-rule-gate-blocked-families
```

First replay should use:

```text
--row-rule-gate-allowed-directions higher_good
--row-rule-gate-blocked-families rejection_chop
```

Acceptance for this diagnostic replay:

- offset `960` should improve versus `19 signals, 7 TP / 12 FP, precision
  0.368`;
- combined precision should stay above the higher-good baseline `0.537`;
- if signal count collapses to near zero, this is only a suppression rule, not
  a useful adaptive router.

Replay result:

```text
offset=0:
  38 signals, 24 TP / 14 FP, precision 0.632

offset=480:
  6 signals, 6 TP / 0 FP, precision 1.000

offset=960:
  0 signals

combined:
  44 signals, 30 TP / 14 FP
  precision 0.682
  FDR 0.318
  lift 1.784x
```

Interpretation:

- the filter did remove the repeated bad `rejection_chop` context;
- precision improved materially versus the higher-good baseline;
- coverage dropped from `82` signals to `44` signals;
- offset `960` changed from weak false-positive behavior into no-signal
  behavior.

Decision boundary:

- acceptable as a conservative false-positive suppressor;
- not promotable alone as a complete adaptive router;
- next ranked-signal work should focus on finding additional safe specialist
  contexts for old/quiet regimes, not loosening `rejection_chop` again.

## Regime / Change-Risk Diagnostic Layer

The active next diagnostic is:

```bash
python -m regression_feature_engineering.walkforward.rank_signal_regime_diagnostic
```

Reason:

```text
ranker candidates emit signals, but quality changes by chronological block.
The next missing component is not another threshold sweep; it is an explicit
prediction-safe regime and change-risk explanation layer.
```

The command consumes completed `rank_signal_router` runs and writes:

```text
regime_context.parquet
change_point_events.parquet
regime_signal_quality.parquet
hmm_state_metrics.parquet
regime_transfer_report.md
```

Contract:

- `regime_context.parquet` excludes current prediction outcomes;
- latent regimes are assigned using prior windows only;
- `hmmlearn.GaussianHMM` is used when available;
- otherwise the command uses a Gaussian-mixture Markov proxy;
- CUSUM/Page-Hinkley style alarms are diagnostic change-risk signals;
- router behavior remains unchanged until regime states prove useful
  out-of-sample.

Feature planes are intentionally separated:

```text
ranker prediction features:
  side-specific panel -> ElasticNet relevance selector -> optional sequence
  encoder -> CatBoostRanker

market-regime features:
  fixed stable RPF family aggregates from prior available batches

change-risk features:
  small router/market shift series for CUSUM/Page-Hinkley alarms
```

ElasticNet-selected ranker features are not reused as the HMM/change-point
feature set. They are target-specific and fold-specific, so using them as the
global regime representation would make regime states unstable and hard to
compare across windows.

Promotion requirement for a future `regime_aware_router_v1`:

```text
states or change alarms must separate precision/lift/FDR materially for both
UP and DOWN, not only explain one cherry-picked block.
```
