#!/usr/bin/env python3
"""
Aggregate 4h Bybit Data → 8h Timeframe (Resumable)
==================================================
Bybit API doesn't provide 8h intervals, so we aggregate from 4h.

Data sources aggregated:
- OHLCV klines (sorted-4h → sorted-8h)
- Open Interest (open-interest-4h → open-interest-8h)
- Mark Price (mark-price-4h → mark-price-8h)
- Index Price (index-price-4h → index-price-8h)
- Premium Price (premium-price-4h → premium-price-8h)
- Long/Short Ratio (long-short-ratio-4h → long-short-ratio-8h)

Note: Funding rate is already 8h from API, no aggregation needed.

Usage:
    python aggregate_to_8h.py              # Aggregate all sources
    python aggregate_to_8h.py --dry-run    # Show what would be done
    python aggregate_to_8h.py --force      # Rebuild all (ignore existing)

Author: RiskYieldMM Project
"""

import argparse
import glob
import logging
from datetime import datetime
from pathlib import Path

import polars as pl

try:
    from .source_config import BYBIT_SYMBOLS, normalized_symbols, symbol_slug
except ImportError:  # pragma: no cover - script execution from fetchingByBit/
    from source_config import BYBIT_SYMBOLS, normalized_symbols, symbol_slug  # type: ignore

# ────────────────── CONFIG ──────────────────
BASE_DIR = Path(__file__).parent
SYMBOLS = tuple(symbol_slug(symbol) for symbol in normalized_symbols(BYBIT_SYMBOLS))
SYMBOL = SYMBOLS[0]

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


# ────────────────── AGGREGATION FUNCTIONS ──────────────────


def load_4h_klines(base_dir: Path, symbol: str = SYMBOL) -> pl.DataFrame:
    """
    Load all 4h OHLCV klines from batch files.

    Returns DataFrame with columns:
        timestamp, open, high, low, close, volume, turnover, interval
    """
    source_dir = base_dir / "sorted-4h-bybit-linear"
    if not source_dir.exists():
        raise FileNotFoundError(f"4h klines directory not found: {source_dir}")

    batch_files = sorted(
        glob.glob(str(source_dir / f"{symbol}_linear_sorted_batch_*.parquet"))
    )
    if not batch_files:
        raise FileNotFoundError(
            f"No 4h batch files found for {symbol} in {source_dir}"
        )

    logger.info(f"Loading {len(batch_files)} 4h kline batch files...")
    dfs = [pl.read_parquet(f) for f in batch_files]
    df = pl.concat(dfs)

    # Ensure sorted by timestamp
    df = df.sort("timestamp")

    logger.info(
        f"Loaded {len(df):,} 4h klines: {df['timestamp'].min()} to {df['timestamp'].max()}"
    )
    return df


def load_4h_data(
    base_dir: Path, source_type: str, symbol: str = SYMBOL
) -> pl.DataFrame | None:
    """
    Load 4h data for non-kline sources (OI, mark, index, premium, L/S ratio).

    source_type: 'open-interest', 'mark-price', 'index-price', 'premium-price', 'long-short-ratio'
    """
    source_dir = base_dir / f"{source_type}-4h-bybit-linear"
    if not source_dir.exists():
        logger.warning(f"4h {source_type} directory not found: {source_dir}")
        return None

    # Find the data file
    file_patterns = [
        f"{symbol}_oi.parquet",
        f"{symbol}_mark.parquet",
        f"{symbol}_index.parquet",
        f"{symbol}_premium.parquet",
        f"{symbol}_ls_ratio.parquet",
    ]

    data_file = None
    for pattern in file_patterns:
        candidate = source_dir / pattern
        if candidate.exists():
            data_file = candidate
            break

    if data_file is None:
        logger.warning(f"No {symbol} data file found in {source_dir}")
        return None

    df = pl.read_parquet(data_file)
    df = df.sort("timestamp")

    logger.info(f"Loaded {len(df):,} 4h {source_type} rows")
    return df


def get_existing_8h_max_timestamp(output_file: Path) -> datetime | None:
    """Get the maximum timestamp from existing 8h file (for resuming)."""
    if not output_file.exists():
        return None

    try:
        df = pl.read_parquet(output_file, columns=["timestamp"])
        if df.height == 0:
            return None
        max_ts = df["timestamp"].max()
        logger.info(f"Existing 8h data ends at: {max_ts}")
        return max_ts
    except Exception as e:
        logger.warning(f"Could not read existing file {output_file}: {e}")
        return None


def aggregate_ohlcv_to_8h(df_4h: pl.DataFrame) -> pl.DataFrame:
    """
    Aggregate 4h OHLCV to 8h bars.

    8h periods: 00:00-08:00, 08:00-16:00, 16:00-00:00 UTC
    Each 8h bar contains exactly 2 4h bars.

    Aggregation rules:
        - open: first value
        - high: max
        - low: min
        - close: last value
        - volume: sum
        - turnover: sum
    """
    # Floor timestamp to 8h boundary
    df = df_4h.with_columns(
        [
            # Calculate 8h period start (floor to nearest 8h)
            (pl.col("timestamp").dt.truncate("8h")).alias("period_start")
        ]
    )

    # Group and aggregate
    df_8h = (
        df.group_by("period_start")
        .agg(
            [
                pl.col("open").first().alias("open"),
                pl.col("high").max().alias("high"),
                pl.col("low").min().alias("low"),
                pl.col("close").last().alias("close"),
                pl.col("volume").sum().alias("volume"),
                pl.col("turnover").sum().alias("turnover"),
                pl.len().alias("bar_count"),  # Should be 2 for complete bars
            ]
        )
        .rename({"period_start": "timestamp"})
    )

    # Add interval label
    df_8h = df_8h.with_columns([pl.lit("8h").alias("interval")])

    # Sort by timestamp
    df_8h = df_8h.sort("timestamp")

    # Report incomplete bars (not exactly 2 4h bars)
    incomplete = df_8h.filter(pl.col("bar_count") != 2)
    if incomplete.height > 0:
        logger.warning(
            f"Found {incomplete.height} incomplete 8h bars (missing 4h data)"
        )

    # Drop bar_count column
    df_8h = df_8h.drop("bar_count")

    return df_8h


def aggregate_ohlc_to_8h(df_4h: pl.DataFrame) -> pl.DataFrame:
    """
    Aggregate 4h OHLC data (mark/index/premium prices) to 8h.

    Same logic as OHLCV but without volume/turnover.
    """
    df = df_4h.with_columns(
        [(pl.col("timestamp").dt.truncate("8h")).alias("period_start")]
    )

    df_8h = (
        df.group_by("period_start")
        .agg(
            [
                pl.col("open").first().alias("open"),
                pl.col("high").max().alias("high"),
                pl.col("low").min().alias("low"),
                pl.col("close").last().alias("close"),
            ]
        )
        .rename({"period_start": "timestamp"})
    )

    # Preserve timestamp_ms if exists
    if "timestamp_ms" in df_4h.columns:
        # Use the first timestamp_ms in each 8h period
        ts_ms = (
            df.group_by("period_start")
            .agg(
                [
                    pl.col("timestamp_ms").first().alias("timestamp_ms"),
                ]
            )
            .rename({"period_start": "timestamp"})
        )
        df_8h = df_8h.join(ts_ms, on="timestamp", how="left")

    return df_8h.sort("timestamp")


def aggregate_oi_to_8h(df_4h: pl.DataFrame) -> pl.DataFrame:
    """
    Aggregate 4h Open Interest to 8h.

    OI is a snapshot value, so we take the LAST value in each 8h period
    (represents the state at the end of the period).
    """
    df = df_4h.with_columns(
        [(pl.col("timestamp").dt.truncate("8h")).alias("period_start")]
    )

    df_8h = (
        df.group_by("period_start")
        .agg(
            [
                pl.col("openInterest").last().alias("openInterest"),
            ]
        )
        .rename({"period_start": "timestamp"})
    )

    # Preserve timestamp_ms if exists
    if "timestamp_ms" in df_4h.columns:
        ts_ms = (
            df.group_by("period_start")
            .agg(
                [
                    pl.col("timestamp_ms").last().alias("timestamp_ms"),
                ]
            )
            .rename({"period_start": "timestamp"})
        )
        df_8h = df_8h.join(ts_ms, on="timestamp", how="left")

    return df_8h.sort("timestamp")


def aggregate_ls_ratio_to_8h(df_4h: pl.DataFrame) -> pl.DataFrame:
    """
    Aggregate 4h Long/Short Ratio to 8h.

    L/S ratio represents account positioning, so we AVERAGE the values
    (mean of the two 4h periods gives representative 8h sentiment).
    """
    df = df_4h.with_columns(
        [(pl.col("timestamp").dt.truncate("8h")).alias("period_start")]
    )

    df_8h = (
        df.group_by("period_start")
        .agg(
            [
                pl.col("buyRatio").mean().alias("buyRatio"),
                pl.col("sellRatio").mean().alias("sellRatio"),
            ]
        )
        .rename({"period_start": "timestamp"})
    )

    # Preserve timestamp_ms if exists
    if "timestamp_ms" in df_4h.columns:
        ts_ms = (
            df.group_by("period_start")
            .agg(
                [
                    pl.col("timestamp_ms").first().alias("timestamp_ms"),
                ]
            )
            .rename({"period_start": "timestamp"})
        )
        df_8h = df_8h.join(ts_ms, on="timestamp", how="left")

    return df_8h.sort("timestamp")


# ────────────────── MAIN AGGREGATION ──────────────────


def aggregate_klines(
    base_dir: Path,
    symbol: str = SYMBOL,
    force: bool = False,
    dry_run: bool = False,
) -> dict:
    """Aggregate 4h OHLCV klines to 8h."""
    output_dir = base_dir / "sorted-8h-bybit-linear"
    output_file = output_dir / f"{symbol}_8h.parquet"

    result = {
        "symbol": symbol,
        "source": "klines",
        "status": "skipped",
        "new_rows": 0,
    }

    # Load 4h data
    try:
        df_4h = load_4h_klines(base_dir, symbol)
    except FileNotFoundError as e:
        logger.error(str(e))
        result["status"] = "error"
        return result

    # Check resume point
    resume_from = None if force else get_existing_8h_max_timestamp(output_file)

    if resume_from is not None:
        # Filter to only new data (after last 8h timestamp + 8 hours)
        df_4h = df_4h.filter(pl.col("timestamp") > resume_from)
        if df_4h.height == 0:
            logger.info("OHLCV klines: Up to date, no new 4h data")
            result["status"] = "up-to-date"
            return result
        logger.info(f"Processing {df_4h.height} new 4h klines since {resume_from}")

    if dry_run:
        logger.info(
            f"[DRY RUN] Would aggregate {df_4h.height} 4h klines → ~{df_4h.height // 2} 8h bars"
        )
        result["status"] = "dry-run"
        result["new_rows"] = df_4h.height // 2
        return result

    # Aggregate
    df_8h_new = aggregate_ohlcv_to_8h(df_4h)
    logger.info(f"Aggregated {df_4h.height} 4h bars → {df_8h_new.height} 8h bars")

    # Merge with existing or create new
    output_dir.mkdir(parents=True, exist_ok=True)

    if resume_from is not None and output_file.exists():
        # Append to existing
        df_existing = pl.read_parquet(output_file)
        df_combined = pl.concat([df_existing, df_8h_new])
        df_combined = df_combined.unique(subset=["timestamp"], keep="last")
        df_combined = df_combined.sort("timestamp")
        df_combined.write_parquet(output_file)
        logger.info(
            f"✓ Updated {output_file.name}: {df_existing.height} → {df_combined.height} rows"
        )
        result["new_rows"] = df_combined.height - df_existing.height
    else:
        # Create new file
        df_8h_new.write_parquet(output_file)
        logger.info(f"✓ Created {output_file.name}: {df_8h_new.height} rows")
        result["new_rows"] = df_8h_new.height

    result["status"] = "success"
    return result


def aggregate_generic(
    base_dir: Path,
    symbol: str,
    source_type: str,
    aggregator_func,
    output_filename: str,
    force: bool = False,
    dry_run: bool = False,
) -> dict:
    """
    Generic aggregation for non-kline sources.

    source_type: 'open-interest', 'mark-price', 'index-price', 'premium-price', 'long-short-ratio'
    aggregator_func: Function to aggregate DataFrame
    output_filename: e.g., 'btcusdt_open_interest_8h.parquet'
    """
    output_dir = base_dir / f"{source_type}-8h-bybit-linear"
    output_file = output_dir / output_filename

    result = {
        "symbol": symbol,
        "source": source_type,
        "status": "skipped",
        "new_rows": 0,
    }

    # Load 4h data
    df_4h = load_4h_data(base_dir, source_type, symbol)
    if df_4h is None:
        logger.warning(f"{source_type}: No 4h data found")
        result["status"] = "no-source"
        return result

    # Check resume point
    resume_from = None if force else get_existing_8h_max_timestamp(output_file)

    if resume_from is not None:
        df_4h = df_4h.filter(pl.col("timestamp") > resume_from)
        if df_4h.height == 0:
            logger.info(f"{source_type}: Up to date, no new 4h data")
            result["status"] = "up-to-date"
            return result
        logger.info(
            f"Processing {df_4h.height} new 4h {source_type} rows since {resume_from}"
        )

    if dry_run:
        logger.info(
            f"[DRY RUN] Would aggregate {df_4h.height} 4h {source_type} → ~{df_4h.height // 2} 8h rows"
        )
        result["status"] = "dry-run"
        result["new_rows"] = df_4h.height // 2
        return result

    # Aggregate
    df_8h_new = aggregator_func(df_4h)
    logger.info(f"Aggregated {df_4h.height} 4h → {df_8h_new.height} 8h {source_type}")

    # Merge with existing or create new
    output_dir.mkdir(parents=True, exist_ok=True)

    if resume_from is not None and output_file.exists():
        df_existing = pl.read_parquet(output_file)

        # Ensure schema consistency before concatenation
        # Match new data columns to existing file schema (drop extra columns in new data)
        existing_cols = set(df_existing.columns)
        new_cols = set(df_8h_new.columns)

        # If existing file has fewer columns, only keep those columns in new data
        if existing_cols != new_cols:
            cols_to_drop = new_cols - existing_cols
            if cols_to_drop:
                logger.info(f"Dropping extra columns from new data: {cols_to_drop}")
                df_8h_new = df_8h_new.drop(list(cols_to_drop))
            # If existing file has more columns than new data (shouldn't happen), add them as null
            cols_to_add = existing_cols - new_cols
            if cols_to_add:
                for col in cols_to_add:
                    col_type = df_existing.schema[col]
                    df_8h_new = df_8h_new.with_columns(
                        pl.lit(None).cast(col_type).alias(col)
                    )

        # Ensure column order matches existing file
        df_8h_new = df_8h_new.select(df_existing.columns)

        df_combined = pl.concat([df_existing, df_8h_new])
        df_combined = df_combined.unique(subset=["timestamp"], keep="last")
        df_combined = df_combined.sort("timestamp")
        df_combined.write_parquet(output_file)
        logger.info(
            f"✓ Updated {output_file.name}: {df_existing.height} → {df_combined.height} rows"
        )
        result["new_rows"] = df_combined.height - df_existing.height
    else:
        # For new files, also drop timestamp_ms to keep schema consistent
        if "timestamp_ms" in df_8h_new.columns:
            df_8h_new = df_8h_new.drop("timestamp_ms")
        df_8h_new.write_parquet(output_file)
        logger.info(f"✓ Created {output_file.name}: {df_8h_new.height} rows")
        result["new_rows"] = df_8h_new.height

    result["status"] = "success"
    return result


def aggregate_all(
    base_dir: Path, force: bool = False, dry_run: bool = False
) -> list[dict]:
    """Aggregate all 4h sources to 8h."""
    results = []

    print("\n" + "=" * 60)
    print("AGGREGATING 4H → 8H DATA")
    print("=" * 60 + "\n")

    for symbol in SYMBOLS:
        print("\n" + "#" * 60)
        print(f"SYMBOL: {symbol.upper()}")
        print("#" * 60)

        # 1. OHLCV Klines
        print("─" * 40)
        print("1. OHLCV Klines")
        print("─" * 40)
        results.append(aggregate_klines(base_dir, symbol, force, dry_run))

        # 2. Open Interest
        print("\n" + "─" * 40)
        print("2. Open Interest")
        print("─" * 40)
        results.append(
            aggregate_generic(
                base_dir,
                symbol,
                "open-interest",
                aggregate_oi_to_8h,
                f"{symbol}_open_interest_8h.parquet",
                force,
                dry_run,
            )
        )

        # 3. Mark Price
        print("\n" + "─" * 40)
        print("3. Mark Price")
        print("─" * 40)
        results.append(
            aggregate_generic(
                base_dir,
                symbol,
                "mark-price",
                aggregate_ohlc_to_8h,
                f"{symbol}_mark_price_8h.parquet",
                force,
                dry_run,
            )
        )

        # 4. Index Price
        print("\n" + "─" * 40)
        print("4. Index Price")
        print("─" * 40)
        results.append(
            aggregate_generic(
                base_dir,
                symbol,
                "index-price",
                aggregate_ohlc_to_8h,
                f"{symbol}_index_price_8h.parquet",
                force,
                dry_run,
            )
        )

        # 5. Premium Price
        print("\n" + "─" * 40)
        print("5. Premium Price")
        print("─" * 40)
        results.append(
            aggregate_generic(
                base_dir,
                symbol,
                "premium-price",
                aggregate_ohlc_to_8h,
                f"{symbol}_premium_price_8h.parquet",
                force,
                dry_run,
            )
        )

        # 6. Long/Short Ratio
        print("\n" + "─" * 40)
        print("6. Long/Short Ratio")
        print("─" * 40)
        results.append(
            aggregate_generic(
                base_dir,
                symbol,
                "long-short-ratio",
                aggregate_ls_ratio_to_8h,
                f"{symbol}_ls_ratio.parquet",
                force,
                dry_run,
            )
        )

    return results


def print_summary(results: list[dict]) -> None:
    """Print aggregation summary."""
    print("\n" + "=" * 60)
    print("AGGREGATION SUMMARY")
    print("=" * 60)

    for r in results:
        status_icon = {
            "success": "✓",
            "up-to-date": "○",
            "dry-run": "◎",
            "no-source": "⚠",
            "error": "✗",
            "skipped": "─",
        }.get(r["status"], "?")

        print(
            f"  {status_icon} {r.get('symbol', SYMBOL):8} "
            f"{r['source']:20} → {r['status']:12} (+{r['new_rows']} rows)"
        )

    print("=" * 60 + "\n")


def verify_8h_data(base_dir: Path) -> None:
    """Quick verification of 8h data files."""
    print("\n" + "=" * 60)
    print("8H DATA VERIFICATION")
    print("=" * 60)

    for symbol in SYMBOLS:
        print(f"\n{symbol.upper()}:")
        files_to_check = [
            ("sorted-8h-bybit-linear", f"{symbol}_8h.parquet"),
            ("open-interest-8h-bybit-linear", f"{symbol}_open_interest_8h.parquet"),
            ("mark-price-8h-bybit-linear", f"{symbol}_mark_price_8h.parquet"),
            ("index-price-8h-bybit-linear", f"{symbol}_index_price_8h.parquet"),
            ("premium-price-8h-bybit-linear", f"{symbol}_premium_price_8h.parquet"),
            ("long-short-ratio-8h-bybit-linear", f"{symbol}_ls_ratio.parquet"),
            ("funding-rate-bybit-linear", f"{symbol}_funding_rate.parquet"),
        ]

        for folder, filename in files_to_check:
            filepath = base_dir / folder / filename
            if filepath.exists():
                df = pl.read_parquet(filepath)
                ts_col = "timestamp" if "timestamp" in df.columns else df.columns[0]
                print(f"  ✓ {folder}/{filename}")
                print(f"      Rows: {len(df):,}")
                print(f"      Range: {df[ts_col].min()} → {df[ts_col].max()}")
            else:
                print(f"  ✗ {folder}/{filename} NOT FOUND")

    print("=" * 60 + "\n")


# ────────────────── MAIN ──────────────────


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Aggregate 4h Bybit data to 8h timeframe (resumable)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild all 8h data from scratch (ignore existing)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Only verify existing 8h data files",
    )
    parser.add_argument(
        "--base-dir",
        type=str,
        default=str(BASE_DIR),
        help=f"Base directory for data files (default: {BASE_DIR})",
    )

    args = parser.parse_args()
    base_dir = Path(args.base_dir)

    print(f"\nBase directory: {base_dir}")
    print(
        f"Mode: {'DRY RUN' if args.dry_run else 'FORCE REBUILD' if args.force else 'INCREMENTAL'}"
    )

    if args.verify:
        verify_8h_data(base_dir)
    else:
        results = aggregate_all(base_dir, force=args.force, dry_run=args.dry_run)
        print_summary(results)

        # Always verify after aggregation
        if not args.dry_run:
            verify_8h_data(base_dir)

        print("Next steps:")
        print("  1. Run data quality check:")
        for symbol in SYMBOLS:
            print(
                f"     python data_quality_monitor.py --base-dir {base_dir} "
                f"--symbol {symbol.upper()}"
            )
        print("  2. Prepare merged dataset:")
        print("     python -m scripts.feature_engineering.prepare_dataset")
        print()
