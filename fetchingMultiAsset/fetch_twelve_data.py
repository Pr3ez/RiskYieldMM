#!/usr/bin/env python3
"""Twelve Data OHLCV fetcher for the multi-asset source layer."""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import polars as pl
import requests

try:
    from .asset_config import (
        ASSETS,
        DEFAULT_END_DATE,
        DEFAULT_INTERVALS,
        DEFAULT_MARKET,
        DEFAULT_PROVIDER,
        DEFAULT_START_DATE,
        INTERVAL_MS,
        TWELVE_DATA_INTERVALS,
        AssetSpec,
        selected_assets,
    )
except ImportError:  # pragma: no cover - script execution from fetchingMultiAsset/
    from asset_config import (  # type: ignore
        ASSETS,
        DEFAULT_END_DATE,
        DEFAULT_INTERVALS,
        DEFAULT_MARKET,
        DEFAULT_PROVIDER,
        DEFAULT_START_DATE,
        INTERVAL_MS,
        TWELVE_DATA_INTERVALS,
        AssetSpec,
        selected_assets,
    )


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
PROGRESS_FILE = BASE_DIR / ".fetch_progress.json"
LOCAL_SECRET_FILES = (
    BASE_DIR / "local_secrets.env",
    BASE_DIR / ".env",
    PROJECT_ROOT / ".env.local",
    PROJECT_ROOT / ".env",
)
TIMESTAMP_DTYPE = pl.Datetime("ms", "UTC")
OHLCV_COLUMNS = [
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "turnover",
    "interval",
]
OHLCV_SCHEMA = {
    "timestamp": TIMESTAMP_DTYPE,
    "open": pl.Float64,
    "high": pl.Float64,
    "low": pl.Float64,
    "close": pl.Float64,
    "volume": pl.Float64,
    "turnover": pl.Float64,
    "interval": pl.String,
}

MAX_BARS_PER_REQUEST = 5000
DEFAULT_CHUNK_SIZE = 1000
DEFAULT_REQUEST_SLEEP = 0.12
TIME_SERIES_URL = "https://api.twelvedata.com/time_series"
SYMBOL_SEARCH_URL = "https://api.twelvedata.com/symbol_search"


class TwelveDataError(RuntimeError):
    """Raised when Twelve Data returns an API-level error payload."""


@dataclass(frozen=True)
class FetchSummary:
    asset: str
    interval: str
    rows_fetched: int
    rows_written: int
    files: int
    first_ts: datetime | None
    last_ts: datetime | None
    status: str


@dataclass(frozen=True)
class WriteSummary:
    rows_written: int
    files: int
    first_ts: datetime | None
    last_ts: datetime | None


def _empty_ohlcv_frame() -> pl.DataFrame:
    return pl.DataFrame(schema=OHLCV_SCHEMA)


def _strip_env_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def load_local_env_file(path: Path, *, override: bool = False) -> dict[str, str]:
    """Load simple KEY=VALUE pairs from a local secrets file.

    This intentionally supports only the small `.env` subset we need for API
    keys. Existing process environment variables win by default.
    """
    loaded: dict[str, str] = {}
    if not path.exists():
        return loaded

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = _strip_env_quotes(value)
        if not key:
            continue
        if override or key not in os.environ:
            os.environ[key] = value
        loaded[key] = value

    return loaded


def load_local_secret_files(
    paths: tuple[Path, ...] = LOCAL_SECRET_FILES,
    *,
    override: bool = False,
) -> dict[str, str]:
    """Load ignored local secret files in priority order."""
    loaded: dict[str, str] = {}
    for path in paths:
        loaded.update(load_local_env_file(path, override=override))
    return loaded


def configured_api_key(cli_api_key: str | None = None) -> str | None:
    """Return Twelve Data API key from CLI, environment, or ignored local files."""
    if cli_api_key:
        return cli_api_key
    if os.getenv("TWELVE_DATA_API_KEY"):
        return os.getenv("TWELVE_DATA_API_KEY")
    load_local_secret_files()
    return os.getenv("TWELVE_DATA_API_KEY")


def _normalize_timestamp_dtype(df: pl.DataFrame) -> pl.DataFrame:
    if "timestamp" not in df.columns:
        return df
    return df.with_columns(pl.col("timestamp").cast(TIMESTAMP_DTYPE)).select(
        OHLCV_COLUMNS
    )


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_datetime(value: str | datetime) -> datetime:
    """Parse configured date strings into UTC datetimes."""
    if isinstance(value, datetime):
        return _as_utc(value)

    raw = str(value).strip()
    if raw.lower() in {"now", "today"}:
        return datetime.now(timezone.utc)

    normalized = raw.replace("Z", "+00:00")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", normalized):
        dt = datetime.strptime(normalized, "%Y-%m-%d")
    else:
        dt = datetime.fromisoformat(normalized)
    return _as_utc(dt)


def format_twelve_datetime(dt: datetime) -> str:
    return _as_utc(dt).strftime("%Y-%m-%d %H:%M:%S")


def _parse_value_datetime(value: str) -> datetime:
    return parse_datetime(value)


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    return float(value)


def twelve_values_to_ohlcv(
    values: list[dict[str, Any]], interval_label: str
) -> pl.DataFrame:
    """Convert Twelve Data `values` rows into the strict Bybit OHLCV schema."""
    rows: list[dict[str, Any]] = []
    for row in values:
        dt_raw = row.get("datetime")
        if not dt_raw:
            continue
        rows.append(
            {
                "timestamp": _parse_value_datetime(str(dt_raw)),
                "open": _to_float(row.get("open")),
                "high": _to_float(row.get("high")),
                "low": _to_float(row.get("low")),
                "close": _to_float(row.get("close")),
                "volume": _to_float(row.get("volume")),
                "turnover": None,
                "interval": interval_label,
            }
        )

    if not rows:
        return _empty_ohlcv_frame()

    df = pl.DataFrame(rows).with_columns(
        [
            pl.col("timestamp").cast(TIMESTAMP_DTYPE),
            pl.col("open").cast(pl.Float64),
            pl.col("high").cast(pl.Float64),
            pl.col("low").cast(pl.Float64),
            pl.col("close").cast(pl.Float64),
            pl.col("volume").cast(pl.Float64),
            pl.col("turnover").cast(pl.Float64),
            pl.col("interval").cast(pl.String),
        ]
    )
    df = df.drop_nulls(subset=["timestamp", "open", "high", "low", "close"])
    df = df.unique(subset=["timestamp"], keep="last").sort("timestamp")
    return _normalize_timestamp_dtype(df)


class TwelveDataClient:
    """Small REST client with explicit API error handling."""

    def __init__(
        self,
        api_key: str,
        *,
        session: requests.Session | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.api_key = api_key
        self.session = session or requests.Session()
        self.timeout = timeout

    def time_series(
        self,
        *,
        symbol: str,
        interval: str,
        start: datetime,
        end: datetime,
        outputsize: int = MAX_BARS_PER_REQUEST,
    ) -> list[dict[str, Any]]:
        params = {
            "symbol": symbol,
            "interval": interval,
            "start_date": format_twelve_datetime(start),
            "end_date": format_twelve_datetime(end),
            "timezone": "UTC",
            "order": "ASC",
            "format": "JSON",
            "outputsize": str(outputsize),
            "apikey": self.api_key,
        }
        response = self.session.get(
            TIME_SERIES_URL, params=params, timeout=self.timeout
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") == "error":
            message = payload.get("message") or payload
            raise TwelveDataError(str(message))
        values = payload.get("values")
        if values is None:
            return []
        if not isinstance(values, list):
            raise TwelveDataError(
                f"Unexpected values payload for {symbol}: {type(values)!r}"
            )
        return values

    def symbol_search(self, symbol: str) -> dict[str, Any]:
        params = {"symbol": symbol, "apikey": self.api_key}
        response = self.session.get(
            SYMBOL_SEARCH_URL, params=params, timeout=self.timeout
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") == "error":
            message = payload.get("message") or payload
            raise TwelveDataError(str(message))
        return payload


def save_progress(
    *,
    asset: AssetSpec,
    interval: str,
    last_ts: datetime | None,
    status: str,
    provider: str = DEFAULT_PROVIDER,
    progress_file: Path = PROGRESS_FILE,
) -> None:
    progress: dict[str, Any] = {}
    if progress_file.exists():
        try:
            progress = json.loads(progress_file.read_text(encoding="utf-8"))
        except Exception:
            progress = {}

    key = f"{provider}_{asset.symbol}_ohlcv_{interval}"
    progress[key] = {
        "last_timestamp_ms": (
            int(_as_utc(last_ts).timestamp() * 1000) if last_ts is not None else None
        ),
        "last_update": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "source_symbol": asset.provider_symbol,
    }
    progress_file.parent.mkdir(parents=True, exist_ok=True)
    progress_file.write_text(json.dumps(progress, indent=2), encoding="utf-8")


def output_dir_for_interval(
    base_dir: Path,
    interval: str,
    *,
    provider: str = DEFAULT_PROVIDER,
    market: str = DEFAULT_MARKET,
) -> Path:
    return base_dir / f"sorted-{interval}-{provider}-{market}"


def batch_prefix(asset: AssetSpec, *, provider: str = DEFAULT_PROVIDER) -> str:
    return f"{asset.slug}_{provider}_sorted_batch_"


def _list_existing_files(output_dir: Path, prefix: str) -> list[tuple[int, Path, int]]:
    if not output_dir.exists():
        return []
    files: list[tuple[int, Path, int]] = []
    rx = re.compile(rf"^{re.escape(prefix)}(\d+)\.parquet$")
    for path in output_dir.iterdir():
        match = rx.match(path.name)
        if match:
            idx = match.group(1)
            files.append((int(idx), path, len(idx)))
    return sorted(files, key=lambda item: item[0])


def _read_timestamp_summary(
    files: list[Path],
) -> tuple[int, datetime | None, datetime | None]:
    try:
        import pyarrow.parquet as pq

        rows = 0
        non_empty: list[Path] = []
        for path in files:
            row_count = int(pq.ParquetFile(path).metadata.num_rows)
            rows += row_count
            if row_count > 0:
                non_empty.append(path)
        if not non_empty:
            return rows, None, None
        first_df = pl.read_parquet(non_empty[0], columns=["timestamp"])
        last_df = (
            first_df
            if non_empty[-1] == non_empty[0]
            else pl.read_parquet(non_empty[-1], columns=["timestamp"])
        )
        return (
            rows,
            _as_utc(first_df["timestamp"].min()),
            _as_utc(last_df["timestamp"].max()),
        )
    except Exception:
        pass

    rows = 0
    first_ts = None
    last_ts = None
    for path in files:
        df = pl.read_parquet(path, columns=["timestamp"])
        if df.height == 0:
            continue
        rows += df.height
        file_first = _as_utc(df["timestamp"].min())
        file_last = _as_utc(df["timestamp"].max())
        if first_ts is None or file_first < first_ts:
            first_ts = file_first
        if last_ts is None or file_last > last_ts:
            last_ts = file_last
    return rows, first_ts, last_ts


def existing_summary(
    *,
    asset: AssetSpec,
    interval: str,
    base_dir: Path = BASE_DIR,
    provider: str = DEFAULT_PROVIDER,
    market: str = DEFAULT_MARKET,
) -> WriteSummary:
    output_dir = output_dir_for_interval(
        base_dir, interval, provider=provider, market=market
    )
    files = [
        path
        for _, path, _ in _list_existing_files(
            output_dir, batch_prefix(asset, provider=provider)
        )
    ]
    rows, first_ts, last_ts = _read_timestamp_summary(files)
    return WriteSummary(
        rows_written=rows,
        files=len(files),
        first_ts=first_ts,
        last_ts=last_ts,
    )


def _write_chunk(path: Path, df: pl.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _normalize_timestamp_dtype(df).write_parquet(path)


def _resolve_resume_chunk_size(reference_rows: int, requested_chunk_size: int) -> int:
    """Avoid locking future appends to tiny one-off probe chunks."""
    if reference_rows <= 0:
        return requested_chunk_size
    if reference_rows < max(2, requested_chunk_size // 2):
        return requested_chunk_size
    return reference_rows


def append_ohlcv_batches(
    df: pl.DataFrame,
    *,
    asset: AssetSpec,
    interval: str,
    base_dir: Path = BASE_DIR,
    provider: str = DEFAULT_PROVIDER,
    market: str = DEFAULT_MARKET,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> WriteSummary:
    """Append sorted OHLCV rows to Bybit-style batch parquet files."""
    df = _normalize_timestamp_dtype(df)
    if df.height == 0:
        return existing_summary(
            asset=asset,
            interval=interval,
            base_dir=base_dir,
            provider=provider,
            market=market,
        )

    output_dir = output_dir_for_interval(
        base_dir, interval, provider=provider, market=market
    )
    prefix = batch_prefix(asset, provider=provider)
    existing = _list_existing_files(output_dir, prefix)

    if existing:
        last_ts = existing_summary(
            asset=asset,
            interval=interval,
            base_dir=base_dir,
            provider=provider,
            market=market,
        ).last_ts
        if last_ts is not None:
            df = df.filter(pl.col("timestamp") > last_ts)
    if df.height == 0:
        return existing_summary(
            asset=asset,
            interval=interval,
            base_dir=base_dir,
            provider=provider,
            market=market,
        )

    df = _normalize_timestamp_dtype(
        df.unique(subset=["timestamp"], keep="last").sort("timestamp")
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    if not existing:
        written = 0
        idx = 0
        while written < df.height:
            chunk = df.slice(written, chunk_size)
            _write_chunk(output_dir / f"{prefix}{idx:06d}.parquet", chunk)
            written += chunk.height
            idx += 1
        return existing_summary(
            asset=asset,
            interval=interval,
            base_dir=base_dir,
            provider=provider,
            market=market,
        )

    first_idx, first_path, _ = existing[0]
    del first_idx
    reference_rows = pl.read_parquet(first_path, columns=["timestamp"]).height
    resolved_chunk_size = _resolve_resume_chunk_size(reference_rows, chunk_size)
    last_idx, last_path, pad_digits = existing[-1]
    pad_width = max(6, pad_digits)
    last_rows = pl.read_parquet(last_path, columns=["timestamp"]).height
    consumed = 0

    if last_rows < resolved_chunk_size:
        need = min(resolved_chunk_size - last_rows, df.height)
        if need > 0:
            combined = pl.concat(
                [
                    _normalize_timestamp_dtype(pl.read_parquet(last_path)),
                    df.slice(0, need),
                ]
            )
            combined = _normalize_timestamp_dtype(
                combined.unique(subset=["timestamp"], keep="last").sort("timestamp")
            )
            _write_chunk(last_path, combined)
            consumed = need

    remaining = df.slice(consumed)
    if remaining.height > 0:
        next_idx = last_idx + 1
        written = 0
        while written < remaining.height:
            chunk = remaining.slice(written, resolved_chunk_size)
            _write_chunk(
                output_dir / f"{prefix}{next_idx:0{pad_width}d}.parquet", chunk
            )
            written += chunk.height
            next_idx += 1

    return existing_summary(
        asset=asset,
        interval=interval,
        base_dir=base_dir,
        provider=provider,
        market=market,
    )


def fetch_asset_interval(
    *,
    asset: AssetSpec,
    interval: str,
    client: TwelveDataClient,
    start_date: str | datetime = DEFAULT_START_DATE,
    end_date: str | datetime = DEFAULT_END_DATE,
    base_dir: Path = BASE_DIR,
    request_sleep: float = DEFAULT_REQUEST_SLEEP,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    progress_file: Path | None = None,
) -> FetchSummary:
    if interval not in TWELVE_DATA_INTERVALS:
        raise KeyError(f"Unsupported interval {interval!r}")

    requested_start = parse_datetime(start_date)
    requested_end = min(parse_datetime(end_date), datetime.now(timezone.utc))
    step_ms = INTERVAL_MS[interval]
    step = timedelta(milliseconds=step_ms)
    current_summary = existing_summary(
        asset=asset, interval=interval, base_dir=base_dir
    )
    resolved_progress_file = progress_file or base_dir / ".fetch_progress.json"
    start = requested_start
    if current_summary.last_ts is not None:
        start = max(start, current_summary.last_ts + step)

    if start > requested_end:
        save_progress(
            asset=asset,
            interval=interval,
            last_ts=current_summary.last_ts,
            status="up-to-date",
            progress_file=resolved_progress_file,
        )
        return FetchSummary(
            asset=asset.symbol,
            interval=interval,
            rows_fetched=0,
            rows_written=0,
            files=current_summary.files,
            first_ts=current_summary.first_ts,
            last_ts=current_summary.last_ts,
            status="up-to-date",
        )

    provider_interval = TWELVE_DATA_INTERVALS[interval]
    max_window = step * (MAX_BARS_PER_REQUEST - 1)
    cursor = start
    rows_fetched = 0
    rows_before = current_summary.rows_written
    latest_seen = current_summary.last_ts

    while cursor <= requested_end:
        window_end = min(cursor + max_window, requested_end)
        values = client.time_series(
            symbol=asset.provider_symbol,
            interval=provider_interval,
            start=cursor,
            end=window_end,
            outputsize=MAX_BARS_PER_REQUEST,
        )
        df = twelve_values_to_ohlcv(values, interval)
        if df.height > 0:
            df = df.filter(
                (pl.col("timestamp") >= cursor) & (pl.col("timestamp") <= window_end)
            )
        if df.height > 0:
            rows_fetched += df.height
            append_ohlcv_batches(
                df,
                asset=asset,
                interval=interval,
                base_dir=base_dir,
                chunk_size=chunk_size,
            )
            latest_seen = _as_utc(df["timestamp"].max())
            save_progress(
                asset=asset,
                interval=interval,
                last_ts=latest_seen,
                status="partial",
                progress_file=resolved_progress_file,
            )

        cursor = window_end + step
        if request_sleep > 0:
            time.sleep(request_sleep)

    final_summary = existing_summary(asset=asset, interval=interval, base_dir=base_dir)
    rows_written = max(0, final_summary.rows_written - rows_before)
    save_progress(
        asset=asset,
        interval=interval,
        last_ts=final_summary.last_ts or latest_seen,
        status="complete",
        progress_file=resolved_progress_file,
    )
    return FetchSummary(
        asset=asset.symbol,
        interval=interval,
        rows_fetched=rows_fetched,
        rows_written=rows_written,
        files=final_summary.files,
        first_ts=final_summary.first_ts,
        last_ts=final_summary.last_ts,
        status="complete",
    )


def discover_symbols(
    client: TwelveDataClient, assets: tuple[AssetSpec, ...]
) -> dict[str, Any]:
    return {
        asset.symbol: client.symbol_search(asset.provider_symbol) for asset in assets
    }


def _interval_list(raw: str | None) -> tuple[str, ...]:
    if raw is None:
        return DEFAULT_INTERVALS
    intervals = tuple(part.strip() for part in raw.split(",") if part.strip())
    unknown = [
        interval for interval in intervals if interval not in TWELVE_DATA_INTERVALS
    ]
    if unknown:
        known = ", ".join(TWELVE_DATA_INTERVALS)
        raise argparse.ArgumentTypeError(
            f"Unsupported intervals: {unknown}. Known: {known}"
        )
    return intervals


def _asset_id_list(raw: str | None) -> tuple[str, ...] | None:
    if raw is None:
        return None
    return tuple(part.strip().upper() for part in raw.split(",") if part.strip())


def print_status(
    *,
    assets: tuple[AssetSpec, ...] = ASSETS,
    intervals: tuple[str, ...] = DEFAULT_INTERVALS,
    base_dir: Path = BASE_DIR,
) -> None:
    print("\n" + "=" * 70)
    print("MULTI-ASSET DATA STATUS")
    print("=" * 70)
    print(f"Base dir: {base_dir}")
    print(f"Provider root: {DEFAULT_PROVIDER}-{DEFAULT_MARKET}")
    print(
        "Parquet contract: timestamp, open, high, low, close, volume, turnover, interval"
    )

    now = datetime.now(timezone.utc)
    for asset in assets:
        print("\n" + "#" * 70)
        print(f"ASSET: {asset.symbol} ({asset.display_name})")
        print(f"Source symbol: {asset.provider_symbol}")
        for interval in intervals:
            summary = existing_summary(
                asset=asset, interval=interval, base_dir=base_dir
            )
            print(f"\n{interval} OHLCV:")
            if summary.files == 0:
                print("  Status: NOT FOUND")
                continue
            stale_hours = (
                (now - summary.last_ts).total_seconds() / 3600
                if summary.last_ts is not None
                else float("inf")
            )
            print(f"  Files: {summary.files:,}")
            print(f"  Rows: {summary.rows_written:,}")
            print(f"  Range: {summary.first_ts} -> {summary.last_ts}")
            print(f"  Staleness: {stale_hours:.2f} hours")

    print("=" * 70 + "\n")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Multi-Asset Data Pipeline - Twelve Data OHLCV Fetcher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python fetch_twelve_data.py --status
  python fetch_twelve_data.py --dry-run
  TWELVE_DATA_API_KEY=... python fetch_twelve_data.py --intervals 1m,15m
  TWELVE_DATA_API_KEY=... python fetch_twelve_data.py --discover-symbols
        """,
    )
    parser.add_argument("--api-key", default=None)
    parser.add_argument(
        "--assets",
        type=_asset_id_list,
        default=None,
        help="Comma-separated canonical ids",
    )
    parser.add_argument(
        "--intervals",
        type=_interval_list,
        default=DEFAULT_INTERVALS,
        help="Comma-separated intervals",
    )
    parser.add_argument("--start-date", default=DEFAULT_START_DATE)
    parser.add_argument("--end-date", default=DEFAULT_END_DATE)
    parser.add_argument(
        "--status", action="store_true", help="Show local source status and exit"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview fetch plan without API calls or writes",
    )
    parser.add_argument(
        "--discover-symbols",
        action="store_true",
        help="Run provider symbol search for configured assets",
    )
    parser.add_argument("--request-sleep", type=float, default=DEFAULT_REQUEST_SLEEP)
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    assets = selected_assets(args.assets)
    intervals = args.intervals

    if args.status:
        print_status(assets=assets, intervals=intervals)
        return 0

    print("\n" + "=" * 70)
    print("MULTI-ASSET TWELVE DATA FETCHER")
    print("=" * 70)
    print(f"Assets: {', '.join(asset.symbol for asset in assets)}")
    print(f"Intervals: {', '.join(intervals)}")
    print(f"Date range: {args.start_date} -> {args.end_date}")
    print(f"Output root: {BASE_DIR}")

    if args.dry_run:
        print("\nDRY RUN")
        for asset in assets:
            for interval in intervals:
                out_dir = output_dir_for_interval(BASE_DIR, interval)
                prefix = batch_prefix(asset)
                print(
                    f"  {asset.symbol:<7} {interval:<3} "
                    f"{asset.provider_symbol:<10} -> {out_dir.name}/{prefix}*.parquet"
                )
        return 0

    api_key = configured_api_key(args.api_key)
    if not api_key:
        print("ERROR: set TWELVE_DATA_API_KEY or pass --api-key before fetching.")
        print(
            "You can store it in ignored local file: "
            "fetchingMultiAsset/local_secrets.env"
        )
        return 2

    client = TwelveDataClient(api_key)

    if args.discover_symbols:
        payload = discover_symbols(client, assets)
        print(json.dumps(payload, indent=2))
        return 0

    failures = 0
    for asset in assets:
        print("\n" + "#" * 70)
        print(
            f"FETCHING {asset.symbol} from Twelve Data symbol {asset.provider_symbol}"
        )
        print("#" * 70)
        for interval in intervals:
            try:
                summary = fetch_asset_interval(
                    asset=asset,
                    interval=interval,
                    client=client,
                    start_date=args.start_date,
                    end_date=args.end_date,
                    request_sleep=args.request_sleep,
                    chunk_size=args.chunk_size,
                )
                print(
                    f"{asset.symbol} {interval}: {summary.status}, "
                    f"fetched={summary.rows_fetched:,}, written={summary.rows_written:,}, "
                    f"range={summary.first_ts} -> {summary.last_ts}"
                )
            except Exception as exc:
                failures += 1
                print(f"ERROR: {asset.symbol} {interval} failed: {exc}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
