# Multi-Model Optimization Implementation Plan

**Created:** 2026-01-19  
**Goal:** Per-model optimization with individual windows, splits, feature selection  
**Constraint:** NO future leakage - only past data available at prediction time

---

## Executive Summary

Current `l2_backtest_sync.py` uses a **shared configuration** for all 4 models. This plan outlines how to give each model its own optimization parameters while maintaining walk-forward alignment.

---

## Part 1: Current State Analysis

### Shared Settings (SyncBacktestConfig)
```python
train_window: int = 500           # All models share
train_ratio: float = 0.55         # All models share
val_ratio: float = 0.15           # All models share
cal_ratio: float = 0.30           # All models share
embargo_bars: int = 24            # All models share
```

### Current Individual Tuning
| Model | Tuning | Features |
|-------|--------|----------|
| CatBoost | Optuna (15 trials) - iterations, depth, lr, l2_leaf_reg | All 266 |
| LightGBM | Optuna (15 trials) - n_estimators, max_depth, lr, reg_lambda | All 266 |
| LSTM | Fixed (100 epochs, hidden=64, seq_len=20) | All 266 |
| Linear | Fixed (alpha=1.0) | All 266 |

**Problem:** One-size-fits-all ignores model-specific requirements!

---

## Part 2: Model-Specific Optimal Configurations

### CatBoost (GBDT)
| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Window Size | 200-400 bars | Sufficient samples per leaf |
| Split Ratios | 60/20/20 | More validation for robust tuning |
| Feature Selection | Tree importance | 40-50% of features |
| Embargo | Target horizon × 2 | No label overlap |
| Optuna Trials | 15-20 | Balance speed vs quality |

**Hyperparameter Ranges:**
- iterations: [50, 500]
- depth: [4, 10]
- learning_rate: [0.01, 0.3] (log scale)
- l2_leaf_reg: [0.1, 10.0] (log scale)
- border_count: [32, 255]

### LightGBM (GBDT)
| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Window Size | 200-400 bars | Similar to CatBoost |
| Split Ratios | 60/20/20 | Early stopping needs good val set |
| Feature Selection | Gain importance | 50-60% of features |
| Embargo | Target horizon × 2 | No label overlap |
| Optuna Trials | 15-20 | Balance speed vs quality |

**Hyperparameter Ranges:**
- n_estimators: [100, 1000] with early_stopping_rounds=50
- max_depth: [3, 12]
- num_leaves: [15, 255]
- learning_rate: [0.01, 0.3] (log scale)
- reg_lambda: [0.0, 10.0]
- min_child_samples: [5, 100]
- colsample_bytree: [0.5, 1.0]

### LSTM (RNN)
| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Window Size | 500-1000 bars | Deep learning needs more data |
| Split Ratios | 70/15/15 | Maximize training data |
| Feature Selection | Variance filter + PCA | 30-40% → reduce dimensions |
| Embargo | sequence_length × 2 | Prevent sequence overlap |
| Epochs | 50-200 with early stopping | Val loss based |

**Hyperparameter Ranges:**
- hidden_size: [32, 128]
- num_layers: [1, 3]
- dropout: [0.1, 0.5]
- learning_rate: [1e-4, 1e-2] (log scale)
- batch_size: [16, 64]
- sequence_length: [10, 40]

### Linear (Ridge/Logistic)
| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Window Size | 150-300 bars | Simple model, react faster |
| Split Ratios | 50/20/30 | More calibration (linear probs need it) |
| Feature Selection | VIF + correlation | 20-30% (handle multicollinearity) |
| Embargo | Target horizon × 2 | No label overlap |

**Hyperparameter Ranges:**
- alpha: [0.01, 100] (log scale)
- C (LogisticRegression): [0.01, 100] (log scale)

---

## Part 3: Embargo Bars by Target

From Lopez de Prado "Advances in Financial ML":
- Embargo = gap to prevent information leakage
- Labels that overlap in time should not appear in both train and test

| Target | Horizon | Look-ahead | Optimal Embargo |
|--------|---------|------------|-----------------|
| direction_1bar | 1 bar | 8 hours | 2 bars (16h) |
| direction_3bar | 3 bars | 24 hours | 4 bars (32h) |
| direction_6bar | 6 bars | 48 hours | 8 bars (64h) |
| direction_12bar | 12 bars | 96 hours | 15 bars (5 days) |

**LSTM Special Case:** Embargo should be at least 2× sequence_length to prevent sequence overlap.

---

## Part 4: Ensemble Weight Optimization

### Level 1: Per-Step Adaptive Weights (EXISTS)
```python
# Current implementation in SyncBacktestConfig
use_adaptive_weights: bool = False
adaptive_lookback: int = 50  # Rolling window for performance
```
- Track rolling accuracy/IC for each model
- Use Multiplicative Weights Update (MWU)
- Formula: `w_new = w_old × exp(η × performance)`

### Level 2: Per-Target Base Weights (NEW)
Different targets have different model affinities:
- **direction:** Tree models may excel (nonlinear boundaries)
- **volatility:** Linear may be strong (vol clustering is linear)
- **regime:** LSTM may capture transitions better

**Algorithm:**
1. Accumulate per-model predictions over first N steps (e.g., N=100)
2. At step N, compute optimal weights via constrained least squares:
   ```
   min_w ||y_true - Σ w_i × pred_i||² 
   subject to: Σw_i = 1, w_i >= 0
   ```
3. Use these as new base weights
4. Re-optimize every M steps (e.g., M=200)

### Level 3: Regime-Aware Weights (NEW)
- **High volatility:** Increase LSTM weight (captures patterns)
- **Low volatility:** Increase Linear weight (stable baseline)
- **Trending:** Increase GBDT weight (captures momentum)

Use `vol_regime` and `trend_regime` predictions to gate weights:
```python
if vol_regime_pred == 0:  # LOW volatility
    weights = shift_toward_linear(base_weights)
elif vol_regime_pred == 2:  # HIGH volatility
    weights = shift_toward_lstm(base_weights)
```

---

## Part 5: Feature Selection Strategies

| Model | Strategy | % Features | Method |
|-------|----------|------------|--------|
| CatBoost | Tree importance | 40-50% | PredictionValuesChange |
| LightGBM | Gain importance | 50-60% | feature_importance(type=gain) |
| LSTM | Variance filter | 30-40% | Drop low-variance + PCA |
| Linear | Correlation filter | 20-30% | VIF < 5 + top correlations |

### Implementation Principles
1. Compute feature selection WITHIN training window only (no leakage)
2. Apply selected features to that model's training/prediction
3. Store which features were selected for post-hoc analysis
4. Track feature stability across steps (features that flip often = noise)

---

## Part 6: Comprehensive Metrics Storage

### Currently Stored (Per Step)
- cb_pred, lgb_pred, lstm_pred, linear_pred
- cb_prob, lgb_prob, lstm_prob, linear_prob
- cb_iterations, cb_depth, lgb_n_estimators, lgb_max_depth

### Missing (To Add)
```python
# Per-Model Training Metrics
cb_train_time: float
lgb_train_time: float
lstm_train_time: float
linear_train_time: float

cb_n_features: int
lgb_n_features: int
lstm_n_features: int
linear_n_features: int

cb_window_size: int
lgb_window_size: int
lstm_window_size: int
linear_window_size: int

cb_feature_importance: dict  # Top 10 features
lgb_feature_importance: dict
lstm_val_loss_final: float
lstm_epochs_run: int
linear_coefficients: list

# Per-Step Diagnostics
model_agreement_cb_lgb: float  # % same prediction
model_agreement_cb_lstm: float
model_agreement_lgb_lstm: float
feature_drift_score: float  # PSI of features vs previous
label_drift_score: float  # Class distribution change
optuna_best_trial_value: float
optuna_n_trials_completed: int

# Cumulative Analysis
rolling_accuracy_cb_20: float  # EMA with span=20
rolling_accuracy_lgb_20: float
rolling_accuracy_lstm_20: float
rolling_accuracy_linear_20: float
rolling_ic_cb_20: float
rolling_ic_lgb_20: float
model_rank_history: list  # Which model was best at each step
regime_at_prediction: dict  # vol_regime, trend_regime for analysis
```

---

## Part 7: Implementation Plan

### Phase 1: Architecture Refactor (2-3 hours)
**File:** `scripts/target_models/validation/l2_backtest_sync.py`

Create new dataclass:
```python
@dataclass
class PerModelConfig:
    window_size: int           # Different per model
    train_ratio: float
    val_ratio: float
    cal_ratio: float
    embargo_bars: int          # Based on target horizon
    feature_selection: str     # 'tree_importance', 'variance', 'correlation'
    feature_pct: float         # Percentage of features to keep
    hyperparams: dict          # Model-specific tunables
    optuna_trials: int         # Tuning intensity per model
    optuna_timeout: float      # Timeout per model

@dataclass
class ModelEnsembleConfig:
    catboost: PerModelConfig
    lightgbm: PerModelConfig
    lstm: PerModelConfig
    linear: PerModelConfig
    
    @classmethod
    def default_for_target(cls, target_horizon: int) -> 'ModelEnsembleConfig':
        """Create default config based on target horizon."""
        base_embargo = max(2, target_horizon * 2)
        return cls(
            catboost=PerModelConfig(
                window_size=300,
                train_ratio=0.60,
                val_ratio=0.20,
                cal_ratio=0.20,
                embargo_bars=base_embargo,
                feature_selection='tree_importance',
                feature_pct=0.45,
                ...
            ),
            # ... similar for other models
        )
```

### Phase 2: Per-Model Windows (3-4 hours)
- Separate window extraction for each model
- Handle different window starts for pred_idx alignment
- LSTM gets longer window (e.g., 800 bars)
- Linear gets shorter window (e.g., 200 bars)

**Key Challenge:** Different windows mean different starting points. Solution:
```python
# Find common prediction index that all models can predict
min_required = max(
    cb_config.window_size,
    lgb_config.window_size,
    lstm_config.window_size,
    linear_config.window_size
)
start_pred_idx = min_required
```

### Phase 3: Feature Selection Module (2-3 hours)
**New File:** `scripts/target_models/validation/feature_selection.py`

```python
def tree_importance_selection(model, X, y, pct: float) -> list[str]:
    """Select top pct% features by tree importance."""
    
def variance_selection(X, pct: float) -> list[str]:
    """Drop low-variance features, keep top pct%."""
    
def vif_selection(X, threshold: float = 5.0) -> list[str]:
    """Remove features with VIF > threshold."""
    
def apply_feature_selection(
    X: pd.DataFrame,
    method: str,
    pct: float,
    model: Any = None,
    y: pd.Series = None
) -> tuple[pd.DataFrame, list[str]]:
    """Apply feature selection and return (filtered_X, selected_features)."""
```

### Phase 4: Comprehensive Metrics Storage (2-3 hours)
- Extend predictions dict with all new fields
- Create separate parquet files for detailed analysis
- Add rolling metrics computation

### Phase 5: Ensemble Weight Optimization (3-4 hours)
- Implement constrained least squares for Level 2
- Implement regime-aware gating for Level 3
- Store weight history for analysis

### Phase 6: Testing and Validation (2-3 hours)
- Run on subset (step_size=50) to verify no leakage
- Compare metrics vs baseline (current single-window approach)
- Validate predictions are aligned correctly

---

## Part 8: Data Flow Diagram

```
                          COMBINED DATASET (266 features)
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        │                           │                           │
        ▼                           ▼                           ▼
┌───────────────┐          ┌───────────────┐          ┌───────────────┐
│ CB Window:300 │          │ LSTM Window:800│         │ Lin Window:200│
│ train/val/cal │          │ train/val/cal │          │ train/val/cal │
│ embargo:h×2   │          │ embargo:seq×2 │          │ embargo:h×2   │
└───────────────┘          └───────────────┘          └───────────────┘
        │                           │                           │
        ▼                           ▼                           ▼
┌───────────────┐          ┌───────────────┐          ┌───────────────┐
│ Feature Sel:  │          │ Feature Sel:  │          │ Feature Sel:  │
│ Tree Imp 45%  │          │ Variance 35%  │          │ VIF 25%       │
└───────────────┘          └───────────────┘          └───────────────┘
        │                           │                           │
        ▼                           ▼                           ▼
┌───────────────┐          ┌───────────────┐          ┌───────────────┐
│ Optuna Tune   │          │ Train LSTM    │          │ Fit Ridge     │
│ 15 trials     │          │ early stop    │          │ Tune alpha    │
└───────────────┘          └───────────────┘          └───────────────┘
        │                           │                           │
        ▼                           ▼                           ▼
┌───────────────┐          ┌───────────────┐          ┌───────────────┐
│ cb_pred       │          │ lstm_pred     │          │ linear_pred   │
│ + metrics     │          │ + metrics     │          │ + metrics     │
└───────────────┘          └───────────────┘          └───────────────┘
        │                           │                           │
        └───────────────────────────┼───────────────────────────┘
                                    │
                                    ▼
                    ┌───────────────────────────────┐
                    │   ENSEMBLE COMBINATION         │
                    │  weights: per-target optimized │
                    │  regime-aware adjustment       │
                    └───────────────────────────────┘
```

---

## Part 9: Risks and Mitigations

### Risk 1: Complexity Increase
**Mitigation:** Incremental implementation with tests after each phase

### Risk 2: Prediction Alignment
**Mitigation:** All models predict same `pred_idx`, just use different windows

### Risk 3: Computational Overhead
**Mitigation:** Cache feature selection within step, parallel model training

### Risk 4: Feature Selection Leakage
**Mitigation:** Selection computed ONLY on training split, NEVER on val/cal/test

---

## Estimated Total Effort

| Phase | Hours | Priority |
|-------|-------|----------|
| 1. Architecture | 2-3 | HIGH |
| 2. Per-model windows | 3-4 | HIGH |
| 3. Feature selection | 2-3 | MEDIUM |
| 4. Metrics storage | 2-3 | MEDIUM |
| 5. Weight optimization | 3-4 | MEDIUM |
| 6. Testing | 2-3 | HIGH |
| **TOTAL** | **15-20** | |

---

## References

1. Lopez de Prado, M. (2018). *Advances in Financial Machine Learning* - Purged k-fold CV, Embargo
2. Lopez de Prado, M. (2020). *Machine Learning for Asset Managers* - CPCV methodology
3. Neptune.ai CatBoost tuning guide - Depth 6-10 optimal
4. arXiv papers on LSTM sequence length optimization
5. Multiplicative Weights Update (MWU) for adaptive ensemble weighting
