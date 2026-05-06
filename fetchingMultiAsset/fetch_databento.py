#!/usr/bin/env python3
"""Databento futures OHLCV fetch/preflight utilities."""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import polars as pl

try:
    from .asset_config import (
        DATABENTO_MARKET,
        DATABENTO_PROVIDER,
        DatabentoFuturesSpec,
        selected_databento_futures,
    )
    from .fetch_twelve_data import (
        OHLCV_COLUMNS,
        TIMESTAMP_DTYPE,
        append_ohlcv_batches,
        existing_summary,
        load_local_secret_files,
        output_dir_for_interval,
        parse_datetime,
    )
except ImportError:  # pragma: no cover - script execution from fetchingMultiAsset/
    from asset_config import (  # type: ignore
        DATABENTO_MARKET,
        DATABENTO_PROVIDER,
        DatabentoFuturesSpec,
        selected_databento_futures,
    )
    from fetch_twelve_data import (  # type: ignore
        OHLCV_COLUMNS,
        TIMESTAMP_DTYPE,
        append_ohlcv_batches,
        existing_summary,
        load_local_secret_files,
        output_dir_for_interval,
        parse_datetime,
    )


BASE_DIR = Path(__file__).resolve().parent
DATABENTO_SAFE_END_DELAY = timedelta(minutes=10)
DATABENTO_SAFE_END_INTERVAL = timedelta(minutes=15)


class DatabentoNotInstalledError(RuntimeError):
    """Raised when the optional Databento SDK is not installed."""


@dataclass(frozen=True)
class DatabentoCostEstimate:
    asset: str
    provider_symbol: str
    dataset: str
    schema: str
    start: str
    end: str
    cost_usd: float


@dataclass(frozen=True)
class DatabentoFetchPlan:
    asset: str
    provider_symbol: str
    requested_start: datetime
    requested_end: datetime
    fetch_start: datetime | None
    fetch_end: datetime | None
    local_last_ts: datetime | None
    status: str

    @property
    def needs_fetch(self) -> bool:
        return self.fetch_start is not None and self.fetch_end is not None


def configured_databento_api_key(cli_api_key: str | None = None) -> str | None:
    if cli_api_key:
        return cli_api_key
    if os.getenv("DATABENTO_API_KEY"):
        return os.getenv("DATABENTO_API_KEY")
    load_local_secret_files()
    return os.getenv("DATABENTO_API_KEY")


def require_databento_sdk():
    try:
        import databento as db
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on local env
        raise DatabentoNotInstalledError(
            "Databento SDK is not installed. Install it with: python -m pip install databento"
        ) from exc
    return db


def databento_client(api_key: str | None = None):
    key = configured_databento_api_key(api_key)
    if not key:
        raise RuntimeError(
            "DATABENTO_API_KEY is missing from environment or local_secrets.env"
        )
    db = require_databento_sdk()
    return db.Historical(key)


def output_dir_for_databento_interval(base_dir: Path, interval: str) -> Path:
    return output_dir_for_interval(
        base_dir,
        interval,
        provider=DATABENTO_PROVIDER,
        market=DATABENTO_MARKET,
    )


def databento_batch_prefix(asset: DatabentoFuturesSpec) -> str:
    return f"{asset.slug}_{DATABENTO_PROVIDER}_sorted_batch_"


def _floor_datetime(dt: datetime, interval: timedelta) -> datetime:
    seconds = int(dt.timestamp())
    interval_seconds = int(interval.total_seconds())
    floored = seconds - (seconds % interval_seconds)
    return datetime.fromtimestamp(floored, tz=timezone.utc)


def latest_safe_databento_end(now: datetime | None = None) -> datetime:
    """Return a conservative provider-safe end for Databento `end=now` queries."""
    current = parse_datetime(now) if now is not None else datetime.now(timezone.utc)
    return _floor_datetime(
        current - DATABENTO_SAFE_END_DELAY,
        DATABENTO_SAFE_END_INTERVAL,
    )


def resolve_databento_end(
    end: str | datetime,
    *,
    now: datetime | None = None,
) -> datetime:
    """Cap Databento end timestamps to avoid querying unpublished recent bars."""
    if isinstance(end, str) and end.strip().lower() in {"now", "today"} and now:
        requested_end = parse_datetime(now)
    else:
        requested_end = parse_datetime(end)
    return min(requested_end, latest_safe_databento_end(now))


def databento_available_end(
    client: Any,
    *,
    dataset: str,
    schema: str,
) -> datetime:
    """Return the Databento entitlement-aware available end for a schema."""
    dataset_range = client.metadata.get_dataset_range(dataset=dataset)
    schema_ranges = dataset_range.get("schema") or {}
    schema_range = (
        schema_ranges.get(schema) if isinstance(schema_ranges, dict) else None
    )
    range_payload = schema_range or dataset_range
    end = range_payload.get("end") if isinstance(range_payload, dict) else None
    if not end:
        raise RuntimeError(f"Databento dataset range has no end for {dataset} {schema}")
    return parse_datetime(str(end))


def plan_fetch_range(
    *,
    asset: DatabentoFuturesSpec,
    start: str | datetime,
    end: str | datetime,
    base_dir: Path = BASE_DIR,
    available_end: datetime | None = None,
) -> DatabentoFetchPlan:
    requested_start = parse_datetime(start)
    requested_end = resolve_databento_end(end)
    if available_end is not None:
        requested_end = min(requested_end, parse_datetime(available_end))
    summary = existing_summary(
        asset=asset,  # type: ignore[arg-type]
        interval="1m",
        base_dir=base_dir,
        provider=DATABENTO_PROVIDER,
        market=DATABENTO_MARKET,
    )
    fetch_start = requested_start
    # Databento OHLCV schema here is 1-minute, so resume strictly after the
    # latest local bar. This avoids spending credits refetching known history.
    if summary.last_ts is not None:
        fetch_start = max(requested_start, summary.last_ts + timedelta(minutes=1))

    if fetch_start > requested_end:
        return DatabentoFetchPlan(
            asset=asset.symbol,
            provider_symbol=asset.provider_symbol,
            requested_start=requested_start,
            requested_end=requested_end,
            fetch_start=None,
            fetch_end=None,
            local_last_ts=summary.last_ts,
            status="up-to-date",
        )

    return DatabentoFetchPlan(
        asset=asset.symbol,
        provider_symbol=asset.provider_symbol,
        requested_start=requested_start,
        requested_end=requested_end,
        fetch_start=fetch_start,
        fetch_end=requested_end,
        local_last_ts=summary.last_ts,
        status="fetch",
    )


def _inverse_price_expr(column: str) -> pl.Expr:
    return (
        pl.when(pl.col(column).is_not_null() & (pl.col(column) != 0))
        .then(1.0 / pl.col(column))
        .otherwise(None)
    )


def databento_frame_to_ohlcv(
    frame: Any,
    interval_label: str,
    *,
    price_transform: str = "identity",
) -> pl.DataFrame:
    """Normalize a Databento OHLCV DataFrame into the Bybit-style schema."""
    df = pl.from_pandas(frame.reset_index() if hasattr(frame, "reset_index") else frame)
    timestamp_col = None
    for candidate in ("ts_event", "timestamp", "index"):
        if candidate in df.columns:
            timestamp_col = candidate
            break
    if timestamp_col is None:
        raise ValueError(f"Databento frame has no timestamp column: {df.columns}")

    required = {"open", "high", "low", "close", "volume"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Databento frame missing OHLCV columns: {missing}")

    normalized = (
        df.with_columns(
            [
                pl.col(timestamp_col).cast(TIMESTAMP_DTYPE).alias("timestamp"),
                pl.col("open").cast(pl.Float64),
                pl.col("high").cast(pl.Float64),
                pl.col("low").cast(pl.Float64),
                pl.col("close").cast(pl.Float64),
                pl.col("volume").cast(pl.Float64),
                pl.lit(None).cast(pl.Float64).alias("turnover"),
                pl.lit(interval_label).alias("interval"),
            ]
        )
        .select(OHLCV_COLUMNS)
        .unique(subset=["timestamp"], keep="last")
        .sort("timestamp")
    )
    if price_transform == "identity":
        return normalized
    if price_transform == "inverse":
        return normalized.with_columns(
            [
                _inverse_price_expr("open").alias("open"),
                _inverse_price_expr("low").alias("high"),
                _inverse_price_expr("high").alias("low"),
                _inverse_price_expr("close").alias("close"),
            ]
        ).select(OHLCV_COLUMNS)
    raise ValueError(f"Unsupported Databento price transform {price_transform!r}")


def estimate_costs(
    *,
    assets: tuple[DatabentoFuturesSpec, ...],
    start: str,
    end: str,
    base_dir: Path = BASE_DIR,
    api_key: str | None = None,
) -> list[DatabentoCostEstimate]:
    client = databento_client(api_key)
    estimates = []
    available_end_by_source: dict[tuple[str, str], datetime] = {}
    for asset in assets:
        source_key = (asset.dataset, asset.schema)
        if source_key not in available_end_by_source:
            available_end_by_source[source_key] = databento_available_end(
                client,
                dataset=asset.dataset,
                schema=asset.schema,
            )
        plan = plan_fetch_range(
            asset=asset,
            start=start,
            end=end,
            base_dir=base_dir,
            available_end=available_end_by_source[source_key],
        )
        if not plan.needs_fetch:
            estimates.append(
                DatabentoCostEstimate(
                    asset=asset.symbol,
                    provider_symbol=asset.provider_symbol,
                    dataset=asset.dataset,
                    schema=asset.schema,
                    start=start,
                    end=end,
                    cost_usd=0.0,
                )
            )
            continue
        cost = client.metadata.get_cost(
            dataset=asset.dataset,
            symbols=asset.provider_symbol,
            stype_in=asset.stype_in,
            schema=asset.schema,
            start=plan.fetch_start.isoformat(),
            end=plan.fetch_end.isoformat(),
        )
        estimates.append(
            DatabentoCostEstimate(
                asset=asset.symbol,
                provider_symbol=asset.provider_symbol,
                dataset=asset.dataset,
                schema=asset.schema,
                start=plan.fetch_start.isoformat(),
                end=plan.fetch_end.isoformat(),
                cost_usd=float(cost),
            )
        )
    return estimates


def fetch_asset_interval(
    *,
    asset: DatabentoFuturesSpec,
    start: str | datetime,
    end: str | datetime,
    base_dir: Path = BASE_DIR,
    api_key: str | None = None,
    max_cost_usd: float | None = None,
) -> int:
    """Fetch one Databento futures asset as 1m OHLCV and append parquet batches."""
    start_dt = parse_datetime(start)
    end_dt = parse_datetime(end)
    client = databento_client(api_key)
    available_end = databento_available_end(
        client,
        dataset=asset.dataset,
        schema=asset.schema,
    )
    plan = plan_fetch_range(
        asset=asset,
        start=start_dt,
        end=end_dt,
        base_dir=base_dir,
        available_end=available_end,
    )
    if not plan.needs_fetch:
        return existing_summary(
            asset=asset,  # type: ignore[arg-type]
            interval="1m",
            base_dir=base_dir,
            provider=DATABENTO_PROVIDER,
            market=DATABENTO_MARKET,
        ).rows_written

    start_s = plan.fetch_start.isoformat()
    end_s = plan.fetch_end.isoformat()

    if max_cost_usd is not None:
        estimate = estimate_costs(
            assets=(asset,),
            start=start_s,
            end=end_s,
            base_dir=base_dir,
            api_key=api_key,
        )[0]
        if estimate.cost_usd > max_cost_usd:
            raise RuntimeError(
                f"Refusing Databento fetch for {asset.symbol}: estimated "
                f"${estimate.cost_usd:.6f} exceeds max ${max_cost_usd:.6f}"
            )

    data = client.timeseries.get_range(
        dataset=asset.dataset,
        symbols=asset.provider_symbol,
        stype_in=asset.stype_in,
        schema=asset.schema,
        start=start_s,
        end=end_s,
    )
    df = databento_frame_to_ohlcv(
        data.to_df(),
        "1m",
        price_transform=asset.price_transform,
    )
    summary = append_ohlcv_batches(
        df,
        asset=asset,  # type: ignore[arg-type]
        interval="1m",
        base_dir=base_dir,
        provider=DATABENTO_PROVIDER,
        market=DATABENTO_MARKET,
    )
    return summary.rows_written


def print_plan(
    assets: tuple[DatabentoFuturesSpec, ...], base_dir: Path = BASE_DIR
) -> None:
    print("\nDATABENTO FUTURES PLAN")
    print("-" * 70)
    for asset in assets:
        out_dir = output_dir_for_databento_interval(base_dir, "1m")
        print(
            f"{asset.symbol:<3} {asset.provider_symbol:<8} "
            f"dataset={asset.dataset:<9} schema={asset.schema:<8} "
            f"stype={asset.stype_in:<10} -> {out_dir.name}/{databento_batch_prefix(asset)}*.parquet"
        )
    print("-" * 70)
    print("Full fetches require an explicit --fetch and a --max-cost-usd guard.")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Databento futures preflight/fetcher for normalized OHLCV bars",
    )
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--assets", default="", help="Comma-separated ids: GC,CL,ES,NQ")
    parser.add_argument("--start", default="2024-01-02T14:30:00Z")
    parser.add_argument("--end", default="2024-01-02T15:30:00Z")
    parser.add_argument("--dry-run", action="store_true", help="Print output plan only")
    parser.add_argument(
        "--estimate-cost", action="store_true", help="Call free metadata.get_cost"
    )
    parser.add_argument(
        "--fetch", action="store_true", help="Fetch the requested range"
    )
    parser.add_argument(
        "--max-cost-usd",
        type=float,
        default=0.0,
        help="Required non-negative cost ceiling for --fetch",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    assets = selected_databento_futures(
        tuple(part.strip().upper() for part in args.assets.split(",") if part.strip())
        if args.assets
        else None
    )

    key = configured_databento_api_key(args.api_key)
    print("DATABENTO_API_KEY:", "present" if key else "missing")
    print_plan(assets)

    if args.dry_run or (not args.estimate_cost and not args.fetch):
        return 0

    if args.estimate_cost:
        estimates = estimate_costs(
            assets=assets,
            start=args.start,
            end=args.end,
            api_key=args.api_key,
        )
        total = sum(item.cost_usd for item in estimates)
        for item in estimates:
            print(
                f"cost {item.asset:<3} {item.provider_symbol:<8} "
                f"{item.start} -> {item.end}: ${item.cost_usd:.8f}"
            )
        print(f"total estimated Databento cost: ${total:.8f}")

    if args.fetch:
        if args.max_cost_usd < 0:
            print("ERROR: --max-cost-usd must be >= 0")
            return 2
        for asset in assets:
            rows = fetch_asset_interval(
                asset=asset,
                start=args.start,
                end=args.end,
                api_key=args.api_key,
                max_cost_usd=args.max_cost_usd,
            )
            print(f"fetched {asset.symbol}: rows_written_total={rows}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
