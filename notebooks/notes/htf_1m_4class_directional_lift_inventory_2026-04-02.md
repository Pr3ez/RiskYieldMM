# HTF 1m Target 4class Directional-Lift Inventory

## Goal

Find the historical methods used around `1m/target_4class` that produced directional-accuracy lifts, and separate:

- real deployable methods
- sparse-coverage methods
- hindsight/oracle methods
- diagnostic subset analyses

Artifacts:

- `test_output/htf_1m_4class_directional_lift_inventory/method_inventory_20260402.csv`
- `test_output/htf_1m_4class_directional_lift_inventory/method_inventory_20260402.json`

## Main Conclusion

The historical "huge directional lifts" did exist, but they came from different mechanisms:

1. `winner_combo_class` and the calibrated winner-policy gate showed very large directional accuracy, but they were not clean live methods.
2. High-quality subset analyses also showed very large directional accuracy, but only on selected steps.
3. The strongest actually deployable methods were later sparse directional meta methods, especially the cross-target production-selection runs.
4. Ordinary full-coverage winner12 ensemble variants did not produce huge lifts. They mostly stayed around low-`0.51` to low-`0.53` directional accuracy.

## Method Families

### 1. Direct Stage-1 winner12 / combo-match methods

Saved audit:

- `test_output/htf_walkforward_ensemble_audit/ensemble_method_comparison_20260402.json`

Key results:

- `winner_combo_class`
  - directional accuracy: `0.729758`
  - row coverage: `1.000000`
  - status: hindsight/oracle only
- `weighted_majority_class`
  - directional accuracy: `0.519267`
  - row coverage: `1.000000`
  - status: best valid full-coverage live-style method
- `weighted_majority_direction`
  - directional accuracy: `0.519000`
  - row coverage: `1.000000`
- `all12_unanimous_direction`
  - directional accuracy: `0.526144`
  - row coverage: `0.150925`
- `all12_unanimous_class`
  - directional accuracy: `0.538084`
  - row coverage: `0.049233`

Interpretation:

- the basic live-style full-coverage winner12 consensus never gave the huge lift
- agreement/unanimity filters gave some lift, but only by cutting coverage sharply

### 2. Winner12 secondary ensemble experiments

Relevant summaries:

- `prediction_analysis/winner12_dynamic_ensemble_outputs/2026-02-19_16-56-47/winner12_dynamic_ensemble_summary.json`
- `prediction_analysis/winner12_hedge_outputs/2026-02-19_17-06-28/winner12_hedge_summary.json`
- `prediction_analysis/winner12_diversity_outputs/2026-02-19_17-23-56/winner12_diversity_summary.json`
- `prediction_analysis/winner12_regime_router_outputs/2026-02-19_17-20-20/winner12_router_summary.json`
- `prediction_analysis/winner12_class_specialist_outputs/2026-02-19_17-27-14/winner12_classspec_summary.json`
- `prediction_analysis/winner12_discounted_model_averaging_outputs/2026-02-19_17-40-39/winner12_dma_summary.json`

Directional results:

- dynamic top-k ensemble: `0.511767`
- hedge online: `0.508267`
- diversity subset walkforward: `0.522873`
- regime router walkforward: `0.519638`
- per-class specialist walkforward: `0.525022`
- discounted model averaging: `0.516008`

Interpretation:

- these methods were real experiments, but they did not create the remembered huge lifts
- most were close to or below the simple full-coverage consensus range

### 3. Probability-gated winner policy

Key artifact:

- `data/htf_backtest_results/stage1_catboost_live/catboost/1m/target_4class/proba_gate_calibration/2026-02-13_00-04-23/winner12_calibration_summary.json`

Result:

- baseline winner policy
  - directional accuracy: `0.729758`
  - coverage: `1.000000`
- calibrated winner policy
  - directional accuracy: `0.861217`
  - coverage: `0.552442`
  - no-class rate: `0.447558`

Interpretation:

- this is one of the clearest sources of the remembered huge lift
- but it is not a clean live method:
  - it depends on winner-policy logic tied to hindsight winner selection
  - it also gains accuracy by abstaining on about `44.76%` of rows

### 4. Winner-dependency / high-quality subset analyses

Relevant artifacts:

- `prediction_analysis/reports/winner_dependency_last500_20260221_100724/unit_highlow_summary_last500.csv`
- `prediction_analysis/reports/winner_dependency_last500_20260221_100724/directional_top12_last500_minsteps30.csv`
- `prediction_analysis/reports/winner_dependency_last500_20260221_100724/winner_dependency_report_last500.md`

Important results for `1m/target_4class`:

- high-acc60 subset
  - directional accuracy: `0.887655`
  - subset coverage: `161 / 351` diagnosed steps
- low subset
  - directional accuracy: `0.632544`
- best single combo in subset analysis
  - `f2_v1_t4`
  - directional accuracy: `0.753611`
  - subset coverage: `45 / 351` diagnosed steps

Interpretation:

- this is another real source of huge directional numbers
- but it is diagnostic subset conditioning, not a standalone live final-prediction method

### 5. Cross-target / meta directional methods

These were the strongest historical methods that still look like actual deployable final-prediction logic.

Relevant reports:

- `prediction_analysis/reports/production_selection_final_20260221_151050/summary.json`
- `prediction_analysis/reports/production_selection_final_20260221_152516_with_finetune/summary.json`
- `prediction_analysis/reports/production_selection_final_20260221_152516_with_finetune/report.md`

Best historical production-style setups:

- `strict_brier_single`
  - weight: `history_brier_ewma`
  - rule: `strict_agreement_margin`
  - directional active accuracy: `0.550380`
  - directional active coverage: `0.157297`
- finetuned best macro
  - weight: `diversity_weighted`
  - rule: `dual_ova_thresholds`
  - directional active accuracy: `0.570492`
  - directional active coverage: `0.136812`
- finetuned best risk-guard
  - weight: `winner_history_blend`
  - rule: `dual_ova_thresholds`
  - directional active accuracy: `0.556355`
  - directional active coverage: `0.124701`

Interpretation:

- these are much more realistic historical lift methods than the oracle/subset cases
- they are still sparse directional methods, not full-coverage predictors
- this looks like the best historical balance between lift and usable coverage

### 6. 1m-only meta validation methods

Relevant artifacts:

- `prediction_analysis/multitimeframe_cross_target_validation/20260226_154523_one_minute_meta_safeFULL_agreement_hold/method_comparison_table.csv`
- `prediction_analysis/multitimeframe_cross_target_validation/20260226_154650_one_minute_meta_safeFULL_strict_agreement_margin/method_comparison_table.csv`
- `prediction_analysis/multitimeframe_cross_target_validation/20260226_1m_only_strict_dual/method_comparison_table.csv`

Important examples:

- `dualhead_meta_logit + agreement_hold`
  - directional active accuracy: `0.514952`
  - directional active coverage: `0.337001`
- `dualhead_meta_logit + strict_agreement_margin`
  - directional active accuracy: `0.521008`
  - directional active coverage: `0.011002`
- `diversity_weighted + dual_ova_thresholds` in `1m_only_strict_dual`
  - directional active accuracy: `0.736434`
  - directional active coverage: `0.002385`

Interpretation:

- this family can also show huge-looking numbers
- but the biggest values come from extremely small active coverage
- those are not practically useful unless that sparse-fire behavior is explicitly desired

## What Actually Caused the "Huge Lifts"

The historical large directional-accuracy jumps came mainly from:

1. hindsight winner selection
2. no-class / abstention gating
3. high-quality subset conditioning
4. very strict directional filters with tiny active coverage

They did not come from ordinary full-coverage ensemble averaging alone.

## Practical Ranking

### Best historical full-coverage methods

- `weighted_majority_class` at about `0.5193`
- `weighted_majority_direction` at about `0.5190`
- per-class specialist / diversity subset were nearby but not materially better

### Best historical sparse but realistically deployable methods

- `diversity_weighted + dual_ova_thresholds` finetune
  - active directional accuracy `0.5705`
  - active coverage `0.1368`
- `winner_history_blend + dual_ova_thresholds` finetune
  - active directional accuracy `0.5564`
  - active coverage `0.1247`
- `history_brier_ewma + strict_agreement_margin`
  - active directional accuracy `0.5504`
  - active coverage `0.1573`

### Biggest historical numbers, but not clean live methods

- calibrated winner policy: `0.8612` at `0.5524` coverage
- high-acc60 subset: `0.8877`
- `1m_only_strict_dual` top config: `0.7364` at `0.24%` active coverage
- oracle `winner_combo_class`: `0.7298` at full coverage

## Bottom Line

If the question is "where did the huge historical directional lifts come from?", the answer is:

- not from ordinary full-coverage winner12 ensembling
- mostly from gating, abstention, subset selection, or hindsight winner selection

If the question is "which historical methods looked strongest while still being plausible final predictors?", the answer is:

- the later cross-target production-selection methods
- especially `dual_ova_thresholds` with `diversity_weighted` or `winner_history_blend`

