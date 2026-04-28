# HTF Target Labeling Logic (from `notebooks/htf_pythonscript.py`)

> IMPORTANT
> This file is currently a legacy 8-class reference.
> The active workflow has been migrated to `target_4class` (primary) and
> `target_breakfree`. Use this document only as historical context until the
> full 4-class rewrite is completed.

This document explains target computation in the notebook script, with direct code excerpts and file/line references.

File of record:
- `notebooks/htf_pythonscript.py`

## Scope

Historical targets covered in this legacy snapshot:
- `target_8class` (multiclass, 8 labels)
- `target_breakfree` (multiclass, 4 position-aware labels, with neutral `-1`)

Current active workflow targets:
- `target_4class` (primary)
- `target_breakfree` (3-class, non-overlapping):
  - `0`: `UP_ABOVE_BREAKFREE`
  - `1`: `DOWN_ABOVE_BREAKFREE`
  - `2`: `IN_BETWEEN_BELOW_BREAKFREE`
  - `-1`: unlabeled / invalid row

Main labeling flow in the script:
1. Cell 7: compute forward-looking distance metrics (current batch only)
2. Cell 8: create 15m labels (`target_8class`, `target_breakfree`)
3. Cell 9: create hybrid 5m labels (`target_8class`, `target_breakfree`) using 5m entry and 15m future bars
4. Cell 9B: create hybrid 1m labels (`target_8class`, `target_breakfree`) using 1m entry and 15m future bars

## 1) Cell 7: Distance Metrics Base

Reference: `notebooks/htf_pythonscript.py:1107`

```python
# Only use bars within the current batch (no next-batch borrowing).
# This means the last 1 bar (15m) and last 3 bars (5m) are unlabeled
# due to missing forward bars needed for distance metrics.
MIN_REMAINING_BARS_BY_TF = {"5m": 3, "15m": 1}
OUTLIER_PERCENTILE = 0.05  # Top/bottom 5%
BB_PERIOD = 20
BB_STD = 2.0

# Per-timeframe optimal thresholds (used for labeling + batch stats)
TF_THRESHOLDS = {
    "5m": {"BREAKOUT": 1.6, "RISK_RATIO": 2.5},
    "15m": {"BREAKOUT": 2.1, "RISK_RATIO": 2.5},
}

# Bars per 8h batch by timeframe
BARS_PER_8H = {"5m": 96, "15m": 32}
```

### 1.1 Metric computation per row

Reference: `notebooks/htf_pythonscript.py:1144`

```python
@njit
def compute_distance_metrics(close, high, low, batch_id, bar_pos, bars_per_batch, min_remaining):
    n = len(close)
    dist_avg_high = np.full(n, np.nan, dtype=np.float64)
    dist_avg_low = np.full(n, np.nan, dtype=np.float64)
    dist_top5_high = np.full(n, np.nan, dtype=np.float64)
    dist_bot5_low = np.full(n, np.nan, dtype=np.float64)
    remaining_bars_out = np.full(n, 0, dtype=np.int32)

    outlier_pct = 0.05  # Top/bottom 5%

    for i in range(n):
        entry = close[i]
        current_batch = batch_id[i]

        # Find batch end
        batch_end = i + 1
        while batch_end < n and batch_id[batch_end] == current_batch:
            batch_end += 1

        count = batch_end - (i + 1)
        remaining_bars_out[i] = count

        if count < min_remaining:
            continue

        highs = np.zeros(count, dtype=np.float64)
        lows = np.zeros(count, dtype=np.float64)
        for j in range(count):
            highs[j] = high[i + 1 + j]
            lows[j] = low[i + 1 + j]

        sorted_highs = np.sort(highs)
        sorted_lows = np.sort(lows)
        top_n = max(1, int(count * outlier_pct))

        avg_high = np.mean(highs)
        avg_low = np.mean(lows)
        avg_top_high = np.mean(sorted_highs[-top_n:])
        avg_bot_low = np.mean(sorted_lows[:top_n])

        dist_avg_high[i] = 100.0 * (avg_high - entry) / entry
        dist_avg_low[i] = 100.0 * (entry - avg_low) / entry
        dist_top5_high[i] = 100.0 * (avg_top_high - entry) / entry
        dist_bot5_low[i] = 100.0 * (entry - avg_bot_low) / entry

    return dist_avg_high, dist_avg_low, dist_top5_high, dist_bot5_low, remaining_bars_out
```

Interpretation:
- `dist_avg_high`: upside potential from current close to average future highs
- `dist_avg_low`: downside potential from current close to average future lows
- `dist_top5_high`: extreme upside tail metric (top 5% future highs)
- `dist_bot5_low`: extreme downside tail metric (bottom 5% future lows)
- `remaining_bars`: count of future bars in same batch

### 1.2 Which rows are valid

Reference: `notebooks/htf_pythonscript.py:1263`

```python
# keep full batches
# also keep LAST (possibly incomplete) batch if it has enough bars
bars_per_batch = BARS_PER_8H[tf]
min_remaining = MIN_REMAINING_BARS_BY_TF.get(tf, 1)
min_last_batch_bars = min_remaining + 1

batch_counts = df.group_by("batch_id").agg(pl.len().alias("n")).sort("batch_id")
last_batch_id = batch_counts["batch_id"].max()
valid_batches = batch_counts.filter(
    (pl.col("n") == bars_per_batch)
    | ((pl.col("batch_id") == last_batch_id) & (pl.col("n") >= min_last_batch_bars))
)["batch_id"].to_list()
```

Effect:
- Full batches are always kept.
- Last incomplete batch is kept only if it can still produce at least one labeled row.

### 1.3 Output of Cell 7

Reference: `notebooks/htf_pythonscript.py:1328`

```python
output_path = HTF_BACKTEST_DIR / f"{tf}_distance_metrics.parquet"
df.write_parquet(output_path)
```

Files:
- `data/htf_backtest/5m_distance_metrics.parquet`
- `data/htf_backtest/15m_distance_metrics.parquet`

## 2) Cell 8: 15m Labeling

Reference: `notebooks/htf_pythonscript.py:1605`

### 2.1 Core thresholds and breakfree threshold

Reference: `notebooks/htf_pythonscript.py:1658`

```python
BREAKFREE_THRESHOLD = 0.001  # 0.10%
PROCESS_TIMEFRAMES = ["15m"]
```

### 2.2 8-class logic (vectorized)

Reference: `notebooks/htf_pythonscript.py:1679`

```python
def compute_8class_labels(df: pl.DataFrame, breakout_thresh: float, risk_thresh: float) -> pl.DataFrame:
    eps = 1e-10

    # Scenario detection
    df = df.with_columns([
        (pl.col("dist_avg_low") < 0).alias("is_breakout_up"),
        (pl.col("dist_avg_high") < 0).alias("is_breakout_down"),
        ((pl.col("dist_avg_low") > 0) & (pl.col("dist_avg_high") > 0)).alias("is_oscillation"),
    ])

    # Direction
    df = df.with_columns([
        pl.when(pl.col("is_breakout_up")).then(pl.lit(True))
        .when(pl.col("is_breakout_down")).then(pl.lit(False))
        .otherwise(pl.col("dist_avg_high") > pl.col("dist_avg_low"))
        .alias("is_up")
    ])

    # Risk flags
    df = df.with_columns([
        pl.when(pl.col("is_breakout_up")).then(pl.col("dist_top5_high") > breakout_thresh)
        .when(pl.col("is_breakout_down")).then(pl.lit(False))
        .otherwise((pl.col("dist_top5_high") / (pl.col("dist_avg_high") + eps)) > risk_thresh)
        .alias("high_risk_up"),

        pl.when(pl.col("is_breakout_down")).then(pl.col("dist_bot5_low") > breakout_thresh)
        .when(pl.col("is_breakout_up")).then(pl.lit(False))
        .otherwise((pl.col("dist_bot5_low") / (pl.col("dist_avg_low") + eps)) > risk_thresh)
        .alias("high_risk_down"),
    ])

    # Class assignment
    df = df.with_columns([
        pl.when(pl.col("dist_avg_high").is_nan()).then(pl.lit(-1))
        .when(pl.col("is_up") & pl.col("high_risk_up") & pl.col("high_risk_down")).then(pl.lit(5))
        .when(pl.col("is_up") & pl.col("high_risk_up") & ~pl.col("high_risk_down")).then(pl.lit(4))
        .when(pl.col("is_up") & ~pl.col("high_risk_up") & pl.col("high_risk_down")).then(pl.lit(6))
        .when(pl.col("is_up") & ~pl.col("high_risk_up") & ~pl.col("high_risk_down")).then(pl.lit(3))
        .when(~pl.col("is_up") & pl.col("high_risk_up") & pl.col("high_risk_down")).then(pl.lit(2))
        .when(~pl.col("is_up") & ~pl.col("high_risk_up") & pl.col("high_risk_down")).then(pl.lit(1))
        .when(~pl.col("is_up") & pl.col("high_risk_up") & ~pl.col("high_risk_down")).then(pl.lit(7))
        .when(~pl.col("is_up") & ~pl.col("high_risk_up") & ~pl.col("high_risk_down")).then(pl.lit(0))
        .otherwise(pl.lit(-1))
        .alias("target_8class")
    ])
```

### 2.3 Class meaning

- `0 DOWN_BALANCED`: down direction, no high upside/downside tail risk
- `1 DOWN_CONT`: down direction + downside continuation risk
- `2 DOWN_VOLATILE`: down direction + both-sided risk
- `3 UP_BALANCED`: up direction, no high upside/downside tail risk
- `4 UP_CONT`: up direction + upside continuation risk
- `5 UP_VOLATILE`: up direction + both-sided risk
- `6 UP_REVERSAL_RISK`: up direction + downside reversal tail risk
- `7 DOWN_REVERSAL_RISK`: down direction + upside reversal tail risk
- `-1`: invalid (not enough forward bars)

### 2.4 Breakfree target

Reference: `notebooks/htf_pythonscript.py:1852`

```python
# end_return = (close_end - close_now) / close_now
pl.when(pl.col("target_8class") < 0).then(pl.lit(-1))
 .when(pl.col("target_8class").is_in([3, 4, 5, 6]) & (pl.col("end_return") <= -BREAKFREE_THRESHOLD)).then(pl.lit(0))
 .when(pl.col("target_8class").is_in([3, 4, 5, 6]) & (pl.col("end_return") >= BREAKFREE_THRESHOLD)).then(pl.lit(1))
 .when(pl.col("target_8class").is_in([0, 1, 2, 7]) & (pl.col("end_return") <= -BREAKFREE_THRESHOLD)).then(pl.lit(2))
 .when(pl.col("target_8class").is_in([0, 1, 2, 7]) & (pl.col("end_return") >= BREAKFREE_THRESHOLD)).then(pl.lit(3))
 .otherwise(pl.lit(-1))
 .alias("target_breakfree")
```

Interpretation:
- `0`: `LONG_BELOW_BREAKFREE` (long-side setup, end close <= -0.10%)
- `1`: `LONG_ABOVE_BREAKFREE` (long-side setup, end close >= +0.10%)
- `2`: `SHORT_BELOW_BREAKFREE` (short-side setup, end close <= -0.10%)
- `3`: `SHORT_ABOVE_BREAKFREE` (short-side setup, end close >= +0.10%)
- `-1`: neutral zone between -0.10% and +0.10%

### 2.5 Save path

Reference: `notebooks/htf_pythonscript.py:1927`

```python
tf_labels_dir = HTF_LABELS_DIR / tf
batch_path = tf_labels_dir / f"batch_{bid:04d}.parquet"
```

For Cell 8 this is:
- `data/htf_8class_labels/15m/batch_XXXX.parquet`

## 3) Cell 9: Hybrid 5m Labeling (active 5m path)

Reference: `notebooks/htf_pythonscript.py:2016`

This is a different 5m method than plain 5m Cell-7 thresholds.

Design:
- Entry reference is 5m close
- Future path is from remaining 15m bars in the same batch
- This makes 5m labels less noisy while preserving 5m entry timing

### 3.1 Hybrid distance computation

Reference: `notebooks/htf_pythonscript.py:2200`

```python
def compute_hybrid_distance_metrics(
    close_5m, batch_id_5m, bar_pos_15m_for_5m,
    high_15m, low_15m, batch_id_15m, bar_pos_15m,
    min_remaining, outlier_pct,
):
    # for each 5m row, collect remaining 15m rows in same batch with higher 15m bar_pos
    # compute avg/top5/bot5 distances from 5m entry close
```

Actual selection condition:

```python
if batch_id_15m[j] == current_batch and bar_pos_15m[j] > current_15m_pos:
    highs.append(high_15m[j])
    lows.append(low_15m[j])
```

### 3.2 Hybrid thresholds

Reference: `notebooks/htf_pythonscript.py:2060`

```python
BREAKOUT_THRESHOLD = 2.1
RISK_RATIO = 2.5
```

So hybrid 5m currently uses the 15m-like thresholds (not Cell-7 generic 5m `1.6`).

### 3.3 Hybrid 8class and breakfree

References:
- 8class assignment: `notebooks/htf_pythonscript.py:2408`
- breakfree: `notebooks/htf_pythonscript.py:2466`

Both formulas are the same structural logic as Cell 8:
- same class decision tree
- same 4-class position-aware breakfree mapping (plus neutral `-1`)

### 3.4 Save path

Reference: `notebooks/htf_pythonscript.py:2550`

```python
tf_labels_dir = HTF_LABELS_DIR / "5m"
batch_path = tf_labels_dir / f"batch_{bid:04d}.parquet"
```

This writes to:
- `data/htf_8class_labels/5m/batch_XXXX.parquet`

## 4) Final output schema used downstream

Columns saved include (depending on tf/cell):
- OHLCV: `timestamp, open, high, low, close, volume`
- batch/meta: `batch_id`, bar position columns, `remaining_bars`, segment fields
- distance metrics: `dist_avg_high, dist_avg_low, dist_top5_high, dist_bot5_low`
- end-of-batch fields: `close_end, end_return`
- labels: `target_8class, target_name, target_breakfree`

See examples:
- `notebooks/htf_pythonscript.py:1932` (15m list)
- `notebooks/htf_pythonscript.py:2519` (hybrid 5m list)

## 5) Important operational note

There are two potential 5m label-generation paths in the script:
- generic Cell 7/8-style logic
- hybrid Cell 9 logic

The effective data used by backtest is whatever was written last to:
- `data/htf_8class_labels/5m/batch_XXXX.parquet`
- `data/htf_8class_labels/15m/batch_XXXX.parquet`

Current script intent is:
- 15m labels from Cell 8
- 5m labels from Cell 9 hybrid

## 6) Quick verification checklist

Use this when validating outputs without opening the script:

1. Confirm label files exist:
- `data/htf_8class_labels/1m/batch_0001.parquet`
- `data/htf_8class_labels/5m/batch_0001.parquet`
- `data/htf_8class_labels/15m/batch_0001.parquet`

2. Confirm targets present in each file:
- `target_8class`
- `target_breakfree`

3. Confirm invalid rows policy:
- last rows per batch have `target_8class = -1` due to insufficient forward bars

4. Confirm breakfree threshold behavior:
- long-side classes (`target_8class` in `3,4,5,6`):
  - `end_return <= -0.001 => 0 (LONG_BELOW_BREAKFREE)`
  - `end_return >= +0.001 => 1 (LONG_ABOVE_BREAKFREE)`
- short-side classes (`target_8class` in `0,1,2,7`):
  - `end_return <= -0.001 => 2 (SHORT_BELOW_BREAKFREE)`
  - `end_return >= +0.001 => 3 (SHORT_ABOVE_BREAKFREE)`
- otherwise `-1`
