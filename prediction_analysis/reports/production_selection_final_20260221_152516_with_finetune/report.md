# Production Selection Summary (Full Walk-Forward)

## Inputs
- Ensemble input run: `prediction_analysis/multitimeframe_ensemble_outputs/20260221_125858_full500_fullsupport_risk_ensemble`
- Walk-forward: warmup=120, same_period_close, full production horizon

## Scans Executed
1. Full grid (macro objective):
   - `prediction_analysis/multitimeframe_cross_target_outputs/20260221_133308_fullprod_fullsupport_risk_macro_20260221_143247`
2. Full grid (risk-aware objective, cov floor 0.15):
   - `prediction_analysis/multitimeframe_cross_target_outputs/20260221_135215_fullprod_fullsupport_risk_riskaware_20260221_1453`
3. Focused risk-aware finetune (cov floor 0.12):
   - `prediction_analysis/multitimeframe_cross_target_outputs/20260221_141257_fullprod_fullsupport_risk_riskaware_finetune_cov12_20260221_1513`

## Final Ranking Filters
- `directional_active_coverage >= 0.12`
- `opposite_fp_rate_covered <= 0.08`

## Best Macro Under Filters
- weight: `diversity_weighted`
- rule: `dual_ova_thresholds`
- run: `grid_riskaware_finetune_cov12`
- metrics:
  - `macro_f1 = 0.5704918032786885`
  - `custom_mean_cost = 0.11752392344497607`
  - `directional_active_coverage = 0.1368122009569378`
  - `opposite_fp_rate_covered = 0.058761961722488036`
  - `directional_fp_risk_score = 0.13516746411483252`

## Best Risk-Guard Under Filters
- weight: `winner_history_blend`
- rule: `dual_ova_thresholds`
- run: `grid_riskaware_finetune_cov12`
- metrics:
  - `macro_f1 = 0.5563549160671463`
  - `custom_mean_cost = 0.11064593301435406`
  - `directional_active_coverage = 0.12470095693779905`
  - `opposite_fp_rate_covered = 0.05532296650717703`
  - `directional_fp_risk_score = 0.12664473684210525`

## Stability Check (first-half vs second-half)
Compared with earlier strict baseline (`history_brier_ewma + strict_agreement_margin`):
- strict baseline coverage: `0.2667 -> 0.0478`
- strict baseline safe directional accuracy: `0.5717 -> 0.4313`
- finetune best-macro coverage: `0.1725 -> 0.1011`
- finetune best-macro safe directional accuracy: `0.5702 -> 0.5710`

Interpretation: finetune setup is materially more stable over time with lower opposite-direction error.
