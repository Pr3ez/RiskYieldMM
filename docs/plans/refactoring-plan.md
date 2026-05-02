# 🏗️ REFACTORING PLAN: l2_backtest_sync.py Modularization

**Created:** 2026-01-19
**Purpose:** Split 2941-line god module into maintainable modules
**Approach:** Strangler Fig (gradual migration, never big-bang)

---

## ⚠️ CRITICAL VALIDATION RULES

**EVERY extraction follows this pattern:**
1. **BEFORE:** Record exact line numbers, count lines, hash content
2. **EXTRACT:** Copy to new file (DO NOT delete yet)
3. **VERIFY:** New file has EXACT same content (diff)
4. **IMPORT:** Add import in original file, verify works
5. **REMOVE:** Delete old code from original
6. **VALIDATE:** Full import test, check no conflicts
7. **DOCUMENT:** Update line counts, mark complete

**If ANY step fails → STOP and fix before continuing**

---

## 📊 CURRENT STATE

```
scripts/target_models/validation/
├── l2_backtest_sync.py          ← 2941 lines (GOD MODULE)
├── _archived_functions.py       ← Dead functions moved here (499 lines)
└── backtest/                    ← Modular package target
```

**Line counts by section (current):**
| Section | Lines | % | Description |
|---------|-------|---|-------------|
| Imports | 1-50 | 2% | stdlib, numpy, pandas, torch, etc |
| Comments/Docs | 51-125 | 3% | Header comments, target descriptions |
| LSTM Models | 126-400 | 9% | LSTMClassifier, LSTMRegressor, sequences |
| Config Classes | 401-650 | 8% | SyncBacktestConfig, PerModelConfig, defaults |
| Data Classes | 651-900 | 8% | ConfigData, parsing, loading |
| Utilities | 901-1040 | 5% | Embargo, clipping, timestamps |
| Per-Model Training | 1041-2150 | 38% | Classification + regression per-model |
| Optuna Tuning | 2151-2300 | 5% | CB/LGB tuners |
| Metrics | 2301-2400 | 3% | Metrics computation |
| Orchestration | 2401-2941 | 19% | run_sync_backtest(), main loop |

---

## 🎯 TARGET STRUCTURE

```
scripts/target_models/validation/
├── backtest/                    ← NEW PACKAGE
│   ├── __init__.py             ← Public exports
│   │
│   ├── domain/                 ← DATA STRUCTURES (no logic)
│   │   ├── __init__.py
│   │   ├── config.py           ← SyncBacktestConfig, PerModelConfig
│   │   └── types.py            ← ConfigData, type aliases
│   │
│   ├── core/                   ← PURE LOGIC (no I/O)
│   │   ├── __init__.py
│   │   ├── ensemble.py         ← Weights, adaptive MWU
│   │   ├── metrics.py          ← Metric computation
│   │   └── splits.py           ← Embargo, split ratios
│   │
│   ├── models/                 ← MODEL DEFINITIONS
│   │   ├── __init__.py
│   │   └── lstm.py             ← LSTM classes, sequences
│   │
│   ├── adapters/               ← I/O, SIDE EFFECTS
│   │   ├── __init__.py
│   │   ├── data_loader.py      ← Load config data, timestamps
│   │   └── output.py           ← DualOutput, file writing
│   │
│   └── services/               ← ORCHESTRATION
│       ├── __init__.py
│       ├── training.py         ← _train_predict_* functions
│       ├── tuning.py           ← Optuna tuners
│       └── backtest.py         ← run_sync_backtest()
│
├── l2_backtest_sync.py          ← THIN FACADE (re-exports from backtest/)
└── _archived_functions.py       ← Keep for reference
```

---

## 📋 DETAILED EXTRACTION PLAN

### Phase 0: Safety Baseline ⬜

**Before ANY changes:**
```bash
# 1. Verify imports work
python -c "from scripts.target_models.validation.l2_backtest_sync import run_sync_backtest, SyncBacktestConfig"

# 2. Record file size
wc -l scripts/target_models/validation/l2_backtest_sync.py  # Should be 2941

# 3. If a temporary local backup is needed, keep it untracked.
git status --short
```

**Output:** ✅ or ❌ for each check

---

## 📋 PHASE-BY-PHASE EXTRACTION WITH VALIDATION

---

### Phase 0: Safety Baseline ⬜

**Checklist:**
- [ ] 0.1 Run: `python -c "from scripts.target_models.validation.l2_backtest_sync import run_sync_backtest, SyncBacktestConfig; print('OK')"`
- [ ] 0.2 Record: `wc -l scripts/target_models/validation/l2_backtest_sync.py` → Expected: 2941
- [ ] 0.3 Verify any temporary backup files are untracked: `git status --short`
- [ ] 0.4 Record git status (any uncommitted changes?)

**STOP if any check fails**

---

### Phase 1: Create Package Structure ⬜

**1.1 Create directories:**
- [ ] `mkdir -p scripts/target_models/validation/backtest/{domain,core,models,adapters,services}`

**1.2 Create empty __init__.py files:**
- [ ] `touch scripts/target_models/validation/backtest/__init__.py`
- [ ] `touch scripts/target_models/validation/backtest/domain/__init__.py`
- [ ] `touch scripts/target_models/validation/backtest/core/__init__.py`
- [ ] `touch scripts/target_models/validation/backtest/models/__init__.py`
- [ ] `touch scripts/target_models/validation/backtest/adapters/__init__.py`
- [ ] `touch scripts/target_models/validation/backtest/services/__init__.py`

**1.3 Verify:**
- [ ] `python -c "from scripts.target_models.validation.backtest import *; print('Package OK')"`

---

### Phase 2: Extract domain/config.py ⬜

#### 2.1 BEFORE (Record what we're moving)
- [ ] Identify exact lines for `class PerModelConfig`: Lines ____-____
- [ ] Identify exact lines for `DEFAULT_CB_CONFIG`: Lines ____-____
- [ ] Identify exact lines for `DEFAULT_LGB_CONFIG`: Lines ____-____
- [ ] Identify exact lines for `DEFAULT_LSTM_CONFIG`: Lines ____-____
- [ ] Identify exact lines for `DEFAULT_LINEAR_CONFIG`: Lines ____-____
- [ ] Identify exact lines for `class SyncBacktestConfig`: Lines ____-____
- [ ] Total lines to move: ____ lines
- [ ] Record md5sum of these lines: `sed -n 'START,ENDp' FILE | md5sum`

#### 2.2 EXTRACT (Copy to new file)
- [ ] Create `backtest/domain/config.py` with proper imports header
- [ ] Copy `PerModelConfig` class (EXACT copy, no changes)
- [ ] Copy `DEFAULT_*_CONFIG` constants (EXACT copy, no changes)
- [ ] Copy `SyncBacktestConfig` class (EXACT copy, no changes)
- [ ] Add required imports at top

#### 2.3 VERIFY (Exact match)
- [ ] Compare content: `diff <(sed -n 'X,Yp' old.py) <(sed -n 'A,Bp' new.py)`
- [ ] Diff should show ONLY import differences, not code changes
- [ ] `python -c "from scripts.target_models.validation.backtest.domain.config import SyncBacktestConfig; print('OK')"`

#### 2.4 IMPORT (Add import to original)
- [ ] Add to l2_backtest_sync.py: `from .backtest.domain.config import (...)`
- [ ] `python -c "from scripts.target_models.validation.l2_backtest_sync import SyncBacktestConfig; print('OK')"`

#### 2.5 REMOVE (Delete old code)
- [ ] Comment out old code FIRST (don't delete yet)
- [ ] Verify imports still work
- [ ] Delete commented code
- [ ] `wc -l l2_backtest_sync.py` → Should be ~300 lines less

#### 2.6 VALIDATE (Check for conflicts)
- [ ] `grep -n "PerModelConfig\|SyncBacktestConfig" l2_backtest_sync.py` → Only imports
- [ ] `python -c "from scripts.target_models.validation.l2_backtest_sync import run_sync_backtest"` → OK
- [ ] Check workflow/config.py still works (uses SyncBacktestConfig)

#### 2.7 DOCUMENT
- [ ] Update line count: l2_backtest_sync.py now ____ lines
- [ ] Mark Phase 2 complete ✅

---

### Phase 3: Extract core/ensemble.py ⬜

#### 3.1 BEFORE
- [ ] Identify `_update_adaptive_weights` in _archived_functions.py: Lines ____-____
- [ ] Identify `_compute_sample_weights` in _archived_functions.py: Lines ____-____
- [ ] Record line count: ____ lines total
- [ ] Document: These are currently DEAD CODE, will be wired up in Phase 7

#### 3.2 EXTRACT
- [ ] Create `backtest/core/ensemble.py`
- [ ] Copy `_update_adaptive_weights()` from archive
- [ ] Copy `_compute_sample_weights()` from archive
- [ ] Add new `compute_ensemble()` helper function
- [ ] Add new `AdaptiveWeightTracker` class

#### 3.3 VERIFY
- [ ] Functions are syntactically correct: `python -c "from scripts.target_models.validation.backtest.core.ensemble import _update_adaptive_weights"`
- [ ] No import errors

#### 3.4 IMPORT
- [ ] Update `backtest/core/__init__.py` with exports
- [ ] NOTE: Don't import in l2_backtest_sync.py YET (will do in Phase 7)

#### 3.5 DOCUMENT
- [ ] Mark Phase 3 complete ✅

---

### Phase 4: Extract core/metrics.py ⬜

#### 4.1 BEFORE
- [ ] Identify `_build_step_metrics`: Lines ____-____
- [ ] Identify `_compute_config_metrics`: Lines ____-____
- [ ] Record total lines: ____
- [ ] md5sum of lines

#### 4.2 EXTRACT
- [ ] Create `backtest/core/metrics.py`
- [ ] Copy functions EXACTLY
- [ ] Add required imports

#### 4.3 VERIFY
- [ ] `diff` shows only import differences
- [ ] `python -c "from scripts.target_models.validation.backtest.core.metrics import _build_step_metrics"`

#### 4.4 IMPORT
- [ ] Add import to l2_backtest_sync.py
- [ ] Verify: `python -c "from scripts.target_models.validation.l2_backtest_sync import run_sync_backtest"`

#### 4.5 REMOVE
- [ ] Comment out old code
- [ ] Verify still works
- [ ] Delete old code
- [ ] `wc -l` → ____ lines

#### 4.6 VALIDATE
- [ ] `grep -n "_build_step_metrics\|_compute_config_metrics" l2_backtest_sync.py` → Only imports
- [ ] Full import test passes

#### 4.7 DOCUMENT
- [ ] Mark Phase 4 complete ✅

---

### Phase 5: Extract models/lstm.py ⬜

#### 5.1 BEFORE
- [ ] `class LSTMClassifier`: Lines ____-____
- [ ] `class LSTMRegressor`: Lines ____-____
- [ ] `_create_sequences()`: Lines ____-____
- [ ] `_train_lstm_classifier()`: Lines ____-____
- [ ] `_train_lstm_regressor()`: Lines ____-____
- [ ] Total: ____ lines
- [ ] Dependencies: torch, torch.nn, numpy, StandardScaler

#### 5.2 EXTRACT
- [ ] Create `backtest/models/lstm.py`
- [ ] Copy all 5 items EXACTLY
- [ ] Add torch imports

#### 5.3 VERIFY
- [ ] `diff` each function
- [ ] `python -c "from scripts.target_models.validation.backtest.models.lstm import LSTMClassifier"`

#### 5.4 IMPORT
- [ ] Add import to l2_backtest_sync.py
- [ ] Verify import works

#### 5.5 REMOVE
- [ ] Comment out → verify → delete
- [ ] `wc -l` → ____ lines

#### 5.6 VALIDATE
- [ ] `grep -n "LSTMClassifier\|LSTMRegressor\|_create_sequences\|_train_lstm" l2_backtest_sync.py` → Only imports
- [ ] Check _train_predict_* functions still work (they USE these)

#### 5.7 DOCUMENT
- [ ] Mark Phase 5 complete ✅

---

### Phase 6: Extract adapters/data_loader.py ⬜

#### 6.1 BEFORE
- [ ] `_parse_config()`: Lines ____-____
- [ ] `_clip_features()`: Lines ____-____
- [ ] `_load_timestamps_for_config()`: Lines ____-____
- [ ] `_load_config_data()`: Lines ____-____
- [ ] Total: ____ lines

#### 6.2 EXTRACT
- [ ] Create `backtest/adapters/data_loader.py`
- [ ] Copy all 4 functions EXACTLY
- [ ] Add required imports (polars, pandas, Path)

#### 6.3 VERIFY
- [ ] `diff` each function
- [ ] `python -c "from scripts.target_models.validation.backtest.adapters.data_loader import _load_config_data"`

#### 6.4 IMPORT
- [ ] Add import to l2_backtest_sync.py

#### 6.5 REMOVE
- [ ] Comment → verify → delete
- [ ] `wc -l` → ____ lines

#### 6.6 VALIDATE
- [ ] `grep -n "_load_config_data\|_parse_config\|_clip_features" l2_backtest_sync.py` → Only imports
- [ ] run_sync_backtest still works (uses _load_config_data)

#### 6.7 DOCUMENT
- [ ] Mark Phase 6 complete ✅

---

### Phase 7: Extract adapters/output.py ⬜

#### 7.1 BEFORE
- [ ] `class DualOutput`: Lines ____-____
- [ ] Total: ____ lines

#### 7.2-7.7: Same pattern as above

---

### Phase 8: Extract services/tuning.py ⬜

#### 8.1 BEFORE
- [ ] `_tune_cb_classifier()`: Lines ____-____
- [ ] `_tune_lgb_classifier()`: Lines ____-____
- [ ] `_tune_cb_regressor()`: Lines ____-____
- [ ] `_tune_lgb_regressor()`: Lines ____-____
- [ ] Total: ____ lines

#### 8.2-8.7: Same pattern

---

### Phase 9: Extract services/training.py ⬜ (LARGEST)

#### 9.1 BEFORE
- [ ] `_train_predict_classification_permodel()`: Lines ____-____
- [ ] `_train_predict_regression_permodel()`: Lines ____-____
- [ ] `_extract_per_model_splits()`: Lines ____-____
- [ ] Total: ~1200 lines

**⚠️ EXTRA CAUTION: This is the largest extraction**

#### 9.2 EXTRACT
- [ ] Create `backtest/services/training.py`
- [ ] Copy classification function EXACTLY (save old hash)
- [ ] Copy regression function EXACTLY (save old hash)
- [ ] Add ALL required imports (many dependencies)

#### 9.3 VERIFY
- [ ] `md5sum` of old function == `md5sum` of new function (minus imports)
- [ ] Import test passes
- [ ] Function signature identical

#### 9.4 IMPORT
- [ ] Add import to l2_backtest_sync.py
- [ ] Verify run_sync_backtest can call them

#### 9.5 REMOVE
- [ ] Comment out old code
- [ ] **FULL TEST**: Run small backtest (3 steps) before deleting
- [ ] Delete old code
- [ ] `wc -l` → Should drop by ~1200 lines

#### 9.6 VALIDATE
- [ ] `grep -n "_train_predict_classification_permodel\|_train_predict_regression_permodel" l2_backtest_sync.py` → Only imports
- [ ] Full backtest works

#### 9.7 DOCUMENT
- [ ] Mark Phase 9 complete ✅

---

### Phase 10: Extract services/backtest.py ⬜

#### 10.1 BEFORE
- [ ] `run_sync_backtest()`: Lines ____-____
- [ ] Total: ~600 lines

#### 10.2-10.7: Same pattern

---

### Phase 11: Wire Adaptive Weights ⬜

#### 11.1 BEFORE
- [ ] Check `use_adaptive_weights` is defined: Line ____
- [ ] Check `_update_adaptive_weights` is in core/ensemble.py
- [ ] Check current weight usage: `grep -n "config.cb_weight" services/backtest.py`

#### 11.2 IMPLEMENT
- [ ] Import AdaptiveWeightTracker in services/backtest.py
- [ ] Add weight tracking initialization in run_sync_backtest()
- [ ] Add accuracy recording after each prediction
- [ ] Add weight update call when use_adaptive_weights=True
- [ ] Modify ensemble computation to use dynamic weights

#### 11.3 VERIFY
- [ ] `use_adaptive_weights=True` → weights change over time
- [ ] `use_adaptive_weights=False` → weights stay static
- [ ] No crashes, no import errors

#### 11.4 DOCUMENT
- [ ] Mark Phase 11 complete ✅

---

### Phase 12: Config Sync ⬜

#### 12.1 BEFORE
- [ ] List all SyncBacktestConfig fields
- [ ] List all L2BacktestDefaults fields
- [ ] Identify missing: ____ fields

#### 12.2 IMPLEMENT
- [ ] Add missing fields to L2BacktestDefaults
- [ ] Update to_sync_config_kwargs() to pass all fields

#### 12.3 VERIFY
- [ ] `len(to_sync_config_kwargs())` == number of SyncBacktestConfig fields
- [ ] Import test passes
- [ ] Backtest with custom config works

#### 12.4 DOCUMENT
- [ ] Mark Phase 12 complete ✅

---

### Phase 13: Fix Comments ⬜

#### 13.1 IDENTIFY
- [ ] Find comment at L434 (use_adaptive_weights)
- [ ] Find comment at L465 (use_sample_weights)
- [ ] List any other misleading comments

#### 13.2 FIX
- [ ] Update L434 comment to match new reality
- [ ] Update L465 comment to match new reality

#### 13.3 VERIFY
- [ ] Comments accurately describe behavior
- [ ] No syntax errors introduced

#### 13.4 DOCUMENT
- [ ] Mark Phase 13 complete ✅

---

### Phase 14: Create Facade ⬜

#### 14.1 IMPLEMENT
- [ ] l2_backtest_sync.py becomes thin re-export file
- [ ] All imports come from backtest/ submodules
- [ ] `wc -l l2_backtest_sync.py` → Target: <100 lines

#### 14.2 VERIFY
- [ ] `from scripts.target_models.validation.l2_backtest_sync import run_sync_backtest` → Works
- [ ] `from scripts.target_models.validation.l2_backtest_sync import SyncBacktestConfig` → Works
- [ ] All existing imports still work

#### 14.3 DOCUMENT
- [ ] Mark Phase 14 complete ✅

---

### Phase 15: Final Validation ⬜

- [ ] Full import test: `python -c "from scripts.target_models.validation.l2_backtest_sync import *"`
- [ ] workflow/config.py still works
- [ ] notebooks/main_wf.py still works
- [ ] Run actual backtest (10 steps minimum)
- [ ] No circular imports: `python -c "from scripts.target_models.validation.backtest import *"`
- [ ] l2_backtest_sync.py < 100 lines
- [ ] All extracted modules work independently

**FINAL SIGN-OFF: ✅ or ❌**
    predictions: dict[str, float],  # {"cb": 0.7, "lgb": 0.6, ...}
    weights: dict[str, float],      # {"cb": 0.3, "lgb": 0.3, ...}
) -> float:
    """Compute weighted ensemble from predictions."""
    return sum(weights[m] * predictions[m] for m in predictions)
```

---

### Phase 6: Extract core/metrics.py (~100 lines) ⬜

**Move these items:**
| Item | Current Line | Notes |
|------|--------------|-------|
| `_build_step_metrics()` | 672-812 | Large function |
| `_compute_config_metrics()` | 2245-2306 | Metric aggregation |

---

### Phase 7: Extract models/lstm.py (~300 lines) ⬜

**Move these items:**
| Item | Current Line | Notes |
|------|--------------|-------|
| `class LSTMClassifier` | 154-183 | PyTorch module |
| `class LSTMRegressor` | 185-212 | PyTorch module |
| `_create_sequences()` | 214-261 | Sequence builder |
| `_train_lstm_classifier()` | 263-333 | Training loop |
| `_train_lstm_regressor()` | 335-402 | Training loop |

**Dependencies:**
- `torch`, `torch.nn`
- `numpy`
- `StandardScaler`

---

### Phase 8: Extract adapters/data_loader.py (~200 lines) ⬜

**Move these items:**
| Item | Current Line | Notes |
|------|--------------|-------|
| `_parse_config()` | 832-855 | Parse config name |
| `_clip_features()` | 882-894 | Feature clipping |
| `_load_timestamps_for_config()` | 896-929 | Polars loader |
| `_load_config_data()` | 931-1020 | Main data loader |

---

### Phase 9: Extract adapters/output.py (~50 lines) ⬜

**Move these items:**
| Item | Current Line | Notes |
|------|--------------|-------|
| `class DualOutput` | 652-670 | Dual stdout/file output |
| File writing utilities | scattered | Consolidate |

---

### Phase 10: Extract services/tuning.py (~200 lines) ⬜

**Move these items:**
| Item | Current Line | Notes |
|------|--------------|-------|
| `_tune_cb_classifier()` | ~2061 | Optuna CB tuner |
| `_tune_lgb_classifier()` | ~2103 | Optuna LGB tuner |
| `_tune_cb_regressor()` | ~2554 | Optuna CB tuner |
| `_tune_lgb_regressor()` | ~2593 | Optuna LGB tuner |

---

### Phase 11: Extract services/training.py (~1200 lines) ⬜

**Move these items:**
| Item | Current Line | Notes |
|------|--------------|-------|
| `_train_predict_classification_permodel()` | 1099-1668 | BIG function |
| `_train_predict_regression_permodel()` | 1765-2242 | BIG function |

**These are the BIGGEST functions - extract LAST**

---

### Phase 12: Extract services/backtest.py (~600 lines) ⬜

**Move these items:**
| Item | Current Line | Notes |
|------|--------------|-------|
| `run_sync_backtest()` | 2306-2941 | Main orchestrator |

---

### Phase 13: Create l2_backtest_sync.py Facade ⬜

**Final l2_backtest_sync.py should be ~50 lines:**
```python
"""Backward compatibility facade for l2_backtest_sync.

All functionality has been moved to the backtest/ package.
This module provides re-exports for backward compatibility.
"""

from .backtest import (
    # Domain
    SyncBacktestConfig,
    PerModelConfig,
    ConfigData,
    DEFAULT_CB_CONFIG,
    DEFAULT_LGB_CONFIG,
    DEFAULT_LSTM_CONFIG,
    DEFAULT_LINEAR_CONFIG,
    
    # Core
    get_embargo_for_horizon,
    compute_ensemble,
    
    # Services
    run_sync_backtest,
)

__all__ = [
    "SyncBacktestConfig",
    "PerModelConfig",
    "ConfigData",
    "DEFAULT_CB_CONFIG",
    "DEFAULT_LGB_CONFIG",
    "DEFAULT_LSTM_CONFIG",
    "DEFAULT_LINEAR_CONFIG",
    "get_embargo_for_horizon",
    "compute_ensemble",
    "run_sync_backtest",
]
```

---

## 🔧 FIXING ISSUES DURING EXTRACTION

### Issue A: Wire Adaptive Weights (Phase 5)

**In core/ensemble.py:**
```python
class AdaptiveWeightTracker:
    """Track model accuracies and compute adaptive weights."""
    
    def __init__(self, lookback: int = 50, learning_rate: float = 0.1, min_weight: float = 0.05):
        self.lookback = lookback
        self.learning_rate = learning_rate
        self.min_weight = min_weight
        self.recent_accuracies = {m: deque(maxlen=lookback) for m in ["cb", "lgb", "lstm", "linear"]}
        self.current_weights = {"cb": 0.25, "lgb": 0.25, "lstm": 0.25, "linear": 0.25}
    
    def record(self, model: str, correct: bool) -> None:
        """Record whether model prediction was correct."""
        self.recent_accuracies[model].append(int(correct))
    
    def update(self) -> dict[str, float]:
        """Update weights using MWU algorithm."""
        if len(self.recent_accuracies["cb"]) < self.lookback:
            return self.current_weights
        
        self.current_weights = _update_adaptive_weights(
            {f"{m}_weight": self.current_weights[m] for m in ["cb", "lgb", "lstm", "linear"]},
            {m: list(v) for m, v in self.recent_accuracies.items()},
            self.learning_rate,
            self.min_weight
        )
        # Convert back to simple keys
        return {m: self.current_weights[f"{m}_weight"] for m in ["cb", "lgb", "lstm", "linear"]}
```

**Usage in services/backtest.py:**
```python
# Initialize
if config.use_adaptive_weights:
    weight_tracker = AdaptiveWeightTracker(
        config.adaptive_lookback,
        config.adaptive_learning_rate,
        config.adaptive_min_weight
    )
    weights = {"cb": config.cb_weight, "lgb": config.lgb_weight, ...}
else:
    weight_tracker = None
    weights = {"cb": config.cb_weight, ...}  # Static

# After each prediction
if weight_tracker and task_type == "classification":
    weight_tracker.record("cb", components["cb_pred"] == y_true)
    weight_tracker.record("lgb", components["lgb_pred"] == y_true)
    weight_tracker.record("lstm", components["lstm_pred"] == y_true)
    weight_tracker.record("linear", components["linear_pred"] == y_true)
    weights = weight_tracker.update()
```

---

### Issue B: Config Sync (Phase 2)

**In domain/config.py, update SyncBacktestConfig to use L2BacktestDefaults values:**

Just ensure all fields exist in both places with same defaults.

**In workflow/config.py, update to_sync_config_kwargs():**
```python
def to_sync_config_kwargs(self) -> dict[str, Any]:
    return {
        # Existing
        "train_window": self.train_window,
        "step_size": self.step_size,
        # ... all existing ...
        
        # ADD THESE:
        "use_adaptive_weights": self.use_adaptive_weights,
        "adaptive_lookback": self.adaptive_lookback,
        "adaptive_learning_rate": self.adaptive_learning_rate,
        "adaptive_min_weight": self.adaptive_min_weight,
        "use_sample_weights": self.use_sample_weights,
        "sample_decay_halflife": self.sample_decay_halflife,
        "train_ratio": self.train_ratio,
        "val_ratio": self.val_ratio,
        "cal_ratio": self.cal_ratio,
        "embargo_bars": self.embargo_bars,
        # ... etc
    }
```

---

### Issue C: Fix Comments (Phase 2)

**In domain/config.py after wiring adaptive weights:**
```python
# BEFORE (misleading):
use_adaptive_weights: bool = True  # Adjust weights based on recent performance

# AFTER (accurate):
use_adaptive_weights: bool = True  # Enable MWU adaptive weights (default). Set False for static weights.
```

---

## ✅ VERIFICATION CHECKLIST

After EACH phase:
- [ ] `python -c "from scripts.target_models.validation.l2_backtest_sync import run_sync_backtest"` works
- [ ] `wc -l` shows expected line reduction
- [ ] No circular imports: `python -c "from scripts.target_models.validation.backtest import *"`

After ALL phases:
- [ ] `l2_backtest_sync.py` < 100 lines (facade only)
- [ ] All functionality accessible via `from ... import run_sync_backtest`
- [ ] Tests pass (when fixed)
- [ ] Adaptive weights actually work when `use_adaptive_weights=True`

---

## 📐 DEPENDENCY RULES

```
┌─────────────────────────────────────────────────────┐
│                  l2_backtest_sync.py                │
│                  (facade re-exports)                │
└───────────────────────┬─────────────────────────────┘
                        │ imports
                        ▼
┌─────────────────────────────────────────────────────┐
│              backtest/__init__.py                   │
│              (public API)                           │
└───────────────────────┬─────────────────────────────┘
                        │ imports
                        ▼
┌─────────────────────────────────────────────────────┐
│                   services/                          │
│     (backtest.py, training.py, tuning.py)           │
└────────┬─────────────────────────────┬──────────────┘
         │                             │
    imports                       imports
         ▼                             ▼
┌─────────────────┐          ┌─────────────────────────┐
│     core/       │          │      adapters/          │
│ (pure logic)    │          │ (I/O, side effects)     │
└────────┬────────┘          └────────────────────────┬┘
         │                                            │
    imports                                      imports
         ▼                                            ▼
┌───────────────────────────────────────────────────────┐
│                      domain/                          │
│              (config.py, types.py)                    │
└───────────────────────────────────────────────────────┘
```

**Rules:**
1. `domain/` → NO imports from other backtest modules
2. `core/` → imports from `domain/` only
3. `adapters/` → imports from `domain/` only
4. `services/` → imports from `core/`, `adapters/`, `domain/`
5. `models/` → imports from `domain/` (for types)
6. NO circular imports

---

## 🕐 ESTIMATED EFFORT

| Phase | Lines Moved | Effort | Risk |
|-------|-------------|--------|------|
| 0: Safety | 0 | 5 min | None |
| 1: Structure | 0 | 5 min | None |
| 2: domain/config | ~300 | 30 min | Low |
| 3: domain/types | ~100 | 15 min | Low |
| 4: core/splits | ~50 | 10 min | Low |
| 5: core/ensemble | ~150 | 30 min | Medium |
| 6: core/metrics | ~100 | 15 min | Low |
| 7: models/lstm | ~300 | 30 min | Medium |
| 8: adapters/data | ~200 | 20 min | Low |
| 9: adapters/output | ~50 | 10 min | Low |
| 10: services/tuning | ~200 | 20 min | Low |
| 11: services/training | ~1200 | 60 min | High |
| 12: services/backtest | ~600 | 30 min | High |
| 13: Facade | ~50 | 10 min | Low |

**Total:** ~4-5 hours of focused work

---

## 🎯 SUCCESS CRITERIA

1. ✅ `l2_backtest_sync.py` is < 100 lines (facade)
2. ✅ All imports work as before
3. ✅ Adaptive weights work when enabled
4. ✅ Static weights work when disabled
5. ✅ Config sync complete (all 32 missing fields)
6. ✅ Comments match reality
7. ✅ No circular imports
8. ✅ Clear module boundaries
