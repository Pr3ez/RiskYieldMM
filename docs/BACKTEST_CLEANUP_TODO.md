# 🔧 BACKTEST CLEANUP & INTEGRATION TODO

**Created:** 2026-01-19
**Status:** COMPREHENSIVE AUDIT COMPLETE
**Last Updated:** 2026-01-19

---

## 📁 FILES AUDITED

| File | Lines | Role |
|------|-------|------|
| `scripts/target_models/validation/l2_backtest_sync.py` | 3330 | Main backtest logic |
| `scripts/workflow/config.py` | 387 | L2BacktestDefaults wrapper |
| `notebooks/main_wf.py` | 1089 | Workflow entry point |
| `scripts/run_l2_backtest.py` | ~200 | CLI entry point |

---

## 🔴 CRITICAL ISSUES (MUST FIX)

### Issue 1: ADAPTIVE WEIGHTS - EXISTS BUT NEVER USED

**Evidence:**

```
l2_backtest_sync.py:434:    use_adaptive_weights: bool = True  ← NEVER CHECKED
l2_backtest_sync.py:435:    adaptive_lookback: int = 50        ← NEVER USED
l2_backtest_sync.py:436:    adaptive_learning_rate: float = 0.1 ← NEVER USED
l2_backtest_sync.py:437:    adaptive_min_weight: float = 0.05   ← NEVER USED
l2_backtest_sync.py:1077:   def _update_adaptive_weights(...)   ← NEVER CALLED (count: 1)
```

**Problem:** Config says `use_adaptive_weights=True` but:
- Flag is never checked in any if-statement
- `_update_adaptive_weights()` is defined but never called
- No `recent_accuracies` tracking in main loop (line 2886)

**Fix needed:**
- [ ] Track per-model accuracy in main loop
- [ ] Check `use_adaptive_weights` flag
- [ ] Call `_update_adaptive_weights()` after each step
- [ ] Use returned weights instead of `config.cb_weight` etc

---

### Issue 2: HARDCODED WEIGHTS - 35 REFERENCES

**All locations in l2_backtest_sync.py:**

| Line | Usage | Context |
|------|-------|---------|
| 428 | `cb_weight: float = 0.30` | Config default |
| 429 | `lgb_weight: float = 0.30` | Config default |
| 430 | `lstm_weight: float = 0.25` | Config default |
| 1898-1905 | `config.cb_weight * cb_prob + ...` | Classification binary ensemble |
| 1931-1936 | `config.cb_weight * cb_cal_probs + ...` | Conformal calibration |
| 1990-1997 | `config.cb_weight * cb_probs + ...` | Classification multiclass ensemble |
| 2032-2035 | `"cb_weight_used": config.cb_weight` | Metrics logging |
| 2489-2496 | `config.cb_weight * cb_pred + ...` | Regression ensemble |
| 2511-2514 | `config.cb_weight * cb_cal_preds + ...` | Regression conformal |
| 2532-2535 | `"cb_weight_used": config.cb_weight` | Regression metrics |
| 2746-2750 | Print statements | Info logging |

**In workflow/config.py:**

| Line | Usage |
|------|-------|
| 239-241 | `cb_weight: float = 0.30` etc | L2BacktestDefaults |
| 258-260 | `def linear_weight(self)` | Property |
| 270-272 | `to_sync_config_kwargs()` | Passes to SyncBacktestConfig |
| 289-290 | `print_summary()` | Info logging |

**Problem:** Weights should be DYNAMIC based on model performance, not static

---

### Issue 3: L2BacktestDefaults MISSING FIELDS

**SyncBacktestConfig has (lines 404-490):**
```python
# Split ratios
train_ratio: float = 0.55
val_ratio: float = 0.15
cal_ratio: float = 0.30
embargo_bars: int = 24
random_state: int = 42

# Adaptive weights
use_adaptive_weights: bool = True
adaptive_lookback: int = 50
adaptive_learning_rate: float = 0.1
adaptive_min_weight: float = 0.05

# Additional model params
cb_l2_leaf_reg: float = 5.0
lgb_reg_lambda: float = 3.0
lgb_min_child_samples: int = 20
lstm_hidden_size: int = 64
lstm_num_layers: int = 2
lstm_lr: float = 0.001
lstm_epochs: int = 100
lstm_batch_size: int = 32
lstm_dropout: float = 0.2
lstm_seq_len: int = 20

# Conformal
conformal_alpha: float = 0.1

# Feature clipping
duration_max: float = 1000.0

# Sample weighting
use_sample_weights: bool = True
sample_decay_halflife: float = 0.3

# Per-model configs
cb_config: PerModelConfig | None = None
lgb_config: PerModelConfig | None = None
lstm_config: PerModelConfig | None = None
linear_config: PerModelConfig | None = None
```

**L2BacktestDefaults has (lines 221-280):**
```python
train_window: int = 500
step_size: int = 1
n_steps: int | None = None
n_estimators: int = 100
max_depth: int = 6
cb_weight: float = 0.30
lgb_weight: float = 0.30
lstm_weight: float = 0.25
cb_learning_rate: float = 0.03
lgb_learning_rate: float = 0.03
enable_optuna: bool = True
n_optuna_trials: int = 15
optuna_timeout: float | None = 30.0
store_extended_metrics: bool = False
```

**MISSING from L2BacktestDefaults:**
- [ ] `use_adaptive_weights`
- [ ] `adaptive_lookback`
- [ ] `adaptive_learning_rate`
- [ ] `adaptive_min_weight`
- [ ] `train_ratio`, `val_ratio`, `cal_ratio`
- [ ] `embargo_bars`
- [ ] All LSTM params
- [ ] `use_sample_weights`, `sample_decay_halflife`
- [ ] `conformal_alpha`
- [ ] `PerModelConfig` support (cb_config, lgb_config, etc.)

**ALSO MISSING from `to_sync_config_kwargs()`:**
All the above fields are NOT passed when creating SyncBacktestConfig!

---

### Issue 4: DUPLICATED WEIGHT COMPUTATION

Same pattern appears 6 times:
```python
linear_weight = max(0.0, 1.0 - config.cb_weight - config.lgb_weight - config.lstm_weight)
ensemble = (
    config.cb_weight * cb_pred
    + config.lgb_weight * lgb_pred
    + config.lstm_weight * lstm_pred
    + linear_weight * linear_pred
)
```

**Locations:**
- Line 1898-1905 (binary classification)
- Line 1931-1936 (conformal calibration)
- Line 1990-1997 (multiclass classification)
- Line 2489-2496 (regression)
- Line 2511-2514 (regression conformal)
- Line 2746-2750 (print summary)

**Fix needed:**
- [ ] Create `_compute_ensemble()` helper function
- [ ] Accept weights dict as parameter
- [ ] Call helper everywhere

---

### Issue 5: DEAD CODE - FUNCTIONS NEVER CALLED

| Function | Line | Count | Status |
|----------|------|-------|--------|
| `_update_adaptive_weights` | 1077 | 1 (def only) | DEAD |
| `_compute_sample_weights` | 1031 | 1 (def only) | DEAD |
| `_tune_classification_params` | 1143 | 1 (def only) | DEAD? |
| `_tune_regression_params` | 1298 | 1 (def only) | DEAD? |
| `validate()` on PerModelConfig | 594 | 1 (def only) | DEAD |

**Investigation needed:**
- [ ] Confirm these are truly unused
- [ ] Either integrate or remove

---

## 🟡 CONFIG SYNC ISSUES

### `to_sync_config_kwargs()` incomplete

**Currently passes (14 fields):**
```python
train_window, step_size, n_steps, n_estimators, max_depth,
cb_weight, lgb_weight, lstm_weight,
cb_learning_rate, lgb_learning_rate,
enable_optuna, n_optuna_trials, optuna_timeout,
store_extended_metrics
```

**Should also pass (~20 more fields):**
```python
# Splits
train_ratio, val_ratio, cal_ratio, embargo_bars

# Adaptive weights
use_adaptive_weights, adaptive_lookback, adaptive_learning_rate, adaptive_min_weight

# Model params
cb_l2_leaf_reg, lgb_reg_lambda, lgb_min_child_samples,
lstm_hidden_size, lstm_num_layers, lstm_lr, lstm_epochs, lstm_batch_size, lstm_dropout, lstm_seq_len

# Features
conformal_alpha, duration_max, use_sample_weights, sample_decay_halflife
```

---

## 🟢 ITEMS CONFIRMED WORKING

- [x] `PerModelConfig` dataclass (line 554)
- [x] `DEFAULT_CB_CONFIG`, `DEFAULT_LGB_CONFIG`, `DEFAULT_LSTM_CONFIG`, `DEFAULT_LINEAR_CONFIG` (lines 607-649)
- [x] `SyncBacktestConfig.__post_init__` auto-creates per-model configs (line 493)
- [x] `get_model_config()` returns PerModelConfig (line 523)
- [x] `_train_predict_classification_permodel()` uses per-model splits (line 1491)
- [x] `_train_predict_regression_permodel()` uses per-model splits (line 2157)
- [x] `_extract_per_model_splits()` extracts correct windows (line 1433)
- [x] Dynamic embargo via `get_embargo_for_horizon()` (line 857)
- [x] Main loop structure (line 2886)
- [x] Config data flow: `L2BacktestDefaults` → `to_sync_config_kwargs()` → `SyncBacktestConfig`

---

## 📊 CALL GRAPH

```
notebooks/main_wf.py
    └── L2BacktestDefaults() (line 1025)
    └── .to_sync_config_kwargs() (line 1053)
    └── SyncBacktestConfig(**kwargs) (line 1053)
    └── run_sync_backtest(config=sync_config) (line 1062)
        └── for step in range(n_iterations): (line 2886)
            └── _train_predict_classification_permodel() (line 2914)
                └── _extract_per_model_splits() × 4
                └── Uses config.cb_weight etc (HARDCODED)
                └── NEVER calls _update_adaptive_weights()
            └── _train_predict_regression_permodel() (line 2936)
                └── Same pattern
```

---

## 📋 IMPLEMENTATION PLAN

### Phase 1: Fix Adaptive Weights Integration

**Step 1:** Add tracking in main loop (around line 2886)
```python
# Initialize before loop
recent_accuracies = {m: deque(maxlen=cfg.adaptive_lookback) for m in ["cb", "lgb", "lstm", "linear"]}
current_weights = {
    "cb_weight": cfg.cb_weight,
    "lgb_weight": cfg.lgb_weight,
    "lstm_weight": cfg.lstm_weight,
    "linear_weight": max(0, 1 - cfg.cb_weight - cfg.lgb_weight - cfg.lstm_weight)
}
```

**Step 2:** Track accuracy after each prediction (around line 2960)
```python
# After prediction
if data.task_type == "classification":
    recent_accuracies["cb"].append(int(components["cb_pred"] == y_true))
    recent_accuracies["lgb"].append(int(components["lgb_pred"] == y_true))
    # ...
```

**Step 3:** Update weights (around line 2965)
```python
if cfg.use_adaptive_weights and step >= cfg.adaptive_lookback:
    current_weights = _update_adaptive_weights(
        current_weights,
        {k: list(v) for k, v in recent_accuracies.items()},
        cfg.adaptive_learning_rate,
        cfg.adaptive_min_weight
    )
```

**Step 4:** Modify train functions to accept weights parameter
- Change `_train_predict_classification_permodel()` signature
- Change `_train_predict_regression_permodel()` signature
- Use passed weights instead of `config.cb_weight`

### Phase 2: Sync Configs

**Step 1:** Add missing fields to L2BacktestDefaults
**Step 2:** Update `to_sync_config_kwargs()` to pass all fields
**Step 3:** Add PerModelConfig support to L2BacktestDefaults (optional)

### Phase 3: Remove Dead Code

**Step 1:** Verify `_compute_sample_weights` is unused → remove or integrate
**Step 2:** Verify `_tune_classification_params`/`_tune_regression_params` → likely dead
**Step 3:** Call `PerModelConfig.validate()` or remove

### Phase 4: Refactor Duplications

**Step 1:** Create `_compute_ensemble(predictions, weights)` helper
**Step 2:** Replace all 6 duplicate patterns

---

## 🔍 GREP COMMANDS FOR VERIFICATION

```bash
# Find all adaptive weight refs
grep -n "_update_adaptive_weights\|use_adaptive_weights\|adaptive_lookback\|adaptive_learning_rate\|adaptive_min_weight" scripts/target_models/validation/l2_backtest_sync.py

# Find all hardcoded weight refs
grep -n "cb_weight\|lgb_weight\|lstm_weight\|linear_weight" scripts/target_models/validation/l2_backtest_sync.py

# Find dead functions (count=1 means only definition)
grep -oE "def [a-z_]+\(" FILE | sed 's/def //' | sed 's/($//' | while read f; do echo "$(grep -c "$f" FILE) $f"; done | sort -n
```

---

## ❓ DECISIONS NEEDED

1. **Keep hardcoded weights as fallback when `use_adaptive_weights=False`?**
   - RECOMMENDED: Yes, keep as initial weights and fallback

2. **Per-target or global weight tracking?**
   - CURRENT: Per-target (each config has own tracker)
   - RECOMMENDED: Keep per-target

3. **Should L2BacktestDefaults mirror ALL SyncBacktestConfig fields?**
   - Option A: Yes, full sync
   - Option B: Only commonly-changed fields
   - RECOMMENDED: Add critical fields (adaptive, splits), leave advanced defaults

4. **What to do with dead code?**
   - `_compute_sample_weights` → integrate or remove?
   - `_tune_*_params` → investigate if called elsewhere

---

## 🎯 PRIORITY ORDER

1. 🔴 **HIGH:** Integrate adaptive weights (Issue 1)
2. 🔴 **HIGH:** Fix config sync (Issue 3) - affects all users
3. 🟡 **MEDIUM:** Remove weight duplication (Issue 4)
4. 🟡 **MEDIUM:** Investigate/remove dead code (Issue 5)
5. 🟢 **LOW:** Full L2BacktestDefaults sync

---

# 🏗️ ARCHITECTURE REORGANIZATION PLAN

**Main Entry Point:** `notebooks/main_wf.py` (Python script version of notebook)

## Research Foundation

| Principle | Source | Application |
|-----------|--------|-------------|
| **Information Hiding** | Parnas 1972 (ACM) | Split by change-prone decisions, hide behind stable interfaces |
| **Maintainability** | ISO/IEC 25010 | Modularity, analysability, modifiability, reusability |
| **Cohesion/Coupling** | Stevens/Myers/Constantine | High cohesion (one responsibility), low coupling (minimal dependencies) |
| **Dependency Rule** | Clean Architecture (Uncle Bob) | Core must not depend on frameworks/adapters |
| **Hexagonal/Ports & Adapters** | Alistair Cockburn | Define ports in core, implement adapters outside |
| **Strangler Fig** | Martin Fowler | Gradual migration, not big-bang rewrite |
| **Refactoring Discipline** | Fowler | Small behavior-preserving transformations |

## Current Structure Analysis

```
scripts/
├── workflow/
│   ├── config.py          ← L2BacktestDefaults (INCOMPLETE)
│   ├── __init__.py        ← Exports
│   └── ...
├── target_models/
│   └── validation/
│       └── l2_backtest_sync.py  ← EVERYTHING (3330 lines, god module)
├── run_l2_backtest.py     ← CLI entrypoint
└── tests/
    └── test_lstm_gap_fix.py

notebooks/
└── main_wf.py             ← MAIN ENTRY POINT (workflow orchestration)
```

**Problems:**
- `l2_backtest_sync.py` is a **god module** (3330 lines, 40+ functions)
- Configs split between `workflow/config.py` and `l2_backtest_sync.py`
- Core logic mixed with I/O, training, validation, reporting
- No clear adapter boundaries for future exchange support

## Target Architecture

```
src/riskyieldmm/
├── core/                  ← PURE LOGIC (no I/O, no side effects)
│   ├── ensemble.py        ← Weight computation, adaptive weights
│   ├── metrics.py         ← Accuracy, AUC, regression metrics
│   ├── splits.py          ← Train/val/cal splitting logic
│   └── conformal.py       ← Conformal prediction sets
│
├── domain/                ← DATA STRUCTURES (types, contracts)
│   ├── config.py          ← SyncBacktestConfig, PerModelConfig
│   ├── results.py         ← Prediction results, metrics dicts
│   └── types.py           ← Type aliases, enums
│
├── services/              ← ORCHESTRATION (calls core + adapters)
│   ├── backtest.py        ← run_sync_backtest() main loop
│   ├── training.py        ← _train_predict_* functions
│   └── tuning.py          ← Optuna tuning logic
│
├── adapters/              ← SIDE EFFECTS (I/O, external)
│   ├── data_loader.py     ← _load_config_data, _load_timestamps
│   ├── model_io.py        ← Model save/load
│   └── reporting.py       ← Logging, file output, DualOutput
│
├── models/                ← MODEL DEFINITIONS
│   ├── lstm.py            ← LSTMClassifier, LSTMRegressor
│   ├── catboost_wrapper.py
│   └── lightgbm_wrapper.py
│
└── cli/                   ← THIN ENTRYPOINTS
    └── run_backtest.py    ← Parse args, build config, call services

notebooks/
└── main_wf.py             ← Workflow orchestration (calls services)
```

## Migration Plan (Strangler Fig)

### Phase 0: Safety Baseline
- [ ] Identify all entry points: `main_wf.py`, `run_l2_backtest.py`, tests
- [ ] Create golden output snapshots from current backtest runs
- [ ] Ensure tests pass before any changes

### Phase 1: Build Dependency Map
- [ ] Generate import graph for `l2_backtest_sync.py`
- [ ] Identify circular imports
- [ ] Classify functions into CORE / EDGE / ORCHESTRATION

**Current Classification (from audit):**

| Category | Functions | Lines |
|----------|-----------|-------|
| **CORE (pure)** | `_update_adaptive_weights`, `_compute_sample_weights`, `_build_step_metrics`, `_compute_config_metrics`, `get_embargo_for_horizon` | ~200 |
| **MODELS** | `LSTMClassifier`, `LSTMRegressor`, `_train_lstm_*`, `_create_sequences` | ~300 |
| **TRAINING** | `_train_predict_classification_permodel`, `_train_predict_regression_permodel`, `_extract_per_model_splits` | ~1200 |
| **TUNING** | `_tune_*_params`, `_tune_cb_*`, `_tune_lgb_*` | ~400 |
| **I/O** | `_load_config_data`, `_load_timestamps_for_config`, `_parse_config`, `_clip_features`, `DualOutput` | ~200 |
| **ORCHESTRATION** | `run_sync_backtest` | ~600 |
| **CONFIG** | `SyncBacktestConfig`, `PerModelConfig`, `ConfigData`, defaults | ~300 |

### Phase 2: Extract Core First
- [ ] Move `_update_adaptive_weights` → `core/ensemble.py`
- [ ] Move `_compute_sample_weights` → `core/weights.py`
- [ ] Move `get_embargo_for_horizon` → `core/splits.py`
- [ ] Move `_build_step_metrics`, `_compute_config_metrics` → `core/metrics.py`
- [ ] Keep imports working via re-exports

### Phase 3: Extract Domain Types
- [ ] Move `SyncBacktestConfig` → `domain/config.py`
- [ ] Move `PerModelConfig` → `domain/config.py`
- [ ] Move `ConfigData` → `domain/types.py`
- [ ] Unify `L2BacktestDefaults` with `SyncBacktestConfig`

### Phase 4: Extract Adapters
- [ ] Move `_load_config_data`, `_load_timestamps_for_config` → `adapters/data_loader.py`
- [ ] Move `DualOutput` → `adapters/reporting.py`
- [ ] Move model save/load (if any) → `adapters/model_io.py`

### Phase 5: Extract Services
- [ ] Move `_train_predict_*` → `services/training.py`
- [ ] Move tuning functions → `services/tuning.py`
- [ ] Move `run_sync_backtest` → `services/backtest.py`

### Phase 6: Clean Entrypoints
- [ ] Make `run_l2_backtest.py` thin (parse args → call service)
- [ ] Make `main_wf.py` call services, not internal functions
- [ ] Remove side effects from module-level code

## Dependency Rules (ENFORCE)

```
              ┌─────────────────────────────────────┐
              │          cli/ notebooks/            │
              │    (thin wrappers, arg parsing)     │
              └─────────────┬───────────────────────┘
                            │ calls
                            ▼
              ┌─────────────────────────────────────┐
              │           services/                 │
              │   (orchestration, use-cases)        │
              └──────┬──────────────────┬───────────┘
                     │                  │
            calls    │                  │ calls
                     ▼                  ▼
        ┌────────────────┐    ┌─────────────────────┐
        │     core/      │    │     adapters/       │
        │ (pure logic)   │    │ (I/O, side effects) │
        └────────┬───────┘    └─────────────────────┘
                 │
           uses  │
                 ▼
        ┌────────────────┐
        │    domain/     │
        │ (types, config)│
        └────────────────┘
```

**Rules:**
1. `core/` imports ONLY from `domain/` and stdlib
2. `adapters/` imports from `domain/` (never from `core/`)
3. `services/` imports from `core/`, `adapters/`, `domain/`
4. `cli/` imports from `services/`, `domain/`
5. NO circular imports
6. NO side effects at import time

## Definition of Done

- [ ] Baseline tests pass with identical outputs
- [ ] Import graph has no cycles
- [ ] Core modules have zero imports from adapters
- [ ] Entry scripts are thin wrappers only
- [ ] `l2_backtest_sync.py` < 500 lines (orchestration only)
- [ ] ARCHITECTURE_NOTES.md describes boundaries
- [ ] All configs unified (no L2BacktestDefaults vs SyncBacktestConfig split)

## Work Style

- **Small commits:** "move one function", "extract one interface"
- **Run baseline after each change**
- **Never big-bang rewrite**
- **Preserve all existing behavior**
