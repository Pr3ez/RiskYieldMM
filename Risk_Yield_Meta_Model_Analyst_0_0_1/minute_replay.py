"""Causal current-canonical one-minute replay for Analyst research.

The replay deliberately separates three clocks:

* canonical source candles are one-minute bar-open observations;
* a target-timeframe signal is committed only at its scheduled UTC bucket end;
* an order is filled at the first later real one-minute open.

The stored canonical files do not contain first-seen or revision timestamps.
Results are therefore a replay of the *current* canonical revision, not an
as-was-live historical record and not evidence that a strategy will be
profitable in production.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import polars as pl
from chart_config import (
    BYBIT_ASSETS,
    CANONICAL_TIMEFRAMES,
    resolve_ohlcv_files,
    timeframe_seconds,
)
from indicators import (
    CUSUM_SENSITIVITIES,
    DEFAULT_CUSUM_SENSITIVITY,
    CusumTrendEngine,
)
from online_signals import OnlineSignalConfig, OnlineSignalEngine
from trade_ml.artifact import (
    LogisticCoefficientArtifact,
    artifact_deployment_rejection,
    digest_feature_schema,
)
from trade_ml.contracts import (
    BarrierConfig,
    BarrierPlan,
    TradeSide,
    activate_barrier_plan,
)
from trade_ml.economics import nonembedded_cost_bps
from trade_ml.features import (
    META_FEATURE_NAMES,
    FeatureSnapshot,
    build_feature_snapshot,
)
from trade_ml.inference import InferenceResult, score_features
from trade_ml.labeling import (
    BarrierEvaluation,
    BarrierOutcome,
    BarrierTracker,
    MinuteBar,
    cancel_barrier_plan,
)
from trade_ml.shadow import (
    ShadowCandidate,
    ShadowEventBook,
    ShadowGapPolicy,
)

MINUTE_REPLAY_VERSION = "current_canonical_minute_replay_v2"
EXECUTION_MODEL_VERSION = "normalized_next_real_minute_open_v2"
MINUTE_SECONDS = 60
INGESTION_SAFETY_LAG_SECONDS = 5
DEFAULT_REPLAY_DAYS = 365
MAX_REPLAY_DAYS = 730
MAX_SOURCE_MINUTES = 1_250_000
MAX_CHART_SERIES_POINTS = 12_000
DEFAULT_EVENT_LIMIT = 5_000
DEFAULT_WARMUP_TARGET_BARS = 240
SESSION_GAP_TOLERANCE_SECONDS = 4 * 24 * 60 * 60
META_FILTER_MODES = frozenset(("off", "shadow", "gate"))


def _stable_digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _json_dataclass(instance: Any) -> dict[str, Any]:
    payload = asdict(instance)
    for key, value in tuple(payload.items()):
        if isinstance(value, tuple):
            payload[key] = list(value)
    return payload


@dataclass(frozen=True)
class IndicatorStrategyConfig:
    """Executable mapping from the Analyst indicator components.

    Prototype-regime values are untrained diagnostic weights.  They do not
    veto execution unless the explicitly experimental ablation flag is enabled.
    """

    cusum_sensitivity: str = DEFAULT_CUSUM_SENSITIVITY
    horizons: tuple[int, int, int] = (12, 48, 192)
    trend_z_clip: float = 8.0
    aligned_score: float = 0.20
    aligned_quality: float = 0.25
    developing_score: float = 0.08
    change_risk_threshold: float = 0.55
    max_fast_slow_ratio: float = 1.75
    minimum_path_quality: float = 0.15
    trade_developing_trends: bool = True
    require_cusum_agreement: bool = True
    enable_experimental_prototype_regime_gate: bool = False
    require_regime_direction: bool = False
    maximum_exposure: float = 1.0
    minimum_volatility_scale: float = 0.25
    position_step: float = 0.10

    def __post_init__(self) -> None:
        if self.cusum_sensitivity not in CUSUM_SENSITIVITIES:
            raise ValueError("Unknown CUSUM sensitivity")
        if (
            len(self.horizons) != 3
            or tuple(sorted(self.horizons)) != self.horizons
            or len(set(self.horizons)) != 3
            or any(value <= 0 for value in self.horizons)
        ):
            raise ValueError("horizons must be three strictly increasing positive ints")
        finite = (
            self.trend_z_clip,
            self.aligned_score,
            self.aligned_quality,
            self.developing_score,
            self.change_risk_threshold,
            self.max_fast_slow_ratio,
            self.minimum_path_quality,
            self.maximum_exposure,
            self.minimum_volatility_scale,
            self.position_step,
        )
        if not all(math.isfinite(value) for value in finite):
            raise ValueError("Indicator strategy parameters must be finite")
        if self.trend_z_clip <= 0.0:
            raise ValueError("trend_z_clip must be positive")
        if not 0.0 <= self.developing_score <= self.aligned_score <= 1.0:
            raise ValueError("Trend thresholds are invalid")
        if not 0.0 <= self.aligned_quality <= 1.0:
            raise ValueError("aligned_quality must be between zero and one")
        if not 0.0 <= self.change_risk_threshold <= 1.0:
            raise ValueError("change_risk_threshold must be between zero and one")
        if self.max_fast_slow_ratio <= 0.0:
            raise ValueError("max_fast_slow_ratio must be positive")
        if not 0.0 <= self.minimum_path_quality <= 1.0:
            raise ValueError("minimum_path_quality must be between zero and one")
        if not 0.0 < self.maximum_exposure <= 1.0:
            raise ValueError("maximum_exposure must be in (0, 1]")
        if not 0.0 < self.minimum_volatility_scale <= 1.0:
            raise ValueError("minimum_volatility_scale must be in (0, 1]")
        if not 0.0 < self.position_step <= self.maximum_exposure:
            raise ValueError("position_step must be in (0, maximum_exposure]")
        if not isinstance(self.enable_experimental_prototype_regime_gate, bool):
            raise ValueError("enable_experimental_prototype_regime_gate must be a bool")

    def as_dict(self) -> dict[str, Any]:
        return _json_dataclass(self)

    def digest(self) -> str:
        return _stable_digest(self.as_dict())


@dataclass(frozen=True)
class ReplayCostConfig:
    """Normalized next-open execution assumptions."""

    fee_bps: float = 1.0
    slippage_bps: float = 1.0
    spread_bps: float = 0.0
    execution_latency_minutes: int = 1
    initial_equity: float = 1.0

    def __post_init__(self) -> None:
        if not all(
            math.isfinite(value)
            for value in (
                self.fee_bps,
                self.slippage_bps,
                self.spread_bps,
                self.initial_equity,
            )
        ):
            raise ValueError("Replay cost parameters must be finite")
        if self.fee_bps < 0.0 or self.slippage_bps < 0.0 or self.spread_bps < 0.0:
            raise ValueError("Replay costs must be non-negative")
        if (
            isinstance(self.execution_latency_minutes, bool)
            or not isinstance(self.execution_latency_minutes, int)
            or self.execution_latency_minutes < 0
        ):
            raise ValueError("execution_latency_minutes must be a non-negative int")
        if self.initial_equity <= 0.0:
            raise ValueError("initial_equity must be positive")

    def as_dict(self) -> dict[str, Any]:
        return _json_dataclass(self)

    def digest(self) -> str:
        return _stable_digest(self.as_dict())


@dataclass(frozen=True)
class ProtectedReplayConfig:
    """Explicit opt-in static bracket experiment for the minute replay.

    ``timeout_target_bars`` counts accepted finalized candles in the selected
    signal timeframe. Session closures count zero while a sparse, accepted
    session candle counts once. Keeping this separate from
    :class:`IndicatorStrategyConfig` preserves the locked E0 strategy digest.
    """

    enabled: bool = False
    risk_unit_volatility_multiplier: float = 2.0
    stop_risk_units: float = 1.0
    target_risk_units: float = 2.0
    timeout_target_bars: int = 20
    break_even_safety_margin: float = 0.05

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ValueError("enabled must be bool")
        finite_positive = (
            self.risk_unit_volatility_multiplier,
            self.stop_risk_units,
            self.target_risk_units,
        )
        if not all(math.isfinite(value) and value > 0.0 for value in finite_positive):
            raise ValueError(
                "Protected replay risk and barrier values must be positive"
            )
        if (
            isinstance(self.timeout_target_bars, bool)
            or not isinstance(self.timeout_target_bars, int)
            or self.timeout_target_bars <= 0
        ):
            raise ValueError("timeout_target_bars must be a positive int")
        if (
            not math.isfinite(self.break_even_safety_margin)
            or not 0.0 <= self.break_even_safety_margin < 1.0
        ):
            raise ValueError("break_even_safety_margin must be within [0, 1)")

    def barrier_config(self, timeframe: str) -> BarrierConfig:
        target_interval = timeframe_seconds(timeframe.strip().lower())
        return BarrierConfig(
            stop_risk_units=self.stop_risk_units,
            target_risk_units=self.target_risk_units,
            timeout_target_bars=self.timeout_target_bars,
            target_interval_seconds=target_interval,
        )

    def as_dict(self, *, timeframe: str | None = None) -> dict[str, Any]:
        payload = _json_dataclass(self)
        if timeframe is not None:
            barrier = self.barrier_config(timeframe)
            payload["finalized_target_barrier"] = barrier.as_dict()
            payload["finalized_target_barrier_digest"] = barrier.digest()
        return payload

    def digest(self) -> str:
        return _stable_digest(self.as_dict())


def meta_label_policy_digest(
    *,
    strategy: IndicatorStrategyConfig,
    costs: ReplayCostConfig,
    protection: ProtectedReplayConfig,
    timeframe: str,
) -> str:
    """Digest the exact candidate, barrier, and cost question scored by ML.

    The timeout geometry is carried by the feature snapshot, so the policy
    family digest intentionally remains identical across canonical
    timeframes.  Validating ``timeframe`` here still prevents callers from
    creating an apparently valid digest for an unsupported interval.
    """

    if not protection.enabled:
        raise ValueError("Meta-label policy requires an enabled protected bracket")
    normalized_timeframe = timeframe.strip().lower()
    if normalized_timeframe not in CANONICAL_TIMEFRAMES:
        allowed = ", ".join(CANONICAL_TIMEFRAMES)
        raise ValueError(
            f"Unsupported timeframe {timeframe!r}; expected one of: {allowed}"
        )
    timeframe_seconds(normalized_timeframe)
    payload = {
        "policy_version": "cusum_new_setup_immutable_bracket_v2",
        "event_sampling": "cusum_bull_or_bear_start_once",
        "strategy_digest": strategy.digest(),
        "cost_digest": costs.digest(),
        "protected_bracket": protection.as_dict(),
        "timeout_clock": "accepted_finalized_target_bars",
        "strategy_exit_policy": "ignored_while_bracket_active",
        "label_clock": "max_nominal_close_and_first_seen_observation",
        "cost_accounting": "adverse_entry_embedded_once_then_nonembedded_costs",
        "execution_model_version": EXECUTION_MODEL_VERSION,
        "same_bar_primary": "stop_first",
        "timeout_binary_label": 0,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def execution_eligible_at(
    *,
    scheduled_close: datetime,
    observed_at: datetime,
    latency_minutes: int,
) -> datetime:
    """Return the first whole-minute boundary at or after order eligibility.

    Historical replay passes a deterministic observation-time scenario; the
    forward-paper path can pass the actual first-seen provider timestamp.  The
    shared calculation prevents the two paths from silently disagreeing about
    latency rounding.
    """

    if (
        isinstance(latency_minutes, bool)
        or not isinstance(latency_minutes, int)
        or latency_minutes < 0
    ):
        raise ValueError("latency_minutes must be a non-negative int")
    base = max(_utc(scheduled_close), _utc(observed_at)) + timedelta(
        minutes=latency_minutes
    )
    rounded_epoch = math.ceil(base.timestamp() / MINUTE_SECONDS) * MINUTE_SECONDS
    return datetime.fromtimestamp(rounded_epoch, tz=timezone.utc)


def execution_costs(
    *, equity: float, turnover: float, costs: ReplayCostConfig
) -> dict[str, float]:
    """Return normalized one-way execution costs for a position change.

    ``spread_bps`` is the quoted full bid/ask spread, so a market order pays
    half of it relative to the reference mid/open.  Slippage is an additional
    adverse one-way assumption and fees apply to the full changed notional.
    """

    equity_value = float(equity)
    turnover_value = float(turnover)
    if not math.isfinite(equity_value) or equity_value < 0.0:
        raise ValueError("equity must be finite and non-negative")
    if not math.isfinite(turnover_value) or turnover_value < 0.0:
        raise ValueError("turnover must be finite and non-negative")
    notional = equity_value * turnover_value
    fee = notional * costs.fee_bps / 10_000.0
    slippage = notional * costs.slippage_bps / 10_000.0
    spread = notional * (0.5 * costs.spread_bps) / 10_000.0
    return {
        "fee": fee,
        "slippage": slippage,
        "spread": spread,
        "total": fee + slippage + spread,
    }


def _estimated_roundtrip_cost_bps(costs: ReplayCostConfig) -> float:
    return 2.0 * (costs.fee_bps + costs.slippage_bps + 0.5 * costs.spread_bps)


def _decision_static_stop_break_even_probability(
    *,
    entry_reference: float,
    risk_unit: float | None,
    barrier: BarrierConfig,
    costs: ReplayCostConfig,
    side: TradeSide,
) -> float | None:
    """Return a declared static STOP-vs-TP approximation at decision time.

    Class zero also contains timeouts and ambiguity, so this is deliberately
    not presented as an exact economic break-even probability.
    """

    entry = _finite_float(entry_reference)
    risk = _finite_float(risk_unit)
    if entry is None or entry <= 0.0 or risk is None or risk <= 0.0:
        return None
    adverse_entry_bps = costs.slippage_bps + 0.5 * costs.spread_bps
    expected_fill = entry * (1.0 + side.multiplier * adverse_entry_bps / 10_000.0)
    if expected_fill <= 0.0:
        return None
    loss = barrier.stop_risk_units * risk / expected_fill
    gain = barrier.target_risk_units * risk / expected_fill
    roundtrip_cost = _estimated_roundtrip_cost_bps(costs)
    remaining_cost = (
        nonembedded_cost_bps(
            roundtrip_cost_bps=roundtrip_cost,
            embedded_entry_execution_bps=adverse_entry_bps,
        )
        / 10_000.0
    )
    denominator = gain + loss
    if denominator <= 0.0:
        return None
    return max((loss + remaining_cost) / denominator, 0.0)


def adverse_execution_price(
    *, reference_price: float, order_delta: float, costs: ReplayCostConfig
) -> float:
    """Return the deterministic adverse market-order scenario price."""

    price = float(reference_price)
    delta = float(order_delta)
    if not math.isfinite(price) or price <= 0.0:
        raise ValueError("reference_price must be finite and positive")
    if not math.isfinite(delta):
        raise ValueError("order_delta must be finite")
    if math.isclose(delta, 0.0, abs_tol=1e-15):
        return price
    adverse_bps = costs.slippage_bps + 0.5 * costs.spread_bps
    return price * (1.0 + math.copysign(adverse_bps / 10_000.0, delta))


class CausalCandleBuilder:
    """Build one UTC-anchored target candle from finalized real 1m rows."""

    def __init__(self, timeframe: str) -> None:
        self.timeframe = timeframe.strip().lower()
        self.interval_seconds = timeframe_seconds(self.timeframe)
        if self.interval_seconds % MINUTE_SECONDS != 0:
            raise ValueError("Minute replay requires a whole-minute timeframe")
        self._bar: dict[str, Any] | None = None

    @property
    def bucket_end(self) -> datetime | None:
        if self._bar is None:
            return None
        return self._bar["timestamp"] + timedelta(seconds=self.interval_seconds)

    def advance_to(self, timestamp: datetime) -> dict[str, Any] | None:
        """Finalize the current non-empty bucket once its scheduled end is known."""

        timestamp = _utc(timestamp)
        end = self.bucket_end
        if self._bar is None or end is None or timestamp < end:
            return None
        closed = dict(self._bar)
        closed["available_at"] = end
        self._bar = None
        return closed

    def add(self, row: dict[str, Any]) -> None:
        timestamp = _utc(row["timestamp"])
        bucket = _bucket_start(timestamp, self.interval_seconds)
        if self._bar is not None and self._bar["timestamp"] != bucket:
            raise ValueError("Candle builder must be advanced before a new bucket")
        if self._bar is None:
            self._bar = {
                "timestamp": bucket,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": _finite_or_zero(row.get("volume")),
                "is_session_open_bar": bool(row.get("is_session_open_bar", False)),
                "source_minute_count": 1,
                "source_minute_first": timestamp,
                "source_minute_last": timestamp,
                "source_minutes_contiguous": (
                    timestamp.second == 0 and timestamp.microsecond == 0
                ),
            }
            return
        previous_source_minute = _utc(self._bar["source_minute_last"])
        if timestamp != previous_source_minute + timedelta(minutes=1):
            self._bar["source_minutes_contiguous"] = False
        self._bar["high"] = max(float(self._bar["high"]), float(row["high"]))
        self._bar["low"] = min(float(self._bar["low"]), float(row["low"]))
        self._bar["close"] = float(row["close"])
        self._bar["volume"] += _finite_or_zero(row.get("volume"))
        self._bar["is_session_open_bar"] = bool(
            self._bar["is_session_open_bar"] or row.get("is_session_open_bar", False)
        )
        self._bar["source_minute_count"] += 1
        self._bar["source_minute_last"] = timestamp


def _target_bar_completeness(
    bar: dict[str, Any], *, asset: str, timeframe: str
) -> dict[str, Any]:
    normalized_asset = str(asset).strip().upper()
    normalized_timeframe = str(timeframe).strip().lower()
    expected_minutes = timeframe_seconds(normalized_timeframe) // MINUTE_SECONDS
    bucket_start = _utc(bar["timestamp"])
    expected_last = bucket_start + timedelta(minutes=expected_minutes - 1)
    first = _utc(bar.get("source_minute_first", bucket_start))
    last = _utc(bar.get("source_minute_last", first))
    source_count = int(bar.get("source_minute_count", 0))
    contiguous = bool(bar.get("source_minutes_contiguous", False))
    exact = bool(
        source_count == expected_minutes
        and first == bucket_start
        and last == expected_last
        and contiguous
    )
    if normalized_asset in BYBIT_ASSETS:
        classification = "continuous_exact" if exact else "continuous_incomplete"
        complete = exact
    elif exact:
        classification = "session_exact"
        complete = True
    elif contiguous:
        # A contiguous fragment can still be missing unknown minutes at either
        # bucket edge.  Without an authoritative exchange schedule it must not
        # create detector state or a training candidate.
        classification = "session_incomplete_unverified_boundary"
        complete = False
    else:
        # The current canonical session calendar is inferred from observed
        # provider rows, not an authoritative exchange schedule.  A hole inside
        # a target bucket could therefore be either a closure or an outage.  It
        # is never safe to aggregate across that unknown path for labels.
        classification = "session_incomplete_unverified_internal_gap"
        complete = False
    return {
        "complete": complete,
        "classification": classification,
        "expected_source_minutes": expected_minutes,
        "source_minute_count": source_count,
        "source_minute_first": first,
        "source_minute_last": last,
        "source_minutes_contiguous": contiguous,
    }


def target_bar_is_complete(bar: dict[str, Any], asset: str, timeframe: str) -> bool:
    """Return whether a target candle satisfies its asset cadence contract."""

    return bool(
        _target_bar_completeness(bar, asset=asset, timeframe=timeframe)["complete"]
    )


def _parse_utc(value: str | datetime | None) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return _utc(value)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return _utc(parsed)


def load_canonical_minute_window(
    *,
    asset: str,
    timeframe: str,
    start: str | datetime | None = None,
    end: str | datetime | None = None,
    replay_days: int = DEFAULT_REPLAY_DAYS,
    now: datetime | None = None,
    warmup_target_bars: int = DEFAULT_WARMUP_TARGET_BARS,
    max_source_minutes: int = MAX_SOURCE_MINUTES,
) -> tuple[pl.DataFrame, dict[str, Any]]:
    """Load a bounded canonical 1m window plus hidden causal signal warm-up."""

    normalized_asset = asset.strip().upper()
    interval_seconds = timeframe_seconds(timeframe)
    if (
        isinstance(replay_days, bool)
        or not isinstance(replay_days, int)
        or not 1 <= replay_days <= MAX_REPLAY_DAYS
    ):
        raise ValueError(f"replay_days must be between 1 and {MAX_REPLAY_DAYS}")
    if warmup_target_bars < 0:
        raise ValueError("warmup_target_bars must be non-negative")
    if max_source_minutes <= 0:
        raise ValueError("max_source_minutes must be positive")

    resolution = resolve_ohlcv_files(
        asset=normalized_asset,
        timeframe="1m",
        source="canonical",
    )
    safe_clock = _utc(now or datetime.now(timezone.utc)) - timedelta(
        seconds=INGESTION_SAFETY_LAG_SECONDS
    )
    requested_end = _parse_utc(end) or safe_clock
    evaluation_end = min(requested_end, safe_clock)
    requested_start = _parse_utc(start)
    evaluation_start = requested_start or (evaluation_end - timedelta(days=replay_days))
    if evaluation_start >= evaluation_end:
        raise ValueError("Replay start must be before replay end")

    # Session assets need extra calendar time for weekends and exchange breaks.
    warmup_multiplier = 1 if normalized_asset in BYBIT_ASSETS else 2
    warmup_seconds = interval_seconds * warmup_target_bars * warmup_multiplier
    scan_start = _bucket_start(
        evaluation_start - timedelta(seconds=warmup_seconds),
        interval_seconds,
    )

    lazy = pl.scan_parquet([str(path) for path in resolution.files])
    schema = lazy.collect_schema()
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = required - set(schema.names())
    if missing:
        raise ValueError(
            "Canonical 1m source is missing required columns: "
            + ", ".join(sorted(missing))
        )
    optional = (
        "calendar_id",
        "is_synthetic_no_trade",
        "is_session_open_bar",
    )
    expressions = [
        pl.col("timestamp"),
        pl.col("open").cast(pl.Float64),
        pl.col("high").cast(pl.Float64),
        pl.col("low").cast(pl.Float64),
        pl.col("close").cast(pl.Float64),
        pl.col("volume").cast(pl.Float64),
        *(pl.col(name) for name in optional if name in schema),
    ]
    frame = (
        lazy.select(expressions)
        .filter(
            (pl.col("timestamp") >= pl.lit(scan_start))
            & (pl.col("timestamp") < pl.lit(evaluation_end))
            & (pl.col("timestamp") + pl.duration(minutes=1) <= pl.lit(safe_clock))
        )
        .unique(subset=["timestamp"], keep="last")
        .sort("timestamp")
        .collect()
    )
    if frame.is_empty():
        raise ValueError("No safely closed canonical 1m rows in the replay window")
    if frame.height > max_source_minutes:
        raise ValueError(
            f"Replay needs {frame.height:,} source minutes; limit is "
            f"{max_source_minutes:,}. Shorten replay_days or the explicit range."
        )
    first_timestamp = _utc(frame["timestamp"].min())
    last_timestamp = _utc(frame["timestamp"].max())
    source_snapshot = []
    for path in resolution.files:
        stat = path.stat()
        source_snapshot.append(
            {
                "path": _relative_source_path(path),
                "size": int(stat.st_size),
                "mtime_ns": int(stat.st_mtime_ns),
            }
        )
    metadata = {
        "asset": normalized_asset,
        "timeframe": timeframe.strip().lower(),
        "source": "canonical_1m",
        "evaluation_start": _iso(evaluation_start),
        "evaluation_end": _iso(evaluation_end),
        "scan_start": _iso(scan_start),
        "loaded_start": _iso(first_timestamp),
        "loaded_end": _iso(last_timestamp),
        "source_rows": frame.height,
        "warmup_target_bars_requested": int(warmup_target_bars),
        "safe_clock": _iso(safe_clock),
        "source_snapshot": source_snapshot,
        "source_generation": _stable_digest({"files": source_snapshot}),
    }
    return frame, metadata


def run_minute_replay(
    frame: pl.DataFrame,
    *,
    asset: str,
    timeframe: str,
    strategy: IndicatorStrategyConfig | None = None,
    costs: ReplayCostConfig | None = None,
    protection: ProtectedReplayConfig | None = None,
    meta_filter_mode: str = "off",
    meta_artifact: LogisticCoefficientArtifact | None = None,
    evaluation_start: str | datetime | None = None,
    replay_clock: str | datetime | None = None,
    event_limit: int = DEFAULT_EVENT_LIMIT,
    capture_series: bool = True,
) -> dict[str, Any]:
    """Replay one selected asset/timeframe causally over finalized 1m rows."""

    if (
        isinstance(event_limit, bool)
        or not isinstance(event_limit, int)
        or event_limit < 0
    ):
        raise ValueError("event_limit must be a non-negative int")
    if not isinstance(capture_series, bool):
        raise ValueError("capture_series must be bool")
    strategy = strategy or IndicatorStrategyConfig()
    costs = costs or ReplayCostConfig()
    protection = protection or ProtectedReplayConfig()
    meta_filter_mode = str(meta_filter_mode).strip().lower()
    if meta_filter_mode not in META_FILTER_MODES:
        allowed = ", ".join(sorted(META_FILTER_MODES))
        raise ValueError(f"meta_filter_mode must be one of: {allowed}")
    if meta_filter_mode != "off" and not protection.enabled:
        raise ValueError("Meta-label scoring requires an enabled protected bracket")
    if meta_artifact is not None and not isinstance(
        meta_artifact, LogisticCoefficientArtifact
    ):
        raise TypeError("meta_artifact must be a LogisticCoefficientArtifact")
    normalized_asset = asset.strip().upper()
    normalized_timeframe = timeframe.strip().lower()
    if meta_filter_mode == "gate":
        deployment_rejection = artifact_deployment_rejection(
            meta_artifact,
            asset=normalized_asset,
            timeframe=normalized_timeframe,
        )
        if deployment_rejection is not None:
            raise ValueError(
                "meta_filter_mode=gate requires an explicitly promoted artifact "
                "whose locked walk-forward deployment gate passed for this exact "
                "asset/timeframe selection: "
                f"{deployment_rejection}"
            )
    interval_seconds = timeframe_seconds(normalized_timeframe)
    source = _normalized_minute_frame(frame)
    if source.is_empty():
        raise ValueError("Minute replay frame is empty")

    source_first = _utc(source["timestamp"].min())
    source_last = _utc(source["timestamp"].max())
    observation_delay = timedelta(seconds=MINUTE_SECONDS + INGESTION_SAFETY_LAG_SECONDS)
    clock = _parse_utc(replay_clock) or (source_last + observation_delay)
    eval_start = _parse_utc(evaluation_start) or source_first
    if eval_start >= clock:
        raise ValueError("evaluation_start must be before replay_clock")

    source = source.filter(
        pl.col("timestamp")
        + pl.duration(seconds=MINUTE_SECONDS + INGESTION_SAFETY_LAG_SECONDS)
        <= pl.lit(clock)
    )
    input_rows = source.height
    synthetic_rows = 0
    if "is_synthetic_no_trade" in source.columns:
        synthetic_rows = int(
            source.select(pl.col("is_synthetic_no_trade").fill_null(False).sum()).item()
        )
        source = source.filter(~pl.col("is_synthetic_no_trade").fill_null(False))
    if source.is_empty():
        raise ValueError("Replay contains no real, safely closed source minutes")

    online_config = OnlineSignalConfig(
        horizons=strategy.horizons,
        trend_z_clip=strategy.trend_z_clip,
        aligned_score=strategy.aligned_score,
        aligned_quality=strategy.aligned_quality,
        developing_score=strategy.developing_score,
        change_risk_threshold=strategy.change_risk_threshold,
        expected_interval_seconds=interval_seconds,
        max_gap_seconds=(
            interval_seconds
            if normalized_asset in BYBIT_ASSETS
            else max(interval_seconds, SESSION_GAP_TOLERANCE_SECONDS)
        ),
    )
    online_engine = OnlineSignalEngine(online_config)
    cusum_engine = CusumTrendEngine(strategy.cusum_sensitivity)
    builder = CausalCandleBuilder(normalized_timeframe)
    evaluation_rows = int(
        source.filter(pl.col("timestamp") >= pl.lit(eval_start)).height
    )
    target_minutes = interval_seconds // MINUTE_SECONDS
    display_stride_minutes = max(
        target_minutes,
        math.ceil(max(evaluation_rows, 1) / MAX_CHART_SERIES_POINTS),
    )
    ledger = _ExecutionLedger(
        costs=costs,
        protection=protection,
        timeframe=normalized_timeframe,
        evaluation_start=eval_start,
        display_stride_minutes=display_stride_minutes,
        event_limit=event_limit,
        capture_series=capture_series,
    )
    strategy_digest = strategy.digest()
    meta_policy_digest = (
        meta_label_policy_digest(
            strategy=strategy,
            costs=costs,
            protection=protection,
            timeframe=normalized_timeframe,
        )
        if protection.enabled
        else None
    )
    pending_order: dict[str, Any] | None = None
    signals: deque[dict[str, Any]] = deque(maxlen=event_limit)
    orders: deque[dict[str, Any]] = deque(maxlen=event_limit)
    meta_score_events: deque[dict[str, Any]] = deque(maxlen=event_limit)
    meta_score_points: deque[dict[str, Any]] = deque(maxlen=MAX_CHART_SERIES_POINTS)
    shadow_book = (
        ShadowEventBook(
            max_open_events=max(DEFAULT_EVENT_LIMIT, event_limit, 1),
            max_resolved_records=max(event_limit, 1),
        )
        if protection.enabled
        else None
    )
    signal_count = 0
    order_count = 0
    meta_candidate_count = 0
    meta_scored_count = 0
    meta_accepted_count = 0
    meta_rejected_count = 0
    meta_unavailable_count = 0
    meta_label_schedule_rejected_count = 0
    order_suppressed_pending_count = 0
    target_bar_count = 0
    complete_target_bar_count = 0
    suppressed_incomplete_target_bars = 0
    suppressed_unobserved_target_bars = 0
    target_bar_completeness_counts: dict[str, int] = {}
    invalid_source_rows = 0
    continuous_source_gap_count = 0
    missing_continuous_source_minutes = 0
    unverified_session_source_gap_count = 0
    missing_unverified_session_source_minutes = 0
    order_cancelled_data_gap_count = 0
    last_valid_source_timestamp: datetime | None = None

    def commit_closed_bar(bar: dict[str, Any]) -> None:
        nonlocal complete_target_bar_count
        nonlocal cusum_engine
        nonlocal online_engine
        nonlocal order_count
        nonlocal order_suppressed_pending_count
        nonlocal pending_order
        nonlocal signal_count
        nonlocal meta_accepted_count
        nonlocal meta_candidate_count
        nonlocal meta_rejected_count
        nonlocal meta_scored_count
        nonlocal meta_unavailable_count
        nonlocal meta_label_schedule_rejected_count
        nonlocal suppressed_incomplete_target_bars
        nonlocal suppressed_unobserved_target_bars
        nonlocal target_bar_count

        available_at = _utc(bar["available_at"])
        observed_at = available_at + timedelta(seconds=INGESTION_SAFETY_LAG_SECONDS)
        if observed_at > clock:
            suppressed_unobserved_target_bars += 1
            return
        target_bar_count += 1
        completeness = _target_bar_completeness(
            bar,
            asset=normalized_asset,
            timeframe=normalized_timeframe,
        )
        classification = str(completeness["classification"])
        target_bar_completeness_counts[classification] = (
            target_bar_completeness_counts.get(classification, 0) + 1
        )
        if not completeness["complete"]:
            suppressed_incomplete_target_bars += 1
            # A missing continuous-market source minute makes both return and
            # detector state unknowable.  Reset instead of bridging the gap or
            # allowing a partial candle to influence a later signal.
            online_engine = OnlineSignalEngine(online_config)
            cusum_engine = CusumTrendEngine(strategy.cusum_sensitivity)
            return

        complete_target_bar_count += 1
        ledger.advance_protected_target_bar(
            bar=bar,
            observed_at=observed_at,
        )
        if shadow_book is not None:
            shadow_book.advance_target_bar(
                asset=normalized_asset,
                timeframe=normalized_timeframe,
                bar_open=bar["timestamp"],
                close_price=float(bar["close"]),
                observed_at=observed_at,
            )
        online = online_engine.update(
            timestamp=bar["timestamp"],
            open_value=bar["open"],
            high=bar["high"],
            low=bar["low"],
            close=bar["close"],
            volume=bar["volume"],
            is_final=True,
            scheduled_gap=bool(bar.get("is_session_open_bar", False)),
        )
        cusum = cusum_engine.update(
            timestamp=bar["timestamp"],
            close=bar["close"],
        )
        desired, reason = _desired_position(
            online=online,
            cusum=cusum,
            strategy=strategy,
        )
        if (
            protection.enabled
            and ledger.requires_fresh_cusum_setup
            and abs(ledger.position) <= 1e-12
            and abs(desired) > 1e-12
        ):
            has_fresh_setup = bool(
                cusum.get("bull_start", False)
                if desired > 0.0
                else cusum.get("bear_start", False)
            )
            if not has_fresh_setup:
                desired = 0.0
                reason = "flat_waiting_fresh_cusum_setup_after_protected_exit"
        risk_unit = _protected_risk_unit(
            close=float(bar["close"]),
            online=online,
            cusum=cusum,
            protection=protection,
        )
        opens_new_direction = abs(desired) > 1e-12 and (
            abs(ledger.position) <= 1e-12
            or math.copysign(1.0, desired) != math.copysign(1.0, ledger.position)
        )
        if protection.enabled and opens_new_direction and risk_unit is None:
            desired = 0.0
            reason = "flat_protected_risk_scale_unavailable"
        eligible_at = execution_eligible_at(
            scheduled_close=available_at,
            observed_at=observed_at,
            latency_minutes=costs.execution_latency_minutes,
        )
        signal_identity = {
            "asset": normalized_asset,
            "timeframe": normalized_timeframe,
            "source_bar_open": _iso(bar["timestamp"]),
            "available_at": _iso(available_at),
            "strategy_digest": strategy_digest,
        }
        signal = {
            "signal_id": hashlib.sha256(
                json.dumps(
                    signal_identity, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
            ).hexdigest()[:24],
            **signal_identity,
            "observed_at": _iso(observed_at),
            "eligible_at": eligible_at,
            "desired_position": desired,
            "reason": reason,
            "status": online.get("status"),
            "trend_state_code": online.get("trend_state_code"),
            "trend_score": online.get("trend_score"),
            "path_quality": online.get("path_quality"),
            "fast_slow_ratio": online.get("fast_slow_ratio"),
            "cusum_regime": cusum.get("regime"),
            "cusum_bull_start": bool(cusum.get("bull_start", False)),
            "cusum_bear_start": bool(cusum.get("bear_start", False)),
            "cusum_residual_scale": cusum.get("res_std"),
            "cusum_trail_stop": cusum.get("trail_stop"),
            "ewma_vol_slow_pct": online.get("ewma_vol_slow_pct"),
            "protected_risk_unit": risk_unit,
            "protected_bracket_enabled": protection.enabled,
            "regime_state": online.get("regime_state"),
            "regime_change_risk": online.get("regime_change_risk"),
            "source_minute_count": int(bar["source_minute_count"]),
            "expected_source_minute_count": int(
                completeness["expected_source_minutes"]
            ),
            "target_bar_completeness": classification,
        }
        if available_at < eval_start:
            return

        setup_side = (
            TradeSide.LONG
            if bool(cusum.get("bull_start", False))
            else TradeSide.SHORT
            if bool(cusum.get("bear_start", False))
            else None
        )
        snapshot: FeatureSnapshot | None = None
        feature_error: str | None = None
        expanded_barrier = (
            protection.barrier_config(normalized_timeframe)
            if protection.enabled
            else None
        )
        if setup_side is not None and protection.enabled:
            if risk_unit is None:
                feature_error = "protected_risk_scale_unavailable"
                meta_label_schedule_rejected_count += 1
            else:
                try:
                    assert expanded_barrier is not None
                    feature_online = dict(online)
                    if feature_online.get("available_at") is None:
                        feature_online["available_at"] = observed_at
                    feature_cusum = dict(cusum)
                    if feature_cusum.get("available_at") is None:
                        feature_cusum["available_at"] = observed_at
                    snapshot = build_feature_snapshot(
                        setup_id=signal["signal_id"],
                        side=setup_side,
                        decision_at=observed_at,
                        online=feature_online,
                        cusum=feature_cusum,
                        entry_reference=float(bar["close"]),
                        risk_unit=risk_unit,
                        stop_risk_units=expanded_barrier.stop_risk_units,
                        target_risk_units=expanded_barrier.target_risk_units,
                        timeout_target_bars=(expanded_barrier.timeout_target_bars),
                        target_interval_seconds=(
                            expanded_barrier.target_interval_seconds
                        ),
                        estimated_roundtrip_cost_bps=_estimated_roundtrip_cost_bps(
                            costs
                        ),
                    )
                    assert shadow_book is not None and meta_policy_digest is not None
                    shadow_book.schedule(
                        ShadowCandidate(
                            event_id=signal["signal_id"],
                            setup_id=signal["signal_id"],
                            asset=normalized_asset,
                            timeframe=normalized_timeframe,
                            decision_at=observed_at,
                            eligible_at=eligible_at,
                            side=setup_side,
                            entry_reference=float(bar["close"]),
                            risk_unit=risk_unit,
                            features=snapshot,
                            barrier_config=expanded_barrier,
                            policy_digest=meta_policy_digest,
                            estimated_roundtrip_cost_bps=(
                                _estimated_roundtrip_cost_bps(costs)
                            ),
                            adverse_entry_bps=(
                                costs.slippage_bps + 0.5 * costs.spread_bps
                            ),
                            gap_policy=(
                                ShadowGapPolicy.CONTINUOUS_CANCEL
                                if normalized_asset in BYBIT_ASSETS
                                else ShadowGapPolicy.SESSION_NEXT_OPEN
                            ),
                        )
                    )
                except (TypeError, ValueError) as exc:
                    feature_error = str(exc)
                    snapshot = None
                    meta_label_schedule_rejected_count += 1

        if meta_filter_mode != "off":
            inference: InferenceResult | None = None
            meta_gate_accepted: bool | None = None
            if setup_side is not None:
                meta_candidate_count += 1
                if snapshot is None:
                    inference = InferenceResult(
                        available=False,
                        accepted=False,
                        probability=None,
                        decision_threshold=(
                            None
                            if meta_artifact is None
                            else meta_artifact.decision_threshold
                        ),
                        reason="feature_snapshot_invalid",
                        model_version=(
                            None
                            if meta_artifact is None
                            else meta_artifact.model_version
                        ),
                        artifact_checksum=(
                            None if meta_artifact is None else meta_artifact.checksum
                        ),
                    )
                elif meta_artifact is None:
                    inference = InferenceResult(
                        available=False,
                        accepted=False,
                        probability=None,
                        decision_threshold=None,
                        reason="artifact_not_configured",
                        model_version=None,
                        artifact_checksum=None,
                    )
                else:
                    assert meta_policy_digest is not None
                    inference = score_features(
                        meta_artifact,
                        snapshot.feature_map(),
                        expected_feature_names=META_FEATURE_NAMES,
                        expected_policy_digest=meta_policy_digest,
                        asset=normalized_asset,
                        timeframe=normalized_timeframe,
                        decision_at=observed_at,
                    )

                static_break_even_probability = (
                    None
                    if expanded_barrier is None
                    else _decision_static_stop_break_even_probability(
                        entry_reference=float(bar["close"]),
                        risk_unit=risk_unit,
                        barrier=expanded_barrier,
                        costs=costs,
                        side=setup_side,
                    )
                )
                static_threshold_with_margin = (
                    None
                    if static_break_even_probability is None
                    else static_break_even_probability
                    + protection.break_even_safety_margin
                )
                static_payoff_untradeable = bool(
                    static_threshold_with_margin is not None
                    and static_threshold_with_margin >= 1.0
                )
                thresholds = [
                    value
                    for value in (
                        inference.decision_threshold,
                        static_threshold_with_margin,
                    )
                    if value is not None
                ]
                required_probability = (
                    None
                    if static_payoff_untradeable
                    else max(thresholds)
                    if thresholds
                    else None
                )
                meta_gate_accepted = bool(
                    inference.available
                    and inference.probability is not None
                    and required_probability is not None
                    and inference.probability > required_probability
                )

                score_event = {
                    "time": int(observed_at.timestamp()),
                    "event_id": signal["signal_id"],
                    "decision_at": _iso(observed_at),
                    "side": setup_side.value,
                    "mode": meta_filter_mode,
                    "available": inference.available,
                    "accepted": meta_gate_accepted,
                    "model_threshold_accepted": inference.accepted,
                    "value": inference.probability,
                    "probability": inference.probability,
                    "decision_threshold": inference.decision_threshold,
                    "decision_static_stop_break_even_probability": (
                        static_break_even_probability
                    ),
                    "break_even_safety_margin": (protection.break_even_safety_margin),
                    "static_threshold_with_margin": static_threshold_with_margin,
                    "static_payoff_untradeable_after_costs": (
                        static_payoff_untradeable
                    ),
                    "required_probability": required_probability,
                    "reason": inference.reason,
                    "model_version": inference.model_version,
                    "artifact_checksum": inference.artifact_checksum,
                    "policy_digest": meta_policy_digest,
                    "feature_schema_digest": (
                        None
                        if snapshot is None
                        else digest_feature_schema(snapshot.feature_names)
                    ),
                    "feature_snapshot_digest": (
                        None if snapshot is None else snapshot.digest()
                    ),
                    "feature_error": feature_error,
                    "stored_at_event_time": True,
                }
                meta_score_events.append(score_event)
                if inference.available and inference.probability is not None:
                    meta_scored_count += 1
                    meta_accepted_count += int(meta_gate_accepted)
                    meta_rejected_count += int(not meta_gate_accepted)
                    meta_score_points.append(
                        {
                            "time": int(observed_at.timestamp()),
                            "value": inference.probability,
                        }
                    )
                else:
                    meta_unavailable_count += 1
                signal["meta_filter"] = {
                    key: value
                    for key, value in score_event.items()
                    if key not in {"time", "feature_error"}
                }

            opens_new_direction = abs(desired) > 1e-12 and (
                abs(ledger.position) <= 1e-12
                or math.copysign(1.0, desired) != math.copysign(1.0, ledger.position)
            )
            if (
                meta_filter_mode == "gate"
                and opens_new_direction
                and ledger.active_barrier is None
            ):
                if setup_side is None:
                    desired = 0.0
                    reason = "flat_meta_gate_requires_new_cusum_setup"
                elif inference is None or not inference.available:
                    desired = 0.0
                    reason = "flat_meta_gate_unavailable"
                elif not meta_gate_accepted:
                    desired = 0.0
                    reason = "flat_meta_probability_below_threshold"
                signal["desired_position"] = desired
                signal["reason"] = reason

        if protection.enabled and ledger.active_barrier is not None:
            if not math.isclose(desired, ledger.position, abs_tol=1e-12):
                signal["suppressed_strategy_desired_position"] = desired
                desired = ledger.position
                reason = "protected_bracket_owns_position_until_terminal"
                signal["desired_position"] = desired
                signal["reason"] = reason

        signal_count += 1
        if pending_order is not None:
            order_suppressed_pending_count += 1
            signal["order_status"] = "suppressed_pending"
            signal["retained_order_id"] = pending_order["order_id"]
        elif math.isclose(desired, ledger.position, abs_tol=1e-12):
            signal["order_status"] = "no_change"
        else:
            order_identity = {
                "execution_model_version": EXECUTION_MODEL_VERSION,
                "signal_id": signal["signal_id"],
                "eligible_at": _iso(eligible_at),
                "desired_position": desired,
            }
            order_id = _stable_digest(order_identity)
            order = {
                "order_id": order_id,
                "status": "pending",
                "order_status": "pending",
                "execution_model_version": EXECUTION_MODEL_VERSION,
                "signal_id": signal["signal_id"],
                "created_at": observed_at,
                "scheduled_close": available_at,
                "observed_at": observed_at,
                "eligible_at": eligible_at,
                "desired_position": desired,
                "reason": reason,
                "protected_risk_unit": risk_unit,
                "_signal_record": signal,
            }
            signal["order_id"] = order_id
            signal["order_status"] = "pending"
            pending_order = order
            order_count += 1
            orders.append(order)
        signals.append(signal)

    for row in source.iter_rows(named=True):
        timestamp = _utc(row["timestamp"])
        valid_row = _valid_ohlcv_row(row)
        source_gap = bool(
            valid_row
            and last_valid_source_timestamp is not None
            and timestamp > last_valid_source_timestamp + timedelta(minutes=1)
        )
        unknown_path_gap_at = (
            last_valid_source_timestamp + timedelta(minutes=1)
            if source_gap and last_valid_source_timestamp is not None
            else None
        )
        missing_source_minutes = (
            max(
                0,
                int(
                    (timestamp - last_valid_source_timestamp).total_seconds()
                    // MINUTE_SECONDS
                )
                - 1,
            )
            if source_gap and last_valid_source_timestamp is not None
            else 0
        )
        if source_gap and normalized_asset in BYBIT_ASSETS:
            continuous_source_gap_count += 1
            missing_continuous_source_minutes += missing_source_minutes
        elif source_gap:
            # Session boundaries in the current canonical files are inferred
            # from observed provider rows.  They are useful chart metadata but
            # are not authoritative proof that a timestamp hole was closed.
            unverified_session_source_gap_count += 1
            missing_unverified_session_source_minutes += missing_source_minutes

        if source_gap:
            # A working order may have become eligible inside the missing
            # interval.  Its historical fill is unknowable, so never move it
            # to a later observed open and pretend that was the first fill.
            if pending_order is not None:
                pending_order["status"] = "cancelled_data_gap"
                pending_order["order_status"] = "cancelled_data_gap"
                pending_order["cancelled_at"] = timestamp
                signal_record = pending_order.get("_signal_record")
                if isinstance(signal_record, dict):
                    signal_record["order_status"] = "cancelled_data_gap"
                pending_order = None
                order_cancelled_data_gap_count += 1

        # Finalize the prior target candle before inspecting the next candle's
        # first minute. Horizontal touches inside the completed candle were
        # already processed, so its Nth accepted close can now time out without
        # allowing a future minute to win the race.
        closed = builder.advance_to(timestamp)
        if closed is not None:
            commit_closed_bar(closed)

        if valid_row and timestamp >= eval_start:
            minute_observed_at = timestamp + timedelta(
                seconds=MINUTE_SECONDS + INGESTION_SAFETY_LAG_SECONDS
            )
            if shadow_book is not None:
                shadow_book.update(
                    {
                        "asset": normalized_asset,
                        "timestamp": timestamp,
                        "open": row["open"],
                        "high": row["high"],
                        "low": row["low"],
                        "close": row["close"],
                        "observed_at": minute_observed_at,
                        "is_real": True,
                    }
                )
            pending_order = ledger.process_minute(
                row=row,
                pending_signal=pending_order,
                observed_at=minute_observed_at,
                unknown_path_gap_at=unknown_path_gap_at,
            )

        if source_gap:
            # Do not bridge a timestamp hole in either detector unless an
            # authoritative calendar proves the market was closed.  The current
            # observed-session calendar does not make that stronger claim.
            online_engine = OnlineSignalEngine(online_config)
            cusum_engine = CusumTrendEngine(strategy.cusum_sensitivity)

        if not valid_row:
            invalid_source_rows += 1
            continue
        builder.add(row)
        last_valid_source_timestamp = timestamp

    final_closed = builder.advance_to(clock)
    if final_closed is not None:
        commit_closed_bar(final_closed)
    ledger.finish()
    meta_label_book = (
        None if shadow_book is None else shadow_book.view(resolved_limit=event_limit)
    )

    result = ledger.result()
    metrics = result["metrics"]
    metrics.update(
        {
            "signal_count": signal_count,
            "order_count": order_count,
            "order_fill_count": metrics["fill_count"],
            "order_pending_count": 1 if pending_order is not None else 0,
            "order_suppressed_pending_count": order_suppressed_pending_count,
            "order_cancelled_data_gap_count": order_cancelled_data_gap_count,
            "meta_candidate_count": meta_candidate_count,
            "meta_scored_count": meta_scored_count,
            "meta_accepted_count": meta_accepted_count,
            "meta_rejected_count": meta_rejected_count,
            "meta_unavailable_count": meta_unavailable_count,
            "meta_label_schedule_rejected_count": (meta_label_schedule_rejected_count),
            "meta_label_scheduled_count": (
                0 if meta_label_book is None else meta_label_book["total_scheduled"]
            ),
            "meta_label_filled_count": (
                0 if meta_label_book is None else meta_label_book["total_filled"]
            ),
            "meta_label_resolved_count": (
                0 if meta_label_book is None else meta_label_book["total_resolved"]
            ),
            "meta_label_outcome_counts": (
                {outcome.value: 0 for outcome in BarrierOutcome}
                if meta_label_book is None
                else meta_label_book["outcome_counts"]
            ),
        }
    )

    retained_counts = {
        "signals": len(signals),
        "orders": len(orders),
        "fills": len(result["fills"]),
        "markers": len(result["markers"]),
        "meta_score_events": len(meta_score_events),
    }
    total_counts = {
        "signals": signal_count,
        "orders": order_count,
        "fills": metrics["fill_count"],
        "markers": metrics["marker_count"],
        "meta_score_events": meta_candidate_count,
    }
    metadata = {
        "mode": "current_canonical_minute_replay",
        "algorithm_version": MINUTE_REPLAY_VERSION,
        "execution_model_version": EXECUTION_MODEL_VERSION,
        "asset": normalized_asset,
        "timeframe": normalized_timeframe,
        "source_timeframe": "1m",
        "input_source_rows": input_rows,
        "processed_real_source_minutes": source.height,
        "evaluation_real_minutes": metrics["evaluated_real_minutes"],
        "excluded_synthetic_minutes": synthetic_rows,
        "invalid_source_rows": invalid_source_rows,
        "continuous_source_gap_count": continuous_source_gap_count,
        "missing_continuous_source_minutes": missing_continuous_source_minutes,
        "unverified_session_source_gap_count": (unverified_session_source_gap_count),
        "missing_unverified_session_source_minutes": (
            missing_unverified_session_source_minutes
        ),
        "target_closed_bars": target_bar_count,
        "target_complete_bars": complete_target_bar_count,
        "suppressed_incomplete_target_bars": suppressed_incomplete_target_bars,
        "suppressed_unobserved_target_bars": suppressed_unobserved_target_bars,
        "target_bar_completeness_counts": target_bar_completeness_counts,
        "evaluation_start": _iso(eval_start),
        "replay_clock": _iso(clock),
        "signal_availability": "scheduled_target_bucket_end",
        "execution_timing": "first_real_1m_open_at_or_after_signal_eligibility",
        "execution_latency_minutes": costs.execution_latency_minutes,
        "historical_observation_lag_seconds": INGESTION_SAFETY_LAG_SECONDS,
        "replay_clock_semantics": "actual_observation_cutoff",
        "display_stride_minutes": display_stride_minutes,
        "capture_series": capture_series,
        "event_limit": event_limit,
        "event_retention": {
            name: {
                "total": total_counts[name],
                "returned": retained_counts[name],
                "truncated": total_counts[name] > retained_counts[name],
            }
            for name in total_counts
        },
        "series_retention": result["series_retention"],
        "metrics_use_every_real_minute": True,
        "synthetic_fill_policy": "excluded_no_fill_no_signal_input",
        "session_finalization": (
            "scheduled_utc_bucket_end_only_internal_timestamp_holes_quarantined"
        ),
        "session_calendar_authority": "observed_provider_segments_not_exchange_schedule",
        "signal_vintage": "current_canonical_replay",
        "validation_safe": False,
        "as_was_live_journal": False,
        "diagnostic_only": True,
        "normalized_economic_proxy": True,
        "protected_bracket": {
            "enabled": protection.enabled,
            "policy": "E4_static_fill_activated_stop_target_timeout",
            "risk_scale": ("max_slow_ewma_price_sigma_prior_only_cusum_residual_scale"),
            "minute_precedence": (
                "gap_protection_then_eligible_order_then_intraminute_barriers"
            ),
            "same_bar_policy": "ambiguous_with_stop_first_execution",
            "unknown_source_path_policy": (
                "cancel_label_reconcile_flat_at_next_observed_open_and_invalidate_performance"
            ),
            "performance_path_valid": metrics["protected_performance_path_valid"],
        },
        "meta_filter": {
            "mode": meta_filter_mode,
            "status": (
                "disabled"
                if meta_filter_mode == "off"
                else "artifact_unavailable"
                if meta_artifact is None
                else "event_time_scored"
                if meta_scored_count > 0
                else "event_time_scores_unavailable"
            ),
            "policy_digest": meta_policy_digest,
            "historical_rescore_forbidden": True,
            "scoring_applied": meta_scored_count > 0,
        },
        "profitability_guaranteed": False,
        "instrument_costs_complete": False,
        "validation_warning": (
            "Current canonical files lack first-seen and revision timestamps. "
            "This is a causal current-revision replay, not an as-was-live "
            "backtest or a profitability guarantee. Futures multipliers, rolls, "
            "funding, borrow, spread history and market impact are not modeled."
        ),
    }
    return {
        "metadata": metadata,
        "config": {
            "strategy": strategy.as_dict(),
            "strategy_digest": strategy_digest,
            "costs": costs.as_dict(),
            "cost_digest": costs.digest(),
            "protected_bracket": protection.as_dict(timeframe=normalized_timeframe),
            "protected_bracket_digest": protection.digest(),
            "meta_filter": {
                "mode": meta_filter_mode,
                "artifact_status": (
                    "disabled"
                    if meta_filter_mode == "off"
                    else "not_configured"
                    if meta_artifact is None
                    else "loaded_compatible"
                ),
                "policy_digest": meta_policy_digest,
                "model_version": (
                    None if meta_artifact is None else meta_artifact.model_version
                ),
                "artifact_checksum": (
                    None if meta_artifact is None else meta_artifact.checksum
                ),
                "decision_threshold": (
                    None if meta_artifact is None else meta_artifact.decision_threshold
                ),
                "created_at": (
                    None if meta_artifact is None else _iso(meta_artifact.created_at)
                ),
                "trained_through": (
                    None
                    if meta_artifact is None
                    else _iso(meta_artifact.trained_through)
                ),
                "label_mature_through": (
                    None
                    if meta_artifact is None
                    else _iso(meta_artifact.label_mature_through)
                ),
                "entry_gate_rule": (
                    "strictly_above_max_model_and_static_stop_threshold_with_margin"
                ),
                "break_even_safety_margin": protection.break_even_safety_margin,
                "stored_event_time_scores_only": True,
            },
            "online_signal_config_digest": online_config.digest(),
        },
        "metrics": metrics,
        "equity": result["equity"],
        "drawdown": result["drawdown"],
        "position": result["position"],
        "risk_stop": result["risk_stop"],
        "risk_target": result["risk_target"],
        "meta_scores": list(meta_score_points),
        "meta_score_events": list(meta_score_events),
        "meta_label_book": meta_label_book,
        "markers": result["markers"],
        "fills": result["fills"],
        "barrier_plans": result["barrier_plans"],
        "barrier_evaluations": result["barrier_evaluations"],
        "signals": [_serialize_signal(signal) for signal in signals],
        "orders": [_serialize_order(order) for order in orders],
    }


class _ExecutionLedger:
    """Normalized one-minute mark-to-market and next-open fill ledger."""

    def __init__(
        self,
        *,
        costs: ReplayCostConfig,
        evaluation_start: datetime,
        display_stride_minutes: int,
        event_limit: int,
        capture_series: bool,
        protection: ProtectedReplayConfig | None = None,
        timeframe: str = "1m",
    ) -> None:
        self.costs = costs
        self.protection = protection or ProtectedReplayConfig()
        self.barrier_config = self.protection.barrier_config(timeframe)
        self.evaluation_start = evaluation_start
        self.display_stride_minutes = display_stride_minutes
        self.event_limit = event_limit
        self.capture_series = capture_series
        self.equity = costs.initial_equity
        self.gross_equity = costs.initial_equity
        self.peak = costs.initial_equity
        self.max_drawdown = 0.0
        self.position = 0.0
        self.previous_close: float | None = None
        self.first_minute: datetime | None = None
        self.last_minute: datetime | None = None
        self.evaluated_real_minutes = 0
        self.exposure_minutes = 0
        self.turnover = 0.0
        self.fee_paid = 0.0
        self.slippage_paid = 0.0
        self.spread_paid = 0.0
        self.fill_count = 0
        self.marker_count = 0
        self.fills: deque[dict[str, Any]] = deque(maxlen=event_limit)
        self.markers: deque[dict[str, Any]] = deque(maxlen=event_limit)
        self.equity_points: deque[dict[str, Any]] = deque(
            maxlen=MAX_CHART_SERIES_POINTS
        )
        self.drawdown_points: deque[dict[str, Any]] = deque(
            maxlen=MAX_CHART_SERIES_POINTS
        )
        self.position_points: deque[dict[str, Any]] = deque(
            maxlen=MAX_CHART_SERIES_POINTS
        )
        self.series_sample_count = 0
        self.last_series_epoch: int | None = None
        self.return_count = 0
        self.return_mean = 0.0
        self.return_m2 = 0.0
        self.entry_equity: float | None = None
        self.round_trip_count = 0
        self.round_trip_wins = 0
        self.ruined = False
        self.active_barrier: BarrierTracker | None = None
        self.requires_fresh_cusum_setup = False
        self.protected_entry_count = 0
        self.protected_stop_count = 0
        self.protected_target_count = 0
        self.protected_timeout_count = 0
        self.protected_ambiguous_count = 0
        self.protected_cancel_count = 0
        self.protected_unknown_path_gap_count = 0
        self.protected_performance_path_valid = True
        self.barrier_evaluations: deque[dict[str, Any]] = deque(maxlen=event_limit)
        self.barrier_plans: deque[dict[str, Any]] = deque(maxlen=event_limit)
        self.risk_stop_points: deque[dict[str, Any]] = deque(
            maxlen=MAX_CHART_SERIES_POINTS
        )
        self.risk_target_points: deque[dict[str, Any]] = deque(
            maxlen=MAX_CHART_SERIES_POINTS
        )

    def process_minute(
        self,
        *,
        row: dict[str, Any],
        pending_signal: dict[str, Any] | None,
        observed_at: datetime | str | None = None,
        unknown_path_gap_at: datetime | str | None = None,
    ) -> dict[str, Any] | None:
        timestamp = _utc(row["timestamp"])
        observed = (
            timestamp + timedelta(minutes=1)
            if observed_at is None
            else _utc(observed_at)
        )
        if observed < timestamp + timedelta(minutes=1):
            raise ValueError("observed_at predates finalized replay minute")
        open_value = float(row["open"])
        close_value = float(row["close"])
        start_equity = self.equity
        fill_happened = False
        minute_had_exposure = abs(self.position) > 1e-12
        self.first_minute = self.first_minute or timestamp
        self.last_minute = timestamp

        if self.previous_close is not None:
            self._mark(self.previous_close, open_value, self.position)

        if unknown_path_gap_at is not None and self.protection.enabled:
            gap_started_at = _utc(unknown_path_gap_at)
            if gap_started_at > timestamp:
                raise ValueError(
                    "unknown_path_gap_at must not follow the current minute"
                )
            if self.active_barrier is not None:
                self._reconcile_unknown_path_gap(
                    gap_started_at=gap_started_at,
                    observed_at=observed,
                    timestamp=timestamp,
                    reference_open=open_value,
                )
                fill_happened = True
                pending_signal = self._cancel_pending_after_barrier(
                    pending_signal,
                    timestamp=timestamp,
                )

        # A gap through an already-working protective order has precedence
        # over a strategy order that is also eligible at this minute open.
        gap_evaluation = (
            self._active_gap_evaluation(row, observed_at=observed)
            if self.protection.enabled
            else None
        )
        if gap_evaluation is not None:
            self._execute_barrier_exit(
                evaluation=gap_evaluation,
                timestamp=timestamp,
                reference_price=open_value,
            )
            fill_happened = True
            pending_signal = self._cancel_pending_after_barrier(
                pending_signal,
                timestamp=timestamp,
            )

        if (
            pending_signal is not None
            and _utc(pending_signal["eligible_at"]) <= timestamp
        ):
            if self.protection.enabled and self.active_barrier is not None:
                requested = float(pending_signal["desired_position"])
                if not math.isclose(requested, self.position, abs_tol=1e-12):
                    pending_signal["status"] = "suppressed_active_protected_bracket"
                    pending_signal["order_status"] = (
                        "suppressed_active_protected_bracket"
                    )
                    pending_signal = None
            if pending_signal is not None:
                target = float(pending_signal["desired_position"])
                if not math.isclose(target, self.position, abs_tol=1e-12):
                    target, next_plan = self._prepare_order_protection(
                        pending_signal=pending_signal,
                        timestamp=timestamp,
                        reference_open=open_value,
                        requested_target=target,
                    )
                    if target is not None and not math.isclose(
                        target, self.position, abs_tol=1e-12
                    ):
                        prior_position = self.position
                        self._cancel_active_for_strategy_fill(
                            target=target,
                            timestamp=timestamp,
                        )
                        fill = self._fill(
                            timestamp=timestamp,
                            open_value=open_value,
                            target=target,
                            signal=pending_signal,
                        )
                        fill_happened = True
                        minute_had_exposure = bool(
                            minute_had_exposure or abs(self.position) > 1e-12
                        )
                        if next_plan is not None:
                            self._activate_protection(
                                next_plan,
                                fill=fill,
                                timestamp=timestamp,
                            )
                        elif (
                            abs(prior_position) <= 1e-12
                            and abs(target) > 1e-12
                            and self.protection.enabled
                        ):
                            raise RuntimeError(
                                "Protected entry filled without an activated barrier"
                            )
            pending_signal = None

        intraminute_evaluation = (
            self.active_barrier.update(
                MinuteBar.from_mapping(row),
                observed_at=observed,
            )
            if self.protection.enabled and self.active_barrier is not None
            else None
        )
        if intraminute_evaluation is None:
            self._mark(open_value, close_value, self.position)
        elif intraminute_evaluation.primary_outcome is BarrierOutcome.TIMEOUT:
            # A vertical barrier is known at this finalized minute close.
            self._mark(open_value, close_value, self.position)
            self._execute_barrier_exit(
                evaluation=intraminute_evaluation,
                timestamp=timestamp + timedelta(minutes=1),
                reference_price=close_value,
            )
            fill_happened = True
            pending_signal = self._cancel_pending_after_barrier(
                pending_signal,
                timestamp=timestamp + timedelta(minutes=1),
            )
        else:
            assert intraminute_evaluation.exit_price is not None
            self._mark(open_value, intraminute_evaluation.exit_price, self.position)
            self._execute_barrier_exit(
                evaluation=intraminute_evaluation,
                timestamp=timestamp,
                reference_price=intraminute_evaluation.exit_price,
            )
            fill_happened = True
            pending_signal = self._cancel_pending_after_barrier(
                pending_signal,
                timestamp=timestamp,
            )
        self.previous_close = close_value
        self.evaluated_real_minutes += 1
        if (
            minute_had_exposure
            if self.protection.enabled
            else abs(self.position) > 1e-12
        ):
            self.exposure_minutes += 1
        minute_return = (
            (self.equity / start_equity) - 1.0 if start_equity > 0.0 else 0.0
        )
        self._update_return_stats(minute_return)
        self.peak = max(self.peak, self.equity)
        drawdown = 0.0 if self.peak <= 0.0 else (self.equity / self.peak) - 1.0
        self.max_drawdown = min(self.max_drawdown, drawdown)

        point_time = timestamp + timedelta(minutes=1)
        epoch_minute = int(point_time.timestamp()) // MINUTE_SECONDS
        if (
            fill_happened
            or self.evaluated_real_minutes == 1
            or epoch_minute % self.display_stride_minutes == 0
        ):
            self._append_point(point_time, drawdown)
        return pending_signal

    def _prepare_order_protection(
        self,
        *,
        pending_signal: dict[str, Any],
        timestamp: datetime,
        reference_open: float,
        requested_target: float,
    ) -> tuple[float | None, BarrierPlan | None]:
        if not self.protection.enabled:
            return requested_target, None
        opens_new = abs(requested_target) > 1e-12 and (
            abs(self.position) <= 1e-12
            or math.copysign(1.0, requested_target) != math.copysign(1.0, self.position)
        )
        if not opens_new:
            return requested_target, None
        risk_unit = _finite_float(pending_signal.get("protected_risk_unit"))
        if risk_unit is None or risk_unit <= 0.0:
            return self._reject_unprotected_entry(
                pending_signal,
                reason="protected_risk_unit_missing_at_fill",
            )
        order_delta = requested_target - self.position
        actual_fill = adverse_execution_price(
            reference_price=reference_open,
            order_delta=order_delta,
            costs=self.costs,
        )
        side = TradeSide.LONG if requested_target > 0.0 else TradeSide.SHORT
        try:
            plan = activate_barrier_plan(
                setup_id=str(pending_signal["signal_id"]),
                side=side,
                fill_price=actual_fill,
                risk_unit=risk_unit,
                activated_at=timestamp,
                config=self.barrier_config,
            )
        except (TypeError, ValueError):
            return self._reject_unprotected_entry(
                pending_signal,
                reason="protected_barrier_invalid_at_actual_fill",
            )
        return requested_target, plan

    def _reject_unprotected_entry(
        self,
        pending_signal: dict[str, Any],
        *,
        reason: str,
    ) -> tuple[float | None, None]:
        pending_signal["status"] = "cancelled_risk_plan"
        pending_signal["order_status"] = "cancelled_risk_plan"
        pending_signal["cancel_reason"] = reason
        signal_record = pending_signal.get("_signal_record")
        if isinstance(signal_record, dict):
            signal_record["order_status"] = "cancelled_risk_plan"
            signal_record["cancel_reason"] = reason
        # A failed reversal plan may still flatten the old protected position;
        # a flat account must never open without its mandatory bracket.
        return (0.0, None) if abs(self.position) > 1e-12 else (None, None)

    def _cancel_active_for_strategy_fill(
        self,
        *,
        target: float,
        timestamp: datetime,
    ) -> None:
        if self.active_barrier is None:
            return
        closes_old = abs(self.position) > 1e-12 and (
            abs(target) <= 1e-12
            or math.copysign(1.0, target) != math.copysign(1.0, self.position)
        )
        if closes_old:
            raise RuntimeError(
                "strategy fill attempted to override an immutable protected bracket"
            )

    def _activate_protection(
        self,
        plan: BarrierPlan,
        *,
        fill: dict[str, Any],
        timestamp: datetime,
    ) -> None:
        self.active_barrier = BarrierTracker(plan=plan)
        self.requires_fresh_cusum_setup = False
        self.protected_entry_count += 1
        plan_record = plan.as_dict()
        plan_record["plan_digest"] = plan.digest()
        self.barrier_plans.append(plan_record)
        fill["protected_bracket"] = plan_record
        self._append_risk_level(timestamp, plan)

    def _active_gap_evaluation(
        self,
        row: dict[str, Any],
        *,
        observed_at: datetime,
    ) -> BarrierEvaluation | None:
        tracker = self.active_barrier
        if tracker is None:
            return None
        plan = tracker.plan
        timestamp = _utc(row["timestamp"])
        open_value = float(row["open"])
        if plan.side is TradeSide.LONG:
            outcome = (
                BarrierOutcome.STOP
                if open_value <= plan.stop_price
                else BarrierOutcome.TARGET
                if open_value >= plan.target_price
                else None
            )
        else:
            outcome = (
                BarrierOutcome.STOP
                if open_value >= plan.stop_price
                else BarrierOutcome.TARGET
                if open_value <= plan.target_price
                else None
            )
        if outcome is None:
            return None
        observed_bars = tracker.observed_bars + 1
        evaluation = BarrierEvaluation(
            setup_id=plan.setup_id,
            plan_digest=plan.digest(),
            outcome=outcome,
            primary_outcome=outcome,
            optimistic_outcome=None,
            occurred_at=timestamp,
            label_known_at=observed_at,
            observed_bars=observed_bars,
            exit_price=open_value,
            optimistic_exit_price=None,
            gap_through=True,
            same_bar_ambiguous=False,
            optimistic_target_possible=False,
            default_binary_label=1 if outcome is BarrierOutcome.TARGET else 0,
            side_return_pct=(
                plan.side.multiplier * ((open_value / plan.fill_price) - 1.0) * 100.0
            ),
            reason=(
                "gap_through_target"
                if outcome is BarrierOutcome.TARGET
                else "gap_through_stop"
            ),
        )
        tracker.observed_bars = observed_bars
        tracker.last_timestamp = timestamp
        tracker.last_observation_at = observed_at
        tracker.terminal = evaluation
        return evaluation

    def _reconcile_unknown_path_gap(
        self,
        *,
        gap_started_at: datetime,
        observed_at: datetime,
        timestamp: datetime,
        reference_open: float,
    ) -> None:
        """Quarantine an active bracket whose path crossed missing source data.

        The position is flattened at the first later observed open so the
        replay cannot continue with an unprotected position.  The resulting
        equity path is explicitly invalid for performance evidence because an
        unseen stop or target may have executed inside the missing interval.
        """

        tracker = self.active_barrier
        if tracker is None:
            return
        plan = tracker.plan
        cancelled_at = max(gap_started_at, plan.activated_at)
        evaluation = cancel_barrier_plan(
            plan,
            cancelled_at=cancelled_at,
            observed_at=observed_at,
            reason="protected_market_data_gap_unknown_path",
            observed_bars=tracker.observed_bars,
        )
        self._record_barrier_evaluation(evaluation)
        self._end_risk_level(timestamp, plan)
        self.active_barrier = None
        self.protected_unknown_path_gap_count += 1
        self.protected_performance_path_valid = False
        reconciliation = {
            "order_id": _stable_digest(
                {
                    "plan_digest": plan.digest(),
                    "gap_started_at": _iso(cancelled_at),
                    "reconciled_at": _iso(timestamp),
                }
            ),
            "signal_id": plan.setup_id,
            "eligible_at": plan.activated_at,
            "reason": "protected_data_gap_reconciliation_flatten",
        }
        fill = self._fill(
            timestamp=timestamp,
            open_value=reference_open,
            target=0.0,
            signal=reconciliation,
        )
        fill["exit_reason"] = reconciliation["reason"]
        fill["barrier_evaluation"] = evaluation.as_dict()
        fill["barrier_plan_digest"] = plan.digest()
        fill["performance_path_valid"] = False

    def advance_protected_target_bar(
        self,
        *,
        bar: dict[str, Any],
        observed_at: datetime | str,
    ) -> BarrierEvaluation | None:
        """Apply an accepted finalized target candle to the vertical barrier."""

        if not self.protection.enabled or self.active_barrier is None:
            return None
        evaluation = self.active_barrier.advance_target_bar(
            bar_open=_utc(bar["timestamp"]),
            close_price=float(bar["close"]),
            observed_at=_utc(observed_at),
        )
        if evaluation is None:
            return None
        self._execute_barrier_exit(
            evaluation=evaluation,
            timestamp=evaluation.occurred_at,
            reference_price=float(bar["close"]),
        )
        return evaluation

    def _execute_barrier_exit(
        self,
        *,
        evaluation: BarrierEvaluation,
        timestamp: datetime,
        reference_price: float,
    ) -> None:
        if self.active_barrier is None:
            raise RuntimeError("Barrier exit has no active protected position")
        plan = self.active_barrier.plan
        exit_order_id = _stable_digest(
            {
                "plan_digest": plan.digest(),
                "evaluation_digest": evaluation.digest(),
                "exit_at": _iso(timestamp),
            }
        )
        exit_signal = {
            "order_id": exit_order_id,
            "signal_id": plan.setup_id,
            "eligible_at": plan.activated_at,
            "reason": f"protected_{evaluation.primary_outcome.value.lower()}",
        }
        fill = self._fill(
            timestamp=timestamp,
            open_value=reference_price,
            target=0.0,
            signal=exit_signal,
        )
        fill["exit_reason"] = exit_signal["reason"]
        fill["barrier_evaluation"] = evaluation.as_dict()
        fill["barrier_plan_digest"] = plan.digest()
        self._record_barrier_evaluation(evaluation)
        self._end_risk_level(timestamp, plan)
        self.active_barrier = None

    def _record_barrier_evaluation(self, evaluation: BarrierEvaluation) -> None:
        self.barrier_evaluations.append(evaluation.as_dict())
        self.requires_fresh_cusum_setup = True
        if evaluation.outcome is BarrierOutcome.STOP:
            self.protected_stop_count += 1
        elif evaluation.outcome is BarrierOutcome.TARGET:
            self.protected_target_count += 1
        elif evaluation.outcome is BarrierOutcome.TIMEOUT:
            self.protected_timeout_count += 1
        elif evaluation.outcome is BarrierOutcome.AMBIGUOUS:
            self.protected_ambiguous_count += 1
        elif evaluation.outcome is BarrierOutcome.CANCELLED:
            self.protected_cancel_count += 1

    def _cancel_active_barrier(self, *, timestamp: datetime, reason: str) -> None:
        if self.active_barrier is None:
            return
        plan = self.active_barrier.plan
        evaluation = cancel_barrier_plan(
            plan,
            cancelled_at=timestamp,
            reason=reason,
            observed_bars=self.active_barrier.observed_bars,
        )
        self._record_barrier_evaluation(evaluation)
        self._end_risk_level(timestamp, plan)
        self.active_barrier = None

    def _cancel_pending_after_barrier(
        self,
        pending_signal: dict[str, Any] | None,
        *,
        timestamp: datetime,
    ) -> None:
        if pending_signal is None:
            return None
        pending_signal["status"] = "cancelled_protective_exit"
        pending_signal["order_status"] = "cancelled_protective_exit"
        pending_signal["cancelled_at"] = timestamp
        signal_record = pending_signal.get("_signal_record")
        if isinstance(signal_record, dict):
            signal_record["order_status"] = "cancelled_protective_exit"
        return None

    def _append_risk_level(self, timestamp: datetime, plan: BarrierPlan) -> None:
        epoch = int(_utc(timestamp).timestamp())
        self._append_series_value(
            self.risk_stop_points,
            {"time": epoch, "value": plan.stop_price},
        )
        self._append_series_value(
            self.risk_target_points,
            {"time": epoch, "value": plan.target_price},
        )

    def _end_risk_level(self, timestamp: datetime, plan: BarrierPlan) -> None:
        self._append_risk_level(timestamp, plan)
        blank_epoch = int(_utc(timestamp).timestamp()) + MINUTE_SECONDS
        self._append_series_value(self.risk_stop_points, {"time": blank_epoch})
        self._append_series_value(self.risk_target_points, {"time": blank_epoch})

    @staticmethod
    def _append_series_value(
        series: deque[dict[str, Any]], point: dict[str, Any]
    ) -> None:
        if series and series[-1].get("time") == point.get("time"):
            series.pop()
        series.append(point)

    def _mark(self, start: float, end: float, position: float) -> None:
        if self.ruined or start <= 0.0 or end <= 0.0:
            return
        multiplier = 1.0 + position * ((end / start) - 1.0)
        if multiplier <= 0.0:
            self.equity = 0.0
            self.gross_equity = 0.0
            self.ruined = True
            return
        self.equity *= multiplier
        self.gross_equity *= multiplier

    def _fill(
        self,
        *,
        timestamp: datetime,
        open_value: float,
        target: float,
        signal: dict[str, Any],
    ) -> dict[str, Any]:
        old_position = self.position
        turnover = abs(target - old_position)
        equity_before_cost = self.equity
        cost_values = execution_costs(
            equity=equity_before_cost,
            turnover=turnover,
            costs=self.costs,
        )
        fee = cost_values["fee"]
        slippage = cost_values["slippage"]
        spread = cost_values["spread"]
        self.equity = max(0.0, self.equity - cost_values["total"])
        if self.equity <= 0.0:
            self.ruined = True
        self.turnover += turnover
        self.fee_paid += fee
        self.slippage_paid += slippage
        self.spread_paid += spread

        closes_old = abs(old_position) > 1e-12 and (
            abs(target) <= 1e-12
            or math.copysign(1.0, target) != math.copysign(1.0, old_position)
        )
        opens_new = abs(target) > 1e-12 and (
            abs(old_position) <= 1e-12
            or math.copysign(1.0, target) != math.copysign(1.0, old_position)
        )
        close_turnover = abs(old_position) if closes_old else 0.0
        close_cost_fraction = (
            0.0 if turnover <= 0.0 else min(1.0, close_turnover / turnover)
        )
        equity_after_close_cost = max(
            0.0,
            equity_before_cost - cost_values["total"] * close_cost_fraction,
        )
        if closes_old and self.entry_equity is not None and self.entry_equity > 0.0:
            round_trip_return = equity_after_close_cost / self.entry_equity - 1.0
            self.round_trip_count += 1
            self.round_trip_wins += int(round_trip_return > 0.0)
            self.entry_equity = None
        if opens_new:
            # On a reversal, closing costs belong to the completed trade and
            # the remaining equity is the pre-entry basis for the new trade.
            # From flat, this is simply equity before the opening transaction.
            self.entry_equity = (
                equity_after_close_cost if closes_old else equity_before_cost
            )

        order_delta = target - old_position
        adverse_price = adverse_execution_price(
            reference_price=open_value,
            order_delta=order_delta,
            costs=self.costs,
        )
        fill_minute_open = _iso(timestamp)
        fill_id = _stable_digest(
            {
                "execution_model_version": EXECUTION_MODEL_VERSION,
                "order_id": signal["order_id"],
                "fill_minute_open": fill_minute_open,
                "from_position": old_position,
                "to_position": target,
                "reference_open": open_value,
            }
        )
        fill = {
            "execution_model_version": EXECUTION_MODEL_VERSION,
            "fill_id": fill_id,
            "order_id": signal["order_id"],
            "order_status": "filled",
            "fill_status": "filled",
            "partial_fill": False,
            "time": int(timestamp.timestamp()),
            "timestamp": fill_minute_open,
            "fill_minute_open": fill_minute_open,
            "signal_id": signal["signal_id"],
            "eligible_at": _iso(_utc(signal["eligible_at"])),
            "from_position": old_position,
            "to_position": target,
            "turnover": turnover,
            "reference_open": open_value,
            "adverse_fill_price": adverse_price,
            "fee_paid": fee,
            "slippage_paid": slippage,
            "spread_paid": spread,
            "all_in_cost_paid": cost_values["total"],
            "equity_before_cost": equity_before_cost,
            "equity_after_cost": self.equity,
            "reason": signal["reason"],
        }
        signal["status"] = "filled"
        signal["order_status"] = "filled"
        signal["filled_at"] = timestamp
        signal["fill_id"] = fill_id
        signal_record = signal.get("_signal_record")
        if isinstance(signal_record, dict):
            signal_record["order_status"] = "filled"
            signal_record["fill_id"] = fill_id
            signal_record["filled_at"] = _iso(timestamp)
        self.fills.append(fill)
        self.fill_count += 1
        direction = 1 if target > old_position else -1
        self.markers.append(
            {
                "time": int(timestamp.timestamp()),
                "position": "belowBar" if direction > 0 else "aboveBar",
                "color": "#0f8b6d" if direction > 0 else "#c23b52",
                "shape": "arrowUp" if direction > 0 else "arrowDown",
                "text": f"Replay {old_position:.2f}->{target:.2f}",
            }
        )
        self.marker_count += 1
        self.position = target
        return fill

    def _update_return_stats(self, value: float) -> None:
        if not math.isfinite(value):
            return
        self.return_count += 1
        delta = value - self.return_mean
        self.return_mean += delta / self.return_count
        self.return_m2 += delta * (value - self.return_mean)

    def _append_point(self, timestamp: datetime, drawdown: float) -> None:
        epoch = int(timestamp.timestamp())
        replaces_last = self.last_series_epoch == epoch
        if not replaces_last:
            self.series_sample_count += 1
        self.last_series_epoch = epoch
        if not self.capture_series:
            return
        if replaces_last and self.equity_points:
            self.equity_points.pop()
            self.drawdown_points.pop()
            self.position_points.pop()
        self.equity_points.append({"time": epoch, "value": self.equity})
        self.drawdown_points.append({"time": epoch, "value": 100.0 * drawdown})
        self.position_points.append(
            {
                "time": epoch,
                "value": self.position,
                "color": (
                    "rgba(15,139,109,0.45)"
                    if self.position > 0.0
                    else "rgba(194,59,82,0.45)"
                    if self.position < 0.0
                    else "rgba(120,116,108,0.25)"
                ),
            }
        )
        if self.active_barrier is not None:
            self._append_risk_level(timestamp, self.active_barrier.plan)

    def finish(self) -> None:
        if self.last_minute is None:
            return
        point_time = self.last_minute + timedelta(minutes=1)
        drawdown = 0.0 if self.peak <= 0.0 else (self.equity / self.peak) - 1.0
        self._append_point(point_time, drawdown)

    def result(self) -> dict[str, Any]:
        duration_years = None
        if self.first_minute is not None and self.last_minute is not None:
            elapsed = (self.last_minute - self.first_minute).total_seconds()
            duration_years = elapsed / (365.25 * 24.0 * 60.0 * 60.0)
        sharpe = None
        if (
            self.return_count > 1
            and duration_years is not None
            and duration_years > 0.0
        ):
            variance = self.return_m2 / (self.return_count - 1)
            if variance > 0.0:
                observations_per_year = self.return_count / duration_years
                sharpe = (
                    self.return_mean
                    / math.sqrt(variance)
                    * math.sqrt(observations_per_year)
                )
        total_return = (self.equity / self.costs.initial_equity) - 1.0
        gross_return = (self.gross_equity / self.costs.initial_equity) - 1.0
        breakeven_cost_bps = (
            None if self.turnover <= 0.0 else 10_000.0 * gross_return / self.turnover
        )
        total_cost = self.fee_paid + self.slippage_paid + self.spread_paid
        metrics = {
            "initial_equity": self.costs.initial_equity,
            "final_equity": self.equity,
            "total_return_pct": 100.0 * total_return,
            "gross_total_return_pct": 100.0 * gross_return,
            "max_drawdown_pct": -100.0 * self.max_drawdown,
            "annualized_sharpe": sharpe,
            "fill_count": self.fill_count,
            "marker_count": self.marker_count,
            "round_trip_count": self.round_trip_count,
            "round_trip_win_rate_pct": (
                None
                if self.round_trip_count == 0
                else 100.0 * self.round_trip_wins / self.round_trip_count
            ),
            "turnover_notional": self.turnover,
            "fee_paid_equity": self.fee_paid,
            "slippage_paid_equity": self.slippage_paid,
            "spread_paid_equity": self.spread_paid,
            "total_cost_pct_of_initial": 100.0 * total_cost / self.costs.initial_equity,
            "breakeven_all_in_cost_bps": breakeven_cost_bps,
            "evaluated_real_minutes": self.evaluated_real_minutes,
            "exposure_minutes": self.exposure_minutes,
            "exposure_time_pct": (
                0.0
                if self.evaluated_real_minutes == 0
                else 100.0 * self.exposure_minutes / self.evaluated_real_minutes
            ),
            "open_position": self.position,
            "ruined": self.ruined,
            "protected_entry_count": self.protected_entry_count,
            "protected_stop_count": self.protected_stop_count,
            "protected_target_count": self.protected_target_count,
            "protected_timeout_count": self.protected_timeout_count,
            "protected_ambiguous_count": self.protected_ambiguous_count,
            "protected_cancel_count": self.protected_cancel_count,
            "protected_unknown_path_gap_count": (self.protected_unknown_path_gap_count),
            "protected_performance_path_valid": (self.protected_performance_path_valid),
            "protected_position_open": self.active_barrier is not None,
            "protected_waiting_fresh_setup": self.requires_fresh_cusum_setup,
        }
        return {
            "metrics": metrics,
            "equity": list(self.equity_points),
            "drawdown": list(self.drawdown_points),
            "position": list(self.position_points),
            "markers": list(self.markers),
            "fills": list(self.fills),
            "risk_stop": list(self.risk_stop_points),
            "risk_target": list(self.risk_target_points),
            "barrier_plans": list(self.barrier_plans),
            "barrier_evaluations": list(self.barrier_evaluations),
            "series_retention": {
                "captured": self.capture_series,
                "sampled_points": self.series_sample_count,
                "returned_points": len(self.equity_points),
                "truncated": self.series_sample_count > len(self.equity_points),
                "maximum_returned_points": MAX_CHART_SERIES_POINTS,
            },
        }


def _desired_position(
    *,
    online: dict[str, Any],
    cusum: dict[str, Any],
    strategy: IndicatorStrategyConfig,
) -> tuple[float, str]:
    if online.get("status") != "ok":
        return 0.0, f"flat_{online.get('status') or 'unavailable'}"
    trend_code = online.get("trend_state_code")
    if trend_code not in (-2, -1, 1, 2):
        return 0.0, "flat_no_directional_trend"
    if not strategy.trade_developing_trends and abs(int(trend_code)) != 2:
        return 0.0, "flat_developing_trend_disabled"
    path_quality = _finite_float(online.get("path_quality"))
    if path_quality is None or path_quality < strategy.minimum_path_quality:
        return 0.0, "flat_low_path_quality"
    direction = 1 if int(trend_code) > 0 else -1
    cusum_regime = cusum.get("regime")
    if strategy.require_cusum_agreement and cusum_regime != direction:
        return 0.0, "flat_cusum_disagreement"
    volatility_ratio = _finite_float(online.get("fast_slow_ratio"))
    if volatility_ratio is None or volatility_ratio <= 0.0:
        return 0.0, "flat_volatility_unavailable"
    if volatility_ratio > strategy.max_fast_slow_ratio:
        return 0.0, "flat_fast_volatility_gate"
    if strategy.enable_experimental_prototype_regime_gate and bool(
        online.get("regime_risk_active")
    ):
        return 0.0, "flat_prototype_change_risk"
    if strategy.require_regime_direction:
        expected_regime = 0 if direction > 0 else 1
        if online.get("regime_state") != expected_regime:
            return 0.0, "flat_prototype_direction_disagreement"
    volatility_scale = min(
        1.0,
        max(strategy.minimum_volatility_scale, 1.0 / max(volatility_ratio, 1.0)),
    )
    exposure = direction * strategy.maximum_exposure * volatility_scale
    exposure = round(exposure / strategy.position_step) * strategy.position_step
    exposure = min(max(exposure, -strategy.maximum_exposure), strategy.maximum_exposure)
    return (
        exposure,
        "long_indicator_agreement" if direction > 0 else "short_indicator_agreement",
    )


def _protected_risk_unit(
    *,
    close: float,
    online: dict[str, Any],
    cusum: dict[str, Any],
    protection: ProtectedReplayConfig,
) -> float | None:
    """Return a causal price risk unit known at the finalized signal bar.

    The first protected experiment uses the wider of slow close-to-close EWMA
    volatility and the prior-only CUSUM residual scale.  It is intentionally a
    small, versioned research primitive rather than an instrument contract or
    a claim that one multiplier is optimal for every market.
    """

    if not protection.enabled:
        return None
    close_value = _finite_float(close)
    slow_volatility_pct = _finite_float(online.get("ewma_vol_slow_pct"))
    residual_scale = _finite_float(cusum.get("res_std"))
    candidates: list[float] = []
    if (
        close_value is not None
        and close_value > 0.0
        and slow_volatility_pct is not None
        and slow_volatility_pct > 0.0
    ):
        candidates.append(close_value * slow_volatility_pct / 100.0)
    if residual_scale is not None and residual_scale > 0.0:
        candidates.append(residual_scale)
    if not candidates:
        return None
    risk_unit = protection.risk_unit_volatility_multiplier * max(candidates)
    return risk_unit if math.isfinite(risk_unit) and risk_unit > 0.0 else None


def _normalized_minute_frame(frame: pl.DataFrame) -> pl.DataFrame:
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(
            "Minute replay frame is missing required columns: "
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
        pl.col(name)
        for name in (
            "calendar_id",
            "is_synthetic_no_trade",
            "is_session_open_bar",
        )
        if name in frame.columns
    )
    return (
        frame.select(expressions)
        .filter(pl.col("timestamp").is_not_null())
        .unique(subset=["timestamp"], keep="last")
        .sort("timestamp")
    )


def _valid_ohlcv_row(row: dict[str, Any]) -> bool:
    open_value = _finite_float(row.get("open"))
    high = _finite_float(row.get("high"))
    low = _finite_float(row.get("low"))
    close = _finite_float(row.get("close"))
    if any(value is None or value <= 0.0 for value in (open_value, high, low, close)):
        return False
    assert (
        open_value is not None
        and high is not None
        and low is not None
        and close is not None
    )
    return high >= max(open_value, close) and low <= min(open_value, close)


def _serialize_signal(signal: dict[str, Any]) -> dict[str, Any]:
    return {
        **signal,
        "eligible_at": _iso(signal["eligible_at"]),
    }


def _serialize_order(order: dict[str, Any]) -> dict[str, Any]:
    serialized = {key: value for key, value in order.items() if not key.startswith("_")}
    for name in (
        "created_at",
        "scheduled_close",
        "observed_at",
        "eligible_at",
        "filled_at",
        "cancelled_at",
    ):
        value = serialized.get(name)
        if isinstance(value, datetime):
            serialized[name] = _iso(value)
    return serialized


def _bucket_start(timestamp: datetime, interval_seconds: int) -> datetime:
    epoch = int(_utc(timestamp).timestamp())
    return datetime.fromtimestamp(
        (epoch // interval_seconds) * interval_seconds,
        tz=timezone.utc,
    )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _finite_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _finite_or_zero(value: Any) -> float:
    parsed = _finite_float(value)
    return 0.0 if parsed is None else parsed


def _relative_source_path(path: Path) -> str:
    try:
        return str(path.relative_to(Path(__file__).resolve().parent.parent))
    except ValueError:
        return str(path)
