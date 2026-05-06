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
        AssetSpec,
        DatabentoFuturesSpec,
        selected_assets,
        selected_databento_futures,
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
        configured_api_key,
        existing_summary,
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
except ImportError:  # pragma: no cover - script execution from fetchingMultiAsset/
    from aggregate_ohlcv import write_aggregate  # type: ignore
    from asset_config import (  # type: ignore
        DATABENTO_MARKET,
        DATABENTO_PROVIDER,
        DEFAULT_INTERVALS,
        HTF_REQUIRED_INTERVALS,
        INTERVAL_MS,
        TWELVE_DATA_INTERVALS,
        AssetSpec,
        DatabentoFuturesSpec,
        selected_assets,
        selected_databento_futures,
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
        configured_api_key,
        existing_summary,
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


BASE_DIR = Path(__file__).resolve().parent
PROVIDERS = ("twelvedata", "databento")
CORE_TWELVE_ASSETS = ("EURUSD", "USDJPY")
CORE_DATABENTO_FUTURES = ("EURUSD", "USDJPY", "GC", "CL", "ES", "NQ")


@dataclass(frozen=True)
class TwelveRequestEstimate:
    asset: str
    interval: str
    fetch_start: datetime | None
    fetch_end: datetime | None
    estimated_requests: int
    local_last_ts: datetime | None


def _csv(raw: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def provider_list(raw: str, *, all_providers: bool = False) -> tuple[str, ...]:
    if all_providers:
        return PROVIDERS
    if not raw:
        return ("twelvedata",)
    providers = tuple(provider.lower() for provider in _csv(raw))
    unknown = [provider for provider in providers if provider not in PROVIDERS]
    if unknown:
        raise argparse.ArgumentTypeError(
            f"Unknown providers: {unknown}. Known providers: {', '.join(PROVIDERS)}"
        )
    return providers


def _resolve_end(end_date: str | datetime) -> datetime:
    return min(parse_datetime(end_date), datetime.now(timezone.utc))


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


def print_status(
    *,
    providers: tuple[str, ...],
    twelve_assets: tuple[AssetSpec, ...],
    futures_assets: tuple[DatabentoFuturesSpec, ...],
    intervals: tuple[str, ...],
) -> None:
    if "twelvedata" in providers:
        print_twelve_status(assets=twelve_assets, intervals=intervals)
    if "databento" in providers:
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


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Multi-Asset Data Pipeline - update normalized OHLCV bars",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python update_data.py --status --core --htf-only
  python update_data.py --core --dry-run --htf-only
  python update_data.py --providers databento --core --estimate-only --htf-only
  python update_data.py --providers twelvedata --assets EURUSD,USDJPY --htf-only
  python update_data.py --status --all
  python update_data.py --all --dry-run --htf-only  # audit every configured adapter
        """,
    )
    parser.add_argument(
        "--core",
        action="store_true",
        help=(
            "Select the intended production source mix: Databento "
            "EURUSD/USDJPY/GC/CL/ES/NQ. Twelve Data remains manual fallback only."
        ),
    )
    parser.add_argument(
        "--all", action="store_true", help="Select all providers and configured assets"
    )
    parser.add_argument(
        "--providers",
        default="",
        help="Comma-separated providers: twelvedata,databento",
    )
    parser.add_argument(
        "--assets", default="", help="Comma-separated Twelve Data canonical ids"
    )
    parser.add_argument(
        "--futures", default="", help="Comma-separated Databento futures ids"
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
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    if args.core and args.all:
        parser.error("--core and --all are mutually exclusive")
    if args.core and not args.providers and not args.all:
        providers = ("databento",)
    else:
        providers = provider_list(args.providers, all_providers=args.all)
    intervals = tuple(
        HTF_REQUIRED_INTERVALS if args.htf_only else _interval_list(args.intervals)
    )
    unknown_intervals = [
        interval for interval in intervals if interval not in TWELVE_DATA_INTERVALS
    ]
    if unknown_intervals:
        raise SystemExit(f"Unsupported intervals: {unknown_intervals}")

    if args.assets:
        twelve_asset_ids = _asset_id_list(args.assets)
    elif args.core:
        twelve_asset_ids = CORE_TWELVE_ASSETS
    else:
        twelve_asset_ids = None
    twelve_assets = selected_assets(twelve_asset_ids)

    if args.futures:
        futures_asset_ids = tuple(part.upper() for part in _csv(args.futures))
    elif args.core:
        futures_asset_ids = CORE_DATABENTO_FUTURES
    else:
        futures_asset_ids = None
    futures_assets = selected_databento_futures(futures_asset_ids)

    start_time = datetime.now(timezone.utc)
    print("\n" + "=" * 70)
    print("MULTI-ASSET DATA PIPELINE")
    print("=" * 70)
    print(f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"Base dir: {BASE_DIR}")
    print(f"Providers: {', '.join(providers)}")
    print(f"Intervals: {', '.join(intervals)}")
    if args.core:
        print(
            "Core source mix: Databento EURUSD,USDJPY,GC,CL,ES,NQ; "
            "Twelve Data is fallback only"
        )
    sys.stdout.flush()

    if args.status:
        print_status(
            providers=providers,
            twelve_assets=twelve_assets,
            futures_assets=futures_assets,
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
