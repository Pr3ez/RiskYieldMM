# RPF Ranked Signal Regime Diagnostic

## Purpose

Diagnose whether ranked-signal quality is conditional on prediction-safe latent regimes and change-risk alarms.

## Inputs

- `test_output/rpf_ranked_signal_router/20260628_102938_rank_signal_router_btcusdt_8h_b`
- `test_output/rpf_ranked_signal_router/20260628_110557_rank_signal_router_btcusdt_8h_b`
- `test_output/rpf_ranked_signal_router/20260628_120309_rank_signal_router_btcusdt_8h_b`
- `test_output/rpf_ranked_signal_router/20260628_123958_rank_signal_router_btcusdt_8h_b`

## Artifact Contract

- `regime_context.parquet` contains prediction-time-safe context and past-only regime assignments.
- `regime_signal_quality.parquet` joins matured outcomes for analysis only.
- `change_point_events.parquet` contains CUSUM/Page-Hinkley style change alarms from safe context features.
- `hmm_state_metrics.parquet` summarizes signal quality by inferred state.

## Summary

- context rows: `3840`
- change alarms: `9063`
- state metric rows: `6`

## State Quality

| Side | Candidate | Model | State | Windows | Signals | TP | FP | Precision | Base | Lift | FDR |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| down | down_rocket_16_diag_v1 | gmm_markov_proxy | 0 | 629 | 954 | 385 | 569 | 0.403564 | 0.393468 | 1.02566 | 0.596436 |
| down | down_rocket_16_diag_v1 | gmm_markov_proxy | 1 | 591 | 922 | 366 | 556 | 0.396963 | 0.37273 | 1.06502 | 0.603037 |
| down | down_rocket_16_diag_v1 | gmm_markov_proxy | 2 | 620 | 1004 | 391 | 613 | 0.389442 | 0.392991 | 0.990971 | 0.610558 |
| up | up_rocket_64_v1 | gmm_markov_proxy | 0 | 575 | 792 | 297 | 495 | 0.375 | 0.354043 | 1.05919 | 0.625 |
| up | up_rocket_64_v1 | gmm_markov_proxy | 1 | 655 | 922 | 416 | 506 | 0.451193 | 0.406902 | 1.10885 | 0.548807 |
| up | up_rocket_64_v1 | gmm_markov_proxy | 2 | 610 | 855 | 344 | 511 | 0.402339 | 0.398996 | 1.00838 | 0.597661 |

## Interpretation

- A useful regime layer should show materially different precision/lift/FDR by state.
- High regime entropy or frequent change alarms should be treated as risk context, not as a signal by itself.
- This command does not modify router decisions; promotion requires a separate walk-forward router mode.
