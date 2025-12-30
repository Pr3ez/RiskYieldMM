"""
Feature Optimization Modules (Causal)
=====================================

Each optimizer implements a specific signal quality improvement strategy.
All optimizers follow the same interface for easy composition and benchmarking.

CAUSAL GUARANTEE:
    All optimizers use only past data for computations.
    No future leakage — safe for time-series modeling.

Available Optimizers:
    - RollingZScoreOptimizer: Fix distribution drift with rolling normalization
    - RegimeConditioningOptimizer: Weight features by market regime (trending/reverting)
    - InteractionOptimizer: Add cross-domain interaction features (expanding standardization)
    - WinsorizeOptimizer: Handle outliers via expanding percentile clipping

REMOVED (Future Leakage):
    - DomainPCAOptimizer: PCA requires full covariance matrix — cannot be causal

Usage:
    from scripts.analysis.optimizers import OptimizationPipeline, RollingZScoreOptimizer

    pipeline = OptimizationPipeline([
        RollingZScoreOptimizer(window=252),
        WinsorizeOptimizer(lower=0.01, upper=0.99),
    ])
    X_optimized = pipeline.fit_transform(X, y)
    metrics = pipeline.get_metrics()
"""

from scripts.analysis.optimizers.base import BaseOptimizer, OptimizerMetrics
from scripts.analysis.optimizers.expanding_rank import ExpandingRankOptimizer
from scripts.analysis.optimizers.expanding_zscore import ExpandingZScoreOptimizer
from scripts.analysis.optimizers.interactions import InteractionOptimizer
from scripts.analysis.optimizers.log_transform import LogTransformOptimizer
from scripts.analysis.optimizers.pipeline import OptimizationPipeline
from scripts.analysis.optimizers.regime_conditioning import RegimeConditioningOptimizer
from scripts.analysis.optimizers.rolling_zscore import RollingZScoreOptimizer
from scripts.analysis.optimizers.winsorize import WinsorizeOptimizer

# NOTE: DomainPCAOptimizer removed — PCA cannot be made causal (needs full covariance matrix)

__all__ = [
    "BaseOptimizer",
    "OptimizerMetrics",
    "ExpandingRankOptimizer",
    "ExpandingZScoreOptimizer",
    "InteractionOptimizer",
    "LogTransformOptimizer",
    "RollingZScoreOptimizer",
    "RegimeConditioningOptimizer",
    "WinsorizeOptimizer",
    "OptimizationPipeline",
]
