# RPF Ranked Signal Router Report

## Scope

- `asset`: `BTCUSDT`
- `root`: `8h/B`
- `candidate_set`: `pruned_reliability_v1`
- `selection_mode`: `prequential_reliability_v1`
- `outer_window_count`: `60`

## Side Summary

- `up`: `{'rows': 14400, 'positive_count': 4682, 'negative_count': 9718, 'predicted_positive_count': 0, 'true_positive_count': 0, 'false_positive_count': 0, 'false_negative_count': 4682, 'true_negative_count': 9718, 'precision': None, 'recall': 0.0, 'false_positive_rate': 0.0, 'false_discovery_rate': None, 'predicted_positive_rate': 0.0, 'base_positive_rate': 0.32513888888888887, 'precision_lift': None, 'decision_cost': 4682.0, 'decision_cost_per_row': 0.32513888888888887, 'decision_cost_per_signal': None, 'active_window_rate': 0.0, 'zero_signal_window_rate': 1.0, 'high_target_window_count': 29, 'high_target_window_capture_rate': 0.0, 'missed_high_target_window_rate': 1.0, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 19.883333333333333, 'ranked_signal_quality': -3.5310677083333335}`
- `down`: `{'rows': 14400, 'positive_count': 6569, 'negative_count': 7831, 'predicted_positive_count': 3, 'true_positive_count': 0, 'false_positive_count': 3, 'false_negative_count': 6569, 'true_negative_count': 7828, 'precision': 0.0, 'recall': 0.0, 'false_positive_rate': 0.0003830928361639637, 'false_discovery_rate': 1.0, 'predicted_positive_rate': 0.00020833333333333335, 'base_positive_rate': 0.45618055555555553, 'precision_lift': 0.0, 'decision_cost': 6584.0, 'decision_cost_per_row': 0.4572222222222222, 'decision_cost_per_signal': 2194.6666666666665, 'active_window_rate': 0.016666666666666666, 'zero_signal_window_rate': 0.9833333333333333, 'high_target_window_count': 38, 'high_target_window_capture_rate': 0.0, 'missed_high_target_window_rate': 1.0, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 39.7, 'ranked_signal_quality': -3.535364583333333}`

## Decision Contract

- Validation-only mode selects candidates from validation metrics only.
- Prequential reliability mode selects candidates from prior matured prediction-window reliability after current validation sanity checks.
- Context-rule mode selects candidates by prediction-safe candidate-specific rules loaded from a simulator artifact.
- Prediction metrics are outer evaluation and never choose a candidate.
- If no candidate passes the active selection contract, the side emits no signals for that prediction batch.
- Diagnostic artifacts include validation row scores, validation batch metrics, selected features, and sequence diagnostics.
