# Volatility Target Redesign

## Terminology Clarification

**IMPORTANT:** "vol" is ambiguous in trading contexts:
- **Volume** = Number of contracts/shares traded (liquidity metric)
- **Volatility** = Standard deviation of returns (risk/movement metric)

This document discusses **VOLATILITY** (price movement risk), NOT volume.

---

## Current Target Inventory

We have TWO volatility-related targets:

| Target Name | Type | Predicts | Column |
|-------------|------|----------|--------|
| `volatility` | Regression | `\|close[t+h] - close[t]\| / close[t]` (absolute return magnitude) | `y_volatility` |
| `vol_spike` | Classification | Binary: will volatility increase 50%+ in next H bars? | `y_vol_spike` |

**Key difference:**
- `volatility` = predicts the MAGNITUDE of price movement (continuous)
- `vol_spike` = predicts whether volatility will INCREASE significantly (binary)

---

## Where `vol_spike` is Defined

**Definition:** `scripts/workflow/targets.py` lines 270-315
```python
@register_target(
    name="vol_spike",
    task_type="classification",
    n_classes=2,
    target_column="y_vol_spike",
    description="Binary: predicts 50%+ volatility increase in next N bars",
    label_enum=VolSpikeLabel,
)
```

**Enum:** `scripts/workflow/targets.py` lines 77-80
```python
class VolSpikeLabel(IntEnum):
    NO_SPIKE = 0  # Vol ratio < 1.5 (stable or decreasing)
    SPIKE = 1     # Vol ratio >= 1.5 (50%+ increase)
```

---

## Where `vol_spike` is Called/Referenced

| File | Line | Usage |
|------|------|-------|
| `scripts/workflow/config.py` | 51 | Listed in `WORKFLOW_TARGETS` |
| `scripts/workflow/targets.py` | 270-315 | Definition |
| `backtest/services/backtest.py` | ~65 | Label display names (if added) |
| `data/datasets/vol_spike_1bar.parquet` | — | Generated dataset |

---

## Problem Summary

**Issue:** `vol_spike` target causes backtest crash at step 104+

**Root Cause Chain:**
1. `vol_spike` uses `spike = (future_vol / current_vol) >= 1.5` (50% increase threshold)
2. Volatility spikes are **rare events** (~5-10% of bars)
3. During calm market periods, training windows have 100% NO_SPIKE labels
4. When only 1 class exists, `train_predict_classification_permodel()` early-exits
5. Early-exit returns `components = {"models_trained": False}` without `cb_pred`, `lgb_pred` etc.
6. Later, `_display_step_metrics()` reads all predictions as DataFrame
7. Rows without `cb_pred` become NaN → `accuracy_score()` crashes

**Evidence from step 104:**
```
vol_spike_1bar           NO_SPIKE NO_SPIKE      ✓  |   104/104       100.0%
```
100% accuracy = 100% NO_SPIKE = zero class diversity = crash trigger

---

## Current Implementation

```python
# targets.py lines 270-315
@register_target(
    name="vol_spike",
    task_type="classification",
    n_classes=2,
    target_column="y_vol_spike",
    description="Binary: predicts 50%+ volatility increase in next N bars",
    label_enum=VolSpikeLabel,
)
def compute_vol_spike(
    close, high, low, horizon,
    vol_window: int = 21,
    spike_threshold: float = 1.5,
    **kwargs,
):
    log_returns = np.log(close / close.shift(1))
    rolling_vol = log_returns.rolling(vol_window).std()
    future_vol = rolling_vol.shift(-horizon)
    
    vol_ratio = future_vol / rolling_vol.clip(lower=1e-8)
    labels = (vol_ratio >= spike_threshold).astype(float)
    
    labels[rolling_vol.isna() | future_vol.isna()] = np.nan
    return labels
```

**Labels:**
- `0 (NO_SPIKE)`: Vol ratio < 1.5
- `1 (SPIKE)`: Vol ratio >= 1.5

**NaN in dataset:** 22/5545 (0.40%)
- First 21 rows: rolling warmup
- Last row: shift(-horizon) edge

---

## What Should This Target Predict?

### Core Question
**"Will the NEXT bar(s) have HIGH or LOW price volatility (return standard deviation)?"**

### Precise Definition

**Volatility** = Standard deviation of log returns over a rolling window

```
log_return[t] = ln(close[t] / close[t-1])
volatility[t] = std(log_return[t-N:t])  # N = window size (typically 21)
```

### Prediction Task Options

| Option | Question Being Asked | Labels |
|--------|---------------------|--------|
| **Spike Detection** | "Will volatility INCREASE by 50%+?" | NO_SPIKE / SPIKE |
| **Regime Classification** | "Will volatility be HIGH or LOW relative to recent history?" | LOW / HIGH |
| **Change Direction** | "Will volatility INCREASE or DECREASE?" | DECREASE / INCREASE |
| **Percentile Bucket** | "Which volatility bucket will we be in?" | LOW / MED / HIGH |

### Naming Conventions (MUST avoid "vol" ambiguity)

| Name | Meaning | Recommended? |
|------|---------|--------------|
| `vol_spike` | ❌ Ambiguous - volume spike? | No |
| `volatility_spike` | ✅ Clear - price volatility spike | Yes |
| `volatility_regime` | ✅ Clear - high/low volatility regime | Yes |
| `price_volatility` | ✅ Explicit - price movement volatility | Yes |
| `return_std_regime` | ✅ Technical - return standard deviation | Yes (for quants) |

### Trading Application

| Prediction | Trading Action |
|------------|----------------|
| HIGH volatility expected | Reduce position size, widen stops |
| LOW volatility expected | Increase position size, tighten stops |
| SPIKE incoming | Risk-off, reduce exposure |
| NO_SPIKE expected | Maintain normal exposure |

---

## Design Options

### Option A: Volatility Regime (Median Split)

**Concept:** HIGH_VOLATILITY vs LOW_VOLATILITY based on rolling median

```python
class VolatilityRegimeLabel(IntEnum):
    LOW = 0   # Future volatility below median
    HIGH = 1  # Future volatility above median

@register_target(
    name="volatility_regime",  # CLEAR: price volatility, not volume
    task_type="classification",
    n_classes=2,
    target_column="y_volatility_regime",
    description="Binary: will future price volatility be HIGH or LOW relative to recent median?",
    label_enum=VolatilityRegimeLabel,
)
def compute_volatility_regime(
    close, high, low, horizon,
    vol_window: int = 21,
    lookback_window: int = 126,  # ~6 months for percentile
    **kwargs,
):
    log_returns = np.log(close / close.shift(1))
    rolling_vol = log_returns.rolling(vol_window).std()
    future_vol = rolling_vol.shift(-horizon)
    
    # Rolling median as adaptive threshold
    vol_median = rolling_vol.rolling(lookback_window).median()
    
    # HIGH if future vol > median, else LOW
    labels = (future_vol > vol_median).astype(float)
    labels[rolling_vol.isna() | future_vol.isna() | vol_median.isna()] = np.nan
    return labels
```

**Pros:**
- Guaranteed ~50/50 class balance by design
- Self-normalizing (adapts to market regime)
- No fixed thresholds

**Cons:**
- More NaN at start (126 bar warmup)
- Median can lag during regime shifts
- "HIGH/LOW" less actionable than "SPIKE"

---

### Option B: Vol Percentile (Quantile-Based)

**Concept:** Classify into HIGH (top 33%) vs LOW (bottom 33%) vs NORMAL (middle 33%)

```python
class VolPercentileLabel(IntEnum):
    LOW = 0      # Bottom tertile
    NORMAL = 1   # Middle tertile  
    HIGH = 2     # Top tertile

def compute_vol_percentile(
    close, high, low, horizon,
    vol_window: int = 21,
    lookback_window: int = 126,
    **kwargs,
):
    log_returns = np.log(close / close.shift(1))
    rolling_vol = log_returns.rolling(vol_window).std()
    future_vol = rolling_vol.shift(-horizon)
    
    # Rolling quantiles
    q33 = rolling_vol.rolling(lookback_window).quantile(0.33)
    q67 = rolling_vol.rolling(lookback_window).quantile(0.67)
    
    labels = pd.Series(1, index=close.index, dtype=float)  # Default NORMAL
    labels[future_vol <= q33] = 0  # LOW
    labels[future_vol >= q67] = 2  # HIGH
    
    labels[rolling_vol.isna() | future_vol.isna() | q33.isna()] = np.nan
    return labels
```

**Pros:**
- 3 classes = more granular
- Balanced by design (~33/33/33)
- Captures both extremes

**Cons:**
- 3-class classification harder than binary
- More NaN from lookback
- May not improve on existing `volatility` regression target

---

### Option C: Vol Change Direction (Simpler)

**Concept:** Will volatility INCREASE or DECREASE?

```python
class VolChangeLabel(IntEnum):
    DECREASE = 0  # Vol will go down
    INCREASE = 1  # Vol will go up

def compute_vol_change(
    close, high, low, horizon,
    vol_window: int = 21,
    **kwargs,
):
    log_returns = np.log(close / close.shift(1))
    rolling_vol = log_returns.rolling(vol_window).std()
    future_vol = rolling_vol.shift(-horizon)
    
    # Simple: will vol increase or decrease?
    labels = (future_vol > rolling_vol).astype(float)
    
    labels[rolling_vol.isna() | future_vol.isna()] = np.nan
    return labels
```

**Pros:**
- Simplest logic
- Natural ~50/50 balance (vol mean-reverts)
- Minimal NaN (only 21 bar warmup)

**Cons:**
- Small changes classified same as large changes
- May be too noisy

---

### Option D: Vol Spike with Lower Threshold

**Concept:** Keep spike detection but use lower threshold (1.2 instead of 1.5)

```python
# Just change threshold
spike_threshold: float = 1.2  # 20% increase instead of 50%
```

**Pros:**
- Minimal code change
- More frequent spikes = better class balance

**Cons:**
- Still event-based (will have imbalanced periods)
- Doesn't guarantee balance
- May still crash during very calm periods

---

### Option E: Adaptive Spike Threshold

**Concept:** Use rolling percentile as threshold instead of fixed ratio

```python
def compute_vol_spike_adaptive(
    close, high, low, horizon,
    vol_window: int = 21,
    lookback_window: int = 126,
    percentile: float = 0.75,  # Top 25% = spike
    **kwargs,
):
    log_returns = np.log(close / close.shift(1))
    rolling_vol = log_returns.rolling(vol_window).std()
    future_vol = rolling_vol.shift(-horizon)
    
    # Rolling 75th percentile as adaptive "spike" threshold
    vol_p75 = rolling_vol.rolling(lookback_window).quantile(percentile)
    
    # Spike if future vol exceeds historical 75th percentile
    labels = (future_vol > vol_p75).astype(float)
    
    labels[rolling_vol.isna() | future_vol.isna() | vol_p75.isna()] = np.nan
    return labels
```

**Pros:**
- Guaranteed ~25% SPIKE class
- Adapts to market regime
- Still "spike" semantics

**Cons:**
- More NaN from lookback
- 75/25 split still somewhat imbalanced

---

## Trading Use Cases

| Target Type | Trading Application |
|-------------|---------------------|
| **HIGH/LOW Vol Regime** | Position sizing - reduce size in HIGH_VOL |
| **Vol Percentile** | Dynamic stop-loss adjustment |
| **Vol Change Direction** | Entry timing - enter on DECREASE prediction |
| **Vol Spike** | Risk-off trigger - reduce exposure before spike |

---

## Recommendation Summary

| Option | Class Balance | Complexity | Actionability | Recommended? |
|--------|---------------|------------|---------------|--------------|
| A: Median Split | ✅ 50/50 | Low | Medium | ✅ Good default |
| B: Percentile | ✅ 33/33/33 | Medium | High | Consider |
| C: Change Dir | ✅ ~50/50 | Lowest | Low | Fallback |
| D: Lower Threshold | ❌ Still imbalanced | Lowest | High | No |
| E: Adaptive Spike | ✅ ~75/25 | Medium | High | ✅ Best of both |

**My suggestion:** Option A (Median Split) or Option E (Adaptive Spike) - both guarantee class balance while remaining interpretable.

---

## Files to Modify (if renaming to `volatility_regime`)

| File | Change Required |
|------|-----------------|
| `scripts/workflow/targets.py` | Rename enum, function, registration |
| `scripts/workflow/config.py` | Change `"vol_spike"` → `"volatility_regime"` in WORKFLOW_TARGETS |
| `backtest/services/backtest.py` | Add label display: `"volatility_regime": {0: "LOW", 1: "HIGH"}` |
| `data/datasets/vol_spike_1bar.parquet` | DELETE - will be regenerated as `volatility_regime_1bar.parquet` |

---

## Decision Needed

1. **Which prediction task?** (spike detection vs regime classification)
2. **Final target name?** Recommend: `volatility_regime` (unambiguous)
3. **Binary (2-class) or ternary (3-class)?** Recommend: Binary (simpler, guaranteed balance)
4. **Which formula?** Recommend: Option A (median split) for guaranteed 50/50 balance
