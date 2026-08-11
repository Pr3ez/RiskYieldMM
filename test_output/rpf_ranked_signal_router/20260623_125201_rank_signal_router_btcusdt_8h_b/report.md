# RPF Ranked Signal Router Report

## Scope

- `asset`: `BTCUSDT`
- `root`: `8h/B`
- `candidate_set`: `pruned_reliability_v1`
- `selection_mode`: `prequential_reliability_v1`
- `outer_window_count`: `40`

## Side Summary

- `up`: `{'rows': 9600, 'positive_count': 4523, 'negative_count': 5077, 'predicted_positive_count': 0, 'true_positive_count': 0, 'false_positive_count': 0, 'false_negative_count': 4523, 'true_negative_count': 5077, 'precision': None, 'recall': 0.0, 'false_positive_rate': 0.0, 'false_discovery_rate': None, 'predicted_positive_rate': 0.0, 'base_positive_rate': 0.4711458333333333, 'precision_lift': None, 'decision_cost': 4523.0, 'decision_cost_per_row': 0.4711458333333333, 'decision_cost_per_signal': None, 'active_window_rate': 0.0, 'zero_signal_window_rate': 1.0, 'high_target_window_count': 25, 'high_target_window_capture_rate': 0.0, 'missed_high_target_window_rate': 1.0, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 20.8, 'ranked_signal_quality': -3.5325}`
- `down`: `{'rows': 9600, 'positive_count': 3079, 'negative_count': 6521, 'predicted_positive_count': 14, 'true_positive_count': 9, 'false_positive_count': 5, 'false_negative_count': 3070, 'true_negative_count': 6516, 'precision': 0.6428571428571429, 'recall': 0.002923026956804157, 'false_positive_rate': 0.0007667535654040791, 'false_discovery_rate': 0.35714285714285715, 'predicted_positive_rate': 0.0014583333333333334, 'base_positive_rate': 0.3207291666666667, 'precision_lift': 2.004361341808565, 'decision_cost': 3095.0, 'decision_cost_per_row': 0.3223958333333333, 'decision_cost_per_signal': 221.07142857142858, 'active_window_rate': 0.125, 'zero_signal_window_rate': 0.875, 'high_target_window_count': 20, 'high_target_window_capture_rate': 0.1, 'missed_high_target_window_rate': 0.9, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 39.175, 'ranked_signal_quality': 0.4146546032599871}`

## Decision Contract

- Validation-only mode selects candidates from validation metrics only.
- Prequential reliability mode selects candidates from prior matured prediction-window reliability after current validation sanity checks.
- Prediction metrics are outer evaluation and never choose a candidate.
- If no candidate passes validation gates, the side emits no signals for that prediction batch.
- Diagnostic artifacts include validation row scores, validation batch metrics, selected features, and sequence diagnostics.
