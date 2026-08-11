# RPF Ranked Signal Router Report

## Scope

- `asset`: `BTCUSDT`
- `root`: `8h/B`
- `candidate_set`: `pruned_reliability_v1`
- `selection_mode`: `prequential_reliability_v1`
- `outer_window_count`: `120`

## Side Summary

- `up`: `{'rows': 28800, 'positive_count': 10432, 'negative_count': 18368, 'predicted_positive_count': 0, 'true_positive_count': 0, 'false_positive_count': 0, 'false_negative_count': 10432, 'true_negative_count': 18368, 'precision': None, 'recall': 0.0, 'false_positive_rate': 0.0, 'false_discovery_rate': None, 'predicted_positive_rate': 0.0, 'base_positive_rate': 0.3622222222222222, 'precision_lift': None, 'decision_cost': 10432.0, 'decision_cost_per_row': 0.3622222222222222, 'decision_cost_per_signal': None, 'active_window_rate': 0.0, 'zero_signal_window_rate': 1.0, 'high_target_window_count': 61, 'high_target_window_capture_rate': 0.0, 'missed_high_target_window_rate': 1.0, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 21.183333333333334, 'ranked_signal_quality': -3.5330989583333334}`
- `down`: `{'rows': 28800, 'positive_count': 12017, 'negative_count': 16783, 'predicted_positive_count': 11, 'true_positive_count': 11, 'false_positive_count': 0, 'false_negative_count': 12006, 'true_negative_count': 16783, 'precision': 1.0, 'recall': 0.0009153698926520762, 'false_positive_rate': 0.0, 'false_discovery_rate': 0.0, 'predicted_positive_rate': 0.00038194444444444446, 'base_positive_rate': 0.41725694444444444, 'precision_lift': 2.396604809852709, 'decision_cost': 12006.0, 'decision_cost_per_row': 0.416875, 'decision_cost_per_signal': 1091.4545454545455, 'active_window_rate': 0.03333333333333333, 'zero_signal_window_rate': 0.9666666666666667, 'high_target_window_count': 70, 'high_target_window_capture_rate': 0.05714285714285714, 'missed_high_target_window_rate': 0.9428571428571428, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 39.125, 'ranked_signal_quality': 1.8768387119673224}`

## Decision Contract

- Validation-only mode selects candidates from validation metrics only.
- Prequential reliability mode selects candidates from prior matured prediction-window reliability after current validation sanity checks.
- Prediction metrics are outer evaluation and never choose a candidate.
- If no candidate passes validation gates, the side emits no signals for that prediction batch.
- Diagnostic artifacts include validation row scores, validation batch metrics, selected features, and sequence diagnostics.
