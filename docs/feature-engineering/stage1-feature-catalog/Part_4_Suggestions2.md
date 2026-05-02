# Part 4 (2): Academic Research Suggestions

> **Navigation:** [README](README.md) | [Part 0: Convention](Part_0_Convention.md) | [Part 1: Groups](Part_1_Groups.md) | [Part 2: Raw](Part_2_Raw.md) | [Part 3: Approved](Part_3_Approved.md) | [Part 3 (2)](Part_3_Approved2.md) | [Part 4: Suggestions](Part_4_Suggestions.md) | **Part 4 (2): Suggestions** | [Part 5: Disapproved](Part_5_Disapproved.md)

---

**Status:** ✅ Decided — 6 approved, 5 future suggestions, 1 covered  
**Date:** 2025-12-22  
**Source:** Academic literature review

---

## Feature 1: L_V_amihudIlliquidity_{n}_rat_N

| Item | Details |
|------|---------|
| **Formula** | `mean(\|ln(close/prev_close)\| / (close * volume), n)` |
| **Periods** | 12, 21, 63 |
| **Groups** | Liquidity (L), Volatility (V) |
| **Form** | Ratio |
| **Normalization** | _N (scale-invariant) |
| **Source** | Amihud (2002) "Illiquidity and stock returns: cross-section and time-series effects" |
| **Link** | https://www.jstor.org/stable/48616728 |
| **Citations** | Lou (2017) — 161 citations, Journal of Finance |
| **Computable** | ✅ Yes |
| **Recommendation** | ✅ RECOMMEND |

---

## Feature 2: V_parkinson_{n}_pct_N

| Item | Details |
|------|---------|
| **Formula** | `sqrt(mean((1/(4*ln(2))) * (ln(high/low))², n))` |
| **Periods** | 12, 21 |
| **Groups** | Volatility (V) |
| **Form** | Percentage |
| **Normalization** | _N (scale-invariant, log-based) |
| **Source** | Parkinson (1980) "The Extreme Value Method for Estimating the Variance of the Rate of Return" |
| **Link** | https://www.jstor.org/stable/2352358 |
| **Citations** | 40+ years of academic use |
| **Computable** | ✅ Yes |
| **Recommendation** | ⚠️ BORDERLINE (overlaps with V_atrPct) |

---

## Feature 3: V_garmanKlass_{n}_pct_N

| Item | Details |
|------|---------|
| **Formula** | `sqrt(mean(0.5*(ln(H/L))² - (2*ln(2)-1)*(ln(C/O))², n))` |
| **Periods** | 12, 21 |
| **Groups** | Volatility (V) |
| **Form** | Percentage |
| **Normalization** | _N (scale-invariant, log-based) |
| **Source** | Garman & Klass (1980) "On the Estimation of Security Price Volatilities from Historical Data" |
| **Link** | https://www.jstor.org/stable/2352358 |
| **Citations** | Standard in volatility research |
| **Computable** | ✅ Yes |
| **Recommendation** | ⚠️ OPTIONAL |

---

## Feature 4: V_rogersSatchell_{n}_pct_N

| Item | Details |
|------|---------|
| **Formula** | `sqrt(mean(ln(H/C)*ln(H/O) + ln(L/C)*ln(L/O), n))` |
| **Periods** | 12, 21 |
| **Groups** | Volatility (V) |
| **Form** | Percentage |
| **Normalization** | _N (scale-invariant, log-based) |
| **Source** | Rogers & Satchell (1991) "Estimating Variance From High, Low and Closing Prices" |
| **Link** | https://www.sciencedirect.com/science/article/abs/pii/030440769190014D |
| **Citations** | Multiple SSRN working papers |
| **Computable** | ✅ Yes |
| **Recommendation** | ⚠️ OPTIONAL (handles drift) |

---

## Feature 5: V_hurstExponent_{n}_rat_N

| Item | Details |
|------|---------|
| **Formula** | `log(R/S) / log(n)` where R = max(cumsum) - min(cumsum), S = std(returns) |
| **Periods** | 63, 126 |
| **Groups** | Volatility (V) |
| **Form** | Ratio (bounded 0-1) |
| **Normalization** | _N (scale-invariant) |
| **Source** | "Implied Hurst Exponent and Fractional Implied Volatility" |
| **Link** | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2383618 |
| **Citations** | Multiple SSRN papers on long-memory |
| **Computable** | ✅ Yes |
| **Recommendation** | ❌ SKIP (V_autocorr covers, expensive) |

---

## Feature 6: L_rollSpread_{n}_pct_N

| Item | Details |
|------|---------|
| **Formula** | `2 * sqrt(-cov)` if `Cov(Δprice_t, Δprice_{t-1}) < 0` else 0 |
| **Periods** | 21, 63 |
| **Groups** | Liquidity (L) |
| **Form** | Percentage |
| **Normalization** | _N (scale-invariant) |
| **Source** | Roll (1984) "A Simple Implicit Measure of the Effective Bid-Ask Spread" |
| **Link** | https://arxiv.org/abs/2208.03568 |
| **Citations** | 20+ arXiv citations |
| **Computable** | ⚠️ Maybe |
| **Recommendation** | ❌ SKIP (8h bars too coarse) |

---

## Feature 7: Order Flow Imbalance

| Item | Details |
|------|---------|
| **Formula** | Signed trade volume aggregation |
| **Periods** | N/A |
| **Groups** | Liquidity (L), Sentiment (S) |
| **Form** | Ratio |
| **Normalization** | N/A |
| **Source** | Kyle (1985) "Continuous Auctions and Insider Trading" |
| **Link** | https://www.jstor.org/stable/1913210 |
| **Citations** | Foundational market microstructure paper |
| **Computable** | ❌ No (requires tick data) |
| **Recommendation** | ❌ N/A |

---

## Feature 8: Kyle Lambda

| Item | Details |
|------|---------|
| **Formula** | Price impact = λ × order flow |
| **Periods** | N/A |
| **Groups** | Liquidity (L) |
| **Form** | Ratio |
| **Normalization** | N/A |
| **Source** | Kyle (1985) "Continuous Auctions and Insider Trading" |
| **Link** | https://www.jstor.org/stable/1913210 |
| **Citations** | Foundational market microstructure paper |
| **Computable** | ❌ No (requires order book) |
| **Recommendation** | ❌ N/A |

---

## Feature 9: Information Coefficient (IC)

| Item | Details |
|------|---------|
| **Formula** | `corr(signal_rank, return_rank)` cross-sectionally |
| **Periods** | N/A |
| **Groups** | N/A |
| **Form** | Ratio (-1 to 1) |
| **Normalization** | N/A |
| **Source** | Grinold & Kahn "Active Portfolio Management" |
| **Link** | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3387744 |
| **Citations** | Standard quant metric |
| **Computable** | ❌ No (single asset, need multi-asset) |
| **Recommendation** | ❌ N/A |

---

## Feature 10: V_yangZhang_{n}_pct_N

| Item | Details |
|------|---------|
| **Formula** | Combines overnight variance + open-close variance + Rogers-Satchell |
| **Periods** | 12, 21 |
| **Groups** | Volatility (V) |
| **Form** | Percentage |
| **Normalization** | _N (scale-invariant) |
| **Source** | Yang & Zhang (2000) "Drift Independent Volatility Estimation" |
| **Link** | https://www.jstor.org/stable/222571 |
| **Citations** | Most efficient range-based estimator |
| **Computable** | ✅ Yes |
| **Recommendation** | ❌ NOT NEEDED (no overnight gaps in 24/7 crypto) |

---

## Feature 11: Realized Higher Moments (Intraday)

| Item | Details |
|------|---------|
| **Formula** | Realized skewness/kurtosis from intraday returns |
| **Periods** | N/A |
| **Groups** | Volatility (V) |
| **Form** | Ratio |
| **Normalization** | N/A |
| **Source** | Amaya et al. (2015) "Does Realized Skewness Predict the Cross-Section of Equity Returns?" |
| **Link** | https://www.sciencedirect.com/science/article/abs/pii/S0304405X15000288 |
| **Citations** | Journal of Financial Economics |
| **Computable** | ❌ No (requires intraday data) |
| **Recommendation** | ❌ DIFFERENT CONCEPT (V_skew/V_kurtosis adequate) |

---

## Feature 12: Factor Momentum / Time Series Momentum

| Item | Details |
|------|---------|
| **Formula** | Cross-asset momentum signals |
| **Periods** | N/A |
| **Groups** | Momentum (M) |
| **Form** | Percentage |
| **Normalization** | N/A |
| **Source** | Moskowitz, Ooi & Pedersen (2011) "Time Series Momentum" |
| **Link** | https://www.sciencedirect.com/science/article/abs/pii/S0304405X11002613 |
| **Citations** | 2000+ citations, Journal of Financial Economics |
| **Computable** | N/A (single asset) |
| **Recommendation** | ❌ ALREADY COVERED (M_P_roc, M_P_V_momAtr) |

---

## Summary Table

| # | Feature | Computable | Status |
|---|---------|------------|--------|
| 1 | L_V_amihudIlliquidity | ✅ Yes | ✅ **APPROVED** → Part_3_Approved2.md |
| 2 | V_parkinson | ✅ Yes | ✅ **APPROVED** → Part_3_Approved2.md |
| 3 | V_garmanKlass | ✅ Yes | ✅ **APPROVED** → Part_3_Approved2.md |
| 4 | V_rogersSatchell | ✅ Yes | ✅ **APPROVED** → Part_3_Approved2.md |
| 5 | V_hurstExponent | ✅ Yes | ✅ **APPROVED** → Part_3_Approved2.md |
| 6 | L_rollSpread | ⚠️ Maybe (1m) | 🔮 FUTURE — requires 1m data |
| 7 | Order Flow Imbalance | ❌ No | 🔮 FUTURE — requires tick data |
| 8 | Kyle Lambda | ❌ No | 🔮 FUTURE — requires order book |
| 9 | Information Coefficient | ❌ No | 🔮 FUTURE — requires multi-asset |
| 10 | V_yangZhang | ✅ Yes | ✅ **APPROVED** → Part_3_Approved2.md |
| 11 | Realized Higher Moments | ❌ No | 🔮 FUTURE — requires intraday data |
| 12 | Factor Momentum | N/A | ❌ COVERED (M_P_roc, M_P_V_momAtr) |

---

## Implementation Status

**Date:** 2025-12-22

**Approved & Implemented:**
- 6 features added to Part_3_Approved2.md
- 6 compute functions added to compute_features.py
- 13 new feature columns (with period variations)
- Validation: 160/166 passing

**Future Suggestions (require different data):**
- L_rollSpread — needs 1m bars
- Order Flow Imbalance — needs tick/trade data
- Kyle Lambda — needs order book snapshots
- Information Coefficient — needs multi-asset universe
- Realized Higher Moments — needs intraday data
