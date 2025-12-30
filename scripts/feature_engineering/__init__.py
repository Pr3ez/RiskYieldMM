"""
RiskYieldMM Feature Engineering Package
=======================================

Scripts for computing, validating, and analyzing features.

Usage:
    python -m feature_engineering.compute_features --analyze

Or:
    from feature_engineering.compute_features import compute_all_features, load_raw_data
"""

from .compute_features import (
    compute_all_features,
    compute_atr,
    compute_atr_pct,
    compute_basis,
    compute_body_size,
    compute_candle_direction,
    compute_funding_cumulative,
    compute_funding_ma,
    compute_funding_ma_diff,
    compute_funding_zscore,
    # Individual feature functions
    compute_log_return,
    compute_lower_shadow,
    compute_mark_index_spread,
    compute_mom_atr,
    compute_oi_pct_change,
    compute_oi_ratio,
    compute_oi_roc,
    compute_pct_b,
    compute_ppo,
    compute_premium_ma,
    compute_premium_zscore,
    compute_price_ema_deviation,
    compute_price_sma_deviation,
    compute_return_std,
    compute_roc,
    compute_roc_accel,
    compute_rsi,
    compute_stochastic_d,
    compute_stochastic_k,
    compute_upper_shadow,
    compute_vol_oi_ratio,
    compute_volume_ratio,
    compute_volume_roc,
    load_raw_data,
)

__version__ = "1.0.0"
__all__ = [
    "load_raw_data",
    "compute_all_features",
]
