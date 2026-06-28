# RPF Current Experiment Summary

## Purpose

Provide one organized summary of the active RPF modeling workflow, the current
experiment families, and the strongest completed evidence so far.

## Current Status

Status: `research_active_not_promoted`.

`regression_path_features_v1` is engineering-valid, but no RPF model path is
production-promoted. The current work is focused on binary UP/DOWN extreme-path
classification and regime-conditioned decision quality.

The latest completed classifier checks showed that ElasticNet plus causal CNN
plus CatBoost works mechanically, but the probability-threshold classifier is
not stable enough to promote. DOWN improved false-positive control versus the
earlier tabular holdout but remains sparse. UP failed on the reserved holdout
because precision fell below the holdout base positive rate.

The active implementation path is now `rank_signal_router`: fixed
ranked-signal candidates are evaluated on validation batches only, the best
passing branch is selected per side and prediction fold, and the unseen
prediction batch is scored as outer evaluation. EMA gates, EMA-regime runs,
learned gates, and bank selection remain abandoned or deferred for the active
path and are kept only as historical diagnostics unless a new plan explicitly
reopens them.

The first completed ranked-signal no-sequence baseline is now available:

| Side | Run | Holdout precision | Holdout lift | Holdout signals | Holdout TP/FP |
|---|---|---:|---:|---:|---:|
| UP | `20260622_212507_rank_signal_btcusdt_8h_b_up` | `0.680` | `1.331` | `25` | `17/8` |
| DOWN | `20260622_213040_rank_signal_btcusdt_8h_b_down` | `0.432` | `2.185` | `74` | `32/42` |

Interpretation: the ranked-signal framing is useful enough to continue, but
not promoted. UP is sparse and higher precision on holdout. DOWN has stronger
lift and coverage but still too many false positives. The next controlled A/B
is `causal_rocket_v1` sequence memory against the same windows and tabular
panels.

The completed `causal_rocket_v1` A/B did not produce a global improvement:

| Side | Mode | Holdout precision | Holdout lift | Active windows | High-target capture | Holdout TP/FP |
|---|---|---:|---:|---:|---:|---:|
| UP | `none` | `0.680` | `1.331` | `0.500` | `0.571` | `17/8` |
| UP | `causal_rocket_v1` | `0.568` | `1.111` | `0.900` | `0.714` | `21/16` |
| DOWN | `none` | `0.432` | `2.185` | `0.900` | `0.750` | `32/42` |
| DOWN | `causal_rocket_v1` | `0.139` | `0.702` | `0.800` | `0.250` | `5/31` |

Decision: keep the no-sequence ranker as the current DOWN baseline. ROCKET is
rejected for DOWN in this configuration. For UP, ROCKET is only a diagnostic
hint that sequence memory can increase coverage, but the false-positive cost is
too high without stricter gating or decision-budget control.

Next run is a decision-control test, not a model-capacity expansion:

- UP uses `causal_rocket_v1` but freezes around the best UP ROCKET shape and
  tests stricter thresholds plus smaller signal budgets.
- DOWN uses `sequence_mode=none`, freezes around the best DOWN no-sequence
  shape, and tests stricter thresholds plus smaller signal budgets.

The goal is to determine whether the current useful evidence is recoverable by
decision control alone before adding more model complexity.

Decision-control result:

| Side | Mode | Holdout precision | Holdout lift | Signals | TP/FP | FPR | Cost/row |
|---|---|---:|---:|---:|---:|---:|---:|
| UP | `rocket_control` | `0.556` | `1.088` | `9` | `5/4` | `0.00341` | `0.5171` |
| DOWN | `none_control` | `0.444` | `2.246` | `9` | `4/5` | `0.00260` | `0.2067` |

Interpretation: stricter decision control is useful for DOWN, where it keeps
lift and high-target capture while reducing false-positive rate by roughly an
order of magnitude. It is not enough for UP, where precision/lift fall below
the no-sequence UP baseline.

Longer 50-step / 20-holdout ranked-signal confirmation:

| Side | Mode | Run | Holdout precision | Holdout lift | Signals | TP/FP | Active windows | High-target capture |
|---|---|---|---:|---:|---:|---:|---:|---:|
| UP | `none` | `20260622_224229_rank_signal_btcusdt_8h_b_up` | `0.571` | `1.036` | `21` | `12/9` | `0.350` | `0.267` |
| UP | `small_rocket` | `20260623_000231_rank_signal_btcusdt_8h_b_up` | `0.765` | `1.386` | `17` | `13/4` | `0.450` | `0.467` |
| DOWN | `none_control` | `20260623_002707_rank_signal_btcusdt_8h_b_down` | `0.459` | `2.274` | `37` | `17/20` | `0.650` | `0.571` |

Interpretation:

- the larger holdout weakens the old UP no-sequence result; precision barely
  beats the local base rate;
- smaller ROCKET is now the strongest UP ranked-signal candidate. It reduced
  false positives versus full ROCKET and improved holdout precision/lift;
- DOWN still works best without sequence features. It has strong lift, but the
  false discovery rate remains high enough that it is not promoted;
- active path after this check moved to adaptive router validation: choose
  among fixed side-specific candidates from validation evidence only, then
  evaluate the next prediction batch.

Adaptive router 240-window result:

```text
run: test_output/rpf_ranked_signal_router/20260623_020631_rank_signal_router_btcusdt_8h_b/
UP:   precision 0.400, base 0.396, lift 1.010, signals 185, TP/FP 74/111
DOWN: precision 0.508, base 0.375, lift 1.354, signals 244, TP/FP 124/120
```

Interpretation: router mechanics are valid and branch selection is adaptive,
but validation gates are not predictive enough yet. Validation quality had
near-zero correlation with next-batch precision.

Follow-up diagnostic router run:

```text
run: test_output/rpf_ranked_signal_router/20260623_111705_rank_signal_router_btcusdt_8h_b/
windows: 120
UP:   precision 0.439, base 0.430, lift 1.021, signals 98,  TP/FP 43/55
DOWN: precision 0.500, base 0.333, lift 1.500, signals 116, TP/FP 58/58
```

This run reproduced the loose-router behavior while adding validation row
scores, validation per-batch metrics, selected features, and sequence
diagnostics. It showed that strict gates are not the right fix and that several
branches should be pruned:

- remove: `up_rocket_16_v1`, `up_rocket_32_v1`,
  `down_rocket_32_diag_v1`;
- keep for the next controlled pass: `up_none_v1`, `up_rocket_64_v1`,
  `down_none_v1`, `down_rocket_16_diag_v1`;
- optional diagnostic only: `down_rocket_64_diag_v1`.

Current conclusion: the active issue is validation-to-prediction transfer and
batch-regime dominance. The next improvement should use a pruned candidate set
and a separate batch-regime diagnostic, not another broad router sweep.

Implemented next path:

```text
command:        python -m regression_feature_engineering.walkforward.rank_signal_router
selection mode: prequential_reliability_v1
candidate set:  pruned_reliability_v1
```

This mode keeps validation as a sanity check but selects candidates from prior
matured prediction-window reliability. Current prediction-batch metrics are
written as shadow diagnostics and are added to reliability memory only after the
current routing decision.

Latest correction after the older 120-window inspection:

- reliability now records global candidate lift and active-window row lift
  separately;
- `window_selection_lift` measures whether a branch tends to fire in higher-base
  batches;
- `selected_window_row_lift` measures whether the selected rows beat the base
  rate inside the active windows where the branch actually fires;
- `selected_window_row_lift_lcb` is now a reliability gate, defaulting to
  `1.05`;
- this is meant to reject the failure pattern where DOWN looked acceptable
  globally but only matched selected-window base rate, and where UP barely
  passed reliability before firing into near-zero-UP batches.

Row-lift gated older 120-window result:

```text
run: test_output/rpf_ranked_signal_router/20260623_133606_rank_signal_router_btcusdt_8h_b/
UP:   0 signals
DOWN: 9 signals, 3 TP / 6 FP, precision 0.333, lift 0.799
```

Interpretation: the row-lift gate correctly suppressed UP and reduced total
fires, but DOWN quality degraded. The remaining active DOWN batches were fully
polarized (`0%`, `100%`, `0%` DOWN positives), so the unresolved problem is
batch-state transfer: deciding whether the next batch contains the side at all.
Row ranking is now downstream of that missing side/batch-state gate.

Implemented batch-state gate:

```text
--batch-state-gate-mode logistic_prefix_v1
```

This adds a fold-local logistic gate before row decisions. It learns from train
batches whether a batch has enough side opportunity, uses validation batches
for sanity metrics, and uses only the first prediction-batch prefix rows as
live-safe evidence. If the gate fails, the side emits no row signals for that
batch. This is the active next test for the validation-to-prediction transfer
problem.

Older 120-window batch-state-gated result:

```text
run: test_output/rpf_ranked_signal_router/20260623_161709_rank_signal_router_btcusdt_8h_b/
final UP signals:   0
final DOWN signals: 0
```

Shadow candidate metrics show the important detail:

```text
down_none_v1:            23 signals, 13 TP / 10 FP, precision 0.565, lift 1.35
down_rocket_16_diag_v1: 100 signals, 49 TP / 51 FP, precision 0.490, lift 1.17
up_none_v1:              22 signals, 10 TP / 12 FP, precision 0.455, lift ~1.25
up_rocket_64_v1:         58 signals, 23 TP / 35 FP, precision 0.397, lift ~1.10
```

Interpretation: final router output was fully suppressed, but the shadow
candidate evidence is not empty. The strongest current branch is the sparse
`down_none_v1` specialist. The active router failed to use it because
reliability gates require too much rolling signal history for sparse signals.
The logistic prefix gate is mechanically leak-safe, but its pass/fail buckets
do not yet separate batch base rate well enough to be trusted as the main
selection signal.

Sparse-specialist reliability rerun:

```text
run: test_output/rpf_ranked_signal_router/20260623_165332_rank_signal_router_btcusdt_8h_b/
change: reliability-min-history-windows 10, min-signals 5, min-active-windows 2
final UP:   2 signals, 0 TP / 2 FP
final DOWN: 3 signals, 0 TP / 3 FP
```

Interpretation: relaxing history gates made candidates selectable, but selected
windows were still wrong. `down_none_v1` remains the strongest shadow branch,
but aggregate reliability does not tell us when to enter. The next work should
compare `down_none_v1` good active shadow windows against selected false-positive
windows and build a stronger current-window entry condition from
prediction-time-safe diagnostics.

Entry diagnostic for `down_none_v1`:

```text
artifact: test_output/rpf_ranked_signal_router/20260623_165332_rank_signal_router_btcusdt_8h_b/down_none_v1_entry_diagnostic.parquet
report:   test_output/rpf_ranked_signal_router/20260623_165332_rank_signal_router_btcusdt_8h_b/down_none_v1_entry_diagnostic_report.md
```

Active shadow windows showed a clear one-block pattern:

```text
validation candidate signals == 0
batch-state gate passed
```

On active `down_none_v1` windows in this block, that rule selected:

```text
batches: 5624, 5669, 5671, 5686
signals: 11
TP / FP: 11 / 0
precision: 1.0
```

Interpretation: quiet validation may be useful for sparse specialist routing,
because it implies a conservative threshold. This is diagnostic evidence only.
Next implementation should add an explicit experimental
`down_none_validation_quiet_v1` entry mode, then replay older and latest blocks.

Implemented experimental specialist entry mode:

```text
--specialist-entry-mode down_none_validation_quiet_v1
```

Contract:

```text
candidate must be down_none_v1
selection mode must be prequential_reliability_v1
validation candidate signal count must be 0
batch_state_gate_passed must be true
current prediction labels are not used
row decisions still use the normal causal signal budget
```

Validation:

```text
python -m pytest tests/test_rpf_rank_signal_router.py -q  # 15 passed
python -m py_compile regression_feature_engineering/walkforward/rank_signal_router.py
```

Older-block replay with the specialist entry enabled:

```text
run: test_output/rpf_ranked_signal_router/20260623_174040_rank_signal_router_btcusdt_8h_b/
UP:   0 signals
DOWN: 11 signals, 11 TP / 0 FP
DOWN precision: 1.0
DOWN lift:      2.397
active batches: 5624, 5669, 5671, 5686
```

This confirms the diagnostic rule can be executed by the router itself. It is
not yet generalization evidence because the rule was discovered on this same
older block. The next required run is the latest 120-window block with the same
configuration and `--window-end-offset-steps 0`.

Latest-block replay with the same specialist entry:

```text
run: test_output/rpf_ranked_signal_router/20260623_180640_rank_signal_router_btcusdt_8h_b/
UP:   0 selected-router signals
DOWN: 23 selected-router signals, 3 TP / 20 FP
DOWN precision: 0.1304
DOWN base rate: 0.3333
DOWN lift:      0.3913
active batches: 5777, 5793, 5808, 5813, 5834, 5846, 5847, 5849
```

This falsifies the specialist entry as a general rule. It reproduced the older
cluster but failed on the untouched latest block. It should remain diagnostic
only.

Shadow candidates on the latest block still showed some raw signal:

```text
up_none_v1:             12 signals,  9 TP /  3 FP, precision 0.75,   lift 1.7446
up_rocket_64_v1:        40 signals, 20 TP / 20 FP, precision 0.50,   lift 1.1631
down_none_v1:           50 signals, 15 TP / 35 FP, precision 0.30,   lift 0.90
down_rocket_16_diag_v1: 69 signals, 26 TP / 43 FP, precision 0.3768, lift 1.1304
```

Interpretation: the latest-block problem is not total absence of RPF signal.
The problem is transfer and branch selection. The next useful step is a
cross-block diagnostic comparing the older high-quality specialist windows
against latest false-positive windows using only prediction-time-safe regime
features and prior matured candidate outcomes.

Implemented transfer diagnostic:

```text
command: python -m regression_feature_engineering.walkforward.rank_signal_transfer_diagnostic
run:     test_output/rpf_ranked_signal_transfer_diagnostic/20260623_183857_rank_signal_transfer_diagnostic/
```

Artifacts:

```text
candidate_transfer_table.parquet  # includes post-hoc outcomes; diagnostic only
safe_context_features.parquet     # excludes current prediction labels/outcomes
active_window_comparison.parquet
transfer_report.md
```

First diagnostic summary:

```text
candidate_transfer_rows: 960
safe_context_rows:       960
active_window_rows:      157
good candidate windows:  47
bad candidate windows:   86
safe-context leaks:      0
```

The diagnostic confirms the next problem is not data plumbing. We now have a
clean table to study which prediction-safe validation/reliability/batch-state
context separates good candidate windows from bad ones. Do not implement or run
`context_meta_router_v1` until that separator analysis is done.

Implemented transfer separator analysis:

```text
command: python -m regression_feature_engineering.walkforward.rank_signal_transfer_separator
run:     test_output/rpf_ranked_signal_transfer_separator/20260623_185104_rank_signal_transfer_separator/
```

First separator result:

```text
active good/bad rows analyzed: 133
safe feature count:            69
separator rows:                403
```

Top candidate-specific separators:

```text
down_none_v1:           recent_candidate_selected_window_row_lift, AUC 0.9381
up_none_v1:             reliability_active_window_rate, AUC 0.95
up_rocket_64_v1:        score_mean, AUC 0.8033
down_rocket_16_diag_v1: reliability_precision_lift, AUC 0.7292
```

Interpretation: candidate-specific separators are stronger than the global
separator. A future meta-router should be candidate-conditioned. The separator
evidence is not enough to deploy yet; next step should be a dry-run meta-router
simulator on existing transfer rows.

Pruned active candidates:

```text
UP:   up_none_v1, up_rocket_64_v1
DOWN: down_none_v1, down_rocket_16_diag_v1
```

New reliability artifacts:

```text
candidate_prediction_window_metrics.parquet
candidate_reliability_state.parquet
candidate_selection_audit.parquet
reliability_block_summary.parquet
batch_regime_diagnostics.parquet
```

## Scope

Current benchmark:

```text
asset: BTCUSDT
root:  8h/B
```

Active binary targets:

```text
target_cls_extreme_up_ge_2x_down_hvol_v2
target_cls_extreme_down_ge_2x_up_hvol_v2
```

These are derived from `distance_horizon_vol_v2` hvol targets:

```text
UP positive:   up_extreme > 0 and up_extreme >= 2 * down_extreme
DOWN positive: down_extreme > 0 and down_extreme >= 2 * up_extreme
```

## Source Of Truth

- Current state: `current_feature_state.md`
- Binary pipeline contract: `rpf_binary_prediction_pipeline_contract.md`
- Ranked-signal plan: `rpf_ranked_signal_plan.md`
- Binary classifier: `regression_feature_engineering/walkforward/classify.py`
- Ranked-signal command: `regression_feature_engineering/walkforward/rank_signal.py`
- Adaptive router command:
  `regression_feature_engineering/walkforward/rank_signal_router.py`
- Binary experiment doc: `rpf_binary_classification_experiment.md`
- Regime-gate plan: `rpf_regime_gated_prediction_plan.md`
- Regime-gate tracker: `rpf_regime_gate_implementation_todo.md`
- EMA-regime batch selection: `rpf_ema_regime_batch_selection.md`
  (abandoned active path; historical reference only)
- Signal-bank contract: `rpf_signal_bank_batch_selection.md`
- Decision-bank contract: `rpf_separate_decision_banks.md`
- Clean RPF optimizer: `clean_rpf_walkforward_reset.md`

## What This Does Not Decide

This doc does not choose final model parameters, delete feature families, or
promote a trading rule. It records current evidence and keeps the workflow
organized.

## Workflow Map

The current RPF workflow has these layers:

1. **Feature layer**:
   `regression_path_features_v1` produces causal `rpf_*` features under the
   per-asset/per-root RPF feature root defined in `data_contract.md`.

2. **Readiness layer**:
   `python -m regression_feature_engineering.walkforward.optimize --stage readiness`
   exact-joins RPF features and hvol v2 labels by `timestamp,batch_id`, checks
   label-window safety, and writes frozen sparse windows.

3. **Binary classifier layer**:
   `python -m regression_feature_engineering.walkforward.classify_optuna`
   trains CatBoost classifiers for UP/DOWN `2x` targets and writes row-level
   `validation_scores.parquet` and `prediction_scores.parquet`.

4. **Optional sequence layer**:
   `--sequence-embedding-mode causal_cnn_v1` adds causal CNN embeddings before
   CatBoost. The current implementation trains CNN loss only on labeled
   eligible anchor rows and uses left-padded causal sequences ending at the
   anchor row.

5. **Regime diagnostics layer**:
   OHLCV and label diagnostics explain when classifiers work or fail. These are
   post-hoc diagnostics only, not live features.

6. **Deferred diagnostics layer**:
   EMA gates and EMA-regime train/validation/prediction selection are
   abandoned for active modeling and remain reproducible historical
   diagnostics only. Learned gates, signal banks, and decision banks are also
   not active model-development paths unless a new plan reopens them.

## Completed Evidence Summary

### Regression RPF Versus Old HTF Features

The corrected Stage-1 smoke for `target_reg_distance_up_extreme_hvol_v2`
favored old HTF/helper features:

| Feature source | Validation Spearman |
|---|---:|
| `htf_only` | `0.304247` |
| `regression_only` | `0.059750` |
| `htf_plus_regression` | `0.095225` |

Interpretation: the first RPF feature set is technically valid but did not beat
old HTF features for direct hvol regression in that smoke. This is why the
current work shifted to binary/regime-conditioned decisions.

### Chronological 50-Step Binary Classifiers

Selected completed 50-step runs using
`group_structural_room+liquidity_volume_pressure+interaction_confluence`:

| Target | Objective | Precision | Recall | FPR | Predicted positive rate | Decision cost/row | TP/FP/FN/TN |
|---|---|---:|---:|---:|---:|---:|---|
| UP | validation logloss | `0.504` | `0.085` | `0.075` | `0.080` | `-` | `484/476/5182/5858` |
| UP | validation decision cost | `0.315` | `0.100` | `0.195` | `0.150` | `0.939` | `567/1233/5099/5101` |
| DOWN | validation logloss | `0.388` | `0.190` | `0.136` | `0.153` | `-` | `713/1123/3038/7126` |
| DOWN | validation decision cost | `0.362` | `0.083` | `0.066` | `0.071` | `0.514` | `310/546/3441/7703` |

Interpretation:

- DOWN has the strongest completed global evidence, but it is not stable
  enough to promote.
- Cost-sensitive DOWN reduces false positives at the cost of low recall.
- UP is not globally useful yet; it is regime-dependent and often too
  conservative or inverted.

### Fifteen-Step Objective Sweep

The 15-step objective sweep is useful for understanding tradeoffs, not for
promotion.

Best false-positive-control example:

| Target | Scope | Objective | Precision | Recall | FPR | Predicted positive rate | Decision cost/row | TP/FP/FN/TN |
|---|---|---|---:|---:|---:|---:|---:|---|
| DOWN | `group_structural_room+liquidity_volume_pressure+interaction_confluence` | validation decision cost | `0.647` | `0.099` | `0.012` | `0.028` | `0.218` | `66/36/603/2895` |

Best clean UP example:

| Target | Scope | Objective | Precision | Recall | FPR | TP/FP/FN/TN |
|---|---|---|---:|---:|---:|---|
| UP | `only_structural_room` | validation logloss | `1.000` | `0.036` | `0.000` | `67/0/1814/1719` |

Interpretation:

- Fifteen-step results show that false-positive control is possible.
- They also show the main failure mode: precision can be good only when recall
  collapses.
- These results must be confirmed on longer windows before promotion.

### ElasticNet Selector Plus CatBoost Chronological Check

The 15-step lower-threshold DOWN diagnostic looked promising:

```text
run: test_output/rpf_clean_classification/20260616_184600_classification_cls_extreme_down_ge_2x_up_hvol_v2
trial: 0
status: ok
prediction precision:              0.502
prediction recall:                 0.360
prediction false-positive rate:    0.0815
prediction predicted-positive rate:0.133
prediction decision cost / row:    0.4508
```

The wider chronological check used the same focused feature group and selected
DOWN configuration with `--n-steps 50 --holdout-steps 20`, so the first `30`
windows were tuning evidence and the latest `20` windows were reserved for
holdout. It completed under:

```text
test_output/rpf_clean_classification/20260616_223950_classification_cls_extreme_down_ge_2x_up_hvol_v2
```

That run did **not** produce `holdout_summary.json`, because the single tuning
candidate was rejected before holdout:

```text
status:                         rejected:threshold_constraints
threshold pass windows:         17 / 30
prediction precision:           0.336
prediction recall:              0.087
prediction false-positive rate: 0.108
prediction decision cost / row: 0.6846
prediction AUC diagnostic:      0.377
prediction positive windows:    3 all-positive, 27 zero-positive
```

Interpretation:

- the 15-step DOWN result was not stable enough to trust;
- the main failure mode is window-level collapse, alternating between no
  positives and whole-batch positives;
- aggregate metrics are insufficient unless the objective penalizes per-window
  instability;
- this exact config should not be rerun unchanged or promoted to holdout.

### ElasticNet Plus CNN Plus CatBoost Holdout Checks

The 2026-06-18 CNN-cap checks used the same chronological structure for both
binary targets:

```text
n_steps:       50
holdout_steps: 20
feature group: group_structural_room+liquidity_volume_pressure+interaction_confluence
selector:      elasticnet_logistic_v1
sequence:      causal_cnn_v1, length 16, embedding dim 8
decision:      validation-selected threshold plus max_signals_per_batch
objective:     stable_prediction_quality
```

Reserved holdout results:

| Target | Precision | Lift | Recall | FPR | Cost / row | Signals | TP/FP/FN/TN | Status |
|---|---:|---:|---:|---:|---:|---:|---|---|
| UP | `0.514` | `0.93` | `0.126` | `0.146` | `0.810` | `648` | `333/315/2315/1837` | rejected; precision below base rate |
| DOWN | `0.375` | `1.86` | `0.163` | `0.0687` | `0.443` | `421` | `158/263/812/3567` | useful FP reduction, still sparse |

Interpretation:

- CNN plus per-batch signal caps helped DOWN by reducing false positives and
  decision cost versus the prior tabular DOWN holdout.
- The same shape did not transfer to UP. UP validation looked clean, but
  holdout precision fell below the holdout base positive rate.
- The immediate problem is not whether CNN can run; it can. The problem is
  stable window-level decision quality, especially for high-base-rate UP
  windows and isolated whole-batch firing.

The first UP target-aware stability rerun improved tuning-window precision and
FPR but correctly rejected itself before holdout:

```text
run: test_output/rpf_clean_classification_optuna/20260618_202138_classification_classification_cls_extreme_up_ge_2x_down_hvo
status: rejected:window_stability
reason: too_many_missed_high_target_windows
precision / lift: 0.670 / 1.43
recall / FPR:     0.172 / 0.0743
missed high-target windows: 5 / 8
```

After that run, validation threshold/cap selection under
`stable_prediction_quality` was changed to use the stable quality scorer
instead of pure validation decision cost, and the score now includes an
explicit recall term. The next UP run should test whether this reduces missed
high-target windows before widening again.

### Regime Diagnostics

The true 50-step regime-quality report shows that model quality depends heavily
on market state.

For UP:

- In actual up batches, precision was `1.000`, FPR `0.000`, recall `0.105`.
- In actual down batches, precision was `0.008`, FPR `0.149`.

For DOWN:

- In actual down batches, target positive rate was high (`0.779`), precision
  `0.675`, recall `0.124`, but FPR was still `0.210`.
- In flat batches, precision `0.390`, recall `0.344`, FPR `0.213`.
- In actual up batches, precision dropped to `0.205`.

Interpretation: global UP versus DOWN comparison is the wrong decision
surface. We need to learn when each side should be active.

## Gate And Bank Results

### Learned Regime Gates

DOWN learned gates can reach very low false positives but usually collapse
recall.

Example completed 50-step DOWN gate:

| Gate target | Scope | Precision | Recall | FPR | Predicted positive rate | TP/FP/FN/TN |
|---|---|---:|---:|---:|---:|---|
| `future_down_dominant` | `only_regime_calendar_state` | `1.000` | `0.016` | `0.000` | `0.005` | `60/0/3691/8249` |

UP learned gates mostly collapsed to zero prediction positives on held-out
windows.

Interpretation: learned gates prove false-positive suppression is possible, but
they are currently too sparse.

### Signal Bank

Pure `signal_bank` and interrupted `hybrid_recent_signal_bank` are rejected for
the current gate shape.

First pure signal-bank DOWN result:

```text
prediction TP/FP/FN/TN: 31/449/3720/7800
prediction false-positive rate: 0.054
prediction precision: 0.065
```

The paired classifier join suppressed all DOWN classifier positives. Do not
rerun this exact configuration unchanged.

### Separate Decision Bank

Separate target/gate bank audits passed maturity safety but found no usable
gate bank under the first strict settings:

```text
target_bank_usable_window_rate: 1.0
gate_bank_usable_window_rate:   0.0
```

Interpretation: target-event banks exist, but the classifier-trust bank is too
sparse with current thresholds.

### Deterministic EMA200 Post-Hoc Gate

Post-hoc EMA200 gating is not promoted.

Summary:

- UP above `15m` EMA reduced false positives but hurt precision and recall.
- UP above `1h` and `4h` changed little because existing UP positives already
  fired mostly in those regimes.
- UP above `1d` suppressed true positives.
- DOWN below `1d` retained some recall but worsened precision.
- DOWN below `15m`, `1h`, and `4h` removed useful true positives.

Interpretation: EMA200 is useful as a transparent diagnostic, not as a simple
post-hoc gate.

## EMA-Regime Experiment

Status: abandoned active path; historical reference only.

The historical EMA-regime classifier path is different from post-hoc gating.

It changes the training and validation banks:

```text
UP:   train/val from mature historical batches mostly above EMA200
DOWN: train/val from mature historical batches mostly below EMA200
```

It also filters prediction rows to rows where a live decision would be allowed.

Current implementation details:

- Each EMA timeframe gets its own effective prediction-window list.
- Prediction-window selection uses current 1m close versus latest closed EMA200,
  so it is live-safe.
- Inventory construction is RAM-safe: batch-range limited and chunked.
- `15m` EMA looked noisy and was interrupted.
- The broader EMA-regime sweep was stopped because it does not address the
  cleaner chronological classifier failure mode: per-window prediction
  collapse and threshold instability.

Do not run EMA-regime as the next step. Keep it only for reproducibility unless
a new plan explicitly reopens EMA work.

## Best Current Interpretation

Best completed evidence so far:

1. **DOWN target is more promising globally than UP**, but it still needs
   regime control.
2. **UP target should not be discarded**; it works only inside supportive
   regimes and fails badly in wrong regimes.
3. **False-positive control is achievable**, but current methods often collapse
   recall.
4. **Regime-conditioned evaluation is mandatory**; global metrics hide the
   useful parts of both targets.
5. **The next clean experiment is still chronological**, using the revised
   target-aware stability objective: penalize all-positive windows,
   zero-positive collapse, high per-window false-positive rate, low
   threshold-pass rate, missed high-target windows, and low-target whole-batch
   firing before widening or reattempting holdout.

## Current Do-Not-Repeat List

Do not spend more time on these unchanged configurations:

- direct RPF hvol regression as the primary path without new evidence;
- pure `signal_bank` gate training with the first DOWN settings;
- learned UP gates that collapse to zero positives;
- simple post-hoc EMA200 gate as a final filter;
- EMA-gate or EMA-regime paths as an active modeling step;
- the 20260616/17 DOWN ElasticNet/CatBoost chronological config unchanged,
  because it rejected itself on the 30 tuning windows before holdout.

## Next Evidence Needed

The next useful summary should come from a small UP-focused chronological
classifier run using the target-aware stability objective. It should report:

```text
target
feature scope
threshold grid
tuning windows
reserved holdout windows
prediction precision
prediction recall
prediction false-positive rate
prediction predicted-positive rate
prediction decision cost per row
threshold-pass window rate
zero-positive window count
all-positive window count
missed high-target window count/rate
low-target all-positive window count/rate
per-window max false-positive rate
per-window max decision cost
```

Only after a config improves the UP failure rates should it be widened to a
larger holdout. EMA paths remain abandoned for the active path.

## Ranked-Signal Transfer Meta-Router Simulator

Status as of 2026-06-23:

```text
command: python -m regression_feature_engineering.walkforward.rank_signal_meta_router_simulator
run:     test_output/rpf_ranked_signal_meta_router_simulator/20260623_205856_rank_signal_meta_router_simulator/
input:   test_output/rpf_ranked_signal_transfer_diagnostic/20260623_183857_rank_signal_transfer_diagnostic/
```

Purpose:

- test whether safe-context separators learned from the older block transfer
  into the latest block;
- keep the live router unchanged while evaluating candidate-specific rules;
- decide whether `context_meta_router_v1` has enough evidence to implement.

Result:

| Source | Side | Signals | TP | FP | Precision | Lift |
|---|---|---:|---:|---:|---:|---:|
| older | DOWN | 8 | 8 | 0 | 1.000 | 2.397 |
| older | UP | 9 | 9 | 0 | 1.000 | 2.761 |
| latest | DOWN | 38 | 9 | 29 | 0.237 | 0.711 |
| latest | UP | 3 | 3 | 0 | 1.000 | 2.326 |

Conclusion:

- UP context filters transfer but are too sparse to call promoted.
- `down_rocket_16_diag_v1` looks clean but sparse in candidate acceptance.
- `down_none_v1` remains the latest-block failure point.
- The next experiment should not widen the candidate set. It should test a
  conservative allow-list/reject rule for `down_none_v1` on the same windows.

Conservative allow-list replay:

```text
command: python -m regression_feature_engineering.walkforward.rank_signal_meta_router_simulator
run:     test_output/rpf_ranked_signal_meta_router_simulator/20260623_210014_rank_signal_meta_router_simulator/
allowed: up_none_v1, up_rocket_64_v1, down_rocket_16_diag_v1
excluded: down_none_v1
```

Result:

| Source | Side | Signals | TP | FP | Precision | Lift |
|---|---|---:|---:|---:|---:|---:|
| older | DOWN | 3 | 3 | 0 | 1.000 | 2.397 |
| older | UP | 9 | 9 | 0 | 1.000 | 2.761 |
| latest | DOWN | 2 | 2 | 0 | 1.000 | 3.000 |
| latest | UP | 3 | 3 | 0 | 1.000 | 2.326 |

This is the cleanest transfer diagnostic so far, but it is very sparse and is
still artifact-only. The next live experiment should reproduce this candidate
restriction in `rank_signal_router` or replay it on another chronological
block before implementation into `context_meta_router_v1`.

Implementation status:

- `rank_signal_router` now accepts `--candidate-name-allowlist`.
- Use `up_none_v1,up_rocket_64_v1,down_rocket_16_diag_v1` to reproduce the
  conservative allow-list in a real live-router run.
- Default router behavior is unchanged when the allow-list is omitted.

Live allow-list run result:

```text
run: test_output/rpf_ranked_signal_router/20260623_210606_rank_signal_router_btcusdt_8h_b/
final UP decisions: 0
final DOWN decisions: 0
```

This means the allow-list itself is not the active fix. The default
`prequential_reliability_v1` gates are too strict for sparse candidates. The
shadow candidates still produced signals, but simple validation-only selection
was not clean enough:

```text
DOWN validation-only shadow: 58 signals, 27 TP, 31 FP, precision 0.466
UP validation-only shadow:   84 signals, 39 TP, 45 FP, precision 0.464
```

Fresh diagnostic using the live allow-list artifacts:

```text
transfer diagnostic: test_output/rpf_ranked_signal_transfer_diagnostic/20260623_212043_rank_signal_transfer_diagnostic/
meta-rule simulator: test_output/rpf_ranked_signal_meta_router_simulator/20260623_212049_rank_signal_meta_router_simulator/
```

Older-trained context rules replayed on the live allow-list artifacts produced:

```text
latest DOWN: 9 signals, 6 TP, 3 FP, precision 0.667, lift 2.000
latest UP:   17 signals, 14 TP, 3 FP, precision 0.824, lift 1.916
```

Current next step: implement a live context-rule/meta-router selection mode.
Do not rerun the same allow-list with plain prequential reliability unchanged.

Live context-rule implementation:

```text
selection mode: context_rule_v1
context rule source: meta-router simulator artifact
```

Smoke run:

```text
run: test_output/rpf_ranked_signal_router/20260623_212951_rank_signal_router_btcusdt_8h_b/
outer windows: 5
UP: 2 signals, 2 TP, 0 FP
DOWN: 0 signals
```

This confirms the live router can apply candidate-specific context rules and
emit decisions. Next evidence should come from the latest 120-window replay
using the same context-rule artifact.

Latest 120-window context-rule replay:

```text
run: test_output/rpf_ranked_signal_router/20260623_213215_rank_signal_router_btcusdt_8h_b/
selection mode: context_rule_v1
outer windows: 120
```

Result:

| Side | Signals | TP | FP | Precision | Lift | Active Window Rate |
|---|---:|---:|---:|---:|---:|---:|
| UP | 17 | 14 | 3 | 0.824 | 1.916 | 0.083 |
| DOWN | 9 | 6 | 3 | 0.667 | 2.000 | 0.025 |

Interpretation:

- `context_rule_v1` is the first live-router selection path that transfers
  useful sparse precision on both sides in the latest block.
- This is not production promotion yet. The next check must replay the same
  frozen context rules on shifted/older windows to test chronological stability.

Shifted older-block stability replay:

```text
run: test_output/rpf_ranked_signal_router/20260623_214859_rank_signal_router_btcusdt_8h_b/
selection mode: context_rule_v1
window_end_offset_steps: 240
prediction batches: 5497..5616
outer windows: 120
```

| Side | Signals | TP | FP | Precision | Lift | FDR |
|---|---:|---:|---:|---:|---:|---:|
| UP | 24 | 9 | 15 | 0.375 | 1.199 | 0.625 |
| DOWN | 0 | 0 | 0 | - | - | - |

Interpretation: the same context rules that worked on the latest block did not
hold on the offset-240 block. UP became too noisy and DOWN missed a high-base
older DOWN regime. The next useful work is multi-block rule-bank validation,
not more tuning of the latest-block frozen rules.

Implemented rule-bank transfer diagnostic:

```text
command: python -m regression_feature_engineering.walkforward.rank_signal_rule_bank
```

The first check used three chronological blocks:

```text
offset240 -> middle -> latest
```

All-prior rule training failed the latest transition:

```text
run: test_output/rpf_ranked_signal_rule_bank/20260623_221017_rank_signal_rule_bank/
latest UP:   113 signals, 56 TP, 57 FP, precision 0.496, lift 1.153
latest DOWN: 0 signals
```

Rolling-one-block rule training performed better:

```text
run: test_output/rpf_ranked_signal_rule_bank/20260623_221037_rank_signal_rule_bank/
middle -> latest UP:   17 signals, 14 TP, 3 FP, precision 0.824, lift 1.916
middle -> latest DOWN: 9 signals, 6 TP, 3 FP, precision 0.667, lift 2.000
```

Current interpretation: context rules should adapt from recent matured blocks,
not all accumulated history. This is still under-tested because only two
forward transitions exist. The next run should add an older offset-360 block
and rerun the rolling rule-bank across four blocks.

Four-block rolling rule-bank check:

```text
offset360 router: test_output/rpf_ranked_signal_router/20260623_221301_rank_signal_router_btcusdt_8h_b/
rule bank:        test_output/rpf_ranked_signal_rule_bank/20260623_221856_rank_signal_rule_bank/
```

Important caveat: the offset360 router block contains only `40` windows
(`5457..5496`), not `120`, because the active readiness run exposes only `400`
frozen windows. A true full offset360 block needs a longer readiness run.

Rolling-one-block forward result:

| Train | Test | Side | Signals | TP | FP | Precision | Lift | FDR |
|---|---|---|---:|---:|---:|---:|---:|---:|
| offset360 | offset240 | DOWN | 12 | 12 | 0 | 1.000 | 2.193 | 0.000 |
| offset360 | offset240 | UP | 8 | 4 | 4 | 0.500 | 1.599 | 0.500 |
| offset240 | middle | DOWN | 6 | 3 | 3 | 0.500 | 1.198 | 0.500 |
| offset240 | middle | UP | 10 | 8 | 2 | 0.800 | 2.209 | 0.200 |
| middle | latest | DOWN | 9 | 6 | 3 | 0.667 | 2.000 | 0.333 |
| middle | latest | UP | 17 | 14 | 3 | 0.824 | 1.916 | 0.176 |

Overall:

```text
DOWN: 27 signals, 21 TP, 6 FP, precision 0.778, lift 1.934
UP:   35 signals, 26 TP, 9 FP, precision 0.743, lift 2.017
```

Interpretation: recent-block rule adaptation is now the strongest evidence in
the RPF ranked-signal branch. It is still not promotion evidence because the
oldest block is short. The next validation should rebuild longer readiness and
repeat full-size rolling blocks.

Full-size four-block rolling rule-bank validation:

```text
readiness: 520 frozen windows
rule bank: test_output/rpf_ranked_signal_rule_bank/20260623_232201_rank_signal_rule_bank/
```

All four blocks are now full `120` prediction windows:

```text
offset360: 5377..5496
offset240: 5497..5616
middle:    5617..5736
latest:    5737..5856
```

Forward fold result:

| Train | Test | Side | Signals | TP | FP | Precision | Lift | FDR |
|---|---|---|---:|---:|---:|---:|---:|---:|
| offset360 | offset240 | DOWN | 9 | 4 | 5 | 0.444 | 0.974 | 0.556 |
| offset360 | offset240 | UP | 23 | 10 | 13 | 0.435 | 1.391 | 0.565 |
| offset240 | middle | DOWN | 31 | 22 | 9 | 0.710 | 1.701 | 0.290 |
| offset240 | middle | UP | 49 | 20 | 29 | 0.408 | 1.127 | 0.592 |
| middle | latest | DOWN | 53 | 23 | 30 | 0.434 | 1.302 | 0.566 |
| middle | latest | UP | 58 | 41 | 17 | 0.707 | 1.644 | 0.293 |

Overall:

```text
DOWN precision 0.527, lift 1.310, FDR 0.473, signals 93
UP precision 0.546, lift 1.483, FDR 0.454, signals 130
```

Interpretation: the full-size rule bank confirms some predictive lift, but the
current threshold objective is too permissive. It accepts rules with too many
false positives. The next implementation should add explicit train-rule
eligibility gates before a context rule can be replayed.

Conservative rule eligibility implementation:

```text
command: python -m regression_feature_engineering.walkforward.rank_signal_rule_bank
new artifact: rule_bank_rule_candidates.parquet
```

Useful calibrated run:

```text
run: test_output/rpf_ranked_signal_rule_bank/20260623_233251_rank_signal_rule_bank/
rule-min-train-signals: 3
rule-min-train-precision: 0.65
rule-min-train-precision-lcb: 0.35
rule-min-train-lift: 1.40
rule-max-train-fdr: 0.35
rule-max-train-active-rate: 0.50
```

| Side | Signals | TP | FP | Precision | Lift | FDR |
|---|---:|---:|---:|---:|---:|---:|
| DOWN | 84 | 45 | 39 | 0.536 | 1.332 | 0.464 |
| UP | 81 | 51 | 30 | 0.630 | 1.710 | 0.370 |

Decision: conservative gates improve UP substantially but do not solve DOWN.
The next step should split rule eligibility by side: keep the UP sparse
conservative gate as a candidate, and require stricter/different DOWN context
separation before replaying DOWN rules.

Side-specific rule eligibility is now implemented and validated.

Asymmetric sparse-UP / strict-DOWN replay:

```text
run: test_output/rpf_ranked_signal_rule_bank/20260623_234159_rank_signal_rule_bank/
UP gate:   min signals 3,  precision 0.65, precision LCB 0.35, lift 1.40, max FDR 0.35
DOWN gate: min signals 10, precision 0.65, precision LCB 0.50, lift 1.40, max FDR 0.35
```

| Side | Signals | TP | FP | Precision | Lift | FDR |
|---|---:|---:|---:|---:|---:|---:|
| DOWN | 31 | 22 | 9 | 0.710 | 1.764 | 0.290 |
| UP | 81 | 51 | 30 | 0.630 | 1.710 | 0.370 |

Decision: this is the current clean rule-bank diagnostic. UP remains usable as
a sparse conservative replay. DOWN is cleaner only when stricter history gates
are applied, but then it becomes sparse and misses some regimes. The next step
is not broader model tuning; it is better DOWN context separation or a
side-specific objective before any live router wiring.

DOWN-focused transfer separator:

```text
run: test_output/rpf_ranked_signal_transfer_separator/20260624_161310_rank_signal_transfer_separator/
candidate: down_rocket_16_diag_v1
active good/bad rows: 81
tested safe features: 57
top feature: reliability_precision
top best AUC: 0.703
```

Interpretation: the separator found only moderate safe-context separation, and
the top direction is not stable enough to promote directly. Keep the strict
DOWN rule gate as the defensive diagnostic. To recover DOWN coverage, the next
work needs better DOWN-specific prediction-time context features or a different
DOWN objective, not another loose replay of the same rules.

Enriched safe-context diagnostic:

```text
code path: rank_signal_transfer_diagnostic
new context: validation score-shape, validation-batch stability,
             train-only ElasticNet selector profile

two-block enriched separator:
  test_output/rpf_ranked_signal_transfer_separator/20260624_162157_rank_signal_transfer_separator/

four-block enriched separator:
  test_output/rpf_ranked_signal_transfer_separator/20260624_162115_rank_signal_transfer_separator/
```

Result:

```text
two-block: top feature still reliability_precision, best AUC 0.703
four-block: top feature threshold / validation_score_q95, best AUC about 0.599
```

Decision: aggregate router metadata is not enough to solve DOWN transfer.
The next useful work should add causal market/RPF regime context or row-level
context conditioning. More replays of the same aggregate validation/reliability
features are unlikely to recover DOWN coverage safely.

Prior-RPF context diagnostic:

```text
diagnostic:
  test_output/rpf_ranked_signal_transfer_diagnostic/20260624_163148_rank_signal_transfer_diagnostic/
DOWN separator:
  test_output/rpf_ranked_signal_transfer_separator/20260624_163220_rank_signal_transfer_separator/
UP separator:
  test_output/rpf_ranked_signal_transfer_separator/20260624_163242_rank_signal_transfer_separator/
```

Implementation:

```text
rank_signal_transfer_diagnostic adds prior RPF family summaries when
--base-run is provided.

For each prediction batch:
  allowed context batches = batch_id < router_pred_batch_id

The current prediction batch is not summarized.
```

Result:

```text
safe context rows: 1440
safe context columns: 301
prior RPF context columns: 168

DOWN top separator:
  prior_rpf_l20_regime_calendar_state_std_mean
  best AUC 0.605

UP top separator:
  score_mean
  best AUC 0.730 overall
  up_rocket_64_v1 score_mean best AUC 0.770
```

Decision: prior RPF family context confirms the current asymmetry. UP has
usable sparse separator structure; DOWN still lacks a strong prediction-safe
separator. The next step should be controlled rule-bank use of these separator
fields or a row-level DOWN objective. Do not expand candidate branches until
DOWN has a stronger context explanation.

Row-level DOWN TP/FP diagnostic:

```text
command: python -m regression_feature_engineering.walkforward.rank_signal_row_diagnostic
run: test_output/rpf_ranked_signal_row_diagnostic/20260624_185848_rank_signal_row_diagnostic/
side: down
candidate: down_rocket_16_diag_v1
source: candidate_prediction_scores
```

Input runs:

```text
test_output/rpf_ranked_signal_router/20260623_174040_rank_signal_router_btcusdt_8h_b
test_output/rpf_ranked_signal_router/20260623_180640_rank_signal_router_btcusdt_8h_b
```

Result:

```text
signal rows: 169
TP rows: 75
FP rows: 94

middle precision: 49/100 = 0.490
latest precision: 26/69 = 0.377
```

Top row-level separator:

```text
rank_score, best AUC 0.688, higher_good
```

Best RPF row-family separators:

```text
structural_room_mean_abs, best AUC 0.646, higher_good
sequence_embedding_layer_max_abs, best AUC 0.627, lower_good
cross_asset_context_positive_rate, best AUC 0.620, higher_good
```

One-step middle-to-latest rule replay:

```text
cross_asset_context_mean_abs >= ~0.299:
  latest 9 signals, 6 TP, 3 FP, precision 0.667

interaction_confluence_mean >= ~0.135:
  latest 11 signals, 7 TP, 4 FP, precision 0.636
```

Decision: row-level context can clean DOWN signals, but only sparsely. This
supports a row-filter rule-bank as the next controlled experiment. It does not
support broadening DOWN candidates or loosening strict DOWN gates.

Corrected row-filter rule-bank replay:

```text
command: python -m regression_feature_engineering.walkforward.rank_signal_row_rule_bank
run: test_output/rpf_ranked_signal_row_rule_bank/20260624_192814_rank_signal_row_rule_bank/
source: test_output/rpf_ranked_signal_row_diagnostic/20260624_185848_rank_signal_row_diagnostic/
```

Design:

```text
train row filters on prior matured signal rows
apply eligibility gates
replay only the top eligible rule per side/candidate by default
```

The top-rule cap matters. Without it, many eligible filters unioned together
and accepted all latest DOWN signals. The corrected command defaults to:

```text
--max-rules-per-candidate 1
```

Corrected result:

```text
train block: middle
test block: latest
side: down
candidate: down_rocket_16_diag_v1

rule:
  row_rpf_cross_asset_context_mean >= 0.3012844470752333

train:
  10 accepted, 10 TP, 0 FP, precision 1.000, lift 2.041

latest replay:
  9 signals, 6 TP, 3 FP, precision 0.667, FDR 0.333
```

Decision: this is the first DOWN-specific filter that transfers cleanly enough
to justify a broader validation. It is sparse and not promotable yet. Next step
should be rebuilding row diagnostics across more chronological blocks and
replaying the row-filter rule bank across multiple transitions.

Broader row-rule validation:

```text
diagnostic:
  test_output/rpf_ranked_signal_row_diagnostic/20260624_193124_rank_signal_row_diagnostic/

blocks:
  offset240 -> middle -> latest

raw down_rocket_16_diag_v1 precision:
  offset240: 95/200 = 0.475
  middle:    49/100 = 0.490
  latest:    26/69  = 0.377
```

The old threshold-only rule ranking did not transfer:

```text
run:
  test_output/rpf_ranked_signal_row_rule_bank/20260624_193146_rank_signal_row_rule_bank/

overall:
  25 signals, 9 TP, 16 FP, precision 0.360
```

Reason:

```text
The selected offset240->middle rule had high train lift but weak feature-level
direction support. It was a narrow threshold coincidence, not a stable row
context separator.
```

Implemented fix:

```text
rank_signal_row_rule_bank now supports:
  --rule-selection-score directional_lcb_v1

The score is still train-only. It combines:
  precision lower bound
  accepted-row support
  false-discovery penalty
  feature-level AUC direction agreement
```

Result:

```text
run:
  test_output/rpf_ranked_signal_row_rule_bank/20260624_193705_rank_signal_row_rule_bank/

offset240 -> middle:
  row_rpf_rejection_chop_max_abs <= 0.9583333333333334
  21 signals, 13 TP, 8 FP, precision 0.619

middle -> latest:
  row_rpf_cross_asset_context_mean >= 0.3012844470752333
  9 signals, 6 TP, 3 FP, precision 0.667

overall:
  30 signals, 19 TP, 11 FP, precision 0.633
```

Decision:

```text
directional_lcb_v1 is the current best row-filter selection method.
It is not promotable yet, but it is the first DOWN cleanup method that improves
both tested chronological transitions.
```

Four-block validation changed the conclusion:

```text
router blocks with candidate_prediction_scores:
  offset360: 20260624_215759_rank_signal_router_btcusdt_8h_b
  offset240: 20260624_221618_rank_signal_router_btcusdt_8h_b
  middle:    20260624_223415_rank_signal_router_btcusdt_8h_b
  latest:    20260624_225218_rank_signal_router_btcusdt_8h_b

row diagnostic:
  test_output/rpf_ranked_signal_row_diagnostic/20260624_233918_rank_signal_row_diagnostic/

row-rule replay:
  test_output/rpf_ranked_signal_row_rule_bank/20260624_233936_rank_signal_row_rule_bank/
```

Raw candidate quality:

```text
offset360: precision 0.381
offset240: precision 0.475
middle:    precision 0.495
latest:    precision 0.395
```

`directional_lcb_v1` replay:

```text
offset360 -> offset240:
  39 signals, 20 TP, 19 FP, precision 0.513

offset240 -> middle:
  53 signals, 35 TP, 18 FP, precision 0.660

middle -> latest:
  49 signals, 14 TP, 35 FP, precision 0.286

overall:
  141 signals, 69 TP, 72 FP, precision 0.489
```

Important diagnostic:

```text
The middle->latest failure is selector failure, not absence of all possible
row filters. All-eligible diagnostic replay found better latest filters:

row_rpf_unsupervised_factor_layer_positive_rate >= 1.0:
  18 signals, 11 TP, 7 FP, precision 0.611

row_rpf_structural_room_mean_abs >= 0.411443:
  25 signals, 14 TP, 11 FP, precision 0.560
```

Updated decision:

```text
Do not promote directional_lcb_v1 alone.
Next step should be row-rule prequential reliability:
  train eligible row rules on current block,
  shadow-score all eligible rules on next block,
  mature their performance,
  then prefer rule families with proven out-of-sample reliability.
```

Implemented row-rule prequential reliability:

```text
command:
  python -m regression_feature_engineering.walkforward.rank_signal_row_rule_bank

mode:
  --row-rule-selection-mode prequential_reliability_v1

artifacts:
  row_rule_bank_shadow_rule_acceptance.parquet
  row_rule_bank_rule_reliability.parquet
  row_rule_bank_selection_audit.parquet
```

First run:

```text
test_output/rpf_ranked_signal_row_rule_bank/20260624_235147_rank_signal_row_rule_bank/
```

Result:

```text
warmup policy:
  no_signal

selected mature fold:
  middle -> latest

selected rule:
  row_rpf_rejection_chop_max_abs <= 0.994176

latest replay:
  52 signals, 22 TP, 30 FP, precision 0.423
```

Comparison:

```text
raw latest down_rocket_16_diag_v1:
  precision 0.395

static directional_lcb_v1 latest:
  precision 0.286

prequential reliability latest:
  precision 0.423
```

Decision:

```text
Prequential reliability is implemented and safer than static rule selection,
but the first four-block evidence is only a small improvement. It needs more
chronological blocks before router integration.
```

Eight-block validation:

```text
row diagnostic:
  test_output/rpf_ranked_signal_row_diagnostic/20260627_125952_rank_signal_row_diagnostic/

feature-direction reliability:
  test_output/rpf_ranked_signal_row_rule_bank/20260627_130019_rank_signal_row_rule_bank/

family-direction reliability:
  test_output/rpf_ranked_signal_row_rule_bank/20260627_130034_rank_signal_row_rule_bank/
```

Raw DOWN candidate:

```text
down_rocket_16_diag_v1:
  811 signals, 354 TP, 457 FP
  precision 0.436
```

Feature-direction reliability:

```text
comparison artifact:
  test_output/rpf_ranked_signal_row_rule_bank/20260627_131037_rank_signal_row_rule_bank/

selected mature folds: 5
filtered: 69 signals, 40 TP, 29 FP
precision: 0.580
same-block raw precision: 0.448
precision lift: 1.30x
```

Family-direction reliability:

```text
comparison artifact:
  test_output/rpf_ranked_signal_row_rule_bank/20260627_131053_rank_signal_row_rule_bank/

selected mature folds: 6
filtered: 116 signals, 66 TP, 50 FP
precision: 0.569
same-block raw precision: 0.459
precision lift: 1.24x
```

Decision:

```text
Feature-direction reliability is the current preferred row-filter mode:
cleaner than family-direction, every selected block beat raw precision, but
coverage is sparse.

This is now validated_signal for diagnostic row filtering, not yet promoted
router behavior.
```

Implementation note:

```text
row_rule_bank now writes row_rule_bank_fold_comparison.parquet and
row_rule_bank_overall_comparison.parquet, so shadow gate lift/retention are
available directly from each run artifact.
```

Router integration update:

```text
implemented:
  rank_signal_router --row-rule-gate-mode prequential_reliability_v1

default shadow gate:
  side: down
  candidate: down_rocket_16_diag_v1
  reliability key: feature_direction
```

The implementation keeps normal router outputs unchanged and writes the
row-filtered comparison separately:

```text
row_rule_gate_signal_rows.parquet
row_rule_gate_rule_candidates.parquet
row_rule_gate_rules.parquet
row_rule_gate_rule_acceptance.parquet
row_rule_gate_shadow_rule_acceptance.parquet
row_rule_gate_rule_reliability.parquet
row_rule_gate_selection_audit.parquet
row_rule_gate_decisions.parquet
row_rule_gate_fold_summary.parquet
row_rule_gate_overall_summary.parquet
row_rule_gate_fold_comparison.parquet
row_rule_gate_overall_comparison.parquet
```

This is still a shadow gate. It is designed to answer whether the previously
validated DOWN row-rule filter survives inside the real router output flow.
Promotion requires the integrated router run to reproduce the diagnostic lift
without using current prediction labels for current decisions.

Integrated router shadow-gate validation:

```text
run:
  test_output/rpf_ranked_signal_router/20260627_133550_rank_signal_router_btcusdt_8h_b/

outer windows:
  480

shadow candidate:
  down_rocket_16_diag_v1
```

Result:

```text
raw down_rocket_16_diag_v1:
  811 signals, 354 TP / 457 FP, precision 0.436

row-rule filtered:
  69 signals, 40 TP / 29 FP, precision 0.580

same selected-block raw baseline:
  487 signals, 218 TP / 269 FP, precision 0.448

precision lift vs raw:
  1.295x
```

Decision:

```text
The row-rule gate is now validated as an integrated shadow filter for DOWN.
The router selection layer remains weak, so the next useful implementation is
an explicit active row-rule decision mode for the DOWN rocket branch, not more
router candidate selection tuning.
```

Active row-rule output is implemented:

```text
option:
  --row-rule-gate-output-mode active_down_candidate

active artifacts:
  row_rule_active_prediction_scores.parquet
  row_rule_active_decisions.parquet
  row_rule_active_window_metrics.parquet
  row_rule_active_block_summary.parquet
  row_rule_active_side_summary.json
```

The active artifact keeps the full candidate prediction row universe and flips
`decision=1` only for rows accepted by the mature row-rule gate. This makes
precision, false-positive rate, recall, block stability, and signal retention
auditable without overwriting raw router decisions.

Active row-rule output validation:

```text
run:
  test_output/rpf_ranked_signal_router/20260627_150157_rank_signal_router_btcusdt_8h_b/

DOWN active row-rule:
  69 signals
  40 TP / 29 FP
  precision 0.580
  FDR 0.420
  precision lift vs full DOWN base rate 1.445x

normal selected router DOWN:
  62 signals
  25 TP / 37 FP
  precision 0.403

same-block raw candidate:
  precision 0.448
  row-rule lift vs raw 1.295x
```

Decision:

```text
The active row-rule artifact was the strongest current DOWN evidence on the
480-window slice, but it is not promoted. The required next step was longer
chronological validation.
```

960-window active row-rule stress test:

```text
run:
  test_output/rpf_ranked_signal_router/20260627_162925_rank_signal_router_btcusdt_8h_b/

setup:
  outer windows: 960
  row-rule output: active_down_candidate
  candidate allowlist: up_none_v1, down_rocket_16_diag_v1

normal router DOWN:
  24 signals, 6 TP / 18 FP
  precision 0.250
  FDR 0.750

active row-rule DOWN:
  144 signals, 55 TP / 89 FP
  precision 0.382
  FDR 0.618
  precision lift vs full DOWN base rate 0.981x

same-block raw candidate:
  795 signals, 326 TP / 469 FP
  precision 0.410
```

Conclusion:

```text
The 480-window win was real but local. Over 960 windows the active row-rule
gate underperformed the same-block raw candidate and did not beat the full DOWN
base rate. The current failure is stale row-rule reliability: old matured
history can keep a rule eligible after recent blocks have degraded. The next
fix is recency-limited row-rule reliability, then rerun the 960-window stress
test with short lookbacks.
```

Recency-limited reliability check:

```text
lookback=3:
  run: test_output/rpf_ranked_signal_router/20260627_174917_rank_signal_router_btcusdt_8h_b/
  111 signals, 55 TP / 56 FP
  precision 0.495
  FDR 0.505
  lift vs full DOWN base 1.272x

lookback=5:
  run: test_output/rpf_ranked_signal_router/20260627_190215_rank_signal_router_btcusdt_8h_b/
  116 signals, 49 TP / 67 FP
  precision 0.422
  FDR 0.578
  lift vs full DOWN base 1.085x
```

Decision:

```text
The stale-history diagnosis is confirmed. `lookback=3` materially improves
precision and FDR, but still misses a strict promotion bar. Post-hoc filtering
on the lookback=3 run shows that requiring reliability_precision_lcb >= 0.55
would produce 38 signals with 24 TP / 14 FP, precision 0.632. The next real
test should keep lookback=3 and raise reliability_min_precision_lcb to 0.55.
```

Strict recency reliability result:

```text
run:
  test_output/rpf_ranked_signal_router/20260627_202223_rank_signal_router_btcusdt_8h_b/

configuration:
  lookback_folds: 3
  min_precision_lcb: 0.55
  max_false_discovery_rate: 0.35

active row-rule DOWN:
  38 signals
  24 TP / 14 FP
  precision 0.632
  FDR 0.368
  lift vs full DOWN base 1.622x
  lift vs raw gate-signal rows 1.556x
```

Decision:

```text
This is the best current DOWN precision result on the 960-window span, but it
is sparse. Treat it as a specialist high-precision signal. The next validation
should test chronological transfer on older/adjacent 960-window slices before
any further model tuning.
```

Offset transfer result:

```text
latest offset=0:
  38 signals, 24 TP / 14 FP
  precision 0.632

offset=480:
  15 signals, 6 TP / 9 FP
  precision 0.400

offset=960:
  9 signals, 0 TP / 9 FP
  precision 0.000
```

Failure diagnosis:

```text
The strict specialist does not transfer as-is. The repeated older false-positive
period is pred_batch_id 4657..4716, caused by:

row_rpf_liquidity_volume_pressure_mean_abs lower_good <= 0.3223715487502642

Latest successful strict rules are all higher_good. Post-hoc filtering across
offset=0,480,960 gives 44 signals, 30 TP / 14 FP, precision 0.682 when only
higher_good rules are kept.
```

Next test:

```text
Rerun the three offset spans with:
--row-rule-gate-allowed-directions higher_good
```

Higher-good direction-filter result:

```text
offset=0:
  38 signals, 24 TP / 14 FP
  precision 0.632

offset=480:
  25 signals, 13 TP / 12 FP
  precision 0.520

offset=960:
  19 signals, 7 TP / 12 FP
  precision 0.368
```

Decision:

```text
The direction filter improves the bridge slice and combined precision, but it
does not solve transfer. The older non-overlapping slice still underperforms
the local DOWN base rate. The row-rule specialist is not promotable as a stable
rule. Next work should diagnose the bad 4657..4716 regime with safe context
features instead of adding another threshold blindly.
```

Safe-context diagnostic:

```text
run:
  test_output/rpf_ranked_signal_context_diagnostic/20260628_044337_rank_signal_context_diagnostic/

inputs:
  higher-good offset=0, offset=480, offset=960 router runs

active blocks:
  6

labels:
  good: 3
  bad: 2
  neutral_active: 1

combined:
  82 signals, 44 TP / 38 FP
  precision 0.537
  lift 1.416x
```

Findings:

```text
bad blocks:
  offset480/block004 and offset960/block012
  feature family: rejection_chop
  rule: row_rpf_rejection_chop_mean_abs higher_good

good blocks:
  mostly liquidity_volume_pressure, plus one rank_score block

safe separators:
  rule_score
  selection_score
  reliability_score
  train_lift
  reliability_precision_lcb
  feature_family
```

Decision:

```text
Next work should not be more global ranker tuning. The next implementation
should turn this diagnostic into a conservative context rule or family-specific
allow/block policy, then replay on offset blocks. Outcome labels remain in
specialist_block_outcomes.parquet only; context_rows.parquet is the safe input
table.
```

Implemented control:

```text
--row-rule-gate-allowed-families
--row-rule-gate-blocked-families
```

Next replay target:

```text
same strict higher-good row-rule setup
plus:
  --row-rule-gate-blocked-families rejection_chop
```

Reason:

```text
The only repeated bad active block across offset480 and offset960 came from
rejection_chop. This run tests whether suppressing that family improves
transfer without destroying sparse high-precision signals.
```

Replay result:

```text
offset=0:
  38 signals, 24 TP / 14 FP
  precision 0.632

offset=480:
  6 signals, 6 TP / 0 FP
  precision 1.000

offset=960:
  0 signals
```

Combined:

```text
44 signals, 30 TP / 14 FP
precision 0.682
FDR 0.318
lift 1.784x
```

Comparison:

```text
previous higher_good baseline:
  82 signals, 44 TP / 38 FP
  precision 0.537

excluding rejection_chop:
  44 signals, 30 TP / 14 FP
  precision 0.682
```

Decision:

```text
The family block improved precision and removed the repeated false-positive
context, but offset960 became no-signal. This is useful as a conservative
false-positive control, not proof that the router can adaptively find signals
in every regime. Next work should test whether liquidity/rank-score-style
families repeat over longer non-overlapping history or whether older regimes
need separate specialist discovery.
```

UP tracking correction:

```text
The latest row-rule replay was DOWN-focused. It kept UP in the router, but the
candidate allow-list included only up_none_v1 on the UP side:

  --candidate-name-allowlist up_none_v1,down_rocket_16_diag_v1

This means the latest UP numbers are not a complete UP optimization result.
They exclude up_rocket_64_v1, even though earlier evidence showed
up_rocket_64_v1 was the stronger UP specialist candidate.
```

Latest UP selected-router output from the same three offset runs:

```text
offset=0:
  21 signals, 9 TP / 12 FP, precision 0.429, lift 1.142x

offset=480:
  21 signals, 6 TP / 15 FP, precision 0.286, lift 0.742x

offset=960:
  3 signals, 0 TP / 3 FP, precision 0.000

combined:
  45 signals, 15 TP / 30 FP
  precision about 0.333
  lift about 0.86x
```

UP evidence to preserve:

```text
small ROCKET UP:
  test_output/rpf_ranked_signal/20260623_000231_rank_signal_btcusdt_8h_b_up/
  17 signals, 13 TP / 4 FP, precision 0.765, lift 1.386x

sparse conservative UP rule bank:
  test_output/rpf_ranked_signal_rule_bank/20260623_234159_rank_signal_rule_bank/
  81 signals, 51 TP / 30 FP, precision 0.630, lift 1.710x

UP transfer separator:
  test_output/rpf_ranked_signal_transfer_separator/20260624_163242_rank_signal_transfer_separator/
  up_rocket_64_v1 score_mean, lower_good, best candidate AUC 0.770
```

Decision:

```text
UP needs its own replay path with up_rocket_64_v1 restored and its own
context/rule diagnostic. The DOWN rejection_chop decision should not be treated
as an UP-side conclusion.
```

## Active Dual-Target Tracking Update

Status as of 2026-06-28:

```text
active tracking doc:
  regression_feature_engineering/docs/rpf_dual_target_tracking.md

active router output mode for new side-symmetric checks:
  --row-rule-gate-output-mode active_candidate

historical-only router output mode:
  --row-rule-gate-output-mode active_down_candidate
```

The next run must cover both sides explicitly:

```text
UP:
  candidate: up_rocket_64_v1
  first row-rule direction: lower_good

DOWN:
  candidate: down_rocket_16_diag_v1
  first row-rule direction: higher_good
  blocked row-rule family: rejection_chop
```

Acceptance for the next pass is not only precision. It must report:

```text
signals
active batches
active days / signal frequency
precision
precision lift versus local base rate
false discovery rate
whether each side beats local base rate on latest and older non-overlapping spans
```

Reason:

```text
The latest DOWN specialist has useful precision but not enough frequency for
steady trading. The latest UP replay was incomplete because up_rocket_64_v1 was
excluded. The next step is a side-symmetric active-candidate replay, not another
DOWN-only filter.
```
