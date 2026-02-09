# %% [markdown]
# # HTF Strategy Backtest
#
# ## Data Preparation Summary
#
# We have prepared **5,574 8-hour batches** of data for backtesting across three timeframes:
#
# | Timeframe | Batches | Rows/Batch | Total Rows | Combined File |
# |-----------|---------|------------|------------|---------------|
# | 1m | 5,574 | 480 | 2,675,634 | `1m_HTF_combined.parquet` (41.6 MB) |
# | 5m | 5,574 | 96 | 535,060 | `5m_HTF_combined.parquet` (8.9 MB) |
# | 15m | 5,574 | 32 | 178,354 | `15m_HTF_combined.parquet` (3.1 MB) |
#
# **Data structure:**
# - Each batch covers one 8h period (00:00-08:00, 08:00-16:00, or 16:00-00:00 UTC)
# - Columns: `timestamp`, `open`, `high`, `low`, `close`, `volume`, `period_8h_start`, `batch_id`
# - Date range: 2021-01-01 to 2026-02-01
#
# **File locations:**
# - Individual batches: `data/htf_backtest/{tf}_HTF_backtest_XXXX.parquet`
# - Combined files: `data/htf_backtest/{tf}_HTF_combined.parquet`

# %%
# =============================================================================
# CELL 2: SETUP & PATHS (No data loading - just config)
# =============================================================================
import gc
from datetime import datetime
from pathlib import Path

import polars as pl

# Project paths
PROJECT_ROOT = Path("..").resolve()
DATA_DIR = PROJECT_ROOT / "data"
HTF_BACKTEST_DIR = DATA_DIR / "htf_backtest"
HTF_FEATURES_DIR = DATA_DIR / "htf_features"
HTF_LABELS_DIR = DATA_DIR / "htf_8class_labels"
HTF_OPTIMIZED_DIR = DATA_DIR / "htf_optimized"
RAW_DATA_DIR = PROJECT_ROOT / "fetchingByBit"

# Create ALL required dirs (robust - works from scratch)
DATA_DIR.mkdir(parents=True, exist_ok=True)
HTF_BACKTEST_DIR.mkdir(parents=True, exist_ok=True)
HTF_FEATURES_DIR.mkdir(parents=True, exist_ok=True)
HTF_LABELS_DIR.mkdir(parents=True, exist_ok=True)
HTF_OPTIMIZED_DIR.mkdir(parents=True, exist_ok=True)

# Timeframes we're working with (5m and 15m only - 1h excluded due to MIN_REMAINING_BARS constraint)
HTF_TIMEFRAMES = ["5m", "15m"]

# Quick validation - check files exist
print("=" * 70)
print("DATA FILES CHECK")
print("=" * 70)
for tf in HTF_TIMEFRAMES:
    ohlcv_path = HTF_BACKTEST_DIR / f"{tf}_HTF_combined.parquet"
    feature_path = HTF_FEATURES_DIR / tf

    ohlcv_exists = "✓" if ohlcv_path.exists() else "✗"
    feature_exists = (
        "✓"
        if feature_path.exists() and list(feature_path.glob("batch_*.parquet"))
        else "○ (will compute)"
    )

    # Get row counts without loading full data
    if ohlcv_path.exists():
        rows = pl.scan_parquet(ohlcv_path).select(pl.len()).collect().item()
        print(f"{tf}: OHLCV {ohlcv_exists} ({rows:,} rows), Features {feature_exists}")
    else:
        print(f"{tf}: OHLCV {ohlcv_exists}, Features {feature_exists}")

print("\n✓ Setup complete. Run next cells to process data.")

# %%
# =============================================================================
# CELL 2.5: ROBUST HTF COMBINED FILE GENERATION
# =============================================================================
# For each timeframe in HTF_TIMEFRAMES:
#   1. Check if {tf}_HTF_combined.parquet exists
#   2. Compare against raw source data (fetchingByBit/sorted-{tf}-bybit-linear/)
#   3. Create/update if raw data is newer or has more rows
#
# This ensures combined files are always in sync with fetched data.
# =============================================================================

from datetime import timedelta
from pathlib import Path

import polars as pl

# Configuration
DATE_START = datetime(2021, 1, 1)
DATE_END = datetime(2026, 2, 1)
FORCE_RECREATE_ALL = False  # Set True to force regenerate everything

# Timeframe config: how many bars per 8h batch
TF_CONFIG = {
    "1m": {"bars_per_8h": 480, "raw_dir": "sorted-1m-bybit-linear"},
    "5m": {"bars_per_8h": 96, "raw_dir": "sorted-5m-bybit-linear"},
    "15m": {"bars_per_8h": 32, "raw_dir": "sorted-15m-bybit-linear"},
    "1h": {"bars_per_8h": 8, "raw_dir": "sorted-1h-bybit-linear"},
    "4h": {"bars_per_8h": 2, "raw_dir": "sorted-4h-bybit-linear"},
}


def get_raw_data_info(tf: str) -> dict:
    """Get info about raw source data for a timeframe."""
    if tf not in TF_CONFIG:
        return {"exists": False, "error": f"Unknown timeframe: {tf}"}

    raw_dir = RAW_DATA_DIR / TF_CONFIG[tf]["raw_dir"]
    if not raw_dir.exists():
        return {"exists": False, "error": f"Raw dir not found: {raw_dir}"}

    files = sorted(raw_dir.glob("*.parquet"))
    if not files:
        return {"exists": False, "error": f"No parquet files in {raw_dir}"}

    # Scan all files lazily to get row count and date range
    lf = pl.scan_parquet(raw_dir / "*.parquet")
    stats = lf.select(
        [
            pl.len().alias("total_rows"),
            pl.col("timestamp").min().alias("min_ts"),
            pl.col("timestamp").max().alias("max_ts"),
        ]
    ).collect()

    return {
        "exists": True,
        "raw_dir": raw_dir,
        "n_files": len(files),
        "total_rows": stats["total_rows"].item(),
        "min_ts": stats["min_ts"].item(),
        "max_ts": stats["max_ts"].item(),
    }


def get_combined_info(tf: str) -> dict:
    """Get info about existing combined file."""
    combined_path = HTF_BACKTEST_DIR / f"{tf}_HTF_combined.parquet"

    if not combined_path.exists():
        return {"exists": False, "path": combined_path}

    lf = pl.scan_parquet(combined_path)
    stats = lf.select(
        [
            pl.len().alias("total_rows"),
            pl.col("timestamp").min().alias("min_ts"),
            pl.col("timestamp").max().alias("max_ts"),
            pl.col("batch_id").max().alias("max_batch"),
        ]
    ).collect()

    return {
        "exists": True,
        "path": combined_path,
        "total_rows": stats["total_rows"].item(),
        "min_ts": stats["min_ts"].item(),
        "max_ts": stats["max_ts"].item(),
        "max_batch": stats["max_batch"].item(),
    }


def create_combined_file(tf: str, raw_info: dict) -> dict:
    """Create or recreate the combined file for a timeframe."""
    bars_per_8h = TF_CONFIG[tf]["bars_per_8h"]
    output_path = HTF_BACKTEST_DIR / f"{tf}_HTF_combined.parquet"

    # Load all raw data
    df_raw = pl.read_parquet(raw_info["raw_dir"] / "*.parquet")

    # Normalize timestamp and filter date range
    df = (
        df_raw.with_columns(
            pl.col("timestamp").dt.replace_time_zone(None).alias("ts_norm")
        )
        .filter((pl.col("ts_norm") >= DATE_START) & (pl.col("ts_norm") < DATE_END))
        .sort("ts_norm")
    )

    # Compute period_8h_start (floor to nearest 8h boundary)
    df = df.with_columns((pl.col("ts_norm").dt.truncate("8h")).alias("period_8h_start"))

    # Assign batch_id (sequential, starting from 1)
    batch_mapping = (
        df.select("period_8h_start")
        .unique()
        .sort("period_8h_start")
        .with_row_index("batch_id")
        .with_columns((pl.col("batch_id") + 1).cast(pl.Int32))
    )

    df = df.join(batch_mapping, on="period_8h_start", how="left")

    # Select and order columns to match expected format
    df_final = df.select(
        [
            "timestamp",
            pl.col("open").cast(pl.Float64),
            pl.col("high").cast(pl.Float64),
            pl.col("low").cast(pl.Float64),
            pl.col("close").cast(pl.Float64),
            pl.col("volume").cast(pl.Float64),
            pl.col("period_8h_start")
            .dt.replace_time_zone("UTC")
            .cast(pl.Datetime("us", "UTC")),
            "batch_id",
        ]
    ).sort(["batch_id", "timestamp"])

    # Check for incomplete batches
    rows_per_batch = df_final.group_by("batch_id").len()
    complete_batches = rows_per_batch.filter(pl.col("len") == bars_per_8h)
    incomplete_batches = rows_per_batch.filter(pl.col("len") != bars_per_8h)

    # Save
    df_final.write_parquet(output_path)

    return {
        "path": output_path,
        "total_rows": len(df_final),
        "n_batches": df_final["batch_id"].n_unique(),
        "complete_batches": len(complete_batches),
        "incomplete_batches": len(incomplete_batches),
        "rows_per_batch": bars_per_8h,
        "date_range": (df_final["timestamp"].min(), df_final["timestamp"].max()),
    }


# =============================================================================
# MAIN: Check and update all timeframes
# =============================================================================
print("=" * 70)
print("HTF COMBINED FILE CHECK & UPDATE")
print("=" * 70)
print(f"Timeframes: {HTF_TIMEFRAMES}")
print(f"Date range: {DATE_START} to {DATE_END}")
print()

results = {}

for tf in HTF_TIMEFRAMES:
    print(f"\n{'─' * 70}")
    print(f"TIMEFRAME: {tf}")
    print(f"{'─' * 70}")

    # Check if timeframe is supported
    if tf not in TF_CONFIG:
        print("  ✗ Unknown timeframe (not in TF_CONFIG)")
        results[tf] = {"status": "error", "reason": "unknown_tf"}
        continue

    # Get raw data info
    raw_info = get_raw_data_info(tf)
    if not raw_info["exists"]:
        print(f"  ✗ Raw data not found: {raw_info.get('error', 'unknown')}")
        results[tf] = {"status": "error", "reason": "no_raw_data"}
        continue

    print(f"  Raw data: {raw_info['total_rows']:,} rows in {raw_info['n_files']} files")
    print(f"  Raw range: {raw_info['min_ts']} to {raw_info['max_ts']}")

    # Get combined file info
    combined_info = get_combined_info(tf)

    # Decide if we need to create/update
    needs_update = False
    update_reason = ""

    if FORCE_RECREATE_ALL:
        needs_update = True
        update_reason = "forced"
    elif not combined_info["exists"]:
        needs_update = True
        update_reason = "missing"
    else:
        print(
            f"  Combined: {combined_info['total_rows']:,} rows, {combined_info['max_batch']} batches"
        )
        print(
            f"  Combined range: {combined_info['min_ts']} to {combined_info['max_ts']}"
        )

        # Check if raw data is newer (has later timestamp)
        raw_max = raw_info["max_ts"]
        combined_max = combined_info["max_ts"]

        # Normalize both to compare (remove timezone if needed)
        if hasattr(raw_max, "replace"):
            raw_max_cmp = (
                raw_max.replace(tzinfo=None) if hasattr(raw_max, "tzinfo") else raw_max
            )
        else:
            raw_max_cmp = raw_max
        if hasattr(combined_max, "replace"):
            combined_max_cmp = (
                combined_max.replace(tzinfo=None)
                if hasattr(combined_max, "tzinfo")
                else combined_max
            )
        else:
            combined_max_cmp = combined_max

        # Compare timestamps
        if raw_max_cmp > combined_max_cmp:
            # Check if there's at least 8h of new data (one complete batch)
            time_diff = raw_max_cmp - combined_max_cmp
            if hasattr(time_diff, "total_seconds"):
                hours_diff = time_diff.total_seconds() / 3600
            else:
                hours_diff = time_diff / timedelta(hours=1)

            if hours_diff >= 8:
                needs_update = True
                update_reason = f"new_data (+{hours_diff:.1f}h)"
            else:
                print(
                    f"  ℹ Raw has {hours_diff:.1f}h more data (< 8h, not enough for new batch)"
                )

    if needs_update:
        print(f"  → Creating/updating ({update_reason})...")
        result = create_combined_file(tf, raw_info)
        print(f"  ✓ Saved: {result['path'].name}")
        print(f"    Rows: {result['total_rows']:,}")
        print(
            f"    Batches: {result['n_batches']} ({result['complete_batches']} complete, {result['incomplete_batches']} incomplete)"
        )
        print(f"    Rows/batch: {result['rows_per_batch']}")
        results[tf] = {"status": "created", **result}
    else:
        print("  ✓ Up to date")
        results[tf] = {"status": "current", **combined_info}

# =============================================================================
# SUMMARY
# =============================================================================
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print(f"{'TF':<6} {'Status':<12} {'Rows':>12} {'Batches':>10} {'Rows/Batch':>12}")
print("-" * 70)

for tf in HTF_TIMEFRAMES:
    r = results.get(tf, {})
    status = r.get("status", "?")
    rows = r.get("total_rows", 0)
    batches = r.get("n_batches", r.get("max_batch", 0))
    expected_rpb = TF_CONFIG.get(tf, {}).get("bars_per_8h", "?")
    actual_rpb = f"{rows / batches:.0f}" if batches else "?"

    status_icon = {"created": "🆕", "current": "✓", "error": "✗"}.get(status, "?")
    print(
        f"{tf:<6} {status_icon} {status:<10} {rows:>12,} {batches:>10} {actual_rpb:>8}/{expected_rpb}"
    )

print("\n✓ All HTF combined files checked.")

# %%
# =============================================================================
# CELL 3: VALIDATE BATCH ALIGNMENT (Load → Validate → Save Results → Free Memory)
# =============================================================================
# Validates that batched LTF data aligns with 8h candles (OPEN & CLOSE match)
# Results saved to parquet so we don't need to keep data in memory
# =============================================================================

SKIP_VALIDATION = False  # Set False to re-run validation

validation_results_path = HTF_BACKTEST_DIR / "validation_results.parquet"

if SKIP_VALIDATION and validation_results_path.exists():
    print("=" * 70)
    print("VALIDATION: Loading cached results")
    print("=" * 70)
    validation_summary = pl.read_parquet(validation_results_path)
    print(validation_summary)
    print("\n✓ Validation already completed. Set SKIP_VALIDATION=False to re-run.")

else:
    print("=" * 70)
    print("VALIDATION: 8h OHLCV vs Batched Data (OPEN & CLOSE Alignment)")
    print("=" * 70)

    # Load 8h reference data (small - only ~5.5K rows)
    df_8h = pl.read_parquet(RAW_DATA_DIR / "sorted-8h-bybit-linear/btcusdt_8h.parquet")
    df_8h = (
        df_8h.with_columns(
            pl.col("timestamp")
            .dt.replace_time_zone(None)
            .cast(pl.Datetime("us"))
            .alias("timestamp_norm")
        )
        .filter(
            (pl.col("timestamp_norm") >= datetime(2021, 1, 1))
            & (pl.col("timestamp_norm") < datetime(2026, 2, 1))
        )
        .sort("timestamp_norm")
    )

    print(f"8h reference data: {len(df_8h):,} rows")

    # Validation function
    def validate_batch_alignment(
        df_ltf: pl.DataFrame, df_8h: pl.DataFrame, tf_name: str
    ) -> dict:
        """Validate that LTF batches align with 8h candles."""
        df_ltf_norm = df_ltf.with_columns(
            pl.col("period_8h_start")
            .dt.replace_time_zone(None)
            .cast(pl.Datetime("us"))
            .alias("period_norm"),
            pl.col("timestamp")
            .dt.replace_time_zone(None)
            .cast(pl.Datetime("us"))
            .alias("ts_norm"),
        )

        batches = (
            df_ltf_norm.sort("ts_norm")
            .group_by("batch_id", "period_norm")
            .agg(
                [
                    pl.col("ts_norm").first().alias("first_ts"),
                    pl.col("open").first().alias("batch_open"),
                    pl.col("close").last().alias("batch_close"),
                ]
            )
            .sort("batch_id")
        )

        df_8h_ref = df_8h.select(
            [
                pl.col("timestamp_norm").alias("period_norm"),
                pl.col("open").alias("ref_open"),
                pl.col("close").alias("ref_close"),
            ]
        )

        validation = batches.join(df_8h_ref, on="period_norm", how="left")
        matched = validation.filter(pl.col("ref_close").is_not_null())

        tolerance = 0.001
        open_ok = matched.filter(
            (pl.col("batch_open") - pl.col("ref_open")).abs() <= tolerance
        )
        close_ok = matched.filter(
            (pl.col("batch_close") - pl.col("ref_close")).abs() <= tolerance
        )

        return {
            "tf": tf_name,
            "total_batches": len(batches),
            "matched": len(matched),
            "open_aligned": len(open_ok),
            "close_aligned": len(close_ok),
            "open_pct": 100 * len(open_ok) / len(matched) if len(matched) > 0 else 0,
            "close_pct": 100 * len(close_ok) / len(matched) if len(matched) > 0 else 0,
        }

    # Run validation for each timeframe (load one at a time to save memory)
    results = []
    for tf in HTF_TIMEFRAMES:
        print(f"\nValidating {tf}...")
        df_ltf = pl.read_parquet(HTF_BACKTEST_DIR / f"{tf}_HTF_combined.parquet")
        r = validate_batch_alignment(df_ltf, df_8h, tf)
        results.append(r)

        status = "✅" if r["open_pct"] == 100 and r["close_pct"] == 100 else "⚠️"
        print(f"  {status} OPEN={r['open_pct']:.1f}%, CLOSE={r['close_pct']:.1f}%")

        # Free memory immediately
        del df_ltf
        gc.collect()

    # Save results
    validation_summary = pl.DataFrame(results)
    validation_summary.write_parquet(validation_results_path)

    # Free 8h data
    del df_8h
    gc.collect()

    print("\n" + "=" * 70)
    print("VALIDATION SUMMARY (saved to validation_results.parquet)")
    print("=" * 70)
    print(validation_summary)
    print("\n✓ Validation complete. Memory freed.")

# %%
# =============================================================================
# CELL 5: HTF FEATURE ENGINEERING (Compute on Full Data, Then Split to Batches)
# =============================================================================
# Features with long windows (xlong=8h) need continuous data to avoid NaN
# Strategy: Compute features on FULL combined data, THEN split into batch files
# Output: data/htf_features/{tf}/batch_{batch_id:04d}.parquet
# =============================================================================

import gc
import importlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from numba import njit

# Add project root to path for imports
project_root = Path.cwd().parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Force reload of the module (in case it was changed)
import scripts.feature_engineering.compute_htf_features as htf_module

importlib.reload(htf_module)
from scripts.feature_engineering.compute_htf_features import HTFFeatureEngine

# =============================================================================
# CONFIGURATION
# =============================================================================
RECOMPUTE_FEATURES = True  # Set True to force recompute all batches

# Ensure bars-per-batch mapping exists (Cell 7 defines it; keep safe default here)
if "BARS_PER_8H" not in globals():
    BARS_PER_8H = {"1m": 480, "5m": 96, "15m": 32}

# Rolling distance feature windows (fixed from IC optimization)
# These are past-window (causal) distances based on OHLCV only.
DISTANCE_WINDOWS_BY_TF = {
    "5m": {
        "dist_avg_high": 48,
        "dist_avg_low": 48,
        "dist_top5_high": 48,
        "dist_bot5_low": 24,
    },
    "15m": {
        "dist_avg_high": 16,
        "dist_avg_low": 16,
        "dist_top5_high": 16,
        "dist_bot5_low": 8,
    },
}
DISTANCE_OUTLIER_PCT = 0.05


@njit
def _compute_past_distance_metrics(close, high, low, bar_pos, window, outlier_pct):
    n = len(close)
    dist_avg_high = np.full(n, np.nan, dtype=np.float64)
    dist_avg_low = np.full(n, np.nan, dtype=np.float64)
    dist_top5_high = np.full(n, np.nan, dtype=np.float64)
    dist_bot5_low = np.full(n, np.nan, dtype=np.float64)

    top_n = max(1, int(window * outlier_pct))

    for i in range(n):
        if bar_pos[i] < window:
            continue

        entry = close[i]
        if entry == 0:
            continue

        start = i - window
        highs = high[start:i]
        lows = low[start:i]

        avg_high = np.mean(highs)
        avg_low = np.mean(lows)

        sorted_highs = np.sort(highs)
        sorted_lows = np.sort(lows)
        avg_top_high = np.mean(sorted_highs[-top_n:])
        avg_bot_low = np.mean(sorted_lows[:top_n])

        dist_avg_high[i] = 100.0 * (avg_high - entry) / entry
        dist_avg_low[i] = 100.0 * (entry - avg_low) / entry
        dist_top5_high[i] = 100.0 * (avg_top_high - entry) / entry
        dist_bot5_low[i] = 100.0 * (entry - avg_bot_low) / entry

    return dist_avg_high, dist_avg_low, dist_top5_high, dist_bot5_low


# Verify paths from Cell 2 exist
assert HTF_BACKTEST_DIR.exists(), f"HTF_BACKTEST_DIR not found: {HTF_BACKTEST_DIR}"

# =============================================================================
# STEP 1: INITIALIZE ENGINE
# =============================================================================
print("=" * 70)
print("HTF FEATURE ENGINEERING PIPELINE")
print("=" * 70)
print(f"Source: {HTF_BACKTEST_DIR}")
print(f"Output: {HTF_FEATURES_DIR}/{{tf}}/batch_XXXX.parquet")
print()
print("Strategy: Compute on FULL data (for long windows), then split to batches")
print()

# Engine for feature computation
engine = HTFFeatureEngine(data_dir=RAW_DATA_DIR, verbose=False)
engine.discover_available_sources()

# =============================================================================
# STEP 2: COMPUTE FEATURES ON FULL DATA, THEN SPLIT TO BATCHES
# =============================================================================
for tf in HTF_TIMEFRAMES:
    print(f"\n{'=' * 70}")
    print(f"PROCESSING {tf.upper()} TIMEFRAME")
    print(f"{'=' * 70}")

    # Create output directory for this timeframe
    tf_output_dir = HTF_FEATURES_DIR / tf
    tf_output_dir.mkdir(parents=True, exist_ok=True)

    # Check if already computed (check for any batch files)
    existing_batches = list(tf_output_dir.glob("batch_*.parquet"))
    if existing_batches and not RECOMPUTE_FEATURES:
        print(
            f"  ✓ {len(existing_batches)} batch files already exist. Set RECOMPUTE_FEATURES=True to recompute."
        )
        continue

    # Clear existing batch files if recomputing
    if RECOMPUTE_FEATURES and existing_batches:
        print(f"  Clearing {len(existing_batches)} existing batch files...")
        for f in existing_batches:
            f.unlink()

    # Load FULL combined data (has batch_id, period_8h_start)
    src_path = HTF_BACKTEST_DIR / f"{tf}_HTF_combined.parquet"
    if not src_path.exists():
        print(f"  ✗ Source file not found: {src_path}")
        continue

    print(f"  Loading full data: {src_path.name}")
    df_full = pl.read_parquet(src_path)
    print(f"  → {len(df_full):,} rows, {df_full['batch_id'].n_unique()} batches")

    # Sort by timestamp for correct rolling window computation
    df_full = df_full.sort("timestamp")

    # Compute bar position inside each batch (for causal past-window distances)
    df_full = df_full.with_columns(
        (pl.cum_count("timestamp").over("batch_id") - 1).alias("bar_pos")
    )
    # Normalized time-within-batch feature (0..1)
    bars_per_batch = BARS_PER_8H[tf]
    df_full = df_full.with_columns(
        ((pl.col("bar_pos") + 1) / bars_per_batch).alias("bar_in_batch_norm")
    )

    # Extract metadata (batch_id, period_8h_start) to rejoin later
    meta_df = df_full.select(
        ["timestamp", "batch_id", "period_8h_start", "bar_in_batch_norm"]
    )

    # Cache bar_pos for distance feature computation
    bar_pos = df_full["bar_pos"].to_numpy().astype(np.int32)

    # Convert to pandas for feature computation (OHLCV only)
    ohlcv_cols = ["timestamp", "open", "high", "low", "close", "volume"]
    df_pd = df_full.select(ohlcv_cols).to_pandas()

    # Free polars data
    del df_full
    gc.collect()

    # Compute features on FULL continuous data
    print(f"  Computing features on full {len(df_pd):,} rows...")
    print("    (This ensures xlong windows have enough history)")
    df_features = engine.compute_features(df=df_pd, target_tf=tf)

    # Compute past-window distance features (causal)
    distance_windows = DISTANCE_WINDOWS_BY_TF.get(tf, {})
    if distance_windows:
        unique_windows = sorted(set(distance_windows.values()))
        close = df_pd["close"].to_numpy()
        high = df_pd["high"].to_numpy()
        low = df_pd["low"].to_numpy()

        dist_feature_map = {}
        for window in unique_windows:
            d_avg_high, d_avg_low, d_top5_high, d_bot5_low = (
                _compute_past_distance_metrics(
                    close, high, low, bar_pos, window, DISTANCE_OUTLIER_PCT
                )
            )

            if distance_windows.get("dist_avg_high") == window:
                dist_feature_map[f"D_dist_avg_high_w{window}"] = d_avg_high
            if distance_windows.get("dist_avg_low") == window:
                dist_feature_map[f"D_dist_avg_low_w{window}"] = d_avg_low
            if distance_windows.get("dist_top5_high") == window:
                dist_feature_map[f"D_dist_top5_high_w{window}"] = d_top5_high
            if distance_windows.get("dist_bot5_low") == window:
                dist_feature_map[f"D_dist_bot5_low_w{window}"] = d_bot5_low

        if dist_feature_map:
            df_features = pd.concat(
                [df_features, pd.DataFrame(dist_feature_map)], axis=1
            )

    # Merge OHLCV back (compute_features returns features + timestamp)
    df_features = pd.concat(
        [df_features, df_pd[["open", "high", "low", "close", "volume"]]], axis=1
    )
    print(f"  → Features computed: {len(df_features.columns)} columns")

    # Convert to polars and join batch metadata
    df_pl = pl.from_pandas(df_features)
    del df_features, df_pd
    gc.collect()

    # Join batch_id and period_8h_start back by timestamp
    df_pl = df_pl.join(meta_df, on="timestamp", how="left")
    del meta_df
    gc.collect()

    # Verify batch_id joined correctly
    null_batch_count = df_pl["batch_id"].null_count()
    if null_batch_count > 0:
        print(f"  ⚠ Warning: {null_batch_count} rows have null batch_id after join")

    # ==========================================================================
    # SPLIT INTO BATCH FILES
    # ==========================================================================
    print("  Splitting into batch files...")
    batch_ids = sorted(df_pl["batch_id"].unique().drop_nulls().to_list())

    for i, batch_id in enumerate(batch_ids):
        out_path = tf_output_dir / f"batch_{batch_id:04d}.parquet"

        # Extract this batch
        df_batch = df_pl.filter(pl.col("batch_id") == batch_id)

        # Save
        df_batch.write_parquet(out_path)

        # Progress every 500 batches
        if (i + 1) % 500 == 0:
            print(f"    Saved {i + 1}/{len(batch_ids)} batches...")

    print(f"  ✓ Saved {len(batch_ids)} batch files to {tf_output_dir.name}/")

    # Clean up
    del df_pl
    gc.collect()

# =============================================================================
# STEP 3: SUMMARY
# =============================================================================
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)

for tf in HTF_TIMEFRAMES:
    tf_dir = HTF_FEATURES_DIR / tf
    if tf_dir.exists():
        batch_files = list(tf_dir.glob("batch_*.parquet"))
        n_batches = len(batch_files)

        # Sample one batch to get feature count
        if batch_files:
            sample = pl.read_parquet(batch_files[0])
            meta_cols = [
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "batch_id",
                "period_8h_start",
            ]
            n_features = len([c for c in sample.columns if c not in meta_cols])
            rows_per_batch = len(sample)
            print(f"\n{tf.upper()}:")
            print(f"  Batches:          {n_batches}")
            print(f"  Rows per batch:   {rows_per_batch}")
            print(f"  Features:         {n_features}")
            print(f"  Location:         {tf_dir}/batch_XXXX.parquet")
    else:
        print(f"\n{tf.upper()}: No batches computed")

print("\n" + "=" * 70)
print("FEATURES READY")
print("=" * 70)
print("✓ Features computed on FULL continuous data (no xlong NaN issue)")
print("✓ Then split into individual batch files")
print("✓ Structure: HTF_FEATURES_DIR/{tf}/batch_{batch_id:04d}.parquet")

# %%
# =============================================================================
# CELL 6: VALIDATE BATCH FEATURE FILES
# =============================================================================
# Validates the batch-by-batch feature files created in Cell 5:
# 1. All batches exist and are readable
# 2. Each batch has correct structure (batch_id, period_8h_start, features)
# 3. No gaps in batch sequence
# 4. Feature values are reasonable (no extreme outliers, NaN patterns ok)
# 5. Timestamps align within each batch
# =============================================================================

from pathlib import Path

import polars as pl

print("=" * 70)
print("VALIDATING BATCH FEATURE FILES")
print("=" * 70)

# Ensure remaining-bars config exists (Cell 7 defines it; keep a safe default here)
if "MIN_REMAINING_BARS_BY_TF" not in globals():
    # Use only current batch; last 3 (5m) or last 1 (15m) bars are unlabeled.
    MIN_REMAINING_BARS_BY_TF = {"5m": 3, "15m": 1}

validation_results = {}

for tf in HTF_TIMEFRAMES:
    print(f"\n{'─' * 70}")
    print(f"{tf.upper()} TIMEFRAME VALIDATION")
    print(f"{'─' * 70}")

    tf_dir = HTF_FEATURES_DIR / tf
    issues = []

    # Check directory exists
    if not tf_dir.exists():
        print(f"  ✗ Directory not found: {tf_dir}")
        validation_results[tf] = {"valid": False, "issues": ["Directory not found"]}
        continue

    # Get all batch files
    batch_files = sorted(tf_dir.glob("batch_*.parquet"))
    n_files = len(batch_files)
    print(f"  Found {n_files} batch files")

    if n_files == 0:
        print("  ✗ No batch files found")
        validation_results[tf] = {"valid": False, "issues": ["No batch files"]}
        continue

    # ==========================================================================
    # CHECK 1: Batch ID sequence (no gaps)
    # ==========================================================================
    batch_ids_from_files = []
    for f in batch_files:
        try:
            batch_num = int(f.stem.split("_")[1])
            batch_ids_from_files.append(batch_num)
        except:
            issues.append(f"Invalid filename: {f.name}")

    batch_ids_from_files = sorted(batch_ids_from_files)
    expected_ids = list(range(min(batch_ids_from_files), max(batch_ids_from_files) + 1))
    missing_ids = set(expected_ids) - set(batch_ids_from_files)

    if missing_ids:
        issues.append(
            f"Missing batch IDs: {sorted(missing_ids)[:10]}{'...' if len(missing_ids) > 10 else ''}"
        )
        print(f"  ⚠ Missing {len(missing_ids)} batch IDs")
    else:
        print(
            f"  ✓ Batch ID sequence complete: {min(batch_ids_from_files)} → {max(batch_ids_from_files)}"
        )

    # ==========================================================================
    # CHECK 2: Sample batches for structure validation
    # ==========================================================================
    # Check first, middle, and last batches
    sample_indices = [0, n_files // 2, n_files - 1]
    required_cols = [
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "batch_id",
        "period_8h_start",
    ]

    rows_per_batch = []
    feature_counts = []

    for idx in sample_indices:
        f = batch_files[idx]
        try:
            df = pl.read_parquet(f)

            # Check required columns
            missing_cols = [c for c in required_cols if c not in df.columns]
            if missing_cols:
                issues.append(f"Batch {f.name}: Missing columns {missing_cols}")

            rows_per_batch.append(len(df))

            # Count features (exclude metadata columns)
            meta_cols = [
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "batch_id",
                "period_8h_start",
            ]
            feature_cols = [c for c in df.columns if c not in meta_cols]
            feature_counts.append(len(feature_cols))

            # Check batch_id consistency within file
            unique_batch_ids = df["batch_id"].unique().to_list()
            if len(unique_batch_ids) != 1:
                issues.append(
                    f"Batch {f.name}: Multiple batch_ids in single file: {unique_batch_ids}"
                )

            # Check timestamps are monotonic
            ts_sorted = df["timestamp"].is_sorted()
            if not ts_sorted:
                issues.append(f"Batch {f.name}: Timestamps not sorted")

        except Exception as e:
            issues.append(f"Batch {f.name}: Read error - {e}")

    # Verify consistent structure across samples
    if len(set(feature_counts)) > 1:
        issues.append(f"Inconsistent feature counts across batches: {feature_counts}")
    else:
        print(f"  ✓ Consistent feature count: {feature_counts[0]} features per batch")

    # Expected rows per batch based on timeframe (features are full 8h windows)
    expected_rows = {"1m": 480, "5m": 96, "15m": 32}
    if tf in expected_rows:
        exp = expected_rows[tf]
        actual_rows = rows_per_batch[0]
        if actual_rows == exp:
            print(
                f"  ✓ Rows per batch: {actual_rows} (expected {exp} for 8h of {tf} data)"
            )
        else:
            print(f"  ⚠ Rows per batch: {actual_rows} (expected {exp})")

        # Labeling excludes last bars (forward-looking metrics).
        if tf in {"5m", "15m"}:
            min_remaining = MIN_REMAINING_BARS_BY_TF.get(tf, 1)
            expected_valid_labels = max(exp - min_remaining, 0)
            print(
                f"  ℹ Expected valid label rows per full batch: {expected_valid_labels} "
                f"(exclude last {min_remaining} bars, last batch may be smaller)"
            )

    # ==========================================================================
    # CHECK 3: Feature value sanity (sample check)
    # ==========================================================================
    # Load a middle batch for detailed checks
    mid_file = batch_files[n_files // 2]
    df_mid = pl.read_parquet(mid_file)

    meta_cols = [
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "batch_id",
        "period_8h_start",
    ]
    feature_cols = [c for c in df_mid.columns if c not in meta_cols]

    # Check for features that are all NaN (bad) vs partially NaN (expected at start)
    all_nan_features = []
    high_nan_features = []

    for col in feature_cols:
        null_pct = df_mid[col].null_count() / len(df_mid) * 100
        if null_pct == 100:
            all_nan_features.append(col)
        elif null_pct > 80:
            high_nan_features.append((col, null_pct))

    if all_nan_features:
        issues.append(f"Features with 100% NaN in sample batch: {all_nan_features[:5]}")
        print(f"  ⚠ {len(all_nan_features)} features are all NaN in sample batch")

    if high_nan_features:
        print(
            f"  ⚠ {len(high_nan_features)} features have >80% NaN (may be expected at batch start)"
        )
    else:
        print("  ✓ Feature NaN patterns look reasonable")

    # Check for infinite values
    for col in feature_cols[:20]:  # Sample first 20 features
        if df_mid[col].dtype in [pl.Float32, pl.Float64]:
            inf_count = df_mid.filter(pl.col(col).is_infinite()).height
            if inf_count > 0:
                issues.append(f"Feature {col} has {inf_count} infinite values")

    # ==========================================================================
    # CHECK 4: Timestamp alignment with batch boundaries
    # ==========================================================================
    first_ts = df_mid["timestamp"][0]
    period_start = df_mid["period_8h_start"][0]

    # First timestamp should equal period_8h_start for the batch
    if str(first_ts)[:19] == str(period_start)[:19]:  # Compare without timezone
        print("  ✓ Timestamps align with 8h period start")
    else:
        issues.append(
            f"Timestamp misalignment: first_ts={first_ts}, period_start={period_start}"
        )
        print("  ⚠ Timestamp alignment issue")

    # ==========================================================================
    # SUMMARY FOR THIS TIMEFRAME
    # ==========================================================================
    is_valid = len(issues) == 0
    validation_results[tf] = {
        "valid": is_valid,
        "n_batches": n_files,
        "n_features": feature_counts[0] if feature_counts else 0,
        "rows_per_batch": rows_per_batch[0] if rows_per_batch else 0,
        "issues": issues,
    }

    if is_valid:
        print(f"\n  ✅ {tf.upper()} VALIDATION PASSED")
    else:
        print(f"\n  ❌ {tf.upper()} VALIDATION FAILED - {len(issues)} issues:")
        for issue in issues[:5]:
            print(f"      - {issue}")

# =============================================================================
# FINAL SUMMARY
# =============================================================================
print("\n" + "=" * 70)
print("VALIDATION SUMMARY")
print("=" * 70)

all_valid = all(r["valid"] for r in validation_results.values())

print(
    f"\n{'Timeframe':<10} {'Batches':>10} {'Features':>10} {'Rows/Batch':>12} {'Status':>10}"
)
print("-" * 55)
for tf, r in validation_results.items():
    status = "✅ PASS" if r["valid"] else "❌ FAIL"
    print(
        f"{tf:<10} {r.get('n_batches', 0):>10} {r.get('n_features', 0):>10} {r.get('rows_per_batch', 0):>12} {status:>10}"
    )

if all_valid:
    print("\n" + "=" * 70)
    print("✅ ALL VALIDATIONS PASSED - BATCH FEATURES READY FOR BACKTEST")
    print("=" * 70)
else:
    print("\n" + "=" * 70)
    print("❌ VALIDATION ISSUES DETECTED - REVIEW BEFORE PROCEEDING")
    print("=" * 70)

# %%
# =============================================================================
# CELL 7: COMPUTE DISTANCE METRICS FOR 8-CLASS TARGET LABELING
# =============================================================================
# Computes per-bar distance metrics for all timeframes:
#   - dist_avg_high: distance to average of remaining highs (%)
#   - dist_avg_low: distance to average of remaining lows (%)
#   - dist_top5_high: distance to top 5% high average (%)
#   - dist_bot5_low: distance to bottom 5% low average (%)
#
# Output Files:
#   - {tf}_distance_metrics.parquet (per-bar metrics)
#   - {tf}_batch_stats.parquet (per-batch aggregates for future 8h labeling)
#   - distance_metrics_summary.json (global stats)
# =============================================================================

import gc
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import polars as pl
from numba import njit

# =============================================================================
# PATHS (redefine here so cell can run standalone)
# =============================================================================
PROJECT_ROOT = Path("..").resolve()
DATA_DIR = PROJECT_ROOT / "data"
HTF_BACKTEST_DIR = DATA_DIR / "htf_backtest"
HTF_LABELS_DIR = DATA_DIR / "htf_8class_labels"
HTF_LABELS_DIR.mkdir(exist_ok=True)

# =============================================================================
# STEP 1.1: CONFIGURATION CONSTANTS
# =============================================================================
# Only use bars within the current batch (no next-batch borrowing).
# This means the last 1 bar (15m) and last 3 bars (5m) are unlabeled
# due to missing forward bars needed for distance metrics.
MIN_REMAINING_BARS_BY_TF = {"5m": 3, "15m": 1}
OUTLIER_PERCENTILE = 0.05  # Top/bottom 5%
BB_PERIOD = 20
BB_STD = 2.0

# Per-timeframe optimal thresholds (used for labeling + batch stats)
TF_THRESHOLDS = {
    "5m": {"BREAKOUT": 1.6, "RISK_RATIO": 2.5},  # MSE=47.21 (structural mismatch)
    "15m": {"BREAKOUT": 2.1, "RISK_RATIO": 2.5},  # MSE=1.39 (perfect fit)
}

# Bars per 8h batch by timeframe
BARS_PER_8H = {"5m": 96, "15m": 32}
BARS_PER_2H = {"5m": 24, "15m": 8}

# Timeframes to process (5m and 15m only)
HTF_TIMEFRAMES = ["5m", "15m"]

RECOMPUTE_DISTANCE_METRICS = True  # Set False to skip recomputation

print("=" * 70)
print("DISTANCE METRICS COMPUTATION FOR 8-CLASS TARGET LABELING")
print("=" * 70)
print(f"Config: MIN_REMAINING_BARS_BY_TF={MIN_REMAINING_BARS_BY_TF}")
print(
    f"        OUTLIER_PERCENTILE={OUTLIER_PERCENTILE}, BB_PERIOD={BB_PERIOD}, BB_STD={BB_STD}"
)
print(f"        TF_THRESHOLDS={TF_THRESHOLDS}")
print("=" * 70)


# =============================================================================
# STEP 1.2: NUMBA FUNCTION FOR PER-BAR METRICS
# =============================================================================
@njit
def compute_distance_metrics(
    close,
    high,
    low,
    batch_id,
    bar_pos,
    bars_per_batch,
    min_remaining,
):
    """
    Compute distance metrics for each bar (current batch only).
    """
    n = len(close)
    dist_avg_high = np.full(n, np.nan, dtype=np.float64)
    dist_avg_low = np.full(n, np.nan, dtype=np.float64)
    dist_top5_high = np.full(n, np.nan, dtype=np.float64)
    dist_bot5_low = np.full(n, np.nan, dtype=np.float64)
    remaining_bars_out = np.full(n, 0, dtype=np.int32)

    outlier_pct = 0.05  # Top/bottom 5%

    for i in range(n):
        entry = close[i]
        current_batch = batch_id[i]

        # Find batch end
        batch_end = i + 1
        while batch_end < n and batch_id[batch_end] == current_batch:
            batch_end += 1

        count = batch_end - (i + 1)
        remaining_bars_out[i] = count

        if count < min_remaining:
            continue

        # Collect remaining highs/lows (current batch only)
        highs = np.zeros(count, dtype=np.float64)
        lows = np.zeros(count, dtype=np.float64)
        for j in range(count):
            highs[j] = high[i + 1 + j]
            lows[j] = low[i + 1 + j]

        # Sort for percentiles
        sorted_highs = np.sort(highs)
        sorted_lows = np.sort(lows)
        top_n = max(1, int(count * outlier_pct))

        # Compute averages
        avg_high = np.mean(highs)
        avg_low = np.mean(lows)
        avg_top_high = np.mean(sorted_highs[-top_n:])
        avg_bot_low = np.mean(sorted_lows[:top_n])

        # Compute distances as percentages
        dist_avg_high[i] = 100.0 * (avg_high - entry) / entry
        dist_avg_low[i] = 100.0 * (entry - avg_low) / entry
        dist_top5_high[i] = 100.0 * (avg_top_high - entry) / entry
        dist_bot5_low[i] = 100.0 * (entry - avg_bot_low) / entry

    return (
        dist_avg_high,
        dist_avg_low,
        dist_top5_high,
        dist_bot5_low,
        remaining_bars_out,
    )


# =============================================================================
# STEP 1.3: PROCESS EACH TIMEFRAME
# =============================================================================
if RECOMPUTE_DISTANCE_METRICS:
    for tf in HTF_TIMEFRAMES:
        print(f"\n{'=' * 50}")
        print(f"Processing {tf}...")
        print("=" * 50)

        # 1. Load data
        input_path = HTF_BACKTEST_DIR / f"{tf}_HTF_combined.parquet"
        df = pl.read_parquet(input_path)
        print(f"  Loaded: {len(df):,} rows")
        df = df.sort(["batch_id", "timestamp"])

        # 2. Compute BB indicators
        df = (
            df.with_columns(
                [
                    pl.col("close")
                    .rolling_mean(window_size=BB_PERIOD)
                    .alias("bb_middle"),
                    pl.col("close").rolling_std(window_size=BB_PERIOD).alias("bb_std"),
                ]
            )
            .with_columns(
                [
                    (pl.col("bb_middle") + BB_STD * pl.col("bb_std")).alias("bb_upper"),
                    (pl.col("bb_middle") - BB_STD * pl.col("bb_std")).alias("bb_lower"),
                ]
            )
            .with_columns(
                [
                    (
                        (pl.col("close") - pl.col("bb_lower"))
                        / (pl.col("bb_upper") - pl.col("bb_lower"))
                        * 100
                    ).alias("bb_position_pct"),
                ]
            )
        )

        # 3. Compute bar position within batch
        df = df.with_columns(
            (pl.col("timestamp").rank("ordinal").over("batch_id") - 1)
            .cast(pl.Int32)
            .alias("bar_pos")
        )

        # 4. Filter batches robustly:
        #    - keep full batches
        #    - also keep LAST (possibly incomplete) batch if it has enough bars
        bars_per_batch = BARS_PER_8H[tf]
        min_remaining = MIN_REMAINING_BARS_BY_TF.get(tf, 1)
        # Keep last batch even if incomplete, as long as it can provide labels
        min_last_batch_bars = min_remaining + 1

        batch_counts = df.group_by("batch_id").agg(pl.len().alias("n")).sort("batch_id")
        last_batch_id = batch_counts["batch_id"].max()
        valid_batches = batch_counts.filter(
            (pl.col("n") == bars_per_batch)
            | (
                (pl.col("batch_id") == last_batch_id)
                & (pl.col("n") >= min_last_batch_bars)
            )
        )["batch_id"].to_list()

        df = df.filter(pl.col("batch_id").is_in(valid_batches))
        print(
            f"  Valid batches: {len(valid_batches):,} ({len(df):,} rows) "
            f"(last batch allowed if >= {min_last_batch_bars} bars)"
        )

        # 5. Add 2h segment column
        df = df.with_columns((pl.col("bar_pos") // BARS_PER_2H[tf]).alias("segment_2h"))

        # 6. Run numba function
        close_np = df["close"].to_numpy()
        high_np = df["high"].to_numpy()
        low_np = df["low"].to_numpy()
        batch_id_np = df["batch_id"].to_numpy()
        bar_pos_np = df["bar_pos"].to_numpy()

        d_avg_high, d_avg_low, d_top5_high, d_bot5_low, remaining = (
            compute_distance_metrics(
                close_np,
                high_np,
                low_np,
                batch_id_np,
                bar_pos_np,
                bars_per_batch,
                min_remaining,
            )
        )

        # 7. Add columns to dataframe
        df = df.with_columns(
            [
                pl.Series("dist_avg_high", d_avg_high),
                pl.Series("dist_avg_low", d_avg_low),
                pl.Series("dist_top5_high", d_top5_high),
                pl.Series("dist_bot5_low", d_bot5_low),
                pl.Series("remaining_bars", remaining),
            ]
        )

        # Count valid bars
        valid_count = len(df.filter(pl.col("dist_avg_high").is_not_nan()))
        print(
            f"  Valid bars (with metrics): {valid_count:,} ({100 * valid_count / len(df):.1f}%)"
        )

        # 8. Save per-bar metrics
        output_path = HTF_BACKTEST_DIR / f"{tf}_distance_metrics.parquet"
        df.write_parquet(output_path)
        print(f"  ✓ Saved {output_path.name}")

        del df
        gc.collect()

    print("\n" + "=" * 70)
    print("PHASE 1.3 COMPLETE: Distance metrics computed for all timeframes")
    print("=" * 70)
else:
    print("Skipping recomputation (RECOMPUTE_DISTANCE_METRICS=False)")


# =============================================================================
# STEP 1.4: COMPUTE PER-BATCH AGGREGATES
# =============================================================================
print("\n" + "=" * 70)
print("STEP 1.4: COMPUTING PER-BATCH AGGREGATES")
print("=" * 70)


@njit
def compute_8class_label_numba(
    dist_avg_high,
    dist_avg_low,
    dist_top5_high,
    dist_bot5_low,
    breakout_thresh,
    risk_ratio,
):
    """Compute 8-class label for a single bar."""
    if np.isnan(dist_avg_high):
        return -1  # Invalid

    epsilon = 1e-10
    is_breakout_up = dist_avg_low < 0
    is_breakout_down = dist_avg_high < 0

    # Direction
    if is_breakout_up:
        is_up = True
    elif is_breakout_down:
        is_up = False
    else:
        is_up = dist_avg_high > dist_avg_low

    # Risk flags (dual threshold)
    if is_breakout_up:
        high_risk_up = dist_top5_high > breakout_thresh
        high_risk_down = False
    elif is_breakout_down:
        high_risk_up = False
        high_risk_down = dist_bot5_low > breakout_thresh
    else:
        high_risk_up = (dist_top5_high / (dist_avg_high + epsilon)) > risk_ratio
        high_risk_down = (dist_bot5_low / (dist_avg_low + epsilon)) > risk_ratio

    if is_up:
        if high_risk_up and high_risk_down:
            return 5  # UP_VOLATILE
        elif high_risk_up:
            return 4  # UP_CONT
        elif high_risk_down:
            return 6  # UP_REVERSAL_RISK
        else:
            return 3  # UP_BALANCED
    else:
        if high_risk_up and high_risk_down:
            return 2  # DOWN_VOLATILE
        elif high_risk_down:
            return 1  # DOWN_CONT
        elif high_risk_up:
            return 7  # DOWN_REVERSAL_RISK
        else:
            return 0  # DOWN_BALANCED


@njit
def compute_8class_labels_batch(
    dist_avg_high,
    dist_avg_low,
    dist_top5_high,
    dist_bot5_low,
    breakout_thresh,
    risk_ratio,
):
    """Vectorized 8-class labeling using numba."""
    n = len(dist_avg_high)
    labels = np.full(n, -1, dtype=np.int8)
    for i in range(n):
        labels[i] = compute_8class_label_numba(
            dist_avg_high[i],
            dist_avg_low[i],
            dist_top5_high[i],
            dist_bot5_low[i],
            breakout_thresh,
            risk_ratio,
        )
    return labels


for tf in HTF_TIMEFRAMES:
    print(f"\nProcessing {tf} batch stats...")

    # Load distance metrics
    df = pl.read_parquet(HTF_BACKTEST_DIR / f"{tf}_distance_metrics.parquet")

    thresholds = TF_THRESHOLDS.get(tf)
    if thresholds is None:
        print(f"  ⚠️ No thresholds for {tf}, skipping batch stats")
        del df
        gc.collect()
        continue

    # Compute 8-class labels using numba
    labels = compute_8class_labels_batch(
        df["dist_avg_high"].to_numpy(),
        df["dist_avg_low"].to_numpy(),
        df["dist_top5_high"].to_numpy(),
        df["dist_bot5_low"].to_numpy(),
        thresholds["BREAKOUT"],
        thresholds["RISK_RATIO"],
    )
    df = df.with_columns(pl.Series("target_8class", labels))

    # Re-save with labels
    df.write_parquet(HTF_BACKTEST_DIR / f"{tf}_distance_metrics.parquet")

    # Check if we have valid data for batch stats
    valid_df = df.filter(pl.col("target_8class") >= 0)
    if len(valid_df) == 0:
        print(f"  ⚠️ No valid bars for {tf}, skipping batch stats")
        del df
        gc.collect()
        continue

    # Aggregate per batch
    batch_stats = valid_df.group_by("batch_id").agg(
        [
            (pl.col("target_8class") == 0).sum().alias("class_0_count"),
            (pl.col("target_8class") == 1).sum().alias("class_1_count"),
            (pl.col("target_8class") == 2).sum().alias("class_2_count"),
            (pl.col("target_8class") == 3).sum().alias("class_3_count"),
            (pl.col("target_8class") == 4).sum().alias("class_4_count"),
            (pl.col("target_8class") == 5).sum().alias("class_5_count"),
            (pl.col("target_8class") == 6).sum().alias("class_6_count"),
            (pl.col("target_8class") == 7).sum().alias("class_7_count"),
            pl.len().alias("valid_bars"),
            (pl.col("target_8class").is_in([3, 4, 5, 6])).mean().alias("up_pct"),
            pl.col("dist_top5_high").mean().alias("avg_top5_high"),
            pl.col("dist_bot5_low").mean().alias("avg_bot5_low"),
            ((pl.col("target_8class").is_in([1, 2, 4, 5, 6, 7])).mean()).alias(
                "outlier_frequency"
            ),
        ]
    )

    # Compute dominant class
    class_cols = [f"class_{i}_count" for i in range(8)]
    batch_stats = batch_stats.with_columns(
        pl.concat_list(class_cols).list.arg_max().alias("dominant_class")
    )

    # Compute volatility regime (with None handling)
    global_avg_outlier = batch_stats["avg_top5_high"].mean()
    if global_avg_outlier is not None and len(batch_stats) > 0:
        batch_stats = batch_stats.with_columns(
            pl.when(pl.col("avg_top5_high") > global_avg_outlier * 1.5)
            .then(pl.lit("HIGH"))
            .when(pl.col("avg_top5_high") < global_avg_outlier * 0.5)
            .then(pl.lit("LOW"))
            .otherwise(pl.lit("NORMAL"))
            .alias("volatility_regime")
        )
        batch_stats = batch_stats.with_columns(
            pl.when(pl.col("up_pct") > 0.6)
            .then(pl.lit("BULLISH"))
            .when(pl.col("up_pct") < 0.4)
            .then(pl.lit("BEARISH"))
            .otherwise(pl.lit("NEUTRAL"))
            .alias("direction_bias")
        )
    else:
        batch_stats = batch_stats.with_columns(
            [
                pl.lit("UNKNOWN").alias("volatility_regime"),
                pl.lit("UNKNOWN").alias("direction_bias"),
            ]
        )

    # Save batch stats
    output_path = HTF_BACKTEST_DIR / f"{tf}_batch_stats.parquet"
    batch_stats.write_parquet(output_path)
    print(f"  ✓ Saved {output_path.name}: {len(batch_stats):,} batches")

    # Print quick class distribution
    total = len(valid_df)
    print(f"  Class distribution (n={total:,}):")
    for cls in range(8):
        count = len(valid_df.filter(pl.col("target_8class") == cls))
        pct = 100 * count / total if total > 0 else 0
        print(f"    {cls}: {count:>8,} ({pct:>5.1f}%)")

    del df, batch_stats, valid_df
    gc.collect()

print("\n" + "=" * 70)
print("STEP 1.4 COMPLETE: Batch aggregates saved")
print("=" * 70)


# =============================================================================
# STEP 1.5: SAVE SUMMARY JSON
# =============================================================================
print("\n" + "=" * 70)
print("STEP 1.5: SAVING SUMMARY JSON")
print("=" * 70)

summary = {
    "computed_at": datetime.now().isoformat(),
    "parameters": {
        "MIN_REMAINING_BARS_BY_TF": MIN_REMAINING_BARS_BY_TF,
        "OUTLIER_PERCENTILE": OUTLIER_PERCENTILE,
        "BB_PERIOD": BB_PERIOD,
        "BB_STD": BB_STD,
        "TF_THRESHOLDS": TF_THRESHOLDS,
    },
    "timeframes": {},
}

for tf in HTF_TIMEFRAMES:
    df = pl.read_parquet(HTF_BACKTEST_DIR / f"{tf}_distance_metrics.parquet")
    df_valid = df.filter(pl.col("dist_avg_high").is_not_nan())

    # Handle empty or None stats
    if len(df_valid) > 0:
        avg_high = df_valid["dist_avg_high"].mean()
        avg_low = df_valid["dist_avg_low"].mean()
        top5_high = df_valid["dist_top5_high"].mean()
        bot5_low = df_valid["dist_bot5_low"].mean()
        global_stats = {
            "dist_avg_high_mean": float(avg_high) if avg_high is not None else None,
            "dist_avg_low_mean": float(avg_low) if avg_low is not None else None,
            "dist_top5_high_mean": float(top5_high) if top5_high is not None else None,
            "dist_bot5_low_mean": float(bot5_low) if bot5_low is not None else None,
        }
    else:
        global_stats = {
            "dist_avg_high_mean": None,
            "dist_avg_low_mean": None,
            "dist_top5_high_mean": None,
            "dist_bot5_low_mean": None,
        }

    summary["timeframes"][tf] = {
        "total_bars": len(df),
        "valid_bars": len(df_valid),
        "complete_batches": df["batch_id"].n_unique(),
        "global_stats": global_stats,
    }
    del df, df_valid

summary_path = HTF_BACKTEST_DIR / "distance_metrics_summary.json"
with open(summary_path, "w") as f:
    json.dump(summary, f, indent=2)

print(f"✓ Saved {summary_path.name}")
print("\nSummary contents:")
print(json.dumps(summary, indent=2))

gc.collect()
print("\n" + "=" * 70)
print("PHASE 1 COMPLETE: All distance metrics, batch stats, and summary saved")
print("=" * 70)

# %%
# =============================================================================
# CELL 8: 8-CLASS TARGET LABELING (15m IMPLEMENTATION)
# =============================================================================
# Implements the validated 8-class labeling system:
#   - Precomputed distance metrics from Cell 7
#   - Per-timeframe optimal thresholds from grid search
#
# Classes:
#   0: DOWN_BALANCED     - Down direction, no extreme outliers
#   1: DOWN_CONT         - Down with strong downside momentum
#   2: DOWN_VOLATILE     - Down with both-side outliers
#   3: UP_BALANCED       - Up direction, no extreme outliers
#   4: UP_CONT           - Up with strong upside momentum
#   5: UP_VOLATILE       - Up with both-side outliers
#   6: UP_REVERSAL_RISK  - Up but has significant downside outliers
#   7: DOWN_REVERSAL_RISK- Down but has significant upside outliers
#
# Output: {tf}_labels.parquet in HTF_LABELS_DIR (target_8class)
# =============================================================================

import json
from pathlib import Path

import polars as pl

# =============================================================================
# PATHS
# =============================================================================
PROJECT_ROOT = Path("..").resolve()
DATA_DIR = PROJECT_ROOT / "data"
HTF_BACKTEST_DIR = DATA_DIR / "htf_backtest"
HTF_LABELS_DIR = DATA_DIR / "htf_8class_labels"
HTF_LABELS_DIR.mkdir(exist_ok=True)

# =============================================================================
# PER-TIMEFRAME OPTIMAL THRESHOLDS (from grid search)
# (Defined in STEP 1.1 above; reused here)
# =============================================================================

# Class names for display
CLASS_NAMES = {
    0: "DOWN_BALANCED",
    1: "DOWN_CONT",
    2: "DOWN_VOLATILE",
    3: "UP_BALANCED",
    4: "UP_CONT",
    5: "UP_VOLATILE",
    6: "UP_REVERSAL_RISK",
    7: "DOWN_REVERSAL_RISK",
}

# Doc target distribution for validation
DOC_TARGETS = {0: 25.5, 1: 11.2, 2: 9.8, 3: 28.4, 4: 9.5, 5: 9.6, 6: 3.5, 7: 2.6}

# Breakfree threshold (end-of-batch close distance)
# end_return = (close_end - close_now) / close_now
BREAKFREE_THRESHOLD = 0.001  # 0.10%
# Only consider entries in the first 4h of each 8h batch
ENTRY_WINDOW_HOURS = 4

# Which timeframes to process (15m first since it matches perfectly)
PROCESS_TIMEFRAMES = ["15m"]  # Add "5m" later with 5m-specific targets

RECOMPUTE_LABELS = True

print("=" * 70)
print("8-CLASS TARGET LABELING")
print("=" * 70)
print(f"Processing timeframes: {PROCESS_TIMEFRAMES}")
print(f"Output directory: {HTF_LABELS_DIR}")
print(f"Min remaining bars per TF: {MIN_REMAINING_BARS_BY_TF} (exclude last bars)")
print(f"Entry window: first {ENTRY_WINDOW_HOURS}h of each 8h batch")
print("=" * 70)


# =============================================================================
# LABELING FUNCTION (VECTORIZED POLARS)
# =============================================================================
def compute_8class_labels(
    df: pl.DataFrame, breakout_thresh: float, risk_thresh: float
) -> pl.DataFrame:
    """
    Compute 8-class labels using vectorized Polars expressions.

    Logic:
    - BREAKOUT UP (dist_avg_low < 0): Direction is UP, check top5_high > breakout_thresh
    - BREAKOUT DOWN (dist_avg_high < 0): Direction is DOWN, check bot5_low > breakout_thresh
    - OSCILLATION (both > 0): Use ratio-based risk flags
    """
    eps = 1e-10

    # Scenario detection
    df = df.with_columns(
        [
            (pl.col("dist_avg_low") < 0).alias("is_breakout_up"),
            (pl.col("dist_avg_high") < 0).alias("is_breakout_down"),
            ((pl.col("dist_avg_low") > 0) & (pl.col("dist_avg_high") > 0)).alias(
                "is_oscillation"
            ),
        ]
    )

    # Direction: breakout UP → UP, breakout DOWN → DOWN, oscillation → compare avgs
    df = df.with_columns(
        [
            pl.when(pl.col("is_breakout_up"))
            .then(pl.lit(True))
            .when(pl.col("is_breakout_down"))
            .then(pl.lit(False))
            .otherwise(pl.col("dist_avg_high") > pl.col("dist_avg_low"))
            .alias("is_up")
        ]
    )

    # Risk flags
    # For breakouts: use absolute threshold
    # For oscillation: use ratio threshold
    df = df.with_columns(
        [
            # high_risk_up
            pl.when(pl.col("is_breakout_up"))
            .then(pl.col("dist_top5_high") > breakout_thresh)
            .when(pl.col("is_breakout_down"))
            .then(pl.lit(False))  # Ignore upside in breakout DOWN
            .otherwise(
                (pl.col("dist_top5_high") / (pl.col("dist_avg_high") + eps))
                > risk_thresh
            )
            .alias("high_risk_up"),
            # high_risk_down
            pl.when(pl.col("is_breakout_down"))
            .then(pl.col("dist_bot5_low") > breakout_thresh)
            .when(pl.col("is_breakout_up"))
            .then(pl.lit(False))  # Ignore downside in breakout UP
            .otherwise(
                (pl.col("dist_bot5_low") / (pl.col("dist_avg_low") + eps)) > risk_thresh
            )
            .alias("high_risk_down"),
        ]
    )

    # Compute 8-class label
    df = df.with_columns(
        [
            pl.when(pl.col("dist_avg_high").is_nan())
            .then(pl.lit(-1))  # Invalid bar
            # UP direction classes
            .when(pl.col("is_up") & pl.col("high_risk_up") & pl.col("high_risk_down"))
            .then(pl.lit(5))  # UP_VOLATILE
            .when(pl.col("is_up") & pl.col("high_risk_up") & ~pl.col("high_risk_down"))
            .then(pl.lit(4))  # UP_CONT
            .when(pl.col("is_up") & ~pl.col("high_risk_up") & pl.col("high_risk_down"))
            .then(pl.lit(6))  # UP_REVERSAL_RISK
            .when(pl.col("is_up") & ~pl.col("high_risk_up") & ~pl.col("high_risk_down"))
            .then(pl.lit(3))  # UP_BALANCED
            # DOWN direction classes
            .when(~pl.col("is_up") & pl.col("high_risk_up") & pl.col("high_risk_down"))
            .then(pl.lit(2))  # DOWN_VOLATILE
            .when(~pl.col("is_up") & ~pl.col("high_risk_up") & pl.col("high_risk_down"))
            .then(pl.lit(1))  # DOWN_CONT
            .when(~pl.col("is_up") & pl.col("high_risk_up") & ~pl.col("high_risk_down"))
            .then(pl.lit(7))  # DOWN_REVERSAL_RISK
            .when(
                ~pl.col("is_up") & ~pl.col("high_risk_up") & ~pl.col("high_risk_down")
            )
            .then(pl.lit(0))  # DOWN_BALANCED
            .otherwise(pl.lit(-1))
            .alias("target_8class")
        ]
    )

    # Add class name column
    df = df.with_columns(
        [
            pl.col("target_8class")
            .replace_strict(
                {i: name for i, name in CLASS_NAMES.items()}, default="INVALID"
            )
            .alias("target_name")
        ]
    )

    # Clean up intermediate columns
    df = df.drop(
        [
            "is_breakout_up",
            "is_breakout_down",
            "is_oscillation",
            "is_up",
            "high_risk_up",
            "high_risk_down",
        ]
    )

    return df


# =============================================================================
# PROCESS EACH TIMEFRAME
# =============================================================================
results = {}

for tf in PROCESS_TIMEFRAMES:
    print(f"\n{'=' * 30} {tf.upper()} {'=' * 30}")

    # Get thresholds
    thresholds = TF_THRESHOLDS[tf]
    bt = thresholds["BREAKOUT"]
    rt = thresholds["RISK_RATIO"]
    print(f"Thresholds: BREAKOUT={bt}%, RISK_RATIO={rt}x")

    # Load distance metrics
    metrics_path = HTF_BACKTEST_DIR / f"{tf}_distance_metrics.parquet"
    if not metrics_path.exists():
        print(f"  ⚠️ Distance metrics not found: {metrics_path}")
        print("     Run Cell 7 first to compute distance metrics")
        continue

    print(f"Loading: {metrics_path.name}")
    df = pl.read_parquet(metrics_path)
    print(f"  → {len(df):,} rows")

    # Compute end-of-batch close distance for breakfree target
    batch_close = df.group_by("batch_id").agg(
        pl.col("close").sort_by("timestamp").last().alias("close_end")
    )
    df = df.join(batch_close, on="batch_id", how="left").with_columns(
        ((pl.col("close_end") - pl.col("close")) / pl.col("close")).alias("end_return")
    )

    # Filter valid rows (current batch only), then keep first 4h entry window
    entry_bar_limit = int(BARS_PER_8H[tf] * (ENTRY_WINDOW_HOURS / 8.0))
    df_valid = df.filter(
        pl.col("dist_avg_high").is_not_nan() & (pl.col("bar_pos") < entry_bar_limit)
    )
    n_valid = len(df_valid)
    n_invalid = len(df) - n_valid
    print(
        f"  → {n_valid:,} valid rows, {n_invalid:,} invalid (insufficient remaining bars)"
    )
    expected_valid = min(
        BARS_PER_8H[tf] - MIN_REMAINING_BARS_BY_TF.get(tf, 1),
        entry_bar_limit,
    )
    print(
        f"  Expected valid rows per full batch: {expected_valid} "
        f"(first {ENTRY_WINDOW_HOURS}h only)"
    )

    if n_valid == 0:
        print(f"  ⚠️ No valid rows for {tf}. Skipping.")
        continue

    # Compute 8-class labels
    print("Computing 8-class labels...")
    df_labeled = compute_8class_labels(df_valid, bt, rt)

    # Breakfree binary target (1=up, 0=down, -1=neutral)
    df_labeled = df_labeled.with_columns(
        [
            pl.when(pl.col("end_return") >= BREAKFREE_THRESHOLD)
            .then(pl.lit(1))
            .when(pl.col("end_return") <= -BREAKFREE_THRESHOLD)
            .then(pl.lit(0))
            .otherwise(pl.lit(-1))
            .alias("target_breakfree")
        ]
    )

    # ==========================================================================
    # VALIDATE CLASS DISTRIBUTION
    # ==========================================================================
    print(f"\n{'─' * 60}")
    print("CLASS DISTRIBUTION VALIDATION")
    print(f"{'─' * 60}")

    class_counts = (
        df_labeled.filter(pl.col("target_8class") >= 0)
        .group_by("target_8class")
        .agg(pl.len().alias("count"))
        .sort("target_8class")
    )

    total = class_counts["count"].sum()

    print(
        f"\n{'Class':<3} {'Name':<20} {'Count':>10} {'Actual':>8} {'Target':>8} {'Diff':>8} {'Status'}"
    )
    print("-" * 75)

    mse = 0.0
    for cls in range(8):
        row = class_counts.filter(pl.col("target_8class") == cls)
        count = row["count"][0] if len(row) > 0 else 0
        pct = 100 * count / total if total > 0 else 0
        target = DOC_TARGETS[cls]
        diff = pct - target
        mse += diff**2
        status = "✓" if abs(diff) < 2 else "≈" if abs(diff) < 5 else "✗"
        print(
            f"{cls:<3} {CLASS_NAMES[cls]:<20} {count:>10,} {pct:>7.1f}% {target:>7.1f}% {diff:>+7.1f}% {status}"
        )

    print(f"\nMSE to doc targets: {mse:.2f}")

    # Group summary
    print(f"\n{'─' * 60}")
    print("GROUP SUMMARY")
    print(f"{'─' * 60}")

    groups = {
        "BALANCED": [0, 3],
        "CONT": [1, 4],
        "VOLATILE": [2, 5],
        "REVERSAL": [6, 7],
    }
    doc_group = {"BALANCED": 53.9, "CONT": 20.7, "VOLATILE": 19.4, "REVERSAL": 6.1}

    for name, classes in groups.items():
        group_count = sum(
            class_counts.filter(pl.col("target_8class") == c)["count"][0]
            if len(class_counts.filter(pl.col("target_8class") == c)) > 0
            else 0
            for c in classes
        )
        pct = 100 * group_count / total if total > 0 else 0
        target = doc_group[name]
        print(f"  {name:<12}: {pct:>6.1f}% (target: {target:.1f}%)")

    # ==========================================================================
    # SAVE LABELED DATA (PER-BATCH for downstream compatibility)
    # ==========================================================================
    tf_labels_dir = HTF_LABELS_DIR / tf
    tf_labels_dir.mkdir(exist_ok=True)
    print(f"\nSaving per-batch files to: {tf_labels_dir}")

    # Select relevant columns (consistent with 5m hybrid schema)
    output_cols = [
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",  # OHLCV
        "batch_id",
        "bar_pos",
        "remaining_bars",  # Batch info
        "bb_upper",
        "bb_lower",
        "bb_middle",
        "bb_position_pct",  # BB indicators
        "segment_2h",  # 2h segment (0-3)
        "dist_avg_high",
        "dist_avg_low",
        "dist_top5_high",
        "dist_bot5_low",  # Distance metrics
        "close_end",
        "end_return",
        "target_8class",
        "target_name",
        "target_breakfree",
        # Labels
    ]

    # Only keep columns that exist
    available_cols = [c for c in output_cols if c in df_labeled.columns]
    df_output = df_labeled.select(available_cols)

    # Save per-batch (8h aligned)
    batch_ids = df_output["batch_id"].unique().sort().to_list()
    for bid in batch_ids:
        batch_df = df_output.filter(pl.col("batch_id") == bid)
        batch_path = tf_labels_dir / f"batch_{bid:04d}.parquet"
        batch_df.write_parquet(batch_path)

    print(f"  ✓ Saved {len(batch_ids):,} batch files ({len(df_output):,} total rows)")

    results[tf] = {
        "batches": len(batch_ids),
        "rows": len(df_output),
        "mse": mse,
        "thresholds": thresholds,
    }

    del df, df_valid, df_labeled, df_output
    import gc

    gc.collect()

# =============================================================================
# SUMMARY
# =============================================================================
print("\n" + "=" * 70)
print("8-CLASS LABELING COMPLETE")
print("=" * 70)

for tf, res in results.items():
    print(f"\n{tf}:")
    print(f"  Batches: {res['batches']:,}")
    print(f"  Rows: {res['rows']:,}")
    print(f"  MSE: {res['mse']:.2f}")
    print(
        f"  Thresholds: BREAKOUT={res['thresholds']['BREAKOUT']}%, RISK_RATIO={res['thresholds']['RISK_RATIO']}x"
    )
    print(f"  Output: {HTF_LABELS_DIR / tf}/batch_*.parquet")

print(f"\n{'=' * 70}")
print("NEXT STEPS")
print("=" * 70)
print("1. Use target_8class as ML target for classification")
print("2. Filter to valid rows (target_8class >= 0)")
print("3. Train model to predict class given features")
print("4. For 5m: use 5m-specific targets (see docs/5m_target_labeling_findings.md)")
print("=" * 70)

# %%
# =============================================================================
# CELL 9: HYBRID 5m TARGET LABELING (5m ENTRY + 15m DISTANCE METRICS)
# =============================================================================
# This cell implements a hybrid approach for 5m timeframe:
#   - Entry reference: 5m close (granular entry timing)
#   - Distance metrics: computed from remaining 15m bars (smoother targets)
#
# Why this works:
#   - Each 5m bar gets unique distances because entry close differs
#   - But the future bars used are 15m (less noisy than 5m)
#   - Inherits 15m's better oscillation/breakout distribution (~26% vs 16%)
#
# Current-batch only:
#   - No next-batch borrowing
#   - Last 3 (5m) bars of each batch are unlabeled (need 1 remaining 15m bar)
#
# Output: data/htf_8class_labels/5m_hybrid_labels.parquet
# =============================================================================

import gc
from pathlib import Path

import polars as pl
from numba import njit

# =============================================================================
# PATHS
# =============================================================================
PROJECT_ROOT = Path("..").resolve()
DATA_DIR = PROJECT_ROOT / "data"
HTF_BACKTEST_DIR = DATA_DIR / "htf_backtest"
HTF_LABELS_DIR = DATA_DIR / "htf_8class_labels"
HTF_LABELS_DIR.mkdir(exist_ok=True)

# =============================================================================
# CONFIGURATION
# =============================================================================
# Use only current batch for hybrid 5m labeling
# Requires at least 1 remaining 15m bar => last 3 (5m) bars are unlabeled
MIN_REMAINING_BARS_15M = 1  # remaining 15m bars needed
MIN_REMAINING_BARS_5M = MIN_REMAINING_BARS_15M * 3  # 3x 5m bars per 15m bar
OUTLIER_PERCENTILE = 0.05  # Top/bottom 5%
BB_PERIOD = 20
BB_STD = 2.0
BARS_PER_8H_15M = 32  # 15m bars per 8h batch
BARS_PER_8H_5M = 96  # 5m bars per 8h batch
FINISH_THRESHOLD = 0.001  # 0.10% end-close threshold

# Optimal thresholds from grid search (same as 15m!)
BREAKOUT_THRESHOLD = 2.1  # % (absolute distance for breakout continuation)
RISK_RATIO = 2.5  # x (ratio threshold for oscillation risk)
# Only consider entries in the first 4h of each 8h batch
ENTRY_WINDOW_HOURS_5M = 4

# Class definitions
CLASS_NAMES = {
    0: "DOWN_BALANCED",
    1: "DOWN_CONT",
    2: "DOWN_VOLATILE",
    3: "UP_BALANCED",
    4: "UP_CONT",
    5: "UP_VOLATILE",
    6: "UP_REVERSAL_RISK",
    7: "DOWN_REVERSAL_RISK",
}

# CORRECT DOC_TARGETS (from Cell 8 / target_labeling_implementation.md)
DOC_TARGETS = {0: 25.5, 1: 11.2, 2: 9.8, 3: 28.4, 4: 9.5, 5: 9.6, 6: 3.5, 7: 2.6}

print("=" * 70)
print("HYBRID 5m TARGET LABELING (5m Entry + 15m Distance Metrics)")
print("=" * 70)
print(f"Thresholds: BREAKOUT={BREAKOUT_THRESHOLD}%, RISK_RATIO={RISK_RATIO}x")
print(f"Entry window: first {ENTRY_WINDOW_HOURS_5M}h of each 8h batch")
print("=" * 70)

# =============================================================================
# STEP 1: LOAD 5m AND 15m DATA
# =============================================================================
print("\n[STEP 1] Loading data...")

df_5m = pl.read_parquet(HTF_BACKTEST_DIR / "5m_HTF_combined.parquet").sort("timestamp")
df_15m = pl.read_parquet(HTF_BACKTEST_DIR / "15m_HTF_combined.parquet").sort(
    "timestamp"
)

print(f"  5m bars: {len(df_5m):,}")
print(f"  15m bars: {len(df_15m):,}")

# Filter to valid batches (allow last incomplete batch if it has enough bars)
counts_5m = df_5m.group_by("batch_id").agg(pl.len().alias("n")).sort("batch_id")
counts_15m = df_15m.group_by("batch_id").agg(pl.len().alias("n")).sort("batch_id")

last_5m = counts_5m["batch_id"].max()
last_15m = counts_15m["batch_id"].max()

min_last_5m = MIN_REMAINING_BARS_5M + 1  # minimum to label any 5m rows
min_last_15m_label = MIN_REMAINING_BARS_15M + 1  # minimum to label any 15m rows

valid_5m = counts_5m.filter(
    (pl.col("n") == BARS_PER_8H_5M)
    | ((pl.col("batch_id") == last_5m) & (pl.col("n") >= min_last_5m))
)["batch_id"].to_list()
valid_15m_for_label = counts_15m.filter(
    (pl.col("n") == BARS_PER_8H_15M)
    | ((pl.col("batch_id") == last_15m) & (pl.col("n") >= min_last_15m_label))
)["batch_id"].to_list()
# Batches we actually label (need valid 5m + valid 15m label support)
label_batches = set(valid_5m) & set(valid_15m_for_label)

print(
    f"  Label batches (both TFs): {len(label_batches):,} "
    f"(last batch labels if >= {min_last_5m} 5m bars & {min_last_15m_label} 15m bars)"
)

df_5m = df_5m.filter(pl.col("batch_id").is_in(label_batches))
df_15m = df_15m.filter(pl.col("batch_id").is_in(label_batches))

print(f"  Filtered 5m bars: {len(df_5m):,}")
print(f"  Filtered 15m bars: {len(df_15m):,}")

# Breakfree threshold (end-of-batch close distance) for 5m hybrid labels
# end_return = (close_end - close_now) / close_now
BREAKFREE_THRESHOLD_5M = 0.001  # 0.10%

# Compute end-of-batch close distance for breakfree target (5m labels)
batch_close_5m = df_5m.group_by("batch_id").agg(
    pl.col("close").sort_by("timestamp").last().alias("close_end")
)
df_5m = df_5m.join(batch_close_5m, on="batch_id", how="left").with_columns(
    ((pl.col("close_end") - pl.col("close")) / pl.col("close")).alias("end_return")
)

# =============================================================================
# STEP 2: COMPUTE 5m BAR POSITION AND 15m MAPPING
# =============================================================================
print("\n[STEP 2] Computing bar positions...")

# Add 5m bar position within batch
df_5m = df_5m.with_columns(
    (pl.col("timestamp").rank("ordinal").over("batch_id") - 1)
    .cast(pl.Int32)
    .alias("bar_pos_5m")
)

# Truncate 5m timestamp to 15m boundary
df_5m = df_5m.with_columns([(pl.col("timestamp").dt.truncate("15m")).alias("ts_15m")])

# Add 15m bar position within batch
df_15m = df_15m.with_columns(
    (pl.col("timestamp").rank("ordinal").over("batch_id") - 1)
    .cast(pl.Int32)
    .alias("bar_pos_15m")
)

# Compute BB for 5m (using 5m close as entry reference needs BB context)
df_5m = (
    df_5m.with_columns(
        [
            pl.col("close").rolling_mean(window_size=BB_PERIOD).alias("bb_middle"),
            pl.col("close").rolling_std(window_size=BB_PERIOD).alias("bb_std"),
        ]
    )
    .with_columns(
        [
            (pl.col("bb_middle") + BB_STD * pl.col("bb_std")).alias("bb_upper"),
            (pl.col("bb_middle") - BB_STD * pl.col("bb_std")).alias("bb_lower"),
        ]
    )
    .with_columns(
        [
            (
                (pl.col("close") - pl.col("bb_lower"))
                / (pl.col("bb_upper") - pl.col("bb_lower"))
                * 100
            ).alias("bb_position_pct"),
        ]
    )
)

# Add 2h segment
df_5m = df_5m.with_columns((pl.col("bar_pos_5m") // 24).alias("segment_2h"))

print("  5m bar positions computed")

# =============================================================================
# STEP 3: COMPUTE DISTANCE METRICS (5m ENTRY + 15m REMAINING BARS)
# =============================================================================
print("\n[STEP 3] Computing hybrid distance metrics...")


@njit
def compute_hybrid_distance_metrics(
    close_5m,  # 5m close prices (entry reference)
    batch_id_5m,  # 5m batch IDs
    bar_pos_15m_for_5m,  # Which 15m bar each 5m bar belongs to
    high_15m,  # 15m highs (flattened, indexed by batch)
    low_15m,  # 15m lows
    batch_id_15m,  # 15m batch IDs
    bar_pos_15m,  # 15m bar positions
    min_remaining,  # 1
    outlier_pct,  # 0.05
):
    """
    Compute distance metrics for each 5m bar using:
    - Entry = 5m close
    - Remaining bars = 15m bars after the 5m bar's 15m period (current batch only)
    """
    n = len(close_5m)
    dist_avg_high = np.full(n, np.nan, dtype=np.float64)
    dist_avg_low = np.full(n, np.nan, dtype=np.float64)
    dist_top5_high = np.full(n, np.nan, dtype=np.float64)
    dist_bot5_low = np.full(n, np.nan, dtype=np.float64)
    remaining_bars_out = np.full(n, 0, dtype=np.int32)

    # Build batch index for 15m data
    n_15m = len(high_15m)

    for i in range(n):
        entry = close_5m[i]
        current_batch = batch_id_5m[i]
        current_15m_pos = bar_pos_15m_for_5m[i]

        # Collect remaining 15m bars in current batch only
        highs = []
        lows = []
        for j in range(n_15m):
            if batch_id_15m[j] == current_batch and bar_pos_15m[j] > current_15m_pos:
                highs.append(high_15m[j])
                lows.append(low_15m[j])

        count = len(highs)
        remaining_bars_out[i] = count

        if count < min_remaining:
            continue

        # Convert to arrays for sorting
        highs_arr = np.array(highs, dtype=np.float64)
        lows_arr = np.array(lows, dtype=np.float64)

        sorted_highs = np.sort(highs_arr)
        sorted_lows = np.sort(lows_arr)
        top_n = max(1, int(count * outlier_pct))

        # Compute averages
        avg_high = np.mean(highs_arr)
        avg_low = np.mean(lows_arr)
        avg_top_high = np.mean(sorted_highs[-top_n:])
        avg_bot_low = np.mean(sorted_lows[:top_n])

        # Compute distances as percentages from 5m entry
        dist_avg_high[i] = 100.0 * (avg_high - entry) / entry
        dist_avg_low[i] = 100.0 * (entry - avg_low) / entry
        dist_top5_high[i] = 100.0 * (avg_top_high - entry) / entry
        dist_bot5_low[i] = 100.0 * (entry - avg_bot_low) / entry

    return (
        dist_avg_high,
        dist_avg_low,
        dist_top5_high,
        dist_bot5_low,
        remaining_bars_out,
    )


# Join 15m bar position to 5m
df_15m_pos = df_15m.select(
    [
        pl.col("timestamp").alias("ts_15m"),
        pl.col("batch_id").alias("batch_id_check"),
        "bar_pos_15m",
    ]
)

df_5m = df_5m.join(df_15m_pos, on="ts_15m", how="left")

# Prepare arrays for numba
close_5m_np = df_5m["close"].to_numpy().astype(np.float64)
batch_id_5m_np = df_5m["batch_id"].to_numpy().astype(np.int64)
bar_pos_15m_for_5m_np = df_5m["bar_pos_15m"].fill_null(0).to_numpy().astype(np.int32)

high_15m_np = df_15m["high"].to_numpy().astype(np.float64)
low_15m_np = df_15m["low"].to_numpy().astype(np.float64)
batch_id_15m_np = df_15m["batch_id"].to_numpy().astype(np.int64)
bar_pos_15m_np = df_15m["bar_pos_15m"].to_numpy().astype(np.int32)

print("  Running numba function...")
d_avg_high, d_avg_low, d_top5_high, d_bot5_low, remaining = (
    compute_hybrid_distance_metrics(
        close_5m_np,
        batch_id_5m_np,
        bar_pos_15m_for_5m_np,
        high_15m_np,
        low_15m_np,
        batch_id_15m_np,
        bar_pos_15m_np,
        MIN_REMAINING_BARS_15M,
        OUTLIER_PERCENTILE,
    )
)

# Add to dataframe
df_5m = df_5m.with_columns(
    [
        pl.Series("dist_avg_high", d_avg_high),
        pl.Series("dist_avg_low", d_avg_low),
        pl.Series("dist_top5_high", d_top5_high),
        pl.Series("dist_bot5_low", d_bot5_low),
        pl.Series("remaining_bars", remaining),
    ]
)

# Count valid
valid_count = len(df_5m.filter(pl.col("dist_avg_high").is_not_nan()))
print(
    f"  Valid 5m bars (with metrics): {valid_count:,} ({100 * valid_count / len(df_5m):.1f}%)"
)
entry_bar_limit_5m = int(BARS_PER_8H_5M * (ENTRY_WINDOW_HOURS_5M / 8.0))
expected_valid_5m = min(BARS_PER_8H_5M - MIN_REMAINING_BARS_5M, entry_bar_limit_5m)
print(
    f"  Expected valid label rows per full 5m batch: {expected_valid_5m} "
    f"(first {ENTRY_WINDOW_HOURS_5M}h only)"
)

# =============================================================================
# STEP 4: CHECK SCENARIO DISTRIBUTION
# =============================================================================
print("\n[STEP 4] Checking scenario distribution...")

df_valid = df_5m.filter(
    pl.col("dist_avg_high").is_not_nan() & (pl.col("bar_pos_5m") < entry_bar_limit_5m)
)

breakout_up = (df_valid["dist_avg_low"] < 0).sum()
breakout_down = (df_valid["dist_avg_high"] < 0).sum()
oscillation = ((df_valid["dist_avg_low"] > 0) & (df_valid["dist_avg_high"] > 0)).sum()
total = len(df_valid)

print(f"  Breakout UP:   {breakout_up:>10,} ({100 * breakout_up / total:.1f}%)")
print(f"  Breakout DOWN: {breakout_down:>10,} ({100 * breakout_down / total:.1f}%)")
print(f"  Oscillation:   {oscillation:>10,} ({100 * oscillation / total:.1f}%)")
print("  (Pure 5m had: 84% breakout, 16% oscillation)")
print("  (Pure 15m has: 74% breakout, 26% oscillation)")

# =============================================================================
# STEP 5: COMPUTE 8-CLASS LABELS
# =============================================================================
print("\n[STEP 5] Computing 8-class labels...")


def compute_8class_labels(
    df: pl.DataFrame, breakout_thresh: float, risk_thresh: float
) -> pl.DataFrame:
    """Compute 8-class labels using dual-threshold approach."""
    eps = 1e-10

    # Scenario detection
    df = df.with_columns(
        [
            (pl.col("dist_avg_low") < 0).alias("is_breakout_up"),
            (pl.col("dist_avg_high") < 0).alias("is_breakout_down"),
            ((pl.col("dist_avg_low") > 0) & (pl.col("dist_avg_high") > 0)).alias(
                "is_oscillation"
            ),
        ]
    )

    # Direction
    df = df.with_columns(
        [
            pl.when(pl.col("is_breakout_up"))
            .then(pl.lit(True))
            .when(pl.col("is_breakout_down"))
            .then(pl.lit(False))
            .otherwise(pl.col("dist_avg_high") > pl.col("dist_avg_low"))
            .alias("is_up")
        ]
    )

    # Risk flags (dual threshold)
    df = df.with_columns(
        [
            pl.when(pl.col("is_breakout_up"))
            .then(pl.col("dist_top5_high") > breakout_thresh)
            .when(pl.col("is_breakout_down"))
            .then(pl.lit(False))
            .otherwise(
                (pl.col("dist_top5_high") / (pl.col("dist_avg_high") + eps))
                > risk_thresh
            )
            .alias("high_risk_up"),
            pl.when(pl.col("is_breakout_down"))
            .then(pl.col("dist_bot5_low") > breakout_thresh)
            .when(pl.col("is_breakout_up"))
            .then(pl.lit(False))
            .otherwise(
                (pl.col("dist_bot5_low") / (pl.col("dist_avg_low") + eps)) > risk_thresh
            )
            .alias("high_risk_down"),
        ]
    )

    # 8-class assignment
    df = df.with_columns(
        [
            pl.when(pl.col("dist_avg_high").is_nan())
            .then(pl.lit(-1))
            .when(pl.col("is_up") & pl.col("high_risk_up") & pl.col("high_risk_down"))
            .then(pl.lit(5))  # UP_VOLATILE
            .when(pl.col("is_up") & pl.col("high_risk_up") & ~pl.col("high_risk_down"))
            .then(pl.lit(4))  # UP_CONT
            .when(pl.col("is_up") & ~pl.col("high_risk_up") & pl.col("high_risk_down"))
            .then(pl.lit(6))  # UP_REVERSAL_RISK
            .when(pl.col("is_up") & ~pl.col("high_risk_up") & ~pl.col("high_risk_down"))
            .then(pl.lit(3))  # UP_BALANCED
            .when(~pl.col("is_up") & pl.col("high_risk_up") & pl.col("high_risk_down"))
            .then(pl.lit(2))  # DOWN_VOLATILE
            .when(~pl.col("is_up") & ~pl.col("high_risk_up") & pl.col("high_risk_down"))
            .then(pl.lit(1))  # DOWN_CONT
            .when(~pl.col("is_up") & pl.col("high_risk_up") & ~pl.col("high_risk_down"))
            .then(pl.lit(7))  # DOWN_REVERSAL_RISK
            .when(
                ~pl.col("is_up") & ~pl.col("high_risk_up") & ~pl.col("high_risk_down")
            )
            .then(pl.lit(0))  # DOWN_BALANCED
            .otherwise(pl.lit(-1))
            .alias("target_8class")
        ]
    )

    # Add class name
    df = df.with_columns(
        [
            pl.col("target_8class")
            .replace_strict(
                {i: name for i, name in CLASS_NAMES.items()}, default="INVALID"
            )
            .alias("target_name")
        ]
    )

    # Cleanup
    df = df.drop(
        [
            "is_breakout_up",
            "is_breakout_down",
            "is_oscillation",
            "is_up",
            "high_risk_up",
            "high_risk_down",
            "batch_id_check",
        ]
    )

    return df


df_labeled = compute_8class_labels(df_5m, BREAKOUT_THRESHOLD, RISK_RATIO)

# Breakfree binary target (1=up, 0=down, -1=neutral)
df_labeled = df_labeled.with_columns(
    [
        pl.when(pl.col("end_return") >= BREAKFREE_THRESHOLD_5M)
        .then(pl.lit(1))
        .when(pl.col("end_return") <= -BREAKFREE_THRESHOLD_5M)
        .then(pl.lit(0))
        .otherwise(pl.lit(-1))
        .alias("target_breakfree")
    ]
)

# Keep labels only for first 4h entry window; mark later bars as invalid
df_labeled = df_labeled.with_columns(
    [
        pl.when(pl.col("bar_pos_5m") < entry_bar_limit_5m)
        .then(pl.col("target_8class"))
        .otherwise(pl.lit(-1))
        .alias("target_8class"),
        pl.when(pl.col("bar_pos_5m") < entry_bar_limit_5m)
        .then(pl.col("target_breakfree"))
        .otherwise(pl.lit(-1))
        .alias("target_breakfree"),
    ]
)
df_labeled = df_labeled.with_columns(
    [
        pl.col("target_8class")
        .replace_strict({i: name for i, name in CLASS_NAMES.items()}, default="INVALID")
        .alias("target_name")
    ]
)

# =============================================================================
# STEP 6: VALIDATE CLASS DISTRIBUTION
# =============================================================================
print("\n[STEP 6] Validating class distribution...")

class_counts = (
    df_labeled.filter(pl.col("target_8class") >= 0)
    .group_by("target_8class")
    .agg(pl.len().alias("count"))
    .sort("target_8class")
)

total = class_counts["count"].sum()

print(
    f"\n{'Class':<3} {'Name':<20} {'Count':>10} {'Actual':>8} {'Target':>8} {'Diff':>8} {'Status'}"
)
print("-" * 75)

mse = 0.0
for cls in range(8):
    row = class_counts.filter(pl.col("target_8class") == cls)
    count = row["count"][0] if len(row) > 0 else 0
    pct = 100 * count / total if total > 0 else 0
    target = DOC_TARGETS[cls]
    diff = pct - target
    mse += diff**2
    status = "✓" if abs(diff) < 2 else "≈" if abs(diff) < 5 else "✗"
    print(
        f"{cls:<3} {CLASS_NAMES[cls]:<20} {count:>10,} {pct:>7.1f}% {target:>7.1f}% {diff:>+7.1f}% {status}"
    )

mse = mse / len(DOC_TARGETS)
print(f"\nMSE to doc targets: {mse:.2f}")
print("(Pure 15m: MSE=1.39, Pure 5m: MSE=47.21)")

# =============================================================================
# STEP 7: SAVE LABELED DATA (PER-BATCH for downstream compatibility)
# =============================================================================
print("\n[STEP 7] Saving labeled data (per-batch)...")

# Select output columns (matching docs specification)
output_cols = [
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "batch_id",
    "bar_pos_5m",
    "bar_pos_15m",
    "remaining_bars",
    "bb_upper",
    "bb_lower",
    "bb_middle",
    "bb_position_pct",
    "segment_2h",
    "dist_avg_high",
    "dist_avg_low",
    "dist_top5_high",
    "dist_bot5_low",
    "close_end",
    "end_return",
    "target_8class",
    "target_name",
    "target_breakfree",
]

available_cols = [c for c in output_cols if c in df_labeled.columns]
df_output = df_labeled.select(available_cols)

# Save per-batch (8h aligned)
tf_labels_dir = HTF_LABELS_DIR / "5m"
tf_labels_dir.mkdir(exist_ok=True)

batch_ids = df_output["batch_id"].unique().sort().to_list()
for bid in batch_ids:
    batch_df = df_output.filter(pl.col("batch_id") == bid)
    batch_path = tf_labels_dir / f"batch_{bid:04d}.parquet"
    batch_df.write_parquet(batch_path)

print(f"  ✓ Saved {len(batch_ids):,} batch files to {tf_labels_dir}")
print(f"  ✓ Total rows: {len(df_output):,}")

# =============================================================================
# STEP 8: SUMMARY
# =============================================================================
print("\n" + "=" * 70)
print("HYBRID 5m LABELING COMPLETE")
print("=" * 70)
print("\nApproach: 5m entry close + 15m remaining bars for distance metrics")
print(f"Thresholds: BREAKOUT={BREAKOUT_THRESHOLD}%, RISK_RATIO={RISK_RATIO}x")
print(f"MSE: {mse:.2f} (vs Pure 5m: 47.21, Pure 15m: 1.39)")
print(f"\nOutput: {tf_labels_dir}/batch_*.parquet")
print(f"Batches: {len(batch_ids):,}")
print(f"Rows: {len(df_output):,}")
print(f"Valid labels: {len(df_output.filter(pl.col('target_8class') >= 0)):,}")

# Show column info
print(f"\nColumns saved ({len(available_cols)}):")
for col in available_cols:
    print(f"  - {col}")

# Cleanup
del df_5m, df_15m, df_labeled, df_output, df_valid
gc.collect()

print("\n" + "=" * 70)
print("NEXT: Combine with 15m labels for multi-TF training")
print("=" * 70)

# %%
# =============================================================================
# CELL 10: HTF FEATURE OPTIMIZATION (Rolling Rank-Winsorize)
# =============================================================================
# CORRECT winsorize-rank implementation:
#   1. Rolling rank: u_t = percentile of x_t vs past L values (t-L..t-1)
#   2. Clip ranks: u_t' = clip(u_t, p_min, p_max)
#   3. Post-transform: uniform [-1,1] or signed
#
# KEY DESIGN:
#   - Rolling window (bounded memory O(L) per feature)
#   - State carries across batches (no reset at boundaries)
#   - Walk-forward validation on EARLY data only (no look-ahead)
#   - Grid search: window L, clip bounds, post-transform
#
# CAUSAL GUARANTEE:
#   At row t, rank uses ONLY t-L..t-1. No future leakage.
#
# Output: data/htf_optimized/{tf}/{target}/batch_XXXX.parquet
# =============================================================================

import importlib
import sys
from pathlib import Path

# Ensure project root is in path
PROJECT_ROOT = Path("..").resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Force reload to pick up changes
import scripts.feature_engineering.optimize_htf_features as opt_module

importlib.reload(opt_module)
from scripts.feature_engineering.optimize_htf_features import (
    HTFOptimizationConfig,
    optimize_htf_features,
)

# Configuration - Walk-forward on EARLY data
# For 8-class: optimize directly against target_8class
config = HTFOptimizationConfig(
    project_root=PROJECT_ROOT,
    timeframes=["5m", "15m"],  # 1h excluded
    targets=["target_8class"],  # 8-class categorical target
    n_early_batches=200,  # Use FIRST 200 batches chronologically for tuning
    n_val_folds=3,  # 3-fold walk-forward validation
    stability_lambda=0.5,  # score = mean(IC) - 0.5 * std(IC)
    recompute=True,
    save_results=True,
)

# Run optimization
results = optimize_htf_features(config, verbose=True)

# Show results
if len(results) > 0:
    print("\n" + "=" * 70)
    print("OPTIMIZATION RESULTS")
    print("=" * 70)
    print(results.to_string(index=False))

# %%
# =============================================================================
# CELL 11: L1 HELPER FEATURES (CORRECTED - RAW DATA INPUT)
# =============================================================================
# ISSUE FIXED: Previous version fed rank-winsorized data (0-1) to helpers.
# Helpers expect RAW returns and prices for proper estimation.
#
# SOLUTION:
# 1. Load from htf_features/ (has raw OHLCV: close ~40000-70000)
# 2. Compute raw returns from raw close
# 3. Build feature matrix with raw returns at column 0 (what helpers expect)
# 4. Run walk-forward helper generation
# 5. Join results with htf_optimized/ (rank-winsorized features)
#
# OUTPUT: data/htf_with_helpers/{tf}/{target}/combined.parquet
# =============================================================================

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl

# Ensure project root is in path
PROJECT_ROOT = Path("..").resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import helper infrastructure (SAME as main_wf)
from scripts.target_models.helpers import create_helper_ensemble

# =============================================================================
# HELPER: PREPARE RAW DATA FOR HELPERS
# =============================================================================


def prepare_raw_features_for_helpers(df: pl.DataFrame) -> tuple[np.ndarray, list[str]]:
    """
    Prepare feature matrix with RAW returns/volatility that helpers expect.

    Helpers use column indices:
    - return_col_idx=0: raw log returns
    - vol_col_idx=1: raw volatility (rolling std of returns)
    - price_col_idx: close price (for OU, Kalman)

    Returns:
        (feature_matrix, column_names)
    """
    # Get raw close prices
    close = df["close"].to_numpy().astype(np.float64)

    # Compute raw log returns
    returns = np.zeros_like(close)
    returns[1:] = np.diff(np.log(np.maximum(close, 1e-10)))

    # Compute rolling volatility (20-period std of returns)
    volatility = pd.Series(returns).rolling(20, min_periods=1).std().fillna(0.01).values

    # Build feature matrix: [returns, volatility, close, other raw columns...]
    # This puts returns at index 0, volatility at index 1
    feature_cols = ["raw_returns", "raw_volatility", "close"]
    features = np.column_stack([returns, volatility, close])

    # Add other raw numeric columns that might be useful
    for col in ["open", "high", "low", "volume"]:
        if col in df.columns:
            vals = df[col].to_numpy().astype(np.float64)
            features = np.column_stack([features, vals])
            feature_cols.append(col)

    return features, feature_cols


# =============================================================================
# WALK-FORWARD HELPER GENERATION (NO LOOK-AHEAD BIAS)
# =============================================================================


def compute_helpers_walk_forward_raw(
    raw_df: pl.DataFrame,
    target: str,
    horizon: int = 1,
    warmup_rows: int = 5000,
    refit_every: int = 1000,
    helpers: list[str] | None = None,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Generate L1 helper features using walk-forward approach with RAW data.

    CRITICAL: At each row t, we only use data from rows [0, t-1] to fit.
    Uses RAW returns/prices, not rank-winsorized data.
    """
    if helpers is None:
        helpers = ["ou", "garch", "cusum", "kalman", "egarch"]

    # Prepare raw feature matrix
    X, feature_cols = prepare_raw_features_for_helpers(raw_df)
    n_rows = len(X)

    if verbose:
        print(f"  Raw data prepared: {n_rows:,} rows, {len(feature_cols)} columns")
        print(f"  Returns range: {np.nanmin(X[:, 0]):.6f} to {np.nanmax(X[:, 0]):.6f}")
        print(f"  Close range: {np.nanmin(X[:, 2]):.2f} to {np.nanmax(X[:, 2]):.2f}")
        print(f"  Walk-forward: warmup={warmup_rows}, refit_every={refit_every}")

    # Convert to DataFrame for helper API
    X_df = pd.DataFrame(X, columns=feature_cols)

    helper_output_list = []
    t0 = time.time()
    chunk_size = refit_every

    for chunk_start in range(warmup_rows, n_rows, chunk_size):
        chunk_end = min(chunk_start + chunk_size, n_rows)

        # 1. FIT on all data up to chunk_start (past only)
        X_train = X_df.iloc[:chunk_start]

        # Create and fit fresh ensemble
        ensemble = create_helper_ensemble(
            target=target,
            horizon=horizon,
            random_state=42 + chunk_start,
            helpers=helpers,
            enable_boosting=False,
        )
        ensemble.fit(X_train)

        # 2. TRANSFORM the current chunk
        X_chunk = X_df.iloc[chunk_start:chunk_end]
        chunk_features = ensemble.transform(X_chunk)
        helper_output_list.append(chunk_features.features)

        if verbose and (chunk_start - warmup_rows) % (chunk_size * 20) == 0:
            elapsed = time.time() - t0
            progress = (chunk_end - warmup_rows) / (n_rows - warmup_rows)
            eta = elapsed / max(progress, 0.01) * (1 - progress)
            print(
                f"    {chunk_end:,}/{n_rows:,} ({progress * 100:.1f}%), "
                f"{elapsed / 60:.1f}m elapsed, ~{eta / 60:.1f}m remaining"
            )

    # Concatenate and add NaN warmup
    helper_df = pd.concat(helper_output_list, axis=0, ignore_index=True)
    warmup_features = pd.DataFrame(
        np.nan, index=range(warmup_rows), columns=helper_df.columns
    )
    helper_df_full = pd.concat([warmup_features, helper_df], axis=0, ignore_index=True)

    if verbose:
        print(
            f"  Generated {len(helper_df.columns)} helper features in {time.time() - t0:.1f}s"
        )

    return helper_df_full


# =============================================================================
# PROCESS ALL HTF TIMEFRAMES AND TARGETS
# =============================================================================

print("=" * 70)
print("HTF L1 HELPER FEATURES (CORRECTED - RAW DATA INPUT)")
print("=" * 70)

TIMEFRAMES = ["5m", "15m"]  # 1h excluded
TARGETS = ["target_8class"]  # 8-class target
HELPERS = ["ou", "garch", "cusum", "kalman", "egarch"]

results = []

for tf in TIMEFRAMES:
    for target in TARGETS:
        print(f"\n{'─' * 50}")
        print(f"{tf} / {target}")
        print("─" * 50)

        # Load RAW data from htf_features (before rank-winsorize)
        raw_dir = PROJECT_ROOT / "data" / "htf_features" / tf
        if not raw_dir.exists():
            print("  ⚠️ htf_features directory not found")
            continue

        raw_files = sorted(raw_dir.glob("batch_*.parquet"))
        if not raw_files:
            print("  ⚠️ No batch files in htf_features")
            continue

        # Load and combine raw data
        print(f"  Loading {len(raw_files)} raw batches...", end=" ", flush=True)
        t0 = time.time()
        dfs = [pl.read_parquet(rf) for rf in raw_files]
        raw_combined = pl.concat(dfs).sort("timestamp")
        print(f"{len(raw_combined):,} rows in {time.time() - t0:.1f}s")

        # Adjust warmup/refit based on timeframe
        if tf == "5m":
            warmup, refit = 10000, 5000
        elif tf == "15m":
            warmup, refit = 5000, 2500
        else:  # 1h
            warmup, refit = 2000, 1000

        # Generate helper features with walk-forward on RAW data
        t0 = time.time()
        helper_df = compute_helpers_walk_forward_raw(
            raw_df=raw_combined,
            target=target.replace("target_", ""),
            horizon=1,
            warmup_rows=warmup,
            refit_every=refit,
            helpers=HELPERS,
            verbose=True,
        )
        helper_time = time.time() - t0

        # Now load rank-winsorized data from htf_optimized and join
        opt_dir = PROJECT_ROOT / "data" / "htf_optimized" / tf / target
        if not opt_dir.exists():
            print(f"  ⚠️ htf_optimized/{tf}/{target} not found")
            continue

        opt_files = sorted(opt_dir.glob("batch_*.parquet"))
        print(f"  Loading {len(opt_files)} optimized batches...", end=" ", flush=True)
        t0 = time.time()
        opt_dfs = [
            pl.read_parquet(of).with_columns(
                pl.lit(int(of.stem.split("_")[1])).alias("batch_id")
            )
            for of in opt_files
        ]
        opt_combined = pl.concat(opt_dfs).sort("timestamp")
        print(f"{len(opt_combined):,} rows in {time.time() - t0:.1f}s")

        # Add timestamp to helper_df for joining (raw_combined has timestamps)
        helper_pl = pl.from_pandas(helper_df)
        helper_pl = helper_pl.with_columns(raw_combined["timestamp"])

        # Join by timestamp (handles filtered rows correctly)
        enriched = opt_combined.join(
            helper_pl.select(
                ["timestamp"] + [c for c in helper_pl.columns if c.startswith("H_")]
            ),
            on="timestamp",
            how="left",
        )

        print(f"  Joined: {len(enriched):,} rows (matched by timestamp)")

        # Save
        output_dir = PROJECT_ROOT / "data" / "htf_with_helpers" / tf / target
        output_dir.mkdir(parents=True, exist_ok=True)
        combined_path = output_dir / "combined.parquet"
        enriched.write_parquet(combined_path)

        n_helper = len([c for c in enriched.columns if c.startswith("H_")])
        results.append(
            {
                "tf": tf,
                "target": target,
                "rows": len(enriched),
                "helpers": n_helper,
                "warmup": warmup,
                "time": helper_time,
            }
        )
        print(f"  ✓ Saved {combined_path.name} ({n_helper} helper features)")

# Summary
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print(pl.DataFrame(results))

# %%
# =============================================================================
# CELL 12: SPLIT BACK TO 8H BATCHES
# =============================================================================
# Split combined.parquet back into batch files matching original structure:
#   - Each batch = 1 8h candle period
#   - 5m: 96 bars per batch (96 * 5min = 8h)
#   - 15m: 32 bars per batch (32 * 15min = 8h)
#   - 1h: 8 bars per batch (8 * 1h = 8h)
#
# Uses batch_id from optimized data to ensure alignment.
#
# OUTPUT: data/htf_with_helpers/{tf}/{target}/batch_XXXX.parquet
# =============================================================================

import time
from pathlib import Path

import polars as pl

PROJECT_ROOT = Path("..").resolve()

print("=" * 70)
print("SPLIT COMBINED DATA BACK TO 8H BATCHES")
print("=" * 70)

TIMEFRAMES = ["5m", "15m"]  # 1h excluded
TARGETS = ["target_8class"]  # 8-class target

# Expected bars per 8h batch (note: actual may vary due to filtering)
BARS_PER_BATCH = {
    "5m": 96,  # 8h * 60min / 5min = 96
    "15m": 32,  # 8h * 60min / 15min = 32 (but filtered to ~22 valid)
}

results = []

for tf in TIMEFRAMES:
    for target in TARGETS:
        print(f"\n{'─' * 50}")
        print(f"{tf} / {target}")
        print("─" * 50)

        # Load combined file
        combined_path = (
            PROJECT_ROOT
            / "data"
            / "htf_with_helpers"
            / tf
            / target
            / "combined.parquet"
        )
        if not combined_path.exists():
            print(f"  ⚠️ Combined file not found: {combined_path}")
            continue

        t0 = time.time()
        df = pl.read_parquet(combined_path)
        print(f"  Loaded: {len(df):,} rows, {len(df.columns)} columns")

        # Verify batch_id column exists
        if "batch_id" not in df.columns:
            print("  ⚠️ No batch_id column - cannot split by original batches")
            continue

        # Get unique batch IDs and sort
        batch_ids = sorted(df["batch_id"].unique().drop_nulls().to_list())
        print(f"  Found {len(batch_ids)} unique batch_ids")

        # Create output directory (same as input, files will overwrite combined)
        output_dir = combined_path.parent

        # Verify expected batch structure
        expected_bars = BARS_PER_BATCH[tf]

        # Split and save each batch
        saved_count = 0
        total_rows = 0

        for batch_id in batch_ids:
            batch_df = df.filter(pl.col("batch_id") == batch_id)

            # Verify row count matches expected
            if len(batch_df) != expected_bars:
                # Some batches at boundaries might have fewer rows - that's OK
                if len(batch_df) > expected_bars:
                    print(
                        f"  ⚠️ Batch {batch_id}: {len(batch_df)} rows (expected {expected_bars})"
                    )

            # Save batch file
            batch_path = output_dir / f"batch_{batch_id:04d}.parquet"
            batch_df.write_parquet(batch_path, compression="zstd")

            saved_count += 1
            total_rows += len(batch_df)

        elapsed = time.time() - t0

        results.append(
            {
                "tf": tf,
                "target": target,
                "batches": saved_count,
                "rows": total_rows,
                "time_s": round(elapsed, 1),
            }
        )

        print(
            f"  ✓ Saved {saved_count} batch files ({total_rows:,} rows) in {elapsed:.1f}s"
        )

# Summary
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print(pl.DataFrame(results))

# Verify output
print("\n" + "=" * 70)
print("VERIFICATION")
print("=" * 70)

for tf in TIMEFRAMES:
    for target in TARGETS:
        batch_dir = PROJECT_ROOT / "data" / "htf_with_helpers" / tf / target
        batch_files = sorted(batch_dir.glob("batch_*.parquet"))

        if batch_files:
            # Check first and last batch
            first = pl.read_parquet(batch_files[0])
            last = pl.read_parquet(batch_files[-1])

            first_ts = first["timestamp"].min()
            last_ts = last["timestamp"].max()

            h_cols = len([c for c in first.columns if c.startswith("H_")])

            print(f"\n{tf}/{target}:")
            print(f"  Batches: {len(batch_files)}")
            print(f"  Date range: {first_ts} to {last_ts}")
            print(f"  Helper features: {h_cols}")
            print(f"  Rows per batch: {len(first)} (first), {len(last)} (last)")

# %% [markdown]
# # Cell 14: Walk-Forward Backtest Design
#
# ## Architecture: 1-Step-Forward Backtest
#
# Each **step** = 1 batch (8h period). At each step:
# 1. **Train** on all batches `[0, current_batch)`
# 2. **Predict** batch `current_batch` row-by-row
# 3. **Track** predictions vs actuals during that 8h period
#
# ```
# ┌─────────────────────────────────────────────────────────────────────────────┐
# │                    HTF WALK-FORWARD BACKTEST                                │
# ├─────────────────────────────────────────────────────────────────────────────┤
# │                                                                             │
# │  BATCH TIMELINE:                                                            │
# │  ┌─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┐             │
# │  │  0  │  1  │  2  │ ... │ N-2 │ N-1 │  N  │ N+1 │ ... │ END │             │
# │  └─────┴─────┴─────┴─────┴─────┴─────┴─────┴─────┴─────┴─────┘             │
# │         ◄───── TRAIN ─────►│◄PRED►│                                         │
# │                            │      │                                         │
# │  At step N:                │      │                                         │
# │  • Train on batches 0..N-1 │      │                                         │
# │  • Predict batch N row-by-row     │                                         │
# │  • Record: y_pred vs y_actual     │                                         │
# │                                                                             │
# │  WITHIN BATCH N (e.g., 5m = 96 rows):                                       │
# │  ┌────┬────┬────┬────┬────┬────┐                                           │
# │  │ r0 │ r1 │ r2 │...│r94 │r95 │  ← Each row gets a prediction              │
# │  └────┴────┴────┴────┴────┴────┘                                           │
# │                                                                             │
# └─────────────────────────────────────────────────────────────────────────────┘
# ```
#
#
# # HTF Walk‑Forward Backtest — Structure & Modules (Multi‑Target LightGBM)
#
# This notebook runs a **walk‑forward backtest** on two timeframes (5m, 15m) and can run multiple targets per timeframe in the same step (for example: `target_8class` + `target_breakfree`). Each step trains on all batches available **before** the prediction batch and then predicts one 8h batch, matching a live‑style workflow.
#
# ## Core Modules (where they live and what they do)
#
# - `scripts/htf_backtest/lightgbm/runner.py`
#   Orchestrates the full walk‑forward loop: selects batches, runs optimization, trains, predicts, saves artifacts per step.
#
# - `scripts/htf_backtest/lightgbm/utils.py`
#   Shared utilities: data loading, feature selection helpers, class weights, save routines, and Optuna trial export.
#
# - `scripts/htf_backtest/lightgbm/tf_5m/optimizer.py`
#   5m‑specific search spaces + optimization logic + training. Uses Optuna to search lookback, features, and LGBM params.
#
# - `scripts/htf_backtest/lightgbm/tf_15m/optimizer.py`
#   15m‑specific search spaces + optimization logic + training. Same structure as 5m, tuned for 15m.
#
# - `scripts/htf_backtest/lightgbm/base_optimizer.py`
#   Compatibility layer that re‑exports the runner and optimizers.
#
# ## Walk‑Forward Flow (one step)
#
# 1. **Select prediction batch** (same batch ID for 5m and 15m so they align).
# 2. **Train window** = all batches up to `pred_batch - 1`.
# 3. **Optuna search** chooses:
#    - lookback window
#    - feature subset
#    - LightGBM hyperparameters
#    - class weighting
# 4. **Train final model** with best params.
# 5. **Predict** the selected batch and save metrics + per‑row predictions.
#
# ## Output Structure (per run)
#
# Results are written to:
# `data/htf_backtest_results/<run_id>/<model_name>/`
#
# Inside each run:
# - `run_config.json` — run metadata (steps, timeframes, lookback min, etc.)
# - `run_summary.json` — aggregated metrics across all steps
# - `<timeframe>/<target>/batch_XXXX/` — per‑step artifacts (batch ID = prediction batch)
#
# Per‑step artifacts:
# - `optimization.json` — best trial summary (params, selected features, best accuracy)
# - `study.db` — full Optuna study database (all trials)
# - `trials.parquet` / `trials.jsonl` — **all trials exported** (params + metrics + feature hash)
# - `model.txt` — trained LightGBM model
# - `class_metrics.parquet` — per‑class validation metrics (best trial)
# - `prediction_metrics.json` — prediction‑batch metrics
# - `predictions.parquet` — per‑row predictions + class probabilities
#
# ## How to Configure From This Notebook
#
# Cell 14 supports:
# - model + timeframe + target selection
# - per-target Optuna overrides:
#   `OPTUNA_OVERRIDES_BY_MODEL[model][timeframe][target]`
# - target registry metadata (`task_type`, `n_classes`, `class_names`)
# - feature source mapping per target (`FEATURE_SOURCE_BY_MODEL`)
#
# These overrides are applied at runtime without editing the optimizer source files.
#
# ## Notes on Alignment Across Timeframes
#
# - 5m and 15m **predict the same batch ID** per step.
# - Batch timestamps align by 8h windows, so performance comparisons are directly comparable.
# - Training always excludes the prediction batch, preventing look‑ahead.
#
#

# %%
# ============================================================================
# CELL 14: HTF WALK-FORWARD BACKTEST (MODEL+TARGET CONFIGURABLE)
# ============================================================================

import sys
from pathlib import Path

if "PROJECT_ROOT" not in dir():
    PROJECT_ROOT = Path("/media/przem/linux_data/RiskYieldMM (Copy)")

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import importlib

for mod_name in list(sys.modules.keys()):
    if "htf_backtest" in mod_name:
        del sys.modules[mod_name]

from scripts.htf_backtest.lightgbm.base_optimizer import run_walk_forward_backtest

# ============================================================================
# RUN CONFIGURATION
# ============================================================================

MODEL_NAME = "lightgbm"

# Resume controls (passed to run_walk_forward_backtest at the bottom of this cell):
# - RESUME=False -> fresh run (new run_id if run_id=None)
# - RESUME=True + RESUME_MODE="continue" -> reopen same run and append Optuna trials
# - RESUME=True + RESUME_MODE="skip_completed" -> skip steps with model+prediction already saved
# - ALLOW_OVERRIDE_MISMATCH=True -> allow config overrides to differ from stored run_config on resume
RESUME = False  # keep False for now: start fresh run flow
RESUME_RUN_ID = "run_2026-02-05_18-06-04"  # used only when RESUME=True
RESUME_MODE = "continue"  # "continue" or "skip_completed" (used only when RESUME=True)
ALLOW_OVERRIDE_MISMATCH = False  # strict resume safety by default

# Which timeframes to run (per model)
TIMEFRAMES_BY_MODEL = {
    "lightgbm": ["5m", "15m"],
}

# Targets per model + timeframe (multi-target)
TARGETS_BY_MODEL = {
    "lightgbm": {
        "5m": ["target_8class", "target_breakfree"],
        "15m": ["target_8class", "target_breakfree"],
    }
}

# 8-class names
CLASS_NAMES_8 = [
    "DOWN_BALANCED",
    "DOWN_CONT",
    "DOWN_VOLATILE",
    "UP_BALANCED",
    "UP_CONT",
    "UP_VOLATILE",
    "UP_REVERSAL_RISK",
    "DOWN_REVERSAL_RISK",
]

# Binary target class names
CLASS_NAMES_BREAKFREE = [
    "BELOW_BREAKFREE",
    "ABOVE_BREAKFREE",
]

# Target registry (classification only)
TARGET_REGISTRY = {
    "target_8class": {
        "task_type": "multiclass",
        "n_classes": 8,
        "class_names": CLASS_NAMES_8,
    },
    "target_breakfree": {
        "task_type": "binary",
        "n_classes": 2,
        "class_names": CLASS_NAMES_BREAKFREE,
    },
}

# Number of classes per model + timeframe + target
N_CLASSES_BY_MODEL = {
    "lightgbm": {
        "5m": {
            "target_8class": 8,
            "target_breakfree": 2,
        },
        "15m": {
            "target_8class": 8,
            "target_breakfree": 2,
        },
    }
}

# Class names per model + timeframe + target
CLASS_NAMES_BY_MODEL = {
    "lightgbm": {
        "5m": {
            "target_8class": CLASS_NAMES_8,
            "target_breakfree": CLASS_NAMES_BREAKFREE,
        },
        "15m": {
            "target_8class": CLASS_NAMES_8,
            "target_breakfree": CLASS_NAMES_BREAKFREE,
        },
    }
}

# Feature source mapping per target.
# `target_breakfree` intentionally reuses `target_8class` helper-feature files.
FEATURE_SOURCE_BY_MODEL = {
    "lightgbm": {
        "5m": {
            "target_8class": "target_8class",
            "target_breakfree": "target_8class",
        },
        "15m": {
            "target_8class": "target_8class",
            "target_breakfree": "target_8class",
        },
    }
}

# Per-model Optuna overrides (target-specific; no mixing between targets)
OPTUNA_OVERRIDES_BY_MODEL = {
    "lightgbm": {
        "5m": {
            "target_8class": {
                "optuna_trials": 2000,
                "optuna_timeout": 60,
                "optuna_metric": "macro_f1",  # options: accuracy, log_loss, balanced_accuracy, macro_f1, macro_f1_up, macro_f1_down, directional_accuracy
                # Keep optimization leakage-safe: no prediction-batch trial metrics.
                "track_pred_metrics": False,
                # Extra tail exclusion is disabled.
                # Labels already encode the intended entry window (first 4h).
                # "exclude_tail_pct": 0.33,
                # Optional stratified shuffle split within lookback window
                # "shuffle_split": True,
                # "shuffle_seed": 42,
                # "shuffle_val_ratio": 0.2,
                # Optional shuffle of batch order (keeps row order inside each batch)
                # "shuffle_batches": True,
                # "shuffle_batches_seed": 42,
                # Optional class balancing via resampling
                "balance_strategy": "upsample",  # upsample, downsample, none
                "balance_apply_to": "train",  # train or train_val
                "window_space": {
                    "lookback_min": 100,
                    "lookback_max": 450,
                    "window_selection_mode": "deterministic_solver",
                    "train_share_min": 0.70,
                    "train_share_max": 0.80,
                    "embargo_mode": "auto_tf",
                    # Optional:
                    # "embargo_train_val_batches": 1,
                    # "embargo_val_pred_batches": 1,
                    "solver_step_batches": 1,
                    # "decay_min": 0.98,
                    # "decay_max": 0.9999,
                    "min_samples_per_class": 100,
                },
                # "feature_space": {
                #     "feature_k_min": 30,
                #     "feature_k_max": 120,
                #     "corr_threshold_min": 0.75,
                #     "corr_threshold_max": 0.95,
                #     "var_threshold_min": 0.0005,
                #     "var_threshold_max": 0.01,
                # },
                # "model_space": {
                #     "learning_rate_min": 0.005,
                #     "learning_rate_max": 0.15,
                #     "num_leaves_min": 16,
                #     "num_leaves_max": 96,
                #     "max_depth_min": 3,
                #     "max_depth_max": 10,
                #     "min_child_samples_min": 20,
                #     "min_child_samples_max": 150,
                #     "reg_lambda_min": 1e-4,
                #     "reg_lambda_max": 50.0,
                #     "reg_alpha_min": 1e-4,
                #     "reg_alpha_max": 50.0,
                #     "subsample_min": 0.4,
                #     "subsample_max": 0.9,
                #     "colsample_bytree_min": 0.4,
                #     "colsample_bytree_max": 0.9,
                #     "feature_fraction_bynode_min": 0.4,
                #     "feature_fraction_bynode_max": 0.9,
                #     "num_boost_round_min": 100,
                #     "num_boost_round_max": 800,
                # },
            },
            "target_breakfree": {
                "optuna_trials": 1200,
                "optuna_timeout": 60,
                "optuna_metric": "macro_f1",  # options: accuracy, log_loss, balanced_accuracy, macro_f1, macro_f1_up, macro_f1_down, directional_accuracy
                "track_pred_metrics": False,
                # "exclude_tail_pct": 0.33,
                # Optional stratified shuffle split within lookback window
                # "shuffle_split": True,
                # "shuffle_seed": 42,
                # "shuffle_val_ratio": 0.2,
                # Optional shuffle of batch order (keeps row order inside each batch)
                # "shuffle_batches": True,
                # "shuffle_batches_seed": 42,
                # Optional class balancing via resampling
                "balance_strategy": "upsample",  # upsample, downsample, none
                "balance_apply_to": "train",  # train or train_val
                "window_space": {
                    "lookback_min": 100,
                    "lookback_max": 450,
                    "window_selection_mode": "deterministic_solver",
                    "train_share_min": 0.70,
                    "train_share_max": 0.80,
                    "embargo_mode": "auto_tf",
                    "solver_step_batches": 1,
                    "min_samples_per_class": 100,
                },
            },
        },
        "15m": {
            "target_8class": {
                "optuna_trials": 2000,
                "optuna_timeout": 60,
                "optuna_metric": "macro_f1",  # options: accuracy, log_loss, balanced_accuracy, macro_f1, macro_f1_up, macro_f1_down, directional_accuracy
                "track_pred_metrics": False,
                # "exclude_tail_pct": 0.33,
                # Optional stratified shuffle split within lookback window
                # "shuffle_split": True,
                # "shuffle_seed": 42,
                # "shuffle_val_ratio": 0.2,
                # Optional shuffle of batch order (keeps row order inside each batch)
                # "shuffle_batches": True,
                # "shuffle_batches_seed": 42,
                # Optional class balancing via resampling
                "balance_strategy": "upsample",  # upsample, downsample, none
                "balance_apply_to": "train",  # train or train_val
                "window_space": {
                    "lookback_min": 100,
                    "lookback_max": 450,
                    "window_selection_mode": "deterministic_solver",
                    "train_share_min": 0.70,
                    "train_share_max": 0.80,
                    "embargo_mode": "auto_tf",
                    "solver_step_batches": 1,
                    # "decay_min": 0.95,
                    # "decay_max": 0.999,
                    "min_samples_per_class": 50,
                },
                # "feature_space": {
                #     "feature_k_min": 20,
                #     "feature_k_max": 100,
                #     "corr_threshold_min": 0.7,
                #     "corr_threshold_max": 0.95,
                #     "var_threshold_min": 0.001,
                #     "var_threshold_max": 0.01,
                # },
                # "model_space": {
                #     "learning_rate_min": 0.01,
                #     "learning_rate_max": 0.2,
                #     "num_leaves_min": 16,
                #     "num_leaves_max": 128,
                #     "max_depth_min": 4,
                #     "max_depth_max": 12,
                #     "min_child_samples_min": 10,
                #     "min_child_samples_max": 100,
                #     "reg_lambda_min": 1e-6,
                #     "reg_lambda_max": 10.0,
                #     "reg_alpha_min": 1e-6,
                #     "reg_alpha_max": 10.0,
                #     "subsample_min": 0.5,
                #     "subsample_max": 1.0,
                #     "colsample_bytree_min": 0.5,
                #     "colsample_bytree_max": 1.0,
                #     "feature_fraction_bynode_min": 0.5,
                #     "feature_fraction_bynode_max": 1.0,
                #     "num_boost_round_min": 100,
                #     "num_boost_round_max": 1000,
                # },
            },
            "target_breakfree": {
                "optuna_trials": 1200,
                "optuna_timeout": 60,
                "optuna_metric": "macro_f1",  # options: accuracy, log_loss, balanced_accuracy, macro_f1, macro_f1_up, macro_f1_down, directional_accuracy
                "track_pred_metrics": False,
                # "exclude_tail_pct": 0.33,
                # Optional stratified shuffle split within lookback window
                # "shuffle_split": True,
                # "shuffle_seed": 42,
                # "shuffle_val_ratio": 0.2,
                # Optional shuffle of batch order (keeps row order inside each batch)
                # "shuffle_batches": True,
                # "shuffle_batches_seed": 42,
                # Optional class balancing via resampling
                "balance_strategy": "upsample",  # upsample, downsample, none
                "balance_apply_to": "train",  # train or train_val
                "window_space": {
                    "lookback_min": 100,
                    "lookback_max": 450,
                    "window_selection_mode": "deterministic_solver",
                    "train_share_min": 0.70,
                    "train_share_max": 0.80,
                    "embargo_mode": "auto_tf",
                    "solver_step_batches": 1,
                    "min_samples_per_class": 50,
                },
            },
        },
    }
}


results = run_walk_forward_backtest(
    n_steps=120,
    timeframes=TIMEFRAMES_BY_MODEL[MODEL_NAME],
    model_name=MODEL_NAME,
    verbose=True,
    debug_batches=True,
    optuna_overrides_by_model=OPTUNA_OVERRIDES_BY_MODEL,
    targets_by_model=TARGETS_BY_MODEL,
    n_classes_by_model=N_CLASSES_BY_MODEL,
    class_names_by_model=CLASS_NAMES_BY_MODEL,
    feature_source_by_model=FEATURE_SOURCE_BY_MODEL,
    target_registry=TARGET_REGISTRY,
    run_id=RESUME_RUN_ID if RESUME else None,
    resume=RESUME,
    resume_mode=RESUME_MODE,
    allow_override_mismatch=ALLOW_OVERRIDE_MISMATCH,
)

# %%
