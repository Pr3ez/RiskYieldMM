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
- change alarms: `327`
- state metric rows: `6`

## State Quality

| Side | Candidate | Model | State | Windows | Signals | TP | FP | Precision | Base | Lift | FDR |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| down | down_rocket_16_diag_v1 | gmm_markov_proxy | 0 | 585 | 901 | 329 | 572 | 0.36515 | 0.382343 | 0.955031 | 0.63485 |
| down | down_rocket_16_diag_v1 | gmm_markov_proxy | 1 | 615 | 930 | 369 | 561 | 0.396774 | 0.383435 | 1.03479 | 0.603226 |
| down | down_rocket_16_diag_v1 | gmm_markov_proxy | 2 | 640 | 1052 | 420 | 632 | 0.39924 | 0.382096 | 1.04487 | 0.60076 |
| up | up_rocket_64_v1 | gmm_markov_proxy | 0 | 563 | 792 | 316 | 476 | 0.39899 | 0.355506 | 1.12231 | 0.60101 |
| up | up_rocket_64_v1 | gmm_markov_proxy | 1 | 644 | 903 | 392 | 511 | 0.434109 | 0.40099 | 1.08259 | 0.565891 |
| up | up_rocket_64_v1 | gmm_markov_proxy | 2 | 633 | 859 | 345 | 514 | 0.40163 | 0.406431 | 0.988187 | 0.59837 |

## Interpretation

- A useful regime layer should show materially different precision/lift/FDR by state.
- High regime entropy or frequent change alarms should be treated as risk context, not as a signal by itself.
- This command does not modify router decisions; promotion requires a separate walk-forward router mode.
