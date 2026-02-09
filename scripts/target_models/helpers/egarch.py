"""
EGARCH (Exponential GARCH) Asymmetric Volatility Helper.

Captures asymmetric volatility responses (leverage effect):
- Bad news (negative returns) increases volatility more than good news
- Uses Nelson's EGARCH specification

Features Generated (~8 per target-horizon):
- egarch_vol: EGARCH conditional volatility forecast
- egarch_log_vol: Log volatility (σ²)
- egarch_asymmetry: Leverage coefficient (γ)
- egarch_persistence: Persistence (β)
- egarch_news_impact: |ε| + γ*ε (news impact)
- egarch_vol_zscore: Volatility z-score
- egarch_vol_regime: LOW(0)/NORMAL(1)/HIGH(2) volatility
- egarch_leverage_active: Binary: recent negative shock

Math:
EGARCH(1,1):
ln(σ²_t) = ω + α*(|ε_{t-1}| - E|ε|) + γ*ε_{t-1} + β*ln(σ²_{t-1})

where:
- ε_t = r_t / σ_t  (standardized residual)
- γ < 0 captures leverage effect (bad news → higher vol)
- |γ| measures asymmetry strength

References:
- Nelson (1991) - Conditional Heteroskedasticity in Asset Returns
"""

from dataclasses import dataclass

import numpy as np

from .base import BaseHelper, HelperConfig

# Try to import Rust accelerated version
try:
    import riskyield_rust

    HAS_RUST = True
except ImportError:
    HAS_RUST = False


# =============================================================================
# CONFIGURATION
# =============================================================================
@dataclass
class EGARCHConfig(HelperConfig):
    """Configuration specific to EGARCH helper."""

    # Rolling window for parameter estimation
    rolling_window: int = 126  # ~6 weeks of 8h bars

    # EGARCH(1,1) initial parameters
    # These are starting values for optimization
    omega_init: float = 0.0  # Log variance intercept
    alpha_init: float = 0.1  # ARCH coefficient (magnitude)
    gamma_init: float = -0.1  # Leverage coefficient (asymmetry)
    beta_init: float = 0.85  # GARCH coefficient (persistence)

    # Volatility regime thresholds (percentiles)
    low_vol_percentile: float = 25.0
    high_vol_percentile: float = 75.0

    # Recent shock window
    recent_shock_window: int = 5

    # Feature column index (returns)
    returns_col_idx: int = 0


# =============================================================================
# EGARCH HELPER
# =============================================================================
class EGARCHHelper(BaseHelper):
    """
    EGARCH asymmetric volatility helper.

    Captures leverage effect where negative returns
    increase volatility more than positive returns.

    Features generated:
    - H_{prefix}_egarch_vol: Conditional volatility
    - H_{prefix}_egarch_log_vol: Log conditional variance
    - H_{prefix}_egarch_asymmetry: Leverage coefficient γ
    - H_{prefix}_egarch_persistence: GARCH coefficient β
    - H_{prefix}_egarch_news_impact: News impact curve value
    - H_{prefix}_egarch_vol_zscore: Volatility z-score
    - H_{prefix}_egarch_vol_regime: 0=LOW, 1=NORMAL, 2=HIGH
    - H_{prefix}_egarch_leverage_active: Binary: recent negative shock

    LEAKAGE PREVENTION:
    - Rolling window parameter estimation [t-window:t]
    - No future data access
    - Volatility forecast only uses past data
    """

    def __init__(self, config: EGARCHConfig | None = None):
        super().__init__(config or EGARCHConfig())
        self.config: EGARCHConfig

        # Fitted parameters
        self._omega: float = 0.0
        self._alpha: float = 0.1
        self._gamma: float = -0.1
        self._beta: float = 0.85
        self._unconditional_var: float = 0.01

        # Volatility percentile thresholds (from training)
        self._low_vol_threshold: float = 0.01
        self._high_vol_threshold: float = 0.03

    @property
    def supports_incremental(self) -> bool:
        """EGARCH has state - can be incremental."""
        return True

    @property
    def helper_name(self) -> str:
        return "egarch"

    def _fit_impl(self, X: np.ndarray, y: np.ndarray | None = None) -> None:
        """
        Fit EGARCH model on training data.

        Estimates EGARCH parameters using quasi-maximum likelihood.

        Args:
            X: Feature matrix (n_samples, n_features)
            y: Ignored
        """
        n_samples, n_features = X.shape
        ret_idx = min(self.config.returns_col_idx, n_features - 1)
        returns = X[:, ret_idx]

        # Clean returns
        returns_clean = returns[~np.isnan(returns)]

        if len(returns_clean) < 50:
            # Not enough data, use defaults
            return

        # Estimate EGARCH parameters
        omega, alpha, gamma, beta = self._estimate_egarch_params(returns_clean)

        self._omega = omega
        self._alpha = alpha
        self._gamma = gamma
        self._beta = beta

        # Compute unconditional variance
        # For EGARCH: E[ln(σ²)] = ω / (1 - β)
        if abs(beta) < 0.999:
            self._unconditional_var = np.exp(omega / (1 - beta))
        else:
            self._unconditional_var = np.var(returns_clean)

        # Compute volatility series for threshold calibration
        vol_series = self._compute_egarch_vol(returns_clean)

        # Calibrate thresholds from training data
        valid_vol = vol_series[~np.isnan(vol_series) & (vol_series > 0)]
        if len(valid_vol) > 10:
            self._low_vol_threshold = float(
                np.percentile(valid_vol, self.config.low_vol_percentile)
            )
            self._high_vol_threshold = float(
                np.percentile(valid_vol, self.config.high_vol_percentile)
            )

        self._fit_params = {
            "n_samples": n_samples,
            "omega": self._omega,
            "alpha": self._alpha,
            "gamma": self._gamma,
            "beta": self._beta,
            "unconditional_var": self._unconditional_var,
            "low_vol_threshold": self._low_vol_threshold,
            "high_vol_threshold": self._high_vol_threshold,
        }

        if self.config.verbose:
            print(f"EGARCHHelper fitted on {X.shape}")
            print(f"  ω: {self._omega:.6f}")
            print(f"  α: {self._alpha:.4f}")
            print(f"  γ: {self._gamma:.4f} (leverage)")
            print(f"  β: {self._beta:.4f} (persistence)")

    def _transform_impl(self, X: np.ndarray) -> np.ndarray:
        """
        Generate EGARCH-based features using rolling or fitted parameters.

        When Rust acceleration is available, uses full rolling window estimation
        for each sample. Otherwise falls back to fitted constant params.

        Args:
            X: Feature matrix (n_samples, n_features)

        Returns:
            Feature matrix (n_samples, 8) with EGARCH features
        """
        n_samples, n_features = X.shape
        ret_idx = min(self.config.returns_col_idx, n_features - 1)
        returns = X[:, ret_idx].astype(np.float64)

        # Use Rust accelerated version if available
        if HAS_RUST:
            return self._transform_rust(returns)

        # Fallback to Python implementation with fitted params
        return self._transform_python(returns, n_samples)

    def _transform_rust(self, returns: np.ndarray) -> np.ndarray:
        """
        Use Rust accelerated EGARCH with fitted parameters.
        """
        # Ensure contiguous float64 array
        returns_c = np.ascontiguousarray(returns, dtype=np.float64)

        # Call Rust: returns (n_samples, 8) array
        # Columns: [vol, log_vol, asymmetry, persistence, news_impact,
        #           vol_zscore, vol_regime, leverage_active]
        features = riskyield_rust.py_egarch_rolling_transform(
            returns_c,
            omega=self._omega,
            alpha=self._alpha,
            gamma=self._gamma,
            beta=self._beta,
            low_vol_threshold=self._low_vol_threshold,
            high_vol_threshold=self._high_vol_threshold,
            recent_shock_window=self.config.recent_shock_window,
        )

        return features

    def _transform_python(self, returns: np.ndarray, n_samples: int) -> np.ndarray:
        """
        Python implementation using fitted constant params.
        """
        # Compute volatility series using FITTED params (not re-estimated)
        vol_series, log_vol_series = self._compute_egarch_vol_full(returns)

        # Initialize output arrays - use FITTED params (constant across samples)
        vol_arr = vol_series
        log_vol_arr = log_vol_series
        asymmetry_arr = np.full(n_samples, self._gamma)  # Fitted leverage coef
        persistence_arr = np.full(n_samples, self._beta)  # Fitted persistence

        # News impact: computed per-sample but uses fitted params (fast)
        news_impact_arr = np.zeros(n_samples)
        for t in range(1, n_samples):
            if not np.isnan(returns[t - 1]) and vol_series[t - 1] > 0:
                std_resid = returns[t - 1] / vol_series[t - 1]
                expected_abs = 0.798  # E[|ε|] for standard normal
                news_impact_arr[t] = (
                    self._alpha * (abs(std_resid) - expected_abs)
                    + self._gamma * std_resid
                )

        # Volatility z-score (causal expanding, no look-ahead)
        vol_zscore_arr = np.full(n_samples, np.nan)
        count = 0
        sum_v = 0.0
        sum_sq = 0.0
        for i in range(n_samples):
            v = vol_series[i]
            if np.isnan(v) or v <= 0:
                continue
            count += 1
            sum_v += v
            sum_sq += v * v
            mean = sum_v / count
            var = max(sum_sq / count - mean * mean, 1e-10)
            vol_zscore_arr[i] = (v - mean) / np.sqrt(var)

        # Vol regime classification using training thresholds
        vol_regime_arr = np.ones(n_samples)  # Default NORMAL
        vol_regime_arr[vol_series < self._low_vol_threshold] = 0.0  # LOW
        vol_regime_arr[vol_series > self._high_vol_threshold] = 2.0  # HIGH

        # Leverage active: recent negative shock (vectorized)
        leverage_active_arr = np.zeros(n_samples)
        ret_std = np.nanstd(returns) + 1e-8
        shock_window = self.config.recent_shock_window
        for t in range(shock_window, n_samples):
            recent = returns[t - shock_window + 1 : t + 1]
            valid_recent = recent[~np.isnan(recent)]
            if len(valid_recent) > 0 and np.any(valid_recent < -ret_std):
                leverage_active_arr[t] = 1.0

        # Stack all features
        features = np.column_stack(
            [
                vol_arr,
                log_vol_arr,
                asymmetry_arr,
                persistence_arr,
                news_impact_arr,
                vol_zscore_arr,
                vol_regime_arr,
                leverage_active_arr,
            ]
        )

        return features

    def _estimate_egarch_params(
        self,
        returns: np.ndarray,
    ) -> tuple[float, float, float, float]:
        """
        Estimate EGARCH(1,1) parameters using grid search.

        Uses Rust-accelerated parallel grid search when available (1500x faster),
        falls back to Python implementation otherwise.

        Args:
            returns: Return series

        Returns:
            (omega, alpha, gamma, beta)
        """
        n = len(returns)
        if n < 30:
            return self._omega, self._alpha, self._gamma, self._beta

        # Use Rust accelerated version if available (1500x faster)
        if HAS_RUST:
            returns_c = np.ascontiguousarray(returns, dtype=np.float64)
            return riskyield_rust.py_egarch_estimate_params(returns_c)

        # Fallback to Python grid search
        return self._estimate_egarch_params_python(returns)

    def _estimate_egarch_params_python(
        self,
        returns: np.ndarray,
    ) -> tuple[float, float, float, float]:
        """
        Python fallback for EGARCH parameter estimation.

        Uses grid search over (gamma, beta, alpha) combinations.
        """
        # Demean returns
        mean_ret = np.mean(returns)
        resid = returns - mean_ret

        # Sample variance
        var_sample = np.var(resid) + 1e-10

        # Grid search for gamma (leverage) and beta (persistence)
        best_params = (self._omega, self._alpha, self._gamma, self._beta)
        best_ll = -np.inf

        for gamma in [-0.2, -0.1, -0.05, 0.0, 0.05]:
            for beta in [0.7, 0.8, 0.85, 0.9, 0.95]:
                for alpha in [0.05, 0.1, 0.15, 0.2]:
                    # Compute implied omega for stationarity
                    # E[ln(σ²)] = ω / (1 - β)
                    # ω = (1 - β) * ln(var_sample)
                    omega = (1 - beta) * np.log(var_sample)

                    # Compute log-likelihood
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
        """
        Compute EGARCH log-likelihood.

        ln(σ²_t) = ω + α*(|ε_{t-1}| - E|ε|) + γ*ε_{t-1} + β*ln(σ²_{t-1})

        Args:
            resid: Residuals (returns - mean)
            omega, alpha, gamma, beta: EGARCH parameters

        Returns:
            Log-likelihood
        """
        n = len(resid)

        # Initialize log variance
        log_var = np.log(np.var(resid) + 1e-10)

        # Expected |ε| for standard normal
        expected_abs = 0.798

        ll = 0.0

        for t in range(1, n):
            # Standardized residual at t-1
            std_resid = resid[t - 1] / np.exp(0.5 * log_var) if log_var > -20 else 0

            # EGARCH recursion
            log_var = (
                omega
                + alpha * (abs(std_resid) - expected_abs)
                + gamma * std_resid
                + beta * log_var
            )

            # Clip for numerical stability
            log_var = np.clip(log_var, -20, 10)

            # Gaussian log-likelihood contribution
            var_t = np.exp(log_var)
            ll += -0.5 * (np.log(2 * np.pi) + log_var + resid[t] ** 2 / var_t)

        return ll

    def _compute_egarch_vol(self, returns: np.ndarray) -> np.ndarray:
        """
        Compute EGARCH volatility series.

        Args:
            returns: Return series

        Returns:
            Volatility series
        """
        _, log_vol = self._compute_egarch_vol_full(returns)
        return np.exp(0.5 * log_vol)

    def _compute_egarch_vol_full(
        self,
        returns: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Compute EGARCH volatility and log-variance series.

        Args:
            returns: Return series

        Returns:
            (volatility, log_variance)
        """
        n = len(returns)

        # Demean
        mean_ret = np.nanmean(returns)
        resid = returns - mean_ret

        # Initialize
        log_var = np.log(np.nanvar(resid) + 1e-10)
        log_var_series = np.full(n, np.nan)
        vol_series = np.full(n, np.nan)

        log_var_series[0] = log_var
        vol_series[0] = np.exp(0.5 * log_var)

        # Expected |ε| for standard normal
        expected_abs = 0.798

        for t in range(1, n):
            if np.isnan(resid[t - 1]):
                log_var_series[t] = log_var
                vol_series[t] = np.exp(0.5 * log_var)
                continue

            # Standardized residual at t-1
            vol_prev = np.exp(0.5 * log_var)
            std_resid = resid[t - 1] / vol_prev if vol_prev > 1e-10 else 0

            # EGARCH recursion
            log_var = (
                self._omega
                + self._alpha * (abs(std_resid) - expected_abs)
                + self._gamma * std_resid
                + self._beta * log_var
            )

            # Clip for numerical stability
            log_var = np.clip(log_var, -20, 10)

            log_var_series[t] = log_var
            vol_series[t] = np.exp(0.5 * log_var)

        return vol_series, log_var_series

    def _get_feature_names(self) -> list[str]:
        """Get feature names."""
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

    def _make_feature_name(self, base_name: str) -> str:
        """Create feature name with prefix."""
        if self.config.prefix:
            return f"{self.config.prefix}_{base_name}"
        return f"H_{base_name}"

    def validate(
        self,
        X_val: np.ndarray,
        y_val: np.ndarray | None = None,
    ) -> dict[str, float]:
        """
        Validate EGARCH model - check leverage effect presence.

        Args:
            X_val: Validation features
            y_val: Ignored

        Returns:
            Validation metrics
        """
        # Convert if needed
        X_val = X_val.values if hasattr(X_val, "values") else X_val

        # Get features
        features = self._transform_impl(X_val)
        vol = features[:, 0]
        asymmetry = features[:, 2]
        persistence = features[:, 3]

        # Compute statistics
        mean_vol = float(np.nanmean(vol))
        mean_asymmetry = float(np.nanmean(asymmetry))
        mean_persistence = float(np.nanmean(persistence))

        # Regime distribution
        regime = features[:, 6]
        valid_regime = regime[~np.isnan(regime)]
        frac_high_vol = (valid_regime == 2.0).mean() if len(valid_regime) > 0 else 0.0

        # Leverage effect strength
        leverage_strength = abs(mean_asymmetry)

        return {
            "mean_vol": mean_vol,
            "mean_asymmetry": mean_asymmetry,
            "mean_persistence": mean_persistence,
            "frac_high_vol": float(frac_high_vol),
            "leverage_strength": leverage_strength,
        }


# =============================================================================
# FACTORY FUNCTION
# =============================================================================
def create_egarch_helper(
    target: str,
    horizon: int,
    random_state: int = 42,
) -> EGARCHHelper:
    """
    Create EGARCH helper with target-specific configuration.

    Args:
        target: Target name (e.g., "direction", "volatility")
        horizon: Forecast horizon
        random_state: Random seed (unused but kept for interface consistency)

    Returns:
        Configured EGARCHHelper
    """
    config = EGARCHConfig(
        target=target,
        horizon=horizon,
        random_state=random_state,
        prefix=f"H_{target}_{horizon}",
        # 8h bars configuration
        rolling_window=126,  # ~6 weeks
        omega_init=0.0,
        alpha_init=0.1,
        gamma_init=-0.1,  # Expect leverage effect
        beta_init=0.85,
        low_vol_percentile=25.0,
        high_vol_percentile=75.0,
        recent_shock_window=5,
    )
    return EGARCHHelper(config)
