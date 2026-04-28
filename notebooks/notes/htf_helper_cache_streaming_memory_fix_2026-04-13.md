# HTF Helper Cache Streaming Memory Fix — 2026-04-13

## Objective

Replace the helper-cache full-memory build path with a streaming writer so the
main HTF rebuild can regenerate helper artifacts without exhausting RAM.

## Problem

The previous implementation in `scripts/feature_engineering/htf_helper_cache.py`
did all of the following in one process:

1. collected the full raw HTF feature dataset
2. converted the full helper input to NumPy and pandas
3. accumulated all helper chunk outputs in `helper_output_list`
4. concatenated the full helper output table
5. converted the full helper output back to Polars
6. built a global helper lookup and only then wrote per-batch files

That design was identified as the likely cause of the `8h/C/1m/helpers/cache`
crash during the full rebuild.

## Implemented Fix

### 1. Minimal raw-column projection

Helper cache now scans only:

- `timestamp`
- `batch_id`
- `close`
- `open`
- `high`
- `low`
- `volume`

This matches the actual helper input contract used by
`prepare_raw_features_for_helpers(...)`.

### 2. Streaming chunk iterator

Added `iter_helper_chunk_outputs(...)`:

- preserves the same walk-forward training/prediction boundaries
- preserves the same helper transform continuity rules
- yields chunk outputs instead of accumulating all rows in memory

`compute_helpers_walk_forward_raw(...)` is now only a collecting wrapper over
that iterator for diagnostics and small-sample comparisons.

### 3. Streaming batch writer in `build_helper_cache_exact(...)`

The helper-cache build now:

- processes one helper chunk at a time
- splits each chunk by contiguous `batch_id`
- keeps at most one in-progress batch buffer in memory
- writes completed cache batches immediately
- preserves the old warmup semantics by emitting:
  - full-null helper batches before helper output begins
  - leading null rows inside the first warmup-crossing batch

This keeps output semantics aligned with the previous global-join behavior.

## Verification

### Smoke parity

A reduced-sample parity check was run on the first `20` batches of
`data/htf_features_shift4h/1m`:

- built helper cache with the new streaming writer
- built expected output using `compute_helpers_walk_forward_raw(...)` and the
  previous timestamp-join semantics
- compared every saved batch file

Result:

- `parity_ok = True`

Artifact root:

- `test_output/htf_helper_cache_streaming_smoke/20260413_streaming_check`

### Real `1m` config parity

A second parity check was run with the actual `1m` helper-cache settings used by
the production pipeline:

- first `60` batches of `data/htf_features_shift4h/1m`
- `warmup_rows = 20000`
- `refit_every = 10000`

Result:

- `parity_ok = True`

Artifact root:

- `test_output/htf_helper_cache_streaming_smoke/20260413_streaming_check_realcfg`

## Expected Effect

This fix removes the largest avoidable memory spikes:

- full `151`-column raw collect
- full helper-output accumulation
- full helper lookup join

Peak memory should now be dominated by:

- the minimal raw helper source frame
- the helper input matrix
- one helper chunk
- one in-progress cache batch buffer

instead of multiple full-dataset copies.
