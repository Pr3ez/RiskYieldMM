# HTF Stage-1-v2 Fixed-Policy Audit

Date: 2026-04-20

Run audited:

- `stage1_catboost_8h_b_v2_fixed_policy_pb5170_5355_live`

Window audited:

- `pred_batch 5170..5355`
- `186` steps

## Important Artifact Caveat

The root-level Stage-1-v2 rollup artifacts in the run directory are partial after resume:

- `stage1_progress.parquet` has `186` rows
- `stage1_v2_progress.parquet` has only `44` rows

So the root `stage1_v2_*` rollups do **not** currently reflect the full resumed run.

For this audit, the full summary was rebuilt directly from the step files:

- `catboost/1m/target_4class/batch_*/stage1_v2/stage1_v2_combo_metrics.parquet`
- `catboost/1m/target_4class/batch_*/stage1_v2/stage1_v2_step_summary.json`
- `catboost/1m/target_4class/batch_*/stage1_v2/stage1_v2_selected_features.json`

## Core Findings

1. The produced step data is complete for the requested window.
   - `186` combo-metric step files
   - `186` step summaries
   - `186` selected-feature payloads

2. Fixed masks were stable across the full run for every combo.
   - each combo had exactly `1` mask hash across all `186` steps
   - `missing_policy_feature_count_max = 0` for all combos

3. Winner-level performance improved strongly under fixed preselection.
   - baseline winner accuracy mean: `0.3102`
   - selected winner accuracy mean: `0.5366`
   - mean winner accuracy lift: `+0.2264`
   - baseline winner CDE mean: `0.4664`
   - selected winner CDE mean: `0.2647`
   - mean winner CDE improvement: `+0.2017`
   - baseline winner macro-F1 mean: `0.1727`
   - selected winner macro-F1 mean: `0.2879`
   - mean winner macro-F1 lift: `+0.1152`

4. The selected winner changed on most steps.
   - winner change steps: `148 / 186`
   - winner change rate: `79.6%`

## Winner Counts

Baseline winner counts:

- `f2_v2_t10`: `30`
- `f2_v1_t3`: `27`
- `f2_v2_t4`: `25`
- `f2_v3_t9`: `24`
- `f2_v2_t8`: `23`
- `f2_v1_t6`: `22`
- `f2_v1_t5`: `21`
- `f7_v1_t4`: `14`

Selected winner counts under fixed preselection:

- `f2_v1_t3`: `29`
- `f2_v2_t4`: `26`
- `f2_v3_t9`: `26`
- `f2_v2_t8`: `24`
- `f2_v2_t10`: `22`
- `f7_v1_t4`: `21`
- `f2_v1_t6`: `21`
- `f2_v1_t5`: `17`

## Per-Combo Performance

Columns:

- `delta_accuracy_mean`: mean(`filtered_accuracy - baseline_accuracy`)
- `delta_cde_improve_mean`: mean(`baseline_cde - filtered_cde`)

### Best Accuracy Lift

- `f2_v2_t8`: `+0.0345`
- `f2_v2_t10`: `+0.0247`
- `f2_v3_t9`: `+0.0154`
- `f2_v1_t5`: `+0.0135`
- `f2_v1_t6`: `+0.0037`

### Accuracy Regressions

- `f7_v1_t4`: `-0.0021`
- `f2_v1_t3`: `-0.0026`
- `f2_v2_t4`: `-0.0056`

### Best CDE Improvement

- `f2_v2_t8`: `+0.0407`
- `f2_v2_t4`: `+0.0299`
- `f2_v1_t5`: `+0.0214`
- `f2_v1_t6`: `+0.0143`
- `f2_v2_t10`: `+0.0093`

### CDE Regressions

- `f2_v1_t3`: `-0.0112`
- `f2_v3_t9`: `-0.0170`

### Full Per-Combo Table

- `f2_v1_t3`
  - baseline winner steps: `27`
  - selected winner steps: `29`
  - delta accuracy mean: `-0.0026`
  - accuracy improved rate: `41.9%`
  - delta macro-F1 mean: `-0.0106`
  - delta CDE improve mean: `-0.0112`
  - features used: `59`

- `f2_v1_t5`
  - baseline winner steps: `21`
  - selected winner steps: `17`
  - delta accuracy mean: `+0.0135`
  - accuracy improved rate: `48.9%`
  - delta macro-F1 mean: `+0.0044`
  - delta CDE improve mean: `+0.0214`
  - features used: `59`

- `f2_v1_t6`
  - baseline winner steps: `22`
  - selected winner steps: `21`
  - delta accuracy mean: `+0.0037`
  - accuracy improved rate: `48.9%`
  - delta macro-F1 mean: `-0.0039`
  - delta CDE improve mean: `+0.0143`
  - features used: `59`

- `f2_v2_t10`
  - baseline winner steps: `30`
  - selected winner steps: `22`
  - delta accuracy mean: `+0.0247`
  - accuracy improved rate: `47.8%`
  - delta macro-F1 mean: `+0.0145`
  - delta CDE improve mean: `+0.0093`
  - features used: `59`

- `f2_v2_t4`
  - baseline winner steps: `25`
  - selected winner steps: `26`
  - delta accuracy mean: `-0.0056`
  - accuracy improved rate: `45.2%`
  - delta macro-F1 mean: `+0.0022`
  - delta CDE improve mean: `+0.0299`
  - features used: `86`
  - requested keep count in registry: `94`

- `f2_v2_t8`
  - baseline winner steps: `23`
  - selected winner steps: `24`
  - delta accuracy mean: `+0.0345`
  - accuracy improved rate: `44.6%`
  - delta macro-F1 mean: `+0.0119`
  - delta CDE improve mean: `+0.0407`
  - features used: `59`

- `f2_v3_t9`
  - baseline winner steps: `24`
  - selected winner steps: `26`
  - delta accuracy mean: `+0.0154`
  - accuracy improved rate: `46.8%`
  - delta macro-F1 mean: `-0.0011`
  - delta CDE improve mean: `-0.0170`
  - features used: `66`
  - requested keep count in registry: `68`

- `f7_v1_t4`
  - baseline winner steps: `14`
  - selected winner steps: `21`
  - delta accuracy mean: `-0.0021`
  - accuracy improved rate: `44.6%`
  - delta macro-F1 mean: `-0.0094`
  - delta CDE improve mean: `+0.0063`
  - features used: `24`

## Interpretation

The fixed-policy replay is working as intended:

- each combo reused one stable feature mask across all steps
- all combo metrics were produced for every available step
- the comparison is now on equal footing: each combo is judged with its own fixed preselected features

The strongest fixed-policy combo on raw mean self-improvement is `f2_v2_t8`.

The main mixed-result combos are:

- `f2_v2_t4`: better CDE, slightly worse accuracy
- `f2_v3_t9`: better accuracy, worse CDE
- `f2_v1_t3`: slightly worse on both accuracy and CDE

## Generated Audit Artifacts

- [summary.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/stage1_v2_fixed_policy_audit_20260420_8h_b_pb5170_5355/summary.json)
- [per_combo_summary.csv](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/stage1_v2_fixed_policy_audit_20260420_8h_b_pb5170_5355/per_combo_summary.csv)
- [per_combo_summary.parquet](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/stage1_v2_fixed_policy_audit_20260420_8h_b_pb5170_5355/per_combo_summary.parquet)
- [mask_stability.csv](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/stage1_v2_fixed_policy_audit_20260420_8h_b_pb5170_5355/mask_stability.csv)
- [selected_winner_timeline.csv](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/stage1_v2_fixed_policy_audit_20260420_8h_b_pb5170_5355/selected_winner_timeline.csv)
