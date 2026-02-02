# path_label_7 Target Implementation - Master TODO List

**Date:** 2026-01-27  
**Status:** Ready to implement  
**Estimated Time:** 2-3 hours

---

## Summary

7-class path characterization using 15m intrabar analysis:
- STRONG_BULLISH (1.5%)
- BULLISH (16.8%)
- MEAN_REVERT_UP (28.1%)
- SIDEWAYS (9.4%)
- MEAN_REVERT_DOWN (27.2%)
- BEARISH (15.7%)
- STRONG_BEARISH (1.1%)

---

## Phase 1: Core Implementation (targets.py)

### 1.1 Add PathLabel7Class Enum ⬜

**File:** `scripts/workflow/targets.py`  
**Location:** Near other enums (line ~70)

```python
class PathLabel7Class(IntEnum):
    """7-class path characterization labels."""
    STRONG_BULLISH = 0   # Clean rally
    BULLISH = 1          # Normal up
    MEAN_REVERT_UP = 2   # Dip bought
    SIDEWAYS = 3         # Range-bound
    MEAN_REVERT_DOWN = 4 # Rally sold
    BEARISH = 5          # Normal down
    STRONG_BEARISH = 6   # Clean selloff
```

**Validation:**
- [ ] Enum values 0-6 consecutive
- [ ] Import IntEnum present

---

### 1.2 Extend _load_15m_data_for_8h() Helper ⬜

**File:** `scripts/workflow/targets.py`  
**Location:** `_load_15m_data_for_8h()` function (line ~359)

**Currently returns:** `first_extreme`, `time_to_first`, `vol_to_first`

**Need to add:**
- `efficiency_ratio`: Kaufman ER
- `retracement`: % giveback from extreme
- `high_time_idx`: Bar index (0-31) where 8h high was hit
- `low_time_idx`: Bar index (0-31) where 8h low was hit
- `net_return`: (close[-1] - close[0]) / close[0]

**Code to add inside the loop:**
```python
closes_15m = bars['close'].values
highs_15m = bars['high'].values
lows_15m = bars['low'].values

# Kaufman Efficiency Ratio
net_change = abs(closes_15m[-1] - closes_15m[0])
individual_changes = np.abs(np.diff(closes_15m))
total_path = individual_changes.sum()
efficiency_ratio = net_change / total_path if total_path > 0 else 0

# High/Low timing indices
high_time_idx = np.argmax(highs_15m)
low_time_idx = np.argmin(lows_15m)

# Retracement
candle_high = highs_15m.max()
candle_low = lows_15m.min()
candle_range = candle_high - candle_low
candle_close = closes_15m[-1]
if candle_range > 0:
    if high_time_idx < low_time_idx:  # High came first
        retracement = (candle_high - candle_close) / candle_range
    else:  # Low came first
        retracement = (candle_close - candle_low) / candle_range
else:
    retracement = 0

# Net return
net_return = (closes_15m[-1] - closes_15m[0]) / closes_15m[0]
```

**Validation:**
- [ ] Existing targets (first_extreme, vol_to_extreme) still work
- [ ] New fields present in returned DataFrame
- [ ] No NaN explosion

---

### 1.3 Register compute_path_label_7() Function ⬜

**File:** `scripts/workflow/targets.py`  
**Location:** After other @register_target functions

**Classification Logic:**
- Direction: UP if net_return > 0.001, DOWN if < -0.001, else FLAT
- Mean revert UP: direction=UP AND low_time < high_time AND retr > 0.5
- Mean revert DOWN: direction=DOWN AND high_time < low_time AND retr > 0.5
- Strong bullish: direction=UP AND ER > 0.224 AND abs(ret) > 0.0152
- Strong bearish: direction=DOWN AND ER > 0.224 AND abs(ret) > 0.0152
- Bullish: direction=UP AND not (mean_revert OR strong)
- Bearish: direction=DOWN AND not (mean_revert OR strong)
- Sideways: direction=FLAT

**Validation:**
- [ ] Function registered in _TARGET_REGISTRY
- [ ] Returns pd.Series with values 0-6
- [ ] NaN for rows without 15m data
- [ ] Shift by -horizon applied (forward-looking)

---

## Phase 2: Workflow Configuration (config.py)

### 2.1 Add to WORKFLOW_TARGETS ⬜

**File:** `scripts/workflow/config.py`  
**Location:** WORKFLOW_TARGETS list (line ~48)

```python
WORKFLOW_TARGETS = [
    "direction",
    "volatility",
    "volatility_regime",
    "trend_regime",
    "first_extreme",
    "vol_to_extreme",
    "path_label_7",   # <-- ADD THIS
]
```

**Validation:**
- [ ] get_workflow_configs() generates path_label_7_Xbar
- [ ] get_configs_1bar() includes path_label_7_1bar
- [ ] Config summary shows correct count

---

## Phase 3: Analysis Pipeline (Step 2-4 in main_wf.py)

### 3.1 Verify analysis/data.py (Step 2) ⬜

**File:** `scripts/analysis/data.py`

**Note:** May NOT need changes! Step 4 calls compute_target_polars() directly.

**Check:**
- [ ] Verify path_label_7 is computed in Step 4 via compute_target_polars()

---

### 3.2 Verify analysis/parallel_optimize.py (Step 3) ⬜

**File:** `scripts/analysis/parallel_optimize.py`

**Note:** main_wf.py passes WORKFLOW_TARGETS explicitly, so default list may be fine.

**Validation:**
- [ ] Step 3 in main_wf.py optimizes path_label_7
- [ ] Output: features_8h_optimized_path_label_7_Xbar.parquet

---

### 3.3 Verify analysis/run.py (Step 4) ⬜

**File:** `scripts/analysis/run.py`

**Note:** main_wf.py passes WORKFLOW_TARGETS explicitly.

**Validation:**
- [ ] Step 4 creates data/datasets/path_label_7_Xbar.parquet
- [ ] Dataset has y_path_label_7 column
- [ ] Label distribution matches empirical analysis

---

## Phase 4: Backtest Integration (Step 8-10)

### 4.1 Add LABEL_NAMES for path_label_7 ⬜

**File:** `scripts/target_models/validation/backtest/services/backtest.py`  
**Location:** LABEL_NAMES dict (line ~61)

```python
LABEL_NAMES = {
    "direction": {0: "DOWN", 1: "UP", 2: "NEUTRAL"},
    "volatility_regime": {0: "DECREASE", 1: "INCREASE"},
    "trend_regime": {0: "DOWN", 1: "UP"},
    "first_extreme": {0: "LOW", 1: "HIGH"},
    "path_label_7": {   # <-- ADD THIS
        0: "STRONG_BULLISH",
        1: "BULLISH",
        2: "MEAN_REVERT_UP",
        3: "SIDEWAYS",
        4: "MEAN_REVERT_DOWN",
        5: "BEARISH",
        6: "STRONG_BEARISH",
    },
}
```

**Validation:**
- [ ] get_label_name("path_label_7_1bar", 0) returns "STRONG_BULLISH"
- [ ] All 7 labels have human-readable names

---

### 4.2 Verify L1 Precompute (Step 8) Works ⬜

Uses get_workflow_configs() - should work automatically.

**Validation:**
- [ ] data/precomputed/path_label_7_1bar/ directory created
- [ ] L1 iterations computed for path_label_7_1bar
- [ ] metadata.json has correct total_iterations

---

### 4.3 Verify Dataset Assembly (Step 9) Works ⬜

Uses get_workflow_configs() - should work automatically.

**Validation:**
- [ ] data/precomputed/path_label_7_1bar/assembled.parquet created
- [ ] Correct row count

---

### 4.4 Verify Combined Datasets (Step 9b) Works ⬜

Uses get_workflow_configs() - should work automatically.

**Validation:**
- [ ] data/combined_datasets/path_label_7_1bar.parquet created
- [ ] Has raw features + helpers + target

---

### 4.5 Verify L2 Backtest (Step 10) Works ⬜

**Special Consideration:**
- 7 classes with imbalanced distribution
- STRONG_* classes are rare (1.1-1.5%)
- May need class weights or oversampling

**Validation:**
- [ ] Backtest runs without crash
- [ ] Predictions are 0-6 (7 classes)
- [ ] Metrics calculated correctly (accuracy, etc.)
- [ ] Results saved to data/l2_backtest_results/

---

## Phase 5: Documentation & Cleanup

### 5.1 Update main_wf.py Comments ⬜

**File:** `notebooks/main_wf.py`

- [ ] Update Step 2 docstring (add y_path_label_7)
- [ ] Update Pipeline Complete summary

---

### 5.2 Update Research Doc ⬜

**File:** `docs/target-redesign/multi-label-targets-research.md`

- [ ] Mark implementation steps as complete
- [ ] Add actual validation results
- [ ] Document any deviations from plan

---

## Phase 6: Full Validation

### 6.1 Unit Test: Target Computation ⬜

**Expected Distribution:**
- STRONG_BULLISH: ~1.5%
- BULLISH: ~16.8%
- MEAN_REVERT_UP: ~28.1%
- SIDEWAYS: ~9.4%
- MEAN_REVERT_DOWN: ~27.2%
- BEARISH: ~15.7%
- STRONG_BEARISH: ~1.1%

---

### 6.2 Integration Test: Run Steps 2-4 ⬜

- [ ] Step 3 creates features_8h_optimized_path_label_7_1bar.parquet
- [ ] Step 4 creates data/datasets/path_label_7_1bar.parquet
- [ ] Dataset has correct column: y_path_label_7
- [ ] No NaN explosion in target column

---

### 6.3 Integration Test: Run Steps 8-10 ⬜

- [ ] Step 8: L1 precompute runs for path_label_7_1bar
- [ ] Step 9: Assembly creates assembled.parquet
- [ ] Step 9b: Combined dataset created
- [ ] Step 10: L2 backtest runs with 7-class classifier
- [ ] Results show accuracy metric

---

### 6.4 Regression Test: Existing Targets Still Work ⬜

- [ ] direction_1bar
- [ ] volatility_regime_1bar
- [ ] first_extreme_1bar (uses same _load_15m_data_for_8h helper)
- [ ] vol_to_extreme_1bar (uses same helper)

---

## Recommended Implementation Order

1. **Phase 1.1:** Add enum (quick, no risk)
2. **Phase 1.2:** Extend helper (CAREFUL - affects existing targets)
3. **Phase 6.4:** VALIDATE existing targets still work before continuing
4. **Phase 1.3:** Register compute function
5. **Phase 2.1:** Add to WORKFLOW_TARGETS
6. **Phase 4.1:** Add LABEL_NAMES
7. **Phase 6.1:** Unit test
8. **Phase 3.*:** Verify analysis pipeline
9. **Phase 6.2:** Integration test Steps 2-4
10. **Phase 4.2-4.5:** Verify backtest integration
11. **Phase 6.3:** Integration test Steps 8-10
12. **Phase 5.*:** Documentation cleanup

---

## Files Modified Summary

| File | Phase | Changes |
|------|-------|---------|
| `scripts/workflow/targets.py` | 1.1, 1.2, 1.3 | Enum + helper extension + compute function |
| `scripts/workflow/config.py` | 2.1 | Add to WORKFLOW_TARGETS |
| `backtest/services/backtest.py` | 4.1 | Add LABEL_NAMES |
| `notebooks/main_wf.py` | 5.1 | Update comments |
| `docs/target-redesign/*.md` | 5.2 | Update docs |

---

## Risk Assessment

**Low Risk:**
- Adding enum (no existing code uses it)
- Adding LABEL_NAMES (additive change)
- Adding to WORKFLOW_TARGETS (controlled via list)

**Medium Risk:**
- Extending `_load_15m_data_for_8h()` helper - existing targets use this
- **Mitigation:** Validate existing targets immediately after change

**Higher Risk:**
- 7-class classification with imbalanced data may have poor accuracy on rare classes
- **Mitigation:** Can add class weights later if needed
