"""
EVT POT (Extreme Value Theory - Peaks Over Threshold) Helper.

Tail risk estimation using Generalized Pareto Distribution (GPD):
- Estimates tail heaviness (shape parameter ξ)
- Provides VaR/ES estimates from fitted GPD
- Detects fat-tail regimes for risk gating

Features Generated (~10 per target-horizon):
- evt_xi: Shape parameter (tail heaviness)
- evt_beta: Scale parameter
- evt_exceedance_rate: Fraction above threshold
- evt_var95/var99: Value at Risk estimates
- evt_es95: Expected Shortfall (CVaR)
- evt_tail_prob_2std/3std: Tail probability estimates
- evt_tail_flag: Binary fat-tail indicator
- evt_regime: NORMAL/FAT_TAIL regime

Math (Pickands-Balkema-de Haan theorem):
For high threshold u, exceedances Y = X - u | X > u follow GPD:
P(Y ≤ y) = 1 - (1 + ξy/β)^(-1/ξ)

Where:
- ξ (xi) > 0: Fréchet (heavy tail, infinite higher moments)
- ξ = 0: Gumbel (exponential tail)
- ξ < 0: Weibull (bounded tail)

References:
- Coles (2001) - An Introduction to Statistical Modeling of Extreme Values
- McNeil, Frey, Embrechts (2015) - Quantitative Risk Management
"""

from dataclasses import dataclass

import numpy as np
from scipy import stats

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
class EVTPOTConfig(HelperConfig):
    """Configuration specific to EVT POT helper.

    Note: threshold_percentile uses adaptive params based on target type if None.
    Adaptive params: direction/volatility/vol_regime=99.0, returns=92.5,
    trend_regime=95.0 (validated +34.6% IC improvement overall).
    """

    # Threshold selection (None = use adaptive params)
    threshold_percentile: float | None = None
    min_exceedances: int = 30  # Minimum exceedances for stable GPD fit

    # Rolling window for time-varying tail estimation
    # For 8h bars: 63 bars ≈ 3 weeks, 252 bars ≈ 3 months
    rolling_window: int = 252

    # Declustering (handle volatility clustering in exceedances)
    decluster: bool = True
    decluster_gap: int = 3  # Min bars between cluster peaks (8h bars)

    # Tail probability thresholds (in std devs)
    tail_2std_mult: float = 2.0
    tail_3std_mult: float = 3.0

    # Fat-tail regime threshold (xi value)
    fat_tail_xi_threshold: float = 0.25  # ξ > 0.25 means heavy tail

    # Feature column index (returns)
    return_col_idx: int = 0

    # Use absolute returns (two-sided tail) vs signed (one-sided)
    use_absolute: bool = True

    def __post_init__(self):
        """Apply adaptive params if percentile not specified."""
        if self.threshold_percentile is None:
            from .adaptive_params import get_evt_percentile

            self.threshold_percentile = get_evt_percentile(self.target, self.horizon)


# =============================================================================
# EVT POT HELPER
# =============================================================================
class EVTPOTHelper(BaseHelper):
    """
    EVT Peaks-Over-Threshold helper for tail risk estimation.

    Uses GPD (Generalized Pareto Distribution) to model exceedances
    over a threshold. Provides rolling estimates of tail heaviness
    and tail probability features for risk gating.

    Features generated:
    - H_{prefix}_evt_xi: Shape parameter (tail heaviness)
    - H_{prefix}_evt_beta: Scale parameter
    - H_{prefix}_evt_exceedance_rate: λ_u (fraction above threshold)
    - H_{prefix}_evt_var95: 95% VaR from GPD
    - H_{prefix}_evt_var99: 99% VaR from GPD
    - H_{prefix}_evt_es95: 95% Expected Shortfall
    - H_{prefix}_evt_tail_prob_2std: P(|return| > 2σ)
    - H_{prefix}_evt_tail_prob_3std: P(|return| > 3σ)
    - H_{prefix}_evt_tail_flag: Binary: tail risk elevated (ξ > threshold)
    - H_{prefix}_evt_regime: 0=NORMAL, 1=FAT_TAIL

    LEAKAGE PREVENTION:
    - Rolling fit uses only data [t-window:t] (backward-only)
    - Threshold computed during fit() on training data
    - No centered windows or backfill
    """

    def __init__(self, config: EVTPOTConfig | None = None):
        super().__init__(config or EVTPOTConfig())
        self.config: EVTPOTConfig

        # Fitted parameters (from training data)
        self._threshold: float = 0.0  # Exceedance threshold u
        self._baseline_std: float = 1.0  # For computing tail probabilities
        self._baseline_mean: float = 0.0

        # Default GPD parameters (fallback)
        self._default_xi: float = 0.1
        self._default_beta: float = 0.01

    @property
    def supports_incremental(self) -> bool:
        """EVT requires threshold calibration - no incremental support."""
        return False

    @property
    def helper_name(self) -> str:
        return "evt"

    def _fit_impl(self, X: np.ndarray, y: np.ndarray | None = None) -> None:
        """
        Fit EVT POT model on training data.

        Computes:
        1. Threshold u from percentile
        2. Baseline statistics for tail probability computation

        Args:
            X: Feature matrix (n_samples, n_features)
            y: Ignored
        """
        n_samples, n_features = X.shape
        ret_idx = min(self.config.return_col_idx, n_features - 1)
        returns = X[:, ret_idx]

        # Use absolute returns if configured
        if self.config.use_absolute:
            series = np.abs(returns)
        else:
            series = returns

        # Remove NaN
        series_clean = series[~np.isnan(series)]

        if len(series_clean) < 100:
            # Not enough data - use defaults
            self._threshold = (
                float(np.nanpercentile(series_clean, 95))
                if len(series_clean) > 0
                else 0.01
            )
            self._baseline_std = (
                float(np.nanstd(series_clean)) if len(series_clean) > 0 else 0.01
            )
            self._baseline_mean = (
                float(np.nanmean(series_clean)) if len(series_clean) > 0 else 0.0
            )
            return

        # Compute threshold from training data percentile
        self._threshold = float(
            np.nanpercentile(series_clean, self.config.threshold_percentile)
        )

        # Ensure threshold is positive and reasonable
        self._threshold = max(self._threshold, 1e-8)

        # Baseline statistics
        self._baseline_std = float(np.nanstd(returns)) + 1e-8
        self._baseline_mean = float(np.nanmean(returns))

        # Try to fit GPD on training exceedances to get default params
        exceedances = series_clean[series_clean > self._threshold] - self._threshold
        if len(exceedances) >= self.config.min_exceedances:
            try:
                xi, loc, beta = stats.genpareto.fit(exceedances, floc=0)
                # Validate parameters
                if np.isfinite(xi) and np.isfinite(beta) and beta > 0:
                    self._default_xi = float(np.clip(xi, -0.5, 1.0))
                    self._default_beta = float(beta)
            except Exception:
                pass  # Keep defaults

        self._fit_params = {
            "n_samples": n_samples,
            "threshold": self._threshold,
            "baseline_std": self._baseline_std,
            "default_xi": self._default_xi,
            "default_beta": self._default_beta,
        }

        if self.config.verbose:
            print(f"EVTPOTHelper fitted on {X.shape}")
            print(f"  Threshold: {self._threshold:.6f}")
            print(
                f"  Default xi: {self._default_xi:.4f}, beta: {self._default_beta:.6f}"
            )

    def _transform_impl(self, X: np.ndarray) -> np.ndarray:
        """
        Generate EVT-based features using rolling GPD estimation.

        When Rust acceleration is available, uses full rolling window estimation
        for each sample. Otherwise falls back to fitted constant params.

        Args:
            X: Feature matrix (n_samples, n_features)

        Returns:
            Feature matrix (n_samples, 10) with EVT features
        """
        n_samples, n_features = X.shape
        ret_idx = min(self.config.return_col_idx, n_features - 1)
        returns = X[:, ret_idx].astype(np.float64)

        # Use Rust accelerated version if available
        if HAS_RUST:
            return self._transform_rust(returns)

        # Fallback to Python implementation with fitted params
        return self._transform_python(returns, n_samples)

    def _transform_rust(self, returns: np.ndarray) -> np.ndarray:
        """
        Use Rust accelerated rolling GPD estimation.

        Full rolling window estimation per sample - proper algorithm.
        """
        # Ensure contiguous float64 array
        returns_c = np.ascontiguousarray(returns, dtype=np.float64)

        # Call Rust: returns (n_samples, 10) array
        # Columns: [xi, beta, exceedance_rate, var95, var99, es95,
        #           tail_prob_2std, tail_prob_3std, tail_flag, regime]
        features = riskyield_rust.py_evt_rolling_transform(
            returns_c,
            rolling_window=self.config.rolling_window,
            threshold_percentile=self.config.threshold_percentile,
            min_exceedances=self.config.min_exceedances,
            fat_tail_threshold=self.config.fat_tail_xi_threshold,
            fitted_threshold=self._threshold,
        )

        return features

    def _transform_python(self, returns: np.ndarray, n_samples: int) -> np.ndarray:
        """
        Python fallback using fitted constant params.

        This is faster but less accurate - uses single xi/beta from fit().
        """
        # Use absolute returns if configured
        if self.config.use_absolute:
            series = np.abs(returns)
        else:
            series = returns

        window = self.config.rolling_window

        # Use FITTED GPD parameters (estimated once on training data)
        xi = self._default_xi
        beta = self._default_beta

        # Initialize output arrays
        xi_arr = np.full(n_samples, xi)  # Constant (fitted)
        beta_arr = np.full(n_samples, beta)  # Constant (fitted)
        exceedance_rate_arr = np.full(n_samples, np.nan)
        var95_arr = np.full(n_samples, np.nan)
        var99_arr = np.full(n_samples, np.nan)
        es95_arr = np.full(n_samples, np.nan)
        tail_prob_2std_arr = np.full(n_samples, np.nan)
        tail_prob_3std_arr = np.full(n_samples, np.nan)
        tail_flag_arr = np.full(
            n_samples, 1.0 if xi > self.config.fat_tail_xi_threshold else 0.0
        )
        regime_arr = np.full(
            n_samples, 1.0 if xi > self.config.fat_tail_xi_threshold else 0.0
        )

        # Compute per-sample features using FITTED params (fast - no optimization)
        for t in range(window, n_samples):
            window_data = series[t - window : t]
            window_returns = returns[t - window : t]

            valid_data = window_data[~np.isnan(window_data)]
            if len(valid_data) < 50:
                continue

            # Exceedance rate (fast - just counting)
            n_exceed = np.sum(valid_data > self._threshold)
            exceedance_rate = n_exceed / len(valid_data)
            exceedance_rate_arr[t] = exceedance_rate

            # Compute VaR and ES using FITTED xi/beta (fast arithmetic)
            if exceedance_rate > 0:
                var95_arr[t] = self._compute_var(xi, beta, exceedance_rate, 0.95)
                var99_arr[t] = self._compute_var(xi, beta, exceedance_rate, 0.99)
                es95_arr[t] = self._compute_es(xi, beta, exceedance_rate, 0.95)
            else:
                var95_arr[t] = float(np.nanpercentile(valid_data, 95))
                var99_arr[t] = float(np.nanpercentile(valid_data, 99))
                high_vals = valid_data[valid_data > np.nanpercentile(valid_data, 95)]
                es95_arr[t] = (
                    float(np.nanmean(high_vals)) if len(high_vals) > 0 else var95_arr[t]
                )

            # Tail probabilities using FITTED params
            local_std = float(np.nanstd(window_returns)) + 1e-8
            tail_prob_2std_arr[t] = self._compute_tail_prob(
                xi, beta, exceedance_rate, self.config.tail_2std_mult * local_std
            )
            tail_prob_3std_arr[t] = self._compute_tail_prob(
                xi, beta, exceedance_rate, self.config.tail_3std_mult * local_std
            )

        # Fill early values
        first_valid = window
        for arr, default in [
            (exceedance_rate_arr, 0.0),
            (var95_arr, self._threshold),
            (var99_arr, self._threshold * 1.5),
            (es95_arr, self._threshold * 1.2),
            (tail_prob_2std_arr, 0.05),
            (tail_prob_3std_arr, 0.01),
        ]:
            if first_valid < n_samples and not np.isnan(arr[first_valid]):
                arr[:first_valid] = arr[first_valid]
            else:
                arr[:first_valid] = default

        # Stack all features
        features = np.column_stack(
            [
                xi_arr,
                beta_arr,
                exceedance_rate_arr,
                var95_arr,
                var99_arr,
                es95_arr,
                tail_prob_2std_arr,
                tail_prob_3std_arr,
                tail_flag_arr,
                regime_arr,
            ]
        )

        return features

    def _fit_gpd(self, exceedances: np.ndarray) -> tuple[float, float]:
        """
        Fit GPD to exceedances using MLE.

        Args:
            exceedances: Array of exceedances (X - u | X > u)

        Returns:
            (xi, beta) - shape and scale parameters
        """
        try:
            # scipy.stats.genpareto uses (c, loc, scale) parameterization
            # where c = xi (shape), scale = beta
            xi, loc, beta = stats.genpareto.fit(exceedances, floc=0)

            # Validate and clip to reasonable range
            xi = float(np.clip(xi, -0.5, 1.0))
            beta = float(max(beta, 1e-10))

            if not (np.isfinite(xi) and np.isfinite(beta)):
                return self._default_xi, self._default_beta

            return xi, beta

        except Exception:
            return self._default_xi, self._default_beta

    def _decluster_exceedances(
        self, series: np.ndarray, threshold: float, gap: int
    ) -> np.ndarray:
        """
        Decluster exceedances to handle volatility clustering.

        Takes only the maximum exceedance within each cluster,
        where clusters are separated by at least `gap` bars.

        Args:
            series: Full series
            threshold: Exceedance threshold
            gap: Minimum bars between clusters

        Returns:
            Declustered exceedances
        """
        above_threshold = series > threshold
        exceedance_indices = np.where(above_threshold)[0]

        if len(exceedance_indices) == 0:
            return np.array([])

        # Group into clusters
        clusters = []
        current_cluster = [exceedance_indices[0]]

        for i in range(1, len(exceedance_indices)):
            if exceedance_indices[i] - exceedance_indices[i - 1] <= gap:
                current_cluster.append(exceedance_indices[i])
            else:
                clusters.append(current_cluster)
                current_cluster = [exceedance_indices[i]]
        clusters.append(current_cluster)

        # Take max from each cluster
        declustered = []
        for cluster in clusters:
            cluster_values = series[cluster]
            max_idx = cluster[np.argmax(cluster_values)]
            declustered.append(series[max_idx] - threshold)

        return np.array(declustered)

    def _compute_var(
        self, xi: float, beta: float, exceedance_rate: float, p: float
    ) -> float:
        """
        Compute VaR at level p using GPD.

        VaR_p = u + (β/ξ) * ((λ_u / (1-p))^ξ - 1)  for ξ ≠ 0
        VaR_p = u + β * log(λ_u / (1-p))           for ξ = 0

        Args:
            xi: Shape parameter
            beta: Scale parameter
            exceedance_rate: λ_u = P(X > u)
            p: Probability level (e.g., 0.95)

        Returns:
            VaR estimate
        """
        if exceedance_rate <= 0 or exceedance_rate >= 1:
            return self._threshold

        # Probability in the tail
        tail_prob = 1 - p
        if tail_prob >= exceedance_rate:
            # VaR is below threshold
            return self._threshold * 0.5

        if abs(xi) < 1e-10:
            # Exponential case (ξ ≈ 0)
            var = self._threshold + beta * np.log(exceedance_rate / tail_prob)
        else:
            var = self._threshold + (beta / xi) * (
                (exceedance_rate / tail_prob) ** xi - 1
            )

        return float(np.clip(var, 0, 10))  # Clip to reasonable range

    def _compute_es(
        self, xi: float, beta: float, exceedance_rate: float, p: float
    ) -> float:
        """
        Compute Expected Shortfall (CVaR) at level p.

        ES_p = VaR_p / (1 - ξ) + (β - ξ*u) / (1 - ξ)  for ξ < 1

        Args:
            xi: Shape parameter
            beta: Scale parameter
            exceedance_rate: λ_u
            p: Probability level

        Returns:
            ES estimate
        """
        var_p = self._compute_var(xi, beta, exceedance_rate, p)

        if xi >= 1:
            # ES is infinite for ξ ≥ 1
            return var_p * 1.5

        es = var_p / (1 - xi) + (beta - xi * self._threshold) / (1 - xi)
        return float(np.clip(es, var_p, 10))

    def _compute_tail_prob(
        self, xi: float, beta: float, exceedance_rate: float, x: float
    ) -> float:
        """
        Compute tail probability P(X > x) using GPD.

        P(X > x) = λ_u * (1 + ξ*(x-u)/β)^(-1/ξ)  for x > u

        Args:
            xi: Shape parameter
            beta: Scale parameter
            exceedance_rate: λ_u
            x: Threshold value

        Returns:
            Tail probability
        """
        if x <= self._threshold:
            return exceedance_rate

        y = x - self._threshold

        if abs(xi) < 1e-10:
            # Exponential case
            prob = exceedance_rate * np.exp(-y / beta)
        else:
            term = 1 + xi * y / beta
            if term <= 0:
                prob = 0.0
            else:
                prob = exceedance_rate * term ** (-1 / xi)

        return float(np.clip(prob, 0, 1))

    def _get_feature_names(self) -> list[str]:
        """Get feature names."""
        return [
            self._make_feature_name("evt_xi"),
            self._make_feature_name("evt_beta"),
            self._make_feature_name("evt_exceedance_rate"),
            self._make_feature_name("evt_var95"),
            self._make_feature_name("evt_var99"),
            self._make_feature_name("evt_es95"),
            self._make_feature_name("evt_tail_prob_2std"),
            self._make_feature_name("evt_tail_prob_3std"),
            self._make_feature_name("evt_tail_flag"),
            self._make_feature_name("evt_regime"),
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
        Validate EVT model - check VaR coverage.

        Args:
            X_val: Validation features
            y_val: Ignored

        Returns:
            Validation metrics including VaR coverage
        """
        # Convert if needed
        X_val = X_val.values if hasattr(X_val, "values") else X_val

        n_features = X_val.shape[1]
        ret_idx = min(self.config.return_col_idx, n_features - 1)
        returns = X_val[:, ret_idx]

        # Get features
        features = self._transform_impl(X_val)
        var95 = features[:, 3]  # evt_var95
        var99 = features[:, 4]  # evt_var99

        # Use absolute returns if configured
        if self.config.use_absolute:
            actual = np.abs(returns)
        else:
            actual = returns

        # Compute VaR exceedance rates (should be ~5% for VaR95, ~1% for VaR99)
        valid_mask = ~np.isnan(var95) & ~np.isnan(actual)
        if valid_mask.sum() > 0:
            exceedances_95 = (actual[valid_mask] > var95[valid_mask]).mean()
            exceedances_99 = (actual[valid_mask] > var99[valid_mask]).mean()
        else:
            exceedances_95 = 0.0
            exceedances_99 = 0.0

        # Mean xi (tail heaviness indicator)
        mean_xi = float(np.nanmean(features[:, 0]))

        return {
            "var95_exceedance_rate": float(exceedances_95),
            "var99_exceedance_rate": float(exceedances_99),
            "mean_xi": mean_xi,
            "xi_std": float(np.nanstd(features[:, 0])),
        }


# =============================================================================
# FACTORY FUNCTION
# =============================================================================
def create_evt_pot_helper(
    target: str,
    horizon: int,
    random_state: int = 42,
) -> EVTPOTHelper:
    """
    Create EVT POT helper with target-specific configuration.

    Args:
        target: Target name (e.g., "direction", "volatility")
        horizon: Forecast horizon
        random_state: Random seed (unused but kept for interface consistency)

    Returns:
        Configured EVTPOTHelper
    """
    config = EVTPOTConfig(
        target=target,
        horizon=horizon,
        random_state=random_state,
        prefix=f"H_{target}_{horizon}",
        # 8h bars: 252 bars ≈ 3 months
        rolling_window=252,
        threshold_percentile=95.0,
        min_exceedances=20,  # Lower for 8h data (less samples)
        decluster=True,
        decluster_gap=3,  # 3 * 8h = 24h between cluster peaks
        use_absolute=True,  # Two-sided tail
        fat_tail_xi_threshold=0.25,
    )
    return EVTPOTHelper(config)
