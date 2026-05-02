# Backtest Improvements: Research-Based Recommendations

## 📋 Executive Summary

**Current Problem:**
- Random entry (every candle open) with constant TP/SL achieves ~46% batch profitability
- This is essentially a coin flip minus fees
- Best config: 1m LONG TP=3%/SL=2.5% → -668% net return after 0.11% fees
- **Root cause:** No entry signal = no edge

**Required improvement:** Avg return per trade must exceed **0.11%** (VIP0 fee threshold)

---

## 🔬 Research Sources

| Source | Paper/Topic | Key Insight |
|--------|-------------|-------------|
| arXiv 2109.12142 | Periodicity in Cryptocurrency Volatility | BTC volatility peaks ~16 UTC, bottoms ~5 UTC |
| arXiv 2601.19504 | Hybrid AI Trading System | Bollinger Bands + RSI for mean-reversion, MACD for trend |
| arXiv 2112.08534 | Momentum Transformer | Combined momentum + mean-reversion with regime detection |
| arXiv 2510.15949 | ATLAS Adaptive Trading | ATR-based volatility-aware stop placement |
| arXiv 2511.08571 | Forecast-to-Fill | ATR-based exits + volatility targeting |
| arXiv 2408.03594 | Order Flow Imbalance | OFI predicts short-term volatility and direction |
| arXiv 2509.14385 | Regime-Aware RL | HMM regime detection improves risk-adjusted returns |
| arXiv 2402.05272 | Downside Risk Reduction | Regime-switching signals reduce drawdowns |

---

## 🎯 Improvement Categories

### 1️⃣ ENTRY SIGNAL FILTERS (Most Critical)

**Problem:** Currently entering at EVERY candle open → no selectivity

**Research-backed solutions:**

#### A) Bollinger Band Entry Zones
```
Source: arXiv 2601.19504, arXiv 2412.15448

Logic:
- LONG entry: Price touches/crosses BELOW lower band (mean-reversion)
- SHORT entry: Price touches/crosses ABOVE upper band (mean-reversion)
- Skip trades when price is in the middle zone (no edge)

Parameters to test:
- BB period: 20, 50
- BB std: 1.5, 2.0, 2.5
- Entry zone: touch vs cross vs % outside
```

#### B) RSI Oversold/Overbought Filter
```
Source: arXiv 2601.19504, arXiv 2204.05781

Logic:
- LONG only when RSI < 30 (oversold)
- SHORT only when RSI > 70 (overbought)
- Skip middle range (30-70)

Parameters to test:
- RSI period: 14, 21
- Threshold: 20/80 (strict) vs 30/70 (loose)
```

#### C) Volume Spike Confirmation
```
Source: arXiv 2109.12142, arXiv 2505.08180

Logic:
- Only enter when volume > X × average volume
- High volume = higher conviction moves
- Filters out low-liquidity noise

Parameters to test:
- Volume MA period: 20, 50
- Spike threshold: 1.5x, 2.0x, 3.0x
```

#### D) Order Flow Imbalance (Advanced)
```
Source: arXiv 2408.03594, arXiv 2411.08382

Logic:
- Calculate buy_volume / (buy_volume + sell_volume)
- LONG when imbalance > 0.6 (buying pressure)
- SHORT when imbalance < 0.4 (selling pressure)

Note: Requires tick data or taker buy/sell volume
```

---

### 2️⃣ ADAPTIVE TP/SL (Volatility-Based)

**Problem:** Fixed TP/SL ignores market conditions

**Research-backed solutions:**

#### A) ATR-Based Stops
```
Source: arXiv 2510.15949, arXiv 2511.08571

Logic:
- TP = entry_price ± ATR(14) × tp_multiplier
- SL = entry_price ∓ ATR(14) × sl_multiplier

Benefits:
- Wider stops in volatile periods → fewer whipsaws
- Tighter stops in calm periods → faster exits
- Automatically adapts to regime

Parameters to test:
- ATR period: 14, 21
- TP multiplier: 1.5, 2.0, 2.5, 3.0
- SL multiplier: 1.0, 1.5, 2.0
```

#### B) Parkinson Volatility Scaling
```
Source: arXiv 2204.05781

Logic:
- Parkinson vol = sqrt(1/(4*ln(2)) * ln(H/L)^2)
- Scale TP/SL by rolling Parkinson volatility
- More accurate than close-to-close volatility for intraday
```

---

### 3️⃣ TIME-OF-DAY FILTERS

**Problem:** BTC volatility has strong intraday seasonality

**Research finding:**
```
Source: arXiv 2109.12142 (Hansen et al.)

"Volatility tends to be high around 16 UTC and hit bottom near 5 UTC"

Implications:
- Trading during high-volatility hours = more TP/SL hits
- 08:00-16:00 UTC batch might have different optimal params than 00:00-08:00
```

**Implementation:**
```python
# Add to batch data
8h_session = batch_start.hour  # 0, 8, or 16

# Test different TP/SL per session
session_params = {
    0:  {'tp': 2.0, 'sl': 1.5},   # Low vol (00-08 UTC)
    8:  {'tp': 2.5, 'sl': 2.0},   # Rising vol
    16: {'tp': 3.0, 'sl': 2.5},   # Peak vol (16-00 UTC)
}
```

---

### 4️⃣ REGIME DETECTION

**Problem:** Strategy performs differently in trending vs ranging markets

**Research-backed solutions:**

#### A) HMM Regime Detection
```
Source: arXiv 2509.14385, arXiv 2310.04536

Logic:
- Fit 2-3 state HMM on returns + volatility
- States typically emerge as: Bull, Bear, Sideways
- Adjust strategy per regime:
  - Bull: LONG bias, wider TP
  - Bear: SHORT bias, tighter SL
  - Sideways: Mean-reversion only
```

#### B) Volatility Regime Filter
```
Source: arXiv 2601.19504, arXiv 2402.05272

Simple implementation:
- rolling_vol = returns.rolling(20).std()
- vol_percentile = rolling_vol.rank(pct=True)

- High vol regime (>70th %): Use momentum strategy
- Low vol regime (<30th %): Use mean-reversion strategy
- Middle: Skip or reduce position size
```

---

### 5️⃣ TREND FILTERS

**Problem:** Mean-reversion fails in strong trends

**Research-backed solutions:**

#### A) EMA Trend Filter
```
Source: arXiv 2601.19504

Logic:
- Calculate EMA(50) and EMA(200)
- LONG only when price > EMA(50) > EMA(200)
- SHORT only when price < EMA(50) < EMA(200)
- Skip when EMAs are crossed (transition period)
```

#### B) ADX Strength Filter
```
Source: arXiv 2204.05781

Logic:
- ADX > 25: Strong trend → use momentum/trend-following
- ADX < 20: Weak trend → use mean-reversion
- 20-25: Transitional → reduce position size
```

---

## 📊 Implementation Priority

### Phase 1: Quick Wins (High Impact, Low Effort)
1. **Bollinger Band entry filter** — Most cited, easy to implement
2. **ATR-based TP/SL** — Automatic volatility adaptation
3. **Time-of-day params** — Already have 8h batches

### Phase 2: Signal Quality
4. **RSI filter** — Adds confirmation to BB signals
5. **Volume spike confirmation** — Filters low-quality entries
6. **EMA trend filter** — Prevents counter-trend trades

### Phase 3: Advanced
7. **Regime detection (HMM)** — Requires more complex modeling
8. **Order Flow Imbalance** — Requires tick/taker data

---

## 🧮 Expected Impact

| Improvement | Expected Effect |
|-------------|-----------------|
| BB entry filter | Reduce trades by 80-90%, increase per-trade edge |
| ATR stops | Improve win rate by 5-10% |
| Time-of-day | Reduce batch variance |
| Regime filter | Avoid 20-30% of losing periods |

**Target:** 
- Reduce trades from ~7,600 to ~500-1,000 per period
- Increase avg return per trade from 0.02% to >0.15%
- Achieve >50% batch profitability

---

## 🔗 Key Papers to Read

1. **arXiv 2601.19504** - "Generating Alpha: A Hybrid AI-Driven Trading System"
   - Full framework combining BB, RSI, MACD, regime, sentiment
   
2. **arXiv 2112.08534** - "Trading with the Momentum Transformer"
   - Cited 33x, interpretable momentum + mean-reversion
   
3. **arXiv 2109.12142** - "Periodicity in Cryptocurrency Volatility"
   - Key for time-of-day effects in BTC
   
4. **arXiv 2510.15949** - "ATLAS: Adaptive Trading with LLM Agents"
   - ATR-based stop placement methodology
   
5. **arXiv 2408.03594** - "Forecasting high frequency order flow imbalance"
   - If you can get OFI data, this is powerful

---

## ⚠️ Caveats

1. **Overfitting risk** — More parameters = more risk of curve-fitting
2. **Look-ahead bias** — BB/RSI must use only past data at entry time
3. **Transaction costs** — All improvements must clear 0.11% threshold
4. **Regime changes** — What worked 2021-2023 may not work 2024+

**Validation approach:**
- Walk-forward testing (train on 1 year, test on next 6 months)
- Out-of-sample batch holdout (use 80% batches for param search, 20% for validation)
- Multiple seed testing for any ML components

---

## 📝 Next Steps

1. [ ] Implement Bollinger Band entry filter in backtest
2. [ ] Add ATR-based dynamic TP/SL
3. [ ] Compare batch profitability before/after
4. [ ] If profitable: add RSI confirmation
5. [ ] If still marginal: add time-of-day params
6. [ ] Document findings in session.md
