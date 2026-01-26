"""
Main backtest orchestrator service.

Contains the synchronized walk-forward backtest execution
that processes all configs step by step.
"""

from __future__ import annotations

import json
import sys
import time
import warnings
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd
from backtest.adapters.data_loader import ConfigData, load_config_data
from backtest.adapters.output import DualOutput
from backtest.core.ensemble import AdaptiveWeightTracker
from backtest.core.metrics import build_step_metrics, compute_config_metrics
from backtest.domain.config import SyncBacktestConfig
from backtest.services.training import (
    train_predict_classification_permodel,
    train_predict_regression_permodel,
)
from scipy import stats
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from scripts.analysis.signal_labels import get_target_type_from_config
from scripts.target_models.validation.combined_datasets import (
    compute_common_pred_idx_range,
)
from scripts.workflow.config import get_all_configs

if TYPE_CHECKING:
    pass


__all__ = [
    "run_sync_backtest",
    "get_label_name",
    "LABEL_NAMES",
    "ALL_CONFIGS",
]

# Re-export ALL_CONFIGS for backward compatibility
ALL_CONFIGS = get_all_configs()

# Human-readable label names for each target type
LABEL_NAMES = {
    "direction": {0: "DOWN", 1: "UP", 2: "NEUTRAL"},
    "vol_regime": {0: "LOW", 1: "MED", 2: "HIGH"},
    "trend_regime": {0: "DOWN", 1: "UP"},
}


def get_label_name(config_name: str, label_value: int) -> str:
    """Get human-readable label name for a config's prediction."""
    target_type = get_target_type_from_config(config_name)
    if target_type in LABEL_NAMES:
        return LABEL_NAMES[target_type].get(int(label_value), str(label_value))
    return str(label_value)


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
        print("SYNCHRONIZED L2 BACKTEST - 4-MODEL ENSEMBLE")
        print("=" * 70)
        print(f"Configs: {len(configs_list)}")
        print(f"Train window: {cfg.train_window}")
        print(f"Step size: {cfg.step_size}")
        print("\nEnsemble weights:")
        print(f"  CatBoost (GPU):  {cfg.cb_weight:.2f}")
        print(f"  LightGBM (GPU):  {cfg.lgb_weight:.2f}")
        print(f"  LSTM (GPU):      {cfg.lstm_weight:.2f}")
        linear_weight = max(0.0, 1.0 - cfg.cb_weight - cfg.lgb_weight - cfg.lstm_weight)
        print(f"  Linear (CPU):    {linear_weight:.2f}")
        if cfg.enable_optuna:
            print(
                f"\nOptuna tuning: ENABLED ({cfg.n_optuna_trials} trials, {cfg.optuna_timeout}s timeout)"
            )
            print("  → Hyperparameters tuned fresh at each step (CB + LGB)")
            print("  → Warm-starting from previous step's best params")
            print("  → LSTM uses fixed architecture (hidden=64, layers=2)")
        else:
            print("\nOptuna tuning: DISABLED (using fixed params)")
            print(f"  CatBoost:  lr={cfg.cb_learning_rate}, l2={cfg.cb_l2_leaf_reg}")
            print(f"  LightGBM:  lr={cfg.lgb_learning_rate}, l2={cfg.lgb_reg_lambda}")
            print(
                f"  LSTM:      hidden={cfg.lstm_hidden_size}, layers={cfg.lstm_num_layers}"
            )
        print()

    # PHASE 1: Compute common pred_idx range for synchronized loading
    if verbose:
        print("Computing common pred_idx range for alignment...")

    common_range = compute_common_pred_idx_range(configs=configs_list)
    if verbose:
        print(
            f"  Common range: pred_idx {common_range['common_start']} to "
            f"{common_range['common_end']} ({common_range['common_length']} values)"
        )

    # PHASE 2: Load all config data (aligned to common range)
    if verbose:
        print("\nLoading data for all configs (aligned)...")

    all_data: dict[str, ConfigData] = {}

    for i, config_name in enumerate(configs_list):
        try:
            data = load_config_data(config_name, cfg, common_range=common_range)
            all_data[config_name] = data
            if verbose:
                print(
                    f"  [{i + 1}/{len(configs_list)}] {config_name}: "
                    f"{len(data.X_features)} samples, "
                    f"pred_idx {data.pred_idx[0]}-{data.pred_idx[-1]}"
                )
        except Exception as e:
            print(f"  [{i + 1}/{len(configs_list)}] {config_name}: ERROR - {e}")
            continue

    if not all_data:
        raise RuntimeError("No configs loaded successfully")

    # Verify all configs have same length (alignment check)
    sample_counts = {name: len(data.X_features) for name, data in all_data.items()}
    unique_counts = set(sample_counts.values())
    if len(unique_counts) > 1:
        raise RuntimeError(
            f"Alignment failed: configs have different sample counts: {sample_counts}"
        )

    # All configs have same length now
    n_samples = list(sample_counts.values())[0]

    # Use max window size for per-model configs, otherwise shared window
    effective_window = cfg.get_max_window_size()
    max_iterations = (n_samples - effective_window) // cfg.step_size

    # Handle n_steps parameter: limit iterations or use most recent N steps
    if cfg.n_steps is not None and cfg.n_steps > 0:
        if cfg.n_steps > max_iterations:
            print(
                f"Warning: Requested {cfg.n_steps} steps but only {max_iterations} available. "
                f"Using all {max_iterations} steps."
            )
            n_iterations = max_iterations
            start_idx = effective_window  # Start from beginning
        else:
            # Use the MOST RECENT n_steps (end of data)
            n_iterations = cfg.n_steps
            # Calculate start_idx to get the last n_steps predictions
            start_idx = n_samples - (n_iterations * cfg.step_size)
    else:
        # n_steps is None or 0 → use all available
        n_iterations = max_iterations
        start_idx = effective_window

    if verbose:
        print(f"\nAligned samples across all configs: {n_samples}")
        print(f"Maximum possible iterations: {max_iterations}")
        print(f"Running iterations: {n_iterations}")
        if cfg.n_steps is not None:
            print(f"  (Limited to last {cfg.n_steps} steps as requested)")
        print(f"Start index: {start_idx}")
        # Per-model configuration is always active
        print("\nPer-model configuration (each model optimizes independently):")
        print(f"  Effective window (max): {effective_window}")
        print(
            f"  CatBoost:  window={cfg.cb_config.train_window}, selection={cfg.cb_config.feature_selection}"
        )
        print(
            f"  LightGBM:  window={cfg.lgb_config.train_window}, selection={cfg.lgb_config.feature_selection}"
        )
        print(
            f"  LSTM:      window={cfg.lstm_config.train_window}, selection={cfg.lstm_config.feature_selection}"
        )
        print(
            f"  Linear:    window={cfg.linear_config.train_window}, selection={cfg.linear_config.feature_selection}"
        )
        print()

    # Calculate split sizes (with embargo gaps per de Prado)
    # These are computed per-model in training functions using model-specific ratios
    # Values below are for reference only
    total_embargo = 2 * cfg.embargo_bars
    usable_window = effective_window - total_embargo
    train_size = int(usable_window * cfg.train_ratio)
    val_size = int(usable_window * cfg.val_ratio)
    cal_size = usable_window - train_size - val_size

    if verbose:
        print(f"Reference splits: train={train_size}, val={val_size}, cal={cal_size}")
        print(f"Embargo gap: {cfg.embargo_bars} bars between splits")
        print()
        if cfg.enable_optuna:
            print(
                f"Optuna tuning: {cfg.n_optuna_trials} trials, {cfg.optuna_timeout}s timeout (warm-started)"
            )
        else:
            print("Optuna tuning: DISABLED")
        if cfg.use_adaptive_weights:
            print(
                f"\nAdaptive weights: ENABLED (lookback={cfg.adaptive_lookback}, "
                f"lr={cfg.adaptive_learning_rate})"
            )
        else:
            print("\nAdaptive weights: DISABLED (using fixed config weights)")
        print()
        print("Starting walk-forward...")
        print("-" * 70)

    # Track best params per config for warm-starting
    config_best_params: dict[str, dict[str, dict[str, Any]]] = {}

    # Initialize adaptive weight tracker (arXiv 2304.09947 - Multiplicative Weights Update)
    adaptive_tracker = AdaptiveWeightTracker(
        lookback=cfg.adaptive_lookback,
        learning_rate=cfg.adaptive_learning_rate,
        min_weight=cfg.adaptive_min_weight,
        initial_cb_weight=cfg.cb_weight,
        initial_lgb_weight=cfg.lgb_weight,
        initial_lstm_weight=cfg.lstm_weight,
        initial_linear_weight=max(
            0.0, 1.0 - cfg.cb_weight - cfg.lgb_weight - cfg.lstm_weight
        ),
    )

    # PHASE 2: Walk-forward - 1 step at a time for ALL configs
    for step in range(n_iterations):
        pred_position = start_idx + step * cfg.step_size

        # Process ALL configs at this step
        for _config_idx, (_config_name, data) in enumerate(all_data.items()):
            # Skip if this config doesn't have enough data for this position
            if pred_position >= len(data.X_features):
                continue

            # Get previous best params for warm-starting (if any)
            previous_best = config_best_params.get(_config_name)

            # Get window indices
            window_end = pred_position
            window_start = window_end - effective_window

            # X_pred is always the same (prediction point)
            X_pred = data.X_features.iloc[[pred_position]]
            y_true = data.y_target.iloc[pred_position]

            # Per-model mode: pass full window, let training functions slice per-model
            # Each model (CB, LGB, LSTM, Linear) uses its own window size and optimization
            X_full = data.X_features.iloc[window_start:window_end]
            y_full = data.y_target.iloc[window_start:window_end]

            # Train/predict with per-model slicing
            if data.task_type == "classification":
                y_pred, y_prob, prediction_set, components, tuned_params = (
                    train_predict_classification_permodel(
                        X_full,
                        y_full,
                        X_pred,
                        cfg,
                        data.n_classes,
                        data.horizon,
                        previous_best,
                    )
                )
                # Classification post-processing
                y_true_int = int(y_true)
                if prediction_set is not None and y_true_int < len(prediction_set):
                    covered = bool(prediction_set[y_true_int])
                else:
                    covered = False
                interval_width = None
                set_size = (
                    np.sum(prediction_set) if prediction_set is not None else None
                )
            else:
                y_pred, interval, covered, components, tuned_params = (
                    train_predict_regression_permodel(
                        X_full,
                        y_full,
                        X_pred,
                        y_true,
                        cfg,
                        data.horizon,
                        previous_best,
                    )
                )
                # Regression post-processing
                prediction_set = None
                interval_width = interval[1] - interval[0] if interval else None
                set_size = None

            # Store tuned params for warm-starting next step
            config_best_params[_config_name] = tuned_params

            # Calculate prediction error
            if data.task_type == "regression":
                pred_error = float(y_true - y_pred)
                abs_pred_error = abs(pred_error)
            else:
                pred_error = None
                abs_pred_error = None

            # Get prediction datetime from timestamps (if available)
            if data.timestamps is not None and pred_position < len(data.timestamps):
                prediction_datetime = data.timestamps[pred_position]
            else:
                prediction_datetime = None

            # Store prediction for this config with comprehensive data
            data.predictions.append(
                {
                    # Core identifiers
                    "step": step,
                    "pred_position": pred_position,
                    "pred_idx": data.pred_idx[pred_position],
                    "prediction_datetime": prediction_datetime,
                    # Predictions and actuals
                    "y_pred": y_pred,
                    "y_true": float(y_true),
                    "pred_error": pred_error,
                    "abs_pred_error": abs_pred_error,
                    # Conformal metrics
                    "covered": covered,
                    "interval_width": interval_width,
                    "set_size": set_size,
                    # Window indices for debugging
                    "window_start": window_start,
                    "window_end": window_end,
                    # All component predictions and metrics
                    **components,
                }
            )

            # Record per-model accuracies for adaptive weight tracking
            # (arXiv 2304.09947: MWU online ensemble learning)
            if cfg.use_adaptive_weights:
                if data.task_type == "classification":
                    y_true_int = int(y_true)
                    # Record whether each model's prediction matched ground truth
                    adaptive_tracker.record_accuracy(
                        "cb", components.get("cb_pred") == y_true_int
                    )
                    adaptive_tracker.record_accuracy(
                        "lgb", components.get("lgb_pred") == y_true_int
                    )
                    adaptive_tracker.record_accuracy(
                        "lstm", components.get("lstm_pred") == y_true_int
                    )
                    adaptive_tracker.record_accuracy(
                        "linear", components.get("linear_pred") == y_true_int
                    )
                else:
                    # For regression: use direction accuracy (did sign match?)
                    # If y_true > 0 and pred > 0, direction is correct
                    y_true_sign = y_true > 0
                    cb_correct = (components.get("cb_pred", 0) > 0) == y_true_sign
                    lgb_correct = (components.get("lgb_pred", 0) > 0) == y_true_sign
                    lstm_correct = (components.get("lstm_pred", 0) > 0) == y_true_sign
                    linear_correct = (
                        components.get("linear_pred", 0) > 0
                    ) == y_true_sign
                    adaptive_tracker.record_accuracy("cb", cb_correct)
                    adaptive_tracker.record_accuracy("lgb", lgb_correct)
                    adaptive_tracker.record_accuracy("lstm", lstm_correct)
                    adaptive_tracker.record_accuracy("linear", linear_correct)

        # After processing all configs at this step, update adaptive weights
        if cfg.use_adaptive_weights:
            new_weights = adaptive_tracker.update_weights()
            # Apply new weights to config for next step
            cfg.cb_weight = new_weights["cb_weight"]
            cfg.lgb_weight = new_weights["lgb_weight"]
            cfg.lstm_weight = new_weights["lstm_weight"]
            # linear_weight is auto-computed as 1 - sum(others)

        # Display live metrics table after each step
        if verbose:
            _display_step_metrics(all_data, step, n_iterations, start_time)

        # Collect step metrics for export (every N steps to reduce overhead)
        if cfg.save_step_metrics and (step + 1) % cfg.step_metrics_interval == 0:
            elapsed_so_far = time.time() - start_time
            step_cls, step_reg = build_step_metrics(all_data, step + 1, elapsed_so_far)
            all_cls_metrics.extend(step_cls)
            all_reg_metrics.extend(step_reg)

    # PHASE 3: Compute final metrics for each config
    elapsed_total = time.time() - start_time

    if verbose:
        print("-" * 70)
        print("\nComputing metrics...")

    results = {}
    for config_name, data in all_data.items():
        metrics = compute_config_metrics(data)
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
        _print_results_summary(results, elapsed_total, n_iterations)

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
            step_cls, step_reg = build_step_metrics(
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


def _display_step_metrics(
    all_data: dict[str, ConfigData],
    step: int,
    n_iterations: int,
    start_time: float,
) -> None:
    """Display live metrics table after each step."""
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
    print(f"STEP {step + 1}/{n_iterations} | Elapsed: {time.time() - start_time:.1f}s")
    print(f"{'=' * 100}")

    # Latest Predictions vs Actuals for ALL configs (compact view)
    print("\n[LATEST PRED vs ACTUAL - ALL CONFIGS]")
    # Classification configs first
    if cls_configs:
        print(
            f"{'Config':<24} {'Pred':>8} {'Actual':>8} {'Match':>6} {'|':>2} {'Cum Correct':>12} {'Cum Acc%':>9}"
        )
        print("-" * 78)
        for config_name, data in sorted(cls_configs, key=lambda x: x[0]):
            last_pred = data.predictions[-1]
            y_pred = last_pred["y_pred"]
            y_true = last_pred["y_true"]
            match = "✓" if y_pred == y_true else "✗"
            # Get human-readable label names
            pred_name = get_label_name(config_name, y_pred)
            actual_name = get_label_name(config_name, y_true)
            # Cumulative stats
            preds_df = pd.DataFrame(data.predictions)
            n_total = len(preds_df)
            n_correct = (preds_df["y_pred"] == preds_df["y_true"]).sum()
            cum_acc = (n_correct / n_total * 100) if n_total > 0 else 0.0
            print(
                f"{config_name:<24} {pred_name:>8} {actual_name:>8} {match:>6} {'|':>2} {n_correct:>5}/{n_total:<6} {cum_acc:>8.1f}%"
            )
    # Regression configs
    if reg_configs:
        if cls_configs:
            print()  # Separator between cls and reg
        print(
            f"{'Config':<24} {'Pred':>10} {'Actual':>10} {'Err%':>8} {'|':>2} {'Cum Pred':>10} {'Cum Act':>10} {'Cum Err%':>9}"
        )
        print("-" * 100)
        for config_name, data in sorted(reg_configs, key=lambda x: x[0]):
            last_pred = data.predictions[-1]
            y_pred = last_pred["y_pred"]
            y_true = last_pred["y_true"]
            # Percentage error relative to actual (handle zero)
            if abs(y_true) > 1e-10:
                error_pct = ((y_pred - y_true) / abs(y_true)) * 100
            else:
                error_pct = 0.0 if abs(y_pred) < 1e-10 else float("inf")
            # Format with sign and %
            if abs(error_pct) == float("inf"):
                err_str = "   inf%"
            else:
                err_str = f"{error_pct:>+7.1f}%"
            # Cumulative stats
            preds_df = pd.DataFrame(data.predictions)
            cum_pred = preds_df["y_pred"].sum()
            cum_actual = preds_df["y_true"].sum()
            if abs(cum_actual) > 1e-10:
                cum_err_pct = ((cum_pred - cum_actual) / abs(cum_actual)) * 100
                cum_err_str = f"{cum_err_pct:>+8.1f}%"
            else:
                cum_err_str = "    0.0%" if abs(cum_pred) < 1e-10 else "    inf%"
            print(
                f"{config_name:<24} {y_pred:>10.6f} {y_true:>10.6f} {err_str} {'|':>2} {cum_pred:>10.4f} {cum_actual:>10.4f} {cum_err_str}"
            )

    # Classification table - show ensemble + individual model accuracy + AUC
    if cls_configs:
        # Section header and column header with proper alignment
        print("\n[CLASSIFICATION]")
        print(
            f"{'Config':<20} {'Ens':>6} {'CB':>6} {'LGB':>6} {'LSTM':>6} {'Lin':>6} {'AUC':>6} {'Prec':>6} {'Rec':>6} {'F1':>6} {'N':>5}"
        )
        print("-" * 105)
        for config_name, data in cls_configs:
            preds = pd.DataFrame(data.predictions)
            y_true_arr = preds["y_true"].values
            y_pred_arr = preds["y_pred"].values
            n_samples = len(preds)

            # Ensemble accuracy
            acc = accuracy_score(y_true_arr, y_pred_arr)

            # Individual model accuracy (from stored components)
            if "cb_pred" in preds.columns:
                cb_preds = preds["cb_pred"].values
                lgb_preds = preds["lgb_pred"].values
                lstm_preds = (
                    preds["lstm_pred"].values
                    if "lstm_pred" in preds.columns
                    else y_pred_arr
                )
                lin_preds = preds["linear_pred"].values
            else:
                # Fallback for early-exit or missing data
                cb_preds = lgb_preds = lstm_preds = lin_preds = y_pred_arr

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
            lstm_acc = accuracy_score(y_true_arr, lstm_preds)
            lin_acc = accuracy_score(y_true_arr, lin_preds)

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                prec = precision_score(
                    y_true_arr, y_pred_arr, average="macro", zero_division=0
                )
                rec = recall_score(
                    y_true_arr, y_pred_arr, average="macro", zero_division=0
                )
                f1 = f1_score(y_true_arr, y_pred_arr, average="macro", zero_division=0)

            # Right-aligned values for proper column alignment
            print(
                f"{config_name:<20} {acc:>6.3f} {cb_acc:>6.3f} {lgb_acc:>6.3f} {lstm_acc:>6.3f} {lin_acc:>6.3f} {auc:>6.3f} {prec:>6.3f} {rec:>6.3f} {f1:>6.3f} {n_samples:>5}"
            )

    # Regression table - show ensemble + individual model IC
    if reg_configs:
        # Section header and column header with proper alignment
        print("\n[REGRESSION]")
        print(
            f"{'Config':<20} {'Ens_IC':>7} {'CB_IC':>7} {'LGB_IC':>7} {'LSTM_IC':>7} {'Lin_IC':>7} {'RMSE':>10} {'MAE':>10} {'N':>5}"
        )
        print("-" * 100)
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
            lstm_preds = (
                preds["lstm_pred"].values.astype(float)
                if "lstm_pred" in preds.columns
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
                lstm_ic, _ = stats.spearmanr(y_true_arr, lstm_preds)
                lin_ic, _ = stats.spearmanr(y_true_arr, lin_preds)
                ic = ic if not np.isnan(ic) else 0.0
                cb_ic = cb_ic if not np.isnan(cb_ic) else 0.0
                lgb_ic = lgb_ic if not np.isnan(lgb_ic) else 0.0
                lstm_ic = lstm_ic if not np.isnan(lstm_ic) else 0.0
                lin_ic = lin_ic if not np.isnan(lin_ic) else 0.0
            else:
                ic = cb_ic = lgb_ic = lstm_ic = lin_ic = 0.0

            # RMSE/MAE for ensemble
            rmse = np.sqrt(np.mean((y_true_arr - y_pred_arr) ** 2))
            mae = np.mean(np.abs(y_true_arr - y_pred_arr))

            # Right-aligned values for proper column alignment
            print(
                f"{config_name:<20} {ic:>7.3f} {cb_ic:>7.3f} {lgb_ic:>7.3f} {lstm_ic:>7.3f} {lin_ic:>7.3f} {rmse:>10.6f} {mae:>10.6f} {n_samples:>5}"
            )

    print("-" * 100)


def _print_results_summary(
    results: dict[str, dict],
    elapsed_total: float,
    n_iterations: int,
) -> None:
    """Print final results summary."""
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
            print(f"{config_name:<25} {ic:<12.4f} {rmse:<12.6f} {cov:<12.4f} {n:<8}")
