# RPF Regime-Gate Walk-Forward

## Gate

- `gate_target`: `future_up_dominant`
- `gate_rule`: `up_extreme >= 2 * down_extreme`
- `asset`: `BTCUSDT`
- `root`: `8h/B`

## Run

- `windows`: `15`
- `feature_ablation`: `only_regime_calendar_state`
- `feature_count`: `209`
- `objective_metric`: `validation_decision_cost`
- `threshold_mode`: `validation_sweep`
- `fp_cost`: `5`
- `fn_cost`: `1`

## Best

- `trial_number`: `6`
- `status`: `ok`
- `gate_target`: `future_up_dominant`
- `feature_ablation`: `only_regime_calendar_state`
- `feature_count`: `209`
- `threshold_mode`: `validation_sweep`
- `selected_threshold`: `0.6`
- `threshold_constraints_pass`: `True`
- `threshold_constraints_reason`: `pass`
- `objective_metric`: `validation_decision_cost`
- `objective_direction`: `minimize`
- `objective_value`: `0.5555`
- `fp_cost`: `5`
- `fn_cost`: `1`
- `tp_reward`: `0`
- `fbeta_beta`: `0.5`
- `gate_high_quantile`: `0.7`
- `gate_low_quantile`: `0.3`
- `iterations`: `400`
- `depth`: `3`
- `learning_rate`: `0.02`
- `l2_leaf_reg`: `10`
- `early_stopping_rounds`: `100`
- `od_wait`: `100`
- `validation_rows`: `36000`
- `validation_threshold`: `0.6`
- `validation_positive_rate`: `0.561833`
- `validation_predicted_positive_rate`: `0.0075`
- `validation_prob_mean`: `0.494339`
- `validation_prob_std`: `0.0425814`
- `validation_prob_unique`: `252`
- `validation_accuracy`: `0.445278`
- `validation_balanced_accuracy`: `0.50628`
- `validation_precision`: `0.974074`
- `validation_recall`: `0.0130031`
- `validation_f1`: `0.0256635`
- `validation_fbeta`: `0.0617197`
- `validation_false_positive_rate`: `0.000443768`
- `validation_false_negative_rate`: `0.986997`
- `validation_false_discovery_rate`: `0.0259259`
- `validation_specificity`: `0.999556`
- `validation_decision_cost`: `19998`
- `validation_decision_cost_per_row`: `0.5555`
- `validation_utility`: `-19998`
- `validation_utility_per_row`: `-0.5555`
- `validation_logloss`: `0.688271`
- `validation_brier`: `0.247707`
- `validation_auc`: `0.503638`
- `validation_tp`: `263`
- `validation_tn`: `15767`
- `validation_fp`: `7`
- `validation_fn`: `19963`
- `prediction_rows`: `3600`
- `prediction_threshold`: `0.6`
- `prediction_positive_rate`: `0.5225`
- `prediction_predicted_positive_rate`: `0`
- `prediction_prob_mean`: `0.489101`
- `prediction_prob_std`: `0.0490145`
- `prediction_prob_unique`: `32`
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
- `prediction_logloss`: `0.723592`
- `prediction_brier`: `0.264327`
- `prediction_auc`: `0.414767`
- `prediction_tp`: `0`
- `prediction_tn`: `1719`
- `prediction_fp`: `0`
- `prediction_fn`: `1881`

## Gated Decision Evaluation

No classifier score path was provided, so gated decision metrics are empty.
