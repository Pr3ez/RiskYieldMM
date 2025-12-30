# Bybit Market Data Sources - Technical Analysis Guide

## Overview

The updated `fetch_bybit_market_data.py` script now fetches **6 complementary data sources** that provide rich information for building technical indicators and training ML models.

## Data Sources & Their Value

### 1. **OHLCV Klines** (Standard Candlesticks)
**Fields**: `timestamp, open, high, low, close, volume, turnover, interval`

**Use for:**
- **Price-based indicators**: SMA, EMA, MACD, RSI, Bollinger Bands
- **Volume indicators**: OBV, VWAP, Volume Profile, MFI
- **Volatility indicators**: ATR, Bollinger Band Width, Keltner Channels
- **Momentum**: ROC, Stochastic, Williams %R
- **Pattern recognition**: Candlestick patterns, chart patterns

**Why turnover is valuable:**
- Turnover = Price × Volume (in quote currency)
- Better for dollar-weighted analysis
- Useful for calculating true VWAP
- Identifies whale activity vs retail

---

### 2. **Funding Rate** (Perpetuals Only)
**Fields**: `timestamp, symbol, fundingRate, fundingRateTimestamp`

**Use for:**
- **Sentiment indicator**: Positive = longs paying shorts (bullish bias), Negative = shorts paying longs (bearish bias)
- **Extreme readings**: High funding often precedes reversals (funding squeeze)
- **Divergences**: Price up + funding down = weakening trend
- **Mean reversion signals**: Extreme funding rates tend to revert

**Model Features:**
```python
# Example derived features
funding_change = funding_rate.diff()
funding_ema = funding_rate.ewm(span=8).mean()
funding_zscore = (funding_rate - funding_rate.rolling(24).mean()) / funding_rate.rolling(24).std()
extreme_funding = (abs(funding_rate) > 0.01).astype(int)  # Binary flag
```

**Trading Context:**
- Updated every 8 hours (typically 00:00, 08:00, 16:00 UTC)
- Ranges typically: -0.05% to +0.05% per 8h period
- Extreme values (>0.1% or <-0.1%) signal high sentiment imbalance

---

### 3. **Open Interest** (Derivatives Only)
**Fields**: `timestamp, symbol, openInterest, timestamp_ms`

**Use for:**
- **Trend confirmation**: Rising OI + rising price = strong uptrend
- **Trend weakness**: Falling OI + rising price = weak move (shorts covering)
- **Liquidation cascades**: Sharp OI drops = mass liquidations
- **Volume divergence**: Price move + flat OI = low conviction

**Model Features:**
```python
# Derived features
oi_change = open_interest.pct_change()
oi_volume_ratio = open_interest / volume
oi_trend = open_interest.ewm(span=24).mean()
oi_acceleration = oi_change.diff()

# Multi-signal
price_up_oi_up = ((close.pct_change() > 0) & (oi_change > 0)).astype(int)
price_down_oi_down = ((close.pct_change() < 0) & (oi_change < 0)).astype(int)
```

**Trading Context:**
- High OI = more leverage in system = higher volatility risk
- OI increasing with price = healthy trend
- OI decreasing with price = liquidation cascade

---

### 4. **Mark Price** (Derivatives Only)
**Fields**: `timestamp, open, high, low, close, timestamp_ms`

**Use for:**
- **Fair value reference**: Mark price = index + premium (funding-based adjustment)
- **Liquidation calculations**: Bybit uses mark price for liquidations, not last price
- **Price manipulation detection**: Last price vs mark price deviation
- **Premium/discount analysis**: Compare to index to see perpetual bias

**Model Features:**
```python
# Deviation analysis
mark_last_spread = mark_price - last_price
mark_last_spread_pct = (mark_price - last_price) / last_price * 100
spread_volatility = mark_last_spread.rolling(24).std()

# Manipulation signals
large_deviation = (abs(mark_last_spread_pct) > 0.5).astype(int)
```

**Why it matters:**
- Prevents stop-hunting and manipulation-based liquidations
- More stable than last traded price
- Critical for risk management and position sizing

---

### 5. **Index Price**
**Fields**: `timestamp, open, high, low, close, timestamp_ms`

**Use for:**
- **Spot-futures arbitrage**: Compare perpetual price to spot index
- **Premium/discount calculation**: Perp price - index price = premium
- **Multi-exchange price**: Bybit's index aggregates Binance, Coinbase, Kraken, etc.
- **Manipulation-free reference**: Can't be manipulated by single exchange

**Model Features:**
```python
# Basis analysis
basis = last_price - index_price
basis_pct = (last_price - index_price) / index_price * 100
basis_ema = basis.ewm(span=24).mean()

# Arbitrage signals
overvalued = (basis_pct > 1.0).astype(int)  # Perp trading above fair value
undervalued = (basis_pct < -1.0).astype(int)  # Perp trading below fair value
```

**Trading Context:**
- Index typically = weighted average of multiple spot exchanges
- Perpetual should trade close to index (within funding rate adjustment)
- Large deviations = arbitrage opportunity or market stress

---

### 6. **Premium Index** (Perpetuals Only)
**Fields**: `timestamp, open, high, low, close, timestamp_ms`

**Use for:**
- **Funding rate prediction**: Premium index drives next funding rate
- **Sentiment gauge**: Persistent premium = bullish, persistent discount = bearish
- **Mean reversion**: Extreme premiums tend to correct
- **Early warning**: Premium spike before funding collection

**Model Features:**
```python
# Premium analysis
premium_ma = premium_index.rolling(24).mean()
premium_std = premium_index.rolling(24).std()
premium_zscore = (premium_index - premium_ma) / premium_std

# Reversion signals
extreme_premium = (premium_zscore > 2).astype(int)
extreme_discount = (premium_zscore < -2).astype(int)
```

**Relationship to Funding:**
```
Next Funding Rate ≈ Premium Index / (Funding Interval)
```

---

## Advanced Indicator Examples

### Multi-Source Momentum Indicator
```python
# Combine price momentum with market structure
price_momentum = close.pct_change(24)
oi_momentum = open_interest.pct_change(24)
funding_momentum = funding_rate.diff()

# Composite signal
strong_long = (
    (price_momentum > 0.02) &      # Price up 2%
    (oi_momentum > 0.05) &         # OI up 5%
    (funding_rate > 0) &           # Longs paying
    (basis > 0)                    # Perp premium to spot
).astype(int)
```

### Liquidation Risk Indicator
```python
# Identify conditions for liquidation cascades
high_leverage = (open_interest / volume.rolling(24).mean()) > 10
extreme_funding = abs(funding_rate) > 0.01
price_volatility = close.pct_change().rolling(24).std()

liquidation_risk = (
    high_leverage & 
    extreme_funding & 
    (price_volatility > price_volatility.rolling(168).mean())
).astype(int)
```

### Arbitrage Opportunity Detector
```python
# Spot-futures arbitrage
basis_zscore = (basis - basis.rolling(168).mean()) / basis.rolling(168).std()
funding_zscore = (funding_rate - funding_rate.rolling(24).mean()) / funding_rate.rolling(24).std()

# Cash-and-carry opportunity (basis > funding cost)
arb_long_perp = (basis_zscore < -2) & (funding_zscore < 0)  # Perp cheap, funding negative
arb_short_perp = (basis_zscore > 2) & (funding_zscore > 0.5)  # Perp expensive, funding high
```

### Market Regime Classifier
```python
# Classify market conditions for regime-aware models
regime = pd.DataFrame()
regime['trending'] = (
    (abs(close.pct_change(24)) > 0.05) & 
    (oi_change > 0)
).astype(int)

regime['ranging'] = (
    (abs(close.pct_change(24)) < 0.02) & 
    (abs(oi_change) < 0.02)
).astype(int)

regime['liquidation'] = (
    (abs(close.pct_change(1)) > 0.02) & 
    (oi_change < -0.05)
).astype(int)

regime['manipulation'] = (
    abs(mark_last_spread_pct) > 0.5
).astype(int)
```

---

## Data Quality Indicators

### Completeness Check
```python
def check_data_quality(df, interval_minutes):
    """Check for gaps and anomalies."""
    df = df.sort_values('timestamp')
    
    # Time gaps
    time_diffs = df['timestamp'].diff().dt.total_seconds() / 60
    expected_diff = interval_minutes
    gaps = (time_diffs > expected_diff * 1.5).sum()
    
    # Zero values
    zero_volume = (df['volume'] == 0).sum()
    zero_oi = (df['openInterest'] == 0).sum() if 'openInterest' in df else 0
    
    # Outliers (price jumps > 10%)
    price_jumps = (abs(df['close'].pct_change()) > 0.10).sum()
    
    return {
        'total_records': len(df),
        'gaps': gaps,
        'zero_volume': zero_volume,
        'zero_oi': zero_oi,
        'price_jumps': price_jumps,
        'start_date': df['timestamp'].min(),
        'end_date': df['timestamp'].max()
    }
```

---

## Feature Engineering Pipeline

### Step 1: Align All Data Sources
```python
# Merge all data on timestamp
df = klines.copy()
df = df.merge(funding_rate[['timestamp', 'fundingRate']], on='timestamp', how='left')
df = df.merge(open_interest[['timestamp', 'openInterest']], on='timestamp', how='left')
df = df.merge(mark_price[['timestamp', 'close']].rename(columns={'close': 'mark_price'}), on='timestamp', how='left')
df = df.merge(index_price[['timestamp', 'close']].rename(columns={'close': 'index_price'}), on='timestamp', how='left')
df = df.merge(premium_index[['timestamp', 'close']].rename(columns={'close': 'premium'}), on='timestamp', how='left')

# Forward fill funding (updated every 8h)
df['fundingRate'] = df['fundingRate'].fillna(method='ffill')
```

### Step 2: Generate Technical Indicators
```python
import pandas_ta as ta

# Price-based
df['rsi'] = ta.rsi(df['close'], length=14)
df['macd'], df['macd_signal'], df['macd_hist'] = ta.macd(df['close'])
df['bb_upper'], df['bb_mid'], df['bb_lower'] = ta.bbands(df['close'])

# Volume-based
df['vwap'] = (df['turnover'].cumsum() / df['volume'].cumsum())
df['mfi'] = ta.mfi(df['high'], df['low'], df['close'], df['volume'])

# Market structure
df['basis'] = df['close'] - df['index_price']
df['basis_pct'] = df['basis'] / df['index_price'] * 100
df['oi_change_pct'] = df['openInterest'].pct_change()
df['funding_ma8'] = df['fundingRate'].rolling(8).mean()
```

### Step 3: Lagged Features
```python
# Create lookback features for ML models
for lag in [1, 3, 6, 12, 24]:
    df[f'return_{lag}h'] = df['close'].pct_change(lag)
    df[f'oi_change_{lag}h'] = df['openInterest'].pct_change(lag)
    df[f'volume_change_{lag}h'] = df['volume'].pct_change(lag)
```

### Step 4: Target Variables
```python
# Forward-looking returns for prediction
for horizon in [1, 3, 6, 12, 24]:
    df[f'target_return_{horizon}h'] = df['close'].pct_change(horizon).shift(-horizon)
    df[f'target_direction_{horizon}h'] = (df[f'target_return_{horizon}h'] > 0).astype(int)
```

---

## Model Training Strategy

### Feature Categories
1. **Price features**: OHLC, technical indicators (RSI, MACD, etc.)
2. **Volume features**: Volume, turnover, volume ratios
3. **Market microstructure**: Funding, OI, basis, premium
4. **Volatility features**: ATR, realized volatility, implied spreads
5. **Time features**: Hour, day of week, funding cycle position

### Sample Model Input Matrix
```python
feature_cols = [
    # Price
    'close', 'rsi', 'macd', 'bb_width',
    # Volume  
    'volume', 'vwap', 'mfi',
    # Market structure
    'fundingRate', 'funding_ma8', 'oi_change_pct', 'basis_pct', 'premium',
    # Lagged returns
    'return_1h', 'return_6h', 'return_24h',
    # Volatility
    'atr', 'realized_vol_24h'
]

X = df[feature_cols].fillna(0)
y = df['target_direction_6h']  # Predict 6h direction
```

---

## Why This Data is Superior

### Compared to OHLCV Only:
❌ **OHLCV only**: Can't detect:
- Overleveraged markets (OI)
- Sentiment extremes (funding)
- Manipulation (mark vs last)
- Arbitrage opportunities (basis)

✅ **Multi-source data**: Enables:
- **Regime detection**: Identify trending vs ranging vs liquidation events
- **Risk management**: Avoid entering during high liquidation risk
- **Sentiment analysis**: Funding shows smart money positioning
- **Fair value**: Compare perpetual vs spot for mispricing

### Real-World Alpha Sources:
1. **Funding rate arbitrage**: Earn funding by holding opposite position on spot
2. **Basis trading**: Perp-spot arbitrage when basis exceeds funding cost
3. **Liquidation anticipation**: Exit before cascades, enter after panic
4. **Manipulation detection**: Avoid trades during price-mark divergence

---

## Data Storage Structure

```
fetchingByBit/
├── sorted-1m-bybit-linear/          # 1-minute OHLCV klines
├── sorted-5m-bybit-linear/          # 5-minute OHLCV klines
├── sorted-1h-bybit-linear/          # 1-hour OHLCV klines
├── funding-rate-bybit-linear/       # Funding rate history
│   └── btcusdt_funding_rate.parquet
├── open-interest-1m-bybit-linear/   # 1-minute OI
├── open-interest-1h-bybit-linear/   # 1-hour OI
├── mark-price-1m-bybit-linear/      # 1-minute mark price
├── index-price-1m-bybit-linear/     # 1-minute index price
└── premium-price-1m-bybit-linear/   # 1-minute premium index
```

---

## Next Steps

1. **Run the script**: Fetch all data sources
2. **Align timestamps**: Merge data on common timeframe
3. **Engineer features**: Create indicators from multiple sources
4. **Train models**: Use rich feature set for predictions
5. **Backtest**: Validate on historical data
6. **Live trading**: Deploy with full market context

---

**Remember**: More data sources = better market understanding = higher edge potential!
