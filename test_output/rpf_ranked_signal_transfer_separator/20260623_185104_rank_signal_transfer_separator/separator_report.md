# RPF Ranked Signal Transfer Separator Report

## Scope

- diagnostic run: `test_output/rpf_ranked_signal_transfer_diagnostic/20260623_183857_rank_signal_transfer_diagnostic`
- analyzed rows: `133`
- separator rows: `403`

## Group Summary

| Scope | Side | Candidate | Tested Features | Top Feature | Score | Best AUC | Direction | Std Diff |
|---|---|---|---:|---|---:|---:|---|---:|
| all | all | all | 62 | `recent_candidate_selected_window_row_lift_lcb` | 0.445718 | 0.690549 | lower_good | -0.25848 |
| candidate | down | down_none_v1 | 57 | `recent_candidate_selected_window_row_lift` | 1.26975 | 0.938095 | lower_good | -1.57423 |
| candidate | down | down_rocket_16_diag_v1 | 56 | `reliability_precision_lift` | 0.594151 | 0.729167 | lower_good | -0.543269 |
| candidate | up | up_none_v1 | 56 | `reliability_active_window_rate` | 1.4 | 0.95 | lower_good | -2.18169 |
| candidate | up | up_rocket_64_v1 | 55 | `score_mean` | 0.874759 | 0.803309 | lower_good | -1.07257 |
| side | down | all | 58 | `reliability_selected_window_row_lift` | 0.500379 | 0.682518 | lower_good | -0.541371 |
| side | up | all | 59 | `recent_candidate_selected_window_row_lift_lcb` | 0.569974 | 0.739286 | lower_good | -0.365612 |

## Top 20 Separators

| Scope | Side | Candidate | Feature | Score | Best AUC | Direction | Good Mean | Bad Mean | Std Diff |
|---|---|---|---|---:|---:|---|---:|---:|---:|
| candidate | up | up_none_v1 | `reliability_active_window_rate` | 1.4 | 0.95 | lower_good | 0.0166667 | 0.0529768 | -2.18169 |
| candidate | up | up_none_v1 | `reliability_zero_signal_window_rate` | 1.4 | 0.95 | higher_good | 0.983333 | 0.947023 | 2.18169 |
| candidate | up | up_none_v1 | `reliability_active_windows` | 1.3141 | 0.925 | lower_good | 1 | 2.6 | -1.85638 |
| candidate | down | down_none_v1 | `recent_candidate_selected_window_row_lift` | 1.26975 | 0.938095 | lower_good | 1.17912 | 1.56834 | -1.57423 |
| candidate | up | up_none_v1 | `reliability_signal_count` | 1.19041 | 0.9 | lower_good | 3 | 6.6 | -1.56164 |
| candidate | up | up_none_v1 | `threshold` | 1.05291 | 0.85 | higher_good | 0.0145667 | 0.0039547 | 1.41166 |
| candidate | up | up_none_v1 | `recent_candidate_selected_window_row_lift_lcb` | 1.04372 | 0.85 | lower_good | 0.859578 | 1.19136 | -1.37487 |
| candidate | down | down_none_v1 | `recent_candidate_selected_window_row_lift_lcb` | 0.893519 | 0.795238 | lower_good | 0.845464 | 1.07639 | -1.21217 |
| candidate | up | up_rocket_64_v1 | `score_mean` | 0.874759 | 0.803309 | lower_good | -0.000550256 | 0.00100173 | -1.07257 |
| candidate | up | up_none_v1 | `reliability_reliability_score` | 0.813736 | 0.825 | lower_good | -0.829096 | 0.459955 | -0.654944 |
| candidate | down | down_none_v1 | `reliability_selected_window_row_lift` | 0.795647 | 0.795238 | lower_good | 1.11118 | 1.52711 | -0.820684 |
| candidate | up | up_none_v1 | `recent_candidate_selected_window_row_lift` | 0.761495 | 0.75 | lower_good | 1.21001 | 1.47601 | -1.04598 |
| candidate | up | up_none_v1 | `validation_precision` | 0.75 | 0.75 | lower_good | 0 | 0.5 | -1 |
| candidate | up | up_none_v1 | `validation_precision_lift` | 0.75 | 0.75 | lower_good | 0 | 1.01351 | -1 |
| candidate | up | up_none_v1 | `validation_false_discovery_rate` | 0.75 | 0.75 | higher_good | 1 | 0.5 | 1 |
| candidate | up | up_none_v1 | `past_60_batch_positive_rate_std` | 0.746324 | 0.775 | higher_good | 0.389101 | 0.376686 | 0.785298 |
| candidate | up | up_none_v1 | `recent_candidate_precision_lift_lcb` | 0.690989 | 0.775 | lower_good | 1.02363 | 1.37525 | -0.563954 |
| candidate | down | down_none_v1 | `score_mean` | 0.676758 | 0.742188 | lower_good | 0.00228211 | 0.00712123 | -0.769534 |
| candidate | up | up_rocket_64_v1 | `batch_state_gate_val_pass_rate` | 0.626309 | 0.725184 | lower_good | 0.447059 | 0.6125 | -0.703764 |
| candidate | down | down_none_v1 | `reliability_selected_window_row_lift_lcb` | 0.615845 | 0.719048 | lower_good | 0.772327 | 1.01543 | -0.710999 |

## Interpretation

- This is separator evidence only; it does not prove a deployable meta-router.
- Features are from `safe_context_features.parquet`; current prediction labels are used only as post-hoc labels.
- A high score means the field separated `candidate_good` from `candidate_bad` on the compared blocks.
