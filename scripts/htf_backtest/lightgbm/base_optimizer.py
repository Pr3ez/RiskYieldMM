"""
Base Optimizer — Compatibility Layer
=====================================

This module provides backwards-compatible imports.
All logic has been moved to:
- utils.py — Shared utilities (data loading, features, persistence)
- runner.py — Walk-forward backtest runner
- tf_1m/optimizer.py — 1m-specific optimization
- tf_5m/optimizer.py — 5m-specific optimization
- tf_15m/optimizer.py — 15m-specific optimization

Usage:
    # NEW way (preferred):
    from scripts.htf_backtest.lightgbm.tf_1m import Optimizer1m
    from scripts.htf_backtest.lightgbm.tf_5m import Optimizer5m
    from scripts.htf_backtest.lightgbm.tf_15m import Optimizer15m
    from scripts.htf_backtest.lightgbm.runner import run_walk_forward_backtest

    # OLD way (still works):
    from scripts.htf_backtest.lightgbm.base_optimizer import (
        StepOptimizer,  # Alias to StepOptimizer5m
        run_walk_forward_backtest,
    )
"""

# Re-export everything from utils for backwards compatibility
# Re-export runner
from .runner import run_walk_forward_backtest

# Re-export timeframe-specific optimizers
from .tf_1m import (
    Config1m,
    FeatureSpace1m,
    ModelSpace1m,
    Optimizer1m,
    StepOptimizer1m,
    WindowSpace1m,
)
from .tf_5m import (
    Config5m,
    FeatureSpace5m,
    ModelSpace5m,
    Optimizer5m,
    StepOptimizer5m,
    WindowSpace5m,
)
from .tf_15m import (
    Config15m,
    FeatureSpace15m,
    ModelSpace15m,
    Optimizer15m,
    StepOptimizer15m,
    WindowSpace15m,
)
from .utils import (
    BaseOptimizerConfig,
    FeatureSearchSpace,
    ModelSearchSpace,
    WindowSearchSpace,
    apply_sample_weights,
    compute_class_weights,
    drop_correlated_features,
    drop_low_variance_features,
    format_timestamp_for_folder,
    export_study_trials,
    get_batch_count,
    get_feature_columns,
    load_batch,
    load_batches_range,
    prepare_features_target,
    save_step_results,
    select_features_by_mi,
    weights_to_sample_weights,
)

# Backwards compatibility: alias 5m optimizer as default
StepOptimizer = StepOptimizer5m


def train_with_optimized_params(
    config, timeframe: str, train_end: int, opt_result: dict
):
    """
    Train model with optimized parameters.

    DEPRECATED: Use Optimizer5m.train_model() or Optimizer15m.train_model() instead.
    """
    if timeframe == "1m":
        optimizer = Optimizer1m(config=config)
    elif timeframe == "5m":
        optimizer = Optimizer5m(config=config)
    elif timeframe == "15m":
        optimizer = Optimizer15m(config=config)
    else:
        raise ValueError(f"Unknown timeframe: {timeframe}")

    return optimizer.train_model(train_end, opt_result)


__all__ = [
    # Base config classes
    "BaseOptimizerConfig",
    "WindowSearchSpace",
    "FeatureSearchSpace",
    "ModelSearchSpace",
    # 1m
    "Optimizer1m",
    "StepOptimizer1m",
    "Config1m",
    "WindowSpace1m",
    "FeatureSpace1m",
    "ModelSpace1m",
    # 5m
    "Optimizer5m",
    "StepOptimizer5m",
    "Config5m",
    "WindowSpace5m",
    "FeatureSpace5m",
    "ModelSpace5m",
    # 15m
    "Optimizer15m",
    "StepOptimizer15m",
    "Config15m",
    "WindowSpace15m",
    "FeatureSpace15m",
    "ModelSpace15m",
    # Backwards compat alias
    "StepOptimizer",
    # Utilities
    "load_batch",
    "load_batches_range",
    "get_batch_count",
    "get_feature_columns",
    "prepare_features_target",
    "apply_sample_weights",
    "select_features_by_mi",
    "drop_correlated_features",
    "drop_low_variance_features",
    "compute_class_weights",
    "weights_to_sample_weights",
    "save_step_results",
    "format_timestamp_for_folder",
    "export_study_trials",
    "train_with_optimized_params",
    # Runner
    "run_walk_forward_backtest",
]
