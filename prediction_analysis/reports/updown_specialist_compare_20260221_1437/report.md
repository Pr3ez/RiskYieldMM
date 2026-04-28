# UP/DOWN Specialist Split Analysis

Input production run:
- `prediction_analysis/multitimeframe_cross_target_outputs/20260221_141257_fullprod_fullsupport_risk_riskaware_finetune_cov12_20260221_1513`

## What was tested
- Independent config selection for UP and DOWN from the same method pool.
- Combined final prediction:
  - UP if UP specialist signals and DOWN specialist does not
  - DOWN if DOWN specialist signals and UP specialist does not
  - HOLD otherwise

## Best specialist split (risk-weighted objective)
Run:
- `prediction_analysis/multitimeframe_cross_target_specialist_outputs/20260221_143615_updown_specialist_prod`

Selected configs:
- UP specialist: `diversity_weighted + dual_ova_thresholds` (rare high-precision UP)
- DOWN specialist: `acc_logloss_blend + dual_ova_thresholds`

Dual-specialist metrics:
- `directional_active_safe_accuracy = 0.5825`
- `directional_active_coverage = 0.1404`
- `opposite_fp_rate_covered = 0.0410`
- `hold_side_cross_error_rate_covered = 0.0176`

Single-config baseline from same run:
- `directional_active_safe_accuracy = 0.5705`
- `directional_active_coverage = 0.1368`
- `opposite_fp_rate_covered = 0.0411`
- `hold_side_cross_error_rate_covered = 0.0176`

## Conclusion
- Splitting UP and DOWN specialists improved directional safe accuracy and coverage while keeping opposite-direction error essentially unchanged/slightly lower.
- In this dataset, best split uses a very selective UP specialist and a broader DOWN specialist.
