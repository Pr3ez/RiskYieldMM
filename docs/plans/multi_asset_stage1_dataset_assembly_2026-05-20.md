# Multi-Asset Stage-1 Dataset Assembly

## Status

Implemented in this branch as an opt-in Stage-1 launcher path.

Main code:

- `scripts/htf_backtest/catboost/stage1_multiasset_dataset.py`
- `scripts/analysis/htf_stage1_regime_family_walkforward.py`
- `scripts/htf_backtest/catboost/utils.py`

## Contract

The assembler builds one merged dataset per target asset, context asset set, and
regime/family root:

```text
8h/B, 8h/C, 24h/B, 24h/C, 7d/B, 7d/C
```

Target rows remain authoritative. Context assets are exact `timestamp` joins
only. Rows missing any selected context asset are dropped. Labels come only from
the target asset. Rows with null model feature values after the merge are also
dropped, and the manifest reports them separately as
`rows_dropped_by_null_features`.

Output layout:

```text
data/htf_multiasset_merged/{target_asset}/{context_hash}/{root_id}/features/1m/target_4class/batch_*.parquet
data/htf_multiasset_merged/{target_asset}/{context_hash}/{root_id}/labels/1m/batch_*.parquet
data/htf_multiasset_merged/{target_asset}/{context_hash}/{root_id}/stage1_batch_index.parquet
data/htf_multiasset_merged/{target_asset}/{context_hash}/{root_id}/manifest.json
```

Feature naming:

- target feature columns: `T_<target_asset>__<feature>`
- context feature columns: `C_<context_asset>__<feature>`
- preserved Stage-1 columns: `timestamp`, `batch_id`, `bar_in_batch_norm`
- target labels remain unprefixed in the label files

Context `target_*` label columns are excluded from merged features.

Sparse batch ids are allowed. Exact timestamp alignment can drop early target
history or local closed-session spans, so merged roots may not contain every
batch id between the first and last written file. Stage-1 treats the actual
written feature/label batch intersection as the valid batch set, writes a dense
`stage1_available_pos` sidecar, and plans train/validation windows by available
position instead of numeric `batch_id` continuity.

The original `batch_id` remains the historical HTF/root identifier. Fold
artifacts preserve both the backward-compatible start/end batch columns and
explicit `train_batch_ids` / `val_batch_ids` lists, so sparse roots are
first-class Stage-1 inputs rather than expected no-winner failures.

## Commands

Build one merged root without training:

```bash
python scripts/analysis/htf_stage1_regime_family_walkforward.py \
  --build-merged-dataset \
  --target-assets BTCUSDT \
  --context-assets ETHUSDT,EURUSD,USDJPY,GC,CL,ES,NQ \
  --roots 8h/B \
  --plan-only
```

Run a small Stage-1 smoke job:

```bash
python scripts/analysis/htf_stage1_regime_family_walkforward.py \
  --build-merged-dataset \
  --target-assets BTCUSDT \
  --context-assets ETHUSDT,EURUSD,USDJPY,GC,CL,ES,NQ \
  --roots 8h/B \
  --n-steps 2 \
  --resume-mode skip_completed \
  --runtime-mode routine
```

Run one job per core target:

```bash
python scripts/analysis/htf_stage1_regime_family_walkforward.py \
  --build-merged-dataset \
  --target-assets core \
  --context-assets core-ex-target \
  --roots 8h/B \
  --n-steps 2 \
  --resume-mode skip_completed \
  --runtime-mode routine
```

Run target-by-target before launching `--target-assets core`; full all-core
context roots are wide and can write many GB of generated parquet data.

## Local Smoke Evidence

Latest validated local smoke:

```text
root: 8h/B
target: BTCUSDT
context: core-ex-target
all-core exact timestamp rows: 413,652
manifest duplicate_count: 0
manifest null_feature_count: 0
manifest rows_dropped_by_missing_context: 974,965
manifest rows_dropped_by_null_features: 16,823
Stage-1 valid batches: 1,718 / 1,761
Stage-1 smoke result: steps_ok=1, steps_error=0
winner_accuracy: 0.2667
winner_macro_f1: 0.1053
```

The quality numbers above are only smoke evidence. They prove the assembly and
Stage-1 payload path run end to end, but they are not enough to judge model
quality or trading usefulness.

## Validation

Implemented tests:

```bash
python -m pytest tests/test_htf_multiasset_stage1_dataset.py -q
python -m pytest tests/test_htf_workflow_contract.py -q
```

Compile check:

```bash
python -m py_compile \
  scripts/analysis/htf_stage1_regime_family_walkforward.py \
  scripts/htf_backtest/catboost/stage1_multiasset_dataset.py \
  scripts/htf_backtest/catboost/utils.py
```

## Still Deferred

- As-of/freshness-based context joins.
- Downstream causal-method diagnostics grouped by target/context identity.
- Stage-1 Step-2 reporting updates for multi-asset run ids.
