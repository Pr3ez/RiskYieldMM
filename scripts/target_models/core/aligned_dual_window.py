"""
Timestamp-Aligned Expanding L1 + Sliding L2 Window Management.

NEW ARCHITECTURE (replaces fixed-window dual_window.py):

Data: All 20 targets aligned by timestamp (4679 common rows)

LAYER 1 (Expanding): Unsupervised helpers use ALL historical data
    [0 ─────────────────────────── L2_start]
    - Starts at index 0, grows each iteration
    - Helpers fitted on full history (incrementally updated)
    - No fixed train/cal/val split - use expanding OOS validation

LAYER 2 (Sliding): Supervised models use fixed recent window
    [L2_start ──────────────────── pred_time]
    - Fixed size (e.g., 500 rows)
    - Slides forward each iteration
    - train/cal/val split within the window

KEY PROPERTIES:
1. No overlap/gap between L1 and L2 - they are contiguous
2. All 20 targets predict for SAME timestamp
3. L1 can be incrementally updated (warm_start) for speed
4. L2 size can be optimized per target/horizon
"""

from collections.abc import Generator
from dataclasses import dataclass, field

import pandas as pd

from .validators import validate_no_lookahead
from .window import WindowSlice


# =============================================================================
# EXPANDING L1 CONFIGURATION
# =============================================================================
@dataclass
class ExpandingL1Config:
    """
    Configuration for Layer 1 (expanding window for unsupervised helpers).

    L1 uses ALL data from start to L2_start, growing each iteration.
    """

    min_warmup: int = 500  # Minimum rows before L1 can produce valid features

    # For helper optimization/validation within expanding window:
    holdout_ratio: float = 0.2  # Last 20% for validation

    def get_train_val_split(self, total_rows: int) -> tuple[int, int]:
        """Split expanding window into train/val portions."""
        val_size = max(int(total_rows * self.holdout_ratio), 50)
        train_end = total_rows - val_size
        return train_end, val_size


# =============================================================================
# SLIDING L2 CONFIGURATION
# =============================================================================
@dataclass
class SlidingL2Config:
    """
    Configuration for Layer 2 (sliding window for supervised models).

    Fixed-size window that slides forward.

    Default split (window_size=500):
        - train: 275 samples (55%)
        - cal: 150 samples (30%) - required for MAPIE conformal prediction
        - purge: 21 samples (horizon protection)
        - val: 54 samples (remainder)
    """

    window_size: int = 500  # Total L2 window size

    # Window splits (within the sliding window):
    # Adjusted for conformal prediction (Phase 8): cal needs 150+ samples
    train_ratio: float = 0.55  # 55% for training (275 samples)
    cal_ratio: float = 0.30  # 30% for calibration (150 samples for MAPIE)
    val_ratio: float = 0.15  # Remainder for validation (~54 samples)

    # Purge gap between train and cal/val (to prevent leakage)
    purge_gap: int = 21  # max(21, horizon + 10)

    # Prediction size
    pred_size: int = 1

    def get_splits(self) -> tuple[int, int, int]:
        """Get train/cal/val sizes within the window."""
        train_size = int(self.window_size * self.train_ratio)
        cal_size = int(self.window_size * self.cal_ratio)
        val_size = self.window_size - train_size - cal_size - self.purge_gap
        return train_size, cal_size, val_size

    @property
    def total_size(self) -> int:
        """Total size including prediction."""
        return self.window_size + self.pred_size


# =============================================================================
# ADAPTIVE L2 CONFIGURATION (Tier 1.2)
# =============================================================================
# Research basis: docs/validation/ADAPTIVE_OPTIMIZATION_RESEARCH.md
# Decision Point 1.2: Regime targets need larger windows due to high persistence

# Targets that require larger windows due to regime persistence
# Regime persistence >95% means ~20 bar expected duration
REGIME_TARGETS: frozenset[str] = frozenset(
    {
        "trend_regime",
        "vol_regime",
    }
)

# Standard L2 config - works for direction/volatility/returns targets
STANDARD_L2_CONFIG = SlidingL2Config(
    window_size=500,
    train_ratio=0.55,  # 275 samples
    cal_ratio=0.30,  # 150 samples (adequate for conformal)
    val_ratio=0.15,  # ~54 samples
    purge_gap=21,
)

# Regime L2 config - for trend_regime and vol_regime targets
# Larger window to capture more regime transitions (persistence >95%)
REGIME_L2_CONFIG = SlidingL2Config(
    window_size=700,
    train_ratio=0.60,  # 420 samples (more for class balance)
    cal_ratio=0.25,  # 175 samples (adequate for conformal)
    val_ratio=0.15,  # ~84 samples
    purge_gap=21,
)


def get_l2_config_for_target(target_name: str) -> SlidingL2Config:
    """
    Return appropriate L2 config based on target characteristics.

    Regime targets (trend_regime, vol_regime) use larger windows
    due to high regime persistence (~95%, ~20 bar duration).

    Args:
        target_name: Target name (e.g., "volatility", "trend_regime")

    Returns:
        SlidingL2Config appropriate for the target

    Research basis:
        - Regime persistence >95% → expected duration 20 bars
        - 700 bars → ~35 regime transitions (vs 25 with 500)
        - 420 train samples → ~60 minority class samples
        - See docs/validation/ADAPTIVE_OPTIMIZATION_RESEARCH.md

    Example:
        >>> config = get_l2_config_for_target("trend_regime")
        >>> print(f"Window: {config.window_size}, Train ratio: {config.train_ratio}")
        Window: 700, Train ratio: 0.6
    """
    # Check if target is a regime target (prefix match)
    for regime_prefix in REGIME_TARGETS:
        if target_name.startswith(regime_prefix):
            return REGIME_L2_CONFIG

    return STANDARD_L2_CONFIG


def is_regime_target(target_name: str) -> bool:
    """Check if target is a regime target requiring larger windows."""
    for regime_prefix in REGIME_TARGETS:
        if target_name.startswith(regime_prefix):
            return True
    return False


# =============================================================================
# ALIGNED DUAL-LAYER CONFIGURATION
# =============================================================================
@dataclass
class AlignedDualConfig:
    """
    Combined configuration for expanding L1 + sliding L2.

    Window Layout:

    Data: [0 ─────────────────────────────────────────── N]
               │<── L1 EXPANDING ──>│<── L2 SLIDING ──>│pred
               [0 ─────────── L2_start][L2 window ───→][horizon]
                     grows ↑              slides →

    Backtest Control:
        backtest_rows controls how many iterations to run.
        If set to 500, the first prediction starts at (N - 500 - L2_window).
        This gives exactly 500 walk-forward iterations.
    """

    l1: ExpandingL1Config = field(default_factory=ExpandingL1Config)
    l2: SlidingL2Config = field(default_factory=SlidingL2Config)

    # Iteration control
    step_size: int = 1
    backtest_rows: int | None = 500  # None = use all data, int = limit iterations

    # Target-horizon identification
    target_name: str = ""
    horizon: int = 1

    def __post_init__(self):
        """Auto-adjust purge gaps based on horizon."""
        min_purge = self.horizon + 10
        if self.l2.purge_gap < min_purge:
            self.l2.purge_gap = min_purge

    @property
    def min_required_rows(self) -> int:
        """Minimum rows needed to start iteration."""
        return self.l1.min_warmup + self.l2.total_size

    @property
    def identifier(self) -> str:
        return f"{self.target_name}_{self.horizon}bar"


# =============================================================================
# LAYER WINDOWS
# =============================================================================
@dataclass
class ExpandingL1Window:
    """Window for Layer 1 (expanding unsupervised helpers)."""

    full: WindowSlice  # All data from 0 to L2_start
    train: WindowSlice  # Training portion (0 to train_end)
    val: WindowSlice  # Validation portion (train_end to L2_start)

    @property
    def size(self) -> int:
        """Current size of expanding window."""
        return len(self.full)

    def __repr__(self) -> str:
        return f"ExpandingL1Window(size={self.size}, train={len(self.train)}, val={len(self.val)})"


@dataclass
class SlidingL2Window:
    """Window for Layer 2 (sliding supervised models)."""

    full: WindowSlice  # Full L2 window
    train: WindowSlice  # Training portion
    cal: WindowSlice  # Calibration portion
    val: WindowSlice  # Validation portion
    pred: WindowSlice  # Prediction row(s)

    def __repr__(self) -> str:
        return (
            f"SlidingL2Window(train={len(self.train)}, cal={len(self.cal)}, "
            f"val={len(self.val)}, pred={len(self.pred)})"
        )


@dataclass
class AlignedDualWindow:
    """
    Complete aligned dual-layer window at a specific prediction timestamp.

    Both L1 and L2 reference the same aligned data, ensuring all 20 targets
    predict for the same timestamp.
    """

    l1: ExpandingL1Window
    l2: SlidingL2Window

    pred_timestamp: pd.Timestamp  # The prediction timestamp
    pred_idx: int  # Index in aligned data
    iteration: int  # Iteration number
    config: AlignedDualConfig  # Config used

    # Full data references
    _X_full: pd.DataFrame = field(repr=False, default=None)
    _y_full: pd.Series = field(repr=False, default=None)

    def get_l1_end_idx(self) -> int:
        """Index where L1 ends (= L2 starts)."""
        return self.l1.full.end_idx

    def get_l2_start_idx(self) -> int:
        """Index where L2 starts."""
        return self.l2.full.start_idx

    def verify_no_overlap(self) -> bool:
        """Verify L1 and L2 don't overlap."""
        return self.l1.full.end_idx == self.l2.full.start_idx

    def __repr__(self) -> str:
        return (
            f"AlignedDualWindow(iter={self.iteration}, "
            f"pred={self.pred_timestamp.strftime('%Y-%m-%d %H:%M')}, "
            f"L1_size={self.l1.size}, L2={self.l2})"
        )


# =============================================================================
# ALIGNED DUAL-LAYER ENGINE
# =============================================================================
class AlignedDualEngine:
    """
    Engine that yields AlignedDualWindow objects for walk-forward iteration.

    Works with timestamp-aligned data from load_aligned_data().

    Key Properties:
    - L1 expands from 0 to L2_start (uses all history)
    - L2 slides forward with fixed size
    - All 20 targets share same window boundaries (same timestamps)

    Usage:
        from scripts.target_models.registry import load_aligned_data

        aligned = load_aligned_data()
        config = AlignedDualConfig(target_name="volatility", horizon=6)

        for window in AlignedDualEngine(aligned.X, aligned.y, config).iterate():
            # 1. Fit helpers on expanding L1 window
            helpers.fit(window.l1.train.X)
            helpers.validate(window.l1.val.X)

            # 2. Transform L2 data
            X_l2_enriched = helpers.transform(window.l2.full.X)

            # 3. Fit supervised models on L2
            models.fit(X_l2_enriched[train_slice])
            models.calibrate(X_l2_enriched[cal_slice])

            # 4. Predict
            pred = models.predict(X_l2_enriched[pred_slice])
    """

    def __init__(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        config: AlignedDualConfig,
    ):
        """
        Initialize engine with aligned data.

        Args:
            X: Feature DataFrame with timestamp index
            y: Target Series with timestamp index
            config: Configuration for L1/L2 windows
        """
        # Keep timestamp index for alignment verification
        self.timestamps = X.index.copy()
        self.X = X.reset_index(drop=True)
        self.y = y.reset_index(drop=True)
        self.config = config

        self._validate_data()

    def _validate_data(self):
        """Validate data is sufficient for dual-layer windows."""
        n_samples = len(self.X)
        min_required = self.config.min_required_rows

        if n_samples < min_required:
            raise ValueError(
                f"Not enough data: {n_samples} rows, need at least {min_required} "
                f"for config {self.config.identifier}"
            )

    @property
    def first_pred_idx(self) -> int:
        """
        First valid prediction index.

        If backtest_rows is set, start later in data to limit iterations.
        Otherwise, start as early as possible (after warmup + L2 window).
        """
        # Minimum possible start (need L1 warmup + L2 window)
        min_start = self.config.min_required_rows - 1

        # If backtest_rows is set, calculate start to give exactly that many iterations
        if self.config.backtest_rows is not None:
            # We want: last_pred_idx - first_pred_idx + 1 = backtest_rows
            # So: first_pred_idx = last_pred_idx - backtest_rows + 1
            desired_start = self.last_pred_idx - self.config.backtest_rows + 1
            # But can't start before minimum
            return max(min_start, desired_start)

        return min_start

    @property
    def last_pred_idx(self) -> int:
        """Last valid prediction index."""
        return len(self.X) - self.config.l2.pred_size

    @property
    def n_iterations(self) -> int:
        """Total number of iterations."""
        return (self.last_pred_idx - self.first_pred_idx) // self.config.step_size + 1

    def get_window(self, pred_idx: int, iteration: int = 0) -> AlignedDualWindow:
        """
        Compute window boundaries for a specific prediction index.

        Layout:

        [0 ─────────── L2_start][L2_train][purge][L2_cal][L2_val][pred]
        │<─── L1 expanding ───>│<────── L2 sliding ─────────────>│

        Args:
            pred_idx: Index of the row to predict
            iteration: Iteration number

        Returns:
            AlignedDualWindow with all slices populated
        """
        l1_cfg = self.config.l1
        l2_cfg = self.config.l2

        # === LAYER 2 (work backwards from pred_idx) ===
        l2_pred_end = pred_idx + l2_cfg.pred_size
        l2_pred_start = pred_idx

        # Get train/cal/val sizes
        train_size, cal_size, val_size = l2_cfg.get_splits()

        # Work backwards
        l2_val_end = l2_pred_start
        l2_val_start = l2_val_end - val_size

        l2_cal_end = l2_val_start
        l2_cal_start = l2_cal_end - cal_size

        l2_train_end = l2_cal_start - l2_cfg.purge_gap
        l2_train_start = l2_train_end - train_size

        # L2 full window start
        l2_full_start = l2_train_start

        # === LAYER 1 (expanding from 0 to L2 start) ===
        l1_full_start = 0
        l1_full_end = l2_full_start  # Contiguous with L2

        # Split L1 into train/val
        l1_train_end, _ = l1_cfg.get_train_val_split(l1_full_end)
        l1_train_start = 0
        l1_val_start = l1_train_end
        l1_val_end = l1_full_end

        # === Create WindowSlices ===
        l1_window = ExpandingL1Window(
            full=WindowSlice(
                X=self.X.iloc[l1_full_start:l1_full_end].reset_index(drop=True),
                y=self.y.iloc[l1_full_start:l1_full_end].reset_index(drop=True),
                start_idx=l1_full_start,
                end_idx=l1_full_end,
                name="l1_full",
            ),
            train=WindowSlice(
                X=self.X.iloc[l1_train_start:l1_train_end].reset_index(drop=True),
                y=self.y.iloc[l1_train_start:l1_train_end].reset_index(drop=True),
                start_idx=l1_train_start,
                end_idx=l1_train_end,
                name="l1_train",
            ),
            val=WindowSlice(
                X=self.X.iloc[l1_val_start:l1_val_end].reset_index(drop=True),
                y=self.y.iloc[l1_val_start:l1_val_end].reset_index(drop=True),
                start_idx=l1_val_start,
                end_idx=l1_val_end,
                name="l1_val",
            ),
        )

        l2_window = SlidingL2Window(
            full=WindowSlice(
                X=self.X.iloc[l2_full_start:l2_pred_end].reset_index(drop=True),
                y=self.y.iloc[l2_full_start:l2_pred_end].reset_index(drop=True),
                start_idx=l2_full_start,
                end_idx=l2_pred_end,
                name="l2_full",
            ),
            train=WindowSlice(
                X=self.X.iloc[l2_train_start:l2_train_end].reset_index(drop=True),
                y=self.y.iloc[l2_train_start:l2_train_end].reset_index(drop=True),
                start_idx=l2_train_start,
                end_idx=l2_train_end,
                name="l2_train",
            ),
            cal=WindowSlice(
                X=self.X.iloc[l2_cal_start:l2_cal_end].reset_index(drop=True),
                y=self.y.iloc[l2_cal_start:l2_cal_end].reset_index(drop=True),
                start_idx=l2_cal_start,
                end_idx=l2_cal_end,
                name="l2_cal",
            ),
            val=WindowSlice(
                X=self.X.iloc[l2_val_start:l2_val_end].reset_index(drop=True),
                y=self.y.iloc[l2_val_start:l2_val_end].reset_index(drop=True),
                start_idx=l2_val_start,
                end_idx=l2_val_end,
                name="l2_val",
            ),
            pred=WindowSlice(
                X=self.X.iloc[l2_pred_start:l2_pred_end].reset_index(drop=True),
                y=self.y.iloc[l2_pred_start:l2_pred_end].reset_index(drop=True),
                start_idx=l2_pred_start,
                end_idx=l2_pred_end,
                name="l2_pred",
            ),
        )

        # ──────────────────────────────────────────────────────────────────
        # Tier 1.3: Lookahead validation (prevents information leakage)
        # ──────────────────────────────────────────────────────────────────
        is_valid, msg, metrics = validate_no_lookahead(
            pred_idx=pred_idx,
            train_end_idx=l2_train_end - 1,  # Convert exclusive end to inclusive
            cal_start_idx=l2_cal_start,
            horizon=l2_cfg.pred_size,
            purge_gap=l2_cfg.purge_gap,
        )
        if not is_valid:
            raise RuntimeError(
                f"CRITICAL: Lookahead bias detected at iteration {iteration}! {msg}. "
                f"This indicates a bug in the window calculation."
            )

        return AlignedDualWindow(
            l1=l1_window,
            l2=l2_window,
            pred_timestamp=self.timestamps[pred_idx],
            pred_idx=pred_idx,
            iteration=iteration,
            config=self.config,
            _X_full=self.X,
            _y_full=self.y,
        )

    def iterate(self) -> Generator[AlignedDualWindow, None, None]:
        """
        Yield windows for walk-forward iteration.

        Yields:
            AlignedDualWindow for each prediction timestamp
        """
        pred_idx = self.first_pred_idx
        iteration = 0

        while pred_idx <= self.last_pred_idx:
            yield self.get_window(pred_idx, iteration)
            pred_idx += self.config.step_size
            iteration += 1

    def get_iteration_summary(self) -> str:
        """Get summary of iteration parameters."""
        return (
            f"AlignedDualEngine Summary:\n"
            f"  Data: {len(self.X)} rows\n"
            f"  First pred: idx={self.first_pred_idx}, ts={self.timestamps[self.first_pred_idx]}\n"
            f"  Last pred: idx={self.last_pred_idx}, ts={self.timestamps[self.last_pred_idx]}\n"
            f"  Iterations: {self.n_iterations}\n"
            f"  L1 warmup: {self.config.l1.min_warmup}\n"
            f"  L2 window: {self.config.l2.window_size}\n"
            f"  Step size: {self.config.step_size}"
        )


# =============================================================================
# FACTORY FUNCTIONS
# =============================================================================
def create_aligned_config(
    target: str,
    horizon: int,
    l1_min_warmup: int = 500,
    l2_window_size: int | None = None,  # None = use adaptive config
    l2_purge_gap: int | None = None,
    step_size: int = 1,
    backtest_rows: int | None = 500,
) -> AlignedDualConfig:
    """
    Create aligned dual config for a target-horizon combination.

    Args:
        target: Target name (volatility, returns, etc.)
        horizon: Prediction horizon (1, 3, 6, 12)
        l1_min_warmup: Minimum rows for L1 before generating features
        l2_window_size: Size of sliding L2 window (None = use adaptive config)
        l2_purge_gap: Gap between L2 train and cal (auto if None)
        step_size: How many rows to advance each iteration
        backtest_rows: Number of walk-forward iterations (None = all data)
        use_adaptive_config: If True, use adaptive L2 config based on target type

    Returns:
        AlignedDualConfig ready for use

    Note on pred_size = horizon:
        For horizon alignment across all 20 models, each model predicts
        `horizon` rows. The LAST prediction from each horizon targets
        the same future bar:

        h=1:  predict 1 row  → last targets t+1
        h=3:  predict 3 rows → last targets (t-2)+3 = t+1
        h=6:  predict 6 rows → last targets (t-5)+6 = t+1
        h=12: predict 12 rows → last targets (t-11)+12 = t+1

        All horizons' LAST prediction aligns to the same target bar.

    Adaptive Config (Tier 1.2):
        When use_adaptive_config=True or l2_window_size=None:
        - Regime targets (trend_regime, vol_regime): window=700, train=60%
        - Standard targets: window=500, train=55%

        This addresses high regime persistence (~95%) which causes
        single-class training windows in regime targets.
    """
    l1_cfg = ExpandingL1Config(min_warmup=l1_min_warmup)

    # Use adaptive L2 config based on target type (Tier 1.2)
    # If l2_window_size is explicitly provided, respect it
    # Otherwise, use adaptive config based on target
    if l2_window_size is None:
        # Auto-select config based on target type
        base_l2_cfg = get_l2_config_for_target(target)
        l2_cfg = SlidingL2Config(
            window_size=base_l2_cfg.window_size,
            train_ratio=base_l2_cfg.train_ratio,
            cal_ratio=base_l2_cfg.cal_ratio,
            val_ratio=base_l2_cfg.val_ratio,
            purge_gap=base_l2_cfg.purge_gap,
            pred_size=horizon,
        )
    else:
        # Use explicitly provided window size with default ratios
        l2_cfg = SlidingL2Config(window_size=l2_window_size, pred_size=horizon)

    if l2_purge_gap is not None:
        l2_cfg.purge_gap = l2_purge_gap

    config = AlignedDualConfig(
        l1=l1_cfg,
        l2=l2_cfg,
        step_size=step_size,
        backtest_rows=backtest_rows,
        target_name=target,
        horizon=horizon,
    )

    return config


# =============================================================================
# BACKWARD COMPATIBILITY ALIASES (for pipeline.py)
# =============================================================================
# These map old DualLayer* names to new Aligned* classes
Layer1Config = ExpandingL1Config
Layer2Config = SlidingL2Config
DualLayerConfig = AlignedDualConfig
Layer1Window = ExpandingL1Window
Layer2Window = SlidingL2Window
DualLayerWindow = AlignedDualWindow
DualLayerEngine = AlignedDualEngine


def create_dual_config(
    target: str | None = None,
    horizon: int = 1,
    l1_window_size: int = 500,
    l2_window_size: int = 500,
    purge_gap: int | None = None,
    step_size: int = 1,
    backtest_rows: int | None = 500,
    # Backward compatibility with old pipeline.py parameter names
    target_name: str | None = None,
    l1_train: int | None = None,
    l1_cal: int | None = None,
    l1_val: int | None = None,
    l2_train: int | None = None,
    l2_cal: int | None = None,
    l2_val: int | None = None,
) -> AlignedDualConfig:
    """
    Backward-compatible factory for DualLayerConfig.

    Accepts both old parameter names (l1_train, l1_cal, etc.) and
    new parameter names (l1_window_size, l2_window_size).

    Maps to create_aligned_config with appropriate parameter names.
    """
    # Handle target name (accept both 'target' and 'target_name')
    actual_target = target_name if target_name is not None else target
    if actual_target is None:
        actual_target = "unknown"

    # Use old L1 sizes if provided, otherwise use l1_window_size
    actual_l1_warmup = l1_train if l1_train is not None else l1_window_size

    # Use old L2 train size if provided, otherwise use l2_window_size
    actual_l2_window = l2_train if l2_train is not None else l2_window_size

    return create_aligned_config(
        target=actual_target,
        horizon=horizon,
        l1_min_warmup=actual_l1_warmup,
        l2_window_size=actual_l2_window,
        l2_purge_gap=purge_gap,
        step_size=step_size,
        backtest_rows=backtest_rows,
    )


# Default configs for backward compatibility
DEFAULT_DUAL_CONFIGS: dict[str, AlignedDualConfig] = {}


# =============================================================================
# TEST / CLI
# =============================================================================
if __name__ == "__main__":
    from scripts.target_models.registry import load_aligned_data

    print("=" * 60)
    print("ALIGNED DUAL-LAYER WINDOW TEST")
    print("=" * 60)

    # Load aligned data
    aligned = load_aligned_data(verbose=True)

    # Create config
    config = create_aligned_config(
        target="volatility",
        horizon=6,
        l1_min_warmup=500,
        l2_window_size=500,
    )

    print()
    print(f"Config: {config.identifier}")
    print(f"  L1 min warmup: {config.l1.min_warmup}")
    print(f"  L2 window size: {config.l2.window_size}")
    print(f"  L2 purge gap: {config.l2.purge_gap}")

    # Get target
    y = aligned.targets["volatility_6bar"]

    # Create engine
    engine = AlignedDualEngine(aligned.X, y, config)

    print()
    print(engine.get_iteration_summary())

    # Test first and last windows
    print()
    print("=" * 60)
    print("FIRST WINDOW")
    print("=" * 60)

    first_window = engine.get_window(engine.first_pred_idx, 0)
    print(first_window)
    print(f"  L1 ends at idx: {first_window.get_l1_end_idx()}")
    print(f"  L2 starts at idx: {first_window.get_l2_start_idx()}")
    print(f"  No overlap: {first_window.verify_no_overlap()}")

    print()
    print("=" * 60)
    print("LAST WINDOW")
    print("=" * 60)

    last_window = engine.get_window(engine.last_pred_idx, engine.n_iterations - 1)
    print(last_window)
    print(f"  L1 ends at idx: {last_window.get_l1_end_idx()}")
    print(f"  L2 starts at idx: {last_window.get_l2_start_idx()}")
    print(f"  L1 growth: {last_window.l1.size - first_window.l1.size} rows")
