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
- `window_mode`: `signal_bank`
- `objective_metric`: `validation_decision_cost`
- `threshold_mode`: `validation_sweep`
- `fp_cost`: `5`
- `fn_cost`: `1`

## Best

- `trial_number`: `11`
- `status`: `ok`
- `gate_target`: `future_down_dominant`
- `feature_ablation`: `only_regime_calendar_state`
- `feature_count`: `209`
- `window_mode`: `signal_bank`
- `positive_batch_min_rate`: `0.8`
- `opposite_batch_max_rate`: `0.2`
- `train_positive_batches`: `80`
- `train_negative_batches`: `160`
- `val_positive_batches`: `20`
- `val_negative_batches`: `40`
- `candidate_lookback_batches`: `2000`
- `label_maturity_embargo_batches`: `1`
- `threshold_mode`: `validation_sweep`
- `selected_threshold`: `0.5`
- `threshold_constraints_pass`: `True`
- `threshold_constraints_reason`: `pass`
- `objective_metric`: `validation_decision_cost`
- `objective_direction`: `minimize`
- `objective_value`: `0.594`
- `fp_cost`: `5`
- `fn_cost`: `1`
- `tp_reward`: `0`
- `fbeta_beta`: `0.5`
- `gate_high_quantile`: `0.7`
- `gate_low_quantile`: `0.3`
- `iterations`: `800`
- `depth`: `2`
- `learning_rate`: `0.02`
- `l2_leaf_reg`: `30`
- `early_stopping_rounds`: `100`
- `od_wait`: `100`
- `validation_rows`: `720000`
- `validation_threshold`: `0.5`
- `validation_positive_rate`: `0.334567`
- `validation_predicted_positive_rate`: `0.0868333`
- `validation_prob_mean`: `0.393429`
- `validation_prob_std`: `0.0823187`
- `validation_prob_unique`: `2585`
- `validation_accuracy`: `0.636844`
- `validation_balanced_accuracy`: `0.500159`
- `validation_precision`: `0.335381`
- `validation_recall`: `0.0870446`
- `validation_f1`: `0.138217`
- `validation_fbeta`: `0.213537`
- `validation_false_positive_rate`: `0.0867271`
- `validation_false_negative_rate`: `0.912955`
- `validation_false_discovery_rate`: `0.664619`
- `validation_specificity`: `0.913273`
- `validation_decision_cost`: `427680`
- `validation_decision_cost_per_row`: `0.594`
- `validation_utility`: `-427680`
- `validation_utility_per_row`: `-0.594`
- `validation_logloss`: `0.673772`
- `validation_brier`: `0.239373`
- `validation_auc`: `0.45124`
- `validation_tp`: `20968`
- `validation_tn`: `437560`
- `validation_fp`: `41552`
- `validation_fn`: `219920`
- `prediction_rows`: `12000`
- `prediction_threshold`: `0.5`
- `prediction_positive_rate`: `0.312583`
- `prediction_predicted_positive_rate`: `0.04`
- `prediction_prob_mean`: `0.403531`
- `prediction_prob_std`: `0.0832495`
- `prediction_prob_unique`: `52`
- `prediction_accuracy`: `0.652583`
- `prediction_balanced_accuracy`: `0.476917`
- `prediction_precision`: `0.0645833`
- `prediction_recall`: `0.00826446`
- `prediction_f1`: `0.0146537`
- `prediction_fbeta`: `0.027332`
- `prediction_false_positive_rate`: `0.0544308`
- `prediction_false_negative_rate`: `0.991736`
- `prediction_false_discovery_rate`: `0.935417`
- `prediction_specificity`: `0.945569`
- `prediction_decision_cost`: `5965`
- `prediction_decision_cost_per_row`: `0.497083`
- `prediction_utility`: `-5965`
- `prediction_utility_per_row`: `-0.497083`
- `prediction_logloss`: `0.670409`
- `prediction_brier`: `0.237884`
- `prediction_auc`: `0.456511`
- `prediction_tp`: `31`
- `prediction_tn`: `7800`
- `prediction_fp`: `449`
- `prediction_fn`: `3720`

## Gated Decision Evaluation

- {'trial_number': 11, 'classifier_side': 'down', 'classifier_score_path': 'test_output/rpf_clean_classification/20260615_181239_classification_cls_extreme_down_ge_2x_up_hvol_v2/prediction_scores.parquet', 'classifier_trial_number': 8, 'rows': 12000, 'gate_active_rate': 0.04, 'ungated_precision': 0.39310995752713546, 'ungated_recall': 0.22207411356971474, 'ungated_false_positive_rate': 0.1558976845678264, 'ungated_predicted_positive_rate': 0.17658333333333334, 'ungated_tp': 833, 'ungated_fp': 1286, 'ungated_tn': 6963, 'ungated_fn': 2918, 'gated_precision': None, 'gated_recall': 0.0, 'gated_false_positive_rate': 0.0, 'gated_predicted_positive_rate': 0.0, 'gated_tp': 0, 'gated_fp': 0, 'gated_tn': 8249, 'gated_fn': 3751, 'both_suppressed_rate': 0.17658333333333334, 'both_active_conflict_rate': None, 'false_positive_reduction': 1.0, 'recall_retained': 0.0, 'precision_improvement': None}
