# HTF Helper Cleanup Execution Board

Date: 2026-04-12

Status key:

- `READY`
- `IN_PROGRESS`
- `BLOCKED`
- `DONE`

## Board

- `DONE` Freeze current helper contract
  - current helper-family contracts are now documented for `CUSUM`, `GARCH`,
    `OU`, `Kalman`, and `EGARCH`
  - regime/family applicability is explicitly tracked for:
    - `8h/B`, `8h/C`
    - `24h/B`, `24h/C`
    - `7d/B`, `7d/C`

- `DONE` Block degenerate EGARCH parameter helper features
  - block `*_egarch_asymmetry`
  - block `*_egarch_persistence`
  - enforce at both final-output policy level and training-loader level

- `DONE` Remove OU future-fill behavior
  - fix Python fallback
  - fix Rust production path
  - ensure early rows are not filled from later valid values

- `DONE` Add causal helper context at chunk boundaries
  - pass trailing historical context into helper transforms
  - trim context rows before saving outputs
  - use enough context for current rolling helper windows

- `DONE` Add source-backed comments in helper modules
  - point to primary sources and the audit rationale for the implementation contract

- `IN_PROGRESS` Add helper causality tests to the codebase
  - prefix invariance
  - no future fill
  - context invariance after enough history
  - Rust vs reference consistency

- `DONE` Decide Kalman live-parity contract
  - chosen direction: explicit streaming state handoff
  - reference plan:
    - `notebooks/notes/htf_kalman_streaming_state_implementation_plan_2026-04-13.md`

- `DONE` Implement Kalman streaming-state handoff in Rust and Python
  - added explicit initial-state/final-state contract
  - carried running innovation and velocity statistics, not only hidden filter state
  - Python fallback and Rust runtime now match exactly under the same carried state

- `DONE` Make helper cache Kalman-aware
  - stopped relying on generic prepended raw context for Kalman continuity
  - kept generic context buffering only for helpers that still need it

- `DONE` Add Kalman state-handoff parity tests
  - one-pass prefix vs split-chunk parity
  - Python vs Rust parity under the same carried state
  - helper-cache workflow parity smoke

- `DONE` Redesign dynamic EGARCH as a streaming-state helper
  - replaced chunk-wide statistics with explicit train-end state handoff
  - aligned Python fallback and Rust runtime under the same contract
  - made helper cache EGARCH-aware so it no longer replays prepended context
    for EGARCH continuity
  - kept degenerate parameter traces blocked from model-facing training

- `IN_PROGRESS` Add workflow validation guards for helper causality and degeneracy
  - `DONE` helper implementation fingerprint + contract metadata now force
    helper-cache/helper-output invalidation when helper code changes
  - `DONE` production validation now checks:
    - helper output meta exists
    - helper/cache contract version matches current code
    - helper/cache runtime-contract map matches current code
    - helper/cache implementation fingerprint matches current code
    - constant helper columns are absent
  - `PENDING` audit-artifact-driven causality gate
  - `PENDING` optional near-constant helper guard

- `DONE` Replace helper-cache full-memory build path with streaming writes
  - raw helper source scan is now limited to the minimal OHLCV + batch columns
  - helper chunk outputs are streamed directly into per-batch cache files
  - old warmup behavior is preserved by writing null helper rows for:
    - batches before helper output begins
    - the leading part of the first warmup-crossing batch
  - parity smoke artifact:
    - `test_output/htf_helper_cache_streaming_smoke/20260413_streaming_check`
  - implementation note:
    - `notebooks/notes/htf_helper_cache_streaming_memory_fix_2026-04-13.md`

- `READY` Re-run six-root walk-forward diagnostics after cleanup
  - compare helper usage and predictive quality before vs after

## Current Execution Slice

Current implementation scope:

1. block degenerate EGARCH parameter features
2. remove OU future fill in Python and Rust
3. add causal context buffer in helper cache chunk transforms
4. add source-backed comments
5. rerun targeted helper audits

Items intentionally left for the next slice:

- workflow-level validation guards
- helper artifact rebuild on the full HTF corpus
- six-root diagnostic rerun

## Validation Snapshot

- `DONE` Python compile checks passed for all touched Python modules
- `DONE` Rust OU unit tests passed
- `DONE` `riskyield_rust` rebuilt for the actual `ml_env` CPython 3.11 runtime
- `DONE` model loaders now exclude:
  - `H_4class_1_egarch_asymmetry`
  - `H_4class_1_egarch_persistence`
- `DONE` targeted OU runtime checks now show early rows remain `NaN` in both Python and Rust
- `DONE` helper causality audit rerun saved to:
  - `test_output/htf_helper_causality_audit/20260412_190909`
- `IN_PROGRESS` audit interpretation after current slice:
  - `OU` is now fully green in the helper causality audit after fixing `ou_reverting`
  - `Kalman` is now green under the explicit state-handoff contract
  - `Kalman` prefix audit passes
  - `Kalman` state-handoff audit passes
  - old Kalman raw-context replay is now treated as not applicable rather than a valid parity check
  - `EGARCH` is now green under the explicit streaming-state handoff contract
  - `EGARCH` prefix audit passes
  - `EGARCH` state-handoff audit passes
  - old EGARCH raw-context replay is now treated as not applicable rather than a valid parity check
  - latest audit rerun saved to:
    - `test_output/htf_helper_causality_audit/20260412_235309`
  - helper artifact validation now fails stale helper outputs built before the
    new contract metadata was introduced, which forces a rebuild instead of
    silently reusing outdated helper parquets
