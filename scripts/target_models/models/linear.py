"""
Linear Model Wrapper for Layer 2.

Linear models serve as interpretable baselines:
- Ridge regression for continuous targets
- Logistic regression for classification
- Fast training and prediction
- Feature coefficient analysis
"""

from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.preprocessing import StandardScaler

from scripts.target_models.models.base import BaseModel, ModelConfig


class LinearModel(BaseModel):
    """
    Linear model wrapper for classification and regression.

    Uses:
    - Ridge regression for regression tasks
    - Logistic regression for classification tasks

    Always applies StandardScaler to features.
    """

    def __init__(self, config: ModelConfig, **kwargs):
        super().__init__(config)
        self._model = None
        self._single_class = None  # For degenerate case handling
        self._scaler = StandardScaler()
        self._feature_names: list[str] = []
        self._extra_params = kwargs

    @property
    def name(self) -> str:
        if self.config.is_classification:
            return "LogisticRegression"
        return "Ridge"

    def _get_model_params(self) -> dict[str, Any]:
        """Get model parameters based on task type."""
        if self.config.is_classification:
            base_params = {
                "random_state": self.config.random_state,
                "max_iter": self.config.max_iterations,
                "solver": "lbfgs",
                "C": 1.0,  # Inverse of regularization
            }
            # multi_class is deprecated in newer sklearn, lbfgs handles it automatically
        else:  # regression
            base_params = {
                "random_state": self.config.random_state,
                "alpha": 10.0,  # Regularization strength
            }

        # Override with extra params
        base_params.update(self._extra_params)

        return base_params

    def _fit(self, X: np.ndarray, y: np.ndarray) -> None:
        """Fit linear model with scaling."""
        # Check for degenerate case: all targets are the same
        # sklearn LogisticRegression cannot train when there's no variation
        unique_classes = np.unique(y)
        if self.config.is_classification and len(unique_classes) == 1:
            # Store the single class for prediction
            self._single_class = unique_classes[0]
            self._model = None  # No model to fit
            # Still fit scaler for consistent transforms
            self._scaler.fit(X)
            self.fit_params["degenerate"] = True
            self.fit_params["single_class"] = int(self._single_class)
            return

        self._single_class = None  # Normal training

        # Scale features
        X_scaled = self._scaler.fit_transform(X)

        # Get params
        params = self._get_model_params()

        # Create model
        if self.config.is_classification:
            self._model = LogisticRegression(**params)
        else:
            self._model = Ridge(**params)

        # Fit (no early stopping for linear models)
        self._model.fit(X_scaled, y)

        # Store fit info
        if hasattr(self._model, "n_iter_"):
            self.fit_params["n_iterations"] = self._model.n_iter_

    def _predict(self, X: np.ndarray) -> np.ndarray:
        """Generate point predictions."""
        # Handle degenerate case (all targets were same class)
        if self._single_class is not None:
            return np.full(len(X), self._single_class)

        X_scaled = self._scaler.transform(X)
        return self._model.predict(X_scaled).flatten()

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

        X_scaled = self._scaler.transform(X)
        probs = self._model.predict_proba(X_scaled)

        # Ensure 2D for binary
        if probs.ndim == 1:
            probs = np.column_stack([1 - probs, probs])

        return probs

    def get_feature_importance(
        self, feature_names: list[str] | None = None
    ) -> pd.Series:
        """
        Get feature coefficients as importance.

        For linear models, absolute coefficient magnitude indicates importance.
        Sign indicates direction of effect.
        """
        if self._model is None:
            raise RuntimeError("Model not fitted")

        if self.config.is_classification and self.config.task_type == "multiclass":
            # Average absolute coefficients across classes
            coef = np.abs(self._model.coef_).mean(axis=0)
        else:
            coef = self._model.coef_.flatten()

        names = feature_names or [f"f{i}" for i in range(len(coef))]

        return pd.Series(np.abs(coef), index=names).sort_values(ascending=False)

    def get_coefficients(self, feature_names: list[str] | None = None) -> pd.Series:
        """
        Get raw coefficients (with sign).

        Useful for understanding direction of feature effects.
        """
        if self._model is None:
            raise RuntimeError("Model not fitted")

        coef = self._model.coef_.flatten()
        names = feature_names or [f"f{i}" for i in range(len(coef))]

        return pd.Series(coef, index=names).sort_values(key=abs, ascending=False)


def create_linear_model(
    target: str,
    horizon: int,
    task_type: str = "regression",
    n_classes: int = 2,
    random_state: int = 42,
    **kwargs,
) -> LinearModel:
    """
    Factory function to create a linear model.

    Args:
        target: Target name (e.g., "volatility")
        horizon: Prediction horizon in bars
        task_type: "regression", "binary", or "multiclass"
        n_classes: Number of classes for classification
        random_state: Random seed
        **kwargs: Additional model parameters

    Returns:
        Configured LinearModel (Ridge or LogisticRegression)
    """
    config = ModelConfig(
        target=target,
        horizon=horizon,
        task_type=task_type,
        n_classes=n_classes,
        random_state=random_state,
    )
    return LinearModel(config, **kwargs)
