---
name: cross-target-ensemble-audit
description: |
  Audit cross-target and cross-timeframe ensemble artifacts for alignment integrity (15/3/1 anchor rules), truth mapping consistency, and confusion accounting. Use when validating multitimeframe ensemble outputs before reporting. Do not use for model training.
---

# Cross Target Ensemble Audit

## Inputs
- `unit_prediction_rows_dedup` parquet/csv
- Optional `final_predictions_walkforward.parquet`

## Outputs
- `ensemble_audit.json`
- `confusions.parquet`

## Core checks
1. Per-candidate per-batch row counts (`1m=240`, `5m=48`, `15m=16`).
2. Per-anchor row counts (`1m=15`, `5m=3`, `15m=1`) using 15m floor.
3. Optional final confusion table if truth/pred columns are available.
