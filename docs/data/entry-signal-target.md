# Entry Signal Target (7-Class)

## Overview

A multiclass classification target based on 1h Bollinger Band entry signals, aggregated to 8h bars for ML training alignment. Combines **mean-reversion** signals with **trend-following** bias detection.

---

## Signal Detection Logic

### BBand Entry Zones (1h timeframe)
```
BBand_Mid = SMA(close, 20)
BBand_Std = STD(close, 20)

Long Entry Zone  = BBand_Mid - 1σ  (oversold)
Short Entry Zone = BBand_Mid + 1σ  (overbought)
```

### Signal Generation
A **NEW signal** is generated when price **enters** the zone (transition, not just "in zone"):
- **LONG signal**: `close <= Long_Entry_Zone` AND previous bar was NOT in zone
- **SHORT signal**: `close >= Short_Entry_Zone` AND previous bar was NOT in zone

### Directional Bias Detection
For bars with no BBand signals, we measure where price spent time relative to the mid:
```
std_from_mid = (close - BBand_Mid) / BBand_Std

Bullish Bias:  mean(std_from_mid) > +0.3σ  → trending up
Bearish Bias:  mean(std_from_mid) < -0.3σ  → trending down
Neutral:       mean(std_from_mid) within ±0.3σ
```

---

## Why 1h Timeframe?

Analysis of all timeframes showed 1h produces optimal signal frequency for 8h training:

| Timeframe | Avg Signals/8h | 8h bars with 1 signal | Clean (0-2 signals) |
|-----------|----------------|----------------------|---------------------|
| 5m        | 12.18          | 0%                   | 0%                  |
| 15m       | 4.08           | 3.5%                 | 15.4%               |
| **1h**    | **0.97**       | **46.0%**            | **96.6%**           |
| 4h        | 0.22           | 21.7%                | 100%                |

**1h is optimal:** ~1 signal per 8h bar on average, 96.6% have clean (0-2) signals.

---

## 7-Class Target Definition

| Class | Name | Definition | Trading Logic |
|-------|------|------------|---------------|
| 0 | **HOLD** | No signals, neutral bias (±0.3σ) | Truly flat — wait |
| 1 | **LONG** | Single "L" signal | Mean-revert LONG |
| 2 | **SHORT** | Single "S" signal | Mean-revert SHORT |
| 3 | **MEAN_REVERT_LONG** | Multiple signals, first is L | Strong oversold — confident LONG |
| 4 | **MEAN_REVERT_SHORT** | Multiple signals, first is S | Strong overbought — confident SHORT |
| 5 | **TREND_FOLLOW_LONG** | No signals, bullish bias (>+0.3σ) | Trend-follow LONG |
| 6 | **TREND_FOLLOW_SHORT** | No signals, bearish bias (<-0.3σ) | Trend-follow SHORT |

### Class Distribution (verified on full dataset)
```
Class Name                    Count        %     Visual
───────────────────────────────────────────────────────
0     HOLD                      311     5.6%   ██
1     LONG                    1,272    22.8%   ███████████
2     SHORT                   1,290    23.1%   ███████████
3     MEAN_REVERT_LONG          652    11.7%   █████
4     MEAN_REVERT_SHORT         676    12.1%   ██████
5     TREND_FOLLOW_LONG         732    13.1%   ██████
6     TREND_FOLLOW_SHORT        641    11.5%   █████
───────────────────────────────────────────────────────
Total                         5,574   100.0%

Class imbalance ratio: 4.15x (manageable with class weights)
```

---

## HOLD Decomposition Analysis

The original 5-class had HOLD at 30.2%. Analysis revealed it contained:

| Subcategory | Count | % of Original HOLD | Outcome |
|-------------|-------|-------------------|---------|
| Bullish Bias | 732 | 43.5% | Mean return +0.34%, 53.4% up |
| Bearish Bias | 641 | 38.1% | Mean return -0.22%, 52.1% up |
| Truly Neutral | 311 | 18.5% | Near zero return |

**Key insight:** 81.5% of "no signal" bars had directional bias that's tradeable!

### Threshold Sensitivity
- If we used ±0.9σ (instead of ±1σ): 78.7% of HOLD would become signals
- If we used ±0.8σ: 87.1% would become signals
- Current design captures bias WITHOUT changing signal thresholds

---

## Two Trading Strategies Combined

### 📉 Mean-Reversion (Classes 1-4)
Based on BBand zone entries:
- **LONG (1)**: Price dipped to -1σ → expect bounce
- **SHORT (2)**: Price spiked to +1σ → expect drop
- **MEAN_REVERT_LONG (3)**: Multiple oversold signals → stronger bounce expected
- **MEAN_REVERT_SHORT (4)**: Multiple overbought signals → stronger drop expected

### 📈 Trend-Following (Classes 5-6)
Based on directional bias when no reversal signal:
- **TREND_FOLLOW_LONG (5)**: Spending time above mid (>+0.3σ) → trending up
- **TREND_FOLLOW_SHORT (6)**: Spending time below mid (<-0.3σ) → trending down

### ⏸️ True Wait (Class 0)
- **HOLD (0)**: No signal AND no bias → genuinely flat, wait

---

## Pattern Details

### Mean-Reversion Patterns

**MEAN_REVERT_LONG (class 3):**
| Pattern | Count | Meaning |
|---------|-------|---------|
| LL | 399 | Double dip to oversold |
| LS | 173 | Dip then spike (V-bottom) |
| LLL, LLS, LSL, LSS | rare | Extended oversold |

**MEAN_REVERT_SHORT (class 4):**
| Pattern | Count | Meaning |
|---------|-------|---------|
| SS | 356 | Double spike to overbought |
| SL | 213 | Spike then dip (Λ-top) |
| SSS, SSL, SLS, SLL | rare | Extended overbought |

### Trend-Following Bias

**TREND_FOLLOW_LONG (class 5):**
- Mean position: >+0.3σ above BBand mid
- Interpretation: Consistent upward drift without touching extremes
- Action: Follow the trend with LONG

**TREND_FOLLOW_SHORT (class 6):**
- Mean position: <-0.3σ below BBand mid
- Interpretation: Consistent downward drift without touching extremes
- Action: Follow the trend with SHORT

---

## Signal Alignment Verification

Tested whether 1h signals predict 8h outcomes:
- LONG signals: **53.3%** of next 8h bars were UP
- SHORT signals: **52.5%** of next 8h bars were DOWN
- Overall accuracy: **52.9%** (above 50% random baseline)

The edge is small but real — suitable for ML to learn and amplify.

---

## Implementation

### Enum Definition
```python
class EntrySignalClass(IntEnum):
    HOLD = 0               # No signals, neutral
    LONG = 1               # Single L
    SHORT = 2              # Single S  
    MEAN_REVERT_LONG = 3   # LL, LS, LLL, ...
    MEAN_REVERT_SHORT = 4  # SS, SL, SSS, ...
    TREND_FOLLOW_LONG = 5  # Bullish bias, no signal
    TREND_FOLLOW_SHORT = 6 # Bearish bias, no signal
```

### Target Computation Logic
```python
def compute_entry_signal_7c(df_1h: pl.DataFrame) -> pl.DataFrame:
    """
    Compute 7-class entry_signal target from 1h BBand signals aggregated to 8h.
    
    Steps:
    1. Compute BBands (period=20)
    2. Detect NEW signals (zone entry transitions)
    3. Compute std_from_mid for bias detection
    4. Aggregate to 8h bars: collect signal sequence + mean bias
    5. Map to 7-class target
    """
    
    # BBands
    df = df_1h.with_columns([
        pl.col("close").rolling_mean(20).alias("bband_mid"),
        pl.col("close").rolling_std(20).alias("bband_std"),
    ])
    df = df.with_columns([
        (pl.col("bband_mid") - pl.col("bband_std")).alias("long_zone"),
        (pl.col("bband_mid") + pl.col("bband_std")).alias("short_zone"),
        ((pl.col("close") - pl.col("bband_mid")) / pl.col("bband_std")).alias("std_from_mid"),
    ])
    
    # Signal detection (transitions)
    df = df.with_columns([
        (pl.col("close") <= pl.col("long_zone")).alias("in_long"),
        (pl.col("close") >= pl.col("short_zone")).alias("in_short"),
    ])
    df = df.with_columns([
        (pl.col("in_long") & ~pl.col("in_long").shift(1).fill_null(False)).alias("long_signal"),
        (pl.col("in_short") & ~pl.col("in_short").shift(1).fill_null(False)).alias("short_signal"),
    ])
    
    # Aggregate to 8h
    df = df.with_columns(pl.col("timestamp").dt.truncate("8h").alias("bar_8h"))
    
    agg = df.group_by("bar_8h").agg([
        pl.col("long_signal").sum().alias("n_long"),
        pl.col("short_signal").sum().alias("n_short"),
        pl.col("std_from_mid").mean().alias("mean_std"),
    ])
    
    # Get signal sequences
    signals = df.filter(pl.col("long_signal") | pl.col("short_signal"))
    signals = signals.with_columns(
        pl.when(pl.col("long_signal")).then(pl.lit("L")).otherwise(pl.lit("S")).alias("sig")
    )
    patterns = signals.group_by("bar_8h").agg(pl.col("sig").str.concat("").alias("pattern"))
    
    agg = agg.join(patterns, on="bar_8h", how="left")
    agg = agg.with_columns([
        pl.col("pattern").fill_null(""),
        pl.col("mean_std").fill_null(0.0),
    ])
    
    # 7-class classification
    agg = agg.with_columns([
        pl.when(pl.col("pattern") == "L").then(1)                           # LONG
        .when(pl.col("pattern") == "S").then(2)                             # SHORT
        .when(pl.col("pattern").str.starts_with("L")).then(3)               # MEAN_REVERT_LONG
        .when(pl.col("pattern").str.starts_with("S")).then(4)               # MEAN_REVERT_SHORT
        .when((pl.col("pattern") == "") & (pl.col("mean_std") > 0.3)).then(5)   # TREND_FOLLOW_LONG
        .when((pl.col("pattern") == "") & (pl.col("mean_std") < -0.3)).then(6)  # TREND_FOLLOW_SHORT
        .otherwise(0)                                                        # HOLD
        .alias("y_entry_signal")
    ])
    
    return agg
```

---

## Key Design Decisions

1. **Why zone entry (transition) not just "in zone"?**
   - "In zone" would have ~50% of bars as signals (too many)
   - Transitions capture the meaningful event (price just entered oversold/overbought)

2. **Why first signal determines direction for multi-signal?**
   - First signal = initial market state that triggered opportunity
   - Subsequent signals are refinements/confirmations

3. **Why ±0.3σ threshold for bias detection?**
   - Analysis showed clear outcome differentiation at this threshold
   - Bullish bias (+0.34% mean return) vs Bearish bias (-0.22% mean return)
   - Keeps HOLD truly neutral (5.6% of data)

4. **Why not just lower signal threshold to ±0.8σ?**
   - Would change meaning of mean-reversion signals
   - Bias detection is conceptually different (trend-following vs mean-reversion)
   - This way we have TWO distinct strategy types in one target

---

## Summary Table

| Class | Name | Count | % | Strategy | Action |
|-------|------|-------|---|----------|--------|
| 0 | HOLD | 311 | 5.6% | None | Wait |
| 1 | LONG | 1,272 | 22.8% | Mean-Reversion | Buy dip |
| 2 | SHORT | 1,290 | 23.1% | Mean-Reversion | Sell spike |
| 3 | MEAN_REVERT_LONG | 652 | 11.7% | Mean-Reversion | Strong buy |
| 4 | MEAN_REVERT_SHORT | 676 | 12.1% | Mean-Reversion | Strong sell |
| 5 | TREND_FOLLOW_LONG | 732 | 13.1% | Trend-Following | Follow up |
| 6 | TREND_FOLLOW_SHORT | 641 | 11.5% | Trend-Following | Follow down |

**Total: 5,574 8h bars | Imbalance: 4.15x | Truly neutral: only 5.6%**

3. **Why 5 classes not 7?**
   - Merging LL+LS and SS+SL reduces imbalance (2.58x vs 8.34x)
   - Both represent "strong mean reversion setup from same initial direction"

4. **Why not exclude HOLD?**
   - Model should learn to predict "no opportunity" — valuable for position sizing
   - Avoids forcing trades when signal quality is low

## Files

- **Target computation**: `scripts/workflow/targets.py` → `compute_entry_signal()`
- **Config**: `scripts/workflow/config.py` → WORKFLOW_TARGETS
- **Label names**: `backtest/services/backtest.py` → LABEL_NAMES
