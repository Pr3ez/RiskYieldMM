# L2 Prediction Pipeline: Complete Flow Documentation

This document describes how models make predictions from start to end in the L2 backtest system.

---

## Overview: The Two-Layer Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           DATA FLOW OVERVIEW                                     │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  [Raw OHLCV Data] ──► [Feature Engineering] ──► [L1 Precompute] ──► [Assembly]  │
│                                                           │                      │
│                                                           ▼                      │
│                                                   [assembled.parquet]            │
│                                                           │                      │
│                                                           ▼                      │
│                                                  [L2 Walk-Forward]               │
│                                                           │                      │
│                                                           ▼                      │
│                                                   [Predictions]                  │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Stage 1: L1 Precomputation (Run Once)

**File:** `scripts/target_models/validation/l1_precompute.py`

### Purpose
Transform raw features into "helper features" using unsupervised statistical models.
This is computationally expensive (~1 hour per config) but only needs to run once.

### Process for Each Walk-Forward Iteration

```
For iteration i with prediction timestamp T:

┌─────────────────────────────────────────────────────────────────┐
│ L1 WINDOW                                                        │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│   [───── L1.train ─────][── L1.val ──]                          │
│         (unsupervised)   (IC boosting)                          │
│                                                                  │
│                          ▼                                       │
│                                                                  │
│   ensemble.fit(X_l1_train)      # Fit HMM, GARCH, Kalman, etc.  │
│   ensemble.optimize(X_l1_val, y_l1_val)  # Target-aware tuning  │
│                                                                  │
│                          ▼                                       │
│                                                                  │
│   ensemble.transform(X_l2_full) # Generate helper features       │
│                                                                  │
│   → Save to: 2025-10-13_08h.parquet                             │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Helper Models (L1 Ensemble)

| Helper | Features Generated | Purpose |
|--------|-------------------|---------|
| HMM-4 | 9 features | Hidden Markov regime detection |
| HMM-5 | 10 features | 5-state regime detection |
| GARCH | 8 features | Volatility modeling |
| EGARCH | 8 features | Asymmetric volatility |
| Kalman | 7 features | Trend/velocity extraction |
| CUSUM | 12 features | Changepoint detection |
| OU | 8 features | Mean reversion signals |
| EVT | 10 features | Tail risk (GPD) |
| BOCPD | 7 features | Bayesian changepoint |
| IsolationForest | 1 feature | Anomaly scores |
| **Total** | **~91 features** | |

### Output Structure
```
data/precomputed/{config_name}/
├── 2025-10-13_00h.parquet    # Helper features for pred at 00:00 UTC
├── 2025-10-13_08h.parquet    # Helper features for pred at 08:00 UTC
├── 2025-10-13_16h.parquet    # Helper features for pred at 16:00 UTC
├── index.json                 # timestamp → metadata mapping
└── metadata.json              # Precomputation summary
```

---

## Stage 2: Dataset Assembly

**File:** `scripts/target_models/validation/dataset_assembly.py`

### Purpose
Combine all per-iteration parquet files into one continuous dataset for efficient loading.

### Process
```
For each config (e.g., "direction_1bar"):

1. Scan all iteration files: data/precomputed/direction_1bar/*.parquet
2. From each file, extract ONLY the prediction row (last row)
3. Add pred_idx column to track original position
4. Concatenate all rows → assembled.parquet

Result: 
  - 69,074 rows (one per prediction point)
  - 92 columns (91 helper features + pred_idx)
```

### Output
```
data/precomputed/{config}/assembled.parquet
```

---

## Stage 3: L2 Walk-Forward Backtest

**File:** `scripts/target_models/validation/l2_backtest_sync.py`

This is where the actual prediction happens.

### Configuration

```python
@dataclass
class SyncBacktestConfig:
    train_window: int = 500      # Total window size
    step_size: int = 1           # Move 1 bar per iteration
    
    # Split ratios within window
    train_ratio: float = 0.55    # 275 bars for training
    val_ratio: float = 0.15      # 75 bars (not used in L2)
    cal_ratio: float = 0.30      # 150 bars for conformal calibration
    
    # Ensemble weights
    cb_weight: float = 0.4       # CatBoost
    lgb_weight: float = 0.4      # LightGBM
    # linear_weight = 0.2        # Ridge/Logistic (auto-computed)
```

### Walk-Forward Window Structure

```
For prediction at position P:

                    ◄──────────── train_window (500) ────────────►
Position:   P-500                                              P-1    P (predict)
            │                                                   │     │
            ▼                                                   ▼     ▼
Data:       ├────────────────────┬────────────────┬────────────┤     ●
            │                    │                │            │
            │    train (55%)     │    val (15%)   │  cal (30%) │
            │    275 bars        │    75 bars     │  150 bars  │
            │                    │                │            │
            │  Models trained    │   (unused)     │ Conformal  │
            │  on this data      │                │ calibration│
            │                    │                │            │
            └────────────────────┴────────────────┴────────────┘

Then window slides forward by step_size (1 bar) for next iteration.
```

### Data Loading

```python
def _load_config_data(config_name: str, config: SyncBacktestConfig) -> ConfigData:
    """Load and prepare data for a single config."""
    
    # 1. Load assembled L1 features (91 helper features)
    X_assembled = load_assembled(config_name)  # From dataset_assembly.py
    pred_idx = X_assembled["pred_idx"].values
    X_features = X_assembled.drop(columns=["pred_idx"])
    
    # 2. Clip extreme duration features (prevent numerical issues)
    X_features = _clip_features(X_features, duration_max=1000.0)
    
    # 3. Load target data (y values)
    _, y_full, _ = load_target_data(target, horizon, ...)
    
    # 4. Align targets with features using pred_idx + horizon offset
    y_aligned = []
    for idx in pred_idx:
        aligned_idx = int(idx) + horizon - 1  # Horizon-aligned
        y_aligned.append(y_full.iloc[aligned_idx])
    
    return ConfigData(X_features, y_target, ...)
```

---

## Stage 4: Model Training and Prediction

### For Classification Tasks (direction, vol_regime, trend_regime)

**File:** `l2_backtest_sync.py`, function `_train_predict_classification()`

```python
def _train_predict_classification(...):
    # 1. Check if enough classes in training data
    unique_classes = np.unique(y_train)
    if len(unique_classes) < 2:
        # Early exit: return majority class prediction
        return majority_class, None, None, {...}
    
    # 2. Determine binary vs multiclass from config (not data!)
    is_binary = n_classes == 2  # Only direction_* is binary
    
    # 3. Initialize 3 models
    
    # CatBoost (GPU)
    cb_model = CatBoostClassifier(
        iterations=100,
        depth=6,
        learning_rate=0.03,
        task_type="GPU",
        loss_function="Logloss" if is_binary else "MultiClass",
    )
    
    # LightGBM (GPU)
    lgb_model = LGBMClassifier(
        n_estimators=100,
        max_depth=6,
        learning_rate=0.03,
        device="gpu",
        objective="binary" if is_binary else "multiclass",
    )
    
    # Linear (CPU regularizer)
    linear_model = LogisticRegression(max_iter=1000)
    
    # 4. Train all models on same training data
    cb_model.fit(X_train, y_train)
    lgb_model.fit(X_train, y_train)
    linear_model.fit(X_train, y_train)
    
    # 5. Get probability predictions
    if is_binary:
        cb_prob = cb_model.predict_proba(X_pred)[0, 1]    # P(class=1)
        lgb_prob = lgb_model.predict_proba(X_pred)[0, 1]
        linear_prob = linear_model.predict_proba(X_pred)[0, 1]
        
        # 6. Weighted ensemble
        ensemble_prob = 0.4 * cb_prob + 0.4 * lgb_prob + 0.2 * linear_prob
        y_pred = int(ensemble_prob > 0.5)
    else:
        # Multiclass: combine probability vectors
        cb_probs = cb_model.predict_proba(X_pred)[0]
        lgb_probs = lgb_model.predict_proba(X_pred)[0]
        linear_probs = linear_model.predict_proba(X_pred)[0]
        
        ensemble_probs = 0.4 * cb_probs + 0.4 * lgb_probs + 0.2 * linear_probs
        y_pred = int(np.argmax(ensemble_probs))
    
    # 7. Conformal prediction set (uncertainty quantification)
    # ... (see Conformal Prediction section below)
    
    return y_pred, y_prob, prediction_set, components
```

### For Regression Tasks (returns, volatility)

**File:** `l2_backtest_sync.py`, function `_train_predict_regression()`

```python
def _train_predict_regression(...):
    # 1. Initialize 3 models
    
    # CatBoost (GPU)
    cb_model = CatBoostRegressor(
        iterations=100,
        depth=6,
        learning_rate=0.03,
        task_type="GPU",
        loss_function="RMSE",
    )
    
    # LightGBM (GPU)
    lgb_model = LGBMRegressor(
        n_estimators=100,
        max_depth=6,
        learning_rate=0.03,
        device="gpu",
    )
    
    # Linear (CPU regularizer)
    linear_model = Ridge(alpha=1.0)
    
    # 2. Train all models
    cb_model.fit(X_train, y_train)
    lgb_model.fit(X_train, y_train)
    linear_model.fit(X_train, y_train)
    
    # 3. Get point predictions
    cb_pred = cb_model.predict(X_pred)[0]
    lgb_pred = lgb_model.predict(X_pred)[0]
    linear_pred = linear_model.predict(X_pred)[0]
    
    # 4. Weighted ensemble
    y_pred_raw = 0.4 * cb_pred + 0.4 * lgb_pred + 0.2 * linear_pred
    
    # 5. CRITICAL: Clip predictions to prevent explosions
    # Use ONLY training statistics (no future leakage!)
    y_train_mean = float(y_train.mean())
    y_train_std = float(y_train.std())
    clip_lower = y_train_mean - 5.0 * y_train_std
    clip_upper = y_train_mean + 5.0 * y_train_std
    y_pred = np.clip(y_pred_raw, clip_lower, clip_upper)
    
    # 6. Conformal interval
    # ... (see Conformal Prediction section below)
    
    return y_pred, interval, covered, components
```

---

## Stage 5: Conformal Prediction (Uncertainty Quantification)

### For Classification: Conformal Prediction Sets

```python
# Calibration: compute non-conformity scores on held-out cal set
cal_probs = model.predict_proba(X_cal)
scores = 1 - cal_probs[np.arange(len(y_cal)), y_cal]  # 1 - prob of true class

# Compute threshold at (1-alpha) quantile
threshold = np.quantile(scores, 1 - alpha)  # e.g., alpha=0.1 → 90% coverage

# For new prediction
prediction_set = (1 - y_prob) <= threshold  # Boolean array of plausible classes
```

**Result:** A set of classes with 90% guaranteed coverage.

### For Regression: Conformal Intervals

```python
# Calibration: compute absolute residuals on cal set
cal_preds = model.predict(X_cal)
residuals = np.abs(y_cal - cal_preds)

# Compute width at (1-alpha) quantile
width = np.quantile(residuals, 1 - alpha)  # e.g., 90th percentile of |error|

# For new prediction
interval = (y_pred - width, y_pred + width)
covered = interval[0] <= y_true <= interval[1]
```

**Result:** An interval [lower, upper] with 90% guaranteed coverage.

---

## Stage 6: Metrics Computation

### Classification Metrics

| Metric | Computation | Interpretation |
|--------|-------------|----------------|
| Accuracy | `accuracy_score(y_true, y_pred)` | % correct predictions |
| AUC | `roc_auc_score(y_true, y_prob)` | Ranking quality (binary only) |
| Precision | `precision_score(...)` | TP / (TP + FP) |
| Recall | `recall_score(...)` | TP / (TP + FN) |
| F1 | `f1_score(...)` | Harmonic mean of P & R |
| Coverage | Mean of `covered` flags | Conformal coverage |

### Regression Metrics

| Metric | Computation | Interpretation |
|--------|-------------|----------------|
| IC | `spearmanr(y_true, y_pred)` | Rank correlation |
| RMSE | `sqrt(mean((y_true - y_pred)^2))` | Error magnitude |
| MAE | `mean(abs(y_true - y_pred))` | Average absolute error |
| Coverage | Mean of `covered` flags | Conformal interval coverage |

**IMPORTANT:** All metrics are **cumulative** - they use ALL predictions from step 1 onward.

---

## Complete Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        COMPLETE PREDICTION PIPELINE                              │
└─────────────────────────────────────────────────────────────────────────────────┘

  ┌──────────────────────────────────────────────────────────────────────────────┐
  │ STAGE 1: L1 PRECOMPUTATION (Run Once, ~1 hour per config)                    │
  ├──────────────────────────────────────────────────────────────────────────────┤
  │                                                                               │
  │   Raw Features (X)         L1 Helpers               Output                   │
  │   ┌─────────────┐         ┌───────────┐          ┌──────────────┐            │
  │   │ price       │         │ HMM       │          │ 2025-01-01_  │            │
  │   │ volume      │   ───►  │ GARCH     │   ───►   │   00h.parquet│            │
  │   │ returns     │         │ Kalman    │          │ 91 features  │            │
  │   │ volatility  │         │ CUSUM     │          │              │            │
  │   │ ...         │         │ OU/EVT    │          └──────────────┘            │
  │   └─────────────┘         │ BOCPD     │                                       │
  │                           └───────────┘                                       │
  └──────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
  ┌──────────────────────────────────────────────────────────────────────────────┐
  │ STAGE 2: ASSEMBLY (Combine per-iteration files)                              │
  ├──────────────────────────────────────────────────────────────────────────────┤
  │                                                                               │
  │   Per-iteration files                    Assembled dataset                   │
  │   ┌─────────────────┐                   ┌────────────────────────────────┐   │
  │   │ 2025-01-01_00h  │                   │ assembled.parquet              │   │
  │   │ 2025-01-01_08h  │   ───►            │                                │   │
  │   │ 2025-01-01_16h  │   extract         │ 69,074 rows × 92 columns       │   │
  │   │ ...             │   pred rows       │ (one row per prediction point) │   │
  │   │ 2025-12-31_16h  │                   │                                │   │
  │   └─────────────────┘                   └────────────────────────────────┘   │
  └──────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
  ┌──────────────────────────────────────────────────────────────────────────────┐
  │ STAGE 3-6: L2 WALK-FORWARD (For each step)                                   │
  ├──────────────────────────────────────────────────────────────────────────────┤
  │                                                                               │
  │   For step i at position P:                                                  │
  │                                                                               │
  │   ┌─────────────────────────────────────────────────────────────────────┐   │
  │   │            ◄───────── Window (500 bars) ──────────►                 │   │
  │   │                                                                      │   │
  │   │   [train: 275 bars]     [val: 75]    [cal: 150 bars]    [predict]   │   │
  │   │          │                             │                    │        │   │
  │   │          ▼                             ▼                    ▼        │   │
  │   │   ┌───────────────┐           ┌─────────────┐      ┌────────────┐   │   │
  │   │   │ CatBoost.fit()│           │ Conformal   │      │ y_pred =   │   │   │
  │   │   │ LightGBM.fit()│           │ calibration │      │ 0.4*CB +   │   │   │
  │   │   │ Ridge.fit()   │           │ (90% cover) │      │ 0.4*LGB +  │   │   │
  │   │   └───────────────┘           └─────────────┘      │ 0.2*Lin    │   │   │
  │   │                                                     └────────────┘   │   │
  │   └─────────────────────────────────────────────────────────────────────┘   │
  │                                                                               │
  │   Output per step:                                                           │
  │   ┌──────────────────────────────────────────────────────────────────────┐  │
  │   │ {                                                                     │  │
  │   │   "y_pred": 1,                    # Ensemble prediction               │  │
  │   │   "y_true": 0,                    # Actual value                      │  │
  │   │   "y_prob": 0.62,                 # Probability (binary class)        │  │
  │   │   "cb_pred": 1, "cb_prob": 0.65,  # CatBoost individual               │  │
  │   │   "lgb_pred": 1, "lgb_prob": 0.58, # LightGBM individual              │  │
  │   │   "linear_pred": 0, "linear_prob": 0.48, # Linear individual          │  │
  │   │   "covered": True,                # Conformal coverage                │  │
  │   │   "interval_width": 0.05,         # Regression only                   │  │
  │   │ }                                                                     │  │
  │   └──────────────────────────────────────────────────────────────────────┘  │
  └──────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
  ┌──────────────────────────────────────────────────────────────────────────────┐
  │ FINAL OUTPUT: Cumulative Metrics                                             │
  ├──────────────────────────────────────────────────────────────────────────────┤
  │                                                                               │
  │   Classification:                          Regression:                       │
  │   ┌────────────────────────────┐          ┌─────────────────────────────┐   │
  │   │ Accuracy: 52.3%            │          │ IC: 0.08                    │   │
  │   │ AUC: 0.56                  │          │ RMSE: 0.028                 │   │
  │   │ Precision: 0.51            │          │ MAE: 0.019                  │   │
  │   │ Recall: 0.54               │          │ Coverage: 89%               │   │
  │   │ Coverage: 94%              │          │                             │   │
  │   └────────────────────────────┘          └─────────────────────────────┘   │
  │                                                                               │
  │   NOTE: Metrics are cumulative (all predictions from step 1 to current)     │
  │         Early steps have high variance due to small N                        │
  └──────────────────────────────────────────────────────────────────────────────┘
```

---

## Key Design Decisions

### 1. Why Two Layers?

**L1 (Helper Features):** Unsupervised, expensive, target-agnostic
- HMM, GARCH, etc. don't need target y for fitting
- Can be precomputed once and reused
- Same features work for all targets

**L2 (Supervised Models):** Supervised, fast, target-specific
- CatBoost/LightGBM/Ridge need target y
- Must retrain each step (walk-forward)
- Different models per target type

### 2. Why 3-Model Ensemble?

| Model | Strengths | Role |
|-------|-----------|------|
| CatBoost | GPU-fast, handles categoricals | Primary predictor |
| LightGBM | GPU-fast, good on tabular | Secondary predictor |
| Ridge/LogReg | Fast, regularized, stable | Stabilizer |

Ensemble reduces variance and provides more robust predictions.

### 3. Why Conformal Prediction?

- **Distribution-free:** No assumptions about data distribution
- **Finite-sample guarantee:** 90% coverage is guaranteed, not asymptotic
- **Calibration set:** Uses recent data, adapts to regime changes

### 4. Why Cumulative Metrics?

Early iterations have few samples (N=3, N=10) → metrics are noisy.
Cumulative metrics stabilize over time, showing true model performance.

**Implication:** Don't trust early accuracy (73% at N=19). Wait for N>100 for reliable estimates.

---

## Troubleshooting Guide

### Issue: Accuracy drops from 70% to 50%

**Not a bug!** This is expected:
- Early high accuracy (N<20) is statistical noise
- True performance (~52%) emerges with more samples
- Direction prediction is inherently difficult (markets are efficient)

### Issue: RMSE explodes to 1000+

**Cause:** Unbounded predictions from models
**Fix:** Prediction clipping using training statistics (±5σ)

### Issue: Coverage below 90%

**Cause:** Heteroscedasticity (error varies with conditions)
**Fix:** Conformalized Quantile Regression (CQR) for adaptive intervals

### Issue: Model skips iterations

**Cause:** Single class in training window
**Fix:** Return majority class prediction with `models_trained=False` flag

---

## File Reference

| File | Purpose |
|------|---------|
| `l1_precompute.py` | Precompute L1 helper features |
| `dataset_assembly.py` | Assemble per-iteration files |
| `l2_backtest_sync.py` | Run walk-forward backtest |
| `registry.py` | Load target data (y values) |
| `helpers/*.py` | Individual L1 helper implementations |

---

*Document generated: 2026-01-11*
*System: RiskYieldMM L2 Backtest Pipeline*
