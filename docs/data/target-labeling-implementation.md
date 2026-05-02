# Target Labeling Implementation Guide

**Date:** 2026-02-05  
**Based on:** target-labeling-analysis-2026-02-05.md
**Status:** Ready for Implementation

---

# IMPLEMENTATION CHECKLIST

## Phase 1: Compute Distance Metrics Cell (New Cell before Cell 7)

### Step 1.1: Setup & Configuration
```python
# Constants
RISK_THRESHOLD = 2.0          # Outlier > 2x average = risky
MIN_REMAINING_BARS = 10       # Need enough bars for 5% to be meaningful
OUTLIER_PERCENTILE = 0.05     # Top/bottom 5%
BB_PERIOD = 20
BB_STD = 2.0

# Bars per 8h batch by timeframe
BARS_PER_8H = {"5m": 96, "15m": 32, "1h": 8}
BARS_PER_2H = {"5m": 24, "15m": 8, "1h": 2}

# Timeframes to process
HTF_TIMEFRAMES = ["5m", "15m", "1h"]
```

### Step 1.2: Numba Function for Per-Bar Metrics
```python
@njit
def compute_distance_metrics(close, high, low, batch_id, bar_pos, bars_per_batch):
    """
    Compute distance metrics for each bar.
    
    Returns:
        dist_avg_high: distance to avg of remaining highs (%)
        dist_avg_low: distance to avg of remaining lows (%)
        dist_top5_high: distance to top 5% high avg (%)
        dist_bot5_low: distance to bottom 5% low avg (%)
        remaining_bars: how many bars left in batch
    """
    n = len(close)
    dist_avg_high = np.full(n, np.nan, dtype=np.float64)
    dist_avg_low = np.full(n, np.nan, dtype=np.float64)
    dist_top5_high = np.full(n, np.nan, dtype=np.float64)
    dist_bot5_low = np.full(n, np.nan, dtype=np.float64)
    remaining_bars_out = np.full(n, 0, dtype=np.int32)
    
    for i in range(n):
        remaining = bars_per_batch - 1 - bar_pos[i]
        remaining_bars_out[i] = remaining
        
        if remaining < MIN_REMAINING_BARS:
            continue
            
        entry = close[i]
        current_batch = batch_id[i]
        
        # Find batch end
        batch_end = i + 1
        while batch_end < n and batch_id[batch_end] == current_batch:
            batch_end += 1
        
        count = batch_end - (i + 1)
        if count < MIN_REMAINING_BARS:
            continue
        
        # Collect remaining highs/lows
        highs = np.zeros(count, dtype=np.float64)
        lows = np.zeros(count, dtype=np.float64)
        for j in range(count):
            highs[j] = high[i + 1 + j]
            lows[j] = low[i + 1 + j]
        
        # Sort for percentiles
        sorted_highs = np.sort(highs)
        sorted_lows = np.sort(lows)
        top_n = max(1, int(count * OUTLIER_PERCENTILE))
        
        # Compute averages
        avg_high = np.mean(highs)
        avg_low = np.mean(lows)
        avg_top_high = np.mean(sorted_highs[-top_n:])
        avg_bot_low = np.mean(sorted_lows[:top_n])
        
        # Compute distances as percentages
        dist_avg_high[i] = 100.0 * (avg_high - entry) / entry
        dist_avg_low[i] = 100.0 * (entry - avg_low) / entry
        dist_top5_high[i] = 100.0 * (avg_top_high - entry) / entry
        dist_bot5_low[i] = 100.0 * (entry - avg_bot_low) / entry
    
    return dist_avg_high, dist_avg_low, dist_top5_high, dist_bot5_low, remaining_bars_out
```

### Step 1.3: Process Each Timeframe
```python
for tf in HTF_TIMEFRAMES:
    # 1. Load data
    df = pl.read_parquet(HTF_BACKTEST_DIR / f"{tf}_HTF_combined.parquet")
    df = df.sort(["batch_id", "timestamp"])
    
    # 2. Compute BB indicators
    df = df.with_columns([
        pl.col('close').rolling_mean(window_size=BB_PERIOD).alias('bb_middle'),
        pl.col('close').rolling_std(window_size=BB_PERIOD).alias('bb_std'),
    ]).with_columns([
        (pl.col('bb_middle') + BB_STD * pl.col('bb_std')).alias('bb_upper'),
        (pl.col('bb_middle') - BB_STD * pl.col('bb_std')).alias('bb_lower'),
    ]).with_columns([
        ((pl.col('close') - pl.col('bb_lower')) / 
         (pl.col('bb_upper') - pl.col('bb_lower')) * 100).alias('bb_position_pct'),
    ])
    
    # 3. Compute bar position within batch
    df = df.with_columns(
        (pl.col("timestamp").rank("ordinal").over("batch_id") - 1)
        .cast(pl.Int32).alias("bar_pos")
    )
    
    # 4. Filter complete batches only
    bars_per_batch = BARS_PER_8H[tf]
    complete = df.group_by("batch_id").agg(
        pl.len().alias("n")
    ).filter(pl.col("n") == bars_per_batch)["batch_id"].to_list()
    df = df.filter(pl.col("batch_id").is_in(complete))
    
    # 5. Add 2h segment column
    df = df.with_columns(
        (pl.col('bar_pos') // BARS_PER_2H[tf]).alias('segment_2h')
    )
    
    # 6. Run numba function
    close_np = df["close"].to_numpy()
    high_np = df["high"].to_numpy()
    low_np = df["low"].to_numpy()
    batch_id_np = df["batch_id"].to_numpy()
    bar_pos_np = df["bar_pos"].to_numpy()
    
    d_avg_high, d_avg_low, d_top5_high, d_bot5_low, remaining = compute_distance_metrics(
        close_np, high_np, low_np, batch_id_np, bar_pos_np, bars_per_batch
    )
    
    # 7. Add columns to dataframe
    df = df.with_columns([
        pl.Series('dist_avg_high', d_avg_high),
        pl.Series('dist_avg_low', d_avg_low),
        pl.Series('dist_top5_high', d_top5_high),
        pl.Series('dist_bot5_low', d_bot5_low),
        pl.Series('remaining_bars', remaining),
    ])
    
    # 8. Save per-bar metrics
    output_path = HTF_BACKTEST_DIR / f"{tf}_distance_metrics.parquet"
    df.write_parquet(output_path)
    print(f"✓ Saved {tf} distance metrics: {len(df):,} rows")
```

### Step 1.4: Compute Per-Batch Aggregates
```python
@njit
def compute_8class_label(dist_avg_high, dist_avg_low, dist_top5_high, dist_bot5_low):
    """
    Compute 8-class label for a single bar.
    
    Classes:
        0: DOWN_BALANCED - down, no outliers
        1: DOWN_CONT - down with downside outliers (momentum)
        2: DOWN_VOLATILE - down with both-side outliers
        3: UP_BALANCED - up, no outliers
        4: UP_CONT - up with upside outliers (momentum)
        5: UP_VOLATILE - up with both-side outliers
        6: UP_REVERSAL_RISK - up but downside outliers exist
        7: DOWN_REVERSAL_RISK - down but upside outliers exist
    """
    if np.isnan(dist_avg_high):
        return -1  # Invalid
    
    # Direction
    is_up = dist_avg_high > dist_avg_low
    
    # Risk ratios
    epsilon = 1e-10
    risk_up = dist_top5_high / (abs(dist_avg_high) + epsilon)
    risk_down = dist_bot5_low / (abs(dist_avg_low) + epsilon)
    
    # Outlier flags
    high_risk_up = risk_up > RISK_THRESHOLD
    high_risk_down = risk_down > RISK_THRESHOLD
    
    if is_up:
        if high_risk_up and high_risk_down:
            return 5  # UP_VOLATILE
        elif high_risk_up:
            return 4  # UP_CONT
        elif high_risk_down:
            return 6  # UP_REVERSAL_RISK
        else:
            return 3  # UP_BALANCED
    else:
        if high_risk_up and high_risk_down:
            return 2  # DOWN_VOLATILE
        elif high_risk_down:
            return 1  # DOWN_CONT
        elif high_risk_up:
            return 7  # DOWN_REVERSAL_RISK
        else:
            return 0  # DOWN_BALANCED


for tf in HTF_TIMEFRAMES:
    # Load distance metrics
    df = pl.read_parquet(HTF_BACKTEST_DIR / f"{tf}_distance_metrics.parquet")
    
    # Compute 8-class labels
    labels = []
    for i in range(len(df)):
        label = compute_8class_label(
            df["dist_avg_high"][i],
            df["dist_avg_low"][i],
            df["dist_top5_high"][i],
            df["dist_bot5_low"][i]
        )
        labels.append(label)
    
    df = df.with_columns(pl.Series("target_8class", labels))
    
    # Aggregate per batch
    batch_stats = df.filter(pl.col("target_8class") >= 0).group_by("batch_id").agg([
        # Class distribution
        (pl.col("target_8class") == 0).sum().alias("class_0_count"),
        (pl.col("target_8class") == 1).sum().alias("class_1_count"),
        (pl.col("target_8class") == 2).sum().alias("class_2_count"),
        (pl.col("target_8class") == 3).sum().alias("class_3_count"),
        (pl.col("target_8class") == 4).sum().alias("class_4_count"),
        (pl.col("target_8class") == 5).sum().alias("class_5_count"),
        (pl.col("target_8class") == 6).sum().alias("class_6_count"),
        (pl.col("target_8class") == 7).sum().alias("class_7_count"),
        pl.len().alias("valid_bars"),
        
        # Direction bias
        (pl.col("target_8class") >= 3).mean().alias("up_pct"),  # Classes 3-7 are UP
        
        # Volatility metrics
        pl.col("dist_top5_high").mean().alias("avg_top5_high"),
        pl.col("dist_bot5_low").mean().alias("avg_bot5_low"),
        
        # Outlier frequency
        ((pl.col("target_8class").is_in([1,2,4,5,6,7])).mean()).alias("outlier_frequency"),
    ])
    
    # Compute dominant class
    class_cols = [f"class_{i}_count" for i in range(8)]
    batch_stats = batch_stats.with_columns(
        pl.concat_list(class_cols).list.arg_max().alias("dominant_class")
    )
    
    # Compute volatility regime (based on avg outlier distance)
    global_avg_outlier = batch_stats["avg_top5_high"].mean()
    batch_stats = batch_stats.with_columns(
        pl.when(pl.col("avg_top5_high") > global_avg_outlier * 1.5)
        .then(pl.lit("HIGH"))
        .when(pl.col("avg_top5_high") < global_avg_outlier * 0.5)
        .then(pl.lit("LOW"))
        .otherwise(pl.lit("NORMAL"))
        .alias("volatility_regime")
    )
    
    # Compute direction bias category
    batch_stats = batch_stats.with_columns(
        pl.when(pl.col("up_pct") > 0.6)
        .then(pl.lit("BULLISH"))
        .when(pl.col("up_pct") < 0.4)
        .then(pl.lit("BEARISH"))
        .otherwise(pl.lit("NEUTRAL"))
        .alias("direction_bias")
    )
    
    # Save batch stats
    output_path = HTF_BACKTEST_DIR / f"{tf}_batch_stats.parquet"
    batch_stats.write_parquet(output_path)
    print(f"✓ Saved {tf} batch stats: {len(batch_stats):,} batches")
```

### Step 1.5: Save Summary JSON
```python
import json

# Compute aggregated summary stats
summary = {
    "computed_at": datetime.now().isoformat(),
    "parameters": {
        "RISK_THRESHOLD": RISK_THRESHOLD,
        "MIN_REMAINING_BARS": MIN_REMAINING_BARS,
        "OUTLIER_PERCENTILE": OUTLIER_PERCENTILE,
        "BB_PERIOD": BB_PERIOD,
        "BB_STD": BB_STD,
    },
    "timeframes": {}
}

for tf in HTF_TIMEFRAMES:
    df = pl.read_parquet(HTF_BACKTEST_DIR / f"{tf}_distance_metrics.parquet")
    df_valid = df.filter(pl.col("dist_avg_high").is_not_nan())
    
    summary["timeframes"][tf] = {
        "total_bars": len(df),
        "valid_bars": len(df_valid),
        "complete_batches": df["batch_id"].n_unique(),
        "global_stats": {
            "dist_avg_high_mean": float(df_valid["dist_avg_high"].mean()),
            "dist_avg_low_mean": float(df_valid["dist_avg_low"].mean()),
            "dist_top5_high_mean": float(df_valid["dist_top5_high"].mean()),
            "dist_bot5_low_mean": float(df_valid["dist_bot5_low"].mean()),
        }
    }

with open(HTF_BACKTEST_DIR / "distance_metrics_summary.json", "w") as f:
    json.dump(summary, f, indent=2)

print("✓ Saved distance_metrics_summary.json")
```

---

## Phase 2: Modify Cell 7 for 8-Class Labeling

### Step 2.1: Load Precomputed Metrics
```python
# Load distance metrics (already computed in previous cell)
distance_metrics = {}
for tf in HTF_TIMEFRAMES:
    distance_metrics[tf] = pl.read_parquet(
        HTF_BACKTEST_DIR / f"{tf}_distance_metrics.parquet"
    )
    print(f"Loaded {tf}: {len(distance_metrics[tf]):,} rows")
```

### Step 2.2: Apply 8-Class Labeling (vectorized)
```python
def apply_8class_labels(df: pl.DataFrame) -> pl.DataFrame:
    """
    Apply 8-class labels using precomputed distance metrics.
    """
    epsilon = 1e-10
    
    # Compute risk ratios
    df = df.with_columns([
        (pl.col("dist_top5_high") / (pl.col("dist_avg_high").abs() + epsilon)).alias("risk_up"),
        (pl.col("dist_bot5_low") / (pl.col("dist_avg_low").abs() + epsilon)).alias("risk_down"),
    ])
    
    # Compute flags
    df = df.with_columns([
        (pl.col("dist_avg_high") > pl.col("dist_avg_low")).alias("is_up"),
        (pl.col("risk_up") > RISK_THRESHOLD).alias("high_risk_up"),
        (pl.col("risk_down") > RISK_THRESHOLD).alias("high_risk_down"),
    ])
    
    # Compute 8-class label
    df = df.with_columns(
        pl.when(pl.col("dist_avg_high").is_nan())
        .then(pl.lit(-1))
        # UP classes
        .when(pl.col("is_up") & pl.col("high_risk_up") & pl.col("high_risk_down"))
        .then(pl.lit(5))  # UP_VOLATILE
        .when(pl.col("is_up") & pl.col("high_risk_up"))
        .then(pl.lit(4))  # UP_CONT
        .when(pl.col("is_up") & pl.col("high_risk_down"))
        .then(pl.lit(6))  # UP_REVERSAL_RISK
        .when(pl.col("is_up"))
        .then(pl.lit(3))  # UP_BALANCED
        # DOWN classes
        .when(~pl.col("is_up") & pl.col("high_risk_up") & pl.col("high_risk_down"))
        .then(pl.lit(2))  # DOWN_VOLATILE
        .when(~pl.col("is_up") & pl.col("high_risk_down"))
        .then(pl.lit(1))  # DOWN_CONT
        .when(~pl.col("is_up") & pl.col("high_risk_up"))
        .then(pl.lit(7))  # DOWN_REVERSAL_RISK
        .otherwise(pl.lit(0))  # DOWN_BALANCED
        .alias("target_8class")
    )
    
    # Cleanup temp columns
    df = df.drop(["risk_up", "risk_down", "is_up", "high_risk_up", "high_risk_down"])
    
    return df

# Apply to each timeframe
for tf in HTF_TIMEFRAMES:
    distance_metrics[tf] = apply_8class_labels(distance_metrics[tf])
    
    # Print distribution
    valid = distance_metrics[tf].filter(pl.col("target_8class") >= 0)
    dist = valid.group_by("target_8class").agg(pl.len().alias("count")).sort("target_8class")
    print(f"\n{tf} Class Distribution:")
    print(dist)
```

### Step 2.3: Class Name Mapping
```python
CLASS_NAMES = {
    0: "DOWN_BALANCED",
    1: "DOWN_CONT", 
    2: "DOWN_VOLATILE",
    3: "UP_BALANCED",
    4: "UP_CONT",
    5: "UP_VOLATILE",
    6: "UP_REVERSAL_RISK",
    7: "DOWN_REVERSAL_RISK",
    -1: "INVALID",
}

# Add class name column
for tf in HTF_TIMEFRAMES:
    distance_metrics[tf] = distance_metrics[tf].with_columns(
        pl.col("target_8class").replace(CLASS_NAMES).alias("target_name")
    )
```

---

## Phase 3: Validation & Output

### Step 3.1: Validate Class Distribution
```python
print("="*70)
print("8-CLASS DISTRIBUTION VALIDATION")
print("="*70)

for tf in HTF_TIMEFRAMES:
    df = distance_metrics[tf]
    valid = df.filter(pl.col("target_8class") >= 0)
    total = len(valid)
    
    print(f"\n{tf} ({total:,} valid bars):")
    print("-"*50)
    
    for cls in range(8):
        count = len(valid.filter(pl.col("target_8class") == cls))
        pct = 100 * count / total
        print(f"  {cls}: {CLASS_NAMES[cls]:<20} {count:>10,} ({pct:>5.1f}%)")
    
    # Check direction balance
    up_total = len(valid.filter(pl.col("target_8class") >= 3))
    down_total = len(valid.filter(pl.col("target_8class") < 3))
    print(f"\n  UP total: {up_total:,} ({100*up_total/total:.1f}%)")
    print(f"  DOWN total: {down_total:,} ({100*down_total/total:.1f}%)")
```

### Step 3.2: Save Final Labeled Data
```python
for tf in HTF_TIMEFRAMES:
    output_path = HTF_LABELS_DIR / f"{tf}_8class_labels.parquet"
    distance_metrics[tf].write_parquet(output_path)
    print(f"✓ Saved {output_path.name}")
```

---

## Output Files Summary

After running both cells, you should have:

```
data/htf_backtest/
├── 5m_distance_metrics.parquet     # Per-bar metrics (Phase 1)
├── 15m_distance_metrics.parquet
├── 1h_distance_metrics.parquet
├── 5m_batch_stats.parquet          # Per-batch aggregates (Phase 1)
├── 15m_batch_stats.parquet
├── 1h_batch_stats.parquet
└── distance_metrics_summary.json   # Summary stats (Phase 1)

data/htf_labels/
├── 5m_8class_labels.parquet        # Final labeled data (Phase 2)
├── 15m_8class_labels.parquet
└── 1h_8class_labels.parquet
```

---

## Columns in Final Output

| Column | Type | Description |
|--------|------|-------------|
| timestamp | datetime | Bar timestamp |
| open, high, low, close, volume | float | OHLCV data |
| batch_id | int | 8h batch identifier |
| bar_pos | int | Position within batch (0 to bars_per_8h-1) |
| bb_position_pct | float | BB position (0-100%) |
| segment_2h | int | 2h segment (0-3) |
| remaining_bars | int | Bars left in batch |
| dist_avg_high | float | Distance to avg high (%) |
| dist_avg_low | float | Distance to avg low (%) |
| dist_top5_high | float | Distance to top 5% high (%) |
| dist_bot5_low | float | Distance to bottom 5% low (%) |
| target_8class | int | 8-class target (0-7, or -1 for invalid) |
| target_name | str | Human-readable class name |

---

## Expected Class Distribution (from analysis)

| Class | Name | Expected % |
|-------|------|------------|
| 0 | DOWN_BALANCED | ~25.5% |
| 1 | DOWN_CONT | ~11.2% |
| 2 | DOWN_VOLATILE | ~9.8% |
| 3 | UP_BALANCED | ~28.4% |
| 4 | UP_CONT | ~9.5% |
| 5 | UP_VOLATILE | ~9.6% |
| 6 | UP_REVERSAL_RISK | ~3.5% |
| 7 | DOWN_REVERSAL_RISK | ~2.6% |

---

## Notes

1. **MIN_REMAINING_BARS = 10** — Bars with fewer remaining will have `target_8class = -1`
2. **RISK_THRESHOLD = 2.0** — Outlier > 2x average triggers risk flag
3. **1h timeframe** may have sparse valid bars due to only 8 bars per batch
4. **Batch stats** are for future 8h labeling, not used in current pipeline
