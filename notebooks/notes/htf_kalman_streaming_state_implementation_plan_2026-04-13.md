# HTF Kalman Streaming-State Implementation Plan

Date: 2026-04-13

## Objective

Redesign the Kalman helper as a true streaming-state helper so that:

1. helper features are causally valid under strict no-lookahead rules
2. batch HTF generation and live market generation follow the same state contract
3. Python fallback and Rust runtime produce the same outputs under the same carried state
4. the implementation works correctly for all active HTF roots:
   - `8h/B`
   - `8h/C`
   - `24h/B`
   - `24h/C`
   - `7d/B`
   - `7d/C`

This plan replaces the earlier open decision between:

- cold-start plus prepended context
- explicit state handoff

The chosen direction is:

- `Kalman = explicit streaming state handoff`

## Why This Change Is Needed

Current Kalman behavior is only approximately live-equivalent:

- `fit()` warms the filter on the train prefix
- `transform()` currently ignores that fitted hidden state
- helper cache prepends raw context rows to warm the cold-start transform again

That design is workable, but it is not the cleanest contract for a recursive filter.
It also leaves Kalman context-sensitive at chunk boundaries and makes parity depend
on an arbitrary context buffer length.

For a Kalman filter, the more correct live contract is:

- carry forward the hidden filter state directly
- do not reconstruct it indirectly by replaying raw rows

## Workflow Context

The regime/family contract still comes from:

- `scripts/feature_engineering/htf_multiregime_pipeline.py`

Families:

- `B` = unshifted anchor
- `C` = half-period-shifted anchor

Anchors:

- `8h/B` = `00:00 UTC`
- `8h/C` = `04:00 UTC`
- `24h/B` = `00:00 UTC`
- `24h/C` = `12:00 UTC`
- `7d/B` = `Monday 00:00 UTC`
- `7d/C` = `Thursday 12:00 UTC`

Entry windows:

- `8h` = `4h`
- `24h` = `12h`
- `7d` = `84h`

Important implication:

- the Kalman redesign must be regime-agnostic
- state carryover is between consecutive rows of the helper source series
- it must not special-case `8h`, `24h`, `7d`, `B`, or `C`
- the regime/family roots only change which source series Kalman runs over

## Required Kalman State Contract

To get true chunk-to-chunk parity, we must carry more than just filter state.

### State that must be handed off

Core filter state:

- `x`: hidden state vector `[position, velocity, acceleration]`
- `P`: covariance matrix `3x3`

Streaming stats needed for downstream derived features:

- innovation running stats:
  - `innovation_count`
  - `innovation_sum`
  - `innovation_sum_sq`
- velocity running stats:
  - `velocity_count`
  - `velocity_sum`
  - `velocity_sum_sq`

### Why those stats are required

Kalman helper outputs are:

- `filtered_dev`
- `velocity`
- `acceleration`
- `pred_error`
- `innovation`
- `zscore`
- `regime`

`zscore` uses expanding innovation moments.
`regime` uses expanding velocity moments.

If we only carry `x` and `P`, then:

- the filter path is continuous
- but `zscore` and `regime` would reset each chunk

That would still break batch/live parity.

## Implementation Scope

### Phase 1. Define explicit Kalman streaming state

Add a formal Kalman state schema in both Python and Rust.

Python:

- add state dataclass or structured dict in:
  - `scripts/target_models/helpers/kalman.py`

Rust:

- add typed state structs in:
  - `riskyield_rust/src/kalman.rs`

The state schema must include:

- filter hidden state
- covariance
- innovation running stats
- velocity running stats
- contract version

Acceptance:

- a single serialized state object can fully resume Kalman transform at the next row

### Phase 2. Add stateful Kalman transform APIs

Rust:

- extend `riskyield_rust/src/lib.rs`
- add Python bindings for:
  - transform with optional initial state
  - returning final state together with features

Rust implementation should expose something equivalent to:

- `kalman_transform_with_state(signal, config, initial_state=None) -> (features, final_state)`

Python fallback:

- implement the same API in:
  - `scripts/target_models/helpers/kalman.py`

Acceptance:

- Python and Rust both accept the same initial-state payload
- Python and Rust both return the same final-state structure

### Phase 3. Change helper class contract for Kalman

Current Kalman helper still behaves like:

- fit on train prefix
- transform on chunk independently

We need to change KalmanHelper so that:

- `fit()` builds the train-end streaming state
- `transform()` starts from stored state
- `transform()` updates and persists the end state after processing the chunk

This stateful behavior must be explicit, not incidental.

Required code areas:

- `scripts/target_models/helpers/kalman.py`
- possibly shared helper base contracts in:
  - `scripts/target_models/helpers/base.py`

Decision:

- do not generalize the whole helper base layer unless needed
- it is acceptable to give Kalman helper its own explicit state API first

Acceptance:

- Kalman helper can process train prefix then prediction chunk without replaying raw context rows

### Phase 4. Make helper-cache Kalman-aware

Current helper cache prepends generic raw context rows before chunk transform:

- `scripts/feature_engineering/htf_helper_cache.py`

For Kalman under the new contract:

- helper cache must stop relying on prepended raw context for Kalman continuity
- Kalman should consume:
  - train prefix to establish initial state
  - prediction chunk starting from that state

Design target:

- leave generic context buffering in place for helpers that still need it
- make Kalman use explicit state handoff instead of raw-context warmup

That means helper-cache needs helper-specific orchestration:

- `CUSUM`, `GARCH`, current others may still use context-prepend policy
- `Kalman` must switch to state-handoff policy

Acceptance:

- removing Kalman context-prepend does not change outputs when state handoff is used correctly

### Phase 5. Add exact parity and causality tests

We need stronger Kalman-specific tests than the current generic audit.

Required tests:

1. prefix-vs-state-handoff parity
   - full causal prefix transform
   - split at row `k`
   - continue second half from saved state
   - outputs must match full-prefix run on rows `k+1:`

2. Python-vs-Rust parity
   - same signal
   - same initial state
   - same final state
   - same features within tight tolerance

3. chunk-splitting invariance
   - split one sequence into multiple chunks
   - merged outputs must match one-pass outputs

4. helper-cache workflow parity
   - train prefix + pred chunk through production cache path
   - compare with one-pass causal reference

5. regime/family smoke coverage
   - run tests on representatives from:
     - `8h/B`
     - `8h/C`
     - `24h/B`
     - `24h/C`
     - `7d/B`
     - `7d/C`

Acceptance:

- Kalman becomes green on both:
  - prefix causality
  - context/state continuity

### Phase 6. Update workflow guards

Production workflow validation must reflect the new Kalman contract.

Add or extend guards in:

- `scripts/feature_engineering/htf_multiregime_pipeline.py`

Guards should verify:

- no Kalman helper column is constant or degenerate
- no Kalman helper column fails state-handoff parity tests
- Python fallback and Rust runtime remain aligned

Acceptance:

- helper validation fails automatically if the Kalman contract regresses

### Phase 7. Rebuild and rerun downstream analysis

After implementation:

1. rebuild helper artifacts for all six active roots
2. rerun helper causality audit
3. rerun merged walk-forward diagnostics
4. compare:
   - Kalman usage in feature importance
   - pruning behavior
   - model quality deltas

Primary downstream outputs to refresh:

- helper audit outputs
- HTF walk-forward diagnostics root
- helper cleanup execution board

## Files Expected To Change

Core implementation:

- `scripts/target_models/helpers/kalman.py`
- `riskyield_rust/src/kalman.rs`
- `riskyield_rust/src/lib.rs`
- `scripts/feature_engineering/htf_helper_cache.py`

Possibly shared contract helpers:

- `scripts/target_models/helpers/base.py`
- `scripts/target_models/helpers/ensemble.py`

Validation and workflow:

- `scripts/feature_engineering/htf_multiregime_pipeline.py`
- `scripts/analysis/htf_helper_causality_audit.py`

Documentation:

- `notebooks/notes/htf_helper_cleanup_execution_board_2026-04-12.md`
- `notebooks/notes/htf_helper_finalization_plan_2026-04-12.md`

## Risks

1. hidden contract mismatch between Python and Rust state serialization
2. partial continuity if we carry `x/P` but forget the expanding-stat state
3. helper-cache double-warmup if Kalman still receives prepended raw context
4. subtle breakage in walk-forward helper regeneration across `B/C` shifted roots

## Rollout Order

1. formal state schema
2. Rust API
3. Python fallback API
4. Kalman helper class update
5. helper-cache integration
6. Kalman-specific audits and tests
7. workflow guards
8. helper rebuild
9. six-root diagnostics rerun

## Finish Criteria

Kalman redesign is only done when all of these are true:

- Python and Rust support explicit initial-state and final-state handoff
- batch outputs equal chunked state-handoff outputs within tolerance
- helper-cache no longer depends on prepended raw context for Kalman continuity
- causality audit passes under the new state-handoff contract
- live-equivalent generation is documented and reproducible
- the contract works unchanged for `8h/24h/7d` and both `B/C` families
