# RPF Ranked Signal Context Diagnostic

## Purpose

Compare safe row-rule context against matured outcomes across completed router runs.

## Inputs

- `test_output/rpf_ranked_signal_router/20260628_001251_rank_signal_router_btcusdt_8h_b`
- `test_output/rpf_ranked_signal_router/20260628_013625_rank_signal_router_btcusdt_8h_b`
- `test_output/rpf_ranked_signal_router/20260628_025919_rank_signal_router_btcusdt_8h_b`

## Summary

- context rows: `6`
- outcome rows: `6`
- active blocks: `6`
- good blocks: `3`
- bad blocks: `2`
- signals: `82`
- precision: `0.536585`
- base rate: `0.379039`
- precision lift: `1.41565`

## Strongest Context Separators

| Type | Feature | Category | Good Mean/Rate | Bad Mean/Rate | Delta |
|---|---|---|---:|---:|---:|
| numeric | `pred_batch_start` | - | 5477 | 4657 | 820 |
| numeric | `pred_batch_end` | - | 5536 | 4716 | 820 |
| numeric | `window_end_offset_steps` | - | 160 | 720 | -560 |
| numeric | `reliability_signals` | - | 15.3333 | 48 | -32.6667 |
| numeric | `reliability_tp` | - | 11.6667 | 32 | -20.3333 |
| numeric | `reliability_fp` | - | 3.66667 | 16 | -12.3333 |
| numeric | `train_rows` | - | 76 | 88 | -12 |
| numeric | `train_accepted_rows` | - | 13.3333 | 18 | -4.66667 |
| numeric | `block_idx` | - | 12.3333 | 8 | 4.33333 |
| numeric | `train_tp` | - | 10 | 13 | -3 |
| numeric | `train_fp` | - | 3.33333 | 5 | -1.66667 |
| categorical | `feature` | row_rpf_rejection_chop_mean_abs | 0 | 1 | -1 |
| categorical | `feature_family` | rejection_chop | 0 | 1 | -1 |
| numeric | `rule_score` | - | 2.1568 | 1.41976 | 0.737038 |
| categorical | `source_block` | latest | 0.666667 | 0 | 0.666667 |
| categorical | `feature_family` | liquidity_volume_pressure | 0.666667 | 0 | 0.666667 |
| categorical | `source_block` | offset960 | 0 | 0.5 | -0.5 |
| numeric | `selection_score` | - | 2.1112 | 1.6481 | 0.463105 |
| numeric | `reliability_score` | - | 2.03203 | 1.57501 | 0.45702 |
| numeric | `train_lift` | - | 1.85142 | 1.51323 | 0.338195 |
| categorical | `feature` | rank_score | 0.333333 | 0 | 0.333333 |
| categorical | `feature` | row_rpf_liquidity_volume_pressure_mean | 0.333333 | 0 | 0.333333 |
| categorical | `feature` | row_rpf_liquidity_volume_pressure_positive_rate | 0.333333 | 0 | 0.333333 |
| categorical | `feature_family` | rank_score | 0.333333 | 0 | 0.333333 |
| categorical | `source_block` | offset480 | 0.333333 | 0.5 | -0.166667 |
| numeric | `reliability_precision` | - | 0.800595 | 0.666667 | 0.133929 |
| numeric | `reliability_false_discovery_rate` | - | 0.199405 | 0.333333 | -0.133929 |
| numeric | `reliability_precision_lcb` | - | 0.690417 | 0.595836 | 0.0945815 |
| numeric | `threshold` | - | 0.432494 | 0.350268 | 0.0822262 |
| numeric | `train_base_precision` | - | 0.412195 | 0.477273 | -0.0650782 |

## Leakage Rule

- `context_rows.parquet` excludes current TP/FP/precision/base-rate outcome columns.
- `specialist_block_outcomes.parquet` contains matured labels and must only be used after the block matures.
