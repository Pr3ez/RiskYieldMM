# RPF Ranked Signal Router Report

## Scope

- `asset`: `BTCUSDT`
- `root`: `8h/B`
- `candidate_set`: `pruned_reliability_v1`
- `selection_mode`: `prequential_reliability_v1`
- `outer_window_count`: `960`

## Side Summary

- `up`: `{'rows': 230400, 'positive_count': 88698, 'negative_count': 141702, 'predicted_positive_count': 21, 'true_positive_count': 6, 'false_positive_count': 15, 'false_negative_count': 88692, 'true_negative_count': 141687, 'precision': 0.2857142857142857, 'recall': 6.764526821348847e-05, 'false_positive_rate': 0.00010585595122157768, 'false_discovery_rate': 0.7142857142857143, 'predicted_positive_rate': 9.114583333333334e-05, 'base_positive_rate': 0.3849739583333333, 'precision_lift': 0.7421652283994163, 'decision_cost': 88767.0, 'decision_cost_per_row': 0.3852734375, 'decision_cost_per_signal': 4227.0, 'active_window_rate': 0.007291666666666667, 'zero_signal_window_rate': 0.9927083333333333, 'high_target_window_count': 518, 'high_target_window_capture_rate': 0.003861003861003861, 'missed_high_target_window_rate': 0.9961389961389961, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 23.428125, 'ranked_signal_quality': -2.804476458182513}`
- `down`: `{'rows': 230400, 'positive_count': 87413, 'negative_count': 142987, 'predicted_positive_count': 12, 'true_positive_count': 0, 'false_positive_count': 12, 'false_negative_count': 87413, 'true_negative_count': 142975, 'precision': 0.0, 'recall': 0.0, 'false_positive_rate': 8.392371334456979e-05, 'false_discovery_rate': 1.0, 'predicted_positive_rate': 5.208333333333334e-05, 'base_positive_rate': 0.37939670138888887, 'precision_lift': 0.0, 'decision_cost': 87473.0, 'decision_cost_per_row': 0.3796571180555556, 'decision_cost_per_signal': 7289.416666666667, 'active_window_rate': 0.004166666666666667, 'zero_signal_window_rate': 0.9958333333333333, 'high_target_window_count': 506, 'high_target_window_capture_rate': 0.0, 'missed_high_target_window_rate': 1.0, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 39.155208333333334, 'ranked_signal_quality': -3.5545133463541667}`

## Decision Contract

- Validation-only mode selects candidates from validation metrics only.
- Prequential reliability mode selects candidates from prior matured prediction-window reliability after current validation sanity checks.
- Context-rule mode selects candidates by prediction-safe candidate-specific rules loaded from a simulator artifact.
- Prediction metrics are outer evaluation and never choose a candidate.
- If no candidate passes the active selection contract, the side emits no signals for that prediction batch.
- Diagnostic artifacts include validation row scores, validation batch metrics, selected features, and sequence diagnostics.
