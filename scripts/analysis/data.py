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
    - y_volatility_regime: Binary (0=DECREASE, 1=INCREASE)
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

    # Volatility regime: will volatility INCREASE or DECREASE?
    # Binary: 1 = INCREASE (future_vol > current_vol), 0 = DECREASE
    # Guaranteed ~50/50 balance due to volatility mean-reversion
    VOL_WINDOW = 21
    print(f"  Computing volatility_regime (window={VOL_WINDOW})")

    # Calculate rolling vol and future vol
    rolling_vol = df["rolling_vol_21"]
    future_vol = rolling_vol.shift(-1)  # Shift by 1 bar (horizon=1)

    y_volatility_regime = (
        pl.when(future_vol > rolling_vol)
        .then(pl.lit(1))  # INCREASE
        .otherwise(pl.lit(0))  # DECREASE
        .cast(pl.Int8)
        .alias("y_volatility_regime")
    )
    df = df.with_columns(y_volatility_regime)

    # Triple-Barrier Labels (AFML Ch.3)
    # Uses high/low for accurate barrier touch detection
    print("\nComputing triple-barrier labels...")
    from scripts.analysis.triple_barrier_labels import compute_triple_barrier_labels

    # Need raw OHLC for barrier computation - merge from raw data
    df = df.with_columns(
        [
            raw["RAW_P_high_abs_NN"].alias("_tb_high"),
            raw["RAW_P_low_abs_NN"].alias("_tb_low"),
            raw["RAW_P_close_abs_NN"].alias("_tb_close"),
        ]
    )

    df = compute_triple_barrier_labels(
        df,
        tp_mult=2.0,  # TP = 2 × ATR
        sl_mult=2.0,  # SL = 2 × ATR
        max_bars=3,  # 3 bars = 24h time barrier
        atr_window=21,
        high_col="_tb_high",
        low_col="_tb_low",
        close_col="_tb_close",
        verbose=True,
    )

    # Remove temporary columns
    df = df.drop(["_tb_high", "_tb_low", "_tb_close"])

    # Multi-Class Signal Labels (research-backed)
    # Based on: Dezhkam et al. 2022 (Bayesian tri-state), Lopez de Prado AFML
    print("\nComputing multi-class signal labels...")
    from scripts.analysis.signal_labels import (
        LABEL_NAMES_3C,
        LABEL_NAMES_5C,
        LabelingConfig,
        add_signal_labels_to_df,
    )

    # Convert to pandas for signal labeling (uses adaptive threshold)
    df_pd = df.to_pandas()
    label_config = LabelingConfig(
        threshold_sigma=0.5,  # 0.5σ threshold for neutrality
        min_threshold=0.005,  # 0.5% minimum
        max_threshold=0.05,  # 5% maximum
        vol_lookback=21,
        use_triple_barrier=True,
    )

    df_pd = add_signal_labels_to_df(
        df_pd,
        config=label_config,
        schemes=["3class", "5class", "4class"],
        return_col="y_tb_return",
        barrier_col="y_tb_barrier",
    )

    # Show distribution
    for scheme, names in [
        ("y_signal_3c", LABEL_NAMES_3C),
        ("y_signal_5c", LABEL_NAMES_5C),
    ]:
        counts = df_pd[scheme].value_counts().sort_index()
        print(f"  {scheme}:")
        for label, count in counts.items():
            pct = count / len(df_pd) * 100
            name = names.get(label, f"Class {label}")
            print(f"    {name}: {count:,} ({pct:.1f}%)")

    # Convert back to polars
    df = pl.from_pandas(df_pd)

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
