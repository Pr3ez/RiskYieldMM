# Phase 0.4: AlignedDualEngine Data Flow Audit

**Date**: 2025-12-24
**Status**: COMPLETE ✅

---

## Summary

| Aspect | Finding |
|--------|---------|
| **Data Flow** | L1 → Helper features → L2 |
| **Preprocessing Location** | **TWO places needed** |
| **Current State** | No preprocessing on base features |
| **Action Required** | Add preprocessing hooks at both layers |

---

## 0.4.1 Current Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         CURRENT DATA FLOW                                │
└─────────────────────────────────────────────────────────────────────────┘

ALIGNED DATA (4679 rows × 166 base features × 20 targets)
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ For prediction at timestamp T:                                           │
│                                                                          │
│ ┌────────────────────────────────┐ ┌────────────────────────────────┐   │
│ │  L1 EXPANDING (grows each iter) │ │  L2 SLIDING (fixed 500 rows)   │   │
│ │  [0 ──────────── L2_start]     │ │  [L2_start ─────────── pred]   │   │
│ │       ↑ grows                   │ │       ↑ slides →               │   │
│ └────────────────────────────────┘ └────────────────────────────────┘   │
│         │                                    │                           │
│         ▼                                    │                           │
│  ┌─────────────────┐                        │                           │
│  │ HelperEnsemble  │                        │                           │
│  │   fit()         │                        │                           │
│  │                 │                        │                           │
│  │ (58 features    │                        │                           │
│  │  generated)     │                        │                           │
│  └────────┬────────┘                        │                           │
│           │                                  │                           │
│           └──────────────────────────────────┼──────────────────────┐   │
│                                              │                      │   │
│                                              ▼                      ▼   │
│                                       ┌─────────────────────────────┐   │
│                                       │  transform(L2 data)         │   │
│                                       │  → 58 helper features       │   │
│                                       └─────────────┬───────────────┘   │
│                                                     │                   │
│                                                     ▼                   │
│                                       ┌─────────────────────────────┐   │
│                                       │  ModelEnsemble              │   │
│                                       │  CatBoost + LightGBM + Ridge│   │
│                                       │  (fit on 58 helper features)│   │
│                                       └─────────────────────────────┘   │
│                                                     │                   │
│                                                     ▼                   │
│                                       ┌─────────────────────────────┐   │
│                                       │  Prediction for timestamp T │   │
│                                       └─────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

### Key Observation: NO PREPROCESSING CURRENTLY

The current flow is:
1. **L1**: Raw base features (166) → Helpers fit → 58 helper features generated
2. **L2**: 58 helper features → Models fit → Prediction

**MISSING**: 
- Base features are NOT preprocessed before helpers
- Helper features are NOT preprocessed before models

---

## 0.4.2 Proposed Data Flow with Preprocessing

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      PROPOSED DATA FLOW WITH PREPROCESSING               │
└─────────────────────────────────────────────────────────────────────────┘

ALIGNED DATA (4679 rows × 166 base features × 20 targets)
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ For prediction at timestamp T:                                           │
│                                                                          │
│ ┌────────────────────────────────┐ ┌────────────────────────────────┐   │
│ │  L1 EXPANDING                  │ │  L2 SLIDING                     │   │
│ └────────────────────────────────┘ └────────────────────────────────┘   │
│         │                                    │                           │
│         ▼                                    │                           │
│  ┌─────────────────┐                        │                           │
│  │ BASE PREPROCESSOR ◄──────────── NEW HOOK 1                          │
│  │ (fit on L1 data)│                        │                           │
│  │ - Winsorize     │                        │                           │
│  │ - ZScore/Rank   │                        │                           │
│  └────────┬────────┘                        │                           │
│           │                                  │                           │
│           ▼                                  │                           │
│  ┌─────────────────┐                        │                           │
│  │ HelperEnsemble  │                        │                           │
│  │ fit(preprocessed)│                       │                           │
│  └────────┬────────┘                        │                           │
│           │                                  │                           │
│           └──────────────────────────────────┼──────────────────────┐   │
│                                              │                      │   │
│                                              ▼                      ▼   │
│                                       ┌─────────────────────────────┐   │
│                                       │ BASE PREPROCESSOR.transform │◄── Uses L1 stats
│                                       │ (transform L2 base features)│   │
│                                       └─────────────┬───────────────┘   │
│                                                     │                   │
│                                                     ▼                   │
│                                       ┌─────────────────────────────┐   │
│                                       │ Helpers.transform           │   │
│                                       │ → 58 helper features        │   │
│                                       └─────────────┬───────────────┘   │
│                                                     │                   │
│                                                     ▼                   │
│                                       ┌─────────────────────────────┐   │
│                                       │ HELPER PREPROCESSOR ◄────────── NEW HOOK 2
│                                       │ (for helper features only)  │   │
│                                       │ - Classification: Rank      │   │
│                                       │ - Regression: ZScore        │   │
│                                       └─────────────┬───────────────┘   │
│                                                     │                   │
│                                                     ▼                   │
│                                       ┌─────────────────────────────┐   │
│                                       │  ModelEnsemble              │   │
│                                       │  CatBoost + LightGBM + Ridge│   │
│                                       └─────────────────────────────┘   │
│                                                     │                   │
│                                                     ▼                   │
│                                       ┌─────────────────────────────┐   │
│                                       │  Prediction for timestamp T │   │
│                                       └─────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 0.4.3 WHERE Preprocessing Should Happen

### HOOK 1: Base Feature Preprocessing (Before Helpers)

**Location**: Before `HelperEnsemble.fit()` in L1 window

**What**: 
- Winsorize unbounded features (118 of 166)
- Task-specific scaling (ZScore for regression, Rank for classification)
- Pass through bounded features (48 of 166)

**When fitted**: During L1 expanding window processing
**When transformed**: On L2 data BEFORE helper transform

**Code location to modify**: Pipeline code that calls helpers

### HOOK 2: Helper Feature Preprocessing (Before Models)

**Location**: After `HelperEnsemble.transform()`, before `ModelEnsemble`

**What**:
- Winsorize helper features with leakage (18 of 58, identified in Phase 0.1)
- Task-specific scaling:
  - Returns/Volatility: Light winsorize only (helpers already produce normalized features)
  - Classification: ExpandingRank for unbounded helper features (30 of 58)

**When fitted**: On helper features from L2 train window
**When transformed**: On helper features for L2 cal/val/pred

---

## 0.4.4 Current Transform Pipeline Order

Current order (from `ensemble.py`):

```python
# In L1 fitting:
ensemble.fit(X_train)                  # Step 1: Fit helpers on raw base features
ensemble.optimize(X_cal, y_cal)        # Step 2: Learn boosting weights
ensemble.validate(X_val, y_val)        # Step 3: Validate

# In L2:
output = ensemble.transform(X_layer2)  # Step 4: Generate helper features
X_boosted = output.features            # Step 5: Get boosted features
# → Feed to ModelEnsemble
```

### Missing Steps

```python
# PROPOSED NEW ORDER:

# In L1:
base_preprocessor.fit(X_train)         # NEW: Fit base preprocessing on L1 train
X_preprocessed = base_preprocessor.transform(X_train)  # NEW: Preprocess L1
ensemble.fit(X_preprocessed)           # Helpers fit on preprocessed data
ensemble.optimize(X_cal_preprocessed, y_cal)
ensemble.validate(X_val_preprocessed, y_val)

# In L2:
X_l2_preprocessed = base_preprocessor.transform(X_l2)  # NEW: Preprocess L2 base
helper_features = ensemble.transform(X_l2_preprocessed)
helper_preprocessor.fit(helper_features.train)  # NEW: Fit helper preprocessing
helper_features_preprocessed = helper_preprocessor.transform(helper_features)  # NEW
# → Feed to ModelEnsemble
```

---

## 0.4.5 Integration Points in AlignedDualEngine

### Current Engine Flow (from `aligned_dual_window.py`)

```python
for window in AlignedDualEngine(X, y, config).iterate():
    # Window contains:
    #   window.l1.full.X  - Expanding L1 data (base features)
    #   window.l1.train.X - L1 training portion
    #   window.l1.val.X   - L1 validation portion
    #   window.l2.full.X  - Sliding L2 data (base features)
    #   window.l2.train.X - L2 training portion
    #   window.l2.cal.X   - L2 calibration portion
    #   window.l2.val.X   - L2 validation portion
    #   window.l2.pred.X  - L2 prediction row(s)
```

### Recommended Integration

```python
class TargetWorkflow:
    """Complete workflow for one target-horizon combination."""
    
    def __init__(self, target: str, horizon: int, task_type: str):
        # Preprocessors
        self.base_preprocessor = create_base_pipeline(target, task_type)
        self.helper_preprocessor = create_helper_pipeline(task_type)
        
        # Helpers
        self.helpers = HelperEnsemble(target, horizon)
        
        # Models
        self.models = ModelEnsemble(task_type)
    
    def process_window(self, window: AlignedDualWindow):
        # === L1 PROCESSING ===
        # Fit base preprocessor on L1 train (expanding)
        self.base_preprocessor.fit(window.l1.train.X)
        
        # Preprocess L1 data
        l1_preprocessed = self.base_preprocessor.transform(window.l1.full.X)
        
        # Fit helpers on preprocessed L1
        self.helpers.fit(l1_preprocessed)
        
        # === L2 PROCESSING ===
        # Preprocess L2 base features (using L1-fitted preprocessor)
        l2_preprocessed = self.base_preprocessor.transform(window.l2.full.X)
        
        # Transform to helper features
        helper_features = self.helpers.transform(l2_preprocessed)
        
        # Fit helper preprocessor on L2 train helper features
        self.helper_preprocessor.fit(helper_features.train)
        
        # Preprocess all helper features
        helper_preprocessed = self.helper_preprocessor.transform(helper_features)
        
        # === MODEL TRAINING ===
        self.models.fit(helper_preprocessed.train, window.l2.train.y)
        self.models.calibrate(helper_preprocessed.cal, window.l2.cal.y)
        
        # === PREDICTION ===
        return self.models.predict(helper_preprocessed.pred)
```

---

## 0.4.6 Key Design Decisions

### Decision 1: Separate Base vs Helper Preprocessing

**Why**: Base features and helper features have different characteristics:
- Base features: Raw computations, some already bounded, some unbounded
- Helper features: Model outputs, already somewhat normalized, but with leakage issues

**Approach**: Two separate preprocessor pipelines

### Decision 2: Fit Preprocessors on Different Data

| Preprocessor | Fit On | Transform On |
|--------------|--------|--------------|
| Base preprocessor | L1 train (expanding) | L1 full, L2 full |
| Helper preprocessor | L2 train helper features | L2 cal/val/pred |

**Why**:
- Base preprocessor uses ALL historical data (expanding) for causal stats
- Helper preprocessor uses L2 train only (to avoid contaminating cal/val)

### Decision 3: Task-Type Determines Pipeline

| Task | Base Pipeline | Helper Pipeline |
|------|---------------|-----------------|
| regression (returns) | Winsorize → RollingZScore | Winsorize only |
| regression (volatility) | Winsorize → Log → ExpandingZScore | Winsorize only |
| binary/multiclass | Winsorize → ExpandingRank | ExpandingRank |

---

## Phase 0.4 Completion Checklist

- [x] 0.4.1 Trace data flow from aligned data → L1 → L2 → prediction
- [x] 0.4.2 Identify WHERE preprocessing should happen
- [x] 0.4.3 Document current transform pipeline order
- [x] 0.4.4 Identify missing preprocessing steps

**Key Findings**:
1. **TWO preprocessing hooks needed**: Before helpers (base), after helpers (helper)
2. **Integration point**: `TargetWorkflow` class that encapsulates complete pipeline
3. **Fit/transform split**: Base preprocessor fits on L1, helper preprocessor fits on L2 train

**Status**: COMPLETE ✅

**Next**: Phase 1 — Design task-specific preprocessing pipelines
