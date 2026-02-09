# Part 3: Models

> Model architectures, training, ensembles, and position sizing
>
> **Note:** This documents the Kaggle competition models. For production Walk-Forward training, see [Part 3: Walk-Forward System](../3-Walk_Forward_System/README.md)

---

## Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         KAGGLE PIPELINE: MODEL FLOW                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   RAW DATA (train.csv)                                                      │
│       ↓                                                                     │
│   FEATURE ENGINEERING (~400 base features)                                  │
│   ├── RowByRowFeatureCalculator → ~400 technical features                  │
│   │                                                                         │
│   ├── REGIME DETECTION                                                      │
│   │   ├── HMM-4 Regime → ~20 features                                      │
│   │   ├── HMM-5 Regime → ~20 features                                      │
│   │   ├── Feature-Group HMMs (6 groups) → ~60 features                     │
│   │   ├── Derived Feature HMMs (MOM*, D*) → ~16 features                   │
│   │   └── DTMC → ~11 features                                              │
│   │                                                                         │
│   ├── ANOMALY DETECTION                                                     │
│   │   ├── Multi-Level Isolation Forest → ~15 features                      │
│   │   └── Per-Group Isolation Forest → ~45 features                        │
│   │                                                                         │
│   ├── CHANGE DETECTION                                                      │
│   │   ├── CUSUM Changepoint → ~25 features                                 │
│   │   └── Multi-Signal Ensemble → ~35 features                             │
│   │                                                                         │
│   ├── STATE ESTIMATION                                                      │
│   │   ├── Kalman Filter (3D) → ~5 features                                 │
│   │   └── GARCH(1,1) → ~7 features                                         │
│   │                                                                         │
│   └── HELPER BASELINES                                                      │
│       ├── Linear Regression Vol → ~3 features                              │
│       ├── EWMA Vol → ~6 features                                           │
│       └── Logistic Regression Dir → ~4 features                            │
│       ↓                                                                     │
│   FEATURE SELECTION (CatBoost RecursiveByShapValues)                       │
│   ├── Multi-fold temporal CV (5 folds)                                     │
│   ├── Keep ~85% of features (conservative)                                 │
│   └── Eliminate only if harmful in ≥60% of folds                           │
│       ↓                                                                     │
│   MODEL TRAINING                                                            │
│   ├── Direction Model (CatBoostClassifier) → P(up)                         │
│   └── Volatility Model (CatBoostRegressor) → σ                             │
│       ↓                                                                     │
│   POSITION SIZING OPTIMIZATION                                              │
│   ├── Grid search over model combinations                                  │
│   ├── Calculate Sharpe-like competition score                              │
│   └── Find optimal threshold/scaling                                       │
│       ↓                                                                     │
│   SUBMISSION                                                                │
│       position = f(direction_prob, volatility_pred, optimized_params)      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 1. Direction Model (Cell 18)

### Architecture

| Property | Value |
|----------|-------|
| **Type** | CatBoostClassifier |
| **Target** | `direction_target = (net_candle_ret > 0)` — uses up_move - down_move |
| **Loss** | Logloss (binary cross-entropy) |
| **Feature Selection** | RecursiveByShapValues |
| **Temporal Order** | `has_time=True` (critical) |

### Training Configuration

```python
CatBoostClassifier(
    iterations=None,           # Auto-optimized
    learning_rate=None,        # Auto-optimized
    depth=None,                # Auto-optimized
    has_time=True,             # CRITICAL: Preserves temporal order
    random_seed=42 + run_idx,
    task_type='GPU'            # If available
)
```

### Feature Selection Process

1. **Multi-fold temporal CV** (5 folds):
   ```python
   fold_configs = [
       (0.50, 0.70),   # Train 0-50%, Val 50-70%
       (0.60, 0.80),   # Train 0-60%, Val 60-80%
       (0.70, 0.85),   # Train 0-70%, Val 70-85%
       (0.75, 0.90),   # Train 0-75%, Val 75-90%
       (0.80, 0.95),   # Train 0-80%, Val 80-95%
   ]
   ```

2. **Selection algorithm**: `RecursiveByShapValues` (most accurate per CatBoost docs)

3. **Conservative threshold**: Only eliminate if harmful in ≥60% of folds

4. **Target retention**: ~85% of features kept

### Excluded Columns (Data Leakage Prevention)

```python
exclude_cols = [
    # Metadata
    'date', 'timestamp', 'row_id',
    
    # Targets (MUST exclude)
    'direction_target', 'volatility_target', 'target',
    
    # Forward-looking (MUST exclude)
    'forward_returns', 'risk_free_rate', 'market_forward_excess_returns',
    
    # Raw data
    'close', 'open', 'high', 'low', 'volume'
]
```

### Metrics (Validation)

- **Primary**: AUC-ROC (better for imbalanced data)
- **Secondary**: F-β (β=0.5), Precision, Recall

### Multiple Runs Strategy

```python
num_baseline_runs = 3  # Different seeds
# Select best by AUC on validation set
best_run = max(all_runs, key=lambda x: x['val_auc'])
```

---

## 2. Volatility Model (Cell 19)

### Architecture

| Property | Value |
|----------|-------|
| **Type** | CatBoostRegressor |
| **Target** | `volatility_target = \|forward_returns\|` (winsorized) |
| **Loss** | Huber (δ=1.0) — robust to outliers |
| **Feature Selection** | RecursiveByShapValues |
| **Temporal Order** | `has_time=True` (critical) |

### Training Configuration

```python
CatBoostRegressor(
    iterations=500,
    learning_rate=0.05,
    depth=6,
    has_time=True,              # CRITICAL: Preserves temporal order
    loss_function='Huber:delta=1.0',
    early_stopping_rounds=50,
    l2_leaf_reg=3.0,            # Regularization
    task_type='GPU'
)
```

### Target Preprocessing (Winsorization)

```python
# Clip |forward_returns| to [5th, 95th] percentile
p05 = abs(forward_returns).quantile(0.05)
p95 = abs(forward_returns).quantile(0.95)
volatility_target = clip(abs(forward_returns), p05, p95)
```

### Why Huber Loss?

- More robust than MSE to outliers
- δ=1.0 balances between MSE (δ→∞) and MAE (δ→0)
- Financial returns have fat tails → Huber appropriate

### Metrics (Validation)

- **Primary**: RMSE
- **Secondary**: R², MAE, MAPE

---

## 3. HMM Regime Models (Cells 6-7)

### HMM-4 (4-State Regime Model)

```python
from hmmlearn.hmm import GaussianHMM

hmm4 = GaussianHMM(
    n_components=4,            # 4 market regimes
    covariance_type='full',
    n_iter=1000,
    random_state=42
)
```

**Regimes Typically Represent:**
- Regime 0: Low volatility, trending up
- Regime 1: Low volatility, trending down
- Regime 2: High volatility, trending up
- Regime 3: High volatility, trending down

**Features Generated:**
- `hmm4_regime` — Current regime (0-3)
- `hmm4_prob_0` to `hmm4_prob_3` — Regime probabilities
- `hmm4_transition_prob_{i}_{j}` — Transition matrix entries

### HMM-5 (5-State Regime Model)

Same as HMM-4 but with 5 components:
- Adds intermediate regime state
- More granular regime detection

### Feature-Group HMMs (Cell 7.6) — final-2.py only

Separate HMMs trained on feature groups:

| Prefix | Feature Group |
|--------|---------------|
| M* | Momentum features |
| E* | EWMA features |
| I* | Indicator features |
| P* | Price-based features |
| V* | Volatility features |
| S* | Statistical features |

Each generates:
- `{prefix}_hmm_regime`
- `{prefix}_hmm_prob_{i}`

### Derived Feature HMMs (Cell 7.7) — final-2.py only

HMMs trained on **calculated/derived features** (not raw data):

| Prefix | Feature Group | Description |
|--------|---------------|-------------|
| MOM* | Momentum_Dynamics | Momentum acceleration, vol-adjusted momentum |
| D* | Binary_Regimes | High vol regime, trend regime, reversal signals |

**Momentum Features (MOM group):**
```python
MOMENTUM_FEATURES = [
    'momentum_accel_5d', 'momentum_accel_21d',    # Momentum acceleration
    'vol_momentum_5', 'vol_momentum_21',           # Volatility momentum
    'vol_adj_momentum_5d', 'vol_adj_momentum_21d', # Vol-adjusted momentum
]
```

**Binary Regime Features (D group):**
```python
BINARY_FEATURES = [
    'high_vol_regime', 'extreme_vol_regime',       # Volatility regimes
    'uptrend_regime', 'strong_uptrend',            # Trend regimes
    'reversal_5d', 'reversal_21d',                 # Reversal signals
    'ma_cross_5_20', 'ma_cross_10_50', 'ma_cross_50_200',  # MA crossovers
]
```

**Features Generated (per derived group):**
- `{prefix}_hmm_regime` — Current regime (0, 1, 2)
- `{prefix}_hmm_confidence` — Max probability across regimes
- `{prefix}_hmm_regime_change` — Binary transition indicator
- `{prefix}_hmm_duration` — Consecutive rows in current regime

**Sample Size Requirements:**
- Uses 3-component diagonal HMM
- Dynamically limits features: `max_features = (samples/20 - 8) / 6`
- Minimum 300 samples required
- Features auto-limited to 3-15 based on available data

---

## 4. Anomaly Detection (Cell 10)

### Multi-Level Isolation Forest

Three Isolation Forest models with different contamination levels for hierarchical anomaly detection:

```python
from sklearn.ensemble import IsolationForest

# Three levels with auto-determined contamination
contamination_levels = {
    'extreme': 0.01,    # High precision - most severe anomalies
    'moderate': 0.05,   # Balanced - typical anomalies  
    'mild': 0.10,       # High recall - sensitive detection
}

for level_name, contamination in contamination_levels.items():
    iso_forest = IsolationForest(
        contamination=contamination,
        random_state=42,
        n_estimators=100
    )
```

**Features Generated (per level):**
- `anomaly_{level}_is` — Binary anomaly flag (0/1)
- `anomaly_{level}_severity` — Severity score (normalized anomaly score)

**HMM Interaction Features:**
- `anomaly_moderate_sev_x_hmm5` — Severity × HMM-5 regime
- `anomaly_extreme_sev_x_hmm5` — Severity × HMM-5 regime
- `anomaly_moderate_sev_x_hmm` — Severity × HMM-4 regime

### Per-Group Isolation Forest (Cell 7.8)

Separate Isolation Forest models per feature group for granular anomaly detection:

| Prefix | Feature Group | Features |
|--------|---------------|----------|
| M* | Momentum | Momentum-related features |
| E* | EWMA | EWMA signals |
| I* | Indicator | Technical indicators |
| P* | Price | Price-based features |
| V* | Volatility | Volatility measures |
| S* | Statistical | Statistical features |

**Features Generated (per group):**
- `{prefix}_if_anomaly_score` — Raw anomaly score
- `{prefix}_if_anomaly_score_norm` — Normalized score (0-1)
- `{prefix}_if_is_anomaly` — Binary flag
- `{prefix}_if_severity` — Severity score

**Global Aggregates:**
- `group_if_anomaly_score_mean` — Mean score across all groups
- `group_if_anomaly_score_max` — Maximum score across groups
- `group_if_n_anomalies` — Count of groups with anomalies
- `group_if_max_severity` — Maximum severity across groups
- `group_if_any_severe` — Binary: any group has severe anomaly

---

## 5. Change Detection (Cell 11)

### CUSUM (Cumulative Sum Control Chart)

Enhanced CUSUM with adaptive normalization and reset logic:

```python
def cusum_changepoint(series, threshold=2.0, drift=0.0, 
                      min_spacing=5, rolling_window=63):
    """
    CUSUM with improvements:
    1. Reset after detection (prevents runaway accumulation)
    2. Rolling normalization (adapts to changing conditions)
    3. Minimum spacing (prevents clustered detections)
    4. Returns magnitude for feature engineering
    """
    for i in range(1, n):
        # Rolling z-score normalization (63-day window)
        if rolling_window > 0 and i >= rolling_window:
            window_data = series[i-rolling_window:i]
            mean = np.mean(window_data)
            std = np.std(window_data, ddof=1) + 1e-8
        
        # CUSUM update with drift
        cusum_pos[i] = max(0, cusum_pos[i-1] + (z_score - drift))
        cusum_neg[i] = min(0, cusum_neg[i-1] + (z_score + drift))
        
        # Detection with reset
        if cusum_pos[i] > threshold:
            changepoint_up[i] = 1
            cusum_pos[i] = 0  # Reset after detection
```

**Basic CUSUM Features:**
- `cusum_volatility_pos` — Positive CUSUM for volatility
- `cusum_volatility_neg` — Negative CUSUM for volatility
- `cusum_returns_pos` — Positive CUSUM for returns
- `cusum_returns_neg` — Negative CUSUM for returns

**Changepoint Indicators:**
- `changepoint_vol_up` — Volatility increased significantly
- `changepoint_vol_down` — Volatility decreased significantly
- `changepoint_vol_any` — Any volatility changepoint
- `changepoint_ret_up/down/any` — Same for returns
- `changepoint_vol_magnitude` — Size of volatility change
- `changepoint_ret_magnitude` — Size of return change

**Derived Features:**
- `changepoint_combined` — Either vol or return changepoint
- `cusum_vol_ratio` — Pos/Neg balance
- `cusum_vol_momentum` — Pos + Neg (direction)
- `cusum_days_since_changepoint` — Time since last changepoint
- `changepoint_signal_count` — Sum of all changepoint signals
- `cusum_changepoint_count_21d/63d` — Rolling count

**HMM Interactions:**
- `cusum_vol_change_x_hmm` — Changepoint × HMM-4 regime
- `cusum_ret_mom_x_hmm` — Momentum × HMM-4 regime
- `cusum_vol_change_x_hmm5` — Changepoint × HMM-5 regime
- `cusum_vol_change_x_extreme_anom` — Changepoint × Anomaly

---

## 6. Multi-Signal Ensemble (Cell 12)

Combines multiple signals for high-precision changepoint detection using ensemble voting:

### Signal Sources (5-6 total)

1. **CUSUM changepoints** — Rolling 63-day normalization
2. **HMM-4 regime transitions** — 4-state market regimes
3. **HMM-5 regime transitions** — 5-state volatility regimes (if available)
4. **Anomaly detection** — 3 severity levels combined
5. **Volatility jumps** — Multi-period (21d/180d/252d)

### Ensemble Methods

```python
# Signal agreement count
signal_count = (cusum_cp + hmm4_trans + hmm5_trans + 
                anomaly_flag + vol_jump)

# Multiple ensemble strategies evaluated:
ensemble_methods = {
    'CUSUM_only': cusum_only,           # Baseline
    'Any_2plus': signal_count >= 2,      # High recall
    'Majority_3plus': signal_count >= 3, # Balanced
    'Strong_4plus': signal_count >= 4,   # High precision
    'VeryStrong_5plus': signal_count >= 5,# Ultra precision
}

# Auto-select best by F1 score on validation
```

### Multi-Period Volatility Jumps

Different lookback windows capture different market dynamics:

| Period | Lookback | Use Case |
|--------|----------|----------|
| Month | 21 days | Day/swing trading, weekly options |
| Half-year | 180 days | Position trading, monthly options |
| Year | 252 days | Portfolio rebalancing, macro |

**Per-Period Features:**
- `{period}_vol_jump` — Raw jump detection (binary)
- `{period}_ensemble` — Optimized ensemble (binary)
- `{period}_signal_count` — Signals agreeing (0-6)
- `{period}_confidence` — Signal agreement ratio (0.0-1.0)

**Aggregate Features:**
- `periods_detecting_jump` — Count of periods with jumps (0-3)
- `periods_ensemble_triggered` — Period ensembles triggered (0-3)
- `avg_period_confidence` — Average confidence across periods
- `cusum_vol_momentum` — Legacy feature (best overall method)
- `large_vol_jump` — Majority consensus volatility jump

**HMM Interaction Features (per period):**
- `{period}_ensemble_x_hmm4` — Ensemble × HMM-4 regime
- `{period}_confidence_x_hmm4` — Confidence × HMM-4 regime
- `{period}_ensemble_x_hmm5` — Ensemble × HMM-5 regime
- `{period}_confidence_x_hmm5` — Confidence × HMM-5 regime

---

## 7. Kalman Filter (Cells 13-14)

**3D State-Space Model** with position, velocity, and acceleration:

State estimation for noisy time series with adaptive noise estimation:

```python
class AdaptiveKalmanFilter:
    """
    3D State: [position, velocity, acceleration]
    - Position: Current value estimate
    - Velocity: Rate of change (1st derivative)  
    - Acceleration: Rate of change of velocity (2nd derivative)
    
    Allows modeling curved trajectories and momentum changes.
    """
    
    # State transition matrix F (3x3)
    F = np.array([
        [1, dt, 0.5*dt**2],  # position += velocity*dt + 0.5*accel*dt²
        [0, 1, dt],           # velocity += accel*dt
        [0, 0, 1]             # acceleration persists
    ])
    
    # Predict step
    x_pred = F @ x_prev
    P_pred = F @ P_prev @ F.T + Q
    
    # Update step (with measurement)
    K = P_pred @ H.T @ inv(H @ P_pred @ H.T + R)
    x_new = x_pred + K @ (z - H @ x_pred)
```

**Training Strategy:**
- **Train on PARTIAL** using TRUE forward_returns_20d (horizon=20 days)
- **Apply predict-only** to TRAIN/VALIDATION — no future updates
- Supervised training extracts regime-dependent signal

**Features Generated:**
- `kalman_state_mean` — Filtered position estimate
- `kalman_state_variance` — Estimation uncertainty
- `kalman_residual` — Innovation (actual - predicted)
- `kalman_velocity` — Rate of change estimate
- `kalman_acceleration` — Second derivative estimate

---

## 8. GARCH(1,1) Volatility Model (Cell 14.5)

**Generalized Autoregressive Conditional Heteroskedasticity** for modeling time-varying variance:

```python
# GARCH(1,1) equation:
#   σ²[t] = ω + α * ε²[t-1] + β * σ²[t-1]
#
# Parameters:
#   ω (omega) = long-run variance weight  
#   α (alpha) = ARCH parameter (reaction to past shocks)
#   β (beta)  = GARCH parameter (persistence of volatility)

from arch import arch_model

# Fit on PARTIAL dataset (returns scaled to percentage)
garch_model = arch_model(
    returns_scaled,
    vol='Garch', p=1, q=1,
    mean='Zero',
    rescale=False
)
garch_result = garch_model.fit(disp='off')

# Extract fitted parameters
garch_omega = garch_result.params['omega']
garch_alpha = garch_result.params['alpha[1]']
garch_beta = garch_result.params['beta[1]']

# Stationarity check: α + β < 1
assert garch_alpha + garch_beta < 1.0

# Long-run variance: ω / (1 - α - β)
garch_long_run_var = garch_omega / (1 - garch_alpha - garch_beta)
```

**Strategy:**
1. Fit GARCH(1,1) on PARTIAL to get parameters (ω, α, β)
2. Apply row-by-row to PARTIAL + TRAIN with extracted parameters
3. EWMA fallback if arch library unavailable or model non-stationary

**Features Generated:**
- `garch_variance` — Current conditional variance σ²[t]
- `garch_volatility` — Square root of variance (rescaled to decimal)
- `garch_forecast_1d` — 1-day ahead volatility forecast
- `garch_standardized_resid` — ε[t] / σ[t] (should be ~N(0,1))
- `garch_vol_shock` — (ε² - σ²) / σ² (surprise measure)
- `garch_vol_regime` — Tercile regime (1=low, 2=medium, 3=high)
- `garch_vol_change_1d` — Day-over-day volatility change

**EWMA Fallback:**
When GARCH fitting fails, uses RiskMetrics EWMA:
```python
ewma_lambda = 0.94  # Standard decay factor
var_t = lambda * var_t_prev + (1-lambda) * epsilon_sq
```

---

## 9. Helper Baseline Models (Cell 9)

Simple baseline models providing comparative features:

### Linear Regression Volatility Helper

```python
from sklearn.linear_model import LinearRegression

# Features for volatility prediction (all lagged)
vol_features_cols = [
    'daily_volatility_lagged',
    'volatility_ma_5', 'volatility_ma_21',
    'mean_hist_vol_5', 'mean_hist_vol_21',
]

# Expanding window training (row i trains on rows 0 to i-1)
lr = LinearRegression()
lr.fit(train_data[:i], train_target[:i])
```

**Features Generated:**
- `helper_vol_lr` — Linear regression volatility forecast
- `helper_vol_lr_error` — Prediction error (actual - predicted)
- `helper_vol_lr_x_regime` — LR × HMM regime interaction

### EWMA Volatility Helper

```python
ewma_span = 21  # 21-day span
helper_vol_ewma = returns.ewm(span=ewma_span).std()
```

**Features Generated:**
- `helper_vol_ewma` — EWMA volatility forecast
- `helper_vol_ewma_error` — Prediction error
- `helper_vol_ewma_variance` — EWMA volatility std
- `helper_vol_ewma_absret` — EWMA of absolute returns
- `helper_vol_ewma_x_regime` — EWMA × regime interaction
- `helper_vol_rolling_mean` — 21-day rolling mean volatility
- `helper_vol_rolling_std` — 21-day rolling std of volatility
- `helper_vol_consensus` — Average of LR and EWMA forecasts

### Logistic Regression Direction Helper

```python
from sklearn.linear_model import LogisticRegression

# Enhanced features for direction prediction
dir_features_cols = [...]  # Multiple technical features

log_reg = LogisticRegression(max_iter=1000)
scaler = StandardScaler()
```

**Features Generated:**
- `helper_dir_prob` — Logistic regression P(up)
- `helper_dir_confidence` — |prob - 0.5| * 2
- `helper_dir_signal` — Discretized (-1/0/1) based on threshold
- `helper_dir_prob_x_regime` — Direction prob × HMM-4 regime

---

## 10. Position Sizing (Cells 20-22)

### Competition Scoring Function

```python
def calculate_competition_score(positions, forward_returns, risk_free_rate):
    """Calculate competition metric"""
    positions = np.clip(positions, 0.0, 2.0)  # Competition constraint
    
    # Strategy returns
    strategy_returns = risk_free_rate * (1 - positions) + positions * forward_returns
    strategy_excess_returns = strategy_returns - risk_free_rate
    
    # Sharpe-like metric
    cumulative = (1 + strategy_excess_returns).prod()
    mean_excess = cumulative ** (1/n) - 1
    std = strategy_returns.std()
    sharpe = mean_excess / std * sqrt(252)
    
    # Volatility penalty
    strategy_vol = std * sqrt(252) * 100
    market_vol = forward_returns.std() * sqrt(252) * 100
    excess_vol = max(0, strategy_vol / market_vol - 1.2)
    
    return sharpe - penalty(excess_vol)
```

### Position Sizing Formula

```python
# Basic formula (varies by strategy)
position = scale_factor * direction_prob * (1 / volatility_pred)

# With threshold
if direction_prob < threshold:
    position = 0  # No position

# Clipped to competition bounds
position = clip(position, 0.0, 2.0)
```

### Optimization (Cell 21)

Grid search over:
- Direction model runs (different seeds)
- Volatility model runs
- Probability thresholds
- Scale factors

```python
# All combinations
for dir_run in direction_model_runs:
    for vol_run in volatility_model_runs:
        for threshold in [0.45, 0.50, 0.55, 0.60]:
            for scale in [0.5, 1.0, 1.5, 2.0]:
                score = evaluate(dir_run, vol_run, threshold, scale)
```

### Modern Risk-Aware Position Sizing (Cell 22)

Advanced strategies using:
- Neural networks (MLPRegressor)
- Gradient boosting
- Random Forest
- Ridge regression

Input features:
- Direction probability
- Volatility prediction
- HMM regime probabilities
- Anomaly scores

---

## 11. Model Persistence (Session Management)

### Session ID Protection

```python
TRAINING_SESSION_ID = f"session_{timestamp}_{hash[:8]}"
```

All saved states tagged with session ID to prevent loading stale data.

### State Files

```python
# Calculator state (for inference)
row_by_row_calculator.save_state('calculator_state.pkl')

# Includes:
# - All EWMA states
# - Rolling windows
# - Cumulative statistics
```

---

## Summary: Complete Model Ensemble

```
KAGGLE PIPELINE: COMPLETE MODEL ARCHITECTURE
═══════════════════════════════════════════════════════════════════════════

FEATURE ENGINEERING MODELS
├── Regime Detection
│   ├── HMM-4 (4-state) → regime probabilities, transitions
│   ├── HMM-5 (5-state) → finer volatility regimes
│   ├── Feature-Group HMMs (6 groups) → per-group regimes
│   └── Derived Feature HMMs (MOM*, D*) → momentum/binary regimes
│
├── Anomaly Detection  
│   ├── Multi-Level Isolation Forest → extreme/moderate/mild
│   └── Per-Group Isolation Forest → group-specific anomalies
│
├── Change Detection
│   ├── CUSUM → volatility/return changepoints with rolling normalization
│   ├── Multi-Signal Ensemble → consensus across 5-6 signals
│   └── Multi-Period Analysis → month/halfyear/year timescales
│
├── State Estimation
│   ├── Kalman Filter (3D) → position/velocity/acceleration
│   └── GARCH(1,1) → conditional variance, volatility forecasts
│
├── Helper Baselines
│   ├── Linear Regression Vol → simple vol forecast
│   ├── EWMA Vol → exponential smoothing
│   └── Logistic Regression Dir → simple direction prob
│
└── DTMC → transition matrices, steady-state probabilities

MAIN PREDICTION MODELS
├── Direction Model (CatBoostClassifier)
│   ├── Target: P(return > 0)
│   ├── Feature Selection: RecursiveByShapValues (5-fold temporal CV)
│   └── Multiple runs (3 seeds) → best by AUC
│
└── Volatility Model (CatBoostRegressor)
    ├── Target: |forward_returns| (winsorized)
    ├── Loss: Huber (δ=1.0) — robust to outliers
    └── Multiple runs → best by RMSE

POSITION SIZING
├── Competition scoring function (Sharpe-like)
├── Grid search optimization
└── Risk-aware advanced strategies (MLP, RF, Ridge)

TEMPORAL SAFEGUARDS
├── has_time=True in all tree models
├── Expanding window training (row i uses 0 to i-1 only)
├── Rolling normalization with past-only data
├── PARTIAL → TRAIN → VALIDATION strict ordering
└── Session ID protection for saved states
```

**Feature Count by Category:**

| Category | Cell | Features |
|----------|------|----------|
| HMM-4 | 6 | ~20 |
| HMM-5 | 7 | ~20 |
| Feature-Group HMMs | 7.6 | ~60 |
| Derived Feature HMMs | 7.7 | ~16 |
| Multi-Level IF | 10 | ~15 |
| Per-Group IF | 7.8 | ~45 |
| CUSUM | 11 | ~25 |
| Multi-Signal Ensemble | 12 | ~35 |
| Kalman Filter | 13-14 | ~5 |
| GARCH(1,1) | 14.5 | ~7 |
| Helper Models | 9 | ~15 |
| DTMC | 7.5 | ~11 |
| **Total Helper Features** | | **~250** |
