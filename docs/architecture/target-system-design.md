# Target System Design

**Status:** DRAFT - Under Discussion  
**Date:** 2026-01-29  
**Authors:** Przem + Astra

---

## 1. Goal

Design a coherent target system where each target contributes to the final position decision:
- **Direction:** LONG / SHORT / FLAT
- **Size:** How much capital to allocate
- **Confidence:** How sure are we

---

## 2. Core Questions Targets Must Answer

| # | Question | Answer Type | Use in Position |
|---|----------|-------------|-----------------|
| 1 | Which direction will price move? | Classification | Entry direction |
| 2 | What type of move (trend vs revert)? | Classification | Strategy selection |
| 3 | How big will the range be? | Regression | Position sizing |
| 4 | What's the upside potential? | Regression | Reward estimate |
| 5 | What's the downside risk? | Regression | Risk estimate |
| 6 | Are we trading with/against trend? | Classification | Confidence modifier |
| 7 | Is volatility expanding/contracting? | Classification | Exposure adjustment |

---

## 3. Data Sources

### 8h Timeframe Data
- OHLCV at 8h intervals
- Close = price at end of 8h bar
- High/Low = extremes within 8h bar
- Timestamp = bar open time

### 15m Timeframe Data (for intrabar analysis)
- 32 × 15min bars = 1 × 8h bar
- Used to determine: path type, which extreme first, retracement
- Located: `fetchingByBit/sorted-15m-bybit-linear/`

### SMA Calculations
- Fast SMA: 21 bars (7 days at 8h)
- Slow SMA: 63 bars (21 days at 8h)
- Used for: trend regime, trend alignment

### Dataset Pipeline Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         TARGET COMPUTATION PIPELINE                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Step 4: data/datasets/{config}.parquet                                     │
│     │                                                                       │
│     ├── Raw features (170)                                                  │
│     ├── Target columns (y_*)  ← TARGETS COMPUTED HERE via compute_target_polars()
│     └── timestamp                                                           │
│                                                                             │
│  Step 8-9: data/precomputed/{config}/assembled.parquet                      │
│     │                                                                       │
│     ├── Helper features (H_*)                                               │
│     └── pred_idx                                                            │
│                                                                             │
│  Step 9b: data/combined_datasets/{config}.parquet  ← L2 BACKTEST USES THIS  │
│     │                                                                       │
│     ├── Raw features (from datasets/)                                       │
│     ├── Helper features (from precomputed/)                                 │
│     ├── Target columns (y_*)  ← COPIED from datasets/                       │
│     ├── pred_idx                                                            │
│     └── timestamp                                                           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Key Files for Target System

| File | Purpose |
|------|---------|
| `scripts/workflow/targets.py` | Target definitions + compute functions |
| `scripts/workflow/config.py` | WORKFLOW_TARGETS list (which targets to use) |
| `scripts/analysis/signal_labels.py` | TARGET_LABELING_STRATEGY, task types |
| `backtest/services/backtest.py` | LABEL_NAMES (human-readable class names) |
| `scripts/analysis/data.py` | Step 4 calls compute_target_polars() |
| `combined_datasets.py` | Step 9b copies targets to combined dataset |

### To Update Targets

When changing target definitions:

1. **Edit** `scripts/workflow/targets.py` - change compute function
2. **Update** `scripts/workflow/config.py` - add/remove from WORKFLOW_TARGETS
3. **Update** `backtest/services/backtest.py` - add LABEL_NAMES if classification
4. **Update** `scripts/analysis/signal_labels.py` - add TARGET_LABELING_STRATEGY entry
5. **Rerun Step 4** (`cmd_build_datasets`) → regenerates `data/datasets/*.parquet`
6. **Rerun Step 9b** (`create_all_combined_datasets`) → copies to `data/combined_datasets/`
7. **L2 backtest** will now use new targets

---

## 3b. Module Architecture

### `scripts/workflow/targets.py` - SINGLE SOURCE OF TRUTH

**Purpose:** Central hub for ALL target definitions, compute functions, and configuration.

**Architecture:**
```python
# 1. LABEL ENUMS - Define class values
class DirectionLabel(IntEnum):
    STRONG_BULLISH = 0  # >50% above +1σ band AND closes above +1σ
    BULLISH = 1         # >50% above SMA AND closes above SMA
    NEUTRAL = 2         # Mixed zones OR didn't persist at close
    BEARISH = 3         # >50% below SMA AND closes below SMA
    STRONG_BEARISH = 4  # >50% below -1σ band AND closes below -1σ

# 2. TARGET REGISTRY - Global dict storing target configs
_TARGET_REGISTRY: dict[str, TargetConfig] = {}

# 3. @register_target DECORATOR - Auto-registers compute functions
@register_target(
    name="direction",
    task_type="classification",
    n_classes=5,
    target_column="y_direction_5c",
    description="5-class direction from 15m BBand analysis with persistence",
    label_enum=DirectionLabel,
)
def compute_direction(close, high, low, horizon, **kwargs) -> pd.Series:
    ...

# 4. PUBLIC API - Used by other modules
compute_target_pandas()    # Compute target for pandas DataFrames
compute_target_polars()    # Compute target for polars (used in Step 4)
get_target_config()        # Get TargetConfig by name
get_config_horizon()       # Extract horizon from config name
get_config_task_type()     # Classification vs regression
get_config_n_classes()     # Number of classes
```

**Currently Registered Targets (11 total):**

| Name | Type | Classes | Column | Uses 15m Data |
|------|------|---------|--------|---------------|
| `direction` | classification | 5 | `y_direction_5c` | ✅ (BBands) |
| `volatility` | regression | - | `y_volatility` | ❌ |
| `volatility_regime` | classification | 2 | `y_volatility_regime` | ❌ |
| `trend_regime` | classification | 2 | `y_trend_regime` | ❌ |
| `first_extreme` | classification | 2 | `y_first_extreme` | ✅ |
| `time_to_extreme` | regression | - | `y_time_to_extreme` | ✅ |
| `vol_to_extreme` | regression | - | `y_vol_to_extreme` | ✅ |
| `path_label_7` | classification | 7 | `y_path_label_7` | ✅ |
| `path_label_5` | classification | 5 | `y_path_label_5` | ✅ |
| `strategy_label` | classification | 5 | `y_strategy_label` | ✅ |
| `triple_barrier` | classification | 3 | `y_triple_barrier` | ✅ |

**15m Data Helper:**
```python
def _load_15m_data_for_8h(timestamps_8h, data_dir):
    """
    For each 8h timestamp, loads 32 subsequent 15m bars.
    Returns DataFrame with:
        # Path analysis (used by first_extreme, vol_to_extreme, path_label_*)
        - first_extreme: Which extreme hit first (0=low, 1=high)
        - time_to_first: Bars until first extreme (0-31)
        - vol_to_first: Move magnitude to first extreme
        - efficiency_ratio: Kaufman ER (|net| / sum(|moves|))
        - retracement: How much price retraced from first extreme
        - high_time_idx: When high was hit (0-31)
        - low_time_idx: When low was hit (0-31)
        - net_return: (close - open) / open for 8h period
        
        # 5-level BBand analysis (20-period SMA on 15m close)
        # Bands: upper (2σ) > upper_mid (1σ) > mid (SMA) > lower_mid (-1σ) > lower (-2σ)
        - bband_pct_above_upper: % of bars closing above +2σ band
        - bband_pct_above_upper_mid: % of bars closing above +1σ band
        - bband_pct_above_mid: % of bars closing above SMA
        - bband_pct_below_mid: % of bars closing below SMA
        - bband_pct_below_lower_mid: % of bars closing below -1σ band
        - bband_pct_below_lower: % of bars closing below -2σ band
        - bband_closes_above_upper: Final bar closes above +2σ
        - bband_closes_above_upper_mid: Final bar closes above +1σ
        - bband_closes_above_mid: Final bar closes above SMA
        - bband_closes_below_mid: Final bar closes below SMA
        - bband_closes_below_lower_mid: Final bar closes below -1σ
        - bband_closes_below_lower: Final bar closes below -2σ
    """
```

**Critical Pattern - Forward Shift:**
```python
# ALL targets must shift by -horizon for prediction alignment
# At time T, target gives the value for bar at T+horizon
result = analysis["first_extreme"].reindex(close.index)
result = result.shift(-horizon)  # ← CRITICAL
return result
```

---

### `scripts/analysis/signal_labels.py` - LEGACY LABELING UTILITIES

**Purpose:** Original signal labeling module based on triple-barrier research.
Now mostly **DEPRECATED** in favor of targets.py, but still provides:
1. Legacy labeling strategies mapping
2. Adaptive threshold calculation
3. Class weight computation
4. Helper functions for backward compatibility

**Key Components:**

```python
# 1. SIGNAL ENUMS - Different labeling schemes
class Signal3Class(IntEnum):
    DOWN = 0
    UP = 1  
    NEUTRAL = 2

class Signal5Class(IntEnum):
    STRONG_SHORT = 0
    WEAK_SHORT = 1
    NO_SIGNAL = 2
    WEAK_LONG = 3
    STRONG_LONG = 4

# 2. LABELING CONFIG
@dataclass
class LabelingConfig:
    threshold_sigma: float = 0.5      # Volatility multiple
    min_threshold: float = 0.005      # 0.5%
    max_threshold: float = 0.05       # 5%
    vol_lookback: int = 21
    use_triple_barrier: bool = True

# 3. TARGET_LABELING_STRATEGY - Maps target → labeling approach
TARGET_LABELING_STRATEGY = {
    "direction": "tristate_tb",           # Triple-barrier based
    "volatility": "regression",           # Continuous
    "volatility_regime": "existing_binary",
    "trend_regime": "existing_binary",
    "first_extreme": "existing_binary",
    "path_label_5": "existing_multiclass",
    "strategy_label": "existing_multiclass",
    "triple_barrier": "existing_multiclass",
    ...
}

# 4. LEGACY HELPER - Redirects to targets.py
def get_optimal_target_for_config(df, config_name, horizon):
    """DEPRECATED: Now calls compute_target_pandas() from targets.py"""
```

**Functions Still Used:**
- `get_config_task_type()` - Returns classification vs regression
- `get_config_n_classes()` - Returns class count
- `get_target_type_from_config()` - Parses config name like "direction_1bar"

**Functions DEPRECATED:**
- `compute_tristate_labels()` - Was for triple-barrier labeling
- `compute_multiclass_labels()` - 5-class signal labels
- `add_signal_labels_to_df()` - Adds y_signal_* columns

---

### Module Interaction Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        targets.py                                   │
│  SINGLE SOURCE OF TRUTH for target computation                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  @register_target("direction", ...)                                 │
│  def compute_direction()                                            │
│                                                                     │
│  @register_target("path_label_5", ...)                              │
│  def compute_path_label_5()                                         │
│                                                                     │
│  ...11 targets total...                                             │
│                                                                     │
│  ┌─────────────────────────────────────────┐                        │
│  │ PUBLIC API                              │                        │
│  │ • compute_target_polars()  ← Step 4    │                        │
│  │ • compute_target_pandas()              │                        │
│  │ • get_target_config()                  │                        │
│  │ • get_config_horizon()                 │                        │
│  └─────────────────────────────────────────┘                        │
└────────────────────────┬────────────────────────────────────────────┘
                         │
        imports & calls compute functions
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    signal_labels.py                                 │
│  LEGACY module - kept for backward compatibility                    │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  from scripts.workflow.targets import (                             │
│      compute_target_pandas,                                         │
│      get_config_horizon,                                            │
│      get_config_target,                                             │
│  )                                                                  │
│                                                                     │
│  TARGET_LABELING_STRATEGY = {...}  # Maps target → strategy name    │
│                                                                     │
│  def get_optimal_target_for_config():                               │
│      # Redirects to targets.py                                      │
│      target_series = compute_target_pandas(...)                     │
│                                                                     │
│  # DEPRECATED but still present:                                    │
│  # - compute_tristate_labels()                                      │
│  # - compute_multiclass_labels()                                    │
│  # - adaptive threshold functions                                   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

USAGE IN PIPELINE:
                         
Step 4 (data.py)         Step 10 (L2 backtest)       Other scripts
      │                         │                         │
      │                         │                         │
      ▼                         ▼                         ▼
┌─────────────┐          ┌─────────────────┐      ┌────────────────┐
│ compute_    │          │ Reads dataset   │      │ signal_labels  │
│ target_     │          │ with y_* cols   │      │ _labels.py for │
│ polars()    │          │ already present │      │ class weights  │
└─────────────┘          └─────────────────┘      │ and helpers    │
                                                  └────────────────┘
```

---

### Summary: What Each Module Does

| Module | Primary Use | Status |
|--------|-------------|--------|
| **targets.py** | Define & compute targets | ✅ ACTIVE - Single source of truth |
| **signal_labels.py** | Legacy labeling + utilities | ⚠️ MOSTLY DEPRECATED |
| **config.py** | `WORKFLOW_TARGETS` list | ✅ ACTIVE - Controls which targets in pipeline |
| **backtest.py** | `LABEL_NAMES` display | ✅ ACTIVE - Human-readable class names |

**When Adding New Target:**
1. Add enum + `@register_target` function in `targets.py`
2. Add to `WORKFLOW_TARGETS` in `config.py`  
3. Add `LABEL_NAMES` entry in `backtest.py`
4. Add `TARGET_LABELING_STRATEGY` entry in `signal_labels.py` (for backward compat)

---

## 4. Implemented Targets

### Target 1: `direction` (5-class classification) ✅ IMPLEMENTED

**Question:** What will be the price direction behavior in the next 8h?

**Method:** Uses 5-level Bollinger Bands (20-period SMA with ±1σ and ±2σ) on 15m data to classify direction based on:
1. **Position** - Where price spent time relative to bands
2. **Persistence** - Whether it stayed in that zone AND closed there

**BBand Structure (5 levels):**
```
            +2σ ───── upper band (extreme bullish zone)
            +1σ ───── upper_mid band (STRONG threshold for bullish)
             0  ───── mid (SMA - boundary between bullish/bearish)
            -1σ ───── lower_mid band (STRONG threshold for bearish)
            -2σ ───── lower band (extreme bearish zone)
```

**Classes:**
| Value | Name | Definition | Trading Action |
|-------|------|------------|----------------|
| 0 | STRONG_BULLISH | >50% above +1σ band AND closes above +1σ | Strong LONG |
| 1 | BULLISH | >50% above SMA AND closes above SMA (but not STRONG) | LONG |
| 2 | NEUTRAL | Mixed zones OR didn't persist at close | NO TRADE |
| 3 | BEARISH | >50% below SMA AND closes below SMA (but not STRONG) | SHORT |
| 4 | STRONG_BEARISH | >50% below -1σ band AND closes below -1σ | Strong SHORT |

**BBand Parameters:**
- Period: 20 bars (5 hours on 15m data)
- STRONG threshold: ±1σ (upper_mid / lower_mid bands)
- Regular threshold: SMA (mid band)
- Applied to: 15m close prices within each 8h window
- ~32 bars per window, ~12 valid after 20-bar warmup

**Empirical Distribution (5,561 samples, 2021-2026):**
| Class | Count | % | Notes |
|-------|-------|---|-------|
| STRONG_BULLISH | 660 | 11.9% | Persistent above +1σ |
| BULLISH | 1,504 | 27.0% | Above SMA but not extreme |
| NEUTRAL | 1,473 | 26.5% | Mixed zones or didn't persist |
| BEARISH | 1,301 | 23.4% | Below SMA but not extreme |
| STRONG_BEARISH | 623 | 11.2% | Persistent below -1σ |

**Computation:**
```python
# For each 8h period, analyze ~32 x 15m bars (warmup period = 20 bars)
# Calculate 5-level BBands on 15m close
sma = closes.rolling(20).mean()
std = closes.rolling(20).std()
upper_band = sma + 2 * std      # +2σ (extreme)
upper_mid = sma + 1 * std       # +1σ (STRONG threshold)
# mid = sma                     # SMA (regular threshold)
lower_mid = sma - 1 * std       # -1σ (STRONG threshold)
lower_band = sma - 2 * std      # -2σ (extreme)

# Count bars in each zone (only valid bars after warmup)
pct_above_upper_mid = (closes > upper_mid).sum() / n_valid
pct_above_mid = (closes > sma).sum() / n_valid
pct_below_mid = (closes < sma).sum() / n_valid
pct_below_lower_mid = (closes < lower_mid).sum() / n_valid

# Classification requires BOTH position (>50%) AND persistence (closes in zone)
STRONG_BULLISH = (pct_above_upper_mid > 0.5) & closes_above_upper_mid
BULLISH = (pct_above_mid > 0.5) & closes_above_mid & ~STRONG_BULLISH
STRONG_BEARISH = (pct_below_lower_mid > 0.5) & closes_below_lower_mid
BEARISH = (pct_below_mid > 0.5) & closes_below_mid & ~STRONG_BEARISH
NEUTRAL = everything else
```

**Design Evolution:**
- Initial version used 2σ for STRONG → resulted in <1% STRONG classes (too rare)
- Updated to 1σ intermediate bands → ~12% STRONG classes (well balanced)

---

### Target 2: `trade_setup` (4-class classification) ✅ IMPLEMENTED

**Question:** What pullback entry opportunity will occur in the next 8h?

**Replaces:** `first_extreme`, `time_to_extreme`, `vol_to_extreme` (DEPRECATED - these old targets didn't capture sequence information useful for trade entry)

**Method:** Uses 5-level Bollinger Bands to detect **sequence of band touches**. The key insight is: if price dips to -1σ BEFORE reaching +1σ, that's a LONG setup (pullback opportunity). Mirror logic for SHORT.

**BBand Structure (same as direction):**
```
            +2σ ───── upper band      (STRONG_SHORT entry signal)
            +1σ ───── upper_mid band  (SHORT entry / LONG target)
             0  ───── mid (SMA)
            -1σ ───── lower_mid band  (LONG entry / SHORT target)
            -2σ ───── lower band      (STRONG_LONG entry signal)
```

**Helper columns in `_load_15m_data_for_8h()`:**
```python
# First bar index when price closed beyond each band (-1 if never touched)
- first_touch_upper      # First close above +2σ
- first_touch_upper_mid  # First close above +1σ
- first_touch_lower_mid  # First close below -1σ
- first_touch_lower      # First close below -2σ
```

**Classes (4-class, no NO_SETUP):**
| Value | Name | Definition | Trading Action |
|-------|------|------------|----------------|
| 0 | STRONG_LONG | Touched -2σ BEFORE reaching +1σ | Deep pullback buy opportunity |
| 1 | LONG_SETUP | Touched -1σ BEFORE reaching +1σ | Pullback buy opportunity |
| 2 | SHORT_SETUP | Touched +1σ BEFORE reaching -1σ | Pullback short opportunity |
| 3 | STRONG_SHORT | Touched +2σ BEFORE reaching -1σ | Deep pullback short opportunity |

**Note:** NO_SETUP removed - the ~1% of cases where no band was touched are assigned to LONG_SETUP or SHORT_SETUP based on net return direction to avoid class imbalance issues during training.

**Classification Logic:**
```python
# Get first touch indices for each band (-1 = never touched)
ft_upper = analysis["first_touch_upper"]      # First close above +2σ
ft_upper_mid = analysis["first_touch_upper_mid"]  # First close above +1σ
ft_lower_mid = analysis["first_touch_lower_mid"]  # First close below -1σ
ft_lower = analysis["first_touch_lower"]      # First close below -2σ
net_return = analysis["net_return"]           # For assigning ambiguous cases

# STRONG_LONG: Touched -2σ BEFORE reaching +1σ
strong_long = (ft_lower >= 0) & (
    (ft_upper_mid < 0) |                      # Never reached +1σ
    (ft_lower < ft_upper_mid)                 # Or -2σ came first
)

# LONG_SETUP: Touched -1σ BEFORE reaching +1σ (but not -2σ first)
long_setup = ~strong_long & (ft_lower_mid >= 0) & (
    (ft_upper_mid < 0) |                      # Never reached +1σ
    (ft_lower_mid < ft_upper_mid)             # Or -1σ came first
)

# STRONG_SHORT: Touched +2σ BEFORE reaching -1σ
strong_short = (ft_upper >= 0) & (
    (ft_lower_mid < 0) |                      # Never reached -1σ
    (ft_upper < ft_lower_mid)                 # Or +2σ came first
)

# SHORT_SETUP: Touched +1σ BEFORE reaching -1σ (but not +2σ first)
short_setup = ~strong_short & (ft_upper_mid >= 0) & (
    (ft_lower_mid < 0) |                      # Never reached -1σ
    (ft_upper_mid < ft_lower_mid)             # Or +1σ came first
)

# Handle rare ~1% cases where no band touched - assign by net return
unassigned = ~(strong_long | long_setup | short_setup | strong_short)
# Assign to LONG_SETUP if net_return >= 0, else SHORT_SETUP
```

**Example Price Paths:**
| Price Path | Result | Interpretation |
|------------|--------|----------------|
| Bar 5: dips to -2σ, Bar 20: reaches +1σ | STRONG_LONG | Deep pullback, then recovered |
| Bar 8: dips to -1σ, Bar 15: reaches +1σ | LONG_SETUP | Pullback buy worked |
| Bar 3: rallies to +1σ, Bar 25: dips to -1σ | SHORT_SETUP | Pullback short worked |
| Bar 6: rallies to +2σ, Bar 18: dips to -1σ | STRONG_SHORT | Deep rally, then dropped |
| Never touches ±1σ, net return > 0 | LONG_SETUP | Tight range, assigned by return |
| Bar 10: +1σ, Bar 12: -1σ (close timing) | SHORT_SETUP | +1σ came first |

**Use Cases:**
- **Entry timing:** Wait for predicted pullback before entering
- **Direction agnostic:** Works for both LONG and SHORT strategies
- **Combines with `direction`:** 
  - `direction` = BULLISH + `trade_setup` = LONG_SETUP → High confidence buy on dip
  - `direction` = BEARISH + `trade_setup` = SHORT_SETUP → High confidence short on rally
- **STRONG variants:** Indicate deeper pullbacks = better entries

**Actual Distribution (validated on 5,574 samples):**
| Class | Actual % | Notes |
|-------|----------|-------|
| STRONG_LONG | 25.0% | Crypto volatility = frequent -2σ touches |
| LONG_SETUP | 23.3% | Pullback buy patterns |
| SHORT_SETUP | 26.1% | Pullback short patterns |
| STRONG_SHORT | 25.5% | Crypto volatility = frequent +2σ touches |

**Very well balanced distribution!** Crypto's high volatility means most 8h periods touch ±2σ bands, making STRONG variants more common than initially expected.

**Implementation Status:** ✅ COMPLETE
- [x] Add `first_touch_*` columns to `_load_15m_data_for_8h()` helper
- [x] Add `TradeSetupLabel` enum to targets.py (4 classes)
- [x] Add `compute_trade_setup()` function with @register_target
- [x] Add to WORKFLOW_TARGETS in config.py
- [x] Add LABEL_NAMES in backtest.py
- [x] Validate distribution (25%/23%/26%/26% - well balanced)

**DEPRECATED Targets (removed from WORKFLOW_TARGETS):**
- `first_extreme` - Binary, loses sequence info → replaced by trade_setup
- `time_to_extreme` - Regression, not directly actionable → replaced by trade_setup
- `vol_to_extreme` - Regression, not band-relative → replaced by trade_setup

---

## 5. Proposed Targets (Not Yet Implemented)


### Target 2: `move_type` (5-class classification) - PROPOSED

**Question:** What kind of price movement will happen in the next 8h?

**Classes:**
| Value | Name | Definition | Trading Action |
|-------|------|------------|----------------|
| 0 | TREND_UP | net_return > threshold AND ER > 0.2 AND low_first | LONG momentum |
| 1 | TREND_DOWN | net_return < -threshold AND ER > 0.2 AND high_first | SHORT momentum |
| 2 | REVERT_UP | net_return > threshold AND low_first AND retracement > 0.5 | LONG after dip |
| 3 | REVERT_DOWN | net_return < -threshold AND high_first AND retracement > 0.5 | SHORT after rally |
| 4 | SIDEWAYS | abs(net_return) < threshold | NO TRADE |

**Thresholds (calibrate from data):**
- threshold = 0.001 (0.1% net return)
- ER = Efficiency Ratio (Kaufman)

**Computation:**
```python
# Uses 15m data for the NEXT 8h bar (shifted by horizon)
analysis = _get_15m_analysis(close).shift(-horizon)
net_return = analysis["net_return"]
efficiency_ratio = analysis["efficiency_ratio"]
retracement = analysis["retracement"]
low_first = analysis["low_time_idx"] < analysis["high_time_idx"]
```

**Open Questions:**
- [ ] Should SIDEWAYS include high-vol choppy moves or only low-vol?
- [ ] Exact thresholds for ER and retracement?
- [ ] Is 5-class too many? Merge to 3-class (UP/DOWN/FLAT)?

---

### Target 2: `range_pct` (regression)

**Question:** What will be the price range in the next 8h bar?

**Definition:**
```python
range_pct = (future_high - future_low) / current_close
```

**Use:** Position sizing based on expected volatility
- High range → smaller position (more risk per unit)
- Low range → larger position (less risk per unit)

**Computation:**
```python
future_high = high.shift(-horizon)
future_low = low.shift(-horizon)
range_pct = (future_high - future_low) / close
```

**Open Questions:**
- [ ] Use close or open as denominator?
- [ ] Should we normalize by recent average range?

---

### Target 3: `upside_pct` (regression)

**Question:** How much can price rise from current close?

**Definition:**
```python
upside_pct = (future_high - current_close) / current_close
```

**Use:** 
- Reward estimate for LONG positions
- Risk estimate for SHORT positions

**Computation:**
```python
future_high = high.shift(-horizon)
upside_pct = (future_high - close) / close
```

---

### Target 4: `downside_pct` (regression)

**Question:** How much can price fall from current close?

**Definition:**
```python
downside_pct = (current_close - future_low) / current_close
```

**Use:**
- Risk estimate for LONG positions
- Reward estimate for SHORT positions

**Computation:**
```python
future_low = low.shift(-horizon)
downside_pct = (close - future_low) / close
```

---

### Target 5: `trend_alignment` (2-class classification)

**Question:** Is the predicted move aligned with the longer-term trend?

**Classes:**
| Value | Name | Definition |
|-------|------|------------|
| 0 | AGAINST_TREND | Predicted direction opposes SMA trend |
| 1 | WITH_TREND | Predicted direction aligns with SMA trend |

**Use:** Confidence modifier
- WITH_TREND → higher conviction, can size up
- AGAINST_TREND → lower conviction, should size down

**Computation:**
```python
sma_fast = close.rolling(21).mean()
sma_slow = close.rolling(63).mean()
sma_bullish = sma_fast > sma_slow

# Compare to move_type prediction
predicted_up = move_type in [TREND_UP, REVERT_UP]
predicted_down = move_type in [TREND_DOWN, REVERT_DOWN]

trend_alignment = (predicted_up & sma_bullish) | (predicted_down & ~sma_bullish)
```

**Open Questions:**
- [ ] Should this be computed from actual future, or be model-based?
- [ ] If model-based, it depends on move_type prediction accuracy

---

### Target 6: `volatility_regime` (2-class classification)

**Question:** Will volatility expand or contract vs current level?

**Classes:**
| Value | Name | Definition |
|-------|------|------------|
| 0 | DECREASE | Future vol < current vol |
| 1 | INCREASE | Future vol > current vol |

**Use:** Exposure adjustment
- INCREASE → reduce position size (expect bigger moves)
- DECREASE → normal or increase size (expect smaller moves)

**Computation:**
```python
log_returns = np.log(close / close.shift(1))
rolling_vol = log_returns.rolling(21).std()
future_vol = rolling_vol.shift(-horizon)
volatility_regime = (future_vol > rolling_vol).astype(int)
```

---

## 5. Targets to REMOVE / DEPRECATE

| Target | Status | Reason | Replacement |
|--------|--------|--------|-------------|
| `first_extreme` | DEPRECATE | Binary, loses sequence info | `trade_setup` |
| `time_to_extreme` | DEPRECATE | Regression, not directly actionable | `trade_setup` |
| `vol_to_extreme` | DEPRECATE | Regression, not band-relative | `trade_setup` |
| `path_label_5` | KEEP for now | Still in use, may merge later | - |
| `path_label_7` | DEPRECATE | 7-class had rare class issues | `path_label_5` |
| `strategy_label` | KEEP for now | Prescriptive, useful | - |
| `triple_barrier` | KEEP for now | Still in use | - |
| `trend_regime` | KEEP for now | Simple trend filter | - |

---

## 6. Final Target List

| # | Target | Type | Classes | Purpose |
|---|--------|------|---------|---------|
| 1 | `move_type` | classification | 5 | Direction + path type |
| 2 | `range_pct` | regression | - | Expected volatility |
| 3 | `upside_pct` | regression | - | Reward (LONG) / Risk (SHORT) |
| 4 | `downside_pct` | regression | - | Risk (LONG) / Reward (SHORT) |
| 5 | `trend_alignment` | classification | 2 | Confidence modifier |
| 6 | `volatility_regime` | classification | 2 | Exposure adjustment |

**Total: 6 targets (3 classification, 3 regression)**

---

## 7. Position Decision Flow

```
INPUT: Model predictions for all 6 targets

STEP 1: Direction Decision (from move_type)
├── TREND_UP or REVERT_UP → direction = LONG
├── TREND_DOWN or REVERT_DOWN → direction = SHORT
└── SIDEWAYS → direction = FLAT, EXIT

STEP 2: Risk/Reward Check
├── If LONG:
│   ├── risk = downside_pct
│   └── reward = upside_pct
├── If SHORT:
│   ├── risk = upside_pct
│   └── reward = downside_pct
└── risk_reward_ratio = reward / risk
    └── If ratio < MIN_RR (e.g., 1.5) → FLAT, EXIT

STEP 3: Position Sizing
├── base_risk = 0.01 (1% of capital per trade)
├── position_risk = risk prediction (e.g., 0.02 = 2%)
└── base_size = capital × base_risk / position_risk

STEP 4: Confidence Adjustments
├── If trend_alignment == AGAINST_TREND: size *= 0.8
├── If volatility_regime == INCREASE: size *= 0.8
└── (Can stack: both conditions → size *= 0.64)

STEP 5: Final Position
└── position = direction × adjusted_size
```

---

## 8. Open Questions

1. **Class balance for move_type:**
   - What % of data is SIDEWAYS? Too much = class imbalance
   - Should we adjust thresholds to get ~20% per class?

2. **Regression targets normalization:**
   - Raw percentages or normalized by rolling avg?
   - Affects model training and position sizing

3. **Horizon handling:**
   - Design assumes horizon=1 (next 8h bar)
   - How to adapt for horizon=3,6,12?
   - 15m data: need 32×horizon bars?

4. **SMA windows:**
   - Fast=21, Slow=63 fixed or horizon-dependent?
   - Current trend_regime uses `max(21, horizon*5)`

5. **Dependencies:**
   - `trend_alignment` depends on `move_type` prediction
   - Should it be computed from oracle (future data) or model output?
   - If oracle: it's a target to predict
   - If model: it's post-processing, not a target

---

## 9. Next Steps

- [ ] Przem reviews this design
- [ ] Agree on final target list
- [x] Implement `direction` target with 15m BBand analysis
- [ ] Agree on thresholds and definitions for remaining targets
- [ ] Implement remaining targets in targets.py
- [x] Update WORKFLOW_TARGETS in config.py (direction already present)
- [x] Update LABEL_NAMES in backtest.py
- [ ] Test with Step 3-4 pipeline
- [x] Verify class distributions for direction

---

## 10. Discussion Notes

*Add notes from our discussion here:*

```
[2026-01-29] Initial draft created
- Proposed 6 targets to replace current 9
- Key change: move_type combines direction + path into one target
- Regression targets for explicit risk/reward estimation
- TODO: Przem to review and provide feedback

[2026-02-01] Implemented `direction` with 15m BBand analysis
- Changed from 3-class (DOWN/UP/NEUTRAL) to 5-class with BBand persistence
- Uses 20-period SMA ± 2 std on 15m close within each 8h window
- Classification requires BOTH >50% time in zone AND closing in that zone
- Results: STRONG classes very rare (0.2%), BULLISH/BEARISH ~73%, NEUTRAL ~27%
- Files updated: targets.py, backtest.py (LABEL_NAMES), signal_labels.py
- Archived old targets.py to: Archive-usefull-info-from-past-work/targets_backup_2026-02-01.py
- DECISION NEEDED: Keep 5-class or merge STRONG into regular? Adjust thresholds?
```
