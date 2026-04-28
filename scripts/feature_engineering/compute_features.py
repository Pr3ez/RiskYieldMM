"""
Feature Engineering Script for RiskYieldMM
==========================================
Computes all 67 approved features from Part 3 documentation.

Usage:
    python compute_features.py                    # Compute features only
    python compute_features.py --validate         # Compute + validate against docs
    python compute_features.py --analyze          # Compute + full statistical analysis
    python compute_features.py --export output.parquet  # Export computed features

Features are computed from 8h Bybit BTCUSDT perpetual data.
All features follow naming convention: [groups]_featureName_[form]_[norm]

Feature Categories (67 total):
- Momentum & Price: 9 features (logReturn, roc, momAtr)
- Volatility: 10 features (atrPct, returnStd, bollingerBandwidth)
- Normalized Price Position: 4 features (pctB)
- Trend: 10 features (ppo, priceSmaDeviation, priceEmaDeviation)
- Funding: 11 features (cumulative, MA, diff, zscore)
- Premium: 7 features (MA, zscore, change, range)
- Spread: 2 features (basis, markIndexSpread)
- Open Interest: 11 features (pctChange, ratio, roc, volumeRatio)
- Candlestick: 4 features (bodySize, shadows, direction)
- Oscillators: 7 features (rsi, stochastic K/D)
- Volume: 6 features (roc, ratio)
- Momentum Acceleration: 2 features (rocAccel)
- VWAP: 2 features (deviation, return)
- OI Composite: 1 feature (oiWeightedReturn)
- Temporal: 2 features (fundingCyclePosition, dayOfWeek)
- Mark Price: 9 features (deviation, atrRatio, range, returnDiff, vol)
- Volatility Regime: 8 features (atrPercentile, rangeExpansion, volOfVol, premiumRange)
- Distribution Shape: 6 features (skew, kurtosis)
- Risk Management: 8 features (maxDrawdown, sharpe, sortino, calmar)
- Regime Detection: 8 features (autocorr, zScore, volMomentum)
- Momentum Quality: 5 features (consecutiveUp/Down, winRate)
- Volume-Price: 8 features (obv, mfi, cmf)
- Trend Strength: 7 features (adx, diDiff, cci)
- Perpetual Composite: 3 features (oiVolumeRatio)

Author: P. Augustyniak
RiskYieldMM Project
Created: 2025-12-20
Updated: 2025-12-21 (added 31 new features from research batch)
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

# =============================================================================
# DATA LOADING
# =============================================================================


def load_raw_data(data_dir: Path) -> pd.DataFrame:
    """Load and merge all raw data sources."""

    # OHLCV data
    ohlcv = pd.read_parquet(data_dir / "sorted-8h-bybit-linear/btcusdt_8h.parquet")

    # Open Interest
    oi = pd.read_parquet(
        data_dir / "open-interest-8h-bybit-linear/btcusdt_open_interest_8h.parquet"
    )

    # Mark Price
    mark = pd.read_parquet(
        data_dir / "mark-price-8h-bybit-linear/btcusdt_mark_price_8h.parquet"
    )
    mark = mark.rename(
        columns={
            "close": "markClose",
            "open": "markOpen",
            "high": "markHigh",
            "low": "markLow",
        }
    )

    # Index Price
    index = pd.read_parquet(
        data_dir / "index-price-8h-bybit-linear/btcusdt_index_price_8h.parquet"
    )
    index = index.rename(
        columns={
            "close": "indexClose",
            "open": "indexOpen",
            "high": "indexHigh",
            "low": "indexLow",
        }
    )

    # Premium
    premium = pd.read_parquet(
        data_dir / "premium-price-8h-bybit-linear/btcusdt_premium_price_8h.parquet"
    )
    premium = premium.rename(
        columns={
            "open": "premiumOpen",
            "high": "premiumHigh",
            "low": "premiumLow",
            "close": "premiumClose",
        }
    )

    # Funding Rate
    funding = pd.read_parquet(
        data_dir / "funding-rate-bybit-linear/btcusdt_funding_rate.parquet"
    )

    # Long/Short Ratio
    ls_ratio = pd.read_parquet(
        data_dir / "long-short-ratio-8h-bybit-linear/btcusdt_ls_ratio.parquet"
    )
    # Compute longShortRatio = buyRatio / sellRatio
    ls_ratio["longShortRatio"] = ls_ratio["buyRatio"] / ls_ratio["sellRatio"]

    # Merge all data
    df = ohlcv.copy()
    df = df.merge(oi[["timestamp", "openInterest"]], on="timestamp", how="left")
    df = df.merge(mark[["timestamp", "markClose"]], on="timestamp", how="left")
    df = df.merge(index[["timestamp", "indexClose"]], on="timestamp", how="left")
    df = df.merge(
        premium[
            ["timestamp", "premiumOpen", "premiumHigh", "premiumLow", "premiumClose"]
        ],
        on="timestamp",
        how="left",
    )
    df = df.merge(funding[["timestamp", "fundingRate"]], on="timestamp", how="left")
    df = df.merge(ls_ratio[["timestamp", "longShortRatio"]], on="timestamp", how="left")

    # Sort by timestamp
    df = df.sort_values("timestamp").reset_index(drop=True)
    if "longShortRatio" in df.columns:
        ratio = df["longShortRatio"].replace([np.inf, -np.inf], np.nan)
        # Long/short ratio is strictly positive; zeros/non-positive values are
        # treated as missing and causally forward-filled from the last valid
        # observation.
        df["longShortRatio"] = ratio.mask(ratio <= 0, np.nan).ffill()

    return df


# =============================================================================
# FEATURE COMPUTATION - MOMENTUM & PRICE
# =============================================================================


def compute_log_return(df: pd.DataFrame) -> pd.Series:
    """M_P_logReturn_pct_N: ln(close_t / close_{t-1})"""
    return np.log(df["close"] / df["close"].shift(1))


def compute_roc(df: pd.DataFrame, n: int) -> pd.Series:
    """M_P_roc_{n}_pct_N: (close_t - close_{t-n}) / close_{t-n}"""
    return (df["close"] - df["close"].shift(n)) / df["close"].shift(n)


def compute_atr(df: pd.DataFrame, n: int) -> pd.Series:
    """Compute ATR (helper function)."""
    tr = np.maximum(
        df["high"] - df["low"],
        np.maximum(
            abs(df["high"] - df["close"].shift(1)),
            abs(df["low"] - df["close"].shift(1)),
        ),
    )
    return tr.ewm(span=n, adjust=False).mean()


def compute_mom_atr(df: pd.DataFrame, n: int) -> pd.Series:
    """M_P_V_momAtr_{n}_rat_N: (close_t - close_{t-n}) / ATR(n)"""
    atr = compute_atr(df, n)
    return (df["close"] - df["close"].shift(n)) / atr


# =============================================================================
# FEATURE COMPUTATION - VOLATILITY
# =============================================================================


def compute_atr_pct(df: pd.DataFrame, n: int) -> pd.Series:
    """V_atrPct_{n}_pct_N: ATR(n) / close_t"""
    atr = compute_atr(df, n)
    return atr / df["close"]


def compute_return_std(df: pd.DataFrame, n: int) -> pd.Series:
    """V_returnStd_{n}_pct_N: std(log_returns) over n periods"""
    log_returns = np.log(df["close"] / df["close"].shift(1))
    return log_returns.rolling(n).std()


# =============================================================================
# FEATURE COMPUTATION - NORMALIZED PRICE POSITION
# =============================================================================


def compute_pct_b(df: pd.DataFrame, n: int) -> pd.Series:
    """N_P_V_pctB_{n}_bnd_N: (close - BBAND-) / (BBAND+ - BBAND-)"""
    sma = df["close"].rolling(n).mean()
    std = df["close"].rolling(n).std()
    bband_upper = sma + 2 * std
    bband_lower = sma - 2 * std
    return (df["close"] - bband_lower) / (bband_upper - bband_lower)


def compute_bollinger_bandwidth(df: pd.DataFrame, n: int) -> pd.Series:
    """N_V_bollingerBandwidth_{n}_pct_N: (BBAND+ - BBAND-) / SMA(n)

    Measures volatility as width of Bollinger Bands normalized by price.
    Low bandwidth (squeeze) often precedes breakouts.
    Used for regime/context detection, not ML prediction.
    """
    sma = df["close"].rolling(n).mean()
    std = df["close"].rolling(n).std()
    bband_upper = sma + 2 * std
    bband_lower = sma - 2 * std
    return (bband_upper - bband_lower) / sma


# =============================================================================
# FEATURE COMPUTATION - TREND
# =============================================================================


def compute_ppo(df: pd.DataFrame, short: int, long: int) -> pd.Series:
    """M_T_ppo_{s}_{l}_pct_N: (EMA(short) - EMA(long)) / EMA(long) * 100"""
    ema_short = df["close"].ewm(span=short, adjust=False).mean()
    ema_long = df["close"].ewm(span=long, adjust=False).mean()
    return (ema_short - ema_long) / ema_long * 100


def compute_price_sma_deviation(df: pd.DataFrame, n: int) -> pd.Series:
    """N_P_T_priceSmaDeviation_{n}_pct_N: (close - SMA(n)) / SMA(n)"""
    sma = df["close"].rolling(n).mean()
    return (df["close"] - sma) / sma


def compute_price_ema_deviation(df: pd.DataFrame, n: int) -> pd.Series:
    """N_P_T_priceEmaDeviation_{n}_pct_N: (close - EMA(n)) / EMA(n)"""
    ema = df["close"].ewm(span=n, adjust=False).mean()
    return (df["close"] - ema) / ema


# =============================================================================
# FEATURE COMPUTATION - FUNDING
# =============================================================================


def compute_funding_cumulative(df: pd.DataFrame, n: int) -> pd.Series:
    """F_I_fundingCumulative_{n}_pct_N: sum(fundingRate) over n periods"""
    return df["fundingRate"].rolling(n, min_periods=1).sum()


def compute_funding_ma(df: pd.DataFrame, n: int) -> pd.Series:
    """F_I_T_fundingMa_{n}_pct_N: mean(fundingRate) over n periods"""
    return df["fundingRate"].rolling(n, min_periods=1).mean()


def compute_funding_ma_diff(df: pd.DataFrame, short: int, long: int) -> pd.Series:
    """F_I_M_fundingMaDiff_{s}_{l}_pct_N: fundingMa(short) - fundingMa(long)"""
    ma_short = df["fundingRate"].rolling(short, min_periods=1).mean()
    ma_long = df["fundingRate"].rolling(long, min_periods=1).mean()
    return ma_short - ma_long


def compute_funding_zscore(df: pd.DataFrame, n: int) -> pd.Series:
    """F_I_N_S_fundingZscore_{n}_zsc_N: (fundingRate - mean) / std"""
    mu = df["fundingRate"].rolling(n).mean()
    sigma = df["fundingRate"].rolling(n).std(ddof=0)
    zscore = (df["fundingRate"] - mu) / sigma
    # Handle edge case: constant funding -> z=0
    zscore = zscore.where(sigma.abs() > 1e-8, 0.0)
    return zscore


# =============================================================================
# FEATURE COMPUTATION - PREMIUM
# =============================================================================


def compute_premium_ma(df: pd.DataFrame, n: int) -> pd.Series:
    """D_F_T_premiumMa_{n}_pct_N: mean(premiumClose) over n periods"""
    return df["premiumClose"].rolling(n, min_periods=1).mean()


def compute_premium_zscore(df: pd.DataFrame, n: int) -> pd.Series:
    """D_F_N_S_premiumZscore_{n}_zsc_N: (premiumClose - mean) / std"""
    mu = df["premiumClose"].rolling(n).mean()
    sigma = df["premiumClose"].rolling(n).std(ddof=0)
    zscore = (df["premiumClose"] - mu) / sigma
    zscore = zscore.where(sigma.abs() > 1e-8, 0.0)
    return zscore


# =============================================================================
# FEATURE COMPUTATION - SPREAD
# =============================================================================


def compute_basis(df: pd.DataFrame) -> pd.Series:
    """D_F_basis_pct_N: (futuresClose - indexClose) / indexClose"""
    return (df["close"] - df["indexClose"]) / df["indexClose"]


def compute_mark_index_spread(df: pd.DataFrame) -> pd.Series:
    """D_markIndexSpread_pct_N: (markClose - indexClose) / indexClose"""
    return (df["markClose"] - df["indexClose"]) / df["indexClose"]


# =============================================================================
# FEATURE COMPUTATION - OPEN INTEREST
# =============================================================================


def compute_oi_pct_change(df: pd.DataFrame) -> pd.Series:
    """L_M_N_S_oiPctChange_pct_N: (OI_t - OI_{t-1}) / OI_{t-1}"""
    return (df["openInterest"] - df["openInterest"].shift(1)) / df[
        "openInterest"
    ].shift(1)


def compute_vol_oi_ratio(df: pd.DataFrame) -> pd.Series:
    """L_N_volOiRatio_rat_N: volume / openInterest"""
    return df["volume"] / df["openInterest"]


def compute_oi_roc(df: pd.DataFrame, n: int) -> pd.Series:
    """L_M_N_S_oiRoc_{n}_pct_N: (OI_t - OI_{t-n}) / OI_{t-n}"""
    return (df["openInterest"] - df["openInterest"].shift(n)) / df[
        "openInterest"
    ].shift(n)


def compute_oi_ratio(df: pd.DataFrame, n: int) -> pd.Series:
    """L_N_S_oiRatio_{n}_rat_N: openInterest / SMA(openInterest, n)"""
    sma = df["openInterest"].rolling(n).mean()
    return df["openInterest"] / sma


# =============================================================================
# FEATURE COMPUTATION - CANDLESTICK
# =============================================================================


def compute_body_size(df: pd.DataFrame) -> pd.Series:
    """C_N_bodySize_bnd_N: |close - open| / (high - low)"""
    range_ = df["high"] - df["low"]
    ratio = abs(df["close"] - df["open"]) / range_.replace(0, np.nan)
    # A zero-range candle is flat by definition; emit 0 instead of NaN so
    # complete batches stay model-ready without using any future information.
    return ratio.mask(range_.eq(0), 0.0)


def compute_upper_shadow(df: pd.DataFrame) -> pd.Series:
    """C_N_upperShadow_bnd_N: (high - max(open, close)) / (high - low)"""
    range_ = df["high"] - df["low"]
    ratio = (df["high"] - np.maximum(df["open"], df["close"])) / range_.replace(0, np.nan)
    return ratio.mask(range_.eq(0), 0.0)


def compute_lower_shadow(df: pd.DataFrame) -> pd.Series:
    """C_N_lowerShadow_bnd_N: (min(open, close) - low) / (high - low)"""
    range_ = df["high"] - df["low"]
    ratio = (np.minimum(df["open"], df["close"]) - df["low"]) / range_.replace(0, np.nan)
    return ratio.mask(range_.eq(0), 0.0)


def compute_candle_direction(df: pd.DataFrame) -> pd.Series:
    """B_C_candleDirection_bin: sign(close - open)"""
    return np.sign(df["close"] - df["open"])


# =============================================================================
# FEATURE COMPUTATION - OSCILLATORS
# =============================================================================


def compute_rsi(df: pd.DataFrame, n: int) -> pd.Series:
    """M_N_rsi_{n}_bnd_N: RSI = 100 - (100 / (1 + RS))"""
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0).rolling(n).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(n).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def compute_stochastic_k(df: pd.DataFrame, n: int) -> pd.Series:
    """M_N_stochasticK_{n}_bnd_N: (close - lowest_low) / (highest_high - lowest_low) * 100"""
    lowest_low = df["low"].rolling(n).min()
    highest_high = df["high"].rolling(n).max()
    range_ = (highest_high - lowest_low).replace(0, np.nan)
    return (df["close"] - lowest_low) / range_ * 100


def compute_stochastic_d(df: pd.DataFrame, n: int, smooth: int = 3) -> pd.Series:
    """M_N_T_stochasticD_{n}_bnd_N: SMA(%K, smooth)"""
    stoch_k = compute_stochastic_k(df, n)
    return stoch_k.rolling(smooth).mean()


# =============================================================================
# FEATURE COMPUTATION - VOLUME
# =============================================================================


def compute_volume_roc(df: pd.DataFrame, n: int) -> pd.Series:
    """L_M_N_volumeRoc_{n}_pct_N: (volume_t - volume_{t-n}) / volume_{t-n}"""
    return (df["volume"] - df["volume"].shift(n)) / df["volume"].shift(n)


def compute_volume_ratio(df: pd.DataFrame, n: int) -> pd.Series:
    """L_N_volumeRatio_{n}_rat_N: volume / SMA(volume, n)"""
    sma = df["volume"].rolling(n).mean()
    return df["volume"] / sma


# =============================================================================
# FEATURE COMPUTATION - MOMENTUM ACCELERATION
# =============================================================================


def compute_roc_accel(df: pd.DataFrame, n: int) -> pd.Series:
    """M_N_rocAccel_{n}_dif_N: ROC_t(n) - ROC_{t-n}(n)"""
    roc = compute_roc(df, n)
    return roc - roc.shift(n)


# =============================================================================
# FEATURE COMPUTATION - VWAP (2025-12-21)
# =============================================================================


def compute_vwap_deviation(df: pd.DataFrame) -> pd.Series:
    """N_P_L_vwapDeviation_pct_N: (close - VWAP) / VWAP where VWAP = turnover / volume"""
    vwap = df["turnover"] / df["volume"]
    return (df["close"] - vwap) / vwap


def compute_vwap_return(df: pd.DataFrame) -> pd.Series:
    """M_P_L_vwapReturn_pct_N: ln(VWAP_t / VWAP_{t-1})"""
    vwap = df["turnover"] / df["volume"]
    return np.log(vwap / vwap.shift(1))


# =============================================================================
# FEATURE COMPUTATION - PREMIUM DYNAMICS (2025-12-21)
# =============================================================================


def compute_premium_change(df: pd.DataFrame) -> pd.Series:
    """M_D_F_S_premiumChange_pct_N: premiumClose - premiumOpen"""
    return df["premiumClose"] - df["premiumOpen"]


def compute_premium_range(df: pd.DataFrame) -> pd.Series:
    """V_D_F_S_premiumRange_pct_N: premiumHigh - premiumLow"""
    return df["premiumHigh"] - df["premiumLow"]


# =============================================================================
# FEATURE COMPUTATION - OI COMPOSITE (2025-12-20)
# =============================================================================


def compute_oi_weighted_return(df: pd.DataFrame) -> pd.Series:
    """M_P_S_W_oiWeightedReturn_pct_N: logReturn × sign(oiPctChange)

    Positive: price and OI moving together (trend continuation signal)
    Negative: price and OI diverging (trend reversal signal)
    """
    log_return = np.log(df["close"] / df["close"].shift(1))
    oi_change = (df["openInterest"] - df["openInterest"].shift(1)) / df[
        "openInterest"
    ].shift(1)
    return log_return * np.sign(oi_change)


# =============================================================================
# FEATURE COMPUTATION - TEMPORAL (2025-12-20)
# =============================================================================


def compute_funding_cycle_position(df: pd.DataFrame) -> pd.Series:
    """F_TM_fundingCyclePosition_bin: hour_in_day / 8 (which 8h funding cycle)

    Bybit funding: 00:00, 08:00, 16:00 UTC
    Returns 0, 1, or 2 indicating which cycle we're in.
    """
    return (df["timestamp"].dt.hour // 8).astype(int)


def compute_day_of_week(df: pd.DataFrame) -> pd.Series:
    """B_TM_dayOfWeek_bin: day of week (0=Mon, 6=Sun)"""
    return df["timestamp"].dt.dayofweek


# =============================================================================
# FEATURE COMPUTATION - MARK PRICE (2025-12-20)
# =============================================================================


def compute_mark_close_deviation(df: pd.DataFrame) -> pd.Series:
    """D_N_markCloseDeviation_pct_N: (close - markClose) / markClose

    How much futures trades away from mark price.
    Large deviations = aggressive positioning.
    """
    return (df["close"] - df["markClose"]) / df["markClose"]


def compute_mark_atr_ratio(df: pd.DataFrame, n: int) -> pd.Series:
    """D_N_V_markAtrRatio_{n}_rat_N: ATR(mark) / ATR(close)

    >1: Mark price more volatile (arbitrage activity)
    <1: Close price more volatile (retail speculation)
    """
    # ATR for close price
    tr_close = np.maximum(
        df["high"] - df["low"],
        np.maximum(
            abs(df["high"] - df["close"].shift(1)),
            abs(df["low"] - df["close"].shift(1)),
        ),
    )
    atr_close = tr_close.ewm(span=n, adjust=False).mean()

    # ATR for mark price (use close for prev since we only have markClose)
    # This is an approximation - markHigh/markLow would be ideal
    mark_range = abs(df["markClose"] - df["markClose"].shift(1))
    atr_mark = mark_range.ewm(span=n, adjust=False).mean()

    return atr_mark / atr_close


def compute_mark_close_range(df: pd.DataFrame) -> pd.Series:
    """D_N_V_markCloseRange_rat_N: |close - markClose| / (high - low)

    Mark-close deviation relative to bar range.
    High values = mark significantly outside close's bar range.
    """
    range_ = (df["high"] - df["low"]).replace(0, np.nan)
    return abs(df["close"] - df["markClose"]) / range_


def compute_mark_return_diff(df: pd.DataFrame) -> pd.Series:
    """M_P_D_markReturnDiff_pct_N: logReturn(close) - logReturn(markClose)

    Difference in return momentum between close and mark.
    """
    log_return_close = np.log(df["close"] / df["close"].shift(1))
    log_return_mark = np.log(df["markClose"] / df["markClose"].shift(1))
    return log_return_close - log_return_mark


def compute_close_vs_mark_vol(df: pd.DataFrame, n: int) -> pd.Series:
    """D_N_closeVsMarkVol_{n}_pct_N: std(close - markClose) / std(close) over n periods

    Relative volatility of close-mark spread vs close price.
    """
    spread = df["close"] - df["markClose"]
    spread_std = spread.rolling(n).std()
    close_std = df["close"].rolling(n).std()
    return spread_std / close_std.replace(0, np.nan)


# =============================================================================
# FEATURE COMPUTATION - VOLATILITY REGIME (2025-12-20)
# =============================================================================


def compute_atr_percentile(df: pd.DataFrame, n: int) -> pd.Series:
    """N_V_atrPercentile_{n}_rnk_N: percentile rank of ATR within lookback

    Bounded [0, 1]. 1.0 = highest volatility in lookback period.
    """
    atr = compute_atr(df, n)
    return atr.rolling(n).rank(pct=True)


def compute_range_expansion(df: pd.DataFrame, n: int) -> pd.Series:
    """M_N_V_rangeExpansion_{n}_rat_N: (high - low) / SMA(high - low, n)

    Current range relative to average range.
    >1 = range expansion, <1 = range contraction.
    """
    range_ = df["high"] - df["low"]
    range_sma = range_.rolling(n).mean()
    return range_ / range_sma


def compute_vol_of_vol(df: pd.DataFrame, n: int) -> pd.Series:
    """V_volOfVol_{n}_pct_N: std(V_returnStd_6, n) / mean(V_returnStd_6, n)

    Volatility of volatility - indicates volatility clustering or regime changes.
    Base volatility window m=6 (fixed), outer window n (variable).
    """
    log_returns = np.log(df["close"] / df["close"].shift(1))
    # Base volatility with fixed window m=6 (per docs)
    return_std = log_returns.rolling(6).std()

    # Outer window n for vol-of-vol
    vol_std = return_std.rolling(n).std()
    vol_mean = return_std.rolling(n).mean()
    return vol_std / vol_mean.replace(0, np.nan)


def compute_premium_range_norm(df: pd.DataFrame) -> pd.Series:
    """D_N_premiumRange_rat_N: premiumRange / atrPct(6)

    Premium volatility relative to price volatility.
    Uses atrPct_6 for normalization (per docs).
    """
    premium_range = df["premiumHigh"] - df["premiumLow"]
    # Use atrPct with n=6 (per docs)
    atr_pct = compute_atr_pct(df, 6)
    return premium_range / atr_pct.replace(0, np.nan)


# =============================================================================
# FEATURE COMPUTATION - DISTRIBUTION SHAPE (2025-12-21)
# =============================================================================


def compute_skew(df: pd.DataFrame, n: int) -> pd.Series:
    """V_skew_{n}_rat_N: rolling skewness of log returns

    >0: right-skewed (fat right tail, positive surprises)
    <0: left-skewed (fat left tail, negative surprises)
    Clip at ±3 for stability.
    """
    log_returns = np.log(df["close"] / df["close"].shift(1))
    skew = log_returns.rolling(n).skew()
    return skew.clip(-3, 3)


def compute_kurtosis(df: pd.DataFrame, n: int) -> pd.Series:
    """V_kurtosis_{n}_rat_N: rolling excess kurtosis of log returns

    >0: fat tails (more extreme moves than normal)
    <0: thin tails (fewer extreme moves)
    Clip at [-3, 10] for stability.
    """
    log_returns = np.log(df["close"] / df["close"].shift(1))
    # pandas kurtosis is excess kurtosis (Fisher's definition)
    kurt = log_returns.rolling(n).kurt()
    return kurt.clip(-3, 10)


# =============================================================================
# FEATURE COMPUTATION - RISK MANAGEMENT (2025-12-21)
# =============================================================================


def compute_max_drawdown(df: pd.DataFrame, n: int) -> pd.Series:
    """V_maxDrawdown_{n}_pct_N: maximum drawdown over n periods

    MaxDD = (trough - peak) / peak
    Always negative or zero. More negative = worse drawdown.
    """

    def rolling_max_dd(window):
        if len(window) < 2:
            return np.nan
        peak = window.expanding().max()
        dd = (window - peak) / peak
        return dd.min()

    return df["close"].rolling(n).apply(rolling_max_dd, raw=False)


def compute_sharpe(df: pd.DataFrame, n: int) -> pd.Series:
    """M_V_sharpe_{n}_rat_N: mean(returns) / std(returns) × sqrt(n) over n periods

    Risk-adjusted return. Higher = better.
    Clip at ±5 for stability.
    """
    log_returns = np.log(df["close"] / df["close"].shift(1))
    mean_ret = log_returns.rolling(n).mean()
    std_ret = log_returns.rolling(n).std()
    sharpe = (mean_ret / std_ret.replace(0, np.nan)) * np.sqrt(n)
    return sharpe.clip(-5, 5)


def compute_sortino(df: pd.DataFrame, n: int) -> pd.Series:
    """M_V_sortino_{n}_rat_N: mean(returns) / downside_std × sqrt(n)

    Like Sharpe but only penalizes downside volatility.
    Clip at ±5 for stability.
    """
    log_returns = np.log(df["close"] / df["close"].shift(1))
    mean_ret = log_returns.rolling(n).mean()

    # Downside deviation - std of negative returns only
    def downside_std(window):
        neg = window[window < 0]
        if len(neg) < 2:
            return np.nan
        return neg.std()

    down_std = log_returns.rolling(n).apply(downside_std, raw=False)
    sortino = (mean_ret / down_std.replace(0, np.nan)) * np.sqrt(n)
    return sortino.clip(-5, 5)


def compute_calmar(df: pd.DataFrame, n: int) -> pd.Series:
    """M_V_calmar_{n}_rat_N: (close_t / close_{t-n} - 1) / |max_drawdown|

    Return per unit of maximum drawdown. Higher = better.
    Clip at ±5 for stability.
    """
    # Simple return over n periods (per docs)
    cum_return = df["close"] / df["close"].shift(n) - 1
    max_dd = compute_max_drawdown(df, n)

    calmar = cum_return / abs(max_dd).replace(0, np.nan)
    return calmar.clip(-5, 5)


# =============================================================================
# FEATURE COMPUTATION - REGIME DETECTION (2025-12-21)
# =============================================================================


def compute_autocorr(df: pd.DataFrame, n: int) -> pd.Series:
    """V_autocorr_{n}_bnd_N: lag-1 autocorrelation of returns over n periods

    >0: trending (momentum)
    <0: mean-reverting
    Bounded [-1, 1] by construction.
    """
    log_returns = np.log(df["close"] / df["close"].shift(1))
    return log_returns.rolling(n).apply(
        lambda x: x.autocorr(lag=1) if len(x) > 1 else np.nan, raw=False
    )


def compute_price_zscore(df: pd.DataFrame, n: int) -> pd.Series:
    """N_P_zScore_{n}_zsc_N: (close - mean(close, n)) / std(close, n)

    How many standard deviations price is from mean.
    Clip at ±4 for stability.
    """
    mean = df["close"].rolling(n).mean()
    std = df["close"].rolling(n).std()
    zscore = (df["close"] - mean) / std.replace(0, np.nan)
    return zscore.clip(-4, 4)


def compute_vol_momentum(df: pd.DataFrame, n: int) -> pd.Series:
    """V_volMomentum_{n}_pct_N: (std(returns, m) / std(returns, m).shift(n)) - 1

    Rate of change of volatility.
    Inner volatility window m = n//2 (per docs: n=6->m=3, n=12->m=6, n=21->m=10)
    >0: volatility increasing, <0: volatility decreasing.
    Clipped to [-1, 15] to handle division by small volatility.
    """
    log_returns = np.log(df["close"] / df["close"].shift(1))
    # Inner window m = n/2 (per docs)
    m = max(n // 2, 2)  # minimum 2 for std calculation
    return_std = log_returns.rolling(m).std()
    vol_mom = (return_std / return_std.shift(n)) - 1
    return vol_mom.clip(-1, 15)


# =============================================================================
# FEATURE COMPUTATION - MOMENTUM QUALITY (2025-12-21)
# =============================================================================


def compute_consecutive_up(df: pd.DataFrame) -> pd.Series:
    """B_consecutiveUp_bnd_N: count of consecutive up bars

    Resets to 0 when bar closes down.
    Bounded [0, 10] for stability.
    """
    direction = (df["close"] > df["close"].shift(1)).astype(int)

    # Count consecutive ups
    def count_consecutive(series):
        result = []
        count = 0
        for val in series:
            if val == 1:
                count += 1
            else:
                count = 0
            result.append(count)
        return pd.Series(result, index=series.index)

    return count_consecutive(direction).clip(0, 10)


def compute_consecutive_down(df: pd.DataFrame) -> pd.Series:
    """B_consecutiveDown_bnd_N: count of consecutive down bars

    Resets to 0 when bar closes up.
    Bounded [0, 10] for stability.
    """
    direction = (df["close"] < df["close"].shift(1)).astype(int)

    def count_consecutive(series):
        result = []
        count = 0
        for val in series:
            if val == 1:
                count += 1
            else:
                count = 0
            result.append(count)
        return pd.Series(result, index=series.index)

    return count_consecutive(direction).clip(0, 10)


def compute_win_rate(df: pd.DataFrame, n: int) -> pd.Series:
    """M_winRate_{n}_bnd_N: count(positive returns) / n over n periods

    Bounded [0, 1]. 0.5 = balanced, >0.5 = bullish bias.
    """
    log_returns = np.log(df["close"] / df["close"].shift(1))
    positive = (log_returns > 0).astype(int)
    return positive.rolling(n).mean()


# =============================================================================
# FEATURE COMPUTATION - VOLUME-PRICE (2025-12-21)
# =============================================================================


def compute_obv(df: pd.DataFrame, n: int) -> pd.Series:
    """L_M_S_obv_{n}_zsc_N: z-scored On-Balance Volume

    OBV = cumsum(sign(return) × volume)
    Then z-scored over n periods for stationarity.
    """
    log_returns = np.log(df["close"] / df["close"].shift(1))
    signed_volume = np.sign(log_returns) * df["volume"]
    obv = signed_volume.cumsum()

    # Z-score for stationarity
    mean = obv.rolling(n).mean()
    std = obv.rolling(n).std()
    return ((obv - mean) / std.replace(0, np.nan)).clip(-4, 4)


def compute_mfi(df: pd.DataFrame, n: int) -> pd.Series:
    """L_M_S_mfi_{n}_bnd_N: Money Flow Index

    Volume-weighted RSI. Bounded [0, 100].
    """
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    raw_money_flow = typical_price * df["volume"]

    tp_diff = typical_price.diff()
    positive_mf = raw_money_flow.where(tp_diff > 0, 0).rolling(n).sum()
    negative_mf = raw_money_flow.where(tp_diff < 0, 0).rolling(n).sum()

    money_ratio = positive_mf / negative_mf.replace(0, np.nan)
    return 100 - (100 / (1 + money_ratio))


def compute_cmf(df: pd.DataFrame, n: int) -> pd.Series:
    """L_M_S_cmf_{n}_bnd_N: Chaikin Money Flow

    Bounded [-1, +1]. Measures buying vs selling pressure.
    """
    # Money Flow Multiplier = ((close - low) - (high - close)) / (high - low)
    range_ = (df["high"] - df["low"]).replace(0, np.nan)
    mf_multiplier = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / range_
    mf_multiplier = mf_multiplier.fillna(0)  # Handle high == low case

    mf_volume = mf_multiplier * df["volume"]

    return mf_volume.rolling(n).sum() / df["volume"].rolling(n).sum()


# =============================================================================
# FEATURE COMPUTATION - TREND STRENGTH (2025-12-21)
# =============================================================================


def compute_adx(df: pd.DataFrame, n: int) -> pd.Series:
    """M_T_V_adx_{n}_bnd_N: Average Directional Index

    Bounded [0, 100]. Measures trend strength regardless of direction.
    <20 = no trend, 25-50 = strong trend, >50 = very strong.
    """
    # True Range
    tr = np.maximum(
        df["high"] - df["low"],
        np.maximum(
            abs(df["high"] - df["close"].shift(1)),
            abs(df["low"] - df["close"].shift(1)),
        ),
    )

    # Directional Movement
    up_move = df["high"] - df["high"].shift(1)
    down_move = df["low"].shift(1) - df["low"]

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)

    plus_dm = pd.Series(plus_dm, index=df.index)
    minus_dm = pd.Series(minus_dm, index=df.index)

    # Smoothed values (Wilder smoothing)
    atr = tr.ewm(span=n, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(span=n, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(span=n, adjust=False).mean() / atr

    # DX and ADX
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.ewm(span=n, adjust=False).mean()

    return adx


def compute_di_diff(df: pd.DataFrame, n: int) -> pd.Series:
    """M_T_V_diDiff_{n}_bnd_N: (+DI - -DI) / 100

    Bounded [-1, +1]. Positive = bullish trend, negative = bearish.
    """
    # Same calculation as ADX but return DI difference
    tr = np.maximum(
        df["high"] - df["low"],
        np.maximum(
            abs(df["high"] - df["close"].shift(1)),
            abs(df["low"] - df["close"].shift(1)),
        ),
    )

    up_move = df["high"] - df["high"].shift(1)
    down_move = df["low"].shift(1) - df["low"]

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)

    plus_dm = pd.Series(plus_dm, index=df.index)
    minus_dm = pd.Series(minus_dm, index=df.index)

    atr = tr.ewm(span=n, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(span=n, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(span=n, adjust=False).mean() / atr

    return (plus_di - minus_di) / 100


def compute_cci(df: pd.DataFrame, n: int) -> pd.Series:
    """N_M_cci_{n}_zsc_N: Commodity Channel Index

    (TP - SMA(TP)) / (0.015 × MeanDeviation)
    Clip at ±300 for stability.
    """
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    sma_tp = typical_price.rolling(n).mean()

    # Mean deviation
    mean_dev = abs(typical_price - sma_tp).rolling(n).mean()

    cci = (typical_price - sma_tp) / (0.015 * mean_dev).replace(0, np.nan)
    return cci.clip(-300, 300)


def compute_oi_volume_ratio(df: pd.DataFrame, n: int) -> pd.Series:
    """L_S_oiVolumeRatio_{n}_rat_N: openInterest / SMA(volume, n)

    Position commitment vs trading activity.
    High = positions held longer (conviction), low = high turnover.
    """
    sma_vol = df["volume"].rolling(n).mean()
    return df["openInterest"] / sma_vol


# =============================================================================
# FEATURE COMPUTATION - LONG/SHORT RATIO (2025-12-22)
# =============================================================================


def compute_long_short_ratio(df: pd.DataFrame) -> pd.Series:
    """S_longShortRatio_rat_N: buyRatio / sellRatio (raw from data)

    Raw positioning signal for regime detection.
    >1 = longs dominate, <1 = shorts dominate.
    Extreme values (>2.0 or <0.7) indicate crowded positioning.

    Academic: Baker & Wurgler (2006), De Long et al. (1990)
    """
    ls = df["longShortRatio"].replace([np.inf, -np.inf], np.nan)
    return ls.mask(ls <= 0, np.nan)


def compute_long_short_zscore(df: pd.DataFrame, n: int) -> pd.Series:
    """S_N_longShortZscore_{n}_zsc_N: (lsRatio - mean_n) / std_n

    Main contrarian signal - extremes predict reversals.
    Empirically: Z>2 → -0.323% 3-bar return (bearish)
                 Z<-2 → +0.746% 3-bar return (bullish)

    Academic: Baker & Wurgler (2006), Moskowitz et al. (2011)
    """
    ls = compute_long_short_ratio(df)
    mean = ls.rolling(n).mean()
    std = ls.rolling(n).std()
    zscore = pd.Series(np.nan, index=df.index, dtype=np.float64)
    ready = mean.notna() & std.notna()
    nonflat = ready & (std > 0)
    flat = ready & (std == 0)

    zscore.loc[nonflat] = (ls.loc[nonflat] - mean.loc[nonflat]) / std.loc[nonflat]
    # A flat, fully observed rolling window means positioning matches its local
    # baseline exactly, so the z-score should be neutral rather than missing.
    zscore.loc[flat] = 0.0
    return zscore.clip(-5, 5)


def compute_long_short_change(df: pd.DataFrame, n: int) -> pd.Series:
    """S_M_longShortChange_{n}_pct_N: (lsRatio / lsRatio.shift(n)) - 1

    Momentum in positioning shifts.
    Rapid changes may signal regime transitions.

    Academic: Moskowitz et al. (2011)
    """
    ls = compute_long_short_ratio(df)
    change = (ls / ls.shift(n)).replace([np.inf, -np.inf], np.nan) - 1
    return change.clip(-1, 1)


# =============================================================================
# FEATURE COMPUTATION - ACADEMIC VOLATILITY (2025-12-22)
# Range-based volatility estimators from academic literature
# =============================================================================


def compute_amihud_illiquidity(df: pd.DataFrame, n: int) -> pd.Series:
    """L_V_amihudIlliquidity_{n}_rat_N: mean(|ln(C/C.shift(1))| / (C * volume), n)

    Measures price impact per dollar traded.
    High = illiquid (big price moves per volume), low = liquid.

    Academic: Amihud (2002), Lou (2017) 161 citations
    Link: https://www.jstor.org/stable/48616728
    """
    log_returns = np.log(df["close"] / df["close"].shift(1))
    dollar_volume = df["close"] * df["volume"]
    illiq = np.abs(log_returns) / dollar_volume.replace(0, np.nan)
    return illiq.rolling(n).mean()


def compute_parkinson_volatility(df: pd.DataFrame, n: int) -> pd.Series:
    """V_parkinson_{n}_pct_N: sqrt(mean((1/(4*ln(2))) * (ln(H/L))², n))

    Range-based volatility estimator using high-low.
    ~5x more efficient than close-to-close volatility.

    Academic: Parkinson (1980) "Extreme Value Method"
    Link: https://www.jstor.org/stable/2352358
    """
    log_hl = np.log(df["high"] / df["low"])
    # Parkinson constant: 1/(4*ln(2)) ≈ 0.3607
    parkinson_const = 1 / (4 * np.log(2))
    variance = parkinson_const * (log_hl**2)
    return np.sqrt(variance.rolling(n).mean())


def compute_garman_klass_volatility(df: pd.DataFrame, n: int) -> pd.Series:
    """V_garmanKlass_{n}_pct_N: sqrt(mean(0.5*(ln(H/L))² - (2*ln(2)-1)*(ln(C/O))², n))

    Uses ALL OHLC data. ~7-8x more efficient than close-to-close.
    Assumes no drift (trending periods less accurate).

    Academic: Garman & Klass (1980)
    Link: https://www.jstor.org/stable/2352358
    """
    log_hl = np.log(df["high"] / df["low"])
    log_co = np.log(df["close"] / df["open"])
    # Constants: 0.5 and (2*ln(2) - 1) ≈ 0.3863
    gk_const = 2 * np.log(2) - 1
    variance = 0.5 * (log_hl**2) - gk_const * (log_co**2)
    # Can go negative in trending markets, use abs for safety
    return np.sqrt(np.abs(variance.rolling(n).mean()))


def compute_rogers_satchell_volatility(df: pd.DataFrame, n: int) -> pd.Series:
    """V_rogersSatchell_{n}_pct_N: sqrt(mean(ln(H/C)*ln(H/O) + ln(L/C)*ln(L/O), n))

    Drift-independent volatility estimator.
    Works better than Parkinson/GK in trending markets.

    Academic: Rogers & Satchell (1991)
    Link: https://www.sciencedirect.com/science/article/abs/pii/030440769190014D
    """
    log_hc = np.log(df["high"] / df["close"])
    log_ho = np.log(df["high"] / df["open"])
    log_lc = np.log(df["low"] / df["close"])
    log_lo = np.log(df["low"] / df["open"])

    variance = log_hc * log_ho + log_lc * log_lo
    # Can go negative, use abs for safety
    return np.sqrt(np.abs(variance.rolling(n).mean()))


def compute_hurst_exponent(df: pd.DataFrame, n: int) -> pd.Series:
    """V_hurstExponent_{n}_rat_N: log(R/S) / log(n)

    Measures long-memory/persistence of price series.
    H > 0.5 = trending, H < 0.5 = mean-reverting, H = 0.5 = random walk.

    Academic: "Implied Hurst Exponent and Fractional Implied Volatility" (SSRN)
    Link: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2383618
    """
    log_returns = np.log(df["close"] / df["close"].shift(1))

    def rs_analysis(window):
        if len(window) < 10:  # Need minimum points
            return np.nan
        mean_ret = window.mean()
        deviations = window - mean_ret
        cumsum = deviations.cumsum()
        R = cumsum.max() - cumsum.min()  # Range
        S = window.std()  # Standard deviation
        if S == 0 or S != S:  # Avoid division by zero or NaN
            return np.nan
        return R / S

    rs = log_returns.rolling(n).apply(rs_analysis, raw=False)
    # H = log(R/S) / log(n)
    hurst = np.log(rs) / np.log(n)
    return hurst.clip(0, 1)  # Bounded [0, 1]


def compute_yang_zhang_volatility(df: pd.DataFrame, n: int) -> pd.Series:
    """V_yangZhang_{n}_pct_N: combines open-close variance + Rogers-Satchell

    Most efficient range-based estimator. Drift-independent.
    Simplified for 24/7 markets (no overnight gap).

    Academic: Yang & Zhang (2000) "Drift Independent Volatility Estimation"
    Link: https://www.jstor.org/stable/222571
    """
    # Open-to-close returns (within bar)
    log_oc = np.log(df["close"] / df["open"])
    mean_oc = log_oc.rolling(n).mean()
    var_oc = ((log_oc - mean_oc) ** 2).rolling(n).mean()

    # Rogers-Satchell variance (drift-independent)
    log_hc = np.log(df["high"] / df["close"])
    log_ho = np.log(df["high"] / df["open"])
    log_lc = np.log(df["low"] / df["close"])
    log_lo = np.log(df["low"] / df["open"])
    var_rs = (log_hc * log_ho + log_lc * log_lo).rolling(n).mean()

    # k weighting constant (Yang-Zhang formula)
    k = 0.34 / (1.34 + (n + 1) / (n - 1))

    # Combined variance (no overnight component for 24/7 markets)
    variance = k * var_oc + (1 - k) * np.abs(var_rs)

    return np.sqrt(np.abs(variance))


# =============================================================================
# MAIN FEATURE COMPUTATION
# =============================================================================


def compute_all_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute all 70 approved features from Part 3 documentation.

    Returns DataFrame with timestamp + all features.
    """
    features = pd.DataFrame()
    features["timestamp"] = df["timestamp"]

    # -------------------------------------------------------------------------
    # MOMENTUM & PRICE (3 features × periods)
    # -------------------------------------------------------------------------
    features["M_P_logReturn_pct_N"] = compute_log_return(df)

    for n in [3, 6, 12, 21]:
        features[f"M_P_roc_{n}_pct_N"] = compute_roc(df, n)
        features[f"M_P_V_momAtr_{n}_rat_N"] = compute_mom_atr(df, n)

    # -------------------------------------------------------------------------
    # VOLATILITY (2 features × periods)
    # -------------------------------------------------------------------------
    for n in [3, 6, 12, 21]:
        features[f"V_atrPct_{n}_pct_N"] = compute_atr_pct(df, n)
        features[f"V_returnStd_{n}_pct_N"] = compute_return_std(df, n)

    # Bollinger Bandwidth - regime/context indicator (longer periods)
    for n in [21, 42]:
        features[f"N_V_bollingerBandwidth_{n}_pct_N"] = compute_bollinger_bandwidth(
            df, n
        )

    # -------------------------------------------------------------------------
    # NORMALIZED PRICE POSITION (1 feature × periods)
    # -------------------------------------------------------------------------
    for n in [3, 6, 12, 21]:
        features[f"N_P_V_pctB_{n}_bnd_N"] = compute_pct_b(df, n)

    # -------------------------------------------------------------------------
    # TREND (3 features)
    # -------------------------------------------------------------------------
    features["M_T_ppo_8_21_pct_N"] = compute_ppo(df, 8, 21)
    features["M_T_ppo_12_26_pct_N"] = compute_ppo(df, 12, 26)

    for n in [3, 6, 12, 21]:
        features[f"N_P_T_priceSmaDeviation_{n}_pct_N"] = compute_price_sma_deviation(
            df, n
        )
        features[f"N_P_T_priceEmaDeviation_{n}_pct_N"] = compute_price_ema_deviation(
            df, n
        )

    # -------------------------------------------------------------------------
    # FUNDING (4 features × periods)
    # -------------------------------------------------------------------------
    for n in [3, 7, 21]:
        features[f"F_I_fundingCumulative_{n}_pct_N"] = compute_funding_cumulative(df, n)
        features[f"F_I_T_fundingMa_{n}_pct_N"] = compute_funding_ma(df, n)

    for short, long in [(3, 7), (3, 21), (7, 21)]:
        features[f"F_I_M_fundingMaDiff_{short}_{long}_pct_N"] = compute_funding_ma_diff(
            df, short, long
        )

    for n in [21, 42]:
        features[f"F_I_N_S_fundingZscore_{n}_zsc_N"] = compute_funding_zscore(df, n)

    # -------------------------------------------------------------------------
    # PREMIUM (2 features × periods)
    # -------------------------------------------------------------------------
    for n in [3, 7, 21]:
        features[f"D_F_T_premiumMa_{n}_pct_N"] = compute_premium_ma(df, n)

    for n in [21, 42]:
        features[f"D_F_N_S_premiumZscore_{n}_zsc_N"] = compute_premium_zscore(df, n)

    # -------------------------------------------------------------------------
    # SPREAD (2 features)
    # -------------------------------------------------------------------------
    features["D_F_basis_pct_N"] = compute_basis(df)
    features["D_markIndexSpread_pct_N"] = compute_mark_index_spread(df)

    # -------------------------------------------------------------------------
    # OPEN INTEREST (4 features × periods)
    # -------------------------------------------------------------------------
    features["L_M_N_S_oiPctChange_pct_N"] = compute_oi_pct_change(df)
    features["L_N_volOiRatio_rat_N"] = compute_vol_oi_ratio(df)

    for n in [3, 6, 12]:
        features[f"L_M_N_S_oiRoc_{n}_pct_N"] = compute_oi_roc(df, n)

    for n in [6, 12, 21]:
        features[f"L_N_S_oiRatio_{n}_rat_N"] = compute_oi_ratio(df, n)

    # -------------------------------------------------------------------------
    # CANDLESTICK (4 features)
    # -------------------------------------------------------------------------
    features["C_N_bodySize_bnd_N"] = compute_body_size(df)
    features["C_N_upperShadow_bnd_N"] = compute_upper_shadow(df)
    features["C_N_lowerShadow_bnd_N"] = compute_lower_shadow(df)
    features["B_C_candleDirection_bin"] = compute_candle_direction(df)

    # -------------------------------------------------------------------------
    # OSCILLATORS (3 features × periods)
    # -------------------------------------------------------------------------
    for n in [6, 12, 21]:
        features[f"M_N_rsi_{n}_bnd_N"] = compute_rsi(df, n)

    for n in [6, 12]:
        features[f"M_N_stochasticK_{n}_bnd_N"] = compute_stochastic_k(df, n)
        features[f"M_N_T_stochasticD_{n}_bnd_N"] = compute_stochastic_d(df, n)

    # -------------------------------------------------------------------------
    # VOLUME (2 features × periods)
    # -------------------------------------------------------------------------
    for n in [3, 6, 12]:
        features[f"L_M_N_volumeRoc_{n}_pct_N"] = compute_volume_roc(df, n)

    for n in [6, 12, 21]:
        features[f"L_N_volumeRatio_{n}_rat_N"] = compute_volume_ratio(df, n)

    # -------------------------------------------------------------------------
    # MOMENTUM ACCELERATION (1 feature × periods)
    # -------------------------------------------------------------------------
    for n in [3, 6]:
        features[f"M_N_rocAccel_{n}_dif_N"] = compute_roc_accel(df, n)

    # -------------------------------------------------------------------------
    # VWAP FEATURES (2025-12-21)
    # -------------------------------------------------------------------------
    features["N_P_L_vwapDeviation_pct_N"] = compute_vwap_deviation(df)
    features["M_P_L_vwapReturn_pct_N"] = compute_vwap_return(df)

    # -------------------------------------------------------------------------
    # PREMIUM DYNAMICS (2025-12-21)
    # -------------------------------------------------------------------------
    features["M_D_F_S_premiumChange_pct_N"] = compute_premium_change(df)
    features["V_D_F_S_premiumRange_pct_N"] = compute_premium_range(df)

    # -------------------------------------------------------------------------
    # OI COMPOSITE (2025-12-20)
    # -------------------------------------------------------------------------
    features["M_P_S_W_oiWeightedReturn_pct_N"] = compute_oi_weighted_return(df)

    # -------------------------------------------------------------------------
    # TEMPORAL (2025-12-20)
    # -------------------------------------------------------------------------
    features["F_TM_fundingCyclePosition_bin"] = compute_funding_cycle_position(df)
    features["B_TM_dayOfWeek_bin"] = compute_day_of_week(df)

    # -------------------------------------------------------------------------
    # MARK PRICE (2025-12-20)
    # -------------------------------------------------------------------------
    features["D_N_markCloseDeviation_pct_N"] = compute_mark_close_deviation(df)
    features["D_N_V_markCloseRange_rat_N"] = compute_mark_close_range(df)
    features["M_P_D_markReturnDiff_pct_N"] = compute_mark_return_diff(df)

    for n in [6, 12, 21]:
        features[f"D_N_V_markAtrRatio_{n}_rat_N"] = compute_mark_atr_ratio(df, n)
        features[f"D_N_closeVsMarkVol_{n}_pct_N"] = compute_close_vs_mark_vol(df, n)

    # -------------------------------------------------------------------------
    # VOLATILITY REGIME (2025-12-20)
    # -------------------------------------------------------------------------
    for n in [21, 42]:
        features[f"N_V_atrPercentile_{n}_rnk_N"] = compute_atr_percentile(df, n)

    for n in [6, 12, 21]:
        features[f"M_N_V_rangeExpansion_{n}_rat_N"] = compute_range_expansion(df, n)
        features[f"V_volOfVol_{n}_pct_N"] = compute_vol_of_vol(df, n)

    features["D_N_premiumRange_rat_N"] = compute_premium_range_norm(df)

    # -------------------------------------------------------------------------
    # DISTRIBUTION SHAPE (2025-12-21)
    # -------------------------------------------------------------------------
    for n in [12, 21, 42]:
        features[f"V_skew_{n}_rat_N"] = compute_skew(df, n)
        features[f"V_kurtosis_{n}_rat_N"] = compute_kurtosis(df, n)

    # -------------------------------------------------------------------------
    # RISK MANAGEMENT (2025-12-21)
    # -------------------------------------------------------------------------
    for n in [21, 42]:
        features[f"V_maxDrawdown_{n}_pct_N"] = compute_max_drawdown(df, n)
        features[f"M_V_sharpe_{n}_rat_N"] = compute_sharpe(df, n)
        features[f"M_V_sortino_{n}_rat_N"] = compute_sortino(df, n)
        features[f"M_V_calmar_{n}_rat_N"] = compute_calmar(df, n)

    # -------------------------------------------------------------------------
    # REGIME DETECTION (2025-12-21)
    # -------------------------------------------------------------------------
    for n in [12, 21]:
        features[f"V_autocorr_{n}_bnd_N"] = compute_autocorr(df, n)

    for n in [12, 21, 42]:
        features[f"N_P_zScore_{n}_zsc_N"] = compute_price_zscore(df, n)

    for n in [6, 12, 21]:
        features[f"V_volMomentum_{n}_pct_N"] = compute_vol_momentum(df, n)

    # -------------------------------------------------------------------------
    # MOMENTUM QUALITY (2025-12-21)
    # -------------------------------------------------------------------------
    features["B_consecutiveUp_bnd_N"] = compute_consecutive_up(df)
    features["B_consecutiveDown_bnd_N"] = compute_consecutive_down(df)

    for n in [6, 12, 21]:
        features[f"M_winRate_{n}_bnd_N"] = compute_win_rate(df, n)

    # -------------------------------------------------------------------------
    # VOLUME-PRICE (2025-12-21)
    # -------------------------------------------------------------------------
    for n in [21, 42]:
        features[f"L_M_S_obv_{n}_zsc_N"] = compute_obv(df, n)

    for n in [6, 12, 21]:
        features[f"L_M_S_mfi_{n}_bnd_N"] = compute_mfi(df, n)
        features[f"L_M_S_cmf_{n}_bnd_N"] = compute_cmf(df, n)

    # -------------------------------------------------------------------------
    # TREND STRENGTH (2025-12-21)
    # -------------------------------------------------------------------------
    for n in [6, 12]:
        features[f"M_T_V_adx_{n}_bnd_N"] = compute_adx(df, n)
        features[f"M_T_V_diDiff_{n}_bnd_N"] = compute_di_diff(df, n)

    for n in [6, 12, 21]:
        features[f"N_M_cci_{n}_zsc_N"] = compute_cci(df, n)

    # -------------------------------------------------------------------------
    # PERPETUAL-SPECIFIC COMPOSITE (2025-12-21)
    # -------------------------------------------------------------------------
    for n in [6, 12, 21]:
        features[f"L_S_oiVolumeRatio_{n}_rat_N"] = compute_oi_volume_ratio(df, n)

    # -------------------------------------------------------------------------
    # LONG/SHORT RATIO SENTIMENT (2025-12-22)
    # Part 3.2: Contrarian sentiment from retail positioning
    # -------------------------------------------------------------------------
    features["S_longShortRatio_rat_N"] = compute_long_short_ratio(df)

    for n in [21, 63]:
        features[f"S_N_longShortZscore_{n}_zsc_N"] = compute_long_short_zscore(df, n)

    for n in [3, 12]:
        features[f"S_M_longShortChange_{n}_pct_N"] = compute_long_short_change(df, n)

    # -------------------------------------------------------------------------
    # ACADEMIC VOLATILITY ESTIMATORS (2025-12-22)
    # Part 3.2: Range-based estimators from academic literature
    # -------------------------------------------------------------------------

    # Amihud Illiquidity - unique liquidity/volatility signal
    for n in [12, 21, 63]:
        features[f"L_V_amihudIlliquidity_{n}_rat_N"] = compute_amihud_illiquidity(df, n)

    # Parkinson - efficient range-based volatility
    for n in [12, 21]:
        features[f"V_parkinson_{n}_pct_N"] = compute_parkinson_volatility(df, n)

    # Garman-Klass - most efficient under no-drift
    for n in [12, 21]:
        features[f"V_garmanKlass_{n}_pct_N"] = compute_garman_klass_volatility(df, n)

    # Rogers-Satchell - drift-independent
    for n in [12, 21]:
        features[f"V_rogersSatchell_{n}_pct_N"] = compute_rogers_satchell_volatility(
            df, n
        )

    # Hurst Exponent - long-memory/persistence
    for n in [63, 126]:
        features[f"V_hurstExponent_{n}_rat_N"] = compute_hurst_exponent(df, n)

    # Yang-Zhang - most efficient overall
    for n in [12, 21]:
        features[f"V_yangZhang_{n}_pct_N"] = compute_yang_zhang_volatility(df, n)

    # -------------------------------------------------------------------------
    # FRACTIONAL DIFFERENTIATION (AFML Ch.5) - 2026-01-16
    # Preserves memory while achieving stationarity
    # d=0.3-0.7 optimal for financial series
    # -------------------------------------------------------------------------
    from scripts.feature_engineering.fracdiff import compute_ffd

    # Price FFD features (close)
    for d in [0.3, 0.5, 0.7]:
        features[f"M_P_close_fracdiff_{d}_pct_N"] = compute_ffd(
            df["close"].values, d=d, max_window=100
        )

    # Volume FFD feature
    features["L_V_volume_fracdiff_0.5_N"] = compute_ffd(
        df["volume"].values, d=0.5, max_window=100
    )

    return features


# =============================================================================
# MAIN
# =============================================================================


def main():
    parser = argparse.ArgumentParser(description="Compute features for RiskYieldMM")
    parser.add_argument(
        "--validate", action="store_true", help="Validate against documentation"
    )
    parser.add_argument(
        "--analyze", action="store_true", help="Run full statistical analysis"
    )
    parser.add_argument(
        "--timeseries", action="store_true", help="Run time-series specific validation"
    )
    parser.add_argument("--all", action="store_true", help="Run all validations")
    parser.add_argument("--export", type=str, help="Export features to parquet file")
    parser.add_argument(
        "--data-dir", type=str, default="fetchingByBit", help="Path to data directory"
    )
    args = parser.parse_args()

    # --all enables all checks
    if args.all:
        args.validate = True
        args.analyze = True
        args.timeseries = True

    # Resolve paths
    script_dir = Path(__file__).parent
    project_root = script_dir.parent.parent
    data_dir = project_root / args.data_dir

    print("=" * 70)
    print("RiskYieldMM Feature Engineering")
    print("=" * 70)
    print(f"Data directory: {data_dir}")

    # Load data
    print("\n[1/3] Loading raw data...")
    df = load_raw_data(data_dir)
    print(f"      Loaded {len(df):,} rows")
    print(f"      Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")

    # Compute features
    print("\n[2/3] Computing features...")
    features = compute_all_features(df)
    feature_cols = [c for c in features.columns if c != "timestamp"]
    print(f"      Computed {len(feature_cols)} features")

    # Summary
    print("\n[3/3] Feature summary:")
    valid_rows = features[feature_cols].dropna().shape[0]
    print(f"      Total rows: {len(features):,}")
    print(f"      Valid rows (no NaN): {valid_rows:,}")
    print(f"      NaN rows (warmup): {len(features) - valid_rows:,}")

    # Export if requested
    if args.export:
        export_path = Path(args.export)
        if not export_path.is_absolute():
            export_path = project_root / export_path
        features.to_parquet(export_path)
        print(f"\n✓ Exported to: {export_path}")

    # Validate if requested
    if args.validate:
        print("\n" + "=" * 70)
        print("VALIDATION (vs Part 3 documentation)")
        print("=" * 70)
        # Import validation module
        from validate_features import validate_all

        validate_all(features, df)

    # Analyze if requested
    if args.analyze:
        print("\n" + "=" * 70)
        print("STATISTICAL ANALYSIS")
        print("=" * 70)
        # Import analysis module
        from analyze_features import analyze_all

        analyze_all(features)

    # Time-series validation if requested
    if args.timeseries:
        print("\n" + "=" * 70)
        print("TIME-SERIES VALIDATION")
        print("=" * 70)
        # Import time-series validation module
        from timeseries_validation import validate_timeseries_features

        # Create simple target for testing (future return)
        # This is just for validation - real target comes from your ML pipeline
        target = np.log(df["close"].shift(-1) / df["close"])
        target.name = "future_log_return"

        ts_results = validate_timeseries_features(df, features, target)

    return features


if __name__ == "__main__":
    main()
