# `htf_pythonscript.py` Runtime Report - 2026-03-18

## Purpose

This report documents how [htf_pythonscript.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py) works **today**, from top to bottom.

The focus is:

- execution order when the script is run end to end
- modules it imports and relies on
- which parts are self-contained inside the notebook
- which parts delegate to shared code modules
- what each major stage reads, computes, and writes

This is a runtime/reference report for the current script, not a redesign document.

## Completeness Notes

This report was cross-checked against the current notebook file on
2026-03-18.

One important reading rule:

- this file is a notebook-export style script, so many cells re-import modules,
  redefine paths, and restate constants so they can run independently

When executed as one script, those later redefinitions become part of the live
global state. That is why this report describes both:

- the logical stage flow
- and the notebook-style standalone-cell behavior that still exists inside the
  file

## Core Fact

When [htf_pythonscript.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py) is run as a script, it executes **all cells sequentially**.

That means the current runtime flow is:

1. legacy `8h` pipeline cells `1-13`
2. then `CELL 14`, which launches the shared multi-regime pipeline for `8h`, `24h`, and `7d`

So today this file is both:

- a legacy HTF compute implementation
- a production wrapper around the newer shared multi-regime engine

## Runtime Layers

The script uses three layers of logic.

### 1. Notebook-owned runtime/orchestration layer

This lives directly in [htf_pythonscript.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py) and includes:

- path resolution
- directory creation
- log/status files
- heartbeat thread
- artifact metadata helpers
- family/path scope helpers
- legacy stage implementations

### 2. Shared compute modules used by the notebook

These are imported and used directly:

- [compute_htf_features.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/compute_htf_features.py)
- [optimize_htf_features.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/optimize_htf_features.py)
- [htf_helper_cache.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_helper_cache.py)
- [htf_multiregime_pipeline.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py)

### 3. Shared modules that are *not* directly imported here but are used transitively

These are used through imported modules:

- analysis optimizer internals used by `optimize_htf_features.py`
- helper model modules used by `htf_helper_cache.py`
- fetched-source loading logic used by `HTFFeatureEngine`
- rolling rank-winsorize transformer internals used by the optimizer path

## Module Inventory

## Standard library modules

Imported directly in the notebook:

- `gc`
- `os`
- `hashlib`
- `json`
- `shutil`
- `sys`
- `time`
- `atexit`
- `builtins`
- `threading`
- `datetime`
- `timedelta`
- `pathlib.Path`
- `typing.Any`
- `importlib`

These support:

- run logging and lifecycle
- fingerprinting
- file cleanup
- dynamic module reloads
- runtime path injection
- elapsed-time/status reporting
- repeated cell-local setup blocks

## Third-party data stack

Imported directly in the notebook:

- `polars`
- `numpy`
- `pandas`
- `numba` with safe fallback if unavailable

Role by library:

- `polars`: parquet IO, joins, batch scans, validations
- `numpy`: array kernels for metrics and labels
- `pandas`: feature-engine input/output dataframe path
- `numba`: acceleration for notebook-local metric/label kernels

Important detail:

- `numba` is imported with a safe local fallback in multiple cells, not once at
  the file top
- this keeps the script portable, but if `numba` is missing, several legacy
  metric/label kernels still run in pure Python and can become much slower

## Shared project modules imported directly by this script

### Feature engine

Imported in `CELL 5`:

- [compute_htf_features.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/compute_htf_features.py)

Used via:

- `HTFFeatureEngine`

Notebook lines:

- [htf_pythonscript.py:1553](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L1553)
- [htf_pythonscript.py:1556](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L1556)
- [htf_pythonscript.py:1656](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L1656)

### Optimizer

Imported in `CELL 10`:

- [optimize_htf_features.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/optimize_htf_features.py)

Used via:

- `HTFOptimizationConfig`
- `optimize_htf_features`

Notebook lines:

- [htf_pythonscript.py:5130](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L5130)
- [htf_pythonscript.py:5133](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L5133)
- [htf_pythonscript.py:5193](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L5193)

### Helper cache / helper materialization

Imported in `CELL 11`:

- [htf_helper_cache.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_helper_cache.py)

Used via:

- `DEFAULT_HELPER_NAMES`
- `build_helper_cache_exact`
- `materialize_helpers_from_cache`

Notebook lines:

- [htf_pythonscript.py:5245](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L5245)
- [htf_pythonscript.py:5319](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L5319)
- [htf_pythonscript.py:5444](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L5444)

### Shared multi-regime production engine

Imported in `CELL 14`:

- [htf_multiregime_pipeline.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py)

Used via:

- `MultiRegimeHTFConfig`
- `run_multi_regime_htf_pipeline`

Notebook lines:

- [htf_pythonscript.py:6465](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L6465)
- [htf_pythonscript.py:6468](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L6468)
- [htf_pythonscript.py:6523](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L6523)

## Top-to-Bottom Runtime Flow

## 1. Bootstrap and runtime logging

Sections:

- [htf_pythonscript.py:41](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L41)
- [htf_pythonscript.py:218](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L218)

What happens:

- resolves repo root
- defines all major data directories
- creates output directories
- creates one run log file and one live status JSON file
- monkey-patches `print()` to tee into the run log
- starts heartbeat thread
- sets global pipeline version / artifact-version tags
- defines active legacy scope lists and family scope maps
- exposes stage/status helpers:
  - `set_run_stage`
  - `log_loop_progress`
  - `multi_regime_progress_callback`

What this stage uses:

- standard library only
- `polars` only for later helpers defined in the same bootstrap block

## 2. Artifact utility layer

Sections:

- [htf_pythonscript.py:359](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L359)
- [htf_pythonscript.py:417](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L417)
- [htf_pythonscript.py:540](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L540)

What happens:

- defines family scope lookup for legacy `B` and `C`
- defines metadata columns shared across stages
- defines file fingerprinting
- defines schema inspection
- defines artifact rebuild-reason logic
- defines stage metadata payload format

What this stage uses:

- `hashlib`
- `json`
- `shutil`
- `polars`

This logic is used by:

- combined generation
- features
- labels
- helper cache/materialization

## 3. Legacy combined generation

Sections:

- [htf_pythonscript.py:629](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L629)
- [htf_pythonscript.py:825](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L825)
- [htf_pythonscript.py:1077](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L1077)

What happens:

- reads fetched OHLCV from `fetchingByBit/sorted-{tf}-bybit-linear`
- filters to runtime date range
- inspects raw/combined freshness before deciding whether rebuild is needed
- assigns legacy `8h` batch IDs
- writes:
  - `data/htf_backtest/{tf}_HTF_combined.parquet`
- builds shifted family `C` by remapping base family `B`
- writes:
  - `data/htf_backtest_shift4h/{tf}_HTF_combined.parquet`

What this stage uses:

- notebook-local logic only
- `polars`
- artifact helpers from bootstrap

External shared module usage:

- none

Important detail:

- this script does **not** fetch data itself
- it assumes the `fetchingByBit/...` trees already exist and are sufficiently
  fresh before HTF preparation starts

## 4. Legacy batch validation

Section:

- [htf_pythonscript.py:1360](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L1360)

What happens:

- validates batch alignment and basic combined-file consistency

What this stage uses:

- notebook-local validation logic
- `polars`

## 5. Legacy feature engineering

Sections:

- [htf_pythonscript.py:1518](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L1518)
- [htf_pythonscript.py:1602](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L1602)

What happens:

- dynamically reloads [compute_htf_features.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/compute_htf_features.py)
- creates `HTFFeatureEngine`
- discovers available fetched auxiliary sources
- loads continuous combined data for `1m` and `15m`
- optionally augments input with:
  - mark/index/premium
  - open interest
  - long/short ratio
  - funding
- computes engine features
- computes notebook-local `D_*` past-distance features with `_compute_past_distance_metrics`
- rejoins metadata
- splits to per-batch parquet files
- writes `_build_meta.json` with schema/fingerprint/incremental-scope details

What this stage uses:

- shared module:
  - `HTFFeatureEngine`
- notebook-local code:
  - incremental batch selection
  - `D_*` feature kernel
  - batch splitting and metadata writing

Inputs:

- `data/htf_backtest/*.parquet`
- `fetchingByBit/...`

Outputs:

- `data/htf_features/{tf}/batch_XXXX.parquet`
- `data/htf_features/{tf}/_build_meta.json`

## 6. Shifted-family feature materialization

Section:

- [htf_pythonscript.py:2073](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L2073)

What happens:

- backfills missing family metadata into base feature batches if needed
- builds `shift4h` feature batches for family `C`
- reuses base family `B` feature rows by exact `timestamp`
- joins shifted family metadata from shifted combined files
- writes shifted feature metadata

What this stage uses:

- notebook-local code
- `polars`
- artifact metadata helpers

External shared module usage:

- none beyond earlier feature generation output

## 7. Legacy feature validation

Section:

- [htf_pythonscript.py:2224](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L2224)

What happens:

- validates feature batch presence, row counts, and structure

What this stage uses:

- notebook-local validation code
- `polars`

## 8. Legacy distance metrics for labeling

Section:

- [htf_pythonscript.py:2498](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L2498)

What happens:

- computes per-bar future-path distance metrics for `15m` and legacy `5m`
- computes batch aggregates and summary JSON
- uses notebook-local numba kernels:
  - `compute_distance_metrics`
  - `compute_4class_label_numba`
  - `compute_4class_labels_batch`

What this stage uses:

- notebook-local compute kernels
- `numpy`
- `polars`
- `numba`

Outputs:

- `data/htf_backtest/{tf}_distance_metrics.parquet`
- `data/htf_backtest/{tf}_batch_stats.parquet`
- `data/htf_backtest/distance_metrics_summary.json`

Important detail:

- this cell redefines several local paths and constants so it can run
  standalone
- when the whole file is executed, those definitions become part of the live
  global state for later legacy cells unless those later cells use their own
  local constants

## 9. Legacy `15m` labels

Section:

- [htf_pythonscript.py:3125](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L3125)

What happens:

- loads distance metrics
- computes `target_4class`
- computes `target_breakfree`
- gates labels to the first `4h` of each legacy `8h` batch
- writes per-batch label files for family `B`
- writes `_labels_meta.json`

What this stage uses:

- notebook-local `compute_4class_labels`
- notebook-local incremental label selection
- artifact metadata helpers

Outputs:

- `data/htf_4class_labels/15m/batch_XXXX.parquet`

## 10. Legacy shifted `15m` labels

Section:

- [htf_pythonscript.py:3648](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L3648)

What happens:

- computes shifted-family `15m` labels for family `C`
- writes shifted-family `_labels_meta.json`

What this stage uses:

- notebook-local logic
- `polars`

Outputs:

- `data/htf_4class_labels_shift4h/15m/batch_XXXX.parquet`

## 11. Legacy hybrid `5m` labels

Section:

- [htf_pythonscript.py:3938](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L3938)

What happens:

- defines notebook-local `compute_hybrid_distance_metrics`
- contains the legacy `5m` hybrid label flow

Important current fact:

- `ENABLE_5M_PIPELINE = False`, so this path is normally skipped

## 12. Legacy hybrid `1m` labels

Section:

- [htf_pythonscript.py:4396](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L4396)

What happens:

- loads `1m` combined and `15m` combined
- maps each `1m` row to a `15m` bar
- computes future-path distances using notebook-local `compute_hybrid_distance_metrics`
- computes `target_4class`
- computes `target_breakfree`
- gates to first `4h`
- writes per-batch labels for family `B`
- writes `_labels_meta.json`

What this stage uses:

- notebook-local hybrid metric kernel
- notebook-local `compute_4class_labels`
- `polars`
- `numpy`

Outputs:

- `data/htf_4class_labels/1m/batch_XXXX.parquet`

## 13. Legacy shifted hybrid `1m` labels

Section:

- [htf_pythonscript.py:4746](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L4746)

What happens:

- same hybrid `1m` label flow for shifted family `C`
- writes shifted-family `_labels_meta.json`

Outputs:

- `data/htf_4class_labels_shift4h/1m/batch_XXXX.parquet`

## 14. Optimization stage

Section:

- [htf_pythonscript.py:5100](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L5100)

What happens:

- dynamically reloads [optimize_htf_features.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/optimize_htf_features.py)
- builds optimization configs for families `B` and `C`
- runs only for `target_4class`

What this stage uses:

- shared optimizer module
- notebook-owned family run enumeration

Outputs:

- `data/htf_optimized/...`

## 15. Helper cache and helper materialization

Section:

- [htf_pythonscript.py:5212](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L5212)

What happens:

- imports shared helper-cache/materialization module
- builds helper cache namespaces:
  - `base_0h`
  - `shift4h`
- materializes helper columns onto optimized batches for families `B` and `C`
- writes helper cache metadata and final helper metadata

What this stage uses:

- shared helper functions:
  - `build_helper_cache_exact`
  - `materialize_helpers_from_cache`
- notebook-owned family iteration and local config values

Outputs:

- `data/htf_helper_cache/...`
- `data/htf_with_helpers/...`
- `data/htf_with_helpers_shift4h/...`

## 16. Split helpers back to batches

Section:

- [htf_pythonscript.py:5496](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L5496)

What happens:

- verifies or re-splits helper outputs when combined helper files exist

Important current detail:

- with `WRITE_HELPERS_COMBINED = False`, most helper outputs are already written
  directly in `CELL 11`, so `CELL 12` is mainly verification/backfill rather
  than the primary helper writer

What this stage uses:

- notebook-local orchestration
- `polars`

## 17. Legacy end-to-end validation

Section:

- [htf_pythonscript.py:5661](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L5661)

What happens:

- runs a notebook-local validation suite across:
  - combined
  - labels
  - optimized
  - helpers
  - cross-family consistency

If failures exist, it raises `AssertionError`.

What this stage uses:

- notebook-local validator functions
- `polars`

## 18. Shared multi-regime production pipeline

Section:

- [htf_pythonscript.py:6439](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L6439)

What happens:

- dynamically reloads [htf_multiregime_pipeline.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py)
- builds `MultiRegimeHTFConfig`
- runs:
  - `8h`
  - `24h`
  - `7d`
- runs:
  - combined
  - features
  - `15m` metrics
  - `1m` labels
  - optimization
- helpers
- validation

Default toggles currently set in the file:

- `RUN_MULTI_REGIME_EXTENSION = True`
- `MULTI_REGIME_BUILD_REGIMES = ("8h", "24h", "7d")`
- `MULTI_REGIME_FORCE_FULL_REBUILD = False`
- `MULTI_REGIME_RUN_OPTIMIZATION = True`
- `MULTI_REGIME_RUN_HELPERS = True`
- `MULTI_REGIME_RUN_VALIDATION = True`

What this stage uses:

- fully shared multi-regime engine
- notebook passes progress callback and config only

Outputs:

- `data/htf_*`
- `data/htf_*_24h`
- `data/htf_*_24h_shift12h`
- `data/htf_*_7d`
- `data/htf_*_7d_shift84h`

## What Is Notebook-Local vs Shared Today

## Notebook-local compute logic

Still implemented directly in this file:

- combined generation for legacy `8h`
- shifted combined generation for legacy `shift4h`
- `_compute_past_distance_metrics`
- `compute_distance_metrics`
- `compute_4class_labels`
- `compute_hybrid_distance_metrics`
- legacy `15m` label materialization
- legacy `1m` hybrid label materialization
- legacy validation suite

## Shared compute logic used by the notebook

Imported from modules:

- feature-engine source loading and feature generation
- optimization
- helper cache generation
- helper materialization
- full shared multi-regime pipeline

What is notably **not** yet fully shared:

- legacy combined generation
- legacy distance metrics
- legacy `15m` and hybrid `1m` label materialization
- legacy validation

## Current Authority Boundary

Today this script itself states:

- cells `1-13` are legacy
- `CELL 14` is the authoritative multi-regime pipeline

That means the current script works in two modes at once:

- legacy direct implementation
- shared delegated implementation

Operationally, if the whole script is run, **both happen**.

## External Data and Files This Script Uses

## Reads

- fetched raw data from `fetchingByBit/...`
- existing combined/features/labels/optimized/helper artifacts under `data/...`
- shared Python modules under `scripts/feature_engineering/...`

## Writes

- combined HTF parquet files
- feature parquet batches
- label parquet batches
- optimized feature batches
- helper cache batches
- helper-enriched batches
- validation outputs
- run log and status files under `test_output/htf_run_logs`

## Important Runtime Behaviors

### Dynamic reloads

The script uses `importlib.reload(...)` before:

- feature engine module
- optimization module
- shared multi-regime module

This means the script tries to pick up current code changes without restarting the kernel/process.

It also means the runtime behavior depends on the currently installed source
files at execution time, not only on what was originally imported when the
process began.

### Numba fallback

The notebook defines local no-op `njit` fallbacks in multiple cells if `numba` is unavailable.

This keeps the script runnable in weak environments, but much slower.

### Shared modules are not used uniformly

The script does **not** delegate every stage to shared modules yet.

That is why both:

- notebook-local compute
- shared multi-regime compute

still coexist.

## Bottom-Line Description

`htf_pythonscript.py` today is:

1. a runtime harness
2. a legacy `8h` HTF pipeline implementation
3. a wrapper around the newer shared multi-regime production engine

If someone asks, “what code does this script use while working?”, the answer is:

- it uses its **own internal code** for most legacy combined/features/labels/validation stages
- it uses **shared modules** for:
  - feature engine internals
  - optimization
  - helper cache/materialization
  - the full multi-regime path in `CELL 14`

It also repeatedly reloads those shared modules at stage boundaries so fresh
code edits can be picked up during a new script run.

So this file is currently the main operational entrypoint, but not yet a thin wrapper.

## Most Important Practical Takeaway

If the goal is to understand this script exactly as it works now:

- read it as a **two-layer script**
- first layer: legacy notebook-owned HTF pipeline
- second layer: delegated shared multi-regime pipeline

That dual structure is the main architectural fact to keep in mind before changing anything.
