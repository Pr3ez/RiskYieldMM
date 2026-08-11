"""Streaming, lookahead-safe signal engine for the local Analyst chart.

The engine uses one scalar update path for both historical replay and live bar
updates.  It intentionally avoids full-sequence HMM smoothing and Viterbi
decoding.  The regime layer is a fixed-prototype four-state Gaussian HMM whose
posterior is advanced with the one-step forward recursion after each completed
bar.  Its parameters are diagnostic defaults, not trained alpha.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import polars as pl

ONLINE_SIGNAL_VERSION = "online_signal_v2"
FINALITY_SAFETY_LAG_SECONDS = 5
TREND_HORIZONS = (12, 48, 192)
TREND_LABELS = ("fast", "medium", "slow")
REGIME_LABELS = (
    "Bull trend",
    "Bear trend",
    "Range / chop",
    "Transition risk",
)


class RevisionRequired(ValueError):
    """Raised when finalized history differs from the engine's current state."""


@dataclass(frozen=True)
class OnlineSignalConfig:
    """Versioned parameters for the causal trend and regime engine."""

    horizons: tuple[int, int, int] = TREND_HORIZONS
    trend_z_clip: float = 8.0
    aligned_score: float = 0.20
    aligned_quality: float = 0.25
    developing_score: float = 0.08
    change_risk_threshold: float = 0.55
    expected_interval_seconds: int = 3600
    # ``None`` means exact cadence.  A larger explicit value permits only
    # forward, interval-aligned gaps up to that duration (for example a known
    # exchange weekend) without using a future calendar or future bars.
    max_gap_seconds: int | None = None

    def digest(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class OnlineSignalEngine:
    """Stateful closed-bar engine with JSON-safe snapshot/restore support."""

    # Observation order: trend score, path quality, volatility pressure,
    # normalized range pressure.  These prototypes are deliberately fixed so
    # live inference never refits on the current chart request.
    _EMISSION_MEANS = (
        (0.55, 0.55, 0.05, 0.25),
        (-0.55, 0.55, 0.05, 0.25),
        (0.00, 0.18, -0.15, 0.20),
        (0.00, 0.30, 0.65, 0.70),
    )
    _EMISSION_STDS = (
        (0.35, 0.30, 0.45, 0.35),
        (0.35, 0.30, 0.45, 0.35),
        (0.30, 0.24, 0.40, 0.30),
        (0.42, 0.32, 0.38, 0.32),
    )
    _TRANSITION = (
        (0.940, 0.005, 0.040, 0.015),
        (0.005, 0.940, 0.040, 0.015),
        (0.020, 0.020, 0.930, 0.030),
        (0.080, 0.080, 0.240, 0.600),
    )
    _INITIAL_POSTERIOR = (0.10, 0.10, 0.70, 0.10)

    def __init__(self, config: OnlineSignalConfig | None = None) -> None:
        self.config = config or OnlineSignalConfig()
        _validate_config(self.config)
        self._decays = {
            label: math.exp(-math.log(2.0) / float(horizon))
            for label, horizon in zip(TREND_LABELS, self.config.horizons)
        }
        self.previous_close: float | None = None
        self.variances: dict[str, float | None] = dict.fromkeys(TREND_LABELS)
        self.returns: deque[float] = deque(maxlen=max(self.config.horizons))
        self.last_timestamp: datetime | None = None
        self.previous_trend_state: int | None = None
        self.posterior = list(self._INITIAL_POSTERIOR)
        self.regime_state: int | None = None
        self.regime_duration = 0
        self.risk_active = False
        self.bars_seen = 0
        self.last_input_fingerprint: str | None = None
        self.last_output: dict[str, Any] | None = None

    def update(
        self,
        *,
        timestamp: datetime,
        open_value: float | None,
        high: float | None,
        low: float | None,
        close: float | None,
        volume: float | None = None,
        is_final: bool = True,
        scheduled_gap: bool = False,
    ) -> dict[str, Any]:
        """Advance the engine once for a completed bar.

        ``timestamp`` is the bar-open time.  The returned point is stamped at
        ``timestamp + expected_interval``—the earliest next-bar time at which
        the closed-bar observation can be acted upon.  A non-nominal interval
        is carried only when the caller explicitly marks it as a scheduled gap
        and the configured fixed tolerance permits it.
        """

        timestamp = _utc(timestamp)
        if not isinstance(scheduled_gap, bool):
            raise ValueError("scheduled_gap must be a bool")
        available_at = timestamp + timedelta(
            seconds=self.config.expected_interval_seconds
        )
        if not is_final:
            return self._empty_point(
                timestamp, available_at, status="forming_bar_not_processed"
            )
        input_fingerprint = _bar_fingerprint(
            timestamp=timestamp,
            open_value=open_value,
            high=high,
            low=low,
            close=close,
            volume=volume,
            scheduled_gap=scheduled_gap,
        )
        previous_timestamp = self.last_timestamp
        if previous_timestamp is not None and timestamp == previous_timestamp:
            if (
                input_fingerprint == self.last_input_fingerprint
                and self.last_output is not None
            ):
                return dict(self.last_output)
            raise RevisionRequired(
                "Finalized bar changed at the current timestamp; replay is required"
            )
        if previous_timestamp is not None and timestamp < previous_timestamp:
            raise RevisionRequired(
                "Finalized bar predates the current engine state; replay is required"
            )

        self.last_timestamp = timestamp
        self.bars_seen += 1
        current_close, invalid_status = _validated_ohlc(
            open_value=open_value,
            high=high,
            low=low,
            close=close,
        )
        if invalid_status is not None:
            self._reset_signal_state()
            return self._remember_finalized(
                input_fingerprint,
                self._empty_point(
                    timestamp,
                    available_at,
                    status=invalid_status,
                ),
            )
        assert current_close is not None

        expected_interval = timedelta(seconds=self.config.expected_interval_seconds)
        if previous_timestamp is not None and not _elapsed_is_allowed(
            timestamp - previous_timestamp,
            expected_interval=expected_interval,
            max_gap_seconds=self.config.max_gap_seconds,
            scheduled_gap=scheduled_gap,
        ):
            elapsed = timestamp - previous_timestamp
            self._reset_signal_state()
            self.previous_close = current_close
            return self._remember_finalized(
                input_fingerprint,
                self._empty_point(
                    timestamp,
                    available_at,
                    status=f"cadence_gap_reset_{_format_seconds(elapsed)}",
                ),
            )

        if self.previous_close is None:
            self.previous_close = current_close
            return self._remember_finalized(
                input_fingerprint,
                self._empty_point(timestamp, available_at, status="seed_close"),
            )

        log_return = math.log(current_close / self.previous_close)
        prior_sigmas = {
            label: (None if variance is None else math.sqrt(max(float(variance), 0.0)))
            for label, variance in self.variances.items()
        }
        self.returns.append(log_return)

        horizon_values: dict[str, dict[str, float | None]] = {}
        for label, horizon in zip(TREND_LABELS, self.config.horizons):
            horizon_values[label] = self._trend_horizon(
                horizon=horizon,
                prior_sigma=prior_sigmas[label],
            )

        # The trend score uses sigma_(t-1).  Only after calculating it do we
        # update variance with r_t, preserving the causal timing contract.
        ewma_volatility: dict[str, float] = {}
        squared_return = log_return * log_return
        for label in TREND_LABELS:
            prior_variance = self.variances[label]
            decay = self._decays[label]
            variance = (
                squared_return
                if prior_variance is None
                else decay * float(prior_variance) + (1.0 - decay) * squared_return
            )
            self.variances[label] = variance
            ewma_volatility[label] = 100.0 * math.sqrt(variance)

        trend = self._trend_state(horizon_values)
        fast_vol = ewma_volatility["fast"]
        slow_vol = ewma_volatility["slow"]
        vol_ratio = fast_vol / slow_vol if slow_vol > 0.0 else None
        volatility_pressure = (
            None
            if vol_ratio is None or vol_ratio <= 0.0
            else math.tanh(math.log(vol_ratio) / 0.35)
        )
        range_pressure = _range_pressure(
            high=high,
            low=low,
            prior_sigma=prior_sigmas["slow"],
        )
        regime = self._regime_update(
            trend_score=trend["trend_score"],
            path_quality=trend["path_quality"],
            volatility_pressure=volatility_pressure,
            range_pressure=range_pressure,
        )

        self.previous_close = current_close
        point = {
            "source_timestamp": timestamp,
            "timestamp": available_at,
            "available_at": available_at,
            "earliest_execution_at": available_at,
            "availability": "post_close_usable_next_bar",
            "status": "ok" if trend["trend_score"] is not None else "warmup",
            "log_return": log_return,
            "ewma_vol_fast_pct": fast_vol,
            "ewma_vol_medium_pct": ewma_volatility["medium"],
            "ewma_vol_slow_pct": slow_vol,
            "fast_slow_ratio": vol_ratio,
            **{
                f"trend_z_{label}": horizon_values[label]["z"] for label in TREND_LABELS
            },
            **{
                f"path_efficiency_{label}": horizon_values[label]["efficiency"]
                for label in TREND_LABELS
            },
            **{
                f"trend_component_{label}": horizon_values[label]["component"]
                for label in TREND_LABELS
            },
            **trend,
            "volatility_pressure": volatility_pressure,
            "range_pressure": range_pressure,
            **regime,
        }
        return self._remember_finalized(input_fingerprint, point)

    def snapshot(self) -> dict[str, Any]:
        """Return a versioned JSON-safe state snapshot."""

        payload = {
            "algorithm_version": ONLINE_SIGNAL_VERSION,
            "config": _config_payload(self.config),
            "config_digest": self.config.digest(),
            "previous_close": self.previous_close,
            "variances": dict(self.variances),
            "returns": list(self.returns),
            "last_timestamp": (
                None if self.last_timestamp is None else _iso(self.last_timestamp)
            ),
            "previous_trend_state": self.previous_trend_state,
            "posterior": list(self.posterior),
            "regime_state": self.regime_state,
            "regime_duration": self.regime_duration,
            "risk_active": self.risk_active,
            "bars_seen": self.bars_seen,
            "last_input_fingerprint": self.last_input_fingerprint,
            "last_output": (
                None if self.last_output is None else _serialize_point(self.last_output)
            ),
        }
        checksum_source = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        return {
            **payload,
            "checksum": hashlib.sha256(checksum_source.encode("utf-8")).hexdigest(),
        }

    @classmethod
    def restore(
        cls,
        snapshot: dict[str, Any],
        *,
        expected_config: OnlineSignalConfig | None = None,
    ) -> OnlineSignalEngine:
        """Restore a snapshot after verifying its version, config and checksum."""

        if not isinstance(snapshot, dict):
            raise ValueError("Online signal snapshot must be a mapping")
        raw = dict(snapshot)
        checksum = str(raw.pop("checksum", ""))
        try:
            checksum_source = json.dumps(
                raw, sort_keys=True, separators=(",", ":"), allow_nan=False
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("Online signal snapshot is not JSON-safe") from exc
        expected_checksum = hashlib.sha256(checksum_source.encode("utf-8")).hexdigest()
        if checksum != expected_checksum:
            raise ValueError("Online signal snapshot checksum mismatch")
        if raw.get("algorithm_version") != ONLINE_SIGNAL_VERSION:
            raise ValueError("Online signal snapshot algorithm version mismatch")
        raw_config = raw.get("config")
        if not isinstance(raw_config, dict):
            raise ValueError("Online signal snapshot config is invalid")
        config_values = dict(raw_config)
        config_values["horizons"] = tuple(config_values.get("horizons", ()))
        try:
            config = OnlineSignalConfig(**config_values)
            _validate_config(config)
        except (TypeError, ValueError) as exc:
            raise ValueError("Online signal snapshot config is invalid") from exc
        if raw.get("config_digest") != config.digest():
            raise ValueError("Online signal snapshot config digest mismatch")
        if expected_config is not None and config != expected_config:
            raise ValueError("Online signal snapshot does not match expected config")

        engine = cls(config)
        previous_close = raw.get("previous_close")
        if previous_close is not None and _positive_float(previous_close) is None:
            raise ValueError("Online signal snapshot previous close is invalid")
        engine.previous_close = (
            None if previous_close is None else float(previous_close)
        )

        variances = raw.get("variances")
        if not isinstance(variances, dict) or set(variances) != set(TREND_LABELS):
            raise ValueError("Online signal snapshot variances are invalid")
        restored_variances: dict[str, float | None] = {}
        for label in TREND_LABELS:
            value = variances[label]
            parsed = None if value is None else _finite_float(value)
            if value is not None and (parsed is None or parsed < 0.0):
                raise ValueError("Online signal snapshot variances are invalid")
            restored_variances[label] = parsed
        engine.variances = restored_variances

        raw_returns = raw.get("returns")
        if not isinstance(raw_returns, list) or len(raw_returns) > max(config.horizons):
            raise ValueError("Online signal snapshot return buffer is invalid")
        restored_returns = [_finite_float(value) for value in raw_returns]
        if any(value is None for value in restored_returns):
            raise ValueError("Online signal snapshot return buffer is invalid")
        engine.returns = deque(
            (float(value) for value in restored_returns if value is not None),
            maxlen=max(config.horizons),
        )
        last_timestamp = raw.get("last_timestamp")
        try:
            engine.last_timestamp = (
                None if last_timestamp is None else _parse_iso(str(last_timestamp))
            )
        except ValueError as exc:
            raise ValueError("Online signal snapshot timestamp is invalid") from exc

        previous_trend_state = _optional_int(raw.get("previous_trend_state"))
        if previous_trend_state not in (None, -2, -1, 0, 1, 2):
            raise ValueError("Online signal snapshot trend state is invalid")
        engine.previous_trend_state = previous_trend_state

        raw_posterior = raw.get("posterior")
        if not isinstance(raw_posterior, list):
            raise ValueError("Online signal snapshot posterior is invalid")
        try:
            posterior = [float(value) for value in raw_posterior]
        except (TypeError, ValueError) as exc:
            raise ValueError("Online signal snapshot posterior is invalid") from exc
        if len(posterior) != len(REGIME_LABELS) or not all(
            math.isfinite(value) and value >= 0.0 for value in posterior
        ):
            raise ValueError("Online signal snapshot posterior is invalid")
        posterior_sum = math.fsum(posterior)
        if posterior_sum <= 0.0 or not math.isclose(
            posterior_sum, 1.0, rel_tol=1e-12, abs_tol=1e-12
        ):
            raise ValueError("Online signal snapshot posterior mass is invalid")
        # Preserve the serialized IEEE-754 values exactly. Re-normalizing here
        # would make a restore diverge by one ulp from uninterrupted replay.
        engine.posterior = posterior
        regime_state = _optional_int(raw.get("regime_state"))
        if regime_state not in (None, 0, 1, 2, 3):
            raise ValueError("Online signal snapshot regime state is invalid")
        engine.regime_state = regime_state
        engine.regime_duration = _nonnegative_int(
            raw.get("regime_duration"), field="regime duration"
        )
        if (regime_state is None) != (engine.regime_duration == 0):
            raise ValueError("Online signal snapshot regime duration is inconsistent")
        risk_active = raw.get("risk_active")
        if not isinstance(risk_active, bool):
            raise ValueError("Online signal snapshot risk flag is invalid")
        engine.risk_active = risk_active
        engine.bars_seen = _nonnegative_int(raw.get("bars_seen"), field="bar count")

        fingerprint = raw.get("last_input_fingerprint")
        serialized_output = raw.get("last_output")
        if engine.last_timestamp is None:
            if fingerprint is not None or serialized_output is not None:
                raise ValueError(
                    "Online signal snapshot duplicate cache is inconsistent"
                )
            if engine.bars_seen != 0:
                raise ValueError("Online signal snapshot bar count is inconsistent")
        else:
            if (
                not isinstance(fingerprint, str)
                or len(fingerprint) != 64
                or any(character not in "0123456789abcdef" for character in fingerprint)
                or not isinstance(serialized_output, dict)
            ):
                raise ValueError("Online signal snapshot duplicate cache is invalid")
            if engine.bars_seen <= 0:
                raise ValueError("Online signal snapshot bar count is inconsistent")
            engine.last_input_fingerprint = fingerprint
            engine.last_output = _deserialize_point(serialized_output)
            if engine.last_output.get("source_timestamp") != engine.last_timestamp:
                raise ValueError("Online signal snapshot cached point is inconsistent")
            expected_available_at = engine.last_timestamp + timedelta(
                seconds=config.expected_interval_seconds
            )
            if any(
                engine.last_output.get(field) != expected_available_at
                for field in (
                    "timestamp",
                    "available_at",
                    "earliest_execution_at",
                )
            ):
                raise ValueError("Online signal snapshot cached point is inconsistent")
        return engine

    def _trend_horizon(
        self,
        *,
        horizon: int,
        prior_sigma: float | None,
    ) -> dict[str, float | None]:
        if len(self.returns) < horizon or prior_sigma is None or prior_sigma <= 0.0:
            return {"z": None, "efficiency": None, "component": None}
        window = list(self.returns)[-horizon:]
        net_return = math.fsum(window)
        path = math.fsum(abs(value) for value in window)
        denominator = prior_sigma * math.sqrt(float(horizon))
        if denominator <= 0.0:
            return {"z": None, "efficiency": None, "component": None}
        raw_z = net_return / denominator
        z_value = min(max(raw_z, -self.config.trend_z_clip), self.config.trend_z_clip)
        efficiency = min(
            max(0.0 if path == 0.0 else abs(net_return) / path, 0.0),
            1.0,
        )
        component = efficiency * math.tanh(z_value / 2.0)
        return {"z": z_value, "efficiency": efficiency, "component": component}

    def _trend_state(
        self, horizon_values: dict[str, dict[str, float | None]]
    ) -> dict[str, Any]:
        values = [horizon_values[label] for label in TREND_LABELS]
        if any(item["component"] is None for item in values):
            return {
                "trend_score": None,
                "path_quality": None,
                "trend_agreement": None,
                "trend_state_code": None,
                "trend_state": "Warm-up / unavailable",
                "trend_bull_start": False,
                "trend_bear_start": False,
                "trend_exit": False,
            }

        components = [float(item["component"]) for item in values]
        efficiencies = [float(item["efficiency"]) for item in values]
        z_values = [float(item["z"]) for item in values]
        trend_score = math.fsum(components) / len(components)
        path_quality = math.fsum(efficiencies) / len(efficiencies)
        signs = [1 if value > 0.0 else -1 if value < 0.0 else 0 for value in z_values]
        agreement = math.fsum(signs) / len(signs)
        if (
            agreement == 1.0
            and trend_score >= self.config.aligned_score
            and path_quality >= self.config.aligned_quality
        ):
            code, state = 2, "Bullish aligned"
        elif (
            agreement == -1.0
            and trend_score <= -self.config.aligned_score
            and path_quality >= self.config.aligned_quality
        ):
            code, state = -2, "Bearish aligned"
        elif agreement >= (1.0 / 3.0) and trend_score >= self.config.developing_score:
            code, state = 1, "Bullish developing"
        elif agreement <= (-1.0 / 3.0) and trend_score <= -self.config.developing_score:
            code, state = -1, "Bearish developing"
        else:
            code, state = 0, "Mixed / choppy"

        previous = self.previous_trend_state
        bull_start = code == 2 and previous != 2
        bear_start = code == -2 and previous != -2
        trend_exit = previous is not None and abs(previous) == 2 and abs(code) != 2
        self.previous_trend_state = code
        return {
            "trend_score": trend_score,
            "path_quality": path_quality,
            "trend_agreement": agreement,
            "trend_state_code": code,
            "trend_state": state,
            "trend_bull_start": bull_start,
            "trend_bear_start": bear_start,
            "trend_exit": trend_exit,
        }

    def _regime_update(
        self,
        *,
        trend_score: float | None,
        path_quality: float | None,
        volatility_pressure: float | None,
        range_pressure: float | None,
    ) -> dict[str, Any]:
        if any(
            value is None
            for value in (
                trend_score,
                path_quality,
                volatility_pressure,
                range_pressure,
            )
        ):
            return _empty_regime_fields()

        observation = (
            float(trend_score),
            float(path_quality),
            float(volatility_pressure),
            float(range_pressure),
        )
        prior = [
            math.fsum(
                self.posterior[previous] * self._TRANSITION[previous][current]
                for previous in range(len(REGIME_LABELS))
            )
            for current in range(len(REGIME_LABELS))
        ]
        log_weights = []
        log_emissions = []
        for state_idx, (means, stds) in enumerate(
            zip(self._EMISSION_MEANS, self._EMISSION_STDS)
        ):
            log_emission = 0.0
            for value, mean, std in zip(observation, means, stds):
                z_value = (value - mean) / std
                log_emission += -0.5 * z_value * z_value - math.log(std)
            log_emissions.append(log_emission)
            log_weights.append(math.log(max(prior[state_idx], 1e-300)) + log_emission)
        maximum = max(log_weights)
        weights = [math.exp(value - maximum) for value in log_weights]
        weight_sum = math.fsum(weights)
        next_posterior = [value / weight_sum for value in weights]

        previous_posterior = self.posterior
        previous_state = self.regime_state
        state = max(range(len(REGIME_LABELS)), key=next_posterior.__getitem__)
        log_normalizer = maximum + math.log(weight_sum)
        filtered_switch_probability = math.fsum(
            math.exp(
                math.log(max(previous_posterior[previous], 1e-300))
                + math.log(max(self._TRANSITION[previous][current], 1e-300))
                + log_emissions[current]
                - log_normalizer
            )
            for previous in range(len(REGIME_LABELS))
            for current in range(len(REGIME_LABELS))
            if previous != current
        )
        # The first term is a formal filtered HMM switch probability.  The
        # second is the current weight of the explicitly defined transition
        # prototype.  Their maximum remains a versioned diagnostic heuristic,
        # never a calibrated probability or a default execution veto.
        change_risk = max(next_posterior[3], filtered_switch_probability)
        risk_active = change_risk >= self.config.change_risk_threshold
        risk_start = risk_active and not self.risk_active
        state_changed = previous_state is not None and previous_state != state
        self.regime_duration = (
            self.regime_duration + 1
            if previous_state is not None and previous_state == state
            else 1
        )
        self.posterior = next_posterior
        self.regime_state = state
        self.risk_active = risk_active
        entropy = -math.fsum(
            probability * math.log(max(probability, 1e-300))
            for probability in next_posterior
        ) / math.log(float(len(REGIME_LABELS)))
        predictive_state_probability = prior[state]
        return {
            "regime_model": "fixed_prototype_gaussian_hmm_forward_v1",
            "regime_state": state,
            "regime_label": REGIME_LABELS[state],
            "regime_probability_bull": next_posterior[0],
            "regime_probability_bear": next_posterior[1],
            "regime_probability_range": next_posterior[2],
            "regime_probability_transition": next_posterior[3],
            "regime_confidence": max(next_posterior),
            "regime_entropy": entropy,
            "regime_filtered_switch_probability": filtered_switch_probability,
            "regime_change_risk": change_risk,
            "regime_risk_active": risk_active,
            "regime_risk_start": risk_start,
            "regime_state_changed": state_changed,
            "regime_state_duration_bars": self.regime_duration,
            "regime_predictive_state_probability": predictive_state_probability,
            # Compatibility alias for existing chart payloads.  This is the
            # forward predictive prior mass of the selected current state, not
            # merely one transition-matrix cell between two argmax states.
            "regime_transition_probability": predictive_state_probability,
        }

    def _empty_point(
        self,
        source_timestamp: datetime,
        available_at: datetime,
        *,
        status: str,
    ) -> dict[str, Any]:
        return {
            "source_timestamp": source_timestamp,
            "timestamp": available_at,
            "available_at": available_at,
            "earliest_execution_at": available_at,
            "availability": "post_close_usable_next_bar",
            "status": status,
            "log_return": None,
            "ewma_vol_fast_pct": None,
            "ewma_vol_medium_pct": None,
            "ewma_vol_slow_pct": None,
            "fast_slow_ratio": None,
            **{f"trend_z_{label}": None for label in TREND_LABELS},
            **{f"path_efficiency_{label}": None for label in TREND_LABELS},
            **{f"trend_component_{label}": None for label in TREND_LABELS},
            "trend_score": None,
            "path_quality": None,
            "trend_agreement": None,
            "trend_state_code": None,
            "trend_state": "Warm-up / unavailable",
            "trend_bull_start": False,
            "trend_bear_start": False,
            "trend_exit": False,
            "volatility_pressure": None,
            "range_pressure": None,
            **_empty_regime_fields(),
        }

    def _remember_finalized(
        self,
        input_fingerprint: str,
        point: dict[str, Any],
    ) -> dict[str, Any]:
        self.last_input_fingerprint = input_fingerprint
        self.last_output = dict(point)
        return dict(point)

    def _reset_signal_state(self) -> None:
        self.previous_close = None
        self.variances = dict.fromkeys(TREND_LABELS)
        self.returns.clear()
        self.previous_trend_state = None
        self.posterior = list(self._INITIAL_POSTERIOR)
        self.regime_state = None
        self.regime_duration = 0
        self.risk_active = False


def compute_online_signal_frame(
    frame: pl.DataFrame,
    *,
    config: OnlineSignalConfig | None = None,
    now: datetime | None = None,
    safety_lag_seconds: float = FINALITY_SAFETY_LAG_SECONDS,
) -> tuple[pl.DataFrame, OnlineSignalEngine]:
    """Replay safely closed OHLCV rows through the live scalar update path."""

    engine = OnlineSignalEngine(config)
    if not math.isfinite(safety_lag_seconds) or safety_lag_seconds < 0.0:
        raise ValueError("safety_lag_seconds must be finite and non-negative")
    if frame.is_empty():
        return pl.DataFrame(), engine
    current_time = _utc(now or datetime.now(timezone.utc)) - timedelta(
        seconds=safety_lag_seconds
    )
    rows: list[dict[str, Any]] = []
    sorted_frame = frame.unique(subset=["timestamp"], keep="last").sort("timestamp")
    interval = timedelta(seconds=engine.config.expected_interval_seconds)
    for row in sorted_frame.iter_rows(named=True):
        timestamp = _utc(row["timestamp"])
        if timestamp + interval > current_time:
            break
        rows.append(
            engine.update(
                timestamp=timestamp,
                open_value=row.get("open"),
                high=row.get("high"),
                low=row.get("low"),
                close=row.get("close"),
                volume=row.get("volume"),
                is_final=True,
                scheduled_gap=row.get("is_session_open_bar") is True,
            )
        )
    return pl.DataFrame(rows, infer_schema_length=None), engine


def _empty_regime_fields() -> dict[str, Any]:
    return {
        "regime_model": "fixed_prototype_gaussian_hmm_forward_v1",
        "regime_state": None,
        "regime_label": "Warm-up / unavailable",
        "regime_probability_bull": None,
        "regime_probability_bear": None,
        "regime_probability_range": None,
        "regime_probability_transition": None,
        "regime_confidence": None,
        "regime_entropy": None,
        "regime_filtered_switch_probability": None,
        "regime_change_risk": None,
        "regime_risk_active": False,
        "regime_risk_start": False,
        "regime_state_changed": False,
        "regime_state_duration_bars": None,
        "regime_predictive_state_probability": None,
        "regime_transition_probability": None,
    }


def _range_pressure(*, high: Any, low: Any, prior_sigma: float | None) -> float | None:
    high_value = _positive_float(high)
    low_value = _positive_float(low)
    if (
        high_value is None
        or low_value is None
        or high_value < low_value
        or prior_sigma is None
        or prior_sigma <= 0.0
    ):
        return None
    range_return = math.log(high_value / low_value)
    return min(max(math.tanh(range_return / (3.0 * prior_sigma)), 0.0), 1.0)


def _validate_config(config: OnlineSignalConfig) -> None:
    horizons = config.horizons
    if (
        len(horizons) != len(TREND_LABELS)
        or any(
            isinstance(value, bool) or not isinstance(value, int) for value in horizons
        )
        or any(value <= 0 for value in horizons)
        or tuple(sorted(horizons)) != tuple(horizons)
        or len(set(horizons)) != len(horizons)
    ):
        raise ValueError(
            "horizons must contain three strictly increasing positive ints"
        )
    if (
        isinstance(config.expected_interval_seconds, bool)
        or not isinstance(config.expected_interval_seconds, int)
        or config.expected_interval_seconds <= 0
    ):
        raise ValueError("expected_interval_seconds must be a positive int")
    if config.max_gap_seconds is not None and (
        isinstance(config.max_gap_seconds, bool)
        or not isinstance(config.max_gap_seconds, int)
        or config.max_gap_seconds < config.expected_interval_seconds
    ):
        raise ValueError(
            "max_gap_seconds must be None or at least expected_interval_seconds"
        )
    finite_parameters = (
        config.trend_z_clip,
        config.aligned_score,
        config.aligned_quality,
        config.developing_score,
        config.change_risk_threshold,
    )
    if not all(math.isfinite(value) for value in finite_parameters):
        raise ValueError("signal thresholds must be finite")
    if config.trend_z_clip <= 0.0:
        raise ValueError("trend_z_clip must be positive")
    if not 0.0 <= config.developing_score <= config.aligned_score <= 1.0:
        raise ValueError("trend score thresholds are invalid")
    if not 0.0 <= config.aligned_quality <= 1.0:
        raise ValueError("aligned_quality must be between zero and one")
    if not 0.0 <= config.change_risk_threshold <= 1.0:
        raise ValueError("change_risk_threshold must be between zero and one")


def _config_payload(config: OnlineSignalConfig) -> dict[str, Any]:
    payload = asdict(config)
    payload["horizons"] = list(config.horizons)
    return payload


def _validated_ohlc(
    *,
    open_value: Any,
    high: Any,
    low: Any,
    close: Any,
) -> tuple[float | None, str | None]:
    close_value = _positive_float(close)
    if close_value is None:
        return None, "invalid_close_reset"
    open_float = _positive_float(open_value)
    high_float = _positive_float(high)
    low_float = _positive_float(low)
    if (
        open_float is None
        or high_float is None
        or low_float is None
        or high_float < low_float
        or high_float < max(open_float, close_value)
        or low_float > min(open_float, close_value)
    ):
        return close_value, "invalid_ohlc_reset"
    return close_value, None


def _bar_fingerprint(
    *,
    timestamp: datetime,
    open_value: Any,
    high: Any,
    low: Any,
    close: Any,
    volume: Any,
    scheduled_gap: bool,
) -> str:
    payload = {
        "timestamp": _iso(timestamp),
        "open": _fingerprint_value(open_value),
        "high": _fingerprint_value(high),
        "low": _fingerprint_value(low),
        "close": _fingerprint_value(close),
        "volume": _fingerprint_value(volume),
        "scheduled_gap": bool(scheduled_gap),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _fingerprint_value(value: Any) -> str | None:
    if value is None:
        return None
    parsed = _finite_float(value)
    if parsed is not None:
        return parsed.hex()
    try:
        nonfinite = float(value)
    except (TypeError, ValueError):
        return f"invalid:{type(value).__name__}:{value!s}"
    if math.isnan(nonfinite):
        return "nonfinite:nan"
    return "nonfinite:+inf" if nonfinite > 0.0 else "nonfinite:-inf"


def _elapsed_is_allowed(
    elapsed: timedelta,
    *,
    expected_interval: timedelta,
    max_gap_seconds: int | None,
    scheduled_gap: bool,
) -> bool:
    if elapsed == expected_interval:
        return True
    if not scheduled_gap or max_gap_seconds is None:
        return False
    tolerance = timedelta(seconds=max_gap_seconds)
    return (
        elapsed > timedelta(0)
        and elapsed <= tolerance
        and elapsed % expected_interval == timedelta(0)
    )


def _format_seconds(elapsed: timedelta) -> str:
    seconds = elapsed.total_seconds()
    if seconds.is_integer():
        return f"{int(seconds)}s"
    return f"{seconds:.6f}".rstrip("0").rstrip(".") + "s"


_POINT_TIME_FIELDS = (
    "source_timestamp",
    "timestamp",
    "available_at",
    "earliest_execution_at",
)


def _serialize_point(point: dict[str, Any]) -> dict[str, Any]:
    serialized = dict(point)
    for field in _POINT_TIME_FIELDS:
        value = serialized.get(field)
        if not isinstance(value, datetime):
            raise ValueError("Online signal cached point timestamp is invalid")
        serialized[field] = _iso(value)
    return serialized


def _deserialize_point(point: dict[str, Any]) -> dict[str, Any]:
    restored = dict(point)
    try:
        for field in _POINT_TIME_FIELDS:
            value = restored.get(field)
            if not isinstance(value, str):
                raise ValueError
            restored[field] = _parse_iso(value)
    except ValueError as exc:
        raise ValueError("Online signal cached point timestamp is invalid") from exc
    if not isinstance(restored.get("status"), str):
        raise ValueError("Online signal cached point status is invalid")
    return restored


def _nonnegative_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"Online signal snapshot {field} is invalid")
    return value


def _positive_float(value: Any) -> float | None:
    result = _finite_float(value)
    return result if result is not None and result > 0.0 else None


def _finite_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("Online signal snapshot state value is invalid")
    return value


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _parse_iso(value: str) -> datetime:
    return _utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
