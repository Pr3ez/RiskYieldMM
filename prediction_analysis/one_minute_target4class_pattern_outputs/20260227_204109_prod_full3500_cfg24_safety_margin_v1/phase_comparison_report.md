# Safety-Margin V1 Comparison (Holdout 500)

Run: `20260227_204109_prod_full3500_cfg24_safety_margin_v1`

| metric | phaseA | phaseB_prev | phaseB_patched | online_pool_v1 | dir_threshold_v1 | safety_margin_v1 | Δ vs phaseA | Δ vs phaseB_prev | Δ vs phaseB_patched |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| active_batches | 58 | 65 | 60 | 58 | 75 | 0 | -58.000000 | -65.000000 | -60.000000 |
| coverage | 0.116000 | 0.130000 | 0.120000 | 0.116000 | 0.150000 | 0.000000 | -0.116000 | -0.130000 | -0.120000 |
| batches_per_signal | 8.620690 | 7.692308 | 8.333333 | 8.620690 | 6.666667 | inf |  |  |  |
| directional_active_safe_accuracy | 0.517241 | 0.476923 | 0.516667 | 0.482759 | 0.493333 | 0.000000 | -0.517241 | -0.476923 | -0.516667 |
| opposite_fp_rate_active | 0.482759 | 0.523077 | 0.483333 | 0.517241 | 0.506667 | 0.000000 | -0.482759 | -0.523077 | -0.483333 |
| opposite_fp_rate_covered | 0.056000 | 0.068000 | 0.058000 | 0.060000 | 0.076000 | 0.000000 | -0.056000 | -0.068000 | -0.058000 |
| opposite_fp_count | 28 | 34 | 29 | 30 | 38 | 0 | -28.000000 | -34.000000 | -29.000000 |
| pass_production_gate | false | false | false | false | false | false | +0.000000 | +0.000000 | +0.000000 |