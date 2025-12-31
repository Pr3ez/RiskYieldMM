"""
Data Loading and Target Generation
==================================

Centralized data operations:
- Load features and raw data
- Generate targets (direction, volatility, forward returns)
- Create analysis-ready dataset
"""

from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl

from . import config


def load_features() -> pl.DataFrame:
    """Load computed features."""
    return pl.read_parquet(config.FEATURES_FILE)


def load_raw() -> pl.DataFrame:
    """Load raw merged data."""
    return pl.read_parquet(config.RAW_FILE)


def load_analysis_data(as_pandas: bool = True) -> pd.DataFrame | pl.DataFrame:
    """
    Load analysis dataset with features and targets.

    If analysis file doesn't exist, creates it.

    Args:
        as_pandas: Return pandas DataFrame (default) or polars

    Returns:
        DataFrame with features, targets, and metadata
    """
    if not config.ANALYSIS_FILE.exists():
        print("Analysis file not found. Creating...")
        create_analysis_dataset()

    df = pl.read_parquet(config.ANALYSIS_FILE)

    if as_pandas:
        pdf = df.to_pandas()
        pdf = pdf.set_index("timestamp")
        return pdf
    return df


def get_feature_columns(df: pd.DataFrame | pl.DataFrame) -> list[str]:
    """Get list of feature columns (exclude targets and meta)."""
    cols = df.columns if isinstance(df, pl.DataFrame) else list(df.columns)
    return [
        c for c in cols if not c.startswith(("y_", "RAW_", "rolling_", "timestamp"))
    ]


def get_target_columns() -> list[str]:
    """Get list of target column names."""
    return config.TARGET_COLS.copy()


def create_analysis_dataset(
    features_file: Path | None = None,
    raw_file: Path | None = None,
    output_file: Path | None = None,
) -> pl.DataFrame:
    """
    Create unified analysis dataset with all targets.

    Generates:
    - y_direction: Binary (1=up, 0=down)
    - y_volatility: |forward_return|
    - y_forward_return_{1,3,6,12}: Multi-horizon returns
    - y_vol_regime: LOW/MEDIUM/HIGH (0/1/2)
    - y_trend_regime: Binary (SMA crossover)

    Returns:
        Combined DataFrame saved to analysis_8h.parquet
    """
    features_file = features_file or config.FEATURES_FILE
    raw_file = raw_file or config.RAW_FILE
    output_file = output_file or config.ANALYSIS_FILE

    print("Loading data...")
    features = pl.read_parquet(features_file)
    raw = pl.read_parquet(raw_file)

    print(f"Features: {features.shape}")
    print(f"Raw: {raw.shape}")

    # Verify alignment
    features_ts = features["timestamp"]
    raw_ts = raw["RAW_TM_timestamp"]
    assert features_ts.equals(raw_ts), "Timestamp mismatch!"
    print("✓ Timestamps aligned")

    # Get OHLC prices
    close = raw["RAW_P_close_abs_NN"]
    high = raw["RAW_P_high_abs_NN"]
    low = raw["RAW_P_low_abs_NN"]

    # Compute forward returns (close-to-close, used for volatility)
    print("\nComputing forward returns...")
    forward_returns = {}
    for horizon, label in config.FORWARD_HORIZONS.items():
        future_close = close.shift(-horizon)
        fwd_ret = (future_close - close) / close
        col_name = f"y_forward_return_{horizon}"
        forward_returns[col_name] = fwd_ret

        valid = fwd_ret.drop_nulls()
        print(f"  {col_name} ({label}): mean={valid.mean():.4%}, std={valid.std():.4%}")

    # Net candle return for direction (up_move - down_move)
    # Uses full candle info (high, low) for better signal
    future_high_1 = high.shift(-1)
    future_low_1 = low.shift(-1)
    up_move_1 = (future_high_1 - close) / close
    down_move_1 = (close - future_low_1) / close
    net_candle_ret_1 = up_move_1 - down_move_1

    # Primary targets
    # y_direction uses NET CANDLE method (up_move > down_move)
    y_direction = (net_candle_ret_1 > 0).cast(pl.Int8).alias("y_direction")
    # y_volatility still uses close-to-close (absolute movement)
    y_forward_1 = forward_returns["y_forward_return_1"]
    y_volatility = y_forward_1.abs().alias("y_volatility")
    y_direction_strength = y_forward_1.abs().alias("y_direction_strength")

    # Regime targets
    log_returns = (close / close.shift(1)).log()
    rolling_vol = log_returns.rolling_std(21).alias("rolling_vol_21")

    sma_21 = close.rolling_mean(21)
    sma_63 = close.rolling_mean(63)
    y_trend_regime = (sma_21 > sma_63).cast(pl.Int8).alias("y_trend_regime")

    # Build combined dataframe
    df = features.clone()

    for col_name, col_data in forward_returns.items():
        df = df.with_columns(col_data.alias(col_name))

    df = df.with_columns(
        [
            y_direction,
            y_volatility,
            y_direction_strength,
            rolling_vol,
            y_trend_regime,
        ]
    )

    df = df.with_columns(close.alias("RAW_close"))

    # Volatility regime (fixed historical thresholds)
    # Use first WARMUP_PERIOD bars to compute thresholds (avoids future data leakage)
    WARMUP_PERIOD = 1000
    warmup_vol = df["rolling_vol_21"].head(WARMUP_PERIOD).drop_nulls()
    vol_25 = warmup_vol.quantile(0.25)
    vol_75 = warmup_vol.quantile(0.75)
    print(
        f"  Volatility thresholds (from first {WARMUP_PERIOD} bars): 25%={vol_25:.6f}, 75%={vol_75:.6f}"
    )

    y_vol_regime = (
        pl.when(df["rolling_vol_21"] < vol_25)
        .then(pl.lit(0))
        .when(df["rolling_vol_21"] < vol_75)
        .then(pl.lit(1))
        .otherwise(pl.lit(2))
        .cast(pl.Int8)
        .alias("y_vol_regime")
    )
    df = df.with_columns(y_vol_regime)

    # Save
    print(f"\nSaving to {output_file}...")
    df.write_parquet(output_file)
    print(
        f"✓ Shape: {df.shape}, Size: {output_file.stat().st_size / 1024 / 1024:.2f} MB"
    )

    return df


def compute_sample_weights(n_samples: int, half_life: int | None = None) -> np.ndarray:
    """
    Compute half-life sample weights for temporal weighting.

    Args:
        n_samples: Number of samples
        half_life: Half-life in bars (default from config)

    Returns:
        Weight array with most recent sample having weight 1.0
    """
    half_life = half_life or config.MODEL_CONFIG.half_life_bars
    min_weight = config.MODEL_CONFIG.min_sample_weight

    decay_rate = np.log(2) / half_life
    weights = np.exp(-decay_rate * np.arange(n_samples)[::-1])
    weights = weights / weights.max()
    weights = np.maximum(weights, min_weight)

    return weights
