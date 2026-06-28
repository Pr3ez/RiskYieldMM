# RPF Ranked Signal Regime Diagnostic

## Purpose

Diagnose whether ranked-signal quality is conditional on prediction-safe latent regimes and change-risk alarms.

## Inputs

- `test_output/rpf_ranked_signal_router/20260628_120309_rank_signal_router_btcusdt_8h_b`
- `test_output/rpf_ranked_signal_router/20260628_123958_rank_signal_router_btcusdt_8h_b`
- `test_output/rpf_ranked_signal_router/20260628_102938_rank_signal_router_btcusdt_8h_b`
- `test_output/rpf_ranked_signal_router/20260628_110557_rank_signal_router_btcusdt_8h_b`

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
- change alarms: `12479`
- state metric rows: `6`
- suppression candidates: `27`

## State Quality

| Side | Candidate | Model | State | Windows | Signals | TP | FP | Precision | Base | Lift | FDR |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| down | down_rocket_16_diag_v1 | gaussian_hmm | 0 | 512 | 794 | 313 | 481 | 0.394207 | 0.385531 | 1.0225 | 0.605793 |
| down | down_rocket_16_diag_v1 | gaussian_hmm | 1 | 614 | 942 | 342 | 600 | 0.363057 | 0.374016 | 0.9707 | 0.636943 |
| down | down_rocket_16_diag_v1 | gaussian_hmm | 2 | 714 | 1147 | 463 | 684 | 0.403662 | 0.387938 | 1.04053 | 0.596338 |
| up | up_rocket_64_v1 | gaussian_hmm | 0 | 499 | 698 | 302 | 396 | 0.432665 | 0.398514 | 1.0857 | 0.567335 |
| up | up_rocket_64_v1 | gaussian_hmm | 1 | 673 | 940 | 395 | 545 | 0.420213 | 0.39813 | 1.05547 | 0.579787 |
| up | up_rocket_64_v1 | gaussian_hmm | 2 | 668 | 916 | 356 | 560 | 0.388646 | 0.372542 | 1.04323 | 0.611354 |

## Regime Target Match

| Side | Candidate | State | Status | Signals | Precision | Base | Lift | FDR | Score |
|---|---|---:|---|---:|---:|---:|---:|---:|---:|
| down | down_rocket_16_diag_v1 | 0 | avoid | 794 | 0.394207 | 0.385531 | 1.0225 | 0.605793 | 0.0167105 |
| down | down_rocket_16_diag_v1 | 1 | avoid | 942 | 0.363057 | 0.374016 | 0.9707 | 0.636943 | -0.0662427 |
| down | down_rocket_16_diag_v1 | 2 | neutral | 1147 | 0.403662 | 0.387938 | 1.04053 | 0.596338 | 0.0441941 |
| up | up_rocket_64_v1 | 2 | avoid | 916 | 0.388646 | 0.372542 | 1.04323 | 0.611354 | 0.0318732 |
| up | up_rocket_64_v1 | 0 | neutral | 698 | 0.432665 | 0.398514 | 1.0857 | 0.567335 | 0.118361 |
| up | up_rocket_64_v1 | 1 | neutral | 940 | 0.420213 | 0.39813 | 1.05547 | 0.579787 | 0.0756783 |

## Change-Risk Target Match

| Side | Candidate | Flag | Value | Status | Signals | Precision | Base | Lift | FDR |
|---|---|---|---|---|---:|---:|---:|---:|---:|
| down | down_rocket_16_diag_v1 | has_cusum | False | avoid | 1684 | 0.391924 | 0.379549 | 1.0326 | 0.608076 |
| down | down_rocket_16_diag_v1 | has_page_hinkley | True | avoid | 2463 | 0.390987 | 0.380271 | 1.02818 | 0.609013 |
| down | down_rocket_16_diag_v1 | has_any_change | True | avoid | 2651 | 0.390041 | 0.37943 | 1.02797 | 0.609959 |
| down | down_rocket_16_diag_v1 | has_cusum | True | avoid | 1331 | 0.393689 | 0.388608 | 1.01307 | 0.606311 |
| down | down_rocket_16_diag_v1 | has_any_change | False | neutral | 364 | 0.412088 | 0.411219 | 1.00211 | 0.587912 |
| down | down_rocket_16_diag_v1 | has_page_hinkley | False | neutral | 552 | 0.400362 | 0.397051 | 1.00834 | 0.599638 |
| up | up_rocket_64_v1 | has_any_change | False | favorable | 352 | 0.426136 | 0.374632 | 1.13748 | 0.573864 |
| up | up_rocket_64_v1 | has_cusum | False | neutral | 1556 | 0.422237 | 0.391439 | 1.07868 | 0.577763 |
| up | up_rocket_64_v1 | has_page_hinkley | False | neutral | 510 | 0.409804 | 0.377854 | 1.08456 | 0.590196 |
| up | up_rocket_64_v1 | has_page_hinkley | True | neutral | 2168 | 0.416974 | 0.390142 | 1.06878 | 0.583026 |
| up | up_rocket_64_v1 | has_any_change | True | neutral | 2326 | 0.414015 | 0.389769 | 1.06221 | 0.585985 |
| up | up_rocket_64_v1 | has_cusum | True | neutral | 1122 | 0.406417 | 0.382953 | 1.06127 | 0.593583 |

## Suppression Candidates

| Side | Candidate | Context | Signals | Lift | FDR | Suppression Score |
|---|---|---|---:|---:|---:|---:|
| down | down_rocket_16_diag_v1 | regime_state_change_flag:1:has_cusum=false | 542 | 0.950311 | 0.653137 | 0.102826 |
| down | down_rocket_16_diag_v1 | regime_state_change_flag:1:has_page_hinkley=true | 761 | 0.953987 | 0.638633 | 0.0846467 |
| down | down_rocket_16_diag_v1 | regime_state_change_flag:2:has_page_hinkley=false | 199 | 0.927583 | 0.59799 | 0.0724166 |
| down | down_rocket_16_diag_v1 | regime_state_change_flag:1:has_any_change=true | 830 | 0.965987 | 0.63494 | 0.068953 |
| down | down_rocket_16_diag_v1 | regime_state:1:= | 942 | 0.9707 | 0.636943 | 0.0662427 |
| down | down_rocket_16_diag_v1 | regime_state_change_flag:0:has_page_hinkley=false | 143 | 0.954067 | 0.608392 | 0.0543242 |
| down | down_rocket_16_diag_v1 | regime_state_change_flag:1:has_any_change=false | 112 | 1.0064 | 0.651786 | 0.0517857 |
| down | down_rocket_16_diag_v1 | regime_state_change_flag:0:has_any_change=false | 92 | 0.953975 | 0.554348 | 0.0460248 |
| down | down_rocket_16_diag_v1 | regime_state_change_flag:0:has_cusum=true | 369 | 0.978076 | 0.617886 | 0.0398097 |
| down | down_rocket_16_diag_v1 | regime_state_change_flag:1:has_page_hinkley=false | 181 | 1.04528 | 0.629834 | 0.0298343 |
| down | down_rocket_16_diag_v1 | regime_state_change_flag:1:has_cusum=true | 400 | 0.997489 | 0.615 | 0.0175107 |
| down | down_rocket_16_diag_v1 | regime_state_change_flag:2:has_any_change=false | 140 | 0.982971 | 0.564286 | 0.0170286 |
| down | down_rocket_16_diag_v1 | regime_state_change_flag:0:has_any_change=true | 702 | 1.03408 | 0.612536 | 0.0125356 |
| down | down_rocket_16_diag_v1 | change_flag::has_any_change=true | 2651 | 1.02797 | 0.609959 | 0.00995851 |
| down | down_rocket_16_diag_v1 | change_flag::has_page_hinkley=true | 2463 | 1.02818 | 0.609013 | 0.0090134 |
| down | down_rocket_16_diag_v1 | change_flag::has_cusum=false | 1684 | 1.0326 | 0.608076 | 0.00807601 |
| down | down_rocket_16_diag_v1 | change_flag::has_cusum=true | 1331 | 1.01307 | 0.606311 | 0.00631104 |
| down | down_rocket_16_diag_v1 | regime_state:0:= | 794 | 1.0225 | 0.605793 | 0.00579345 |
| down | down_rocket_16_diag_v1 | regime_state_change_flag:2:has_cusum=true | 527 | 1.03201 | 0.605313 | 0.00531309 |
| down | down_rocket_16_diag_v1 | regime_state_change_flag:0:has_page_hinkley=true | 651 | 1.0387 | 0.605223 | 0.00522273 |
| down | down_rocket_16_diag_v1 | regime_state_change_flag:2:has_any_change=true | 1007 | 1.05179 | 0.600794 | 0.000794439 |
| up | up_rocket_64_v1 | regime_state_change_flag:2:has_cusum=true | 359 | 0.986555 | 0.643454 | 0.0568992 |
| up | up_rocket_64_v1 | regime_state_change_flag:0:has_any_change=false | 90 | 1.09695 | 0.655556 | 0.0555556 |
| up | up_rocket_64_v1 | regime_state_change_flag:0:has_page_hinkley=false | 144 | 1.09301 | 0.652778 | 0.0527778 |
| up | up_rocket_64_v1 | regime_state_change_flag:2:has_page_hinkley=true | 732 | 1.03053 | 0.624317 | 0.0243169 |
| up | up_rocket_64_v1 | regime_state_change_flag:2:has_any_change=true | 778 | 1.02549 | 0.620823 | 0.0208226 |
| up | up_rocket_64_v1 | regime_state:2:= | 916 | 1.04323 | 0.611354 | 0.0113537 |

## Interpretation

- A useful regime layer should show materially different precision/lift/FDR by state.
- High regime entropy or frequent change alarms should be treated as risk context, not as a signal by itself.
- Favorable/avoid labels are diagnostic; use them for the next shadow suppression replay before changing live routing.
- This command does not modify router decisions; promotion requires a separate walk-forward router mode.
