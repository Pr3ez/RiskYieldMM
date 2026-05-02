"""Kalman Filter helper for state estimation.

Implements a 3D Kalman filter to estimate:
1. Price level (filtered)
2. Velocity (trend/momentum)
3. Acceleration (rate of change of trend)

Provides filtered state estimates and prediction errors as features.

Source contract:
- Kalman (1960): https://www.cs.unc.edu/~welch/kalman/media/pdf/Kalman1960.pdf
- strict helper live-parity rationale:
  `notebooks/notes/htf_helper_source_backed_validity_audit_2026-04-12.md`
- streaming-state redesign plan:
  `notebooks/notes/htf_kalman_streaming_state_implementation_plan_2026-04-13.md`

Runtime contract:
- Kalman is a true streaming-state helper
- `fit()` builds the train-end streaming state
- `transform()` starts from that train-end state instead of cold-starting
- Python fallback and Rust runtime intentionally use the same carried-state
  contract so batch HTF generation and live generation can match exactly
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from scripts.target_models.helpers.base import BaseHelper, HelperConfig, HelperOutput

try:
    import riskyield_rust as _rust

    HAS_RUST = hasattr(_rust, "py_kalman_transform_with_state")
except ImportError:
    _rust = None
    HAS_RUST = False


KALMAN_STATE_VERSION = 1


@dataclass(frozen=True)
class KalmanStreamingState:
    """Serializable Kalman streaming state.

    A true streaming contract must carry both:
    - the hidden Kalman filter state (`x`, `P`)
    - the expanding statistics behind derived features (`zscore`, `regime`)

    Carrying only the filter state would keep the filter continuous but still
    reset the feature families derived from innovation/velocity moments.
    """

    x: tuple[float, float, float]
    p: tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]
    innovation_count: int
    innovation_sum: float
    innovation_sum_sq: float
    velocity_count: int
    velocity_sum: float
    velocity_sum_sq: float
    version: int = KALMAN_STATE_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": int(self.version),
            "x": [float(v) for v in self.x],
            "p": [[float(v) for v in row] for row in self.p],
            "innovation_count": int(self.innovation_count),
            "innovation_sum": float(self.innovation_sum),
            "innovation_sum_sq": float(self.innovation_sum_sq),
            "velocity_count": int(self.velocity_count),
            "velocity_sum": float(self.velocity_sum),
            "velocity_sum_sq": float(self.velocity_sum_sq),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "KalmanStreamingState":
        x = payload.get("x")
        p = payload.get("p")
        if x is None or p is None:
            raise ValueError("Kalman streaming state requires 'x' and 'p'")
        return cls(
            x=tuple(float(v) for v in x),
            p=tuple(tuple(float(v) for v in row) for row in p),
            innovation_count=int(payload.get("innovation_count", 0)),
            innovation_sum=float(payload.get("innovation_sum", 0.0)),
            innovation_sum_sq=float(payload.get("innovation_sum_sq", 0.0)),
            velocity_count=int(payload.get("velocity_count", 0)),
            velocity_sum=float(payload.get("velocity_sum", 0.0)),
            velocity_sum_sq=float(payload.get("velocity_sum_sq", 0.0)),
            version=int(payload.get("version", KALMAN_STATE_VERSION)),
        )

    def copy(self) -> "KalmanStreamingState":
        return KalmanStreamingState.from_dict(self.to_dict())

    def x_array(self) -> np.ndarray:
        return np.asarray(self.x, dtype=np.float64)

    def p_array(self) -> np.ndarray:
        return np.asarray(self.p, dtype=np.float64)


class KalmanHelper(BaseHelper):
    """Kalman Filter for state estimation and filtering.

    Uses a 3D state space model:
    - State 0: Position (level)
    - State 1: Velocity (trend/momentum)
    - State 2: Acceleration (change in trend)

    Provides filtered estimates and prediction errors as features.
    """

    def __init__(
        self,
        config: HelperConfig,
        process_noise: float = 1e-5,
        measurement_noise: float = 1e-3,
        dt: float | None = None,
    ):
        super().__init__(config)
        self.process_noise = process_noise
        self.measurement_noise = measurement_noise

        if dt is None:
            from .adaptive_params import get_kalman_dt

            self.dt = get_kalman_dt(config.target, config.horizon)
        else:
            self.dt = dt

        self._fitted_stream_state: KalmanStreamingState | None = None
        self._last_transform_state: KalmanStreamingState | None = None

    @property
    def supports_incremental(self) -> bool:
        """Kalman filter is naturally incremental - O(1) per update."""
        return True

    @property
    def helper_name(self) -> str:
        return "kalman"

    def _system_matrices(self) -> tuple[np.ndarray, np.ndarray, float]:
        dt = self.dt
        f = np.array(
            [
                [1.0, dt, 0.5 * dt**2],
                [0.0, 1.0, dt],
                [0.0, 0.0, 1.0],
            ],
            dtype=np.float64,
        )

        q = self.process_noise
        q_matrix = np.array(
            [
                [q * dt**5 / 20.0, q * dt**4 / 8.0, q * dt**3 / 6.0],
                [q * dt**4 / 8.0, q * dt**3 / 3.0, q * dt**2 / 2.0],
                [q * dt**3 / 6.0, q * dt**2 / 2.0, q * dt],
            ],
            dtype=np.float64,
        )
        return f, q_matrix, float(self.measurement_noise)

    def _initial_stream_state(self, first_observation: float) -> KalmanStreamingState:
        return KalmanStreamingState(
            x=(float(first_observation), 0.0, 0.0),
            p=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
            innovation_count=0,
            innovation_sum=0.0,
            innovation_sum_sq=0.0,
            velocity_count=0,
            velocity_sum=0.0,
            velocity_sum_sq=0.0,
        )

    def _coerce_state(
        self,
        state: KalmanStreamingState | dict[str, Any] | None,
    ) -> KalmanStreamingState | None:
        if state is None:
            return None
        if isinstance(state, KalmanStreamingState):
            return state.copy()
        return KalmanStreamingState.from_dict(state)

    def _feature_names(self) -> list[str]:
        prefix = f"H_{self.config.target}_{self.config.horizon}_{self.helper_name}_"
        return [
            f"{prefix}filtered_dev",
            f"{prefix}velocity",
            f"{prefix}acceleration",
            f"{prefix}pred_error",
            f"{prefix}innovation",
            f"{prefix}zscore",
            f"{prefix}regime",
        ]

    @staticmethod
    def _update_running_zscore(
        count: int,
        total: float,
        total_sq: float,
        value: float,
    ) -> tuple[int, float, float, float]:
        next_count = count + 1
        next_total = total + value
        next_total_sq = total_sq + value * value
        mean = next_total / next_count
        var = max(next_total_sq / next_count - mean * mean, 1e-10)
        zscore = (value - mean) / np.sqrt(var)
        return next_count, next_total, next_total_sq, float(zscore)

    def _transform_python_with_state(
        self,
        X: np.ndarray,
        initial_state: KalmanStreamingState | None,
    ) -> tuple[np.ndarray, KalmanStreamingState | None]:
        n_samples = int(X.shape[0])
        if n_samples == 0:
            return np.zeros((0, len(self._feature_names())), dtype=np.float64), initial_state

        signal = X[:, 0].astype(np.float64, copy=False)
        if initial_state is None:
            state = self._initial_stream_state(float(signal[0]))
        else:
            state = initial_state.copy()

        f, q_matrix, r = self._system_matrices()
        x = state.x_array()
        p = state.p_array()
        innovation_count = state.innovation_count
        innovation_sum = state.innovation_sum
        innovation_sum_sq = state.innovation_sum_sq
        velocity_count = state.velocity_count
        velocity_sum = state.velocity_sum
        velocity_sum_sq = state.velocity_sum_sq

        features = np.zeros((n_samples, len(self._feature_names())), dtype=np.float64)

        for i, z in enumerate(signal):
            x_pred = f @ x
            p_pred = f @ p @ f.T + q_matrix

            innovation = float(z - x_pred[0])
            s = float(p_pred[0, 0] + r)
            k = p_pred[:, 0] / s

            x = x_pred + k * innovation
            p = p_pred - np.outer(k, p_pred[0, :])

            pred_error = float(z - x[0])
            innovation_count, innovation_sum, innovation_sum_sq, innovation_zscore = (
                self._update_running_zscore(
                    innovation_count,
                    innovation_sum,
                    innovation_sum_sq,
                    innovation,
                )
            )
            velocity = float(x[1])
            velocity_count, velocity_sum, velocity_sum_sq, velocity_zscore = (
                self._update_running_zscore(
                    velocity_count,
                    velocity_sum,
                    velocity_sum_sq,
                    velocity,
                )
            )

            regime = 2.0 if velocity_zscore > 1.0 else 0.0 if velocity_zscore < -1.0 else 1.0

            features[i, 0] = float(x[0] - z)
            features[i, 1] = velocity
            features[i, 2] = float(x[2])
            features[i, 3] = pred_error
            features[i, 4] = innovation
            features[i, 5] = innovation_zscore
            features[i, 6] = regime

        final_state = KalmanStreamingState(
            x=tuple(float(v) for v in x),
            p=tuple(tuple(float(v) for v in row) for row in p),
            innovation_count=innovation_count,
            innovation_sum=float(innovation_sum),
            innovation_sum_sq=float(innovation_sum_sq),
            velocity_count=velocity_count,
            velocity_sum=float(velocity_sum),
            velocity_sum_sq=float(velocity_sum_sq),
        )
        return features, final_state

    def _transform_rust_with_state(
        self,
        X: np.ndarray,
        initial_state: KalmanStreamingState | None,
    ) -> tuple[np.ndarray, KalmanStreamingState | None]:
        signal = np.ascontiguousarray(X[:, 0], dtype=np.float64)
        if initial_state is None:
            features, x_out, p_out, inn_count, inn_sum, inn_sum_sq, vel_count, vel_sum, vel_sum_sq = (
                _rust.py_kalman_transform_with_state(
                    signal,
                    self.process_noise,
                    self.measurement_noise,
                    self.dt,
                )
            )
        else:
            features, x_out, p_out, inn_count, inn_sum, inn_sum_sq, vel_count, vel_sum, vel_sum_sq = (
                _rust.py_kalman_transform_with_state(
                    signal,
                    self.process_noise,
                    self.measurement_noise,
                    self.dt,
                    np.ascontiguousarray(initial_state.x_array(), dtype=np.float64),
                    np.ascontiguousarray(initial_state.p_array(), dtype=np.float64),
                    initial_state.innovation_count,
                    initial_state.innovation_sum,
                    initial_state.innovation_sum_sq,
                    initial_state.velocity_count,
                    initial_state.velocity_sum,
                    initial_state.velocity_sum_sq,
                )
            )

        final_state = KalmanStreamingState(
            x=tuple(float(v) for v in np.asarray(x_out, dtype=np.float64).reshape(3)),
            p=tuple(
                tuple(float(v) for v in row)
                for row in np.asarray(p_out, dtype=np.float64).reshape(3, 3)
            ),
            innovation_count=int(inn_count),
            innovation_sum=float(inn_sum),
            innovation_sum_sq=float(inn_sum_sq),
            velocity_count=int(vel_count),
            velocity_sum=float(vel_sum),
            velocity_sum_sq=float(vel_sum_sq),
        )
        return np.asarray(features, dtype=np.float64), final_state

    def _transform_with_state(
        self,
        X: np.ndarray,
        initial_state: KalmanStreamingState | None,
    ) -> tuple[np.ndarray, KalmanStreamingState | None]:
        if HAS_RUST:
            return self._transform_rust_with_state(X, initial_state)
        return self._transform_python_with_state(X, initial_state)

    def _fit_impl(self, X: np.ndarray, y: np.ndarray | None = None) -> None:
        _, final_state = self._transform_python_with_state(X, initial_state=None)
        self._fitted_stream_state = final_state
        self._last_transform_state = None

    def _partial_fit_impl(
        self,
        X: np.ndarray,
        y: np.ndarray | None,
        n_samples_seen: int,
    ) -> None:
        if self._fitted_stream_state is None:
            self._fit_impl(X, y)
            return

        new_signal = X[n_samples_seen:]
        if len(new_signal) == 0:
            return

        _, final_state = self._transform_with_state(new_signal, self._fitted_stream_state)
        self._fitted_stream_state = final_state
        self._last_transform_state = None

    def _transform_impl(self, X: np.ndarray) -> np.ndarray:
        features, final_state = self._transform_with_state(X, self._fitted_stream_state)
        self._last_transform_state = final_state
        return features

    def transform_with_stream_state(
        self,
        X: pd.DataFrame | np.ndarray,
        initial_state: KalmanStreamingState | dict[str, Any] | None = None,
    ) -> tuple[HelperOutput, KalmanStreamingState | None]:
        if not self.is_fitted and initial_state is None:
            raise RuntimeError(f"{self.helper_name} not fitted. Call fit() first.")

        X_np = X.values if isinstance(X, pd.DataFrame) else X
        if self.is_fitted and X_np.shape[1] != self._n_features_in:
            raise ValueError(
                f"X has {X_np.shape[1]} features, but {self.helper_name} "
                f"was fitted with {self._n_features_in} features"
            )

        resolved_state = self._coerce_state(initial_state)
        if resolved_state is None:
            resolved_state = self._coerce_state(self._fitted_stream_state)

        features_np, final_state = self._transform_with_state(X_np, resolved_state)
        feature_names = self._feature_names()
        features_df = pd.DataFrame(features_np, columns=feature_names)
        output = HelperOutput(
            features=features_df,
            feature_names=feature_names,
            helper_name=self.helper_name,
            metadata={
                "config": self.config,
                "fit_params": self._fit_params,
                "initial_stream_state": None if resolved_state is None else resolved_state.to_dict(),
                "final_stream_state": None if final_state is None else final_state.to_dict(),
                "state_contract": "streaming_handoff_v1",
            },
        )
        self._last_transform_state = final_state
        return output, final_state

    def transform(
        self,
        X: pd.DataFrame | np.ndarray,
    ) -> HelperOutput:
        output, _ = self.transform_with_stream_state(X)
        return output

    def _get_feature_names(self) -> list[str]:
        return self._feature_names()

    def optimize(
        self, X_cal: np.ndarray | pd.DataFrame, y_cal: np.ndarray | None = None
    ) -> dict[str, Any]:
        return self.validate(X_cal, y_cal)

    def validate(
        self, X_val: np.ndarray | pd.DataFrame, y_val: np.ndarray | None = None
    ) -> dict[str, Any]:
        if isinstance(X_val, pd.DataFrame):
            X_val = X_val.values

        features, _ = self._transform_with_state(X_val, self._fitted_stream_state)
        innovations = features[:, 4]
        pred_errors = features[:, 3]
        return {
            "mean_innovation": float(np.mean(innovations)),
            "std_innovation": float(np.std(innovations)),
            "mean_pred_error": float(np.mean(np.abs(pred_errors))),
            "max_pred_error": float(np.max(np.abs(pred_errors))),
        }

    def get_state(self) -> dict[str, Any] | None:
        if self._fitted_stream_state is None:
            return None
        return self._fitted_stream_state.to_dict()

    def get_last_transform_state(self) -> dict[str, Any] | None:
        if self._last_transform_state is None:
            return None
        return self._last_transform_state.to_dict()


def create_kalman_helper(
    target: str,
    horizon: int,
    process_noise: float = 1e-5,
    measurement_noise: float = 1e-3,
    random_state: int = 42,
) -> KalmanHelper:
    config = HelperConfig(target=target, horizon=horizon, random_state=random_state)
    return KalmanHelper(
        config, process_noise=process_noise, measurement_noise=measurement_noise
    )


if __name__ == "__main__":
    from scripts.target_models.registry import load_target_data

    X, y, spec = load_target_data("volatility", 6, verbose=False)
    print(f"Data shape: {X.shape}")

    kalman = create_kalman_helper("volatility", 6)
    kalman.fit(X.iloc[:800])
    out, final_state = kalman.transform_with_stream_state(X.iloc[800:1300])
    print(f"\nKalman output: {out}")
    print(f"Features: {out.feature_names}")
    print(f"State version: {final_state.version if final_state is not None else 'none'}")

    metrics = kalman.validate(X.iloc[800:1300])
    print(f"Validation: {metrics}")
