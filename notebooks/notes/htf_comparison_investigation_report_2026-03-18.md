# HTF Comparison Investigation Report - 2026-03-18

## Goal

This report compares the current HTF documentation set and source anchors to
capture the remaining things that still need investigation before planning full
unification.

Compared artifacts:

- [htf_pythonscript_runtime_report_2026-03-18.md](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/notes/htf_pythonscript_runtime_report_2026-03-18.md)
- [htf_multiregime_pipeline_runtime_report_2026-03-18.md](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/notes/htf_multiregime_pipeline_runtime_report_2026-03-18.md)
- [htf_unification_report_2026-03-18.md](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/notes/htf_unification_report_2026-03-18.md)
- [htf_workflow_audit_2026-03-18.md](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/notes/htf_workflow_audit_2026-03-18.md)
- [htf_pythonscript.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py)
- [htf_multiregime_pipeline.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py)

## High-Confidence Aligned Facts

These points are consistently supported by the reports and the source code.

- The system still has **two execution layers**:
  - legacy notebook cells `1-13` in [htf_pythonscript.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L41)
  - shared production engine in [run_multi_regime_htf_pipeline()](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L2787)
- The shared multi-regime engine is the current source of truth for:
  - `8h`
  - `24h`
  - `7d`
  - families `B` and `C`
- Some major lower-level modules are already shared correctly:
  - [compute_htf_features.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/compute_htf_features.py)
  - [optimize_htf_features.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/optimize_htf_features.py)
  - [htf_helper_cache.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_helper_cache.py)
- Fetching is still outside both HTF execution paths. The Step 0 fetch gate lives in:
  - [data_fetching.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/workflow/data_fetching.py#L40)
  - [main_wf.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/main_wf.py#L139)
  - [Fetch_data.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/Fetch_data.py#L64)
- The notebook still contains legacy-only `5m` code, while the shared engine is `1m`/`15m` only:
  - [htf_pythonscript.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L321)
  - [htf_multiregime_pipeline.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L82)

## Investigation Items

## 1. Execution authority is still ambiguous

Evidence:

- The notebook says `CELL 14` is authoritative in
  [htf_pythonscript.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L6439)
- But when the script is run end to end, cells `1-13` still execute first, as
  documented in the runtime report and visible in the file structure

Why it matters:

- the same `8h` production roots can be touched by both the legacy path and the
  shared path in one run
- that increases runtime, complicates debugging, and makes “which code produced
  this artifact?” harder to answer

Need to investigate:

- what the exact supported production run recipe should be
- whether legacy cells should be runnable only manually/debug-only
- whether end-to-end script execution should skip cells `1-13` by default

## 2. Duplicated compute kernels are still a real drift risk

Evidence:

- Shared engine owns:
  - [compute_distance_metrics()](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L355)
  - [compute_hybrid_distance_metrics()](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L414)
  - [_compute_past_distance_metrics()](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L476)
  - [compute_4class_labels()](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L507)
- Notebook still owns parallel versions:
  - [_compute_past_distance_metrics()](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L1602)
  - [compute_distance_metrics()](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L2627)
  - [compute_4class_labels()](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L3210)
  - [compute_hybrid_distance_metrics()](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L4007)

Why it matters:

- this is the highest-risk drift area because these functions define the actual
  feature/label math, not just orchestration

Need to investigate:

- whether the notebook and shared versions are still byte-for-byte equivalent in
  logic
- whether one side has silent bug fixes not mirrored to the other
- which exact kernel extraction order is safest

## 3. Control-plane duplication is still broader than just kernels

Evidence:

- Notebook artifact utility layer:
  - [fingerprint_paths()](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L417)
  - [artifact_rebuild_reasons()](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L487)
  - [artifact_meta_payload()](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L516)
  - [prepare_stage_rebuild()](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L540)
- Shared equivalents:
  - [_fingerprint_paths()](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L593)
  - [_artifact_rebuild_reasons()](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L673)
  - [_artifact_meta_payload()](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L700)
  - [_prepare_stage_rebuild()](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L724)

Why it matters:

- even if kernels are unified, rebuild behavior can still diverge and produce
  inconsistent incremental behavior

Need to investigate:

- whether notebook and shared rebuild reasons still match semantically
- whether metadata payloads are structurally compatible enough to merge
- whether a shared artifact-utility module can be introduced without breaking
  current metadata consumers

## 4. Legacy `5m` is still an unresolved scope boundary

Evidence:

- Notebook still carries `5m` config and helper/feature settings in several
  places, for example:
  - [htf_pythonscript.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L656)
  - [htf_pythonscript.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L1566)
  - [htf_pythonscript.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L5288)
- Shared engine excludes `5m` entirely:
  - [htf_multiregime_pipeline.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L82)

Why it matters:

- unification cannot be clean until `5m` is explicitly decided:
  - remove
  - archive
  - or port

Need to investigate:

- whether anything still depends on `5m` artifacts
- whether `5m` should remain notebook-only or be formally retired

## 5. Fetch orchestration is still disconnected from HTF production runs

Evidence:

- fetch gate exists only in workflow/fetch notebooks and workflow module:
  - [run_step0_fetch_and_aggregate()](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/workflow/data_fetching.py#L40)
- `htf_pythonscript.py` does not call it

Why it matters:

- “automatic check data and compute what is missing” is not fully true until
  fetch freshness is part of the same production recipe

Need to investigate:

- whether `htf_pythonscript.py` should gain a Step 0 fetch gate
- or whether fetch should remain explicitly separate but documented as required

## 6. Runtime config defaults may still hide mixed-path behavior

Evidence:

- `CELL 14` defaults are embedded directly in the notebook:
  - [htf_pythonscript.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L6473)
- legacy cells also have their own toggles and defaults earlier in the notebook

Why it matters:

- the runtime behavior of the notebook depends on a mix of:
  - global notebook variables
  - cell-local redefinitions
  - shared config defaults

Need to investigate:

- whether all production-significant toggles can be consolidated into one config
  block
- whether later cell-local redefinitions can still affect earlier assumptions in
  surprising ways

## 7. Compatibility aliases and legacy path names need an explicit contract

Evidence:

- Shared engine preserves:
  - legacy root names through `BASE_SCOPE_NAMES` and `LEGACY_8H_SHIFT_NAMES`
  - `period_8h_start` for all regimes
  in [htf_multiregime_pipeline.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L92)
- Notebook legacy code still naturally assumes those same names

Why it matters:

- this is one of the reasons the shared engine can coexist with the notebook
- but it also locks unification to historical naming choices unless downstream
  consumers are audited

Need to investigate:

- which downstream consumers truly require `period_8h_start`
- whether compatibility aliases can remain while internal logic is simplified

## 8. Validation ownership is still split

Evidence:

- Notebook has legacy validation sections/cells
- shared engine has regime-wide validation in
  [_validate_regime()](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L2514)

Why it matters:

- if both validations stay live, they can disagree or create duplicate runtime
  cost
- if only one should remain, that needs to be explicit

Need to investigate:

- which notebook validation checks are not already subsumed by shared validation
- whether validation should be fully centralized in the shared engine

## 9. Feature-schema promotion still needs one controlled production refresh

Evidence:

- workflow audit confirms code is ready but production feature/optimized/helper
  trees are still on the old schema in
  [htf_workflow_audit_2026-03-18.md](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/notes/htf_workflow_audit_2026-03-18.md)

Why it matters:

- a clean unification plan should not assume production artifacts already match
  the newest code

Need to investigate:

- the safest minimal production rerun path:
  - features
  - optimization
  - helpers
- whether that refresh should happen before or after structural unification

## 10. Helper/runtime performance remains a secondary but real concern

Evidence:

- earlier runs showed helper generation is the longest stage
- shared helper logic is now delegated, but notebook still owns part of the
  outer staging around it

Why it matters:

- unification that preserves exactness but ignores runtime cost may still leave
  the production workflow operationally painful

Need to investigate:

- whether helper checkpointing/progress/resume needs a dedicated pass after
  unification
- whether runtime-critical monitoring belongs only in the notebook wrapper

## What Does Not Look Like a Current Investigation Priority

- Rewriting the feature engine itself
- Changing label semantics
- Changing helper semantics
- Adding new fetched data sources
- Changing optimizer math

Those areas already look structurally separated enough for the current
unification decision.

## Actionable TODO List

Use this section as the next working checklist.

### TODO-01: Verify production execution authority

Task:
Decide which path is officially allowed to produce production HTF artifacts:

- full notebook end-to-end
- shared `CELL 14` only
- notebook wrapper that skips legacy compute cells by default

Verify:

- which stages in `htf_pythonscript.py` still write to the same `8h` roots as the
  shared engine
- whether a `CELL 14` only run produces the full intended production artifact set

Evidence to collect:

- one stage/write map for notebook cells `1-13`
- one stage/write map for shared `CELL 14`
- one recommended run recipe

Update report with:

- the single supported production entry procedure
- explicit statement about whether cells `1-13` are debug-only

Done when:

- there is no ambiguity about how production HTF should be run

Current finding:

- `CELL 14` and the shared engine are sufficient for the **supported
  multi-regime HTF production scope**:
  - combined batches
  - `1m` and `15m` features
  - `15m` distance metrics
  - `1m` labels
  - `1m / target_4class` optimized outputs
  - helper cache + final helper outputs
  - validation
- For `8h`, this shared path writes the same legacy-compatible roots as the old
  notebook path through
  [\_family_scope()](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L876):
  - `data/htf_backtest`
  - `data/htf_backtest_shift4h`
  - `data/htf_features`
  - `data/htf_features_shift4h`
  - `data/htf_4class_labels` for `1m`
  - `data/htf_4class_labels_shift4h` for `1m`
  - `data/htf_optimized`
  - `data/htf_optimized_shift4h`
  - `data/htf_with_helpers`
  - `data/htf_with_helpers_shift4h`
  - `data/htf_helper_cache` via shared helper-cache namespaces
- Cells `1-13` still overlap those same `8h` roots, so running the full notebook
  end to end means the legacy path can refresh `8h` artifacts before `CELL 14`
  refreshes them again

Legacy-only outputs not reproduced by `CELL 14`:

- `data/htf_4class_labels/15m/...`
- `data/htf_4class_labels_shift4h/15m/...`
- optional legacy `5m` outputs
- `data/htf_backtest/validation_results.parquet`
- `data/htf_backtest/{tf}_batch_stats.parquet`
- `data/htf_backtest/distance_metrics_summary.json`
- legacy helper split/verification side effects from `CELL 12`

Important caveat:

- the shared engine intentionally defines `TARGET_TIMEFRAMES = ("1m",)` in
  [htf_multiregime_pipeline.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L85)
- but some downstream backtest/analysis code still references `15m` and `5m`
  units through the legacy labels directory, for example:
  - [scripts/htf_backtest/catboost/utils.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/htf_backtest/catboost/utils.py#L46)
  - [scripts/htf_backtest/lightgbm/utils.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/htf_backtest/lightgbm/utils.py#L47)
- so `CELL 14` is the supported production path for current HTF materialization,
  but not yet a full replacement for every legacy downstream consumer

Recommended production run recipe:

1. Run Step 0 fetch freshness/update separately using the existing fetch
   workflow.
2. Use the notebook runtime wrapper for logging/monitoring only.
3. Execute `CELL 14` as the production HTF materialization path with
   `MULTI_REGIME_FORCE_FULL_REBUILD = False` by default.
4. Treat cells `1-13` as legacy/debug/back-compat only until `15m`/`5m`
   downstream dependencies are retired or migrated.

### TODO-02: Diff duplicated compute kernels

Task:
Compare notebook-local and shared-engine implementations of:

- `compute_distance_metrics`
- `compute_hybrid_distance_metrics`
- `_compute_past_distance_metrics`
- `compute_4class_labels`

Verify:

- logic equivalence
- parameter equivalence
- NaN/null handling
- threshold behavior
- any bug-fix drift between copies

Evidence to collect:

- code diff notes per function
- verdict per function: `identical`, `equivalent`, or `drift`

Update report with:

- which kernel should become canonical
- safest extraction order

Done when:

- each duplicated kernel has a clear parity verdict

Current finding:

- `compute_distance_metrics`
  - Verdict: `identical`
  - Evidence:
    - notebook:
      [compute_distance_metrics()](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L2627)
    - shared:
      [compute_distance_metrics()](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L355)
  - Notes:
    - same parameters
    - same `@njit` decoration
    - same `min_remaining` gating
    - same top/bottom `5%` outlier logic
    - same NaN behavior via untouched preallocated arrays
- `compute_hybrid_distance_metrics`
  - Verdict: `identical`
  - Evidence:
    - notebook:
      [compute_hybrid_distance_metrics()](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L4007)
    - shared:
      [compute_hybrid_distance_metrics()](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L414)
  - Notes:
    - same parameters
    - same expanding scan over remaining `15m` bars in the current batch only
    - same `min_remaining` gating
    - same outlier percentile behavior
- `_compute_past_distance_metrics`
  - Verdict: `identical`
  - Evidence:
    - notebook:
      [\_compute_past_distance_metrics()](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L1602)
    - shared:
      [\_compute_past_distance_metrics()](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L476)
  - Notes:
    - same parameters
    - same `bar_pos < window` gating
    - same zero-entry skip behavior
    - same top/bottom tail averaging logic
- `compute_4class_labels`
  - Verdict: `equivalent`
  - Evidence:
    - notebook runtime definition:
      [compute_4class_labels()](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L3210)
    - shared:
      [compute_4class_labels()](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L507)
  - Notes:
    - class assignment logic is the same
    - `NaN` handling is the same: `dist_avg_high.is_nan() -> -1`
    - breakout and ratio threshold behavior is the same
    - notebook runtime version creates an unused `is_oscillation` intermediate column
    - shared version omits `is_oscillation`
    - notebook runtime version leaves `batch_id_check` in the returned dataframe if present
    - shared version defensively drops `batch_id_check`
    - notebook contains a second fallback `compute_4class_labels` definition later in the file that is closer to the shared cleanup behavior, but it is guarded by `if "compute_4class_labels" not in globals()` and is not the normal runtime owner in a full script run
    - this cleanup mismatch is interface-level, not final label-artifact-level, because notebook save paths later select explicit output columns and do not persist `batch_id_check`

Validation evidence:

- synthetic parity checks:
  - [/media/przem/linux_data/RiskYieldMM (Copy)/test_output/todo02_kernel_parity_summary.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/todo02_kernel_parity_summary.json)
- real-data `compute_4class_labels` check on `2,000` rows from `data/htf_backtest/15m_distance_metrics.parquet`:
  - [/media/przem/linux_data/RiskYieldMM (Copy)/test_output/todo02_kernel_realdata_check.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/todo02_kernel_realdata_check.json)

Canonical owner recommendation:

- The shared implementation should become canonical for all four kernels.
- Reason:
  - it already serves `8h`, `24h`, and `7d`
  - it has the cleaner `compute_4class_labels` interface
  - it already contains the defensive `batch_id_check` cleanup that the notebook runtime version lacks

Safest extraction order:

1. `_compute_past_distance_metrics`
2. `compute_distance_metrics`
3. `compute_hybrid_distance_metrics`
4. `compute_4class_labels`

Why this order:

- the first three are direct identical copies and can be extracted with the lowest behavioral risk
- `compute_4class_labels` should be done last because it has minor interface drift and two notebook-local definitions to collapse safely

### TODO-03: Diff duplicated control-plane utilities

Task:
Compare notebook and shared implementations of:

- fingerprints
- rebuild-reason logic
- metadata payload builders
- stage rebuild preparation

Verify:

- whether they encode the same rebuild semantics
- whether their metadata files are structurally compatible
- whether one side has newer invalidation behavior

Evidence to collect:

- field-by-field metadata comparison
- rebuild-reason comparison on representative scenarios

Update report with:

- which utility layer should become canonical
- what compatibility shims are needed

Done when:

- shared artifact utility extraction can be planned without unknowns

Current finding:

- `load_json_safe` vs `_load_json_safe`
  - Verdict: `identical`
  - Same missing-file and invalid-JSON behavior.
- `schema_columns_for_batch_dir` vs `_schema_columns_for_batch_dir`
  - Verdict: `identical`
  - Same first-batch schema inspection behavior.
- `artifact_rebuild_reasons` vs `_artifact_rebuild_reasons`
  - Verdict: `identical semantics`
  - Same comparison keys:
    - `artifact_version`
    - `family`
    - `timeframe`
    - `source_fingerprint`
    - `schema_columns`
  - Representative checks show the same reason lists for:
    - exact match
    - schema drift
    - source drift
- `prepare_stage_rebuild` vs `_prepare_stage_rebuild`
  - Verdict: `equivalent semantics`
  - Representative checks show the same rebuild-mode decisions for:
    - no reasons → `incremental_tail`
    - non-destructive drift with restricted `full_rebuild_reasons` → `incremental_tail`
    - `legacy_schema` mismatch in destructive set → `full` + cleanup
  - Important interface drift:
    - notebook version prints rebuild-mode diagnostics
    - shared version performs the same cleanup/mode decision but leaves logging to callers
- `fingerprint_paths` vs `_fingerprint_paths`
  - Verdict: `drift`
  - Notebook fingerprint payload:
    - uses project-relative paths in the digest
    - stores `count`, `latest_mtime_ns`, `total_size_bytes`, `digest`
  - Shared fingerprint payload:
    - uses absolute paths in the digest
    - stores `count`, `digest`, `paths`
  - These payloads are not structurally compatible, and their digests differ even on the same files.
- `fingerprint_batch_dir` vs `_fingerprint_batch_dir`
  - Verdict: `drift`
  - Drift is inherited directly from the underlying fingerprint payload shape.
- `find_batch_missing_required_columns` vs `_find_batch_missing_required_columns`
  - Verdict: `equivalent`
  - Same missing-column detection.
  - Path formatting differs:
    - notebook returns project-relative `path`
    - shared returns absolute `path`
- `clear_artifact_target` vs `_clear_artifact_target`
  - Verdict: `equivalent`
  - Same deletion behavior.
  - Removed-path reporting differs:
    - notebook returns project-relative paths
    - shared returns absolute paths
- `artifact_meta_payload` vs `_artifact_meta_payload`
  - Verdict: `equivalent with format drift`
  - Same logical fields:
    - `artifact_version`
    - `family`
    - `timeframe`
    - `source_fingerprint`
    - `schema_columns`
    - `rebuild_mode`
    - extra payload merge
  - `updated_at` formatting differs:
    - notebook: `...Z`
    - shared: `...+00:00`

Validation evidence:

- representative scenario harness:
  - [/media/przem/linux_data/RiskYieldMM (Copy)/test_output/todo03_control_plane_summary.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/todo03_control_plane_summary.json)

Canonical owner recommendation:

- The shared utility layer should become canonical.
- Reason:
  - rebuild semantics already match
  - the shared path is already the production owner for multi-regime materialization
  - caller-owned logging is a cleaner separation than embedding prints inside the utility layer

Compatibility notes:

- The main migration risk is not rebuild-mode logic. It is metadata/fingerprint shape.
- Cross-compatibility will need one explicit decision:
  - either migrate notebook metadata/fingerprints to the shared shape
  - or add a compatibility reader that can understand both old notebook-style and new shared-style fingerprints during the transition
- The biggest concrete incompatibilities are:
  - relative vs absolute `path`
  - digest input using relative vs absolute path strings
  - notebook fingerprint summary fields (`latest_mtime_ns`, `total_size_bytes`) vs shared `paths`
  - `updated_at` timestamp format
- Shared also has one versioning helper the notebook lacks:
  - [\_stage_version()](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L664)
  - this should likely become the unification target instead of keeping notebook-local `ARTIFACT_STAGE_VERSIONS` as the long-term owner

Safest extraction order:

1. `load_json_safe`
2. `schema_columns_for_batch_dir`
3. `find_batch_missing_required_columns`
4. `clear_artifact_target`
5. `artifact_rebuild_reasons`
6. `prepare_stage_rebuild`
7. `artifact_meta_payload`
8. `fingerprint_paths`
9. `fingerprint_batch_dir`

Why this order:

- the first six are already behaviorally aligned enough to consolidate with low risk
- `artifact_meta_payload` is safe after deciding the timestamp format
- fingerprint migration should be last because it changes the persisted metadata contract and therefore the resume/invalidation surface

### TODO-04: Decide `5m` fate

Task:
Determine whether `5m` is:

- still used
- archive-only
- formally retired
- or needs porting into the shared engine

Verify:

- whether any downstream notebooks/scripts still read `5m` HTF artifacts
- whether any recent workflow depends on `5m`

Evidence to collect:

- repo search results for `5m` HTF artifact paths and assumptions
- decision note for keep/archive/retire

Update report with:

- final `5m` status and impact on unification scope

Done when:

- `5m` is no longer an open ambiguity

Current finding:

- `5m` is **not** archive-only and is **not** formally retired.
- `5m` is still an active downstream dependency in the current repo:
  - stage-1 / backtest workflow references:
    - [notebooks/htf_stage1.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_stage1.py#L90)
    - [notebooks/htf_cell_14_backtest.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_cell_14_backtest.py#L182)
    - [scripts/htf_backtest/configuration.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/htf_backtest/configuration.py#L68)
    - [scripts/htf_backtest/catboost/stage1_runner.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/htf_backtest/catboost/stage1_runner.py#L834)
    - [scripts/htf_backtest/lightgbm/runner.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/htf_backtest/lightgbm/runner.py#L432)
  - prediction-analysis workflow references:
    - [prediction_analysis/multitimeframe_direction_ensemble_analysis.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/prediction_analysis/multitimeframe_direction_ensemble_analysis.py#L3)
    - [prediction_analysis/multitimeframe_cross_target_ensemble_search.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/prediction_analysis/multitimeframe_cross_target_ensemble_search.py#L458)
    - [prediction_analysis/multitimeframe_subset_pruning_analysis.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/prediction_analysis/multitimeframe_subset_pruning_analysis.py#L29)
    - [prediction_analysis/multitimeframe_causal_ensemble_benchmark.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/prediction_analysis/multitimeframe_causal_ensemble_benchmark.py#L34)
- Current production-style artifacts for `5m` are also present on disk:
  - `data/htf_backtest/5m_HTF_combined.parquet`
  - `data/htf_features/5m`
  - `data/htf_4class_labels/5m`
  - `data/htf_optimized/5m/target_4class`
  - `data/htf_with_helpers/5m/target_4class`
- At the same time, `5m` is already outside the current supported shared-engine scope:
  - notebook default has `ENABLE_5M_PIPELINE = False` in
    [htf_pythonscript.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L321)
  - shared engine excludes `5m` entirely through
    [TARGET_TIMEFRAMES = (\"1m\",)](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L85)

Decision:

- `5m` should be treated as an **active legacy dependency**.
- It should **not** be retired or silently dropped during the current unification phase.
- It should also **not** block unification of the supported production HTF path, because the current shared-engine authority is already `1m`-target-centric and excludes `5m`.

Unification impact:

- Phase 1 unification should proceed for:
  - shared production path
  - `8h`, `24h`, `7d`
  - `1m` and `15m`
- `5m` should remain explicitly legacy-scoped until one of two follow-up decisions is made:
  1. port `5m` into the shared engine deliberately
  2. migrate or retire downstream `5m` consumers and then archive the legacy `5m` path

Practical rule:

- do not remove notebook-local `5m` logic during the first unification pass
- isolate it as a legacy island with explicit comments/scope boundaries
- do not claim the HTF system is fully unified until the separate `5m` decision is implemented

### TODO-05: Decide fetch-step ownership

Task:
Decide whether fetch freshness checking should be integrated into
`htf_pythonscript.py` or remain an explicit Step 0 prerequisite.

Verify:

- whether current users expect HTF to self-check freshness
- whether adding `run_step0_fetch_and_aggregate()` would be safe in HTF runs

Evidence to collect:

- dependency note on fetch inputs
- recommended ownership rule for Step 0

Update report with:

- final policy: integrated Step 0 vs separate prerequisite

Done when:

- the supported production recipe includes a clear fetch rule

Current finding:

- The current fetch/update ownership is already explicit in the main workflow:
  - [scripts/workflow/data_fetching.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/workflow/data_fetching.py#L35)
  - [notebooks/Fetch_data.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/Fetch_data.py#L57)
  - [notebooks/main_wf.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/main_wf.py#L135)
- `htf_pythonscript.py` does **not** call `run_step0_fetch_and_aggregate()` and does **not** own raw-data mutation. It assumes `fetchingByBit/...` already exists and then reads from it through:
  - [RAW_DATA_DIR](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L104)
  - raw combined builders using `sorted-{tf}-bybit-linear`
  - [HTFFeatureEngine](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L1656)
- The current Step 0 freshness check is too narrow to become the HTF production authority as-is:
  - [check_data_freshness()](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/workflow/data_fetching.py#L14) checks only the `8h` OHLCV parquet freshness
  - but HTF now depends on more than that:
    - lower-timeframe OHLCV inputs
    - auxiliary fetched sources discovered by
      [discover_available_sources()](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/compute_htf_features.py#L289)
    - source selection/broadcasting through
      [load_data_for_timeframe()](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/compute_htf_features.py#L685)
      and
      [get_source_paths_for_timeframe()](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/compute_htf_features.py#L439)
- So integrating the current Step 0 fetch wrapper directly into HTF runs would create a false sense of completeness:
  - it can say “fresh” based on `8h` only
  - while auxiliary source freshness for enriched HTF features is not fully validated by that check
- There is also an operational reason to keep fetch separate:
  - HTF runs are long, resumable artifact builds
  - implicit raw-data mutation at the start of the same script makes the input snapshot less explicit and complicates debugging/reproducibility

Decision:

- Keep fetch/update as an **explicit Step 0 prerequisite**, not an automatic mutating step inside `htf_pythonscript.py`.
- The supported production recipe should remain:
  1. run Step 0 fetch/update separately
  2. then run the HTF production path

Recommended improvement:

- HTF may add a **non-mutating preflight freshness/status check** at startup, but not auto-fetch.
- That preflight should:
  - report whether key `fetchingByBit` inputs exist
  - optionally summarize latest timestamps for:
    - core OHLCV inputs
    - auxiliary sources used by the feature engine
- If a future integrated fetch mode is ever added, it should be an explicit opt-in wrapper around Step 0, not the default production behavior.

### TODO-06: Consolidate runtime config ownership

Task:
Identify all production-significant toggles in:

- notebook global setup
- legacy cells
- `CELL 14`
- `MultiRegimeHTFConfig`

Verify:

- whether any cell-local redefinitions can still alter production behavior
- whether duplicate config knobs disagree in default value or meaning

Evidence to collect:

- one config inventory with source location and current default

Update report with:

- the minimal config surface that should remain user-facing

Done when:

- production toggles can be expressed from one place

Current finding:

- The notebook currently has **four config layers**:
  1. top-level runtime/bootstrap globals in
     [htf_pythonscript.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L89)
  2. legacy-path stage toggles spread across Cells `2-13`
  3. `CELL 14` wrapper toggles in
     [htf_pythonscript.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L6473)
  4. shared-engine defaults in
     [MultiRegimeHTFConfig](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L143)
- For the supported production path, the duplicated meanings mostly **do not conflict numerically**:
  - `CELL 14` defaults and `MultiRegimeHTFConfig` defaults match for:
    - build regimes `("8h", "24h", "7d")`
    - `rebuild_existing=False`
    - `smoke_mode=False`
    - `run_optimization=True`
    - `run_helpers=True`
    - `run_validation=True`
- The real drift is **ownership**, not raw value mismatch:
  - `CELL 14` is not yet self-contained; it still depends on notebook globals defined by legacy cells:
    - `PIPELINE_ARTIFACT_VERSION`
    - `TF_THRESHOLDS`
    - `DISTANCE_WINDOWS_BY_TF`
    - `BREAKOUT_THRESHOLD`
    - `RISK_RATIO`
    - `BREAKFREE_THRESHOLD`
  - these are then injected into
    [MultiRegimeHTFConfig(...)](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L6499)
  - so later notebook edits or cell-local redefinitions can still silently alter the shared production path
- There is also naming drift that makes the runtime surface harder to reason about:
  - notebook uses `MULTI_REGIME_FORCE_FULL_REBUILD`
  - shared engine uses `rebuild_existing`
  - same meaning, different name
- Several shared-engine production knobs are **not surfaced** in the notebook wrapper at all:
  - `force_recreate_combined`
  - `min_raw_lead_hours_for_update`
  - `feature_incremental_update`
  - feature overlap/context policies
  - metric/label/helper incremental tail policies
  - helper-cache overlap and cache-root settings
  - `stage_progress_every_batches`
- Several legacy notebook toggles should be treated as **legacy-only/debug-only**, not part of the supported production config surface:
  - `ENABLE_5M_PIPELINE`
  - `SKIP_VALIDATION`
  - `RECOMPUTE_FEATURES`
  - `RECOMPUTE_DISTANCE_METRICS`
  - `RECOMPUTE_LABELS`
  - legacy helper/label incremental knobs for `5m`/`15m`

Decision:

- The supported production config surface should be reduced to **one explicit shared-path config block** in `htf_pythonscript.py`, whose job is only to populate `MultiRegimeHTFConfig`.
- Legacy cell toggles should remain available only for debug/back-compat runs and should be clearly marked non-production.
- The shared production path should no longer depend on notebook-defined legacy globals for core semantics. The following should move to shared ownership or a dedicated shared-path config block:
  - artifact version
  - threshold map
  - distance-window map
  - breakout/risk/breakfree constants

Recommended minimal user-facing production config:

1. Execution scope
   - run enabled
   - build regimes
   - validate regimes
2. Rebuild mode
   - force full rebuild
   - smoke mode / smoke window
3. Downstream stage toggles
   - run optimization
   - run helpers
   - run validation
4. Optional advanced shared-path settings
   - combined update threshold
   - incremental overlap/tail policies
   - helper-cache root and cache policy

Everything else should either:

- live inside `MultiRegimeHTFConfig` defaults
- or remain explicitly legacy/debug-only outside the supported production recipe

### TODO-07: Audit compatibility aliases and path contracts

Task:
Determine which legacy naming contracts are truly required:

- `period_8h_start`
- legacy `8h` root names
- `shift4h` naming

Verify:

- downstream code that reads these fields/paths
- whether aliases are needed only externally or also internally

Evidence to collect:

- downstream consumer list
- alias-retention recommendation

Update report with:

- compatibility contract to preserve during unification

Done when:

- alias retention is a deliberate choice instead of a default habit

Current finding:

- The compatibility surface is **not uniform**; some names are real downstream contracts and some are mostly internal producer conventions.
- `period_8h_start` is a real external contract today:
  - analysis notebooks explicitly exclude/read it:
    - [notebooks/htf_analyze.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_analyze.py#L54)
    - [notebooks/htf_batch_correlation.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_batch_correlation.py#L94)
  - optimizer metadata handling explicitly excludes it from transformable features:
    - [scripts/feature_engineering/optimize_htf_features.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/optimize_htf_features.py#L90)
  - both the notebook and shared engine explicitly document that it is being preserved for compatibility:
    - [htf_pythonscript.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L9)
    - [htf_multiregime_pipeline.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L4)
- The base production root names are also real downstream contracts:
  - backtest utilities hardcode:
    - `data/htf_with_helpers`
    - `data/htf_4class_labels`
    in
    [scripts/htf_backtest/catboost/utils.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/htf_backtest/catboost/utils.py#L39)
    and
    [scripts/htf_backtest/lightgbm/utils.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/htf_backtest/lightgbm/utils.py#L40)
  - feature optimization also defaults to the legacy roots:
    - [scripts/feature_engineering/optimize_htf_features.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/optimize_htf_features.py#L79)
- `bar_in_batch_norm` is also consumed downstream for training-window/tail filtering:
  - [scripts/htf_backtest/catboost/utils.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/htf_backtest/catboost/utils.py#L278)
  - [scripts/htf_backtest/lightgbm/utils.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/htf_backtest/lightgbm/utils.py#L235)
- By contrast, `shift4h` naming looks much less external:
  - direct code references are effectively confined to:
    - [notebooks/htf_pythonscript.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py)
    - [htf_multiregime_pipeline.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py)
  - downstream backtest/optimizer consumers generally read the **base** roots, not the `*_shift4h` roots directly
  - this suggests `shift4h` is primarily a producer-side legacy convention, not a wide downstream API

Decision:

- Preserve `period_8h_start` as an **external compatibility alias on written artifacts** during unification.
- Preserve the base legacy production root names as the supported external contract:
  - `htf_backtest`
  - `htf_features`
  - `htf_4class_labels`
  - `htf_optimized`
  - `htf_with_helpers`
- Preserve `bar_in_batch_norm` as part of the downstream artifact contract.
- Treat `shift4h` naming as a **legacy producer/path contract**, not a foundational semantic contract:
  - keep it during the first unification pass to avoid needless churn
  - but do not let it dictate internal shared-kernel design

Compatibility contract to preserve during unification:

1. External artifact columns
   - `period_8h_start`
   - `bar_in_batch_norm`
   - existing family/meta columns currently consumed by optimizers/helpers
2. External base root names
   - `data/htf_backtest`
   - `data/htf_features`
   - `data/htf_4class_labels`
   - `data/htf_optimized`
   - `data/htf_with_helpers`
3. Legacy shift-family paths
   - retain `*_shift4h` names for compatibility in phase 1
   - reevaluate only after producer unification is complete and downstream readers are audited

### TODO-08: Decide validation ownership

Task:
Compare notebook validation and shared-engine validation and decide final
ownership.

Verify:

- which notebook checks are unique
- which shared checks subsume notebook checks
- whether notebook validation is still needed outside debug workflows

Evidence to collect:

- validation coverage matrix: notebook vs shared

Update report with:

- final validation authority

Done when:

- there is one clear place that defines production validation

Current finding:

- Validation is still split across **three notebook-side layers** plus the shared engine:
  1. legacy raw/batch alignment validation in
     [htf_pythonscript.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L1360)
  2. legacy feature-batch sanity validation in
     [htf_pythonscript.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L2238)
  3. legacy end-to-end family/timeframe validation in
     [htf_pythonscript.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L6348)
  4. shared regime-wide validation in
     [_validate_regime()](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L2514)

Validation coverage matrix:

1. Notebook-only today
   - raw `8h` OHLCV vs batched open/close alignment
   - feature-batch structure sanity:
     - required feature columns
     - sample feature counts
     - all-NaN / high-NaN / infinite-value checks
     - first-timestamp vs `period_8h_start`
   - optimized/helper existence and row-count parity checks
   - helper-column presence checks
   - legacy `5m` validation coverage
   - legacy `15m` label-side coverage that is outside the shared production scope

2. Shared-engine coverage today
   - combined-file existence and rows-per-batch by regime/family/tf
   - period-start alignment
   - anchor alignment
   - `1m` label valid-row counts by regime/family
   - `remaining_bars` within-batch consistency
   - `close_end` / breakfree batch-end-close consistency
   - `B/C` cross-family source mapping and valid-label coverage

3. Overlap
   - combined batch geometry/alignment
   - label-window coverage semantics
   - cross-family `B/C` consistency for the supported path

Key conclusion:

- The shared engine does **not yet subsume** all notebook validation.
- In particular, shared validation currently does **not** cover:
  - feature artifact sanity
  - optimized artifact row-count checks
  - helper artifact row-count/helper-column checks
  - legacy `5m`
- So notebook validation is still useful, but mostly as:
  - legacy/debug validation
  - supplemental artifact sanity checking
  - `5m` coverage

Decision:

- The **final production validation authority** should be the shared engine, because it is the supported production HTF path.
- However, notebook validation cannot be retired yet without loss of coverage.
- During unification:
  1. port the production-relevant notebook checks for:
     - features
     - optimized batches
     - helpers
     into the shared validation layer
  2. leave raw-alignment checks and `5m` validation notebook-local/debug-only unless `5m` is later migrated

Supported rule for now:

- For supported production HTF (`CELL 14` / multi-regime path), treat shared validation as the authoritative pass/fail gate.
- Treat notebook validations as supplementary debug/back-compat checks until the missing feature/optimized/helper checks are migrated.

### TODO-09: Plan the controlled feature-schema promotion refresh

Task:
Define the smallest safe production refresh needed to promote the richer feature
schema.

Verify:

- whether labels can remain untouched
- exact downstream stages to rerun:
  - features
  - optimization
  - helpers

Evidence to collect:

- artifact dependency chain for the schema change
- proposed partial rerun recipe

Update report with:

- exact production refresh plan and prerequisites

Done when:

- the schema promotion can be run without another broad full-notebook rerun

Current finding:

- The richer feature schema does **not** require a full HTF rebuild.
- The dependency chain for this schema change is:
  1. combined stays valid
  2. labels stay valid
  3. features must refresh
  4. optimized outputs must refresh because feature columns/fingerprints changed
  5. helper stages must refresh because they depend on rewritten feature and optimized artifacts
- This is already documented in the workflow audit:
  - [htf_workflow_audit_2026-03-18.md](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/notes/htf_workflow_audit_2026-03-18.md#what-still-must-rebuild-after-a-schema-change)
- The current invalidation probe confirms production `1m`/`15m` feature trees are stale for the right reasons:
  - `artifact_version`
  - `source_fingerprint`
  - `schema_columns`
  in
  [resume_logic_feature_invalidation_summary.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/resume_logic_feature_invalidation_summary.json)
- The helper stage is also downstream of rewritten feature batches:
  - helper cache rebuild checks raw batch mtimes/fingerprints in
    [htf_helper_cache.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_helper_cache.py#L370)
  - final helper materialization checks optimized batch mtimes and helper-cache mtimes in
    [htf_helper_cache.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_helper_cache.py#L634)

Decision:

- The smallest safe promotion path is a **shared-path production refresh from the feature stage onward**, not a full notebook replay.
- Labels do **not** need rebuilding for this change.
- Combined batches do **not** need rebuilding unless Step 0 fetch/update changed the raw snapshot separately.

Exact production refresh recipe:

1. Keep fetch ownership separate
   - if needed, run Step 0 fetch/update first
   - otherwise keep the current raw snapshot unchanged for a pure schema-promotion rerun
2. Run the supported production HTF path only:
   - `CELL 14` / `run_multi_regime_htf_pipeline(...)`
3. Use these settings:
   - `rebuild_existing=False`
   - `build_regimes=("8h", "24h", "7d")`
   - `run_optimization=True`
   - `run_helpers=True`
   - `run_validation=True`
4. Expected stage behavior on this rerun:
   - combined: `current`
   - labels: `current`
   - features (`1m`, `15m`, `B`, `C`, all regimes): stale and rebuilt
   - optimized (`1m/target_4class`): refreshed
   - helper cache/materialization: refreshed as invalidated by upstream artifact changes
5. Do **not** run the legacy notebook end to end just for this promotion.
6. Do **not** rebuild `5m` as part of this promotion; it is outside the current shared-path scope.

Operational note:

- Because the shared engine will still execute the combined and label stages, “from the feature stage onward” means **letting resume logic skip them**, not manually deleting notebook cells from the run recipe.
- The relevant safety property is that the supported production entrypoint is resumable and should only rebuild the stale downstream artifacts for this schema change.

### TODO-10: Bound the helper/runtime performance follow-up

Task:
Decide which performance concerns belong to the unification phase and which
should be deferred.

Verify:

- whether helper checkpointing/progress is required for usability now
- whether performance work can wait until after structural unification

Evidence to collect:

- one short list of performance issues that are blocking vs non-blocking

Update report with:

- explicit statement of what performance work is in scope for the next phase

Done when:

- runtime speed concerns are separated from correctness/unification concerns

Current finding:

- The main runtime pain is still helper-related:
  - long exact helper-cache builds
  - Python-orchestrated walk-forward refits
  - long reruns when upstream feature artifacts change
- But most of that is **not blocking unification correctness**.
- The system already has the minimum operational visibility needed for the next structural phase:
  - per-run logs
  - live status JSON
  - heartbeats
  - stage progress reporting

Blocking / in-scope for the next unification phase:

1. Do not regress resumability
   - preserve current rebuild/current detection
   - do not reintroduce accidental full-history recompute for supported stages
2. Preserve monitoring/usability
   - keep per-run logging, status JSON, and heartbeat output
   - keep stage-level progress for long helper/cache phases
3. Preserve exact helper semantics
   - keep the current helper-cache/materialization split
   - do not mix structural unification with helper-math changes

Non-blocking / defer until after structural unification:

1. Faster helper fitting strategies
   - `partial_fit()` adoption
   - approximate incremental helper updates
2. Deep helper runtime optimization
   - Python loop elimination
   - Rust/vectorized rewrites of the walk-forward orchestration
   - broader parallelization work
3. Long-run usability enhancements beyond current monitoring
   - cache checkpointing inside the long exact helper pass
   - more aggressive intermediate persistence
4. Broader non-HTF performance work
   - fetch speedups
   - backtest/training runtime tuning

Decision:

- The next phase should stay focused on **structural unification and ownership cleanup**.
- Performance work is in scope only when it is necessary to:
  - preserve current resumability
  - preserve current observability
  - avoid breaking exact helper semantics
- Everything else should be deferred until the production path is unified enough that performance improvements only need to be implemented once.

## Suggested Execution Order

1. `TODO-01` execution authority
2. `TODO-02` duplicated kernels
3. `TODO-03` duplicated control-plane utilities
4. `TODO-08` validation ownership
5. `TODO-04` `5m` decision
6. `TODO-05` fetch-step ownership
7. `TODO-06` config consolidation
8. `TODO-07` compatibility alias contract
9. `TODO-09` controlled schema-promotion refresh
10. `TODO-10` helper/runtime performance scope

## Bottom Line

The reports now agree on the big picture:

- the shared multi-regime engine is the long-term compute authority
- the notebook should become the single user-facing entrypoint
- but the system is not ready to be called “one implementation” yet

The most important remaining investigations are not broad or abstract anymore.
They are concrete:

- duplicated kernels
- duplicated rebuild utilities
- legacy `5m`
- fetch-step ownership
- validation ownership
- mixed-path execution defaults

That is enough to plan the next phase without another full audit.
