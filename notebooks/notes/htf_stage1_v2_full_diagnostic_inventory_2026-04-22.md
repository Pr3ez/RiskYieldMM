# HTF Stage-1-v2 Full Diagnostic Inventory

Date: 2026-04-22
Scope: inventory what Stage-1-v2 already records for combo models, feature behavior, and batch usage, and define the next analysis order from those existing artifacts.

## Bottom line

We already have enough data to do a serious diagnostic pass on:

- combo behavior
- feature selection behavior
- feature importance behavior
- winner-change behavior
- prediction-row behavior
- fixed-policy replay behavior

We do **not** yet have one critical thing persisted explicitly:

- exact per-fold train/validation batch membership for each combo-step

That means:

- we can already answer most questions about which combos work, which features help, and when feature pruning helps
- but for exact fold-window causality at the batch level, we either need to reconstruct windows from the Stage-1 logic or add a new persisted artifact

## 1. What artifacts already exist

### A. Root-level nested-selector artifacts

For the `8h/B` root under [stage1_catboost_8h_b_v2_live](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_b_v2_live):

- [stage1_v2_run_summary.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_b_v2_live/stage1_v2_run_summary.json)
- [stage1_v2_progress.parquet](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_b_v2_live/stage1_v2_progress.parquet)
- [stage1_v2_feature_importance_global.parquet](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_b_v2_live/stage1_v2_feature_importance_global.parquet)
- [stage1_v2_feature_mask_global.parquet](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_b_v2_live/stage1_v2_feature_mask_global.parquet)
- [stage1_v2_feature_stability.parquet](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_b_v2_live/stage1_v2_feature_stability.parquet)
- [stage1_v2_baseline_vs_selected_root.parquet](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_b_v2_live/stage1_v2_baseline_vs_selected_root.parquet)
- [stage1_v2_winner_change_summary.parquet](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_b_v2_live/stage1_v2_winner_change_summary.parquet)

Important facts from the run summary:

- execution mode: `nested_selector`
- completed step rows: `310`
- feature importance rows: `421600`
- feature mask rows: `421600`

So root-level aggregation is already large enough for robust feature-pattern analysis.

### B. Per-step nested-selector artifacts

For each step directory like [batch_5360/stage1_v2](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_b_v2_live/catboost/1m/target_4class/batch_5360/stage1_v2):

- [stage1_v2_step_summary.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_b_v2_live/catboost/1m/target_4class/batch_5360/stage1_v2/stage1_v2_step_summary.json)
- [stage1_v2_combo_metrics.parquet](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_b_v2_live/catboost/1m/target_4class/batch_5360/stage1_v2/stage1_v2_combo_metrics.parquet)
- [stage1_v2_feature_importance_steps.parquet](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_b_v2_live/catboost/1m/target_4class/batch_5360/stage1_v2/stage1_v2_feature_importance_steps.parquet)
- [stage1_v2_selected_features.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_b_v2_live/catboost/1m/target_4class/batch_5360/stage1_v2/stage1_v2_selected_features.json)
- [stage1_v2_selector_fold_outputs.parquet](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_b_v2_live/catboost/1m/target_4class/batch_5360/stage1_v2/stage1_v2_selector_fold_outputs.parquet)
- [stage1_v2_pred_batch_predictions_baseline.parquet](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_b_v2_live/catboost/1m/target_4class/batch_5360/stage1_v2/stage1_v2_pred_batch_predictions_baseline.parquet)
- [stage1_v2_pred_batch_predictions_selected.parquet](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_b_v2_live/catboost/1m/target_4class/batch_5360/stage1_v2/stage1_v2_pred_batch_predictions_selected.parquet)

These are the most important columns already available:

From `stage1_v2_combo_metrics.parquet`:

- `action_key`
- `combo_id`
- `fold_count`
- `val_batches_per_fold`
- `train_batches_per_fold`
- `baseline_accuracy`
- `filtered_accuracy`
- `baseline_cross_direction_error`
- `filtered_cross_direction_error`
- `baseline_rank`
- `filtered_rank`
- `n_features_used`
- `improved_step`

From `stage1_v2_feature_importance_steps.parquet`:

- `action_key`
- `combo_id`
- `pred_batch`
- `feature`
- `importance`
- `baseline_accuracy_step`
- `filtered_accuracy_step`
- `delta_accuracy_step`
- `fold_vote_count`
- `fold_vote_frac`
- `is_selected_step`
- `improved_step`
- `selection_source`

From `stage1_v2_selector_fold_outputs.parquet`:

- `action_key`
- `combo_id`
- `fold_id`
- `n_features_total`
- `n_selected_fold`
- `selected_features_fold`
- `selector_method`
- `selector_shap_calc_type`
- `selector_steps`
- `target_select_count`

From `stage1_v2_selected_features.json`:

- per combo:
  - `fold_count`
  - `val_batches_per_fold`
  - `train_batches_per_fold`
  - `keep_count`
  - `kept_features`
  - `dropped_features`

From `stage1_v2_pred_batch_predictions_selected.parquet`:

- `action_key`
- `combo_id`
- `pred_batch`
- `timestamp`
- `y_true`
- `y_pred`
- `prob_class_0..3`
- `n_features_selected`

This means we already have both:

- step-level aggregate quality
- row-level prediction distributions

### C. Base Stage-1 summary artifacts

The linked base Stage-1 step summary, for example [batch_5360/stage1/stage1_step_summary.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_b_v2_live/catboost/1m/target_4class/batch_5360/stage1/stage1_step_summary.json), gives:

- `train_end_batch`
- `pred_batch`
- `lookback_range_start_batch`
- `lookback_range_end_batch`
- `stage1_grid`
- `fold_windows_total`
- `fold_windows_completed`

This is useful for window-scale context, but not for exact fold membership.

### D. Fixed-policy build artifacts

Under [stage1_v2_fixed_policy_build](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_b_v2_live/stage1_v2_fixed_policy_build):

- [stage1_v2_fixed_policy_build_summary.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_b_v2_live/stage1_v2_fixed_policy_build_summary.json)
- [stage1_v2_fixed_policy_registry.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_b_v2_live/stage1_v2_fixed_policy_registry.json)
- [per_combo_feature_stats.parquet](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_b_v2_live/stage1_v2_fixed_policy_build/per_combo_feature_stats.parquet)
- [combo_policy_summary.parquet](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_b_v2_live/stage1_v2_fixed_policy_build/combo_policy_summary.parquet)
- [final_mask_features.parquet](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_b_v2_live/stage1_v2_fixed_policy_build/final_mask_features.parquet)

Important facts from the fixed-policy build summary:

- source run completed steps: `499`
- incomplete steps: `1`
- combos: `8`
- features: `170`

Important fields from `combo_policy_summary.parquet`:

- `action_key`
- `fold_count`
- `val_batches_per_fold`
- `train_batches_per_fold`
- `final_mask_count`
- `core_keep_count`
- `conditional_keep_count`
- `neutral_keep_count`
- `avoid_count`
- `steps_seen`
- `apply_pruned_steps`
- `improved_steps`
- `baseline_accuracy_mean`
- `filtered_accuracy_mean`
- `delta_accuracy_mean`
- `baseline_cde_mean`
- `filtered_cde_mean`
- `delta_cde_improve_mean`

Important fields from `per_combo_feature_stats.parquet`:

- `action_key`
- `feature`
- `combo_steps`
- `selected_steps`
- `improved_steps`
- `selected_improved_steps`
- `importance_mean_selected`
- `fold_vote_frac_mean_selected`
- `delta_accuracy_mean_selected`
- `delta_accuracy_mean_not_selected`
- `delta_cde_mean_selected`
- `delta_cde_mean_not_selected`
- `selection_rate_all`
- `selection_rate_improved`
- `selection_rate_non_improved`
- `delta_accuracy_selected_lift`
- `delta_cde_selected_lift`
- `improved_selection_lift`

Important fields from `final_mask_features.parquet`:

- all of the above plus:
  - `policy_bucket`
  - `mask_role`

The fixed-policy registry also stores, per combo:

- combo triplet definition
- final mask
- core keep list
- conditional keep list
- avoid list
- support summary
- historical means

So for fixed-policy analysis, we already know exactly which combo uses which final feature set.

## 2. What we can answer now without rerunning anything

### A. Combo-model questions

We can answer:

- Which action keys are best on average by:
  - filtered CDE
  - accuracy
  - macro F1
  - rank
- Which combos improve most from feature pruning versus baseline
- Which combos are robust and which are unstable across windows
- Whether a combo’s usefulness depends on:
  - pred batch
  - batch difficulty
  - root regime/family context
- How often the selected winner differs from the baseline winner

Already available sources:

- `stage1_v2_combo_metrics.parquet`
- `stage1_v2_progress.parquet`
- `stage1_v2_baseline_vs_selected_root.parquet`
- fixed-policy replay combo metrics

### B. Feature-behavior questions

We can answer:

- Which features are repeatedly selected for each combo
- Which features are repeatedly dropped for each combo
- Which features show positive or negative selection lift for:
  - accuracy
  - CDE
  - improved-step selection
- Which features are core vs conditional vs neutral vs avoid under fixed policy
- Which features have high importance but low selection frequency
- Which features are highly selected but low-importance
- Which features help only specific combos

Already available sources:

- `stage1_v2_feature_importance_steps.parquet`
- `stage1_v2_feature_importance_global.parquet`
- `stage1_v2_feature_stability.parquet`
- `stage1_v2_selected_features.json`
- `per_combo_feature_stats.parquet`
- `final_mask_features.parquet`

### C. Batch-context questions

We can answer:

- Which pred batches are difficult globally
- Which pred batches trigger winner changes
- Which pred batches produce large baseline-vs-selected deltas
- Whether certain batches systematically favor certain combos
- Whether selected masks are smaller/larger on difficult batches
- Whether prediction confidence shape changes by batch:
  - entropy
  - margin
  - class concentration
  - directional imbalance

Already available sources:

- `stage1_v2_progress.parquet`
- `stage1_v2_step_summary.json`
- `stage1_v2_pred_batch_predictions_selected.parquet`
- fixed-policy replay outputs

### D. Policy-quality questions

We can answer:

- Whether fixed policy is better than live nested selection for each combo
- Whether the current selector branch is robust
- Which policy families look good ex post but not ex ante
- Whether combo performance drifts over rolling windows

Already available sources:

- fixed-policy registry/build artifacts
- loss-discounted selector audit
- nested selector rolling audit

## 3. What we cannot answer cleanly yet

### Missing artifact 1: exact fold-window batch membership

We know:

- `fold_count`
- `val_batches_per_fold`
- `train_batches_per_fold`
- `lookback_range_start_batch`
- `lookback_range_end_batch`

We do **not** have a simple persisted table like:

- `pred_batch`
- `action_key`
- `fold_id`
- `train_batch_ids`
- `val_batch_ids`
- `train_start_batch`
- `train_end_batch`
- `val_start_batch`
- `val_end_batch`

Why this matters:

- without it, exact batch-level failure attribution is harder
- we can still reconstruct windows from code, but not read them directly from artifacts

### Missing artifact 2: fold-level validation metrics per combo-step

We have fold-level selected feature lists, but we do not have a clean persisted table of:

- fold-level val accuracy
- fold-level val CDE
- fold-level val macro F1
- fold-level training size / validation size

Why this matters:

- it would let us see whether a feature mask or combo is unstable because one fold dominates
- it would let us separate:
  - stable combo, unstable prediction batch
  - unstable fold construction, stable combo

### Missing artifact 3: direct batch metadata table for difficult steps

We can derive some context from predictions and step summaries, but a direct diagnostic table of:

- market volatility level
- label balance
- class skew
- acceptance/pruned status
- helper-regime indicators

per `pred_batch` would make the batch analysis easier and safer.

## 4. What we should analyze next, in order

### Slice 1. Combo diagnostic audit

Goal:

- determine whether the performance ceiling problem is in the underlying combos or only in selection

Questions:

- Which combos dominate by:
  - mean CDE
  - mean accuracy
  - mean rank
  - best-window frequency
- Which combos are best only in specific windows
- Which combos collapse on difficult batches

Inputs:

- fixed-policy run combo metrics
- rolling selector audit window summaries

Deliverable:

- per-combo robust ranking table
- per-window combo best map
- difficult-batch combo leaderboard

### Slice 2. Feature audit by combo

Goal:

- determine whether the main opportunity is feature engineering or combo design

Questions:

- Which features repeatedly help each combo
- Which features are consistently neutral and can be removed
- Which features are combo-specific rather than global
- Which current fixed-policy masks are bloated with neutral features
- Which avoid features still appear in good ex-post windows

Inputs:

- `per_combo_feature_stats.parquet`
- `final_mask_features.parquet`
- `stage1_v2_feature_importance_steps.parquet`
- `stage1_v2_feature_stability.parquet`

Deliverable:

- action-key feature necessity map
- candidate drop list
- candidate feature family gaps

### Slice 3. Batch-difficulty audit

Goal:

- determine what kind of batches break combo selection and feature pruning

Questions:

- Which batches cause:
  - winner changes
  - largest CDE spikes
  - highest disagreement between top combos
  - most unstable prediction probabilities
- Do those batches cluster by:
  - volatility
  - label structure
  - helper/regime state

Inputs:

- `stage1_v2_progress.parquet`
- prediction-row artifacts
- combo metrics

Deliverable:

- difficult-batch inventory
- batch clusters
- failure-mode typology

### Slice 4. Add missing fold-window artifact only if needed

Goal:

- if slices 1 to 3 show unresolved ambiguity around batch-window effects, then persist exact fold-window metadata in future runs

Do **not** do this first.

Reason:

- we already have enough evidence to learn a lot before expanding the artifact contract

## 5. Recommended next action

The next best move is **not** another selector experiment first.

The next best move is:

### Recommendation

Run a structured analysis in this order:

1. combo audit on the fixed-policy run
2. per-combo feature audit
3. difficult-batch audit

Reason:

- selector work is downstream of combo quality and batch difficulty
- if certain combos are structurally weak, no selector will fix that
- if certain feature groups are systematically missing or harmful, that is the cleaner improvement path
- if specific batch contexts break all combos, that points to missing context features or target/batch design issues

## 6. Practical conclusion

We do **not** have an information shortage.

We have:

- enough combo-level data
- enough feature-level data
- enough prediction-row data
- enough fixed-policy data

What we lack is not raw evidence.

What we lack is a structured synthesis over those artifacts.

So the right next move is to mine the artifacts we already have, not to jump straight into more selection logic.

