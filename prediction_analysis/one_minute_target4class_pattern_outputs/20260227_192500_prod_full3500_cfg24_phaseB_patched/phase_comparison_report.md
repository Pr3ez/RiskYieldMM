# Phase Comparison (Holdout 500)

Patched run: `20260227_192500_prod_full3500_cfg24_phaseB_patched`

| metric | phaseA | phaseB_prev | patched | Δ patched-phaseA | Δ patched-phaseB_prev |
|---|---:|---:|---:|---:|---:|
| active_batches | 58 | 65 | 60 | +2.000000 | -5.000000 |
| coverage | 0.116000 | 0.130000 | 0.120000 | +0.004000 | -0.010000 |
| batches_per_signal | 8.620690 | 7.692308 | 8.333333 | -0.287356 | +0.641026 |
| directional_active_safe_accuracy | 0.517241 | 0.476923 | 0.516667 | -0.000575 | +0.039744 |
| opposite_fp_rate_active | 0.482759 | 0.523077 | 0.483333 | +0.000575 | -0.039744 |
| opposite_fp_rate_covered | 0.056000 | 0.068000 | 0.058000 | +0.002000 | -0.010000 |
| opposite_fp_count | 28 | 34 | 29 | +1.000000 | -5.000000 |
| pass_production_gate | false | false | false | +0.000000 | +0.000000 |
| violation_score | 1.695241 | 2.106308 | 3.314679 | +1.619438 | +1.208372 |

Notes:
- `violation_score` is not directly comparable pre/post patch because holdout scoring now uses conformal bounds in conformal mode.
- Risk metrics (`opposite_fp_rate_active`, `opposite_fp_rate_covered`, `directional_active_safe_accuracy`) remain directly comparable.