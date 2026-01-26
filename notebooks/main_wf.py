# %% [markdown]
# # RiskYieldMM ML Pipeline
#
# **Automated workflow for BTC perpetual futures prediction**
#
# ## Architecture Overview
#
# This notebook is the **main orchestration layer**. Heavy calculations are in modules.
#
# ```
# ┌─────────────────────────────────────────────────────────────────────────┐
# │                        PIPELINE OVERVIEW                                │
# ├─────────┬───────────────────────────────────────────────────────────────┤
# │ Step 0  │ Data Fetching & Aggregation (Bybit API → 8h bars)            │
# │ Step 1a │ Merge raw sources → merged_8h_raw.parquet                     │
# │ Step 1b │ Compute features → features_8h.parquet                        │
# │ Step 2  │ Generate targets → analysis_8h.parquet                        │
# │ Step 3  │ Feature optimization → features_8h_optimized_*.parquet        │
# │ Step 4  │ Build final datasets → data/datasets/*.parquet                │
# │ Step 5  │ IC/ICIR analysis → data/analysis/results/ic_*.csv             │
# │ Step 6  │ Feature importance → data/analysis/results/*_importance.csv   │
# │ Step 7  │ Cross-validation → data/analysis/results/cv_results.csv       │
# │ Step 8  │ L1 Precomputation → data/precomputed/{config}/               │
# │ Step 9  │ Dataset Assembly → data/precomputed/{config}/assembled.parquet│
# │ Step 10 │ L2 Backtest → data/l2_backtest_results/                       │
# └─────────┴───────────────────────────────────────────────────────────────┘
# ```
#
# ## Module Guide (scripts/workflow/)
#
# | Module | Purpose | When to Modify |
# |--------|---------|----------------|
# | `config.py` | Constants, defaults, WorkflowConfig | Add new config options, change defaults |
# | `data_fetching.py` | Step 0: fetch & aggregate | Change data sources, fetch logic |
# | `state_detection.py` | Staleness detection, sync checks | Add new file checks, change stale logic |
# | `validation.py` | Causality tests, pipeline verification | Add new validation tests |
# | `l1_helpers.py` | L1 precompute helpers | Modify iteration calculation, status checks |
#
# ## Where to Make Changes
#
# | Change Type | Location |
# |-------------|----------|
# | Add new target type | `config.py` → WORKFLOW_TARGETS |
# | Add new horizon | `config.py` → WORKFLOW_HORIZONS |
# | Change data freshness threshold | `config.py` → STALE_THRESHOLD_HOURS |
# | Modify fetch behavior | `data_fetching.py` → run_step0_fetch_and_aggregate() |
# | Add new staleness check | `state_detection.py` → get_data_status() |
# | Add new validation test | `validation.py` → new function, export in __init__.py |
# | Change L1 helpers list | `config.py` → L1_HELPERS |
# | Modify L1 iteration logic | `l1_helpers.py` → compute_feasible_iters() |
# | Add new pipeline step | This notebook + relevant module |
#
# ## Backup & Recovery
#
# - Original 1703-line version: `notebooks/main_wf_original_backup.py`
# - If modules break, can copy logic back from backup

# %%
# ============================================================================
# WORKSPACE SETUP
# ============================================================================
import os
import sys
from pathlib import Path

# HARDCODED to Copy workspace due to space in path name
PROJECT_ROOT = Path("/media/przem/linux_data/RiskYieldMM (Copy)")

if not PROJECT_ROOT.exists():
    raise FileNotFoundError(f"Workspace not found: {PROJECT_ROOT}")

os.chdir(PROJECT_ROOT)
sys.path.insert(0, str(PROJECT_ROOT))
# Add validation directory for backtest package imports
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "target_models" / "validation"))

print(f"Working dir: {os.getcwd()}")
print(f"✓ Workspace: {PROJECT_ROOT.name}")

# %%
# ============================================================================
# WORKFLOW CONFIGURATION
# ============================================================================
# MODIFY: scripts/workflow/config.py for persistent changes
# OVERRIDE: Uncomment lines below for one-time runs
#
# Available config options (from config.py):
#   WORKFLOW_HORIZONS  - List of bar horizons [1, 3, 6, 12]
#   WORKFLOW_TARGETS   - List of targets ["direction", "volatility", ...]
#   AUTO_FETCH_IF_STALE - Auto-fetch from Bybit when data is old
#   STALE_THRESHOLD_HOURS - Hours before data considered stale
#   L1_CONFIG_MODE     - "1bar", "reduced", or "all"
#   L1_ROWS            - Number of backtest iterations (None=auto)
#   L1_HELPERS         - List of helper names to use
#   EXPECTED_FEATURES  - Expected feature count (for validation)
# ============================================================================

from scripts.workflow.config import (
    AUTO_FETCH_IF_STALE,
    L1_CONFIG_MODE,
    L1_HELPERS,
    L1_ROWS,
    STALE_THRESHOLD_HOURS,
    WORKFLOW_HORIZONS,
    WORKFLOW_TARGETS,
    get_workflow_config,
)

# Optional: Override defaults for this run
# WORKFLOW_HORIZONS = [1, 3]  # Uncomment to process more horizons
# WORKFLOW_TARGETS = ["direction", "volatility"]  # Uncomment to limit targets

config = get_workflow_config()
config.print_summary()

# %% [markdown]
# # Step 0: Data Fetching & Aggregation
#
# **Automatic** - fetches new data from Bybit if current data is stale.
# Uses `fetchingByBit/update_data.py` which handles:
# 1. Incremental fetch from Bybit API (resumes from last point)
# 2. Aggregation from 4h → 8h timeframe
# 3. Data quality validation

# %%
# ----------------------------------------------------------------------------
# STEP 0 IMPLEMENTATION: scripts/workflow/data_fetching.py
# ----------------------------------------------------------------------------
# Functions:
#   run_step0_fetch_and_aggregate() - Main entry point
#   check_data_freshness()          - Check if data is stale
#   get_raw_8h_info()               - Get 8h parquet file info
#
# To modify data fetching behavior:
#   1. Change freshness logic → data_fetching.py::check_data_freshness()
#   2. Add new data sources → fetchingByBit/update_data.py
#   3. Change aggregation → fetchingByBit/aggregate_to_8h.py
# ----------------------------------------------------------------------------
from scripts.workflow.data_fetching import run_step0_fetch_and_aggregate

step0_success = run_step0_fetch_and_aggregate(
    project_root=PROJECT_ROOT,
    auto_fetch=AUTO_FETCH_IF_STALE,
    stale_threshold_hours=STALE_THRESHOLD_HOURS,
)

if not step0_success:
    print("\n⚠️ WARNING: Proceeding with potentially stale data!")

# Quality Gate: Verify data quality hasn't degraded
from scripts.workflow import run_quality_gate

run_quality_gate("step0_data", PROJECT_ROOT, threshold_pct=10.0, auto_halt=True)

# %%
# ============================================================================
# PIPELINE STATE MANAGEMENT
# ============================================================================
# Track data versions to detect when full recompute is needed.
#
# VERIFIED (2026-01-18): All optimizers are CAUSAL and incrementally resumable!
# - ExpandingRank: rank[i] uses only rows 0..i-1 (historical unchanged)
# - Winsorize: bounds from expanding quantiles with shift(1)
# - Interactions: standardization from expanding mean/std with shift(1)
#
# Recompute from scratch only when source data is CORRECTED (not just extended)
# or when pipeline code changes. Adding new rows does NOT change historical values.

# ----------------------------------------------------------------------------
# STATE DETECTION: scripts/workflow/state_detection.py
# ----------------------------------------------------------------------------
# Functions:
#   detect_new_data()       - Check if new rows added, returns (bool, row_count)
#   get_data_status()       - Get DataStatus with all file row counts
#   check_file_sync()       - Check single file against expected rows
#   check_optimized_files() - Check all optimized files exist and current
#
# DataStatus fields: raw_rows, merged_rows, features_rows, analysis_rows,
#                    new_data_detected, new_rows, sync_reason
#
# To add new staleness checks:
#   1. Add file check in get_data_status()
#   2. Update DataStatus dataclass if new field needed
#   3. Export in __init__.py if public
# ----------------------------------------------------------------------------
from scripts.analysis.pipeline_state import (
    PipelineState,
    compute_data_checksum,
    compute_schema_hash,
    print_pipeline_status,
)
from scripts.workflow.state_detection import detect_new_data

# Load pipeline state and detect changes
pipeline_state = PipelineState.load(PROJECT_ROOT)
print_pipeline_status(pipeline_state, PROJECT_ROOT)

NEW_DATA_DETECTED, current_raw_rows = detect_new_data(
    PROJECT_ROOT, pipeline_state, verbose=True
)

# %% [markdown]
# # Step 1: Feature Engineering
#
# Run `prepare_dataset.py` → `compute_features.py`
# These steps are ALWAYS rerun when new data is detected to ensure consistency.

# %%
# Step 1a: Merge raw data sources → merged_8h_raw.parquet
import polars as pl

from scripts.feature_engineering.prepare_dataset import (
    merge_all_sources,
    print_dataset_summary,
)

print("=" * 70)
print("STEP 1a: MERGE RAW DATA SOURCES")
print("=" * 70)

merged_file = PROJECT_ROOT / "data" / "merged_8h_raw.parquet"
SKIP_MERGE = False

if not NEW_DATA_DETECTED and merged_file.exists():
    merged_df = pl.read_parquet(merged_file)
    if len(merged_df) == current_raw_rows:
        print(f"✓ merged_8h_raw.parquet is current ({len(merged_df)} rows)")
        print("  Skipping merge (no new data)")
        SKIP_MERGE = True
        df_raw = merged_df.to_pandas()

if not SKIP_MERGE:
    data_dir = PROJECT_ROOT / "fetchingByBit"
    df_raw = merge_all_sources(data_dir)
    print_dataset_summary(df_raw)

    # Save
    df_raw.to_parquet(merged_file)
    print(f"\n✓ Saved: {merged_file}")

    # Update state
    pipeline_state.update_step(
        "merged_raw",
        row_count=len(df_raw),
        last_timestamp=str(df_raw["RAW_TM_timestamp"].max()),
        checksum=compute_data_checksum(df_raw),
        schema_hash=compute_schema_hash(df_raw),
    )
    pipeline_state.save(PROJECT_ROOT)

# %%
# Step 1b: Compute features → features_8h.parquet
from scripts.feature_engineering.compute_features import (
    compute_all_features,
    load_raw_data,
)

print("=" * 70)
print("STEP 1b: COMPUTE FEATURES")
print("=" * 70)

features_file = PROJECT_ROOT / "data" / "features_8h.parquet"
SKIP_FEATURES = False

if not NEW_DATA_DETECTED and features_file.exists():
    features_df_check = pl.read_parquet(features_file)
    if len(features_df_check) == current_raw_rows:
        print(f"✓ features_8h.parquet is current ({len(features_df_check)} rows)")
        print("  Skipping feature computation (no new data)")
        SKIP_FEATURES = True
        features_df = features_df_check.to_pandas()

if not SKIP_FEATURES:
    data_dir = PROJECT_ROOT / "fetchingByBit"
    df_for_features = load_raw_data(data_dir)
    print(f"Loaded raw data: {df_for_features.shape}")

    features_df = compute_all_features(df_for_features)
    print(f"Computed features: {features_df.shape}")

    # Save
    features_df.to_parquet(features_file)
    print(f"\n✓ Saved: {features_file}")

    # Update state
    pipeline_state.update_step(
        "features",
        row_count=len(features_df),
        last_timestamp=str(features_df["timestamp"].max()),
        checksum=compute_data_checksum(features_df),
        schema_hash=compute_schema_hash(features_df),
    )
    pipeline_state.save(PROJECT_ROOT)

# %%
# ----------------------------------------------------------------------------
# VALIDATION: scripts/workflow/validation.py
# ----------------------------------------------------------------------------
# Functions:
#   run_causality_test()       - Verify no future leakage in ExpandingRank
#   run_pipeline_verification() - Check all pipeline steps complete
#   verify_step1_features()    - Verify features_8h.parquet output
#   verify_step2_targets()     - Verify analysis_8h.parquet output
#   verify_step3_optimization() - Verify optimized files exist
#
# Result classes:
#   CausalityTestResult      - spike_test_passed, manual_verify_passed, etc.
#   PipelineVerificationResult - all_passed, checks list, details dict
#
# To add new validation tests:
#   1. Create function in validation.py
#   2. Return structured result (dataclass preferred)
#   3. Export in __init__.py
#   4. Call from this notebook where appropriate
# ----------------------------------------------------------------------------
from scripts.workflow.validation import verify_step1_features

verify_step1_features(PROJECT_ROOT)

# Quality Gate: Verify feature engineering metrics haven't degraded
run_quality_gate("step1_features", PROJECT_ROOT, threshold_pct=10.0, auto_halt=True)

# %% [markdown]
# # Step 2: Target Generation
#
# Generate `analysis_8h.parquet` with targets:
# - `y_direction_1bar`: Binary (1=up, 0=down)
# - `y_forward_return_{1,3,6,12}`: Multi-horizon returns
# - `y_volatility`: |forward_return_1|
# - `y_volatility_regime`: DECREASE/INCREASE (0/1)
# - `y_trend_regime`: SMA crossover

# %%
from scripts.analysis.data import create_analysis_dataset

print("=" * 70)
print("STEP 2: TARGET GENERATION")
print("=" * 70)

analysis_file = PROJECT_ROOT / "data" / "analysis_8h.parquet"
SKIP_ANALYSIS = False

if not NEW_DATA_DETECTED and analysis_file.exists():
    analysis_check = pl.read_parquet(analysis_file)
    if len(analysis_check) == current_raw_rows:
        print(f"✓ analysis_8h.parquet is current ({len(analysis_check)} rows)")
        print("  Skipping target generation (no new data)")
        SKIP_ANALYSIS = True
        df_analysis = analysis_check

if not SKIP_ANALYSIS:
    df_analysis = create_analysis_dataset()
    print(f"\n✓ Saved: {analysis_file}")

    # Update state
    pipeline_state.update_step(
        "analysis",
        row_count=len(df_analysis),
        last_timestamp=str(df_analysis.select("timestamp").max().item()),
        checksum=compute_data_checksum(df_analysis),
        schema_hash=compute_schema_hash(df_analysis),
    )
    pipeline_state.save(PROJECT_ROOT)

# %%
# Verify Step 2 output
from scripts.workflow.validation import verify_step2_targets

verify_step2_targets(PROJECT_ROOT)

# Quality Gate: Verify target distributions haven't degraded
run_quality_gate("step2_targets", PROJECT_ROOT, threshold_pct=10.0, auto_halt=True)

# %% [markdown]
# # Step 3: Feature Optimization
#
# Per-target feature optimization using optimization pipeline.
# Configs controlled by WORKFLOW_HORIZONS and WORKFLOW_TARGETS.
#
# **✅ CAUSAL & INCREMENTALLY RESUMABLE (Verified 2026-01-18)**
#
# All optimizers use expanding windows with `.shift(1)` — at row N, only
# rows 0..N-1 are used. Adding new rows does NOT change historical values.
#
# Verification tests confirmed:
# - ExpandingRank: rank[i] = count(rows 0..i-1 <= value[i]) / count(rows 0..i-1)
# - Winsorize: bounds from expanding quantiles with shift(1)
# - Interactions: standardization from expanding mean/std with shift(1)
#
# **When to recompute from scratch:**
# - Source data (analysis_8h.parquet) was CORRECTED (not just extended)
# - Pipeline code changed (different algorithm/params)
#
# **Pipeline by target type:**
#
# | Target            | Pipeline Steps                           |
# |-------------------|------------------------------------------|
# | direction         | Winsorize → ExpandingRank → Interactions |
# | volatility        | Winsorize only (base features are excellent) |
# | volatility_regime | Winsorize → ExpandingRank → Interactions |
# | trend_regime      | Winsorize → ExpandingRank → Interactions |
#
# **Output:** `features_8h_optimized_{target}_{horizon}bar.parquet`

# %%
import importlib
import multiprocessing as mp

import scripts.analysis.parallel_optimize as po
from scripts.analysis.optimizers.expanding_rank_fast import HAS_NUMBA
from scripts.workflow.state_detection import check_optimized_files

importlib.reload(po)  # Reload to get latest changes

print("=" * 70)
print("STEP 3: FEATURE OPTIMIZATION")
print("=" * 70)
print(f"\nNumba JIT available: {HAS_NUMBA}")
print(f"CPU cores available: {mp.cpu_count()}")

# Check if optimization is needed
SKIP_OPTIMIZATION = False
if not NEW_DATA_DETECTED:
    all_current = check_optimized_files(
        PROJECT_ROOT, WORKFLOW_TARGETS, WORKFLOW_HORIZONS, current_raw_rows
    )
    if all_current:
        print("  Skipping optimization (no new data)")
        SKIP_OPTIMIZATION = True

if not SKIP_OPTIMIZATION:
    if NEW_DATA_DETECTED:
        print("\n✅ NEW DATA DETECTED - Running incremental optimization")
        print(
            "   (Causal: only new rows need computation, historical values unchanged)"
        )

    print("\nRunning THREADED auto-optimization...\n")

    optimization_results = po.parallel_auto_optimize(
        horizons=WORKFLOW_HORIZONS,
        targets=WORKFLOW_TARGETS,
        n_workers=4,
        save=True,
        use_threading=True,
    )

    # Update state
    for target in WORKFLOW_TARGETS:
        for horizon in WORKFLOW_HORIZONS:
            opt_file = (
                PROJECT_ROOT
                / "data"
                / f"features_8h_optimized_{target}_{horizon}bar.parquet"
            )
            if opt_file.exists():
                opt_df = pl.read_parquet(opt_file)
                pipeline_state.update_step(
                    f"optimized_{target}_{horizon}bar",
                    row_count=len(opt_df),
                    last_timestamp=str(opt_df.select("timestamp").max().item()),
                )
    pipeline_state.save(PROJECT_ROOT)

    # Record metrics for quality monitoring
    from scripts.workflow.metrics_tracking import (
        check_quality_degradation,
        compute_optimization_metrics,
        record_run_metrics,
    )

    opt_metrics = compute_optimization_metrics(PROJECT_ROOT)
    record_run_metrics(
        run_type="optimization",
        metrics=opt_metrics,
        data_rows=current_raw_rows,
        data_timestamp_end=str(
            pl.read_parquet(PROJECT_ROOT / "data" / "analysis_8h.parquet")
            .select("timestamp")
            .max()
            .item()
        ),
    )

    # Check for quality degradation
    degradation = check_quality_degradation(threshold_pct=10.0)
    if degradation:
        print("\n⚠️ QUALITY DEGRADATION DETECTED!")
        for d in degradation["degradations"]:
            print(
                f"   {d['metric']}: {d['prev']:.4f} → {d['curr']:.4f} ({d['pct_change']:+.1f}%)"
            )
        # Show skipped metrics (new/removed targets)
        if degradation.get("skipped_metrics"):
            print(
                f"\nℹ️ Skipped (target changed): {', '.join(degradation['skipped_metrics'])}"
            )

    # Print optimization summary (methods stored in parquet metadata)
    from scripts.workflow.config import print_optimization_summary

    print_optimization_summary(PROJECT_ROOT)

# Quality Gate: Halt if optimization metrics degraded significantly
run_quality_gate("step3_optimization", PROJECT_ROOT, threshold_pct=10.0, auto_halt=True)

# %%
# Causality validation (optional but recommended)
from scripts.workflow.validation import run_causality_test

run_causality_test(verbose=True)

# %%
# Verify Step 3 output
from scripts.workflow.validation import verify_step3_optimization

verify_step3_optimization(PROJECT_ROOT, WORKFLOW_TARGETS, WORKFLOW_HORIZONS)

# %% [markdown]
# # Step 4: Build Dataset Matrix
#
# Generate datasets for selected configs (controlled by WORKFLOW_HORIZONS).
#
# Each dataset contains:
# - 166 base features (shared across all)
# - 3-5 target-specific interaction features (from Step 3 optimization)
# - 1 target column
#
# **Output:** `data/datasets/{target_type}_{horizon}bar.parquet`

# %%
from scripts.analysis.run import cmd_build_datasets

expected_datasets = len(WORKFLOW_TARGETS) * len(WORKFLOW_HORIZONS)
print(
    f"Building {expected_datasets}-dataset matrix (horizons={WORKFLOW_HORIZONS})...\n"
)

dataset_summary = cmd_build_datasets(
    horizons=WORKFLOW_HORIZONS,
    target_types=WORKFLOW_TARGETS,
)

# %%
# Verify Step 4 output
print("=" * 60)
print("STEP 4 COMPLETE: DATASET MATRIX")
print("=" * 60)

datasets_dir = PROJECT_ROOT / "data" / "datasets"

total_valid = 0
for target in WORKFLOW_TARGETS:
    for horizon in WORKFLOW_HORIZONS:
        filepath = datasets_dir / f"{target}_{horizon}bar.parquet"
        if filepath.exists():
            df = pl.read_parquet(filepath)
            n_features = len(
                [c for c in df.columns if not c.startswith(("y_", "timestamp"))]
            )
            n_interactions = len([c for c in df.columns if "×" in c])
            target_col = [c for c in df.columns if c.startswith("y_")][0]
            n_valid = df[target_col].drop_nulls().len()
            total_valid += n_valid
            print(
                f"✓ {target}_{horizon}bar: {n_features} base + {n_interactions} interactions, {n_valid:,} valid"
            )
        else:
            print(f"✗ {target}_{horizon}bar: NOT FOUND")

print(f"\n✓ Total: {expected_datasets} datasets")

# %% [markdown]
# # Step 5: Feature Analysis (IC/ICIR)
#
# Compute Information Coefficient (IC) and IC Information Ratio (ICIR) for all features.

# %%
from scripts.analysis.run import cmd_features

print("Running multi-horizon IC analysis...\n")
ic_results = cmd_features(plot=False)

# %%
# Show top features
import pandas as pd

if ic_results is not None:
    print("=" * 60)
    print("TOP 20 FEATURES BY |IC|")
    print("=" * 60)
    display_cols = [
        "feature",
        "domain",
        "ic_1bar",
        "ic_3bar",
        "ic_6bar",
        "ic_12bar",
        "best_horizon",
    ]
    available_cols = [c for c in display_cols if c in ic_results.columns]
    top_20 = ic_results[available_cols].head(20)
    print(top_20.to_string(index=False))

# %% [markdown]
# # Step 6: Feature Importance (MDI + MDA)
#
# Two complementary importance methods:
# - **MDI**: Fast, from LightGBM's built-in feature importances
# - **MDA**: Out-of-sample, model-agnostic (based on AFML Ch.8)

# %%
from scripts.analysis.run import cmd_importance, cmd_mda

print("Computing MDI feature importance...")
mdi_results = cmd_importance(plot=False)

print("\n" + "=" * 60)
print("TOP 20 FEATURES BY MDI IMPORTANCE")
print("=" * 60)
print(mdi_results.head(20).to_string(index=False))

# %%
print("Computing MDA feature importance (permutation-based)...\n")
mda_results = cmd_mda(n_repeats=5)

print("\n" + "=" * 60)
print("TOP 20 FEATURES BY MDA IMPORTANCE")
print("=" * 60)
print(mda_results.head(20).to_string(index=False))

# %% [markdown]
# # Step 7: Cross-Validation
#
# Time-series cross-validation with proper temporal separation.
# Uses PurgedKFold CV (from Lopez de Prado, AFML Ch.7).

# %%
from scripts.analysis.run import cmd_cv

print("Running PurgedKFold Cross-Validation...")
print("  purge_gap=21 bars, embargo_gap=12 bars\n")

cv_results = cmd_cv(use_purged=True)

print("\n" + "=" * 60)
print("CROSS-VALIDATION SUMMARY")
print("=" * 60)
for model_name, cv_result in cv_results.items():
    print(
        f"  {model_name:10s}: AUC = {cv_result.mean_auc:.4f} ± {cv_result.std_auc:.4f}"
    )

# %% [markdown]
# # Pipeline Verification
#
# Check all steps are complete.

# %%
from scripts.workflow.validation import run_pipeline_verification

run_pipeline_verification(PROJECT_ROOT)

# %% [markdown]
# # Step 8: L1 Precomputation
#
# Precompute L1 helper features for selected configs.
#
# **Config Modes:** (counts auto-update based on WORKFLOW_TARGETS in config.py)
# - `"1bar"`: len(WORKFLOW_TARGETS) configs (currently 7) - **DEFAULT**
# - `"reduced"`: len(WORKFLOW_TARGETS) × 2 configs (1bar + 3bar horizons)
# - `"all"`: len(WORKFLOW_TARGETS) × 4 configs (all 4 horizons)
#
# **Storage:** `data/precomputed/{config_name}/{YYYY-MM-DD_HHh}.parquet`

# %%
import json
import time
from dataclasses import asdict

from scripts.target_models.validation.l1_precompute import (
    L1PrecomputeConfig,
    get_config_names,
    precompute_l1_for_config,
)
from scripts.target_models.validation.regenerate_all_precomputes import (
    _filtered_end_timestamp_and_last_idx,
)

# ----------------------------------------------------------------------------
# L1 HELPERS: scripts/workflow/l1_helpers.py
# ----------------------------------------------------------------------------
# Functions:
#   compute_feasible_iters() - Calculate max walk-forward iterations for config
#   check_config_status()    - Check if config done (iterations + features match)
#   print_rust_status()      - Show which helpers have Rust acceleration
#   scan_config_status()     - Pre-scan all configs, return (to_compute, to_skip)
#
# Status dict from check_config_status():
#   status: 'done', 'wrong_iters', 'wrong_features', 'missing'
#   current_iters, current_features, needs_recompute
#
# To modify iteration calculation:
#   1. Edit compute_feasible_iters() for geometry changes
#   2. Edit check_config_status() for status logic changes
#
# Note: These depend on L1PrecomputeConfig, SlidingL2Config, ExpandingL1Config
#       from scripts/target_models/ modules
# ----------------------------------------------------------------------------
from scripts.workflow.l1_helpers import (
    check_config_status,
    compute_feasible_iters,
    print_rust_status,
    scan_config_status,
)

# Print Rust backend status
rust_status = print_rust_status()

# Configuration
from scripts.workflow.config import EXPECTED_FEATURES

cfg = L1PrecomputeConfig(
    data_dir=PROJECT_ROOT / "data" / "datasets",
    output_dir=PROJECT_ROOT / "data" / "precomputed",
    backtest_rows=L1_ROWS or 1,
    random_state=42,
    helpers=L1_HELPERS,
    enable_boosting=False,
)

configs = get_config_names(L1_CONFIG_MODE)
print(f"\nL1 Config Mode: {L1_CONFIG_MODE} ({len(configs)} configs)")
print(f"Configs: {', '.join(configs)}")

# Find global end timestamp
global_end: pd.Timestamp | None = None
ends = [_filtered_end_timestamp_and_last_idx(name, cfg)[0] for name in configs]
global_end = min(ends)

# Pre-scan status
to_compute, to_skip = scan_config_status(
    configs, cfg, L1_ROWS, EXPECTED_FEATURES, global_end, verbose=True
)

if len(to_compute) == 0:
    print("\n✓ All configs already complete! Nothing to do.")

# %%
# Run L1 precomputation
from scripts.workflow import run_l1_quality_gate, snapshot_l1_historical

results: list[dict] = []
total_t0 = time.time()
skipped_count = 0
regenerated_count = 0

print("\n" + "=" * 60)
print("L1 PRECOMPUTATION (WITH RUST ACCELERATION)")
print("=" * 60)

for i, config_name in enumerate(configs, start=1):
    print(f"[{i}/{len(configs)}] {config_name}")

    expected_iters = compute_feasible_iters(config_name, cfg, L1_ROWS, global_end)
    status = check_config_status(config_name, cfg, expected_iters, EXPECTED_FEATURES)

    if not status["needs_recompute"]:
        print("  ⏭️  SKIP (already done)")
        skipped_count += 1
        continue

    # SNAPSHOT: Capture historical values BEFORE computation
    l1_snapshot = snapshot_l1_historical(config_name, PROJECT_ROOT, n_rows=100)
    if l1_snapshot["status"] == "captured":
        print(f"  📸 Snapshot: {l1_snapshot['n_rows']} historical rows captured")

    # Compute
    action = status["status"]
    use_force = action == "wrong_features"

    regenerated_count += 1
    t0 = time.time()
    cfg.backtest_rows = expected_iters

    meta = precompute_l1_for_config(
        config_name,
        cfg=cfg,
        verbose=True,
        force=use_force,
        max_timestamp=global_end,
    )
    dt = time.time() - t0

    meta_dict = asdict(meta)
    meta_dict["elapsed_sec"] = round(dt, 2)
    results.append(meta_dict)
    print(f"  ✓ {meta.total_iterations} L1 iterations in {dt:.1f}s")

    # VERIFY: Check historical values haven't changed (causality guarantee)
    if l1_snapshot["status"] == "captured":
        run_l1_quality_gate(config_name, PROJECT_ROOT, l1_snapshot, auto_halt=True)

total_dt = time.time() - total_t0

print(f"\n{'=' * 60}")
print("L1 PRECOMPUTATION COMPLETE")
print(f"{'=' * 60}")
print(f"  Skipped: {skipped_count}")
print(f"  Computed: {regenerated_count}")
print(f"  Time: {total_dt / 60:.1f} min")

# %%
# Verify L1 precomputation
precomputed_dir = PROJECT_ROOT / "data" / "precomputed"

print("=" * 60)
print(f"L1 PRECOMPUTATION VERIFICATION (mode: {L1_CONFIG_MODE})")
print("=" * 60)

valid_configs = []
for config_name in configs:
    metadata_path = precomputed_dir / config_name / "metadata.json"
    if metadata_path.exists():
        with open(metadata_path) as f:
            meta = json.load(f)
        valid_configs.append((config_name, meta["total_iterations"]))

print(f"\n✓ Precomputed configs: {len(valid_configs)}/{len(configs)}")
for name, n_iters in valid_configs[:5]:
    print(f"  {name}: {n_iters} iterations")
if len(valid_configs) > 5:
    print(f"  ... and {len(valid_configs) - 5} more")

# %% [markdown]
# # Step 9: Assemble Prediction Datasets
#
# Assemble continuous prediction datasets from precomputed L1 iterations.
# Each assembled.parquet contains one row per walk-forward iteration.
#
# **Output:** `data/precomputed/{config}/assembled.parquet`

# %%
from scripts.target_models.validation.dataset_assembly import (
    assemble_all,
    check_assembly_status,
    update_all,
    validate_all,
)
from scripts.workflow.config import get_workflow_configs

# Use workflow configs (consistent with WORKFLOW_HORIZONS × WORKFLOW_TARGETS)
workflow_configs = get_workflow_configs()

print(f"Checking assembly status for {len(workflow_configs)} configs...")
print(f"  Configs: {', '.join(workflow_configs)}")
needs_update = []
up_to_date = []
missing = []

for config in workflow_configs:
    assembled_path = precomputed_dir / config / "assembled.parquet"
    if not assembled_path.exists():
        missing.append(config)
    else:
        status = check_assembly_status(config, precomputed_dir)
        if status.needs_update:
            needs_update.append((config, status.missing_rows))
        else:
            up_to_date.append(config)

print(f"  ✓ Up to date: {len(up_to_date)} configs")
if needs_update:
    print(f"  🔄 Need update: {len(needs_update)} configs")
if missing:
    print(f"  ⚪ Missing: {len(missing)} configs")

# Handle assembly/update
if missing:
    print("\nAssembling missing datasets...")
    results = assemble_all(precomputed_dir, configs=workflow_configs)
elif needs_update:
    print("\nUpdating with new iterations...")
    results = update_all(precomputed_dir, configs=workflow_configs)
else:
    print("\n✓ All assembled datasets are current.")

# %%
# Verify Step 9 - ONLY validate configs that have assembled.parquet
print("=" * 60)
print("STEP 9 VERIFICATION: ASSEMBLED DATASETS")
print("=" * 60)

# Filter to only configs that have L1 data (assembled.parquet exists)
configs_with_l1 = [
    cfg
    for cfg in workflow_configs
    if (precomputed_dir / cfg / "assembled.parquet").exists()
]
configs_missing_l1 = [cfg for cfg in workflow_configs if cfg not in configs_with_l1]

if configs_missing_l1:
    print(f"\n⚠️  {len(configs_missing_l1)} configs missing L1 data (need Step 8):")
    for cfg in configs_missing_l1:
        print(f"   - {cfg}")
    print()

if configs_with_l1:
    all_valid, reports = validate_all(precomputed_dir, configs=configs_with_l1)

    if all_valid:
        total_rows = sum(r.get("n_rows", 0) for r in reports)
        print(f"✓ {len(configs_with_l1)} configs valid")
        print(f"  Total prediction rows: {total_rows:,}")
        print("  Ready for fast backtesting with precomputed L1 features")
    else:
        failed = [r["config_name"] for r in reports if not r.get("is_valid", False)]
        print(f"\n✗ {len(failed)} configs failed validation")
else:
    print("\n⚠️  No configs have L1 data yet. Run Step 8 first.")

# %% [markdown]
# # Pipeline Complete ✓
#
# **Summary of outputs:**
#
# | Step | Output | Location |
# |------|--------|----------|
# | 0 | Fetched & aggregated 8h data | `fetchingByBit/*-8h-bybit-linear/` |
# | 1a | Raw merged data | `data/merged_8h_raw.parquet` |
# | 1b | Computed features | `data/features_8h.parquet` |
# | 2 | Analysis dataset + targets | `data/analysis_8h.parquet` |
# | 3 | Optimized features | `data/features_8h_optimized_{target}_{horizon}bar.parquet` |
# | 4 | Final datasets | `data/datasets/{target}_{horizon}bar.parquet` |
# | 5 | IC/ICIR analysis | `data/analysis/results/ic_*.csv` |
# | 6 | Feature importance | `data/analysis/results/{feature_importance,mda_importance}.csv` |
# | 7 | CV results | `data/analysis/results/cv_results.csv` |
# | 8 | L1 precomputed | `data/precomputed/{config}/*.parquet` |
# | 9 | Assembled datasets | `data/precomputed/{config}/assembled.parquet` |
# | 10 | L2 Backtest | `data/l2_backtest_results/` |
#
# **Next steps:**
# - Full analysis: `cmd_all()`

# %% [markdown]
# # Step 9b: Create Combined Datasets for L2 Backtest
#
# Combine raw features, helper features, and targets into single datasets
# for each config. These are required for L2 walk-forward backtesting.
#
# **Output:** `data/combined_datasets/{config}.parquet`

# %%
from scripts.target_models.validation.combined_datasets import (
    create_all_combined_datasets,
)

print("=" * 60)
print("STEP 9b: CREATE COMBINED DATASETS FOR L2 BACKTEST")
print("=" * 60)

# Only create combined datasets for configs that have L1 data
# (configs_with_l1 is defined in Step 9 cell above)
if not configs_with_l1:
    print("\n⚠️  No configs have L1 data. Run Step 8 first.")
    combined_results = {}
else:
    print(
        f"Creating combined datasets for {len(configs_with_l1)} configs with L1 data..."
    )
    if configs_missing_l1:
        print(f"  (Skipping {len(configs_missing_l1)} configs without L1 data)")

    # Create combined datasets (raw + helper + interactions + targets)
    combined_results = create_all_combined_datasets(configs=configs_with_l1)

    print(f"\n✓ Created {len(combined_results)} combined datasets")
    for config, info in combined_results.items():
        print(
            f"   {config}: {info.get('rows', '?')} rows, {info.get('total_cols', '?')} features"
        )

# %% [markdown]
# # Step 10: L2 Walk-Forward Backtest
#
# **4-Model Ensemble Backtest:**
# - CatBoost (GPU) - gradient boosting
# - LightGBM (GPU) - gradient boosting
# - LSTM (GPU) - temporal sequence model
# - Linear (CPU) - Ridge regularized baseline
#
# **Configuration from workflow:**
# - Uses `get_workflow_configs()` for consistent config list
# - Uses `L2BacktestDefaults` for default parameters
#
# **Note:** Quality gates skipped for backtest (not ready yet)

# %%
# ============================================================================
# STEP 10: L2 WALK-FORWARD BACKTEST
# ============================================================================
# Module: scripts/target_models/validation/l2_backtest_sync.py
# Config: scripts/workflow/config.py (L2BacktestDefaults, get_workflow_configs)
# Output: data/l2_backtest_results/
# ============================================================================

# Path setup (allows running this cell standalone or as part of full notebook)
import os
import sys
from pathlib import Path

# Setup PROJECT_ROOT if not already defined (when running standalone)
if "PROJECT_ROOT" not in dir() or not PROJECT_ROOT.exists():
    PROJECT_ROOT = Path("/media/przem/linux_data/RiskYieldMM (Copy)")
    os.chdir(PROJECT_ROOT)
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    validation_path = str(PROJECT_ROOT / "scripts" / "target_models" / "validation")
    if validation_path not in sys.path:
        sys.path.insert(0, validation_path)
    print(f"✓ Standalone mode: PROJECT_ROOT={PROJECT_ROOT}")

from scripts.target_models.validation.l2_backtest_sync import (
    SyncBacktestConfig,
    run_sync_backtest,
)
from scripts.workflow.config import L2BacktestDefaults, get_workflow_configs

# Get configs from workflow (consistent with WORKFLOW_HORIZONS × WORKFLOW_TARGETS)
all_configs = get_workflow_configs()

# Filter to only configs with combined datasets (Step 9b completed)
COMBINED_DIR = Path("data/combined_datasets")
configs_ready = []
configs_pending = []
for cfg in all_configs:
    combined_path = COMBINED_DIR / f"{cfg}.parquet"
    if combined_path.exists():
        configs_ready.append(cfg)
    else:
        configs_pending.append(cfg)

backtest_configs = configs_ready

# Get default backtest parameters
defaults = L2BacktestDefaults()

print("=" * 70)
print("STEP 10: L2 WALK-FORWARD BACKTEST")
print("=" * 70)
print(f"\n📊 Configs ready for backtest ({len(configs_ready)}/{len(all_configs)}):")
for cfg_name in configs_ready:
    print(f"   ✓ {cfg_name}")
if configs_pending:
    print("\n⚠️  Configs pending (no combined dataset yet):")
    for cfg_name in configs_pending:
        print(f"   - {cfg_name}")
    print("\n   → Run Steps 8 (L1) and 9b (Combined) first for these configs")

defaults.print_summary()

# %%
# Run L2 Backtest
# ---------------
# This runs walk-forward validation with 4-model ensemble.
# At each step: train on window → predict next bar → move forward.
#
# Optional overrides (uncomment to modify):
#   defaults.n_steps = 100  # Limit to last 100 steps (faster for testing)
#   defaults.enable_optuna = False  # Disable Optuna tuning (much faster)
#   defaults.train_window = 300  # Smaller training window

# Create SyncBacktestConfig from workflow defaults
sync_config = SyncBacktestConfig(**defaults.to_sync_config_kwargs())

# Run the backtest
print("\n" + "=" * 70)
print("STARTING BACKTEST")
print("=" * 70)

results = run_sync_backtest(
    configs=backtest_configs,
    config=sync_config,
    verbose=True,
)

# %%
# Step 10 Summary
print("\n" + "=" * 70)
print("STEP 10 SUMMARY: BACKTEST RESULTS")
print("=" * 70)

for config_name, result in results.items():
    metrics = result.get("metrics", {})
    task_type = "Classification" if "accuracy" in metrics else "Regression"

    if task_type == "Classification":
        acc = metrics.get("accuracy", 0) * 100
        auc = metrics.get("auc", None)
        auc_str = f", AUC={auc:.3f}" if auc else ""
        print(f"  {config_name}: Acc={acc:.1f}%{auc_str}")
    else:
        ic = metrics.get("ic", 0)
        rmse = metrics.get("rmse", 0)
        print(f"  {config_name}: IC={ic:.4f}, RMSE={rmse:.4f}")

print("\n✓ Backtest complete")
print(f"  Results saved to: {sync_config.output_dir}/")
print("  Files: backtest_run.log, predictions_*.parquet")
