# HTF Phase 8 Wrapper Review

Date: 2026-03-18

## Scope
Review the remaining wrapper/shim functions in `notebooks/htf_pythonscript.py` and decide:
- which ones must stay for phase-1 compatibility
- which ones are only temporary pass-through names
- which ones should not be removed yet even though shared implementations already exist

## Result
The remaining wrappers fall into two groups.

### 1. Keep for phase-1 compatibility
These wrappers preserve notebook-specific legacy behavior and should remain until final acceptance:
- `fingerprint_paths`
- `fingerprint_batch_dir`
- `find_batch_missing_required_columns`
- `clear_artifact_target`
- `artifact_rebuild_reasons`
- `artifact_meta_payload`
- `prepare_stage_rebuild`

Why they still matter:
- project-relative fingerprint serialization
- `include_summary_stats=True` in legacy fingerprints
- legacy metadata timestamp formatting (`updated_at_mode="z"`)
- notebook-local rebuild logging (`log=print`)

These are not just naming aliases; they still preserve legacy notebook conventions.

### 2. Temporary pass-through names
These wrappers currently add no math behavior and exist mainly for stable notebook-local naming:
- `_compute_past_distance_metrics`
- `compute_distance_metrics`
- `compute_4class_labels`
- `compute_hybrid_distance_metrics`

Why they are still not removed yet:
- legacy cells reference these local names directly
- some legacy/hybrid cells still use `if \"name\" not in globals()` guards
- removing them safely requires either:
  - a small alias strategy applied consistently across legacy cells, or
  - retiring more of the legacy/debug path at once

So they are candidates for later cleanup, but not safe blind deletion in this phase.

### 3. Low-impact utility aliases
These are effectively direct shared aliases:
- `load_json_safe`
- `schema_columns_for_batch_dir`

These are not high-risk, but removing them now brings little value. They can be folded later together with the broader legacy-wrapper cleanup.

## Practical Conclusion
The next safe cleanup rule is:
- do not remove artifact/control wrappers yet
- do not remove kernel-name wrappers until legacy cell-order behavior is simplified explicitly
- prefer targeted alias cleanup later over broad deletion now

This means the correct next Phase 8 work is still structural:
- continue reducing ambiguity in notebook ownership
- keep wrappers documented
- delay wrapper removal until after final acceptance or a dedicated legacy-cell simplification pass
