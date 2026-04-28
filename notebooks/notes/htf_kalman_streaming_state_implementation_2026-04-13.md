# HTF Kalman Streaming-State Implementation

Date: 2026-04-13

## Scope

Implemented the Kalman helper redesign from cold-start-plus-context replay to
explicit streaming-state handoff.

This change was made so Kalman helper features can be generated causally and
reproduced in live streaming without depending on arbitrary prepended raw
context rows.

## Files Changed

- `scripts/target_models/helpers/kalman.py`
- `riskyield_rust/src/kalman.rs`
- `riskyield_rust/src/lib.rs`
- `scripts/feature_engineering/htf_helper_cache.py`
- `scripts/analysis/htf_helper_causality_audit.py`

## What Changed

### 1. Explicit streaming state

Kalman now carries:

- hidden state `x`
- covariance `P`
- innovation running moments
- velocity running moments

This is required because `zscore` and `regime` depend on expanding moments and
would still reset at chunk boundaries if only `x/P` were carried.

### 2. Python and Rust API parity

Both implementations now support:

- transform with optional initial state
- returning final state after processing the chunk

### 3. Helper-cache integration

Helper cache is now Kalman-aware:

- generic raw-context replay still applies to helpers that need it
- Kalman consumes only the real prediction chunk and starts from the fitted
  train-end state

### 4. Audit changes

Kalman-specific state-handoff parity is now audited directly.

The old Kalman raw-context replay comparison is no longer treated as a valid
continuity check because that is no longer the chosen contract.

## Validation

Python compile:

- passed

Rust tests:

- `cargo test kalman --lib` passed

Direct Python vs Rust parity:

- `feature_max_abs_diff = 0.0`
- `feature_mean_abs_diff = 0.0`
- `state_x_max_abs_diff = 0.0`
- `state_p_max_abs_diff = 0.0`

Direct split-chunk parity:

- `split_full_max_abs_diff = 0.0`
- `split_full_mean_abs_diff = 0.0`

Helper-cache smoke:

- succeeded with mixed helper run (`kalman`, `ou`)
- produced expected helper columns without row-misalignment errors

Updated audit output:

- `test_output/htf_helper_causality_audit/20260412_233532`

Kalman audit result:

- `prefix_all_pass = True`
- `state_handoff_all_pass = True`
- `state_handoff_fail_features = 0`
- `state_handoff_max_abs_diff = 0.0`

## Remaining Global Work

Kalman itself is now green under the chosen contract.

Remaining helper-system work is outside this Kalman slice:

- dynamic `EGARCH` redesign
- workflow-level helper validation guards
- helper rebuild and six-root walk-forward rerun
