# RPF Regime-Gate Walk-Forward

## Gate

- `gate_target`: `future_down_dominant`
- `gate_rule`: `down_extreme >= 2 * up_extreme`
- `asset`: `BTCUSDT`
- `root`: `8h/B`

## Run

- `windows`: `15`
- `feature_ablation`: `group_structural_room+acceptance_persistence+spike_breakout+liquidity_volume_pressure`
- `feature_count`: `831`
- `objective_metric`: `validation_decision_cost`
- `threshold_mode`: `validation_sweep`
- `fp_cost`: `5`
- `fn_cost`: `1`

## Best

- `trial_number`: `7`
- `status`: `ok`
- `gate_target`: `future_down_dominant`
- `feature_ablation`: `group_structural_room+acceptance_persistence+spike_breakout+liquidity_volume_pressure`
- `feature_count`: `831`
- `threshold_mode`: `validation_sweep`
- `selected_threshold`: `0.7`
- `threshold_constraints_pass`: `True`
- `threshold_constraints_reason`: `pass`
- `objective_metric`: `validation_decision_cost`
- `objective_direction`: `minimize`
- `objective_value`: `0.221833`
- `fp_cost`: `5`
- `fn_cost`: `1`
- `tp_reward`: `0`
- `fbeta_beta`: `0.5`
- `gate_high_quantile`: `0.7`
- `gate_low_quantile`: `0.3`
- `iterations`: `400`
- `depth`: `3`
- `learning_rate`: `0.02`
- `l2_leaf_reg`: `30`
- `early_stopping_rounds`: `100`
- `od_wait`: `100`
- `validation_rows`: `36000`
- `validation_threshold`: `0.7`
- `validation_positive_rate`: `0.22325`
- `validation_predicted_positive_rate`: `0.00275`
- `validation_prob_mean`: `0.439755`
- `validation_prob_std`: `0.0966993`
- `validation_prob_unique`: `3641`
- `validation_accuracy`: `0.779056`
- `validation_balanced_accuracy`: `0.505518`
- `validation_precision`: `0.919192`
- `validation_recall`: `0.0113226`
- `validation_f1`: `0.0223697`
- `validation_fbeta`: `0.0539547`
- `validation_false_positive_rate`: `0.000286092`
- `validation_false_negative_rate`: `0.988677`
- `validation_false_discovery_rate`: `0.0808081`
- `validation_specificity`: `0.999714`
- `validation_decision_cost`: `7986`
- `validation_decision_cost_per_row`: `0.221833`
- `validation_utility`: `-7986`
- `validation_utility_per_row`: `-0.221833`
- `validation_logloss`: `0.619872`
- `validation_brier`: `0.214429`
- `validation_auc`: `0.633634`
- `validation_tp`: `91`
- `validation_tn`: `27955`
- `validation_fp`: `8`
- `validation_fn`: `7946`
- `prediction_rows`: `3600`
- `prediction_threshold`: `0.7`
- `prediction_positive_rate`: `0.185833`
- `prediction_predicted_positive_rate`: `0.0144444`
- `prediction_prob_mean`: `0.51152`
- `prediction_prob_std`: `0.089782`
- `prediction_prob_unique`: `350`
- `prediction_accuracy`: `0.8075`
- `prediction_balanced_accuracy`: `0.503981`
- `prediction_precision`: `0.269231`
- `prediction_recall`: `0.0209268`
- `prediction_f1`: `0.038835`
- `prediction_fbeta`: `0.0798176`
- `prediction_false_positive_rate`: `0.0129649`
- `prediction_false_negative_rate`: `0.979073`
- `prediction_false_discovery_rate`: `0.730769`
- `prediction_specificity`: `0.987035`
- `prediction_decision_cost`: `845`
- `prediction_decision_cost_per_row`: `0.234722`
- `prediction_utility`: `-845`
- `prediction_utility_per_row`: `-0.234722`
- `prediction_logloss`: `0.677415`
- `prediction_brier`: `0.241707`
- `prediction_auc`: `0.767336`
- `prediction_tp`: `14`
- `prediction_tn`: `2893`
- `prediction_fp`: `38`
- `prediction_fn`: `655`

## Gated Decision Evaluation

No classifier score path was provided, so gated decision metrics are empty.
