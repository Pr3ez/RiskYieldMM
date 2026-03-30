# HTF Final Parquet Usability Cleanup - 2026-03-28

## Scope
- tighten final-parquet usability validation so helper-stage checks the full model-facing schema
- remove confirmed structurally all-null model-facing columns from optimized/helper outputs on future runs
- keep the change bounded and avoid changing helper warmup row-retention policy

## What Was Wrong
Two separate issues were confirmed during remediation:

1. Helper-stage usability validation was incomplete.
   - The shared validator only audited `H_*` helper columns inside final helper parquets.
   - That missed all-null optimized-feature columns which still reach `data/htf_with_helpers/...`.

2. Initial optimizer exclusion propagation was incomplete.
   - `get_feature_cols(...)` could exclude unusable all-null features.
   - But `apply_streaming_to_all_batches(...)` preserved every non-selected column as "metadata", which reintroduced dropped features into saved optimized outputs.

3. A first attempt at exclusion scope was too narrow.
   - Deciding exclusions from the first streamed batch alone over-dropped warmup-heavy columns.
   - The correct scope is the gated early sample already used for optimizer tuning.

## Code Changes
### `scripts/feature_engineering/htf_multiregime_pipeline.py`
- helper-stage usability audit now checks all numeric non-meta columns in final helper parquets
- helper-only `H_*` audits remain in place
- helper-prefix warmup audit remains helper-only

### `scripts/feature_engineering/optimize_htf_features.py`
- `get_feature_cols(...)` now excludes numeric columns that are entirely null/NaN after target gating
- `load_early_batches(...)` applies target gating before feature-column selection
- the early-sample feature set is now carried into streaming optimization
- `apply_streaming_to_all_batches(...)` now preserves only real metadata columns, so excluded features cannot leak back into optimized outputs

## Bounded Evidence
### Existing final helper outputs
- model-facing helper audit:
  - [htf_usability_cleanup_probe_8h.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/htf_usability_cleanup_probe_8h.json)
- confirmed all-null model-facing columns in current `8h` final helper outputs:
  - `8h/B/1m`: `D_dist_avg_high_w240`, `D_dist_avg_low_w240`, `D_dist_top5_high_w240`
  - `8h/C/1m`: `F_I_N_S_fundingZscore_long_zsc`

### Optimizer selection on gated early sample
- [htf_optimizer_selection_probe_8h.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/htf_optimizer_selection_probe_8h.json)
- confirmed selected drops:
  - `8h/B/1m`: the three all-null `D_*_w240` columns
  - `8h/C/1m`: `F_I_N_S_fundingZscore_long_zsc`

### Saved-output propagation proof
- [htf_usability_cleanup_first_batch_check.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/htf_usability_cleanup_first_batch_check.json)
- first-batch replay using the early-sample feature set shows:
  - `8h/B`: bad `D_*_w240` columns absent from saved optimized parquet
  - `8h/C`: bad funding-zscore column absent from saved optimized parquet

## What Is Fixed
- final helper validation now sees model-facing all-null columns instead of only helper-column nulls
- confirmed all-null model-facing columns can now be excluded from optimized/helper outputs on future runs
- exclusion no longer leaks back through the optimizer metadata path
- exclusion scope is based on the broader gated early sample, not the first streamed batch

## What Is Not Fixed In This Pass
- production parquet trees were not rebuilt in this remediation pass
- helper warmup null policy is unchanged
- high-null but not fully all-null columns are still diagnostics/policy work, not automatic exclusions

## Remaining Known Policy Work
- decide whether helper warmup nulls should block the workflow or just be reported
- decide whether high-null columns like `D_dist_bot5_low_w120`, `D_F_N_S_premiumZscore_xlong_zsc`, and `X_D_fundingBasisPressure_xlong_pct` should be tolerated, redesigned, or excluded
- rerun the relevant production stages when ready so the cleaned model-facing schema is written to production optimized/helper outputs
