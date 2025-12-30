"""
Optimization Pipeline
=====================

Chains multiple optimizers together and tracks metrics for each.
Allows comparing individual and combined optimizer performance.

Usage:
    from scripts.analysis.optimizers import (
        OptimizationPipeline,
        RollingZScoreOptimizer,
        WinsorizeOptimizer,
        RegimeConditioningOptimizer,
    )

    pipeline = OptimizationPipeline([
        WinsorizeOptimizer(lower=0.01, upper=0.99),
        RollingZScoreOptimizer(window=252),
        RegimeConditioningOptimizer(),
    ])

    # Fit and transform
    X_optimized = pipeline.fit_transform(X, y)

    # Get metrics for each optimizer
    metrics_df = pipeline.get_metrics_df()

    # Compare before/after
    comparison = pipeline.compare_performance(X, y)
"""

from typing import Any

import pandas as pd

from scripts.analysis.optimizers.base import BaseOptimizer, OptimizerMetrics


class OptimizationPipeline:
    """
    Chain multiple optimizers and track their individual/combined performance.

    The pipeline:
        1. Applies optimizers in sequence
        2. Tracks metrics after each step
        3. Allows comparison of individual vs combined improvements

    Args:
        optimizers: List of BaseOptimizer instances
        name: Name for the pipeline
    """

    def __init__(
        self,
        optimizers: list[BaseOptimizer],
        name: str = "OptimizationPipeline",
    ) -> None:
        self.optimizers = optimizers
        self.name = name
        self.is_fitted = False

        # Tracking
        self._step_metrics: list[OptimizerMetrics] = []
        self._baseline_ic: float = 0.0
        self._final_ic: float = 0.0

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "OptimizationPipeline":
        """
        Fit all optimizers in sequence.

        Args:
            X: Feature DataFrame
            y: Target series

        Returns:
            self
        """
        self._step_metrics = []
        X_current = X.copy()

        # Compute baseline IC
        self._baseline_ic = self._compute_mean_ic(X, y)

        for optimizer in self.optimizers:
            # Evaluate and fit
            metrics = optimizer.evaluate(X_current, y)
            self._step_metrics.append(metrics)

            # Transform for next step
            X_current = optimizer.transform(X_current)

        # Final IC
        self._final_ic = self._compute_mean_ic(X_current, y)

        self.is_fitted = True
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """
        Apply all optimizers in sequence.

        Args:
            X: Feature DataFrame

        Returns:
            Transformed DataFrame
        """
        if not self.is_fitted:
            raise RuntimeError("Must call fit() before transform()")

        X_current = X.copy()
        for optimizer in self.optimizers:
            X_current = optimizer.transform(X_current)
        return X_current

    def fit_transform(self, X: pd.DataFrame, y: pd.Series) -> pd.DataFrame:
        """Fit and transform in one step."""
        return self.fit(X, y).transform(X)

    def _compute_mean_ic(self, X: pd.DataFrame, y: pd.Series) -> float:
        """Compute mean absolute IC across features."""
        import numpy as np
        from scipy import stats

        ics = []
        y_vals = y.values
        for col in X.columns:
            x_vals = X[col].values
            mask = ~np.isnan(x_vals) & ~np.isnan(y_vals)
            if mask.sum() > 100:
                ic, _ = stats.spearmanr(x_vals[mask], y_vals[mask])
                if not np.isnan(ic):
                    ics.append(abs(ic))
        return float(np.mean(ics)) if ics else 0.0

    def get_metrics(self) -> list[OptimizerMetrics]:
        """Get metrics for each optimizer step."""
        return self._step_metrics

    def get_metrics_df(self) -> pd.DataFrame:
        """Get metrics as DataFrame for easy comparison."""
        rows = []
        for i, metrics in enumerate(self._step_metrics):
            row = metrics.to_dict()
            row["step"] = i + 1
            rows.append(row)

        # Add pipeline summary
        if rows:
            rows.append(
                {
                    "name": f"{self.name}_TOTAL",
                    "step": len(rows) + 1,
                    "ic_before": self._baseline_ic,
                    "ic_after": self._final_ic,
                    "ic_improvement": (self._final_ic - self._baseline_ic)
                    / (abs(self._baseline_ic) + 1e-10),
                    "n_features_in": rows[0].get("n_features_in", 0),
                    "n_features_out": rows[-1].get("n_features_out", 0),
                }
            )

        return pd.DataFrame(rows)

    def compare_performance(self, X: pd.DataFrame, y: pd.Series) -> dict[str, Any]:
        """
        Compare baseline vs optimized performance.

        Args:
            X: Original feature DataFrame
            y: Target series

        Returns:
            Dictionary with comparison metrics
        """
        if not self.is_fitted:
            raise RuntimeError("Must call fit() before compare_performance()")

        X_optimized = self.transform(X)

        return {
            "baseline_ic": self._baseline_ic,
            "optimized_ic": self._final_ic,
            "ic_improvement": self._final_ic - self._baseline_ic,
            "ic_improvement_pct": (self._final_ic - self._baseline_ic)
            / (abs(self._baseline_ic) + 1e-10)
            * 100,
            "n_features_original": X.shape[1],
            "n_features_optimized": X_optimized.shape[1],
            "n_optimizers": len(self.optimizers),
            "optimizer_names": [opt.name for opt in self.optimizers],
        }

    def print_report(self) -> None:
        """Print a formatted report of optimization results."""
        print("=" * 70)
        print(f"OPTIMIZATION PIPELINE: {self.name}")
        print("=" * 70)

        print(f"\nBaseline mean |IC|: {self._baseline_ic:.4f}")
        print(f"Final mean |IC|:    {self._final_ic:.4f}")
        improvement = (self._final_ic - self._baseline_ic) / (
            abs(self._baseline_ic) + 1e-10
        )
        print(f"Improvement:        {improvement:+.1%}")

        print("\n--- Step-by-Step Metrics ---")
        print(
            f"{'Step':<5} {'Optimizer':<25} {'IC Before':>10} {'IC After':>10} "
            f"{'Δ IC':>10} {'Features':>12}"
        )
        print("-" * 80)

        for i, metrics in enumerate(self._step_metrics, 1):
            delta = metrics.ic_after - metrics.ic_before
            feat_change = f"{metrics.n_features_in}→{metrics.n_features_out}"
            print(
                f"{i:<5} {metrics.name:<25} {metrics.ic_before:>10.4f} "
                f"{metrics.ic_after:>10.4f} {delta:>+10.4f} {feat_change:>12}"
            )

        print("=" * 70)

    def __repr__(self) -> str:
        opt_names = [o.name for o in self.optimizers]
        status = "fitted" if self.is_fitted else "not fitted"
        return f"OptimizationPipeline({opt_names}, {status})"
