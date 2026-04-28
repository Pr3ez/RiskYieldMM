# HTF EGARCH Streaming-State Implementation

Date: 2026-04-13

## Objective

Replace the old chunk-dependent EGARCH helper contract with a live-safe
streaming-state contract that works without lookahead and matches the HTF
workflow for:

- `8h/B`, `8h/C`
- `24h/B`, `24h/C`
- `7d/B`, `7d/C`

## Previous Problems

The previous EGARCH implementation had three blocking issues:

1. Python fallback used chunk-wide statistics.
   - full-chunk demeaning
   - full-chunk variance initialization
   - whole-chunk return standard deviation for leverage activity

2. Python and Rust did not implement the same exact semantics.

3. Helper-cache replayed prepended raw context for EGARCH, which is the wrong
   continuity contract once EGARCH is treated as a true stateful helper.

Source rationale:

- Nelson (1991):
  `https://econpapers.repec.org/RePEc:ecm:emetrp:v:59:y:1991:i:2:p:347-70`
- helper source-backed audit:
  `notebooks/notes/htf_helper_source_backed_validity_audit_2026-04-12.md`

## New Contract

`EGARCH` now uses explicit streaming-state handoff.

Train phase:

- `fit()` estimates `omega`, `alpha`, `gamma`, `beta`
- `fit()` stores the train-prefix mean return
- `fit()` runs the train prefix through the EGARCH recursion
- `fit()` stores the final train-end streaming state
- volatility thresholds are calibrated from the train-prefix feature output

Prediction phase:

- `transform()` starts from the stored train-end state
- each row consumes only the current return and prior carried state
- each row outputs the updated EGARCH state after assimilating the current row
- no future rows, no chunk-wide statistics, no replayed context rows

## Streaming State

The carried state is:

- `log_var`
- `vol_count`
- `vol_sum`
- `vol_sum_sq`
- `recent_shock_flags`

This is enough to keep continuous:

- `egarch_vol`
- `egarch_log_vol`
- `egarch_news_impact`
- `egarch_vol_zscore`
- `egarch_vol_regime`
- `egarch_leverage_active`

Blocked parameter traces remain blocked from model-facing training:

- `*_egarch_asymmetry`
- `*_egarch_persistence`

## Implementation Files

Python:

- `scripts/target_models/helpers/egarch.py`

Rust:

- `riskyield_rust/src/egarch.rs`
- `riskyield_rust/src/lib.rs`

Workflow integration:

- `scripts/feature_engineering/htf_helper_cache.py`
- `scripts/analysis/htf_helper_causality_audit.py`

## Validation

### Build and compile

- `cargo test egarch --lib` passed
- `maturin develop --release` passed
- Python compile checks passed

### Python vs Rust parity

Direct parity under the same carried state:

- max abs diff: `3.413314075828566e-11`
- mean abs diff: `1.4038722401223686e-12`

Final state parity:

- `log_var` diff near zero
- `vol_count` exact match
- `vol_sum` diff near zero
- `vol_sum_sq` diff near zero
- `recent_shock_flags` exact match

### Split-chunk parity

One-pass vs split-chunk state handoff:

- max abs diff: `0.0`

Rust unit test added:

- `test_streaming_state_handoff_matches_one_pass`

### Real-data causality audit

Audit output:

- `test_output/htf_helper_causality_audit/20260412_235309`

Result:

- `egarch prefix_all_pass=True`
- `egarch state_handoff_all_pass=True`

Context replay is no longer the EGARCH continuity contract, so the old
`with_context` comparison is intentionally not applicable.

### Helper-cache workflow smoke

Smoke path:

- `compute_helpers_walk_forward_raw(... helpers=['egarch'])`

Observed:

- correct row coverage
- correct row index continuity
- expected EGARCH feature columns returned

## Conclusion

`EGARCH` is now correct under the chosen live-safe contract:

- no lookahead
- explicit state continuity
- Python/Rust parity
- workflow integration aligned with helper-cache logic

Remaining helper-system work is now outside EGARCH itself:

- workflow-level validation guards
- helper artifact rebuild
- six-root diagnostics rerun
