"""
LightGBM Model Wrapper for Layer 2.

LightGBM complements CatBoost in ensemble:
- Faster training (histogram-based)
- Different bias-variance tradeoff
- Good for feature importance analysis
"""

from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd

from scripts.target_models.models.base import BaseModel, ModelConfig


class LightGBMModel(BaseModel):
    """
    LightGBM wrapper for classification and regression.

    Automatically selects classifier or regressor based on task_type.
    """

    def __init__(self, config: ModelConfig, **kwargs):
        super().__init__(config)
        self._model = None
        self._single_class = None  # For degenerate case handling
        self._feature_names: list[str] = []
        self._extra_params = kwargs

    @property
    def name(self) -> str:
        return "LightGBM"

    def _get_model_params(self) -> dict[str, Any]:
        """Get LightGBM parameters based on task type."""
        base_params = {
            "n_estimators": self.config.max_iterations,
            "random_state": self.config.random_state,
            "verbose": -1 if not self.config.verbose else 1,
            # Structure
            "max_depth": 6,
            "num_leaves": 31,
            "learning_rate": 0.05,
            # Regularization
            "reg_alpha": 0.1,
            "reg_lambda": 0.1,
            "min_child_samples": 20,
            # Speed - GPU acceleration
            "device": "gpu",
            "gpu_platform_id": 0,
            "gpu_device_id": 0,
        }

        if self.config.is_classification:
            if self.config.task_type == "binary":
                base_params["objective"] = "binary"
                base_params["metric"] = "auc"
            else:  # multiclass
                base_params["objective"] = "multiclass"
                base_params["metric"] = "multi_logloss"
                base_params["num_class"] = self.config.n_classes
        else:  # regression
            base_params["objective"] = "regression"
            base_params["metric"] = "rmse"

        # Override with extra params
        base_params.update(self._extra_params)

        return base_params

    def _fit(self, X: np.ndarray, y: np.ndarray) -> None:
        """Fit LightGBM model."""
        # Check for degenerate case: all targets are the same
        # LightGBM cannot train when there's no variation in target
        unique_classes = np.unique(y)
        if self.config.is_classification and len(unique_classes) == 1:
            # Store the single class for prediction
            self._single_class = unique_classes[0]
            self._model = None  # No model to fit
            self.fit_params["degenerate"] = True
            self.fit_params["single_class"] = int(self._single_class)
            return

        self._single_class = None  # Normal training

        params = self._get_model_params()

        # Create model
        if self.config.is_classification:
            self._model = lgb.LGBMClassifier(**params)
        else:
            self._model = lgb.LGBMRegressor(**params)

        # Prepare callbacks for early stopping
        callbacks = []
        eval_set = None
        eval_names = None

        if self._X_val is not None and self._y_val is not None:
            X_val_filtered = self._X_val
            y_val_filtered = self._y_val

            # For multiclass: filter validation to only classes present in training
            # LightGBM's label encoder fails if validation has unseen classes
            if self.config.is_classification and self.config.task_type == "multiclass":
                train_classes = set(np.unique(y))
                val_classes = set(np.unique(self._y_val))
                if not val_classes.issubset(train_classes):
                    # Filter validation to only include samples with known classes
                    mask = np.isin(self._y_val, list(train_classes))
                    if mask.sum() > 0:
                        X_val_filtered = self._X_val[mask]
                        y_val_filtered = self._y_val[mask]
                    else:
                        # No valid samples, skip validation
                        X_val_filtered = None
                        y_val_filtered = None

            if X_val_filtered is not None and y_val_filtered is not None:
                eval_set = [(X_val_filtered, y_val_filtered)]
                eval_names = ["valid"]
                callbacks.append(
                    lgb.early_stopping(
                        stopping_rounds=self.config.early_stopping_rounds,
                        verbose=self.config.verbose,
                    )
                )

        # Fit
        self._model.fit(
            X,
            y,
            eval_set=eval_set,
            eval_names=eval_names,
            callbacks=callbacks if callbacks else None,
        )

        # Store fit info
        self.fit_params["best_iteration"] = self._model.best_iteration_
        if hasattr(self._model, "best_score_"):
            self.fit_params["best_score"] = self._model.best_score_

    def _predict(self, X: np.ndarray) -> np.ndarray:
        """Generate point predictions."""
        # Handle degenerate case (all targets were same class)
        if self._single_class is not None:
            return np.full(len(X), self._single_class)

        return self._model.predict(X).flatten()

    def _predict_proba(self, X: np.ndarray) -> np.ndarray | None:
        """Generate probability predictions for classification."""
        if not self.config.is_classification:
            return None

        # Handle degenerate case (all targets were same class)
        if self._single_class is not None:
            n_classes = self.config.n_classes
            probs = np.zeros((len(X), n_classes))
            probs[:, int(self._single_class)] = 1.0
            return probs

        probs = self._model.predict_proba(X)

        # Ensure 2D for binary
        if probs.ndim == 1:
            probs = np.column_stack([1 - probs, probs])

        return probs

    def get_feature_importance(
        self,
        feature_names: list[str] | None = None,
        importance_type: str = "gain",
    ) -> pd.Series:
        """
        Get feature importance from trained model.

        Args:
            feature_names: Optional list of feature names
            importance_type: "gain" (default), "split", or "weight"
        """
        if self._model is None:
            raise RuntimeError("Model not fitted")

        importance = self._model.feature_importances_
        names = feature_names or [f"f{i}" for i in range(len(importance))]

        return pd.Series(importance, index=names).sort_values(ascending=False)


def create_lightgbm_model(
    target: str,
    horizon: int,
    task_type: str = "regression",
    n_classes: int = 2,
    random_state: int = 42,
    **kwargs,
) -> LightGBMModel:
    """
    Factory function to create a LightGBM model.

    Args:
        target: Target name (e.g., "volatility")
        horizon: Prediction horizon in bars
        task_type: "regression", "binary", or "multiclass"
        n_classes: Number of classes for classification
        random_state: Random seed
        **kwargs: Additional LightGBM parameters

    Returns:
        Configured LightGBMModel
    """
    config = ModelConfig(
        target=target,
        horizon=horizon,
        task_type=task_type,
        n_classes=n_classes,
        random_state=random_state,
    )
    return LightGBMModel(config, **kwargs)
