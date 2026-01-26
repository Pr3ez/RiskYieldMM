# CatBoost Dynamic Optimization - Full Implementation Plan

**Status:** 📋 PLANNING  
**Created:** 2026-01-19  
**Author:** Astra  
**Goal:** Guarantee best CatBoost prediction across ALL backtest targets

---

## 1. SCOPE & CONSTRAINTS

### 1.1 What We're Optimizing

**Focus:** CatBoost ONLY. Other models and ensemble irrelevant for now.

**Target Types to Handle:**

| Target Category | Targets | Task Type | Classes/Range |
|-----------------|---------|-----------|---------------|
| **Direction** | direction_{1,3,6,12}bar | Classification | 3 classes (down/neutral/up) |
| **Volatility** | volatility_{1,3,6,12}bar | Regression | Continuous (positive) |
| **Vol Regime** | vol_regime_{1,3,6,12}bar | Classification | 3 classes (low/medium/high) |
| **Trend Regime** | trend_regime_{1,3,6,12}bar | Classification | 3 classes |
| **First Extreme** | first_extreme_{1,3,6,12}bar | Classification | Binary (0/1) |
| **Time to Extreme** | time_to_extreme_{1,3,6,12}bar | Regression | Integer (0-31) |
| **Vol to Extreme** | vol_to_extreme_{1,3,6,12}bar | Regression | Continuous |

**Total:** 7 target types × 4 horizons = 28 configs

### 1.2 What Parameters to Optimize

**Per-Step Optimization (every backtest step):**

| Parameter | Current | Range | Impact |
|-----------|---------|-------|--------|
| `train_window` | 400 | 200-700 | How much history to use |
| `train_ratio` | 0.60 | 0.50-0.70 | Training data proportion |
| `val_ratio` | 0.20 | 0.15-0.25 | Validation for early stopping |
| `cal_ratio` | 0.20 | 0.10-0.30 | Calibration for conformal |
| `feature_selection_ratio` | 0.60 | 0.30-0.80 | Features to keep |
| `min_features` | 30 | 20-50 | Minimum feature floor |

**Hyperparameters (co-optimize with above):**

| Parameter | Current | Range | Impact |
|-----------|---------|-------|--------|
| `n_estimators` | 100 | 50-500 | Model complexity (with early stop) |
| `max_depth` | 6 | 4-10 | Tree depth |
| `learning_rate` | 0.03 | 0.01-0.3 | Learning rate |
| `l2_leaf_reg` | 5.0 | 1.0-15.0 | Regularization strength |

### 1.3 Constraints (NON-NEGOTIABLE)

```
┌─────────────────────────────────────────────────────────────┐
│                    NO FUTURE LEAKAGE                        │
├─────────────────────────────────────────────────────────────┤
│ At prediction step t, we have:                              │
│   ├── X_full[0:t-1] → Historical features                   │
│   ├── y_full[0:t-1] → Historical targets                    │
│   └── X_pred[t]     → Features for prediction (no target!)  │
│                                                             │
│ FORBIDDEN:                                                  │
│   ├── y_pred[t]     → The answer we're predicting           │
│   └── Any data > t  → Future information                    │
│                                                             │
│ ALL optimization must use ONLY data[0:t-1]                  │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. DATA AVAILABLE AT EACH STEP

### 2.1 Current Entry Point

```python
def train_predict_classification_permodel(
    X_full: pd.DataFrame,    # Shape: (max_window, ~265 features)
    y_full: pd.Series,       # Shape: (max_window,)
    X_pred: pd.DataFrame,    # Shape: (1, ~265 features)
    config: SyncBacktestConfig,
    n_classes: int,
    horizon: int,
    previous_best: dict[str, dict[str, Any]] | None = None,
)
```

### 2.2 What We Can Derive

| Derivation | Source | Use Case |
|------------|--------|----------|
| Target distribution | `y_full.value_counts()` | Class balance → train ratio |
| Target autocorrelation | `y_full.autocorr(lag)` | Predictability → window size |
| Feature volatility | `X_full.std()` | Regime detection → window size |
| Feature correlations | `X_full.corr()` | Redundancy → feature selection |
| Rolling class balance | `y_full.rolling(100).apply(...)` | Stationarity → window size |
| Recent vs old distribution | `KS test on y_full splits` | Drift → window size |

### 2.3 New Entry Point Design

**CRITICAL:** Optimization happens BEFORE splits are extracted.

```python
def optimize_catboost_config(
    X_full: pd.DataFrame,
    y_full: pd.Series,
    target_name: str,
    task_type: str,  # "classification" or "regression"
    horizon: int,
    previous_config: CatBoostModelConfig | None = None,
    previous_performance: dict | None = None,  # Last step's metrics
) -> CatBoostModelConfig:
    """
    Optimize CatBoost config for THIS step and THIS target.
    
    Called at the START of each step, BEFORE any training.
    Uses only historical data (X_full, y_full) - no leakage.
    """
```

---

## 3. OPTIMIZATION STRATEGY

### 3.1 Multi-Stage Pipeline

```
┌────────────────────────────────────────────────────────────────┐
│              STAGE 1: DATA CHARACTERIZATION                    │
│  Analyze X_full, y_full to understand current data state       │
├────────────────────────────────────────────────────────────────┤
│  • Class balance (classification) / distribution (regression)  │
│  • Stationarity (ADF test, rolling stats comparison)           │
│  • Regime detection (volatility level, trend strength)         │
│  • Feature quality (variance, correlation structure)           │
└────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────┐
│              STAGE 2: CANDIDATE CONFIG GENERATION              │
│  Generate 3-5 candidate configs based on Stage 1               │
├────────────────────────────────────────────────────────────────┤
│  • Conservative config (smaller window, higher regularization) │
│  • Aggressive config (larger window, lower regularization)     │
│  • Balanced config (baseline with adjustments)                 │
│  • Target-specific config (based on target type)               │
│  • Performance-adapted config (if previous metrics available)  │
└────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────┐
│              STAGE 3: HOLDOUT VALIDATION                       │
│  Test candidates on internal holdout (NO leakage)              │
├────────────────────────────────────────────────────────────────┤
│  • Use oldest 15% of X_full as "pseudo-test"                   │
│  • Train each candidate on remaining 85%                       │
│  • Measure: accuracy, log_loss, calibration                    │
│  • Select best config by validation score                      │
└────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────┐
│              STAGE 4: HYPERPARAMETER REFINEMENT                │
│  Fine-tune hyperparameters with selected config                │
├────────────────────────────────────────────────────────────────┤
│  • Quick Optuna study (10 trials, 20s timeout)                 │
│  • Search: iterations, depth, learning_rate, l2_leaf_reg       │
│  • Warm-start from previous step's best params                 │
│  • Return final optimized config                               │
└────────────────────────────────────────────────────────────────┘
```

### 3.2 Stage 1: Data Characterization Functions

```python
@dataclass
class DataCharacteristics:
    """Summary of data characteristics for optimization."""
    
    # === Target Characteristics ===
    task_type: str                    # "classification" or "regression"
    n_classes: int | None             # For classification
    class_balance: float | None       # Min class proportion (0-0.5)
    class_imbalance_ratio: float | None  # max/min class ratio
    target_mean: float | None         # For regression
    target_std: float | None          # For regression
    target_skew: float | None         # Distribution skew
    
    # === Stationarity ===
    adf_statistic: float              # ADF test statistic
    adf_pvalue: float                 # ADF p-value
    is_stationary: bool               # p < 0.05
    rolling_mean_drift: float         # Recent vs old mean difference
    rolling_std_drift: float          # Recent vs old std difference
    
    # === Regime ===
    volatility_level: str             # "low", "medium", "high"
    volatility_ratio: float           # Recent vol / baseline vol
    trend_strength: float | None      # Autocorrelation(1) for direction
    
    # === Feature Quality ===
    n_features: int                   # Total features
    n_low_variance: int               # Features with var < threshold
    mean_correlation: float           # Average abs correlation
    max_correlation: float            # Max correlation (redundancy)
    
    # === Sample Size ===
    n_samples: int                    # Total samples available
    samples_per_class: dict | None    # For classification


def characterize_data(
    X_full: pd.DataFrame,
    y_full: pd.Series,
    task_type: str,
) -> DataCharacteristics:
    """Comprehensive data characterization for optimization."""
    ...
```

### 3.3 Stage 2: Candidate Generation Rules

**Rule-Based Candidate Generation:**

```python
def generate_candidate_configs(
    characteristics: DataCharacteristics,
    target_name: str,
    horizon: int,
) -> list[CatBoostModelConfig]:
    """Generate 3-5 candidate configs based on data characteristics."""
    
    candidates = []
    
    # === BASELINE CONFIG ===
    baseline = CatBoostModelConfig(
        train_window=400,
        train_ratio=0.60,
        val_ratio=0.20,
        cal_ratio=0.20,
        feature_selection_ratio=0.60,
    )
    candidates.append(baseline)
    
    # === CLASS BALANCE ADJUSTMENT ===
    if characteristics.class_balance is not None:
        if characteristics.class_balance < 0.20:
            # Severe imbalance: need more training data
            imbalance_cfg = CatBoostModelConfig(
                train_window=500,  # More data
                train_ratio=0.65,  # More for training
                val_ratio=0.20,
                cal_ratio=0.15,
                feature_selection_ratio=0.50,  # Fewer features to reduce noise
                l2_leaf_reg=8.0,  # More regularization
            )
            candidates.append(imbalance_cfg)
    
    # === STATIONARITY ADJUSTMENT ===
    if not characteristics.is_stationary or characteristics.rolling_mean_drift > 0.3:
        # Non-stationary: focus on recent data
        drift_cfg = CatBoostModelConfig(
            train_window=300,  # Smaller window
            train_ratio=0.55,
            val_ratio=0.25,  # More validation to catch drift
            cal_ratio=0.20,
            feature_selection_ratio=0.50,
            learning_rate=0.05,  # Faster learning
            l2_leaf_reg=10.0,  # More regularization
        )
        candidates.append(drift_cfg)
    
    # === VOLATILITY REGIME ADJUSTMENT ===
    if characteristics.volatility_level == "high":
        high_vol_cfg = CatBoostModelConfig(
            train_window=350,
            train_ratio=0.60,
            val_ratio=0.20,
            cal_ratio=0.20,
            feature_selection_ratio=0.40,  # More aggressive selection
            max_depth=5,  # Shallower trees
            l2_leaf_reg=12.0,  # Strong regularization
        )
        candidates.append(high_vol_cfg)
    elif characteristics.volatility_level == "low":
        low_vol_cfg = CatBoostModelConfig(
            train_window=500,
            train_ratio=0.60,
            val_ratio=0.20,
            cal_ratio=0.20,
            feature_selection_ratio=0.70,  # Keep more features
            max_depth=7,
            l2_leaf_reg=3.0,  # Less regularization
        )
        candidates.append(low_vol_cfg)
    
    # === TARGET-TYPE SPECIFIC ===
    if "direction" in target_name:
        # Direction: benefits from recent data, needs good calibration
        direction_cfg = CatBoostModelConfig(
            train_window=350,
            train_ratio=0.55,
            val_ratio=0.20,
            cal_ratio=0.25,  # More calibration for 3-class
            feature_selection_ratio=0.55,
        )
        candidates.append(direction_cfg)
    
    elif "volatility" in target_name and characteristics.task_type == "regression":
        # Volatility regression: can use more data
        vol_cfg = CatBoostModelConfig(
            train_window=500,
            train_ratio=0.65,
            val_ratio=0.20,
            cal_ratio=0.15,
            feature_selection_ratio=0.65,
            max_depth=6,
        )
        candidates.append(vol_cfg)
    
    elif "regime" in target_name:
        # Regime: needs stability
        regime_cfg = CatBoostModelConfig(
            train_window=450,
            train_ratio=0.60,
            val_ratio=0.20,
            cal_ratio=0.20,
            feature_selection_ratio=0.50,
            l2_leaf_reg=7.0,
        )
        candidates.append(regime_cfg)
    
    # === HORIZON-BASED ADJUSTMENT ===
    horizon_mult = {1: 1.0, 3: 1.1, 6: 1.2, 12: 1.3}
    for cfg in candidates:
        cfg.train_window = int(cfg.train_window * horizon_mult.get(horizon, 1.0))
        cfg.train_window = min(cfg.train_window, 700)  # Cap at max
    
    return candidates
```

### 3.4 Stage 3: Holdout Validation

```python
def validate_configs_on_holdout(
    X_full: pd.DataFrame,
    y_full: pd.Series,
    candidates: list[CatBoostModelConfig],
    task_type: str,
    n_classes: int | None,
) -> tuple[CatBoostModelConfig, dict]:
    """
    Validate candidate configs on internal holdout.
    
    Split strategy:
    - Holdout (oldest 15%): pseudo-test set
    - Remaining 85%: used for train/val/cal per config
    
    Returns:
        Best config and validation results dict
    """
    n_samples = len(X_full)
    holdout_size = int(n_samples * 0.15)
    
    # CRITICAL: Holdout is OLDEST data (temporal split)
    X_holdout = X_full.iloc[:holdout_size]
    y_holdout = y_full.iloc[:holdout_size]
    X_remain = X_full.iloc[holdout_size:]
    y_remain = y_full.iloc[holdout_size:]
    
    results = []
    for cfg in candidates:
        # Extract splits from remaining data
        window = min(cfg.train_window, len(X_remain))
        X_window = X_remain.iloc[-window:]
        y_window = y_remain.iloc[-window:]
        
        # Calculate split sizes
        train_end = int(window * cfg.train_ratio)
        val_end = train_end + int(window * cfg.val_ratio)
        
        X_train = X_window.iloc[:train_end]
        y_train = y_window.iloc[:train_end]
        X_val = X_window.iloc[train_end:val_end]
        y_val = y_window.iloc[train_end:val_end]
        
        # Quick train with fixed hyperparams
        score = _quick_train_evaluate(
            X_train, y_train, X_val, y_val,
            X_holdout, y_holdout,
            cfg, task_type, n_classes
        )
        results.append((cfg, score))
    
    # Select best
    best_cfg, best_score = max(results, key=lambda x: x[1]["combined_score"])
    return best_cfg, {"candidates": len(candidates), "best_score": best_score}


def _quick_train_evaluate(
    X_train, y_train, X_val, y_val,
    X_test, y_test,
    config: CatBoostModelConfig,
    task_type: str,
    n_classes: int | None,
) -> dict:
    """Quick training and evaluation for config selection."""
    
    # Feature selection
    features = apply_quick_feature_selection(
        X_train, y_train,
        config.feature_selection_ratio,
        config.min_features
    )
    
    X_train_sel = X_train[features]
    X_val_sel = X_val[features]
    X_test_sel = X_test[features]
    
    if task_type == "classification":
        model = CatBoostClassifier(
            iterations=100,
            depth=config.max_depth,
            learning_rate=config.learning_rate,
            l2_leaf_reg=config.l2_leaf_reg,
            early_stopping_rounds=20,
            use_best_model=True,
            loss_function="Logloss" if n_classes == 2 else "MultiClass",
            task_type="GPU",
            devices="0",
            verbose=False,
            random_seed=42,
        )
        model.fit(X_train_sel, y_train, eval_set=(X_val_sel, y_val))
        
        y_pred = model.predict(X_test_sel)
        y_prob = model.predict_proba(X_test_sel)
        
        accuracy = accuracy_score(y_test, y_pred)
        log_loss_val = log_loss(y_test, y_prob, labels=range(n_classes))
        
        # Combined score: balance accuracy and calibration
        combined = 0.6 * accuracy + 0.4 * (1 - min(log_loss_val, 2) / 2)
        
        return {
            "accuracy": accuracy,
            "log_loss": log_loss_val,
            "combined_score": combined,
            "best_iteration": model.get_best_iteration(),
        }
    
    else:  # regression
        model = CatBoostRegressor(
            iterations=100,
            depth=config.max_depth,
            learning_rate=config.learning_rate,
            l2_leaf_reg=config.l2_leaf_reg,
            early_stopping_rounds=20,
            use_best_model=True,
            loss_function="RMSE",
            task_type="GPU",
            devices="0",
            verbose=False,
            random_seed=42,
        )
        model.fit(X_train_sel, y_train, eval_set=(X_val_sel, y_val))
        
        y_pred = model.predict(X_test_sel)
        
        mse = mean_squared_error(y_test, y_pred)
        mae = mean_absolute_error(y_test, y_pred)
        
        # Normalize by target std for comparable score
        target_std = y_test.std()
        normalized_rmse = np.sqrt(mse) / target_std if target_std > 0 else np.sqrt(mse)
        
        combined = 1 - min(normalized_rmse, 2) / 2  # 0-1 score
        
        return {
            "rmse": np.sqrt(mse),
            "mae": mae,
            "combined_score": combined,
            "best_iteration": model.get_best_iteration(),
        }
```

### 3.5 Stage 4: Hyperparameter Refinement

```python
def refine_hyperparameters(
    X_full: pd.DataFrame,
    y_full: pd.Series,
    base_config: CatBoostModelConfig,
    task_type: str,
    n_classes: int | None,
    previous_best: dict | None = None,
    n_trials: int = 10,
    timeout: float = 20.0,
) -> CatBoostModelConfig:
    """
    Fine-tune hyperparameters using Optuna.
    
    Uses the selected config from Stage 3 as base,
    then optimizes iterations, depth, learning_rate, l2_leaf_reg.
    """
    
    # Extract splits using base config
    window = min(base_config.train_window, len(X_full))
    X_window = X_full.iloc[-window:]
    y_window = y_full.iloc[-window:]
    
    train_end = int(window * base_config.train_ratio)
    val_end = train_end + int(window * base_config.val_ratio)
    
    X_train = X_window.iloc[:train_end]
    y_train = y_window.iloc[:train_end]
    X_val = X_window.iloc[train_end:val_end]
    y_val = y_window.iloc[train_end:val_end]
    
    # Feature selection
    features = apply_quick_feature_selection(
        X_train, y_train,
        base_config.feature_selection_ratio,
        base_config.min_features
    )
    X_train_sel = X_train[features]
    X_val_sel = X_val[features]
    
    def objective(trial):
        # Search around base config values
        iterations = trial.suggest_int("iterations", 50, 300)
        depth = trial.suggest_int("depth", max(4, base_config.max_depth - 2),
                                          min(10, base_config.max_depth + 2))
        lr = trial.suggest_float("learning_rate", 
                                 max(0.01, base_config.learning_rate * 0.5),
                                 min(0.3, base_config.learning_rate * 2),
                                 log=True)
        l2 = trial.suggest_float("l2_leaf_reg",
                                 max(1.0, base_config.l2_leaf_reg * 0.5),
                                 min(15.0, base_config.l2_leaf_reg * 2))
        
        if task_type == "classification":
            model = CatBoostClassifier(
                iterations=iterations,
                depth=depth,
                learning_rate=lr,
                l2_leaf_reg=l2,
                early_stopping_rounds=30,
                use_best_model=True,
                loss_function="Logloss" if n_classes == 2 else "MultiClass",
                task_type="GPU",
                devices="0",
                verbose=False,
            )
            model.fit(X_train_sel, y_train, eval_set=(X_val_sel, y_val))
            return accuracy_score(y_val, model.predict(X_val_sel))
        else:
            model = CatBoostRegressor(
                iterations=iterations,
                depth=depth,
                learning_rate=lr,
                l2_leaf_reg=l2,
                early_stopping_rounds=30,
                use_best_model=True,
                loss_function="RMSE",
                task_type="GPU",
                devices="0",
                verbose=False,
            )
            model.fit(X_train_sel, y_train, eval_set=(X_val_sel, y_val))
            return -mean_squared_error(y_val, model.predict(X_val_sel))
    
    # Warm-start if previous best available
    sampler = optuna.samplers.TPESampler(seed=42)
    study = optuna.create_study(direction="maximize", sampler=sampler)
    
    if previous_best:
        study.enqueue_trial(previous_best)
    
    study.optimize(objective, n_trials=n_trials, timeout=timeout, show_progress_bar=False)
    
    # Update config with best params
    final_config = CatBoostModelConfig(
        train_window=base_config.train_window,
        train_ratio=base_config.train_ratio,
        val_ratio=base_config.val_ratio,
        cal_ratio=base_config.cal_ratio,
        feature_selection=base_config.feature_selection,
        feature_selection_ratio=base_config.feature_selection_ratio,
        min_features=base_config.min_features,
        n_estimators=study.best_params["iterations"],
        max_depth=study.best_params["depth"],
        learning_rate=study.best_params["learning_rate"],
        l2_leaf_reg=study.best_params["l2_leaf_reg"],
    )
    
    return final_config
```

---

## 4. INTEGRATION INTO BACKTEST

### 4.1 Modified Training Flow

**Current flow:**
```
train_predict_classification_permodel()
├── _get_model_configs() → Returns fixed baseline configs
├── extract_per_model_splits() → Uses config.train_window, etc.
├── _apply_feature_selection_with_quick_model()
└── cb_train_predict_cls() → Trains and predicts
```

**New flow:**
```
train_predict_classification_permodel()
├── optimize_catboost_config()        ← NEW: 4-stage optimization
│   ├── characterize_data()           ← Stage 1
│   ├── generate_candidate_configs()  ← Stage 2
│   ├── validate_configs_on_holdout() ← Stage 3
│   └── refine_hyperparameters()      ← Stage 4
├── extract_per_model_splits()        ← Uses OPTIMIZED config
├── _apply_feature_selection_with_quick_model()
└── cb_train_predict_cls()            ← Trains with OPTIMIZED params
```

### 4.2 Code Changes Required

**File: `backtest/models/catboost_model.py`**

```python
# ADD these new classes/functions:
@dataclass
class DataCharacteristics:
    """Data characterization results."""
    ...

def characterize_data(...) -> DataCharacteristics:
    """Stage 1: Characterize data."""
    ...

def generate_candidate_configs(...) -> list[CatBoostModelConfig]:
    """Stage 2: Generate candidates."""
    ...

def validate_configs_on_holdout(...) -> tuple[CatBoostModelConfig, dict]:
    """Stage 3: Holdout validation."""
    ...

def refine_hyperparameters(...) -> CatBoostModelConfig:
    """Stage 4: Hyperparameter refinement."""
    ...

def optimize_catboost_config(...) -> CatBoostModelConfig:
    """Main entry point - runs all 4 stages."""
    characteristics = characterize_data(X_full, y_full, task_type)
    candidates = generate_candidate_configs(characteristics, target_name, horizon)
    best_config, _ = validate_configs_on_holdout(X_full, y_full, candidates, ...)
    final_config = refine_hyperparameters(X_full, y_full, best_config, ...)
    return final_config
```

**File: `backtest/services/training.py`**

```python
# MODIFY _get_model_configs() to call optimize_catboost_config():

def _get_model_configs(
    config: SyncBacktestConfig,
    horizon: int,
    X_full: pd.DataFrame,      # ADD
    y_full: pd.Series,         # ADD
    target_name: str,          # ADD
    task_type: str,            # ADD
    previous_cb_config: CatBoostModelConfig | None = None,  # ADD
) -> tuple[CatBoostModelConfig, ...]:
    """Get per-model configs with dynamic optimization for CatBoost."""
    
    dynamic_embargo = get_embargo_for_horizon(horizon)
    
    # CatBoost: OPTIMIZED
    cb_cfg = optimize_catboost_config(
        X_full=X_full,
        y_full=y_full,
        target_name=target_name,
        task_type=task_type,
        horizon=horizon,
        previous_config=previous_cb_config,
    )
    cb_cfg.embargo_bars = dynamic_embargo
    
    # Other models: keep baseline for now
    lgb_cfg = LightGBMModelConfig(...)  # baseline
    lstm_cfg = LSTMModelConfig(...)      # baseline
    linear_cfg = LinearModelConfig(...)  # baseline
    
    return cb_cfg, lgb_cfg, lstm_cfg, linear_cfg
```

### 4.3 Performance Considerations

**Estimated overhead per step:**

| Stage | Time | Notes |
|-------|------|-------|
| Stage 1: Characterization | ~50ms | Fast pandas operations |
| Stage 2: Candidate generation | ~5ms | Rule-based, no training |
| Stage 3: Holdout validation | ~500ms | 3-5 quick CatBoost fits (GPU) |
| Stage 4: Hyperparameter refinement | ~2s | 10 Optuna trials |
| **Total overhead** | **~2.5s** | Per step |

**Current training time:** ~5s per step (4 models)  
**With optimization:** ~7.5s per step  
**Impact:** +50% time, but CatBoost-only optimization

**Optimization options:**
1. Run Stage 3-4 every N steps (e.g., every 10 steps)
2. Cache characteristics if data changes <5%
3. Reduce Optuna trials to 5 for faster refinement

---

## 5. TARGET-SPECIFIC ADJUSTMENTS

### 5.1 Classification Targets

| Target | Special Handling |
|--------|------------------|
| **direction** | 3-class, sensitive to drift, benefit from larger cal_ratio (0.25) |
| **vol_regime** | 3-class, more stable, can use larger window |
| **trend_regime** | 3-class, regime-switching, need regime detection |
| **first_extreme** | Binary, often imbalanced, need class weighting |

### 5.2 Regression Targets

| Target | Special Handling |
|--------|------------------|
| **volatility** | Positive values, can use log transform, larger window OK |
| **time_to_extreme** | Bounded (0-31), count-like, consider Poisson loss |
| **vol_to_extreme** | Continuous, may be skewed, check distribution |

### 5.3 Horizon Adjustments

| Horizon | Window Multiplier | Notes |
|---------|-------------------|-------|
| 1-bar | 1.0x | Baseline, most data points |
| 3-bar | 1.1x | Slightly more history needed |
| 6-bar | 1.2x | More pattern averaging |
| 12-bar | 1.3x | Longest horizon, needs stable patterns |

---

## 6. VALIDATION & TESTING

### 6.1 Unit Tests

```python
def test_no_leakage_in_optimization():
    """Verify optimization uses only historical data."""
    X_full = make_mock_features(800)
    y_full = make_mock_targets(800)
    X_pred = make_mock_features(1)
    
    # Mark future data
    future_marker = "FUTURE_LEAK"
    X_pred.iloc[0, 0] = future_marker
    
    config = optimize_catboost_config(X_full, y_full, "direction_1bar", "classification", 1)
    
    # Config should not contain any reference to X_pred
    assert future_marker not in str(config)

def test_config_bounds():
    """Verify optimized configs stay within valid bounds."""
    config = optimize_catboost_config(...)
    
    assert 200 <= config.train_window <= 700
    assert 0.50 <= config.train_ratio <= 0.70
    assert 0.15 <= config.val_ratio <= 0.25
    assert 0.10 <= config.cal_ratio <= 0.30
    assert abs(config.train_ratio + config.val_ratio + config.cal_ratio - 1.0) < 0.01

def test_target_specific_adjustments():
    """Verify different targets produce different configs."""
    X, y_dir = make_direction_target(800)
    X, y_vol = make_volatility_target(800)
    
    cfg_dir = optimize_catboost_config(X, y_dir, "direction_1bar", "classification", 1)
    cfg_vol = optimize_catboost_config(X, y_vol, "volatility_1bar", "regression", 1)
    
    # Should produce different configs
    assert cfg_dir.train_window != cfg_vol.train_window or \
           cfg_dir.feature_selection_ratio != cfg_vol.feature_selection_ratio
```

### 6.2 Integration Tests

```python
def test_full_backtest_with_optimization():
    """Run short backtest with optimization enabled."""
    configs = ["direction_1bar", "volatility_1bar"]
    
    for config_name in configs:
        results = run_sync_backtest([config_name], max_steps=10)
        
        # Check results are valid
        assert len(results) == 10
        assert all("cb_pred" in r for r in results)
        assert all("cb_config_window" in r for r in results)  # Track config used

def test_optimization_improves_performance():
    """Compare optimized vs baseline on known data."""
    baseline_results = run_backtest(optimization=False, steps=100)
    optimized_results = run_backtest(optimization=True, steps=100)
    
    # Optimized should not be significantly worse
    baseline_acc = compute_accuracy(baseline_results)
    optimized_acc = compute_accuracy(optimized_results)
    
    assert optimized_acc >= baseline_acc * 0.95  # Allow 5% variance
```

---

## 7. IMPLEMENTATION PHASES

### Phase 1: Core Analysis (Est: 2 hours)
- [ ] Implement `DataCharacteristics` dataclass
- [ ] Implement `characterize_data()` function
- [ ] Unit test characterization

### Phase 2: Candidate Generation (Est: 2 hours)
- [ ] Implement candidate generation rules
- [ ] Cover all target types
- [ ] Cover all horizons
- [ ] Unit test candidate generation

### Phase 3: Holdout Validation (Est: 3 hours)
- [ ] Implement `validate_configs_on_holdout()`
- [ ] Implement `_quick_train_evaluate()`
- [ ] Support both classification and regression
- [ ] Unit test validation

### Phase 4: Hyperparameter Refinement (Est: 2 hours)
- [ ] Implement `refine_hyperparameters()`
- [ ] Add warm-start support
- [ ] Optimize Optuna settings
- [ ] Unit test refinement

### Phase 5: Integration (Est: 3 hours)
- [ ] Modify `_get_model_configs()` signature
- [ ] Wire optimization into training flow
- [ ] Add config tracking to output
- [ ] Integration test

### Phase 6: Validation (Est: 2 hours)
- [ ] Run full backtest on 1-bar targets
- [ ] Compare vs baseline
- [ ] Tune thresholds if needed
- [ ] Document results

**Total Estimated: 14 hours**

---

## 8. SUCCESS CRITERIA

### 8.1 Must Have
- [ ] No future data leakage (verified by test)
- [ ] Works for all 28 target configs
- [ ] Doesn't crash on edge cases (few samples, imbalanced)
- [ ] Overhead < 100% of current training time

### 8.2 Should Have
- [ ] Improves or maintains CatBoost accuracy vs baseline
- [ ] Produces meaningful config variation across targets
- [ ] Logs optimization decisions for debugging

### 8.3 Nice to Have
- [ ] Configurable optimization intensity (fast/balanced/thorough)
- [ ] Caching of characterization across similar targets
- [ ] Performance dashboard showing config choices

---

## 9. RISKS & MITIGATIONS

| Risk | Impact | Mitigation |
|------|--------|------------|
| Optimization overhead too high | Backtest takes 2x longer | Add skip_optimization option, tune trial counts |
| Holdout validation misleading | Picks wrong config | Use multiple evaluation metrics, add sanity checks |
| Over-optimization to holdout | Poor generalization | Limit config search space, use regularization |
| Target-specific rules wrong | Bad configs for some targets | Start conservative, tune based on results |

---

## 10. NEXT STEPS

1. **Get approval** on this plan
2. **Implement Phase 1** (characterization)
3. **Test Phase 1** thoroughly before proceeding
4. **Continue with Phases 2-6**
5. **Run comparison backtest** (baseline vs optimized)
6. **Document results** and refine thresholds

---

*Document ready for review. Implementation can begin after approval.*
