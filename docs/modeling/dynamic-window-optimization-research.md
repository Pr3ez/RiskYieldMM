# Dynamic Window/Split Optimization Research

## Executive Summary

**Problem:** Current backtest uses FIXED window sizes and train/val/cal split ratios per model.
**Goal:** Make these ADAPTIVE to target type, data regime, and available data without future leakage.

---

## Current Fixed Configuration

| Model | Window | Train/Val/Cal | Feature Selection |
|-------|--------|---------------|-------------------|
| CatBoost | 400 | 60/20/20 | importance 60% |
| LightGBM | 400 | 60/20/20 | importance 60% |
| LSTM | 600 | 70/15/15 | variance 80% |
| Linear | 800 | 50/20/30 | icir 50% |

**Issues:**
1. Window size doesn't adapt to data regime (trending vs ranging)
2. Split ratios don't adapt to target difficulty/signal strength
3. Calibration may need more/less data depending on prediction task
4. No consideration of stationarity changes over time

---

## No-Leakage Constraint

**CRITICAL:** Any adaptive method MUST only use data BEFORE the prediction point.

Available at prediction time `t`:
- `X_full[:t]` - All features up to (but not including) t
- `y_full[:t]` - All targets up to (but not including) t
- `previous_best_params` - What worked in the last step

**FORBIDDEN:**
- Looking at future data for window selection
- Using test performance to select training window
- Any form of peeking at `X_full[t:]` or `y_full[t:]`

---

## Research: Per-Model Adaptive Methods

### 1. CatBoost / LightGBM (Tree Models)

#### A. Window Size Optimization

**Method 1: Nested Walk-Forward Validation**
```
For each candidate window_size in [200, 300, 400, 500, 600]:
    - Take oldest 20% of available data as "holdout"
    - Train on window_size bars BEFORE holdout
    - Validate on holdout
    - Record holdout performance
Select window_size with best holdout performance
```

**Pros:** Directly measures what we care about
**Cons:** Computationally expensive (5x training per step)

**Method 2: Early Stopping Ratio**
```
Train with early stopping enabled
ratio = best_iteration / max_iterations
if ratio > 0.9:  # Used most iterations
    → Data might be too limited, consider larger window
if ratio < 0.3:  # Stopped very early
    → Data might be noisy/non-stationary, consider smaller window
```

**Pros:** Free signal from training process
**Cons:** Heuristic, needs calibration

**Method 3: Stationarity-Based Window**
```
For window_size starting from max, decreasing:
    - Run ADF test on target in window
    - If stationary (p < 0.05), use this window
    - Else reduce window
```

**Pros:** Theoretically motivated
**Cons:** ADF test on short windows unreliable

**Method 4: Cross-Validation Score Stability**
```
Using TimeSeriesSplit with 3-5 folds on available data:
    - Compute CV score variance for each window_size
    - Smaller variance → more stable predictions
Select window with lowest CV variance AND acceptable mean score
```

**Pros:** Measures consistency
**Cons:** Still requires multiple training runs

#### B. Train/Val/Cal Split Optimization

**Current:** Fixed 60/20/20

**Adaptive Approach:**
```python
def optimize_splits(X_train, y_train, task_type):
    if task_type == 'regression':
        # Regression needs larger validation for reliable MSE
        return {'train': 0.60, 'val': 0.25, 'cal': 0.15}
    
    n_classes = len(np.unique(y_train))
    class_min = min(np.bincount(y_train))
    
    if class_min < 30:
        # Imbalanced: need more training data
        return {'train': 0.70, 'val': 0.15, 'cal': 0.15}
    
    # Check prediction difficulty
    baseline_acc = 1.0 / n_classes  # Random baseline
    # If target is easy, can afford smaller train
    # If target is hard, need more calibration for uncertainty
    
    return {'train': 0.55, 'val': 0.20, 'cal': 0.25}
```

**Key Considerations:**
- **Calibration size:** Larger for conformal prediction, especially with small test sets
- **Validation size:** Larger for early stopping reliability
- **Training size:** Larger when signal is weak

---

### 2. LSTM (Sequence Model)

#### A. Sequence Length (Lookback) Optimization

**LSTM is Different:** Lookback affects the MODEL ARCHITECTURE, not just data quantity.

**Method 1: Partial Autocorrelation Analysis**
```python
from statsmodels.tsa.stattools import pacf

def suggest_lookback(target_series, max_lag=100):
    """Use PACF to determine relevant lookback."""
    pacf_values = pacf(target_series, nlags=max_lag)
    
    # Find where PACF becomes insignificant (< 0.05)
    significant_lags = np.where(np.abs(pacf_values) > 0.05)[0]
    
    if len(significant_lags) > 0:
        suggested = max(significant_lags) + 1
    else:
        suggested = 20  # default
    
    return min(suggested, max_lag)
```

**Pros:** Data-driven, theoretically motivated
**Cons:** PACF assumes linear relationships

**Method 2: Validation Loss by Lookback**
```python
for lookback in [10, 20, 30, 50, 75, 100]:
    # Split data: train | validation
    model = build_lstm(lookback=lookback)
    model.fit(train_sequences)
    val_loss = model.evaluate(val_sequences)
    record(lookback, val_loss)
    
# Select lookback with best validation loss
```

**Pros:** Direct optimization of what we care about
**Cons:** Expensive - need to train multiple models

**Method 3: Information-Theoretic**
```
Compute mutual information between:
    - Target at t+h
    - Features at t, t-1, t-2, ..., t-k for various k

Where MI starts dropping off → that's the useful lookback
```

**Pros:** Measures actual information content
**Cons:** MI estimation on continuous variables is noisy

#### B. Window Size for Training Data

Separate from lookback:
- **Lookback:** How many past timesteps LSTM sees per prediction
- **Window:** How many training examples to create

**Recommendation:**
```python
def lstm_window_size(lookback, target_complexity):
    # Need at least 50-100 examples per class for stable training
    min_examples_per_class = 100
    n_classes = 3  # typical
    
    min_window = lookback + min_examples_per_class * n_classes
    
    # Adjust for target complexity
    if target_complexity == 'high':
        return min_window * 1.5
    return min_window
```

---

### 3. Linear (Ridge/Logistic)

#### A. Window Size vs Regularization Tradeoff

**Key Insight:** Linear models have a DIRECT tradeoff:
- Small window → High variance → Need STRONG regularization
- Large window → May include stale data → Need WEAK regularization

**Method 1: Condition Number Monitoring**
```python
from numpy.linalg import cond

def assess_linear_health(X):
    """Check if linear regression will be stable."""
    condition = cond(X.T @ X)
    
    if condition > 1e10:
        return 'ill-conditioned'  # Need more regularization
    elif condition < 1e3:
        return 'well-conditioned'  # Can reduce regularization
    return 'normal'
```

**Method 2: Joint Optimization of Window + Alpha**
```python
from sklearn.linear_model import RidgeClassifierCV

def optimize_linear_config(X_full, y_full, max_window=800):
    best_score = -np.inf
    best_config = None
    
    for window in [400, 500, 600, 700, 800]:
        X_train = X_full[-window:]
        y_train = y_full[-window:]
        
        # Let RidgeCV find best alpha for this window
        model = RidgeClassifierCV(alphas=[0.1, 1.0, 10.0, 100.0], cv=5)
        model.fit(X_train, y_train)
        score = model.best_score_
        
        if score > best_score:
            best_score = score
            best_config = {'window': window, 'alpha': model.alpha_}
    
    return best_config
```

**Pros:** Direct optimization
**Cons:** Linear CV is fast, but still O(n_windows) overhead

#### B. Feature Stability Check

```python
def check_feature_stability(X, window_sizes=[400, 600, 800]):
    """Check if feature relationships are stable across windows."""
    correlations = []
    
    for w in window_sizes:
        X_window = X[-w:]
        corr_matrix = np.corrcoef(X_window.T)
        correlations.append(corr_matrix)
    
    # Compare correlation matrices
    stability_score = 0
    for i in range(len(correlations)-1):
        diff = np.abs(correlations[i] - correlations[i+1])
        stability_score += np.mean(diff)
    
    return stability_score / (len(window_sizes) - 1)
```

If features unstable: prefer smaller window (more recent data)
If features stable: prefer larger window (more training examples)

---

## Implementation Architecture

### Option A: Centralized Analysis Function

```python
# In core/features.py or new core/adaptive.py

def analyze_optimal_config(
    X_full: np.ndarray,
    y_full: np.ndarray,
    model_type: str,
    task_type: str,
    max_window: int = 800
) -> Dict[str, Any]:
    """
    Analyze available data to suggest optimal configuration.
    
    CRITICAL: Uses only X_full[:t] and y_full[:t] where t is last available.
    No future leakage.
    
    Returns:
        {
            'window_size': int,
            'train_ratio': float,
            'val_ratio': float,
            'cal_ratio': float,
            'confidence': float,  # How confident in suggestion
            'reasoning': str      # Why these values
        }
    """
    ...
```

### Option B: Per-Model Adaptive Methods

```python
# In each model module

def optimize_catboost_config(X_full, y_full, task_type, prev_config):
    """CatBoost-specific optimization using early stopping signals."""
    ...

def optimize_lstm_config(X_full, y_full, task_type, prev_config):
    """LSTM-specific optimization using PACF for lookback."""
    ...

def optimize_linear_config(X_full, y_full, task_type, prev_config):
    """Linear-specific joint window+alpha optimization."""
    ...
```

### Option C: Bayesian Approach (Most Sophisticated)

Track performance over time, use Bayesian updating:
```python
# Prior: Current fixed configs
# Likelihood: Performance on recent predictions
# Posterior: Updated belief about optimal config

from scipy.stats import beta

class AdaptiveConfigTracker:
    def __init__(self, model_type, initial_config):
        self.prior = initial_config
        self.performance_history = []
    
    def update(self, config_used, performance):
        self.performance_history.append((config_used, performance))
        # Update posterior based on recent performance
        self.posterior = self._bayesian_update()
    
    def suggest_config(self):
        # Sample from posterior or return MAP estimate
        return self.posterior
```

---

## Recommended Implementation Plan

### Phase 1: Infrastructure (1 day)
1. Create `core/adaptive.py` with base analysis functions
2. Add `config_mode: Literal['fixed', 'adaptive']` to `SyncBacktestConfig`
3. Modify `_get_model_configs()` to call adaptive analysis when enabled

### Phase 2: CatBoost/LightGBM (2 days)
1. Implement early-stopping ratio heuristic (cheap signal)
2. Implement nested walk-forward for window optimization (optional, expensive)
3. Test on one target type (direction)

### Phase 3: LSTM (2 days)
1. Implement PACF-based lookback suggestion
2. Connect lookback to sequence length in model building
3. Test with trend_regime target

### Phase 4: Linear (1 day)
1. Implement joint window+alpha optimization via CV
2. Add condition number monitoring
3. Test with volatility target

### Phase 5: Integration & Validation (2 days)
1. Run full backtest with adaptive configs
2. Compare performance vs fixed configs
3. Ensure no regression in metrics
4. Validate no future leakage via walk-forward analysis

---

## Open Questions for Przem

1. **Computation budget:** How much extra time per step is acceptable?
   - Option A: ~0 extra (use free signals like early stopping ratio)
   - Option B: ~1-2x extra (limited nested CV)
   - Option C: ~5x extra (full window search)

2. **Adaptation frequency:**
   - Every step? (most responsive, most expensive)
   - Every N steps? (amortized cost)
   - Only when detecting regime change?

3. **Fallback strategy:**
   - If adaptive method fails (no clear winner), use fixed defaults?
   - Use previous step's config?
   - Weighted average?

4. **Priority of models:**
   - Start with which model first?
   - CatBoost (most used) → LightGBM → Linear → LSTM?

---

## References

- CatBoost Cross-Validation: https://catboost.ai/docs/en/features/cross-validation
- Walk-Forward Validation: https://www.emergentmind.com/topics/walk-forward-validation-strategy
- LSTM Lookback Impact: diva-portal.org paper on sequence length
- Ridge Regression Bias-Variance: Ruoqing Zhu lecture notes

---

*Document created: 2025-01-19*
*Status: Research complete, awaiting implementation decisions*
