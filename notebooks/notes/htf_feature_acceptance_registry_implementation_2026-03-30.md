# HTF Feature Acceptance Registry Implementation 2026-03-30

## Scope
- implement the first safe remediation slice from
  [htf_null_heavy_feature_remediation_plan_2026-03-30.md](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/notes/htf_null_heavy_feature_remediation_plan_2026-03-30.md)
- add an explicit final-output feature acceptance registry
- exclude the current structural design-mismatch families from model-facing optimized/helper outputs
- wire the policy into optimizer resume logic and shared validation

## Code Changes

### New shared policy module
- added [htf_feature_acceptance.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_feature_acceptance.py)

It defines:
- explicit final-output exclusion rules
- policy version and signature
- helpers to resolve excluded columns by output stage

Current explicit exclusions:
- `F_I_N_S_fundingZscore_*_zsc`
- `D_dist_avg_high_w240`
- `D_dist_avg_low_w240`
- `D_dist_top5_high_w240`

### Optimizer integration
- updated [optimize_htf_features.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/optimize_htf_features.py)

What changed:
- `get_feature_cols(...)` now excludes:
  1. policy-blocked final-output columns
  2. all-null gated columns
- optimized metadata now stores:
  - `final_output_feature_policy_version`
  - `final_output_feature_policy_signature`
- resume logic now treats a policy-version/signature mismatch as a full recompute trigger from the first batch
- cached `feature_cols` are not reused when policy changed

Why this matters:
- the new exclusions will actually take effect on future reruns
- old optimized trees will not stay incorrectly `current` just because the feature/label input files did not change

### Shared validation integration
- updated [htf_multiregime_pipeline.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py)

What changed:
- optimized validation now adds:
  - `policy_excluded_columns_absent`
- helper validation now adds:
  - `policy_excluded_columns_absent`

Why this matters:
- the workflow now distinguishes:
  - generic null-heavy columns
  - columns that are explicitly disallowed from final model-facing outputs

## Bounded Validation

### Compile
- `python -m py_compile` passed for:
  - `scripts/feature_engineering/htf_feature_acceptance.py`
  - `scripts/feature_engineering/optimize_htf_features.py`
  - `scripts/feature_engineering/htf_multiregime_pipeline.py`

### Optimizer feature-column selection proof
Using the current live `8h/B/1m` feature+label batch `0001`, `get_feature_cols(...)` now excludes the explicit policy-blocked columns.

Observed blocked set:
- `D_dist_avg_high_w240`
- `D_dist_avg_low_w240`
- `D_dist_top5_high_w240`
- `F_I_N_S_fundingZscore_long_zsc`
- `F_I_N_S_fundingZscore_xlong_zsc`

Observed selection result:
- all blocked columns were absent from the selected model feature set

### Resume invalidation proof
Current production optimized metadata in:
- `data/htf_optimized/1m/optimized_target_4class_meta.json`

does not contain the new policy fields yet, so:
- cached policy version: `None`
- cached policy signature: `None`
- current policy version: `2026-03-30-b8d1c43c8001`
- policy change detection: `True`

That means the next optimization rerun will not incorrectly reuse the old model-facing feature set.

### Current output-schema policy detection proof
Current live batch schema still contains policy-blocked funding z-score columns in:
- `data/htf_optimized/1m/target_4class/batch_0001.parquet`
- `data/htf_with_helpers/1m/target_4class/batch_0001.parquet`

So the new validation logic will correctly flag those current outputs until the affected stages are rerun.

## What This Implementation Does Not Do
- it does not rewrite current production optimized/helper outputs by itself
- it does not redesign funding z-score semantics
- it does not decide the sparse-source gap policy for:
  - `D_F_N_S_premiumZscore_xlong_zsc`
  - `X_D_fundingBasisPressure_xlong_pct`
- it does not change raw feature-stage artifacts

## Practical Effect
On the next optimization/helper rerun:
- funding z-score family will be excluded from model-facing optimized/helper outputs
- the explicitly blocked `D_*_w240` windows will be excluded from model-facing optimized/helper outputs
- shared validation will have an explicit policy check for these final outputs

## Next Actions
- rerun the affected optimized/helper stages so the live training parquets adopt the new final-output policy
- then re-run validation/usability checks
- after that, move to the next unresolved family:
  - sparse-source-gap handling for premium/index-based xlong derivatives features
