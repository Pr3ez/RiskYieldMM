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
from scripts.target_models.calibration.cqr import CQRConfig, CQRRegressor
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
from scripts.target_models.validation.statistical_metrics import (
    compute_conformal_sizing_metrics,
    compute_deflated_sharpe_ratio,
    compute_regime_metrics,
    compute_rolling_metrics,
    compute_sortino_ratio,
    compute_tail_risk_metrics,
    compute_trade_metrics,
)

logger = logging.getLogger(__name__)


def clip_extreme_features(
    df: pd.DataFrame,
    clip_percentile: float = 99,
    duration_max: float = 500,
) -> pd.DataFrame:
    """
    Clip extreme feature values to prevent model explosion.

    Specifically targets HMM duration features which can reach 10,000+
    while other features are typically in 0-5 range.

    Args:
        df: DataFrame with features
        clip_percentile: Percentile for general feature clipping (default: 99)
        duration_max: Hard cap for duration features (default: 500)

    Returns:
        DataFrame with clipped features
    """
    df = df.copy()

    # Find duration columns (HMM state duration features)
    duration_cols = [c for c in df.columns if "_duration" in c.lower()]

    if duration_cols:
        for col in duration_cols:
            original_max = df[col].max()
            if original_max > duration_max:
                df[col] = df[col].clip(upper=duration_max)
                logger.debug(
                    f"Clipped {col}: max {original_max:.0f} -> {duration_max:.0f}"
                )

    return df


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

    # CQR (Conformalized Quantile Regression) for heteroscedasticity
    # CQR produces adaptive-width intervals based on predicted uncertainty
    # Validation (2025-01-01): CQR achieves 5/6 configs in target range vs 0/6 for standard
    # Research: docs/conformal/HETEROSCEDASTICITY_ANALYSIS.md
    use_cqr: bool = True  # Default True - CQR is strictly better for regression

    # Model settings
    random_state: int = 42

    # Class balance validation (Tier 1.1) - SAFETY NET, not primary fix
    # Primary fix is use_adaptive_window=True + class_weight='balanced' in models
    # With balanced class weights, models can handle smaller minority classes
    validate_class_balance: bool = True
    min_samples_per_class: int = 10  # Lowered from 30 since we now use class weights
    min_balance_score: float = 0.3

    # Feature clipping (Tier 0 fix for HMM duration explosion)
    # HMM duration features can reach 10,000+ causing model explosion
    clip_extreme_features: bool = True
    duration_feature_max: float = 500.0  # Hard cap for _duration features

    # Economic simulation (Tier 1.6)
    # Transaction costs as fraction of trade value (e.g., 0.001 = 0.1%)
    transaction_cost_bps: float = 10.0  # 10 bps = 0.1% round trip
    # Slippage as fraction of volatility
    slippage_vol_fraction: float = 0.1  # 10% of realized volatility
    # Enable economic simulation in metrics
    compute_economic_metrics: bool = True

    # Statistical rigor metrics (Tier 3)
    # DSR: Deflated Sharpe Ratio corrects for multiple testing and non-normality
    # Regime: Metrics partitioned by volatility regime (high/normal/low)
    compute_statistical_metrics: bool = True
    n_optuna_trials: int = 20  # Number of trials tested (for DSR correction)

    # Distribution shift detection (Tier 5)
    # PSI: Population Stability Index detects covariate shift in features
    # Rolling metrics: Detect concept drift via degrading IC/Sharpe over time
    detect_distribution_shift: bool = True
    psi_bins: int = 10  # Number of bins for PSI calculation
    rolling_window_size: int = 30  # Window size for rolling metrics

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

            # Clip extreme features (HMM duration can reach 10,000+)
            if self.config.clip_extreme_features:
                helper_features = clip_extreme_features(
                    helper_features,
                    duration_max=self.config.duration_feature_max,
                )

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
                        # Use CQR for regression if enabled (handles heteroscedasticity)
                        if self.config.use_cqr:
                            cqr_config = CQRConfig(
                                alpha=self.config.conformal_alpha,
                                aci_enabled=conformal_cfg.aci_enabled,
                                aci_gamma=conformal_cfg.aci_gamma,
                                random_state=self.config.random_state + iteration,
                            )
                            cqr = CQRRegressor(cqr_config)
                            cqr.fit(
                                X_train.values,
                                y_train.values,
                                X_val.values,
                                y_val.values,
                            )
                            cqr.calibrate(X_cal.values, y_cal.values)
                            _, intervals = cqr.predict(X_pred.values)
                        else:
                            # Standard conformal (constant-width intervals)
                            conf_wrapper = ConformalRegressor(
                                model_ensemble, conformal_cfg
                            )
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

        # Statistical rigor metrics (Tier 3)
        if self.config.compute_statistical_metrics:
            stat_metrics = self._compute_statistical_metrics(predictions, spec)
            metrics.update(stat_metrics)

        # Distribution shift detection (Tier 5)
        if self.config.detect_distribution_shift:
            shift_metrics = self._compute_shift_metrics(predictions, spec)
            metrics.update(shift_metrics)

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

        # =====================================================================
        # TIER 4 ENHANCED METRICS
        # =====================================================================

        # 1. Tail risk metrics (CVaR, VaR)
        tail_risk = compute_tail_risk_metrics(net_returns)
        metrics["var_95"] = tail_risk.var_95
        metrics["var_99"] = tail_risk.var_99
        metrics["cvar_95"] = tail_risk.cvar_95
        metrics["cvar_99"] = tail_risk.cvar_99
        metrics["max_drawdown_duration"] = tail_risk.max_drawdown_duration

        # 2. Trade-level metrics (win rate, profit factor)
        trade_metrics = compute_trade_metrics(net_returns)
        metrics["win_rate"] = trade_metrics.win_rate
        metrics["profit_factor"] = trade_metrics.profit_factor
        metrics["avg_win"] = trade_metrics.avg_win
        metrics["avg_loss"] = trade_metrics.avg_loss
        metrics["win_loss_ratio"] = trade_metrics.win_loss_ratio
        metrics["expectancy"] = trade_metrics.expectancy

        # 3. Sortino ratio (downside-only risk)
        sortino = compute_sortino_ratio(net_returns, periods_per_year=periods_per_year)
        metrics["sortino_ratio"] = sortino

        # 4. Conformal-aware position sizing (if interval_width available)
        if "interval_width" in predictions.columns:
            interval_widths = predictions["interval_width"].values
            valid_widths = ~np.isnan(interval_widths)

            if np.sum(valid_widths) > 10:
                conformal_sizing = compute_conformal_sizing_metrics(
                    returns=y_true[valid_widths],
                    predictions=y_pred[valid_widths],
                    interval_widths=interval_widths[valid_widths],
                    scaling_factor=1.0,  # Can be tuned
                    min_position=0.1,
                    max_position=1.0,
                    periods_per_year=periods_per_year,
                )

                metrics["conformal_sharpe"] = conformal_sizing.conformal_sharpe
                metrics["conformal_sizing_benefit"] = conformal_sizing.sizing_benefit
                metrics["conformal_avg_position"] = conformal_sizing.avg_position_size
                metrics["uncertainty_error_correlation"] = (
                    conformal_sizing.uncertainty_correlation
                )

        return metrics

    def _compute_statistical_metrics(
        self,
        predictions: pd.DataFrame,
        spec: dict,
    ) -> dict[str, float]:
        """
        Compute statistical rigor metrics (Tier 3).

        Includes:
        1. Deflated Sharpe Ratio (DSR) - corrected for multiple testing
        2. Regime-conditional metrics - performance across volatility regimes

        Args:
            predictions: DataFrame with y_pred, y_true columns
            spec: Target specification with task_type

        Returns:
            Dict with statistical metrics:
                - dsr: Deflated Sharpe Ratio
                - dsr_p_value: P-value for DSR significance
                - dsr_significant: Whether DSR is statistically significant
                - regime_ic_high: IC during high volatility
                - regime_ic_normal: IC during normal volatility
                - regime_ic_low: IC during low volatility
                - regime_sharpe_high/normal/low: Sharpe by regime
        """
        metrics = {}

        # Get valid predictions
        valid = predictions.dropna(subset=["y_true"])
        if len(valid) < 50:  # Need minimum samples for statistical tests
            return metrics

        y_true = valid["y_true"].values
        y_pred = valid["y_pred"].values

        # Only compute for regression or binary (not multiclass regime)
        if spec["task_type"] not in ("regression", "binary"):
            return metrics

        # Calculate strategy returns for DSR
        if spec["task_type"] == "regression":
            positions = np.sign(y_pred)
        else:  # binary
            positions = np.where(y_pred == 1, 1.0, -1.0)

        strategy_returns = positions * y_true

        # 1. Deflated Sharpe Ratio
        try:
            dsr_result = compute_deflated_sharpe_ratio(
                strategy_returns,
                n_trials=self.config.n_optuna_trials,
                periods_per_year=1095,  # 8-hour bars
            )
            metrics["dsr"] = dsr_result.deflated_sharpe
            metrics["dsr_p_value"] = dsr_result.p_value
            metrics["dsr_significant"] = dsr_result.is_significant
            metrics["dsr_skewness"] = dsr_result.skewness
            metrics["dsr_kurtosis"] = dsr_result.kurtosis
        except Exception as e:
            logger.warning(f"DSR calculation failed: {e}")

        # 2. Regime-conditional metrics
        try:
            regime_result = compute_regime_metrics(
                returns=y_true,
                predictions=y_pred,
                vol_window=21,
                high_quantile=0.75,
                low_quantile=0.25,
            )

            # IC by regime
            metrics["regime_ic_high"] = regime_result.high_vol.get("ic", np.nan)
            metrics["regime_ic_normal"] = regime_result.normal.get("ic", np.nan)
            metrics["regime_ic_low"] = regime_result.low_vol.get("ic", np.nan)

            # Sharpe by regime
            metrics["regime_sharpe_high"] = regime_result.high_vol.get("sharpe", np.nan)
            metrics["regime_sharpe_normal"] = regime_result.normal.get("sharpe", np.nan)
            metrics["regime_sharpe_low"] = regime_result.low_vol.get("sharpe", np.nan)

            # Accuracy by regime
            metrics["regime_accuracy_high"] = regime_result.high_vol.get(
                "accuracy", np.nan
            )
            metrics["regime_accuracy_normal"] = regime_result.normal.get(
                "accuracy", np.nan
            )
            metrics["regime_accuracy_low"] = regime_result.low_vol.get(
                "accuracy", np.nan
            )

            # Sample counts
            metrics["regime_n_high"] = regime_result.regime_counts.get("high", 0)
            metrics["regime_n_normal"] = regime_result.regime_counts.get("normal", 0)
            metrics["regime_n_low"] = regime_result.regime_counts.get("low", 0)

        except Exception as e:
            logger.warning(f"Regime metrics calculation failed: {e}")

        return metrics

    def _compute_shift_metrics(
        self,
        predictions: pd.DataFrame,
        spec: dict,
    ) -> dict[str, float]:
        """
        Compute distribution shift detection metrics (Tier 5).

        Detects two types of shift:
        1. Covariate shift (PSI): Feature distributions changing between train/test
        2. Concept drift (rolling IC/Sharpe): Model performance degrading over time

        Args:
            predictions: DataFrame with y_pred, y_true, and feature columns
            spec: Target specification with task_type

        Returns:
            Dict with shift metrics:
                - concept_drift_detected: Boolean flag for drift
                - ic_trend: Slope of rolling IC (negative = degrading)
                - sharpe_trend: Slope of rolling Sharpe
                - recent_vs_early_ic: Ratio comparing recent to early performance
        """
        metrics = {}

        # Get valid predictions
        valid = predictions.dropna(subset=["y_true"])
        if len(valid) < 30:  # Need minimum samples for rolling metrics
            return metrics

        y_true = valid["y_true"].values
        y_pred = valid["y_pred"].values

        try:
            # Compute rolling metrics to detect concept drift
            rolling_result = compute_rolling_metrics(
                predictions=y_pred,
                actuals=y_true,
                returns=None,  # Will use sign(pred) * actual
                window_size=self.config.rolling_window_size,
                min_periods=10,
                degradation_threshold=-0.01,
            )

            # Core drift metrics
            metrics["concept_drift_detected"] = rolling_result.concept_drift_detected
            metrics["ic_trend"] = rolling_result.ic_trend
            metrics["sharpe_trend"] = rolling_result.sharpe_trend
            metrics["ic_volatility"] = rolling_result.ic_volatility
            metrics["recent_vs_early_ic"] = rolling_result.recent_vs_early_ic
            metrics["ic_degrading"] = rolling_result.ic_degrading
            metrics["sharpe_degrading"] = rolling_result.sharpe_degrading

        except Exception as e:
            logger.warning(f"Concept drift detection failed: {e}")

        # Note: PSI (covariate shift) requires feature columns which may not
        # always be in predictions DataFrame. If needed, can extend to track
        # feature distributions separately during backtest iteration.

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

    def run_strategy_backtest(
        self,
        horizon: int = 1,
        ohlc_path: str | Path | None = None,
        strategy_config: dict | None = None,
        verbose: bool = True,
    ) -> StrategyBacktestResult:
        """
        Run regime-filtered strategy backtest using model predictions.

        This runs direction, vol_regime, and trend_regime models, then applies
        the regime filter strategy to only trade in profitable conditions.

        Args:
            horizon: Horizon for all models (default: 1 = 8h bars)
            ohlc_path: Path to OHLC parquet file (default: auto-detect)
            strategy_config: Config overrides for RegimeFilterConfig
            verbose: Print progress

        Returns:
            StrategyBacktestResult with trades and metrics

        Example:
            >>> backtester = FastBacktester(BacktestConfig(backtest_rows=300))
            >>> result = backtester.run_strategy_backtest(horizon=1)
            >>> print(f"Win rate: {result.win_rate:.1%}")
            >>> print(f"Avg PnL: {result.avg_pnl_bps:.1f} bps")
        """
        from scripts.strategy.regime_filtered_strategy import (
            ModelPredictions,
            RegimeFilterConfig,
            RegimeFilteredStrategy,
        )

        start_time = time.time()

        if verbose:
            print("\n" + "=" * 70)
            print("REGIME-FILTERED STRATEGY BACKTEST")
            print("=" * 70)

        # ─────────────────────────────────────────────────────────────────────
        # Step 1: Run all three model backtests
        # ─────────────────────────────────────────────────────────────────────
        if verbose:
            print("\n[1/4] Running model backtests...")

        dir_result = self.run(f"direction_{horizon}bar", verbose=False)
        vol_result = self.run(f"vol_regime_{horizon}bar", verbose=False)
        trend_result = self.run(f"trend_regime_{horizon}bar", verbose=False)

        if verbose:
            print(f"  Direction: {len(dir_result.predictions)} predictions")
            print(f"  Vol regime: {len(vol_result.predictions)} predictions")
            print(f"  Trend regime: {len(trend_result.predictions)} predictions")

        # ─────────────────────────────────────────────────────────────────────
        # Step 2: Merge predictions
        # ─────────────────────────────────────────────────────────────────────
        if verbose:
            print("\n[2/4] Merging predictions...")

        predictions_df = self._merge_strategy_predictions(
            dir_result, vol_result, trend_result
        )

        if verbose:
            print(f"  Merged: {len(predictions_df)} aligned predictions")

            # Show regime distribution
            vol_dist = predictions_df["vol_pred"].value_counts().sort_index().to_dict()
            trend_dist = (
                predictions_df["trend_pred"].value_counts().sort_index().to_dict()
            )
            print(f"  Vol regime dist: {vol_dist}")
            print(f"  Trend regime dist: {trend_dist}")

            # Optimal regime count
            mask = (predictions_df["vol_pred"] == 0) & (
                predictions_df["trend_pred"] == 1
            )
            print(
                f"  Optimal regime (vol=0, trend=1): {mask.sum()} ({mask.mean():.1%})"
            )

        # ─────────────────────────────────────────────────────────────────────
        # Step 3: Load OHLC data
        # ─────────────────────────────────────────────────────────────────────
        if verbose:
            print("\n[3/4] Loading OHLC data...")

        ohlc_df = self._load_ohlc_data(ohlc_path, horizon)

        if verbose:
            print(f"  OHLC rows: {len(ohlc_df)}")
            print(f"  Date range: {ohlc_df.index.min()} to {ohlc_df.index.max()}")

        # ─────────────────────────────────────────────────────────────────────
        # Step 4: Run strategy backtest
        # ─────────────────────────────────────────────────────────────────────
        if verbose:
            print("\n[4/4] Running strategy backtest...")

        # Create strategy
        cfg_dict = {
            "optimal_vol_regimes": {0},
            "optimal_trend_regimes": {1},
            "take_profit_bps": 50.0,
            "stop_loss_bps": 30.0,
            "transaction_cost_bps": self.config.transaction_cost_bps,
            "min_direction_prob": 0.5,
            "min_vol_regime_prob": 0.5,
            "min_trend_regime_prob": 0.5,
        }
        if strategy_config:
            cfg_dict.update(strategy_config)

        strategy = RegimeFilteredStrategy(RegimeFilterConfig(**cfg_dict))

        # Execute backtest
        trades = []
        hours_per_bar = horizon * 8  # Assuming 8h base timeframe

        for _, row in predictions_df.iterrows():
            # Skip if any prediction is NaN
            if (
                pd.isna(row["dir_pred"])
                or pd.isna(row["vol_pred"])
                or pd.isna(row["trend_pred"])
            ):
                continue

            # Create predictions object
            preds = ModelPredictions(
                timestamp=row["timestamp"],
                direction_pred=int(row["dir_pred"]),
                direction_prob=float(row["dir_prob"]),
                vol_regime_pred=int(row["vol_pred"]),
                vol_regime_prob=float(row["vol_prob"]),
                trend_regime_pred=int(row["trend_pred"]),
                trend_regime_prob=float(row["trend_prob"]),
            )

            # Generate signal
            signal = strategy.generate_signal(preds)

            if not signal.should_trade:
                continue

            # Get next bar's OHLC
            next_ts = row["timestamp"] + pd.Timedelta(hours=hours_per_bar)
            if next_ts not in ohlc_df.index:
                continue

            next_bar = ohlc_df.loc[next_ts]
            entry_price = next_bar["open"]

            # Create entry order
            entry = strategy.create_entry(signal, entry_price)

            # Check exit using actual high/low/close
            _, exit_price, exit_reason = strategy.check_exit(
                entry, next_bar["high"], next_bar["low"], next_bar["close"]
            )

            # Calculate PnL
            pnl_bps = strategy.calculate_pnl(entry, exit_price, include_costs=True)

            trades.append(
                {
                    "timestamp": row["timestamp"],
                    "direction": signal.direction.name,
                    "dir_true": row["dir_true"],
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "exit_reason": exit_reason,
                    "pnl_bps": pnl_bps,
                    "vol_regime": signal.vol_regime.value,
                    "trend_regime": signal.trend_regime.value,
                    "confidence": signal.confidence,
                }
            )

        # Build result
        elapsed = time.time() - start_time
        result = StrategyBacktestResult.from_trades(
            trades=trades,
            predictions_df=predictions_df,
            strategy_config=cfg_dict,
            elapsed_seconds=elapsed,
            horizon=horizon,
        )

        if verbose:
            print("\n" + "=" * 70)
            print("STRATEGY BACKTEST RESULTS")
            print("=" * 70)
            print(f"\nTotal predictions: {len(predictions_df)}")
            print(f"Total trades: {result.n_trades}")
            print(f"Trade rate: {result.trade_rate:.1%}")
            print()
            print(f"Win rate: {result.win_rate:.1%}")
            print(f"Avg PnL (net): {result.avg_pnl_bps:.1f} bps")
            print(f"Total PnL: {result.total_pnl_bps:.1f} bps")
            print(f"Sharpe (annual): {result.sharpe:.2f}")
            print(f"Direction accuracy: {result.direction_accuracy:.1%}")
            print()
            print(
                f"Exit breakdown: TP={result.tp_hit_rate:.1%}, SL={result.sl_hit_rate:.1%}, HOLD={result.hold_rate:.1%}"
            )
            print(f"Elapsed: {elapsed:.1f}s")

        return result

    def _merge_strategy_predictions(
        self,
        dir_result: BacktestResult,
        vol_result: BacktestResult,
        trend_result: BacktestResult,
    ) -> pd.DataFrame:
        """
        Merge predictions from direction, vol_regime, and trend_regime models.

        Args:
            dir_result: Direction model backtest result
            vol_result: Vol regime model backtest result
            trend_result: Trend regime model backtest result

        Returns:
            DataFrame with aligned predictions
        """

        def extract_prob(x, default=0.6):
            """Extract max probability from array or scalar."""
            if x is None or (isinstance(x, float) and np.isnan(x)):
                return default
            if isinstance(x, np.ndarray):
                return float(np.max(x))
            try:
                return float(x)
            except (TypeError, ValueError):
                return default

        # Direction predictions
        dir_df = dir_result.predictions[
            ["iteration", "aligned_timestamp", "y_pred", "y_true", "y_prob", "skipped"]
        ].copy()
        dir_df = dir_df[~dir_df["skipped"]]
        dir_df["dir_prob"] = dir_df["y_prob"].apply(lambda x: extract_prob(x, 0.55))
        dir_df = dir_df[
            ["iteration", "aligned_timestamp", "y_pred", "y_true", "dir_prob"]
        ]
        dir_df.columns = ["iteration", "timestamp", "dir_pred", "dir_true", "dir_prob"]
        dir_df["timestamp"] = pd.to_datetime(dir_df["timestamp"])

        # Vol regime predictions
        vol_df = vol_result.predictions[
            ["iteration", "y_pred", "y_prob", "skipped"]
        ].copy()
        vol_df = vol_df[~vol_df["skipped"]]
        vol_df["vol_prob"] = vol_df["y_prob"].apply(lambda x: extract_prob(x, 0.8))
        vol_df = vol_df[["iteration", "y_pred", "vol_prob"]]
        vol_df.columns = ["iteration", "vol_pred", "vol_prob"]

        # Trend regime predictions
        trend_df = trend_result.predictions[
            ["iteration", "y_pred", "y_prob", "skipped"]
        ].copy()
        trend_df = trend_df[~trend_df["skipped"]]
        trend_df["trend_prob"] = trend_df["y_prob"].apply(
            lambda x: extract_prob(x, 0.7)
        )
        trend_df = trend_df[["iteration", "y_pred", "trend_prob"]]
        trend_df.columns = ["iteration", "trend_pred", "trend_prob"]

        # Merge on iteration (inner join)
        merged = dir_df.merge(vol_df, on="iteration").merge(trend_df, on="iteration")
        merged = merged.dropna()

        return merged

    def _load_ohlc_data(
        self,
        ohlc_path: str | Path | None,
        horizon: int,
    ) -> pd.DataFrame:
        """
        Load OHLC data for strategy backtest.

        Args:
            ohlc_path: Path to OHLC parquet file (auto-detect if None)
            horizon: Horizon for timeframe detection

        Returns:
            DataFrame with OHLC data indexed by timestamp
        """
        if ohlc_path is None:
            # Auto-detect based on horizon
            hours = horizon * 8
            ohlc_path = Path(
                f"fetchingByBit/mark-price-{hours}h-bybit-linear/btcusdt_mark_price_{hours}h.parquet"
            )

        ohlc = pd.read_parquet(ohlc_path)
        ohlc["timestamp"] = pd.to_datetime(ohlc["timestamp"])
        ohlc.set_index("timestamp", inplace=True)

        return ohlc


@dataclass
class StrategyBacktestResult:
    """Results from regime-filtered strategy backtest."""

    # Core metrics
    n_trades: int
    n_predictions: int
    trade_rate: float
    win_rate: float
    avg_pnl_bps: float
    std_pnl_bps: float
    total_pnl_bps: float
    sharpe: float

    # Direction accuracy
    direction_accuracy: float
    n_correct: int

    # Exit breakdown
    tp_hit_rate: float
    sl_hit_rate: float
    hold_rate: float

    # Trade details
    trades_df: pd.DataFrame
    predictions_df: pd.DataFrame

    # Config used
    strategy_config: dict
    horizon: int
    elapsed_seconds: float

    # Additional metrics
    max_win_bps: float = 0.0
    max_loss_bps: float = 0.0
    max_drawdown_bps: float = 0.0

    @classmethod
    def from_trades(
        cls,
        trades: list[dict],
        predictions_df: pd.DataFrame,
        strategy_config: dict,
        elapsed_seconds: float,
        horizon: int,
    ) -> StrategyBacktestResult:
        """Create result from list of trades."""
        if not trades:
            return cls(
                n_trades=0,
                n_predictions=len(predictions_df),
                trade_rate=0.0,
                win_rate=0.0,
                avg_pnl_bps=0.0,
                std_pnl_bps=0.0,
                total_pnl_bps=0.0,
                sharpe=0.0,
                direction_accuracy=0.0,
                n_correct=0,
                tp_hit_rate=0.0,
                sl_hit_rate=0.0,
                hold_rate=0.0,
                trades_df=pd.DataFrame(),
                predictions_df=predictions_df,
                strategy_config=strategy_config,
                horizon=horizon,
                elapsed_seconds=elapsed_seconds,
            )

        trades_df = pd.DataFrame(trades)
        n_trades = len(trades_df)
        n_predictions = len(predictions_df)

        # Core metrics
        win_rate = (trades_df["pnl_bps"] > 0).mean()
        avg_pnl = trades_df["pnl_bps"].mean()
        std_pnl = trades_df["pnl_bps"].std() if n_trades > 1 else 0.0
        total_pnl = trades_df["pnl_bps"].sum()

        # Sharpe (annualized for 8h bars = 3/day * 365)
        periods_per_year = 365 * 3 / horizon
        sharpe = avg_pnl / std_pnl * np.sqrt(periods_per_year) if std_pnl > 0 else 0.0

        # Direction accuracy
        n_correct = sum(
            1
            for _, t in trades_df.iterrows()
            if (1 if t["direction"] == "LONG" else 0) == t["dir_true"]
        )
        direction_accuracy = n_correct / n_trades if n_trades > 0 else 0.0

        # Exit breakdown
        tp_hit_rate = (trades_df["exit_reason"] == "TP_HIT").mean()
        sl_hit_rate = (trades_df["exit_reason"] == "SL_HIT").mean()
        hold_rate = (trades_df["exit_reason"] == "HOLDING").mean()

        # Max/min
        max_win = trades_df["pnl_bps"].max()
        max_loss = trades_df["pnl_bps"].min()

        # Max drawdown
        cum_pnl = trades_df["pnl_bps"].cumsum()
        max_dd = (cum_pnl - cum_pnl.cummax()).min()

        return cls(
            n_trades=n_trades,
            n_predictions=n_predictions,
            trade_rate=n_trades / n_predictions if n_predictions > 0 else 0.0,
            win_rate=win_rate,
            avg_pnl_bps=avg_pnl,
            std_pnl_bps=std_pnl,
            total_pnl_bps=total_pnl,
            sharpe=sharpe,
            direction_accuracy=direction_accuracy,
            n_correct=n_correct,
            tp_hit_rate=tp_hit_rate,
            sl_hit_rate=sl_hit_rate,
            hold_rate=hold_rate,
            trades_df=trades_df,
            predictions_df=predictions_df,
            strategy_config=strategy_config,
            horizon=horizon,
            elapsed_seconds=elapsed_seconds,
            max_win_bps=max_win,
            max_loss_bps=max_loss,
            max_drawdown_bps=max_dd,
        )

    def __repr__(self) -> str:
        return (
            f"StrategyBacktestResult(trades={self.n_trades}, "
            f"win_rate={self.win_rate:.1%}, avg_pnl={self.avg_pnl_bps:.1f}bps, "
            f"sharpe={self.sharpe:.2f})"
        )

    def summary(self) -> str:
        """Generate a formatted summary string."""
        return f"""
Regime-Filtered Strategy Results
================================
Trades: {self.n_trades} / {self.n_predictions} ({self.trade_rate:.1%} trade rate)
Win Rate: {self.win_rate:.1%}
Direction Accuracy: {self.direction_accuracy:.1%} ({self.n_correct}/{self.n_trades})

PnL Metrics:
  Avg PnL (net): {self.avg_pnl_bps:.1f} bps
  Std PnL: {self.std_pnl_bps:.1f} bps
  Total PnL: {self.total_pnl_bps:.1f} bps
  Max Win: {self.max_win_bps:.1f} bps
  Max Loss: {self.max_loss_bps:.1f} bps
  Max Drawdown: {self.max_drawdown_bps:.1f} bps

Risk-Adjusted:
  Sharpe (annual): {self.sharpe:.2f}

Exit Breakdown:
  TP Hit: {self.tp_hit_rate:.1%}
  SL Hit: {self.sl_hit_rate:.1%}
  Hold: {self.hold_rate:.1%}

Config: TP={self.strategy_config.get("take_profit_bps", 50)}bps, SL={self.strategy_config.get("stop_loss_bps", 30)}bps
Elapsed: {self.elapsed_seconds:.1f}s
"""


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
