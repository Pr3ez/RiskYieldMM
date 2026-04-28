# HTF Helper Workflow Invalidation Guards

Date: 2026-04-13

## Objective

Prevent the production HTF workflow from silently reusing stale helper artifacts
after helper implementation changes.

This applies to the main production entrypoint:

- `notebooks/htf_pythonscript.py`

through the shared pipeline:

- `scripts/feature_engineering/htf_multiregime_pipeline.py`

and the helper cache/materialization layer:

- `scripts/feature_engineering/htf_helper_cache.py`

## Problem

Before this slice, helper artifacts were invalidated mainly by:

- raw-source fingerprint changes
- pipeline artifact version changes
- helper output policy version changes

That was not enough. If `OU`, `Kalman`, `EGARCH`, `CUSUM`, or `GARCH`
implementation changed, the workflow could still treat existing helper cache and
materialized helper outputs as current unless raw data also changed or the user
forced a rebuild.

## What Was Added

### 1. Helper implementation fingerprint

`htf_helper_cache.py` now computes a content-based fingerprint over the active
helper implementation files, including:

- helper Python modules
- helper Rust modules
- helper ensemble wiring
- helper cache orchestration
- helper feature-acceptance policy

### 2. Helper runtime-contract metadata

The helper cache and final helper outputs now record:

- `helper_contract_version`
- `helper_runtime_contracts`
- `helper_implementation_fingerprint`

Current runtime contracts:

- `cusum` -> `context_replay_v1`
- `garch` -> `context_replay_v1`
- `ou` -> `context_replay_v1`
- `kalman` -> `streaming_handoff_v1`
- `egarch` -> `streaming_handoff_v1`

### 3. Rebuild invalidation on helper code changes

Helper cache rebuild logic now treats contract changes as full-rebuild reasons.

Materialized helper outputs also track the current helper contract and require
it to match during rebuild/current checks.

### 4. Production validation checks

The validation stage in `htf_multiregime_pipeline.py` now checks:

- helper output meta exists
- helper policy version matches current policy
- helper contract version matches current code
- helper runtime-contract map matches current code
- helper implementation fingerprint matches current code
- helper cache meta exists
- helper cache contract version matches current code
- helper cache runtime-contract map matches current code
- helper cache implementation fingerprint matches current code
- helper columns are not constant

## Practical Effect

Existing helper artifacts built before this slice do not carry the new metadata.

That is intentional. The validation now flags them as stale, which forces the
next real HTF run to rebuild helper cache and helper outputs under the current
contract instead of silently accepting old helper parquets.

## Remaining Work

This slice does not finish the whole helper finalization process.

Still pending:

- rebuild helper artifacts under the new metadata contract
- rerun six-root diagnostics
- optional audit-artifact-driven causality gate in production validation
