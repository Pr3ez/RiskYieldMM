"""
Multi-Level Isolation Forest Helper.

Three Isolation Forest models with different contamination levels
for hierarchical anomaly detection:
- Extreme (1%): High precision, most severe anomalies
- Moderate (5%): Balanced detection
- Mild (10%): High recall, sensitive detection

Features Generated (~10 per target-horizon):
- Per level: anomaly_score, is_anomaly, severity
- Aggregates: mean_score, max_score, n_anomalies, any_severe
"""

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from sklearn.ensemble import IsolationForest

from .base import BaseHelper, HelperConfig


# =============================================================================
# CONFIGURATION
# =============================================================================
@dataclass
class IsolationForestConfig(HelperConfig):
    """Configuration specific to Isolation Forest helper."""

    # Contamination levels for 3-tier detection
    contamination_extreme: float = 0.01  # 1% — high precision
    contamination_moderate: float = 0.05  # 5% — balanced
    contamination_mild: float = 0.10  # 10% — high recall

    # IsolationForest params
    n_estimators: int = 100
    max_samples: str | int = "auto"
    max_features: float = 1.0
    bootstrap: bool = False

    # Feature subset control (optional)
    use_all_features: bool = True
    feature_groups: list[str] = field(default_factory=list)  # If not all


# =============================================================================
# ISOLATION FOREST HELPER
# =============================================================================
class IsolationForestHelper(BaseHelper):
    """
    Multi-level Isolation Forest for anomaly detection.

    Trains 3 separate models with different contamination levels
    to capture anomalies at different severity thresholds.

    Supports incremental training via warm_start=True.

    Features generated:
    - H_{prefix}_if_extreme_score: Anomaly score from extreme model
    - H_{prefix}_if_extreme_is: Binary anomaly flag (extreme)
    - H_{prefix}_if_extreme_severity: Normalized severity (extreme)
    - H_{prefix}_if_moderate_score: Anomaly score from moderate model
    - H_{prefix}_if_moderate_is: Binary anomaly flag (moderate)
    - H_{prefix}_if_moderate_severity: Normalized severity (moderate)
    - H_{prefix}_if_mild_score: Anomaly score from mild model
    - H_{prefix}_if_mild_is: Binary anomaly flag (mild)
    - H_{prefix}_if_mild_severity: Normalized severity (mild)
    - H_{prefix}_if_mean_score: Mean score across all levels
    - H_{prefix}_if_max_severity: Max severity across levels
    - H_{prefix}_if_n_anomalies: Count of levels detecting anomaly
    """

    def __init__(self, config: IsolationForestConfig | None = None):
        super().__init__(config or IsolationForestConfig())
        self.config: IsolationForestConfig  # Type hint for IDE

        # Models for each level
        self._models: dict[str, IsolationForest] = {}
        self._levels = ["extreme", "moderate", "mild"]

        # Normalization stats (for severity scores)
        self._score_mins: dict[str, float] = {}
        self._score_maxs: dict[str, float] = {}

        # Incremental settings
        self._incremental_n_estimators = 20  # Add 20 trees per update

    @property
    def supports_incremental(self) -> bool:
        """IsolationForest supports incremental via warm_start."""
        return True

    @property
    def helper_name(self) -> str:
        return "isolation_forest"

    def _fit_impl(self, X: np.ndarray, y: np.ndarray | None = None) -> None:
        """
        Fit 3 Isolation Forest models at different contamination levels.

        Args:
            X: Feature matrix (n_samples, n_features)
            y: Ignored (unsupervised)
        """
        contaminations = {
            "extreme": self.config.contamination_extreme,
            "moderate": self.config.contamination_moderate,
            "mild": self.config.contamination_mild,
        }

        for level, contamination in contaminations.items():
            model = IsolationForest(
                n_estimators=self.config.n_estimators,
                max_samples=self.config.max_samples,
                max_features=self.config.max_features,
                contamination=contamination,
                bootstrap=self.config.bootstrap,
                random_state=self.config.random_state,
                n_jobs=-1,
            )
            model.fit(X)
            self._models[level] = model

            # Compute normalization stats on training data
            scores = model.decision_function(X)
            self._score_mins[level] = float(np.min(scores))
            self._score_maxs[level] = float(np.max(scores))

        # Store fit params
        self._fit_params = {
            "n_samples": X.shape[0],
            "n_features": X.shape[1],
            "contaminations": contaminations,
        }

        if self.config.verbose:
            print(f"IsolationForestHelper fitted on {X.shape}")
            for level in self._models:
                print(f"  {level}: contamination={contaminations[level]}")

    def _partial_fit_impl(
        self,
        X: np.ndarray,
        y: np.ndarray | None,
        n_samples_seen: int,
    ) -> None:
        """Incrementally update IsolationForest with warm_start.

        Adds more trees to existing models rather than retraining from scratch.

        Args:
            X: Full feature matrix
            y: Ignored (unsupervised)
            n_samples_seen: Number of samples from previous fit
        """
        if not self._models:
            # No existing models, do full fit
            self._fit_impl(X, y)
            return

        contaminations = {
            "extreme": self.config.contamination_extreme,
            "moderate": self.config.contamination_moderate,
            "mild": self.config.contamination_mild,
        }

        for level, _contamination in contaminations.items():
            model = self._models[level]

            # Enable warm_start and increase n_estimators
            model.warm_start = True
            current_n_estimators = model.n_estimators
            model.n_estimators = current_n_estimators + self._incremental_n_estimators

            # Refit with warm_start (adds trees, doesn't retrain existing)
            model.fit(X)

            # Update normalization stats
            scores = model.decision_function(X)
            self._score_mins[level] = float(np.min(scores))
            self._score_maxs[level] = float(np.max(scores))

        # Update fit params
        self._fit_params["n_samples"] = X.shape[0]

    def _transform_impl(self, X: np.ndarray) -> np.ndarray:
        """
        Generate anomaly detection features.

        Args:
            X: Feature matrix (n_samples, n_features)

        Returns:
            Feature matrix (n_samples, 12) with anomaly features
        """
        n_samples = X.shape[0]

        # Storage for features
        features = []

        # Per-level features
        for level in self._levels:
            model = self._models[level]

            # Raw anomaly score (higher = more normal)
            scores = model.decision_function(X)

            # Binary prediction (-1 = anomaly, 1 = normal)
            predictions = model.predict(X)
            is_anomaly = (predictions == -1).astype(np.float32)

            # Normalized severity (0 = normal, 1 = most anomalous)
            # Invert scores so higher = more anomalous
            score_min = self._score_mins[level]
            score_max = self._score_maxs[level]
            score_range = score_max - score_min
            if score_range > 1e-8:
                severity = (score_max - scores) / score_range
            else:
                severity = np.zeros(n_samples)
            severity = np.clip(severity, 0, 1)

            features.extend([scores, is_anomaly, severity])

        # Aggregate features
        all_scores = np.column_stack(features[::3])  # Every 3rd starting from 0
        all_is_anomaly = np.column_stack(features[1::3])  # Every 3rd starting from 1
        all_severity = np.column_stack(features[2::3])  # Every 3rd starting from 2

        mean_score = np.mean(all_scores, axis=1)
        max_severity = np.max(all_severity, axis=1)
        n_anomalies = np.sum(all_is_anomaly, axis=1)

        features.extend([mean_score, max_severity, n_anomalies])

        return np.column_stack(features)

    def _get_feature_names(self) -> list[str]:
        """Get feature names with proper prefix."""
        names = []

        # Per-level features
        for level in self._levels:
            names.extend(
                [
                    self._make_feature_name(f"if_{level}_score"),
                    self._make_feature_name(f"if_{level}_is"),
                    self._make_feature_name(f"if_{level}_severity"),
                ]
            )

        # Aggregate features
        names.extend(
            [
                self._make_feature_name("if_mean_score"),
                self._make_feature_name("if_max_severity"),
                self._make_feature_name("if_n_anomalies"),
            ]
        )

        return names

    def optimize(
        self,
        X_cal: np.ndarray,
        y_cal: np.ndarray | None = None,
    ) -> dict[str, Any]:
        """
        Optimize contamination levels based on calibration data.

        For now, keeps default levels. Future: could tune based on
        validation metrics or target correlation.
        """
        # Re-compute normalization stats on combined train+cal
        for level, model in self._models.items():
            scores = model.decision_function(X_cal)
            # Update running stats (simple max extension)
            self._score_mins[level] = min(
                self._score_mins[level], float(np.min(scores))
            )
            self._score_maxs[level] = max(
                self._score_maxs[level], float(np.max(scores))
            )

        return {
            "score_mins": self._score_mins.copy(),
            "score_maxs": self._score_maxs.copy(),
        }

    def validate(
        self,
        X_val: np.ndarray,
        y_val: np.ndarray | None = None,
    ) -> dict[str, float]:
        """
        Compute validation metrics for anomaly detection quality.

        Returns detection rates at each level.
        """
        metrics = {}

        for level, model in self._models.items():
            predictions = model.predict(X_val)
            anomaly_rate = np.mean(predictions == -1)
            metrics[f"anomaly_rate_{level}"] = float(anomaly_rate)

        return metrics

    def get_params(self) -> dict[str, Any]:
        """Get detailed parameters."""
        return {
            **super().get_params(),
            "contamination_extreme": self.config.contamination_extreme,
            "contamination_moderate": self.config.contamination_moderate,
            "contamination_mild": self.config.contamination_mild,
            "n_estimators": self.config.n_estimators,
        }


# =============================================================================
# FACTORY
# =============================================================================
def create_isolation_forest_helper(
    target: str,
    horizon: int,
    task_type: str = "regression",
    **kwargs,
) -> IsolationForestHelper:
    """
    Create IsolationForestHelper for a specific target-horizon.

    Args:
        target: Target name (volatility, direction, etc.)
        horizon: Prediction horizon (1, 3, 6, 12)
        task_type: Task type (regression, binary, multiclass)
        **kwargs: Additional config overrides

    Returns:
        Configured IsolationForestHelper
    """
    config = IsolationForestConfig(
        target=target,
        horizon=horizon,
        task_type=task_type,
        prefix=f"{target[:3]}_{horizon}",
        **kwargs,
    )
    return IsolationForestHelper(config)
