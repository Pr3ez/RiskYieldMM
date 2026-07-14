"""Restart-safe, forward-only paper execution over first-seen finalized minutes.

The stream intentionally keeps market-data observation time separate from bar
time.  A target candle can only create a paper order after the candle's
scheduled close *and* after the finalized source minute was first observed.
The order is then eligible on a later whole-minute open.  Historical bootstrap
and catch-up modes warm indicator state, but never invent fills or orders.

All prices and PnL are normalized proxies.  Instrument multipliers, funding,
borrow, rolls, spread history, and market impact are outside this component.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from chart_config import (
    BYBIT_ASSETS,
    CANONICAL_TIMEFRAMES,
    normalize_asset,
    normalize_timeframe,
    timeframe_seconds,
)
from indicators import CusumTrendEngine
from minute_replay import (
    EXECUTION_MODEL_VERSION,
    SESSION_GAP_TOLERANCE_SECONDS,
    CausalCandleBuilder,
    IndicatorStrategyConfig,
    ProtectedReplayConfig,
    ReplayCostConfig,
    _decision_static_stop_break_even_probability,
    _desired_position,
    _estimated_roundtrip_cost_bps,
    _protected_risk_unit,
    adverse_execution_price,
    execution_costs,
    execution_eligible_at,
    meta_label_policy_digest,
    target_bar_is_complete,
)
from online_signals import OnlineSignalConfig, OnlineSignalEngine
from trade_ml.artifact import LogisticCoefficientArtifact, digest_feature_schema
from trade_ml.contracts import TradeSide
from trade_ml.features import META_FEATURE_NAMES, build_feature_snapshot
from trade_ml.inference import InferenceResult, score_features
from trade_ml.shadow import (
    ShadowCandidate,
    ShadowEventBook,
    ShadowEventRecord,
    ShadowEventState,
    ShadowExecutionMinute,
    ShadowGapPolicy,
)

FORWARD_PAPER_STREAM_VERSION = "forward_paper_stream_v3"
PAPER_LEDGER_VERSION = "normalized_paper_ledger_v2"
PAPER_EVENT_VERSION = "paper_event_v2"
PAPER_ORDER_SCHEMA_VERSION = "paper_order_v2"
PAPER_FILL_SCHEMA_VERSION = "paper_fill_v2"
META_SHADOW_MODE = "shadow_only_no_order_effect"
META_SHADOW_MAX_OPEN_EVENTS = 10_000
META_SHADOW_MAX_RESOLVED_RECORDS = 10_000
META_SHADOW_FAILURE_PHASES = frozenset(
    (
        "accepted_target_bar_advance",
        "candidate_score_and_schedule",
        "execution_minute_update",
    )
)

StreamMode = Literal["bootstrap", "catchup", "forward"]
_STREAM_MODES = frozenset(("bootstrap", "catchup", "forward"))


class ForwardPaperStateError(ValueError):
    """Raised when persisted paper state is invalid or incompatible."""


@dataclass(frozen=True)
class _MinuteCursor:
    timestamp: datetime
    fingerprint: str
    observed_at: datetime


class NormalizedPaperLedger:
    """Normalized one-minute mark-to-market ledger with explicit costs."""

    def __init__(self, costs: ReplayCostConfig) -> None:
        self.costs = costs
        self.equity = float(costs.initial_equity)
        self.gross_equity = float(costs.initial_equity)
        self.peak_equity = float(costs.initial_equity)
        self.max_drawdown = 0.0
        self.position = 0.0
        self.previous_close: float | None = None
        self.last_minute: datetime | None = None
        self.real_minutes_marked = 0
        self.forward_minutes_marked = 0
        self.exposure_minutes = 0
        self.suppressed_minutes = 0
        self.fill_count = 0
        self.turnover = 0.0
        self.fee_paid = 0.0
        self.slippage_paid = 0.0
        self.spread_paid = 0.0
        self.first_forward_minute: datetime | None = None
        self.last_forward_minute: datetime | None = None
        self.return_count = 0
        self.return_mean = 0.0
        self.return_m2 = 0.0
        self.entry_equity: float | None = None
        self.round_trip_count = 0
        self.round_trip_wins = 0
        self.ruined = False

    def process_real_minute(
        self,
        *,
        row: dict[str, Any],
        observed_at: datetime,
        pending_order: dict[str, Any] | None,
        allow_fill: bool = True,
        forward_evidence: bool = True,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any]]:
        """Mark one real minute, filling only an already-eligible order."""

        if not isinstance(allow_fill, bool) or not isinstance(forward_evidence, bool):
            raise ValueError("allow_fill and forward_evidence must be bools")
        timestamp = _utc(row["timestamp"])
        if self.last_minute is not None and timestamp <= self.last_minute:
            raise ForwardPaperStateError("Paper ledger minutes must be chronological")
        open_value = _positive_finite(row.get("open"), field="open")
        close_value = _positive_finite(row.get("close"), field="close")
        start_equity = self.equity
        old_position = self.position

        if self.previous_close is not None:
            self._mark_price(self.previous_close, open_value, self.position)

        fill: dict[str, Any] | None = None
        if pending_order is not None and allow_fill:
            eligible_at = _parse_utc(pending_order.get("eligible_at"), "eligible_at")
            if eligible_at <= timestamp:
                target = _bounded_position(pending_order.get("desired_position"))
                if not math.isclose(target, self.position, abs_tol=1e-12):
                    fill = self._fill(
                        timestamp=timestamp,
                        observed_at=observed_at,
                        reference_open=open_value,
                        target=target,
                        order=pending_order,
                    )
                pending_order = None

        self._mark_price(open_value, close_value, self.position)
        self.previous_close = close_value
        self.last_minute = timestamp
        self.real_minutes_marked += 1
        if forward_evidence:
            self.first_forward_minute = self.first_forward_minute or timestamp
            self.last_forward_minute = timestamp
            self.forward_minutes_marked += 1
            if abs(self.position) > 1e-12:
                self.exposure_minutes += 1
        self.peak_equity = max(self.peak_equity, self.equity)
        drawdown = (
            0.0 if self.peak_equity <= 0.0 else (self.equity / self.peak_equity) - 1.0
        )
        self.max_drawdown = min(self.max_drawdown, drawdown)
        minute_return = (
            0.0 if start_equity <= 0.0 else (self.equity / start_equity) - 1.0
        )
        if forward_evidence:
            self._update_return_stats(minute_return)
        mark = {
            "minute_open": _iso(timestamp),
            "marked_at": _iso(timestamp + timedelta(minutes=1)),
            "observed_at": _iso(observed_at),
            "open": open_value,
            "close": close_value,
            "position_before_open": old_position,
            "position": self.position,
            "minute_return": minute_return,
            "equity": self.equity,
            "gross_equity": self.gross_equity,
            "peak_equity": self.peak_equity,
            "drawdown": drawdown,
            "max_drawdown": self.max_drawdown,
            "turnover": self.turnover,
            "fee_paid": self.fee_paid,
            "slippage_paid": self.slippage_paid,
            "spread_paid": self.spread_paid,
            "forward_evidence": forward_evidence,
            "ruined": self.ruined,
        }
        return pending_order, fill, mark

    def suppress_minute(self, row: dict[str, Any]) -> None:
        """Advance the price anchor without simulating historical PnL."""

        timestamp = _utc(row["timestamp"])
        close_value = _positive_finite(row.get("close"), field="close")
        self.previous_close = close_value
        self.last_minute = timestamp
        self.suppressed_minutes += 1

    def _mark_price(self, start: float, end: float, position: float) -> None:
        if self.ruined:
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
        observed_at: datetime,
        reference_open: float,
        target: float,
        order: dict[str, Any],
    ) -> dict[str, Any]:
        old_position = self.position
        delta = target - old_position
        turnover = abs(delta)
        equity_before_cost = self.equity
        costs = execution_costs(
            equity=equity_before_cost,
            turnover=turnover,
            costs=self.costs,
        )
        fee = costs["fee"]
        slippage = costs["slippage"]
        spread = costs["spread"]
        adverse_price = adverse_execution_price(
            reference_price=reference_open,
            order_delta=delta,
            costs=self.costs,
        )
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
            equity_before_cost - costs["total"] * close_cost_fraction,
        )
        if closes_old and self.entry_equity is not None and self.entry_equity > 0.0:
            round_trip_return = equity_after_close_cost / self.entry_equity - 1.0
            self.round_trip_count += 1
            self.round_trip_wins += int(round_trip_return > 0.0)
            self.entry_equity = None
        if opens_new:
            self.entry_equity = (
                equity_after_close_cost if closes_old else equity_before_cost
            )
        self.equity = max(0.0, self.equity - costs["total"])
        if self.equity <= 0.0:
            self.ruined = True
        self.position = target
        self.fill_count += 1
        self.turnover += turnover
        self.fee_paid += fee
        self.slippage_paid += slippage
        self.spread_paid += spread
        fill_minute_open = _iso(timestamp)
        fill_id = _digest(
            {
                "execution_model_version": EXECUTION_MODEL_VERSION,
                "order_id": order["order_id"],
                "fill_minute_open": fill_minute_open,
                "from_position": old_position,
                "to_position": target,
                "reference_open": reference_open,
            },
            length=24,
        )
        return {
            "fill_schema_version": PAPER_FILL_SCHEMA_VERSION,
            "fill_id": fill_id,
            "order_id": order["order_id"],
            "order_schema_version": order["order_schema_version"],
            "order_status": "filled",
            "fill_status": "filled",
            "partial_fill": False,
            "signal_id": order["signal_id"],
            "signal_observed_at": order["observed_at"],
            "eligible_at": order["eligible_at"],
            "fill_minute_open": fill_minute_open,
            "observed_at": _iso(observed_at),
            "from_position": old_position,
            "to_position": target,
            "turnover": turnover,
            "reference_open": reference_open,
            "adverse_fill_price": adverse_price,
            "fee_paid": fee,
            "slippage_paid": slippage,
            "spread_paid": spread,
            "all_in_cost_paid": costs["total"],
            "equity_before_cost": equity_before_cost,
            "equity_after_cost": self.equity,
            "reason": order["reason"],
        }

    def _update_return_stats(self, value: float) -> None:
        if not math.isfinite(value):
            return
        self.return_count += 1
        delta = value - self.return_mean
        self.return_mean += delta / self.return_count
        self.return_m2 += delta * (value - self.return_mean)

    def metrics(self) -> dict[str, Any]:
        """Return the shared replay/paper metric contract plus legacy aliases."""

        initial = self.costs.initial_equity
        duration_years = None
        if (
            self.first_forward_minute is not None
            and self.last_forward_minute is not None
        ):
            elapsed = (
                self.last_forward_minute - self.first_forward_minute
            ).total_seconds()
            duration_years = elapsed / (365.25 * 24.0 * 60.0 * 60.0)
        sharpe = None
        if self.return_count > 1 and duration_years and duration_years > 0.0:
            variance = self.return_m2 / (self.return_count - 1)
            if variance > 0.0:
                observations_per_year = self.return_count / duration_years
                sharpe = (
                    self.return_mean
                    / math.sqrt(variance)
                    * math.sqrt(observations_per_year)
                )
        total_return = self.equity / initial - 1.0
        gross_return = self.gross_equity / initial - 1.0
        total_cost = self.fee_paid + self.slippage_paid + self.spread_paid
        exposure_time_pct = (
            0.0
            if self.forward_minutes_marked == 0
            else 100.0 * self.exposure_minutes / self.forward_minutes_marked
        )
        shared = {
            "initial_equity": initial,
            "final_equity": self.equity,
            "total_return_pct": 100.0 * total_return,
            "gross_total_return_pct": 100.0 * gross_return,
            "max_drawdown_pct": -100.0 * self.max_drawdown,
            "annualized_sharpe": sharpe,
            "fill_count": self.fill_count,
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
            "total_cost_pct_of_initial": 100.0 * total_cost / initial,
            "breakeven_all_in_cost_bps": (
                None
                if self.turnover <= 0.0
                else 10_000.0 * gross_return / self.turnover
            ),
            "evaluated_real_minutes": self.forward_minutes_marked,
            "exposure_minutes": self.exposure_minutes,
            "exposure_time_pct": exposure_time_pct,
            "open_position": self.position,
            "ruined": self.ruined,
        }
        return {
            **shared,
            "current_position": self.position,
            "turnover": self.turnover,
            "fee_paid_pct_of_initial": self.fee_paid / initial * 100.0,
            "slippage_paid_pct_of_initial": self.slippage_paid / initial * 100.0,
            "spread_paid_pct_of_initial": self.spread_paid / initial * 100.0,
            "real_minutes_marked": self.real_minutes_marked,
            "forward_minutes_marked": self.forward_minutes_marked,
            "suppressed_catchup_minutes": self.suppressed_minutes,
        }

    def snapshot(self) -> dict[str, Any]:
        payload = {
            "algorithm_version": PAPER_LEDGER_VERSION,
            "costs": self.costs.as_dict(),
            "cost_digest": self.costs.digest(),
            "equity": self.equity,
            "gross_equity": self.gross_equity,
            "peak_equity": self.peak_equity,
            "max_drawdown": self.max_drawdown,
            "position": self.position,
            "previous_close": self.previous_close,
            "last_minute": _iso_or_none(self.last_minute),
            "real_minutes_marked": self.real_minutes_marked,
            "forward_minutes_marked": self.forward_minutes_marked,
            "exposure_minutes": self.exposure_minutes,
            "suppressed_minutes": self.suppressed_minutes,
            "fill_count": self.fill_count,
            "turnover": self.turnover,
            "fee_paid": self.fee_paid,
            "slippage_paid": self.slippage_paid,
            "spread_paid": self.spread_paid,
            "first_forward_minute": _iso_or_none(self.first_forward_minute),
            "last_forward_minute": _iso_or_none(self.last_forward_minute),
            "return_count": self.return_count,
            "return_mean": self.return_mean,
            "return_m2": self.return_m2,
            "entry_equity": self.entry_equity,
            "round_trip_count": self.round_trip_count,
            "round_trip_wins": self.round_trip_wins,
            "ruined": self.ruined,
        }
        return _with_checksum(payload)

    @classmethod
    def restore(
        cls,
        snapshot: dict[str, Any],
        *,
        expected_costs: ReplayCostConfig | None = None,
    ) -> NormalizedPaperLedger:
        raw = _validated_snapshot(snapshot, name="paper ledger")
        if raw.get("algorithm_version") != PAPER_LEDGER_VERSION:
            raise ForwardPaperStateError("Paper ledger version mismatch")
        costs = _restore_costs(raw.get("costs"))
        if raw.get("cost_digest") != costs.digest():
            raise ForwardPaperStateError("Paper ledger cost digest mismatch")
        if expected_costs is not None and costs != expected_costs:
            raise ForwardPaperStateError("Paper ledger costs do not match stream")
        ledger = cls(costs)
        ledger.equity = _nonnegative_finite(raw.get("equity"), "equity")
        ledger.gross_equity = _nonnegative_finite(
            raw.get("gross_equity"), "gross equity"
        )
        ledger.peak_equity = _positive_finite(
            raw.get("peak_equity"), field="peak equity"
        )
        ledger.max_drawdown = _finite(raw.get("max_drawdown"), "max drawdown")
        if not -1.0 <= ledger.max_drawdown <= 0.0:
            raise ForwardPaperStateError("Paper ledger max drawdown is invalid")
        ledger.position = _bounded_position(raw.get("position"))
        previous_close = raw.get("previous_close")
        ledger.previous_close = (
            None
            if previous_close is None
            else _positive_finite(previous_close, field="previous close")
        )
        ledger.last_minute = _optional_utc(raw.get("last_minute"), "last minute")
        ledger.real_minutes_marked = _nonnegative_int(
            raw.get("real_minutes_marked"), "real minute count"
        )
        ledger.forward_minutes_marked = _nonnegative_int(
            raw.get("forward_minutes_marked"), "forward minute count"
        )
        ledger.exposure_minutes = _nonnegative_int(
            raw.get("exposure_minutes"), "exposure minute count"
        )
        ledger.suppressed_minutes = _nonnegative_int(
            raw.get("suppressed_minutes"), "suppressed minute count"
        )
        ledger.fill_count = _nonnegative_int(raw.get("fill_count"), "fill count")
        ledger.turnover = _nonnegative_finite(raw.get("turnover"), "turnover")
        ledger.fee_paid = _nonnegative_finite(raw.get("fee_paid"), "fee paid")
        ledger.slippage_paid = _nonnegative_finite(
            raw.get("slippage_paid"), "slippage paid"
        )
        ledger.spread_paid = _nonnegative_finite(raw.get("spread_paid"), "spread paid")
        ledger.first_forward_minute = _optional_utc(
            raw.get("first_forward_minute"), "first forward minute"
        )
        ledger.last_forward_minute = _optional_utc(
            raw.get("last_forward_minute"), "last forward minute"
        )
        ledger.return_count = _nonnegative_int(raw.get("return_count"), "return count")
        ledger.return_mean = _finite(raw.get("return_mean"), "return mean")
        ledger.return_m2 = _nonnegative_finite(raw.get("return_m2"), "return m2")
        entry_equity = raw.get("entry_equity")
        ledger.entry_equity = (
            None
            if entry_equity is None
            else _nonnegative_finite(entry_equity, "entry equity")
        )
        ledger.round_trip_count = _nonnegative_int(
            raw.get("round_trip_count"), "round-trip count"
        )
        ledger.round_trip_wins = _nonnegative_int(
            raw.get("round_trip_wins"), "round-trip wins"
        )
        ruined = raw.get("ruined")
        if not isinstance(ruined, bool):
            raise ForwardPaperStateError("Paper ledger ruined flag is invalid")
        ledger.ruined = ruined
        if ledger.equity > ledger.peak_equity * (1.0 + 1e-12):
            raise ForwardPaperStateError("Paper ledger peak equity is inconsistent")
        if ledger.forward_minutes_marked > ledger.real_minutes_marked:
            raise ForwardPaperStateError("Paper ledger forward minute count is invalid")
        if ledger.exposure_minutes > ledger.forward_minutes_marked:
            raise ForwardPaperStateError("Paper ledger exposure count is invalid")
        if ledger.round_trip_wins > ledger.round_trip_count:
            raise ForwardPaperStateError("Paper ledger round-trip count is invalid")
        if (ledger.first_forward_minute is None) != (
            ledger.last_forward_minute is None
        ) or (ledger.forward_minutes_marked == 0) != (
            ledger.first_forward_minute is None
        ):
            raise ForwardPaperStateError("Paper ledger forward timing is invalid")
        return ledger


class ForwardPaperStream:
    """One deterministic first-seen paper stream for one asset/timeframe."""

    def __init__(
        self,
        *,
        asset: str,
        timeframe: str,
        strategy: IndicatorStrategyConfig | None = None,
        costs: ReplayCostConfig | None = None,
        meta_shadow_protection: ProtectedReplayConfig | None = None,
        meta_artifact: LogisticCoefficientArtifact | None = None,
        meta_artifact_reason: str = "artifact_not_configured",
    ) -> None:
        self.asset = normalize_asset(asset)
        self.timeframe = normalize_timeframe(timeframe)
        if self.timeframe not in CANONICAL_TIMEFRAMES:
            allowed = ", ".join(CANONICAL_TIMEFRAMES)
            raise ValueError(f"Paper timeframe must be canonical: {allowed}")
        self.interval_seconds = timeframe_seconds(self.timeframe)
        self.strategy = strategy or IndicatorStrategyConfig()
        # A one-minute default prevents a finalized REST bar from filling at
        # the already-passed open of the same minute.
        self.costs = costs or ReplayCostConfig(execution_latency_minutes=1)
        self.online_config = OnlineSignalConfig(
            horizons=self.strategy.horizons,
            trend_z_clip=self.strategy.trend_z_clip,
            aligned_score=self.strategy.aligned_score,
            aligned_quality=self.strategy.aligned_quality,
            developing_score=self.strategy.developing_score,
            change_risk_threshold=self.strategy.change_risk_threshold,
            expected_interval_seconds=self.interval_seconds,
            max_gap_seconds=(
                self.interval_seconds
                if self.asset in BYBIT_ASSETS
                else max(self.interval_seconds, SESSION_GAP_TOLERANCE_SECONDS)
            ),
        )
        self.online_engine = OnlineSignalEngine(self.online_config)
        self.cusum_engine = CusumTrendEngine(self.strategy.cusum_sensitivity)
        self.builder = CausalCandleBuilder(self.timeframe)
        self.ledger = NormalizedPaperLedger(self.costs)
        if meta_shadow_protection is not None and not isinstance(
            meta_shadow_protection, ProtectedReplayConfig
        ):
            raise TypeError(
                "meta_shadow_protection must be a ProtectedReplayConfig or None"
            )
        if meta_shadow_protection is not None and not meta_shadow_protection.enabled:
            raise ValueError("Meta shadow protection must be enabled")
        if meta_artifact is not None and not isinstance(
            meta_artifact, LogisticCoefficientArtifact
        ):
            raise TypeError("meta_artifact must be a LogisticCoefficientArtifact")
        if meta_artifact is not None and meta_shadow_protection is None:
            raise ValueError("meta_artifact requires enabled meta shadow protection")
        artifact_reason = str(meta_artifact_reason).strip()
        if not artifact_reason:
            raise ValueError("meta_artifact_reason cannot be empty")
        self.meta_shadow_protection = meta_shadow_protection
        self.meta_artifact = meta_artifact
        self.meta_artifact_reason = (
            "ok" if meta_artifact is not None else artifact_reason
        )
        self.meta_shadow_enabled = meta_shadow_protection is not None
        self.meta_shadow_policy_digest = (
            meta_label_policy_digest(
                strategy=self.strategy,
                costs=self.costs,
                protection=meta_shadow_protection,
                timeframe=self.timeframe,
            )
            if meta_shadow_protection is not None
            else None
        )
        self.meta_shadow_book = (
            ShadowEventBook(
                max_open_events=META_SHADOW_MAX_OPEN_EVENTS,
                max_resolved_records=META_SHADOW_MAX_RESOLVED_RECORDS,
            )
            if self.meta_shadow_enabled
            else None
        )
        self.pending_order: dict[str, Any] | None = None
        self.cursor: _MinuteCursor | None = None
        self.clean_start_at: datetime | None = None
        self.bootstrap_target_bar_count = 0
        self.bootstrap_target_through: datetime | None = None
        self.source_gap_count = 0
        self.rejected_incomplete_target_count = 0
        self.accepted_partial_session_target_count = 0
        self.meta_shadow_failure_count = 0
        self.last_meta_shadow_failure: dict[str, Any] | None = None
        self.stream_id = _digest(
            {
                "algorithm_version": FORWARD_PAPER_STREAM_VERSION,
                "asset": self.asset,
                "timeframe": self.timeframe,
                "strategy_digest": self.strategy.digest(),
                "cost_digest": self.costs.digest(),
            },
            length=24,
        )

    def bootstrap_target_bars(self, rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
        """Warm both indicators directly from finalized target candles.

        This path intentionally bypasses the one-minute candle builder so a
        12h/1d stream can be warmed without replaying a huge minute history.
        Minute ingestion may start only at or after the next clean UTC target
        boundary.
        """

        if self.builder.bucket_end is not None or self.cursor is not None:
            raise ForwardPaperStateError(
                "Target-bar bootstrap must run before minute ingestion"
            )
        if self.pending_order is not None or self.ledger.fill_count:
            raise ForwardPaperStateError("Cannot bootstrap a traded paper stream")
        last_timestamp = self.bootstrap_target_through
        added = 0
        skipped_synthetic = 0
        for raw_row in rows:
            row = _normalized_ohlcv_row(raw_row)
            if bool(row.get("is_synthetic_no_trade", False)):
                skipped_synthetic += 1
                continue
            timestamp = row["timestamp"]
            if _bucket_start(timestamp, self.interval_seconds) != timestamp:
                raise ValueError("Bootstrap target candle is not UTC bucket-aligned")
            if last_timestamp is not None and timestamp <= last_timestamp:
                raise ValueError("Bootstrap target candles must be chronological")
            self.online_engine.update(
                timestamp=timestamp,
                open_value=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row["volume"],
                is_final=True,
                scheduled_gap=bool(row.get("is_session_open_bar", False)),
            )
            self.cusum_engine.update(timestamp=timestamp, close=row["close"])
            last_timestamp = timestamp
            added += 1
        if added:
            assert last_timestamp is not None
            self.bootstrap_target_bar_count += added
            self.bootstrap_target_through = last_timestamp
            self.clean_start_at = last_timestamp + timedelta(
                seconds=self.interval_seconds
            )
        return {
            "stream_id": self.stream_id,
            "added_target_bars": added,
            "skipped_synthetic_target_bars": skipped_synthetic,
            "total_target_bars": self.bootstrap_target_bar_count,
            "bootstrap_target_through": _iso_or_none(self.bootstrap_target_through),
            "minute_ingestion_from": _iso_or_none(self.clean_start_at),
            "builder_empty": self.builder.bucket_end is None,
            "signals_created": 0,
            "fills_created": 0,
        }

    def consume(
        self,
        row: dict[str, Any],
        *,
        observed_at: datetime | str,
        mode: StreamMode = "forward",
    ) -> list[dict[str, Any]]:
        """Consume one finalized first-seen real minute in chronological order."""

        if mode not in _STREAM_MODES:
            raise ValueError("mode must be bootstrap, catchup, or forward")
        normalized = _normalized_ohlcv_row(row)
        timestamp = normalized["timestamp"]
        observed = _parse_utc(observed_at, "observed_at")
        minute_end = timestamp + timedelta(minutes=1)
        if observed < minute_end:
            raise ValueError("observed_at predates finalization of the one-minute bar")
        fingerprint = _minute_fingerprint(normalized)

        if self.cursor is not None and timestamp == self.cursor.timestamp:
            if fingerprint == self.cursor.fingerprint:
                return []
            return [
                self._incident(
                    incident_type="source_revision",
                    timestamp=timestamp,
                    observed_at=observed,
                    received_fingerprint=fingerprint,
                    retained_fingerprint=self.cursor.fingerprint,
                    retained_observed_at=_iso(self.cursor.observed_at),
                )
            ]
        if self.cursor is not None and timestamp < self.cursor.timestamp:
            return [
                self._incident(
                    incident_type="late_row",
                    timestamp=timestamp,
                    observed_at=observed,
                    received_fingerprint=fingerprint,
                    retained_cursor=_iso(self.cursor.timestamp),
                )
            ]
        if bool(normalized.get("is_synthetic_no_trade", False)):
            return [
                self._incident(
                    incident_type="synthetic_row_rejected",
                    timestamp=timestamp,
                    observed_at=observed,
                    received_fingerprint=fingerprint,
                )
            ]

        if self.clean_start_at is not None:
            if timestamp < self.clean_start_at:
                bootstrap_floor = (
                    None
                    if self.bootstrap_target_through is None
                    else self.bootstrap_target_through
                    + timedelta(seconds=self.interval_seconds)
                )
                if bootstrap_floor is not None and timestamp >= bootstrap_floor:
                    # The source began inside the target bucket.  Keep the
                    # first-seen cursor/price anchor current, but do not build
                    # a partial candle or repeatedly journal an incident while
                    # waiting for the already-recorded clean boundary.
                    self.cursor = _MinuteCursor(timestamp, fingerprint, observed)
                    self.ledger.suppress_minute(normalized)
                    return []
                return [
                    self._incident(
                        incident_type="bootstrap_overlap_ignored",
                        timestamp=timestamp,
                        observed_at=observed,
                        received_fingerprint=fingerprint,
                        minute_ingestion_from=_iso(self.clean_start_at),
                    )
                ]
            if _bucket_start(timestamp, self.interval_seconds) != timestamp:
                self.cursor = _MinuteCursor(timestamp, fingerprint, observed)
                self.clean_start_at = _next_bucket_start(
                    timestamp, self.interval_seconds
                )
                self.ledger.suppress_minute(normalized)
                return [
                    self._event(
                        "minute_suppressed_partial_bucket",
                        occurred_at=minute_end,
                        first_seen_at=observed,
                        mode=mode,
                        minute_open=_iso(timestamp),
                        next_clean_boundary=_iso(self.clean_start_at),
                        reason="direct_target_bootstrap_requires_clean_bucket",
                    )
                ]
            self.clean_start_at = None

        events: list[dict[str, Any]] = []
        if self.cursor is not None:
            gap_seconds = (timestamp - self.cursor.timestamp).total_seconds()
            if gap_seconds > 60.0:
                self.source_gap_count += 1
                events.append(
                    self._event(
                        "paper_stream_incident",
                        occurred_at=observed,
                        first_seen_at=observed,
                        incident_type="source_gap",
                        received_minute_open=_iso(timestamp),
                        prior_minute_open=_iso(self.cursor.timestamp),
                        gap_seconds=gap_seconds,
                        session_gap_policy=(
                            "continuous_minutes_required"
                            if self.asset in BYBIT_ASSETS
                            else "sparse_session_minutes_allowed"
                        ),
                        state_mutated=True,
                    )
                )
        mark_payload: dict[str, Any] | None = None
        if mode == "forward":
            self.pending_order, fill_payload, mark_payload = (
                self.ledger.process_real_minute(
                    row=normalized,
                    observed_at=observed,
                    pending_order=self.pending_order,
                )
            )
            if fill_payload is not None:
                events.append(
                    self._event(
                        "paper_fill",
                        occurred_at=timestamp,
                        first_seen_at=observed,
                        **fill_payload,
                    )
                )
        else:
            if self.pending_order is not None:
                events.append(
                    self._event(
                        "paper_order_suppressed_catchup",
                        occurred_at=minute_end,
                        first_seen_at=observed,
                        mode=mode,
                        order_id=self.pending_order["order_id"],
                        order_schema_version=self.pending_order["order_schema_version"],
                        prior_order_status=self.pending_order["order_status"],
                        order_status="canceled",
                        reason="non_forward_minute_cannot_fill_pending_order",
                    )
                )
                self.pending_order = None
            _, _, mark_payload = self.ledger.process_real_minute(
                row=normalized,
                observed_at=observed,
                pending_order=None,
                allow_fill=False,
                forward_evidence=False,
            )
            self.ledger.suppressed_minutes += 1

        # Causality contract: close the prior target candle before adding this
        # new minute to the next UTC bucket.
        closed = self.builder.advance_to(timestamp)
        if closed is not None:
            events.extend(
                self._commit_closed_target(
                    closed,
                    observed_at=observed,
                    mode=mode,
                )
            )
        self.builder.add(normalized)

        # The prior accepted target candle advances the vertical horizon in
        # ``_commit_closed_target`` before this first constituent minute of the
        # next target candle can touch a horizontal barrier.  Catch-up updates
        # candidates restored from durable state but never schedules new ones.
        if mode != "bootstrap" and self.meta_shadow_book is not None:
            events.extend(
                self._update_meta_shadow_minute_safely(
                    row=normalized,
                    observed_at=observed,
                )
            )
        self.cursor = _MinuteCursor(timestamp, fingerprint, observed)

        if mark_payload is not None:
            events.append(
                self._event(
                    "paper_mark",
                    occurred_at=minute_end,
                    first_seen_at=observed,
                    mode=mode,
                    **mark_payload,
                )
            )
        return events

    def _commit_closed_target(
        self,
        bar: dict[str, Any],
        *,
        observed_at: datetime,
        mode: StreamMode,
    ) -> list[dict[str, Any]]:
        scheduled_close = _utc(bar["available_at"])
        source_minute_count = int(bar["source_minute_count"])
        expected_source_minute_count = self.interval_seconds // 60
        bar_identity = {
            "source_bar_open": _iso(_utc(bar["timestamp"])),
            "scheduled_close": _iso(scheduled_close),
            "source_minute_count": source_minute_count,
            "expected_source_minute_count": expected_source_minute_count,
        }
        if not target_bar_is_complete(
            bar,
            asset=self.asset,
            timeframe=self.timeframe,
        ):
            self.rejected_incomplete_target_count += 1
            return [
                self._event(
                    "target_bar_rejected_incomplete",
                    occurred_at=scheduled_close,
                    first_seen_at=observed_at,
                    mode=mode,
                    **bar_identity,
                    partial_bucket_policy=(
                        "reject_without_exact_source_cadence_or_authoritative_calendar"
                    ),
                    indicator_state_mutated=False,
                    signal_created=False,
                    order_created=False,
                    open=float(bar["open"]),
                    high=float(bar["high"]),
                    low=float(bar["low"]),
                    close=float(bar["close"]),
                    volume=float(bar["volume"]),
                )
            ]

        partial_session_bucket = (
            self.asset not in BYBIT_ASSETS
            and source_minute_count < expected_source_minute_count
        )
        if partial_session_bucket:
            self.accepted_partial_session_target_count += 1
        partial_bucket_policy = (
            "require_exact_source_cadence_without_authoritative_calendar"
            if self.asset not in BYBIT_ASSETS
            else "require_complete_continuous_minutes"
        )
        events = (
            self._advance_meta_shadow_target_bar_safely(
                bar=bar,
                observed_at=observed_at,
            )
            if mode != "bootstrap"
            else []
        )
        online = self.online_engine.update(
            timestamp=_utc(bar["timestamp"]),
            open_value=bar["open"],
            high=bar["high"],
            low=bar["low"],
            close=bar["close"],
            volume=bar["volume"],
            is_final=True,
            scheduled_gap=bool(bar.get("is_session_open_bar", False)),
        )
        cusum = self.cusum_engine.update(
            timestamp=_utc(bar["timestamp"]), close=bar["close"]
        )
        desired, reason = _desired_position(
            online=online,
            cusum=cusum,
            strategy=self.strategy,
        )
        target_event = self._event(
            "target_bar_closed",
            occurred_at=scheduled_close,
            first_seen_at=observed_at,
            mode=mode,
            **bar_identity,
            target_bar_complete=True,
            partial_session_bucket=partial_session_bucket,
            partial_bucket_policy=partial_bucket_policy,
            open=float(bar["open"]),
            high=float(bar["high"]),
            low=float(bar["low"]),
            close=float(bar["close"]),
            volume=float(bar["volume"]),
            indicator_status=online.get("status"),
        )

        signal_identity = {
            "stream_id": self.stream_id,
            **bar_identity,
            "observed_at": _iso(observed_at),
            "strategy_digest": self.strategy.digest(),
        }
        signal_id = _digest(signal_identity, length=24)
        signal_payload = {
            "signal_id": signal_id,
            **bar_identity,
            "observed_at": _iso(observed_at),
            "desired_position": desired,
            "reason": reason,
            "target_bar_complete": True,
            "partial_session_bucket": partial_session_bucket,
            "partial_bucket_policy": partial_bucket_policy,
            "status": online.get("status"),
            "trend_state_code": online.get("trend_state_code"),
            "trend_score": online.get("trend_score"),
            "path_quality": online.get("path_quality"),
            "fast_slow_ratio": online.get("fast_slow_ratio"),
            "cusum_regime": cusum.get("regime"),
            "regime_state": online.get("regime_state"),
            "regime_change_risk": online.get("regime_change_risk"),
        }
        if mode != "forward":
            return [
                *events,
                target_event,
                self._event(
                    "signal_suppressed_catchup",
                    occurred_at=observed_at,
                    first_seen_at=observed_at,
                    mode=mode,
                    suppression_reason="historical_mode_never_creates_orders",
                    **signal_payload,
                ),
            ]

        eligible_at = execution_eligible_at(
            scheduled_close=scheduled_close,
            observed_at=observed_at,
            latency_minutes=self.costs.execution_latency_minutes,
        )
        signal_payload["eligible_at"] = _iso(eligible_at)
        signal_event = self._event(
            "signal_issued",
            occurred_at=observed_at,
            first_seen_at=observed_at,
            **signal_payload,
        )
        events.extend((target_event, signal_event))
        setup_side = (
            "LONG"
            if bool(cusum.get("bull_start", False))
            else "SHORT"
            if bool(cusum.get("bear_start", False))
            else None
        )
        if setup_side is not None and self.meta_shadow_book is not None:
            events.append(
                self._schedule_meta_shadow_candidate_safely(
                    signal_id=signal_id,
                    side=setup_side,
                    bar=bar,
                    online=online,
                    cusum=cusum,
                    decision_at=observed_at,
                    eligible_at=eligible_at,
                )
            )
        # A previously emitted order is immutable.  Retaining it is critical
        # when finalized REST rows arrive after its eligible open: a newer
        # target signal must not retroactively replace an order that would
        # already have been working in real time.
        if self.pending_order is not None:
            events.append(
                self._event(
                    "paper_order_suppressed_pending",
                    occurred_at=observed_at,
                    first_seen_at=observed_at,
                    signal_id=signal_id,
                    retained_order_id=self.pending_order["order_id"],
                    retained_order_schema_version=self.pending_order[
                        "order_schema_version"
                    ],
                    retained_order_status=self.pending_order["order_status"],
                    retained_eligible_at=self.pending_order["eligible_at"],
                    reason="previous_forward_order_is_immutable_until_fill",
                )
            )
            return events
        if math.isclose(desired, self.ledger.position, abs_tol=1e-12):
            self.pending_order = None
            return events

        order_id = _digest(
            {
                "execution_model_version": EXECUTION_MODEL_VERSION,
                "order_schema_version": PAPER_ORDER_SCHEMA_VERSION,
                "stream_id": self.stream_id,
                "signal_id": signal_id,
                "eligible_at": _iso(eligible_at),
                "desired_position": desired,
            },
            length=24,
        )
        self.pending_order = {
            "order_schema_version": PAPER_ORDER_SCHEMA_VERSION,
            "order_id": order_id,
            "order_status": "pending",
            "order_type": "market_at_first_eligible_minute_open",
            "partial_fills": False,
            "signal_id": signal_id,
            "source_bar_open": bar_identity["source_bar_open"],
            "scheduled_close": bar_identity["scheduled_close"],
            "observed_at": _iso(observed_at),
            "eligible_at": _iso(eligible_at),
            "desired_position": desired,
            "reason": reason,
        }
        events.append(
            self._event(
                "paper_order_created",
                occurred_at=observed_at,
                first_seen_at=observed_at,
                **self.pending_order,
                from_position=self.ledger.position,
                requested_turnover=abs(desired - self.ledger.position),
            )
        )
        return events

    def _update_meta_shadow_minute_safely(
        self,
        *,
        row: dict[str, Any],
        observed_at: datetime,
    ) -> list[dict[str, Any]]:
        """Apply one minute atomically to optional shadow state.

        Shadow inference and labeling are observational.  A defect in that
        optional path must retain the last valid shadow book and must never
        interrupt the baseline paper ledger or its durable journal writes.
        """

        assert self.meta_shadow_book is not None
        try:
            candidate_book = self.meta_shadow_book.clone()
            changed = candidate_book.update(
                ShadowExecutionMinute.from_mapping(
                    {
                        "asset": self.asset,
                        "timestamp": row["timestamp"],
                        "open": row["open"],
                        "high": row["high"],
                        "low": row["low"],
                        "close": row["close"],
                        "observed_at": observed_at,
                        "is_real": True,
                    }
                )
            )
            events = self._meta_shadow_terminal_events(
                changed,
                first_seen_at=observed_at,
            )
            self._validate_meta_shadow_transaction(candidate_book, events)
        except Exception as exc:
            return [
                self._meta_shadow_failure_event(
                    phase="execution_minute_update",
                    observed_at=observed_at,
                    error=exc,
                )
            ]
        self.meta_shadow_book = candidate_book
        return events

    def _advance_meta_shadow_target_bar_safely(
        self,
        *,
        bar: dict[str, Any],
        observed_at: datetime,
    ) -> list[dict[str, Any]]:
        """Atomically count one accepted finalized selected-timeframe candle."""

        if self.meta_shadow_book is None:
            return []
        try:
            candidate_book = self.meta_shadow_book.clone()
            changed = candidate_book.advance_target_bar(
                asset=self.asset,
                timeframe=self.timeframe,
                bar_open=_utc(bar["timestamp"]),
                close_price=float(bar["close"]),
                observed_at=observed_at,
            )
            events = self._meta_shadow_terminal_events(
                changed,
                first_seen_at=observed_at,
            )
            self._validate_meta_shadow_transaction(candidate_book, events)
        except Exception as exc:
            return [
                self._meta_shadow_failure_event(
                    phase="accepted_target_bar_advance",
                    observed_at=observed_at,
                    error=exc,
                )
            ]
        self.meta_shadow_book = candidate_book
        return events

    def _schedule_meta_shadow_candidate_safely(
        self,
        *,
        signal_id: str,
        side: str,
        bar: dict[str, Any],
        online: dict[str, Any],
        cusum: dict[str, Any],
        decision_at: datetime,
        eligible_at: datetime,
    ) -> dict[str, Any]:
        """Score and schedule on a copy, promoting only a valid JSON state."""

        assert self.meta_shadow_book is not None
        try:
            candidate_book = self.meta_shadow_book.clone()
            event = self._schedule_meta_shadow_candidate(
                book=candidate_book,
                signal_id=signal_id,
                side=side,
                bar=bar,
                online=online,
                cusum=cusum,
                decision_at=decision_at,
                eligible_at=eligible_at,
            )
            self._validate_meta_shadow_transaction(candidate_book, (event,))
        except Exception as exc:
            return self._meta_shadow_failure_event(
                phase="candidate_score_and_schedule",
                observed_at=decision_at,
                error=exc,
            )
        self.meta_shadow_book = candidate_book
        return event

    @staticmethod
    def _validate_meta_shadow_transaction(
        book: ShadowEventBook,
        events: Iterable[dict[str, Any]],
    ) -> None:
        json.dumps(
            {"book": book.snapshot(), "events": list(events)},
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )

    def _meta_shadow_failure_event(
        self,
        *,
        phase: str,
        observed_at: datetime,
        error: Exception,
    ) -> dict[str, Any]:
        """Return bounded diagnostics without exposing messages or paths."""

        if phase not in META_SHADOW_FAILURE_PHASES:
            raise ValueError("Unknown meta shadow failure phase")
        error_class = error.__class__.__name__
        if not error_class or len(error_class) > 128 or "\x00" in error_class:
            error_class = "Exception"
        error_digest = hashlib.sha256(
            (
                f"{error.__class__.__module__}.{error.__class__.__qualname__}:{error}"
            ).encode("utf-8", errors="replace")
        ).hexdigest()
        self.meta_shadow_failure_count += 1
        self.last_meta_shadow_failure = {
            "phase": phase,
            "error_class": error_class,
            "error_digest": error_digest,
            "observed_at": _iso(observed_at),
        }
        return self._event(
            "meta_shadow_processing_failed",
            occurred_at=observed_at,
            first_seen_at=observed_at,
            mode=META_SHADOW_MODE,
            phase=phase,
            error_class=error_class,
            error_digest=error_digest,
            failure_count=self.meta_shadow_failure_count,
            shadow_state_preserved=True,
            affects_orders=False,
            affects_positions=False,
            real_order_routing=False,
        )

    def _schedule_meta_shadow_candidate(
        self,
        *,
        book: ShadowEventBook,
        signal_id: str,
        side: str,
        bar: dict[str, Any],
        online: dict[str, Any],
        cusum: dict[str, Any],
        decision_at: datetime,
        eligible_at: datetime,
    ) -> dict[str, Any]:
        """Score and schedule one fresh CUSUM setup without affecting orders."""

        assert self.meta_shadow_protection is not None
        assert self.meta_shadow_policy_digest is not None
        barrier_config = self.meta_shadow_protection.barrier_config(self.timeframe)
        estimated_cost_bps = _estimated_roundtrip_cost_bps(self.costs)
        risk_unit = _protected_risk_unit(
            close=float(bar["close"]),
            online=online,
            cusum=cusum,
            protection=self.meta_shadow_protection,
        )
        feature_snapshot = None
        feature_error: str | None = None
        if risk_unit is not None:
            feature_online = dict(online)
            if feature_online.get("available_at") is None:
                feature_online["available_at"] = decision_at
            feature_cusum = dict(cusum)
            if feature_cusum.get("available_at") is None:
                feature_cusum["available_at"] = decision_at
            feature_snapshot = build_feature_snapshot(
                setup_id=signal_id,
                side=side,
                decision_at=decision_at,
                online=feature_online,
                cusum=feature_cusum,
                entry_reference=float(bar["close"]),
                risk_unit=risk_unit,
                stop_risk_units=barrier_config.stop_risk_units,
                target_risk_units=barrier_config.target_risk_units,
                timeout_target_bars=barrier_config.timeout_target_bars,
                target_interval_seconds=barrier_config.target_interval_seconds,
                estimated_roundtrip_cost_bps=estimated_cost_bps,
            )
        else:
            feature_error = "causal protected risk unit is unavailable"

        inference: InferenceResult
        if feature_snapshot is None:
            inference = InferenceResult(
                available=False,
                accepted=False,
                probability=None,
                decision_threshold=(
                    None
                    if self.meta_artifact is None
                    else self.meta_artifact.decision_threshold
                ),
                reason=(
                    "risk_unit_unavailable"
                    if risk_unit is None
                    else "feature_snapshot_invalid"
                ),
                model_version=(
                    None
                    if self.meta_artifact is None
                    else self.meta_artifact.model_version
                ),
                artifact_checksum=(
                    None if self.meta_artifact is None else self.meta_artifact.checksum
                ),
            )
        elif self.meta_artifact is None:
            inference = InferenceResult(
                available=False,
                accepted=False,
                probability=None,
                decision_threshold=None,
                reason=self.meta_artifact_reason,
                model_version=None,
                artifact_checksum=None,
            )
        else:
            inference = score_features(
                self.meta_artifact,
                feature_snapshot.feature_map(),
                expected_feature_names=META_FEATURE_NAMES,
                expected_policy_digest=self.meta_shadow_policy_digest,
                asset=self.asset,
                timeframe=self.timeframe,
                decision_at=decision_at,
            )
        static_break_even_probability = _decision_static_stop_break_even_probability(
            entry_reference=float(bar["close"]),
            risk_unit=risk_unit,
            barrier=barrier_config,
            costs=self.costs,
            side=TradeSide(side),
        )
        static_threshold_with_margin = (
            None
            if static_break_even_probability is None
            else static_break_even_probability
            + self.meta_shadow_protection.break_even_safety_margin
        )
        static_payoff_untradeable = bool(
            static_threshold_with_margin is not None
            and static_threshold_with_margin >= 1.0
        )
        required_thresholds = [
            threshold
            for threshold in (
                inference.decision_threshold,
                static_threshold_with_margin,
            )
            if threshold is not None
        ]
        required_probability = (
            None
            if static_payoff_untradeable
            else max(required_thresholds)
            if required_thresholds
            else None
        )
        counterfactual_accepted = bool(
            inference.available
            and inference.probability is not None
            and required_probability is not None
            and inference.probability > required_probability
        )
        counterfactual_reason = (
            inference.reason
            if not inference.available
            else "static_payoff_untradeable_after_costs"
            if static_payoff_untradeable
            else "required_probability_unavailable"
            if required_probability is None
            else "accepted"
            if counterfactual_accepted
            else "probability_below_required_threshold"
        )

        shadow_event_id = _digest(
            {
                "mode": META_SHADOW_MODE,
                "stream_id": self.stream_id,
                "signal_id": signal_id,
            },
            length=64,
        )
        candidate: ShadowCandidate | None = None
        if feature_snapshot is not None and risk_unit is not None:
            candidate = ShadowCandidate(
                event_id=shadow_event_id,
                setup_id=signal_id,
                asset=self.asset,
                timeframe=self.timeframe,
                decision_at=decision_at,
                eligible_at=eligible_at,
                side=side,
                entry_reference=float(bar["close"]),
                risk_unit=risk_unit,
                features=feature_snapshot,
                barrier_config=barrier_config,
                policy_digest=self.meta_shadow_policy_digest,
                estimated_roundtrip_cost_bps=estimated_cost_bps,
                adverse_entry_bps=(
                    self.costs.slippage_bps + 0.5 * self.costs.spread_bps
                ),
                gap_policy=(
                    ShadowGapPolicy.CONTINUOUS_CANCEL
                    if self.asset in BYBIT_ASSETS
                    else ShadowGapPolicy.SESSION_NEXT_OPEN
                ),
            )
            book.schedule(candidate)

        return self._event(
            "meta_shadow_prediction",
            occurred_at=decision_at,
            first_seen_at=decision_at,
            mode=META_SHADOW_MODE,
            shadow_event_id=shadow_event_id,
            setup_id=signal_id,
            decision_at=_iso(decision_at),
            eligible_at=_iso(eligible_at),
            side=side,
            entry_reference=float(bar["close"]),
            risk_unit=risk_unit,
            available=inference.available,
            model_threshold_accepted=inference.accepted,
            counterfactual_accepted=counterfactual_accepted,
            probability=inference.probability,
            decision_threshold=inference.decision_threshold,
            decision_static_stop_break_even_probability=(static_break_even_probability),
            break_even_safety_margin=(
                self.meta_shadow_protection.break_even_safety_margin
            ),
            static_threshold_with_margin=static_threshold_with_margin,
            static_payoff_untradeable_after_costs=static_payoff_untradeable,
            required_probability=required_probability,
            acceptance_rule=(
                "probability_strictly_exceeds_model_and_static_threshold_with_margin"
            ),
            score_reason=inference.reason,
            counterfactual_reason=counterfactual_reason,
            model_version=inference.model_version,
            artifact_checksum=inference.artifact_checksum,
            artifact_load_reason=self.meta_artifact_reason,
            policy_digest=self.meta_shadow_policy_digest,
            protection_config_digest=self.meta_shadow_protection.digest(),
            barrier_config_digest=barrier_config.digest(),
            feature_schema_digest=(
                None
                if feature_snapshot is None
                else digest_feature_schema(feature_snapshot.feature_names)
            ),
            feature_snapshot_digest=(
                None if feature_snapshot is None else feature_snapshot.digest()
            ),
            feature_snapshot=(
                None if feature_snapshot is None else feature_snapshot.as_dict()
            ),
            feature_error=feature_error,
            candidate_scheduled=candidate is not None,
            candidate_digest=None if candidate is None else candidate.digest(),
            candidate_error=None,
            stored_at_event_time=True,
            affects_orders=False,
            affects_positions=False,
            real_order_routing=False,
        )

    def _meta_shadow_terminal_events(
        self,
        records: Iterable[ShadowEventRecord],
        *,
        first_seen_at: datetime,
    ) -> list[dict[str, Any]]:
        """Journal only terminal shadow outcomes, never minute-by-minute state."""

        events: list[dict[str, Any]] = []
        for record in records:
            if record.state is not ShadowEventState.RESOLVED:
                continue
            assert record.label_known_at is not None
            events.append(
                self._event(
                    "meta_shadow_label",
                    occurred_at=record.label_known_at,
                    first_seen_at=first_seen_at,
                    mode=META_SHADOW_MODE,
                    shadow_event_id=record.candidate.event_id,
                    setup_id=record.candidate.setup_id,
                    decision_at=_iso(record.candidate.decision_at),
                    eligible_at=_iso(record.candidate.eligible_at),
                    outcome=(None if record.outcome is None else record.outcome.value),
                    outcome_occurred_at=(
                        None if record.occurred_at is None else _iso(record.occurred_at)
                    ),
                    label_known_at=_iso(record.label_known_at),
                    default_binary_label=(
                        None
                        if record.evaluation is None
                        else record.evaluation.default_binary_label
                    ),
                    economic_binary_target=record.economic_binary_target,
                    gross_return_bps=record.gross_return_bps,
                    net_return_bps=record.net_return_bps,
                    reason=record.reason,
                    observed_bars=record.observed_bars,
                    candidate_digest=record.candidate.digest(),
                    plan_digest=(None if record.plan is None else record.plan.digest()),
                    evaluation_digest=(
                        None
                        if record.evaluation is None
                        else record.evaluation.digest()
                    ),
                    policy_digest=record.candidate.policy_digest,
                    artifact_checksum=(
                        None
                        if self.meta_artifact is None
                        else self.meta_artifact.checksum
                    ),
                    model_version=(
                        None
                        if self.meta_artifact is None
                        else self.meta_artifact.model_version
                    ),
                    shadow_record=record.as_dict(),
                    affects_orders=False,
                    affects_positions=False,
                    real_order_routing=False,
                )
            )
        return events

    def _incident(
        self,
        *,
        incident_type: str,
        timestamp: datetime,
        observed_at: datetime,
        **details: Any,
    ) -> dict[str, Any]:
        return self._event(
            "paper_stream_incident",
            occurred_at=observed_at,
            first_seen_at=observed_at,
            incident_type=incident_type,
            received_minute_open=_iso(timestamp),
            state_mutated=False,
            **details,
        )

    def _event(
        self,
        event_type: str,
        *,
        occurred_at: datetime,
        first_seen_at: datetime,
        **payload: Any,
    ) -> dict[str, Any]:
        event = {
            "event_version": PAPER_EVENT_VERSION,
            "event_type": event_type,
            "stream_id": self.stream_id,
            "asset": self.asset,
            "timeframe": self.timeframe,
            "occurred_at": _iso(occurred_at),
            "observed_at": _iso(first_seen_at),
            **payload,
        }
        # Reject NaN/Infinity before an event reaches an append-only journal.
        encoded = json.dumps(
            event, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        return {
            "event_id": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
            **event,
        }

    def snapshot(self) -> dict[str, Any]:
        bar = getattr(self.builder, "_bar", None)
        builder_bar = None
        if bar is not None:
            builder_bar = {
                **bar,
                "timestamp": _iso(_utc(bar["timestamp"])),
                "source_minute_first": _iso(
                    _utc(bar.get("source_minute_first", bar["timestamp"]))
                ),
                "source_minute_last": _iso(
                    _utc(bar.get("source_minute_last", bar["timestamp"]))
                ),
            }
        cursor = None
        if self.cursor is not None:
            cursor = {
                "timestamp": _iso(self.cursor.timestamp),
                "fingerprint": self.cursor.fingerprint,
                "observed_at": _iso(self.cursor.observed_at),
            }
        payload = {
            "algorithm_version": FORWARD_PAPER_STREAM_VERSION,
            "asset": self.asset,
            "timeframe": self.timeframe,
            "interval_seconds": self.interval_seconds,
            "strategy": self.strategy.as_dict(),
            "strategy_digest": self.strategy.digest(),
            "costs": self.costs.as_dict(),
            "cost_digest": self.costs.digest(),
            "online_config_digest": self.online_config.digest(),
            "stream_id": self.stream_id,
            "builder": {
                "timeframe": self.timeframe,
                "current_bar": builder_bar,
            },
            "online_engine": self.online_engine.snapshot(),
            "cusum_engine": self.cusum_engine.snapshot(),
            "ledger": self.ledger.snapshot(),
            "pending_order": self.pending_order,
            "cursor": cursor,
            "clean_start_at": _iso_or_none(self.clean_start_at),
            "bootstrap_target_bar_count": self.bootstrap_target_bar_count,
            "bootstrap_target_through": _iso_or_none(self.bootstrap_target_through),
            "source_gap_count": self.source_gap_count,
            "rejected_incomplete_target_count": (self.rejected_incomplete_target_count),
            "accepted_partial_session_target_count": (
                self.accepted_partial_session_target_count
            ),
            "meta_shadow_failure_count": self.meta_shadow_failure_count,
            "last_meta_shadow_failure": self.last_meta_shadow_failure,
        }
        if self.meta_shadow_book is not None:
            assert self.meta_shadow_protection is not None
            assert self.meta_shadow_policy_digest is not None
            barrier = self.meta_shadow_protection.barrier_config(self.timeframe)
            payload["meta_shadow"] = {
                "mode": META_SHADOW_MODE,
                "protection_config_digest": self.meta_shadow_protection.digest(),
                "barrier_config_digest": barrier.digest(),
                "policy_digest": self.meta_shadow_policy_digest,
                "artifact_identity": self._meta_artifact_identity(),
                "book": self.meta_shadow_book.snapshot(),
            }
        return _with_checksum(payload)

    @classmethod
    def restore(
        cls,
        snapshot: dict[str, Any],
        *,
        meta_shadow_protection: ProtectedReplayConfig | None = None,
        meta_artifact: LogisticCoefficientArtifact | None = None,
        meta_artifact_reason: str = "artifact_not_configured",
    ) -> ForwardPaperStream:
        raw = _validated_snapshot(snapshot, name="forward paper stream")
        if raw.get("algorithm_version") != FORWARD_PAPER_STREAM_VERSION:
            raise ForwardPaperStateError("Forward paper stream version mismatch")
        strategy = _restore_strategy(raw.get("strategy"))
        costs = _restore_costs(raw.get("costs"))
        raw_meta_shadow = raw.get("meta_shadow")
        if raw_meta_shadow is not None and not isinstance(raw_meta_shadow, dict):
            raise ForwardPaperStateError("Forward paper meta shadow state is invalid")
        if raw_meta_shadow is None and meta_shadow_protection is not None:
            raise ForwardPaperStateError(
                "Forward paper snapshot predates the configured meta shadow cohort"
            )
        if raw_meta_shadow is not None and meta_shadow_protection is None:
            raise ForwardPaperStateError(
                "Forward paper meta shadow restore requires the server-side config"
            )
        stream = cls(
            asset=str(raw.get("asset", "")),
            timeframe=str(raw.get("timeframe", "")),
            strategy=strategy,
            costs=costs,
            meta_shadow_protection=meta_shadow_protection,
            meta_artifact=meta_artifact,
            meta_artifact_reason=meta_artifact_reason,
        )
        if raw.get("interval_seconds") != stream.interval_seconds:
            raise ForwardPaperStateError("Forward paper interval mismatch")
        if raw.get("strategy_digest") != strategy.digest():
            raise ForwardPaperStateError("Forward paper strategy digest mismatch")
        if raw.get("cost_digest") != costs.digest():
            raise ForwardPaperStateError("Forward paper cost digest mismatch")
        if raw.get("online_config_digest") != stream.online_config.digest():
            raise ForwardPaperStateError("Forward paper online config mismatch")
        if raw.get("stream_id") != stream.stream_id:
            raise ForwardPaperStateError("Forward paper stream identity mismatch")

        stream.online_engine = OnlineSignalEngine.restore(
            raw.get("online_engine"), expected_config=stream.online_config
        )
        stream.cusum_engine = CusumTrendEngine.restore(
            raw.get("cusum_engine"),
            expected_sensitivity=stream.strategy.cusum_sensitivity,
        )
        stream.ledger = NormalizedPaperLedger.restore(
            raw.get("ledger"), expected_costs=stream.costs
        )
        builder_state = raw.get("builder")
        if (
            not isinstance(builder_state, dict)
            or builder_state.get("timeframe") != stream.timeframe
        ):
            raise ForwardPaperStateError("Forward paper builder state is invalid")
        restored_bar = _restore_builder_bar(
            builder_state.get("current_bar"), interval_seconds=stream.interval_seconds
        )
        stream.builder._bar = restored_bar

        stream.pending_order = _restore_pending_order(raw.get("pending_order"))
        cursor = raw.get("cursor")
        if cursor is not None:
            if not isinstance(cursor, dict):
                raise ForwardPaperStateError("Forward paper cursor is invalid")
            timestamp = _parse_utc(cursor.get("timestamp"), "cursor timestamp")
            observed_at = _parse_utc(cursor.get("observed_at"), "cursor observed_at")
            fingerprint = cursor.get("fingerprint")
            if not _is_hex_digest(
                fingerprint, 64
            ) or observed_at < timestamp + timedelta(minutes=1):
                raise ForwardPaperStateError("Forward paper cursor is invalid")
            stream.cursor = _MinuteCursor(timestamp, str(fingerprint), observed_at)
        stream.clean_start_at = _optional_utc(raw.get("clean_start_at"), "clean start")
        stream.bootstrap_target_bar_count = _nonnegative_int(
            raw.get("bootstrap_target_bar_count"), "bootstrap target count"
        )
        stream.bootstrap_target_through = _optional_utc(
            raw.get("bootstrap_target_through"), "bootstrap target through"
        )
        stream.source_gap_count = _nonnegative_int(
            raw.get("source_gap_count"), "source gap count"
        )
        stream.rejected_incomplete_target_count = _nonnegative_int(
            raw.get("rejected_incomplete_target_count"),
            "rejected incomplete target count",
        )
        stream.accepted_partial_session_target_count = _nonnegative_int(
            raw.get("accepted_partial_session_target_count"),
            "accepted partial session target count",
        )
        stream.meta_shadow_failure_count = _nonnegative_int(
            raw.get("meta_shadow_failure_count"),
            "meta shadow failure count",
        )
        raw_last_failure = raw.get("last_meta_shadow_failure")
        if raw_last_failure is None:
            if stream.meta_shadow_failure_count:
                raise ForwardPaperStateError(
                    "Forward paper meta shadow failure state is invalid"
                )
            stream.last_meta_shadow_failure = None
        else:
            if not isinstance(raw_last_failure, dict):
                raise ForwardPaperStateError(
                    "Forward paper meta shadow failure state is invalid"
                )
            phase = raw_last_failure.get("phase")
            error_class = raw_last_failure.get("error_class")
            error_digest = raw_last_failure.get("error_digest")
            failure_observed_at = _parse_utc(
                raw_last_failure.get("observed_at"),
                "meta shadow failure observed_at",
            )
            if (
                phase not in META_SHADOW_FAILURE_PHASES
                or not isinstance(error_class, str)
                or not error_class
                or len(error_class) > 128
                or "\x00" in error_class
                or not _is_hex_digest(error_digest, 64)
                or stream.meta_shadow_failure_count == 0
            ):
                raise ForwardPaperStateError(
                    "Forward paper meta shadow failure state is invalid"
                )
            stream.last_meta_shadow_failure = {
                "phase": phase,
                "error_class": error_class,
                "error_digest": str(error_digest),
                "observed_at": _iso(failure_observed_at),
            }
        if raw_meta_shadow is None and stream.meta_shadow_failure_count:
            raise ForwardPaperStateError(
                "Forward paper meta shadow failure state is invalid"
            )
        if raw_meta_shadow is not None:
            assert stream.meta_shadow_protection is not None
            assert stream.meta_shadow_policy_digest is not None
            if raw_meta_shadow.get("mode") != META_SHADOW_MODE:
                raise ForwardPaperStateError("Forward paper meta shadow mode mismatch")
            barrier = stream.meta_shadow_protection.barrier_config(stream.timeframe)
            expected_meta_contract = {
                "protection_config_digest": stream.meta_shadow_protection.digest(),
                "barrier_config_digest": barrier.digest(),
                "policy_digest": stream.meta_shadow_policy_digest,
                "artifact_identity": stream._meta_artifact_identity(),
            }
            for field_name, expected_value in expected_meta_contract.items():
                if raw_meta_shadow.get(field_name) != expected_value:
                    raise ForwardPaperStateError(
                        f"Forward paper meta shadow {field_name} mismatch"
                    )
            book_snapshot = raw_meta_shadow.get("book")
            if not isinstance(book_snapshot, dict):
                raise ForwardPaperStateError(
                    "Forward paper meta shadow book snapshot is invalid"
                )
            try:
                stream.meta_shadow_book = ShadowEventBook.from_snapshot(book_snapshot)
            except (TypeError, ValueError) as exc:
                raise ForwardPaperStateError(
                    "Forward paper meta shadow book snapshot is invalid"
                ) from exc
        if (stream.bootstrap_target_bar_count == 0) != (
            stream.bootstrap_target_through is None
        ):
            raise ForwardPaperStateError("Forward paper bootstrap state is invalid")
        if (
            stream.cursor is not None
            and stream.ledger.last_minute != stream.cursor.timestamp
        ):
            raise ForwardPaperStateError("Forward paper cursor and ledger diverged")
        return stream

    def _meta_artifact_identity(self) -> dict[str, Any]:
        return {
            "available": self.meta_artifact is not None,
            "reason": self.meta_artifact_reason,
            "model_version": (
                None if self.meta_artifact is None else self.meta_artifact.model_version
            ),
            "checksum": (
                None if self.meta_artifact is None else self.meta_artifact.checksum
            ),
        }


def _normalized_ohlcv_row(row: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(row, dict):
        raise ValueError("Paper minute must be a mapping")
    timestamp = _parse_utc(row.get("timestamp"), "timestamp")
    if timestamp.second or timestamp.microsecond:
        raise ValueError("Paper minute timestamp must be minute-aligned")
    open_value = _positive_finite(row.get("open"), field="open")
    high = _positive_finite(row.get("high"), field="high")
    low = _positive_finite(row.get("low"), field="low")
    close = _positive_finite(row.get("close"), field="close")
    if high < max(open_value, close) or low > min(open_value, close):
        raise ValueError("Paper minute OHLC ordering is invalid")
    volume = _nonnegative_finite(row.get("volume", 0.0), "volume")
    return {
        "timestamp": timestamp,
        "open": open_value,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "is_session_open_bar": bool(row.get("is_session_open_bar", False)),
        "is_synthetic_no_trade": bool(row.get("is_synthetic_no_trade", False)),
    }


def _minute_fingerprint(row: dict[str, Any]) -> str:
    return _digest(
        {
            **row,
            "timestamp": _iso(_utc(row["timestamp"])),
        },
        length=64,
    )


def _restore_builder_bar(raw: Any, *, interval_seconds: int) -> dict[str, Any] | None:
    if raw is None:
        return None
    row = _normalized_ohlcv_row(raw)
    timestamp = row["timestamp"]
    if _bucket_start(timestamp, interval_seconds) != timestamp:
        raise ForwardPaperStateError("Forward paper builder bucket is invalid")
    count = _positive_int(raw.get("source_minute_count"), "source minute count")
    source_minute_first = _parse_utc(
        raw.get("source_minute_first"), "builder source minute first"
    )
    source_minute_last = _parse_utc(
        raw.get("source_minute_last"), "builder source minute last"
    )
    contiguous = raw.get("source_minutes_contiguous")
    if (
        not isinstance(contiguous, bool)
        or source_minute_first < timestamp
        or source_minute_last < source_minute_first
        or source_minute_last >= timestamp + timedelta(seconds=interval_seconds)
    ):
        raise ForwardPaperStateError("Forward paper builder source cadence is invalid")
    return {
        "timestamp": timestamp,
        "open": row["open"],
        "high": row["high"],
        "low": row["low"],
        "close": row["close"],
        "volume": row["volume"],
        "is_session_open_bar": row["is_session_open_bar"],
        "source_minute_count": count,
        "source_minute_first": source_minute_first,
        "source_minute_last": source_minute_last,
        "source_minutes_contiguous": contiguous,
    }


def _restore_pending_order(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ForwardPaperStateError("Forward paper pending order is invalid")
    required_strings = (
        "order_schema_version",
        "order_id",
        "order_status",
        "order_type",
        "signal_id",
        "source_bar_open",
        "scheduled_close",
        "observed_at",
        "eligible_at",
        "reason",
    )
    if any(not isinstance(raw.get(field), str) for field in required_strings):
        raise ForwardPaperStateError("Forward paper pending order is invalid")
    if not _is_hex_digest(raw["order_id"], 24) or not _is_hex_digest(
        raw["signal_id"], 24
    ):
        raise ForwardPaperStateError("Forward paper pending order is invalid")
    if (
        raw["order_schema_version"] != PAPER_ORDER_SCHEMA_VERSION
        or raw["order_status"] != "pending"
        or raw["order_type"] != "market_at_first_eligible_minute_open"
        or raw.get("partial_fills") is not False
    ):
        raise ForwardPaperStateError("Forward paper pending order contract is invalid")
    source_bar = _parse_utc(raw["source_bar_open"], "order source bar")
    scheduled = _parse_utc(raw["scheduled_close"], "order scheduled close")
    observed = _parse_utc(raw["observed_at"], "order observed_at")
    eligible = _parse_utc(raw["eligible_at"], "order eligible_at")
    if source_bar >= scheduled or eligible < max(scheduled, observed):
        raise ForwardPaperStateError("Forward paper pending order timing is invalid")
    return {
        **raw,
        "desired_position": _bounded_position(raw.get("desired_position")),
    }


def _restore_strategy(raw: Any) -> IndicatorStrategyConfig:
    if not isinstance(raw, dict):
        raise ForwardPaperStateError("Forward paper strategy is invalid")
    values = dict(raw)
    values["horizons"] = tuple(values.get("horizons", ()))
    try:
        return IndicatorStrategyConfig(**values)
    except (TypeError, ValueError) as exc:
        raise ForwardPaperStateError("Forward paper strategy is invalid") from exc


def _restore_costs(raw: Any) -> ReplayCostConfig:
    if not isinstance(raw, dict):
        raise ForwardPaperStateError("Forward paper costs are invalid")
    try:
        return ReplayCostConfig(**raw)
    except (TypeError, ValueError) as exc:
        raise ForwardPaperStateError("Forward paper costs are invalid") from exc


def _with_checksum(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
    except (TypeError, ValueError) as exc:
        raise ForwardPaperStateError("Snapshot is not JSON-safe") from exc
    return {
        **payload,
        "checksum": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
    }


def _validated_snapshot(snapshot: Any, *, name: str) -> dict[str, Any]:
    if not isinstance(snapshot, dict):
        raise ForwardPaperStateError(f"{name.title()} snapshot must be a mapping")
    raw = dict(snapshot)
    checksum = raw.pop("checksum", None)
    try:
        encoded = json.dumps(
            raw, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
    except (TypeError, ValueError) as exc:
        raise ForwardPaperStateError(
            f"{name.title()} snapshot is not JSON-safe"
        ) from exc
    expected = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    if checksum != expected:
        raise ForwardPaperStateError(f"{name.title()} snapshot checksum mismatch")
    return raw


def _digest(payload: dict[str, Any], *, length: int) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:length]


def _bucket_start(timestamp: datetime, interval_seconds: int) -> datetime:
    epoch = int(_utc(timestamp).timestamp())
    return datetime.fromtimestamp(
        (epoch // interval_seconds) * interval_seconds, tz=timezone.utc
    )


def _next_bucket_start(timestamp: datetime, interval_seconds: int) -> datetime:
    return _bucket_start(timestamp, interval_seconds) + timedelta(
        seconds=interval_seconds
    )


def _parse_utc(value: Any, field: str) -> datetime:
    if isinstance(value, datetime):
        return _utc(value)
    if not isinstance(value, str) or not value:
        raise ForwardPaperStateError(f"Forward paper {field} is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ForwardPaperStateError(f"Forward paper {field} is invalid") from exc
    return _utc(parsed)


def _optional_utc(value: Any, field: str) -> datetime | None:
    return None if value is None else _parse_utc(value, field)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _iso_or_none(value: datetime | None) -> str | None:
    return None if value is None else _iso(value)


def _finite(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise ForwardPaperStateError(f"Forward paper {field} is invalid")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ForwardPaperStateError(f"Forward paper {field} is invalid") from exc
    if not math.isfinite(parsed):
        raise ForwardPaperStateError(f"Forward paper {field} is invalid")
    return parsed


def _positive_finite(value: Any, *, field: str) -> float:
    parsed = _finite(value, field)
    if parsed <= 0.0:
        raise ForwardPaperStateError(f"Forward paper {field} must be positive")
    return parsed


def _nonnegative_finite(value: Any, field: str) -> float:
    parsed = _finite(value, field)
    if parsed < 0.0:
        raise ForwardPaperStateError(f"Forward paper {field} must be non-negative")
    return parsed


def _bounded_position(value: Any) -> float:
    parsed = _finite(value, "position")
    if not -1.0 <= parsed <= 1.0:
        raise ForwardPaperStateError("Forward paper position is out of bounds")
    return parsed


def _nonnegative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ForwardPaperStateError(f"Forward paper {field} is invalid")
    return value


def _positive_int(value: Any, field: str) -> int:
    parsed = _nonnegative_int(value, field)
    if parsed <= 0:
        raise ForwardPaperStateError(f"Forward paper {field} must be positive")
    return parsed


def _is_hex_digest(value: Any, length: int) -> bool:
    return (
        isinstance(value, str)
        and len(value) == length
        and all(character in "0123456789abcdef" for character in value)
    )
