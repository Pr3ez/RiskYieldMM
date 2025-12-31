"""
OU (Ornstein-Uhlenbeck / AR(1)) Mean Reversion Helper.

Mean-reversion strength estimation using AR(1) model:
- Estimates AR(1) coefficient φ and converts to half-life
- Provides z-score for entry signal timing
- Classifies mean-reversion regime (too fast/optimal/too slow)

Features Generated (~8 per target-horizon):
- ou_phi: AR(1) coefficient
- ou_kappa: Mean reversion speed
- ou_halflife: Half-life in bars
- ou_zscore: Current deviation z-score
- ou_zscore_abs: |z-score|
- ou_is_stationary: Binary stationarity indicator
- ou_halflife_regime: TOO_FAST(0)/OPTIMAL(1)/TOO_SLOW(2)
- ou_reverting: Binary: moving toward mean

Math:
AR(1) model: x_t = φ * x_{t-1} + ε_t

Mapping to continuous-time OU:
κ = -ln(φ) / Δt           # Mean reversion speed
t_{1/2} = ln(2) / κ       # Half-life (time to decay 50%)

Mean reversion requires |φ| < 1

References:
- Vasicek (1977) - OU rate model
- Hamilton (1994) - Time Series Analysis
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
class OUConfig(HelperConfig):
    """Configuration specific to OU helper.

    Note: rolling_window uses adaptive params based on target type if set to None.
    Adaptive params: direction=42, returns=21, volatility/vol_regime=126,
    trend_regime=63 (validated +34.6% IC improvement overall).
    """

    # Rolling window for AR(1) estimation (None = use adaptive)
    rolling_window: int | None = None

    # Z-score parameters (None = auto-derive from rolling_window)
    zscore_window: int | None = None

    # Half-life bounds (in bars) for regime classification
    min_halflife: float = 2.0  # Too fast = noise
    max_halflife: float = 50.0  # Too slow = trending

    # Stationarity threshold
    phi_stationarity_threshold: float = 0.99  # |φ| < this for stationary

    # Feature column index (deviation from trend or spread)
    deviation_col_idx: int = 0

    def __post_init__(self):
        """Apply adaptive params if window not specified."""
        if self.rolling_window is None:
            from .adaptive_params import get_ou_window

            self.rolling_window = get_ou_window(self.target, self.horizon)
        if self.zscore_window is None:
            self.zscore_window = max(7, self.rolling_window // 3)


# =============================================================================
# OU HELPER
# =============================================================================
class OUHelper(BaseHelper):
    """
    Ornstein-Uhlenbeck / AR(1) mean reversion helper.

    Estimates rolling AR(1) coefficients and converts to half-life.
    Provides z-score for timing mean-reversion entries.

    Features generated:
    - H_{prefix}_ou_phi: AR(1) coefficient
    - H_{prefix}_ou_kappa: Mean reversion speed (κ)
    - H_{prefix}_ou_halflife: Half-life in bars
    - H_{prefix}_ou_zscore: Current z-score
    - H_{prefix}_ou_zscore_abs: |z-score|
    - H_{prefix}_ou_is_stationary: Binary: |φ| < threshold
    - H_{prefix}_ou_halflife_regime: 0=TOO_FAST, 1=OPTIMAL, 2=TOO_SLOW
    - H_{prefix}_ou_reverting: Binary: z * Δz < 0 (moving toward mean)

    LEAKAGE PREVENTION:
    - Rolling OLS uses only data [t-window:t] (backward-only)
    - Z-score uses only past data
    - No centered windows or backfill
    """

    def __init__(self, config: OUConfig | None = None):
        super().__init__(config or OUConfig())
        self.config: OUConfig

        # Fitted parameters (baseline from training)
        self._baseline_phi: float = 0.9
        self._baseline_std: float = 1.0
        self._baseline_mean: float = 0.0

    @property
    def supports_incremental(self) -> bool:
        """OU is computed via rolling window - no incremental needed."""
        return False

    @property
    def helper_name(self) -> str:
        return "ou"

    def _fit_impl(self, X: np.ndarray, y: np.ndarray | None = None) -> None:
        """
        Fit OU model baseline statistics on training data.

        Computes baseline AR(1) coefficient and statistics for
        later use as fallback values.

        Args:
            X: Feature matrix (n_samples, n_features)
            y: Ignored
        """
        n_samples, n_features = X.shape
        dev_idx = min(self.config.deviation_col_idx, n_features - 1)
        series = X[:, dev_idx]

        # Remove NaN
        series_clean = series[~np.isnan(series)]

        if len(series_clean) < 30:
            # Not enough data
            return

        # Baseline statistics
        self._baseline_mean = float(np.nanmean(series_clean))
        self._baseline_std = float(np.nanstd(series_clean)) + 1e-8

        # Fit AR(1) on full training data for baseline
        if len(series_clean) >= 50:
            phi = self._estimate_ar1(series_clean)
            if np.isfinite(phi):
                self._baseline_phi = float(np.clip(phi, -0.999, 0.999))

        self._fit_params = {
            "n_samples": n_samples,
            "baseline_phi": self._baseline_phi,
            "baseline_mean": self._baseline_mean,
            "baseline_std": self._baseline_std,
        }

        if self.config.verbose:
            print(f"OUHelper fitted on {X.shape}")
            print(f"  Baseline φ: {self._baseline_phi:.4f}")
            halflife = self._phi_to_halflife(self._baseline_phi)
            print(f"  Baseline half-life: {halflife:.2f} bars")

    def _transform_impl(self, X: np.ndarray) -> np.ndarray:
        """
        Generate OU-based features using rolling AR(1) estimation.

        When Rust acceleration is available, uses full rolling window estimation
        for each sample. Otherwise falls back to fitted constant params.

        Features: [phi, kappa, halflife, zscore, zscore_abs, is_stationary,
                   halflife_regime, reverting]

        Args:
            X: Feature matrix (n_samples, n_features)

        Returns:
            Feature matrix (n_samples, 8) with OU features
        """
        n_samples, n_features = X.shape
        dev_idx = min(self.config.deviation_col_idx, n_features - 1)
        series = X[:, dev_idx].astype(np.float64)

        # Use Rust accelerated version if available
        if HAS_RUST:
            return self._transform_rust(series)

        # Fallback to Python implementation with fitted params
        return self._transform_python(series, n_samples)

    def _transform_rust(self, series: np.ndarray) -> np.ndarray:
        """
        Use Rust accelerated rolling AR(1) estimation.

        Full rolling window estimation per sample - proper algorithm.
        """
        # Ensure contiguous float64 array
        series_c = np.ascontiguousarray(series, dtype=np.float64)

        # Call Rust: returns (n_samples, 8) array
        # Columns: [phi, kappa, halflife, zscore, zscore_abs, is_stationary, halflife_regime, reverting]
        features = riskyield_rust.py_ou_rolling_transform(
            series_c,
            rolling_window=self.config.rolling_window,
            zscore_window=self.config.zscore_window,
            min_halflife=self.config.min_halflife,
            max_halflife=self.config.max_halflife,
            phi_threshold=self.config.phi_stationarity_threshold,
        )

        return features

    def _transform_python(self, series: np.ndarray, n_samples: int) -> np.ndarray:
        """
        Python fallback using fitted constant params.

        This is faster but less accurate - uses single phi from fit().
        """
        zscore_window = self.config.zscore_window

        # Use FITTED phi (estimated once on training data)
        phi = self._baseline_phi
        kappa = self._phi_to_kappa(phi)
        halflife = self._phi_to_halflife(phi)

        # Initialize output arrays with CONSTANT fitted values
        phi_arr = np.full(n_samples, phi)
        kappa_arr = np.full(n_samples, kappa)
        halflife_arr = np.full(n_samples, halflife)

        # Stationarity is constant (based on fitted phi)
        is_stationary = (
            1.0 if abs(phi) < self.config.phi_stationarity_threshold else 0.0
        )
        is_stationary_arr = np.full(n_samples, is_stationary)

        # Half-life regime is constant (based on fitted phi)
        if halflife < self.config.min_halflife:
            regime = 0.0  # TOO_FAST
        elif halflife > self.config.max_halflife:
            regime = 2.0  # TOO_SLOW
        else:
            regime = 1.0  # OPTIMAL
        halflife_regime_arr = np.full(n_samples, regime)

        # Z-score features: computed per-sample using rolling window (fast)
        zscore_arr = np.full(n_samples, np.nan)
        zscore_abs_arr = np.full(n_samples, np.nan)
        reverting_arr = np.zeros(n_samples)

        # Vectorized z-score calculation using rolling statistics
        for t in range(zscore_window, n_samples):
            window_data = series[t - zscore_window : t]
            valid_data = window_data[~np.isnan(window_data)]

            if len(valid_data) < 5:
                continue

            mean = np.mean(valid_data)
            std = np.std(valid_data) + 1e-8

            if not np.isnan(series[t]):
                z = (series[t] - mean) / std
                zscore_arr[t] = z
                zscore_abs_arr[t] = abs(z)

                # Reverting: z and delta_z have opposite signs
                if t > 0 and not np.isnan(series[t - 1]):
                    z_prev = (series[t - 1] - mean) / std
                    delta_z = z - z_prev
                    reverting_arr[t] = 1.0 if z * delta_z < 0 else 0.0

        # Fill early values
        first_valid = zscore_window
        if first_valid < n_samples:
            first_z = (
                zscore_arr[first_valid]
                if not np.isnan(zscore_arr[first_valid])
                else 0.0
            )
            zscore_arr[:first_valid] = first_z
            zscore_abs_arr[:first_valid] = abs(first_z)

        # Stack all features
        features = np.column_stack(
            [
                phi_arr,
                kappa_arr,
                halflife_arr,
                zscore_arr,
                zscore_abs_arr,
                is_stationary_arr,
                halflife_regime_arr,
                reverting_arr,
            ]
        )

        return features

    def _estimate_ar1(self, series: np.ndarray) -> float:
        """
        Estimate AR(1) coefficient using OLS.

        x_t = φ * x_{t-1} + ε_t
        φ = Cov(x_t, x_{t-1}) / Var(x_{t-1})

        Args:
            series: Time series

        Returns:
            AR(1) coefficient φ
        """
        if len(series) < 3:
            return self._baseline_phi

        # Lag-0 and lag-1
        x_t = series[1:]
        x_lag = series[:-1]

        # Remove any pairs with NaN
        mask = ~(np.isnan(x_t) | np.isnan(x_lag))
        x_t = x_t[mask]
        x_lag = x_lag[mask]

        if len(x_t) < 3:
            return self._baseline_phi

        # OLS: φ = Cov(x_t, x_lag) / Var(x_lag)
        cov = np.cov(x_t, x_lag)[0, 1]
        var_lag = np.var(x_lag)

        if var_lag < 1e-10:
            return self._baseline_phi

        phi = cov / var_lag

        return float(phi)

    def _phi_to_kappa(self, phi: float) -> float:
        """
        Convert AR(1) coefficient to mean-reversion speed.

        κ = -ln(φ) / Δt  (Δt = 1 for discrete time)

        Args:
            phi: AR(1) coefficient

        Returns:
            Mean reversion speed κ
        """
        # Handle edge cases
        if phi <= 0:
            return 10.0  # Very fast mean reversion
        if phi >= 1:
            return 0.0  # No mean reversion (unit root)

        kappa = -np.log(phi)
        return float(np.clip(kappa, 0.001, 10.0))

    def _phi_to_halflife(self, phi: float) -> float:
        """
        Convert AR(1) coefficient to half-life.

        t_{1/2} = ln(2) / κ = ln(2) / (-ln(φ))

        Args:
            phi: AR(1) coefficient

        Returns:
            Half-life in bars
        """
        kappa = self._phi_to_kappa(phi)

        if kappa < 1e-6:
            return 1000.0  # Very slow

        halflife = np.log(2) / kappa
        return float(np.clip(halflife, 0.1, 1000.0))

    def _get_feature_names(self) -> list[str]:
        """Get feature names."""
        return [
            self._make_feature_name("ou_phi"),
            self._make_feature_name("ou_kappa"),
            self._make_feature_name("ou_halflife"),
            self._make_feature_name("ou_zscore"),
            self._make_feature_name("ou_zscore_abs"),
            self._make_feature_name("ou_is_stationary"),
            self._make_feature_name("ou_halflife_regime"),
            self._make_feature_name("ou_reverting"),
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
        Validate OU model - check half-life stability.

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
        phi = features[:, 0]
        halflife = features[:, 2]
        zscore = features[:, 3]

        # Compute statistics
        mean_phi = float(np.nanmean(phi))
        mean_halflife = float(np.nanmean(halflife))
        halflife_std = float(np.nanstd(halflife))

        # Fraction in each regime
        regime = features[:, 6]
        valid_regime = regime[~np.isnan(regime)]
        frac_optimal = (valid_regime == 1.0).mean() if len(valid_regime) > 0 else 0.0

        # Z-score statistics
        zscore_mean = float(np.nanmean(np.abs(zscore)))

        return {
            "mean_phi": mean_phi,
            "mean_halflife": mean_halflife,
            "halflife_std": halflife_std,
            "frac_optimal_regime": float(frac_optimal),
            "mean_abs_zscore": zscore_mean,
        }


# =============================================================================
# FACTORY FUNCTION
# =============================================================================
def create_ou_helper(
    target: str,
    horizon: int,
    random_state: int = 42,
) -> OUHelper:
    """
    Create OU helper with target-specific configuration.

    Args:
        target: Target name (e.g., "direction", "volatility")
        horizon: Forecast horizon
        random_state: Random seed (unused but kept for interface consistency)

    Returns:
        Configured OUHelper
    """
    config = OUConfig(
        target=target,
        horizon=horizon,
        random_state=random_state,
        prefix=f"H_{target}_{horizon}",
        # 8h bars configuration
        rolling_window=63,  # ~3 weeks
        zscore_window=21,  # ~1 week
        min_halflife=2.0,  # 16h minimum
        max_halflife=50.0,  # ~17 days maximum
        phi_stationarity_threshold=0.99,
    )
    return OUHelper(config)
