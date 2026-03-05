# Hybrid vs Baseline (Full 500-Batch Production Comparison)

- Generated (UTC): 2026-02-21T11:12:24.303697+00:00
- Baseline anchor universe: 8608
- Hybrid anchor universe: 5472
- Baseline final rows: 6688
- Hybrid final rows: 3552
- Common comparable rows: 3552 (batches=222)

## Full-run summary (not directly comparable due row-count mismatch)
- macro_f1: baseline=0.505263, hybrid=0.514504, delta=0.009241
- directional_active_accuracy: baseline=0.505263, hybrid=0.514504, delta=0.009241
- directional_active_coverage: baseline=0.170455, hybrid=0.184403, delta=0.013949
- directional_safe_accuracy: baseline=0.915670, hybrid=0.910473, delta=-0.005197
- opposite_fp_rate_covered: baseline=0.084330, hybrid=0.089527, delta=0.005197
- opposite_fp_rate_active: baseline=0.494737, hybrid=0.485496, delta=-0.009241
- custom_mean_cost: baseline=0.168660, hybrid=0.179054, delta=0.010394
- custom_utility: baseline=0.915670, hybrid=0.910473, delta=-0.005197
- fp_risk_score: baseline=None, hybrid=None, delta=None

## Common-row fair comparison (same anchors)
- macro_f1: baseline=0.558036, hybrid=0.514504, delta=-0.043532
- directional_active_accuracy: baseline=0.558036, hybrid=0.514504, delta=-0.043532
- directional_active_coverage: baseline=0.126126, hybrid=0.184403, delta=0.058277
- directional_safe_accuracy: baseline=0.944257, hybrid=0.910473, delta=-0.033784
- opposite_fp_rate_covered: baseline=0.055743, hybrid=0.089527, delta=0.033784
- opposite_fp_rate_active: baseline=0.441964, hybrid=0.485496, delta=0.043532
- custom_mean_cost: baseline=0.111486, hybrid=0.179054, delta=0.067568
- custom_utility: baseline=0.944257, hybrid=0.910473, delta=-0.033784
- fp_risk_score: baseline=0.126971, hybrid=0.212556, delta=0.085586

## Interpretation
- Hybrid appears better on full-run macro_f1 only because it drops many hard rows (coverage collapse from 6688 to 3552 rows).
- On the exact same anchors, baseline is materially better: higher directional accuracy and lower opposite-direction risk/cost.
- Recommendation: do not deploy this hybrid set as-is; enforce per-candidate full-history support constraints before diversity pruning.