"""Causal, ordered feature snapshots for CUSUM setup meta-labeling."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .contracts import TradeSide, as_utc_datetime, stable_digest, utc_iso

FEATURE_SCHEMA_VERSION = "cusum_meta_features_v2"

# This order is the model contract.  It must change together with the feature
# schema version and any persisted model artifact, never implicitly at runtime.
META_FEATURE_NAMES: tuple[str, ...] = (
    "log_return_directional",
    "trend_score_directional",
    "trend_agreement_directional",
    "trend_state_alignment",
    "path_quality",
    "risk_unit_fraction",
    "stop_risk_units",
    "target_risk_units",
    "timeout_horizon_minutes_log1p",
    "estimated_roundtrip_cost_bps",
    "trend_z_fast_directional",
    "trend_z_medium_directional",
    "trend_z_slow_directional",
    "path_efficiency_fast",
    "path_efficiency_medium",
    "path_efficiency_slow",
    "trend_component_fast_directional",
    "trend_component_medium_directional",
    "trend_component_slow_directional",
    "ewma_vol_fast_pct",
    "ewma_vol_medium_pct",
    "ewma_vol_slow_pct",
    "fast_slow_ratio",
    "volatility_pressure",
    "range_pressure",
    "cusum_regime_alignment",
    "cusum_standardized_residual_directional",
    "cusum_pressure_balance_directional",
    "cusum_pressure_fraction",
    "cusum_same_side_start",
    "cusum_opposite_side_start",
    "cusum_scale_ready",
)


def _optional_float(source: Mapping[str, Any], key: str) -> float | None:
    value = source.get(key)
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{key} must be numeric, not boolean")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be numeric when present") from exc
    if not math.isfinite(number):
        raise ValueError(f"{key} must be finite when present")
    return number


def _optional_flag(source: Mapping[str, Any], key: str) -> float | None:
    value = source.get(key)
    if value is None:
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if value in (0, 1):
        return float(value)
    raise ValueError(f"{key} must be boolean when present")


def _decision_number(
    value: Any,
    *,
    name: str,
    strictly_positive: bool = False,
) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{name} must be numeric, not boolean")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric when present") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite when present")
    if strictly_positive and number <= 0.0:
        raise ValueError(f"{name} must be positive when present")
    if not strictly_positive and number < 0.0:
        raise ValueError(f"{name} must be non-negative when present")
    return number


def _required_timestamp(
    source: Mapping[str, Any],
    keys: tuple[str, ...],
    *,
    source_name: str,
) -> datetime:
    for key in keys:
        if source.get(key) is not None:
            return as_utc_datetime(source[key], name=f"{source_name}.{key}")
    joined = ", ".join(keys)
    raise ValueError(f"{source_name} requires one timestamp field from: {joined}")


def _validate_causal_sources(
    *,
    decision_at: datetime,
    online: Mapping[str, Any],
    cusum: Mapping[str, Any],
) -> tuple[datetime, datetime, datetime, datetime]:
    online_source = _required_timestamp(
        online, ("source_timestamp",), source_name="online"
    )
    online_available = _required_timestamp(
        online,
        ("available_at",),
        source_name="online",
    )
    if online_available < online_source:
        raise ValueError("online availability precedes its source observation")
    for key in ("timestamp", "available_at", "earliest_execution_at"):
        if online.get(key) is None:
            continue
        timestamp = as_utc_datetime(online[key], name=f"online.{key}")
        if timestamp < online_source:
            raise ValueError(f"online.{key} precedes source_timestamp")
        if timestamp > decision_at:
            raise ValueError(f"online.{key} is not available at decision_at")
    if online_source > decision_at:
        raise ValueError("online source_timestamp is after decision_at")

    cusum_source = _required_timestamp(
        cusum, ("source_timestamp", "timestamp"), source_name="cusum"
    )
    cusum_available = _required_timestamp(
        cusum,
        ("available_at",),
        source_name="cusum",
    )
    if cusum_available < cusum_source:
        raise ValueError("cusum availability precedes its source observation")
    for key in ("timestamp", "available_at", "earliest_execution_at"):
        if cusum.get(key) is None:
            continue
        timestamp = as_utc_datetime(cusum[key], name=f"cusum.{key}")
        if timestamp < cusum_source:
            raise ValueError(f"cusum.{key} precedes its source observation")
        if timestamp > decision_at:
            raise ValueError(f"cusum.{key} is not available at decision_at")
    if cusum_source > decision_at:
        raise ValueError("cusum source timestamp is after decision_at")
    return online_source, online_available, cusum_source, cusum_available


@dataclass(frozen=True, slots=True)
class FeatureSnapshot:
    """One immutable model row captured at a setup decision boundary."""

    setup_id: str
    side: TradeSide
    decision_at: datetime
    online_source_timestamp: datetime
    online_available_at: datetime
    cusum_source_timestamp: datetime
    cusum_available_at: datetime
    online_status: str
    cusum_status: str
    feature_names: tuple[str, ...]
    values: tuple[float | None, ...]

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
            "decision_at",
            "online_source_timestamp",
            "online_available_at",
            "cusum_source_timestamp",
            "cusum_available_at",
        ):
            object.__setattr__(
                self,
                field_name,
                as_utc_datetime(getattr(self, field_name), name=field_name),
            )
        feature_names = tuple(self.feature_names)
        if feature_names != META_FEATURE_NAMES:
            raise ValueError(
                "feature_names must exactly match META_FEATURE_NAMES order"
            )
        object.__setattr__(self, "feature_names", feature_names)
        values = tuple(self.values)
        if len(values) != len(feature_names):
            raise ValueError("values length must match feature_names")
        normalized: list[float | None] = []
        for name, value in zip(feature_names, values, strict=True):
            if value is None:
                normalized.append(None)
                continue
            if isinstance(value, bool):
                raise ValueError(f"feature {name} must be numeric or None")
            number = float(value)
            if not math.isfinite(number):
                raise ValueError(f"feature {name} must be finite or None")
            normalized.append(number)
        object.__setattr__(self, "values", tuple(normalized))
        for field_name in ("online_status", "cusum_status"):
            status = str(getattr(self, field_name)).strip()
            if not status:
                raise ValueError(f"{field_name} must not be empty")
            object.__setattr__(self, field_name, status)
        if self.online_source_timestamp > self.online_available_at:
            raise ValueError("online source timestamp exceeds availability timestamp")
        if self.cusum_source_timestamp > self.cusum_available_at:
            raise ValueError("cusum source timestamp exceeds availability timestamp")
        for field_name in (
            "online_source_timestamp",
            "online_available_at",
            "cusum_source_timestamp",
            "cusum_available_at",
        ):
            if getattr(self, field_name) > self.decision_at:
                raise ValueError(f"{field_name} exceeds decision_at")

    def feature_map(self) -> dict[str, float | None]:
        """Return features in the contract's insertion order."""

        return dict(zip(self.feature_names, self.values, strict=True))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": FEATURE_SCHEMA_VERSION,
            "setup_id": self.setup_id,
            "side": self.side.value,
            "decision_at": utc_iso(self.decision_at),
            "online_source_timestamp": utc_iso(self.online_source_timestamp),
            "online_available_at": utc_iso(self.online_available_at),
            "cusum_source_timestamp": utc_iso(self.cusum_source_timestamp),
            "cusum_available_at": utc_iso(self.cusum_available_at),
            "online_status": self.online_status,
            "cusum_status": self.cusum_status,
            "feature_names": list(self.feature_names),
            "values": list(self.values),
            "features": self.feature_map(),
        }

    def digest(self) -> str:
        return stable_digest(self.as_dict())


def build_feature_snapshot(
    *,
    setup_id: str,
    side: TradeSide | str,
    decision_at: datetime | str,
    online: Mapping[str, Any],
    cusum: Mapping[str, Any],
    entry_reference: float | None = None,
    risk_unit: float | None = None,
    stop_risk_units: float | None = None,
    target_risk_units: float | None = None,
    timeout_target_bars: int | None = None,
    target_interval_seconds: int | None = None,
    estimated_roundtrip_cost_bps: float | None = None,
) -> FeatureSnapshot:
    """Capture a deterministic, side-normalized row from finalized indicators.

    The function rejects any source timestamp or stated availability later than
    ``decision_at``.  It never derives a feature from future OHLC bars, barrier
    outcomes, target/stop prices, or post-entry trade state.
    """

    if not isinstance(online, Mapping) or not isinstance(cusum, Mapping):
        raise TypeError("online and cusum must be mappings")
    try:
        normalized_side = side if isinstance(side, TradeSide) else TradeSide(side)
    except ValueError as exc:
        raise ValueError("side must be LONG or SHORT") from exc
    decision = as_utc_datetime(decision_at, name="decision_at")
    (
        online_source,
        online_available,
        cusum_source,
        cusum_available,
    ) = _validate_causal_sources(
        decision_at=decision,
        online=online,
        cusum=cusum,
    )
    direction = float(normalized_side.multiplier)
    entry_value = _decision_number(
        entry_reference, name="entry_reference", strictly_positive=True
    )
    risk_value = _decision_number(risk_unit, name="risk_unit", strictly_positive=True)
    stop_units = _decision_number(
        stop_risk_units, name="stop_risk_units", strictly_positive=True
    )
    target_units = _decision_number(
        target_risk_units, name="target_risk_units", strictly_positive=True
    )
    timeout_values = (timeout_target_bars, target_interval_seconds)
    if (timeout_target_bars is None) != (target_interval_seconds is None):
        raise ValueError("timeout target bars and interval must be provided together")
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value <= 0
        for value in timeout_values
        if value is not None
    ):
        raise ValueError("timeout target bars and interval must be positive integers")
    cost_bps = _decision_number(
        estimated_roundtrip_cost_bps,
        name="estimated_roundtrip_cost_bps",
    )

    trend_state = _optional_float(online, "trend_state_code")
    residual = _optional_float(cusum, "residual")
    residual_std = _optional_float(cusum, "res_std")
    standardized_residual = (
        residual / residual_std
        if residual is not None and residual_std is not None and residual_std > 0.0
        else None
    )
    bull_pressure = _optional_float(cusum, "bull_pressure")
    bear_pressure = _optional_float(cusum, "bear_pressure")
    pressure_balance = (
        bull_pressure - bear_pressure
        if bull_pressure is not None and bear_pressure is not None
        else None
    )
    pressure_pct = _optional_float(cusum, "pressure_pct")
    if pressure_pct is not None and not 0.0 <= pressure_pct <= 100.0:
        raise ValueError("pressure_pct must be between zero and 100")
    cusum_regime = _optional_float(cusum, "regime")

    same_start_key = "bull_start" if normalized_side is TradeSide.LONG else "bear_start"
    opposite_start_key = (
        "bear_start" if normalized_side is TradeSide.LONG else "bull_start"
    )

    def directional(source: Mapping[str, Any], key: str) -> float | None:
        value = _optional_float(source, key)
        return direction * value if value is not None else None

    values: tuple[float | None, ...] = (
        directional(online, "log_return"),
        directional(online, "trend_score"),
        directional(online, "trend_agreement"),
        direction * trend_state / 2.0 if trend_state is not None else None,
        _optional_float(online, "path_quality"),
        risk_value / entry_value
        if risk_value is not None and entry_value is not None
        else None,
        stop_units,
        target_units,
        (
            math.log1p(timeout_target_bars * target_interval_seconds / 60.0)
            if timeout_target_bars is not None and target_interval_seconds is not None
            else None
        ),
        cost_bps,
        directional(online, "trend_z_fast"),
        directional(online, "trend_z_medium"),
        directional(online, "trend_z_slow"),
        _optional_float(online, "path_efficiency_fast"),
        _optional_float(online, "path_efficiency_medium"),
        _optional_float(online, "path_efficiency_slow"),
        directional(online, "trend_component_fast"),
        directional(online, "trend_component_medium"),
        directional(online, "trend_component_slow"),
        _optional_float(online, "ewma_vol_fast_pct"),
        _optional_float(online, "ewma_vol_medium_pct"),
        _optional_float(online, "ewma_vol_slow_pct"),
        _optional_float(online, "fast_slow_ratio"),
        _optional_float(online, "volatility_pressure"),
        _optional_float(online, "range_pressure"),
        direction * cusum_regime if cusum_regime is not None else None,
        direction * standardized_residual
        if standardized_residual is not None
        else None,
        direction * pressure_balance if pressure_balance is not None else None,
        pressure_pct / 100.0 if pressure_pct is not None else None,
        _optional_flag(cusum, same_start_key),
        _optional_flag(cusum, opposite_start_key),
        _optional_flag(cusum, "scale_ready"),
    )
    return FeatureSnapshot(
        setup_id=setup_id,
        side=normalized_side,
        decision_at=decision,
        online_source_timestamp=online_source,
        online_available_at=online_available,
        cusum_source_timestamp=cusum_source,
        cusum_available_at=cusum_available,
        online_status=str(online.get("status", "unknown")),
        cusum_status=str(cusum.get("status", "unknown")),
        feature_names=META_FEATURE_NAMES,
        values=values,
    )


__all__ = [
    "FEATURE_SCHEMA_VERSION",
    "META_FEATURE_NAMES",
    "FeatureSnapshot",
    "build_feature_snapshot",
]
