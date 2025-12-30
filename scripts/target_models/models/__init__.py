"""
Layer 2 Supervised Models for Dual-Layer Walk-Forward.

Supervised models that use helper-enriched features to make predictions.
Each model is trained per target-horizon with appropriate task type handling.

Models:
    - CatBoost: Gradient boosting with native categorical support
    - LightGBM: Fast gradient boosting, good for ensembling
    - Ridge/LogisticRegression: Linear baseline for interpretability

Architecture:
    Layer 1 (helpers)         Layer 2 (supervised)
    ─────────────────         ────────────────────
    [train][cal][val]──gap──>[train][cal][val][pred]
                                ↑        ↑       ↑
                             fit here  tune   predict

Usage:
    from scripts.target_models.models import (
        create_model_ensemble,
        ModelEnsemble,
        ModelOutput,
    )

    # Create ensemble for specific target-horizon
    ensemble = create_model_ensemble("volatility", horizon=6, task_type="regression")

    # Fit on Layer 2 train data (enriched with helper features)
    ensemble.fit(X_train, y_train)

    # Calibrate on Layer 2 cal data
    ensemble.calibrate(X_cal, y_cal)

    # Predict on Layer 2 pred
    output = ensemble.predict(X_pred)
"""

from scripts.target_models.models.base import (
    BaseModel,
    ModelConfig,
    ModelOutput,
)
from scripts.target_models.models.catboost_model import (
    CatBoostModel,
    create_catboost_model,
)
from scripts.target_models.models.ensemble import (
    EnsembleOutput,
    ModelEnsemble,
    create_model_ensemble,
)
from scripts.target_models.models.lightgbm_model import (
    LightGBMModel,
    create_lightgbm_model,
)
from scripts.target_models.models.linear import (
    LinearModel,
    create_linear_model,
)

__all__ = [
    # Base classes
    "BaseModel",
    "ModelConfig",
    "ModelOutput",
    # Ensemble
    "ModelEnsemble",
    "EnsembleOutput",
    "create_model_ensemble",
    # Individual models
    "CatBoostModel",
    "create_catboost_model",
    "LightGBMModel",
    "create_lightgbm_model",
    "LinearModel",
    "create_linear_model",
]
