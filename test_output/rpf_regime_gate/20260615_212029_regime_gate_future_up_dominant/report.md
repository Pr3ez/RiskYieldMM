# RPF Regime-Gate Walk-Forward

## Gate

- `gate_target`: `future_up_dominant`
- `gate_rule`: `up_extreme >= 2 * down_extreme`
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

- `trial_number`: `0`
- `status`: `ok`
- `gate_target`: `future_up_dominant`
- `feature_ablation`: `all`
- `feature_count`: `2530`
- `threshold_mode`: `validation_sweep`
- `selected_threshold`: `0.55`
- `threshold_constraints_pass`: `True`
- `threshold_constraints_reason`: `pass`
- `objective_metric`: `validation_decision_cost`
- `objective_direction`: `minimize`
- `objective_value`: `0.551667`
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
- `validation_predicted_positive_rate`: `0.0133333`
- `validation_prob_mean`: `0.490946`
- `validation_prob_std`: `0.0381954`
- `validation_prob_unique`: `118`
- `validation_accuracy`: `0.450444`
- `validation_balanced_accuracy`: `0.510794`
- `validation_precision`: `0.960417`
- `validation_recall`: `0.0227924`
- `validation_f1`: `0.0445282`
- `validation_fbeta`: `0.104082`
- `validation_false_positive_rate`: `0.00120451`
- `validation_false_negative_rate`: `0.977208`
- `validation_false_discovery_rate`: `0.0395833`
- `validation_specificity`: `0.998795`
- `validation_decision_cost`: `19860`
- `validation_decision_cost_per_row`: `0.551667`
- `validation_utility`: `-19860`
- `validation_utility_per_row`: `-0.551667`
- `validation_logloss`: `0.692659`
- `validation_brier`: `0.249819`
- `validation_auc`: `0.404996`
- `validation_tp`: `461`
- `validation_tn`: `15755`
- `validation_fp`: `19`
- `validation_fn`: `19765`
- `prediction_rows`: `3600`
- `prediction_threshold`: `0.55`
- `prediction_positive_rate`: `0.5225`
- `prediction_predicted_positive_rate`: `0`
- `prediction_prob_mean`: `0.480103`
- `prediction_prob_std`: `0.0510189`
- `prediction_prob_unique`: `23`
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
- `prediction_logloss`: `0.674627`
- `prediction_brier`: `0.241097`
- `prediction_auc`: `0.570925`
- `prediction_tp`: `0`
- `prediction_tn`: `1719`
- `prediction_fp`: `0`
- `prediction_fn`: `1881`

## Gated Decision Evaluation

No classifier score path was provided, so gated decision metrics are empty.
