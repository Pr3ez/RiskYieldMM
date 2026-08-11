# RPF Ranked Signal Router Report

## Scope

- `asset`: `BTCUSDT`
- `root`: `8h/B`
- `candidate_set`: `default_v1`
- `outer_window_count`: `240`

## Side Summary

- `up`: `{'rows': 57600, 'positive_count': 22813, 'negative_count': 34787, 'predicted_positive_count': 185, 'true_positive_count': 74, 'false_positive_count': 111, 'false_negative_count': 22739, 'true_negative_count': 34676, 'precision': 0.4, 'recall': 0.0032437645202296936, 'false_positive_rate': 0.003190847155546612, 'false_discovery_rate': 0.6, 'predicted_positive_rate': 0.0032118055555555554, 'base_positive_rate': 0.3960590277777778, 'precision_lift': 1.009950466839083, 'decision_cost': 23294.0, 'decision_cost_per_row': 0.4044097222222222, 'decision_cost_per_signal': 125.91351351351351, 'active_window_rate': 0.3458333333333333, 'zero_signal_window_rate': 0.6541666666666667, 'high_target_window_count': 134, 'high_target_window_capture_rate': 0.23880597014925373, 'missed_high_target_window_rate': 0.7611940298507462, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 20.791666666666668, 'ranked_signal_quality': -1.577163159916361}`
- `down`: `{'rows': 57600, 'positive_count': 21617, 'negative_count': 35983, 'predicted_positive_count': 244, 'true_positive_count': 124, 'false_positive_count': 120, 'false_negative_count': 21493, 'true_negative_count': 35863, 'precision': 0.5081967213114754, 'recall': 0.005736226118332794, 'false_positive_rate': 0.003334908151071339, 'false_discovery_rate': 0.4918032786885246, 'predicted_positive_rate': 0.0042361111111111115, 'base_positive_rate': 0.3752951388888889, 'precision_lift': 1.354125509901512, 'decision_cost': 22093.0, 'decision_cost_per_row': 0.3835590277777778, 'decision_cost_per_signal': 90.54508196721312, 'active_window_rate': 0.3458333333333333, 'zero_signal_window_rate': 0.6541666666666667, 'high_target_window_count': 130, 'high_target_window_capture_rate': 0.3076923076923077, 'missed_high_target_window_rate': 0.6923076923076923, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 39.083333333333336, 'ranked_signal_quality': -0.5366838596105953}`

## Decision Contract

- Candidates are selected from validation metrics only.
- Prediction metrics are outer evaluation and never choose a candidate.
- If no candidate passes validation gates, the side emits no signals for that prediction batch.
