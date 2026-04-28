# Target Labeling Analysis - Batch-Based Approach

**Date:** 2026-02-05  
**Status:** Analysis Complete  
**Decision:** 8-class target structure

---

# TABLE OF CONTENTS

1. [Overview](#overview)
2. [Data Foundation](#part-1-data-foundation)
3. [Target Design](#part-2-target-design)
4. [Distance Metrics Analysis](#part-3-distance-metrics-analysis)
5. [Trade Implications](#part-4-trade-implications)
6. [Implementation Plan](#part-5-implementation-plan)
7. [Reference Data](#part-6-reference-data)

---

# OVERVIEW

**Goal:** Replace fixed BB TP/SL logic with batch-based approach measuring remaining price movement within each 8h batch.

**Key Innovation:** Use average of top/bottom 5% of remaining bars as outlier level (instead of noisy single max/min).

**Final Decision:** 8-class target with direction + both-side risk information.

---

# PART 1: DATA FOUNDATION

## 1.1 Batch Structure

| Timeframe | Bars per 8h | Complete Batches | Incomplete |
|-----------|-------------|------------------|------------|
| 5m        | 96          | 5,573            | 1 (latest) |
| 15m       | 32          | 5,573            | 1          |
| 1h        | 8           | 5,571            | 1          |

- No gaps in batch sequence
- Only the latest batch is incomplete (still accumulating)

## 1.2 Key Parameters

| Parameter | Value | Reason |
|-----------|-------|--------|
| `RISK_THRESHOLD` | 2.0x | Balanced class distribution (60/40 split) |
| `MIN_REMAINING_BARS` | 10 | Need enough bars for 5% to be meaningful |
| `OUTLIER_PERCENTILE` | 0.05 | Top/bottom 5% of remaining bars |

## 1.3 Timeframe Comparison

| Timeframe | Breakout Classes % | Notes |
|-----------|-------------------|-------|
| 5m (96 bars) | ~51% | Most data, best resolution |
| 15m (32 bars) | ~53% | Good balance |
| 1h (8 bars) | ~29% | Few bars, less extreme moves |

---

# PART 2: TARGET DESIGN

## 2.1 Approach Comparison

| Approach | Classes | Description |
|----------|---------|-------------|
| Original (breakout) | 4 | UP, DOWN, BREAK_UP, BREAK_DOWN — single max/min detection |
| Risk-based | 4 | UP_SAFE, UP_RISKY, DOWN_SAFE, DOWN_RISKY |
| **Full risk (SELECTED)** | **8** | Direction + which side has outlier extremes |

## 2.2 The 8-Class System

| Class | Name | Count | % | Meaning |
|-------|------|-------|---|---------|
| 0 | DOWN_BALANCED | 122,444 | 25.5% | Normal down move, no extremes |
| 1 | DOWN_CONT | 53,516 | 11.2% | Down with downside outliers (momentum) |
| 2 | DOWN_VOLATILE | 46,892 | 9.8% | Down with both-side outliers |
| 3 | UP_BALANCED | 136,268 | 28.4% | Normal up move, no extremes |
| 4 | UP_CONT | 45,425 | 9.5% | Up with upside outliers (momentum) |
| 5 | UP_VOLATILE | 45,789 | 9.6% | Up with both-side outliers |
| 6 | UP_REVERSAL_RISK | 16,625 | 3.5% | Up direction but downside outliers exist |
| 7 | DOWN_REVERSAL_RISK | 12,319 | 2.6% | Down direction but upside outliers exist |

**Distribution Summary:**
- DOWN total: 235,171 (49.1%)
- UP total: 244,107 (50.9%)
- Balanced (no outliers): 258,712 (53.9%)
- With outliers: 220,566 (46.1%)

## 2.3 Core Logic

```python
# Entry reference = close price at entry bar
entry_price = close[i]

# Remaining bars in 8h batch (after entry bar)
remaining_highs = high[i+1 : batch_end]
remaining_lows = low[i+1 : batch_end]

# Sort for percentiles
sorted_highs = np.sort(remaining_highs)
sorted_lows = np.sort(remaining_lows)

# Top/bottom 5%
top_n = max(1, int(count * 0.05))
avg_top_high = np.mean(sorted_highs[-top_n:])  # Outlier high level
avg_bot_low = np.mean(sorted_lows[:top_n])     # Outlier low level

# Regular averages
avg_high = np.mean(remaining_highs)
avg_low = np.mean(remaining_lows)

# Distances from entry
dist_up = avg_high - entry_price
dist_down = entry_price - avg_low

# Outlier distances from entry
outlier_up = avg_top_high - entry_price
outlier_down = entry_price - avg_bot_low

# Risk ratios
risk_up = outlier_up / (abs(dist_up) + epsilon)
risk_down = outlier_down / (abs(dist_down) + epsilon)

# Classification
direction = "UP" if dist_up > dist_down else "DOWN"
high_risk_up = risk_up > RISK_THRESHOLD
high_risk_down = risk_down > RISK_THRESHOLD
```

## 2.4 Threshold Sensitivity

| Risk Threshold | SAFE % | RISKY % | Notes |
|----------------|--------|---------|-------|
| 1.5x | 25.9% | 74.1% | Too sensitive |
| **2.0x** | **60.0%** | **40.0%** | **SELECTED - Balanced** |
| 2.5x | 79.0% | 21.0% | Conservative |
| 3.0x | 88.6% | 11.4% | Very conservative |

---

# PART 3: DISTANCE METRICS ANALYSIS

## 3.1 Global Distance Stats (5m baseline)

| Metric | Mean | P75 | P95 |
|--------|------|-----|-----|
| dist_avg_high | 0.12% | 0.37% | 1.26% |
| dist_top5_high | **0.82%** | 1.06% | 2.72% |
| dist_avg_low | 0.10% | 0.35% | 1.24% |
| dist_bot5_low | **0.85%** | 1.08% | 2.81% |

**Key Finding:** Outlier distance is ~7x larger than average distance.

## 3.2 Metrics by BB Position

### 5m Timeframe

| BB Position | Count | avg_high | top5_high | avg_low | bot5_low |
|-------------|-------|----------|-----------|---------|----------|
| 0-25% | 91,850 | 0.125 | 0.822 | 0.098 | **0.890** |
| 25-50% | 117,930 | 0.113 | 0.807 | 0.098 | 0.851 |
| 50-75% | 122,897 | 0.113 | 0.809 | 0.094 | 0.817 |
| 75-100% | 96,513 | 0.116 | **0.824** | 0.094 | 0.806 |

### 15m Timeframe

| BB Position | Count | avg_high | top5_high | avg_low | bot5_low |
|-------------|-------|----------|-----------|---------|----------|
| 0-25% | 22,653 | 0.220 | 0.979 | 0.207 | **1.123** |
| 25-50% | 31,275 | 0.198 | 0.906 | 0.184 | 0.976 |
| 50-75% | 32,629 | 0.193 | 0.935 | 0.184 | 0.941 |
| 75-100% | 23,775 | 0.206 | **0.993** | 0.189 | 0.961 |

*Note: 1h TF has insufficient data per bucket (only 8 bars per batch).*

## 3.3 Metrics by 2h Segment × BB Position (5m TF)

### Full Grid (Mean values in %)

| Segment | BB Position | Count | avg_high | top5_high | avg_low | bot5_low |
|---------|-------------|-------|----------|-----------|---------|----------|
| **0-2h** | 0-25% | 26,390 | 0.111 | **1.011** | 0.105 | **1.110** |
| 0-2h | 25-50% | 33,402 | 0.108 | 1.007 | 0.100 | 1.072 |
| 0-2h | 50-75% | 33,872 | 0.112 | 1.013 | 0.096 | 1.040 |
| 0-2h | 75-100% | 26,332 | 0.117 | 1.032 | 0.092 | 1.036 |
| **2-4h** | 0-25% | 25,492 | 0.116 | 0.885 | 0.105 | 0.975 |
| 2-4h | 25-50% | 33,377 | 0.108 | 0.865 | 0.101 | 0.924 |
| 2-4h | 50-75% | 35,177 | 0.120 | 0.884 | 0.085 | 0.883 |
| 2-4h | 75-100% | 26,780 | 0.137 | 0.919 | 0.072 | 0.861 |
| **4-6h** | 0-25% | 25,084 | 0.160 | 0.767 | 0.067 | 0.767 |
| 4-6h | 25-50% | 32,679 | 0.128 | 0.732 | 0.088 | 0.749 |
| 4-6h | 50-75% | 34,290 | 0.107 | 0.716 | 0.103 | 0.734 |
| 4-6h | 75-100% | 27,307 | 0.096 | 0.718 | 0.116 | 0.730 |
| **6-8h** | 0-25% | 14,884 | 0.105 | 0.472 | 0.124 | 0.562 |
| 6-8h | 25-50% | 18,472 | 0.108 | 0.474 | 0.104 | 0.502 |
| 6-8h | 50-75% | 19,558 | 0.115 | 0.485 | 0.088 | 0.460 |
| 6-8h | 75-100% | 16,094 | 0.116 | 0.505 | 0.096 | 0.467 |

### Outlier Decay Over Time (52% reduction)

| Segment | Avg top5_high | Avg bot5_low | Outlier Ratio |
|---------|---------------|--------------|---------------|
| 0-2h | **1.016%** | **1.065%** | ~9x |
| 2-4h | 0.888% | 0.911% | ~7.5x |
| 4-6h | 0.733% | 0.745% | ~6x |
| 6-8h | **0.484%** | **0.498%** | ~4.5x |

### BB Position Asymmetry by Segment

| Segment | Lower BB (0-25%) Downside Bias | Upper BB (75-100%) Upside Bias |
|---------|-------------------------------|-------------------------------|
| 0-2h | +9.8% | -0.4% |
| 2-4h | +10.2% | +6.7% |
| 4-6h | +0.0% (balanced) | -1.6% |
| 6-8h | **+19.1%** | +8.1% |

## 3.4 Key Insights

### Risk Asymmetry by BB Position

| Position | dist_top5_high | dist_bot5_low | Asymmetry |
|----------|----------------|---------------|-----------|
| Lower BB (0-25%) | 0.822% | **0.890%** | +8.3% more downside risk |
| Middle (25-75%) | 0.808% | 0.834% | Balanced |
| Upper BB (75-100%) | **0.824%** | 0.806% | +2.2% more upside risk |

### Position-Dependent Outlier Detection

| Entry Position | Remaining Bars | Outlier Detection % |
|---------------|----------------|---------------------|
| Early (0-23) | 72-95 | ~67% |
| Mid-Early (24-47) | 48-71 | ~63% |
| Mid-Late (48-71) | 24-47 | ~51% |
| Late (72-93) | 2-23 | ~21% |

**Problem:** Late entries have fewer remaining bars → less chance to observe extremes.  
**Solution:** Minimum 10 remaining bars cutoff.

### Zone Win Rates

**Long Zones:**

| Zone | Description | Count | Reward | Risk | Win% |
|------|-------------|-------|--------|------|------|
| LZ1 | lower_bb → lower_mid | 91,850 | 0.125% | 0.890% | **53.9%** |
| LZ2 | lower_mid → middle | 117,962 | 0.113% | 0.851% | 51.8% |
| LZ3 | middle → upper_mid | 122,865 | 0.113% | 0.817% | 50.1% |

**Short Zones:**

| Zone | Description | Count | Reward | Risk | Win% |
|------|-------------|-------|--------|------|------|
| SZ1 | upper_mid → upper_bb | 96,513 | 0.094% | 0.824% | **51.8%** |
| SZ2 | middle → upper_mid | 122,865 | 0.094% | 0.809% | 49.9% |
| SZ3 | lower_mid → middle | 117,962 | 0.098% | 0.807% | 48.2% |

---

# PART 4: TRADE IMPLICATIONS

## 4.1 For LONG Positions

| Priority | Class | Name | Reason |
|----------|-------|------|--------|
| **Best** | 4 | UP_CONT | Momentum, upside outliers = extra profit potential |
| **Good** | 3 | UP_BALANCED | Clean up move, predictable |
| **Caution** | 5 | UP_VOLATILE | Both-side risk, unpredictable |
| **Avoid** | 6 | UP_REVERSAL_RISK | Downside outliers exist, stop loss exposure |

## 4.2 For SHORT Positions

| Priority | Class | Name | Reason |
|----------|-------|------|--------|
| **Best** | 1 | DOWN_CONT | Momentum, downside outliers = extra profit potential |
| **Good** | 0 | DOWN_BALANCED | Clean down move, predictable |
| **Caution** | 2 | DOWN_VOLATILE | Both-side risk, unpredictable |
| **Avoid** | 7 | DOWN_REVERSAL_RISK | Upside outliers exist, stop loss exposure |

## 4.3 Design Implications

1. **Zone-aware thresholds:** Risk thresholds could vary by BB position
2. **Asymmetric risk:** Lower BB entries face more downside spikes, upper BB entries face more upside spikes
3. **Mean reversion tendency:** Price at extremes tends to revert to middle
4. **Zone 1 advantage:** Entries near band extremes have ~2-4% higher win rates
5. **Time decay:** Early entries (0-2h) see 52% more outlier potential than late entries (6-8h)

---

# PART 5: IMPLEMENTATION PLAN

## 5.1 Storage Architecture

**DO NOT hardcode metrics** — compute fresh each time and store to files.

### Per-Bar Metrics Files

```
data/htf_backtest/
├── 5m_distance_metrics.parquet
├── 15m_distance_metrics.parquet
├── 1h_distance_metrics.parquet
└── distance_metrics_summary.json
```

**Columns per bar:**
- `dist_avg_high` — distance to average of remaining highs (%)
- `dist_avg_low` — distance to average of remaining lows (%)
- `dist_top5_high` — distance to top 5% high average (%)
- `dist_bot5_low` — distance to bottom 5% low average (%)
- `bb_position_pct` — BB position at entry (0-100%)
- `segment_2h` — which 2h segment (0-3)
- `remaining_bars` — how many bars left in batch

### Per-Batch Aggregates Files (for future 8h labeling)

```
data/htf_backtest/
├── 5m_batch_stats.parquet
├── 15m_batch_stats.parquet
└── 1h_batch_stats.parquet
```

**Columns per batch:**
- `batch_id` — unique batch identifier
- `class_distribution` — count/pct of each class within batch
- `dominant_class` — most frequent class in batch
- `volatility_regime` — batch-level volatility classification
- `direction_bias` — net UP vs DOWN within batch
- `outlier_frequency` — % of bars with outlier conditions

**Future uses:**
1. Label 8h timeframe data (aggregate behavior of lower TFs)
2. Detect regime changes across batches
3. Filter batches by quality/volatility for training
4. Create hierarchical labels (batch context + bar-level target)

### Aggregated Summary (JSON)

- `DISTANCE_METRICS_BY_BB_POSITION` — stats by BB zone
- `DISTANCE_METRICS_BY_SEGMENT_AND_BB` — stats by 2h segment × BB zone
- `SEGMENT_DECAY` — outlier decay rates
- `RISK_ASYMMETRY` — asymmetry by zone

## 5.2 Notebook Cell Structure

**New Cell (before Cell 7):** Compute Distance Metrics
1. Load `{tf}_HTF_combined.parquet` for each TF
2. Compute BB indicators
3. Run numba function to compute per-bar metrics
4. Save to `{tf}_distance_metrics.parquet`
5. Compute per-batch aggregates
6. Save to `{tf}_batch_stats.parquet`
7. Aggregate stats and save to `distance_metrics_summary.json`
8. Print summary for verification

**Cell 7 (modified):** Use precomputed metrics for labeling
- Load `{tf}_distance_metrics.parquet`
- Apply 8-class labeling logic using stored metrics
- No recomputation needed

---

# PART 6: REFERENCE DATA

## 6.1 Precomputed Metrics (Analysis Snapshot)

*Note: These are reference values from analysis. Implementation should compute fresh.*

```python
# =============================================================================
# DISTANCE METRICS BY BB POSITION - FROM 2026-02-05 ANALYSIS
# =============================================================================
# All values are percentages (e.g., 0.125 = 0.125%)

DISTANCE_METRICS_BY_BB_POSITION = {
    '5m': [
        {'bb_range': '0-25%', 'count': 91850, 
         'dist_avg_high_mean': 0.1245, 'dist_avg_high_p75': 0.4002, 'dist_avg_high_p95': 1.2307, 
         'dist_top5_high_mean': 0.8222, 'dist_top5_high_p75': 1.0468, 'dist_top5_high_p95': 2.6569, 
         'dist_avg_low_mean': 0.0979, 'dist_avg_low_p75': 0.3419, 'dist_avg_low_p95': 1.3668, 
         'dist_bot5_low_mean': 0.8900, 'dist_bot5_low_p75': 1.1191, 'dist_bot5_low_p95': 3.0268},
        {'bb_range': '25-50%', 'count': 117930, 
         'dist_avg_high_mean': 0.1133, 'dist_avg_high_p75': 0.3670, 'dist_avg_high_p95': 1.2104, 
         'dist_top5_high_mean': 0.8071, 'dist_top5_high_p75': 1.0294, 'dist_top5_high_p95': 2.6581, 
         'dist_avg_low_mean': 0.0978, 'dist_avg_low_p75': 0.3361, 'dist_avg_low_p95': 1.2542, 
         'dist_bot5_low_mean': 0.8514, 'dist_bot5_low_p75': 1.0815, 'dist_bot5_low_p95': 2.8554},
        {'bb_range': '50-75%', 'count': 122897, 
         'dist_avg_high_mean': 0.1135, 'dist_avg_high_p75': 0.3543, 'dist_avg_high_p95': 1.2141, 
         'dist_top5_high_mean': 0.8091, 'dist_top5_high_p75': 1.0390, 'dist_top5_high_p95': 2.6757, 
         'dist_avg_low_mean': 0.0936, 'dist_avg_low_p75': 0.3484, 'dist_avg_low_p95': 1.1530, 
         'dist_bot5_low_mean': 0.8173, 'dist_bot5_low_p75': 1.0517, 'dist_bot5_low_p95': 2.6922},
        {'bb_range': '75-100%', 'count': 96513, 
         'dist_avg_high_mean': 0.1164, 'dist_avg_high_p75': 0.3500, 'dist_avg_high_p95': 1.2898, 
         'dist_top5_high_mean': 0.8241, 'dist_top5_high_p75': 1.0630, 'dist_top5_high_p95': 2.7892, 
         'dist_avg_low_mean': 0.0941, 'dist_avg_low_p75': 0.3656, 'dist_avg_low_p95': 1.1248, 
         'dist_bot5_low_mean': 0.8058, 'dist_bot5_low_p75': 1.0400, 'dist_bot5_low_p95': 2.5915},
    ],
    '15m': [
        {'bb_range': '0-25%', 'count': 22653, 
         'dist_avg_high_mean': 0.2203, 'dist_avg_high_p75': 0.5308, 'dist_avg_high_p95': 1.4947, 
         'dist_top5_high_mean': 0.9787, 'dist_top5_high_p75': 1.2428, 'dist_top5_high_p95': 3.0480, 
         'dist_avg_low_mean': 0.2068, 'dist_avg_low_p75': 0.4663, 'dist_avg_low_p95': 1.7425, 
         'dist_bot5_low_mean': 1.1229, 'dist_bot5_low_p75': 1.3908, 'dist_bot5_low_p95': 3.5924},
        {'bb_range': '25-50%', 'count': 31275, 
         'dist_avg_high_mean': 0.1983, 'dist_avg_high_p75': 0.4628, 'dist_avg_high_p95': 1.3486, 
         'dist_top5_high_mean': 0.9063, 'dist_top5_high_p75': 1.1476, 'dist_top5_high_p95': 2.8498, 
         'dist_avg_low_mean': 0.1835, 'dist_avg_low_p75': 0.4285, 'dist_avg_low_p95': 1.4398, 
         'dist_bot5_low_mean': 0.9760, 'dist_bot5_low_p75': 1.2460, 'dist_bot5_low_p95': 3.1609},
        {'bb_range': '50-75%', 'count': 32629, 
         'dist_avg_high_mean': 0.1931, 'dist_avg_high_p75': 0.4473, 'dist_avg_high_p95': 1.3995, 
         'dist_top5_high_mean': 0.9352, 'dist_top5_high_p75': 1.2078, 'dist_top5_high_p95': 2.9629, 
         'dist_avg_low_mean': 0.1843, 'dist_avg_low_p75': 0.4484, 'dist_avg_low_p95': 1.3515, 
         'dist_bot5_low_mean': 0.9413, 'dist_bot5_low_p75': 1.2150, 'dist_bot5_low_p95': 2.9905},
        {'bb_range': '75-100%', 'count': 23775, 
         'dist_avg_high_mean': 0.2064, 'dist_avg_high_p75': 0.4768, 'dist_avg_high_p95': 1.5774, 
         'dist_top5_high_mean': 0.9932, 'dist_top5_high_p75': 1.3157, 'dist_top5_high_p95': 3.1898, 
         'dist_avg_low_mean': 0.1892, 'dist_avg_low_p75': 0.5077, 'dist_avg_low_p95': 1.3482, 
         'dist_bot5_low_mean': 0.9612, 'dist_bot5_low_p75': 1.2513, 'dist_bot5_low_p95': 2.8756},
    ],
    '1h': [],  # Insufficient data (only 8 bars per batch)
}

# Summary stats across all BB positions (5m baseline)
GLOBAL_DISTANCE_STATS_5M = {
    'dist_avg_high_mean': 0.116,
    'dist_avg_low_mean': 0.096,
    'dist_top5_high_mean': 0.815,
    'dist_bot5_low_mean': 0.841,
    'outlier_ratio': 7.3,
}

# Risk asymmetry by zone (5m)
RISK_ASYMMETRY = {
    'lower_bb_0_25': {'upside': 0.822, 'downside': 0.890, 'asymmetry_pct': +8.3},
    'middle_25_75': {'upside': 0.808, 'downside': 0.834, 'asymmetry_pct': +3.2},
    'upper_bb_75_100': {'upside': 0.824, 'downside': 0.806, 'asymmetry_pct': -2.2},
}

# Segment decay summary
SEGMENT_DECAY = {
    '0-2h': {'avg_top5_high': 1.016, 'avg_bot5_low': 1.065, 'outlier_ratio': 9.0},
    '2-4h': {'avg_top5_high': 0.888, 'avg_bot5_low': 0.911, 'outlier_ratio': 7.5},
    '4-6h': {'avg_top5_high': 0.733, 'avg_bot5_low': 0.745, 'outlier_ratio': 6.0},
    '6-8h': {'avg_top5_high': 0.484, 'avg_bot5_low': 0.498, 'outlier_ratio': 4.5},
}

# Distance by segment and BB position
DISTANCE_METRICS_BY_SEGMENT_AND_BB = {
    '0-2h': {
        '0-25%': {'count': 26390, 'avg_high': 0.111, 'top5_high': 1.011, 'avg_low': 0.105, 'bot5_low': 1.110},
        '25-50%': {'count': 33402, 'avg_high': 0.108, 'top5_high': 1.007, 'avg_low': 0.100, 'bot5_low': 1.072},
        '50-75%': {'count': 33872, 'avg_high': 0.112, 'top5_high': 1.013, 'avg_low': 0.096, 'bot5_low': 1.040},
        '75-100%': {'count': 26332, 'avg_high': 0.117, 'top5_high': 1.032, 'avg_low': 0.092, 'bot5_low': 1.036},
    },
    '2-4h': {
        '0-25%': {'count': 25492, 'avg_high': 0.116, 'top5_high': 0.885, 'avg_low': 0.105, 'bot5_low': 0.975},
        '25-50%': {'count': 33377, 'avg_high': 0.108, 'top5_high': 0.865, 'avg_low': 0.101, 'bot5_low': 0.924},
        '50-75%': {'count': 35177, 'avg_high': 0.120, 'top5_high': 0.884, 'avg_low': 0.085, 'bot5_low': 0.883},
        '75-100%': {'count': 26780, 'avg_high': 0.137, 'top5_high': 0.919, 'avg_low': 0.072, 'bot5_low': 0.861},
    },
    '4-6h': {
        '0-25%': {'count': 25084, 'avg_high': 0.160, 'top5_high': 0.767, 'avg_low': 0.067, 'bot5_low': 0.767},
        '25-50%': {'count': 32679, 'avg_high': 0.128, 'top5_high': 0.732, 'avg_low': 0.088, 'bot5_low': 0.749},
        '50-75%': {'count': 34290, 'avg_high': 0.107, 'top5_high': 0.716, 'avg_low': 0.103, 'bot5_low': 0.734},
        '75-100%': {'count': 27307, 'avg_high': 0.096, 'top5_high': 0.718, 'avg_low': 0.116, 'bot5_low': 0.730},
    },
    '6-8h': {
        '0-25%': {'count': 14884, 'avg_high': 0.105, 'top5_high': 0.472, 'avg_low': 0.124, 'bot5_low': 0.562},
        '25-50%': {'count': 18472, 'avg_high': 0.108, 'top5_high': 0.474, 'avg_low': 0.104, 'bot5_low': 0.502},
        '50-75%': {'count': 19558, 'avg_high': 0.115, 'top5_high': 0.485, 'avg_low': 0.088, 'bot5_low': 0.460},
        '75-100%': {'count': 16094, 'avg_high': 0.116, 'top5_high': 0.505, 'avg_low': 0.096, 'bot5_low': 0.467},
    },
}
```

---

# NEXT STEPS

- [x] Decide on class structure → **8 classes**
- [ ] Implement distance metrics computation cell
- [ ] Implement 8-class labeling function in notebook Cell 7
- [ ] Consider zone-aware risk thresholds (optional)
- [ ] Validate class distribution across all timeframes
- [ ] Update downstream pipeline to use new targets
