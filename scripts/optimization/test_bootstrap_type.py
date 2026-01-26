#!/usr/bin/env python3
"""
Bootstrap Type Comparison for CatBoost
=======================================
Test different bootstrap_type options on 1-bar prediction configs.

Bootstrap types:
- Bayesian: Default, good regularization, no speedup
- Bernoulli: Stochastic GB, some speedup, good regularization
- MVS: Minimum Variance Sampling, fast but weak regularization
- No: All samples, no regularization

Reference: https://catboost.ai/docs/en/concepts/algorithm-main-stages_bootstrap-options
"""

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier, CatBoostRegressor
from scipy.stats import spearmanr
from sklearn.metrics import accuracy_score, roc_auc_score

# Add project root
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def load_1bar_data(config_name: str) -> tuple[pd.DataFrame, pd.Series, str]:
    """Load data for a 1bar config from datasets folder."""
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
        # Fallback
        target_cols = [c for c in df.columns if c.startswith("y_")]
        target_col = target_cols[0] if target_cols else None
        task_type = "classification"

    if target_col not in df.columns:
        raise ValueError(f"Target column {target_col} not found in {config_name}")

    # Use all numeric features except target and timestamp
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

    print(
        f"Loaded {config_name}: {len(X)} rows, {len(feature_cols)} features, task={task_type}"
    )

    return X, y, task_type


def walk_forward_cv(
    X: pd.DataFrame,
    y: pd.Series,
    task_type: str,
    bootstrap_type: str,
    n_splits: int = 5,
    train_size: int = 400,
    val_size: int = 100,
) -> dict:
    """
    Walk-forward cross-validation for a single bootstrap type.

    Returns metrics dict with mean and std for each metric.
    """
    results = {
        "accuracy": [] if task_type == "classification" else None,
        "auc": [] if task_type == "classification" else None,
        "ic": [] if task_type == "regression" else None,
        "times": [],
    }

    n_total = len(X)
    step_size = (n_total - train_size - val_size) // n_splits

    for i in range(n_splits):
        train_start = i * step_size
        train_end = train_start + train_size
        val_start = train_end
        val_end = val_start + val_size

        if val_end > n_total:
            break

        X_train = X.iloc[train_start:train_end]
        y_train = y.iloc[train_start:train_end]
        X_val = X.iloc[val_start:val_end]
        y_val = y.iloc[val_start:val_end]

        # Handle single-class case
        if task_type == "classification":
            unique_classes = y_train.nunique()
            if unique_classes < 2:
                continue

        # Build model params
        base_params = {
            "iterations": 100,
            "depth": 6,
            "learning_rate": 0.03,
            "l2_leaf_reg": 3.0,
            "random_seed": 42,
            "verbose": False,
            "task_type": "GPU",
            "devices": "0",
        }

        # Add bootstrap-specific params
        if bootstrap_type == "Bayesian":
            base_params["bootstrap_type"] = "Bayesian"
            base_params["bagging_temperature"] = 1.0
        elif bootstrap_type == "Bernoulli":
            base_params["bootstrap_type"] = "Bernoulli"
            base_params["subsample"] = 0.8
        elif bootstrap_type == "MVS":
            base_params["bootstrap_type"] = "MVS"
            base_params["subsample"] = 0.8
        elif bootstrap_type == "Poisson":
            base_params["bootstrap_type"] = "Poisson"
            base_params["subsample"] = 0.66
        else:  # No
            base_params["bootstrap_type"] = "No"

        # Train
        start_time = time.time()

        if task_type == "classification":
            n_classes = int(y_train.max() + 1)
            is_binary = n_classes == 2

            model = CatBoostClassifier(
                **base_params,
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
                **base_params,
                loss_function="RMSE",
            )
            model.fit(X_train, y_train, verbose=False)

            y_pred = model.predict(X_val)

            # Information Coefficient (Spearman correlation)
            ic, _ = spearmanr(y_val, y_pred)
            if np.isfinite(ic):
                results["ic"].append(ic)

        elapsed = time.time() - start_time
        results["times"].append(elapsed)

    # Aggregate
    summary = {"bootstrap_type": bootstrap_type}

    if results["accuracy"] is not None and len(results["accuracy"]) > 0:
        summary["accuracy_mean"] = np.mean(results["accuracy"])
        summary["accuracy_std"] = np.std(results["accuracy"])

    if results["auc"] is not None and len(results["auc"]) > 0:
        summary["auc_mean"] = np.mean(results["auc"])
        summary["auc_std"] = np.std(results["auc"])

    if results["ic"] is not None and len(results["ic"]) > 0:
        summary["ic_mean"] = np.mean(results["ic"])
        summary["ic_std"] = np.std(results["ic"])

    summary["time_mean"] = np.mean(results["times"])
    summary["time_std"] = np.std(results["times"])
    summary["n_splits"] = len(results["times"])

    return summary


def run_bootstrap_comparison(config_name: str) -> pd.DataFrame:
    """Run bootstrap type comparison for a single config."""
    print(f"\n{'=' * 60}")
    print(f"Bootstrap Type Comparison: {config_name}")
    print(f"{'=' * 60}")

    X, y, task_type = load_1bar_data(config_name)

    bootstrap_types = ["Bayesian", "Bernoulli", "MVS", "Poisson", "No"]
    results = []

    for bt in bootstrap_types:
        print(f"\nTesting {bt}...")
        try:
            summary = walk_forward_cv(X, y, task_type, bt)
            results.append(summary)

            if task_type == "classification":
                print(
                    f"  Accuracy: {summary.get('accuracy_mean', 0):.4f} ± {summary.get('accuracy_std', 0):.4f}"
                )
                if "auc_mean" in summary:
                    print(
                        f"  AUC:      {summary.get('auc_mean', 0):.4f} ± {summary.get('auc_std', 0):.4f}"
                    )
            else:
                print(
                    f"  IC:       {summary.get('ic_mean', 0):.4f} ± {summary.get('ic_std', 0):.4f}"
                )

            print(
                f"  Time:     {summary['time_mean']:.2f}s ± {summary['time_std']:.2f}s"
            )

        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({"bootstrap_type": bt, "error": str(e)})

    df = pd.DataFrame(results)
    return df


def main():
    """Run bootstrap comparison on all 1-bar configs."""
    configs_1bar = [
        "direction_1bar",
        "returns_1bar",
        "volatility_1bar",
        "vol_regime_1bar",
        "trend_regime_1bar",
    ]

    all_results = {}

    for config in configs_1bar:
        try:
            df = run_bootstrap_comparison(config)
            all_results[config] = df
            print(f"\n{config} Results:")
            print(df.to_string(index=False))
        except FileNotFoundError as e:
            print(f"Skipping {config}: {e}")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY - Best Bootstrap Type per Config")
    print("=" * 80)

    for config, df in all_results.items():
        if "error" in df.columns:
            df = df[df["error"].isna()]

        if df.empty:
            continue

        # Find best by primary metric
        if "accuracy_mean" in df.columns:
            best_row = df.loc[df["accuracy_mean"].idxmax()]
            metric = f"Acc={best_row['accuracy_mean']:.4f}"
        elif "ic_mean" in df.columns:
            best_row = df.loc[df["ic_mean"].idxmax()]
            metric = f"IC={best_row['ic_mean']:.4f}"
        else:
            continue

        print(
            f"  {config}: {best_row['bootstrap_type']} ({metric}, {best_row['time_mean']:.2f}s)"
        )

    # Save results
    output_dir = project_root / "data" / "optimization"
    output_dir.mkdir(parents=True, exist_ok=True)

    for config, df in all_results.items():
        df.to_csv(output_dir / f"{config}_bootstrap_comparison.csv", index=False)

    print(f"\nResults saved to {output_dir}")


if __name__ == "__main__":
    main()
