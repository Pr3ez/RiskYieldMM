# RPF Ranked Signal Router Report

## Scope

- `asset`: `BTCUSDT`
- `root`: `8h/B`
- `candidate_set`: `pruned_reliability_v1`
- `selection_mode`: `context_rule_v1`
- `outer_window_count`: `120`

## Side Summary

- `up`: `{'rows': 28800, 'positive_count': 12381, 'negative_count': 16419, 'predicted_positive_count': 17, 'true_positive_count': 14, 'false_positive_count': 3, 'false_negative_count': 12367, 'true_negative_count': 16416, 'precision': 0.8235294117647058, 'recall': 0.001130764881673532, 'false_positive_rate': 0.0001827151470856934, 'false_discovery_rate': 0.17647058823529413, 'predicted_positive_rate': 0.0005902777777777778, 'base_positive_rate': 0.4298958333333333, 'precision_lift': 1.9156487407175131, 'decision_cost': 12382.0, 'decision_cost_per_row': 0.42993055555555554, 'decision_cost_per_signal': 728.3529411764706, 'active_window_rate': 0.08333333333333333, 'zero_signal_window_rate': 0.9166666666666666, 'high_target_window_count': 73, 'high_target_window_capture_rate': 0.1095890410958904, 'missed_high_target_window_rate': 0.8904109589041096, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 20.225, 'ranked_signal_quality': 0.6671952474335489}`
- `down`: `{'rows': 28800, 'positive_count': 9600, 'negative_count': 19200, 'predicted_positive_count': 9, 'true_positive_count': 6, 'false_positive_count': 3, 'false_negative_count': 9594, 'true_negative_count': 19197, 'precision': 0.6666666666666666, 'recall': 0.000625, 'false_positive_rate': 0.00015625, 'false_discovery_rate': 0.3333333333333333, 'predicted_positive_rate': 0.0003125, 'base_positive_rate': 0.3333333333333333, 'precision_lift': 2.0, 'decision_cost': 9609.0, 'decision_cost_per_row': 0.3336458333333333, 'decision_cost_per_signal': 1067.6666666666667, 'active_window_rate': 0.025, 'zero_signal_window_rate': 0.975, 'high_target_window_count': 60, 'high_target_window_capture_rate': 0.03333333333333333, 'missed_high_target_window_rate': 0.9666666666666667, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 39.041666666666664, 'ranked_signal_quality': 0.19899739583333323}`

## Decision Contract

- Validation-only mode selects candidates from validation metrics only.
- Prequential reliability mode selects candidates from prior matured prediction-window reliability after current validation sanity checks.
- Context-rule mode selects candidates by prediction-safe candidate-specific rules loaded from a simulator artifact.
- Prediction metrics are outer evaluation and never choose a candidate.
- If no candidate passes the active selection contract, the side emits no signals for that prediction batch.
- Diagnostic artifacts include validation row scores, validation batch metrics, selected features, and sequence diagnostics.
