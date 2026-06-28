# RPF Regime-Gate Walk-Forward

## Gate

- `gate_target`: `future_down_dominant`
- `gate_rule`: `down_extreme >= 2 * up_extreme`
- `asset`: `BTCUSDT`
- `root`: `8h/B`

## Run

- `windows`: `15`
- `feature_ablation`: `all`
- `feature_count`: `2530`
- `objective_metric`: `validation_decision_cost`
- `threshold_mode`: `validation_sweep`
- `fp_cost`: `5`
- `fn_cost`: `1`

## Best

- `trial_number`: `2`
- `status`: `ok`
- `gate_target`: `future_down_dominant`
- `feature_ablation`: `all`
- `feature_count`: `2530`
- `threshold_mode`: `validation_sweep`
- `selected_threshold`: `0.75`
- `threshold_constraints_pass`: `True`
- `threshold_constraints_reason`: `pass`
- `objective_metric`: `validation_decision_cost`
- `objective_direction`: `minimize`
- `objective_value`: `0.223222`
- `fp_cost`: `5`
- `fn_cost`: `1`
- `tp_reward`: `0`
- `fbeta_beta`: `0.5`
- `gate_high_quantile`: `0.7`
- `gate_low_quantile`: `0.3`
- `iterations`: `400`
- `depth`: `2`
- `learning_rate`: `0.02`
- `l2_leaf_reg`: `10`
- `early_stopping_rounds`: `100`
- `od_wait`: `100`
- `validation_rows`: `36000`
- `validation_threshold`: `0.75`
- `validation_positive_rate`: `0.22325`
- `validation_predicted_positive_rate`: `2.77778e-05`
- `validation_prob_mean`: `0.392407`
- `validation_prob_std`: `0.0908006`
- `validation_prob_unique`: `2114`
- `validation_accuracy`: `0.776778`
- `validation_balanced_accuracy`: `0.500062`
- `validation_precision`: `1`
- `validation_recall`: `0.000124425`
- `validation_f1`: `0.000248818`
- `validation_fbeta`: `0.000621813`
- `validation_false_positive_rate`: `0`
- `validation_false_negative_rate`: `0.999876`
- `validation_false_discovery_rate`: `0`
- `validation_specificity`: `1`
- `validation_decision_cost`: `8036`
- `validation_decision_cost_per_row`: `0.223222`
- `validation_utility`: `-8036`
- `validation_utility_per_row`: `-0.223222`
- `validation_logloss`: `0.577766`
- `validation_brier`: `0.194272`
- `validation_auc`: `0.635256`
- `validation_tp`: `1`
- `validation_tn`: `27963`
- `validation_fp`: `0`
- `validation_fn`: `8036`
- `prediction_rows`: `3600`
- `prediction_threshold`: `0.75`
- `prediction_positive_rate`: `0.185833`
- `prediction_predicted_positive_rate`: `0.0313889`
- `prediction_prob_mean`: `0.47623`
- `prediction_prob_std`: `0.118594`
- `prediction_prob_unique`: `204`
- `prediction_accuracy`: `0.793333`
- `prediction_balanced_accuracy`: `0.498165`
- `prediction_precision`: `0.168142`
- `prediction_recall`: `0.0284006`
- `prediction_f1`: `0.0485934`
- `prediction_fbeta`: `0.0847458`
- `prediction_false_positive_rate`: `0.032071`
- `prediction_false_negative_rate`: `0.971599`
- `prediction_false_discovery_rate`: `0.831858`
- `prediction_specificity`: `0.967929`
- `prediction_decision_cost`: `1120`
- `prediction_decision_cost_per_row`: `0.311111`
- `prediction_utility`: `-1120`
- `prediction_utility_per_row`: `-0.311111`
- `prediction_logloss`: `0.646303`
- `prediction_brier`: `0.22491`
- `prediction_auc`: `0.71202`
- `prediction_tp`: `19`
- `prediction_tn`: `2837`
- `prediction_fp`: `94`
- `prediction_fn`: `650`

## Gated Decision Evaluation

No classifier score path was provided, so gated decision metrics are empty.
