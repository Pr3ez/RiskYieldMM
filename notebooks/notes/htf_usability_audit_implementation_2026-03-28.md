# HTF Usability Audit Implementation - 2026-03-28

## Scope

Implemented the first remediation step from the HTF final-output quality and
logic audits:

- add automated usability checks to the shared multi-regime workflow
- keep this step read-only with respect to feature/helper semantics
- surface structurally bad columns directly in shared validation

## Code Changes

Updated:

- [htf_multiregime_pipeline.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py)

What was added:

1. Validation config knobs in `MultiRegimeHTFConfig`
   - `usability_audit_enabled`
   - `usability_audit_null_rate_threshold`
   - `usability_audit_report_top_n`
   - `usability_audit_helper_prefix_batches`
   - `usability_audit_fail_on_all_null`
   - `usability_audit_fail_on_high_null`

2. Shared null/usability helpers
   - `_nullish_count_expr(...)`
   - `_audit_value_columns(...)`
   - `_format_usability_columns(...)`

3. Validation integration
   - `features`: root-wide value-column usability audit
   - `optimized`: root-wide value-column usability audit
   - `helpers`: root-wide helper-column usability audit
   - `helpers`: early-prefix helper audit to expose warmup-null helper families

4. Machine-readable artifacts
   - validation now writes per-regime usability diagnostics to:
     - [test_output/htf_validation_usability](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/htf_validation_usability)

## Validation Result

Compile:

- `python -m py_compile scripts/feature_engineering/htf_multiregime_pipeline.py`

Bounded probe:

- [htf_usability_probe_8h.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/htf_usability_probe_8h.json)
- [8h_latest.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/htf_validation_usability/8h_latest.json)

Probe summary:

- new usability rows emitted for `8h`: `18`
- failing usability rows: `4`

Those `4` failures match the already-known serious issue families:

1. `8h/B/1m optimized`
   - all-null:
     - `D_dist_avg_high_w240`
     - `D_dist_avg_low_w240`
     - `D_dist_top5_high_w240`

2. `8h/C/1m optimized`
   - all-null:
     - `F_I_N_S_fundingZscore_long_zsc`

3. `8h/B/1m helpers`
   - early-prefix helper warmup nulls across helper columns

4. `8h/C/1m helpers`
   - early-prefix helper warmup nulls across helper columns

## Conclusion

This implementation does not solve the semantic issues yet.

It does solve an important workflow problem:

- the shared pipeline can now automatically detect and document structurally bad
  final-output columns instead of silently passing them through basic existence
  checks

## Recommended Next Fix Tasks

1. decide policy for all-null `D_*` windows in final saved outputs
2. redesign or retire funding z-score features
3. decide policy for helper warmup rows in final outputs
4. decide whether high-null source-gap-derived columns should be accepted,
   imputed, or excluded
