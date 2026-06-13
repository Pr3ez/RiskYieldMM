"""Closed-bar alignment utilities for regression path features."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import polars as pl


TIMEFRAME_MINUTES: dict[str, int] = {
    "15m": 15,
    "1h": 60,
    "4h": 240,
    "8h": 480,
    "12h": 720,
    "1d": 1440,
}
DEFAULT_TIMEFRAMES: tuple[str, ...] = ("15m", "1h", "4h", "8h", "12h", "1d")
OHLCV_COLUMNS: tuple[str, ...] = ("open", "high", "low", "close", "volume")


@dataclass(frozen=True)
class AlignmentDiagnostics:
    """Summary of closed-bar alignment for one timeframe."""

    timeframe: str
    rows: int
    aligned_rows: int
    missing_rows: int


def normalize_timeframes(raw: str | tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    """Parse and validate canonical OHLCV timeframe ids."""

    if raw is None:
        values = DEFAULT_TIMEFRAMES
    elif isinstance(raw, str):
        values = tuple(part.strip() for part in raw.split(",") if part.strip())
    else:
        values = tuple(str(part).strip() for part in raw if str(part).strip())
    unknown = [value for value in values if value not in TIMEFRAME_MINUTES]
    if unknown:
        known = ", ".join(TIMEFRAME_MINUTES)
        raise ValueError(f"Unknown timeframe(s) {unknown}; expected one of: {known}")
    return values


def source_prefix(timeframe: str) -> str:
    """Return the private source-column prefix used during feature computation."""

    return f"_rpf_src_{timeframe}_"


def align_prefix(timeframe: str) -> str:
    """Return the diagnostic alignment-column prefix for one timeframe."""

    return f"rpf_align_{timeframe}_"


def prepare_closed_bar_frame(
    bars: pl.DataFrame,
    *,
    timeframe: str,
    include_source_ohlcv: bool = True,
    source_columns: tuple[str, ...] | None = None,
) -> pl.DataFrame:
    """Prepare one canonical timeframe for backward as-of joining.

    Canonical bar timestamps are bar-open timestamps. A bar can first be used at
    `timestamp + timeframe`, so this function converts that close timestamp into
    the right-side join key. No partially formed bar is exposed.
    """

    if timeframe not in TIMEFRAME_MINUTES:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    if source_columns is None:
        source_columns = OHLCV_COLUMNS if include_source_ohlcv else ()
    elif not include_source_ohlcv:
        source_columns = ()

    required = {"timestamp", *source_columns}
    missing = required - set(bars.columns)
    if missing:
        raise ValueError(f"Canonical {timeframe} bars missing columns: {sorted(missing)}")

    minutes = TIMEFRAME_MINUTES[timeframe]
    prefix = align_prefix(timeframe)
    src_prefix = source_prefix(timeframe)
    selected = [
        pl.col("timestamp").alias(f"{prefix}bar_open_ts"),
        (pl.col("timestamp") + timedelta(minutes=minutes)).alias(f"{prefix}bar_close_ts"),
    ]
    selected.extend(pl.col(col).cast(pl.Float64).alias(f"{src_prefix}{col}") for col in source_columns)
    return bars.select(selected).sort(f"{prefix}bar_close_ts")


def join_closed_bar_context(
    rows: pl.DataFrame,
    bars: pl.DataFrame,
    *,
    timeframe: str,
    include_source_ohlcv: bool = True,
    source_columns: tuple[str, ...] | None = None,
) -> pl.DataFrame:
    """Attach the latest closed higher-timeframe bar to each prediction row."""

    if "timestamp" not in rows.columns:
        raise ValueError("Prediction rows must contain a timestamp column")
    prefix = align_prefix(timeframe)
    right = prepare_closed_bar_frame(
        bars,
        timeframe=timeframe,
        include_source_ohlcv=include_source_ohlcv,
        source_columns=source_columns,
    )
    row_order = "_rpf_row_order"
    left = rows.with_row_index(row_order).sort("timestamp")
    joined = left.join_asof(
        right,
        left_on="timestamp",
        right_on=f"{prefix}bar_close_ts",
        strategy="backward",
    ).sort(row_order)
    return joined.drop(row_order).with_columns(
        pl.col(f"{prefix}bar_open_ts").is_not_null().alias(f"{prefix}has_closed_bar")
    )


def join_all_closed_bar_context(
    rows: pl.DataFrame,
    bars_by_timeframe: dict[str, pl.DataFrame],
    *,
    timeframes: tuple[str, ...] = DEFAULT_TIMEFRAMES,
    include_source_ohlcv: bool = True,
    source_columns: tuple[str, ...] | None = None,
) -> pl.DataFrame:
    """Attach closed-bar context for all requested timeframes."""

    out = rows
    for timeframe in normalize_timeframes(timeframes):
        if timeframe not in bars_by_timeframe:
            raise KeyError(f"Missing canonical bars for timeframe {timeframe}")
        out = join_closed_bar_context(
            out,
            bars_by_timeframe[timeframe],
            timeframe=timeframe,
            include_source_ohlcv=include_source_ohlcv,
            source_columns=source_columns,
        )
    return out


def alignment_diagnostics(df: pl.DataFrame, *, timeframe: str) -> AlignmentDiagnostics:
    """Summarize alignment coverage for one joined timeframe."""

    has_col = f"{align_prefix(timeframe)}has_closed_bar"
    if has_col not in df.columns:
        raise ValueError(f"Missing alignment column: {has_col}")
    aligned = int(df[has_col].sum())
    rows = len(df)
    return AlignmentDiagnostics(
        timeframe=timeframe,
        rows=rows,
        aligned_rows=aligned,
        missing_rows=rows - aligned,
    )
