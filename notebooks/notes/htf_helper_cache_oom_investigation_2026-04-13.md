# HTF Helper Cache OOM Investigation — 2026-04-13

## Run

- Run ID: `htf_pythonscript_20260413_021337_pid47941`
- Log: `/media/przem/linux_data/RiskYieldMM (Copy)/test_output/htf_run_logs/htf_pythonscript_20260413_021337_pid47941.log`
- Status: `/media/przem/linux_data/RiskYieldMM (Copy)/test_output/htf_run_logs/htf_pythonscript_20260413_021337_pid47941_status.json`

## Observed Failure

- The process disappeared during `HTF / 8h/C/1m/helpers`.
- Last detail was `8h/C/1m/helpers/cache`.
- No Python traceback was written.
- No helper output files were written for `data/htf_helper_cache/shift4h/1m/target_4class`.

Because kernel logs were not accessible from the environment, this note cannot prove OOM from `dmesg`. The process behavior is nevertheless consistent with an external kill or OOM kill.

## Strongest Evidence

- `8h/B/1m/helpers` completed earlier in the same long-lived process.
- `8h/C/1m/helpers` died before the first helper-chunk progress line appeared.
- The failed path is the same helper-cache implementation in `scripts/feature_engineering/htf_helper_cache.py`.

## Data Size

For `8h/C/1m` raw features:

- rows: `2,720,967`
- batches: `5,669`
- raw columns scanned: `151`
- raw parquet size on disk: `~2.307 GiB`

Helpers actually use only:

- `raw_returns`
- `raw_volatility`
- `close`
- `open`
- `high`
- `low`
- `volume`

So the helper-cache path currently reads far more data than it needs.

## Memory-Heavy Code Path

### 1. Full raw dataset is collected eagerly

File: `scripts/feature_engineering/htf_helper_cache.py`

- `raw_combined = pl.scan_parquet(...).sort("timestamp").collect()`

This collects the full `151`-column raw dataset into memory even though helper preparation only needs `7` columns.

### 2. Raw helper inputs are materialized again

File: `scripts/feature_engineering/htf_helper_cache.py`

- `X, feature_cols = prepare_raw_features_for_helpers(raw_df)`
- `X_df = pd.DataFrame(X, columns=feature_cols)`

This creates:

- a full NumPy matrix
- then a full pandas copy of that matrix

### 3. Helper outputs are accumulated for the whole run

File: `scripts/feature_engineering/htf_helper_cache.py`

- `helper_output_list.append(chunk_df)`
- `helper_df_partial = pd.concat(helper_output_list, axis=0, ignore_index=True)`

Nothing is written incrementally during helper generation. The full helper result is kept in memory until the entire run completes.

### 4. Full helper output is converted again and joined globally

File: `scripts/feature_engineering/htf_helper_cache.py`

- `helper_pl = pl.from_pandas(helper_df_partial)`
- `helper_lookup = ...`
- `raw_batch_lookup = {batch_id: pl.read_parquet(...)}`

So the code builds another full Polars copy of the helper outputs and a global timestamp lookup before writing batch files.

## Lower-Bound Memory Estimate

Using float64-equivalent payload only, without allocator or object overhead:

- raw full matrix equivalent (`2,720,967 x 151 x 8`): `~3.06 GiB`
- helper input matrix (`2,720,967 x 7 x 8`): `~0.14 GiB`
- helper output matrix (`2,720,967 x 44 x 8`): `~0.89 GiB`

This lower bound is already `~4.09 GiB` before:

- pandas object/block overhead
- Polars/Rust allocation overhead
- joins/lookups
- process memory retained after earlier stages
- memory fragmentation after `8h/B/1m/helpers`

That makes OOM on the second `8h` helper family plausible on a 14 GiB machine.

## Most Likely Cause

The helper-cache builder is not streaming. It holds multiple full-dataset copies in memory:

1. full raw HTF features
2. full helper input matrix
3. full pandas helper input frame
4. full concatenated helper output frame
5. full Polars helper output copy
6. full helper timestamp lookup

`8h/B/1m/helpers` completed first, so the process likely entered `8h/C/1m/helpers` with memory already elevated. The second full helper-cache build then pushed the process past available RAM.

## Fix Direction

1. Scan only the helper source columns instead of all `151` raw columns.
2. Stop accumulating `helper_output_list` across the full dataset.
3. Write helper outputs incrementally per chunk or per batch.
4. Remove the global `helper_lookup` join path and emit directly to target cache batches.
5. Optionally isolate helper-cache builds per family/timeframe in a subprocess for clean RSS release.

## Conclusion

The failure is very likely caused by the current helper-cache implementation strategy, not by the helper model logic itself. The next change should target memory behavior in `scripts/feature_engineering/htf_helper_cache.py`.
