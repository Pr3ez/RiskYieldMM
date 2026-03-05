---
name: ts-rolling-eval
description: |
  Run leakage-safe rolling-origin (walk-forward) baseline evaluation for time series and output deterministic artifacts (metrics, report, fold schedule). Use when forecasting evaluation must be reproducible and temporally valid. Do not use for execution or live trading actions.
---

# TS Rolling Eval

## Inputs
- Input CSV/Parquet path
- `ts_col` and `y_col`
- Optional: `id_col`, horizon, min train size, step, seasonal length

## Outputs
- `metrics.json`
- `report.md`
- `folds.csv`

## Workflow
1. Sort by time.
2. Build rolling-origin folds with no overlap leakage.
3. Evaluate baselines: last value, drift, optional seasonal-naive.
4. Write deterministic artifacts.
