"""
Base classes and protocols for per-model architecture.

Provides:
- ModelConfig: ABC for model-specific configurations
- ModelResult: Dataclass for standardized model outputs
- ModelProtocol: Protocol defining model interface

Each model module (catboost_model.py, lightgbm_model.py, etc.) will:
1. Extend ModelConfig with model-specific hyperparameters
2. Return ModelResult from train_and_predict()
3. Implement ModelProtocol interface
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    pass


@dataclass
class ModelConfig(ABC):
    """Abstract base class for model-specific configurations.

    All models share these common training/splitting parameters.
    Subclasses add model-specific hyperparameters (e.g., n_estimators, hidden_size).

    Window/split design based on:
    - de Prado "Advances in Financial ML" Ch. 7 (sample size requirements)
    - arXiv 2305.17094 (tree model depth/regularization)

    Defaults optimized per model type:
    - Tree models (CB/LGB): 400 window, recent data preference
    - LSTM: 600 window, needs sequence data
    - Linear: 800 window, data-hungry for stability
    """

    # === Window/Split Configuration ===
    train_window: int = 500  # Training window size (bars)
    train_ratio: float = 0.55  # Train split within window
    val_ratio: float = 0.15  # Validation split
    cal_ratio: float = 0.30  # Calibration split

    # === Embargo (leakage prevention) ===
    # Gap between train/val/cal to prevent temporal leakage
    # Formula: min(3 * horizon, 36) - see get_embargo_for_horizon()
    embargo_bars: int = 24

    # === Feature Selection ===
    feature_selection: str = "none"  # "none", "icir", "importance", "variance"
    feature_selection_ratio: float = 1.0  # Keep top X% of features (1.0 = all)
    min_features: int = 20  # Never go below this count

    # === Random State ===
    random_state: int = 42

    def validate(self) -> None:
        """Validate configuration values.

        Raises:
            ValueError: If any configuration value is invalid.
        """
        if self.train_window < 100:
            raise ValueError(f"train_window must be >= 100, got {self.train_window}")
        if not (0.3 <= self.train_ratio <= 0.8):
            raise ValueError(f"train_ratio must be 0.3-0.8, got {self.train_ratio}")
        if self.feature_selection not in ("none", "icir", "importance", "variance"):
            raise ValueError(f"Invalid feature_selection: {self.feature_selection}")
        if not (0.1 <= self.feature_selection_ratio <= 1.0):
            raise ValueError("feature_selection_ratio must be 0.1-1.0")

    @abstractmethod
    def get_model_name(self) -> str:
        """Return model identifier (e.g., 'catboost', 'lightgbm', 'lstm', 'linear')."""

    @property
    def cal_ratio_computed(self) -> float:
        """Compute calibration ratio from train and val ratios."""
        return 1.0 - self.train_ratio - self.val_ratio


@dataclass
class ModelResult:
    """Standardized output from model training and prediction.

    Returned by each model's train_and_predict() function.
    Contains everything needed for ensemble and metrics.

    Fields:
    - prediction: Hard class prediction (0, 1, 2 for direction)
    - probabilities: Soft probability distribution over classes
    - metrics: Model-specific metrics (accuracy, loss, etc.)
    - trained_model: The trained model object (for feature importance)
    - selected_features: List of features used (after selection)
    - best_params: Tuned hyperparameters (if Optuna was used)
    """

    # === Core Predictions ===
    prediction: int | None = None  # Hard prediction (class index)
    probabilities: np.ndarray | None = None  # Shape: (n_classes,)

    # === Training Metrics ===
    metrics: dict[str, Any] = field(default_factory=dict)
    # Example: {"val_accuracy": 0.65, "val_loss": 0.8, "train_time": 2.5}

    # === Model State ===
    trained_model: Any = None  # The actual trained model object
    selected_features: list[str] = field(default_factory=list)
    best_params: dict[str, Any] = field(default_factory=dict)

    # === Debug/Diagnostics ===
    train_size: int = 0
    val_size: int = 0
    cal_size: int = 0

    def is_valid(self) -> bool:
        """Check if result contains valid prediction."""
        return self.prediction is not None and self.probabilities is not None


class ModelProtocol(Protocol):
    """Protocol defining the interface each model module must implement.

    Each model module (catboost_model.py, etc.) should have functions matching:
    - train_and_predict_classifier(...)
    - train_and_predict_regressor(...)
    - get_default_config()
    """

    def train_and_predict_classifier(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_val: pd.DataFrame,
        y_val: pd.Series,
        X_cal: pd.DataFrame,
        y_cal: pd.Series,
        X_pred: pd.DataFrame,
        config: ModelConfig,
        n_classes: int,
        tune: bool = True,
        previous_best: dict[str, Any] | None = None,
    ) -> ModelResult:
        """Train classifier and predict single point.

        Args:
            X_train: Training features
            y_train: Training labels
            X_val: Validation features (for early stopping/tuning)
            y_val: Validation labels
            X_cal: Calibration features (for conformal prediction)
            y_cal: Calibration labels
            X_pred: Single row to predict
            config: Model-specific configuration
            n_classes: Number of classes
            tune: Whether to run Optuna tuning
            previous_best: Best params from previous step (warm start)

        Returns:
            ModelResult with prediction, probabilities, metrics, etc.
        """
        ...

    def train_and_predict_regressor(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_val: pd.DataFrame,
        y_val: pd.Series,
        X_cal: pd.DataFrame,
        y_cal: pd.Series,
        X_pred: pd.DataFrame,
        config: ModelConfig,
        tune: bool = True,
        previous_best: dict[str, Any] | None = None,
    ) -> ModelResult:
        """Train regressor and predict single point.

        Args:
            X_train: Training features
            y_train: Training targets
            X_val: Validation features
            y_val: Validation targets
            X_cal: Calibration features
            y_cal: Calibration targets
            X_pred: Single row to predict
            config: Model-specific configuration
            tune: Whether to run Optuna tuning
            previous_best: Best params from previous step

        Returns:
            ModelResult with prediction, metrics, etc.
        """
        ...


__all__ = [
    "ModelConfig",
    "ModelResult",
    "ModelProtocol",
]
