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
- `regime_target_match.parquet` labels states as favorable/neutral/avoid for each target side.
- `change_risk_target_match.parquet` labels change-risk flags by side.
- `regime_suppression_candidates.parquet` lists contexts that should be tested as false-positive suppressors.

## Summary

- context rows: `960`
- change alarms: `3559`
- state metric rows: `2`
- suppression candidates: `11`

## State Quality

| Side | Candidate | Model | State | Windows | Signals | TP | FP | Precision | Base | Lift | FDR |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| up | up_rocket_64_v1 | gmm_markov_proxy | 0 | 429 | 595 | 223 | 372 | 0.37479 | 0.360907 | 1.03847 | 0.62521 |
| up | up_rocket_64_v1 | gmm_markov_proxy | 1 | 511 | 682 | 294 | 388 | 0.431085 | 0.386138 | 1.1164 | 0.568915 |

## Regime Target Match

| Side | Candidate | State | Status | Signals | Precision | Base | Lift | FDR | Score |
|---|---|---:|---|---:|---:|---:|---:|---:|---:|
| up | up_rocket_64_v1 | 0 | avoid | 595 | 0.37479 | 0.360907 | 1.03847 | 0.62521 | 0.0132562 |
| up | up_rocket_64_v1 | 1 | favorable | 682 | 0.431085 | 0.386138 | 1.1164 | 0.568915 | 0.147486 |

## Change-Risk Target Match

| Side | Candidate | Flag | Value | Status | Signals | Precision | Base | Lift | FDR |
|---|---|---|---|---|---:|---:|---:|---:|---:|
| up | up_rocket_64_v1 | has_page_hinkley | False | avoid | 363 | 0.399449 | 0.373725 | 1.06883 | 0.600551 |
| up | up_rocket_64_v1 | has_cusum | False | avoid | 341 | 0.372434 | 0.3737 | 0.996612 | 0.627566 |
| up | up_rocket_64_v1 | has_any_change | False | avoid | 116 | 0.301724 | 0.359604 | 0.839046 | 0.698276 |
| up | up_rocket_64_v1 | has_cusum | True | favorable | 964 | 0.420124 | 0.375775 | 1.11802 | 0.579876 |
| up | up_rocket_64_v1 | has_any_change | True | neutral | 1189 | 0.417998 | 0.376694 | 1.10965 | 0.582002 |
| up | up_rocket_64_v1 | has_page_hinkley | True | neutral | 942 | 0.410828 | 0.375819 | 1.09315 | 0.589172 |

## Suppression Candidates

| Side | Candidate | Context | Signals | Lift | FDR | Suppression Score |
|---|---|---|---:|---:|---:|---:|
| up | up_rocket_64_v1 | change_flag::has_any_change=false | 116 | 0.839046 | 0.698276 | 0.25923 |
| up | up_rocket_64_v1 | regime_state_change_flag:0:has_cusum=false | 159 | 0.910656 | 0.654088 | 0.143432 |
| up | up_rocket_64_v1 | regime_state_change_flag:0:has_page_hinkley=true | 435 | 1.02341 | 0.634483 | 0.0344828 |
| up | up_rocket_64_v1 | change_flag::has_cusum=false | 341 | 0.996612 | 0.627566 | 0.0309537 |
| up | up_rocket_64_v1 | regime_state:0:= | 595 | 1.03847 | 0.62521 | 0.0252101 |
| up | up_rocket_64_v1 | regime_state_change_flag:0:has_any_change=true | 540 | 1.06677 | 0.614815 | 0.0148148 |
| up | up_rocket_64_v1 | regime_state_change_flag:0:has_cusum=true | 436 | 1.08882 | 0.614679 | 0.0146789 |
| up | up_rocket_64_v1 | regime_state_change_flag:1:has_cusum=false | 164 | 1.07847 | 0.609756 | 0.0097561 |
| up | up_rocket_64_v1 | regime_state_change_flag:1:has_page_hinkley=false | 193 | 1.05892 | 0.601036 | 0.00103627 |
| up | up_rocket_64_v1 | change_flag::has_page_hinkley=false | 363 | 1.06883 | 0.600551 | 0.000550964 |
| up | up_rocket_64_v1 | regime_state_change_flag:0:has_page_hinkley=false | 160 | 1.0759 | 0.6 | 0 |

## Interpretation

- A useful regime layer should show materially different precision/lift/FDR by state.
- High regime entropy or frequent change alarms should be treated as risk context, not as a signal by itself.
- Favorable/avoid labels are diagnostic; use them for the next shadow suppression replay before changing live routing.
- This command does not modify router decisions; promotion requires a separate walk-forward router mode.
