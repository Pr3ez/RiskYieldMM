# HTF Underused Feature Audit

Date: 2026-04-11

## Scope

Audit the merged HTF walk-forward diagnostics to find features that appear useful
on paper but are being ignored by the current CatBoost workflow.

Source root:

- `/media/przem/linux_data/RiskYieldMM (Copy)/test_output/htf_walkforward_diagnostics/20260411_153744_merged`

Generated audit root:

- `/media/przem/linux_data/RiskYieldMM (Copy)/test_output/htf_underused_feature_audit/20260411_204727`

Primary lens:

- `root_topk`
- `PredictionValuesChange`

This is the right lens because it reflects the strongest practical Step-2 view:

- winner plus near-winner action keys
- stable feature selection across steps
- directly comparable across all six roots

## What Was Measured

For each root:

- `selected_step_freq`
- `mean_importance`
- feature family
- null rate
- drift level / drift score
- policy-blocked flag
- suspicious flag

Outputs written by the audit:

- `all_features.csv|parquet`
- `suspiciously_underused_clean.csv|parquet`
- `expected_underused.csv|parquet`
- `family_summary.csv|parquet`
- `consistently_underused_clean.csv|parquet`
- `expected_feature_panel.csv|parquet`

## Main Result

The model is **not** broadly ignoring the core market-state feature stack.

The real underuse pattern is much narrower:

1. most of the **helper-state** feature family is barely used
2. raw `volume` is consistently underused across all roots
3. many classic indicators that look “low ranked” are **not** actually ignored
   - they are selected often
   - they just do not dominate importance

That distinction matters.

Low mean importance does **not** imply ignored.
The better indicator of “ignored” is low `selected_step_freq`.

## What Is Truly Being Ignored

### 1. Helper-state features

This is the strongest and cleanest pattern in the audit.

Consistently underused clean features across all six roots include many helper features:

- `H_4class_1_egarch_persistence`
- `H_4class_1_egarch_asymmetry`
- `H_4class_1_egarch_vol_regime`
- `H_4cl_1_cp_any`
- `H_4class_1_kalman_regime`
- `H_4class_1_ou_is_stationary`
- `H_4class_1_ou_halflife_regime`
- `H_4class_1_ou_reverting`
- `H_4class_1_kalman_innovation`
- `H_4class_1_kalman_pred_error`
- `H_4class_1_egarch_log_vol`
- `H_4cl_1_garch_vol_forecast`
- `H_4class_1_kalman_zscore`
- `H_4class_1_ou_kappa`
- `H_4class_1_ou_zscore`
- `H_4class_1_ou_zscore_abs`

Representative usage levels:

- `H_4class_1_egarch_persistence`: mean selected-step frequency `0.001554`
- `H_4class_1_egarch_asymmetry`: mean selected-step frequency `0.001554`
- `H_4class_1_kalman_regime`: mean selected-step frequency `0.008859`
- `H_4class_1_ou_is_stationary`: mean selected-step frequency `0.014296`

Interpretation:

- the helper block is mostly clean in the audit
- but the CatBoost walk-forward process is barely selecting most of it
- this suggests a **semantic mismatch**, not a null/drift problem

Important exception:

- `H_4cl_1_garch_persistence` is not uniformly dead
- it becomes important in weekly roots, especially `7d/B` and `7d/C`

So the helper family should not be dismissed entirely.
The correct reading is:

- most helper features look underused
- one small subset of persistence / volatility-state helpers still matters

### 2. Raw `volume`

`volume` is the only plain OHLCV feature that is consistently underused and clean across all six roots.

Selected-step frequency by root:

- `8h/B`: `0.127333`
- `8h/C`: `0.105333`
- `24h/B`: `0.092369`
- `24h/C`: `0.048667`
- `7d/B`: `0.062745`
- `7d/C`: `0.128968`

Mean importance stays near zero everywhere.

Interpretation:

- the model rarely wants raw volume itself
- it seems to prefer transformed volume-flow features instead

This is not necessarily a bug.
It may simply mean:

- `volume` is too crude
- `volumeRoc`, `volumeRatio`, `mfi`, `cmf`, `obv` already capture the useful part

## What Is Not Actually Being Ignored

Several feature families looked weak at first glance because their mean importance is modest, but they are selected in most steps.

That means the model still uses them as supporting features.

### Candlestick / direction features

Examples:

- `B_C_candleDirection_bin`
- `B_consecutiveUp_bnd`
- `B_consecutiveDown_bnd`
- `C_N_bodySize_bnd`
- `C_N_upperShadow_bnd`
- `C_N_lowerShadow_bnd`

These are selected frequently:

- often `0.61` to `0.93` selected-step frequency depending on root

So they are **not ignored**.
They are just not dominant drivers.

### RSI / CCI / classic oscillators

Examples:

- `M_N_rsi_short_bnd`
- `M_N_rsi_med_bnd`
- `M_N_rsi_long_bnd`
- `N_M_cci_short_zsc`
- `N_M_cci_med_zsc`

These are also selected often:

- RSI typically around `0.73` to `0.91`
- CCI typically around `0.81` to `0.95`

So again:

- not ignored
- just secondary to stronger structural and pressure features

### Volume-flow transformations

Examples:

- `L_M_N_volumeRoc_*`
- `L_N_volumeRatio_*`

These are selected frequently across all roots:

- usually around `0.70` to `0.92`

So the model is not rejecting volume information in general.
It is rejecting **raw volume**, not the transformed volume context.

## Root-Level Family Pattern

Family-level summary from the audit:

- the **helper** family is the lowest-usage family in every root
- everything else is materially more used

Representative mean selected-step frequency:

- `8h/B` helper: `0.103659`
- `8h/C` helper: `0.077922`
- `24h/B` helper: `0.067650`
- `24h/C` helper: `0.027829`
- `7d/B` helper: `0.051756`
- `7d/C` helper: `0.139350`

By contrast:

- funding families are usually `0.65+`
- volume-flow / OI families are usually `0.75+`
- trend / normalized-position / volatility families are usually `0.78+`
- weekly roots use most non-helper families above `0.83`

Interpretation:

- helper underuse is the main systematic anomaly
- core feature families are broadly engaged by the model

## What This Likely Means

### Likely expected underuse

These do **not** currently look like problems:

- candlestick-direction features with high selection but low mean weight
- RSI / CCI with high selection but modest average importance
- transformed volume-flow features with high selection but low average importance

They are functioning as secondary support features.

### Potentially real issue

These deserve investigation:

1. helper-state family underuse
   - especially Kalman / OU / changepoint / EGARCH regime-state outputs
   - they are mostly clean but barely selected

2. raw `volume`
   - consistently ignored across all roots
   - maybe fine, but worth explicitly deciding whether to keep as a base feature

## Recommended Interpretation

The correct conclusion is:

- there is **not** a broad feature-importance failure where the model ignores the whole classical technical stack
- there **is** a narrow underuse issue centered on the helper-state family
- `volume` is the only core plain-market feature that is consistently neglected

So if we want to improve the feature set, the most useful next questions are:

1. Are most helper features semantically mismatched to `1m / target_4class`?
2. Should helper features be redesigned, thinned, or grouped differently?
3. Is raw `volume` redundant enough to remove, or should it stay as a harmless base column?

## Bottom Line

The model is mostly using the feature space as expected.

What looks genuinely underused:

- most helper-state features
- raw `volume`

What only looks weak but is still actively used:

- candlestick / direction features
- RSI / CCI
- volume-flow transforms
- many secondary momentum / normalization features

So the next feature-quality investigation should focus on the helper block first, not on the classical indicator families.
