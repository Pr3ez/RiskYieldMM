"""
Configuration for target-specific model training.

Each target type has its own:
- Model type (regressor vs classifier)
- Evaluation metrics
- Hyperparameter search space
- CV strategy
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

# =============================================================================
# PATHS
# =============================================================================
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DATASETS_DIR = DATA_DIR / "datasets"
MODELS_DIR = DATA_DIR / "models"
RESULTS_DIR = DATA_DIR / "target_model_results"

# Ensure directories exist
MODELS_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


# =============================================================================
# TARGET CONFIGURATIONS
# =============================================================================
@dataclass
class TargetConfig:
    """Configuration for a specific prediction target."""

    name: str
    task_type: Literal["regression", "binary", "multiclass"]
    target_column_pattern: str  # e.g., "y_volatility_{horizon}"
    primary_metric: str
    secondary_metrics: list[str] = field(default_factory=list)
    horizons: list[int] = field(default_factory=lambda: [1, 3, 6, 12])

    def get_target_column(self, horizon: int) -> str:
        return self.target_column_pattern  # Target column same for all horizons

    def get_dataset_path(self, horizon: int) -> Path:
        return DATASETS_DIR / f"{self.name}_{horizon}bar.parquet"

    def get_model_path(self, horizon: int, model_name: str) -> Path:
        return MODELS_DIR / f"{self.name}_{horizon}bar_{model_name}.joblib"

    def get_results_path(self, horizon: int) -> Path:
        return RESULTS_DIR / f"{self.name}_{horizon}bar_results.csv"


# =============================================================================
# TARGET REGISTRY
# =============================================================================
TARGETS = {
    "volatility": TargetConfig(
        name="volatility",
        task_type="regression",
        target_column_pattern="y_volatility",  # Same column for all horizons
        primary_metric="rmse",
        secondary_metrics=["mae", "r2", "ic"],
    ),
    "direction": TargetConfig(
        name="direction",
        task_type="binary",
        target_column_pattern="y_direction",
        primary_metric="auc",
        secondary_metrics=["accuracy", "f1", "log_loss"],
    ),
    "returns": TargetConfig(
        name="returns",
        task_type="regression",
        target_column_pattern="y_returns",
        primary_metric="rmse",
        secondary_metrics=["mae", "r2", "ic"],
    ),
    "vol_regime": TargetConfig(
        name="vol_regime",
        task_type="multiclass",
        target_column_pattern="y_vol_regime",
        primary_metric="accuracy",
        secondary_metrics=["f1_macro", "log_loss"],
    ),
    "trend_regime": TargetConfig(
        name="trend_regime",
        task_type="binary",
        target_column_pattern="y_trend_regime",
        primary_metric="auc",
        secondary_metrics=["accuracy", "f1"],
    ),
}


# =============================================================================
# CV CONFIGURATION
# =============================================================================
@dataclass
class CVConfig:
    """Cross-validation configuration with temporal awareness."""

    n_splits: int = 5
    purge_gap: int = 21  # Bars to purge before test (max feature lookback)
    embargo_gap: int = 12  # Bars to embargo after test (max target horizon)
    test_size: float = 0.2  # For final holdout


# =============================================================================
# MODEL HYPERPARAMETER SPACES
# =============================================================================
CATBOOST_SPACE = {
    "iterations": [500, 1000, 2000],
    "depth": [4, 6, 8],
    "learning_rate": [0.01, 0.03, 0.1],
    "l2_leaf_reg": [1, 3, 10],
    "random_strength": [0.5, 1, 2],
}

LIGHTGBM_SPACE = {
    "n_estimators": [500, 1000, 2000],
    "max_depth": [4, 6, 8, -1],
    "learning_rate": [0.01, 0.03, 0.1],
    "reg_lambda": [0, 1, 10],
    "num_leaves": [15, 31, 63],
}

RIDGE_SPACE = {
    "alpha": [0.001, 0.01, 0.1, 1, 10, 100],
}
