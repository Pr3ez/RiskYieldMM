"""
Expanding Z-Score Optimizer (Causal)
====================================

Standardizes features using EXPANDING mean and std (not rolling).
Uses only past data — no future leakage.

CAUSAL GUARANTEE:
    At row N, mean and std are computed from rows 0..N-1 only.
    First `min_periods` rows use available data.

Research basis:
- For volatility prediction, we care about ABSOLUTE magnitude
- Rolling z-score destroys magnitude information (normalizes to local window)
- Expanding z-score preserves magnitude relative to full history
- Welford's algorithm used for numerical stability

Usage:
    optimizer = ExpandingZScoreOptimizer(min_periods=252)
    X_scaled = optimizer.fit_transform(X)
"""

import pandas as pd

from scripts.analysis.optimizers.base import BaseOptimizer


class ExpandingZScoreOptimizer(BaseOptimizer):
    """
    Standardize features using EXPANDING mean/std (causal).

    For each feature at each row:
        mean_t = expanding_mean(x[:t])
        std_t = expanding_std(x[:t])
        z_t = (x_t - mean_t) / std_t

    CAUSAL: Only uses data available up to current row.

    Unlike RollingZScore:
    - Preserves magnitude relative to full history
    - Better for volatility prediction where absolute level matters
    - More stable (doesn't adapt to local regime changes)

    Args:
        min_periods: Minimum observations before computing stats (default 252)
        exclude_patterns: Feature patterns to exclude from scaling
    """

    name = "ExpandingZScore"

    def __init__(
        self,
        min_periods: int = 252,
        exclude_patterns: list[str] | None = None,
    ) -> None:
        super().__init__()
        self.min_periods = min_periods
        self.exclude_patterns = exclude_patterns or [
            "_bnd_",  # Already bounded [0,1]
            "_rnk_",  # Already ranked [0,1]
            "_bin",  # Binary features
            "_zsc_",  # Already z-scored
        ]
        self._cols_to_scale: list[str] = []

    def fit(
        self, X: pd.DataFrame, y: pd.Series | None = None
    ) -> "ExpandingZScoreOptimizer":
        """
        Identify which columns to scale (no params stored — computed causally).

        Args:
            X: Feature DataFrame
            y: Not used

        Returns:
            self
        """
        self._feature_names_in = list(X.columns)
        self._cols_to_scale = []

        for col in X.columns:
            # Check exclusion
            if any(pattern in col for pattern in self.exclude_patterns):
                continue

            # Only include columns with enough non-null values
            if X[col].notna().sum() > self.min_periods:
                self._cols_to_scale.append(col)

        self._feature_names_out = list(X.columns)
        self.is_fitted = True
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """
        Apply CAUSAL expanding z-score standardization.

        At each row, mean/std are computed from all previous rows only.

        Args:
            X: Feature DataFrame

        Returns:
            Scaled DataFrame
        """
        if not self.is_fitted:
            raise RuntimeError("Must call fit() before transform()")

        result = X.copy()

        for col in self._cols_to_scale:
            if col not in result.columns:
                continue

            series = X[col]

            # Compute expanding stats (shifted to avoid using current row)
            expanding_mean = (
                series.expanding(min_periods=self.min_periods)
                .mean()
                .shift(1)  # Use only past data
            )
            expanding_std = (
                series.expanding(min_periods=self.min_periods)
                .std()
                .shift(1)  # Use only past data
            )

            # Z-score using expanding stats
            result[col] = (series - expanding_mean) / (expanding_std + 1e-8)

        return result

    def get_scale_info(self) -> pd.DataFrame:
        """Get summary of columns being scaled."""
        rows = []
        for col in self._cols_to_scale:
            rows.append(
                {
                    "feature": col,
                    "method": "expanding_zscore",
                    "min_periods": self.min_periods,
                }
            )
        return pd.DataFrame(rows)
