# CatBoost Dynamic Optimization - Plan Validation

> Historical note
>
> This validation note predates the multi-asset source and HTF materialization
> work. Its "single-asset" references describe the older state. Current source
> data, HTF outputs, and Stage-1 merged target/context dataset assembly are
> multi-asset-aware. Downstream diagnostics may still use older run groupings.

**Status:** 📋 VALIDATION IN PROGRESS  
**Purpose:** Verify plan completeness against universal template before implementation

---

## 0️⃣ DEFINE THE WORK UNIT

### ✅ One-sentence goal
**Feature:** CatBoost Dynamic Configuration Optimization

**Goal (1 sentence):**
Implement a 4-stage optimization pipeline that analyzes data characteristics to select optimal CatBoost window/split/hyperparameter configurations per prediction step and per target, guaranteeing best possible CatBoost predictions across all 28 backtest targets without future data leakage.

### ✅ Success Criteria (Observable)

| # | Criterion | Test/Validation |
|---|-----------|-----------------|
| 1 | No future data leakage | Unit test: `test_no_leakage_in_optimization()` marks future data, verifies not accessed |
| 2 | Works for all 28 targets | Integration test: Run all target configs, no crashes |
| 3 | Config bounds respected | Unit test: All params within defined ranges |
| 4 | Overhead < 100% | Benchmark: Compare step time with/without optimization |
| 5 | Performance ≥ baseline | Comparison: Optimized accuracy ≥ 95% of baseline |
| 6 | Config varies by data | Assert: Different targets → different configs |

**Quantifiable Definition of "Done":**
1. All 6 new functions implemented and type-checked
2. All unit tests pass
3. All integration tests pass
4. Full backtest runs without errors on all 28 targets
5. Documentation complete with usage examples

### ✅ Out of Scope

| # | Exclusion | Reason |
|---|-----------|--------|
| 1 | LightGBM optimization | CatBoost first, then others |
| 2 | LSTM optimization | CatBoost first |
| 3 | Linear optimization | CatBoost first |
| 4 | Ensemble weight optimization | Separate work unit |
| 5 | Multi-asset support | Current system is single-asset |
| 6 | Automatic feature engineering | Feature selection only |
| 7 | GPU/CPU fallback | GPU assumed available |

---

## 1️⃣ RECON AND CONSTRAINTS

### ✅ Where It Lives

| Component | Location |
|-----------|----------|
| New code | `backtest/models/catboost_model.py` |
| Integration | `backtest/services/training.py` |
| Tests | `tests/test_catboost_optimizer.py` (NEW) |
| Documentation | `docs/astra-research/CATBOOST_*.md` |

### ✅ Existing Patterns to Follow

| Pattern | Source | Will Follow |
|---------|--------|-------------|
| Dataclass config | `CatBoostModelConfig` at lines 56-95 | ✅ Yes |
| Type hints | All model files use `pd.DataFrame`, `pd.Series` | ✅ Yes |
| Error handling | `ValueError` for invalid params | ✅ Yes |
| Logging | Via `logging` module (see training.py) | ✅ Yes |
| Test fixtures | pytest fixtures in `tests/test_models.py` | ✅ Yes |
| Docstrings | NumPy style (Args, Returns, Raises) | ✅ Yes |

### ✅ Dependencies and Risks

| Dependency | Version | Risk | Mitigation |
|------------|---------|------|------------|
| CatBoost | Any recent | Low - stable API | Pin to tested version |
| Optuna | 3.x | Low | Already in project |
| scipy (ADF test) | Any | Low | Standard library |
| GPU availability | Required | Medium | Add CPU fallback warning |

### ✅ Constraints

| Constraint | Type | Value | Source |
|------------|------|-------|--------|
| train_window | Range | 200-700 | Plan Section 1.2 |
| train_ratio | Range | 0.50-0.70 | Plan Section 1.2 |
| val_ratio | Range | 0.15-0.25 | Plan Section 1.2 |
| cal_ratio | Range | 0.10-0.30 | Plan Section 1.2 |
| n_estimators | Range | 50-500 | Plan Section 1.2 |
| max_depth | Range | 4-10 | Plan Section 1.2 |
| learning_rate | Range | 0.01-0.3 | Plan Section 1.2 |
| l2_leaf_reg | Range | 1.0-15.0 | Plan Section 1.2 |
| NO LEAKAGE | Hard | Only data[0:t-1] at step t | Plan Section 1.3 |
| Overhead | Soft | <100% increase | Plan Section 4.3 |

### ✅ Data Contracts

**Input Contract:**
```python
X_full: pd.DataFrame  # Shape (N, ~265), dtype float64, no NaN after imputation
y_full: pd.Series     # Shape (N,), int for classification, float for regression
target_name: str      # Pattern: "{type}_{horizon}bar" e.g. "direction_1bar"
task_type: str        # Literal["classification", "regression"]
horizon: int          # One of [1, 3, 6, 12]
n_classes: int | None # For classification: 2 or 3; None for regression
```

**Output Contract:**
```python
CatBoostModelConfig   # All fields filled, within bounds
                      # train_ratio + val_ratio + cal_ratio ≈ 1.0
```

---

## 2️⃣ DESIGN THE INTERFACE

### ✅ Public API (Minimal Surface)

**New public symbols:**

| Symbol | Type | Purpose |
|--------|------|---------|
| `DataCharacteristics` | @dataclass | Stage 1 output - data analysis results |
| `characterize_data()` | function | Stage 1 - analyze X_full, y_full |
| `generate_candidate_configs()` | function | Stage 2 - create candidate configs |
| `validate_configs_on_holdout()` | function | Stage 3 - test candidates |
| `refine_hyperparameters()` | function | Stage 4 - Optuna fine-tuning |
| `optimize_catboost_config()` | function | Main entry - runs all 4 stages |

**Modified existing:**

| Symbol | Change |
|--------|--------|
| `_get_model_configs()` in training.py | Add call to `optimize_catboost_config()` |

### ✅ Input/Output Types

```python
# Stage 1: Characterization
def characterize_data(
    X_full: pd.DataFrame,
    y_full: pd.Series,
    task_type: str,  # "classification" | "regression"
) -> DataCharacteristics:
    ...

# Stage 2: Candidate Generation
def generate_candidate_configs(
    characteristics: DataCharacteristics,
    target_name: str,
    horizon: int,
) -> list[CatBoostModelConfig]:  # 3-5 candidates
    ...

# Stage 3: Holdout Validation
def validate_configs_on_holdout(
    X_full: pd.DataFrame,
    y_full: pd.Series,
    candidates: list[CatBoostModelConfig],
    task_type: str,
    n_classes: int | None,
) -> tuple[CatBoostModelConfig, dict[str, Any]]:  # best_config, validation_info
    ...

# Stage 4: Hyperparameter Refinement
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
    ...

# Main Entry Point
def optimize_catboost_config(
    X_full: pd.DataFrame,
    y_full: pd.Series,
    target_name: str,
    task_type: str = "classification",
    horizon: int = 1,
    n_classes: int | None = 3,
    previous_config: CatBoostModelConfig | None = None,
    previous_performance: dict | None = None,
) -> CatBoostModelConfig:
    ...
```

### ✅ Error Taxonomy

| Error | When | Handling |
|-------|------|----------|
| `ValueError("Insufficient samples")` | len(X_full) < 100 | Caller must provide more data |
| `ValueError("Invalid task_type")` | Not classification/regression | Fix calling code |
| `ValueError("train_ratio + val_ratio + cal_ratio != 1.0")` | Invalid split | Normalize in function |
| `RuntimeWarning("Non-stationary data")` | ADF p > 0.05 | Log warning, continue |
| `RuntimeWarning("Imbalanced classes")` | min_class < 0.15 | Log warning, adjust config |

### ✅ Config Source

All config values derived from:
1. **Data analysis** (Stage 1) - stationarity, balance, volatility
2. **Rule-based mapping** (Stage 2) - characteristics → config
3. **Empirical validation** (Stage 3) - holdout performance
4. **Optuna search** (Stage 4) - hyperparameter tuning

**NO external config files needed** - everything computed from data.

---

## 3️⃣ FOLDER + MODULE PLACEMENT

### ✅ Architecture Sanity

| Component | Location | Rationale |
|-----------|----------|-----------|
| `DataCharacteristics` | `backtest/models/catboost_model.py` | CatBoost-specific analysis |
| `characterize_data()` | `backtest/models/catboost_model.py` | Produces CatBoost-specific output |
| `generate_candidate_configs()` | `backtest/models/catboost_model.py` | CatBoost config rules |
| `validate_configs_on_holdout()` | `backtest/models/catboost_model.py` | Uses CatBoost for validation |
| `refine_hyperparameters()` | `backtest/models/catboost_model.py` | Tunes CatBoost hyperparameters |
| `optimize_catboost_config()` | `backtest/models/catboost_model.py` | Main entry, orchestrates stages |
| Integration | `backtest/services/training.py` | Calls optimizer, uses config |
| Tests | `tests/test_catboost_optimizer.py` | Isolated test file |

### ✅ Import Boundaries

```
backtest/models/catboost_model.py
├── Imports FROM:
│   ├── dataclasses (std lib)
│   ├── typing (std lib)
│   ├── numpy
│   ├── pandas
│   ├── scipy.stats (for ADF test)
│   ├── optuna
│   ├── catboost
│   ├── sklearn.metrics
│   └── backtest.core.base (ModelConfig, ModelResult)
└── Exports TO:
    └── backtest.services.training (optimize_catboost_config)

backtest/services/training.py
├── Imports FROM:
│   ├── backtest.models.catboost_model (optimize_catboost_config)  # ADD
│   └── ... (existing)
└── Uses:
    └── optimize_catboost_config() in _get_model_configs()
```

**No circular imports** - catboost_model.py doesn't import from services.

### ✅ `__all__` Exports

Add to `catboost_model.py`:
```python
__all__ = [
    "CatBoostModelConfig",
    "DataCharacteristics",  # ADD
    "characterize_data",     # ADD
    "generate_candidate_configs",  # ADD
    "validate_configs_on_holdout",  # ADD
    "refine_hyperparameters",  # ADD
    "optimize_catboost_config",  # Already in __all__
    ...
]
```

---

## 4️⃣ TEST SCAFFOLDING

### ✅ Test File Structure

```
tests/test_catboost_optimizer.py
├── TestDataCharacteristics
│   ├── test_classification_characterization()
│   ├── test_regression_characterization()
│   ├── test_stationarity_detection()
│   └── test_class_imbalance_detection()
├── TestCandidateGeneration
│   ├── test_generates_3_to_5_candidates()
│   ├── test_all_candidates_within_bounds()
│   ├── test_target_type_affects_config()
│   └── test_horizon_affects_window()
├── TestHoldoutValidation
│   ├── test_uses_oldest_data_as_holdout()
│   ├── test_returns_best_config()
│   └── test_no_leakage_to_holdout()
├── TestHyperparameterRefinement
│   ├── test_optuna_runs_n_trials()
│   ├── test_warm_start_with_previous()
│   └── test_timeout_respected()
├── TestOptimizeCatboostConfig
│   ├── test_no_leakage_in_optimization()  # CRITICAL
│   ├── test_config_bounds()
│   ├── test_target_specific_adjustments()
│   ├── test_returns_valid_config()
│   └── test_overhead_acceptable()
└── TestIntegration
    ├── test_full_backtest_with_optimization()
    └── test_optimization_vs_baseline()
```

### ✅ Minimal Test Set

| Test Type | Test | Priority |
|-----------|------|----------|
| Happy path | `test_returns_valid_config()` | P0 |
| Edge case | `test_few_samples_handled()` | P1 |
| Failure case | `test_invalid_task_type_raises()` | P1 |
| Regression | `test_baseline_not_worse()` | P0 |
| **Leakage** | `test_no_leakage_in_optimization()` | **P0 CRITICAL** |

---

## 5️⃣ IMPLEMENTATION SLICES

### ✅ Vertical Slice Order

| # | Slice | Deliverable | Est. Time |
|---|-------|-------------|-----------|
| 1 | Skeleton | `DataCharacteristics` + function stubs | 30 min |
| 2 | Stage 1 | `characterize_data()` working | 1.5 hr |
| 3 | Stage 2 | `generate_candidate_configs()` working | 1.5 hr |
| 4 | Stage 3 | `validate_configs_on_holdout()` working | 2 hr |
| 5 | Stage 4 | `refine_hyperparameters()` working | 1.5 hr |
| 6 | Orchestrator | `optimize_catboost_config()` wires stages | 1 hr |
| 7 | Integration | Wire into `_get_model_configs()` | 1 hr |
| 8 | Tests | All tests pass | 2 hr |
| 9 | Validation | Full backtest comparison | 2 hr |
| 10 | Polish | Docs, edge cases, cleanup | 1 hr |

**Total: ~14 hours** (matches plan estimate)

### ✅ Safe Stop Points

| After Slice | Safe to Stop | State |
|-------------|--------------|-------|
| 1 | ✅ Yes | Skeleton only, baseline unchanged |
| 2 | ✅ Yes | Stage 1 works, others stub |
| 3 | ✅ Yes | Stages 1-2 work, others stub |
| 4 | ✅ Yes | Stages 1-3 work, Stage 4 stub |
| 5 | ✅ Yes | All stages work, not wired |
| 6 | ✅ Yes | Optimizer complete, not integrated |
| 7 | ⚠️ No | Integration incomplete = broken |
| 8 | ✅ Yes | Tests pass, validation pending |
| 9 | ✅ Yes | Validated, docs pending |
| 10 | ✅ Yes | DONE |

---

## 6️⃣ INTEGRATION WIRING

### ✅ Integration Points

| Point | File | Line | Change |
|-------|------|------|--------|
| Signature | `training.py` | ~81 | Add X_full, y_full, target_name params |
| Call | `training.py` | ~100 | Call `optimize_catboost_config()` |
| Config use | `training.py` | ~120 | Use returned config for CatBoost |

### ✅ Feature Flag

Add `enable_cb_optimization: bool = True` to `SyncBacktestConfig`:
- If `True`: Call `optimize_catboost_config()`
- If `False`: Use baseline config (current behavior)

This allows:
1. **A/B testing** - Compare optimized vs baseline
2. **Rollback** - Disable if issues found
3. **Gradual rollout** - Enable for specific targets

### ✅ Backward Compatibility

| Aspect | Handling |
|--------|----------|
| Old API calls | Still work - optimizer is internal |
| Old config files | N/A - no config files used |
| Old test data | Works - optimizer adapts to data |
| Old results | Comparable - can run baseline mode |

---

## 7️⃣ DOCUMENTATION

### ✅ Required Documentation

| Doc Type | Location | Status |
|----------|----------|--------|
| Docstrings | Each function | 🔲 TODO |
| Type hints | All signatures | 🔲 TODO |
| Research doc | `CATBOOST_DYNAMIC_CONFIG.md` | ✅ Done |
| Implementation plan | `CATBOOST_IMPLEMENTATION_PLAN.md` | ✅ Done |
| Plan validation | This file | ✅ Done |
| Usage example | `CATBOOST_IMPLEMENTATION_PLAN.md` Section 4 | ✅ Done |
| Limitations | Plan Section 9 (Risks) | ✅ Done |

### ✅ Gotchas / Failure Modes

| Gotcha | Impact | Prevention |
|--------|--------|------------|
| Too few samples | Optimization fails | Min 100 samples check |
| All classes same | No variance in y | Return baseline config |
| GPU not available | Training fails | Error message + docs |
| ADF test fails | scipy error | Try-except, assume non-stationary |
| Optuna timeout | Incomplete search | Use best found so far |

---

## 8️⃣ QUALITY GATES

### ✅ Before Implementation Starts

- [x] Plan documented (`CATBOOST_IMPLEMENTATION_PLAN.md`)
- [x] Contracts defined (Section 2 above)
- [x] Test scaffolding designed (Section 4 above)
- [x] Safe stop points identified (Section 5 above)
- [ ] Plan reviewed by user ← **CURRENT STEP**

### ✅ Before Each Slice Merge

- [ ] Lint/format (ruff)
- [ ] Type check (pyright)
- [ ] Unit tests pass
- [ ] No debug prints
- [ ] No unused code

### ✅ Before Final Merge

- [ ] All tests pass
- [ ] Full backtest completes without errors
- [ ] Performance comparison documented
- [ ] Docstrings complete
- [ ] No TODOs in code

---

## 9️⃣ FOLLOW-THROUGH

### Post-Implementation Tasks

- [ ] Run full comparison backtest (all 28 targets)
- [ ] Document performance delta
- [ ] Monitor for regressions
- [ ] Open issues for:
  - LightGBM optimizer (next work unit)
  - LSTM optimizer (future)
  - Linear optimizer (future)

---

## 🔍 GAP ANALYSIS

### Comparing Plan vs Universal Template

| Template Section | Plan Status | Gap | Fix |
|------------------|-------------|-----|-----|
| 0. Define work unit | ✅ Complete | None | - |
| 1. Recon & constraints | ✅ Complete | None | - |
| 2. Interface design | ✅ Complete | None | - |
| 3. Folder placement | ✅ Complete | None | - |
| 4. Test scaffolding | ⚠️ Partial | No test file exists | Create during implementation |
| 5. Implementation slices | ✅ Complete | None | - |
| 6. Integration wiring | ⚠️ Partial | No feature flag | Add `enable_cb_optimization` |
| 7. Documentation | ✅ Complete | None | - |
| 8. Quality gates | ✅ Complete | None | - |
| 9. Follow-through | ✅ Complete | None | - |

### Missing Items Identified

1. **Feature Flag** - Should add `enable_cb_optimization` to `SyncBacktestConfig` for safe rollback
2. **Test File** - `tests/test_catboost_optimizer.py` needs to be created
3. **Signature Change** - `_get_model_configs()` needs X_full, y_full, target_name params
4. **CatBoost-Only Mode** - Need model enable flags to skip other models during validation

---

## 🆕 PHASE 0: CatBoost-Only Mode (Added)

**Problem:** Current architecture always trains all 4 models (CB, LGB, LSTM, Linear), even when we only need CatBoost. This wastes time during validation.

**Solution:** Add model enable flags to `SyncBacktestConfig`.

### Changes Required

**File: `backtest/domain/config.py`**
```python
@dataclass
class SyncBacktestConfig:
    ...
    # Model enable flags (for focused validation)
    enable_catboost: bool = True
    enable_lightgbm: bool = True
    enable_lstm: bool = True
    enable_linear: bool = True
```

**File: `backtest/services/training.py`**
```python
def train_predict_classification_permodel(...):
    ...
    # CatBoost - always train if enabled
    if config.enable_catboost:
        cb_result = cb_train_predict_cls(...)
    else:
        cb_result = _create_dummy_result(n_classes, "catboost")
    
    # LightGBM - skip if disabled
    if config.enable_lightgbm:
        lgb_result = lgb_train_predict_cls(...)
    else:
        lgb_result = _create_dummy_result(n_classes, "lightgbm")
    
    # Same for LSTM and Linear...
```

**Usage for CatBoost-only validation:**
```python
cfg = SyncBacktestConfig(
    enable_catboost=True,
    enable_lightgbm=False,
    enable_lstm=False,
    enable_linear=False,
    cb_weight=1.0,
    lgb_weight=0.0,
    lstm_weight=0.0,
    # linear_weight auto-computed = 0.0
)
results = run_sync_backtest(["direction_1bar", "volatility_1bar"], cfg)
```

### Benefits
1. **Fast validation** - Only train CatBoost (~4x faster)
2. **Clean metrics** - Direct CatBoost performance without ensemble noise
3. **No architecture changes** - Same walk-forward loop, same metrics
4. **Reusable** - Can later test LGB-only, LSTM-only, etc.

### Safe Stop Point
✅ Yes - After Phase 0, system works exactly as before (all flags default True)

---

## ✅ PLAN VALIDATION RESULT

**Status: READY FOR IMPLEMENTATION**

All major gaps identified and documented. Two minor items to address during implementation:

1. Add feature flag for safe rollback
2. Create test file structure

The plan follows the universal template and provides:
- Clear scope and success criteria
- Well-defined contracts and interfaces
- Safe stop points between slices
- Comprehensive test coverage plan
- Risk mitigations documented

---

**Ready for user approval to proceed with implementation.**
