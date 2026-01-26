"""
Pipeline Orchestrator for 20 Target-Horizon Models.

Manages the complete workflow:
1. Data loading for all 20 target-horizons
2. Layer 1 (helpers) → Layer 2 (supervised) execution per target
3. Ensemble predictions across targets (ALIGNED by horizon)
4. Position sizing layer for final output

HORIZON ALIGNMENT:
    Each horizon predicts `horizon` rows. The LAST prediction from each
    targets the SAME future bar, enabling proper ensemble combination:

    At walk-forward step t, to predict bar t+1:
        h=1:  predict 1 row  → targets t+1        ✓
        h=3:  predict 3 rows → last targets t+1   ✓
        h=6:  predict 6 rows → last targets t+1   ✓
        h=12: predict 12 rows → last targets t+1  ✓

    All 20 models' LAST prediction aligns to the same target bar.

Architecture:

    ┌─────────────────────────────────────────────────────────────────────┐
    │                        PIPELINE ORCHESTRATOR                         │
    ├─────────────────────────────────────────────────────────────────────┤
    │                                                                      │
    │  ┌─────────────────── PER TARGET-HORIZON ──────────────────────┐   │
    │  │                                                              │   │
    │  │  LAYER 1 (Unsupervised Helpers)                             │   │
    │  │  ├── HMM-4, HMM-5                                           │   │
    │  │  ├── GARCH(1,1)                                             │   │
    │  │  ├── Isolation Forest                                       │   │
    │  │  ├── Kalman Filter                                          │   │
    │  │  └── CUSUM                                                  │   │
    │  │       ↓                                                      │   │
    │  │  helper_features (58 features for Layer 2)                  │   │
    │  │       ↓                                                      │   │
    │  │  LAYER 2 (Supervised Models)                                │   │
    │  │  ├── CatBoost                                               │   │
    │  │  ├── LightGBM                                               │   │
    │  │  └── Ridge/LogisticRegression                               │   │
    │  │       ↓                                                      │   │
    │  │  predictions[horizon] → aligned_pred (last one)             │   │
    │  │                                                              │   │
    │  └──────────────────────────────────────────────────────────────┘   │
    │                              ↓                                       │
    │                    × 20 target-horizons                              │
    │                              ↓                                       │
    │  ┌────────────────── ENSEMBLE LAYER (ALIGNED) ──────────────────┐   │
    │  │  Combine LAST prediction from each horizon:                  │   │
    │  │  - direction_{1,3,6,12}.aligned  → P(up) for same bar       │   │
    │  │  - returns_{1,3,6,12}.aligned    → E[return] for same bar   │   │
    │  │  - volatility_{1,3,6,12}.aligned → E[vol] for same bar      │   │
    │  │  - vol_regime_{1,3,6,12}.aligned → regime for same bar      │   │
    │  │  - trend_regime_{1,3,6,12}.aligned → trend for same bar     │   │
    │  └──────────────────────────────────────────────────────────────┘   │
    │                              ↓                                       │
    │  ┌────────────────── POSITION SIZING ───────────────────────────┐   │
    │  │  V3 Pipeline:                                                │   │
    │  │  1. Gate check (prob >= threshold)                          │   │
    │  │  2. Rolling EMA ratio (TP/FP performance)                    │   │
    │  │  3. Config alignment (multi-model agreement)                 │   │
    │  │  4. Volatility adjustment                                    │   │
    │  │  5. Final position ∈ [0.0, 2.0]                             │   │
    │  └──────────────────────────────────────────────────────────────┘   │
    │                              ↓                                       │
    │                      FINAL PREDICTION (ONE per step)                 │
    │                                                                      │
    └─────────────────────────────────────────────────────────────────────┘

Usage:
    from scripts.target_models.pipeline import (
        PipelineOrchestrator,
        PipelineConfig,
        run_full_pipeline,
    )

    # Quick run
    results = run_full_pipeline()

    # Custom config
    config = PipelineConfig(
        targets=["direction", "volatility"],
        horizons=[6, 12],
    )
    orchestrator = PipelineOrchestrator(config)
    results = orchestrator.run()
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd

from .calibration import (
    AdaptiveConformalInference,
    ConformalClassifier,
    ConformalConfig,
    ConformalRegressor,
    apply_mapie_patches,
)
from .core import (
    DualLayerConfig,
    DualLayerEngine,
    DualLayerWindow,
    create_dual_config,
    validate_class_balance,
)
from .registry import (
    ALL_HORIZONS,
    ALL_TARGETS,
    TargetSpec,
    get_target_spec,
    load_target_data,
)

# Apply MAPIE patches for sklearn 1.8.0 compatibility
apply_mapie_patches()


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================
def extract_aligned_probability(
    y_prob: np.ndarray | None,
    task_type: str,
) -> float | None:
    """
    Extract a single aligned probability from model output.

    Model predictions return shape [n_samples, n_classes] for classification.
    This function extracts the appropriate scalar probability.

    Args:
        y_prob: Probability array from model
            - None: Regression task, return None
            - [n_samples, 2]: Binary classification, return P(class=1)
            - [n_samples, 3+]: Multiclass, return max probability
            - [n_samples]: Already 1D, return as-is
        task_type: One of 'regression', 'binary', 'multiclass'

    Returns:
        float: Aligned probability for last prediction
        None: If regression task or no probabilities available

    Examples:
        >>> # Binary: return P(positive class)
        >>> extract_aligned_probability(np.array([[0.3, 0.7]]), 'binary')
        0.7

        >>> # Multiclass: return max probability
        >>> extract_aligned_probability(np.array([[0.1, 0.6, 0.3]]), 'multiclass')
        0.6

        >>> # Regression: no probability
        >>> extract_aligned_probability(None, 'regression')
        None
    """
    if y_prob is None:
        return None

    if task_type == "regression":
        return None

    # Get last row (aligned prediction)
    last_prob = y_prob[-1]

    # Handle 1D case (already scalar or 1D array)
    if np.ndim(last_prob) == 0:
        return float(last_prob)

    # Handle 2D case: [n_classes]
    if len(last_prob) == 2:
        # Binary classification: return P(positive class = class 1)
        return float(last_prob[1])

    # Multiclass: return maximum probability
    return float(np.max(last_prob))


# =============================================================================
# CONFIGURATION
# =============================================================================
class RunMode(Enum):
    """Pipeline execution modes."""

    BACKTEST = "backtest"  # Full walk-forward backtest
    VALIDATION = "validation"  # Single train/val split
    LIVE = "live"  # Production mode (no labels)


@dataclass
class PipelineConfig:
    """
    Configuration for the pipeline orchestrator.

    Controls which targets/horizons to run and how.
    """

    # Target selection (default: all 20)
    targets: tuple[str, ...] = ALL_TARGETS
    horizons: tuple[int, ...] = ALL_HORIZONS

    # Execution mode
    mode: RunMode = RunMode.BACKTEST

    # Walk-forward settings
    step_size: int = 1
    min_train_size: int = 500
    backtest_rows: int = 500  # Number of walk-forward iterations

    # Layer 1 (helpers) config
    l1_train_size: int = 800
    l1_cal_size: int = 100
    l1_val_size: int = 100

    # Layer 2 (supervised) config
    l2_train_size: int = 500
    l2_cal_size: int = 100
    l2_val_size: int = 100

    # Position sizing
    position_sizing_enabled: bool = True
    prob_threshold: float = 0.52
    max_position: float = 2.0

    # Output
    save_predictions: bool = True
    output_dir: Path = field(default_factory=lambda: Path("data/pipeline_results"))

    # Parallel execution
    n_jobs: int = 1  # -1 for all cores

    def __post_init__(self):
        """Ensure output directory exists."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @property
    def n_targets(self) -> int:
        return len(self.targets) * len(self.horizons)

    def get_target_specs(self) -> list[TargetSpec]:
        """Get all TargetSpec objects for configured targets."""
        specs = []
        for target in self.targets:
            for horizon in self.horizons:
                specs.append(get_target_spec(target, horizon))
        return specs

    def get_dual_config(self, target: str, horizon: int) -> DualLayerConfig:
        """Create DualLayerConfig for a specific target-horizon."""
        return create_dual_config(
            target_name=target,
            horizon=horizon,
            l1_train=self.l1_train_size,
            l1_cal=self.l1_cal_size,
            l1_val=self.l1_val_size,
            l2_train=self.l2_train_size,
            l2_cal=self.l2_cal_size,
            l2_val=self.l2_val_size,
            backtest_rows=self.backtest_rows,
        )


# =============================================================================
# PREDICTION CONTAINERS
# =============================================================================
@dataclass
class TargetPrediction:
    """
    Prediction result for a single target-horizon.

    For horizon alignment, each model predicts `horizon` rows.
    The LAST prediction is the aligned one (all horizons target same bar).

    Example for horizon=3:
        y_pred = [pred_t-2, pred_t-1, pred_t]  # 3 predictions
        aligned_pred = pred_t  # Last one, targets t+3

    For horizon=1:
        y_pred = [pred_t]  # 1 prediction
        aligned_pred = pred_t  # Targets t+1

    Conformal prediction fields (added Phase 8):
        - prediction_set: Valid classes for classification (may have multiple)
        - prediction_interval: (lower, upper) bounds for regression
        - uncertainty: Set size (cls) or interval width (reg)
        - current_alpha: Adapted miscoverage rate from ACI
    """

    target: str
    horizon: int
    task_type: str

    # Predictions (array of size=horizon for alignment)
    y_pred: np.ndarray  # All predictions [horizon]
    y_prob: np.ndarray | None  # Probabilities [horizon] (classification)
    y_true: np.ndarray | None  # Ground truth [horizon] (if available)

    # Conformal prediction outputs (for aligned/last prediction)
    prediction_set: np.ndarray | None = (
        None  # [n_classes] boolean mask (classification)
    )
    prediction_interval: tuple[float, float] | None = (
        None  # (lower, upper) (regression)
    )
    uncertainty: float | None = None  # Set size or interval width
    current_alpha: float | None = None  # Current ACI-adapted miscoverage rate

    # Metadata
    timestamps: np.ndarray | None = None
    iteration: int = 0

    @property
    def identifier(self) -> str:
        return f"{self.target}_{self.horizon}bar"

    @property
    def aligned_pred(self) -> float:
        """Get the aligned prediction (last one, targets same bar as all horizons)."""
        return float(self.y_pred[-1])

    @property
    def aligned_prob(self) -> float | None:
        """Get the aligned probability (last one, for classification tasks).

        For binary classification, returns P(positive class).
        For multiclass, returns the maximum class probability.
        For regression, returns None.
        """
        return extract_aligned_probability(self.y_prob, self.task_type)

    @property
    def aligned_true(self) -> float | None:
        """Get the aligned ground truth (last one)."""
        if self.y_true is None:
            return None
        return float(self.y_true[-1])

    @property
    def conformal_set_size(self) -> int | None:
        """Get number of classes in prediction set (classification only)."""
        if self.prediction_set is None:
            return None
        return int(np.sum(self.prediction_set))

    @property
    def conformal_interval_width(self) -> float | None:
        """Get width of prediction interval (regression only)."""
        if self.prediction_interval is None:
            return None
        return self.prediction_interval[1] - self.prediction_interval[0]

    @property
    def has_conformal(self) -> bool:
        """Check if conformal prediction was applied."""
        return self.prediction_set is not None or self.prediction_interval is not None


@dataclass
class EnsemblePrediction:
    """Combined predictions from all targets for a single timestep."""

    timestamp: int  # Index in data

    # Direction predictions
    direction_probs: dict[int, float] = field(default_factory=dict)  # horizon → P(up)

    # Returns predictions
    returns_pred: dict[int, float] = field(default_factory=dict)  # horizon → E[return]

    # Volatility predictions
    volatility_pred: dict[int, float] = field(default_factory=dict)  # horizon → E[vol]

    # Regime predictions
    vol_spike: dict[int, int] = field(
        default_factory=dict
    )  # horizon → 0/1 (NO_SPIKE/SPIKE)
    trend_regime: dict[int, int] = field(default_factory=dict)  # horizon → 0/1

    def get_direction_consensus(self) -> float:
        """Average P(up) across horizons."""
        if not self.direction_probs:
            return 0.5
        return np.mean(list(self.direction_probs.values()))

    def get_volatility_consensus(self) -> float:
        """Average volatility across horizons."""
        if not self.volatility_pred:
            return 0.0
        return np.mean(list(self.volatility_pred.values()))

    def is_vol_spike(self) -> bool:
        """Check if majority of vol_spike predictions are SPIKE (1)."""
        if not self.vol_spike:
            return False
        return np.mean([v == 1 for v in self.vol_spike.values()]) > 0.5


@dataclass
class PositionSizingResult:
    """Final position sizing output."""

    timestamp: int

    # Input signals
    direction_prob: float
    expected_return: float
    expected_volatility: float

    # Position sizing components
    gate_passed: bool
    ratio_factor: float
    alignment_factor: float
    vol_factor: float

    # Output
    raw_position: float
    final_position: float  # After clipping to [0, max_position]

    # Direction
    direction: Literal["long", "short", "flat"]


# =============================================================================
# TARGET RUNNER (Single Target-Horizon)
# =============================================================================
class TargetRunner:
    """
    Runs the dual-layer pipeline for a single target-horizon.

    Each TargetRunner is COMPLETELY ISOLATED:
    - Loads its own data (X, y specific to this target-horizon)
    - Trains its own helper ensemble (optimized for this target)
    - Runs its own supervised models
    - Produces predictions for this target only

    Manages:
    - Data loading (target-specific y)
    - Layer 1 helper fitting and optimization (using y for IC-based tuning)
    - Layer 2 supervised fitting and prediction
    - Conformal prediction (uncertainty quantification)
    - Result collection

    Conformal Prediction (Phase 8):
    - ConformalClassifier with LAC for classification tasks
    - ConformalRegressor with EnbPI for regression tasks
    - ACI (Adaptive Conformal Inference) for dynamic alpha adjustment
    """

    def __init__(
        self,
        spec: TargetSpec,
        config: PipelineConfig,
        layer2_models: dict[str, Any] | None = None,
        conformal_config: ConformalConfig | None = None,
    ):
        self.spec = spec
        self.config = config
        self.layer2_models = layer2_models or {}

        # Conformal prediction configuration
        self.conformal_config = conformal_config or ConformalConfig()

        # Data (target-specific)
        self.X: pd.DataFrame | None = None
        self.y: pd.Series | None = None

        # Helper ensemble (target-specific, re-created each iteration)
        self.helper_ensemble: Any = None  # Will be HelperEnsemble

        # Conformal wrapper (re-calibrated each iteration, holds no persistent state)
        self._conformal_wrapper: ConformalClassifier | ConformalRegressor | None = None

        # ACI state (persistent across iterations for adaptive alpha)
        self.aci: AdaptiveConformalInference | None = None
        if self.conformal_config.enabled and self.conformal_config.aci_enabled:
            self.aci = AdaptiveConformalInference(
                alpha_target=self.conformal_config.alpha,
                gamma=self.conformal_config.aci_gamma,
                alpha_min=self.conformal_config.aci_alpha_min,
                alpha_max=self.conformal_config.aci_alpha_max,
            )

        # Engine
        self.engine: DualLayerEngine | None = None

        # Results
        self.predictions: list[TargetPrediction] = []
        self.helper_metrics: list[dict] = []
        self.conformal_metrics: list[dict] = []  # Track coverage per iteration

    def load_data(self, verbose: bool = True) -> tuple[pd.DataFrame, pd.Series]:
        """Load data for this target-horizon.

        Each target has its own y column computed from the same base features.
        """
        self.X, self.y, _ = load_target_data(
            self.spec.target,
            self.spec.horizon,
            drop_na=True,
            verbose=verbose,
        )
        if verbose:
            print(f"  {self.spec.identifier}: Loaded {len(self.X)} samples")
        return self.X, self.y

    def setup_engine(self) -> DualLayerEngine:
        """Create the dual-layer walk-forward engine."""
        if self.X is None:
            self.load_data(verbose=False)

        dual_config = self.config.get_dual_config(
            self.spec.target,
            self.spec.horizon,
        )

        self.engine = DualLayerEngine(self.X, self.y, dual_config)
        return self.engine

    def _fit_helpers(self, window: "DualLayerWindow") -> pd.DataFrame:
        """
        Fit helper ensemble on Layer 1 data and generate features for Layer 2.

        This is the key target-awareness step:
        1. Fit helpers on L1 train (unsupervised)
        2. Optimize helpers on L1 cal using TARGET y (target-aware IC optimization)
        3. Validate on L1 val
        4. Generate helper features for L2 data

        Returns:
            DataFrame with helper features for Layer 2 train+cal+val+pred
        """
        from scripts.target_models.helpers import create_helper_ensemble

        # Create fresh ensemble for this iteration (target-specific)
        self.helper_ensemble = create_helper_ensemble(
            target=self.spec.target,
            horizon=self.spec.horizon,
            random_state=self.config.get_random_state(window.iteration)
            if hasattr(self.config, "get_random_state")
            else 42 + window.iteration,
        )

        # Get Layer 1 data slices
        # L1 has train + val only (no separate cal, val used for optimization)
        l1 = window.l1
        X_l1_train = self.X.iloc[l1.train.start_idx : l1.train.end_idx]
        X_l1_val = self.X.iloc[l1.val.start_idx : l1.val.end_idx]

        # Get corresponding y values for optimization/validation (same split)
        y_l1_val = self.y.iloc[l1.val.start_idx : l1.val.end_idx]

        # 1. Fit on L1 train (unsupervised)
        self.helper_ensemble.fit(X_l1_train)

        # 2. Optimize on L1 val using TARGET y (target-aware!)
        # Note: L1 uses val for both optimization and validation (no separate cal)
        opt_results = self.helper_ensemble.optimize(X_l1_val, y_l1_val)

        # 3. Validate on L1 val (same as optimize for L1)
        val_results = self.helper_ensemble.validate(X_l1_val, y_l1_val)

        # Store metrics for analysis
        self.helper_metrics.append(
            {
                "iteration": window.iteration,
                "optimize": opt_results,
                "validate": val_results,
            }
        )

        # 4. Generate features for entire Layer 2 range
        l2 = window.l2
        l2_start = l2.train.start_idx
        l2_end = l2.pred.end_idx  # Include prediction row
        X_l2_full = self.X.iloc[l2_start:l2_end]

        helper_output = self.helper_ensemble.transform(X_l2_full)
        return helper_output.features

    def _apply_conformal_prediction(
        self,
        model_ensemble: Any,
        X_cal: pd.DataFrame,
        y_cal: pd.Series,
        X_pred: pd.DataFrame,
        y_true_aligned: float | None,
    ) -> tuple[np.ndarray | None, tuple[float, float] | None, float | None, float]:
        """
        Apply conformal prediction after isotonic calibration.

        Args:
            model_ensemble: Fitted and calibrated ModelEnsemble
            X_cal: Calibration features
            y_cal: Calibration targets
            X_pred: Prediction features
            y_true_aligned: Aligned ground truth for ACI update

        Returns:
            Tuple of (prediction_set, prediction_interval, uncertainty, current_alpha)
        """
        if not self.conformal_config.enabled:
            return None, None, None, self.conformal_config.alpha

        # Get current alpha (from ACI if enabled, otherwise fixed)
        current_alpha = self.aci.alpha if self.aci else self.conformal_config.alpha

        prediction_set = None
        prediction_interval = None
        uncertainty = None

        try:
            if self.spec.task_type != "regression":
                # Classification: Use LAC method
                conf_wrapper = ConformalClassifier(
                    model_ensemble, self.conformal_config
                )
                conf_wrapper.calibrate(X_cal.values, y_cal.values)

                # Get prediction sets for all predictions, extract aligned (last) one
                sets = conf_wrapper.predict_with_sets(
                    X_pred.values, alpha=current_alpha
                )
                prediction_set = sets[-1]  # Aligned (last) prediction
                uncertainty = float(np.sum(prediction_set))

            else:
                # Regression: Use EnbPI method
                conf_wrapper = ConformalRegressor(model_ensemble, self.conformal_config)
                conf_wrapper.calibrate(X_cal.values, y_cal.values)

                # Get intervals for all predictions, extract aligned (last)
                intervals = conf_wrapper.predict_with_intervals(
                    X_pred.values, alpha=current_alpha
                )
                lower, upper = intervals[-1]  # Aligned (last) prediction
                prediction_interval = (float(lower), float(upper))
                uncertainty = float(upper - lower)

            # Update ACI state if we have ground truth (for next iteration's alpha)
            if self.aci and y_true_aligned is not None:
                if self.spec.task_type != "regression":
                    # Classification: check if true label is in prediction set
                    covered = bool(prediction_set[int(y_true_aligned)])
                else:
                    # Regression: check if true value is in interval
                    covered = (
                        prediction_interval[0]
                        <= y_true_aligned
                        <= prediction_interval[1]
                    )

                # Update ACI with batch error rate (single prediction = 0 or 1)
                error_rate = 0.0 if covered else 1.0
                self.aci.update_batch(error_rate)

                # Track conformal metrics
                self.conformal_metrics.append(
                    {
                        "iteration": len(self.conformal_metrics),
                        "covered": covered,
                        "alpha": current_alpha,
                        "uncertainty": uncertainty,
                    }
                )

        except Exception as e:
            # Log but don't fail - conformal is enhancement, not critical
            import warnings

            warnings.warn(
                f"Conformal prediction failed for {self.spec.identifier}: {e}",
                stacklevel=2,
            )

        return prediction_set, prediction_interval, uncertainty, current_alpha

    def run_iteration(self, window: "DualLayerWindow") -> TargetPrediction:
        """
        Run one walk-forward iteration with full dual-layer pipeline.

        Flow:
        1. Fit helpers on Layer 1 → get helper features (58 features)
        2. Layer 2 uses ONLY helper features (not base features)
        3. Train supervised model ensemble on helper features
        4. Calibrate on L2 cal (isotonic for classification)
        5. Apply conformal prediction for uncertainty quantification
        6. Predict on L2 pred

        Architecture:
            Layer 1: base features (166) → helpers → helper features (58)
            Layer 2: helper features (58) → CatBoost/LightGBM/Ridge → prediction
            Conformal: calibrated ensemble → MAPIE → prediction sets/intervals
        """
        from scripts.target_models.models import create_model_ensemble

        # Step 1: Fit helpers and get features
        helper_features = self._fit_helpers(window)

        # Step 2: Layer 2 uses ONLY helper features (not original base features)
        # This ensures clean separation: L1 learns representations, L2 learns to predict
        X_l2 = helper_features.reset_index(drop=True)

        # Get y for Layer 2
        l2 = window.l2
        l2_start = l2.train.start_idx
        l2_end = l2.pred.end_idx
        y_l2 = self.y.iloc[l2_start:l2_end].reset_index(drop=True)

        # Compute local indices within L2
        train_len = l2.train.end_idx - l2.train.start_idx
        cal_start = train_len + (l2.cal.start_idx - l2.train.end_idx)
        cal_len = l2.cal.end_idx - l2.cal.start_idx
        val_start = cal_start + cal_len + (l2.val.start_idx - l2.cal.end_idx)
        val_len = l2.val.end_idx - l2.val.start_idx
        pred_start = val_start + val_len + (l2.pred.start_idx - l2.val.end_idx)

        # Split helper features for L2 windows
        X_train = X_l2.iloc[:train_len]
        y_train = y_l2.iloc[:train_len]
        X_cal = X_l2.iloc[cal_start : cal_start + cal_len]
        y_cal = y_l2.iloc[cal_start : cal_start + cal_len]
        X_val = X_l2.iloc[val_start : val_start + val_len]
        y_val = y_l2.iloc[val_start : val_start + val_len]
        # Predict `horizon` rows for alignment (last pred targets same bar)
        X_pred = X_l2.iloc[pred_start : pred_start + self.spec.horizon]

        # ──────────────────────────────────────────────────────────────────
        # Tier 1.1: Class balance validation (prevents single-class failures)
        # ──────────────────────────────────────────────────────────────────
        if self.spec.task_type != "regression":
            is_valid, msg, metrics = validate_class_balance(
                y_train.values,
                min_samples_per_class=30,
                min_balance_score=0.5,
            )
            if not is_valid:
                import warnings

                warnings.warn(
                    f"Iteration {window.iteration}: Class imbalance - {msg}. "
                    f"Skipping training, returning NaN prediction.",
                    stacklevel=2,
                )
                # Return NaN prediction for this iteration
                return TargetPrediction(
                    target=self.spec.target,
                    horizon=self.spec.horizon,
                    task_type=self.spec.task_type,
                    y_pred=np.array([np.nan] * self.spec.horizon),
                    y_prob=None,
                    y_true=self.y.iloc[
                        window.l2.pred.start_idx : window.l2.pred.start_idx
                        + self.spec.horizon
                    ].values
                    if self.y is not None
                    else None,
                    prediction_set=None,
                    prediction_interval=None,
                    uncertainty=None,
                    current_alpha=self.conformal_config.alpha,
                    iteration=window.iteration,
                )

        # Step 3: Create and fit Layer 2 model ensemble
        model_ensemble = create_model_ensemble(
            target=self.spec.target,
            horizon=self.spec.horizon,
            task_type=self.spec.task_type,
            n_classes=self.spec.n_classes,
            random_state=42 + window.iteration,
        )

        # Fit with validation set for early stopping
        model_ensemble.fit(X_train, y_train, X_val=X_val, y_val=y_val)

        # Step 4: Calibrate on L2 cal (isotonic for classification)
        if self.spec.task_type != "regression":
            model_ensemble.calibrate(X_cal, y_cal, method="isotonic")

        # Step 5: Predict on L2 pred (point predictions)
        output = model_ensemble.predict(X_pred)

        # Get ground truth for all horizon predictions
        pred_idx = window.l2.pred.start_idx
        y_true = (
            self.y.iloc[pred_idx : pred_idx + self.spec.horizon].values
            if self.y is not None
            else None
        )

        # Get aligned ground truth for ACI update
        y_true_aligned = float(y_true[-1]) if y_true is not None else None

        # Step 6: Apply conformal prediction for uncertainty quantification
        prediction_set, prediction_interval, uncertainty, current_alpha = (
            self._apply_conformal_prediction(
                model_ensemble, X_cal, y_cal, X_pred, y_true_aligned
            )
        )

        # Use calibrated probabilities if available
        y_prob = (
            output.y_prob_calibrated
            if output.y_prob_calibrated is not None
            else output.y_prob
        )

        return TargetPrediction(
            target=self.spec.target,
            horizon=self.spec.horizon,
            task_type=self.spec.task_type,
            y_pred=output.y_pred,
            y_prob=y_prob,
            y_true=y_true,
            prediction_set=prediction_set,
            prediction_interval=prediction_interval,
            uncertainty=uncertainty,
            current_alpha=current_alpha,
            iteration=window.iteration,
        )

    def run(
        self, max_iterations: int | None = None, verbose: bool = True
    ) -> list[TargetPrediction]:
        """
        Run the full walk-forward for this target-horizon.

        Args:
            max_iterations: Limit iterations (for testing)
            verbose: Print progress


        Returns:
            List of predictions for each iteration
        """
        if self.engine is None:
            self.setup_engine()

        self.predictions = []
        self.helper_metrics = []
        self.conformal_metrics = []  # Reset conformal tracking

        if verbose:
            print(f"\n=== {self.spec.identifier} ===")
            print(f"  Task type: {self.spec.task_type}")
            print(f"  Total iterations: {self.engine.n_iterations}")
            if self.conformal_config.enabled:
                aci_status = "ACI" if self.conformal_config.aci_enabled else "fixed"
                print(f"  Conformal: enabled ({aci_status})")

        for i, window in enumerate(self.engine.iterate()):
            if max_iterations and i >= max_iterations:
                break

            pred = self.run_iteration(window)
            self.predictions.append(pred)

            if verbose and i % 500 == 0:
                # Show helper IC from last iteration
                if self.helper_metrics:
                    last_opt = self.helper_metrics[-1].get("optimize", {})
                    mean_ic = last_opt.get("mean_abs_ic", "N/A")
                    print(
                        f"  Iteration {i}/{self.engine.n_iterations}, "
                        f"helper mean|IC|: {mean_ic:.4f}"
                        if isinstance(mean_ic, float)
                        else f"  Iteration {i}/{self.engine.n_iterations}"
                    )

        if verbose:
            print(f"  Completed {len(self.predictions)} iterations")

            # Show conformal coverage summary
            if self.conformal_config.enabled and self.conformal_metrics:
                summary = self.get_conformal_summary()
                coverage = summary.get("coverage")
                target = summary.get("target_coverage")
                if coverage is not None:
                    status = "✓" if abs(coverage - target) < 0.05 else "⚠"
                    print(f"  Coverage: {coverage:.1%} (target: {target:.0%}) {status}")

        return self.predictions

    def get_helper_summary(self) -> dict:
        """Get summary of helper performance across iterations."""
        if not self.helper_metrics:
            return {}

        cal_ics = []
        val_ics = []

        for m in self.helper_metrics:
            opt = m.get("optimize", {})
            val = m.get("validate", {})

            # Get aggregate IC from ensemble (not per-helper)
            if "mean_abs_ic" in opt:
                cal_ics.append(opt["mean_abs_ic"])
            if "mean_abs_ic" in val:
                val_ics.append(val["mean_abs_ic"])

        return {
            "target": self.spec.target,
            "horizon": self.spec.horizon,
            "n_iterations": len(self.helper_metrics),
            "mean_cal_ic": float(np.mean(cal_ics)) if cal_ics else None,
            "mean_val_ic": float(np.mean(val_ics)) if val_ics else None,
            "ic_stability": float(np.std(cal_ics)) if len(cal_ics) > 1 else None,
        }

    def get_conformal_summary(self) -> dict:
        """Get summary of conformal prediction coverage across iterations."""
        if not self.conformal_metrics:
            return {
                "target": self.spec.target,
                "horizon": self.spec.horizon,
                "enabled": self.conformal_config.enabled,
                "n_iterations": 0,
            }

        covered = [m["covered"] for m in self.conformal_metrics]
        alphas = [m["alpha"] for m in self.conformal_metrics]
        uncertainties = [
            m["uncertainty"]
            for m in self.conformal_metrics
            if m["uncertainty"] is not None
        ]

        return {
            "target": self.spec.target,
            "horizon": self.spec.horizon,
            "task_type": self.spec.task_type,
            "enabled": self.conformal_config.enabled,
            "aci_enabled": self.conformal_config.aci_enabled,
            "n_iterations": len(self.conformal_metrics),
            "coverage": float(np.mean(covered)) if covered else None,
            "target_coverage": 1.0 - self.conformal_config.alpha,
            "coverage_gap": float(
                np.mean(covered) - (1.0 - self.conformal_config.alpha)
            )
            if covered
            else None,
            "mean_alpha": float(np.mean(alphas)) if alphas else None,
            "alpha_std": float(np.std(alphas)) if len(alphas) > 1 else None,
            "mean_uncertainty": float(np.mean(uncertainties))
            if uncertainties
            else None,
            "uncertainty_std": float(np.std(uncertainties))
            if len(uncertainties) > 1
            else None,
        }


# =============================================================================
# ENSEMBLE AGGREGATOR
# =============================================================================
class EnsembleAggregator:
    """
    Combines predictions from all 20 target-horizons.

    Takes TargetPredictions and produces EnsemblePredictions.
    """

    def __init__(self, config: PipelineConfig):
        self.config = config
        self.target_predictions: dict[str, list[TargetPrediction]] = {}

    def add_target_predictions(
        self,
        spec: TargetSpec,
        predictions: list[TargetPrediction],
    ):
        """Add predictions from a target-horizon."""
        self.target_predictions[spec.identifier] = predictions

    def aggregate_for_timestamp(self, iteration: int) -> EnsemblePrediction:
        """
        Aggregate all target predictions for a single iteration.

        Uses ALIGNED predictions (last one from each horizon) so all
        horizons target the same future bar.

        Example at iteration t:
            h=1:  pred[0] targets t+1
            h=3:  pred[2] (last of 3) targets t+1
            h=6:  pred[5] (last of 6) targets t+1
            h=12: pred[11] (last of 12) targets t+1

        All combined into single EnsemblePrediction for t+1.

        Returns EnsemblePrediction combining all aligned signals.
        """
        ensemble = EnsemblePrediction(timestamp=iteration)

        for _identifier, preds in self.target_predictions.items():
            if iteration >= len(preds):
                continue

            pred = preds[iteration]
            horizon = pred.horizon

            # Use ALIGNED predictions (last one targets same bar as all horizons)
            if pred.target == "direction" and pred.y_prob is not None:
                ensemble.direction_probs[horizon] = pred.aligned_prob

            elif pred.target == "returns":
                ensemble.returns_pred[horizon] = pred.aligned_pred

            elif pred.target == "volatility":
                ensemble.volatility_pred[horizon] = pred.aligned_pred

            elif pred.target == "vol_spike":
                ensemble.vol_spike[horizon] = int(pred.aligned_pred)

            elif pred.target == "trend_regime":
                ensemble.trend_regime[horizon] = int(pred.aligned_pred)

        return ensemble

    def aggregate_all(self) -> list[EnsemblePrediction]:
        """Aggregate predictions for all iterations."""
        # Find max iterations across all targets
        max_iters = (
            max(len(preds) for preds in self.target_predictions.values())
            if self.target_predictions
            else 0
        )

        return [self.aggregate_for_timestamp(i) for i in range(max_iters)]


# =============================================================================
# POSITION SIZING LAYER
# =============================================================================
class PositionSizer:
    """
    Position sizing V3 implementation.

    Converts ensemble predictions into final positions.

    Key features:
    - Gate check: Skip if direction probability below threshold
    - Rolling EMA ratio: Track TP/FP for position scaling
    - Config alignment: Scale by multi-horizon agreement
    - Volatility adjustment: Reduce size in high-vol regimes
    """

    def __init__(self, config: PipelineConfig):
        self.config = config

        # Rolling state for ratio calculation
        self.tp_count: int = 0
        self.fp_count: int = 0
        self.ema_ratio: float = 1.0
        self.ema_alpha: float = 0.1  # EMA decay rate

        # Historical results for TP/FP tracking
        self._history: list[dict] = []

    def update_from_outcome(
        self,
        predicted_direction: Literal["long", "short", "flat"],
        actual_return: float,
    ) -> None:
        """
        Update TP/FP counts from realized outcome.

        Call this AFTER you know the actual return for a prediction.

        Args:
            predicted_direction: What we predicted ("long", "short", "flat")
            actual_return: Actual realized return (positive = up, negative = down)
        """
        if predicted_direction == "flat":
            return  # No position, no update

        # Determine if prediction was correct
        is_correct = (predicted_direction == "long" and actual_return > 0) or (
            predicted_direction == "short" and actual_return < 0
        )

        # Update counts
        if is_correct:
            self.tp_count += 1
        else:
            self.fp_count += 1

        # Update EMA ratio
        total = self.tp_count + self.fp_count
        if total > 10:  # Need minimum history before updating ratio
            current_ratio = self.tp_count / total if total > 0 else 0.5
            self.ema_ratio = (
                self.ema_alpha * current_ratio + (1 - self.ema_alpha) * self.ema_ratio
            )

        # Store in history
        self._history.append(
            {
                "predicted_direction": predicted_direction,
                "actual_return": actual_return,
                "is_correct": is_correct,
                "ema_ratio": self.ema_ratio,
            }
        )

    def compute_alignment_factor(self, ensemble: EnsemblePrediction) -> float:
        """
        Compute alignment factor based on multi-horizon agreement.

        Checks if all 4 horizons agree on direction.
        Higher agreement = higher alignment factor.

        Returns:
            float in [0.5, 1.0] where 1.0 = perfect agreement
        """
        if not ensemble.direction_probs:
            return 0.5

        # Get direction consensus per horizon
        directions = []
        for _h, prob in ensemble.direction_probs.items():
            if prob > 0.55:
                directions.append("long")
            elif prob < 0.45:
                directions.append("short")
            else:
                directions.append("neutral")

        # Count agreements
        n_horizons = len(directions)
        if n_horizons == 0:
            return 0.5

        # Most common direction
        from collections import Counter

        counts = Counter(directions)
        most_common, count = counts.most_common(1)[0]

        # Alignment = fraction that agree with most common
        agreement = count / n_horizons

        # Scale to [0.5, 1.0]
        return 0.5 + 0.5 * agreement

    def compute_position(self, ensemble: EnsemblePrediction) -> PositionSizingResult:
        """
        Compute final position from ensemble predictions.

        Implements V3 pipeline:
        1. Gate check
        2. Rolling EMA ratio
        3. Config alignment
        4. Volatility adjustment
        5. Final position
        """
        direction_prob = ensemble.get_direction_consensus()
        expected_vol = ensemble.get_volatility_consensus()
        expected_return = (
            np.mean(list(ensemble.returns_pred.values()))
            if ensemble.returns_pred
            else 0.0
        )

        # Step 1: Gate check
        gate_passed = direction_prob >= self.config.prob_threshold

        if not gate_passed:
            return PositionSizingResult(
                timestamp=ensemble.timestamp,
                direction_prob=direction_prob,
                expected_return=expected_return,
                expected_volatility=expected_vol,
                gate_passed=False,
                ratio_factor=0.0,
                alignment_factor=0.0,
                vol_factor=0.0,
                raw_position=0.0,
                final_position=0.0,
                direction="flat",
            )

        # Step 2: Rolling EMA ratio (now properly tracked via update_from_outcome)
        # Caps at 1.2x to prevent over-leverage during lucky streaks
        ratio_factor = min(1.2, self.ema_ratio)

        # Step 3: Config alignment - now uses multi-horizon agreement
        alignment_factor = self.compute_alignment_factor(ensemble)

        # Step 4: Volatility adjustment - reduce position if spike predicted
        vol_factor = 0.7 if ensemble.is_vol_spike() else 1.0

        # Step 5: Base position and final
        base_position = 1.0  # Start with base position
        raw_position = base_position * ratio_factor * alignment_factor * vol_factor

        # Clip to [0, max_position]
        final_position = np.clip(raw_position, 0.0, self.config.max_position)

        # Determine direction
        direction: Literal["long", "short", "flat"]
        if final_position == 0:
            direction = "flat"
        elif direction_prob > 0.5:
            direction = "long"
        else:
            direction = "short"

        return PositionSizingResult(
            timestamp=ensemble.timestamp,
            direction_prob=direction_prob,
            expected_return=expected_return,
            expected_volatility=expected_vol,
            gate_passed=True,
            ratio_factor=ratio_factor,
            alignment_factor=alignment_factor,
            vol_factor=vol_factor,
            raw_position=raw_position,
            final_position=final_position,
            direction=direction,
        )

    def size_all(
        self, ensembles: list[EnsemblePrediction]
    ) -> list[PositionSizingResult]:
        """Compute positions for all ensemble predictions."""
        return [self.compute_position(e) for e in ensembles]

    def get_stats(self) -> dict:
        """Get position sizer statistics."""
        total = self.tp_count + self.fp_count
        win_rate = self.tp_count / total if total > 0 else 0.5
        return {
            "tp_count": self.tp_count,
            "fp_count": self.fp_count,
            "total_trades": total,
            "win_rate": win_rate,
            "ema_ratio": self.ema_ratio,
            "history_length": len(self._history),
        }


# =============================================================================
# MAIN ORCHESTRATOR
# =============================================================================
class PipelineOrchestrator:
    """
    Main orchestrator that coordinates the entire pipeline.

    Manages:
    - All 20 target-horizon runners
    - Ensemble aggregation
    - Position sizing
    - Result persistence
    """

    def __init__(self, config: PipelineConfig | None = None):
        self.config = config or PipelineConfig()

        # Components
        self.target_runners: dict[str, TargetRunner] = {}
        self.aggregator: EnsembleAggregator | None = None
        self.position_sizer: PositionSizer | None = None

        # Results
        self.ensemble_predictions: list[EnsemblePrediction] = []
        self.position_results: list[PositionSizingResult] = []

        self._setup_runners()

    def _setup_runners(self):
        """Create TargetRunner for each target-horizon."""
        for spec in self.config.get_target_specs():
            runner = TargetRunner(spec, self.config)
            self.target_runners[spec.identifier] = runner

    def load_all_data(
        self, verbose: bool = True
    ) -> dict[str, tuple[pd.DataFrame, pd.Series]]:
        """Load data for all targets."""
        data = {}

        if verbose:
            print(f"Loading data for {len(self.target_runners)} target-horizons...")

        for identifier, runner in self.target_runners.items():
            X, y = runner.load_data(verbose=False)
            data[identifier] = (X, y)

            if verbose:
                print(f"  {identifier}: {X.shape}")

        return data

    def run_all_targets(
        self,
        max_iterations: int | None = None,
        verbose: bool = True,
    ) -> dict[str, list[TargetPrediction]]:
        """
        Run all target-horizon pipelines.

        Returns dict mapping identifier → predictions.
        """
        results = {}

        if verbose:
            print(f"Running {len(self.target_runners)} target-horizons...")

        for identifier, runner in self.target_runners.items():
            if verbose:
                print(f"\n{identifier}:")

            predictions = runner.run(
                max_iterations=max_iterations,
                verbose=verbose,
            )
            results[identifier] = predictions

        return results

    def aggregate_predictions(
        self,
        target_predictions: dict[str, list[TargetPrediction]],
    ) -> list[EnsemblePrediction]:
        """Aggregate all target predictions into ensemble predictions."""
        self.aggregator = EnsembleAggregator(self.config)

        for identifier, predictions in target_predictions.items():
            spec = get_target_spec(
                identifier.rsplit("_", 1)[0].replace("_regime", "_regime"),
                int(identifier.split("_")[-1].replace("bar", "")),
            )
            self.aggregator.add_target_predictions(spec, predictions)

        self.ensemble_predictions = self.aggregator.aggregate_all()
        return self.ensemble_predictions

    def compute_positions(
        self,
        ensemble_predictions: list[EnsemblePrediction] | None = None,
    ) -> list[PositionSizingResult]:
        """Compute final positions from ensemble predictions."""
        if ensemble_predictions is None:
            ensemble_predictions = self.ensemble_predictions

        self.position_sizer = PositionSizer(self.config)
        self.position_results = self.position_sizer.size_all(ensemble_predictions)

        return self.position_results

    def run(
        self,
        max_iterations: int | None = None,
        verbose: bool = True,
    ) -> list[PositionSizingResult]:
        """
        Run the complete pipeline.

        1. Load all data
        2. Run all target-horizon models
        3. Aggregate predictions
        4. Compute positions

        Returns final position sizing results.
        """
        if verbose:
            print("=" * 60)
            print("PIPELINE ORCHESTRATOR")
            print("=" * 60)
            print(f"Targets: {self.config.targets}")
            print(f"Horizons: {self.config.horizons}")
            print(f"Total combinations: {self.config.n_targets}")
            print()

        # Step 1: Load data
        self.load_all_data(verbose=verbose)

        # Step 2: Run all targets
        target_predictions = self.run_all_targets(
            max_iterations=max_iterations,
            verbose=verbose,
        )

        # Step 3: Aggregate
        if verbose:
            print("\nAggregating predictions...")
        self.aggregate_predictions(target_predictions)

        # Step 4: Position sizing
        if self.config.position_sizing_enabled:
            if verbose:
                print("Computing positions...")
            self.compute_positions()

        if verbose:
            print("\nPipeline complete!")
            print(f"  Ensemble predictions: {len(self.ensemble_predictions)}")
            print(f"  Position results: {len(self.position_results)}")

        return self.position_results

    def get_results_dataframe(self) -> pd.DataFrame:
        """Convert position results to DataFrame."""
        if not self.position_results:
            return pd.DataFrame()

        return pd.DataFrame(
            [
                {
                    "timestamp": r.timestamp,
                    "direction_prob": r.direction_prob,
                    "expected_return": r.expected_return,
                    "expected_volatility": r.expected_volatility,
                    "gate_passed": r.gate_passed,
                    "ratio_factor": r.ratio_factor,
                    "alignment_factor": r.alignment_factor,
                    "vol_factor": r.vol_factor,
                    "raw_position": r.raw_position,
                    "final_position": r.final_position,
                    "direction": r.direction,
                }
                for r in self.position_results
            ]
        )

    def save_results(self, path: Path | None = None):
        """Save results to disk."""
        path = path or self.config.output_dir / "pipeline_results.parquet"
        df = self.get_results_dataframe()
        df.to_parquet(path)
        return path

    def run_synchronized(
        self,
        max_iterations: int | None = None,
        verbose: bool = True,
    ) -> list[PositionSizingResult]:
        """
        Run all 20 models in SYNCHRONIZED step-by-step mode.

        Key difference from run():
        - run(): Each target runs ALL iterations, then next target
        - run_synchronized(): All targets advance ONE step together, then next step

        This ensures:
        1. All 20 models predict for the SAME timestamp at each step
        2. Proper alignment of horizon predictions (all target same bar)
        3. Immediate ensemble aggregation after each step

        Flow per iteration:
            For each step i in [0..n_iterations):
                For each target-horizon (20 combinations):
                    1. Get window for step i
                    2. Fit Layer 1 helpers
                    3. Generate helper features
                    4. Fit Layer 2 models
                    5. Predict (horizon rows, use last for alignment)
                    6. Store prediction
                Aggregate all 20 predictions for step i
                Compute position for step i
                Advance to step i+1
        """
        if verbose:
            print("=" * 60)
            print("SYNCHRONIZED PIPELINE (Step-by-Step)")
            print("=" * 60)
            print(f"Targets: {self.config.targets}")
            print(f"Horizons: {self.config.horizons}")
            print(f"Total combinations: {self.config.n_targets}")
            print(f"Backtest rows: {self.config.backtest_rows}")
            print()

        # Step 1: Load data for all targets and setup engines
        if verbose:
            print("Loading data and setting up engines...")

        for _id, runner in self.target_runners.items():
            runner.load_data(verbose=False)
            runner.setup_engine()

        # Determine number of iterations (use minimum across all targets)
        n_iterations = min(
            runner.engine.n_iterations for runner in self.target_runners.values()
        )

        if max_iterations is not None:
            n_iterations = min(n_iterations, max_iterations)

        if verbose:
            print(f"  Iterations: {n_iterations}")
            print()

        # Storage for predictions by target
        all_target_predictions: dict[str, list[TargetPrediction]] = {
            identifier: [] for identifier in self.target_runners
        }

        # Step 2: Run synchronized iterations
        for step in range(n_iterations):
            if verbose and step % 50 == 0:
                print(f"Step {step}/{n_iterations}...")

            # Run all 20 models for this step
            for identifier, runner in self.target_runners.items():
                try:
                    # Get window for this step
                    engine = runner.engine
                    pred_idx = engine.first_pred_idx + step * engine.config.step_size
                    window = engine.get_window(pred_idx, step)

                    # Run single iteration
                    prediction = runner.run_iteration(window)
                    all_target_predictions[identifier].append(prediction)

                except Exception as e:
                    if verbose:
                        print(f"  Warning: {identifier} step {step} failed: {e}")
                    continue

        # Step 3: Aggregate and compute positions
        if verbose:
            print("\nAggregating predictions...")

        # Store predictions in runners for aggregation
        for id_, preds in all_target_predictions.items():
            self.target_runners[id_].predictions = preds

        self.aggregate_predictions(all_target_predictions)

        if self.config.position_sizing_enabled:
            if verbose:
                print("Computing positions...")
            self.compute_positions()

        if verbose:
            print("\nSynchronized pipeline complete!")
            print(f"  Ensemble predictions: {len(self.ensemble_predictions)}")
            print(f"  Position results: {len(self.position_results)}")

        return self.position_results


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================
def run_full_pipeline(
    targets: tuple[str, ...] | None = None,
    horizons: tuple[int, ...] | None = None,
    max_iterations: int | None = None,
    verbose: bool = True,
) -> list[PositionSizingResult]:
    """
    Quick function to run the full pipeline.

    Args:
        targets: Subset of targets (default all)
        horizons: Subset of horizons (default all)
        max_iterations: Limit iterations (for testing)
        verbose: Print progress

    Returns:
        List of PositionSizingResult
    """
    config = PipelineConfig(
        targets=targets or ALL_TARGETS,
        horizons=horizons or ALL_HORIZONS,
    )

    orchestrator = PipelineOrchestrator(config)
    return orchestrator.run(max_iterations=max_iterations, verbose=verbose)


def run_single_target(
    target: str,
    horizon: int,
    max_iterations: int | None = None,
    verbose: bool = True,
) -> list[TargetPrediction]:
    """
    Run pipeline for a single target-horizon.

    Useful for testing/debugging.
    """
    config = PipelineConfig(
        targets=(target,),
        horizons=(horizon,),
        position_sizing_enabled=False,
    )

    spec = get_target_spec(target, horizon)
    runner = TargetRunner(spec, config)

    return runner.run(max_iterations=max_iterations, verbose=verbose)


# =============================================================================
# CLI
# =============================================================================
def main():
    """CLI entry point."""

    # Quick test with limited iterations
    print("Running pipeline test (10 iterations)...")
    print()

    results = run_full_pipeline(
        targets=("volatility", "direction"),
        horizons=(6,),
        max_iterations=10,
        verbose=True,
    )

    print()
    print("Results:")
    for r in results[:5]:
        print(f"  t={r.timestamp}: pos={r.final_position:.2f} dir={r.direction}")


if __name__ == "__main__":
    main()
