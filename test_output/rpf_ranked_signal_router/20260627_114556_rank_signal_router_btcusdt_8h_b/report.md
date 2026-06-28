# RPF Ranked Signal Router Report

## Scope

- `asset`: `BTCUSDT`
- `root`: `8h/B`
- `candidate_set`: `pruned_reliability_v1`
- `selection_mode`: `prequential_reliability_v1`
- `outer_window_count`: `60`

## Side Summary

- `up`: `{'rows': 14400, 'positive_count': 6539, 'negative_count': 7861, 'predicted_positive_count': 6, 'true_positive_count': 2, 'false_positive_count': 4, 'false_negative_count': 6537, 'true_negative_count': 7857, 'precision': 0.3333333333333333, 'recall': 0.0003058571647040832, 'false_positive_rate': 0.0005088411143620405, 'false_discovery_rate': 0.6666666666666666, 'predicted_positive_rate': 0.0004166666666666667, 'base_positive_rate': 0.4540972222222222, 'precision_lift': 0.7340571952897996, 'decision_cost': 6557.0, 'decision_cost_per_row': 0.45534722222222224, 'decision_cost_per_signal': 1092.8333333333333, 'active_window_rate': 0.05, 'zero_signal_window_rate': 0.95, 'high_target_window_count': 36, 'high_target_window_capture_rate': 0.027777777777777776, 'missed_high_target_window_rate': 0.9722222222222222, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 21.05, 'ranked_signal_quality': -2.575112847222222}`
- `down`: `{'rows': 14400, 'positive_count': 4916, 'negative_count': 9484, 'predicted_positive_count': 0, 'true_positive_count': 0, 'false_positive_count': 0, 'false_negative_count': 4916, 'true_negative_count': 9484, 'precision': None, 'recall': 0.0, 'false_positive_rate': 0.0, 'false_discovery_rate': None, 'predicted_positive_rate': 0.0, 'base_positive_rate': 0.3413888888888889, 'precision_lift': None, 'decision_cost': 4916.0, 'decision_cost_per_row': 0.3413888888888889, 'decision_cost_per_signal': None, 'active_window_rate': 0.0, 'zero_signal_window_rate': 1.0, 'high_target_window_count': 29, 'high_target_window_capture_rate': 0.0, 'missed_high_target_window_rate': 1.0, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 39.733333333333334, 'ranked_signal_quality': -3.5620833333333333}`

## Decision Contract

- Validation-only mode selects candidates from validation metrics only.
- Prequential reliability mode selects candidates from prior matured prediction-window reliability after current validation sanity checks.
- Context-rule mode selects candidates by prediction-safe candidate-specific rules loaded from a simulator artifact.
- Prediction metrics are outer evaluation and never choose a candidate.
- If no candidate passes the active selection contract, the side emits no signals for that prediction batch.
- Diagnostic artifacts include validation row scores, validation batch metrics, selected features, and sequence diagnostics.
