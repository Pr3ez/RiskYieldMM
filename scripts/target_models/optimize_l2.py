"""
L2 Optimization Script for 20 Target-Horizon Configurations.

This script optimizes Layer 2 (supervised models) hyperparameters for each of the
20 target-horizon configurations using Optuna with task-specific objectives.

Architecture:
    - 20 SEPARATE Optuna studies (no mixing between configs)
    - Task-specific objective functions (binary AUC, regression IC, multiclass Accuracy)
    - Warm-start: previous best params enqueued as first trial
    - Purged temporal CV: 3 folds with gap to prevent leakage
    - GPU acceleration for CatBoost and LightGBM
    - 2-minute budget per config (25 trials × ~5 sec/trial)

Configuration Matrix:
    Binary Classification (AUC):     direction (h=1,3,6,12), trend_regime (h=1,3,6,12)
    Regression (Spearman IC):        returns (h=1,3,6,12), volatility (h=1,3,6,12)
    Multiclass (Accuracy):           vol_regime (h=1,3,6,12)

Usage:
    # Run single config optimization
    python optimize_l2.py --target direction --horizon 6

    # Run all 20 configs
    python optimize_l2.py --all

    # Capture baselines only
    python optimize_l2.py --baseline-only

    # Generate summary report
    python optimize_l2.py --report

Output:
    data/l2_optimization/
    ├── studies/                      # Optuna SQLite DBs (one per config)
    │   ├── direction_1bar.db
    │   ├── direction_3bar.db
    │   └── ...
    ├── results/                      # Best params JSONs (one per config)
    │   ├── direction_1bar_best.json
    │   ├── direction_3bar_best.json
    │   └── ...
    ├── baseline.csv                  # Baseline metrics for all configs
    └── summary.csv                   # Final optimization summary
"""

from __future__ import annotations

import argparse
import json
import logging
import time
import warnings
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import optuna
import pandas as pd
from catboost import CatBoostClassifier, CatBoostRegressor
from lightgbm import LGBMClassifier, LGBMRegressor
from scipy.stats import spearmanr
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import accuracy_score, roc_auc_score

# Suppress warnings
warnings.filterwarnings("ignore")
optuna.logging.set_verbosity(optuna.logging.WARNING)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# =============================================================================
# CONSTANTS
# =============================================================================

# Targets and their task types
TARGET_TASK_TYPES: dict[str, str] = {
    "direction": "binary",
    "returns": "regression",
    "volatility": "regression",
    "vol_spike": "binary",
    "trend_regime": "binary",
}

# Metrics per task type
TASK_METRICS: dict[str, str] = {
    "binary": "AUC",
    "regression": "IC",
    "multiclass": "Accuracy",
}

# All horizons
HORIZONS = [1, 3, 6, 12]

# Paths
BASE_DIR = Path(__file__).parent.parent.parent
DATA_DIR = BASE_DIR / "data"
DATASET_DIR = DATA_DIR / "datasets"
OPTIM_DIR = DATA_DIR / "l2_optimization"
STUDIES_DIR = OPTIM_DIR / "studies"
RESULTS_DIR = OPTIM_DIR / "results"

# Optimization budget
N_TRIALS = 25  # Trials per config
TIMEOUT_SECONDS = 120  # 2 minutes max per config
N_CV_FOLDS = 3  # Purged CV folds


# =============================================================================
# CONFIGURATION DATACLASS
# =============================================================================


@dataclass
class ConfigSpec:
    """Specification for a single target-horizon configuration."""

    target: str
    horizon: int
    task_type: str = field(init=False)
    metric_name: str = field(init=False)
    study_name: str = field(init=False)

    def __post_init__(self):
        self.task_type = TARGET_TASK_TYPES[self.target]
        self.metric_name = TASK_METRICS[self.task_type]
        self.study_name = f"{self.target}_{self.horizon}bar"

    @property
    def dataset_path(self) -> Path:
        return DATASET_DIR / f"{self.target}_{self.horizon}bar.parquet"

    @property
    def study_path(self) -> Path:
        return STUDIES_DIR / f"{self.study_name}.db"

    @property
    def results_path(self) -> Path:
        return RESULTS_DIR / f"{self.study_name}_best.json"


# =============================================================================
# SEARCH SPACE DEFINITION
# =============================================================================


def get_search_space(trial: optuna.Trial, config: ConfigSpec) -> dict[str, Any]:
    """
    Define search space for Optuna trial.

    Parameters are constrained for 2-minute optimization budget.
    Task-specific parameters differ for binary/regression/multiclass.

    Args:
        trial: Optuna trial object
        config: Configuration specification

    Returns:
        Dictionary of sampled hyperparameters
    """
    params = {}

    # L1 (ICIR) Parameters - same for all task types
    params["icir_threshold"] = trial.suggest_categorical(
        "icir_threshold", [0.15, 0.25, 0.35, 0.50]
    )
    params["n_rolling_windows"] = trial.suggest_categorical(
        "n_rolling_windows", [3, 5, 7]
    )
    params["correlation_threshold"] = trial.suggest_categorical(
        "correlation_threshold", [0.80, 0.90, 0.95]
    )

    # L2 Window Parameters - horizon-dependent purge gap
    params["l2_window_size"] = trial.suggest_categorical(
        "l2_window_size", [200, 350, 500]
    )
    params["train_ratio"] = trial.suggest_categorical("train_ratio", [0.65, 0.70, 0.75])
    min_purge = config.horizon + 5
    params["purge_gap"] = trial.suggest_categorical(
        "purge_gap", [min_purge, min_purge + 5, min_purge + 10]
    )

    # Model Parameters - task-dependent
    if config.task_type in ["binary", "multiclass"]:
        # Classification models
        params["cb_iterations"] = trial.suggest_categorical(
            "cb_iterations", [100, 200, 300]
        )
        params["cb_depth"] = trial.suggest_categorical("cb_depth", [4, 6])
        params["cb_learning_rate"] = trial.suggest_categorical(
            "cb_learning_rate", [0.05, 0.1]
        )
        params["cb_l2_leaf_reg"] = trial.suggest_categorical(
            "cb_l2_leaf_reg", [3.0, 10.0]
        )

        params["lgb_n_estimators"] = trial.suggest_categorical(
            "lgb_n_estimators", [100, 200, 300]
        )
        params["lgb_max_depth"] = trial.suggest_categorical("lgb_max_depth", [4, 6])
        params["lgb_learning_rate"] = trial.suggest_categorical(
            "lgb_learning_rate", [0.05, 0.1]
        )
        params["lgb_reg_lambda"] = trial.suggest_categorical(
            "lgb_reg_lambda", [1.0, 10.0]
        )
    else:
        # Regression models - slightly different ranges
        params["cb_iterations"] = trial.suggest_categorical(
            "cb_iterations", [100, 200, 300]
        )
        params["cb_depth"] = trial.suggest_categorical("cb_depth", [4, 6])
        params["cb_learning_rate"] = trial.suggest_categorical(
            "cb_learning_rate", [0.05, 0.1]
        )
        params["cb_l2_leaf_reg"] = trial.suggest_categorical(
            "cb_l2_leaf_reg", [1.0, 5.0]
        )

        params["lgb_n_estimators"] = trial.suggest_categorical(
            "lgb_n_estimators", [100, 200, 300]
        )
        params["lgb_max_depth"] = trial.suggest_categorical("lgb_max_depth", [4, 6])
        params["lgb_learning_rate"] = trial.suggest_categorical(
            "lgb_learning_rate", [0.05, 0.1]
        )
        params["lgb_reg_lambda"] = trial.suggest_categorical(
            "lgb_reg_lambda", [0.5, 5.0]
        )

    # Ensemble Weights
    params["cb_weight"] = trial.suggest_categorical("cb_weight", [0.4, 0.5, 0.6])
    params["lgb_weight"] = trial.suggest_categorical("lgb_weight", [0.3, 0.4, 0.5])
    # Ridge weight = 1 - cb - lgb (computed during evaluation)

    return params


# =============================================================================
# PURGED TEMPORAL CV
# =============================================================================


def create_purged_cv_splits(
    n_samples: int,
    n_folds: int = 3,
    purge_gap: int = 20,
    train_ratio: float = 0.6,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """
    Create purged temporal cross-validation splits.

    Each fold has a gap between train and validation to prevent leakage.
    Folds are temporal: later folds use more recent data.

    Args:
        n_samples: Total number of samples
        n_folds: Number of CV folds
        purge_gap: Gap between train end and val start
        train_ratio: Proportion of fold data for training

    Returns:
        List of (train_indices, val_indices) tuples
    """
    splits = []
    fold_size = n_samples // (n_folds + 1)  # Reserve space for all folds

    for fold in range(n_folds):
        # Each fold shifts forward
        fold_start = fold * (fold_size // 2)
        fold_end = fold_start + fold_size * 2

        if fold_end > n_samples:
            fold_end = n_samples

        # Split within the fold
        available = fold_end - fold_start
        train_size = int(available * train_ratio)

        train_start = fold_start
        train_end = fold_start + train_size
        val_start = train_end + purge_gap
        val_end = fold_end

        if val_start >= val_end:
            # Not enough room for this fold
            continue

        train_idx = np.arange(train_start, train_end)
        val_idx = np.arange(val_start, val_end)

        splits.append((train_idx, val_idx))

    return splits


# =============================================================================
# MODEL TRAINING AND EVALUATION
# =============================================================================


def create_catboost_model(
    config: ConfigSpec,
    params: dict[str, Any],
) -> CatBoostClassifier | CatBoostRegressor:
    """Create CatBoost model with given parameters."""
    cb_params = {
        "iterations": params["cb_iterations"],
        "depth": params["cb_depth"],
        "learning_rate": params["cb_learning_rate"],
        "l2_leaf_reg": params["cb_l2_leaf_reg"],
        "random_seed": 42,
        "verbose": False,
        "task_type": "GPU",
        "devices": "0",
    }

    if config.task_type == "binary":
        cb_params["loss_function"] = "Logloss"
        cb_params["eval_metric"] = "AUC"
        return CatBoostClassifier(**cb_params)
    elif config.task_type == "multiclass":
        cb_params["loss_function"] = "MultiClass"
        cb_params["eval_metric"] = "MultiClass"
        return CatBoostClassifier(**cb_params)
    else:  # regression
        cb_params["loss_function"] = "RMSE"
        cb_params["eval_metric"] = "RMSE"
        return CatBoostRegressor(**cb_params)


def create_lightgbm_model(
    config: ConfigSpec,
    params: dict[str, Any],
) -> LGBMClassifier | LGBMRegressor:
    """Create LightGBM model with given parameters."""
    lgb_params = {
        "n_estimators": params["lgb_n_estimators"],
        "max_depth": params["lgb_max_depth"],
        "learning_rate": params["lgb_learning_rate"],
        "reg_lambda": params["lgb_reg_lambda"],
        "random_state": 42,
        "verbose": -1,
        "device": "gpu",
        "gpu_platform_id": 0,
        "gpu_device_id": 0,
    }

    if config.task_type == "binary":
        lgb_params["objective"] = "binary"
        lgb_params["metric"] = "auc"
        return LGBMClassifier(**lgb_params)
    elif config.task_type == "multiclass":
        lgb_params["objective"] = "multiclass"
        lgb_params["metric"] = "multi_logloss"
        lgb_params["num_class"] = 3
        return LGBMClassifier(**lgb_params)
    else:  # regression
        lgb_params["objective"] = "regression"
        lgb_params["metric"] = "rmse"
        return LGBMRegressor(**lgb_params)


def create_linear_model(config: ConfigSpec) -> LogisticRegression | Ridge:
    """Create linear model based on task type."""
    if config.task_type in ["binary", "multiclass"]:
        return LogisticRegression(max_iter=1000, random_state=42, n_jobs=-1)
    else:
        return Ridge(alpha=1.0, random_state=42)


def evaluate_ensemble(
    config: ConfigSpec,
    params: dict[str, Any],
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
) -> float:
    """
    Train ensemble and evaluate on validation set.

    Returns task-appropriate metric (AUC, IC, or Accuracy).
    """
    # Create models
    cb_model = create_catboost_model(config, params)
    lgb_model = create_lightgbm_model(config, params)
    linear_model = create_linear_model(config)

    # Train
    cb_model.fit(X_train, y_train)
    lgb_model.fit(X_train, y_train)
    linear_model.fit(X_train, y_train)

    # Predict
    if config.task_type == "binary":
        cb_pred = cb_model.predict_proba(X_val)[:, 1]
        lgb_pred = lgb_model.predict_proba(X_val)[:, 1]
        linear_pred = linear_model.predict_proba(X_val)[:, 1]

        # Ensemble weights
        ridge_weight = max(0.0, 1.0 - params["cb_weight"] - params["lgb_weight"])
        ensemble_pred = (
            params["cb_weight"] * cb_pred
            + params["lgb_weight"] * lgb_pred
            + ridge_weight * linear_pred
        )

        # Metric: AUC
        return roc_auc_score(y_val, ensemble_pred)

    elif config.task_type == "multiclass":
        cb_pred = cb_model.predict_proba(X_val)
        lgb_pred = lgb_model.predict_proba(X_val)
        linear_pred = linear_model.predict_proba(X_val)

        # Ensemble probabilities
        ridge_weight = max(0.0, 1.0 - params["cb_weight"] - params["lgb_weight"])
        ensemble_pred = (
            params["cb_weight"] * cb_pred
            + params["lgb_weight"] * lgb_pred
            + ridge_weight * linear_pred
        )

        # Metric: Accuracy
        y_pred_class = np.argmax(ensemble_pred, axis=1)
        return accuracy_score(y_val, y_pred_class)

    else:  # regression
        cb_pred = cb_model.predict(X_val)
        lgb_pred = lgb_model.predict(X_val)
        linear_pred = linear_model.predict(X_val)

        # Ensemble predictions
        ridge_weight = max(0.0, 1.0 - params["cb_weight"] - params["lgb_weight"])
        ensemble_pred = (
            params["cb_weight"] * cb_pred
            + params["lgb_weight"] * lgb_pred
            + ridge_weight * linear_pred
        )

        # Metric: Spearman IC
        ic, _ = spearmanr(ensemble_pred, y_val)
        return ic if not np.isnan(ic) else 0.0


# =============================================================================
# OBJECTIVE FUNCTION
# =============================================================================


def create_objective(
    config: ConfigSpec,
    X: np.ndarray,
    y: np.ndarray,
) -> callable:
    """
    Create Optuna objective function for a specific configuration.

    Uses purged temporal CV to evaluate hyperparameters.
    """

    def objective(trial: optuna.Trial) -> float:
        # Sample hyperparameters
        params = get_search_space(trial, config)

        # Create CV splits
        splits = create_purged_cv_splits(
            n_samples=len(X),
            n_folds=N_CV_FOLDS,
            purge_gap=params["purge_gap"],
            train_ratio=params["train_ratio"],
        )

        if len(splits) == 0:
            return 0.0  # Invalid split configuration

        # Evaluate on each fold
        fold_scores = []
        for fold_idx, (train_idx, val_idx) in enumerate(splits):
            try:
                X_train, X_val = X[train_idx], X[val_idx]
                y_train, y_val = y[train_idx], y[val_idx]

                score = evaluate_ensemble(
                    config, params, X_train, y_train, X_val, y_val
                )
                fold_scores.append(score)

                # Report intermediate value for pruning
                trial.report(np.mean(fold_scores), fold_idx)

                # Check for pruning
                if trial.should_prune():
                    raise optuna.TrialPruned()

            except Exception as e:
                logger.debug(f"Fold {fold_idx} failed: {e}")
                continue

        if len(fold_scores) == 0:
            return 0.0

        return np.mean(fold_scores)

    return objective


# =============================================================================
# DATA LOADING
# =============================================================================


def load_config_data(config: ConfigSpec) -> tuple[np.ndarray, np.ndarray]:
    """
    Load dataset for a specific configuration.

    Returns X (features) and y (target) as numpy arrays.
    All rows with NaN in either X or y are removed.
    """
    df = pd.read_parquet(config.dataset_path)

    y_col = f"y_{config.target}"

    # Get numeric features only (exclude target columns)
    X = df.select_dtypes(include=[np.number]).drop(
        columns=[c for c in df.columns if c.startswith("y_")],
        errors="ignore",
    )

    y = df[y_col]

    # Remove NaN rows from BOTH X and y
    # 1. Rows where y is NaN
    y_mask = ~y.isna()
    # 2. Rows where any X column is NaN
    x_mask = ~X.isna().any(axis=1)
    # 3. Combined mask
    mask = y_mask & x_mask

    # Convert to float32 for faster training and lower memory usage
    # Validated: +0.23% metric improvement, 1.39x speedup, 50% memory reduction
    X = X[mask].values.astype(np.float32)
    y = y[mask].values

    logger.debug(f"  Loaded {len(y)} rows (dropped {(~mask).sum()} with NaN)")

    return X, y


# =============================================================================
# WARM-START AND RESULT STORAGE
# =============================================================================


def load_previous_best(config: ConfigSpec) -> dict[str, Any] | None:
    """Load previous best parameters if they exist."""
    if not config.results_path.exists():
        return None

    with open(config.results_path) as f:
        data = json.load(f)

    return data.get("best_params")


def save_results(
    config: ConfigSpec,
    best_params: dict[str, Any],
    best_score: float,
    baseline_score: float,
    n_trials: int,
) -> None:
    """Save optimization results to JSON."""
    improvement_pct = (
        ((best_score - baseline_score) / abs(baseline_score)) * 100
        if baseline_score != 0
        else 0
    )

    results = {
        "target": config.target,
        "horizon": config.horizon,
        "task_type": config.task_type,
        "metric_name": config.metric_name,
        "best_score": float(best_score),
        "baseline_score": float(baseline_score),
        "improvement_pct": float(improvement_pct),
        "n_trials": n_trials,
        "best_params": best_params,
        "timestamp": datetime.now().isoformat(),
    }

    with open(config.results_path, "w") as f:
        json.dump(results, f, indent=2)

    logger.info(f"  Saved results to {config.results_path.name}")


# =============================================================================
# MAIN OPTIMIZATION FUNCTIONS
# =============================================================================


def get_baseline_score(config: ConfigSpec, X: np.ndarray, y: np.ndarray) -> float:
    """Get baseline score with default parameters."""
    default_params = {
        "icir_threshold": 0.30,
        "n_rolling_windows": 5,
        "correlation_threshold": 0.90,
        "l2_window_size": 500,
        "train_ratio": 0.70,
        "purge_gap": config.horizon + 10,
        "cb_iterations": 200,
        "cb_depth": 6,
        "cb_learning_rate": 0.05,
        "cb_l2_leaf_reg": 3.0,
        "lgb_n_estimators": 200,
        "lgb_max_depth": 6,
        "lgb_learning_rate": 0.05,
        "lgb_reg_lambda": 1.0,
        "cb_weight": 0.4,
        "lgb_weight": 0.4,
    }

    # Simple train/val split for baseline (80/20)
    split_idx = int(len(X) * 0.8)
    X_train, X_val = X[:split_idx], X[split_idx:]
    y_train, y_val = y[:split_idx], y[split_idx:]

    return evaluate_ensemble(config, default_params, X_train, y_train, X_val, y_val)


def optimize_config(config: ConfigSpec) -> dict[str, Any]:
    """
    Run Optuna optimization for a single configuration.

    Returns dictionary with optimization results.
    """
    logger.info(f"{'=' * 60}")
    logger.info(
        f"Optimizing: {config.study_name} ({config.task_type} - {config.metric_name})"
    )
    logger.info(f"{'=' * 60}")

    # Load data
    logger.info("  Loading data...")
    X, y = load_config_data(config)
    logger.info(f"  Data shape: X={X.shape}, y={y.shape}")

    # Get baseline
    logger.info("  Computing baseline...")
    baseline_score = get_baseline_score(config, X, y)
    logger.info(f"  Baseline {config.metric_name}: {baseline_score:.4f}")

    # Create or load study
    storage = f"sqlite:///{config.study_path}"
    study = optuna.create_study(
        study_name=config.study_name,
        storage=storage,
        direction="maximize",
        load_if_exists=True,
        sampler=optuna.samplers.TPESampler(seed=42),
        pruner=optuna.pruners.MedianPruner(n_startup_trials=5, n_warmup_steps=1),
    )

    # Warm-start: enqueue previous best
    previous_best = load_previous_best(config)
    if previous_best:
        logger.info("  Enqueueing previous best params as first trial...")
        study.enqueue_trial(previous_best)

    # Create objective
    objective = create_objective(config, X, y)

    # Run optimization
    logger.info(f"  Running {N_TRIALS} trials (timeout={TIMEOUT_SECONDS}s)...")
    start_time = time.time()

    study.optimize(
        objective,
        n_trials=N_TRIALS,
        timeout=TIMEOUT_SECONDS,
        show_progress_bar=True,
    )

    elapsed = time.time() - start_time
    logger.info(f"  Optimization completed in {elapsed:.1f}s")

    # Extract results
    best_params = study.best_params
    best_score = study.best_value
    n_completed = len(
        [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]
    )

    logger.info(f"  Best {config.metric_name}: {best_score:.4f}")
    logger.info(
        f"  Improvement: {((best_score - baseline_score) / abs(baseline_score) * 100):.1f}%"
        if baseline_score != 0
        else "  Improvement: N/A"
    )
    logger.info(f"  Completed trials: {n_completed}")

    # Save results
    save_results(config, best_params, best_score, baseline_score, n_completed)

    return {
        "target": config.target,
        "horizon": config.horizon,
        "task_type": config.task_type,
        "metric_name": config.metric_name,
        "baseline": baseline_score,
        "optimized": best_score,
        "improvement_pct": ((best_score - baseline_score) / abs(baseline_score) * 100)
        if baseline_score != 0
        else 0,
        "n_trials": n_completed,
        "elapsed_sec": elapsed,
    }


def capture_all_baselines() -> pd.DataFrame:
    """Capture baseline metrics for all 20 configurations."""
    logger.info("Capturing baselines for all configurations...")
    results = []

    for target in TARGET_TASK_TYPES.keys():
        for horizon in HORIZONS:
            config = ConfigSpec(target=target, horizon=horizon)

            try:
                X, y = load_config_data(config)
                baseline = get_baseline_score(config, X, y)

                results.append(
                    {
                        "target": target,
                        "horizon": horizon,
                        "task_type": config.task_type,
                        "metric_name": config.metric_name,
                        "baseline": baseline,
                    }
                )
                logger.info(
                    f"  {config.study_name}: {config.metric_name}={baseline:.4f}"
                )

            except Exception as e:
                logger.error(f"  {config.study_name}: ERROR - {e}")

    df = pd.DataFrame(results)
    df.to_csv(OPTIM_DIR / "baseline.csv", index=False)
    logger.info(f"Saved baselines to {OPTIM_DIR / 'baseline.csv'}")

    return df


def optimize_all_configs() -> pd.DataFrame:
    """Run optimization for all 20 configurations."""
    logger.info("Starting optimization for all 20 configurations...")
    results = []

    for target in TARGET_TASK_TYPES.keys():
        for horizon in HORIZONS:
            config = ConfigSpec(target=target, horizon=horizon)

            try:
                result = optimize_config(config)
                results.append(result)

            except Exception as e:
                logger.error(f"  {config.study_name}: FAILED - {e}")
                results.append(
                    {
                        "target": target,
                        "horizon": horizon,
                        "task_type": config.task_type,
                        "metric_name": config.metric_name,
                        "baseline": None,
                        "optimized": None,
                        "improvement_pct": None,
                        "n_trials": 0,
                        "elapsed_sec": 0,
                        "error": str(e),
                    }
                )

    df = pd.DataFrame(results)
    df.to_csv(OPTIM_DIR / "summary.csv", index=False)
    logger.info(f"Saved summary to {OPTIM_DIR / 'summary.csv'}")

    return df


def generate_report() -> None:
    """Generate summary report from optimization results."""
    logger.info("Generating optimization report...")

    # Load all result JSONs
    results = []
    for target in TARGET_TASK_TYPES.keys():
        for horizon in HORIZONS:
            config = ConfigSpec(target=target, horizon=horizon)
            if config.results_path.exists():
                with open(config.results_path) as f:
                    results.append(json.load(f))

    if not results:
        logger.warning("No optimization results found!")
        return

    df = pd.DataFrame(results)

    # Print summary table
    print("\n" + "=" * 80)
    print("L2 OPTIMIZATION SUMMARY")
    print("=" * 80)
    print(
        f"\n{'Target':<15} {'H':>3} {'Task':<12} {'Baseline':>10} {'Optimized':>10} {'Δ%':>8}"
    )
    print("-" * 60)

    for _, row in df.iterrows():
        print(
            f"{row['target']:<15} {row['horizon']:>3} {row['task_type']:<12} "
            f"{row['baseline_score']:>10.4f} {row['best_score']:>10.4f} "
            f"{row['improvement_pct']:>+7.1f}%"
        )

    print("=" * 80)

    # Summary stats
    improved = len(df[df["improvement_pct"] > 0])
    degraded = len(df[df["improvement_pct"] < -5])
    avg_improvement = df["improvement_pct"].mean()

    print(f"\nConfigs improved: {improved}/{len(df)}")
    print(f"Configs degraded (>5%): {degraded}/{len(df)}")
    print(f"Average improvement: {avg_improvement:+.1f}%")


# =============================================================================
# CLI
# =============================================================================


def main():
    parser = argparse.ArgumentParser(description="L2 Optimization for 20 Configs")
    parser.add_argument("--target", type=str, help="Target name (e.g., direction)")
    parser.add_argument("--horizon", type=int, help="Horizon (1, 3, 6, or 12)")
    parser.add_argument("--all", action="store_true", help="Optimize all 20 configs")
    parser.add_argument(
        "--baseline-only", action="store_true", help="Capture baselines only"
    )
    parser.add_argument("--report", action="store_true", help="Generate summary report")

    args = parser.parse_args()

    # Ensure output directories exist
    STUDIES_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    if args.baseline_only:
        capture_all_baselines()
    elif args.report:
        generate_report()
    elif args.all:
        optimize_all_configs()
    elif args.target and args.horizon:
        config = ConfigSpec(target=args.target, horizon=args.horizon)
        optimize_config(config)
    else:
        parser.print_help()
        print("\nExamples:")
        print("  python optimize_l2.py --target direction --horizon 6")
        print("  python optimize_l2.py --all")
        print("  python optimize_l2.py --baseline-only")
        print("  python optimize_l2.py --report")


if __name__ == "__main__":
    main()
