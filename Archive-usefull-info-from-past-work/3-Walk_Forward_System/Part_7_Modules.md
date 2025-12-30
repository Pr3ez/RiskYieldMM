# Part 7: Supporting Modules Reference

## Module Overview

The Walk-Forward system is modularized into 16 supporting files:

```
/media/przem/w/kaggle/
├── sliding_window_evidence_based56.py   ← Main script (4,515 lines)
├── wf_config.py                         ← Configuration constants
├── wf_features.py                       ← Feature engineering
├── wf_functions.py                      ← Utility functions
├── wf_optuna.py                         ← Hyperparameter tuning
├── wf_adaptive_scorer.py                ← Multi-period scoring
├── wf_stable_ensemble.py                ← Config ensemble
├── wf_position_sizing.py                ← Position sizing V2
├── wf_position_sizing_v3.py             ← Position sizing V3 (primary)
├── wf_hull_scorer.py                    ← Hull performance scoring
├── wf_analysis.py                       ← Post-run analysis
├── wf_rolling_cal_buffer.py             ← Calibration buffers
├── wf_rolling_meta_buffer.py            ← Meta-stacker buffers
├── wf_config_history.py                 ← Config history V3
├── wf_config_voting.py                  ← Voting system
├── wf_model_cache.py                    ← Model caching
├── wf_fast_predictions.py               ← Fast prediction utilities
├── window_diagnostics.py                ← Window size calculations
└── signal_aggregator.py                 ← Weak signal combination
```

---

## wf_config.py (15KB)

**Purpose:** All configuration constants, feature groups, and hyperparameters.

### Key Sections

```python
# Signal Aggregation
USE_SIGNAL_AGGREGATION = True

# Window Settings
USE_AUTOMATIC_WINDOWS = False
MIN_VAL_WINDOW = 150
MIN_CAL_WINDOW = 100
MANUAL_WF_TRAIN = 1000
MANUAL_WF_VAL = 200
MANUAL_WF_CAL = 150

# Feature Selection
FEATURE_SELECTION_PERCENT = 40
USE_TWO_PHASE_FEATURE_SELECTION = True
USE_PACF_LAG_SELECTION = True

# Calibration
USE_PROBABILITY_CALIBRATION = True
CALIBRATION_METHOD = 'platt'
CALIBRATION_BUFFER_SIZE = 10
MIN_CALIBRATION_SAMPLES = 100

# Multi-Config Grid
CONFIG_GRID = {
    'model': ['single', 'ensemble'],
    'calibration': ['platt', 'isotonic', 'none'],
    'threshold': ['quantile_match', 'youden_j', 'class_balanced', 'fixed'],
    'auc_adjust': [True, False],
    'regime_thr': [True, False],
}

# Feature Groups
DIRECTION_FEATURE_GROUPS = {
    'top_raw': ['E10', 'M12', 'P6', 'I2', 'P1'],
    'hmm_signals': ['hmm_regime', 'hmm5_regime', ...],
    'anomaly_signals': ['HMM4_if_is_anomaly', ...],
    ...
}

# GPU Setup
def setup_gpu_params():
    if torch.cuda.is_available():
        return {'task_type': 'GPU', 'devices': '0'}, True
    return {}, False
```

---

## wf_features.py (17KB)

**Purpose:** Feature engineering functions (RSI, Dual EMA, Risk Guard).

### Functions

```python
# RSI Features
def calculate_rsi_from_returns(returns, period=14):
    """Calculate RSI using EWM method (no future leak)."""
    delta = returns.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    
    avg_gain = gain.ewm(span=period, min_periods=period).mean()
    avg_loss = loss.ewm(span=period, min_periods=period).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def create_rsi_features(df, returns_col='lagged_forward_returns', periods=[7, 14, 21, 28]):
    """Create RSI features for multiple periods."""
    feature_cols = []
    for period in periods:
        col_name = f'rsi_{period}'
        df[col_name] = calculate_rsi_from_returns(df[returns_col], period)
        feature_cols.append(col_name)
    return df, feature_cols

# Dual EMA Features
def create_dual_ema_features(df, returns_col='lagged_forward_returns', max_period=180):
    """
    Create dual EMA features: short→long vs long→short aggregation.
    Captures different temporal patterns.
    """
    feature_cols = []
    
    # Indicators to aggregate
    indicators = ['RSI', 'Volatility', 'Momentum', 'Skewness']
    
    for indicator in indicators:
        # Long-first: process 180→1
        col_long = f'{indicator}_ema_long_first'
        # Short-first: process 1→180
        col_short = f'{indicator}_ema_short_first'
        # Divergence: difference between the two
        col_div = f'{indicator}_ema_divergence'
        
        # Calculate...
        feature_cols.extend([col_long, col_short, col_div])
    
    return df, feature_cols

# Risk Guard Features
def create_risk_guard_features(df):
    """Create risk guard score from multiple signals."""
    df['risk_guard_score'] = (
        (df.get('high_vol_regime', 0) == 1).astype(float) * 0.3 +
        (df.get('hmm_regime', 0) == 2).astype(float) * 0.2 +
        (df.get('V_hmm_transitions_5d', 0) >= 2).astype(float) * 0.2 +
        (df.get('V_hmm_stable_5d', 1) == 0).astype(float) * 0.2 +
        (df.get('cusum_days_since_changepoint', 100) < 10).astype(float) * 0.1
    )
    return df, ['risk_guard_score']
```

---

## wf_functions.py (19KB)

**Purpose:** Utility functions for calibration, thresholds, etc.

### Functions

```python
def compute_brier_score(probs, labels):
    """Mean squared error of probabilities."""
    return np.mean((probs - labels) ** 2)

def compute_ece(probs, labels, n_bins=10):
    """Expected Calibration Error."""
    ...

def calculate_scale_pos_weight(y):
    """Calculate class imbalance weight for boosting."""
    neg = (y == 0).sum()
    pos = (y == 1).sum()
    return neg / pos if pos > 0 else 1.0

def calculate_half_life_weights(n_samples, half_life=50):
    """Exponential decay weights with half-life."""
    decay_rate = np.log(2) / half_life
    weights = np.exp(-decay_rate * np.arange(n_samples)[::-1])
    return weights / weights.max()

def calibrate_probabilities_adaptive(probs, labels, method='platt'):
    """Fit calibrator and return calibrated probabilities."""
    if method == 'platt':
        calibrator = LogisticRegression(C=1e10)
        calibrator.fit(probs.reshape(-1, 1), labels)
        return calibrator.predict_proba(probs.reshape(-1, 1))[:, 1]
    elif method == 'isotonic':
        calibrator = IsotonicRegression(out_of_bounds='clip')
        calibrator.fit(probs, labels)
        return calibrator.predict(probs)

def calculate_optimal_threshold(probs_or_history, labels=None, method='quantile_match', 
                                regime_pos_rate=None):
    """Calculate optimal threshold using specified method."""
    if method == 'quantile_match':
        pos_rate = regime_pos_rate or labels.mean()
        return np.percentile(probs, (1 - pos_rate) * 100)
    elif method == 'youden_j':
        fpr, tpr, thresholds = roc_curve(labels, probs)
        j = tpr - fpr
        return thresholds[np.argmax(j)]
    elif method == 'class_balanced':
        return labels.mean()
    else:
        return 0.5

def select_top_features(model, feature_cols, percent=40):
    """Select top features by importance."""
    importances = model.get_feature_importance()
    n_keep = int(len(feature_cols) * percent / 100)
    top_idx = np.argsort(importances)[::-1][:n_keep]
    return [feature_cols[i] for i in top_idx]
```

---

## wf_optuna.py (29KB)

**Purpose:** Optuna hyperparameter tuning.

### Functions

```python
def run_optuna_tuning(X_train, y_train, X_val, y_val, 
                      timeout_sec=60, gpu_params=None, gap_size=None, verbose=True):
    """
    Run Optuna tuning for both CatBoost and LightGBM.
    Returns best params for both.
    """
    # CatBoost objective
    def catboost_objective(trial):
        params = {
            'num_leaves': trial.suggest_int('num_leaves', 16, 64),
            'max_depth': trial.suggest_int('max_depth', 4, 12),
            'learning_rate': trial.suggest_float('learning_rate', 0.005, 0.05, log=True),
            ...
        }
        model = CatBoostClassifier(**params, **gpu_params)
        model.fit(X_train, y_train, eval_set=(X_val, y_val), verbose=False)
        return roc_auc_score(y_val, model.predict_proba(X_val)[:, 1])
    
    # LightGBM objective
    def lightgbm_objective(trial):
        ...
    
    # Run studies
    cb_study = optuna.create_study(direction='maximize')
    cb_study.optimize(catboost_objective, timeout=timeout_sec/2)
    
    lgb_study = optuna.create_study(direction='maximize')
    lgb_study.optimize(lightgbm_objective, timeout=timeout_sec/2)
    
    return {
        'best_cb_params': cb_study.best_params,
        'best_cb_score': cb_study.best_value,
        'best_lgb_params': lgb_study.best_params,
        'best_lgb_score': lgb_study.best_value,
    }

def calculate_optuna_search_space(n_samples, n_features):
    """Estimate search space bounds based on data size."""
    ...

def analyze_dataset_and_estimate_ranges(X, y):
    """Analyze dataset to suggest hyperparameter ranges."""
    ...
```

---

## wf_adaptive_scorer.py (67KB)

**Purpose:** Multi-period performance scoring with EMA smoothing.

### Class

```python
class AdaptiveMultiPeriodScorerV3:
    """
    Track config performance across multiple time periods.
    Uses EMA smoothing for momentum signals.
    """
    def __init__(self, min_samples_per_window=3, switch_threshold=0.20, ...):
        self.config_data = {}
        self.current_config = None
        self.switch_history = []
        self.actual_ratio_history = []
        self.lt_ema_span = 30
        self.st_ema_span = 7
    
    def update(self, config_name, iteration, tp, fp, tn, fn):
        """Update config with new outcome."""
        ...
    
    def get_composite_score(self, config_name, iteration):
        """Calculate composite score from multiple signals."""
        ...
    
    def select_best_config(self, iteration):
        """Select config with highest score."""
        ...
    
    def select_regime_adapted_config(self, iteration, market_ratio, n_top=5):
        """Select config based on current market regime."""
        ...
    
    def get_top_configs(self, iteration, n=10):
        """Get top N configs by score."""
        ...
    
    def get_state(self):
        """Serialize state for checkpoint."""
        ...
    
    def restore_state(self, state, rebase_to_zero=False):
        """Restore state from checkpoint."""
        ...
```

---

## wf_stable_ensemble.py (24KB)

**Purpose:** Ensemble of stable configs for signal calculation.

### Class

```python
class StableConfigEnsemble:
    """
    Combine signals from multiple stable configs.
    """
    def __init__(self, config_scorer, min_ratio=1.05, n_configs=10, ...):
        self.config_scorer = config_scorer
        self.min_ratio = min_ratio
        self.n_configs = n_configs
    
    def get_stable_configs(self, iteration):
        """Get configs meeting stability criteria."""
        ...
    
    def calculate_ensemble_signal(self, config_probs, iteration, ...):
        """Calculate weighted ensemble signal."""
        ...
    
    def calculate_benchmark_signal(self, probability, threshold, ...):
        """Calculate simple gates-only signal."""
        ...
    
    def calculate_position_size_baseline(self, probability, threshold, ...):
        """Calculate signal with gates + EMA scaling."""
        ...
    
    def get_position_recommendation(self, signal):
        """Convert signal to human-readable recommendation."""
        ...
```

---

## wf_hull_scorer.py (7KB)

**Purpose:** Hull-based performance scoring.

### Class

```python
class HullScorer:
    """
    Track strategy performance using Hull-style scoring.
    Based on Sharpe ratio of position-weighted returns.
    """
    def __init__(self, min_samples=60, rolling_window=180):
        self.history = []
        self.min_samples = min_samples
        self.rolling_window = rolling_window
    
    def update(self, position, market_return, risk_free_rate):
        """Add new observation."""
        strategy_return = position * market_return
        excess_return = strategy_return - risk_free_rate
        self.history.append({
            'position': position,
            'market_return': market_return,
            'strategy_return': strategy_return,
            'excess_return': excess_return,
        })
    
    def get_score(self):
        """Calculate Hull score (Sharpe-based)."""
        if len(self.history) < self.min_samples:
            return np.nan, {}
        
        recent = self.history[-self.rolling_window:]
        excess_returns = [h['excess_return'] for h in recent]
        
        sharpe = np.mean(excess_returns) / np.std(excess_returns) if np.std(excess_returns) > 0 else 0
        
        return sharpe, {
            'sharpe': sharpe,
            'avg_position': np.mean([h['position'] for h in recent]),
            'avg_return': np.mean([h['strategy_return'] for h in recent]),
        }
```

---

## wf_analysis.py (44KB)

**Purpose:** Post-run analysis and reporting.

### Function

```python
def run_all_analysis(config_results, config_scorer, walkforward_prediction_df, 
                     walkforward_iteration_df, **kwargs):
    """
    Run comprehensive post-run analysis.
    Generates summaries, plots, and metrics.
    """
    # Multi-config summary
    print_config_summary(config_results, config_scorer)
    
    # Performance metrics
    calculate_overall_metrics(walkforward_prediction_df)
    
    # Hull score analysis
    analyze_hull_scores(kwargs['hull_scorer_benchmark'], kwargs['hull_scorer_baseline'])
    
    # Drift analysis
    if kwargs['drift_alerts']:
        analyze_drift_events(kwargs['drift_alerts'])
    
    # Calibration analysis
    analyze_calibration_quality(kwargs['calibration_diagnostics'])
    
    # Model diversity analysis
    analyze_model_diversity(kwargs['model_diversity_metrics'])
```

---

## Other Modules

### wf_rolling_cal_buffer.py (2KB)
Rolling buffer for calibration data accumulation.

### wf_rolling_meta_buffer.py (2KB)
Rolling buffer for meta-stacker training data.

### wf_config_history.py (2KB)
Config history tracking (V3 format).

### wf_config_voting.py (24KB)
Voting system for config selection based on roles.

### wf_model_cache.py (19KB)
Caching for trained models to speed up iterations.

### wf_fast_predictions.py (17KB)
Utilities for fast batch predictions.

### window_diagnostics.py
Window size calculations based on data characteristics.

### signal_aggregator.py
Combine multiple weak signals into stronger features.

---

## Module Dependencies

```
sliding_window_evidence_based56.py
│
├── wf_config.py ────────────────────┐
│                                     │
├── wf_features.py                    │
│   └── [no dependencies]             │
│                                     │
├── wf_functions.py                   │
│   └── sklearn, numpy                │
│                                     │
├── wf_optuna.py                      │
│   └── optuna, catboost, lightgbm    │
│                                     │
├── wf_adaptive_scorer.py ────────────┤
│   └── numpy                         │
│                                     │
├── wf_stable_ensemble.py ────────────┤
│   └── wf_adaptive_scorer            │
│                                     │
├── wf_position_sizing_v3.py          │
│   └── numpy, dataclasses            │
│                                     │
├── wf_hull_scorer.py                 │
│   └── numpy                         │
│                                     │
├── wf_analysis.py                    │
│   └── pandas, numpy, matplotlib     │
│                                     │
├── wf_rolling_cal_buffer.py          │
├── wf_rolling_meta_buffer.py         │
├── wf_config_history.py              │
├── wf_config_voting.py               │
├── wf_model_cache.py                 │
├── wf_fast_predictions.py            │
│                                     │
├── window_diagnostics.py             │
└── signal_aggregator.py              │
```

---

*End of Walk-Forward System Documentation*
