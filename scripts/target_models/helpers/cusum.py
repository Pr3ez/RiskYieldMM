"""
CUSUM (Cumulative Sum Control Chart) Helper.

Change point detection using CUSUM with:
- Rolling normalization (adaptive to changing conditions)
- Reset after detection (prevents runaway accumulation)
- Minimum spacing (prevents clustered detections)
- Multi-target support (returns, volatility)

Features Generated (~12 per target-horizon):
- cusum_pos/neg: Raw CUSUM values
- changepoint_up/down/any: Binary change indicators
- magnitude: Size of detected change
- days_since: Time since last changepoint
- combined: Either vol or return changepoint

Now uses Rust backend for ~200x speedup when available.
"""

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
class CUSUMConfig(HelperConfig):
    """Configuration specific to CUSUM helper."""

    # CUSUM parameters
    threshold: float = 2.0  # Detection threshold (in std devs)
    drift: float = 0.0  # Drift term (0 = no drift adjustment)
    min_spacing: int = 5  # Minimum bars between detections

    # Rolling normalization
    rolling_window: int = 63  # Window for z-score normalization

    # Feature columns to use (by name pattern or index)
    # If empty, will use returns and volatility proxies
    return_col_idx: int = 0  # Index of return-like feature
    vol_col_idx: int = 1  # Index of volatility-like feature


# =============================================================================
# CUSUM HELPER
# =============================================================================
class CUSUMHelper(BaseHelper):
    """
    CUSUM change point detection helper.

    Applies CUSUM algorithm to returns and volatility series to
    detect regime changes and structural breaks.

    Uses Rust backend when available for ~200x speedup.

    Features generated:
    - H_{prefix}_cusum_ret_pos: Positive CUSUM for returns
    - H_{prefix}_cusum_ret_neg: Negative CUSUM for returns
    - H_{prefix}_cusum_vol_pos: Positive CUSUM for volatility
    - H_{prefix}_cusum_vol_neg: Negative CUSUM for volatility
    - H_{prefix}_cp_ret_up: Return increase changepoint
    - H_{prefix}_cp_ret_down: Return decrease changepoint
    - H_{prefix}_cp_vol_up: Volatility increase changepoint
    - H_{prefix}_cp_vol_down: Volatility decrease changepoint
    - H_{prefix}_cp_any: Any changepoint detected
    - H_{prefix}_cp_magnitude: Change magnitude (if detected)
    - H_{prefix}_days_since_cp: Days since last changepoint
    - H_{prefix}_cp_count_21: Rolling 21-bar changepoint count
    """

    def __init__(self, config: CUSUMConfig | None = None):
        super().__init__(config or CUSUMConfig())
        self.config: CUSUMConfig  # Type hint

        # Fitted parameters (rolling stats from training)
        self._return_mean: float = 0.0
        self._return_std: float = 1.0
        self._vol_mean: float = 0.0
        self._vol_std: float = 1.0

    @property
    def supports_incremental(self) -> bool:
        """CUSUM requires full refit for threshold calibration.

        The detection thresholds need to be calibrated on the full
        training data distribution to maintain proper false positive rates.
        """
        return False

    @property
    def helper_name(self) -> str:
        return "cusum"

    def _fit_impl(self, X: np.ndarray, y: np.ndarray | None = None) -> None:
        """
        Compute baseline statistics for CUSUM normalization.

        Args:
            X: Feature matrix (n_samples, n_features)
            y: Ignored
        """
        n_samples, n_features = X.shape

        # Extract return and volatility proxies
        ret_idx = min(self.config.return_col_idx, n_features - 1)
        vol_idx = min(self.config.vol_col_idx, n_features - 1)

        returns = X[:, ret_idx]
        volatility = X[:, vol_idx]

        # Compute baseline statistics (robust to outliers)
        self._return_mean = float(np.nanmedian(returns))
        self._return_std = float(np.nanstd(returns)) + 1e-8

        self._vol_mean = float(np.nanmedian(volatility))
        self._vol_std = float(np.nanstd(volatility)) + 1e-8

        self._fit_params = {
            "n_samples": n_samples,
            "return_col_idx": ret_idx,
            "vol_col_idx": vol_idx,
            "return_mean": self._return_mean,
            "return_std": self._return_std,
            "vol_mean": self._vol_mean,
            "vol_std": self._vol_std,
        }

        if self.config.verbose:
            print(f"CUSUMHelper fitted on {X.shape}")
            print(
                f"  Return baseline: μ={self._return_mean:.6f}, σ={self._return_std:.6f}"
            )
            print(f"  Vol baseline: μ={self._vol_mean:.6f}, σ={self._vol_std:.6f}")

    def _transform_impl(self, X: np.ndarray) -> np.ndarray:
        """
        Generate CUSUM-based features.

        Args:
            X: Feature matrix (n_samples, n_features)

        Returns:
            Feature matrix (n_samples, 12) with CUSUM features
        """
        n_features = X.shape[1]

        # Extract series
        ret_idx = min(self.config.return_col_idx, n_features - 1)
        vol_idx = min(self.config.vol_col_idx, n_features - 1)

        returns = X[:, ret_idx]
        volatility = X[:, vol_idx]

        # Use Rust backend if available (~200x faster)
        if HAS_RUST:
            return self._transform_rust(returns, volatility)

        # Fallback to Python implementation
        return self._transform_python(returns, volatility)

    def _transform_rust(
        self, returns: np.ndarray, volatility: np.ndarray
    ) -> np.ndarray:
        """Rust-accelerated CUSUM transform."""
        # Ensure contiguous arrays
        returns = np.ascontiguousarray(returns, dtype=np.float64)
        volatility = np.ascontiguousarray(volatility, dtype=np.float64)

        # Call Rust backend
        features = _rust.py_cusum_transform(
            returns,
            volatility,
            self._return_mean,
            self._return_std,
            self._vol_mean,
            self._vol_std,
            threshold=self.config.threshold,
            drift=self.config.drift,
            min_spacing=self.config.min_spacing,
            rolling_window=self.config.rolling_window,
        )

        return features

    def _transform_python(
        self, returns: np.ndarray, volatility: np.ndarray
    ) -> np.ndarray:
        """Pure Python CUSUM transform (fallback)."""
        # Compute CUSUM for returns
        ret_cusum_pos, ret_cusum_neg, ret_cp_up, ret_cp_down = self._compute_cusum(
            returns,
            self._return_mean,
            self._return_std,
        )

        # Compute CUSUM for volatility
        vol_cusum_pos, vol_cusum_neg, vol_cp_up, vol_cp_down = self._compute_cusum(
            volatility,
            self._vol_mean,
            self._vol_std,
        )

        # Combined features
        any_cp = np.maximum.reduce([ret_cp_up, ret_cp_down, vol_cp_up, vol_cp_down])

        # Change magnitude (absolute z-score at changepoint)
        ret_zscore = np.abs((returns - self._return_mean) / self._return_std)
        vol_zscore = np.abs((volatility - self._vol_mean) / self._vol_std)
        magnitude = np.where(any_cp > 0, np.maximum(ret_zscore, vol_zscore), 0.0)

        # Days since last changepoint
        days_since = self._compute_days_since(any_cp)

        # Rolling changepoint count (21-bar window)
        cp_count_21 = self._rolling_sum(any_cp, 21)

        # Stack all features
        features = np.column_stack(
            [
                ret_cusum_pos,
                ret_cusum_neg,
                vol_cusum_pos,
                vol_cusum_neg,
                ret_cp_up,
                ret_cp_down,
                vol_cp_up,
                vol_cp_down,
                any_cp,
                magnitude,
                days_since,
                cp_count_21,
            ]
        )

        return features

    def _compute_cusum(
        self,
        series: np.ndarray,
        mean: float,
        std: float,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """
        Compute CUSUM with reset and minimum spacing.

        Args:
            series: Input time series
            mean: Baseline mean
            std: Baseline std

        Returns:
            cusum_pos, cusum_neg, changepoint_up, changepoint_down
        """
        n = len(series)
        threshold = self.config.threshold
        drift = self.config.drift
        min_spacing = self.config.min_spacing
        window = self.config.rolling_window

        cusum_pos = np.zeros(n)
        cusum_neg = np.zeros(n)
        cp_up = np.zeros(n)
        cp_down = np.zeros(n)

        last_cp_idx = -min_spacing  # Allow first detection

        for i in range(1, n):
            # Use rolling normalization if enough history
            if window > 0 and i >= window:
                window_data = series[max(0, i - window) : i]
                local_mean = np.nanmean(window_data)
                local_std = np.nanstd(window_data) + 1e-8
            else:
                local_mean = mean
                local_std = std

            # Z-score
            z = (series[i] - local_mean) / local_std

            # CUSUM update
            cusum_pos[i] = max(0, cusum_pos[i - 1] + z - drift)
            cusum_neg[i] = min(0, cusum_neg[i - 1] + z + drift)

            # Detection with minimum spacing
            if i - last_cp_idx >= min_spacing:
                if cusum_pos[i] > threshold:
                    cp_up[i] = 1
                    cusum_pos[i] = 0  # Reset after detection
                    last_cp_idx = i
                elif cusum_neg[i] < -threshold:
                    cp_down[i] = 1
                    cusum_neg[i] = 0  # Reset after detection
                    last_cp_idx = i

        return cusum_pos, cusum_neg, cp_up, cp_down

    def _compute_days_since(self, changepoints: np.ndarray) -> np.ndarray:
        """Compute days since last changepoint."""
        n = len(changepoints)
        days_since = np.zeros(n)

        last_cp = -1
        for i in range(n):
            if changepoints[i] > 0:
                last_cp = i
            days_since[i] = i - last_cp if last_cp >= 0 else i

        return days_since

    def _rolling_sum(self, arr: np.ndarray, window: int) -> np.ndarray:
        """Compute rolling sum."""
        n = len(arr)
        result = np.zeros(n)

        cumsum = np.cumsum(arr)
        result[window - 1 :] = cumsum[window - 1 :] - np.concatenate(
            [[0], cumsum[:-window]]
        )

        # Handle early values
        for i in range(min(window - 1, n)):
            result[i] = np.sum(arr[: i + 1])

        return result

    def _get_feature_names(self) -> list[str]:
        """Get feature names."""
        return [
            self._make_feature_name("cusum_ret_pos"),
            self._make_feature_name("cusum_ret_neg"),
            self._make_feature_name("cusum_vol_pos"),
            self._make_feature_name("cusum_vol_neg"),
            self._make_feature_name("cp_ret_up"),
            self._make_feature_name("cp_ret_down"),
            self._make_feature_name("cp_vol_up"),
            self._make_feature_name("cp_vol_down"),
            self._make_feature_name("cp_any"),
            self._make_feature_name("cp_magnitude"),
            self._make_feature_name("days_since_cp"),
            self._make_feature_name("cp_count_21"),
        ]

    def validate(
        self,
        X_val: np.ndarray,
        y_val: np.ndarray | None = None,
    ) -> dict[str, float]:
        """Compute validation metrics."""
        features = self._transform_impl(X_val)

        # Changepoint detection rate
        cp_any_idx = 8  # Index of cp_any feature
        cp_rate = np.mean(features[:, cp_any_idx])

        # Average days between changepoints
        days_since_idx = 10
        avg_spacing = np.mean(features[:, days_since_idx])

        return {
            "changepoint_rate": float(cp_rate),
            "avg_days_since_cp": float(avg_spacing),
        }

    def get_params(self) -> dict[str, Any]:
        """Get detailed parameters."""
        return {
            **super().get_params(),
            "threshold": self.config.threshold,
            "drift": self.config.drift,
            "min_spacing": self.config.min_spacing,
            "rolling_window": self.config.rolling_window,
        }


# =============================================================================
# FACTORY
# =============================================================================
def create_cusum_helper(
    target: str,
    horizon: int,
    task_type: str = "regression",
    **kwargs,
) -> CUSUMHelper:
    """
    Create CUSUMHelper for a specific target-horizon.

    Args:
        target: Target name
        horizon: Prediction horizon
        task_type: Task type
        **kwargs: Additional config overrides

    Returns:
        Configured CUSUMHelper
    """
    config = CUSUMConfig(
        target=target,
        horizon=horizon,
        task_type=task_type,
        prefix=f"{target[:3]}_{horizon}",
        **kwargs,
    )
    return CUSUMHelper(config)
