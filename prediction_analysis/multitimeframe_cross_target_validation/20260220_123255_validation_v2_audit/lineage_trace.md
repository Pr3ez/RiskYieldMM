# Data Preparation Lineage Trace (Validated)

Input source run: `prediction_analysis/multitimeframe_ensemble_outputs/20260220_082046_backfill_fix`

1. Candidate universe loaded from `candidate_sets_by_unit.json`.
- units: 6 (expected 6)
- candidates per unit: 12 unique (validated for all units)

2. Row-level predictions loaded from `unit_prediction_rows_dedup.parquet`.
- filtered rows used by v2: 3648000
- expected per candidate/batch rows by timeframe: 1m=240, 5m=48, 15m=16
- grouped row checks: 36000 groups, bad groups: 0

3. Truth anchors built from 15m units.
- breakfree truth source: `15m/target_breakfree` (domain {0,1,2})
- 4class truth source: `15m/target_4class` (domain {0,1,2,3})
- invalid label rows: breakfree=0, 4class=0
- discovered batches: 500 (expected 500)
- anchor rows: 8000 (expected 8000); per-batch=16 validated

4. same_period_close alignment applied.
- row-position contract: 1m uses row 15, 5m row 3, 15m row 1 inside each 15m anchor
- aligned rows: 576000
- row-count mismatches: 0
- expected anchor-candidate rows: 576000
- missing anchor-candidate rows: 0 (must be 0)

5. Feature matrix construction.
- candidate count: 72 (expected 72)
- base features: 252 (expected 252)
- derived features: 216 (expected 216)
- total features: 468 (expected 468)

6. Runtime walk-forward validation status.
- phase1 integrity gate: pass
- phase2 lookback/fallback gate: pass
- phase3 full production gate: incomplete (not complete)

7. Guard outcomes from validated runtime phases.
- leakage guard (`history_max_batch < pred_batch`): True
- lookback guard (`effective <= history_available`): pass
- fallback usage observed and logged: {'fallback_rows': 1, 'fallback_rate': 0.1}
