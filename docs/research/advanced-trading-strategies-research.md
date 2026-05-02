# Advanced Trading Strategies Research

**Date:** 2026-02-15  
**Purpose:** Improve backtest win rate from 36% to >50% to overcome 0.11% Bybit fees

---

## 1. Problem Statement

### Current State
- **Signal filters:** BB(20,2σ) + RSI(14) on 5m timeframe
- **Win rate:** 36% (improved from baseline 21%)
- **R:R ratio:** 3.4:1 (good)
- **Theoretical EV:** +0.03% per trade (barely positive)
- **After fees (0.11%):** Negative EV

### Required Improvement
- At 3.4:1 R:R, need ~25% win rate for breakeven
- At 0.11% fee hurdle, need **>50% win rate** for profitability
- Gap: +14 percentage points

---

## 2. Academic Research Summary

### 2.1 Triple Barrier Method (de Prado, AFML)

**Sources:**
- arXiv 2504.02249: "Triple Barrier Labeling for Financial Forecasting"
- arXiv 2411.12753: "New Approaches to Algorithmic Trading"

**Key Concepts:**
- Three barriers: Take-profit, Stop-loss, Time-limit
- Creates 3-class labels: WIN / LOSS / TIMEOUT
- Better than fixed-time labeling for ML training
- Achieves balanced label distribution (~35/30/35 split)

**Implementation Notes:**
- Use high/low prices for barrier detection (not just close)
- If both TP and SL hit same day → label as TIMEOUT
- Optimize time horizon + TP/SL thresholds for balance

**Relevance to Our Project:**
- Replace current binary outcome labels
- Better training signal for ML models
- Our current 36% win rate might improve with balanced training

```python
# Triple Barrier Pseudo-code
def triple_barrier_label(entry_price, tp_pct, sl_pct, max_bars):
    for bar in range(max_bars):
        if high[bar] >= entry_price * (1 + tp_pct):
            return "TAKE_PROFIT"
        if low[bar] <= entry_price * (1 - sl_pct):
            return "STOP_LOSS"
    return "TIME_EXIT"
```

---

### 2.2 Meta-Labeling (de Prado, AFML)

**Sources:**
- "Does Meta Labeling Add to Signal Efficacy?" (Hudson Thames / QuantConnect)
- mlfinlab, finmlkit GitHub implementations

**Key Concepts:**
- **Primary Model:** Generates direction signals (buy/sell) - we already have this (BB+RSI)
- **Secondary Model (Meta):** Predicts whether the signal will be profitable
- Trade only when meta-model confidence exceeds threshold (e.g., 60%)

**Why It Works:**
- Primary model identifies WHEN to consider trading
- Meta-model filters to only HIGH-QUALITY signals
- Reduces false positives (unprofitable signals that look good)

**Implementation:**
```python
# Meta-Labeling Workflow
1. Generate primary signals (BB enters oversold/overbought zone)
2. For each signal, extract features:
   - Signal features (RSI value, distance from band, volume, etc.)
   - Market context (volatility, trend strength, time of day)
3. Label each signal: 1 = hit TP, 0 = hit SL or timeout
4. Train gradient boosting classifier on these features
5. At inference: only trade when meta_model.predict_proba() > 0.6
```

**Expected Improvement:**
- Research shows out-of-sample improvement
- Can improve precision without sacrificing recall significantly
- Key: avoid overfitting with proper walk-forward validation

---

### 2.3 Regime Detection (Hidden Markov Model)

**Sources:**
- arXiv 2107.05535: "Predicting Risk-adjusted Returns using HMM"
- arXiv 2407.19858: "Integrating HMMs with Neural Networks"
- arXiv 2006.08307: "HMM for Momentum Trading"
- arXiv 2208.11574: "Improving Markov-Switching Models"

**Key Concepts:**
- Markets operate in different regimes: Bull / Bear / High-Volatility
- HMM captures volatility clustering, fat tails, time-varying correlations
- Trade strategies aligned with current regime

**For Our Mean-Reversion Strategy:**
- Mean-reversion works BEST in ranging/low-volatility regimes
- Fails in trending/high-volatility regimes
- Filter: only trade when HMM predicts "mean-reverting" regime

**HMM Features:**
- Returns (rolling)
- Volatility (rolling, realized)
- Correlation with market
- Volume ratios

**Implementation:**
```python
from hmmlearn import GaussianHMM

# Train HMM with 3 states (bull, bear, ranging)
model = GaussianHMM(n_components=3, covariance_type="full")
model.fit(features)  # returns, volatility, etc.

# Predict regime
regime = model.predict(current_features)

# Only trade if regime == RANGING (or however we label it)
if regime == MEAN_REVERTING_REGIME:
    execute_trade()
```

---

### 2.4 Gradient Boosting Models (XGBoost / LightGBM / CatBoost)

**Sources:**
- arXiv 2409.03674: "Practical Forecasting of Cryptocoins Timeseries"
- arXiv 2407.18334: "41 ML Models for Bitcoin Trading" (RFC best consistency)
- arXiv 2407.11786: "Cryptocurrency Price Forecasting Using XGBoost"

**Key Findings:**
- XGBoost/LightGBM/CatBoost predict BTC/ETH with high accuracy
- Fast to train → enables walk-forward validation
- Feature importance identifies predictive signals
- Random Forest Classifier shows best consistency across markets

**For Meta-Model:**
- Use gradient boosting for meta-labeling classifier
- Input: signal features + market context
- Output: probability signal will hit TP

**Recommended Features:**
- RSI value at signal
- Distance from BB mid (in σ)
- ATR (volatility)
- Volume ratio (vs 20-bar average)
- Hour of day (crypto has 24h patterns)
- Day of week
- BB width (squeeze detection)
- Recent momentum (1h, 4h return)

---

### 2.5 Deep Reinforcement Learning

**Sources:**
- arXiv 2411.01456: "MC-DDPG Agent Trading" - 67% win rate, 48% profit
- arXiv 2109.14789: "Bitcoin Strategy Based on Deep RL"

**Key Concepts:**
- Monte Carlo DDPG: combines RL with tree search
- PPO + LSTM: learns features automatically
- Can learn complex non-linear relationships

**Pros/Cons:**
| Pros | Cons |
|------|------|
| Learns from raw data | Complex to implement |
| Adapts to regime changes | Requires extensive training |
| No manual feature engineering | Risk of overfitting |
| High reported win rates (67%) | Simulation-to-reality gap |

**Recommendation:** 
- Try gradient boosting first (simpler, faster)
- RL for Phase 2 if gradient boosting insufficient

---

## 3. Implementation Priority

### Phase 1: Meta-Labeling (1-2 days)
**Rationale:** Fastest to implement, proven effective, uses existing signals

**Steps:**
1. Label historical signals: 1 = hit TP, 0 = hit SL/timeout
2. Extract features for each signal (RSI, vol, time, etc.)
3. Train LightGBM classifier with walk-forward validation
4. Filter: only trade when P(TP) > 0.6

**Expected Result:** Improve precision by filtering low-quality signals

---

### Phase 2: Regime Detection (1-2 days)
**Rationale:** Additional filter, orthogonal to meta-labeling

**Steps:**
1. Train HMM on {returns, volatility, volume} with 2-3 states
2. Identify which state is "mean-reverting" (lowest volatility + balanced returns)
3. Only trade when in mean-reverting regime
4. Combine with meta-labeling for stacked filter

**Expected Result:** Avoid trading during trend-following periods

---

### Phase 3: Triple Barrier Training (1 day)
**Rationale:** Better labels for meta-model training

**Steps:**
1. Replace binary outcome labels with 3-class triple barrier
2. Retrain meta-model with new labels
3. Test if 3-class → 2-class (ignore TIMEOUT) improves

**Expected Result:** More robust meta-model

---

### Phase 4: Advanced (Optional, 3+ days)
- Deep RL (PPO/DDPG) if Phase 1-3 insufficient
- Multi-timeframe voting (5m, 15m, 1h signals agree)
- Funding rate integration (crypto-specific edge)
- Order flow features (buy/sell imbalance)

---

## 4. Open Source Resources

### FinMLKit (Recommended)
- **Repo:** github.com/quantscious/finmlkit
- **Language:** Python + Numba
- **Features:** Triple barrier, meta-labeling, sample weighting
- **Pros:** Fast (Numba), well-documented, based on de Prado

### mlfinlab
- **Repo:** Hudson & Thames
- **Features:** Full AFML implementation
- **Note:** Some features behind paywall

### hmmlearn
- **Install:** `pip install hmmlearn`
- **Use for:** Regime detection HMM

---

## 5. Validation Protocol

### Walk-Forward Validation (Critical)
- Train on window T, predict on T+1
- Roll forward, never look ahead
- Match live trading conditions

### Metrics to Track
| Metric | Target |
|--------|--------|
| Win Rate | >50% (after fees) |
| Precision | >0.5 (true positive / predicted positive) |
| Recall | Acceptable trade count |
| Sharpe | >1.0 annualized |
| Max Drawdown | <20% |

### A/B Testing
- Baseline: current BB+RSI signals (36% win rate)
- Treatment: meta-labeled signals
- Significance: >100 trades per cohort

---

## 6. Risk Considerations

1. **Overfitting:** Use strict temporal validation (no shuffle)
2. **Regime Shifts:** Market behavior changes over time
3. **Fee Assumptions:** 0.11% may increase (check VIP tier)
4. **Slippage:** Not modeled yet, typically 1-5 bps on liquid pairs
5. **Latency:** Signal-to-execution delay

---

## 7. Next Steps

1. [ ] Implement meta-labeling in notebook
2. [ ] Train LightGBM meta-model with walk-forward
3. [ ] Evaluate precision/recall tradeoff
4. [ ] Add regime detection filter
5. [ ] Run full backtest with both filters
6. [ ] Document results

---

## References

1. de Prado, M. L. (2018). Advances in Financial Machine Learning. Wiley.
2. arXiv 2107.05535 - HMM for Risk-adjusted Returns
3. arXiv 2407.19858 - HMM + Neural Networks
4. arXiv 2409.03674 - Gradient Boosting for Crypto
5. arXiv 2411.01456 - MC-DDPG Trading Agent
6. arXiv 2411.12753 - Triple Barrier Labeling
7. arXiv 2504.02249 - Korean Stocks Triple Barrier
