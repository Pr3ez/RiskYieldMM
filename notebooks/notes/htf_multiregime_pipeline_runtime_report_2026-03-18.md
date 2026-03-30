# `htf_multiregime_pipeline.py` Runtime Report - 2026-03-18

## Purpose

This report documents how
[htf_multiregime_pipeline.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py)
works **today**, from top to bottom.

The focus is:

- execution order when `run_multi_regime_htf_pipeline(...)` is called
- modules it imports and relies on
- which parts are self-contained inside this shared engine
- which parts delegate to other shared modules
- what each major stage reads, computes, validates, and writes

This is a runtime/reference report for the current module, not a redesign
document.

## Completeness Notes

This report was cross-checked against the current shared pipeline file on
2026-03-18.

One important reading rule:

- this file is a pure engine module, not a notebook-export script
- it does not own Bybit/raw data fetching
- it does not own the outer notebook heartbeat/log-file runtime harness
- it expects a configured `MultiRegimeHTFConfig` and already-fetched raw parquet
  trees under `fetchingByBit`

That is why this report focuses on:

- regime/family abstraction
- stage orchestration
- artifact invalidation
- compute kernels
- shared-module delegation

Completeness rule used for this report:

- every workflow-owning stage and every behavior-shaping utility cluster is
  covered explicitly
- very small helper functions are grouped under the layer they influence rather
  than each receiving a standalone subsection

## Core Fact

When
[run_multi_regime_htf_pipeline()](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L2787)
is called, this module executes one unified HTF materialization flow for:

- regimes `8h`, `24h`, `7d`
- families `B` and `C`
- upstream timeframes `1m` and `15m`

The current runtime flow is:

1. initialize shared feature-engine context
2. build/refresh combined artifacts for `B` and `C`
3. build/refresh feature batches
4. build/refresh `15m` distance metrics
5. build/refresh `1m` labels
6. run optimization for `1m / target_4class`
7. build helpers from cache plus optimized batches
8. run regime validation

So today this file is the **shared production HTF engine**, while
[htf_pythonscript.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py)
is the outer runtime wrapper that can call it.

## Runtime Layers

The module uses four layers of logic.

### 1. Shared engine-owned orchestration layer

This lives directly in
[htf_multiregime_pipeline.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py)
and includes:

- regime configuration
- stage ordering
- progress/event emission
- artifact invalidation and metadata
- combined-batch generation
- feature batching
- distance metric generation
- label generation
- helper-cache selection
- regime validation

### 2. Shared compute kernels owned by this module

These still live directly in this file:

- [compute_distance_metrics()](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L355)
- [compute_hybrid_distance_metrics()](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L414)
- [_compute_past_distance_metrics()](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L476)
- [compute_4class_labels()](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L507)

These are important because they still overlap conceptually with legacy
notebook-local kernels and therefore matter for later unification work.

### 3. Shared modules delegated to by this engine

These are imported and used directly:

- [compute_htf_features.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/compute_htf_features.py)
  via lazy import in
  [_init_feature_engine()](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L1393)
- [optimize_htf_features.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/optimize_htf_features.py)
  via lazy import in
  [_run_optimization()](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L2310)
- [htf_helper_cache.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_helper_cache.py)
  via direct import at file top and usage in
  [_build_helpers()](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L2348)

### 4. Transitively used lower-level modules

These are used through the delegated modules:

- fetched-source loading and broadcast logic from `HTFFeatureEngine`
- optimizer internals including rolling-rank-winsorize transformers
- helper model modules called through `htf_helper_cache.py`

## Module Inventory

## Standard library modules

Imported directly:

- `gc`
- `hashlib`
- `json`
- `shutil`
- `sys`
- `time`
- `dataclasses`
- `datetime`
- `timedelta`
- `timezone`
- `pathlib.Path`
- `typing.TYPE_CHECKING`
- `typing.Any`
- `typing.Callable`

These support:

- artifact fingerprints
- metadata IO
- runtime progress/log timing
- directory cleanup
- dataclass-based config
- delayed/shared typing

## Third-party data stack

Imported directly:

- `numpy`
- `pandas`
- `polars`
- `numba` with safe fallback if unavailable

Role by library:

- `numpy`: array kernels for metrics and labels
- `pandas`: feature-engine compute path
- `polars`: parquet IO, joins, scans, validation
- `numba`: acceleration for shared metric/label kernels

Important detail:

- `numba` is imported once at module top with a safe fallback
- if `numba` is missing, shared kernels still work but can become much slower

## Shared project modules imported directly by this script

### Helper cache / helper materialization

Imported at module top:

- [htf_helper_cache.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_helper_cache.py)

Used via:

- `DEFAULT_HELPER_NAMES`
- `build_helper_cache_exact`
- `materialize_helpers_from_cache`

Module lines:

- [htf_multiregime_pipeline.py:28](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L28)
- [htf_multiregime_pipeline.py:2348](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L2348)

### Feature engine

Imported lazily in:

- [_init_feature_engine()](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L1393)

Used via:

- `HTFFeatureEngine`

This lazy import keeps the shared engine usable for lightweight validation or
inspection without importing the full feature-engine stack until needed.

### Optimizer

Imported lazily in:

- [_run_optimization()](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L2310)

Used via:

- `HTFOptimizationConfig`
- `optimize_htf_features`

This keeps optimization optional at runtime and reduces import cost when only
combined/features/labels are needed.

## Top-to-Bottom Runtime Flow

## 1. Regime and stage configuration layer

Sections:

- [htf_multiregime_pipeline.py:50](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L50)
- [htf_multiregime_pipeline.py:58](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L58)
- [htf_multiregime_pipeline.py:82](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L82)
- [htf_multiregime_pipeline.py:143](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L143)

What happens:

- defines `BatchRegimeConfig`
- defines `REGIME_CONFIGS` for `8h`, `24h`, `7d`
- defines active HTF scope constants:
  - `TF_MINUTES`
  - `DISTANCE_TIMEFRAMES`
  - `UPSTREAM_TIMEFRAMES`
  - `TARGET_TIMEFRAMES`
  - `SOURCE_AUGMENTED_FEATURE_TFS`
  - `HELPER_NAMES`
- defines runtime control constants used later by metrics and labels:
  - `MIN_REMAINING_15M`
  - `MIN_REMAINING_1M_FROM_15M`
  - `BB_PERIOD`
  - `BB_STD`
  - `OUTLIER_PERCENTILE`
- defines output-root naming compatibility:
  - `BASE_SCOPE_NAMES`
  - `LEGACY_8H_SHIFT_NAMES`
- defines family metadata columns and combined output columns
- defines `MultiRegimeHTFConfig`, which controls:
  - build regimes
  - artifact invalidation behavior
  - feature incremental windows
  - label incremental windows
  - helper/cache settings
  - optimization/helper/validation toggles
  - smoke/date filters
  - progress callback

What this stage uses:

- standard library
- module-level constants only

Important detail:

- `BASE_SCOPE_NAMES` and `LEGACY_8H_SHIFT_NAMES` are what preserve the legacy
  `8h/B` and `8h/C` artifact layout even though this is now a multi-regime
  engine
- `MIN_REMAINING_15M` and `MIN_REMAINING_1M_FROM_15M` are hard gates used later
  in the label/metric validity rules
- `BB_PERIOD`, `BB_STD`, and `OUTLIER_PERCENTILE` are not cosmetic constants;
  they directly shape the distance-metric and `D_*` feature calculations

## 2. Progress and event-emission layer

Sections:

- [htf_multiregime_pipeline.py:244](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L244)
- [htf_multiregime_pipeline.py:298](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L298)

What happens:

- formats elapsed time
- stringifies progress detail values
- emits structured progress callbacks
- logs stage start/done summaries
- emits periodic batch-progress events

This is the bridge used by the notebook runtime wrapper. The outer notebook can
pass `progress_callback`, but the shared engine itself owns the stage semantics.

## 3. Shared compute-kernel layer

Sections:

- [htf_multiregime_pipeline.py:355](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L355)
- [htf_multiregime_pipeline.py:414](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L414)
- [htf_multiregime_pipeline.py:476](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L476)
- [htf_multiregime_pipeline.py:507](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L507)

What happens:

- `compute_distance_metrics(...)` computes forward-path price excursion metrics
  on a single timeframe
- `compute_hybrid_distance_metrics(...)` computes `1m` entry vs `15m`
  remaining-path metrics inside the same regime batch
- `_compute_past_distance_metrics(...)` computes the custom causal `D_*`
  batch-local past-distance features
- `compute_4class_labels(...)` turns forward-path metrics into the 4-class HTF
  label

What this stage uses:

- `numpy`
- `numba`

This kernel layer is central to both validation and later unification because
it encodes the actual label/feature math, not just orchestration.

## 4. Artifact utility and rebuild-decision layer

Sections:

- [htf_multiregime_pipeline.py:533](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L533)
- [htf_multiregime_pipeline.py:709](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L709)
- [htf_multiregime_pipeline.py:833](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L833)

What happens:

- fingerprints source files and batch directories
- loads/writes stage metadata
- inspects expected vs current schema
- finds missing required columns
- computes rebuild reasons from:
  - artifact version drift
  - source fingerprint drift
  - schema column drift
  - missing metadata
  - missing batch files
- prepares stage run mode:
  - `current`
  - `incremental_tail`
  - `full`

Key helper functions in this layer:

- `_artifact_meta_payload(...)` builds the normalized metadata JSON payload used
  across stages
- `_prepare_stage_rebuild(...)` centralizes destructive vs incremental rebuild
  decisions
- `_output_stats(...)` summarizes existing artifacts for current/skip decisions
- `_stage_meta(...)` builds regime/family-aware stage metadata fingerprints for
  helper/cache and related stages

What this stage uses:

- `hashlib`
- `json`
- `shutil`
- `polars`

This is the shared replacement for notebook-local artifact invalidation logic.

## 5. Regime/family abstraction layer

Sections:

- [htf_multiregime_pipeline.py:876](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L876)
- [htf_multiregime_pipeline.py:911](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L911)

What happens:

- maps regime/family to data roots via `_family_scope(...)`
- maps timeframe to raw fetched directories via `_raw_dir_for_tf(...)`
- resolves helper-cache root via `_helper_cache_root(...)`
- selects helper-cache namespace via `_helper_cache_source(...)`
- computes batch sizes, half-batch sizes, entry windows, anchor strings
- adds family metadata columns with `_add_family_metadata(...)`
- preserves legacy compatibility fields, especially `period_8h_start`

Important detail:

- `family B` uses unshifted base anchor
- `family C` uses regime-specific half-shift
- helper caches are split by source timeline namespace:
  - `base_0h`
  - `shift4h`
  - `shift12h`
  - `shift84h`

That means the module treats family/regime geometry as a first-class concept,
not just a naming convention.

## 6. Combined artifact build layer

Sections:

- [htf_multiregime_pipeline.py:1073](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L1073)
- [htf_multiregime_pipeline.py:1247](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L1247)

What happens:

- `_build_base_combined(...)`
  - reads raw parquet from `fetchingByBit`
  - applies smoke/date filters
  - normalizes timestamps
  - deduplicates on normalized timestamp, keeping the last row
  - computes regime-aligned batch periods from the configured anchor
  - attaches family metadata
  - writes per-timeframe combined parquet plus build metadata
  - can keep current output when raw input has not advanced materially
  - can return `current_no_raw` when raw input is missing but a valid existing
    combined artifact is already present
- `_build_shifted_combined(...)`
  - remaps family `B` combined into family `C`
  - preserves compatibility column naming
  - writes shifted combined parquet plus build metadata

What this stage reads:

- fetched raw parquet trees under `raw_data_dir`
- existing combined parquet/meta if present

What this stage writes:

- regime/family combined parquet
- `_build_meta.json`

## 7. Feature build layer

Sections:

- [htf_multiregime_pipeline.py:1393](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L1393)
- [htf_multiregime_pipeline.py:1403](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L1403)
- [htf_multiregime_pipeline.py:1420](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L1420)
- [htf_multiregime_pipeline.py:1442](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L1442)
- [htf_multiregime_pipeline.py:1572](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L1572)

What happens:

- lazily initializes `HTFFeatureEngine`
- fingerprints both combined input and auxiliary fetched-source files
- computes the expected current feature schema
- isolates feature-value columns from metadata with `_feature_value_cols(...)`
- for family `C`, reuses base family feature rows by exact `timestamp` through
  `_build_shifted_feature_batches_from_base(...)`
- for family `B`:
  - loads continuous combined data
  - applies incremental context/tail logic
  - converts to pandas for the feature engine
  - for `1m` and `15m`, augments with fetched auxiliary sources
  - runs `compute_features(...)`
  - adds custom `D_*` past-distance features
  - rejoins OHLCV and family metadata
  - writes per-batch parquet plus build metadata

What this stage reads:

- combined parquet
- auxiliary fetched-source parquet discovered by `HTFFeatureEngine`
- existing feature batches/meta if present

What this stage writes:

- feature batch parquet per regime/family/timeframe
- `_build_meta.json`

Important detail:

- this is the authoritative place where the richer `1m` and `15m` source-based
  feature expansion is applied
- `5m` is intentionally out of scope here

## 8. `15m` distance-metric layer

Section:

- [htf_multiregime_pipeline.py:1812](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L1812)

What happens:

- loads `15m` combined data
- determines full and last-partial valid batches
- decides incremental vs full rebuild
- computes Bollinger-band columns
- computes forward-path distance metrics with `compute_distance_metrics(...)`
- upserts rebuilt rows into the stage parquet
- writes stage metadata

What this stage writes:

- one metrics parquet per regime/family
- `_build_meta.json`

## 9. `1m` label layer

Section:

- [htf_multiregime_pipeline.py:1979](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L1979)

What happens:

- loads regime/family `1m` and `15m` combined data
- determines batches valid in both timeframes
- uses `_select_incremental_label_batches(...)` to derive:
  - target batches to rewrite
  - compute batches including one warmup batch before the earliest target
- chooses target batches incrementally when possible
- computes:
  - same-batch `close_end`
  - same-batch `end_return`
  - remaining `15m` future-path metrics
- creates:
  - `target_4class`
  - `target_breakfree`
- gates labels to the first half of the regime batch
- writes per-batch label parquet plus metadata

What this stage uses:

- `compute_hybrid_distance_metrics(...)`
- `compute_4class_labels(...)`

What this stage writes:

- `1m` label batches
- `_labels_meta.json`

Important detail:

- label semantics stay regime-aware but unchanged across regimes:
  - `target_4class` uses regime-matched remaining `15m` path
  - `target_breakfree` uses same-batch `1m` end close
- first-half validity is not hardcoded per regime; it is derived from
  `_entry_bar_limit(...)`, which itself depends on the regime config

## 10. Optimization layer

Section:

- [htf_multiregime_pipeline.py:2310](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L2310)

What happens:

- lazily imports the optimizer module
- builds `HTFOptimizationConfig`
- points it at the current regime/family feature and label roots
- runs optimization only for `1m / target_4class`

What this stage writes:

- optimized feature batches
- optimizer metadata/config artifacts created by the optimizer module

Important detail:

- this module does not implement the optimizer math itself
- it only wires regime/family-specific directories into the shared optimizer

## 11. Helper layer

Section:

- [htf_multiregime_pipeline.py:2348](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L2348)

What happens:

- selects helper cache namespace for the regime/family
- builds or resumes exact helper cache using
  `build_helper_cache_exact(...)`
- materializes final helper outputs onto optimized batches using
  `materialize_helpers_from_cache(...)`
- writes helper metadata

What this stage reads:

- feature batches or cache inputs used by `htf_helper_cache.py`
- optimized batches
- existing helper cache/meta and final helper artifacts

What this stage writes:

- helper cache artifacts
- final helper batch parquet
- helper metadata

Important detail:

- this module owns the helper-cache selection policy, not the helper math
- helper math is delegated fully to `htf_helper_cache.py`

## 12. Validation layer

Sections:

- [htf_multiregime_pipeline.py:2484](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L2484)
- [htf_multiregime_pipeline.py:2492](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L2492)
- [htf_multiregime_pipeline.py:2514](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L2514)

What happens:

- validates period-start consistency
- validates anchor alignment
- validates rows-per-batch rules
- validates first-half label coverage
- validates regime-specific valid-row counts
- validates cross-family source mapping
- validates family `B` + `C` union coverage
- returns one validation dataframe for all checks

Important detail:

- the driver raises `AssertionError` if any validation row has `ok=False`
- this makes validation a hard correctness gate, not just a passive report

## 13. Driver/orchestrator layer

Section:

- [htf_multiregime_pipeline.py:2787](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L2787)

What happens:

- emits pipeline start event
- initializes feature engine once
- loops through configured regimes
- builds combined `B/C` for each upstream timeframe
- for each family:
  - builds features for `1m` and `15m`
  - builds `15m` metrics
  - builds `1m` labels
  - optionally runs optimization
  - optionally builds helpers
- optionally validates all configured regimes
- raises if validation fails
- returns a structured summary dictionary with stage results and validation

This function is the real runtime entrypoint for production HTF materialization.

## External Data and Artifact Contract

## What this module reads

- raw fetched parquet under `fetchingByBit/...`
- auxiliary fetched-source parquet discovered by `HTFFeatureEngine`
- existing combined, feature, metric, label, optimized, helper, and cache
  artifacts
- existing per-stage metadata JSON files

## What this module writes

- combined parquet trees
- feature parquet trees
- `15m` metric parquet
- `1m` label parquet trees
- optimization outputs through the optimizer module
- helper cache and final helper parquet trees
- stage metadata JSON files
- validation dataframe in returned memory object, not as a persistent file

## What this module does not do

- does not fetch raw market data itself
- does not own the outer run log/status JSON harness
- does not own notebook cell sequencing or notebook UI comments

Those concerns stay outside this module.

## What This Module Owns Versus Delegates

## Owned here

- regime geometry
- family geometry
- combined batch construction
- artifact invalidation policy
- feature-stage source/schema invalidation
- label gating semantics
- validation semantics
- helper-cache namespace selection
- overall production stage ordering

## Delegated

- generic HTF feature engineering to `HTFFeatureEngine`
- optimizer internals to `optimize_htf_features.py`
- helper math and cache/materialization internals to `htf_helper_cache.py`

## Important Runtime Behaviors

- `8h` compatibility is preserved intentionally:
  - legacy root names
  - `period_8h_start` compatibility column
- `C` families do not recompute features from raw; they reuse `B` by timestamp
- helper outputs are cache-backed and source-timeline aware
- richer fetched-source features for `1m` and `15m` are activated here
- labels are independent from feature-schema drift
- validation is hard-fail, not advisory

## Bottom-Line Description

[htf_multiregime_pipeline.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py)
is the shared production HTF engine.

It is already much closer to a unified implementation than
[htf_pythonscript.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py)
because it centralizes:

- regime/family abstraction
- rebuild/resume logic
- combined/features/metrics/labels/helpers/validation stage ordering

But it is not yet the **only** compute implementation in the repository,
because some important kernels and stage semantics still exist in parallel
inside the legacy notebook.

So the current architecture is:

- `htf_multiregime_pipeline.py` = shared production engine
- `htf_pythonscript.py` = runtime wrapper plus remaining legacy implementation

That is the key fact this report should contribute to future unification work.
