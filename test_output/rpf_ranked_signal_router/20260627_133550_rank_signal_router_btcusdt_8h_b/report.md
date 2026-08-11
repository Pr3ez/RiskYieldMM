# RPF Ranked Signal Router Report

## Scope

- `asset`: `BTCUSDT`
- `root`: `8h/B`
- `candidate_set`: `pruned_reliability_v1`
- `selection_mode`: `prequential_reliability_v1`
- `outer_window_count`: `480`

## Side Summary

- `up`: `{'rows': 115200, 'positive_count': 43997, 'negative_count': 71203, 'predicted_positive_count': 3, 'true_positive_count': 3, 'false_positive_count': 0, 'false_negative_count': 43994, 'true_negative_count': 71203, 'precision': 1.0, 'recall': 6.81864672591313e-05, 'false_positive_rate': 0.0, 'false_discovery_rate': 0.0, 'predicted_positive_rate': 2.604166666666667e-05, 'base_positive_rate': 0.3819184027777778, 'precision_lift': 2.618360342750642, 'decision_cost': 43994.0, 'decision_cost_per_row': 0.38189236111111113, 'decision_cost_per_signal': 14664.666666666666, 'active_window_rate': 0.0020833333333333333, 'zero_signal_window_rate': 0.9979166666666667, 'high_target_window_count': 264, 'high_target_window_capture_rate': 0.003787878787878788, 'missed_high_target_window_rate': 0.9962121212121212, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 20.116666666666667, 'ranked_signal_quality': 2.2146823332285566}`
- `down`: `{'rows': 115200, 'positive_count': 46204, 'negative_count': 68996, 'predicted_positive_count': 62, 'true_positive_count': 25, 'false_positive_count': 37, 'false_negative_count': 46179, 'true_negative_count': 68959, 'precision': 0.4032258064516129, 'recall': 0.000541078694485326, 'false_positive_rate': 0.0005362629717664793, 'false_discovery_rate': 0.5967741935483871, 'predicted_positive_rate': 0.0005381944444444444, 'base_positive_rate': 0.4010763888888889, 'precision_lift': 1.0053591226566054, 'decision_cost': 46364.0, 'decision_cost_per_row': 0.4024652777777778, 'decision_cost_per_signal': 747.8064516129032, 'active_window_rate': 0.04375, 'zero_signal_window_rate': 0.95625, 'high_target_window_count': 268, 'high_target_window_capture_rate': 0.026119402985074626, 'missed_high_target_window_rate': 0.9738805970149254, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 38.93958333333333, 'ranked_signal_quality': -2.430269292739971}`

## Decision Contract

- Validation-only mode selects candidates from validation metrics only.
- Prequential reliability mode selects candidates from prior matured prediction-window reliability after current validation sanity checks.
- Context-rule mode selects candidates by prediction-safe candidate-specific rules loaded from a simulator artifact.
- Prediction metrics are outer evaluation and never choose a candidate.
- If no candidate passes the active selection contract, the side emits no signals for that prediction batch.
- Diagnostic artifacts include validation row scores, validation batch metrics, selected features, and sequence diagnostics.
