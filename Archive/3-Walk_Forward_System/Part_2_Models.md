# Part 2: Ensemble Models

> **Input:** ~450 features from [Part 2: Kaggle Pipeline Features](../2-Kaggle_Pipeline/Part_2_Features.md)

## Complete Model Pipeline

The Walk-Forward system uses a **2-model ensemble** (CatBoost + LightGBM) for direction prediction, plus a separate **CatBoostRegressor** for volatility, combined via meta-stacking and position sizing.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    COMPLETE PREDICTION PIPELINE                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  INPUT: ~450 features (direction_feature_cols, volatility_feature_cols)     │
│       │                                                                      │
│       ├─────────────────────────────────────────────────────┐               │
│       │           DIRECTION ENSEMBLE                         │               │
│       │                                                      │               │
│       │  ┌─────────┐        ┌─────────┐                     │               │
│       │  │CatBoost │        │LightGBM │                     │               │
│       │  │P(up)GPU │        │P(up)    │                     │               │
│       │  └────┬────┘        └────┬────┘                     │               │
│       │       │                  │                          │               │
│       │       ▼                  ▼                          │               │
│       │  ┌─────────┐        ┌─────────┐                     │               │
│       │  │ Platt   │        │ Platt   │   (rolling CAL)     │               │
│       │  │ Calib   │        │ Calib   │                     │               │
│       │  └────┬────┘        └────┬────┘                     │               │
│       │       └───────┬─────────┘                           │               │
│       │               ▼                                     │               │
│       │      ┌────────────────┐                             │               │
│       │      │ Meta-Stacker   │ (RF or avg)                 │               │
│       │      └───────┬────────┘                             │               │
│       │              │ ensemble_prob                        │               │
│       └──────────────┼────────────────Tool github-pull-request_renderIssues failed validation: object has required property 'reactionCount' that is not defined──────────────────────┘               │
│                      │                                                       │
│       ┌──────────────┼──────────────────────────────────────┐               │
│       │              │    VOLATILITY MODEL                   │               │
│       │              ▼                                       │               │
│       │  ┌─────────────────────┐                            │               │
│       │  │ CatBoostRegressor   │                            │               │
│       │  │ Target: |returns|   │                            │               │
│       │  │ + dir_regime from   │ ◄── direction coupling     │               │
│       │  │   ensemble_prob     │                            │               │
│       │  └──────────┬──────────┘                            │               │
│       │             │ vol_pred (calibrated)                 │               │
│       └─────────────┼───────────────────────────────────────┘               │
│                     │                                                        │
│       ┌─────────────┼───────────────────────────────────────┐               │
│       │             ▼    THRESHOLD & SIGNAL                  │               │
│       │  signal = (ensemble_prob >= threshold) ? 1 : 0      │               │
│       │  + regime-specific threshold adjustment              │               │
│       └─────────────┬───────────────────────────────────────┘               │
│                     │                                                        │
│       ┌─────────────▼───────────────────────────────────────┐               │
│       │         POSITION SIZING V3                           │               │
│       │  1. Gate Check (direction gate + alpha gate)        │               │
│       │  2. EMA Ratio (recent TP/FP)                        │               │
│       │  3. Config Alignment (Top10 agreement)              │               │
│       │  4. Vol Adjustment (high vol → reduce)              │               │
│       │  5. Leverage Rules                                  │               │
│       │  6. Final Position ∈ [0.0, 2.0]                     │               │
│       └─────────────┬───────────────────────────────────────┘               │
│                     │                                                        │
│  OUTPUT: position = signal × size × leverage                                │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 1. Direction Models

### CatBoost Configuration

```python
# From wf_config.py and Optuna tuning
CATBOOST_DIR_PARAMS = {
    'grow_policy': 'Lossguide',     # Leaf-wise growth (like LightGBM)
    'max_leaves': 31,                # From Optuna
    'depth': 8,                      # Max depth
    'learning_rate': 0.01,           # Conservative
    'iterations': 1000,              # With early stopping
    'l2_leaf_reg': 10.0,            # Regularization
    'min_data_in_leaf': 50,         # Prevent overfitting
    'subsample': 0.8,               # Row sampling
    'bootstrap_type': 'Bernoulli',
    'has_time': True,               # Temporal ordering preserved
    'early_stopping_rounds': 300,
    'use_best_model': True,
    'loss_function': 'Logloss',
    'eval_metric': 'AUC',
    **CATBOOST_GPU_PARAMS,          # task_type='GPU' if available
}

# Training
cb_model = CatBoostClassifier(**CATBOOST_DIR_PARAMS)
cb_model.fit(
    X_train, y_train,
    eval_set=(X_val, y_val),
    sample_weight=train_weights,    # Half-life weighting
    verbose=False,
)
```

### LightGBM Configuration

```python
LIGHTGBM_DIR_PARAMS = {
    'boosting_type': 'gbdt',
    'num_leaves': 31,               # From Optuna
    'max_depth': 8,
    'learning_rate': 0.01,
    'n_estimators': 1000,
    'reg_lambda': 10.0,             # L2 regularization
    'min_child_samples': 50,
    'subsample': 0.8,
    'subsample_freq': 1,
    'objective': 'binary',
    'metric': 'auc',
    'verbose': -1,
    'device': 'gpu',                # Or 'cpu' if GPU unavailable
}

# Training
lgb_model = LGBMClassifier(**LIGHTGBM_DIR_PARAMS)
lgb_model.fit(
    X_train, y_train,
    eval_set=[(X_val, y_val)],
    callbacks=[early_stopping(300)],
    sample_weight=train_weights,
)
```

## Optuna Hyperparameter Tuning

```python
# Initial tuning on first window (60 seconds default)
from wf_optuna import run_optuna_tuning

optuna_results = run_optuna_tuning(
    X_tune_train, y_tune_train, 
    X_tune_val, y_tune_val,
    timeout_sec=OPTUNA_TIMEOUT_SECONDS,  # Default: 60
    gpu_params=CATBOOST_GPU_PARAMS,
    gap_size=WF_CAL + WF_VAL,
    verbose=True
)

# Returns BOTH CatBoost and LightGBM best params
best_cb_params = optuna_results['best_cb_params']
best_lgb_params = optuna_results['best_lgb_params']
```

### Optuna Search Space

```python
# From wf_optuna.py
def catboost_objective(trial):
    params = {
        'num_leaves': trial.suggest_int('num_leaves', 16, 64),
        'max_depth': trial.suggest_int('max_depth', 4, 12),
        'learning_rate': trial.suggest_float('learning_rate', 0.005, 0.05, log=True),
        'n_estimators': trial.suggest_int('n_estimators', 500, 2000),
        'reg_lambda': trial.suggest_float('reg_lambda', 1.0, 100.0, log=True),
        'min_child_samples': trial.suggest_int('min_child_samples', 20, 100),
        'subsample': trial.suggest_float('subsample', 0.6, 0.95),
    }
    # ... fit and evaluate
```

---

## 2. Volatility Model

Separate CatBoostRegressor trained on `|forward_returns|` with **direction-volatility coupling**:

```python
# Direction→Volatility regime coupling
# Use META ENSEMBLE output for direction regime (meta already trained)
train_dir_regime = ((cb_train_probs + lgb_train_probs) / 2.0 > 0.5).astype(float)
val_dir_regime = ((cb_val_probs + lgb_val_probs) / 2.0 > 0.5).astype(float)
pred_dir_regime = (ensemble_prob > 0.5).astype(float)

# Create enhanced volatility features with direction regime
X_train_vol_enhanced = X_train_vol.copy()
X_train_vol_enhanced['dir_regime'] = train_dir_regime  # Direction coupling

# Train volatility model
volatility_model = CatBoostRegressor(**vol_params)
volatility_model.fit(
    X_train_vol_enhanced,
    y_train_vol,           # Target: |forward_returns|
    sample_weight=train_sample_weights,  # Half-life temporal weighting
    eval_set=(X_val_vol_enhanced, y_val_vol),
)

# Generate predictions
pred_vol_preds_raw = volatility_model.predict(X_pred_vol_enhanced)
```

### Volatility Calibration

```python
# Empirical rescaling based on CAL residual distribution
cal_vol_residuals = np.abs(y_cal_vol - cal_vol_preds)
cal_vol_scale = (
    np.median(y_cal_vol) / np.median(cal_vol_preds)
    if np.median(cal_vol_preds) > 0 else 1.0
)
cal_vol_scale = np.clip(cal_vol_scale, 0.5, 2.0)  # Limit extreme rescaling

# Apply calibration to prediction
pred_vol_preds = pred_vol_preds_raw * cal_vol_scale
```

### Volatility Regime Classification

```python
# Thresholds based on historical volatility percentiles
VOL_THRESH_LOW = 0.0021   # P25
VOL_THRESH_MED = 0.0055   # P50
VOL_THRESH_HIGH = 0.0105  # P75
VOL_THRESH_VHIGH = 0.0171 # P90

def classify_vol_regime(vol_pred):
    if vol_pred < VOL_THRESH_LOW:
        return "LOW"        # Calm market, good for directional trades
    elif vol_pred < VOL_THRESH_MED:
        return "MEDIUM"     # Normal conditions
    elif vol_pred < VOL_THRESH_HIGH:
        return "HIGH"       # Elevated risk
    elif vol_pred < VOL_THRESH_VHIGH:
        return "VERY_HIGH"  # High risk, reduce position
    else:
        return "EXTREME"    # Crisis mode, defensive only
```

---

## 3. Meta-Stacker

```python
# RandomForest meta-stacker combines calibrated probabilities
from sklearn.ensemble import RandomForestClassifier as RF_Meta

# Features: [cb_cal_prob, lgb_cal_prob] (2 features)
X_meta_buffer, y_meta_buffer = meta_buffer.get_buffer()

meta_stacker = RF_Meta(
    n_estimators=200,           # META_STACKER_N_ESTIMATORS
    max_depth=6,                # META_STACKER_MAX_DEPTH
    min_samples_leaf=20,        # META_STACKER_MIN_SAMPLES_LEAF
    random_state=42,
    n_jobs=-1,
)
meta_stacker.fit(X_meta_buffer, y_meta_buffer)

# Generate ensemble prediction
X_meta_pred = np.column_stack([cb_pred_probs_cal, lgb_pred_probs_cal])
pred_dir_probs = meta_stacker.predict_proba(X_meta_pred)[:, 1]
```

### Fallback: Simple Averaging

```python
# When meta_buffer < MIN_SAMPLES or only one class
if meta_buffer.size() < META_STACKER_MIN_SAMPLES:
    # CB+LGB mode: equal weighting
    pred_dir_probs = (cb_pred_probs_cal + lgb_pred_probs_cal) / 2.0
```

## Model Diversity Tracking

```python
# Track correlation between base models
corr_cb_lgb = np.corrcoef(cb_val_probs, lgb_val_probs)[0, 1]

# Disagreement rate: how often models give opposite predictions
cb_val_preds = (cb_val_probs > 0.5).astype(int)
lgb_val_preds = (lgb_val_probs > 0.5).astype(int)
disagreement_rate = 1.0 - (cb_val_preds == lgb_val_preds).mean()

# Prediction spread: average std across models
stacked_probs = np.column_stack([cb_val_probs, lgb_val_probs])
pred_spread = stacked_probs.std(axis=1).mean()

# Logged every iteration for analysis
model_diversity_metrics.append({
    'iteration': iteration,
    'avg_correlation': corr_cb_lgb,
    'disagreement_rate': disagreement_rate,/media/przem/w/kaggle/final-2.py
    'pred_spread': pred_spread,
    'cb_val_auc': cb_val_auc,
    'lgb_val_auc': lgb_val_auc,
    'meta_type': meta_type,  # 'rf' or 'avg'
})
```

## Disagreement Guard

```python
# Force prediction to 0 when models strongly disagree
USE_DISAGREEMENT_GUARD = True
DISAGREEMENT_THRESHOLD = 0.25

pred_disagreement = np.abs(cb_pred_probs_cal - lgb_pred_probs_cal).mean()
val_disagreement_std = np.abs(cb_val_probs_cal - lgb_val_probs_cal).std()
disagreement_z_score = (pred_disagreement - val_disagreement) / max(val_disagreement_std, 0.01)

if pred_disagreement > DISAGREEMENT_THRESHOLD or disagreement_z_score > 2.0:
    pred_preds = np.zeros_like(pred_preds)  # Force to 0 (no trade)
```

## Drift Detection & Retuning

```python
# Check for distribution drift using PSI
if USE_DRIFT_DETECTION and iteration % DRIFT_CHECK_INTERVAL == 0:
    psi_score = compute_psi(train_features, val_features)
    
    if psi_score > DRIFT_PSI_THRESHOLD:
        # Drift detected
        drift_alerts.append({
            'iteration': iteration,
            'psi_score': psi_score,
        })
        
        # Optionally retune hyperparameters
        if OPTUNA_RETUNE_ON_DRIFT:
            optuna_results = run_optuna_tuning(
                X_train, y_train, X_val, y_val,
                timeout_sec=OPTUNA_RETUNE_TIMEOUT,
                # Enqueue previous best as starting point
                enqueue_previous=OPTUNA_ENQUEUE_PREVIOUS_BEST,
            )
```

## Drift Adjustments

```python
# When drift is active, adjust model params for stability
if USE_DRIFT_ADJUSTMENT and drift_active:
    DIR_MODEL_PARAMS['l2_leaf_reg'] *= DRIFT_L2_MULTIPLIER     # More regularization
    DIR_MODEL_PARAMS['depth'] -= DRIFT_DEPTH_REDUCTION          # Shallower trees
    DIR_MODEL_PARAMS['iterations'] = int(iterations * 0.75)     # Fewer iterations
```

## Half-Life Sample Weighting

```python
# Recent samples weighted more heavily
def calculate_half_life_weights(n_samples, half_life=HALF_LIFE_SAMPLES):
    """
    Exponential decay weights with half-life.
    Last sample has weight 1.0, sample at half_life ago has weight 0.5
    """
    decay_rate = np.log(2) / half_life
    weights = np.exp(-decay_rate * np.arange(n_samples)[::-1])
    weights = weights / weights.max()  # Normalize to max=1
    weights = np.maximum(weights, MIN_SAMPLE_WEIGHT)  # Floor
    return weights

# Applied during training
train_weights = calculate_half_life_weights(len(X_train))
cb_model.fit(X_train, y_train, sample_weight=train_weights, ...)
```

## Feature Importance

```python
# CatBoost feature importance
cb_importances = cb_model.get_feature_importance(
    type=FEATURE_IMPORTANCE_TYPE  # 'PredictionValuesChange'
)

# Top features selection
top_indices = np.argsort(cb_importances)[::-1][:int(len(feature_cols) * FEATURE_SELECTION_PERCENT / 100)]
selected_features = [feature_cols[i] for i in top_indices]
```

---

## Returns Regression Model

The final prediction stage combines direction probability, volatility prediction, and additional signals to predict expected returns magnitude.

### Model Architecture

```python
# Ridge Regression for returns prediction
from sklearn.linear_model import Ridge

RETURNS_MODEL_ALPHA = 10.0  # L2 regularization strength
```

### Feature Construction

```python
# Combine all model outputs into returns features
returns_features = {
    # Direction signals
    'ensemble_prob': pred_dir_probs.mean(),           # Meta-stacker output
    'cb_prob': cb_pred_probs_cal.mean(),              # CatBoost calibrated
    'lgb_prob': lgb_pred_probs_cal.mean(),            # LightGBM calibrated
    'direction_confidence': np.abs(pred_dir_probs.mean() - 0.5) * 2,  # [0,1]
    
    # Volatility signals
    'vol_pred': vol_pred_rescaled.mean(),             # Predicted volatility
    'vol_regime': vol_regime,                          # Categorical regime
    
    # Combined signals
    'direction_weighted_vol': vol_pred * (pred_dir_probs - 0.5),  # Signed volatility
    
    # Historical context
    'lagged_returns_1': df['close'].pct_change(1).iloc[-1],
    'lagged_returns_5': df['close'].pct_change(5).iloc[-1],
}

X_returns = pd.DataFrame([returns_features])
```

### Target Definition

```python
# Continuous net candle return (regression target)
# Uses full candle info (high, low) for better signal
future_high = high.shift(-horizon)
future_low = low.shift(-horizon)
up_move = (future_high - close) / close
down_move = (close - future_low) / close
y_returns = up_move - down_move
```

### Model Training

```python
returns_model = Ridge(alpha=RETURNS_MODEL_ALPHA)
returns_model.fit(X_returns_train, y_returns_train, sample_weight=train_weights)

# Prediction
expected_returns = returns_model.predict(X_returns_pred)
```

---

## Complete Prediction Integration

This section shows how all models combine to produce the final position signal.

### Prediction Pipeline Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    WALK-FORWARD ITERATION                       │
└─────────────────────────────────────────────────────────────────┘
                              │
    ┌─────────────────────────┼─────────────────────────┐
    │                         │                         │
    ▼                         ▼                         ▼
┌─────────┐           ┌─────────────┐           ┌─────────────┐
│CatBoost │           │  LightGBM   │           │HistGradient │
│Direction│           │  Direction  │           │  Direction  │
└────┬────┘           └──────┬──────┘           └──────┬──────┘
     │                       │                         │
     ▼                       ▼                         ▼
┌─────────┐           ┌─────────────┐           ┌─────────────┐
│ Isotonic│           │  Isotonic   │           │  Isotonic   │
│Calibrate│           │  Calibrate  │           │  Calibrate  │
└────┬────┘           └──────┬──────┘           └──────┬──────┘
     │                       │                         │
     └───────────────────────┼─────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │  Meta-Stacker   │
                    │(RF or Averaging)│
                    └────────┬────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │   P(up) [0,1]   │──────────────────┐
                    └────────┬────────┘                  │
                              │                          │
                              ▼                          │
                    ┌─────────────────┐                  │
                    │  dir_regime =   │                  │
                    │  1 if P>0.5     │                  │
                    │  else 0         │                  │
                    └────────┬────────┘                  │
                              │                          │
                              ▼                          │
                    ┌─────────────────┐                  │
                    │CatBoost Regress │                  │
                    │  (Volatility)   │                  │
                    │ +dir_regime feat│                  │
                    └────────┬────────┘                  │
                              │                          │
                              ▼                          │
                    ┌─────────────────┐                  │
                    │ Calibration     │                  │
                    │(CAL rescaling)  │                  │
                    └────────┬────────┘                  │
                              │                          │
                              ▼                          │
                    ┌─────────────────┐                  │
                    │  vol_pred [0,∞) │                  │
                    └────────┬────────┘                  │
                              │                          │
                              ▼                          ▼
                    ┌─────────────────────────────────────┐
                    │       Returns Regression            │
                    │ Features: P(up), vol_pred, lags    │
                    │           Ridge(α=10)              │
                    └────────────────┬────────────────────┘
                                     │
                                     ▼
                    ┌─────────────────────────────────────┐
                    │        expected_returns [-∞,+∞]     │
                    └────────────────┬────────────────────┘
                                     │
                                     ▼
                    ┌─────────────────────────────────────┐
                    │        Position Sizing V3          │
                    │  (See Part_4_Position_Sizing.md)   │
                    │                                     │
                    │  1. Signal polarity → {-1, 0, +1}  │
                    │  2. Confidence → scale factor      │
                    │  3. Volatility → risk adjustment   │
                    │  4. Risk budget check              │
                    │  5. Drawdown adjustment            │
                    │  6. Clip to [0, MAX_LEVERAGE]      │
                    └────────────────┬────────────────────┘
                                     │
                                     ▼
                    ┌─────────────────────────────────────┐
                    │     FINAL POSITION SIZE [0,2.0]     │
                    │  + DIRECTION from P(up) threshold   │
                    └─────────────────────────────────────┘
```

### Key Integration Points

| Stage | Input | Output | Purpose |
|-------|-------|--------|---------|
| Direction Ensemble | Features | P(up) ∈ [0,1] | Classify market direction |
| Direction→Volatility Coupling | P(up) | dir_regime ∈ {0,1} | Condition vol prediction |
| Volatility Model | Features + dir_regime | σ̂ ∈ [0,∞) | Predict absolute magnitude |
| Returns Regression | P(up), σ̂, lags | E[r] ∈ ℝ | Expected signed return |
| Position Sizing | E[r], σ̂, P(up), state | size ∈ [0,2] | Final leveraged position |

### Code Summary

```python
# === DIRECTION ===
cb_probs = cb_model.predict_proba(X_pred)[:, 1]
lgb_probs = lgb_model.predict_proba(X_pred)[:, 1]

cb_probs_cal = cb_calibrator.predict(cb_probs)
lgb_probs_cal = lgb_calibrator.predict(lgb_probs)

if USE_META_STACKER:
    meta_X = np.column_stack([cb_probs_cal, lgb_probs_cal])
    dir_prob = meta_stacker.predict_proba(meta_X)[:, 1]
else:
    dir_prob = (cb_probs_cal + lgb_probs_cal) / 2

# === VOLATILITY (conditioned on direction) ===
X_pred_vol = X_pred.copy()
X_pred_vol['dir_regime'] = (dir_prob > 0.5).astype(int)
vol_pred_raw = vol_model.predict(X_pred_vol)
vol_pred = vol_pred_raw * vol_calibration_factor
vol_pred = np.clip(vol_pred, VOL_MIN, VOL_MAX)

# === RETURNS ===
returns_X = build_returns_features(dir_prob, vol_pred, lagged_returns)
expected_returns = returns_model.predict(returns_X)

# === POSITION SIZING ===
position_size, position_direction = position_sizer_v3(
    expected_returns=expected_returns,
    dir_prob=dir_prob,
    vol_pred=vol_pred,
    current_drawdown=current_drawdown,
    risk_budget_remaining=risk_budget,
)

# Final output
final_position = position_direction * position_size  # in [-2.0, +2.0]
```

---

*See [Part_3_Calibration.md](Part_3_Calibration.md) for probability calibration details.*
*See [Part_4_Position_Sizing.md](Part_4_Position_Sizing.md) for position sizing logic.*
