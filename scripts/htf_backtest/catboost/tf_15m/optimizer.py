"""
15-Minute Timeframe Optimizer for HTF CatBoost Backtest
=======================================================

Thin 15m adapter built on top of the 5m CatBoost optimizer implementation.
It reuses the same optimization/training flow and customizes:
- timeframe id ("15m")
- default search spaces for cleaner 15m data
"""

from dataclasses import dataclass

from ..tf_5m.optimizer import (
    Config5m,
    FeatureSpace5m,
    ModelSpace5m,
    Optimizer5m,
    StepOptimizer5m,
    WindowSpace5m,
)


@dataclass
class Config15m(Config5m):
    """15m-specific optimizer runtime defaults."""

    optuna_trials: int = 20
    optuna_timeout: int = 120


@dataclass
class WindowSpace15m(WindowSpace5m):
    """15m window defaults (fewer rows per batch than 5m)."""

    lookback_min: int = 150
    lookback_max: int = 500
    decay_min: float = 0.95
    decay_max: float = 0.999
    min_samples_per_class: int = 50


@dataclass
class FeatureSpace15m(FeatureSpace5m):
    """15m feature-selection defaults."""

    feature_k_min: int = 20
    feature_k_max: int = 100
    corr_threshold_min: float = 0.7
    corr_threshold_max: float = 0.95
    var_threshold_min: float = 0.001
    var_threshold_max: float = 0.01


@dataclass
class ModelSpace15m(ModelSpace5m):
    """15m model-search defaults."""

    learning_rate_min: float = 0.01
    learning_rate_max: float = 0.2
    num_leaves_min: int = 16
    num_leaves_max: int = 128
    max_depth_min: int = 4
    max_depth_max: int = 12
    min_child_samples_min: int = 10
    min_child_samples_max: int = 100
    reg_lambda_min: float = 1e-6
    reg_lambda_max: float = 10.0
    reg_alpha_min: float = 1e-6
    reg_alpha_max: float = 10.0
    subsample_min: float = 0.5
    subsample_max: float = 1.0
    colsample_bytree_min: float = 0.5
    colsample_bytree_max: float = 1.0
    feature_fraction_bynode_min: float = 0.5
    feature_fraction_bynode_max: float = 1.0
    num_boost_round_min: int = 100
    num_boost_round_max: int = 1000


class StepOptimizer15m(StepOptimizer5m):
    """15m step optimizer (same logic as 5m, different timeframe id)."""

    TIMEFRAME = "15m"


class Optimizer15m(Optimizer5m):
    """15-minute timeframe optimizer."""

    TIMEFRAME = "15m"

    def __init__(
        self,
        config: Config15m | None = None,
        window_space: WindowSpace15m | None = None,
        feature_space: FeatureSpace15m | None = None,
        model_space: ModelSpace15m | None = None,
    ):
        self.config = config or Config15m()
        self.window_space = window_space or WindowSpace15m()
        self.feature_space = feature_space or FeatureSpace15m()
        self.model_space = model_space or ModelSpace15m()

    def create_step_optimizer(self) -> StepOptimizer15m:
        return StepOptimizer15m(
            config=self.config,
            window_space=self.window_space,
            feature_space=self.feature_space,
            model_space=self.model_space,
        )


def optimize_15m_step(train_end: int, n_trials: int = 20, timeout: int = 120) -> dict:
    """Quick function to optimize a single 15m step."""
    opt = Optimizer15m()
    return opt.optimize_step(train_end, n_trials, timeout)
