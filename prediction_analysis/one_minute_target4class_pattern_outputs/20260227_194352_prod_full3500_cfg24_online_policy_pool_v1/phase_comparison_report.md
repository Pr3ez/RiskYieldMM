# Online Policy Pool V1 Comparison (Holdout 500)

Run: `20260227_194352_prod_full3500_cfg24_online_policy_pool_v1`

| metric | phaseA | phaseB_prev | phaseB_patched | online_pool_v1 | Δ vs phaseA | Δ vs phaseB_prev | Δ vs phaseB_patched |
|---|---:|---:|---:|---:|---:|---:|---:|
| active_batches | 58 | 65 | 60 | 58 | +0.000000 | -7.000000 | -2.000000 |
| coverage | 0.116000 | 0.130000 | 0.120000 | 0.116000 | +0.000000 | -0.014000 | -0.004000 |
| batches_per_signal | 8.620690 | 7.692308 | 8.333333 | 8.620690 | +0.000000 | +0.928382 | +0.287356 |
| directional_active_safe_accuracy | 0.517241 | 0.476923 | 0.516667 | 0.482759 | -0.034483 | +0.005836 | -0.033908 |
| opposite_fp_rate_active | 0.482759 | 0.523077 | 0.483333 | 0.517241 | +0.034483 | -0.005836 | +0.033908 |
| opposite_fp_rate_covered | 0.056000 | 0.068000 | 0.058000 | 0.060000 | +0.004000 | -0.008000 | +0.002000 |
| opposite_fp_count | 28 | 34 | 29 | 30 | +2.000000 | -4.000000 | +1.000000 |
| pass_production_gate | false | false | false | false | +0.000000 | +0.000000 | +0.000000 |