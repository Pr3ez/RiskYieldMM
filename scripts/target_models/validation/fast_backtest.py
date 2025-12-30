"""
Fast Backtesting with Precomputed L1 Features
==============================================

Runs walk-forward backtest using precomputed L1 (helper) features,
which is much faster than running the full dual-layer pipeline.

Speed comparison (200 iterations):
- Full pipeline: ~40-60 minutes (L1 + L2 each iteration)
- Fast backtest: ~3-5 minutes (L2 only, precomputed L1)

The flow:
1. For each iteration i:
   a. Load helper_features from precomputed/config_name/iter_NNNN.parquet
   b. Load y from config dataset (using same L2 indices)
   c. Split helper_features into train/cal/val/pred
   d. Validate class balance (skip if single-class)
   e. Fit ModelEnsemble, calibrate, apply conformal, predict
2. Aggregate all predictions and compute metrics

Tier 1 Validation (2025-01):
- Validates class balance before training (t1-1-i4)
- Uses adaptive window configs for regime targets (t1-2-i4)
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.target_models.calibration import ConformalClassifier, ConformalRegressor
from scripts.target_models.calibration.aci import AdaptiveConformalInference
from scripts.target_models.calibration.config import ConformalConfig
from scripts.target_models.core.aligned_dual_window import (
    get_l2_config_for_target,
    is_regime_target,
)
from scripts.target_models.core.validators import validate_class_balance
from scripts.target_models.models import create_model_ensemble
from scripts.target_models.registry import load_target_data
from scripts.target_models.validation.l1_precompute import (
    L1PrecomputeConfig,
    load_iteration_index,
    load_precomputed_l1,
    load_precomputed_metadata,
)

logger = logging.getLogger(__name__)


@dataclass
class BacktestConfig:
    """Configuration for fast backtesting."""

    # Data paths
    data_dir: Path = field(default_factory=lambda: Path("data/datasets"))
    precomputed_dir: Path = field(default_factory=lambda: Path("data/precomputed"))
    output_dir: Path = field(default_factory=lambda: Path("data/backtest_results"))

    # Backtest settings (must match precomputation)
    backtest_rows: int = 300

    # L2 window configuration (from SlidingL2Config)
    # NOTE: These are DEFAULTS. For regime targets, use use_adaptive_window=True
    # to automatically use window=700, train=60% (see get_l2_config_for_target)
    l2_window_size: int = 500
    l2_train_ratio: float = 0.55  # 275 samples
    l2_cal_ratio: float = 0.30  # 150 samples
    l2_purge_gap: int = 21  # minimum; actual purge = max(this, horizon + 10)

    # Adaptive window configuration (Tier 1.2)
    # When True, regime targets (trend_regime, vol_regime) use larger windows
    # to ensure sufficient class representation (window=700, train=420)
    use_adaptive_window: bool = True

    # Conformal prediction
    conformal_enabled: bool = True
    conformal_alpha: float = 0.10

    # Model settings
    random_state: int = 42

    # Class balance validation (Tier 1.1) - SAFETY NET, not primary fix
    # Primary fix is use_adaptive_window=True which uses larger windows
    validate_class_balance: bool = True
    min_samples_per_class: int = 30
    min_balance_score: float = 0.3

    # Economic simulation (Tier 1.6)
    # Transaction costs as fraction of trade value (e.g., 0.001 = 0.1%)
    transaction_cost_bps: float = 10.0  # 10 bps = 0.1% round trip
    # Slippage as fraction of volatility
    slippage_vol_fraction: float = 0.1  # 10% of realized volatility
    # Enable economic simulation in metrics
    compute_economic_metrics: bool = True

    def get_l2_splits(
        self,
        horizon: int,
        window_size: int | None = None,
        train_ratio: float | None = None,
    ) -> tuple[int, int, int, int]:
        """Get train/cal/val sizes within L2 window, matching production splits."""

        effective_window = window_size or self.l2_window_size
        effective_train_ratio = train_ratio or self.l2_train_ratio
        purge_gap = max(self.l2_purge_gap, horizon + 10)

        train_size = int(effective_window * effective_train_ratio)
        cal_size = int(effective_window * self.l2_cal_ratio)
        val_size = effective_window - train_size - cal_size - purge_gap
        return train_size, cal_size, val_size, purge_gap

    def get_effective_l2_config(self, target_name: str) -> tuple[int, float, float]:
        """
        Get effective L2 window config for a target.

        For regime targets (trend_regime, vol_regime), returns larger window
        config to ensure sufficient class representation.

        Returns:
            (window_size, train_ratio, cal_ratio)
        """
        if self.use_adaptive_window and is_regime_target(target_name):
            # Use adaptive config for regime targets
            l2_config = get_l2_config_for_target(target_name)
            return l2_config.window_size, l2_config.train_ratio, l2_config.cal_ratio
        else:
            # Use default config
            return self.l2_window_size, self.l2_train_ratio, self.l2_cal_ratio


@dataclass
class IterationResult:
    """Result from a single iteration."""

    iteration: int
    pred_idx: int  # Global index in dataset
    aligned_pred_idx: int  # Global index of aligned prediction (pred_idx + horizon - 1)
    y_pred: float | int
    y_true: float | int | None
    pred_timestamp: str | None = None
    aligned_timestamp: str | None = None
    y_prob: np.ndarray | None = None
    prediction_set: np.ndarray | None = None
    prediction_interval: tuple[float, float] | None = None
    uncertainty: float | None = None
    covered: bool | None = None
    # Class balance validation (Tier 1.1)
    skipped: bool = False  # True if iteration was skipped due to class imbalance
    skip_reason: str | None = None  # Reason for skipping
    balance_score: float | None = None  # Normalized entropy of training classes


@dataclass
class BacktestResult:
    """Results from a fast backtest run."""

    config_name: str
    task_type: str  # "regression", "binary", "multiclass"
    n_iterations: int
    elapsed_seconds: float

    # Predictions
    predictions: pd.DataFrame  # All iterations with y_pred, y_true, covered, etc.

    # Aggregate metrics
    metrics: dict[str, float]

    # Conformal metrics
    coverage: float | None = None
    mean_interval_width: float | None = None
    mean_set_size: float | None = None

    # Class balance validation (Tier 1.1)
    n_skipped: int = 0  # Iterations skipped due to class imbalance
    skip_rate: float = 0.0  # Fraction of iterations skipped

    def __repr__(self) -> str:
        cov_str = f", coverage={self.coverage:.1%}" if self.coverage else ""
        skip_str = f", skipped={self.n_skipped}" if self.n_skipped > 0 else ""
        return (
            f"BacktestResult({self.config_name}, {self.n_iterations} iters, "
            f"{self.elapsed_seconds:.1f}s{cov_str}{skip_str})"
        )


def get_target_spec(config_name: str) -> dict:
    """Get target specification from config name."""
    parts = config_name.rsplit("_", 1)
    target = parts[0]
    horizon = int(parts[1].replace("bar", ""))

    # Define task types and n_classes
    task_types = {
        "returns": ("regression", None),
        "direction": ("binary", 2),
        "volatility": ("regression", None),
        "vol_regime": ("multiclass", 3),
        "trend_regime": ("multiclass", 3),
    }

    task_type, n_classes = task_types.get(target, ("regression", None))

    return {
        "target": target,
        "horizon": horizon,
        "task_type": task_type,
        "n_classes": n_classes,
    }


class FastBacktester:
    """
    Fast backtester using precomputed L1 features.

    Only runs L2 (supervised model) walk-forward, using precomputed
    L1 (helper) features. This is ~10x faster than full pipeline.

    Usage:
        # First precompute L1 features (slow, but only once)
        from scripts.target_models.validation.l1_precompute import precompute_l1_for_config
        precompute_l1_for_config("direction_1bar")

        # Then run fast backtest (fast, reusable)
        backtester = FastBacktester()
        result = backtester.run("direction_1bar")
    """

    def __init__(self, config: BacktestConfig | None = None):
        self.config = config or BacktestConfig()

    def run(
        self,
        config_name: str,
        verbose: bool = True,
    ) -> BacktestResult:
        """
        Run fast backtest for a single config using precomputed L1 features.

        Args:
            config_name: e.g., "direction_1bar", "returns_6bar"
            verbose: Print progress

        Returns:
            BacktestResult with predictions and metrics
        """
        start_time = time.time()
        spec = get_target_spec(config_name)

        if verbose:
            print(f"\n{'=' * 60}")
            print(f"Fast Backtest: {config_name}")
            print(f"{'=' * 60}")

        # Load precomputation metadata
        l1_cfg = L1PrecomputeConfig(
            data_dir=self.config.data_dir,
            output_dir=self.config.precomputed_dir,
            backtest_rows=self.config.backtest_rows,
        )

        try:
            metadata = load_precomputed_metadata(config_name, l1_cfg)
            index = load_iteration_index(config_name, l1_cfg)
        except FileNotFoundError as e:
            raise FileNotFoundError(
                f"Precomputed features not found for {config_name}. "
                f"Run precompute_l1_for_config('{config_name}') first.\n{e}"
            ) from e

        n_available = len(index)
        n_iterations = (
            min(n_available, self.config.backtest_rows)
            if self.config.backtest_rows is not None
            else n_available
        )
        if metadata.total_iterations != n_available and verbose:
            print(
                f"  Warning: metadata iterations ({metadata.total_iterations}) "
                f"!= index entries ({n_available})"
            )

        if verbose:
            msg = f"Loaded {n_available} precomputed iterations"
            if n_iterations != n_available:
                msg += f" (running first {n_iterations})"
            print(msg)
            print(
                f"L2 splits: train={self.config.l2_train_ratio:.0%}, "
                f"cal={self.config.l2_cal_ratio:.0%}"
            )

        # Precompute and production both operate on NA-filtered data.
        # Indexes in `index.json` refer to this cleaned dataset.
        if getattr(metadata, "data_drop_na", None) is not True:
            raise ValueError(
                "Precompute metadata indicates legacy/unknown NA filtering. "
                "Please recompute L1 features for parity with production (drop_na=True)."
            )

        _, y_full, _ = load_target_data(
            spec["target"], spec["horizon"], drop_na=True, verbose=False
        )
        y_col = f"y_{spec['target']}"

        if verbose:
            print(f"Target: {y_col}")

        # Setup conformal prediction (mirror production defaults/ACI toggles)
        conformal_cfg = ConformalConfig(
            enabled=self.config.conformal_enabled,
            confidence_level=1 - self.config.conformal_alpha,
        )
        aci = (
            AdaptiveConformalInference(
                alpha_target=conformal_cfg.alpha,
                gamma=conformal_cfg.aci_gamma,
                alpha_min=conformal_cfg.aci_alpha_min,
                alpha_max=conformal_cfg.aci_alpha_max,
            )
            if conformal_cfg.enabled and conformal_cfg.aci_enabled
            else None
        )

        # Get L2 split sizes (production-aligned)
        effective_window = metadata.l2_window_size
        train_size, cal_size, val_size, purge_gap = self.config.get_l2_splits(
            spec["horizon"], window_size=effective_window
        )

        if verbose:
            print(
                f"L2 window: train={train_size}, cal={cal_size}, val={val_size}, "
                f"purge={purge_gap}, horizon={spec['horizon']}"
            )
            print(f"\nRunning {n_iterations} iterations...")

        # Run L2-only walk-forward
        results: list[IterationResult] = []

        for iteration in range(n_iterations):
            iter_meta = index[iteration]

            # Load precomputed helper features for this iteration
            helper_features = load_precomputed_l1(config_name, iteration, l1_cfg)

            # Basic structural checks to catch drift vs. production windowing
            expected_rows = effective_window + spec["horizon"]
            if len(helper_features) != expected_rows:
                raise ValueError(
                    f"Iteration {iteration}: expected {expected_rows} rows "
                    f"(window + horizon), got {len(helper_features)}"
                )

            # Get corresponding y slice
            l2_start = iter_meta["l2_start_idx"]
            l2_end = iter_meta["l2_end_idx"]
            pred_idx = iter_meta["pred_idx"]
            aligned_pred_idx = int(
                iter_meta.get("aligned_pred_idx", pred_idx + (spec["horizon"] - 1))
            )
            pred_timestamp = iter_meta.get("timestamp")
            aligned_timestamp = iter_meta.get("aligned_timestamp")

            y_l2 = y_full.iloc[l2_start:l2_end].reset_index(drop=True)

            # Split helper features for L2 (matching pipeline TargetRunner logic)
            X_l2 = helper_features.reset_index(drop=True)

            cal_start = train_size + purge_gap
            val_start = cal_start + cal_size
            pred_start = effective_window  # last horizon rows

            X_train = X_l2.iloc[:train_size]
            y_train = y_l2.iloc[:train_size]
            X_cal = X_l2.iloc[cal_start : cal_start + cal_size]
            y_cal = y_l2.iloc[cal_start : cal_start + cal_size]
            X_val = X_l2.iloc[val_start : val_start + val_size]
            y_val = y_l2.iloc[val_start : val_start + val_size]
            X_pred = X_l2.iloc[pred_start : pred_start + spec["horizon"]]

            # ──────────────────────────────────────────────────────────────────
            # Tier 1.1: Class balance validation (prevents single-class failures)
            # ──────────────────────────────────────────────────────────────────
            balance_score = None
            skip_reason = None

            if spec["task_type"] != "regression" and self.config.validate_class_balance:
                is_valid, msg, metrics = validate_class_balance(
                    y_train.values,
                    min_samples_per_class=self.config.min_samples_per_class,
                    min_balance_score=self.config.min_balance_score,
                )
                balance_score = metrics.balance_score if metrics else None

                if not is_valid:
                    skip_reason = msg
                    logger.warning(
                        f"Iteration {iteration} (pred_idx={pred_idx}): "
                        f"Skipping due to class imbalance - {msg}"
                    )
                    results.append(
                        IterationResult(
                            iteration=iteration,
                            pred_idx=pred_idx,
                            aligned_pred_idx=aligned_pred_idx,
                            y_pred=np.nan,
                            y_true=None,
                            pred_timestamp=pred_timestamp,
                            aligned_timestamp=aligned_timestamp,
                            skipped=True,
                            skip_reason=skip_reason,
                            balance_score=balance_score,
                        )
                    )
                    continue

            # Create and fit L2 model ensemble
            model_ensemble = create_model_ensemble(
                target=spec["target"],
                horizon=spec["horizon"],
                task_type=spec["task_type"],
                n_classes=spec["n_classes"],
                random_state=self.config.random_state + iteration,
            )

            model_ensemble.fit(X_train, y_train, X_val=X_val, y_val=y_val)

            # Calibrate (isotonic for classification)
            if spec["task_type"] != "regression":
                model_ensemble.calibrate(X_cal, y_cal, method="isotonic")

            # Predict
            output = model_ensemble.predict(X_pred)

            # Get y_pred and aligned y_true (last horizon target)
            y_pred = output.y_pred[-1]  # Last prediction (aligned)
            y_true_window = y_full.iloc[pred_idx : pred_idx + spec["horizon"]]
            y_true_aligned = (
                y_true_window.iloc[-1]
                if len(y_true_window) == spec["horizon"]
                else None
            )
            y_true = y_true_aligned
            y_prob = (
                output.y_prob_calibrated
                if output.y_prob_calibrated is not None
                else output.y_prob
            )

            # Apply conformal prediction (same flow as pipeline TargetRunner)
            prediction_set = None
            prediction_interval = None
            uncertainty = None
            covered = None
            current_alpha = conformal_cfg.alpha

            if self.config.conformal_enabled:
                current_alpha = aci.alpha if aci else conformal_cfg.alpha

                try:
                    if spec["task_type"] != "regression":
                        conf_wrapper = ConformalClassifier(
                            model_ensemble, conformal_cfg
                        )
                        conf_wrapper.calibrate(X_cal.values, y_cal.values)
                        sets = conf_wrapper.predict_with_sets(
                            X_pred.values, alpha=current_alpha
                        )
                        prediction_set = sets[-1]
                        uncertainty = float(np.sum(prediction_set))

                        if y_true is not None:
                            covered = bool(prediction_set[int(y_true)])
                    else:
                        conf_wrapper = ConformalRegressor(model_ensemble, conformal_cfg)
                        conf_wrapper.calibrate(X_cal.values, y_cal.values)
                        intervals = conf_wrapper.predict_with_intervals(
                            X_pred.values, alpha=current_alpha
                        )
                        lower, upper = intervals[-1]
                        prediction_interval = (float(lower), float(upper))
                        uncertainty = float(upper - lower)

                        if y_true is not None:
                            covered = lower <= y_true <= upper

                    # Update ACI
                    if aci and covered is not None:
                        error_rate = 0.0 if covered else 1.0
                        aci.update_batch(error_rate)

                except Exception as e:
                    if verbose and iteration == 0:
                        print(f"  Warning: Conformal prediction failed: {e}")

            results.append(
                IterationResult(
                    iteration=iteration,
                    pred_idx=pred_idx,
                    aligned_pred_idx=aligned_pred_idx,
                    pred_timestamp=pred_timestamp,
                    aligned_timestamp=aligned_timestamp,
                    y_pred=y_pred,
                    y_true=y_true,
                    y_prob=y_prob[-1] if y_prob is not None else None,
                    prediction_set=prediction_set,
                    prediction_interval=prediction_interval,
                    uncertainty=uncertainty,
                    covered=covered,
                    skipped=False,
                    skip_reason=None,
                    balance_score=balance_score,
                )
            )

            if verbose and (iteration + 1) % 50 == 0:
                elapsed = time.time() - start_time
                rate = (iteration + 1) / elapsed
                remaining = (n_iterations - iteration - 1) / rate
                print(
                    f"  Iteration {iteration + 1}/{n_iterations} "
                    f"[{elapsed:.1f}s elapsed, ~{remaining:.1f}s remaining]"
                )

        # Aggregate results
        total_time = time.time() - start_time
        predictions_df = self._build_predictions_df(results, spec)
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

        # Calculate skip metrics (Tier 1.1)
        n_skipped = (
            predictions_df["skipped"].sum()
            if "skipped" in predictions_df.columns
            else 0
        )
        skip_rate = n_skipped / n_iterations if n_iterations > 0 else 0.0

        if verbose:
            print(
                f"\n✓ Completed in {total_time:.1f}s ({total_time / n_iterations:.2f}s/iter)"
            )
            if n_skipped > 0:
                print(
                    f"  ⚠️ Skipped {n_skipped}/{n_iterations} iterations "
                    f"({skip_rate:.1%}) due to class imbalance"
                )
            if metrics:
                print(
                    f"  Primary metric: {list(metrics.keys())[0]}={list(metrics.values())[0]:.4f}"
                )
            if coverage is not None:
                print(f"  Coverage: {coverage:.1%}")

        return BacktestResult(
            config_name=config_name,
            task_type=spec["task_type"],
            n_iterations=n_iterations,
            elapsed_seconds=total_time,
            predictions=predictions_df,
            metrics=metrics,
            coverage=coverage,
            mean_interval_width=mean_interval_width,
            mean_set_size=mean_set_size,
            n_skipped=n_skipped,
            skip_rate=skip_rate,
        )

    def _build_predictions_df(
        self,
        results: list[IterationResult],
        spec: dict,
    ) -> pd.DataFrame:
        """Build predictions DataFrame from iteration results."""
        records = []
        for r in results:
            record = {
                "iteration": r.iteration,
                "pred_idx": r.pred_idx,
                "aligned_pred_idx": r.aligned_pred_idx,
                "pred_timestamp": r.pred_timestamp,
                "aligned_timestamp": r.aligned_timestamp,
                "y_pred": r.y_pred,
                "y_true": r.y_true,
                "y_prob": r.y_prob,
                "covered": r.covered,
                "uncertainty": r.uncertainty,
                # Tier 1.1: Class balance validation fields
                "skipped": r.skipped,
                "skip_reason": r.skip_reason,
                "balance_score": r.balance_score,
            }

            if spec["task_type"] == "regression":
                if r.prediction_interval:
                    record["interval_lower"] = r.prediction_interval[0]
                    record["interval_upper"] = r.prediction_interval[1]
                    record["interval_width"] = (
                        r.prediction_interval[1] - r.prediction_interval[0]
                    )
            else:
                if r.prediction_set is not None:
                    record["set_size"] = np.sum(r.prediction_set)

            records.append(record)

        return pd.DataFrame(records)

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
            from scipy.stats import spearmanr

            ic, _ = spearmanr(y_true, y_pred)
            metrics["ic"] = ic

            # MSE, MAE
            mse = ((y_true - y_pred) ** 2).mean()
            mae = (y_true - y_pred).abs().mean()
            metrics["mse"] = mse
            metrics["mae"] = mae

        elif spec["task_type"] == "binary":
            # Accuracy, AUC
            from sklearn.metrics import accuracy_score, roc_auc_score

            accuracy = accuracy_score(y_true, y_pred)
            metrics["accuracy"] = accuracy

            # AUC if we have probabilities
            if "y_prob" in predictions.columns:
                try:
                    probs = predictions.loc[y_true.index, "y_prob"]
                    auc = roc_auc_score(y_true, probs)
                    metrics["auc"] = auc
                except Exception:
                    pass

        else:  # multiclass
            from sklearn.metrics import accuracy_score

            accuracy = accuracy_score(y_true, y_pred)
            metrics["accuracy"] = accuracy

        # Economic simulation metrics (Tier 1.6)
        if self.config.compute_economic_metrics:
            econ_metrics = self._compute_economic_metrics(predictions, spec)
            metrics.update(econ_metrics)

        return metrics

    def _compute_economic_metrics(
        self,
        predictions: pd.DataFrame,
        spec: dict,
    ) -> dict[str, float]:
        """
        Compute economic simulation metrics including transaction costs,
        slippage, and drawdown analysis.

        These metrics answer: "Would this strategy actually make money?"

        Args:
            predictions: DataFrame with y_pred, y_true columns
            spec: Target specification with task_type

        Returns:
            Dict with economic metrics:
                - gross_sharpe: Sharpe before costs
                - net_sharpe: Sharpe after costs
                - max_drawdown: Maximum drawdown percentage
                - calmar_ratio: Annual return / max drawdown
                - total_trades: Number of position changes
                - total_cost_bps: Total transaction costs in bps
                - avg_slippage_bps: Average slippage in bps
        """
        metrics = {}

        # Get valid predictions (non-NaN y_true)
        valid = predictions.dropna(subset=["y_true"])
        if len(valid) < 10:
            return metrics

        y_true = valid["y_true"].values
        y_pred = valid["y_pred"].values

        # Determine position from prediction
        # For regression: sign of prediction
        # For classification: +1 if pred=1 (long), -1 if pred=0 (short)
        if spec["task_type"] == "regression":
            positions = np.sign(y_pred)
        elif spec["task_type"] == "binary":
            positions = np.where(y_pred == 1, 1.0, -1.0)
        else:  # multiclass (regime) - harder to convert to position
            # For regime targets, we can't directly map to positions
            return metrics

        # Calculate gross returns (before costs)
        # Strategy return = position * actual return
        gross_returns = positions * y_true

        # Calculate position changes (for transaction costs)
        position_changes = np.abs(np.diff(positions, prepend=positions[0]))
        n_trades = int(np.sum(position_changes > 0))

        # Transaction costs (in return terms)
        # Each position change of 2 (full flip) costs transaction_cost_bps
        cost_per_flip = (
            self.config.transaction_cost_bps / 10000
        )  # Convert bps to decimal
        transaction_costs = (
            position_changes * cost_per_flip / 2
        )  # /2 because change of 2 = full flip

        # Slippage (proportional to volatility)
        # Estimate realized volatility using rolling std
        vol_window = 21
        realized_vol = np.zeros_like(y_true)
        for i in range(vol_window, len(y_true)):
            realized_vol[i] = np.std(y_true[i - vol_window : i])

        # Slippage only on trade execution
        slippage = (
            position_changes
            * realized_vol
            * self.config.slippage_vol_fraction
            / 2  # /2 for same reason as above
        )

        # Net returns (after costs)
        net_returns = gross_returns - transaction_costs - slippage

        # Compute metrics
        n_periods = len(gross_returns)
        periods_per_year = 1095  # 8-hour bars: 3/day * 365

        # Sharpe ratios
        if np.std(gross_returns) > 0:
            gross_sharpe = (
                np.mean(gross_returns)
                / np.std(gross_returns)
                * np.sqrt(periods_per_year)
            )
            metrics["gross_sharpe"] = float(gross_sharpe)

        if np.std(net_returns) > 0:
            net_sharpe = (
                np.mean(net_returns) / np.std(net_returns) * np.sqrt(periods_per_year)
            )
            metrics["net_sharpe"] = float(net_sharpe)

        # Max drawdown
        cumulative_returns = np.cumsum(net_returns)
        running_max = np.maximum.accumulate(cumulative_returns)
        drawdowns = cumulative_returns - running_max
        max_drawdown = float(np.min(drawdowns))
        metrics["max_drawdown"] = max_drawdown

        # Calmar ratio (annual return / max drawdown)
        if max_drawdown < 0:
            annual_return = np.mean(net_returns) * periods_per_year
            calmar = annual_return / abs(max_drawdown)
            metrics["calmar_ratio"] = float(calmar)

        # Trade statistics
        metrics["total_trades"] = n_trades
        metrics["turnover_rate"] = float(n_trades / n_periods) if n_periods > 0 else 0.0

        # Cost breakdown
        total_cost = float(np.sum(transaction_costs))
        total_slippage = float(np.sum(slippage))
        metrics["total_cost_bps"] = total_cost * 10000  # Convert back to bps
        metrics["total_slippage_bps"] = total_slippage * 10000
        metrics["cost_drag_bps"] = (total_cost + total_slippage) * 10000

        # Return metrics
        metrics["gross_return_annual"] = float(
            np.mean(gross_returns) * periods_per_year
        )
        metrics["net_return_annual"] = float(np.mean(net_returns) * periods_per_year)

        return metrics

    def run_all(
        self,
        configs: list[str] | None = None,
        verbose: bool = True,
    ) -> dict[str, BacktestResult]:
        """
        Run fast backtest for multiple configs.

        Args:
            configs: List of config names (default: all 20)
            verbose: Print progress

        Returns:
            Dict mapping config name to BacktestResult
        """
        if configs is None:
            configs = [
                f"{target}_{horizon}bar"
                for target in [
                    "returns",
                    "direction",
                    "volatility",
                    "vol_regime",
                    "trend_regime",
                ]
                for horizon in [1, 3, 6, 12]
            ]

        if verbose:
            print(f"Running fast backtest for {len(configs)} configs...")

        results = {}
        total_start = time.time()

        for i, config_name in enumerate(configs):
            if verbose:
                print(f"\n[{i + 1}/{len(configs)}] {config_name}")
            try:
                results[config_name] = self.run(config_name, verbose=verbose)
            except Exception as e:
                print(f"  ERROR: {e}")
                results[config_name] = None

        total_time = time.time() - total_start

        if verbose:
            success = sum(1 for v in results.values() if v is not None)
            print(f"\n{'=' * 60}")
            print(
                f"COMPLETE: {success}/{len(configs)} configs in {total_time / 60:.1f} minutes"
            )
            print(f"{'=' * 60}")

        return results

    @staticmethod
    def merge_aligned_predictions(
        results: dict[str, BacktestResult],
        how: str = "inner",
    ) -> pd.DataFrame:
        """Merge multiple BacktestResults by aligned prediction time.

        Uses `aligned_pred_idx` (end of horizon span) as the alignment key so
        longer horizons effectively start earlier and all 20 configs line up to
        the same decision bar.

        Args:
            results: Mapping config_name -> BacktestResult
            how: Join type: 'inner' (default) keeps only rows where all configs
                 have an aligned prediction; 'outer' keeps union.

        Returns:
            Wide DataFrame indexed by `aligned_pred_idx` with per-config columns.
        """
        if how not in {"inner", "outer"}:
            raise ValueError("how must be 'inner' or 'outer'")

        frames: list[pd.DataFrame] = []
        for config_name, res in results.items():
            if res is None:
                continue
            df = res.predictions.copy()
            if "aligned_pred_idx" not in df.columns:
                raise ValueError(
                    f"Missing aligned_pred_idx in predictions for {config_name}"
                )

            cols = [
                c
                for c in ["y_pred", "y_prob", "uncertainty", "covered"]
                if c in df.columns
            ]
            view = df.set_index("aligned_pred_idx")[cols]
            view = view.add_prefix(f"{config_name}__")
            frames.append(view)

        if not frames:
            return pd.DataFrame()

        join = "inner" if how == "inner" else "outer"
        merged = pd.concat(frames, axis=1, join=join).sort_index()
        merged.index.name = "aligned_pred_idx"
        return merged

    def save_results(
        self,
        result: BacktestResult,
        output_dir: Path | None = None,
    ) -> Path:
        """Save backtest results to JSON."""
        output_dir = output_dir or self.config.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        output_path = output_dir / f"{result.config_name}_backtest.json"

        data = {
            "config_name": result.config_name,
            "task_type": result.task_type,
            "n_iterations": result.n_iterations,
            "elapsed_seconds": result.elapsed_seconds,
            "metrics": result.metrics,
            "coverage": result.coverage,
            "mean_interval_width": result.mean_interval_width,
            "mean_set_size": result.mean_set_size,
        }

        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)

        # Also save predictions as parquet
        pred_path = output_dir / f"{result.config_name}_predictions.parquet"
        result.predictions.to_parquet(pred_path)

        return output_path


if __name__ == "__main__":
    import warnings

    warnings.filterwarnings("ignore")

    # Test with one config
    config = BacktestConfig(backtest_rows=200)
    backtester = FastBacktester(config)

    # Run fast backtest (requires precomputed features)
    try:
        result = backtester.run("direction_1bar", verbose=True)
        print(f"\nResult: {result}")
        print(f"Metrics: {result.metrics}")
    except FileNotFoundError as e:
        print(f"\n{e}")
        print("\nRun l1_precompute.py first to generate precomputed features.")
