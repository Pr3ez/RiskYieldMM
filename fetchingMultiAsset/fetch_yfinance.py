"""Yahoo Finance recent-tail fetch and Databento continuation checks."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import polars as pl

try:
    from .asset_config import (
        DATABENTO_MARKET,
        DATABENTO_PROVIDER,
        INTERVAL_MS,
        YFINANCE_MARKET,
        YFINANCE_PROVIDER,
        YFinanceFuturesSpec,
        selected_yfinance_futures,
    )
    from .fetch_twelve_data import (
        OHLCV_COLUMNS,
        TIMESTAMP_DTYPE,
        append_ohlcv_batches,
        batch_prefix,
        existing_summary,
        output_dir_for_interval,
        replace_ohlcv_window,
    )
except ImportError:  # pragma: no cover - script execution from fetchingMultiAsset/
    from asset_config import (  # type: ignore
        DATABENTO_MARKET,
        DATABENTO_PROVIDER,
        INTERVAL_MS,
        YFINANCE_MARKET,
        YFINANCE_PROVIDER,
        YFinanceFuturesSpec,
        selected_yfinance_futures,
    )
    from fetch_twelve_data import (  # type: ignore
        OHLCV_COLUMNS,
        TIMESTAMP_DTYPE,
        append_ohlcv_batches,
        batch_prefix,
        existing_summary,
        output_dir_for_interval,
        replace_ohlcv_window,
    )


BASE_DIR = Path(__file__).resolve().parent
YFINANCE_INTERVAL_LIMITS = {
    "1m": timedelta(days=7),
    "15m": timedelta(days=60),
}
DEFAULT_OVERLAP_BARS = 120
DEFAULT_MIN_OVERLAP_BARS = 30
DEFAULT_MAX_CLOSE_DIFF_PCT = 0.10


def _empty_ohlcv_frame() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "timestamp": TIMESTAMP_DTYPE,
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume": pl.Float64,
            "turnover": pl.Float64,
            "interval": pl.String,
        }
    )


@dataclass(frozen=True)
class YFinanceTailPlan:
    asset: str
    provider_symbol: str
    interval: str
    status: str
    databento_last_ts: datetime | None
    yfinance_last_ts: datetime | None
    fetch_start: datetime | None
    fetch_end: datetime | None
    reason: str

    @property
    def needs_fetch(self) -> bool:
        return self.status == "fetch"


@dataclass(frozen=True)
class YFinanceDemoPlan:
    asset: str
    provider_symbol: str
    interval: str
    status: str
    local_last_ts: datetime | None
    fetch_start: datetime | None
    fetch_end: datetime | None
    reason: str

    @property
    def needs_fetch(self) -> bool:
        return self.status == "fetch"


@dataclass(frozen=True)
class YFinanceDemoFetchResult:
    asset: str
    interval: str
    status: str
    fetched_rows: int
    files: int
    first_ts: datetime | None
    last_ts: datetime | None
    reason: str


@dataclass(frozen=True)
class ContinuationCheck:
    asset: str
    interval: str
    passed: bool
    overlap_rows: int
    tail_rows: int
    max_close_diff_pct: float | None
    median_close_diff_pct: float | None
    reason: str


def output_dir_for_yfinance_interval(base_dir: Path, interval: str) -> Path:
    return output_dir_for_interval(
        base_dir,
        interval,
        provider=YFINANCE_PROVIDER,
        market=YFINANCE_MARKET,
    )


def yfinance_batch_prefix(asset: YFinanceFuturesSpec) -> str:
    return batch_prefix(asset, provider=YFINANCE_PROVIDER)  # type: ignore[arg-type]


def _inverse_price_expr(column: str) -> pl.Expr:
    return (
        pl.when(pl.col(column).is_not_null() & (pl.col(column) != 0))
        .then(1.0 / pl.col(column))
        .otherwise(None)
    )


def _flatten_yfinance_columns(frame: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(frame.columns, pd.MultiIndex):
        return frame
    if len(frame.columns.levels) == 2:
        level0 = list(frame.columns.get_level_values(0))
        level1 = list(frame.columns.get_level_values(1))
        price_names = {"open", "high", "low", "close", "adj close", "volume"}
        if all(str(value).lower() in price_names for value in level0):
            frame = frame.copy()
            frame.columns = level0
            return frame
        frame = frame.copy()
        frame.columns = level1
        return frame
    frame = frame.copy()
    frame.columns = ["_".join(str(part) for part in col if part) for col in frame.columns]
    return frame


def yfinance_frame_to_ohlcv(
    frame: pd.DataFrame,
    interval_label: str,
    *,
    price_transform: str = "identity",
) -> pl.DataFrame:
    """Normalize a yfinance DataFrame into the Bybit-style OHLCV schema."""
    if frame.empty:
        return _empty_ohlcv_frame()

    pdf = _flatten_yfinance_columns(frame).copy()
    lower_to_original = {str(col).strip().lower(): col for col in pdf.columns}
    if isinstance(pdf.index, pd.DatetimeIndex):
        timestamps = pd.to_datetime(pdf.index, utc=True)
    else:
        timestamp_col = None
        for candidate in ("datetime", "date", "timestamp"):
            if candidate in lower_to_original:
                timestamp_col = lower_to_original[candidate]
                break
        if timestamp_col is None:
            raise ValueError("yfinance frame has no datetime index or timestamp column")
        timestamps = pd.to_datetime(pdf[timestamp_col], utc=True)

    required = {"open", "high", "low", "close", "volume"}
    missing = sorted(required - set(lower_to_original))
    if missing:
        raise ValueError(f"yfinance frame missing OHLCV columns: {missing}")

    normalized = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": pd.to_numeric(pdf[lower_to_original["open"]], errors="coerce"),
            "high": pd.to_numeric(pdf[lower_to_original["high"]], errors="coerce"),
            "low": pd.to_numeric(pdf[lower_to_original["low"]], errors="coerce"),
            "close": pd.to_numeric(pdf[lower_to_original["close"]], errors="coerce"),
            "volume": pd.to_numeric(pdf[lower_to_original["volume"]], errors="coerce"),
            "turnover": None,
            "interval": interval_label,
        }
    )
    df = (
        pl.from_pandas(normalized)
        .with_columns(
            [
                pl.col("timestamp").cast(TIMESTAMP_DTYPE),
                pl.col("open").cast(pl.Float64),
                pl.col("high").cast(pl.Float64),
                pl.col("low").cast(pl.Float64),
                pl.col("close").cast(pl.Float64),
                pl.col("volume").cast(pl.Float64),
                pl.col("turnover").cast(pl.Float64),
            ]
        )
        .drop_nulls(subset=["timestamp", "open", "high", "low", "close"])
        .select(OHLCV_COLUMNS)
        .unique(subset=["timestamp"], keep="last")
        .sort("timestamp")
    )
    if price_transform == "identity":
        return df
    if price_transform == "inverse":
        return df.with_columns(
            [
                _inverse_price_expr("open").alias("open"),
                _inverse_price_expr("low").alias("high"),
                _inverse_price_expr("high").alias("low"),
                _inverse_price_expr("close").alias("close"),
            ]
        ).select(OHLCV_COLUMNS)
    raise ValueError(f"Unsupported yfinance price transform {price_transform!r}")


def latest_complete_bar_start(
    interval: str,
    now: datetime | None = None,
) -> datetime:
    if interval not in INTERVAL_MS:
        raise KeyError(f"Unsupported interval {interval!r}")
    resolved_now = now or datetime.now(timezone.utc)
    if resolved_now.tzinfo is None:
        resolved_now = resolved_now.replace(tzinfo=timezone.utc)
    resolved_now = resolved_now.astimezone(timezone.utc)
    step_seconds = INTERVAL_MS[interval] // 1000
    floored = int(resolved_now.timestamp()) // step_seconds * step_seconds
    return datetime.fromtimestamp(floored - step_seconds, tz=timezone.utc)


def plan_yfinance_tail(
    *,
    asset: YFinanceFuturesSpec,
    interval: str = "1m",
    base_dir: Path = BASE_DIR,
    now: datetime | None = None,
    target_end: datetime | None = None,
    overlap_bars: int = DEFAULT_OVERLAP_BARS,
    max_gap: timedelta | None = None,
) -> YFinanceTailPlan:
    if interval not in YFINANCE_INTERVAL_LIMITS:
        return YFinanceTailPlan(
            asset=asset.symbol,
            provider_symbol=asset.provider_symbol,
            interval=interval,
            status="unsupported_interval",
            databento_last_ts=None,
            yfinance_last_ts=None,
            fetch_start=None,
            fetch_end=None,
            reason=f"Yahoo interval {interval!r} is not configured",
        )
    databento_summary = existing_summary(
        asset=asset,  # type: ignore[arg-type]
        interval=interval,
        base_dir=base_dir,
        provider=DATABENTO_PROVIDER,
        market=DATABENTO_MARKET,
    )
    yfinance_summary = existing_summary(
        asset=asset,  # type: ignore[arg-type]
        interval=interval,
        base_dir=base_dir,
        provider=YFINANCE_PROVIDER,
        market=YFINANCE_MARKET,
    )
    if databento_summary.last_ts is None:
        return YFinanceTailPlan(
            asset=asset.symbol,
            provider_symbol=asset.provider_symbol,
            interval=interval,
            status="no_databento_anchor",
            databento_last_ts=None,
            yfinance_last_ts=yfinance_summary.last_ts,
            fetch_start=None,
            fetch_end=None,
            reason="Databento local data is required before Yahoo can be used",
        )
    resolved_now = now or datetime.now(timezone.utc)
    if resolved_now.tzinfo is None:
        resolved_now = resolved_now.replace(tzinfo=timezone.utc)
    resolved_now = resolved_now.astimezone(timezone.utc)
    fetch_end = latest_complete_bar_start(interval, resolved_now)
    if target_end is not None:
        if target_end.tzinfo is None:
            target_end = target_end.replace(tzinfo=timezone.utc)
        target_end = target_end.astimezone(timezone.utc)
        step_seconds = INTERVAL_MS[interval] // 1000
        floored_target = (
            int(target_end.timestamp()) // step_seconds * step_seconds
        )
        fetch_end = min(
            fetch_end,
            datetime.fromtimestamp(floored_target, tz=timezone.utc),
        )
    if fetch_end <= databento_summary.last_ts:
        return YFinanceTailPlan(
            asset=asset.symbol,
            provider_symbol=asset.provider_symbol,
            interval=interval,
            status="up_to_date",
            databento_last_ts=databento_summary.last_ts,
            yfinance_last_ts=yfinance_summary.last_ts,
            fetch_start=None,
            fetch_end=None,
            reason="Databento already covers the latest complete Yahoo bar",
        )
    gap = fetch_end - databento_summary.last_ts
    limit = max_gap or YFINANCE_INTERVAL_LIMITS[interval]
    if gap > limit:
        return YFinanceTailPlan(
            asset=asset.symbol,
            provider_symbol=asset.provider_symbol,
            interval=interval,
            status="gap_too_large",
            databento_last_ts=databento_summary.last_ts,
            yfinance_last_ts=yfinance_summary.last_ts,
            fetch_start=None,
            fetch_end=fetch_end,
            reason=f"Gap {gap} exceeds Yahoo {interval} limit {limit}",
        )
    step = timedelta(milliseconds=INTERVAL_MS[interval])
    overlap_start = databento_summary.last_ts - step * max(1, overlap_bars - 1)
    retention_start = resolved_now - limit
    if overlap_start < retention_start:
        return YFinanceTailPlan(
            asset=asset.symbol,
            provider_symbol=asset.provider_symbol,
            interval=interval,
            status="outside_yahoo_retention",
            databento_last_ts=databento_summary.last_ts,
            yfinance_last_ts=yfinance_summary.last_ts,
            fetch_start=None,
            fetch_end=fetch_end,
            reason=(
                f"Overlap start {overlap_start} is older than Yahoo "
                f"{interval} retention boundary {retention_start}"
            ),
        )
    return YFinanceTailPlan(
        asset=asset.symbol,
        provider_symbol=asset.provider_symbol,
        interval=interval,
        status="fetch",
        databento_last_ts=databento_summary.last_ts,
        yfinance_last_ts=yfinance_summary.last_ts,
        fetch_start=overlap_start,
        fetch_end=fetch_end,
        reason="Fetch overlap plus recent tail, then validate before writing",
    )


def _resolve_target_end(
    *,
    interval: str,
    now: datetime | None = None,
    target_end: datetime | None = None,
) -> datetime:
    resolved_now = now or datetime.now(timezone.utc)
    if resolved_now.tzinfo is None:
        resolved_now = resolved_now.replace(tzinfo=timezone.utc)
    resolved_now = resolved_now.astimezone(timezone.utc)
    fetch_end = latest_complete_bar_start(interval, resolved_now)
    if target_end is not None:
        if target_end.tzinfo is None:
            target_end = target_end.replace(tzinfo=timezone.utc)
        target_end = target_end.astimezone(timezone.utc)
        step_seconds = INTERVAL_MS[interval] // 1000
        floored_target = int(target_end.timestamp()) // step_seconds * step_seconds
        fetch_end = min(fetch_end, datetime.fromtimestamp(floored_target, tz=timezone.utc))
    return fetch_end


def resolve_yfinance_demo_window(
    *,
    interval: str = "1m",
    now: datetime | None = None,
    target_end: datetime | None = None,
    max_span: timedelta | None = None,
) -> tuple[datetime, datetime]:
    if interval not in YFINANCE_INTERVAL_LIMITS:
        raise KeyError(f"Yahoo interval {interval!r} is not configured")
    fetch_end = _resolve_target_end(interval=interval, now=now, target_end=target_end)
    limit = max_span or YFINANCE_INTERVAL_LIMITS[interval]
    step = timedelta(milliseconds=INTERVAL_MS[interval])
    return fetch_end - limit + step, fetch_end


def plan_yfinance_demo(
    *,
    asset: YFinanceFuturesSpec,
    interval: str = "1m",
    base_dir: Path = BASE_DIR,
    now: datetime | None = None,
    target_end: datetime | None = None,
    max_span: timedelta | None = None,
) -> YFinanceDemoPlan:
    if interval not in YFINANCE_INTERVAL_LIMITS:
        return YFinanceDemoPlan(
            asset=asset.symbol,
            provider_symbol=asset.provider_symbol,
            interval=interval,
            status="unsupported_interval",
            local_last_ts=None,
            fetch_start=None,
            fetch_end=None,
            reason=f"Yahoo interval {interval!r} is not configured",
        )

    fetch_start, fetch_end = resolve_yfinance_demo_window(
        interval=interval,
        now=now,
        target_end=target_end,
        max_span=max_span,
    )
    yfinance_summary = existing_summary(
        asset=asset,  # type: ignore[arg-type]
        interval=interval,
        base_dir=base_dir,
        provider=YFINANCE_PROVIDER,
        market=YFINANCE_MARKET,
    )
    if yfinance_summary.last_ts is not None and yfinance_summary.last_ts >= fetch_end:
        return YFinanceDemoPlan(
            asset=asset.symbol,
            provider_symbol=asset.provider_symbol,
            interval=interval,
            status="up_to_date",
            local_last_ts=yfinance_summary.last_ts,
            fetch_start=fetch_start,
            fetch_end=fetch_end,
            reason="Local Yahoo demo data already covers the requested latest bar",
        )
    return YFinanceDemoPlan(
        asset=asset.symbol,
        provider_symbol=asset.provider_symbol,
        interval=interval,
        status="fetch",
        local_last_ts=yfinance_summary.last_ts,
        fetch_start=fetch_start,
        fetch_end=fetch_end,
        reason=f"Fetch latest Yahoo {interval} demo window up to provider retention",
    )


def load_recent_provider_rows(
    *,
    asset: YFinanceFuturesSpec,
    interval: str,
    provider: str,
    market: str,
    min_rows: int,
    base_dir: Path = BASE_DIR,
) -> pl.DataFrame:
    output_dir = output_dir_for_interval(
        base_dir,
        interval,
        provider=provider,
        market=market,
    )
    files = sorted(output_dir.glob(f"{batch_prefix(asset, provider=provider)}*.parquet"))  # type: ignore[arg-type]
    parts: list[pl.DataFrame] = []
    total_rows = 0
    for path in reversed(files):
        part = pl.read_parquet(path).select(OHLCV_COLUMNS)
        parts.append(part)
        total_rows += part.height
        if total_rows >= min_rows:
            break
    if not parts:
        return _empty_ohlcv_frame()
    return (
        pl.concat(list(reversed(parts)), how="diagonal_relaxed")
        .with_columns(pl.col("timestamp").cast(TIMESTAMP_DTYPE))
        .unique(subset=["timestamp"], keep="last")
        .sort("timestamp")
    )


def validate_yfinance_continuation(
    *,
    asset: str,
    interval: str,
    databento_df: pl.DataFrame,
    yfinance_df: pl.DataFrame,
    databento_last_ts: datetime,
    min_overlap_bars: int = DEFAULT_MIN_OVERLAP_BARS,
    max_close_diff_pct: float = DEFAULT_MAX_CLOSE_DIFF_PCT,
) -> ContinuationCheck:
    db = databento_df.select(
        [
            "timestamp",
            pl.col("close").alias("close_databento"),
        ]
    )
    yf = yfinance_df.select(
        [
            "timestamp",
            pl.col("close").alias("close_yfinance"),
        ]
    )
    overlap = (
        db.join(yf, on="timestamp", how="inner")
        .with_columns(
            (
                (pl.col("close_yfinance") - pl.col("close_databento")).abs()
                / pl.col("close_databento").abs()
                * 100.0
            ).alias("close_diff_pct")
        )
        .filter(pl.col("timestamp") <= databento_last_ts)
        .sort("timestamp")
    )
    tail_rows = int(yfinance_df.filter(pl.col("timestamp") > databento_last_ts).height)
    if overlap.height < min_overlap_bars:
        return ContinuationCheck(
            asset=asset,
            interval=interval,
            passed=False,
            overlap_rows=overlap.height,
            tail_rows=tail_rows,
            max_close_diff_pct=None,
            median_close_diff_pct=None,
            reason=f"Only {overlap.height} overlap rows; need at least {min_overlap_bars}",
        )
    max_diff = float(overlap["close_diff_pct"].max())
    median_diff = float(overlap["close_diff_pct"].median())
    passed = max_diff <= max_close_diff_pct
    reason = (
        "overlap_passed"
        if passed
        else f"max close diff {max_diff:.4f}% exceeds {max_close_diff_pct:.4f}%"
    )
    return ContinuationCheck(
        asset=asset,
        interval=interval,
        passed=passed,
        overlap_rows=overlap.height,
        tail_rows=tail_rows,
        max_close_diff_pct=max_diff,
        median_close_diff_pct=median_diff,
        reason=reason,
    )


def fetch_yfinance_frame(
    symbol: str,
    *,
    interval: str,
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    try:
        import yfinance as yf
    except ImportError as exc:  # pragma: no cover - depends on optional package
        raise RuntimeError(
            "yfinance is not installed. Install the market-data extra or run "
            "`python -m pip install yfinance`."
        ) from exc
    return yf.download(
        symbol,
        interval=interval,
        start=start,
        end=end + timedelta(milliseconds=INTERVAL_MS[interval]),
        auto_adjust=False,
        progress=False,
        threads=False,
    )


def fetch_yfinance_tail(
    *,
    asset: YFinanceFuturesSpec,
    interval: str = "1m",
    base_dir: Path = BASE_DIR,
    now: datetime | None = None,
    target_end: datetime | None = None,
    overlap_bars: int = DEFAULT_OVERLAP_BARS,
    min_overlap_bars: int = DEFAULT_MIN_OVERLAP_BARS,
    max_close_diff_pct: float = DEFAULT_MAX_CLOSE_DIFF_PCT,
) -> ContinuationCheck:
    plan = plan_yfinance_tail(
        asset=asset,
        interval=interval,
        base_dir=base_dir,
        now=now,
        target_end=target_end,
        overlap_bars=overlap_bars,
    )
    if not plan.needs_fetch:
        return ContinuationCheck(
            asset=asset.symbol,
            interval=interval,
            passed=False,
            overlap_rows=0,
            tail_rows=0,
            max_close_diff_pct=None,
            median_close_diff_pct=None,
            reason=plan.reason,
        )
    assert plan.fetch_start is not None
    assert plan.fetch_end is not None
    assert plan.databento_last_ts is not None
    raw = fetch_yfinance_frame(
        asset.provider_symbol,
        interval=interval,
        start=plan.fetch_start,
        end=plan.fetch_end,
    )
    yfinance_df = yfinance_frame_to_ohlcv(
        raw,
        interval,
        price_transform=asset.price_transform,
    ).filter(pl.col("timestamp") <= plan.fetch_end)
    databento_df = load_recent_provider_rows(
        asset=asset,
        interval=interval,
        provider=DATABENTO_PROVIDER,
        market=DATABENTO_MARKET,
        min_rows=max(overlap_bars + min_overlap_bars, min_overlap_bars),
        base_dir=base_dir,
    )
    check = validate_yfinance_continuation(
        asset=asset.symbol,
        interval=interval,
        databento_df=databento_df,
        yfinance_df=yfinance_df,
        databento_last_ts=plan.databento_last_ts,
        min_overlap_bars=min_overlap_bars,
        max_close_diff_pct=max_close_diff_pct,
    )
    if not check.passed:
        return check
    tail = yfinance_df.filter(pl.col("timestamp") > plan.databento_last_ts)
    if tail.height > 0:
        append_ohlcv_batches(
            tail,
            asset=asset,  # type: ignore[arg-type]
            interval=interval,
            base_dir=base_dir,
            provider=YFINANCE_PROVIDER,
            market=YFINANCE_MARKET,
        )
    return check


def fetch_yfinance_demo(
    *,
    asset: YFinanceFuturesSpec,
    interval: str = "1m",
    base_dir: Path = BASE_DIR,
    now: datetime | None = None,
    target_end: datetime | None = None,
    max_span: timedelta | None = None,
) -> YFinanceDemoFetchResult:
    plan = plan_yfinance_demo(
        asset=asset,
        interval=interval,
        base_dir=base_dir,
        now=now,
        target_end=target_end,
        max_span=max_span,
    )
    if not plan.needs_fetch:
        summary = existing_summary(
            asset=asset,  # type: ignore[arg-type]
            interval=interval,
            base_dir=base_dir,
            provider=YFINANCE_PROVIDER,
            market=YFINANCE_MARKET,
        )
        return YFinanceDemoFetchResult(
            asset=asset.symbol,
            interval=interval,
            status=plan.status,
            fetched_rows=0,
            files=summary.files,
            first_ts=summary.first_ts,
            last_ts=summary.last_ts,
            reason=plan.reason,
        )

    assert plan.fetch_start is not None
    assert plan.fetch_end is not None
    raw = fetch_yfinance_frame(
        asset.provider_symbol,
        interval=interval,
        start=plan.fetch_start,
        end=plan.fetch_end,
    )
    yfinance_df = yfinance_frame_to_ohlcv(
        raw,
        interval,
        price_transform=asset.price_transform,
    ).filter(
        (pl.col("timestamp") >= plan.fetch_start)
        & (pl.col("timestamp") <= plan.fetch_end)
    )
    if yfinance_df.height == 0:
        return YFinanceDemoFetchResult(
            asset=asset.symbol,
            interval=interval,
            status="empty",
            fetched_rows=0,
            files=0,
            first_ts=None,
            last_ts=None,
            reason="Yahoo returned no rows for the demo window",
        )
    summary = replace_ohlcv_window(
        yfinance_df,
        asset=asset,  # type: ignore[arg-type]
        interval=interval,
        window_start=plan.fetch_start,
        window_end=plan.fetch_end,
        base_dir=base_dir,
        provider=YFINANCE_PROVIDER,
        market=YFINANCE_MARKET,
    )
    return YFinanceDemoFetchResult(
        asset=asset.symbol,
        interval=interval,
        status="written",
        fetched_rows=int(yfinance_df.height),
        files=summary.files,
        first_ts=summary.first_ts,
        last_ts=summary.last_ts,
        reason="Yahoo demo rows written or already present",
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Yahoo Finance recent-tail continuation checker",
    )
    parser.add_argument("--assets", default="", help="Comma-separated ids")
    parser.add_argument("--interval", default="1m")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    assets = selected_yfinance_futures(
        tuple(part.strip().upper() for part in args.assets.split(",") if part.strip())
        or None
    )
    for asset in assets:
        plan = plan_yfinance_tail(asset=asset, interval=args.interval)
        print(
            f"{asset.symbol:<7} {asset.provider_symbol:<6} {args.interval:<3} "
            f"{plan.status}: {plan.reason}"
        )
        if args.dry_run or not plan.needs_fetch:
            continue
        check = fetch_yfinance_tail(asset=asset, interval=args.interval)
        print(
            f"  overlap={check.overlap_rows} tail={check.tail_rows} "
            f"passed={check.passed} reason={check.reason}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
