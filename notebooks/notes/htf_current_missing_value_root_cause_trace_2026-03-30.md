# HTF Current Missing Value Root Cause Trace 2026-03-30

## Scope
- Trace the current live post-rerun null-heavy columns in final HTF helper outputs.
- Identify:
  - what is missing,
  - where it is first produced,
  - and the exact reason for the missingness.

## Method
- Use the finished live post-rerun artifacts only.
- Avoid root-wide OOM-prone scans.
- Trace representative live problem columns through:
  - `features`
  - `optimized`
  - `helpers`
- Then map each column to the exact feature definition and recompute on bounded raw-source slices where needed.

## Key Conclusion
The current missing values are **originated in the feature stage**, not created by helpers.

More precisely:
- `helpers` mostly preserve what `optimized` gives them
- `optimized` may increase or decrease null rate only because it keeps a label-gated subset of rows
- the actual null-producing logic is in the **feature formulas and source alignment rules**

So the missingness is not caused by:
- helper cache corruption
- helper materialization bugs
- resume logic corruption
- generic parquet writing problems

## Current Problem Families

### 1. Batch-local distance warmup nulls
Example live columns:
- `D_dist_bot5_low_w120`
- `D_dist_avg_high_w240`
- `D_dist_avg_low_w240`
- `D_dist_top5_high_w240`

Where produced:
- `scripts/feature_engineering/htf_multiregime_pipeline.py`
- inside `_compute_past_distance_metrics(...)`
- shared kernel in `scripts/feature_engineering/htf_kernels.py`

Exact reason:
- `_compute_past_distance_metrics` explicitly does:
  - `if bar_pos[i] < window: continue`
- so rows before the required in-batch lookback window are intentionally `NaN`

Why it becomes severe in final outputs:
- these `D_*` features are batch-local
- optimized/final outputs keep the front label-eligible part of the batch
- the warmup nulls are concentrated exactly in that front segment

Concrete evidence:
- `8h/B/1m` feature batch `0001`:
  - `D_dist_bot5_low_w120`: `120 / 480 = 25.00%` null
- `8h/B/1m` optimized batch `0001`:
  - `D_dist_bot5_low_w120`: `121 / 240 = 50.42%` null
- `8h/B/1m` helper batch `0001`:
  - `D_dist_bot5_low_w120`: `121 / 240 = 50.42%` null

Interpretation:
- feature stage creates the warmup nulls
- optimized/helper stages do not create them
- final outputs look worse because the saved row subset is front-loaded

### 2. Funding z-score nulls
Example live columns:
- `F_I_N_S_fundingZscore_long_zsc`
- `F_I_N_S_fundingZscore_xlong_zsc`

Where produced:
- `scripts/feature_engineering/compute_htf_features.py`
- `_compute_funding_zscore(df, n)`

Definition:
- `mu = fundingRate.rolling(n).mean()`
- `sigma = fundingRate.rolling(n).std()`
- `z = (fundingRate - mu) / sigma.replace(0, np.nan)`

Exact reason:
- `fundingRate` is broadcast from an `8h` stepwise source
- within long constant plateaus, rolling std becomes `0`
- the implementation replaces `0` std with `NaN`
- therefore any window containing only one funding value becomes undefined

This is not a missing-fetch problem.
It is a formula/source-cadence mismatch.

Exact recomputation proof:
- Live batch: `data/htf_features_7d/1m/batch_0002.parquet`
- feature nulls for `F_I_N_S_fundingZscore_long_zsc`: `5061`
- bounded raw-source recomputation nulls: `5061`

Interpretation:
- nulls are exactly reproducible from the current formula and raw funding feed

Additional practical reading:
- with a `240` minute window on an `8h = 480` minute stepwise source,
  roughly half the rows fall into zero-std windows
- that is why live null rates cluster around `~50%+`

### 3. Premium z-score xlong nulls
Example live column:
- `D_F_N_S_premiumZscore_xlong_zsc`

Where produced:
- `scripts/feature_engineering/compute_htf_features.py`
- `_compute_premium_zscore(df, n)`

Definition:
- rolling z-score over `premiumClose`
- for `1m`, `xlong = 480`

Exact reason:
- the raw `1m` premium feed has very small real timestamp holes
- the z-score uses a `480` row rolling window requiring a full valid window
- a single missing source minute invalidates up to `480` downstream rows

So the serious null rate is caused by **source-gap amplification**, not by many raw missing rows.

Concrete evidence:

#### `7d/B/1m` batch `0002`
- live feature nulls for `D_F_N_S_premiumZscore_xlong_zsc`: `4870`
- bounded raw-source recomputation nulls: `4870`
- raw premium source holes in the exact `480`-row context window set: `11`
  - this includes `10` missing minutes inside the batch range plus `1` in the pre-batch context

#### `24h/C/1m` batch `0002`
- live feature nulls: `802`
- bounded raw-source recomputation nulls: `802`
- raw premium holes in the exact context set: `2`

#### `8h/B/1m` batch `0001`
- live feature nulls: `480`
- bounded raw-source recomputation nulls: `480`
- reason here is start-of-history context absence:
  - there is no prior `480` minute context at dataset start
  - plus the earliest raw `1m` premium feed starts at `00:01`, not `00:00`

Interpretation:
- tiny raw source gaps are being multiplied by the long rolling window rule

### 4. Funding-basis pressure xlong nulls
Example live column:
- `X_D_fundingBasisPressure_xlong_pct`

Where produced:
- `scripts/feature_engineering/compute_htf_features.py`
- `_rolling_mean_product(fundingRate, basis, 480)`
- where `basis = (close - indexClose) / indexClose`

Exact reason:
- this column depends on `indexClose` through `basis`
- the raw `1m` index feed has the same tiny timestamp holes pattern as premium
- rolling mean uses a full `480` row valid window
- each missing `indexClose` minute invalidates up to `480` downstream rows

Exact recomputation proof:

#### `7d/B/1m` batch `0002`
- live feature nulls: `4870`
- bounded raw-source recomputation nulls: `4870`
- `basis` nulls in exact context set: `11`
- `indexClose` missing timestamps in exact context set: `11`

#### `24h/C/1m` batch `0002`
- live feature nulls: `802`
- bounded raw-source recomputation nulls: `802`
- context `indexClose` source holes: `2`

#### `8h/B/1m` batch `0001`
- live feature nulls: `480`
- bounded raw-source recomputation nulls: `480`
- at dataset start there is no full `480` row context, and the earliest raw `1m` index feed also starts at `00:01`

Interpretation:
- same amplification pattern as premium z-score
- but through `basis`, not `premiumClose`

## Stage Propagation Summary

### `8h/B/1m` batch `0001`
- feature:
  - `D_dist_bot5_low_w120`: `120 / 480`
  - `D_F_N_S_premiumZscore_xlong_zsc`: `480 / 480`
  - `F_I_N_S_fundingZscore_long_zsc`: `480 / 480`
  - `X_D_fundingBasisPressure_xlong_pct`: `480 / 480`
- optimized:
  - same three xlong/funding columns remain `100%` null
  - `D_dist_bot5_low_w120` becomes `121 / 240`
- helper:
  - same as optimized

### `24h/C/1m` batch `0002`
- feature:
  - `F_I_N_S_fundingZscore_long_zsc`: `723 / 1440`
  - `D_F_N_S_premiumZscore_xlong_zsc`: `802 / 1440`
  - `X_D_fundingBasisPressure_xlong_pct`: `802 / 1440`
- optimized:
  - `482 / 720`
  - `322 / 720`
  - `322 / 720`
- helper:
  - same as optimized

### `7d/B/1m` batch `0002`
- feature:
  - `F_I_N_S_fundingZscore_long_zsc`: `5061 / 10080`
  - `D_F_N_S_premiumZscore_xlong_zsc`: `4870 / 10080`
  - `X_D_fundingBasisPressure_xlong_pct`: `4870 / 10080`
- optimized:
  - `2412 / 5040`
  - `2436 / 5040`
  - `2436 / 5040`
- helper:
  - same as optimized

Interpretation:
- nulls start in `features`
- `optimized` changes rates only because row selection changes
- `helpers` preserve them

## Exact Root Cause Map

| Column family | First produced as null in | Exact cause |
| --- | --- | --- |
| `D_*` batch-local windows | feature stage | intentional batch-local warmup: `bar_pos < window` |
| `F_I_N_S_fundingZscore_*` | feature stage | rolling std on stepwise `8h` funding becomes `0`, replaced with `NaN` |
| `D_F_N_S_premiumZscore_xlong_zsc` | feature stage | tiny raw `1m` premium gaps amplified by `480`-row rolling full-window requirement |
| `X_D_fundingBasisPressure_xlong_pct` | feature stage | tiny raw `1m` index gaps amplified by `480`-row rolling full-window requirement |

## What This Means
- The current missingness is real and reproducible.
- It is not random corruption.
- It is not primarily a helper bug.
- It is not primarily an optimizer bug.
- It is mainly:
  - feature design vs retained-row mismatch (`D_*`)
  - stepwise-source z-score design mismatch (`funding zscore`)
  - long-window amplification of tiny raw source holes (`premium zscore`, `funding-basis pressure`)

## Next Actions
- Decide final training-data policy:
  - tolerate bounded nulls,
  - or hard-fail final outputs with these families still present
- Then implement column-family fixes:
  - redesign or drop `funding zscore`
  - redesign or drop null-heavy `D_*` windows that are structurally front-half invalid
  - decide whether sparse `1m` source gaps should be imputed, masked, or used to drop affected long-window features
