# RPF Ranked Signal Router Report

## Scope

- `asset`: `BTCUSDT`
- `root`: `8h/B`
- `candidate_set`: `pruned_reliability_v1`
- `selection_mode`: `prequential_reliability_v1`
- `outer_window_count`: `2`

## Side Summary

- `up`: `{'rows': 480, 'positive_count': 107, 'negative_count': 373, 'predicted_positive_count': 2, 'true_positive_count': 0, 'false_positive_count': 2, 'false_negative_count': 107, 'true_negative_count': 371, 'precision': 0.0, 'recall': 0.0, 'false_positive_rate': 0.005361930294906166, 'false_discovery_rate': 1.0, 'predicted_positive_rate': 0.004166666666666667, 'base_positive_rate': 0.22291666666666668, 'precision_lift': 0.0, 'decision_cost': 117.0, 'decision_cost_per_row': 0.24375, 'decision_cost_per_signal': 58.5, 'active_window_rate': 0.5, 'zero_signal_window_rate': 0.5, 'high_target_window_count': 1, 'high_target_window_capture_rate': 0.0, 'missed_high_target_window_rate': 1.0, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 21.0, 'ranked_signal_quality': -2.7328125}`
- `down`: `{'rows': 480, 'positive_count': 171, 'negative_count': 309, 'predicted_positive_count': 0, 'true_positive_count': 0, 'false_positive_count': 0, 'false_negative_count': 171, 'true_negative_count': 309, 'precision': None, 'recall': 0.0, 'false_positive_rate': 0.0, 'false_discovery_rate': None, 'predicted_positive_rate': 0.0, 'base_positive_rate': 0.35625, 'precision_lift': None, 'decision_cost': 171.0, 'decision_cost_per_row': 0.35625, 'decision_cost_per_signal': None, 'active_window_rate': 0.0, 'zero_signal_window_rate': 1.0, 'high_target_window_count': 2, 'high_target_window_capture_rate': 0.0, 'missed_high_target_window_rate': 1.0, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 40.0, 'ranked_signal_quality': -3.5625}`

## Decision Contract

- Validation-only mode selects candidates from validation metrics only.
- Prequential reliability mode selects candidates from prior matured prediction-window reliability after current validation sanity checks.
- Prediction metrics are outer evaluation and never choose a candidate.
- If no candidate passes validation gates, the side emits no signals for that prediction batch.
- Diagnostic artifacts include validation row scores, validation batch metrics, selected features, and sequence diagnostics.
