"""
Adaptive Conformal Inference (ACI) for dynamic alpha adjustment.

Based on Zaffran et al. (2022) - Adaptive Conformal Predictions for Time Series.

ACI maintains coverage during distribution shifts by adjusting alpha
based on observed error rates. Uses batch-level updates (not per-sample).
"""

import numpy as np


class AdaptiveConformalInference:
    """
    Adaptive Conformal Inference for dynamic coverage maintenance.

    Adjusts alpha (miscoverage rate) based on observed coverage to maintain
    target coverage even under distribution shift.

    Formula: α_{t+1} = α_t + γ(α_target - error_rate_t)

    Attributes:
        alpha: Current miscoverage rate
        alpha_target: Target miscoverage rate
        gamma: Learning rate for updates (higher = more responsive)
        alpha_min: Minimum alpha bound
        alpha_max: Maximum alpha bound
        history: History of alpha values

    Example:
        >>> aci = AdaptiveConformalInference(alpha_target=0.10, gamma=0.04)
        >>> # After each prediction batch:
        >>> coverage = 0.85  # Observed coverage
        >>> aci.update_batch(1 - coverage)  # Pass error rate
        >>> next_conf = aci.confidence_level  # Use for next batch
    """

    def __init__(
        self,
        alpha_target: float = 0.10,
        gamma: float = 0.04,
        alpha_min: float = 0.02,
        alpha_max: float = 0.30,
    ):
        """
        Initialize ACI.

        Args:
            alpha_target: Target miscoverage rate (default 0.10 for 90% coverage)
            gamma: Learning rate (0.04 conservative, 0.10 responsive)
            alpha_min: Minimum alpha to prevent overconfidence
            alpha_max: Maximum alpha to prevent extreme uncertainty
        """
        if not 0.01 <= alpha_target <= 0.50:
            raise ValueError(
                f"alpha_target must be in [0.01, 0.50], got {alpha_target}"
            )
        if not 0.001 <= gamma <= 0.50:
            raise ValueError(f"gamma must be in [0.001, 0.50], got {gamma}")

        self.alpha = alpha_target
        self.alpha_target = alpha_target
        self.gamma = gamma
        self.alpha_min = alpha_min
        self.alpha_max = alpha_max
        self.history: list[float] = [alpha_target]
        self._error_history: list[float] = []

    def update_batch(self, error_rate: float) -> None:
        """
        Update alpha based on batch error rate.

        Call after each prediction batch with the observed error rate
        (fraction of samples not covered).

        Args:
            error_rate: Fraction of samples not covered (1 - coverage)
        """
        if not 0.0 <= error_rate <= 1.0:
            raise ValueError(f"error_rate must be in [0, 1], got {error_rate}")

        # ACI update formula
        self.alpha = self.alpha + self.gamma * (self.alpha_target - error_rate)
        self.alpha = np.clip(self.alpha, self.alpha_min, self.alpha_max)

        self.history.append(self.alpha)
        self._error_history.append(error_rate)

    def update_from_coverage(self, coverage: float) -> None:
        """
        Convenience method to update from coverage instead of error rate.

        Args:
            coverage: Fraction of samples covered (in [0, 1])
        """
        self.update_batch(1.0 - coverage)

    @property
    def confidence_level(self) -> float:
        """Current confidence level (1 - alpha)."""
        return 1.0 - self.alpha

    @property
    def coverage_target(self) -> float:
        """Target coverage (1 - alpha_target)."""
        return 1.0 - self.alpha_target

    def reset(self) -> None:
        """Reset alpha to target and clear history."""
        self.alpha = self.alpha_target
        self.history = [self.alpha_target]
        self._error_history = []

    def get_diagnostics(self) -> dict:
        """
        Get diagnostic information about ACI state.

        Returns:
            Dictionary with alpha trajectory, error history, and statistics.
        """
        return {
            "current_alpha": self.alpha,
            "alpha_target": self.alpha_target,
            "gamma": self.gamma,
            "n_updates": len(self._error_history),
            "alpha_history": self.history.copy(),
            "error_history": self._error_history.copy(),
            "mean_error": np.mean(self._error_history) if self._error_history else None,
            "alpha_range": (min(self.history), max(self.history)),
        }

    def __repr__(self) -> str:
        return (
            f"AdaptiveConformalInference("
            f"alpha={self.alpha:.3f}, "
            f"target={self.alpha_target:.3f}, "
            f"gamma={self.gamma:.3f}, "
            f"updates={len(self._error_history)})"
        )
