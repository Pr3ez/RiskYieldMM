# RPF Regime-Gate Walk-Forward

## Gate

- `gate_target`: `future_down_dominant`
- `gate_rule`: `down_extreme >= 2 * up_extreme`
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

- `trial_number`: `4`
- `status`: `ok`
- `gate_target`: `future_down_dominant`
- `feature_ablation`: `group_structural_room+liquidity_volume_pressure+interaction_confluence`
- `feature_count`: `612`
- `threshold_mode`: `validation_sweep`
- `selected_threshold`: `0.75`
- `threshold_constraints_pass`: `True`
- `threshold_constraints_reason`: `pass`
- `objective_metric`: `validation_decision_cost`
- `objective_direction`: `minimize`
- `objective_value`: `0.222778`
- `fp_cost`: `5`
- `fn_cost`: `1`
- `tp_reward`: `0`
- `fbeta_beta`: `0.5`
- `gate_high_quantile`: `0.7`
- `gate_low_quantile`: `0.3`
- `iterations`: `400`
- `depth`: `3`
- `learning_rate`: `0.01`
- `l2_leaf_reg`: `10`
- `early_stopping_rounds`: `100`
- `od_wait`: `100`
- `validation_rows`: `36000`
- `validation_threshold`: `0.75`
- `validation_positive_rate`: `0.22325`
- `validation_predicted_positive_rate`: `0.000472222`
- `validation_prob_mean`: `0.4564`
- `validation_prob_std`: `0.102183`
- `validation_prob_unique`: `3748`
- `validation_accuracy`: `0.777222`
- `validation_balanced_accuracy`: `0.501058`
- `validation_precision`: `1`
- `validation_recall`: `0.00211522`
- `validation_f1`: `0.0042215`
- `validation_fbeta`: `0.0104874`
- `validation_false_positive_rate`: `0`
- `validation_false_negative_rate`: `0.997885`
- `validation_false_discovery_rate`: `0`
- `validation_specificity`: `1`
- `validation_decision_cost`: `8020`
- `validation_decision_cost_per_row`: `0.222778`
- `validation_utility`: `-8020`
- `validation_utility_per_row`: `-0.222778`
- `validation_logloss`: `0.622054`
- `validation_brier`: `0.215169`
- `validation_auc`: `0.699606`
- `validation_tp`: `17`
- `validation_tn`: `27963`
- `validation_fp`: `0`
- `validation_fn`: `8020`
- `prediction_rows`: `3600`
- `prediction_threshold`: `0.75`
- `prediction_positive_rate`: `0.185833`
- `prediction_predicted_positive_rate`: `0`
- `prediction_prob_mean`: `0.509342`
- `prediction_prob_std`: `0.10235`
- `prediction_prob_unique`: `337`
- `prediction_accuracy`: `0.814167`
- `prediction_balanced_accuracy`: `0.5`
- `prediction_precision`: `-`
- `prediction_recall`: `0`
- `prediction_f1`: `-`
- `prediction_fbeta`: `-`
- `prediction_false_positive_rate`: `0`
- `prediction_false_negative_rate`: `1`
- `prediction_false_discovery_rate`: `-`
- `prediction_specificity`: `1`
- `prediction_decision_cost`: `669`
- `prediction_decision_cost_per_row`: `0.185833`
- `prediction_utility`: `-669`
- `prediction_utility_per_row`: `-0.185833`
- `prediction_logloss`: `0.679822`
- `prediction_brier`: `0.243699`
- `prediction_auc`: `0.729273`
- `prediction_tp`: `0`
- `prediction_tn`: `2931`
- `prediction_fp`: `0`
- `prediction_fn`: `669`

## Gated Decision Evaluation

No classifier score path was provided, so gated decision metrics are empty.
