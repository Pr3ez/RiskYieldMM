"""
CatBoost Model Wrapper for Layer 2.

CatBoost is the primary boosting model due to:
- Native handling of categorical features
- Built-in overfitting detection
- Good performance on small datasets
- Robust to hyperparameter choices
"""

import os
import sys
from typing import Any

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier, CatBoostRegressor

from scripts.target_models.models.base import BaseModel, ModelConfig


class CatBoostModel(BaseModel):
    """
    CatBoost wrapper for classification and regression.

    Automatically selects CatBoostClassifier or CatBoostRegressor
    based on task_type in config.
    """

    def __init__(self, config: ModelConfig, **kwargs):
        super().__init__(config)
        self._model = None
        self._single_class = None  # For degenerate case handling
        self._feature_names: list[str] = []
        self._extra_params = kwargs
        self._use_gpu = self._check_gpu_available()

    def _check_gpu_available(self) -> bool:
        """Check if GPU is available for CatBoost."""
        # Allow override via environment variable
        if os.environ.get("CATBOOST_USE_CPU", "").lower() in ("1", "true", "yes"):
            return False
        if os.environ.get("CUDA_VISIBLE_DEVICES", "") == "":
            return False
        try:
            import subprocess

            result = subprocess.run(["nvidia-smi"], capture_output=True, timeout=5)
            return result.returncode == 0
        except Exception:
            return False

    def _get_task_type(self) -> str:
        """Get task type (GPU or CPU) based on availability."""
        return "GPU" if self._use_gpu else "CPU"

    @property
    def name(self) -> str:
        return "CatBoost"

    def _get_model_params(self) -> dict[str, Any]:
        """Get CatBoost parameters based on task type."""
        base_params = {
            "iterations": self.config.max_iterations,
            "random_seed": self.config.random_state,
            "verbose": self.config.verbose,
            "early_stopping_rounds": self.config.early_stopping_rounds,
            "use_best_model": True,
            # Regularization
            "depth": 6,
            "l2_leaf_reg": 3.0,
            "learning_rate": 0.05,
            # Speed - GPU acceleration (if available)
            "task_type": self._get_task_type(),
        }
        # Only add devices param for GPU
        if self._use_gpu:
            base_params["devices"] = "0"

        if self.config.is_classification:
            if self.config.task_type == "binary":
                base_params["loss_function"] = "Logloss"
                base_params["eval_metric"] = "AUC"
            else:  # multiclass
                base_params["loss_function"] = "MultiClass"
                base_params["eval_metric"] = "MultiClass"
                base_params["classes_count"] = self.config.n_classes
        else:  # regression
            base_params["loss_function"] = "RMSE"
            base_params["eval_metric"] = "RMSE"

        # Override with extra params
        base_params.update(self._extra_params)

        return base_params

    def _fit(self, X: np.ndarray, y: np.ndarray) -> None:
        """Fit CatBoost model."""
        # Check for degenerate case: all targets are the same
        # CatBoost cannot train when there's no variation in target
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

        # Only use best model if we have validation set
        has_val = self._X_val is not None and self._y_val is not None
        if not has_val:
            params["use_best_model"] = False
            params.pop("early_stopping_rounds", None)

        # Create model
        if self.config.is_classification:
            self._model = CatBoostClassifier(**params)
        else:
            self._model = CatBoostRegressor(**params)

        # Prepare eval set if available
        eval_set = None
        if has_val:
            X_val_filtered = self._X_val
            y_val_filtered = self._y_val

            # For multiclass: filter validation to only classes present in training
            # Prevents issues with CatBoost's internal label handling
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
                eval_set = (X_val_filtered, y_val_filtered)
            else:
                # No valid validation set, disable use_best_model
                params["use_best_model"] = False
                params.pop("early_stopping_rounds", None)

        # Fit with stderr suppression for multiclass
        # CatBoost warns "Found only N unique classes but defined M classes" when
        # training data has fewer classes than classes_count. This is expected for
        # multiclass with rare classes in some windows - the warning is harmless and
        # we NEED classes_count to maintain consistent output shape.
        suppress_stderr = (
            self.config.is_classification and self.config.task_type == "multiclass"
        )

        if suppress_stderr:
            stderr_fd = sys.stderr.fileno()
            old_stderr = os.dup(stderr_fd)
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, stderr_fd)

        try:
            self._model.fit(
                X,
                y,
                eval_set=eval_set,
                verbose=self.config.verbose,
            )
        finally:
            if suppress_stderr:
                os.dup2(old_stderr, stderr_fd)
                os.close(old_stderr)
                os.close(devnull)

        # Store fit info
        if has_val:
            self.fit_params["best_iteration"] = self._model.get_best_iteration()
            self.fit_params["best_score"] = self._model.get_best_score()
        else:
            self.fit_params["iterations"] = params["iterations"]

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
        self, feature_names: list[str] | None = None
    ) -> pd.Series:
        """Get feature importance from trained model."""
        if self._model is None:
            raise RuntimeError("Model not fitted")

        importance = self._model.get_feature_importance()
        names = feature_names or [f"f{i}" for i in range(len(importance))]

        return pd.Series(importance, index=names).sort_values(ascending=False)


def create_catboost_model(
    target: str,
    horizon: int,
    task_type: str = "regression",
    n_classes: int = 2,
    random_state: int = 42,
    **kwargs,
) -> CatBoostModel:
    """
    Factory function to create a CatBoost model.

    Args:
        target: Target name (e.g., "volatility")
        horizon: Prediction horizon in bars
        task_type: "regression", "binary", or "multiclass"
        n_classes: Number of classes for classification
        random_state: Random seed
        **kwargs: Additional CatBoost parameters

    Returns:
        Configured CatBoostModel
    """
    config = ModelConfig(
        target=target,
        horizon=horizon,
        task_type=task_type,
        n_classes=n_classes,
        random_state=random_state,
    )
    return CatBoostModel(config, **kwargs)
