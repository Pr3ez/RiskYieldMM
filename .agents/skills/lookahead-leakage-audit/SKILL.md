---
name: lookahead-leakage-audit
description: |
  Audit feature and label pipelines for lookahead bias and temporal leakage using strict split checks, suspicious feature-name heuristics, and optional per-row feature-time constraints. Use when validating training data integrity before modeling. Do not use as a replacement for model evaluation.
---

# Lookahead Leakage Audit

## Inputs
- Feature table path (CSV/Parquet)
- Timestamp column
- Optional split column (`train/val/test`)
- Optional per-row max feature timestamp column

## Outputs
- `leakage_audit.json`
- `leakage_findings.md`

## Checks
1. Split monotonicity and overlap.
2. Suspicious future-feature naming patterns.
3. Optional row-level `feature_time_max <= row_time` validation.
4. Severity classification: critical/high/medium.
