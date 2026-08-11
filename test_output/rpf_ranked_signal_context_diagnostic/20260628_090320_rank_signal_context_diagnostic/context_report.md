# RPF Ranked Signal Context Diagnostic

## Purpose

Compare safe row-rule context against matured outcomes across completed router runs.

## Inputs

- `test_output/rpf_ranked_signal_router/20260628_045015_rank_signal_router_btcusdt_8h_b`
- `test_output/rpf_ranked_signal_router/20260628_061237_rank_signal_router_btcusdt_8h_b`
- `test_output/rpf_ranked_signal_router/20260628_073452_rank_signal_router_btcusdt_8h_b`

## Summary

- context rows: `4`
- outcome rows: `4`
- active blocks: `4`
- good blocks: `3`
- bad blocks: `0`
- signals: `44`
- precision: `0.681818`
- base rate: `0.37658`
- precision lift: `1.81055`

## Strongest Context Separators

| Type | Feature | Category | Good Mean/Rate | Bad Mean/Rate | Delta |
|---|---|---|---:|---:|---:|
| numeric | `raw_signal_context_available` | - | 1 | - | - |
| numeric | `selected_feature_count_mean` | - | 0 | - | - |
| numeric | `reliability_score` | - | 2.03203 | - | - |
| numeric | `reliability_false_discovery_rate` | - | 0.199405 | - | - |
| numeric | `reliability_precision_lcb` | - | 0.690417 | - | - |
| numeric | `reliability_precision` | - | 0.800595 | - | - |
| numeric | `reliability_fp` | - | 3.66667 | - | - |
| numeric | `reliability_tp` | - | 11.6667 | - | - |
| numeric | `reliability_signals` | - | 15.3333 | - | - |
| numeric | `reliability_history_folds` | - | 1 | - | - |
| numeric | `selection_score` | - | 2.1112 | - | - |
| numeric | `directional_lcb_score` | - | 0.791771 | - | - |
| numeric | `direction_agreement` | - | 1 | - | - |
| numeric | `feature_auc_abs` | - | 0.636984 | - | - |
| numeric | `feature_auc` | - | 0.636984 | - | - |
| numeric | `rule_score` | - | 2.1568 | - | - |
| numeric | `train_accepted_rate` | - | 0.182987 | - | - |
| numeric | `train_precision_lcb` | - | 0.61621 | - | - |
| numeric | `train_false_discovery_rate` | - | 0.250149 | - | - |
| numeric | `train_lift` | - | 1.85142 | - | - |
| numeric | `train_base_precision` | - | 0.412195 | - | - |
| numeric | `train_precision` | - | 0.749851 | - | - |
| numeric | `train_fp` | - | 3.33333 | - | - |
| numeric | `train_tp` | - | 10 | - | - |
| numeric | `train_accepted_rows` | - | 13.3333 | - | - |
| numeric | `train_rows` | - | 76 | - | - |
| numeric | `threshold` | - | 0.432494 | - | - |
| categorical | `direction` | higher_good | 1 | - | - |
| categorical | `feature_family` | rank_score | 0.333333 | - | - |
| categorical | `feature_family` | liquidity_volume_pressure | 0.666667 | - | - |

## Leakage Rule

- `context_rows.parquet` excludes current TP/FP/precision/base-rate outcome columns.
- `specialist_block_outcomes.parquet` contains matured labels and must only be used after the block matures.
