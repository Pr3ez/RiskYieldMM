"""Local HTTP server for the browser-based chart inspector."""

from __future__ import annotations

import argparse
import bisect
import json
import math
import os
import threading
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

import polars as pl
from chart_config import (
    CANONICAL_SOURCE,
    CANONICAL_TIMEFRAMES,
    DEFAULT_MAX_BARS,
    HARD_MAX_BARS,
    WEB_ROOT,
    build_chart_manifest,
    normalize_asset,
    normalize_timeframe,
    resolve_ohlcv_files,
    timeframe_seconds,
)
from chart_export import (
    INDICATOR_CROSS_TIMEFRAME_CONTEXT,
    INDICATOR_NONE,
    INDICATOR_WARMUP_BARS,
    build_lightweight_charts_payload,
    load_ohlcv_window,
    load_ohlcv_window_with_context,
    normalize_indicators,
    required_indicator_warmup_bars,
)
from forward_paper.chart_overlay import (
    META_SHADOW_OVERLAY_VERSION,
    load_live_chart_overlay,
    read_meta_shadow_chart_overlay,
)
from forward_paper.runtime import default_state_dir, read_json_object
from forward_paper.supervisor import inspect_process, status_path
from indicator_optimizer import optimize_indicator_strategy
from indicators import DEFAULT_CUSUM_SENSITIVITY
from minute_replay import (
    DEFAULT_REPLAY_DAYS,
    MAX_REPLAY_DAYS,
    IndicatorStrategyConfig,
    ProtectedReplayConfig,
    ReplayCostConfig,
    load_canonical_minute_window,
    meta_label_policy_digest,
    run_minute_replay,
)
from multi_timeframe_context import (
    build_causal_mtf_context,
    context_timeframes,
    unavailable_mtf_context,
)
from trade_ml.artifact import artifact_deployment_rejection, load_artifact_safe
from trade_ml.features import META_FEATURE_NAMES

MAX_REPLAY_COST_BPS = 1_000.0
MAX_REPLAY_EVENT_LIMIT = 5_000
DEFAULT_REPLAY_EVENT_LIMIT = 2_000
MAX_PROTECTED_RISK_UNIT_MULTIPLIER = 20.0
MAX_PROTECTED_STOP_RISK_UNITS = 20.0
MAX_PROTECTED_TARGET_RISK_UNITS = 50.0
MAX_PROTECTED_TIMEOUT_TARGET_BARS = 1_000
MAX_PROTECTED_BREAK_EVEN_SAFETY_MARGIN = 0.50
META_FILTER_MODES = ("off", "shadow", "gate")
META_ARTIFACT_ENV = "RISKYIELDMM_META_ARTIFACT"
# Research payloads can still be several megabytes even after chart/audit
# bounding.  Keep only a very small LRU in-process; durable evidence belongs in
# the optimizer registry and forward-paper journal, not server RAM.
RESPONSE_CACHE_SIZE = 3
MTF_CONTEXT_VISIBLE_BARS = 512


@dataclass(frozen=True)
class ReplayApiRequest:
    """Validated query shared by the backtest and optimizer endpoints."""

    asset: str
    timeframe: str
    source: str
    start: datetime | None
    end: datetime | None
    replay_days: int
    event_limit: int
    strategy: IndicatorStrategyConfig
    costs: ReplayCostConfig
    protection: ProtectedReplayConfig
    meta_filter_mode: str

    def cache_parameters(self) -> tuple[Any, ...]:
        return (
            self.asset,
            self.timeframe,
            self.source,
            _iso_or_none(self.start),
            _iso_or_none(self.end),
            self.replay_days,
            self.event_limit,
            self.strategy.digest(),
            self.costs.digest(),
            self.protection.digest(),
            self.meta_filter_mode,
        )


_RESPONSE_CACHE: OrderedDict[tuple[Any, ...], dict[str, Any]] = OrderedDict()
_RESPONSE_CACHE_LOCK = threading.RLock()


def _single(
    query: dict[str, list[str]], name: str, default: str | None = None
) -> str | None:
    values = query.get(name)
    if not values:
        return default
    value = values[-1].strip()
    return value if value else default


def _parse_max_bars(value: str | None) -> int:
    if value is None:
        return DEFAULT_MAX_BARS
    max_bars = int(value)
    if max_bars <= 0:
        raise ValueError("max_bars must be positive")
    if max_bars > HARD_MAX_BARS:
        raise ValueError(f"max_bars cannot exceed {HARD_MAX_BARS}")
    return max_bars


def _parse_replay_request(raw_query: str) -> ReplayApiRequest:
    query = parse_qs(raw_query)
    asset = normalize_asset(_single(query, "asset", "BTCUSDT") or "BTCUSDT")
    timeframe = normalize_timeframe(_single(query, "timeframe", "1h") or "1h")
    if timeframe not in CANONICAL_TIMEFRAMES:
        allowed = ", ".join(CANONICAL_TIMEFRAMES)
        raise ValueError(
            f"Unsupported canonical timeframe {timeframe!r}. Allowed: {allowed}"
        )

    source = (_single(query, "source", CANONICAL_SOURCE) or CANONICAL_SOURCE).lower()
    if source != CANONICAL_SOURCE:
        raise ValueError("Minute replay endpoints require source=canonical")

    start = _parse_optional_datetime("start", _single(query, "start"))
    end = _parse_optional_datetime("end", _single(query, "end"))
    if start is not None and end is not None and start >= end:
        raise ValueError("start must be before end")

    replay_days = _parse_bounded_int(
        "replay_days",
        _single(query, "replay_days", str(DEFAULT_REPLAY_DAYS)),
        minimum=1,
        maximum=MAX_REPLAY_DAYS,
    )
    default_costs = ReplayCostConfig()
    fee_bps = _parse_bounded_float(
        "fee_bps",
        _single(query, "fee_bps", str(default_costs.fee_bps)),
        minimum=0.0,
        maximum=MAX_REPLAY_COST_BPS,
    )
    slippage_bps = _parse_bounded_float(
        "slippage_bps",
        _single(query, "slippage_bps", str(default_costs.slippage_bps)),
        minimum=0.0,
        maximum=MAX_REPLAY_COST_BPS,
    )
    spread_bps = _parse_bounded_float(
        "spread_bps",
        _single(query, "spread_bps", str(default_costs.spread_bps)),
        minimum=0.0,
        maximum=MAX_REPLAY_COST_BPS,
    )
    execution_latency_minutes = _parse_bounded_int(
        "execution_latency_minutes",
        _single(
            query,
            "execution_latency_minutes",
            str(default_costs.execution_latency_minutes),
        ),
        minimum=0,
        maximum=60,
    )
    event_limit = _parse_bounded_int(
        "event_limit",
        _single(query, "event_limit", str(DEFAULT_REPLAY_EVENT_LIMIT)),
        minimum=0,
        maximum=MAX_REPLAY_EVENT_LIMIT,
    )
    cusum_sensitivity = _single(
        query,
        "cusum_sensitivity",
        DEFAULT_CUSUM_SENSITIVITY,
    )
    strategy = IndicatorStrategyConfig(
        cusum_sensitivity=cusum_sensitivity or DEFAULT_CUSUM_SENSITIVITY,
    )
    protected_bracket = _parse_bool_flag(
        "protected_bracket",
        _single(query, "protected_bracket", "0"),
    )
    if protected_bracket:
        protection = ProtectedReplayConfig(
            enabled=True,
            risk_unit_volatility_multiplier=_parse_bounded_float(
                "risk_unit_volatility_multiplier",
                _single(query, "risk_unit_volatility_multiplier", "2"),
                minimum=0.1,
                maximum=MAX_PROTECTED_RISK_UNIT_MULTIPLIER,
            ),
            stop_risk_units=_parse_bounded_float(
                "stop_risk_units",
                _single(query, "stop_risk_units", "1"),
                minimum=0.1,
                maximum=MAX_PROTECTED_STOP_RISK_UNITS,
            ),
            target_risk_units=_parse_bounded_float(
                "target_risk_units",
                _single(query, "target_risk_units", "2"),
                minimum=0.1,
                maximum=MAX_PROTECTED_TARGET_RISK_UNITS,
            ),
            timeout_target_bars=_parse_bounded_int(
                "timeout_target_bars",
                _single(query, "timeout_target_bars", "20"),
                minimum=1,
                maximum=MAX_PROTECTED_TIMEOUT_TARGET_BARS,
            ),
            break_even_safety_margin=_parse_bounded_float(
                "break_even_safety_margin",
                _single(query, "break_even_safety_margin", "0.05"),
                minimum=0.0,
                maximum=MAX_PROTECTED_BREAK_EVEN_SAFETY_MARGIN,
            ),
        )
    else:
        # Disabled E0 requests intentionally ignore bracket-only query values.
        # This preserves the historical contract even if a browser retains
        # stale inputs from a prior protected experiment.
        protection = ProtectedReplayConfig(enabled=False)
    meta_filter_mode = (_single(query, "meta_filter_mode", "off") or "off").lower()
    if meta_filter_mode not in META_FILTER_MODES:
        allowed = ", ".join(META_FILTER_MODES)
        raise ValueError(f"meta_filter_mode must be one of: {allowed}")
    costs = ReplayCostConfig(
        fee_bps=fee_bps,
        spread_bps=spread_bps,
        slippage_bps=slippage_bps,
        execution_latency_minutes=execution_latency_minutes,
    )
    return ReplayApiRequest(
        asset=asset,
        timeframe=timeframe,
        source=source,
        start=start,
        end=end,
        replay_days=replay_days,
        event_limit=event_limit,
        strategy=strategy,
        costs=costs,
        protection=protection,
        meta_filter_mode=meta_filter_mode,
    )


def _parse_bool_flag(name: str, value: str | None) -> bool:
    normalized = str(value or "0").strip().lower()
    if normalized in {"1", "true"}:
        return True
    if normalized in {"0", "false"}:
        return False
    raise ValueError(f"{name} must be 0 or 1")


def _parse_optional_datetime(name: str, value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_bounded_int(
    name: str,
    value: str | None,
    *,
    minimum: int,
    maximum: int,
) -> int:
    try:
        parsed = int(value) if value is not None else minimum
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not minimum <= parsed <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return parsed


def _parse_bounded_float(
    name: str,
    value: str | None,
    *,
    minimum: float,
    maximum: float,
) -> float:
    try:
        parsed = float(value) if value is not None else minimum
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number") from exc
    if not math.isfinite(parsed) or not minimum <= parsed <= maximum:
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}")
    return parsed


def _iso_or_none(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _response_cache_get(key: tuple[Any, ...]) -> dict[str, Any] | None:
    with _RESPONSE_CACHE_LOCK:
        payload = _RESPONSE_CACHE.get(key)
        if payload is not None:
            _RESPONSE_CACHE.move_to_end(key)
        return payload


def _response_cache_put(key: tuple[Any, ...], payload: dict[str, Any]) -> None:
    with _RESPONSE_CACHE_LOCK:
        _RESPONSE_CACHE[key] = payload
        _RESPONSE_CACHE.move_to_end(key)
        while len(_RESPONSE_CACHE) > RESPONSE_CACHE_SIZE:
            _RESPONSE_CACHE.popitem(last=False)


def _clear_response_cache() -> None:
    """Clear cached research responses; intended for tests and server maintenance."""

    with _RESPONSE_CACHE_LOCK:
        _RESPONSE_CACHE.clear()


def _artifact_is_gate_eligible(
    artifact: Any,
    *,
    asset: str,
    timeframe: str,
) -> bool:
    """Compatibility wrapper around the shared execution-path validator."""

    return (
        artifact_deployment_rejection(
            artifact,
            asset=normalize_asset(asset),
            timeframe=normalize_timeframe(timeframe),
        )
        is None
    )


def _build_research_response(raw_query: str, *, optimize: bool) -> dict[str, Any]:
    request = _parse_replay_request(raw_query)
    if optimize and (request.protection.enabled or request.meta_filter_mode != "off"):
        raise ValueError(
            "Walk-forward optimization currently supports E0 only; set "
            "protected_bracket=0 and meta_filter_mode=off"
        )
    meta_artifact = None
    if request.meta_filter_mode != "off":
        artifact_path = os.environ.get(META_ARTIFACT_ENV, "").strip()
        if not artifact_path:
            raise ValueError(
                f"meta_filter_mode={request.meta_filter_mode} requires a compatible "
                "server-side model artifact; none is configured"
            )
        if not request.protection.enabled:
            raise ValueError("Meta-label scoring requires protected_bracket=1")
        policy_digest = meta_label_policy_digest(
            strategy=request.strategy,
            costs=request.costs,
            protection=request.protection,
            timeframe=request.timeframe,
        )
        loaded = load_artifact_safe(
            artifact_path,
            expected_feature_names=META_FEATURE_NAMES,
            expected_policy_digest=policy_digest,
            asset=request.asset,
            timeframe=request.timeframe,
        )
        if not loaded.available or loaded.artifact is None:
            detail = f" ({loaded.detail})" if loaded.detail else ""
            raise ValueError(
                "Configured promoted meta-label artifact is unavailable: "
                f"{loaded.reason}{detail}"
            )
        meta_artifact = loaded.artifact
        deployment_rejection = (
            artifact_deployment_rejection(
                meta_artifact,
                asset=request.asset,
                timeframe=request.timeframe,
            )
            if request.meta_filter_mode == "gate"
            else None
        )
        if deployment_rejection is not None:
            raise ValueError(
                "meta_filter_mode=gate requires an explicitly promoted artifact "
                "whose locked walk-forward deployment gate passed for this exact "
                "asset/timeframe selection; use shadow mode for candidate models: "
                f"{deployment_rejection}"
            )
    frame, source_metadata = load_canonical_minute_window(
        asset=request.asset,
        timeframe=request.timeframe,
        start=request.start,
        end=request.end,
        replay_days=request.replay_days,
    )
    source_generation = source_metadata.get("source_generation")
    if not isinstance(source_generation, str) or not source_generation:
        raise ValueError("Canonical minute source metadata has no source_generation")

    endpoint = "optimize" if optimize else "backtest"
    cache_key = (
        endpoint,
        *request.cache_parameters(),
        source_generation,
        None if meta_artifact is None else meta_artifact.checksum,
    )
    cached = _response_cache_get(cache_key)
    if cached is not None:
        return cached

    evaluation_start = source_metadata.get("evaluation_start")
    replay_clock_raw = source_metadata.get("evaluation_end")
    if not isinstance(evaluation_start, str) or not evaluation_start:
        raise ValueError("Canonical minute source metadata has no evaluation_start")
    if not isinstance(replay_clock_raw, str) or not replay_clock_raw:
        raise ValueError("Canonical minute source metadata has no evaluation_end")

    if optimize:
        replay_clock = _parse_optional_datetime("evaluation_end", replay_clock_raw)
        optimization = optimize_indicator_strategy(
            frame,
            request.asset,
            request.timeframe,
            request.costs,
            research_start=evaluation_start,
            replay_clock=replay_clock,
        )
        if not isinstance(optimization, dict):
            raise TypeError("optimize engine returned a non-object payload")
        response = _optimization_response(
            optimization,
            request=request,
            source_metadata=source_metadata,
        )
    else:
        payload = run_minute_replay(
            frame,
            asset=request.asset,
            timeframe=request.timeframe,
            strategy=request.strategy,
            costs=request.costs,
            protection=request.protection,
            meta_filter_mode=request.meta_filter_mode,
            meta_artifact=meta_artifact,
            evaluation_start=evaluation_start,
            replay_clock=replay_clock_raw,
            event_limit=request.event_limit,
        )
        if not isinstance(payload, dict):
            raise TypeError("backtest engine returned a non-object payload")
        response = dict(payload)
        result_metadata = response.get("metadata")
        if result_metadata is not None and not isinstance(result_metadata, dict):
            raise TypeError("backtest metadata must be an object")
        response["metadata"] = {
            **source_metadata,
            **(result_metadata or {}),
        }
        response_config = response.get("config")
        if response_config is not None and not isinstance(response_config, dict):
            raise TypeError("backtest config must be an object")
        response["config"] = dict(response_config or {})
        response["config"].setdefault(
            "meta_filter",
            {
                "mode": "off",
                "status": "disabled",
                "scoring_applied": False,
            },
        )
        for field in ("risk_stop", "risk_target", "meta_scores"):
            response.setdefault(field, [])
    _response_cache_put(cache_key, response)
    return response


def _optimization_response(
    optimization: dict[str, Any],
    *,
    request: ReplayApiRequest,
    source_metadata: dict[str, Any],
) -> dict[str, Any]:
    """Adapt optimizer research output to the chart replay payload contract."""

    final_replay = optimization.get("final_replay")
    if final_replay is not None and not isinstance(final_replay, dict):
        raise TypeError("optimizer final_replay must be an object or null")
    response = dict(final_replay or {})
    replay_metadata = response.get("metadata")
    if replay_metadata is not None and not isinstance(replay_metadata, dict):
        raise TypeError("optimizer replay metadata must be an object")
    optimization_summary = {
        key: optimization.get(key)
        for key in (
            "optimizer_version",
            "status",
            "reason",
            "research_only",
            "profitability_guaranteed",
            "disclaimer",
            "optimization_hash",
            "best_config_hash",
            "split",
            "development",
            "holdout",
            "acceptance_gates",
            "final_replay_error",
        )
        if optimization.get(key) is not None
    }
    response["metadata"] = {
        **source_metadata,
        **(replay_metadata or {}),
        "optimization": optimization_summary,
    }
    response.setdefault("metrics", {})
    response.setdefault(
        "config",
        {
            "strategy": optimization.get("best_config") or {},
            "costs": request.costs.as_dict(),
            "protected_bracket": request.protection.as_dict(
                timeframe=request.timeframe
            ),
            "meta_filter": {
                "mode": "off",
                "status": "disabled",
                "scoring_applied": False,
            },
        },
    )
    response_config = response.get("config")
    if not isinstance(response_config, dict):
        raise TypeError("optimizer replay config must be an object")
    response["config"] = {
        **response_config,
        "protected_bracket": response_config.get("protected_bracket")
        or request.protection.as_dict(timeframe=request.timeframe),
        "meta_filter": response_config.get("meta_filter")
        or {
            "mode": "off",
            "status": "disabled",
            "scoring_applied": False,
        },
    }
    for field in (
        "equity",
        "drawdown",
        "position",
        "risk_stop",
        "risk_target",
        "meta_scores",
        "markers",
        "fills",
        "signals",
    ):
        response.setdefault(field, [])
    for field in (
        "status",
        "reason",
        "best_config",
        "best_config_hash",
        "trials",
        "development",
        "holdout",
        "acceptance_gates",
    ):
        response[field] = optimization.get(field)
    return response


def _build_forward_paper_status(raw_query: str) -> dict[str, Any]:
    """Return a bounded selection view of the local forward-paper heartbeat."""

    query = parse_qs(raw_query)
    asset = normalize_asset(_single(query, "asset", "BTCUSDT") or "BTCUSDT")
    timeframe = normalize_timeframe(_single(query, "timeframe", "1h") or "1h")
    if timeframe not in CANONICAL_TIMEFRAMES:
        allowed = ", ".join(CANONICAL_TIMEFRAMES)
        raise ValueError(
            f"Unsupported canonical timeframe {timeframe!r}. Allowed: {allowed}"
        )

    state_dir = default_state_dir()
    process = inspect_process(state_dir)
    try:
        heartbeat = read_json_object(status_path(state_dir))
    except (OSError, ValueError) as exc:
        heartbeat = {
            "status": "invalid_status_file",
            "error": str(exc),
        }
    if heartbeat is None:
        heartbeat = {
            "status": "not_started",
            "message": (
                "Start the forward paper service with "
                "`python update_data.py --live-start`."
            ),
            "profitability_guaranteed": False,
            "real_order_routing": False,
        }

    feeds = heartbeat.get("feeds")
    streams = heartbeat.get("streams")
    feed = feeds.get(asset) if isinstance(feeds, dict) else None
    stream_key = f"{asset}|{timeframe}"
    stream = streams.get(stream_key) if isinstance(streams, dict) else None
    service = {
        key: value
        for key, value in heartbeat.items()
        if key not in {"feeds", "streams"}
    }
    return {
        "selection": {"asset": asset, "timeframe": timeframe},
        "process": {
            "running": process.running,
            "pid": process.pid,
            "reason": process.reason,
        },
        "service": service,
        "feed": feed,
        "stream": stream,
    }


def _canonical_minute_boundary_context(
    *,
    asset: str,
    timeframe: str,
) -> pl.DataFrame | None:
    """Load enough canonical minutes to complete one live HTF boundary bucket."""

    interval_minutes = timeframe_seconds(timeframe) // 60
    if interval_minutes <= 1:
        return None

    # This context needs at most one target bucket.  Calling the generic chart
    # window loader here used to count/deduplicate/sort the complete multi-year
    # 1m dataset before returning a few dozen rows, which retained more than a
    # gigabyte in the long-running server after one default chart request.
    resolution = resolve_ohlcv_files(
        asset=asset,
        timeframe="1m",
        source=CANONICAL_SOURCE,
    )
    lazy = pl.scan_parquet([str(path) for path in resolution.files])
    schema = set(lazy.collect_schema().names())
    columns = [
        pl.col("timestamp"),
        pl.col("open").cast(pl.Float64),
        pl.col("high").cast(pl.Float64),
        pl.col("low").cast(pl.Float64),
        pl.col("close").cast(pl.Float64),
        pl.col("volume").cast(pl.Float64),
    ]
    columns.extend(
        pl.col(name)
        for name in ("is_synthetic_no_trade", "is_session_open_bar")
        if name in schema
    )
    requested_rows = interval_minutes + 2
    candidate_rows = max(256, requested_rows * 4)
    frame = lazy.select(columns).tail(candidate_rows).collect()
    if "is_synthetic_no_trade" in frame.columns:
        frame = frame.filter(~pl.col("is_synthetic_no_trade").fill_null(False)).drop(
            "is_synthetic_no_trade"
        )
    return (
        frame.filter(pl.col("timestamp").is_not_null())
        .unique(subset=["timestamp"], keep="last")
        .sort("timestamp")
        .tail(requested_rows)
    )


def _merge_displaced_indicator_context(
    indicator_context: pl.DataFrame | None,
    displaced: pl.DataFrame,
    *,
    max_bars: int = INDICATOR_WARMUP_BARS,
) -> pl.DataFrame | None:
    """Keep a continuous warm-up immediately before a newly tailed live window."""

    if displaced.is_empty():
        return indicator_context
    frames = [frame for frame in (indicator_context, displaced) if frame is not None]
    if not frames:
        return None
    return (
        pl.concat(frames, how="diagonal_relaxed")
        .unique(subset=["timestamp"], keep="last")
        .sort("timestamp")
        .tail(max_bars)
    )


def _apply_live_chart_overlay(
    *,
    frame: pl.DataFrame,
    metadata: dict[str, Any],
    indicator_context: pl.DataFrame | None,
    start: str | None,
    max_bars: int,
) -> tuple[pl.DataFrame, dict[str, Any], pl.DataFrame | None]:
    """Attach the active first-seen journal tail without mutating canonical data."""

    try:
        canonical_minutes = _canonical_minute_boundary_context(
            asset=str(metadata["asset"]),
            timeframe=str(metadata["timeframe"]),
        )
        overlay = load_live_chart_overlay(
            frame,
            asset=str(metadata["asset"]),
            timeframe=str(metadata["timeframe"]),
            canonical_minutes=canonical_minutes,
            # Split the calculation context only after the journal has been
            # merged, otherwise displaced live rows create a hidden state gap.
            max_bars=None,
        )
    except Exception as exc:
        if metadata.get("live_start_fallback"):
            raise ValueError(
                "The requested start is newer than canonical data and the "
                f"first-seen live overlay is unavailable: {exc}"
            ) from exc
        return (
            frame,
            {
                **metadata,
                "live_overlay": {
                    "available": False,
                    "status": "overlay_error",
                    "reason": f"{exc.__class__.__name__}: {exc}",
                    "canonical_is_historical_base": True,
                    "canonical_mutated": False,
                },
            },
            indicator_context,
        )

    combined = overlay.frame
    context = indicator_context
    context_bars = int(
        metadata.get("indicator_warmup_requested") or INDICATOR_WARMUP_BARS
    )
    if start is not None:
        start_dt = _parse_optional_datetime("start", start)
        assert start_dt is not None
        before_start = combined.filter(pl.col("timestamp") < pl.lit(start_dt))
        combined = combined.filter(pl.col("timestamp") >= pl.lit(start_dt))
        context = _merge_displaced_indicator_context(
            context,
            before_start,
            max_bars=context_bars,
        )
        if combined.is_empty():
            raise ValueError(
                f"No canonical or first-seen live rows found at or after {start}"
            )
    overflow = max(0, combined.height - max_bars)
    displaced = combined.head(overflow) if overflow else combined.head(0)
    visible = combined.tail(max_bars) if overflow else combined
    context = _merge_displaced_indicator_context(
        context,
        displaced,
        max_bars=context_bars,
    )
    appended = int(overlay.metadata.get("live_rows_appended") or 0)
    if metadata.get("live_start_fallback"):
        rows_before_limit = combined.height
    else:
        rows_before_limit = (
            int(metadata.get("rows_before_window_limit") or frame.height) + appended
        )
    result_metadata = {
        **metadata,
        "start": _iso_or_none(visible["timestamp"].min()),
        "end": _iso_or_none(visible["timestamp"].max()),
        "row_count": visible.height,
        "rows_before_window_limit": rows_before_limit,
        "truncated_to_max_bars": rows_before_limit > max_bars,
        "live_overlay": overlay.metadata,
        "live_source_generation": overlay.metadata.get("generation"),
    }
    if context is not None:
        result_metadata["indicator_warmup_loaded"] = context.height
        result_metadata["indicator_warmup_complete"] = context.height >= context_bars
        if not context.is_empty():
            result_metadata["indicator_calculation_start"] = _iso_or_none(
                context["timestamp"].min()
            )
    return visible, result_metadata, context


def _calculation_rows(
    frame: pl.DataFrame,
    context: pl.DataFrame | None,
) -> pl.DataFrame:
    """Combine hidden warm-up and visible rows without exporting the former."""

    if context is None or context.is_empty():
        return frame.sort("timestamp")
    return (
        pl.concat([context, frame], how="diagonal_relaxed")
        .unique(subset=["timestamp"], keep="last")
        .sort("timestamp")
    )


def _build_mtf_overlay(
    *,
    frame: pl.DataFrame,
    metadata: dict[str, Any],
    indicator_context: pl.DataFrame | None,
    max_bars: int,
    end: str | None,
    calculation_now: datetime,
) -> dict[str, Any]:
    """Load mapped canonical contexts and align only already-available signals."""

    asset = str(metadata.get("asset") or "")
    active_timeframe = str(metadata.get("timeframe") or "")
    if metadata.get("source") != CANONICAL_SOURCE:
        return unavailable_mtf_context(
            chart_timeframe=active_timeframe,
            reason=(
                "Cross-timeframe context is canonical-only; raw/provider sources "
                "remain single-stream debugging views."
            ),
            status="unsupported_source",
        )

    calculation_frames = {
        active_timeframe: _calculation_rows(frame, indicator_context).tail(
            INDICATOR_WARMUP_BARS + MTF_CONTEXT_VISIBLE_BARS
        )
    }
    context_visible_frame = frame.tail(MTF_CONTEXT_VISIBLE_BARS)
    visible_start = _iso_or_none(context_visible_frame["timestamp"].min())
    for timeframe in context_timeframes(active_timeframe):
        try:
            context_kwargs = {
                "asset": asset,
                "timeframe": timeframe,
                "source": CANONICAL_SOURCE,
                "start": visible_start,
                "end": end,
                "max_bars": min(max_bars, MTF_CONTEXT_VISIBLE_BARS),
            }
            try:
                context_frame, context_metadata, hidden = (
                    load_ohlcv_window_with_context(**context_kwargs)
                )
            except ValueError as exc:
                can_retry_for_live_tail = bool(
                    end is None and "No rows found" in str(exc)
                )
                if not can_retry_for_live_tail:
                    raise
                context_frame, context_metadata, hidden = (
                    load_ohlcv_window_with_context(**{**context_kwargs, "start": None})
                )
                context_metadata = {
                    **context_metadata,
                    "requested_start": visible_start,
                    "live_start_fallback": True,
                }
            if end is None:
                context_frame, context_metadata, hidden = _apply_live_chart_overlay(
                    frame=context_frame,
                    metadata=context_metadata,
                    indicator_context=hidden,
                    start=visible_start,
                    max_bars=min(max_bars, MTF_CONTEXT_VISIBLE_BARS),
                )
            calculation_frames[timeframe] = _calculation_rows(context_frame, hidden)
        except Exception as exc:  # Context must never hide the primary candles.
            return unavailable_mtf_context(
                chart_timeframe=active_timeframe,
                reason=(
                    f"{timeframe} context unavailable: {exc.__class__.__name__}: {exc}"
                ),
                status="source_error",
            )

    return build_causal_mtf_context(
        asset=asset,
        chart_timeframe=active_timeframe,
        visible_frame=context_visible_frame,
        calculation_frames=calculation_frames,
        now=calculation_now,
    )


def _build_chart_response(raw_query: str) -> dict[str, Any]:
    """Build one chart response, including the causal live tail when eligible."""

    query = parse_qs(raw_query)
    asset = _single(query, "asset", "BTCUSDT")
    timeframe = _single(query, "timeframe", "1h")
    source = _single(query, "source", CANONICAL_SOURCE)
    start = _single(query, "start")
    end = _single(query, "end")
    legacy_indicator = _single(query, "indicator", INDICATOR_NONE)
    indicators = normalize_indicators(
        query.get("indicators", []),
        indicator=legacy_indicator,
    )
    cusum_sensitivity = _single(
        query,
        "cusum_sensitivity",
        DEFAULT_CUSUM_SENSITIVITY,
    )
    max_bars = _parse_max_bars(_single(query, "max_bars", str(DEFAULT_MAX_BARS)))
    indicator_warmup_bars = required_indicator_warmup_bars(
        indicators,
        timeframe=timeframe or "1h",
    )

    window_kwargs = {
        "asset": asset or "BTCUSDT",
        "timeframe": timeframe or "1h",
        "source": source or CANONICAL_SOURCE,
        "start": start,
        "end": end,
        "max_bars": max_bars,
    }

    def load_window(
        kwargs: dict[str, Any],
    ) -> tuple[pl.DataFrame, dict[str, Any], pl.DataFrame | None]:
        if indicators:
            loaded_frame, loaded_metadata, loaded_context = (
                load_ohlcv_window_with_context(
                    **kwargs,
                    indicator_warmup_bars=indicator_warmup_bars,
                )
            )
            return loaded_frame, loaded_metadata, loaded_context
        loaded_frame, loaded_metadata = load_ohlcv_window(**kwargs)
        return loaded_frame, loaded_metadata, None

    try:
        frame, metadata, indicator_context = load_window(window_kwargs)
    except ValueError as exc:
        can_retry_for_live_tail = bool(
            start is not None
            and end is None
            and str(source or CANONICAL_SOURCE).lower() == CANONICAL_SOURCE
            and "No rows found" in str(exc)
        )
        if not can_retry_for_live_tail:
            raise
        frame, metadata, indicator_context = load_window(
            {**window_kwargs, "start": None}
        )
        requested_start = _parse_optional_datetime("start", start)
        metadata = {
            **metadata,
            "requested_start": _iso_or_none(requested_start),
            "live_start_fallback": True,
        }

    if metadata.get("source") == CANONICAL_SOURCE and end is None:
        frame, metadata, indicator_context = _apply_live_chart_overlay(
            frame=frame,
            metadata=metadata,
            indicator_context=indicator_context,
            start=start,
            max_bars=max_bars,
        )

    calculation_now = datetime.now(timezone.utc)
    mtf_context_overlay = None
    if INDICATOR_CROSS_TIMEFRAME_CONTEXT in indicators:
        mtf_context_overlay = _build_mtf_overlay(
            frame=frame,
            metadata=metadata,
            indicator_context=indicator_context,
            max_bars=max_bars,
            end=end,
            calculation_now=calculation_now,
        )

    response = build_lightweight_charts_payload(
        frame=frame,
        metadata=metadata,
        indicators=indicators,
        cusum_sensitivity=cusum_sensitivity or DEFAULT_CUSUM_SENSITIVITY,
        indicator_context=indicator_context,
        mtf_context_overlay=mtf_context_overlay,
        use_live_signal_service=True,
        calculation_now=calculation_now,
    )
    response["forward_meta_shadow"] = _forward_meta_shadow_for_chart(
        frame=frame,
        metadata=metadata,
        as_of=calculation_now,
    )
    return response


def _forward_meta_shadow_for_chart(
    *,
    frame: pl.DataFrame,
    metadata: dict[str, Any],
    as_of: datetime,
) -> dict[str, Any]:
    """Attach redacted journal evidence without making candles depend on it."""

    asset = str(metadata.get("asset") or "")
    timeframe = str(metadata.get("timeframe") or "")
    if metadata.get("source") != CANONICAL_SOURCE:
        return {
            "version": META_SHADOW_OVERLAY_VERSION,
            "mode": "shadow",
            "asset": asset,
            "timeframe": timeframe,
            "available": False,
            "status": "unavailable",
            "reason": "canonical_source_required",
            "scores": [],
            "outcome_markers": [],
            "audit": [],
            "counts": {},
            "diagnostic_only": True,
            "affects_orders": False,
            "affects_positions": False,
            "real_order_routing": False,
        }
    if frame.is_empty():
        return {
            "version": META_SHADOW_OVERLAY_VERSION,
            "mode": "shadow",
            "asset": asset,
            "timeframe": timeframe,
            "available": False,
            "status": "unavailable",
            "reason": "chart_has_no_rows",
            "scores": [],
            "outcome_markers": [],
            "audit": [],
            "counts": {},
            "diagnostic_only": True,
            "affects_orders": False,
            "affects_positions": False,
            "real_order_routing": False,
        }
    visible_start = frame["timestamp"].min()
    visible_last = frame["timestamp"].max()
    assert isinstance(visible_start, datetime)
    assert isinstance(visible_last, datetime)
    visible_end = visible_last + timedelta(seconds=timeframe_seconds(timeframe))
    live_metadata = metadata.get("live_overlay")
    selected_run_id = (
        live_metadata.get("run_id") if isinstance(live_metadata, dict) else None
    )
    try:
        overlay = read_meta_shadow_chart_overlay(
            asset=asset,
            timeframe=timeframe,
            run_id=selected_run_id,
            as_of=as_of,
            start=visible_start,
            end=visible_end,
        ).payload
        return _align_forward_meta_outcomes_to_frame(overlay, frame=frame)
    except Exception as exc:
        return {
            "version": META_SHADOW_OVERLAY_VERSION,
            "mode": "shadow",
            "asset": asset,
            "timeframe": timeframe,
            "run_id": selected_run_id,
            "available": False,
            "status": "overlay_error",
            "reason": "forward_meta_shadow_journal_read_failed",
            "error_type": exc.__class__.__name__,
            "scores": [],
            "outcome_markers": [],
            "audit": [],
            "counts": {},
            "diagnostic_only": True,
            "affects_orders": False,
            "affects_positions": False,
            "real_order_routing": False,
        }


def _align_forward_meta_outcomes_to_frame(
    payload: dict[str, Any],
    *,
    frame: pl.DataFrame,
) -> dict[str, Any]:
    """Place label evidence on the first chart candle not earlier than maturity."""

    candle_times = [int(value.timestamp()) for value in frame["timestamp"].to_list()]
    aligned: list[dict[str, Any]] = []
    markers = payload.get("outcome_markers")
    if not isinstance(markers, list):
        return payload
    for raw_marker in markers:
        if not isinstance(raw_marker, dict):
            continue
        known_at = raw_marker.get("time")
        if isinstance(known_at, bool) or not isinstance(known_at, (int, float)):
            continue
        known_epoch = int(known_at)
        candle_index = bisect.bisect_left(candle_times, known_epoch)
        if candle_index >= len(candle_times):
            continue
        aligned.append(
            {
                **raw_marker,
                "time": candle_times[candle_index],
                "known_at_epoch": known_epoch,
                "time_semantics": "first_candle_at_or_after_known_at",
            }
        )
    return {**payload, "outcome_markers": aligned}


class ChartRequestHandler(SimpleHTTPRequestHandler):
    """Serve static viewer assets and bounded chart API responses."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(WEB_ROOT), **kwargs)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self._send_json({"ok": True})
            return
        if parsed.path == "/api/manifest":
            self._send_json(build_chart_manifest())
            return
        if parsed.path == "/api/chart":
            self._handle_chart(parsed.query)
            return
        if parsed.path == "/api/backtest":
            self._handle_research(parsed.query, optimize=False)
            return
        if parsed.path == "/api/optimize":
            self._handle_research(parsed.query, optimize=True)
            return
        if parsed.path == "/api/paper/status":
            self._handle_forward_paper_status(parsed.query)
            return
        super().do_GET()

    def _handle_chart(self, raw_query: str) -> None:
        try:
            payload = _build_chart_response(raw_query)
        except Exception as exc:
            self._send_json(
                {
                    "error": str(exc),
                    "type": exc.__class__.__name__,
                },
                status=HTTPStatus.BAD_REQUEST,
            )
            return

        self._send_json(payload)

    def _handle_research(self, raw_query: str, *, optimize: bool) -> None:
        try:
            payload = _build_research_response(raw_query, optimize=optimize)
        except Exception as exc:
            self._send_json(
                {
                    "error": str(exc),
                    "type": exc.__class__.__name__,
                },
                status=HTTPStatus.BAD_REQUEST,
            )
            return
        self._send_json(payload)

    def _handle_forward_paper_status(self, raw_query: str) -> None:
        try:
            payload = _build_forward_paper_status(raw_query)
        except Exception as exc:
            self._send_json(
                {
                    "error": str(exc),
                    "type": exc.__class__.__name__,
                },
                status=HTTPStatus.BAD_REQUEST,
            )
            return
        self._send_json(payload)

    def _send_json(
        self,
        payload: dict[str, Any],
        status: HTTPStatus = HTTPStatus.OK,
    ) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run_server(host: str = "127.0.0.1", port: int = 8765) -> None:
    server = ThreadingHTTPServer((host, port), ChartRequestHandler)
    print(f"RiskYieldMM chart inspector: http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping chart inspector.")
    finally:
        server.server_close()


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve the local chart inspector.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    return parser


def main() -> None:
    args = _build_arg_parser().parse_args()
    run_server(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
