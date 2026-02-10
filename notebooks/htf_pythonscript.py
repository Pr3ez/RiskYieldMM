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
HTF_LABELS_DIR = DATA_DIR / "htf_4class_labels"
HTF_OPTIMIZED_DIR = DATA_DIR / "htf_optimized"
RAW_DATA_DIR = PROJECT_ROOT / "fetchingByBit"

# Create ALL required dirs (robust - works from scratch)
DATA_DIR.mkdir(parents=True, exist_ok=True)
HTF_BACKTEST_DIR.mkdir(parents=True, exist_ok=True)
HTF_FEATURES_DIR.mkdir(parents=True, exist_ok=True)
HTF_LABELS_DIR.mkdir(parents=True, exist_ok=True)
HTF_OPTIMIZED_DIR.mkdir(parents=True, exist_ok=True)

# Timeframes we're working with (1m/5m/15m; 1h excluded)
HTF_TIMEFRAMES = ["1m", "5m", "15m"]

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

    # Guard against overlapping raw source files:
    # keep one row per normalized timestamp (latest row wins).
    # This prevents oversized batches when raw batches overlap in time.
    rows_before_dedup = len(df)
    df = df.unique(subset=["ts_norm"], keep="last", maintain_order=True)
    rows_after_dedup = len(df)
    duplicate_rows_removed = rows_before_dedup - rows_after_dedup

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
        "rows_before_dedup": rows_before_dedup,
        "rows_after_dedup": rows_after_dedup,
        "duplicate_rows_removed": duplicate_rows_removed,
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
        print(
            f"    Rows: {result['total_rows']:,} "
            f"(dedup removed {result['duplicate_rows_removed']:,})"
        )
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
import json
import sys
from datetime import datetime
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
RECOMPUTE_FEATURES = False  # Fast mode default: reuse existing feature batches (set True for full rebuild)

# Ensure bars-per-batch mapping exists (Cell 7 defines it; keep safe default here)
if "BARS_PER_8H" not in globals():
    BARS_PER_8H = {"1m": 480, "5m": 96, "15m": 32}

# Rolling distance feature windows (fixed from IC optimization)
# These are past-window (causal) distances based on OHLCV only.
DISTANCE_WINDOWS_BY_TF = {
    # Keep time-equivalent horizons across TFs:
    # 1m: 240/120 bars == 5m: 48/24 bars == 15m: 16/8 bars
    "1m": {
        "dist_avg_high": 240,
        "dist_avg_low": 240,
        "dist_top5_high": 240,
        "dist_bot5_low": 120,
    },
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
        meta_path = tf_output_dir / "_build_meta.json"
        if meta_path.exists():
            print(f"  ✓ Existing metadata: {meta_path.name}")
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
    batch_stats = (
        df_pl.group_by("batch_id")
        .agg(
            [
                pl.len().alias("rows"),
                pl.col("timestamp").min().alias("first_ts"),
                pl.col("timestamp").max().alias("last_ts"),
            ]
        )
        .sort("batch_id")
    )

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

    # Persist build metadata for robust incremental/live updates
    expected_rows = int(bars_per_batch)
    incomplete_stats = batch_stats.filter(pl.col("rows") < expected_rows)
    last_batch_id = int(batch_stats["batch_id"].max())
    last_batch_row = batch_stats.filter(pl.col("batch_id") == last_batch_id).row(
        0, named=True
    )
    source_plan = engine.get_source_resolution_plan(tf)
    feature_meta = {
        "timeframe": tf,
        "created_at_utc": f"{datetime.utcnow().isoformat()}Z",
        "source_file": str(src_path),
        "source_plan": source_plan,
        "recompute_features": bool(RECOMPUTE_FEATURES),
        "distance_windows": DISTANCE_WINDOWS_BY_TF.get(tf, {}),
        "distance_outlier_pct": float(DISTANCE_OUTLIER_PCT),
        "rows_total": int(len(df_pl)),
        "batches_total": int(len(batch_ids)),
        "expected_rows_per_batch": expected_rows,
        "incomplete_batches_count": int(len(incomplete_stats)),
        "incomplete_batch_ids": [
            int(v) for v in incomplete_stats["batch_id"].to_list()
        ],
        "first_batch_id": int(batch_stats["batch_id"].min()),
        "last_batch_id": last_batch_id,
        "first_timestamp": str(batch_stats["first_ts"].min()),
        "last_timestamp": str(batch_stats["last_ts"].max()),
        "last_batch_rows": int(last_batch_row["rows"]),
        "last_batch_first_timestamp": str(last_batch_row["first_ts"]),
        "last_batch_last_timestamp": str(last_batch_row["last_ts"]),
        "columns_total": int(len(df_pl.columns)),
        "output_dir": str(tf_output_dir),
        "output_pattern": "batch_XXXX.parquet",
    }
    meta_path = tf_output_dir / "_build_meta.json"
    with open(meta_path, "w") as f:
        json.dump(feature_meta, f, indent=2)
    print(f"  ✓ Saved metadata: {meta_path.name}")

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
# CELL 7: COMPUTE DISTANCE METRICS FOR 4-CLASS TARGET LABELING
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
HTF_LABELS_DIR = DATA_DIR / "htf_4class_labels"
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

# Timeframes to process in this cell (1m hybrid labels are built in CELL 9B)
HTF_TIMEFRAMES = ["5m", "15m"]

RECOMPUTE_DISTANCE_METRICS = False  # Fast mode default: update tail batches only when INCREMENTAL_DISTANCE_METRICS=True
INCREMENTAL_DISTANCE_METRICS = (
    True  # If True and RECOMPUTE_DISTANCE_METRICS=False, rebuild only tail batches
)
INCREMENTAL_TAIL_BATCHES_BY_TF = {"5m": 8, "15m": 8}

print("=" * 70)
print("DISTANCE METRICS COMPUTATION FOR 4-CLASS TARGET LABELING")
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
if RECOMPUTE_DISTANCE_METRICS or INCREMENTAL_DISTANCE_METRICS:
    run_mode = "full_recompute" if RECOMPUTE_DISTANCE_METRICS else "incremental_tail"
    print(f"Run mode: {run_mode}")
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
        #    - always keep LAST (possibly incomplete) batch for live-update continuity
        #      (rows without enough forward bars will naturally stay unlabeled later)
        bars_per_batch = BARS_PER_8H[tf]
        min_remaining = MIN_REMAINING_BARS_BY_TF.get(tf, 1)
        # Keep last batch even if it has only 1 row
        min_last_batch_bars = 1

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
            f"(last batch included with >= {min_last_batch_bars} row)"
        )

        output_path = HTF_BACKTEST_DIR / f"{tf}_distance_metrics.parquet"
        if RECOMPUTE_DISTANCE_METRICS or not output_path.exists():
            rebuild_batches = valid_batches
            print("  Rebuild scope: all valid batches")
        else:
            tail_n = INCREMENTAL_TAIL_BATCHES_BY_TF.get(tf, 8)
            rebuild_batches = valid_batches[-tail_n:]
            print(
                f"  Rebuild scope: tail {len(rebuild_batches)} batches "
                f"({rebuild_batches[0]}..{rebuild_batches[-1]})"
            )

        if len(rebuild_batches) == 0:
            print("  ⚠️ No batches selected for rebuild, skipping timeframe")
            continue

        df = df.filter(pl.col("batch_id").is_in(rebuild_batches))

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

        # 8. Save per-bar metrics (incremental upsert by batch_id)
        if RECOMPUTE_DISTANCE_METRICS or not output_path.exists():
            df_out = df
        else:
            df_prev = pl.read_parquet(output_path).filter(
                ~pl.col("batch_id").is_in(rebuild_batches)
            )
            df_out = pl.concat([df_prev, df], how="diagonal_relaxed").sort(
                ["batch_id", "timestamp"]
            )

        df_out.write_parquet(output_path)
        print(f"  ✓ Saved {output_path.name}")
        meta = {
            "updated_at": datetime.now().isoformat(),
            "mode": run_mode,
            "timeframe": tf,
            "updated_batches": [int(b) for b in rebuild_batches],
            "updated_batches_count": int(len(rebuild_batches)),
            "total_rows_saved": int(len(df_out)),
            "min_remaining_bars": int(min_remaining),
            "bars_per_batch": int(bars_per_batch),
        }
        meta_path = HTF_BACKTEST_DIR / f"{tf}_distance_metrics_meta.json"
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)
        print(f"  ✓ Saved {meta_path.name}")

        del df
        if "df_out" in locals():
            del df_out
        if "df_prev" in locals():
            del df_prev
        gc.collect()

    print("\n" + "=" * 70)
    print("PHASE 1.3 COMPLETE: Distance metrics computed for all timeframes")
    print("=" * 70)
else:
    print(
        "Skipping recomputation (RECOMPUTE_DISTANCE_METRICS=False and INCREMENTAL_DISTANCE_METRICS=False)"
    )


# =============================================================================
# STEP 1.4: COMPUTE PER-BATCH AGGREGATES
# =============================================================================
print("\n" + "=" * 70)
print("STEP 1.4: COMPUTING PER-BATCH AGGREGATES")
print("=" * 70)


@njit
def compute_4class_label_numba(
    dist_avg_high,
    dist_avg_low,
    dist_top5_high,
    dist_bot5_low,
    breakout_thresh,
    risk_ratio,
):
    """Compute 4-class label for a single bar."""
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

    is_expansion = high_risk_up or high_risk_down
    if is_up:
        return 3 if is_expansion else 2  # UP_EXPANSION / UP_BALANCED
    return 1 if is_expansion else 0  # DOWN_EXPANSION / DOWN_BALANCED


@njit
def compute_4class_labels_batch(
    dist_avg_high,
    dist_avg_low,
    dist_top5_high,
    dist_bot5_low,
    breakout_thresh,
    risk_ratio,
):
    """Vectorized 4-class labeling using numba."""
    n = len(dist_avg_high)
    labels = np.full(n, -1, dtype=np.int8)
    for i in range(n):
        labels[i] = compute_4class_label_numba(
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

    # Compute 4-class labels using numba
    labels = compute_4class_labels_batch(
        df["dist_avg_high"].to_numpy(),
        df["dist_avg_low"].to_numpy(),
        df["dist_top5_high"].to_numpy(),
        df["dist_bot5_low"].to_numpy(),
        thresholds["BREAKOUT"],
        thresholds["RISK_RATIO"],
    )
    df = df.with_columns(pl.Series("target_4class", labels))

    # Re-save with labels
    df.write_parquet(HTF_BACKTEST_DIR / f"{tf}_distance_metrics.parquet")

    # Check if we have valid data for batch stats
    valid_df = df.filter(pl.col("target_4class") >= 0)
    if len(valid_df) == 0:
        print(f"  ⚠️ No valid bars for {tf}, skipping batch stats")
        del df
        gc.collect()
        continue

    # Aggregate per batch
    batch_stats = valid_df.group_by("batch_id").agg(
        [
            (pl.col("target_4class") == 0).sum().alias("class_0_count"),
            (pl.col("target_4class") == 1).sum().alias("class_1_count"),
            (pl.col("target_4class") == 2).sum().alias("class_2_count"),
            (pl.col("target_4class") == 3).sum().alias("class_3_count"),
            pl.len().alias("valid_bars"),
            (pl.col("target_4class").is_in([2, 3])).mean().alias("up_pct"),
            pl.col("dist_top5_high").mean().alias("avg_top5_high"),
            pl.col("dist_bot5_low").mean().alias("avg_bot5_low"),
            ((pl.col("target_4class").is_in([1, 3])).mean()).alias(
                "outlier_frequency"
            ),
        ]
    )

    # Compute dominant class
    class_cols = [f"class_{i}_count" for i in range(4)]
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
    for cls in range(4):
        count = len(valid_df.filter(pl.col("target_4class") == cls))
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
# CELL 8: 4-CLASS TARGET LABELING (15m IMPLEMENTATION)
# =============================================================================
# Implements the validated 4-class labeling system:
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
# Output: {tf}_labels.parquet in HTF_LABELS_DIR (target_4class)
# =============================================================================

import json
from datetime import datetime
from pathlib import Path

import polars as pl

# =============================================================================
# PATHS
# =============================================================================
PROJECT_ROOT = Path("..").resolve()
DATA_DIR = PROJECT_ROOT / "data"
HTF_BACKTEST_DIR = DATA_DIR / "htf_backtest"
HTF_LABELS_DIR = DATA_DIR / "htf_4class_labels"
HTF_LABELS_DIR.mkdir(exist_ok=True)

# =============================================================================
# PER-TIMEFRAME OPTIMAL THRESHOLDS (from grid search)
# (Defined in STEP 1.1 above; reused here)
# =============================================================================

# Class names for display
CLASS_NAMES = {
    0: "DOWN_BALANCED",
    1: "DOWN_EXPANSION",
    2: "UP_BALANCED",
    3: "UP_EXPANSION",
}

# Target distribution reference (collapsed from prior detailed class scheme)
DOC_TARGETS = {0: 25.5, 1: 23.6, 2: 28.4, 3: 22.6}

# Breakfree threshold (end-of-batch close distance)
# end_return = (close_end - close_now) / close_now
# target_breakfree (3-class, position-aware, non-overlapping):
#   0: UP_ABOVE_BREAKFREE
#      (4-class is UP-side and end_return >= +threshold)
#   1: DOWN_ABOVE_BREAKFREE
#      (4-class is DOWN-side and end_return <= -threshold)
#   2: IN_BETWEEN_BELOW_BREAKFREE
#      (valid 4-class row but neither UP_ABOVE nor DOWN_ABOVE condition met)
#   -1: invalid / unlabeled (invalid 4-class row)
BREAKFREE_THRESHOLD = 0.001  # 0.10%
# Only consider entries in the first 4h of each 8h batch
ENTRY_WINDOW_HOURS = 4

# Which timeframes to process (15m first since it matches perfectly)
PROCESS_TIMEFRAMES = ["15m"]  # Add "5m" later with 5m-specific targets

RECOMPUTE_LABELS = False  # Fast mode default: update label tail batches only
INCREMENTAL_LABEL_UPDATE = True
INCREMENTAL_LABEL_TAIL_BATCHES_BY_TF = {"15m": 8, "5m": 8, "1m": 8}

print("=" * 70)
print("4-CLASS TARGET LABELING")
print("=" * 70)
print(f"Processing timeframes: {PROCESS_TIMEFRAMES}")
print(f"Output directory: {HTF_LABELS_DIR}")
print(f"Min remaining bars per TF: {MIN_REMAINING_BARS_BY_TF} (exclude last bars)")
print(f"Entry window: first {ENTRY_WINDOW_HOURS}h of each 8h batch")
print("=" * 70)


# =============================================================================
# LABELING FUNCTION (VECTORIZED POLARS)
# =============================================================================
def compute_4class_labels(
    df: pl.DataFrame, breakout_thresh: float, risk_thresh: float
) -> pl.DataFrame:
    """
    Compute 4-class labels using vectorized Polars expressions.

    Classes:
    - 0 DOWN_BALANCED
    - 1 DOWN_EXPANSION
    - 2 UP_BALANCED
    - 3 UP_EXPANSION
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

    # Compute 4-class label
    df = df.with_columns(
        [
            pl.when(pl.col("dist_avg_high").is_nan())
            .then(pl.lit(-1))  # Invalid bar
            .when(
                pl.col("is_up") & (pl.col("high_risk_up") | pl.col("high_risk_down"))
            )
            .then(pl.lit(3))  # UP_EXPANSION
            .when(pl.col("is_up"))
            .then(pl.lit(2))  # UP_BALANCED
            .when(
                ~pl.col("is_up") & (pl.col("high_risk_up") | pl.col("high_risk_down"))
            )
            .then(pl.lit(1))  # DOWN_EXPANSION
            .when(~pl.col("is_up"))
            .then(pl.lit(0))  # DOWN_BALANCED
            .otherwise(pl.lit(-1))
            .alias("target_4class")
        ]
    )

    # Add class name column
    df = df.with_columns(
        [
            pl.col("target_4class")
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

    # Incremental scope: rebuild only tail batches if label files already exist
    tf_labels_dir = HTF_LABELS_DIR / tf
    tf_labels_dir.mkdir(exist_ok=True)
    existing_label_files = sorted(tf_labels_dir.glob("batch_*.parquet"))
    all_batches = sorted(df["batch_id"].unique().to_list())
    if RECOMPUTE_LABELS or not INCREMENTAL_LABEL_UPDATE or not existing_label_files:
        target_batches = all_batches
        print("  Label scope: full")
    else:
        tail_n = INCREMENTAL_LABEL_TAIL_BATCHES_BY_TF.get(tf, 8)
        target_batches = all_batches[-tail_n:]
        print(
            f"  Label scope: incremental tail {len(target_batches)} "
            f"({target_batches[0]}..{target_batches[-1]})"
        )

    df = df.filter(pl.col("batch_id").is_in(target_batches))
    if len(df) == 0:
        print("  ⚠️ No rows in selected label scope, skipping timeframe")
        continue

    # Compute end-of-batch close distance for breakfree target
    batch_close = df.group_by("batch_id").agg(
        pl.col("close").sort_by("timestamp").last().alias("close_end")
    )
    df = df.join(batch_close, on="batch_id", how="left").with_columns(
        ((pl.col("close_end") - pl.col("close")) / pl.col("close")).alias("end_return")
    )

    # Count valid rows (current batch only), then keep first 4h entry window.
    # We still compute/save labels for ALL rows; invalid rows become -1.
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

    if len(df) == 0:
        print(f"  ⚠️ No rows for {tf}. Skipping.")
        continue

    # Compute 4-class labels on full rows; invalid horizon rows become -1
    print("Computing 4-class labels...")
    df_labeled = compute_4class_labels(df, bt, rt)
    df_labeled = df_labeled.with_columns(
        [
            pl.when(pl.col("bar_pos") < entry_bar_limit)
            .then(pl.col("target_4class"))
            .otherwise(pl.lit(-1))
            .alias("target_4class")
        ]
    )
    df_labeled = df_labeled.with_columns(
        [
            pl.col("target_4class")
            .replace_strict(
                {i: name for i, name in CLASS_NAMES.items()}, default="INVALID"
            )
            .alias("target_name")
        ]
    )

    # Breakfree 3-class target (position-aware and non-overlapping)
    # UP classes in 4-class: 2,3
    # DOWN classes in 4-class: 0,1
    df_labeled = df_labeled.with_columns(
        [
            pl.when(pl.col("target_4class") < 0)
            .then(pl.lit(-1))
            .when(
                pl.col("target_4class").is_in([2, 3])
                & (pl.col("end_return") >= BREAKFREE_THRESHOLD)
            )
            .then(pl.lit(0))  # UP_ABOVE_BREAKFREE
            .when(
                pl.col("target_4class").is_in([0, 1])
                & (pl.col("end_return") <= -BREAKFREE_THRESHOLD)
            )
            .then(pl.lit(1))  # DOWN_ABOVE_BREAKFREE
            .otherwise(pl.lit(2))  # IN_BETWEEN_BELOW_BREAKFREE
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
        df_labeled.filter(pl.col("target_4class") >= 0)
        .group_by("target_4class")
        .agg(pl.len().alias("count"))
        .sort("target_4class")
    )

    total = class_counts["count"].sum()

    print(
        f"\n{'Class':<3} {'Name':<20} {'Count':>10} {'Actual':>8} {'Target':>8} {'Diff':>8} {'Status'}"
    )
    print("-" * 75)

    mse = 0.0
    for cls in range(4):
        row = class_counts.filter(pl.col("target_4class") == cls)
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
        "DOWN_SIDE": [0, 1],
        "UP_SIDE": [2, 3],
        "BALANCED": [0, 2],
        "EXPANSION": [1, 3],
    }
    doc_group = {
        "DOWN_SIDE": DOC_TARGETS[0] + DOC_TARGETS[1],
        "UP_SIDE": DOC_TARGETS[2] + DOC_TARGETS[3],
        "BALANCED": DOC_TARGETS[0] + DOC_TARGETS[2],
        "EXPANSION": DOC_TARGETS[1] + DOC_TARGETS[3],
    }

    for name, classes in groups.items():
        group_count = sum(
            class_counts.filter(pl.col("target_4class") == c)["count"][0]
            if len(class_counts.filter(pl.col("target_4class") == c)) > 0
            else 0
            for c in classes
        )
        pct = 100 * group_count / total if total > 0 else 0
        target = doc_group[name]
        print(f"  {name:<12}: {pct:>6.1f}% (target: {target:.1f}%)")

    # ==========================================================================
    # SAVE LABELED DATA (PER-BATCH for downstream compatibility)
    # ==========================================================================
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
        "target_4class",
        "target_name",
        "target_breakfree",
        # Labels
    ]

    # Only keep columns that exist
    available_cols = [c for c in output_cols if c in df_labeled.columns]
    df_output = df_labeled.select(available_cols)

    # Save per-batch (8h aligned) - overwrite only selected scope
    batch_ids = df_output["batch_id"].unique().sort().to_list()
    for bid in batch_ids:
        batch_df = df_output.filter(pl.col("batch_id") == bid)
        batch_path = tf_labels_dir / f"batch_{bid:04d}.parquet"
        batch_df.write_parquet(batch_path)

    print(f"  ✓ Saved {len(batch_ids):,} batch files ({len(df_output):,} total rows)")
    labels_meta = {
        "updated_at": datetime.now().isoformat(),
        "timeframe": tf,
        "mode": "full"
        if (RECOMPUTE_LABELS or not existing_label_files)
        else "incremental_tail",
        "updated_batches": [int(b) for b in batch_ids],
        "updated_batches_count": int(len(batch_ids)),
        "entry_window_hours": ENTRY_WINDOW_HOURS,
        "breakfree_threshold": BREAKFREE_THRESHOLD,
    }
    labels_meta_path = tf_labels_dir / "_labels_meta.json"
    with open(labels_meta_path, "w") as f:
        json.dump(labels_meta, f, indent=2)
    print(f"  ✓ Saved {labels_meta_path.name}")

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
print("4-CLASS LABELING COMPLETE")
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
print("1. Use target_4class as ML target for classification")
print("2. Filter to valid rows (target_4class >= 0)")
print("3. Train model to predict class given features")
print("4. For 5m/1m hybrid, use 15m future bars for distance metrics")
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
# Output: data/htf_4class_labels/5m/batch_XXXX.parquet
# =============================================================================

import gc
import json
from datetime import datetime
from pathlib import Path

import polars as pl
from numba import njit

# =============================================================================
# PATHS
# =============================================================================
PROJECT_ROOT = Path("..").resolve()
DATA_DIR = PROJECT_ROOT / "data"
HTF_BACKTEST_DIR = DATA_DIR / "htf_backtest"
HTF_LABELS_DIR = DATA_DIR / "htf_4class_labels"
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
    1: "DOWN_EXPANSION",
    2: "UP_BALANCED",
    3: "UP_EXPANSION",
}

# Reference distribution (collapsed from prior detailed class scheme)
DOC_TARGETS = {0: 25.5, 1: 23.6, 2: 28.4, 3: 22.6}
INCREMENTAL_LABEL_UPDATE_5M = True
INCREMENTAL_TAIL_BATCHES_5M = 8

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

# Filter to valid batches (always include last incomplete batch for live continuity)
counts_5m = df_5m.group_by("batch_id").agg(pl.len().alias("n")).sort("batch_id")
counts_15m = df_15m.group_by("batch_id").agg(pl.len().alias("n")).sort("batch_id")

last_5m = counts_5m["batch_id"].max()
last_15m = counts_15m["batch_id"].max()

min_last_5m = 1  # include last batch even if currently unlabeled
min_last_15m_label = 1  # include last 15m batch even if currently unlabeled

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
    f"(last batch included with >= {min_last_5m} row in each TF)"
)

tf_labels_dir = HTF_LABELS_DIR / "5m"
tf_labels_dir.mkdir(exist_ok=True)
existing_5m_labels = sorted(tf_labels_dir.glob("batch_*.parquet"))
sorted_label_batches = sorted(label_batches)
if INCREMENTAL_LABEL_UPDATE_5M and existing_5m_labels and len(sorted_label_batches) > 0:
    target_batches_5m = set(sorted_label_batches[-INCREMENTAL_TAIL_BATCHES_5M:])
    min_target = min(target_batches_5m)
    warmup_batch = min_target - 1
    compute_batches_5m = set(target_batches_5m)
    if warmup_batch in label_batches:
        compute_batches_5m.add(warmup_batch)
    print(
        f"  Incremental label update: target={len(target_batches_5m)} batches, "
        f"compute={len(compute_batches_5m)} (includes warmup)"
    )
else:
    target_batches_5m = set(label_batches)
    compute_batches_5m = set(label_batches)
    print("  Label update mode: full")

df_5m = df_5m.filter(pl.col("batch_id").is_in(compute_batches_5m))
df_15m = df_15m.filter(pl.col("batch_id").is_in(compute_batches_5m))

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
# STEP 5: COMPUTE 4-CLASS LABELS
# =============================================================================
print("\n[STEP 5] Computing 4-class labels...")


def compute_4class_labels(
    df: pl.DataFrame, breakout_thresh: float, risk_thresh: float
) -> pl.DataFrame:
    """Compute 4-class labels using dual-threshold approach."""
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

    # 4-class assignment
    df = df.with_columns(
        [
            pl.when(pl.col("dist_avg_high").is_nan())
            .then(pl.lit(-1))
            .when(
                pl.col("is_up") & (pl.col("high_risk_up") | pl.col("high_risk_down"))
            )
            .then(pl.lit(3))  # UP_EXPANSION
            .when(pl.col("is_up"))
            .then(pl.lit(2))  # UP_BALANCED
            .when(
                ~pl.col("is_up") & (pl.col("high_risk_up") | pl.col("high_risk_down"))
            )
            .then(pl.lit(1))  # DOWN_EXPANSION
            .when(~pl.col("is_up"))
            .then(pl.lit(0))  # DOWN_BALANCED
            .otherwise(pl.lit(-1))
            .alias("target_4class")
        ]
    )

    # Add class name
    df = df.with_columns(
        [
            pl.col("target_4class")
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


df_labeled = compute_4class_labels(df_5m, BREAKOUT_THRESHOLD, RISK_RATIO)

# Breakfree 3-class target (position-aware, non-overlapping)
df_labeled = df_labeled.with_columns(
    [
        pl.when(pl.col("target_4class") < 0)
        .then(pl.lit(-1))
        .when(pl.col("target_4class").is_in([2, 3]) & (pl.col("end_return") >= BREAKFREE_THRESHOLD_5M))
        .then(pl.lit(0))  # UP_ABOVE_BREAKFREE
        .when(pl.col("target_4class").is_in([0, 1]) & (pl.col("end_return") <= -BREAKFREE_THRESHOLD_5M))
        .then(pl.lit(1))  # DOWN_ABOVE_BREAKFREE
        .otherwise(pl.lit(2))  # IN_BETWEEN_BELOW_BREAKFREE
        .alias("target_breakfree")
    ]
)

# Keep labels only for first 4h entry window; mark later bars as invalid
df_labeled = df_labeled.with_columns(
    [
        pl.when(pl.col("bar_pos_5m") < entry_bar_limit_5m)
        .then(pl.col("target_4class"))
        .otherwise(pl.lit(-1))
        .alias("target_4class"),
        pl.when(pl.col("bar_pos_5m") < entry_bar_limit_5m)
        .then(pl.col("target_breakfree"))
        .otherwise(pl.lit(-1))
        .alias("target_breakfree"),
    ]
)
df_labeled = df_labeled.with_columns(
    [
        pl.col("target_4class")
        .replace_strict({i: name for i, name in CLASS_NAMES.items()}, default="INVALID")
        .alias("target_name")
    ]
)

# =============================================================================
# STEP 6: VALIDATE CLASS DISTRIBUTION
# =============================================================================
print("\n[STEP 6] Validating class distribution...")

class_counts = (
    df_labeled.filter(pl.col("target_4class") >= 0)
    .group_by("target_4class")
    .agg(pl.len().alias("count"))
    .sort("target_4class")
)

total = class_counts["count"].sum()

print(
    f"\n{'Class':<3} {'Name':<20} {'Count':>10} {'Actual':>8} {'Target':>8} {'Diff':>8} {'Status'}"
)
print("-" * 75)

mse = 0.0
for cls in range(4):
    row = class_counts.filter(pl.col("target_4class") == cls)
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
print("(Hybrid 5m should remain close to 15m-side risk structure)")

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
    "target_4class",
    "target_name",
    "target_breakfree",
]

available_cols = [c for c in output_cols if c in df_labeled.columns]
df_output = df_labeled.filter(pl.col("batch_id").is_in(target_batches_5m)).select(
    available_cols
)

# Save per-batch (8h aligned)
batch_ids = df_output["batch_id"].unique().sort().to_list()
for bid in batch_ids:
    batch_df = df_output.filter(pl.col("batch_id") == bid)
    batch_path = tf_labels_dir / f"batch_{bid:04d}.parquet"
    batch_df.write_parquet(batch_path)

print(f"  ✓ Saved {len(batch_ids):,} batch files to {tf_labels_dir}")
print(f"  ✓ Total rows: {len(df_output):,}")
labels_meta_5m = {
    "updated_at": datetime.now().isoformat(),
    "timeframe": "5m",
    "mode": "incremental_tail"
    if (INCREMENTAL_LABEL_UPDATE_5M and existing_5m_labels)
    else "full",
    "updated_batches": [int(b) for b in batch_ids],
    "updated_batches_count": int(len(batch_ids)),
    "entry_window_hours": ENTRY_WINDOW_HOURS_5M,
    "breakfree_threshold": BREAKFREE_THRESHOLD_5M,
}
with open(tf_labels_dir / "_labels_meta.json", "w") as f:
    json.dump(labels_meta_5m, f, indent=2)
print("  ✓ Saved _labels_meta.json")

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
print(f"Valid labels: {len(df_output.filter(pl.col('target_4class') >= 0)):,}")

# Show column info
print(f"\nColumns saved ({len(available_cols)}):")
for col in available_cols:
    print(f"  - {col}")

# Cleanup
del df_5m, df_15m, df_labeled, df_output, df_valid
gc.collect()

print("\n" + "=" * 70)
print("NEXT: Build 1m hybrid labels, then continue with helper/optimization cells")
print("=" * 70)

# %%
# =============================================================================
# CELL 9B: HYBRID 1m TARGET LABELING (1m ENTRY + 15m DISTANCE METRICS)
# =============================================================================
# This mirrors Cell 9 logic used for 5m:
#   - Entry reference: 1m close
#   - Future distance metrics: remaining 15m bars from the same 8h batch
#   - Same BREAKOUT/RISK thresholds as 15m and 5m hybrid, so target levels align
#   - Labels restricted to first 4h of each 8h batch
#
# Output: data/htf_4class_labels/1m/batch_XXXX.parquet
# =============================================================================

import gc
import json
from datetime import datetime
from pathlib import Path

import polars as pl

if "compute_hybrid_distance_metrics" not in globals():
    raise RuntimeError(
        "Run CELL 9 first (compute_hybrid_distance_metrics is required)."
    )
if "compute_4class_labels" not in globals():
    raise RuntimeError("Run CELL 9 first (compute_4class_labels is required).")

PROJECT_ROOT = Path("..").resolve()
DATA_DIR = PROJECT_ROOT / "data"
HTF_BACKTEST_DIR = DATA_DIR / "htf_backtest"
HTF_LABELS_DIR = DATA_DIR / "htf_4class_labels"
HTF_LABELS_DIR.mkdir(exist_ok=True)

# 1m entry config (hybrid distances still use 15m bars)
MIN_REMAINING_BARS_15M = 1
MIN_REMAINING_BARS_1M = MIN_REMAINING_BARS_15M * 15
BARS_PER_8H_15M = 32
BARS_PER_8H_1M = 480
ENTRY_WINDOW_HOURS_1M = 4
BREAKFREE_THRESHOLD_1M = 0.001  # 0.10%
INCREMENTAL_LABEL_UPDATE_1M = True
INCREMENTAL_TAIL_BATCHES_1M = 8

print("=" * 70)
print("HYBRID 1m TARGET LABELING (1m Entry + 15m Distance Metrics)")
print("=" * 70)
print(f"Thresholds: BREAKOUT={BREAKOUT_THRESHOLD}%, RISK_RATIO={RISK_RATIO}x")
print(f"Entry window: first {ENTRY_WINDOW_HOURS_1M}h of each 8h batch")
print("=" * 70)

print("\n[STEP 1] Loading 1m + 15m data...")
df_1m = pl.read_parquet(HTF_BACKTEST_DIR / "1m_HTF_combined.parquet").sort("timestamp")
df_15m = pl.read_parquet(HTF_BACKTEST_DIR / "15m_HTF_combined.parquet").sort(
    "timestamp"
)

print(f"  1m bars: {len(df_1m):,}")
print(f"  15m bars: {len(df_15m):,}")

# Keep full batches and always include last partial batch for live continuity
counts_1m = df_1m.group_by("batch_id").agg(pl.len().alias("n")).sort("batch_id")
counts_15m = df_15m.group_by("batch_id").agg(pl.len().alias("n")).sort("batch_id")
last_1m = counts_1m["batch_id"].max()
last_15m = counts_15m["batch_id"].max()
min_last_1m = 1
min_last_15m = 1

valid_1m = counts_1m.filter(
    (pl.col("n") == BARS_PER_8H_1M)
    | ((pl.col("batch_id") == last_1m) & (pl.col("n") >= min_last_1m))
)["batch_id"].to_list()
valid_15m_for_label = counts_15m.filter(
    (pl.col("n") == BARS_PER_8H_15M)
    | ((pl.col("batch_id") == last_15m) & (pl.col("n") >= min_last_15m))
)["batch_id"].to_list()

label_batches = set(valid_1m) & set(valid_15m_for_label)
print(
    f"  Label batches (both TFs): {len(label_batches):,} "
    f"(last batch included with >= {min_last_1m} row in each TF)"
)

tf_labels_dir_1m = HTF_LABELS_DIR / "1m"
tf_labels_dir_1m.mkdir(exist_ok=True)
existing_1m_labels = sorted(tf_labels_dir_1m.glob("batch_*.parquet"))
sorted_label_batches_1m = sorted(label_batches)
if (
    INCREMENTAL_LABEL_UPDATE_1M
    and existing_1m_labels
    and len(sorted_label_batches_1m) > 0
):
    target_batches_1m = set(sorted_label_batches_1m[-INCREMENTAL_TAIL_BATCHES_1M:])
    min_target_1m = min(target_batches_1m)
    warmup_batch_1m = min_target_1m - 1
    compute_batches_1m = set(target_batches_1m)
    if warmup_batch_1m in label_batches:
        compute_batches_1m.add(warmup_batch_1m)
    print(
        f"  Incremental label update: target={len(target_batches_1m)} batches, "
        f"compute={len(compute_batches_1m)} (includes warmup)"
    )
else:
    target_batches_1m = set(label_batches)
    compute_batches_1m = set(label_batches)
    print("  Label update mode: full")

df_1m = df_1m.filter(pl.col("batch_id").is_in(compute_batches_1m))
df_15m = df_15m.filter(pl.col("batch_id").is_in(compute_batches_1m))
print(f"  Filtered 1m bars: {len(df_1m):,}")
print(f"  Filtered 15m bars: {len(df_15m):,}")

# End-of-batch close distance for breakfree target
batch_close_1m = df_1m.group_by("batch_id").agg(
    pl.col("close").sort_by("timestamp").last().alias("close_end")
)
df_1m = df_1m.join(batch_close_1m, on="batch_id", how="left").with_columns(
    ((pl.col("close_end") - pl.col("close")) / pl.col("close")).alias("end_return")
)

print("\n[STEP 2] Computing bar positions and 15m mapping...")
df_1m = df_1m.with_columns(
    (pl.col("timestamp").rank("ordinal").over("batch_id") - 1)
    .cast(pl.Int32)
    .alias("bar_pos_1m")
)
df_1m = df_1m.with_columns(pl.col("timestamp").dt.truncate("15m").alias("ts_15m"))
df_15m = df_15m.with_columns(
    (pl.col("timestamp").rank("ordinal").over("batch_id") - 1)
    .cast(pl.Int32)
    .alias("bar_pos_15m")
)

# BB context on 1m entry stream
df_1m = (
    df_1m.with_columns(
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
        (
            (pl.col("close") - pl.col("bb_lower"))
            / (pl.col("bb_upper") - pl.col("bb_lower"))
            * 100
        ).alias("bb_position_pct")
    )
)
df_1m = df_1m.with_columns((pl.col("bar_pos_1m") // 120).alias("segment_2h"))

print("\n[STEP 3] Computing hybrid distance metrics (1m entry, 15m future)...")
df_15m_pos = df_15m.select(
    [
        pl.col("timestamp").alias("ts_15m"),
        pl.col("batch_id").alias("batch_id_check"),
        "bar_pos_15m",
    ]
)
df_1m = df_1m.join(df_15m_pos, on="ts_15m", how="left")

close_1m_np = df_1m["close"].to_numpy().astype("float64")
batch_id_1m_np = df_1m["batch_id"].to_numpy().astype("int64")
bar_pos_15m_for_1m_np = df_1m["bar_pos_15m"].fill_null(0).to_numpy().astype("int32")
high_15m_np = df_15m["high"].to_numpy().astype("float64")
low_15m_np = df_15m["low"].to_numpy().astype("float64")
batch_id_15m_np = df_15m["batch_id"].to_numpy().astype("int64")
bar_pos_15m_np = df_15m["bar_pos_15m"].to_numpy().astype("int32")

d_avg_high, d_avg_low, d_top5_high, d_bot5_low, remaining = (
    compute_hybrid_distance_metrics(
        close_1m_np,
        batch_id_1m_np,
        bar_pos_15m_for_1m_np,
        high_15m_np,
        low_15m_np,
        batch_id_15m_np,
        bar_pos_15m_np,
        MIN_REMAINING_BARS_15M,
        OUTLIER_PERCENTILE,
    )
)

df_1m = df_1m.with_columns(
    [
        pl.Series("dist_avg_high", d_avg_high),
        pl.Series("dist_avg_low", d_avg_low),
        pl.Series("dist_top5_high", d_top5_high),
        pl.Series("dist_bot5_low", d_bot5_low),
        pl.Series("remaining_bars", remaining),
    ]
)

entry_bar_limit_1m = int(BARS_PER_8H_1M * (ENTRY_WINDOW_HOURS_1M / 8.0))
valid_count = len(df_1m.filter(pl.col("dist_avg_high").is_not_nan()))
expected_valid_1m = min(BARS_PER_8H_1M - MIN_REMAINING_BARS_1M, entry_bar_limit_1m)
print(
    f"  Valid 1m bars (with metrics): {valid_count:,} "
    f"({100 * valid_count / max(1, len(df_1m)):.1f}%)"
)
print(
    f"  Expected valid label rows per full 1m batch: {expected_valid_1m} "
    f"(first {ENTRY_WINDOW_HOURS_1M}h only)"
)

print("\n[STEP 4] Computing 4-class + breakfree labels...")
df_labeled_1m = compute_4class_labels(df_1m, BREAKOUT_THRESHOLD, RISK_RATIO)
df_labeled_1m = df_labeled_1m.with_columns(
    [
        pl.when(pl.col("target_4class") < 0)
        .then(pl.lit(-1))
        .when(pl.col("target_4class").is_in([2, 3]) & (pl.col("end_return") >= BREAKFREE_THRESHOLD_1M))
        .then(pl.lit(0))  # UP_ABOVE_BREAKFREE
        .when(pl.col("target_4class").is_in([0, 1]) & (pl.col("end_return") <= -BREAKFREE_THRESHOLD_1M))
        .then(pl.lit(1))  # DOWN_ABOVE_BREAKFREE
        .otherwise(pl.lit(2))  # IN_BETWEEN_BELOW_BREAKFREE
        .alias("target_breakfree")
    ]
)
df_labeled_1m = df_labeled_1m.with_columns(
    [
        pl.when(pl.col("bar_pos_1m") < entry_bar_limit_1m)
        .then(pl.col("target_4class"))
        .otherwise(pl.lit(-1))
        .alias("target_4class"),
        pl.when(pl.col("bar_pos_1m") < entry_bar_limit_1m)
        .then(pl.col("target_breakfree"))
        .otherwise(pl.lit(-1))
        .alias("target_breakfree"),
    ]
)
df_labeled_1m = df_labeled_1m.with_columns(
    pl.col("target_4class")
    .replace_strict({i: name for i, name in CLASS_NAMES.items()}, default="INVALID")
    .alias("target_name")
)

print("\n[STEP 5] Saving per-batch 1m labels...")
output_cols_1m = [
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "batch_id",
    "bar_pos_1m",
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
    "target_4class",
    "target_name",
    "target_breakfree",
]
available_cols_1m = [c for c in output_cols_1m if c in df_labeled_1m.columns]
df_output_1m = df_labeled_1m.filter(pl.col("batch_id").is_in(target_batches_1m)).select(
    available_cols_1m
)

batch_ids_1m = df_output_1m["batch_id"].unique().sort().to_list()
for bid in batch_ids_1m:
    df_output_1m.filter(pl.col("batch_id") == bid).write_parquet(
        tf_labels_dir_1m / f"batch_{bid:04d}.parquet"
    )

valid_labels_1m = len(df_output_1m.filter(pl.col("target_4class") >= 0))
print(f"  ✓ Saved {len(batch_ids_1m):,} batch files to {tf_labels_dir_1m}")
print(f"  ✓ Total rows: {len(df_output_1m):,}")
print(f"  ✓ Valid 4-class labels: {valid_labels_1m:,}")
labels_meta_1m = {
    "updated_at": datetime.now().isoformat(),
    "timeframe": "1m",
    "mode": "incremental_tail"
    if (INCREMENTAL_LABEL_UPDATE_1M and existing_1m_labels)
    else "full",
    "updated_batches": [int(b) for b in batch_ids_1m],
    "updated_batches_count": int(len(batch_ids_1m)),
    "entry_window_hours": ENTRY_WINDOW_HOURS_1M,
    "breakfree_threshold": BREAKFREE_THRESHOLD_1M,
}
with open(tf_labels_dir_1m / "_labels_meta.json", "w") as f:
    json.dump(labels_meta_1m, f, indent=2)
print("  ✓ Saved _labels_meta.json")

print("\n" + "=" * 70)
print("HYBRID 1m LABELING COMPLETE")
print("=" * 70)
print("Approach: 1m entry close + 15m remaining bars for distance metrics")
print(f"Output: {tf_labels_dir_1m}/batch_*.parquet")

del df_1m, df_15m, df_labeled_1m, df_output_1m
gc.collect()

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
from types import SimpleNamespace

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
# For 4-class: optimize directly against target_4class
config = HTFOptimizationConfig(
    project_root=PROJECT_ROOT,
    timeframes=["1m", "5m", "15m"],  # 1h excluded
    targets=["target_4class"],  # 4-class categorical target
    n_early_batches=200,  # Use FIRST 200 batches chronologically for tuning
    n_val_folds=3,  # 3-fold walk-forward validation
    stability_lambda=0.5,  # score = mean(IC) - 0.5 * std(IC)
    recompute=False,  # keep False for fast live updates (reuses previous optimized batches)
    incremental_update=True,  # update only changed/new batches when metadata is available
    max_state_snapshots=32,  # checkpoints for faster resume on append-only data
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
# OUTPUT:
#   - data/htf_with_helpers/{tf}/{target}/batch_XXXX.parquet
#   - optional: data/htf_with_helpers/{tf}/{target}/combined.parquet
# =============================================================================

import json
import sys
import time
from datetime import datetime
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

TIMEFRAMES = ["1m", "5m", "15m"]  # 1h excluded
TARGETS = ["target_4class"]  # 4-class target
INCREMENTAL_SPLIT_BATCHES = True  # skip rewriting unchanged helper batch files
HELPERS = ["ou", "garch", "cusum", "kalman", "egarch"]
INCREMENTAL_HELPERS_SKIP_UNCHANGED = True
WRITE_HELPERS_COMBINED = False  # keep False to avoid OOM on large timeframe joins

results = []

for tf in TIMEFRAMES:
    for target in TARGETS:
        print(f"\n{'─' * 50}")
        print(f"{tf} / {target}")
        print("─" * 50)

        output_dir = PROJECT_ROOT / "data" / "htf_with_helpers" / tf / target
        output_dir.mkdir(parents=True, exist_ok=True)
        combined_path = output_dir / "combined.parquet"
        helpers_meta_path = output_dir / "_helpers_meta.json"

        # Load RAW data from htf_features (before rank-winsorize)
        raw_dir = PROJECT_ROOT / "data" / "htf_features" / tf
        if not raw_dir.exists():
            print("  ⚠️ htf_features directory not found")
            continue

        raw_files = sorted(raw_dir.glob("batch_*.parquet"))
        if not raw_files:
            print("  ⚠️ No batch files in htf_features")
            continue

        # Load optimized files list first so we can skip unchanged runs quickly
        opt_dir = PROJECT_ROOT / "data" / "htf_optimized" / tf / target
        if not opt_dir.exists():
            print(f"  ⚠️ htf_optimized/{tf}/{target} not found")
            continue
        opt_files = sorted(opt_dir.glob("batch_*.parquet"))
        if not opt_files:
            print(f"  ⚠️ No optimized batch files in {opt_dir}")
            continue

        raw_sig = {
            "count": int(len(raw_files)),
            "last_file": raw_files[-1].name,
            "last_mtime_ns": int(raw_files[-1].stat().st_mtime_ns),
        }
        opt_sig = {
            "count": int(len(opt_files)),
            "last_file": opt_files[-1].name,
            "last_mtime_ns": int(opt_files[-1].stat().st_mtime_ns),
        }
        if INCREMENTAL_HELPERS_SKIP_UNCHANGED and helpers_meta_path.exists():
            try:
                with open(helpers_meta_path) as f:
                    prev_meta = json.load(f)
            except Exception:
                prev_meta = {}
            batch_files_exist = any(output_dir.glob("batch_*.parquet"))
            outputs_ready = batch_files_exist or combined_path.exists()
            if (
                prev_meta.get("raw_sig") == raw_sig
                and prev_meta.get("opt_sig") == opt_sig
                and outputs_ready
            ):
                print("  ✓ Inputs unchanged since last helper build, skipping")
                results.append(
                    {
                        "tf": tf,
                        "target": target,
                        "rows": int(prev_meta.get("rows", 0)),
                        "helpers": int(prev_meta.get("helper_cols", 0)),
                        "warmup": int(prev_meta.get("warmup", 0)),
                        "time": 0.0,
                        "skipped": True,
                    }
                )
                continue

        # Load and combine raw data
        print(f"  Loading {len(raw_files)} raw batches...", end=" ", flush=True)
        t0 = time.time()
        raw_combined = (
            pl.scan_parquet(str(raw_dir / "batch_*.parquet"))
            .sort("timestamp")
            .collect()
        )
        print(f"{len(raw_combined):,} rows in {time.time() - t0:.1f}s")

        # Adjust warmup/refit based on timeframe
        if tf == "1m":
            warmup, refit = 20000, 10000
        elif tf == "5m":
            warmup, refit = 10000, 5000
        elif tf == "15m":
            warmup, refit = 5000, 2500
        else:
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

        # Build helper lookup once, then join per optimized batch to avoid OOM.
        helper_pl = pl.from_pandas(helper_df).with_columns(raw_combined["timestamp"])
        helper_cols = [c for c in helper_pl.columns if c.startswith("H_")]
        helper_lookup = (
            helper_pl.select(["timestamp"] + helper_cols)
            .sort("timestamp")
            .unique(subset=["timestamp"], keep="last")
        )

        print(
            f"  Joining helper features into {len(opt_files)} optimized batches...",
            flush=True,
        )
        t0 = time.time()
        rows_joined = 0
        saved_batches = 0
        skipped_batches = 0

        for i, of in enumerate(opt_files, 1):
            batch_id = int(of.stem.split("_")[1])
            opt_batch = pl.read_parquet(of).with_columns(
                pl.lit(batch_id).alias("batch_id")
            )
            enriched_batch = opt_batch.join(helper_lookup, on="timestamp", how="left")

            batch_path = output_dir / f"batch_{batch_id:04d}.parquet"
            if INCREMENTAL_SPLIT_BATCHES and batch_path.exists():
                existing = pl.read_parquet(batch_path, columns=["timestamp"])
                same_rows = len(existing) == len(enriched_batch)
                same_last_ts = (
                    existing["timestamp"].max() == enriched_batch["timestamp"].max()
                )
                if same_rows and same_last_ts:
                    skipped_batches += 1
                    rows_joined += len(enriched_batch)
                    if i % 500 == 0:
                        print(f"    processed {i}/{len(opt_files)} batches...")
                    continue

            enriched_batch.write_parquet(batch_path, compression="zstd")
            saved_batches += 1
            rows_joined += len(enriched_batch)

            if i % 500 == 0:
                print(f"    processed {i}/{len(opt_files)} batches...")

        join_elapsed = time.time() - t0
        print(
            f"  Joined and saved {rows_joined:,} rows in {join_elapsed:.1f}s "
            f"(saved={saved_batches}, skipped={skipped_batches})"
        )

        if WRITE_HELPERS_COMBINED:
            print("  Building optional combined.parquet from per-batch files...")
            pl.concat(
                [
                    pl.read_parquet(batch_file)
                    for batch_file in sorted(output_dir.glob("batch_*.parquet"))
                ]
            ).sort("timestamp").write_parquet(combined_path)
            print(f"  ✓ Saved {combined_path.name}")

        n_helper = len(helper_cols)
        helpers_meta = {
            "updated_at": datetime.now().isoformat(),
            "timeframe": tf,
            "target": target,
            "rows": int(rows_joined),
            "helper_cols": int(n_helper),
            "warmup": int(warmup),
            "refit_every": int(refit),
            "raw_sig": raw_sig,
            "opt_sig": opt_sig,
            "saved_batches": int(saved_batches),
            "skipped_batches": int(skipped_batches),
            "write_helpers_combined": bool(WRITE_HELPERS_COMBINED),
        }
        with open(helpers_meta_path, "w") as f:
            json.dump(helpers_meta, f, indent=2)
        results.append(
            {
                "tf": tf,
                "target": target,
                "rows": rows_joined,
                "helpers": n_helper,
                "warmup": warmup,
                "time": helper_time,
                "skipped": False,
            }
        )
        print(f"  ✓ Saved batch helper files ({n_helper} helper features)")
        print(f"  ✓ Saved {helpers_meta_path.name}")

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
# NOTE:
#   In low-RAM mode (WRITE_HELPERS_COMBINED=False in Cell 11), batch files are
#   already written directly and combined.parquet does not exist.
#   In that case, this cell reports and skips splitting.
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

TIMEFRAMES = ["1m", "5m", "15m"]  # 1h excluded
TARGETS = ["target_4class"]  # 4-class target

# Expected bars per 8h batch (note: actual may vary due to filtering)
BARS_PER_BATCH = {
    "1m": 480,  # 8h * 60min / 1min = 480
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
            existing_batches = sorted(
                (PROJECT_ROOT / "data" / "htf_with_helpers" / tf / target).glob(
                    "batch_*.parquet"
                )
            )
            if existing_batches:
                print(
                    "  ℹ️ combined.parquet not present (low-RAM mode); "
                    "batch files already available, skipping split."
                )
                results.append(
                    {
                        "tf": tf,
                        "target": target,
                        "batches": len(existing_batches),
                        "rows": 0,
                        "time_s": 0.0,
                    }
                )
                continue
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
        skipped_count = 0
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
            if INCREMENTAL_SPLIT_BATCHES and batch_path.exists():
                existing = pl.read_parquet(batch_path, columns=["timestamp"])
                same_rows = len(existing) == len(batch_df)
                same_last_ts = (
                    existing["timestamp"].max() == batch_df["timestamp"].max()
                )
                if same_rows and same_last_ts:
                    skipped_count += 1
                    total_rows += len(batch_df)
                    continue
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
        if INCREMENTAL_SPLIT_BATCHES:
            print(f"  ↪ Skipped unchanged batches: {skipped_count}")

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

# %%
# =============================================================================
# CELL 13: END-TO-END PIPELINE VALIDATION SUITE
# =============================================================================
# Purpose:
#   Validate each stage output (combined/features/labels/optimized/helpers)
#   and fail fast if any structural/data-integrity issue is detected.
# =============================================================================

from pathlib import Path

import polars as pl

PROJECT_ROOT = Path("..").resolve()
DATA_DIR = PROJECT_ROOT / "data"

TIMEFRAMES = ["1m", "5m", "15m"]
BARS_PER_BATCH = {"1m": 480, "5m": 96, "15m": 32}
ENTRY_VALID_ROWS = {"1m": 240, "5m": 48, "15m": 16}  # first 4h policy
EXPECTED_BATCH_COUNT = 5571

HTF_BACKTEST_DIR = DATA_DIR / "htf_backtest"
HTF_FEATURES_DIR = DATA_DIR / "htf_features"
HTF_LABELS_DIR = DATA_DIR / "htf_4class_labels"
HTF_OPTIMIZED_DIR = DATA_DIR / "htf_optimized"
HTF_WITH_HELPERS_DIR = DATA_DIR / "htf_with_helpers"


def _batch_id_from_file(path: Path) -> int:
    return int(path.stem.split("_")[1])


def _is_contiguous(ids: list[int]) -> bool:
    if not ids:
        return False
    return ids == list(range(ids[0], ids[-1] + 1))


def _scan_batch_counts(glob_pattern: str) -> pl.DataFrame:
    return (
        pl.scan_parquet(glob_pattern)
        .group_by("batch_id")
        .agg(pl.len().alias("n"))
        .collect()
        .sort("batch_id")
    )


def _duplicate_ts_count(glob_pattern: str) -> int:
    return int(
        pl.scan_parquet(glob_pattern)
        .group_by(["batch_id", "timestamp"])
        .agg(pl.len().alias("n"))
        .filter(pl.col("n") > 1)
        .select(pl.len())
        .collect()
        .item()
    )


def _null_count(glob_pattern: str, col: str) -> int:
    return int(
        pl.scan_parquet(glob_pattern)
        .filter(pl.col(col).is_null())
        .select(pl.len())
        .collect()
        .item()
    )


def _validate_combined(tf: str) -> tuple[list[dict], dict]:
    rows = []
    path = HTF_BACKTEST_DIR / f"{tf}_HTF_combined.parquet"
    stage = "combined"
    state = {"ok": True, "batch_count": 0}

    if not path.exists():
        rows.append(
            {
                "stage": stage,
                "tf": tf,
                "check": "file_exists",
                "ok": False,
                "detail": f"missing: {path}",
            }
        )
        state["ok"] = False
        return rows, state

    scan = pl.scan_parquet(path)
    schema = set(scan.collect_schema().names())
    required = {
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "period_8h_start",
        "batch_id",
    }
    missing = sorted(required - schema)
    rows.append(
        {
            "stage": stage,
            "tf": tf,
            "check": "required_columns",
            "ok": len(missing) == 0,
            "detail": "missing=" + ",".join(missing) if missing else "ok",
        }
    )
    if missing:
        state["ok"] = False

    counts = (
        scan.group_by("batch_id").agg(pl.len().alias("n")).collect().sort("batch_id")
    )
    ids = counts["batch_id"].to_list()
    state["batch_count"] = len(ids)
    if len(counts) > 0:
        last_batch_id = counts["batch_id"].max()
        bad_n = counts.filter(
            (
                (pl.col("batch_id") != last_batch_id)
                & (pl.col("n") != BARS_PER_BATCH[tf])
            )
            | (
                (pl.col("batch_id") == last_batch_id)
                & ((pl.col("n") <= 0) | (pl.col("n") > BARS_PER_BATCH[tf]))
            )
        )
    else:
        bad_n = counts

    rows.extend(
        [
            {
                "stage": stage,
                "tf": tf,
                "check": "batch_count",
                "ok": len(ids) == EXPECTED_BATCH_COUNT,
                "detail": f"found={len(ids)}, expected={EXPECTED_BATCH_COUNT}",
            },
            {
                "stage": stage,
                "tf": tf,
                "check": "batch_ids_contiguous",
                "ok": _is_contiguous(ids),
                "detail": f"min={ids[0] if ids else None}, max={ids[-1] if ids else None}",
            },
            {
                "stage": stage,
                "tf": tf,
                "check": "rows_per_batch",
                "ok": len(bad_n) == 0,
                "detail": f"bad_batches={len(bad_n)}, allow_last_incomplete=True",
            },
        ]
    )

    dup_ts = _duplicate_ts_count(str(path))
    rows.append(
        {
            "stage": stage,
            "tf": tf,
            "check": "duplicate_timestamp_within_batch",
            "ok": dup_ts == 0,
            "detail": f"duplicates={dup_ts}",
        }
    )
    if dup_ts != 0:
        state["ok"] = False

    for check_col in ["timestamp", "batch_id", "period_8h_start"]:
        n_null = _null_count(str(path), check_col)
        rows.append(
            {
                "stage": stage,
                "tf": tf,
                "check": f"null_{check_col}",
                "ok": n_null == 0,
                "detail": f"nulls={n_null}",
            }
        )
        if n_null != 0:
            state["ok"] = False

    mismatched_period = int(
        scan.filter(pl.col("period_8h_start") != pl.col("timestamp").dt.truncate("8h"))
        .select(pl.len())
        .collect()
        .item()
    )
    rows.append(
        {
            "stage": stage,
            "tf": tf,
            "check": "period_8h_start_alignment",
            "ok": mismatched_period == 0,
            "detail": f"mismatched_rows={mismatched_period}",
        }
    )
    if mismatched_period != 0:
        state["ok"] = False

    state["ok"] = state["ok"] and all(
        r["ok"] for r in rows if r["stage"] == stage and r["tf"] == tf
    )
    return rows, state


def _validate_batch_dir(
    stage: str,
    tf: str,
    path: Path,
    expected_rows_per_batch: int | None,
    required_cols: set[str],
    allow_last_incomplete: bool = False,
) -> tuple[list[dict], int]:
    rows = []
    files = sorted(path.glob("batch_*.parquet"))
    ids = [_batch_id_from_file(f) for f in files]

    if not files:
        rows.append(
            {
                "stage": stage,
                "tf": tf,
                "check": "files_exist",
                "ok": False,
                "detail": f"missing files in {path}",
            }
        )
        return rows, 0

    rows.extend(
        [
            {
                "stage": stage,
                "tf": tf,
                "check": "batch_file_count",
                "ok": len(files) == EXPECTED_BATCH_COUNT,
                "detail": f"found={len(files)}, expected={EXPECTED_BATCH_COUNT}",
            },
            {
                "stage": stage,
                "tf": tf,
                "check": "batch_ids_contiguous",
                "ok": _is_contiguous(ids),
                "detail": f"min={ids[0]}, max={ids[-1]}",
            },
        ]
    )

    glob_pattern = str(path / "batch_*.parquet")
    scan = pl.scan_parquet(glob_pattern)
    schema = set(scan.collect_schema().names())
    missing = sorted(required_cols - schema)
    rows.append(
        {
            "stage": stage,
            "tf": tf,
            "check": "required_columns",
            "ok": len(missing) == 0,
            "detail": "missing=" + ",".join(missing) if missing else "ok",
        }
    )

    counts = _scan_batch_counts(glob_pattern)
    if expected_rows_per_batch is not None:
        if allow_last_incomplete and len(counts) > 0:
            last_batch_id = counts["batch_id"].max()
            bad_n = counts.filter(
                (
                    (pl.col("batch_id") != last_batch_id)
                    & (pl.col("n") != expected_rows_per_batch)
                )
                | (
                    (pl.col("batch_id") == last_batch_id)
                    & ((pl.col("n") <= 0) | (pl.col("n") > expected_rows_per_batch))
                )
            )
        else:
            bad_n = counts.filter(pl.col("n") != expected_rows_per_batch)
        rows.append(
            {
                "stage": stage,
                "tf": tf,
                "check": "rows_per_batch",
                "ok": len(bad_n) == 0,
                "detail": f"bad_batches={len(bad_n)}, allow_last_incomplete={allow_last_incomplete}",
            }
        )

    dup_ts = _duplicate_ts_count(glob_pattern)
    rows.append(
        {
            "stage": stage,
            "tf": tf,
            "check": "duplicate_timestamp_within_batch",
            "ok": dup_ts == 0,
            "detail": f"duplicates={dup_ts}",
        }
    )

    for check_col in ["timestamp", "batch_id"]:
        if check_col in schema:
            n_null = _null_count(glob_pattern, check_col)
            rows.append(
                {
                    "stage": stage,
                    "tf": tf,
                    "check": f"null_{check_col}",
                    "ok": n_null == 0,
                    "detail": f"nulls={n_null}",
                }
            )

    return rows, len(files)


def _validate_labels(tf: str) -> tuple[list[dict], pl.DataFrame]:
    stage = "labels"
    path = HTF_LABELS_DIR / tf
    rows, _ = _validate_batch_dir(
        stage=stage,
        tf=tf,
        path=path,
        expected_rows_per_batch=BARS_PER_BATCH[tf],
        required_cols={"timestamp", "batch_id", "target_4class", "target_breakfree"},
        allow_last_incomplete=True,
    )
    glob_pattern = str(path / "batch_*.parquet")
    scan = pl.scan_parquet(glob_pattern)
    schema = set(scan.collect_schema().names())

    bad_t4 = int(
        scan.filter(~pl.col("target_4class").is_in([-1, 0, 1, 2, 3]))
        .select(pl.len())
        .collect()
        .item()
    )
    bad_bf = int(
        scan.filter(~pl.col("target_breakfree").is_in([-1, 0, 1, 2]))
        .select(pl.len())
        .collect()
        .item()
    )
    rows.extend(
        [
            {
                "stage": stage,
                "tf": tf,
                "check": "target_4class_value_range",
                "ok": bad_t4 == 0,
                "detail": f"invalid_rows={bad_t4}",
            },
            {
                "stage": stage,
                "tf": tf,
                "check": "target_breakfree_value_range",
                "ok": bad_bf == 0,
                "detail": f"invalid_rows={bad_bf}",
            },
        ]
    )

    valid_counts = (
        scan.group_by("batch_id")
        .agg((pl.col("target_4class") >= 0).sum().alias("n_valid_4class"))
        .collect()
        .sort("batch_id")
    )
    if len(valid_counts) > 0:
        last_batch_id = valid_counts["batch_id"].max()
        bad_valid = valid_counts.filter(
            (
                (pl.col("batch_id") != last_batch_id)
                & (pl.col("n_valid_4class") != ENTRY_VALID_ROWS[tf])
            )
            | (
                (pl.col("batch_id") == last_batch_id)
                & (pl.col("n_valid_4class") > ENTRY_VALID_ROWS[tf])
            )
        )
    else:
        bad_valid = valid_counts
    rows.append(
        {
            "stage": stage,
            "tf": tf,
            "check": "target_4class_valid_rows_per_batch",
            "ok": len(bad_valid) == 0,
            "detail": f"bad_batches={len(bad_valid)}, expected_non_last={ENTRY_VALID_ROWS[tf]}, allow_last_incomplete=True",
        }
    )

    # Target-breakfree must be -1 whenever 4-class is invalid
    invalid_pair = int(
        scan.filter((pl.col("target_4class") < 0) & (pl.col("target_breakfree") != -1))
        .select(pl.len())
        .collect()
        .item()
    )
    rows.append(
        {
            "stage": stage,
            "tf": tf,
            "check": "breakfree_invalid_when_4class_invalid",
            "ok": invalid_pair == 0,
            "detail": f"violations={invalid_pair}",
        }
    )

    # Entry-window gating check (labels should be invalid outside first 4h)
    bar_col_map = {"1m": "bar_pos_1m", "5m": "bar_pos_5m", "15m": "bar_pos"}
    bar_col = bar_col_map[tf]
    if bar_col in schema:
        entry_limit = BARS_PER_BATCH[tf] // 2
        late_labels = int(
            scan.filter(
                (pl.col(bar_col) >= entry_limit) & (pl.col("target_4class") >= 0)
            )
            .select(pl.len())
            .collect()
            .item()
        )
        rows.append(
            {
                "stage": stage,
                "tf": tf,
                "check": "entry_window_gating_4class",
                "ok": late_labels == 0,
                "detail": f"late_labeled_rows={late_labels}",
            }
        )

    return rows, valid_counts


def _validate_optimized(
    tf: str, label_valid_counts: pl.DataFrame
) -> tuple[list[dict], pl.DataFrame]:
    stage = "optimized"
    path = HTF_OPTIMIZED_DIR / tf / "target_4class"
    rows, _ = _validate_batch_dir(
        stage=stage,
        tf=tf,
        path=path,
        expected_rows_per_batch=None,
        required_cols={"timestamp", "batch_id"},
    )
    files = sorted(path.glob("batch_*.parquet"))
    if not files:
        return rows, pl.DataFrame({"batch_id": [], "n_opt": []})

    opt_counts = _scan_batch_counts(str(path / "batch_*.parquet")).rename(
        {"n": "n_opt"}
    )
    joined = label_valid_counts.join(
        opt_counts, on="batch_id", how="left"
    ).with_columns(pl.col("n_opt").fill_null(-1))
    bad = joined.filter(pl.col("n_valid_4class") != pl.col("n_opt"))
    rows.append(
        {
            "stage": stage,
            "tf": tf,
            "check": "rows_match_label_valid_counts",
            "ok": len(bad) == 0,
            "detail": f"bad_batches={len(bad)}",
        }
    )
    return rows, opt_counts


def _validate_helpers(tf: str, opt_counts: pl.DataFrame) -> list[dict]:
    stage = "helpers"
    path = HTF_WITH_HELPERS_DIR / tf / "target_4class"
    rows, _ = _validate_batch_dir(
        stage=stage,
        tf=tf,
        path=path,
        expected_rows_per_batch=None,
        required_cols={"timestamp", "batch_id"},
    )
    files = sorted(path.glob("batch_*.parquet"))
    if not files:
        return rows

    schema = set(
        pl.scan_parquet(str(path / "batch_*.parquet")).collect_schema().names()
    )
    n_helper_cols = len([c for c in schema if c.startswith("H_")])
    rows.append(
        {
            "stage": stage,
            "tf": tf,
            "check": "helper_columns_present",
            "ok": n_helper_cols > 0,
            "detail": f"helper_cols={n_helper_cols}",
        }
    )

    helper_counts = _scan_batch_counts(str(path / "batch_*.parquet")).rename(
        {"n": "n_helper"}
    )
    if len(opt_counts) > 0:
        joined = opt_counts.join(helper_counts, on="batch_id", how="left").with_columns(
            pl.col("n_helper").fill_null(-1)
        )
        bad = joined.filter(pl.col("n_opt") != pl.col("n_helper"))
        rows.append(
            {
                "stage": stage,
                "tf": tf,
                "check": "rows_match_optimized_counts",
                "ok": len(bad) == 0,
                "detail": f"bad_batches={len(bad)}",
            }
        )

    return rows


print("=" * 70)
print("CELL 13: END-TO-END PIPELINE VALIDATION")
print("=" * 70)
print(f"Timeframes: {TIMEFRAMES}")
print(f"Expected batches per timeframe: {EXPECTED_BATCH_COUNT}")
print(f"Expected valid label rows per batch: {ENTRY_VALID_ROWS}")
print("=" * 70)

all_rows: list[dict] = []
critical_failures: list[dict] = []

for tf in TIMEFRAMES:
    print(f"\n--- {tf} ---")

    combined_rows, combined_state = _validate_combined(tf)
    all_rows.extend(combined_rows)

    feature_rows, _ = _validate_batch_dir(
        stage="features",
        tf=tf,
        path=HTF_FEATURES_DIR / tf,
        expected_rows_per_batch=BARS_PER_BATCH[tf],
        required_cols={
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "batch_id",
            "period_8h_start",
            "bar_in_batch_norm",
        },
        # Live updates can include a still-forming last batch.
        allow_last_incomplete=True,
    )
    all_rows.extend(feature_rows)

    label_rows, label_valid_counts = _validate_labels(tf)
    all_rows.extend(label_rows)

    opt_rows, opt_counts = _validate_optimized(tf, label_valid_counts)
    all_rows.extend(opt_rows)

    helper_rows = _validate_helpers(tf, opt_counts)
    all_rows.extend(helper_rows)

validation_df = pl.DataFrame(all_rows).with_columns(
    pl.when(pl.col("ok")).then(pl.lit("PASS")).otherwise(pl.lit("FAIL")).alias("status")
)

summary = (
    validation_df.group_by(["stage", "tf"])
    .agg(
        [
            pl.len().alias("checks"),
            pl.col("ok").sum().alias("pass"),
            (pl.len() - pl.col("ok").sum()).alias("fail"),
        ]
    )
    .sort(["stage", "tf"])
)

print("\n" + "=" * 70)
print("VALIDATION SUMMARY")
print("=" * 70)
print(summary)

fails = validation_df.filter(~pl.col("ok"))
if len(fails) > 0:
    print("\n" + "=" * 70)
    print("FAILED CHECKS")
    print("=" * 70)
    print(fails.select(["stage", "tf", "check", "detail"]))
    raise AssertionError(
        f"Pipeline validation failed: {len(fails)} failed checks. "
        "Fix failures before running backtest."
    )

print("\nAll validation checks passed.")

# %% [markdown]
# # Cell 14: Walk-Forward Backtest Design
#
# This cell runs the current **multi-model, multi-timeframe, multi-target walk-forward backtest**.
# Configuration is declarative and centralized in Cell 14.
#
# ## Current flow (one step)
#
# For each selected `model / timeframe / target`:
# 1. Select one aligned prediction batch ID.
# 2. Use only history up to `train_end = pred_batch - 1` for optimization and training.
# 3. Run Optuna on train/val slices.
# 4. Train final model with best trial settings.
# 5. Predict the current batch and store metrics + per-row outputs.
#
# Prediction batch rows are excluded from optimization/training (leakage-safe).
#
# ## Module map (where logic lives)
#
# - `scripts/htf_backtest/runner.py`
#   Top-level model orchestrator (`run_walk_forward_backtest_models`), supports one or multiple models in one run.
#
# - `scripts/htf_backtest/configuration.py`
#   Declarative config utilities:
#   - `merge_backtest_specs(base, overrides)` for robust deep-merge
#   - `build_backtest_maps(model_specs_by_model)` to build runner maps
#
# - `scripts/htf_backtest/lightgbm/runner.py`
#   LightGBM walk-forward step loop, resume behavior, artifact writing, summaries.
#
# - `scripts/htf_backtest/lightgbm/utils.py`
#   Shared utilities: data loading, metrics, save/export helpers, search-space dataclasses.
#
# - `scripts/htf_backtest/lightgbm/tf_1m/optimizer.py`
# - `scripts/htf_backtest/lightgbm/tf_5m/optimizer.py`
# - `scripts/htf_backtest/lightgbm/tf_15m/optimizer.py`
#   Timeframe-specific optimization + final training implementations.
#
# - `scripts/htf_backtest/catboost/runner.py`
#   CatBoost walk-forward step loop, resume behavior, artifact writing, summaries.
#
# - `scripts/htf_backtest/catboost/utils.py`
#   Shared utilities for CatBoost optimizer/search-space + persistence.
#
# - `scripts/htf_backtest/catboost/tf_1m/optimizer.py`
# - `scripts/htf_backtest/catboost/tf_5m/optimizer.py`
# - `scripts/htf_backtest/catboost/tf_15m/optimizer.py`
#   Timeframe-specific CatBoost optimization + final training implementations.
#
# ## Configuration pattern used now
#
# 1. Define stable defaults in `MODEL_BACKTEST_SPECS_BASE`.
# 2. Apply run-specific diffs in `MODEL_SPEC_OVERRIDES`.
# 3. Build final spec:
#    `MODEL_BACKTEST_SPECS = merge_backtest_specs(MODEL_BACKTEST_SPECS_BASE, MODEL_SPEC_OVERRIDES)`
# 4. Resolve runtime maps:
#    `RESOLVED_BACKTEST = build_backtest_maps(MODEL_BACKTEST_SPECS)`
# 5. Run:
#    `run_walk_forward_backtest_models(model_specs_by_model=MODEL_BACKTEST_SPECS, ...)`
#
# This gives full control per **model -> timeframe -> target**, including separate Optuna spaces and metrics.
#
# ## Artifact layout (current canonical)
#
# Root:
# - `data/htf_backtest_results/<run_id>/`
#
# Run-level:
# - `run_config.json`
# - `run_summary.json`
# - `run_model_index.json`
#
# Per-step:
# - `<model>/<timeframe>/<target>/batch_XXXX/`
#   - `study.db`, `optimization.json`, `trials.parquet`, `trials.jsonl`
#   - model file (model-specific):
#     - LightGBM: `model.txt`
#     - CatBoost: `model.cbm`
#   - `class_metrics.parquet`
#   - `prediction_metrics.json`
#   - `predictions.parquet`
#   - `batch_metadata.json`
#
# ## Alignment notes
#
# - 1m/5m/15m use the same prediction batch ID per step.
# - Outputs are isolated by model/timeframe/target so studies and artifacts never mix.
# - Optional multi-model runs are controlled by `ACTIVE_MODELS`.
#
#

# %%
# ============================================================================
# CELL 14: HTF WALK-FORWARD BACKTEST (CATBOOST STAGE-1 ONLY)
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

from scripts.htf_backtest.configuration import (
    build_backtest_maps,
    merge_backtest_specs,
    summarize_backtest_maps,
)
from scripts.htf_backtest.catboost.base_optimizer import run_walk_forward_stage1_grid
from scripts.htf_backtest.catboost.stage1_optimizer import build_stage1_combo_grid

# ==========================================================================
# STAGE-1 CONFIGURATION ONLY
# ==========================================================================
# This cell is intentionally isolated:
# - CatBoost only
# - Stage-1 fold-grid only
# - No standard Optuna profile settings here

STAGE1_MODEL = "catboost"
if STAGE1_MODEL != "catboost":
    raise ValueError("Cell 14 supports only STAGE1_MODEL='catboost'.")

# Resume controls
RESUME = False
RESUME_RUN_ID = "run_2026-02-05_18-06-04"
RESUME_MODE = "continue"  # "continue" or "skip_completed"
ALLOW_OVERRIDE_MISMATCH = False

# Stage-1 run size
STAGE1_N_STEPS = 10

# Targets / classes
CLASS_NAMES_4 = [
    "DOWN_BALANCED",
    "DOWN_EXPANSION",
    "UP_BALANCED",
    "UP_EXPANSION",
]

CLASS_NAMES_BREAKFREE = [
    "UP_ABOVE_BREAKFREE",
    "DOWN_ABOVE_BREAKFREE",
    "IN_BETWEEN_BELOW_BREAKFREE",
]

STAGE1_CB_BASE_PARAMS = {
    "loss_function": "MultiClass",
    "eval_metric": "MultiClass",
    "task_type": "GPU",
    "devices": "0",
    "random_seed": 42,
    "allow_writing_files": False,
    "verbose": False,
    "thread_count": -1,
    "bootstrap_type": "Bernoulli",
}


def _stage1_tf_spec(
    lookback_max: int,
    min_samples_4: int,
    min_samples_breakfree: int,
):
    stage1_folds_min = 2
    stage1_folds_max = 9
    stage1_val_batches_min = 1
    stage1_val_batches_max = 4
    stage1_val_batches_grid = list(range(stage1_val_batches_min, stage1_val_batches_max + 1))
    stage1_train_multiplier_grid = [2, 3, 4, 5, 6, 7, 8, 9]
    stage1_train_batches_grid = sorted(
        {
            val_batches * mult
            for val_batches in stage1_val_batches_grid
            for mult in stage1_train_multiplier_grid
        }
    )
    stage1_fixed_iterations = 300
    stage1_lookback_min = max(
        100,
        max(stage1_train_batches_grid) + stage1_folds_max * stage1_val_batches_max + 2,
    )

    return {
        # `shared_optuna` key name is part of the shared configuration schema.
        # In Stage-1 mode this is used as a plain config container only;
        # the Stage-1 runner does not execute Optuna.
        "shared_optuna": {
            # Stage-1 relevant keys only
            "track_pred_metrics": False,
            "balance_strategy": "none",
            "balance_apply_to": "train",
            "cb_base_params": STAGE1_CB_BASE_PARAMS,
            "window_space": {
                "lookback_min": stage1_lookback_min,
                "lookback_max": lookback_max,
                "window_selection_mode": "stage1_fold_cv",
                "stage1_execution_mode": "fast_grid",
                "stage1_folds_min": stage1_folds_min,
                "stage1_folds_max": stage1_folds_max,
                "stage1_val_batches_min": stage1_val_batches_min,
                "stage1_val_batches_max": stage1_val_batches_max,
                "stage1_val_batches_grid": stage1_val_batches_grid,
                "stage1_train_batches_min": min(stage1_train_batches_grid),
                "stage1_train_batches_max": max(stage1_train_batches_grid),
                "stage1_train_batches_grid": stage1_train_batches_grid,
                "stage1_train_multiplier_grid": stage1_train_multiplier_grid,
                "stage1_stability_lambda": 0.25,
                "stage1_trial_selection_mode": "prediction_batch",
                "embargo_mode": "auto_tf",
            },
            "model_space": {
                "num_boost_round_min": stage1_fixed_iterations,
                "num_boost_round_max": stage1_fixed_iterations,
            },
        },
        "targets": {
            "target_4class": {
                "task_type": "multiclass",
                "n_classes": 4,
                "class_names": CLASS_NAMES_4,
                "feature_source": "target_4class",
                "optuna": {
                    "optuna_metric": "cross_direction_error",
                    "window_space": {"min_samples_per_class": min_samples_4},
                },
            },
            "target_breakfree": {
                "task_type": "multiclass",
                "n_classes": 3,
                "class_names": CLASS_NAMES_BREAKFREE,
                "feature_source": "target_4class",
                "optuna": {
                    "optuna_metric": "macro_f1",
                    "window_space": {"min_samples_per_class": min_samples_breakfree},
                },
            },
        },
    }


STAGE1_MODEL_BACKTEST_SPECS_BASE = {
    "catboost": {
        "timeframes": {
            "1m": _stage1_tf_spec(
                lookback_max=450,
                min_samples_4=150,
                min_samples_breakfree=150,
            ),
            "5m": _stage1_tf_spec(
                lookback_max=450,
                min_samples_4=100,
                min_samples_breakfree=100,
            ),
            "15m": _stage1_tf_spec(
                lookback_max=450,
                min_samples_4=50,
                min_samples_breakfree=50,
            ),
        }
    }
}

# Optional: Stage-1-only spec overrides
STAGE1_SPEC_OVERRIDES = {}

STAGE1_MODEL_BACKTEST_SPECS = merge_backtest_specs(
    STAGE1_MODEL_BACKTEST_SPECS_BASE,
    STAGE1_SPEC_OVERRIDES,
)
STAGE1_RESOLVED_BACKTEST = build_backtest_maps(STAGE1_MODEL_BACKTEST_SPECS)

# Keep explicit maps for readability/debugging
TIMEFRAMES_BY_MODEL = STAGE1_RESOLVED_BACKTEST["timeframes_by_model"]
TARGETS_BY_MODEL = STAGE1_RESOLVED_BACKTEST["targets_by_model"]
N_CLASSES_BY_MODEL = STAGE1_RESOLVED_BACKTEST["n_classes_by_model"]
CLASS_NAMES_BY_MODEL = STAGE1_RESOLVED_BACKTEST["class_names_by_model"]
FEATURE_SOURCE_BY_MODEL = STAGE1_RESOLVED_BACKTEST["feature_source_by_model"]
OPTUNA_OVERRIDES_BY_MODEL = STAGE1_RESOLVED_BACKTEST["optuna_overrides_by_model"]
TARGET_REGISTRY = STAGE1_RESOLVED_BACKTEST["target_registry"]

def _print_stage1_setup_summary() -> None:
    from types import SimpleNamespace as _SimpleNamespace

    print("Resolved stage1 setup:")
    print("Run profile: catboost_stage1")
    catboost_targets = TARGETS_BY_MODEL.get("catboost", {})
    catboost_overrides = OPTUNA_OVERRIDES_BY_MODEL.get("catboost", {})
    for tf in TIMEFRAMES_BY_MODEL.get("catboost", []):
        tf_targets = catboost_targets.get(tf, [])
        for target_col in tf_targets:
            target_overrides = {}
            tf_overrides = catboost_overrides.get(tf, {})
            if isinstance(tf_overrides, dict):
                target_overrides = tf_overrides.get(target_col, {})
            if not isinstance(target_overrides, dict):
                target_overrides = {}
            window_space = target_overrides.get("window_space", {})
            val_grid = list(window_space.get("stage1_val_batches_grid", [1]))
            train_grid = list(window_space.get("stage1_train_batches_grid", []))
            train_mult_grid = list(window_space.get("stage1_train_multiplier_grid", []))
            win_obj = _SimpleNamespace(**window_space)
            combo_count = len(build_stage1_combo_grid(win_obj))
            folds_min = int(window_space.get("stage1_folds_min", 2))
            folds_max = int(window_space.get("stage1_folds_max", folds_min))
            print(f"  {tf}/{target_col}:")
            if train_mult_grid:
                print(
                    "    stage1_grid: "
                    f"folds={folds_min}-{folds_max}, "
                    f"val_batches_grid={val_grid}, "
                    f"train=val*x{train_mult_grid} "
                    f"(fallback_train_batches_grid={train_grid})"
                )
            else:
                print(
                    "    stage1_grid: "
                    f"folds={folds_min}-{folds_max}, "
                    f"val_batches_grid={val_grid}, "
                    f"train_batches_grid={train_grid}"
                )
            print(f"    combinations_per_step={combo_count}")


_print_stage1_setup_summary()

results_stage1 = run_walk_forward_stage1_grid(
    n_steps=STAGE1_N_STEPS,
    timeframes=TIMEFRAMES_BY_MODEL["catboost"],
    run_description="Stage-1 fold-grid dataset generation (CatBoost)",
    verbose=True,
    debug_batches=True,
    run_id=RESUME_RUN_ID if RESUME else None,
    resume=RESUME,
    resume_mode=RESUME_MODE,
    allow_override_mismatch=ALLOW_OVERRIDE_MISMATCH,
    model_name="catboost",
    optuna_overrides_by_model=OPTUNA_OVERRIDES_BY_MODEL,
    targets_by_model=TARGETS_BY_MODEL,
    n_classes_by_model=N_CLASSES_BY_MODEL,
    class_names_by_model=CLASS_NAMES_BY_MODEL,
    feature_source_by_model=FEATURE_SOURCE_BY_MODEL,
    target_registry=TARGET_REGISTRY,
)

# %%
# ============================================================================
# CELL 15: HTF WALK-FORWARD BACKTEST (STANDARD PROFILE)
# ============================================================================

from scripts.htf_backtest.runner import run_walk_forward_backtest_models

# Select models for standard profile run
STANDARD_ACTIVE_MODELS = ["lightgbm", "catboost"]
STANDARD_N_STEPS = 10

# Optional: reuse resume controls from Cell 14
# RESUME, RESUME_RUN_ID, RESUME_MODE, ALLOW_OVERRIDE_MISMATCH

# Shared standard config
STANDARD_COMMON_OPTUNA_FLAGS = {
    "track_pred_metrics": False,
    "balance_strategy": "upsample",
    "balance_apply_to": "train",
}

STANDARD_COMMON_WINDOW_SPACE = {
    "lookback_min": 100,
    "window_selection_mode": "deterministic_solver",
    "train_share_min": 0.70,
    "train_share_max": 0.80,
    "embargo_mode": "auto_tf",
    "solver_step_batches": 1,
    "reference_distribution_mode": "blend_recent_all",
    "recent_ref_batches": 96,
    "recent_ref_weight": 0.70,
    "active_class_min_frac": 0.02,
    "min_val_samples_per_active_class": 5,
}


def _standard_tf_spec(
    lookback_max: int,
    min_samples_4: int,
    min_samples_breakfree: int,
):
    return {
        "shared_optuna": {
            **STANDARD_COMMON_OPTUNA_FLAGS,
            "window_space": {
                **STANDARD_COMMON_WINDOW_SPACE,
                "lookback_max": lookback_max,
            },
        },
        "targets": {
            "target_4class": {
                "task_type": "multiclass",
                "n_classes": 4,
                "class_names": CLASS_NAMES_4,
                "feature_source": "target_4class",
                "optuna": {
                    "optuna_trials": 2000,
                    "optuna_timeout": 360,
                    "optuna_metric": "cross_direction_error",
                    "window_space": {"min_samples_per_class": min_samples_4},
                },
            },
            "target_breakfree": {
                "task_type": "multiclass",
                "n_classes": 3,
                "class_names": CLASS_NAMES_BREAKFREE,
                "feature_source": "target_4class",
                "optuna": {
                    "optuna_trials": 1200,
                    "optuna_timeout": 360,
                    "optuna_metric": "macro_f1",
                    "window_space": {"min_samples_per_class": min_samples_breakfree},
                },
            },
        },
    }


def _standard_tf_spec_catboost(
    lookback_max: int,
    min_samples_4: int,
    min_samples_breakfree: int,
):
    return {
        "shared_optuna": {
            **STANDARD_COMMON_OPTUNA_FLAGS,
            "window_space": {
                **STANDARD_COMMON_WINDOW_SPACE,
                "lookback_max": lookback_max,
            },
        },
        "targets": {
            "target_4class": {
                "task_type": "multiclass",
                "n_classes": 4,
                "class_names": CLASS_NAMES_4,
                "feature_source": "target_4class",
                "optuna": {
                    "optuna_trials": 1200,
                    "optuna_timeout": 360,
                    "optuna_metric": "cross_direction_error",
                    "window_space": {"min_samples_per_class": min_samples_4},
                },
            },
            "target_breakfree": {
                "task_type": "multiclass",
                "n_classes": 3,
                "class_names": CLASS_NAMES_BREAKFREE,
                "feature_source": "target_4class",
                "optuna": {
                    "optuna_trials": 1000,
                    "optuna_timeout": 360,
                    "optuna_metric": "macro_f1",
                    "window_space": {"min_samples_per_class": min_samples_breakfree},
                },
            },
        },
    }


STANDARD_MODEL_BACKTEST_SPECS_BASE = {
    "lightgbm": {
        "timeframes": {
            "1m": _standard_tf_spec(
                lookback_max=450,
                min_samples_4=150,
                min_samples_breakfree=150,
            ),
            "5m": _standard_tf_spec(
                lookback_max=450,
                min_samples_4=100,
                min_samples_breakfree=100,
            ),
            "15m": _standard_tf_spec(
                lookback_max=450,
                min_samples_4=50,
                min_samples_breakfree=50,
            ),
        }
    },
    "catboost": {
        "timeframes": {
            "1m": _standard_tf_spec_catboost(
                lookback_max=450,
                min_samples_4=150,
                min_samples_breakfree=150,
            ),
            "5m": _standard_tf_spec_catboost(
                lookback_max=450,
                min_samples_4=100,
                min_samples_breakfree=100,
            ),
            "15m": _standard_tf_spec_catboost(
                lookback_max=450,
                min_samples_4=50,
                min_samples_breakfree=50,
            ),
        }
    },
}

# Optional: standard-profile-only overrides
STANDARD_SPEC_OVERRIDES = {}

STANDARD_MODEL_BACKTEST_SPECS = merge_backtest_specs(
    STANDARD_MODEL_BACKTEST_SPECS_BASE,
    STANDARD_SPEC_OVERRIDES,
)
STANDARD_RESOLVED_BACKTEST = build_backtest_maps(STANDARD_MODEL_BACKTEST_SPECS)

print("Resolved backtest setup:")
print("Run profile: standard")
print(summarize_backtest_maps(STANDARD_RESOLVED_BACKTEST))

results_standard = run_walk_forward_backtest_models(
    model_names=STANDARD_ACTIVE_MODELS,
    model_specs_by_model=STANDARD_MODEL_BACKTEST_SPECS,
    n_steps=STANDARD_N_STEPS,
    verbose=True,
    debug_batches=True,
    run_id=RESUME_RUN_ID if RESUME else None,
    resume=RESUME,
    resume_mode=RESUME_MODE,
    allow_override_mismatch=ALLOW_OVERRIDE_MISMATCH,
)

# %%
