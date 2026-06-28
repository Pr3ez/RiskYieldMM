# RPF Ranked Signal Transfer Separator Report

## Scope

- diagnostic run: `test_output/rpf_ranked_signal_transfer_diagnostic/20260624_163148_rank_signal_transfer_diagnostic`
- analyzed rows: `377`
- separator rows: `869`

## Group Summary

| Scope | Side | Candidate | Tested Features | Top Feature | Score | Best AUC | Direction | Std Diff |
|---|---|---|---:|---|---:|---:|---|---:|
| all | all | all | 220 | `score_mean` | 0.58451 | 0.730216 | lower_good | -0.496314 |
| candidate | up | up_none_v1 | 216 | `score_mean` | 0.457839 | 0.667907 | lower_good | -0.488099 |
| candidate | up | up_rocket_64_v1 | 213 | `score_mean` | 0.784957 | 0.769848 | lower_good | -0.981042 |
| side | up | all | 220 | `score_mean` | 0.58451 | 0.730216 | lower_good | -0.496314 |

## Top 20 Separators

| Scope | Side | Candidate | Feature | Score | Best AUC | Direction | Good Mean | Bad Mean | Std Diff |
|---|---|---|---|---:|---:|---|---:|---:|---:|
| candidate | up | up_rocket_64_v1 | `score_mean` | 0.784957 | 0.769848 | lower_good | -0.000501199 | 0.000982059 | -0.981042 |
| all | all | all | `score_mean` | 0.58451 | 0.730216 | lower_good | 0.000212324 | 0.00249472 | -0.496314 |
| side | up | all | `score_mean` | 0.58451 | 0.730216 | lower_good | 0.000212324 | 0.00249472 | -0.496314 |
| candidate | up | up_none_v1 | `score_mean` | 0.457839 | 0.667907 | lower_good | 0.00232435 | 0.00587181 | -0.488099 |
| candidate | up | up_none_v1 | `prior_rpf_l20_cross_asset_context_std_abs` | 0.455971 | 0.660465 | higher_good | 0.0212344 | 0.0190586 | 0.540162 |
| candidate | up | up_none_v1 | `validation_batch_base_rate_std` | 0.417397 | 0.649302 | higher_good | 0.389999 | 0.337 | 0.47517 |
| candidate | up | up_none_v1 | `validation_batch_base_rate_max` | 0.39993 | 0.638837 | higher_good | 0.901167 | 0.78062 | 0.489023 |
| candidate | up | up_none_v1 | `past_20_batch_positive_rate_std` | 0.393837 | 0.639529 | higher_good | 0.377595 | 0.347944 | 0.459112 |
| candidate | up | up_none_v1 | `validation_batch_precision_lift_std` | 0.391491 | 0.665165 | higher_good | 2.438 | 1.7316 | 0.244643 |
| candidate | up | up_none_v1 | `validation_margin_positive_rate` | 0.383964 | 0.642093 | lower_good | 0.0992667 | 0.176056 | -0.399113 |
| candidate | up | up_none_v1 | `validation_batch_base_rate_range` | 0.368187 | 0.632093 | higher_good | 0.873833 | 0.77156 | 0.416004 |
| candidate | up | up_none_v1 | `current_validation_signal_rate` | 0.368004 | 0.626279 | higher_good | 0.00716667 | 0.00625969 | 0.461783 |
| candidate | up | up_none_v1 | `prior_rpf_l60_sequence_embedding_layer_std_abs` | 0.343684 | 0.61907 | higher_good | 0.0433551 | 0.0406843 | 0.422177 |
| candidate | up | up_none_v1 | `score_std` | 0.333603 | 0.64186 | higher_good | 0.00469133 | 0.00372742 | 0.199529 |
| candidate | up | up_none_v1 | `validation_batch_base_rate_mean` | 0.32799 | 0.617907 | higher_good | 0.407 | 0.346638 | 0.368706 |
| candidate | up | up_none_v1 | `current_validation_positive_rate` | 0.32706 | 0.617442 | higher_good | 0.407 | 0.346638 | 0.368706 |
| candidate | up | up_none_v1 | `prior_rpf_l60_regime_calendar_state_std_abs` | 0.322862 | 0.611628 | lower_good | 0.0215138 | 0.0219454 | -0.398424 |
| candidate | up | up_none_v1 | `prior_rpf_l60_interaction_confluence_mean_abs` | 0.322807 | 0.616744 | lower_good | 0.103 | 0.10337 | -0.357275 |
| candidate | up | up_none_v1 | `prior_rpf_l20_interaction_confluence_std_mean` | 0.321746 | 0.603721 | higher_good | 0.0218769 | 0.0203069 | 0.457216 |
| candidate | up | up_none_v1 | `prior_rpf_l20_spike_breakout_std_mean` | 0.312106 | 0.612558 | higher_good | 0.0220427 | 0.0209564 | 0.347961 |

## Interpretation

- This is separator evidence only; it does not prove a deployable meta-router.
- Features are from `safe_context_features.parquet`; current prediction labels are used only as post-hoc labels.
- A high score means the field separated `candidate_good` from `candidate_bad` on the compared blocks.
