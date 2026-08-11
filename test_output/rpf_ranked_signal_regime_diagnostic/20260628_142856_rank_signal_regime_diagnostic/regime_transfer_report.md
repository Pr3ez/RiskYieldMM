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
- `regime_target_match.parquet` labels states as favorable/neutral/avoid for each target side.
- `change_risk_target_match.parquet` labels change-risk flags by side.
- `regime_suppression_candidates.parquet` lists contexts that should be tested as false-positive suppressors.

## Summary

- context rows: `3840`
- change alarms: `327`
- state metric rows: `6`
- suppression candidates: `22`

## State Quality

| Side | Candidate | Model | State | Windows | Signals | TP | FP | Precision | Base | Lift | FDR |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| down | down_rocket_16_diag_v1 | gmm_markov_proxy | 0 | 585 | 901 | 329 | 572 | 0.36515 | 0.382343 | 0.955031 | 0.63485 |
| down | down_rocket_16_diag_v1 | gmm_markov_proxy | 1 | 615 | 930 | 369 | 561 | 0.396774 | 0.383435 | 1.03479 | 0.603226 |
| down | down_rocket_16_diag_v1 | gmm_markov_proxy | 2 | 640 | 1052 | 420 | 632 | 0.39924 | 0.382096 | 1.04487 | 0.60076 |
| up | up_rocket_64_v1 | gmm_markov_proxy | 0 | 563 | 792 | 316 | 476 | 0.39899 | 0.355506 | 1.12231 | 0.60101 |
| up | up_rocket_64_v1 | gmm_markov_proxy | 1 | 644 | 903 | 392 | 511 | 0.434109 | 0.40099 | 1.08259 | 0.565891 |
| up | up_rocket_64_v1 | gmm_markov_proxy | 2 | 633 | 859 | 345 | 514 | 0.40163 | 0.406431 | 0.988187 | 0.59837 |

## Regime Target Match

| Side | Candidate | State | Status | Signals | Precision | Base | Lift | FDR | Score |
|---|---|---:|---|---:|---:|---:|---:|---:|---:|
| down | down_rocket_16_diag_v1 | 2 | avoid | 1052 | 0.39924 | 0.382096 | 1.04487 | 0.60076 | 0.0441057 |
| down | down_rocket_16_diag_v1 | 1 | avoid | 930 | 0.396774 | 0.383435 | 1.03479 | 0.603226 | 0.031563 |
| down | down_rocket_16_diag_v1 | 0 | avoid | 901 | 0.36515 | 0.382343 | 0.955031 | 0.63485 | -0.0798188 |
| up | up_rocket_64_v1 | 0 | avoid | 792 | 0.39899 | 0.355506 | 1.12231 | 0.60101 | 0.121305 |
| up | up_rocket_64_v1 | 2 | avoid | 859 | 0.40163 | 0.406431 | 0.988187 | 0.59837 | -0.0101833 |
| up | up_rocket_64_v1 | 1 | neutral | 903 | 0.434109 | 0.40099 | 1.08259 | 0.565891 | 0.116701 |

## Change-Risk Target Match

| Side | Candidate | Flag | Value | Status | Signals | Precision | Base | Lift | FDR |
|---|---|---|---|---|---:|---:|---:|---:|---:|
| down | down_rocket_16_diag_v1 | has_cusum | False | avoid | 2813 | 0.395663 | 0.384187 | 1.02987 | 0.604337 |
| down | down_rocket_16_diag_v1 | has_any_change | False | avoid | 2769 | 0.393644 | 0.383704 | 1.0259 | 0.606356 |
| down | down_rocket_16_diag_v1 | has_page_hinkley | False | avoid | 2962 | 0.391627 | 0.382979 | 1.02258 | 0.608373 |
| down | down_rocket_16_diag_v1 | has_any_change | True | avoid | 246 | 0.382114 | 0.380622 | 1.00392 | 0.617886 |
| down | down_rocket_16_diag_v1 | has_cusum | True | avoid | 202 | 0.351485 | 0.37221 | 0.944319 | 0.648515 |
| down | down_rocket_16_diag_v1 | has_page_hinkley | True | neutral | 53 | 0.45283 | 0.409144 | 1.10678 | 0.54717 |
| up | up_rocket_64_v1 | has_cusum | True | favorable | 143 | 0.440559 | 0.39591 | 1.11278 | 0.559441 |
| up | up_rocket_64_v1 | has_page_hinkley | False | neutral | 2614 | 0.418133 | 0.388583 | 1.07605 | 0.581867 |
| up | up_rocket_64_v1 | has_any_change | False | neutral | 2473 | 0.416498 | 0.387843 | 1.07388 | 0.583502 |
| up | up_rocket_64_v1 | has_cusum | False | neutral | 2535 | 0.414201 | 0.387318 | 1.06941 | 0.585799 |
| up | up_rocket_64_v1 | has_any_change | True | neutral | 205 | 0.404878 | 0.387358 | 1.04523 | 0.595122 |
| up | up_rocket_64_v1 | has_page_hinkley | True | neutral | 64 | 0.3125 | 0.353075 | 0.88508 | 0.6875 |

## Suppression Candidates

| Side | Candidate | Context | Signals | Lift | FDR | Suppression Score |
|---|---|---|---:|---:|---:|---:|
| down | down_rocket_16_diag_v1 | change_flag::has_cusum=true | 202 | 0.944319 | 0.648515 | 0.104196 |
| down | down_rocket_16_diag_v1 | regime_state_change_flag:0:has_any_change=false | 830 | 0.93958 | 0.637349 | 0.0977693 |
| down | down_rocket_16_diag_v1 | regime_state_change_flag:0:has_page_hinkley=false | 892 | 0.949264 | 0.637892 | 0.0886286 |
| down | down_rocket_16_diag_v1 | regime_state_change_flag:0:has_cusum=false | 836 | 0.948106 | 0.633971 | 0.085865 |
| down | down_rocket_16_diag_v1 | regime_state:0:= | 901 | 0.955031 | 0.63485 | 0.0798188 |
| down | down_rocket_16_diag_v1 | change_flag::has_any_change=true | 246 | 1.00392 | 0.617886 | 0.0178862 |
| down | down_rocket_16_diag_v1 | regime_state_change_flag:1:has_any_change=false | 835 | 1.02925 | 0.608383 | 0.00838323 |
| down | down_rocket_16_diag_v1 | change_flag::has_page_hinkley=false | 2962 | 1.02258 | 0.608373 | 0.00837272 |
| down | down_rocket_16_diag_v1 | regime_state_change_flag:1:has_page_hinkley=false | 902 | 1.03572 | 0.60643 | 0.00643016 |
| down | down_rocket_16_diag_v1 | change_flag::has_any_change=false | 2769 | 1.0259 | 0.606356 | 0.00635609 |
| down | down_rocket_16_diag_v1 | change_flag::has_cusum=false | 2813 | 1.02987 | 0.604337 | 0.00433701 |
| down | down_rocket_16_diag_v1 | regime_state_change_flag:1:has_cusum=false | 860 | 1.03333 | 0.603488 | 0.00348837 |
| down | down_rocket_16_diag_v1 | regime_state:1:= | 930 | 1.03479 | 0.603226 | 0.00322581 |
| down | down_rocket_16_diag_v1 | regime_state:2:= | 1052 | 1.04487 | 0.60076 | 0.000760456 |
| up | up_rocket_64_v1 | regime_state_change_flag:2:has_any_change=true | 80 | 0.989369 | 0.6625 | 0.0731311 |
| up | up_rocket_64_v1 | regime_state_change_flag:2:has_page_hinkley=false | 837 | 0.985351 | 0.599761 | 0.0146493 |
| up | up_rocket_64_v1 | regime_state:2:= | 859 | 0.988187 | 0.59837 | 0.0118131 |
| up | up_rocket_64_v1 | regime_state_change_flag:2:has_any_change=false | 779 | 0.989562 | 0.591784 | 0.0104381 |
| up | up_rocket_64_v1 | regime_state_change_flag:0:has_cusum=false | 756 | 1.0975 | 0.609788 | 0.00978836 |
| up | up_rocket_64_v1 | regime_state_change_flag:2:has_cusum=false | 801 | 0.991752 | 0.590512 | 0.0082475 |
| up | up_rocket_64_v1 | regime_state_change_flag:0:has_any_change=false | 742 | 1.1088 | 0.602426 | 0.00242588 |
| up | up_rocket_64_v1 | regime_state:0:= | 792 | 1.12231 | 0.60101 | 0.0010101 |

## Interpretation

- A useful regime layer should show materially different precision/lift/FDR by state.
- High regime entropy or frequent change alarms should be treated as risk context, not as a signal by itself.
- Favorable/avoid labels are diagnostic; use them for the next shadow suppression replay before changing live routing.
- This command does not modify router decisions; promotion requires a separate walk-forward router mode.
