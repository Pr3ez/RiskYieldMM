# Regression Target Rollout

## Purpose

Define how `distance_horizon_vol_v2` regression labels should be materialized
and validated beyond the first BTCUSDT `8h/B` benchmark.

## Current Status

The target materializer and validator support all Stage-1 roots through the
shared Stage-1 root layout registry. Local `distance_horizon_vol_v2` target
coverage is present for every core asset and root. ES `7d/C` has materially
shorter local coverage than the other session assets and must remain marked as a
coverage caveat before any cross-asset 7d/C promotion.

Current local coverage:

| Asset | `8h_b` | `8h_c` | `24h_b` | `24h_c` | `7d_b` | `7d_c` |
|---|---:|---:|---:|---:|---:|---:|
| BTCUSDT | 5856 | 5855 | 1952 | 1951 | 278 | 279 |
| ETHUSDT | 5637 | 5636 | 1879 | 1878 | 268 | 268 |
| EURUSD | 4129 | 4138 | 1381 | 1381 | 278 | 279 |
| USDJPY | 4129 | 4138 | 1381 | 1381 | 278 | 279 |
| GC | 4124 | 4133 | 1378 | 1378 | 278 | 279 |
| CL | 4124 | 4133 | 1378 | 1378 | 278 | 279 |
| ES | 4129 | 4138 | 1381 | 1381 | 278 | 199 |
| NQ | 4129 | 4138 | 1381 | 1381 | 278 | 279 |

Values are local batch counts in the generated regression target roots.

## Scope

Applies to the full core target matrix:

```text
8 assets x 6 roots x 6 regression target columns = 288 target series
```

Assets:

```text
BTCUSDT, ETHUSDT, EURUSD, USDJPY, GC, CL, ES, NQ
```

Root IDs:

```text
8h_b, 8h_c, 24h_b, 24h_c, 7d_b, 7d_c
```

Target columns:

```text
target_reg_distance_up_extreme_hvol_v2
target_reg_distance_up_mean_high_hvol_v2
target_reg_distance_down_mean_low_hvol_v2
target_reg_distance_down_extreme_hvol_v2
target_reg_direction_extreme_up_share_hvol_v2
target_reg_direction_mean_up_share_hvol_v2
```

## Source Of Truth

- Materializer: `scripts/analysis/materialize_stage1_regression_targets.py`
- Validator: `scripts/analysis/validate_stage1_regression_targets.py`
- Root layouts: `scripts/htf_backtest/catboost/stage1_multiasset_dataset.py`
- Feature contract: `data_contract.md`
- Feature rollout: `workflow.md`

## What This Does Not Decide

This document does not implement regression features, choose model
hyperparameters, or promote a target to production. It only defines target
artifact rollout and validation.

## Existing Root Mapping

The materializer uses the existing Stage-1 label root as row authority and the
opposite-family `15m_HTF_combined.parquet` as the future path scan source.

| Root | Source label root | Future window source |
|---|---|---|
| `8h/B` | `htf_4class_labels` | `htf_backtest_shift4h/15m_HTF_combined.parquet` |
| `8h/C` | `htf_4class_labels_shift4h` | `htf_backtest/15m_HTF_combined.parquet` |
| `24h/B` | `htf_4class_labels_24h` | `htf_backtest_24h_shift12h/15m_HTF_combined.parquet` |
| `24h/C` | `htf_4class_labels_24h_shift12h` | `htf_backtest_24h/15m_HTF_combined.parquet` |
| `7d/B` | `htf_4class_labels_7d` | `htf_backtest_7d_shift84h/15m_HTF_combined.parquet` |
| `7d/C` | `htf_4class_labels_7d_shift84h` | `htf_backtest_7d/15m_HTF_combined.parquet` |

Output label roots append the variant suffix to the source label root:

```text
data/htf_multiasset/{asset}/{layout_label_root}_reg_distance_horizon_vol_v2/1m/
```

## Rollout Order

Use one consistent materialization formula across all roots first, then
optimize features target-by-target.

1. Verify HTF inputs exist for every selected asset/root.
2. Materialize `distance_horizon_vol_v2` labels for all selected assets/roots.
3. Validate every generated root before model training.
4. Inspect sanity reports for invalid ratio, target range, zero-target rates,
   and horizon-volatility distribution.
5. Build regression features once the target matrix is complete.
6. Run target-specific feature selection inside walk-forward training for each
   target column.
7. Compare target families together so feature decisions do not help one path
   distance while damaging its opposite-direction counterpart.

This lets us optimize the feature families step by step across the whole matrix
instead of building a separate ad hoc workflow for each target.

## Commands

Materialize all core targets:

```bash
python scripts/analysis/materialize_stage1_regression_targets.py \
  --assets core \
  --roots 8h/B 8h/C 24h/B 24h/C 7d/B 7d/C \
  --variant distance_horizon_vol_v2 \
  --write-sanity-report
```

Validate all generated targets:

```bash
python scripts/analysis/validate_stage1_regression_targets.py \
  --assets core \
  --roots 8h/B 8h/C 24h/B 24h/C 7d/B 7d/C \
  --variant distance_horizon_vol_v2 \
  --write-report
```

If a full run is too heavy, use the same commands in staged blocks:

```bash
python scripts/analysis/materialize_stage1_regression_targets.py \
  --assets BTCUSDT,ETHUSDT \
  --roots 8h/B 8h/C 24h/B 24h/C 7d/B 7d/C \
  --variant distance_horizon_vol_v2 \
  --write-sanity-report
```

```bash
python scripts/analysis/materialize_stage1_regression_targets.py \
  --assets EURUSD,USDJPY,GC,CL,ES,NQ \
  --roots 8h/B 8h/C 24h/B 24h/C 7d/B 7d/C \
  --variant distance_horizon_vol_v2 \
  --write-sanity-report
```

## Acceptance Checks

Each generated asset/root must pass:

- duplicate `timestamp,batch_id` count is zero;
- valid rows are only in `is_label_half`;
- invalid rows have explicit reasons;
- normalized target equals raw distance divided by horizon volatility;
- raw distances independently recompute from the opposite-family 15m windows;
- future-window bar counts and extreme timestamps match the window source;
- no negative or nonfinite valid targets;
- zero targets are explained by raw distance equal to zero.

## Optimization Implication

After the full target matrix exists, feature work should be optimized in this
order:

1. shared causal feature formulas across all assets/roots;
2. per-target train-only feature selection;
3. per-target clipping and duplicate removal;
4. matrix-level comparison of six targets per asset/root;
5. ablation by feature family before promotion.

This preserves one clean feature workflow while still allowing each distance
target to select the features it actually needs.
