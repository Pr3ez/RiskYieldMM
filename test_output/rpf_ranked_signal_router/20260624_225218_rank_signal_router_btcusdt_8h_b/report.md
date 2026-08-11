# RPF Ranked Signal Router Report

## Scope

- `asset`: `BTCUSDT`
- `root`: `8h/B`
- `candidate_set`: `pruned_reliability_v1`
- `selection_mode`: `prequential_reliability_v1`
- `outer_window_count`: `120`

## Side Summary

- `up`: `{'rows': 28800, 'positive_count': 12381, 'negative_count': 16419, 'predicted_positive_count': 0, 'true_positive_count': 0, 'false_positive_count': 0, 'false_negative_count': 12381, 'true_negative_count': 16419, 'precision': None, 'recall': 0.0, 'false_positive_rate': 0.0, 'false_discovery_rate': None, 'predicted_positive_rate': 0.0, 'base_positive_rate': 0.4298958333333333, 'precision_lift': None, 'decision_cost': 12381.0, 'decision_cost_per_row': 0.4298958333333333, 'decision_cost_per_signal': None, 'active_window_rate': 0.0, 'zero_signal_window_rate': 1.0, 'high_target_window_count': 73, 'high_target_window_capture_rate': 0.0, 'missed_high_target_window_rate': 1.0, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 20.391666666666666, 'ranked_signal_quality': -3.5318619791666666}`
- `down`: `{'rows': 28800, 'positive_count': 9600, 'negative_count': 19200, 'predicted_positive_count': 32, 'true_positive_count': 12, 'false_positive_count': 20, 'false_negative_count': 9588, 'true_negative_count': 19180, 'precision': 0.375, 'recall': 0.00125, 'false_positive_rate': 0.0010416666666666667, 'false_discovery_rate': 0.625, 'predicted_positive_rate': 0.0011111111111111111, 'base_positive_rate': 0.3333333333333333, 'precision_lift': 1.125, 'decision_cost': 9688.0, 'decision_cost_per_row': 0.3363888888888889, 'decision_cost_per_signal': 302.75, 'active_window_rate': 0.09166666666666666, 'zero_signal_window_rate': 0.9083333333333333, 'high_target_window_count': 60, 'high_target_window_capture_rate': 0.05, 'missed_high_target_window_rate': 0.95, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 39.041666666666664, 'ranked_signal_quality': -2.1468359375}`

## Decision Contract

- Validation-only mode selects candidates from validation metrics only.
- Prequential reliability mode selects candidates from prior matured prediction-window reliability after current validation sanity checks.
- Context-rule mode selects candidates by prediction-safe candidate-specific rules loaded from a simulator artifact.
- Prediction metrics are outer evaluation and never choose a candidate.
- If no candidate passes the active selection contract, the side emits no signals for that prediction batch.
- Diagnostic artifacts include validation row scores, validation batch metrics, selected features, and sequence diagnostics.
