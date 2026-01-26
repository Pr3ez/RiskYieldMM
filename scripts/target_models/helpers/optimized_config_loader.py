"""
Optimized Config Loader for L2 Pipeline.

Loads optimized hyperparameters from L2 optimization results.
Only applies optimized configs where improvement was positive.
Falls back to defaults for configs that degraded during optimization.

Usage:
    from scripts.target_models.helpers.optimized_config_loader import (
        get_optimized_icir_config,
        get_optimized_model_params,
        get_optimized_l2_params,
        IMPROVED_CONFIGS,
    )

    # Get ICIR config (optimized if improved, else default)
    icir_config = get_optimized_icir_config("volatility", 12)

    # Get model hyperparameters
    model_params = get_optimized_model_params("volatility", 12)

    # Get L2 window parameters
    l2_params = get_optimized_l2_params("volatility", 12)
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .icir_config import DEFAULT_ICIR_CONFIG, ICIRConfig

# Path to optimization results
OPTIMIZATION_RESULTS_DIR = (
    Path(__file__).parent.parent.parent.parent / "data" / "l2_optimization" / "results"
)

# Configs that IMPROVED during optimization (apply optimized params)
# Based on summary.csv results - only configs with improvement_pct > 0
IMPROVED_CONFIGS: set[str] = {
    "direction_1bar",  # +5.7%
    "direction_3bar",  # +0.3%
    "returns_1bar",  # +332.3%
    "returns_12bar",  # +97.7%
    "volatility_3bar",  # +9.5%
    "volatility_6bar",  # +382.8%
    "volatility_12bar",  # +576.1%
    "vol_spike_1bar",  # +0.3%
    "vol_spike_3bar",  # +0.3%
    "vol_spike_6bar",  # +0.3%
}

# Configs that DEGRADED during optimization (keep defaults)
# direction_6bar (-4.2%), direction_12bar (-5.9%)
# returns_3bar (-24.9%), returns_6bar (-67.7%)
# volatility_1bar (-17.7%)
# vol_spike_12bar (-5.2%)
# trend_regime_1bar (-2.0%), trend_regime_3bar (-2.0%), trend_regime_6bar (-1.8%), trend_regime_12bar (+0.0%)


@dataclass
class OptimizedModelParams:
    """Optimized model hyperparameters."""

    # CatBoost
    cb_iterations: int = 200
    cb_depth: int = 5
    cb_learning_rate: float = 0.05
    cb_l2_leaf_reg: float = 1.0

    # LightGBM
    lgb_n_estimators: int = 200
    lgb_max_depth: int = 5
    lgb_learning_rate: float = 0.05
    lgb_reg_lambda: float = 1.0

    # Ensemble weights
    cb_weight: float = 0.5
    lgb_weight: float = 0.5


@dataclass
class OptimizedL2Params:
    """Optimized L2 window parameters."""

    l2_window_size: int = 300
    train_ratio: float = 0.7
    purge_gap: int = 12


def _load_optimized_params(target: str, horizon: int) -> dict[str, Any] | None:
    """Load optimized params from JSON file.

    Args:
        target: Target name (e.g., "volatility", "direction")
        horizon: Forecast horizon (1, 3, 6, 12)

    Returns:
        Dict with best_params if file exists and config improved, else None
    """
    config_key = f"{target}_{horizon}bar"

    # Only load if this config improved
    if config_key not in IMPROVED_CONFIGS:
        return None

    json_path = OPTIMIZATION_RESULTS_DIR / f"{config_key}_best.json"
    if not json_path.exists():
        return None

    try:
        with open(json_path) as f:
            data = json.load(f)

        # Verify improvement is positive
        if data.get("improvement_pct", 0) <= 0:
            return None

        return data.get("best_params", {})
    except (json.JSONDecodeError, KeyError):
        return None


def get_optimized_icir_config(target: str, horizon: int) -> ICIRConfig:
    """Get ICIR config for a target-horizon.

    Returns optimized config if optimization improved performance,
    otherwise returns default config.

    Args:
        target: Target name (e.g., "volatility", "direction")
        horizon: Forecast horizon (1, 3, 6, 12)

    Returns:
        ICIRConfig - optimized if improved, else default
    """
    params = _load_optimized_params(target, horizon)

    if params is None:
        return DEFAULT_ICIR_CONFIG

    # Build ICIRConfig from optimized params
    return ICIRConfig(
        enable_icir=True,
        enable_correlation_filter=True,
        icir_threshold=params.get("icir_threshold", 0.3),
        n_rolling_windows=params.get("n_rolling_windows", 5),
        correlation_threshold=params.get("correlation_threshold", 0.90),
        min_window_size=50,  # Keep default
        min_valid_windows=3,  # Keep default
        correlation_method="pearson",
        fallback_to_ic=True,
        fallback_ic_threshold=0.02,
        top_k_interactions=5,
        verbose=False,
    )


def get_optimized_model_params(target: str, horizon: int) -> OptimizedModelParams:
    """Get model hyperparameters for a target-horizon.

    Returns optimized params if optimization improved performance,
    otherwise returns default params.

    Args:
        target: Target name (e.g., "volatility", "direction")
        horizon: Forecast horizon (1, 3, 6, 12)

    Returns:
        OptimizedModelParams - optimized if improved, else default
    """
    params = _load_optimized_params(target, horizon)

    if params is None:
        return OptimizedModelParams()

    return OptimizedModelParams(
        cb_iterations=params.get("cb_iterations", 200),
        cb_depth=params.get("cb_depth", 5),
        cb_learning_rate=params.get("cb_learning_rate", 0.05),
        cb_l2_leaf_reg=params.get("cb_l2_leaf_reg", 1.0),
        lgb_n_estimators=params.get("lgb_n_estimators", 200),
        lgb_max_depth=params.get("lgb_max_depth", 5),
        lgb_learning_rate=params.get("lgb_learning_rate", 0.05),
        lgb_reg_lambda=params.get("lgb_reg_lambda", 1.0),
        cb_weight=params.get("cb_weight", 0.5),
        lgb_weight=params.get("lgb_weight", 0.5),
    )


def get_optimized_l2_params(target: str, horizon: int) -> OptimizedL2Params:
    """Get L2 window parameters for a target-horizon.

    Returns optimized params if optimization improved performance,
    otherwise returns default params.

    Args:
        target: Target name (e.g., "volatility", "direction")
        horizon: Forecast horizon (1, 3, 6, 12)

    Returns:
        OptimizedL2Params - optimized if improved, else default
    """
    params = _load_optimized_params(target, horizon)

    if params is None:
        return OptimizedL2Params()

    return OptimizedL2Params(
        l2_window_size=params.get("l2_window_size", 300),
        train_ratio=params.get("train_ratio", 0.7),
        purge_gap=params.get("purge_gap", 12),
    )


def is_config_optimized(target: str, horizon: int) -> bool:
    """Check if a config uses optimized parameters.

    Args:
        target: Target name
        horizon: Forecast horizon

    Returns:
        True if using optimized params, False if using defaults
    """
    config_key = f"{target}_{horizon}bar"
    return config_key in IMPROVED_CONFIGS


def get_all_optimized_configs() -> dict[str, dict[str, Any]]:
    """Load all optimized configs that showed improvement.

    Returns:
        Dict mapping config_key to full optimization result
    """
    results = {}

    for config_key in IMPROVED_CONFIGS:
        json_path = OPTIMIZATION_RESULTS_DIR / f"{config_key}_best.json"
        if json_path.exists():
            try:
                with open(json_path) as f:
                    results[config_key] = json.load(f)
            except json.JSONDecodeError:
                pass

    return results


def print_optimization_summary() -> None:
    """Print summary of which configs use optimized vs default params."""
    all_configs = get_all_optimized_configs()

    print("=" * 60)
    print("L2 OPTIMIZATION CONFIG STATUS")
    print("=" * 60)
    print("\n✅ USING OPTIMIZED PARAMS (10 configs):")
    for key in sorted(IMPROVED_CONFIGS):
        if key in all_configs:
            pct = all_configs[key].get("improvement_pct", 0)
            print(f"  {key}: +{pct:.1f}%")

    print("\n⚠️ USING DEFAULT PARAMS (10 configs):")
    all_targets = ["direction", "returns", "volatility", "vol_spike", "trend_regime"]
    all_horizons = [1, 3, 6, 12]
    for target in all_targets:
        for horizon in all_horizons:
            key = f"{target}_{horizon}bar"
            if key not in IMPROVED_CONFIGS:
                print(f"  {key}: (degraded during optimization)")

    print("=" * 60)


if __name__ == "__main__":
    print_optimization_summary()
