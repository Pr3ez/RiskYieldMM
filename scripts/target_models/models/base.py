"""
Base classes for Layer 2 supervised models.

Provides:
- BaseModel: Abstract base class with common interface
- ModelConfig: Configuration dataclass for models
- ModelOutput: Container for model predictions
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
import pandas as pd


# =============================================================================
# CONFIGURATION
# =============================================================================
@dataclass
class ModelConfig:
    """
    Configuration for a supervised model.

    Contains both model-specific params and target-horizon context.
    """

    # Target-horizon context
    target: str = ""
    horizon: int = 1
    task_type: Literal["regression", "binary", "multiclass"] = "regression"
    n_classes: int = 2  # For classification (binary=2, vol_regime=3)

    # Common model settings
    random_state: int = 42
    verbose: bool = False

    # Training settings
    early_stopping_rounds: int = 50
    max_iterations: int = 1000

    @property
    def identifier(self) -> str:
        return f"{self.target}_{self.horizon}bar"

    @property
    def is_classification(self) -> bool:
        return self.task_type in ("binary", "multiclass")

    @property
    def is_regression(self) -> bool:
        return self.task_type == "regression"


# =============================================================================
# OUTPUT CONTAINER
# =============================================================================
@dataclass
class ModelOutput:
    """
    Container for model predictions.

    Provides consistent interface for combining outputs from
    multiple models.
    """

    y_pred: np.ndarray  # Point predictions
    y_prob: np.ndarray | None  # Probabilities (classification only)
    model_name: str
    metadata: dict[str, Any] = field(default_factory=dict)

    # Optional calibrated probabilities
    y_prob_calibrated: np.ndarray | None = None

    @property
    def n_samples(self) -> int:
        return len(self.y_pred)

    @property
    def has_probabilities(self) -> bool:
        return self.y_prob is not None

    @property
    def has_calibrated(self) -> bool:
        return self.y_prob_calibrated is not None

    def __repr__(self) -> str:
        prob_str = f", prob={self.y_prob.shape}" if self.has_probabilities else ""
        return f"ModelOutput({self.model_name}: n={self.n_samples}{prob_str})"


# =============================================================================
# BASE MODEL CLASS
# =============================================================================
class BaseModel(ABC):
    """
    Abstract base class for all Layer 2 supervised models.

    Models are supervised learners that:
    1. Fit on Layer 2 train window (enriched with helper features)
    2. Optionally calibrate on Layer 2 cal window
    3. Predict on Layer 2 val/pred windows

    Subclasses must implement:
    - _fit(): Internal fit logic
    - _predict(): Internal prediction logic
    - _predict_proba(): Internal probability prediction (classification)
    """

    def __init__(self, config: ModelConfig):
        self.config = config
        self._fitted = False
        self._calibrator = None  # For probability calibration
        self.fit_params: dict[str, Any] = {}

    @property
    @abstractmethod
    def name(self) -> str:
        """Model name for identification."""
        ...

    @property
    def is_fitted(self) -> bool:
        return self._fitted

    # -------------------------------------------------------------------------
    # Abstract methods for subclasses
    # -------------------------------------------------------------------------
    @abstractmethod
    def _fit(self, X: np.ndarray, y: np.ndarray) -> None:
        """Internal fit implementation."""
        ...

    @abstractmethod
    def _predict(self, X: np.ndarray) -> np.ndarray:
        """Internal prediction implementation."""
        ...

    @abstractmethod
    def _predict_proba(self, X: np.ndarray) -> np.ndarray | None:
        """Internal probability prediction. Returns None for regression."""
        ...

    # -------------------------------------------------------------------------
    # Public interface
    # -------------------------------------------------------------------------
    def fit(
        self,
        X: pd.DataFrame | np.ndarray,
        y: pd.Series | np.ndarray,
        X_val: pd.DataFrame | np.ndarray | None = None,
        y_val: pd.Series | np.ndarray | None = None,
    ) -> "BaseModel":
        """
        Fit model on training data.

        Args:
            X: Training features
            y: Training targets
            X_val: Optional validation features (for early stopping)
            y_val: Optional validation targets

        Returns:
            self for chaining
        """
        # Convert to numpy
        X_np = X.values if isinstance(X, pd.DataFrame) else X
        y_np = y.values if isinstance(y, pd.Series) else y

        X_val_np = None
        y_val_np = None
        if X_val is not None:
            X_val_np = X_val.values if isinstance(X_val, pd.DataFrame) else X_val
            y_val_np = y_val.values if isinstance(y_val, pd.Series) else y_val

        # Store validation set for early stopping
        self._X_val = X_val_np
        self._y_val = y_val_np

        # Fit
        self._fit(X_np, y_np)
        self._fitted = True

        return self

    def _normalize_proba_shape(self, y_prob: np.ndarray | None) -> np.ndarray | None:
        """
        Ensure probability array has correct number of columns for multiclass.

        When some classes are missing from training data, models may output
        fewer probability columns. This pads with zeros to match n_classes.
        """
        if y_prob is None:
            return None

        if self.config.task_type != "multiclass":
            return y_prob

        n_samples = y_prob.shape[0]
        n_prob_cols = y_prob.shape[1] if y_prob.ndim > 1 else 1
        n_expected = self.config.n_classes

        if n_prob_cols == n_expected:
            return y_prob

        # Pad with zeros for missing classes
        if n_prob_cols < n_expected:
            padded = np.zeros((n_samples, n_expected), dtype=y_prob.dtype)
            padded[:, :n_prob_cols] = y_prob
            return padded

        # Truncate if more than expected (shouldn't happen, but be safe)
        return y_prob[:, :n_expected]

    def predict(self, X: pd.DataFrame | np.ndarray) -> ModelOutput:
        """
        Generate predictions.

        Args:
            X: Features to predict on

        Returns:
            ModelOutput with predictions and probabilities
        """
        if not self.is_fitted:
            raise RuntimeError(f"{self.name} must be fitted before predict")

        X_np = X.values if isinstance(X, pd.DataFrame) else X

        y_pred = self._predict(X_np)
        y_prob = self._predict_proba(X_np) if self.config.is_classification else None

        # Normalize probability shape for multiclass (handle missing classes)
        y_prob = self._normalize_proba_shape(y_prob)

        # Apply calibration if available
        y_prob_calibrated = None
        if y_prob is not None and self._calibrator is not None:
            y_prob_calibrated = self._calibrate_proba(y_prob)
            # Also normalize calibrated probabilities
            y_prob_calibrated = self._normalize_proba_shape(y_prob_calibrated)

        return ModelOutput(
            y_pred=y_pred,
            y_prob=y_prob,
            y_prob_calibrated=y_prob_calibrated,
            model_name=self.name,
            metadata={"config": self.config, "fit_params": self.fit_params},
        )

    def calibrate(
        self,
        X: pd.DataFrame | np.ndarray,
        y: pd.Series | np.ndarray,
        method: Literal["isotonic", "platt"] = "isotonic",
    ) -> "BaseModel":
        """
        Calibrate probability predictions using calibration data.

        Only applies to classification models.

        Args:
            X: Calibration features
            y: Calibration targets
            method: 'isotonic' (non-parametric) or 'platt' (sigmoid)

        Returns:
            self for chaining
        """
        if not self.config.is_classification:
            return self  # No-op for regression

        if not self.is_fitted:
            raise RuntimeError(f"{self.name} must be fitted before calibrate")

        from sklearn.isotonic import IsotonicRegression
        from sklearn.linear_model import LogisticRegression

        X_np = X.values if isinstance(X, pd.DataFrame) else X
        y_np = y.values if isinstance(y, pd.Series) else y

        # Get uncalibrated probabilities
        y_prob = self._predict_proba(X_np)

        if y_prob is None:
            return self

        # For binary: use column 1 (P(positive))
        if self.config.task_type == "binary":
            probs = y_prob[:, 1] if y_prob.ndim > 1 else y_prob

            if method == "isotonic":
                self._calibrator = IsotonicRegression(out_of_bounds="clip")
                self._calibrator.fit(probs, y_np)
            else:  # platt
                self._calibrator = LogisticRegression()
                self._calibrator.fit(probs.reshape(-1, 1), y_np)

        else:  # multiclass - calibrate per class
            # Use sklearn's CalibratedClassifierCV approach
            # Store calibrators per class
            self._calibrator = {}
            n_prob_classes = y_prob.shape[1] if y_prob.ndim > 1 else 1
            for cls in range(self.config.n_classes):
                y_binary = (y_np == cls).astype(int)

                # Handle case where model outputs fewer classes than configured
                # (can happen if some classes are missing from training data)
                if cls >= n_prob_classes:
                    # Create a dummy calibrator that returns 0 probability
                    self._calibrator[cls] = None
                    continue

                probs = y_prob[:, cls]

                if method == "isotonic":
                    cal = IsotonicRegression(out_of_bounds="clip")
                else:
                    cal = LogisticRegression()

                cal.fit(probs.reshape(-1, 1) if method == "platt" else probs, y_binary)
                self._calibrator[cls] = cal

        self.fit_params["calibration_method"] = method
        return self

    def _calibrate_proba(self, y_prob: np.ndarray) -> np.ndarray:
        """Apply calibration to probability predictions."""
        if self._calibrator is None:
            return y_prob

        if self.config.task_type == "binary":
            probs = y_prob[:, 1] if y_prob.ndim > 1 else y_prob

            if hasattr(self._calibrator, "predict_proba"):
                # Platt scaling (LogisticRegression)
                cal_probs = self._calibrator.predict_proba(probs.reshape(-1, 1))[:, 1]
            else:
                # Isotonic regression - use predict()
                cal_probs = self._calibrator.predict(probs)

            # Clip to [0, 1]
            cal_probs = np.clip(cal_probs, 0, 1)
            return np.column_stack([1 - cal_probs, cal_probs])

        else:  # multiclass
            # Ensure output has correct shape for all configured classes
            n_samples = y_prob.shape[0]
            n_prob_classes = y_prob.shape[1] if y_prob.ndim > 1 else 1
            cal_probs = np.zeros((n_samples, self.config.n_classes))

            for cls, cal in self._calibrator.items():
                # Handle missing classes (calibrator is None)
                if cal is None:
                    cal_probs[:, cls] = 0.0
                    continue

                # Handle case where y_prob has fewer columns than n_classes
                if cls >= n_prob_classes:
                    cal_probs[:, cls] = 0.0
                    continue

                probs = y_prob[:, cls]
                if hasattr(cal, "predict_proba"):
                    # Platt scaling
                    cal_probs[:, cls] = cal.predict_proba(probs.reshape(-1, 1))[:, 1]
                else:
                    cal_probs[:, cls] = cal.predict(probs)

            # Normalize to sum to 1
            cal_probs = np.clip(cal_probs, 1e-10, 1)
            cal_probs = cal_probs / cal_probs.sum(axis=1, keepdims=True)
            return cal_probs

    def get_feature_importance(self) -> pd.Series | None:
        """
        Get feature importance if available.

        Returns:
            Series with feature names as index, importance as values.
            None if model doesn't support feature importance.
        """
        return None  # Override in subclasses

    def __repr__(self) -> str:
        status = "fitted" if self.is_fitted else "not fitted"
        return f"{self.name}({self.config.identifier}, {status})"
