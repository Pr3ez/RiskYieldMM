# RPF Ranked Signal Router Report

## Scope

- `asset`: `BTCUSDT`
- `root`: `8h/B`
- `candidate_set`: `pruned_reliability_v1`
- `selection_mode`: `prequential_reliability_v1`
- `outer_window_count`: `60`

## Side Summary

- `up`: `{'rows': 14400, 'positive_count': 6580, 'negative_count': 7820, 'predicted_positive_count': 0, 'true_positive_count': 0, 'false_positive_count': 0, 'false_negative_count': 6580, 'true_negative_count': 7820, 'precision': None, 'recall': 0.0, 'false_positive_rate': 0.0, 'false_discovery_rate': None, 'predicted_positive_rate': 0.0, 'base_positive_rate': 0.45694444444444443, 'precision_lift': None, 'decision_cost': 6580.0, 'decision_cost_per_row': 0.45694444444444443, 'decision_cost_per_signal': None, 'active_window_rate': 0.0, 'zero_signal_window_rate': 1.0, 'high_target_window_count': 38, 'high_target_window_capture_rate': 0.0, 'missed_high_target_window_rate': 1.0, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 20.45, 'ranked_signal_quality': -3.531953125}`
- `down`: `{'rows': 14400, 'positive_count': 4901, 'negative_count': 9499, 'predicted_positive_count': 14, 'true_positive_count': 9, 'false_positive_count': 5, 'false_negative_count': 4892, 'true_negative_count': 9494, 'precision': 0.6428571428571429, 'recall': 0.001836359926545603, 'false_positive_rate': 0.0005263711969681019, 'false_discovery_rate': 0.35714285714285715, 'predicted_positive_rate': 0.0009722222222222222, 'base_positive_rate': 0.34034722222222225, 'precision_lift': 1.8888273530183344, 'decision_cost': 4917.0, 'decision_cost_per_row': 0.3414583333333333, 'decision_cost_per_signal': 351.2142857142857, 'active_window_rate': 0.08333333333333333, 'zero_signal_window_rate': 0.9166666666666666, 'high_target_window_count': 30, 'high_target_window_capture_rate': 0.06666666666666667, 'missed_high_target_window_rate': 0.9333333333333333, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 38.65, 'ranked_signal_quality': 0.06440693817952595}`

## Decision Contract

- Validation-only mode selects candidates from validation metrics only.
- Prequential reliability mode selects candidates from prior matured prediction-window reliability after current validation sanity checks.
- Context-rule mode selects candidates by prediction-safe candidate-specific rules loaded from a simulator artifact.
- Prediction metrics are outer evaluation and never choose a candidate.
- If no candidate passes the active selection contract, the side emits no signals for that prediction batch.
- Diagnostic artifacts include validation row scores, validation batch metrics, selected features, and sequence diagnostics.
