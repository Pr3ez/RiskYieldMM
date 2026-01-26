"""
Core Ensemble Module

Contains ensemble weight computation and adaptive weight tracking:
- AdaptiveWeightTracker: Tracks per-model accuracies and computes adaptive weights
- compute_sample_weights: Exponential decay sample weighting for concept drift
- update_adaptive_weights: MWU algorithm for weight updates

Based on:
- arXiv 2304.09947 "Online Ensemble Learning for Sector Rotation"
- de Prado (2018) "Advances in Financial Machine Learning"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


def compute_sample_weights(
    n_samples: int,
    halflife_fraction: float = 0.3,
) -> np.ndarray:
    """Compute exponential decay sample weights.

    Based on research from:
    - de Prado (2018) "Advances in Financial Machine Learning"
    - arXiv 2103.14079 "Domain Specific Concept Drift Detectors"

    Recent samples get higher weights, older samples decay exponentially.

    Args:
        n_samples: Number of training samples
        halflife_fraction: Fraction of window where weight decays to 50%
                          e.g., 0.3 means at 70% through the window, weight = 50%

    Returns:
        Array of sample weights, normalized to sum to n_samples
    """
    if n_samples <= 0:
        return np.array([])

    # Halflife in samples (from the end)
    halflife = int(n_samples * halflife_fraction)
    halflife = max(halflife, 1)  # At least 1

    # Create time indices (0 = oldest, n_samples-1 = newest)
    t = np.arange(n_samples)

    # Exponential decay: w(t) = 2^((t - n_samples) / halflife)
    # At t = n_samples - halflife: w = 0.5
    # At t = n_samples - 1: w = ~1.0
    weights = np.power(2.0, (t - n_samples + 1) / halflife)

    # Normalize so weights sum to n_samples (equivalent to uniform mean)
    weights = weights * (n_samples / weights.sum())

    return weights


def update_adaptive_weights(
    current_weights: dict[str, float],
    recent_accuracies: dict[str, list[float]],
    learning_rate: float = 0.1,
    min_weight: float = 0.05,
) -> dict[str, float]:
    """Update ensemble weights using Multiplicative Weights Update algorithm.

    Based on arXiv 2304.09947 "Online Ensemble Learning for Sector Rotation"
    and standard MWU theory (Freund & Schapire).

    Models with better recent performance get higher weights.

    Args:
        current_weights: Current model weights (cb, lgb, lstm, linear)
        recent_accuracies: Dict of model_name -> list of recent correct predictions (0/1)
        learning_rate: How fast to adjust (eta in MWU)
        min_weight: Minimum weight to prevent zeroing out

    Returns:
        Updated weights dictionary
    """
    models = ["cb", "lgb", "lstm", "linear"]

    # Compute recent accuracy for each model
    model_scores = {}
    for model in models:
        accs = recent_accuracies.get(model, [])
        if len(accs) > 0:
            # Recent accuracy (0 to 1)
            model_scores[model] = np.mean(accs)
        else:
            # No data yet, use neutral score
            model_scores[model] = 0.5

    # MWU update: w_new = w_old * exp(eta * reward)
    # Reward = accuracy - 0.5 (centered so random = 0)
    new_weights = {}
    for model in models:
        reward = model_scores[model] - 0.5  # -0.5 to +0.5
        old_w = current_weights.get(f"{model}_weight", 0.25)
        new_w = old_w * np.exp(learning_rate * reward)
        new_weights[f"{model}_weight"] = new_w

    # Normalize to sum to 1.0
    total = sum(new_weights.values())
    for model in models:
        key = f"{model}_weight"
        new_weights[key] = new_weights[key] / total
        # Apply minimum weight constraint
        new_weights[key] = max(new_weights[key], min_weight)

    # Re-normalize after applying minimums
    total = sum(new_weights.values())
    for model in models:
        key = f"{model}_weight"
        new_weights[key] = new_weights[key] / total

    return new_weights


@dataclass
class AdaptiveWeightTracker:
    """Tracks per-model prediction accuracy and computes adaptive ensemble weights.

    This class manages the state needed for adaptive ensemble weighting:
    - Stores recent predictions for each model
    - Computes current weights based on recent accuracy
    - Provides weights for ensemble prediction

    Usage:
        tracker = AdaptiveWeightTracker(lookback=50, learning_rate=0.1)

        # After each prediction step:
        tracker.record_accuracy("cb", y_true == cb_pred)
        tracker.record_accuracy("lgb", y_true == lgb_pred)
        ...

        # Get current weights for ensemble:
        weights = tracker.get_weights()  # {"cb_weight": 0.28, "lgb_weight": 0.32, ...}

    References:
        - arXiv 2304.09947 "Online Ensemble Learning for Sector Rotation"
        - Freund & Schapire (1997) "A Decision-Theoretic Generalization of On-Line Learning"
    """

    # Configuration
    lookback: int = 50  # Number of recent predictions to consider
    learning_rate: float = 0.1  # MWU learning rate (eta)
    min_weight: float = 0.05  # Minimum weight per model

    # Initial weights (will be updated adaptively)
    initial_cb_weight: float = 0.30
    initial_lgb_weight: float = 0.30
    initial_lstm_weight: float = 0.25
    initial_linear_weight: float = 0.15

    # State (mutable)
    _recent_correct: dict[str, list[bool]] = field(default_factory=dict)
    _current_weights: dict[str, float] = field(default_factory=dict)
    _n_updates: int = 0

    def __post_init__(self):
        """Initialize tracking state."""
        # Initialize empty history for each model
        self._recent_correct = {
            "cb": [],
            "lgb": [],
            "lstm": [],
            "linear": [],
        }
        # Initialize weights from config
        self._current_weights = {
            "cb_weight": self.initial_cb_weight,
            "lgb_weight": self.initial_lgb_weight,
            "lstm_weight": self.initial_lstm_weight,
            "linear_weight": self.initial_linear_weight,
        }
        self._n_updates = 0

    def record_accuracy(self, model: str, correct: bool | int) -> None:
        """Record whether a model's prediction was correct.

        Args:
            model: Model name ("cb", "lgb", "lstm", "linear")
            correct: Whether prediction was correct (True/1 or False/0)
        """
        if model not in self._recent_correct:
            self._recent_correct[model] = []

        # Convert to bool and append
        self._recent_correct[model].append(bool(correct))

        # Trim to lookback window
        if len(self._recent_correct[model]) > self.lookback:
            self._recent_correct[model] = self._recent_correct[model][-self.lookback :]

    def update_weights(self) -> dict[str, float]:
        """Update weights based on recent accuracy using MWU algorithm.

        Call this after recording accuracies for all models in a step.

        Returns:
            Updated weights dictionary
        """
        # Convert bool lists to float lists for update function
        recent_accs = {
            model: [float(c) for c in correct_list]
            for model, correct_list in self._recent_correct.items()
        }

        # Apply MWU update
        self._current_weights = update_adaptive_weights(
            self._current_weights,
            recent_accs,
            self.learning_rate,
            self.min_weight,
        )
        self._n_updates += 1

        return self._current_weights.copy()

    def get_weights(self) -> dict[str, float]:
        """Get current ensemble weights.

        Returns:
            Current weights: {"cb_weight": float, "lgb_weight": float, ...}
        """
        return self._current_weights.copy()

    def get_weight(self, model: str) -> float:
        """Get weight for a specific model.

        Args:
            model: Model name ("cb", "lgb", "lstm", "linear")

        Returns:
            Current weight for the model
        """
        return self._current_weights.get(f"{model}_weight", 0.25)

    def get_stats(self) -> dict[str, Any]:
        """Get tracking statistics for debugging/logging.

        Returns:
            Dict with recent accuracies, current weights, and update count
        """
        # Compute recent accuracy for each model
        recent_acc = {}
        for model, correct_list in self._recent_correct.items():
            if len(correct_list) > 0:
                recent_acc[f"{model}_recent_acc"] = np.mean(correct_list)
                recent_acc[f"{model}_n_samples"] = len(correct_list)
            else:
                recent_acc[f"{model}_recent_acc"] = None
                recent_acc[f"{model}_n_samples"] = 0

        return {
            "n_updates": self._n_updates,
            "lookback": self.lookback,
            **self._current_weights,
            **recent_acc,
        }

    def reset(self) -> None:
        """Reset tracker to initial state."""
        self.__post_init__()


def compute_ensemble_prediction(
    predictions: dict[str, Any],
    weights: dict[str, float],
    task_type: str = "classification",
) -> Any:
    """Compute weighted ensemble prediction from individual model predictions.

    Args:
        predictions: Dict mapping model name to prediction
                    For classification: {"cb": 1, "lgb": 2, "lstm": 1, "linear": 0}
                    For regression: {"cb": 0.5, "lgb": 0.6, "lstm": 0.4, "linear": 0.7}
        weights: Dict with model weights (cb_weight, lgb_weight, etc.)
        task_type: "classification" or "regression"

    Returns:
        Ensemble prediction (class label for classification, float for regression)
    """
    models = ["cb", "lgb", "lstm", "linear"]

    if task_type == "regression":
        # Weighted average for regression
        weighted_sum = 0.0
        total_weight = 0.0
        for model in models:
            if model in predictions:
                w = weights.get(f"{model}_weight", 0.25)
                weighted_sum += w * predictions[model]
                total_weight += w
        if total_weight > 0:
            return weighted_sum / total_weight
        return np.mean([predictions[m] for m in models if m in predictions])

    else:
        # Weighted voting for classification
        # Collect all predictions and their weights
        vote_weights = {}
        for model in models:
            if model in predictions:
                pred = predictions[model]
                w = weights.get(f"{model}_weight", 0.25)
                if pred not in vote_weights:
                    vote_weights[pred] = 0.0
                vote_weights[pred] += w

        # Return class with highest weighted vote
        if vote_weights:
            return max(vote_weights, key=lambda k: vote_weights[k])
        return predictions.get("cb", 0)  # Fallback


# Exports
__all__ = [
    "compute_sample_weights",
    "update_adaptive_weights",
    "AdaptiveWeightTracker",
    "compute_ensemble_prediction",
]
