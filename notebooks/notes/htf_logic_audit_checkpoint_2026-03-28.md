# HTF Logic Audit Checkpoint

Date: 2026-03-28

## Purpose

Checkpoint note for the end-to-end logic audit of null-bearing final HTF columns.

This does **not** close the full audit. It records what is already verified from the code path so we do not lose context or start guessing.

## Verified So Far

### 1. Helper materialization is not the origin of the problematic feature nulls

Shared path:

- features are built in `scripts/feature_engineering/htf_multiregime_pipeline.py`
  - source augmentation: lines `1492-1499`
  - core feature compute: line `1499`
  - batch-local `D_*` distance features: lines `1500-1520`
  - final feature write: lines `1527-1534`

- helper stage later uses:
  - raw feature batches as helper-cache input
  - optimized batches as the frame to receive helper columns
  - helper materialization in `scripts/feature_engineering/htf_multiregime_pipeline.py` lines `2118-2235`

Conclusion:

- helper materialization does not create `F_I_*`, `D_F_*`, `S_*`, or `D_dist_*`
- those columns already exist, with their null patterns, before helper materialization

### 2. Funding-zscore nulls originate in feature math, not source absence

Feature creation:

- `F_I_N_S_fundingZscore_{label}_zsc` is created in `scripts/feature_engineering/compute_htf_features.py` lines `885-895`
- formula is `_compute_funding_zscore()` in lines `1590-1597`

Formula behavior:

- rolling mean / std on broadcast funding series
- if std is zero, denominator becomes `NaN`

This matches the observed outcome:

- shifted `8h/C` retained rows can sit inside a constant funding plateau
- therefore the long funding z-score becomes structurally undefined across the retained final rows

### 3. `D_*` distance nulls originate in batch-local feature logic

Shared path:

- `D_*` feature arrays are created from `_compute_past_distance_metrics(...)` in `scripts/feature_engineering/htf_multiregime_pipeline.py` lines `1500-1518`
- they depend on:
  - `close`
  - `high`
  - `low`
  - `bar_pos`
  - configured window length

This means:

- they are computed inside batch-local history
- they do not come from fetched auxiliary sources

Observed final-output result is therefore consistent with a window-vs-retained-slice mismatch:

- large windows like `w240` / `w16` can be structurally invalid for most or all retained final rows

### 4. Label generation does not filter rows by feature completeness

Shared label path:

- label logic is built from combined `1m`/`15m` data in `scripts/feature_engineering/htf_multiregime_pipeline.py` lines `1908-2027`
- gating is applied on label-valid entry bars, not on feature completeness

Conclusion:

- rows can remain in final outputs even when some feature columns are null
- this is expected under the current contract

### 5. The current final-output contract is row-retention first, feature-usability second

What the shared path currently guarantees:

- structurally valid batch/timestamp rows
- label gating
- optimization and helper processing

What it does **not** currently guarantee:

- every saved feature column is usable on every saved row
- every saved feature column has acceptable missingness
- every engineered feature window is compatible with the retained final slice

## Working Conclusion

The current evidence points to:

1. **feature-design mismatches**
   - funding z-score on broadcast stepwise funding
   - some `D_*` windows too large for retained final rows

2. **source-driven gaps**
   - mark/index/premium sparse timestamps

3. **missing workflow guardrails**
   - no automated feature-usability audit before outputs are accepted

This is serious enough to justify a full logic review, but the evidence so far does **not** point to random corruption inside helpers or final parquet writing.

## Still Open In The Audit

- optimizer null-handling behavior and whether it amplifies or simply carries nulls
- whether any additional feature families besides funding-zscore and `D_*` are structurally invalid in final outputs
- whether some current windows should be removed entirely from final modeling sets
- what the formal acceptance policy should be for source-gap-driven sparse nulls

