"""
1-Minute Timeframe Optimizer for HTF CatBoost Backtest
======================================================

Thin 1m adapter built on top of the 5m optimizer implementation.
It reuses the same optimization/training flow and only customizes:
- timeframe id ("1m")
- default search spaces for denser 1m data
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
class Config1m(Config5m):
    """
    1m-specific configuration.

    1m has the highest row density, so we keep a slightly longer timeout.
    """

    optuna_trials: int = 35
    optuna_timeout: int = 240


@dataclass
class WindowSpace1m(WindowSpace5m):
    """
    1m window search space.

    With 1m labels limited to the first 4h of each batch, sample density is still
    much higher than 5m/15m. Use a moderate lookback range by default.
    """

    lookback_min: int = 100
    lookback_max: int = 350
    decay_min: float = 0.99
    decay_max: float = 0.99995
    min_samples_per_class: int = 150


@dataclass
class FeatureSpace1m(FeatureSpace5m):
    """
    1m feature search space.

    Slightly wider feature count with stricter correlation filtering.
    """

    feature_k_min: int = 40
    feature_k_max: int = 140
    corr_threshold_min: float = 0.80
    corr_threshold_max: float = 0.97
    var_threshold_min: float = 0.0003
    var_threshold_max: float = 0.01


@dataclass
class ModelSpace1m(ModelSpace5m):
    """
    1m model search space.

    1m is noisier, so defaults favor stronger regularization and fewer rounds.
    """

    learning_rate_min: float = 0.003
    learning_rate_max: float = 0.12
    num_leaves_min: int = 16
    num_leaves_max: int = 80
    max_depth_min: int = 3
    max_depth_max: int = 10
    min_child_samples_min: int = 30
    min_child_samples_max: int = 200
    reg_lambda_min: float = 1e-4
    reg_lambda_max: float = 80.0
    reg_alpha_min: float = 1e-4
    reg_alpha_max: float = 80.0
    subsample_min: float = 0.35
    subsample_max: float = 0.9
    colsample_bytree_min: float = 0.35
    colsample_bytree_max: float = 0.9
    feature_fraction_bynode_min: float = 0.35
    feature_fraction_bynode_max: float = 0.9
    num_boost_round_min: int = 80
    num_boost_round_max: int = 700


class StepOptimizer1m(StepOptimizer5m):
    """1m step optimizer (same logic as 5m, different timeframe id)."""

    TIMEFRAME = "1m"


class Optimizer1m(Optimizer5m):
    """1-minute timeframe optimizer."""

    TIMEFRAME = "1m"

    def __init__(
        self,
        config: Config1m | None = None,
        window_space: WindowSpace1m | None = None,
        feature_space: FeatureSpace1m | None = None,
        model_space: ModelSpace1m | None = None,
    ):
        self.config = config or Config1m()
        self.window_space = window_space or WindowSpace1m()
        self.feature_space = feature_space or FeatureSpace1m()
        self.model_space = model_space or ModelSpace1m()

    def create_step_optimizer(self) -> StepOptimizer1m:
        return StepOptimizer1m(
            config=self.config,
            window_space=self.window_space,
            feature_space=self.feature_space,
            model_space=self.model_space,
        )


def optimize_1m_step(train_end: int, n_trials: int = 35, timeout: int = 240) -> dict:
    """Quick function to optimize a single 1m step."""
    opt = Optimizer1m()
    return opt.optimize_step(train_end, n_trials, timeout)
