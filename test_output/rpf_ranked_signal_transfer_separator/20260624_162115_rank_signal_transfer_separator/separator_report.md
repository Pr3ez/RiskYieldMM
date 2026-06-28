# RPF Ranked Signal Transfer Separator Report

## Scope

- diagnostic run: `test_output/rpf_ranked_signal_transfer_diagnostic/20260624_162103_rank_signal_transfer_diagnostic`
- analyzed rows: `227`
- separator rows: `288`

## Group Summary

| Scope | Side | Candidate | Tested Features | Top Feature | Score | Best AUC | Direction | Std Diff |
|---|---|---|---:|---|---:|---:|---|---:|
| all | all | all | 96 | `threshold` | 0.289581 | 0.599194 | higher_good | 0.364775 |
| candidate | down | down_rocket_16_diag_v1 | 96 | `threshold` | 0.289581 | 0.599194 | higher_good | 0.364775 |
| side | down | all | 96 | `threshold` | 0.289581 | 0.599194 | higher_good | 0.364775 |

## Top 50 Separators

| Scope | Side | Candidate | Feature | Score | Best AUC | Direction | Good Mean | Bad Mean | Std Diff |
|---|---|---|---|---:|---:|---|---:|---:|---:|
| all | all | all | `threshold` | 0.289581 | 0.599194 | higher_good | 0.025704 | 0.0223126 | 0.364775 |
| side | down | all | `threshold` | 0.289581 | 0.599194 | higher_good | 0.025704 | 0.0223126 | 0.364775 |
| candidate | down | down_rocket_16_diag_v1 | `threshold` | 0.289581 | 0.599194 | higher_good | 0.025704 | 0.0223126 | 0.364775 |
| all | all | all | `validation_score_q95` | 0.289416 | 0.599104 | higher_good | 0.0257037 | 0.0223118 | 0.364832 |
| side | down | all | `validation_score_q95` | 0.289416 | 0.599104 | higher_good | 0.0257037 | 0.0223118 | 0.364832 |
| candidate | down | down_rocket_16_diag_v1 | `validation_score_q95` | 0.289416 | 0.599104 | higher_good | 0.0257037 | 0.0223118 | 0.364832 |
| all | all | all | `validation_score_q99` | 0.28496 | 0.598118 | higher_good | 0.0262645 | 0.0230817 | 0.354893 |
| side | down | all | `validation_score_q99` | 0.28496 | 0.598118 | higher_good | 0.0262645 | 0.0230817 | 0.354893 |
| candidate | down | down_rocket_16_diag_v1 | `validation_score_q99` | 0.28496 | 0.598118 | higher_good | 0.0262645 | 0.0230817 | 0.354893 |
| all | all | all | `validation_score_max` | 0.283402 | 0.596774 | higher_good | 0.02641 | 0.0232254 | 0.359415 |
| side | down | all | `validation_score_max` | 0.283402 | 0.596774 | higher_good | 0.02641 | 0.0232254 | 0.359415 |
| candidate | down | down_rocket_16_diag_v1 | `validation_score_max` | 0.283402 | 0.596774 | higher_good | 0.02641 | 0.0232254 | 0.359415 |
| all | all | all | `validation_score_q90` | 0.268556 | 0.591577 | higher_good | 0.0245907 | 0.0213042 | 0.341608 |
| side | down | all | `validation_score_q90` | 0.268556 | 0.591577 | higher_good | 0.0245907 | 0.0213042 | 0.341608 |
| candidate | down | down_rocket_16_diag_v1 | `validation_score_q90` | 0.268556 | 0.591577 | higher_good | 0.0245907 | 0.0213042 | 0.341608 |
| all | all | all | `reliability_selected_window_row_lift_lcb` | 0.255967 | 0.590669 | lower_good | 0.991733 | 1.02534 | -0.298515 |
| all | all | all | `recent_candidate_selected_window_row_lift_lcb` | 0.255967 | 0.590669 | lower_good | 0.991733 | 1.02534 | -0.298515 |
| side | down | all | `reliability_selected_window_row_lift_lcb` | 0.255967 | 0.590669 | lower_good | 0.991733 | 1.02534 | -0.298515 |
| side | down | all | `recent_candidate_selected_window_row_lift_lcb` | 0.255967 | 0.590669 | lower_good | 0.991733 | 1.02534 | -0.298515 |
| candidate | down | down_rocket_16_diag_v1 | `reliability_selected_window_row_lift_lcb` | 0.255967 | 0.590669 | lower_good | 0.991733 | 1.02534 | -0.298515 |
| candidate | down | down_rocket_16_diag_v1 | `recent_candidate_selected_window_row_lift_lcb` | 0.255967 | 0.590669 | lower_good | 0.991733 | 1.02534 | -0.298515 |
| all | all | all | `validation_batch_base_rate_mean` | 0.252968 | 0.589651 | lower_good | 0.376597 | 0.41343 | -0.294666 |
| side | down | all | `validation_batch_base_rate_mean` | 0.252968 | 0.589651 | lower_good | 0.376597 | 0.41343 | -0.294666 |
| candidate | down | down_rocket_16_diag_v1 | `validation_batch_base_rate_mean` | 0.252968 | 0.589651 | lower_good | 0.376597 | 0.41343 | -0.294666 |
| all | all | all | `current_validation_positive_rate` | 0.252878 | 0.589606 | lower_good | 0.376597 | 0.41343 | -0.294666 |
| side | down | all | `current_validation_positive_rate` | 0.252878 | 0.589606 | lower_good | 0.376597 | 0.41343 | -0.294666 |
| candidate | down | down_rocket_16_diag_v1 | `current_validation_positive_rate` | 0.252878 | 0.589606 | lower_good | 0.376597 | 0.41343 | -0.294666 |
| all | all | all | `validation_margin_std` | 0.243292 | 0.582527 | higher_good | 0.0177522 | 0.0155358 | 0.312955 |
| side | down | all | `validation_margin_std` | 0.243292 | 0.582527 | higher_good | 0.0177522 | 0.0155358 | 0.312955 |
| candidate | down | down_rocket_16_diag_v1 | `validation_margin_std` | 0.243292 | 0.582527 | higher_good | 0.0177522 | 0.0155358 | 0.312955 |
| all | all | all | `validation_score_std` | 0.243292 | 0.582527 | higher_good | 0.0177522 | 0.0155358 | 0.312955 |
| side | down | all | `validation_score_std` | 0.243292 | 0.582527 | higher_good | 0.0177522 | 0.0155358 | 0.312955 |
| candidate | down | down_rocket_16_diag_v1 | `validation_score_std` | 0.243292 | 0.582527 | higher_good | 0.0177522 | 0.0155358 | 0.312955 |
| all | all | all | `selected_feature_count` | 0.235126 | 0.577957 | higher_good | 39.3611 | 38.7806 | 0.316848 |
| all | all | all | `selected_feature_rows` | 0.235126 | 0.577957 | higher_good | 39.3611 | 38.7806 | 0.316848 |
| side | down | all | `selected_feature_count` | 0.235126 | 0.577957 | higher_good | 39.3611 | 38.7806 | 0.316848 |
| side | down | all | `selected_feature_rows` | 0.235126 | 0.577957 | higher_good | 39.3611 | 38.7806 | 0.316848 |
| candidate | down | down_rocket_16_diag_v1 | `selected_feature_count` | 0.235126 | 0.577957 | higher_good | 39.3611 | 38.7806 | 0.316848 |
| candidate | down | down_rocket_16_diag_v1 | `selected_feature_rows` | 0.235126 | 0.577957 | higher_good | 39.3611 | 38.7806 | 0.316848 |
| all | all | all | `validation_margin_mean` | 0.23157 | 0.581541 | lower_good | -0.0252472 | -0.022374 | -0.273951 |
| side | down | all | `validation_margin_mean` | 0.23157 | 0.581541 | lower_good | -0.0252472 | -0.022374 | -0.273951 |
| candidate | down | down_rocket_16_diag_v1 | `validation_margin_mean` | 0.23157 | 0.581541 | lower_good | -0.0252472 | -0.022374 | -0.273951 |
| all | all | all | `validation_margin_min` | 0.230092 | 0.578405 | lower_good | -0.0497438 | -0.0443433 | -0.293127 |
| side | down | all | `validation_margin_min` | 0.230092 | 0.578405 | lower_good | -0.0497438 | -0.0443433 | -0.293127 |
| candidate | down | down_rocket_16_diag_v1 | `validation_margin_min` | 0.230092 | 0.578405 | lower_good | -0.0497438 | -0.0443433 | -0.293127 |
| all | all | all | `score_mean` | 0.223905 | 0.576523 | lower_good | 0.00398388 | 0.00651674 | -0.283435 |
| side | down | all | `score_mean` | 0.223905 | 0.576523 | lower_good | 0.00398388 | 0.00651674 | -0.283435 |
| candidate | down | down_rocket_16_diag_v1 | `score_mean` | 0.223905 | 0.576523 | lower_good | 0.00398388 | 0.00651674 | -0.283435 |
| all | all | all | `validation_score_tail_spread_q95_q50` | 0.209969 | 0.571505 | higher_good | 0.0265989 | 0.0234622 | 0.267833 |
| all | all | all | `validation_margin_tail_spread_q95_q50` | 0.209969 | 0.571505 | higher_good | 0.0265989 | 0.0234622 | 0.267833 |

## Interpretation

- This is separator evidence only; it does not prove a deployable meta-router.
- Features are from `safe_context_features.parquet`; current prediction labels are used only as post-hoc labels.
- A high score means the field separated `candidate_good` from `candidate_bad` on the compared blocks.
