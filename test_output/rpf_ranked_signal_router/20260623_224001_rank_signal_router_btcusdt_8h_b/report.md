# RPF Ranked Signal Router Report

## Scope

- `asset`: `BTCUSDT`
- `root`: `8h/B`
- `candidate_set`: `pruned_reliability_v1`
- `selection_mode`: `context_rule_v1`
- `outer_window_count`: `120`

## Side Summary

- `up`: `{'rows': 28800, 'positive_count': 9005, 'negative_count': 19795, 'predicted_positive_count': 24, 'true_positive_count': 9, 'false_positive_count': 15, 'false_negative_count': 8996, 'true_negative_count': 19780, 'precision': 0.375, 'recall': 0.000999444752915047, 'false_positive_rate': 0.0007577671129072998, 'false_discovery_rate': 0.625, 'predicted_positive_rate': 0.0008333333333333334, 'base_positive_rate': 0.31267361111111114, 'precision_lift': 1.1993337034980565, 'decision_cost': 9071.0, 'decision_cost_per_row': 0.3149652777777778, 'decision_cost_per_signal': 377.9583333333333, 'active_window_rate': 0.09166666666666666, 'zero_signal_window_rate': 0.9083333333333333, 'high_target_window_count': 60, 'high_target_window_capture_rate': 0.08333333333333333, 'missed_high_target_window_rate': 0.9166666666666666, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 20.25, 'ranked_signal_quality': -1.9154732180038871}`
- `down`: `{'rows': 28800, 'positive_count': 13135, 'negative_count': 15665, 'predicted_positive_count': 0, 'true_positive_count': 0, 'false_positive_count': 0, 'false_negative_count': 13135, 'true_negative_count': 15665, 'precision': None, 'recall': 0.0, 'false_positive_rate': 0.0, 'false_discovery_rate': None, 'predicted_positive_rate': 0.0, 'base_positive_rate': 0.4560763888888889, 'precision_lift': None, 'decision_cost': 13135.0, 'decision_cost_per_row': 0.4560763888888889, 'decision_cost_per_signal': None, 'active_window_rate': 0.0, 'zero_signal_window_rate': 1.0, 'high_target_window_count': 75, 'high_target_window_capture_rate': 0.0, 'missed_high_target_window_rate': 1.0, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 38.13333333333333, 'ranked_signal_quality': -3.5595833333333333}`

## Decision Contract

- Validation-only mode selects candidates from validation metrics only.
- Prequential reliability mode selects candidates from prior matured prediction-window reliability after current validation sanity checks.
- Context-rule mode selects candidates by prediction-safe candidate-specific rules loaded from a simulator artifact.
- Prediction metrics are outer evaluation and never choose a candidate.
- If no candidate passes the active selection contract, the side emits no signals for that prediction batch.
- Diagnostic artifacts include validation row scores, validation batch metrics, selected features, and sequence diagnostics.
