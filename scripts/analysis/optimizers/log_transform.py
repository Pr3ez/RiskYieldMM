"""
Log Transform Optimizer (Stateless)
===================================

Applies signed log transform to right-skewed features (volatility, volume).
Formula: sign(x) * log(1 + |x|)

STATELESS: No fitting required — same transform applied everywhere.

Research basis:
- Volatility features are right-skewed (heavy positive tail)
- Log transform makes distribution more Gaussian
- Signed log preserves direction for features that can be negative

Usage:
    optimizer = LogTransformOptimizer()
    X_transformed = optimizer.fit_transform(X)
"""

import numpy as np
import pandas as pd

from scripts.analysis.optimizers.base import BaseOptimizer


class LogTransformOptimizer(BaseOptimizer):
    """
    Apply signed log transform: sign(x) * log(1 + |x|).

    STATELESS: No parameters learned, same transform always applied.

    Args:
        include_patterns: Feature patterns to include (default: volatility features)
        exclude_patterns: Feature patterns to exclude
    """

    name = "LogTransform"

    def __init__(
        self,
        include_patterns: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
    ) -> None:
        super().__init__()
        # Default: apply to volatility-like features
        self.include_patterns = include_patterns or [
            "V_",  # Volatility domain
            "_vol",  # Volume features
            "_atr",  # ATR features
            "_std",  # Standard deviation
        ]
        self.exclude_patterns = exclude_patterns or [
            "_bnd_",  # Already bounded [0,1]
            "_rnk_",  # Already ranked [0,1]
            "_bin",  # Binary features
        ]
        self._cols_to_transform: list[str] = []

    def fit(
        self, X: pd.DataFrame, y: pd.Series | None = None
    ) -> "LogTransformOptimizer":
        """
        Identify which columns to transform (stateless — no parameters stored).

        Args:
            X: Feature DataFrame
            y: Not used

        Returns:
            self
        """
        self._feature_names_in = list(X.columns)
        self._cols_to_transform = []

        for col in X.columns:
            # Check exclusion first
            if any(pattern in col for pattern in self.exclude_patterns):
                continue

            # Check inclusion
            if any(pattern in col.lower() for pattern in self.include_patterns):
                self._cols_to_transform.append(col)

        self._feature_names_out = list(X.columns)
        self.is_fitted = True
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """
        Apply signed log transform.

        Formula: sign(x) * log(1 + |x|)

        Args:
            X: Feature DataFrame

        Returns:
            Transformed DataFrame
        """
        if not self.is_fitted:
            raise RuntimeError("Must call fit() before transform()")

        result = X.copy()

        for col in self._cols_to_transform:
            if col not in result.columns:
                continue

            series = X[col]
            # Signed log: preserves direction, compresses magnitude
            result[col] = np.sign(series) * np.log1p(np.abs(series))

        return result

    def get_transform_info(self) -> pd.DataFrame:
        """Get summary of columns being transformed."""
        rows = []
        for col in self._cols_to_transform:
            rows.append({"feature": col, "transform": "signed_log"})
        return pd.DataFrame(rows)
