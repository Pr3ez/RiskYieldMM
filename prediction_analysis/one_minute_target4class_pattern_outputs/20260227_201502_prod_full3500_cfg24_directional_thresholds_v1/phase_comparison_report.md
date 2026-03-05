# Directional Thresholds V1 Comparison (Holdout 500)

Run: `20260227_201502_prod_full3500_cfg24_directional_thresholds_v1`

| metric | phaseA | phaseB_prev | phaseB_patched | online_pool_v1 | dir_threshold_v1 | Δ vs phaseA | Δ vs phaseB_prev | Δ vs phaseB_patched | Δ vs online_pool_v1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| active_batches | 58 | 65 | 60 | 58 | 75 | +17.000000 | +10.000000 | +15.000000 | +17.000000 |
| coverage | 0.116000 | 0.130000 | 0.120000 | 0.116000 | 0.150000 | +0.034000 | +0.020000 | +0.030000 | +0.034000 |
| batches_per_signal | 8.620690 | 7.692308 | 8.333333 | 8.620690 | 6.666667 | -1.954023 | -1.025641 | -1.666667 | -1.954023 |
| directional_active_safe_accuracy | 0.517241 | 0.476923 | 0.516667 | 0.482759 | 0.493333 | -0.023908 | +0.016410 | -0.023333 | +0.010575 |
| opposite_fp_rate_active | 0.482759 | 0.523077 | 0.483333 | 0.517241 | 0.506667 | +0.023908 | -0.016410 | +0.023333 | -0.010575 |
| opposite_fp_rate_covered | 0.056000 | 0.068000 | 0.058000 | 0.060000 | 0.076000 | +0.020000 | +0.008000 | +0.018000 | +0.016000 |
| opposite_fp_count | 28 | 34 | 29 | 30 | 38 | +10.000000 | +4.000000 | +9.000000 | +8.000000 |
| pass_production_gate | false | false | false | false | false | +0.000000 | +0.000000 | +0.000000 | +0.000000 |