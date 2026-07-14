"""Restart-safe shadow event book for causal CUSUM meta labels.

The book intentionally does not place orders or make trading decisions.  It
captures an immutable setup at its decision boundary, applies a declared
adverse entry assumption at the first eligible real one-minute open, and then
delegates every exit/timeout decision to :class:`BarrierTracker`.  The same
component can therefore consume historical prefixes or finalized live minutes
without defining a second set of barrier semantics.
"""

from __future__ import annotations

import math
from collections import OrderedDict, deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from threading import RLock
from typing import Any

from .contracts import (
    BarrierConfig,
    BarrierOutcome,
    BarrierPlan,
    TradeSide,
    activate_barrier_plan,
    as_utc_datetime,
    stable_digest,
    utc_iso,
)
from .economics import barrier_net_return_bps
from .features import FEATURE_SCHEMA_VERSION, FeatureSnapshot
from .labeling import BarrierEvaluation, BarrierTracker, MinuteBar

SHADOW_SCHEMA_VERSION = "cusum_meta_shadow_book_v2"
SHADOW_CANDIDATE_SCHEMA_VERSION = "cusum_meta_shadow_candidate_v2"
SHADOW_RECORD_SCHEMA_VERSION = "cusum_meta_shadow_record_v2"
EXECUTION_BAR_INTERVAL_SECONDS = 60


class ShadowGapPolicy(str, Enum):
    """Entry behavior when the exact eligible minute is not a real bar."""

    CONTINUOUS_CANCEL = "CONTINUOUS_CANCEL"
    SESSION_NEXT_OPEN = "SESSION_NEXT_OPEN"


class ShadowEventState(str, Enum):
    """Lifecycle state exposed by the shadow book."""

    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    RESOLVED = "RESOLVED"


class ShadowBookCapacityError(RuntimeError):
    """Raised instead of silently discarding a pending or active setup."""


def _required_text(value: Any, *, name: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{name} must not be empty")
    return text


def _positive(value: Any, *, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite positive number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite positive number") from exc
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(f"{name} must be a finite positive number")
    return number


def _nonnegative(value: Any, *, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite non-negative number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite non-negative number") from exc
    if not math.isfinite(number) or number < 0.0:
        raise ValueError(f"{name} must be a finite non-negative number")
    return number


def _positive_int(value: Any, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _feature_snapshot_from_dict(payload: Mapping[str, Any]) -> FeatureSnapshot:
    if payload.get("schema_version") != FEATURE_SCHEMA_VERSION:
        raise ValueError("unsupported feature snapshot schema_version")
    try:
        names = tuple(payload["feature_names"])
        values = tuple(payload["values"])
        snapshot = FeatureSnapshot(
            setup_id=payload["setup_id"],
            side=payload["side"],
            decision_at=payload["decision_at"],
            online_source_timestamp=payload["online_source_timestamp"],
            online_available_at=payload["online_available_at"],
            cusum_source_timestamp=payload["cusum_source_timestamp"],
            cusum_available_at=payload["cusum_available_at"],
            online_status=payload["online_status"],
            cusum_status=payload["cusum_status"],
            feature_names=names,
            values=values,
        )
    except KeyError as exc:
        raise ValueError(f"feature snapshot is missing {exc.args[0]!r}") from exc
    redundant = payload.get("features")
    if redundant is not None:
        if not isinstance(redundant, Mapping):
            raise ValueError("feature snapshot features must be a mapping")
        if dict(redundant) != snapshot.feature_map():
            raise ValueError("feature snapshot values disagree with features mapping")
    return snapshot


@dataclass(frozen=True, slots=True)
class ShadowCandidate:
    """Immutable setup captured before any post-decision minute is inspected."""

    event_id: str
    setup_id: str
    asset: str
    timeframe: str
    decision_at: datetime
    eligible_at: datetime
    side: TradeSide
    entry_reference: float
    risk_unit: float
    features: FeatureSnapshot
    barrier_config: BarrierConfig
    policy_digest: str
    estimated_roundtrip_cost_bps: float
    adverse_entry_bps: float = 0.0
    gap_policy: ShadowGapPolicy = ShadowGapPolicy.CONTINUOUS_CANCEL

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "event_id", _required_text(self.event_id, name="event_id")
        )
        object.__setattr__(
            self, "setup_id", _required_text(self.setup_id, name="setup_id")
        )
        object.__setattr__(
            self, "asset", _required_text(self.asset, name="asset").upper()
        )
        object.__setattr__(
            self, "timeframe", _required_text(self.timeframe, name="timeframe").lower()
        )
        object.__setattr__(
            self,
            "decision_at",
            as_utc_datetime(self.decision_at, name="decision_at"),
        )
        object.__setattr__(
            self,
            "eligible_at",
            as_utc_datetime(self.eligible_at, name="eligible_at"),
        )
        if self.eligible_at < self.decision_at:
            raise ValueError("eligible_at must not precede decision_at")
        try:
            side = (
                self.side if isinstance(self.side, TradeSide) else TradeSide(self.side)
            )
        except ValueError as exc:
            raise ValueError("side must be LONG or SHORT") from exc
        object.__setattr__(self, "side", side)
        object.__setattr__(
            self,
            "entry_reference",
            _positive(self.entry_reference, name="entry_reference"),
        )
        object.__setattr__(
            self, "risk_unit", _positive(self.risk_unit, name="risk_unit")
        )
        if not isinstance(self.features, FeatureSnapshot):
            raise TypeError("features must be a FeatureSnapshot")
        if not isinstance(self.barrier_config, BarrierConfig):
            raise TypeError("barrier_config must be a BarrierConfig")
        object.__setattr__(
            self,
            "policy_digest",
            _required_text(self.policy_digest, name="policy_digest"),
        )
        object.__setattr__(
            self,
            "estimated_roundtrip_cost_bps",
            _nonnegative(
                self.estimated_roundtrip_cost_bps,
                name="estimated_roundtrip_cost_bps",
            ),
        )
        adverse = _nonnegative(self.adverse_entry_bps, name="adverse_entry_bps")
        if adverse >= 10_000.0:
            raise ValueError("adverse_entry_bps must be below 10000")
        if adverse > self.estimated_roundtrip_cost_bps:
            raise ValueError(
                "adverse_entry_bps cannot exceed estimated_roundtrip_cost_bps"
            )
        object.__setattr__(self, "adverse_entry_bps", adverse)
        try:
            gap_policy = (
                self.gap_policy
                if isinstance(self.gap_policy, ShadowGapPolicy)
                else ShadowGapPolicy(self.gap_policy)
            )
        except ValueError as exc:
            raise ValueError("invalid gap_policy") from exc
        object.__setattr__(self, "gap_policy", gap_policy)

        if self.features.setup_id != self.setup_id:
            raise ValueError("feature setup_id does not match candidate setup_id")
        if self.features.side is not self.side:
            raise ValueError("feature side does not match candidate side")
        if self.features.decision_at != self.decision_at:
            raise ValueError("feature decision_at does not match candidate decision_at")
        expected_features = {
            "risk_unit_fraction": self.risk_unit / self.entry_reference,
            "stop_risk_units": self.barrier_config.stop_risk_units,
            "target_risk_units": self.barrier_config.target_risk_units,
            "timeout_horizon_minutes_log1p": math.log1p(
                self.barrier_config.timeout_target_bars
                * self.barrier_config.target_interval_seconds
                / 60.0
            ),
            "estimated_roundtrip_cost_bps": self.estimated_roundtrip_cost_bps,
        }
        feature_map = self.features.feature_map()
        for name, expected in expected_features.items():
            actual = feature_map[name]
            if actual is None or not math.isclose(
                actual, expected, rel_tol=1e-12, abs_tol=1e-12
            ):
                raise ValueError(f"feature {name} does not match candidate policy")

    @property
    def execution_policy_digest(self) -> str:
        """Digest binding risk, cost, gap, and fill assumptions."""

        return stable_digest(
            {
                "barrier_config_digest": self.barrier_config.digest(),
                "policy_digest": self.policy_digest,
                "estimated_roundtrip_cost_bps": self.estimated_roundtrip_cost_bps,
                "adverse_entry_bps": self.adverse_entry_bps,
                "gap_policy": self.gap_policy.value,
            }
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SHADOW_CANDIDATE_SCHEMA_VERSION,
            "event_id": self.event_id,
            "setup_id": self.setup_id,
            "asset": self.asset,
            "timeframe": self.timeframe,
            "decision_at": utc_iso(self.decision_at),
            "eligible_at": utc_iso(self.eligible_at),
            "side": self.side.value,
            "entry_reference": self.entry_reference,
            "risk_unit": self.risk_unit,
            "features": self.features.as_dict(),
            "feature_digest": self.features.digest(),
            "barrier_config": self.barrier_config.as_dict(),
            "barrier_config_digest": self.barrier_config.digest(),
            "policy_digest": self.policy_digest,
            "execution_policy_digest": self.execution_policy_digest,
            "estimated_roundtrip_cost_bps": self.estimated_roundtrip_cost_bps,
            "adverse_entry_bps": self.adverse_entry_bps,
            "gap_policy": self.gap_policy.value,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ShadowCandidate:
        if payload.get("schema_version") != SHADOW_CANDIDATE_SCHEMA_VERSION:
            raise ValueError("unsupported shadow candidate schema_version")
        try:
            feature_payload = payload["features"]
            config_payload = payload["barrier_config"]
            if not isinstance(feature_payload, Mapping):
                raise ValueError("candidate features must be a mapping")
            if not isinstance(config_payload, Mapping):
                raise ValueError("candidate barrier_config must be a mapping")
            candidate = cls(
                event_id=payload["event_id"],
                setup_id=payload["setup_id"],
                asset=payload["asset"],
                timeframe=payload["timeframe"],
                decision_at=payload["decision_at"],
                eligible_at=payload["eligible_at"],
                side=payload["side"],
                entry_reference=payload["entry_reference"],
                risk_unit=payload["risk_unit"],
                features=_feature_snapshot_from_dict(feature_payload),
                barrier_config=BarrierConfig.from_dict(config_payload),
                policy_digest=payload["policy_digest"],
                estimated_roundtrip_cost_bps=payload["estimated_roundtrip_cost_bps"],
                adverse_entry_bps=payload["adverse_entry_bps"],
                gap_policy=payload["gap_policy"],
            )
        except KeyError as exc:
            raise ValueError(f"shadow candidate is missing {exc.args[0]!r}") from exc
        expected = {
            "feature_digest": candidate.features.digest(),
            "barrier_config_digest": candidate.barrier_config.digest(),
            "execution_policy_digest": candidate.execution_policy_digest,
        }
        for key, value in expected.items():
            if payload.get(key) != value:
                raise ValueError(f"shadow candidate {key} mismatch")
        return candidate

    def digest(self) -> str:
        return stable_digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class ShadowExecutionMinute:
    """A finalized execution-minute observation, real or synthetic."""

    asset: str
    bar: MinuteBar
    observed_at: datetime | None = None
    is_real: bool = True
    scheduled_session_gap: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "asset", _required_text(self.asset, name="asset").upper()
        )
        if not isinstance(self.bar, MinuteBar):
            raise TypeError("bar must be a MinuteBar")
        nominal_close = self.bar.timestamp + timedelta(
            seconds=EXECUTION_BAR_INTERVAL_SECONDS
        )
        observed_at = (
            nominal_close
            if self.observed_at is None
            else as_utc_datetime(self.observed_at, name="observed_at")
        )
        if observed_at < nominal_close:
            raise ValueError("observed_at predates finalized execution minute")
        object.__setattr__(self, "observed_at", observed_at)
        if not isinstance(self.is_real, bool):
            raise ValueError("is_real must be boolean")
        if not isinstance(self.scheduled_session_gap, bool):
            raise ValueError("scheduled_session_gap must be boolean")
        if self.scheduled_session_gap and not self.is_real:
            raise ValueError("scheduled_session_gap requires a real observation")

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> ShadowExecutionMinute:
        try:
            if "is_real" in payload:
                is_real = payload["is_real"]
            elif "is_synthetic" in payload:
                synthetic = payload["is_synthetic"]
                if not isinstance(synthetic, bool):
                    raise ValueError("is_synthetic must be boolean")
                is_real = not synthetic
            else:
                is_real = True
            if not isinstance(is_real, bool):
                raise ValueError("is_real must be boolean")
            return cls(
                asset=payload["asset"],
                bar=MinuteBar.from_mapping(payload),
                observed_at=payload.get("observed_at"),
                is_real=is_real,
                scheduled_session_gap=payload.get(
                    "scheduled_session_gap_verified", False
                ),
            )
        except KeyError as exc:
            raise ValueError(f"execution minute is missing {exc.args[0]!r}") from exc

    def as_dict(self) -> dict[str, Any]:
        assert self.observed_at is not None
        return {
            "asset": self.asset,
            **self.bar.as_dict(),
            "observed_at": utc_iso(self.observed_at),
            "is_real": self.is_real,
            "scheduled_session_gap_verified": self.scheduled_session_gap,
        }


@dataclass(frozen=True, slots=True)
class ShadowFill:
    """Actual shadow entry created from a real minute open."""

    event_id: str
    filled_at: datetime
    source_open: float
    adverse_entry_bps: float
    fill_price: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "event_id", _required_text(self.event_id, name="event_id")
        )
        object.__setattr__(
            self, "filled_at", as_utc_datetime(self.filled_at, name="filled_at")
        )
        object.__setattr__(
            self, "source_open", _positive(self.source_open, name="source_open")
        )
        object.__setattr__(
            self,
            "adverse_entry_bps",
            _nonnegative(self.adverse_entry_bps, name="adverse_entry_bps"),
        )
        object.__setattr__(
            self, "fill_price", _positive(self.fill_price, name="fill_price")
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "filled_at": utc_iso(self.filled_at),
            "source_open": self.source_open,
            "adverse_entry_bps": self.adverse_entry_bps,
            "fill_price": self.fill_price,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ShadowFill:
        try:
            return cls(
                event_id=payload["event_id"],
                filled_at=payload["filled_at"],
                source_open=payload["source_open"],
                adverse_entry_bps=payload["adverse_entry_bps"],
                fill_price=payload["fill_price"],
            )
        except KeyError as exc:
            raise ValueError(f"shadow fill is missing {exc.args[0]!r}") from exc


@dataclass(frozen=True, slots=True)
class ShadowEventRecord:
    """JSON-safe view of one pending, active, or resolved setup."""

    candidate: ShadowCandidate
    state: ShadowEventState
    fill: ShadowFill | None = None
    plan: BarrierPlan | None = None
    evaluation: BarrierEvaluation | None = None
    outcome: BarrierOutcome | None = None
    occurred_at: datetime | None = None
    label_known_at: datetime | None = None
    reason: str | None = None
    observed_bars: int = 0
    last_observed_at: datetime | None = None
    last_observation_at: datetime | None = None
    target_bars_elapsed: int = 0
    last_target_bar_open: datetime | None = None
    last_target_bar_observation_at: datetime | None = None
    gross_return_bps: float | None = None
    embedded_entry_execution_bps: float | None = None
    deducted_cost_bps: float | None = None
    net_return_bps: float | None = None
    economic_binary_target: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.candidate, ShadowCandidate):
            raise TypeError("candidate must be a ShadowCandidate")
        try:
            state = (
                self.state
                if isinstance(self.state, ShadowEventState)
                else ShadowEventState(self.state)
            )
        except ValueError as exc:
            raise ValueError("invalid shadow event state") from exc
        object.__setattr__(self, "state", state)
        if isinstance(self.observed_bars, bool) or not isinstance(
            self.observed_bars, int
        ):
            raise ValueError("observed_bars must be a non-negative integer")
        if self.observed_bars < 0:
            raise ValueError("observed_bars must be a non-negative integer")
        if (
            isinstance(self.target_bars_elapsed, bool)
            or not isinstance(self.target_bars_elapsed, int)
            or self.target_bars_elapsed < 0
        ):
            raise ValueError("target_bars_elapsed must be a non-negative integer")
        for name in (
            "last_observed_at",
            "last_observation_at",
            "last_target_bar_open",
            "last_target_bar_observation_at",
        ):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(
                    self,
                    name,
                    as_utc_datetime(value, name=name),
                )
        for name in ("occurred_at", "label_known_at"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, as_utc_datetime(value, name=name))
        if self.target_bars_elapsed > self.candidate.barrier_config.timeout_target_bars:
            raise ValueError("target_bars_elapsed exceeds the candidate horizon")
        if (self.target_bars_elapsed == 0) != (self.last_target_bar_open is None):
            raise ValueError("target-bar progress requires last_target_bar_open")
        if (self.target_bars_elapsed == 0) != (
            self.last_target_bar_observation_at is None
        ):
            raise ValueError("target-bar progress requires its observation clock")
        if self.label_known_at is not None and self.occurred_at is not None:
            if self.label_known_at < self.occurred_at:
                raise ValueError("label_known_at must not precede occurred_at")
        if self.outcome is not None:
            try:
                outcome = (
                    self.outcome
                    if isinstance(self.outcome, BarrierOutcome)
                    else BarrierOutcome(self.outcome)
                )
            except ValueError as exc:
                raise ValueError("invalid barrier outcome") from exc
            object.__setattr__(self, "outcome", outcome)
        if self.fill is not None and not isinstance(self.fill, ShadowFill):
            raise TypeError("fill must be a ShadowFill or None")
        if self.plan is not None and not isinstance(self.plan, BarrierPlan):
            raise TypeError("plan must be a BarrierPlan or None")
        if self.evaluation is not None and not isinstance(
            self.evaluation, BarrierEvaluation
        ):
            raise TypeError("evaluation must be a BarrierEvaluation or None")

        if state is ShadowEventState.PENDING:
            if (
                any(
                    value is not None
                    for value in (
                        self.fill,
                        self.plan,
                        self.evaluation,
                        self.outcome,
                        self.occurred_at,
                        self.label_known_at,
                        self.reason,
                        self.last_observed_at,
                        self.last_observation_at,
                        self.last_target_bar_open,
                        self.last_target_bar_observation_at,
                        self.gross_return_bps,
                        self.embedded_entry_execution_bps,
                        self.deducted_cost_bps,
                        self.net_return_bps,
                        self.economic_binary_target,
                    )
                )
                or self.observed_bars != 0
                or self.target_bars_elapsed != 0
            ):
                raise ValueError("pending records cannot contain execution state")
            return

        if state is ShadowEventState.ACTIVE:
            if self.fill is None or self.plan is None:
                raise ValueError("active records require an actual fill and plan")
            if any(
                value is not None
                for value in (
                    self.evaluation,
                    self.outcome,
                    self.occurred_at,
                    self.label_known_at,
                    self.reason,
                    self.gross_return_bps,
                    self.embedded_entry_execution_bps,
                    self.deducted_cost_bps,
                    self.net_return_bps,
                    self.economic_binary_target,
                )
            ):
                raise ValueError("active records cannot contain terminal state")
            self._validate_fill_and_plan()
            return

        if self.outcome is None or self.occurred_at is None:
            raise ValueError("resolved records require outcome and occurred_at")
        if self.label_known_at is None or not _required_text(
            self.reason, name="reason"
        ):
            raise ValueError("resolved records require label_known_at and reason")
        if self.outcome is BarrierOutcome.CANCELLED:
            if self.evaluation is not None or any(
                value is not None
                for value in (
                    self.gross_return_bps,
                    self.net_return_bps,
                    self.economic_binary_target,
                )
            ):
                raise ValueError("cancelled records cannot contain a training label")
            if self.fill is None:
                if (
                    self.plan is not None
                    or self.last_observed_at is not None
                    or self.last_observation_at is not None
                    or self.observed_bars != 0
                    or self.target_bars_elapsed != 0
                    or self.last_target_bar_open is not None
                    or self.last_target_bar_observation_at is not None
                ):
                    raise ValueError(
                        "pre-fill cancellations cannot contain execution state"
                    )
            else:
                if self.plan is None:
                    raise ValueError("post-fill cancellations require the actual plan")
                self._validate_fill_and_plan()
                if self.occurred_at < self.fill.filled_at:
                    raise ValueError("post-fill cancellation precedes the actual fill")
                if (self.observed_bars == 0) != (self.last_observed_at is None):
                    raise ValueError(
                        "cancelled tracker progress requires matching last_observed_at"
                    )
                if (self.observed_bars == 0) != (self.last_observation_at is None):
                    raise ValueError(
                        "cancelled tracker progress requires observation timestamp"
                    )
            return

        if self.fill is None or self.plan is None or self.evaluation is None:
            raise ValueError("barrier resolutions require fill, plan, and evaluation")
        self._validate_fill_and_plan()
        if self.evaluation.outcome is not self.outcome:
            raise ValueError("evaluation outcome does not match record outcome")
        if self.evaluation.occurred_at != self.occurred_at:
            raise ValueError("evaluation occurred_at does not match record")
        if self.evaluation.label_known_at != self.label_known_at:
            raise ValueError("evaluation label_known_at does not match record")
        if self.evaluation.reason != self.reason:
            raise ValueError("evaluation reason does not match record")
        if self.evaluation.plan_digest != self.plan.digest():
            raise ValueError("evaluation plan does not match record plan")
        if self.observed_bars != self.evaluation.observed_bars:
            raise ValueError("record observed_bars does not match evaluation")
        if (
            self.outcome is not BarrierOutcome.TIMEOUT
            and self.last_observed_at != self.evaluation.occurred_at
        ):
            raise ValueError("record last_observed_at does not match evaluation")
        if self.last_observation_at != self.evaluation.label_known_at:
            raise ValueError("record observation timestamp does not match evaluation")
        if self.evaluation.side_return_pct is None:
            raise ValueError("resolved barrier evaluation requires a side return")
        expected_gross, expected_deducted, expected_net = barrier_net_return_bps(
            side_return_pct=self.evaluation.side_return_pct,
            roundtrip_cost_bps=self.candidate.estimated_roundtrip_cost_bps,
            embedded_entry_execution_bps=self.candidate.adverse_entry_bps,
        )
        for name, value, expected in (
            ("gross_return_bps", self.gross_return_bps, expected_gross),
            (
                "embedded_entry_execution_bps",
                self.embedded_entry_execution_bps,
                self.candidate.adverse_entry_bps,
            ),
            ("deducted_cost_bps", self.deducted_cost_bps, expected_deducted),
            ("net_return_bps", self.net_return_bps, expected_net),
        ):
            if (
                value is None
                or not math.isfinite(float(value))
                or not math.isclose(float(value), expected, rel_tol=1e-12, abs_tol=1e-9)
            ):
                raise ValueError(f"{name} is inconsistent with the barrier result")
            object.__setattr__(self, name, float(value))
        expected_economic = int(
            self.outcome is BarrierOutcome.TARGET and expected_net > 0.0
        )
        if isinstance(self.economic_binary_target, bool) or (
            self.economic_binary_target != expected_economic
        ):
            raise ValueError("economic_binary_target is inconsistent with outcome/cost")

    def _validate_fill_and_plan(self) -> None:
        assert self.fill is not None and self.plan is not None
        if self.fill.event_id != self.candidate.event_id:
            raise ValueError("fill event_id does not match candidate")
        if self.fill.adverse_entry_bps != self.candidate.adverse_entry_bps:
            raise ValueError("fill adverse_entry_bps does not match candidate")
        if self.fill.filled_at < self.candidate.eligible_at:
            raise ValueError("fill precedes candidate eligibility")
        if (
            self.candidate.gap_policy is ShadowGapPolicy.CONTINUOUS_CANCEL
            and self.fill.filled_at != self.candidate.eligible_at
        ):
            raise ValueError("continuous-market fill must occur at exact eligibility")
        if self.plan.setup_id != self.candidate.setup_id:
            raise ValueError("plan setup_id does not match candidate")
        if self.plan.side is not self.candidate.side:
            raise ValueError("plan side does not match candidate")
        if self.plan.activated_at != self.fill.filled_at:
            raise ValueError("plan activation does not match actual fill time")
        if self.plan.fill_price != self.fill.fill_price:
            raise ValueError("plan price does not match actual fill")
        if self.plan.risk_unit != self.candidate.risk_unit:
            raise ValueError("plan risk unit does not match candidate")
        if self.plan.config_digest != self.candidate.barrier_config.digest():
            raise ValueError("plan barrier policy does not match candidate")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SHADOW_RECORD_SCHEMA_VERSION,
            "event_id": self.candidate.event_id,
            "candidate": self.candidate.as_dict(),
            "candidate_digest": self.candidate.digest(),
            "state": self.state.value,
            "fill": self.fill.as_dict() if self.fill is not None else None,
            "plan": self.plan.as_dict() if self.plan is not None else None,
            "evaluation": (
                self.evaluation.as_dict() if self.evaluation is not None else None
            ),
            "outcome": self.outcome.value if self.outcome is not None else None,
            "occurred_at": (
                utc_iso(self.occurred_at) if self.occurred_at is not None else None
            ),
            "label_known_at": (
                utc_iso(self.label_known_at)
                if self.label_known_at is not None
                else None
            ),
            "reason": self.reason,
            "observed_bars": self.observed_bars,
            "last_observed_at": (
                utc_iso(self.last_observed_at)
                if self.last_observed_at is not None
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
            "gross_return_bps": self.gross_return_bps,
            "embedded_entry_execution_bps": self.embedded_entry_execution_bps,
            "deducted_cost_bps": self.deducted_cost_bps,
            "net_return_bps": self.net_return_bps,
            "economic_binary_target": self.economic_binary_target,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ShadowEventRecord:
        if payload.get("schema_version") != SHADOW_RECORD_SCHEMA_VERSION:
            raise ValueError("unsupported shadow event record schema_version")
        try:
            candidate_payload = payload["candidate"]
            if not isinstance(candidate_payload, Mapping):
                raise ValueError("record candidate must be a mapping")
            candidate = ShadowCandidate.from_dict(candidate_payload)
            fill_payload = payload.get("fill")
            plan_payload = payload.get("plan")
            evaluation_payload = payload.get("evaluation")
            for name, value in (
                ("fill", fill_payload),
                ("plan", plan_payload),
                ("evaluation", evaluation_payload),
            ):
                if value is not None and not isinstance(value, Mapping):
                    raise ValueError(f"record {name} must be a mapping or null")
            record = cls(
                candidate=candidate,
                state=payload["state"],
                fill=(
                    ShadowFill.from_dict(fill_payload)
                    if fill_payload is not None
                    else None
                ),
                plan=(
                    BarrierPlan.from_dict(plan_payload)
                    if plan_payload is not None
                    else None
                ),
                evaluation=(
                    BarrierEvaluation.from_dict(evaluation_payload)
                    if evaluation_payload is not None
                    else None
                ),
                outcome=payload.get("outcome"),
                occurred_at=payload.get("occurred_at"),
                label_known_at=payload.get("label_known_at"),
                reason=payload.get("reason"),
                observed_bars=payload["observed_bars"],
                last_observed_at=payload.get("last_observed_at"),
                last_observation_at=payload.get("last_observation_at"),
                target_bars_elapsed=payload.get("target_bars_elapsed", 0),
                last_target_bar_open=payload.get("last_target_bar_open"),
                last_target_bar_observation_at=payload.get(
                    "last_target_bar_observation_at"
                ),
                gross_return_bps=payload.get("gross_return_bps"),
                embedded_entry_execution_bps=payload.get(
                    "embedded_entry_execution_bps"
                ),
                deducted_cost_bps=payload.get("deducted_cost_bps"),
                net_return_bps=payload.get("net_return_bps"),
                economic_binary_target=payload.get("economic_binary_target"),
            )
        except KeyError as exc:
            raise ValueError(f"shadow event record is missing {exc.args[0]!r}") from exc
        if payload.get("event_id") != candidate.event_id:
            raise ValueError("record event_id does not match candidate")
        if payload.get("candidate_digest") != candidate.digest():
            raise ValueError("record candidate_digest mismatch")
        return record


@dataclass(slots=True)
class _OpenRuntime:
    candidate: ShadowCandidate
    fill: ShadowFill | None = None
    tracker: BarrierTracker | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.candidate, ShadowCandidate):
            raise TypeError("candidate must be a ShadowCandidate")
        if (self.fill is None) != (self.tracker is None):
            raise ValueError("fill and tracker must be both present or both absent")
        if self.tracker is not None:
            if self.tracker.terminal is not None:
                raise ValueError("open runtime tracker cannot already be terminal")
            ShadowEventRecord(
                candidate=self.candidate,
                state=ShadowEventState.ACTIVE,
                fill=self.fill,
                plan=self.tracker.plan,
                observed_bars=self.tracker.observed_bars,
                last_observed_at=self.tracker.last_timestamp,
                last_observation_at=self.tracker.last_observation_at,
                target_bars_elapsed=self.tracker.target_bars_elapsed,
                last_target_bar_open=self.tracker.last_target_bar_open,
                last_target_bar_observation_at=(
                    self.tracker.last_target_bar_observation_at
                ),
            )

    def record(self) -> ShadowEventRecord:
        if self.tracker is None:
            return ShadowEventRecord(
                candidate=self.candidate, state=ShadowEventState.PENDING
            )
        return ShadowEventRecord(
            candidate=self.candidate,
            state=ShadowEventState.ACTIVE,
            fill=self.fill,
            plan=self.tracker.plan,
            observed_bars=self.tracker.observed_bars,
            last_observed_at=self.tracker.last_timestamp,
            last_observation_at=self.tracker.last_observation_at,
            target_bars_elapsed=self.tracker.target_bars_elapsed,
            last_target_bar_open=self.tracker.last_target_bar_open,
            last_target_bar_observation_at=(
                self.tracker.last_target_bar_observation_at
            ),
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "candidate": self.candidate.as_dict(),
            "fill": self.fill.as_dict() if self.fill is not None else None,
            "tracker": self.tracker.snapshot() if self.tracker is not None else None,
        }

    @classmethod
    def from_snapshot(cls, payload: Mapping[str, Any]) -> _OpenRuntime:
        try:
            candidate_payload = payload["candidate"]
            fill_payload = payload["fill"]
            tracker_payload = payload["tracker"]
        except KeyError as exc:
            raise ValueError(f"open runtime is missing {exc.args[0]!r}") from exc
        for name, value in (
            ("candidate", candidate_payload),
            ("fill", fill_payload),
            ("tracker", tracker_payload),
        ):
            if value is not None and not isinstance(value, Mapping):
                raise ValueError(f"open runtime {name} must be a mapping or null")
        if candidate_payload is None:
            raise ValueError("open runtime candidate cannot be null")
        return cls(
            candidate=ShadowCandidate.from_dict(candidate_payload),
            fill=(
                ShadowFill.from_dict(fill_payload) if fill_payload is not None else None
            ),
            tracker=(
                BarrierTracker.from_snapshot(tracker_payload)
                if tracker_payload is not None
                else None
            ),
        )


class ShadowEventBook:
    """Bounded collection of overlapping causal shadow-label candidates."""

    def __init__(
        self,
        *,
        max_open_events: int = 10_000,
        max_resolved_records: int = 10_000,
    ) -> None:
        self.max_open_events = _positive_int(max_open_events, name="max_open_events")
        self.max_resolved_records = _positive_int(
            max_resolved_records, name="max_resolved_records"
        )
        self._open: OrderedDict[str, _OpenRuntime] = OrderedDict()
        self._resolved: deque[ShadowEventRecord] = deque()
        self._candidate_digests: dict[str, str] = {}
        self._cursor_by_asset: dict[str, datetime] = {}
        self.total_scheduled = 0
        self.total_filled = 0
        self.total_resolved = 0
        self.outcome_counts: dict[str, int] = {
            outcome.value: 0 for outcome in BarrierOutcome
        }
        self._lock = RLock()

    def schedule(self, candidate: ShadowCandidate) -> ShadowEventRecord:
        """Schedule a setup, treating an exact duplicate event as idempotent."""

        if not isinstance(candidate, ShadowCandidate):
            raise TypeError("candidate must be a ShadowCandidate")
        with self._lock:
            existing_digest = self._candidate_digests.get(candidate.event_id)
            if existing_digest is not None:
                if existing_digest != candidate.digest():
                    raise ValueError(
                        "event_id already exists with a different candidate digest"
                    )
                existing = self._record_by_id(candidate.event_id)
                if existing is None:  # Defensive invariant; should never be reachable.
                    raise RuntimeError("candidate digest index is inconsistent")
                return existing
            cursor = self._cursor_by_asset.get(candidate.asset)
            if cursor is not None and candidate.eligible_at <= cursor:
                raise ValueError("candidate eligibility is not after the asset cursor")
            if len(self._open) >= self.max_open_events:
                raise ShadowBookCapacityError(
                    "max_open_events reached; pending/active events are never evicted"
                )
            runtime = _OpenRuntime(candidate=candidate)
            self._open[candidate.event_id] = runtime
            self._candidate_digests[candidate.event_id] = candidate.digest()
            self.total_scheduled += 1
            return runtime.record()

    def update(
        self, minute: ShadowExecutionMinute | Mapping[str, Any]
    ) -> tuple[ShadowEventRecord, ...]:
        """Consume one finalized minute and update every overlapping asset setup.

        Returned records are the final state of events changed by this minute.
        A fill which also touches a barrier on the same minute is returned once
        as ``RESOLVED``.
        """

        observation = (
            minute
            if isinstance(minute, ShadowExecutionMinute)
            else ShadowExecutionMinute.from_mapping(minute)
            if isinstance(minute, Mapping)
            else None
        )
        if observation is None:
            raise TypeError("minute must be a ShadowExecutionMinute or mapping")
        with self._lock:
            previous = self._cursor_by_asset.get(observation.asset)
            if previous is not None and observation.bar.timestamp <= previous:
                raise ValueError("execution minutes must increase per asset")
            missing_interval_at = (
                previous + timedelta(seconds=EXECUTION_BAR_INTERVAL_SECONDS)
                if previous is not None
                and observation.bar.timestamp
                > previous + timedelta(seconds=EXECUTION_BAR_INTERVAL_SECONDS)
                else None
            )
            self._cursor_by_asset[observation.asset] = observation.bar.timestamp
            changed: dict[str, ShadowEventRecord] = {}
            for event_id, runtime in list(self._open.items()):
                candidate = runtime.candidate
                if candidate.asset != observation.asset:
                    continue
                if observation.bar.timestamp < candidate.decision_at:
                    continue
                unknown_path_gap = bool(
                    not observation.is_real
                    or (
                        missing_interval_at is not None
                        and (
                            candidate.gap_policy is ShadowGapPolicy.CONTINUOUS_CANCEL
                            or not observation.scheduled_session_gap
                        )
                    )
                )
                if unknown_path_gap:
                    if runtime.tracker is None:
                        record = self._cancel_missing_entry(
                            runtime,
                            observation,
                            occurred_at=(
                                max(missing_interval_at, candidate.decision_at)
                                if missing_interval_at is not None
                                else observation.bar.timestamp
                            ),
                            reason=(
                                "continuous_market_data_gap_before_entry"
                                if missing_interval_at is not None
                                and candidate.gap_policy
                                is ShadowGapPolicy.CONTINUOUS_CANCEL
                                else "session_market_unverified_data_gap_before_entry"
                                if missing_interval_at is not None
                                else "continuous_market_non_real_minute_before_entry"
                                if candidate.gap_policy
                                is ShadowGapPolicy.CONTINUOUS_CANCEL
                                else "session_market_non_real_minute_before_entry"
                            ),
                        )
                    else:
                        record = self._cancel_active_data_gap(
                            runtime,
                            observation,
                            occurred_at=(
                                missing_interval_at
                                if missing_interval_at is not None
                                else observation.bar.timestamp
                            ),
                            reason=(
                                "continuous_market_data_gap_unknown_path"
                                if candidate.gap_policy
                                is ShadowGapPolicy.CONTINUOUS_CANCEL
                                else "session_market_unverified_data_gap_unknown_path"
                            ),
                        )
                    changed[event_id] = record
                    continue
                if runtime.tracker is None:
                    if observation.bar.timestamp < candidate.eligible_at:
                        continue
                    if not observation.is_real:
                        if candidate.gap_policy is ShadowGapPolicy.CONTINUOUS_CANCEL:
                            changed[event_id] = self._cancel_missing_entry(
                                runtime, observation
                            )
                        continue
                    if (
                        candidate.gap_policy is ShadowGapPolicy.CONTINUOUS_CANCEL
                        and observation.bar.timestamp != candidate.eligible_at
                    ):
                        changed[event_id] = self._cancel_missing_entry(
                            runtime, observation
                        )
                        continue
                    if (
                        candidate.gap_policy is ShadowGapPolicy.SESSION_NEXT_OPEN
                        and observation.bar.timestamp != candidate.eligible_at
                        and not observation.scheduled_session_gap
                    ):
                        changed[event_id] = self._cancel_missing_entry(
                            runtime,
                            observation,
                            reason=("session_market_unverified_data_gap_before_entry"),
                        )
                        continue
                    fill_failure = self._fill(runtime, observation)
                    if fill_failure is not None:
                        changed[event_id] = fill_failure
                        continue
                elif not observation.is_real:
                    continue

                if runtime.tracker is None:
                    continue
                evaluation = runtime.tracker.update(
                    observation.bar,
                    bar_interval_seconds=EXECUTION_BAR_INTERVAL_SECONDS,
                    observed_at=observation.observed_at,
                )
                if evaluation is not None:
                    changed[event_id] = self._resolve_barrier(runtime, evaluation)
                else:
                    changed[event_id] = runtime.record()

            return tuple(changed.values())

    def update_batch(
        self,
        minutes: Iterable[ShadowExecutionMinute | Mapping[str, Any]],
    ) -> tuple[ShadowEventRecord, ...]:
        """Consume a historical/live batch with identical per-minute semantics."""

        changed: list[ShadowEventRecord] = []
        for minute in minutes:
            changed.extend(self.update(minute))
        return tuple(changed)

    def advance_target_bar(
        self,
        *,
        asset: str,
        timeframe: str,
        bar_open: datetime | str,
        close_price: float,
        observed_at: datetime | str,
    ) -> tuple[ShadowEventRecord, ...]:
        """Count one accepted finalized signal-timeframe bar for active setups."""

        normalized_asset = _required_text(asset, name="asset").upper()
        normalized_timeframe = _required_text(timeframe, name="timeframe").lower()
        opened = as_utc_datetime(bar_open, name="target_bar_open")
        observed = as_utc_datetime(observed_at, name="observed_at")
        changed: dict[str, ShadowEventRecord] = {}
        with self._lock:
            for event_id, runtime in list(self._open.items()):
                candidate = runtime.candidate
                if (
                    candidate.asset != normalized_asset
                    or candidate.timeframe != normalized_timeframe
                    or runtime.tracker is None
                ):
                    continue
                closed = opened + timedelta(
                    seconds=runtime.tracker.plan.target_interval_seconds
                )
                if closed <= runtime.tracker.plan.activated_at:
                    continue
                evaluation = runtime.tracker.advance_target_bar(
                    bar_open=opened,
                    close_price=close_price,
                    observed_at=observed,
                )
                if evaluation is not None:
                    changed[event_id] = self._resolve_barrier(runtime, evaluation)
                else:
                    changed[event_id] = runtime.record()
        return tuple(changed.values())

    def clone(self) -> ShadowEventBook:
        """Return a checksummed copy suitable for fail-open shadow computation."""

        return self.from_snapshot(self.snapshot())

    def get(self, event_id: str) -> ShadowEventRecord | None:
        with self._lock:
            return self._record_by_id(_required_text(event_id, name="event_id"))

    def view(self, *, resolved_limit: int | None = None) -> dict[str, Any]:
        """Return bounded JSON-safe state for monitoring and dataset extraction."""

        with self._lock:
            if resolved_limit is None:
                limit = self.max_resolved_records
            elif (
                isinstance(resolved_limit, bool)
                or not isinstance(resolved_limit, int)
                or resolved_limit < 0
                or resolved_limit > self.max_resolved_records
            ):
                raise ValueError(
                    "resolved_limit must be between zero and max_resolved_records"
                )
            else:
                limit = resolved_limit
            open_records = [runtime.record() for runtime in self._open.values()]
            pending = [
                record.as_dict()
                for record in open_records
                if record.state is ShadowEventState.PENDING
            ]
            active = [
                record.as_dict()
                for record in open_records
                if record.state is ShadowEventState.ACTIVE
            ]
            retained = list(self._resolved)
            selected = retained[-limit:] if limit else []
            payload = {
                "schema_version": SHADOW_SCHEMA_VERSION,
                "max_open_events": self.max_open_events,
                "max_resolved_records": self.max_resolved_records,
                "total_scheduled": self.total_scheduled,
                "total_filled": self.total_filled,
                "total_resolved": self.total_resolved,
                "outcome_counts": dict(self.outcome_counts),
                "pending_count": len(pending),
                "active_count": len(active),
                "resolved_retained_count": len(retained),
                "resolved_returned_count": len(selected),
                "resolved_truncated_count": self.total_resolved - len(selected),
                "cursor_by_asset": {
                    asset: utc_iso(timestamp)
                    for asset, timestamp in sorted(self._cursor_by_asset.items())
                },
                "pending": pending,
                "active": active,
                "resolved": [record.as_dict() for record in selected],
            }
            # Assert the public payload never contains NaN/Infinity indirectly.
            stable_digest(payload)
            return payload

    def snapshot(self) -> dict[str, Any]:
        """Return a bounded checksummed snapshot retaining pending trackers."""

        with self._lock:
            payload = {
                "schema_version": SHADOW_SCHEMA_VERSION,
                "max_open_events": self.max_open_events,
                "max_resolved_records": self.max_resolved_records,
                "open_events": [runtime.snapshot() for runtime in self._open.values()],
                "resolved_events": [record.as_dict() for record in self._resolved],
                "cursor_by_asset": {
                    asset: utc_iso(timestamp)
                    for asset, timestamp in sorted(self._cursor_by_asset.items())
                },
                "total_scheduled": self.total_scheduled,
                "total_filled": self.total_filled,
                "total_resolved": self.total_resolved,
                "outcome_counts": dict(self.outcome_counts),
            }
            return {**payload, "checksum": stable_digest(payload)}

    @classmethod
    def from_snapshot(cls, payload: Mapping[str, Any]) -> ShadowEventBook:
        """Restore after checksum, contract, counter, and tracker validation."""

        if payload.get("schema_version") != SHADOW_SCHEMA_VERSION:
            raise ValueError("unsupported shadow event book schema_version")
        keys = (
            "max_open_events",
            "max_resolved_records",
            "open_events",
            "resolved_events",
            "cursor_by_asset",
            "total_scheduled",
            "total_filled",
            "total_resolved",
            "outcome_counts",
            "checksum",
        )
        missing = [key for key in keys if key not in payload]
        if missing:
            raise ValueError(f"shadow event book snapshot is missing {missing[0]!r}")
        unsigned = {"schema_version": payload["schema_version"]}
        unsigned.update({key: payload[key] for key in keys[:-1]})
        if payload["checksum"] != stable_digest(unsigned):
            raise ValueError("shadow event book snapshot checksum mismatch")
        for name in ("open_events", "resolved_events"):
            if not isinstance(payload[name], list):
                raise ValueError(f"{name} must be a list")
        if not isinstance(payload["cursor_by_asset"], Mapping):
            raise ValueError("cursor_by_asset must be a mapping")
        if not isinstance(payload["outcome_counts"], Mapping):
            raise ValueError("outcome_counts must be a mapping")

        book = cls(
            max_open_events=payload["max_open_events"],
            max_resolved_records=payload["max_resolved_records"],
        )
        for runtime_payload in payload["open_events"]:
            if not isinstance(runtime_payload, Mapping):
                raise ValueError("open event snapshot must be a mapping")
            runtime = _OpenRuntime.from_snapshot(runtime_payload)
            event_id = runtime.candidate.event_id
            if event_id in book._candidate_digests:
                raise ValueError("duplicate event_id in shadow snapshot")
            book._open[event_id] = runtime
            book._candidate_digests[event_id] = runtime.candidate.digest()
        if len(book._open) > book.max_open_events:
            raise ValueError("snapshot exceeds max_open_events")
        for record_payload in payload["resolved_events"]:
            if not isinstance(record_payload, Mapping):
                raise ValueError("resolved event snapshot must be a mapping")
            record = ShadowEventRecord.from_dict(record_payload)
            if record.state is not ShadowEventState.RESOLVED:
                raise ValueError("resolved_events may only contain resolved records")
            event_id = record.candidate.event_id
            if event_id in book._candidate_digests:
                raise ValueError("duplicate event_id in shadow snapshot")
            book._resolved.append(record)
            book._candidate_digests[event_id] = record.candidate.digest()
        if len(book._resolved) > book.max_resolved_records:
            raise ValueError("snapshot exceeds max_resolved_records")
        for asset, timestamp in payload["cursor_by_asset"].items():
            normalized_asset = _required_text(asset, name="cursor asset").upper()
            if normalized_asset in book._cursor_by_asset:
                raise ValueError("duplicate normalized cursor asset")
            book._cursor_by_asset[normalized_asset] = as_utc_datetime(
                timestamp, name="asset cursor"
            )

        counters: dict[str, int] = {}
        expected_outcomes = {outcome.value for outcome in BarrierOutcome}
        if set(payload["outcome_counts"]) != expected_outcomes:
            raise ValueError("outcome_counts keys do not match BarrierOutcome")
        for name, value in payload["outcome_counts"].items():
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError("outcome counts must be non-negative integers")
            counters[name] = value
        totals: dict[str, int] = {}
        for name in ("total_scheduled", "total_filled", "total_resolved"):
            value = payload[name]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
            totals[name] = value
        if sum(counters.values()) != totals["total_resolved"]:
            raise ValueError("outcome_counts do not sum to total_resolved")
        if totals["total_scheduled"] != totals["total_resolved"] + len(book._open):
            raise ValueError(
                "total_scheduled is inconsistent with open/resolved events"
            )
        if not (0 <= totals["total_filled"] <= totals["total_scheduled"]):
            raise ValueError("total_filled is inconsistent with total_scheduled")
        retained_filled = sum(
            record.fill is not None for record in book._resolved
        ) + sum(runtime.fill is not None for runtime in book._open.values())
        if totals["total_filled"] < retained_filled:
            raise ValueError("total_filled is below retained fill count")
        retained_outcomes = {outcome.value: 0 for outcome in BarrierOutcome}
        for record in book._resolved:
            assert record.outcome is not None
            retained_outcomes[record.outcome.value] += 1
        if any(retained_outcomes[key] > counters[key] for key in counters):
            raise ValueError("retained outcomes exceed outcome counters")

        book.total_scheduled = totals["total_scheduled"]
        book.total_filled = totals["total_filled"]
        book.total_resolved = totals["total_resolved"]
        book.outcome_counts = counters
        return book

    def _fill(
        self,
        runtime: _OpenRuntime,
        observation: ShadowExecutionMinute,
    ) -> ShadowEventRecord | None:
        candidate = runtime.candidate
        direction = candidate.side.multiplier
        fill_price = observation.bar.open * (
            1.0 + direction * candidate.adverse_entry_bps / 10_000.0
        )
        fill = ShadowFill(
            event_id=candidate.event_id,
            filled_at=observation.bar.timestamp,
            source_open=observation.bar.open,
            adverse_entry_bps=candidate.adverse_entry_bps,
            fill_price=fill_price,
        )
        try:
            plan = activate_barrier_plan(
                setup_id=candidate.setup_id,
                side=candidate.side,
                fill_price=fill.fill_price,
                risk_unit=candidate.risk_unit,
                activated_at=fill.filled_at,
                config=candidate.barrier_config,
            )
        except (TypeError, ValueError):
            return self._cancel_missing_entry(
                runtime,
                observation,
                occurred_at=observation.bar.timestamp,
                reason="barrier_invalid_at_actual_shadow_fill",
            )
        runtime.fill = fill
        runtime.tracker = BarrierTracker(plan=plan)
        self.total_filled += 1
        return None

    def _resolve_barrier(
        self, runtime: _OpenRuntime, evaluation: BarrierEvaluation
    ) -> ShadowEventRecord:
        assert runtime.fill is not None and runtime.tracker is not None
        assert evaluation.side_return_pct is not None
        gross, deducted_cost, net = barrier_net_return_bps(
            side_return_pct=evaluation.side_return_pct,
            roundtrip_cost_bps=runtime.candidate.estimated_roundtrip_cost_bps,
            embedded_entry_execution_bps=runtime.candidate.adverse_entry_bps,
        )
        record = ShadowEventRecord(
            candidate=runtime.candidate,
            state=ShadowEventState.RESOLVED,
            fill=runtime.fill,
            plan=runtime.tracker.plan,
            evaluation=evaluation,
            outcome=evaluation.outcome,
            occurred_at=evaluation.occurred_at,
            label_known_at=evaluation.label_known_at,
            reason=evaluation.reason,
            observed_bars=evaluation.observed_bars,
            last_observed_at=runtime.tracker.last_timestamp,
            last_observation_at=runtime.tracker.last_observation_at,
            target_bars_elapsed=runtime.tracker.target_bars_elapsed,
            last_target_bar_open=runtime.tracker.last_target_bar_open,
            last_target_bar_observation_at=(
                runtime.tracker.last_target_bar_observation_at
            ),
            gross_return_bps=gross,
            embedded_entry_execution_bps=runtime.candidate.adverse_entry_bps,
            deducted_cost_bps=deducted_cost,
            net_return_bps=net,
            economic_binary_target=int(
                evaluation.outcome is BarrierOutcome.TARGET and net > 0.0
            ),
        )
        self._commit_resolution(record)
        return record

    def _cancel_missing_entry(
        self,
        runtime: _OpenRuntime,
        observation: ShadowExecutionMinute,
        *,
        occurred_at: datetime | None = None,
        reason: str = "continuous_market_missing_eligible_real_minute",
    ) -> ShadowEventRecord:
        record = ShadowEventRecord(
            candidate=runtime.candidate,
            state=ShadowEventState.RESOLVED,
            outcome=BarrierOutcome.CANCELLED,
            occurred_at=occurred_at or runtime.candidate.eligible_at,
            label_known_at=observation.observed_at,
            reason=reason,
        )
        self._commit_resolution(record)
        return record

    def _cancel_active_data_gap(
        self,
        runtime: _OpenRuntime,
        observation: ShadowExecutionMinute,
        *,
        occurred_at: datetime,
        reason: str = "continuous_market_data_gap_unknown_path",
    ) -> ShadowEventRecord:
        assert runtime.fill is not None and runtime.tracker is not None
        record = ShadowEventRecord(
            candidate=runtime.candidate,
            state=ShadowEventState.RESOLVED,
            fill=runtime.fill,
            plan=runtime.tracker.plan,
            outcome=BarrierOutcome.CANCELLED,
            occurred_at=occurred_at,
            label_known_at=observation.observed_at,
            reason=reason,
            observed_bars=runtime.tracker.observed_bars,
            last_observed_at=runtime.tracker.last_timestamp,
            last_observation_at=runtime.tracker.last_observation_at,
            target_bars_elapsed=runtime.tracker.target_bars_elapsed,
            last_target_bar_open=runtime.tracker.last_target_bar_open,
            last_target_bar_observation_at=(
                runtime.tracker.last_target_bar_observation_at
            ),
        )
        self._commit_resolution(record)
        return record

    def _commit_resolution(self, record: ShadowEventRecord) -> None:
        event_id = record.candidate.event_id
        if event_id not in self._open:
            raise RuntimeError("cannot resolve an event that is not open")
        del self._open[event_id]
        if len(self._resolved) == self.max_resolved_records:
            evicted = self._resolved.popleft()
            self._candidate_digests.pop(evicted.candidate.event_id, None)
        self._resolved.append(record)
        self._candidate_digests[event_id] = record.candidate.digest()
        assert record.outcome is not None
        self.total_resolved += 1
        self.outcome_counts[record.outcome.value] += 1

    def _record_by_id(self, event_id: str) -> ShadowEventRecord | None:
        runtime = self._open.get(event_id)
        if runtime is not None:
            return runtime.record()
        for record in reversed(self._resolved):
            if record.candidate.event_id == event_id:
                return record
        return None


__all__ = [
    "EXECUTION_BAR_INTERVAL_SECONDS",
    "SHADOW_CANDIDATE_SCHEMA_VERSION",
    "SHADOW_RECORD_SCHEMA_VERSION",
    "SHADOW_SCHEMA_VERSION",
    "ShadowBookCapacityError",
    "ShadowCandidate",
    "ShadowEventBook",
    "ShadowEventRecord",
    "ShadowEventState",
    "ShadowExecutionMinute",
    "ShadowFill",
    "ShadowGapPolicy",
]
