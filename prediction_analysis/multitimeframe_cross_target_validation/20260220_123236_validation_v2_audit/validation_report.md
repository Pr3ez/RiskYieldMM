# Validation Report: multitimeframe_cross_target_ensemble_search_v2.py

Generated: 2026-02-20T12:32:36.717140+00:00
Overall status: **fail**
Critical failures: logic_invariant_code_audit
Blockers: phase3_full_production_gate_not_completed

## Data Lineage Checks
- `candidate_universe`: pass
  - units=6 (expected 6)
- `upstream_row_contract`: pass
  - groups_checked=36000, bad_groups=0

## Runtime Phases
- `phase1_integrity_gate`: pass
  - path: `/media/przem/linux_data/RiskYieldMM (Copy)/prediction_analysis/multitimeframe_cross_target_outputs_v2/20260220_122212_validation_phase1`
  - summary_exists: True
  - integrity_exists: True
  - leakage_checks: {'history_max_batch_lt_pred_batch': True, 'bad_rows': 0, 'lookback_effective_le_history_available': True, 'lookback_bad_rows': 0}
  - fallback_usage: {'fallback_rows': 1, 'fallback_rate': 0.5}
  - artifact_missing_count: 0
- `phase2_lookback_fallback_gate`: pass
  - path: `/media/przem/linux_data/RiskYieldMM (Copy)/prediction_analysis/multitimeframe_cross_target_outputs_v2/20260220_122258_validation_phase2`
  - summary_exists: True
  - integrity_exists: True
  - leakage_checks: {'history_max_batch_lt_pred_batch': True, 'bad_rows': 0, 'lookback_effective_le_history_available': True, 'lookback_bad_rows': 0}
  - fallback_usage: {'fallback_rows': 1, 'fallback_rate': 0.1}
  - artifact_missing_count: 0
- `phase3_full_production_gate`: incomplete
  - path: `/media/przem/linux_data/RiskYieldMM (Copy)/prediction_analysis/multitimeframe_cross_target_outputs_v2/20260220_123004_validation_phase3_fullgate`
  - summary_exists: False
  - integrity_exists: False

## Logic Invariant Code Audit
- `same_period_close_alignment`: fail
- `strict_missing_pairs_anti_join`: pass
- `lookback_clipping_functions_present`: pass
- `leakage_guard_history_lt_pred`: pass
- `fallback_policy_present`: pass
- `optuna_history_only_split`: pass

## Trial Resilience
- hard_fail probe: pass
- note: hard_fail probe with invalid GPU device terminated immediately (non-zero), demonstrating fail-fast path; process ended with segfault exit in CatBoost/CUDA stack.

## Acceptance Criteria Status
- [x] All integrity checks pass with zero missing aligned rows
- [x] One-step smoke run passes with strict guards
- [ ] Full-run completes and writes complete artifact set
- [x] Leakage and lookback guards pass globally (validated phases)
- [x] Fallback usage reported and traceable
- [x] Documentation audit checklist exists
