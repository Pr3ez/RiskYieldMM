"""
Helper Selection Module.

Provides task-type aware helper selection for the 20 target-horizons.

Different target types benefit from different helper combinations:
- Regression (volatility, returns): All helpers useful
- Binary (direction, trend_regime): Regime helpers most important
- Multiclass (vol_regime): Volatility-focused helpers

This module centralizes the logic for selecting appropriate helpers
based on target characteristics.
"""

from typing import Literal

from scripts.target_models.helpers.base import BaseHelper, HelperConfig
from scripts.target_models.helpers.cusum import CUSUMConfig, CUSUMHelper
from scripts.target_models.helpers.garch import GARCHConfig, GARCHHelper
from scripts.target_models.helpers.hmm import (
    create_market_regime_hmm,
    create_volatility_regime_hmm,
)
from scripts.target_models.helpers.isolation_forest import (
    IsolationForestConfig,
    IsolationForestHelper,
)
from scripts.target_models.helpers.kalman import KalmanHelper

# =============================================================================
# HELPER PROFILES
# =============================================================================
# Define which helpers are useful for each task type

HELPER_PROFILES = {
    "regression": {
        # Volatility and returns prediction benefit from all helpers
        "hmm4": True,  # Market regime detection
        "hmm5": True,  # Volatility regime detection
        "garch": True,  # Volatility clustering
        "if": True,  # Anomaly detection
        "kalman": True,  # State estimation
        "cusum": True,  # Change point detection
        # New helpers
        "evt": True,  # Tail risk estimation
        "ou": True,  # Mean reversion strength
        "bocpd": True,  # Bayesian changepoint detection
        "egarch": True,  # Asymmetric volatility
    },
    "binary": {
        # Direction/trend prediction - focus on regime detection
        "hmm4": True,  # Market regime is key
        "hmm5": True,  # Volatility regimes affect direction
        "garch": True,  # Volatility timing
        "if": True,  # Anomalies often precede moves
        "kalman": True,  # Trend estimation
        "cusum": True,  # Regime changes
        # New helpers
        "evt": True,  # Tail risk informs direction
        "ou": True,  # Mean reversion for timing
        "bocpd": True,  # Changepoints for regime shifts
        "egarch": True,  # Leverage effect
    },
    "multiclass": {
        # Vol_regime prediction - volatility-focused
        "hmm4": False,  # Market regime less useful
        "hmm5": True,  # Volatility regime is key
        "garch": True,  # Volatility is the target
        "if": True,  # Anomaly detection
        "kalman": True,  # Level/trend estimation
        "cusum": True,  # Volatility regime changes
        # New helpers
        "evt": True,  # Tail risk for vol regime
        "ou": False,  # Less useful for vol regime
        "bocpd": True,  # Regime changes
        "egarch": True,  # Asymmetric vol for regime
    },
}

# Target-specific overrides
TARGET_OVERRIDES = {
    # Volatility targets benefit most from volatility-focused helpers
    "volatility": {
        "hmm5": True,  # Primary
        "garch": True,  # Primary
    },
    # Returns/direction benefit from all
    "returns": {},
    "direction": {},
    # Regime targets need regime detection
    "vol_spike": {
        "hmm4": False,  # Not useful for vol spike
    },
    "trend_regime": {
        "hmm4": True,  # Market regime is key for trend
    },
}


# =============================================================================
# HELPER FACTORY FUNCTIONS
# =============================================================================
def get_helpers_for_target(
    target: str,
    horizon: int,
    task_type: Literal["regression", "binary", "multiclass"],
    random_state: int = 42,
) -> dict[str, "BaseHelper"]:
    """
    Get appropriate helpers for a target-horizon combination.

    Args:
        target: Target name (volatility, returns, direction, vol_regime, trend_regime)
        horizon: Prediction horizon (1, 3, 6, 12)
        task_type: Task type (regression, binary, multiclass)
        random_state: Random seed for reproducibility

    Returns:
        Dict mapping helper name to helper instance
    """
    # Get base profile for task type
    profile = HELPER_PROFILES.get(task_type, HELPER_PROFILES["regression"]).copy()

    # Apply target-specific overrides
    if target in TARGET_OVERRIDES:
        for helper_name, enabled in TARGET_OVERRIDES[target].items():
            profile[helper_name] = enabled

    # Build helper instances
    helpers = {}
    base_config = HelperConfig(
        target=target,
        horizon=horizon,
        task_type=task_type,
        random_state=random_state,
    )

    if profile.get("hmm4", False):
        helpers["hmm4"] = create_market_regime_hmm(target, horizon, random_state)

    if profile.get("hmm5", False):
        helpers["hmm5"] = create_volatility_regime_hmm(target, horizon, random_state)

    if profile.get("garch", False):
        garch_config = GARCHConfig(
            target=target,
            horizon=horizon,
            task_type=task_type,
            random_state=random_state,
            forecast_horizon=horizon,  # Match prediction horizon
        )
        helpers["garch"] = GARCHHelper(garch_config)

    if profile.get("if", False):
        if_config = IsolationForestConfig(
            target=target,
            horizon=horizon,
            task_type=task_type,
            random_state=random_state,
        )
        helpers["if"] = IsolationForestHelper(if_config)

    if profile.get("kalman", False):
        helpers["kalman"] = KalmanHelper(base_config)

    if profile.get("cusum", False):
        cusum_config = CUSUMConfig(
            target=target,
            horizon=horizon,
            task_type=task_type,
            random_state=random_state,
        )
        helpers["cusum"] = CUSUMHelper(cusum_config)

    return helpers


def get_helper_summary(
    target: str,
    horizon: int,
    task_type: Literal["regression", "binary", "multiclass"],
) -> dict[str, bool]:
    """
    Get summary of which helpers are enabled for a target.

    Args:
        target: Target name
        horizon: Prediction horizon
        task_type: Task type

    Returns:
        Dict mapping helper name to enabled status
    """
    profile = HELPER_PROFILES.get(task_type, HELPER_PROFILES["regression"]).copy()

    if target in TARGET_OVERRIDES:
        for helper_name, enabled in TARGET_OVERRIDES[target].items():
            profile[helper_name] = enabled

    return profile


def get_incremental_helpers(
    target: str,
    horizon: int,
    task_type: Literal["regression", "binary", "multiclass"],
    random_state: int = 42,
) -> tuple[dict[str, "BaseHelper"], dict[str, "BaseHelper"]]:
    """
    Get helpers split by incremental capability.

    Args:
        target: Target name
        horizon: Prediction horizon
        task_type: Task type
        random_state: Random seed

    Returns:
        Tuple of (incremental_helpers, full_refit_helpers)
    """
    all_helpers = get_helpers_for_target(target, horizon, task_type, random_state)

    incremental = {}
    full_refit = {}

    for name, helper in all_helpers.items():
        if helper.supports_incremental:
            incremental[name] = helper
        else:
            full_refit[name] = helper

    return incremental, full_refit


# =============================================================================
# SUMMARY UTILITIES
# =============================================================================
def print_helper_matrix():
    """Print matrix of helpers enabled per target type."""
    from scripts.target_models.registry import ALL_TARGETS

    print("=" * 70)
    print("HELPER SELECTION MATRIX")
    print("=" * 70)
    print()

    # Header
    helpers = ["hmm4", "hmm5", "garch", "if", "kalman", "cusum"]
    header = f"{'Target':<15}" + "".join(f"{h:>8}" for h in helpers)
    print(header)
    print("-" * len(header))

    # Task type mapping
    task_types = {
        "volatility": "regression",
        "returns": "regression",
        "direction": "binary",
        "vol_spike": "binary",
        "trend_regime": "binary",
    }

    for target in ALL_TARGETS:
        task_type = task_types[target]
        profile = get_helper_summary(target, 1, task_type)
        row = f"{target:<15}"
        for h in helpers:
            enabled = profile.get(h, False)
            row += f"{'✓':>8}" if enabled else f"{'-':>8}"
        print(row)

    print()
    print("Incremental support: HMM4 ✓, HMM5 ✓, IF ✓, Kalman ✓, GARCH ✗, CUSUM ✗")


if __name__ == "__main__":
    print_helper_matrix()
