# HTF Helper Resume Investigation 2026-04-01

## Question

Why does `8h/C/1m/helpers` appear to recompute from the beginning on repeated runs, even when the user believes the data is unchanged?

## Conclusion

Helper resume logic is implemented and works for the `B` family. The expensive repeated work is concentrated in the `C` helper cache, especially `8h/C/1m`, and the immediate reason is stale helper-cache metadata relative to the current `C` feature corpus.

This is not the same as "helpers always recompute everything."

## Evidence

### 1. Resume logic exists

The helper cache stage returns `run_mode=\"current\"` only when there are no affected batches and no rebuild reasons:

- [htf_helper_cache.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_helper_cache.py#L410)

The final helper materialization stage has the same type of short-circuit:

- [htf_helper_cache.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_helper_cache.py#L686)

### 2. `B` helpers are resuming incrementally

Current `8h/B` metas show small tail-only recompute:

- cache meta: `first_affected_batch=5668`, `write_start_batch=5666`, `saved_batches=3`
- helpers meta: `first_affected_batch=5670`, `write_start_batch=5668`, `saved_batches=1`

### 3. `C` helper cache is stale versus current `C` features

For `8h/C`:

- helper cache meta mtime: `2026-03-31T01:32:15`
- helper output meta mtime: `2026-03-31T01:33:53`
- latest `htf_features_shift4h/1m/batch_5669.parquet` mtime: `2026-04-01T01:48:45`

That means the `shift4h` helper cache fingerprint is older than the current `shift4h` feature corpus. The rebuild reason is therefore `source_fingerprint`, and the cache starts from batch `1`.

### 4. Current log confirms full-tail cache rebuild for `8h/C/1m`

From:

- [htf_pythonscript_20260401_031616_pid1243795.log](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/htf_run_logs/htf_pythonscript_20260401_031616_pid1243795.log)

Observed lines:

- `8h/C/1m/features` finishes as `current`, with `written=0, skipped=5669`
- `8h/C/1m/helpers/cache` then logs:
  - `affected=5669 (first=1), write_start=1, write_batches=5669`

So the heavy helper work is not caused by the current run rewriting all `C` feature batches first. It is caused by the stale helper-cache state.

### 5. Helper cache meta is only written at the end

The cache stage writes `_helper_cache_meta.json` after the full loop finishes:

- [htf_helper_cache.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_helper_cache.py#L546)

The final helper output meta is also written at the end:

- [htf_helper_cache.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_helper_cache.py#L764)

This means that if the long-running `shift4h` cache rebuild is interrupted before completion, the stale meta remains in place, and the next run will restart from batch `1` again.

## Separate inefficiency

There is also a different issue in shifted `C` feature materialization:

- [htf_multiregime_pipeline.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L1231)

`_build_shifted_feature_batches_from_base(...)` scans every shifted batch and skips them one by one. It does not have the fast early `current` short-circuit that exists for `B` features:

- shifted `C` feature stage: [htf_multiregime_pipeline.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L1280)
- `B` feature early current exit: [htf_multiregime_pipeline.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L1451)

This wastes time every run and makes the workflow look worse, but it is not the direct cause of the helper cache rebuilding from batch `1`.

## Practical reading

The current `8h/C/1m/helpers` behavior means:

1. helper resume is implemented
2. `C` helper cache is currently dirty relative to `shift4h` features
3. the long rebuild has not yet completed cleanly and refreshed its meta
4. rerunning before that completion makes it start from batch `1` again

## Recommended next fixes

1. Let one full `shift4h` helper-cache rebuild complete cleanly and verify the next run goes `current`.
2. Add a fast early `current` short-circuit to shifted `C` feature materialization.
3. Consider progress-safe cache metadata or checkpointing if interrupted helper-cache builds are common.
