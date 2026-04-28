# HTF Unification Report - Legacy Notebook vs Shared Multi-Regime Pipeline

## Goal

This report compares:

- [htf_pythonscript.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py)
- [htf_multiregime_pipeline.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py)

The purpose is to decide how to unify production HTF execution into a single path centered on `htf_pythonscript`.

## Executive Summary

The current system is only **partially unified**.

It already shares these core modules:

- feature engine: [compute_htf_features.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/compute_htf_features.py)
- optimizer: [optimize_htf_features.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/optimize_htf_features.py)
- helper cache/materialization: [htf_helper_cache.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_helper_cache.py)

But several crucial HTF computations still exist twice:

- artifact metadata / rebuild helpers
- combined batch generation
- past-distance feature kernels
- distance metrics
- 4-class label logic
- hybrid `1m` label logic
- validation

So today:

- the notebook is still a large legacy implementation
- the shared multi-regime pipeline is a second implementation of the same HTF workflow
- `CELL 14` in the notebook calls the shared pipeline, but cells `1-13` still run the old path before it

This is operationally risky because production behavior depends on two parallel implementations that can drift.

The right target is:

- **one production entrypoint**: `htf_pythonscript.py`
- **one production execution engine**: shared stage modules
- notebook keeps only orchestration, config, run logging, and analysis/debug helpers

In other words: unify to one script as an entrypoint, not one giant monolithic file.

## High-Level Difference

### Legacy notebook path

The notebook contains the original HTF pipeline as a sequence of cells:

- setup and run logging
- combined generation
- feature engineering
- shift-family materialization
- distance metrics
- labels
- optimization
- helpers
- validation

This path is primarily legacy `8h`, with old `shift4h` family naming and a disabled legacy `5m` branch.

### Shared multi-regime path

The shared pipeline is a reusable module with the same major stages but generalized for:

- `8h`
- `24h`
- `7d`
- family `B`
- family `C`

This path is the current source of truth for multi-regime HTF materialization.

## Section-by-Section Comparison

## 1. Setup and Runtime Control

### Notebook

The notebook owns:

- repo/path resolution
- directory creation
- run log files
- status JSON
- heartbeat thread
- progress callback formatting

Relevant code:

- [htf_pythonscript.py:41](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L41)
- [htf_pythonscript.py:218](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L218)
- [htf_pythonscript.py:257](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L257)

### Shared pipeline

The shared pipeline has its own stage logging and progress signaling, but no notebook-style runtime harness.

Relevant code:

- [htf_multiregime_pipeline.py:205](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L205)
- [htf_multiregime_pipeline.py:266](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L266)

### Conclusion

This separation is fine.

Recommended unification:

- keep runtime logging/orchestration in `htf_pythonscript.py`
- do not move notebook run-heartbeat logic into the shared compute module

## 2. Artifact Metadata and Rebuild Logic

### Notebook

The notebook defines:

- `fingerprint_paths`
- `fingerprint_batch_dir`
- `artifact_rebuild_reasons`
- `artifact_meta_payload`
- `prepare_stage_rebuild`

Relevant code:

- [htf_pythonscript.py:417](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L417)
- [htf_pythonscript.py:487](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L487)
- [htf_pythonscript.py:540](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L540)

### Shared pipeline

The shared pipeline defines near-equivalent copies:

- `_fingerprint_paths`
- `_fingerprint_batch_dir`
- `_artifact_rebuild_reasons`
- `_artifact_meta_payload`
- `_prepare_stage_rebuild`

Relevant code:

- [htf_multiregime_pipeline.py:593](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L593)
- [htf_multiregime_pipeline.py:673](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L673)
- [htf_multiregime_pipeline.py:724](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L724)

### Conclusion

This is duplicated control-plane logic and should be unified first.

Recommended target:

- extract one shared artifact utility module
- notebook and shared pipeline should both import the same helper functions

## 3. Batch Regime Model and Family Metadata

### Notebook

The notebook still thinks in legacy `8h` terms:

- `TF_CONFIG`
- `bars_per_half`
- `add_family_metadata`
- `shift4h`
- `period_8h_start`

Relevant code:

- [htf_pythonscript.py:359](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L359)
- [htf_pythonscript.py:663](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L663)

### Shared pipeline

The shared pipeline has the generalized regime model:

- `BatchRegimeConfig`
- `REGIME_CONFIGS`
- `_bars_per_batch`
- `_bars_per_half`
- `_entry_bar_limit`
- `_family_scope`
- `_add_family_metadata`

Relevant code:

- [htf_multiregime_pipeline.py:50](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L50)
- [htf_multiregime_pipeline.py:844](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L844)
- [htf_multiregime_pipeline.py:958](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L958)

### Conclusion

The shared version is the correct long-term model.

Recommended target:

- notebook should stop owning batch geometry logic
- notebook should delegate all family/regime metadata generation to shared code

## 4. Combined Batch Generation

### Notebook

Notebook combined generation is legacy `8h` plus shifted `4h`:

- `create_combined_file`
- `build_shift4h_combined_from_base`
- `ensure_base_combined_family_metadata`

Relevant code:

- [htf_pythonscript.py:825](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L825)
- [htf_pythonscript.py:963](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L963)
- [htf_pythonscript.py:1077](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L1077)

### Shared pipeline

Shared combined generation is generalized:

- `_build_base_combined`
- `_build_shifted_combined`

Relevant code:

- [htf_multiregime_pipeline.py:1073](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L1073)
- [htf_multiregime_pipeline.py:1247](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L1247)

### Conclusion

This is a direct duplication of a production stage.

Recommended target:

- shared combined generation becomes the only production implementation
- notebook only calls it

## 5. Feature Engineering

### Shared part

Both paths already share:

- `HTFFeatureEngine`
- fetched-source augmentation
- core feature computation

Relevant code:

- [compute_htf_features.py:566](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/compute_htf_features.py#L566)
- [compute_htf_features.py:743](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/compute_htf_features.py#L743)

### Duplicated part

Both files still separately implement:

- expected feature schema handling
- batch splitting
- incremental feature scope selection
- shifted-family materialization
- custom `D_*` batch-local features

Notebook:

- [htf_pythonscript.py:1602](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L1602)
- [htf_pythonscript.py:1660](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L1660)
- [htf_pythonscript.py:2109](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L2109)

Shared pipeline:

- [htf_multiregime_pipeline.py:1403](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L1403)
- [htf_multiregime_pipeline.py:1572](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L1572)
- [htf_multiregime_pipeline.py:1442](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L1442)

### Conclusion

Feature compute kernel is shared, but the stage orchestration is still duplicated.

Recommended target:

- one shared feature-stage builder
- no notebook-local feature stage logic except launch and progress display

## 6. Distance Metrics and Label Kernels

This is the biggest duplication problem.

### Notebook owns its own kernels

- `_compute_past_distance_metrics`
- `compute_distance_metrics`
- `compute_4class_labels`
- `compute_hybrid_distance_metrics`

Relevant code:

- [htf_pythonscript.py:1602](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L1602)
- [htf_pythonscript.py:2627](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L2627)
- [htf_pythonscript.py:3210](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L3210)
- [htf_pythonscript.py:4007](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L4007)

### Shared pipeline owns near-identical kernels

- `compute_distance_metrics`
- `compute_hybrid_distance_metrics`
- `_compute_past_distance_metrics`
- `compute_4class_labels`

Relevant code:

- [htf_multiregime_pipeline.py:355](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L355)
- [htf_multiregime_pipeline.py:414](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L414)
- [htf_multiregime_pipeline.py:476](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L476)
- [htf_multiregime_pipeline.py:507](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L507)

### Conclusion

These kernels should not exist in two places.

Recommended target:

- move them into one shared `htf_labeling_kernels.py` or similar module
- both notebook and multi-regime pipeline import the same functions

This is the highest-priority code unification step.

## 7. 15m Metrics and 1m Labels

### Notebook

Legacy implementation:

- `CELL 7`
- `CELL 8`
- `CELL 9B`
- `CELL 9C`

The notebook still directly implements:

- metric generation
- label gating
- per-batch save loops
- shift-family label flow

### Shared pipeline

Shared implementations:

- `_build_15m_metrics`
- `_build_1m_labels`

Relevant code:

- [htf_multiregime_pipeline.py:1812](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L1812)
- [htf_multiregime_pipeline.py:1979](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L1979)

### Conclusion

This is still duplicated stage logic, even if formulas currently match.

Recommended target:

- notebook should no longer own label materialization logic
- notebook should call shared `build_metrics` and `build_labels` stages only

## 8. Optimization

### Current state

This part is already mostly unified.

Notebook:

- [htf_pythonscript.py:5100](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L5100)

Shared pipeline:

- [htf_multiregime_pipeline.py:2310](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L2310)

Both call:

- [optimize_htf_features.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/optimize_htf_features.py)

### Conclusion

This is already in good shape.

Recommended target:

- keep optimizer as shared module
- remove notebook-specific orchestration duplication over time

## 9. Helpers

### Current state

This is also mostly unified now.

Notebook:

- [htf_pythonscript.py:5212](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L5212)

Shared pipeline:

- [htf_multiregime_pipeline.py:2348](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L2348)

Both call:

- [htf_helper_cache.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_helper_cache.py)

### Remaining duplication

Still duplicated:

- family-run enumeration
- helper source namespace selection
- local metadata plumbing

### Conclusion

Much better than labels, but still not fully unified.

Recommended target:

- notebook should become a wrapper around one shared helper stage function

## 10. Validation

### Notebook

Large legacy validation suite:

- [htf_pythonscript.py:5661](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L5661)

### Shared pipeline

Shared multi-regime validator:

- [htf_multiregime_pipeline.py:2514](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L2514)

### Conclusion

Validation still exists in two different systems.

Recommended target:

- one shared validator library
- notebook displays results, but does not own validation rules

## 11. Scope Differences

### Notebook-only scope

- legacy `5m` logic still exists in notebook
- legacy cell-by-cell workflow
- notebook-style runtime monitoring
- legacy end-to-end validation suite

### Shared-pipeline-only scope

- full regime generalization (`8h`, `24h`, `7d`)
- centralized regime config
- cleaner family/regime abstraction
- current production validation for multi-regime outputs

## Current Authority Boundary

Today the files imply this authority split:

- `htf_pythonscript.py`
  - runtime harness
  - historical/legacy HTF notebook implementation
  - launches `CELL 14`
- `htf_multiregime_pipeline.py`
  - authoritative multi-regime implementation

That means the notebook is still both:

- a legacy implementation
- a wrapper around the newer implementation

This is exactly the ambiguity we should remove.

## Main Risks of the Current Dual Structure

1. Formula drift

If one copy of:

- `compute_4class_labels`
- `compute_hybrid_distance_metrics`
- `_compute_past_distance_metrics`

changes and the other does not, results diverge silently.

2. Resume logic drift

Feature invalidation and artifact metadata logic already had to be patched in both places.

That is a sign of structural duplication, not just incidental complexity.

3. Validation drift

Two different validators means one path can say “good” while the other misses a rule or handles an edge batch differently.

4. Operational confusion

If someone runs the whole notebook from top to bottom, they still execute the legacy path before the shared path.

That is slower, harder to reason about, and makes production state less transparent.

## Recommended Unification Target

The right target is **not** “put every line into one giant notebook file”.

The right target is:

- one **production entrypoint**: `htf_pythonscript.py`
- one **production implementation**: shared imported stage code

### `htf_pythonscript.py` should keep

- configuration
- fetch-step handoff
- run logging
- status/heartbeat
- stage toggles
- smoke/full-run control
- inspection/debug notes

### Shared modules should own

- artifact rebuild helpers
- regime/family model
- combined generation
- feature batch building
- distance metrics
- label kernels
- label materialization
- optimization stage orchestration
- helper stage orchestration
- validation rules

## Recommended Migration Order

### Phase 1: unify duplicated kernels

Move into shared modules:

- `_compute_past_distance_metrics`
- `compute_distance_metrics`
- `compute_hybrid_distance_metrics`
- `compute_4class_labels`

This removes the most dangerous duplication first.

### Phase 2: unify artifact/rebuild utilities

Extract one shared module for:

- fingerprinting
- schema checks
- artifact metadata payloads
- rebuild mode selection

### Phase 3: notebook stops owning stage logic

Replace legacy notebook implementations of:

- combined generation
- feature materialization
- metrics
- labels
- validation

with calls into the shared stage functions.

### Phase 4: legacy-only paths are isolated

Decide what to do with `5m`:

- archive it
- or move it to a separate explicit legacy module

It should not keep the main notebook structurally legacy-heavy if it is not part of the production target.

### Phase 5: notebook becomes thin orchestrator

At that point:

- `CELL 14` style execution becomes the normal execution
- cells `1-13` stop being production compute code
- they either disappear or become wrappers / debugging helpers only

## Decision Basis

Based on the current code, the safest unification plan is:

1. keep `htf_pythonscript.py` as the single visible entrypoint
2. move all real compute rules under shared modules
3. remove notebook-local implementations of stage logic
4. retain notebook runtime monitoring and analysis convenience

That gives:

- one user-facing script
- one compute implementation
- lower drift risk
- easier resume correctness
- simpler production operations

## Recommended Next Task

The next implementation plan should focus on:

- extracting duplicated labeling and distance kernels first
- then replacing notebook stage implementations with shared imports

That is the shortest path to a truly unified HTF workflow centered on `htf_pythonscript`.
