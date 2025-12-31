"""
BOCPD (Bayesian Online Changepoint Detection) Helper.

Detects regime shifts in real-time using Bayesian inference:
- Tracks posterior over run length (time since last changepoint)
- Detects changes in mean or variance
- Provides probability of recent changepoint

Features Generated (~7 per target-horizon):
- bocpd_run_length: Expected run length (time since last CP)
- bocpd_cp_prob: Probability of changepoint at current bar
- bocpd_cp_recent: Binary: changepoint in last N bars
- bocpd_run_length_norm: Normalized run length
- bocpd_regime_age: Same as run_length (semantic alias)
- bocpd_cp_intensity: Rolling sum of CP probabilities
- bocpd_stability: 1 - cp_prob (regime stability indicator)

Math:
Recursive posterior over run length r_t:
P(r_t | x_{1:t}) ∝ P(x_t | r_t) P(r_t | r_{t-1}) P(r_{t-1} | x_{1:t-1})

Hazard function H(τ) = 1/λ (constant hazard rate)

References:
- Adams & MacKay (2007) - Bayesian Online Changepoint Detection
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
class BOCPDConfig(HelperConfig):
    """Configuration specific to BOCPD helper."""

    # Prior hazard rate (expected run length = 1/hazard)
    # 1/250 means expected ~250 bars between changepoints
    hazard_rate: float = 1 / 250

    # Truncation length for run length distribution
    # PERFORMANCE: Keep small for efficiency (50-100 sufficient for most regimes)
    max_run_length: int = 100

    # Observation model parameters
    # Prior mean and precision for Normal-Gamma conjugate prior
    prior_mean: float = 0.0
    prior_precision: float = 0.1  # Low = vague prior
    prior_alpha: float = 1.0  # Shape parameter
    prior_beta: float = 1.0  # Rate parameter

    # Changepoint detection threshold
    cp_threshold: float = 0.3  # P(CP) > threshold = changepoint

    # Recent window for "recent changepoint" feature
    recent_window: int = 5  # bars

    # Rolling window for intensity calculation
    intensity_window: int = 21

    # Feature column index (observation series)
    observation_col_idx: int = 0


# =============================================================================
# BOCPD HELPER
# =============================================================================
class BOCPDHelper(BaseHelper):
    """
    Bayesian Online Changepoint Detection helper.

    Computes posterior over run length (time since last changepoint)
    using conjugate Normal-Gamma model.

    Features generated:
    - H_{prefix}_bocpd_run_length: Expected run length
    - H_{prefix}_bocpd_cp_prob: Changepoint probability
    - H_{prefix}_bocpd_cp_recent: Binary: CP in last N bars
    - H_{prefix}_bocpd_run_length_norm: Run length / max_run_length
    - H_{prefix}_bocpd_regime_age: Same as run_length
    - H_{prefix}_bocpd_cp_intensity: Rolling CP probability sum
    - H_{prefix}_bocpd_stability: 1 - cp_prob

    LEAKAGE PREVENTION:
    - Online algorithm - processes data sequentially
    - At time t, only uses observations x_{1:t}
    - No backward smoothing or future data access
    """

    def __init__(self, config: BOCPDConfig | None = None):
        super().__init__(config or BOCPDConfig())
        self.config: BOCPDConfig

        # Prior parameters (set during fit)
        self._prior_mu: float = 0.0
        self._prior_kappa: float = 0.1
        self._prior_alpha: float = 1.0
        self._prior_beta: float = 1.0

    @property
    def supports_incremental(self) -> bool:
        """BOCPD is inherently online - supports incremental."""
        return True

    @property
    def helper_name(self) -> str:
        return "bocpd"

    def _fit_impl(self, X: np.ndarray, y: np.ndarray | None = None) -> None:
        """
        Fit BOCPD prior parameters on training data.

        Sets prior hyperparameters for Normal-Gamma conjugate model
        based on training data statistics.

        Args:
            X: Feature matrix (n_samples, n_features)
            y: Ignored
        """
        n_samples, n_features = X.shape
        obs_idx = min(self.config.observation_col_idx, n_features - 1)
        series = X[:, obs_idx]

        # Clean series
        series_clean = series[~np.isnan(series)]

        if len(series_clean) < 30:
            # Use config defaults
            self._prior_mu = self.config.prior_mean
            self._prior_kappa = self.config.prior_precision
            self._prior_alpha = self.config.prior_alpha
            self._prior_beta = self.config.prior_beta
        else:
            # Set prior based on data statistics
            data_mean = np.mean(series_clean)
            data_var = np.var(series_clean) + 1e-8

            self._prior_mu = data_mean
            self._prior_kappa = self.config.prior_precision
            self._prior_alpha = self.config.prior_alpha
            # Prior beta based on empirical variance
            self._prior_beta = data_var * self._prior_alpha

        self._fit_params = {
            "n_samples": n_samples,
            "prior_mu": self._prior_mu,
            "prior_kappa": self._prior_kappa,
            "prior_alpha": self._prior_alpha,
            "prior_beta": self._prior_beta,
        }

        if self.config.verbose:
            print(f"BOCPDHelper fitted on {X.shape}")
            print(f"  Prior μ: {self._prior_mu:.4f}")
            print(f"  Prior κ: {self._prior_kappa:.4f}")
            print(f"  Hazard rate: {self.config.hazard_rate:.6f}")

    def _transform_impl(self, X: np.ndarray) -> np.ndarray:
        """
        Run BOCPD algorithm and generate features.

        CRITICAL: Online algorithm - at time t, only uses x_{1:t}

        When Rust acceleration is available, uses Rust implementation.
        Otherwise falls back to Python.

        Args:
            X: Feature matrix (n_samples, n_features)

        Returns:
            Feature matrix (n_samples, 7) with BOCPD features
        """
        n_samples, n_features = X.shape
        obs_idx = min(self.config.observation_col_idx, n_features - 1)
        series = X[:, obs_idx].astype(np.float64)

        # Use Rust accelerated version if available
        if HAS_RUST:
            return self._transform_rust(series)

        # Fallback to Python implementation
        return self._transform_python(series, n_samples)

    def _transform_rust(self, series: np.ndarray) -> np.ndarray:
        """
        Use Rust accelerated BOCPD algorithm.
        """
        # Ensure contiguous float64 array
        series_c = np.ascontiguousarray(series, dtype=np.float64)

        # Call Rust: returns (n_samples, 7) array
        # Columns: [run_length, cp_prob, cp_recent, run_length_norm,
        #           regime_age, cp_intensity, stability]
        features = riskyield_rust.py_bocpd_online(
            series_c,
            hazard_rate=self.config.hazard_rate,
            max_run_length=self.config.max_run_length,
            prior_mu=self._prior_mu,
            prior_kappa=self._prior_kappa,
            prior_alpha=self._prior_alpha,
            prior_beta=self._prior_beta,
            cp_threshold=self.config.cp_threshold,
            recent_window=self.config.recent_window,
            intensity_window=self.config.intensity_window,
        )

        return features

    def _transform_python(self, series: np.ndarray, n_samples: int) -> np.ndarray:
        """
        Python implementation of BOCPD algorithm.
        """
        max_rl = self.config.max_run_length
        hazard = self.config.hazard_rate

        # Initialize output arrays
        run_length_arr = np.zeros(n_samples)
        cp_prob_arr = np.zeros(n_samples)
        cp_recent_arr = np.zeros(n_samples)
        run_length_norm_arr = np.zeros(n_samples)
        cp_intensity_arr = np.zeros(n_samples)
        stability_arr = np.ones(n_samples)

        # Run BOCPD
        run_lengths, cp_probs = self._run_bocpd_online(series, max_rl, hazard)

        # Fill arrays
        run_length_arr[:] = run_lengths
        cp_prob_arr[:] = cp_probs
        run_length_norm_arr[:] = run_lengths / max_rl
        stability_arr[:] = 1.0 - cp_probs

        # Binary changepoint detection
        cp_detected = cp_probs > self.config.cp_threshold

        # Recent changepoint (any CP in last N bars)
        recent_window = self.config.recent_window
        for t in range(n_samples):
            start_idx = max(0, t - recent_window + 1)
            cp_recent_arr[t] = 1.0 if np.any(cp_detected[start_idx : t + 1]) else 0.0

        # CP intensity (rolling sum of CP probabilities)
        intensity_window = self.config.intensity_window
        for t in range(n_samples):
            start_idx = max(0, t - intensity_window + 1)
            cp_intensity_arr[t] = np.sum(cp_probs[start_idx : t + 1])

        # Stack all features
        features = np.column_stack(
            [
                run_length_arr,
                cp_prob_arr,
                cp_recent_arr,
                run_length_norm_arr,
                run_length_arr,  # regime_age (same as run_length)
                cp_intensity_arr,
                stability_arr,
            ]
        )

        return features

    def _run_bocpd_online(
        self,
        series: np.ndarray,
        max_rl: int,
        hazard: float,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Run BOCPD algorithm online.

        Uses Normal-Gamma conjugate prior for efficient updates.

        Args:
            series: Observation series
            max_rl: Maximum run length to track
            hazard: Constant hazard rate

        Returns:
            (expected_run_lengths, changepoint_probabilities)
        """
        n = len(series)

        # Output arrays
        expected_rl = np.zeros(n)
        cp_prob = np.zeros(n)

        # Initialize run length distribution
        # R[r] = P(r_t = r | x_{1:t})
        R = np.zeros(max_rl + 1)
        R[0] = 1.0  # Start with run length 0

        # Sufficient statistics for each run length
        # For Normal-Gamma: track sum(x), sum(x^2), count
        sum_x = np.zeros(max_rl + 1)
        sum_x2 = np.zeros(max_rl + 1)
        counts = np.zeros(max_rl + 1)

        for t in range(n):
            x = series[t]

            # Handle NaN - treat as missing, don't update
            if np.isnan(x):
                expected_rl[t] = expected_rl[t - 1] if t > 0 else 0
                cp_prob[t] = 0.0
                continue

            # Predictive probability P(x_t | r_t = r, x_{1:t-1})
            pred_prob = np.zeros(max_rl + 1)

            for r in range(max_rl + 1):
                if R[r] < 1e-10:
                    continue

                # Compute posterior predictive for this run length
                # Student-t distribution
                pred_prob[r] = self._predictive_probability(
                    x, sum_x[r], sum_x2[r], counts[r]
                )

            # Growth probabilities: P(r_t = r+1 | r_{t-1} = r) = 1 - hazard
            growth_prob = R[:-1] * pred_prob[:-1] * (1 - hazard)

            # Changepoint probability: sum over all previous run lengths
            cp_mass = np.sum(R * pred_prob * hazard)

            # New run length distribution
            R_new = np.zeros(max_rl + 1)
            R_new[0] = cp_mass
            R_new[1:] = growth_prob

            # Normalize
            total = np.sum(R_new)
            if total > 1e-10:
                R_new /= total
            else:
                R_new[0] = 1.0

            # Update sufficient statistics
            # Shift statistics for growth
            sum_x_new = np.zeros(max_rl + 1)
            sum_x2_new = np.zeros(max_rl + 1)
            counts_new = np.zeros(max_rl + 1)

            # For r=0 (new segment), start fresh
            sum_x_new[0] = 0
            sum_x2_new[0] = 0
            counts_new[0] = 0

            # For r>0, inherit from r-1 and add new observation
            for r in range(1, max_rl + 1):
                if R_new[r] > 1e-10:
                    sum_x_new[r] = sum_x[r - 1] + x
                    sum_x2_new[r] = sum_x2[r - 1] + x * x
                    counts_new[r] = counts[r - 1] + 1

            # Update state
            R = R_new
            sum_x = sum_x_new
            sum_x2 = sum_x2_new
            counts = counts_new

            # Expected run length
            expected_rl[t] = np.sum(np.arange(max_rl + 1) * R)

            # Changepoint probability (mass on r=0)
            cp_prob[t] = R[0]

        return expected_rl, cp_prob

    def _predictive_probability(
        self,
        x: float,
        sum_x: float,
        sum_x2: float,
        n: float,
    ) -> float:
        """
        Compute predictive probability under Normal-Gamma conjugate prior.

        The posterior predictive is Student-t distributed.

        Args:
            x: New observation
            sum_x: Sum of previous observations
            sum_x2: Sum of squared previous observations
            n: Number of previous observations

        Returns:
            P(x | previous observations)
        """
        # Update prior parameters
        mu0 = self._prior_mu
        kappa0 = self._prior_kappa
        alpha0 = self._prior_alpha
        beta0 = self._prior_beta

        # Posterior parameters
        kappa_n = kappa0 + n
        alpha_n = alpha0 + n / 2

        if n > 0:
            mean_x = sum_x / n
            mu_n = (kappa0 * mu0 + n * mean_x) / kappa_n
            # Sample variance
            ss = sum_x2 - n * mean_x * mean_x
            beta_n = beta0 + 0.5 * ss + 0.5 * kappa0 * n * (mean_x - mu0) ** 2 / kappa_n
        else:
            mu_n = mu0
            beta_n = beta0

        # Predictive distribution is Student-t
        # t_{2α}(μ, β(κ+1)/(ακ))
        df = 2 * alpha_n
        loc = mu_n
        scale = np.sqrt(beta_n * (kappa_n + 1) / (alpha_n * kappa_n) + 1e-8)

        # PDF of Student-t
        try:
            prob = stats.t.pdf(x, df, loc=loc, scale=scale)
        except (ValueError, FloatingPointError):
            prob = 1e-10

        return max(prob, 1e-10)

    def _get_feature_names(self) -> list[str]:
        """Get feature names."""
        return [
            self._make_feature_name("bocpd_run_length"),
            self._make_feature_name("bocpd_cp_prob"),
            self._make_feature_name("bocpd_cp_recent"),
            self._make_feature_name("bocpd_run_length_norm"),
            self._make_feature_name("bocpd_regime_age"),
            self._make_feature_name("bocpd_cp_intensity"),
            self._make_feature_name("bocpd_stability"),
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
        Validate BOCPD model - check changepoint statistics.

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
        run_length = features[:, 0]
        cp_prob = features[:, 1]
        cp_recent = features[:, 2]

        # Compute statistics
        mean_run_length = float(np.nanmean(run_length))
        cp_rate = float(np.nanmean(cp_prob))
        frac_recent_cp = float(np.nanmean(cp_recent))

        # Number of detected changepoints
        n_changepoints = int(np.sum(cp_prob > self.config.cp_threshold))

        return {
            "mean_run_length": mean_run_length,
            "cp_rate": cp_rate,
            "frac_recent_cp": frac_recent_cp,
            "n_changepoints_detected": n_changepoints,
        }


# =============================================================================
# FACTORY FUNCTION
# =============================================================================
def create_bocpd_helper(
    target: str,
    horizon: int,
    random_state: int = 42,
) -> BOCPDHelper:
    """
    Create BOCPD helper with target-specific configuration.

    Args:
        target: Target name (e.g., "direction", "volatility")
        horizon: Forecast horizon
        random_state: Random seed (unused but kept for interface consistency)

    Returns:
        Configured BOCPDHelper
    """
    config = BOCPDConfig(
        target=target,
        horizon=horizon,
        random_state=random_state,
        prefix=f"H_{target}_{horizon}",
        # 8h bars configuration
        # ~250 bars = ~80 days expected between changepoints
        hazard_rate=1 / 250,
        max_run_length=500,
        cp_threshold=0.3,
        recent_window=5,
        intensity_window=21,
    )
    return BOCPDHelper(config)
