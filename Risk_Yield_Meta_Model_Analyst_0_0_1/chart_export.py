"""Windowed OHLCV exports for the local Lightweight Charts viewer."""

from __future__ import annotations

import argparse
import json
from bisect import bisect_left
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import polars as pl
from chart_config import (
    BYBIT_ASSETS,
    CANONICAL_SOURCE,
    DEFAULT_MAX_BARS,
    DEFAULT_PAYLOAD_PATH,
    HARD_MAX_BARS,
    PROJECT_ROOT,
    WEB_DATA_ROOT,
    asset_price_format,
    resolve_ohlcv_files,
    timeframe_seconds,
)
from indicators import (
    CUSUM_TREND_VERSION,
    DEFAULT_CUSUM_SENSITIVITY,
    EWMA_VOLATILITY_HALF_LIVES,
    EWMA_VOLATILITY_LABELS,
    compute_cusum_trend,
    compute_ewma_volatility,
    value_series,
)
from live_signal_service import (
    UnsupportedLiveSignalSelection,
    build_online_signal_config,
    get_live_signal_frame,
)
from market_context import MARKET_CONTEXT_VERSION, build_market_context_overlays
from multi_timeframe_context import unavailable_mtf_context
from online_signals import (
    ONLINE_SIGNAL_VERSION,
    REGIME_LABELS,
    TREND_HORIZONS,
    TREND_LABELS,
    OnlineSignalConfig,
    compute_online_signal_frame,
)

INDICATOR_NONE = "none"
INDICATOR_CUSUM_TREND = "cusum_trend"
INDICATOR_EWMA_VOLATILITY = "ewma_volatility"
INDICATOR_VOLATILITY_SCALED_TREND = "volatility_scaled_trend"
INDICATOR_ONLINE_REGIME = "online_regime"
INDICATOR_CROSS_TIMEFRAME_CONTEXT = "cross_timeframe_context"
INDICATOR_PRIOR_STRUCTURE = "prior_structure"
INDICATOR_COMPARABLE_VOLATILITY = "comparable_volatility"
INDICATOR_PHASE_ADJUSTED_PARTICIPATION = "phase_adjusted_participation"
INDICATOR_CHOICES = (
    INDICATOR_CUSUM_TREND,
    INDICATOR_EWMA_VOLATILITY,
    INDICATOR_VOLATILITY_SCALED_TREND,
    INDICATOR_ONLINE_REGIME,
    INDICATOR_CROSS_TIMEFRAME_CONTEXT,
    INDICATOR_PRIOR_STRUCTURE,
    INDICATOR_COMPARABLE_VOLATILITY,
    INDICATOR_PHASE_ADJUSTED_PARTICIPATION,
)
INDICATOR_LABELS = {
    INDICATOR_CUSUM_TREND: "CUSUM Trend",
    INDICATOR_EWMA_VOLATILITY: "EWMA Volatility",
    INDICATOR_VOLATILITY_SCALED_TREND: "Volatility-Scaled Trend",
    INDICATOR_ONLINE_REGIME: "Prototype Regime",
    INDICATOR_CROSS_TIMEFRAME_CONTEXT: "Cross-Timeframe Context",
    INDICATOR_PRIOR_STRUCTURE: "Prior Structure",
    INDICATOR_COMPARABLE_VOLATILITY: "Comparable Volatility",
    INDICATOR_PHASE_ADJUSTED_PARTICIPATION: "Phase-Adjusted Participation",
}

# Ten slow half-lives leave less than 0.1% of a seeded EWMA variance state.
# Two additional closes support a prior-bar volatility denominator at the
# first 192-bar trend observation.
INDICATOR_WARMUP_BARS = (10 * max(EWMA_VOLATILITY_HALF_LIVES)) + 2
# Participation compares each completed bar only with earlier observations from
# the same UTC/session phase.  Twenty reference occurrences are the production
# minimum; two extra phase cycles plus a small state cushion cover a page
# boundary and one shortened/holiday session without making the first visible
# point look spuriously mature.  The 1m canonical request is therefore 31,872
# hidden rows, safely below HARD_MAX_BARS, while higher timeframes retain the
# EWMA warm-up.
PARTICIPATION_REFERENCE_OCCURRENCES = 20
PARTICIPATION_CONTEXT_PHASE_CYCLES = PARTICIPATION_REFERENCE_OCCURRENCES + 2
PARTICIPATION_CONTEXT_STATE_CUSHION = 192
ONLINE_SIGNAL_MINIMUM_BARS = max(TREND_HORIZONS) + 1
_CANONICAL_BASE_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")
_CANONICAL_OPTIONAL_COLUMNS = (
    "asset_id",
    "calendar_id",
    "is_market_open",
    "is_synthetic_no_trade",
    "is_open_session_gap_fill",
    "minutes_since_prev_real_bar",
    "session_id",
    "session_date",
    "session_bar_pos",
    "session_minutes_to_close",
    "is_session_open_bar",
    "is_session_close_bar",
    "is_weekly_open_bar",
    "is_weekly_close_bar",
)


def _parse_utc(value: str | datetime | None) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _path_sample(paths: tuple[Path, ...], sample_size: int = 5) -> list[str]:
    if len(paths) <= sample_size * 2:
        return [_relative(path) for path in paths]
    sampled = list(paths[:sample_size]) + list(paths[-sample_size:])
    return [_relative(path) for path in sampled]


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _iso_utc(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    parsed = _parse_utc(str(value))
    return None if parsed is None else parsed.isoformat().replace("+00:00", "Z")


def normalize_indicators(
    indicators: str | Iterable[str] | None = None,
    *,
    indicator: str | None = None,
) -> tuple[str, ...]:
    """Normalize legacy single-indicator and multi-indicator inputs."""
    raw_values: list[str] = []
    if indicator:
        raw_values.append(indicator)
    if isinstance(indicators, str):
        raw_values.extend(indicators.split(","))
    elif indicators is not None:
        raw_values.extend(str(value) for value in indicators)

    normalized: list[str] = []
    for raw in raw_values:
        for part in str(raw).split(","):
            value = part.strip().lower()
            if not value or value == INDICATOR_NONE:
                continue
            if value not in INDICATOR_CHOICES:
                known = ", ".join((INDICATOR_NONE, *INDICATOR_CHOICES))
                raise ValueError(
                    f"Unknown indicator {part!r}. Known indicators: {known}"
                )
            if value not in normalized:
                normalized.append(value)
    return tuple(normalized)


def required_indicator_warmup_bars(
    indicators: str | Iterable[str] | None,
    *,
    timeframe: str,
    indicator: str | None = None,
) -> int:
    """Return hidden history needed by the selected causal chart diagnostics.

    The visible ``max_bars`` contract is deliberately independent: this value
    controls calculation state only and the loaded rows are never serialized as
    candles.  Phase-adjusted participation is the only current layer whose
    required history varies by bar duration.
    """

    enabled = normalize_indicators(indicators, indicator=indicator)
    required = INDICATOR_WARMUP_BARS
    if INDICATOR_PHASE_ADJUSTED_PARTICIPATION in enabled:
        interval_seconds = timeframe_seconds(timeframe)
        bars_per_utc_day = max(1, (86_400 + interval_seconds - 1) // interval_seconds)
        phase_required = (
            PARTICIPATION_CONTEXT_PHASE_CYCLES * bars_per_utc_day
            + PARTICIPATION_CONTEXT_STATE_CUSHION
        )
        required = max(required, phase_required)
    if required > HARD_MAX_BARS:
        raise ValueError(
            f"Selected indicators require {required} hidden bars, exceeding "
            f"the hard calculation limit {HARD_MAX_BARS}."
        )
    return required


def _scan_ohlcv(files: tuple[Path, ...]) -> pl.LazyFrame:
    lazy = pl.scan_parquet([str(path) for path in files])
    schema = lazy.collect_schema()
    expressions: list[pl.Expr] = [
        pl.col("timestamp").alias("timestamp"),
        pl.col("open").cast(pl.Float64),
        pl.col("high").cast(pl.Float64),
        pl.col("low").cast(pl.Float64),
        pl.col("close").cast(pl.Float64),
        pl.col("volume").cast(pl.Float64),
    ]
    # Canonical session metadata makes a non-nominal gap distinguishable from
    # missing open-market data without consulting future prices.  Keep it in
    # the hidden calculation frame; candle JSON still exports only OHLCV.
    expressions.extend(
        pl.col(column) for column in _CANONICAL_OPTIONAL_COLUMNS if column in schema
    )
    return lazy.select(expressions).filter(pl.col("timestamp").is_not_null())


def _single_canonical_parquet_tail(
    path: Path,
    *,
    max_bars: int,
    before: datetime | None = None,
) -> tuple[pl.DataFrame, int] | None:
    """Read only the final required Parquet row groups of one canonical file.

    Polars' lazy ``tail`` still retained hundreds of megabytes for the 1m
    canonical artifact in this environment.  Row-group reads keep the common
    latest-window path proportional to the requested browser window.  ``None``
    asks the caller to use the portable lazy-frame fallback.
    """

    try:
        import pyarrow as pa
        import pyarrow.compute as pc
        import pyarrow.parquet as pq
    except ImportError:
        return None

    parquet = pq.ParquetFile(path)
    available = set(parquet.schema_arrow.names)
    if not set(_CANONICAL_BASE_COLUMNS) <= available:
        return None
    columns = [
        *_CANONICAL_BASE_COLUMNS,
        *(name for name in _CANONICAL_OPTIONAL_COLUMNS if name in available),
    ]
    timestamp_index = parquet.schema_arrow.names.index("timestamp")
    chunks: list[Any] = []
    remaining = max_bars
    for row_group_index in range(parquet.metadata.num_row_groups - 1, -1, -1):
        row_group = parquet.metadata.row_group(row_group_index)
        if before is not None:
            statistics = row_group.column(timestamp_index).statistics
            if statistics is not None and statistics.has_min_max:
                minimum = statistics.min
                if isinstance(minimum, datetime):
                    if minimum.tzinfo is None:
                        minimum = minimum.replace(tzinfo=timezone.utc)
                    else:
                        minimum = minimum.astimezone(timezone.utc)
                    if minimum >= before:
                        continue
        table = parquet.read_row_group(row_group_index, columns=columns)
        if before is not None and table.num_rows:
            timestamp_type = table.schema.field("timestamp").type
            table = table.filter(
                pc.less(table["timestamp"], pa.scalar(before, type=timestamp_type))
            )
        if not table.num_rows:
            continue
        if table.num_rows > remaining:
            table = table.slice(table.num_rows - remaining, remaining)
        chunks.insert(0, table)
        remaining -= table.num_rows
        if remaining <= 0:
            break

    if not chunks:
        return (
            pl.DataFrame(
                schema={
                    "timestamp": pl.Datetime(time_zone="UTC"),
                    "open": pl.Float64,
                    "high": pl.Float64,
                    "low": pl.Float64,
                    "close": pl.Float64,
                    "volume": pl.Float64,
                }
            ),
            int(parquet.metadata.num_rows),
        )
    arrow_frame = pa.concat_tables(chunks) if len(chunks) > 1 else chunks[0]
    frame = pl.from_arrow(arrow_frame, rechunk=False)
    assert isinstance(frame, pl.DataFrame)
    frame = frame.with_columns(
        pl.col("open").cast(pl.Float64),
        pl.col("high").cast(pl.Float64),
        pl.col("low").cast(pl.Float64),
        pl.col("close").cast(pl.Float64),
        pl.col("volume").cast(pl.Float64),
    )
    return frame, int(parquet.metadata.num_rows)


def _deduplicated_sorted(lazy: pl.LazyFrame) -> pl.LazyFrame:
    """Return one chronologically ordered OHLCV row per timestamp."""
    return lazy.unique(subset=["timestamp"], keep="last").sort("timestamp")


def _collect_canonical_window(
    lazy: pl.LazyFrame,
    *,
    max_bars: int,
) -> tuple[pl.DataFrame, int, bool]:
    """Collect a sorted canonical tail without sorting its full history.

    Materialized canonical OHLCV is contractually timestamp-sorted and unique.
    Counting the projected lazy frame is cheap, while applying ``tail`` before
    ``collect`` keeps a multi-million-row 1m chart request bounded.  A local
    invariant check retains the slower corrective path if a canonical artifact
    unexpectedly contains duplicate timestamps.
    """

    full_count = int(lazy.select(pl.len().alias("rows")).collect()["rows"][0])
    truncated = full_count > max_bars
    candidate = (lazy.tail(max_bars) if truncated else lazy).collect()
    frame = candidate.unique(subset=["timestamp"], keep="last").sort("timestamp")
    expected_rows = min(full_count, max_bars)
    if frame.height == expected_rows:
        return frame, full_count, truncated

    # This is an integrity fallback, not the normal canonical request path.
    corrected = _deduplicated_sorted(lazy)
    unique_count = int(corrected.select(pl.len().alias("rows")).collect()["rows"][0])
    unique_truncated = unique_count > max_bars
    if unique_truncated:
        corrected = corrected.tail(max_bars)
    return corrected.collect(), unique_count, unique_truncated


def load_ohlcv_window(
    asset: str,
    timeframe: str,
    source: str = "canonical",
    start: str | datetime | None = None,
    end: str | datetime | None = None,
    max_bars: int = DEFAULT_MAX_BARS,
) -> tuple[pl.DataFrame, dict[str, Any]]:
    """Load a bounded OHLCV window and return data plus export metadata."""

    if max_bars <= 0:
        raise ValueError("max_bars must be positive")
    if max_bars > HARD_MAX_BARS:
        raise ValueError(
            f"max_bars={max_bars} is too large for browser inspection. "
            f"Hard limit: {HARD_MAX_BARS}"
        )

    resolution = resolve_ohlcv_files(asset=asset, timeframe=timeframe, source=source)
    start_dt = _parse_utc(start)
    end_dt = _parse_utc(end)
    if start_dt and end_dt and start_dt > end_dt:
        raise ValueError(f"start {start_dt} is after end {end_dt}")

    fast_canonical = None
    if (
        resolution.source == CANONICAL_SOURCE
        and len(resolution.files) == 1
        and start_dt is None
        and end_dt is None
    ):
        fast_canonical = _single_canonical_parquet_tail(
            resolution.files[0],
            max_bars=max_bars,
        )

    if fast_canonical is not None:
        frame, full_count = fast_canonical
        truncated = full_count > max_bars
    else:
        lazy = _scan_ohlcv(resolution.files)
        if start_dt is not None:
            lazy = lazy.filter(pl.col("timestamp") >= start_dt)
        if end_dt is not None:
            lazy = lazy.filter(pl.col("timestamp") <= end_dt)
        if resolution.source == CANONICAL_SOURCE:
            frame, full_count, truncated = _collect_canonical_window(
                lazy,
                max_bars=max_bars,
            )
        else:
            lazy = _deduplicated_sorted(lazy)
            full_count = int(lazy.select(pl.len().alias("rows")).collect()["rows"][0])
            truncated = full_count > max_bars
            if truncated:
                lazy = lazy.tail(max_bars)
            frame = lazy.collect()
    if frame.is_empty():
        raise ValueError(
            f"No rows found for asset={resolution.asset}, timeframe={resolution.timeframe}, "
            f"source={resolution.source}, start={start}, end={end}"
        )

    metadata = {
        "asset": resolution.asset,
        "timeframe": resolution.timeframe,
        "source": resolution.source,
        "provider": resolution.provider,
        "price_format": asset_price_format(resolution.asset),
        "description": resolution.description,
        "start": _iso_utc(frame["timestamp"].min()),
        "end": _iso_utc(frame["timestamp"].max()),
        "requested_start": _iso_utc(start_dt),
        "requested_end": _iso_utc(end_dt),
        "row_count": frame.height,
        "rows_before_window_limit": int(full_count),
        "truncated_to_max_bars": bool(truncated),
        "max_bars": int(max_bars),
        "source_root": _relative(resolution.source_root),
        "source_path_count": len(resolution.files),
        "source_paths_sample": _path_sample(resolution.files),
    }
    return frame, metadata


def load_ohlcv_calculation_context(
    *,
    asset: str,
    timeframe: str,
    source: str,
    before: datetime,
    max_bars: int = INDICATOR_WARMUP_BARS,
) -> pl.DataFrame:
    """Load hidden pre-window history for stateful chart-indicator calculation."""

    if max_bars <= 0:
        return pl.DataFrame(
            schema={
                "timestamp": pl.Datetime(time_zone="UTC"),
                "open": pl.Float64,
                "high": pl.Float64,
                "low": pl.Float64,
                "close": pl.Float64,
                "volume": pl.Float64,
            }
        )
    resolution = resolve_ohlcv_files(asset=asset, timeframe=timeframe, source=source)
    if resolution.source == CANONICAL_SOURCE and len(resolution.files) == 1:
        fast_context = _single_canonical_parquet_tail(
            resolution.files[0],
            max_bars=max_bars,
            before=before,
        )
        if fast_context is not None:
            return fast_context[0]
    lazy = _scan_ohlcv(resolution.files).filter(pl.col("timestamp") < before)
    if resolution.source == CANONICAL_SOURCE:
        frame, _, _ = _collect_canonical_window(lazy, max_bars=max_bars)
        return frame
    return _deduplicated_sorted(lazy).tail(max_bars).collect()


def load_ohlcv_window_with_context(
    asset: str,
    timeframe: str,
    source: str = "canonical",
    start: str | datetime | None = None,
    end: str | datetime | None = None,
    max_bars: int = DEFAULT_MAX_BARS,
    indicator_warmup_bars: int = INDICATOR_WARMUP_BARS,
) -> tuple[pl.DataFrame, dict[str, Any], pl.DataFrame]:
    """Load visible OHLCV rows plus hidden history for stateful indicators.

    The context bypasses an explicit user ``start`` boundary, but is never
    emitted in the chart payload. This keeps every lazy-loaded page from
    restarting EWMA/CUSUM state at its left boundary.
    """

    frame, metadata = load_ohlcv_window(
        asset=asset,
        timeframe=timeframe,
        source=source,
        start=start,
        end=end,
        max_bars=max_bars,
    )
    context = load_ohlcv_calculation_context(
        asset=asset,
        timeframe=timeframe,
        source=source,
        before=frame["timestamp"].min(),
        max_bars=indicator_warmup_bars,
    )
    calculation_start = (
        context["timestamp"].min()
        if not context.is_empty()
        else frame["timestamp"].min()
    )
    metadata = {
        **metadata,
        "indicator_warmup_requested": int(indicator_warmup_bars),
        "indicator_warmup_loaded": context.height,
        "indicator_warmup_complete": context.height >= indicator_warmup_bars,
        "indicator_calculation_start": _iso_utc(calculation_start),
    }
    return frame, metadata, context


def _calculation_frame(
    frame: pl.DataFrame,
    indicator_context: pl.DataFrame | None,
) -> pl.DataFrame:
    if indicator_context is None or indicator_context.is_empty():
        return frame.sort("timestamp")
    return (
        pl.concat([indicator_context, frame], how="vertical_relaxed")
        .unique(subset=["timestamp"], keep="last")
        .sort("timestamp")
    )


def _annotate_debug_session_gaps(
    frame: pl.DataFrame,
    *,
    asset: str,
    source: str,
    config: OnlineSignalConfig,
) -> tuple[pl.DataFrame, str]:
    """Add a causal, explicitly unverified gap flag to session debug feeds."""

    if "is_session_open_bar" in frame.columns:
        return frame, "canonical_is_session_open_bar"
    if source == "canonical" or asset.upper() in BYBIT_ASSETS:
        return frame, "exact_continuous_cadence"
    maximum_gap = config.max_gap_seconds
    if maximum_gap is None:
        return frame, "exact_cadence_no_calendar_metadata"
    interval = config.expected_interval_seconds
    elapsed = pl.col("timestamp").diff().dt.total_seconds()
    annotated = frame.sort("timestamp").with_columns(
        ((elapsed > interval) & (elapsed <= maximum_gap) & ((elapsed % interval) == 0))
        .fill_null(False)
        .alias("is_session_open_bar")
    )
    return annotated, "bounded_timestamp_gap_inference_debug_only"


def _visible_action_indicator_rows(
    indicator_frame: pl.DataFrame,
    frame: pl.DataFrame,
    *,
    timeframe_seconds: int,
) -> pl.DataFrame:
    """Shift closed-bar diagnostics to their earliest actionable chart time."""

    if indicator_frame.is_empty() or frame.is_empty():
        return indicator_frame
    start = frame["timestamp"].min()
    end = frame["timestamp"].max() + timedelta(seconds=timeframe_seconds)
    return (
        indicator_frame.with_columns(
            pl.col("timestamp").alias("source_timestamp"),
            (pl.col("timestamp") + pl.duration(seconds=timeframe_seconds)).alias(
                "timestamp"
            ),
        )
        .filter((pl.col("timestamp") >= start) & (pl.col("timestamp") <= end))
        .with_columns(pl.col("timestamp").dt.epoch("s").cast(pl.Int64).alias("time"))
        .sort("timestamp")
    )


def _visible_online_rows(
    online_frame: pl.DataFrame | None,
    frame: pl.DataFrame,
    *,
    timeframe_seconds: int,
) -> pl.DataFrame:
    """Slice action-time online outputs to the displayed range plus next open."""

    if online_frame is None or online_frame.is_empty() or frame.is_empty():
        return pl.DataFrame()
    start = frame["timestamp"].min()
    end = frame["timestamp"].max() + timedelta(seconds=timeframe_seconds)
    return (
        online_frame.filter(
            (pl.col("timestamp") >= start) & (pl.col("timestamp") <= end)
        )
        .with_columns(pl.col("timestamp").dt.epoch("s").cast(pl.Int64).alias("time"))
        .sort("time")
    )


def build_lightweight_charts_payload(
    frame: pl.DataFrame,
    metadata: dict[str, Any],
    indicator: str | None = INDICATOR_NONE,
    indicators: str | Iterable[str] | None = None,
    cusum_sensitivity: str = DEFAULT_CUSUM_SENSITIVITY,
    indicator_context: pl.DataFrame | None = None,
    live_signal_frame: pl.DataFrame | None = None,
    live_signal_metadata: dict[str, Any] | None = None,
    mtf_context_overlay: dict[str, Any] | None = None,
    use_live_signal_service: bool = False,
    calculation_now: datetime | None = None,
) -> dict[str, Any]:
    """Convert an OHLCV frame to the JSON contract consumed by app.js."""
    enabled_indicators = normalize_indicators(indicators, indicator=indicator)

    export_frame = (
        frame.with_columns(
            [
                pl.col("timestamp").dt.epoch("s").cast(pl.Int64).alias("time"),
                pl.when(pl.col("close") >= pl.col("open"))
                .then(pl.lit("#26a69a"))
                .otherwise(pl.lit("#ef5350"))
                .alias("volume_color"),
            ]
        )
        .select(["time", "open", "high", "low", "close", "volume", "volume_color"])
        .sort("time")
    )
    overlays: dict[str, Any] = {}
    markers: list[dict[str, Any]] = []
    indicator_labels: list[str] = []
    market_context_calculation_frame = _calculation_frame(frame, indicator_context)
    # Participation needs many phase-matched observations on 1m data.  Keep
    # that extended context out of the legacy Python online/HMM replay and the
    # existing EWMA/CUSUM paths: their fixed warm-up is already sufficient and
    # processing ~30k rows there would add latency without changing results.
    calculation_frame = market_context_calculation_frame.tail(
        frame.height + INDICATOR_WARMUP_BARS
    )
    needs_online_signals = bool(
        {
            INDICATOR_VOLATILITY_SCALED_TREND,
            INDICATOR_ONLINE_REGIME,
        }
        & set(enabled_indicators)
    )
    online_frame = live_signal_frame
    online_metadata = dict(live_signal_metadata or {})
    use_persistent_live_replay = bool(
        needs_online_signals
        and online_frame is None
        and use_live_signal_service
        and metadata.get("source") == "canonical"
        and metadata.get("requested_end") is None
    )
    if use_persistent_live_replay:
        try:
            online_frame, online_metadata = get_live_signal_frame(
                asset=str(metadata.get("asset") or ""),
                timeframe=str(metadata.get("timeframe") or ""),
                source=str(metadata.get("source") or ""),
                now=calculation_now,
                replay_frame=calculation_frame,
                visible_start=frame["timestamp"].min(),
            )
        except UnsupportedLiveSignalSelection as exc:
            online_metadata = {
                "status": "unsupported_selection",
                "reason": str(exc),
                "diagnostic_only": True,
            }
        except Exception as exc:  # Optional diagnostics must not hide candles.
            online_metadata = {
                "status": "service_error",
                "reason": f"Online signal service failed: {exc}",
                "diagnostic_only": True,
            }
    if needs_online_signals and online_frame is None:
        asset = str(metadata.get("asset") or "")
        source = str(metadata.get("source") or "")
        local_config = build_online_signal_config(
            asset=asset,
            timeframe=str(metadata.get("timeframe") or "1h"),
        )
        local_calculation_frame, session_gap_policy = _annotate_debug_session_gaps(
            calculation_frame,
            asset=asset,
            source=source,
            config=local_config,
        )
        online_frame, _ = compute_online_signal_frame(
            local_calculation_frame,
            config=local_config,
            now=calculation_now,
        )
        service_reason = online_metadata.get("reason")
        signal_vintage = (
            "current_canonical_replay"
            if source == "canonical"
            else "current_source_replay"
        )
        online_metadata = {
            **online_metadata,
            "status": "bounded_request_replay",
            "mode": "bounded_request_replay",
            "replay_scope": "chart_window_plus_hidden_warmup",
            "hidden_context_bars": min(
                int(metadata.get("indicator_warmup_loaded") or 0),
                INDICATOR_WARMUP_BARS,
            ),
            "closed_bar_count": online_frame.height,
            "warmup_required_closed_bars": ONLINE_SIGNAL_MINIMUM_BARS,
            "algorithm_version": ONLINE_SIGNAL_VERSION,
            "config_digest": local_config.digest(),
            "expected_interval_seconds": local_config.expected_interval_seconds,
            "maximum_tolerated_gap_seconds": local_config.max_gap_seconds,
            "session_gap_policy": session_gap_policy,
            "model": "fixed_prototype_gaussian_hmm_forward_v1",
            "trained_model": False,
            "calibrated_model": False,
            "diagnostic_only": True,
            "usable_as_trading_gate": False,
            "availability": "post_close_usable_next_bar",
            "ingestion_safety_lag_seconds": 5,
            "signal_vintage": signal_vintage,
            "validation_safe": False,
            "as_was_live_journal": False,
            "historical_revision_policy": (
                "latest_source_revision_replays_and_rewrites_derived_history"
            ),
            "validation_warning": (
                "Signals are a causal replay of the current source revision, not an "
                "append-only as-was-live vintage. Do not treat this chart as a PnL "
                "backtest or calibrated trading gate."
            ),
            **(
                {"service_warning": service_reason}
                if service_reason is not None
                else {}
            ),
        }
    if needs_online_signals:
        online_metadata.setdefault("asset", metadata.get("asset"))
        online_metadata.setdefault("timeframe", metadata.get("timeframe"))
        online_metadata.setdefault("source", metadata.get("source"))
    visible_online_frame = _visible_online_rows(
        online_frame,
        frame,
        timeframe_seconds=timeframe_seconds(str(metadata.get("timeframe") or "1h")),
    )
    interval_seconds = timeframe_seconds(str(metadata.get("timeframe") or "1h"))
    enabled_market_context = tuple(
        indicator_id
        for indicator_id in (
            INDICATOR_PRIOR_STRUCTURE,
            INDICATOR_COMPARABLE_VOLATILITY,
            INDICATOR_PHASE_ADJUSTED_PARTICIPATION,
        )
        if indicator_id in enabled_indicators
    )
    market_context_overlays: dict[str, Any] = {}
    if enabled_market_context:
        try:
            all_market_context_overlays = build_market_context_overlays(
                market_context_calculation_frame,
                asset=str(metadata.get("asset") or ""),
                timeframe=str(metadata.get("timeframe") or "1h"),
                visible_start=frame["timestamp"].min(),
                visible_end=frame["timestamp"].max(),
            )
            selection_provenance = {
                "chart_source": metadata.get("source"),
                "chart_provider": metadata.get("provider"),
                "calendar_metadata_status": (
                    "carried_in_calculation_frame"
                    if {
                        "calendar_id",
                        "is_synthetic_no_trade",
                        "is_open_session_gap_fill",
                    }
                    & set(market_context_calculation_frame.columns)
                    else "not_available_in_chart_frame"
                ),
                "provider_cohort_status": "not_carried_in_chart_frame",
                "roll_provenance_status": "not_carried_in_chart_frame",
            }
            for context_overlay in all_market_context_overlays.values():
                context_overlay["data_provenance"] = dict(selection_provenance)
            all_market_context_overlays[INDICATOR_PHASE_ADJUSTED_PARTICIPATION][
                "implementation_scope"
            ] = "target_timeframe_prior_phase_median_proxy"
            all_market_context_overlays[INDICATOR_PHASE_ADJUSTED_PARTICIPATION][
                "not_implemented"
            ] = "one_minute_constituent_session_total_phase_share_decomposition"
            market_context_overlays = {
                indicator_id: all_market_context_overlays[indicator_id]
                for indicator_id in enabled_market_context
            }
        except Exception as exc:  # Diagnostics must never hide primary candles.
            market_context_overlays = {
                indicator_id: _unavailable_market_context_overlay(
                    indicator_id,
                    exc,
                )
                for indicator_id in enabled_market_context
            }

    if INDICATOR_CUSUM_TREND in enabled_indicators:
        indicator_frame = _visible_action_indicator_rows(
            compute_cusum_trend(
                calculation_frame,
                sensitivity=cusum_sensitivity,
            ),
            frame,
            timeframe_seconds=interval_seconds,
        )
        color_frame = indicator_frame.select(
            [
                "time",
                pl.col("candle_color").alias("color"),
                pl.col("candle_color").alias("borderColor"),
                pl.col("candle_color").alias("wickColor"),
            ]
        )
        export_frame = export_frame.join(color_frame, on="time", how="left")
        markers.extend(_cusum_markers(indicator_frame, frame))
        overlays[INDICATOR_CUSUM_TREND] = {
            "id": INDICATOR_CUSUM_TREND,
            "label": "CUSUM Trend",
            "sensitivity": cusum_sensitivity,
            "algorithm": "prior_scale_standardized_two_sided_cusum_on_hma_residual",
            "algorithm_version": CUSUM_TREND_VERSION,
            "availability": "post_close_usable_next_bar",
            "plotted_at": "earliest_next_bar_execution_time",
            "signal_semantics": "directional_change_candidate_not_trade_instruction",
            "diagnostic_only": True,
            "upper_band": value_series(indicator_frame, value_col="up_band"),
            "lower_band": value_series(indicator_frame, value_col="dn_band"),
            "trail_stop": value_series(indicator_frame, value_col="trail_stop"),
            "last": _cusum_last_state(indicator_frame),
        }
        indicator_labels.append(INDICATOR_LABELS[INDICATOR_CUSUM_TREND])

    if INDICATOR_EWMA_VOLATILITY in enabled_indicators:
        indicator_frame = _visible_action_indicator_rows(
            compute_ewma_volatility(calculation_frame),
            frame,
            timeframe_seconds=interval_seconds,
        )
        overlays[INDICATOR_EWMA_VOLATILITY] = {
            "id": INDICATOR_EWMA_VOLATILITY,
            "label": INDICATOR_LABELS[INDICATOR_EWMA_VOLATILITY],
            "unit": "percent_per_bar",
            "return_basis": "log_close_to_close",
            "availability": "post_close_usable_next_bar",
            "plotted_at": "earliest_next_bar_execution_time",
            "observation_basis": "observed_trading_bars",
            "comparability_warning": (
                "Percent-per-bar levels are comparable within this asset/timeframe; "
                "do not compare raw levels across different bar durations."
            ),
            "diagnostic_only": True,
            "half_lives_bars": dict(
                zip(EWMA_VOLATILITY_LABELS, EWMA_VOLATILITY_HALF_LIVES)
            ),
            "state_thresholds": {
                "expanding_fast_slow_ratio": 1.20,
                "contracting_fast_slow_ratio": 0.85,
                "semantics": "versioned_chart_heuristic_not_calibrated",
            },
            "maturity_required_observations": 10 * max(EWMA_VOLATILITY_HALF_LIVES),
            "fast": value_series(indicator_frame, value_col="ewma_vol_fast_pct"),
            "medium": value_series(indicator_frame, value_col="ewma_vol_medium_pct"),
            "slow": value_series(indicator_frame, value_col="ewma_vol_slow_pct"),
            "last": _ewma_volatility_last_state(indicator_frame),
        }
        indicator_labels.append(INDICATOR_LABELS[INDICATOR_EWMA_VOLATILITY])

    if INDICATOR_VOLATILITY_SCALED_TREND in enabled_indicators:
        trend_overlay = _trend_overlay(visible_online_frame, online_metadata)
        overlays[INDICATOR_VOLATILITY_SCALED_TREND] = trend_overlay
        markers.extend(_trend_markers(visible_online_frame, frame))
        indicator_labels.append(INDICATOR_LABELS[INDICATOR_VOLATILITY_SCALED_TREND])

    if INDICATOR_ONLINE_REGIME in enabled_indicators:
        if online_metadata.get("status") in {
            "unsupported_selection",
            "service_error",
        }:
            regime_overlay = _unavailable_regime_overlay(online_metadata)
        else:
            regime_overlay = _online_regime_overlay(
                visible_online_frame,
                online_metadata,
            )
            markers.extend(_online_regime_markers(visible_online_frame, frame))
        overlays[INDICATOR_ONLINE_REGIME] = regime_overlay
        indicator_labels.append(INDICATOR_LABELS[INDICATOR_ONLINE_REGIME])

    if INDICATOR_CROSS_TIMEFRAME_CONTEXT in enabled_indicators:
        overlay = mtf_context_overlay or unavailable_mtf_context(
            chart_timeframe=str(metadata.get("timeframe") or ""),
            reason=(
                "Cross-timeframe context requires the canonical chart API so "
                "its higher-timeframe source windows can be aligned causally."
            ),
        )
        overlays[INDICATOR_CROSS_TIMEFRAME_CONTEXT] = overlay
        indicator_labels.append(INDICATOR_LABELS[INDICATOR_CROSS_TIMEFRAME_CONTEXT])

    for indicator_id in (
        INDICATOR_PRIOR_STRUCTURE,
        INDICATOR_COMPARABLE_VOLATILITY,
        INDICATOR_PHASE_ADJUSTED_PARTICIPATION,
    ):
        if indicator_id not in enabled_indicators:
            continue
        overlay = market_context_overlays[indicator_id]
        overlays[indicator_id] = overlay
        indicator_labels.append(INDICATOR_LABELS[indicator_id])
        if indicator_id == INDICATOR_PRIOR_STRUCTURE:
            markers.extend(_market_context_markers(overlay, frame))

    if not enabled_indicators:
        legacy_indicator = INDICATOR_NONE
    elif len(enabled_indicators) == 1:
        legacy_indicator = enabled_indicators[0]
    else:
        legacy_indicator = "multiple"
    metadata = {
        **metadata,
        "indicator": legacy_indicator,
        "indicators": list(enabled_indicators),
        "indicator_labels": indicator_labels,
        **(
            {"cusum_sensitivity": cusum_sensitivity}
            if INDICATOR_CUSUM_TREND in enabled_indicators
            else {}
        ),
        **(
            {
                "market_context": {
                    "algorithm_version": MARKET_CONTEXT_VERSION,
                    "indicators": list(enabled_market_context),
                    "availability": "post_close_usable_next_bar",
                    "diagnostic_only": True,
                    "usable_as_trading_gate": False,
                    "changes_execution_decisions": False,
                    "calculation_granularity": "selected_chart_timeframe",
                    "hidden_context_bars": int(
                        metadata.get("indicator_warmup_loaded") or 0
                    ),
                    "hidden_context_requested": int(
                        metadata.get("indicator_warmup_requested") or 0
                    ),
                    "participation_implementation_scope": (
                        "target_timeframe_prior_phase_median_proxy"
                    ),
                }
            }
            if enabled_market_context
            else {}
        ),
        **(
            {
                "online_signal": {
                    key: online_metadata.get(key)
                    for key in (
                        "status",
                        "reason",
                        "mode",
                        "algorithm_version",
                        "config_digest",
                        "model",
                        "trained_model",
                        "calibrated_model",
                        "diagnostic_only",
                        "usable_as_trading_gate",
                        "replay_scope",
                        "hidden_context_bars",
                        "closed_bar_count",
                        "warmup_required_closed_bars",
                        "expected_interval_seconds",
                        "maximum_tolerated_gap_seconds",
                        "session_gap_policy",
                        "source_generation",
                        "seed_origin",
                        "computed_source_through",
                        "available_through",
                        "replayed",
                        "replay_cause",
                        "replay_from",
                        "appended_bars",
                        "restart_behavior",
                        "availability",
                        "ingestion_safety_lag_seconds",
                        "signal_vintage",
                        "validation_safe",
                        "as_was_live_journal",
                        "historical_revision_policy",
                        "validation_warning",
                        "service_warning",
                    )
                    if online_metadata.get(key) is not None
                }
            }
            if needs_online_signals
            else {}
        ),
    }

    candle_cols = ["time", "open", "high", "low", "close"]
    if {"color", "borderColor", "wickColor"} <= set(export_frame.columns):
        candle_cols.extend(["color", "borderColor", "wickColor"])
    candles = export_frame.select(candle_cols).to_dicts()
    volume = [
        {
            "time": row["time"],
            "value": row["volume"],
            "color": row["volume_color"],
        }
        for row in export_frame.select(["time", "volume", "volume_color"]).to_dicts()
        if row["volume"] is not None
    ]

    return {
        "metadata": metadata,
        "candles": candles,
        "volume": volume,
        "markers": markers,
        "overlays": overlays,
    }


def _unavailable_market_context_overlay(
    indicator_id: str,
    exc: Exception,
) -> dict[str, Any]:
    """Expose a calculation failure without making the OHLCV chart unavailable."""

    common: dict[str, Any] = {
        "id": indicator_id,
        "label": INDICATOR_LABELS[indicator_id],
        "status": "calculation_error",
        "reason": f"{exc.__class__.__name__}: {exc}",
        "diagnostic_only": True,
        "usable_as_trading_gate": False,
        "last": {},
    }
    if indicator_id == INDICATOR_PRIOR_STRUCTURE:
        return {
            **common,
            "channels": {
                lookback: {"upper": [], "lower": []} for lookback in ("4", "16", "48")
            },
            "markers": [],
        }
    if indicator_id == INDICATOR_COMPARABLE_VOLATILITY:
        return {
            **common,
            "volatility_percentile": [],
            "fast_slow_ratio_score": [],
            "range_shock_score": [],
        }
    return {**common, "rvol_score": [], "rvol": []}


def _market_context_markers(
    overlay: dict[str, Any],
    candle_frame: pl.DataFrame,
) -> list[dict[str, Any]]:
    """Normalize structure events onto observed chart candles."""

    if candle_frame.is_empty():
        return []
    candle_times = sorted(
        int(value.timestamp()) for value in candle_frame["timestamp"].to_list()
    )
    normalized: list[dict[str, Any]] = []
    for marker in overlay.get("markers") or []:
        try:
            available_time = int(marker["time"])
        except (KeyError, TypeError, ValueError):
            continue
        chart_time = _first_candle_at_or_after(candle_times, available_time)
        if chart_time is None:
            continue
        state = str(marker.get("state") or "structure_context")
        normalized.append(
            {
                **marker,
                "time": chart_time,
                "source": INDICATOR_PRIOR_STRUCTURE,
                "signal_kind": state,
                "available_time": available_time,
            }
        )
    return normalized


def _cusum_markers(
    indicator_frame: pl.DataFrame,
    candle_frame: pl.DataFrame,
) -> list[dict[str, Any]]:
    markers: list[dict[str, Any]] = []
    candle_times = sorted(
        int(value.timestamp()) for value in candle_frame["timestamp"].to_list()
    )
    signal_rows = (
        indicator_frame.filter(pl.col("bull_start") | pl.col("bear_start"))
        .select(["time", "source_timestamp", "bull_start", "bear_start"])
        .to_dicts()
    )
    for row in signal_rows:
        available_time = int(row["time"])
        time_value = _first_candle_at_or_after(candle_times, available_time)
        if time_value is None:
            continue
        source_time = int(row["source_timestamp"].timestamp())
        if row["bull_start"]:
            markers.append(
                {
                    "time": time_value,
                    "position": "belowBar",
                    "color": "#018208",
                    "shape": "arrowUp",
                    "text": "CUSUM bull shift",
                    "source": INDICATOR_CUSUM_TREND,
                    "signal_kind": "bullish_change_candidate",
                    "source_time": source_time,
                    "available_time": available_time,
                }
            )
        elif row["bear_start"]:
            markers.append(
                {
                    "time": time_value,
                    "position": "aboveBar",
                    "color": "#d12208",
                    "shape": "arrowDown",
                    "text": "CUSUM bear shift",
                    "source": INDICATOR_CUSUM_TREND,
                    "signal_kind": "bearish_change_candidate",
                    "source_time": source_time,
                    "available_time": available_time,
                }
            )
    return markers


def _cusum_last_state(indicator_frame: pl.DataFrame) -> dict[str, Any]:
    if indicator_frame.is_empty():
        return {}
    last = indicator_frame.tail(1).to_dicts()[0]
    regime = int(last.get("regime") or 0)
    if regime == 1:
        status = "Bullish"
    elif regime == -1:
        status = "Bearish"
    else:
        status = "Ranging"
    trail_stop = last.get("trail_stop")
    return {
        "as_of": int(last["time"]),
        "source_as_of": int(last["source_timestamp"].timestamp()),
        "status": status,
        "regime": regime,
        "pressure_pct": float(last.get("pressure_pct") or 0.0),
        "trail_stop": None if trail_stop is None else float(trail_stop),
    }


def _ewma_volatility_last_state(indicator_frame: pl.DataFrame) -> dict[str, Any]:
    """Return the newest finite EWMA state for the chart subtitle and UI."""
    valid = indicator_frame.filter(pl.col("ewma_vol_slow_pct").is_not_null())
    if valid.is_empty():
        return {}
    last = valid.tail(1).to_dicts()[0]
    fast = float(last["ewma_vol_fast_pct"])
    medium = float(last["ewma_vol_medium_pct"])
    slow = float(last["ewma_vol_slow_pct"])
    ratio_raw = last.get("fast_slow_ratio")
    ratio = None if ratio_raw is None else float(ratio_raw)
    if ratio is None:
        status = "Unavailable"
    elif ratio >= 1.20:
        status = "Expanding"
    elif ratio <= 0.85:
        status = "Contracting"
    else:
        status = "Stable"
    observations = int(last.get("ewma_observations") or 0)
    maturity_required = 10 * max(EWMA_VOLATILITY_HALF_LIVES)
    return {
        "as_of": int(last["time"]),
        "source_as_of": int(last["source_timestamp"].timestamp()),
        "status": status,
        "fast_pct": fast,
        "medium_pct": medium,
        "slow_pct": slow,
        "fast_slow_ratio": ratio,
        "observations": observations,
        "maturity": "mature" if observations >= maturity_required else "warming",
        "maturity_pct": min(observations / maturity_required, 1.0),
    }


def _value_or_whitespace_series(
    frame: pl.DataFrame,
    *,
    value_col: str,
) -> list[dict[str, float | int]]:
    """Return line data with explicit gaps so missing states are not bridged."""

    if frame.is_empty() or value_col not in frame.columns:
        return []
    series: list[dict[str, float | int]] = []
    for row in frame.select(["time", value_col]).iter_rows(named=True):
        value = row[value_col]
        if value is None:
            series.append({"time": int(row["time"])})
        else:
            series.append({"time": int(row["time"]), "value": float(value)})
    return series


def _trend_overlay(
    signal_frame: pl.DataFrame,
    signal_metadata: dict[str, Any],
) -> dict[str, Any]:
    interval_seconds = timeframe_seconds(str(signal_metadata.get("timeframe") or "1h"))
    max_gap_raw = signal_metadata.get("maximum_tolerated_gap_seconds")
    config = OnlineSignalConfig(
        expected_interval_seconds=interval_seconds,
        max_gap_seconds=(None if max_gap_raw is None else int(max_gap_raw)),
    )
    valid = (
        signal_frame.filter(pl.col("trend_score").is_not_null())
        if not signal_frame.is_empty() and "trend_score" in signal_frame.columns
        else pl.DataFrame()
    )
    partial = (
        any(
            signal_frame[column].drop_nulls().len() > 0
            for column in (
                "trend_component_fast",
                "trend_component_medium",
                "trend_component_slow",
            )
            if column in signal_frame.columns
        )
        if not signal_frame.is_empty()
        else False
    )
    if not valid.is_empty():
        status = "ok"
        reason = None
    elif partial:
        status = "partial_warmup"
        reason = (
            f"Composite trend and Prototype Regime require "
            f"{ONLINE_SIGNAL_MINIMUM_BARS} closed bars; shorter-horizon trend "
            "components are shown where available."
        )
    else:
        status = "warmup_or_no_overlap"
        reason = (
            f"Signal requires at least {ONLINE_SIGNAL_MINIMUM_BARS} closed bars "
            "after the latest reset."
        )
    return {
        "id": INDICATOR_VOLATILITY_SCALED_TREND,
        "label": INDICATOR_LABELS[INDICATOR_VOLATILITY_SCALED_TREND],
        "status": status,
        "reason": reason,
        "unit": "bounded_directional_quality_score",
        "availability": "post_close_usable_next_bar",
        "plotted_at": "earliest_next_bar_execution_time",
        "return_basis": "closed_log_returns",
        "volatility_denominator": "matching_prior_bar_ewma_sigma",
        "horizons_bars": dict(zip(TREND_LABELS, TREND_HORIZONS)),
        "component_formula": "path_efficiency * tanh(vol_scaled_return / 2)",
        "state_thresholds": {
            "aligned_score": config.aligned_score,
            "aligned_quality": config.aligned_quality,
            "developing_score": config.developing_score,
        },
        "diagnostic_only": True,
        "validation_safe": bool(signal_metadata.get("validation_safe", False)),
        "signal_vintage": signal_metadata.get(
            "signal_vintage", "current_source_replay"
        ),
        "validation_warning": signal_metadata.get("validation_warning"),
        "mode": signal_metadata.get("mode", "bounded_request_replay"),
        "algorithm_version": signal_metadata.get(
            "algorithm_version", ONLINE_SIGNAL_VERSION
        ),
        "config_digest": signal_metadata.get("config_digest", config.digest()),
        "source_generation": signal_metadata.get("source_generation"),
        "computed_source_through": signal_metadata.get("computed_source_through"),
        "session_gap_policy": signal_metadata.get(
            "session_gap_policy",
            "carry_only_when_incoming_bar_is_marked_session_open_and_within_tolerance",
        ),
        "fast": _value_or_whitespace_series(
            signal_frame, value_col="trend_component_fast"
        ),
        "medium": _value_or_whitespace_series(
            signal_frame, value_col="trend_component_medium"
        ),
        "slow": _value_or_whitespace_series(
            signal_frame, value_col="trend_component_slow"
        ),
        "score": _value_or_whitespace_series(signal_frame, value_col="trend_score"),
        "path_quality": _value_or_whitespace_series(
            signal_frame, value_col="path_quality"
        ),
        "last": _trend_last_state(valid),
    }


def _trend_last_state(valid: pl.DataFrame) -> dict[str, Any]:
    if valid.is_empty():
        return {}
    last = valid.tail(1).to_dicts()[0]
    return {
        "as_of": int(last["time"]),
        "source_as_of": int(last["source_timestamp"].timestamp()),
        "status": str(last["trend_state"]),
        "state_code": int(last["trend_state_code"]),
        "fast": float(last["trend_component_fast"]),
        "medium": float(last["trend_component_medium"]),
        "slow": float(last["trend_component_slow"]),
        "score": float(last["trend_score"]),
        "path_quality": float(last["path_quality"]),
        "agreement": float(last["trend_agreement"]),
    }


def _trend_markers(
    signal_frame: pl.DataFrame,
    candle_frame: pl.DataFrame,
) -> list[dict[str, Any]]:
    if signal_frame.is_empty():
        return []
    candle_times = sorted(
        int(value.timestamp()) for value in candle_frame["timestamp"].to_list()
    )
    markers: list[dict[str, Any]] = []
    rows = signal_frame.filter(
        pl.col("trend_bull_start") | pl.col("trend_bear_start")
    ).select(["time", "trend_bull_start", "trend_bear_start"])
    for row in rows.iter_rows(named=True):
        available_time = int(row["time"])
        time_value = _first_candle_at_or_after(candle_times, available_time)
        if time_value is None:
            continue
        bullish = bool(row["trend_bull_start"])
        markers.append(
            {
                "time": time_value,
                "position": "belowBar" if bullish else "aboveBar",
                "color": "#2a9d8f" if bullish else "#d1495b",
                "shape": "arrowUp" if bullish else "arrowDown",
                "text": "Trend +" if bullish else "Trend -",
            }
        )
    return markers


def _online_regime_overlay(
    signal_frame: pl.DataFrame,
    signal_metadata: dict[str, Any],
) -> dict[str, Any]:
    valid = (
        signal_frame.filter(pl.col("regime_state").is_not_null())
        if not signal_frame.is_empty() and "regime_state" in signal_frame.columns
        else pl.DataFrame()
    )
    reason = (
        signal_metadata.get("reason")
        if not valid.is_empty()
        else (
            f"Prototype Regime requires at least {ONLINE_SIGNAL_MINIMUM_BARS} "
            "closed bars after the latest reset."
        )
    )
    state_band: list[dict[str, Any]] = []
    if not signal_frame.is_empty() and "regime_state" in signal_frame.columns:
        for row in signal_frame.select(["time", "regime_state"]).iter_rows(named=True):
            if row["regime_state"] is None:
                state_band.append({"time": int(row["time"])})
            else:
                state = int(row["regime_state"])
                state_band.append(
                    {
                        "time": int(row["time"]),
                        "value": 1.0,
                        "color": _regime_color(state),
                    }
                )
    return {
        "id": INDICATOR_ONLINE_REGIME,
        "label": INDICATOR_LABELS[INDICATOR_ONLINE_REGIME],
        "status": "ok" if not valid.is_empty() else "warmup_or_no_overlap",
        "reason": reason,
        "model": "fixed_prototype_gaussian_hmm_forward_v1",
        "trained_model": False,
        "calibrated_model": False,
        "diagnostic_only": True,
        "usable_as_trading_gate": False,
        "weight_semantics": (
            "forward_filter_posterior_under_fixed_untrained_prototypes"
        ),
        "change_risk_semantics": (
            "max(filtered_pairwise_state_switch_probability, "
            "transition_prototype_weight); uncalibrated diagnostic heuristic"
        ),
        "validation_safe": bool(signal_metadata.get("validation_safe", False)),
        "signal_vintage": signal_metadata.get(
            "signal_vintage", "current_source_replay"
        ),
        "validation_warning": signal_metadata.get("validation_warning"),
        "filter_mode": "one_step_forward_only",
        "availability": "post_close_usable_next_bar",
        "plotted_at": "earliest_next_bar_execution_time",
        "state_labels": list(REGIME_LABELS),
        "change_risk_threshold": OnlineSignalConfig().change_risk_threshold,
        "mode": signal_metadata.get("mode", "bounded_request_replay"),
        "algorithm_version": signal_metadata.get(
            "algorithm_version", ONLINE_SIGNAL_VERSION
        ),
        "config_digest": signal_metadata.get("config_digest"),
        "source_generation": signal_metadata.get("source_generation"),
        "seed_origin": signal_metadata.get("seed_origin"),
        "computed_source_through": signal_metadata.get("computed_source_through"),
        "available_through": signal_metadata.get("available_through"),
        "replayed": signal_metadata.get("replayed"),
        "appended_bars": signal_metadata.get("appended_bars"),
        "marker_alignment": "first_observed_candle_at_or_after_availability",
        "state_band": state_band,
        "bull": _value_or_whitespace_series(
            signal_frame, value_col="regime_probability_bull"
        ),
        "bear": _value_or_whitespace_series(
            signal_frame, value_col="regime_probability_bear"
        ),
        "range": _value_or_whitespace_series(
            signal_frame, value_col="regime_probability_range"
        ),
        "transition": _value_or_whitespace_series(
            signal_frame, value_col="regime_probability_transition"
        ),
        "entropy": _value_or_whitespace_series(
            signal_frame, value_col="regime_entropy"
        ),
        "filtered_switch_probability": _value_or_whitespace_series(
            signal_frame, value_col="regime_filtered_switch_probability"
        ),
        "change_risk": _value_or_whitespace_series(
            signal_frame, value_col="regime_change_risk"
        ),
        "last": _online_regime_last_state(valid),
    }


def _unavailable_regime_overlay(signal_metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": INDICATOR_ONLINE_REGIME,
        "label": INDICATOR_LABELS[INDICATOR_ONLINE_REGIME],
        "status": signal_metadata.get("status", "unavailable"),
        "reason": signal_metadata.get("reason", "Online regime is unavailable."),
        "model": "fixed_prototype_gaussian_hmm_forward_v1",
        "trained_model": False,
        "diagnostic_only": True,
        "filter_mode": "one_step_forward_only",
        "availability": "post_close_usable_next_bar",
        "plotted_at": "earliest_next_bar_execution_time",
        "state_labels": list(REGIME_LABELS),
        "state_band": [],
        "bull": [],
        "bear": [],
        "range": [],
        "transition": [],
        "entropy": [],
        "filtered_switch_probability": [],
        "change_risk": [],
        "last": {},
    }


def _online_regime_last_state(valid: pl.DataFrame) -> dict[str, Any]:
    if valid.is_empty():
        return {}
    last = valid.tail(1).to_dicts()[0]
    return {
        "as_of": int(last["time"]),
        "source_as_of": int(last["source_timestamp"].timestamp()),
        "state": int(last["regime_state"]),
        "status": str(last["regime_label"]),
        "max_weight": float(last["regime_confidence"]),
        "entropy": float(last["regime_entropy"]),
        "filtered_switch_probability": float(
            last["regime_filtered_switch_probability"]
        ),
        "change_risk": float(last["regime_change_risk"]),
        "risk_active": bool(last["regime_risk_active"]),
        "duration_bars": int(last["regime_state_duration_bars"]),
        "predictive_state_weight": (
            None
            if last.get("regime_predictive_state_probability") is None
            else float(last["regime_predictive_state_probability"])
        ),
    }


def _online_regime_markers(
    signal_frame: pl.DataFrame,
    candle_frame: pl.DataFrame,
) -> list[dict[str, Any]]:
    if signal_frame.is_empty():
        return []
    candle_times = sorted(
        int(value.timestamp()) for value in candle_frame["timestamp"].to_list()
    )
    rows = signal_frame.filter(pl.col("regime_risk_start")).select(
        ["time", "regime_risk_start"]
    )
    markers: list[dict[str, Any]] = []
    for row in rows.iter_rows(named=True):
        available_time = int(row["time"])
        time_value = _first_candle_at_or_after(candle_times, available_time)
        if time_value is None:
            continue
        if bool(row["regime_risk_start"]):
            markers.append(
                {
                    "time": time_value,
                    "position": "aboveBar",
                    "color": "#d1495b",
                    "shape": "square",
                    "text": "Risk",
                }
            )
    return markers


def _first_candle_at_or_after(
    candle_times: list[int], available_time: int
) -> int | None:
    """Map an already-available signal to its first executable chart candle."""

    index = bisect_left(candle_times, available_time)
    return candle_times[index] if index < len(candle_times) else None


def _regime_color(state: int) -> str:
    colors = (
        "rgba(42, 157, 143, 0.24)",
        "rgba(209, 73, 91, 0.24)",
        "rgba(87, 117, 144, 0.20)",
        "rgba(244, 162, 97, 0.28)",
    )
    return colors[state] if 0 <= state < len(colors) else "rgba(127, 73, 222, 0.20)"


def export_ohlcv_payload(
    asset: str = "BTCUSDT",
    timeframe: str = "1h",
    source: str = "canonical",
    start: str | datetime | None = None,
    end: str | datetime | None = None,
    max_bars: int = DEFAULT_MAX_BARS,
    output_path: str | Path = DEFAULT_PAYLOAD_PATH,
    indicator: str | None = INDICATOR_NONE,
    indicators: str | Iterable[str] | None = None,
    cusum_sensitivity: str = DEFAULT_CUSUM_SENSITIVITY,
) -> dict[str, Any]:
    """Write a windowed chart payload and return its metadata."""

    enabled_indicators = normalize_indicators(indicators, indicator=indicator)
    if enabled_indicators:
        indicator_warmup_bars = required_indicator_warmup_bars(
            enabled_indicators,
            timeframe=timeframe,
        )
        frame, metadata, indicator_context = load_ohlcv_window_with_context(
            asset=asset,
            timeframe=timeframe,
            source=source,
            start=start,
            end=end,
            max_bars=max_bars,
            indicator_warmup_bars=indicator_warmup_bars,
        )
    else:
        frame, metadata = load_ohlcv_window(
            asset=asset,
            timeframe=timeframe,
            source=source,
            start=start,
            end=end,
            max_bars=max_bars,
        )
        indicator_context = None
    payload = build_lightweight_charts_payload(
        frame=frame,
        metadata=metadata,
        indicator=indicator,
        indicators=indicators,
        cusum_sensitivity=cusum_sensitivity,
        indicator_context=indicator_context,
        use_live_signal_service=True,
    )

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    metadata = dict(metadata)
    metadata["output_path"] = _relative(output)
    return metadata


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export a bounded OHLCV JSON payload for the local chart viewer."
    )
    parser.add_argument("--asset", default="BTCUSDT")
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--source", default="canonical")
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    parser.add_argument("--max-bars", type=int, default=DEFAULT_MAX_BARS)
    parser.add_argument("--output", default=str(DEFAULT_PAYLOAD_PATH))
    parser.add_argument("--indicator", default=INDICATOR_NONE)
    parser.add_argument("--indicators", default="")
    parser.add_argument("--cusum-sensitivity", default=DEFAULT_CUSUM_SENSITIVITY)
    return parser


def main() -> None:
    args = _build_arg_parser().parse_args()
    metadata = export_ohlcv_payload(
        asset=args.asset,
        timeframe=args.timeframe,
        source=args.source,
        start=args.start,
        end=args.end,
        max_bars=args.max_bars,
        output_path=args.output,
        indicator=args.indicator,
        indicators=args.indicators,
        cusum_sensitivity=args.cusum_sensitivity,
    )
    WEB_DATA_ROOT.mkdir(parents=True, exist_ok=True)
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
