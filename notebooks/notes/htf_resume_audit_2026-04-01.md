# HTF Resume Audit 2026-04-01

## Goal

Double-check whether production HTF resume logic works correctly across all stages, regimes, and families.

Scope:

- regimes: `8h`, `24h`, `7d`
- families: `B`, `C`
- stages:
  - combined
  - features
  - distance metrics
  - labels
  - optimized
  - helpers

## Executive Summary

Resume is not uniformly broken, but it is not uniformly strong either.

Current state:

1. `B` family resume is generally healthy.
2. `C` family resume is more conservative and has real operational gaps.
3. Optimization resume is the strongest stage.
4. Helper resume exists, but `C` helper cache is vulnerable to restarting from batch `1` after interrupted long rebuilds.
5. Fingerprints are mtime/size-based, not content-based, so rewriting identical upstream files still counts as source drift.

## Important Systemic Constraint

Fingerprinting is based on:

- path
- `st_mtime_ns`
- file size

Relevant code:

- [htf_artifact_utils.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_artifact_utils.py#L30)
- [htf_helper_cache.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_helper_cache.py#L69)

This means:

- if a stage rewrites files with the same values but newer mtimes,
- downstream stages still treat that as `source_fingerprint` drift.

So from an operational perspective, "same data" and "same source fingerprint" are not the same thing in this workflow.

## Stage-by-Stage Audit

### 1. Combined

#### `B`

Code:

- [htf_multiregime_pipeline.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L862)

Behavior:

- supports `current`
- otherwise rewrites the full combined parquet
- does **not** support incremental tail updates

Assessment:

- correct for its current contract
- coarse-grained, not incremental

#### `C`

Code:

- [htf_multiregime_pipeline.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L1036)

Behavior:

- supports `current`
- otherwise rewrites the full shifted combined parquet
- depends on fingerprint of base `B` combined parquet + base meta

Assessment:

- correct for its current contract
- also coarse-grained, not incremental
- sensitive to upstream rewrite cascades

### 2. Features

#### `B`

Code:

- [htf_multiregime_pipeline.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L1361)
- early `current` exit: [htf_multiregime_pipeline.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L1451)

Behavior:

- supports `current`
- supports `incremental_tail`
- uses overlap/context batches

Assessment:

- healthy
- best batch-stage resume behavior in the pipeline

#### `C`

Code:

- [htf_multiregime_pipeline.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L1231)

Behavior:

- derived from base `B` feature batches plus shifted combined metadata
- skips unchanged output batches one by one
- does **not** have a fast early `current` short-circuit
- when `_prepare_stage_rebuild(...)` sees reasons, all current reasons become destructive because no custom `full_rebuild_reasons` override is provided

Assessment:

- logically correct for current outputs
- operationally inefficient
- resume is incomplete compared with `B`

Observed consequence:

- even with no writes, `8h/C/1m/features` scans all `5669` batches and returns `written=0, skipped=5669`

### 3. Distance Metrics (`15m`)

Code:

- [htf_multiregime_pipeline.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L1601)

Behavior:

- supports `current`
- supports `incremental_tail`
- stores a single parquet and merges rebuilt tail batches back into prior output

Assessment:

- logic is sound
- current metas mostly still show first-build/full-refresh history, but code path itself supports tail resume

### 4. Labels (`1m`)

Code:

- [htf_multiregime_pipeline.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L1768)

Behavior:

- supports `current`
- supports `incremental_tail`
- uses eligible label-batch coverage, not raw combined-batch coverage

Assessment:

- healthy
- current logic is consistent with the earlier weekly label fix

### 5. Optimized

Code:

- [optimize_htf_features.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/optimize_htf_features.py#L599)

Behavior:

- fingerprint-based resume
- per-batch output checks
- transformer state snapshots
- policy-version invalidation

Assessment:

- strongest resume implementation in the workflow

Observed live behavior:

- `8h/B`: `already_up_to_date`
- `24h/B`: resumed from snapshot near tail
- `7d/B`: resumed from snapshot near tail
- `24h/C` and `7d/C`: full recompute after first changed batch

### 6. Helpers

Code:

- orchestration: [htf_multiregime_pipeline.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L2127)
- helper cache build: [htf_helper_cache.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_helper_cache.py#L336)
- helper materialization: [htf_helper_cache.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_helper_cache.py#L603)

#### `B`

Behavior:

- uses canonical helper cache namespace `base_0h`
- supports `current`
- supports `incremental_tail`

Assessment:

- healthy
- note: `24h/B` and `7d/B` intentionally share the canonical `B` cache source rooted on base `8h/B` features

#### `C`

Behavior:

- uses per-regime namespaces:
  - `shift4h`
  - `shift12h`
  - `shift84h`
- supports `current`
- supports `incremental_tail`
- but metadata is only written after successful completion of the full loop

Assessment:

- logic exists
- operational robustness is weak

Observed live state:

- `8h/C` helper cache meta is older than current `shift4h` features
- `24h/C` helper cache meta is older than current `shift12h` features
- `7d/C` helper cache meta is older than current `shift84h` features
- all three currently show:
  - `run_mode=incremental_tail`
  - `first_affected_batch=1`
  - `rebuild_reasons=['source_fingerprint']`

Implication:

- if the long `C` helper-cache rebuild is interrupted before completion,
- stale meta remains,
- next run starts from batch `1` again

## Live Meta Snapshot

### Healthy `B` examples

- `8h/B` features `1m`: `write_start_batch=5668`, `write_batches_count=3`
- `8h/B` helper cache: `first_affected_batch=5668`, `write_start_batch=5666`
- `8h/B` helpers: `first_affected_batch=5670`, `write_start_batch=5668`

### Problematic `C` examples

- `8h/C` features `1m`: no early current exit, scans all `5669` batches even when unchanged
- `8h/C` helper cache: `first_affected_batch=1`, `write_start_batch=1`, `saved_batches=5669`
- `24h/C` helper cache: `first_affected_batch=1`, `write_start_batch=1`, `saved_batches=1890`
- `7d/C` helper cache: `first_affected_batch=1`, `write_start_batch=1`, `saved_batches=271`

## Final Assessment

### Works correctly

- `B` features resume
- `B` labels resume
- `B` optimized resume
- `B` helpers resume
- distance metrics resume logic

### Works, but too coarse

- base combined
- shifted combined

### Works, but inefficient/incomplete

- shifted `C` features

### Works in theory, but operationally fragile

- `C` helper cache / helper materialization

## Most Important Gaps To Fix

1. Add a fast early `current` short-circuit to shifted `C` feature materialization.
2. Improve `C` helper-cache robustness so interrupted long runs do not keep restarting from batch `1`.
3. Revisit mtime/size-only fingerprints if the intended contract is "same values should not trigger downstream recompute."
