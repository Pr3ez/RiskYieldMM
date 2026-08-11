# RPF Ranked Signal Transfer Diagnostic

## Purpose

Compare completed router blocks and separate prediction-safe context from post-hoc prediction outcomes.

## Summary

- transfer rows: `1440`
- source blocks: `extra_1, extra_2, latest, older`

## Candidate Aggregates

| Source | Side | Candidate | Windows | Active | Good | Bad | Signals | TP | FP | Precision | Base Rate | Lift |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| extra_1 | down | down_rocket_16_diag_v1 | 120 | 67 | 17 | 35 | 200 | 95 | 105 | 0.475 | 0.456076 | 1.04149 |
| extra_1 | up | up_none_v1 | 120 | 36 | 8 | 24 | 108 | 35 | 73 | 0.324074 | 0.312674 | 1.03646 |
| extra_1 | up | up_rocket_64_v1 | 120 | 101 | 21 | 65 | 197 | 63 | 134 | 0.319797 | 0.312674 | 1.02278 |
| extra_2 | down | down_rocket_16_diag_v1 | 120 | 71 | 19 | 36 | 208 | 103 | 105 | 0.495192 | 0.417257 | 1.18678 |
| extra_2 | up | up_none_v1 | 120 | 40 | 5 | 27 | 115 | 35 | 80 | 0.304348 | 0.362222 | 0.840224 |
| extra_2 | up | up_rocket_64_v1 | 120 | 74 | 19 | 41 | 145 | 59 | 86 | 0.406897 | 0.362222 | 1.12333 |
| latest | down | down_rocket_16_diag_v1 | 120 | 62 | 19 | 35 | 172 | 68 | 104 | 0.395349 | 0.333333 | 1.18605 |
| latest | up | up_none_v1 | 120 | 38 | 7 | 20 | 114 | 54 | 60 | 0.473684 | 0.429896 | 1.10186 |
| latest | up | up_rocket_64_v1 | 120 | 82 | 16 | 42 | 156 | 69 | 87 | 0.442308 | 0.429896 | 1.02887 |
| older | down | down_rocket_16_diag_v1 | 120 | 79 | 17 | 49 | 231 | 88 | 143 | 0.380952 | 0.397639 | 0.958036 |
| older | up | up_none_v1 | 120 | 29 | 5 | 15 | 87 | 41 | 46 | 0.471264 | 0.422882 | 1.11441 |
| older | up | up_rocket_64_v1 | 120 | 86 | 18 | 44 | 166 | 78 | 88 | 0.46988 | 0.422882 | 1.11114 |

## Interpretation Rules

- `safe_context_features.parquet` excludes current prediction outcomes and can feed future meta-router research.
- `candidate_transfer_table.parquet` includes post-hoc labels and must not be used as current-window input.
- `candidate_good` means active, precision lift >= configured threshold, and false-discovery rate <= configured threshold.
- `candidate_bad` means active with high false-discovery rate.
