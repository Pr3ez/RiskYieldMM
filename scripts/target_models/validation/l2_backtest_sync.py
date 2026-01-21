"""
Synchronized L2 Backtest Module

Processes walk-forward validation ONE STEP AT A TIME across ALL 20 configs.
At each step, trains/predicts for all configs before moving to next step.

Each config has its own metric storage.

Usage:
    from scripts.target_models.validation.l2_backtest_sync import (
        SyncBacktestConfig,
        run_sync_backtest,
    )

    # Run synchronized backtest
    results = run_sync_backtest(verbose=True)
"""

from __future__ import annotations

import json
import sys
import time
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier, CatBoostRegressor
from lightgbm import LGBMClassifier, LGBMRegressor
from scipy import stats
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from scripts.target_models.validation.dataset_assembly import (
    ALL_CONFIGS,
    load_assembled,
)


@dataclass
class SyncBacktestConfig:
    """Configuration for synchronized L2 backtest."""

    # Walk-forward settings
    train_window: int = 500
    step_size: int = 1

    # Split ratios within training window
    train_ratio: float = 0.55
    val_ratio: float = 0.15
    cal_ratio: float = 0.30

    # Model settings
    random_state: int = 42
    n_estimators: int = 100
    max_depth: int = 6

    # Ensemble weights (CatBoost + LightGBM + Linear)
    cb_weight: float = 0.4
    lgb_weight: float = 0.4
    # linear_weight = 1.0 - cb_weight - lgb_weight (auto-computed)

    # CatBoost params
    cb_learning_rate: float = 0.03
    cb_l2_leaf_reg: float = 3.0

    # LightGBM params
    lgb_learning_rate: float = 0.03
    lgb_reg_lambda: float = 1.0

    # Conformal
    conformal_alpha: float = 0.1  # 90% confidence

    # Feature clipping
    duration_max: float = 1000.0

    # Output
    output_dir: Path = field(default_factory=lambda: Path("data/l2_backtest_results"))

    # Logging
    log_to_file: bool = True  # Save all print output to log file
    save_step_metrics: bool = True  # Save per-step metrics to parquet
    step_metrics_interval: int = 10  # Save metrics every N steps (avoid I/O overhead)

    def __post_init__(self):
        self.output_dir = Path(self.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)


class DualOutput:
    """Write output to both console and log file."""

    def __init__(self, log_path: Path):
        self.terminal = sys.stdout
        self.log_file = open(log_path, "w", encoding="utf-8")

    def write(self, message: str):
        self.terminal.write(message)
        self.log_file.write(message)
        self.log_file.flush()  # Ensure immediate write

    def flush(self):
        self.terminal.flush()
        self.log_file.flush()

    def close(self):
        self.log_file.close()


def _build_step_metrics(
    all_data: dict[str, ConfigData], step: int, elapsed: float
) -> tuple[list[dict], list[dict]]:
    """Build classification and regression metrics dicts for current step."""
    cls_metrics = []
    reg_metrics = []

    for config_name, data in all_data.items():
        if len(data.predictions) == 0:
            continue

        preds = pd.DataFrame(data.predictions)
        y_true_arr = preds["y_true"].values
        y_pred_arr = preds["y_pred"].values
        n_samples = len(preds)

        if data.task_type == "classification":
            # Compute classification metrics
            acc = accuracy_score(y_true_arr, y_pred_arr)

            # Individual model accuracy
            cb_preds = (
                preds["cb_pred"].values if "cb_pred" in preds.columns else y_pred_arr
            )
            lgb_preds = (
                preds["lgb_pred"].values if "lgb_pred" in preds.columns else y_pred_arr
            )
            lin_preds = (
                preds["linear_pred"].values
                if "linear_pred" in preds.columns
                else y_pred_arr
            )

            cb_acc = accuracy_score(y_true_arr, cb_preds)
            lgb_acc = accuracy_score(y_true_arr, lgb_preds)
            lin_acc = accuracy_score(y_true_arr, lin_preds)

            # AUC for binary
            is_binary = data.n_classes == 2
            if (
                is_binary
                and "y_prob" in preds.columns
                and len(np.unique(y_true_arr)) == 2
            ):
                try:
                    auc = roc_auc_score(y_true_arr, preds["y_prob"].values)
                except ValueError:
                    auc = 0.0
            else:
                auc = 0.0

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                prec = precision_score(
                    y_true_arr, y_pred_arr, average="macro", zero_division=0
                )
                rec = recall_score(
                    y_true_arr, y_pred_arr, average="macro", zero_division=0
                )
                f1 = f1_score(y_true_arr, y_pred_arr, average="macro", zero_division=0)

            cov_pct = (
                preds["covered"].mean() * 100 if preds["covered"].notna().any() else 0.0
            )

            cls_metrics.append(
                {
                    "step": step,
                    "elapsed_s": elapsed,
                    "config": config_name,
                    "n_samples": n_samples,
                    "ens_acc": acc,
                    "cb_acc": cb_acc,
                    "lgb_acc": lgb_acc,
                    "lin_acc": lin_acc,
                    "auc": auc,
                    "precision": prec,
                    "recall": rec,
                    "f1": f1,
                    "coverage_pct": cov_pct,
                    "is_binary": is_binary,
                }
            )

        else:  # regression
            y_true_f = y_true_arr.astype(float)
            y_pred_f = y_pred_arr.astype(float)

            cb_preds = (
                preds["cb_pred"].values.astype(float)
                if "cb_pred" in preds.columns
                else y_pred_f
            )
            lgb_preds = (
                preds["lgb_pred"].values.astype(float)
                if "lgb_pred" in preds.columns
                else y_pred_f
            )
            lin_preds = (
                preds["linear_pred"].values.astype(float)
                if "linear_pred" in preds.columns
                else y_pred_f
            )

            if n_samples > 1:
                ic, _ = stats.spearmanr(y_true_f, y_pred_f)
                cb_ic, _ = stats.spearmanr(y_true_f, cb_preds)
                lgb_ic, _ = stats.spearmanr(y_true_f, lgb_preds)
                lin_ic, _ = stats.spearmanr(y_true_f, lin_preds)
                ic = ic if not np.isnan(ic) else 0.0
                cb_ic = cb_ic if not np.isnan(cb_ic) else 0.0
                lgb_ic = lgb_ic if not np.isnan(lgb_ic) else 0.0
                lin_ic = lin_ic if not np.isnan(lin_ic) else 0.0
            else:
                ic = cb_ic = lgb_ic = lin_ic = 0.0

            rmse = np.sqrt(np.mean((y_true_f - y_pred_f) ** 2))
            mae = np.mean(np.abs(y_true_f - y_pred_f))
            cov_pct = (
                preds["covered"].mean() * 100 if preds["covered"].notna().any() else 0.0
            )

            reg_metrics.append(
                {
                    "step": step,
                    "elapsed_s": elapsed,
                    "config": config_name,
                    "n_samples": n_samples,
                    "ens_ic": ic,
                    "cb_ic": cb_ic,
                    "lgb_ic": lgb_ic,
                    "lin_ic": lin_ic,
                    "rmse": rmse,
                    "mae": mae,
                    "coverage_pct": cov_pct,
                }
            )

    return cls_metrics, reg_metrics


@dataclass
class ConfigData:
    """Preloaded data for a single config."""

    config_name: str
    task_type: str  # regression | classification
    target_name: str
    horizon: int
    n_classes: int | None

    X_features: pd.DataFrame  # L1 features (aligned, clipped)
    y_target: pd.Series  # Aligned targets
    pred_idx: np.ndarray  # Original pred_idx for reference

    # Per-step results storage
    predictions: list[dict] = field(default_factory=list)


def _parse_config(config_name: str) -> dict[str, Any]:
    """Parse config name to get target specification."""
    parts = config_name.rsplit("_", 1)
    target_name = parts[0]
    horizon = int(parts[1].replace("bar", ""))

    task_type = "regression"
    n_classes = None

    if target_name == "direction":
        task_type = "classification"
        n_classes = 2  # Binary: 0/1
    elif target_name == "vol_regime":
        task_type = "classification"
        n_classes = 3  # Multiclass: LOW=0, MED=1, HIGH=2
    elif target_name == "trend_regime":
        task_type = "classification"
        n_classes = 2  # Binary per registry (not 3!)

    return {
        "target": target_name,
        "horizon": horizon,
        "task_type": task_type,
        "n_classes": n_classes,
    }


def _clip_features(df: pd.DataFrame, duration_max: float = 1000.0) -> pd.DataFrame:
    """Clip extreme feature values."""
    df = df.copy()
    duration_cols = [c for c in df.columns if "duration" in c.lower()]
    for col in duration_cols:
        if col in df.columns:
            df[col] = df[col].clip(upper=duration_max)
    return df


def _load_config_data(config_name: str, config: SyncBacktestConfig) -> ConfigData:
    """Load and prepare data for a single config."""
    from scripts.target_models.registry import load_target_data

    spec = _parse_config(config_name)

    # Load assembled L1 features
    X_assembled = load_assembled(config_name)
    pred_idx = X_assembled["pred_idx"].values
    X_features = X_assembled.drop(columns=["pred_idx"])

    # Clip extreme features
    X_features = _clip_features(X_features, config.duration_max)

    # Load target data
    _, y_full, _ = load_target_data(
        target=spec["target"],
        horizon=spec["horizon"],
        drop_na=True,
        verbose=False,
    )

    # Align targets with assembled features
    y_aligned = []
    for idx in pred_idx:
        aligned_idx = int(idx) + spec["horizon"] - 1
        if aligned_idx < len(y_full):
            y_aligned.append(y_full.iloc[aligned_idx])
        else:
            y_aligned.append(np.nan)

    y_aligned = pd.Series(y_aligned)

    # Filter out NaN
    valid_mask = y_aligned.notna().values
    X_valid = X_features.iloc[valid_mask].reset_index(drop=True)
    y_valid = y_aligned[valid_mask].reset_index(drop=True)
    pred_idx_valid = pred_idx[valid_mask]

    return ConfigData(
        config_name=config_name,
        task_type=spec["task_type"],
        target_name=spec["target"],
        horizon=spec["horizon"],
        n_classes=spec["n_classes"],
        X_features=X_valid,
        y_target=y_valid,
        pred_idx=pred_idx_valid,
        predictions=[],
    )


def _train_predict_classification(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_cal: pd.DataFrame,
    y_cal: pd.Series,
    X_pred: pd.DataFrame,
    config: SyncBacktestConfig,
    n_classes: int,
) -> tuple[int, np.ndarray | None, np.ndarray | None, dict[str, Any]]:
    """Train 3-model ensemble classifier and return weighted prediction with conformal set."""
    unique_classes = np.unique(y_train)

    # Fix B2: Handle early exit with proper components (single class in training)
    if len(unique_classes) < 2:
        majority_class = int(y_train.mode().iloc[0])
        return (
            majority_class,
            None,
            None,
            {
                "models_trained": False,
                "n_train_classes": 1,
                "cb_pred": majority_class,
                "lgb_pred": majority_class,
                "linear_pred": majority_class,
            },
        )

    # Fix B1: Use config spec (n_classes) not training data to determine binary vs multiclass
    # Only direction_* configs have n_classes=2 (binary)
    # vol_regime_* and trend_regime_* have n_classes=3 (multiclass)
    is_binary = n_classes == 2

    # Suppress LightGBM GPU memory warnings
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*GPU memory available.*")
        warnings.filterwarnings("ignore", category=UserWarning)

        # CatBoost (GPU)
        cb_model = CatBoostClassifier(
            iterations=config.n_estimators,
            depth=config.max_depth,
            learning_rate=config.cb_learning_rate,
            l2_leaf_reg=config.cb_l2_leaf_reg,
            loss_function="Logloss" if is_binary else "MultiClass",
            task_type="GPU",
            devices="0",
            verbose=False,
            random_seed=config.random_state,
        )

        # LightGBM (GPU)
        if is_binary:
            lgb_model = LGBMClassifier(
                n_estimators=config.n_estimators,
                max_depth=config.max_depth,
                learning_rate=config.lgb_learning_rate,
                reg_lambda=config.lgb_reg_lambda,
                objective="binary",
                metric="auc",
                device="gpu",
                verbose=-1,
                random_state=config.random_state,
            )
        else:
            # Use actual number of classes from training data
            n_actual_classes = len(unique_classes)
            lgb_model = LGBMClassifier(
                n_estimators=config.n_estimators,
                max_depth=config.max_depth,
                learning_rate=config.lgb_learning_rate,
                reg_lambda=config.lgb_reg_lambda,
                objective="multiclass",
                metric="multi_logloss",
                num_class=n_actual_classes,
                device="gpu",
                verbose=-1,
                random_state=config.random_state,
            )

        # Linear (CPU - regularizer)
        linear_model = LogisticRegression(
            max_iter=1000, random_state=config.random_state, n_jobs=-1
        )

        # Train all models
        cb_model.fit(X_train, y_train)
        lgb_model.fit(X_train, y_train)
        linear_model.fit(X_train, y_train)

    # Get predictions
    if is_binary:
        cb_prob = cb_model.predict_proba(X_pred)[0, 1]
        lgb_prob = lgb_model.predict_proba(X_pred)[0, 1]
        linear_prob = linear_model.predict_proba(X_pred)[0, 1]

        # Weighted ensemble
        linear_weight = max(0.0, 1.0 - config.cb_weight - config.lgb_weight)
        ensemble_prob = (
            config.cb_weight * cb_prob
            + config.lgb_weight * lgb_prob
            + linear_weight * linear_prob
        )
        y_pred = int(ensemble_prob > 0.5)
        y_prob = np.array([1 - ensemble_prob, ensemble_prob])

        # Conformal prediction set (using ensemble)
        prediction_set = None
        if len(X_cal) > 10:
            try:
                cb_cal_probs = cb_model.predict_proba(X_cal)[:, 1]
                lgb_cal_probs = lgb_model.predict_proba(X_cal)[:, 1]
                linear_cal_probs = linear_model.predict_proba(X_cal)[:, 1]
                ensemble_cal_probs = (
                    config.cb_weight * cb_cal_probs
                    + config.lgb_weight * lgb_cal_probs
                    + linear_weight * linear_cal_probs
                )
                cal_probs_full = np.column_stack(
                    [1 - ensemble_cal_probs, ensemble_cal_probs]
                )
                # Clip y_cal to valid class indices (0 or 1 for binary)
                y_cal_clipped = np.clip(y_cal.astype(int), 0, 1)
                scores = 1 - cal_probs_full[np.arange(len(y_cal)), y_cal_clipped]
                threshold = np.quantile(scores, 1 - config.conformal_alpha)
                prediction_set = (1 - y_prob) <= threshold
            except Exception:
                pass

        components = {
            "models_trained": True,
            "n_train_classes": len(unique_classes),
            "cb_prob": float(cb_prob),
            "lgb_prob": float(lgb_prob),
            "linear_prob": float(linear_prob),
            "cb_pred": int(cb_prob > 0.5),
            "lgb_pred": int(lgb_prob > 0.5),
            "linear_pred": int(linear_prob > 0.5),
            "y_prob": float(ensemble_prob),  # Ensemble probability for AUC
        }
    else:
        # Multiclass
        cb_probs = cb_model.predict_proba(X_pred)[0]
        lgb_probs = lgb_model.predict_proba(X_pred)[0]
        linear_probs = linear_model.predict_proba(X_pred)[0]

        # Weighted ensemble
        linear_weight = max(0.0, 1.0 - config.cb_weight - config.lgb_weight)
        ensemble_probs = (
            config.cb_weight * cb_probs
            + config.lgb_weight * lgb_probs
            + linear_weight * linear_probs
        )
        y_pred = int(np.argmax(ensemble_probs))
        y_prob = ensemble_probs

        # Conformal prediction set
        prediction_set = None
        if len(X_cal) > 10:
            try:
                cb_cal_probs = cb_model.predict_proba(X_cal)
                lgb_cal_probs = lgb_model.predict_proba(X_cal)
                linear_cal_probs = linear_model.predict_proba(X_cal)
                ensemble_cal_probs = (
                    config.cb_weight * cb_cal_probs
                    + config.lgb_weight * lgb_cal_probs
                    + linear_weight * linear_cal_probs
                )
                # Clip y_cal to valid class indices (model may have fewer classes than data)
                n_model_classes = ensemble_cal_probs.shape[1]
                y_cal_clipped = np.clip(y_cal.astype(int), 0, n_model_classes - 1)
                scores = 1 - ensemble_cal_probs[np.arange(len(y_cal)), y_cal_clipped]
                threshold = np.quantile(scores, 1 - config.conformal_alpha)
                prediction_set = (1 - ensemble_probs) <= threshold
            except Exception:
                pass

        components = {
            "models_trained": True,
            "n_train_classes": len(unique_classes),
            "cb_pred": int(np.argmax(cb_probs)),
            "lgb_pred": int(np.argmax(lgb_probs)),
            "linear_pred": int(np.argmax(linear_probs)),
            # Store max prob for potential future use
            "cb_prob": float(np.max(cb_probs)),
            "lgb_prob": float(np.max(lgb_probs)),
            "linear_prob": float(np.max(linear_probs)),
        }

    return y_pred, y_prob, prediction_set, components


def _train_predict_regression(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_cal: pd.DataFrame,
    y_cal: pd.Series,
    X_pred: pd.DataFrame,
    y_true: float,
    config: SyncBacktestConfig,
) -> tuple[float, tuple[float, float] | None, bool | None, dict[str, Any]]:
    """Train 3-model ensemble regressor and return weighted prediction with conformal interval."""
    # Suppress LightGBM GPU memory warnings
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*GPU memory available.*")
        warnings.filterwarnings("ignore", category=UserWarning)

        # CatBoost (GPU)
        cb_model = CatBoostRegressor(
            iterations=config.n_estimators,
            depth=config.max_depth,
            learning_rate=config.cb_learning_rate,
            l2_leaf_reg=config.cb_l2_leaf_reg,
            loss_function="RMSE",
            task_type="GPU",
            devices="0",
            verbose=False,
            random_seed=config.random_state,
        )

        # LightGBM (GPU)
        lgb_model = LGBMRegressor(
            n_estimators=config.n_estimators,
            max_depth=config.max_depth,
            learning_rate=config.lgb_learning_rate,
            reg_lambda=config.lgb_reg_lambda,
            objective="regression",
            metric="rmse",
            device="gpu",
            verbose=-1,
            random_state=config.random_state,
        )

        # Linear (CPU - regularizer)
        linear_model = Ridge(alpha=1.0, random_state=config.random_state)

        # Train all models
        cb_model.fit(X_train, y_train)
        lgb_model.fit(X_train, y_train)
        linear_model.fit(X_train, y_train)

    # Get predictions
    cb_pred = cb_model.predict(X_pred)[0]
    lgb_pred = lgb_model.predict(X_pred)[0]
    linear_pred = linear_model.predict(X_pred)[0]

    # Weighted ensemble
    linear_weight = max(0.0, 1.0 - config.cb_weight - config.lgb_weight)
    y_pred = float(
        config.cb_weight * cb_pred
        + config.lgb_weight * lgb_pred
        + linear_weight * linear_pred
    )

    # Conformal interval (using ensemble)
    interval = None
    covered = None
    if len(X_cal) > 10:
        try:
            cb_cal_preds = cb_model.predict(X_cal)
            lgb_cal_preds = lgb_model.predict(X_cal)
            linear_cal_preds = linear_model.predict(X_cal)
            ensemble_cal_preds = (
                config.cb_weight * cb_cal_preds
                + config.lgb_weight * lgb_cal_preds
                + linear_weight * linear_cal_preds
            )
            residuals = np.abs(y_cal - ensemble_cal_preds)
            width = np.quantile(residuals, 1 - config.conformal_alpha)
            interval = (y_pred - width, y_pred + width)
            covered = interval[0] <= y_true <= interval[1]
        except Exception:
            pass

    components = {
        "cb_pred": float(cb_pred),
        "lgb_pred": float(lgb_pred),
        "linear_pred": float(linear_pred),
    }

    return y_pred, interval, covered, components


def _compute_config_metrics(data: ConfigData) -> dict[str, float]:
    """Compute metrics for a single config from its predictions."""
    if not data.predictions:
        return {}

    df = pd.DataFrame(data.predictions)
    y_true = df["y_true"].dropna()
    y_pred = df.loc[y_true.index, "y_pred"]

    if len(y_true) == 0:
        return {}

    metrics = {}

    if data.task_type == "regression":
        # IC
        ic, _ = stats.spearmanr(y_true, y_pred)
        metrics["ic"] = ic if not np.isnan(ic) else 0.0

        # RMSE
        rmse = np.sqrt(np.mean((y_true - y_pred) ** 2))
        metrics["rmse"] = rmse

        # MAE
        mae = np.mean(np.abs(y_true - y_pred))
        metrics["mae"] = mae

        # Coverage
        covered = df["covered"].dropna()
        if len(covered) > 0:
            metrics["coverage"] = covered.mean()

        # Mean interval width
        widths = df["interval_width"].dropna()
        if len(widths) > 0:
            metrics["mean_interval_width"] = widths.mean()

    else:
        # Accuracy
        metrics["accuracy"] = accuracy_score(y_true, y_pred)

        # F1
        metrics["f1_weighted"] = f1_score(
            y_true, y_pred, average="weighted", zero_division=0
        )

        # Coverage
        covered = df["covered"].dropna()
        if len(covered) > 0:
            metrics["coverage"] = covered.mean()

        # Mean set size
        sizes = df["set_size"].dropna()
        if len(sizes) > 0:
            metrics["mean_set_size"] = sizes.mean()

    metrics["n_predictions"] = len(df)

    return metrics


def run_sync_backtest(
    configs: list[str] | None = None,
    config: SyncBacktestConfig | None = None,
    verbose: bool = True,
) -> dict[str, dict]:
    """
    Run synchronized L2 backtest across all configs.

    At each step:
    1. Process all configs (train/predict)
    2. Store metrics for each config
    3. Move to next step

    Args:
        configs: List of config names (default: ALL_CONFIGS)
        config: Backtest configuration
        verbose: Print progress

    Returns:
        Dict mapping config_name -> {metrics, predictions_df}
    """
    warnings.filterwarnings("ignore")

    configs_list = configs or ALL_CONFIGS
    cfg = config or SyncBacktestConfig()

    start_time = time.time()

    # Setup dual output (console + log file)
    dual_output = None
    original_stdout = sys.stdout
    if cfg.log_to_file:
        log_path = cfg.output_dir / "backtest_run.log"
        dual_output = DualOutput(log_path)
        sys.stdout = dual_output

    # Accumulate per-step metrics for export
    all_cls_metrics: list[dict] = []
    all_reg_metrics: list[dict] = []

    if verbose:
        print("=" * 70)
        print("SYNCHRONIZED L2 BACKTEST - 3-MODEL ENSEMBLE")
        print("=" * 70)
        print(f"Configs: {len(configs_list)}")
        print(f"Train window: {cfg.train_window}")
        print(f"Step size: {cfg.step_size}")
        print("\nEnsemble:")
        print(
            f"  CatBoost (GPU):  weight={cfg.cb_weight:.2f}, lr={cfg.cb_learning_rate}, l2={cfg.cb_l2_leaf_reg}"
        )
        print(
            f"  LightGBM (GPU):  weight={cfg.lgb_weight:.2f}, lr={cfg.lgb_learning_rate}, l2={cfg.lgb_reg_lambda}"
        )
        linear_weight = max(0.0, 1.0 - cfg.cb_weight - cfg.lgb_weight)
        print(f"  Linear (CPU):    weight={linear_weight:.2f} (auto-computed)")
        print()

    # PHASE 1: Load all config data
    if verbose:
        print("Loading data for all configs...")

    all_data: dict[str, ConfigData] = {}
    min_samples = float("inf")

    for i, config_name in enumerate(configs_list):
        try:
            data = _load_config_data(config_name, cfg)
            all_data[config_name] = data
            min_samples = min(min_samples, len(data.X_features))
            if verbose:
                print(
                    f"  [{i + 1}/{len(configs_list)}] {config_name}: {len(data.X_features)} samples"
                )
        except Exception as e:
            print(f"  [{i + 1}/{len(configs_list)}] {config_name}: ERROR - {e}")
            continue

    if not all_data:
        raise RuntimeError("No configs loaded successfully")

    # Calculate number of iterations based on minimum samples
    n_samples = int(min_samples)
    start_idx = cfg.train_window
    n_iterations = (n_samples - start_idx) // cfg.step_size

    if verbose:
        print(f"\nMin samples across configs: {n_samples}")
        print(f"Total iterations: {n_iterations}")
        print()

    # Calculate split sizes
    train_size = int(cfg.train_window * cfg.train_ratio)
    val_size = int(cfg.train_window * cfg.val_ratio)
    cal_size = cfg.train_window - train_size - val_size

    if verbose:
        print(f"Window splits: train={train_size}, val={val_size}, cal={cal_size}")
        print()
        print("Starting walk-forward...")
        print("-" * 70)

    # PHASE 2: Walk-forward - 1 step at a time for ALL configs
    for step in range(n_iterations):
        pred_position = start_idx + step * cfg.step_size

        # Process ALL configs at this step
        for _config_idx, (_config_name, data) in enumerate(all_data.items()):
            # Skip if this config doesn't have enough data for this position
            if pred_position >= len(data.X_features):
                continue

            # Get window indices
            window_end = pred_position
            window_start = window_end - cfg.train_window

            train_end = window_start + train_size
            val_end = train_end + val_size
            cal_end = val_end + cal_size

            # Split data
            X_train = data.X_features.iloc[window_start:train_end]
            y_train = data.y_target.iloc[window_start:train_end]
            X_cal = data.X_features.iloc[val_end:cal_end]
            y_cal = data.y_target.iloc[val_end:cal_end]
            X_pred = data.X_features.iloc[[pred_position]]
            y_true = data.y_target.iloc[pred_position]

            # Train/predict based on task type with ensemble
            if data.task_type == "classification":
                y_pred, y_prob, prediction_set, components = (
                    _train_predict_classification(
                        X_train, y_train, X_cal, y_cal, X_pred, cfg, data.n_classes
                    )
                )
                covered = (
                    bool(prediction_set[int(y_true)])
                    if prediction_set is not None
                    else None
                )
                interval_width = None
                set_size = (
                    np.sum(prediction_set) if prediction_set is not None else None
                )
            else:
                y_pred, interval, covered, components = _train_predict_regression(
                    X_train, y_train, X_cal, y_cal, X_pred, y_true, cfg
                )
                prediction_set = None
                interval_width = interval[1] - interval[0] if interval else None
                set_size = None

            # Store prediction for this config
            data.predictions.append(
                {
                    "step": step,
                    "pred_position": pred_position,
                    "pred_idx": data.pred_idx[pred_position],
                    "y_pred": y_pred,
                    "y_true": y_true,
                    "covered": covered,
                    "interval_width": interval_width,
                    "set_size": set_size,
                    **components,  # Add CB/LGB/Linear component predictions
                }
            )

        # Display live metrics table after each step
        if verbose:
            # Separate tables for classification and regression
            cls_configs = [
                (n, d)
                for n, d in all_data.items()
                if d.task_type == "classification" and len(d.predictions) > 0
            ]
            reg_configs = [
                (n, d)
                for n, d in all_data.items()
                if d.task_type == "regression" and len(d.predictions) > 0
            ]

            print(f"\n{'=' * 100}")
            print(
                f"STEP {step + 1}/{n_iterations} | Elapsed: {time.time() - start_time:.1f}s"
            )
            print(f"{'=' * 100}")

            # Classification table - show ensemble + individual model accuracy + AUC
            if cls_configs:
                # Section header and column header with proper alignment
                print("\n[CLASSIFICATION]")
                print(
                    f"{'Config':<20} {'Ens':>6} {'CB':>6} {'LGB':>6} {'Lin':>6} {'AUC':>6} {'Prec':>6} {'Rec':>6} {'F1':>6} {'Cov%':>6} {'N':>5}"
                )
                print("-" * 95)
                for config_name, data in cls_configs:
                    preds = pd.DataFrame(data.predictions)
                    y_true_arr = preds["y_true"].values
                    y_pred_arr = preds["y_pred"].values
                    n_samples = len(preds)

                    # Ensemble accuracy
                    acc = accuracy_score(y_true_arr, y_pred_arr)

                    # Individual model accuracy (from stored components)
                    # Fix B4: Use cb_pred consistently (now stored for both binary and multiclass)
                    if "cb_pred" in preds.columns:
                        cb_preds = preds["cb_pred"].values
                        lgb_preds = preds["lgb_pred"].values
                        lin_preds = preds["linear_pred"].values
                    else:
                        # Fallback for early-exit or missing data
                        cb_preds = lgb_preds = lin_preds = y_pred_arr

                    # AUC: only for binary classification (use config spec, not column detection)
                    is_binary = data.n_classes == 2
                    if (
                        is_binary
                        and "y_prob" in preds.columns
                        and len(np.unique(y_true_arr)) == 2
                    ):
                        try:
                            auc = roc_auc_score(y_true_arr, preds["y_prob"].values)
                        except ValueError:
                            auc = 0.0
                    else:
                        auc = 0.0

                    cb_acc = accuracy_score(y_true_arr, cb_preds)
                    lgb_acc = accuracy_score(y_true_arr, lgb_preds)
                    lin_acc = accuracy_score(y_true_arr, lin_preds)

                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        prec = precision_score(
                            y_true_arr, y_pred_arr, average="macro", zero_division=0
                        )
                        rec = recall_score(
                            y_true_arr, y_pred_arr, average="macro", zero_division=0
                        )
                        f1 = f1_score(
                            y_true_arr, y_pred_arr, average="macro", zero_division=0
                        )

                    cov_pct = (
                        preds["covered"].mean() * 100
                        if preds["covered"].notna().any()
                        else 0.0
                    )
                    # Right-aligned values for proper column alignment
                    print(
                        f"{config_name:<20} {acc:>6.3f} {cb_acc:>6.3f} {lgb_acc:>6.3f} {lin_acc:>6.3f} {auc:>6.3f} {prec:>6.3f} {rec:>6.3f} {f1:>6.3f} {cov_pct:>6.1f} {n_samples:>5}"
                    )

            # Regression table - show ensemble + individual model IC
            if reg_configs:
                # Section header and column header with proper alignment
                print("\n[REGRESSION]")
                print(
                    f"{'Config':<20} {'Ens_IC':>7} {'CB_IC':>7} {'LGB_IC':>7} {'Lin_IC':>7} {'RMSE':>10} {'MAE':>10} {'Cov%':>6} {'N':>5}"
                )
                print("-" * 95)
                for config_name, data in reg_configs:
                    preds = pd.DataFrame(data.predictions)
                    y_true_arr = preds["y_true"].values.astype(float)
                    y_pred_arr = preds["y_pred"].values.astype(float)
                    n_samples = len(preds)

                    # Individual model predictions
                    cb_preds = (
                        preds["cb_pred"].values.astype(float)
                        if "cb_pred" in preds.columns
                        else y_pred_arr
                    )
                    lgb_preds = (
                        preds["lgb_pred"].values.astype(float)
                        if "lgb_pred" in preds.columns
                        else y_pred_arr
                    )
                    lin_preds = (
                        preds["linear_pred"].values.astype(float)
                        if "linear_pred" in preds.columns
                        else y_pred_arr
                    )

                    # IC (Spearman) for ensemble and each model
                    if n_samples > 1:
                        ic, _ = stats.spearmanr(y_true_arr, y_pred_arr)
                        cb_ic, _ = stats.spearmanr(y_true_arr, cb_preds)
                        lgb_ic, _ = stats.spearmanr(y_true_arr, lgb_preds)
                        lin_ic, _ = stats.spearmanr(y_true_arr, lin_preds)
                        ic = ic if not np.isnan(ic) else 0.0
                        cb_ic = cb_ic if not np.isnan(cb_ic) else 0.0
                        lgb_ic = lgb_ic if not np.isnan(lgb_ic) else 0.0
                        lin_ic = lin_ic if not np.isnan(lin_ic) else 0.0
                    else:
                        ic = cb_ic = lgb_ic = lin_ic = 0.0

                    # RMSE/MAE for ensemble
                    rmse = np.sqrt(np.mean((y_true_arr - y_pred_arr) ** 2))
                    mae = np.mean(np.abs(y_true_arr - y_pred_arr))

                    cov_pct = (
                        preds["covered"].mean() * 100
                        if preds["covered"].notna().any()
                        else 0.0
                    )
                    # Right-aligned values for proper column alignment
                    print(
                        f"{config_name:<20} {ic:>7.3f} {cb_ic:>7.3f} {lgb_ic:>7.3f} {lin_ic:>7.3f} {rmse:>10.6f} {mae:>10.6f} {cov_pct:>6.1f} {n_samples:>5}"
                    )

            print("-" * 95)

        # Collect step metrics for export (every N steps to reduce overhead)
        if cfg.save_step_metrics and (step + 1) % cfg.step_metrics_interval == 0:
            elapsed_so_far = time.time() - start_time
            step_cls, step_reg = _build_step_metrics(all_data, step + 1, elapsed_so_far)
            all_cls_metrics.extend(step_cls)
            all_reg_metrics.extend(step_reg)

    # PHASE 3: Compute final metrics for each config
    elapsed_total = time.time() - start_time

    if verbose:
        print("-" * 70)
        print("\nComputing metrics...")

    results = {}
    for config_name, data in all_data.items():
        metrics = _compute_config_metrics(data)
        predictions_df = pd.DataFrame(data.predictions)

        # Save predictions
        output_path = cfg.output_dir / f"{config_name}_sync_predictions.parquet"
        predictions_df.to_parquet(output_path, index=False)

        results[config_name] = {
            "task_type": data.task_type,
            "metrics": metrics,
            "predictions_df": predictions_df,
            "n_predictions": len(predictions_df),
        }

    # Print summary
    if verbose:
        print("\n" + "=" * 70)
        print("RESULTS SUMMARY")
        print("=" * 70)
        print(f"Total time: {elapsed_total:.1f}s ({elapsed_total / 60:.1f} min)")
        print(f"Iterations: {n_iterations}")
        print()

        # Classification configs
        print("CLASSIFICATION:")
        print(f"{'Config':<25} {'Accuracy':<12} {'F1':<12} {'Coverage':<12} {'N':<8}")
        print("-" * 70)
        for config_name, res in sorted(results.items()):
            if res["task_type"] == "classification":
                m = res["metrics"]
                acc = m.get("accuracy", 0)
                f1 = m.get("f1_weighted", 0)
                cov = m.get("coverage", 0)
                n = m.get("n_predictions", 0)
                print(f"{config_name:<25} {acc:<12.4f} {f1:<12.4f} {cov:<12.4f} {n:<8}")

        print()
        print("REGRESSION:")
        print(f"{'Config':<25} {'IC':<12} {'RMSE':<12} {'Coverage':<12} {'N':<8}")
        print("-" * 70)
        for config_name, res in sorted(results.items()):
            if res["task_type"] == "regression":
                m = res["metrics"]
                ic = m.get("ic", 0)
                rmse = m.get("rmse", 0)
                cov = m.get("coverage", 0)
                n = m.get("n_predictions", 0)
                print(
                    f"{config_name:<25} {ic:<12.4f} {rmse:<12.6f} {cov:<12.4f} {n:<8}"
                )

    # Save summary JSON
    summary_path = cfg.output_dir / "sync_backtest_summary.json"
    summary = {
        config_name: {
            "task_type": r["task_type"],
            "n_predictions": r["n_predictions"],
            "metrics": r["metrics"],
        }
        for config_name, r in results.items()
    }
    summary["_meta"] = {
        "elapsed_seconds": elapsed_total,
        "n_iterations": n_iterations,
        "train_window": cfg.train_window,
        "step_size": cfg.step_size,
        "n_configs": len(results),
    }

    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    if verbose:
        print(f"\nSummary saved to: {summary_path}")

    # Save per-step metrics to parquet
    if cfg.save_step_metrics:
        # Collect final step if not already collected
        if n_iterations % cfg.step_metrics_interval != 0:
            step_cls, step_reg = _build_step_metrics(
                all_data, n_iterations, elapsed_total
            )
            all_cls_metrics.extend(step_cls)
            all_reg_metrics.extend(step_reg)

        if all_cls_metrics:
            cls_df = pd.DataFrame(all_cls_metrics)
            cls_path = cfg.output_dir / "classification_metrics_history.parquet"
            cls_df.to_parquet(cls_path, index=False)
            if verbose:
                print(f"Classification metrics history saved to: {cls_path}")

        if all_reg_metrics:
            reg_df = pd.DataFrame(all_reg_metrics)
            reg_path = cfg.output_dir / "regression_metrics_history.parquet"
            reg_df.to_parquet(reg_path, index=False)
            if verbose:
                print(f"Regression metrics history saved to: {reg_path}")

    # Restore stdout and close log file
    if dual_output is not None:
        print(f"\nLog file saved to: {cfg.output_dir / 'backtest_run.log'}")
        sys.stdout = original_stdout
        dual_output.close()

    return results


if __name__ == "__main__":
    # Run with default settings
    results = run_sync_backtest(verbose=True)
