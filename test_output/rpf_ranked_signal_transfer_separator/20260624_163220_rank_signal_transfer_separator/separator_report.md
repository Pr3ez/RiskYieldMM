# RPF Ranked Signal Transfer Separator Report

## Scope

- diagnostic run: `test_output/rpf_ranked_signal_transfer_diagnostic/20260624_163148_rank_signal_transfer_diagnostic`
- analyzed rows: `227`
- separator rows: `648`

## Group Summary

| Scope | Side | Candidate | Tested Features | Top Feature | Score | Best AUC | Direction | Std Diff |
|---|---|---|---:|---|---:|---:|---|---:|
| all | all | all | 216 | `prior_rpf_l20_regime_calendar_state_std_mean` | 0.297991 | 0.605018 | lower_good | -0.351822 |
| candidate | down | down_rocket_16_diag_v1 | 216 | `prior_rpf_l20_regime_calendar_state_std_mean` | 0.297991 | 0.605018 | lower_good | -0.351822 |
| side | down | all | 216 | `prior_rpf_l20_regime_calendar_state_std_mean` | 0.297991 | 0.605018 | lower_good | -0.351822 |

## Top 20 Separators

| Scope | Side | Candidate | Feature | Score | Best AUC | Direction | Good Mean | Bad Mean | Std Diff |
|---|---|---|---|---:|---:|---|---:|---:|---:|
| all | all | all | `prior_rpf_l20_regime_calendar_state_std_mean` | 0.297991 | 0.605018 | lower_good | 0.0510422 | 0.0524551 | -0.351822 |
| side | down | all | `prior_rpf_l20_regime_calendar_state_std_mean` | 0.297991 | 0.605018 | lower_good | 0.0510422 | 0.0524551 | -0.351822 |
| candidate | down | down_rocket_16_diag_v1 | `prior_rpf_l20_regime_calendar_state_std_mean` | 0.297991 | 0.605018 | lower_good | 0.0510422 | 0.0524551 | -0.351822 |
| all | all | all | `threshold` | 0.289581 | 0.599194 | higher_good | 0.025704 | 0.0223126 | 0.364775 |
| side | down | all | `threshold` | 0.289581 | 0.599194 | higher_good | 0.025704 | 0.0223126 | 0.364775 |
| candidate | down | down_rocket_16_diag_v1 | `threshold` | 0.289581 | 0.599194 | higher_good | 0.025704 | 0.0223126 | 0.364775 |
| all | all | all | `prior_rpf_l20_interaction_confluence_mean_abs` | 0.289536 | 0.601613 | higher_good | 0.103846 | 0.103062 | 0.345241 |
| side | down | all | `prior_rpf_l20_interaction_confluence_mean_abs` | 0.289536 | 0.601613 | higher_good | 0.103846 | 0.103062 | 0.345241 |
| candidate | down | down_rocket_16_diag_v1 | `prior_rpf_l20_interaction_confluence_mean_abs` | 0.289536 | 0.601613 | higher_good | 0.103846 | 0.103062 | 0.345241 |
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

## Interpretation

- This is separator evidence only; it does not prove a deployable meta-router.
- Features are from `safe_context_features.parquet`; current prediction labels are used only as post-hoc labels.
- A high score means the field separated `candidate_good` from `candidate_bad` on the compared blocks.
