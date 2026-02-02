# Multi-Label Target Redesign: Research & Design

**Date:** 2026-01-27  
**Status:** Research Phase  
**Author:** Astra + Przem

---

## Problem Statement

Current targets capture **where** price ended but not **how** it got there:

| Current Approach | Limitation |
|-----------------|------------|
| `direction` = UP | Could be trending up OR mean-reverting to end up |
| `direction` = DOWN | Could be breakdown OR failed rally |
| `volatility_regime` | Binary increase/decrease, no path info |

**User insight:**
> "Bullish trending price move up is different than mean reverting ending up with price up at the end of 8h candle"

**Goal:** Use 15m intrabar data (32 bars per 8h candle) to distinguish price paths.

---

## Academic Research

### 1. Kaufman Efficiency Ratio (Perry Kaufman, 1995) ⭐

**Source:** "Smarter Trading: Improving Performance in Changing Markets" (ISBN 0-07-034002-1)

**Formula:**
```
ER = |Close[N] - Close[0]| / Σ|Close[i] - Close[i-1]|
```

**Interpretation:**
| ER Value | Market State |
|----------|--------------|
| ER = 1.0 | Perfect trend — all bars moved same direction |
| ER ≈ 0.6+ | Efficient trending movement |
| ER ≈ 0.3-0.6 | Mixed/transitional |
| ER < 0.3 | Choppy/ranging — bars cancel each other |
| ER = 0.0 | Perfect chop — net zero movement |

**Key insight:** Compares momentum (net change) with volatility (total path). High ER = trend. Low ER = noise.

**Application:** Compute on 32 × 15m bars within each 8h candle to classify PATH_TYPE.

---

### 2. Mean-Reversion Detection (arXiv:2404.16467)

**Paper:** "Analysis of Price Jumps and Mean-Reversion in Financial Markets"

**Key findings:**
- 60% of price jumps exhibit positive mean-reversion score (D2 > 0)
- V-shape price profile is the signature of mean-reversion
- Both exogenous (news-driven) and endogenous (self-initiated) jumps can mean-revert
- Strongly exogenous jumps (large D1 > 0) show D2 ≈ 0 (no mean-reversion)

**Mean-reversion score D2:**
- D2 > 0: Price reverts after jump
- D2 ≈ 0: Price holds at new level
- D2 < 0: Price continues in jump direction

**Application:** Detect V-shape patterns in 15m data to identify MEAN_REVERT path type.

---

### 3. Regime Switching (arXiv:2504.10914, Schmidhuber 2021)

**Key concept:** Markets dynamically transition between:
- **Trend-following regime** — governed by momentum traders
- **Mean-reversion regime** — governed by fundamental traders

**Mechanism:** Autoregressive coefficients become trend-dependent, enabling dynamic regime transitions.

**Application:** PATH_TYPE captures which regime dominated the 8h candle.

---

### 4. Hurst Exponent (SSRN papers)

**Papers:**
- "Short Term Trading Models Using Hurst Exponent" (SSRN 3824032)
- "Hurst Exponent Dynamics of S&P 500 Returns" (SSRN 4200407)

**Interpretation:**
| Hurst H | Behavior |
|---------|----------|
| H > 0.5 | Trending/momentum (persistent) |
| H = 0.5 | Random walk |
| H < 0.5 | Mean-reverting (anti-persistent) |

**Computation:** Can be estimated on intrabar data using R/S analysis or DFA.

**Application:** Alternative/complementary to Kaufman ER for trend detection.

---

### 5. Triple-Barrier Method (López de Prado, 2018)

**Source:** "Advances in Financial Machine Learning" (Wiley)

**Already implemented** in our system for `first_extreme` and `vol_to_extreme` targets.

**Extension opportunity:** Use intermediate barrier crossings to detect V-shapes and breakout patterns.

---

### 6. Multi-Label Classification in Finance (PMC10936758)

**Paper:** "Fusing Labels for Multi-Objective Portfolio Optimization"

**Key insights:**
- Multi-label problems common in finance (return + risk simultaneously)
- Label correlation is a real problem
- "Fusing labels" approach: weighted combination into composite label
- XGBoost handles multi-label well

**Advantages of multi-label over single composite:**
1. Adjustable weights per dimension
2. Alleviates label correlation issues
3. Mitigates class imbalance
4. Better interpretability
5. Resolves label conflicts

---

## Proposed Multi-Label Design

### Three Independent Dimensions

| Label | Question Answered | Classes |
|-------|-------------------|---------|
| **FINAL_DIRECTION** | Where did it end? | UP, DOWN, FLAT |
| **PATH_TYPE** | How did it get there? | TRENDING, BREAKOUT, MEAN_REVERT, RANGING |
| **MOMENTUM_TIMING** | When did the move happen? | FRONT, BACK, DISTRIBUTED |

---

### Label 1: FINAL_DIRECTION

**What:** Net price change over 8h candle.

**Classes:**
- **UP:** `close > open + threshold`
- **DOWN:** `close < open - threshold`  
- **FLAT:** within threshold

**Threshold:** Adaptive based on recent volatility (e.g., 0.3 × ATR)

**Implementation:** Already exists as `direction` target.

---

### Label 2: PATH_TYPE ⭐ (New)

**What:** Character of price movement within the candle.

**Classes:**

| Class | Kaufman ER | Additional Criteria |
|-------|------------|---------------------|
| **TRENDING** | ER > 0.6 | Steady progression, no major reversals |
| **BREAKOUT** | ER > 0.6 | >60% of move in first half |
| **MEAN_REVERT** | ER < 0.6 | V-shape: extreme hit then >50% retracement |
| **RANGING** | ER < 0.3 | No clear direction, bars cancel out |

**Pseudocode:**
```python
def compute_path_type(closes_15m: np.ndarray, highs_15m: np.ndarray, lows_15m: np.ndarray) -> str:
    """
    closes_15m: 32 close prices (15m bars within 8h candle)
    """
    # 1. Compute Kaufman Efficiency Ratio
    net_change = abs(closes_15m[-1] - closes_15m[0])
    individual_changes = np.abs(np.diff(closes_15m))
    total_path = individual_changes.sum()
    er = net_change / total_path if total_path > 0 else 0
    
    # 2. Detect V-shape (mean-reversion signature)
    candle_high = highs_15m.max()
    candle_low = lows_15m.min()
    candle_range = candle_high - candle_low
    
    high_time = highs_15m.argmax()
    low_time = lows_15m.argmin()
    
    # V-shape: extreme in first half, then >50% retracement
    mid_idx = len(closes_15m) // 2
    if high_time < mid_idx:  # High early
        retracement = (candle_high - closes_15m[-1]) / candle_range
        v_shape = retracement > 0.5
    elif low_time < mid_idx:  # Low early
        retracement = (closes_15m[-1] - candle_low) / candle_range
        v_shape = retracement > 0.5
    else:
        v_shape = False
    
    # 3. Classify
    if er > 0.6:
        # Check momentum timing
        first_half_move = abs(closes_15m[mid_idx] - closes_15m[0])
        total_move = net_change
        if total_move > 0 and first_half_move / total_move > 0.6:
            return "BREAKOUT"
        return "TRENDING"
    elif v_shape:
        return "MEAN_REVERT"
    else:
        return "RANGING"
```

---

### Label 3: MOMENTUM_TIMING

**What:** When during the candle did the significant move occur?

**Classes:**
- **FRONT:** >60% of extreme reached in first half
- **BACK:** >60% of extreme reached in second half
- **DISTRIBUTED:** Balanced throughout

**Pseudocode:**
```python
def compute_momentum_timing(closes_15m: np.ndarray, highs_15m: np.ndarray, lows_15m: np.ndarray) -> str:
    """Determine when the major move happened within the candle."""
    mid_idx = len(closes_15m) // 2
    
    # Determine if this was an up or down candle
    net_return = closes_15m[-1] - closes_15m[0]
    
    if net_return > 0:  # Up candle - track progress toward high
        candle_high = highs_15m.max()
        first_half_max = highs_15m[:mid_idx].max()
        progress_at_mid = (first_half_max - closes_15m[0]) / (candle_high - closes_15m[0])
    else:  # Down candle - track progress toward low
        candle_low = lows_15m.min()
        first_half_min = lows_15m[:mid_idx].min()
        progress_at_mid = (closes_15m[0] - first_half_min) / (closes_15m[0] - candle_low)
    
    if progress_at_mid > 0.6:
        return "FRONT"
    elif progress_at_mid < 0.4:
        return "BACK"
    else:
        return "DISTRIBUTED"
```

---

## Implementation Considerations

### Data Requirements

Already have 15m data available:
- Used by `first_extreme` and `vol_to_extreme` targets
- 32 bars per 8h candle (8h ÷ 15m = 32)

### Thresholds to Calibrate

| Parameter | Proposed Value | Notes |
|-----------|---------------|-------|
| ER trending threshold | 0.6 | Needs empirical validation on our data |
| ER ranging threshold | 0.3 | Needs empirical validation |
| V-shape retracement | 0.5 (50%) | Could be adaptive |
| Direction threshold | 0.3 × ATR | Already used in existing targets |
| Timing threshold | 0.6 (60%) | Standard majority threshold |

### Integration Options

**Option A: Separate targets**
```python
WORKFLOW_TARGETS = [
    'direction',           # Existing
    'path_type',           # NEW
    'momentum_timing',     # NEW
    'volatility',          # Existing
    ...
]
```

**Option B: Composite target**
```python
# e.g., "UP_TRENDING_FRONT" = 12 combinations
# But this creates class explosion and imbalance issues
```

**Recommendation:** Option A — separate targets, predict independently.

---

---

## Empirical Analysis Results (Jan 27, 2026)

### Dataset
- **Source:** `fetchingByBit/sorted-15m-bybit-linear/` (178 parquet files)
- **Total 15m bars:** 177,475
- **Date range:** 2021-01-01 to 2026-01-23
- **8h periods analyzed:** 5,546

### Key Finding 1: Efficiency Ratio is MUCH Lower Than Expected

| Statistic | Value |
|-----------|-------|
| Mean ER | 0.172 |
| Median ER | 0.142 |
| 25th percentile | 0.066 |
| 75th percentile | 0.250 |
| 90th percentile | 0.361 |
| Max ER | 0.820 |

**Implication:** Academic threshold of 0.6 would classify only **0.5%** as trending!
Crypto 8h candles are mostly **CHOPPY**, not trending.

### Key Finding 2: V-Shape (Mean Reversion) is VERY Common

- **62%** of candles have >50% retracement
- Confirms arXiv:2404.16467 finding (60% mean-reverting)
- Retracement distribution is nearly uniform

### Key Finding 3: Momentum Timing is Symmetric

| Timing | Percentage |
|--------|------------|
| FRONT (>60% in first half) | 38.7% |
| BACK (<40% in first half) | 38.1% |
| DISTRIBUTED | 23.2% |

No strong bias toward early or late moves.

### Key Finding 4: Direction vs Efficiency

| Path Efficiency | DOWN candles | FLAT candles | UP candles |
|-----------------|--------------|--------------|------------|
| CHOPPY | 27.3% | **90.2%** | 26.8% |
| TRANSITIONAL | 36.7% | 9.8% | 36.3% |
| TRENDING | 36.0% | **0.0%** | 36.9% |

**Critical insight:** FLAT candles are almost always CHOPPY (90%).
When there IS a move (UP/DOWN), efficiency distribution is similar.

### Key Finding 5: No Autocorrelation

| Metric | Correlation with NEXT return |
|--------|------------------------------|
| efficiency_ratio | -0.004 |
| retracement | -0.008 |
| momentum_timing | -0.011 |
| volatility | +0.025 |
| net_return | +0.022 |

Path characteristics have **zero predictive power** for next candle direction.
This is expected — we're labeling outcomes, not predicting them.

---

## Data-Driven Thresholds (REVISED)

Based on empirical analysis, the thresholds should be:

### LABEL 2: PATH_EFFICIENCY (Kaufman ER)

| Class | Threshold | Percentile | Description |
|-------|-----------|------------|-------------|
| **TRENDING** | ER > 0.21 | Top 33% | Efficient directional movement |
| **TRANSITIONAL** | ER 0.09-0.21 | Middle 33% | Mixed efficiency |
| **CHOPPY** | ER < 0.09 | Bottom 33% | Low efficiency, moves cancel out |

### LABEL 3: PATH_REVERSAL (Retracement)

| Class | Threshold | Percentile | Description |
|-------|-----------|------------|-------------|
| **CONTINUATION** | Retr < 0.45 | ~23% | Price held its gains/losses |
| **PARTIAL** | Retr 0.45-0.74 | ~39% | Some giveback |
| **REVERSAL** | Retr > 0.74 | ~38% | Went there and came back |

---

## Most Common Combinations (27 possible)

| Combination | Count | % | Interpretation |
|-------------|-------|---|----------------|
| UP_TREND_REV | 609 | 11.0% | Strong rally that retraced (distribution trap) |
| DOWN_TREND_REV | 534 | 9.6% | Strong selloff that bounced (accumulation trap) |
| DOWN_TRANS_PART | 414 | 7.5% | Normal down day with bounce |
| UP_TRANS_PART | 361 | 6.5% | Normal up day with pullback |
| DOWN_CHOPPY_CONT | 354 | 6.4% | Choppy down, held losses |
| UP_CHOPPY_CONT | 344 | 6.2% | Choppy up, held gains |
| FLAT_CHOPPY_CONT | 254 | 4.6% | True consolidation |

**Trading insight:** The most common pattern is "efficient move that reverses" (TREND+REV).
This is the classic trap pattern where price moves strongly then gives it all back.

---

## Open Questions (Updated)

1. ~~ER thresholds~~ → ✅ DONE: Use tertiles (0.09, 0.21)
2. ~~V-shape detection~~ → ✅ DONE: Use retracement tertiles (0.45, 0.74)
3. **Hurst exponent:** Keep as feature, not label (computation cost)
4. **Interaction with existing targets:**
   - `first_extreme` overlaps with momentum_timing → could replace
   - `vol_to_extreme` provides magnitude info → keep separately
5. **Model architecture:** Train separate models (simpler, more interpretable)

---

## FINAL LABEL DESIGN (Jan 27, 2026)

After empirical analysis, we designed **intuitive single-label system** instead of multi-label.

**Reason:** User requested labels like "strong bullish, bullish, sideways up/down, mean reverting up/down, bearish, strong bearish" - these are mutually exclusive categories that capture direction + path in one label.

---

### 7-Class System (PRIMARY - Starting Implementation) ✅

**Selected as initial implementation** — simpler, well-balanced, captures core patterns.

| Label | % | Avg Return | Description | Trading Interpretation |
|-------|---|------------|-------------|----------------------|
| **STRONG_BULLISH** | 1.5% | +3.05% | UP + trending (ER>0.22) + big move (>1.5%) | Clean rally - go long |
| **BULLISH** | 16.8% | +0.86% | UP + normal path (includes choppy) | Modest up - cautious long |
| **MEAN_REVERT_UP** | 28.1% | +1.54% | UP + went DOWN first + retraced >50% | Dip bought - reversal play |
| **SIDEWAYS** | 9.4% | -0.00% | FLAT net movement | Range-bound - stay out |
| **MEAN_REVERT_DOWN** | 27.2% | -1.56% | DOWN + went UP first + retraced >50% | Rally sold - reversal play |
| **BEARISH** | 15.7% | -0.83% | DOWN + normal path (includes choppy) | Modest down - cautious short |
| **STRONG_BEARISH** | 1.1% | -2.81% | DOWN + trending (ER>0.22) + big move (>1.5%) | Clean selloff - go short |

**Classification Logic:**
```python
# Data-driven thresholds
er_high = 0.224  # 70th percentile
return_75 = 1.52  # 75th percentile of abs(return)

# Direction
direction = 'UP' if net_return > 0.001 else ('DOWN' if net_return < -0.001 else 'FLAT')

# Mean reversion detection
mean_revert_up = (direction == 'UP' and low_time_idx < high_time_idx and retracement > 0.5)
mean_revert_down = (direction == 'DOWN' and high_time_idx < low_time_idx and retracement > 0.5)

# Strong moves (trending + big magnitude)
strong_bullish = (direction == 'UP' and efficiency_ratio > er_high and abs(net_return) > return_75)
strong_bearish = (direction == 'DOWN' and efficiency_ratio > er_high and abs(net_return) > return_75)
```

**Key Characteristics:**
- **55% of candles are mean-reverting** (went one way, came back)
- **Only ~2.6% are STRONG** (clean trends) → May need oversampling
- **Good balance:** 46.5% bullish / 44.1% bearish / 9.4% neutral
- **Trading insight:** MEAN_REVERT_UP (+1.54% avg) more profitable than BULLISH (+0.86%) because dip provides better entry

---

### 9-Class System (ALTERNATIVE - More Granular)

**Adds SIDEWAYS_UP/DOWN** to distinguish choppy paths from normal moves.

| Label | % | Avg Return | Description | Trading Interpretation |
|-------|---|------------|-------------|----------------------|
| **STRONG_BULLISH** | 1.5% | +3.05% | UP + trending (ER>0.22) + held gains + big move | Clean rally - go long |
| **BULLISH** | 9.4% | +0.86% | UP + decent efficiency | Modest up - cautious long |
| **SIDEWAYS_UP** | 7.5% | +0.38% | UP + choppy path (ER<0.08) | Choppy up - scalp only |
| **MEAN_REVERT_UP** | 28.1% | +1.54% | UP + went DOWN first + retraced >50% | Dip bought - reversal play |
| **SIDEWAYS** | 9.4% | -0.00% | FLAT net movement | Range-bound - stay out |
| **MEAN_REVERT_DOWN** | 27.2% | -1.56% | DOWN + went UP first + retraced >50% | Rally sold - reversal play |
| **SIDEWAYS_DOWN** | 7.8% | -0.38% | DOWN + choppy path (ER<0.08) | Choppy down - scalp only |
| **BEARISH** | 7.9% | -0.83% | DOWN + decent efficiency | Modest down - cautious short |
| **STRONG_BEARISH** | 1.1% | -2.81% | DOWN + trending (ER>0.22) + held losses + big move | Clean selloff - go short |

**Classification Logic (adds choppy detection):**
```python
# Additional threshold
er_low = 0.080  # 30th percentile

# Choppy variants (only for directional moves)
if direction == 'UP':
    if mean_revert_up:
        label = 'MEAN_REVERT_UP'
    elif strong_bullish:
        label = 'STRONG_BULLISH'
    elif efficiency_ratio < er_low:
        label = 'SIDEWAYS_UP'  # Choppy
    else:
        label = 'BULLISH'
```

**When to use 9-class:**
- Want to specifically target/avoid choppy conditions
- Model can learn difference between clean directional vs noisy
- Have enough data for smaller classes

**When to use 7-class:**
- Simpler model, fewer parameters
- SIDEWAYS_UP/DOWN have weak signal (+0.38% vs -0.38%)
- Easier to interpret results

---

## Implementation Plan

### Current System Review

**Existing targets in WORKFLOW_TARGETS:**
```python
# scripts/workflow/config.py
WORKFLOW_TARGETS = [
    "direction",          # 3-class: DOWN/UP/NEUTRAL
    "volatility",         # Regression: abs(forward_return)
    "volatility_regime",  # Binary: vol will INCREASE/DECREASE
    "trend_regime",       # Binary: fast_sma > slow_sma
    "first_extreme",      # Binary: LOW_FIRST/HIGH_FIRST (uses 15m)
    "vol_to_extreme",     # Regression: magnitude to first extreme (uses 15m)
]
```

**How registration works:**
1. Define label enum (e.g., `PathLabel7Class`)
2. Use `@register_target()` decorator
3. Implement compute function
4. Add to `WORKFLOW_TARGETS` list

**Existing 15m infrastructure:**
- `_load_15m_data_for_8h()` helper function already exists in targets.py
- Loads 32 15m bars for each 8h period
- Returns DataFrame with timestamp alignment
- Already used by `first_extreme` and `vol_to_extreme` targets

---

### Step 1: Add Label Enum

Add to `scripts/workflow/targets.py` near other enums:

```python
class PathLabel7Class(IntEnum):
    """7-class path characterization labels."""
    
    STRONG_BULLISH = 0   # Clean rally
    BULLISH = 1          # Normal up
    MEAN_REVERT_UP = 2   # Dip bought
    SIDEWAYS = 3         # Range-bound
    MEAN_REVERT_DOWN = 4 # Rally sold
    BEARISH = 5          # Normal down
    STRONG_BEARISH = 6   # Clean selloff
```

---

### Step 2: Implement Compute Function

Add new registered target to `scripts/workflow/targets.py`:

```python
@register_target(
    name="path_label_7",
    task_type="classification",
    n_classes=7,
    target_column="y_path_label_7",
    description="7-class path characterization using 15m intrabar analysis",
    label_enum=PathLabel7Class,
)
def compute_path_label_7(
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    horizon: int,
    **kwargs: Any,
) -> pd.Series:
    """
    Compute 7-class path label using 15m intrabar data.
    
    Classes:
    0 - STRONG_BULLISH: UP + trending (ER>0.22) + big move (>1.5%)
    1 - BULLISH: UP + normal path
    2 - MEAN_REVERT_UP: UP + went DOWN first + retraced >50%
    3 - SIDEWAYS: FLAT net movement
    4 - MEAN_REVERT_DOWN: DOWN + went UP first + retraced >50%
    5 - BEARISH: DOWN + normal path
    6 - STRONG_BEARISH: DOWN + trending (ER>0.22) + big move (>1.5%)
    
    Uses 32 15m bars within each 8h candle to compute:
    - Kaufman Efficiency Ratio (ER)
    - Retracement (how much giveback from extreme)
    - Extreme timing (which came first: high or low)
    """
    import polars as pl
    
    # Load 15m data aligned to 8h timestamps
    df_15m = _load_15m_data_for_8h(close.index)
    
    # Convert to pandas for easier manipulation
    df_15m_pd = df_15m if isinstance(df_15m, pd.DataFrame) else df_15m.to_pandas()
    
    # Initialize labels as float (for NaN support)
    labels = pd.Series(np.nan, index=close.index, dtype=float)
    
    # Data-driven thresholds (from empirical analysis)
    ER_HIGH = 0.224    # 70th percentile
    RETURN_75 = 0.0152  # 75th percentile (1.52%)
    
    for idx in close.index:
        if idx not in df_15m_pd['timestamp_8h'].values:
            continue
            
        # Get 15m bars for this 8h period
        row = df_15m_pd[df_15m_pd['timestamp_8h'] == idx].iloc[0]
        
        # Skip if insufficient data
        if pd.isna(row.get('first_extreme')):
            continue
        
        # Extract metrics from 15m analysis
        # NOTE: _load_15m_data_for_8h needs to be extended to return these
        efficiency_ratio = row.get('efficiency_ratio', np.nan)
        retracement = row.get('retracement', np.nan)
        high_time_idx = row.get('high_time_idx', np.nan)
        low_time_idx = row.get('low_time_idx', np.nan)
        
        # Compute net return for this 8h period
        future_close = close.shift(-horizon).loc[idx]
        if pd.isna(future_close):
            continue
        net_return = (future_close - close.loc[idx]) / close.loc[idx]
        
        # Direction classification
        if net_return > 0.001:
            direction = 'UP'
        elif net_return < -0.001:
            direction = 'DOWN'
        else:
            direction = 'FLAT'
        
        # Apply classification logic
        if direction == 'FLAT':
            labels.loc[idx] = PathLabel7Class.SIDEWAYS
        
        elif direction == 'UP':
            # Mean reversion detection
            if low_time_idx < high_time_idx and retracement > 0.5:
                labels.loc[idx] = PathLabel7Class.MEAN_REVERT_UP
            # Strong bullish (trending + big move)
            elif efficiency_ratio > ER_HIGH and abs(net_return) > RETURN_75:
                labels.loc[idx] = PathLabel7Class.STRONG_BULLISH
            # Normal bullish
            else:
                labels.loc[idx] = PathLabel7Class.BULLISH
        
        elif direction == 'DOWN':
            # Mean reversion detection
            if high_time_idx < low_time_idx and retracement > 0.5:
                labels.loc[idx] = PathLabel7Class.MEAN_REVERT_DOWN
            # Strong bearish (trending + big move)
            elif efficiency_ratio > ER_HIGH and abs(net_return) > RETURN_75:
                labels.loc[idx] = PathLabel7Class.STRONG_BEARISH
            # Normal bearish
            else:
                labels.loc[idx] = PathLabel7Class.BEARISH
    
    return labels
```

**Critical dependency:** Need to extend `_load_15m_data_for_8h()` to compute and return:
- `efficiency_ratio`: Kaufman ER
- `retracement`: % giveback from extreme
- `high_time_idx`: Bar index where 8h high was reached
- `low_time_idx`: Bar index where 8h low was reached

---

### Step 3: Extend _load_15m_data_for_8h()

Current function returns: `first_extreme`, `time_to_first`, `vol_to_first`

Need to add:
```python
def _load_15m_data_for_8h(...) -> pd.DataFrame:
    ...
    
    # EXISTING CODE
    first_extreme = ...
    time_to_first = ...
    vol_to_first = ...
    
    # NEW: Compute additional metrics
    closes_15m = bars['close'].values
    highs_15m = bars['high'].values
    lows_15m = bars['low'].values
    
    # 1. Kaufman Efficiency Ratio
    net_change = abs(closes_15m[-1] - closes_15m[0])
    individual_changes = np.abs(np.diff(closes_15m))
    total_path = individual_changes.sum()
    efficiency_ratio = net_change / total_path if total_path > 0 else 0
    
    # 2. High/Low timing indices
    high_time_idx = np.argmax(highs_15m)
    low_time_idx = np.argmin(lows_15m)
    
    # 3. Retracement
    candle_high = highs_15m.max()
    candle_low = lows_15m.min()
    candle_range = candle_high - candle_low
    candle_close = closes_15m[-1]
    
    if candle_range > 0:
        if high_time_idx < low_time_idx:  # High came first
            retracement = (candle_high - candle_close) / candle_range
        else:  # Low came first
            retracement = (candle_close - candle_low) / candle_range
    else:
        retracement = 0
    
    results.append({
        "timestamp_8h": ts_8h,
        "first_extreme": first_extreme,
        "time_to_first": time_to_first,
        "vol_to_first": vol_to_first,
        # NEW FIELDS
        "efficiency_ratio": efficiency_ratio,
        "high_time_idx": high_time_idx,
        "low_time_idx": low_time_idx,
        "retracement": retracement,
    })
```

---

### Step 4: Add to WORKFLOW_TARGETS

```python
# scripts/workflow/config.py
WORKFLOW_TARGETS = [
    "direction",
    "volatility",
    "volatility_regime",
    "trend_regime",
    "first_extreme",
    "vol_to_extreme",
    "path_label_7",  # NEW
]
```

---

### Step 5: Testing Checklist

- [ ] Verify `_load_15m_data_for_8h()` returns new fields without breaking existing targets
- [ ] Run `compute_path_label_7()` on test data, check distributions match empirical analysis
- [ ] Confirm no NaN explosion (should have same coverage as `first_extreme`)
- [ ] Test temporal alignment: labels should align with 8h candle timestamps
- [ ] Verify label enum values (0-6) match class definitions
- [ ] Run full workflow Step 4 (dataset building) to ensure integration works

---

## Next Steps

- [x] Empirical analysis: Compute Kaufman ER on historical 15m data
- [x] Threshold calibration: Find natural breakpoints in ER distribution
- [x] V-shape detection: Implement and test on historical data
- [x] Class balance: Check distribution of proposed labels
- [x] **DECISION:** 7-class system selected as primary (9-class as alternative)
- [ ] Implementation: Add `compute_path_label_7()` to `scripts/workflow/targets.py`
- [ ] Integration: Add to WORKFLOW_TARGETS
- [ ] Testing: Verify alignment and distributions

---

## References

1. Kaufman, P.J. (1995). *Smarter Trading: Improving Performance in Changing Markets*. McGraw-Hill. ISBN 0-07-034002-1
2. López de Prado, M. (2018). *Advances in Financial Machine Learning*. Wiley.
3. arXiv:2404.16467 - Price jump and mean-reversion analysis
4. arXiv:2504.10914 - Trend-following vs mean-reversion regimes
5. SSRN:3824032 - Hurst Exponent for short-term trading
6. PMC10936758 - Multi-label classification in finance
