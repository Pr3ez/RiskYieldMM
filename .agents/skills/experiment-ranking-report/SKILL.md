---
name: experiment-ranking-report
description: |
  Aggregate experiment run summaries, compute deterministic rankings using metric priorities and tie-breakers, and produce a recommendation report with artifact links. Use when selecting the best configuration across many runs. Do not use for generating new model predictions.
---

# Experiment Ranking Report

## Inputs
- Parent directory containing run folders
- Optional glob pattern for summary files
- Ranking objective (defaults: higher macro_f1, then lower cost)

## Outputs
- `ranking_table.parquet`
- `ranking_table.csv`
- `selection_report.md`

## Workflow
1. Discover run summaries.
2. Parse core metrics.
3. Rank deterministically with explicit tie-break order.
4. Emit report with recommended run and rationale.
