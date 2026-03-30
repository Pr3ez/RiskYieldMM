# Phase 9 Validation Resolution

Date: 2026-03-24

## Summary

The Phase 9 production refresh itself was already materially complete. The only
blocking failure was shared validation for weekly `1m` label batch-prefix
coverage in `7d/B` and `7d/C`.

The root cause was validation drift:

- label building uses a label-eligible batch rule derived from combined `1m` and
  `15m` batch counts
- shared validation compared label ids against raw combined `1m` batch ids

For weekly regimes, that drift mattered because batch `0001` is partial in the
combined inputs and therefore not label-eligible.

## Fix

Added one shared helper in:

- `scripts/feature_engineering/htf_multiregime_pipeline.py`

New helper:

- `_eligible_label_batches_from_counts(...)`

It now drives both:

1. label building
2. shared validation label expected-id checks

This keeps validation aligned with the same eligibility rule the label builder
already uses, instead of duplicating a looser expectation from raw combined ids.

## Evidence

Weekly combined counts:

- `7d/B 1m` batch `1`: `4320` rows, full batch = `10080`
- `7d/B 15m` batch `1`: `288` rows, full batch = `672`
- `7d/C 1m` batch `1`: `9360` rows, full batch = `10080`
- `7d/C 15m` batch `1`: `624` rows, full batch = `672`

So weekly label trees correctly begin at `batch_0002`.

That is consistent across:

- refreshed Phase 9 artifacts
- pre-Phase-9 backup snapshot

Validation artifacts:

- pre-fix failures:
  - `test_output/htf_phase9_validation_failures_7d.json`
- post-fix `7d` validation:
  - `test_output/htf_phase9_validation_failures_7d_after_fix.json`
  - result: `158` checks, `0` failures
- post-fix all-regime validation:
  - `test_output/htf_phase9_validation_all_regimes_after_fix.json`
  - result: `474` checks, `0` failures

Code anchors:

- helper definition: `scripts/feature_engineering/htf_multiregime_pipeline.py:624`
- label build now uses the helper: `scripts/feature_engineering/htf_multiregime_pipeline.py:1783`
- shared validation now uses the helper: `scripts/feature_engineering/htf_multiregime_pipeline.py:2643`

## Operational Note

A broader pipeline sweep was started during verification, but it was stopped as
soon as it began current-state incremental work on live artifacts. Final
acceptance for this fix is based on direct read-only `_validate_regime(...)`
reruns, not that broader sweep.

Observed live-artifact writes from that aborted sweep were limited to:

- `data/htf_optimized/1m/optimized_target_4class_meta.json`
- `data/htf_with_helpers/1m/target_4class/_helpers_meta.json`
- `data/htf_with_helpers/1m/target_4class/batch_5670.parquet`

## Conclusion

Phase 9 is now validation-clean.

The richer-schema production promotion is accepted without another full HTF
production rerun.
