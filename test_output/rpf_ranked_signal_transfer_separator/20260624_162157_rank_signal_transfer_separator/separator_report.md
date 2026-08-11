# RPF Ranked Signal Transfer Separator Report

## Scope

- diagnostic run: `test_output/rpf_ranked_signal_transfer_diagnostic/20260624_162157_rank_signal_transfer_diagnostic`
- analyzed rows: `81`
- separator rows: `303`

## Group Summary

| Scope | Side | Candidate | Tested Features | Top Feature | Score | Best AUC | Direction | Std Diff |
|---|---|---|---:|---|---:|---:|---|---:|
| all | all | all | 101 | `reliability_precision` | 0.570524 | 0.702635 | lower_good | -0.661014 |
| candidate | down | down_rocket_16_diag_v1 | 101 | `reliability_precision` | 0.570524 | 0.702635 | lower_good | -0.661014 |
| side | down | all | 101 | `reliability_precision` | 0.570524 | 0.702635 | lower_good | -0.661014 |

## Top 50 Separators

| Scope | Side | Candidate | Feature | Score | Best AUC | Direction | Good Mean | Bad Mean | Std Diff |
|---|---|---|---|---:|---:|---|---:|---:|---:|
| all | all | all | `reliability_precision` | 0.570524 | 0.702635 | lower_good | 0.390398 | 0.434757 | -0.661014 |
| all | all | all | `reliability_selected_window_precision` | 0.570524 | 0.702635 | lower_good | 0.390398 | 0.434757 | -0.661014 |
| side | down | all | `reliability_precision` | 0.570524 | 0.702635 | lower_good | 0.390398 | 0.434757 | -0.661014 |
| side | down | all | `reliability_selected_window_precision` | 0.570524 | 0.702635 | lower_good | 0.390398 | 0.434757 | -0.661014 |
| candidate | down | down_rocket_16_diag_v1 | `reliability_precision` | 0.570524 | 0.702635 | lower_good | 0.390398 | 0.434757 | -0.661014 |
| candidate | down | down_rocket_16_diag_v1 | `reliability_selected_window_precision` | 0.570524 | 0.702635 | lower_good | 0.390398 | 0.434757 | -0.661014 |
| all | all | all | `reliability_false_discovery_rate` | 0.570524 | 0.702635 | higher_good | 0.609602 | 0.565243 | 0.661014 |
| all | all | all | `reliability_selected_window_false_discovery_rate` | 0.570524 | 0.702635 | higher_good | 0.609602 | 0.565243 | 0.661014 |
| side | down | all | `reliability_false_discovery_rate` | 0.570524 | 0.702635 | higher_good | 0.609602 | 0.565243 | 0.661014 |
| side | down | all | `reliability_selected_window_false_discovery_rate` | 0.570524 | 0.702635 | higher_good | 0.609602 | 0.565243 | 0.661014 |
| candidate | down | down_rocket_16_diag_v1 | `reliability_false_discovery_rate` | 0.570524 | 0.702635 | higher_good | 0.609602 | 0.565243 | 0.661014 |
| candidate | down | down_rocket_16_diag_v1 | `reliability_selected_window_false_discovery_rate` | 0.570524 | 0.702635 | higher_good | 0.609602 | 0.565243 | 0.661014 |
| all | all | all | `batch_state_gate_probability` | 0.524721 | 0.697531 | lower_good | 0.93875 | 0.977652 | -0.518639 |
| side | down | all | `batch_state_gate_probability` | 0.524721 | 0.697531 | lower_good | 0.93875 | 0.977652 | -0.518639 |
| candidate | down | down_rocket_16_diag_v1 | `batch_state_gate_probability` | 0.524721 | 0.697531 | lower_good | 0.93875 | 0.977652 | -0.518639 |
| all | all | all | `reliability_precision_lift` | 0.521052 | 0.688746 | lower_good | 1.0872 | 1.15396 | -0.574236 |
| side | down | all | `reliability_precision_lift` | 0.521052 | 0.688746 | lower_good | 1.0872 | 1.15396 | -0.574236 |
| candidate | down | down_rocket_16_diag_v1 | `reliability_precision_lift` | 0.521052 | 0.688746 | lower_good | 1.0872 | 1.15396 | -0.574236 |
| all | all | all | `reliability_precision_lcb` | 0.520131 | 0.686966 | lower_good | 0.320646 | 0.353165 | -0.584797 |
| all | all | all | `reliability_selected_window_precision_lcb` | 0.520131 | 0.686966 | lower_good | 0.320646 | 0.353165 | -0.584797 |
| side | down | all | `reliability_precision_lcb` | 0.520131 | 0.686966 | lower_good | 0.320646 | 0.353165 | -0.584797 |
| side | down | all | `reliability_selected_window_precision_lcb` | 0.520131 | 0.686966 | lower_good | 0.320646 | 0.353165 | -0.584797 |
| candidate | down | down_rocket_16_diag_v1 | `reliability_precision_lcb` | 0.520131 | 0.686966 | lower_good | 0.320646 | 0.353165 | -0.584797 |
| candidate | down | down_rocket_16_diag_v1 | `reliability_selected_window_precision_lcb` | 0.520131 | 0.686966 | lower_good | 0.320646 | 0.353165 | -0.584797 |
| all | all | all | `reliability_precision_lift_lcb` | 0.382604 | 0.64245 | lower_good | 0.893671 | 0.942105 | -0.390813 |
| side | down | all | `reliability_precision_lift_lcb` | 0.382604 | 0.64245 | lower_good | 0.893671 | 0.942105 | -0.390813 |
| candidate | down | down_rocket_16_diag_v1 | `reliability_precision_lift_lcb` | 0.382604 | 0.64245 | lower_good | 0.893671 | 0.942105 | -0.390813 |
| all | all | all | `recent_candidate_false_discovery_rate` | 0.367603 | 0.652869 | higher_good | 0.538375 | 0.493563 | 0.247464 |
| side | down | all | `recent_candidate_false_discovery_rate` | 0.367603 | 0.652869 | higher_good | 0.538375 | 0.493563 | 0.247464 |
| candidate | down | down_rocket_16_diag_v1 | `recent_candidate_false_discovery_rate` | 0.367603 | 0.652869 | higher_good | 0.538375 | 0.493563 | 0.247464 |
| all | all | all | `validation_batch_signal_rate_std` | 0.366487 | 0.666442 | lower_good | 0.00575463 | 0.00591303 | -0.134411 |
| side | down | all | `validation_batch_signal_rate_std` | 0.366487 | 0.666442 | lower_good | 0.00575463 | 0.00591303 | -0.134411 |
| candidate | down | down_rocket_16_diag_v1 | `validation_batch_signal_rate_std` | 0.366487 | 0.666442 | lower_good | 0.00575463 | 0.00591303 | -0.134411 |
| all | all | all | `validation_score_max` | 0.340419 | 0.619946 | higher_good | 0.024707 | 0.0204963 | 0.402107 |
| side | down | all | `validation_score_max` | 0.340419 | 0.619946 | higher_good | 0.024707 | 0.0204963 | 0.402107 |
| candidate | down | down_rocket_16_diag_v1 | `validation_score_max` | 0.340419 | 0.619946 | higher_good | 0.024707 | 0.0204963 | 0.402107 |
| all | all | all | `validation_score_q99` | 0.321592 | 0.613881 | higher_good | 0.0243633 | 0.0203824 | 0.375319 |
| side | down | all | `validation_score_q99` | 0.321592 | 0.613881 | higher_good | 0.0243633 | 0.0203824 | 0.375319 |
| candidate | down | down_rocket_16_diag_v1 | `validation_score_q99` | 0.321592 | 0.613881 | higher_good | 0.0243633 | 0.0203824 | 0.375319 |
| all | all | all | `validation_score_q95` | 0.317666 | 0.613881 | higher_good | 0.02365 | 0.0198229 | 0.359614 |
| side | down | all | `validation_score_q95` | 0.317666 | 0.613881 | higher_good | 0.02365 | 0.0198229 | 0.359614 |
| candidate | down | down_rocket_16_diag_v1 | `validation_score_q95` | 0.317666 | 0.613881 | higher_good | 0.02365 | 0.0198229 | 0.359614 |
| all | all | all | `threshold` | 0.317662 | 0.613881 | higher_good | 0.0236503 | 0.0198235 | 0.359595 |
| side | down | all | `threshold` | 0.317662 | 0.613881 | higher_good | 0.0236503 | 0.0198235 | 0.359595 |
| candidate | down | down_rocket_16_diag_v1 | `threshold` | 0.317662 | 0.613881 | higher_good | 0.0236503 | 0.0198235 | 0.359595 |
| all | all | all | `validation_margin_min` | 0.300659 | 0.605795 | lower_good | -0.0462794 | -0.0387223 | -0.356273 |
| side | down | all | `validation_margin_min` | 0.300659 | 0.605795 | lower_good | -0.0462794 | -0.0387223 | -0.356273 |
| candidate | down | down_rocket_16_diag_v1 | `validation_margin_min` | 0.300659 | 0.605795 | lower_good | -0.0462794 | -0.0387223 | -0.356273 |
| all | all | all | `reliability_reliability_score` | 0.284951 | 0.599057 | lower_good | -0.929373 | -0.822916 | -0.34735 |
| side | down | all | `reliability_reliability_score` | 0.284951 | 0.599057 | lower_good | -0.929373 | -0.822916 | -0.34735 |

## Interpretation

- This is separator evidence only; it does not prove a deployable meta-router.
- Features are from `safe_context_features.parquet`; current prediction labels are used only as post-hoc labels.
- A high score means the field separated `candidate_good` from `candidate_bad` on the compared blocks.
