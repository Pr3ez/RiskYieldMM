# HTF Auxiliary Stage Validation Report 2026-03-30

## Scope
Validate the staged repaired raw auxiliary sources under
`test_output/fetchingByBit_aux_stage_20260330_182045` before any live swap.

Validated source families:
- `mark-price-*`
- `index-price-*`
- `premium-price-*`

Validated intervals:
- `1m`
- `5m`
- `15m`
- `1h`
- `4h`

## Evidence
- machine-readable summary:
  [htf_aux_stage_validation_20260330.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/htf_aux_stage_validation/htf_aux_stage_validation_20260330.json)
- staged source tree:
  [fetchingByBit_aux_stage_20260330_182045](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/fetchingByBit_aux_stage_20260330_182045)
- live backup before repair:
  [fetchingByBit_aux_sources_pre_gap_repair_20260330_182015](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/backups/fetchingByBit_aux_sources_pre_gap_repair_20260330_182015)

## Validation Checks
Each staged parquet was checked for:
- existence
- duplicate timestamps
- monotonic ordering
- gap events larger than the expected interval
- bad interval steps
- start/end range versus the current live file

## Result
All `15/15` staged files passed.

Overall metrics:
- staged files passing: `15/15`
- staged total gap events: `0`
- live total gap events: `10,433`
- staged total duplicates: `0`
- live total duplicates: `0`
- total staged row increase versus live: `149,406`

## Key Improvements
Examples:
- `mark 1m`
  - staged first timestamp: `2021-01-01 00:00:00+00:00`
  - live first timestamp: `2021-01-01 00:01:00+00:00`
  - staged gap events: `0`
  - live gap events: `2712`
- `premium 5m`
  - staged first timestamp: `2021-01-01 00:00:00+00:00`
  - live first timestamp: `2021-01-01 00:05:00+00:00`
  - staged gap events: `0`
  - live gap events: `539`
- `index 4h`
  - staged first timestamp: `2021-01-01 00:00:00+00:00`
  - live first timestamp: `2021-01-01 04:00:00+00:00`
  - staged gap events: `0`
  - live gap events: `9`

## Production Decision
Yes: the staged repaired auxiliary files are correct on the validated dimensions and
are suitable to replace the current live raw files for these source families and
intervals.

This decision applies to raw-source quality only.
It does **not** mean downstream HTF features/optimized/helpers are already fixed;
those still need a rebuild after the raw swap.

## Next Steps
1. swap the staged repaired auxiliary files into `fetchingByBit`
2. rerun downstream HTF features, optimized outputs, and helpers
3. re-audit remaining null-heavy feature families on the rebuilt HTF outputs
