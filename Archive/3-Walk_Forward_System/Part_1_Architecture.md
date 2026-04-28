# Part 1: Walk-Forward Architecture

## 4-Window Layout

The Walk-Forward system uses a **4-window sliding architecture** that maintains strict temporal separation to prevent look-ahead bias.

```
Time →
├────────────────────────┬──────────┬──────────┬──────┐
│         TRAIN          │   CAL    │   VAL    │ PRED │
│    (Fit Models)        │(Calibr.) │(Early S.)│(Apply)│
├────────────────────────┴──────────┴──────────┴──────┤
│                                                      │
│  Each iteration: Windows slide forward by 1 day     │
│                                                      │
└──────────────────────────────────────────────────────┘
```

### Window Purposes

| Window | Size (typical) | Purpose | Data Usage |
|--------|---------------|---------|------------|
| **TRAIN** | 1000 days | Fit CatBoost + LightGBM | Features → Target |
| **CAL** | 150 days | Probability calibration | Calibrate raw probs |
| **VAL** | 200 days | Early stopping, threshold calc | Validation metrics |
| **PRED** | 1 day | Generate prediction | Apply ensemble |

### Window Size Formulas

```python
# Automatic window sizing (when USE_AUTOMATIC_WINDOWS=True)
# Based on data diagnostics: M=memory, R=regime, S=seasonality, V=vol cycle, p=pos rate

W_train = max(3*M, 1.5*R, 2*S, 2*V, 180)
W_cal = max(200/p, V, 30)    # Ensures enough positive samples for calibration
W_val = max(V, S, 30, MIN_VAL_WINDOW)
W_pred = 1                   # Single-day prediction
```

### Example Window Boundaries

```
Iteration 100 (pred_start = 1450):
├─ TRAIN: [0:1000]      rows 0-999
├─ CAL:   [1000:1150]   rows 1000-1149
├─ VAL:   [1150:1350]   rows 1150-1349
└─ PRED:  [1350:1351]   row 1350

Iteration 101 (pred_start = 1451):
├─ TRAIN: [1:1001]      rows 1-1000 (slid +1)
├─ CAL:   [1001:1151]   rows 1001-1150
├─ VAL:   [1151:1351]   rows 1151-1350
└─ PRED:  [1351:1352]   row 1351
```

## Data Flow Per Iteration

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ITERATION DATA FLOW                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  STEP 0: Pre-iteration                                                       │
│  ├─ Read regime state from features (no look-ahead)                         │
│  ├─ Adaptive window sizing if enabled                                       │
│  └─ Lagged evaluation of previous prediction (live mode)                    │
│                                                                              │
│  STEP 1-2: Feature Engineering (on TRAIN only)                              │
│  ├─ Signal aggregator fitted on TRAIN window                                │
│  ├─ Feature selection (if enabled)                                          │
│  └─ Compute sample weights (half-life)                                      │
│                                                                              │
│  STEP 3-4: Model Training                                                    │
│  ├─ CatBoost: fit on TRAIN, early_stop on VAL                              │
│  ├─ LightGBM: fit on TRAIN, early_stop on VAL                              │
│  └─ Generate raw probabilities for all windows                              │
│                                                                              │
│  STEP 5-6: Calibration                                                       │
│  ├─ Platt/Isotonic calibrator fitted on CAL window                          │
│  ├─ Per-model calibration (CB, LGB separately)                              │
│  └─ Rolling calibration buffer updated                                      │
│                                                                              │
│  STEP 7: Meta-Stacking                                                       │
│  ├─ RandomForest meta-stacker trained on VAL                                │
│  ├─ Combines calibrated CB + LGB probabilities                              │
│  └─ Model diversity metrics computed                                        │
│                                                                              │
│  STEP 8: Threshold Calculation                                               │
│  ├─ Quantile matching / Youden J / Class balanced                           │
│  ├─ AUC confidence adjustment                                               │
│  ├─ Regime-specific adjustments                                             │
│  └─ Risk gate / Bullish gate                                                │
│                                                                              │
│  STEP 9: Position Sizing                                                     │
│  ├─ V3 Pipeline: Gate → Ratio → Alignment → Vol → Position                  │
│  ├─ Hull scorers updated                                                    │
│  └─ Config-specific predictions generated                                   │
│                                                                              │
│  STEP 10: Multi-Config Tracking                                              │
│  ├─ 48+ configs evaluated in parallel                                       │
│  ├─ Config scorer updated with TP/FP                                        │
│  └─ Best config selected for next iteration                                 │
│                                                                              │
│  STEP 11: Output & Advance                                                   │
│  ├─ Store prediction record                                                 │
│  ├─ Update rolling buffers                                                  │
│  └─ pred_start += 1 (slide windows)                                         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Temporal Safeguards

### 1. Strict Window Separation

```python
# Windows are computed from pred_start BACKWARDS
pred_end = pred_start + WF_PRED
val_end = pred_start
val_start = val_end - WF_VAL
cal_end = val_start
cal_start = cal_end - WF_CAL
train_end = cal_start
train_start = max(0, train_end - WF_TRAIN)

# This ensures: TRAIN < CAL < VAL < PRED in time
```

### 2. Lagged Target for Production

```python
# In production, we don't know today's outcome - only yesterday's
# lagged_direction_target = direction_target from previous day

if 'lagged_forward_returns' in source_df.columns:
    source_df[LAGGED_DIRECTION_TARGET] = (
        source_df['lagged_forward_returns'] > 0
    ).astype(int)
```

### 3. Per-Iteration Feature Engineering

```python
# Signal aggregator is fitted ONLY on TRAIN each iteration
# Never sees VAL, CAL, or PRED data during fitting

if USE_SIGNAL_AGGREGATION and iteration == 1:
    # First iteration: fit aggregator on train
    signal_aggregator.fit(train_df[signal_candidate_cols])
```

### 4. Rolling Calibration Buffers

```python
# Calibration buffers accumulate PAST CAL windows only
# Never includes current or future data

class RollingCalBuffer:
    def __init__(self, max_windows=10, max_samples=2000):
        self.buffer = deque(maxlen=max_windows)
    
    def append(self, probs, labels):
        # Appends AFTER current iteration's calibration
        self.buffer.append((probs, labels))
```

## Window Size Diagnostics

The system can automatically compute window sizes from data characteristics:

```python
from window_diagnostics import compute_diagnostics

diagnostics = compute_diagnostics(
    df,
    returns_col='lagged_forward_returns',
    vol_col='volatility_target',
    label_col='direction_target',
    min_val_window=MIN_VAL_WINDOW,
)

# Returns:
# M_memory_days: Autocorrelation memory
# R_days_since_break: Days since last regime break
# S_seasonality_days: Seasonality cycle length
# V_vol_cycle_days: Volatility cycle length
# p_positive_rate: Positive class rate
# W_train: Recommended train window
# W_val: Recommended val window
# calibration_method: 'platt' or 'isotonic' based on samples
```

## Adaptive Per-Iteration Windows

When `USE_ADAPTIVE_WINDOWS_PER_ITERATION=True`:

```python
# Recalculate CAL window based on LOCAL positive rate
lookback_start = max(0, pred_start - ADAPTIVE_LOOKBACK_FOR_P)
local_slice = source_df.iloc[lookback_start:pred_start]
local_p = float((local_slice[DIRECTION_TARGET] == 1).mean())

# More samples needed when p is extreme
local_WF_CAL = max(MIN_CAL_WINDOW, int(np.ceil(200 / max(0.1, local_p))), 30)
local_WF_CAL = min(local_WF_CAL, 500)  # Cap to prevent excessive size

# Adaptive half-life based on regime stability
p_deviation = abs(local_p - historical_p)
if p_deviation > 0.08:
    # Regime shift → shorter half-life
    adaptive_half_life = MIN_ADAPTIVE_HALF_LIFE
```

## Regime-Aware Train Window Sizing

When `USE_REGIME_AWARE_TRAIN_SIZING=True`:

```python
# Check if proposed TRAIN window has compatible regime
train_regimes = source_df['hmm_regime'].iloc[train_start:train_end]
regime_purity = float((train_regimes == current_hmm_regime).mean())

pos_rate_deviation = abs(train_pos_rate - current_regime_pos_rate)

should_shrink = (
    pos_rate_deviation > REGIME_P_MISMATCH_THRESHOLD or
    regime_purity < REGIME_PURITY_THRESHOLD or
    transitions_5d >= INSTABILITY_TRANSITION_THRESHOLD or
    days_since_cp < WF_TRAIN * 0.3
)

if should_shrink:
    # Shrink train to only current regime data
    adjusted_train_size = min(int(regime_duration * 0.9), WF_TRAIN)
    adjusted_train_size = max(adjusted_train_size, MIN_TRAIN_WINDOW_ADAPTIVE)
```

---

*See [Part_2_Models.md](Part_2_Models.md) for model training details.*
