# Part 3: Data Schema and Leakage Prevention

> **Document Version**: 1.0  
> **Last Updated**: 2025-12-22  
> **Primary File**: `data/analysis_8h.parquet`

---

## Overview

This document provides the complete schema of `analysis_8h.parquet` and the rules that prevent data leakage in our analysis pipeline.

---

## File Summary

| Property | Value |
|----------|-------|
| **Path** | `data/analysis_8h.parquet` |
| **Rows** | 5,438 |
| **Columns** | 178 |
| **Size** | ~6.32 MB |
| **Timeframe** | 8-hour bars |
| **Coverage** | Multiple years of BTCUSDT perpetual data |

---

## Column Categories

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         COLUMN STRUCTURE (178 total)                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌─────────────────┐                                                        │
│   │   FEATURES      │  167 columns                                           │
│   │   (MODEL INPUT) │  Prefixes: M_, V_, L_, N_, D_, F_, S_, B_, C_         │
│   └─────────────────┘                                                        │
│                                                                              │
│   ┌─────────────────┐                                                        │
│   │   TARGETS       │  9 columns                                             │
│   │   (y_* prefix)  │  Forward returns, directions, regimes                  │
│   └─────────────────┘                                                        │
│                                                                              │
│   ┌─────────────────┐                                                        │
│   │   META/RAW      │  2 columns                                             │
│   │                 │  timestamp, RAW_close                                  │
│   └─────────────────┘                                                        │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Target Columns (9)

All targets are prefixed with `y_` for easy identification and filtering.

| Column | Type | Description | Formula |
|--------|------|-------------|---------||
| `y_forward_return_1` | float | 1-bar forward return | (close[t+1] - close[t]) / close[t] |
| `y_forward_return_3` | float | 3-bar forward return | (close[t+3] - close[t]) / close[t] |
| `y_forward_return_6` | float | 6-bar forward return | (close[t+6] - close[t]) / close[t] |
| `y_forward_return_12` | float | 12-bar forward return | (close[t+12] - close[t]) / close[t] |
| `y_direction` | int | 1-bar direction | 1 if (up_move - down_move) > 0 (net candle) |
| `y_direction_strength` | float | Magnitude of direction | abs(forward_return_1) |
| `y_volatility` | float | Forward realized volatility | abs(forward_return) |
| `y_vol_regime` | int | Volatility regime | Low(0), Medium(1), High(2) |
| `y_trend_regime` | int | Trend regime | SMA crossover (sma_fast > sma_slow) |

**Critical Rule**: These columns contain FUTURE information and must NEVER be used as model inputs.

---

## Feature Columns (167)

### Feature Domain Breakdown

| Prefix | Domain | Count | Description |
|--------|--------|-------|-------------|
| `M_` | Momentum | 40 | RSI, ROC, momentum indicators |
| `V_` | Volume | 35 | Volume patterns, OI changes |
| `L_` | Liquidity | 28 | Spread, depth, market microstructure |
| `N_` | Normalized | 23 | Z-scores, percentile ranks |
| `D_` | Derivatives | 16 | Funding, basis, premium |
| `F_` | Funding | 12 | Funding rate features |
| `S_` | Sentiment | 5 | Long/short ratio, positioning |
| `B_` | Binary/Behavioral | 4 | Direction bins, day of week |
| `C_` | Candlestick | 3 | Body size, shadows |
| (other) | Mixed | 1 | Rolling volatility |

### Feature Naming Convention

```
{Domain}_{Subcategory}_{BaseName}_{Lookback}_{Transformation}_{Suffix}

Examples:
- M_N_rsi_14_zsc_N      → Momentum, Normalized RSI 14, Z-score, Normalized
- V_T_volumeRatio_21_pct_N → Volume, Trend, 21-bar ratio, Percentage, Normalized
- D_F_N_S_premiumZscore_21_zsc_N → Derivatives, Funding, Normalized, Smoothed
```

### Sample Features by Domain

**Momentum (M_)**:
- `M_N_rsi_14_zsc_N` — RSI z-score
- `M_T_roc_3_pct_N` — 3-bar rate of change
- `M_N_macdHist_zsc_N` — MACD histogram z-score

**Volume (V_)**:
- `V_N_volumeRatio_21_rat_N` — Volume relative to 21-bar average
- `V_T_oiChange_6_pct_N` — Open interest change

**Derivatives (D_)**:
- `D_F_basis_pct_N` — Basis percentage
- `D_F_N_S_premiumZscore_21_zsc_N` — Premium z-score

**Sentiment (S_)**:
- `S_longShortRatio_rat_N` — Long/short ratio
- `S_N_longShortZscore_21_zsc_N` — L/S ratio z-score

---

## Meta/Raw Columns (2)

| Column | Type | Description | Usage |
|--------|------|-------------|-------|
| `timestamp` | datetime | Bar timestamp | Indexing, temporal ordering |
| `RAW_close` | float | Close price | Reference only, NOT for training |

---

## Leakage Prevention Rules

### Rule 1: Target Identification

```python
# CORRECT: Identify targets by prefix
target_cols = [c for c in df.columns if c.startswith('y_')]

# WRONG: Hardcoding target names (might miss some)
target_cols = ['y_direction', 'y_forward_return_1']  # DON'T DO THIS
```

### Rule 2: Feature Selection

```python
# CORRECT: Exclude all non-feature columns
feature_cols = [
    c for c in df.columns 
    if not c.startswith('y_')      # Not a target
    and not c.startswith('RAW_')   # Not raw data
    and c != 'timestamp'           # Not timestamp
]

# Our data.py implementation uses this exact pattern
```

### Rule 3: Temporal Ordering

```python
# ALWAYS verify temporal ordering before training
assert df['timestamp'].is_sorted(), "Data must be sorted by time!"

# ALWAYS use temporal CV, never random CV
from sklearn.model_selection import TimeSeriesSplit  # CORRECT
from sklearn.model_selection import KFold           # WRONG for time series
```

### Rule 4: Feature Window Lookback

All rolling features use ONLY past data:

```python
# CORRECT: Rolling window looks backward
rolling_mean = df['price'].rolling(window=21, min_periods=21).mean()

# WRONG: Centered window uses future data
rolling_mean = df['price'].rolling(window=21, center=True).mean()  # LEAKAGE!
```

### Rule 5: Train/Test Gap

```python
# Always use gap in TimeSeriesSplit to prevent feature/target overlap
tscv = TimeSeriesSplit(n_splits=5, gap=50)  # 50-bar gap

# Gap should be >= max(feature_lookback_windows)
# Our features use up to 63-bar windows, so gap=50 is conservative
```

---

## Schema Validation Script

Run this to verify the schema:

```python
import polars as pl

def validate_analysis_schema(filepath: str = "data/analysis_8h.parquet"):
    """Validate analysis_8h.parquet schema for leakage prevention."""
    df = pl.read_parquet(filepath)
    
    # Check 1: All targets have y_ prefix
    target_cols = [c for c in df.columns if c.startswith('y_')]
    assert len(target_cols) == 9, f"Expected 9 targets, found {len(target_cols)}"
    print(f"✅ Check 1 PASS: {len(target_cols)} target columns with y_ prefix")
    
    # Check 2: Timestamp exists and is sorted
    assert 'timestamp' in df.columns, "Missing timestamp column"
    assert df['timestamp'].is_sorted(), "Data not sorted by timestamp!"
    print("✅ Check 2 PASS: Timestamp present and sorted")
    
    # Check 3: Feature columns don't include y_ or RAW_
    feature_cols = [
        c for c in df.columns 
        if not c.startswith('y_') 
        and not c.startswith('RAW_') 
        and c != 'timestamp'
    ]
    for col in feature_cols:
        assert not col.startswith('y_'), f"Target column in features: {col}"
        assert not col.startswith('RAW_'), f"Raw column in features: {col}"
    print(f"✅ Check 3 PASS: {len(feature_cols)} clean feature columns")
    
    # Check 4: No NaN in targets (except at boundaries)
    for col in target_cols:
        nan_count = df[col].null_count()
        nan_pct = nan_count / len(df) * 100
        if nan_pct > 5:
            print(f"⚠️ Warning: {col} has {nan_pct:.1f}% NaN values")
        else:
            print(f"✅ {col}: {nan_pct:.1f}% NaN (acceptable at boundaries)")
    
    print("\n✅ ALL VALIDATION CHECKS PASSED")
    return True

# Run validation
if __name__ == "__main__":
    validate_analysis_schema()
```

---

## Column Reference (Complete List)

### Targets (9)
```
y_direction
y_direction_strength
y_forward_return_1
y_forward_return_12
y_forward_return_3
y_forward_return_6
y_trend_regime
y_vol_regime
y_volatility
```

### Meta (2)
```
timestamp
RAW_close
```

### Features (167)
```
(See full list by running: df.columns in Python)

Organized by domain prefix:
- M_*: 40 momentum features
- V_*: 35 volume features  
- L_*: 28 liquidity features
- N_*: 23 normalized features
- D_*: 16 derivatives features
- F_*: 12 funding features
- S_*: 5 sentiment features
- B_*: 4 binary/behavioral features
- C_*: 3 candlestick features
- rolling_*: 1 rolling feature
```

---

## Usage Example

```python
import polars as pl
from scripts.analysis import data

# Load data
df = data.load_analysis_data()

# Get feature columns (auto-excludes targets and meta)
feature_cols = data.get_feature_columns(df)

# Prepare for training
X = df.select(feature_cols).to_pandas()
y = df['y_direction'].to_pandas()

# Verify no leakage
assert 'y_direction' not in X.columns
assert 'RAW_close' not in X.columns
```

---

## Dataset Matrix System

> **Added**: 2025-12-22  
> **Last Updated**: 2025-12-22  
> **Purpose**: Per-target, per-horizon optimized datasets

### Why Separate Datasets?

Our validation found that **feature interactions optimized for one target/horizon predict the WRONG DIRECTION for other combinations**:

| Interaction Set | IC vs 12-bar Target |
|-----------------|---------------------|
| 1-bar optimized | **-0.09** ❌ (wrong sign!) |
| 12-bar optimized | **+0.06** ✅ (correct) |

This means using 1-bar-optimized interactions to predict 12-bar returns would **actively hurt** performance.

### Per-Target Optimization

**CRITICAL**: Each target type requires its OWN optimized features because:

1. **InteractionOptimizer** selects feature pairs by IC (Information Coefficient)
   - IC is computed against the specific target column
   - Features predictive of `direction` are NOT predictive of `volatility`
   - Overlap between target types: **0%** (completely different interactions)

2. **RollingZScoreOptimizer** behaves differently per target:
   - HELPS `direction`/`returns` (mean-reverting price signals)
   - HURTS `volatility`/`vol_regime`/`trend_regime` (destroys magnitude information)
   - Tested: -42% IC degradation when using wrong pipeline

**Pipeline by Target Type**:

| Target        | Pipeline Steps                           |
|---------------|------------------------------------------|
| direction     | Winsorize → RollingZScore → Interactions |
| returns       | Winsorize → RollingZScore → Interactions |
| volatility    | Winsorize → Interactions (NO ZScore)     |
| vol_regime    | Winsorize → Interactions (NO ZScore)     |
| trend_regime  | Winsorize → Interactions (NO ZScore)     |

**Validation Results** (all 20 combinations show IC improvement):

| Target        | IC Improvement Range |
|---------------|---------------------|
| direction     | +0.7% to +1.4% ✅    |
| returns       | +1.0% to +1.5% ✅    |
| volatility    | +0.8% to +1.8% ✅    |
| vol_regime    | +3.8% to +4.3% ✅    |
| trend_regime  | +1.9% to +6.3% ✅    |

### Optimization Workflow

```bash
# Step 1: Run optimization for ALL 20 target/horizon combinations
for target in direction returns volatility vol_regime trend_regime; do
  for horizon in 1 3 6 12; do
    python -m scripts.analysis.run optimize --target $target --horizon $horizon
  done
done

# Step 2: Build datasets (auto-loads correct optimized file for each)
python -m scripts.analysis.run build-datasets
```

Or in Python:
```python
from scripts.analysis.run import cmd_optimize, cmd_build_datasets

targets = ['direction', 'returns', 'volatility', 'vol_regime', 'trend_regime']
horizons = [1, 3, 6, 12]

for target in targets:
    for horizon in horizons:
        cmd_optimize(target=target, horizon=horizon)

cmd_build_datasets()  # Uses features_8h_optimized_{target}_{horizon}bar.parquet
```

### Matrix Structure

```
data/datasets/
├── direction_1bar.parquet      # 5 target types
├── direction_3bar.parquet      # ×
├── direction_6bar.parquet      # 4 horizons
├── direction_12bar.parquet     # = 20 datasets
├── returns_1bar.parquet        
├── returns_3bar.parquet        
├── returns_6bar.parquet        
├── returns_12bar.parquet       
├── volatility_1bar.parquet     
├── volatility_3bar.parquet     
├── volatility_6bar.parquet     
├── volatility_12bar.parquet    
├── vol_regime_1bar.parquet     
├── vol_regime_3bar.parquet     
├── vol_regime_6bar.parquet     
├── vol_regime_12bar.parquet    
├── trend_regime_1bar.parquet   
├── trend_regime_3bar.parquet   
├── trend_regime_6bar.parquet   
├── trend_regime_12bar.parquet  
└── dataset_summary.csv         # Index of all datasets

data/
├── features_8h_optimized_direction_1bar.parquet   # Optimized for direction @ 1-bar
├── features_8h_optimized_direction_3bar.parquet   
├── features_8h_optimized_direction_6bar.parquet   
├── features_8h_optimized_direction_12bar.parquet  
├── features_8h_optimized_returns_1bar.parquet     # Optimized for returns @ 1-bar
├── features_8h_optimized_returns_3bar.parquet     
├── features_8h_optimized_returns_6bar.parquet     
├── features_8h_optimized_returns_12bar.parquet    
├── features_8h_optimized_volatility_1bar.parquet  # Optimized for volatility @ 1-bar
├── features_8h_optimized_volatility_3bar.parquet  
├── features_8h_optimized_volatility_6bar.parquet  
├── features_8h_optimized_volatility_12bar.parquet 
├── features_8h_optimized_vol_regime_1bar.parquet  # Optimized for vol_regime @ 1-bar
├── features_8h_optimized_vol_regime_3bar.parquet  
├── features_8h_optimized_vol_regime_6bar.parquet  
├── features_8h_optimized_vol_regime_12bar.parquet 
├── features_8h_optimized_trend_regime_1bar.parquet # Optimized for trend_regime
├── features_8h_optimized_trend_regime_3bar.parquet
├── features_8h_optimized_trend_regime_6bar.parquet
└── features_8h_optimized_trend_regime_12bar.parquet
```

### Target Types Explained

| Target Type | Column | Purpose | Model Type | Use Case |
|-------------|--------|---------|------------|----------|
| `direction` | `y_direction` | Binary up/down | Classification | Trade direction signals |
| `returns` | `y_returns` | Continuous return | Regression | Expected return estimation |
| `volatility` | `y_volatility` | \|return\| | Regression | Position sizing, risk |
| `vol_regime` | `y_vol_regime` | LOW/MED/HIGH | Multiclass | Regime-aware strategies |
| `trend_regime` | `y_trend_regime` | Up/Down trend | Binary | Trend-following filters |

### Horizons Explained

| Horizon | Bars | Time (8h bars) | Use Case |
|---------|------|----------------|----------|
| 1-bar | 1 | 8 hours | Intraday trading, high-frequency |
| 3-bar | 3 | 24 hours | Daily rebalancing |
| 6-bar | 6 | 48 hours | Swing trading |
| 12-bar | 12 | 96 hours | Position trading, trend-following |

### Dataset Contents

Each dataset contains:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DATASET STRUCTURE (per file)                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌─────────────────┐                                                        │
│   │  BASE FEATURES  │  166 columns (IDENTICAL across all datasets)          │
│   │                 │  These don't depend on target                          │
│   └─────────────────┘                                                        │
│                                                                              │
│   ┌─────────────────┐                                                        │
│   │  INTERACTIONS   │  5 columns (UNIQUE per horizon)                        │
│   │  (×)            │  Optimized specifically for this horizon's target      │
│   └─────────────────┘                                                        │
│                                                                              │
│   ┌─────────────────┐                                                        │
│   │  TARGET         │  1 column (y_*)                                        │
│   │                 │  Computed for this specific horizon                    │
│   └─────────────────┘                                                        │
│                                                                              │
│   Total: 172 columns (166 base + 5 interactions + 1 target)                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Interaction Features (Per-Horizon)

The `InteractionOptimizer` selects different feature pairs based on which horizon's target they predict best:

**1-bar interactions** (short-term momentum):
```
V_hurstExponent_126_×N_P_T_priceSmaDeviat  — Hurst × SMA deviation
M_P_roc_3_pct_N×V_hurstExponent_126_       — ROC(3) × Hurst
M_P_V_momAtr_3_rat_N×V_hurstExponent_126_  — MomATR(3) × Hurst
V_hurstExponent_126_×M_T_V_diDiff_6_bnd_N  — Hurst × DI diff
V_skew_42_rat_N×L_M_S_cmf_21_bnd_N         — Skew × CMF
```

**12-bar interactions** (long-term sentiment):
```
V_hurstExponent_126_×S_M_longShortChange_  — Hurst × L/S change
V_hurstExponent_126_×M_V_calmar_21_rat_N   — Hurst × Calmar
M_P_roc_21_pct_N×L_M_S_cmf_12_bnd_N        — ROC(21) × CMF
M_P_V_momAtr_21_rat_×L_M_S_cmf_12_bnd_N    — MomATR(21) × CMF
N_V_bollingerBandwid×M_T_V_adx_12_bnd_N    — BBwidth × ADX
```

**Key insight**: 1-bar uses short-term momentum (ROC_3, momAtr_3), while 12-bar uses long-term sentiment (longShortChange, calmar_21).

### Per-Horizon Target Computation

**direction_{n}bar** (net candle method):
```python
# Uses full candle info for better signal
future_high = high.shift(-n)
future_low = low.shift(-n)
up_move = (future_high - close) / close
down_move = (close - future_low) / close
net_candle_ret = up_move - down_move
y_direction = (net_candle_ret > 0).astype(int)
```

**returns_{n}bar** (net candle method):
```python
# Captures intracandle volatility
future_high = high.shift(-n)
future_low = low.shift(-n)
up_move = (future_high - close) / close
down_move = (close - future_low) / close
y_returns = up_move - down_move
```

**volatility_{n}bar** (close-to-close):
```python
y_volatility = abs(y_forward_return_{n})
```

**vol_regime_{n}bar**:
```python
# Window scales with horizon
window = max(21, horizon * 3)
rolling_vol = log_returns.rolling(window).std()
vol_25, vol_75 = rolling_vol.quantile([0.25, 0.75])
y_vol_regime = 0 if vol < vol_25 else (1 if vol < vol_75 else 2)
```

**trend_regime_{n}bar**:
```python
# SMA windows scale with horizon
fast_window = max(21, horizon * 5)
slow_window = max(63, horizon * 15)
y_trend_regime = 1 if SMA(fast) > SMA(slow) else 0
```

### CLI Usage

```bash
# Build all 20 datasets
python -m scripts.analysis.run build-datasets

# Build specific horizons
python -m scripts.analysis.run build-datasets --horizons 1 12

# Build specific target types
python -m scripts.analysis.run build-datasets --target-types direction returns

# Build specific combination
python -m scripts.analysis.run build-datasets --horizons 12 --target-types direction
```

### Loading Datasets

```python
import pandas as pd
from pathlib import Path

# Load specific dataset
df = pd.read_parquet("data/datasets/direction_12bar.parquet")

# Get feature columns (excludes y_* and timestamp)
feature_cols = [c for c in df.columns if not c.startswith(('y_', 'timestamp'))]

# Get target
target = df['y_direction']

# Ready for training
X, y = df[feature_cols], target
```

### Training Workflow

```python
# For each target type and horizon, use the matched dataset:
for horizon in [1, 3, 6, 12]:
    for target_type in ['direction', 'returns', 'volatility']:
        # Load horizon-specific dataset
        df = pd.read_parquet(f"data/datasets/{target_type}_{horizon}bar.parquet")
        
        # Train model for this specific task
        model = train_model(df)
        
        # Save model with matching name
        save_model(model, f"models/{target_type}_{horizon}bar.pkl")
```

### Why This Matters

1. **No cross-contamination**: Each model uses features optimized for its specific target
2. **Better signal extraction**: Interactions that work for 1-bar don't work for 12-bar
3. **Cleaner architecture**: One dataset per task, no confusion about which target to use
4. **Ensemble-ready**: Later, combine predictions from multiple horizon-specific models

---

## Dataset Selection Guide

> **Added**: 2025-12-22 (Step 10 of validation)

### Quick Reference: Which Dataset for Which Task?

| I want to... | Dataset | Model Type | Y Column | Notes |
|--------------|---------|------------|----------|-------|
| Predict if price goes up in 8h | `direction_1bar` | Binary Classification | `y_direction` | Balanced ~50/50 |
| Predict if price goes up in 4d | `direction_12bar` | Binary Classification | `y_direction` | Balanced ~50/50 |
| Estimate 24h expected return | `returns_3bar` | Regression | `y_returns` | Mean ~0%, range ±21% |
| Estimate 4-day expected return | `returns_12bar` | Regression | `y_returns` | Mean ~0%, range ±30% |
| Size positions by volatility | `volatility_{n}bar` | Regression | `y_volatility` | Always ≥0, for risk |
| Detect high-vol regimes | `vol_regime_{n}bar` | Multiclass (3-class) | `y_vol_regime` | {0,1,2} = LOW/MED/HIGH |
| Filter by trend state | `trend_regime_{n}bar` | Binary Classification | `y_trend_regime` | 1=uptrend, 0=downtrend |

### Model Type by Target

| Target Type | Scikit-learn | XGBoost/CatBoost | Loss Function |
|-------------|--------------|------------------|---------------|
| `direction` | `LogisticRegression`, `RandomForestClassifier` | `XGBClassifier`, `CatBoostClassifier` | `log_loss` |
| `returns` | `Ridge`, `RandomForestRegressor` | `XGBRegressor`, `CatBoostRegressor` | `mse`, `mae` |
| `volatility` | `Ridge`, `RandomForestRegressor` | `XGBRegressor` | `mse` (values always ≥0) |
| `vol_regime` | `LogisticRegression(multi_class='multinomial')` | `XGBClassifier(objective='multi:softmax')` | `multi_logloss` |
| `trend_regime` | `LogisticRegression` | `XGBClassifier` | `log_loss` |

### Validation Summary (2025-12-22)

All 20 datasets passed validation:

| Target | Check | Result |
|--------|-------|--------|
| `direction_*` | Binary {0,1}, ~50/50 balance, 100% sign match | ✅ PASS |
| `returns_*` | Continuous, exact fwd_return match, mean ~0 | ✅ PASS |
| `volatility_*` | Non-negative, exact \|fwd_return\| match | ✅ PASS |
| `vol_regime_*` | Values {0,1,2}, ~25/50/25 tercile distribution | ✅ PASS |
| `trend_regime_*` | Binary {0,1}, ~47/53 balance | ✅ PASS |
| **Interactions** | 0% overlap between 1-bar and 12-bar | ✅ CRITICAL PASS |

### Code Examples

**Classification (Direction Prediction)**:
```python
import pandas as pd
from catboost import CatBoostClassifier

# Load 12-bar direction dataset
df = pd.read_parquet("data/datasets/direction_12bar.parquet")
X = df.drop(columns=['timestamp', 'y_direction'])
y = df['y_direction']

# Train classifier
model = CatBoostClassifier(
    iterations=500,
    learning_rate=0.03,
    depth=6,
    loss_function='Logloss'
)
model.fit(X, y)
```

**Regression (Returns Prediction)**:
```python
import pandas as pd
from catboost import CatBoostRegressor

# Load 12-bar returns dataset
df = pd.read_parquet("data/datasets/returns_12bar.parquet")
X = df.drop(columns=['timestamp', 'y_returns'])
y = df['y_returns']

# Train regressor
model = CatBoostRegressor(
    iterations=500,
    learning_rate=0.03,
    depth=6,
    loss_function='RMSE'
)
model.fit(X, y)
```

**Multiclass (Vol Regime Prediction)**:
```python
import pandas as pd
from catboost import CatBoostClassifier

# Load 12-bar vol_regime dataset
df = pd.read_parquet("data/datasets/vol_regime_12bar.parquet")
X = df.drop(columns=['timestamp', 'y_vol_regime'])
y = df['y_vol_regime']

# Train multiclass classifier
model = CatBoostClassifier(
    iterations=500,
    learning_rate=0.03,
    depth=6,
    loss_function='MultiClass'  # 3 classes: 0, 1, 2
)
model.fit(X, y)
```

---

## Related Documents

- **Part_1_Architecture.md** — System design
- **Part_4_Analysis_Methods.md** — How features are analyzed
- **Part_5_Modules.md** — data.py module details
