"""Immutable contracts for protected trades and their barrier outcomes.

The contracts in this module deliberately contain no order-routing logic.  A
barrier plan is created only after an entry fill is known, which keeps research
labels and future live execution tied to the same price-based definition.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

CONTRACT_SCHEMA_VERSION = "trade_ml_contracts_v2"


class TradeSide(str, Enum):
    """Direction of a protected trade."""

    LONG = "LONG"
    SHORT = "SHORT"

    @property
    def multiplier(self) -> int:
        return 1 if self is TradeSide.LONG else -1


class BarrierOutcome(str, Enum):
    """Terminal outcomes supported by the barrier-label contract."""

    TARGET = "TARGET"
    STOP = "STOP"
    TIMEOUT = "TIMEOUT"
    AMBIGUOUS = "AMBIGUOUS"
    CANCELLED = "CANCELLED"


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


def as_utc_datetime(value: datetime | str, *, name: str = "timestamp") -> datetime:
    """Return a timezone-aware UTC datetime, rejecting ambiguous naive input."""

    parsed: datetime
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            raise ValueError(f"{name} must not be empty")
        if candidate.endswith("Z"):
            candidate = f"{candidate[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError as exc:
            raise ValueError(f"{name} must be an ISO-8601 timestamp") from exc
    else:
        raise ValueError(f"{name} must be a datetime or ISO-8601 string")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return parsed.astimezone(timezone.utc)


def utc_iso(value: datetime) -> str:
    """Serialize an aware datetime as a canonical UTC ISO-8601 string."""

    return as_utc_datetime(value).isoformat().replace("+00:00", "Z")


def stable_digest(payload: Mapping[str, Any]) -> str:
    """Return a stable SHA-256 digest for a JSON-safe mapping."""

    encoded = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class BarrierConfig:
    """Risk-unit distances and a finalized target-candle horizon."""

    stop_risk_units: float = 1.0
    target_risk_units: float = 2.0
    timeout_target_bars: int = 20
    target_interval_seconds: int = 60

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "stop_risk_units",
            _finite_positive(self.stop_risk_units, name="stop_risk_units"),
        )
        object.__setattr__(
            self,
            "target_risk_units",
            _finite_positive(self.target_risk_units, name="target_risk_units"),
        )
        for name in ("timeout_target_bars", "target_interval_seconds"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": CONTRACT_SCHEMA_VERSION,
            "stop_risk_units": self.stop_risk_units,
            "target_risk_units": self.target_risk_units,
            "timeout_target_bars": self.timeout_target_bars,
            "target_interval_seconds": self.target_interval_seconds,
            "timeout_clock": "accepted_finalized_target_bars",
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> BarrierConfig:
        """Restore a validated config from its JSON representation."""

        if payload.get("schema_version") != CONTRACT_SCHEMA_VERSION:
            raise ValueError("unsupported barrier config schema_version")
        try:
            return cls(
                stop_risk_units=payload["stop_risk_units"],
                target_risk_units=payload["target_risk_units"],
                timeout_target_bars=payload["timeout_target_bars"],
                target_interval_seconds=payload["target_interval_seconds"],
            )
        except KeyError as exc:
            raise ValueError(f"barrier config is missing {exc.args[0]!r}") from exc

    def digest(self) -> str:
        return stable_digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class BarrierPlan:
    """A fixed stop/target plan activated from the actual entry fill."""

    setup_id: str
    side: TradeSide
    fill_price: float
    risk_unit: float
    stop_price: float
    target_price: float
    activated_at: datetime
    stop_risk_units: float
    target_risk_units: float
    timeout_target_bars: int
    target_interval_seconds: int
    config_digest: str

    def __post_init__(self) -> None:
        setup_id = str(self.setup_id).strip()
        if not setup_id:
            raise ValueError("setup_id must not be empty")
        object.__setattr__(self, "setup_id", setup_id)
        try:
            side = (
                self.side if isinstance(self.side, TradeSide) else TradeSide(self.side)
            )
        except ValueError as exc:
            raise ValueError("side must be LONG or SHORT") from exc
        object.__setattr__(self, "side", side)

        for field_name in (
            "fill_price",
            "risk_unit",
            "stop_price",
            "target_price",
            "stop_risk_units",
            "target_risk_units",
        ):
            object.__setattr__(
                self,
                field_name,
                _finite_positive(getattr(self, field_name), name=field_name),
            )
        object.__setattr__(
            self,
            "activated_at",
            as_utc_datetime(self.activated_at, name="activated_at"),
        )
        for name in ("timeout_target_bars", "target_interval_seconds"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")

        if side is TradeSide.LONG:
            ordered = self.stop_price < self.fill_price < self.target_price
            expected_stop = self.fill_price - self.stop_risk_units * self.risk_unit
            expected_target = self.fill_price + self.target_risk_units * self.risk_unit
        else:
            ordered = self.target_price < self.fill_price < self.stop_price
            expected_stop = self.fill_price + self.stop_risk_units * self.risk_unit
            expected_target = self.fill_price - self.target_risk_units * self.risk_unit
        if not ordered:
            raise ValueError(
                "barrier prices must straddle the fill in side-aware order"
            )
        if not math.isclose(
            self.stop_price, expected_stop, rel_tol=1e-12, abs_tol=1e-12
        ):
            raise ValueError(
                "stop_price is inconsistent with fill, risk unit, and config"
            )
        if not math.isclose(
            self.target_price, expected_target, rel_tol=1e-12, abs_tol=1e-12
        ):
            raise ValueError(
                "target_price is inconsistent with fill, risk unit, and config"
            )

        expected_config_digest = BarrierConfig(
            stop_risk_units=self.stop_risk_units,
            target_risk_units=self.target_risk_units,
            timeout_target_bars=self.timeout_target_bars,
            target_interval_seconds=self.target_interval_seconds,
        ).digest()
        if self.config_digest != expected_config_digest:
            raise ValueError("config_digest does not match the plan parameters")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": CONTRACT_SCHEMA_VERSION,
            "setup_id": self.setup_id,
            "side": self.side.value,
            "fill_price": self.fill_price,
            "risk_unit": self.risk_unit,
            "stop_price": self.stop_price,
            "target_price": self.target_price,
            "activated_at": utc_iso(self.activated_at),
            "stop_risk_units": self.stop_risk_units,
            "target_risk_units": self.target_risk_units,
            "timeout_target_bars": self.timeout_target_bars,
            "target_interval_seconds": self.target_interval_seconds,
            "timeout_clock": "accepted_finalized_target_bars",
            "config_digest": self.config_digest,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> BarrierPlan:
        """Restore and fully revalidate a plan from a JSON-safe mapping."""

        if payload.get("schema_version") != CONTRACT_SCHEMA_VERSION:
            raise ValueError("unsupported barrier plan schema_version")
        try:
            plan = cls(
                setup_id=payload["setup_id"],
                side=payload["side"],
                fill_price=payload["fill_price"],
                risk_unit=payload["risk_unit"],
                stop_price=payload["stop_price"],
                target_price=payload["target_price"],
                activated_at=payload["activated_at"],
                stop_risk_units=payload["stop_risk_units"],
                target_risk_units=payload["target_risk_units"],
                timeout_target_bars=payload["timeout_target_bars"],
                target_interval_seconds=payload["target_interval_seconds"],
                config_digest=payload["config_digest"],
            )
        except KeyError as exc:
            raise ValueError(f"barrier plan is missing {exc.args[0]!r}") from exc
        return plan

    def digest(self) -> str:
        return stable_digest(self.as_dict())


def activate_barrier_plan(
    *,
    setup_id: str,
    side: TradeSide | str,
    fill_price: float,
    risk_unit: float,
    activated_at: datetime | str,
    config: BarrierConfig,
) -> BarrierPlan:
    """Create immutable barriers from an actual fill and a positive risk unit."""

    if not isinstance(config, BarrierConfig):
        raise TypeError("config must be a BarrierConfig")
    normalized_side = side if isinstance(side, TradeSide) else TradeSide(side)
    fill = _finite_positive(fill_price, name="fill_price")
    risk = _finite_positive(risk_unit, name="risk_unit")
    if normalized_side is TradeSide.LONG:
        stop = fill - config.stop_risk_units * risk
        target = fill + config.target_risk_units * risk
    else:
        stop = fill + config.stop_risk_units * risk
        target = fill - config.target_risk_units * risk
    if stop <= 0.0 or target <= 0.0:
        raise ValueError("configured barriers must remain above zero")
    return BarrierPlan(
        setup_id=setup_id,
        side=normalized_side,
        fill_price=fill,
        risk_unit=risk,
        stop_price=stop,
        target_price=target,
        activated_at=as_utc_datetime(activated_at, name="activated_at"),
        stop_risk_units=config.stop_risk_units,
        target_risk_units=config.target_risk_units,
        timeout_target_bars=config.timeout_target_bars,
        target_interval_seconds=config.target_interval_seconds,
        config_digest=config.digest(),
    )


__all__ = [
    "CONTRACT_SCHEMA_VERSION",
    "BarrierConfig",
    "BarrierOutcome",
    "BarrierPlan",
    "TradeSide",
    "activate_barrier_plan",
    "as_utc_datetime",
    "stable_digest",
    "utc_iso",
]
