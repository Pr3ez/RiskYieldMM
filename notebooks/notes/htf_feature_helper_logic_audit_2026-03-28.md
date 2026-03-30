# HTF Feature/Helper Logic Audit - 2026-03-28

## Scope

This audit continues the final-output quality work and answers a narrower
question:

- are the missing values in final HTF outputs caused by broken pipeline logic,
  or by specific feature/helper designs that are incompatible with the saved
  rows?

This pass focused on:

1. feature creation
2. label gating / saved-row selection
3. optimization null handling
4. helper-cache generation and helper materialization

The audit was intentionally run in an OOM-safe way:

- one root at a time
- one small sampled stage comparison at a time
- no full-root lazy aggregate joins

Supporting artifacts:

- [htf_final_output_data_quality_audit_2026-03-27.md](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/notes/htf_final_output_data_quality_audit_2026-03-27.md)
- [htf_final_output_broad_quality_verification_2026-03-28.md](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/notes/htf_final_output_broad_quality_verification_2026-03-28.md)
- [htf_stage_null_propagation_sample.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/htf_stage_null_propagation_sample.json)
- [htf_helper_warmup_null_sample.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/htf_helper_warmup_null_sample.json)

## Stage Ownership

### Feature stage

Shared feature generation happens in:

- [htf_multiregime_pipeline.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L1492)
- [compute_htf_features.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/compute_htf_features.py#L743)

Important facts:

- auxiliary feeds are merged before feature computation
- `F_I_*`, `D_F_*`, `S_*`, and composite derivatives features are created here
- batch-local `D_*` distance features are also created here, not in helpers

### Label stage

Shared label generation happens in:

- [htf_multiregime_pipeline.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L1885)

Important fact:

- labels gate targets by entry-bar policy, but they do not require every feature
  column to be non-null

So a row can remain in the saved final dataset while some feature columns are
still null.

### Optimization stage

Optimization happens in:

- [optimize_htf_features.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/optimize_htf_features.py#L662)

Important facts:

- optimizer joins feature and label batches on `timestamp` and `batch_id`
- for `target_4class` / `target_breakfree`, it keeps only rows with valid labels
  (`target >= 0`)
- it applies rolling rank-winsorize to feature columns
- it does **not** fill NaNs in the saved optimized batches
- `fillna(0)` appears only inside walk-forward scoring logic, not in the saved
  production outputs

### Helper stage

Helper cache and final helper materialization happen in:

- [htf_helper_cache.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_helper_cache.py#L322)
- [htf_helper_cache.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_helper_cache.py#L590)
- [htf_multiregime_pipeline.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L2118)

Important facts:

- helpers are built from raw inputs prepared by
  [prepare_raw_features_for_helpers()](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_helper_cache.py#L110)
- helper cache writes a full timestamp-aligned cache batch even for timestamps
  before helper warmup is complete
- helper materialization joins optimized rows with helper cache by timestamp
- helper stage does **not** create the problematic `F_I_*`, `D_F_*`, or `D_*`
  feature columns

## What Is Confirmed Not Broken

These points are now evidence-backed:

- no generic corruption of final batches:
  - no duplicate `(batch_id, timestamp)` pairs
  - no batch overlap
  - no non-monotonic timestamps
  - no infinite values
- helper materialization is **not** the origin of the audited feature nulls
- optimizer is **not** inventing the main null-bearing feature families
- label stage is behaving as designed: target validity and feature completeness
  are separate concerns

## Issue Classification

### 1. Funding z-score features

Columns:

- `F_I_N_S_fundingZscore_long_zsc`
- by extension, same mechanism applies to the `xlong` version

Root cause:

- funding is an `8h` stepwise source
- the z-score formula divides by rolling std
- inside a constant funding plateau, rolling std becomes `0`
- the implementation turns zero-denominator windows into `NaN`

Relevant code:

- [compute_htf_features.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/compute_htf_features.py#L885)
- [compute_htf_features.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/compute_htf_features.py#L1590)

Verdict:

- not a helper bug
- not a resume bug
- mostly a feature-design mismatch with a stepwise broadcast source

Severity:

- high, because `8h/C` final outputs can become `100%` null for this feature

### 2. Basis / mark / premium-derived sparse nulls

Columns:

- `D_F_basis_pct`
- `D_N_markCloseDeviation_pct`
- `D_F_N_S_premiumZscore_long_zsc`
- `X_D_fundingBasisPressure_long_pct`

Root cause:

- raw `1m` mark/index/premium feeds have real timestamp holes
- derivatives features inherit those holes
- long rolling windows amplify sparse source gaps

Verdict:

- this is not a downstream pipeline bug
- this is source-gap propagation plus rolling-window amplification

Severity:

- low to medium for `basis` / `markCloseDeviation`
- medium for `premium zscore` and `funding-basis pressure`

### 3. Batch-local `D_*` distance windows

Columns with confirmed structural problems:

- `D_dist_avg_high_w240`
- `D_dist_avg_low_w240`
- `D_dist_top5_high_w240`
- `D_dist_bot5_low_w120`
- `D_dist_avg_high_w16`
- `D_dist_avg_low_w16`
- `D_dist_top5_high_w16`

Root cause:

- these features are computed batch-locally and need enough prior bars in the
  same batch
- final downstream datasets keep only label-valid front slices
- large distance windows can be valid on the full feature tree but become
  structurally unusable once only the saved front-half rows remain

Evidence from sampled stage propagation:

- `8h/B/1m` sampled features:
  - `D_dist_avg_high_w240`: `1200 / 2400` null
  - optimized: `1200 / 1200` null
  - helpers: `1200 / 1200` null
- `8h/B/15m` sampled features:
  - `D_dist_avg_high_w16`: `80 / 160` null
  - helpers: `80 / 80` null

Verdict:

- not a helper bug
- not an optimizer bug
- design mismatch between feature window and saved row policy

Severity:

- high for the all-null final columns

### 4. Helper warmup nulls in early saved batches

Columns:

- `H_4cl_1_cp_any`
- `H_4cl_1_cp_count_21`
- `H_4cl_1_cp_magnitude`
- `H_4cl_1_cp_ret_up`
- `H_4cl_1_cp_ret_down`
- `H_4cl_1_cp_vol_up`
- `H_4cl_1_cp_vol_down`
- `H_4cl_1_cusum_ret_pos`
- `H_4cl_1_cusum_ret_neg`
- `H_4cl_1_cusum_vol_neg`
- and related early helper families

What the data shows:

- first helper cache batches already contain these columns as all-null
- example:
  - [batch_0001.parquet](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_helper_cache/base_0h/1m/target_4class/batch_0001.parquet)
  - [batch_0001.parquet](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_helper_cache/shift4h/1m/target_4class/batch_0001.parquet)
- in sampled final helper outputs:
  - `8h/B/1m` first 20 batches: these helper columns are `4800 / 4800` null
  - `24h/B/1m` first 20 batches: `10080 / 14400` null
  - `7d/B/1m` first 20 batches: `10080 / 100800` null

Why:

- helper compute starts only after `warmup_rows`
- see [compute_helpers_walk_forward_raw()](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_helper_cache.py#L128)
- but cache batches are written for the whole timestamp range in
  [build_helper_cache_exact()](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_helper_cache.py#L469)
- pre-warmup timestamps get joined to no helper output and therefore stay null

Verdict:

- this is not random corruption
- it is an expected consequence of current helper warmup handling
- but it is also a real **usability / validation gap**, because those all-null
  early helper columns are allowed through to final outputs without a dedicated
  quality check

Severity:

- medium

This is the closest thing found here to an actual workflow-level bug:

- not because the code crashes or writes broken rows
- but because the workflow currently treats pre-warmup helper nulls as
  acceptable final outputs without an explicit policy

## Stage-by-Stage Conclusion

### Features

Main audited nulls are created here.

Conclusion:

- feature stage contains design-limited feature families
- the worst ones are funding z-score and some `D_*` windows

### Labels

Labels are not the source of these nulls.

Conclusion:

- behavior is correct
- row retention policy exposes the mismatch in some feature families

### Optimizer

Optimizer keeps valid-label rows only and transforms numeric feature columns.

Conclusion:

- it does not create the main null-bearing columns
- it can make structural incompatibility more visible because only the
  front-half labeled rows survive into optimized outputs

### Helpers

Helpers do not create the audited feature-family nulls.

Conclusion:

- helper stage is not the source of `F_I_*`, `D_F_*`, or `D_*` problems
- helper stage does have its own warmup-null policy issue for early saved rows

## Overall Conclusion

This is **not** a broad “the whole workflow is broken” result.

It is a narrower but still important result:

1. some feature families are mathematically incompatible with the saved final
   row policy
2. some auxiliary-derived columns inherit real source-feed sparsity
3. helper warmup nulls are allowed into early final outputs without an
   explicit acceptance policy

So the current situation is:

- the pipeline is structurally sound
- final outputs are not generically corrupted
- but several columns are low-quality or unusable for modeling in their current
  form

## Recommended Next Actions

### Immediate

1. Add an automated feature/helper usability audit after final artifact write.
2. Flag columns that are:
   - `100%` null
   - above a configurable null threshold
   - all-null only in saved final rows

### Likely fixes

1. Remove or redesign funding z-score features.
2. Remove or redesign the structurally invalid `D_*` windows from final
   modeling outputs.
3. Decide explicit policy for source-gap-driven derivatives features.
4. Decide explicit policy for pre-warmup helper rows:
   - keep but mark invalid
   - or drop them from final helper outputs
   - or exclude affected helper columns until warmup is complete

### Before changing behavior

Any fix should first classify each affected column into:

- acceptable sparse nulls
- structurally invalid for saved outputs
- helper warmup artifact
- true implementation bug

This audit confirms the first three categories. It did **not** find evidence of
generic stage corruption.
