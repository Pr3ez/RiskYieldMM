# RPF Ranked Signal Router Report

## Scope

- `asset`: `BTCUSDT`
- `root`: `8h/B`
- `candidate_set`: `pruned_reliability_v1`
- `selection_mode`: `prequential_reliability_v1`
- `outer_window_count`: `960`

## Side Summary

- `up`: `{'status': 'empty'}`
- `down`: `{'rows': 230400, 'positive_count': 89736, 'negative_count': 140664, 'predicted_positive_count': 24, 'true_positive_count': 6, 'false_positive_count': 18, 'false_negative_count': 89730, 'true_negative_count': 140646, 'precision': 0.25, 'recall': 6.686279753944904e-05, 'false_positive_rate': 0.0001279645111755673, 'false_discovery_rate': 0.75, 'predicted_positive_rate': 0.00010416666666666667, 'base_positive_rate': 0.38947916666666665, 'precision_lift': 0.6418828563787109, 'decision_cost': 89820.0, 'decision_cost_per_row': 0.38984375, 'decision_cost_per_signal': 3742.5, 'active_window_rate': 0.008333333333333333, 'zero_signal_window_rate': 0.9916666666666667, 'high_target_window_count': 521, 'high_target_window_capture_rate': 0.003838771593090211, 'missed_high_target_window_rate': 0.9961612284069098, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 38.98125, 'ranked_signal_quality': -2.916432835242722}`

## Decision Contract

- Validation-only mode selects candidates from validation metrics only.
- Prequential reliability mode selects candidates from prior matured prediction-window reliability after current validation sanity checks.
- Context-rule mode selects candidates by prediction-safe candidate-specific rules loaded from a simulator artifact.
- Prediction metrics are outer evaluation and never choose a candidate.
- If no candidate passes the active selection contract, the side emits no signals for that prediction batch.
- Diagnostic artifacts include validation row scores, validation batch metrics, selected features, and sequence diagnostics.
