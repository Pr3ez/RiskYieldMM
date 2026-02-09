# Walk-Forward Prediction System Documentation

## Overview

`sliding_window_evidence_based56.py` (5,500+ lines) is a **production-ready Walk-Forward prediction system** for time-series ML trading. It implements a 4-window architecture with proper temporal safeguards to prevent look-ahead bias.

> **Prerequisites:** This system uses features from [Part 2: Kaggle Pipeline](../2-Kaggle_Pipeline/README.md). Read Part 2 first to understand the ~450 features that feed into these models.

## Pipeline Position

```
┌─────────────────────────────────────────────────────────────────────────────┐
│   Part 1: Feature Eng    Part 2: Features (Kaggle)     Part 3: THIS FOLDER  │
│   ═════════════════      ══════════════════════════    ═══════════════════  │
│   Naming conventions  →  ~450 features calculated   →  Model training      │
│   Raw data structure     RowByRow + HMM + DTMC         CatBoost + LightGBM │
│                          Kalman + GARCH                Calibration          │
│                                                        Position Sizing      │
└─────────────────────────────────────────────────────────────────────────────┘
```

**← Previous:** [Part 2: Features](../2-Kaggle_Pipeline/README.md) — Where the features come from

## Final Prediction Architecture

```
┌──────────────────────────────────────────────────────────────────────────────┐
│               WALK-FORWARD: COMPLETE PREDICTION FLOW                          │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  INPUT: ~450 features (from Part 2: Kaggle Pipeline)                         │
│      ↓                                                                        │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │           STEP 1: BASE MODEL TRAINING (TRAIN window)                     │ │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌───────────────────────┐   │ │
│  │  │   CatBoost      │  │   LightGBM      │  │   CatBoost Regressor  │   │ │
│  │  │  Direction (GPU)│  │  Direction      │  │   Volatility          │   │ │
│  │  │  P(return > 0)  │  │  P(return > 0)  │  │   |forward_returns|   │   │ │
│  │  └────────┬────────┘  └────────┬────────┘  └───────────┬───────────┘   │ │
│  └───────────┼────────────────────┼───────────────────────┼───────────────┘ │
│              │ raw_cb_prob        │ raw_lgb_prob          │ raw_vol_pred    │
│              ↓                    ↓                       ↓                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │          STEP 2: PLATT CALIBRATION (per-model, on CAL buffer)           │ │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌───────────────────────┐   │ │
│  │  │ Platt(CB) → LR  │  │ Platt(LGB) → LR │  │ Scale: median(actual) │   │ │
│  │  │ Rolling buffer  │  │ Rolling buffer  │  │       /median(pred)   │   │ │
│  │  └────────┬────────┘  └────────┬────────┘  └───────────┬───────────┘   │ │
│  └───────────┼────────────────────┼───────────────────────┼───────────────┘ │
│              │ cb_cal_prob        │ lgb_cal_prob          │ vol_calibrated  │
│              ↓                    ↓                       ↓                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │           STEP 3: META-STACKER (combines calibrated probs)              │ │
│  │                                                                          │ │
│  │   [cb_cal_prob, lgb_cal_prob] ──→ RandomForest Meta ──→ ensemble_prob   │ │
│  │         or simple averaging when meta buffer < min_samples              │ │
│  │                                                                          │ │
│  └────────────────────────────────────────┬────────────────────────────────┘ │
│                                           ↓                                   │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │       STEP 4: THRESHOLD & SIGNAL CLASSIFICATION                          │ │
│  │                                                                          │ │
│  │   signal = (ensemble_prob >= optimal_threshold) ? 1 : 0                 │ │
│  │   optimal_threshold = F1-optimal on rolling CAL buffer                  │ │
│  │   + regime-specific adjustments (high vol → more conservative)          │ │
│  │                                                                          │ │
│  └────────────────────────────────────────┬────────────────────────────────┘ │
│                                           ↓                                   │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │       STEP 5: POSITION SIZING V3 (6-step pipeline)                       │ │
│  │                                                                          │ │
│  │   1. Gate Check (prob >= threshold?)                                    │ │
│  │   2. Rolling EMA Ratio (recent TP/FP)                                   │ │
│  │   3. Config Alignment (Top10 agreement) + EMA scaling                   │ │
│  │   4. Volatility Adjustment (high vol → reduce)                          │ │
│  │   5. Leverage Rules (ratio >= 1.3, alignment >= 70%)                    │ │
│  │   6. Final Position ∈ [0.0, 2.0]                                        │ │
│  │                                                                          │ │
│  └────────────────────────────────────────┬────────────────────────────────┘ │
│                                           ↓                                   │
│  OUTPUT: position = direction_signal × position_size × leverage              │
│                                                                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Architecture Summary

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                    WALK-FORWARD 4-WINDOW ARCHITECTURE                        │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│   [TRAIN]  →  [CAL]  →  [VAL]  →  [PRED]                                     │
│      ↓          ↓         ↓         ↓                                        │
│   Fit CB    Calibrate  Early     Apply                                       │
│   Fit LGB   Platt/ISO  Stop      Threshold                                   │
│   Features  Meta-stack Meta      Position                                    │
│                                                                               │
│   Window Sizes (Automatic or Manual):                                        │
│   • TRAIN: max(3M, 1.5R, 2S, 2V, 180) ≈ 1000 days                           │
│   • CAL:   max(200/p, V, 30) ≈ 150 days                                      │
│   • VAL:   max(V, S, 30) ≈ 200 days                                          │
│   • PRED:  1 day (production prediction)                                     │
│                                                                               │
│   Where: M=memory, R=regime break, S=seasonality, V=vol cycle, p=pos rate   │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Deployment Modes

| Mode | Purpose | Usage |
|------|---------|-------|
| `backtest` | Full historical simulation | Optimization & analysis |
| `warmup` | Build state for live trading | Run last N iterations to prepare |
| `live` | Single prediction | Load checkpoint, predict, save |
| `auto` | Smart mode selection | Warmup if no checkpoint, else live |

```bash
# Set mode via environment variable
WF_DEPLOY_MODE=backtest python sliding_window_evidence_based56.py
WF_DEPLOY_MODE=live python sliding_window_evidence_based56.py
```

## Documentation Structure

| File | Description |
|------|-------------|
| [Part_1_Architecture.md](Part_1_Architecture.md) | 4-Window layout, data flow, temporal safeguards |
| [Part_2_Models.md](Part_2_Models.md) | CatBoost + LightGBM ensemble, meta-stacking |
| [Part_3_Calibration.md](Part_3_Calibration.md) | Platt scaling, isotonic regression, per-model calibration |
| [Part_4_Position_Sizing.md](Part_4_Position_Sizing.md) | V3 pipeline: Gate → Ratio → Alignment → Position |
| [Part_5_Config_Tracking.md](Part_5_Config_Tracking.md) | Multi-config parallel tracking, adaptive selection |
| [Part_6_Checkpoints.md](Part_6_Checkpoints.md) | State persistence, warmup/live transitions |
| [Part_7_Modules.md](Part_7_Modules.md) | Supporting module reference (wf_*.py) |

## Key Components

### 1. Direction Model Ensemble
Three base models trained separately, then combined:

```
┌─────────────────────────────────────────────────────────────────┐
│  BASE MODELS (all trained on TRAIN, validated on VAL)          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  CatBoost (GPU)           LightGBM                              │
│  ├─ Task: Classification  ├─ Task: Classification               │
│  ├─ Target: direction_target (return > 0)                       │
│  ├─ Features: ~200 selected (direction_feature_cols)            │
│  ├─ Optuna-tuned: depth, leaves, lr                             │
│  └─ Output: P(up) ∈ [0,1]                                       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2. Volatility Model
Separate CatBoostRegressor for expected volatility:

```python
# Target: |forward_returns| (absolute return magnitude)
# Features: volatility_feature_cols + dir_regime coupling
# dir_regime = (ensemble_direction_prob > 0.5)

volatility_model = CatBoostRegressor(**vol_params)
volatility_model.fit(
    X_train_vol_enhanced,  # Includes dir_regime
    y_train_vol,           # |forward_returns|
    sample_weight=train_sample_weights,  # Half-life weighting
)

# Calibration: scale factor from CAL residuals
cal_vol_scale = median(actual_vol) / median(pred_vol)
pred_vol_calibrated = pred_vol_raw * cal_vol_scale
```

### 3. Ensemble & Meta-Stacking
Calibrated probabilities combined via RF meta-stacker:

```python
# Per-model Platt calibration (on rolling CAL buffer)
cb_calibrator = LogisticRegression().fit(cb_cal_probs, y_cal)
lgb_calibrator = LogisticRegression().fit(lgb_cal_probs, y_cal)

# Apply calibration to predictions
cb_pred_probs_cal = cb_calibrator.predict_proba(cb_pred_probs)[:, 1]
lgb_pred_probs_cal = lgb_calibrator.predict_proba(lgb_pred_probs)[:, 1]

# Meta-stacker: combines calibrated probs
X_meta = [cb_cal_prob, lgb_cal_prob]
meta_stacker = RandomForestClassifier(n_estimators=200, max_depth=6)
ensemble_prob = meta_stacker.predict_proba(X_meta_pred)[:, 1]
```

### 4. Returns Regression (Optional)
Ridge regressor combines all outputs for continuous return prediction:

```python
# Features: ensemble_prob, cb_prob, lgb_prob, vol_pred, lagged_returns
#          (direction-weighted vol: (prob - 0.5) * vol)
returns_model = Ridge(alpha=10.0)
pred_returns = returns_model.predict(X_ret_pred)
```

### 5. Threshold Optimization
F1-optimal threshold with regime adjustments:

```python
# Find optimal threshold on CAL calibrated probs
optimal_threshold = calculate_optimal_threshold(cal_probs, y_cal)

# Regime adjustment (high vol → more conservative)
effective_threshold = adjust_threshold_for_regime(
    base_threshold=optimal_threshold,
    vol_regime=classify_vol_regime(pred_vol),
    base_rate=cal_base_rate,
)

# Final signal
signal = 1 if ensemble_prob >= effective_threshold else 0
```

### 6. Position Sizing V3
Clean 6-step pipeline:
1. **Gate Check** (prob >= threshold)
2. **Rolling EMA Ratio** (recent TP/FP performance)
3. **Config Alignment** (Top10 agreement) + EMA scaling
4. **Volatility Adjustment** (high vol → reduce)
5. **Leverage Rules** (ratio >= 1.3, alignment >= 70%)
6. **Final Position** (0.0 to 2.0)

### 7. Multi-Config Tracking
- 48+ parallel configurations tracked simultaneously
- Adaptive selection based on regime and momentum
- Rolling TP/FP ratios per config

### 8. Hull Scoring
- **HullB**: Cumulative from iter 1 (full strategy history)
- **HullF**: Rolling 180-day window (recent performance)
- Sharpe-based performance tracking

## Module Dependencies

```
sliding_window_evidence_based56.py
├── wf_config.py              ← All configuration constants
├── wf_features.py            ← RSI, Dual EMA, Risk Guard features
├── wf_optuna.py              ← Hyperparameter tuning
├── wf_adaptive_scorer.py     ← Multi-period performance scoring
├── wf_stable_ensemble.py     ← Config ensemble and signal calculation
├── wf_position_sizing.py     ← Position sizing V2
├── wf_position_sizing_v3.py  ← Position sizing V3 (primary)
├── wf_hull_scorer.py         ← Hull performance scoring
├── wf_analysis.py            ← Post-run analysis & reporting
├── wf_rolling_cal_buffer.py  ← Rolling calibration buffers
├── wf_rolling_meta_buffer.py ← Rolling meta-stacker buffers
├── wf_config_history.py      ← Config history tracking V3
├── wf_config_voting.py       ← Voting system for configs
├── wf_model_cache.py         ← Model caching for speed
├── wf_functions.py           ← Utility functions
├── window_diagnostics.py     ← Window size calculations
└── signal_aggregator.py      ← Weak signal combination
```

## Quick Start

### Backtest Mode (Full Run)
```bash
cd /media/przem/w/kaggle
python sliding_window_evidence_based56.py
# Or explicitly:
WF_DEPLOY_MODE=backtest python sliding_window_evidence_based56.py
```

### Warmup → Live Flow
```bash
# Step 1: Build state (30 iterations)
WF_DEPLOY_MODE=warmup WARMUP_ITERATIONS=30 python sliding_window_evidence_based56.py
# Creates: deploy_checkpoint.pkl

# Step 2: Make live prediction
WF_DEPLOY_MODE=live python sliding_window_evidence_based56.py
# Loads checkpoint, predicts, saves updated state
```

### Auto Mode (Recommended)
```bash
WF_DEPLOY_MODE=auto python sliding_window_evidence_based56.py
# Automatically: warmup if no checkpoint, live if checkpoint exists
```

## Key Temporal Safeguards

1. **Window Separation**: CAL between TRAIN and VAL prevents leakage
2. **Lagged Targets**: `lagged_direction_target` used for production TP/FP tracking
3. **Per-Iteration Feature Engineering**: Signal aggregator fitted on TRAIN only
4. **Pending Prediction**: Live mode stores prediction for lagged evaluation
5. **Regime-Aware Sizing**: Adaptive train window based on regime stability

## Performance Metrics

The system tracks:
- **TP/FP Ratio**: Primary performance metric (target > 1.0)
- **Hull Score**: Sharpe-based cumulative performance
- **Config Diversity**: CB/LGB correlation and disagreement rate
- **Calibration Quality**: Brier score, ECE (Expected Calibration Error)

## Configuration

All tunable parameters in `wf_config.py`:
- Window sizes
- Feature selection thresholds
- Calibration settings
- Model hyperparameters (or Optuna search)
- Multi-config grid

---

*Last updated: Based on sliding_window_evidence_based56.py analysis*

---

## Related Documentation

- **← Previous:** [Part 2: Kaggle Pipeline](../2-Kaggle_Pipeline/README.md) — Feature engineering (~450 features)
- [Part 2: Features](../2-Kaggle_Pipeline/Part_2_Features.md) — Complete feature formulas
- [Part 1: Feature Engineering](../1-Feature_Eng_st1/README.md) — Naming conventions
