#!/usr/bin/env python3
"""
Bybit Data Pipeline - Fetch & Aggregate (Production Ready)
===========================================================
Complete data pipeline that:
1. Fetches new data from Bybit API for all configured raw source timeframes
   (currently 1m, 5m, 15m, 1h, 4h, and 1d klines plus derivatives context)
2. Aggregates 4h → 8h compatibility outputs for legacy/supporting workflows
3. Validates raw and aggregate data quality

This is the SINGLE command to keep data up-to-date for the ML pipeline.

Usage:
    python update_data.py                  # Full update (fetch + aggregate)
    python update_data.py --fetch-only     # Only fetch from Bybit
    python update_data.py --aggregate-only # Only aggregate 4h → 8h compatibility data
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

try:
    from .source_config import BYBIT_CATEGORY, BYBIT_SYMBOLS, normalized_symbols
except ImportError:  # pragma: no cover - script execution from fetchingByBit/
    from source_config import (  # type: ignore
        BYBIT_CATEGORY,
        BYBIT_SYMBOLS,
        normalized_symbols,
    )

# ────────────────── CONFIG ──────────────────
BASE_DIR = Path(__file__).parent
CONFIGURED_SYMBOLS = normalized_symbols(BYBIT_SYMBOLS)
CATEGORY = BYBIT_CATEGORY
HTF_REQUIRED_RAW_KLINES = ("1m", "15m")
SUPPORTING_RAW_KLINES = ("5m", "1h", "4h", "1d")
HTF_FEATURE_SOURCE_ORDER = (
    "ohlcv",
    "mark_price",
    "index_price",
    "premium_price",
    "open_interest",
    "long_short_ratio",
    "funding_rate",
)
HTF_FEATURE_SOURCE_LABELS = {
    "ohlcv": "OHLCV",
    "mark_price": "mark price",
    "index_price": "index price",
    "premium_price": "premium price",
    "open_interest": "open interest",
    "long_short_ratio": "long/short ratio",
    "funding_rate": "funding rate",
}
HTF_EXPECTED_FEATURE_SOURCES = {
    "1m": {
        "ohlcv": "1m",
        "mark_price": "1m",
        "index_price": "1m",
        "premium_price": "1m",
        "open_interest": "5m",
        "long_short_ratio": "5m",
        "funding_rate": "8h",
    },
    "15m": {
        "ohlcv": "15m",
        "mark_price": "15m",
        "index_price": "15m",
        "premium_price": "15m",
        "open_interest": "15m",
        "long_short_ratio": "15m",
        "funding_rate": "8h",
    },
}
STATUS_STEP_HOURS = {
    "1m": 1 / 60,
    "5m": 5 / 60,
    "15m": 15 / 60,
    "1h": 1,
    "4h": 4,
    "8h": 8,
    "1d": 24,
}


def run_fetch(
    *,
    dry_run: bool = False,
    start_date: str = "2021-01-01",
    end_date: str = "now",
) -> bool:
    """Run the Bybit data fetcher."""
    print("\n" + "=" * 70)
    print("STEP 1: FETCHING CONFIGURED BYBIT RAW SOURCES")
    print("=" * 70 + "\n")

    if dry_run:
        print(
            "[DRY RUN] Would run: python fetch_bybit_market_data.py "
            f"for {', '.join(CONFIGURED_SYMBOLS)} "
            "(1m, 5m, 15m, 1h, 4h, 1d and configured derivatives sources) "
            f"from {start_date} to {end_date}"
        )
        return True

    fetch_script = BASE_DIR / "fetch_bybit_market_data.py"
    if not fetch_script.exists():
        print(f"ERROR: Fetch script not found: {fetch_script}")
        return False

    try:
        result = subprocess.run(
            [
                sys.executable,
                str(fetch_script),
                "--start-date",
                start_date,
                "--end-date",
                end_date,
            ],
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
    print("STEP 2: AGGREGATING 4H → 8H COMPATIBILITY DATA")
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
    print("STEP 3: VERIFYING RAW AND AGGREGATE DATA QUALITY")
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
        for symbol in CONFIGURED_SYMBOLS:
            print(f"\nSymbol: {symbol}")
            subprocess.run(
                [
                    sys.executable,
                    str(monitor_script),
                    "--symbol",
                    symbol,
                    "--category",
                    CATEGORY,
                ],
                cwd=str(BASE_DIR),
            )

    return True


def _as_utc(dt):
    """Normalize a Polars/Python datetime scalar to UTC."""
    if dt is None:
        return None
    if getattr(dt, "tzinfo", None) is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _summarize_timestamp_files(files: list[Path]):
    """Return row/range summary for parquet files with a timestamp column."""
    import polars as pl

    rows = 0
    first_ts = None
    last_ts = None
    for path in files:
        df = pl.read_parquet(path, columns=["timestamp"])
        if df.height == 0:
            continue
        rows += df.height
        file_min = _as_utc(df["timestamp"].min())
        file_max = _as_utc(df["timestamp"].max())
        if file_min is not None and (first_ts is None or file_min < first_ts):
            first_ts = file_min
        if file_max is not None and (last_ts is None or file_max > last_ts):
            last_ts = file_max
    return {
        "files": len(files),
        "rows": rows,
        "first_ts": first_ts,
        "last_ts": last_ts,
    }


def _staleness_status(staleness_hours: float, step_hours: float) -> str:
    bars_behind = staleness_hours / step_hours if step_hours > 0 else 0.0
    if bars_behind < 2.5:
        return "OK"
    if bars_behind < 12:
        return f"SLIGHTLY STALE ({bars_behind:.1f} bars behind)"
    return f"STALE ({bars_behind:.1f} bars behind)"


def _print_timeseries_status(
    title: str,
    files: list[Path],
    *,
    step_hours: float,
    required: bool,
) -> None:
    print(f"\n{title}:")
    if not files:
        marker = "REQUIRED" if required else "optional/supporting"
        print(f"  Status: NOT FOUND ({marker})")
        return

    summary = _summarize_timestamp_files(files)
    last_ts = summary["last_ts"]
    now = datetime.now(timezone.utc)
    staleness_hours = (
        (now - last_ts).total_seconds() / 3600 if last_ts is not None else float("inf")
    )
    print(f"  Files: {summary['files']:,}")
    print(f"  Rows: {summary['rows']:,}")
    print(f"  Range: {summary['first_ts']} -> {last_ts}")
    print(f"  Staleness: {staleness_hours:.2f} hours")
    print(f"  Status: {_staleness_status(staleness_hours, step_hours)}")


def _kline_files(label: str, symbol: str) -> list[Path]:
    prefix = symbol.lower()
    return sorted(
        (BASE_DIR / f"sorted-{label}-bybit-linear").glob(
            f"{prefix}_linear_sorted_batch_*.parquet"
        )
    )


def _aggregate_8h_files(symbol: str) -> list[Path]:
    return sorted(
        (BASE_DIR / "sorted-8h-bybit-linear").glob(f"{symbol.lower()}_8h.parquet")
    )


def _print_htf_feature_source_plan() -> None:
    """Print the source-resolution plan used by the HTF feature engine."""
    print("\nHTF FEATURE SOURCE RESOLUTION")
    print("-" * 70)
    print(
        "This uses scripts.feature_engineering.compute_htf_features.HTFFeatureEngine "
        "against local files. The current HTF feature engine is BTCUSDT-oriented; "
        "multi-symbol materialization is a later dataset layer."
    )

    project_root = BASE_DIR.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    try:
        from scripts.feature_engineering.compute_htf_features import HTFFeatureEngine
    except Exception as exc:
        print(f"  Status: UNAVAILABLE (could not import HTFFeatureEngine: {exc})")
        return

    try:
        engine = HTFFeatureEngine(data_dir=BASE_DIR, verbose=False)
        engine.discover_available_sources()
    except Exception as exc:
        print(f"  Status: UNAVAILABLE (source discovery failed: {exc})")
        return

    for target_tf in HTF_REQUIRED_RAW_KLINES:
        print(f"\nTarget {target_tf}:")
        plan = engine.get_source_resolution_plan(target_tf)
        expected_sources = HTF_EXPECTED_FEATURE_SOURCES[target_tf]

        for data_type in HTF_FEATURE_SOURCE_ORDER:
            source_plan = plan.get(
                data_type,
                {"source_tf": None, "method": "unavailable"},
            )
            source_tf = source_plan.get("source_tf")
            method = source_plan.get("method") or "unavailable"
            expected_tf = expected_sources[data_type]

            if source_tf is None:
                status = f"MISSING (preferred {expected_tf})"
            elif source_tf == expected_tf:
                status = "OK"
            else:
                status = f"WARN (preferred {expected_tf})"

            label = HTF_FEATURE_SOURCE_LABELS[data_type]
            print(
                f"  {label:<17} "
                f"source={source_tf or 'none':<4} "
                f"method={method:<11} "
                f"status={status}"
            )


def print_status() -> None:
    """Print current data status."""
    print("\n" + "=" * 70)
    print("CURRENT DATA STATUS")
    print("=" * 70)
    print(f"Configured Bybit symbols: {', '.join(CONFIGURED_SYMBOLS)}")
    print("HTF required raw OHLCV inputs: 1m and 15m.")
    print("8h data is a supporting compatibility aggregate built from 4h data.")

    for symbol in CONFIGURED_SYMBOLS:
        print("\n" + "#" * 70)
        print(f"SYMBOL: {symbol}")
        print("#" * 70)

        print("\nHTF REQUIRED RAW KLINES")
        print("-" * 70)
        for label in HTF_REQUIRED_RAW_KLINES:
            _print_timeseries_status(
                f"{label} OHLCV raw source",
                _kline_files(label, symbol),
                step_hours=STATUS_STEP_HOURS[label],
                required=True,
            )

        print("\nSUPPORTING RAW KLINES")
        print("-" * 70)
        for label in SUPPORTING_RAW_KLINES:
            _print_timeseries_status(
                f"{label} OHLCV raw source",
                _kline_files(label, symbol),
                step_hours=STATUS_STEP_HOURS[label],
                required=False,
            )

        print("\n8H COMPATIBILITY AGGREGATE")
        print("-" * 70)
        _print_timeseries_status(
            "8h OHLCV aggregate",
            _aggregate_8h_files(symbol),
            step_hours=STATUS_STEP_HOURS["8h"],
            required=False,
        )

    _print_htf_feature_source_plan()

    print("=" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Bybit Data Pipeline - Fetch & Aggregate (Production Ready)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python update_data.py                  # Full update
  python update_data.py --fetch-only     # Only fetch new data
  python update_data.py --aggregate-only # Only aggregate 4h to 8h compatibility data
  python update_data.py --status         # Show current data status
  python update_data.py --dry-run        # Preview without changes
  python update_data.py --fetch-only --start-date 2024-01-01 --end-date 2024-02-01
        """,
    )
    parser.add_argument(
        "--fetch-only",
        action="store_true",
        help="Only fetch data from Bybit (skip aggregation and verification)",
    )
    parser.add_argument(
        "--aggregate-only",
        action="store_true",
        help="Only aggregate 4h → 8h compatibility data (skip fetching)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Only verify existing data",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show current data status and HTF source-resolution plan, then exit",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be done without making changes",
    )
    parser.add_argument(
        "--force-aggregate",
        action="store_true",
        help="Force rebuild all 8h compatibility data from scratch",
    )
    parser.add_argument("--start-date", default="2021-01-01")
    parser.add_argument("--end-date", default="now")

    args = parser.parse_args()

    start_time = datetime.now(timezone.utc)

    print("\n" + "=" * 70)
    print("BYBIT DATA PIPELINE")
    print("=" * 70)
    print(f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"Base dir: {BASE_DIR}")
    print(f"Date range: {args.start_date} -> {args.end_date}")

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
        fetch_ok = run_fetch(
            dry_run=args.dry_run,
            start_date=args.start_date,
            end_date=args.end_date,
        )
        if not fetch_ok:
            print("\n⚠ Fetch had issues, continuing to aggregation...")

    # Step 2: Aggregate
    if do_aggregate:
        agg_ok = run_aggregate(dry_run=args.dry_run, force=args.force_aggregate)
        if not agg_ok:
            success = False

    # Step 3: Verify only for the full Bybit pipeline. The root multi-asset
    # orchestrator calls this script with --fetch-only, and should not emit 8h
    # compatibility or historical gap reports during the source-fetch step.
    if not args.dry_run and do_aggregate:
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

    if success and not args.dry_run and do_aggregate:
        print("Data is ready for the HTF workflow. Next steps from repo root:")
        print("     cd ..")
        print("  1. Run HTF materialization:")
        print("     python notebooks/htf_pythonscript.py")
        print("  2. Plan Stage-1 walk-forward:")
        print(
            "     python scripts/analysis/htf_stage1_regime_family_walkforward.py "
            "--plan-only"
        )
        print()

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
