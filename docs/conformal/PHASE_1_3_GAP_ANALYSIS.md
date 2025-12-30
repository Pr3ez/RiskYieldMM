# Phase 1.3: Pipeline Gap Analysis

**Status**: ✅ COMPLETE  
**Date**: 2025-12-23  
**Purpose**: Document current pipeline structure and identify gaps for MAPIE/ACI integration

---

## 1. Current Pipeline Architecture

### 1.1 Data Flow Overview

```
┌────────────────────────────────────────────────────────────────────────────┐
│                         CURRENT PIPELINE ARCHITECTURE                       │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  INPUT: 5,438 rows, 5 years of data (2021-2025)                           │
│         20 configs (5 targets × 4 horizons)                                │
│                                                                            │
│  ┌─────────────────────── LAYER 1 (Expanding) ────────────────────────┐   │
│  │  Helpers: HMM-4, HMM-5, GARCH, IsolationForest, Kalman, CUSUM      │   │
│  │  Window: [0 ──────────────────────────────── L2_start]             │   │
│  │  Output: 58 features per sample                                     │   │
│  └────────────────────────────────────────────────────────────────────┘   │
│                                    ↓                                       │
│  ┌─────────────────────── LAYER 2 (Sliding) ──────────────────────────┐   │
│  │  Window Size: 500 rows total (configurable)                         │   │
│  │                                                                      │   │
│  │  ┌──────────┐ ┌────┐ ┌─────┐ ┌─────┐ ┌──────┐                       │   │
│  │  │  TRAIN   │ │PURGE│ │ CAL │ │ VAL │ │ PRED │                       │   │
│  │  │   70%    │ │  21 │ │ 15% │ │ 15% │ │  H   │                       │   │
│  │  │  ~350    │ │ gap │ │ ~75 │ │ ~75 │ │      │                       │   │
│  │  └──────────┘ └────┘ └─────┘ └─────┘ └──────┘                       │   │
│  │                                                                      │   │
│  │  Models: CatBoost (40%), LightGBM (40%), Linear (20%)               │   │
│  └────────────────────────────────────────────────────────────────────┘   │
│                                    ↓                                       │
│  ┌─────────────────────── ENSEMBLE OUTPUT ────────────────────────────┐   │
│  │  • y_pred: np.ndarray              Point predictions                │   │
│  │  • y_prob: np.ndarray | None       Raw probabilities                │   │
│  │  • y_prob_calibrated: np.ndarray   Isotonic-calibrated (cls only)   │   │
│  │  • model_outputs: dict             Per-model predictions            │   │
│  │  • weights: dict                   Model weights                    │   │
│  └────────────────────────────────────────────────────────────────────┘   │
│                                    ↓                                       │
│  ┌─────────────────────── POSITION SIZING ────────────────────────────┐   │
│  │  Uses: direction_prob, expected_return, expected_volatility         │   │
│  │  Output: final_position ∈ [0.0, 2.0]                                │   │
│  └────────────────────────────────────────────────────────────────────┘   │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Key Files

| File | Purpose |
|------|---------|
| `scripts/target_models/pipeline.py` | Main orchestrator (1242 lines) |
| `scripts/target_models/core/aligned_dual_window.py` | Window management (653 lines) |
| `scripts/target_models/models/ensemble.py` | L2 ModelEnsemble (391 lines) |
| `scripts/target_models/helpers/ensemble.py` | L1 HelperEnsemble (673 lines) |

---

## 2. Current Calibration Window Analysis

### 2.1 L2 Window Configuration

From `SlidingL2Config` in `aligned_dual_window.py`:

```python
@dataclass
class SlidingL2Config:
    window_size: int = 500      # Total L2 window size
    train_ratio: float = 0.7    # 70% for training = 350 rows
    cal_ratio: float = 0.15     # 15% for calibration = 75 rows
    val_ratio: float = 0.15     # 15% for validation = 75 rows
    purge_gap: int = 21         # Gap between train and cal
```

### 2.2 Actual Cal Window Size Calculation

From `SlidingL2Config.get_splits()`:
```python
def get_splits(self) -> tuple[int, int, int]:
    train_size = int(self.window_size * self.train_ratio)  # 350
    cal_size = int(self.window_size * self.cal_ratio)      # 75
    val_size = self.window_size - train_size - cal_size - self.purge_gap
    return train_size, cal_size, val_size
```

### 2.3 Current Cal Window Sizes

| Config Setting | Window Size | Cal Ratio | **Cal Size** |
|---------------|-------------|-----------|--------------|
| Default (500) | 500 | 15% | **75 rows** |
| Documented (~20) | ~133 | 15% | **~20 rows** |

⚠️ **DISCREPANCY FOUND**: 
- Code default: 75 samples (15% of 500)
- Session.md mention: "~20 samples"
- Both are **TOO SMALL** for MAPIE (needs 100+)

### 2.4 Configurable Via PipelineConfig

From `pipeline.py`:
```python
@dataclass
class PipelineConfig:
    # Layer 2 (supervised) config
    l2_train_size: int = 500
    l2_cal_size: int = 100   # NOTE: This is IGNORED in favor of ratio
    l2_val_size: int = 100   # NOTE: This is IGNORED in favor of ratio
```

⚠️ **BUG FOUND**: `l2_cal_size` in PipelineConfig is **NOT USED** by SlidingL2Config - it uses ratios instead!

---

## 3. Where Calibration Currently Happens

### 3.1 Probability Calibration (Isotonic)

From `pipeline.py` lines 574-576:
```python
# Step 4: Calibrate on L2 cal (classification only)
if spec.task_type in ["binary", "multiclass"]:
    model_ensemble.calibrate(X_cal, y_cal, method="isotonic")
```

From `ensemble.py` lines 173-191:
```python
def calibrate(
    self,
    X: pd.DataFrame | np.ndarray,
    y: pd.Series | np.ndarray,
    method: str = "isotonic",
) -> "ModelEnsemble":
    """Calibrate all classification models."""
    if not self.config.is_classification:
        return self  # No-op for regression

    for name, model in self.models.items():
        model.calibrate(X, y, method=method)

    self._calibrated = True
```

### 3.2 Current Calibration Flow

```
Walk-Forward Iteration i:
│
├── L1 Fit (expanding window)
│   └── Helpers fitted on [0, L2_start]
│
├── L2 Fit (sliding window)
│   ├── X_train, y_train: 350 rows
│   ├── [purge_gap: 21 rows]
│   ├── X_cal, y_cal: 75 rows ← PROBABILITY CALIBRATION HERE
│   └── X_val, y_val: 75 rows
│
├── Models fitted on train
├── Models calibrated on cal (isotonic/platt)
├── Predict on pred rows
│
└── Output: EnsembleOutput(y_pred, y_prob, y_prob_calibrated)
```

### 3.3 What Current Calibration Does

- **Isotonic Regression**: Maps raw probabilities to calibrated probabilities
- **Per-model**: Each of CatBoost, LightGBM, Linear calibrated separately
- **Then averaged**: Ensemble combines calibrated probabilities

**This is NOT conformal prediction!** This is probability calibration.

---

## 4. Ensemble Output Format

### 4.1 Layer 2 ModelEnsemble Output

From `ensemble.py`:
```python
@dataclass
class EnsembleOutput:
    y_pred: np.ndarray              # Point predictions
    y_prob: np.ndarray | None       # Ensemble probability (classification)
    y_prob_calibrated: np.ndarray | None  # Calibrated ensemble probability
    
    model_outputs: dict[str, ModelOutput]  # Per-model outputs
    weights: dict[str, float]              # Model weights
    metadata: dict[str, Any]               # Config info
```

### 4.2 Per-Model Output

From `models/base.py`:
```python
@dataclass
class ModelOutput:
    y_pred: np.ndarray
    y_prob: np.ndarray | None
    y_prob_calibrated: np.ndarray | None
```

### 4.3 Pipeline Target Prediction

From `pipeline.py`:
```python
@dataclass
class TargetPrediction:
    target: str
    horizon: int
    task_type: str
    
    y_pred: np.ndarray      # All predictions [horizon]
    y_prob: np.ndarray | None  # Probabilities [horizon]
    y_true: np.ndarray | None  # Ground truth (if available)
    
    @property
    def aligned_pred(self) -> float:
        """Last prediction (aligned across horizons)."""
        return float(self.y_pred[-1])
    
    @property
    def aligned_prob(self) -> float | None:
        """Last probability (aligned)."""
```

---

## 5. Gap Analysis: What Needs to Change

### 5.1 CRITICAL GAP: Calibration Sample Size

| Requirement | Current | MAPIE Needs | Gap |
|-------------|---------|-------------|-----|
| Cal samples (default) | 75 | 100+ | **+33%** |
| Cal samples (mentioned) | ~20 | 100+ | **+400%** |
| Cal samples (stable) | 75 | 150-200 | **+100-166%** |

**Options to Address** (Phase 3 will evaluate):
- A) Expand cal_ratio to 25-30% (reduces train size)
- B) Expand total window to 700-800 rows
- C) Use cumulative calibration (all past predictions)
- D) Use rolling calibration window (last N predictions)
- E) Post-hoc calibration after all training

### 5.2 GAP: No Conformal Prediction Layer

Current pipeline produces:
```python
EnsembleOutput:
    y_pred: [0, 1, 1, 0, ...]        # Point predictions
    y_prob: [[0.3, 0.7], ...]        # Probabilities
    y_prob_calibrated: [[0.35, 0.65], ...]  # Calibrated probs
```

MAPIE needs to add:
```python
ExtendedEnsembleOutput:
    # Existing
    y_pred: np.ndarray
    y_prob: np.ndarray | None
    y_prob_calibrated: np.ndarray | None
    
    # NEW: Conformal fields
    y_pred_set: np.ndarray        # Boolean [n, n_classes] for classification
    y_interval: np.ndarray        # [n, 2] for regression (lower, upper)
    uncertainty: np.ndarray       # Set size or interval width
    current_alpha: float          # Current alpha (may adapt with ACI)
```

### 5.3 GAP: No ACI State Tracking

For ACI, need to track per-target adaptive alpha:
```python
class ACIState:
    alpha_t: dict[str, float] = {
        "direction_1bar": 0.1,
        "direction_3bar": 0.1,
        "returns_1bar": 0.1,
        # ... 20 total
    }
    gamma: float = 0.04
```

### 5.4 GAP: Pipeline Integration Points

Need to add conformal prediction **between L2 ensemble and position sizer**:

```
Current:
    L2 Ensemble → Position Sizer

Proposed:
    L2 Ensemble → CONFORMAL LAYER → Position Sizer
                       │
                       ├── Classification: SplitConformalClassifier
                       ├── Regression: TimeSeriesRegressor (EnbPI/ACI)
                       └── ACI: Adaptive alpha tracking
```

---

## 6. Specific Code Changes Required

### 6.1 Window Configuration Fix

**File**: `scripts/target_models/core/aligned_dual_window.py`

Current (ratio-based):
```python
class SlidingL2Config:
    cal_ratio: float = 0.15  # 15% = 75 rows
```

Option 1 - Increase ratio:
```python
class SlidingL2Config:
    cal_ratio: float = 0.25  # 25% = 125 rows
```

Option 2 - Use absolute size:
```python
class SlidingL2Config:
    cal_size: int = 150  # Absolute, not ratio
```

### 6.2 EnsembleOutput Extension

**File**: `scripts/target_models/models/ensemble.py`

```python
@dataclass
class EnsembleOutput:
    # Existing
    y_pred: np.ndarray
    y_prob: np.ndarray | None
    y_prob_calibrated: np.ndarray | None
    model_outputs: dict[str, ModelOutput]
    weights: dict[str, float]
    metadata: dict[str, Any]
    
    # NEW: Conformal fields
    y_pred_set: np.ndarray | None = None       # Classification
    y_interval: np.ndarray | None = None       # Regression
    conformal_alpha: float | None = None       # Current alpha
    uncertainty: np.ndarray | None = None      # Quantified uncertainty
```

### 6.3 New Module Structure

**Directory**: `scripts/target_models/calibration/`

```
calibration/
├── __init__.py
├── config.py          # ConformalConfig dataclass
├── classifier.py      # ConformalClassifier (wraps MAPIE)
├── regressor.py       # ConformalRegressor (wraps MAPIE TimeSeriesRegressor)
├── aci.py             # AdaptiveConformalInference state tracker
└── wrapper.py         # sklearn wrapper for ModelEnsemble
```

### 6.4 Pipeline Integration

**File**: `scripts/target_models/pipeline.py`

Add after model fitting, before prediction return:

```python
def run_iteration(self, window: DualLayerWindow) -> TargetPrediction:
    # ... existing code ...
    
    # Step 5: Conformal prediction (NEW)
    if self.conformal_enabled:
        conformal_output = self.conformal_predictor.predict(
            X_pred, 
            ensemble_output,
            alpha=self.current_alpha
        )
        # Update ACI if enabled
        if self.aci_enabled:
            self.aci_tracker.update(
                predicted=conformal_output.coverage,
                actual=y_true,
                gamma=self.aci_gamma
            )
    
    # ... return prediction ...
```

---

## 7. Summary: Key Gaps

| # | Gap | Impact | Phase to Address |
|---|-----|--------|------------------|
| 1 | Cal window too small (75 vs 100+) | MAPIE won't work well | Phase 3 |
| 2 | No conformal prediction layer | No uncertainty quantification | Phase 7 |
| 3 | No ACI state tracking | Can't adapt to distribution shift | Phase 7 |
| 4 | EnsembleOutput missing conformal fields | Can't pass uncertainty downstream | Phase 6-7 |
| 5 | l2_cal_size config ignored | Can't configure via PipelineConfig | Phase 7 |
| 6 | No sklearn wrapper for ensemble | MAPIE can't wrap our models | Phase 2 |

---

## 8. Phase 1.3 Deliverables ✅

1. ✅ **Mapped where calibration happens**: L2 window, isotonic regression on ~75 samples
2. ✅ **Identified cal window sizes**: 75 (default) to ~20 (documented), both too small
3. ✅ **Documented ensemble output format**: EnsembleOutput with y_pred, y_prob, y_prob_calibrated
4. ✅ **Gap analysis complete**: 6 gaps identified with phases to address

---

## 9. Next Steps

**Phase 2.1: Install MAPIE**
- pip install mapie
- Verify imports work
- Check version >= 0.8

**Phase 2.2-2.4: Compatibility Tests**
- Test CatBoost, LightGBM with MAPIE
- Create sklearn wrapper for ModelEnsemble

---

## References

- `scripts/target_models/pipeline.py` - Main pipeline orchestrator
- `scripts/target_models/core/aligned_dual_window.py` - Window configuration
- `scripts/target_models/models/ensemble.py` - L2 model ensemble
- Phase 1.1: MAPIE API Research
- Phase 1.2: ACI Paper Study
