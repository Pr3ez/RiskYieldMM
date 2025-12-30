"""
Rolling Z-Score Optimizer
=========================

Fixes distribution drift by applying rolling normalization.
Instead of global mean/std, uses a rolling window to compute
z-scores, making features stationary over time.

Research basis:
- Volatility and market structure change over time
- Global normalization creates look-ahead bias
- Rolling z-score adapts to regime changes

Usage:
    optimizer = RollingZScoreOptimizer(window=252)  # ~84 days for 8h bars
    X_normalized = optimizer.fit_transform(X)
"""

import numpy as np
import pandas as pd

from scripts.analysis.optimizers.base import BaseOptimizer


class RollingZScoreOptimizer(BaseOptimizer):
    """
    Apply rolling z-score normalization to features.

    For each feature:
        z_t = (x_t - rolling_mean_t) / rolling_std_t

    This handles:
        - Distribution drift over time
        - Volatility regime changes
        - Non-stationarity in raw features

    Args:
        window: Rolling window size in bars (default 252 = ~84 days for 8h)
        min_periods: Minimum observations for valid calculation
        exclude_patterns: Feature name patterns to exclude from normalization
    """

    name = "RollingZScore"

    def __init__(
        self,
        window: int = 252,
        min_periods: int | None = None,
        exclude_patterns: list[str] | None = None,
    ) -> None:
        super().__init__()
        self.window = window
        self.min_periods = min_periods or window // 2
        self.exclude_patterns = exclude_patterns or [
            "_bnd_",  # Already bounded [0,1]
            "_rnk_",  # Already ranked [0,1]
            "Ratio",  # Already ratio-based
        ]
        self._cols_to_transform: list[str] = []
        self._cols_passthrough: list[str] = []

    def fit(
        self, X: pd.DataFrame, y: pd.Series | None = None
    ) -> "RollingZScoreOptimizer":
        """
        Identify which columns to transform.

        Args:
            X: Feature DataFrame
            y: Not used, kept for API consistency

        Returns:
            self
        """
        self._feature_names_in = list(X.columns)
        self._cols_to_transform = []
        self._cols_passthrough = []

        for col in X.columns:
            # Check if should be excluded
            exclude = any(pattern in col for pattern in self.exclude_patterns)
            if exclude:
                self._cols_passthrough.append(col)
            else:
                self._cols_to_transform.append(col)

        self._feature_names_out = list(X.columns)  # Same columns, transformed
        self.is_fitted = True
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """
        Apply rolling z-score normalization.

        Args:
            X: Feature DataFrame

        Returns:
            DataFrame with rolling z-score normalized features
        """
        if not self.is_fitted:
            raise RuntimeError("Must call fit() before transform()")

        result = X.copy()

        for col in self._cols_to_transform:
            if col in X.columns:
                series = X[col]
                rolling_mean = series.rolling(
                    window=self.window, min_periods=self.min_periods
                ).mean()
                rolling_std = series.rolling(
                    window=self.window, min_periods=self.min_periods
                ).std()

                # Avoid division by zero
                rolling_std = rolling_std.replace(0, np.nan)

                # Compute z-score
                result[col] = (series - rolling_mean) / rolling_std

                # Clip extreme z-scores (optional safety)
                result[col] = result[col].clip(-5, 5)

        return result

    def get_transform_info(self) -> dict:
        """Get information about which columns were transformed."""
        return {
            "transformed": self._cols_to_transform,
            "passthrough": self._cols_passthrough,
            "window": self.window,
        }
