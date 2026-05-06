#!/usr/bin/env python3
"""Aggregate normalized multi-asset OHLCV parquet intervals locally."""

from __future__ import annotations

import argparse
from pathlib import Path

import polars as pl

try:
    from .asset_config import INTERVAL_MS
    from .fetch_twelve_data import (
        OHLCV_COLUMNS,
        TIMESTAMP_DTYPE,
        append_ohlcv_batches,
        output_dir_for_interval,
    )
except ImportError:  # pragma: no cover - script execution from fetchingMultiAsset/
    from asset_config import INTERVAL_MS  # type: ignore
    from fetch_twelve_data import (  # type: ignore
        OHLCV_COLUMNS,
        TIMESTAMP_DTYPE,
        append_ohlcv_batches,
        output_dir_for_interval,
    )


BASE_DIR = Path(__file__).resolve().parent


def batch_prefix(symbol: str, provider: str) -> str:
    return f"{symbol.lower()}_{provider}_sorted_batch_"


def load_provider_ohlcv(
    *,
    symbol: str,
    provider: str,
    market: str,
    interval: str,
    base_dir: Path = BASE_DIR,
) -> pl.DataFrame:
    source_dir = output_dir_for_interval(
        base_dir,
        interval,
        provider=provider,
        market=market,
    )
    files = sorted(source_dir.glob(f"{batch_prefix(symbol, provider)}*.parquet"))
    if not files:
        raise FileNotFoundError(f"No {symbol} {interval} files found in {source_dir}")
    df = pl.concat([pl.read_parquet(path) for path in files])
    return (
        df.select(OHLCV_COLUMNS)
        .with_columns(pl.col("timestamp").cast(TIMESTAMP_DTYPE))
        .unique(subset=["timestamp"], keep="last")
        .sort("timestamp")
    )


def aggregate_ohlcv(
    df: pl.DataFrame,
    *,
    source_interval: str,
    target_interval: str,
    allow_partial: bool = False,
) -> pl.DataFrame:
    if source_interval not in INTERVAL_MS:
        raise KeyError(f"Unsupported source interval {source_interval!r}")
    if target_interval not in INTERVAL_MS:
        raise KeyError(f"Unsupported target interval {target_interval!r}")
    source_ms = INTERVAL_MS[source_interval]
    target_ms = INTERVAL_MS[target_interval]
    if target_ms <= source_ms or target_ms % source_ms != 0:
        raise ValueError(
            f"target_interval={target_interval!r} must be an integer multiple "
            f"above source_interval={source_interval!r}"
        )

    expected_count = target_ms // source_ms
    every = f"{target_ms // 60_000}m"
    out = (
        df.select(OHLCV_COLUMNS)
        .with_columns(pl.col("timestamp").cast(TIMESTAMP_DTYPE))
        .sort("timestamp")
        .group_by_dynamic("timestamp", every=every, period=every, closed="left")
        .agg(
            [
                pl.col("open").first().alias("open"),
                pl.col("high").max().alias("high"),
                pl.col("low").min().alias("low"),
                pl.col("close").last().alias("close"),
                pl.col("volume").sum().alias("volume"),
                pl.when(pl.col("turnover").is_not_null().any())
                .then(pl.col("turnover").sum())
                .otherwise(pl.lit(None).cast(pl.Float64))
                .alias("turnover"),
                pl.len().alias("bar_count"),
            ]
        )
        .sort("timestamp")
    )
    if not allow_partial:
        out = out.filter(pl.col("bar_count") == expected_count)
    return (
        out.with_columns(pl.lit(target_interval).alias("interval"))
        .drop("bar_count")
        .select(OHLCV_COLUMNS)
        .with_columns(pl.col("timestamp").cast(TIMESTAMP_DTYPE))
    )


def write_aggregate(
    *,
    symbol: str,
    provider: str,
    market: str,
    source_interval: str,
    target_interval: str,
    base_dir: Path = BASE_DIR,
    allow_partial: bool = False,
) -> int:
    df = load_provider_ohlcv(
        symbol=symbol,
        provider=provider,
        market=market,
        interval=source_interval,
        base_dir=base_dir,
    )
    aggregated = aggregate_ohlcv(
        df,
        source_interval=source_interval,
        target_interval=target_interval,
        allow_partial=allow_partial,
    )
    asset_like = type(
        "AssetLike", (), {"slug": symbol.lower(), "symbol": symbol.upper()}
    )()
    summary = append_ohlcv_batches(
        aggregated,
        asset=asset_like,  # type: ignore[arg-type]
        interval=target_interval,
        base_dir=base_dir,
        provider=provider,
        market=market,
    )
    return summary.rows_written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Aggregate normalized multi-asset OHLCV parquet intervals",
    )
    parser.add_argument("--symbols", required=True, help="Comma-separated ids")
    parser.add_argument("--provider", required=True)
    parser.add_argument("--market", required=True)
    parser.add_argument("--source-interval", default="1m")
    parser.add_argument("--target-interval", default="15m")
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Keep incomplete target bars; useful only for tiny probes",
    )
    args = parser.parse_args(argv)

    symbols = [part.strip().upper() for part in args.symbols.split(",") if part.strip()]
    for symbol in symbols:
        rows = write_aggregate(
            symbol=symbol,
            provider=args.provider,
            market=args.market,
            source_interval=args.source_interval,
            target_interval=args.target_interval,
            allow_partial=args.allow_partial,
        )
        print(
            f"{symbol}: {args.source_interval}->{args.target_interval} "
            f"rows_written_total={rows}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
