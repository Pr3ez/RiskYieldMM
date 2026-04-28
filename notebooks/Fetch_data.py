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
from scripts.workflow.config import (
    AUTO_FETCH_IF_STALE,
    STALE_THRESHOLD_HOURS,
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
    print_pipeline_status,
)
from scripts.workflow.state_detection import detect_new_data

# Load pipeline state and detect changes
pipeline_state = PipelineState.load(PROJECT_ROOT)
print_pipeline_status(pipeline_state, PROJECT_ROOT)

NEW_DATA_DETECTED, current_raw_rows = detect_new_data(
    PROJECT_ROOT, pipeline_state, verbose=True
)
# %%
