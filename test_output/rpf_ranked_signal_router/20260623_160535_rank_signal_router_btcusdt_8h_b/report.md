# RPF Ranked Signal Router Report

## Scope

- `asset`: `BTCUSDT`
- `root`: `8h/B`
- `candidate_set`: `pruned_reliability_v1`
- `selection_mode`: `prequential_reliability_v1`
- `outer_window_count`: `2`

## Side Summary

- `up`: `{'rows': 480, 'positive_count': 207, 'negative_count': 273, 'predicted_positive_count': 0, 'true_positive_count': 0, 'false_positive_count': 0, 'false_negative_count': 207, 'true_negative_count': 273, 'precision': None, 'recall': 0.0, 'false_positive_rate': 0.0, 'false_discovery_rate': None, 'predicted_positive_rate': 0.0, 'base_positive_rate': 0.43125, 'precision_lift': None, 'decision_cost': 207.0, 'decision_cost_per_row': 0.43125, 'decision_cost_per_signal': None, 'active_window_rate': 0.0, 'zero_signal_window_rate': 1.0, 'high_target_window_count': 1, 'high_target_window_capture_rate': 0.0, 'missed_high_target_window_rate': 1.0, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 22.5, 'ranked_signal_quality': -3.53515625}`
- `down`: `{'rows': 480, 'positive_count': 238, 'negative_count': 242, 'predicted_positive_count': 0, 'true_positive_count': 0, 'false_positive_count': 0, 'false_negative_count': 238, 'true_negative_count': 242, 'precision': None, 'recall': 0.0, 'false_positive_rate': 0.0, 'false_discovery_rate': None, 'predicted_positive_rate': 0.0, 'base_positive_rate': 0.49583333333333335, 'precision_lift': None, 'decision_cost': 238.0, 'decision_cost_per_row': 0.49583333333333335, 'decision_cost_per_signal': None, 'active_window_rate': 0.0, 'zero_signal_window_rate': 1.0, 'high_target_window_count': 1, 'high_target_window_capture_rate': 0.0, 'missed_high_target_window_rate': 1.0, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 40.0, 'ranked_signal_quality': -3.5625}`

## Decision Contract

- Validation-only mode selects candidates from validation metrics only.
- Prequential reliability mode selects candidates from prior matured prediction-window reliability after current validation sanity checks.
- Prediction metrics are outer evaluation and never choose a candidate.
- If no candidate passes validation gates, the side emits no signals for that prediction batch.
- Diagnostic artifacts include validation row scores, validation batch metrics, selected features, and sequence diagnostics.
