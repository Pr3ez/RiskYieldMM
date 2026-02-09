# Bybit Strategy ML Integration Guide

**Purpose:** Bridge the gap between the rule-based `bybitmodel.py` trading strategy and the ML-driven `main_wf.py` pipeline.

**Created:** 2026-02-03

---

## Table of Contents

1. [Strategy Analysis Summary](#1-strategy-analysis-summary)
2. [Target Design for ML Models](#2-target-design-for-ml-models)
3. [Feature Requirements for ML](#3-feature-requirements-for-ml)
4. [15m → 8h Data Merge (No Leakage)](#4-15m--8h-data-merge-no-leakage)
5. [Model Architecture Recommendations](#5-model-architecture-recommendations)
6. [Implementation Roadmap](#6-implementation-roadmap)
7. [Integration with main_wf.py](#7-integration-with-main_wfpy)

---

## 1. Strategy Analysis Summary

### 1.1 How Positions are Opened (from bybitmodel.py)

The live trading bot uses a **multi-timeframe Bollinger Band approach**:

| Direction | Entry Price Construction | Gate Condition |
|-----------|-------------------------|----------------|
| **LONG** | `midpoint_15 = (BBand_Lower_15m + BBand_Mid_15m) / 2` → use `max(midpoint_15, BBand_Lower_1h)` | 15m close ≤ entry_long |
| **SHORT** | `midpoint_5 = (BBand_Upper_5m + BBand_Mid_5m) / 2` → use `min(midpoint_5, BBand_Upper_1h)` | 5m close ≥ entry_short |

**Key Insight:** Entry triggers when price touches a pullback zone (lower BBand for longs, upper for shorts), using lower timeframes for precision.

### 1.2 Take-Profit Calculation

| Direction | New Entry TP | Dynamic Update (Position Management) |
|-----------|-------------|-------------------------------------|
| **LONG** | `SMA_20_1h` (must satisfy ≥ 1.006× entry) | `max(BBand_Upper_1h - Δ, BBand_Upper_4h - Δ)` where Δ = (upper - mid) / 5 |
| **SHORT** | `BBand_Lower_1h` (must satisfy ≤ 0.994× entry) | `min(BBand_Lower_1h + Δ, BBand_Lower_4h + Δ)` where Δ = (mid - lower) / 5 |

### 1.3 Stop-Loss Calculation

| Direction | New Entry SL | Dynamic Update |
|-----------|-------------|----------------|
| **LONG** | `entry_price - (1.5 × ATR_14)` | If close > BBand_Mid_1h: `BBand_Mid_1h - Δ_bottom` else: `entry - profit_dist / 3` |
| **SHORT** | `entry_price + (1.5 × ATR_14)` | If close < BBand_Mid_1h: `BBand_Mid_1h + Δ_top` else: `entry + profit_dist / 3` |

### 1.4 Leverage Calculation

Uses ATR/Bollinger risk-based sizing:
```
profit_dist = |take_profit - entry_price|
stop_dist = profit_dist / 3
loss_pct = stop_dist / entry_price
leverage = floor(risk_pct / loss_pct)  # risk_pct = 0.10 (10%)
```

### 1.5 Timeframe Usage Summary

| Timeframe | Purpose |
|-----------|---------|
| **1d** | Breakout skip filters only |
| **4h** | Regime classification, volatility gate, leverage sizing, dynamic SL/TP |
| **1h** | Core entry evaluation, TP targets, dynamic SL/TP |
| **15m** | LONG entry construction + gating |
| **5m** | SHORT entry construction + gating |

---

## 2. Target Design for ML Models

### 2.1 What Predictions Does This Strategy Need?

To deploy ML models that **support and enhance** this strategy, we need predictions for:

| Question | ML Target | Current Status | Recommended Action |
|----------|-----------|----------------|-------------------|
| "Will price reach entry zone?" | **entry_touch** | ❌ Not implemented | New target needed |
| "Which direction will win?" | `direction` | ✅ Exists (5-class) | Use as-is |
| "Should I trade?" | `strategy_label` | ✅ Exists (5-class) | Use as-is |
| "Will TP hit before SL?" | `triple_barrier` | ✅ Exists (3-class) | Use as-is |
| "What type of move?" | `path_label_5` | ✅ Exists (5-class) | Use as-is |
| "Pullback entry quality?" | `trade_setup` | ✅ Exists (4-class) | Use as-is |
| "What regime?" | `trend_regime` | ✅ Exists (binary) | Use as-is |
| "Vol going up/down?" | `volatility_regime` | ✅ Exists (binary) | Use as-is |

### 2.2 New Target: `bband_entry_touch`

This target predicts **whether price will touch the Bollinger Band entry zone** in the next 8h bar.

**Definition:**
```python
class BBandEntryTouch(IntEnum):
    NO_TOUCH = 0       # Price never reached entry zone
    TOUCH_LOWER = 1    # Price touched lower BBand zone (LONG opportunity)
    TOUCH_UPPER = 2    # Price touched upper BBand zone (SHORT opportunity)
    TOUCH_BOTH = 3     # Price touched both zones (volatile, unclear)
```

**Logic (using 15m intrabar analysis):**
```python
# Within 8h bar, check if any 15m bar touched:
# LONG zone: close <= (BBand_Lower_15m + BBand_Mid_15m) / 2
# SHORT zone: close >= (BBand_Upper_15m + BBand_Mid_15m) / 2
```

**Why it matters:** The strategy only enters when price reaches the pullback zone. Predicting this helps:
- Filter out bars where no entry opportunity will exist
- Size position confidence based on entry probability
- Pre-compute orders before zone touch

### 2.3 New Target: `trade_outcome` (Enhanced Triple Barrier)

The existing `triple_barrier` target uses symmetric ATR-based barriers. The live strategy uses **asymmetric** Bollinger-based targets. A new target matching the strategy's exact logic:

**Definition:**
```python
class TradeOutcome(IntEnum):
    STOP_LOSS = 0      # Hit SL first
    TIME_EXIT = 1      # Neither barrier hit in horizon
    TAKE_PROFIT = 2    # Hit TP first
    PARTIAL_TP = 3     # Hit first TP target but reversed
```

**Barrier construction matching bybitmodel.py:**
```python
# LONG barriers:
tp = SMA_20_1h  # or BBand_Upper_1h - delta
sl = entry - 1.5 * ATR_14

# SHORT barriers:
tp = BBand_Lower_1h  # + delta
sl = entry + 1.5 * ATR_14
```

### 2.4 Target Mapping to Strategy Decisions

| Strategy Decision | Primary Target | Supporting Targets |
|------------------|----------------|-------------------|
| Enter LONG? | `strategy_label == MR_LONG` | `trade_setup == LONG_SETUP`, `direction ∈ {BULLISH, STRONG_BULLISH}` |
| Enter SHORT? | `strategy_label == MR_SHORT` | `trade_setup == SHORT_SETUP`, `direction ∈ {BEARISH, STRONG_BEARISH}` |
| Skip trade? | `strategy_label == FLAT` | `triple_barrier == TIME_EXIT`, `volatility_regime == INCREASE` |
| Use trend strategy? | `strategy_label ∈ {TF_LONG, TF_SHORT}` | `trend_regime`, `path_label_5 ∈ {BULLISH, BEARISH}` |
| Use MR strategy? | `strategy_label ∈ {MR_LONG, MR_SHORT}` | `path_label_5 ∈ {MEAN_REVERT_UP, MEAN_REVERT_DOWN}` |

---

## 3. Feature Requirements for ML

### 3.1 Features Already in Pipeline (L1 Helpers)

The current pipeline computes 91 features from 10 L1 helpers. Relevant ones:

| Helper | Features | Relevance to Strategy |
|--------|----------|----------------------|
| `kalman` | trend, trend_strength, cycle, volatility | Regime detection |
| `garch` | volatility forecasts, VaR | Risk sizing |
| `cusum` | change points, regime changes | Entry timing |
| `hmm4/hmm5` | regime states, regime probs | Market regime |
| `evt` | tail risk estimates | Position sizing |
| `ou` | mean-reversion speed | MR vs Trend decision |

### 3.2 Missing Features (Need to Add)

To fully support the bybitmodel strategy, add these features:

| Feature Group | Calculation | Why Needed |
|---------------|-------------|------------|
| **BBand Position** | `(close - BBand_Mid) / (BBand_Upper - BBand_Lower)` | Entry zone detection |
| **BBand Bandwidth** | `(BBand_Upper - BBand_Lower) / BBand_Mid` | Squeeze detection |
| **ATR Ratio** | `ATR_14 / close` (normalized volatility) | Stop sizing |
| **Price vs SMA_20** | `(close - SMA_20) / SMA_20` | TP target distance |
| **KC Position** | `(close - KC_Mid) / (KC_Upper - KC_Lower)` | Fallback entry logic |
| **Vol Ratio** | `rolling_vol / rolling_vol.mean(63)` | High-vol regime filter |

### 3.3 Multi-Timeframe Features

The strategy uses 5m, 15m, 1h, 4h data. Current pipeline only uses 8h. Options:

**Option A: Pre-aggregate lower TF into 8h features**
- Add 15m BBand touch counts per 8h bar (already in `_load_15m_data_for_8h`)
- Add 1h/4h regime state at each 8h bar close
- Pro: Fits existing pipeline
- Con: Loses intra-bar timing precision

**Option B: Hierarchical model (recommended)**
- Train separate models for entry timing (15m) and direction (8h)
- Combine predictions at execution time
- Pro: Better precision
- Con: More complex deployment

---

## 4. 15m → 8h Data Merge (No Leakage)

### 4.1 Current Implementation in targets.py

The pipeline already handles this safely in `_load_15m_data_for_8h()`:

```python
def _load_15m_data_for_8h(timestamps_8h, data_dir):
    """
    For each 8h timestamp, loads the 32 subsequent 15m bars
    to analyze intrabar price action.
    """
    for ts_8h in timestamps_8h:
        # Get 32 15m bars starting from this 8h timestamp
        ts_end = ts_8h + pd.Timedelta(hours=8)
        mask = (df_15m.index >= ts_8h) & (df_15m.index < ts_end)
        bars = df_15m.loc[mask]
        # ... analyze bars ...
```

**Key Safety Rules:**
1. Only use 15m bars within the 8h window (no future leakage)
2. Use `close_time` for alignment, not `open_time`
3. Results are indexed by 8h timestamp
4. Target shift (`shift(-horizon)`) applied AFTER aggregation

### 4.2 Adding New 15m-Based Features

To add new features from 15m data, extend `_load_15m_data_for_8h`:

```python
# Example: BBand entry zone touch detection
# Inside the bar loop:

# Calculate BBand on 15m data (20-period)
sma = closes.rolling(20).mean()
std = closes.rolling(20).std()
upper_mid = sma + std  # +1σ
lower_mid = sma - std  # -1σ

# Entry zone definitions (matching bybitmodel.py)
long_zone = (lower_mid + sma) / 2   # Midpoint between -1σ and SMA
short_zone = (upper_mid + sma) / 2  # Midpoint between +1σ and SMA

# Count touches
touched_long_zone = (closes <= long_zone).sum()
touched_short_zone = (closes >= short_zone).sum()
```

### 4.3 Using Polars for Efficiency

For production, convert to Polars join_asof:

```python
import polars as pl

# Build close times
df_8h = df_8h.with_columns(
    (pl.col("timestamp") + pl.duration(hours=8)).alias("close_time")
)
df_15m = df_15m.with_columns(
    (pl.col("timestamp") + pl.duration(minutes=15)).alias("close_time")
)

# Join: get last 15m bar that closed at or before 8h close
merged = df_8h.join_asof(
    df_15m,
    on="close_time",
    strategy="backward",
    suffix="_15m"
)
```

---

## 5. Model Architecture Recommendations

### 5.1 Current Ensemble (main_wf.py Step 10)

| Model | Weight | Window | Strengths |
|-------|--------|--------|-----------|
| CatBoost | 0.30 | 300-700 | Golden features, tree policies |
| LightGBM | 0.30 | 300-700 | Fast, handles unbalance |
| LSTM | 0.25 | 450-900 | Sequence patterns |
| Linear | 0.15 | 550-1000 | Interpretable baseline |

### 5.2 Recommended Model Setup for Strategy Support

**A. Entry Signal Model (Primary)**
- Target: `strategy_label` (5-class)
- Output: Probability distribution over FLAT, TF_LONG, TF_SHORT, MR_LONG, MR_SHORT
- Features: All 91 L1 features + BBand position features
- Use: Weighted vote from ensemble

**B. Risk/Reward Model (Secondary)**
- Target: `triple_barrier` (3-class)
- Output: Probability of STOP_LOSS, TIME_EXIT, TAKE_PROFIT
- Features: Focus on volatility features (GARCH, EVT, ATR)
- Use: Position sizing, entry quality filter

**C. Path Characterization Model (Auxiliary)**
- Target: `path_label_5` (5-class)
- Output: Probability of path type
- Features: Regime features (HMM, Kalman, CUSUM)
- Use: Strategy selection (trend-follow vs mean-revert)

### 5.3 Multi-Output Architecture

Instead of training separate models per target, consider multi-output:

```python
# Pseudo-architecture
class MultiTargetHead(nn.Module):
    def __init__(self, hidden_dim):
        self.strategy_head = nn.Linear(hidden_dim, 5)    # strategy_label
        self.barrier_head = nn.Linear(hidden_dim, 3)     # triple_barrier
        self.path_head = nn.Linear(hidden_dim, 5)        # path_label_5
    
    def forward(self, features):
        shared = self.backbone(features)
        return {
            "strategy": self.strategy_head(shared),
            "barrier": self.barrier_head(shared),
            "path": self.path_head(shared),
        }
```

**Benefits:**
- Shared representation learning
- Consistent feature importance
- Efficient inference (one forward pass)

### 5.4 Confidence Calibration

The live strategy needs calibrated probabilities for:
- Entry threshold: only enter if P(correct direction) > 0.55
- Position sizing: scale by P(TAKE_PROFIT) / P(STOP_LOSS)
- Skip threshold: if P(FLAT) > 0.50, don't trade

Use Platt scaling or isotonic regression post-training.

---

## 6. Implementation Roadmap

### Phase 1: Immediate (Use Existing Targets) ✅

Already available in pipeline:
- `direction` → Directional prediction
- `strategy_label` → Trade/no-trade + strategy type
- `triple_barrier` → Risk/reward outcome
- `trade_setup` → Pullback entry quality
- `path_label_5` → Path characterization

**Action:** Run full pipeline (Steps 3-10) with current 9 WORKFLOW_TARGETS.

### Phase 2: Short-term (Add Missing Features)

1. Add BBand position features to `scripts/analysis/features.py`:
   ```python
   # BBand relative position (-1 to +1)
   df["bband_position"] = (df["close"] - df["bband_mid"]) / (df["bband_upper"] - df["bband_lower"])
   
   # BBand squeeze detection
   df["bband_squeeze"] = df["bband_bandwidth"] / df["bband_bandwidth"].rolling(50).mean()
   ```

2. Add ATR-based features:
   ```python
   df["atr_ratio"] = df["atr_14"] / df["close"]
   df["price_vs_sma20"] = (df["close"] - df["sma_20"]) / df["close"]
   ```

3. Register in `L1_HELPERS` or create new helper module.

### Phase 3: Medium-term (Enhanced Targets)

1. Implement `bband_entry_touch` target:
   - Extend `_load_15m_data_for_8h` with entry zone touch detection
   - Register with `@register_target`
   - Add to WORKFLOW_TARGETS

2. Implement `trade_outcome` target matching bybitmodel exact barriers

### Phase 4: Long-term (Live Integration)

1. Model serving infrastructure:
   ```
   8h bar close → Load latest L1 features → Ensemble inference → Signal generation
   ```

2. Integration with bybitmodel.py:
   ```python
   # In generate_trade_signal()
   ml_probs = load_model_predictions()
   if ml_probs["strategy"]["MR_LONG"] > 0.55 and rule_signal == "LONG":
       confidence_boost = ml_probs["barrier"]["TAKE_PROFIT"]
       # Adjust position size by confidence
   ```

---

## 7. Integration with main_wf.py

### 7.1 Current Pipeline Flow

```
Step 0: Fetch data
Step 1: Merge → features
Step 2: Generate targets
Step 3: Feature optimization
Step 4: Build datasets
Step 5-7: Analysis (IC, importance, CV)
Step 8: L1 precompute (Rust helpers)
Step 9: Dataset assembly
Step 10: L2 backtest
```

### 7.2 No Changes Needed for Existing Targets

The targets in this document (`strategy_label`, `triple_barrier`, `trade_setup`, `path_label_5`) are already:
- Registered in `scripts/workflow/targets.py`
- Listed in `scripts/workflow/config.py` WORKFLOW_TARGETS
- Computed in Step 2/4 automatically
- Available for L2 backtest in Step 10

### 7.3 Adding New Targets (bband_entry_touch)

1. **targets.py**: Add enum + compute function:
   ```python
   class BBandEntryTouch(IntEnum):
       NO_TOUCH = 0
       TOUCH_LOWER = 1
       TOUCH_UPPER = 2
       TOUCH_BOTH = 3
   
   @register_target(
       name="bband_entry_touch",
       task_type="classification",
       n_classes=4,
       target_column="y_bband_entry_touch",
       description="4-class BBand entry zone touch detection",
       label_enum=BBandEntryTouch,
   )
   def compute_bband_entry_touch(close, high, low, horizon, **kwargs):
       # ... implementation using _load_15m_data_for_8h ...
   ```

2. **config.py**: Add to WORKFLOW_TARGETS:
   ```python
   WORKFLOW_TARGETS = [
       "direction",
       # ... existing ...
       "bband_entry_touch",  # NEW
   ]
   ```

3. **backtest.py**: Add LABEL_NAMES:
   ```python
   LABEL_NAMES["bband_entry_touch"] = {
       0: "NO_TOUCH",
       1: "TOUCH_LOWER",
       2: "TOUCH_UPPER",
       3: "TOUCH_BOTH",
   }
   ```

### 7.4 Adding BBand Features

Add to `scripts/analysis/features.py` (Step 1b):

```python
def compute_bband_features(df: pl.DataFrame) -> pl.DataFrame:
    """Bollinger Band derived features for strategy support."""
    return df.with_columns([
        # BBand position (-1 at lower band, +1 at upper band)
        ((pl.col("close") - pl.col("bband_mid")) / 
         (pl.col("bband_upper") - pl.col("bband_lower"))).alias("bband_position"),
        
        # BBand squeeze (bandwidth vs historical avg)
        (pl.col("bband_bandwidth") / 
         pl.col("bband_bandwidth").rolling_mean(50)).alias("bband_squeeze"),
        
        # Distance to entry zones (normalized by BBand width)
        ((pl.col("close") - (pl.col("bband_lower") + pl.col("bband_mid")) / 2) /
         (pl.col("bband_upper") - pl.col("bband_lower"))).alias("dist_to_long_zone"),
         
        ((pl.col("close") - (pl.col("bband_upper") + pl.col("bband_mid")) / 2) /
         (pl.col("bband_upper") - pl.col("bband_lower"))).alias("dist_to_short_zone"),
    ])
```

---

## Appendix A: Exact bybitmodel.py Logic Reference

### Entry Scoring Indicators

From `evaluate_generic_conditions`:
```
RSI_14, MACD_Line, ADX, Stochastic_%K, Stochastic_%D, CCI_14, Williams_%R
Bollinger_*, KC_*, EMA_20, EMA_50, EMA_200, ATR_14
Support, Resistance, Volume_SMA_5, Volume_SMA_20
```

### Regime Classification

From `classify_market_regime`:
- **Trending** if: ADX > 25 AND (RSI > 70 OR RSI < 30)
- **Ranging** otherwise
- 4h timeframe primary, 1h secondary

### Risk Management Constants

```python
ATR_MULTIPLIER = 1.5        # For stop-loss
MIN_REWARD_RATIO = 1.006    # LONG TP must be >= 1.006× entry
MAX_REWARD_RATIO = 0.994    # SHORT TP must be <= 0.994× entry
RISK_PCT = 0.10             # 10% equity risk for leverage calc
```

---

## Appendix B: Target Compatibility Matrix

| Target | Works with 8h bars? | Uses 15m analysis? | Classification? | n_classes |
|--------|--------------------|--------------------|-----------------|-----------|
| direction | ✅ | ✅ | Yes | 5 |
| volatility | ✅ | ❌ | No (regression) | - |
| volatility_regime | ✅ | ❌ | Yes | 2 |
| trend_regime | ✅ | ❌ | Yes | 2 |
| trade_setup | ✅ | ✅ | Yes | 4 |
| path_label_5 | ✅ | ✅ | Yes | 5 |
| strategy_label | ✅ | ✅ | Yes | 5 |
| triple_barrier | ✅ | ✅ | Yes | 3 |
| bband_entry_touch (NEW) | ✅ | ✅ | Yes | 4 |

---

## Summary

### Immediate Actions (No Code Changes)

1. Run pipeline with current targets to generate predictions for:
   - `strategy_label` → Primary trade decision
   - `triple_barrier` → Risk/reward filtering
   - `trade_setup` → Entry quality assessment

### Short-term Improvements

2. Add BBand position features to capture strategy-relevant signals
3. Add `bband_entry_touch` target for entry timing prediction

### Strategy Enhancement

4. Use model predictions to:
   - Confirm rule-based signals (higher confidence = larger position)
   - Filter low-confidence signals (P(FLAT) > 0.5 → skip)
   - Adjust leverage based on P(TAKE_PROFIT) / P(STOP_LOSS)

The existing pipeline already provides the core capabilities. The main gap is **feature engineering** to capture Bollinger Band relationships that the live strategy depends on.
