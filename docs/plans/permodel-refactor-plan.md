# Per-Model Architecture Refactor Plan

**Created:** 2026-01-19
**Status:** In Progress
**Goal:** Reorganize backtest so each model (CB, LGB, LSTM, Linear) has its own self-contained module

---

## Quick Reference: How Backtest Currently Works

### Data Flow
```
1. load_config_data(config_name) → ConfigData
   - Loads combined dataset (raw + helper + interaction features)
   - Extracts X_features, y_target, pred_idx, timestamps

2. run_sync_backtest() orchestrates walk-forward:
   For each step:
     - Extract X_full (800 bars = max window)
     - Extract X_pred (1 row to predict)
     - Call train_predict_classification/regression_permodel()
     - Store predictions + metrics
     - Update adaptive weights

3. train_predict_*_permodel() does the heavy lifting:
   - Extract per-model splits (CB:400, LGB:400, LSTM:600, Linear:800)
   - Apply per-model feature selection
   - Tune hyperparams (CB/LGB only currently)
   - Train all 4 models
   - Get predictions from each
   - Ensemble with weighted average
   - Conformal prediction intervals
```

### Current File Responsibilities

| File | Lines | Responsibility |
|------|-------|----------------|
| `services/backtest.py` | 772 | Orchestration, metrics display, results saving |
| `services/training.py` | 1131 | **MONOLITH**: All 4 models' train/predict logic |
| `services/tuning.py` | 251 | Optuna tuning for CB + LGB only |
| `domain/config.py` | 276 | SyncBacktestConfig + PerModelConfig + 4 DEFAULTs |
| `models/lstm.py` | 305 | LSTM class + train functions (no config/tuning) |
| `core/ensemble.py` | 328 | AdaptiveWeightTracker, sample weights |
| `core/metrics.py` | 259 | Metrics computation |
| `adapters/data_loader.py` | 278 | Data loading, ConfigData |
| `adapters/output.py` | 53 | DualOutput for logging |

### Key Functions to Extract

From `training.py`:
- `apply_feature_selection()` (lines 42-84) → `core/features.py`
- `extract_per_model_splits()` (lines 87-147) → each model module
- CB logic (scattered) → `models/catboost_model.py`
- LGB logic (scattered) → `models/lightgbm_model.py`
- LSTM logic (scattered) → `models/lstm_model.py` (enhance)
- Linear logic (scattered) → `models/linear_model.py`

From `tuning.py`:
- `tune_cb_classifier/regressor()` → `models/catboost_model.py`
- `tune_lgb_classifier/regressor()` → `models/lightgbm_model.py`

### Default Window Sizes (IMPORTANT - preserve these!)
| Model | Window | Split Ratios | Feature Selection |
|-------|--------|--------------|-------------------|
| CatBoost | 400 | 60/20/20 | importance (60%) |
| LightGBM | 400 | 60/20/20 | importance (60%) |
| LSTM | 600 | 70/15/15 | variance (80%) |
| Linear | 800 | 50/20/30 | icir (50%) |

### Embargo Formula (CRITICAL - preserve!)
```python
embargo_bars = min(3 * horizon, 36)
# 1bar → 3, 3bar → 9, 6bar → 18, 12bar → 36
```

### LSTM Sequence Gap Fix (CRITICAL - preserve!)
```python
# In prediction, use lstm_X_full_for_seq (includes cal features)
# NOT lstm_X_full (train+val only)
# This reduces gap from ~93 bars to ~3 bars (embargo only)
lstm_X_full_for_seq = pd.concat([lstm_X_train_sel, lstm_X_val_sel, lstm_X_cal_sel])
```

### Conformal Prediction (stays in backtest.py)
- Uses calibration set from each model
- Excludes LSTM (different cal structure)
- Computes intervals for regression, sets for classification

---

## Todo List (119 Steps)

### Phase 0: Pre-flight Validation ✅ COMPLETE
- [x] **Phase 0**: BEFORE any changes: Run baseline test, capture current metrics, backup files
- [x] **Phase 0.1**: Run baseline 3-step backtest
  - Result: Accuracy=0.333, F1=0.167
- [x] **Phase 0.2**: Backup current files
  - Created: `backtest_backup_pre_refactor/`
- [x] **Phase 0.3**: Document current line counts
  - Total: 3692 lines (training.py=1131, tuning.py=251, config.py=276, lstm.py=305)

### Phase 1: Create core/base.py ✅ COMPLETE (209 lines)
- [x] **Phase 1**: NEW FILE: ModelConfig ABC, ModelResult dataclass, ModelProtocol
- [x] **Phase 1.1**: Write ModelConfig ABC (lines 28-81)
  - train_window, ratios, embargo, feature_selection, validate(), @abstractmethod get_model_name()
- [x] **Phase 1.2**: Write ModelResult dataclass (lines 84-123)
  - prediction, probabilities, metrics, trained_model, selected_features, best_params, sizes
- [x] **Phase 1.3**: Write ModelProtocol (lines 126-195)
  - Protocol with train_and_predict_classifier/regressor signatures
- [x] **Phase 1.4**: Validate Phase 1 ✅ Imports work

### Phase 2: Create core/features.py ✅ COMPLETE (178 lines)
- [x] **Phase 2**: Extract apply_feature_selection() + extract_per_model_splits()
- [x] **Phase 2.1**: apply_feature_selection (lines 26-99)
  - variance/importance/icir/none methods
- [x] **Phase 2.2**: extract_per_model_splits (lines 102-178) **BONUS**
  - Shared split extraction used by all model modules
- [x] **Phase 2.3**: Validate Phase 2 ✅ Exports via core/__init__.py

### Phase 3: Create models/catboost_model.py ✅ COMPLETE (424 lines)
- [x] **Phase 3**: NEW FILE: Complete CB pipeline
- [x] **Phase 3.1**: CatBoostModelConfig (lines 55-96)
  - window=400, importance selection, GPU settings, Optuna settings
- [x] **Phase 3.2**: Uses shared extract_per_model_splits from core/features.py
- [x] **Phase 3.3**: Uses shared apply_feature_selection
- [x] **Phase 3.4**: tune_catboost_classifier (line 108)
- [x] **Phase 3.5**: tune_catboost_regressor (line 173)
- [x] **Phase 3.6**: Internal _train_cb_model logic
- [x] **Phase 3.7**: Predict embedded in train_and_predict functions
- [x] **Phase 3.8**: train_and_predict_classifier/regressor complete
- [x] **Phase 3.9**: __all__ exports 6 items
- [x] **Phase 3.10**: Validate ✅ Valid predictions

### Phase 4: Create models/lightgbm_model.py ✅ COMPLETE (455 lines)
- [x] **Phase 4**: NEW FILE: Complete LGB pipeline - mirrors CB structure
- [x] **Phase 4.1**: LightGBMModelConfig (lines 55-96)
  - window=400, importance selection, GPU settings
- [x] **Phase 4.2**: Uses shared extract_per_model_splits
- [x] **Phase 4.3**: Uses shared apply_feature_selection
- [x] **Phase 4.4**: tune_lightgbm_classifier (line 108)
- [x] **Phase 4.5**: tune_lightgbm_regressor (line 185)
- [x] **Phase 4.6**: Internal training logic
- [x] **Phase 4.7**: Predict embedded in train_and_predict
- [x] **Phase 4.8**: train_and_predict_classifier/regressor complete
- [x] **Phase 4.9**: __all__ exports 6 items
- [x] **Phase 4.10**: Validate ✅ Valid predictions

### Phase 5: Enhance models/lstm_model.py ✅ COMPLETE (880 lines, was 305)
- [x] **Phase 5**: Enhanced with LSTMModelConfig, tune_lstm(), train_and_predict()
- [x] **Phase 5.1**: LSTMModelConfig (lines 62-103)
  - window=600, variance selection, seq_len=20, **Optuna settings (NEW!)**
- [x] **Phase 5.2**: Uses shared functions for splits
- [x] **Phase 5.3**: Uses shared apply_feature_selection
- [x] **Phase 5.4**: tune_lstm_classifier (line 230) **NEW!**
  - Optuna for hidden_size, num_layers, lr, seq_len, dropout
- [x] **Phase 5.4b**: tune_lstm_regressor (line 337) **NEW!**
- [x] **Phase 5.5**: LSTM gap fix preserved (lines 633, 745)
  - `X_for_seq = pd.concat([X_full, X_cal]...)` reduces gap to ~3 bars
- [x] **Phase 5.6**: train_and_predict_classifier/regressor complete
- [x] **Phase 5.7**: __all__ exports 10 items
- [x] **Phase 5.8**: Validate ✅ Gap fix verified, Optuna works

### Phase 6: Create models/linear_model.py ✅ COMPLETE (419 lines)
- [x] **Phase 6**: NEW FILE: Complete Linear pipeline with **NEW Optuna tuning!**
- [x] **Phase 6.1**: LinearModelConfig (lines 58-95)
  - window=800, icir selection, C/alpha params
- [x] **Phase 6.2**: Uses shared extract_per_model_splits
- [x] **Phase 6.3**: Uses shared apply_feature_selection
- [x] **Phase 6.4**: tune_linear_classifier (line 109) **NEW!**
  - Optuna for C, solver, penalty
- [x] **Phase 6.4b**: tune_linear_regressor (line 172) **NEW!**
  - Optuna for alpha
- [x] **Phase 6.5**: LogisticRegression/Ridge training
- [x] **Phase 6.6**: predict_proba/predict
- [x] **Phase 6.7**: train_and_predict_classifier/regressor complete
- [x] **Phase 6.8**: __all__ exports 6 items
- [x] **Phase 6.9**: Validate ✅ Valid predictions

> ⚠️ **NOTE:** sklearn deprecation warnings for LogisticRegression `penalty` and `n_jobs`
> params in sklearn 1.8 - to be fixed in post-refactor cleanup

### CHECKPOINT A ✅ PASSED (Jan 19, 2026)
- [x] **CHECKPOINT A**: All 4 model modules work
  - ✅ CatBoost: Valid predictions with correct shape
  - ✅ LightGBM: Valid predictions with correct shape
  - ✅ LSTM: Valid predictions + gap fix verified
  - ✅ Linear: Valid predictions with correct shape

### Phase 7: Refactor domain/config.py
> 📝 **IMPLEMENTATION NOTES:**
> - Each model module now has its own DEFAULT_*_CONFIG (e.g., DEFAULT_CB_CONFIG)
> - SyncBacktestConfig should import configs from model modules OR use models directly
> - Dynamic embargo formula `min(3*horizon, 36)` needs to be wired in Phase 8 backtest.py

- [ ] **Phase 7**: Remove PerModelConfig, DEFAULT_*_CONFIG - now in model modules
- [ ] **Phase 7.1**: Remove PerModelConfig class
  - Lines 18-66 → DELETE (moved to each model)
- [ ] **Phase 7.2**: Remove DEFAULT_*_CONFIG
  - Lines 70-120 → DELETE (moved to model modules)
- [ ] **Phase 7.3**: Update SyncBacktestConfig
  - Change cb_config etc to import from model modules
- [ ] **Phase 7.4**: Update __all__ exports
  - Remove deleted exports, add model module imports
- [ ] **Phase 7.5**: Validate Phase 7
  - Import SyncBacktestConfig, verify get_model_config() still works

### Phase 8: Rewrite services/backtest.py
> 📝 **IMPLEMENTATION NOTES:**
> - **CRITICAL:** Wire dynamic embargo formula here: `embargo = min(3 * horizon, 36)`
> - Each model's config has default `embargo_bars=24`, but backtest.py should override based on horizon
> - Call pattern: `result = catboost_model.train_and_predict_classifier(X_train, ...)`
> - Window extraction: Use linear_window (800) for full data, then each model extracts its own subset

- [ ] **Phase 8**: Simplify to use model modules instead of monolithic training.py
- [ ] **Phase 8.1**: Update imports
  - Import from backtest.models.* instead of training.py
- [ ] **Phase 8.2**: Replace train_predict_classification call
  - Call each model's train_and_predict() separately
- [ ] **Phase 8.3**: Replace train_predict_regression call
  - Call each model's train_and_predict() separately
- [ ] **Phase 8.4**: Keep ensemble logic
  - Weighted combination stays in backtest.py
- [ ] **Phase 8.5**: Keep conformal logic
  - Calibration set processing stays in backtest.py
- [ ] **Phase 8.6**: Keep adaptive weights
  - AdaptiveWeightTracker usage unchanged
- [ ] **Phase 8.7**: Update comments
  - Update docstrings to reflect new architecture
- [ ] **Phase 8.8**: Validate Phase 8
  - run_sync_backtest imports and basic call works

### Phase 9: Delete services/training.py
- [ ] **Phase 9**: All logic now in model modules - DELETE 1131 lines
- [ ] **Phase 9.1**: Verify no remaining imports
  - `grep for 'from backtest.services.training'` - should be 0
- [ ] **Phase 9.2**: Delete file
  - `rm services/training.py`
- [ ] **Phase 9.3**: Update services/__init__.py
  - Remove training exports if any
- [ ] **Phase 9.4**: Validate Phase 9
  - Full import chain still works

### Phase 10: Delete services/tuning.py
- [ ] **Phase 10**: All tuning now in model modules - DELETE 251 lines
- [ ] **Phase 10.1**: Verify no remaining imports
  - `grep for 'from backtest.services.tuning'` - should be 0
- [ ] **Phase 10.2**: Delete file
  - `rm services/tuning.py`
- [ ] **Phase 10.3**: Update services/__init__.py
  - Remove tuning exports if any
- [ ] **Phase 10.4**: Validate Phase 10
  - Full import chain still works

### CHECKPOINT B
- [ ] **CHECKPOINT B**: Core refactor complete
  - All old files deleted, new structure in place

### Phase 11: Update facade l2_backtest_sync.py
- [ ] **Phase 11**: Update imports to reflect new module structure
- [ ] **Phase 11.1**: Remove old training imports
  - Remove extract_per_model_splits, train_predict_* imports
- [ ] **Phase 11.2**: Remove old tuning imports
  - Remove tune_cb_*, tune_lgb_* imports
- [ ] **Phase 11.3**: Add new model imports
  - Import from backtest.models.catboost_model etc
- [ ] **Phase 11.4**: Update __all__ list
  - Reflect new exports, keep backward compatibility
- [ ] **Phase 11.5**: Update module docstring
  - Update architecture comment to show new structure
- [ ] **Phase 11.6**: Validate Phase 11
  - All imports from facade work

### Phase 12: Update models/__init__.py
> 📝 **IMPLEMENTATION NOTES:**
> - Currently has placeholder: `# Re-exports will be added after extraction`
> - Need to export all new model configs and functions for clean imports
> - Consider explicit exports vs `from .module import *` for clarity

- [ ] **Phase 12**: Export all model modules cleanly
- [ ] **Phase 12.1**: Add CB model exports
  - `from .catboost_model import *`
- [ ] **Phase 12.2**: Add LGB model exports
  - `from .lightgbm_model import *`
- [ ] **Phase 12.3**: Add LSTM model exports
  - `from .lstm_model import *` (enhanced)
- [ ] **Phase 12.4**: Add Linear model exports
  - `from .linear_model import *`
- [ ] **Phase 12.5**: Validate Phase 12
  - `from backtest.models import CatBoostModelConfig` works

### Phase 13: Update backtest/__init__.py
- [ ] **Phase 13**: Clean package-level exports
- [ ] **Phase 13.1**: Add model config exports
  - Export all *ModelConfig classes
- [ ] **Phase 13.2**: Add model result exports
  - Export all *Result classes
- [ ] **Phase 13.3**: Update version
  - `__version__ = '3.0.0'` (major refactor)
- [ ] **Phase 13.4**: Validate Phase 13
  - `from backtest import run_sync_backtest` works

### CHECKPOINT C
- [ ] **CHECKPOINT C**: All imports work
  - Test every import path documented in facade

### Phase 14: Update documentation
- [ ] **Phase 14**: Update all comments, docstrings, and docs/ files
- [ ] **Phase 14.1**: Update session.md
  - Document new architecture in memory
- [ ] **Phase 14.2**: Update backtest.py docstring
  - Reflect new model module calls
- [ ] **Phase 14.3**: Update each model docstring
  - Ensure each model module has complete docs
- [ ] **Phase 14.4**: Update MULTI_MODEL_IMPLEMENTATION_SPEC.md
  - Reflect new per-model architecture
- [ ] **Phase 14.5**: Validate Phase 14
  - Read through all updated docs for accuracy

### Phase 15: Final Validation
- [ ] **Phase 15**: End-to-end testing to ensure nothing broke
- [ ] **Phase 15.1**: Run 3-step backtest
  - Same test as Phase 0.1 - compare metrics
- [ ] **Phase 15.2**: Compare metrics
  - Accuracy, IC, coverage should match baseline ±1%
- [ ] **Phase 15.3**: Check per-model predictions
  - All 4 models produce predictions in output
- [ ] **Phase 15.4**: Check adaptive weights
  - Weights update correctly during run
- [ ] **Phase 15.5**: Check conformal intervals
  - Intervals computed, coverage reasonable
- [ ] **Phase 15.6**: Check output files
  - Parquet outputs have all expected columns
- [ ] **Phase 15.7**: Memory/timing check
  - No significant regression in performance
- [ ] **Phase 15.8**: Run notebook cell 27
  - main_wf.py Step 10 works end-to-end

### FINAL: Cleanup
- [ ] **FINAL**: Remove backup, update git, celebrate
- [ ] **Final.1**: Remove backup folder
  - `rm -rf backtest_backup_pre_refactor/`
- [ ] **Final.2**: Git commit
  - `git add -A && git commit -m 'Refactor: per-model architecture'`
- [ ] **Final.3**: Document line count reduction
  - Was ~2400 lines, now ~1800 - cleaner AND smaller

---

## Post-Refactor Cleanup (After FINAL)

> 🔧 **Items to address after refactor is complete and stable:**

### 1. sklearn Deprecation Warnings
**File:** `models/linear_model.py`
**Issue:** sklearn 1.8 deprecated `penalty` and `n_jobs` parameters in LogisticRegression
**Fix:**
```python
# Change from:
LogisticRegression(penalty='l2', n_jobs=-1, ...)
# To:
LogisticRegression(...)  # Use defaults, or update per sklearn 1.8 docs
```
**Priority:** Low (warnings only, not errors)

### 2. ICIR Feature Selection
**File:** `core/features.py` line 95
**Issue:** ICIR method currently falls back to variance (TODO in code)
**Fix:** Implement proper Information Coefficient / Information Ratio calculation
**Priority:** Medium (affects linear model feature selection)

### 3. Consider Model-Specific Embargo Override
**Files:** All model configs
**Current:** Each model has `embargo_bars=24` default
**Enhancement:** Allow passing `horizon` to model config to auto-compute `min(3*horizon, 36)`
**Priority:** Low (backtest.py handles this dynamically)

---

## Target Architecture (After Refactor)

```
backtest/
├── __init__.py                    # Package exports (v3.0.0)
├── domain/
│   └── config.py                  # SyncBacktestConfig ONLY (~100 lines)
├── core/
│   ├── base.py                    # NEW: ModelConfig ABC, ModelResult, Protocol
│   ├── features.py                # NEW: apply_feature_selection (~50 lines)
│   ├── ensemble.py                # KEEP: AdaptiveWeightTracker (328 lines)
│   └── metrics.py                 # KEEP: metrics functions (259 lines)
├── models/
│   ├── __init__.py                # Export all model modules
│   ├── catboost_model.py          # NEW: Complete CB (~280 lines)
│   ├── lightgbm_model.py          # NEW: Complete LGB (~280 lines)
│   ├── lstm_model.py              # ENHANCED: + config, tuning (~400 lines)
│   └── linear_model.py            # NEW: Complete Linear (~220 lines)
├── adapters/
│   ├── data_loader.py             # KEEP (278 lines)
│   └── output.py                  # KEEP (53 lines)
└── services/
    └── backtest.py                # SIMPLIFIED orchestrator (~400 lines)
```

**Deleted files:**
- `services/training.py` (1131 lines) → logic moved to model modules
- `services/tuning.py` (251 lines) → logic moved to model modules

**Net result:** ~2400 lines → ~1800 lines (25% reduction, cleaner architecture)

---

## Validation Commands Reference

```bash
# Phase validation template
cd "/media/przem/linux_data/RiskYieldMM (Copy)"
PYTHONPATH="$PWD:$PWD/scripts/target_models/validation" \
  /media/przem/linux_data/conda/envs/ml_env/bin/python -c \
  "from backtest.MODULE import CLASS; print('✅ Import OK')"

# Baseline test
PYTHONPATH="$PWD:$PWD/scripts/target_models/validation" \
  /media/przem/linux_data/conda/envs/ml_env/bin/python -c "
from backtest.services.backtest import run_sync_backtest
from backtest.domain.config import SyncBacktestConfig
cfg = SyncBacktestConfig(n_steps=3, enable_optuna=False)
results = run_sync_backtest(['direction_1bar'], config=cfg, verbose=True)
print('Baseline accuracy:', results['direction_1bar']['metrics'].get('accuracy'))
"

# Grep for old imports (should return 0 after cleanup)
grep -r "from backtest.services.training" scripts/
grep -r "from backtest.services.tuning" scripts/
```

---

## Notes for Implementation

1. **Always test imports after each file change** - prevents cascading failures
2. **Keep backup until Phase 15 passes** - easy rollback
3. **Model modules are self-contained** - config + splits + features + tuning + train + predict
4. **Ensemble stays in backtest.py** - it's orchestration, not model-specific
5. **Conformal stays in backtest.py** - uses all models' calibration sets
6. **Preserve LSTM gap fix** - critical for temporal continuity
7. **Preserve embargo formula** - prevents data leakage
