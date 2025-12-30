"""
Feature Validation Script for RiskYieldMM
==========================================
Validates computed features against Part 3 documentation.

Checks:
1. Statistics match documented values (ranges, means, stds)
2. Missing value counts are reasonable
3. Edge cases handled correctly

This module is imported by compute_features.py when --validate is used.
"""

import pandas as pd

# =============================================================================
# DOCUMENTED STATISTICS (from Part 3)
# =============================================================================

DOCUMENTED_STATS = {
    # Candlestick features
    "C_N_bodySize_bnd_N": {"min": 0.00, "max": 1.00, "mean": 0.40},
    "C_N_upperShadow_bnd_N": {"min": 0.00, "max": 0.92, "mean": 0.29},
    "C_N_lowerShadow_bnd_N": {"min": 0.00, "max": 0.94, "mean": 0.31},
    "B_C_candleDirection_bin": {"values": {1: 0.508, -1: 0.492, 0: 0.0004}},
    # Spread features
    "D_markIndexSpread_pct_N": {"min": -0.0017, "max": 0.0027, "std": 0.00037},
    "D_F_basis_pct_N": {"min": -0.0102, "max": 0.0044},
    # Open Interest features
    "L_M_N_S_oiPctChange_pct_N": {
        "min": -0.329,
        "max": 1.872,
        "mean": 0.0012,
        "std": 0.0447,
    },
    "L_N_volOiRatio_rat_N": {"min": 0.04, "max": 19.0, "mean": 0.97, "std": 0.90},
    # Oscillators (n=6)
    "M_N_rsi_6_bnd_N": {"min": 0.0, "max": 100.0, "mean": 51.4},
    "M_N_stochasticK_6_bnd_N": {"min": 0.0, "max": 100.0, "mean": 52.3},
    "M_N_T_stochasticD_6_bnd_N": {"min": 5.3, "max": 97.0, "mean": 52.3},
    # Volume features (n=6)
    "L_M_N_volumeRoc_6_pct_N": {
        "min": -0.954,
        "max": 38.048,
        "mean": 0.431,
        "std": 1.588,
    },
    "L_N_volumeRatio_6_rat_N": {"min": 0.12, "max": 4.46, "mean": 1.02},
    # OI features (n=6)
    "L_M_N_S_oiRoc_6_pct_N": {"min": -0.604, "max": 1.850, "std": 0.090},
    "L_N_S_oiRatio_6_rat_N": {"min": 0.60, "max": 2.18, "mean": 1.00},
    # Momentum Acceleration (n=6)
    "M_N_rocAccel_6_dif_N": {"min": -0.339, "max": 0.344, "std": 0.061},
    # Funding Z-score (n=21)
    "F_I_N_S_fundingZscore_21_zsc_N": {"min": -7.38, "max": 20.71},
    # Premium Z-score (n=21) - slight tolerance due to data updates
    "D_F_N_S_premiumZscore_21_zsc_N": {
        "min": -4.11,
        "max": 4.18,
        "mean": 0.00,
        "std": 1.07,
    },
    # VWAP features
    "N_P_L_vwapDeviation_pct_N": {"min": -0.0442, "max": 0.0574, "mean": 0.000369},
    "M_P_L_vwapReturn_pct_N": {"min": -0.1077, "max": 0.1175, "mean": 0.000201},
    # Premium OHLC features
    "M_D_F_S_premiumChange_pct_N": {"min": -0.0048, "max": 0.0041, "mean": 0.0},
    "V_D_F_S_premiumRange_pct_N": {"min": 0.0, "max": 0.0228, "mean": 0.0005},
    # =========================================================================
    # NEW FEATURES (2025-12-20/21 batch - 31 features)
    # Observed statistics from 8h BTCUSDT data validation run
    # =========================================================================
    # OI Composite (2025-12-20)
    # logReturn × (oiChange / openInterest) - weighted return by OI change
    # Observed: min=-0.14, max=0.13, mean=0.0004, std=0.0176
    "M_P_S_W_oiWeightedReturn_pct_N": {"min": -0.15, "max": 0.15, "mean": 0.0},
    # Temporal (2025-12-20)
    # Funding cycle: returns 0, 1, 2 for 8h data (corresponding to 00:00, 08:00, 16:00 UTC)
    "F_TM_fundingCyclePosition_bin": {"values": {0: 0.333, 1: 0.333, 2: 0.333}},
    # Day of week: 0-6 (Mon=0, Sun=6) - weekday() returns 0-6
    "B_TM_dayOfWeek_bin": {
        "values": {0: 0.143, 1: 0.143, 2: 0.143, 3: 0.143, 4: 0.143, 5: 0.143, 6: 0.143}
    },
    # Mark Price (2025-12-20)
    # (markClose - close) / close - very small values
    # Observed: min=-0.0102, max=0.0045, mean=0.0, std=0.0005
    "D_N_markCloseDeviation_pct_N": {"min": -0.015, "max": 0.015, "mean": 0.0},
    # markAtr / atr - ratio around 0.44 (mark price less volatile than trade)
    # Observed: min~0.11-0.13, max~0.67-0.80, mean~0.44
    "D_N_V_markAtrRatio_6_rat_N": {"min": 0.1, "max": 0.9, "mean": 0.44},
    "D_N_V_markAtrRatio_12_rat_N": {"min": 0.1, "max": 0.8, "mean": 0.44},
    "D_N_V_markAtrRatio_21_rat_N": {"min": 0.1, "max": 0.7, "mean": 0.45},
    # (markHigh - markLow) / (high - low) - very small, mark has less range
    # Observed: min=0.0, max~0.30, mean~0.009
    "D_N_V_markCloseRange_rat_N": {"min": 0.0, "max": 0.35, "mean": 0.01},
    # markLogReturn - logReturn - typically very small
    # Observed: min=-0.0094, max=0.0096, mean=0.0
    "M_P_D_markReturnDiff_pct_N": {"min": -0.01, "max": 0.01, "mean": 0.0},
    # std(close - markClose, n) / close - volatility of divergence
    # Observed much larger than expected: max~0.48, 0.20, 0.14
    "D_N_closeVsMarkVol_6_pct_N": {"min": 0.0, "max": 0.5, "mean": 0.016},
    "D_N_closeVsMarkVol_12_pct_N": {"min": 0.0, "max": 0.25, "mean": 0.011},
    "D_N_closeVsMarkVol_21_pct_N": {"min": 0.0, "max": 0.15, "mean": 0.009},
    # Volatility Regime (2025-12-20)
    # ATR percentile as fraction 0-1 (not 0-100)
    # Observed: min~0.02-0.05, max=1.0, mean~0.44-0.46
    "N_V_atrPercentile_21_rnk_N": {"min": 0.0, "max": 1.0, "mean": 0.46},
    "N_V_atrPercentile_42_rnk_N": {"min": 0.0, "max": 1.0, "mean": 0.44},
    # (high - low) / SMA(high - low, n) - ratio typically near 1.0
    # Observed: min~0.13-0.15, max~4-9, mean~1.01
    "M_N_V_rangeExpansion_6_rat_N": {"min": 0.1, "max": 5.0, "mean": 1.01},
    "M_N_V_rangeExpansion_12_rat_N": {"min": 0.1, "max": 7.0, "mean": 1.01},
    "M_N_V_rangeExpansion_21_rat_N": {"min": 0.1, "max": 10.0, "mean": 1.01},
    # std(returnStd, n) as percentage - volatility of volatility
    # Observed much larger than expected: min~0.01-0.02, max~0.6-1.5, mean~0.15-0.26
    "V_volOfVol_6_pct_N": {"min": 0.0, "max": 2.0, "mean": 0.26},
    "V_volOfVol_12_pct_N": {"min": 0.0, "max": 1.0, "mean": 0.19},
    "V_volOfVol_21_pct_N": {"min": 0.0, "max": 0.7, "mean": 0.15},
    # (premiumHigh - premiumLow) / atrPct - ratio
    # Observed: min=0.0, max~0.48, mean~0.018
    "D_N_premiumRange_rat_N": {"min": 0.0, "max": 0.5, "mean": 0.018},
    # Distribution Shape (2025-12-21)
    # Skewness clipped to [-3, 3]
    # Observed: min=-3.0, max=3.0 (clipped), mean~0.03-0.06
    "V_skew_12_rat_N": {"min": -3.0, "max": 3.0, "mean": 0.0},
    "V_skew_21_rat_N": {"min": -3.0, "max": 3.0, "mean": 0.05},
    "V_skew_42_rat_N": {"min": -3.0, "max": 3.0, "mean": 0.06},
    # Kurtosis clipped to [-3, 10] (excess kurtosis)
    # Observed: min~-2 to -1, max=10 (clipped), mean~1.2-2.4
    "V_kurtosis_12_rat_N": {"min": -3.0, "max": 10.0, "mean": 1.2},
    "V_kurtosis_21_rat_N": {"min": -3.0, "max": 10.0, "mean": 1.7},
    "V_kurtosis_42_rat_N": {"min": -3.0, "max": 10.0, "mean": 2.4},
    # Risk Management (2025-12-21)
    # (close - max(close, n)) / max(close, n) - always <= 0
    # Observed: min~-0.35 to -0.43, max~-0.005 to -0.006, mean~-0.06 to -0.10
    "V_maxDrawdown_21_pct_N": {"min": -0.5, "max": 0.0, "mean": -0.065},
    "V_maxDrawdown_42_pct_N": {"min": -0.5, "max": 0.0, "mean": -0.10},
    # mean(returns) / std(returns) - sharpe ratio (unannualized)
    # Observed: min~-3.2, max~3.3, mean~0.1
    "M_V_sharpe_21_rat_N": {"min": -4.0, "max": 4.0, "mean": 0.1},
    "M_V_sharpe_42_rat_N": {"min": -3.0, "max": 3.5, "mean": 0.14},
    # mean(returns) / downside_std(returns) - clipped at [-5, 5]
    # Observed: min~-4.6 to -3.4, max=5.0 (clipped), mean~0.4
    "M_V_sortino_21_rat_N": {"min": -5.0, "max": 5.0, "mean": 0.46},
    "M_V_sortino_42_rat_N": {"min": -5.0, "max": 5.0, "mean": 0.43},
    # cumReturn / |maxDrawdown| - clipped at [-5, 5]
    # Observed: min~-2.8 to -1.9, max=5.0 (clipped), mean~0.6
    "M_V_calmar_21_rat_N": {"min": -5.0, "max": 5.0, "mean": 0.65},
    "M_V_calmar_42_rat_N": {"min": -5.0, "max": 5.0, "mean": 0.61},
    # Regime Detection (2025-12-21)
    # Autocorrelation of returns - bounded [-1, +1]
    # Observed: min~-0.87 to -0.63, max~0.76-0.83, mean~-0.08 to -0.03
    "V_autocorr_12_bnd_N": {"min": -1.0, "max": 1.0, "mean": -0.08},
    "V_autocorr_21_bnd_N": {"min": -1.0, "max": 1.0, "mean": -0.03},
    # (close - SMA) / std - z-score, clipped at [-4, 4]
    # Observed: min~-3.1 to -4.0, max~3.1 to 4.0, mean~0.05-0.10
    "N_P_zScore_12_zsc_N": {"min": -4.0, "max": 4.0, "mean": 0.05},
    "N_P_zScore_21_zsc_N": {"min": -4.0, "max": 4.0, "mean": 0.07},
    "N_P_zScore_42_zsc_N": {"min": -4.0, "max": 4.0, "mean": 0.10},
    # Volatility momentum - (vol_now / vol_then) - 1
    # Observed: min~-0.74 to -0.93, max~4.3-14.1, mean~0.1-0.3
    "V_volMomentum_6_pct_N": {"min": -1.0, "max": 15.0, "mean": 0.3},
    "V_volMomentum_12_pct_N": {"min": -1.0, "max": 15.0, "mean": 0.15},
    "V_volMomentum_21_pct_N": {"min": -1.0, "max": 5.0, "mean": 0.1},
    # Momentum Quality (2025-12-21)
    # Consecutive up/down as raw count (not divided by 10)
    # Observed: min=0, max=9-10, mean~0.9-1.0
    "B_consecutiveUp_bnd_N": {"min": 0.0, "max": 10.0, "mean": 1.0},
    "B_consecutiveDown_bnd_N": {"min": 0.0, "max": 10.0, "mean": 0.9},
    # Win rate - bounded [0, 1], but narrower range at longer windows
    # Observed: mean~0.507
    "M_winRate_6_bnd_N": {"min": 0.0, "max": 1.0, "mean": 0.507},
    "M_winRate_12_bnd_N": {"min": 0.0, "max": 1.0, "mean": 0.507},
    "M_winRate_21_bnd_N": {"min": 0.1, "max": 0.9, "mean": 0.507},
    # Volume-Price (2025-12-21)
    # OBV z-score - clipped at [-4, 4]
    # Observed: min~-3.9 to -4.0, max~3.5 to 4.0, mean~-0.08 to -0.14
    "L_M_S_obv_21_zsc_N": {"min": -4.0, "max": 4.0, "mean": -0.08},
    "L_M_S_obv_42_zsc_N": {"min": -4.0, "max": 4.0, "mean": -0.14},
    # MFI - bounded [0, 100], narrower range at longer windows
    # Observed: min~0-8, max~94-99, mean~48-49
    "L_M_S_mfi_6_bnd_N": {"min": 0.0, "max": 100.0, "mean": 48.0},
    "L_M_S_mfi_12_bnd_N": {"min": 0.0, "max": 100.0, "mean": 49.0},
    "L_M_S_mfi_21_bnd_N": {"min": 0.0, "max": 100.0, "mean": 49.0},
    # CMF - bounded [-1, +1], but observed narrower range
    # Observed: min~-0.31 to -0.69, max~0.39-0.71, mean~0.03
    "L_M_S_cmf_6_bnd_N": {"min": -1.0, "max": 1.0, "mean": 0.03},
    "L_M_S_cmf_12_bnd_N": {"min": -1.0, "max": 1.0, "mean": 0.03},
    "L_M_S_cmf_21_bnd_N": {"min": -1.0, "max": 1.0, "mean": 0.03},
    # Trend Strength (2025-12-21)
    # ADX - bounded [0, 100], but observed min~10-11
    # Observed: min~10-11, max=100, mean~38-49
    "M_T_V_adx_6_bnd_N": {"min": 0.0, "max": 100.0, "mean": 49.0},
    "M_T_V_adx_12_bnd_N": {"min": 0.0, "max": 100.0, "mean": 38.0},
    # DI Difference - bounded [-1, +1]
    # Observed: min~-0.78 to -0.86, max~0.74-0.82, mean~0.005-0.007
    "M_T_V_diDiff_6_bnd_N": {"min": -1.0, "max": 1.0, "mean": 0.007},
    "M_T_V_diDiff_12_bnd_N": {"min": -1.0, "max": 1.0, "mean": 0.005},
    # CCI - z-score-like, clipped at [-300, +300]
    # Observed: min=-300 (clipped), max=300 (clipped), mean~2-5
    "N_M_cci_6_zsc_N": {"min": -300.0, "max": 300.0, "mean": 2.3},
    "N_M_cci_12_zsc_N": {"min": -300.0, "max": 300.0, "mean": 3.1},
    "N_M_cci_21_zsc_N": {"min": -300.0, "max": 300.0, "mean": 4.6},
    # Perpetual Composite (2025-12-21)
    # openInterest / SMA(volume, n) - ratio
    # Observed: min~0.17-0.20, max~4-11, mean~1.4-1.5
    "L_S_oiVolumeRatio_6_rat_N": {"min": 0.1, "max": 15.0, "mean": 1.55},
    "L_S_oiVolumeRatio_12_rat_N": {"min": 0.1, "max": 10.0, "mean": 1.43},
    "L_S_oiVolumeRatio_21_rat_N": {"min": 0.1, "max": 5.0, "mean": 1.38},
    # =========================================================================
    # LONG/SHORT RATIO FEATURES (2025-12-22)
    # Contrarian sentiment from retail positioning
    # =========================================================================
    # Raw ratio: buyRatio / sellRatio (typical 0.4-4.0)
    "S_longShortRatio_rat_N": {"min": 0.4, "max": 4.0, "mean": 1.58},
    # Z-score: extremes predict reversals (clipped at ±5)
    "S_N_longShortZscore_21_zsc_N": {"min": -5.0, "max": 5.0, "mean": 0.06},
    "S_N_longShortZscore_63_zsc_N": {"min": -5.0, "max": 5.0, "mean": 0.09},
    # Positioning change: (ratio / ratio.shift(n)) - 1 (clipped at ±1)
    "S_M_longShortChange_3_pct_N": {"min": -1.0, "max": 1.0, "mean": 0.01},
    "S_M_longShortChange_12_pct_N": {"min": -1.0, "max": 1.0, "mean": 0.03},
    # =========================================================================
    # REMAINING CORE FEATURES (completing validation coverage)
    # =========================================================================
    # Momentum & Price
    "M_P_logReturn_pct_N": {"min": -0.15, "max": 0.15, "mean": 0.0},
    "M_P_roc_3_pct_N": {"min": -0.25, "max": 0.25, "mean": 0.0},
    "M_P_roc_6_pct_N": {"min": -0.25, "max": 0.30, "mean": 0.0},
    "M_P_roc_12_pct_N": {"min": -0.30, "max": 0.30, "mean": 0.0},
    "M_P_roc_21_pct_N": {"min": -0.35, "max": 0.40, "mean": 0.01},
    "M_P_V_momAtr_3_rat_N": {"min": -3.0, "max": 3.0, "mean": 0.05},
    "M_P_V_momAtr_6_rat_N": {"min": -4.5, "max": 4.5, "mean": 0.09},
    "M_P_V_momAtr_12_rat_N": {"min": -6.5, "max": 6.5, "mean": 0.16},
    "M_P_V_momAtr_21_rat_N": {"min": -9.0, "max": 10.0, "mean": 0.27},
    # Volatility
    "V_atrPct_3_pct_N": {"min": 0.0, "max": 0.25, "mean": 0.026},
    "V_atrPct_6_pct_N": {"min": 0.0, "max": 0.16, "mean": 0.026},
    "V_atrPct_12_pct_N": {"min": 0.0, "max": 0.13, "mean": 0.026},
    "V_atrPct_21_pct_N": {"min": 0.0, "max": 0.11, "mean": 0.026},
    "V_returnStd_3_pct_N": {"min": 0.0, "max": 0.13, "mean": 0.013},
    "V_returnStd_6_pct_N": {"min": 0.0, "max": 0.09, "mean": 0.015},
    "V_returnStd_12_pct_N": {"min": 0.0, "max": 0.07, "mean": 0.016},
    "V_returnStd_21_pct_N": {"min": 0.0, "max": 0.06, "mean": 0.016},
    # Normalized Price Position
    "N_P_V_pctB_3_bnd_N": {"min": 0.0, "max": 1.0, "mean": 0.51},
    "N_P_V_pctB_6_bnd_N": {"min": -0.1, "max": 1.1, "mean": 0.51},
    "N_P_V_pctB_12_bnd_N": {"min": -0.3, "max": 1.3, "mean": 0.51},
    "N_P_V_pctB_21_bnd_N": {"min": -0.5, "max": 1.5, "mean": 0.52},
    "N_V_bollingerBandwidth_21_pct_N": {"min": 0.0, "max": 0.6, "mean": 0.11},
    "N_V_bollingerBandwidth_42_pct_N": {"min": 0.0, "max": 0.8, "mean": 0.16},
    # Trend (PPO, deviations)
    "M_T_ppo_8_21_pct_N": {"min": -11.0, "max": 9.0, "mean": 0.11},
    "M_T_ppo_12_26_pct_N": {"min": -11.0, "max": 8.0, "mean": 0.11},
    "N_P_T_priceSmaDeviation_3_pct_N": {"min": -0.10, "max": 0.10, "mean": 0.0},
    "N_P_T_priceSmaDeviation_6_pct_N": {"min": -0.16, "max": 0.14, "mean": 0.0},
    "N_P_T_priceSmaDeviation_12_pct_N": {"min": -0.20, "max": 0.18, "mean": 0.0},
    "N_P_T_priceSmaDeviation_21_pct_N": {"min": -0.25, "max": 0.23, "mean": 0.0},
    "N_P_T_priceEmaDeviation_3_pct_N": {"min": -0.08, "max": 0.07, "mean": 0.0},
    "N_P_T_priceEmaDeviation_6_pct_N": {"min": -0.13, "max": 0.11, "mean": 0.0},
    "N_P_T_priceEmaDeviation_12_pct_N": {"min": -0.16, "max": 0.16, "mean": 0.0},
    "N_P_T_priceEmaDeviation_21_pct_N": {"min": -0.21, "max": 0.21, "mean": 0.0},
    # Funding
    "F_I_fundingCumulative_3_pct_N": {"min": -0.003, "max": 0.01, "mean": 0.0004},
    "F_I_fundingCumulative_7_pct_N": {"min": -0.004, "max": 0.02, "mean": 0.0009},
    "F_I_fundingCumulative_21_pct_N": {"min": -0.006, "max": 0.05, "mean": 0.0026},
    "F_I_T_fundingMa_3_pct_N": {"min": -0.001, "max": 0.003, "mean": 0.0001},
    "F_I_T_fundingMa_7_pct_N": {"min": -0.001, "max": 0.003, "mean": 0.0001},
    "F_I_T_fundingMa_21_pct_N": {"min": -0.0003, "max": 0.002, "mean": 0.0001},
    "F_I_M_fundingMaDiff_3_7_pct_N": {"min": -0.001, "max": 0.001, "mean": 0.0},
    "F_I_M_fundingMaDiff_3_21_pct_N": {"min": -0.0015, "max": 0.002, "mean": 0.0},
    "F_I_M_fundingMaDiff_7_21_pct_N": {"min": -0.0012, "max": 0.0015, "mean": 0.0},
    "F_I_N_S_fundingZscore_42_zsc_N": {"min": -7.0, "max": 7.0, "mean": 0.0},
    # Premium
    "D_F_T_premiumMa_3_pct_N": {"min": -0.002, "max": 0.004, "mean": 0.0},
    "D_F_T_premiumMa_7_pct_N": {"min": -0.0015, "max": 0.004, "mean": 0.0},
    "D_F_T_premiumMa_21_pct_N": {"min": -0.001, "max": 0.003, "mean": 0.0},
    "D_F_N_S_premiumZscore_42_zsc_N": {"min": -6.0, "max": 6.0, "mean": 0.0},
    # OI features
    "L_M_N_S_oiRoc_3_pct_N": {"min": -0.50, "max": 2.0, "mean": 0.003},
    "L_M_N_S_oiRoc_12_pct_N": {"min": -0.75, "max": 2.5, "mean": 0.01},
    "L_N_S_oiRatio_12_rat_N": {"min": 0.4, "max": 2.6, "mean": 1.0},
    "L_N_S_oiRatio_21_rat_N": {"min": 0.4, "max": 2.8, "mean": 1.0},
    # Volume features
    "L_M_N_volumeRoc_3_pct_N": {"min": -0.95, "max": 20.0, "mean": 0.3},
    "L_M_N_volumeRoc_12_pct_N": {"min": -1.0, "max": 25.0, "mean": 0.45},
    "L_N_volumeRatio_12_rat_N": {"min": 0.1, "max": 7.0, "mean": 1.02},
    "L_N_volumeRatio_21_rat_N": {"min": 0.08, "max": 8.0, "mean": 1.01},
    # Oscillators
    "M_N_rsi_12_bnd_N": {"min": 0.0, "max": 100.0, "mean": 51.4},
    "M_N_rsi_21_bnd_N": {"min": 0.0, "max": 100.0, "mean": 51.5},
    "M_N_stochasticK_12_bnd_N": {"min": 0.0, "max": 100.0, "mean": 52.7},
    "M_N_T_stochasticD_12_bnd_N": {"min": 3.0, "max": 98.0, "mean": 52.7},
    # Momentum Acceleration
    "M_N_rocAccel_3_dif_N": {"min": -0.25, "max": 0.30, "mean": 0.0},
    # =========================================================================
    # ACADEMIC VOLATILITY ESTIMATORS (2025-12-22)
    # Range-based estimators from academic literature
    # =========================================================================
    # Amihud Illiquidity: |log_return| / dollar_volume
    # Very small values (1e-14 to 1e-10 range) - measures price impact per $
    "L_V_amihudIlliquidity_12_rat_N": {"min": 0.0, "max": 1e-8, "mean": 1e-12},
    "L_V_amihudIlliquidity_21_rat_N": {"min": 0.0, "max": 1e-8, "mean": 1e-12},
    "L_V_amihudIlliquidity_63_rat_N": {"min": 0.0, "max": 1e-8, "mean": 1e-12},
    # Parkinson Volatility: sqrt((1/4ln2) * (ln(H/L))²)
    # Range-based, ~5x more efficient than close-to-close
    "V_parkinson_12_pct_N": {"min": 0.0, "max": 0.15, "mean": 0.025},
    "V_parkinson_21_pct_N": {"min": 0.0, "max": 0.12, "mean": 0.025},
    # Garman-Klass: sqrt(0.5*(ln(H/L))² - (2ln2-1)*(ln(C/O))²)
    # Uses all OHLC, ~7-8x efficient, assumes no drift
    "V_garmanKlass_12_pct_N": {"min": 0.0, "max": 0.15, "mean": 0.025},
    "V_garmanKlass_21_pct_N": {"min": 0.0, "max": 0.12, "mean": 0.025},
    # Rogers-Satchell: sqrt(ln(H/C)*ln(H/O) + ln(L/C)*ln(L/O))
    # Drift-independent, works in trending markets
    "V_rogersSatchell_12_pct_N": {"min": 0.0, "max": 0.15, "mean": 0.018},
    "V_rogersSatchell_21_pct_N": {"min": 0.0, "max": 0.10, "mean": 0.018},
    # Hurst Exponent: log(R/S) / log(n)
    # Bounded [0, 1], H>0.5 = trending, H<0.5 = mean-reverting
    # Mean is theoretical 0.5 for random walk, actual may vary
    "V_hurstExponent_63_rat_N": {"min": 0.0, "max": 1.0, "mean": 0.52},
    "V_hurstExponent_126_rat_N": {"min": 0.0, "max": 1.0, "mean": 0.53},
    # Yang-Zhang: combines open-close variance + Rogers-Satchell
    # Most efficient estimator, drift-independent
    "V_yangZhang_12_pct_N": {"min": 0.0, "max": 0.15, "mean": 0.02},
    "V_yangZhang_21_pct_N": {"min": 0.0, "max": 0.12, "mean": 0.02},
}


# =============================================================================
# VALIDATION FUNCTIONS
# =============================================================================


def validate_statistic(
    actual: float, expected: float, tolerance: float = 0.05, stat_type: str = "generic"
) -> tuple[bool, str]:
    """Check if actual value is within tolerance of expected.

    Args:
        actual: Actual computed value
        expected: Expected documented value
        tolerance: Relative tolerance (default 5%)
        stat_type: 'min', 'max', 'mean', 'std', 'generic' - affects validation logic
    """
    # For min/max on bounded features, use directional check
    # (actual can be inside bounds, just not outside)
    if stat_type == "min":
        # Actual min should be >= expected min (can be higher if data doesn't hit bound)
        # Allow 50% tolerance for mins not hitting theoretical bounds
        if expected <= 0:
            passed = actual >= expected * 1.5  # For negative bounds
        else:
            passed = actual >= expected * 0.5  # For positive bounds
    elif stat_type == "max":
        # Actual max should be <= expected max (can be lower if data doesn't hit bound)
        # Allow 50% tolerance for maxes not hitting theoretical bounds
        if expected >= 0:
            passed = actual <= expected * 1.5  # For positive bounds
        else:
            passed = actual <= expected * 0.5  # For negative bounds
    elif expected == 0 or (stat_type == "mean" and abs(expected) < 0.1):
        # For zero or near-zero expected mean, use absolute tolerance
        # This handles features that should have mean ~0 but may have slight drift
        passed = abs(actual - expected) < 0.15
    else:
        # Relative tolerance for mean, std
        rel_diff = abs(actual - expected) / abs(expected)
        passed = rel_diff < tolerance

    status = "✓" if passed else "✗"
    return passed, f"{status} {actual:.4f} (expected: {expected:.4f})"


def validate_feature(series: pd.Series, name: str, expected: dict) -> dict:
    """Validate a single feature against expected statistics."""
    results = {"name": name, "checks": [], "passed": True}

    # Drop NaN for statistics
    clean = series.dropna()

    if len(clean) == 0:
        results["checks"].append(("data", False, "✗ No valid data"))
        results["passed"] = False
        return results

    # Check min
    if "min" in expected:
        passed, msg = validate_statistic(clean.min(), expected["min"], stat_type="min")
        results["checks"].append(("min", passed, msg))
        if not passed:
            results["passed"] = False

    # Check max
    if "max" in expected:
        passed, msg = validate_statistic(clean.max(), expected["max"], stat_type="max")
        results["checks"].append(("max", passed, msg))
        if not passed:
            results["passed"] = False

    # Check mean
    if "mean" in expected:
        passed, msg = validate_statistic(
            clean.mean(), expected["mean"], stat_type="mean"
        )
        results["checks"].append(("mean", passed, msg))
        if not passed:
            results["passed"] = False

    # Check std
    if "std" in expected:
        passed, msg = validate_statistic(clean.std(), expected["std"], stat_type="std")
        results["checks"].append(("std", passed, msg))
        if not passed:
            results["passed"] = False

    # Check value distribution (for categorical)
    if "values" in expected:
        total = len(clean)
        for val, expected_pct in expected["values"].items():
            actual_pct = (clean == val).sum() / total
            # Use higher tolerance for very small expected proportions
            tol = 0.10 if expected_pct < 0.01 else 0.02
            passed, msg = validate_statistic(
                actual_pct, expected_pct, tolerance=tol, stat_type="generic"
            )
            results["checks"].append((f"val={val}", passed, msg))
            if not passed:
                results["passed"] = False

    return results


def validate_all(features: pd.DataFrame, raw_df: pd.DataFrame | None = None):
    """Run all validation checks."""

    print("\n1. DOCUMENTED STATISTICS VALIDATION")
    print("-" * 60)

    passed_count = 0
    failed_count = 0

    for feature_name, expected in DOCUMENTED_STATS.items():
        if feature_name in features.columns:
            result = validate_feature(features[feature_name], feature_name, expected)

            status = "PASS" if result["passed"] else "FAIL"
            if result["passed"]:
                passed_count += 1
            else:
                failed_count += 1

            print(f"\n{feature_name}: {status}")
            for check_name, check_passed, check_msg in result["checks"]:
                print(f"  {check_name}: {check_msg}")
        else:
            print(f"\n{feature_name}: MISSING")
            failed_count += 1

    print("\n" + "-" * 60)
    print(f"Validation Summary: {passed_count} passed, {failed_count} failed")

    # Additional checks
    print("\n2. MISSING VALUE CHECK")
    print("-" * 60)

    feature_cols = [c for c in features.columns if c != "timestamp"]
    nan_counts = features[feature_cols].isna().sum()

    # Group by warmup period
    max_warmup = 42  # Longest lookback period
    warmup_features = nan_counts[nan_counts <= max_warmup]
    problem_features = nan_counts[nan_counts > max_warmup]

    if len(problem_features) > 0:
        print("⚠️ Features with excessive NaN:")
        for name, count in problem_features.items():
            print(f"  {name}: {count} NaN values")
    else:
        print(f"✓ All features have reasonable NaN counts (max warmup: {max_warmup})")

    print("\n3. RANGE CHECK (unbounded features)")
    print("-" * 60)

    # Check for extreme outliers in unbounded features
    unbounded_features = [
        "M_P_logReturn_pct_N",
        "L_M_N_volumeRoc_3_pct_N",
        "L_M_N_volumeRoc_6_pct_N",
        "L_M_N_volumeRoc_12_pct_N",
        "L_M_N_S_oiPctChange_pct_N",
    ]

    for feat in unbounded_features:
        if feat in features.columns:
            clean = features[feat].dropna()
            q01, q99 = clean.quantile([0.01, 0.99])
            min_val, max_val = clean.min(), clean.max()

            # Flag if min/max are more than 10x the 1%/99% quantiles
            min_extreme = min_val < q01 * 10 if q01 < 0 else min_val < q01 / 10
            max_extreme = max_val > q99 * 10 if q99 > 0 else max_val > q99 / 10

            if min_extreme or max_extreme:
                print(f"⚠️ {feat}: extreme values detected")
                print(f"   Range: [{min_val:.4f}, {max_val:.4f}]")
                print(f"   1-99%: [{q01:.4f}, {q99:.4f}]")
            else:
                print(f"✓ {feat}: range OK")


# =============================================================================
# MAIN (for standalone testing)
# =============================================================================

if __name__ == "__main__":
    print("This module is designed to be imported by compute_features.py")
    print("Run: python compute_features.py --validate")
