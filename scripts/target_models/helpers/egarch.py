"""EGARCH (Exponential GARCH) asymmetric volatility helper.

This helper is implemented as a true streaming-state feature generator.

Source contract:
- Nelson (1991): https://econpapers.repec.org/RePEc:ecm:emetrp:v:59:y:1991:i:2:p:347-70
- helper validity audit:
  `notebooks/notes/htf_helper_source_backed_validity_audit_2026-04-12.md`
- streaming redesign rationale:
  `notebooks/notes/htf_helper_finalization_plan_2026-04-12.md`

Runtime contract:
- `fit()` estimates EGARCH parameters on the train prefix
- `transform()` starts from the train-end EGARCH streaming state
- each row emits the one-step-ahead volatility state after assimilating the
  current row's return
- no chunk-wide demeaning, no chunk-wide variance initialization, and no future
  rows are used during feature generation
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .base import BaseHelper, HelperConfig, HelperOutput

try:
    import riskyield_rust

    HAS_RUST = True
except ImportError:
    HAS_RUST = False


EXPECTED_ABS_NORMAL = float(np.sqrt(2.0 / np.pi))
EGARCH_STATE_VERSION = 1


@dataclass
class EGARCHConfig(HelperConfig):
    """Configuration specific to EGARCH helper."""

    rolling_window: int = 126
    omega_init: float = 0.0
    alpha_init: float = 0.1
    gamma_init: float = -0.1
    beta_init: float = 0.85
    low_vol_percentile: float = 25.0
    high_vol_percentile: float = 75.0
    recent_shock_window: int = 5
    recent_shock_z_threshold: float = 1.0
    returns_col_idx: int = 0


@dataclass(frozen=True)
class EGARCHStreamingState:
    """Serializable EGARCH streaming state."""

    log_var: float
    vol_count: int
    vol_sum: float
    vol_sum_sq: float
    recent_shock_flags: tuple[int, ...]
    version: int = EGARCH_STATE_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": int(self.version),
            "log_var": float(self.log_var),
            "vol_count": int(self.vol_count),
            "vol_sum": float(self.vol_sum),
            "vol_sum_sq": float(self.vol_sum_sq),
            "recent_shock_flags": [int(v) for v in self.recent_shock_flags],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EGARCHStreamingState":
        return cls(
            log_var=float(payload.get("log_var", 0.0)),
            vol_count=int(payload.get("vol_count", 0)),
            vol_sum=float(payload.get("vol_sum", 0.0)),
            vol_sum_sq=float(payload.get("vol_sum_sq", 0.0)),
            recent_shock_flags=tuple(int(v) for v in payload.get("recent_shock_flags", [])),
            version=int(payload.get("version", EGARCH_STATE_VERSION)),
        )

    def copy(self) -> "EGARCHStreamingState":
        return EGARCHStreamingState.from_dict(self.to_dict())


class EGARCHHelper(BaseHelper):
    """EGARCH asymmetric volatility helper."""

    def __init__(self, config: EGARCHConfig | None = None):
        super().__init__(config or EGARCHConfig())
        self.config: EGARCHConfig

        self._omega: float = self.config.omega_init
        self._alpha: float = self.config.alpha_init
        self._gamma: float = self.config.gamma_init
        self._beta: float = self.config.beta_init
        self._mean_return: float = 0.0
        self._unconditional_log_var: float = np.log(1e-4)
        self._low_vol_threshold: float = 0.01
        self._high_vol_threshold: float = 0.03
        self._fitted_stream_state: EGARCHStreamingState | None = None
        self._last_transform_state: EGARCHStreamingState | None = None

    @property
    def supports_incremental(self) -> bool:
        return True

    @property
    def helper_name(self) -> str:
        return "egarch"

    def _feature_names(self) -> list[str]:
        return [
            self._make_feature_name("egarch_vol"),
            self._make_feature_name("egarch_log_vol"),
            self._make_feature_name("egarch_asymmetry"),
            self._make_feature_name("egarch_persistence"),
            self._make_feature_name("egarch_news_impact"),
            self._make_feature_name("egarch_vol_zscore"),
            self._make_feature_name("egarch_vol_regime"),
            self._make_feature_name("egarch_leverage_active"),
        ]

    def _coerce_state(
        self,
        state: EGARCHStreamingState | dict[str, Any] | None,
    ) -> EGARCHStreamingState | None:
        if state is None:
            return None
        if isinstance(state, EGARCHStreamingState):
            return state.copy()
        return EGARCHStreamingState.from_dict(state)

    def _cold_start_stream_state(self) -> EGARCHStreamingState:
        return EGARCHStreamingState(
            log_var=float(self._unconditional_log_var),
            vol_count=0,
            vol_sum=0.0,
            vol_sum_sq=0.0,
            recent_shock_flags=tuple(0 for _ in range(self.config.recent_shock_window)),
        )

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
        returns: np.ndarray,
        initial_state: EGARCHStreamingState | None,
    ) -> tuple[np.ndarray, EGARCHStreamingState | None]:
        n_samples = int(len(returns))
        if n_samples == 0:
            return np.zeros((0, len(self._feature_names())), dtype=np.float64), initial_state

        state = self._cold_start_stream_state() if initial_state is None else initial_state.copy()
        shock_window = self.config.recent_shock_window
        shock_flags = list(state.recent_shock_flags)
        if len(shock_flags) != shock_window:
            shock_flags = ([0] * shock_window + shock_flags)[-shock_window:]

        features = np.zeros((n_samples, len(self._feature_names())), dtype=np.float64)

        log_var = float(state.log_var)
        vol_count = int(state.vol_count)
        vol_sum = float(state.vol_sum)
        vol_sum_sq = float(state.vol_sum_sq)

        for i, ret in enumerate(returns.astype(np.float64, copy=False)):
            if np.isfinite(ret):
                sigma_pre = float(np.exp(0.5 * log_var))
                centered = float(ret - self._mean_return)
                eps = centered / max(sigma_pre, 1e-10)
                news_impact = float(
                    self._alpha * (abs(eps) - EXPECTED_ABS_NORMAL) + self._gamma * eps
                )
                shock_flag = int(eps < -self.config.recent_shock_z_threshold)
            else:
                news_impact = 0.0
                shock_flag = 0

            log_var = float(
                np.clip(
                    self._omega + news_impact + self._beta * log_var,
                    -20.0,
                    10.0,
                )
            )
            vol = float(np.exp(0.5 * log_var))
            vol_count, vol_sum, vol_sum_sq, vol_zscore = self._update_running_zscore(
                vol_count, vol_sum, vol_sum_sq, vol
            )
            if vol < self._low_vol_threshold:
                vol_regime = 0.0
            elif vol > self._high_vol_threshold:
                vol_regime = 2.0
            else:
                vol_regime = 1.0

            if shock_window > 0:
                shock_flags = shock_flags[1:] + [shock_flag]
                leverage_active = 1.0 if any(shock_flags) else 0.0
            else:
                leverage_active = float(shock_flag)

            features[i, 0] = vol
            features[i, 1] = log_var
            features[i, 2] = self._gamma
            features[i, 3] = self._beta
            features[i, 4] = news_impact
            features[i, 5] = vol_zscore
            features[i, 6] = vol_regime
            features[i, 7] = leverage_active

        final_state = EGARCHStreamingState(
            log_var=log_var,
            vol_count=vol_count,
            vol_sum=vol_sum,
            vol_sum_sq=vol_sum_sq,
            recent_shock_flags=tuple(int(v) for v in shock_flags),
        )
        return features, final_state

    def _transform_rust_with_state(
        self,
        returns: np.ndarray,
        initial_state: EGARCHStreamingState | None,
    ) -> tuple[np.ndarray, EGARCHStreamingState | None]:
        returns_c = np.ascontiguousarray(returns, dtype=np.float64)
        if initial_state is None:
            (
                features,
                log_var_out,
                vol_count,
                vol_sum,
                vol_sum_sq,
                recent_flags_out,
            ) = riskyield_rust.py_egarch_transform_with_state(
                returns_c,
                omega=self._omega,
                alpha=self._alpha,
                gamma=self._gamma,
                beta=self._beta,
                mean_return=self._mean_return,
                low_vol_threshold=self._low_vol_threshold,
                high_vol_threshold=self._high_vol_threshold,
                recent_shock_window=self.config.recent_shock_window,
                recent_shock_z_threshold=self.config.recent_shock_z_threshold,
            )
        else:
            (
                features,
                log_var_out,
                vol_count,
                vol_sum,
                vol_sum_sq,
                recent_flags_out,
            ) = riskyield_rust.py_egarch_transform_with_state(
                returns_c,
                omega=self._omega,
                alpha=self._alpha,
                gamma=self._gamma,
                beta=self._beta,
                mean_return=self._mean_return,
                low_vol_threshold=self._low_vol_threshold,
                high_vol_threshold=self._high_vol_threshold,
                recent_shock_window=self.config.recent_shock_window,
                recent_shock_z_threshold=self.config.recent_shock_z_threshold,
                state_log_var=initial_state.log_var,
                vol_count=initial_state.vol_count,
                vol_sum=initial_state.vol_sum,
                vol_sum_sq=initial_state.vol_sum_sq,
                recent_shock_flags=np.ascontiguousarray(
                    np.asarray(initial_state.recent_shock_flags, dtype=np.float64)
                ),
            )

        final_state = EGARCHStreamingState(
            log_var=float(log_var_out),
            vol_count=int(vol_count),
            vol_sum=float(vol_sum),
            vol_sum_sq=float(vol_sum_sq),
            recent_shock_flags=tuple(
                int(v) for v in np.asarray(recent_flags_out, dtype=np.float64).astype(int).tolist()
            ),
        )
        return np.asarray(features, dtype=np.float64), final_state

    def _transform_with_state(
        self,
        returns: np.ndarray,
        initial_state: EGARCHStreamingState | None,
    ) -> tuple[np.ndarray, EGARCHStreamingState | None]:
        if HAS_RUST:
            return self._transform_rust_with_state(returns, initial_state)
        return self._transform_python_with_state(returns, initial_state)

    def _estimate_egarch_params(self, returns: np.ndarray) -> tuple[float, float, float, float]:
        n = len(returns)
        if n < 30:
            return self._omega, self._alpha, self._gamma, self._beta

        if HAS_RUST:
            returns_c = np.ascontiguousarray(returns, dtype=np.float64)
            return riskyield_rust.py_egarch_estimate_params(returns_c)

        return self._estimate_egarch_params_python(returns)

    def _estimate_egarch_params_python(
        self,
        returns: np.ndarray,
    ) -> tuple[float, float, float, float]:
        mean_ret = np.mean(returns)
        resid = returns - mean_ret
        var_sample = np.var(resid) + 1e-10

        best_params = (self._omega, self._alpha, self._gamma, self._beta)
        best_ll = -np.inf

        for gamma in [-0.2, -0.1, -0.05, 0.0, 0.05]:
            for beta in [0.7, 0.8, 0.85, 0.9, 0.95]:
                for alpha in [0.05, 0.1, 0.15, 0.2]:
                    omega = (1 - beta) * np.log(var_sample)
                    ll = self._egarch_log_likelihood(resid, omega, alpha, gamma, beta)
                    if ll > best_ll:
                        best_ll = ll
                        best_params = (omega, alpha, gamma, beta)

        return best_params

    def _egarch_log_likelihood(
        self,
        resid: np.ndarray,
        omega: float,
        alpha: float,
        gamma: float,
        beta: float,
    ) -> float:
        n = len(resid)
        log_var = np.log(np.var(resid) + 1e-10)
        ll = 0.0

        for t in range(1, n):
            std_resid = resid[t - 1] / np.exp(0.5 * log_var) if log_var > -20 else 0.0
            log_var = omega + alpha * (abs(std_resid) - EXPECTED_ABS_NORMAL) + gamma * std_resid + beta * log_var
            log_var = float(np.clip(log_var, -20.0, 10.0))
            var_t = np.exp(log_var)
            ll += -0.5 * (np.log(2 * np.pi) + log_var + resid[t] ** 2 / var_t)

        return ll

    def _make_feature_name(self, base_name: str) -> str:
        if self.config.prefix:
            return f"{self.config.prefix}_{base_name}"
        return f"H_{base_name}"

    def _fit_impl(self, X: np.ndarray, y: np.ndarray | None = None) -> None:
        n_samples, n_features = X.shape
        ret_idx = min(self.config.returns_col_idx, n_features - 1)
        returns = X[:, ret_idx].astype(np.float64)
        returns_clean = returns[np.isfinite(returns)]

        if len(returns_clean) == 0:
            return

        self._mean_return = float(np.mean(returns_clean))
        centered = returns_clean - self._mean_return
        var_sample = float(np.var(centered) + 1e-10)

        if len(returns_clean) >= 30:
            omega, alpha, gamma, beta = self._estimate_egarch_params(returns_clean)
            self._omega = float(omega)
            self._alpha = float(alpha)
            self._gamma = float(gamma)
            self._beta = float(beta)

        if abs(self._beta) < 0.999:
            self._unconditional_log_var = float(self._omega / (1.0 - self._beta))
        else:
            self._unconditional_log_var = float(np.log(var_sample))

        train_features, final_state = self._transform_with_state(returns, None)
        self._fitted_stream_state = final_state
        self._last_transform_state = None

        valid_vol = train_features[:, 0]
        valid_vol = valid_vol[np.isfinite(valid_vol) & (valid_vol > 0)]
        if len(valid_vol) > 10:
            self._low_vol_threshold = float(np.percentile(valid_vol, self.config.low_vol_percentile))
            self._high_vol_threshold = float(np.percentile(valid_vol, self.config.high_vol_percentile))

        self._fit_params = {
            "n_samples": n_samples,
            "omega": self._omega,
            "alpha": self._alpha,
            "gamma": self._gamma,
            "beta": self._beta,
            "mean_return": self._mean_return,
            "unconditional_log_var": self._unconditional_log_var,
            "low_vol_threshold": self._low_vol_threshold,
            "high_vol_threshold": self._high_vol_threshold,
            "recent_shock_z_threshold": self.config.recent_shock_z_threshold,
            "state_contract": "streaming_handoff_v1",
        }

    def _partial_fit_impl(
        self,
        X: np.ndarray,
        y: np.ndarray | None,
        n_samples_seen: int,
    ) -> None:
        if self._fitted_stream_state is None:
            self._fit_impl(X, y)
            return

        ret_idx = min(self.config.returns_col_idx, X.shape[1] - 1)
        new_returns = X[n_samples_seen:, ret_idx].astype(np.float64)
        if len(new_returns) == 0:
            return

        _, final_state = self._transform_with_state(new_returns, self._fitted_stream_state)
        self._fitted_stream_state = final_state
        self._last_transform_state = None

    def _transform_impl(self, X: np.ndarray) -> np.ndarray:
        ret_idx = min(self.config.returns_col_idx, X.shape[1] - 1)
        returns = X[:, ret_idx].astype(np.float64)
        features, final_state = self._transform_with_state(returns, self._fitted_stream_state)
        self._last_transform_state = final_state
        return features

    def transform_with_stream_state(
        self,
        X: np.ndarray | Any,
        initial_state: EGARCHStreamingState | dict[str, Any] | None = None,
    ) -> tuple[HelperOutput, EGARCHStreamingState | None]:
        if not self.is_fitted and initial_state is None:
            raise RuntimeError(f"{self.helper_name} not fitted. Call fit() first.")

        X_np = X.values if hasattr(X, "values") else X
        if self.is_fitted and X_np.shape[1] != self._n_features_in:
            raise ValueError(
                f"X has {X_np.shape[1]} features, but {self.helper_name} "
                f"was fitted with {self._n_features_in} features"
            )

        ret_idx = min(self.config.returns_col_idx, X_np.shape[1] - 1)
        returns = X_np[:, ret_idx].astype(np.float64)

        resolved_state = self._coerce_state(initial_state)
        if resolved_state is None:
            resolved_state = self._coerce_state(self._fitted_stream_state)

        features_np, final_state = self._transform_with_state(returns, resolved_state)
        feature_names = self._feature_names()
        features_df = np.asarray(features_np, dtype=np.float64)
        output = HelperOutput(
            features=pd.DataFrame(features_df, columns=feature_names),
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

    def transform(self, X: np.ndarray | Any) -> HelperOutput:
        output, _ = self.transform_with_stream_state(X)
        return output

    def _get_feature_names(self) -> list[str]:
        return self._feature_names()

    def validate(
        self,
        X_val: np.ndarray,
        y_val: np.ndarray | None = None,
    ) -> dict[str, float]:
        X_val = X_val.values if hasattr(X_val, "values") else X_val
        ret_idx = min(self.config.returns_col_idx, X_val.shape[1] - 1)
        returns = X_val[:, ret_idx].astype(np.float64)
        features, _ = self._transform_with_state(returns, self._fitted_stream_state)
        vol = features[:, 0]
        asymmetry = features[:, 2]
        persistence = features[:, 3]
        regime = features[:, 6]
        valid_regime = regime[np.isfinite(regime)]
        frac_high_vol = (valid_regime == 2.0).mean() if len(valid_regime) > 0 else 0.0
        return {
            "mean_vol": float(np.nanmean(vol)),
            "mean_asymmetry": float(np.nanmean(asymmetry)),
            "mean_persistence": float(np.nanmean(persistence)),
            "frac_high_vol": float(frac_high_vol),
            "leverage_strength": abs(float(np.nanmean(asymmetry))),
        }

    def get_state(self) -> dict[str, Any] | None:
        if self._fitted_stream_state is None:
            return None
        return self._fitted_stream_state.to_dict()

    def get_last_transform_state(self) -> dict[str, Any] | None:
        if self._last_transform_state is None:
            return None
        return self._last_transform_state.to_dict()


def create_egarch_helper(
    target: str,
    horizon: int,
    random_state: int = 42,
) -> EGARCHHelper:
    config = EGARCHConfig(
        target=target,
        horizon=horizon,
        random_state=random_state,
        prefix=f"H_{target}_{horizon}",
        rolling_window=126,
        omega_init=0.0,
        alpha_init=0.1,
        gamma_init=-0.1,
        beta_init=0.85,
        low_vol_percentile=25.0,
        high_vol_percentile=75.0,
        recent_shock_window=5,
        recent_shock_z_threshold=1.0,
    )
    return EGARCHHelper(config)
