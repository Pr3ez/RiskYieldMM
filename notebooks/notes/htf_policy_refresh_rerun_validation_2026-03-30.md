# HTF Policy Refresh Rerun Validation 2026-03-30

## Scope
- validate the targeted production rerun launched to materialize the
  final-output feature acceptance policy into live `1m/target_4class`
  optimized/helper outputs
- confirm the run used the supported plain-script `CELL 14` path
- confirm the rebuilt live outputs now carry the policy signature and exclude
  the currently blocked model-facing columns

## Run Artifacts
- run log:
  [htf_pythonscript_20260330_024953_pid43258.log](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/htf_run_logs/htf_pythonscript_20260330_024953_pid43258.log)
- run status:
  [htf_pythonscript_20260330_024953_pid43258_status.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/htf_run_logs/htf_pythonscript_20260330_024953_pid43258_status.json)
- rotation manifest:
  [ris172_rotation_manifest_20260330_024944.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/ris172_rotation_manifest_20260330_024944.json)
- machine-readable post-run summary:
  [htf_policy_refresh_rerun_summary_20260330.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/htf_policy_refresh_rerun_summary_20260330.json)

## Run Outcome
- run finished cleanly
- plain-script short-circuit into supported `CELL 14` is confirmed in the run log
- no legacy notebook replay occurred
- final run status is `shutdown`
- validation stage completed at the end of the run with `rows=552`
- no traceback or runtime error appears in the run log

## Policy Materialization Result

### Optimized metadata
All six optimized roots now contain:
- `final_output_feature_policy_version = 2026-03-30-b8d1c43c8001`
- `final_output_feature_policy_signature = b8d1c43c8001e5f08f40a8087ecc8a6551a4331aa227d6290cac736411670fd0`

All six optimized roots report:
- `resume_reason = full_recompute`
- `reused_batches = 0`
- `skipped_batches = 0`

### Blocked columns in rebuilt outputs
Checked on the first actual live batch in each root:
- optimized roots:
  - `8h/B`: `batch_0001`
  - `8h/C`: `batch_0001`
  - `24h/B`: `batch_0001`
  - `24h/C`: `batch_0001`
  - `7d/B`: `batch_0002`
  - `7d/C`: `batch_0002`
- helper roots:
  - `8h/B`: `batch_0001`
  - `8h/C`: `batch_0001`
  - `24h/B`: `batch_0001`
  - `24h/C`: `batch_0001`
  - `7d/B`: `batch_0002`
  - `7d/C`: `batch_0002`

Observed result:
- no policy-blocked columns are present in any checked rebuilt optimized batch
- no policy-blocked columns are present in any checked rebuilt helper batch

Blocked columns checked:
- `F_I_N_S_fundingZscore_long_zsc`
- `F_I_N_S_fundingZscore_xlong_zsc`
- `D_dist_avg_high_w240`
- `D_dist_avg_low_w240`
- `D_dist_top5_high_w240`

## What This Confirms
- the acceptance registry is now materialized into the live model-facing
  optimized/helper artifacts
- the targeted rerun scope was correct:
  - combined/features/labels were not forced through unnecessary rebuilds
  - optimized/helper outputs were rebuilt from scratch under the new policy
- the pre-rerun outputs remain preserved in the `*_pre_ris172_*` rotated
  directories for before/after comparison

## Important Boundary
- this rerun confirms policy-blocked columns are removed from live model-facing
  outputs
- it does not resolve the remaining null-heavy but still-allowed feature
  families such as sparse-source-gap-sensitive premium/index derivatives

## Next Actions
- use the refreshed optimized/helper parquets as the new live baseline for
  subsequent final-output data-quality work
- continue with the next remediation slice for the still-allowed null-heavy
  families
