# HTF Final Output Data Quality Audit

Date: 2026-03-27

## Scope

This audit checks the produced HTF artifacts for missing-value issues in auxiliary-source-derived features, with emphasis on funding-related features in the final outputs.

Primary audited outputs:

- `data/htf_with_helpers/1m/target_4class`
- `data/htf_with_helpers_shift4h/1m/target_4class`
- `data/htf_with_helpers_24h/1m/target_4class`
- `data/htf_with_helpers_24h_shift12h/1m/target_4class`
- `data/htf_with_helpers_7d/1m/target_4class`
- `data/htf_with_helpers_7d_shift84h/1m/target_4class`
- legacy 8h helper outputs:
  - `data/htf_with_helpers/15m/target_4class`
  - `data/htf_with_helpers_shift4h/15m/target_4class`

Upstream source context checked from `fetchingByBit`:

- `funding-rate-bybit-linear/btcusdt_funding_rate.parquet`
- `mark-price-1m-bybit-linear/btcusdt_mark.parquet`
- `index-price-1m-bybit-linear/btcusdt_index.parquet`
- `premium-price-1m-bybit-linear/btcusdt_premium.parquet`
- `open-interest-5m-bybit-linear/btcusdt_oi.parquet`
- `long-short-ratio-1h-bybit-linear/btcusdt_ls_ratio.parquet`

## What Is Present In Final Outputs

The final helper outputs do contain the new auxiliary-derived feature set. Relevant columns observed in final output batches include:

- Open interest derived:
  - `L_M_N_S_oiPctChange_pct`
  - `L_N_volOiRatio_rat`
  - `L_M_N_S_oiRoc_*`
- Funding derived:
  - `F_I_fundingCumulative_*`
  - `F_I_T_fundingMa_*`
  - `F_I_N_S_fundingZscore_*`
- Long/short derived:
  - `S_longShortRatio_rat`
  - `S_M_longShortChange_*`
  - `S_N_longShortZscore_*`
- Derivatives price derived:
  - `D_F_basis_pct`
  - `D_N_markCloseDeviation_pct`
  - `D_F_T_premiumMa_*`
  - `D_F_N_S_premiumZscore_*`
- Composite auxiliary features:
  - `X_D_oiRetPressure_*`
  - `X_D_basisRetPressure_*`
  - `X_D_fundingBasisPressure_*`
  - `X_D_longShortRetPressure_*`

So this is not a case of the auxiliary feature blocks being absent. The issue is missingness inside specific derived columns.

## Upstream Source Reality

### Funding

- Funding source cadence is stable and complete:
  - first timestamp: `2021-01-01 00:00 UTC`
  - last timestamp: `2026-03-05 16:00 UTC`
  - cadence: exactly `480` minutes for all `5669` gaps

Conclusion:

- funding source availability itself is not the problem

### Mark / Index / Premium 1m sources

- All three start at `2021-01-01 00:01 UTC`, not `00:00 UTC`
- All three contain repeated `2` minute gaps:
  - `2712` two-minute gaps across history

Exact final-output missing timestamps such as:

- `2021-01-01 16:41 UTC`
- `2026-03-04 16:14 UTC`

do not exist in the raw mark/index feeds, while adjacent `-1` minute and `+1` minute rows do exist.

Conclusion:

- scattered `basis` / `markCloseDeviation` missing rows are inherited from upstream mark/index sparsity

### Open interest 5m source

- starts at `2021-01-01 00:05 UTC`
- mostly `5` minute cadence
- also contains `2699` ten-minute gaps and one `25` minute gap

### Long/short ratio 1h source

- starts at `2021-01-01 00:00 UTC`
- mostly `60` minute cadence
- also contains irregular `120`, `180`, `300`, and `1380` minute gaps

## Final Output Missingness Summary

### 1m final helper outputs

Notable missingness rates:

- `8h / B / 1m`
  - `F_I_N_S_fundingZscore_long_zsc`: `403,844 / 1,360,635` = `29.68%`
  - `D_F_N_S_premiumZscore_long_zsc`: `325,456 / 1,360,635` = `23.92%`
  - `X_D_fundingBasisPressure_long_pct`: `325,582 / 1,360,635` = `23.93%`
  - `D_F_basis_pct`: `1,358 / 1,360,635` = `0.0998%`
  - `D_N_markCloseDeviation_pct`: `1,358 / 1,360,635` = `0.0998%`

- `8h / C / 1m`
  - `F_I_N_S_fundingZscore_long_zsc`: `1,360,560 / 1,360,560` = `100%`
  - `D_F_N_S_premiumZscore_long_zsc`: `325,666 / 1,360,560` = `23.94%`
  - `X_D_fundingBasisPressure_long_pct`: `325,540 / 1,360,560` = `23.93%`
  - `D_F_basis_pct`: `1,357 / 1,360,560` = `0.0997%`

- `24h / B / 1m`
  - `F_I_N_S_fundingZscore_long_zsc`: `52.90%`
  - `D_F_N_S_premiumZscore_long_zsc`: `23.93%`
  - `X_D_fundingBasisPressure_long_pct`: `23.92%`

- `24h / C / 1m`
  - `F_I_N_S_fundingZscore_long_zsc`: `76.79%`
  - `D_F_N_S_premiumZscore_long_zsc`: `23.93%`
  - `X_D_fundingBasisPressure_long_pct`: `23.94%`

- `7d / B / 1m`
  - `F_I_N_S_fundingZscore_long_zsc`: `62.92%`
  - `D_F_N_S_premiumZscore_long_zsc`: `23.91%`
  - `X_D_fundingBasisPressure_long_pct`: `23.91%`

- `7d / C / 1m`
  - `F_I_N_S_fundingZscore_long_zsc`: `66.77%`
  - `D_F_N_S_premiumZscore_long_zsc`: `23.93%`
  - `X_D_fundingBasisPressure_long_pct`: `23.93%`

Small missingness items:

- `F_I_fundingCumulative_short_pct`: `1` row only
- `F_I_T_fundingMa_short_pct`: `1` row only
- `S_longShortRatio_rat`: `1` row only
- `L_M_N_S_oiRoc_short_pct`: `1-66` rows depending on root

These are normal startup / shift effects, not the main issue.

### 15m legacy helper outputs

- `8h / B / 15m`
  - `F_I_N_S_fundingZscore_long_zsc`: `33.80%`
  - `D_F_N_S_premiumZscore_long_zsc`: `1.58%`
  - `X_D_fundingBasisPressure_long_pct`: `1.56%`

- `8h / C / 15m`
  - `F_I_N_S_fundingZscore_long_zsc`: `100%`
  - `D_F_N_S_premiumZscore_long_zsc`: `1.56%`
  - `X_D_fundingBasisPressure_long_pct`: `1.56%`

## What Is Expected vs What Is A Real Issue

## Expected / Explainable

### A. One-row and tiny prefix warmup gaps

Examples:

- `F_I_fundingCumulative_short_pct`
- `F_I_T_fundingMa_short_pct`
- `S_longShortRatio_rat`
- `L_M_N_S_oiRoc_short_pct`

Reason:

- first-difference or rolling window startup
- shifted-family first-row effects

These are not concerning.

### B. Long/short ratio z-score early-history gaps

Examples:

- `S_N_longShortZscore_long_zsc`

Pattern:

- tiny fraction of rows
- concentrated in early history only
- tied to sparse / irregular `1h` long-short source coverage and z-score warmup

This is acceptable unless we want stricter early-history cleaning.

## Real Issues / Design Problems

### Issue 1. Funding z-score is effectively unusable for shifted `8h/C`

Affected columns:

- `F_I_N_S_fundingZscore_long_zsc`
- likely the same logic also affects the xlong funding z-score family

Observed:

- `8h / C / 1m`: `100%` missing
- `8h / C / 15m`: `100%` missing

This is **not** a missing-fetch problem.

Evidence:

- funding source is complete and regular at `8h` cadence
- the same feature is already largely missing in the feature stage, before helper materialization
- by `family_bar_pos`, the shifted `8h/C` final outputs keep only positions `0..239`, and all of those rows are missing for `F_I_N_S_fundingZscore_long_zsc`

Reason:

- funding is broadcast from an `8h` stepwise source
- `_compute_funding_zscore()` uses rolling std and turns zero-std windows into `NaN`
- the shifted `4h` label window lives entirely inside one constant funding plateau, so rolling std stays zero in the retained final rows

Conclusion:

- this is a **feature-design mismatch with the retained label window**, not a broken join
- for `8h/C`, the long funding z-score currently contributes no usable signal

### Issue 2. Funding z-score has very high missingness even outside shifted `8h/C`

Affected roots:

- `8h/B/1m`: `29.68%`
- `24h/B/1m`: `52.90%`
- `24h/C/1m`: `76.79%`
- `7d/B/1m`: `62.92%`
- `7d/C/1m`: `66.77%`
- `8h/B/15m`: `33.80%`

Reason:

- same root cause as above: low-frequency stepwise funding source plus rolling z-score with zero-std windows

Conclusion:

- this is a broader design-quality problem for funding z-score features, not just a shifted-family edge case

### Issue 3. `basis` and `markCloseDeviation` inherit scattered upstream 1m source holes

Affected columns:

- `D_F_basis_pct`
- `D_N_markCloseDeviation_pct`

Observed:

- around `0.10%` missing in final `1m` outputs
- missing rows are scattered across the full history, not only at the prefix

Evidence:

- exact missing timestamps in final outputs are absent from raw `mark` and `index` 1m files
- nearby `-1` and `+1` minute source rows do exist

Conclusion:

- this is a real data-quality issue in final outputs
- root cause is upstream source sparsity propagating through native `1m` left-joins

### Issue 4. Premium z-score and funding-basis composite have rolling-window-amplified missingness

Affected columns:

- `D_F_N_S_premiumZscore_long_zsc`
- `X_D_fundingBasisPressure_long_pct`

Observed:

- about `23.9%` missing in final `1m` outputs
- about `1.56%` missing in final `15m` outputs

Reason:

- premium/mark/index feeds contain scattered one-minute holes
- `_compute_premium_zscore()` uses full rolling windows
- `_rolling_mean_product()` also uses full rolling windows
- one sparse missing source point can poison a long trailing window of derived outputs

Conclusion:

- this is not just “premium source has 23.9% missing”
- it is **rolling-window amplification** of sparse upstream gaps

## Important Non-Issue

I did not find evidence that helper materialization or optimization introduced these auxiliary missing values.

For the key funding issue:

- the same pattern is already present in `data/htf_features/1m`
- final helper outputs inherit it

So this is not a helper-stage corruption problem.

## Recommendations

### Priority 1

Decide what to do with funding z-score features.

Options to evaluate:

- drop funding z-score features from final modeling sets where they are structurally unusable
- redefine them on a funding-event cadence instead of minute-level broadcast windows
- compute them over change points rather than over repeated broadcast values

### Priority 2

Add a formal HTF artifact quality audit step after feature generation and before optimization/helper materialization.

It should flag:

- columns above a missingness threshold
- columns that are `100%` missing within any regime/family/tf scope
- columns whose missingness is spread across history instead of prefix-only

### Priority 3

Decide whether small native-source gaps in mark/index/premium should be tolerated or patched.

Possible directions:

- keep current behavior and document it
- bounded one-step fill for isolated one-minute source holes
- source-gap repair before HTF feature computation

No fix is recommended yet without deciding the acceptable market-data semantics.

## Recommended Next Task

Open a follow-up implementation task focused on auxiliary-feature quality:

1. add an automated missingness audit
2. redesign or retire funding z-score features
3. decide policy for sparse mark/index/premium holes

