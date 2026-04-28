# HTF Helper Finalization Plan

Date: 2026-04-12

## Objective

Finalize the HTF helper system so that model-facing helper features are:

1. causally valid under a strict no-lookahead contract
2. reproducible in live generation from streaming market data
3. consistent across all active HTF roots:
   - `8h/B`
   - `8h/C`
   - `24h/B`
   - `24h/C`
   - `7d/B`
   - `7d/C`
4. filtered so that weak or degenerate helper traces do not enter CatBoost / LightGBM training

This plan is the single execution reference for finishing helper cleanup after the first implementation slice.

## Current Root Contract

The regime/family mapping is defined in:

- `scripts/feature_engineering/htf_multiregime_pipeline.py`

Current family meaning:

- `B` = unshifted family anchor
- `C` = half-period-shifted family anchor

Current anchors:

- `8h/B` = `00:00 UTC`
- `8h/C` = `04:00 UTC`
- `24h/B` = `00:00 UTC`
- `24h/C` = `12:00 UTC`
- `7d/B` = `Monday 00:00 UTC`
- `7d/C` = `Thursday 12:00 UTC`

Current entry windows:

- `8h` = `4h`
- `24h` = `12h`
- `7d` = `84h`

Current helper source roots:

- all `B` roots read from the canonical base `1m` HTF feature root
- all `C` roots read from the family-specific shifted `1m` HTF feature root

This means helper cleanup must be:

- helper-family aware,
- but not regime-special-cased unless a helper algorithm truly needs different windowing rules.

## Evidence Base

Primary notes:

- `notebooks/notes/htf_helper_source_backed_validity_audit_2026-04-12.md`
- `notebooks/notes/htf_helper_cleanup_execution_board_2026-04-12.md`
- `notebooks/notes/htf_helper_feature_cleanup_plan_2026-04-12.md`

Primary audit artifacts:

- `test_output/htf_helper_causality_audit/20260412_190909`

Primary implementation files:

- `scripts/feature_engineering/htf_helper_cache.py`
- `scripts/feature_engineering/htf_feature_acceptance.py`
- `scripts/target_models/helpers/ou.py`
- `scripts/target_models/helpers/garch.py`
- `scripts/target_models/helpers/egarch.py`
- `scripts/target_models/helpers/cusum.py`
- `scripts/target_models/helpers/kalman.py`
- `riskyield_rust/src/ou.rs`
- `riskyield_rust/src/garch.rs`
- `riskyield_rust/src/egarch.rs`
- `riskyield_rust/src/cusum.rs`
- `riskyield_rust/src/kalman.rs`

Memory-fix note for the full rebuild path:

- `notebooks/notes/htf_helper_cache_oom_investigation_2026-04-13.md`
- `notebooks/notes/htf_helper_cache_streaming_memory_fix_2026-04-13.md`

## Current Status By Helper Family

### `CUSUM`

Status: `KEEP`

Current verdict:

- prefix-only causality audit: pass
- context audit: fail near chunk boundary
- interpretation: causally valid, but exact live parity still depends on context contract

Needed to finish:

- keep current implementation
- add workflow-level guard / regression test so future changes do not break prefix-only causality

### `GARCH`

Status: `KEEP`

Current verdict:

- prefix-only causality audit: pass
- context audit: fail near chunk boundary
- interpretation: causally valid, but exact live parity still depends on context contract

Needed to finish:

- keep current implementation
- add workflow-level guard / regression test

### `OU`

Status: `KEEP`

Current verdict:

- early future-fill bug is fixed in Python and Rust
- `ou_reverting` is now aligned with the same trailing-history rule as the rest
  of the OU feature family
- prefix-only audit: pass
- context audit: pass

Needed to finish:

- keep regression coverage so future changes do not reintroduce early-row
  leakage or mismatched availability semantics

Primary files:

- `scripts/target_models/helpers/ou.py`
- `riskyield_rust/src/ou.rs`

### `Kalman`

Status: `KEEP`

Current verdict:

- explicit streaming-state handoff is implemented
- prefix-only audit passes
- state-handoff audit passes
- Python fallback and Rust runtime match exactly under the same carried state
- helper-cache is Kalman-aware and no longer replays prepended raw context for
  Kalman continuity
- implementation plan is tracked in:
  - `notebooks/notes/htf_kalman_streaming_state_implementation_plan_2026-04-13.md`

Needed to finish:

- keep regression coverage in place so future edits do not break:
  - state-handoff parity
  - Python vs Rust parity
  - helper-cache integration parity

Primary files:

- `scripts/target_models/helpers/kalman.py`
- `riskyield_rust/src/kalman.rs`
- `riskyield_rust/src/lib.rs`
- `scripts/feature_engineering/htf_helper_cache.py`

### `EGARCH`

Status: `KEEP`

Current verdict:

- degenerate parameter traces are blocked from model-facing training:
  - `*_egarch_asymmetry`
  - `*_egarch_persistence`
- dynamic EGARCH is now implemented as an explicit streaming-state helper
- prefix-only audit passes
- state-handoff audit passes
- helper-cache is EGARCH-aware and no longer relies on generic prepended raw
  context replay for EGARCH continuity
- Python fallback and Rust runtime agree to numerical tolerance under the same
  carried state
- implementation note is tracked in:
  - `notebooks/notes/htf_egarch_streaming_state_implementation_2026-04-13.md`

Needed to finish:

- keep regression coverage in place so future edits do not break:
  - state-handoff parity
  - Python vs Rust parity
  - helper-cache integration parity
- keep blocked parameter traces excluded unless redesign proves they become
  meaningful

Primary files:

- `scripts/target_models/helpers/egarch.py`
- `riskyield_rust/src/lib.rs`
- `riskyield_rust/src/egarch.rs`

## Already Completed

These items are not part of the remaining implementation burden:

- blocked degenerate model-facing EGARCH parameter features
- enforced helper exclusion policy in CatBoost / LightGBM / benchmark loaders
- added helper-cache context buffer (`126` rows)
- replaced helper-cache full-memory build with a streaming per-batch writer
- removed OU early future-fill in Python fallback
- removed OU early future-fill in Rust runtime
- rebuilt `riskyield_rust` for the actual `ml_env` CPython 3.11 runtime
- confirmed the exclusion policy is active across all 6 HTF roots

## Remaining Work To Finish Helpers

### Phase 1. Finish Helper-Specific Causality

#### 1. Fix `OU` fully

Task:

- inspect the exact semantics of `ou_reverting`
- remove any remaining mismatch between:
  - prefix-only transform
  - batch transform
  - context+chunk transform

Acceptance:

- `OU` prefix-only audit passes for all 8 OU features
- `OU` context audit has no remaining semantic failure that would block live use

#### 2. Implement `Kalman` streaming-state continuity

Task:

- replace chunk cold-start replay with explicit carry-over state
- define the serializable streaming-state schema
- implement state handoff in:
  - Rust runtime
  - Python fallback
  - helper-cache orchestration

Acceptance:

- split-chunk state-handoff outputs match one-pass causal outputs within tolerance
- Python and Rust parity passes under the same initial state
- the live-state contract is documented in code comments and note form
- status: completed on 2026-04-13

#### 3. Fix dynamic `EGARCH`

Status: completed on 2026-04-13

Task:

- redesign dynamic EGARCH outputs so chunked transform matches causal prefix behavior
- verify that dynamic outputs remain meaningful after stabilization

Acceptance:

- dynamic `EGARCH` prefix-only audit passes for retained model-facing features
- dynamic `EGARCH` state-handoff audit passes under the chosen live contract
- Python and Rust parity passes under the same carried state
- helper-cache workflow smoke passes on real HTF data

### Phase 2. Add Permanent Validation Guards

#### 4. Add workflow-level helper validation

Task:

- fail or flag on:
  - constant / near-constant helper columns
  - helper columns blocked by explicit policy
  - helper families that fail causality audit
  - suspicious chunk-boundary instability

Primary file:

- `scripts/feature_engineering/htf_multiregime_pipeline.py`

Acceptance:

- helper validation runs as part of the production workflow, not just ad hoc audits
- status on 2026-04-13:
  - helper implementation fingerprint + runtime-contract metadata are now part
    of helper-cache and helper-output metadata
  - helper code changes now invalidate stale helper artifacts even when raw
    source data did not change
  - production validation now checks:
    - helper policy version
    - helper contract version
    - helper runtime-contract map
    - helper implementation fingerprint
    - constant helper columns
  - remaining gap:
    - audit-artifact-driven causality gate is still pending

#### 5. Promote causality audit into execution tests

Task:

- convert the current audit into a tracked regression tool for:
  - prefix invariance
  - context invariance
  - Rust/Python consistency where both exist

Acceptance:

- helper causality checks are repeatable and part of the execution workflow

### Phase 3. Rebuild And Re-Evaluate

#### 6. Rebuild helper artifacts

Task:

- rerun helper cache / helper materialization after final fixes

Acceptance:

- helper outputs are regenerated under the final contract

#### 7. Re-run six-root walk-forward diagnostics

Task:

- rerun diagnostics for:
  - `8h/B`
  - `8h/C`
  - `24h/B`
  - `24h/C`
  - `7d/B`
  - `7d/C`

Acceptance:

- helper usage and predictive quality are remeasured after cleanup
- we can compare before vs after on the same root set

## Exact Finish Criteria

The helper system is only considered fully finished when all of the following are true:

1. `CUSUM` and `GARCH` remain causally valid and documented
2. `OU` no longer has any blocking causality mismatch
3. `Kalman` has an explicit, validated chunk-state continuity contract
4. `EGARCH` dynamic outputs are either:
   - fixed and validated, or
   - blocked from model-facing training
5. degenerate helper traces are blocked by policy
6. workflow-level validation guards are active
7. helper artifacts are rebuilt under the final contract
8. six-root diagnostics are rerun and reviewed

## Immediate Next Slice

The next implementation slice should be:

1. rebuild helper artifacts
2. rerun six-root diagnostics
3. review before/after helper usage and predictive quality
4. decide whether to add the optional audit-artifact-driven causality gate

This order is correct because:

- the helper-family contracts are now stable enough to encode
- the next risk is no longer helper implementation correctness, but workflow
  enforcement and end-to-end regeneration
