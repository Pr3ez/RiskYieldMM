# HTF Helper Feature Cleanup Plan

Date: 2026-04-12

## Goal

Define a clean remediation plan for HTF helper features so that:

1. helper outputs are strictly causal
2. helper outputs do not introduce lookahead bias
3. degenerate or misleading helper features do not enter model-facing training
4. the remaining helper block is easier to reason about and evaluate

This plan is based on:

- current helper generation path
- current helper audit results
- merged walk-forward diagnostics

Relevant notes:

- `/media/przem/linux_data/RiskYieldMM (Copy)/notebooks/notes/htf_helper_feature_usage_audit_2026-04-12.md`
- `/media/przem/linux_data/RiskYieldMM (Copy)/notebooks/notes/htf_underused_feature_audit_2026-04-11.md`

Relevant code:

- `scripts/feature_engineering/htf_helper_cache.py`
- `scripts/target_models/helpers/ensemble.py`
- `scripts/target_models/helpers/ou.py`
- `scripts/target_models/helpers/garch.py`
- `scripts/target_models/helpers/egarch.py`

## Clean Causal Contract

For a helper feature to be valid in model-facing training, row `t` must satisfy:

1. it uses only information available at or before row `t`
2. it does not use any statistic computed from future rows in the same transform chunk
3. it is not backfilled from a later computed row
4. it is not a globally constant artifact with no predictive content
5. it is not merely a batch/era identifier disguised as model state

For this HTF workflow, that means:

- fitting on `X_train` and predicting on `X_chunk` is acceptable
- but every feature value inside `X_chunk` must still be computed causally per row
- chunk-level transform code cannot rely on full-chunk means, variances, or future fills if we want strict no-lookahead semantics

## What Helpers Should Be

The helper block should provide one of two valid signal types:

### A. Dynamic row-level state signals

Examples:

- current conditional volatility
- current vol z-score
- current innovation / shock
- current changepoint pressure
- current filtered deviation
- current state probability

These are the strongest helper candidates because they can vary meaningfully at
the row level while remaining causal.

### B. Slow structural state summaries

Examples:

- estimated persistence
- OU half-life
- regime label

These are only acceptable if:

- they are recomputed from the historical prefix only
- their causal semantics are explicit
- they add signal beyond the richer direct feature stack

These should be treated as second-class helper outputs, not assumed useful by
default.

## Exact Problems Found

## 1. The helper input basis is too narrow

Helpers are currently built from:

- returns
- rolling volatility
- close
- optional raw OHLCV

Code:

- `scripts/feature_engineering/htf_helper_cache.py:110`

This is much narrower than the final HTF feature stack used by CatBoost.

Consequence:

- many helper features are trying to summarize regime/volatility state from a
  smaller information set than the final direct features already expose
- helper outputs become easy to dominate with richer direct market-state
  features

This is not a leakage bug, but it is a design mismatch.

## 2. Several helper outputs are constant or near-constant by design

Examples already confirmed in current saved roots:

- `H_4class_1_egarch_asymmetry`
- `H_4class_1_egarch_persistence`

Implementation source:

- `scripts/target_models/helpers/egarch.py:245`

The same pattern exists in other helpers:

- OU constant fitted-state arrays
  - `scripts/target_models/helpers/ou.py:232`
- GARCH constant persistence
  - `scripts/target_models/helpers/garch.py:285`

Consequence:

- these features are validly causal in a narrow sense
- but they are poor model features because they are piecewise constant or
  globally constant
- they inflate feature count and complicate interpretation

## 3. The helper block mixes dynamic signals with fitted-parameter artifacts

Right now the model-facing helper set does not distinguish between:

- dynamic causal state features
- fitted parameter summaries
- discrete regime flags

These are very different feature types, but they are all exposed uniformly as
`H_*` model features.

Consequence:

- weak fitted-state artifacts travel together with genuinely useful dynamic
  helper signals
- diagnostics become noisier
- pruning decisions are harder to reason about

## 4. Strict no-lookahead semantics are not fully guaranteed by the Python fallback implementations

The runtime environment currently reports:

- `egarch HAS_RUST = True`
- `garch HAS_RUST = True`
- `ou HAS_RUST = True`

So production HTF helper generation is likely using Rust transforms in the
current environment.

However, the Python fallback code still exposes strict-causality risks and
therefore the contract is not clean enough:

### EGARCH fallback

- `scripts/target_models/helpers/egarch.py:454`
  - computes `mean_ret = np.nanmean(returns)` inside the transform path

If `returns` is the full transform chunk, that is not strictly per-row causal.

### OU fallback

- `scripts/target_models/helpers/ou.py:285`
  - fills early z-score rows using `first_z` from the first later valid index

That is an explicit forward fill from a future row within the transform chunk.

### EVT fallback

- similar early-fill behavior exists in `scripts/target_models/helpers/evt_pot.py`

Consequence:

- even if Rust is active today, the helper contract is not clean enough on the
  reference implementation side
- we do not yet have a formal causal equivalence test proving the Rust path is
  row-causal

This is the main reason a cleanup plan must include validation, not only feature
pruning.

## 5. Current documentation is out of date for the HTF helper stack

`scripts/target_models/ARCHITECTURE.md` still describes a broader multi-helper
system centered on HMM / IF / interaction-style workflows, while current HTF
helper generation uses:

- `ou`
- `garch`
- `cusum`
- `kalman`
- `egarch`

from:

- `scripts/feature_engineering/htf_helper_cache.py:17`

Consequence:

- it is harder to reason about current helper design using the existing docs
- remediation should produce a current HTF-specific helper contract doc

## What Is Not Wrong

The following have been ruled out by audit:

- helpers are not missing from the saved `htf_with_helpers*` roots
- helpers are not being dropped by the CatBoost loader
- helper nulls are not the reason for current underuse on evaluated horizons
- the helper cache / helper materialization path is not silently corrupting the
  columns

So the current problem is fundamentally about:

- helper feature design
- helper feature semantics
- strict causality guarantees

## Audit-Informed Execution Plan

The source-backed audit changed the plan materially.

Current certified status:

- keep now:
  - all `CUSUM` features
  - dynamic `GARCH` features
- keep only as coarse optional context:
  - `garch_persistence`
- block now from model-facing training:
  - `H_4class_1_egarch_asymmetry`
  - `H_4class_1_egarch_persistence`
- cleanup required before further model use:
  - all `OU` features
  - all `Kalman` features
  - dynamic `EGARCH` features

So the plan is no longer “review all helpers equally.”  
It is now:

1. freeze the certified-safe subset,
2. block the proven-bad or degenerate subset,
3. repair the not-yet-certifiable families,
4. rerun diagnostics and only then decide what to bring back.

## Tracked TODO List

### TODO 0. Freeze the current helper contract

- write one current HTF helper contract note covering:
  - helper families in production
  - which features are model-facing
  - which are diagnostic-only
  - strict no-lookahead definition
  - live-parity requirement

Acceptance:

- one canonical helper contract note exists
- it matches the current HTF workflow and audit verdicts

### TODO 1. Lock the currently safe subset

- explicitly mark `CUSUM` features as allowed
- explicitly mark dynamic `GARCH` features as allowed
- mark `garch_persistence` as safe-but-coarse, not a default priority feature

Safe-now list:

- `cusum_ret_pos`
- `cusum_ret_neg`
- `cusum_vol_pos`
- `cusum_vol_neg`
- `cp_ret_up`
- `cp_ret_down`
- `cp_vol_up`
- `cp_vol_down`
- `cp_any`
- `cp_magnitude`
- `days_since_cp`
- `cp_count_21`
- `garch_cond_vol`
- `garch_vol_forecast`
- `garch_vol_zscore`
- `garch_vol_shock`
- `garch_vol_regime`
- `garch_vol_change`
- `garch_vol_ratio`
- `garch_persistence` as optional coarse context only

Acceptance:

- safe subset is documented
- loaders / training policy can distinguish it from uncertified helpers

### TODO 2. Block immediately bad or degenerate helper features

- exclude from model-facing training:
  - `H_4class_1_egarch_asymmetry`
  - `H_4class_1_egarch_persistence`
- scan for any additional helper columns with:
  - `n_unique <= 1`
  - effectively zero variance
  - globally degenerate behavior across evaluated roots

Important:

- do **not** mass-remove all fitted-state features
- `garch_persistence` must be handled separately because it is weak/coarse, not invalid

Acceptance:

- blocked columns are absent from model-facing feature loaders
- exclusion is tested on a real helper batch

### TODO 3. Add strict helper causality tests to the codebase

Promote the new audit logic into repeatable tests:

1. prefix invariance
   - helper at row `t` from `[:t]` must match the same row produced in a longer chunk
2. no future fill
   - early rows cannot be filled from the first later valid value
3. context invariance after enough history
   - late rows should converge when enough historical context is present
4. batch-vs-live parity
   - chunk generation with carry-forward state should match a continuous stream
5. Rust-vs-reference consistency
   - Rust output should match a strict causal reference implementation

Acceptance:

- one helper-causality test suite exists
- each helper family has explicit pass/fail status

### TODO 4. Fix OU helper implementation

Problems confirmed by audit:

- early `phi/kappa/halflife/is_stationary/halflife_regime` rows are filled from a later valid row
- early `zscore/zscore_abs` rows are filled from a later valid row

Required changes:

- remove future-to-past fill in Rust and Python implementations
- output neutral / missing / explicit insufficient-history values until enough trailing history exists
- re-audit prefix invariance after the fix

Decision to make after fix:

- whether `ou_phi`, `ou_kappa`, `ou_halflife`, `ou_is_stationary`, `ou_halflife_regime` belong in model-facing training at all

Acceptance:

- OU passes prefix causality audit
- no early future-fill remains

### TODO 5. Fix Kalman helper implementation

Problems confirmed by audit:

- Rust path cold-starts each transform chunk instead of carrying forward the trained end state
- `kalman_zscore` and `kalman_regime` are especially unstable

Required changes:

- add explicit state handoff across chunks
- make chunk transform reproduce a continuous live stream
- re-audit prefix and context invariance

Acceptance:

- Kalman chunk outputs match a continuous stateful stream within tolerance
- `kalman_zscore` and `kalman_regime` stabilize under the audit

### TODO 6. Fix dynamic EGARCH implementation

Problems confirmed by audit:

- dynamic `EGARCH` features are not prefix-invariant
- chunk-boundary instability remains even later in the chunk
- constant fitted parameters are safe but weak and already degenerate in current data

Required changes:

- keep `egarch_asymmetry` and `egarch_persistence` blocked
- redesign dynamic EGARCH transform so:
  - chunk outputs are prefix-causal
  - chunk outputs are stable with enough context
  - batch generation can be reproduced live

Features affected:

- `egarch_vol`
- `egarch_log_vol`
- `egarch_news_impact`
- `egarch_vol_zscore`
- `egarch_vol_regime`
- `egarch_leverage_active`

Acceptance:

- dynamic EGARCH passes causality/reproducibility audit
- or it remains blocked if it cannot be made reliable

### TODO 7. Add validation guards in the HTF workflow

At helper artifact validation time, add checks for:

- constant helper columns
- near-constant helper columns
- very low effective uniqueness
- suspicious chunk-boundary instability
- helper columns that fail the causality audit

This should live alongside the current HTF feature-quality checks so bad helpers are caught before walk-forward runs.

Acceptance:

- helper validation fails loudly on degenerate or non-causal helper outputs

### TODO 8. Re-run walk-forward diagnostics after helper cleanup

After TODO 1-7:

1. rerun helper generation if needed
2. rerun six-root walk-forward diagnostics
3. compare helper usage before/after
4. compare directional accuracy and coverage before/after
5. verify whether weekly helper value remains intact for `7d/B` and `7d/C`

Priority order:

1. `24h/C`
2. `8h/C`
3. `7d/B`
4. `7d/C`
5. then `8h/B` and `24h/B`

Acceptance:

- we have before/after diagnostics for all six roots
- helper usage becomes easier to interpret
- no uncertified helper family is silently back in the model

### TODO 9. Only then do deeper helper redesign

After the current families are clean:

- decide whether helper input basis should expand beyond:
  - returns
  - rolling volatility
  - close
  - raw OHLCV
- reconsider whether helper features should remain one flat `H_*` namespace
- split helper outputs into:
  - dynamic model-facing signals
  - fitted-state diagnostics

Acceptance:

- redesign is based on post-cleanup diagnostics, not on the current mixed state

## Short Operational Summary

What we do now:

- keep `CUSUM`
- keep dynamic `GARCH`
- block degenerate `EGARCH` parameter features
- fix `OU`
- fix `Kalman`
- fix dynamic `EGARCH`
- add tests and validation guards
- rerun full diagnostics

What we do not do now:

- do not drop all helpers
- do not trust `OU`, `Kalman`, or dynamic `EGARCH` in model-facing training until they pass the causality audit
- do not redesign the whole helper stack before the current families are made causal and live-reproducible
