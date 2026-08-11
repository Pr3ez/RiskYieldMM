"""Causal higher-timeframe context for the Analyst chart.

The module aligns only forward-filtered signals whose source bar has already
closed.  Alignment is backward-as-of on the signal's availability timestamp;
forming higher-timeframe bars are never projected into an earlier decision.
The resulting classifications describe context and are not trade orders.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any

import polars as pl
from chart_config import CANONICAL_TIMEFRAMES, timeframe_seconds
from live_signal_service import build_online_signal_config
from online_signals import compute_online_signal_frame

MTF_CONTEXT_VERSION = "causal_mtf_context_v1"
MTF_CONTEXT_MAPPING: dict[str, tuple[str, ...]] = {
    "1m": ("15m", "1h"),
    "15m": ("1h", "4h"),
    "1h": ("4h", "1d"),
    "4h": ("8h", "1d"),
    "8h": ("12h", "1d"),
    "12h": ("1d",),
    "1d": (),
}
_DIRECTION_THRESHOLD = 0.08
_CHANGE_RISK_THRESHOLD = 0.55


def context_timeframes(timeframe: str) -> tuple[str, ...]:
    """Return the frozen higher-timeframe mapping for one canonical chart."""

    normalized = str(timeframe).strip().lower()
    if normalized not in MTF_CONTEXT_MAPPING:
        allowed = ", ".join(CANONICAL_TIMEFRAMES)
        raise ValueError(
            f"Unsupported cross-timeframe selection {timeframe!r}. Allowed: {allowed}"
        )
    return MTF_CONTEXT_MAPPING[normalized]


def build_causal_mtf_context(
    *,
    asset: str,
    chart_timeframe: str,
    visible_frame: pl.DataFrame,
    calculation_frames: Mapping[str, pl.DataFrame],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build a causal context matrix and historical aligned score series.

    ``calculation_frames`` must contain the active timeframe and each mapped
    context timeframe.  Every source is independently replayed through the
    production scalar online engine.  A context value is selected only when
    its emitted ``timestamp`` (the bar-close/actionable time) is no later than
    the active decision timestamp.
    """

    active = str(chart_timeframe).strip().lower()
    contexts = context_timeframes(active)
    requested = (active, *contexts)
    missing = [
        timeframe for timeframe in requested if timeframe not in calculation_frames
    ]
    if missing:
        return unavailable_mtf_context(
            chart_timeframe=active,
            reason="Missing calculation frame(s): " + ", ".join(missing),
            status="source_unavailable",
        )
    if visible_frame.is_empty():
        return unavailable_mtf_context(
            chart_timeframe=active,
            reason="The visible chart window is empty.",
            status="empty_window",
        )

    calculation_now = _utc(now or datetime.now(timezone.utc))
    signal_rows: dict[str, list[dict[str, Any]]] = {}
    signal_times: dict[str, list[datetime]] = {}
    has_first_seen_tail = False
    for timeframe in requested:
        frame = calculation_frames[timeframe]
        first_seen_by_source = _first_seen_lookup(frame)
        has_first_seen_tail = has_first_seen_tail or bool(first_seen_by_source)
        config = build_online_signal_config(asset=asset, timeframe=timeframe)
        signals, _ = compute_online_signal_frame(
            frame,
            config=config,
            now=calculation_now,
        )
        valid = (
            signals.filter(
                pl.col("trend_score").is_not_null()
                & pl.col("regime_state").is_not_null()
            ).sort("timestamp")
            if not signals.is_empty()
            else pl.DataFrame()
        )
        rows = valid.to_dicts() if not valid.is_empty() else []
        for row in rows:
            scheduled = _utc(row["timestamp"])
            observed = first_seen_by_source.get(_utc(row["source_timestamp"]))
            row["context_first_seen_at"] = observed
            row["context_available_at"] = (
                scheduled if observed is None else max(scheduled, observed)
            )
        rows.sort(key=lambda row: _utc(row["context_available_at"]))
        signal_rows[timeframe] = rows
        signal_times[timeframe] = [_utc(row["context_available_at"]) for row in rows]

    start = _utc(visible_frame["timestamp"].min())
    end = _utc(visible_frame["timestamp"].max()) + timedelta(
        seconds=timeframe_seconds(active)
    )
    active_rows = [
        row for row in signal_rows[active] if start <= _utc(row["timestamp"]) <= end
    ]
    if not active_rows:
        return unavailable_mtf_context(
            chart_timeframe=active,
            reason="The active timeframe has not completed signal warm-up.",
            status="warmup_or_no_overlap",
        )

    source_series: dict[str, list[dict[str, Any]]] = {
        timeframe: [] for timeframe in requested
    }
    context_score: list[dict[str, Any]] = []
    agreement_series: list[dict[str, Any]] = []
    risk_series: list[dict[str, Any]] = []
    latest_aligned: dict[str, dict[str, Any] | None] = {}
    latest_summary: dict[str, Any] = {}

    for active_row in active_rows:
        decision_time = _utc(active_row["context_available_at"])
        aligned: dict[str, dict[str, Any] | None] = {active: active_row}
        for timeframe in contexts:
            aligned[timeframe] = _latest_available(
                signal_rows[timeframe],
                signal_times[timeframe],
                decision_time,
            )

        point_time = int(decision_time.timestamp())
        for timeframe in requested:
            source = aligned[timeframe]
            point: dict[str, Any] = {"time": point_time}
            if source is not None:
                point["value"] = float(source["trend_score"])
                point["source_time"] = int(_utc(source["source_timestamp"]).timestamp())
                point["available_time"] = int(
                    _utc(source["context_available_at"]).timestamp()
                )
            source_series[timeframe].append(point)

        summary = _classify_context(
            asset=asset,
            active_timeframe=active,
            context_timeframes=contexts,
            decision_time=decision_time,
            aligned=aligned,
        )
        context_score.append(
            {"time": point_time, "value": float(summary["direction_score"])}
        )
        agreement_series.append(
            {"time": point_time, "value": float(summary["agreement"])}
        )
        risk_series.append(
            {"time": point_time, "value": float(summary["maximum_change_risk"])}
        )
        latest_aligned = aligned
        latest_summary = summary

    sources = []
    for index, timeframe in enumerate(requested):
        role = "current" if index == 0 else ("primary" if index == 1 else "macro")
        latest = latest_aligned.get(timeframe)
        sources.append(
            {
                "timeframe": timeframe,
                "role": role,
                "latest": (
                    None
                    if latest is None
                    else _source_summary(
                        asset=asset,
                        timeframe=timeframe,
                        decision_time=_utc(active_rows[-1]["context_available_at"]),
                        row=latest,
                    )
                ),
                "trend_score": source_series[timeframe],
            }
        )

    status = "ok" if contexts else "no_higher_timeframe"
    reason = (
        None
        if contexts
        else "No higher canonical timeframe exists above 1d; no weekly bar is fabricated."
    )
    return {
        "id": "cross_timeframe_context",
        "label": "Cross-Timeframe Context",
        "version": MTF_CONTEXT_VERSION,
        "status": status,
        "reason": reason,
        "diagnostic_only": True,
        "calibrated": False,
        "usable_as_trading_gate": False,
        "alignment": "backward_asof_on_post_close_available_at",
        "availability": "closed_bars_only_usable_next_bar",
        "data_vintage": (
            "current_canonical_replay_plus_append_only_first_seen_tail"
            if has_first_seen_tail
            else "current_canonical_replay"
        ),
        "current_timeframe": active,
        "context_timeframes": list(contexts),
        "direction_threshold": _DIRECTION_THRESHOLD,
        "change_risk_threshold": _CHANGE_RISK_THRESHOLD,
        "scale": {"trend_score": [-1.0, 1.0], "quality_and_risk": [0.0, 1.0]},
        "limitations": (
            "A versioned context heuristic using fixed untrained prototype-regime "
            "weights. It describes alignment/conflict and is not a Buy/Sell signal."
        ),
        "sources": sources,
        "context_score": context_score,
        "agreement": agreement_series,
        "maximum_change_risk": risk_series,
        "latest": latest_summary,
    }


def unavailable_mtf_context(
    *,
    chart_timeframe: str,
    reason: str,
    status: str = "unavailable",
) -> dict[str, Any]:
    """Return a stable empty overlay contract without hiding the price chart."""

    active = str(chart_timeframe).strip().lower()
    contexts = list(MTF_CONTEXT_MAPPING.get(active, ()))
    return {
        "id": "cross_timeframe_context",
        "label": "Cross-Timeframe Context",
        "version": MTF_CONTEXT_VERSION,
        "status": status,
        "reason": reason,
        "diagnostic_only": True,
        "calibrated": False,
        "usable_as_trading_gate": False,
        "alignment": "backward_asof_on_post_close_available_at",
        "current_timeframe": active,
        "context_timeframes": contexts,
        "sources": [],
        "context_score": [],
        "agreement": [],
        "maximum_change_risk": [],
        "latest": {},
    }


def _latest_available(
    rows: list[dict[str, Any]],
    times: list[datetime],
    decision_time: datetime,
) -> dict[str, Any] | None:
    index = bisect_right(times, decision_time) - 1
    return rows[index] if index >= 0 else None


def _classify_context(
    *,
    asset: str,
    active_timeframe: str,
    context_timeframes: tuple[str, ...],
    decision_time: datetime,
    aligned: Mapping[str, dict[str, Any] | None],
) -> dict[str, Any]:
    ordered = (active_timeframe, *context_timeframes)
    missing = [timeframe for timeframe in ordered if aligned.get(timeframe) is None]
    source_summaries = [
        _source_summary(
            asset=asset,
            timeframe=timeframe,
            decision_time=decision_time,
            row=aligned[timeframe],  # type: ignore[arg-type]
        )
        for timeframe in ordered
        if aligned.get(timeframe) is not None
    ]
    stale = [
        item["timeframe"] for item in source_summaries if item["status"] == "stale"
    ]
    scores = [float(item["trend_score"]) for item in source_summaries]
    directions = [int(item["direction"]) for item in source_summaries]
    direction_score = sum(scores) / len(scores) if scores else 0.0
    nonzero = [direction for direction in directions if direction != 0]
    agreement = abs(sum(nonzero)) / len(nonzero) if nonzero else 0.0
    maximum_risk = max(
        (float(item["change_risk"]) for item in source_summaries),
        default=0.0,
    )
    active_direction = directions[0] if directions else 0
    higher_directions = directions[1:]

    if missing or stale:
        context_class = "insufficient_or_stale"
        reason = "Missing or stale closed-bar context: " + ", ".join(missing + stale)
    elif maximum_risk >= _CHANGE_RISK_THRESHOLD:
        context_class = "transition_risk"
        reason = "At least one timeframe has elevated prototype change-risk weight."
    elif (
        active_direction != 0
        and higher_directions
        and all(direction == active_direction for direction in higher_directions)
    ):
        context_class = "trend_aligned"
        reason = "Current and selected higher-timeframe trend signs agree."
    elif active_direction != 0 and any(
        direction == -active_direction for direction in higher_directions
    ):
        context_class = "countertrend_conflict"
        reason = "The active trend opposes at least one closed higher-timeframe trend."
    else:
        context_class = "range_context"
        reason = "Trend signs are neutral/mixed or higher-timeframe context is absent."

    if direction_score >= _DIRECTION_THRESHOLD:
        bias = "bullish"
    elif direction_score <= -_DIRECTION_THRESHOLD:
        bias = "bearish"
    else:
        bias = "mixed"
    return {
        "as_of": int(decision_time.timestamp()),
        "context_class": context_class,
        "direction_bias": bias,
        "direction_score": direction_score,
        "agreement": agreement,
        "conflict": context_class == "countertrend_conflict",
        "transition_risk": context_class == "transition_risk",
        "maximum_change_risk": maximum_risk,
        "reason": reason,
    }


def _source_summary(
    *,
    asset: str,
    timeframe: str,
    decision_time: datetime,
    row: Mapping[str, Any],
) -> dict[str, Any]:
    source_open = _utc(row["source_timestamp"])
    scheduled_close = _utc(row["timestamp"])
    available_at = _utc(row.get("context_available_at") or scheduled_close)
    first_seen = row.get("context_first_seen_at")
    age_seconds = max(0, int((decision_time - available_at).total_seconds()))
    config = build_online_signal_config(asset=asset, timeframe=timeframe)
    allowed_age = max(
        2 * config.expected_interval_seconds,
        config.max_gap_seconds or config.expected_interval_seconds,
    )
    score = float(row["trend_score"])
    if score >= _DIRECTION_THRESHOLD:
        direction = 1
    elif score <= -_DIRECTION_THRESHOLD:
        direction = -1
    else:
        direction = 0
    ratio = float(row["fast_slow_ratio"])
    if ratio >= 1.20:
        volatility_state = "expanding"
    elif ratio <= 0.85:
        volatility_state = "contracting"
    else:
        volatility_state = "stable"
    return {
        "timeframe": timeframe,
        "source_bar_open": _iso(source_open),
        "source_bar_close": _iso(scheduled_close),
        "available_at": _iso(available_at),
        "first_seen_at": None if first_seen is None else _iso(_utc(first_seen)),
        "age_seconds": age_seconds,
        "status": "stale" if age_seconds > allowed_age else "current",
        "finality": "closed",
        "data_vintage": (
            "append_only_first_seen_tail"
            if first_seen is not None
            else "current_canonical_replay"
        ),
        "direction": direction,
        "trend_state": str(row["trend_state"]),
        "trend_score": score,
        "path_quality": float(row["path_quality"]),
        "trend_agreement": float(row["trend_agreement"]),
        "fast_slow_vol_ratio": ratio,
        "volatility_state": volatility_state,
        "regime_label": str(row["regime_label"]),
        "prototype_top_weight": float(row["regime_confidence"]),
        "regime_value_kind": "forward_weight_under_fixed_untrained_prototypes",
        "filtered_switch_probability": float(row["regime_filtered_switch_probability"]),
        "change_risk": float(row["regime_change_risk"]),
    }


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _first_seen_lookup(frame: pl.DataFrame) -> dict[datetime, datetime]:
    if "live_observed_at" not in frame.columns or frame.is_empty():
        return {}
    rows = frame.select("timestamp", "live_observed_at").drop_nulls().to_dicts()
    return {_utc(row["timestamp"]): _utc(row["live_observed_at"]) for row in rows}


def _iso(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")
