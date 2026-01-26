"""
Synchronized L2 Backtest Module (FACADE)

This is a thin facade that re-exports from the backtest/ package.
All actual implementation lives in backtest/ submodules.

Usage:
    from scripts.target_models.validation.l2_backtest_sync import (
        SyncBacktestConfig,
        run_sync_backtest,
        ALL_CONFIGS,
    )

    # Run synchronized backtest
    results = run_sync_backtest(configs=ALL_CONFIGS, verbose=True)

Architecture:
    backtest/
    ├── domain/config.py        # SyncBacktestConfig, PerModelConfig
    ├── core/base.py            # ModelConfig ABC, ModelResult
    ├── core/features.py        # apply_feature_selection, extract_per_model_splits
    ├── core/ensemble.py        # AdaptiveWeightTracker, sample weights
    ├── core/metrics.py         # build_step_metrics, compute_config_metrics
    ├── models/catboost_model.py # CatBoost pipeline + tuning
    ├── models/lightgbm_model.py # LightGBM pipeline + tuning
    ├── models/lstm_model.py    # LSTM pipeline + tuning (enhanced)
    ├── models/linear_model.py  # Linear pipeline + tuning
    ├── models/lstm.py          # LSTMClassifier, LSTMRegressor (legacy)
    ├── adapters/data_loader.py # ConfigData, load_config_data
    ├── adapters/output.py      # DualOutput
    ├── services/training.py    # Orchestration using model modules
    └── services/backtest.py    # run_sync_backtest (main orchestrator)
"""

from __future__ import annotations

# Adapters layer - I/O
from backtest.adapters.data_loader import (
    ConfigData,
    clip_features,
    get_embargo_for_horizon,
    load_config_data,
    load_timestamps_for_config,
    parse_config,
)
from backtest.adapters.output import DualOutput

# Core layer - Business logic
from backtest.core.ensemble import (
    AdaptiveWeightTracker,
    compute_ensemble_prediction,
    compute_sample_weights,
    update_adaptive_weights,
)
from backtest.core.features import apply_feature_selection, extract_per_model_splits
from backtest.core.metrics import build_step_metrics, compute_config_metrics

# Domain layer - Configuration
from backtest.domain.config import (
    PerModelConfig,
    SyncBacktestConfig,
)

# New model modules (per-model architecture)
from backtest.models.catboost_model import (
    CatBoostModelConfig,
    tune_catboost_classifier,
    tune_catboost_regressor,
)
from backtest.models.catboost_model import (
    train_and_predict_classifier as cb_train_predict,
)
from backtest.models.lightgbm_model import (
    LightGBMModelConfig,
    tune_lightgbm_classifier,
    tune_lightgbm_regressor,
)
from backtest.models.lightgbm_model import (
    train_and_predict_classifier as lgb_train_predict,
)
from backtest.models.linear_model import (
    LinearModelConfig,
    tune_linear_classifier,
    tune_linear_regressor,
)
from backtest.models.linear_model import (
    train_and_predict_classifier as linear_train_predict,
)

# Models layer - LSTM (all imports from lstm_model.py)
from backtest.models.lstm_model import (
    LSTMClassifier,
    LSTMModelConfig,
    LSTMRegressor,
    create_sequences,
    train_lstm_classifier,
    train_lstm_regressor,
    tune_lstm_classifier,
    tune_lstm_regressor,
)
from backtest.models.lstm_model import (
    train_and_predict_classifier as lstm_train_predict,
)
from backtest.services.backtest import (
    ALL_CONFIGS,
    LABEL_NAMES,
    get_label_name,
    run_sync_backtest,
)
from backtest.services.training import (
    train_predict_classification_permodel,
    train_predict_regression_permodel,
)

# Backward compatibility aliases for old tuning function names
tune_cb_classifier = tune_catboost_classifier
tune_cb_regressor = tune_catboost_regressor
tune_lgb_classifier = tune_lightgbm_classifier
tune_lgb_regressor = tune_lightgbm_regressor

# Workflow config (Single Source of Truth for config lists)
from scripts.workflow.config import (
    get_all_configs,
    get_configs_1bar,
    get_configs_reduced,
)

# Convenience re-exports
REDUCED_CONFIGS = get_configs_reduced()

__all__ = [
    # Main entry point
    "run_sync_backtest",
    # Configuration
    "SyncBacktestConfig",
    "PerModelConfig",
    # New model configs
    "CatBoostModelConfig",
    "LightGBMModelConfig",
    "LSTMModelConfig",
    "LinearModelConfig",
    # Config lists
    "ALL_CONFIGS",
    "REDUCED_CONFIGS",
    "get_all_configs",
    "get_configs_1bar",
    "get_configs_reduced",
    # Ensemble
    "AdaptiveWeightTracker",
    "compute_sample_weights",
    "update_adaptive_weights",
    "compute_ensemble_prediction",
    # Metrics
    "build_step_metrics",
    "compute_config_metrics",
    # LSTM models
    "LSTMClassifier",
    "LSTMRegressor",
    "create_sequences",
    "train_lstm_classifier",
    "train_lstm_regressor",
    # Data loading
    "ConfigData",
    "load_config_data",
    "parse_config",
    "clip_features",
    "get_embargo_for_horizon",
    "load_timestamps_for_config",
    # Output
    "DualOutput",
    "LABEL_NAMES",
    "get_label_name",
    # Tuning (backward compat + new names)
    "tune_cb_classifier",
    "tune_cb_regressor",
    "tune_lgb_classifier",
    "tune_lgb_regressor",
    "tune_catboost_classifier",
    "tune_catboost_regressor",
    "tune_lightgbm_classifier",
    "tune_lightgbm_regressor",
    "tune_lstm_classifier",
    "tune_lstm_regressor",
    "tune_linear_classifier",
    "tune_linear_regressor",
    # Training
    "apply_feature_selection",
    "extract_per_model_splits",
    "train_predict_classification_permodel",
    "train_predict_regression_permodel",
    # New model train functions
    "cb_train_predict",
    "lgb_train_predict",
    "lstm_train_predict",
    "linear_train_predict",
]
