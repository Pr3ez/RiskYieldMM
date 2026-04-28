# HTF Walk-Forward Ensemble Method Audit

Date: 2026-04-02

## Scope

Determine which walk-forward ensemble or final-prediction methods were actually used in the historical HTF Stage-1 workflow, and whether the workflow was selecting the final method by directional accuracy plus coverage.

Primary artifact audited:

- `data/htf_backtest_results/stage1_catboost_live/catboost/1m/target_4class/combo_match_analysis/2026-02-13_13-53-39`

Derived comparison artifacts:

- `test_output/htf_walkforward_ensemble_audit/ensemble_method_comparison_20260402.csv`
- `test_output/htf_walkforward_ensemble_audit/ensemble_method_comparison_20260402.json`

## What The Workflow Was Actually Doing

There were three different selection layers:

1. Triplet portfolio selection
   - Defined in `scripts/htf_backtest/catboost/stage1_analysis.py`.
   - For directional targets, the primary selection metric was `cross_direction_error` with `minimize` direction, not directional accuracy.
   - Portfolio construction then optimized `mean_best_acc` and `cov70` coverage across contexts.
   - Relevant code:
     - `scripts/htf_backtest/catboost/stage1_analysis.py:128-135`
     - `scripts/htf_backtest/catboost/stage1_analysis.py:703-739`
     - `scripts/htf_backtest/catboost/stage1_analysis.py:1028-1074`
     - `scripts/htf_backtest/catboost/stage1_analysis.py:1149-1184`

2. Per-step winner combo selection
   - Defined in `notebooks/htf_stage1.py`.
   - The step winner was chosen by:
     1. `accuracy` descending
     2. `macro_f1` descending
     3. `cross_direction_error` ascending
     4. `action_key` ascending
   - This is a hindsight step winner because it uses the realized `y_true` for the same prediction batch.
   - Relevant code:
     - `notebooks/htf_stage1.py:644-678`
     - `notebooks/htf_stage1.py:691-706`

3. Live-style final ensemble analysis
   - Defined in `notebooks/htf_stage1.py`.
   - The workflow built a `winner12` set from the 12 most frequent winner combos, then created a capability-weighted consensus.
   - The weights were normalized **historical max accuracy** per combo, not directional accuracy.
   - Final row-level consensus outputs were:
     - `weighted_majority_class`
     - `weighted_majority_direction`
     - probability-style aggregates `p_class_*`, `p_down`, `p_up`
     - confidence/risk diagnostics
   - Relevant code:
     - `notebooks/htf_stage1.py:2750-2769`
     - `notebooks/htf_stage1.py:3074-3158`

## Important Conclusion

The historical workflow was **not** selecting the final ensemble by directional accuracy plus coverage.

Instead:

- triplet selection used `cross_direction_error` plus coverage-style portfolio metrics (`cov70`, `mean_best_acc`)
- per-step winner selection used `accuracy` first
- final consensus weighting used normalized max accuracy

So if we want a true "best by directional accuracy and coverage" rule, that would be a **new explicit selection policy**, not the old one.

## Methods Actually Present In The Saved Final-Prediction Layer

Using the saved `winner12` combo-match artifacts, the methods available for final-prediction comparison were:

1. `winner_combo_class`
   - Per-step hindsight winner combo applied row-by-row inside that batch.
   - Coverage: full.
   - Not live-deployable because the winner is chosen using realized batch truth.

2. `weighted_majority_class`
   - Capability-weighted class consensus across the 12 winner combos.
   - Coverage: full.
   - Live-style ensemble method.

3. `weighted_majority_direction`
   - Capability-weighted direction consensus across the 12 winner combos.
   - Coverage: full.
   - Live-style ensemble method.

4. `all12_unanimous_class`
   - Only emit a prediction when all 12 combos predict the exact same class.
   - Coverage: sparse.
   - Diagnostic/high-agreement filter, not the default final predictor.

5. `all12_unanimous_direction`
   - Only emit a prediction when all 12 combos agree on direction.
   - Coverage: sparse.
   - Diagnostic/high-agreement filter, not the default final predictor.

## Directional Accuracy vs Coverage

Computed from:

- `winner12_prediction_rows_pred_dedup.parquet`
- `winner12_row_consensus_signals.parquet`
- `winner12_batch_consensus_signals.parquet`

Results:

| method | directional_accuracy | row_coverage | step_coverage | class_accuracy | note |
|---|---:|---:|---:|---:|---|
| `winner_combo_class` | `0.729758` | `1.000000` | `1.000000` | `0.537883` | hindsight/oracle baseline, not deployable |
| `all12_unanimous_class` | `0.538084` | `0.049233` | `0.324000` | `0.321936` | tiny coverage |
| `all12_unanimous_direction` | `0.526144` | `0.150925` | `0.630000` | n/a | sparse directional filter |
| `weighted_majority_class` | `0.519267` | `1.000000` | `1.000000` | `0.302175` | best full-coverage live-style method by directional accuracy |
| `weighted_majority_direction` | `0.519000` | `1.000000` | `1.000000` | n/a | effectively tied with weighted class consensus |

## Which Method Was Best

If oracle hindsight is allowed:

- Best by directional accuracy and coverage was `winner_combo_class`.
- But this is not valid as a production final predictor because the winner combo is selected using realized truth from the same batch.

If only live-style methods are allowed:

- Best practical full-coverage method was `weighted_majority_class`, with `0.519267` directional accuracy at `100%` row coverage and `100%` step coverage.
- `weighted_majority_direction` was effectively tied, slightly worse by a very small margin.

If we allow low-coverage agreement filters:

- `all12_unanimous_direction` improved directional accuracy to `0.526144`, but row coverage dropped to `15.09%`.
- `all12_unanimous_class` improved directional accuracy further to `0.538084`, but row coverage dropped to `4.92%`.

So the best trade-off under the historical saved methods was:

- full coverage: `weighted_majority_class`
- conservative high-agreement filter: `all12_unanimous_direction`

## Bottom Line

The old Stage-1 workflow mixed:

- coverage-first combo portfolio construction
- hindsight per-step winner selection
- accuracy-weighted `winner12` consensus

It did **not** have one clean, explicit rule saying:

> choose the final ensemble method by directional accuracy plus coverage

For future work, if that is the desired decision rule, it should be codified explicitly and separated from:

- combo/triplet selection
- step-winner analysis
- live-style ensemble prediction
