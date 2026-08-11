"""Thread-safe bounded replay and append service for online chart signals."""

from __future__ import annotations

import hashlib
import math
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from typing import Any

import polars as pl
from chart_config import (
    BYBIT_ASSETS,
    PROJECT_ROOT,
    resolve_ohlcv_files,
    timeframe_seconds,
)
from online_signals import (
    ONLINE_SIGNAL_VERSION,
    OnlineSignalConfig,
    OnlineSignalEngine,
)

INGESTION_SAFETY_LAG_SECONDS = 5
SESSION_GAP_TOLERANCE_SECONDS = 4 * 24 * 60 * 60
DEFAULT_SERVICE_REPLAY_BARS = 8_000
MAX_CACHED_STREAMS = 8


class UnsupportedLiveSignalSelection(ValueError):
    """Raised when a stream does not yet have a live replay contract."""


@dataclass
class _CachedStream:
    row_fingerprints: tuple[str, ...]
    engine: OnlineSignalEngine
    output_frame: pl.DataFrame
    source_snapshot: tuple[tuple[str, int, int], ...]
    generation: str
    seed_origin: datetime | None
    computed_source_through: datetime | None
    available_through: datetime | None
    replay_scope: str
    hidden_context_bars: int | None


class LiveSignalService:
    """Maintain selection-keyed causal replay state for chart/live requests.

    The chart passes its visible window plus hidden warm-up rows.  This keeps
    one-minute streams responsive without materializing multi-million-row
    signal journals in memory.  A standalone call falls back to a bounded tail
    replay.  Both paths use the exact same scalar update method as a newly
    closed live bar.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._cache: OrderedDict[tuple[str, str, str, str, str], _CachedStream] = (
            OrderedDict()
        )

    def get(
        self,
        *,
        asset: str,
        timeframe: str,
        source: str,
        now: datetime | None = None,
        replay_frame: pl.DataFrame | None = None,
        visible_start: datetime | None = None,
    ) -> tuple[pl.DataFrame, dict[str, Any]]:
        normalized = (
            asset.strip().upper(),
            timeframe.strip().lower(),
            source.strip().lower(),
        )
        if normalized[2] != "canonical":
            raise UnsupportedLiveSignalSelection(
                "The persistent live signal service is canonical-only. Raw/provider "
                "feeds remain debug sources and use a bounded request replay."
            )
        # Resolution validates that this exact asset/timeframe/source tuple is
        # part of the chart's data contract before any state is created.
        resolution = resolve_ohlcv_files(
            asset=normalized[0], timeframe=normalized[1], source=normalized[2]
        )
        interval_seconds = timeframe_seconds(normalized[1])
        config = build_online_signal_config(
            asset=normalized[0], timeframe=normalized[1]
        )

        current_time = _utc(now or datetime.now(timezone.utc))
        with self._lock:
            if replay_frame is None:
                frame, source_snapshot = _read_stable_source(
                    asset=normalized[0],
                    timeframe=normalized[1],
                    source=normalized[2],
                    max_bars=DEFAULT_SERVICE_REPLAY_BARS,
                )
                replay_scope = "bounded_service_tail_replay"
                hidden_context_bars = None
            else:
                frame = _normalize_replay_frame(replay_frame)
                source_snapshot = _source_snapshot(resolution.files)
                replay_scope = "chart_window_plus_hidden_warmup"
                hidden_context_bars = _hidden_context_count(frame, visible_start)

            closed = _closed_rows(
                frame,
                now=current_time,
                interval_seconds=interval_seconds,
            )
            fingerprints = tuple(
                _row_fingerprint(row) for row in closed.iter_rows(named=True)
            )
            key = (*normalized, ONLINE_SIGNAL_VERSION, config.digest())
            cached = self._cache.get(key)
            replay_from: datetime | None = None
            replay_cause: str | None = None
            appended = 0
            replayed = False

            if cached is not None and _is_exact_prefix(
                cached.row_fingerprints, fingerprints
            ):
                appended = len(fingerprints) - len(cached.row_fingerprints)
                if appended > 0:
                    new_rows = closed.tail(appended)
                    new_outputs = [
                        _update_engine(cached.engine, row)
                        for row in new_rows.iter_rows(named=True)
                    ]
                    new_frame = _signal_frame(new_outputs)
                    cached.output_frame = pl.concat(
                        [cached.output_frame, new_frame], how="vertical_relaxed"
                    )
                cached.row_fingerprints = fingerprints
                cached.source_snapshot = source_snapshot
                cached.generation = _generation(fingerprints, source_snapshot)
                cached.computed_source_through = (
                    closed["timestamp"].max() if not closed.is_empty() else None
                )
                cached.available_through = (
                    cached.output_frame["timestamp"].max()
                    if not cached.output_frame.is_empty()
                    else None
                )
            else:
                replayed = True
                if cached is not None:
                    same_origin = (
                        not closed.is_empty()
                        and cached.seed_origin == closed["timestamp"].min()
                    )
                    if same_origin:
                        replay_cause = "source_revision_or_truncation"
                        mismatch = _first_mismatch(
                            cached.row_fingerprints, fingerprints
                        )
                        if mismatch < closed.height:
                            replay_from = closed["timestamp"][mismatch]
                    else:
                        replay_cause = "bounded_replay_origin_changed"
                else:
                    replay_cause = "cold_start"
                engine = OnlineSignalEngine(config)
                output_rows = [
                    _update_engine(engine, row) for row in closed.iter_rows(named=True)
                ]
                output_frame = _signal_frame(output_rows)
                cached = _CachedStream(
                    row_fingerprints=fingerprints,
                    engine=engine,
                    output_frame=output_frame,
                    source_snapshot=source_snapshot,
                    generation=_generation(fingerprints, source_snapshot),
                    seed_origin=(
                        closed["timestamp"].min() if not closed.is_empty() else None
                    ),
                    computed_source_through=(
                        closed["timestamp"].max() if not closed.is_empty() else None
                    ),
                    available_through=(
                        output_frame["timestamp"].max()
                        if not output_frame.is_empty()
                        else None
                    ),
                    replay_scope=replay_scope,
                    hidden_context_bars=hidden_context_bars,
                )
                self._cache[key] = cached

            cached.replay_scope = replay_scope
            cached.hidden_context_bars = hidden_context_bars
            self._cache.move_to_end(key)
            while len(self._cache) > MAX_CACHED_STREAMS:
                self._cache.popitem(last=False)

            signal_vintage = (
                "current_canonical_replay"
                if normalized[2] == "canonical"
                else "current_source_replay"
            )

            metadata = {
                "status": "ok",
                "mode": "bounded_selection_stream_replay",
                "algorithm_version": ONLINE_SIGNAL_VERSION,
                "config_digest": cached.engine.config.digest(),
                "model": "fixed_prototype_gaussian_hmm_forward_v1",
                "trained_model": False,
                "calibrated_model": False,
                "diagnostic_only": True,
                "usable_as_trading_gate": False,
                "asset": normalized[0],
                "timeframe": normalized[1],
                "source": normalized[2],
                "expected_interval_seconds": interval_seconds,
                "maximum_tolerated_gap_seconds": config.max_gap_seconds,
                "session_gap_policy": (
                    "canonical_is_session_open_bar"
                    if normalized[0] not in BYBIT_ASSETS
                    else "exact_continuous_cadence"
                ),
                "replay_scope": cached.replay_scope,
                "hidden_context_bars": cached.hidden_context_bars,
                "source_generation": cached.generation,
                "source_snapshot": [
                    {"path": path, "size": size, "mtime_ns": mtime_ns}
                    for path, size, mtime_ns in cached.source_snapshot
                ],
                "seed_origin": _iso(cached.seed_origin),
                "computed_source_through": _iso(cached.computed_source_through),
                "available_through": _iso(cached.available_through),
                "closed_bar_count": len(cached.row_fingerprints),
                "warmup_required_closed_bars": max(config.horizons) + 1,
                "replayed": replayed,
                "replay_cause": replay_cause,
                "replay_from": _iso(replay_from),
                "appended_bars": appended,
                "restart_behavior": "deterministic_bounded_context_replay",
                "availability": "post_close_usable_next_bar",
                "ingestion_safety_lag_seconds": INGESTION_SAFETY_LAG_SECONDS,
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
            }
            return cached.output_frame, metadata

    def clear(self) -> None:
        """Clear derived runtime state; primarily useful for deterministic tests."""

        with self._lock:
            self._cache.clear()


LIVE_SIGNAL_SERVICE = LiveSignalService()


def get_live_signal_frame(
    *,
    asset: str,
    timeframe: str,
    source: str,
    now: datetime | None = None,
    replay_frame: pl.DataFrame | None = None,
    visible_start: datetime | None = None,
) -> tuple[pl.DataFrame, dict[str, Any]]:
    """Return materialized online outputs for any supported chart selection."""

    return LIVE_SIGNAL_SERVICE.get(
        asset=asset,
        timeframe=timeframe,
        source=source,
        now=now,
        replay_frame=replay_frame,
        visible_start=visible_start,
    )


def _read_stable_source(
    *, asset: str, timeframe: str, source: str, max_bars: int | None = None
) -> tuple[pl.DataFrame, tuple[tuple[str, int, int], ...]]:
    resolution = resolve_ohlcv_files(asset=asset, timeframe=timeframe, source=source)
    last_error: Exception | None = None
    for _ in range(2):
        before = _source_snapshot(resolution.files)
        try:
            lazy = pl.scan_parquet([str(path) for path in resolution.files])
            schema = lazy.collect_schema()
            expressions: list[pl.Expr] = [
                pl.col("timestamp"),
                pl.col("open").cast(pl.Float64),
                pl.col("high").cast(pl.Float64),
                pl.col("low").cast(pl.Float64),
                pl.col("close").cast(pl.Float64),
                pl.col("volume").cast(pl.Float64),
            ]
            expressions.extend(
                pl.col(column)
                for column in (
                    "calendar_id",
                    "is_market_open",
                    "is_session_open_bar",
                    "is_weekly_open_bar",
                    "minutes_since_prev_real_bar",
                )
                if column in schema
            )
            lazy = (
                lazy.select(expressions)
                .filter(pl.col("timestamp").is_not_null())
                .unique(subset=["timestamp"], keep="last")
                .sort("timestamp")
            )
            if max_bars is not None:
                lazy = lazy.tail(max_bars)
            frame = lazy.collect()
        except (OSError, pl.exceptions.PolarsError) as exc:
            last_error = exc
            continue
        after = _source_snapshot(resolution.files)
        if before == after:
            return frame, after
    if last_error is not None:
        raise RuntimeError(f"Live source could not be read consistently: {last_error}")
    raise RuntimeError("Live source changed while it was being read; retry the request")


def _closed_rows(
    frame: pl.DataFrame,
    *,
    now: datetime,
    interval_seconds: int,
) -> pl.DataFrame:
    cutoff = now - timedelta(seconds=INGESTION_SAFETY_LAG_SECONDS)
    return frame.filter(
        pl.col("timestamp") + pl.duration(seconds=interval_seconds) <= pl.lit(cutoff)
    ).sort("timestamp")


def _update_engine(engine: OnlineSignalEngine, row: dict[str, Any]) -> dict[str, Any]:
    return engine.update(
        timestamp=row["timestamp"],
        open_value=row.get("open"),
        high=row.get("high"),
        low=row.get("low"),
        close=row.get("close"),
        volume=row.get("volume"),
        is_final=True,
        scheduled_gap=bool(row.get("is_session_open_bar", False)),
    )


def _signal_frame(rows: list[dict[str, Any]]) -> pl.DataFrame:
    """Keep the chart-facing live journal compact while retaining audit fields."""

    if not rows:
        return pl.DataFrame()
    columns = [
        "source_timestamp",
        "timestamp",
        "available_at",
        "earliest_execution_at",
        "availability",
        "status",
        "trend_component_fast",
        "trend_component_medium",
        "trend_component_slow",
        "trend_score",
        "path_quality",
        "trend_agreement",
        "trend_state_code",
        "trend_state",
        "trend_bull_start",
        "trend_bear_start",
        "trend_exit",
        "volatility_pressure",
        "range_pressure",
        "regime_model",
        "regime_state",
        "regime_label",
        "regime_probability_bull",
        "regime_probability_bear",
        "regime_probability_range",
        "regime_probability_transition",
        "regime_confidence",
        "regime_entropy",
        "regime_filtered_switch_probability",
        "regime_change_risk",
        "regime_risk_active",
        "regime_risk_start",
        "regime_state_changed",
        "regime_state_duration_bars",
        "regime_predictive_state_probability",
        "regime_transition_probability",
    ]
    frame = pl.DataFrame(rows, infer_schema_length=None)
    return frame.select([column for column in columns if column in frame.columns])


def _normalize_replay_frame(frame: pl.DataFrame) -> pl.DataFrame:
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(
            "Online replay frame is missing required columns: "
            + ", ".join(sorted(missing))
        )
    expressions: list[pl.Expr] = [
        pl.col("timestamp"),
        pl.col("open").cast(pl.Float64),
        pl.col("high").cast(pl.Float64),
        pl.col("low").cast(pl.Float64),
        pl.col("close").cast(pl.Float64),
        pl.col("volume").cast(pl.Float64),
    ]
    expressions.extend(
        pl.col(column)
        for column in (
            "calendar_id",
            "is_market_open",
            "is_session_open_bar",
            "is_weekly_open_bar",
            "minutes_since_prev_real_bar",
        )
        if column in frame.columns
    )
    return (
        frame.select(expressions)
        .filter(pl.col("timestamp").is_not_null())
        .unique(subset=["timestamp"], keep="last")
        .sort("timestamp")
    )


def _hidden_context_count(
    frame: pl.DataFrame, visible_start: datetime | None
) -> int | None:
    if visible_start is None or frame.is_empty():
        return None
    start = _utc(visible_start)
    return int(frame.filter(pl.col("timestamp") < pl.lit(start)).height)


def build_online_signal_config(*, asset: str, timeframe: str) -> OnlineSignalConfig:
    """Return the causal cadence policy for one chart selection."""

    interval_seconds = timeframe_seconds(timeframe)
    max_gap_seconds = (
        interval_seconds
        if asset in BYBIT_ASSETS
        else max(interval_seconds, SESSION_GAP_TOLERANCE_SECONDS)
    )
    return OnlineSignalConfig(
        expected_interval_seconds=interval_seconds,
        max_gap_seconds=max_gap_seconds,
    )


def _source_snapshot(paths: tuple[Path, ...]) -> tuple[tuple[str, int, int], ...]:
    rows = []
    for path in paths:
        stat = path.stat()
        rows.append((_relative(path), int(stat.st_size), int(stat.st_mtime_ns)))
    return tuple(rows)


def _row_fingerprint(row: dict[str, Any]) -> str:
    parts = [_iso(_utc(row["timestamp"])) or ""]
    for column in ("open", "high", "low", "close", "volume"):
        value = row.get(column)
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            parts.append("null")
            continue
        parts.append(numeric.hex() if math.isfinite(numeric) else repr(numeric))
    parts.append("session_open" if row.get("is_session_open_bar") else "regular")
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _is_exact_prefix(old: tuple[str, ...], new: tuple[str, ...]) -> bool:
    return len(new) >= len(old) and new[: len(old)] == old


def _first_mismatch(old: tuple[str, ...], new: tuple[str, ...]) -> int:
    for idx, (left, right) in enumerate(zip(old, new)):
        if left != right:
            return idx
    return min(len(old), len(new))


def _generation(
    fingerprints: tuple[str, ...], source_snapshot: tuple[tuple[str, int, int], ...]
) -> str:
    digest = hashlib.sha256()
    for fingerprint in fingerprints:
        digest.update(fingerprint.encode("ascii"))
    for path, size, mtime_ns in source_snapshot:
        digest.update(f"{path}|{size}|{mtime_ns}".encode())
    return digest.hexdigest()[:20]


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        return str(path)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _utc(value).isoformat().replace("+00:00", "Z")
