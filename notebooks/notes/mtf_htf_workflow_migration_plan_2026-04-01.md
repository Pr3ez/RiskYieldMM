# MTF HTF Workflow Migration Plan 2026-04-01

Superseded later the same day.
Current canonical HTF production entrypoint is:
- [htf_pythonscript.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py)

This note is kept only as historical context from the temporary `mtf_htf_workflow.py`
migration attempt.

## Goal
Move the supported HTF production workflow out of `notebooks/htf_pythonscript.py` into:

- [mtf_htf_workflow.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/mtf_htf_workflow.py)

so production and legacy/debug ownership are no longer mixed in one file.

## Current Verified State

### `mtf_htf_workflow.py`
- currently empty
- safe to use as a clean production entrypoint

### Current supported production surface inside `htf_pythonscript.py`
The real production path is much smaller than the full notebook file suggests.

The supported path currently consists of:

1. bootstrap / path resolution
2. run logging and status-file plumbing
3. shared production config block
4. `multi_regime_progress_callback(...)`
5. `run_supported_multi_regime_pipeline()`
6. script-entry short-circuit gate

Everything below that is legacy notebook content.

## What Must Move

### A. Bootstrap and path resolution
From the current file:
- `resolve_project_root()`
- `PROJECT_ROOT`
- `sys.path` bootstrap
- production paths:
  - `data`
  - `fetchingByBit`
  - `test_output/htf_run_logs`

Why move:
- production entrypoint must be self-contained
- it should not depend on legacy notebook globals

### B. Run logging/runtime state
Move the production-only logging/runtime helpers:
- `RUN_INSTANCE_ID`
- `RUN_LOG_PATH`
- `RUN_STATUS_PATH`
- `RUN_PROGRESS`
- `_format_elapsed`
- `_stringify_progress_value`
- `_write_run_status`
- `_append_to_run_log`
- `_tee_print`
- `set_run_stage`
- `log_loop_progress`
- `multi_regime_progress_callback`
- `_heartbeat_worker`
- `_shutdown_run_logging`

Why move:
- these are part of the operational production runner
- they should not live in the same file as legacy cells if the goal is a clean production entrypoint

### C. Shared production config block
Move only the supported production config:
- `RUN_MULTI_REGIME_EXTENSION`
- `MULTI_REGIME_BUILD_REGIMES`
- `MULTI_REGIME_VALIDATE_REGIMES`
- `MULTI_REGIME_FORCE_FULL_REBUILD`
- `MULTI_REGIME_SMOKE_MODE`
- `MULTI_REGIME_SMOKE_START`
- `MULTI_REGIME_SMOKE_END`
- `MULTI_REGIME_RUN_OPTIMIZATION`
- `MULTI_REGIME_RUN_HELPERS`
- `MULTI_REGIME_RUN_VALIDATION`

and shared config bindings:
- `MULTI_REGIME_PIPELINE_ARTIFACT_VERSION`
- `MULTI_REGIME_THRESHOLDS_BY_TF`
- `MULTI_REGIME_DISTANCE_WINDOWS_BY_TF`
- `MULTI_REGIME_BREAKOUT_THRESHOLD`
- `MULTI_REGIME_RISK_RATIO`
- `MULTI_REGIME_BREAKFREE_THRESHOLD_1M`

Why move:
- this is the real production config surface
- it should be readable in one place without scrolling through notebook history

### D. The production runner itself
Move:
- `_is_interactive_kernel()` only if we still want notebook-aware behavior
- `run_supported_multi_regime_pipeline()`
- the `__main__` launch behavior

Why move:
- this is the actual supported HTF execution path

## What Must Not Move

These belong to legacy/debug scope and should stay in `htf_pythonscript.py`:

- Cells `1-13`
- legacy artifact constants
- legacy feature/label/helper/validation code
- legacy notebook replay toggles:
  - `RUN_LEGACY_NOTEBOOK_CELLS`
  - `ENABLE_5M_PIPELINE`
  - old notebook-specific globals
- legacy imports from:
  - `htf_artifact_utils`
  - `htf_kernels`

Important:
- the new production file does **not** need those shared-kernel imports directly
- those are used by the shared pipeline module and by legacy notebook code, not by the thin production launcher itself

## The Clean Target Architecture

### `notebooks/mtf_htf_workflow.py`
Should become:
- a production-only entrypoint
- no legacy cells
- no legacy notebook replay mode
- no `5m` legacy flow

Minimal structure:

1. module docstring
2. imports
3. `resolve_project_root()`
4. runtime/logging helpers
5. production config block
6. `run_mtf_htf_workflow()`
7. `if __name__ == \"__main__\":`

### `notebooks/htf_pythonscript.py`
Should become one of:

Option A:
- keep as legacy notebook only
- remove production launch responsibility entirely

Option B:
- keep a tiny deprecation wrapper at top that tells users to use `mtf_htf_workflow.py`
- keep the old notebook body only for manual legacy/debug use

Safer first move:
- Option B

Why:
- lower disruption
- preserves old references while making the new production path explicit

## Recommended Migration Order

### Step 1. Create the new production file without changing behavior
Implement `mtf_htf_workflow.py` as a clean copy of the current production path only.

Rules:
- no legacy imports
- no legacy cells
- no interactive short-circuit complexity
- plain script behavior only

### Step 2. Validate the new file in isolation
Checks:
- `py_compile`
- dry startup with production disabled if needed
- confirm log/status paths are created correctly
- confirm it calls the same shared pipeline with the same config values

### Step 3. Point `htf_pythonscript.py` away from production ownership
Make it explicit that:
- supported production run = `mtf_htf_workflow.py`
- `htf_pythonscript.py` = legacy/debug notebook

### Step 4. Re-run the production workflow only through the new file
After that:
- stop using `htf_pythonscript.py` as the production launcher

## Do Not Repeat These Problems

### 1. Do not copy notebook baggage into the new file
The new file should not inherit:
- legacy globals
- legacy validation
- legacy comments
- compatibility wrappers that only exist for notebook replay

### 2. Do not add dual-path execution logic
The new file should not try to be:
- notebook
- legacy debug runner
- production script

It should be only:
- production script

### 3. Do not make the new file depend on cell order
No `globals()` fallbacks
No “if defined above” style behavior
No notebook replay assumptions

## The Exact Move Scope

### Move now
- production launcher/runtime surface only

### Leave behind
- all legacy workflow logic

### Revisit later
- whether to split logging/runtime helpers into a reusable module under `scripts/feature_engineering/`

That extraction is optional.
For the first clean migration, keeping them inside `mtf_htf_workflow.py` is acceptable and simpler.

## Bottom Line
The correct first move is **not** to keep untangling production inside `htf_pythonscript.py`.

The correct move is:
- build a clean production-only launcher in `mtf_htf_workflow.py`
- copy only the current supported runtime surface
- leave legacy/debug notebook behavior in `htf_pythonscript.py`

This is the smallest change that removes the ownership ambiguity at the root.
