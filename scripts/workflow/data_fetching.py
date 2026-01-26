"""
Data fetching and aggregation for the RiskYieldMM ML pipeline.

Step 0: Fetch latest data from Bybit API and aggregate 4h → 8h.
"""

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import polars as pl


def check_data_freshness(
    ohlcv_8h_path: Path,
    stale_threshold_hours: int = 16,
) -> tuple[bool, float, datetime | None]:
    """
    Check if 8h OHLCV data is fresh.

    Args:
        ohlcv_8h_path: Path to the 8h OHLCV parquet file
        stale_threshold_hours: Hours behind before data is considered stale

    Returns:
        Tuple of (is_fresh, hours_behind, last_timestamp)
    """
    if not ohlcv_8h_path.exists():
        return False, 999.0, None

    last_ts = pl.read_parquet(ohlcv_8h_path).select("timestamp").max().item()
    now = datetime.now(timezone.utc)
    hours_behind = (now - last_ts.replace(tzinfo=timezone.utc)).total_seconds() / 3600

    is_fresh = hours_behind <= stale_threshold_hours
    return is_fresh, hours_behind, last_ts


def run_step0_fetch_and_aggregate(
    project_root: Path,
    auto_fetch: bool = True,
    stale_threshold_hours: int = 16,
    verbose: bool = True,
) -> bool:
    """
    Step 0: Fetch & aggregate data from Bybit.

    Args:
        project_root: Path to the project root directory
        auto_fetch: Whether to automatically fetch if data is stale
        stale_threshold_hours: Hours behind before data is considered stale
        verbose: Whether to print status messages

    Returns:
        True if data is fresh (either already current or successfully updated)
    """
    if verbose:
        print("=" * 70)
        print("STEP 0: DATA FETCHING & AGGREGATION")
        print("=" * 70)

    fetch_dir = project_root / "fetchingByBit"
    update_script = fetch_dir / "update_data.py"
    ohlcv_8h = fetch_dir / "sorted-8h-bybit-linear" / "btcusdt_8h.parquet"

    # Check current data status
    is_fresh, hours_behind, last_ts = check_data_freshness(
        ohlcv_8h, stale_threshold_hours
    )

    if last_ts is not None:
        if verbose:
            print(f"\nCurrent 8h data ends: {last_ts}")
            print(f"Hours behind UTC now: {hours_behind:.1f}h")
    else:
        if verbose:
            print("\n⚠️ No 8h OHLCV data found - must fetch first!")

    # Decision: fetch or skip
    if is_fresh:
        if verbose:
            print(f"\n✓ Data is FRESH (within {stale_threshold_hours}h threshold)")
            print("  Skipping fetch - using existing data")
        return True

    if not auto_fetch:
        if verbose:
            print("\n⚠️ Data is STALE but auto_fetch=False")
            print("  To update manually: cd fetchingByBit && python update_data.py")
        return hours_behind < 999  # Return True if we have some data

    # Run the update
    if verbose:
        print(f"\n⚠️ Data is STALE ({hours_behind:.0f}h behind) - fetching...")
        print("-" * 70)

    if not update_script.exists():
        if verbose:
            print(f"ERROR: Update script not found: {update_script}")
        return False

    result = subprocess.run(
        [sys.executable, str(update_script)],
        cwd=str(fetch_dir),
    )

    if result.returncode == 0:
        # Verify new data
        if ohlcv_8h.exists():
            new_ts = pl.read_parquet(ohlcv_8h).select("timestamp").max().item()
            if verbose:
                print("-" * 70)
                print("✓ Data updated successfully")
                print(f"  New data ends: {new_ts}")
            return True
        else:
            if verbose:
                print("✗ Update ran but no data file found")
            return False
    else:
        if verbose:
            print(f"✗ Data update failed (exit code: {result.returncode})")
        return False


def get_raw_8h_info(project_root: Path) -> dict:
    """
    Get information about the raw 8h data file.

    Returns:
        Dict with row_count, last_timestamp, file_path
    """
    raw_8h_file = (
        project_root / "fetchingByBit" / "sorted-8h-bybit-linear" / "btcusdt_8h.parquet"
    )

    if not raw_8h_file.exists():
        return {
            "exists": False,
            "row_count": 0,
            "last_timestamp": None,
            "file_path": raw_8h_file,
        }

    raw_df = pl.read_parquet(raw_8h_file)
    return {
        "exists": True,
        "row_count": len(raw_df),
        "last_timestamp": str(raw_df.select("timestamp").max().item()),
        "file_path": raw_8h_file,
    }
