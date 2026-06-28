# RPF Ranked Signal Row Diagnostic

## Scope

- router runs: `3`
- signal rows: `369`
- TP rows: `170`
- FP rows: `199`

## Candidate Signal Summary

| Source | Side | Candidate | Signals | TP | FP | Precision |
|---|---|---|---:|---:|---:|---:|
| latest | down | down_rocket_16_diag_v1 | 69 | 26 | 43 | 0.376812 |
| middle | down | down_rocket_16_diag_v1 | 100 | 49 | 51 | 0.49 |
| offset240 | down | down_rocket_16_diag_v1 | 200 | 95 | 105 | 0.475 |

## Separator Summary

| Scope | Side | Candidate | Tested Features | Top Feature | Score | Best AUC | Direction | Std Diff |
|---|---|---|---:|---|---:|---:|---|---:|
| all | all | all | 53 | `threshold` | 0.394647 | 0.634555 | higher_good | 0.502149 |
| candidate | down | down_rocket_16_diag_v1 | 53 | `threshold` | 0.394647 | 0.634555 | higher_good | 0.502149 |
| side | down | all | 53 | `threshold` | 0.394647 | 0.634555 | higher_good | 0.502149 |

## Top 40 Row Separators

| Scope | Side | Candidate | Feature | Score | Best AUC | Direction | TP Mean | FP Mean | Std Diff |
|---|---|---|---|---:|---:|---|---:|---:|---:|
| all | all | all | `threshold` | 0.394647 | 0.634555 | higher_good | 0.0276554 | 0.0228942 | 0.502149 |
| side | down | all | `threshold` | 0.394647 | 0.634555 | higher_good | 0.0276554 | 0.0228942 | 0.502149 |
| candidate | down | down_rocket_16_diag_v1 | `threshold` | 0.394647 | 0.634555 | higher_good | 0.0276554 | 0.0228942 | 0.502149 |
| all | all | all | `rank_score` | 0.39178 | 0.63321 | higher_good | 0.0279083 | 0.0232298 | 0.50144 |
| side | down | all | `rank_score` | 0.39178 | 0.63321 | higher_good | 0.0279083 | 0.0232298 | 0.50144 |
| candidate | down | down_rocket_16_diag_v1 | `rank_score` | 0.39178 | 0.63321 | higher_good | 0.0279083 | 0.0232298 | 0.50144 |
| all | all | all | `row_rpf_sequence_embedding_layer_max_abs` | 0.320766 | 0.613021 | lower_good | 0.797057 | 0.862495 | -0.378896 |
| side | down | all | `row_rpf_sequence_embedding_layer_max_abs` | 0.320766 | 0.613021 | lower_good | 0.797057 | 0.862495 | -0.378896 |
| candidate | down | down_rocket_16_diag_v1 | `row_rpf_sequence_embedding_layer_max_abs` | 0.320766 | 0.613021 | lower_good | 0.797057 | 0.862495 | -0.378896 |
| all | all | all | `row_rpf_volatility_state_mean_abs` | 0.269213 | 0.591457 | higher_good | 0.486677 | 0.432245 | 0.345195 |
| side | down | all | `row_rpf_volatility_state_mean_abs` | 0.269213 | 0.591457 | higher_good | 0.486677 | 0.432245 | 0.345195 |
| candidate | down | down_rocket_16_diag_v1 | `row_rpf_volatility_state_mean_abs` | 0.269213 | 0.591457 | higher_good | 0.486677 | 0.432245 | 0.345195 |
| all | all | all | `row_rpf_cross_asset_context_positive_rate` | 0.255056 | 0.585782 | higher_good | 0.584804 | 0.557161 | 0.333969 |
| side | down | all | `row_rpf_cross_asset_context_positive_rate` | 0.255056 | 0.585782 | higher_good | 0.584804 | 0.557161 | 0.333969 |
| candidate | down | down_rocket_16_diag_v1 | `row_rpf_cross_asset_context_positive_rate` | 0.255056 | 0.585782 | higher_good | 0.584804 | 0.557161 | 0.333969 |
| all | all | all | `row_rpf_rejection_chop_max_abs` | 0.231556 | 0.574106 | lower_good | 0.97135 | 0.984445 | -0.333376 |
| side | down | all | `row_rpf_rejection_chop_max_abs` | 0.231556 | 0.574106 | lower_good | 0.97135 | 0.984445 | -0.333376 |
| candidate | down | down_rocket_16_diag_v1 | `row_rpf_rejection_chop_max_abs` | 0.231556 | 0.574106 | lower_good | 0.97135 | 0.984445 | -0.333376 |
| all | all | all | `row_rpf_spike_breakout_mean` | 0.186983 | 0.561839 | higher_good | 0.186093 | 0.17684 | 0.253224 |
| side | down | all | `row_rpf_spike_breakout_mean` | 0.186983 | 0.561839 | higher_good | 0.186093 | 0.17684 | 0.253224 |
| candidate | down | down_rocket_16_diag_v1 | `row_rpf_spike_breakout_mean` | 0.186983 | 0.561839 | higher_good | 0.186093 | 0.17684 | 0.253224 |
| all | all | all | `row_rpf_rejection_chop_positive_rate` | 0.186195 | 0.565386 | higher_good | 0.793873 | 0.776591 | 0.221696 |
| side | down | all | `row_rpf_rejection_chop_positive_rate` | 0.186195 | 0.565386 | higher_good | 0.793873 | 0.776591 | 0.221696 |
| candidate | down | down_rocket_16_diag_v1 | `row_rpf_rejection_chop_positive_rate` | 0.186195 | 0.565386 | higher_good | 0.793873 | 0.776591 | 0.221696 |
| all | all | all | `row_rpf_spike_breakout_positive_rate` | 0.183931 | 0.560937 | higher_good | 0.713235 | 0.691374 | 0.248228 |
| side | down | all | `row_rpf_spike_breakout_positive_rate` | 0.183931 | 0.560937 | higher_good | 0.713235 | 0.691374 | 0.248228 |
| candidate | down | down_rocket_16_diag_v1 | `row_rpf_spike_breakout_positive_rate` | 0.183931 | 0.560937 | higher_good | 0.713235 | 0.691374 | 0.248228 |
| all | all | all | `row_rpf_sequence_embedding_layer_mean_abs` | 0.176802 | 0.560124 | lower_good | 0.243135 | 0.253989 | -0.226216 |
| side | down | all | `row_rpf_sequence_embedding_layer_mean_abs` | 0.176802 | 0.560124 | lower_good | 0.243135 | 0.253989 | -0.226216 |
| candidate | down | down_rocket_16_diag_v1 | `row_rpf_sequence_embedding_layer_mean_abs` | 0.176802 | 0.560124 | lower_good | 0.243135 | 0.253989 | -0.226216 |
| all | all | all | `row_rpf_volatility_state_max_abs` | 0.174314 | 0.556104 | higher_good | 1.67017 | 1.35774 | 0.248425 |
| side | down | all | `row_rpf_volatility_state_max_abs` | 0.174314 | 0.556104 | higher_good | 1.67017 | 1.35774 | 0.248425 |
| candidate | down | down_rocket_16_diag_v1 | `row_rpf_volatility_state_max_abs` | 0.174314 | 0.556104 | higher_good | 1.67017 | 1.35774 | 0.248425 |
| all | all | all | `row_rpf_cross_asset_context_mean` | 0.171011 | 0.558557 | higher_good | 0.253707 | 0.242267 | 0.215584 |
| side | down | all | `row_rpf_cross_asset_context_mean` | 0.171011 | 0.558557 | higher_good | 0.253707 | 0.242267 | 0.215584 |
| candidate | down | down_rocket_16_diag_v1 | `row_rpf_cross_asset_context_mean` | 0.171011 | 0.558557 | higher_good | 0.253707 | 0.242267 | 0.215584 |
| all | all | all | `row_rpf_spike_breakout_mean_abs` | 0.148148 | 0.552646 | higher_good | 0.190317 | 0.185089 | 0.171426 |
| side | down | all | `row_rpf_spike_breakout_mean_abs` | 0.148148 | 0.552646 | higher_good | 0.190317 | 0.185089 | 0.171426 |
| candidate | down | down_rocket_16_diag_v1 | `row_rpf_spike_breakout_mean_abs` | 0.148148 | 0.552646 | higher_good | 0.190317 | 0.185089 | 0.171426 |
| all | all | all | `row_rpf_cross_asset_context_mean_abs` | 0.138338 | 0.549394 | higher_good | 0.369869 | 0.363959 | 0.1582 |

## Interpretation Rules

- This is row-level separator evidence only.
- `row_safe_context_features.parquet` excludes target/outcome columns.
- TP/FP labels are post-hoc diagnostics and must not be used as current-window inputs.
