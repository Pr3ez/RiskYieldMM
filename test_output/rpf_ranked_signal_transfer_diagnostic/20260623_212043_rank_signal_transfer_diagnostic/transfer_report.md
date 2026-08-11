# RPF Ranked Signal Transfer Diagnostic

## Purpose

Compare completed router blocks and separate prediction-safe context from post-hoc prediction outcomes.

## Summary

- transfer rows: `720`
- source blocks: `latest, older`

## Candidate Aggregates

| Source | Side | Candidate | Windows | Active | Good | Bad | Signals | TP | FP | Precision | Base Rate | Lift |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| latest | down | down_rocket_16_diag_v1 | 120 | 62 | 19 | 35 | 172 | 68 | 104 | 0.395349 | 0.333333 | 1.18605 |
| latest | up | up_none_v1 | 120 | 38 | 7 | 20 | 114 | 54 | 60 | 0.473684 | 0.429896 | 1.10186 |
| latest | up | up_rocket_64_v1 | 120 | 82 | 16 | 42 | 156 | 69 | 87 | 0.442308 | 0.429896 | 1.02887 |
| older | down | down_rocket_16_diag_v1 | 120 | 35 | 9 | 18 | 100 | 49 | 51 | 0.49 | 0.417257 | 1.17434 |
| older | up | up_none_v1 | 120 | 8 | 3 | 4 | 22 | 10 | 12 | 0.454545 | 0.362222 | 1.25488 |
| older | up | up_rocket_64_v1 | 120 | 33 | 9 | 20 | 58 | 23 | 35 | 0.396552 | 0.362222 | 1.09477 |

## Interpretation Rules

- `safe_context_features.parquet` excludes current prediction outcomes and can feed future meta-router research.
- `candidate_transfer_table.parquet` includes post-hoc labels and must not be used as current-window input.
- `candidate_good` means active, precision lift >= configured threshold, and false-discovery rate <= configured threshold.
- `candidate_bad` means active with high false-discovery rate.
