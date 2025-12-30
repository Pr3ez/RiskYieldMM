# Part 5: Disapproved Features

> **Navigation:** [README](README.md) | [Part 0: Convention](Part_0_Convention.md) | [Part 1: Groups](Part_1_Groups.md) | [Part 2: Raw](Part_2_Raw.md) | [Part 3: Approved](Part_3_Approved.md) | [Part 3 (2)](Part_3_Approved2.md) | [Part 4: Suggestions](Part_4_Suggestions.md) | **Part 5: Disapproved**

---

Features that were considered but not approved.
Each entry includes: original proposal, reasoning for rejection, and date.
This preserves our thinking for future reference — we may revisit decisions as context changes.

**Normalization suffix:** `_N` = Normalized (scale-invariant), `_NN` = Not Normalized (scale-dependent)

---

## Redundant Features

### L_M_S_oiChange_dif_NN
**Original Proposal:**
- Formula: `openInterest_t - openInterest_{t-1}`
- Groups/Categories: Liquidity (L), Momentum (M), Sentiment (S)
- Form: Difference (BTC units)
- Original Rationale: Rising OI = new money entering; falling OI = positions closing; change rate (momentum) + positioning (sentiment)
- Academic Support: Wang et al. (2020) - OI significant in derivatives ML
- Uses Raw: `RAW_L_S_openInterest_abs_NN`

**Normalization:** _NN (scale-dependent)
**Pros (what we'd lose):**
- Absolute OI change signal — different view than percentage
- Academic support (Wang et al.)
- Simple, interpretable
**Cons (why rejected):**
- Scale-dependent — 10,000 BTC change means different things at 100k vs 500k total OI
- Not comparable across different market conditions
**Rationale for Rejection:** Scale-dependence is critical flaw; normalized version preserves the signal
**Rejected:** 2025-12-20
**Replaced By:** [L_M_N_S_oiPctChange_pct_N](Part_3_Approved.md#l_m_n_s_oipctchange_pct_n)
**Could Revisit If:** Need absolute OI change for specific use case (but can derive from oiPctChange × OI)

### M_N_williamsR_{n}_bnd_N
**Original Proposal:**
- Formula: `%R = (high_n - close) / (high_n - low_n) × -100`
- Groups/Categories: Momentum (M), Normalized (N)
- Form: Bounded (-100 to 0)
- Original Rationale: Inverse of stochastic (measures distance from high); bounded -100 to 0; <-80 = oversold, >-20 = overbought
- Suggested periods: 6, 12
- Uses Raw: `RAW_P_high_abs_NN`, `RAW_P_low_abs_NN`, `RAW_P_close_abs_NN`

**Normalization:** _N (scale-invariant)
**Pros (what we'd lose):**
- None — mathematically identical to StochasticK
**Cons (why rejected):**
- `WilliamsR = -(100 - StochK) = StochK - 100`
- Correlation with StochasticK = 1.000 (perfect)
- Just a linear transformation — no unique information
**Rationale for Rejection:** Mathematically identical to StochasticK. Keeping both would be pure redundancy.
**Rejected:** 2025-12-20
**Replaced By:** [M_N_stochasticK_{n}_bnd_N](Part_4_Suggestions.md#m_n_stochastick_n_bnd_n)
**Could Revisit If:** Never — this is a mathematical identity, not a design choice.

### N_V_rangePct_pct_N
**Original Proposal:**
- Formula: `(high - low) / close`
- Groups/Categories: Normalized (N), Volatility (V)
- Form: Percentage (unbounded, typically 0-0.2)
- Original Rationale: Intraperiod volatility as percentage; normalized across price levels; simple volatility proxy
- Uses Raw: `RAW_P_high_abs_NN`, `RAW_P_low_abs_NN`, `RAW_P_close_abs_NN`

**Normalization:** _N (scale-invariant)
**Pros (what we'd lose):**
- None in 8h continuous data — identical to trueRangePct
**Cons (why rejected):**
- In 8h continuous BTCUSDT data: correlation with trueRangePct = 1.000
- No gaps between bars means TR always equals (H-L)
- trueRangePct handles potential gaps in other timeframes
**Rationale for Rejection:** Identical to trueRangePct in continuous 8h data. Both are redundant — use V_atrPct (smoothed version) instead.
**Rejected:** 2025-12-20
**Replaced By:** [V_atrPct_{n}_pct_N](Part_3_Approved.md#v_atrpct_n_pct_n) — smoothed version with EMA
**Could Revisit If:** Never for 8h — but if using data with gaps (e.g., traditional markets), they would differ.

### N_V_trueRangePct_pct_N
**Original Proposal:**
- Formula: `TR / close` where TR = max(H-L, |H-prev_C|, |L-prev_C|)
- Groups/Categories: Normalized (N), Volatility (V)
- Form: Percentage (unbounded)
- Original Rationale: True range as percentage of price; accounts for gaps; normalized ATR input
- Uses Raw: `RAW_P_high_abs_NN`, `RAW_P_low_abs_NN`, `RAW_P_close_abs_NN`

**Normalization:** _N (scale-invariant)
**Pros (what we'd lose):**
- Single-bar volatility (before EMA smoothing)
- Handles gaps in theory
**Cons (why rejected):**
- Correlation with rangePct = 1.000 in 8h continuous data (only 1 bar differs out of 5,438)
- No actual gaps in 8h BTCUSDT data — TR always equals H-L
- Already captured by V_atrPct (EMA-smoothed version)
**Rationale for Rejection:** Identical to rangePct in continuous 8h data. Single-bar unsmoothed volatility is noisy; use V_atrPct (smoothed) instead.
**Rejected:** 2025-12-20
**Replaced By:** [V_atrPct_{n}_pct_N](Part_3_Approved.md#v_atrpct_n_pct_n) — smoothed version with EMA
**Could Revisit If:** Using data with actual gaps between bars.

### M_momAcceleration_{n}_dif_NN
**Original Proposal:**
- Formula: `ROC_t(n) - ROC_{t-n}(n)` or `MOM(MOM(n), n)`
- Groups/Categories: Momentum (M)
- Form: Difference (second derivative)
- Rationale: Second derivative of price; momentum gaining/losing strength; early reversal signal
- Suggested periods: 3, 6
- Uses Raw: `RAW_P_close_abs_NN`

**Normalization:** _NN (incorrectly labeled — this is actually _N since ROC is already normalized)
**Pros (what we'd lose):**
- None — identical formula to M_N_rocAccel
**Cons (why rejected):**
- Exact same formula: `ROC_t(n) - ROC_{t-n}(n)`
- The _NN suffix was incorrect — ROC is already a percentage, diff of percentages is scale-invariant
- Duplicate reference in documentation, not a distinct feature
**Rationale for Rejection:** Identical computation to already approved M_N_rocAccel_{n}_dif_N. Different name, same formula.
**Rejected:** 2025-12-20
**Replaced By:** [M_N_rocAccel_{n}_dif_N](Part_3_Approved.md#m_n_rocaccel_n_dif_n)
**Could Revisit If:** Never — this is the same computation under a different name.

### L_T_volumeSma_{n}_abs_NN
**Original Proposal:**
- Formula: `SMA(volume, n)`
- Groups/Categories: Liquidity (L), Trend (T)
- Form: Absolute (BTC units)
- Rationale: Baseline volume level; identifies volume trends; reference for volume spikes
- Suggested periods: 6, 12, 21
- Uses Raw: `RAW_L_volume_abs_NN`

**Normalization:** _NN (scale-dependent)
**Pros (what we'd lose):**
- Absolute volume reference level
**Cons (why rejected):**
- Scale-dependent — absolute BTC volume not comparable across market conditions
- The normalized version (volumeRatio = volume/SMA) captures the same concept in scale-invariant form
**Rationale for Rejection:** Scale-dependent; normalized version approved instead.
**Rejected:** 2025-12-20
**Replaced By:** [L_N_volumeRatio_{n}_rat_N](Part_3_Approved.md#l_n_volumeratio_n_rat_n)
**Could Revisit If:** Need absolute volume levels for specific use case (can derive from volumeRatio × SMA).

### L_T_oiSma_{n}_abs_NN
**Original Proposal:**
- Formula: `SMA(openInterest, n)`
- Groups/Categories: Liquidity (L), Trend (T)
- Form: Absolute (BTC units)
- Rationale: Smoothed OI level; OI trend identification; reference for positioning changes
- Suggested periods: 6, 12, 21
- Uses Raw: `RAW_L_S_openInterest_abs_NN`

**Normalization:** _NN (scale-dependent)
**Pros (what we'd lose):**
- Absolute OI reference level
**Cons (why rejected):**
- Scale-dependent — absolute OI not comparable across market conditions
- Normalized versions capture the same concept in scale-invariant form
**Rationale for Rejection:** Scale-dependent; normalized versions approved instead.
**Rejected:** 2025-12-20
**Replaced By:** 
- [L_N_S_oiRatio_{n}_rat_N](Part_3_Approved.md#l_n_s_oiratio_n_rat_n) — position vs average
- [L_M_N_S_oiRoc_{n}_pct_N](Part_3_Approved.md#l_m_n_s_oiroc_n_pct_n) — rate of change
**Could Revisit If:** Need absolute OI levels for specific use case (can derive from oiRatio × SMA).

---

### M_mom_{n}_dif_NN
**Original Proposal:**
- Formula: `MOM(n) = close_t - close_{t-n}`
- Groups/Categories: Momentum (M)
- Form: Difference (price units)
- Original Rationale: Leading indicator for trend direction; can peak/trough before price; best for ensemble models per Demir et al.
- Academic Support: Demir et al. (2020)
- Suggested periods: 3, 6, 12
- Uses Raw: `RAW_P_close_abs_NN`

**Normalization:** _NN (scale-dependent)
**Pros (what we'd lose):**
- Absolute momentum signal — different view than percentage
- Academic support for ensemble models (Demir et al.)
- Simple, interpretable
**Cons (why rejected):**
- Scale-dependent — $3000 move means different things at $20k vs $60k BTC
- Not comparable across time periods with different price levels
**Rationale for Rejection:** Scale-dependence is critical flaw; transformed to normalized version that preserves signal
**Rejected:** 2025-12-20
**Replaced By:** [M_P_V_momAtr_{n}_rat_N](Part_3_Approved.md#m_p_v_momatr_n_rat_n)
**Could Revisit If:** Need absolute dollar momentum for position sizing calculations

### V_rollingStd_{n}_abs_NN
**Original Proposal:**
- Formula: `std(close_{t-n+1:t})`
- Groups/Categories: Volatility (V)
- Form: Absolute (price units)
- Original Rationale: Captures volatility clustering; high volatility follows high volatility; core risk regime indicator
- Academic Support: Poon & Granger (2003)
- Suggested periods: 3, 6, 12
- Uses Raw: `RAW_P_close_abs_NN`

**Normalization:** _NN (scale-dependent)
**Pros (what we'd lose):**
- Captures volatility clustering
- Simple computation
- Academic support (Poon & Granger)
**Cons (why rejected):**
- Scale-dependent — price std in dollars not comparable across price levels
- Finance literature standard is return volatility, not price volatility
**Rationale for Rejection:** Scale-dependence is critical flaw; return-based volatility is the finance standard
**Rejected:** 2025-12-20
**Replaced By:** [V_returnStd_{n}_pct_N](Part_3_Approved.md#v_returnstd_n_pct_n)
**Could Revisit If:** Need absolute price dispersion for specific use case

### V_atr_{n}_abs_NN
**Original Proposal:**
- Formula: `TR = max(high - low, |high - close_{t-1}|, |low - close_{t-1}|); ATR(n) = EMA(TR, n)`
- Groups/Categories: Volatility (V)
- Form: Absolute (price units)
- Original Rationale: More accurate than high-low range; accounts for gaps; widely used in position sizing
- Academic Support: Wilder (1978)
- Suggested periods: 3, 6, 12
- Uses Raw: `RAW_P_high_abs_NN`, `RAW_P_low_abs_NN`, `RAW_P_close_abs_NN`

**Normalization:** _NN (scale-dependent)
**Pros (what we'd lose):**
- Captures intrabar volatility (high-low range)
- Accounts for gaps between periods
- Industry standard (Wilder 1978)
**Cons (why rejected):**
- Scale-dependent — $1000 ATR means different things at $20k vs $60k BTC
- ATR formula preserved in normalized version
**Rationale for Rejection:** Scale-dependence makes it unusable for ML across different price regimes; normalized version preserves all information
**Rejected:** 2025-12-20
**Replaced By:** [V_atrPct_{n}_pct_N](Part_3_Approved.md#v_atrpct_n_pct_n)
**Could Revisit If:** Need absolute dollar volatility for position sizing calculations (but can derive from atrPct × close)

### ~~N_V_bollingerBandwidth_{n}_pct_N~~ → MOVED TO PART 3
**Status:** ✅ **Reconsidered and APPROVED** (2025-12-23)
**See:** [N_V_bollingerBandwidth_{n}_pct_N](Part_3_Approved.md#n_v_bollingerbandwidth_n_pct_n)
**Reason for Reconsideration:** 
- 27% unique variance vs returnStd/atrPct (correlation ~0.73, not redundant)
- Useful for regime/context detection (squeeze precedes breakouts)
- Poor ML prediction performance doesn't invalidate non-prediction uses
- Periods changed: 6, 12 → 21, 42 (regime detection needs longer windows)

**Original Rejection Record (preserved for history):**
- Formula: `Bandwidth = (BBAND+ - BBAND-) / SMA(n)` where BBAND± = SMA ± 2×std
- **Worst-performing TI in Demir et al. (2020)** — improved only 1 of 10 models tested
- Rejected: 2025-12-20

### P_T_sma_{n}_abs_NN
**Original Proposal:**
- Formula: `SMA(n) = mean(close_{t-n+1:t})`
- Groups/Categories: Price (P), Trend (T)
- Form: Absolute (price units)
- Original Rationale: Smoothed price level, filters noise; identifies support/resistance; price crossing SMA signals trend changes
- Academic Support: Murphy (1999), Neftci (1991), Demir et al. (2020) — SMA improved 7/10 ML models
- Suggested periods: 3, 6, 12, 21 (1d, 2d, 4d, 1wk in 8h periods)
- Uses Raw: `RAW_P_close_abs_NN`

**Normalization:** _NN (scale-dependent)
**Pros (what we'd lose):**
- Academic support — Demir et al. (2020) showed SMA improved 7/10 ML models
- Classic trend indicator with strong theoretical foundation (Murphy, Neftci)
- Direct price level smoothing for support/resistance identification
**Cons (why rejected):**
- Scale-dependent — $30k SMA means different things at $20k vs $60k BTC price levels
- Not comparable across time periods with different price regimes
- Information preserved in normalized derivatives: priceSmaDeviation uses SMA internally
**Rationale for Rejection:** Scale-dependence is critical flaw for ML across different price regimes; the SMA signal is preserved through normalized features (priceSmaDeviation, PPO) that maintain comparability
**Rejected:** 2025-12-20
**Replaced By:** [N_P_T_priceSmaDeviation_{n}_pct_N](Part_3_Approved.md#n_p_t_pricesmadeviation_n_pct_n) — normalized price deviation from SMA; [M_T_ppo_{s}_{l}_pct_N](Part_3_Approved.md#m_t_ppo_s_l_pct_n) — uses EMAs (related)
**Could Revisit If:** Need absolute price level for specific use case (but can derive from priceSmaDeviation × close + close)

### P_T_ema_{n}_abs_NN
**Original Proposal:**
- Formula: `EMA(n) = close_t × α + EMA_{t-1} × (1-α)` where `α = 2/(n+1)`
- Groups/Categories: Price (P), Trend (T)
- Form: Absolute (price units)
- Original Rationale: More weight on recent prices than SMA; better for volatile markets; faster response to price changes
- Academic Support: Demir et al. (2020) — EMA improved 8/10 ML models
- Suggested periods: 3, 6, 12
- Uses Raw: `RAW_P_close_abs_NN`

**Normalization:** _NN (scale-dependent)
**Pros (what we'd lose):**
- Strong academic support — Demir et al. (2020) showed EMA improved 8/10 ML models (better than SMA)
- Faster response to recent price changes than SMA
- More weight on recent data — better for volatile crypto markets
**Cons (why rejected):**
- Scale-dependent — $30k EMA means different things at $20k vs $60k BTC price levels
- Not comparable across time periods with different price regimes
- Information preserved in normalized derivatives: priceEmaDeviation and PPO use EMA internally
**Rationale for Rejection:** Scale-dependence is critical flaw for ML across different price regimes; the EMA signal is preserved through normalized features (priceEmaDeviation, PPO) that maintain comparability
**Rejected:** 2025-12-20
**Replaced By:** [N_P_T_priceEmaDeviation_{n}_pct_N](Part_3_Approved.md#n_p_t_priceemadeviation_n_pct_n) — normalized price deviation from EMA; [M_T_ppo_{s}_{l}_pct_N](Part_3_Approved.md#m_t_ppo_s_l_pct_n) — uses EMAs
**Could Revisit If:** Need absolute price level for specific use case

### M_P_markLogReturn_pct_N
**Original Proposal:**
- Formula: `ln(markClose_t / markClose_{t-1})`
- Groups/Categories: Momentum (M), Price (P)
- Form: Percentage (log return)
- Original Rationale: Log return based on mark price (fair value price); captures momentum from the oracle/fair value perspective rather than trade price
- Uses Raw: `RAW_P_markClose_abs_NN`

**Normalization:** _N (scale-invariant)
**Pros (what we'd lose):**
- Mark price perspective — fair value returns vs trade price returns
- Scale-invariant (log return)
**Cons (why rejected):**
- **0.9996 correlation with logReturn** — near-duplicate
- Mark and trade prices move together 94.3% of the time (|diff| < 0.1%)
- Only 5.7% of bars show meaningful divergence
- The unique information is in the DIVERGENCE, not the level
**Rationale for Rejection:** Near-perfect correlation with existing logReturn makes this redundant. The unique signal (when mark differs from trade) is captured by the difference feature markReturnDiff.
**Rejected:** 2025-12-20
**Replaced By:** [M_P_D_markReturnDiff_pct_N](Part_3_Approved.md#m_p_d_markreturndiff_pct_n) — captures the divergence signal directly
**Could Revisit If:** Never for same-symbol analysis. Possibly useful if comparing returns across different instruments where mark/trade divergence patterns differ.

---

## MACD Family (Scale-Dependent)

### M_T_macdLine_dif_NN
**Original Proposal:**
- Formula: `MACD_line = EMA(12) - EMA(26)`
- Groups/Categories: Momentum (M), Trend (T)
- Form: Difference (price units)
- Original Rationale: Combines trend (EMA difference) with momentum interpretation; positive = short-term trend above long-term
- Academic Support: Appel (2005), Demir et al. (2020)
- Suggested periods: (12, 26)
- Uses Raw: `RAW_P_close_abs_NN`

**Normalization:** _NN (scale-dependent)
**Pros (what we'd lose):**
- Classic MACD indicator — widely recognized, Appel (1979)
- Component support — EMA improved 8/10 ML models (Demir et al.)
- Absolute dollar momentum signal
**Cons (why rejected):**
- Scale-dependent — $500 MACD means different things at $20k vs $60k BTC
- **Mathematically identical to PPO** — PPO = MACD_Line / EMA(long) × 100
- No unique information — PPO captures exact same signal, normalized
**Rationale for Rejection:** PPO is the normalized version of MACD Line; they are mathematically equivalent with different scaling. No unique signal lost.
**Rejected:** 2025-12-20
**Replaced By:** [M_T_ppo_{s}_{l}_pct_N](Part_3_Approved.md#m_t_ppo_s_l_pct_n) — normalized MACD (PPO)
**Could Revisit If:** Need absolute dollar EMA difference for position sizing or if different normalization approach needed

### T_macdSignal_abs_NN
**Original Proposal:**
- Formula: `Signal = EMA(MACD_line, 9)`
- Groups/Categories: Trend (T)
- Form: Absolute (same units as MACD line)
- Original Rationale: Smoothed version of MACD line; crossovers generate trading signals
- Academic Support: Appel (2005)
- Suggested periods: 9-period EMA of MACD
- Uses Raw: `RAW_P_close_abs_NN` (derived from MACD)

**Normalization:** _NN (scale-dependent)
**Pros (what we'd lose):**
- Crossover signal generation — MACD/Signal crossovers are classic trading triggers
- Smoother trend indication than raw MACD
**Cons (why rejected):**
- Scale-dependent — inherits MACD Line's scale issues
- Dependent on rejected feature — requires MACD Line which we rejected
- Could create normalized version (PPO Signal) but adds complexity
**Rationale for Rejection:** Depends on MACD Line which is replaced by PPO; could derive PPO Signal if needed but adds parameters without proven benefit over PPO alone
**Rejected:** 2025-12-20
**Replaced By:** Not directly replaced; PPO zero-line crossover provides similar signal
**Could Revisit If:** Evidence shows PPO Signal (EMA of PPO) adds value beyond PPO alone

### M_macdHistogram_dif_NN
**Original Proposal:**
- Formula: `Histogram = MACD_line - Signal`
- Groups/Categories: Momentum (M)
- Form: Difference (price units)
- Original Rationale: Pure momentum signal; shows acceleration/deceleration of trend; divergences can signal reversals
- Academic Support: Appel (2005)
- Uses Raw: `RAW_P_close_abs_NN` (derived from MACD)

**Normalization:** _NN (scale-dependent)
**Pros (what we'd lose):**
- Momentum acceleration signal — rate of change of MACD
- Divergence detection — histogram divergences may precede reversals
**Cons (why rejected):**
- Scale-dependent — inherits MACD Line's scale issues
- Dependent on two rejected features — requires both MACD Line and Signal
- Could create normalized version (PPO Histogram) but adds significant complexity
**Rationale for Rejection:** Double dependency on rejected features; momentum acceleration could be captured by ROC of PPO if needed, which is simpler
**Rejected:** 2025-12-20
**Replaced By:** Not directly replaced; ROC of PPO could capture similar acceleration signal if needed
**Could Revisit If:** Evidence shows PPO Histogram adds unique value; or need momentum acceleration signal

---

## Cross-References

- **Active suggestions:** [Part 4: Suggestions](Part_4_Suggestions.md)
- **Approved features:** [Part 3: Approved](Part_3_Approved.md)
- **Naming convention:** [Part 0: Convention](Part_0_Convention.md)
- **Groups/Categories:** [Part 1: Groups](Part_1_Groups.md)

---

## Why We Keep This

Per our [Design Philosophy](Part_0_Convention.md#design-philosophy):

- **Document everything** — Rejected ideas have value for future reference
- **Preserve reasoning** — Understanding WHY we rejected helps avoid revisiting without new information
- **Enable revisiting** — Context changes; a rejected feature may become valuable later

---

## Rejection Template

When moving features here from Part 4, use this format:

```markdown
### [groups]_featureName_[form]_[norm]
**Original Proposal:**
- Formula: `formula`
- Groups/Categories: ...
- Form: ...
- Original Rationale: ...
- Academic Support: ...
- Suggested periods: ...
- Uses Raw: ...

**Normalization:** _N or _NN
**Pros (what we'd lose):**
- Pro 1
- Pro 2
**Cons (why rejected):**
- Con 1 (critical flaw)
- Con 2
**Rationale for Rejection:** Summary of why cons outweigh pros
**Rejected:** YYYY-MM-DD
**Replaced By:** [link to replacement] (if transformed)
**Could Revisit If:** (conditions that would change the decision)
```

---

## Rejection Categories

Features may be rejected for various reasons:

| Category | Description | Example |
|----------|-------------|---------|
| **Redundant** | Too similar to existing approved feature | Two momentum indicators with same signal |
| **Low Signal** | Expected predictive value too weak | Calendar feature with no domain relevance |
| **Data Leak** | Uses future information | Feature computed with look-ahead |
| **Unstable** | Too sensitive to parameters or noise | Indicator that flips frequently |
| **Out of Scope** | Doesn't fit current model objectives | Feature for different asset class |
| **Deferred** | Good idea but not for current stage | Complex feature needing more data |
