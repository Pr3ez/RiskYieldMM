"""
L2 Backtest Module

Trains L2 models on assembled prediction datasets (L1 features).
Uses walk-forward validation on the continuous assembled.parquet files.

Each assembled.parquet contains:
- ~3500 rows (one per prediction timestamp)
- 91 L1 helper features computed at prediction time
- pred_idx for alignment with targets

Usage:
    from scripts.target_models.validation.l2_backtest import (
        L2BacktestConfig,
        L2Backtester,
        run_l2_backtest,
        run_all_l2_backtests,
    )

    # Run single config
    result = run_l2_backtest("direction_1bar", verbose=True)
    print(result.summary())

    # Run all 20 configs
    results = run_all_l2_backtests(verbose=True)
"""

from __future__ import annotations

import json
import time
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from scripts.target_models.validation.dataset_assembly import (
    ALL_CONFIGS,
    load_assembled,
)


@dataclass
class L2BacktestConfig:
    """Configuration for L2 backtesting on assembled datasets."""

    # Walk-forward settings
    train_window: int = 500  # Training window size (rows)
    val_window: int = 100  # Validation window for early stopping
    cal_window: int = 100  # Calibration window for conformal
    step_size: int = 1  # Step forward each iteration (1 = sliding)

    # Train/val/cal split ratios (within training window)
    train_ratio: float = 0.55
    val_ratio: float = 0.15
    cal_ratio: float = 0.30

    # Model settings
    random_state: int = 42
    n_estimators: int = 100
    max_depth: int = 6

    # Conformal prediction
    conformal_enabled: bool = True
    conformal_alpha: float = 0.1  # 90% confidence

    # Feature clipping (HMM duration can explode)
    clip_extreme_features: bool = True
    duration_feature_max: float = 1000.0

    # Output
    output_dir: Path = field(default_factory=lambda: Path("data/l2_backtest_results"))

    def __post_init__(self):
        self.output_dir = Path(self.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)


@dataclass
class L2BacktestResult:
    """Result of L2 backtest on assembled dataset."""

    config_name: str
    task_type: str
    n_predictions: int
    n_train_rows: int

    # Metrics
    metrics: dict[str, float]

    # Predictions DataFrame
    predictions: pd.DataFrame

    # Conformal metrics
    coverage: float | None = None
    mean_interval_width: float | None = None
    mean_set_size: float | None = None

    # Timing
    elapsed_seconds: float = 0.0

    def summary(self) -> str:
        """Generate summary string."""
        lines = [
            f"\nL2 Backtest Results: {self.config_name}",
            "=" * 50,
            f"Task type: {self.task_type}",
            f"Predictions: {self.n_predictions}",
            f"Training rows: {self.n_train_rows}",
            f"Elapsed: {self.elapsed_seconds:.1f}s",
            "",
            "Metrics:",
        ]

        for name, value in self.metrics.items():
            if isinstance(value, float):
                lines.append(f"  {name}: {value:.4f}")
            else:
                lines.append(f"  {name}: {value}")

        if self.coverage is not None:
            lines.append(f"\nConformal Coverage: {self.coverage:.1%}")
            if self.mean_interval_width is not None:
                lines.append(f"Mean Interval Width: {self.mean_interval_width:.4f}")
            if self.mean_set_size is not None:
                lines.append(f"Mean Set Size: {self.mean_set_size:.2f}")

        return "\n".join(lines)


def get_target_spec(config_name: str) -> dict[str, Any]:
    """Parse config name to get target specification."""
    parts = config_name.rsplit("_", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid config name: {config_name}")

    target_name = parts[0]
    horizon_str = parts[1].replace("bar", "")
    horizon = int(horizon_str)

    # Determine task type and classes
    task_type = "regression"
    n_classes = None

    if target_name == "direction":
        task_type = "classification"
        n_classes = 3  # down, neutral, up
    elif target_name in ("vol_regime", "trend_regime"):
        task_type = "classification"
        n_classes = 3  # low, medium, high / down, sideways, up

    return {
        "target": target_name,
        "horizon": horizon,
        "task_type": task_type,
        "n_classes": n_classes,
    }


def load_target_data_for_backtest(
    target_name: str,
    horizon: int,
    drop_na: bool = True,
) -> tuple[pd.DataFrame, pd.Series, str]:
    """Load target data for the specified target and horizon."""
    from scripts.target_models.registry import load_target_data

    X, y, spec = load_target_data(
        target=target_name,
        horizon=horizon,
        drop_na=drop_na,
        verbose=False,
    )

    y_col = spec.target_column

    return X, y, y_col


def clip_extreme_features(
    df: pd.DataFrame,
    duration_max: float = 1000.0,
) -> pd.DataFrame:
    """Clip extreme feature values (e.g., HMM duration)."""
    df = df.copy()

    # Clip duration features
    duration_cols = [c for c in df.columns if "duration" in c.lower()]
    for col in duration_cols:
        if col in df.columns:
            df[col] = df[col].clip(upper=duration_max)

    return df


class L2Backtester:
    """
    L2 Backtester using assembled prediction datasets.

    Performs walk-forward validation on the continuous assembled.parquet,
    training L2 models to predict targets from L1 features.
    """

    def __init__(self, config: L2BacktestConfig | None = None):
        self.config = config or L2BacktestConfig()

    def run(
        self,
        config_name: str,
        verbose: bool = True,
    ) -> L2BacktestResult:
        """
        Run L2 backtest on assembled dataset.

        Args:
            config_name: e.g., "direction_1bar"
            verbose: Print progress

        Returns:
            L2BacktestResult with predictions and metrics
        """
        start_time = time.time()
        spec = get_target_spec(config_name)

        if verbose:
            print(f"\n{'=' * 60}")
            print(f"L2 Backtest: {config_name}")
            print(f"{'=' * 60}")

        # Load assembled L1 features
        X_assembled = load_assembled(config_name)

        if verbose:
            print(f"Loaded assembled features: {X_assembled.shape}")

        # Extract pred_idx for alignment
        pred_idx = X_assembled["pred_idx"].values
        X_features = X_assembled.drop(columns=["pred_idx"])

        # Clip extreme features
        if self.config.clip_extreme_features:
            X_features = clip_extreme_features(
                X_features,
                duration_max=self.config.duration_feature_max,
            )

        # Load target data
        _, y_full, y_col = load_target_data_for_backtest(
            spec["target"], spec["horizon"], drop_na=True
        )

        if verbose:
            print(f"Target: {y_col}, shape: {y_full.shape}")

        # Align targets with assembled features using pred_idx
        # pred_idx points to the prediction index in the target data
        y_aligned = []
        valid_indices = []

        for i, idx in enumerate(pred_idx):
            # For horizon > 1, the aligned target is at pred_idx + horizon - 1
            aligned_idx = int(idx) + spec["horizon"] - 1
            if aligned_idx < len(y_full):
                y_aligned.append(y_full.iloc[aligned_idx])
                valid_indices.append(i)
            else:
                y_aligned.append(np.nan)
                valid_indices.append(i)

        y_aligned = pd.Series(y_aligned)

        # Filter out rows where target is NaN
        valid_mask = y_aligned.notna().values  # Convert to numpy for indexing
        X_valid = X_features.iloc[valid_mask].reset_index(drop=True)
        y_valid = y_aligned[valid_mask].reset_index(drop=True)
        pred_idx_valid = pred_idx[valid_mask]

        if verbose:
            print(f"Valid samples after alignment: {len(X_valid)}")

        # Walk-forward validation
        total_window = self.config.train_window
        n_samples = len(X_valid)

        if n_samples < total_window + 100:
            raise ValueError(
                f"Insufficient data for walk-forward: {n_samples} samples, "
                f"need at least {total_window + 100}"
            )

        # Calculate split sizes within training window
        train_size = int(total_window * self.config.train_ratio)
        val_size = int(total_window * self.config.val_ratio)
        cal_size = total_window - train_size - val_size

        if verbose:
            print("\nWalk-forward splits:")
            print(f"  Train: {train_size}, Val: {val_size}, Cal: {cal_size}")
            print(f"  Step size: {self.config.step_size}")

        # Run walk-forward
        predictions = []
        start_idx = total_window

        n_iterations = (n_samples - start_idx) // self.config.step_size

        if verbose:
            print(f"\nRunning {n_iterations} iterations...")

        for i in range(n_iterations):
            pred_position = start_idx + i * self.config.step_size

            if pred_position >= n_samples:
                break

            # Get training window ending just before prediction
            window_end = pred_position
            window_start = window_end - total_window

            # Split window into train/val/cal
            train_end = window_start + train_size
            val_end = train_end + val_size
            cal_end = val_end + cal_size

            X_train = X_valid.iloc[window_start:train_end]
            y_train = y_valid.iloc[window_start:train_end]
            X_val = X_valid.iloc[train_end:val_end]
            y_val = y_valid.iloc[train_end:val_end]
            X_cal = X_valid.iloc[val_end:cal_end]
            y_cal = y_valid.iloc[val_end:cal_end]

            # Prediction point
            X_pred = X_valid.iloc[[pred_position]]
            y_true = y_valid.iloc[pred_position]

            # Train model
            if spec["task_type"] == "classification":
                y_pred, y_prob, prediction_set = self._train_classifier(
                    X_train, y_train, X_val, y_val, X_cal, y_cal, X_pred, spec
                )
                covered = (
                    bool(prediction_set[int(y_true)])
                    if prediction_set is not None
                    else None
                )
                interval_width = None
            else:
                y_pred, interval, covered = self._train_regressor(
                    X_train, y_train, X_val, y_val, X_cal, y_cal, X_pred, y_true, spec
                )
                y_prob = None
                prediction_set = None
                interval_width = interval[1] - interval[0] if interval else None

            predictions.append(
                {
                    "iteration": i,
                    "pred_position": pred_position,
                    "pred_idx": pred_idx_valid[pred_position],
                    "y_pred": y_pred,
                    "y_true": y_true,
                    "y_prob": y_prob,
                    "covered": covered,
                    "set_size": np.sum(prediction_set)
                    if prediction_set is not None
                    else None,
                    "interval_width": interval_width,
                }
            )

            if verbose and (i + 1) % 500 == 0:
                elapsed = time.time() - start_time
                rate = (i + 1) / elapsed
                remaining = (n_iterations - i - 1) / rate
                print(
                    f"  Iteration {i + 1}/{n_iterations} "
                    f"[{elapsed:.1f}s elapsed, ~{remaining:.1f}s remaining]"
                )

        # Build results DataFrame
        predictions_df = pd.DataFrame(predictions)

        # Compute metrics
        metrics = self._compute_metrics(predictions_df, spec)

        # Conformal metrics
        coverage = None
        mean_interval_width = None
        mean_set_size = None

        if self.config.conformal_enabled:
            covered_mask = predictions_df["covered"].notna()
            if covered_mask.any():
                coverage = predictions_df.loc[covered_mask, "covered"].mean()

            if spec["task_type"] == "regression":
                widths = predictions_df["interval_width"].dropna()
                if len(widths) > 0:
                    mean_interval_width = widths.mean()
            else:
                sizes = predictions_df["set_size"].dropna()
                if len(sizes) > 0:
                    mean_set_size = sizes.mean()

        elapsed = time.time() - start_time

        if verbose:
            print(f"\n✓ Completed in {elapsed:.1f}s")
            if metrics:
                primary = list(metrics.keys())[0]
                print(f"  Primary metric ({primary}): {metrics[primary]:.4f}")
            if coverage is not None:
                print(f"  Coverage: {coverage:.1%}")

        # Save results
        output_path = self.config.output_dir / f"{config_name}_predictions.parquet"
        predictions_df.to_parquet(output_path, index=False)

        return L2BacktestResult(
            config_name=config_name,
            task_type=spec["task_type"],
            n_predictions=len(predictions_df),
            n_train_rows=len(X_valid),
            metrics=metrics,
            predictions=predictions_df,
            coverage=coverage,
            mean_interval_width=mean_interval_width,
            mean_set_size=mean_set_size,
            elapsed_seconds=elapsed,
        )

    def _train_classifier(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_val: pd.DataFrame,
        y_val: pd.Series,
        X_cal: pd.DataFrame,
        y_cal: pd.Series,
        X_pred: pd.DataFrame,
        spec: dict,
    ) -> tuple[int, np.ndarray | None, np.ndarray | None]:
        """Train classifier and return prediction."""
        from sklearn.ensemble import GradientBoostingClassifier

        # Check class balance
        unique_classes = np.unique(y_train)
        if len(unique_classes) < 2:
            # Single class in training - return majority class
            return int(y_train.mode().iloc[0]), None, None

        model = GradientBoostingClassifier(
            n_estimators=self.config.n_estimators,
            max_depth=self.config.max_depth,
            random_state=self.config.random_state,
            validation_fraction=0.1,
            n_iter_no_change=10,
        )

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model.fit(X_train, y_train)

        y_pred = int(model.predict(X_pred)[0])
        y_prob = model.predict_proba(X_pred)[0]

        # Conformal prediction set
        prediction_set = None
        if self.config.conformal_enabled and len(X_cal) > 10:
            try:
                cal_probs = model.predict_proba(X_cal)
                # Non-conformity scores: 1 - probability of true class
                scores = 1 - cal_probs[np.arange(len(y_cal)), y_cal.astype(int)]
                threshold = np.quantile(scores, 1 - self.config.conformal_alpha)

                # Prediction set: classes where 1 - prob <= threshold
                pred_probs = model.predict_proba(X_pred)[0]
                prediction_set = (1 - pred_probs) <= threshold
            except Exception:
                pass

        return y_pred, y_prob, prediction_set

    def _train_regressor(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_val: pd.DataFrame,
        y_val: pd.Series,
        X_cal: pd.DataFrame,
        y_cal: pd.Series,
        X_pred: pd.DataFrame,
        y_true: float,
        spec: dict,
    ) -> tuple[float, tuple[float, float] | None, bool | None]:
        """Train regressor and return prediction with interval."""
        from sklearn.ensemble import GradientBoostingRegressor

        model = GradientBoostingRegressor(
            n_estimators=self.config.n_estimators,
            max_depth=self.config.max_depth,
            random_state=self.config.random_state,
            validation_fraction=0.1,
            n_iter_no_change=10,
        )

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model.fit(X_train, y_train)

        y_pred = float(model.predict(X_pred)[0])

        # Conformal interval
        interval = None
        covered = None
        if self.config.conformal_enabled and len(X_cal) > 10:
            try:
                cal_preds = model.predict(X_cal)
                residuals = np.abs(y_cal - cal_preds)
                width = np.quantile(residuals, 1 - self.config.conformal_alpha)

                interval = (y_pred - width, y_pred + width)
                covered = interval[0] <= y_true <= interval[1]
            except Exception:
                pass

        return y_pred, interval, covered

    def _compute_metrics(
        self,
        predictions: pd.DataFrame,
        spec: dict,
    ) -> dict[str, float]:
        """Compute performance metrics."""
        y_true = predictions["y_true"].dropna()
        y_pred = predictions.loc[y_true.index, "y_pred"]

        if len(y_true) == 0:
            return {}

        metrics = {}

        if spec["task_type"] == "regression":
            # IC (Information Coefficient)
            ic, _ = stats.spearmanr(y_true, y_pred)
            metrics["ic"] = ic if not np.isnan(ic) else 0.0

            # RMSE
            rmse = np.sqrt(np.mean((y_true - y_pred) ** 2))
            metrics["rmse"] = rmse

            # MAE
            mae = np.mean(np.abs(y_true - y_pred))
            metrics["mae"] = mae

            # R²
            ss_res = np.sum((y_true - y_pred) ** 2)
            ss_tot = np.sum((y_true - y_true.mean()) ** 2)
            r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
            metrics["r2"] = r2

        else:
            # Classification metrics
            from sklearn.metrics import accuracy_score, f1_score

            accuracy = accuracy_score(y_true, y_pred)
            metrics["accuracy"] = accuracy

            # Direction accuracy (for direction target)
            if spec["target"] == "direction":
                # Map: 0=down, 1=neutral, 2=up
                correct_direction = (y_true == y_pred) | (
                    (y_true != 1) & (y_pred != 1) & ((y_true > 1) == (y_pred > 1))
                )
                metrics["direction_accuracy"] = correct_direction.mean()

            # F1 weighted
            f1 = f1_score(y_true, y_pred, average="weighted", zero_division=0)
            metrics["f1_weighted"] = f1

            # Per-class accuracy
            for cls in np.unique(y_true):
                mask = y_true == cls
                if mask.sum() > 0:
                    cls_acc = (y_pred[mask] == cls).mean()
                    metrics[f"accuracy_class_{int(cls)}"] = cls_acc

        return metrics


def run_l2_backtest(
    config_name: str,
    config: L2BacktestConfig | None = None,
    verbose: bool = True,
) -> L2BacktestResult:
    """
    Run L2 backtest on a single config.

    Args:
        config_name: e.g., "direction_1bar"
        config: Backtest configuration
        verbose: Print progress

    Returns:
        L2BacktestResult
    """
    backtester = L2Backtester(config)
    return backtester.run(config_name, verbose=verbose)


def run_all_l2_backtests(
    config: L2BacktestConfig | None = None,
    configs: list[str] | None = None,
    verbose: bool = True,
) -> dict[str, L2BacktestResult]:
    """
    Run L2 backtest on all configs.

    Args:
        config: Backtest configuration
        configs: List of config names (default: ALL_CONFIGS)
        verbose: Print progress

    Returns:
        Dict mapping config_name -> L2BacktestResult
    """
    configs = configs or ALL_CONFIGS
    config = config or L2BacktestConfig()
    backtester = L2Backtester(config)

    results = {}
    total_start = time.time()

    for i, config_name in enumerate(configs):
        if verbose:
            print(f"\n[{i + 1}/{len(configs)}] Processing {config_name}...")

        try:
            result = backtester.run(config_name, verbose=verbose)
            results[config_name] = result
        except Exception as e:
            print(f"  ❌ Error: {e}")
            continue

    total_elapsed = time.time() - total_start

    if verbose:
        print(f"\n{'=' * 60}")
        print("L2 BACKTEST COMPLETE")
        print(f"{'=' * 60}")
        print(f"Total time: {total_elapsed:.1f}s")
        print(f"Successful: {len(results)}/{len(configs)}")

        # Summary table
        print(f"\n{'Config':<25} {'Type':<15} {'Primary Metric':<20}")
        print("-" * 60)

        for config_name, result in results.items():
            task = result.task_type[:12]
            if result.metrics:
                primary_name = list(result.metrics.keys())[0]
                primary_val = result.metrics[primary_name]
                metric_str = f"{primary_name}={primary_val:.4f}"
            else:
                metric_str = "N/A"
            print(f"{config_name:<25} {task:<15} {metric_str:<20}")

    # Save summary
    summary_path = config.output_dir / "l2_backtest_summary.json"
    summary = {
        config_name: {
            "task_type": r.task_type,
            "n_predictions": r.n_predictions,
            "metrics": r.metrics,
            "coverage": r.coverage,
            "elapsed_seconds": r.elapsed_seconds,
        }
        for config_name, r in results.items()
    }
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    if verbose:
        print(f"\nSummary saved to: {summary_path}")

    return results


if __name__ == "__main__":
    warnings.filterwarnings("ignore")

    # Test with direction_1bar
    print("Testing L2 Backtest on direction_1bar...")

    config = L2BacktestConfig(
        train_window=500,
        step_size=1,
    )

    result = run_l2_backtest("direction_1bar", config, verbose=True)
    print(result.summary())
