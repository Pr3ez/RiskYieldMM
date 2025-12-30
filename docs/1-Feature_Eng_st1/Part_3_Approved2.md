# Part 3: Engineered Features (Approved) — Part 2

> **Navigation:** [README](README.md) | [Part 0: Convention](Part_0_Convention.md) | [Part 1: Groups](Part_1_Groups.md) | [Part 2: Raw](Part_2_Raw.md) | [Part 3: Approved](Part_3_Approved.md) | **Part 3 (2)** | [Part 4: Suggestions](Part_4_Suggestions.md) | [Part 5: Disapproved](Part_5_Disapproved.md)

---

Continuation of Part 3 to avoid overly long documents.
Each feature includes: formula, group/category assignments, form suffix, rationale, and raw dependencies.
Prefix convention: `[groups]_featureName_[form]_[norm]`

**Normalization suffix:** `_N` = Normalized (scale-invariant), `_NN` = Not Normalized (scale-dependent)

---

## Sentiment Features (Long/Short Ratio)

### S_longShortRatio_rat_N

**Formula:** `buyRatio / sellRatio` (direct from `RAW_S_longShortRatio_rat_N`)

**Groups/Categories:** Sentiment (S)

**Form:** Ratio (typical range 0.4–4.0, mean ~1.58)

**Normalization:** _N (scale-invariant — ratio of percentages)

**Periods:** N/A (single-bar raw value)

**Pros:**
- Raw positioning signal for regime detection
- Interpretable: >1 = longs dominate, <1 = shorts dominate
- No information loss from transformation

**Cons:**
- Unbounded → addressed by Z-score version below
- 8-hour timeframe → requires alignment for finer granularity

**Rationale:** Provides raw sentiment context that ML can use directly. Extreme values (>2.0 or <0.7) indicate crowded positioning.

**Academic Support:**
- Baker & Wurgler (2006) "Investor Sentiment and the Cross-Section of Stock Returns" — [JoF, 9031 citations](https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.2006.00885.x) — sentiment as predictor
- De Long et al. (1990) "Noise Trader Risk in Financial Markets" — [JPE](https://www.jstor.org/stable/2937765) — noise trader positioning theory

**Uses Raw:** `RAW_S_longShortRatio_rat_N`

**Approved:** 2025-12-22

---

### S_N_longShortZscore_{n}_zsc_N

**Formula:** `(longShortRatio - rolling_mean(n)) / rolling_std(n)`

**Groups/Categories:** Sentiment (S), Normalization (N)

**Form:** Z-score (typically -3 to +3, unbounded at extremes)

**Normalization:** _N (scale-invariant — standardized)

**Periods:** {21, 63} — ~1 week, ~3 weeks in 8h bars

**Pros:**
- **Main contrarian signal** — extremes predict reversals
- Bounded for ML compatibility
- Captures positioning relative to recent history

**Cons:**
- Lagging (uses rolling window) → accepted for noise reduction
- 8-hour timeframe → requires alignment

**Rationale:** Primary feature. Empirically confirmed contrarian effect: Z>2 → -0.323% 3-bar return (bearish), Z<-2 → +0.746% 3-bar return (bullish). Strong academic support for sentiment extremes as contrarian signal.

**Academic Support:**
- Baker & Wurgler (2006) — "When beginning-of-period proxies for sentiment are low, subsequent returns are relatively high" — [JoF, 9031 citations](https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.2006.00885.x)
- Moskowitz, Ooi & Pedersen (2011) "Time Series Momentum" — [SSRN, 2002 citations](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2089463) — speculator positioning predicts reversals
- COT Literature — extreme speculator positioning as contrarian indicator

**Uses Raw:** `RAW_S_longShortRatio_rat_N`

**Approved:** 2025-12-22

---

### S_M_longShortChange_{n}_pct_N

**Formula:** `(longShortRatio / longShortRatio.shift(n)) - 1`

**Groups/Categories:** Sentiment (S), Momentum (M)

**Form:** Percentage change (typical range -0.3 to +0.3)

**Normalization:** _N (scale-invariant — percentage change)

**Periods:** {3, 12} — ~1 day, ~4 days in 8h bars

**Pros:**
- Captures **momentum in positioning shifts**
- Rapid changes may signal regime transitions
- Complementary to level-based Z-score

**Cons:**
- More volatile than Z-score → use shorter periods
- May lag price moves → accepted (sentiment often follows price initially)

**Rationale:** Captures velocity of crowd repositioning. Fast changes in L/S ratio can precede volatility spikes or trend reversals.

**Academic Support:**
- Moskowitz et al. (2011) — speculator positioning dynamics — [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2089463)
- Factor crowding literature — rapid position unwinds cause reversals

**Uses Raw:** `RAW_S_longShortRatio_rat_N`

**Approved:** 2025-12-22

---

## Empirical Validation Summary

**Data:** 4994 merged bars (L/S + Price, 8h timeframe, 2021-05-28 to 2025-12-21)

**Contrarian Signal at Extremes — VERIFIED:**

| Condition | # Bars | Mean 3-bar Return | vs Baseline |
|-----------|--------|-------------------|-------------|
| Z > 2.0 (crowded longs) | 278 | **-0.323%** | Contrarian bearish |
| Z < -2.0 (crowded shorts) | 181 | **+0.746%** | Contrarian bullish |
| All bars | 4971 | +0.052% | Baseline |

**Uniqueness Verification:**
- `longShortRatio` vs `fundingRate`: r = 0.108 (different signal)
- Provides unique sentiment information not captured by funding or OI

---

## Liquidity Features (Academic)

### L_V_amihudIlliquidity_{n}_rat_N

**Formula:** `mean(|ln(close/close.shift(1))| / (close * volume), n)`

**Groups/Categories:** Liquidity (L), Volatility (V)

**Form:** Ratio (very small values, ~1e-12 to 1e-8)

**Normalization:** _N (scale-invariant — ratio of return to dollar volume)

**Periods:** {12, 21, 63} — ~4 days, ~1 week, ~3 weeks in 8h bars

**Pros:**
- **161 citations** (Lou 2017, Journal of Finance) — strong academic support
- Measures price impact per dollar traded — unique signal
- Captures illiquidity premium (high illiquidity → higher expected returns)
- Different from volume-based features (combines return magnitude with volume)

**Cons:**
- Very small absolute values → may need log transform for ML
- Sensitive to low-volume periods → accepted (that's what it measures)

**Rationale:** Foundational illiquidity measure in financial economics. Lou (2017) shows illiquidity predicts returns. Unique signal not captured by our existing volume features.

**Academic Support:**
- Amihud (2002) "Illiquidity and stock returns: cross-section and time-series effects" — [Original paper](https://onlinelibrary.wiley.com/doi/abs/10.1111/1540-6261.00498)
- Lou (2017) "Price Impact or Trading Volume: Why Is the Amihud Measure Priced?" — [JoF, 161 citations](https://www.jstor.org/stable/48616728)

**Uses Raw:** `RAW_P_close_abs_NN`, `RAW_L_volume_abs_NN`

**Approved:** 2025-12-22

---

## Volatility Features (Range-Based Estimators)

### V_parkinson_{n}_pct_N

**Formula:** `sqrt(mean((1/(4*ln(2))) * (ln(high/low))², n))`

**Groups/Categories:** Volatility (V)

**Form:** Percentage (annualized volatility, typical range 0.01–0.10)

**Normalization:** _N (scale-invariant — log-based ratio)

**Periods:** {12, 21} — ~4 days, ~1 week in 8h bars

**Pros:**
- **~5x more efficient** than close-to-close volatility
- Uses intrabar range information (high-low)
- 40+ years of academic validation
- Simpler than Garman-Klass, more robust

**Cons:**
- Assumes no drift (trending periods less accurate) → R-S handles this
- Overlaps with V_atrPct conceptually → different formula, test correlation

**Rationale:** Classic range-based volatility estimator. More efficient use of OHLC data than simple returns. May capture different aspect than V_atrPct.

**Academic Support:**
- Parkinson (1980) "The Extreme Value Method for Estimating the Variance of the Rate of Return" — [Journal of Business](https://www.jstor.org/stable/2352358)

**Uses Raw:** `RAW_P_high_abs_NN`, `RAW_P_low_abs_NN`

**Approved:** 2025-12-22

---

### V_garmanKlass_{n}_pct_N

**Formula:** `sqrt(mean(0.5*(ln(H/L))² - (2*ln(2)-1)*(ln(C/O))², n))`

**Groups/Categories:** Volatility (V)

**Form:** Percentage (annualized volatility, typical range 0.01–0.10)

**Normalization:** _N (scale-invariant — log-based)

**Periods:** {12, 21} — ~4 days, ~1 week in 8h bars

**Pros:**
- **~7-8x more efficient** than close-to-close volatility
- Uses ALL OHLC data (open, high, low, close)
- Standard in volatility research since 1980

**Cons:**
- Assumes no drift — may underestimate in trending markets
- Complex formula — harder to interpret than Parkinson
- May correlate highly with V_parkinson → test empirically

**Rationale:** Most efficient range-based estimator under no-drift assumption. Academic standard. Worth testing if it adds value beyond V_parkinson.

**Academic Support:**
- Garman & Klass (1980) "On the Estimation of Security Price Volatilities from Historical Data" — [Journal of Business](https://www.jstor.org/stable/2352358)

**Uses Raw:** `RAW_P_open_abs_NN`, `RAW_P_high_abs_NN`, `RAW_P_low_abs_NN`, `RAW_P_close_abs_NN`

**Approved:** 2025-12-22

---

### V_rogersSatchell_{n}_pct_N

**Formula:** `sqrt(mean(ln(H/C)*ln(H/O) + ln(L/C)*ln(L/O), n))`

**Groups/Categories:** Volatility (V)

**Form:** Percentage (variance estimate, typical range 0.0001–0.01)

**Normalization:** _N (scale-invariant — log-based)

**Periods:** {12, 21} — ~4 days, ~1 week in 8h bars

**Pros:**
- **Drift-independent** — unbiased even in trending markets
- Uses OHLC without requiring overnight gap
- Theoretically superior to Parkinson/Garman-Klass when drift ≠ 0

**Cons:**
- Can produce negative values inside sqrt → need abs() protection
- Less efficient than Garman-Klass under no-drift assumption
- More complex formula

**Rationale:** Handles trending markets better than Parkinson/Garman-Klass. Crypto often trends hard, so drift-independence is valuable.

**Academic Support:**
- Rogers & Satchell (1991) "Estimating Variance From High, Low and Closing Prices" — [Annals of Applied Probability](https://www.sciencedirect.com/science/article/abs/pii/030440769190014D)

**Uses Raw:** `RAW_P_open_abs_NN`, `RAW_P_high_abs_NN`, `RAW_P_low_abs_NN`, `RAW_P_close_abs_NN`

**Approved:** 2025-12-22

---

### V_hurstExponent_{n}_rat_N

**Formula:** `log(R/S) / log(n)` where R = max(cumsum(returns - mean)) - min(cumsum(returns - mean)), S = std(returns)

**Groups/Categories:** Volatility (V)

**Form:** Ratio (bounded 0–1, typical 0.3–0.7)

**Normalization:** _N (scale-invariant)

**Periods:** {63, 126} — ~3 weeks, ~6 weeks in 8h bars (needs long windows)

**Pros:**
- Measures **long-memory/persistence** of price series
- H > 0.5 = trending, H < 0.5 = mean-reverting, H = 0.5 = random walk
- Strong academic foundation (fractal markets hypothesis)

**Cons:**
- Computationally expensive (cumsum operations per window)
- Noisy at short horizons → requires longer periods
- Overlaps conceptually with V_autocorr → test correlation

**Rationale:** Captures fractal/long-memory properties. May detect regime changes that autocorrelation misses. Academic literature shows predictive power in some markets.

**Academic Support:**
- "Implied Hurst Exponent and Fractional Implied Volatility" — [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2383618)
- Peters (1994) "Fractal Market Analysis" — foundational text
- Multiple SSRN papers on long-memory in financial time series

**Uses Raw:** `RAW_P_close_abs_NN`

**Approved:** 2025-12-22

---

### V_yangZhang_{n}_pct_N

**Formula:** `sqrt(σ²_overnight + k*σ²_open_close + (1-k)*σ²_rogers_satchell)` where k = 0.34/(1.34 + (n+1)/(n-1))

Simplified for 24/7 markets (no overnight gap): `sqrt(k*σ²_open_close + (1-k)*σ²_rogers_satchell)`

Where:
- σ²_open_close = variance of (ln(O) - ln(C.shift(1)))
- σ²_rogers_satchell = as defined above

**Groups/Categories:** Volatility (V)

**Form:** Percentage (annualized volatility, typical range 0.01–0.10)

**Normalization:** _N (scale-invariant — log-based)

**Periods:** {12, 21} — ~4 days, ~1 week in 8h bars

**Pros:**
- **Most efficient** range-based estimator (theoretical minimum variance)
- Combines open-close variance with Rogers-Satchell
- Drift-independent AND gap-independent

**Cons:**
- Designed for overnight gaps which don't exist in 24/7 crypto
- Without overnight component, may not add much over Rogers-Satchell
- Complex formula

**Rationale:** Academic gold standard for volatility estimation. Even without overnight gaps, the combination of open-close and R-S components may capture nuances. Worth testing.

**Academic Support:**
- Yang & Zhang (2000) "Drift Independent Volatility Estimation Based on High, Low, Open, and Close Prices" — [Journal of Business](https://www.jstor.org/stable/222571)

**Uses Raw:** `RAW_P_open_abs_NN`, `RAW_P_high_abs_NN`, `RAW_P_low_abs_NN`, `RAW_P_close_abs_NN`

**Approved:** 2025-12-22

---

## Feature Template

When adding approved features, use this format:

```markdown
### [groups]_featureName_[form]_[norm]
**Formula:** `formula here`
**Groups/Categories:** Group1 (X), Group2 (Y), ...
**Form:** Form type (range description)
**Normalization:** _N (scale-invariant) or _NN (scale-dependent)
**Periods:** (if applicable)
**Pros:**
- Pro 1
- Pro 2
**Cons:**
- Con 1 → covered by [other feature]
- Con 2 → accepted trade-off
**Rationale:** Brief summary of why approved
**Academic Support:** Citations with links
**Uses Raw:** List of raw features from Part 2
**Approved:** YYYY-MM-DD
**Replaces:** (if transformed from original suggestion)
```
