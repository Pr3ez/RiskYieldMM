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
| down | down_rocket_16_diag_v1 | gaussian_hmm | 0 | 512 | 837 | 334 | 503 | 0.399044 | 0.372957 | 1.06995 | 0.600956 |
| down | down_rocket_16_diag_v1 | gaussian_hmm | 1 | 616 | 965 | 408 | 557 | 0.422798 | 0.395042 | 1.07026 | 0.577202 |
| down | down_rocket_16_diag_v1 | gaussian_hmm | 2 | 712 | 1078 | 400 | 678 | 0.371058 | 0.389226 | 0.953321 | 0.628942 |
| up | up_rocket_64_v1 | gaussian_hmm | 0 | 530 | 752 | 327 | 425 | 0.43484 | 0.392492 | 1.1079 | 0.56516 |
| up | up_rocket_64_v1 | gaussian_hmm | 1 | 644 | 907 | 354 | 553 | 0.390298 | 0.378041 | 1.03242 | 0.609702 |
| up | up_rocket_64_v1 | gaussian_hmm | 2 | 666 | 910 | 376 | 534 | 0.413187 | 0.3934 | 1.0503 | 0.586813 |

## Interpretation

- A useful regime layer should show materially different precision/lift/FDR by state.
- High regime entropy or frequent change alarms should be treated as risk context, not as a signal by itself.
- This command does not modify router decisions; promotion requires a separate walk-forward router mode.
