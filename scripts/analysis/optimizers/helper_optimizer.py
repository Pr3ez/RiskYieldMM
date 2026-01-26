"""
Helper Model Optimizer.

Optimizes helper model configurations for each target-horizon combination.
Tests multiple configurations and selects the best based on Information Coefficient (IC).

Academic basis:
- HMM state selection: AIC/BIC, marginal likelihood (arXiv:2405.12343)
- GARCH order: AIC/BIC model comparison (Bollerslev)
- Isolation Forest contamination: OPTUNA optimization (ScienceDirect 2025)
- Kalman Q/R ratio: Sensitivity analysis (Medium)
- CUSUM threshold: Detection delay vs false positive tradeoff (arXiv:1509.01570)
"""

from __future__ import annotations

import json
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

# =============================================================================
# CONFIGURATION SEARCH SPACES
# =============================================================================

# HMM Market Regime (default: 4 states)
HMM4_CONFIGS = [
    {"n_states": 3, "n_iter": 100, "covariance_type": "diag"},
    {"n_states": 4, "n_iter": 100, "covariance_type": "diag"},  # Default
    {"n_states": 5, "n_iter": 100, "covariance_type": "diag"},
]

# HMM Volatility Regime (default: 5 states)
HMM5_CONFIGS = [
    {"n_states": 4, "n_iter": 100, "covariance_type": "diag"},
    {"n_states": 5, "n_iter": 100, "covariance_type": "diag"},  # Default
    {"n_states": 6, "n_iter": 100, "covariance_type": "diag"},
]

# GARCH configurations
GARCH_CONFIGS = [
    {"p": 1, "q": 1, "mean": "Zero"},  # Default
    {"p": 1, "q": 1, "mean": "Constant"},
    {"p": 1, "q": 2, "mean": "Zero"},
    {"p": 2, "q": 1, "mean": "Zero"},
]

# Isolation Forest contamination levels
IF_CONFIGS = [
    # Conservative (low false positives)
    {
        "contamination_extreme": 0.005,
        "contamination_moderate": 0.02,
        "contamination_mild": 0.05,
        "n_estimators": 100,
    },
    # Default
    {
        "contamination_extreme": 0.01,
        "contamination_moderate": 0.05,
        "contamination_mild": 0.10,
        "n_estimators": 100,
    },
    # Sensitive (more anomalies detected)
    {
        "contamination_extreme": 0.02,
        "contamination_moderate": 0.07,
        "contamination_mild": 0.15,
        "n_estimators": 100,
    },
    # High sensitivity for regime targets
    {
        "contamination_extreme": 0.03,
        "contamination_moderate": 0.10,
        "contamination_mild": 0.20,
        "n_estimators": 100,
    },
]

# Kalman Q/R ratio (process_noise / measurement_noise)
KALMAN_CONFIGS = [
    {"process_noise": 1e-6, "measurement_noise": 1e-3},  # Q/R = 0.001 (very smooth)
    {"process_noise": 1e-5, "measurement_noise": 1e-3},  # Q/R = 0.01 (smooth) - Default
    {"process_noise": 1e-4, "measurement_noise": 1e-3},  # Q/R = 0.1 (balanced)
    {"process_noise": 5e-4, "measurement_noise": 1e-3},  # Q/R = 0.5 (responsive)
    {"process_noise": 1e-3, "measurement_noise": 1e-3},  # Q/R = 1.0 (very responsive)
]

# CUSUM threshold/drift configurations
CUSUM_CONFIGS = [
    {"threshold": 2.0, "drift": 0.5},  # Very sensitive
    {"threshold": 2.5, "drift": 0.3},  # Sensitive
    {"threshold": 3.0, "drift": 0.2},  # Balanced
    {"threshold": 4.0, "drift": 0.1},  # Default/conservative
    {"threshold": 5.0, "drift": 0.0},  # Very conservative
]

# Full config registry
HELPER_CONFIG_SEARCH_SPACE = {
    "hmm4": HMM4_CONFIGS,
    "hmm5": HMM5_CONFIGS,
    "garch": GARCH_CONFIGS,
    "if": IF_CONFIGS,
    "kalman": KALMAN_CONFIGS,
    "cusum": CUSUM_CONFIGS,
}

# Task-specific recommendations (from research)
TASK_RECOMMENDED_CONFIGS = {
    # For volatility targets: smooth Kalman, low IF contamination
    "volatility": {
        "kalman": {"process_noise": 1e-5, "measurement_noise": 1e-3},
        "if": {"contamination_extreme": 0.01, "contamination_moderate": 0.05},
    },
    # For direction: responsive Kalman, balanced IF
    "direction": {
        "kalman": {"process_noise": 5e-4, "measurement_noise": 1e-3},
    },
    # For vol_spike: match HMM states for spike detection
    "vol_spike": {
        "hmm5": {"n_states": 3},  # Match binary + transition
        "if": {"contamination_extreme": 0.02, "contamination_moderate": 0.07},
    },
    # For trend_regime: fewer states
    "trend_regime": {
        "hmm4": {"n_states": 3},
    },
}


# =============================================================================
# HELPER OPTIMIZER
# =============================================================================
@dataclass
class HelperOptimizationResult:
    """Result of helper optimization for one target-horizon."""

    target: str
    horizon: int
    helper_name: str
    best_config: dict[str, Any]
    best_ic: float
    baseline_ic: float
    improvement_pct: float
    all_configs_tested: list[dict[str, Any]]
    all_ics: list[float]


@dataclass
class TargetOptimizationResult:
    """Aggregated results for one target-horizon."""

    target: str
    horizon: int
    helper_results: dict[str, HelperOptimizationResult]
    total_baseline_ic: float
    total_optimized_ic: float
    total_improvement_pct: float


def compute_helper_ic(
    helper_features: pd.DataFrame,
    y: np.ndarray,
) -> float:
    """Compute mean |IC| for helper features.

    Args:
        helper_features: DataFrame with helper-generated features
        y: Target values

    Returns:
        Mean absolute Spearman correlation
    """
    ics = []

    for col in helper_features.columns:
        x = helper_features[col].values

        # Skip constant or all-NaN columns
        valid_mask = ~(np.isnan(x) | np.isnan(y))
        if valid_mask.sum() < 30:
            continue

        x_valid = x[valid_mask]
        y_valid = y[valid_mask]

        if np.std(x_valid) < 1e-10 or np.std(y_valid) < 1e-10:
            continue

        try:
            ic, _ = spearmanr(x_valid, y_valid)
            if not np.isnan(ic):
                ics.append(abs(ic))
        except Exception:
            continue

    return np.mean(ics) if ics else 0.0


def create_helper_with_config(
    helper_name: str,
    target: str,
    horizon: int,
    config: dict[str, Any],
    random_state: int = 42,
):
    """Create a helper instance with specific configuration.

    Args:
        helper_name: Name of the helper (hmm4, hmm5, garch, if, kalman, cusum)
        target: Target name
        horizon: Prediction horizon
        config: Configuration dict for this helper
        random_state: Random seed

    Returns:
        Configured helper instance
    """
    from scripts.target_models.helpers.base import HelperConfig
    from scripts.target_models.helpers.cusum import CUSUMConfig, CUSUMHelper
    from scripts.target_models.helpers.garch import GARCHConfig, GARCHHelper
    from scripts.target_models.helpers.hmm import HMMHelper
    from scripts.target_models.helpers.isolation_forest import (
        IsolationForestConfig,
        IsolationForestHelper,
    )
    from scripts.target_models.helpers.kalman import KalmanHelper

    task_type = _get_task_type(target)
    base_config = HelperConfig(
        target=target,
        horizon=horizon,
        task_type=task_type,
        random_state=random_state,
    )

    if helper_name == "hmm4":
        return HMMHelper(
            config=base_config,
            n_states=config.get("n_states", 4),
            regime_type="market",
            n_iter=config.get("n_iter", 100),
            covariance_type=config.get("covariance_type", "diag"),
        )
    elif helper_name == "hmm5":
        return HMMHelper(
            config=base_config,
            n_states=config.get("n_states", 5),
            regime_type="volatility",
            n_iter=config.get("n_iter", 100),
            covariance_type=config.get("covariance_type", "diag"),
        )
    elif helper_name == "garch":
        garch_config = GARCHConfig(
            target=target,
            horizon=horizon,
            task_type=task_type,
            random_state=random_state,
            p=config.get("p", 1),
            q=config.get("q", 1),
            mean=config.get("mean", "Zero"),
            forecast_horizon=horizon,
        )
        return GARCHHelper(garch_config)
    elif helper_name == "if":
        if_config = IsolationForestConfig(
            target=target,
            horizon=horizon,
            task_type=task_type,
            random_state=random_state,
            contamination_extreme=config.get("contamination_extreme", 0.01),
            contamination_moderate=config.get("contamination_moderate", 0.05),
            contamination_mild=config.get("contamination_mild", 0.10),
            n_estimators=config.get("n_estimators", 100),
        )
        return IsolationForestHelper(if_config)
    elif helper_name == "kalman":
        return KalmanHelper(
            config=base_config,
            process_noise=config.get("process_noise", 1e-5),
            measurement_noise=config.get("measurement_noise", 1e-3),
        )
    elif helper_name == "cusum":
        cusum_config = CUSUMConfig(
            target=target,
            horizon=horizon,
            task_type=task_type,
            random_state=random_state,
            threshold=config.get("threshold", 4.0),
            drift=config.get("drift", 0.0),
        )
        return CUSUMHelper(cusum_config)
    else:
        raise ValueError(f"Unknown helper: {helper_name}")


def _get_task_type(target: str) -> Literal["regression", "binary", "multiclass"]:
    """Get task type for target."""
    if target in ("volatility", "returns"):
        return "regression"
    elif target in ("direction", "trend_regime", "vol_spike"):
        return "binary"
    else:
        return "regression"


def optimize_single_helper(
    helper_name: str,
    target: str,
    horizon: int,
    X_train: np.ndarray,
    X_cal: np.ndarray,
    y_cal: np.ndarray,
    configs_to_test: list[dict[str, Any]] | None = None,
    random_state: int = 42,
) -> HelperOptimizationResult:
    """Optimize configuration for a single helper.

    Args:
        helper_name: Name of helper to optimize
        target: Target name
        horizon: Prediction horizon
        X_train: Training features (for helper fitting)
        X_cal: Calibration features (for IC computation)
        y_cal: Calibration targets
        configs_to_test: List of configs to test (None = use defaults)
        random_state: Random seed

    Returns:
        HelperOptimizationResult with best config and metrics
    """
    if configs_to_test is None:
        configs_to_test = HELPER_CONFIG_SEARCH_SPACE.get(helper_name, [{}])

    all_ics = []
    best_ic = -1.0
    best_config = configs_to_test[0] if configs_to_test else {}

    # First config as baseline
    baseline_ic = 0.0

    for i, config in enumerate(configs_to_test):
        try:
            # Create helper with this config
            helper = create_helper_with_config(
                helper_name, target, horizon, config, random_state
            )

            # Fit on training data
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                helper.fit(X_train)

            # Transform calibration data
            output = helper.transform(X_cal)
            features = output.features

            # Compute IC
            ic = compute_helper_ic(features, y_cal)
            all_ics.append(ic)

            # Track baseline (first config)
            if i == 0:
                baseline_ic = ic

            # Track best
            if ic > best_ic:
                best_ic = ic
                best_config = config

        except Exception as e:
            print(f"  Warning: Config {config} failed: {e}")
            all_ics.append(0.0)

    improvement = (
        ((best_ic - baseline_ic) / baseline_ic * 100) if baseline_ic > 0 else 0.0
    )

    return HelperOptimizationResult(
        target=target,
        horizon=horizon,
        helper_name=helper_name,
        best_config=best_config,
        best_ic=best_ic,
        baseline_ic=baseline_ic,
        improvement_pct=improvement,
        all_configs_tested=configs_to_test,
        all_ics=all_ics,
    )


def optimize_all_helpers_for_target(
    target: str,
    horizon: int,
    X_train: np.ndarray,
    X_cal: np.ndarray,
    y_cal: np.ndarray,
    helpers_to_optimize: list[str] | None = None,
    random_state: int = 42,
) -> TargetOptimizationResult:
    """Optimize all helpers for a single target-horizon.

    Args:
        target: Target name
        horizon: Prediction horizon
        X_train: Training features
        X_cal: Calibration features
        y_cal: Calibration targets
        helpers_to_optimize: List of helpers to optimize (None = all)
        random_state: Random seed

    Returns:
        TargetOptimizationResult with all helper results
    """
    if helpers_to_optimize is None:
        helpers_to_optimize = list(HELPER_CONFIG_SEARCH_SPACE.keys())

    helper_results = {}
    total_baseline = 0.0
    total_optimized = 0.0

    for helper_name in helpers_to_optimize:
        print(f"  Optimizing {helper_name}...")

        result = optimize_single_helper(
            helper_name=helper_name,
            target=target,
            horizon=horizon,
            X_train=X_train,
            X_cal=X_cal,
            y_cal=y_cal,
            random_state=random_state,
        )

        helper_results[helper_name] = result
        total_baseline += result.baseline_ic
        total_optimized += result.best_ic

        print(f"    Baseline IC: {result.baseline_ic:.4f}")
        print(f"    Best IC: {result.best_ic:.4f} ({result.improvement_pct:+.1f}%)")
        print(f"    Best config: {result.best_config}")

    improvement = (
        ((total_optimized - total_baseline) / total_baseline * 100)
        if total_baseline > 0
        else 0.0
    )

    return TargetOptimizationResult(
        target=target,
        horizon=horizon,
        helper_results=helper_results,
        total_baseline_ic=total_baseline,
        total_optimized_ic=total_optimized,
        total_improvement_pct=improvement,
    )


def save_optimal_configs(
    results: list[TargetOptimizationResult],
    output_path: str | Path,
) -> None:
    """Save optimal configurations to JSON file.

    Args:
        results: List of optimization results
        output_path: Path to save JSON file
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    configs = {}
    for result in results:
        key = f"{result.target}_{result.horizon}bar"
        configs[key] = {
            "target": result.target,
            "horizon": result.horizon,
            "helpers": {
                name: {
                    "config": hr.best_config,
                    "ic": hr.best_ic,
                    "improvement_pct": hr.improvement_pct,
                }
                for name, hr in result.helper_results.items()
            },
            "total_ic": result.total_optimized_ic,
            "improvement_pct": result.total_improvement_pct,
        }

    with open(output_path, "w") as f:
        json.dump(configs, f, indent=2, default=str)

    print(f"Saved optimal configs to {output_path}")


def load_optimal_configs(config_path: str | Path) -> dict[str, Any]:
    """Load optimal configurations from JSON file.

    Args:
        config_path: Path to JSON file

    Returns:
        Dict of optimal configs by target-horizon
    """
    with open(config_path) as f:
        return json.load(f)


# =============================================================================
# CLI ENTRY POINT
# =============================================================================
def run_helper_optimization(
    targets: list[str] | None = None,
    horizons: list[int] | None = None,
    output_dir: str | Path = "data/analysis/results",
    random_state: int = 42,
    l1_min_warmup: int = 500,
    l2_window_size: int = 500,
) -> list[TargetOptimizationResult]:
    """Run helper optimization for multiple target-horizons.

    CRITICAL: Uses proper L1/L2 window structure to avoid look-ahead bias!

    Architecture (from aligned_dual_window.py):
        [0 ─────────── L2_start][L2_train][purge][L2_cal][L2_val][pred]
        │<─── L1 expanding ───>│<────── L2 sliding ─────────────>│

    Helper optimization uses ONLY L1 data:
        - L1.train (first 80% of L1): Fit helpers
        - L1.val (last 20% of L1): Compute IC for config selection

    L1 ends BEFORE L2 starts, so we never see L2 targets during optimization.

    Args:
        targets: List of targets (None = all 5)
        horizons: List of horizons (None = all 4)
        output_dir: Directory for output files
        random_state: Random seed
        l1_min_warmup: Minimum L1 window size
        l2_window_size: L2 window size

    Returns:
        List of optimization results
    """
    from scripts.target_models.core.aligned_dual_window import (
        AlignedDualEngine,
        create_aligned_config,
    )
    from scripts.target_models.registry import load_target_data

    if targets is None:
        targets = ["volatility", "returns", "direction", "vol_spike", "trend_regime"]
    if horizons is None:
        horizons = [1, 3, 6, 12]

    output_dir = Path(output_dir)
    all_results = []

    print("=" * 80)
    print("HELPER MODEL OPTIMIZATION (Leak-Free)")
    print("=" * 80)
    print("Using L1/L2 window structure:")
    print(f"  L1 min warmup: {l1_min_warmup}")
    print(f"  L2 window size: {l2_window_size}")
    print("  Validation on L1.val ONLY (before L2 starts)")

    for target in targets:
        for horizon in horizons:
            print(f"\n{'=' * 60}")
            print(f"Target: {target}, Horizon: {horizon}-bar")
            print("=" * 60)

            try:
                # Load data
                X, y, spec = load_target_data(target, horizon)

                # Create aligned dual config
                config = create_aligned_config(
                    target=target,
                    horizon=horizon,
                    l1_min_warmup=l1_min_warmup,
                    l2_window_size=l2_window_size,
                )

                # Check if we have enough data
                min_required = config.min_required_rows
                if len(X) < min_required:
                    print(f"  Warning: Not enough data ({len(X)} < {min_required})")
                    continue

                # Create engine and get FIRST window for optimization
                # We optimize on the first valid window's L1 data
                engine = AlignedDualEngine(X, y, config)
                first_window = engine.get_window(engine.first_pred_idx, 0)

                # L1 boundaries (this is ALL we can use for optimization)
                l1_train_end = first_window.l1.train.end_idx
                l1_val_start = first_window.l1.val.start_idx
                l1_val_end = first_window.l1.val.end_idx

                print(
                    f"  L1 window: [0:{l1_train_end}] train, [{l1_val_start}:{l1_val_end}] val"
                )
                print(
                    f"  L2 starts at idx: {first_window.get_l2_start_idx()} (NOT used for optimization)"
                )

                # Extract L1 train and val data
                X_l1_train = X.iloc[:l1_train_end].values
                X_l1_val = X.iloc[l1_val_start:l1_val_end].values
                y_l1_val = y.values[l1_val_start:l1_val_end]

                # Run optimization using ONLY L1 data
                result = optimize_all_helpers_for_target(
                    target=target,
                    horizon=horizon,
                    X_train=X_l1_train,
                    X_cal=X_l1_val,  # L1.val for IC computation
                    y_cal=y_l1_val,  # L1.val targets (BEFORE L2 starts)
                    random_state=random_state,
                )

                all_results.append(result)

                print(f"\n  Total baseline IC: {result.total_baseline_ic:.4f}")
                print(f"  Total optimized IC: {result.total_optimized_ic:.4f}")
                print(f"  Total improvement: {result.total_improvement_pct:+.1f}%")

            except Exception as e:
                print(f"  ERROR: {e}")
                import traceback

                traceback.print_exc()

    # Save results
    if all_results:
        save_optimal_configs(all_results, output_dir / "optimal_helper_configs.json")

        # Create summary DataFrame
        summary_data = []
        for result in all_results:
            for helper_name, hr in result.helper_results.items():
                summary_data.append(
                    {
                        "target": result.target,
                        "horizon": result.horizon,
                        "helper": helper_name,
                        "baseline_ic": hr.baseline_ic,
                        "best_ic": hr.best_ic,
                        "improvement_pct": hr.improvement_pct,
                        "best_config": str(hr.best_config),
                    }
                )

        summary_df = pd.DataFrame(summary_data)
        summary_df.to_csv(output_dir / "helper_optimization_summary.csv", index=False)

        print("\n" + "=" * 80)
        print("OPTIMIZATION COMPLETE")
        print("=" * 80)

        # Print overall summary
        print("\nSummary by helper:")
        for helper in ["hmm4", "hmm5", "garch", "if", "kalman", "cusum"]:
            helper_data = summary_df[summary_df["helper"] == helper]
            if not helper_data.empty:
                mean_improvement = helper_data["improvement_pct"].mean()
                print(f"  {helper}: {mean_improvement:+.1f}% avg improvement")

    return all_results


if __name__ == "__main__":
    results = run_helper_optimization()
