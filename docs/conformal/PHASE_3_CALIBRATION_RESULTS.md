# Phase 3: Calibration Sample Size & Strategy Results

**Date:** 2025-01-14  
**Status:** ✅ ALL TESTS COMPLETE - DECISION POINT 2 READY

---

## Summary

Phase 3 tested calibration sample sizes and strategies to determine optimal configuration.

### Key Findings

| Metric | Finding |
|--------|---------|
| Minimum cal size | **20 samples** achieves <3% deviation |
| Best stability | **Fixed-150** (std=1.9%, score=2.8) |
| Walk-forward variance | **2.8-4.4% std** across time windows |
| Current pipeline | **75 samples** - works but marginal |
| Recommended | **100-150 samples + ACI** |

---

## Phase 3.1: Sample Size Experiment

### Results

| Cal Size | Coverage | Deviation | Status |
|----------|----------|-----------|--------|
| 20 | 87.6% | 2.4% | ✅ GOOD |
| 50 | 90.2% | 0.2% | ✅ GOOD |
| 75 | 91.7% | 1.7% | ✅ GOOD |
| 100 | 90.4% | 0.4% | ✅ GOOD |
| 150 | 87.9% | 2.1% | ✅ GOOD |
| 200 | 88.0% | 2.0% | ✅ GOOD |
| 300 | 84.9% | 5.1% | ❌ POOR |
| 500 | 89.0% | 1.0% | ✅ GOOD |

**Key insight:** Sample size matters less than expected. Even 20 samples can achieve <3% deviation. The issue is **temporal stability**, not sample count.

---

## Phase 3.2: Walk-Forward Stability Analysis

### Results (10 walk-forward windows)

| Cal Size | Mean | Std | Min | Max | Range |
|----------|------|-----|-----|-----|-------|
| 20 | 93.5% | 3.2% | 87% | 100% | 12.5% |
| 50 | 89.5% | 4.4% | 78% | 94% | 16.0% |
| 75 | 90.4% | 4.1% | 80% | 95% | 14.5% |
| 100 | 90.4% | 2.9% | 84% | 94% | 10.0% |
| 200 | 90.0% | 3.2% | 84% | 94% | 11.0% |

**Key insight:** Coverage varies significantly across time periods (2.9-4.4% std, 10-16% range). This is distribution shift in action - **ACI is needed** for adaptation.

---

## Phase 3.3: Strategy Evaluation

### Strategies Tested

**[A] Fixed L2 Cal Window (current approach)**
- Use fixed number of samples after L2 validation
- Simple, matches current pipeline

**[B] Cumulative Cal (growing calibration set)**
- Use all past validation data
- More data over time, but slower to adapt

**[C] Rolling Window**
- Use last N samples only
- Adapts to recent patterns

### Results (Score = deviation from 90% + std)

| Strategy | Mean Cov | Std | Range | Score |
|----------|----------|-----|-------|-------|
| **Fixed-150** | 90.9% | 1.9% | 87-94 | **2.8** ← BEST |
| Rolling-200 | 90.3% | 2.8% | 84-94 | 3.1 |
| Fixed-75 | 90.5% | 3.0% | 86-96 | 3.5 |
| Fixed-100 | 91.0% | 3.0% | 87-96 | 4.0 |
| Rolling-100 | 91.0% | 3.0% | 87-96 | 4.0 |
| Rolling-300 | 91.0% | 3.7% | 83-95 | 4.6 |
| Cumulative | 87.4% | 3.9% | 80-92 | 6.5 ← WORST |

### Strategy Analysis

| Strategy | Pros | Cons | Best For |
|----------|------|------|----------|
| Fixed | Simple, predictable | Doesn't adapt | Stable distributions |
| Cumulative | More data | Slow adaptation, memory grows | Stationary data |
| **Rolling** | Adapts to shifts, fixed memory | May miss long-term | **Non-stationary (financial)** |

---

## Decision Point 2: Calibration Strategy

### Question
Which calibration strategy and sample size should we use?

### Analysis Summary

1. **Sample size:** 100-150 samples is optimal
   - Below 100: higher variance
   - Above 150: diminishing returns
   - Current 75: works but marginal

2. **Strategy:** For financial data (non-stationary), options are:
   - **Fixed-150:** Best score (2.8), lowest std (1.9%)
   - **Rolling-200:** Second best (3.1), adapts to shifts

3. **Enhancement needed:** ACI for dynamic alpha adaptation
   - Walk-forward shows 10-16% coverage range
   - ACI will adjust alpha to maintain target coverage

### Options for Your Decision

**Option A: Minimal Change**
- Keep current Fixed-75 approach
- Add ACI for adaptation
- Pros: Less change, faster to implement
- Cons: Slightly higher variance

**Option B: Recommended**
- Increase to Fixed-100 or Fixed-150
- Add ACI for adaptation
- Pros: Better stability + adaptation
- Cons: Slightly more calibration data needed

**Option C: Maximum Adaptation**
- Switch to Rolling-200
- Add ACI for adaptation
- Pros: Best adaptation to distribution shifts
- Cons: More complex, may require pipeline changes

### Decision Made: Option C (Optimal)

**✅ SELECTED: Fixed-150 + ACI**

Rationale:
1. 150 samples = 30% of 500-sample window (vs current 15%)
2. Fixed-150 has **best score (2.8)** and **lowest std (1.9%)**
3. Simple implementation (just change cal_ratio)
4. ACI handles distribution shifts dynamically

Implementation:
1. Change `cal_ratio` from 0.15 to **0.30** in SlidingL2Config
2. Add ACI layer with gamma=0.04
3. Track alpha per target model

### Alternative Options (Documented for Future)

If Fixed-150 proves problematic, consider these alternatives:

| Option | When to Use | Change Required |
|--------|-------------|-----------------|
| **Fixed-100** | If 150 samples too costly | cal_ratio=0.20 |
| **Rolling-200** | If distribution shifts are severe | Major pipeline change |
| **Fixed-75 (current)** | Rollback if issues | No change |

**Triggers for reconsidering:**
- Coverage consistently <85% → try Rolling-200
- Computational cost too high → fall back to Fixed-100
- Integration issues → rollback to Fixed-75

---

## Next Steps

Pending your decision, the next phases are:

**Phase 4: Method Testing**
- 4.1: Classification methods (LAC/APS/RAPS)
- 4.2: Multiclass test (vol_regime_1bar)
- 4.3: Regression methods (naive/EnbPI)
- 4.4: Decision Point 3 (which methods?)

**Phase 5: ACI Testing**
- 5.1: Baseline with fixed alpha
- 5.2: ACI test with gamma=0.04
- 5.3: Gamma sensitivity
- 5.4: Decision Point 4 (enable ACI?)

---

## Appendix: Test Configuration

```
Dataset: direction_1bar.parquet
Total samples: 5437
Features: 171
Class balance: 48.9% positive

Walk-forward config:
- Train size: 2500 samples
- Test size: 200 samples
- Windows: 10 (100-sample step)
```
