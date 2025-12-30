"""
Core walk-forward infrastructure.

Provides unified sliding window management for all 20 target-horizon pipelines.

Two modes:
1. Single-layer (window.py): Simple train/cal/val/pred for basic models
2. Dual-layer ALIGNED (aligned_dual_window.py): Expanding L1 + Sliding L2

ALIGNED ARCHITECTURE:
- L1 EXPANDING: Uses ALL historical data (grows each iteration)
- L2 SLIDING: Fixed window (e.g., 500 rows) that moves forward
- All 20 targets predict for SAME timestamp

ADAPTIVE CONFIG (Tier 1.2):
- Regime targets (trend_regime, vol_regime): Larger windows (700)
- Standard targets: Default windows (500)
"""

from .aligned_dual_window import (
    # Backward compatibility aliases
    DEFAULT_DUAL_CONFIGS,
    # Adaptive config (Tier 1.2)
    REGIME_L2_CONFIG,
    REGIME_TARGETS,
    STANDARD_L2_CONFIG,
    # New names
    AlignedDualConfig,
    AlignedDualEngine,
    AlignedDualWindow,
    DualLayerConfig,
    DualLayerEngine,
    DualLayerWindow,
    ExpandingL1Config,
    ExpandingL1Window,
    Layer1Config,
    Layer1Window,
    Layer2Config,
    Layer2Window,
    SlidingL2Config,
    SlidingL2Window,
    create_aligned_config,
    create_dual_config,
    get_l2_config_for_target,
    is_regime_target,
)
from .validators import (
    ClassBalanceMetrics,
    LookaheadMetrics,
    compute_class_entropy,
    compute_purge_gap,
    validate_class_balance,
    validate_no_lookahead,
    validate_training_window,
)
from .window import (
    WalkForwardConfig,
    WalkForwardEngine,
    WalkForwardWindow,
    WindowSlice,
)

__all__ = [
    # Single-layer
    "WalkForwardConfig",
    "WalkForwardWindow",
    "WalkForwardEngine",
    "WindowSlice",
    # Dual-layer ALIGNED (new names)
    "ExpandingL1Config",
    "SlidingL2Config",
    "AlignedDualConfig",
    "ExpandingL1Window",
    "SlidingL2Window",
    "AlignedDualWindow",
    "AlignedDualEngine",
    "create_aligned_config",
    # Adaptive config (Tier 1.2)
    "REGIME_TARGETS",
    "STANDARD_L2_CONFIG",
    "REGIME_L2_CONFIG",
    "get_l2_config_for_target",
    "is_regime_target",
    # Validators (Tier 1.1, 1.3)
    "ClassBalanceMetrics",
    "LookaheadMetrics",
    "compute_class_entropy",
    "compute_purge_gap",
    "validate_class_balance",
    "validate_no_lookahead",
    "validate_training_window",
    # Backward compatibility (old names)
    "Layer1Config",
    "Layer2Config",
    "DualLayerConfig",
    "Layer1Window",
    "Layer2Window",
    "DualLayerWindow",
    "DualLayerEngine",
    "create_dual_config",
    "DEFAULT_DUAL_CONFIGS",
]
