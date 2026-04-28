# HTF Helper Feature Usage Audit

Date: 2026-04-12

## Scope

Investigate why HTF helper features are underused by the CatBoost walk-forward
models across the six current roots:

- `8h/B`
- `8h/C`
- `24h/B`
- `24h/C`
- `7d/B`
- `7d/C`

Goal:

- verify whether helpers are broken during computation or loading
- determine whether underuse is caused by nulls / missingness
- identify any degenerate helper features
- explain why some helpers matter while most do not

## Artifacts

Audit output:

- `/media/przem/linux_data/RiskYieldMM (Copy)/test_output/htf_helper_feature_audit/20260412_201750`

Main files:

- `root_summary.parquet`
- `helper_feature_detail.parquet`
- `degenerate_helpers.parquet`
- `selected_helpers.parquet`
- `helper_kind_summary.parquet`

Driver script:

- `/media/przem/linux_data/RiskYieldMM (Copy)/scripts/analysis/htf_helper_feature_audit.py`

Reference diagnostics root:

- `/media/przem/linux_data/RiskYieldMM (Copy)/test_output/htf_walkforward_diagnostics/20260411_153744_merged`

## What Was Checked

1. Whether helper columns are present in saved `htf_with_helpers*` batches.
2. Whether helper columns are admitted into CatBoost model features.
3. Whether helper columns carry nulls on the evaluated walk-forward horizons.
4. Whether helper columns are degenerate or near-constant.
5. Whether Stage-2 actually selects any helper columns.
6. Whether the helper implementation itself explains the observed behavior.

## Verified Facts

### 1. Helpers are not missing from the saved feature roots

Every root still contains all `43` helper columns in the final
`htf_with_helpers* / 1m / target_4class` batches.

Latest batch checks also showed:

- `43/43` helper columns present
- `0/43` helper columns with nulls

across all six roots.

### 2. Helpers are not being dropped before CatBoost sees them

The current CatBoost loader still exposes all `43` helper columns as model
features in every root.

Model feature counts on latest batches:

- total model features: `172`
- helper features inside model set: `43`

for all six roots.

So the low helper usage is **not** caused by the loader excluding them.

### 3. Helper missingness is not the cause on the evaluated horizons

Across the same evaluated horizons used by the recent walk-forward runs:

- `8h` roots: last `500` batches
- `24h` roots: last `500` batches
- `7d` roots: last `170` batches

the maximum helper null rate was `0.0` for every root.

So the current underuse is **not** a warmup/null issue.

## Main Findings

## A. The helper block is not broken end to end

The pipeline is working in the operational sense:

- helpers are computed
- helpers are saved
- helpers are loaded into the model feature set
- some helpers are selected and used

This is confirmed most clearly in weekly roots:

- `7d/B` strongly uses `H_4cl_1_garch_persistence`
- `7d/C` strongly uses:
  - `H_4cl_1_garch_persistence`
  - `H_4class_1_egarch_vol`
  - `H_4class_1_egarch_vol_zscore`
  - `H_4class_1_ou_phi`

So the answer is **not** “helpers failed to compute”.

## B. Part of the helper block is degenerate by design

The clearest issue is that some helper features are effectively constant across
all roots.

Observed in the audit:

- `H_4class_1_egarch_asymmetry`
  - unique values: `1`
  - value: `0.0`
  - constant in all six roots
- `H_4class_1_egarch_persistence`
  - unique values: `1`
  - value: `0.95`
  - constant in all six roots

This behavior is explained directly by the helper implementation:

- `scripts/target_models/helpers/egarch.py`
  - `asymmetry_arr = np.full(n_samples, self._gamma)`
  - `persistence_arr = np.full(n_samples, self._beta)`

So those outputs are constant by construction after each fit.

The same pattern exists in other helpers too:

- `scripts/target_models/helpers/ou.py`
  - `phi_arr`, `kappa_arr`, `halflife_arr`, `is_stationary_arr`, and
    `halflife_regime_arr` are filled as constant arrays from the fitted state
- `scripts/target_models/helpers/garch.py`
  - `persistence = np.full(n_samples, self._alpha + self._beta)`

This means a large fraction of the helper block is made of:

- refit-parameter features
- discrete regime indicators
- piecewise-constant state summaries

rather than fully dynamic per-row signals.

That makes many helper columns weak candidates for a high-frequency `1m`
classification target.

## C. Helper inputs are narrow compared to the final CatBoost feature space

Helpers are computed from a small raw input basis in:

- `scripts/feature_engineering/htf_helper_cache.py`
  - `prepare_raw_features_for_helpers(...)`

That function uses:

- log returns
- rolling volatility
- `close`
- optional raw `open/high/low/volume`

It does **not** use the richer HTF engineered stack that the final CatBoost
models see.

So helper features are trying to summarize state from a much smaller information
set than the final model receives.

This strongly supports the interpretation that helper underuse is largely a
**semantic mismatch**:

- helpers summarize coarse volatility / mean-reversion / regime state
- CatBoost is optimizing a `1m / target_4class` directional problem using a far
  richer direct feature stack

The richer direct features often dominate.

## D. Underuse is root-specific, not uniform

Helper usage is weakest in:

- `24h/C`
  - mean helper selected-step frequency: `0.027829`
  - helpers selected in more than `10%` of steps: `0`

Helper usage is strongest in:

- `7d/C`
  - mean helper selected-step frequency: `0.139350`
  - helpers selected in more than `10%` of steps: `25`
  - helpers selected in more than `20%` of steps: `13`

`8h` roots are in between:

- `8h/B`
  - helper selected-step frequency mean: `0.103659`
- `8h/C`
  - helper selected-step frequency mean: `0.077922`

So helpers are not globally dead.
They are mainly useful in the weekly regime, and much less useful in the daily
and especially `24h/C` root.

## E. The helpers that survive are a small subset

Most-used helper features across the current roots:

- `H_4cl_1_garch_persistence`
- `H_4class_1_egarch_vol`
- `H_4class_1_egarch_vol_zscore`
- `H_4class_1_ou_phi`
- `H_4cl_1_garch_vol_zscore`
- `H_4cl_1_cusum_ret_pos`
- `H_4cl_1_cusum_ret_neg`

So the helper block is not useless.
It just collapses to a much smaller useful subset than the nominal `43`
features suggest.

## Interpretation

The current helper underuse has four causes, in order of importance:

1. **Degenerate constant outputs**
   - especially `egarch_asymmetry` and `egarch_persistence`
2. **Piecewise-constant parameter features**
   - many helper outputs are fitted-state summaries, not rich per-row dynamics
3. **Narrow helper input basis**
   - helpers are built from raw returns / volatility / OHLCV only
4. **Root-specific target mismatch**
   - helpers fit weekly roots better than `24h` and some `8h` roots

What it is **not**:

- not a helper cache corruption issue
- not a missing-column issue
- not a null/warmup issue on the current evaluated horizons
- not a CatBoost loader exclusion issue

## Recommended Next Actions

### 1. Remove globally degenerate helper columns from model-facing training

At minimum, exclude:

- `H_4class_1_egarch_asymmetry`
- `H_4class_1_egarch_persistence`

Potentially also review other helper outputs that are effectively constant or
near-constant over the evaluated horizons.

### 2. Split helper outputs into two conceptual groups

Treat separately:

- dynamic helper signals
  - `egarch_vol`, `egarch_vol_zscore`, `garch_vol_zscore`,
    `cusum_ret_*`, `kalman_*`, etc.
- fitted-state parameters
  - `phi`, `kappa`, `halflife`, `persistence`, `asymmetry`, regime flags

The first group is much more plausible for direct predictive use.

### 3. Prioritize weekly helper analysis first

The strongest evidence that helpers matter is in:

- `7d/B`
- `7d/C`

So helper redesign or pruning experiments should start there.

### 4. Reconsider helper contract for `24h/C`

`24h/C` is the clearest case where helpers are available but practically unused.

That root should be treated as a strong candidate for:

- helper pruning
- helper redesign
- or helper-family downweighting in model development

## Bottom Line

Helper features did **not** break during computation.

But a meaningful part of the helper block is too coarse or degenerate to be
useful for the current `1m / target_4class` modeling task.

The real issue is:

- not missing helpers
- not null helpers
- but helper design and semantic fit

Weekly roots still get real value from a small volatility-state subset.
The rest of the helper stack should be treated as redesign-or-prune territory.
