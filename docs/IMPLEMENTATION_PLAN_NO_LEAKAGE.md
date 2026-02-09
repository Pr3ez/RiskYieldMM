# Implementation Plan: Entry Signals & Adaptive TP/SL

## ⚠️ CRITICAL: Leakage Prevention Rules

**Every indicator must be calculated using ONLY data available at decision time:**

```
Entry decision at bar[i] OPEN:
├── CAN USE: bar[i-1].close, bar[i-1].high, bar[i-1].low, bar[i-1].volume
├── CAN USE: bar[i-k] for any k > 0 (all past bars)
├── CAN USE: bar[i].open (we enter AT open, so we know it)
├── CANNOT USE: bar[i].high, bar[i].low, bar[i].close, bar[i].volume
└── CANNOT USE: any bar[i+k] for k > 0 (future bars)
```

**Implementation pattern:**
```python
# CORRECT (no leakage)
bb_upper = close.shift(1).rolling(20).mean() + 2 * close.shift(1).rolling(20).std()
entry_signal = open < bb_upper  # Compare current OPEN to indicator from PREVIOUS close

# WRONG (leakage!)
bb_upper = close.rolling(20).mean() + 2 * close.rolling(20).std()
entry_signal = close < bb_upper  # Uses current bar's close to decide entry
```

---

## 📋 Implementation Phases

### Phase 1: Feature Engineering (No Leakage)

**Goal:** Add technical indicators to each bar, calculated from PAST data only

#### 1.1 Bollinger Bands
```python
# Calculate at each bar using PREVIOUS bar's data
window = 20
df = df.with_columns([
    # All calculations use shift(1) to reference previous bar's close
    pl.col("close").shift(1).rolling_mean(window).alias("bb_sma"),
    pl.col("close").shift(1).rolling_std(window).alias("bb_std"),
]).with_columns([
    (pl.col("bb_sma") + 2 * pl.col("bb_std")).alias("bb_upper"),
    (pl.col("bb_sma") - 2 * pl.col("bb_std")).alias("bb_lower"),
])

# Entry signals (decided at bar[i] open)
df = df.with_columns([
    (pl.col("open") < pl.col("bb_lower")).alias("signal_bb_long"),   # Price below lower band
    (pl.col("open") > pl.col("bb_upper")).alias("signal_bb_short"),  # Price above upper band
])
```

#### 1.2 RSI
```python
window = 14
df = df.with_columns([
    pl.col("close").shift(1).diff().alias("price_change"),
]).with_columns([
    pl.when(pl.col("price_change") > 0).then(pl.col("price_change")).otherwise(0).alias("gain"),
    pl.when(pl.col("price_change") < 0).then(-pl.col("price_change")).otherwise(0).alias("loss"),
]).with_columns([
    (pl.col("gain").rolling_mean(window) / 
     (pl.col("gain").rolling_mean(window) + pl.col("loss").rolling_mean(window) + 1e-10) * 100
    ).alias("rsi"),
])

# Entry signals
df = df.with_columns([
    (pl.col("rsi") < 30).alias("signal_rsi_oversold"),
    (pl.col("rsi") > 70).alias("signal_rsi_overbought"),
])
```

#### 1.3 ATR (for adaptive TP/SL)
```python
window = 14
df = df.with_columns([
    # True Range components (all from PREVIOUS bar)
    (pl.col("high").shift(1) - pl.col("low").shift(1)).alias("tr1"),
    (pl.col("high").shift(1) - pl.col("close").shift(2)).abs().alias("tr2"),
    (pl.col("low").shift(1) - pl.col("close").shift(2)).abs().alias("tr3"),
]).with_columns([
    pl.max_horizontal("tr1", "tr2", "tr3").alias("true_range"),
]).with_columns([
    pl.col("true_range").rolling_mean(window).alias("atr"),
])
```

#### 1.4 Volume Spike
```python
window = 20
df = df.with_columns([
    # Volume from PREVIOUS bar (current bar's volume unknown at entry)
    pl.col("volume").shift(1).rolling_mean(window).alias("vol_sma"),
]).with_columns([
    (pl.col("volume").shift(1) / pl.col("vol_sma")).alias("vol_ratio"),
    (pl.col("volume").shift(1) > 1.5 * pl.col("vol_sma")).alias("signal_vol_spike"),
])
```

#### 1.5 EMA Trend Filter
```python
df = df.with_columns([
    pl.col("close").shift(1).ewm_mean(span=20).alias("ema_20"),
    pl.col("close").shift(1).ewm_mean(span=50).alias("ema_50"),
]).with_columns([
    # Uptrend: price above EMA20 above EMA50
    ((pl.col("open") > pl.col("ema_20")) & (pl.col("ema_20") > pl.col("ema_50"))).alias("trend_up"),
    # Downtrend: price below EMA20 below EMA50
    ((pl.col("open") < pl.col("ema_20")) & (pl.col("ema_20") < pl.col("ema_50"))).alias("trend_down"),
])
```

---

### Phase 2: Signal Combination Logic

**Entry conditions (all must be TRUE to enter):**

#### LONG Entry:
```python
entry_long = (
    signal_bb_long &           # Price at/below lower BB
    signal_rsi_oversold &      # RSI < 30
    (signal_vol_spike | True) & # Optional: volume confirmation
    ~trend_down                 # Not in strong downtrend
)
```

#### SHORT Entry:
```python
entry_short = (
    signal_bb_short &          # Price at/above upper BB
    signal_rsi_overbought &    # RSI > 70
    (signal_vol_spike | True) & # Optional: volume confirmation
    ~trend_up                   # Not in strong uptrend
)
```

---

### Phase 3: Backtest Engine Modifications

#### 3.1 Add Signal Array to Backtest
```python
@njit(cache=True)
def backtest_single_batch_with_signals(
    ohlc: np.ndarray,          # (N, 4) - OHLC
    entry_signals: np.ndarray,  # (N,) - boolean, True = allowed to enter
    direction: int,
    tp_pct: float,
    sl_pct: float,
    fee_pct: float,
    max_bars: int
) -> tuple[int, int, int, float, float, float]:
    """Only enter when entry_signals[i] is True"""
    ...
    while i < n_bars:
        # SKIP if no entry signal
        if not entry_signals[i]:
            i += 1
            continue
        
        entry_price = ohlc[i, 0]  # Open
        # ... rest of trade logic
```

#### 3.2 Add ATR-Based Dynamic TP/SL
```python
@njit(cache=True)
def backtest_with_atr_stops(
    ohlc: np.ndarray,
    entry_signals: np.ndarray,
    atr_values: np.ndarray,     # Pre-calculated ATR at each bar
    direction: int,
    tp_atr_mult: float,         # TP = entry ± tp_atr_mult * ATR
    sl_atr_mult: float,         # SL = entry ∓ sl_atr_mult * ATR
    fee_pct: float,
    max_bars: int
) -> tuple[...]:
    ...
    while i < n_bars:
        if not entry_signals[i]:
            i += 1
            continue
        
        entry_price = ohlc[i, 0]
        current_atr = atr_values[i]
        
        if direction == 1:  # LONG
            tp_price = entry_price + tp_atr_mult * current_atr
            sl_price = entry_price - sl_atr_mult * current_atr
        else:  # SHORT
            tp_price = entry_price - tp_atr_mult * current_atr
            sl_price = entry_price + sl_atr_mult * current_atr
        
        # ... rest of exit logic
```

---

### Phase 4: Grid Search with Signals

**Parameters to optimize:**

| Parameter | Values to Test |
|-----------|----------------|
| BB period | 10, 20, 30 |
| BB std multiplier | 1.5, 2.0, 2.5 |
| RSI period | 7, 14, 21 |
| RSI thresholds | (20,80), (25,75), (30,70) |
| ATR period | 7, 14, 21 |
| TP ATR multiplier | 1.5, 2.0, 2.5, 3.0 |
| SL ATR multiplier | 1.0, 1.5, 2.0 |
| Volume spike threshold | 1.5x, 2.0x, 3.0x (or disabled) |

**Expected trade reduction:**
- BB filter alone: ~10-20% of bars have entry signal
- BB + RSI: ~2-5% of bars
- BB + RSI + Volume: ~1-3% of bars

---

### Phase 5: Validation Protocol

#### 5.1 Leakage Check
```python
def validate_no_leakage(df):
    """Verify all signals use only past data"""
    for i in range(100, len(df)):
        row = df.row(i, named=True)
        
        # BB should use data up to bar i-1
        expected_bb_upper = df["close"][i-20:i-1].mean() + 2 * df["close"][i-20:i-1].std()
        assert abs(row["bb_upper"] - expected_bb_upper) < 1e-6, f"BB leakage at row {i}"
        
        # Entry signal should only reference bar[i].open and indicators from bar[i-1]
        # ...
```

#### 5.2 Walk-Forward Validation
```
Training period: batches 0 - 3000 (2021-01 to 2023-07)
Validation period: batches 3000 - 4000 (2023-07 to 2024-06)
Test period: batches 4000 - 5574 (2024-06 to 2026-02)

1. Optimize params on Training
2. Validate on Validation (no re-tuning)
3. Final test on Test (completely untouched)
```

#### 5.3 Signal Quality Metrics
```python
# For each signal configuration, track:
metrics = {
    'total_signals': 0,      # How many entry signals generated
    'signals_per_batch': 0,  # Average signals per 8h batch
    'win_rate': 0,           # % of signals that hit TP
    'avg_return_per_signal': 0,  # Must be > 0.11% for profitability
    'batch_profit_rate': 0,  # % of batches with net profit
}
```

---

## 🔄 Implementation Order

### Step 1: Feature Engineering Cell (New)
- [ ] Add BB calculation (shift(1) for no leakage)
- [ ] Add RSI calculation (shift(1) for no leakage)
- [ ] Add ATR calculation (shift(1), shift(2) for no leakage)
- [ ] Add Volume ratio (shift(1) for no leakage)
- [ ] Add EMA trend filter (shift(1) for no leakage)
- [ ] Create combined entry signal columns

### Step 2: Update Backtest Engine
- [ ] Add `entry_signals` parameter to Numba functions
- [ ] Add `atr_values` parameter for dynamic TP/SL
- [ ] Skip bars where entry_signal is False
- [ ] Calculate TP/SL from ATR when ATR mode enabled

### Step 3: Grid Search with Signals
- [ ] Modify `run_grid_search_with_batch_stats` to accept signal array
- [ ] Add feature parameter grid (BB params, RSI params, etc.)
- [ ] Track signal-specific metrics

### Step 4: Validation
- [ ] Implement walk-forward split
- [ ] Run leakage validation
- [ ] Compare in-sample vs out-of-sample performance

---

## ⚠️ Common Leakage Mistakes to Avoid

| Mistake | Why It's Wrong | Correct Approach |
|---------|----------------|------------------|
| `close.rolling(20)` for BB | Uses current bar's close | `close.shift(1).rolling(20)` |
| `atr[i]` using `high[i], low[i]` | Uses current bar's H/L | Use `high[i-1], low[i-1]` |
| Entry decision using `close[i]` | Close unknown at entry | Use `open[i]` only |
| Volume spike using `volume[i]` | Current volume unknown | Use `volume[i-1]` |
| RSI using current bar | Same issue | Shift by 1 |

---

## 📊 Expected Outcomes

### Before (current baseline):
- Entry: Every candle open (no filter)
- Trades: ~7,600 per grid config
- Avg return/trade: 0.02%
- Batch profit rate: 45.8%
- Net return: -668%

### After (with BB + RSI filter):
- Entry: Only at BB extremes + RSI confirmation
- Expected trades: ~200-500 per config
- Target avg return/trade: >0.15%
- Target batch profit rate: >55%
- Target net return: >0%

### Success criteria:
1. Trade count reduced by 80%+
2. Avg return per trade > 0.11% (fee threshold)
3. Batch profit rate > 50%
4. Out-of-sample performance within 20% of in-sample

---

## 📝 Next Implementation Steps

1. **Create new notebook cell** for feature engineering
2. **Test feature calculations** on small sample (verify shift behavior)
3. **Validate no leakage** with manual spot-checks
4. **Modify backtest engine** to accept signals
5. **Run grid search** with signals enabled
6. **Compare results** to baseline
7. **Implement walk-forward** if initial results promising
