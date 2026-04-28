# HTF Batch Metadata Feature Safety

Date: 2026-04-11

## Question

Are these columns safe to use as model features?

- `family_batch_id`
- `family_bar_pos`
- `bar_in_batch_norm`
- `source_base_batch_id`

## Short Answer

- `family_batch_id`: causal, but not safe as a model feature
- `family_bar_pos`: causal, but redundant and better excluded
- `bar_in_batch_norm`: causal and acceptable to keep
- `source_base_batch_id`: causal, but not safe as a model feature

## Why They Are Not Lookahead By Themselves

These fields are built from current-row timestamp and batch assignment metadata in
`scripts/feature_engineering/htf_multiregime_pipeline.py`.

Relevant implementation:

- `family_batch_id`
  - assigned from current family batch index
- `family_bar_pos`
  - assigned as ordinal row position within the current batch
- `source_base_batch_id`
  - inherited from the corresponding base batch for the current row
- `bar_in_batch_norm`
  - normalized from current in-batch position

These values do not read future labels or future closes directly.

So the issue is not classical lookahead bias.

## Why Two Of Them Are Still Unsafe

### `family_batch_id`

This is effectively a monotonic time index over the dataset.

Problems:

- it lets the model learn era position rather than market state
- it has very high drift in diagnostics
- it depends on corpus-specific numbering, so extending history can shift its meaning

Conclusion:

- keep it in artifacts for bookkeeping
- do not let the model train on it

### `source_base_batch_id`

This is the same type of risk in base-batch coordinates.

Problems:

- acts as a time/era proxy
- drift-heavy in merged diagnostics
- can encourage memorization of historical sequence rather than generalizable structure

Conclusion:

- keep it in artifacts
- exclude it from model features

## Why `family_bar_pos` Should Also Be Excluded

`family_bar_pos` is causal: at a given timestamp you know how many bars have elapsed in the batch.

But:

- it carries the same information as `bar_in_batch_norm`, just unnormalized
- `bar_in_batch_norm` is the cleaner downstream contract feature
- keeping both is unnecessary duplication

Conclusion:

- exclude `family_bar_pos`
- keep `bar_in_batch_norm`

## Why `bar_in_batch_norm` Is Different

`bar_in_batch_norm` is the normalized position within the active batch.

It is already part of the documented downstream contract and is used in active code for:

- causal tail filtering in backtest loaders
- head/tail slicing in analysis

It encodes:

- how far we are through the current batch
- how much time remains until batch close

That is available at prediction time, so it is causal.

Conclusion:

- safe from a lookahead perspective
- acceptable to keep as an explicit temporal-position feature

## Code Fix Applied

Backtest loaders were aligned with the intended contract:

- `scripts/htf_backtest/catboost/utils.py`
- `scripts/htf_backtest/lightgbm/utils.py`

Excluded from model feature selection:

- `family_batch_id`
- `family_bar_pos`
- `source_base_batch_id`
- other numeric bookkeeping fields like `is_label_half`, `batch_duration_hours`, `family_shift_hours`, `entry_window_hours`

Intentionally still allowed:

- `bar_in_batch_norm`

## Verification

Verified on a real `7d/C` helper batch:

- excluded in CatBoost loader:
  - `family_batch_id`
  - `family_bar_pos`
  - `source_base_batch_id`
  - `is_label_half`
  - `batch_duration_hours`
  - `family_shift_hours`
  - `entry_window_hours`
- still included:
  - `bar_in_batch_norm`

Result:

- CatBoost feature count after exclusion: `172`
- LightGBM feature count after exclusion: `172`

## Bottom Line

These columns are not all equivalent.

- `family_batch_id` and `source_base_batch_id` are not future-leaking, but they are unsafe as model features because they act as drift-heavy era indices.
- `family_bar_pos` is causal, but redundant next to `bar_in_batch_norm`.
- `bar_in_batch_norm` is the only one of the four that should remain intentionally usable as a model feature.
