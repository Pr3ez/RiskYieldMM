# RPF Ranked Signal Router Report

## Scope

- `asset`: `BTCUSDT`
- `root`: `8h/B`
- `candidate_set`: `pruned_reliability_v1`
- `selection_mode`: `prequential_reliability_v1`
- `outer_window_count`: `60`

## Side Summary

- `up`: `{'rows': 14400, 'positive_count': 4805, 'negative_count': 9595, 'predicted_positive_count': 0, 'true_positive_count': 0, 'false_positive_count': 0, 'false_negative_count': 4805, 'true_negative_count': 9595, 'precision': None, 'recall': 0.0, 'false_positive_rate': 0.0, 'false_discovery_rate': None, 'predicted_positive_rate': 0.0, 'base_positive_rate': 0.33368055555555554, 'precision_lift': None, 'decision_cost': 4805.0, 'decision_cost_per_row': 0.33368055555555554, 'decision_cost_per_signal': None, 'active_window_rate': 0.0, 'zero_signal_window_rate': 1.0, 'high_target_window_count': 32, 'high_target_window_capture_rate': 0.0, 'missed_high_target_window_rate': 1.0, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 20.016666666666666, 'ranked_signal_quality': -3.5312760416666666}`
- `down`: `{'rows': 14400, 'positive_count': 6526, 'negative_count': 7874, 'predicted_positive_count': 0, 'true_positive_count': 0, 'false_positive_count': 0, 'false_negative_count': 6526, 'true_negative_count': 7874, 'precision': None, 'recall': 0.0, 'false_positive_rate': 0.0, 'false_discovery_rate': None, 'predicted_positive_rate': 0.0, 'base_positive_rate': 0.45319444444444446, 'precision_lift': None, 'decision_cost': 6526.0, 'decision_cost_per_row': 0.45319444444444446, 'decision_cost_per_signal': None, 'active_window_rate': 0.0, 'zero_signal_window_rate': 1.0, 'high_target_window_count': 38, 'high_target_window_capture_rate': 0.0, 'missed_high_target_window_rate': 1.0, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 38.6, 'ranked_signal_quality': -3.5603125}`

## Decision Contract

- Validation-only mode selects candidates from validation metrics only.
- Prequential reliability mode selects candidates from prior matured prediction-window reliability after current validation sanity checks.
- Context-rule mode selects candidates by prediction-safe candidate-specific rules loaded from a simulator artifact.
- Prediction metrics are outer evaluation and never choose a candidate.
- If no candidate passes the active selection contract, the side emits no signals for that prediction batch.
- Diagnostic artifacts include validation row scores, validation batch metrics, selected features, and sequence diagnostics.
