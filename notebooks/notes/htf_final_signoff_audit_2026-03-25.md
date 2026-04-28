# HTF Final Sign-Off Audit

Date: 2026-03-25

## Scope
Verify the last open unification sign-off condition from
`notebooks/notes/htf_unification_execution_checklist.md`:

- `Notebook no longer contains duplicate production logic for shared scope`

This audit does not ask whether legacy compatibility wrappers still exist. It
asks whether those wrappers remain part of the supported production execution
path.

## Evidence

### 1. Supported production execution short-circuits into the shared runner

In `notebooks/htf_pythonscript.py`:

- the supported runner is defined at `run_supported_multi_regime_pipeline()`
- normal script execution checks `_should_short_circuit_to_supported_production()`
- when true, it runs the shared `CELL 14` path and immediately exits with
  `SystemExit(0)`

Key lines:

- `notebooks/htf_pythonscript.py:377-450`
- `notebooks/htf_pythonscript.py:453-464`

Meaning:

- normal `python notebooks/htf_pythonscript.py` execution uses the shared
  multi-regime engine only
- the legacy notebook body below that point is not part of the supported
  production path

### 2. Remaining notebook-local wrappers all live below the short-circuit

The remaining artifact/control wrappers and compatibility kernel names are
defined later in the file:

- artifact/control wrappers begin at `notebooks/htf_pythonscript.py:582`
- kernel compatibility shims appear later, including:
  - `_compute_past_distance_metrics`
  - `compute_distance_metrics`
  - `compute_4class_labels`
  - `compute_hybrid_distance_metrics`

Meaning:

- these definitions are inside the retained legacy/debug island
- they are not part of supported production execution because the script exits
  before reaching them in the normal path

### 3. Remaining wrappers are legacy-only compatibility shims

The notebook already documents that these wrappers are retained only for:

- legacy/back-compat notebook replay
- interactive debugging
- legacy `5m`
- phase-1 compatibility during unification

Relevant section:

- `notebooks/htf_pythonscript.py:471-580`

### 4. Shared production authority is already elsewhere

The actual supported production compute/control/validation authority now lives
in shared modules:

- `scripts/feature_engineering/htf_multiregime_pipeline.py`
- `scripts/feature_engineering/htf_artifact_utils.py`
- `scripts/feature_engineering/htf_kernels.py`
- `scripts/feature_engineering/htf_shared_config.py`

## Verdict

The final sign-off condition is satisfied.

`notebooks/htf_pythonscript.py` still contains retained legacy compatibility
wrappers, but it no longer contains duplicate production logic for the shared
scope in the supported execution path.

Therefore:

- final unification sign-off is not blocked by wrapper removal
- wrapper removal is a deferred legacy-cleanup task, not an active production
  unification blocker

## Follow-Up Classification

Deferred, non-blocking cleanup:

- remove notebook-local compatibility wrappers only if and when legacy notebook
  replay requirements are retired
- do not bundle that cleanup into the completed production unification sign-off
