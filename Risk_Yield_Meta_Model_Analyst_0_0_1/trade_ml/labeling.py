"""Side-aware first-touch barrier labeling with explicit ambiguity handling."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from .contracts import (
    BarrierOutcome,
    BarrierPlan,
    TradeSide,
    as_utc_datetime,
    stable_digest,
    utc_iso,
)

LABEL_SCHEMA_VERSION = "trade_ml_barrier_label_v2"
TRACKER_SCHEMA_VERSION = "trade_ml_barrier_tracker_v2"


def _finite_positive(value: Any, *, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite positive number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite positive number") from exc
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(f"{name} must be a finite positive number")
    return number


@dataclass(frozen=True, slots=True)
class MinuteBar:
    """Minimal validated OHLC bar consumed by the label evaluator."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "timestamp",
            as_utc_datetime(self.timestamp, name="bar timestamp"),
        )
        for name in ("open", "high", "low", "close"):
            object.__setattr__(
                self,
                name,
                _finite_positive(getattr(self, name), name=f"bar {name}"),
            )
        if self.high < max(self.open, self.low, self.close):
            raise ValueError("bar high must be at least open, low, and close")
        if self.low > min(self.open, self.high, self.close):
            raise ValueError("bar low must be at most open, high, and close")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> MinuteBar:
        """Build a bar from a mapping with canonical OHLC field names."""

        try:
            return cls(
                timestamp=value["timestamp"],
                open=value["open"],
                high=value["high"],
                low=value["low"],
                close=value["close"],
            )
        except KeyError as exc:
            raise ValueError(f"bar is missing required field {exc.args[0]!r}") from exc

    def as_dict(self) -> dict[str, Any]:
        return {
            "timestamp": utc_iso(self.timestamp),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
        }


@dataclass(frozen=True, slots=True)
class BarrierEvaluation:
    """Terminal label and execution assumptions for a protected setup.

    ``outcome`` preserves data quality: a bar touching both barriers is marked
    ``AMBIGUOUS``.  ``primary_outcome`` is the conservative result used by the
    default binary target, while ``optimistic_outcome`` records the sensitivity
    alternative without silently replacing the primary label.
    """

    setup_id: str
    plan_digest: str
    outcome: BarrierOutcome
    primary_outcome: BarrierOutcome
    optimistic_outcome: BarrierOutcome | None
    occurred_at: datetime
    label_known_at: datetime
    observed_bars: int
    exit_price: float | None
    optimistic_exit_price: float | None
    gap_through: bool
    same_bar_ambiguous: bool
    optimistic_target_possible: bool
    default_binary_label: int | None
    side_return_pct: float | None
    reason: str

    def __post_init__(self) -> None:
        setup_id = str(self.setup_id).strip()
        if not setup_id:
            raise ValueError("setup_id must not be empty")
        object.__setattr__(self, "setup_id", setup_id)
        plan_digest = str(self.plan_digest).strip()
        if not plan_digest:
            raise ValueError("plan_digest must not be empty")
        object.__setattr__(self, "plan_digest", plan_digest)
        object.__setattr__(
            self,
            "occurred_at",
            as_utc_datetime(self.occurred_at, name="occurred_at"),
        )
        object.__setattr__(
            self,
            "label_known_at",
            as_utc_datetime(self.label_known_at, name="label_known_at"),
        )
        if self.label_known_at < self.occurred_at:
            raise ValueError("label_known_at must not precede occurred_at")
        for field_name in ("outcome", "primary_outcome"):
            value = getattr(self, field_name)
            try:
                normalized = (
                    value
                    if isinstance(value, BarrierOutcome)
                    else BarrierOutcome(value)
                )
            except ValueError as exc:
                raise ValueError(f"invalid {field_name}") from exc
            object.__setattr__(self, field_name, normalized)
        if self.optimistic_outcome is not None:
            try:
                normalized_optimistic = (
                    self.optimistic_outcome
                    if isinstance(self.optimistic_outcome, BarrierOutcome)
                    else BarrierOutcome(self.optimistic_outcome)
                )
            except ValueError as exc:
                raise ValueError("invalid optimistic_outcome") from exc
            object.__setattr__(self, "optimistic_outcome", normalized_optimistic)
        if isinstance(self.observed_bars, bool) or not isinstance(
            self.observed_bars, int
        ):
            raise ValueError("observed_bars must be a non-negative integer")
        if self.observed_bars < 0:
            raise ValueError("observed_bars must be a non-negative integer")
        for field_name in ("exit_price", "optimistic_exit_price"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(
                    self,
                    field_name,
                    _finite_positive(value, name=field_name),
                )
        if self.side_return_pct is not None:
            side_return = float(self.side_return_pct)
            if not math.isfinite(side_return):
                raise ValueError("side_return_pct must be finite when present")
            object.__setattr__(self, "side_return_pct", side_return)
        for field_name in (
            "gap_through",
            "same_bar_ambiguous",
            "optimistic_target_possible",
        ):
            if not isinstance(getattr(self, field_name), bool):
                raise ValueError(f"{field_name} must be boolean")
        if isinstance(
            self.default_binary_label, bool
        ) or self.default_binary_label not in (
            None,
            0,
            1,
        ):
            raise ValueError("default_binary_label must be zero, one, or None")

        expected_label = {
            BarrierOutcome.TARGET: 1,
            BarrierOutcome.STOP: 0,
            BarrierOutcome.TIMEOUT: 0,
            BarrierOutcome.AMBIGUOUS: 0,
            BarrierOutcome.CANCELLED: None,
        }[self.outcome]
        if self.default_binary_label != expected_label:
            raise ValueError("default_binary_label is inconsistent with outcome")
        if self.outcome is BarrierOutcome.AMBIGUOUS:
            if (
                self.primary_outcome is not BarrierOutcome.STOP
                or self.optimistic_outcome is not BarrierOutcome.TARGET
                or not self.same_bar_ambiguous
                or not self.optimistic_target_possible
            ):
                raise ValueError(
                    "ambiguous outcomes require stop-first primary semantics"
                )
        elif (
            self.primary_outcome is not self.outcome
            or self.optimistic_outcome is not None
            or self.same_bar_ambiguous
            or self.optimistic_target_possible
        ):
            raise ValueError(
                "non-ambiguous outcomes must use their direct primary result"
            )
        if self.outcome is BarrierOutcome.CANCELLED:
            if self.exit_price is not None or self.optimistic_exit_price is not None:
                raise ValueError("cancelled outcomes must not contain exit prices")
        elif self.exit_price is None:
            raise ValueError("resolved barrier outcomes require an exit price")
        reason = str(self.reason).strip()
        if not reason:
            raise ValueError("reason must not be empty")
        object.__setattr__(self, "reason", reason)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": LABEL_SCHEMA_VERSION,
            "setup_id": self.setup_id,
            "plan_digest": self.plan_digest,
            "outcome": self.outcome.value,
            "primary_outcome": self.primary_outcome.value,
            "optimistic_outcome": (
                self.optimistic_outcome.value if self.optimistic_outcome else None
            ),
            "occurred_at": utc_iso(self.occurred_at),
            "label_known_at": utc_iso(self.label_known_at),
            "observed_bars": self.observed_bars,
            "exit_price": self.exit_price,
            "optimistic_exit_price": self.optimistic_exit_price,
            "gap_through": self.gap_through,
            "same_bar_ambiguous": self.same_bar_ambiguous,
            "optimistic_target_possible": self.optimistic_target_possible,
            "default_binary_label": self.default_binary_label,
            "side_return_pct": self.side_return_pct,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> BarrierEvaluation:
        """Restore and validate a terminal evaluation from JSON-safe data."""

        if payload.get("schema_version") != LABEL_SCHEMA_VERSION:
            raise ValueError("unsupported barrier evaluation schema_version")
        try:
            return cls(
                setup_id=payload["setup_id"],
                plan_digest=payload["plan_digest"],
                outcome=payload["outcome"],
                primary_outcome=payload["primary_outcome"],
                optimistic_outcome=payload.get("optimistic_outcome"),
                occurred_at=payload["occurred_at"],
                label_known_at=payload["label_known_at"],
                observed_bars=payload["observed_bars"],
                exit_price=payload.get("exit_price"),
                optimistic_exit_price=payload.get("optimistic_exit_price"),
                gap_through=payload["gap_through"],
                same_bar_ambiguous=payload["same_bar_ambiguous"],
                optimistic_target_possible=payload["optimistic_target_possible"],
                default_binary_label=payload.get("default_binary_label"),
                side_return_pct=payload.get("side_return_pct"),
                reason=payload["reason"],
            )
        except KeyError as exc:
            raise ValueError(f"barrier evaluation is missing {exc.args[0]!r}") from exc

    def digest(self) -> str:
        return stable_digest(self.as_dict())


def _side_return_pct(plan: BarrierPlan, exit_price: float) -> float:
    return plan.side.multiplier * ((exit_price / plan.fill_price) - 1.0) * 100.0


def _terminal(
    plan: BarrierPlan,
    *,
    outcome: BarrierOutcome,
    occurred_at: datetime,
    label_known_at: datetime,
    observed_bars: int,
    exit_price: float | None,
    reason: str,
    gap_through: bool = False,
    optimistic_exit_price: float | None = None,
) -> BarrierEvaluation:
    ambiguous = outcome is BarrierOutcome.AMBIGUOUS
    primary = BarrierOutcome.STOP if ambiguous else outcome
    optimistic = BarrierOutcome.TARGET if ambiguous else None
    binary = {
        BarrierOutcome.TARGET: 1,
        BarrierOutcome.STOP: 0,
        BarrierOutcome.TIMEOUT: 0,
        BarrierOutcome.AMBIGUOUS: 0,
        BarrierOutcome.CANCELLED: None,
    }[outcome]
    return BarrierEvaluation(
        setup_id=plan.setup_id,
        plan_digest=plan.digest(),
        outcome=outcome,
        primary_outcome=primary,
        optimistic_outcome=optimistic,
        occurred_at=occurred_at,
        label_known_at=label_known_at,
        observed_bars=observed_bars,
        exit_price=exit_price,
        optimistic_exit_price=optimistic_exit_price,
        gap_through=gap_through,
        same_bar_ambiguous=ambiguous,
        optimistic_target_possible=ambiguous,
        default_binary_label=binary,
        side_return_pct=(
            _side_return_pct(plan, exit_price) if exit_price is not None else None
        ),
        reason=reason,
    )


def _as_bar(value: MinuteBar | Mapping[str, Any]) -> MinuteBar:
    if isinstance(value, MinuteBar):
        return value
    if isinstance(value, Mapping):
        return MinuteBar.from_mapping(value)
    raise TypeError("bars must contain MinuteBar instances or mappings")


def _bar_interval(value: int) -> timedelta:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("bar_interval_seconds must be a positive integer")
    return timedelta(seconds=value)


@dataclass(slots=True)
class BarrierTracker:
    """Restart-safe incremental evaluator for one immutable barrier plan."""

    plan: BarrierPlan
    observed_bars: int = 0
    last_timestamp: datetime | None = None
    last_observation_at: datetime | None = None
    target_bars_elapsed: int = 0
    last_target_bar_open: datetime | None = None
    last_target_bar_observation_at: datetime | None = None
    terminal: BarrierEvaluation | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.plan, BarrierPlan):
            raise TypeError("plan must be a BarrierPlan")
        if isinstance(self.observed_bars, bool) or not isinstance(
            self.observed_bars, int
        ):
            raise ValueError("observed_bars must be a non-negative integer")
        if self.observed_bars < 0:
            raise ValueError("observed_bars must be non-negative")
        if (
            isinstance(self.target_bars_elapsed, bool)
            or not isinstance(self.target_bars_elapsed, int)
            or not 0 <= self.target_bars_elapsed <= self.plan.timeout_target_bars
        ):
            raise ValueError("target_bars_elapsed is outside the plan horizon")
        if self.last_timestamp is not None:
            self.last_timestamp = as_utc_datetime(
                self.last_timestamp, name="last_timestamp"
            )
        if self.last_observation_at is not None:
            self.last_observation_at = as_utc_datetime(
                self.last_observation_at,
                name="last_observation_at",
            )
        for name in ("last_target_bar_open", "last_target_bar_observation_at"):
            value = getattr(self, name)
            if value is not None:
                setattr(self, name, as_utc_datetime(value, name=name))
        if self.observed_bars == 0 and (
            self.last_timestamp is not None or self.last_observation_at is not None
        ):
            raise ValueError("tracker timestamps require an observed bar")
        if self.observed_bars > 0 and (
            self.last_timestamp is None or self.last_observation_at is None
        ):
            raise ValueError("observed bars require market and observation timestamps")
        if (
            self.last_timestamp is not None
            and self.last_timestamp < self.plan.activated_at
        ):
            raise ValueError("last_timestamp precedes plan activation")
        if (
            self.last_timestamp is not None
            and self.last_observation_at is not None
            and self.last_observation_at < self.last_timestamp
        ):
            raise ValueError("last_observation_at precedes the source bar")
        if (self.target_bars_elapsed == 0) != (self.last_target_bar_open is None):
            raise ValueError("target-bar progress requires last_target_bar_open")
        if (self.target_bars_elapsed == 0) != (
            self.last_target_bar_observation_at is None
        ):
            raise ValueError("target-bar progress requires its observation clock")
        if self.target_bars_elapsed > 0 and self.observed_bars == 0:
            raise ValueError("target-bar progress requires an observed execution bar")
        if (
            self.last_target_bar_open is not None
            and self.last_timestamp is not None
            and self.last_target_bar_open > self.last_timestamp
        ):
            raise ValueError("target-bar progress is ahead of execution observations")
        if (
            self.last_target_bar_observation_at is not None
            and self.last_observation_at is not None
            and self.last_target_bar_observation_at > self.last_observation_at
        ):
            raise ValueError("target-bar observation is ahead of the tracker clock")
        if (
            self.last_target_bar_open is not None
            and int(self.last_target_bar_open.timestamp())
            % self.plan.target_interval_seconds
            != 0
        ):
            raise ValueError("last_target_bar_open is not timeframe aligned")
        if self.terminal is not None:
            if not isinstance(self.terminal, BarrierEvaluation):
                raise TypeError("terminal must be a BarrierEvaluation")
            if self.terminal.setup_id != self.plan.setup_id:
                raise ValueError("terminal setup_id does not match plan")
            if self.terminal.plan_digest != self.plan.digest():
                raise ValueError("terminal plan_digest does not match plan")
            if self.terminal.observed_bars != self.observed_bars:
                raise ValueError("terminal observed_bars does not match tracker")
            if self.terminal.outcome is BarrierOutcome.TIMEOUT:
                expected_timeout_at = (
                    None
                    if self.last_target_bar_open is None
                    else self.last_target_bar_open
                    + timedelta(seconds=self.plan.target_interval_seconds)
                )
                if self.terminal.occurred_at != expected_timeout_at:
                    raise ValueError("timeout must occur at the counted target close")
            elif (
                self.terminal.outcome is not BarrierOutcome.CANCELLED
                and self.last_timestamp != self.terminal.occurred_at
            ):
                raise ValueError("terminal occurred_at must match last observed bar")
            if self.terminal.label_known_at != self.last_observation_at:
                raise ValueError("terminal label_known_at must match observation time")
        elif self.target_bars_elapsed == self.plan.timeout_target_bars:
            raise ValueError("tracker at its target-bar horizon must be terminal")

    def update(
        self,
        bar: MinuteBar | Mapping[str, Any],
        *,
        bar_interval_seconds: int = 60,
        observed_at: datetime | str | None = None,
    ) -> BarrierEvaluation | None:
        """Consume exactly one later bar and return a terminal result when known."""

        interval = _bar_interval(bar_interval_seconds)
        if self.terminal is not None:
            return self.terminal
        candidate = _as_bar(bar)
        if candidate.timestamp < self.plan.activated_at:
            raise ValueError("bar timestamp precedes barrier activation")
        if (
            self.last_timestamp is not None
            and candidate.timestamp <= self.last_timestamp
        ):
            raise ValueError("bars must be strictly increasing by timestamp")

        nominal_close = candidate.timestamp + interval
        known_at = (
            nominal_close
            if observed_at is None
            else as_utc_datetime(observed_at, name="observed_at")
        )
        if known_at < nominal_close:
            raise ValueError("observed_at predates finalized bar close")
        if self.last_observation_at is not None and known_at < self.last_observation_at:
            raise ValueError("observed_at must be non-decreasing")

        self.observed_bars += 1
        self.last_timestamp = candidate.timestamp
        self.last_observation_at = known_at
        if self.plan.side is TradeSide.LONG:
            gap_stop = candidate.open <= self.plan.stop_price
            gap_target = candidate.open >= self.plan.target_price
            stop_touched = candidate.low <= self.plan.stop_price
            target_touched = candidate.high >= self.plan.target_price
        else:
            gap_stop = candidate.open >= self.plan.stop_price
            gap_target = candidate.open <= self.plan.target_price
            stop_touched = candidate.high >= self.plan.stop_price
            target_touched = candidate.low <= self.plan.target_price

        result: BarrierEvaluation | None = None
        if gap_stop:
            result = _terminal(
                self.plan,
                outcome=BarrierOutcome.STOP,
                occurred_at=candidate.timestamp,
                label_known_at=known_at,
                observed_bars=self.observed_bars,
                exit_price=candidate.open,
                gap_through=True,
                reason="gap_through_stop",
            )
        elif gap_target:
            result = _terminal(
                self.plan,
                outcome=BarrierOutcome.TARGET,
                occurred_at=candidate.timestamp,
                label_known_at=known_at,
                observed_bars=self.observed_bars,
                exit_price=candidate.open,
                gap_through=True,
                reason="gap_through_target",
            )
        elif stop_touched and target_touched:
            result = _terminal(
                self.plan,
                outcome=BarrierOutcome.AMBIGUOUS,
                occurred_at=candidate.timestamp,
                label_known_at=known_at,
                observed_bars=self.observed_bars,
                exit_price=self.plan.stop_price,
                optimistic_exit_price=self.plan.target_price,
                reason="same_bar_both_barriers_stop_first_primary",
            )
        elif stop_touched:
            result = _terminal(
                self.plan,
                outcome=BarrierOutcome.STOP,
                occurred_at=candidate.timestamp,
                label_known_at=known_at,
                observed_bars=self.observed_bars,
                exit_price=self.plan.stop_price,
                reason="stop_touched",
            )
        elif target_touched:
            result = _terminal(
                self.plan,
                outcome=BarrierOutcome.TARGET,
                occurred_at=candidate.timestamp,
                label_known_at=known_at,
                observed_bars=self.observed_bars,
                exit_price=self.plan.target_price,
                reason="target_touched",
            )
        if result is not None:
            self.terminal = result
        return result

    def advance_target_bar(
        self,
        *,
        bar_open: datetime | str,
        close_price: float,
        observed_at: datetime | str,
    ) -> BarrierEvaluation | None:
        """Count one accepted finalized signal-timeframe candle toward expiry."""

        if self.terminal is not None:
            return self.terminal
        opened = as_utc_datetime(bar_open, name="target_bar_open")
        interval = timedelta(seconds=self.plan.target_interval_seconds)
        closed = opened + interval
        observed = as_utc_datetime(observed_at, name="observed_at")
        accepted_close = _finite_positive(close_price, name="target bar close")
        if int(opened.timestamp()) % self.plan.target_interval_seconds != 0:
            raise ValueError("target_bar_open is not timeframe aligned")
        if closed <= self.plan.activated_at:
            raise ValueError("target bar closed before barrier activation")
        if self.observed_bars == 0 or self.last_timestamp is None:
            raise ValueError("target bar requires an observed execution bar")
        if not opened <= self.last_timestamp < closed:
            raise ValueError("latest execution observation is outside the target bar")
        if observed < closed:
            raise ValueError("target bar was observed before its scheduled close")
        if (
            self.last_target_bar_open is not None
            and opened <= self.last_target_bar_open
        ):
            raise ValueError("target bars must be strictly increasing")
        if self.last_observation_at is not None and observed < self.last_observation_at:
            raise ValueError("target-bar observation clock moved backwards")

        self.target_bars_elapsed += 1
        self.last_target_bar_open = opened
        self.last_target_bar_observation_at = observed
        self.last_observation_at = observed
        if self.target_bars_elapsed < self.plan.timeout_target_bars:
            return None
        result = _terminal(
            self.plan,
            outcome=BarrierOutcome.TIMEOUT,
            occurred_at=closed,
            label_known_at=observed,
            observed_bars=self.observed_bars,
            exit_price=accepted_close,
            reason="maximum_finalized_target_bars_reached",
        )
        self.terminal = result
        return result

    def snapshot(self) -> dict[str, Any]:
        """Return a checksummed JSON-safe restart snapshot."""

        payload: dict[str, Any] = {
            "schema_version": TRACKER_SCHEMA_VERSION,
            "plan": self.plan.as_dict(),
            "observed_bars": self.observed_bars,
            "last_timestamp": (
                utc_iso(self.last_timestamp)
                if self.last_timestamp is not None
                else None
            ),
            "last_observation_at": (
                utc_iso(self.last_observation_at)
                if self.last_observation_at is not None
                else None
            ),
            "target_bars_elapsed": self.target_bars_elapsed,
            "last_target_bar_open": (
                utc_iso(self.last_target_bar_open)
                if self.last_target_bar_open is not None
                else None
            ),
            "last_target_bar_observation_at": (
                utc_iso(self.last_target_bar_observation_at)
                if self.last_target_bar_observation_at is not None
                else None
            ),
            "terminal": self.terminal.as_dict() if self.terminal is not None else None,
        }
        return {**payload, "checksum": stable_digest(payload)}

    @classmethod
    def from_snapshot(cls, payload: Mapping[str, Any]) -> BarrierTracker:
        """Restore a tracker after verifying snapshot integrity and invariants."""

        if payload.get("schema_version") != TRACKER_SCHEMA_VERSION:
            raise ValueError("unsupported barrier tracker schema_version")
        required = (
            "plan",
            "observed_bars",
            "last_timestamp",
            "last_observation_at",
            "target_bars_elapsed",
            "last_target_bar_open",
            "last_target_bar_observation_at",
            "terminal",
            "checksum",
        )
        missing = [key for key in required if key not in payload]
        if missing:
            raise ValueError(f"barrier tracker snapshot is missing {missing[0]!r}")
        unsigned = {
            "schema_version": payload["schema_version"],
            "plan": payload["plan"],
            "observed_bars": payload["observed_bars"],
            "last_timestamp": payload["last_timestamp"],
            "last_observation_at": payload["last_observation_at"],
            "target_bars_elapsed": payload["target_bars_elapsed"],
            "last_target_bar_open": payload["last_target_bar_open"],
            "last_target_bar_observation_at": payload["last_target_bar_observation_at"],
            "terminal": payload["terminal"],
        }
        if payload["checksum"] != stable_digest(unsigned):
            raise ValueError("barrier tracker snapshot checksum mismatch")
        if not isinstance(payload["plan"], Mapping):
            raise ValueError("barrier tracker plan must be a mapping")
        terminal_payload = payload["terminal"]
        if terminal_payload is not None and not isinstance(terminal_payload, Mapping):
            raise ValueError("barrier tracker terminal must be a mapping or null")
        return cls(
            plan=BarrierPlan.from_dict(payload["plan"]),
            observed_bars=payload["observed_bars"],
            last_timestamp=payload["last_timestamp"],
            last_observation_at=payload["last_observation_at"],
            target_bars_elapsed=payload["target_bars_elapsed"],
            last_target_bar_open=payload["last_target_bar_open"],
            last_target_bar_observation_at=payload["last_target_bar_observation_at"],
            terminal=(
                BarrierEvaluation.from_dict(terminal_payload)
                if terminal_payload is not None
                else None
            ),
        )

    def digest(self) -> str:
        return str(self.snapshot()["checksum"])


def evaluate_barriers(
    plan: BarrierPlan,
    bars: Iterable[MinuteBar | Mapping[str, Any]],
    *,
    bar_interval_seconds: int = 60,
) -> BarrierEvaluation | None:
    """Evaluate a protected setup against causally ordered post-fill bars.

    Gap-through exits execute at the bar open.  If both barriers are inside one
    otherwise non-gapped OHLC bar, the label remains ``AMBIGUOUS`` and the
    conservative primary result is ``STOP``. ``None`` means no supplied bar
    reaches a horizontal barrier. The selected-timeframe orchestrator must call
    :meth:`BarrierTracker.advance_target_bar` for every accepted finalized
    target candle; raw execution-bar density never defines the timeout. Without
    an explicit ``observed_at`` clock, OHLC-derived labels become known at the
    nominal finalized bar close.
    """

    _bar_interval(bar_interval_seconds)
    tracker = BarrierTracker(plan=plan)
    for value in bars:
        result = tracker.update(value, bar_interval_seconds=bar_interval_seconds)
        if result is not None:
            return result
    return None


def cancel_barrier_plan(
    plan: BarrierPlan,
    *,
    cancelled_at: datetime | str,
    observed_at: datetime | str | None = None,
    reason: str = "cancelled_before_terminal_barrier",
    observed_bars: int = 0,
) -> BarrierEvaluation:
    """Create an explicit non-training cancellation result for a live plan."""

    timestamp = as_utc_datetime(cancelled_at, name="cancelled_at")
    if timestamp < plan.activated_at:
        raise ValueError("cancelled_at must not precede barrier activation")
    known_at = (
        timestamp
        if observed_at is None
        else as_utc_datetime(observed_at, name="observed_at")
    )
    if known_at < timestamp:
        raise ValueError("observed_at must not precede cancelled_at")
    if isinstance(observed_bars, bool) or not isinstance(observed_bars, int):
        raise ValueError("observed_bars must be a non-negative integer")
    if observed_bars < 0:
        raise ValueError("observed_bars must be a non-negative integer")
    return _terminal(
        plan,
        outcome=BarrierOutcome.CANCELLED,
        occurred_at=timestamp,
        label_known_at=known_at,
        observed_bars=observed_bars,
        exit_price=None,
        reason=reason,
    )


__all__ = [
    "LABEL_SCHEMA_VERSION",
    "TRACKER_SCHEMA_VERSION",
    "BarrierEvaluation",
    "BarrierTracker",
    "MinuteBar",
    "cancel_barrier_plan",
    "evaluate_barriers",
]
