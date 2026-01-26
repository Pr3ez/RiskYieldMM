# LightGBM Model Reference

**Official Documentation:** https://lightgbm.readthedocs.io/

## Algorithm Overview

**LightGBM** (Light Gradient Boosting Machine) is a gradient boosting framework by Microsoft.

### How It Works

1. **Gradient Boosting**: Sequential tree building, each correcting previous errors
2. **Leaf-wise Growth**: Grows tree by best leaf (vs level-wise), faster convergence
3. **Histogram-based Splits**: Bins continuous features for faster computation
4. **Gradient-based One-Side Sampling (GOSS)**: Focuses on high-gradient samples

### Key Difference from CatBoost

| CatBoost | LightGBM |
|----------|----------|
| Level-wise (symmetric trees) | **Leaf-wise** (asymmetric) |
| Ordered boosting | Standard boosting |
| Slower but more robust | **Faster** but can overfit |

### Leaf-Wise Growth (Critical)

LightGBM grows trees **best-first** by choosing the leaf with highest gain. This can overfit if unconstrained.

**Key control:** `num_leaves` is **more important than max_depth**
- Use fewer leaves than $2^{\text{max\_depth}}$
- Example: `num_leaves=70` instead of $2^7=128$ for `max_depth=7`

### Prediction Mechanics

**Classification:**
- Trees output log-odds or class scores
- Softmax for multi-class probabilities
- Final = sum of all tree contributions

**Regression:**
- Each tree predicts residual
- Final = sum of all tree predictions

---

## Your Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `train_window` | 400 | Samples in training window |
| `train_ratio` | 0.60 | Portion for training |
| `val_ratio` | 0.20 | Portion for validation |
| `cal_ratio` | 0.20 | Portion for conformal calibration |
| `embargo_bars` | 24 | Gap between splits |
| `feature_selection` | "importance" | Use LightGBM importance |
| `feature_selection_ratio` | 0.6 | Keep top 60% features |
| `min_features` | 30 | Minimum features |

Reference: [lightgbm_model.py#L63-95](../../scripts/target_models/validation/backtest/models/lightgbm_model.py)

---

## Model Hyperparameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `n_estimators` | 100 | Number of boosting rounds |
| `max_depth` | 6 | Maximum tree depth |
| `learning_rate` | 0.03 | Step size shrinkage |
| `reg_lambda` | 3.0 | L2 regularization |
| `min_child_samples` | 20 | Min samples in leaf |
| `use_gpu` | True | GPU acceleration |

Reference: [lightgbm_model.py#L68-80](../../scripts/target_models/validation/backtest/models/lightgbm_model.py)

---

## Optuna Search Space

| Parameter | Range | Scale | Description |
|-----------|-------|-------|-------------|
| `n_estimators` | 50-300 | linear | Number of trees |
| `num_leaves` | 20-100 | linear | Max leaves per tree (key for overfitting) |
| `max_depth` | 3-8 | linear | Tree depth limit |
| `learning_rate` | 0.01-0.3 | **log** | Step size |
| `reg_lambda` | 0.1-10.0 | linear | L2 regularization |
| `reg_alpha` | 0.0-1.0 | linear | L1 regularization |
| `min_child_samples` | 10-100 | linear | Min samples per leaf |
| `feature_fraction` | 0.5-1.0 | linear | Feature subsampling per tree |
| `bagging_fraction` | 0.6-1.0 | linear | Row subsampling per tree |
| `path_smooth` | 0-10 | linear | Leaf value smoothing |

**Tuning settings:**
- Trials: 15
- Timeout: 30 seconds
- Warm-start: Uses previous step's best params

**Critical tuning tip:** `num_leaves` controls complexity more than `max_depth`
- Lower `num_leaves` = less overfitting
- Start with `num_leaves < 2^max_depth`

Reference: [lightgbm_model.py#L240-300](../../scripts/target_models/validation/backtest/models/lightgbm_model.py)

---

## Classification vs Regression

| Aspect | Classification | Regression |
|--------|---------------|------------|
| Objective | `binary` / `multiclass` | default (L2) |
| Output | Class probabilities | Continuous value |
| Optuna metric | Accuracy (maximize) | -MSE (maximize) |
| Extra param | `num_class` for multiclass | - |

### Classification-Specific
```python
LGBMClassifier(
    objective="binary" if is_binary else "multiclass",
    num_class=n_classes if not is_binary else None,
    ...
)
```

### Regression-Specific
```python
LGBMRegressor(
    # Uses default objective (L2/MSE)
    ...
)
```

---

## Feature Selection

**Method:** Train quick model (50 iterations) → Get feature importances → Select top N

```python
quick_model = LGBMClassifier(n_estimators=50, max_depth=4, ...)
quick_model.fit(X_train, y_train)
importances = quick_model.feature_importances_
selected = top_n_by_importance
```

Reference: [lightgbm_model.py#L105-145](../../scripts/target_models/validation/backtest/models/lightgbm_model.py)

---

## Trade-offs

| Strength | Weakness |
|----------|----------|
| ✅ **Very fast** training | ❌ Leaf-wise can overfit |
| ✅ Low memory usage | ❌ Sensitive to hyperparameters |
| ✅ Handles large datasets well | ❌ Less robust than CatBoost |
| ✅ GPU acceleration | |
| ✅ Good feature importance | |

---

## GPU Usage

```python
device="gpu" if config.use_gpu else "cpu",
```

**Memory:** ~0.5-1GB VRAM (more efficient than CatBoost)

**GPU tips:**
- Use smaller `max_bin` (63 recommended) for speed on GPU
- Default is single precision; use `gpu_use_dp=True` for double if needed

---

## Regularization Parameters

| Parameter | Default | Effect |
|-----------|---------|--------|
| `reg_lambda` (L2) | 0 | Penalizes large leaf weights |
| `reg_alpha` (L1) | 0 | Encourages sparse leaf weights |
| `min_child_samples` | 20 | Min samples per leaf (prevent deep splits) |
| `min_sum_hessian_in_leaf` | 0.001 | Min Hessian sum per leaf (like XGBoost's `min_child_weight`) |
| `min_gain_to_split` | 0 | Min loss reduction for split |
| `path_smooth` | 0 | Smooths leaf values when few samples reach leaf |
| `extra_trees` | False | Extremely randomized splits (more regularization) |

**`path_smooth`** - Useful for time series to avoid spiky predictions from rare events

---

## Class Imbalance Handling

```python
# Option 1: Auto-balance
LGBMClassifier(
    is_unbalance=True,  # Auto-adjust weights inversely to class frequency
)

# Option 2: Manual weight
LGBMClassifier(
    scale_pos_weight=2.5,  # Multiply positive class weight
)
```
**Use one or the other, not both.** Improves recall on rare classes.

---

## Reproducibility Settings

```python
LGBMClassifier(
    seed=42,                # Global random seed
    deterministic=True,     # Eliminate multi-threading nondetnderminism
    force_col_wise=True,    # Required with deterministic for stable results
)
```
- `deterministic=True` ensures consistent results across runs (slower)
- Without it, multi-threading can cause different results each run

---

## Bagging & Feature Subsampling

### Row Subsampling
```python
bagging_fraction=0.8,  # Use 80% of rows per tree
bagging_freq=1,        # Apply every iteration (required!)
```
**Both `bagging_fraction < 1.0` AND `bagging_freq > 0` needed to activate bagging**

### Feature Subsampling
```python
feature_fraction=0.8,      # 80% features per tree
feature_fraction_bynode=0.8,  # 80% features per split (stacks!)
# Combined: 0.8 × 0.8 = 64% features per split
```

### Balanced Bagging (for imbalanced classification)
```python
pos_bagging_fraction=0.5,  # Downsample positives
neg_bagging_fraction=0.5,  # Downsample negatives
bagging_freq=1,
```

---

## Boosting Types

| Type | When to Use |
|------|-------------|
| `gbdt` | Default, most cases |
| `dart` | Overfitting issues - drops trees like dropout |
| `goss` | Large data, speed priority - samples by gradient |
| `rf` | Want random forest behavior |

### DART (Dropout Regularization)
```python
boosting_type='dart',
drop_rate=0.1,      # Fraction of trees to drop
skip_drop=0.5,      # Probability to skip dropout
```
- Prevents relying too much on any single boosting stage
- Good for sequential data if GBDT overfits

### GOSS (Gradient-based One-Side Sampling)
```python
boosting_type='gbdt',
data_sample_strategy='goss',
top_rate=0.2,       # Keep top 20% large-gradient samples
other_rate=0.1,     # Keep 10% of small-gradient samples
```
- Speeds up training on large datasets
- Maintains accuracy by focusing on informative samples

---

## Early Stopping

```python
model.fit(
    X_train, y_train,
    eval_set=[(X_val, y_val)],
    callbacks=[lgb.early_stopping(stopping_rounds=50)],
)
best_iteration = model.best_iteration_
```

**Critical:** Provide time-forward validation set, not random split

---

## Time Series Considerations

### No Native Time-Awareness
LightGBM treats data as IID - **you must**:
- Create lag features (ensure no future leakage)
- Use walk-forward validation (not random splits)
- Encode seasonality (sine/cosine for cyclic features)

### Walk-Forward Validation
- Don't use `lgb.cv()` - it does random K-fold
- Manually create time-based folds
- Our pipeline handles this via `WalkForwardValidator`

### Continued Training (Warm Start)
```python
# Initial training
model.fit(X_train, y_train)
model.booster_.save_model('model.txt')

# Continue with new data
new_model = lgb.train(
    params,
    new_dataset,
    init_model='model.txt',  # Warm start
    num_boost_round=50,       # Add more trees
)
```

### Refit Mode (Adjust Leaves Without New Trees)
```python
# CLI: task=refit, refit_decay_rate=0.9
# new_leaf = 0.9 * old_leaf + 0.1 * new_optimal
```
- Updates leaf values with new data
- Useful for drift adaptation without full retraining

### Bagging by Group (Panel Data)
```python
# For multiple time series (e.g., many stocks)
bagging_by_query=True  # Bag entire series, not individual rows
```
- Requires group identifiers via `Dataset.set_group()`
- Ensures bagging respects series boundaries
- Avoids partial series fragments in subsamples

### Saving/Reusing Datasets
```python
# Save after initial loading (skips parsing/binning next time)
dataset.save_binary('data.bin')
# Or set save_binary=True in params
```
- Speeds up repeated training on similar data
- Useful for walk-forward where data grows incrementally

### Initial Score (Baseline Predictions)
```python
# Provide initial predictions to boost from
dataset.set_init_score(previous_model_predictions)
```
- Start training from another model's predictions
- Another form of warm-start (more flexible)

### Monotonic Constraints
```python
monotone_constraints=[1, -1, 0, ...]  # 1=increasing, -1=decreasing, 0=none
```
- Enforce trend direction on specific features
- Use if you have strong prior (e.g., elapsed time should increase prediction)

### Interaction Constraints
```python
interaction_constraints=[[0, 1], [2, 3, 4]]  # Feature groups allowed to interact
```
- Restricts which features can appear together in tree paths
- Prevents certain features from interacting (e.g., time features with others)
- Use to avoid overfitting or leakage from undesired interactions

### Forced Splits
```python
# Via JSON file
forcedsplits_filename="forced_splits.json"
```
- Force specific splits at top of every tree
- Useful for panel data: "split by stock ID first"
- Guarantees domain knowledge is incorporated

---

## Missing Values

LightGBM handles missing values natively:
- NaN sent left or right at each split (whichever is better)
- No imputation needed
- `use_missing=True` by default
- `zero_as_missing=False` by default (only NaN = missing)

---

## Categorical Features

```python
model = LGBMClassifier(
    categorical_feature=[0, 2, 5],  # Column indices
    # OR
    categorical_feature='auto',     # Detect from pandas category dtype
)
```

**Requirements:**
- Categories must be non-negative integers (0 to N-1)
- For high cardinality: tune `cat_smooth` (default 10), `cat_l2` (default 10)
- `max_cat_to_onehot=4` - categories ≤4 values get one-hot encoded

---

## LightGBM vs CatBoost in Ensemble

| Aspect | CatBoost | LightGBM |
|--------|----------|----------|
| Default weight | 0.30 | 0.30 |
| Training speed | Slower | **Faster** |
| Overfitting risk | Lower | Higher |
| Diversity | Conservative | Aggressive |

**Why both?** Different tree-growing strategies provide ensemble diversity:
- CatBoost: More regularized, stable predictions
- LightGBM: Faster, captures different patterns

---

## Limitations for Time Series

| Limitation | Implication |
|------------|-------------|
| **No native time-awareness** | Must create lag features, walk-forward validation manually |
| **No multi-step forecast** | Predicts one step; recursive forecasting compounds errors |
| **No built-in time series CV** | `lgb.cv()` does random K-fold, must use custom folds |
| **Discontinuous predictions** | Tree splits can cause jumps; use `path_smooth` to mitigate |
| **No multi-output** | Predicts single target; train separate models for each |
| **Extrapolation limitation** | Trees can't extrapolate beyond training range; add trend features + monotonic constraints |

### Comparative Gaps
- Unlike CatBoost, no `has_time` parameter for automatic temporal ordering
- No inherent seasonality handling (must engineer sine/cosine features)
- Cannot predict outside training target range (trees clip to seen values)
