# ============================================================================
# WF_FEATURES.PY - Feature Engineering Functions for Walk-Forward
# ============================================================================
# Contains:
#   - calculate_rsi_from_returns(): RSI calculation using Wilder's method
#   - create_rsi_features(): Create RSI features for multiple periods
#   - create_dual_ema_features(): Dual EMA aggregation across periods
#   - create_risk_guard_features(): Risk guard signal features
# ============================================================================

import numpy as np
import pandas as pd

# Default RSI periods
RSI_PERIODS = [2, 3, 5, 7, 9, 10, 12, 14, 16, 20, 21, 25, 30, 50]


def calculate_rsi_from_returns(returns_series, period):
    """
    Calculate RSI using Wilder's smoothed method from lagged forward returns.
    
    Parameters:
    -----------
    returns_series : pd.Series
        The lagged forward returns (can be positive or negative)
    period : int
        RSI lookback period
        
    Returns:
    --------
    pd.Series : RSI values (0-100 scale)
    """
    # Calculate gains and losses
    gains = returns_series.clip(lower=0)  # Keep positive, zero out negative
    losses = (-returns_series).clip(lower=0)  # Abs of negative, zero out positive
    
    # First average: simple mean for first 'period' values
    first_avg_gain = gains.rolling(window=period, min_periods=period).mean()
    first_avg_loss = losses.rolling(window=period, min_periods=period).mean()
    
    # Wilder's smoothed averages using EWM (equivalent to the recursive formula)
    # The span parameter: span = 2*period - 1 gives the same decay as Wilder's formula
    # But actually Wilder's uses: new_avg = (prev_avg * (n-1) + current) / n
    # This is equivalent to EWM with alpha = 1/n, so com = n-1
    avg_gain = gains.ewm(com=period-1, min_periods=period, adjust=False).mean()
    avg_loss = losses.ewm(com=period-1, min_periods=period, adjust=False).mean()
    
    # Calculate RS and RSI
    rs = avg_gain / avg_loss.replace(0, np.finfo(float).eps)  # Avoid division by zero
    rsi = 100 - (100 / (1 + rs))
    
    return rsi


def create_rsi_features(df, returns_col='lagged_forward_returns', periods=None):
    """
    Create RSI features for all specified periods.
    
    Parameters:
    -----------
    df : pd.DataFrame
        Source dataframe
    returns_col : str
        Column name containing lagged forward returns
    periods : list
        List of RSI periods to calculate (default: RSI_PERIODS)
        
    Returns:
    --------
    df : pd.DataFrame with new RSI columns
    rsi_cols : list of new column names
    """
    if periods is None:
        periods = RSI_PERIODS
        
    rsi_cols = []
    
    if returns_col not in df.columns:
        print(f"  ⚠️ Warning: '{returns_col}' not found in dataframe, skipping RSI calculation")
        return df, rsi_cols
    
    returns = df[returns_col]
    
    for period in periods:
        col_name = f'rsi_{period}'
        df[col_name] = calculate_rsi_from_returns(returns, period)
        rsi_cols.append(col_name)
    
    # Also add some derived RSI features
    # RSI divergence: difference between short and long RSI
    if 5 in periods and 14 in periods:
        df['rsi_divergence_5_14'] = df['rsi_5'] - df['rsi_14']
        rsi_cols.append('rsi_divergence_5_14')
    
    if 7 in periods and 21 in periods:
        df['rsi_divergence_7_21'] = df['rsi_7'] - df['rsi_21']
        rsi_cols.append('rsi_divergence_7_21')
    
    # RSI momentum: rate of change in RSI
    if 14 in periods:
        df['rsi_14_momentum'] = df['rsi_14'].diff(3)  # 3-day RSI change
        rsi_cols.append('rsi_14_momentum')
    
    # RSI extremes (binary flags for overbought/oversold)
    if 14 in periods:
        df['rsi_14_overbought'] = (df['rsi_14'] > 70).astype(int)
        df['rsi_14_oversold'] = (df['rsi_14'] < 30).astype(int)
        rsi_cols.extend(['rsi_14_overbought', 'rsi_14_oversold'])
    
    return df, rsi_cols


def create_dual_ema_features(df, returns_col='lagged_forward_returns', max_period=180):
    """
    Create dual EMA features for direction and volatility prediction.
    
    Uses 7 indicator families computed over periods 1-180, then applies
    dual EMA aggregation (short→long and long→short) to capture different
    temporal patterns.
    
    Parameters:
    -----------
    df : pd.DataFrame
        Source dataframe
    returns_col : str
        Column with lagged forward returns
    max_period : int
        Maximum lookback period (default 180)
        
    Returns:
    --------
    df : pd.DataFrame with new dual EMA columns
    dual_ema_cols : list of new column names
    """
    dual_ema_cols = []
    
    if returns_col not in df.columns:
        print(f"  ⚠️ Warning: '{returns_col}' not found, skipping dual EMA features")
        return df, dual_ema_cols
    
    returns = df[returns_col].values
    n = len(returns)
    periods = list(range(1, max_period + 1))
    
    # EMA alpha for aggregation across periods
    EMA_ALPHA = 2 / (max_period + 1)
    
    print(f"  Computing 7 indicator families across {max_period} periods...")
    
    # Pre-allocate indicator matrices: [n_rows x n_periods]
    # Each matrix[i, p] = indicator value at row i for period p
    
    # 1. RSI (already computed for some periods, but we need all 180)
    rsi_matrix = np.full((n, max_period), np.nan)
    for p_idx, period in enumerate(periods):
        gains = np.where(returns > 0, returns, 0)
        losses = np.where(returns < 0, -returns, 0)
        
        # Wilder's smoothed average
        alpha = 1.0 / period
        avg_gain = np.zeros(n)
        avg_loss = np.zeros(n)
        
        for i in range(period, n):
            if i == period:
                avg_gain[i] = np.mean(gains[i-period:i])
                avg_loss[i] = np.mean(losses[i-period:i])
            else:
                avg_gain[i] = avg_gain[i-1] * (1 - alpha) + gains[i] * alpha
                avg_loss[i] = avg_loss[i-1] * (1 - alpha) + losses[i] * alpha
        
        with np.errstate(divide='ignore', invalid='ignore'):
            rs = avg_gain / (avg_loss + 1e-10)
            rsi_matrix[:, p_idx] = 100 - (100 / (1 + rs))
    
    # 2. Volatility (rolling std of returns)
    vol_matrix = np.full((n, max_period), np.nan)
    for p_idx, period in enumerate(periods):
        for i in range(period, n):
            vol_matrix[i, p_idx] = np.std(returns[i-period:i])
    
    # 3. Momentum (cumsum of returns over period)
    mom_matrix = np.full((n, max_period), np.nan)
    for p_idx, period in enumerate(periods):
        for i in range(period, n):
            mom_matrix[i, p_idx] = np.sum(returns[i-period:i])
    
    # 4. Sharpe (mean/std of returns)
    sharpe_matrix = np.full((n, max_period), np.nan)
    for p_idx, period in enumerate(periods):
        for i in range(period, n):
            window = returns[i-period:i]
            std = np.std(window)
            if std > 1e-10:
                sharpe_matrix[i, p_idx] = np.mean(window) / std
            else:
                sharpe_matrix[i, p_idx] = 0
    
    # 5. WinRate (fraction of positive returns)
    winrate_matrix = np.full((n, max_period), np.nan)
    for p_idx, period in enumerate(periods):
        for i in range(period, n):
            winrate_matrix[i, p_idx] = np.mean(returns[i-period:i] > 0)
    
    # 6. Skewness
    skew_matrix = np.full((n, max_period), np.nan)
    for p_idx, period in enumerate(periods):
        if period >= 3:  # Need at least 3 for skewness
            for i in range(period, n):
                window = returns[i-period:i]
                mean = np.mean(window)
                std = np.std(window)
                if std > 1e-10:
                    skew_matrix[i, p_idx] = np.mean(((window - mean) / std) ** 3)
    
    # 7. Drawdown (current vs rolling max)
    # Use cumulative returns
    cumret = np.cumsum(returns)
    dd_matrix = np.full((n, max_period), np.nan)
    for p_idx, period in enumerate(periods):
        for i in range(period, n):
            roll_max = np.max(cumret[i-period:i+1])
            dd_matrix[i, p_idx] = cumret[i] - roll_max
    
    print(f"  Applying dual EMA aggregation...")
    
    # Define indicator matrices and names
    indicators = {
        'RSI': rsi_matrix,
        'Volatility': vol_matrix,
        'Momentum': mom_matrix,
        'Sharpe': sharpe_matrix,
        'WinRate': winrate_matrix,
        'Skewness': skew_matrix,
        'Drawdown': dd_matrix,
    }
    
    # Apply dual EMA to each indicator
    for ind_name, matrix in indicators.items():
        # EMA short→long (process periods 1→180)
        ema_short_first = np.full(n, np.nan)
        for i in range(max_period, n):
            row = matrix[i, :]
            valid_mask = ~np.isnan(row)
            if valid_mask.sum() > 0:
                valid_vals = row[valid_mask]
                # EMA across periods (short to long)
                ema_val = valid_vals[0]
                for v in valid_vals[1:]:
                    ema_val = EMA_ALPHA * v + (1 - EMA_ALPHA) * ema_val
                ema_short_first[i] = ema_val
        
        # EMA long→short (process periods 180→1)
        ema_long_first = np.full(n, np.nan)
        for i in range(max_period, n):
            row = matrix[i, :]
            valid_mask = ~np.isnan(row)
            if valid_mask.sum() > 0:
                valid_vals = row[valid_mask][::-1]  # Reverse: long→short
                ema_val = valid_vals[0]
                for v in valid_vals[1:]:
                    ema_val = EMA_ALPHA * v + (1 - EMA_ALPHA) * ema_val
                ema_long_first[i] = ema_val
        
        # Divergence
        divergence = ema_short_first - ema_long_first
        
        # Add to dataframe
        col_short = f'{ind_name}_ema_short_first'
        col_long = f'{ind_name}_ema_long_first'
        col_div = f'{ind_name}_ema_divergence'
        
        df[col_short] = ema_short_first
        df[col_long] = ema_long_first
        df[col_div] = divergence
        
        dual_ema_cols.extend([col_short, col_long, col_div])
    
    # Also add returns-based EMA (simpler, direct on returns)
    returns_ema_short = np.full(n, np.nan)
    returns_ema_long = np.full(n, np.nan)
    
    for i in range(max_period, n):
        window = returns[i-max_period:i]
        # Short first
        ema_val = window[0]
        for v in window[1:]:
            ema_val = EMA_ALPHA * v + (1 - EMA_ALPHA) * ema_val
        returns_ema_short[i] = ema_val
        # Long first
        ema_val = window[-1]
        for v in window[-2::-1]:
            ema_val = EMA_ALPHA * v + (1 - EMA_ALPHA) * ema_val
        returns_ema_long[i] = ema_val
    
    df['returns_ema_short_first'] = returns_ema_short
    df['returns_ema_long_first'] = returns_ema_long
    df['returns_ema_divergence'] = returns_ema_short - returns_ema_long
    dual_ema_cols.extend(['returns_ema_short_first', 'returns_ema_long_first', 'returns_ema_divergence'])
    
    return df, dual_ema_cols


def create_risk_guard_features(df):
    """
    Create composite risk guard features using ONLY signals with clear deviation
    from base rate (< 47% or > 58% UP rate). Signals in 47-58% range are noise.
    
    Returns:
      df: DataFrame with added risk guard features
      risk_cols: List of new column names
    """
    risk_cols = []
    
    # Check which columns exist
    has_hmm = 'hmm_regime' in df.columns
    has_hmm4_anomaly = 'HMM4_if_is_anomaly' in df.columns
    has_v_stable = 'V_hmm_stable_5d' in df.columns
    has_v_transitions = 'V_hmm_transitions_5d' in df.columns
    has_momentum = 'momentum_3d' in df.columns
    
    # ════════════════════════════════════════════════════════════════════════
    # 1. RISK SCORE: Only signals with < 47% UP rate (truly bearish)
    # ════════════════════════════════════════════════════════════════════════
    risk_score = np.zeros(len(df))
    
    # Create shifted regime for transition detection
    if has_hmm:
        prev_regime = df['hmm_regime'].shift(1)
        
        # hmm_regime=2: 31.6% UP → weight 0.6 (strongest!)
        risk_score += (df['hmm_regime'] == 2).astype(float).values * 0.6
        
        # hmm 1→2 transition: 33.3% UP → weight 0.5
        hmm_1_to_2 = ((prev_regime == 1) & (df['hmm_regime'] == 2)).astype(float).values
        risk_score += hmm_1_to_2 * 0.5
        
        # hmm 0→1 transition: 42.3% UP → weight 0.3
        hmm_0_to_1 = ((prev_regime == 0) & (df['hmm_regime'] == 1)).astype(float).values
        risk_score += hmm_0_to_1 * 0.3
        
        # hmm 1→0 transition: 42.9% UP → weight 0.3
        hmm_1_to_0 = ((prev_regime == 1) & (df['hmm_regime'] == 0)).astype(float).values
        risk_score += hmm_1_to_0 * 0.3
    
    # V_hmm_transitions_5d=2: 34.6% UP → weight 0.5
    if has_v_transitions:
        risk_score += (df['V_hmm_transitions_5d'] == 2).astype(float).values * 0.5
    
    # V_hmm_stable_5d=0: 38.2% UP → weight 0.4
    if has_v_stable:
        risk_score += (df['V_hmm_stable_5d'] == 0).astype(float).values * 0.4
    
    # HMM4 anomaly APPEARANCE: 40.0% UP → weight 0.4
    # Note: This is a transition signal (appeared this row)
    if has_hmm4_anomaly:
        prev_hmm4 = df['HMM4_if_is_anomaly'].shift(1).fillna(0)
        hmm4_appeared = ((df['HMM4_if_is_anomaly'] == 1) & (prev_hmm4 == 0)).astype(float).values
        risk_score += hmm4_appeared * 0.4
    
    df['risk_guard_score'] = risk_score
    risk_cols.append('risk_guard_score')
    
    # Binary risk flags
    df['risk_guard_high'] = (risk_score >= 0.4).astype(int)
    df['risk_guard_extreme'] = (risk_score >= 0.6).astype(int)
    risk_cols.extend(['risk_guard_high', 'risk_guard_extreme'])
    
    # ════════════════════════════════════════════════════════════════════════
    # 2. BULLISH SCORE: Only signals with > 58% UP rate (truly bullish)
    # ════════════════════════════════════════════════════════════════════════
    bullish_score = np.zeros(len(df))
    
    if has_hmm:
        prev_regime = df['hmm_regime'].shift(1)
        
        # hmm 1→3 transition: 65.8% UP → weight 0.6 (strongest!)
        hmm_1_to_3 = ((prev_regime == 1) & (df['hmm_regime'] == 3)).astype(float).values
        bullish_score += hmm_1_to_3 * 0.6
        
        # hmm 3→1 transition: 60.0% UP → weight 0.4
        hmm_3_to_1 = ((prev_regime == 3) & (df['hmm_regime'] == 1)).astype(float).values
        bullish_score += hmm_3_to_1 * 0.4
        
        # hmm 3→0 transition: 58.3% UP → weight 0.3
        hmm_3_to_0 = ((prev_regime == 3) & (df['hmm_regime'] == 0)).astype(float).values
        bullish_score += hmm_3_to_0 * 0.3
    
    # momentum_3d crosses above zero: 59.2% UP → weight 0.4
    if has_momentum:
        prev_mom = df['momentum_3d'].shift(1)
        mom_cross_up = ((df['momentum_3d'] > 0) & (prev_mom <= 0)).astype(float).values
        bullish_score += mom_cross_up * 0.4
    
    df['bullish_boost_score'] = bullish_score
    risk_cols.append('bullish_boost_score')
    
    # Binary bullish flag
    df['bullish_boost_high'] = (bullish_score >= 0.4).astype(int)
    risk_cols.append('bullish_boost_high')
    
    # ════════════════════════════════════════════════════════════════════════
    # 3. LEGACY FLAGS (for model features, not for gating)
    # ════════════════════════════════════════════════════════════════════════
    # Safe entry: in regime 0 or 3, stable volatility, no transitions
    if has_hmm and has_v_stable:
        safe_mask = (
            df['hmm_regime'].isin([0, 3]) & 
            (df['V_hmm_stable_5d'] == 1)
        )
        df['risk_guard_safe'] = safe_mask.astype(int)
        risk_cols.append('risk_guard_safe')
    
    return df, risk_cols
