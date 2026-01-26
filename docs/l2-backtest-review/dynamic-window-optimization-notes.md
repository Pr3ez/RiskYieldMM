# Dynamic Window Optimization - Implementation Notes

**Date:** 2026-01-21  
**Status:** ✅ OPERATIONAL - See audit results below

---

## ✅ AUDIT RESULTS (Jan 21, 2026)

### Fixed Issues:
1. **✅ Constant 800/1000 buffer** - Changed fallback from 800 to 1000 to match max possible window (Linear with horizon multiplier). This is intentional - extracts enough data for any model's optimization.
2. **✅ Linear REGIME/VOL_REG no-op adjustments** - Removed misleading `max(window, 800)` calls that printed fake adjustments. Now shows accurate logging.
3. **✅ Splits verified** - `extract_per_model_splits()` correctly slices INSIDE the dynamically optimized window per model.

### Leakage Audit:
- **vol_regime thresholds:** SAFE - uses warmup period (first 1000 samples) only
- **Feature selection:** SAFE - uses train split only  
- **Conformal calibration:** SAFE - uses cal split only (after train/val)
- **Optimizer characterization:** SAFE - uses X_full, y_full (historical window only)

### Verification:
- 5-step test passed with all 7 configs × 4 models = 28 combinations
- All models train successfully with dynamic window optimization
- Logs show accurate adjustments per model

---

## Overview

Dynamic window optimization is **fully operational**. Each model optimizes its window 
size and splits based on data characteristics at each prediction step.

---

## How It Works (Per-Step Flow)

```
For each prediction step:
  │
  └─► training.py: train_predict_classification_permodel()
        │
        ├─► optimize_catboost_config(X_full, y_full, target_name, ...)
        │     └─► characterize_data() → Stage 1
        │     └─► generate_candidate_configs() → Stage 2
        │     └─► validate_configs_on_holdout() → Stage 3
        │     └─► Optuna refinement → Stage 4 (if enabled)
        │
        ├─► optimize_lightgbm_config(X_full, y_full, target_name, ...)
        │     └─► characterize_data() (reused from catboost_model.py)
        │     └─► Rule-based adjustments
        │
        ├─► optimize_lstm_config(X_full, y_full, target_name, ...)
        │     └─► characterize_data() (reused)
        │     └─► Rule-based adjustments + seq_len tuning
        │
        └─► optimize_linear_config(X_full, y_full, target_name, ...)
              └─► characterize_data() (reused)
              └─► Rule-based adjustments
```

---

## Data Characterization (Stage 1 - Shared)

All models use `characterize_data()` from `catboost_model.py`:

```python
@dataclass
class DataCharacteristics:
    # Target
    task_type: str          # "classification" or "regression"
    n_classes: int | None
    class_balance: float | None       # Min class proportion (0-0.5)
    class_imbalance_ratio: float | None
    
    # Stationarity
    adf_pvalue: float       # ADF test p-value
    is_stationary: bool     # p < 0.05
    rolling_mean_drift: float
    
    # Volatility
    volatility_level: str   # "low", "medium", "high"
    volatility_ratio: float # Recent vol / baseline vol
    
    # Features
    n_features: int
    n_samples: int
```

**Volatility Classification:**
- `volatility_ratio > 1.3` → HIGH
- `volatility_ratio < 0.7` → LOW
- Otherwise → MEDIUM

---

## Per-Model Optimization Details

### CatBoost: 4-Stage Full Optimization

**File:** `models/catboost_model.py`

**Stages:**
1. `characterize_data()` - Analyze target + features
2. `generate_candidate_configs()` - Create 3-5 candidates based on:
   - Class balance
   - Stationarity/drift
   - Volatility regime
   - Target type (direction, volatility, regime, extreme)
   - Horizon multiplier
3. `validate_configs_on_holdout()` - Quick train/eval on holdout
4. Optuna refinement (`n_trials=25`, `timeout=60s`)

**Window Ranges:**
| Condition | Window | Notes |
|-----------|--------|-------|
| Baseline | 400 | |
| Imbalanced | 500 | class_balance < 0.20 |
| High vol | 350 | volatility_level == "high" |
| Low vol | 500 | volatility_level == "low" |
| Drift | 300 | rolling_mean_drift > 0.3 |
| Max | 700 | After horizon multiplier |

**Horizon Multiplier:** {1: 1.0, 3: 1.1, 6: 1.2, 12: 1.3}

---

### LightGBM: Rule-Based Optimization

**File:** `models/lightgbm_model.py`

**Function:** `optimize_lightgbm_config()`

**Logic:** Rule-based (no candidate generation/holdout validation)

**Window Ranges:**
| Condition | Window | Additional |
|-----------|--------|------------|
| Baseline | 400 | |
| High vol | 350 | reg_lambda=10, depth=5 |
| Low vol | 500 | reg_lambda=3, depth=7 |
| Non-stationary | 300 | lr=0.05 |
| Imbalanced | 450 | |
| Direction target | - | cal_ratio=0.25 |
| Volatility reg | 450 | |
| Regime target | 400 | |
| Extreme target | - | train_ratio=0.65 |
| Max | 700 | After horizon multiplier |

---

### LSTM: Rule-Based + Architecture Tuning

**File:** `models/lstm_model.py`

**Function:** `optimize_lstm_config()`

**LSTM-Specific:** Also adjusts `seq_len` and `hidden_size`

**Window Ranges:**
| Condition | Window | seq_len | Other |
|-----------|--------|---------|-------|
| Baseline | 600 | 20 | |
| High vol | 500 | 15 | dropout=0.3 |
| Low vol | 750 | 25 | dropout=0.15 |
| Non-stationary | 450 | 15 | |
| Imbalanced | 600 | - | train_ratio=0.75 |
| Direction | - | 20 | cal_ratio=0.2 |
| Volatility reg | 650 | 25 | |
| Regime | 550 | 20 | |
| Extreme | - | - | dropout=0.25 |
| Max | 900 | - | After horizon mult |

**Hidden Size by Features:**
- n_features > 100 → hidden_size=96
- n_features > 60 → hidden_size=64
- Otherwise → hidden_size=48

---

### Linear: Rule-Based (Longest Windows)

**File:** `models/linear_model.py`

**Function:** `optimize_linear_config()`

**Linear needs longest windows** (averaging reduces noise):

**Window Ranges:**
| Condition | Window | feat_ratio | Other |
|-----------|--------|------------|-------|
| Baseline | 800 | 0.50 | |
| High vol | 650 | 0.40 | |
| Low vol | 900 | 0.60 | |
| Non-stationary | 550 | 0.40 | val_ratio=0.25 |
| Imbalanced | 750 | - | |
| Direction | - | - | cal_ratio=0.3 |
| Volatility reg | 800 | - | |
| Regime | 700 | - | |
| Extreme | - | - | train_ratio=0.55 |
| Max | 1000 | - | After horizon mult |

---

## Embedding Calculation

**Formula:** `embargo = base_embargo (3) × horizon`, capped at 36

```python
def get_embargo_for_horizon(horizon: int, base_embargo: int = 3) -> int:
    embargo = base_embargo * horizon
    return min(embargo, 36)
```

| Horizon | Embargo |
|---------|---------|
| 1 bar | 3 |
| 3 bar | 9 |
| 6 bar | 18 |
| 12 bar | 36 (capped) |

---

## Key Files

| File | Purpose |
|------|---------|
| `services/training.py` | Calls all 4 optimize functions |
| `models/catboost_model.py` | 4-stage optimization + `characterize_data()` |
| `models/lightgbm_model.py` | Rule-based optimization |
| `models/lstm_model.py` | Rule-based + arch tuning |
| `models/linear_model.py` | Rule-based (longest windows) |

---

## Verification: Run Output

The backtest log shows optimization for each model at each step:

```
======================================================================
[DYNAMIC WINDOW] CatBoost | Target: direction | Horizon: 1
======================================================================
  📊 STAGE 1: Data Characteristics (n=800, features=266)
      Volatility: MEDIUM
      Stationary: True (ADF p=0.0000)
      Mean Drift: 0.089
      Class Balance: 0.269 (imbalance ratio: 1.65)
  🔧 STAGE 2: Generated 2 candidate configs
      [1] window=400, splits=60%/20%/20%
      [2] window=350, splits=55%/20%/25%
  🧪 STAGE 3: Holdout Validation (selecting best config)
      Selected: window=400
  ⚙️  STAGE 4: Hyperparameter Refinement (Optuna, n_trials=25)
  ✅ Final Config:
      train_window=400, splits=60%/20%/20%
      feature_selection_ratio=0.6
======================================================================
```

---

## What Was Different Before

| Model | Before | After |
|-------|--------|-------|
| CatBoost | Already had 4-stage | No change |
| LightGBM | Static 400 | Dynamic 350-700 |
| LSTM | Static 600 | Dynamic 450-900 |
| Linear | Static 800 | Dynamic 550-1000 |
