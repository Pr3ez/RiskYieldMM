# RPF Ranked Signal Transfer Diagnostic

## Purpose

Compare completed router blocks and separate prediction-safe context from post-hoc prediction outcomes.

## Summary

- transfer rows: `960`
- source blocks: `latest, older`

## Candidate Aggregates

| Source | Side | Candidate | Windows | Active | Good | Bad | Signals | TP | FP | Precision | Base Rate | Lift |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| latest | down | down_none_v1 | 120 | 18 | 4 | 13 | 50 | 15 | 35 | 0.3 | 0.333333 | 0.9 |
| latest | down | down_rocket_16_diag_v1 | 120 | 26 | 9 | 15 | 69 | 26 | 43 | 0.376812 | 0.333333 | 1.13043 |
| latest | up | up_none_v1 | 120 | 4 | 1 | 1 | 12 | 9 | 3 | 0.75 | 0.429896 | 1.74461 |
| latest | up | up_rocket_64_v1 | 120 | 25 | 8 | 12 | 40 | 20 | 20 | 0.5 | 0.429896 | 1.16307 |
| older | down | down_none_v1 | 120 | 8 | 4 | 3 | 23 | 13 | 10 | 0.565217 | 0.417257 | 1.3546 |
| older | down | down_rocket_16_diag_v1 | 120 | 35 | 9 | 18 | 100 | 49 | 51 | 0.49 | 0.417257 | 1.17434 |
| older | up | up_none_v1 | 120 | 8 | 3 | 4 | 22 | 10 | 12 | 0.454545 | 0.362222 | 1.25488 |
| older | up | up_rocket_64_v1 | 120 | 33 | 9 | 20 | 58 | 23 | 35 | 0.396552 | 0.362222 | 1.09477 |

## Interpretation Rules

- `safe_context_features.parquet` excludes current prediction outcomes and can feed future meta-router research.
- `candidate_transfer_table.parquet` includes post-hoc labels and must not be used as current-window input.
- `candidate_good` means active, precision lift >= configured threshold, and false-discovery rate <= configured threshold.
- `candidate_bad` means active with high false-discovery rate.
