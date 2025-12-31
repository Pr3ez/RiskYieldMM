"""
GARCH(1,1) Volatility Model Helper.

Conditional volatility estimation using GARCH(1,1) model:
- Forecasts volatility for multiple steps ahead
- Provides volatility regime detection
- Captures volatility clustering and persistence

Features Generated (~8 per target-horizon):
- cond_vol: Conditional volatility estimate
- vol_forecast_{horizon}: Multi-step forecast
- vol_zscore: Volatility relative to history
- vol_shock: Standardized residuals
- vol_persistence: GARCH persistence (α + β)
- vol_regime: HIGH/MED/LOW based on percentile
- vol_change: Change in conditional vol

Now uses Rust backend for ~360x speedup when available.
"""

import warnings
from dataclasses import dataclass
from typing import Any

import numpy as np

from .base import BaseHelper, HelperConfig

# Try to import Rust backend
try:
    import riskyield_rust as _rust

    HAS_RUST = True
except ImportError:
    HAS_RUST = False


# =============================================================================
# CONFIGURATION
# =============================================================================
@dataclass
class GARCHConfig(HelperConfig):
    """Configuration specific to GARCH helper."""

    # GARCH model params
    p: int = 1  # GARCH lag order
    q: int = 1  # ARCH lag order
    mean: str = "Zero"  # Mean model: Zero, Constant, AR

    # Forecasting
    forecast_horizon: int = 1  # Steps ahead to forecast

    # Volatility regime thresholds (percentiles)
    regime_low_pct: float = 33.0
    regime_high_pct: float = 67.0

    # Return column index (for extracting returns from features)
    return_col_idx: int = 0

    # Rescaling (arch library likes larger values)
    rescale: float = 100.0


# =============================================================================
# GARCH HELPER
# =============================================================================
class GARCHHelper(BaseHelper):
    """
    GARCH(1,1) conditional volatility helper.

    Uses the arch package for robust GARCH estimation.
    Falls back to simple volatility estimation if fitting fails.

    Features generated:
    - H_{prefix}_garch_cond_vol: Conditional volatility
    - H_{prefix}_garch_vol_forecast: {horizon}-step forecast
    - H_{prefix}_garch_vol_zscore: Vol relative to 63-day mean
    - H_{prefix}_garch_vol_shock: Standardized residuals (ε/σ)
    - H_{prefix}_garch_persistence: α + β (volatility persistence)
    - H_{prefix}_garch_vol_regime: 0=LOW, 1=MED, 2=HIGH
    - H_{prefix}_garch_vol_change: Change in conditional vol
    - H_{prefix}_garch_vol_ratio: Current vol / long-run vol
    """

    def __init__(self, config: GARCHConfig | None = None):
        super().__init__(config or GARCHConfig())
        self.config: GARCHConfig

        # Fitted model components
        self._omega: float = 0.0  # Constant term
        self._alpha: float = 0.1  # ARCH term
        self._beta: float = 0.8  # GARCH term
        self._long_run_var: float = 1.0  # Unconditional variance

        # Regime thresholds
        self._regime_low_thresh: float = 0.0
        self._regime_high_thresh: float = 0.0

        # Whether we successfully fitted arch model
        self._use_arch: bool = False

    @property
    def supports_incremental(self) -> bool:
        """GARCH requires full refit - no incremental support.

        GARCH model estimation via MLE requires the full dataset
        to compute the likelihood function properly. Each new
        observation changes the optimal parameters.
        """
        return False

    @property
    def helper_name(self) -> str:
        return "garch"

    def _fit_impl(self, X: np.ndarray, y: np.ndarray | None = None) -> None:
        """
        Fit GARCH(1,1) model to returns.

        Args:
            X: Feature matrix
            y: Ignored
        """
        n_features = X.shape[1]
        ret_idx = min(self.config.return_col_idx, n_features - 1)
        returns = (
            X[:, ret_idx] * self.config.rescale
        )  # Scale up for numerical stability

        # Remove NaN
        returns = returns[~np.isnan(returns)]

        if len(returns) < 100:
            self._fit_simple(returns)
            return

        try:
            # Try arch package
            from arch import arch_model

            model = arch_model(
                returns,
                mean=self.config.mean,
                vol="GARCH",
                p=self.config.p,
                q=self.config.q,
                rescale=False,  # Already rescaled
            )

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                result = model.fit(disp="off", show_warning=False)

            # Extract parameters
            self._omega = float(result.params.get("omega", 0.01))
            self._alpha = float(result.params.get("alpha[1]", 0.1))
            self._beta = float(result.params.get("beta[1]", 0.8))

            # Ensure valid parameters
            self._alpha = np.clip(self._alpha, 0.01, 0.5)
            self._beta = np.clip(self._beta, 0.3, 0.98)

            # Compute long-run variance
            persistence = self._alpha + self._beta
            if persistence < 1.0:
                self._long_run_var = self._omega / (1 - persistence)
            else:
                self._long_run_var = np.var(returns)

            self._use_arch = True

            if self.config.verbose:
                print(
                    f"GARCH fitted: ω={self._omega:.6f}, α={self._alpha:.4f}, β={self._beta:.4f}"
                )

        except Exception as e:
            if self.config.verbose:
                print(f"GARCH fitting failed: {e}, using simple fallback")
            self._fit_simple(returns)

        # Compute regime thresholds from conditional vol on training data
        cond_vol = self._compute_conditional_vol(returns)
        self._regime_low_thresh = float(
            np.nanpercentile(cond_vol, self.config.regime_low_pct)
        )
        self._regime_high_thresh = float(
            np.nanpercentile(cond_vol, self.config.regime_high_pct)
        )

        self._fit_params = {
            "omega": self._omega,
            "alpha": self._alpha,
            "beta": self._beta,
            "long_run_var": self._long_run_var,
            "use_arch": self._use_arch,
            "regime_thresholds": (self._regime_low_thresh, self._regime_high_thresh),
        }

    def _fit_simple(self, returns: np.ndarray) -> None:
        """Simple EWMA-based volatility fallback."""
        self._omega = float(np.var(returns)) * 0.02
        self._alpha = 0.06
        self._beta = 0.92
        self._long_run_var = float(np.var(returns))
        self._use_arch = False

    def _compute_conditional_vol(self, returns: np.ndarray) -> np.ndarray:
        """
        Compute conditional volatility using fitted GARCH parameters.

        Uses the recursion:
        σ²_t = ω + α * r²_{t-1} + β * σ²_{t-1}
        """
        n = len(returns)
        cond_var = np.zeros(n)
        cond_var[0] = self._long_run_var

        for t in range(1, n):
            cond_var[t] = (
                self._omega
                + self._alpha * returns[t - 1] ** 2
                + self._beta * cond_var[t - 1]
            )

        return np.sqrt(np.maximum(cond_var, 1e-10))

    def _transform_impl(self, X: np.ndarray) -> np.ndarray:
        """
        Generate GARCH-based features.

        Uses Rust backend when available for ~360x speedup.
        Falls back to Python implementation otherwise.

        Args:
            X: Feature matrix

        Returns:
            Feature matrix with GARCH features
        """
        if HAS_RUST:
            return self._transform_rust(X)
        return self._transform_python(X)

    def _transform_rust(self, X: np.ndarray) -> np.ndarray:
        """Transform using Rust backend (~360x faster)."""
        n_features = X.shape[1]
        ret_idx = min(self.config.return_col_idx, n_features - 1)
        returns = X[:, ret_idx] * self.config.rescale

        return _rust.py_garch_transform(
            returns.astype(np.float64),
            self._omega,
            self._alpha,
            self._beta,
            self._long_run_var,
            self.config.forecast_horizon,
            63,  # zscore_window
            self._regime_low_thresh,
            self._regime_high_thresh,
            self.config.rescale,
        )

    def _transform_python(self, X: np.ndarray) -> np.ndarray:
        """Transform using Python backend (original implementation)."""
        n_samples = X.shape[0]
        n_features = X.shape[1]
        ret_idx = min(self.config.return_col_idx, n_features - 1)
        returns = X[:, ret_idx] * self.config.rescale

        # Conditional volatility
        cond_vol = self._compute_conditional_vol(returns)

        # Multi-step forecast
        horizon = self.config.forecast_horizon
        vol_forecast = self._compute_forecast(cond_vol, horizon)

        # Vol z-score (relative to 63-bar rolling mean)
        vol_zscore = self._compute_vol_zscore(cond_vol, window=63)

        # Vol shock (standardized residuals)
        vol_shock = np.zeros(n_samples)
        vol_shock[1:] = returns[1:] / (cond_vol[:-1] + 1e-10)

        # Persistence
        persistence = np.full(n_samples, self._alpha + self._beta)

        # Vol regime
        vol_regime = np.ones(n_samples)  # Default MED
        vol_regime[cond_vol < self._regime_low_thresh] = 0  # LOW
        vol_regime[cond_vol > self._regime_high_thresh] = 2  # HIGH

        # Vol change
        vol_change = np.zeros(n_samples)
        vol_change[1:] = cond_vol[1:] - cond_vol[:-1]

        # Vol ratio (current / long-run)
        long_run_vol = np.sqrt(self._long_run_var)
        vol_ratio = cond_vol / (long_run_vol + 1e-10)

        # Descale conditional vol back to original units
        cond_vol = cond_vol / self.config.rescale
        vol_forecast = vol_forecast / self.config.rescale
        vol_change = vol_change / self.config.rescale

        features = np.column_stack(
            [
                cond_vol,
                vol_forecast,
                vol_zscore,
                vol_shock,
                persistence,
                vol_regime,
                vol_change,
                vol_ratio,
            ]
        )

        return features

    def _compute_forecast(self, cond_vol: np.ndarray, horizon: int) -> np.ndarray:
        """Compute h-step ahead volatility forecast."""
        cond_var = cond_vol**2
        persistence = self._alpha + self._beta

        # h-step forecast: σ²_{t+h|t} = ω(1 + p + ... + p^{h-1}) + p^h * σ²_t
        if abs(persistence - 1.0) > 1e-6:
            sum_factor = (1 - persistence**horizon) / (1 - persistence)
        else:
            sum_factor = float(horizon)

        forecast_var = self._omega * sum_factor + (persistence**horizon) * cond_var
        return np.sqrt(np.maximum(forecast_var, 1e-10))

    def _compute_vol_zscore(self, cond_vol: np.ndarray, window: int = 63) -> np.ndarray:
        """Compute z-score of conditional vol relative to rolling mean."""
        n = len(cond_vol)
        zscore = np.zeros(n)

        for i in range(window, n):
            window_vol = cond_vol[i - window : i]
            mean_vol = np.mean(window_vol)
            std_vol = np.std(window_vol) + 1e-10
            zscore[i] = (cond_vol[i] - mean_vol) / std_vol

        return zscore

    def _get_feature_names(self) -> list[str]:
        """Get feature names."""
        return [
            self._make_feature_name("garch_cond_vol"),
            self._make_feature_name("garch_vol_forecast"),
            self._make_feature_name("garch_vol_zscore"),
            self._make_feature_name("garch_vol_shock"),
            self._make_feature_name("garch_persistence"),
            self._make_feature_name("garch_vol_regime"),
            self._make_feature_name("garch_vol_change"),
            self._make_feature_name("garch_vol_ratio"),
        ]

    def validate(
        self,
        X_val: np.ndarray,
        y_val: np.ndarray | None = None,
    ) -> dict[str, float]:
        """Compute validation metrics."""
        features = self._transform_impl(X_val)

        # Mean conditional vol
        mean_cond_vol = np.mean(features[:, 0])

        # Regime distribution
        vol_regime = features[:, 5]
        low_pct = np.mean(vol_regime == 0)
        high_pct = np.mean(vol_regime == 2)

        return {
            "mean_cond_vol": float(mean_cond_vol),
            "low_regime_pct": float(low_pct),
            "high_regime_pct": float(high_pct),
            "persistence": float(self._alpha + self._beta),
        }

    def get_params(self) -> dict[str, Any]:
        """Get detailed parameters."""
        return {
            **super().get_params(),
            "omega": self._omega,
            "alpha": self._alpha,
            "beta": self._beta,
            "long_run_var": self._long_run_var,
            "use_arch": self._use_arch,
        }


# =============================================================================
# FACTORY
# =============================================================================
def create_garch_helper(
    target: str,
    horizon: int,
    task_type: str = "regression",
    **kwargs,
) -> GARCHHelper:
    """
    Create GARCHHelper for a specific target-horizon.

    Args:
        target: Target name
        horizon: Prediction horizon
        task_type: Task type
        **kwargs: Additional config overrides

    Returns:
        Configured GARCHHelper
    """
    # Adjust forecast horizon based on prediction horizon
    forecast_horizon = kwargs.pop("forecast_horizon", horizon)

    config = GARCHConfig(
        target=target,
        horizon=horizon,
        task_type=task_type,
        prefix=f"{target[:3]}_{horizon}",
        forecast_horizon=forecast_horizon,
        **kwargs,
    )
    return GARCHHelper(config)
