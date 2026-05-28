# Stage-1 Sparse-Batch Window Handling

## Status

Implemented for the CatBoost Stage-1 path.

## Problem

Merged multi-asset Stage-1 roots can be sparse because target rows are kept only
when every selected context asset has an exact matching timestamp. This is
expected for 24/7 crypto targets joined with Monday-Friday/session assets.

Earlier Stage-1 validity scanning could discover sparse roots, but train and
validation fold windows still assumed numeric `batch_id` continuity. That caused
valid sparse runs to lose candidate combinations with errors such as
`missing_batch:5511:train`.

## Implemented Contract

Original `batch_id` and parquet filenames remain unchanged. Stage-1 now adds a
dense available-batch position for window planning:

```text
stage1_available_pos
batch_id
batch_start_ts
batch_end_ts
row_count
valid_row_count
target_col
feature_target_col
```

Merged dataset assembly writes this sidecar beside `manifest.json`:

```text
data/htf_multiasset_merged/{target}/{context_hash}/{variant?}/{root_id}/stage1_batch_index.parquet
```

The Stage-1 runner can also derive the same index on demand from feature/label
roots, so legacy roots and older generated roots remain usable.

## Window Semantics

Stage-1 window sizes now mean number of available valid batches:

```text
train_batches_per_fold = N available batches
val_batches_per_fold   = M available batches
embargo batches        = skipped available batches
```

Fold artifacts keep backward-compatible batch boundaries and add sparse-safe
fields:

```text
train_start_pos, train_end_pos
val_start_pos, val_end_pos
pred_pos
train_batch_ids, val_batch_ids
train_batch_count, val_batch_count
window_is_sparse
```

Downstream selector and Step-2 reloads prefer explicit `train_batch_ids` and
`val_batch_ids`; older artifacts without those columns still fall back to the
legacy numeric range behavior.

## Validation

Focused validation:

```bash
python -m pytest tests/test_stage1_sparse_batch_windows.py -q
python -m pytest tests/test_htf_multiasset_stage1_dataset.py tests/test_stage1_target_survey_summary.py tests/test_stage1_sparse_batch_windows.py -q
```

Expected behavior:

- contiguous legacy roots keep the same chronological order;
- sparse merged roots do not fail valid fold windows with `missing_batch:*`;
- no stale/as-of context rows are introduced;
- `batch_id` remains traceable to the original HTF root.
