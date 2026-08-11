# RPF Regime-Gate Walk-Forward

## Gate

- `gate_target`: `future_down_dominant`
- `gate_rule`: `down_extreme >= 2 * up_extreme`
- `asset`: `BTCUSDT`
- `root`: `8h/B`

## Run

- `windows`: `50`
- `feature_ablation`: `only_regime_calendar_state`
- `feature_count`: `209`
- `objective_metric`: `validation_decision_cost`
- `threshold_mode`: `validation_sweep`
- `fp_cost`: `5`
- `fn_cost`: `1`

## Best

- `trial_number`: `2`
- `status`: `ok`
- `gate_target`: `future_down_dominant`
- `feature_ablation`: `only_regime_calendar_state`
- `feature_count`: `209`
- `threshold_mode`: `validation_sweep`
- `selected_threshold`: `0.7`
- `threshold_constraints_pass`: `True`
- `threshold_constraints_reason`: `pass`
- `objective_metric`: `validation_decision_cost`
- `objective_direction`: `minimize`
- `objective_value`: `0.335858`
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
- `validation_rows`: `120000`
- `validation_threshold`: `0.7`
- `validation_positive_rate`: `0.340083`
- `validation_predicted_positive_rate`: `0.007125`
- `validation_prob_mean`: `0.438324`
- `validation_prob_std`: `0.0909314`
- `validation_prob_unique`: `1133`
- `validation_accuracy`: `0.666075`
- `validation_balanced_accuracy`: `0.509399`
- `validation_precision`: `0.932164`
- `validation_recall`: `0.0195295`
- `validation_f1`: `0.0382575`
- `validation_fbeta`: `0.0900972`
- `validation_false_positive_rate`: `0.000732416`
- `validation_false_negative_rate`: `0.98047`
- `validation_false_discovery_rate`: `0.0678363`
- `validation_specificity`: `0.999268`
- `validation_decision_cost`: `40303`
- `validation_decision_cost_per_row`: `0.335858`
- `validation_utility`: `-40303`
- `validation_utility_per_row`: `-0.335858`
- `validation_logloss`: `0.647201`
- `validation_brier`: `0.22783`
- `validation_auc`: `0.593292`
- `validation_tp`: `797`
- `validation_tn`: `79132`
- `validation_fp`: `58`
- `validation_fn`: `40013`
- `prediction_rows`: `12000`
- `prediction_threshold`: `0.7`
- `prediction_positive_rate`: `0.312583`
- `prediction_predicted_positive_rate`: `0.005`
- `prediction_prob_mean`: `0.452982`
- `prediction_prob_std`: `0.0750018`
- `prediction_prob_unique`: `122`
- `prediction_accuracy`: `0.692417`
- `prediction_balanced_accuracy`: `0.507998`
- `prediction_precision`: `1`
- `prediction_recall`: `0.0159957`
- `prediction_f1`: `0.0314878`
- `prediction_fbeta`: `0.0751691`
- `prediction_false_positive_rate`: `0`
- `prediction_false_negative_rate`: `0.984004`
- `prediction_false_discovery_rate`: `0`
- `prediction_specificity`: `1`
- `prediction_decision_cost`: `3691`
- `prediction_decision_cost_per_row`: `0.307583`
- `prediction_utility`: `-3691`
- `prediction_utility_per_row`: `-0.307583`
- `prediction_logloss`: `0.665763`
- `prediction_brier`: `0.23654`
- `prediction_auc`: `0.52129`
- `prediction_tp`: `60`
- `prediction_tn`: `8249`
- `prediction_fp`: `0`
- `prediction_fn`: `3691`

## Gated Decision Evaluation

- {'trial_number': 2, 'classifier_side': 'down', 'classifier_score_path': 'test_output/rpf_clean_classification/20260615_181239_classification_cls_extreme_down_ge_2x_up_hvol_v2/prediction_scores.parquet', 'classifier_trial_number': 8, 'rows': 12000, 'gate_active_rate': 0.005, 'ungated_precision': 0.39310995752713546, 'ungated_recall': 0.22207411356971474, 'ungated_false_positive_rate': 0.1558976845678264, 'ungated_predicted_positive_rate': 0.17658333333333334, 'ungated_tp': 833, 'ungated_fp': 1286, 'ungated_tn': 6963, 'ungated_fn': 2918, 'gated_precision': 1.0, 'gated_recall': 0.015995734470807786, 'gated_false_positive_rate': 0.0, 'gated_predicted_positive_rate': 0.005, 'gated_tp': 60, 'gated_fp': 0, 'gated_tn': 8249, 'gated_fn': 3691, 'both_suppressed_rate': 0.17158333333333334, 'both_active_conflict_rate': None, 'false_positive_reduction': 1.0, 'recall_retained': 0.07202881152460985, 'precision_improvement': 0.6068900424728645}
