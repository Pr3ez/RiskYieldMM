# Part 4: Suggestions

> **Navigation:** [README](README.md) | [Part 0: Convention](Part_0_Convention.md) | [Part 1: Groups](Part_1_Groups.md) | [Part 2: Raw](Part_2_Raw.md) | [Part 3: Approved](Part_3_Approved.md) | [Part 3 (2)](Part_3_Approved2.md) | **Part 4: Suggestions** | [Part 4 (2)](Part_4_Suggestions2.md) | [Part 5: Disapproved](Part_5_Disapproved.md)

---

**Status:** All suggestions reviewed and decided.

See [Part 4: Analysis](Part_4_Analysis.md) for the detailed review process.

**Summary (2025-12-20 batch):**
- 11 features approved → moved to [Part 3: Approved](Part_3_Approved.md)
- 1 feature rejected → moved to [Part 5: Disapproved](Part_5_Disapproved.md)
- 1 new feature created (markReturnDiff) as alternative to rejected markLogReturn

**Summary (2025-12-21 batch):**
- 4 features approved → moved to [Part 3: Approved](Part_3_Approved.md) (VWAP, premium features)
- 0 features rejected

**Summary (2025-12-21 research batch):**
- 19 features approved → moved to [Part 3: Approved](Part_3_Approved.md) (distribution, risk, regime, volume-price, trend)
- 4 features rejected as duplicates → see Rejected section below

**Summary (2025-12-22 L/S Ratio batch):**
- 3 features approved → moved to [Part 3 (2)](Part_3_Approved2.md) (sentiment/positioning)
- 0 features rejected

---

## Archived Suggestions (Decided 2025-12-20)

The following features have been decided and moved to their final locations.
This section is preserved for historical reference.

### ✅ Approved → Part 3

| Feature | Decision | Notes |
|---------|----------|-------|
| M_P_S_W_oiWeightedReturn_pct_N | Approved | Unique composite signal |
| F_TM_fundingCyclePosition_bin | Approved | Domain-specific categorical |
| B_TM_dayOfWeek_bin | Approved | Standard temporal feature |
| D_N_markCloseDeviation_pct_N | Approved | Perpetual-specific liquidation signal |
| V_markAtr → D_N_V_markAtrRatio | Approved (modified) | Ratio version for scale-invariance |
| D_N_V_markCloseRange_rat_N | Approved | Liquidation vs speculation signal |
| N_V_atrPercentile_{n}_rnk_N | Approved | Bounded regime indicator |
| M_N_V_rangeExpansion_{n}_rat_N | Approved | Volatility momentum signal |
| V_volOfVol_{n}_pct_N | Approved | Second-order volatility |
| D_N_closeVsMarkVol_{n}_pct_N | Approved | Monitor in validation — small values |
| D_N_premiumRange_rat_N | Approved | Formula fixed, well-bounded |

### ❌ Rejected → Part 5

| Feature | Decision | Alternative |
|---------|----------|-------------|
| M_P_markLogReturn_pct_N | Rejected | 0.9996 correlation with logReturn. Created M_P_D_markReturnDiff_pct_N instead to capture divergence. |

### ➕ New Features Created

| Feature | Rationale |
|---------|-----------|
| M_P_D_markReturnDiff_pct_N | `markLogReturn - logReturn` — captures divergence signal directly instead of near-duplicate raw feature |

---

## Archived Suggestions (Decided 2025-12-21)

### ✅ Approved → Part 3

| Feature | Decision | Notes |
|---------|----------|-------|
| N_P_L_vwapDeviation_pct_N | Approved | Unique mean-reversion signal (0.73 corr with logReturn) |
| M_P_L_vwapReturn_pct_N | Approved | Volume-weighted momentum (0.79 corr with logReturn) |
| M_D_F_S_premiumChange_pct_N | Approved | **Extremely unique** (0.017 corr with logReturn!) |
| V_D_F_S_premiumRange_pct_N | Approved | Premium volatility / stress indicator |

---

## ✅ Approved Research Batch (2025-12-21) → Moved to Part 3

*19 features approved after subagent validation. All moved to [Part 3: Approved](Part_3_Approved.md).*

### Batch 1: Distribution, Risk, Regime (12 features)

| # | Feature | Group | Form | Status |
|---|---------|-------|------|--------|
| 1 | V_skew_{n}_rat_N | V | rat | ✅ Approved |
| 2 | V_kurtosis_{n}_rat_N | V | rat | ✅ Approved |
| 3 | V_maxDrawdown_{n}_pct_N | V | pct | ✅ Approved |
| 4 | M_V_sharpe_{n}_rat_N | M, V | rat | ✅ Approved |
| 5 | M_V_sortino_{n}_rat_N | M, V | rat | ✅ Approved |
| 6 | M_V_calmar_{n}_rat_N | M, V | rat | ✅ Approved |
| 7 | V_autocorr_{n}_bnd_N | V | bnd | ✅ Approved |
| 8 | N_P_zScore_{n}_zsc_N | N, P | zsc | ✅ Approved |
| 9 | V_volMomentum_{n}_pct_N | V | pct | ✅ Approved |
| 10 | B_consecutiveUp_bnd_N | B | bnd | ✅ Approved |
| 11 | B_consecutiveDown_bnd_N | B | bnd | ✅ Approved |
| 12 | M_winRate_{n}_bnd_N | M | bnd | ✅ Approved |

### Batch 2: Volume-Price & Trend (7 features)

| # | Feature | Group | Form | Status |
|---|---------|-------|------|--------|
| 13 | L_M_S_obv_{n}_zsc_N | L, M, S | zsc | ✅ Approved |
| 14 | L_M_S_mfi_{n}_bnd_N | L, M, S | bnd | ✅ Approved |
| 15 | L_M_S_cmf_{n}_bnd_N | L, M, S | bnd | ✅ Approved |
| 16 | M_T_V_adx_{n}_bnd_N | M, T, V | bnd | ✅ Approved |
| 17 | M_T_V_diDiff_{n}_bnd_N | M, T, V | bnd | ✅ Approved |
| 18 | N_M_cci_{n}_zsc_N | N, M | zsc | ✅ Approved |
| 19 | L_S_oiVolumeRatio_{n}_rat_N | L, S | rat | ✅ Approved |

---

## Rejected as Duplicates (Validation 2025-12-21)

| Proposed Feature | Existing Feature | Reason |
|-----------------|------------------|--------|
| N_bollinger_{n}_{k}_rnk_N | `N_P_V_pctB_{n}_bnd_N` | **Identical formula** — both compute (close - lower) / (upper - lower) with Bollinger bands |
| V_trueRange_{n}_pct_N | `V_atrPct_{n}_pct_N` | **Identical formula** — both compute ATR(n) / close |
| V_rangePosition_{n}_rnk_N | `M_N_stochasticK_{n}_bnd_N` | **Identical formula** — both compute (close - low_n) / (high_n - low_n) × 100 |
| N_M_williamsR_{n}_bnd_N | `M_N_stochasticK_{n}_bnd_N` | **Linear transform** — %R = %K - 100, perfect correlation r = -1.0 |

---

## Features NOT Proposed (Analysis Showed Redundancy)

| Potential Feature | Correlation | Decision |
|-------------------|-------------|----------|
| turnoverRatio (turnover/avg) | 0.999 with volumeRatio | ❌ Skip — redundant |
| indexReturn | 0.9995 with logReturn | ❌ Skip — redundant |
| indexReturnDiff | 0.932 with markReturnDiff | ❌ Skip — too similar |
| indexCloseRange | 0.898 with markCloseRange | ⚠️ Borderline — not proposed |

---

## Cross-References

**Related Parts:**
- [Part 4: Analysis](Part_4_Analysis.md) — Detailed review process and decisions
- [Part 1: Groups](Part_1_Groups.md) — Full group/category definitions
- [Part 2: Raw](Part_2_Raw.md) — Raw features referenced
- [Part 3: Approved](Part_3_Approved.md) — Where approved features now live
- [Part 5: Disapproved](Part_5_Disapproved.md) — Where rejected features now live

**Naming Convention:** See [Part 0: Convention](Part_0_Convention.md) for full naming rules.

---

## 🆕 New Suggestions (2025-12-22)

### ✅ Long/Short Ratio Features — APPROVED → Moved to Part 3 (2)

**Source Data:** `RAW_S_longShortRatio_rat_N` (buyRatio / sellRatio from Part 2)

**Data Available:** 5002 rows (2021-05-28 to present), 8-hour timeframe

| Feature | Decision | Notes |
|---------|----------|-------|
| S_longShortRatio_rat_N | ✅ Approved | Raw ratio for regime context |
| S_N_longShortZscore_{n}_zsc_N | ✅ Approved | Main contrarian signal at extremes |
| S_M_longShortChange_{n}_pct_N | ✅ Approved | Positioning momentum |

**See:** [Part 3 (2)](Part_3_Approved2.md) for full feature documentation.
