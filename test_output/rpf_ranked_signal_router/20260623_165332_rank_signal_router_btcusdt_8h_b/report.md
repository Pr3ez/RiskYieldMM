# RPF Ranked Signal Router Report

## Scope

- `asset`: `BTCUSDT`
- `root`: `8h/B`
- `candidate_set`: `pruned_reliability_v1`
- `selection_mode`: `prequential_reliability_v1`
- `outer_window_count`: `120`

## Side Summary

- `up`: `{'rows': 28800, 'positive_count': 10432, 'negative_count': 18368, 'predicted_positive_count': 2, 'true_positive_count': 0, 'false_positive_count': 2, 'false_negative_count': 10432, 'true_negative_count': 18366, 'precision': 0.0, 'recall': 0.0, 'false_positive_rate': 0.00010888501742160279, 'false_discovery_rate': 1.0, 'predicted_positive_rate': 6.944444444444444e-05, 'base_positive_rate': 0.3622222222222222, 'precision_lift': 0.0, 'decision_cost': 10442.0, 'decision_cost_per_row': 0.36256944444444444, 'decision_cost_per_signal': 5221.0, 'active_window_rate': 0.008333333333333333, 'zero_signal_window_rate': 0.9916666666666667, 'high_target_window_count': 61, 'high_target_window_capture_rate': 0.0, 'missed_high_target_window_rate': 1.0, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 21.125, 'ranked_signal_quality': -3.519674479166667}`
- `down`: `{'rows': 28800, 'positive_count': 12017, 'negative_count': 16783, 'predicted_positive_count': 3, 'true_positive_count': 0, 'false_positive_count': 3, 'false_negative_count': 12017, 'true_negative_count': 16780, 'precision': 0.0, 'recall': 0.0, 'false_positive_rate': 0.00017875230888398974, 'false_discovery_rate': 1.0, 'predicted_positive_rate': 0.00010416666666666667, 'base_positive_rate': 0.41725694444444444, 'precision_lift': 0.0, 'decision_cost': 12032.0, 'decision_cost_per_row': 0.4177777777777778, 'decision_cost_per_signal': 4010.6666666666665, 'active_window_rate': 0.008333333333333333, 'zero_signal_window_rate': 0.9916666666666667, 'high_target_window_count': 70, 'high_target_window_capture_rate': 0.0, 'missed_high_target_window_rate': 1.0, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 39.125, 'ranked_signal_quality': -3.5477994791666667}`

## Decision Contract

- Validation-only mode selects candidates from validation metrics only.
- Prequential reliability mode selects candidates from prior matured prediction-window reliability after current validation sanity checks.
- Prediction metrics are outer evaluation and never choose a candidate.
- If no candidate passes validation gates, the side emits no signals for that prediction batch.
- Diagnostic artifacts include validation row scores, validation batch metrics, selected features, and sequence diagnostics.
