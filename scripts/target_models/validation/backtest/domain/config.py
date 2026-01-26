"""
Domain Configuration Module

Contains core configuration dataclasses for the backtest system:
- PerModelConfig: Per-model window/split/feature configuration
- SyncBacktestConfig: Main backtest configuration

NOTE: Fixed DEFAULT_*_CONFIG constants have been REMOVED.
Config optimization is now done dynamically per (model, target, data) combination.
See: backtest/models/*_model.py for optimize_*_config() functions.

Extracted from l2_backtest_sync.py for modularity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PerModelConfig:
    """Per-model configuration for independent optimization.

    Allows each model (CatBoost, LightGBM, LSTM, Linear) to have its own:
    - Training window size
    - Train/val/cal split ratios
    - Embargo bars
    - Feature selection method and ratio

    IMPORTANT: Do NOT use fixed values. Use optimize_*_config() functions
    in each model module to determine optimal parameters based on:
    - X_full, y_full: The actual data for the current step
    - target_name: Which target we're predicting
    - task_type: "classification" or "regression"

    The default values below are FALLBACKS only, used when:
    - Testing individual components
    - No optimizer is available yet

    In production backtest, these should be overridden by optimizers.
    """

    # Window configuration
    train_window: int = 500  # Training window size (bars)
    train_ratio: float = 0.55  # Train split within window
    val_ratio: float = 0.15  # Validation split
    cal_ratio: float = 0.30  # Calibration split

    # Embargo (gap between splits to prevent leakage)
    embargo_bars: int = 24  # Gap between train/val/cal

    # Feature selection
    feature_selection: str = "none"  # "none", "icir", "importance", "variance"
    feature_selection_ratio: float = 1.0  # Keep top X% of features (1.0 = all)
    min_features: int = 20  # Never go below this count

    def validate(self) -> None:
        """Validate configuration values."""
        if self.train_window < 100:
            raise ValueError(f"train_window must be >= 100, got {self.train_window}")
        if not (0.3 <= self.train_ratio <= 0.8):
            raise ValueError(f"train_ratio must be 0.3-0.8, got {self.train_ratio}")
        if self.feature_selection not in ("none", "icir", "importance", "variance"):
            raise ValueError(f"Invalid feature_selection: {self.feature_selection}")
        if not (0.1 <= self.feature_selection_ratio <= 1.0):
            raise ValueError("feature_selection_ratio must be 0.1-1.0")


# =============================================================================
# NOTE: Fixed DEFAULT_*_CONFIG constants have been REMOVED
# =============================================================================
# Previously this file contained:
#   DEFAULT_CB_CONFIG = PerModelConfig(train_window=400, ...)
#   DEFAULT_LGB_CONFIG = PerModelConfig(train_window=400, ...)
#   DEFAULT_LSTM_CONFIG = PerModelConfig(train_window=600, ...)
#   DEFAULT_LINEAR_CONFIG = PerModelConfig(train_window=800, ...)
#
# These FIXED configs were used for ALL targets (direction, volatility, etc.)
# and ALL walk-forward steps (step 1 through step 3000+).
#
# NOW: Each model has an optimize_*_config() function that determines
# optimal parameters based on:
#   - X_full, y_full: The actual data for this step
#   - target_name: Which target we're predicting (direction_1bar, vol_6bar, etc.)
#   - task_type: "classification" or "regression"
#
# See: backtest/models/*_model.py for optimize_* functions
# =============================================================================


@dataclass
class SyncBacktestConfig:
    """Configuration for synchronized L2 backtest."""

    # Walk-forward settings
    train_window: int = 500
    step_size: int = 1
    n_steps: int | None = None  # Number of steps to run (None = all available)
    spread_steps: bool = False  # If True, spread n_steps evenly across full data range

    # Split ratios within training window
    train_ratio: float = 0.55
    val_ratio: float = 0.15
    cal_ratio: float = 0.30

    # Embargo gap (de Prado "Advances in Financial ML", arXiv 2512.06932)
    # Gap between train/val/cal to prevent temporal leakage via autocorrelation
    # Set to max prediction horizon (e.g., 24 bars for direction_24bar)
    embargo_bars: int = 24

    # Model settings
    random_state: int = 42
    n_estimators: int = 100
    max_depth: int = 6  # arXiv 2305.17094: depth 6 often optimal

    # Ensemble weights (CatBoost + LightGBM + LSTM + Linear = 1.0)
    cb_weight: float = 0.30
    lgb_weight: float = 0.30
    lstm_weight: float = 0.25
    # linear_weight = 1.0 - cb_weight - lgb_weight - lstm_weight (auto-computed)

    # Adaptive ensemble weights (arXiv 2304.09947 - Multiplicative Weights Update)
    use_adaptive_weights: bool = True  # Adjust weights based on recent performance
    adaptive_lookback: int = 50  # Number of recent predictions to evaluate
    adaptive_learning_rate: float = 0.1  # How fast to adjust weights (eta in MWU)
    adaptive_min_weight: float = 0.05  # Minimum weight per model (prevent zeroing out)

    # CatBoost params (increased regularization per arXiv 2305.17094)
    cb_learning_rate: float = 0.03
    cb_l2_leaf_reg: float = 5.0  # Increased from 3.0 for better generalization

    # LightGBM params (increased regularization)
    lgb_learning_rate: float = 0.03
    lgb_reg_lambda: float = 3.0  # Increased from 1.0
    lgb_min_child_samples: int = 20  # Prevent overfitting to small leaf nodes

    # LSTM params
    lstm_hidden_size: int = 64
    lstm_num_layers: int = 2
    lstm_lr: float = 0.001
    lstm_epochs: int = 100  # Increased for better learning with sequences
    lstm_batch_size: int = 32
    lstm_dropout: float = 0.2
    lstm_seq_len: int = 20  # Temporal sequence length (lookback window)

    # Conformal
    conformal_alpha: float = 0.1  # 90% confidence

    # Feature clipping
    duration_max: float = 1000.0

    # Sample weighting (concept drift mitigation)
    # Based on de Prado "Advances in Financial ML" and arXiv concept drift research
    use_sample_weights: bool = True  # Enable exponential decay weighting
    sample_decay_halflife: float = 0.3  # Halflife as fraction of training window
    # 0.3 means recent 30% of data has ~50% of total weight

    # Optuna tuning settings
    enable_optuna: bool = True  # Enable per-step hyperparameter tuning
    n_optuna_trials: int = 15  # Number of trials per model per step
    optuna_timeout: float | None = 30.0  # Max seconds per model tuning (None=no limit)
    optuna_prune: bool = True  # Enable pruning for faster search

    # Output
    output_dir: Path = field(default_factory=lambda: Path("data/l2_backtest_results"))

    # Logging
    log_to_file: bool = True  # Save all print output to log file
    save_step_metrics: bool = True  # Save per-step metrics to parquet
    step_metrics_interval: int = 10  # Save metrics every N steps (avoid I/O overhead)

    # Per-model configurations - each model has independent optimization
    # These are ALWAYS used (no shared config mode)
    cb_config: PerModelConfig | None = None  # CatBoost config
    lgb_config: PerModelConfig | None = None  # LightGBM config
    lstm_config: PerModelConfig | None = None  # LSTM config
    linear_config: PerModelConfig | None = None  # Linear config

    # Extended metrics storage (comprehensive tracking)
    store_extended_metrics: bool = False  # Store timing, features, importance

    def __post_init__(self):
        self.output_dir = Path(self.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # NOTE: Per-model configs are now set to None by default
        # They will be created dynamically by optimize_*_config() functions
        # in services/training.py based on actual data characteristics.
        #
        # If you need to pass explicit configs, set them when creating
        # SyncBacktestConfig. Otherwise, the training pipeline will
        # call the appropriate optimizer for each (model, target) combination.

    def get_max_window_size(self) -> int:
        """Get the maximum window size across all models.

        Used to ensure we extract enough data for all models.
        Returns 1000 as the safe maximum (Linear with horizon multiplier).

        NOTE: This is used for initial data extraction. The actual
        window used per model may be smaller based on optimization.
        """
        # Use explicit configs if provided, otherwise use safe maximum
        windows = [
            self.cb_config.train_window if self.cb_config else 1000,
            self.lgb_config.train_window if self.lgb_config else 1000,
            self.lstm_config.train_window if self.lstm_config else 1000,
            self.linear_config.train_window if self.linear_config else 1000,
        ]
        return max(windows)

    def get_model_config(self, model: str) -> PerModelConfig:
        """Get configuration for a specific model.

        Args:
            model: One of 'cb', 'lgb', 'lstm', 'linear'

        Returns:
            PerModelConfig for the model
        """
        configs = {
            "cb": self.cb_config,
            "lgb": self.lgb_config,
            "lstm": self.lstm_config,
            "linear": self.linear_config,
        }

        config = configs.get(model)
        if config is not None:
            return config

        # Fallback to shared settings (used when optimizer hasn't run yet)
        return PerModelConfig(
            train_window=self.train_window,
            train_ratio=self.train_ratio,
            val_ratio=self.val_ratio,
            cal_ratio=self.cal_ratio,
            embargo_bars=self.embargo_bars,
        )


# Exports
__all__ = [
    "PerModelConfig",
    "SyncBacktestConfig",
]
