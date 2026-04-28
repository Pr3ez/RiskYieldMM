# HTF Causal Multiregime Method Analysis - 2026-04-02

## Scope

Evaluate the latest Stage-1 walk-forward outputs for:

- `8h/B`
- `8h/C`
- `24h/B`
- `24h/C`
- `7d/B`
- `7d/C`

using only ensemble / post-processing methods that are acceptable under a no-lookahead causal contract.

## Source Artifacts

- Stage-1 walk-forward roots:
  - `data/htf_backtest_results/stage1_catboost_8h_b_live/catboost/1m/target_4class`
  - `data/htf_backtest_results/stage1_catboost_8h_c_live/catboost/1m/target_4class`
  - `data/htf_backtest_results/stage1_catboost_24h_b_live/catboost/1m/target_4class`
  - `data/htf_backtest_results/stage1_catboost_24h_c_live/catboost/1m/target_4class`
  - `data/htf_backtest_results/stage1_catboost_7d_b_live/catboost/1m/target_4class`
  - `data/htf_backtest_results/stage1_catboost_7d_c_live/catboost/1m/target_4class`
- Analysis output root:
  - `test_output/htf_causal_multiregime_method_analysis/20260402_170806`

## Causal Method Contract

Included methods:

- `uniform_argmax_class`
- `uniform_direction_sum`
- `all_agree_class`
- `all_agree_direction`
- `hedge_online`
- `diversity_subset`
- `per_class_specialist`
- `regime_router`
- `stacking_meta`
- `discounted_model_averaging`

Excluded as not cleanly causal under the historical implementation:

- `winner_combo_class`
- `weighted_majority_class`
- `weighted_majority_direction`
- `dynamic_topk`

## Important Evaluation Guard

Some roots had late prediction batches with an incomplete combo set. These were removed from the causal combo-match input before running the ensemble methods so that every scored batch had the same combo universe.

Affected roots:

- `24h/B`
  - dropped `pred_batch` `1866`, `1867`
  - missing combo: `f2_v1_t3`
- `7d/C`
  - dropped `pred_batch` `171`, `172`
  - missing combo: `f2_v1_t3`

This filter is required for fair cross-method comparison because DMA / stacking / router methods assume a complete per-batch combo panel.

## Best Methods By Root

### Best Overall Directional Accuracy

This ranking allows reduced coverage.

| Root | Best method | Config | Directional accuracy | Row coverage |
| --- | --- | --- | ---: | ---: |
| `8h/B` | `all_agree_direction` | `direct` | `0.562381` | `0.172083` |
| `8h/C` | `all_agree_class` | `direct` | `0.640842` | `0.044298` |
| `24h/B` | `stacking_meta` | `c=2.0_iter=180` | `0.509634` | `1.000000` |
| `24h/C` | `uniform_direction_sum` | `direct` | `0.521630` | `1.000000` |
| `7d/B` | `diversity_subset` | `subset=4_alpha=0.55_pow=1.2` | `0.517647` | `1.000000` |
| `7d/C` | `stacking_meta` | `c=0.5_iter=120` | `0.648070` | `1.000000` |

### Best Full-Coverage Directional Accuracy

This ranking requires effectively full row coverage.

| Root | Best full-coverage method | Config | Directional accuracy | Row coverage |
| --- | --- | --- | ---: | ---: |
| `8h/B` | `per_class_specialist` | `spc=3_rp=1.0_floor=0.2` | `0.515888` | `1.000000` |
| `8h/C` | `discounted_model_averaging` | `eta_model=4.0_eta_gamma=2.0_loss=acc_cde` | `0.543542` | `1.000000` |
| `24h/B` | `stacking_meta` | `c=2.0_iter=180` | `0.509634` | `1.000000` |
| `24h/C` | `uniform_direction_sum` | `direct` | `0.521630` | `1.000000` |
| `7d/B` | `diversity_subset` | `subset=4_alpha=0.55_pow=1.2` | `0.517647` | `1.000000` |
| `7d/C` | `stacking_meta` | `c=0.5_iter=120` | `0.648070` | `1.000000` |

## Main Takeaways

- `7d/C` is the strongest current root under a clean causal contract. Its best full-coverage method is `stacking_meta` at `0.648070` directional accuracy.
- `8h/C` also supports a meaningful clean lift without dropping coverage. `discounted_model_averaging` reached `0.543542`.
- `24h/B` prefers walk-forward stacking. All three tested stacking configurations were effectively tied around `0.50963`.
- `24h/C` did not benefit from the more complex causal methods. The simple `uniform_direction_sum` baseline stayed best at `0.521630`.
- `7d/B` benefited most from the diversity subset family, but the lift over direct baselines was modest.
- `8h/B` can get a bigger directional lift only by abstaining. The best causal full-coverage result is lower than the best reduced-coverage `all_agree_direction` filter.

## Operational Interpretation

- If full coverage is required, the most relevant winners are:
  - `8h/B`: `per_class_specialist`
  - `8h/C`: `discounted_model_averaging`
  - `24h/B`: `stacking_meta`
  - `24h/C`: `uniform_direction_sum`
  - `7d/B`: `diversity_subset`
  - `7d/C`: `stacking_meta`
- If selective coverage is acceptable, `all_agree_*` can produce directional lifts on `8h`, but coverage drops sharply and should be treated as an abstention policy rather than a direct replacement.

## Output Files

- Summary JSON:
  - `test_output/htf_causal_multiregime_method_analysis/20260402_170806/summary.json`
- All scores:
  - `test_output/htf_causal_multiregime_method_analysis/20260402_170806/all_method_scores.csv`
  - `test_output/htf_causal_multiregime_method_analysis/20260402_170806/all_method_scores.parquet`
- Best per family:
  - `test_output/htf_causal_multiregime_method_analysis/20260402_170806/best_per_family.csv`
  - `test_output/htf_causal_multiregime_method_analysis/20260402_170806/best_per_family.parquet`
- Global leaderboard:
  - `test_output/htf_causal_multiregime_method_analysis/20260402_170806/leaderboard.csv`
  - `test_output/htf_causal_multiregime_method_analysis/20260402_170806/leaderboard.parquet`
- Summary table:
  - `test_output/htf_causal_multiregime_method_analysis/20260402_170806/summary_table.csv`
