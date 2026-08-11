# RPF Regime-Gate Walk-Forward

## Gate

- `gate_target`: `future_up_dominant`
- `gate_rule`: `up_extreme >= 2 * down_extreme`
- `asset`: `BTCUSDT`
- `root`: `8h/B`

## Run

- `windows`: `15`
- `feature_ablation`: `group_structural_room+liquidity_volume_pressure+interaction_confluence`
- `feature_count`: `612`
- `objective_metric`: `validation_decision_cost`
- `threshold_mode`: `validation_sweep`
- `fp_cost`: `5`
- `fn_cost`: `1`

## Best

- `trial_number`: `9`
- `status`: `ok`
- `gate_target`: `future_up_dominant`
- `feature_ablation`: `group_structural_room+liquidity_volume_pressure+interaction_confluence`
- `feature_count`: `612`
- `threshold_mode`: `validation_sweep`
- `selected_threshold`: `0.65`
- `threshold_constraints_pass`: `True`
- `threshold_constraints_reason`: `pass`
- `objective_metric`: `validation_decision_cost`
- `objective_direction`: `minimize`
- `objective_value`: `0.560056`
- `fp_cost`: `5`
- `fn_cost`: `1`
- `tp_reward`: `0`
- `fbeta_beta`: `0.5`
- `gate_high_quantile`: `0.7`
- `gate_low_quantile`: `0.3`
- `iterations`: `800`
- `depth`: `2`
- `learning_rate`: `0.01`
- `l2_leaf_reg`: `30`
- `early_stopping_rounds`: `100`
- `od_wait`: `100`
- `validation_rows`: `36000`
- `validation_threshold`: `0.65`
- `validation_positive_rate`: `0.561833`
- `validation_predicted_positive_rate`: `0.00327778`
- `validation_prob_mean`: `0.484915`
- `validation_prob_std`: `0.045516`
- `validation_prob_unique`: `558`
- `validation_accuracy`: `0.440944`
- `validation_balanced_accuracy`: `0.502409`
- `validation_precision`: `0.923729`
- `validation_recall`: `0.0053891`
- `validation_f1`: `0.0107157`
- `validation_fbeta`: `0.026331`
- `validation_false_positive_rate`: `0.000570559`
- `validation_false_negative_rate`: `0.994611`
- `validation_false_discovery_rate`: `0.0762712`
- `validation_specificity`: `0.999429`
- `validation_decision_cost`: `20162`
- `validation_decision_cost_per_row`: `0.560056`
- `validation_utility`: `-20162`
- `validation_utility_per_row`: `-0.560056`
- `validation_logloss`: `0.684135`
- `validation_brier`: `0.245684`
- `validation_auc`: `0.566778`
- `validation_tp`: `109`
- `validation_tn`: `15765`
- `validation_fp`: `9`
- `validation_fn`: `20117`
- `prediction_rows`: `3600`
- `prediction_threshold`: `0.65`
- `prediction_positive_rate`: `0.5225`
- `prediction_predicted_positive_rate`: `0`
- `prediction_prob_mean`: `0.464097`
- `prediction_prob_std`: `0.0596835`
- `prediction_prob_unique`: `55`
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
- `prediction_logloss`: `0.740722`
- `prediction_brier`: `0.272688`
- `prediction_auc`: `0.426385`
- `prediction_tp`: `0`
- `prediction_tn`: `1719`
- `prediction_fp`: `0`
- `prediction_fn`: `1881`

## Gated Decision Evaluation

No classifier score path was provided, so gated decision metrics are empty.
