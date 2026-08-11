# Distance Regression Walk-Forward Smoke

Date: 2026-05-28

This smoke validates wiring for the volatility-normalized distance regression
target layer. It is not a promotion result.

## Scope

```text
asset: BTCUSDT
root: 8h/B
context: core-ex-target
target: target_reg_distance_up_extreme_vol_v1
merged batch window: batch_id >= 5800, limit 40
walk-forward steps: 3
lookback batches: 20
validation batches: 5
model: CatBoostRegressor, CPU, 30 iterations, depth 4
```

The run reuses the Stage-1 merged feature/label layout and sparse
`stage1_batch_index.parquet`, but it does not use the four-class
classification runner.

## Command

```bash
/media/przem/linux_data/conda/envs/ml_env/bin/python \
  scripts/analysis/htf_stage1_regression_walkforward.py \
  --build-merged-dataset \
  --target-assets BTCUSDT \
  --context-assets core-ex-target \
  --roots 8h/B \
  --stage1-target-col target_reg_distance_up_extreme_vol_v1 \
  --merged-batch-min 5800 \
  --merged-batch-limit 40 \
  --n-steps 3 \
  --lookback-batches 20 \
  --val-batches 5 \
  --iterations 30 \
  --depth 4 \
  --learning-rate 0.05 \
  --task-type CPU
```

## Result

```text
completed steps: 3
held-out rows: 717
MAE: 4.3016
RMSE: 5.1354
median absolute error: 4.1542
R2: 0.1731
Pearson: 0.4376
Spearman: 0.5257
bias: -0.3760
target mean: 11.6715
prediction mean: 11.2955
target p95: 19.0567
prediction p95: 14.6923
```

Output artifacts:

```text
test_output/stage1_regression_walkforward/stage1_regression_btcusdt_8h_b_ctx_corexself_reg_distance_up_extreme_vol_v1_live/
```

## Interpretation

The positive Spearman/Pearson values are the first useful signal: the model is
ranking larger future upside-distance rows above smaller ones in this small
smoke. Absolute-error metrics are not yet stable because this run covers only
three prediction batches.

Next validation should run all four distance targets with more steps and compare
rank quality, calibration by prediction quantile, and whether upside/downside
distance predictions combine into a useful asymmetric risk/reward signal.

## Horizon-Volatility V2 Follow-Up

The `distance_vol_v1` smoke above remains historical. After the feature/target
quality audit, the corrected `distance_horizon_vol_v2` target was added so
multi-hour future path distances are divided by horizon-adjusted volatility:

```text
horizon_minutes = future_15m_bar_count * 15
horizon_vol_pct = tb_volatility_pct * sqrt(horizon_minutes)
target = raw_distance_pct / horizon_vol_pct
```

BTCUSDT `8h/B` v2 materialization and validation passed:

```text
docs/research/reg-distance-target-sanity-distance_horizon_vol_v2-8h-b-btcusdt-2026-05-28.md
docs/research/reg-distance-target-validation-distance_horizon_vol_v2-8h-b-btcusdt-2026-05-28.md
```

The v2 validation reports:

```text
rows: 2,810,755
valid rows: 1,405,427
bad normalization counters: 0
horizon metadata mismatch counters: 0
raw-distance recomputation violations: 0
```

The regression runner also gained a train-only target-specific feature policy:

```text
--feature-policy target_specific_v1
```

This policy drops raw OHLCV and leakage-name features, removes bad-quality and
near-duplicate columns, ranks survivors against the selected target using train
rows only, and applies train-derived clip bounds to validation/prediction rows.

Bounded wiring smokes completed for all four v2 targets:

```text
target_reg_distance_up_extreme_hvol_v2:      steps=2, rows=480, selected=120 features/step
target_reg_distance_up_mean_high_hvol_v2:    steps=1, rows=240, selected=80 features/step
target_reg_distance_down_mean_low_hvol_v2:   steps=1, rows=240, selected=80 features/step
target_reg_distance_down_extreme_hvol_v2:    steps=1, rows=240, selected=80 features/step
```

These are still wiring checks, not model-quality claims. The next meaningful
test is a longer chronological run for each v2 target with enough held-out
batches to compare MAE, RMSE, R2, Pearson, Spearman, bias, and target/prediction
quantiles.
