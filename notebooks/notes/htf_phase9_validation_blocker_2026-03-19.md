# Phase 9 Validation Blocker

Date: 2026-03-19
Run id: `htf_pythonscript_20260318_163749_pid139025`

## Summary

The controlled Phase 9 production refresh completed the supported shared-path
materialization stages, but the run did not finish cleanly. Final shared
validation failed on weekly `1m` label prefix coverage for both `7d/B` and
`7d/C`.

## What Completed

- combined: refreshed state remained `current`
- features: refreshed through the richer `1m`/`15m` schema update
- distance metrics: remained `current`
- labels: remained `current`
- optimization: completed
- helpers: completed
- validation dataframe build: completed (`rows=474`)

The mirrored run log ended at:
- `test_output/htf_run_logs/htf_pythonscript_20260318_163749_pid139025.log`

The status file ended at:
- `test_output/htf_run_logs/htf_pythonscript_20260318_163749_pid139025_status.json`

## Blocker

The run exited with final validation failure on:

1. `7d/B/1m/labels/batch_ids_cover_expected_prefix`
2. `7d/C/1m/labels/batch_ids_cover_expected_prefix`

Observed on-disk batch ids:

- `data/htf_backtest_7d/1m_HTF_combined.parquet`: `1..271`
- `data/htf_backtest_7d_shift84h/1m_HTF_combined.parquet`: `1..271`
- `data/htf_4class_labels_7d/1m`: `2..271`
- `data/htf_4class_labels_7d_shift84h/1m`: `2..271`

The same weekly label layout already existed in the pre-Phase-9 backup:

- `backups/htf_production_snapshot_pre_phase9_20260318_131026/data/htf_4class_labels_7d/1m`: `2..271`
- `backups/htf_production_snapshot_pre_phase9_20260318_131026/data/htf_4class_labels_7d_shift84h/1m`: `2..271`

So the current blocker is consistent with an expectation mismatch in validation,
not with newly missing weekly label artifacts created by Phase 9.

An isolated shared-validation rerun for `7d` reproduced exactly two failing rows
and saved them to:

- `test_output/htf_phase9_validation_failures_7d.json`

Observed failure rows:

1. `7d / B / 1m / labels / batch_ids_cover_expected_prefix`
2. `7d / C / 1m / labels / batch_ids_cover_expected_prefix`

## Relevant Code Evidence

Shared validation currently compares label ids against combined `1m` ids:

- `scripts/feature_engineering/htf_multiregime_pipeline.py:2629`
- `scripts/feature_engineering/htf_multiregime_pipeline.py:2630`
- `scripts/feature_engineering/htf_multiregime_pipeline.py:2631`

The label builder itself defines valid weekly label batches from the intersection
of valid `1m` and `15m` combined batches:

- `scripts/feature_engineering/htf_multiregime_pipeline.py:1764`
- `scripts/feature_engineering/htf_multiregime_pipeline.py:1772`

## Next Step

Do not rerun production yet.

First verify the intended weekly label-batch contract:

- whether batch `0001` is intentionally excluded for weekly labels
- whether validation should compare weekly labels against combined ids or against
  label-eligible batch ids

Only after that proof should the validator or label expectation be changed.
