# Part 3: Probability Calibration

## Calibration Architecture

Raw model probabilities are often poorly calibrated. The system applies **per-model calibration** using rolling buffers of past CAL window data.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CALIBRATION PIPELINE                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  [CAL Window]  →  Raw Probs  →  Calibrator  →  Calibrated Probs             │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                      ROLLING CAL BUFFER                               │   │
│  │  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐                             │   │
│  │  │Iter │ │Iter │ │Iter │ │Iter │ │Iter │  ... up to 10 windows       │   │
│  │  │ N-4 │ │ N-3 │ │ N-2 │ │ N-1 │ │ N   │                             │   │
│  │  └─────┘ └─────┘ └─────┘ └─────┘ └─────┘                             │   │
│  │                      ↓                                                │   │
│  │            Accumulated probs + labels                                 │   │
│  │                      ↓                                                │   │
│  │        ┌────────────────────────────┐                                 │   │
│  │        │  Platt (LogisticRegression) │                                │   │
│  │        │  or Isotonic Regression     │                                │   │
│  │        └────────────────────────────┘                                 │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Rolling Calibration Buffer

```python
# wf_rolling_cal_buffer.py
class RollingCalBuffer:
    """
    Accumulates calibration data from past CAL windows.
    Prevents recency bias by using multiple windows.
    """
    def __init__(self, max_windows=10, max_samples=2000):
        self.max_windows = max_windows
        self.max_samples = max_samples
        self.buffer = deque(maxlen=max_windows)
    
    def append(self, probs: np.ndarray, labels: np.ndarray):
        """Add current CAL window data."""
        self.buffer.append((probs.copy(), labels.copy()))
    
    def get_buffer(self) -> Tuple[np.ndarray, np.ndarray]:
        """Get concatenated data from all windows."""
        if len(self.buffer) == 0:
            return np.array([]), np.array([])
        
        all_probs = np.concatenate([p for p, _ in self.buffer])
        all_labels = np.concatenate([l for _, l in self.buffer])
        
        # Subsample if too large
        if len(all_probs) > self.max_samples:
            indices = np.random.choice(len(all_probs), self.max_samples, replace=False)
            all_probs = all_probs[indices]
            all_labels = all_labels[indices]
        
        return all_probs, all_labels
    
    def size(self) -> int:
        return sum(len(p) for p, _ in self.buffer)
    
    def n_windows(self) -> int:
        return len(self.buffer)
```

## Calibration Methods

### 1. Platt Scaling (Default)

```python
from sklearn.linear_model import LogisticRegression

def fit_platt_calibrator(probs, labels):
    """
    Platt scaling: fit LogisticRegression on (prob, label) pairs.
    P(y=1|prob) = sigmoid(a*prob + b)
    """
    # Reshape for sklearn
    X = probs.reshape(-1, 1)
    y = labels
    
    calibrator = LogisticRegression(
        solver='lbfgs',
        max_iter=1000,
        C=1e10,  # No regularization
    )
    calibrator.fit(X, y)
    return calibrator

def apply_calibrator(calibrator, probs):
    """Apply fitted calibrator to new probabilities."""
    X = probs.reshape(-1, 1)
    return calibrator.predict_proba(X)[:, 1]
```

### 2. Isotonic Regression

```python
from sklearn.isotonic import IsotonicRegression

def fit_isotonic_calibrator(probs, labels):
    """
    Isotonic regression: monotonic function fitting.
    Better with more data (500+ samples recommended).
    """
    calibrator = IsotonicRegression(out_of_bounds='clip')
    calibrator.fit(probs, labels)
    return calibrator

def apply_isotonic(calibrator, probs):
    return calibrator.predict(probs)
```

### Automatic Method Selection

```python
# From window_diagnostics.py
def select_calibration_method(n_samples, p_positive_rate):
    """
    Select calibration method based on sample size.
    """
    # Isotonic needs more data
    if n_samples >= MIN_SAMPLES_ISOTONIC:  # 500
        return 'isotonic'
    elif n_samples >= MIN_SAMPLES_PLATT:   # 100
        return 'platt'
    else:
        return 'none'  # Too few samples
```

## Per-Model Calibration Flow

```python
# Each model gets its own calibrator and buffer
cb_cal_buffer = RollingCalBuffer(max_windows=10, max_samples=2000)
lgb_cal_buffer = RollingCalBuffer(max_windows=10, max_samples=2000)

# In each iteration:
# 1. Get raw predictions on CAL window
cb_cal_probs = cb_model.predict_proba(X_cal)[:, 1]
lgb_cal_probs = lgb_model.predict_proba(X_cal)[:, 1]

# 2. Add to rolling buffers
cb_cal_buffer.append(cb_cal_probs, y_cal)
lgb_cal_buffer.append(lgb_cal_probs, y_cal)

# 3. Fit calibrators on accumulated data
cb_buffer_probs, cb_buffer_labels = cb_cal_buffer.get_buffer()
lgb_buffer_probs, lgb_buffer_labels = lgb_cal_buffer.get_buffer()

if len(cb_buffer_probs) >= MIN_CALIBRATION_SAMPLES:
    cb_calibrator = fit_platt_calibrator(cb_buffer_probs, cb_buffer_labels)
    lgb_calibrator = fit_platt_calibrator(lgb_buffer_probs, lgb_buffer_labels)
```

## Calibration Quality Metrics

### Brier Score

```python
def compute_brier_score(probs, labels):
    """
    Brier score: mean squared error of probabilities.
    Range: [0, 1], lower is better. Perfect calibration = 0.
    """
    return np.mean((probs - labels) ** 2)

# Decomposition
brier = compute_brier_score(cal_probs, y_cal)
```

### Expected Calibration Error (ECE)

```python
def compute_ece(probs, labels, n_bins=10):
    """
    Expected Calibration Error: weighted average of |accuracy - confidence|
    across probability bins.
    """
    bin_edges = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    
    for i in range(n_bins):
        mask = (probs >= bin_edges[i]) & (probs < bin_edges[i+1])
        if mask.sum() == 0:
            continue
        
        bin_accuracy = labels[mask].mean()
        bin_confidence = probs[mask].mean()
        bin_weight = mask.sum() / len(probs)
        
        ece += bin_weight * abs(bin_accuracy - bin_confidence)
    
    return ece
```

### Calibration Diagnostics

```python
# Logged each iteration
calibration_diagnostics.append({
    'iteration': iteration,
    'cb_brier': compute_brier_score(cb_cal_probs_cal, y_cal),
    'lgb_brier': compute_brier_score(lgb_cal_probs_cal, y_cal),
    'ensemble_brier': compute_brier_score(cal_dir_probs_calibrated, y_cal),
    'cb_ece': compute_ece(cb_cal_probs_cal, y_cal),
    'lgb_ece': compute_ece(lgb_cal_probs_cal, y_cal),
    'ensemble_ece': compute_ece(cal_dir_probs_calibrated, y_cal),
    'calibrator_type': CALIBRATION_METHOD,
    'cal_buffer_samples': cb_cal_buffer.size(),
})
```

## AUC-Confidence Threshold Adjustment

```python
# Pull threshold toward 0.5 when model confidence is low
USE_AUC_CONFIDENCE_ADJUSTMENT = True
AUC_CONFIDENCE_STRENGTH = 0.5
AUC_MIN_FOR_CONFIDENCE = 0.52

# Use ENSEMBLE VAL AUC for confidence
model_auc = ensemble_val_auc

# Calculate confidence: 0.5 AUC = 0 confidence, 1.0 AUC = 1 confidence
if model_auc <= AUC_MIN_FOR_CONFIDENCE:
    auc_confidence = 0.0
else:
    auc_confidence = min(1.0, (model_auc - 0.5) * 2)

# Uncertainty is inverse of confidence
auc_uncertainty = 1.0 - auc_confidence

# Pull threshold toward 0.5
auc_adjustment = (0.5 - optimal_threshold) * auc_uncertainty * AUC_CONFIDENCE_STRENGTH
optimal_threshold = optimal_threshold + auc_adjustment
optimal_threshold = max(0.35, min(0.75, optimal_threshold))  # Clamp
```

## Threshold Calculation Methods

### 1. Quantile Match

```python
def quantile_match_threshold(cal_probs, y_cal):
    """
    Set threshold so predicted positive rate matches CAL positive rate.
    """
    pos_rate = y_cal.mean()
    threshold = np.percentile(cal_probs, (1 - pos_rate) * 100)
    return threshold
```

### 2. Youden's J

```python
def youden_j_threshold(cal_probs, y_cal):
    """
    Maximize sensitivity + specificity - 1 (Youden's J statistic).
    """
    from sklearn.metrics import roc_curve
    fpr, tpr, thresholds = roc_curve(y_cal, cal_probs)
    j_scores = tpr - fpr
    best_idx = np.argmax(j_scores)
    return thresholds[best_idx]
```

### 3. Class Balanced

```python
def class_balanced_threshold(cal_probs, y_cal):
    """
    Use CAL positive rate as threshold (simple but effective).
    """
    return y_cal.mean()
```

### 4. Adaptive (Rolling History)

```python
def adaptive_threshold(walkforward_predictions, window=50):
    """
    Adjust threshold based on recent prediction accuracy.
    """
    if len(walkforward_predictions) < window:
        return 0.5
    
    recent = walkforward_predictions[-window:]
    # Calculate metrics and adjust...
    return adjusted_threshold
```

## Regime-Specific Threshold Adjustments

```python
# Adjust threshold based on volatility regime
REGIME_THRESHOLD_ADJUSTMENTS = {
    'HIGH_VOL': +0.05,    # More conservative in high vol
    'LOW_VOL': -0.03,     # More aggressive in low vol
    'NORMAL': 0.0,
}

if USE_REGIME_SPECIFIC_THRESHOLDS:
    vol_regime = classify_vol_regime(pred_vol)
    regime_adj = REGIME_THRESHOLD_ADJUSTMENTS.get(vol_regime, 0.0)
    optimal_threshold += regime_adj
```

## Risk Gate / Bullish Gate

```python
# Threshold gates only activate on EXTREME signals
RISK_ACTIVATION_THRESHOLD = 0.3      # Risk score >= 0.3 triggers
RISK_GATE_BOOST = 0.10               # +10% threshold boost
BULLISH_ACTIVATION_THRESHOLD = 0.9   # Bullish score >= 0.9 triggers
BULLISH_GATE_REDUCTION = 0.00        # Currently disabled

# Get scores from risk_guard_score feature
pred_risk_score = source_df.iloc[pred_start:pred_end]['risk_guard_score'].values

threshold_adjustment = 0.0
if pred_risk_score[0] >= RISK_ACTIVATION_THRESHOLD:
    threshold_adjustment += RISK_GATE_BOOST  # More conservative

if pred_bullish_score[0] >= BULLISH_ACTIVATION_THRESHOLD and pred_risk_score[0] == 0:
    threshold_adjustment -= BULLISH_GATE_REDUCTION  # More aggressive (if enabled)

optimal_threshold += threshold_adjustment
optimal_threshold = max(0.35, min(0.75, optimal_threshold))  # Clamp
```

---

*See [Part_4_Position_Sizing.md](Part_4_Position_Sizing.md) for position sizing details.*
