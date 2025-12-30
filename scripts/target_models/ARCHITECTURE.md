# Target Models Architecture

## Overview

This package implements a **dual-layer walk-forward ML pipeline** for 20 target-horizon combinations:
- 5 targets: `direction`, `returns`, `volatility`, `vol_regime`, `trend_regime`
- 4 horizons: 1, 3, 6, 12 bars

---

## The 20 Workflows

Each workflow is a unique target × horizon combination with its own task type:

| Target | Task Type | Horizons | Primary Metric | L2 Models |
|--------|-----------|----------|----------------|-----------|
| **volatility** | regression | 1, 3, 6, 12 | IC | CatBoostRegressor, LGBMRegressor, Ridge |
| **returns** | regression | 1, 3, 6, 12 | IC | CatBoostRegressor, LGBMRegressor, Ridge |
| **direction** | binary | 1, 3, 6, 12 | AUC | CatBoostClassifier, LGBMClassifier, LogisticRegression |
| **vol_regime** | multiclass (3) | 1, 3, 6, 12 | Accuracy | CatBoostClassifier, LGBMClassifier, LogisticRegression |
| **trend_regime** | binary | 1, 3, 6, 12 | AUC | CatBoostClassifier, LGBMClassifier, LogisticRegression |

---

## Layer 1: Helper Models (6 complex unsupervised models → 61 features)

| Helper | Model Type | Features | Package | Description |
|--------|-----------|----------|---------|-------------|
| **HMM-4** | GaussianHMM (4 states) | 9 | hmmlearn | Market regime detection |
| **HMM-5** | GaussianHMM (5 states) | 10 | hmmlearn | Volatility regime detection |
| **GARCH** | GARCH(p,q) | 6 | arch | Conditional volatility estimation |
| **Kalman** | Kalman Filter (3D state) | 7 | scipy | State estimation (trend, velocity, acceleration) |
| **CUSUM** | CUSUM Changepoint | 9 | custom | Change point detection |
| **IsolationForest** | Isolation Forest | 12 | sklearn | Anomaly detection (3 contamination levels) |
| **Interactions** | Cross-helper | 7 | - | Top feature interactions (IC-based) |

**Total: 61 helper features per target-horizon (54 base + 7 interactions)**

### IC-Based Boosting

After fitting, helpers are **optimized** using target-specific IC:
1. Compute Spearman IC for each feature vs target y
2. Weight features by |IC| / max(|IC|)
3. Drop features with |IC| < 0.02 threshold
4. Add interaction features from top-K by IC

### ICIR Feature Selection System (v2.0)

The IC-based boosting is enhanced with **ICIR (Information Coefficient Information Ratio)** for more robust feature selection.

#### Why ICIR over IC?

| Metric | Formula | What it measures |
|--------|---------|------------------|
| **IC** | Spearman(feature, target) | Single-point correlation |
| **ICIR** | mean(IC) / std(IC) | Signal consistency over time |

A feature with high IC might be spurious (worked once, won't repeat). ICIR ensures we select features with **stable, repeatable** predictive power.

#### ICIR Computation

```python
# Rolling ICIR over n windows:
for window in rolling_windows:
    ic[window] = spearman_correlation(feature[window], target[window])

icir = mean(ic_values) / std(ic_values)  # Higher = more stable
```

#### Correlation Filter (mRMR-style)

After ICIR selection, we apply **minimal redundancy** filtering:
1. Sort features by |ICIR| descending
2. For each feature, check correlation with already-selected features
3. If |correlation| > threshold (default 0.90), drop the weaker feature

#### Configuration System

All ICIR parameters are configurable via `ICIRConfig`:

```python
from scripts.target_models.helpers import ICIRConfig, DEFAULT_ICIR_CONFIG

# Default configuration
config = ICIRConfig(
    enable_icir=True,             # Master switch
    enable_correlation_filter=True,
    icir_threshold=0.30,          # Min ICIR to keep feature
    correlation_threshold=0.90,   # Max correlation between features
    n_rolling_windows=5,          # Windows for rolling ICIR
    min_samples_per_window=50,    # Min samples per window
    min_ic_threshold=0.02,        # Fallback IC threshold
    ic_top_k=30,                  # Max features to consider
)
```

#### Preset Configurations

| Preset | ICIR Threshold | Corr Threshold | Use Case |
|--------|---------------|----------------|----------|
| `DEFAULT_ICIR_CONFIG` | 0.30 | 0.90 | Balanced (recommended) |
| `ICIR_CONFIG_STRICT` | 0.50 | 0.80 | Few, highly stable features |
| `ICIR_CONFIG_LENIENT` | 0.20 | 0.95 | More features, less filtering |
| `ICIR_CONFIG_DISABLED` | N/A | N/A | Legacy IC-only mode |

#### Per-Target Configuration

```python
# In icir_config.py
TARGET_ICIR_CONFIGS = {
    "volatility": ICIRConfig(icir_threshold=0.35),  # Stricter for volatility
    "returns": ICIRConfig(icir_threshold=0.25),     # More lenient
    # ... other targets use default
}
```

#### Pipeline Integration

The ICIR system is integrated into `HelperEnsemble.optimize()`:

```python
# In ensemble.py _learn_boosting_weights()
result = select_features_full_pipeline(
    features=helper_features,
    target=y,
    config=self.icir_config,
)
# result["selected_features"] → features to use
# result["icir_scores"] → ICIR values per feature
```

#### Fallback Behavior

The system gracefully degrades:
1. **Not enough data for ICIR** → Falls back to single IC computation
2. **No features pass ICIR threshold** → Falls back to IC-based selection
3. **ICIR disabled** → Uses legacy IC-only method

#### Validation Results

Tested across all 20 targets (2025-01):

| Metric | Value |
|--------|-------|
| Average ICIR-selected features | 27.2 |
| Average legacy IC-selected | 40.5 |
| Average reduction | 32.1% |
| Targets with >30% reduction | 12/20 |

Best reductions: `volatility` (45.5%), `returns` (24.9%), `direction` (29.8%)

#### Module Structure

```
helpers/
├── icir_config.py      # ICIRConfig dataclass, presets, TARGET_ICIR_CONFIGS
├── icir_selection.py   # compute_rolling_icir, apply_correlation_filter, etc.
└── ensemble.py         # Uses select_features_full_pipeline() in optimize()
```

### Helper Feature Details

```
IsolationForest (12 features):
  - if_score_{extreme,moderate,mild}          # Anomaly scores
  - if_binary_{extreme,moderate,mild}         # Binary anomaly flags  
  - if_zscore_{extreme,moderate,mild}         # Z-scored anomaly
  - if_agreement, if_any_anomaly, if_severity # Ensemble signals

CUSUM (12 features):
  - cusum_pos_{sens,med,cons}                 # Positive CUSUM
  - cusum_neg_{sens,med,cons}                 # Negative CUSUM
  - cusum_signal_{sens,med,cons}              # Direction signals
  - cusum_change_detected, cusum_direction, cusum_magnitude

GARCH (8 features):
  - garch_cond_vol                            # Conditional volatility
  - garch_vol_forecast_{1..horizon}           # Multi-step forecasts
  - garch_vol_zscore                          # Z-scored volatility
  - garch_vol_regime                          # Regime classification
  - garch_shock                               # Standardized residual

HMM-4 Market Regime (9 features):
  - hmm4_state                                # Current state (0-3)
  - hmm4_prob_state_{0,1,2,3}                 # State probabilities
  - hmm4_entropy                              # State uncertainty
  - hmm4_transition_prob                      # Transition probability
  - hmm4_persistence                          # State persistence

HMM-5 Volatility Regime (10 features):
  - hmm5_state                                # Current state (0-4)
  - hmm5_prob_state_{0,1,2,3,4}              # State probabilities
  - hmm5_entropy                              # State uncertainty
  - hmm5_volatility_regime                    # Mapped to LOW/MED/HIGH

Kalman Filter (7 features):
  - kalman_trend                              # Filtered trend
  - kalman_velocity                           # Rate of change
  - kalman_acceleration                       # Second derivative
  - kalman_trend_zscore                       # Z-scored trend
  - kalman_velocity_zscore                    # Z-scored velocity
  - kalman_state_uncertainty                  # Covariance trace
  - kalman_innovation                         # Prediction error
```

---

## Layer 2: Supervised Model Ensemble (3 models per workflow)

| Task Type | Models | Weights |
|-----------|--------|---------|
| **regression** | CatBoostRegressor + LGBMRegressor + Ridge | 0.4 / 0.4 / 0.2 |
| **binary** | CatBoostClassifier + LGBMClassifier + LogisticRegression | 0.4 / 0.4 / 0.2 |
| **multiclass** | CatBoostClassifier + LGBMClassifier + LogisticRegression | 0.4 / 0.4 / 0.2 |

The model type (Regressor vs Classifier) is **automatically selected** based on `task_type` from `TargetSpec`.

---

```
scripts/target_models/
├── __init__.py              # Package exports
├── ARCHITECTURE.md          # This file
├── config.py                # Configuration classes (TargetConfig, CVConfig)
├── registry.py              # 20 target specs, data loading (load_target_data)
├── pipeline.py              # MAIN: PipelineOrchestrator, TargetRunner, PositionSizer
├── run_full_eval.py         # Full evaluation script
│
├── core/                    # Walk-forward window management
│   ├── __init__.py
│   ├── window.py            # Simple single-layer walk-forward (basic)
│   └── aligned_dual_window.py # MAIN: Expanding L1 + Sliding L2 windows
│
├── helpers/                 # Layer 1: Unsupervised helper models (61 features)
│   ├── __init__.py
│   ├── base.py              # BaseHelper abstract class
│   ├── ensemble.py          # HelperEnsemble (coordinates all 6 helpers)
│   ├── icir_config.py       # ICIR configuration (ICIRConfig, presets)
│   ├── icir_selection.py    # ICIR feature selection algorithms
│   ├── cusum.py             # CUSUM changepoint detection (9 features)
│   ├── garch.py             # GARCH volatility (6 features) - REQUIRES arch package
│   ├── hmm.py               # HMM regime detection (19 features: HMM4 + HMM5)
│   ├── isolation_forest.py  # Anomaly detection (12 features)
│   ├── kalman.py            # Kalman state estimation (7 features)
│   └── helper_selection.py  # Helper config selection utilities
│
└── models/                  # Layer 2: Supervised models
    ├── __init__.py
    ├── base.py              # BaseModel abstract class
    ├── ensemble.py          # ModelEnsemble (CatBoost + LightGBM + Ridge)
    ├── catboost_model.py    # CatBoost wrapper
    ├── lightgbm_model.py    # LightGBM wrapper
    └── linear.py            # Ridge/LogisticRegression wrapper
```

## Class Hierarchy

### Base Classes

| Location | Class | Purpose |
|----------|-------|---------|
| `helpers/base.py` | `BaseHelper` | L1 unsupervised helper interface |
| `models/base.py` | `BaseModel` | L2 supervised model interface |

### Pipeline Classes

```
PipelineOrchestrator
├── config: PipelineConfig
├── target_runners: dict[str, TargetRunner]  # 20 runners
│
├── run_synchronized()    # MAIN: Step-by-step all 20 targets
├── aggregate_predictions()
└── compute_positions()

TargetRunner
├── spec: TargetSpec
├── engine: AlignedDualEngine
├── helper_ensemble: HelperEnsemble
├── model_ensemble: ModelEnsemble
│
├── load_data()
├── setup_engine()
├── run_layer1()          # Fit helpers, get 58 features
└── run_iteration()       # Full L1 → L2 → prediction

PositionSizer
├── aggregate_for_timestamp()  # Combine 20 predictions
└── compute_position()         # Kelly + risk management
```

### Window Classes

```
AlignedDualEngine
├── l1_config: ExpandingL1Config
├── l2_config: SlidingL2Config
└── get_window(idx, iteration) → AlignedDualWindow

AlignedDualWindow
├── l1: ExpandingL1Window    # train + val (EXPANDING)
│   ├── train: WindowSlice
│   └── val: WindowSlice
│
└── l2: SlidingL2Window      # train + cal + val + pred (SLIDING)
    ├── train: WindowSlice
    ├── cal: WindowSlice
    ├── val: WindowSlice
    └── pred: WindowSlice
```

## Data Flow

```
                        WALK-FORWARD STEP i
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  DATA: X (166 features), y (target)                            │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    LAYER 1 (Expanding)                   │   │
│  │  [0 ──────────────────── l1_end][l1_val]                │   │
│  │   │           train           │    │                     │   │
│  │   └───────────────────────────┴────┘                     │   │
│  │                      │                                   │   │
│  │                      ▼                                   │   │
│  │         ┌────────────────────────┐                       │   │
│  │         │   HelperEnsemble       │                       │   │
│  │         │   - fit(X_train)       │                       │   │
│  │         │   - optimize(X_val, y) │                       │   │
│  │         └────────────────────────┘                       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              │ transform(X_l2) → 58 features    │
│                              ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    LAYER 2 (Sliding)                     │   │
│  │  [l2_start][──train──][cal][val][pred]                  │   │
│  │                                    │                     │   │
│  │            ┌───────────────────────┘                     │   │
│  │            ▼                                             │   │
│  │  ┌────────────────────────┐                              │   │
│  │  │   ModelEnsemble        │                              │   │
│  │  │   - fit(X_train, y)    │                              │   │
│  │  │   - calibrate(X_cal, y)│                              │   │
│  │  │   - predict(X_pred)    │ → TargetPrediction           │   │
│  │  └────────────────────────┘                              │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│              ┌───────────────────────────┐                     │
│              │   POSITION SIZING (L3)    │                     │
│              │   - Aggregate 20 targets  │                     │
│              │   - Kelly criterion       │                     │
│              │   - Risk management       │                     │
│              └───────────────────────────┘                     │
│                              │                                  │
│                              ▼                                  │
│                    PositionSizingResult                        │
└─────────────────────────────────────────────────────────────────┘
```

## Key Patterns

### Horizon Alignment

Each horizon predicts `horizon` rows. The LAST prediction targets the same bar:

```
At walk-forward step t, predicting bar t+1:
  h=1:  predict 1 row  → [t] targets t+1         ✓
  h=3:  predict 3 rows → [t-2,t-1,t] last→t+1   ✓
  h=6:  predict 6 rows → [...,t] last→t+1       ✓
  h=12: predict 12 rows → [...,t] last→t+1      ✓
```

### Fresh Helpers Per Iteration

Current behavior (pipeline.py line 469):
```python
# Create fresh ensemble for this iteration (target-specific)
self.helper_ensemble = create_helper_ensemble(...)
```

Helpers are recreated each iteration. The `partial_fit()` incremental capability exists
but is NOT used. This is intentional for simplicity - no state persistence bugs.

## External Dependencies

| Package | Required By | Purpose |
|---------|-------------|---------|
| **numpy** | All | Core array operations |
| **pandas** | All | DataFrames for features/targets |
| **polars** | registry.py | Fast parquet loading |
| **scipy** | kalman.py, base.py | Kalman filter, statistics |
| **sklearn** | All | IsolationForest, metrics, linear models |
| **catboost** | catboost_model.py | CatBoostClassifier/Regressor |
| **lightgbm** | lightgbm_model.py | LGBMClassifier/Regressor |
| **arch** | garch.py | GARCH(p,q) volatility models |
| **hmmlearn** | hmm.py | GaussianHMM for regime detection |
| **joblib** | base.py | Model serialization |

**All dependencies are required.** Install with:
```bash
pip install numpy pandas polars scipy scikit-learn catboost lightgbm arch hmmlearn joblib
```

## Usage

```python
from scripts.target_models import PipelineOrchestrator, PipelineConfig

# Configure
config = PipelineConfig(
    targets=("direction", "volatility"),  # or None for all 5
    horizons=(1, 3, 6, 12),
    backtest_rows=100,
)

# Run synchronized (all 20 targets per step)
orchestrator = PipelineOrchestrator(config)
results = orchestrator.run_synchronized(verbose=True)

# Results are PositionSizingResult objects
for r in results:
    print(f"t={r.timestamp}: pos={r.final_position:.2f}, dir={r.direction}")
```

## File Status

| File | Status | Notes |
|------|--------|-------|
| pipeline.py | ✅ ACTIVE | Main orchestration |
| registry.py | ✅ ACTIVE | Data loading |
| config.py | ✅ ACTIVE | Configuration classes |
| run_full_eval.py | ✅ ACTIVE | Evaluation script |
| core/*.py | ✅ ACTIVE | Window management |
| helpers/*.py | ✅ ACTIVE | L1 helpers |
| models/*.py | ✅ ACTIVE | L2 models |
