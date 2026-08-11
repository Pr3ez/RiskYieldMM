"""Chart indicator implementations for the local visual inspector."""

from __future__ import annotations

import hashlib
import json
import math
from collections import deque
from dataclasses import dataclass
from typing import Any

import polars as pl

CUSUM_TREND_VERSION = "standardized_cusum_trend_stream_v2"
CUSUM_SENSITIVITIES = (
    "Fast (Day Trade)",
    "Balanced (Swing)",
    "Slow (Trend)",
)
DEFAULT_CUSUM_SENSITIVITY = "Balanced (Swing)"

# These are half-lives in observed bars, not calendar-time decay periods. The
# default covers a short, medium, and slow volatility memory without exposing
# runtime tuning controls before a walk-forward experiment exists.
EWMA_VOLATILITY_HALF_LIVES = (12, 48, 192)
EWMA_VOLATILITY_LABELS = ("fast", "medium", "slow")

COL_BULL = (46, 227, 25)
COL_BEAR = (243, 22, 35)
COL_RANGE = (127, 73, 222)


@dataclass(frozen=True)
class CusumParams:
    """Parameter set copied from the Pine CUSUM Trend sensitivity presets."""

    base_len: int
    k_mult: float
    h_mult: float


def cusum_params(sensitivity: str = DEFAULT_CUSUM_SENSITIVITY) -> CusumParams:
    """Return the CUSUM Trend preset parameters for a UI sensitivity label."""
    if sensitivity == "Fast (Day Trade)":
        return CusumParams(base_len=14, k_mult=0.4, h_mult=2.0)
    if sensitivity == "Balanced (Swing)":
        return CusumParams(base_len=21, k_mult=0.5, h_mult=3.0)
    if sensitivity == "Slow (Trend)":
        return CusumParams(base_len=50, k_mult=0.6, h_mult=4.0)
    known = ", ".join(CUSUM_SENSITIVITIES)
    raise ValueError(
        f"Unknown CUSUM sensitivity {sensitivity!r}. Known sensitivities: {known}"
    )


def _is_valid(value: float | None) -> bool:
    try:
        return value is not None and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _rolling_wma(values: list[float | None], length: int) -> list[float | None]:
    weights = list(range(1, length + 1))
    weight_sum = float(sum(weights))
    result: list[float | None] = [None] * len(values)
    for idx in range(length - 1, len(values)):
        window = values[idx - length + 1 : idx + 1]
        if not all(_is_valid(value) for value in window):
            continue
        result[idx] = (
            sum(float(value) * weight for value, weight in zip(window, weights))
            / weight_sum
        )
    return result


def _rolling_std(values: list[float | None], length: int) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    for idx in range(length - 1, len(values)):
        window = values[idx - length + 1 : idx + 1]
        if not all(_is_valid(value) for value in window):
            continue
        typed = [float(value) for value in window]
        mean = sum(typed) / length
        variance = sum((value - mean) ** 2 for value in typed) / length
        result[idx] = math.sqrt(variance)
    return result


def _latest_wma(values: list[float | None], length: int) -> float | None:
    """Return only the newest WMA using the batch implementation's arithmetic."""
    if len(values) < length:
        return None
    window = values[-length:]
    if not all(_is_valid(value) for value in window):
        return None
    weights = list(range(1, length + 1))
    weight_sum = float(sum(weights))
    return (
        sum(float(value) * weight for value, weight in zip(window, weights))
        / weight_sum
    )


def _latest_std(values: list[float | None], length: int) -> float | None:
    """Return only the newest population standard deviation."""
    if len(values) < length:
        return None
    window = values[-length:]
    if not all(_is_valid(value) for value in window):
        return None
    typed = [float(value) for value in window]
    mean = sum(typed) / length
    variance = sum((value - mean) ** 2 for value in typed) / length
    return math.sqrt(variance)


def _hma(values: list[float | None], length: int) -> list[float | None]:
    half_len = max(1, length // 2)
    sqrt_len = max(1, int(math.sqrt(length)))
    wma_half = _rolling_wma(values, half_len)
    wma_full = _rolling_wma(values, length)
    diff: list[float | None] = []
    for half, full in zip(wma_half, wma_full):
        if not _is_valid(half) or not _is_valid(full):
            diff.append(None)
        else:
            diff.append(2.0 * float(half) - float(full))
    return _rolling_wma(diff, sqrt_len)


def _rgba(rgb: tuple[int, int, int], alpha: float) -> str:
    bounded = min(max(alpha, 0.0), 1.0)
    return f"rgba({rgb[0]}, {rgb[1]}, {rgb[2]}, {bounded:.3f})"


def _candle_color(regime: int, pressure_pct: float) -> str:
    alpha = 0.4 + 0.6 * min(max(pressure_pct, 0.0), 100.0) / 100.0
    if regime == 1:
        return _rgba(COL_BULL, alpha)
    if regime == -1:
        return _rgba(COL_BEAR, alpha)
    return _rgba(COL_RANGE, 0.70)


class CusumTrendEngine:
    """Causal standardized CUSUM Trend engine for finalized bars.

    Callers must feed closed bars in chronological order.  Each update emits
    the indicator values for that source bar; those values remain subject to
    the chart contract that a closed-bar observation is actionable no earlier
    than the next bar.  The bounded buffers contain exactly the history needed
    by the nested HMA and residual-standard-deviation calculations.
    """

    def __init__(
        self,
        sensitivity: str = DEFAULT_CUSUM_SENSITIVITY,
    ) -> None:
        self.sensitivity = str(sensitivity)
        self.params = cusum_params(self.sensitivity)
        self._half_len = max(1, self.params.base_len // 2)
        self._sqrt_len = max(1, int(math.sqrt(self.params.base_len)))
        self._close_window: deque[float | None] = deque(maxlen=self.params.base_len)
        self._diff_window: deque[float | None] = deque(maxlen=self._sqrt_len)
        self._residual_window: deque[float | None] = deque(maxlen=self.params.base_len)
        self.bull_pressure = 0.0
        self.bear_pressure = 0.0
        self.regime = 0
        self.bars_seen = 0

    def update(
        self,
        *,
        timestamp: Any,
        close: float | None,
    ) -> dict[str, Any]:
        """Advance once with one finalized close and return its chart row."""

        close_value = None if close is None else float(close)
        if not _is_valid(close_value):
            # ``None`` is JSON-safe and has the same rolling-window semantics
            # as every non-finite value in the historical batch calculation.
            close_value = None
        self._close_window.append(close_value)
        close_window = list(self._close_window)
        wma_half = _latest_wma(close_window, self._half_len)
        wma_full = _latest_wma(close_window, self.params.base_len)
        diff = (
            None
            if not _is_valid(wma_half) or not _is_valid(wma_full)
            else (2.0 * float(wma_half)) - float(wma_full)
        )
        self._diff_window.append(diff)
        hma_base = _latest_wma(list(self._diff_window), self._sqrt_len)
        residual = (
            None
            if not _is_valid(close_value) or not _is_valid(hma_base)
            else float(close_value) - float(hma_base)
        )
        # The current residual must not influence the scale used to score that
        # same observation.  This prior-only scale makes the detector causal at
        # a shock and, unlike the former absolute 0.001 fallback, invariant to
        # the instrument's price units.
        res_std = _latest_std(list(self._residual_window), self.params.base_len)
        self._residual_window.append(residual)

        prev_regime = self.regime
        up_band: float | None = None
        dn_band: float | None = None
        trail_stop: float | None = None
        bull_start = False
        bear_start = False

        numerical_scale_floor = (
            abs(float(hma_base)) * 1e-12 if _is_valid(hma_base) else 0.0
        )
        scale_ready = (
            _is_valid(hma_base)
            and _is_valid(residual)
            and _is_valid(res_std)
            and float(res_std) > numerical_scale_floor
        )
        if not scale_ready:
            # A sequential CUSUM is undefined until its reference scale is
            # available.  Reset instead of generating price-unit-dependent
            # warm-up signals or carrying state across invalid observations.
            self.bull_pressure = 0.0
            self.bear_pressure = 0.0
            self.regime = 0
            output_bull_pressure = 0.0
            output_bear_pressure = 0.0
            pressure_pct = 0.0
        else:
            std_value = float(res_std)
            standardized_residual = float(residual) / std_value
            k_drift = self.params.k_mult
            h_thresh = self.params.h_mult
            up_band = float(hma_base) + (std_value * h_thresh)
            dn_band = float(hma_base) - (std_value * h_thresh)

            self.bull_pressure = max(
                0.0, self.bull_pressure + standardized_residual - k_drift
            )
            self.bear_pressure = max(
                0.0, self.bear_pressure - standardized_residual - k_drift
            )
            trig_bull = self.bull_pressure > h_thresh
            trig_bear = self.bear_pressure > h_thresh

            if trig_bull or trig_bear:
                self.bull_pressure = 0.0
                self.bear_pressure = 0.0

            if trig_bull:
                self.regime = 1
            elif trig_bear:
                self.regime = -1
            elif (
                self.regime == 1
                and _is_valid(close_value)
                and float(close_value) < dn_band
            ):
                self.regime = 0
            elif (
                self.regime == -1
                and _is_valid(close_value)
                and float(close_value) > up_band
            ):
                self.regime = 0

            max_pressure = max(self.bull_pressure, self.bear_pressure)
            pressure_pct = (
                min((max_pressure / h_thresh) * 100.0, 100.0) if h_thresh else 0.0
            )
            if self.regime == 1:
                trail_stop = dn_band
            elif self.regime == -1:
                trail_stop = up_band

            bull_start = self.regime == 1 and prev_regime != 1
            bear_start = self.regime == -1 and prev_regime != -1
            output_bull_pressure = self.bull_pressure
            output_bear_pressure = self.bear_pressure

        self.bars_seen += 1
        return {
            "timestamp": timestamp,
            "hma_base": hma_base,
            "residual": residual,
            "res_std": res_std,
            "scale_ready": scale_ready,
            "status": "ok" if scale_ready else "scale_warmup_or_flat",
            "up_band": up_band,
            "dn_band": dn_band,
            "bull_pressure": output_bull_pressure,
            "bear_pressure": output_bear_pressure,
            "pressure_pct": pressure_pct,
            "regime": self.regime,
            "trail_stop": trail_stop,
            "bull_start": bull_start,
            "bear_start": bear_start,
            "candle_color": _candle_color(self.regime, pressure_pct),
        }

    def snapshot(self) -> dict[str, Any]:
        """Return a checksummed, JSON-safe representation of engine state."""

        payload = {
            "algorithm_version": CUSUM_TREND_VERSION,
            "sensitivity": self.sensitivity,
            "params": {
                "base_len": self.params.base_len,
                "k_mult": self.params.k_mult,
                "h_mult": self.params.h_mult,
            },
            "close_window": list(self._close_window),
            "diff_window": list(self._diff_window),
            "residual_window": list(self._residual_window),
            "bull_pressure": self.bull_pressure,
            "bear_pressure": self.bear_pressure,
            "regime": self.regime,
            "bars_seen": self.bars_seen,
        }
        serialized = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        return {
            **payload,
            "checksum": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
        }

    @classmethod
    def restore(
        cls,
        snapshot: dict[str, Any],
        *,
        expected_sensitivity: str | None = None,
    ) -> CusumTrendEngine:
        """Restore state after validating version, parameters and checksum."""

        if not isinstance(snapshot, dict):
            raise ValueError("CUSUM Trend snapshot must be a mapping")
        raw = dict(snapshot)
        checksum = str(raw.pop("checksum", ""))
        try:
            serialized = json.dumps(
                raw, sort_keys=True, separators=(",", ":"), allow_nan=False
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("CUSUM Trend snapshot is not JSON-safe") from exc
        expected_checksum = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        if checksum != expected_checksum:
            raise ValueError("CUSUM Trend snapshot checksum mismatch")
        if raw.get("algorithm_version") != CUSUM_TREND_VERSION:
            raise ValueError("CUSUM Trend snapshot algorithm version mismatch")

        sensitivity = raw.get("sensitivity")
        if not isinstance(sensitivity, str):
            raise ValueError("CUSUM Trend snapshot sensitivity is invalid")
        if expected_sensitivity is not None and sensitivity != expected_sensitivity:
            raise ValueError("CUSUM Trend snapshot does not match expected sensitivity")
        engine = cls(sensitivity)
        expected_params = {
            "base_len": engine.params.base_len,
            "k_mult": engine.params.k_mult,
            "h_mult": engine.params.h_mult,
        }
        if raw.get("params") != expected_params:
            raise ValueError("CUSUM Trend snapshot parameters are invalid")

        bars_seen = raw.get("bars_seen")
        if (
            isinstance(bars_seen, bool)
            or not isinstance(bars_seen, int)
            or bars_seen < 0
        ):
            raise ValueError("CUSUM Trend snapshot bar count is invalid")
        engine.bars_seen = bars_seen
        engine._close_window = deque(
            _restore_cusum_buffer(
                raw.get("close_window"),
                maximum=engine.params.base_len,
                expected=min(bars_seen, engine.params.base_len),
                name="close",
            ),
            maxlen=engine.params.base_len,
        )
        engine._diff_window = deque(
            _restore_cusum_buffer(
                raw.get("diff_window"),
                maximum=engine._sqrt_len,
                expected=min(bars_seen, engine._sqrt_len),
                name="HMA difference",
            ),
            maxlen=engine._sqrt_len,
        )
        engine._residual_window = deque(
            _restore_cusum_buffer(
                raw.get("residual_window"),
                maximum=engine.params.base_len,
                expected=min(bars_seen, engine.params.base_len),
                name="residual",
            ),
            maxlen=engine.params.base_len,
        )
        engine.bull_pressure = _restore_nonnegative_float(
            raw.get("bull_pressure"), name="bull pressure"
        )
        engine.bear_pressure = _restore_nonnegative_float(
            raw.get("bear_pressure"), name="bear pressure"
        )
        regime = raw.get("regime")
        if isinstance(regime, bool) or regime not in (-1, 0, 1):
            raise ValueError("CUSUM Trend snapshot regime is invalid")
        engine.regime = int(regime)
        if bars_seen == 0 and (
            engine.bull_pressure != 0.0
            or engine.bear_pressure != 0.0
            or engine.regime != 0
        ):
            raise ValueError("CUSUM Trend snapshot empty state is inconsistent")
        return engine


def _restore_cusum_buffer(
    raw: Any,
    *,
    maximum: int,
    expected: int,
    name: str,
) -> list[float | None]:
    if not isinstance(raw, list) or len(raw) > maximum or len(raw) != expected:
        raise ValueError(f"CUSUM Trend snapshot {name} buffer is invalid")
    restored: list[float | None] = []
    for value in raw:
        if value is None:
            restored.append(None)
            continue
        if isinstance(value, bool):
            raise ValueError(f"CUSUM Trend snapshot {name} buffer is invalid")
        try:
            parsed = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"CUSUM Trend snapshot {name} buffer is invalid") from exc
        if not math.isfinite(parsed):
            raise ValueError(f"CUSUM Trend snapshot {name} buffer is invalid")
        restored.append(parsed)
    return restored


def _restore_nonnegative_float(raw: Any, *, name: str) -> float:
    if isinstance(raw, bool):
        raise ValueError(f"CUSUM Trend snapshot {name} is invalid")
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"CUSUM Trend snapshot {name} is invalid") from exc
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"CUSUM Trend snapshot {name} is invalid")
    return value


def _none_series(length: int) -> list[float | None]:
    return [None] * length


def _ewma_decay(half_life_bars: int) -> float:
    """Return the retained variance weight for an EWMA half-life in bars."""
    if half_life_bars <= 0:
        raise ValueError("EWMA volatility half-lives must be positive")
    return math.exp(-math.log(2.0) / float(half_life_bars))


def compute_ewma_volatility(
    frame: pl.DataFrame,
    *,
    half_lives: tuple[int, int, int] = EWMA_VOLATILITY_HALF_LIVES,
) -> pl.DataFrame:
    """Compute post-close EWMA log-return volatility in percent per observed bar.

    For each completed close ``t`` the function updates
    ``v_t = lambda * v_(t-1) + (1 - lambda) * r_t**2`` and emits
    ``100 * sqrt(v_t)`` at the candle timestamp. It is therefore available for
    a decision no earlier than the next bar. Missing, non-finite, or
    non-positive closes reset the return chain instead of producing non-finite
    values. Decay follows observed bars, so session gaps remain one observed
    close-to-close return rather than being silently filled with synthetic bars.
    """

    if len(half_lives) != len(EWMA_VOLATILITY_LABELS):
        raise ValueError("EWMA volatility requires fast, medium, and slow half-lives")
    normalized_half_lives = tuple(int(value) for value in half_lives)
    decays = {
        label: _ewma_decay(half_life)
        for label, half_life in zip(EWMA_VOLATILITY_LABELS, normalized_half_lives)
    }

    if frame.is_empty():
        return pl.DataFrame(
            {
                "timestamp": [],
                "log_return": [],
                "ewma_vol_fast_pct": [],
                "ewma_vol_medium_pct": [],
                "ewma_vol_slow_pct": [],
                "fast_slow_ratio": [],
                "ewma_observations": [],
            }
        )

    sorted_frame = frame.sort("timestamp")
    closes = sorted_frame["close"].to_list()
    variance = dict.fromkeys(EWMA_VOLATILITY_LABELS)
    observations = 0
    observation_counts: list[int] = []
    output = {label: [] for label in EWMA_VOLATILITY_LABELS}
    log_returns: list[float | None] = []
    ratios: list[float | None] = []
    previous_close: float | None = None

    for raw_close in closes:
        close = float(raw_close) if _is_valid(raw_close) else None
        if close is None or close <= 0.0:
            log_returns.append(None)
            for label in EWMA_VOLATILITY_LABELS:
                output[label].append(None)
            ratios.append(None)
            observation_counts.append(observations)
            previous_close = None
            continue

        if previous_close is None:
            log_returns.append(None)
            for label in EWMA_VOLATILITY_LABELS:
                output[label].append(None)
            ratios.append(None)
            observation_counts.append(observations)
            previous_close = close
            continue

        log_return = math.log(close / previous_close)
        squared_return = log_return * log_return
        observations += 1
        log_returns.append(log_return)
        for label in EWMA_VOLATILITY_LABELS:
            prior_variance = variance[label]
            decay = decays[label]
            updated_variance = (
                squared_return
                if prior_variance is None
                else (decay * float(prior_variance)) + ((1.0 - decay) * squared_return)
            )
            variance[label] = updated_variance
            output[label].append(100.0 * math.sqrt(updated_variance))

        fast = output["fast"][-1]
        slow = output["slow"][-1]
        if _is_valid(fast) and _is_valid(slow) and float(slow) > 0.0:
            ratios.append(float(fast) / float(slow))
        else:
            ratios.append(None)
        observation_counts.append(observations)
        previous_close = close

    return pl.DataFrame(
        {
            "timestamp": sorted_frame["timestamp"],
            "log_return": log_returns,
            "ewma_vol_fast_pct": output["fast"],
            "ewma_vol_medium_pct": output["medium"],
            "ewma_vol_slow_pct": output["slow"],
            "fast_slow_ratio": ratios,
            "ewma_observations": observation_counts,
        }
    )


def compute_cusum_trend(
    frame: pl.DataFrame,
    *,
    sensitivity: str = DEFAULT_CUSUM_SENSITIVITY,
) -> pl.DataFrame:
    """Compute a causal, price-scale-invariant CUSUM Trend diagnostic.

    The Hull residual is standardized by its prior-only rolling population
    standard deviation.  Pressure is not updated until that scale is mature;
    triggers then reset pressure before regime and trailing-stop values are
    emitted.  Outputs from close ``t`` are actionable no earlier than ``t+1``.
    """

    if frame.is_empty():
        return pl.DataFrame(
            {
                "timestamp": [],
                "hma_base": [],
                "residual": [],
                "res_std": [],
                "scale_ready": [],
                "status": [],
                "up_band": [],
                "dn_band": [],
                "bull_pressure": [],
                "bear_pressure": [],
                "trail_stop": [],
                "regime": [],
                "pressure_pct": [],
                "bull_start": [],
                "bear_start": [],
                "candle_color": [],
            }
        )

    sorted_frame = frame.sort("timestamp")
    engine = CusumTrendEngine(sensitivity)
    rows = [
        engine.update(timestamp=timestamp, close=close)
        for timestamp, close in zip(
            sorted_frame["timestamp"].to_list(),
            sorted_frame["close"].to_list(),
        )
    ]

    return pl.DataFrame(
        {
            "timestamp": sorted_frame["timestamp"],
            **{
                column: [row[column] for row in rows]
                for column in (
                    "hma_base",
                    "residual",
                    "res_std",
                    "scale_ready",
                    "status",
                    "up_band",
                    "dn_band",
                    "bull_pressure",
                    "bear_pressure",
                    "pressure_pct",
                    "regime",
                    "trail_stop",
                    "bull_start",
                    "bear_start",
                    "candle_color",
                )
            },
        }
    )


def value_series(
    frame: pl.DataFrame,
    *,
    value_col: str,
    time_col: str = "time",
) -> list[dict[str, float | int]]:
    """Convert non-null indicator values into Lightweight Charts line data."""
    if frame.is_empty() or value_col not in frame.columns:
        return []
    rows = (
        frame.filter(pl.col(value_col).is_not_null())
        .select([time_col, value_col])
        .rename({value_col: "value"})
        .to_dicts()
    )
    return [{"time": int(row["time"]), "value": float(row["value"])} for row in rows]
