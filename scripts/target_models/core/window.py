"""
Unified Walk-Forward Window Management.

This module provides the core infrastructure for walk-forward validation
that ALL 20 target-horizon pipelines share.

Key concepts:
- WalkForwardConfig: Window sizes and parameters (target-horizon specific)
- WalkForwardWindow: Current window boundaries at a given pred_time
- WalkForwardEngine: Iterates through time, yielding windows
- WindowSlice: Data slice for a specific window (train/cal/val/pred)

Usage:
    # Each target-horizon has its own config
    config = WalkForwardConfig(
        train_size=1000,
        cal_size=150,
        val_size=200,
        pred_size=1,
        purge_gap=21,  # Depends on horizon
    )

    # Engine iterates through time
    engine = WalkForwardEngine(data, config)

    for window in engine.iterate():
        # window.train -> data slice for training
        # window.cal -> data slice for calibration
        # window.val -> data slice for validation
        # window.pred -> data slice for prediction

        # Fit helpers on train
        hmm.fit(window.train.X)

        # Transform all windows
        train_features = hmm.transform(window.train.X)
        pred_features = hmm.transform(window.pred.X)

        # Fit model on train
        model.fit(train_features, window.train.y)

        # Predict
        prediction = model.predict(pred_features)
"""

from collections.abc import Generator
from dataclasses import dataclass

import numpy as np
import pandas as pd


# =============================================================================
# CONFIGURATION
# =============================================================================
@dataclass
class WalkForwardConfig:
    """
    Configuration for walk-forward window sizes.

    Each target-horizon combination can have different settings optimized
    for its specific characteristics.

    Window layout (looking backwards from pred_time):

    Time →  [====TRAIN====][purge][==CAL==][==VAL==][PRED]
                                                      ↑
                                                  pred_time
    """

    # Window sizes (in bars/rows)
    train_size: int = 1000  # Training window
    cal_size: int = 150  # Calibration window
    val_size: int = 200  # Validation window (early stopping, threshold)
    pred_size: int = 1  # Prediction window (usually 1)

    # Gap sizes (prevent leakage)
    purge_gap: int = 21  # Gap between train and cal (depends on horizon)
    embargo_gap: int = 0  # Gap after pred (for next iteration)

    # Iteration control
    step_size: int = 1  # How much to advance pred_time each iteration
    min_train_size: int = 500  # Minimum train size to start

    # Retraining frequency (not every step needs full retrain)
    retrain_frequency: int = 1  # Retrain every N steps (1 = every step)

    # Target-horizon identification
    target_name: str = ""
    horizon: int = 1

    def __post_init__(self):
        """Validate configuration."""
        if self.train_size < self.min_train_size:
            raise ValueError(
                f"train_size ({self.train_size}) < min_train_size ({self.min_train_size})"
            )
        if self.purge_gap < 0:
            raise ValueError("purge_gap must be >= 0")
        if self.step_size < 1:
            raise ValueError("step_size must be >= 1")

    @property
    def total_window_size(self) -> int:
        """Total rows needed for one complete window."""
        return (
            self.train_size
            + self.purge_gap
            + self.cal_size
            + self.val_size
            + self.pred_size
        )

    @property
    def identifier(self) -> str:
        """Unique identifier for this config."""
        return f"{self.target_name}_{self.horizon}bar"

    def adapt_purge_for_horizon(self) -> "WalkForwardConfig":
        """
        Adjust purge_gap based on horizon to prevent leakage.

        Rule: purge_gap >= horizon + buffer
        """
        min_purge = self.horizon + 10  # horizon + safety buffer
        if self.purge_gap < min_purge:
            return WalkForwardConfig(
                train_size=self.train_size,
                cal_size=self.cal_size,
                val_size=self.val_size,
                pred_size=self.pred_size,
                purge_gap=min_purge,
                embargo_gap=self.embargo_gap,
                step_size=self.step_size,
                min_train_size=self.min_train_size,
                retrain_frequency=self.retrain_frequency,
                target_name=self.target_name,
                horizon=self.horizon,
            )
        return self


# =============================================================================
# WINDOW SLICE
# =============================================================================
@dataclass
class WindowSlice:
    """
    A slice of data for a specific window (train/cal/val/pred).

    Contains the data and index boundaries.
    """

    X: pd.DataFrame  # Features
    y: pd.Series | None  # Target (None for pred in live mode)
    start_idx: int  # Start index in original data
    end_idx: int  # End index (exclusive) in original data
    name: str  # 'train', 'cal', 'val', 'pred'

    def __len__(self) -> int:
        return len(self.X)

    @property
    def indices(self) -> np.ndarray:
        """Array of indices in this slice."""
        return np.arange(self.start_idx, self.end_idx)

    def __repr__(self) -> str:
        return f"WindowSlice({self.name}: [{self.start_idx}:{self.end_idx}], {len(self)} rows)"


# =============================================================================
# WALK-FORWARD WINDOW
# =============================================================================
@dataclass
class WalkForwardWindow:
    """
    Complete window state at a specific prediction time.

    Contains all four slices: train, cal, val, pred.
    All helpers and models operate within these boundaries.
    """

    train: WindowSlice
    cal: WindowSlice
    val: WindowSlice
    pred: WindowSlice

    pred_time: int  # The prediction timestamp index
    iteration: int  # Iteration number
    config: WalkForwardConfig  # Config used to create this window

    @property
    def train_cal(self) -> pd.DataFrame:
        """Combined train + cal features (for some fitting strategies)."""
        return pd.concat([self.train.X, self.cal.X], ignore_index=True)

    @property
    def train_cal_y(self) -> pd.Series:
        """Combined train + cal targets."""
        return pd.concat([self.train.y, self.cal.y], ignore_index=True)

    @property
    def all_X(self) -> pd.DataFrame:
        """All features (train + cal + val + pred)."""
        return pd.concat(
            [self.train.X, self.cal.X, self.val.X, self.pred.X], ignore_index=True
        )

    def get_train_val_split(
        self,
    ) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series]:
        """Return train X, train y, val X, val y for model fitting with early stopping."""
        return self.train.X, self.train.y, self.val.X, self.val.y

    def __repr__(self) -> str:
        return (
            f"WalkForwardWindow(iter={self.iteration}, pred_time={self.pred_time}, "
            f"train={len(self.train)}, cal={len(self.cal)}, "
            f"val={len(self.val)}, pred={len(self.pred)})"
        )


# =============================================================================
# WALK-FORWARD ENGINE
# =============================================================================
class WalkForwardEngine:
    """
    Engine that iterates through time, yielding WalkForwardWindow objects.

    This is the core class that all 20 target-horizon pipelines use.
    Each pipeline passes its own config, but the iteration logic is shared.

    Usage:
        engine = WalkForwardEngine(X, y, config)

        for window in engine.iterate():
            # Process this window
            predictions.append(pipeline.process(window))
    """

    def __init__(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        config: WalkForwardConfig,
    ):
        """
        Initialize engine with data and config.

        Args:
            X: Feature DataFrame (full dataset)
            y: Target Series (full dataset)
            config: Walk-forward configuration
        """
        self.X = X.reset_index(drop=True)
        self.y = y.reset_index(drop=True)
        self.config = config

        self._validate_data()

    def _validate_data(self):
        """Validate data is suitable for walk-forward."""
        n_samples = len(self.X)
        min_required = self.config.total_window_size

        if n_samples < min_required:
            raise ValueError(
                f"Not enough data: {n_samples} rows, need at least {min_required} "
                f"for config {self.config.identifier}"
            )

        if len(self.X) != len(self.y):
            raise ValueError(f"X and y length mismatch: {len(self.X)} vs {len(self.y)}")

    @property
    def start_pred_time(self) -> int:
        """First valid prediction time index."""
        # Need enough history for: train + purge + cal + val
        return (
            self.config.train_size
            + self.config.purge_gap
            + self.config.cal_size
            + self.config.val_size
        )

    @property
    def end_pred_time(self) -> int:
        """Last valid prediction time index."""
        return len(self.X) - self.config.pred_size

    @property
    def n_iterations(self) -> int:
        """Total number of iterations."""
        return (self.end_pred_time - self.start_pred_time) // self.config.step_size + 1

    def get_window(self, pred_time: int, iteration: int = 0) -> WalkForwardWindow:
        """
        Get window boundaries for a specific prediction time.

        Window layout (indices are exclusive on the right):

        [0...train_start...train_end][purge][cal_start...cal_end][val_start...val_end][pred_start...pred_end]
                                                                                         ↑
                                                                                     pred_time
        """
        cfg = self.config

        # Work backwards from pred_time
        pred_end = pred_time + cfg.pred_size
        pred_start = pred_time

        val_end = pred_start
        val_start = val_end - cfg.val_size

        cal_end = val_start
        cal_start = cal_end - cfg.cal_size

        # Train ends before purge gap
        train_end = cal_start - cfg.purge_gap
        train_start = max(0, train_end - cfg.train_size)

        # Create slices
        train_slice = WindowSlice(
            X=self.X.iloc[train_start:train_end].reset_index(drop=True),
            y=self.y.iloc[train_start:train_end].reset_index(drop=True),
            start_idx=train_start,
            end_idx=train_end,
            name="train",
        )

        cal_slice = WindowSlice(
            X=self.X.iloc[cal_start:cal_end].reset_index(drop=True),
            y=self.y.iloc[cal_start:cal_end].reset_index(drop=True),
            start_idx=cal_start,
            end_idx=cal_end,
            name="cal",
        )

        val_slice = WindowSlice(
            X=self.X.iloc[val_start:val_end].reset_index(drop=True),
            y=self.y.iloc[val_start:val_end].reset_index(drop=True),
            start_idx=val_start,
            end_idx=val_end,
            name="val",
        )

        pred_slice = WindowSlice(
            X=self.X.iloc[pred_start:pred_end].reset_index(drop=True),
            y=self.y.iloc[pred_start:pred_end].reset_index(drop=True),
            start_idx=pred_start,
            end_idx=pred_end,
            name="pred",
        )

        return WalkForwardWindow(
            train=train_slice,
            cal=cal_slice,
            val=val_slice,
            pred=pred_slice,
            pred_time=pred_time,
            iteration=iteration,
            config=cfg,
        )

    def iterate(
        self,
        start: int | None = None,
        end: int | None = None,
        verbose: bool = True,
    ) -> Generator[WalkForwardWindow, None, None]:
        """
        Iterate through all valid prediction times.

        Args:
            start: Starting pred_time (default: first valid)
            end: Ending pred_time (default: last valid)
            verbose: Print progress

        Yields:
            WalkForwardWindow for each prediction time
        """
        start = start or self.start_pred_time
        end = end or self.end_pred_time

        if verbose:
            print(f"Walk-forward: {self.config.identifier}")
            print(f"  Data: {len(self.X)} rows")
            print(f"  Range: pred_time {start} → {end}")
            print(f"  Iterations: {self.n_iterations}")
            print(
                f"  Windows: train={self.config.train_size}, cal={self.config.cal_size}, "
                f"val={self.config.val_size}, purge={self.config.purge_gap}"
            )
            print()

        iteration = 0
        pred_time = start

        while pred_time <= end:
            window = self.get_window(pred_time, iteration)
            yield window

            pred_time += self.config.step_size
            iteration += 1

    def should_retrain(self, iteration: int) -> bool:
        """Check if model should be retrained at this iteration."""
        return iteration % self.config.retrain_frequency == 0


# =============================================================================
# FACTORY FUNCTIONS
# =============================================================================
def create_config_for_target(
    target_name: str,
    horizon: int,
    train_size: int = 1000,
    cal_size: int = 150,
    val_size: int = 200,
) -> WalkForwardConfig:
    """
    Create walk-forward config for a specific target-horizon.

    Automatically adjusts purge_gap based on horizon.
    """
    # Base purge gap depends on horizon
    # Rule: need at least horizon + buffer to prevent target leakage
    purge_gap = max(21, horizon + 10)

    config = WalkForwardConfig(
        train_size=train_size,
        cal_size=cal_size,
        val_size=val_size,
        pred_size=1,
        purge_gap=purge_gap,
        target_name=target_name,
        horizon=horizon,
    )

    return config


# =============================================================================
# PRESET CONFIGS FOR ALL 20 TARGET-HORIZONS
# =============================================================================
def get_default_configs() -> dict[str, WalkForwardConfig]:
    """
    Get default configs for all 20 target-horizon combinations.

    Returns dict like: {"volatility_1bar": config, "volatility_3bar": config, ...}
    """
    configs = {}

    targets = ["volatility", "direction", "returns", "vol_regime", "trend_regime"]
    horizons = [1, 3, 6, 12]

    for target in targets:
        for horizon in horizons:
            key = f"{target}_{horizon}bar"
            configs[key] = create_config_for_target(target, horizon)

    return configs


# Default configs (can be imported directly)
DEFAULT_CONFIGS = get_default_configs()
