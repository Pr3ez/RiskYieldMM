"""Shared, auditable economics for static CUSUM meta-label trades."""

from __future__ import annotations

import math
from typing import Any


def _nonnegative(value: Any, *, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite non-negative number")
    number = float(value)
    if not math.isfinite(number) or number < 0.0:
        raise ValueError(f"{name} must be a finite non-negative number")
    return number


def nonembedded_cost_bps(
    *,
    roundtrip_cost_bps: float,
    embedded_entry_execution_bps: float,
) -> float:
    """Return costs not already represented by an adverse actual entry fill."""

    roundtrip = _nonnegative(roundtrip_cost_bps, name="roundtrip_cost_bps")
    embedded = _nonnegative(
        embedded_entry_execution_bps,
        name="embedded_entry_execution_bps",
    )
    if embedded > roundtrip:
        raise ValueError("embedded entry execution cannot exceed roundtrip cost")
    return roundtrip - embedded


def barrier_net_return_bps(
    *,
    side_return_pct: float,
    roundtrip_cost_bps: float,
    embedded_entry_execution_bps: float,
) -> tuple[float, float, float]:
    """Return gross, deducted cost, and net bps without double-counting entry."""

    if isinstance(side_return_pct, bool):
        raise ValueError("side_return_pct must be finite")
    gross = float(side_return_pct) * 100.0
    if not math.isfinite(gross):
        raise ValueError("side_return_pct must be finite")
    deducted = nonembedded_cost_bps(
        roundtrip_cost_bps=roundtrip_cost_bps,
        embedded_entry_execution_bps=embedded_entry_execution_bps,
    )
    return gross, deducted, gross - deducted


__all__ = ["barrier_net_return_bps", "nonembedded_cost_bps"]
