# RPF Ranked Signal Router Report

## Scope

- `asset`: `BTCUSDT`
- `root`: `8h/B`
- `candidate_set`: `pruned_reliability_v1`
- `selection_mode`: `prequential_reliability_v1`
- `outer_window_count`: `960`

## Side Summary

- `up`: `{'rows': 230400, 'positive_count': 92247, 'negative_count': 138153, 'predicted_positive_count': 14, 'true_positive_count': 5, 'false_positive_count': 9, 'false_negative_count': 92242, 'true_negative_count': 138144, 'precision': 0.35714285714285715, 'recall': 5.420230468199508e-05, 'false_positive_rate': 6.514516514299364e-05, 'false_discovery_rate': 0.6428571428571429, 'predicted_positive_rate': 6.076388888888889e-05, 'base_positive_rate': 0.4003776041666667, 'precision_lift': 0.8920150713379762, 'decision_cost': 92287.0, 'decision_cost_per_row': 0.40055121527777776, 'decision_cost_per_signal': 6591.928571428572, 'active_window_rate': 0.007291666666666667, 'zero_signal_window_rate': 0.9927083333333333, 'high_target_window_count': 540, 'high_target_window_capture_rate': 0.003703703703703704, 'missed_high_target_window_rate': 0.9962962962962963, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 20.0, 'ranked_signal_quality': -2.620800264550265}`
- `down`: `{'status': 'empty'}`

## Decision Contract

- Validation-only mode selects candidates from validation metrics only.
- Prequential reliability mode selects candidates from prior matured prediction-window reliability after current validation sanity checks.
- Context-rule mode selects candidates by prediction-safe candidate-specific rules loaded from a simulator artifact.
- Prediction metrics are outer evaluation and never choose a candidate.
- If no candidate passes the active selection contract, the side emits no signals for that prediction batch.
- Diagnostic artifacts include validation row scores, validation batch metrics, selected features, and sequence diagnostics.
