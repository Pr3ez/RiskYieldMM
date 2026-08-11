# RPF Ranked Signal Router Report

## Scope

- `asset`: `BTCUSDT`
- `root`: `8h/B`
- `candidate_set`: `pruned_reliability_v1`
- `selection_mode`: `context_rule_v1`
- `outer_window_count`: `120`

## Side Summary

- `up`: `{'rows': 28800, 'positive_count': 10432, 'negative_count': 18368, 'predicted_positive_count': 34, 'true_positive_count': 13, 'false_positive_count': 21, 'false_negative_count': 10419, 'true_negative_count': 18347, 'precision': 0.38235294117647056, 'recall': 0.001246165644171779, 'false_positive_rate': 0.0011432926829268292, 'false_discovery_rate': 0.6176470588235294, 'predicted_positive_rate': 0.0011805555555555556, 'base_positive_rate': 0.3622222222222222, 'precision_lift': 1.0555756044749187, 'decision_cost': 10524.0, 'decision_cost_per_row': 0.36541666666666667, 'decision_cost_per_signal': 309.52941176470586, 'active_window_rate': 0.11666666666666667, 'zero_signal_window_rate': 0.8833333333333333, 'high_target_window_count': 61, 'high_target_window_capture_rate': 0.09836065573770492, 'missed_high_target_window_rate': 0.9016393442622951, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 21.0, 'ranked_signal_quality': -2.1217352222619916}`
- `down`: `{'rows': 28800, 'positive_count': 12017, 'negative_count': 16783, 'predicted_positive_count': 0, 'true_positive_count': 0, 'false_positive_count': 0, 'false_negative_count': 12017, 'true_negative_count': 16783, 'precision': None, 'recall': 0.0, 'false_positive_rate': 0.0, 'false_discovery_rate': None, 'predicted_positive_rate': 0.0, 'base_positive_rate': 0.41725694444444444, 'precision_lift': None, 'decision_cost': 12017.0, 'decision_cost_per_row': 0.41725694444444444, 'decision_cost_per_signal': None, 'active_window_rate': 0.0, 'zero_signal_window_rate': 1.0, 'high_target_window_count': 70, 'high_target_window_capture_rate': 0.0, 'missed_high_target_window_rate': 1.0, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 39.125, 'ranked_signal_quality': -3.5611328125}`

## Decision Contract

- Validation-only mode selects candidates from validation metrics only.
- Prequential reliability mode selects candidates from prior matured prediction-window reliability after current validation sanity checks.
- Context-rule mode selects candidates by prediction-safe candidate-specific rules loaded from a simulator artifact.
- Prediction metrics are outer evaluation and never choose a candidate.
- If no candidate passes the active selection contract, the side emits no signals for that prediction batch.
- Diagnostic artifacts include validation row scores, validation batch metrics, selected features, and sequence diagnostics.
