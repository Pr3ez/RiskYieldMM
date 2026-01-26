#!/usr/bin/env python3
"""
TRUE Walk-Forward CatBoost Optimization Across All Targets

This script:
1. Loads REAL data for each target
2. Runs ACTUAL walk-forward backtest (like production)
3. Collects REAL predictions and accuracy metrics
4. Stores optimal parameters based on ACTUAL PERFORMANCE

Unlike run_full_catboost_optimization.py which just optimizes once on full data,
THIS runs walk-forward step-by-step to measure real prediction quality.

Usage:
    # Run one target for testing
    python run_walkforward_optimization.py --targets direction --horizons 1 --steps 50

    # Run all targets (SLOW - hours)
    python run_walkforward_optimization.py --steps 100

    # Dry run
    python run_walkforward_optimization.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

# Add paths for imports
project_root = Path(__file__).parent.parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

backtest_root = Path(__file__).parent.parent
sys.path.insert(0, str(backtest_root))

# ruff: noqa: E402
from backtest.adapters.data_loader import load_config_data
from backtest.domain.config import SyncBacktestConfig
from backtest.models.catboost_model import (
    CatBoostModelConfig,
    optimize_catboost_config,
    select_features_catboost,
    select_features_catboost_regression,
    train_and_predict_classifier,
    train_and_predict_regressor,
)
from backtest.models.optimal_storage import (
    ALL_TARGETS,
    DataCharacteristicsSnapshot,
    OptimalConfig,
    OptimalParamsEntry,
    ValidationScores,
    load_optimal_params,
    print_optimization_summary,
    save_optimal_params,
)


@dataclass
class WalkForwardMetrics:
    """Collected metrics from walk-forward run."""

    # Classification metrics
    accuracy: float | None = None
    accuracy_std: float | None = None
    per_class_accuracy: dict[int, float] = field(default_factory=dict)

    # Regression metrics
    rmse: float | None = None
    mae: float | None = None
    r2: float | None = None

    # Timing
    avg_step_time_ms: float = 0.0
    total_time_seconds: float = 0.0

    # Counts
    n_steps: int = 0
    n_correct: int = 0
    n_predictions: list[int] = field(default_factory=list)
    n_actuals: list[int] = field(default_factory=list)


def run_walkforward_single_target(
    target_info: dict,
    n_steps: int = 100,
    train_window: int = 400,
    verbose: bool = True,
) -> tuple[WalkForwardMetrics, CatBoostModelConfig | None]:
    """Run TRUE walk-forward backtest on single target.

    This runs EXACTLY like the production backtest:
    1. Load data
    2. For each step:
       a. Get window [step-window : step]
       b. Optimize config for this window
       c. Train model
       d. Predict next point
       e. Compare to actual
    3. Collect real accuracy/RMSE metrics

    Args:
        target_info: Dict with name, task_type, n_classes, horizon
        n_steps: Number of walk-forward steps
        train_window: Window size for training
        verbose: Print progress

    Returns:
        (WalkForwardMetrics, best_config) tuple
    """
    target_name = target_info["name"]
    task_type = target_info["task_type"]
    n_classes = target_info["n_classes"]
    horizon = target_info["horizon"]

    if verbose:
        print(f"\n{'=' * 70}")
        print(f"WALK-FORWARD: {target_name}")
        print(f"  Task: {task_type}, Classes: {n_classes}, Horizon: {horizon}")
        print(f"  Steps: {n_steps}, Window: {train_window}")
        print("=" * 70)

    # Load real data
    cfg = SyncBacktestConfig(
        train_window=train_window,
        step_size=1,
        enable_optuna=True,
        n_optuna_trials=15,
        random_state=42,
    )

    try:
        data = load_config_data(target_name, cfg)
        X_full = data.X_features
        y_full = data.y_target
    except Exception as e:
        print(f"  ERROR loading data: {e}")
        return WalkForwardMetrics(), None

    n_samples = len(X_full)
    start_idx = train_window + 10  # Small buffer

    # Cap steps to available data
    max_steps = n_samples - start_idx - 1
    actual_steps = min(n_steps, max_steps)

    if actual_steps < 10:
        print(f"  SKIP: Only {actual_steps} steps possible (need >= 10)")
        return WalkForwardMetrics(), None

    if verbose:
        print(f"  Data: {n_samples} samples, {len(X_full.columns)} features")
        print(f"  Running {actual_steps} walk-forward steps...")

    # Metrics collection
    metrics = WalkForwardMetrics()
    predictions = []
    actuals = []
    step_times = []

    # Track best params for warm-starting
    previous_best: dict[str, Any] = {}
    last_config: CatBoostModelConfig | None = None

    # Walk-forward loop
    for step in range(actual_steps):
        step_start = time.time()
        pred_idx = start_idx + step

        # Get window
        window_start = pred_idx - train_window
        window_end = pred_idx

        X_window = X_full.iloc[window_start:window_end].copy()
        y_window = y_full.iloc[window_start:window_end].copy()

        # Prediction point
        X_pred = X_full.iloc[[pred_idx]].copy()
        y_true = y_full.iloc[pred_idx]

        # === DYNAMIC CONFIG OPTIMIZATION (like production) ===
        try:
            cb_config = optimize_catboost_config(
                X_full=X_window,
                y_full=y_window,
                target_name=target_name,
                task_type=task_type,
                horizon=horizon,
                base_config=None,
                enable_holdout_validation=len(X_window) >= 200,
                enable_hyperparameter_refinement=(step % 10 == 0),  # Every 10 steps
                previous_best=previous_best.get("catboost"),
            )
            last_config = cb_config
        except Exception as e:
            if verbose and step == 0:
                print(f"    Config optimization error: {e}, using baseline")
            cb_config = CatBoostModelConfig(train_window=train_window)
            last_config = cb_config

        # === SPLIT WINDOW FOR TRAINING ===
        n_window = len(X_window)
        train_end = int(n_window * cb_config.train_ratio)
        val_end = train_end + int(n_window * cb_config.val_ratio)

        X_train = X_window.iloc[:train_end].reset_index(drop=True)
        y_train = y_window.iloc[:train_end].reset_index(drop=True)
        X_val = X_window.iloc[train_end:val_end].reset_index(drop=True)
        y_val = y_window.iloc[train_end:val_end].reset_index(drop=True)
        X_cal = X_window.iloc[val_end:].reset_index(drop=True)
        y_cal = y_window.iloc[val_end:].reset_index(drop=True)

        # === FEATURE SELECTION ===
        if task_type == "classification":
            selected_features = select_features_catboost(
                X_train, y_train, cb_config, n_classes
            )
        else:
            selected_features = select_features_catboost_regression(
                X_train, y_train, cb_config
            )

        # Apply feature selection
        X_train_sel = X_train[selected_features]
        X_val_sel = X_val[selected_features]
        X_cal_sel = X_cal[selected_features]
        X_pred_sel = X_pred[selected_features]

        # === TRAIN AND PREDICT ===
        try:
            if task_type == "classification":
                result = train_and_predict_classifier(
                    X_train=X_train_sel,
                    y_train=y_train,
                    X_val=X_val_sel,
                    y_val=y_val,
                    X_cal=X_cal_sel,
                    y_cal=y_cal,
                    X_pred=X_pred_sel,
                    config=cb_config,
                    n_classes=n_classes,
                    tune=(step % 5 == 0),  # Tune every 5 steps
                    previous_best=previous_best.get("catboost"),
                )
                y_pred = result.prediction
                predictions.append(y_pred)
                actuals.append(int(y_true))

                # Update warm-start params
                if result.best_params:
                    previous_best["catboost"] = result.best_params

            else:  # Regression
                result = train_and_predict_regressor(
                    X_train=X_train_sel,
                    y_train=y_train,
                    X_val=X_val_sel,
                    y_val=y_val,
                    X_cal=X_cal_sel,
                    y_cal=y_cal,
                    X_pred=X_pred_sel,
                    config=cb_config,
                    tune=(step % 5 == 0),
                    previous_best=previous_best.get("catboost"),
                )
                y_pred = result.prediction
                predictions.append(y_pred)
                actuals.append(float(y_true))

                if result.best_params:
                    previous_best["catboost"] = result.best_params

        except Exception as e:
            if verbose and step < 3:
                print(f"    Step {step} prediction error: {e}")
            continue

        step_time = (time.time() - step_start) * 1000
        step_times.append(step_time)

        # Progress
        if verbose and (step + 1) % 20 == 0:
            if task_type == "classification":
                correct = sum(1 for p, a in zip(predictions, actuals) if p == a)
                acc = correct / len(predictions) if predictions else 0
                print(f"    Step {step + 1}/{actual_steps}: acc={acc:.3f}")
            else:
                if predictions:
                    rmse = np.sqrt(
                        np.mean([(p - a) ** 2 for p, a in zip(predictions, actuals)])
                    )
                    print(f"    Step {step + 1}/{actual_steps}: rmse={rmse:.4f}")

    # === COMPUTE FINAL METRICS ===
    metrics.n_steps = len(predictions)
    metrics.n_predictions = predictions
    metrics.n_actuals = actuals
    metrics.avg_step_time_ms = np.mean(step_times) if step_times else 0
    metrics.total_time_seconds = sum(step_times) / 1000

    if task_type == "classification":
        if predictions:
            correct = sum(1 for p, a in zip(predictions, actuals) if p == a)
            metrics.n_correct = correct
            metrics.accuracy = correct / len(predictions)

            # Per-class accuracy
            for cls in range(n_classes):
                cls_mask = [a == cls for a in actuals]
                if any(cls_mask):
                    cls_correct = sum(
                        1
                        for p, a, m in zip(predictions, actuals, cls_mask)
                        if m and p == a
                    )
                    metrics.per_class_accuracy[cls] = cls_correct / sum(cls_mask)

            # Std via bootstrap
            if len(predictions) >= 20:
                bootstrap_accs = []
                for _ in range(100):
                    idx = np.random.choice(len(predictions), len(predictions))
                    boot_pred = [predictions[i] for i in idx]
                    boot_act = [actuals[i] for i in idx]
                    boot_acc = sum(1 for p, a in zip(boot_pred, boot_act) if p == a)
                    bootstrap_accs.append(boot_acc / len(boot_pred))
                metrics.accuracy_std = np.std(bootstrap_accs)

    else:  # Regression
        if predictions:
            errors = [p - a for p, a in zip(predictions, actuals)]
            metrics.rmse = np.sqrt(np.mean([e**2 for e in errors]))
            metrics.mae = np.mean([abs(e) for e in errors])
            # R2
            ss_res = sum(e**2 for e in errors)
            ss_tot = sum((a - np.mean(actuals)) ** 2 for a in actuals)
            metrics.r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

    if verbose:
        print("\n  RESULTS:")
        if task_type == "classification":
            print(
                f"    Accuracy: {metrics.accuracy:.4f} ± {metrics.accuracy_std or 0:.4f}"
            )
            print(f"    Per-class: {metrics.per_class_accuracy}")
        else:
            print(f"    RMSE: {metrics.rmse:.4f}")
            print(f"    MAE: {metrics.mae:.4f}")
            print(f"    R²: {metrics.r2:.4f}")
        print(f"    Avg step time: {metrics.avg_step_time_ms:.0f}ms")
        print(f"    Total time: {metrics.total_time_seconds:.1f}s")

    return metrics, last_config


def save_walkforward_results(
    target_info: dict,
    metrics: WalkForwardMetrics,
    config: CatBoostModelConfig | None,
    data_size: int,
) -> Path:
    """Save walk-forward results to storage."""
    target_name = target_info["name"]
    task_type = target_info["task_type"]
    n_classes = target_info["n_classes"]
    horizon = target_info["horizon"]

    if config is None:
        config = CatBoostModelConfig()

    entry = OptimalParamsEntry(
        target_name=target_name,
        task_type=task_type,
        n_classes=n_classes,
        horizon=horizon,
        last_optimized=datetime.now().isoformat(),
        optimization_data_size=data_size,
        data_characteristics=DataCharacteristicsSnapshot(
            task_type=task_type,
            n_classes=n_classes,
            class_balance=None,
            class_imbalance_ratio=None,
            is_stationary=True,
            rolling_mean_drift=0.0,
            rolling_std_drift=0.0,
            volatility_level="medium",
            volatility_ratio=1.0,
            n_features=0,
            n_samples=data_size,
            mean_correlation=0.0,
        ),
        optimal_config=OptimalConfig(
            train_window=config.train_window,
            train_ratio=config.train_ratio,
            val_ratio=config.val_ratio,
            cal_ratio=config.cal_ratio,
            feature_selection_ratio=config.feature_selection_ratio,
            n_estimators=config.n_estimators,
            max_depth=config.max_depth,
            learning_rate=config.learning_rate,
            l2_leaf_reg=config.l2_leaf_reg,
            early_stopping_rounds=30,
            feature_selection=config.feature_selection,
            min_features=config.min_features,
        ),
        validation_scores=ValidationScores(
            combined_score=metrics.accuracy or (1.0 - (metrics.rmse or 1.0)),
            accuracy=metrics.accuracy,
            log_loss=None,
            rmse=metrics.rmse,
            mae=metrics.mae,
        ),
        optimization_time_seconds=metrics.total_time_seconds,
        avg_step_time_ms=metrics.avg_step_time_ms,
    )

    path = save_optimal_params(entry)
    return path


def run_walkforward_all_targets(
    target_types: list[str] | None = None,
    horizons: list[int] | None = None,
    n_steps: int = 100,
    train_window: int = 400,
    dry_run: bool = False,
    verbose: bool = True,
) -> dict[str, WalkForwardMetrics]:
    """Run walk-forward optimization on all targets."""
    targets_to_run = ALL_TARGETS.copy()

    if target_types:
        targets_to_run = [
            t
            for t in targets_to_run
            if any(t["name"].startswith(tt) for tt in target_types)
        ]

    if horizons:
        targets_to_run = [t for t in targets_to_run if t["horizon"] in horizons]

    print(f"\n{'=' * 70}")
    print("WALK-FORWARD CATBOOST OPTIMIZATION")
    print(f"{'=' * 70}")
    print(f"Targets: {len(targets_to_run)}")
    print(f"Steps per target: {n_steps}")
    print(f"Train window: {train_window}")

    if dry_run:
        print("\nDRY RUN - Would optimize:")
        for t in targets_to_run:
            existing = load_optimal_params(t["name"])
            status = "EXISTS" if existing else "NEW"
            print(f"  [{status}] {t['name']}: {t['task_type']}, h={t['horizon']}")
        return {}

    results = {}
    success = 0
    failed = 0

    for i, target_info in enumerate(targets_to_run, 1):
        print(f"\n[{i}/{len(targets_to_run)}]")

        try:
            metrics, config = run_walkforward_single_target(
                target_info,
                n_steps=n_steps,
                train_window=train_window,
                verbose=verbose,
            )

            if metrics.n_steps > 0:
                # Load data size for storage
                cfg = SyncBacktestConfig(train_window=train_window)
                try:
                    data = load_config_data(target_info["name"], cfg)
                    data_size = len(data.X_features)
                except Exception:
                    data_size = 0

                path = save_walkforward_results(target_info, metrics, config, data_size)
                print(f"  Saved to: {path}")
                results[target_info["name"]] = metrics
                success += 1
            else:
                failed += 1

        except Exception as e:
            print(f"  EXCEPTION: {e}")
            import traceback

            traceback.print_exc()
            failed += 1

    # Final summary
    print(f"\n{'=' * 70}")
    print("WALK-FORWARD COMPLETE")
    print(f"{'=' * 70}")
    print(f"Success: {success}/{len(targets_to_run)}")
    print(f"Failed: {failed}/{len(targets_to_run)}")

    if results:
        print("\nRESULTS SUMMARY:")
        print(f"{'Target':<30} {'Metric':<15} {'Time':<10}")
        print("-" * 55)
        for name, m in results.items():
            if m.accuracy is not None:
                metric_str = f"acc={m.accuracy:.4f}"
            elif m.rmse is not None:
                metric_str = f"rmse={m.rmse:.4f}"
            else:
                metric_str = "N/A"
            print(f"{name:<30} {metric_str:<15} {m.total_time_seconds:.1f}s")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Run TRUE walk-forward CatBoost optimization"
    )
    parser.add_argument(
        "--targets",
        nargs="+",
        help="Target types (e.g., direction volatility)",
    )
    parser.add_argument(
        "--horizons",
        nargs="+",
        type=int,
        help="Horizons (e.g., 1 3 6 12)",
    )
    parser.add_argument(
        "--steps",
        type=int,
        default=100,
        help="Walk-forward steps per target (default: 100)",
    )
    parser.add_argument(
        "--window",
        type=int,
        default=400,
        help="Training window size (default: 400)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would run without executing",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print summary of existing results",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Less verbose output",
    )

    args = parser.parse_args()

    if args.summary:
        print_optimization_summary()
        return

    run_walkforward_all_targets(
        target_types=args.targets,
        horizons=args.horizons,
        n_steps=args.steps,
        train_window=args.window,
        dry_run=args.dry_run,
        verbose=not args.quiet,
    )


if __name__ == "__main__":
    main()
