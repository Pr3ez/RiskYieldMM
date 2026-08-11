# RPF Regime-Gate Walk-Forward

## Gate

- `gate_target`: `future_up_dominant`
- `gate_rule`: `up_extreme >= 2 * down_extreme`
- `asset`: `BTCUSDT`
- `root`: `8h/B`

## Run

- `windows`: `5`
- `feature_ablation`: `only_regime_calendar_state`
- `feature_count`: `209`
- `objective_metric`: `validation_decision_cost`
- `threshold_mode`: `validation_sweep`
- `fp_cost`: `5`
- `fn_cost`: `1`

## Best

- `trial_number`: `0`
- `status`: `rejected:low_prediction_unique`
- `gate_target`: `future_up_dominant`
- `feature_ablation`: `only_regime_calendar_state`
- `feature_count`: `209`
- `threshold_mode`: `validation_sweep`
- `selected_threshold`: `0.55`
- `threshold_constraints_pass`: `True`
- `threshold_constraints_reason`: `pass`
- `objective_metric`: `validation_decision_cost`
- `objective_direction`: `minimize`
- `objective_value`: `0.625`
- `fp_cost`: `5`
- `fn_cost`: `1`
- `tp_reward`: `0`
- `fbeta_beta`: `0.5`
- `gate_high_quantile`: `0.7`
- `gate_low_quantile`: `0.3`
- `iterations`: `50`
- `depth`: `2`
- `learning_rate`: `0.02`
- `l2_leaf_reg`: `10`
- `early_stopping_rounds`: `20`
- `od_wait`: `20`
- `validation_rows`: `12000`
- `validation_threshold`: `0.55`
- `validation_positive_rate`: `0.625`
- `validation_predicted_positive_rate`: `0`
- `validation_prob_mean`: `0.503606`
- `validation_prob_std`: `0.00931665`
- `validation_prob_unique`: `12`
- `validation_accuracy`: `0.375`
- `validation_balanced_accuracy`: `0.5`
- `validation_precision`: `-`
- `validation_recall`: `0`
- `validation_f1`: `-`
- `validation_fbeta`: `-`
- `validation_false_positive_rate`: `0`
- `validation_false_negative_rate`: `1`
- `validation_false_discovery_rate`: `-`
- `validation_specificity`: `1`
- `validation_decision_cost`: `7500`
- `validation_decision_cost_per_row`: `0.625`
- `validation_utility`: `-7500`
- `validation_utility_per_row`: `-0.625`
- `validation_logloss`: `0.691912`
- `validation_brier`: `0.249383`
- `validation_auc`: `0.503712`
- `validation_tp`: `0`
- `validation_tn`: `4500`
- `validation_fp`: `0`
- `validation_fn`: `7500`
- `prediction_rows`: `1200`
- `prediction_threshold`: `0.55`
- `prediction_positive_rate`: `0.384167`
- `prediction_predicted_positive_rate`: `0`
- `prediction_prob_mean`: `0.504994`
- `prediction_prob_std`: `0.0091208`
- `prediction_prob_unique`: `5`
- `prediction_accuracy`: `0.615833`
- `prediction_balanced_accuracy`: `0.5`
- `prediction_precision`: `-`
- `prediction_recall`: `0`
- `prediction_f1`: `-`
- `prediction_fbeta`: `-`
- `prediction_false_positive_rate`: `0`
- `prediction_false_negative_rate`: `1`
- `prediction_false_discovery_rate`: `-`
- `prediction_specificity`: `1`
- `prediction_decision_cost`: `461`
- `prediction_decision_cost_per_row`: `0.384167`
- `prediction_utility`: `-461`
- `prediction_utility_per_row`: `-0.384167`
- `prediction_logloss`: `0.695163`
- `prediction_brier`: `0.251007`
- `prediction_auc`: `0.512681`
- `prediction_tp`: `0`
- `prediction_tn`: `739`
- `prediction_fp`: `0`
- `prediction_fn`: `461`

## Gated Decision Evaluation

No classifier score path was provided, so gated decision metrics are empty.
