"""
Model Ensemble for Layer 2.

Combines predictions from CatBoost, LightGBM, and Linear models
using weighted averaging or stacking.

Architecture:
    X_enriched (base + helper features)
              ↓
    ┌─────────┼─────────┐
    ↓         ↓         ↓
    CatBoost  LightGBM  Linear
    ↓         ↓         ↓
    └─────────┼─────────┘
              ↓
        Weighted Average
              ↓
        Final Prediction
"""

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from scripts.target_models.models.base import BaseModel, ModelConfig, ModelOutput
from scripts.target_models.models.catboost_model import CatBoostModel
from scripts.target_models.models.lightgbm_model import LightGBMModel
from scripts.target_models.models.linear import LinearModel


@dataclass
class EnsembleOutput:
    """
    Container for ensemble predictions.

    Combines outputs from multiple models with ensemble prediction.
    """

    y_pred: np.ndarray  # Ensemble point prediction
    y_prob: np.ndarray | None  # Ensemble probability (classification)
    y_prob_calibrated: np.ndarray | None  # Calibrated ensemble probability

    # Per-model outputs
    model_outputs: dict[str, ModelOutput] = field(default_factory=dict)

    # Ensemble metadata
    weights: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def n_samples(self) -> int:
        return len(self.y_pred)

    @property
    def n_models(self) -> int:
        return len(self.model_outputs)

    def get_model_predictions(self) -> pd.DataFrame:
        """Get predictions from all models as DataFrame."""
        data = {}
        for name, output in self.model_outputs.items():
            data[f"{name}_pred"] = output.y_pred
            if output.y_prob is not None:
                # For binary: use P(positive)
                if output.y_prob.ndim > 1:
                    data[f"{name}_prob"] = output.y_prob[:, 1]
                else:
                    data[f"{name}_prob"] = output.y_prob
        return pd.DataFrame(data)

    def __repr__(self) -> str:
        models = ", ".join(self.model_outputs.keys())
        return f"EnsembleOutput(n={self.n_samples}, models=[{models}])"


class ModelEnsemble:
    """
    Ensemble of supervised models for Layer 2.

    Combines:
    - CatBoost (primary, weight=0.4)
    - LightGBM (secondary, weight=0.4)
    - Linear (baseline, weight=0.2)

    Supports:
    - Weighted averaging of predictions
    - Per-model calibration
    - Feature importance aggregation
    """

    DEFAULT_WEIGHTS = {
        "CatBoost": 0.4,
        "LightGBM": 0.4,
        "Ridge": 0.2,
        "LogisticRegression": 0.2,
    }

    def __init__(
        self,
        config: ModelConfig,
        weights: dict[str, float] | None = None,
        include_linear: bool = True,
    ):
        self.config = config
        self.weights = weights or self.DEFAULT_WEIGHTS.copy()
        self.include_linear = include_linear

        # Initialize models
        self.models: dict[str, BaseModel] = {}
        self._create_models()

        # State
        self._fitted = False
        self._calibrated = False
        self.fit_params: dict[str, Any] = {}

    def _create_models(self) -> None:
        """Create component models."""
        # CatBoost
        self.models["CatBoost"] = CatBoostModel(self.config)

        # LightGBM
        self.models["LightGBM"] = LightGBMModel(self.config)

        # Linear (optional)
        if self.include_linear:
            self.models["Linear"] = LinearModel(self.config)

    @property
    def is_fitted(self) -> bool:
        return self._fitted

    @property
    def is_calibrated(self) -> bool:
        return self._calibrated

    @property
    def model_names(self) -> list[str]:
        return list(self.models.keys())

    def fit(
        self,
        X: pd.DataFrame | np.ndarray,
        y: pd.Series | np.ndarray,
        X_val: pd.DataFrame | np.ndarray | None = None,
        y_val: pd.Series | np.ndarray | None = None,
    ) -> "ModelEnsemble":
        """
        Fit all models in the ensemble.

        Args:
            X: Training features (enriched with helper features)
            y: Training targets
            X_val: Validation features (for early stopping)
            y_val: Validation targets

        Returns:
            self for chaining
        """
        for name, model in self.models.items():
            if self.config.verbose:
                print(f"  Fitting {name}...")
            model.fit(X, y, X_val, y_val)

        self._fitted = True
        # sklearn-compatible fitted attributes (for check_is_fitted)
        self.classes_ = np.unique(y) if self.config.is_classification else None
        self.n_features_in_ = X.shape[1] if hasattr(X, "shape") else len(X[0])
        return self

    def calibrate(
        self,
        X: pd.DataFrame | np.ndarray,
        y: pd.Series | np.ndarray,
        method: str = "isotonic",
    ) -> "ModelEnsemble":
        """
        Calibrate all classification models.

        Args:
            X: Calibration features
            y: Calibration targets
            method: 'isotonic' or 'platt'

        Returns:
            self for chaining
        """
        if not self.config.is_classification:
            return self  # No-op for regression

        for name, model in self.models.items():
            if self.config.verbose:
                print(f"  Calibrating {name}...")
            model.calibrate(X, y, method=method)

        self._calibrated = True
        self.fit_params["calibration_method"] = method
        return self

    def predict(self, X: pd.DataFrame | np.ndarray) -> EnsembleOutput:
        """
        Generate ensemble predictions.

        Args:
            X: Features to predict on

        Returns:
            EnsembleOutput with ensemble and per-model predictions
        """
        if not self.is_fitted:
            raise RuntimeError("Ensemble must be fitted before predict")

        # Get predictions from each model
        model_outputs = {}
        for name, model in self.models.items():
            model_outputs[name] = model.predict(X)

        # Compute ensemble prediction
        y_pred, y_prob, y_prob_cal = self._combine_predictions(model_outputs)

        return EnsembleOutput(
            y_pred=y_pred,
            y_prob=y_prob,
            y_prob_calibrated=y_prob_cal,
            model_outputs=model_outputs,
            weights=self._get_normalized_weights(),
            metadata={"config": self.config, "fit_params": self.fit_params},
        )

    def predict_proba(self, X: pd.DataFrame | np.ndarray) -> np.ndarray:
        """
        Generate probability predictions (sklearn-compatible interface).

        Required for MAPIE conformal prediction.

        Args:
            X: Features to predict on

        Returns:
            np.ndarray: Class probabilities (n_samples, n_classes)
                       Uses calibrated probabilities if available
        """
        output = self.predict(X)

        # Return calibrated probabilities if available, else raw probabilities
        if output.y_prob_calibrated is not None:
            return output.y_prob_calibrated
        elif output.y_prob is not None:
            return output.y_prob
        else:
            raise ValueError(
                "predict_proba requires classification model with probabilities"
            )

    def predict_labels(self, X: pd.DataFrame | np.ndarray) -> np.ndarray:
        """
        Generate class label predictions (sklearn-compatible interface).

        Args:
            X: Features to predict on

        Returns:
            np.ndarray: Class labels (n_samples,)
        """
        output = self.predict(X)
        return output.y_pred

    def _get_normalized_weights(self) -> dict[str, float]:
        """Get normalized weights for active models."""
        active_weights = {}
        for name in self.models:
            # Map Linear to its actual name
            if name == "Linear":
                key = "LogisticRegression" if self.config.is_classification else "Ridge"
            else:
                key = name
            active_weights[name] = self.weights.get(key, 0.0)

        # Normalize
        total = sum(active_weights.values())
        if total > 0:
            active_weights = {k: v / total for k, v in active_weights.items()}

        return active_weights

    def _combine_predictions(
        self, model_outputs: dict[str, ModelOutput]
    ) -> tuple[np.ndarray, np.ndarray | None, np.ndarray | None]:
        """
        Combine predictions from all models.

        Uses weighted averaging.
        """
        weights = self._get_normalized_weights()

        if self.config.is_classification:
            return self._combine_classification(model_outputs, weights)
        else:
            return self._combine_regression(model_outputs, weights)

    def _combine_regression(
        self, model_outputs: dict[str, ModelOutput], weights: dict[str, float]
    ) -> tuple[np.ndarray, None, None]:
        """Combine regression predictions."""
        weighted_sum = None

        for name, output in model_outputs.items():
            w = weights.get(name, 0.0)
            if w > 0:
                if weighted_sum is None:
                    weighted_sum = w * output.y_pred
                else:
                    weighted_sum += w * output.y_pred

        return weighted_sum, None, None

    def _combine_classification(
        self, model_outputs: dict[str, ModelOutput], weights: dict[str, float]
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
        """Combine classification predictions using probability averaging."""
        # Average probabilities
        weighted_prob = None
        weighted_prob_cal = None

        for name, output in model_outputs.items():
            w = weights.get(name, 0.0)
            if w > 0 and output.y_prob is not None:
                if weighted_prob is None:
                    weighted_prob = w * output.y_prob
                else:
                    weighted_prob += w * output.y_prob

                # Calibrated probabilities
                if output.y_prob_calibrated is not None:
                    if weighted_prob_cal is None:
                        weighted_prob_cal = w * output.y_prob_calibrated
                    else:
                        weighted_prob_cal += w * output.y_prob_calibrated

        # Point prediction from averaged probabilities
        if self.config.task_type == "binary":
            y_pred = (weighted_prob[:, 1] > 0.5).astype(int)
        else:  # multiclass
            y_pred = np.argmax(weighted_prob, axis=1)

        return y_pred, weighted_prob, weighted_prob_cal

    def get_feature_importance(
        self, feature_names: list[str] | None = None, aggregate: str = "mean"
    ) -> pd.DataFrame:
        """
        Get feature importance from all models.

        Args:
            feature_names: Optional list of feature names
            aggregate: 'mean', 'max', or 'weighted'

        Returns:
            DataFrame with importance per model and aggregate
        """
        if not self.is_fitted:
            raise RuntimeError("Ensemble must be fitted first")

        importance_df = pd.DataFrame()

        for name, model in self.models.items():
            imp = model.get_feature_importance(feature_names)
            if imp is not None:
                importance_df[name] = imp

        if importance_df.empty:
            return importance_df

        # Add aggregate column
        if aggregate == "mean":
            importance_df["aggregate"] = importance_df.mean(axis=1)
        elif aggregate == "max":
            importance_df["aggregate"] = importance_df.max(axis=1)
        elif aggregate == "weighted":
            weights = self._get_normalized_weights()
            weighted_sum = None
            for col in importance_df.columns:
                w = weights.get(col, 0.0)
                if weighted_sum is None:
                    weighted_sum = w * importance_df[col]
                else:
                    weighted_sum += w * importance_df[col]
            importance_df["aggregate"] = weighted_sum

        return importance_df.sort_values("aggregate", ascending=False)

    def __repr__(self) -> str:
        status = "fitted" if self.is_fitted else "not fitted"
        models = ", ".join(self.model_names)
        return f"ModelEnsemble({self.config.identifier}, {status}, models=[{models}])"


def create_model_ensemble(
    target: str,
    horizon: int,
    task_type: str = "regression",
    n_classes: int = 2,
    random_state: int = 42,
    weights: dict[str, float] | None = None,
    include_linear: bool = True,
) -> ModelEnsemble:
    """
    Factory function to create a model ensemble.

    Args:
        target: Target name (e.g., "volatility")
        horizon: Prediction horizon in bars
        task_type: "regression", "binary", or "multiclass"
        n_classes: Number of classes for classification
        random_state: Random seed
        weights: Optional custom weights for models
        include_linear: Whether to include linear baseline

    Returns:
        Configured ModelEnsemble
    """
    config = ModelConfig(
        target=target,
        horizon=horizon,
        task_type=task_type,
        n_classes=n_classes,
        random_state=random_state,
    )
    return ModelEnsemble(config, weights=weights, include_linear=include_linear)
