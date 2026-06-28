# RPF Regime-Gate Walk-Forward

## Gate

- `gate_target`: `future_down_dominant`
- `gate_rule`: `down_extreme >= 2 * up_extreme`
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

- `trial_number`: `5`
- `status`: `ok`
- `gate_target`: `future_down_dominant`
- `feature_ablation`: `group_volatility_state+temporal_memory_transforms+rejection_chop`
- `feature_count`: `902`
- `threshold_mode`: `validation_sweep`
- `selected_threshold`: `0.6`
- `threshold_constraints_pass`: `True`
- `threshold_constraints_reason`: `pass`
- `objective_metric`: `validation_decision_cost`
- `objective_direction`: `minimize`
- `objective_value`: `0.222`
- `fp_cost`: `5`
- `fn_cost`: `1`
- `tp_reward`: `0`
- `fbeta_beta`: `0.5`
- `gate_high_quantile`: `0.7`
- `gate_low_quantile`: `0.3`
- `iterations`: `400`
- `depth`: `3`
- `learning_rate`: `0.01`
- `l2_leaf_reg`: `30`
- `early_stopping_rounds`: `100`
- `od_wait`: `100`
- `validation_rows`: `36000`
- `validation_threshold`: `0.6`
- `validation_positive_rate`: `0.22325`
- `validation_predicted_positive_rate`: `0.00191667`
- `validation_prob_mean`: `0.368329`
- `validation_prob_std`: `0.0824801`
- `validation_prob_unique`: `6357`
- `validation_accuracy`: `0.778444`
- `validation_balanced_accuracy`: `0.503972`
- `validation_precision`: `0.942029`
- `validation_recall`: `0.00808759`
- `validation_f1`: `0.0160375`
- `validation_fbeta`: `0.0390954`
- `validation_false_positive_rate`: `0.000143046`
- `validation_false_negative_rate`: `0.991912`
- `validation_false_discovery_rate`: `0.057971`
- `validation_specificity`: `0.999857`
- `validation_decision_cost`: `7992`
- `validation_decision_cost_per_row`: `0.222`
- `validation_utility`: `-7992`
- `validation_utility_per_row`: `-0.222`
- `validation_logloss`: `0.586674`
- `validation_brier`: `0.198125`
- `validation_auc`: `0.530843`
- `validation_tp`: `65`
- `validation_tn`: `27959`
- `validation_fp`: `4`
- `validation_fn`: `7972`
- `prediction_rows`: `3600`
- `prediction_threshold`: `0.6`
- `prediction_positive_rate`: `0.185833`
- `prediction_predicted_positive_rate`: `0.0166667`
- `prediction_prob_mean`: `0.41956`
- `prediction_prob_std`: `0.0888918`
- `prediction_prob_unique`: `672`
- `prediction_accuracy`: `0.808056`
- `prediction_balanced_accuracy`: `0.507206`
- `prediction_precision`: `0.316667`
- `prediction_recall`: `0.0284006`
- `prediction_f1`: `0.0521262`
- `prediction_fbeta`: `0.10451`
- `prediction_false_positive_rate`: `0.0139884`
- `prediction_false_negative_rate`: `0.971599`
- `prediction_false_discovery_rate`: `0.683333`
- `prediction_specificity`: `0.986012`
- `prediction_decision_cost`: `855`
- `prediction_decision_cost_per_row`: `0.2375`
- `prediction_utility`: `-855`
- `prediction_utility_per_row`: `-0.2375`
- `prediction_logloss`: `0.567872`
- `prediction_brier`: `0.18975`
- `prediction_auc`: `0.763783`
- `prediction_tp`: `19`
- `prediction_tn`: `2890`
- `prediction_fp`: `41`
- `prediction_fn`: `650`

## Gated Decision Evaluation

No classifier score path was provided, so gated decision metrics are empty.
