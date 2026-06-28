# RPF Ranked Signal Row Diagnostic

## Scope

- router runs: `2`
- signal rows: `169`
- TP rows: `75`
- FP rows: `94`

## Candidate Signal Summary

| Source | Side | Candidate | Signals | TP | FP | Precision |
|---|---|---|---:|---:|---:|---:|
| latest | down | down_rocket_16_diag_v1 | 69 | 26 | 43 | 0.376812 |
| middle | down | down_rocket_16_diag_v1 | 100 | 49 | 51 | 0.49 |

## Separator Summary

| Scope | Side | Candidate | Tested Features | Top Feature | Score | Best AUC | Direction | Std Diff |
|---|---|---|---:|---|---:|---:|---|---:|
| all | all | all | 52 | `rank_score` | 0.558944 | 0.68844 | higher_good | 0.72826 |
| candidate | down | down_rocket_16_diag_v1 | 52 | `rank_score` | 0.558944 | 0.68844 | higher_good | 0.72826 |
| side | down | all | 52 | `rank_score` | 0.558944 | 0.68844 | higher_good | 0.72826 |

## Top 40 Row Separators

| Scope | Side | Candidate | Feature | Score | Best AUC | Direction | TP Mean | FP Mean | Std Diff |
|---|---|---|---|---:|---:|---|---:|---:|---:|
| all | all | all | `rank_score` | 0.558944 | 0.68844 | higher_good | 0.0291311 | 0.0220604 | 0.72826 |
| side | down | all | `rank_score` | 0.558944 | 0.68844 | higher_good | 0.0291311 | 0.0220604 | 0.72826 |
| candidate | down | down_rocket_16_diag_v1 | `rank_score` | 0.558944 | 0.68844 | higher_good | 0.0291311 | 0.0220604 | 0.72826 |
| all | all | all | `threshold` | 0.558345 | 0.689078 | higher_good | 0.0288394 | 0.0217469 | 0.720755 |
| side | down | all | `threshold` | 0.558345 | 0.689078 | higher_good | 0.0288394 | 0.0217469 | 0.720755 |
| candidate | down | down_rocket_16_diag_v1 | `threshold` | 0.558345 | 0.689078 | higher_good | 0.0288394 | 0.0217469 | 0.720755 |
| all | all | all | `row_rpf_structural_room_mean_abs` | 0.420519 | 0.645816 | higher_good | 0.381829 | 0.358784 | 0.515551 |
| side | down | all | `row_rpf_structural_room_mean_abs` | 0.420519 | 0.645816 | higher_good | 0.381829 | 0.358784 | 0.515551 |
| candidate | down | down_rocket_16_diag_v1 | `row_rpf_structural_room_mean_abs` | 0.420519 | 0.645816 | higher_good | 0.381829 | 0.358784 | 0.515551 |
| all | all | all | `row_rpf_sequence_embedding_layer_max_abs` | 0.360489 | 0.626809 | lower_good | 0.802068 | 0.874847 | -0.427487 |
| side | down | all | `row_rpf_sequence_embedding_layer_max_abs` | 0.360489 | 0.626809 | lower_good | 0.802068 | 0.874847 | -0.427487 |
| candidate | down | down_rocket_16_diag_v1 | `row_rpf_sequence_embedding_layer_max_abs` | 0.360489 | 0.626809 | lower_good | 0.802068 | 0.874847 | -0.427487 |
| all | all | all | `row_rpf_cross_asset_context_positive_rate` | 0.350402 | 0.620496 | higher_good | 0.581667 | 0.54211 | 0.437638 |
| side | down | all | `row_rpf_cross_asset_context_positive_rate` | 0.350402 | 0.620496 | higher_good | 0.581667 | 0.54211 | 0.437638 |
| candidate | down | down_rocket_16_diag_v1 | `row_rpf_cross_asset_context_positive_rate` | 0.350402 | 0.620496 | higher_good | 0.581667 | 0.54211 | 0.437638 |
| all | all | all | `row_rpf_volatility_state_mean_abs` | 0.32945 | 0.613617 | higher_good | 0.483173 | 0.417887 | 0.408865 |
| side | down | all | `row_rpf_volatility_state_mean_abs` | 0.32945 | 0.613617 | higher_good | 0.483173 | 0.417887 | 0.408865 |
| candidate | down | down_rocket_16_diag_v1 | `row_rpf_volatility_state_mean_abs` | 0.32945 | 0.613617 | higher_good | 0.483173 | 0.417887 | 0.408865 |
| all | all | all | `row_rpf_cross_asset_context_mean` | 0.305682 | 0.603546 | higher_good | 0.260588 | 0.239996 | 0.39436 |
| side | down | all | `row_rpf_cross_asset_context_mean` | 0.305682 | 0.603546 | higher_good | 0.260588 | 0.239996 | 0.39436 |
| candidate | down | down_rocket_16_diag_v1 | `row_rpf_cross_asset_context_mean` | 0.305682 | 0.603546 | higher_good | 0.260588 | 0.239996 | 0.39436 |
| all | all | all | `row_rpf_spike_breakout_mean` | 0.288363 | 0.594184 | higher_good | 0.195135 | 0.179986 | 0.399978 |
| side | down | all | `row_rpf_spike_breakout_mean` | 0.288363 | 0.594184 | higher_good | 0.195135 | 0.179986 | 0.399978 |
| candidate | down | down_rocket_16_diag_v1 | `row_rpf_spike_breakout_mean` | 0.288363 | 0.594184 | higher_good | 0.195135 | 0.179986 | 0.399978 |
| all | all | all | `row_rpf_volatility_state_positive_rate` | 0.287093 | 0.60227 | higher_good | 0.771667 | 0.716755 | 0.330218 |
| side | down | all | `row_rpf_volatility_state_positive_rate` | 0.287093 | 0.60227 | higher_good | 0.771667 | 0.716755 | 0.330218 |
| candidate | down | down_rocket_16_diag_v1 | `row_rpf_volatility_state_positive_rate` | 0.287093 | 0.60227 | higher_good | 0.771667 | 0.716755 | 0.330218 |
| all | all | all | `row_rpf_liquidity_volume_pressure_mean_abs` | 0.276061 | 0.611773 | lower_good | 0.411134 | 0.44686 | -0.210058 |
| side | down | all | `row_rpf_liquidity_volume_pressure_mean_abs` | 0.276061 | 0.611773 | lower_good | 0.411134 | 0.44686 | -0.210058 |
| candidate | down | down_rocket_16_diag_v1 | `row_rpf_liquidity_volume_pressure_mean_abs` | 0.276061 | 0.611773 | lower_good | 0.411134 | 0.44686 | -0.210058 |
| all | all | all | `row_rpf_cross_asset_context_mean_abs` | 0.269857 | 0.592482 | lower_good | 0.350228 | 0.362083 | -0.339571 |
| side | down | all | `row_rpf_cross_asset_context_mean_abs` | 0.269857 | 0.592482 | lower_good | 0.350228 | 0.362083 | -0.339571 |
| candidate | down | down_rocket_16_diag_v1 | `row_rpf_cross_asset_context_mean_abs` | 0.269857 | 0.592482 | lower_good | 0.350228 | 0.362083 | -0.339571 |
| all | all | all | `row_rpf_structural_room_max_abs` | 0.262512 | 0.585957 | higher_good | 0.955823 | 0.921245 | 0.362388 |
| side | down | all | `row_rpf_structural_room_max_abs` | 0.262512 | 0.585957 | higher_good | 0.955823 | 0.921245 | 0.362388 |
| candidate | down | down_rocket_16_diag_v1 | `row_rpf_structural_room_max_abs` | 0.262512 | 0.585957 | higher_good | 0.955823 | 0.921245 | 0.362388 |
| all | all | all | `row_rpf_interaction_confluence_positive_rate` | 0.257664 | 0.589149 | higher_good | 0.599444 | 0.569592 | 0.317463 |
| side | down | all | `row_rpf_interaction_confluence_positive_rate` | 0.257664 | 0.589149 | higher_good | 0.599444 | 0.569592 | 0.317463 |
| candidate | down | down_rocket_16_diag_v1 | `row_rpf_interaction_confluence_positive_rate` | 0.257664 | 0.589149 | higher_good | 0.599444 | 0.569592 | 0.317463 |
| all | all | all | `row_rpf_temporal_memory_transforms_mean_abs` | 0.250956 | 0.581418 | lower_good | 0.204454 | 0.236568 | -0.352477 |

## Interpretation Rules

- This is row-level separator evidence only.
- `row_safe_context_features.parquet` excludes target/outcome columns.
- TP/FP labels are post-hoc diagnostics and must not be used as current-window inputs.
