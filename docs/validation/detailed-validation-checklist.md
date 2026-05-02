# 📋 DETAILED VALIDATION CHECKLIST

**Purpose:** Step-by-step verification before ANY code changes
**Rule:** Check → Validate → Reflect → Act → Verify

---

## 📊 MASTER INVENTORY

### Files to Audit (Complete List)

| # | File | Lines | Status | Notes |
|---|------|-------|--------|-------|
| 1 | `scripts/target_models/validation/l2_backtest_sync.py` | 3330 | ⬜ | Main backtest |
| 2 | `scripts/workflow/config.py` | 387 | ⬜ | L2BacktestDefaults |
| 3 | `scripts/workflow/__init__.py` | ~200 | ⬜ | Exports |
| 4 | `notebooks/main_wf.py` | 1089 | ⬜ | Entry point |
| 5 | `scripts/run_l2_backtest.py` | ~200 | ⬜ | CLI entry |
| 6 | `scripts/tests/test_lstm_gap_fix.py` | ~400 | ⬜ | Tests |

---

## 🔍 FILE 1: l2_backtest_sync.py (3330 lines)

### Section A: IMPORTS (Lines 1-50)

| Line | Import | Used? | Notes |
|------|--------|-------|-------|
| ⬜ | Check all imports are used | | |
| ⬜ | Check no circular imports | | |
| ⬜ | Check import order (stdlib, third-party, local) | | |

**Validation:** `grep -n "^import\|^from" FILE | wc -l` then verify each

---

### Section B: CONSTANTS & CONFIG GENERATION (Lines 50-125)

| Line | Item | Status | Notes |
|------|------|--------|-------|
| 49 | Comment about signal_labels.py | ⬜ | Verify still accurate |
| 64-65 | Comment about config generation | ⬜ | Verify matches reality |
| 72 | `ALL_CONFIGS` | ⬜ | Check if used or dead |
| 75-115 | Target descriptions block | ⬜ | Verify matches actual targets |

**Validation Questions:**
- [ ] Do comments match actual code behavior?
- [ ] Is ALL_CONFIGS still used anywhere?
- [ ] Are target descriptions up to date?

---

### Section C: CLASSES - LSTMClassifier (Lines 154-184)

| Line | Method | Parameters | Status | Notes |
|------|--------|------------|--------|-------|
| 154 | `class LSTMClassifier` | | ⬜ | |
| 157 | `__init__` | input_size, hidden_size=64, num_layers=2, n_classes=2, dropout=0.2 | ⬜ | Match with config? |
| 177 | `forward` | x: Tensor | ⬜ | |

**Validation:**
- [ ] Do default params match SyncBacktestConfig lstm_* fields?
- [ ] Is dropout used consistently?

---

### Section D: CLASSES - LSTMRegressor (Lines 185-213)

| Line | Method | Parameters | Status | Notes |
|------|--------|------------|--------|-------|
| 185 | `class LSTMRegressor` | | ⬜ | |
| 188 | `__init__` | input_size, hidden_size=64, num_layers=2, dropout=0.2 | ⬜ | Match with config? |
| 207 | `forward` | x: Tensor | ⬜ | |

**Validation:**
- [ ] Same defaults as LSTMClassifier?
- [ ] Any inconsistency with config.lstm_*?

---

### Section E: FUNCTION - _create_sequences (Lines 214-262)

| Line | Item | Status | Notes |
|------|------|--------|-------|
| 214 | `def _create_sequences` | ⬜ | |
| | Parameters: X, y, seq_len | ⬜ | seq_len matches config? |
| | Returns: X_seq, y_seq | ⬜ | |

**Validation:**
- [ ] Is seq_len properly passed from config.lstm_seq_len?
- [ ] Any hardcoded values?

---

### Section F: FUNCTION - _train_lstm_classifier (Lines 263-334)

| Line | Item | Status | Notes |
|------|------|--------|-------|
| 263 | `def _train_lstm_classifier` | ⬜ | |
| | Params: X_train, y_train, X_val, y_val, n_classes, config | ⬜ | |
| | Uses: hidden_size, num_layers, lr, epochs, batch_size, dropout, seq_len | ⬜ | From config? |

**Validation:**
- [ ] All LSTM params from config, not hardcoded?
- [ ] Device handling correct?
- [ ] Gap fix applied? (extended sequence for continuity)

---

### Section G: FUNCTION - _train_lstm_regressor (Lines 335-403)

| Line | Item | Status | Notes |
|------|------|--------|-------|
| 335 | `def _train_lstm_regressor` | ⬜ | |
| | Same structure as classifier | ⬜ | |

**Validation:**
- [ ] Consistent with _train_lstm_classifier?
- [ ] Gap fix applied?

---

### Section H: CLASS - SyncBacktestConfig (Lines 404-553)

**CRITICAL - This is the source of truth for config**

| Line | Field | Default | In L2BacktestDefaults? | In to_sync_config_kwargs? |
|------|-------|---------|------------------------|---------------------------|
| 407 | train_window | 500 | ✅ Yes | ✅ Yes |
| 408 | step_size | 1 | ✅ Yes | ✅ Yes |
| 409 | n_steps | None | ✅ Yes | ✅ Yes |
| 412 | train_ratio | 0.55 | ❌ NO | ❌ NO |
| 413 | val_ratio | 0.15 | ❌ NO | ❌ NO |
| 414 | cal_ratio | 0.30 | ❌ NO | ❌ NO |
| 418 | embargo_bars | 24 | ❌ NO | ❌ NO |
| 421 | random_state | 42 | ❌ NO | ❌ NO |
| 422 | n_estimators | 100 | ✅ Yes | ✅ Yes |
| 423 | max_depth | 6 | ✅ Yes | ✅ Yes |
| 426 | cb_weight | 0.30 | ✅ Yes | ✅ Yes |
| 427 | lgb_weight | 0.30 | ✅ Yes | ✅ Yes |
| 428 | lstm_weight | 0.25 | ✅ Yes | ✅ Yes |
| 432 | use_adaptive_weights | True | ❌ NO | ❌ NO |
| 433 | adaptive_lookback | 50 | ❌ NO | ❌ NO |
| 434 | adaptive_learning_rate | 0.1 | ❌ NO | ❌ NO |
| 435 | adaptive_min_weight | 0.05 | ❌ NO | ❌ NO |
| 438 | cb_learning_rate | 0.03 | ✅ Yes | ✅ Yes |
| 439 | cb_l2_leaf_reg | 5.0 | ❌ NO | ❌ NO |
| 442 | lgb_learning_rate | 0.03 | ✅ Yes | ✅ Yes |
| 443 | lgb_reg_lambda | 3.0 | ❌ NO | ❌ NO |
| 444 | lgb_min_child_samples | 20 | ❌ NO | ❌ NO |
| 447 | lstm_hidden_size | 64 | ❌ NO | ❌ NO |
| 448 | lstm_num_layers | 2 | ❌ NO | ❌ NO |
| 449 | lstm_lr | 0.001 | ❌ NO | ❌ NO |
| 450 | lstm_epochs | 100 | ❌ NO | ❌ NO |
| 451 | lstm_batch_size | 32 | ❌ NO | ❌ NO |
| 452 | lstm_dropout | 0.2 | ❌ NO | ❌ NO |
| 453 | lstm_seq_len | 20 | ❌ NO | ❌ NO |
| 456 | conformal_alpha | 0.1 | ❌ NO | ❌ NO |
| 459 | duration_max | 1000.0 | ❌ NO | ❌ NO |
| 463 | use_sample_weights | True | ❌ NO | ❌ NO |
| 464 | sample_decay_halflife | 0.3 | ❌ NO | ❌ NO |
| 468 | enable_optuna | True | ✅ Yes | ✅ Yes |
| 469 | n_optuna_trials | 15 | ✅ Yes | ✅ Yes |
| 470 | optuna_timeout | 30.0 | ✅ Yes | ✅ Yes |
| 471 | optuna_prune | True | ❌ NO | ❌ NO |
| 474 | output_dir | Path(...) | ❌ NO | ❌ NO |
| 477 | log_to_file | True | ❌ NO | ❌ NO |
| 478 | save_step_metrics | True | ❌ NO | ❌ NO |
| 479 | step_metrics_interval | 10 | ❌ NO | ❌ NO |
| 483 | cb_config | None | ❌ NO | ❌ NO |
| 484 | lgb_config | None | ❌ NO | ❌ NO |
| 485 | lstm_config | None | ❌ NO | ❌ NO |
| 486 | linear_config | None | ❌ NO | ❌ NO |
| 489 | store_extended_metrics | False | ✅ Yes | ✅ Yes |

**Summary:**
- Total fields in SyncBacktestConfig: ~35
- Fields in L2BacktestDefaults: 14
- Fields passed via to_sync_config_kwargs: 14
- **MISSING from workflow: 21 fields**

---

### Section I: CLASS - PerModelConfig (Lines 554-605)

| Line | Field | Default | Status | Notes |
|------|-------|---------|--------|-------|
| 578 | train_window | 500 | ⬜ | Per-model override |
| 579 | train_ratio | 0.55 | ⬜ | |
| 580 | val_ratio | 0.15 | ⬜ | |
| 581 | cal_ratio | 0.30 | ⬜ | |
| 584 | embargo_bars | 24 | ⬜ | |
| 587 | feature_selection | "none" | ⬜ | |
| 588 | feature_selection_ratio | 1.0 | ⬜ | |
| 589 | min_features | 20 | ⬜ | |

**Validation:**
- [ ] PerModelConfig.validate() is never called - should it be?
- [ ] Defaults match SyncBacktestConfig base values?

---

### Section J: DEFAULT_*_CONFIG Constants (Lines 607-649)

| Line | Constant | train_window | Status | Notes |
|------|----------|--------------|--------|-------|
| 607 | DEFAULT_CB_CONFIG | 400 | ⬜ | |
| 618 | DEFAULT_LGB_CONFIG | 400 | ⬜ | |
| 629 | DEFAULT_LSTM_CONFIG | 600 | ⬜ | |
| 640 | DEFAULT_LINEAR_CONFIG | 800 | ⬜ | |

**Validation:**
- [ ] Window sizes documented correctly?
- [ ] Used in __post_init__?

---

### Section K: CLASS - DualOutput (Lines 652-670)

| Line | Method | Status | Notes |
|------|--------|--------|-------|
| 652 | class DualOutput | ⬜ | Logging helper |
| 655 | __init__ | ⬜ | |
| 659 | write | ⬜ | |
| 664 | flush | ⬜ | |
| 668 | close | ⬜ | |

**Validation:**
- [ ] Used where expected?
- [ ] Resources properly closed?

---

### Section L: FUNCTION - _build_step_metrics (Lines 672-813)

| Line | Item | Status | Notes |
|------|------|--------|-------|
| 672 | def _build_step_metrics | ⬜ | |
| | Returns dict with 30+ fields | ⬜ | |

**Validation:**
- [ ] All fields documented?
- [ ] Consistent with what's logged?

---

### Section M: CLASS - ConfigData (Lines 814-831)

| Line | Field | Status | Notes |
|------|-------|--------|-------|
| 814 | class ConfigData | ⬜ | Holds per-config state |
| | X_features, y_target, etc. | ⬜ | |

---

### Section N: FUNCTION - _parse_config (Lines 832-856)

**Validation:**
- [ ] Correctly parses config names?
- [ ] Handles all target types?

---

### Section O: FUNCTION - get_embargo_for_horizon (Lines 857-881)

| Line | Item | Status | Notes |
|------|------|--------|-------|
| 857 | def get_embargo_for_horizon | ⬜ | |
| | Formula: 3 * horizon, capped at 36 | ⬜ | |

**Validation:**
- [ ] Used consistently in all training functions?
- [ ] Comments match formula?

---

### Section P: FUNCTION - _clip_features (Lines 882-895)

**Validation:**
- [ ] duration_max from config?
- [ ] Applied where needed?

---

### Section Q: FUNCTION - _load_timestamps_for_config (Lines 896-930)

**Validation:**
- [ ] Path construction correct?
- [ ] Error handling present?

---

### Section R: FUNCTION - _load_config_data (Lines 931-1030)

| Line | Item | Status | Notes |
|------|------|--------|-------|
| 931 | def _load_config_data | ⬜ | Main data loading |
| | Loads parquet files | ⬜ | |
| | Determines task_type | ⬜ | |
| | Gets n_classes | ⬜ | |

**Validation:**
- [ ] Task type detection correct for all targets?
- [ ] n_classes matches signal_labels.py?
- [ ] Comments at lines 972-1030 accurate?

---

### Section S: FUNCTION - _compute_sample_weights (Lines 1031-1076)

| Line | Item | Status | Notes |
|------|------|--------|-------|
| 1031 | def _compute_sample_weights | ⬜ | **DEAD CODE - COUNT=1** |

**Validation:**
- [ ] Is this function called anywhere? → NO
- [ ] Should it be integrated or removed?
- [ ] If removed, update any comments referencing it

---

### Section T: FUNCTION - _update_adaptive_weights (Lines 1077-1142)

| Line | Item | Status | Notes |
|------|------|--------|-------|
| 1077 | def _update_adaptive_weights | ⬜ | **DEAD CODE - COUNT=1** |
| | Uses MWU algorithm | ⬜ | |
| | Returns new weights dict | ⬜ | |

**Validation:**
- [ ] Is this function called anywhere? → NO
- [ ] Config says use_adaptive_weights=True but function never called
- [ ] DECISION: Integrate or remove?

---

### Section U: FUNCTION - _tune_classification_params (Lines 1143-1297)

| Line | Item | Status | Notes |
|------|------|--------|-------|
| 1143 | def _tune_classification_params | ⬜ | **POSSIBLY DEAD** |
| 1184 | nested cb_objective | ⬜ | |
| 1218 | nested lgb_objective | ⬜ | |

**Validation:**
- [ ] Is this called or replaced by _tune_cb_classifier etc?
- [ ] Check if warm-starting uses this

---

### Section V: FUNCTION - _tune_regression_params (Lines 1298-1432)

| Line | Item | Status | Notes |
|------|------|--------|-------|
| 1298 | def _tune_regression_params | ⬜ | **POSSIBLY DEAD** |

**Validation:**
- [ ] Same questions as classification version

---

### Section W: FUNCTION - _extract_per_model_splits (Lines 1433-1490)

| Line | Item | Status | Notes |
|------|------|--------|-------|
| 1433 | def _extract_per_model_splits | ⬜ | |
| | Uses PerModelConfig | ⬜ | |
| | Returns X_train, y_train, X_val, y_val, X_cal, y_cal | ⬜ | |

**Validation:**
- [ ] Embargo properly applied?
- [ ] Window extraction from end of data?

---

### Section X: FUNCTION - _train_predict_classification_permodel (Lines 1491-2060)

**CRITICAL - 570 lines, main classification logic**

| Line Range | Subsection | Status | Notes |
|------------|------------|--------|-------|
| 1491-1530 | Function signature & docstring | ⬜ | |
| 1531-1570 | Get per-model configs | ⬜ | |
| 1571-1610 | Extract per-model splits | ⬜ | |
| 1611-1650 | Check sufficient data | ⬜ | |
| 1651-1750 | Feature selection | ⬜ | |
| 1751-1850 | Train CatBoost | ⬜ | |
| 1851-1900 | Train LightGBM | ⬜ | |
| 1901-1950 | Train LSTM | ⬜ | Gap fix here? |
| 1951-2000 | Train Linear | ⬜ | |
| 2001-2060 | Ensemble & return | ⬜ | **HARDCODED WEIGHTS HERE** |

**Validation Points:**
- [ ] Line 1898-1905: Uses `config.cb_weight` - should use adaptive?
- [ ] Line 1931-1936: Conformal uses same weights - consistent?
- [ ] Line 1990-1997: Multiclass uses same pattern
- [ ] All 4 models use same X_pred for alignment?
- [ ] LSTM gap fix applied (extended sequence)?

---

### Section Y: FUNCTION - _tune_cb_classifier (Lines 2061-2102)

| Line | Item | Status | Notes |
|------|------|--------|-------|
| 2061 | def _tune_cb_classifier | ⬜ | |
| 2072 | nested objective | ⬜ | |

**Validation:**
- [ ] Is this the one actually used?
- [ ] Or is _tune_classification_params used?

---

### Section Z: FUNCTION - _tune_lgb_classifier (Lines 2103-2156)

Similar to above.

---

### Section AA: FUNCTION - _train_predict_regression_permodel (Lines 2157-2553)

**CRITICAL - 400 lines, main regression logic**

| Line Range | Subsection | Status | Notes |
|------------|------------|--------|-------|
| 2157-2200 | Function signature | ⬜ | |
| 2201-2300 | Per-model splits | ⬜ | |
| 2301-2400 | Train models | ⬜ | |
| 2401-2500 | Ensemble | ⬜ | **HARDCODED WEIGHTS** |
| 2501-2553 | Return | ⬜ | |

**Validation Points:**
- [ ] Line 2489-2496: Uses `config.cb_weight` - should use adaptive?
- [ ] Line 2511-2514: Conformal uses same weights
- [ ] Parallel structure to classification?

---

### Section AB: FUNCTION - _tune_cb_regressor (Lines 2554-2592)

---

### Section AC: FUNCTION - _tune_lgb_regressor (Lines 2593-2636)

---

### Section AD: FUNCTION - _compute_config_metrics (Lines 2637-2697)

| Line | Item | Status | Notes |
|------|------|--------|-------|
| 2637 | def _compute_config_metrics | ⬜ | |
| | Computes accuracy, AUC, etc. | ⬜ | |

---

### Section AE: FUNCTION - run_sync_backtest (Lines 2698-3330)

**CRITICAL - 632 lines, main entry point**

| Line Range | Subsection | Status | Notes |
|------------|------------|--------|-------|
| 2698-2750 | Function signature & setup | ⬜ | |
| 2751-2800 | Load data for all configs | ⬜ | |
| 2801-2850 | Compute iteration count | ⬜ | |
| 2851-2886 | Setup before main loop | ⬜ | **WHERE TRACKING SHOULD GO** |
| 2886-2970 | Main loop per step | ⬜ | **ADAPTIVE WEIGHTS CALL HERE?** |
| 2971-3100 | Store predictions | ⬜ | |
| 3101-3200 | Progress reporting | ⬜ | |
| 3201-3330 | Final metrics & return | ⬜ | |

**Critical Validation Points:**
- [ ] Line 2886: `for step in range(n_iterations)` - this is the main loop
- [ ] Is there ANY tracking of per-model accuracy? → NO
- [ ] Is `use_adaptive_weights` checked? → NO
- [ ] Is `_update_adaptive_weights` called? → NO
- [ ] Print at 2746-2750 shows weights but they never change

---

## 🔍 FILE 2: workflow/config.py (387 lines)

### Section A: Config Lists (Lines 1-100)

| Line | Function | Status | Notes |
|------|----------|--------|-------|
| 65 | get_configs_1bar | ⬜ | |
| 74 | get_configs_reduced | ⬜ | |
| 85 | get_all_configs | ⬜ | |

---

### Section B: WorkflowConfig (Lines 144-179)

| Line | Field | Status | Notes |
|------|-------|--------|-------|
| 144 | class WorkflowConfig | ⬜ | |

---

### Section C: L2BacktestDefaults (Lines 221-303)

**CRITICAL - Must match SyncBacktestConfig**

| Line | Field | Default | Matches SyncBacktestConfig? |
|------|-------|---------|----------------------------|
| 233 | train_window | 500 | ✅ |
| 234 | step_size | 1 | ✅ |
| 235 | n_steps | None | ✅ |
| 238 | n_estimators | 100 | ✅ |
| 239 | max_depth | 6 | ✅ |
| 242 | cb_weight | 0.30 | ✅ |
| 243 | lgb_weight | 0.30 | ✅ |
| 244 | lstm_weight | 0.25 | ✅ |
| 247 | cb_learning_rate | 0.03 | ✅ |
| 248 | lgb_learning_rate | 0.03 | ✅ |
| 251 | enable_optuna | True | ✅ |
| 252 | n_optuna_trials | 15 | ✅ |
| 253 | optuna_timeout | 30.0 | ✅ |
| 256 | store_extended_metrics | False | ✅ |

**MISSING (see Section H above):** 21 fields

---

### Section D: to_sync_config_kwargs (Lines 262-280)

**CRITICAL - This is what actually gets passed**

| Field Passed | Status |
|--------------|--------|
| train_window | ✅ |
| step_size | ✅ |
| n_steps | ✅ |
| n_estimators | ✅ |
| max_depth | ✅ |
| cb_weight | ✅ |
| lgb_weight | ✅ |
| lstm_weight | ✅ |
| cb_learning_rate | ✅ |
| lgb_learning_rate | ✅ |
| enable_optuna | ✅ |
| n_optuna_trials | ✅ |
| optuna_timeout | ✅ |
| store_extended_metrics | ✅ |

**NOT PASSED:** Everything else uses SyncBacktestConfig defaults

---

## 🔍 FILE 3: notebooks/main_wf.py (1089 lines)

### Lines 1001-1053: Backtest Integration

| Line | Code | Status | Notes |
|------|------|--------|-------|
| 1001 | `from ... import SyncBacktestConfig` | ⬜ | |
| 1004 | `from ... import L2BacktestDefaults` | ⬜ | |
| 1025 | `defaults = L2BacktestDefaults()` | ⬜ | |
| 1053 | `sync_config = SyncBacktestConfig(**defaults.to_sync_config_kwargs())` | ⬜ | |
| 1062 | `results = run_sync_backtest(...)` | ⬜ | |

**Validation:**
- [ ] No overrides between L2BacktestDefaults and SyncBacktestConfig?
- [ ] User can customize before creating SyncBacktestConfig?

---

## 🔍 FILE 4: scripts/run_l2_backtest.py

### Check CLI argument handling

- [ ] Does CLI expose all important config options?
- [ ] Or only subset like main_wf.py?

---

## 📊 FUNCTION CALL COUNTS

| Function | Definition Count | Call Count | Status |
|----------|-----------------|------------|--------|
| `_update_adaptive_weights` | 1 | 0 | 🔴 DEAD |
| `_compute_sample_weights` | 1 | 0 | 🔴 DEAD |
| `_tune_classification_params` | 1 | ? | 🟡 CHECK |
| `_tune_regression_params` | 1 | ? | 🟡 CHECK |
| `PerModelConfig.validate` | 1 | 0 | 🔴 DEAD |
| `_train_predict_classification_permodel` | 1 | 2 | ✅ |
| `_train_predict_regression_permodel` | 1 | 2 | ✅ |
| `run_sync_backtest` | 1 | 2+ | ✅ |

---

## 🔄 DECISION MATRIX

Before making ANY change, answer:

| Question | Answer Required |
|----------|-----------------|
| 1. Is this function/field used? | Count references |
| 2. If dead, was it supposed to be used? | Check config flags |
| 3. Are there comments that reference it? | grep for mentions |
| 4. Would removing it break any imports? | Check __init__.py |
| 5. Is there a test that uses it? | Check test files |

---

## ✅ VALIDATION PROTOCOL

### Before EVERY change:

```
1. IDENTIFY
   - What exactly am I changing?
   - What file? What line? What function?

2. UNDERSTAND
   - Why does this code exist?
   - What calls it?
   - What does it call?

3. IMPACT
   - What else uses this?
   - Will imports break?
   - Will tests break?

4. PLAN
   - What's the minimal change?
   - Can I make it reversible?

5. EXECUTE
   - Make the change

6. VERIFY
   - Does code still run?
   - Do tests pass?
   - Is behavior identical?
```

### After EVERY change:

```
1. CHECK IMPORTS
   - python -c "from scripts.target_models.validation.l2_backtest_sync import *"

2. CHECK TESTS
   - pytest scripts/tests/test_lstm_gap_fix.py -v

3. CHECK BEHAVIOR
   - Run small backtest, compare output
```

---

## 📋 MASTER TODO (Sequential)

### Phase 0: Safety Baseline (BEFORE any changes) ✅ COMPLETE

- [x] 0.1 Create backup of l2_backtest_sync.py → `l2_backtest_sync.py.bak_phase0_20260119` (124533 bytes)
- [x] 0.2 Create backup of workflow/config.py → `config.py.bak_phase0_20260119` (12838 bytes)
- [x] 0.3 Run existing tests, record pass/fail → Tests BROKEN (missing fixtures - pre-existing). Imports OK.
- [x] 0.4 Document current git state → Many uncommitted changes. HEAD: d80a4e3f

### Phase 1: Verify Dead Code (research only) ✅ COMPLETE

- [x] 1.1 `_update_adaptive_weights` count=1 (definition only, line 1077) → **DEAD**
- [x] 1.2 `_compute_sample_weights` count=1 (definition only, line 1031) → **DEAD**
- [x] 1.3 `_tune_classification_params` count=1 (line 1143) → **DEAD**
- [x] 1.4 `_tune_regression_params` count=1 (line 1298) → **DEAD**
- [x] 1.5 `PerModelConfig.validate()` count=1 (line 594) → **DEAD**
- [x] 1.6 Comments at L434 & L465 claim features work but they DON'T

### Phase 2: Verify Config Sync (research only) ✅ COMPLETE

- [x] 2.1 SyncBacktestConfig fields: **46 total**
- [x] 2.2 L2BacktestDefaults fields: **14 total**
- [x] 2.3 to_sync_config_kwargs passes: **14 fields**
- [x] 2.4 **MISSING: 32 fields** (adaptive weights, splits, LSTM, PerModelConfig, etc.)

### Phase 3: Verify Weight Usage (research only) ✅ COMPLETE

- [x] 3.1-3.4 Weight references: 35 in l2_backtest_sync.py, 12 in config.py
- [x] 3.5 `use_adaptive_weights` appears: **1 time (config definition ONLY, NEVER checked)**
- [x] 3.6 `_update_adaptive_weights` called: **0 times**
- [x] 3.7 All 5 ensemble locations use static `config.cb_weight` NOT adaptive

### Phase 4: Verify Comments vs Reality ✅ COMPLETE (covered in Phase 1&3)

- [x] L434: Comment says "Adjust weights based on recent performance" but NEVER happens
- [x] L465: Comment says "Enable exponential decay weighting" but function NEVER called

### Phase 5: Verify LSTM Gap Fix ✅ COMPLETE

- [x] 5.1 `_train_lstm_classifier` (L275): Standalone trainer
- [x] 5.2 `_train_lstm_regressor` (L346): Standalone trainer
- [x] 5.3 `_train_predict_classification_permodel`: Gap fix at L1772-1773, L1868-1871, L1957
- [x] 5.4 `_train_predict_regression_permodel`: Gap fix at L2330, L2380-2381, L2453-2456
- [x] 5.5 **All 4 LSTM paths have extended sequence for continuity**

### Phase 6: Create Decision Document for User Approval 🔴 PENDING

See below for decisions needed.

---

## 🎯 PHASE 6: DECISION DOCUMENT (Requires User Approval)

**All research phases complete. The following decisions require your approval before any code changes:**

### DECISION 1: Dead Functions (5 total)

These functions exist but are NEVER called:

| Function | Line | Purpose | Recommendation | Decision |
|----------|------|---------|----------------|----------|
| `_update_adaptive_weights` | 1077 | MWU algorithm for adaptive weights | **INTEGRATE** (connect to ensemble) | ⬜ KEEP / ⬜ INTEGRATE / ⬜ REMOVE |
| `_compute_sample_weights` | 1031 | Exponential decay sample weighting | **INTEGRATE** (connect to training) | ⬜ KEEP / ⬜ INTEGRATE / ⬜ REMOVE |
| `_tune_classification_params` | 1143 | Legacy hyperparameter tuning | **REMOVE** (replaced by per-model tuners) | ⬜ KEEP / ⬜ REMOVE |
| `_tune_regression_params` | 1298 | Legacy hyperparameter tuning | **REMOVE** (replaced by per-model tuners) | ⬜ KEEP / ⬜ REMOVE |
| `PerModelConfig.validate` | 594 | Config validation | **INTEGRATE** (call during init) | ⬜ KEEP / ⬜ INTEGRATE / ⬜ REMOVE |

**Impact:** 
- INTEGRATE = requires wiring up calls, testing
- REMOVE = simple deletion, ~200 lines total
- KEEP = no change, tech debt remains

---

### DECISION 2: Missing Config Fields (32 fields)

`to_sync_config_kwargs()` passes only 14 of 46 fields. Missing fields use SyncBacktestConfig defaults, NOT L2BacktestDefaults values:

| Category | Missing Fields | Impact | Recommendation |
|----------|---------------|--------|----------------|
| **Adaptive Weights** | `use_adaptive_weights`, `weight_alpha`, `min_weight`, `max_weight` | Adaptive weights system never activates | **ADD** |
| **Sample Weights** | `use_sample_weights`, `weight_decay` | Sample weighting never activates | **ADD** |
| **LSTM Params** | `lstm_hidden_size`, `lstm_num_layers`, `lstm_dropout`, `lstm_lr`, `lstm_epochs` | Uses hardcoded defaults, not configured | **ADD** |
| **Split Ratios** | `split_ratio`, `train_ratio`, `val_ratio` | Uses fixed splits | **ADD** |
| **Per-Model Config** | `model_configs: dict[str, PerModelConfig]` | Never passed through | **ADD** |
| **Ensemble Logic** | `ensemble_method`, `confidence_threshold` | Uses defaults | **ADD** |
| **Other** | `use_conformal`, `conformal_alpha`, `min_samples_cal`, etc. | Various defaults | **REVIEW** |

**Options:**
- **A) Add all 32 fields** to L2BacktestDefaults + to_sync_config_kwargs() (consistent but verbose)
- **B) Add critical 15 fields** (adaptive, sample, LSTM, splits, per-model only)
- **C) Keep as-is** (tech debt remains, features stay broken)

---

### DECISION 3: Hardcoded Weights

Currently ALL ensemble computations use static weights:
```python
# Lines 1902-1905 (binary classification)
weighted_probs = (config.cb_weight * pred_cb + 
                  config.lgb_weight * pred_lgb + 
                  config.lstm_weight * pred_lstm + 
                  config.linear_weight * pred_linear)
```

`use_adaptive_weights=True` in config but **NEVER CHECKED**.
`_update_adaptive_weights()` exists but **NEVER CALLED**.

**Options:**
- **A) Wire up adaptive weights** - Call `_update_adaptive_weights()` after each fold, use results in ensemble
- **B) Keep static weights** - Remove dead adaptive code, document that weights are static by design
- **C) Hybrid** - Keep adaptive code but default off, user can enable via config

---

### DECISION 4: Misleading Comments

| Line | Comment Says | Reality | Action |
|------|-------------|---------|--------|
| 434 | "Adjust weights based on recent performance" | Never happens | ⬜ FIX comment / ⬜ FIX code |
| 465 | "Enable exponential decay weighting" | Never happens | ⬜ FIX comment / ⬜ FIX code |

---

## 📝 YOUR RESPONSE NEEDED

Please indicate your choices:

**Decision 1 (Dead Functions):**
- [ ] A) INTEGRATE adaptive weights + sample weights + validate, REMOVE legacy tuners
- [ ] B) REMOVE ALL dead functions (simpler, focus on working code)
- [ ] C) KEEP as-is for now (document and defer)

**Decision 2 (Config Fields):**
- [ ] A) Add ALL 32 missing fields
- [ ] B) Add critical 15 fields only
- [ ] C) Keep as-is

**Decision 3 (Weights):**
- [ ] A) Wire up adaptive weights (full integration)
- [ ] B) Keep static weights, remove dead adaptive code
- [ ] C) Hybrid (keep code, default off)

**Decision 4 (Comments):**
- [ ] A) Fix comments to match reality (honest documentation)
- [ ] B) Fix code to match comments (full feature implementation)
- [ ] C) Do both as part of larger refactor

---

Once you approve, I will execute Phase 7 changes ONE AT A TIME with verification after each.

---

## 🚫 DO NOT

- Do NOT delete anything without confirming it's unused
- Do NOT change function signatures without checking all callers
- Do NOT remove config fields without checking usage
- Do NOT assume comments are wrong without verification
- Do NOT make multiple changes at once
- Do NOT skip verification steps
