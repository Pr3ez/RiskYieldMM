# RPF Ranked Signal Regime Diagnostic

## Purpose

Diagnose whether ranked-signal quality is conditional on prediction-safe latent regimes and change-risk alarms.

## Inputs

- `test_output/rpf_ranked_signal_router/20260628_102938_rank_signal_router_btcusdt_8h_b`

## Artifact Contract

- `regime_context.parquet` contains prediction-time-safe context and past-only regime assignments.
- `regime_signal_quality.parquet` joins matured outcomes for analysis only.
- `change_point_events.parquet` contains CUSUM/Page-Hinkley style change alarms from safe context features.
- `hmm_state_metrics.parquet` summarizes signal quality by inferred state.

## Summary

- context rows: `960`
- change alarms: `1644`
- state metric rows: `2`

## State Quality

| Side | Candidate | Model | State | Windows | Signals | TP | FP | Precision | Base | Lift | FDR |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| up | up_rocket_64_v1 | gmm_markov_proxy | 0 | 431 | 580 | 247 | 333 | 0.425862 | 0.38228 | 1.11401 | 0.574138 |
| up | up_rocket_64_v1 | gmm_markov_proxy | 1 | 509 | 697 | 270 | 427 | 0.387374 | 0.36814 | 1.05225 | 0.612626 |

## Interpretation

- A useful regime layer should show materially different precision/lift/FDR by state.
- High regime entropy or frequent change alarms should be treated as risk context, not as a signal by itself.
- This command does not modify router decisions; promotion requires a separate walk-forward router mode.
