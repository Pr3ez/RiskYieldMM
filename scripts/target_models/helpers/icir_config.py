"""
ICIR (Information Coefficient Information Ratio) Configuration.

This module defines the configuration for Rolling ICIR feature selection
and correlation filtering in the helper ensemble.

The ICIR approach:
1. Computes IC in rolling windows (not single window)
2. ICIR = mean(IC) / std(IC) - measures signal CONSISTENCY
3. High ICIR = feature is predictive AND stable across time
4. Correlation filter removes redundant features (mRMR principle)

Configuration is kept separate for:
- Easy modification without touching ensemble logic
- Per-target customization if needed
- Clear documentation of all tunable parameters

Research basis:
- ICIR threshold 0.3-0.6 is favorable (Li et al 2024)
- Correlation threshold 0.90 balances redundancy removal vs info loss
- 5 rolling windows provides robust stability estimate

Usage:
    from scripts.target_models.helpers.icir_config import (
        ICIRConfig,
        DEFAULT_ICIR_CONFIG,
    )

    # Use defaults
    config = DEFAULT_ICIR_CONFIG

    # Custom config for specific target
    config = ICIRConfig(
        icir_threshold=0.4,
        correlation_threshold=0.85,
    )
"""

from dataclasses import dataclass
from typing import Literal


@dataclass
class ICIRConfig:
    """Configuration for ICIR-based feature selection.

    All parameters are tunable. Change one at a time to understand impact.

    Attributes:
        enable_icir: Master switch for ICIR computation (vs simple IC)
        enable_correlation_filter: Whether to remove highly correlated features

        icir_threshold: Minimum ICIR to keep feature (0.3 = moderate consistency)
            - 0.2: Lenient, keeps more features
            - 0.3: Balanced (default)
            - 0.5: Strict, keeps only very consistent features

        n_rolling_windows: Number of windows for ICIR computation
            - 3: Minimum for stability estimate
            - 5: Default, good balance
            - 10: More robust but needs more data

        min_window_size: Minimum samples per rolling window
            - 50: Works with 250+ total samples
            - 100: More reliable IC estimates
            - 200: Conservative, needs 1000+ samples

        min_valid_windows: Minimum windows with valid IC to compute ICIR
            - 2: Lenient
            - 3: Default (60% of 5 windows)
            - n_rolling_windows: Require all windows valid

        correlation_threshold: Max correlation before one feature dropped
            - 0.80: Aggressive deduplication
            - 0.90: Balanced (default)
            - 0.95: Conservative, keeps more features

        correlation_method: How to compute correlation
            - "pearson": Linear correlation (default)
            - "spearman": Rank correlation (robust to outliers)

        fallback_to_ic: If ICIR fails, fall back to simple IC selection
        fallback_ic_threshold: IC threshold for fallback (legacy behavior)

        top_k_interactions: Number of top features for interaction terms

        verbose: Print debug info during selection
    """

    # Master switches
    enable_icir: bool = True
    enable_correlation_filter: bool = True

    # ICIR computation
    icir_threshold: float = 0.3  # ICIR = mean(IC)/std(IC), 0.3 = moderate
    n_rolling_windows: int = 5
    min_window_size: int = 50  # Per window, so need 250+ total
    min_valid_windows: int = 3  # At least 3 of 5 windows must have valid IC

    # Correlation filtering
    correlation_threshold: float = 0.90
    correlation_method: Literal["pearson", "spearman"] = "pearson"

    # Fallback behavior
    fallback_to_ic: bool = True
    fallback_ic_threshold: float = 0.02  # Legacy IC_THRESHOLD

    # Interactions
    top_k_interactions: int = 5

    # Debugging
    verbose: bool = False

    def __post_init__(self):
        """Validate configuration."""
        if self.icir_threshold < 0:
            raise ValueError("icir_threshold must be >= 0")
        if self.n_rolling_windows < 2:
            raise ValueError("n_rolling_windows must be >= 2")
        if self.min_valid_windows > self.n_rolling_windows:
            raise ValueError("min_valid_windows cannot exceed n_rolling_windows")
        if not 0 < self.correlation_threshold <= 1:
            raise ValueError("correlation_threshold must be in (0, 1]")

    @property
    def min_samples_required(self) -> int:
        """Minimum samples needed for ICIR computation."""
        return self.n_rolling_windows * self.min_window_size

    def for_small_data(self) -> "ICIRConfig":
        """Return adjusted config for small datasets (<500 samples)."""
        return ICIRConfig(
            enable_icir=self.enable_icir,
            enable_correlation_filter=self.enable_correlation_filter,
            icir_threshold=self.icir_threshold,
            n_rolling_windows=3,  # Fewer windows
            min_window_size=30,  # Smaller windows
            min_valid_windows=2,  # Lower requirement
            correlation_threshold=self.correlation_threshold,
            correlation_method=self.correlation_method,
            fallback_to_ic=True,  # Always allow fallback
            fallback_ic_threshold=self.fallback_ic_threshold,
            top_k_interactions=self.top_k_interactions,
            verbose=self.verbose,
        )

    def for_large_data(self) -> "ICIRConfig":
        """Return adjusted config for large datasets (>2000 samples)."""
        return ICIRConfig(
            enable_icir=self.enable_icir,
            enable_correlation_filter=self.enable_correlation_filter,
            icir_threshold=self.icir_threshold,
            n_rolling_windows=7,  # More windows
            min_window_size=100,  # Larger windows
            min_valid_windows=5,  # Higher requirement
            correlation_threshold=self.correlation_threshold,
            correlation_method=self.correlation_method,
            fallback_to_ic=self.fallback_to_ic,
            fallback_ic_threshold=self.fallback_ic_threshold,
            top_k_interactions=self.top_k_interactions,
            verbose=self.verbose,
        )

    def with_strict_filtering(self) -> "ICIRConfig":
        """Return config with stricter thresholds (fewer features)."""
        return ICIRConfig(
            enable_icir=self.enable_icir,
            enable_correlation_filter=True,
            icir_threshold=0.5,  # Stricter
            n_rolling_windows=self.n_rolling_windows,
            min_window_size=self.min_window_size,
            min_valid_windows=self.min_valid_windows,
            correlation_threshold=0.80,  # More aggressive dedup
            correlation_method=self.correlation_method,
            fallback_to_ic=self.fallback_to_ic,
            fallback_ic_threshold=self.fallback_ic_threshold,
            top_k_interactions=self.top_k_interactions,
            verbose=self.verbose,
        )

    def with_lenient_filtering(self) -> "ICIRConfig":
        """Return config with lenient thresholds (more features)."""
        return ICIRConfig(
            enable_icir=self.enable_icir,
            enable_correlation_filter=self.enable_correlation_filter,
            icir_threshold=0.2,  # More lenient
            n_rolling_windows=self.n_rolling_windows,
            min_window_size=self.min_window_size,
            min_valid_windows=2,  # Lower requirement
            correlation_threshold=0.95,  # Keep more features
            correlation_method=self.correlation_method,
            fallback_to_ic=self.fallback_to_ic,
            fallback_ic_threshold=self.fallback_ic_threshold,
            top_k_interactions=self.top_k_interactions,
            verbose=self.verbose,
        )

    def disabled(self) -> "ICIRConfig":
        """Return config with ICIR disabled (legacy IC behavior)."""
        return ICIRConfig(
            enable_icir=False,
            enable_correlation_filter=False,
            icir_threshold=self.icir_threshold,
            n_rolling_windows=self.n_rolling_windows,
            min_window_size=self.min_window_size,
            min_valid_windows=self.min_valid_windows,
            correlation_threshold=self.correlation_threshold,
            correlation_method=self.correlation_method,
            fallback_to_ic=True,
            fallback_ic_threshold=self.fallback_ic_threshold,
            top_k_interactions=self.top_k_interactions,
            verbose=self.verbose,
        )


# Default configuration - balanced for typical use case
DEFAULT_ICIR_CONFIG = ICIRConfig()

# Pre-configured variants for common scenarios
ICIR_CONFIG_STRICT = DEFAULT_ICIR_CONFIG.with_strict_filtering()
ICIR_CONFIG_LENIENT = DEFAULT_ICIR_CONFIG.with_lenient_filtering()
ICIR_CONFIG_SMALL_DATA = DEFAULT_ICIR_CONFIG.for_small_data()
ICIR_CONFIG_LARGE_DATA = DEFAULT_ICIR_CONFIG.for_large_data()
ICIR_CONFIG_DISABLED = DEFAULT_ICIR_CONFIG.disabled()


# Target-specific configs (can be customized based on validation results)
TARGET_ICIR_CONFIGS: dict[str, ICIRConfig] = {
    # Default: all targets use DEFAULT_ICIR_CONFIG
    # Override specific targets if needed:
    # "trend_regime": ICIR_CONFIG_LENIENT,  # If trend_regime needs more features
    # "volatility": ICIR_CONFIG_STRICT,     # If volatility is noisy
}


def get_icir_config(target: str, horizon: int) -> ICIRConfig:
    """Get ICIR config for a specific target-horizon.

    First checks for L2-optimized config (if optimization improved performance).
    Then checks target-specific override in TARGET_ICIR_CONFIGS.
    Falls back to default config.

    Args:
        target: Target name (e.g., "volatility", "direction")
        horizon: Forecast horizon (1, 3, 6, 12)

    Returns:
        ICIRConfig for this target-horizon
    """
    # First try L2-optimized config (only if it improved performance)
    try:
        from .optimized_config_loader import (
            get_optimized_icir_config,
            is_config_optimized,
        )

        if is_config_optimized(target, horizon):
            return get_optimized_icir_config(target, horizon)
    except ImportError:
        pass  # Loader not available, continue to fallbacks

    # Check target-specific override
    target_key = f"{target}_{horizon}bar"
    if target_key in TARGET_ICIR_CONFIGS:
        return TARGET_ICIR_CONFIGS[target_key]

    # Check target-only override
    if target in TARGET_ICIR_CONFIGS:
        return TARGET_ICIR_CONFIGS[target]

    # Default
    return DEFAULT_ICIR_CONFIG
