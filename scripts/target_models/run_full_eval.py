#!/usr/bin/env python
"""
Full Pipeline Evaluation: Layer 1 + Layer 2 for all 20 target-horizons.

This script:
1. Re-optimizes Layer 1 helpers with horizon-aligned architecture
2. Runs full L1→L2 pipeline for 500 walk-forward iterations
3. Evaluates performance metrics for each target-horizon

Usage:
    python -m scripts.target_models.run_full_eval
    python -m scripts.target_models.run_full_eval --backtest-rows 100 --targets volatility direction
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from .pipeline import extract_aligned_probability


@dataclass
class EvaluationResult:
    """Evaluation metrics for one target-horizon."""

    target: str
    horizon: int
    n_iterations: int

    # Prediction accuracy
    mean_ic: float  # Spearman correlation with actuals
    hit_rate: float  # % of correct direction (classification/direction)
    mse: float  # Mean squared error (regression)

    # Horizon alignment
    pred_size: int  # Number of predictions per step
    aligned_ic: float  # IC using only aligned (last) prediction

    # Layer metrics
    l1_mean_ic: float  # Average helper IC
    l2_train_loss: float  # Average L2 training loss

    # Runtime
    runtime_seconds: float


def evaluate_predictions(
    y_pred: np.ndarray,
    y_true: np.ndarray,
    task_type: str,
) -> dict[str, float]:
    """Compute evaluation metrics.

    Args:
        y_pred: Predictions
        y_true: Ground truth
        task_type: 'binary', 'multiclass', or 'regression'

    Returns:
        Dict of metrics
    """
    # Filter valid pairs
    valid = ~(np.isnan(y_pred) | np.isnan(y_true))
    if valid.sum() < 10:
        return {"ic": 0.0, "hit_rate": 0.0, "mse": 0.0}

    y_pred_valid = y_pred[valid]
    y_true_valid = y_true[valid]

    metrics = {}

    # IC (Spearman correlation)
    try:
        ic, _ = spearmanr(y_pred_valid, y_true_valid)
        metrics["ic"] = float(ic) if not np.isnan(ic) else 0.0
    except Exception:
        metrics["ic"] = 0.0

    # Hit rate (for classification or direction)
    if task_type in ("binary", "multiclass"):
        # For probabilities, threshold at 0.5 for binary
        if task_type == "binary":
            pred_class = (y_pred_valid > 0.5).astype(int)
            true_class = y_true_valid.astype(int)
        else:
            pred_class = np.round(y_pred_valid).astype(int)
            true_class = y_true_valid.astype(int)
        metrics["hit_rate"] = float((pred_class == true_class).mean())
    else:
        # For regression, use sign match as "hit rate"
        sign_match = np.sign(y_pred_valid) == np.sign(y_true_valid)
        metrics["hit_rate"] = float(sign_match.mean())

    # MSE
    metrics["mse"] = float(np.mean((y_pred_valid - y_true_valid) ** 2))

    return metrics


def run_single_target_eval(
    target: str,
    horizon: int,
    backtest_rows: int = 500,
    verbose: bool = True,
) -> EvaluationResult:
    """Run full L1→L2 evaluation for one target-horizon.

    Args:
        target: Target name
        horizon: Prediction horizon
        backtest_rows: Number of walk-forward iterations
        verbose: Print progress

    Returns:
        EvaluationResult with all metrics
    """
    from scripts.target_models.core.aligned_dual_window import (
        AlignedDualEngine,
        create_aligned_config,
    )
    from scripts.target_models.helpers import create_helper_ensemble
    from scripts.target_models.models import create_model_ensemble
    from scripts.target_models.registry import load_target_data

    start_time = time.time()

    # Load data
    X, y, spec = load_target_data(target, horizon, drop_na=True, verbose=False)

    if verbose:
        print(f"\n{'=' * 60}")
        print(f"{target}_{horizon}bar")
        print(f"{'=' * 60}")
        print(f"  Data: {len(X)} rows")
        print(f"  Task: {spec.task_type}")

    # Create aligned config with horizon-specific pred_size
    config = create_aligned_config(
        target=target,
        horizon=horizon,
        l1_min_warmup=500,
        l2_window_size=500,
        backtest_rows=backtest_rows,
    )

    # Verify pred_size = horizon
    assert config.l2.pred_size == horizon, (
        f"pred_size should be {horizon}, got {config.l2.pred_size}"
    )

    # Create engine
    engine = AlignedDualEngine(X, y, config)

    if verbose:
        print(f"  Iterations: {engine.n_iterations}")
        print(f"  First pred idx: {engine.first_pred_idx}")
        print(f"  Pred size: {config.l2.pred_size} (horizon-aligned)")

    # Storage for predictions
    all_aligned_preds = []
    all_aligned_true = []
    all_full_preds = []
    all_full_true = []
    l1_ics = []
    l2_losses = []

    # Walk-forward iteration
    for i, window in enumerate(engine.iterate()):
        try:
            # === LAYER 1: Fit helpers ===
            helper_ensemble = create_helper_ensemble(
                target=target,
                horizon=horizon,
                random_state=42 + window.iteration,
            )

            # Fit on L1 train
            X_l1_train = X.iloc[window.l1.train.start_idx : window.l1.train.end_idx]
            helper_ensemble.fit(X_l1_train)

            # Optimize on L1 cal (using target-specific y)
            X_l1_cal = X.iloc[window.l1.val.start_idx : window.l1.val.end_idx]
            y_l1_cal = y.iloc[window.l1.val.start_idx : window.l1.val.end_idx]
            opt_result = helper_ensemble.optimize(X_l1_cal, y_l1_cal)
            l1_ics.append(opt_result.get("mean_abs_ic", 0.0))

            # === LAYER 2: Generate features and train supervised model ===

            # Get L2 data range
            l2 = window.l2
            l2_start = l2.train.start_idx
            l2_end = l2.pred.end_idx
            X_l2_full = X.iloc[l2_start:l2_end]

            # Transform to helper features
            helper_output = helper_ensemble.transform(X_l2_full)
            X_l2_features = helper_output.features.reset_index(drop=True)
            y_l2 = y.iloc[l2_start:l2_end].reset_index(drop=True)

            # Compute local indices within L2
            train_len = l2.train.end_idx - l2.train.start_idx
            cal_start = train_len + (l2.cal.start_idx - l2.train.end_idx)
            cal_len = l2.cal.end_idx - l2.cal.start_idx
            val_start = cal_start + cal_len + (l2.val.start_idx - l2.cal.end_idx)
            val_len = l2.val.end_idx - l2.val.start_idx
            pred_start = val_start + val_len + (l2.pred.start_idx - l2.val.end_idx)

            # Split
            X_train = X_l2_features.iloc[:train_len]
            y_train = y_l2.iloc[:train_len]
            X_cal = X_l2_features.iloc[cal_start : cal_start + cal_len]
            y_cal = y_l2.iloc[cal_start : cal_start + cal_len]
            X_val = X_l2_features.iloc[val_start : val_start + val_len]
            y_val = y_l2.iloc[val_start : val_start + val_len]
            # Predict horizon rows for alignment
            X_pred = X_l2_features.iloc[pred_start : pred_start + horizon]

            # Create and fit model ensemble
            model_ensemble = create_model_ensemble(
                target=target,
                horizon=horizon,
                task_type=spec.task_type,
                n_classes=spec.n_classes,
                random_state=42 + window.iteration,
            )

            model_ensemble.fit(X_train, y_train, X_val=X_val, y_val=y_val)

            # Calibrate (classification only)
            if spec.task_type != "regression":
                model_ensemble.calibrate(X_cal, y_cal, method="isotonic")

            # Predict
            output = model_ensemble.predict(X_pred)

            # Get predictions and ground truth
            y_pred = output.y_pred
            y_prob = (
                output.y_prob_calibrated
                if output.y_prob_calibrated is not None
                else output.y_prob
            )

            # Ground truth for horizon predictions
            pred_idx = window.l2.pred.start_idx
            y_true = y.iloc[pred_idx : pred_idx + horizon].values

            # Store all predictions
            all_full_preds.extend(y_pred)
            all_full_true.extend(y_true)

            # Store aligned (last) predictions
            # For regression: use prediction directly
            # For classification: extract P(positive) from [n_samples, n_classes] array
            if spec.task_type == "regression":
                aligned_pred = float(y_pred[-1])
            else:
                aligned_pred = extract_aligned_probability(y_prob, spec.task_type)
            aligned_true = y_true[-1]
            all_aligned_preds.append(aligned_pred)
            all_aligned_true.append(aligned_true)

            # Progress
            if verbose and i % 100 == 0:
                print(f"  Iteration {i}/{engine.n_iterations}...")

        except Exception as e:
            if verbose:
                print(f"  Warning: Iteration {i} failed: {e}")
            continue

    # Compute final metrics
    all_aligned_preds = np.array(all_aligned_preds)
    all_aligned_true = np.array(all_aligned_true)
    all_full_preds = np.array(all_full_preds)
    all_full_true = np.array(all_full_true)

    aligned_metrics = evaluate_predictions(
        all_aligned_preds, all_aligned_true, spec.task_type
    )
    full_metrics = evaluate_predictions(all_full_preds, all_full_true, spec.task_type)

    runtime = time.time() - start_time

    result = EvaluationResult(
        target=target,
        horizon=horizon,
        n_iterations=len(all_aligned_preds),
        mean_ic=full_metrics["ic"],
        hit_rate=full_metrics["hit_rate"],
        mse=full_metrics["mse"],
        pred_size=horizon,
        aligned_ic=aligned_metrics["ic"],
        l1_mean_ic=np.mean(l1_ics) if l1_ics else 0.0,
        l2_train_loss=np.mean(l2_losses) if l2_losses else 0.0,
        runtime_seconds=runtime,
    )

    if verbose:
        print("\n  Results:")
        print(f"    Aligned IC: {result.aligned_ic:.4f}")
        print(f"    Full IC: {result.mean_ic:.4f}")
        print(f"    Hit Rate: {result.hit_rate:.2%}")
        print(f"    L1 Mean IC: {result.l1_mean_ic:.4f}")
        print(f"    Runtime: {result.runtime_seconds:.1f}s")

    return result


def run_full_evaluation(
    targets: list[str] | None = None,
    horizons: list[int] | None = None,
    backtest_rows: int = 500,
    output_dir: str | Path = "data/pipeline_results",
    verbose: bool = True,
) -> pd.DataFrame:
    """Run full evaluation for all target-horizons.

    Args:
        targets: List of targets (None = all 5)
        horizons: List of horizons (None = all 4)
        backtest_rows: Number of walk-forward iterations per target
        output_dir: Directory for output files
        verbose: Print progress

    Returns:
        DataFrame with all results
    """
    if targets is None:
        targets = ["volatility", "returns", "direction", "vol_regime", "trend_regime"]
    if horizons is None:
        horizons = [1, 3, 6, 12]

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print("FULL PIPELINE EVALUATION")
    print("=" * 80)
    print(f"Targets: {targets}")
    print(f"Horizons: {horizons}")
    print(f"Backtest rows: {backtest_rows}")
    print(f"Total combinations: {len(targets) * len(horizons)}")

    results = []

    for target in targets:
        for horizon in horizons:
            try:
                result = run_single_target_eval(
                    target=target,
                    horizon=horizon,
                    backtest_rows=backtest_rows,
                    verbose=verbose,
                )
                results.append(result)
            except Exception as e:
                print(f"ERROR on {target}_{horizon}bar: {e}")
                import traceback

                traceback.print_exc()

    # Create summary DataFrame
    summary_df = pd.DataFrame(
        [
            {
                "target": r.target,
                "horizon": r.horizon,
                "n_iterations": r.n_iterations,
                "aligned_ic": r.aligned_ic,
                "full_ic": r.mean_ic,
                "hit_rate": r.hit_rate,
                "mse": r.mse,
                "l1_mean_ic": r.l1_mean_ic,
                "runtime_s": r.runtime_seconds,
            }
            for r in results
        ]
    )

    # Save results
    summary_df.to_csv(output_dir / "full_eval_summary.csv", index=False)
    print(f"\nSaved results to {output_dir / 'full_eval_summary.csv'}")

    # Print summary
    print("\n" + "=" * 80)
    print("EVALUATION SUMMARY")
    print("=" * 80)

    print("\nBy Target:")
    for target in targets:
        target_data = summary_df[summary_df["target"] == target]
        if not target_data.empty:
            avg_ic = target_data["aligned_ic"].mean()
            avg_hr = target_data["hit_rate"].mean()
            print(f"  {target}: IC={avg_ic:.4f}, HitRate={avg_hr:.2%}")

    print("\nBy Horizon:")
    for horizon in horizons:
        horizon_data = summary_df[summary_df["horizon"] == horizon]
        if not horizon_data.empty:
            avg_ic = horizon_data["aligned_ic"].mean()
            avg_hr = horizon_data["hit_rate"].mean()
            print(f"  {horizon}-bar: IC={avg_ic:.4f}, HitRate={avg_hr:.2%}")

    print("\nOverall:")
    print(f"  Mean Aligned IC: {summary_df['aligned_ic'].mean():.4f}")
    print(f"  Mean Hit Rate: {summary_df['hit_rate'].mean():.2%}")
    print(f"  Total Runtime: {summary_df['runtime_s'].sum():.1f}s")

    return summary_df


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Full Pipeline Evaluation")
    parser.add_argument(
        "--targets",
        nargs="+",
        default=None,
        help="Targets to evaluate (default: all 5)",
    )
    parser.add_argument(
        "--horizons",
        nargs="+",
        type=int,
        default=None,
        help="Horizons to evaluate (default: 1 3 6 12)",
    )
    parser.add_argument(
        "--backtest-rows",
        type=int,
        default=500,
        help="Number of walk-forward iterations (default: 500)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/pipeline_results",
        help="Output directory",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Reduce output verbosity",
    )

    args = parser.parse_args()

    run_full_evaluation(
        targets=args.targets,
        horizons=args.horizons,
        backtest_rows=args.backtest_rows,
        output_dir=args.output_dir,
        verbose=not args.quiet,
    )


if __name__ == "__main__":
    main()
