# RPF Regime-Gate Walk-Forward

## Gate

- `gate_target`: `future_down_dominant`
- `gate_rule`: `down_extreme >= 2 * up_extreme`
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

- `trial_number`: `3`
- `status`: `ok`
- `gate_target`: `future_down_dominant`
- `feature_ablation`: `only_regime_calendar_state`
- `feature_count`: `209`
- `threshold_mode`: `validation_sweep`
- `selected_threshold`: `0.65`
- `threshold_constraints_pass`: `True`
- `threshold_constraints_reason`: `pass`
- `objective_metric`: `validation_decision_cost`
- `objective_direction`: `minimize`
- `objective_value`: `0.221583`
- `fp_cost`: `5`
- `fn_cost`: `1`
- `tp_reward`: `0`
- `fbeta_beta`: `0.5`
- `gate_high_quantile`: `0.7`
- `gate_low_quantile`: `0.3`
- `iterations`: `400`
- `depth`: `2`
- `learning_rate`: `0.02`
- `l2_leaf_reg`: `30`
- `early_stopping_rounds`: `100`
- `od_wait`: `100`
- `validation_rows`: `36000`
- `validation_threshold`: `0.65`
- `validation_positive_rate`: `0.22325`
- `validation_predicted_positive_rate`: `0.00166667`
- `validation_prob_mean`: `0.431907`
- `validation_prob_std`: `0.0793213`
- `validation_prob_unique`: `453`
- `validation_accuracy`: `0.778417`
- `validation_balanced_accuracy`: `0.503733`
- `validation_precision`: `1`
- `validation_recall`: `0.00746547`
- `validation_f1`: `0.0148203`
- `validation_fbeta`: `0.036245`
- `validation_false_positive_rate`: `0`
- `validation_false_negative_rate`: `0.992535`
- `validation_false_discovery_rate`: `0`
- `validation_specificity`: `1`
- `validation_decision_cost`: `7977`
- `validation_decision_cost_per_row`: `0.221583`
- `validation_utility`: `-7977`
- `validation_utility_per_row`: `-0.221583`
- `validation_logloss`: `0.61563`
- `validation_brier`: `0.212453`
- `validation_auc`: `0.598677`
- `validation_tp`: `60`
- `validation_tn`: `27963`
- `validation_fp`: `0`
- `validation_fn`: `7977`
- `prediction_rows`: `3600`
- `prediction_threshold`: `0.65`
- `prediction_positive_rate`: `0.185833`
- `prediction_predicted_positive_rate`: `0.0166667`
- `prediction_prob_mean`: `0.454692`
- `prediction_prob_std`: `0.0798696`
- `prediction_prob_unique`: `46`
- `prediction_accuracy`: `0.830833`
- `prediction_balanced_accuracy`: `0.544843`
- `prediction_precision`: `1`
- `prediction_recall`: `0.0896861`
- `prediction_f1`: `0.164609`
- `prediction_fbeta`: `0.330033`
- `prediction_false_positive_rate`: `0`
- `prediction_false_negative_rate`: `0.910314`
- `prediction_false_discovery_rate`: `0`
- `prediction_specificity`: `1`
- `prediction_decision_cost`: `609`
- `prediction_decision_cost_per_row`: `0.169167`
- `prediction_utility`: `-609`
- `prediction_utility_per_row`: `-0.169167`
- `prediction_logloss`: `0.612267`
- `prediction_brier`: `0.21039`
- `prediction_auc`: `0.706456`
- `prediction_tp`: `60`
- `prediction_tn`: `2931`
- `prediction_fp`: `0`
- `prediction_fn`: `609`

## Gated Decision Evaluation

No classifier score path was provided, so gated decision metrics are empty.
