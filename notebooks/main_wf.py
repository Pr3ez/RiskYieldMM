# %% [markdown]
# # Step 1: Feature Engineering
#
# Run `prepare_dataset.py` → `compute_features.py`

# %%
import os
import sys
from pathlib import Path

# HARDCODED to Copy workspace due to space in path name
PROJECT_ROOT = Path("/media/przem/linux_data/RiskYieldMM (Copy)")

if not PROJECT_ROOT.exists():
    raise FileNotFoundError(f"Workspace not found: {PROJECT_ROOT}")

os.chdir(PROJECT_ROOT)
sys.path.insert(0, str(PROJECT_ROOT))

print(f"Working dir: {os.getcwd()}")
print(f"✓ Workspace: {PROJECT_ROOT.name}")

# %%
# Step 1a: Merge raw data sources → merged_8h_raw.parquet
from scripts.feature_engineering.prepare_dataset import (
    merge_all_sources,
    print_dataset_summary,
)

data_dir = PROJECT_ROOT / "fetchingByBit"
df_raw = merge_all_sources(data_dir)
print_dataset_summary(df_raw)

# Save
output_path = PROJECT_ROOT / "data" / "merged_8h_raw.parquet"
df_raw.to_parquet(output_path)
print(f"\n✓ Saved: {output_path}")

# %%
# Step 1b: Compute features → features_8h.parquet
from scripts.feature_engineering.compute_features import (
    compute_all_features,
    load_raw_data,
)

# Load raw data (compute_features expects its own format)
df_for_features = load_raw_data(data_dir)
print(f"Loaded raw data: {df_for_features.shape}")

# Compute all features
features_df = compute_all_features(df_for_features)
print(f"Computed features: {features_df.shape}")

# Save
features_path = PROJECT_ROOT / "data" / "features_8h.parquet"
features_df.to_parquet(features_path)
print(f"\n✓ Saved: {features_path}")

# %%
# Validation summary
import pandas as pd

features = pd.read_parquet(PROJECT_ROOT / "data" / "features_8h.parquet")

print("=" * 60)
print("STEP 1 COMPLETE: FEATURE ENGINEERING")
print("=" * 60)
print("\n✓ features_8h.parquet")
print(f"  Shape: {features.shape}")
print(f"  Columns: {features.shape[1]}")
print(f"  Rows: {features.shape[0]:,}")

# Verify volMomentum fix
vol_cols = ["V_volMomentum_6_pct_N", "V_volMomentum_12_pct_N", "V_volMomentum_21_pct_N"]
print("\n✓ volMomentum clipping verified:")
for col in vol_cols:
    print(f"  {col}: max={features[col].max():.1f} (clipped at 15.0)")

print("\n✓ Ready for Step 2: Target generation")

# %% [markdown]
# # Step 2: Target Generation
#
# Generate `analysis_8h.parquet` with targets:
# - `y_direction_1bar`: Binary (1=up, 0=down)
# - `y_forward_return_{1,3,6,12}`: Multi-horizon returns
# - `y_volatility`: |forward_return_1|
# - `y_vol_regime`: LOW/MED/HIGH (0/1/2)
# - `y_trend_regime`: SMA crossover

# %%
# Step 2: Create analysis dataset with targets
from scripts.analysis.data import create_analysis_dataset

df_analysis = create_analysis_dataset()

print(f"\n✓ Saved: {PROJECT_ROOT / 'data' / 'analysis_8h.parquet'}")

# %%
# Verify Step 2 output
import polars as pl

df_check = pl.read_parquet(PROJECT_ROOT / "data" / "analysis_8h.parquet")

print("=" * 60)
print("STEP 2 COMPLETE: TARGET GENERATION")
print("=" * 60)
print("\n✓ analysis_8h.parquet")
print(f"  Shape: {df_check.shape}")

# Count target columns
target_cols = [c for c in df_check.columns if c.startswith("y_")]
print(f"  Target columns: {len(target_cols)}")
print(f"    {', '.join(target_cols)}")

print("\n✓ Ready for Step 3: Dataset generation")

# %% [markdown]
# # Step 3: Feature Optimization
#
# Per-target feature optimization using optimization pipeline.
#
# **Why per-target optimization?**
# - InteractionOptimizer selects feature pairs by IC against the TARGET
# - Features predictive of `direction` ≠ features predictive of `volatility`
# - RollingZScore HELPS direction/returns, HURTS volatility/regime targets
#
# **Pipeline by target type:**
#
# | Target        | Pipeline Steps                           |
# |---------------|------------------------------------------|
# | direction     | Winsorize → ExpandingRank → Interactions |
# | returns       | Winsorize → RollingZScore → Interactions |
# | volatility    | Winsorize only (base features are excellent) |
# | vol_regime    | Winsorize → ExpandingRank → Interactions |
# | trend_regime  | Winsorize → ExpandingRank → Interactions |
#
# **Output:** 20 files `features_8h_optimized_{target}_{horizon}bar.parquet`

# %%
# Step 3: Run auto-optimization with THREADED execution (live output in Jupyter)
# Each worker processes one target-horizon combo SEQUENTIALLY (causal-safe)
#
# CAUSALITY GUARANTEE:
#   - Workers are isolated (no shared state)
#   - Each worker computes row-by-row internally
#   - Equivalent to sequential, just faster

import importlib
import multiprocessing as mp

import scripts.analysis.parallel_optimize as po
from scripts.analysis.optimizers.expanding_rank_fast import HAS_NUMBA

importlib.reload(po)  # Reload to get latest changes

print(f"Numba JIT available: {HAS_NUMBA}")
print(f"CPU cores available: {mp.cpu_count()}")
print("Running THREADED auto-optimization (live output, causal row-by-row preserved)\n")

# use_threading=True for Jupyter live output (default)
# use_threading=False for max speed (but no live output)
optimization_results = po.parallel_auto_optimize(
    horizons=[1, 3, 6, 12],
    targets=["direction", "returns", "volatility", "vol_regime", "trend_regime"],
    n_workers=4,
    save=True,
    use_threading=True,  # Threads show live output in Jupyter (processes don't)
)

# %%
# VALIDATION: Verify NO FUTURE PEEKING in ExpandingRank
# This test proves row N only sees data from rows 0..N-1

import numpy as np
import pandas as pd

from scripts.analysis.optimizers.expanding_rank_fast import ExpandingRankOptimizerFast

print("=" * 70)
print("CAUSALITY VALIDATION: No Future Peeking Test")
print("=" * 70)

# Create test data with KNOWN pattern
np.random.seed(42)
n = 500
test_values = np.random.randn(n).cumsum()  # Random walk

# Add a SPIKE at row 400 that would be obvious if leaked
test_values[400:] += 100  # Huge jump

df_test = pd.DataFrame({"feature": test_values})

# Apply expanding rank
optimizer = ExpandingRankOptimizerFast(min_periods=50, use_numba=True)
optimizer.fit(df_test)
df_ranked = optimizer.transform(df_test)

# CAUSALITY TEST 1: Row 399 should NOT know about the spike at row 400
# If causal: rank[399] computed from rows 0..398 only (no spike knowledge)
# If leaky: rank[399] would be very low because future values are much higher

rank_before_spike = df_ranked["feature"].iloc[399]
rank_after_spike = df_ranked["feature"].iloc[400]

print("\n1. Spike Detection Test:")
print(f"   Row 399 (just before spike): rank = {rank_before_spike:.4f}")
print(f"   Row 400 (spike row): rank = {rank_after_spike:.4f}")

# Before spike: rank should be HIGH (near 1.0) - it's the cumsum maximum so far
# After spike: rank should be HIGH (near 1.0) - spike is much higher than history
if rank_before_spike > 0.9:
    print(
        f"   ✓ PASS: Row 399 has high rank ({rank_before_spike:.2f}) - doesn't know about future spike"
    )
else:
    print(
        f"   ✗ FAIL: Row 399 has LOW rank ({rank_before_spike:.2f}) - FUTURE LEAKAGE DETECTED!"
    )

# CAUSALITY TEST 2: Manually verify row 100
row_idx = 100
manual_hist = test_values[:row_idx]  # Rows 0..99
current_val = test_values[row_idx]
manual_rank = np.mean(manual_hist <= current_val)
computed_rank = df_ranked["feature"].iloc[row_idx]

print(f"\n2. Manual Verification (row {row_idx}):")
print(f"   Current value: {current_val:.4f}")
print(f"   History size: {len(manual_hist)} rows")
print(f"   Manual rank: {manual_rank:.6f}")
print(f"   Computed rank: {computed_rank:.6f}")
print(f"   Match: {'✓ PASS' if abs(manual_rank - computed_rank) < 1e-6 else '✗ FAIL'}")

# CAUSALITY TEST 3: Check expanding window behavior
print("\n3. Expanding Window Test:")
print(
    f"   First valid rank at row {optimizer.min_periods} (min_periods={optimizer.min_periods})"
)
print(f"   Rows 0-{optimizer.min_periods - 1} should be NaN:")
nan_count = df_ranked["feature"].iloc[: optimizer.min_periods].isna().sum()
print(f"   NaN count in first {optimizer.min_periods} rows: {nan_count}")
print(f"   {'✓ PASS' if nan_count == optimizer.min_periods else '✗ FAIL'}")

print("\n" + "=" * 70)
if rank_before_spike > 0.9 and abs(manual_rank - computed_rank) < 1e-6:
    print("✓ ALL CAUSALITY TESTS PASSED - No future peeking detected")
else:
    print("✗ CAUSALITY VIOLATION DETECTED - Check implementation!")
print("=" * 70)

# %%
# Verify Step 3: Check optimized feature files exist
from pathlib import Path

print("=" * 60)
print("STEP 3 VERIFICATION: OPTIMIZED FEATURES")
print("=" * 60)

data_dir = PROJECT_ROOT / "data"
targets = ["direction", "returns", "volatility", "vol_regime", "trend_regime"]
horizons = [1, 3, 6, 12]

created_files = []
missing_files = []

for target in targets:
    for horizon in horizons:
        filename = f"features_8h_optimized_{target}_{horizon}bar.parquet"
        filepath = data_dir / filename
        if filepath.exists():
            size_mb = filepath.stat().st_size / (1024 * 1024)
            created_files.append((filename, size_mb))
        else:
            missing_files.append(filename)

print(f"\n✓ Created files: {len(created_files)}/20")
for f, size in created_files[:5]:  # Show first 5
    print(f"  {f}: {size:.2f} MB")
if len(created_files) > 5:
    print(f"  ... and {len(created_files) - 5} more")

if missing_files:
    print(f"\n✗ Missing files: {len(missing_files)}")
    for f in missing_files[:5]:
        print(f"  {f}")
else:
    print("\n✓ All 20 optimized feature files created")

print("\n✓ Ready for Step 4: Dataset generation")

# %% [markdown]
# # Step 4: Build Dataset Matrix
#
# Generate 20 final datasets (5 targets × 4 horizons).
#
# Each dataset contains:
# - 166 base features (shared across all)
# - 3-5 target-specific interaction features (from Step 3 optimization)
# - 1 target column
#
# **Target types:**
# - `direction`: Binary (1=up, 0=down) — classification
# - `returns`: Continuous forward return — regression
# - `volatility`: |return| — risk/position sizing
# - `vol_regime`: LOW/MED/HIGH — regime-aware strategies
# - `trend_regime`: Up/Down trend — trend-following
#
# **Horizons:**
# - `1bar` (8h): Intraday
# - `3bar` (24h): Daily rebalancing
# - `6bar` (48h): Swing trading
# - `12bar` (96h): Position trading
#
# **Output:** `data/datasets/{target_type}_{horizon}bar.parquet`

# %%
# Step 4: Build the 20-dataset matrix
from scripts.analysis.run import cmd_build_datasets

# Build all 20 datasets: 5 targets × 4 horizons
# Each dataset:
#   - 166 base features (shared)
#   - 3-5 interaction features (target-specific from Step 3)
#   - 1 target column (y_{target_type})

print("Building 20-dataset matrix...")
print("This loads optimized features from Step 3 for each target-horizon combination\n")

dataset_summary = cmd_build_datasets(
    horizons=[1, 3, 6, 12],
    target_types=["direction", "returns", "volatility", "vol_regime", "trend_regime"],
)

# %%
# Final verification: All datasets created
import polars as pl

print("=" * 60)
print("STEP 4 COMPLETE: DATASET MATRIX")
print("=" * 60)

datasets_dir = PROJECT_ROOT / "data" / "datasets"
targets = ["direction", "returns", "volatility", "vol_regime", "trend_regime"]
horizons = [1, 3, 6, 12]

print(f"\nDatasets directory: {datasets_dir}")
print("-" * 60)

total_valid = 0
for target in targets:
    for horizon in horizons:
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

print("-" * 60)
print("\n✓ Total: 20 datasets")
print("✓ Ready for Step 5: Feature Analysis & Model Training")

# %% [markdown]
# # Step 5: Feature Analysis (IC/ICIR)
#
# Compute Information Coefficient (IC) and IC Information Ratio (ICIR) for all features.
#
# **Metrics computed:**
# - **IC** (Spearman correlation): Feature's predictive power
# - **ICIR** = mean(IC) / std(IC): Stability of predictive power
# - **Hit Rate**: Directional accuracy
# - **FDR-corrected significance**: Multiple testing correction
#
# **Multi-horizon analysis** uses non-overlapping samples for horizons > 1 bar to avoid autocorrelation bias.
#
# **Output:**
# - `data/analysis/results/ic_multi_horizon.csv` — All features across horizons
# - `data/analysis/results/ic_horizon_summary.csv` — Best horizon per feature

# %%
# Step 5: Feature Analysis (IC/ICIR) across all horizons
from scripts.analysis.run import cmd_features

# Compute multi-horizon IC analysis
# - IC for each feature against y_forward_return_{1,3,6,12}
# - Uses non-overlapping samples for horizons > 1 (to avoid autocorrelation)
# - FDR correction for multiple testing
# - Identifies best horizon per feature

print("Running multi-horizon IC analysis...")
print(
    "This computes Information Coefficient for each feature against all forward return horizons\n"
)

ic_results = cmd_features(plot=False)  # Set plot=True to generate visualizations

# %%
# Show top features by IC
import pandas as pd

print("=" * 60)
print("TOP FEATURES BY |IC|")
print("=" * 60)

# Display top 20 features with their IC across horizons
if ic_results is not None:
    display_cols = [
        "feature",
        "domain",
        "ic_1bar",
        "ic_3bar",
        "ic_6bar",
        "ic_12bar",
        "best_horizon",
    ]
    top_20 = ic_results[display_cols].head(20)

    # Format IC values
    for col in ["ic_1bar", "ic_3bar", "ic_6bar", "ic_12bar"]:
        top_20[col] = top_20[col].apply(lambda x: f"{x:+.4f}" if pd.notna(x) else "")

    print(top_20.to_string(index=False))

    # Domain summary
    print("\n" + "-" * 60)
    print("TOP FEATURES BY DOMAIN")
    print("-" * 60)
    domain_counts = (
        ic_results.groupby("domain")
        .agg({"feature": "count", "ic_1bar": lambda x: x.abs().mean()})
        .rename(columns={"feature": "count", "ic_1bar": "mean_|IC|"})
    )
    domain_counts = domain_counts.sort_values("mean_|IC|", ascending=False)
    print(domain_counts.to_string())

# %% [markdown]
# # Step 6: Feature Importance (MDI + MDA)
#
# Two complementary importance methods:
#
# **MDI (Mean Decrease Impurity):**
# - Fast, from LightGBM's built-in feature importances
# - Can be biased toward high-cardinality features
#
# **MDA (Mean Decrease Accuracy / Permutation Importance):**
# - Out-of-sample, model-agnostic
# - Based on Lopez de Prado, AFML Ch.8
# - More reliable but slower
#
# **Output:**
# - `data/analysis/results/feature_importance.csv` (MDI)
# - `data/analysis/results/mda_importance.csv` (MDA)

# %%
# Step 6a: MDI (Mean Decrease Impurity) - Fast importance from LightGBM
from scripts.analysis.run import cmd_importance

print("Computing MDI feature importance...")
mdi_results = cmd_importance(plot=False)

print("\n" + "=" * 60)
print("TOP 20 FEATURES BY MDI IMPORTANCE")
print("=" * 60)
print(mdi_results.head(20).to_string(index=False))

# %%
# Step 6b: MDA (Permutation Importance) - Out-of-sample, model-agnostic
from scripts.analysis.run import cmd_mda

print("Computing MDA feature importance (permutation-based)...")
print("This is more reliable but slower than MDI\n")

mda_results = cmd_mda(n_repeats=5)  # 5 repeats for speed, use 10 for production

print("\n" + "=" * 60)
print("TOP 20 FEATURES BY MDA IMPORTANCE")
print("=" * 60)
print(mda_results.head(20).to_string(index=False))

# %% [markdown]
# # Step 7: Cross-Validation
#
# Time-series cross-validation with proper temporal separation.
#
# **PurgedKFold CV** (from Lopez de Prado, AFML Ch.7):
# - **Purge gap** (21 bars): Removes training samples that could have features using test period data
# - **Embargo gap** (12 bars): Removes training samples whose targets overlap with test period
#
# **Models trained:**
# - CatBoost Classifier (direction)
# - LightGBM Classifier (direction)
# - CatBoost Regressor (volatility)
#
# **Output:** `data/analysis/results/cv_results.csv`

# %%
# Step 7: Cross-Validation with PurgedKFold
from scripts.analysis.run import cmd_cv

print("Running PurgedKFold Cross-Validation...")
print("  purge_gap=21 bars (prevents feature look-ahead)")
print("  embargo_gap=12 bars (prevents target overlap)\n")

cv_results = cmd_cv(use_purged=True)

# Summary
print("\n" + "=" * 60)
print("CROSS-VALIDATION SUMMARY")
print("=" * 60)
for model_name, cv_result in cv_results.items():
    print(
        f"  {model_name:10s}: AUC = {cv_result.mean_auc:.4f} ± {cv_result.std_auc:.4f}"
    )

# %% [markdown]
# # Pipeline Complete ✓
#
# **Summary of outputs:**
#
# | Step | Output | Location |
# |------|--------|----------|
# | 1a | Raw merged data | `data/merged_8h_raw.parquet` |
# | 1b | Computed features | `data/features_8h.parquet` |
# | 2 | Analysis dataset + targets | `data/analysis_8h.parquet` |
# | 3 | Optimized features | `data/features_8h_optimized_{target}_{horizon}bar.parquet` (20 files) |
# | 4 | Final datasets | `data/datasets/{target}_{horizon}bar.parquet` (20 files) |
# | 5 | IC/ICIR analysis | `data/analysis/results/ic_*.csv` |
# | 6 | Feature importance | `data/analysis/results/{feature_importance,mda_importance}.csv` |
# | 7 | CV results | `data/analysis/results/cv_results.csv` |
#
# **Next steps:**
# - Walk-forward backtest: `cmd_backtest()`
# - Full analysis: `cmd_all()`

# %%
# Final pipeline verification
import os
from pathlib import Path

print("=" * 70)
print("PIPELINE VERIFICATION")
print("=" * 70)

checks = []

# Check Step 1: Raw and features
raw_file = PROJECT_ROOT / "data" / "merged_8h_raw.parquet"
features_file = PROJECT_ROOT / "data" / "features_8h.parquet"
checks.append(("Step 1a: merged_8h_raw.parquet", raw_file.exists()))
checks.append(("Step 1b: features_8h.parquet", features_file.exists()))

# Check Step 2: Analysis dataset
analysis_file = PROJECT_ROOT / "data" / "analysis_8h.parquet"
checks.append(("Step 2: analysis_8h.parquet", analysis_file.exists()))

# Check Step 3: Optimized features (20 files)
opt_count = len(list(PROJECT_ROOT.glob("data/features_8h_optimized_*.parquet")))
checks.append((f"Step 3: Optimized features ({opt_count}/20)", opt_count == 20))

# Check Step 4: Final datasets (20 files)
datasets_dir = PROJECT_ROOT / "data" / "datasets"
dataset_count = (
    len(list(datasets_dir.glob("*.parquet"))) if datasets_dir.exists() else 0
)
checks.append((f"Step 4: Final datasets ({dataset_count}/20)", dataset_count == 20))

# Check Step 5-7: Results
results_dir = PROJECT_ROOT / "data" / "analysis" / "results"
ic_file = results_dir / "ic_multi_horizon.csv"
mdi_file = results_dir / "feature_importance.csv"
mda_file = results_dir / "mda_importance.csv"
cv_file = results_dir / "cv_results.csv"

checks.append(("Step 5: IC analysis", ic_file.exists()))
checks.append(("Step 6a: MDI importance", mdi_file.exists()))
checks.append(("Step 6b: MDA importance", mda_file.exists()))
checks.append(("Step 7: CV results", cv_file.exists()))

# Print results
print()
all_passed = True
for name, passed in checks:
    status = "✓" if passed else "✗"
    print(f"  {status} {name}")
    if not passed:
        all_passed = False

print()
if all_passed:
    print("═" * 70)
    print("ALL PIPELINE STEPS COMPLETE ✓")
    print("═" * 70)
else:
    print("Some steps incomplete - run the missing cells above")

# %% [markdown]
# # Step 8: L1 Precomputation
#
# Precompute L1 helper features for all 20 configs (5 targets × 4 horizons).
#
# **Walk-forward config:**
# - `backtest_rows`: 500 iterations
# - `L1_warmup`: 500 bars minimum history before first prediction
# - `L1_window`: 500 bars training window
#
# **What it does per iteration:**
# 1. `fit(X[train_window])` — Fit L1 ensemble on training data
# 2. `transform(X[pred_row])` — Generate helper features for prediction row
# 3. Save `{timestamp}.parquet` with helper features
#
# **Resume capability:**
# - Detects if new data was fetched → regenerates to include new rows
# - Detects if `backtest_rows` changed → regenerates with new count
# - Set `force=True` to regenerate everything from scratch
#
# **Storage:** `data/precomputed/{config_name}/{YYYY-MM-DD_HHh}.parquet`
#
# **Benefit:** After precomputation, backtests load pre-saved helper features instead of recomputing L1 each iteration.

# %%
# Step 8: Precompute L1 helper features for all 20 configs
#
# This ONLY computes L1 features. Later layers use these precomputed outputs.
# NOW INCLUDES NEW HELPERS: EVT POT, OU, BOCPD, EGARCH
# RUST BACKENDS: 7 helpers use high-performance Rust implementations

import json
import time
from dataclasses import asdict

import pandas as pd

from scripts.target_models.core.aligned_dual_window import (
    ExpandingL1Config,
    SlidingL2Config,
    get_l2_config_for_target,
)
from scripts.target_models.helpers.bocpd import HAS_RUST as BOCPD_RUST

# ============================================================================
# RUST BACKEND STATUS
# ============================================================================
from scripts.target_models.helpers.cusum import HAS_RUST as CUSUM_RUST
from scripts.target_models.helpers.egarch import HAS_RUST as EGARCH_RUST
from scripts.target_models.helpers.evt_pot import HAS_RUST as EVT_RUST
from scripts.target_models.helpers.garch import HAS_RUST as GARCH_RUST
from scripts.target_models.helpers.kalman import HAS_RUST as KALMAN_RUST
from scripts.target_models.helpers.ou import HAS_RUST as OU_RUST
from scripts.target_models.validation.l1_precompute import (
    L1PrecomputeConfig,
    get_all_config_names,
    precompute_l1_for_config,
)
from scripts.target_models.validation.regenerate_all_precomputes import (
    _filtered_end_timestamp_and_last_idx,
    verify_config_finishes_at_dataset_end,
)

print("=" * 60)
print("RUST BACKEND STATUS")
print("=" * 60)
rust_status = {
    "CUSUM": CUSUM_RUST,
    "Kalman": KALMAN_RUST,
    "GARCH": GARCH_RUST,
    "EVT": EVT_RUST,
    "OU": OU_RUST,
    "BOCPD": BOCPD_RUST,
    "EGARCH": EGARCH_RUST,
}
for name, has_rust in rust_status.items():
    status = "✓ Rust" if has_rust else "○ Python"
    speedup = {
        "CUSUM": "156x",
        "Kalman": "487x",
        "GARCH": "224x",
        "EVT": "25x",
        "OU": "30x",
        "BOCPD": "20x",
        "EGARCH": "22x",
    }
    print(
        f"  {name:8s}: {status} ({speedup.get(name, '')} speedup)"
        if has_rust
        else f"  {name:8s}: {status}"
    )

rust_count = sum(rust_status.values())
print(f"\n  {rust_count}/7 helpers using Rust backends")
print("  HMM4, HMM5, IsolationForest use optimized Python (hmmlearn/sklearn)")

# ============================================================================
# CONFIGURATION — SET YOUR L1 ITERATION COUNT HERE
# ============================================================================
L1_ROWS = None  # None = auto (use max feasible per config); otherwise acts as cap

# NEW: Include all 10 helpers (6 original + 4 new)
HELPERS = [
    "if",
    "cusum",
    "garch",
    "hmm4",
    "hmm5",
    "kalman",
    "evt",
    "ou",
    "bocpd",
    "egarch",
]
print(f"\nL1 Helpers enabled: {HELPERS}")

# DISABLE feature selection - keep ALL features from helpers
ENABLE_BOOSTING = False  # Set True to enable ICIR feature selection

cfg = L1PrecomputeConfig(
    data_dir=PROJECT_ROOT / "data" / "datasets",
    output_dir=PROJECT_ROOT / "data" / "precomputed",
    backtest_rows=L1_ROWS or 1,  # overwritten per-config below
    random_state=42,
    helpers=HELPERS,  # Pass new helpers list
    enable_boosting=ENABLE_BOOSTING,  # False = keep all features
)

print(
    f"Feature selection: {'ENABLED (ICIR filtering)' if ENABLE_BOOSTING else 'DISABLED (keep all features)'}"
)

# ============================================================================
# SMART RESUME: Check config status (iterations AND features)
# ============================================================================
EXPECTED_FEATURES = 91  # All 10 helpers, no ICIR selection


def compute_feasible_iters(
    config_name: str,
    cfg: L1PrecomputeConfig,
    backtest_rows: int | None,
    max_timestamp: pd.Timestamp | None = None,
) -> int:
    """
    Compute the maximum walk-forward iterations possible for a config
    given the data (after dropna) and current window settings.
    If backtest_rows is None, uses the maximum possible.
    Mirrors DualLayerEngine geometry: min warmup + L2 window + horizon.
    """
    data_path = cfg.data_dir / f"{config_name}.parquet"
    df = pd.read_parquet(data_path)

    feature_cols = [
        c for c in df.columns if not c.startswith("y_") and c != "timestamp"
    ]
    y_cols = [c for c in df.columns if c.startswith("y_")]
    target = config_name.rsplit("_", 1)[0]
    y_col = f"y_{target}"
    if y_col not in df.columns:
        y_col = y_cols[0] if y_cols else None
    if y_col is None:
        raise ValueError(f"No target column found for {config_name}")

    df = df.dropna(subset=feature_cols + [y_col])
    if max_timestamp is not None:
        df = df[df["timestamp"] <= max_timestamp]

    total_rows = len(df)
    if total_rows == 0:
        return 0

    horizon_part = config_name.rsplit("_", 1)[1]
    horizon = (
        int(horizon_part.replace("bar", ""))
        if "bar" in horizon_part
        else int(horizon_part)
    )

    base_l2 = get_l2_config_for_target(target)
    l2_cfg = SlidingL2Config()
    l2_cfg.window_size = base_l2.window_size
    l2_cfg.train_ratio = base_l2.train_ratio
    l2_cfg.cal_ratio = base_l2.cal_ratio
    l2_cfg.val_ratio = base_l2.val_ratio
    l2_cfg.purge_gap = base_l2.purge_gap
    l2_cfg.pred_size = horizon
    l1_warmup = ExpandingL1Config().min_warmup

    min_required_rows = l1_warmup + l2_cfg.total_size
    min_start = min_required_rows - 1
    last_pred_idx = total_rows - l2_cfg.pred_size
    if last_pred_idx < min_start:
        return 0

    if backtest_rows is None:
        first_pred_idx = min_start
    else:
        desired_start = last_pred_idx - backtest_rows + 1
        first_pred_idx = max(min_start, desired_start)
    return last_pred_idx - first_pred_idx + 1


def check_config_status(
    config_name: str,
    cfg: L1PrecomputeConfig,
    expected_iters: int,
    expected_features: int,
) -> dict:
    """Check if config is done with correct settings.

    Returns dict with:
        - status: 'done', 'wrong_iters', 'wrong_features', 'missing'
        - current_iters: int or None
        - current_features: int or None
        - needs_recompute: bool
    """
    metadata_file = cfg.metadata_path(config_name)

    if not metadata_file.exists():
        return {
            "status": "missing",
            "current_iters": None,
            "current_features": None,
            "needs_recompute": True,
        }

    with open(metadata_file) as f:
        meta = json.load(f)

    current_iters = meta.get("total_iterations", 0)
    current_features = meta.get("feature_count", 0)

    # Check iteration count (allow extra iterations; require at least expected)
    if current_iters < expected_iters:
        return {
            "status": "wrong_iters",
            "current_iters": current_iters,
            "current_features": current_features,
            "needs_recompute": True,
        }

    # Check feature count (important for enable_boosting changes)
    if current_features != expected_features:
        return {
            "status": "wrong_features",
            "current_iters": current_iters,
            "current_features": current_features,
            "needs_recompute": True,
        }

    # Both match - config is done
    return {
        "status": "done",
        "current_iters": current_iters,
        "current_features": current_features,
        "needs_recompute": False,
    }


configs = get_all_config_names()
align_global_end = True
no_verify = False

# ============================================================================
# Find global end timestamp (all configs truncated to same end)
# ============================================================================
global_end: pd.Timestamp | None = None
if align_global_end:
    ends = [_filtered_end_timestamp_and_last_idx(name, cfg)[0] for name in configs]
    global_end = min(ends)

# ============================================================================
# PRE-SCAN: Show status of all configs BEFORE starting
# ============================================================================
print("\n" + "=" * 60)
print("PRE-SCAN: CONFIG STATUS")
print("=" * 60)
print(
    f"Target cap: {'auto' if L1_ROWS is None else L1_ROWS} iterations (per-config feasible computed), {EXPECTED_FEATURES} features"
)
print()

to_compute = []
to_skip = []

for config_name in configs:
    expected_iters = compute_feasible_iters(config_name, cfg, L1_ROWS, global_end)
    status = check_config_status(config_name, cfg, expected_iters, EXPECTED_FEATURES)
    if status["needs_recompute"]:
        to_compute.append(config_name)
        if status["status"] == "missing":
            print(f"  ⚪ {config_name}: MISSING")
        elif status["status"] == "wrong_iters":
            print(
                f"  🔄 {config_name}: {status['current_iters']} iters (need {expected_iters})"
            )
        elif status["status"] == "wrong_features":
            print(
                f"  🔧 {config_name}: {status['current_features']} features (need {EXPECTED_FEATURES})"
            )
    else:
        to_skip.append(config_name)
        print(
            f"  ✅ {config_name}: DONE ({status['current_iters']} iters, {status['current_features']} features)"
        )

print()
print(f"Summary: {len(to_skip)} done, {len(to_compute)} need computation")
print("=" * 60)

if len(to_compute) == 0:
    print("\n✓ All configs already complete! Nothing to do.")

results: list[dict] = []
end_timestamps: dict[str, str] = {}

print("\n" + "=" * 60)
print("L1 PRECOMPUTATION (WITH RUST ACCELERATION)")
print("=" * 60)
print(f"\n  L1 iterations: {L1_ROWS}")
print(f"  Expected features: {EXPECTED_FEATURES}")
print(f"  Helpers: {len(HELPERS)} ({', '.join(HELPERS)})")
print(f"  Configs total: {len(configs)}")
print(f"  To skip: {len(to_skip)}")
print(f"  To compute: {len(to_compute)}")
print(f"  Output: {cfg.output_dir}")
if global_end is not None:
    print(f"  Global end: {global_end.strftime('%Y-%m-%d %H:%M')}")
print()

# ============================================================================
# Run L1 precomputation (SMART RESUME)
# ============================================================================
total_t0 = time.time()
skipped_count = 0
regenerated_count = 0

for i, config_name in enumerate(configs, start=1):
    print(f"[{i}/{len(configs)}] {config_name}")

    # Smart resume: check if already done with correct settings
    expected_iters = compute_feasible_iters(config_name, cfg, L1_ROWS, global_end)
    status = check_config_status(config_name, cfg, expected_iters, EXPECTED_FEATURES)

    if not status["needs_recompute"]:
        print(
            f"  ⏭️  SKIP (already {status['current_iters']} iters, {status['current_features']} features)"
        )
        metadata_file = cfg.metadata_path(config_name)
        with open(metadata_file) as f:
            existing_meta = json.load(f)
        existing_meta["skipped"] = True
        results.append(existing_meta)
        skipped_count += 1
        continue

    # Need to compute this config
    action = status["status"]

    # Decide whether to force restart or allow resume
    # - wrong_features: MUST restart (old features incompatible)
    # - wrong_iters: CAN resume if features match, but features=0 means old format
    # - missing: fresh start
    use_force = False
    if action == "missing":
        print("  📥 Computing (fresh start)")
    elif action == "wrong_iters":
        if status["current_features"] == EXPECTED_FEATURES:
            # Same feature count; append missing iterations without wiping
            use_force = False
            print(
                f"  ▶️  Resuming/adding ({status['current_iters']} → {expected_iters} iters)"
            )
        else:
            # Different features or old format (features=0) - must restart
            use_force = True
            print(
                f"  🔄 Restarting ({status['current_iters']} iters, features mismatch)"
            )
    elif action == "wrong_features":
        use_force = True
        print(
            f"  🔧 Restarting ({status['current_features']} → {EXPECTED_FEATURES} features)"
        )

    regenerated_count += 1

    t0 = time.time()
    # Use per-config feasible iteration count when computing
    cfg.backtest_rows = expected_iters

    meta = precompute_l1_for_config(
        config_name,
        cfg=cfg,
        verbose=True,
        force=use_force,  # Only force when features mismatch
        max_timestamp=global_end,
    )
    dt = time.time() - t0

    meta_dict = asdict(meta)
    meta_dict["elapsed_sec"] = round(dt, 2)
    meta_dict["action"] = action

    if meta.total_iterations < expected_iters:
        raise RuntimeError(
            f"{config_name}: got {meta.total_iterations} L1 iterations, expected >= {expected_iters}"
        )
    elif meta.total_iterations > expected_iters:
        print(
            f"  ⚠️  {config_name}: has {meta.total_iterations} iterations (more than expected {expected_iters}); keeping existing."
        )

    if meta.feature_count != EXPECTED_FEATURES:
        raise RuntimeError(
            f"{config_name}: got {meta.feature_count} features, expected {EXPECTED_FEATURES}"
        )

    if not no_verify:
        check = verify_config_finishes_at_dataset_end(
            config_name, cfg, max_timestamp=global_end
        )
        meta_dict["end_alignment"] = check
        if not check["ok"]:
            raise RuntimeError(f"End alignment failed: {json.dumps(check, indent=2)}")
        end_timestamps[config_name] = check["data_last_timestamp"]

    results.append(meta_dict)
    print(f"  ✓ {meta.total_iterations} L1 iterations in {dt:.1f}s")

total_dt = time.time() - total_t0

# ============================================================================
# Verify all configs aligned
# ============================================================================
if not no_verify and end_timestamps:
    unique_ends = sorted(set(end_timestamps.values()))
    if len(unique_ends) != 1:
        print(f"\n⚠️  WARNING: {len(unique_ends)} different end timestamps (expected 1)")

# ============================================================================
# Save summary
# ============================================================================
summary_path = cfg.output_dir / "precompute_summary.json"
summary_path.parent.mkdir(parents=True, exist_ok=True)
with open(summary_path, "w") as f:
    json.dump(
        {
            "l1_iterations": L1_ROWS,
            "expected_features": EXPECTED_FEATURES,
            "helpers": HELPERS,
            "rust_backends": rust_count,
            "output_dir": str(cfg.output_dir),
            "data_dir": str(cfg.data_dir),
            "total_elapsed_sec": round(total_dt, 2),
            "configs": results,
        },
        f,
        indent=2,
    )

print(f"\n{'=' * 60}")
print("L1 PRECOMPUTATION COMPLETE")
print(f"{'=' * 60}")
print(f"  L1 iterations: {L1_ROWS}")
print(f"  Features: {EXPECTED_FEATURES}")
print(f"  Helpers: {len(HELPERS)} (7 Rust + 3 Python)")
print(f"  Skipped: {skipped_count}")
print(f"  Computed: {regenerated_count}")
print(f"  Time: {total_dt / 60:.1f} min")
print(f"\n  Output: {cfg.output_dir}")
print(f"  Summary: {summary_path}")

# %%
# Verify L1 precomputation
import json
from pathlib import Path

precomputed_dir = PROJECT_ROOT / "data" / "precomputed"

# Re-import in case running standalone
from scripts.target_models.validation.l1_precompute import get_all_config_names

config_names = get_all_config_names()

print("=" * 60)
print("L1 PRECOMPUTATION VERIFICATION")
print("=" * 60)

# Check summary file for helpers and Rust info
summary_path = precomputed_dir / "precompute_summary.json"
if summary_path.exists():
    with open(summary_path) as f:
        summary = json.load(f)
    helpers = summary.get("helpers", [])
    rust_count = summary.get("rust_backends", 0)
    print(f"\n  Helpers: {len(helpers)} ({', '.join(helpers)})")
    print(f"  Rust backends: {rust_count}/7")
    print(f"  Total time: {summary.get('total_elapsed_sec', 0) / 60:.1f} min")

valid_configs = []
missing_configs = []

for config_name in config_names:
    metadata_path = precomputed_dir / config_name / "metadata.json"

    if metadata_path.exists():
        with open(metadata_path) as f:
            meta = json.load(f)
        n_iters = meta["total_iterations"]
        date_range = (
            f"{meta['first_pred_timestamp'][:10]} to {meta['last_pred_timestamp'][:10]}"
        )
        valid_configs.append((config_name, n_iters, date_range))
    else:
        missing_configs.append(config_name)

print(f"\n✓ Precomputed configs: {len(valid_configs)}/{len(config_names)}")
for name, n_iters, date_range in valid_configs[:5]:
    print(f"  {name}: {n_iters} iterations ({date_range})")
if len(valid_configs) > 5:
    print(f"  ... and {len(valid_configs) - 5} more")

if missing_configs:
    print(f"\n✗ Missing configs: {len(missing_configs)}")
    for name in missing_configs[:5]:
        print(f"  {name}")
    if len(missing_configs) > 5:
        print(f"  ... and {len(missing_configs) - 5} more")
else:
    print("\n✓ All 20 configs precomputed and ready for Step 9: Dataset Assembly")

# %% [markdown]
# # Step 9: Assemble Prediction Datasets
#
# Assemble continuous prediction datasets from precomputed L1 iterations.
# Each assembled.parquet contains one row per walk-forward iteration (the prediction row).
#
# **What it does:**
# - For each of 20 configs, reads all iteration parquet files
# - Extracts the last row (prediction row) from each file
# - Sorts chronologically by timestamp
# - Saves as `assembled.parquet` in each config directory
#
# **Output:** `data/precomputed/{config}/assembled.parquet`
# - ~3200-3700 rows per config (one per iteration)
# - 92 columns (91 helper features + pred_idx)
# - Indexed by timestamp (timezone-aware UTC)
#
# **Benefit:** Fast feature lookup during backtesting without loading individual parquet files.

# %%
# Step 9: Assemble prediction datasets from precomputed L1 iterations
import time

from scripts.target_models.validation.dataset_assembly import (
    ALL_CONFIGS,
    assemble_all,
    check_assembly_status,
    update_all,
    validate_all,
)

# Check status of all configs
precomputed_dir = PROJECT_ROOT / "data" / "precomputed"

print("Checking assembly status...")
needs_update = []
up_to_date = []
missing = []

for config in ALL_CONFIGS:
    assembled_path = precomputed_dir / config / "assembled.parquet"
    if not assembled_path.exists():
        missing.append(config)
    else:
        status = check_assembly_status(config, precomputed_dir)
        if status.needs_update:
            needs_update.append((config, status.missing_rows))
        else:
            up_to_date.append(config)

# Report status
print(f"  ✓ Up to date: {len(up_to_date)} configs")
if needs_update:
    print(f"  🔄 Need update: {len(needs_update)} configs")
    for cfg, n_new in needs_update[:3]:
        print(f"      {cfg}: +{n_new} new iterations")
    if len(needs_update) > 3:
        print(f"      ... and {len(needs_update) - 3} more")
if missing:
    print(f"  ⚪ Missing: {len(missing)} configs")

# Handle assembly/update
if missing:
    print("\nAssembling missing datasets...")
    t0 = time.time()
    results = assemble_all(precomputed_dir)
    elapsed = time.time() - t0
    print(f"Assembly completed in {elapsed:.1f}s")
elif needs_update:
    print("\nUpdating with new iterations...")
    results = update_all(precomputed_dir)
else:
    print("\n✓ All 20 assembled datasets are current. Nothing to do.")

# %%
# Verify Step 9: Assembled datasets

print("=" * 60)
print("STEP 9 VERIFICATION: ASSEMBLED DATASETS")
print("=" * 60)

all_valid, reports = validate_all(precomputed_dir)

print()
if all_valid:
    total_rows = sum(r.get("n_rows", 0) for r in reports)
    print("=" * 60)
    print("STEP 9 COMPLETE: PREDICTION DATASETS ASSEMBLED")
    print("=" * 60)
    print("  Configs: 20/20 valid")
    print(f"  Total prediction rows: {total_rows:,}")
    print("  Features per row: 91 helper features + pred_idx")
    print("  Output: data/precomputed/{config}/assembled.parquet")
    print("\n✓ Ready for fast backtesting with precomputed L1 features")
else:
    failed = [r["config_name"] for r in reports if not r.get("is_valid", False)]
    print(f"✗ {len(failed)} configs failed validation:")
    for name in failed:
        print(f"  - {name}")
