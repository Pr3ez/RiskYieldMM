#!/usr/bin/env python3
"""Unified update entry point for normalized multi-asset OHLCV sources."""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from .aggregate_ohlcv import write_aggregate
    from .asset_config import (
        DATABENTO_MARKET,
        DATABENTO_PROVIDER,
        DEFAULT_INTERVALS,
        HTF_REQUIRED_INTERVALS,
        INTERVAL_MS,
        TWELVE_DATA_INTERVALS,
        YFINANCE_MARKET,
        YFINANCE_PROVIDER,
        AssetSpec,
        DatabentoFuturesSpec,
        YFinanceFuturesSpec,
        selected_assets,
        selected_databento_futures,
        selected_yfinance_futures,
    )
    from .fetch_databento import (
        estimate_costs,
        resolve_databento_end,
    )
    from .fetch_databento import (
        fetch_asset_interval as fetch_databento_interval,
    )
    from .fetch_databento import (
        plan_fetch_range as plan_databento_fetch_range,
    )
    from .fetch_twelve_data import (
        TwelveDataClient,
        _asset_id_list,
        _interval_list,
        batch_prefix,
        configured_api_key,
        existing_summary,
        output_dir_for_interval,
        parse_datetime,
    )
    from .fetch_twelve_data import (
        discover_symbols as discover_twelve_symbols,
    )
    from .fetch_twelve_data import (
        fetch_asset_interval as fetch_twelve_interval,
    )
    from .fetch_twelve_data import (
        print_status as print_twelve_status,
    )
    from .fetch_yfinance import (
        DEFAULT_MAX_CLOSE_DIFF_PCT,
        DEFAULT_MIN_OVERLAP_BARS,
        DEFAULT_OVERLAP_BARS,
        YFINANCE_INTERVAL_LIMITS,
        YFinanceDemoPlan,
        YFinanceTailPlan,
        fetch_yfinance_demo,
        fetch_yfinance_tail,
        plan_yfinance_demo,
        plan_yfinance_tail,
        resolve_yfinance_demo_window,
    )
except ImportError:  # pragma: no cover - script execution from fetchingMultiAsset/
    from aggregate_ohlcv import write_aggregate  # type: ignore
    from asset_config import (  # type: ignore
        DATABENTO_MARKET,
        DATABENTO_PROVIDER,
        DEFAULT_INTERVALS,
        HTF_REQUIRED_INTERVALS,
        INTERVAL_MS,
        TWELVE_DATA_INTERVALS,
        YFINANCE_MARKET,
        YFINANCE_PROVIDER,
        AssetSpec,
        DatabentoFuturesSpec,
        YFinanceFuturesSpec,
        selected_assets,
        selected_databento_futures,
        selected_yfinance_futures,
    )
    from fetch_databento import (  # type: ignore
        estimate_costs,
        resolve_databento_end,
    )
    from fetch_databento import (
        fetch_asset_interval as fetch_databento_interval,
    )
    from fetch_databento import (
        plan_fetch_range as plan_databento_fetch_range,
    )
    from fetch_twelve_data import (  # type: ignore
        TwelveDataClient,
        _asset_id_list,
        _interval_list,
        batch_prefix,
        configured_api_key,
        existing_summary,
        output_dir_for_interval,
        parse_datetime,
    )
    from fetch_twelve_data import (
        discover_symbols as discover_twelve_symbols,
    )
    from fetch_twelve_data import (
        fetch_asset_interval as fetch_twelve_interval,
    )
    from fetch_twelve_data import (
        print_status as print_twelve_status,
    )
    from fetch_yfinance import (  # type: ignore
        DEFAULT_MAX_CLOSE_DIFF_PCT,
        DEFAULT_MIN_OVERLAP_BARS,
        DEFAULT_OVERLAP_BARS,
        YFINANCE_INTERVAL_LIMITS,
        YFinanceDemoPlan,
        YFinanceTailPlan,
        fetch_yfinance_demo,
        fetch_yfinance_tail,
        plan_yfinance_demo,
        plan_yfinance_tail,
        resolve_yfinance_demo_window,
    )


BASE_DIR = Path(__file__).resolve().parent
PROVIDERS = ("twelvedata", "databento", "yfinance")
AUTO_PROVIDER = "auto"
KNOWN_PROVIDERS = (*PROVIDERS, AUTO_PROVIDER)
CORE_TWELVE_ASSETS = ("EURUSD", "USDJPY")
CORE_DATABENTO_FUTURES = ("EURUSD", "USDJPY", "GC", "CL", "ES", "NQ")
CORE_YFINANCE_FUTURES = CORE_DATABENTO_FUTURES


@dataclass(frozen=True)
class TwelveRequestEstimate:
    asset: str
    interval: str
    fetch_start: datetime | None
    fetch_end: datetime | None
    estimated_requests: int
    local_last_ts: datetime | None


@dataclass(frozen=True)
class LocalInventoryRow:
    provider: str
    market: str
    asset: str
    interval: str
    files: int
    rows: int
    first_ts: datetime | None
    last_ts: datetime | None
    first_file_rows: int | None
    last_file_rows: int | None
    notes: tuple[str, ...]


@dataclass(frozen=True)
class AutoRoutePlan:
    yfinance_assets: tuple[YFinanceFuturesSpec, ...]
    databento_fallback_assets: tuple[DatabentoFuturesSpec, ...]
    yfinance_plans: tuple[YFinanceTailPlan, ...]


def _csv(raw: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def provider_list(raw: str, *, all_providers: bool = False) -> tuple[str, ...]:
    if all_providers:
        return PROVIDERS
    if not raw:
        return ("twelvedata",)
    providers = tuple(provider.lower() for provider in _csv(raw))
    unknown = [provider for provider in providers if provider not in KNOWN_PROVIDERS]
    if unknown:
        raise argparse.ArgumentTypeError(
            f"Unknown providers: {unknown}. Known providers: {', '.join(KNOWN_PROVIDERS)}"
        )
    if AUTO_PROVIDER in providers and len(providers) > 1:
        raise argparse.ArgumentTypeError(
            "--providers auto is a composite router and cannot be combined "
            "with explicit providers."
        )
    return providers


def _expanded_inventory_providers(providers: tuple[str, ...]) -> tuple[str, ...]:
    expanded = set(providers)
    if AUTO_PROVIDER in expanded:
        expanded.update(("databento", "yfinance"))
    return tuple(provider for provider in PROVIDERS if provider in expanded)


def _resolve_end(end_date: str | datetime) -> datetime:
    return min(parse_datetime(end_date), datetime.now(timezone.utc))


def _format_cli_datetime(dt: datetime) -> str:
    return (
        dt.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _read_file_rows(path: Path | None) -> int | None:
    if path is None or not path.exists():
        return None
    return int(existing_summary_file_rows(path))


def existing_summary_file_rows(path: Path) -> int:
    try:
        import pyarrow.parquet as pq

        return int(pq.ParquetFile(path).metadata.num_rows)
    except Exception:
        import polars as pl

        return int(pl.read_parquet(path, columns=["timestamp"]).height)


def _local_inventory_for_asset(
    *,
    asset: AssetSpec | DatabentoFuturesSpec | YFinanceFuturesSpec,
    interval: str,
    provider: str,
    market: str,
    requested_start: datetime,
    requested_end: datetime,
    base_dir: Path = BASE_DIR,
) -> LocalInventoryRow:
    summary = existing_summary(
        asset=asset,  # type: ignore[arg-type]
        interval=interval,
        base_dir=base_dir,
        provider=provider,
        market=market,
    )
    output_dir = output_dir_for_interval(
        base_dir,
        interval,
        provider=provider,
        market=market,
    )
    files = sorted(output_dir.glob(f"{batch_prefix(asset, provider=provider)}*.parquet"))  # type: ignore[arg-type]
    first_file_rows = _read_file_rows(files[0] if files else None)
    last_file_rows = _read_file_rows(files[-1] if files else None)
    notes: list[str] = []
    step = timedelta(milliseconds=INTERVAL_MS[interval])

    if summary.files == 0:
        notes.append("not_found")
    if summary.first_ts is not None and summary.first_ts > requested_start + step:
        prefix_gap = summary.first_ts - requested_start
        label = (
            "missing_prefix_from"
            if prefix_gap >= timedelta(days=7)
            else "starts_after_requested"
        )
        notes.append(f"{label}={requested_start.isoformat()}")
    if summary.last_ts is not None and summary.last_ts < requested_end - step:
        notes.append(f"resume_after={(summary.last_ts + step).isoformat()}")
    if provider == DATABENTO_PROVIDER and interval != "1m" and summary.files > 0:
        notes.append("derived_local")
    if summary.files > 0 and summary.rows_written > 0:
        avg_rows = summary.rows_written / summary.files
        if first_file_rows is not None and first_file_rows < 500 and summary.files > 10:
            notes.append(f"probe_first_file_rows={first_file_rows}")
        if avg_rows < 500 and summary.files > 100:
            notes.append(f"fragmented_avg_rows={avg_rows:.1f}")

    return LocalInventoryRow(
        provider=provider,
        market=market,
        asset=asset.symbol,
        interval=interval,
        files=summary.files,
        rows=summary.rows_written,
        first_ts=summary.first_ts,
        last_ts=summary.last_ts,
        first_file_rows=first_file_rows,
        last_file_rows=last_file_rows,
        notes=tuple(notes),
    )


def build_local_inventory(
    *,
    providers: tuple[str, ...],
    twelve_assets: tuple[AssetSpec, ...],
    futures_assets: tuple[DatabentoFuturesSpec, ...],
    yfinance_assets: tuple[YFinanceFuturesSpec, ...],
    intervals: tuple[str, ...],
    start_date: str,
    end_date: str,
    base_dir: Path = BASE_DIR,
) -> list[LocalInventoryRow]:
    rows: list[LocalInventoryRow] = []
    inventory_providers = _expanded_inventory_providers(providers)
    requested_start = parse_datetime(start_date)
    if "twelvedata" in inventory_providers:
        requested_end = _resolve_end(end_date)
        for asset in twelve_assets:
            for interval in intervals:
                rows.append(
                    _local_inventory_for_asset(
                        asset=asset,
                        interval=interval,
                        provider="twelvedata",
                        market="multi",
                        requested_start=requested_start,
                        requested_end=requested_end,
                        base_dir=base_dir,
                    )
                )
    if "databento" in inventory_providers:
        requested_end = resolve_databento_end(end_date)
        for asset in futures_assets:
            for interval in intervals:
                rows.append(
                    _local_inventory_for_asset(
                        asset=asset,
                        interval=interval,
                        provider=DATABENTO_PROVIDER,
                        market=DATABENTO_MARKET,
                        requested_start=requested_start,
                        requested_end=requested_end,
                        base_dir=base_dir,
                    )
                )
    if "yfinance" in inventory_providers:
        requested_end = _resolve_end(end_date)
        for asset in yfinance_assets:
            for interval in intervals:
                rows.append(
                    _local_inventory_for_asset(
                        asset=asset,
                        interval=interval,
                        provider=YFINANCE_PROVIDER,
                        market=YFINANCE_MARKET,
                        requested_start=requested_start,
                        requested_end=requested_end,
                        base_dir=base_dir,
                    )
                )
    return rows


def _fmt_dt(value: datetime | None) -> str:
    if value is None:
        return "-"
    return value.strftime("%Y-%m-%d %H:%M")


def print_local_inventory(rows: list[LocalInventoryRow]) -> None:
    print("\nLOCAL DATA INVENTORY (NO NETWORK / NO WRITES)")
    print("-" * 110)
    if not rows:
        print("No selected local assets to scan.")
        return
    print(
        f"{'Provider':<10} {'Asset':<7} {'Int':<4} {'Files':>8} {'Rows':>12} "
        f"{'First UTC':<16} {'Last UTC':<16} Notes"
    )
    for row in rows:
        notes = ", ".join(row.notes) if row.notes else "ok"
        print(
            f"{row.provider:<10} {row.asset:<7} {row.interval:<4} "
            f"{row.files:>8,} {row.rows:>12,} "
            f"{_fmt_dt(row.first_ts):<16} {_fmt_dt(row.last_ts):<16} {notes}"
        )


def estimate_twelve_requests(
    *,
    assets: tuple[AssetSpec, ...],
    intervals: tuple[str, ...],
    start_date: str | datetime,
    end_date: str | datetime,
    base_dir: Path = BASE_DIR,
) -> list[TwelveRequestEstimate]:
    requested_start = parse_datetime(start_date)
    requested_end = _resolve_end(end_date)
    estimates: list[TwelveRequestEstimate] = []
    for asset in assets:
        for interval in intervals:
            step = timedelta(milliseconds=INTERVAL_MS[interval])
            summary = existing_summary(
                asset=asset, interval=interval, base_dir=base_dir
            )
            fetch_start = requested_start
            if summary.last_ts is not None:
                fetch_start = max(requested_start, summary.last_ts + step)
            if fetch_start > requested_end:
                estimates.append(
                    TwelveRequestEstimate(
                        asset=asset.symbol,
                        interval=interval,
                        fetch_start=None,
                        fetch_end=None,
                        estimated_requests=0,
                        local_last_ts=summary.last_ts,
                    )
                )
                continue
            bars = (
                int(
                    (requested_end - fetch_start).total_seconds()
                    * 1000
                    // INTERVAL_MS[interval]
                )
                + 1
            )
            estimates.append(
                TwelveRequestEstimate(
                    asset=asset.symbol,
                    interval=interval,
                    fetch_start=fetch_start,
                    fetch_end=requested_end,
                    estimated_requests=max(1, math.ceil(bars / 5000)),
                    local_last_ts=summary.last_ts,
                )
            )
    return estimates


def _print_twelve_plan(estimates: list[TwelveRequestEstimate]) -> int:
    total = sum(item.estimated_requests for item in estimates)
    print("\nTWELVE DATA PLAN")
    print("-" * 70)
    for item in estimates:
        if item.estimated_requests == 0:
            print(
                f"{item.asset:<7} {item.interval:<3} up-to-date local_last={item.local_last_ts}"
            )
        else:
            print(
                f"{item.asset:<7} {item.interval:<3} "
                f"{item.fetch_start} -> {item.fetch_end} "
                f"requests~{item.estimated_requests}"
            )
    print(f"Estimated Twelve Data requests: {total}")
    return total


def _print_databento_plan(
    assets: tuple[DatabentoFuturesSpec, ...],
    *,
    start_date: str,
    end_date: str,
) -> None:
    print("\nDATABENTO PRELIMINARY PLAN")
    print("-" * 70)
    print(
        "This plan is capped to provider-published data. Account-entitled "
        "cost/fetch ranges are printed below after metadata estimation."
    )
    requested_end = parse_datetime(end_date)
    effective_end = resolve_databento_end(end_date)
    if effective_end < requested_end:
        print(
            f"Databento effective end capped to {effective_end} "
            "(provider-safe published-data boundary)."
        )
    for asset in assets:
        plan = plan_databento_fetch_range(asset=asset, start=start_date, end=end_date)
        if not plan.needs_fetch:
            print(
                f"{asset.symbol:<3} {asset.provider_symbol:<8} up-to-date local_last={plan.local_last_ts}"
            )
        else:
            print(
                f"{asset.symbol:<3} {asset.provider_symbol:<8} "
                f"{plan.fetch_start} -> {plan.fetch_end} "
                "fetch=1m, derive requested intervals locally"
            )


def plan_auto_fresh_tail(
    *,
    futures_assets: tuple[DatabentoFuturesSpec, ...],
    yfinance_assets: tuple[YFinanceFuturesSpec, ...],
    end_date: str,
    overlap_bars: int,
    base_dir: Path = BASE_DIR,
    now: datetime | None = None,
) -> AutoRoutePlan:
    """Route each non-crypto asset to Yahoo if its missing range is eligible."""
    target_end = _resolve_end(end_date)
    yfinance_ready: list[YFinanceFuturesSpec] = []
    fallback_symbols: set[str] = set()
    plans: list[YFinanceTailPlan] = []
    futures_symbols = {asset.symbol for asset in futures_assets}

    for asset in yfinance_assets:
        plan = plan_yfinance_tail(
            asset=asset,
            interval="1m",
            base_dir=base_dir,
            now=now,
            target_end=target_end,
            overlap_bars=overlap_bars,
        )
        plans.append(plan)
        if plan.status in {"fetch", "up_to_date"}:
            yfinance_ready.append(asset)
        elif asset.symbol in futures_symbols:
            fallback_symbols.add(asset.symbol)

    yfinance_symbols = {asset.symbol for asset in yfinance_assets}
    fallback_symbols.update(
        asset.symbol for asset in futures_assets if asset.symbol not in yfinance_symbols
    )
    fallback_assets = tuple(
        asset for asset in futures_assets if asset.symbol in fallback_symbols
    )
    return AutoRoutePlan(
        yfinance_assets=tuple(yfinance_ready),
        databento_fallback_assets=fallback_assets,
        yfinance_plans=tuple(plans),
    )


def print_auto_route(route: AutoRoutePlan) -> None:
    print("\nAUTO SOURCE ROUTING")
    print("-" * 70)
    print(
        "Yahoo is attempted first for recent 1m tails. Databento is used only "
        "for assets whose local gap is outside Yahoo's safe range."
    )
    fallback_symbols = {asset.symbol for asset in route.databento_fallback_assets}
    for plan in route.yfinance_plans:
        if plan.status == "fetch":
            source = "yfinance"
            detail = f"{plan.fetch_start} -> {plan.fetch_end}"
        elif plan.status == "up_to_date":
            source = "local"
            detail = plan.reason
        elif plan.asset in fallback_symbols:
            source = "databento_fallback"
            detail = plan.reason
        else:
            source = "unavailable"
            detail = plan.reason
        print(
            f"{plan.asset:<7} {plan.provider_symbol:<6} "
            f"{source:<19} {plan.status}: {detail}"
        )
    if route.databento_fallback_assets:
        symbols = ",".join(asset.symbol for asset in route.databento_fallback_assets)
        print(f"Databento fallback required for: {symbols}")
    else:
        print("Databento fallback required for: none")


def run_twelve(
    *,
    assets: tuple[AssetSpec, ...],
    intervals: tuple[str, ...],
    start_date: str,
    end_date: str,
    dry_run: bool,
    estimate_only: bool,
    max_requests: int,
    request_sleep: float,
    api_key: str | None,
) -> bool:
    estimates = estimate_twelve_requests(
        assets=assets,
        intervals=intervals,
        start_date=start_date,
        end_date=end_date,
    )
    request_count = _print_twelve_plan(estimates)
    if dry_run or estimate_only:
        return True
    if max_requests >= 0 and request_count > max_requests:
        print(
            f"ERROR: Twelve Data plan needs ~{request_count} requests, "
            f"above --max-twelve-requests={max_requests}. "
            "Use smaller date chunks or raise the limit intentionally."
        )
        return False

    key = configured_api_key(api_key)
    if not key:
        print("ERROR: TWELVE_DATA_API_KEY is missing.")
        return False
    client = TwelveDataClient(key)
    ok = True
    for asset in assets:
        for interval in intervals:
            try:
                summary = fetch_twelve_interval(
                    asset=asset,
                    interval=interval,
                    client=client,
                    start_date=start_date,
                    end_date=end_date,
                    request_sleep=request_sleep,
                )
                print(
                    f"Twelve {asset.symbol} {interval}: {summary.status}, "
                    f"fetched={summary.rows_fetched:,}, written={summary.rows_written:,}, "
                    f"range={summary.first_ts} -> {summary.last_ts}"
                )
            except Exception as exc:
                ok = False
                print(f"ERROR: Twelve {asset.symbol} {interval} failed: {exc}")
    return ok


def run_databento(
    *,
    assets: tuple[DatabentoFuturesSpec, ...],
    intervals: tuple[str, ...],
    start_date: str,
    end_date: str,
    dry_run: bool,
    estimate_only: bool,
    max_cost_usd: float,
    api_key: str | None,
) -> bool:
    _print_databento_plan(assets, start_date=start_date, end_date=end_date)
    try:
        estimates = estimate_costs(
            assets=assets,
            start=start_date,
            end=end_date,
            api_key=api_key,
        )
    except Exception as exc:
        print(f"ERROR: Databento cost estimate failed: {exc}")
        return False
    total_cost = sum(item.cost_usd for item in estimates)
    print("\nDATABENTO FINAL COST/FETCH RANGES")
    print("-" * 70)
    for item in estimates:
        print(
            f"Databento cost {item.asset:<3} {item.start} -> {item.end}: "
            f"${item.cost_usd:.8f}"
        )
    print(f"Estimated Databento cost: ${total_cost:.8f}")
    if dry_run or estimate_only:
        return True
    if total_cost > max_cost_usd:
        print(
            f"ERROR: Databento cost ${total_cost:.8f} exceeds "
            f"--max-databento-cost-usd={max_cost_usd:.8f}."
        )
        return False

    ok = True
    for asset in assets:
        try:
            rows = fetch_databento_interval(
                asset=asset,
                start=start_date,
                end=end_date,
                api_key=api_key,
                max_cost_usd=max_cost_usd,
            )
            print(f"Databento {asset.symbol} 1m: rows_written_total={rows}")
            for interval in intervals:
                if interval == "1m":
                    continue
                agg_rows = write_aggregate(
                    symbol=asset.symbol,
                    provider=DATABENTO_PROVIDER,
                    market=DATABENTO_MARKET,
                    source_interval="1m",
                    target_interval=interval,
                )
                print(
                    f"Databento {asset.symbol} {interval}: "
                    f"derived rows_written_total={agg_rows}"
                )
        except Exception as exc:
            ok = False
            print(f"ERROR: Databento {asset.symbol} failed: {exc}")
    return ok


def run_yfinance(
    *,
    assets: tuple[YFinanceFuturesSpec, ...],
    intervals: tuple[str, ...],
    end_date: str,
    dry_run: bool,
    estimate_only: bool,
    overlap_bars: int,
    min_overlap_bars: int,
    max_close_diff_pct: float,
) -> bool:
    print("\nYFINANCE RECENT-TAIL PLAN")
    print("-" * 70)
    print(
        "Yahoo Finance is used only as a recent-tail continuation source. It writes to "
        "separate yfinance folders after Databento overlap validation passes."
    )
    target_end = _resolve_end(end_date)
    ok = True
    planned_assets = assets
    if not planned_assets:
        print("No Yahoo-eligible assets selected.")
        return True
    for asset in planned_assets:
        plan = plan_yfinance_tail(
            asset=asset,
            interval="1m",
            target_end=target_end,
            overlap_bars=overlap_bars,
        )
        if plan.needs_fetch:
            print(
                f"{asset.symbol:<7} {asset.provider_symbol:<6} 1m "
                f"{plan.fetch_start} -> {plan.fetch_end} validate_overlap"
            )
        else:
            print(
                f"{asset.symbol:<7} {asset.provider_symbol:<6} 1m "
                f"{plan.status}: {plan.reason}"
            )
            if plan.status not in {"up_to_date"}:
                ok = False
    if dry_run or estimate_only:
        return ok

    for asset in planned_assets:
        try:
            check = fetch_yfinance_tail(
                asset=asset,
                interval="1m",
                target_end=target_end,
                overlap_bars=overlap_bars,
                min_overlap_bars=min_overlap_bars,
                max_close_diff_pct=max_close_diff_pct,
            )
            print(
                f"Yahoo {asset.symbol} 1m: overlap={check.overlap_rows:,}, "
                f"tail={check.tail_rows:,}, passed={check.passed}, {check.reason}"
            )
            if not check.passed:
                ok = False
                continue
            if "15m" in intervals:
                agg_rows = write_aggregate(
                    symbol=asset.symbol,
                    provider=YFINANCE_PROVIDER,
                    market=YFINANCE_MARKET,
                    source_interval="1m",
                    target_interval="15m",
                )
                print(
                    f"Yahoo {asset.symbol} 15m: derived rows_written_total={agg_rows}"
                )
        except Exception as exc:
            ok = False
            print(f"ERROR: Yahoo {asset.symbol} failed: {exc}")
    return ok


def run_yfinance_demo(
    *,
    assets: tuple[YFinanceFuturesSpec, ...],
    intervals: tuple[str, ...],
    start_date: str,
    end_date: str,
    dry_run: bool,
    estimate_only: bool,
) -> bool:
    print("\nYFINANCE DEMO PLAN")
    print("-" * 70)
    print(
        "Demo mode uses Yahoo Finance standalone data only. It does not require "
        "or validate against Databento, and it writes to separate yfinance folders."
    )
    unsupported = [interval for interval in intervals if interval not in {"1m", "15m"}]
    if unsupported:
        print(f"ERROR: Yahoo demo supports only 1m and derived 15m, got: {unsupported}")
        return False
    target_end = _resolve_end(end_date)
    ok = True
    if not assets:
        print("No Yahoo demo assets selected.")
        return True

    plans: list[YFinanceDemoPlan] = []
    for asset in assets:
        plan = plan_yfinance_demo(asset=asset, interval="1m", target_end=target_end)
        plans.append(plan)
        if plan.needs_fetch:
            print(
                f"{asset.symbol:<7} {asset.provider_symbol:<6} 1m "
                f"{plan.fetch_start} -> {plan.fetch_end} demo_fetch"
            )
        else:
            print(
                f"{asset.symbol:<7} {asset.provider_symbol:<6} 1m "
                f"{plan.status}: {plan.reason}"
            )
            if plan.status not in {"up_to_date"}:
                ok = False

    print(
        f"Demo requested window: {start_date} -> {end_date}; "
        f"Yahoo 1m limit used: {YFINANCE_INTERVAL_LIMITS['1m']}."
    )
    if dry_run or estimate_only:
        return ok

    for asset, plan in zip(assets, plans, strict=True):
        try:
            result = fetch_yfinance_demo(
                asset=asset,
                interval="1m",
                target_end=target_end,
            )
            print(
                f"Yahoo demo {asset.symbol} 1m: status={result.status}, "
                f"fetched={result.fetched_rows:,}, files={result.files}, "
                f"range={result.first_ts} -> {result.last_ts}"
            )
            if result.status not in {"written", "up_to_date"}:
                ok = False
                continue
            if "15m" in intervals:
                agg_rows = write_aggregate(
                    symbol=asset.symbol,
                    provider=YFINANCE_PROVIDER,
                    market=YFINANCE_MARKET,
                    source_interval="1m",
                    target_interval="15m",
                    replace_window_start=plan.fetch_start,
                    replace_window_end=plan.fetch_end,
                )
                print(
                    f"Yahoo demo {asset.symbol} 15m: "
                    f"derived rows_written_total={agg_rows}"
                )
        except Exception as exc:
            ok = False
            print(f"ERROR: Yahoo demo {asset.symbol} failed: {exc}")
    return ok


def run_auto(
    *,
    futures_assets: tuple[DatabentoFuturesSpec, ...],
    yfinance_assets: tuple[YFinanceFuturesSpec, ...],
    intervals: tuple[str, ...],
    start_date: str,
    end_date: str,
    dry_run: bool,
    estimate_only: bool,
    max_cost_usd: float,
    databento_api_key: str | None,
    overlap_bars: int,
    min_overlap_bars: int,
    max_close_diff_pct: float,
) -> bool:
    route = plan_auto_fresh_tail(
        futures_assets=futures_assets,
        yfinance_assets=yfinance_assets,
        end_date=end_date,
        overlap_bars=overlap_bars,
    )
    print_auto_route(route)

    success = True
    if route.databento_fallback_assets:
        databento_ok = run_databento(
            assets=route.databento_fallback_assets,
            intervals=intervals,
            start_date=start_date,
            end_date=end_date,
            dry_run=dry_run,
            estimate_only=estimate_only,
            max_cost_usd=max_cost_usd,
            api_key=databento_api_key,
        )
        success = databento_ok and success
    else:
        print("\nDATABENTO FALLBACK")
        print("-" * 70)
        print("Skipped: every selected asset is current or Yahoo-eligible.")

    if dry_run or estimate_only:
        print("\nYFINANCE RECENT-TAIL PLAN")
        print("-" * 70)
        print(
            "Skipped duplicate Yahoo planning in auto dry-run/estimate mode; "
            "Yahoo-eligible assets are listed in AUTO SOURCE ROUTING."
        )
        return success

    if route.databento_fallback_assets and not success:
        yfinance_after = route.yfinance_assets
    else:
        yfinance_after = yfinance_assets

    return (
        run_yfinance(
            assets=yfinance_after,
            intervals=intervals,
            end_date=end_date,
            dry_run=dry_run,
            estimate_only=estimate_only,
            overlap_bars=overlap_bars,
            min_overlap_bars=min_overlap_bars,
            max_close_diff_pct=max_close_diff_pct,
        )
        and success
    )


def print_status(
    *,
    providers: tuple[str, ...],
    twelve_assets: tuple[AssetSpec, ...],
    futures_assets: tuple[DatabentoFuturesSpec, ...],
    yfinance_assets: tuple[YFinanceFuturesSpec, ...],
    intervals: tuple[str, ...],
) -> None:
    status_providers = _expanded_inventory_providers(providers)
    if "twelvedata" in status_providers:
        print_twelve_status(assets=twelve_assets, intervals=intervals)
    if "databento" in status_providers:
        print("\nDATABENTO FUTURES STATUS")
        print("-" * 70)
        for asset in futures_assets:
            for interval in intervals:
                summary = existing_summary(
                    asset=asset,  # type: ignore[arg-type]
                    interval=interval,
                    base_dir=BASE_DIR,
                    provider=DATABENTO_PROVIDER,
                    market=DATABENTO_MARKET,
                )
                if summary.files == 0:
                    print(f"{asset.symbol:<3} {interval:<3} NOT FOUND")
                else:
                    print(
                        f"{asset.symbol:<3} {interval:<3} files={summary.files} "
                        f"rows={summary.rows_written} "
                        f"range={summary.first_ts} -> {summary.last_ts}"
                    )
    if "yfinance" in status_providers:
        print("\nYFINANCE FUTURES STATUS")
        print("-" * 70)
        for asset in yfinance_assets:
            for interval in intervals:
                summary = existing_summary(
                    asset=asset,  # type: ignore[arg-type]
                    interval=interval,
                    base_dir=BASE_DIR,
                    provider=YFINANCE_PROVIDER,
                    market=YFINANCE_MARKET,
                )
                if summary.files == 0:
                    print(f"{asset.symbol:<7} {interval:<3} NOT FOUND")
                else:
                    print(
                        f"{asset.symbol:<7} {interval:<3} files={summary.files} "
                        f"rows={summary.rows_written} "
                        f"range={summary.first_ts} -> {summary.last_ts}"
                    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Multi-Asset Data Pipeline - update normalized OHLCV bars",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python update_data.py --demo --dry-run --htf-only
  python update_data.py --status --core --htf-only
  python update_data.py --core --dry-run --htf-only
  python update_data.py --providers auto --core --htf-only
  python update_data.py --providers databento --core --estimate-only --htf-only
  python update_data.py --providers yfinance --core --dry-run --htf-only
  python update_data.py --providers twelvedata --assets EURUSD,USDJPY --htf-only
  python update_data.py --status --all
  python update_data.py --all --dry-run --htf-only  # audit every configured adapter
        """,
    )
    parser.add_argument(
        "--core",
        action="store_true",
        help=(
            "Select the intended production source mix: Yahoo recent tail first, "
            "Databento fallback for EURUSD/USDJPY/GC/CL/ES/NQ. Twelve Data "
            "remains manual fallback only."
        ),
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help=(
            "Free-source demo mode for non-crypto core assets. Uses Yahoo Finance "
            "standalone 1m data up to its retention window and derives 15m locally; "
            "Databento and Twelve Data are not used."
        ),
    )
    parser.add_argument(
        "--all", action="store_true", help="Select all providers and configured assets"
    )
    parser.add_argument(
        "--providers",
        default="",
        help="Comma-separated providers: auto,twelvedata,databento,yfinance",
    )
    parser.add_argument(
        "--assets", default="", help="Comma-separated Twelve Data canonical ids"
    )
    parser.add_argument(
        "--futures", default="", help="Comma-separated Databento futures ids"
    )
    parser.add_argument(
        "--yfinance-futures",
        default="",
        help="Comma-separated Yahoo Finance recent-tail futures ids",
    )
    parser.add_argument(
        "--intervals",
        default=",".join(DEFAULT_INTERVALS),
        help=(
            "Comma-separated intervals. For Databento, 1m is fetched and higher "
            "intervals are derived locally."
        ),
    )
    parser.add_argument("--htf-only", action="store_true", help="Use only 1m and 15m")
    parser.add_argument("--start-date", default="2021-01-01")
    parser.add_argument("--end-date", default="now")
    parser.add_argument(
        "--status", action="store_true", help="Show current status and exit"
    )
    parser.add_argument(
        "--skip-local-scan",
        action="store_true",
        help="Skip the local parquet inventory preflight before provider planning.",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview plan without writes"
    )
    parser.add_argument(
        "--estimate-only",
        action="store_true",
        help="Estimate requests/costs without writes",
    )
    parser.add_argument(
        "--discover-symbols",
        action="store_true",
        help="Run Twelve Data symbol discovery only",
    )
    parser.add_argument("--request-sleep", type=float, default=0.12)
    parser.add_argument("--api-key", default="", help="Twelve Data API key override")
    parser.add_argument(
        "--databento-api-key", default="", help="Databento API key override"
    )
    parser.add_argument(
        "--max-twelve-requests",
        type=int,
        default=750,
        help="Refuse Twelve fetches above this estimated request count. Use -1 to disable.",
    )
    parser.add_argument(
        "--max-databento-cost-usd",
        type=float,
        default=0.0,
        help="Required Databento cost ceiling for actual fetches.",
    )
    parser.add_argument(
        "--yfinance-overlap-bars",
        type=int,
        default=DEFAULT_OVERLAP_BARS,
        help="Number of recent Databento bars to fetch as Yahoo overlap.",
    )
    parser.add_argument(
        "--yfinance-min-overlap-bars",
        type=int,
        default=DEFAULT_MIN_OVERLAP_BARS,
        help="Minimum matched Databento/Yahoo overlap bars required.",
    )
    parser.add_argument(
        "--yfinance-max-close-diff-pct",
        type=float,
        default=DEFAULT_MAX_CLOSE_DIFF_PCT,
        help="Maximum allowed Databento/Yahoo overlap close difference percent.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    if args.demo and args.providers:
        parser.error("--demo chooses providers automatically; do not pass --providers.")
    if args.demo and args.all:
        parser.error("--demo and --all are mutually exclusive")
    if args.core and args.all:
        parser.error("--core and --all are mutually exclusive")
    if args.demo:
        providers = ("yfinance",)
    elif args.core and not args.providers and not args.all:
        providers = (AUTO_PROVIDER,)
    else:
        providers = provider_list(args.providers, all_providers=args.all)
    intervals = tuple(
        HTF_REQUIRED_INTERVALS if args.demo or args.htf_only else _interval_list(args.intervals)
    )
    unknown_intervals = [
        interval for interval in intervals if interval not in TWELVE_DATA_INTERVALS
    ]
    if unknown_intervals:
        raise SystemExit(f"Unsupported intervals: {unknown_intervals}")

    core_selection = args.core or args.demo

    if args.assets:
        twelve_asset_ids = _asset_id_list(args.assets)
    elif core_selection:
        twelve_asset_ids = CORE_TWELVE_ASSETS
    else:
        twelve_asset_ids = None
    twelve_assets = selected_assets(twelve_asset_ids)

    if args.futures:
        futures_asset_ids = tuple(part.upper() for part in _csv(args.futures))
    elif core_selection:
        futures_asset_ids = CORE_DATABENTO_FUTURES
    else:
        futures_asset_ids = None
    futures_assets = selected_databento_futures(futures_asset_ids)

    if args.yfinance_futures:
        yfinance_asset_ids = tuple(
            part.upper() for part in _csv(args.yfinance_futures)
        )
    elif core_selection:
        yfinance_asset_ids = CORE_YFINANCE_FUTURES
    else:
        yfinance_asset_ids = None
    yfinance_assets = selected_yfinance_futures(yfinance_asset_ids)

    if args.demo:
        demo_start, demo_end = resolve_yfinance_demo_window(
            interval="1m",
            target_end=_resolve_end(args.end_date),
        )
        args.start_date = _format_cli_datetime(demo_start)
        args.end_date = _format_cli_datetime(demo_end)

    start_time = datetime.now(timezone.utc)
    print("\n" + "=" * 70)
    print("MULTI-ASSET DATA PIPELINE")
    print("=" * 70)
    print(f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"Base dir: {BASE_DIR}")
    print(f"Providers: {', '.join(providers)}")
    print(f"Intervals: {', '.join(intervals)}")
    if args.demo:
        print(
            "Demo source mix: Yahoo Finance standalone 1m for "
            "EURUSD,USDJPY,GC,CL,ES,NQ; 15m is derived locally. "
            "Databento and Twelve Data are disabled."
        )
    elif args.core:
        print(
            "Core source mix: Yahoo recent-tail first for EURUSD,USDJPY,GC,CL,ES,NQ; "
            "Databento is fallback when Yahoo cannot cover the missing span; "
            "Twelve Data is manual fallback only"
        )
    sys.stdout.flush()

    inventory_rows: list[LocalInventoryRow] | None = None
    if not args.skip_local_scan:
        inventory_rows = build_local_inventory(
            providers=providers,
            twelve_assets=twelve_assets,
            futures_assets=futures_assets,
            yfinance_assets=yfinance_assets,
            intervals=intervals,
            start_date=args.start_date,
            end_date=args.end_date,
        )
        print_local_inventory(inventory_rows)
        sys.stdout.flush()

    if args.status:
        if inventory_rows is None:
            print_status(
                providers=providers,
                twelve_assets=twelve_assets,
                futures_assets=futures_assets,
                yfinance_assets=yfinance_assets,
                intervals=intervals,
            )
        return 0

    if args.discover_symbols and providers != ("twelvedata",):
        print(
            "ERROR: --discover-symbols is only for Twelve Data; use --providers twelvedata."
        )
        return 2

    if args.discover_symbols:
        key = configured_api_key(args.api_key or None)
        if not key:
            print("ERROR: TWELVE_DATA_API_KEY is missing.")
            return 1
        client = TwelveDataClient(key)
        payload = discover_twelve_symbols(client, twelve_assets)
        for symbol, result in payload.items():
            matches = result.get("data") or []
            print(f"{symbol}: matches={len(matches)}")
        return 0

    success = True
    if "twelvedata" in providers:
        success = (
            run_twelve(
                assets=twelve_assets,
                intervals=intervals,
                start_date=args.start_date,
                end_date=args.end_date,
                dry_run=args.dry_run,
                estimate_only=args.estimate_only,
                max_requests=args.max_twelve_requests,
                request_sleep=args.request_sleep,
                api_key=args.api_key or None,
            )
            and success
        )

    if "databento" in providers:
        success = (
            run_databento(
                assets=futures_assets,
                intervals=intervals,
                start_date=args.start_date,
                end_date=args.end_date,
                dry_run=args.dry_run,
                estimate_only=args.estimate_only,
                max_cost_usd=args.max_databento_cost_usd,
                api_key=args.databento_api_key or None,
            )
            and success
        )

    if "yfinance" in providers:
        if args.demo:
            success = (
                run_yfinance_demo(
                    assets=yfinance_assets,
                    intervals=intervals,
                    start_date=args.start_date,
                    end_date=args.end_date,
                    dry_run=args.dry_run,
                    estimate_only=args.estimate_only,
                )
                and success
            )
        else:
            success = (
                run_yfinance(
                    assets=yfinance_assets,
                    intervals=intervals,
                    end_date=args.end_date,
                    dry_run=args.dry_run,
                    estimate_only=args.estimate_only,
                    overlap_bars=args.yfinance_overlap_bars,
                    min_overlap_bars=args.yfinance_min_overlap_bars,
                    max_close_diff_pct=args.yfinance_max_close_diff_pct,
                )
                and success
            )

    if AUTO_PROVIDER in providers:
        success = (
            run_auto(
                futures_assets=futures_assets,
                yfinance_assets=yfinance_assets,
                intervals=intervals,
                start_date=args.start_date,
                end_date=args.end_date,
                dry_run=args.dry_run,
                estimate_only=args.estimate_only,
                max_cost_usd=args.max_databento_cost_usd,
                databento_api_key=args.databento_api_key or None,
                overlap_bars=args.yfinance_overlap_bars,
                min_overlap_bars=args.yfinance_min_overlap_bars,
                max_close_diff_pct=args.yfinance_max_close_diff_pct,
            )
            and success
        )

    end_time = datetime.now(timezone.utc)
    print("\n" + "=" * 70)
    print("MULTI-ASSET PIPELINE COMPLETE")
    print("=" * 70)
    print(f"Duration: {(end_time - start_time).total_seconds():.1f} seconds")
    print(f"Status: {'SUCCESS' if success else 'ERRORS OCCURRED'}")
    print("=" * 70 + "\n")
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
