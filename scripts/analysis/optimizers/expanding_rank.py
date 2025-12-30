"""
Expanding Rank Transformer (Causal)
===================================

Transforms features to percentile ranks using EXPANDING CDF estimation.
Output is [0, 1] representing the feature's percentile in historical distribution.

CAUSAL GUARANTEE:
    At row N, rank is computed from rows 0..N-1 only.
    First `min_periods` rows use available data.

Research basis:
- Classification models benefit from monotonic transformations
- Ranks eliminate scale differences between features
- Tree-based models (CatBoost, LightGBM) work well with rank-transformed inputs
- Expanding (not rolling) preserves comparability across time

Usage:
    optimizer = ExpandingRankOptimizer(min_periods=252)
    X_ranked = optimizer.fit_transform(X)
"""

import numpy as np
import pandas as pd

from scripts.analysis.optimizers.base import BaseOptimizer


class ExpandingRankOptimizer(BaseOptimizer):
    """
    Transform features to percentile ranks using EXPANDING distribution.

    For each feature at each row:
        rank_t = percentile_rank(x_t, x[:t-1])

    Output is [0, 1] where 0.5 means the value is at the median of historical values.

    CAUSAL: Only uses data available up to current row.

    Args:
        min_periods: Minimum observations before computing ranks (default 252)
        exclude_patterns: Feature patterns to exclude from ranking
    """

    name = "ExpandingRank"

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
            "_state",  # Discrete state features
            "_regime",  # Regime features (categorical)
        ]
        self._cols_to_rank: list[str] = []

    def fit(
        self, X: pd.DataFrame, y: pd.Series | None = None
    ) -> "ExpandingRankOptimizer":
        """
        Identify which columns to rank.

        Args:
            X: Feature DataFrame
            y: Not used

        Returns:
            self
        """
        self._feature_names_in = list(X.columns)
        self._cols_to_rank = []

        for col in X.columns:
            # Check exclusion
            if any(pattern in col for pattern in self.exclude_patterns):
                continue

            # Only include columns with enough non-null values
            if X[col].notna().sum() > self.min_periods:
                self._cols_to_rank.append(col)

        self._feature_names_out = list(X.columns)
        self.is_fitted = True
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """
        Apply CAUSAL expanding rank transformation.

        At each row, rank is computed relative to all previous values.

        Args:
            X: Feature DataFrame

        Returns:
            Ranked DataFrame with values in [0, 1]
        """
        if not self.is_fitted:
            raise RuntimeError("Must call fit() before transform()")

        result = X.copy()

        for col in self._cols_to_rank:
            if col not in result.columns:
                continue

            series = X[col].values
            n = len(series)
            ranks = np.full(n, np.nan)

            # For each row, compute percentile rank using only past data
            for i in range(self.min_periods, n):
                current_val = series[i]
                if np.isnan(current_val):
                    continue

                # Historical values (excluding current)
                historical = series[:i]
                historical = historical[~np.isnan(historical)]

                if len(historical) < self.min_periods:
                    continue

                # Compute percentile rank
                # (count of values <= current) / (total count)
                ranks[i] = np.mean(historical <= current_val)

            result[col] = ranks

        return result

    def get_rank_info(self) -> pd.DataFrame:
        """Get summary of columns being ranked."""
        rows = []
        for col in self._cols_to_rank:
            rows.append(
                {
                    "feature": col,
                    "method": "expanding_rank",
                    "min_periods": self.min_periods,
                }
            )
        return pd.DataFrame(rows)
