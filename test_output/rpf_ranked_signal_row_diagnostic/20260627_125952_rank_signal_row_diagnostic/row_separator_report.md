# RPF Ranked Signal Row Diagnostic

## Scope

- router runs: `8`
- signal rows: `811`
- TP rows: `354`
- FP rows: `457`

## Candidate Signal Summary

| Source | Side | Candidate | Signals | TP | FP | Precision |
|---|---|---|---:|---:|---:|---:|
| latest | down | down_rocket_16_diag_v1 | 92 | 38 | 54 | 0.413043 |
| middle | down | down_rocket_16_diag_v1 | 102 | 45 | 57 | 0.441176 |
| offset180 | down | down_rocket_16_diag_v1 | 106 | 58 | 48 | 0.54717 |
| offset240 | down | down_rocket_16_diag_v1 | 107 | 47 | 60 | 0.439252 |
| offset300 | down | down_rocket_16_diag_v1 | 93 | 48 | 45 | 0.516129 |
| offset360 | down | down_rocket_16_diag_v1 | 134 | 49 | 85 | 0.365672 |
| offset420 | down | down_rocket_16_diag_v1 | 97 | 39 | 58 | 0.402062 |
| offset60 | down | down_rocket_16_diag_v1 | 80 | 30 | 50 | 0.375 |

## Separator Summary

| Scope | Side | Candidate | Tested Features | Top Feature | Score | Best AUC | Direction | Std Diff |
|---|---|---|---:|---|---:|---:|---|---:|
| all | all | all | 51 | `threshold` | 0.271943 | 0.591638 | higher_good | 0.354668 |
| candidate | down | down_rocket_16_diag_v1 | 51 | `threshold` | 0.271943 | 0.591638 | higher_good | 0.354668 |
| side | down | all | 51 | `threshold` | 0.271943 | 0.591638 | higher_good | 0.354668 |

## Top 30 Row Separators

| Scope | Side | Candidate | Feature | Score | Best AUC | Direction | TP Mean | FP Mean | Std Diff |
|---|---|---|---|---:|---:|---|---:|---:|---:|
| all | all | all | `threshold` | 0.271943 | 0.591638 | higher_good | 0.0257727 | 0.02251 | 0.354668 |
| side | down | all | `threshold` | 0.271943 | 0.591638 | higher_good | 0.0257727 | 0.02251 | 0.354668 |
| candidate | down | down_rocket_16_diag_v1 | `threshold` | 0.271943 | 0.591638 | higher_good | 0.0257727 | 0.02251 | 0.354668 |
| all | all | all | `rank_score` | 0.271123 | 0.591329 | higher_good | 0.0260149 | 0.0228043 | 0.353862 |
| side | down | all | `rank_score` | 0.271123 | 0.591329 | higher_good | 0.0260149 | 0.0228043 | 0.353862 |
| candidate | down | down_rocket_16_diag_v1 | `rank_score` | 0.271123 | 0.591329 | higher_good | 0.0260149 | 0.0228043 | 0.353862 |
| all | all | all | `row_rpf_volatility_state_mean_abs` | 0.203536 | 0.57344 | higher_good | 0.465068 | 0.428287 | 0.226625 |
| side | down | all | `row_rpf_volatility_state_mean_abs` | 0.203536 | 0.57344 | higher_good | 0.465068 | 0.428287 | 0.226625 |
| candidate | down | down_rocket_16_diag_v1 | `row_rpf_volatility_state_mean_abs` | 0.203536 | 0.57344 | higher_good | 0.465068 | 0.428287 | 0.226625 |
| all | all | all | `row_rpf_spike_breakout_mean` | 0.198274 | 0.568996 | higher_good | 0.180982 | 0.172538 | 0.241131 |
| side | down | all | `row_rpf_spike_breakout_mean` | 0.198274 | 0.568996 | higher_good | 0.180982 | 0.172538 | 0.241131 |
| candidate | down | down_rocket_16_diag_v1 | `row_rpf_spike_breakout_mean` | 0.198274 | 0.568996 | higher_good | 0.180982 | 0.172538 | 0.241131 |
| all | all | all | `row_rpf_unsupervised_factor_layer_positive_rate` | 0.197345 | 0.571805 | higher_good | 0.833333 | 0.807896 | 0.21494 |
| side | down | all | `row_rpf_unsupervised_factor_layer_positive_rate` | 0.197345 | 0.571805 | higher_good | 0.833333 | 0.807896 | 0.21494 |
| candidate | down | down_rocket_16_diag_v1 | `row_rpf_unsupervised_factor_layer_positive_rate` | 0.197345 | 0.571805 | higher_good | 0.833333 | 0.807896 | 0.21494 |
| all | all | all | `row_rpf_rejection_chop_max_abs` | 0.193065 | 0.565213 | lower_good | 0.967175 | 0.980108 | -0.250558 |
| side | down | all | `row_rpf_rejection_chop_max_abs` | 0.193065 | 0.565213 | lower_good | 0.967175 | 0.980108 | -0.250558 |
| candidate | down | down_rocket_16_diag_v1 | `row_rpf_rejection_chop_max_abs` | 0.193065 | 0.565213 | lower_good | 0.967175 | 0.980108 | -0.250558 |
| all | all | all | `row_rpf_structural_room_mean_abs` | 0.176094 | 0.561133 | higher_good | 0.361532 | 0.351859 | 0.215311 |
| side | down | all | `row_rpf_structural_room_mean_abs` | 0.176094 | 0.561133 | higher_good | 0.361532 | 0.351859 | 0.215311 |
| candidate | down | down_rocket_16_diag_v1 | `row_rpf_structural_room_mean_abs` | 0.176094 | 0.561133 | higher_good | 0.361532 | 0.351859 | 0.215311 |
| all | all | all | `row_rpf_spike_breakout_mean_abs` | 0.163641 | 0.557919 | higher_good | 0.186706 | 0.181067 | 0.191212 |
| side | down | all | `row_rpf_spike_breakout_mean_abs` | 0.163641 | 0.557919 | higher_good | 0.186706 | 0.181067 | 0.191212 |
| candidate | down | down_rocket_16_diag_v1 | `row_rpf_spike_breakout_mean_abs` | 0.163641 | 0.557919 | higher_good | 0.186706 | 0.181067 | 0.191212 |
| all | all | all | `row_rpf_acceptance_persistence_mean` | 0.162198 | 0.557332 | higher_good | 0.294304 | 0.275184 | 0.19014 |
| side | down | all | `row_rpf_acceptance_persistence_mean` | 0.162198 | 0.557332 | higher_good | 0.294304 | 0.275184 | 0.19014 |
| candidate | down | down_rocket_16_diag_v1 | `row_rpf_acceptance_persistence_mean` | 0.162198 | 0.557332 | higher_good | 0.294304 | 0.275184 | 0.19014 |
| all | all | all | `row_rpf_unsupervised_factor_layer_mean` | 0.162133 | 0.559124 | higher_good | 0.180951 | 0.172126 | 0.175537 |
| side | down | all | `row_rpf_unsupervised_factor_layer_mean` | 0.162133 | 0.559124 | higher_good | 0.180951 | 0.172126 | 0.175537 |
| candidate | down | down_rocket_16_diag_v1 | `row_rpf_unsupervised_factor_layer_mean` | 0.162133 | 0.559124 | higher_good | 0.180951 | 0.172126 | 0.175537 |

## Interpretation Rules

- This is row-level separator evidence only.
- `row_safe_context_features.parquet` excludes target/outcome columns.
- TP/FP labels are post-hoc diagnostics and must not be used as current-window inputs.
