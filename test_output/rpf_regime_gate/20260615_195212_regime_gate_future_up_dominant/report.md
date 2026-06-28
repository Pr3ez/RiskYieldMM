# RPF Regime-Gate Walk-Forward

## Gate

- `gate_target`: `future_up_dominant`
- `gate_rule`: `up_extreme >= 2 * down_extreme`
- `asset`: `BTCUSDT`
- `root`: `8h/B`

## Run

- `windows`: `15`
- `feature_ablation`: `group_volatility_state+temporal_memory_transforms+rejection_chop`
- `feature_count`: `902`
- `objective_metric`: `validation_decision_cost`
- `threshold_mode`: `validation_sweep`
- `fp_cost`: `5`
- `fn_cost`: `1`

## Best

- `trial_number`: `0`
- `status`: `ok`
- `gate_target`: `future_up_dominant`
- `feature_ablation`: `group_volatility_state+temporal_memory_transforms+rejection_chop`
- `feature_count`: `902`
- `threshold_mode`: `validation_sweep`
- `selected_threshold`: `0.55`
- `threshold_constraints_pass`: `True`
- `threshold_constraints_reason`: `pass`
- `objective_metric`: `validation_decision_cost`
- `objective_direction`: `minimize`
- `objective_value`: `0.555167`
- `fp_cost`: `5`
- `fn_cost`: `1`
- `tp_reward`: `0`
- `fbeta_beta`: `0.5`
- `gate_high_quantile`: `0.7`
- `gate_low_quantile`: `0.3`
- `iterations`: `400`
- `depth`: `2`
- `learning_rate`: `0.01`
- `l2_leaf_reg`: `10`
- `early_stopping_rounds`: `100`
- `od_wait`: `100`
- `validation_rows`: `36000`
- `validation_threshold`: `0.55`
- `validation_positive_rate`: `0.561833`
- `validation_predicted_positive_rate`: `0.00666667`
- `validation_prob_mean`: `0.499535`
- `validation_prob_std`: `0.0110946`
- `validation_prob_unique`: `36`
- `validation_accuracy`: `0.444833`
- `validation_balanced_accuracy`: `0.505933`
- `validation_precision`: `1`
- `validation_recall`: `0.0118659`
- `validation_f1`: `0.0234535`
- `validation_fbeta`: `0.0566412`
- `validation_false_positive_rate`: `0`
- `validation_false_negative_rate`: `0.988134`
- `validation_false_discovery_rate`: `0`
- `validation_specificity`: `1`
- `validation_decision_cost`: `19986`
- `validation_decision_cost_per_row`: `0.555167`
- `validation_utility`: `-19986`
- `validation_utility_per_row`: `-0.555167`
- `validation_logloss`: `0.694569`
- `validation_brier`: `0.250718`
- `validation_auc`: `0.368096`
- `validation_tp`: `240`
- `validation_tn`: `15774`
- `validation_fp`: `0`
- `validation_fn`: `19986`
- `prediction_rows`: `3600`
- `prediction_threshold`: `0.55`
- `prediction_positive_rate`: `0.5225`
- `prediction_predicted_positive_rate`: `0`
- `prediction_prob_mean`: `0.497709`
- `prediction_prob_std`: `0.00639544`
- `prediction_prob_unique`: `15`
- `prediction_accuracy`: `0.4775`
- `prediction_balanced_accuracy`: `0.5`
- `prediction_precision`: `-`
- `prediction_recall`: `0`
- `prediction_f1`: `-`
- `prediction_fbeta`: `-`
- `prediction_false_positive_rate`: `0`
- `prediction_false_negative_rate`: `1`
- `prediction_false_discovery_rate`: `-`
- `prediction_specificity`: `1`
- `prediction_decision_cost`: `1881`
- `prediction_decision_cost_per_row`: `0.5225`
- `prediction_utility`: `-1881`
- `prediction_utility_per_row`: `-0.5225`
- `prediction_logloss`: `0.695297`
- `prediction_brier`: `0.251075`
- `prediction_auc`: `0.450445`
- `prediction_tp`: `0`
- `prediction_tn`: `1719`
- `prediction_fp`: `0`
- `prediction_fn`: `1881`

## Gated Decision Evaluation

No classifier score path was provided, so gated decision metrics are empty.
