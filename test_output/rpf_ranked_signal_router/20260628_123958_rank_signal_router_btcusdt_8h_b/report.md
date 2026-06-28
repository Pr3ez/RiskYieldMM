# RPF Ranked Signal Router Report

## Scope

- `asset`: `BTCUSDT`
- `root`: `8h/B`
- `candidate_set`: `pruned_reliability_v1`
- `selection_mode`: `prequential_reliability_v1`
- `outer_window_count`: `960`

## Side Summary

- `up`: `{'status': 'empty'}`
- `down`: `{'rows': 230400, 'positive_count': 86967, 'negative_count': 143433, 'predicted_positive_count': 5, 'true_positive_count': 0, 'false_positive_count': 5, 'false_negative_count': 86967, 'true_negative_count': 143428, 'precision': 0.0, 'recall': 0.0, 'false_positive_rate': 3.485948143035424e-05, 'false_discovery_rate': 1.0, 'predicted_positive_rate': 2.170138888888889e-05, 'base_positive_rate': 0.3774609375, 'precision_lift': 0.0, 'decision_cost': 86992.0, 'decision_cost_per_row': 0.37756944444444446, 'decision_cost_per_signal': 17398.4, 'active_window_rate': 0.0020833333333333333, 'zero_signal_window_rate': 0.9979166666666667, 'high_target_window_count': 515, 'high_target_window_capture_rate': 0.0, 'missed_high_target_window_rate': 1.0, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 39.11770833333333, 'ranked_signal_quality': -3.5577880859374997}`

## Decision Contract

- Validation-only mode selects candidates from validation metrics only.
- Prequential reliability mode selects candidates from prior matured prediction-window reliability after current validation sanity checks.
- Context-rule mode selects candidates by prediction-safe candidate-specific rules loaded from a simulator artifact.
- Prediction metrics are outer evaluation and never choose a candidate.
- If no candidate passes the active selection contract, the side emits no signals for that prediction batch.
- Diagnostic artifacts include validation row scores, validation batch metrics, selected features, and sequence diagnostics.
