# RPF Ranked Signal Router Report

## Scope

- `asset`: `BTCUSDT`
- `root`: `8h/B`
- `candidate_set`: `pruned_reliability_v1`
- `selection_mode`: `prequential_reliability_v1`
- `outer_window_count`: `120`

## Side Summary

- `up`: `{'rows': 28800, 'positive_count': 10432, 'negative_count': 18368, 'predicted_positive_count': 0, 'true_positive_count': 0, 'false_positive_count': 0, 'false_negative_count': 10432, 'true_negative_count': 18368, 'precision': None, 'recall': 0.0, 'false_positive_rate': 0.0, 'false_discovery_rate': None, 'predicted_positive_rate': 0.0, 'base_positive_rate': 0.3622222222222222, 'precision_lift': None, 'decision_cost': 10432.0, 'decision_cost_per_row': 0.3622222222222222, 'decision_cost_per_signal': None, 'active_window_rate': 0.0, 'zero_signal_window_rate': 1.0, 'high_target_window_count': 61, 'high_target_window_capture_rate': 0.0, 'missed_high_target_window_rate': 1.0, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 19.941666666666666, 'ranked_signal_quality': -3.5311588541666667}`
- `down`: `{'rows': 28800, 'positive_count': 12017, 'negative_count': 16783, 'predicted_positive_count': 9, 'true_positive_count': 3, 'false_positive_count': 6, 'false_negative_count': 12014, 'true_negative_count': 16777, 'precision': 0.3333333333333333, 'recall': 0.00024964633435965716, 'false_positive_rate': 0.0003575046177679795, 'false_discovery_rate': 0.6666666666666666, 'predicted_positive_rate': 0.0003125, 'base_positive_rate': 0.41725694444444444, 'precision_lift': 0.7988682699509029, 'decision_cost': 12044.0, 'decision_cost_per_row': 0.4181944444444444, 'decision_cost_per_signal': 1338.2222222222222, 'active_window_rate': 0.025, 'zero_signal_window_rate': 0.975, 'high_target_window_count': 70, 'high_target_window_capture_rate': 0.014285714285714285, 'missed_high_target_window_rate': 0.9857142857142858, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 39.125, 'ranked_signal_quality': -2.6649423363095237}`

## Decision Contract

- Validation-only mode selects candidates from validation metrics only.
- Prequential reliability mode selects candidates from prior matured prediction-window reliability after current validation sanity checks.
- Prediction metrics are outer evaluation and never choose a candidate.
- If no candidate passes validation gates, the side emits no signals for that prediction batch.
- Diagnostic artifacts include validation row scores, validation batch metrics, selected features, and sequence diagnostics.
