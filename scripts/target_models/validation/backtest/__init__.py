"""
Backtest Package - Modular ML Backtest System

This package provides a modular architecture for ML-based backtesting:

Subpackages:
    domain/   - Core config and business entities
    core/     - Pure functions (ensemble, metrics, features)
    models/   - Per-model implementations (CatBoost, LightGBM, LSTM, Linear)
    adapters/ - Data loading and output
    services/ - Orchestration (training, backtest)

Usage:
    from backtest import run_sync_backtest, SyncBacktestConfig
    from backtest import CatBoostModelConfig, tune_catboost_classifier
"""

__version__ = "2.0.0"

# Domain layer
# Core utilities
from .core import (
    ModelConfig,
    apply_feature_selection,
    extract_per_model_splits,
)
from .domain.config import PerModelConfig, SyncBacktestConfig

# Model configs (from models layer)
# Tuning functions (from models layer)
from .models import (
    CatBoostModelConfig,
    LightGBMModelConfig,
    LinearModelConfig,
    LSTMModelConfig,
    tune_catboost_classifier,
    tune_catboost_regressor,
    tune_lightgbm_classifier,
    tune_lightgbm_regressor,
    tune_linear_classifier,
    tune_linear_regressor,
    tune_lstm_classifier,
    tune_lstm_regressor,
)

# Legacy exports
from .models.lstm_model import LSTMClassifier, LSTMRegressor

# Services layer
from .services.backtest import run_sync_backtest
from .services.training import (
    train_predict_classification_permodel,
    train_predict_regression_permodel,
)

# Backward compatibility aliases
tune_cb_classifier = tune_catboost_classifier
tune_cb_regressor = tune_catboost_regressor
tune_lgb_classifier = tune_lightgbm_classifier
tune_lgb_regressor = tune_lightgbm_regressor

__all__ = [
    # Version
    "__version__",
    # Config
    "SyncBacktestConfig",
    "PerModelConfig",
    # Entry point
    "run_sync_backtest",
    # Training
    "train_predict_classification_permodel",
    "train_predict_regression_permodel",
    # Model configs
    "CatBoostModelConfig",
    "LightGBMModelConfig",
    "LSTMModelConfig",
    "LinearModelConfig",
    # Tuning
    "tune_catboost_classifier",
    "tune_catboost_regressor",
    "tune_lightgbm_classifier",
    "tune_lightgbm_regressor",
    "tune_lstm_classifier",
    "tune_lstm_regressor",
    "tune_linear_classifier",
    "tune_linear_regressor",
    # Aliases
    "tune_cb_classifier",
    "tune_cb_regressor",
    "tune_lgb_classifier",
    "tune_lgb_regressor",
    # Core
    "ModelConfig",
    "apply_feature_selection",
    "extract_per_model_splits",
    # Legacy
    "LSTMClassifier",
    "LSTMRegressor",
]
