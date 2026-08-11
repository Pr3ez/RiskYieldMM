# RPF Ranked Signal Router Report

## Scope

- `asset`: `BTCUSDT`
- `root`: `8h/B`
- `candidate_set`: `pruned_reliability_v1`
- `selection_mode`: `prequential_reliability_v1`
- `outer_window_count`: `960`

## Side Summary

- `up`: `{'rows': 230400, 'positive_count': 86454, 'negative_count': 143946, 'predicted_positive_count': 7, 'true_positive_count': 2, 'false_positive_count': 5, 'false_negative_count': 86452, 'true_negative_count': 143941, 'precision': 0.2857142857142857, 'recall': 2.313368959215305e-05, 'false_positive_rate': 3.4735247940199796e-05, 'false_discovery_rate': 0.7142857142857143, 'predicted_positive_rate': 3.0381944444444444e-05, 'base_positive_rate': 0.375234375, 'precision_lift': 0.7614288688617232, 'decision_cost': 86477.0, 'decision_cost_per_row': 0.3753342013888889, 'decision_cost_per_signal': 12353.857142857143, 'active_window_rate': 0.004166666666666667, 'zero_signal_window_rate': 0.9958333333333333, 'high_target_window_count': 514, 'high_target_window_capture_rate': 0.0, 'missed_high_target_window_rate': 1.0, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 20.0, 'ranked_signal_quality': -2.8102976190476188}`
- `down`: `{'status': 'empty'}`

## Decision Contract

- Validation-only mode selects candidates from validation metrics only.
- Prequential reliability mode selects candidates from prior matured prediction-window reliability after current validation sanity checks.
- Context-rule mode selects candidates by prediction-safe candidate-specific rules loaded from a simulator artifact.
- Prediction metrics are outer evaluation and never choose a candidate.
- If no candidate passes the active selection contract, the side emits no signals for that prediction batch.
- Diagnostic artifacts include validation row scores, validation batch metrics, selected features, and sequence diagnostics.
