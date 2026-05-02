# Part 4 Feature Analysis — Autonomous Review

> **Navigation:** [README](README.md) | [Part 0: Convention](Part_0_Convention.md) | [Part 1: Groups](Part_1_Groups.md) | [Part 2: Raw](Part_2_Raw.md) | [Part 3: Approved](Part_3_Approved.md) | [Part 3 (2)](Part_3_Approved2.md) | [Part 4: Suggestions](Part_4_Suggestions.md) | **Part 4: Analysis** | [Part 5: Disapproved](Part_5_Disapproved.md)

---

**Date:** 2025-12-20
**Reviewer:** Astra
**Status:** ✅ COMPLETE — All decisions made, documentation updated

---

## Summary Table

| # | Feature | Decision | Key Reason |
|---|---------|----------|------------|
| 1 | M_P_S_W_oiWeightedReturn | ✅ Approved | Unique composite — interaction not captured by separate features |
| 2 | F_TM_fundingCyclePosition | ✅ Approved | Domain-specific, academically supported, categorical |
| 3 | B_TM_dayOfWeek | ✅ Approved | Standard temporal feature, no overlap |
| 4 | D_N_markCloseDeviation | ✅ Approved | Perpetual-specific liquidation signal |
| 5 | D_N_V_markAtrRatio | ✅ Approved (modified) | Ratio version: `markAtr/atr` — scale-invariant |
| 6 | M_P_markLogReturn | ❌ Rejected | 0.9996 correlation with logReturn — near-duplicate |
| 6b | M_P_D_markReturnDiff | ✅ Created | Difference captures the unique 5.7% divergence signal |
| 7 | D_N_V_markCloseRange | ✅ Approved | Unique liquidation vs speculation signal |
| 8 | N_V_atrPercentile | ✅ Approved | Bounded regime indicator, no duplicate |
| 9 | M_N_V_rangeExpansion | ✅ Approved | Volatility momentum, unique signal |
| 10 | V_volOfVol | ✅ Approved | Second-order volatility, regime stability |
| 11 | D_N_closeVsMarkVol | ✅ Approved | Rare signal may be valuable — monitor in validation |
| 12 | D_N_premiumRange | ✅ Approved | Fixed formula, well-bounded |

**Final Counts:** 
- 11 Approved (including 1 modified + 1 new alternative)
- 1 Rejected (markLogReturn → moved to Part_5)

---

## Decisions Made (2025-12-20)

### Feature 5 (markAtr) → **APPROVED as Ratio**
- Raw absolute markAtr rejected (scale-dependent)
- Ratio version `markAtrRatio = markAtr/atr` approved
- Scale-invariant, captures mark vs trade volatility relationship

### Feature 6 (markLogReturn) → **REJECTED + ALTERNATIVE CREATED**
- Option C chosen: Only keep the difference feature
- Raw markLogReturn rejected (0.9996 correlation with logReturn)
- Created `markReturnDiff = markLogReturn - logReturn`
- Difference captures the unique divergence signal (5.7% of bars)

### Feature 11 (closeVsMarkVol) → **APPROVED**
- Small values don't mean no signal — they mean signal is rare
- Tail events matter for risk management
- Monitor predictive power in validation phase

---

## Detailed Analysis

### 1. M_P_S_W_oiWeightedReturn_pct_N ✅

**Formula:** `logReturn × (oiChange / openInterest)`

**Uniqueness:** Composite signal — we have logReturn and oiPctChange separately, but this captures their INTERACTION which ML would need to learn on its own.

**Data:** Range -5.6% to +1.5%, mean near 0.

**Recommendation:** APPROVE — unique interaction term.

---

### 2. F_TM_fundingCyclePosition_bin ✅

**Formula:** `hour_of_day mod 8` → [0, 8, 16]

**Uniqueness:** No temporal features in Part 3. Domain-specific to perpetuals.

**Academic:** Ruan & Streltsov (2022) - funding cycle patterns.

**Recommendation:** APPROVE — categorical, academically supported.

---

### 3. B_TM_dayOfWeek_bin ✅

**Formula:** One-hot or cyclical encoding (1-7)

**Uniqueness:** No day-of-week feature exists.

**Recommendation:** APPROVE — standard temporal feature for weekend effects.

---

### 4. D_N_markCloseDeviation_pct_N ✅

**Formula:** `(markClose - close) / close`

**Uniqueness:** Different from markIndexSpread (which is mark vs index). This is mark vs trade price.

**Data:** Range -0.45% to +1.03%.

**Recommendation:** APPROVE — perpetual-specific liquidation signal.

---

### 5. D_N_V_markAtrRatio_{n}_rat_N ✅ (Modified)

**Original:** V_markAtr_{n}_abs_NN — ATR from mark price OHLC

**Problem:** Scale-dependent (_NN). Correlation 0.998 with trade ATR.

**Solution:** Create ratio instead: `markAtrRatio = markAtr / atr`
- Range: 0.67-1.09
- Correlation with markCloseRange: 0.71 (different signal)
- Scale-invariant

**Decision:** APPROVED as ratio — raw absolute rejected, ratio version in Part_3.

---

### 6. M_P_markLogReturn_pct_N ❌ → M_P_D_markReturnDiff_pct_N ✅

**Original:** `ln(markClose_t / markClose_{t-1})`

**Problem:** 0.9996 correlation with logReturn. Only 5.7% of bars have |diff| > 0.1%.

**Options Considered:**
- A: Reject (near-duplicate)
- B: Keep both + create difference feature
- C: Only keep difference feature `markReturnDiff`

**Decision:** Option C — Reject raw feature, create difference:
- `markReturnDiff = markLogReturn - logReturn`
- Captures the unique divergence signal (5.7% of bars)
- Raw markLogReturn moved to Part_5_Disapproved

---

### 7. D_N_V_markCloseRange_rat_N ✅

**Formula:** `(markHigh - markLow) / (high - low)`

**Uniqueness:** Single-bar ratio, correlation with markAtrRatio only 0.71.

**Data:** Range 0.39-1.20, mean 0.98.

**Recommendation:** APPROVE — liquidation vs speculation pressure.

---

### 8. N_V_atrPercentile_{n}_rnk_N ✅

**Formula:** `percentile_rank(ATR_t, ATR_{t-n:t})`

**Uniqueness:** Different from raw ATR — this tells you WHERE in the distribution (bounded 0-100).

**Data:** Range 4.8-100, mean 49.1.

**Recommendation:** APPROVE — bounded regime indicator.

---

### 9. M_N_V_rangeExpansion_{n}_rat_N ✅

**Formula:** `(high - low) / SMA(high - low, n)`

**Uniqueness:** Ratio-based volatility momentum. Different from percentile (rank-based).

**Data:** Range 0.20-3.52, mean 0.99.

**Recommendation:** APPROVE — volatility momentum signal.

---

### 10. V_volOfVol_{n}_pct_N ✅

**Formula:** `std(V_returnStd_{m})` over n periods

**Uniqueness:** Second-order feature — volatility OF volatility.

**Dependency:** Uses V_returnStd which IS in Part 3 ✅

**Data:** Range 0.037%-2.55%, mean 0.44%.

**Recommendation:** APPROVE — regime stability signal.

---

### 11. D_N_closeVsMarkVol_{n}_pct_N ✅

**Formula:** `std(close - markClose, n) / close`

**Concern:** Very small values — mean 0.019%, range 0.00%-0.37%.

**Analysis:** Close and markClose track very tightly. Is this signal or noise?

**Decision:** APPROVED — Small values don't mean no signal, they mean signal is rare. Tail events matter for risk. Monitor predictive power in validation.

---

### 12. D_N_premiumRange_rat_N ✅

**Formula:** `(premiumHigh - premiumLow) / atrPct(n)`

**Note:** Formula was fixed (original had division-by-zero).

**Data:** Range 0.00-0.32, mean 0.018.

**Recommendation:** APPROVE — arbitrage condition instability.

---

## Completion Status

**All actions completed (2025-12-20):**
1. ✅ 11 features added to Part_3_Approved.md
2. ✅ 1 feature (markLogReturn) moved to Part_5_Disapproved.md
3. ✅ 1 new feature (markReturnDiff) created as alternative
4. ✅ All counts and cross-references updated

This analysis document is now complete and serves as historical record of the review process.
