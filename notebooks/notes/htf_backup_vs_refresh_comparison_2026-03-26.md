# HTF Backup vs Refresh Comparison

Date: 2026-03-26

## Scope
Compare the pre-Phase-9 production snapshot:

- `backups/htf_production_snapshot_pre_phase9_20260318_131026`

against the current refreshed HTF artifact trees under:

- `data/htf_*`

This comparison is based on root-level file/byte summaries plus representative
schema checks for features, optimized outputs, helpers, and helper cache.

## Executive Summary

The refresh behaved as intended overall.

- All combined/backtest roots are unchanged versus the backup.
- All `4class` label roots are unchanged versus the backup.
- The refreshed run changed only the expected downstream surfaces:
  - features
  - optimized outputs
  - helper outputs
  - helper cache
- Batch/file coverage stayed stable. The refresh updated existing batch content
  rather than creating or deleting HTF batches.

## Root-Level Comparison

Total tracked roots compared: `31`

- unchanged roots: `12`
- changed roots: `19`

Unchanged roots are exactly:

- `data/htf_backtest`
- `data/htf_backtest_shift4h`
- `data/htf_backtest_24h`
- `data/htf_backtest_24h_shift12h`
- `data/htf_backtest_7d`
- `data/htf_backtest_7d_shift84h`
- `data/htf_4class_labels`
- `data/htf_4class_labels_shift4h`
- `data/htf_4class_labels_24h`
- `data/htf_4class_labels_24h_shift12h`
- `data/htf_4class_labels_7d`
- `data/htf_4class_labels_7d_shift84h`

Changed roots are:

- all `htf_features*` roots
- all `htf_optimized*` roots
- all `htf_with_helpers*` roots
- `data/htf_helper_cache`

Interpretation:

- the refresh preserved combined and label contracts
- the changes are downstream of that, which matches the intended richer-feature
  promotion path

## Feature Trees

All refreshed feature roots kept the same number of files as the backup. The
refresh increased bytes and schema width rather than changing batch coverage.

Representative schema comparison:

- `1m` features: `116` total cols / `93` feature cols -> `151` total cols / `128` feature cols
- `15m` features: `116` total cols / `93` feature cols -> `151` total cols / `128` feature cols
- legacy `5m` features: unchanged at `102` total cols / `93` feature cols

This matches the intended available-data expansion:

- `1m` and `15m` gained the auxiliary-source and composite features
- `5m` remained legacy-only and unchanged

## Optimized Trees

All refreshed optimized roots kept the same number of files as the backup.

Observed behavior:

- `1m / target_4class` optimized outputs widened from `116` total cols / `93`
  feature cols to `151` total cols / `128` feature cols
- `15m` optimized outputs in the base root remained unchanged
- `target_8class` optimized outputs remained unchanged
- the multi-regime optimized roots changed because their active optimized leaf is
  `1m / target_4class`

Interpretation:

- the refresh propagated the richer feature schema only into the optimized
  surfaces that are supposed to consume it

## Helper Outputs

All refreshed helper roots kept the same number of files as the backup.

Representative schema comparison:

- helper outputs: `159` total cols / `93` feature cols / `43` helper cols
  -> `194` total cols / `128` feature cols / `43` helper cols

Interpretation:

- helper outputs now carry the richer feature set
- helper column count itself stayed stable at `43`

## Helper Cache

Helper cache root summary:

- file count unchanged: `24845`
- total bytes changed only slightly: `2425322508 -> 2425322521`

By file-size scan, only `3` helper-cache files differed:

- `base_0h/1m/target_4class/batch_5670.parquet`
- `shift12h/1m/target_4class/_helper_cache_meta.json`
- `shift84h/1m/target_4class/_helper_cache_meta.json`

For the changed batch file:

- shape stayed the same: `(87, 44)`
- column set stayed the same
- actual values differ in `4` helper columns:
  - `H_4cl_1_garch_vol_zscore`
  - `H_4class_1_kalman_zscore`
  - `H_4class_1_egarch_vol_zscore`
  - `H_4class_1_egarch_leverage_active`

Important limitation:

- this helper-cache scan detected changed files by existence/size, so it proves
  these `3` files changed
- it does not prove there are no same-size content deltas elsewhere

## Net Conclusion

The refreshed workflow preserved the intended stable surfaces:

- combined/backtest roots unchanged
- `4class` label roots unchanged
- batch/file coverage unchanged across refreshed downstream roots

The refreshed workflow updated the intended mutable surfaces:

- `1m` and `15m` features widened from `93` to `128` feature columns
- `1m / target_4class` optimized outputs widened to match
- helper outputs widened to carry the richer feature set while keeping `43`
  helper columns

The only notable low-level exception found in this comparison was the small
helper-cache delta in `base_0h/1m/target_4class/batch_5670.parquet`, plus two
meta-file updates in shifted helper-cache namespaces.

## Artifacts

- root-level compare:
  - `test_output/htf_backup_vs_current_root_compare.json`
- schema compare:
  - `test_output/htf_backup_vs_current_schema_compare.json`
- optimized compare:
  - `test_output/htf_backup_vs_current_optimized_compare.json`
