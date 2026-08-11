# RPF Ranked Signal Router Report

## Scope

- `asset`: `BTCUSDT`
- `root`: `8h/B`
- `candidate_set`: `pruned_reliability_v1`
- `selection_mode`: `prequential_reliability_v1`
- `outer_window_count`: `120`

## Side Summary

- `up`: `{'rows': 28800, 'positive_count': 9005, 'negative_count': 19795, 'predicted_positive_count': 0, 'true_positive_count': 0, 'false_positive_count': 0, 'false_negative_count': 9005, 'true_negative_count': 19795, 'precision': None, 'recall': 0.0, 'false_positive_rate': 0.0, 'false_discovery_rate': None, 'predicted_positive_rate': 0.0, 'base_positive_rate': 0.31267361111111114, 'precision_lift': None, 'decision_cost': 9005.0, 'decision_cost_per_row': 0.31267361111111114, 'decision_cost_per_signal': None, 'active_window_rate': 0.0, 'zero_signal_window_rate': 1.0, 'high_target_window_count': 60, 'high_target_window_capture_rate': 0.0, 'missed_high_target_window_rate': 1.0, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 20.016666666666666, 'ranked_signal_quality': -3.5312760416666666}`
- `down`: `{'rows': 28800, 'positive_count': 13135, 'negative_count': 15665, 'predicted_positive_count': 3, 'true_positive_count': 1, 'false_positive_count': 2, 'false_negative_count': 13134, 'true_negative_count': 15663, 'precision': 0.3333333333333333, 'recall': 7.613247049866768e-05, 'false_positive_rate': 0.00012767315671879988, 'false_discovery_rate': 0.6666666666666666, 'predicted_positive_rate': 0.00010416666666666667, 'base_positive_rate': 0.4560763888888889, 'precision_lift': 0.7308717167872096, 'decision_cost': 13144.0, 'decision_cost_per_row': 0.4563888888888889, 'decision_cost_per_signal': 4381.333333333333, 'active_window_rate': 0.008333333333333333, 'zero_signal_window_rate': 0.9916666666666667, 'high_target_window_count': 75, 'high_target_window_capture_rate': 0.013333333333333334, 'missed_high_target_window_rate': 0.9866666666666667, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 38.13333333333333, 'ranked_signal_quality': -2.6915833333333334}`

## Decision Contract

- Validation-only mode selects candidates from validation metrics only.
- Prequential reliability mode selects candidates from prior matured prediction-window reliability after current validation sanity checks.
- Context-rule mode selects candidates by prediction-safe candidate-specific rules loaded from a simulator artifact.
- Prediction metrics are outer evaluation and never choose a candidate.
- If no candidate passes the active selection contract, the side emits no signals for that prediction batch.
- Diagnostic artifacts include validation row scores, validation batch metrics, selected features, and sequence diagnostics.
