# RPF Ranked Signal Router Report

## Scope

- `asset`: `BTCUSDT`
- `root`: `8h/B`
- `candidate_set`: `default_v1`
- `outer_window_count`: `20`

## Side Summary

- `up`: `{'rows': 4800, 'positive_count': 2648, 'negative_count': 2152, 'predicted_positive_count': 15, 'true_positive_count': 8, 'false_positive_count': 7, 'false_negative_count': 2640, 'true_negative_count': 2145, 'precision': 0.5333333333333333, 'recall': 0.0030211480362537764, 'false_positive_rate': 0.0032527881040892194, 'false_discovery_rate': 0.4666666666666667, 'predicted_positive_rate': 0.003125, 'base_positive_rate': 0.5516666666666666, 'precision_lift': 0.9667673716012085, 'decision_cost': 2675.0, 'decision_cost_per_row': 0.5572916666666666, 'decision_cost_per_signal': 178.33333333333334, 'active_window_rate': 0.35, 'zero_signal_window_rate': 0.65, 'high_target_window_count': 15, 'high_target_window_capture_rate': 0.26666666666666666, 'missed_high_target_window_rate': 0.7333333333333333, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 19.65, 'ranked_signal_quality': -1.210703125}`
- `down`: `{'rows': 4800, 'positive_count': 970, 'negative_count': 3830, 'predicted_positive_count': 14, 'true_positive_count': 4, 'false_positive_count': 10, 'false_negative_count': 966, 'true_negative_count': 3820, 'precision': 0.2857142857142857, 'recall': 0.004123711340206186, 'false_positive_rate': 0.0026109660574412533, 'false_discovery_rate': 0.7142857142857143, 'predicted_positive_rate': 0.002916666666666667, 'base_positive_rate': 0.20208333333333334, 'precision_lift': 1.413843888070692, 'decision_cost': 1016.0, 'decision_cost_per_row': 0.21166666666666667, 'decision_cost_per_signal': 72.57142857142857, 'active_window_rate': 0.25, 'zero_signal_window_rate': 0.75, 'high_target_window_count': 7, 'high_target_window_capture_rate': 0.0, 'missed_high_target_window_rate': 1.0, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 39.8, 'ranked_signal_quality': -1.6202140095729018}`

## Decision Contract

- Candidates are selected from validation metrics only.
- Prediction metrics are outer evaluation and never choose a candidate.
- If no candidate passes validation gates, the side emits no signals for that prediction batch.
