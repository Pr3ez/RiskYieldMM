# HTF Complete-Batch Readiness Audit — 2026-04-13

## Correction

The earlier pre-fit audit counted warmup / incomplete batches.

That was too broad for the actual readiness question.

This audit uses only complete batches:

- `8h/B`, `8h/C`: batch `>= 43`
- `24h/B`, `24h/C`: batch `>= 15`
- `7d/B`, `7d/C`: batch `>= 4`

These cutoffs are the first helper-clean batches under the rebuilt helper contract.

Audit artifact:

- `test_output/htf_feature_null_constant_audit/20260413_complete_batches_only_audit.json`

## Result

After excluding warmup / incomplete batches:

- helper-family null issues disappear as blockers
- the remaining null-feature union drops to `10` features

Remaining features with nulls on complete batches:

- `C_N_bodySize_bnd`
- `C_N_lowerShadow_bnd`
- `C_N_upperShadow_bnd`
- `D_dist_bot5_low_w120`
- `S_M_longShortChange_med_pct`
- `S_M_longShortChange_short_pct`
- `S_N_longShortZscore_long_zsc`
- `S_N_longShortZscore_xlong_zsc`
- `X_D_longShortRetPressure_long_pct`
- `X_D_longShortRetPressure_xlong_pct`

## Root-Level Summary

### `8h/B`

Remaining features:

- `D_dist_bot5_low_w120`
- `X_D_longShortRetPressure_xlong_pct`
- `S_N_longShortZscore_long_zsc`
- `S_N_longShortZscore_xlong_zsc`
- `X_D_longShortRetPressure_long_pct`
- `C_N_bodySize_bnd`
- `C_N_lowerShadow_bnd`
- `C_N_upperShadow_bnd`
- `S_M_longShortChange_short_pct`

### `8h/C`

Remaining features:

- `S_N_longShortZscore_long_zsc`
- `X_D_longShortRetPressure_xlong_pct`
- `S_N_longShortZscore_xlong_zsc`
- `X_D_longShortRetPressure_long_pct`
- `C_N_bodySize_bnd`
- `C_N_lowerShadow_bnd`
- `C_N_upperShadow_bnd`
- `S_M_longShortChange_med_pct`

### `24h/B`

Remaining features:

- `D_dist_bot5_low_w120`
- `S_N_longShortZscore_long_zsc`
- `S_N_longShortZscore_xlong_zsc`
- `X_D_longShortRetPressure_xlong_pct`
- `C_N_bodySize_bnd`
- `C_N_lowerShadow_bnd`
- `C_N_upperShadow_bnd`
- `X_D_longShortRetPressure_long_pct`

### `24h/C`

Remaining features:

- `X_D_longShortRetPressure_xlong_pct`
- `S_N_longShortZscore_long_zsc`
- `X_D_longShortRetPressure_long_pct`
- `S_N_longShortZscore_xlong_zsc`
- `C_N_bodySize_bnd`
- `C_N_lowerShadow_bnd`
- `C_N_upperShadow_bnd`
- `S_M_longShortChange_med_pct`
- `S_M_longShortChange_short_pct`

### `7d/B`

Remaining features:

- `D_dist_bot5_low_w120`
- `X_D_longShortRetPressure_xlong_pct`
- `S_N_longShortZscore_long_zsc`
- `S_N_longShortZscore_xlong_zsc`
- `X_D_longShortRetPressure_long_pct`
- `C_N_bodySize_bnd`
- `C_N_lowerShadow_bnd`
- `C_N_upperShadow_bnd`
- `S_M_longShortChange_med_pct`
- `S_M_longShortChange_short_pct`

### `7d/C`

Remaining features:

- `C_N_bodySize_bnd`
- `C_N_lowerShadow_bnd`
- `C_N_upperShadow_bnd`

## Cause Categories

### 1. Feature-specific implementation defect

- `D_dist_bot5_low_w120`

Cause:

- still resets every batch because distance metrics use `family_bar_pos` for warmup gating

### 2. Candlestick zero-range handling

- `C_N_bodySize_bnd`
- `C_N_lowerShadow_bnd`
- `C_N_upperShadow_bnd`

Cause:

- these features divide by `(high - low)`
- when `high == low`, the denominator is replaced by `NaN`
- this is happening on real rows in complete batches

### 3. Localized long/short auxiliary coverage / rolling-window gaps

- `S_M_longShortChange_med_pct`
- `S_M_longShortChange_short_pct`
- `S_N_longShortZscore_long_zsc`
- `S_N_longShortZscore_xlong_zsc`
- `X_D_longShortRetPressure_long_pct`
- `X_D_longShortRetPressure_xlong_pct`

Cause:

- remaining nulls are sparse and batch-local
- they cluster in a small number of specific complete batches
- they are consistent with long/short-ratio source gaps or insufficient rolling context after a local source gap

## Decision

If the bar is:

- no nulls in model-facing features on complete trainable batches

then fitting should still wait.

But the blocker set is now much smaller and better defined:

- `1` distance feature defect
- `3` candlestick zero-range features
- `6` long/short-derived features with sparse localized nulls
