# Target Definitions

Source: [scripts/workflow/targets.py](../../scripts/workflow/targets.py)

---

## Summary Table

| Target | Type | Classes | Column | Description |
|--------|------|---------|--------|-------------|
| `direction` | Classification | 3 | `y_direction_3c` | Price direction from triple barrier |
| `volatility` | Regression | - | `y_volatility` | Absolute forward return |
| `vol_regime` | Classification | 3 | `y_vol_regime` | Volatility percentile bucket |
| `trend_regime` | Classification | 2 | `y_trend_regime` | SMA crossover trend |
| `first_extreme` | Classification | 2 | `y_first_extreme` | Which 8h extreme hit first |
| `time_to_extreme` | Regression | - | `y_time_to_extreme` | Bars until first extreme (0-31) |
| `vol_to_extreme` | Regression | - | `y_vol_to_extreme` | Move size to first extreme |

---

## Classification Targets

### 1. `direction` (3-class)

**What it predicts:** Price direction over next `horizon` bars

**Classes:**
| Value | Label | Meaning |
|-------|-------|---------|
| 0 | DOWN | Clear short signal (SL hit or strong negative) |
| 1 | UP | Clear long signal (TP hit or strong positive) |
| 2 | NEUTRAL | No clear signal (TIME barrier, weak move) |

**Computation:**
1. Calculate net candle return: `(future_high - close)/close - (close - future_low)/close`
2. Use triple-barrier info if available (TP/SL/TIME barriers)
3. For TIME barrier: classify based on rolling vol threshold (0.5 × rolling_std)
4. Threshold clipped to [0.5%, 5%] to handle extreme volatility

**Reference:** [targets.py#L178-242](../../scripts/workflow/targets.py)

---

### 2. `vol_regime` (3-class)

**What it predicts:** Current volatility state

**Classes:**
| Value | Label | Meaning |
|-------|-------|---------|
| 0 | LOW | Below 25th percentile volatility |
| 1 | MEDIUM | 25th to 75th percentile |
| 2 | HIGH | Above 75th percentile |

**Computation:**
1. Calculate log returns: `log(close/close.shift(1))`
2. Rolling std with window = `max(21, horizon*3)`
3. Thresholds from warmup period (first 1000 bars) to avoid look-ahead bias
4. Bucket based on fixed 25th/75th percentiles

**Reference:** [targets.py#L270-312](../../scripts/workflow/targets.py)

---

### 3. `trend_regime` (2-class)

**What it predicts:** Trend direction from SMA crossover

**Classes:**
| Value | Label | Meaning |
|-------|-------|---------|
| 0 | DOWN | Fast SMA < Slow SMA (downtrend) |
| 1 | UP | Fast SMA > Slow SMA (uptrend) |

**Computation:**
1. Fast SMA: `max(21, horizon*5)` periods
2. Slow SMA: `max(63, horizon*15)` periods
3. Binary: `fast > slow`

**Reference:** [targets.py#L314-349](../../scripts/workflow/targets.py)

---

### 4. `first_extreme` (2-class)

**What it predicts:** Which 8h bar extreme (high or low) will be hit first

**Classes:**
| Value | Label | Meaning |
|-------|-------|---------|
| 0 | LOW_FIRST | 8h low touched before 8h high (bearish momentum) |
| 1 | HIGH_FIRST | 8h high touched before 8h low (bullish momentum) |

**Computation:**
1. Loads 32 × 15m bars within each 8h period
2. Scans chronologically to find which extreme reached first
3. Uses tolerance of 0.01% for extreme detection
4. Shifted by `-horizon` for forward prediction

**Data source:** `fetchingByBit/sorted-15m-bybit-linear/`

**Reference:** [targets.py#L500-534](../../scripts/workflow/targets.py)

---

## Regression Targets

### 5. `volatility`

**What it predicts:** Magnitude of price movement (absolute return)

**Formula:** `|close[t+horizon] - close[t]| / close[t]`

**Reference:** [targets.py#L246-268](../../scripts/workflow/targets.py)

---

### 6. `time_to_extreme`

**What it predicts:** How quickly the first extreme is reached

**Range:** 0-31 (15m bars = 0-8 hours)

**Use case:** Lower = faster momentum development, higher = slower/choppier

**Reference:** [targets.py#L536-566](../../scripts/workflow/targets.py)

---

### 7. `vol_to_extreme`

**What it predicts:** Size of move to first extreme

**Formula:** `|open_8h - first_extreme_price| / open_8h`

**Use case:** Position sizing - larger expected moves = larger potential profit

**Reference:** [targets.py#L568-598](../../scripts/workflow/targets.py)

---

## Label Enums

```python
class DirectionLabel(IntEnum):
    DOWN = 0
    UP = 1
    NEUTRAL = 2

class VolRegimeLabel(IntEnum):
    LOW = 0
    MEDIUM = 1
    HIGH = 2

class TrendRegimeLabel(IntEnum):
    DOWN = 0
    UP = 1

class FirstExtremeLabel(IntEnum):
    LOW_FIRST = 0
    HIGH_FIRST = 1
```

**Reference:** [targets.py#L64-87](../../scripts/workflow/targets.py)

---

## Horizons

All targets support 4 horizons:
- `1bar` = 8 hours ahead
- `3bar` = 24 hours ahead
- `6bar` = 48 hours ahead
- `12bar` = 96 hours ahead

Config naming: `{target}_{horizon}bar` (e.g., `direction_1bar`, `volatility_3bar`)

---

## Adding New Targets

1. Create enum if classification:
```python
class MyLabel(IntEnum):
    CLASS_A = 0
    CLASS_B = 1
```

2. Register with decorator:
```python
@register_target(
    name="my_target",
    task_type="classification",  # or "regression"
    n_classes=2,                 # None for regression
    target_column="y_my_target",
    description="...",
    label_enum=MyLabel,          # None for regression
)
def compute_my_target(close, high, low, horizon, **kwargs):
    ...
    return labels
```

**Reference:** [targets.py#L15-48](../../scripts/workflow/targets.py)
