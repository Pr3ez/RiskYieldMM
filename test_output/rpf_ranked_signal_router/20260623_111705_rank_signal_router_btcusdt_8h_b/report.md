# RPF Ranked Signal Router Report

## Scope

- `asset`: `BTCUSDT`
- `root`: `8h/B`
- `candidate_set`: `default_v1`
- `outer_window_count`: `120`

## Side Summary

- `up`: `{'rows': 28800, 'positive_count': 12381, 'negative_count': 16419, 'predicted_positive_count': 98, 'true_positive_count': 43, 'false_positive_count': 55, 'false_negative_count': 12338, 'true_negative_count': 16364, 'precision': 0.4387755102040816, 'recall': 0.003473063565140134, 'false_positive_rate': 0.0033497776965710456, 'false_discovery_rate': 0.5612244897959183, 'predicted_positive_rate': 0.0034027777777777776, 'base_positive_rate': 0.4298958333333333, 'precision_lift': 1.0206554150615905, 'decision_cost': 12613.0, 'decision_cost_per_row': 0.4379513888888889, 'decision_cost_per_signal': 128.70408163265307, 'active_window_rate': 0.35833333333333334, 'zero_signal_window_rate': 0.6416666666666666, 'high_target_window_count': 73, 'high_target_window_capture_rate': 0.2602739726027397, 'missed_high_target_window_rate': 0.7397260273972602, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 20.508333333333333, 'ranked_signal_quality': -1.4040229757022311}`
- `down`: `{'rows': 28800, 'positive_count': 9600, 'negative_count': 19200, 'predicted_positive_count': 116, 'true_positive_count': 58, 'false_positive_count': 58, 'false_negative_count': 9542, 'true_negative_count': 19142, 'precision': 0.5, 'recall': 0.0060416666666666665, 'false_positive_rate': 0.0030208333333333333, 'false_discovery_rate': 0.5, 'predicted_positive_rate': 0.004027777777777778, 'base_positive_rate': 0.3333333333333333, 'precision_lift': 1.5, 'decision_cost': 9832.0, 'decision_cost_per_row': 0.3413888888888889, 'decision_cost_per_signal': 84.75862068965517, 'active_window_rate': 0.3333333333333333, 'zero_signal_window_rate': 0.6666666666666667, 'high_target_window_count': 60, 'high_target_window_capture_rate': 0.2833333333333333, 'missed_high_target_window_rate': 0.7166666666666667, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 39.041666666666664, 'ranked_signal_quality': -0.32433593750000017}`

## Decision Contract

- Candidates are selected from validation metrics only.
- Prediction metrics are outer evaluation and never choose a candidate.
- If no candidate passes validation gates, the side emits no signals for that prediction batch.
- Diagnostic artifacts include validation row scores, validation batch metrics, selected features, and sequence diagnostics.
