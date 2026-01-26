# CatBoost Dynamic Configuration Research

**Status:** 📋 RESEARCH IN PROGRESS  
**Created:** 2026-01-19  
**Author:** Astra  

---

## 1. What We Currently Have

### 1.1 CatBoostModelConfig (Current Parameters)

**File:** `models/catboost_model.py` lines 56-95

```python
@dataclass
class CatBoostModelConfig(ModelConfig):
    # === CatBoost Hyperparameters ===
    n_estimators: int = 100      # iterations
    max_depth: int = 6           # arXiv 2305.17094: depth 6 often optimal
    learning_rate: float = 0.03  # Conservative for stability
    l2_leaf_reg: float = 5.0     # Increased regularization

    # === GPU Settings ===
    use_gpu: bool = True
    gpu_device: str = "0"

    # === Optuna Tuning ===
    enable_tuning: bool = True
    n_optuna_trials: int = 15
    optuna_timeout: float | None = 30.0  # seconds

    # === Window/Split Configuration (from ModelConfig) ===
    train_window: int = 400      # ← TO OPTIMIZE
    train_ratio: float = 0.60    # ← TO OPTIMIZE
    val_ratio: float = 0.20      # ← TO OPTIMIZE
    cal_ratio: float = 0.20      # ← TO OPTIMIZE (computed)
    embargo_bars: int = 24       # Dynamic: min(3*horizon, 36)
    
    # === Feature Selection ===
    feature_selection: str = "importance"
    feature_selection_ratio: float = 0.6  # ← TO OPTIMIZE
    min_features: int = 30
```

### 1.2 Current Optimizer Stub

**File:** `models/catboost_model.py` lines 102-135

```python
def optimize_catboost_config(
    X_full: pd.DataFrame,
    y_full: pd.Series,
    target_name: str,
    task_type: str = "classification",
    base_config: CatBoostModelConfig | None = None,
) -> CatBoostModelConfig:
    """Optimize CatBoost config based on data characteristics.

    TODO: Implement data-driven optimization logic:
    - Analyze stationarity to determine optimal train_window
    - Check class balance for train/val/cal ratios
    - Assess feature stability for feature_selection_ratio
    """
    # PLACEHOLDER: Returns baseline config
    if base_config is not None:
        return base_config
    return CatBoostModelConfig(train_window=400, ...)
```

### 1.3 Where Configs Are Used

| Location | What Happens |
|----------|--------------|
| `services/training.py:_get_model_configs()` | Creates CatBoostModelConfig with baseline values |
| `services/training.py:train_predict_classification_permodel()` | Calls `extract_per_model_splits()` with config |
| `core/features.py:extract_per_model_splits()` | Uses `config.train_window`, `config.train_ratio`, etc. |
| `models/catboost_model.py:train_and_predict_classifier()` | Uses config for training hyperparameters |

### 1.4 Current Optuna Search Space

**File:** `models/catboost_model.py` lines 150-195

```python
def tune_catboost_classifier(...):
    """Optuna hyperparameter search."""
    def objective(trial):
        params = {
            "iterations": trial.suggest_int("iterations", 50, 300),
            "depth": trial.suggest_int("depth", 3, 8),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "l2_leaf_reg": trial.suggest_float("l2_leaf_reg", 1.0, 10.0),
        }
```

**Currently Tuned:** iterations, depth, learning_rate, l2_leaf_reg  
**NOT Tuned:** train_window, split ratios, feature_selection_ratio

---

## 2. What We Need to Optimize

### 2.1 Primary Optimization Targets

| Parameter | Current | Range to Explore | Why Optimize |
|-----------|---------|------------------|--------------|
| `train_window` | 400 | 200-800 | Regime changes may need different history |
| `train_ratio` | 0.60 | 0.50-0.70 | Class balance may need more/less train |
| `val_ratio` | 0.20 | 0.15-0.25 | Tuning stability |
| `cal_ratio` | 0.20 | 0.15-0.30 | Conformal calibration quality |
| `feature_selection_ratio` | 0.60 | 0.40-0.80 | Feature stability varies |

### 2.2 Secondary (Hyperparameter) Targets

Already tuned via Optuna, but could be co-optimized:
- `n_estimators` (iterations)
- `max_depth`
- `learning_rate`
- `l2_leaf_reg`

### 2.3 Constraints (NO LEAKAGE)

**CRITICAL:** All optimization MUST use only historical data.

```
Available at prediction step t:
├── X_full[0:t-1]     → Features BEFORE prediction point
├── y_full[0:t-1]     → Targets BEFORE prediction point
└── X_pred[t]         → Feature row TO PREDICT (no target)

FORBIDDEN:
├── y_pred[t]         → The answer we're trying to predict
└── Any future data   → t+1, t+2, etc.
```

---

## 3. Data Available for Optimization

At each prediction step, `optimize_catboost_config()` receives:

```python
def optimize_catboost_config(
    X_full: pd.DataFrame,    # Shape: (800, ~265 features) - historical only
    y_full: pd.Series,       # Shape: (800,) - targets for historical data
    target_name: str,        # e.g., "direction_1bar", "volatility_6bar"
    task_type: str,          # "classification" or "regression"
    base_config: CatBoostModelConfig | None,
) -> CatBoostModelConfig:
```

### 3.1 What We Can Analyze

| Analysis | Data Source | What It Tells Us |
|----------|-------------|------------------|
| **Stationarity** | `X_full`, `y_full` | Is recent data similar to older data? |
| **Class Balance** | `y_full` | Are classes evenly distributed? |
| **Regime Detection** | `X_full` volatility patterns | Trending vs ranging market |
| **Feature Stability** | `X_full` rolling correlations | Which features are stable? |
| **Target Difficulty** | `y_full` autocorrelation | How predictable is the target? |

### 3.2 Window Analysis Possibilities

```python
# Example: Stationarity check
from scipy.stats import ks_2samp

def check_stationarity(y_full, window_sizes=[200, 400, 600]):
    """Check if older data is similar to recent data."""
    recent = y_full[-100:]  # Last 100 bars
    results = {}
    for ws in window_sizes:
        old = y_full[-(ws+100):-100]  # Older portion
        stat, p_value = ks_2samp(old, recent)
        results[ws] = {"ks_stat": stat, "p_value": p_value}
    return results
```

---

## 4. Research Questions

### 4.1 Train Window Size

**Question:** How do we determine optimal window size?

**Approaches to Research:**
1. **Stationarity-based:** Use ADF test on different window sizes
2. **Regime-based:** Detect regime changes, use data from current regime only
3. **Error-based:** Historical holdout test (oldest 100 bars as "test")
4. **Adaptive:** Start with baseline, adjust based on recent performance

**CatBoost-Specific Considerations:**
- Tree models handle non-stationarity better than linear models
- But overly old data can still hurt
- Early stopping provides some automatic adaptation

### 4.2 Split Ratios

**Question:** How do we balance train/val/cal splits?

**Approaches:**
1. **Class-balance based:** More train if class imbalance exists
2. **Difficulty-based:** More val/cal if target is hard to predict
3. **Conformal-quality based:** More cal if prediction sets are too wide

**CatBoost-Specific:**
- Optuna needs sufficient val for hyperparameter tuning
- Conformal prediction quality depends on cal size
- CatBoost handles small datasets well (regularization helps)

### 4.3 Feature Selection Ratio

**Question:** How many features to keep?

**Approaches:**
1. **Stability-based:** Keep features with stable importance across windows
2. **Correlation-based:** Remove highly correlated features
3. **Importance-threshold:** Keep features above certain importance

**Current:** Uses importance-based selection with ratio=0.60

---

## 5. Potential Implementation Approaches

### 5.1 Approach A: Simple Heuristics

```python
def optimize_catboost_config(...) -> CatBoostModelConfig:
    # Analyze data
    class_balance = y_full.value_counts(normalize=True).min()
    volatility = X_full.std().mean()
    
    # Simple rules
    if class_balance < 0.25:  # Imbalanced
        train_ratio = 0.65    # More train data
    else:
        train_ratio = 0.55
    
    if volatility > threshold:  # High volatility regime
        train_window = 300    # Less history (focus on recent)
    else:
        train_window = 500    # More history
    
    return CatBoostModelConfig(...)
```

**Pros:** Fast, interpretable, no additional compute  
**Cons:** May miss complex patterns, requires manual tuning of thresholds

### 5.2 Approach B: Holdout Validation

```python
def optimize_catboost_config(...) -> CatBoostModelConfig:
    # Use oldest 100 bars as holdout
    X_holdout = X_full[:100]
    y_holdout = y_full[:100]
    X_train_opt = X_full[100:]
    y_train_opt = y_full[100:]
    
    # Test different window sizes on holdout
    best_window = 400
    best_score = 0
    for window in [200, 300, 400, 500, 600]:
        score = quick_train_test(X_train_opt[-window:], y_train_opt[-window:], 
                                  X_holdout, y_holdout)
        if score > best_score:
            best_window = window
            best_score = score
    
    return CatBoostModelConfig(train_window=best_window, ...)
```

**Pros:** Data-driven, adapts to actual performance  
**Cons:** Expensive (multiple training runs), uses up data for holdout

### 5.3 Approach C: Meta-Learning

```python
def optimize_catboost_config(...) -> CatBoostModelConfig:
    # Extract meta-features from data
    meta_features = {
        "class_balance": compute_class_balance(y_full),
        "stationarity": compute_adf_statistic(y_full),
        "volatility": compute_volatility(X_full),
        "autocorrelation": compute_autocorr(y_full),
    }
    
    # Pre-trained meta-model predicts best config
    predicted_config = meta_model.predict(meta_features)
    
    return CatBoostModelConfig(**predicted_config)
```

**Pros:** Can learn complex relationships  
**Cons:** Requires pre-training meta-model, risk of overfitting meta-model

### 5.4 Approach D: Bayesian Optimization

```python
def optimize_catboost_config(...) -> CatBoostModelConfig:
    # Optuna for config optimization (separate from hyperparameter tuning)
    def config_objective(trial):
        window = trial.suggest_int("train_window", 200, 600)
        train_ratio = trial.suggest_float("train_ratio", 0.50, 0.70)
        # Quick validation on holdout
        return quick_validate(window, train_ratio, ...)
    
    study = optuna.create_study(direction="maximize")
    study.optimize(config_objective, n_trials=10, timeout=30)
    
    return CatBoostModelConfig(**study.best_params)
```

**Pros:** Systematic exploration, handles interactions  
**Cons:** Expensive, may overfit to specific step

---

## 6. CatBoost-Specific Research

### 6.1 CatBoost Early Stopping as Proxy

CatBoost has built-in early stopping. Could use this as a signal:

```python
# If early stopping triggers very early → data quality issue
# If early stopping never triggers → could use more data

model.fit(X_train, y_train, 
          eval_set=(X_val, y_val),
          early_stopping_rounds=50)

best_iteration = model.get_best_iteration()
# If best_iteration < 50: reduce complexity
# If best_iteration == max_iterations: could benefit from more data
```

### 6.2 CatBoost Feature Importance Stability

```python
# Train multiple quick models on different windows
# Keep features that are important across all windows

importance_lists = []
for window in [200, 400, 600]:
    quick_model = train_quick(X_full[-window:], y_full[-window:])
    importance_lists.append(quick_model.get_feature_importance())

# Features important in ALL windows are stable
stable_features = identify_stable_features(importance_lists)
```

### 6.3 CatBoost Regularization vs Window Size

**Hypothesis:** With more regularization, can use larger windows (older data doesn't hurt as much).

```python
# If using high l2_leaf_reg: larger window OK
# If using low l2_leaf_reg: need smaller, more recent window

if l2_leaf_reg > 5.0:
    window_range = (400, 800)
else:
    window_range = (200, 500)
```

---

## 7. TODO List for Implementation

### Phase 1: Data Analysis Functions

- [ ] `analyze_class_balance(y_full)` → class distribution stats
- [ ] `analyze_stationarity(y_full, X_full)` → ADF test, rolling stats
- [ ] `analyze_volatility_regime(X_full)` → high/medium/low volatility
- [ ] `analyze_feature_stability(X_full, y_full)` → rolling importance

### Phase 2: Optimization Logic

- [ ] Define heuristic rules for window size
- [ ] Define heuristic rules for split ratios
- [ ] Define heuristic rules for feature selection ratio
- [ ] Test on historical data (no leakage!)

### Phase 3: Integration

- [ ] Implement `optimize_catboost_config()` with analysis functions
- [ ] Wire into `services/training.py` 
- [ ] Add logging/tracking of optimization decisions
- [ ] Validate no leakage

### Phase 4: Evaluation

- [ ] Compare fixed vs dynamic configs on backtest
- [ ] Measure computational overhead
- [ ] Check if improvements are consistent across targets

---

## 8. Official CatBoost Documentation Findings

### 8.1 Overfitting Detection (catboost.ai)

**Key Parameters:**

| Parameter | Type | Description | Recommendation |
|-----------|------|-------------|----------------|
| `early_stopping_rounds` | int | Stops after N iterations since optimal metric | Use with `use_best_model=True` |
| `od_type` | str | "IncToDec" (p-value) or "Iter" (count) | "Iter" is simpler, "IncToDec" more sophisticated |
| `od_pval` | float | P-value threshold for IncToDec | Range: 10^-10 to 10^-2 |
| `od_wait` | int | Iterations after optimal before stopping | Default: 20 |
| `use_best_model` | bool | Return model at best iteration | **Always True for time-series** |

**Implementation Pattern:**
```python
model = CatBoostClassifier(
    iterations=1000,           # Set high, let early stopping find optimal
    early_stopping_rounds=50,  # Stop after 50 rounds of no improvement
    use_best_model=True,       # Return model at best iteration
    od_type='Iter',            # Simple overfitting detector
    verbose=False
)
model.fit(X_train, y_train, eval_set=(X_val, y_val))
optimal_iterations = model.get_best_iteration()
```

**Insight for Dynamic Config:**
- `get_best_iteration()` value signals data quality/sufficiency
- If optimal_iterations < 50: reduce complexity OR data has noise
- If optimal_iterations == max_iterations: could benefit from more data

### 8.2 Parameter Tuning Guide (catboost.ai)

**Official Recommendations:**

| Parameter | Range | Notes |
|-----------|-------|-------|
| `depth` | 4-10 | **Recommended: 6-10**. Max 8 for pairwise modes on GPU |
| `learning_rate` | auto | Auto-defined by default. Increase if no overfitting, decrease if overfitting |
| `l2_leaf_reg` | varies | Try different values. Higher = more regularization |
| `border_count` | 254/128 | 254 for best quality, 128 for fast GPU |
| `bagging_temperature` | varies | Try different values for regularization |
| `random_strength` | varies | Try different values |

**Golden Features Insight:**
- For strong predictor features, use 1024 borders instead of 254
- Can identify "golden features" from importance analysis

**Optuna Integration:**
- CatBoost officially supports Optuna pruning callbacks
- Can prune unpromising trials early during hyperparameter search

### 8.3 Time-Series Specific Guidance

From CatBoost best practices for time-series:

1. **Train-Test Split:** MUST be chronological (never shuffle)
2. **Lag Features:** Create explicit lag features; CatBoost doesn't auto-detect temporal order
3. **Seasonal Features:** Extract day-of-week, month, hour as categorical
4. **Rolling Statistics:** Moving averages, rolling sums as features
5. **Monotonicity Constraints:** If known trend exists, can enforce in model

**Overfitting Risk Factors in Time-Series:**
- Small datasets → use higher regularization
- Noise/seasonal fluctuations → adjust l2_leaf_reg
- Non-stationarity → focus on recent data (smaller window)

---

## 9. Scientific Research Findings

### 9.1 Training Window Selection Methods

**Paper:** "Comparing training window selection methods for prediction in non-stationary time series"  
*Petersen, Haslbeck, Tendeiro - British Journal of Mathematical and Statistical Psychology*

**Key Methods Identified:**

| Method | Description | Pros | Cons |
|--------|-------------|------|------|
| **Sliding Window** | Fixed-size window moves forward | Constant complexity | May miss long-term patterns |
| **Expanding Window** | Uses all historical data | Captures all history | May include irrelevant old data |
| **Regime-Based** | Uses data from current regime only | Adapts to market state | Requires regime detection |

**Application to Our Config:**
- `train_window` parameter → Sliding window approach
- Expanding window NOT recommended for non-stationary financial data
- Consider regime detection for window size adaptation

### 9.2 Online Learning for Temporal Data with Regime Changes

**Paper:** "Online learning techniques for prediction of temporal tabular datasets with regime changes"  
*Wong & Barahona - arXiv:2301.00790 (2023)*

**Key Findings:**

1. **GBDT with Dropout** shows high performance, robustness, generalizability
2. **Dynamic Feature Projection** improves robustness by reducing drawdown in regime changes
3. **Dynamical Model Ensembling** based on recent performance improves Sharpe/Calmar ratios
4. LightGBM-dart outperformed standard LightGBM-gbdt in volatile regimes

**Applicable Methods:**

| Method | What It Does | Implementation |
|--------|--------------|----------------|
| Dynamic Feature Projection | Adjusts feature weights based on regime | Adapt `feature_selection_ratio` per regime |
| Model Selection by Recent Performance | Picks best recent model | Track validation scores, use best config |

### 9.3 Learning Curves and Sample Size

**Research Insight:** Learning curve analysis can estimate optimal training sample size

**Method:**
```python
# Fit model on increasing data sizes, track validation error
sample_sizes = [100, 200, 300, 400, 500, 600]
val_errors = []
for size in sample_sizes:
    model = train_quick(X[-size:], y[-size:])
    error = evaluate(model, X_val, y_val)
    val_errors.append(error)

# Find knee point where more data doesn't help
optimal_window = find_knee_point(sample_sizes, val_errors)
```

**Application:**
- Computationally expensive but data-driven
- Could run periodically (not every step) to update window estimate

### 9.4 Gradient Boosting Sample Size Research

**Paper:** "Sample Size Requirements for Popular Classification Algorithms"  
*PMC11688588 (2024)*

**Key Findings:**
- Modern gradient boosting methods (CatBoost, LightGBM) need less data than older methods
- Learning curve flattens at different points for different algorithms
- CatBoost's regularization allows it to work well with smaller samples

---

## 10. sklearn TimeSeriesSplit Patterns

**Official Pattern for Time-Series CV:**

```python
from sklearn.model_selection import TimeSeriesSplit

tscv = TimeSeriesSplit(
    n_splits=5,
    max_train_size=400,    # Cap training window
    test_size=100,         # Fixed test size
    gap=24                 # Embargo period
)

for train_idx, val_idx in tscv.split(X):
    X_train, X_val = X[train_idx], X[val_idx]
    # Train and validate
```

**Key Parameters:**
- `max_train_size`: Limits training window (our `train_window`)
- `gap`: Embargo period between train and test (our `embargo_bars`)
- `test_size`: Size of validation set

**Application to Config Optimization:**
- Use TimeSeriesSplit for config validation (not model validation)
- Multiple folds give more robust estimate of config quality

---

## 11. Synthesized Optimization Strategy

Based on research, recommended approach:

### 11.1 Early Stopping as Data Quality Signal

```python
def estimate_optimal_complexity(X, y, X_val, y_val):
    """Use early stopping behavior as signal."""
    model = CatBoostClassifier(
        iterations=500, early_stopping_rounds=50,
        use_best_model=True, verbose=False
    )
    model.fit(X, y, eval_set=(X_val, y_val))
    
    best_iter = model.get_best_iteration()
    total_iter = 500
    
    # Ratio tells us about data quality
    completion_ratio = best_iter / total_iter
    
    if completion_ratio < 0.2:      # Stops very early
        return "noisy", "reduce_window"
    elif completion_ratio > 0.8:    # Almost completes
        return "clean", "can_increase_window"
    else:
        return "moderate", "baseline_window"
```

### 11.2 Feature Importance Stability Check

```python
def check_feature_stability(X, y, windows=[200, 400]):
    """Check if important features are stable across windows."""
    importances = []
    for w in windows:
        model = train_quick(X[-w:], y[-w:])
        imp = model.get_feature_importance(type='PredictionValuesChange')
        importances.append(pd.Series(imp, index=X.columns))
    
    # Correlation of importances across windows
    stability = importances[0].corr(importances[1])
    
    if stability > 0.7:
        return "stable", 0.6  # Can be more aggressive with feature selection
    elif stability > 0.4:
        return "moderate", 0.5
    else:
        return "unstable", 0.4  # Keep more features as safety
```

### 11.3 Class Balance Adjustment

```python
def adjust_for_class_balance(y):
    """Adjust train ratio based on class imbalance."""
    balance = y.value_counts(normalize=True).min()
    
    if balance < 0.2:       # Severe imbalance
        return 0.65         # More train data needed
    elif balance < 0.35:    # Moderate imbalance
        return 0.60
    else:                   # Balanced
        return 0.55         # Can afford more val/cal
```

### 11.4 Volatility-Based Window Adjustment

```python
def adjust_window_for_volatility(X):
    """Adjust window based on recent volatility."""
    # Use price/return volatility feature if available
    recent_vol = X['volatility_feature'].iloc[-50:].mean()
    baseline_vol = X['volatility_feature'].mean()
    
    vol_ratio = recent_vol / baseline_vol
    
    if vol_ratio > 1.5:     # High volatility regime
        return 300          # Focus on recent data
    elif vol_ratio < 0.7:   # Low volatility regime
        return 500          # Can use more history
    else:
        return 400          # Baseline
```

---

## 12. Updated Implementation Plan

### Phase 1: Analysis Functions ✅ DEFINED

- [ ] `estimate_data_quality(X, y)` → Uses early stopping behavior
- [ ] `check_feature_stability(X, y)` → Importance correlation across windows
- [ ] `analyze_class_balance(y)` → Distribution stats
- [ ] `detect_volatility_regime(X)` → Recent vs baseline volatility

### Phase 2: Config Rules ✅ DEFINED

Window size rules:
- High volatility + noisy → 200-300
- Low volatility + clean → 500-600
- Baseline → 400

Split ratio rules:
- Class imbalance → more train (0.65)
- Balanced → more val/cal (0.55/0.20/0.25)

Feature selection rules:
- Stable features → 0.6 ratio
- Unstable features → 0.4 ratio (keep more as safety)

### Phase 3: Integration

- [ ] Implement `optimize_catboost_config()` with all analysis
- [ ] Add early stopping analysis step
- [ ] Add feature stability check
- [ ] Add class balance adjustment
- [ ] Add volatility-based window adjustment

### Phase 4: Validation

- [ ] Test on synthetic data with known properties
- [ ] Verify no leakage (all analysis uses only historical data)
- [ ] Compare against fixed baseline
- [ ] Measure computational overhead

---

## 13. References & Resources

### Official CatBoost Documentation
- [Overfitting Detector](https://catboost.ai/en/docs/concepts/overfitting-detector-desc) - Early stopping and detection
- [Overfitting Detection Settings](https://catboost.ai/en/docs/references/training-parameters/overfitting-detection) - od_type, od_pval, od_wait
- [Parameter Tuning](https://catboost.ai/en/docs/concepts/parameter-tuning) - Official tuning guide
- [Feature Importance](https://catboost.ai/en/docs/concepts/fstr) - Importance analysis
- [GPU Training](https://catboost.ai/en/docs/features/training-on-gpu) - Performance optimization

### Scientific Papers
- **arXiv:2301.00790** - "Online learning techniques for prediction of temporal tabular datasets with regime changes" (Wong & Barahona, 2023)
- **Petersen et al.** - "Comparing training window selection methods for prediction in non-stationary time series" (British J. Mathematical & Statistical Psychology)
- **PMC11688588** - "Sample Size Requirements for Popular Classification Algorithms" (2024)
- **arXiv 2305.17094** - Tree model depth/regularization study
- **de Prado** - "Advances in Financial ML" Ch. 7 - Sample size requirements

### sklearn Documentation
- [TimeSeriesSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html) - Time-series cross-validation

### Related Code in Project
- `core/features.py` - `apply_feature_selection()`, `extract_per_model_splits()`
- `models/catboost_model.py` - Current implementation
- `services/training.py` - Config creation and wiring

---

## 14. Next Steps

1. **Implement analysis functions** - Start with volatility and class balance (simplest)
2. **Add early stopping analysis** - Train quick model, check best_iteration
3. **Implement config rules** - Map analysis → parameters
4. **Test on holdout** - Use oldest data as test (no leakage)
5. **Iterate** - Refine thresholds based on results
6. **Document learnings** - Add to insights/mistakes.md

---

*Document updated: 2026-01-19 with official CatBoost documentation and scientific research findings.*
