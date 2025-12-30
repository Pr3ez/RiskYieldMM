"""
Winsorization Optimizer (Causal)
================================

Handles outliers by clipping values to EXPANDING percentiles.
Uses only past data to compute bounds — no future leakage.

CAUSAL GUARANTEE:
    At row N, bounds are computed from rows 0..N-1 only.
    First `min_periods` rows use available data.

Research basis:
- Some features have 10-23% outliers (3×IQR method)
- Funding and mark price features most affected
- Winsorization improves model stability

Usage:
    optimizer = WinsorizeOptimizer(lower=0.01, upper=0.99)
    X_clipped = optimizer.fit_transform(X)
"""

import pandas as pd

from scripts.analysis.optimizers.base import BaseOptimizer


class WinsorizeOptimizer(BaseOptimizer):
    """
    Clip feature values to EXPANDING percentile bounds (causal).

    For each feature at each row:
        lower_bound = expanding_percentile(x[:t], lower * 100)
        upper_bound = expanding_percentile(x[:t], upper * 100)
        x_clipped[t] = clip(x[t], lower_bound, upper_bound)

    CAUSAL: Only uses data available up to current row.

    Args:
        lower: Lower percentile (e.g., 0.01 for 1st percentile)
        upper: Upper percentile (e.g., 0.99 for 99th percentile)
        min_periods: Minimum observations before computing bounds (default 252)
        exclude_patterns: Feature patterns to exclude from winsorization
    """

    name = "Winsorize"

    def __init__(
        self,
        lower: float = 0.01,
        upper: float = 0.99,
        min_periods: int = 252,
        exclude_patterns: list[str] | None = None,
    ) -> None:
        super().__init__()
        self.lower = lower
        self.upper = upper
        self.min_periods = min_periods
        self.exclude_patterns = exclude_patterns or [
            "_bnd_",  # Already bounded [0,1]
            "_rnk_",  # Already ranked [0,1]
        ]

        self._cols_to_clip: list[str] = []

    def fit(self, X: pd.DataFrame, y: pd.Series | None = None) -> "WinsorizeOptimizer":
        """
        Identify which columns to clip (no bounds stored — computed causally).

        Args:
            X: Feature DataFrame
            y: Not used

        Returns:
            self
        """
        self._feature_names_in = list(X.columns)
        self._cols_to_clip = []

        for col in X.columns:
            # Check exclusion
            exclude = any(pattern in col for pattern in self.exclude_patterns)
            if exclude:
                continue

            # Only include columns with enough non-null values
            if X[col].notna().sum() > self.min_periods:
                self._cols_to_clip.append(col)

        self._feature_names_out = list(X.columns)
        self.is_fitted = True
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """
        Apply CAUSAL winsorization using expanding percentiles.

        At each row, bounds are computed from all previous rows only.

        Args:
            X: Feature DataFrame

        Returns:
            Clipped DataFrame
        """
        if not self.is_fitted:
            raise RuntimeError("Must call fit() before transform()")

        result = X.copy()

        for col in self._cols_to_clip:
            if col not in result.columns:
                continue

            series = X[col]

            # Compute expanding bounds (shifted to avoid using current row)
            expanding_lower = (
                series.expanding(min_periods=self.min_periods)
                .quantile(self.lower)
                .shift(1)  # Use only past data
            )
            expanding_upper = (
                series.expanding(min_periods=self.min_periods)
                .quantile(self.upper)
                .shift(1)  # Use only past data
            )

            # Clip using expanding bounds
            result[col] = series.clip(lower=expanding_lower, upper=expanding_upper)

        return result

    def get_winsorize_info(self) -> pd.DataFrame:
        """Get summary of columns being winsorized.

        NOTE: In causal mode, bounds are computed per-row using expanding
        quantiles, not stored globally. This method returns column info only.
        """
        rows = []
        for col in self._cols_to_clip:
            rows.append(
                {
                    "feature": col,
                    "lower_percentile": self.lower,
                    "upper_percentile": self.upper,
                    "min_periods": self.min_periods,
                }
            )
        return pd.DataFrame(rows)
