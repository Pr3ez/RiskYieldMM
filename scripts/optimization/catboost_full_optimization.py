#!/usr/bin/env python3
"""
Comprehensive CatBoost Hyperparameter Optimization
===================================================
Full walk-forward optimization with 100+ steps following research-backed tuning order:

1. Bootstrap type (already done)
2. Learning rate + n_estimators (coupled)
3. Tree depth
4. Regularization (l2_leaf_reg)
5. Subsample (for Bernoulli/MVS)

Reference: Analytics Vidhya / Owen Zhang approach
"""

import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier, CatBoostRegressor
from scipy.stats import spearmanr
from sklearn.metrics import accuracy_score, roc_auc_score

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


@dataclass
class OptimizationConfig:
    """Configuration for hyperparameter optimization."""

    config_name: str
    n_steps: int = 100  # Walk-forward steps
    train_size: int = 400
    val_size: int = 100
    step_size: int = 30  # Skip between steps for speed
    random_seed: int = 42
    use_gpu: bool = True


def load_data(config_name: str) -> tuple[pd.DataFrame, pd.Series, str]:
    """Load data for a config from datasets folder."""
    data_path = project_root / "data" / "datasets" / f"{config_name}.parquet"

    if not data_path.exists():
        raise FileNotFoundError(f"No dataset at {data_path}")

    df = pd.read_parquet(data_path)

    # Determine task type and target column
    if "direction" in config_name:
        task_type = "classification"
        target_col = "y_direction"
    elif "vol_regime" in config_name:
        task_type = "classification"
        target_col = "y_vol_regime"
    elif "trend_regime" in config_name:
        task_type = "classification"
        target_col = "y_trend_regime"
    elif "returns" in config_name:
        task_type = "regression"
        target_col = "y_returns"
    elif "volatility" in config_name:
        task_type = "regression"
        target_col = "y_volatility"
    else:
        target_cols = [c for c in df.columns if c.startswith("y_")]
        target_col = target_cols[0] if target_cols else None
        task_type = "classification"

    if target_col not in df.columns:
        raise ValueError(f"Target column {target_col} not found")

    # Use all numeric features
    exclude_cols = ["timestamp", target_col]
    feature_cols = [
        c
        for c in df.columns
        if c not in exclude_cols
        and df[c].dtype in ["float64", "float32", "int64", "int32"]
    ]

    X = df[feature_cols].copy()
    y = df[target_col].copy()

    # Drop rows with NaN
    valid_mask = X.notna().all(axis=1) & y.notna()
    X = X[valid_mask]
    y = y[valid_mask]

    return X, y, task_type


def walk_forward_evaluate(
    X: pd.DataFrame,
    y: pd.Series,
    task_type: str,
    params: dict[str, Any],
    config: OptimizationConfig,
) -> dict[str, float]:
    """
    Walk-forward evaluation with many steps.

    Returns aggregated metrics with mean, std, median, and percentiles.
    """
    n_total = len(X)
    max_start = (
        n_total
        - config.train_size
        - config.val_size
        - config.n_steps * config.step_size
    )

    if max_start < 0:
        # Reduce step_size if needed
        available_steps = (
            n_total - config.train_size - config.val_size
        ) // config.step_size
        if available_steps < 20:
            raise ValueError(f"Not enough data for {config.n_steps} steps")
        actual_steps = min(config.n_steps, available_steps)
    else:
        actual_steps = config.n_steps

    results = {
        "accuracy": [] if task_type == "classification" else None,
        "auc": [] if task_type == "classification" else None,
        "ic": [] if task_type == "regression" else None,
        "times": [],
    }

    # Determine n_classes for multiclass
    n_classes = int(y.max() + 1) if task_type == "classification" else None
    is_binary = n_classes == 2 if n_classes else False

    for step in range(actual_steps):
        train_start = step * config.step_size
        train_end = train_start + config.train_size
        val_start = train_end
        val_end = val_start + config.val_size

        if val_end > n_total:
            break

        X_train = X.iloc[train_start:train_end]
        y_train = y.iloc[train_start:train_end]
        X_val = X.iloc[val_start:val_end]
        y_val = y.iloc[val_start:val_end]

        # Skip if single class in training
        if task_type == "classification" and y_train.nunique() < 2:
            continue

        # Build model
        base_params = {
            "random_seed": config.random_seed,
            "verbose": False,
            "task_type": "GPU" if config.use_gpu else "CPU",
        }
        if config.use_gpu:
            base_params["devices"] = "0"

        model_params = {**base_params, **params}

        start_time = time.time()

        try:
            if task_type == "classification":
                model = CatBoostClassifier(
                    **model_params,
                    loss_function="Logloss" if is_binary else "MultiClass",
                    auto_class_weights="Balanced",
                )
                model.fit(X_train, y_train, verbose=False)

                y_pred = model.predict(X_val).flatten()
                y_prob = model.predict_proba(X_val)

                acc = accuracy_score(y_val, y_pred)
                results["accuracy"].append(acc)

                if is_binary:
                    try:
                        auc = roc_auc_score(y_val, y_prob[:, 1])
                        results["auc"].append(auc)
                    except ValueError:
                        pass
            else:
                model = CatBoostRegressor(
                    **model_params,
                    loss_function="RMSE",
                )
                model.fit(X_train, y_train, verbose=False)

                y_pred = model.predict(X_val)
                ic, _ = spearmanr(y_val, y_pred)
                if np.isfinite(ic):
                    results["ic"].append(ic)

        except Exception as e:
            print(f"  Step {step} error: {e}")
            continue

        elapsed = time.time() - start_time
        results["times"].append(elapsed)

    # Aggregate
    summary = {"n_steps": len(results["times"])}

    if results["accuracy"] is not None and len(results["accuracy"]) > 0:
        arr = np.array(results["accuracy"])
        summary["accuracy_mean"] = float(np.mean(arr))
        summary["accuracy_std"] = float(np.std(arr))
        summary["accuracy_median"] = float(np.median(arr))
        summary["accuracy_p25"] = float(np.percentile(arr, 25))
        summary["accuracy_p75"] = float(np.percentile(arr, 75))

    if results["auc"] is not None and len(results["auc"]) > 0:
        arr = np.array(results["auc"])
        summary["auc_mean"] = float(np.mean(arr))
        summary["auc_std"] = float(np.std(arr))
        summary["auc_median"] = float(np.median(arr))

    if results["ic"] is not None and len(results["ic"]) > 0:
        arr = np.array(results["ic"])
        summary["ic_mean"] = float(np.mean(arr))
        summary["ic_std"] = float(np.std(arr))
        summary["ic_median"] = float(np.median(arr))
        summary["ic_p25"] = float(np.percentile(arr, 25))
        summary["ic_p75"] = float(np.percentile(arr, 75))

    summary["time_mean"] = float(np.mean(results["times"]))
    summary["time_total"] = float(np.sum(results["times"]))

    return summary


def optimize_learning_rate_and_trees(
    X: pd.DataFrame,
    y: pd.Series,
    task_type: str,
    config: OptimizationConfig,
    bootstrap_type: str = "Bayesian",
) -> tuple[float, int, pd.DataFrame]:
    """
    Step 1: Find optimal learning_rate and n_estimators.

    Strategy: Test combinations of learning_rate and n_estimators.
    Lower LR needs more trees.
    """
    print("\n" + "=" * 60)
    print("PHASE 1: Learning Rate + N_Estimators")
    print("=" * 60)

    # Grid: learning_rate vs n_estimators
    lr_options = [0.01, 0.03, 0.05, 0.1, 0.2]
    tree_options = [50, 100, 200, 300, 500]

    results = []

    for lr in lr_options:
        for n_trees in tree_options:
            params = {
                "learning_rate": lr,
                "iterations": n_trees,
                "depth": 6,  # Default
                "l2_leaf_reg": 3.0,  # Default
                "bootstrap_type": bootstrap_type,
            }
            if bootstrap_type == "Bayesian":
                params["bagging_temperature"] = 1.0
            elif bootstrap_type in ["Bernoulli", "MVS"]:
                params["subsample"] = 0.8

            print(f"  Testing LR={lr}, Trees={n_trees}...", end=" ", flush=True)

            try:
                summary = walk_forward_evaluate(X, y, task_type, params, config)
                summary["learning_rate"] = lr
                summary["n_estimators"] = n_trees
                results.append(summary)

                # Print primary metric
                if task_type == "classification":
                    metric = summary.get("accuracy_mean", 0)
                    print(f"Acc={metric:.4f} ({summary['n_steps']} steps)")
                else:
                    metric = summary.get("ic_mean", 0)
                    print(f"IC={metric:.4f} ({summary['n_steps']} steps)")

            except Exception as e:
                print(f"ERROR: {e}")

    df = pd.DataFrame(results)

    # Find best
    if task_type == "classification":
        best_idx = df["accuracy_mean"].idxmax()
    else:
        best_idx = df["ic_mean"].idxmax()

    best_lr = df.loc[best_idx, "learning_rate"]
    best_trees = int(df.loc[best_idx, "n_estimators"])

    print(f"\n  BEST: LR={best_lr}, Trees={best_trees}")

    return best_lr, best_trees, df


def optimize_depth(
    X: pd.DataFrame,
    y: pd.Series,
    task_type: str,
    config: OptimizationConfig,
    learning_rate: float,
    n_estimators: int,
    bootstrap_type: str = "Bayesian",
) -> tuple[int, pd.DataFrame]:
    """
    Step 2: Find optimal tree depth.
    """
    print("\n" + "=" * 60)
    print("PHASE 2: Tree Depth")
    print("=" * 60)

    depth_options = [3, 4, 5, 6, 7, 8, 10]
    results = []

    for depth in depth_options:
        params = {
            "learning_rate": learning_rate,
            "iterations": n_estimators,
            "depth": depth,
            "l2_leaf_reg": 3.0,
            "bootstrap_type": bootstrap_type,
        }
        if bootstrap_type == "Bayesian":
            params["bagging_temperature"] = 1.0
        elif bootstrap_type in ["Bernoulli", "MVS"]:
            params["subsample"] = 0.8

        print(f"  Testing depth={depth}...", end=" ", flush=True)

        try:
            summary = walk_forward_evaluate(X, y, task_type, params, config)
            summary["depth"] = depth
            results.append(summary)

            if task_type == "classification":
                metric = summary.get("accuracy_mean", 0)
                print(f"Acc={metric:.4f}")
            else:
                metric = summary.get("ic_mean", 0)
                print(f"IC={metric:.4f}")

        except Exception as e:
            print(f"ERROR: {e}")

    df = pd.DataFrame(results)

    if task_type == "classification":
        best_idx = df["accuracy_mean"].idxmax()
    else:
        best_idx = df["ic_mean"].idxmax()

    best_depth = int(df.loc[best_idx, "depth"])
    print(f"\n  BEST: depth={best_depth}")

    return best_depth, df


def optimize_regularization(
    X: pd.DataFrame,
    y: pd.Series,
    task_type: str,
    config: OptimizationConfig,
    learning_rate: float,
    n_estimators: int,
    depth: int,
    bootstrap_type: str = "Bayesian",
) -> tuple[float, pd.DataFrame]:
    """
    Step 3: Find optimal L2 regularization.
    """
    print("\n" + "=" * 60)
    print("PHASE 3: L2 Regularization")
    print("=" * 60)

    l2_options = [1.0, 3.0, 5.0, 7.0, 10.0, 15.0, 20.0]
    results = []

    for l2_reg in l2_options:
        params = {
            "learning_rate": learning_rate,
            "iterations": n_estimators,
            "depth": depth,
            "l2_leaf_reg": l2_reg,
            "bootstrap_type": bootstrap_type,
        }
        if bootstrap_type == "Bayesian":
            params["bagging_temperature"] = 1.0
        elif bootstrap_type in ["Bernoulli", "MVS"]:
            params["subsample"] = 0.8

        print(f"  Testing l2_leaf_reg={l2_reg}...", end=" ", flush=True)

        try:
            summary = walk_forward_evaluate(X, y, task_type, params, config)
            summary["l2_leaf_reg"] = l2_reg
            results.append(summary)

            if task_type == "classification":
                metric = summary.get("accuracy_mean", 0)
                print(f"Acc={metric:.4f}")
            else:
                metric = summary.get("ic_mean", 0)
                print(f"IC={metric:.4f}")

        except Exception as e:
            print(f"ERROR: {e}")

    df = pd.DataFrame(results)

    if task_type == "classification":
        best_idx = df["accuracy_mean"].idxmax()
    else:
        best_idx = df["ic_mean"].idxmax()

    best_l2 = float(df.loc[best_idx, "l2_leaf_reg"])
    print(f"\n  BEST: l2_leaf_reg={best_l2}")

    return best_l2, df


def optimize_subsample(
    X: pd.DataFrame,
    y: pd.Series,
    task_type: str,
    config: OptimizationConfig,
    learning_rate: float,
    n_estimators: int,
    depth: int,
    l2_leaf_reg: float,
    bootstrap_type: str = "Bernoulli",
) -> tuple[float, pd.DataFrame]:
    """
    Step 4: Find optimal subsample rate (only for Bernoulli/MVS).
    """
    if bootstrap_type not in ["Bernoulli", "MVS", "Poisson"]:
        print("\n  SKIP: subsample not applicable for bootstrap_type=" + bootstrap_type)
        return 1.0, pd.DataFrame()

    print("\n" + "=" * 60)
    print("PHASE 4: Subsample Rate")
    print("=" * 60)

    subsample_options = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    results = []

    for subsample in subsample_options:
        params = {
            "learning_rate": learning_rate,
            "iterations": n_estimators,
            "depth": depth,
            "l2_leaf_reg": l2_leaf_reg,
            "bootstrap_type": bootstrap_type,
            "subsample": subsample,
        }

        print(f"  Testing subsample={subsample}...", end=" ", flush=True)

        try:
            summary = walk_forward_evaluate(X, y, task_type, params, config)
            summary["subsample"] = subsample
            results.append(summary)

            if task_type == "classification":
                metric = summary.get("accuracy_mean", 0)
                print(f"Acc={metric:.4f}")
            else:
                metric = summary.get("ic_mean", 0)
                print(f"IC={metric:.4f}")

        except Exception as e:
            print(f"ERROR: {e}")

    df = pd.DataFrame(results)

    if len(df) == 0:
        return 0.8, df

    if task_type == "classification":
        best_idx = df["accuracy_mean"].idxmax()
    else:
        best_idx = df["ic_mean"].idxmax()

    best_subsample = float(df.loc[best_idx, "subsample"])
    print(f"\n  BEST: subsample={best_subsample}")

    return best_subsample, df


def run_full_optimization(config_name: str, n_steps: int = 100) -> dict[str, Any]:
    """
    Run full hyperparameter optimization for a single config.
    """
    print("\n" + "#" * 70)
    print(f"# FULL OPTIMIZATION: {config_name}")
    print(f"# Steps: {n_steps}")
    print("#" * 70)

    # Load data
    X, y, task_type = load_data(config_name)
    print(f"Loaded: {len(X)} rows, {X.shape[1]} features, task={task_type}")

    # Determine bootstrap type based on previous results
    if "direction" in config_name:
        bootstrap_type = "Bayesian"  # Best for binary classification
    elif "returns" in config_name:
        bootstrap_type = "Bernoulli"  # MVS had slight edge but Bernoulli more stable
    elif "volatility" in config_name:
        bootstrap_type = "Bernoulli"
    elif "vol_regime" in config_name:
        bootstrap_type = "Bernoulli"  # MVS not supported for multiclass GPU
    elif "trend_regime" in config_name:
        bootstrap_type = "Bayesian"
    else:
        bootstrap_type = "Bayesian"

    print(f"Using bootstrap_type: {bootstrap_type}")

    opt_config = OptimizationConfig(
        config_name=config_name,
        n_steps=n_steps,
        step_size=20,  # Skip 20 bars between steps for ~100 distinct windows
    )

    # Phase 1: Learning Rate + Trees
    best_lr, best_trees, lr_df = optimize_learning_rate_and_trees(
        X, y, task_type, opt_config, bootstrap_type
    )

    # Phase 2: Depth
    best_depth, depth_df = optimize_depth(
        X, y, task_type, opt_config, best_lr, best_trees, bootstrap_type
    )

    # Phase 3: Regularization
    best_l2, l2_df = optimize_regularization(
        X, y, task_type, opt_config, best_lr, best_trees, best_depth, bootstrap_type
    )

    # Phase 4: Subsample (if applicable)
    best_subsample, subsample_df = optimize_subsample(
        X,
        y,
        task_type,
        opt_config,
        best_lr,
        best_trees,
        best_depth,
        best_l2,
        bootstrap_type,
    )

    # Final evaluation with best params
    print("\n" + "=" * 60)
    print("FINAL EVALUATION (Best Parameters)")
    print("=" * 60)

    best_params = {
        "learning_rate": best_lr,
        "iterations": best_trees,
        "depth": best_depth,
        "l2_leaf_reg": best_l2,
        "bootstrap_type": bootstrap_type,
    }
    if bootstrap_type in ["Bernoulli", "MVS", "Poisson"]:
        best_params["subsample"] = best_subsample
    elif bootstrap_type == "Bayesian":
        best_params["bagging_temperature"] = 1.0

    final_summary = walk_forward_evaluate(X, y, task_type, best_params, opt_config)

    print("\nBest Parameters:")
    for k, v in best_params.items():
        print(f"  {k}: {v}")

    print(f"\nFinal Performance ({final_summary['n_steps']} steps):")
    if task_type == "classification":
        print(
            f"  Accuracy: {final_summary.get('accuracy_mean', 0):.4f} ± {final_summary.get('accuracy_std', 0):.4f}"
        )
        print(f"  Accuracy Median: {final_summary.get('accuracy_median', 0):.4f}")
        if "auc_mean" in final_summary:
            print(
                f"  AUC: {final_summary.get('auc_mean', 0):.4f} ± {final_summary.get('auc_std', 0):.4f}"
            )
    else:
        print(
            f"  IC: {final_summary.get('ic_mean', 0):.4f} ± {final_summary.get('ic_std', 0):.4f}"
        )
        print(f"  IC Median: {final_summary.get('ic_median', 0):.4f}")
        print(
            f"  IC P25-P75: [{final_summary.get('ic_p25', 0):.4f}, {final_summary.get('ic_p75', 0):.4f}]"
        )

    # Save results
    output_dir = project_root / "data" / "optimization" / config_name
    output_dir.mkdir(parents=True, exist_ok=True)

    lr_df.to_csv(output_dir / "phase1_lr_trees.csv", index=False)
    depth_df.to_csv(output_dir / "phase2_depth.csv", index=False)
    l2_df.to_csv(output_dir / "phase3_l2_reg.csv", index=False)
    if len(subsample_df) > 0:
        subsample_df.to_csv(output_dir / "phase4_subsample.csv", index=False)

    # Save best params
    result = {
        "config_name": config_name,
        "task_type": task_type,
        "best_params": best_params,
        "final_metrics": final_summary,
        "n_optimization_steps": n_steps,
    }

    with open(output_dir / "best_params.json", "w") as f:
        json.dump(result, f, indent=2)

    print(f"\nResults saved to {output_dir}")

    return result


def main():
    """Run optimization for all 1-bar configs."""
    import argparse

    parser = argparse.ArgumentParser(description="CatBoost hyperparameter optimization")
    parser.add_argument(
        "--config",
        type=str,
        default="direction_1bar",
        help="Config to optimize (or 'all' for all 1bar configs)",
    )
    parser.add_argument(
        "--steps",
        type=int,
        default=100,
        help="Number of walk-forward steps",
    )
    args = parser.parse_args()

    if args.config == "all":
        configs = [
            "direction_1bar",
            "returns_1bar",
            "volatility_1bar",
            "vol_regime_1bar",
            "trend_regime_1bar",
        ]
    else:
        configs = [args.config]

    all_results = {}

    for config in configs:
        try:
            result = run_full_optimization(config, n_steps=args.steps)
            all_results[config] = result
        except Exception as e:
            print(f"ERROR optimizing {config}: {e}")
            import traceback

            traceback.print_exc()

    # Summary
    print("\n" + "#" * 70)
    print("# OPTIMIZATION SUMMARY")
    print("#" * 70)

    for config, result in all_results.items():
        params = result["best_params"]
        metrics = result["final_metrics"]

        print(f"\n{config}:")
        print(
            f"  LR={params['learning_rate']}, Trees={params['iterations']}, "
            f"Depth={params['depth']}, L2={params['l2_leaf_reg']}"
        )

        if result["task_type"] == "classification":
            print(
                f"  Accuracy: {metrics.get('accuracy_mean', 0):.4f} ± {metrics.get('accuracy_std', 0):.4f}"
            )
        else:
            print(
                f"  IC: {metrics.get('ic_mean', 0):.4f} ± {metrics.get('ic_std', 0):.4f}"
            )


if __name__ == "__main__":
    main()
