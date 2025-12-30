"""
Validation Module for Target Models
====================================

Provides:
- L1 feature precomputation (speed up backtesting)
- Fast backtesting with precomputed features
- Strategy performance metrics
- Deployment validation checks
- Statistical validation (DSR, regime metrics)
"""

from scripts.target_models.validation.fast_backtest import (
    BacktestConfig,
    BacktestResult,
    FastBacktester,
)
from scripts.target_models.validation.l1_precompute import (
    L1PrecomputeConfig,
    PrecomputeMetadata,
    load_precomputed_l1,
    load_precomputed_metadata,
    precompute_all_configs,
    precompute_l1_for_config,
)
from scripts.target_models.validation.statistical_metrics import (
    DeflatedSharpeResult,
    RegimeMetrics,
    benjamini_hochberg_correction,
    bonferroni_correction,
    compute_deflated_sharpe_ratio,
    compute_regime_metrics,
    compute_sharpe_ratio,
    summarize_regime_metrics,
    validate_strategy_statistically,
)

__all__ = [
    # L1 precomputation
    "precompute_l1_for_config",
    "precompute_all_configs",
    "load_precomputed_l1",
    "load_precomputed_metadata",
    "L1PrecomputeConfig",
    "PrecomputeMetadata",
    # Fast backtesting
    "FastBacktester",
    "BacktestConfig",
    "BacktestResult",
    # Statistical metrics
    "compute_sharpe_ratio",
    "compute_deflated_sharpe_ratio",
    "DeflatedSharpeResult",
    "compute_regime_metrics",
    "RegimeMetrics",
    "summarize_regime_metrics",
    "bonferroni_correction",
    "benjamini_hochberg_correction",
    "validate_strategy_statistically",
]
