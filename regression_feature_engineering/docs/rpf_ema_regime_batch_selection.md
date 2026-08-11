# RPF EMA-Regime Batch Selection

## Purpose

Historical reference for the deterministic EMA200 regime walk-forward test for
the RPF binary UP/DOWN classifiers. This branch is abandoned for active
modeling as of 2026-06-17.

## Current Status

Status: `abandoned_active_path`.

Do not use this as the active RPF modeling path. The EMA-regime path passed
basic plumbing checks, but it is abandoned because it does not address the
current chronological classifier failure mode: per-window threshold
instability, zero-positive collapse, and whole-batch-positive collapse.
Keep this document only so historical commands and artifacts remain
reproducible.

The implementation is available in:

```text
regression_feature_engineering/walkforward/ema_regime.py
```

and is exposed through:

```bash
python -m regression_feature_engineering.walkforward.classify \
  --window-mode ema_regime_bank
```

This is not a promoted trading gate and is not a next-step experiment. It was
a controlled test of whether the UP classifier works better when trained,
validated, and evaluated inside above-EMA regimes, and whether the DOWN
classifier works better inside below-EMA regimes.

Each EMA timeframe gets its own effective walk-forward prediction window list.
The runner starts from the frozen readiness windows, searches a recent pool,
keeps only prediction batches where the matching EMA side is active, and then
takes the latest requested windows. This stays causal because current close
versus a closed EMA200 is known at prediction time.

## Scope

Initial scope is `BTCUSDT 8h/B` for:

```text
target_cls_extreme_up_ge_2x_down_hvol_v2
target_cls_extreme_down_ge_2x_up_hvol_v2
```

Timeframes to compare:

```text
15m
1h
4h
1d
```

The EMA is always EMA200 computed from closed canonical OHLCV bars. Prediction
rows use current 1m close versus the latest closed EMA200 for the selected
timeframe.

## Source Of Truth

- Batch selector and row filter: `regression_feature_engineering/walkforward/ema_regime.py`
- Binary runner integration: `regression_feature_engineering/walkforward/classify.py`
- Current state: `current_feature_state.md`
- Output artifacts:
  - `ema_regime_inventory_{timeframe}.parquet`
  - `window_ema_regime.parquet`
  - `trials.parquet`
  - `window_metrics.parquet`
  - `validation_scores.parquet`
  - `prediction_scores.parquet`

## What This Does Not Decide

This doc does not promote EMA200 as a final gate, choose the best timeframe, or
replace RPF feature families. It defines the causal test method.

## Causal Rule

For prediction batch `P`, a historical train/validation candidate batch is
allowed only when:

```text
label_window_batch_id_max <= P - 1 - ema_regime_label_maturity_embargo_batches
```

This proves the candidate batch's future label window is fully mature before
the prediction batch. Prediction-batch labels are never used for selecting
train/validation batches.

## Batch Selection

For UP target:

```text
above_ema_rate >= ema_regime_dominance_rate
```

For DOWN target:

```text
below_ema_rate >= ema_regime_dominance_rate
```

Validation uses the most recent mature matching batches. Training uses the
next older matching batches. This intentionally differs from chronological
walk-forward training because it asks whether a same-regime historical bank is
more useful than the most recent mixed-regime history.

## Prediction Window Selection

Before model trials start, the runner filters frozen prediction windows by the
selected EMA side:

```text
UP:   pred batch must contain rows above EMA200
DOWN: pred batch must contain rows below EMA200
```

The default prediction filter is:

```bash
--ema-regime-prediction-search-windows 250
--ema-regime-prediction-min-rate 0
```

`prediction-min-rate=0` means at least one active row is required. Increase it
only when you want prediction batches dominated by the EMA side, not merely
row-filtered to that side.

## Row Filtering

By default, `--ema-regime-filter-rows` is enabled for EMA-regime runs.

That means:

- UP runs keep only rows where current close is above the selected closed EMA200;
- DOWN runs keep only rows where current close is below the selected closed EMA200;
- train, validation, and prediction rows are filtered the same way;
- feature selection, threshold selection, and model fitting see only the
  filtered train/validation rows.

Use `--no-ema-regime-filter-rows` only when testing batch selection without
row-level evaluation filtering.

## Memory Rule

EMA-regime inventory is built in label-batch chunks. Keep:

```bash
--ema-regime-inventory-chunk-batches 32
```

as the default. If the machine is under memory pressure, lower it to `16` or
`8`. This only changes inventory build memory and runtime; it does not change
the formulas or selected rows.

The classifier scans only the batch range needed by the requested frozen
prediction windows and `--ema-regime-candidate-lookback-batches`; it does not
scan the full feature root unless the requested lookback requires it.

## First Sweep Command

```bash
PY="/media/przem/linux_data/conda/envs/ml_env/bin/python"
READINESS_RUN="$(ls -td test_output/rpf_clean_walkforward/*_readiness_* | head -1)"
FEATURE_ABLATION="group_structural_room+liquidity_volume_pressure+interaction_confluence"

mkdir -p test_output/rpf_clean_classification_logs

for TARGET in \
  target_cls_extreme_up_ge_2x_down_hvol_v2 \
  target_cls_extreme_down_ge_2x_up_hvol_v2
do
  for TF in 15m 1h 4h 1d
  do
    "$PY" -m regression_feature_engineering.walkforward.classify \
      --asset BTCUSDT \
      --root 8h/B \
      --target-col "$TARGET" \
      --base-run "$READINESS_RUN" \
      --feature-ablation "$FEATURE_ABLATION" \
      --window-mode ema_regime_bank \
      --ema-regime-timeframe "$TF" \
      --ema-regime-dominance-rate 0.80 \
      --ema-regime-train-batches 120 \
      --ema-regime-val-batches 20 \
      --ema-regime-candidate-lookback-batches 2000 \
      --ema-regime-label-maturity-embargo-batches 1 \
      --ema-regime-buffer 0 \
      --ema-regime-inventory-chunk-batches 32 \
      --ema-regime-prediction-search-windows 250 \
      --ema-regime-prediction-min-rate 0 \
      --ema-regime-filter-rows \
      --n-steps 50 \
      --max-configs 12 \
      --objective-metric validation_decision_cost \
      --threshold-mode validation_sweep \
      --fp-cost 5 \
      --fn-cost 1 \
      --fbeta-beta 0.5 \
      --min-validation-recall 0.05 \
      --min-validation-predicted-positive-rate 0.01 \
      --iterations-choices 400,800 \
      --depth-choices 2,3 \
      --learning-rate-choices 0.01,0.02 \
      --l2-leaf-reg-choices 10,30 \
      --early-stopping-rounds-choices 100 \
      --od-wait-choices 100 \
      --task-type GPU \
      2>&1 | tee "test_output/rpf_clean_classification_logs/${TARGET}_ema_${TF}_50steps_12configs.log"
  done
done
```

## Acceptance Checks

For each target/timeframe, inspect:

- validation decision cost;
- prediction false-positive rate;
- prediction precision;
- prediction recall;
- prediction predicted-positive rate;
- `window_ema_regime.parquet` maturity and dominance rates;
- whether row filtering removed too many prediction rows.

The useful outcome is not necessarily the highest global accuracy. The useful
outcome is a stable regime where false positives fall without collapsing
predicted positives or recall.
