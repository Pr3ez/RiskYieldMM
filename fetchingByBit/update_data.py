#!/usr/bin/env python3
"""
Bybit Data Pipeline - Fetch & Aggregate (Production Ready)
===========================================================
Complete data pipeline that:
1. Fetches new data from Bybit API (resumable from last point)
2. Aggregates 4h → 8h timeframe for all sources
3. Validates data quality

This is the SINGLE command to keep data up-to-date for the ML pipeline.

Usage:
    python update_data.py                  # Full update (fetch + aggregate)
    python update_data.py --fetch-only     # Only fetch from Bybit
    python update_data.py --aggregate-only # Only aggregate 4h → 8h
    python update_data.py --verify         # Only verify existing data
    python update_data.py --dry-run        # Preview what would be done

Production workflow:
    # Daily cron job at 1 AM UTC
    0 1 * * * cd /path/to/fetchingByBit && python update_data.py >> update.log 2>&1

Author: RiskYieldMM Project
"""

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# ────────────────── CONFIG ──────────────────
BASE_DIR = Path(__file__).parent


def run_fetch(dry_run: bool = False) -> bool:
    """Run the Bybit data fetcher."""
    print("\n" + "=" * 70)
    print("STEP 1: FETCHING NEW DATA FROM BYBIT")
    print("=" * 70 + "\n")

    if dry_run:
        print("[DRY RUN] Would run: python fetch_bybit_market_data.py")
        return True

    fetch_script = BASE_DIR / "fetch_bybit_market_data.py"
    if not fetch_script.exists():
        print(f"ERROR: Fetch script not found: {fetch_script}")
        return False

    try:
        result = subprocess.run(
            [sys.executable, str(fetch_script)],
            cwd=str(BASE_DIR),
            check=False,  # Don't raise on non-zero exit
        )
        return result.returncode == 0
    except Exception as e:
        print(f"ERROR running fetch: {e}")
        return False


def run_aggregate(dry_run: bool = False, force: bool = False) -> bool:
    """Run the 4h → 8h aggregation."""
    print("\n" + "=" * 70)
    print("STEP 2: AGGREGATING 4H → 8H DATA")
    print("=" * 70 + "\n")

    aggregate_script = BASE_DIR / "aggregate_to_8h.py"
    if not aggregate_script.exists():
        print(f"ERROR: Aggregate script not found: {aggregate_script}")
        return False

    cmd = [sys.executable, str(aggregate_script)]
    if dry_run:
        cmd.append("--dry-run")
    if force:
        cmd.append("--force")

    try:
        result = subprocess.run(
            cmd,
            cwd=str(BASE_DIR),
            check=False,
        )
        return result.returncode == 0
    except Exception as e:
        print(f"ERROR running aggregate: {e}")
        return False


def run_verify() -> bool:
    """Run data verification."""
    print("\n" + "=" * 70)
    print("STEP 3: VERIFYING DATA QUALITY")
    print("=" * 70 + "\n")

    aggregate_script = BASE_DIR / "aggregate_to_8h.py"
    if aggregate_script.exists():
        subprocess.run(
            [sys.executable, str(aggregate_script), "--verify"],
            cwd=str(BASE_DIR),
        )

    # Also run quality monitor if exists
    monitor_script = BASE_DIR / "data_quality_monitor.py"
    if monitor_script.exists():
        print("\n" + "-" * 40)
        print("Data Quality Monitor")
        print("-" * 40)
        subprocess.run(
            [sys.executable, str(monitor_script)],
            cwd=str(BASE_DIR),
        )

    return True


def print_status() -> None:
    """Print current data status."""
    import polars as pl

    print("\n" + "=" * 70)
    print("CURRENT DATA STATUS")
    print("=" * 70)

    # Check 8h OHLCV (main dataset)
    ohlcv_8h = BASE_DIR / "sorted-8h-bybit-linear" / "btcusdt_8h.parquet"
    if ohlcv_8h.exists():
        df = pl.read_parquet(ohlcv_8h)
        last_ts = df["timestamp"].max()
        now = datetime.now(timezone.utc)

        # Calculate staleness
        staleness_hours = (
            now - last_ts.replace(tzinfo=timezone.utc)
        ).total_seconds() / 3600

        print("\n8h OHLCV Data:")
        print(f"  Last bar: {last_ts}")
        print(f"  Rows: {len(df):,}")
        print(f"  Staleness: {staleness_hours:.1f} hours")

        if staleness_hours < 9:
            print("  Status: ✓ UP TO DATE")
        elif staleness_hours < 24:
            print("  Status: ⚠ SLIGHTLY STALE (1+ bars behind)")
        else:
            print(f"  Status: ✗ STALE ({int(staleness_hours // 8)} bars behind)")
    else:
        print("\n8h OHLCV: NOT FOUND")

    # Check 4h OHLCV
    ohlcv_4h_dir = BASE_DIR / "sorted-4h-bybit-linear"
    if ohlcv_4h_dir.exists():
        import glob

        batch_files = glob.glob(str(ohlcv_4h_dir / "*.parquet"))
        if batch_files:
            dfs = [pl.read_parquet(f, columns=["timestamp"]) for f in batch_files]
            df_4h = pl.concat(dfs)
            print("\n4h OHLCV Data:")
            print(f"  Last bar: {df_4h['timestamp'].max()}")
            print(f"  Rows: {len(df_4h):,}")

    print("=" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Bybit Data Pipeline - Fetch & Aggregate (Production Ready)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python update_data.py                  # Full update
  python update_data.py --fetch-only     # Only fetch new data
  python update_data.py --aggregate-only # Only aggregate to 8h
  python update_data.py --status         # Show current data status
  python update_data.py --dry-run        # Preview without changes
        """,
    )
    parser.add_argument(
        "--fetch-only",
        action="store_true",
        help="Only fetch data from Bybit (skip aggregation)",
    )
    parser.add_argument(
        "--aggregate-only",
        action="store_true",
        help="Only aggregate 4h → 8h (skip fetching)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Only verify existing data",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show current data status and exit",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be done without making changes",
    )
    parser.add_argument(
        "--force-aggregate",
        action="store_true",
        help="Force rebuild all 8h data from scratch",
    )

    args = parser.parse_args()

    start_time = datetime.now(timezone.utc)

    print("\n" + "=" * 70)
    print("BYBIT DATA PIPELINE")
    print("=" * 70)
    print(f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"Base dir: {BASE_DIR}")

    if args.status:
        print_status()
        return 0

    if args.verify:
        run_verify()
        return 0

    # Determine what to run
    do_fetch = not args.aggregate_only
    do_aggregate = not args.fetch_only

    success = True

    # Step 1: Fetch
    if do_fetch:
        fetch_ok = run_fetch(dry_run=args.dry_run)
        if not fetch_ok:
            print("\n⚠ Fetch had issues, continuing to aggregation...")

    # Step 2: Aggregate
    if do_aggregate:
        agg_ok = run_aggregate(dry_run=args.dry_run, force=args.force_aggregate)
        if not agg_ok:
            success = False

    # Step 3: Verify (unless dry-run)
    if not args.dry_run:
        run_verify()

    # Summary
    end_time = datetime.now(timezone.utc)
    duration = (end_time - start_time).total_seconds()

    print("\n" + "=" * 70)
    print("PIPELINE COMPLETE")
    print("=" * 70)
    print(f"Duration: {duration:.1f} seconds")
    print(f"Status: {'✓ SUCCESS' if success else '✗ ERRORS OCCURRED'}")
    print("=" * 70 + "\n")

    if success and not args.dry_run:
        print("Data is ready. Next steps:")
        print("  1. Run feature engineering:")
        print("     python -m scripts.feature_engineering.prepare_dataset")
        print("  2. Or run full workflow:")
        print("     # In notebooks/main_wf.py")
        print()

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
