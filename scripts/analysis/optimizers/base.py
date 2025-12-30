"""
Base Optimizer Class
====================

Abstract base class defining the optimizer interface.
All optimizers must implement fit(), transform(), and evaluate().
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats


@dataclass
class OptimizerMetrics:
    """Metrics to track optimizer performance."""

    name: str
    # Before/after comparison
    ic_before: float = 0.0
    ic_after: float = 0.0
    ic_improvement: float = 0.0
    # Feature stats
    n_features_in: int = 0
    n_features_out: int = 0
    # Data quality
    nan_pct_before: float = 0.0
    nan_pct_after: float = 0.0
    outlier_pct_before: float = 0.0
    outlier_pct_after: float = 0.0
    # Timing
    fit_time_ms: float = 0.0
    transform_time_ms: float = 0.0
    # Extra info
    extra: dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        return (
            f"OptimizerMetrics({self.name}: "
            f"IC {self.ic_before:.4f}→{self.ic_after:.4f} "
            f"({self.ic_improvement:+.1%}), "
            f"features {self.n_features_in}→{self.n_features_out})"
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "ic_before": self.ic_before,
            "ic_after": self.ic_after,
            "ic_improvement": self.ic_improvement,
            "n_features_in": self.n_features_in,
            "n_features_out": self.n_features_out,
            "nan_pct_before": self.nan_pct_before,
            "nan_pct_after": self.nan_pct_after,
            "outlier_pct_before": self.outlier_pct_before,
            "outlier_pct_after": self.outlier_pct_after,
            "fit_time_ms": self.fit_time_ms,
            "transform_time_ms": self.transform_time_ms,
            **self.extra,
        }


class BaseOptimizer(ABC):
    """
    Abstract base class for feature optimizers.

    All optimizers follow the sklearn-like fit/transform pattern:
        1. fit(X, y) - Learn parameters from training data
        2. transform(X) - Apply transformation to features
        3. fit_transform(X, y) - Convenience method for both
        4. evaluate(X, y) - Compute metrics before/after transformation

    Attributes:
        name: Human-readable name for the optimizer
        is_fitted: Whether fit() has been called
        metrics_: OptimizerMetrics populated after evaluate()
    """

    name: str = "BaseOptimizer"

    def __init__(self) -> None:
        self.is_fitted = False
        self.metrics_: OptimizerMetrics | None = None
        self._feature_names_in: list[str] = []
        self._feature_names_out: list[str] = []

    @abstractmethod
    def fit(self, X: pd.DataFrame, y: pd.Series | None = None) -> "BaseOptimizer":
        """
        Fit the optimizer to the training data.

        Args:
            X: Feature DataFrame (rows=samples, columns=features)
            y: Target series (optional, some optimizers need it)

        Returns:
            self for method chaining
        """
        pass

    @abstractmethod
    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """
        Transform features using fitted parameters.

        Args:
            X: Feature DataFrame to transform

        Returns:
            Transformed DataFrame (may have different columns)
        """
        pass

    def fit_transform(
        self, X: pd.DataFrame, y: pd.Series | None = None
    ) -> pd.DataFrame:
        """Fit and transform in one step."""
        return self.fit(X, y).transform(X)

    def evaluate(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        target_col: str = "y_forward_return_1",
    ) -> OptimizerMetrics:
        """
        Evaluate optimizer performance with before/after metrics.

        Args:
            X: Feature DataFrame
            y: Target series for IC calculation
            target_col: Name of target for logging

        Returns:
            OptimizerMetrics with comparison stats
        """
        import time

        # Before metrics
        ic_before = self._compute_mean_ic(X, y)
        nan_before = X.isna().mean().mean()
        outlier_before = self._compute_outlier_pct(X)

        # Fit
        t0 = time.perf_counter()
        self.fit(X, y)
        fit_time = (time.perf_counter() - t0) * 1000

        # Transform
        t0 = time.perf_counter()
        X_transformed = self.transform(X)
        transform_time = (time.perf_counter() - t0) * 1000

        # After metrics
        ic_after = self._compute_mean_ic(X_transformed, y)
        nan_after = X_transformed.isna().mean().mean()
        outlier_after = self._compute_outlier_pct(X_transformed)

        # Compute improvement
        ic_improvement = (ic_after - ic_before) / (abs(ic_before) + 1e-10)

        self.metrics_ = OptimizerMetrics(
            name=self.name,
            ic_before=ic_before,
            ic_after=ic_after,
            ic_improvement=ic_improvement,
            n_features_in=X.shape[1],
            n_features_out=X_transformed.shape[1],
            nan_pct_before=nan_before,
            nan_pct_after=nan_after,
            outlier_pct_before=outlier_before,
            outlier_pct_after=outlier_after,
            fit_time_ms=fit_time,
            transform_time_ms=transform_time,
        )

        return self.metrics_

    def _compute_mean_ic(self, X: pd.DataFrame, y: pd.Series) -> float:
        """Compute mean absolute IC across all features."""
        ics = []
        y_vals = y.values
        for col in X.columns:
            x_vals = X[col].values
            mask = ~np.isnan(x_vals) & ~np.isnan(y_vals)
            if mask.sum() > 100:
                ic, _ = stats.spearmanr(x_vals[mask], y_vals[mask])
                if not np.isnan(ic):
                    ics.append(abs(ic))
        return np.mean(ics) if ics else 0.0

    def _compute_outlier_pct(self, X: pd.DataFrame, iqr_factor: float = 3.0) -> float:
        """Compute percentage of outliers using IQR method."""
        outlier_counts = []
        for col in X.columns:
            x = X[col].dropna()
            if len(x) > 100:
                q1, q3 = x.quantile(0.25), x.quantile(0.75)
                iqr = q3 - q1
                lower, upper = q1 - iqr_factor * iqr, q3 + iqr_factor * iqr
                n_outliers = ((x < lower) | (x > upper)).sum()
                outlier_counts.append(n_outliers / len(x))
        return np.mean(outlier_counts) if outlier_counts else 0.0

    @property
    def feature_names_in_(self) -> list[str]:
        """Input feature names (set after fit)."""
        return self._feature_names_in

    @property
    def feature_names_out_(self) -> list[str]:
        """Output feature names (set after fit)."""
        return self._feature_names_out

    def __repr__(self) -> str:
        status = "fitted" if self.is_fitted else "not fitted"
        return f"{self.__class__.__name__}({status})"
