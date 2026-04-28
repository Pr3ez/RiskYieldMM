# HTF Backtest Findings & Notes

This document tracks findings, issues, and improvements discovered during walk-forward backtesting.

---

## Run Log

### Run: 2026-02-05_11-08-50 (Verification Test)

**Purpose:** Verify class_metrics.parquet fix (should have 0 null values)

**Configuration:**
- Steps: 1 (quick test)
- Warmup: 200 batches

**Results:**

| TF | Val Acc | Test Acc | Features | Lookback |
|----|---------|----------|----------|----------|
| 5m | 27.5% | 65.2% | 32 | 147 |
| 15m | 26.5% | 22.7% | 63 | 488 |

**Verification:** ✅ class_metrics.parquet now has 0 null values

**Duration:** ~5 minutes

---

### Run: 2026-02-05_10-12-10 (First Full Run)

**Configuration:**
- Steps: 5
- Warmup: 200 batches
- Refit interval: 50 batches
- Trials: 30 (5m), 25 (15m)
- Timeout: 180s (5m), 150s (15m)

**Results Summary:**

| TF | Step | Val Acc | Test Acc | Features | Lookback |
|----|------|---------|----------|----------|----------|
| 5m | 1 | 26.0% | 65.2% | 37 | 64 |
| 5m | 2 | 43.0% | 48.5% | 69 | 51 |
| 5m | 3 | 41.9% | 3.0% | 49 | 124 |
| 5m | 4 | 34.2% | 63.6% | 32 | 38 |
| 5m | 5 | 23.1% | 22.7% | 52 | 277 |
| 15m | 1 | 26.2% | 13.6% | 36 | 359 |
| 15m | 2 | 23.0% | 4.5% | 34 | 322 |
| 15m | 3 | 40.1% | 27.3% | 24 | 107 |
| 15m | 4 | 26.9% | 40.9% | 80 | 256 |
| 15m | 5 | 26.4% | 18.2% | 27 | 418 |

**Total Duration:** 27 minutes

---

## Known Issues

### 1. 15m Timeframe Poor Performance ⚠️

**Observation:** 15m consistently underperforms 5m despite having cleaner signals.

**Hypothesis:** 15m may need hybrid high/low features from higher timeframe (1h) to capture proper price ranges.

**Root Cause Analysis:**
- 15m has only 32 bars per 8h batch vs 96 for 5m
- Fewer samples = less stable optimization
- Current features may not capture 1h-level support/resistance
- Lookback ranges (100-500) may be too large for available data

**Proposed Fix:**
1. Add 1h hybrid distance features to 15m dataset
2. Reduce lookback range to 50-200
3. Consider using more trials (50+) to compensate for fewer samples

**Status:** TODO - document in 15m optimizer config

### 2. class_metrics.parquet Had Null Values (FIXED)

**Issue:** Per-class accuracy/count were null in saved parquet.

**Root Cause:** 
- Trial stored metrics as `class_0_accuracy`, `class_1_accuracy`, etc.
- Save function looked for `per_class_accuracy` dict with string keys

**Fix Applied:**
- Updated `optimize()` return to extract individual class metrics into dict
- Updated `save_step_results()` to use integer keys

### 3. GPU Usage Verification ✅

**Status:** LightGBM is configured with GPU:
```python
"device": "gpu",
"gpu_platform_id": 0,
"gpu_device_id": 0,
```

**Evidence:** 5 steps × 2 timeframes completed in 27 minutes (reasonable for GPU).

---

## Architecture Decisions

### Study Storage Strategy

**Current:** Each step creates separate study.db file
- Pro: Clean isolation, easy to delete failed runs
- Pro: Can load any step independently
- Con: Cannot compare trials across steps in single view

**Alternative Considered:** Single study.db with run prefix in study names
- Would allow: `htf_run001_5m_step_0001`, `htf_run001_5m_step_0002`
- Not implemented due to complexity

### Run Naming Convention

**Format:** `run_{YYYY-MM-DD}_{HH-MM-SS}`

**Files per run:**
- `run_config.json` - Configuration snapshot
- `run_summary.json` - Final results
- `study_registry.json` - All studies index
- `{tf}/step_{NNNN}/` - Per-step artifacts

---

## TODO List

### High Priority

- [ ] Add 1h hybrid features to 15m dataset
- [ ] Reduce 15m lookback range (100-500 → 50-200)
- [ ] Increase 15m trials (25 → 50) or add early stopping logic
- [ ] Add test set metrics to class_metrics.parquet (currently only val)

### Medium Priority

- [ ] Add confusion matrix computation and storage
- [ ] Implement run resume from interruption
- [ ] Add visualization cell for study analysis

### Low Priority

- [ ] Consider consolidating studies into single DB per run
- [ ] Add Optuna visualization (importance, parallel coordinate plots)

---

## Optimization Insights

### 5m Observations

- **Optimal lookback:** 38-64 batches (3-5k samples)
- **Feature count:** 32-52 works best
- **Class weighting:** `sqrt` often selected
- **Learning rate:** High (0.1-0.15) with strong regularization

### 15m Observations

- **Lookback tendency:** Very high (300-400+ batches) - possibly overfitting
- **Feature count:** Varies widely (24-80) - unstable
- **Possible issue:** Not enough data per class for stable optimization

---

## Code Improvements Made

### 2026-02-05

1. **Fixed class_metrics extraction**
   - Changed from looking for `per_class_accuracy` dict to extracting `class_X_accuracy` keys
   - Updated save function to use integer keys

2. **Added study_name parameter**
   - Each study now has unique name: `htf_{tf}_step_{step:04d}`
   - Enables loading specific studies later

3. **Added StudyConfig and StudyRegistry**
   - Centralized run configuration
   - Track all studies across run
   - Support for future resume functionality

---

## References

- LightGBM GPU setup: https://lightgbm.readthedocs.io/en/latest/GPU-Tutorial.html
- Optuna SQLite: https://optuna.readthedocs.io/en/stable/tutorial/20_recipes/001_rdb.html
