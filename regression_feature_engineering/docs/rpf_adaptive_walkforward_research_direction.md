# RPF Adaptive Walk-Forward Research Direction

## Purpose

Summarize what the RPF ranked-signal experiments have proven, what failed, and
what external time-series/stream-learning research says we should implement
next.

## Current Conclusion

The active problem is no longer basic model mechanics.

These parts work:

- RPF-native feature and label loading;
- exact `timestamp,batch_id` joins;
- grouped CatBoostRanker training by `batch_id`;
- causal walk-forward windows;
- ElasticNet/CatBoost/ROCKET experiments as mechanical branches;
- row-rule shadow replay and active decision artifacts;
- prequential update discipline where current prediction labels only mature
  into future history.

The current failure is **validation-to-prediction transfer under non-stationary
market context**.

The practical question is:

```text
When is a specialist signal allowed to fire?
```

not:

```text
Can one global classifier/ranker predict all UP/DOWN events?
```

## Local Evidence

### Old Classifier Branches

The binary classifier path produced occasional high-precision sparse results,
but they did not become stable broad predictors. AUC/logloss were not useful
promotion metrics for this target because trading usefulness depends on sparse,
high-precision repeated signals, not global probability calibration.

Historical classifier command surfaces remain diagnostic:

```text
python -m regression_feature_engineering.walkforward.classify
python -m regression_feature_engineering.walkforward.classify_optuna
```

They are not the active promotion path.

### Ranked-Signal Path

The ranked-signal path was the correct reset because it matched the real
decision:

```text
rank rows inside each batch -> fire only selected high-confidence rows
```

The active command surface is:

```text
python -m regression_feature_engineering.walkforward.rank_signal_router
```

### DOWN Row-Rule Specialist Evidence

The best recent strict DOWN specialist on the latest 960 windows:

```text
run:
  test_output/rpf_ranked_signal_router/20260627_202223_rank_signal_router_btcusdt_8h_b/

setup:
  row-rule reliability lookback folds: 3
  row-rule reliability min precision LCB: 0.55
  row-rule reliability max FDR: 0.35

result:
  38 signals
  24 TP / 14 FP
  precision 0.632
  FDR 0.368
  lift vs full DOWN base 1.622x
```

This was a real improvement over all-history reliability:

```text
all-history:
  precision 0.382
  FDR 0.618

lookback=3, loose LCB:
  precision 0.495
  FDR 0.505

lookback=3, strict LCB:
  precision 0.632
  FDR 0.368
```

### Transfer Failure

The same strict specialist failed on older non-overlapping windows:

```text
offset=0 latest:
  pred batches 4897..5856
  38 signals, 24 TP / 14 FP
  precision 0.632

offset=480 bridge:
  pred batches 4417..5376
  15 signals, 6 TP / 9 FP
  precision 0.400

offset=960 older:
  pred batches 3937..4896
  9 signals, 0 TP / 9 FP
  precision 0.000
```

A direction filter improved the bridge slice but still failed on the older
non-overlapping slice:

```text
--row-rule-gate-allowed-directions higher_good

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

The repeated weak period is:

```text
pred_batch_id 4657..4716
```

The current implementation can identify local specialist rules, but it cannot
yet decide whether the current market context is safe for that specialist.

## Research Basis

### Time-Series Splits

Scikit-learn `TimeSeriesSplit` formalizes the core principle we already follow:
training data must come before test data, and a gap can be used to separate
train/test when needed.

Reference:

```text
https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
```

Implication for this project:

- keep explicit chronological train/validation/prediction windows;
- never shuffle;
- never use current prediction labels for current selection;
- keep label-window safety checks.

### Ranking Is Valid For Batch Grouping

CatBoost ranking objectives support pairwise/groupwise ranking, and CatBoost
uses group IDs for ranking groups. This matches our use of:

```text
group_id = batch_id
```

References:

```text
https://catboost.ai/docs/en/concepts/loss-functions-ranking
https://catboost.ai/docs/en/concepts/python-reference_catboostranker
```

Implication for this project:

- CatBoostRanker is still the correct row scorer;
- do not abandon ranking because the rule gate failed;
- the failure is downstream specialist selection, not grouped ranking itself.

### Prequential Evaluation With Forgetting

Stream-learning literature recommends predictive-sequential evaluation with
forgetting mechanisms such as sliding windows or fading factors for
non-stationary streams. This directly matches our observed problem: old rule
success can become stale and harm future decisions.

Reference:

```text
https://link.springer.com/article/10.1007/s10994-012-5320-9
```

Implication for this project:

- use prequential routing;
- update specialist trust only after prediction labels mature;
- use rolling/fading reliability, not all-history reliability;
- report block-level performance, not only aggregate performance.

### Drift Detection

ADWIN is a standard adaptive-window drift detector for streams. It detects
distribution/performance changes by maintaining an adaptive window.

Reference:

```text
https://riverml.xyz/latest/api/drift/ADWIN/
```

Implication for this project:

- add drift monitoring on specialist decision loss or precision-lift;
- if drift is detected, reset or shrink that specialist's reliability memory;
- do not use ADWIN as a model; use it as a memory-control signal.

### Selective Prediction

Selective prediction/reject-option literature frames the real objective:
the model should abstain unless expected risk is acceptable. That maps directly
to sparse trading signals.

References:

```text
SelectiveNet:
https://arxiv.org/abs/1901.09192

Conformal Risk Control:
https://arxiv.org/abs/2208.02814
```

Implication for this project:

- optimize precision/risk at a target coverage level;
- abstention is a valid output, not a failure;
- promotion should require stable risk at low coverage, not high recall.

## What This Means

The right architecture is an **adaptive specialist router**:

```text
RPF features
-> CatBoostRanker candidate score
-> candidate row-rule specialists
-> safe context diagnostics
-> prequential specialist trust with forgetting/drift reset
-> selective decision / abstain
```

The wrong next steps are:

- another broad CatBoost hyperparameter sweep;
- adding more CNN/ROCKET branches before routing is solved;
- tuning row-rule thresholds only on the latest slice;
- optimizing on current prediction labels;
- promoting a specialist from one chronological cluster.

## Recommended Next Implementation

### Phase 1: Safe Context Diagnostic

Implemented:

```bash
python -m regression_feature_engineering.walkforward.rank_signal_context_diagnostic
```

Latest command:

```bash
python -m regression_feature_engineering.walkforward.rank_signal_context_diagnostic \
  --router-run test_output/rpf_ranked_signal_router/20260628_001251_rank_signal_router_btcusdt_8h_b \
  --router-run test_output/rpf_ranked_signal_router/20260628_013625_rank_signal_router_btcusdt_8h_b \
  --router-run test_output/rpf_ranked_signal_router/20260628_025919_rank_signal_router_btcusdt_8h_b \
  --side down \
  --candidate-name down_rocket_16_diag_v1 \
  --good-min-precision 0.60 \
  --good-min-precision-lift 1.20 \
  --bad-max-false-discovery-rate 0.50
```

Latest output:

```text
test_output/rpf_ranked_signal_context_diagnostic/20260628_044337_rank_signal_context_diagnostic/
```

Inputs:

```text
one or more rank_signal_router runs
```

Required outputs:

```text
test_output/rpf_ranked_signal_context_diagnostic/{run_id}/
events.jsonl
stage_status.json
context_rows.parquet
specialist_block_outcomes.parquet
good_bad_context_comparison.parquet
context_report.md
```

Each row should represent:

```text
side
candidate_name
rule feature
rule direction
rule threshold
source run
source offset
block id
pred_batch_start/end
```

Safe context inputs:

```text
rank_score mean/std/p50/p95
threshold
accepted row rate
rule family
rule direction
rule reliability precision/lcb/fdr/signals/history_folds
candidate raw signal count/precision/lift
block base positive rate from matured labels only for diagnostics
past positive-rate mean/std before current block
RPF family summary features already present in safe row context
```

Outcome labels:

```text
good_block = precision >= 0.60 and precision_lift > 1.20
bad_block  = precision < local_base_rate or FDR > 0.50
```

The context model must never use current labels as inputs for the current
decision. Labels are only diagnostic outcomes.

### Phase 2: Specialist Ledger

Build a ledger of each specialist rule family over chronological blocks:

```text
specialist_key =
  side
  candidate_name
  rule_feature_family
  rule_direction
```

For each block:

```text
signals
TP
FP
precision
precision_lift
FDR
active_window_rate
accepted_row_rate
safe context summary
```

This makes the system reason about stable specialists instead of one-off rules.

### Phase 3: Adaptive Specialist Router V2

Add a new selection mode:

```text
--row-rule-gate-selection-mode adaptive_specialist_v2
```

Selection logic per block:

1. Train candidate rules on the prior block.
2. Convert candidate rules into specialist keys.
3. Check recent/fading specialist performance only from matured prior blocks.
4. Check current safe context against the specialist's historically good
   context envelope.
5. If both reliability and context pass, allow the specialist.
6. Otherwise abstain.
7. After the prediction block matures, update the specialist ledger.

Minimum gates for v2:

```text
recent precision LCB >= 0.55
recent FDR <= 0.35
recent signal count >= 8
current accepted row rate inside historical good range
current rank_score/threshold context inside historical good range
optional ADWIN drift state is not alarmed
```

### Phase 4: Replay Validation

Replay on non-overlapping spans:

```text
offset=0
offset=960
offset=1920 if readiness supports it
```

Promotion target:

```text
precision > local base rate on every non-overlapping span
combined precision >= 0.60
FDR <= 0.40
no single bad block wipes out the edge
signal count high enough to be meaningful, but abstention is allowed
```

## Immediate Decision

Do not promote the current row-rule gate.

Do not abandon CatBoostRanker.

Build the safe-context diagnostic and specialist ledger next. The latest tests
show there is signal, but it is regime-conditional. The missing component is a
prediction-safe context router that decides when the specialist is allowed to
fire.
