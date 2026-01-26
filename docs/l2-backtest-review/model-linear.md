# Linear Model Reference

**Official Documentation:**
- LogisticRegression: https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.LogisticRegression.html
- Ridge: https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html

## Algorithm Overview

**Linear Models** are the simplest ML approach: weighted sum of features.

### How It Works

**Classification (Logistic Regression):**
1. Compute linear combination: $z = w_1x_1 + w_2x_2 + ... + w_nx_n + b$
2. Apply sigmoid (binary) or softmax (multi-class)
3. Output probabilities for each class

**Regression (Ridge):**
1. Compute linear combination: $\hat{y} = w_1x_1 + w_2x_2 + ... + w_nx_n + b$
2. L2 regularization prevents overfitting: $\min ||y - Xw||^2 + \alpha||w||^2$

### Why Include Linear?

| Complex Models | Linear |
|----------------|--------|
| Can overfit noise | **Regularized baseline** |
| Capture non-linear | Capture **only linear** |
| Black box | **Interpretable** |

**Role in ensemble:** Stabilizing influence, captures obvious linear relationships

---

## Your Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `train_window` | 800 | Samples in training window (largest!) |
| `train_ratio` | 0.50 | Portion for training |
| `val_ratio` | 0.20 | Portion for validation |
| `cal_ratio` | 0.30 | Portion for conformal (larger!) |
| `embargo_bars` | 24 | Gap between splits |
| `feature_selection` | "variance" | Variance-based selection |
| `feature_selection_ratio` | 0.5 | Keep top 50% features |
| `min_features` | 20 | Minimum features |

**Note:** Largest window (800) because linear models are sample-efficient and benefit from more data.

Reference: [linear_model.py#L63-92](../../scripts/target_models/validation/backtest/models/linear_model.py)

---

## Model Hyperparameters

### Classification (LogisticRegression)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `C` | 1.0 | **Inverse** regularization (higher = less reg) |
| `max_iter` | 1000 | Max iterations for convergence |
| `solver` | "lbfgs" | Optimization algorithm |
| `penalty` | "l2" | Regularization type |
| `class_weight` | None | Set to "balanced" for imbalanced classes |
| `fit_intercept` | True | Add bias term (usually want True) |
| `warm_start` | False | Reuse previous solution for incremental fit |
| `intercept_scaling` | 1 | Scale intercept before regularization (liblinear only) |
| `tol` | 1e-4 | Tolerance for stopping (lower = stricter convergence) |

**Class imbalance:** Use `class_weight="balanced"` to auto-weight inversely to frequency.

**Intercept warning:** With `liblinear` solver, intercept is regularized (undesirable). Either:
- Use `lbfgs` solver (doesn't penalize intercept)
- Set high `intercept_scaling` (e.g., 10000) to reduce intercept regularization

### Regression (Ridge)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `alpha` | 1.0 | Regularization strength (higher = more reg) |
| `positive` | False | Constrain coefficients ≥ 0 (uses LBFGS) |
| `solver` | "auto" | Usually SVD for small data, SAG for large |

**Note:** `C` and `alpha` are inverses! `alpha = 1/(2C)` approximately.

**Multi-target regression:** Ridge supports multiple outputs:
```python
# Predict multiple targets jointly
y = np.column_stack([target1, target2, target3])  # shape: (n_samples, 3)
model = Ridge(alpha=1.0)
model.fit(X, y)
# model.coef_ shape: (3, n_features)
```
Useful for predicting multiple horizons at once in time series.

**Multi-target:** Ridge supports `y` of shape `(n_samples, n_targets)` for multiple outputs.

Reference: [linear_model.py#L68-78](../../scripts/target_models/validation/backtest/models/linear_model.py)

---

## Optuna Search Space

### Classification

| Parameter | Range | Scale | Description |
|-----------|-------|-------|-------------|
| `C` | 0.001-100 | **log** | Inverse regularization |
| `solver` | [lbfgs, liblinear] | categorical | Optimizer (binary only) |
| `penalty` | [l1, l2] | categorical | Regularization type (liblinear only) |

**Penalty types:**
- **L2** (Ridge): Shrinks all coefficients, keeps all features
- **L1** (Lasso): Can zero out coefficients (built-in feature selection)
- **Elasticnet**: Mix of L1/L2 (only `saga` solver), control via `l1_ratio`

**Multi-class note:** Only `lbfgs` with `l2` for n_classes ≥ 3.

### Regression

| Parameter | Range | Scale | Description |
|-----------|-------|-------|-------------|
| `alpha` | 0.001-100 | **log** | Regularization strength |

**Tuning settings:**
- Trials: 20 (fast model, can do more)
- Timeout: 30 seconds

Reference: [linear_model.py#L200-290](../../scripts/target_models/validation/backtest/models/linear_model.py)

---

## Classification vs Regression

| Aspect | Classification | Regression |
|--------|---------------|------------|
| Model | `LogisticRegression` | `Ridge` |
| Output | Probabilities via softmax | Continuous value |
| Regularization | `C` (inverse) | `alpha` (direct) |
| Optuna metric | Accuracy | -MSE |
| Penalty options | L1, L2 | L2 only |

### Classification Implementation
```python
LogisticRegression(
    C=C,
    solver=solver,  # "lbfgs" for multiclass
    penalty=penalty,  # "l2" for lbfgs
    max_iter=1000,
    n_jobs=-1,
)
```

### Regression Implementation
```python
Ridge(
    alpha=alpha,  # Regularization strength
)
```

Reference: [linear_model.py#L310-400](../../scripts/target_models/validation/backtest/models/linear_model.py)

---

## Feature Selection

**Method:** Variance-based (planned: ICIR but not yet implemented)

```python
variances = X_train.var()
selected_features = variances.nlargest(n_keep).index.tolist()
```

**Note:** Linear models could use L1 (Lasso) for built-in selection, but we do pre-selection.

Reference: [linear_model.py#L105-145](../../scripts/target_models/validation/backtest/models/linear_model.py)

---

## Data Preprocessing

**StandardScaler required:** Linear models are sensitive to feature scales.

```python
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_val_scaled = scaler.transform(X_val)  # Same transform!
```

**Why scaling matters:**
1. Features with larger scales dominate weights
2. Regularization penalizes all features equally (assumes same scale)
3. **SAG/SAGA solvers require scaling** for fast convergence

### Missing Value Handling
Neither LogisticRegression nor Ridge handles NaN - you must address it:

```python
from sklearn.impute import SimpleImputer

# Option 1: Forward-fill (time series aware)
X_filled = X.fillna(method='ffill').fillna(method='bfill')

# Option 2: Mean/median imputation
imputer = SimpleImputer(strategy='median')
X_imputed = imputer.fit_transform(X_train)  # Fit only on train!

# Option 3: Indicator for missingness (preserves info about missing pattern)
X['feature_missing'] = X['feature'].isna().astype(int)
X['feature'] = X['feature'].fillna(0)
```

**Important:** Fit imputer on training data only, then transform both train and test.

### Categorical Feature Encoding
Linear models need numeric inputs:

```python
from sklearn.preprocessing import OneHotEncoder

# One-hot encode categorical features
encoder = OneHotEncoder(drop='first', sparse_output=False)  # drop='first' avoids collinearity
X_encoded = encoder.fit_transform(X_categorical)

# Cyclical features (hour, day of week) - use sine/cosine
import numpy as np
df['hour_sin'] = np.sin(2 * np.pi * df['hour'] / 24)
df['hour_cos'] = np.cos(2 * np.pi * df['hour'] / 24)
```

### Target Transformation
For skewed or trending targets:

```python
import numpy as np

# Log transform for multiplicative growth
y_log = np.log(y + 1)  # +1 to handle zeros
model.fit(X, y_log)

# Inverse at prediction
pred_original = np.exp(model.predict(X_test)) - 1

# Or use PowerTransformer for automatic normalization
from sklearn.preprocessing import PowerTransformer
pt = PowerTransformer()
y_transformed = pt.fit_transform(y.reshape(-1, 1))
```

---

## Feature Engineering for Time Series

Linear models need manual feature engineering to capture temporal patterns:

### Lag Features
```python
# Create lags for each variable
df['price_lag1'] = df['price'].shift(1)
df['price_lag2'] = df['price'].shift(2)
df['price_lag24'] = df['price'].shift(24)  # Daily seasonality
```

### Rolling Statistics
```python
# Must shift to avoid leakage (use only past data)
df['price_ma24'] = df['price'].rolling(24).mean().shift(1)
df['price_std24'] = df['price'].rolling(24).std().shift(1)
```

### Cyclical Time Encoding
```python
import numpy as np
# Sine/cosine encoding respects cyclical nature (23:00 close to 00:00)
df['hour_sin'] = np.sin(2 * np.pi * df['hour'] / 24)
df['hour_cos'] = np.cos(2 * np.pi * df['hour'] / 24)
```

**Note:** Our pipeline pre-computes L1 helper features, so explicit lag engineering is handled.

---

## Walk-Forward Validation

```python
from sklearn.model_selection import TimeSeriesSplit, GridSearchCV

tscv = TimeSeriesSplit(
    n_splits=5,
    max_train_size=1000,  # Fixed window: limit training size (None = expanding)
    gap=24,               # Gap between train and test (embargo period)
    test_size=100,        # Fix test size for comparable metrics
)
grid = GridSearchCV(
    Ridge(), 
    param_grid={'alpha': [0.1, 1.0, 10.0, 100.0]},
    cv=tscv,  # Time-aware splits!
    scoring='neg_mean_squared_error'
)
```

**Never use KFold** - it mixes past and future, causing data leakage.

**TimeSeriesSplit behavior:**
- Fold 1: train [t0..t1], test t2
- Fold 2: train [t0..t2], test t3
- Expanding window (training grows)

**Fixed window:** Use `max_train_size` parameter to limit training size.

---

## Incremental Learning (Warm Start)

```python
model = LogisticRegression(warm_start=True, solver='lbfgs')

# Day 1: Initial training
model.fit(X_train_day1, y_train_day1)

# Day 2: Continue from previous solution
model.fit(X_train_day1_and_2, y_train_day1_and_2)  # Reuses coefficients as init
```

- Speeds up convergence when adding small amounts of new data
- Previous `coef_` used as starting point
- For true online learning, use `SGDClassifier` with `partial_fit()`

---

## Trade-offs

| Strength | Weakness |
|----------|----------|
| ✅ **Very fast** training | ❌ Only linear relationships |
| ✅ **Interpretable** (weights = importance) | ❌ Can't model interactions |
| ✅ Robust to overfitting | ❌ Underfits complex patterns |
| ✅ Sample efficient | ❌ Needs feature engineering |
| ✅ CPU-only (no GPU needed) | |

---

## CPU-Only Model

**No GPU acceleration** - Linear models are fast enough on CPU.

```python
n_jobs=-1,  # Use all CPU cores
```

---

## Why Linear in Ensemble?

| Tree/LSTM | Linear |
|-----------|--------|
| Complex patterns | **Simple baseline** |
| Risk of overfitting | **Regularization anchor** |
| Black box | **Interpretable check** |

**Ensemble benefit:**
1. **Diversity:** Captures patterns others miss (or confirms they exist)
2. **Stability:** Reduces ensemble variance
3. **Baseline:** If linear does well, complex models add little value

---

## Default Ensemble Weight

| Model | Weight |
|-------|--------|
| CatBoost | 0.30 |
| LightGBM | 0.30 |
| LSTM | 0.25 |
| **Linear** | **0.15** (lowest) |

**Why lowest?** Linear is the least powerful but provides stability.

---

## Solver Comparison

| Solver | Penalty | Multi-class | Speed |
|--------|---------|-------------|-------|
| `lbfgs` | L2 only | ✅ Native | Fast |
| `liblinear` | L1, L2 | ❌ OvR | Medium |
| `saga` | L1, L2, elasticnet | ✅ | Slow |

**Your default:** `lbfgs` - best for multi-class with L2 penalty.

---

## Coefficient Interpretation

### Ridge (Regression)
Coefficient = change in target per one-unit change in feature.
```python
# Feature importance (with scaled features)
importances = pd.Series(model.coef_, index=feature_names)
print(importances.abs().sort_values(ascending=False))
```

### Logistic Regression
Coefficient in **log-odds**: $\log(odds) = w_0 + w_1 x_1 + ...$

**Odds ratio:** $e^{w_i}$ = how odds multiply per one-unit increase in $x_i$
```python
import numpy as np
odds_ratios = np.exp(model.coef_[0])
# Odds ratio > 1: feature increases probability of positive class
# Odds ratio < 1: feature decreases probability
```

### Interpretation Caveats

| Issue | Solution |
|-------|----------|
| **Scale dependence** | Standardize features first |
| **Multicollinearity** | Ridge helps, but check VIF if interpreting |
| **Correlation ≠ causation** | Coefficients show association only |

**Multicollinearity warning:** Correlated features (e.g., lag1 and lag2) can have unstable or counterintuitive coefficients.

---

## Limitations for Time Series

| Limitation | Implication |
|------------|-------------|
| **Only linear relationships** | Can't capture thresholds, interactions, regimes |
| **Manual feature engineering** | Must create lags, rolling stats, seasonality |
| **Fixed coefficients** | Assumes stable relationship over time |
| **No inherent memory** | Must explicitly provide lag features |
| **i.i.d. assumption** | Autocorrelated errors can bias confidence intervals |

### When to Use Alternatives

| Situation | Alternative |
|-----------|-------------|
| Nonlinear patterns | Tree models (CatBoost, LightGBM) |
| Complex seasonality | ARIMA, Prophet |
| Regime changes | HMM, time-varying models |
| Feature interactions | Tree models, polynomial features |
| Sequence patterns | LSTM, TCN |

**scikit-learn's limitation:** No built-in ARIMA or time series models. Use `sktime` or `statsmodels` for dedicated methods.

### Linear as Baseline
Despite limitations, linear models are excellent baselines:
- If linear performs well → complex models may not add much
- Fast to iterate and debug
- Interpretable sanity check
