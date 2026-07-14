"""Read-only live-chart overlay from the first-seen forward-paper journal.

Canonical Parquet remains the historical source of record.  This module reads
committed ``source_bar_observed`` events from the SQLite WAL journal and layers
their finalized one-minute OHLCV rows over an in-memory canonical chart frame.
It never writes or rematerializes canonical files.

Higher-timeframe rows are UTC-anchored and emitted only after their scheduled
bucket end.  For continuous crypto feeds, every source minute must be present;
session-based assets retain non-empty closed buckets because scheduled market
closures legitimately make those candles sparse.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import polars as pl
from chart_config import (
    BYBIT_ASSETS,
    CANONICAL_TIMEFRAMES,
    normalize_asset,
    normalize_timeframe,
    timeframe_seconds,
)

from .runtime import default_state_dir, read_json_object
from .supervisor import inspect_process

DATABASE_FILENAME = "forward_paper.sqlite3"
STATUS_FILENAME = "status.json"
DEFAULT_MAX_SOURCE_ROWS = 100_000
DEFAULT_MAX_META_SHADOW_ROWS = 2_000
MAX_META_SHADOW_ROWS = 5_000
OVERLAY_VERSION = "first_seen_chart_overlay_v1"
META_SHADOW_OVERLAY_VERSION = "forward_meta_shadow_chart_v1"
_OHLCV_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")
_META_SHADOW_EVENT_TYPES = ("meta_shadow_prediction", "meta_shadow_label")
_REDACTED_META_REASON = "redacted_unrecognized_reason"
_PUBLIC_SCORE_REASONS = frozenset(
    {
        "accepted",
        "artifact_checksum_mismatch",
        "artifact_created_after_decision",
        "artifact_invalid",
        "artifact_labels_mature_after_decision",
        "artifact_not_configured",
        "artifact_not_found",
        "artifact_read_error",
        "artifact_stale",
        "artifact_trained_after_decision",
        "asset_scope_mismatch",
        "decision_time_required_for_staleness_check",
        "disabled",
        "feature_names_mismatch",
        "feature_schema_mismatch",
        "feature_snapshot_invalid",
        "features_not_mapping",
        "invalid_expected_feature_schema",
        "invalid_feature_values",
        "invalid_inference_context",
        "invalid_max_model_age",
        "invalid_runtime_context",
        "missing_features",
        "policy_digest_mismatch",
        "probability_below_threshold",
        "risk_unit_unavailable",
        "timeframe_scope_mismatch",
    }
)
_PUBLIC_COUNTERFACTUAL_REASONS = _PUBLIC_SCORE_REASONS | {
    "probability_below_required_threshold",
    "required_probability_unavailable",
    "static_payoff_untradeable_after_costs",
}
_PUBLIC_LABEL_REASONS = frozenset(
    {
        "barrier_invalid_at_actual_shadow_fill",
        "continuous_market_data_gap_before_entry",
        "continuous_market_data_gap_unknown_path",
        "continuous_market_missing_eligible_real_minute",
        "continuous_market_non_real_minute_before_entry",
        "gap_through_stop",
        "gap_through_target",
        "maximum_finalized_target_bars_reached",
        "maximum_holding_bars_reached",
        "same_bar_both_barriers_stop_first_primary",
        "stop_touched",
        "target_touched",
    }
)


class LiveChartOverlayError(RuntimeError):
    """Raised when an existing journal violates the live-overlay contract."""


@dataclass(frozen=True)
class LiveJournalSnapshot:
    """One bounded, committed view of first-seen minute observations."""

    frame: pl.DataFrame
    metadata: dict[str, Any]


@dataclass(frozen=True)
class LiveChartOverlay:
    """Canonical chart rows with a read-only live tail and cache metadata."""

    frame: pl.DataFrame
    metadata: dict[str, Any]


@dataclass(frozen=True)
class MetaShadowChartOverlay:
    """Bounded, redacted META SHADOW evidence for one forward stream."""

    payload: dict[str, Any]


def load_live_chart_overlay(
    canonical_frame: pl.DataFrame,
    *,
    asset: str,
    timeframe: str,
    database_path: str | Path | None = None,
    status_path: str | Path | None = None,
    run_id: str | None = None,
    as_of: str | datetime | None = None,
    start: str | datetime | None = None,
    end: str | datetime | None = None,
    canonical_minutes: pl.DataFrame | None = None,
    max_source_rows: int = DEFAULT_MAX_SOURCE_ROWS,
    max_bars: int | None = None,
) -> LiveChartOverlay:
    """Layer finalized first-seen rows over a canonical target-timeframe frame.

    ``canonical_minutes`` is optional.  When supplied, only its rows before the
    first journal minute may complete the initial target bucket; journal rows
    remain authoritative from that point onward.  Pass the chart request's
    explicit ``start``/``end`` values so the overlay respects historical views.
    """

    normalized_asset = normalize_asset(asset)
    normalized_timeframe = _canonical_timeframe(timeframe)
    clock = _parse_utc(as_of) or datetime.now(timezone.utc)
    database = (
        Path(database_path).expanduser().resolve()
        if database_path is not None
        else default_state_dir() / DATABASE_FILENAME
    )
    status = (
        Path(status_path).expanduser().resolve()
        if status_path is not None
        else database.parent / STATUS_FILENAME
    )
    snapshot = read_first_seen_minutes(
        asset=normalized_asset,
        database_path=database,
        status_path=status,
        run_id=run_id,
        as_of=clock,
        max_rows=max_source_rows,
    )
    closed_boundary = _bucket_start(clock, timeframe_seconds(normalized_timeframe))
    base_metadata = {
        **snapshot.metadata,
        "version": OVERLAY_VERSION,
        "asset": normalized_asset,
        "timeframe": normalized_timeframe,
        "as_of": _iso_utc(clock),
        "closed_bucket_boundary": _iso_utc(closed_boundary),
        "canonical_mutated": False,
        "canonical_is_historical_base": True,
        "live_observation_wins_timestamp_collision": True,
        "higher_timeframes_closed_only": True,
    }
    base_metadata["generation"] = _generation_token(
        run_id=base_metadata.get("run_id"),
        asset=normalized_asset,
        timeframe=normalized_timeframe,
        source_sequence_no=base_metadata.get("latest_source_sequence_no"),
        source_event_hash=base_metadata.get("latest_source_event_hash"),
        closed_boundary=closed_boundary,
    )

    if snapshot.frame.is_empty():
        bounded = _bounded_frame(canonical_frame, max_bars=max_bars)
        return LiveChartOverlay(
            frame=bounded,
            metadata={
                **base_metadata,
                "target_rows_built": 0,
                "canonical_rows_replaced": 0,
                "live_rows_appended": 0,
                "result_row_count": bounded.height,
            },
        )

    live_target = aggregate_causal_live_minutes(
        snapshot.frame,
        asset=normalized_asset,
        timeframe=normalized_timeframe,
        as_of=clock,
        canonical_minutes=canonical_minutes,
    )
    start_dt = _parse_utc(start)
    end_dt = _parse_utc(end)
    if start_dt is not None:
        live_target = live_target.filter(pl.col("timestamp") >= pl.lit(start_dt))
    if end_dt is not None:
        live_target = live_target.filter(pl.col("timestamp") <= pl.lit(end_dt))

    canonical_timestamps = set(_timestamp_values(canonical_frame))
    live_timestamps = set(_timestamp_values(live_target))
    replaced = len(canonical_timestamps & live_timestamps)
    appended = len(live_timestamps - canonical_timestamps)
    merged = merge_canonical_and_live(canonical_frame, live_target)
    merged = _bounded_frame(merged, max_bars=max_bars)
    return LiveChartOverlay(
        frame=merged,
        metadata={
            **base_metadata,
            "target_rows_built": live_target.height,
            "canonical_rows_replaced": replaced,
            "live_rows_appended": appended,
            "result_row_count": merged.height,
            "live_target_start": _frame_iso_min(live_target),
            "live_target_end": _frame_iso_max(live_target),
        },
    )


def read_first_seen_minutes(
    *,
    asset: str,
    database_path: str | Path,
    status_path: str | Path | None = None,
    run_id: str | None = None,
    as_of: str | datetime | None = None,
    max_rows: int = DEFAULT_MAX_SOURCE_ROWS,
) -> LiveJournalSnapshot:
    """Read a bounded active-run snapshot without taking the writer lock."""

    normalized_asset = normalize_asset(asset)
    if isinstance(max_rows, bool) or not isinstance(max_rows, int) or max_rows <= 0:
        raise ValueError("max_rows must be a positive integer")
    database = Path(database_path).expanduser().resolve()
    clock = _parse_utc(as_of) or datetime.now(timezone.utc)
    empty = _empty_minute_frame()
    status = _status_payload(status_path)
    runtime_metadata = _runtime_metadata(
        database=database,
        status=status,
        asset=normalized_asset,
        clock=clock,
    )
    if not database.is_file():
        return LiveJournalSnapshot(
            empty,
            {
                **_unavailable_metadata(database, reason="journal_not_found"),
                **runtime_metadata,
            },
        )

    requested_run_id = _selected_run_id(
        explicit=run_id,
        status=status,
    )
    try:
        connection = _read_only_connection(database)
        with connection:
            selected_run_id = requested_run_id or _latest_run_id(connection)
            if selected_run_id is None:
                return LiveJournalSnapshot(
                    empty,
                    {
                        **_unavailable_metadata(database, reason="journal_has_no_runs"),
                        **runtime_metadata,
                    },
                )
            if not _run_exists(connection, selected_run_id):
                raise LiveChartOverlayError(
                    f"Selected forward-paper run does not exist: {selected_run_id}"
                )
            rows = connection.execute(
                """
                SELECT sequence_no, event_id, observed_at, event_hash, payload_json
                FROM events
                WHERE run_id = ?
                  AND event_type = 'source_bar_observed'
                  AND stream_id = ?
                ORDER BY sequence_no DESC
                LIMIT ?
                """,
                (selected_run_id, f"source:{normalized_asset}", max_rows + 1),
            ).fetchall()
    except sqlite3.Error as exc:
        raise LiveChartOverlayError(
            f"Could not read forward-paper journal {database}: {exc}"
        ) from exc
    finally:
        if "connection" in locals():
            connection.close()

    truncated = len(rows) > max_rows
    rows = rows[:max_rows]
    parsed: list[dict[str, Any]] = []
    for sqlite_row in reversed(rows):
        parsed_row = _parse_source_event(
            sqlite_row,
            expected_asset=normalized_asset,
        )
        if parsed_row["overlay_observed_at"] > clock:
            continue
        # The provider contract says source minutes are finalized.  Retain an
        # independent causal guard for synthetic journals and historical reads.
        if parsed_row["timestamp"] + timedelta(minutes=1) > clock:
            continue
        parsed.append(parsed_row)

    # A healthy run has no repeated source timestamps.  Keep the later chain
    # event defensively so a live observation still wins deterministically.
    by_timestamp: dict[datetime, dict[str, Any]] = {}
    for row in parsed:
        by_timestamp[row["timestamp"]] = row
    parsed = sorted(by_timestamp.values(), key=lambda row: row["timestamp"])
    frame = _minute_frame(parsed)
    latest = parsed[-1] if parsed else None
    metadata = {
        "available": True,
        "status": "active" if latest is not None else "no_source_rows_as_of",
        "reason": None,
        "database_path": str(database),
        "run_id": selected_run_id,
        "source_vintage": "append_only_first_seen",
        "source_rows_loaded": len(parsed),
        "source_rows_truncated": truncated,
        "max_source_rows": max_rows,
        "latest_source_sequence_no": (
            None if latest is None else latest["overlay_sequence_no"]
        ),
        "latest_source_event_hash": (
            None if latest is None else latest["overlay_event_hash"]
        ),
        "latest_observed_at": (
            None if latest is None else _iso_utc(latest["overlay_observed_at"])
        ),
        "latest_source_timestamp": (
            None if latest is None else _iso_utc(latest["timestamp"])
        ),
        "provider": None if latest is None else latest["overlay_provider"],
        "quality": None if latest is None else latest["overlay_quality"],
        "expected_delay_seconds": (
            None if latest is None else latest["overlay_expected_delay_seconds"]
        ),
        **runtime_metadata,
    }
    metadata.update(_freshness_metadata(metadata, clock=clock))
    return LiveJournalSnapshot(frame, metadata)


def read_meta_shadow_chart_overlay(
    *,
    asset: str,
    timeframe: str,
    database_path: str | Path | None = None,
    status_path: str | Path | None = None,
    run_id: str | None = None,
    as_of: str | datetime | None = None,
    start: str | datetime | None = None,
    end: str | datetime | None = None,
    max_rows: int = DEFAULT_MAX_META_SHADOW_ROWS,
) -> MetaShadowChartOverlay:
    """Read stored forward META SHADOW decisions and label-mature outcomes.

    The reader opens SQLite in query-only mode and selects exactly one run and
    one storage stream.  It exports only a small allowlist of audit fields;
    feature snapshots, artifact paths, coefficients, and other model internals
    never leave the journal.  Outcome display time is the immutable journal
    ``occurred_at`` value, which the writer defines as ``label_known_at``.
    """

    normalized_asset = normalize_asset(asset)
    normalized_timeframe = _canonical_timeframe(timeframe)
    if (
        isinstance(max_rows, bool)
        or not isinstance(max_rows, int)
        or max_rows <= 0
        or max_rows > MAX_META_SHADOW_ROWS
    ):
        raise ValueError(
            f"max_rows must be an integer between 1 and {MAX_META_SHADOW_ROWS}"
        )
    clock = _parse_utc(as_of) or datetime.now(timezone.utc)
    start_dt = _parse_utc(start)
    requested_end = _parse_utc(end)
    end_dt = min(clock, requested_end) if requested_end is not None else clock
    if start_dt is not None and start_dt > end_dt:
        raise ValueError("start must be before or equal to the effective end")
    database = (
        Path(database_path).expanduser().resolve()
        if database_path is not None
        else default_state_dir() / DATABASE_FILENAME
    )
    status = (
        Path(status_path).expanduser().resolve()
        if status_path is not None
        else database.parent / STATUS_FILENAME
    )
    status_payload = _status_payload(status) if status.is_file() else None
    requested_run_id = _selected_run_id(explicit=run_id, status=status_payload)
    base = {
        "version": META_SHADOW_OVERLAY_VERSION,
        "mode": "shadow",
        "asset": normalized_asset,
        "timeframe": normalized_timeframe,
        "run_id": requested_run_id,
        "stream_id": None,
        "as_of": _iso_utc(clock),
        "start": _iso_utc(start_dt),
        "end": _iso_utc(end_dt),
        "available": False,
        "status": "unavailable",
        "reason": None,
        "scores": [],
        "outcome_markers": [],
        "audit": [],
        "counts": {
            "events": 0,
            "predictions": 0,
            "available_scores": 0,
            "unavailable_predictions": 0,
            "accepted": 0,
            "rejected": 0,
            "labels": 0,
        },
        "rows_truncated": False,
        "max_rows": max_rows,
        "diagnostic_only": True,
        "affects_orders": False,
        "affects_positions": False,
        "real_order_routing": False,
        "time_semantics": {
            "prediction": "immutable_journal_occurred_at_equals_decision_at",
            "outcome": "immutable_journal_occurred_at_equals_label_known_at",
            "touch_time_exported": False,
        },
    }
    if not database.is_file():
        return MetaShadowChartOverlay({**base, "reason": "journal_not_found"})

    connection: sqlite3.Connection | None = None
    try:
        connection = _read_only_connection(database)
        selected_run_id = requested_run_id or _latest_run_id(connection)
        if selected_run_id is None:
            return MetaShadowChartOverlay({**base, "reason": "journal_has_no_runs"})
        if not _run_exists(connection, selected_run_id):
            raise LiveChartOverlayError(
                f"Selected forward-paper run does not exist: {selected_run_id}"
            )
        storage_stream_id = (
            f"{selected_run_id}:{normalized_asset}|{normalized_timeframe}"
        )
        clauses = [
            "run_id = ?",
            "stream_id = ?",
            "event_type IN (?, ?)",
            "occurred_at <= ?",
            "observed_at <= ?",
        ]
        params: list[Any] = [
            selected_run_id,
            storage_stream_id,
            *_META_SHADOW_EVENT_TYPES,
            _sqlite_timestamp(end_dt),
            _sqlite_timestamp(clock),
        ]
        if start_dt is not None:
            clauses.append("occurred_at >= ?")
            params.append(_sqlite_timestamp(start_dt))
        rows = connection.execute(
            f"""
            SELECT sequence_no, event_id, event_type, occurred_at, observed_at,
                   payload_json
            FROM events
            WHERE {" AND ".join(clauses)}
            ORDER BY sequence_no DESC
            LIMIT ?
            """,
            (*params, max_rows + 1),
        ).fetchall()
    except sqlite3.Error as exc:
        raise LiveChartOverlayError(
            f"Could not read forward-paper META SHADOW journal: {exc}"
        ) from exc
    finally:
        if connection is not None:
            connection.close()

    truncated = len(rows) > max_rows
    rows = list(reversed(rows[:max_rows]))
    parsed = [
        _parse_meta_shadow_event(
            row,
            expected_asset=normalized_asset,
            expected_timeframe=normalized_timeframe,
        )
        for row in rows
    ]
    prediction_by_shadow_id = {
        item["shadow_event_id"]: item
        for item in parsed
        if item["event_type"] == "meta_shadow_prediction"
    }
    audit: list[dict[str, Any]] = []
    scores: list[dict[str, Any]] = []
    outcome_markers: list[dict[str, Any]] = []
    counts = dict(base["counts"])
    for item in parsed:
        counts["events"] += 1
        if item["event_type"] == "meta_shadow_prediction":
            counts["predictions"] += 1
            if item["available"] and item["probability"] is not None:
                counts["available_scores"] += 1
                scores.append(
                    {
                        "time": item["occurred_at_epoch"],
                        "value": item["probability"],
                        "shadow_event_id": item["shadow_event_id"],
                        "side": item["side"],
                        "accepted": item["accepted"],
                        "reason": item["acceptance_reason"],
                        "model_digest": item["model_digest"],
                        "policy_digest": item["policy_digest"],
                    }
                )
            else:
                counts["unavailable_predictions"] += 1
            if item["accepted"] is True:
                counts["accepted"] += 1
            elif item["accepted"] is False:
                counts["rejected"] += 1
        else:
            counts["labels"] += 1
            prediction = prediction_by_shadow_id.get(item["shadow_event_id"], {})
            side = item["side"] or prediction.get("side")
            outcome_markers.append(_meta_shadow_outcome_marker(item, side=side))
            item = {
                **item,
                "side": side,
                "accepted": prediction.get("accepted"),
                "acceptance_reason": prediction.get("acceptance_reason"),
                "model_digest": item["model_digest"] or prediction.get("model_digest"),
            }
        audit.append(_redacted_meta_shadow_audit(item))

    stream_id = f"{selected_run_id}:{normalized_asset}|{normalized_timeframe}"
    has_events = bool(parsed)
    status_value = (
        "ok"
        if scores
        else "events_without_available_scores"
        if has_events
        else "no_meta_shadow_events"
    )
    reason = (
        None
        if scores
        else "no_available_predictions"
        if has_events
        else "meta_shadow_not_enabled_or_no_signals_for_selection"
    )
    latest = parsed[-1] if parsed else None
    return MetaShadowChartOverlay(
        {
            **base,
            "run_id": selected_run_id,
            "stream_id": stream_id,
            "available": has_events,
            "status": status_value,
            "reason": reason,
            "scores": scores,
            "outcome_markers": outcome_markers,
            "audit": audit,
            "counts": counts,
            "rows_truncated": truncated,
            "latest_sequence_no": (None if latest is None else latest["sequence_no"]),
            "latest_occurred_at": (None if latest is None else latest["occurred_at"]),
        }
    )


def aggregate_causal_live_minutes(
    live_minutes: pl.DataFrame,
    *,
    asset: str,
    timeframe: str,
    as_of: str | datetime,
    canonical_minutes: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Aggregate a live minute tail into safely closed target candles."""

    normalized_asset = normalize_asset(asset)
    normalized_timeframe = _canonical_timeframe(timeframe)
    interval_seconds = timeframe_seconds(normalized_timeframe)
    clock = _parse_utc(as_of)
    if clock is None:  # pragma: no cover - the public type excludes None
        raise ValueError("as_of is required")
    live = _normalized_ohlcv(live_minutes, live=True)
    if "overlay_observed_at" in live.columns:
        live = live.filter(pl.col("overlay_observed_at") <= pl.lit(clock))
    live = live.filter(pl.col("timestamp") + pl.duration(minutes=1) <= pl.lit(clock))
    if live.is_empty():
        return _empty_target_frame()

    if interval_seconds == 60:
        enriched = live.with_columns(
            pl.lit(1).cast(pl.Int64).alias("source_minute_count"),
            pl.lit(1).cast(pl.Int64).alias("live_source_minute_count"),
            pl.col("overlay_observed_at").alias("live_observed_at"),
        )
        return enriched.select(_target_columns(enriched)).sort("timestamp")

    first_live = live["timestamp"].min()
    assert isinstance(first_live, datetime)
    first_bucket = _bucket_start(first_live, interval_seconds)
    first_live_is_session_open = bool(
        live.filter(pl.col("timestamp") == pl.lit(first_live))
        .select(pl.col("is_session_open_bar").fill_null(False).first())
        .item()
    )
    canonical = (
        _empty_minute_frame()
        if canonical_minutes is None or canonical_minutes.is_empty()
        else _normalized_ohlcv(canonical_minutes, live=False).filter(
            (pl.col("timestamp") >= pl.lit(first_bucket))
            & (pl.col("timestamp") < pl.lit(first_live))
        )
    )
    minute_source = _merge_minutes(canonical, live)
    bucket_microseconds = (
        (pl.col("timestamp").dt.epoch(time_unit="s") // interval_seconds)
        * interval_seconds
        * 1_000_000
    )
    minute_source = minute_source.with_columns(
        bucket_microseconds.cast(pl.Datetime("us", "UTC")).alias("_bucket")
    ).sort("timestamp")
    aggregations: list[pl.Expr] = [
        pl.col("open").first().alias("open"),
        pl.col("high").max().alias("high"),
        pl.col("low").min().alias("low"),
        pl.col("close").last().alias("close"),
        pl.col("volume").sum().alias("volume"),
        pl.col("_live_overlay").count().alias("source_minute_count"),
        pl.col("_live_overlay").sum().cast(pl.Int64).alias("live_source_minute_count"),
        pl.col("overlay_observed_at").drop_nulls().max().alias("live_observed_at"),
        pl.col("overlay_provider").drop_nulls().last().alias("overlay_provider"),
        pl.col("overlay_quality").drop_nulls().last().alias("overlay_quality"),
    ]
    if "is_session_open_bar" in minute_source.columns:
        aggregations.append(
            pl.col("is_session_open_bar")
            .fill_null(False)
            .any()
            .alias("is_session_open_bar")
        )
    grouped = (
        minute_source.group_by("_bucket", maintain_order=True)
        .agg(aggregations)
        .rename({"_bucket": "timestamp"})
        .filter(pl.col("live_source_minute_count") > 0)
        .filter(
            pl.col("timestamp") + pl.duration(seconds=interval_seconds) <= pl.lit(clock)
        )
    )
    if normalized_asset in BYBIT_ASSETS:
        expected_minutes = interval_seconds // 60
        grouped = grouped.filter(pl.col("source_minute_count") == expected_minutes)
    elif (
        first_live > first_bucket
        and canonical.is_empty()
        and not first_live_is_session_open
    ):
        # Session assets may be sparse inside a bucket, but a service that
        # starts mid-bucket cannot prove that its first bucket is complete.
        # Canonical boundary rows immediately before the first-seen tail can
        # establish that transitional bucket without inventing any new rows.
        # A causal flag on the *first* live row is independent evidence that
        # the missing prefix was a scheduled closure, so that sparse bucket is
        # also safe.  A later session-open flag cannot prove that prefix.
        grouped = grouped.filter(
            pl.col("timestamp") >= first_bucket + timedelta(seconds=interval_seconds)
        )
    return grouped.sort("timestamp")


def merge_canonical_and_live(
    canonical_frame: pl.DataFrame,
    live_frame: pl.DataFrame,
) -> pl.DataFrame:
    """Merge target rows by timestamp, with live rows winning collisions."""

    if live_frame.is_empty():
        return canonical_frame.clone()
    canonical = _normalized_ohlcv(canonical_frame, live=False).with_columns(
        pl.lit(0).alias("_overlay_priority")
    )
    live = _normalized_ohlcv(live_frame, live=True).with_columns(
        pl.lit(1).alias("_overlay_priority")
    )
    return (
        pl.concat([canonical, live], how="diagonal_relaxed")
        .sort(["timestamp", "_overlay_priority"])
        .unique(subset=["timestamp"], keep="last", maintain_order=True)
        .sort("timestamp")
        .drop("_overlay_priority", "_live_overlay")
    )


def _read_only_connection(database: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(
        f"file:{database}?mode=ro",
        uri=True,
        timeout=2.0,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    connection.execute("PRAGMA busy_timeout = 2000")
    return connection


def _selected_run_id(
    *, explicit: str | None, status: dict[str, Any] | None
) -> str | None:
    if explicit is not None:
        normalized = explicit.strip()
        if not normalized:
            raise ValueError("run_id cannot be empty")
        return normalized
    if status is None:
        return None
    value = status.get("run_id")
    return str(value).strip() if value not in (None, "") else None


def _status_payload(status_path: str | Path | None) -> dict[str, Any] | None:
    if status_path is None:
        return None
    try:
        return read_json_object(Path(status_path).expanduser().resolve())
    except (OSError, ValueError) as exc:
        raise LiveChartOverlayError(
            f"Could not read forward-paper status {status_path}: {exc}"
        ) from exc


def _runtime_metadata(
    *,
    database: Path,
    status: dict[str, Any] | None,
    asset: str,
    clock: datetime,
) -> dict[str, Any]:
    process = inspect_process(database.parent)
    feed: dict[str, Any] | None = None
    if status is not None and isinstance(status.get("feeds"), dict):
        candidate = status["feeds"].get(asset)
        if isinstance(candidate, dict):
            feed = candidate
    heartbeat_at = _parse_utc(None if status is None else status.get("heartbeat_at"))
    heartbeat_age = (
        None
        if heartbeat_at is None
        else max(0.0, (clock - heartbeat_at).total_seconds())
    )
    metadata = {
        "service_running": process.running,
        "service_process_reason": process.reason,
        "service_pid": process.pid,
        "service_status": None if status is None else status.get("status"),
        "service_started_at": None if status is None else status.get("started_at"),
        "service_heartbeat_at": _iso_utc(heartbeat_at),
        "service_heartbeat_age_seconds": heartbeat_age,
        "service_poll_interval_seconds": (
            None if status is None else status.get("poll_interval_seconds")
        ),
        "feed_status": None if feed is None else feed.get("status"),
        "feed_last_attempt_at": None if feed is None else feed.get("last_attempt_at"),
        "feed_last_success_at": None if feed is None else feed.get("last_success_at"),
        "feed_last_observed_at": (
            None if feed is None else feed.get("last_observed_at")
        ),
        "feed_measured_lag_seconds": (
            None if feed is None else feed.get("measured_lag_seconds")
        ),
    }
    if feed is not None:
        for field in ("provider", "quality", "expected_delay_seconds"):
            if feed.get(field) is not None:
                metadata[field] = feed[field]
    return metadata


def _freshness_metadata(metadata: dict[str, Any], *, clock: datetime) -> dict[str, Any]:
    source_timestamp = _parse_utc(metadata.get("latest_source_timestamp"))
    observed_at = _parse_utc(metadata.get("latest_observed_at"))
    source_age = (
        None
        if source_timestamp is None
        else max(
            0.0,
            (clock - (source_timestamp + timedelta(minutes=1))).total_seconds(),
        )
    )
    observation_age = (
        None if observed_at is None else max(0.0, (clock - observed_at).total_seconds())
    )
    expected_delay = metadata.get("expected_delay_seconds")
    poll_interval = metadata.get("service_poll_interval_seconds")
    try:
        stale_after = max(
            180.0,
            float(expected_delay or 0.0) + 2.0 * float(poll_interval or 60.0),
        )
    except (TypeError, ValueError):
        stale_after = 180.0
    if source_age is None:
        freshness = "no_data"
    elif source_age <= stale_after:
        freshness = "fresh"
    elif metadata.get("quality") == "delayed":
        freshness = "delayed_or_market_closed"
    else:
        freshness = "stale"
    delayed = metadata.get("quality") == "delayed"
    return {
        "source_bar_age_seconds": source_age,
        "observation_age_seconds": observation_age,
        "freshness_stale_after_seconds": stale_after,
        "freshness": freshness,
        "indicator_observation_semantics": (
            "retrospective_delayed_observation"
            if delayed
            else "first_seen_after_bar_close"
        ),
        # The forward-paper engine can replay actual observation times.  The
        # chart overlay itself is visual context and must not be reused as an
        # as-was backtest dataset, especially for delayed Yahoo observations.
        "as_was_backtest_safe": False,
    }


def _latest_run_id(connection: sqlite3.Connection) -> str | None:
    row = connection.execute(
        "SELECT run_id FROM runs ORDER BY created_at DESC, run_id DESC LIMIT 1"
    ).fetchone()
    return None if row is None else str(row["run_id"])


def _run_exists(connection: sqlite3.Connection, run_id: str) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM runs WHERE run_id = ? LIMIT 1", (run_id,)
        ).fetchone()
        is not None
    )


def _parse_source_event(
    row: sqlite3.Row,
    *,
    expected_asset: str,
) -> dict[str, Any]:
    try:
        payload = json.loads(str(row["payload_json"]))
        source_row = payload["row"]
        asset = str(payload["asset"]).strip().upper()
        timestamp = _parse_utc(source_row["timestamp"])
        observed_at = _parse_utc(str(row["observed_at"]))
        if timestamp is None or observed_at is None:
            raise ValueError("missing timestamp")
        if asset != expected_asset:
            raise ValueError(f"asset mismatch {asset!r}")
        values = {
            key: float(source_row[key]) for key in ("open", "high", "low", "close")
        }
        volume = float(source_row.get("volume", 0.0))
        if not all(math.isfinite(value) for value in (*values.values(), volume)):
            raise ValueError("non-finite OHLCV")
        if min(values.values()) <= 0.0 or volume < 0.0:
            raise ValueError("invalid OHLCV bounds")
        if values["high"] < max(values["open"], values["close"]):
            raise ValueError("high below candle body")
        if values["low"] > min(values["open"], values["close"]):
            raise ValueError("low above candle body")
        expected_delay = int(payload.get("expected_delay_seconds", 0))
        if expected_delay < 0:
            raise ValueError("negative expected delay")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise LiveChartOverlayError(
            f"Invalid source_bar_observed event at sequence {row['sequence_no']}: {exc}"
        ) from exc
    return {
        "timestamp": timestamp,
        **values,
        "volume": volume,
        "is_session_open_bar": bool(source_row.get("is_session_open_bar", False)),
        "overlay_observed_at": observed_at,
        "overlay_provider": str(payload.get("provider", "unknown")),
        "overlay_quality": str(payload.get("quality", "unknown")),
        "overlay_expected_delay_seconds": expected_delay,
        "overlay_sequence_no": int(row["sequence_no"]),
        "overlay_event_id": str(row["event_id"]),
        "overlay_event_hash": str(row["event_hash"]),
    }


def _parse_meta_shadow_event(
    row: sqlite3.Row,
    *,
    expected_asset: str,
    expected_timeframe: str,
) -> dict[str, Any]:
    sequence_no = int(row["sequence_no"])
    event_type = str(row["event_type"])
    try:
        payload = json.loads(str(row["payload_json"]))
        if not isinstance(payload, dict):
            raise ValueError("payload must be an object")
        if str(payload["asset"]).strip().upper() != expected_asset:
            raise ValueError("asset does not match selected stream")
        if normalize_timeframe(str(payload["timeframe"])) != expected_timeframe:
            raise ValueError("timeframe does not match selected stream")
        occurred_at = _parse_utc(str(row["occurred_at"]))
        observed_at = _parse_utc(str(row["observed_at"]))
        if occurred_at is None or observed_at is None:
            raise ValueError("occurred_at and observed_at are required")
        if observed_at < occurred_at:
            raise ValueError("observed_at cannot precede occurred_at")
        shadow_event_id = _bounded_text(
            payload.get("shadow_event_id"), name="shadow_event_id", maximum=256
        )
        policy_digest = _optional_bounded_text(
            payload.get("policy_digest"), name="policy_digest", maximum=256
        )
        model_digest = _optional_bounded_text(
            payload.get("artifact_checksum"),
            name="artifact_checksum",
            maximum=256,
        )
        side = _optional_meta_side(payload.get("side"))
        common = {
            "sequence_no": sequence_no,
            "event_id": _bounded_text(row["event_id"], name="event_id", maximum=256),
            "event_type": event_type,
            "occurred_at": _iso_utc(occurred_at),
            "occurred_at_epoch": int(occurred_at.timestamp()),
            "observed_at": _iso_utc(observed_at),
            "shadow_event_id": shadow_event_id,
            "side": side,
            "policy_digest": policy_digest,
            "model_digest": model_digest,
        }
        if event_type == "meta_shadow_prediction":
            decision_at = _parse_utc(payload.get("decision_at"))
            if decision_at is None or decision_at != occurred_at:
                raise ValueError(
                    "prediction occurred_at must equal immutable decision_at"
                )
            if side is None:
                raise ValueError("prediction side is required")
            available = payload.get("available")
            accepted = payload.get("counterfactual_accepted")
            if not isinstance(available, bool):
                raise ValueError("available must be boolean")
            if not isinstance(accepted, bool):
                raise ValueError("counterfactual_accepted must be boolean")
            probability = _optional_probability(payload.get("probability"))
            if available and probability is None:
                raise ValueError("available prediction must include probability")
            return {
                **common,
                "available": available,
                "probability": probability,
                "accepted": accepted,
                "availability_reason": _optional_bounded_text(
                    _public_meta_reason(
                        payload.get("score_reason"),
                        name="score_reason",
                        allowed=_PUBLIC_SCORE_REASONS,
                    ),
                    name="public_score_reason",
                    maximum=64,
                ),
                "acceptance_reason": _optional_bounded_text(
                    _public_meta_reason(
                        payload.get("counterfactual_reason"),
                        name="counterfactual_reason",
                        allowed=_PUBLIC_COUNTERFACTUAL_REASONS,
                    ),
                    name="public_counterfactual_reason",
                    maximum=64,
                ),
                "outcome": None,
                "economic_binary_target": None,
            }
        if event_type != "meta_shadow_label":
            raise ValueError(f"unexpected event_type {event_type!r}")
        label_known_at = _parse_utc(payload.get("label_known_at"))
        if label_known_at is None or label_known_at != occurred_at:
            raise ValueError("label occurred_at must equal immutable label_known_at")
        outcome = _bounded_text(payload.get("outcome"), name="outcome", maximum=32)
        economic_target = payload.get("economic_binary_target")
        if isinstance(economic_target, bool) or economic_target not in (0, 1, None):
            raise ValueError("economic_binary_target must be 0, 1, or null")
        if side is None:
            side = _meta_side_from_shadow_record(payload.get("shadow_record"))
        return {
            **common,
            "side": side,
            "available": None,
            "probability": None,
            "accepted": None,
            "availability_reason": None,
            "acceptance_reason": None,
            "outcome": outcome.upper(),
            "economic_binary_target": economic_target,
            "label_reason": _optional_bounded_text(
                _public_meta_reason(
                    payload.get("reason"),
                    name="reason",
                    allowed=_PUBLIC_LABEL_REASONS,
                ),
                name="public_label_reason",
                maximum=64,
            ),
        }
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise LiveChartOverlayError(
            f"Invalid {event_type} event at sequence {sequence_no}: {exc}"
        ) from exc


def _redacted_meta_shadow_audit(item: dict[str, Any]) -> dict[str, Any]:
    """Return an explicit allowlist; never forward raw feature/model payloads."""

    fields = (
        "sequence_no",
        "event_id",
        "event_type",
        "occurred_at",
        "shadow_event_id",
        "side",
        "available",
        "accepted",
        "availability_reason",
        "acceptance_reason",
        "probability",
        "outcome",
        "economic_binary_target",
        "label_reason",
        "model_digest",
        "policy_digest",
    )
    return {field: item.get(field) for field in fields}


def _meta_shadow_outcome_marker(
    item: dict[str, Any], *, side: str | None
) -> dict[str, Any]:
    outcome = str(item.get("outcome") or "UNKNOWN").upper()
    presentation = {
        "TARGET": ("#20c997", "META TP known"),
        "STOP": ("#ff5b6e", "META SL known"),
        "TIMEOUT": ("#f8c15c", "META timeout known"),
        "AMBIGUOUS": ("#d46b91", "META ambiguous known"),
    }
    color, text = presentation.get(outcome, ("#8e9baa", "META outcome known"))
    return {
        "time": item["occurred_at_epoch"],
        "known_at": item["occurred_at"],
        "label_known_at": item["occurred_at"],
        "time_semantics": "known_at",
        "position": "aboveBar",
        "color": color,
        "shape": "circle",
        "text": text,
        "outcome": outcome,
        "shadow_event_id": item.get("shadow_event_id"),
        "side": side,
        "model_digest": item.get("model_digest"),
        "policy_digest": item.get("policy_digest"),
    }


def _optional_probability(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("probability must be numeric")
    probability = float(value)
    if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
        raise ValueError("probability must be finite and within [0, 1]")
    return probability


def _bounded_text(value: Any, *, name: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    normalized = value.strip()
    if len(normalized) > maximum:
        raise ValueError(f"{name} exceeds {maximum} characters")
    return normalized


def _optional_bounded_text(value: Any, *, name: str, maximum: int) -> str | None:
    if value is None:
        return None
    return _bounded_text(value, name=name, maximum=maximum)


def _public_meta_reason(
    value: Any,
    *,
    name: str,
    allowed: frozenset[str] | set[str],
) -> str | None:
    """Expose stable reason codes only; never forward free-form exception text."""

    if value is None:
        return None
    reason = _bounded_text(value, name=name, maximum=512)
    return reason if reason in allowed else _REDACTED_META_REASON


def _optional_meta_side(value: Any) -> str | None:
    if value is None:
        return None
    side = _bounded_text(value, name="side", maximum=16).upper()
    aliases = {"LONG": "LONG", "SHORT": "SHORT", "BUY": "LONG", "SELL": "SHORT"}
    if side not in aliases:
        raise ValueError(f"unsupported side {side!r}")
    return aliases[side]


def _meta_side_from_shadow_record(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    candidate = value.get("candidate")
    if not isinstance(candidate, dict):
        return None
    return _optional_meta_side(candidate.get("side"))


def _minute_frame(rows: list[dict[str, Any]]) -> pl.DataFrame:
    if not rows:
        return _empty_minute_frame()
    return pl.DataFrame(
        rows,
        schema_overrides={
            "timestamp": pl.Datetime("us", "UTC"),
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume": pl.Float64,
            "is_session_open_bar": pl.Boolean,
            "overlay_observed_at": pl.Datetime("us", "UTC"),
            "overlay_expected_delay_seconds": pl.Int64,
            "overlay_sequence_no": pl.Int64,
        },
    ).sort("timestamp")


def _empty_minute_frame() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "timestamp": pl.Datetime("us", "UTC"),
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume": pl.Float64,
            "is_session_open_bar": pl.Boolean,
            "overlay_observed_at": pl.Datetime("us", "UTC"),
            "overlay_provider": pl.String,
            "overlay_quality": pl.String,
            "overlay_expected_delay_seconds": pl.Int64,
            "overlay_sequence_no": pl.Int64,
            "overlay_event_id": pl.String,
            "overlay_event_hash": pl.String,
        }
    )


def _empty_target_frame() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "timestamp": pl.Datetime("us", "UTC"),
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume": pl.Float64,
            "source_minute_count": pl.Int64,
            "live_source_minute_count": pl.Int64,
            "live_observed_at": pl.Datetime("us", "UTC"),
        }
    )


def _normalized_ohlcv(frame: pl.DataFrame, *, live: bool) -> pl.DataFrame:
    missing = set(_OHLCV_COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError("OHLCV frame is missing: " + ", ".join(sorted(missing)))
    normalized = frame.with_columns(
        pl.col("timestamp").cast(pl.Datetime("us", "UTC")),
        *(pl.col(column).cast(pl.Float64) for column in _OHLCV_COLUMNS[1:]),
        pl.lit(1 if live else 0).cast(pl.Int8).alias("_live_overlay"),
    )
    if "is_session_open_bar" not in normalized.columns:
        normalized = normalized.with_columns(pl.lit(False).alias("is_session_open_bar"))
    if "overlay_observed_at" not in normalized.columns:
        normalized = normalized.with_columns(
            pl.lit(None).cast(pl.Datetime("us", "UTC")).alias("overlay_observed_at")
        )
    for column in ("overlay_provider", "overlay_quality"):
        if column not in normalized.columns:
            normalized = normalized.with_columns(
                pl.lit(None).cast(pl.String).alias(column)
            )
    return (
        normalized.filter(pl.col("timestamp").is_not_null())
        .sort(["timestamp", "_live_overlay"])
        .unique(subset=["timestamp"], keep="last", maintain_order=True)
        .sort("timestamp")
    )


def _merge_minutes(canonical: pl.DataFrame, live: pl.DataFrame) -> pl.DataFrame:
    if canonical.is_empty():
        return live
    return (
        pl.concat([canonical, live], how="diagonal_relaxed")
        .sort(["timestamp", "_live_overlay"])
        .unique(subset=["timestamp"], keep="last", maintain_order=True)
        .sort("timestamp")
    )


def _target_columns(frame: pl.DataFrame) -> list[str]:
    columns = [*_OHLCV_COLUMNS, "source_minute_count", "live_source_minute_count"]
    for optional in (
        "is_session_open_bar",
        "live_observed_at",
        "overlay_provider",
        "overlay_quality",
    ):
        if optional in frame.columns:
            columns.append(optional)
    return columns


def _canonical_timeframe(timeframe: str) -> str:
    normalized = normalize_timeframe(timeframe)
    if normalized not in CANONICAL_TIMEFRAMES:
        allowed = ", ".join(CANONICAL_TIMEFRAMES)
        raise ValueError(
            f"Live chart overlay requires a canonical timeframe: {allowed}"
        )
    return normalized


def _bucket_start(timestamp: datetime, interval_seconds: int) -> datetime:
    value = _parse_utc(timestamp)
    assert value is not None
    epoch = int(value.timestamp())
    return datetime.fromtimestamp(
        (epoch // interval_seconds) * interval_seconds,
        tz=timezone.utc,
    )


def _parse_utc(value: str | datetime | None) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    parsed = _parse_utc(value)
    assert parsed is not None
    return parsed.isoformat().replace("+00:00", "Z")


def _sqlite_timestamp(value: datetime) -> str:
    parsed = _parse_utc(value)
    assert parsed is not None
    return parsed.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _generation_token(
    *,
    run_id: Any,
    asset: str,
    timeframe: str,
    source_sequence_no: Any,
    source_event_hash: Any,
    closed_boundary: datetime,
) -> str:
    payload = {
        "asset": asset,
        "closed_bucket_boundary": _iso_utc(closed_boundary),
        "run_id": run_id,
        "source_event_hash": source_event_hash,
        "source_sequence_no": source_sequence_no,
        "timeframe": timeframe,
        "version": OVERLAY_VERSION,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]


def _unavailable_metadata(database: Path, *, reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "status": "unavailable",
        "reason": reason,
        "database_path": str(database),
        "run_id": None,
        "source_vintage": "append_only_first_seen",
        "source_rows_loaded": 0,
        "source_rows_truncated": False,
        "latest_source_sequence_no": None,
        "latest_source_event_hash": None,
        "latest_observed_at": None,
        "latest_source_timestamp": None,
        "provider": None,
        "quality": None,
        "expected_delay_seconds": None,
    }


def _timestamp_values(frame: pl.DataFrame) -> list[datetime]:
    if frame.is_empty() or "timestamp" not in frame.columns:
        return []
    return frame["timestamp"].cast(pl.Datetime("us", "UTC")).to_list()


def _frame_iso_min(frame: pl.DataFrame) -> str | None:
    if frame.is_empty():
        return None
    value = frame["timestamp"].min()
    return _iso_utc(value if isinstance(value, datetime) else None)


def _frame_iso_max(frame: pl.DataFrame) -> str | None:
    if frame.is_empty():
        return None
    value = frame["timestamp"].max()
    return _iso_utc(value if isinstance(value, datetime) else None)


def _bounded_frame(frame: pl.DataFrame, *, max_bars: int | None) -> pl.DataFrame:
    if max_bars is None:
        return frame
    if isinstance(max_bars, bool) or not isinstance(max_bars, int) or max_bars <= 0:
        raise ValueError("max_bars must be a positive integer")
    return frame.tail(max_bars) if frame.height > max_bars else frame


__all__ = [
    "DATABASE_FILENAME",
    "DEFAULT_MAX_META_SHADOW_ROWS",
    "DEFAULT_MAX_SOURCE_ROWS",
    "LiveChartOverlay",
    "LiveChartOverlayError",
    "LiveJournalSnapshot",
    "MAX_META_SHADOW_ROWS",
    "META_SHADOW_OVERLAY_VERSION",
    "MetaShadowChartOverlay",
    "OVERLAY_VERSION",
    "aggregate_causal_live_minutes",
    "load_live_chart_overlay",
    "merge_canonical_and_live",
    "read_first_seen_minutes",
    "read_meta_shadow_chart_overlay",
]
