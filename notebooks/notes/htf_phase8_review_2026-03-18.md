# HTF Phase 8 Review

Date: 2026-03-18

## Scope
Review the remaining legacy validation helpers and compatibility aliases in
`notebooks/htf_pythonscript.py` after the Phase 8 cleanup work.

Goal:
- identify real remaining risks
- separate actual structural problems from acceptable phase-1 legacy baggage
- define the next safe Phase 8 step without guessing

## Findings

### 1. Ownership labeling is still incomplete in the legacy island
Severity: Medium

Some legacy cells are now clearly marked `LEGACY`, but several earlier notebook
sections in the same legacy/debug island are still labeled like normal active
pipeline stages.

Examples:
- `CELL 2.5: ROBUST HTF COMBINED FILE GENERATION`
- `CELL 3: VALIDATE BATCH ALIGNMENT`
- `CELL 5: HTF FEATURE ENGINEERING`
- `CELL 5B: APPLY FAMILY METADATA TO BASE FEATURES + BUILD SHIFT4H FEATURES`
- `CELL 6: VALIDATE BATCH FEATURE FILES`
- `CELL 8B`, `CELL 9`, `CELL 9C`

This is not a correctness bug, but it still makes `htf_pythonscript.py` read as
two equal pipelines instead of:
- one supported production path
- one retained legacy/debug island

### 2. Legacy validation remains a large inline validation engine
Severity: Medium

`CELL 13` still owns a large local validation suite with its own helper stack:
- `_row`
- `_scan_parquet_relaxed`
- `_coerce_lazy_scan`
- `_label_metadata_lookup`
- `_scan_label_batches_normalized`
- `_scan_batch_counts`
- `_duplicate_ts_count`
- `_null_count`
- `_expected_batch_ids`
- `_complete_batch_ids`
- `_period_expr`
- `_validate_*`

This is acceptable as retained legacy/debug scope, but it is still a real
reason the notebook reads like a second engine. Since supported production
validation is already centralized in the shared pipeline, the next cleanup
should focus on fencing this block more clearly, not extending it further.

### 3. Legacy cell-order coupling is still real
Severity: Medium

The legacy path still depends on notebook-style ambient globals and fallback
guards, for example:
- `if "BARS_PER_8H" not in globals()`
- `if "MIN_REMAINING_BARS_BY_TF" not in globals()`
- `if "compute_4class_labels" not in globals()`
- `if "compute_hybrid_distance_metrics" not in globals()`

These are not active supported-production risks anymore because normal script
execution bypasses the legacy cells. But they do mean wrapper removal and legacy
cleanup must stay explicit and local; broad deletion would be risky.

## Non-Findings
- I did not find a new correctness issue in the supported `CELL 14` production path from this review.
- I did not find evidence that the retained legacy wrappers are accidentally used by the supported production run.

## Recommended Next Step
Do a final ownership-label cleanup pass before any deletion:
- mark the remaining legacy cells and banners consistently as legacy/debug
- optionally add one short header comment before the legacy validation block
- do not remove the legacy validation helpers or compatibility aliases yet

That is the safest way to finish Phase 8 structural clarity without drifting
into risky behavior changes.
