# HTF Unification Execution Checklist

Last updated: 2026-03-25

## Current Phase
- Unification implementation complete; deferred legacy-cleanup follow-up only

## Decision Notes
- Supported production HTF path is `CELL 14` / `run_multi_regime_htf_pipeline(...)`.
- Cells `1-13` in `notebooks/htf_pythonscript.py` remain legacy/debug/back-compat only in phase 1.
- Step 0 fetch remains a separate prerequisite and is not moved into the HTF production path.
- `5m` remains a legacy island in this unification pass.
- Shared compute authority is moving into modules under `scripts/feature_engineering/`.
- Shared control-plane metadata contract is preserved during phase 2. No fingerprint-shape migration is bundled into the same extraction.
- Phase-1 compatibility contracts verified from active code:
  - preserve `bar_in_batch_norm`
  - preserve `period_8h_start`
  - preserve the current family/regime metadata set
  - preserve base roots `htf_backtest`, `htf_features`, `htf_4class_labels`, `htf_optimized`, `htf_with_helpers`
  - preserve `*_shift4h` paths in phase 1
  - treat `shift4h` naming as compatibility only, not future architecture guidance
- Shared validation is now the supported production pass/fail gate for `CELL 14` scope.
- Notebook validation cells remain available, but they are legacy/debug only and not part of the supported production acceptance path.
- Normal script execution of `notebooks/htf_pythonscript.py` now short-circuits directly into the supported shared `CELL 14` runner. Replaying legacy cells `1-13` requires `HTF_RUN_LEGACY_NOTEBOOK_CELLS=1`.
- Fresh two-pass resume verification on a bounded `8h/24h/7d` fixture passed after the execution-flow simplification:
  - first pass built `36` stage outputs with `396` validation checks and `0` failures
  - second pass reported `36` stage outputs as `current` with `396` validation checks and `0` failures
- Phase 8 simplification audit confirmed the remaining large body of `htf_pythonscript.py` is legacy/debug scope rather than active supported production scope.
- Phase-1 compatibility wrappers in `htf_pythonscript.py` are still intentional where they preserve legacy-relative fingerprint formatting or notebook-local logging conventions.
- Wrapper review verdict:
  - artifact/control wrappers stay for phase-1 compatibility
  - kernel-name wrappers are temporary pass-through names tied to legacy notebook cell-order behavior
  - broad wrapper deletion is not yet justified
- Remaining ambiguous legacy cell headers were normalized so Cells `2.5`, `3`, `5`,
  `5B`, `8B`, `9`, and `9C` now explicitly read as `LEGACY`.
- Phase 8 completion reassessment concluded:
  - `htf_pythonscript.py` is no longer a second compute engine for the supported
    production path
  - the retained legacy body is clearly fenced as legacy/debug scope
  - moving to Phase 9 is now structurally safe
  - the Phase 8 closure pass was structure-only and did not rewrite production
    HTF artifacts from the earlier long run
- Phase 9 preflight ambiguity resolved:
  - the production pipeline already treats shifted `C` feature trees as dirty
    once base `B` feature trees are rebuilt
  - the mismatch was in the read-only preflight model, not the pipeline
  - shifted `C` feature trees for `8h`, `24h`, and `7d` should be treated as
    `full_recompute` for both `1m` and `15m` during richer-schema promotion
  - this resolution was read-only and did not rewrite production HTF artifacts
- A full pre-Phase-9 backup snapshot now exists for the completed production
  HTF artifact trees, so the earlier long-run outputs can be compared against
  the refreshed workflow and recovered if needed.
- Phase 9 execution has started through the supported shared path only:
  - `HTF_RUN_LEGACY_NOTEBOOK_CELLS=0`
  - shared `CELL 14` runner only
  - `rebuild_existing=False`
  - build/validate regimes: `8h`, `24h`, `7d`
  - run id: `htf_pythonscript_20260318_163749_pid139025`
- Phase 9 run result:
  - the controlled production refresh completed combined/features/optimization/helpers
    through the supported shared path
  - the initial validation blocker was weekly `1m` label prefix coverage for
    `7d/B` and `7d/C`
  - refreshed and backup weekly label trees both start at `batch_0002`, while the
    old validator compared them against combined batch ids `1..271`
  - the blocker was resolved by reusing the label-builder eligibility rule inside
    shared validation via `_eligible_label_batches_from_counts(...)`
  - post-fix validation now passes with:
    - `7d`: `158` checks, `0` failures
    - all regimes: `474` checks, `0` failures
- A broader pipeline sweep was intentionally stopped after it began current-state
  incremental work; final acceptance evidence is based on direct read-only
  `_validate_regime(...)` reruns, not that sweep.
- Final sign-off audit confirmed:
  - normal script execution exits into the shared `CELL 14` runner before the
    retained legacy/debug notebook body is reached
  - the remaining notebook-local wrappers are legacy-only compatibility shims,
    not shared-scope production duplication
  - wrapper removal is deferred legacy cleanup and does not block unification
    sign-off

## Validation Evidence
- `TODO-02` parity evidence from earlier investigation:
  - `test_output/todo02_kernel_parity_summary.json`
  - `test_output/todo02_kernel_realdata_check.json`
- `TODO-03` control-plane evidence from earlier investigation:
  - `test_output/todo03_control_plane_summary.json`
- Extraction validation from this execution pass:
  - `python -m py_compile notebooks/htf_pythonscript.py scripts/feature_engineering/htf_multiregime_pipeline.py scripts/feature_engineering/htf_artifact_utils.py scripts/feature_engineering/htf_kernels.py scripts/feature_engineering/htf_shared_config.py`
  - `ml_env` import smoke for `compute_4class_labels` and `_validate_regime`
  - shared validation smoke on `test_output/feature_expansion_smoke_data` with stage flags matched to available artifacts: `107` checks, `0` failures
- Compatibility trace evidence:
  - `notebooks/notes/htf_compatibility_contract_report_2026-03-18.md`
- Validation-centralization evidence:
  - `python -m py_compile notebooks/htf_pythonscript.py scripts/feature_engineering/htf_multiregime_pipeline.py`
  - shared validation smoke on `test_output/feature_expansion_smoke_data`: `409` checks, `0` failures with `run_optimization=False` and `run_helpers=False`
- Phase 8 execution-flow simplification evidence:
  - `python -m py_compile notebooks/htf_pythonscript.py`
  - `HTF_RUN_MULTI_REGIME_EXTENSION=0 /media/przem/linux_data/conda/envs/ml_env/bin/python notebooks/htf_pythonscript.py`
  - verified direct short-circuit into the shared runner without replaying legacy cells
- Resume verification evidence:
  - `test_output/htf_phase8_resume_check.json`
  - bounded two-pass fixture under `test_output/phase8_resume_fixture`
  - second pass result: `36` statuses `current`, `36` run modes `current`, `396` validation checks, `0` failures
- Phase 8 simplification audit:
  - `notebooks/notes/htf_phase8_simplification_audit_2026-03-18.md`
- Phase 8 wrapper review:
  - `notebooks/notes/htf_phase8_wrapper_review_2026-03-18.md`
- Phase 8 review findings:
  - `notebooks/notes/htf_phase8_review_2026-03-18.md`
- Phase 8 completion reassessment:
  - `notebooks/notes/htf_phase8_completion_reassessment_2026-03-18.md`
- Phase 9 preflight resolution:
  - `notebooks/notes/htf_phase9_preflight_resolution_2026-03-18.md`
  - `test_output/htf_phase9_feature_propagation_check.json`
- Pre-Phase-9 backup snapshot:
  - `notebooks/notes/htf_pre_phase9_backup_2026-03-18.md`
  - `backups/htf_production_snapshot_pre_phase9_20260318_131026/manifest.json`
  - `backups/htf_production_snapshot_pre_phase9_20260318_131026/rsync.log`
- Active Phase 9 execution:
  - log: `test_output/htf_run_logs/htf_pythonscript_20260318_163749_pid139025.log`
  - status: `test_output/htf_run_logs/htf_pythonscript_20260318_163749_pid139025_status.json`
- Phase 9 blocker evidence:
  - `notebooks/notes/htf_phase9_validation_blocker_2026-03-19.md`
  - `notebooks/notes/htf_phase9_validation_resolution_2026-03-24.md`
  - `test_output/htf_phase9_validation_failures_7d.json`
  - `test_output/htf_phase9_validation_failures_7d_after_fix.json`
  - `test_output/htf_phase9_validation_all_regimes_after_fix.json`
  - weekly label tree comparison:
    - refreshed `7d/B` labels: `2..271`
    - refreshed `7d/C` labels: `2..271`
    - backup `7d/B` labels: `2..271`
    - backup `7d/C` labels: `2..271`
- Final sign-off audit:
  - `notebooks/notes/htf_final_signoff_audit_2026-03-25.md`

## Blocked On
- No active blocker.
- Deferred follow-up only:
  - optional retirement of notebook-local compatibility wrappers if legacy
    replay support is later dropped

## Completed Changes
- Added canonical execution tracker for this implementation phase.
- Added shared artifact/control module:
  - `scripts/feature_engineering/htf_artifact_utils.py`
- Added canonical shared kernel module:
  - `scripts/feature_engineering/htf_kernels.py`
- Added shared production config defaults:
  - `scripts/feature_engineering/htf_shared_config.py`
- Wired notebook artifact/control helpers to shared implementations via compatibility wrappers.
- Wired shared pipeline artifact/control helpers to shared implementations via compatibility wrappers.
- Wired notebook duplicated kernels to shared canonical kernels via compatibility wrappers.
- Wired shared pipeline duplicated kernels to shared canonical kernels via compatibility wrappers.
- Moved `CELL 14` critical production config ownership to an explicit shared-config block.
- Added clearer runtime messaging that `CELL 14` is the supported production path and `5m` is legacy-only.
- Added repo-wide compatibility trace report:
  - `notebooks/notes/htf_compatibility_contract_report_2026-03-18.md`
- Extended shared validation to absorb the remaining production-relevant artifact integrity checks from the notebook:
  - combined required columns, duplicate/null safety, and family metadata alignment
  - feature batch coverage plus duplicate/null safety
  - label existence/coverage, metadata backfill, value-range, and entry-window checks
  - optimized/helper batch coverage plus duplicate/null safety
  - cross-family equivalence checks for `C` halves versus `B`
- Marked notebook validation cells explicitly as legacy/debug-only in runtime messaging.
- Extracted a reusable `run_supported_multi_regime_pipeline()` wrapper in `htf_pythonscript.py`.
- Changed normal script execution to skip legacy cells `1-13` and jump straight into the supported shared production path unless `HTF_RUN_LEGACY_NOTEBOOK_CELLS=1`.
- Added clearer ownership comments in `htf_pythonscript.py` to separate:
  - supported production orchestration
  - legacy/debug notebook replay
  - phase-1 compatibility shims
- Documented wrapper categories in `htf_pythonscript.py` and recorded the wrapper review outcome in:
  - `notebooks/notes/htf_phase8_wrapper_review_2026-03-18.md`
- Normalized legacy cell ownership labels in `htf_pythonscript.py` so Cells `7-13`
  are explicitly marked `LEGACY` in notebook headers and the Cell 13 runtime banner.
- Normalized the remaining ambiguous legacy cell ownership labels in `htf_pythonscript.py`
  for Cells `2.5`, `3`, `5`, `5B`, `8B`, `9`, and `9C`.
- Normalized Cell `6` ownership labeling so the retained legacy validation block
  now matches the rest of the legacy/debug notebook island.
- Added an explicit legacy/debug fence comment above the inline Cell 13
  validation suite and recorded the final Phase 8 reassessment in:
  - `notebooks/notes/htf_phase8_completion_reassessment_2026-03-18.md`
- Resolved the Phase 9 preflight ambiguity by correcting the read-only preflight
  propagation model for shifted `C` feature trees and recorded the resolution in:
  - `notebooks/notes/htf_phase9_preflight_resolution_2026-03-18.md`
  - `test_output/htf_phase9_feature_propagation_check.json`
- Created a verified pre-Phase-9 backup snapshot of the completed production
  HTF artifact trees:
  - `backups/htf_production_snapshot_pre_phase9_20260318_131026/`
  - verification recorded in `manifest.json`
  - summary recorded in `notebooks/notes/htf_pre_phase9_backup_2026-03-18.md`
- Resolved the weekly Phase 9 validation blocker by extracting the label-batch
  eligibility rule into shared validation and label building:
  - `scripts/feature_engineering/htf_multiregime_pipeline.py`
  - resolution note: `notebooks/notes/htf_phase9_validation_resolution_2026-03-24.md`
  - post-fix validator evidence:
    - `test_output/htf_phase9_validation_failures_7d_after_fix.json`
    - `test_output/htf_phase9_validation_all_regimes_after_fix.json`

## Phase Checklist

### Phase 0. Set up execution tracking
- [x] Create `htf_unification_execution_checklist.md`.
- [x] Copy into it:
  - [x] phase list
  - [x] done criteria
  - [x] anti-drift checklist
  - [x] quality gates
  - [x] open decisions
- [x] Add sections:
  - [x] `Current Phase`
  - [x] `Decision Notes`
  - [x] `Validation Evidence`
  - [x] `Blocked On`
  - [x] `Completed Changes`
- [x] Link the checklist from the active Linear issue and Notion row.

Done when:
- [x] There is one canonical live checklist for implementation.

### Phase 1. Freeze production authority
- [x] Update the implementation checklist with the fixed authority decision:
  - [x] supported production HTF path = `CELL 14` / shared engine
  - [x] cells `1-13` = legacy/debug/back-compat only
- [x] Implement notebook/runtime changes so this authority is explicit in code comments, stage banners, and default run flow.
- [x] Do not remove legacy cells yet.
- [x] Do not change `5m` behavior yet.

Done when:
- [x] There is no ambiguity in code or docs about the supported production path.

### Phase 2. Extract shared control-plane utilities
- [x] Extract and centralize:
  - [x] JSON/meta loading
  - [x] schema inspection
  - [x] missing-column detection
  - [x] artifact cleanup helpers
  - [x] rebuild-reason logic
  - [x] stage rebuild prep
  - [x] metadata payload building
- [x] Migrate notebook and shared engine to import the same utilities.
- [x] Keep fingerprint/meta contract migration out of this phase unless required for correctness.
- [x] Preserve current rebuild behavior exactly.

Done when:
- [x] Notebook and shared engine no longer own separate rebuild/control logic.

### Phase 3. Extract canonical compute kernels
- [x] Extract to shared kernels module(s):
  - [x] `_compute_past_distance_metrics`
  - [x] `compute_distance_metrics`
  - [x] `compute_hybrid_distance_metrics`
  - [x] `compute_4class_labels`
- [x] Switch notebook callers to imports.
- [x] Switch shared engine callers to imports.
- [x] Preserve output columns and semantics exactly.
- [x] Decide notebook-local compatibility wrapper status after fresh parity/acceptance verification:
  - keep them temporarily as legacy-only compatibility shims
  - treat removal as deferred, non-blocking legacy cleanup

Done when:
- [x] There is one production implementation of these kernels.

### Phase 4. Consolidate shared production config ownership
- [x] Create one explicit shared-path config block in `htf_pythonscript.py`.
- [x] Stop relying on legacy-cell globals for shared production behavior.
- [x] Move ownership of shared-production semantics out of legacy cells:
  - [x] artifact version
  - [x] threshold map
  - [x] distance window map
  - [x] breakout/risk/breakfree constants
- [x] Keep user-facing production knobs minimal:
  - [x] run enabled
  - [x] build regimes
  - [x] validate regimes
  - [x] force full rebuild
  - [x] smoke mode/window
  - [x] run optimization
  - [x] run helpers
  - [x] run validation
- [x] Leave legacy-only toggles clearly isolated.

Done when:
- [x] Shared production behavior can be understood from one config surface.

### Phase 5. Centralize production validation
- [x] Extend shared validation to include notebook-only production-relevant checks:
  - [x] feature artifact sanity
  - [x] optimized row-count parity
  - [x] helper row-count parity
  - [x] helper-column presence
- [x] Keep notebook-only validation for:
  - [x] raw `8h` alignment debug checks
  - [x] `5m`
  - [x] other legacy-only/debug checks
- [x] Make shared validation the only production pass/fail gate.

Done when:
- [x] Supported production HTF validation is fully centralized.

### Phase 6. Lock compatibility contracts
- [x] Preserve written artifact compatibility for:
  - [x] `period_8h_start`
  - [x] `bar_in_batch_norm`
  - [x] current family/meta columns required downstream
- [x] Preserve base legacy roots:
  - [x] `htf_backtest`
  - [x] `htf_features`
  - [x] `htf_4class_labels`
  - [x] `htf_optimized`
  - [x] `htf_with_helpers`
- [x] Preserve `*_shift4h` paths in phase 1.
- [x] Treat `shift4h` naming as compatibility only, not internal architecture guidance.

Done when:
- [x] External artifact contracts remain stable through refactor.

### Phase 7. Isolate legacy `5m`
- [x] Keep `5m` out of shared production scope.
- [x] Fence `5m` code in notebook/runtime as explicit legacy scope.
- [x] Avoid touching `5m` unless required to keep current consumers working.
- [x] Do not claim full HTF unification includes `5m`.

Done when:
- [x] `5m` is clearly isolated and cannot confuse shared production behavior.

### Phase 8. Simplify notebook into orchestrator
- [x] Remove notebook-owned production logic that is now shared from the default script execution path.
- [x] Keep notebook responsibilities limited to:
  - [x] orchestration
  - [x] logging
  - [x] heartbeat/status
  - [x] progress callback formatting
  - [x] shared-path config wrapper
  - [x] optional debug helpers
- [x] Keep legacy/debug sections clearly separated from the production path in normal script execution.

Done when:
- [x] `htf_pythonscript.py` is no longer a second compute engine.

### Phase 9. Controlled richer-feature schema promotion
- [x] Use shared production path only.
- [x] Keep fetch separate unless Step 0 is intentionally rerun first.
- [x] Run with resumable settings:
  - [x] `rebuild_existing=False`
  - [x] supported regimes enabled
  - [x] optimization/helpers/validation enabled
- [x] Expect:
  - [x] combined = current
  - [x] labels = current
  - [x] `1m`/`15m` features = rebuilt
  - [x] optimized = rebuilt
  - [x] helper cache/materialization = rebuilt
  - [x] `5m` untouched

Done when:
- [x] Production artifacts are on the richer schema without a full notebook replay.

## Anti-Drift Checklist
- [x] No change to feature math unless the phase explicitly requires it.
- [x] No change to label math or target semantics.
- [x] No change to helper math or helper-cache semantics.
- [x] No implicit Step 0 fetch added to HTF production flow.
- [x] No compatibility contract removed without downstream proof.
- [x] No `5m` behavior silently changed.
- [x] No production validation removed before shared validation absorbs it.
- [x] No fingerprint/meta contract migration mixed into kernel extraction unless unavoidable.
- [x] No deep performance optimization mixed into structural refactor.
- [x] Checklist, Linear, and Notion updated before phase closure.

## Professional Code-Structure Checklist
- [x] One production entrypoint
- [x] One production compute authority
- [x] One production validation authority
- [x] Clear separation of runtime/orchestration vs compute logic
- [x] Clear separation of supported production scope vs legacy/debug scope
- [x] Shared module boundaries are logical and narrow
- [x] No duplicated production kernels
- [x] No duplicated production control-plane utilities
- [x] Naming remains consistent and up to date with actual ownership
- [x] Comments explain compatibility and scope boundaries, not obsolete history

## Validation and Acceptance Checklist

### Before removing any old implementation
- [x] Synthetic parity check passes after extraction
- [x] Real-slice parity check passes after extraction
- [x] Resume behavior check passes after extraction
- [x] Validation output remains equivalent or intentionally improved

### Before calling a phase complete
- [x] Checklist updated
- [x] Decision notes updated
- [x] Validation evidence captured
- [x] Linear `DONE` comment posted for the phase task
- [x] Notion row updated

### Before final unification sign-off
- [x] `CELL 14` is the only supported production HTF path
- [x] Notebook no longer contains duplicate production logic for shared scope
- [x] Shared validation covers supported production artifacts
- [x] Compatibility contracts are preserved
- [x] Richer schema is promoted successfully
- [x] Reports/checklists reflect final reality

## Open Decisions
- Whether shared validation should absorb notebook feature/optimized/helper checks directly or via a small shared validation submodule.
- When to migrate fingerprint/meta contract shape, if at all, after the structural unification is stable.
