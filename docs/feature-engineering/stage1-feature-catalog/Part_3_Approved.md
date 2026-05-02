# Part 3: Engineered Features (Approved)

> **Navigation:** [README](README.md) | [Part 0: Convention](Part_0_Convention.md) | [Part 1: Groups](Part_1_Groups.md) | [Part 2: Raw](Part_2_Raw.md) | **Part 3: Approved** | [Part 3 (2)](Part_3_Approved2.md) | [Part 4: Suggestions](Part_4_Suggestions.md) | [Part 5: Disapproved](Part_5_Disapproved.md)

---

Features created from raw data after mutual agreement.
Each feature includes: formula, group/category assignments, form suffix, rationale, and raw dependencies.
Prefix convention: `[groups]_featureName_[form]_[norm]`

**Normalization suffix:** `_N` = Normalized (scale-invariant), `_NN` = Not Normalized (scale-dependent)

---

## Momentum & Price Features

### M_P_logReturn_pct_N
**Formula:** `ln(close_t / close_{t-1})`
**Groups/Categories:** Momentum (M), Price (P)
**Form:** Percentage (unbounded)
**Normalization:** _N (scale-invariant)
**Pros:**
- Scale-invariant — works at any price level
- Additive over time — can sum returns across periods
- Approximately normal distribution — good for ML
- Stationary — no unit root issues
- Fundamental building block — used by other features
**Cons:**
- Single period only → covered by M_P_roc_{n}_pct_N for multi-period
- Unbounded → accepted trade-off (rarely extreme)
**Rationale:** Stationary transformation of prices; fundamental for ML on price series
**Academic Support:** 
- Tsay (2005) "Analysis of Financial Time Series" [book](https://books.google.com/books?id=ddL4tTLb_08C)
- Sung et al. (2022) "Cryptocurrency log-return prediction" [paper](https://www.mdpi.com/2075-1680/11/9/448)
**Uses Raw:** `RAW_P_close_abs_NN`
**Approved:** 2025-12-20

### M_P_roc_{n}_pct_N
**Formula:** `(close_t - close_{t-n}) / close_{t-n}`
**Groups/Categories:** Momentum (M), Price (P)
**Form:** Percentage (unbounded)
**Normalization:** _N (scale-invariant)
**Periods:** 3, 6, 12, 21 (1d, 2d, 4d, 1wk) — use logReturn for single-period
**Pros:**
- Scale-invariant — works at any price level
- Multi-period — captures trend strength across horizons
- Simple, interpretable — "how much % change over n periods"
- Strong academic support for ML applications
**Cons:**
- Doesn't account for volatility → covered by M_P_V_momAtr_{n}_rat_N
- Unbounded → accepted trade-off
**Rationale:** Multi-period momentum; captures trend strength across different horizons
**Academic Support:** 
- Demir et al. (2019) "Technical indicators for ML" [paper](https://www.mdpi.com/2076-3417/10/1/255)
- Li & Bastos (2020) "Deep learning & technical analysis review" [paper](https://ieeexplore.ieee.org/abstract/document/9220868/)
**Uses Raw:** `RAW_P_close_abs_NN`
**Approved:** 2025-12-20

### M_P_V_momAtr_{n}_rat_N
**Formula:** `(close_t - close_{t-n}) / ATR(n)`
**Groups/Categories:** Momentum (M), Price (P), Volatility (V)
**Form:** Ratio (volatility units)
**Normalization:** _N (scale-invariant)
**Periods:** 3, 6, 12, 21 (1d, 2d, 4d, 1wk)
**Pros:**
- Scale-invariant — normalized by volatility
- Meaningful units — "how many ATR units did price move"
- Combines momentum + volatility context
- Strong academic support for volatility-adjusted momentum
**Cons:**
- Requires ATR computation → accepted trade-off (ATR is standard)
- Two periods to tune (MOM and ATR) → use same n for simplicity
**Rationale:** Momentum normalized by volatility; combines momentum direction with volatility context
**Academic Support:** 
- Janeiro (2016) "Volatility Adjusted Momentum Strategy" [thesis](https://search.proquest.com/openview/fedd6433b88e905e1b86f521c8696bca/1)
- Baltas & Kosowski (2012) "Improving time-series momentum strategies" [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2019988)
- Wilder (1978) "New Concepts in Technical Trading Systems" [book](https://www.amazon.com/dp/0894590278) — ATR origin
**Uses Raw:** `RAW_P_close_abs_NN`, `RAW_P_high_abs_NN`, `RAW_P_low_abs_NN`
**Approved:** 2025-12-20
**Replaces:** M_mom_{n}_dif_NN (normalized version)

---

## Volatility Features

### V_atrPct_{n}_pct_N
**Formula:** 
```
TR = max(high - low, |high - close_{t-1}|, |low - close_{t-1}|)
ATR(n) = EMA(TR, n)
atrPct = ATR(n) / close_t
```
**Groups/Categories:** Volatility (V)
**Form:** Percentage (unbounded, typically 0.01-0.10)
**Normalization:** _N (scale-invariant)
**Periods:** 3, 6, 12, 21 (1d, 2d, 4d, 1wk)
**Pros:**
- Scale-invariant — ATR normalized by price
- Captures intrabar volatility — uses high/low, not just close
- Accounts for gaps — true range includes gap from previous close
- Industry standard — Wilder (1978), widely used in trading systems
**Cons:**
- EMA weighting choice → accepted trade-off (EMA is standard for ATR)
- Unbounded → accepted trade-off (typically small values)
**Rationale:** Intrabar volatility measure; complements V_returnStd which only sees close-to-close
**Academic Support:** 
- Wilder (1978) "New Concepts in Technical Trading Systems" [book](https://www.amazon.com/dp/0894590278) — ATR origin
- Demir et al. (2020) "Technical indicators for cryptocurrency" [paper](https://www.mdpi.com/2076-3417/10/1/255)
**Uses Raw:** `RAW_P_high_abs_NN`, `RAW_P_low_abs_NN`, `RAW_P_close_abs_NN`
**Approved:** 2025-12-20
**Replaces:** V_atr_{n}_abs_NN (normalized to percentage)

### V_returnStd_{n}_pct_N
**Formula:** `std(ln(close_t / close_{t-1}) for t in [t-n+1, t])`
**Groups/Categories:** Volatility (V)
**Form:** Percentage (unbounded, typically 0-0.1)
**Normalization:** _N (scale-invariant)
**Periods:** 3, 6, 12, 21 (1d, 2d, 4d, 1wk)
**Pros:**
- Scale-invariant — returns are percentages
- Finance standard — this IS how volatility is measured in literature
- Captures volatility clustering — well-documented phenomenon
- Strong academic support — 3074+ citations (Poon & Granger)
**Cons:**
- Misses intrabar movement → covered by V_atrPct_{n}_pct_N
- Unbounded → accepted trade-off (typically small values)
**Rationale:** Standard deviation of log returns; standard approach in financial volatility literature
**Academic Support:** 
- Poon & Granger (2003) "Forecasting volatility in financial markets" [paper](https://www.aeaweb.org/articles?id=10.1257/002205103765762743) — 3074 citations
- Engle (1993) "Statistical models for financial volatility" [paper](https://www.tandfonline.com/doi/pdf/10.2469/faj.v49.n1.72)
**Uses Raw:** `RAW_P_close_abs_NN`
**Approved:** 2025-12-20
**Replaces:** V_rollingStd_{n}_abs_NN (normalized to use returns instead of prices)

### N_V_bollingerBandwidth_{n}_pct_N
**Formula:** 
```
BBAND+ = SMA(n) + 2 × std(close, n)
BBAND- = SMA(n) - 2 × std(close, n)
Bandwidth = (BBAND+ - BBAND-) / SMA(n)
```
**Groups/Categories:** Volatility (V)
**Form:** Percentage (typically 0.01-0.5)
**Normalization:** _N (dividing by SMA makes it scale-invariant)
**Periods:** 21, 42 (regime detection needs longer windows)
**Pros:**
- Captures regime transitions — bandwidth compression precedes breakouts
- 27% unique variance vs returnStd/atrPct (correlation ~0.73)
- Standard technical indicator — widely recognized in trading literature
**Cons:**
- Worst performer in Demir 2020 for ML prediction (1/10 models)
- Redundant with returnStd for pure volatility measurement
**Rationale:** Not for ML prediction — useful as regime/context indicator. Bollinger squeeze (low bandwidth) often precedes significant moves. Periods 21/42 for medium-term regime detection.
**Academic Support:** 
- Bollinger (2002) "Bollinger on Bollinger Bands" — original reference
- Demir et al. (2020) — shows poor predictive power but doesn't invalidate regime indicator use
**Uses Raw:** `RAW_P_close_abs_NN`
**Approved:** 2025-12-23
**Status:** Reconsidered from Part 5 — approved for regime/context use (not prediction)

---

## Normalized Price Position Features

### N_P_V_pctB_{n}_bnd_N
**Formula:** 
```
BBAND+ = SMA(n) + 2 × std(close, n)
BBAND- = SMA(n) - 2 × std(close, n)
%B = (close - BBAND-) / (BBAND+ - BBAND-)
```
**Groups/Categories:** Normalized (N), Price (P), Volatility (V)
**Form:** Bounded (typically 0-1, can exceed)
**Normalization:** _N (scale-invariant)
**Periods:** 3, 6, 12, 21 (1d, 2d, 4d, 1wk)
**Pros:**
- Scale-invariant — position within bands works at any price level
- Bounded output (typically 0-1) — good for ML models
- Overbought/oversold signal — <0 oversold, >1 overbought
- Strong empirical support — 4.42% RMSE reduction in linear models (Demir et al.)
**Cons:**
- Based on std of price levels (not returns) → acceptable for position signal
- Band width affected by trend → mitigated by normalization to band width
**Rationale:** Price position within volatility envelope; provides overbought/oversold signal with empirical ML validation
**Academic Support:** 
- Bollinger (2002) "Bollinger on Bollinger Bands" [book](https://www.amazon.com/dp/0071373683) — indicator definition
- Demir et al. (2020) "Technical indicators for ML" [paper](https://www.mdpi.com/2076-3417/10/1/255) — 4.42% RMSE reduction in linear models
**Uses Raw:** `RAW_P_close_abs_NN`
**Approved:** 2025-12-20

---

## Trend Features

### M_T_ppo_{s}_{l}_pct_N
**Formula:** `PPO = (EMA(short) - EMA(long)) / EMA(long) × 100`
**Groups/Categories:** Momentum (M), Trend (T)
**Form:** Percentage (unbounded, typically -10 to +10)
**Normalization:** _N (scale-invariant)
**Periods:** (8, 21), (12, 26) — 8h bars: 8=2.7d, 21=7d, 12=4d, 26=8.7d
**Pros:**
- Scale-invariant — percentage difference, comparable across price levels
- Established indicator — Gerald Appel (1970s), widely validated
- Strong component support — EMA improved 8/10 ML models (Demir et al.)
- Crossover signals — zero line crossings indicate trend changes
**Cons:**
- Two parameters to tune → use standard (12, 26) or adapt to timeframe
- Lagging indicator → accepted trade-off (all MA-based indicators lag)
**Rationale:** Normalized MACD; provides scale-invariant momentum-trend signal with strong empirical support for EMA components
**Academic Support:**
- Appel (1979) "The Moving Average Convergence Divergence Trading Method" [book](https://www.amazon.com/dp/0934380929) — original MACD/PPO
- Investopedia: "The PPO is identical to MACD, except PPO measures percentage difference"
- Demir et al. (2020) [paper](https://www.mdpi.com/2076-3417/10/1/255) — EMA improved 8/10 ML models
**Uses Raw:** `RAW_P_close_abs_NN`
**Approved:** 2025-12-20
**Note:** PPO = MACD_Line / EMA(long) × 100. If different scaling needed, see rejected MACD features in [Part 5](Part_5_Disapproved.md#m_t_macdline_dif_nn)

### N_P_T_priceSmaDeviation_{n}_pct_N
**Formula:** `deviation = (close - SMA(n)) / SMA(n)`
**Groups/Categories:** Normalized (N), Price (P), Trend (T)
**Form:** Percentage (unbounded)
**Normalization:** _N (scale-invariant)
**Feature Type:** DERIVED — not a standard named indicator
**Periods:** 3, 6, 12, 21 (1d, 2d, 4d, 1wk)
**Pros:**
- Scale-invariant — normalized by SMA level
- Mean-reversion signal — extreme deviations from MA tend to revert
- Component support — SMA improved 7/10 ML models (Demir et al.)
- Intuitive interpretation — "how far has price stretched from trend"
**Cons:**
- Exact formula not academically tested → based on proven components
- Similar concept to DPO but different implementation → our version is real-time, normalized
**Rationale:** Derived feature combining DPO concept (price vs SMA) with percentage normalization; captures mean-reversion opportunities
**Academic Support:**
- Demir et al. (2020) [paper](https://www.mdpi.com/2076-3417/10/1/255) — SMA improved 7/10 ML models
- Conceptual basis: DPO (price relative to MA) + PPO normalization approach
- Note: Exact formula is our derivation, not a standard indicator
**Uses Raw:** `RAW_P_close_abs_NN`
**Approved:** 2025-12-20

### N_P_T_priceEmaDeviation_{n}_pct_N
**Formula:** `deviation = (close - EMA(n)) / EMA(n)` where `EMA(n) = close_t × α + EMA_{t-1} × (1-α)`, `α = 2/(n+1)`
**Groups/Categories:** Normalized (N), Price (P), Trend (T)
**Form:** Percentage (unbounded)
**Normalization:** _N (scale-invariant)
**Feature Type:** DERIVED — not a standard named indicator
**Periods:** 3, 6, 12, 21 (1d, 2d, 4d, 1wk)
**Pros:**
- Scale-invariant — normalized by EMA level
- Mean-reversion signal — extreme deviations from EMA tend to revert
- Strong component support — EMA improved 8/10 ML models (Demir et al.)
- Faster response than SMA version — EMA weights recent prices more heavily
- Complementary to priceSmaDeviation — different MA dynamics capture different views:
  - EMA: deviation from "current" trend (recent-weighted)
  - SMA: deviation from "average" trend (equal-weighted)
**Cons:**
- Exact formula not academically tested → based on proven EMA component (8/10 ML support)
- Unbounded → accepted trade-off (rarely extreme)
**Rationale:** Derived feature using EMA (8/10 ML support) with percentage normalization; captures mean-reversion from recent-weighted trend, complementing SMA version's equal-weighted view
**Academic Support:**
- Demir et al. (2020) [paper](https://www.mdpi.com/2076-3417/10/1/255) — EMA improved 8/10 ML models (better than SMA 7/10)
- Conceptual basis: Same normalization as priceSmaDeviation but with EMA
- Note: Exact formula is our derivation, not a standard indicator
**Uses Raw:** `RAW_P_close_abs_NN`
**Approved:** 2025-12-20

---

## Funding Features

### F_I_fundingCumulative_{n}_pct_N
**Formula:** `sum(fundingRate_{t-n+1:t})`
**Groups/Categories:** Funding (F), Interest (I)
**Form:** Percentage (unbounded, sum of rates)
**Normalization:** _N (scale-invariant)
**Periods:** 3, 7, 21 (1d, ~2d, 1wk)
**Pros:**
- Scale-invariant — funding rates are already percentages
- Captures total economic impact — cumulative cost/benefit of holding position
- Regime accumulation — persistent one-sided funding builds pressure
- Unique to perpetuals — information not available in spot/traditional futures
**Cons:**
- Scales with window size → complemented by fundingMa for comparable values
- Unbounded → accepted trade-off (typically small values)
**Rationale:** Total funding paid/received over n periods; captures cumulative carry cost and positioning pressure unique to perpetual futures
**Academic Support:**
- He, Manela, Ross & von Wachter (2022/2024) "Fundamentals of Perpetual Futures" [arXiv:2212.06888](https://arxiv.org/abs/2212.06888) — Establishes funding rate proportional to perpetual-spot gap; arbitrage on funding yields high Sharpe ratios
**Uses Raw:** `RAW_F_I_S_fundingRate_pct_N`
**Approved:** 2025-12-20

### F_I_T_fundingMa_{n}_pct_N
**Formula:** `mean(fundingRate_{t-n+1:t})`
**Groups/Categories:** Funding (F), Interest (I), Trend (T)
**Form:** Percentage (same range as funding rate, typically -0.1% to +0.3%)
**Normalization:** _N (scale-invariant)
**Periods:** 3, 7, 21 (1d, ~2d, 1wk)
**Pros:**
- Scale-invariant — funding rates are already percentages
- Comparable across periods — mean stays in original range regardless of window
- Trend component — captures funding regime (persistent bullish/bearish sentiment)
- Smoothed signal — filters noise from individual funding readings
**Cons:**
- Mathematically related to cumulative (mean = sum/n) → both kept for different ML use cases
- Lagging → accepted trade-off (all smoothing lags)
**Rationale:** Average funding rate over n periods; captures funding regime and sentiment trend with comparable values across different window sizes
**Academic Support:**
- He, Manela, Ross & von Wachter (2022/2024) "Fundamentals of Perpetual Futures" [arXiv:2212.06888](https://arxiv.org/abs/2212.06888) — Funding reflects perpetual-spot gap; persistent funding indicates market leverage imbalance
**Uses Raw:** `RAW_F_I_S_fundingRate_pct_N`
**Approved:** 2025-12-20
**Note:** Mathematically, `fundingCumulative = fundingMa × n`. Both kept as different scales may benefit different model architectures.

### F_I_M_fundingMaDiff_{s}_{l}_pct_N
**Formula:** `fundingMa(short) - fundingMa(long)` where `fundingMa(n) = mean(fundingRate_{t-n+1:t})`
**Groups/Categories:** Funding (F), Interest (I), Momentum (M)
**Form:** Percentage (unbounded, typically small values)
**Normalization:** _N (scale-invariant)
**Periods:** (3, 7), (3, 21), (7, 21)
**Pros:**
- Scale-invariant — difference of percentages stays in percentage scale
- Captures funding momentum — positive = recent funding rising, negative = recent funding falling
- Regime change detection — crossover signals shift in funding pressure
- New information — unlike cumulative vs mean (same info, different scale), short vs long MA comparison captures rate of change in funding regime
- Strong academic support — MA difference proven momentum signal (Zakamulin & Giner, 39 citations)
**Cons:**
- Two parameters to tune → use aligned pairs from standard periods
- Lagging → accepted trade-off (all MA-based indicators lag)
**Rationale:** Short vs long funding MA difference captures momentum in funding regime; detects acceleration or deceleration of sentiment before absolute levels signal change
**Academic Support:**
- Zakamulin & Giner (2020) "Trend following with momentum versus moving averages" [Quantitative Finance](https://www.tandfonline.com/doi/abs/10.1080/14697688.2020.1716057) — 39 citations; proves MA(short) - MA(long) captures trend momentum and regime changes
- Marshall, Nguyen & Visaltanachoti (2017) "Time series momentum and moving average trading rules" [Quantitative Finance](https://www.tandfonline.com/doi/abs/10.1080/14697688.2016.1205209) — 96 citations; MA crossover signals established momentum indicators
**Uses Raw:** `RAW_F_I_S_fundingRate_pct_N`
**Approved:** 2025-12-20

### F_I_N_S_fundingZscore_{n}_zsc_N
**Formula:** 
```
μ = mean(fundingRate_{t-n+1:t})  # rolling mean over n periods, includes current
σ = std(fundingRate_{t-n+1:t})   # rolling std over n periods, includes current
z = (fundingRate_t - μ) / σ
```
**Groups/Categories:** Funding (F), Interest (I), Normalized (N), Sentiment (S)
**Form:** Z-Score (typically -3 to +3, unbounded)
**Normalization:** _N (scale-invariant)
**Periods:** 21, 42 (1wk, 2wk)
**Pros:**
- Scale-invariant — z-score is unitless, self-normalizing
- Captures statistical extremeness — distinct from level (fundingMa) or direction (fundingMaDiff)
- Mean-reversion signal — extreme z-scores (>2σ) historically tend to revert
- Crowded trade detection — extreme funding = one-sided positioning likely to unwind
- Well-bounded output — 99.7% of values within ±3 (Gaussian assumption)
- Self-stabilizing — including current in window prevents extreme outliers from producing infinity
**Cons:**
- Assumes somewhat normal distribution → funding rates are roughly symmetric, acceptable
- Longer lookback needed for stable std → why we use 21, 42 (not 3, 7)
- Can be unstable with very low std → handled via threshold (see implementation notes)
**Rationale:** Identifies statistically extreme funding conditions; captures "how unusual is current funding relative to recent window" — information not available from level or momentum alone
**Implementation Notes:**
- Window convention: `t-n+1` to `t` (n values total, **includes current**) — consistent with fundingMa, fundingCumulative, V_returnStd
- Use `ddof=0` (population std) for rolling window — consistent with other rolling features
- Edge case handling: if `std < 1e-8`, return `0.0` (constant funding = not extreme)
- Input range: fundingRate typically -0.01% to +0.03% per 8h
- Output range: typically -3 to +3, can exceed in extreme markets
**Academic Support:**
- Z-score normalization is standard statistical practice (no citation needed)
- He et al. (2022/2024) "Fundamentals of Perpetual Futures" [arXiv:2212.06888](https://arxiv.org/abs/2212.06888) — funding rate reflects market positioning
- Sentiment extremes as contrarian signals — established in behavioral finance literature
**Uses Raw:** `RAW_F_I_S_fundingRate_pct_N`
**Approved:** 2025-12-20
**Note:** Complementary to fundingMa (level) and fundingMaDiff (momentum). Z-score captures "extremeness" — the third dimension of funding analysis.

---

## Premium Features

### D_F_T_premiumMa_{n}_pct_N
**Formula:** `mean(premiumClose_{t-n+1:t})`
**Groups/Categories:** Derivative (D), Funding (F), Trend (T)
**Form:** Percentage (decimal form, typically ±0.1%, extremes to ±0.5%)
**Normalization:** _N (scale-invariant)
**Periods:** 3, 7, 21 (1d, ~2d, 1wk)
**Pros:**
- Scale-invariant — premium is already percentage (decimal form)
- Comparable across periods — mean stays in original range
- Leading indicator — premium causes funding rate (He et al.)
- Smoothed regime signal — filters noise from single readings
- Complementary to fundingMa — captures cause (premium) vs effect (funding)
**Cons:**
- Correlated with fundingMa → different timing (premium leads, funding lags)
- Lagging → accepted trade-off (all smoothing lags)
**Rationale:** Smoothed premium captures persistent futures-spot spread; premium is leading indicator that drives funding rate calculation
**Implementation Notes:**
- Window convention: `t-n+1` to `t` (n values, **includes current**) — consistent with fundingMa
- Input format: decimal (0.0005 = 0.05%)
- Input range: typically ±0.1%, extremes to ±0.5% (verified from data: -0.35% to +0.57%)
- Output range: same as input (mean preserves scale)
- Column mapping: `close` column in premium parquet → `RAW_D_F_S_premiumClose_pct_N`
**Academic Support:**
- He et al. (2022/2024) "Fundamentals of Perpetual Futures" [arXiv:2212.06888](https://arxiv.org/abs/2212.06888) — Premium drives funding rate; premium persistence indicates positioning
**Uses Raw:** `RAW_D_F_S_premiumClose_pct_N`
**Approved:** 2025-12-20
**Note:** Premium → Funding causal relationship. Premium is leading indicator (cause), funding is lagging outcome (effect).

### D_F_N_S_premiumZscore_{n}_zsc_N
**Formula:** 
```
μ = mean(premiumClose_{t-n+1:t})  # rolling mean over n periods, includes current
σ = std(premiumClose_{t-n+1:t})   # rolling std over n periods, includes current
z = (premiumClose_t - μ) / σ
```
**Groups/Categories:** Derivative (D), Funding (F), Normalized (N), Sentiment (S)
**Form:** Z-Score (typically -3 to +3, unbounded)
**Normalization:** _N (scale-invariant)
**Periods:** 21, 42 (1wk, 2wk)
**Pros:**
- Scale-invariant — z-score is unitless, self-normalizing
- Very low correlation with premiumMa (-0.046) — captures different information (extremeness vs level)
- Identifies statistical extremes — mean reversion signal when |z| > 2
- Sentiment proxy — extreme positive = crowded longs, extreme negative = crowded shorts
- Well-bounded output — 99%+ of values within ±3 (verified: 0.15% < -3, 0.54% > +3)
- Consistent with fundingZscore — same methodology, same implementation conventions
**Cons:**
- Longer lookback needed for stable std → why we use 21, 42 (not 3, 7)
- Assumes roughly normal distribution → premium is roughly symmetric, acceptable
- Can be unstable with very low std → handled via threshold (see implementation notes)
**Rationale:** Identifies statistically extreme premium conditions; captures "how unusual is current premium relative to recent window" — information not available from premiumMa (level) alone
**Implementation Notes:**
- Window convention: `t-n+1` to `t` (n values total, **includes current**) — consistent with premiumMa, fundingZscore
- Use `ddof=0` (population std) for rolling window — consistent with other rolling features
- Edge case handling: if `std < 1e-8`, return `0.0` (constant premium = not extreme)
- Input format: decimal (0.0005 = 0.05%)
- Input range: typically ±0.1%, extremes to ±0.5% (verified: -0.35% to +0.57%)
- Output range: typically -3 to +3 (verified: -4.11 to +4.18 in historical data)
- Output statistics: mean ≈ 0.00, std ≈ 1.07 (verified on 5,418 valid rows)
**Academic Support:**
- Z-score normalization is standard statistical practice (no citation needed)
- He et al. (2022/2024) "Fundamentals of Perpetual Futures" [arXiv:2212.06888](https://arxiv.org/abs/2212.06888) — premium reflects futures-spot relationship
- Sentiment extremes as contrarian signals — established in behavioral finance literature
**Uses Raw:** `RAW_D_F_S_premiumClose_pct_N`
**Approved:** 2025-12-20
**Note:** Complementary to premiumMa (level). Z-score captures "extremeness" — useful for mean-reversion strategies when market positioning is one-sided.

### M_D_F_S_premiumChange_pct_N
**Formula:** `premiumChange = premiumClose - premiumOpen`
**Groups/Categories:** Momentum (M), Derivative (D), Funding (F), Sentiment (S)
**Form:** Percentage (unbounded, typically -0.5% to +0.5%)
**Normalization:** _N (scale-invariant — premium is already a ratio)
**Pros:**
- **Extremely unique signal** — 0.017 correlation with price movements!
- Captures sentiment shift — how premium evolved within the bar
- Perpetual-specific — unique to derivatives markets
- Near-zero correlation — genuinely new information for model
**Cons:**
- Small absolute values — may need careful scaling
- Interpretation requires domain knowledge → well documented
**Rationale:** Measures the shift in spot-perp basis within a single bar. Unlike premiumClose (end state), this captures the *direction* of premium movement during the bar. Positive = perpetual became more expensive relative to spot (bullish positioning).
**Data Validation (8h BTCUSDT):**
- Range: -0.48% to +0.41%
- Mean: ~0%
- Std: 0.04%
- Correlation with logReturn: 0.017 (extremely unique!)
- Correlation with premiumClose: 0.315
**Implementation Notes:**
- Formula (Polars): `pl.col('close_prem') - pl.col('open_prem')` (from premium parquet)
**Academic Support:**
- He et al. (2022/2024) "Fundamentals of Perpetual Futures" [arXiv:2212.06888](https://arxiv.org/abs/2212.06888) — premium dynamics reflect positioning
- Perpetual futures premium/basis dynamics documented in crypto derivatives literature
**Uses Raw:** `RAW_D_F_S_premiumClose_pct_N`, `RAW_D_F_S_premiumOpen_pct_N`
**Approved:** 2025-12-21

### V_D_F_S_premiumRange_pct_N
**Formula:** `premiumRange = premiumHigh - premiumLow`
**Groups/Categories:** Volatility (V), Derivative (D), Funding (F), Sentiment (S)
**Form:** Percentage (bounded ≥ 0, typically 0 to 2.3%)
**Normalization:** _N (scale-invariant — premium is already a ratio)
**Pros:**
- Unique signal — 0.286 correlation with price range, 0.421 with rangeNorm
- Captures premium volatility — derivatives market stress indicator
- Bounded below by 0 — natural floor
- Perpetual-specific — unique information about derivatives positioning
**Cons:**
- May have fat tails during extreme events → acceptable for stress indicator
- Small absolute values — need careful scaling
**Rationale:** Measures the volatility of the spot-perp basis within a single bar. High premiumRange indicates unstable derivatives positioning — market stress, liquidations, or rapid repositioning.
**Data Validation (8h BTCUSDT):**
- Range: 0% to 2.28%
- Mean: 0.05%
- Std: 0.10%
- Correlation with priceRange: 0.286 (unique)
- Correlation with rangeNorm: 0.421 (unique)
**Implementation Notes:**
- Formula (Polars): `pl.col('high_prem') - pl.col('low_prem')` (from premium parquet)
**Academic Support:**
- He et al. (2022/2024) "Fundamentals of Perpetual Futures" [arXiv:2212.06888](https://arxiv.org/abs/2212.06888) — premium volatility as market stress
- Basis volatility as market stress indicator in derivatives literature
**Uses Raw:** `RAW_D_F_S_premiumHigh_pct_N`, `RAW_D_F_S_premiumLow_pct_N`
**Approved:** 2025-12-21

---

## Spread Features

### D_F_basis_pct_N
**Formula:** `basis = (futuresClose - indexClose) / indexClose`
**Groups/Categories:** Derivative (D), Funding (F)
**Form:** Percentage (unbounded, typically ±0.5%, extremes to ±1%)
**Normalization:** _N (scale-invariant)
**Pros:**
- Scale-invariant — percentage spread works at any price level
- Direct arbitrage signal — captures actual traded price vs spot
- Uses real execution price — unlike premium which uses mark/fair value
- Core to perpetual theory — He et al. (2024) identifies basis as fundamental
- Moderate correlation with premium (0.82) — captures additional information (18% independent variance)
**Cons:**
- Correlated with premium features → but uses different price source (futures close vs mark)
- Can be noisy at bar boundaries → accepted trade-off (reflects actual market)
**Rationale:** Direct measurement of futures-spot spread using actual traded prices; captures arbitrage opportunity and market inefficiency distinct from premium (which uses mark price)
**Implementation Notes:**
- Formula (Polars): `(pl.col('futuresClose') - pl.col('indexClose')) / pl.col('indexClose')`
- Input: futuresClose from sorted-8h (last traded price), indexClose from index-price-8h (spot aggregate)
- Output format: decimal (0.001 = 0.1%)
- Output range: typically ±0.05% (±0.0005), extremes to ±1% (verified: -1.02% to +0.44%)
- No edge cases — indexClose never zero in historical data (verified)
- Note: basis ≠ premium. Basis uses futures close (traded), premium uses mark-index relationship
**Correlation Analysis:**
- Correlation(basis, premium): 0.82 — related but not redundant
- Correlation(basis, premiumMa_7): 0.67 — different signals
- Independent variance: ~33% (1 - 0.82²)
**Academic Support:**
- He et al. (2022/2024) "Fundamentals of Perpetual Futures" [arXiv:2212.06888](https://arxiv.org/abs/2212.06888) — basis is core to perpetual pricing theory and arbitrage
**Uses Raw:** `RAW_P_close_abs_NN`, `RAW_P_indexClose_abs_NN`
**Approved:** 2025-12-20
**Note:** Distinct from premium — basis uses actual traded futures close, premium uses mark/fair value. Both are valid signals capturing different aspects of futures-spot relationship.

### D_markIndexSpread_pct_N
**Formula:** `(markClose - indexClose) / indexClose`
**Groups/Categories:** Derivative (D)
**Form:** Percentage (unbounded, typically ±0.2%)
**Normalization:** _N (scale-invariant)
**Pros:**
- Scale-invariant — percentage spread works at any price level
- Distinct from premium — correlation 0.556 (69% unique variance)
- Short-term mispricing indicator — captures instantaneous mark vs spot divergence
- Mark price drives liquidations — this spread shows liquidation risk relative to spot
- Simple, single-bar feature — no lookback required
**Cons:**
- No academic citation → domain-justified (mark price is perpetual-specific)
- Moderate correlation with premium → but different calculation, different information
**Rationale:** Captures mark-index spread which differs from Bybit's premium calculation; mark price is exchange fair value used for liquidations, making this spread relevant for risk assessment
**Data Validation (8h BTCUSDT):**
- Range: -0.17% to +0.27%
- Std: 0.037%
- Correlation with premium: 0.556 — NOT redundant (verified)
**Implementation Notes:**
- Formula (Polars): `(pl.col('markClose') - pl.col('indexClose')) / pl.col('indexClose')`
- Output format: decimal (0.001 = 0.1%)
- Mark price source: mark-price-8h parquet (close column)
- Index price source: index-price-8h parquet (close column)
**Uses Raw:** `RAW_P_markClose_abs_NN`, `RAW_P_indexClose_abs_NN`
**Approved:** 2025-12-20

---

## Open Interest Features

### L_M_N_S_oiPctChange_pct_N
**Formula:** `(openInterest_t - openInterest_{t-1}) / openInterest_{t-1}`
**Groups/Categories:** Liquidity (L), Momentum (M), Normalized (N), Sentiment (S)
**Form:** Percentage (unbounded)
**Normalization:** _N (scale-invariant)
**Pros:**
- Scale-invariant — percentage change works at any OI level
- Single-period momentum — captures immediate positioning shifts
- Multi-dimensional signal — Liquidity (market depth), Momentum (change rate), Sentiment (positioning)
- Perpetual-specific — OI is unique to derivatives, not available in spot
- Academic support — Wang et al. (2020) validates OI significance in derivatives ML
**Cons:**
- Can be extreme during deleveraging events → accepted trade-off (captures real market stress)
- Single period only → complemented by oiRoc_{n} for multi-period momentum
**Rationale:** Fundamental OI momentum feature; captures single-period positioning change normalized for scale invariance
**Data Validation (8h BTCUSDT):**
- Range: -32.9% to +187.2%
- Mean: 0.12%, Std: 4.47%
- Note: Right-skewed due to occasional large OI increases
**Implementation Notes:**
- Formula (Polars): `(pl.col('openInterest') - pl.col('openInterest').shift(1)) / pl.col('openInterest').shift(1)`
- First row will be null (no previous OI)
**Academic Support:**
- Wang et al. (2020) "Modeling price and risk in Chinese financial derivative market with deep neural network architectures" [paper](https://ieeexplore.ieee.org/abstract/document/9178679/) — OI changes predict returns
**Uses Raw:** `RAW_L_S_openInterest_abs_NN`
**Approved:** 2025-12-20
**Replaces:** `L_M_S_oiChange_dif_NN` (normalized version)

### L_N_volOiRatio_rat_N
**Formula:** `volume / openInterest`
**Groups/Categories:** Liquidity (L), Normalized (N)
**Form:** Ratio (0 to +∞, typically 0.1 to 5)
**Normalization:** _N (scale-invariant)
**Pros:**
- Scale-invariant — ratio is dimensionless, comparable across time
- Unique turnover signal — captures speculation vs holding conviction
- High ratio = high turnover (speculation, short-term trading)
- Low ratio = position holding (conviction, longer-term positioning)
- Perpetual-specific — OI only available in derivatives markets
- Academic support — Honey Singh & Chaudhary (2023) validates vol/OI ratio predictive power
**Cons:**
- Can spike during liquidation cascades → accepted trade-off (captures real market stress)
- OI measured at bar end vs volume over bar → minor timing mismatch, accepted
**Rationale:** Turnover rate combining volume activity with open interest positioning; captures market participation style (speculation vs conviction)
**Data Validation (8h BTCUSDT):**
- Range: 0.04 to 19.0
- Mean: 0.97, Std: 0.90
- Interpretation: ratio near 1.0 = typical turnover; >2 = high speculation; <0.5 = holding conviction
**Implementation Notes:**
- Formula (Polars): `pl.col('volume') / pl.col('openInterest')`
- Edge case: if OI = 0, return null (shouldn't happen in liquid markets)
**Academic Support:**
- Honey Singh & Chaudhary (2024) "Option Volume and Open Interest for Predicting Underlying Return" [Springer](https://link.springer.com/chapter/10.1007/978-981-97-6242-2_6) — validates vol/OI ratio predictive power in derivatives
- Wang et al. (2020) [paper](https://ieeexplore.ieee.org/abstract/document/9178679/) — open interest significance in derivatives ML
**Uses Raw:** `RAW_L_volume_abs_NN`, `RAW_L_S_openInterest_abs_NN`
**Approved:** 2025-12-20
**Note:** Honey Singh & Chaudhary (2024) found vol/OI ratio predictive for individual stock options but less reliable for index derivatives. BTCUSDT perpetual is index-like; use as market structure feature in combination with others, not as standalone predictor.

---

## Candlestick Shape Features

### C_N_bodySize_bnd_N
**Formula:** `|close - open| / (high - low)`
**Groups/Categories:** Candlestick (C), Normalized (N)
**Form:** Bounded (0 to 1)
**Normalization:** _N (scale-invariant)
**Pros:**
- Scale-invariant — bounded 0-1, comparable across all time periods
- Conviction measure — large body = strong directional move
- Indecision signal — small body (doji) = uncertainty
- Classic candlestick analysis — well-established pattern recognition
- Complements price features — shape vs level/return
- No look-ahead — uses only current bar OHLC
**Cons:**
- Edge case when high = low (perfect doji) → division by zero → return 0
- Doesn't distinguish bullish vs bearish → use with candleDirection_bin
**Rationale:** Candlestick body size relative to total range captures conviction; large body = strong directional move, small body = indecision
**Data Validation (8h BTCUSDT):**
- Range: 0.00 to 1.00
- Mean: 0.40
- Interpretation: 0.0 = perfect doji (no body); 1.0 = marubozu (all body, no wicks)
**Implementation Notes:**
- Formula (Polars): `(pl.col('close') - pl.col('open')).abs() / (pl.col('high') - pl.col('low'))`
- Edge case: if high = low, return 0 (no range, doji)
**Academic Support:**
- Nison (1991) "Japanese Candlestick Charting Techniques" [book](https://www.amazon.com/dp/0735201811) — body/range ratio significance
**Uses Raw:** `RAW_P_open_abs_NN`, `RAW_P_high_abs_NN`, `RAW_P_low_abs_NN`, `RAW_P_close_abs_NN`
**Approved:** 2025-12-20

### C_N_upperShadow_bnd_N
**Formula:** `(high - max(open, close)) / (high - low)`
**Groups/Categories:** Candlestick (C), Normalized (N)
**Form:** Bounded (0 to 1)
**Normalization:** _N (scale-invariant)
**Pros:**
- Scale-invariant — bounded 0-1, comparable across all time periods
- Selling pressure signal — long upper shadow = rejection at highs
- Price rejection indicator — market failed to hold higher prices
- Classic candlestick analysis — well-established pattern recognition
- Complements bodySize — together capture full candlestick shape
- No look-ahead — uses only current bar OHLC
**Cons:**
- Edge case when high = low (perfect doji) → division by zero → return 0
- Context-dependent — meaning varies with trend (reversal vs continuation)
**Rationale:** Upper shadow relative to total range captures selling pressure at highs; long shadow = price rejection, short shadow = sustained buying
**Data Validation (8h BTCUSDT):**
- Range: 0.00 to 0.92
- Mean: 0.29
- Interpretation: 0.0 = no upper shadow (closing at high); 0.5 = shadow is half the range
**Implementation Notes:**
- Formula (Polars): `(pl.col('high') - pl.max_horizontal('open', 'close')) / (pl.col('high') - pl.col('low'))`
- Edge case: if high = low, return 0 (no range, doji)
**Academic Support:**
- Nison (1991) "Japanese Candlestick Charting Techniques" [book](https://www.amazon.com/dp/0735201811) — shadow patterns significance
**Uses Raw:** `RAW_P_open_abs_NN`, `RAW_P_high_abs_NN`, `RAW_P_low_abs_NN`, `RAW_P_close_abs_NN`
**Approved:** 2025-12-20

### C_N_lowerShadow_bnd_N
**Formula:** `(min(open, close) - low) / (high - low)`
**Groups/Categories:** Candlestick (C), Normalized (N)
**Form:** Bounded (0-1)
**Normalization:** _N (scale-invariant)
**Pros:**
- Scale-invariant — normalized by bar range
- Bounded 0-1 — no extreme outliers
- Classic candlestick analysis — well-established pattern recognition
- Complements bodySize and upperShadow — together capture full candlestick shape
- No look-ahead — uses only current bar OHLC
**Cons:**
- Edge case when high = low (perfect doji) → division by zero → return 0
- Context-dependent — meaning varies with trend (reversal vs continuation)
**Rationale:** Lower shadow relative to total range captures buying pressure at lows; long shadow = price rejection at lows (bullish), short shadow = weak demand
**Data Validation (8h BTCUSDT):**
- Range: 0.00 to 0.94
- Mean: 0.31
- Interpretation: 0.0 = no lower shadow (closing at low); 0.5 = shadow is half the range
**Implementation Notes:**
- Formula (Polars): `(pl.min_horizontal('open', 'close') - pl.col('low')) / (pl.col('high') - pl.col('low'))`
- Edge case: if high = low, return 0 (no range, doji)
**Academic Support:**
- Nison (1991) "Japanese Candlestick Charting Techniques" [book](https://www.amazon.com/dp/0735201811) — shadow patterns significance
**Uses Raw:** `RAW_P_open_abs_NN`, `RAW_P_high_abs_NN`, `RAW_P_low_abs_NN`, `RAW_P_close_abs_NN`
**Approved:** 2025-12-20

### B_C_candleDirection_bin
**Formula:** `sign(close - open)`
**Groups/Categories:** Binary (B), Candlestick (C)
**Form:** Binary (-1, 0, +1)
**Normalization:** _N (inherently scale-invariant — discrete states)
**Pros:**
- Simple, interpretable — bullish/bearish/doji classification
- Discrete state — useful for tree-based models and splitting
- Nearly balanced classes — no imbalance concern (50.8% vs 49.2%)
- No look-ahead — uses only current bar OHLC
**Cons:**
- Ignores magnitude — doesn't capture how bullish/bearish
- Ignores shadows — only body direction, not conviction
**Rationale:** Basic directional classification; useful as conditional feature for models that split on direction
**Data Validation (8h BTCUSDT):**
- Distribution: +1 (bullish): 50.8%, -1 (bearish): 49.2%, 0 (doji): 0.04%
- Near-perfect balance — no class imbalance handling needed
**Implementation Notes:**
- Formula (Polars): `pl.when(pl.col('close') > pl.col('open')).then(1).when(pl.col('close') < pl.col('open')).then(-1).otherwise(0)`
- Dojis (close = open) rare: only 0.04% of data
**Uses Raw:** `RAW_P_open_abs_NN`, `RAW_P_close_abs_NN`
**Approved:** 2025-12-20

---

## Oscillator Features

### M_N_rsi_{n}_bnd_N
**Formula:** 
```
RS = avg_gain(n) / avg_loss(n)
RSI = 100 - (100 / (1 + RS))
```
**Groups/Categories:** Momentum (M), Normalized (N)
**Form:** Bounded (0-100)
**Normalization:** _N (scale-invariant)
**Periods:** 6, 12, 21 (2d, 4d, 1wk)
**Pros:**
- Bounded 0-100 — no extreme outliers, no normalization needed
- Well-established momentum oscillator — 40+ years of usage
- Clear interpretation — <30 oversold, >70 overbought
- Different concept from pctB — RSI uses gain/loss ratio, pctB uses volatility bands
- Strong academic support for ML applications
**Cons:**
- Can stay extreme in strong trends → not contrarian-only signal
- Lagging indicator → uses historical data by design
**Rationale:** Measures momentum strength via gain/loss balance; bounded oscillator ideal for ML
**Data Validation (8h BTCUSDT, n=6):**
- Range: 0.0 to 100.0
- Mean: 51.4
- Bounded by construction ✓
**Academic Support:**
- Wilder (1978) "New Concepts in Technical Trading Systems" [book](https://www.amazon.com/dp/0894590278) — RSI origin
- Demir et al. (2020) "Technical indicators for cryptocurrency" [paper](https://www.mdpi.com/2076-3417/10/1/255) — RSI effective across model types
**Uses Raw:** `RAW_P_close_abs_NN`
**Approved:** 2025-12-20

### M_N_stochasticK_{n}_bnd_N
**Formula:** `%K = (close - lowest_low_n) / (highest_high_n - lowest_low_n) × 100`
**Groups/Categories:** Momentum (M), Normalized (N)
**Form:** Bounded (0-100)
**Normalization:** _N (scale-invariant)
**Periods:** 6, 12 (2d, 4d)
**Pros:**
- Bounded 0-100 — no extreme outliers
- Price position within actual H/L range — different from Bollinger %B
- Identifies momentum exhaustion — near 100 = near highs, near 0 = near lows
- Standard technical indicator — widely used and understood
**Cons:**
- Can stay extreme in strong trends → similar limitation to RSI
- Uses H/L which can be noisy → smoothed version (%D) addresses this
**Rationale:** Position of close within recent high-low range; identifies overbought/oversold using actual price extremes
**Data Validation (8h BTCUSDT, n=6):**
- Range: 0.0 to 100.0
- Mean: 52.3
- Bounded by construction ✓
**Academic Support:**
- Lane, George C. (1950s-1984) — Stochastic oscillator developed in late 1950s; documented in [Investopedia](https://www.investopedia.com/terms/s/stochasticoscillator.asp)
- Standard technical indicator in most ML trading research
**Uses Raw:** `RAW_P_high_abs_NN`, `RAW_P_low_abs_NN`, `RAW_P_close_abs_NN`
**Approved:** 2025-12-20
**Uniqueness Note:** Different from pctB — StochK uses actual H/L range; pctB uses ±2σ statistical bands. Different range definitions capture different market states.

### M_N_T_stochasticD_{n}_bnd_N
**Formula:** `%D = SMA(%K, 3)`
**Groups/Categories:** Momentum (M), Normalized (N), Trend (T)
**Form:** Bounded (0-100)
**Normalization:** _N (scale-invariant)
**Periods:** 6, 12 (2d, 4d)
**Pros:**
- Smoothed version of %K — reduces noise
- Still bounded 0-100 — inherits from %K
- Crossover signal — %K crossing %D is classic signal
- Trend component (T) — smoothing introduces trend-following aspect
**Cons:**
- More lag than %K → trade-off for smoothness
- Depends on %K → not independent feature
**Rationale:** Smoothed stochastic reduces noise while retaining overbought/oversold signal; crossovers provide entry/exit timing
**Data Validation (8h BTCUSDT, n=6):**
- Range: 5.3 to 97.0
- Mean: 52.3
- Correlation with %K: 0.82 (smoothed but retains signal)
**Implementation Notes:**
- 3-period SMA is standard; adjust for different smoothing
**Academic Support:**
- Lane, George C. (1950s-1984) — Stochastic %D as signal line; documented in [Investopedia](https://www.investopedia.com/terms/s/stochasticoscillator.asp)
**Uses Raw:** `RAW_P_high_abs_NN`, `RAW_P_low_abs_NN`, `RAW_P_close_abs_NN`
**Approved:** 2025-12-20

---

## Volume Features

### L_M_N_volumeRoc_{n}_pct_N
**Formula:** `(volume_t - volume_{t-n}) / volume_{t-n}`
**Groups/Categories:** Liquidity (L), Momentum (M), Normalized (N)
**Form:** Percentage (unbounded, highly skewed)
**Normalization:** _N (scale-invariant)
**Periods:** 3, 6, 12 (1d, 2d, 4d)
**Pros:**
- Scale-invariant — ratio form normalizes across time
- Captures volume momentum — accelerating/decelerating participation
- Multi-period flexibility — different horizons for different signals
**Cons:**
- Highly skewed right — volume spikes cause extreme positive values (+3805%)
- May need capping or log transform for some models
**Rationale:** Rate of change in volume; identifies surges in participation vs declining interest
**Data Validation (8h BTCUSDT, n=6):**
- Range: -95.4% to +3804.8%
- Mean: +43.1%, Std: 158.8%
- Note: Highly skewed — consider log(1+volumeRoc) for symmetry
**Implementation Notes:**
- Formula (Polars): `(pl.col('volume') - pl.col('volume').shift(n)) / pl.col('volume').shift(n)`
**Uses Raw:** `RAW_L_volume_abs_NN`
**Approved:** 2025-12-20

### L_N_volumeRatio_{n}_rat_N
**Formula:** `volume / SMA(volume, n)`
**Groups/Categories:** Liquidity (L), Normalized (N)
**Form:** Ratio (0 to +∞, typically 0.1-4)
**Normalization:** _N (scale-invariant)
**Periods:** 6, 12, 21 (2d, 4d, 1wk)
**Pros:**
- Scale-invariant — ratio to moving average
- Intuitive interpretation — >1 = above average activity, <1 = below
- Better bounded than volumeRoc — max ~4x vs ~38x
- Identifies unusual volume relative to recent baseline
**Cons:**
- SMA introduces lag → trade-off for stability
- Near-zero SMA could cause instability → rare in practice
**Rationale:** Current volume normalized by recent average; identifies unusual activity relative to baseline
**Data Validation (8h BTCUSDT, n=6):**
- Range: 0.12 to 4.46
- Mean: 1.02
- Better bounded than volumeRoc
**Implementation Notes:**
- Formula (Polars): `pl.col('volume') / pl.col('volume').rolling_mean(n)`
**Uses Raw:** `RAW_L_volume_abs_NN`
**Approved:** 2025-12-20

### N_P_L_vwapDeviation_pct_N
**Formula:**
```
VWAP = turnover / volume  (intrabar volume-weighted average price)
vwapDeviation = (close - VWAP) / VWAP
```
**Groups/Categories:** Normalized (N), Price (P), Liquidity (L)
**Form:** Percentage (unbounded, typically -5% to +6%)
**Normalization:** _N (scale-invariant)
**Pros:**
- Scale-invariant — deviation expressed as percentage
- Volume-weighted — reflects where actual trading occurred
- Mean reversion signal — extreme deviations tend to revert
- Intrabar granularity — complements close-to-close features
- Strong industry usage — VWAP deviation bands widely used
**Cons:**
- Single bar only → could extend to rolling VWAP in future
- Requires both turnover and volume → both available in raw data
**Rationale:** Measures how far closing price deviates from the volume-weighted average. When price closes far from VWAP, it often reverts. Mean-reversion signal used by institutional traders.
**Data Validation (8h BTCUSDT):**
- Range: -4.42% to +5.74%
- Mean: 0.04%
- Std: 0.76%
- Correlation with logReturn: 0.730 (unique signal)
**Implementation Notes:**
- Formula (Polars): `(pl.col('close') - pl.col('turnover')/pl.col('volume')) / (pl.col('turnover')/pl.col('volume'))`
**Academic Support:**
- Genet (2025) "Deep Learning for VWAP Execution in Crypto Markets" [arXiv:2502.18177](https://arxiv.org/abs/2502.18177)
- Berkowitz et al. (1988) "The Total Cost of Transactions on the NYSE"
**Uses Raw:** `RAW_L_turnover_abs_NN`, `RAW_L_volume_abs_NN`
**Approved:** 2025-12-21

### M_P_L_vwapReturn_pct_N
**Formula:**
```
VWAP = turnover / volume
vwapReturn = ln(VWAP_t / VWAP_{t-1})
```
**Groups/Categories:** Momentum (M), Price (P), Liquidity (L)
**Form:** Percentage (unbounded)
**Normalization:** _N (scale-invariant)
**Pros:**
- Scale-invariant — log returns
- Volume-weighted — captures where trading actually occurred
- Unique signal — 0.788 correlation with logReturn (~38% unexplained variance)
- Complements logReturn — different perspective on same price movement
**Cons:**
- Requires VWAP computation → straightforward (turnover/volume)
- May be noisy in low-volume periods → volume already captures this
**Rationale:** Log return computed using VWAP instead of close price. Captures momentum from where actual trading occurred, not just where the bar closed.
**Data Validation (8h BTCUSDT):**
- Range: -10.77% to +11.75%
- Mean: 0.02%
- Std: 1.53%
- Correlation with logReturn: 0.788 (unique signal)
**Implementation Notes:**
- Formula (Polars): `(pl.col('turnover')/pl.col('volume')).log() - (pl.col('turnover')/pl.col('volume')).shift(1).log()`
**Academic Support:**
- Genet (2025) "Deep Learning for VWAP Execution in Crypto Markets" [arXiv:2502.18177](https://arxiv.org/abs/2502.18177)
**Uses Raw:** `RAW_L_turnover_abs_NN`, `RAW_L_volume_abs_NN`
**Approved:** 2025-12-21

---

## Open Interest Features

### L_M_N_S_oiRoc_{n}_pct_N
**Formula:** `(openInterest_t - openInterest_{t-n}) / openInterest_{t-n}`
**Groups/Categories:** Liquidity (L), Momentum (M), Normalized (N), Sentiment (S)
**Form:** Percentage (unbounded)
**Normalization:** _N (scale-invariant)
**Periods:** 3, 6, 12 (1d, 2d, 4d)
**Pros:**
- Scale-invariant — ratio form normalizes across time and OI levels
- Multi-period positioning momentum — beyond single-period change (oiPctChange)
- Sentiment indicator — rising OI = new positions, falling OI = position closure
- Perpetual-specific — unique to derivatives markets
**Cons:**
- Unbounded — can have extreme values during deleveraging
- Correlated with oiPctChange (0.69) and oiRatio (0.77) → different horizons provide value
**Rationale:** Rate of change in open interest over multiple periods; captures positioning acceleration/deceleration trends
**Data Validation (8h BTCUSDT, n=6):**
- Range: -60.4% to +185.0%
- Std: 9.0%
- Reasonable bounds for percentage feature
**Academic Support:**
- Ruan & Streltsov (2022) "Perpetual Futures Contracts and Cryptocurrency Market Microstructure" [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4218907) — OI as positioning signal in crypto perpetuals
**Uses Raw:** `RAW_L_S_openInterest_abs_NN`
**Approved:** 2025-12-20
**Uniqueness Note:** Differs from L_M_N_S_oiPctChange (single-period) by capturing multi-period trends. Both have value.

### L_N_S_oiRatio_{n}_rat_N
**Formula:** `openInterest / SMA(openInterest, n)`
**Groups/Categories:** Liquidity (L), Normalized (N), Sentiment (S)
**Form:** Ratio (0 to +∞, typically 0.6-2.2)
**Normalization:** _N (scale-invariant)
**Periods:** 6, 12, 21 (2d, 4d, 1wk)
**Pros:**
- Scale-invariant — ratio to moving average
- Intuitive interpretation — >1 = crowded positioning, <1 = light positioning
- Well-bounded — max ~2.2x in 8h data
- Analogous to volumeRatio for OI — consistent framework
**Cons:**
- SMA introduces lag → trade-off for stability
- Correlated with oiRoc (0.77) and oiPctChange (0.69) → captures different concept (level vs momentum)
**Rationale:** Current OI normalized by recent average; identifies whether positioning is high or low relative to baseline
**Data Validation (8h BTCUSDT, n=6):**
- Range: 0.60 to 2.18
- Mean: 1.00
- Well-bounded ratio
**Academic Support:**
- Positioning analysis literature for derivatives markets
**Uses Raw:** `RAW_L_S_openInterest_abs_NN`
**Approved:** 2025-12-20
**Uniqueness Note:** This is the proper normalized replacement for L_T_oiSma (which was _NN). Captures "is current OI high or low vs recent average?" while oiRoc captures momentum.

---

## Momentum Acceleration Features

### M_N_rocAccel_{n}_dif_N
**Formula:** `ROC_t(n) - ROC_{t-n}(n)` where `ROC(n) = (close_t - close_{t-n}) / close_{t-n}`
**Groups/Categories:** Momentum (M), Normalized (N)
**Form:** Difference of percentages (unbounded, typically ±35%)
**Normalization:** _N (scale-invariant — difference of normalized percentages)
**Periods:** 3, 6 (1d, 2d)
**Pros:**
- Scale-invariant — ROC is dimensionless, difference of ROC is dimensionless
- Second derivative of price — captures momentum acceleration/deceleration
- Identifies momentum exhaustion — acceleration slowing before reversal
- No division instability — simple subtraction, no near-zero denominator issues
- Well-bounded in practice — ±35% range covers most cases
**Cons:**
- Lagging — uses 2n periods of data
- Second-order features can be noisy → use with other signals
**Rationale:** Momentum acceleration — how is the rate of change itself changing? Early reversal signal when momentum is gaining or losing strength.
**Data Validation (8h BTCUSDT, n=6):**
- Range: -33.9% to +34.4%
- Std: 6.1%
- Well-bounded (vs original `ROC(ROC(n),n)` formula which produced ±1,000,000% due to division by near-zero ROC)
**Implementation Notes:**
- Renamed from `rocOfRoc`. Original formula `(ROC_t - ROC_{t-n}) / ROC_{t-n}` was mathematically unstable when `ROC_{t-n} ≈ 0` (3.3% of data). This simpler formula captures same concept without instability.
**Uses Raw:** `RAW_P_close_abs_NN`
**Approved:** 2025-12-20

---

## Composite & Weighted Features

### M_P_S_W_oiWeightedReturn_pct_N
**Formula:** `logReturn × (oiChange / openInterest)`
**Groups/Categories:** Momentum (M), Price (P), Sentiment (S), Weighted (W)
**Form:** Percentage (weighted, unbounded)
**Normalization:** _N (scale-invariant — product of two normalized values)
**Pros:**
- Combines price direction with positioning conviction
- Large OI change amplifies return signal — captures "conviction moves"
- Unique composite — interaction not captured by separate logReturn + oiPctChange
- Scale-invariant — both components are normalized
**Cons:**
- Composite features can be harder to interpret → accepted trade-off for unique signal
- Unbounded → rarely extreme in practice (-5.6% to +1.5%)
**Rationale:** Interaction term — ML would need to learn this relationship from separate features. Providing it directly captures "returns backed by positioning changes."
**Data Validation (8h BTCUSDT):**
- Range: -5.6% to +1.5%
- Mean: 0.0003%, Std: 0.14%
**Uses Raw:** `RAW_P_close_abs_NN`, `RAW_L_S_openInterest_abs_NN`
**Approved:** 2025-12-20

---

## Temporal Features

### F_TM_fundingCyclePosition_bin
**Formula:** `hour_of_day mod 8` → values [0, 8, 16] UTC for 8h data
**Groups/Categories:** Funding (F), Temporal (TM)
**Form:** Binary/Categorical (discrete values)
**Normalization:** N/A (categorical)
**Pros:**
- Domain-specific to perpetuals — funding settlement timing effects
- U-shaped market quality over cycle (academic support)
- Categorical — clean one-hot or cyclical encoding for ML
- Only 3 values for 8h data — low cardinality
**Cons:**
- Only meaningful for perpetual futures → accepted (our domain)
- Requires proper encoding → use one-hot or cyclical sin/cos
**Rationale:** Perpetual-specific temporal feature with academic support. Funding settlements create predictable patterns.
**Academic Support:** Ruan & Streltsov (2022) - funding cycle patterns
**Data Validation (8h BTCUSDT):**
- Unique values: [0, 8, 16]
- Distribution: ~1,813 bars each (uniform)
**Uses Raw:** `RAW_TM_timestamp`
**Approved:** 2025-12-20

### B_TM_dayOfWeek_bin
**Formula:** ISO weekday (1=Mon, 7=Sun) with one-hot or cyclical encoding
**Groups/Categories:** Binary (B), Temporal (TM)
**Form:** Binary/Categorical (1-7)
**Normalization:** N/A (categorical)
**Pros:**
- Captures weekend effects in crypto
- Institutional trading patterns differ by weekday
- Standard temporal feature — well-understood
- Low cardinality (7 values)
**Cons:**
- May have weak signal in 24/7 crypto → monitor in validation
- Requires proper encoding → use one-hot or cyclical sin/cos
**Rationale:** Standard temporal feature for day-of-week seasonality. Weekend liquidity and volatility patterns differ.
**Data Validation (8h BTCUSDT):**
- Distribution: ~777 bars per day (14.3% each) — perfectly uniform
**Uses Raw:** `RAW_TM_timestamp`
**Approved:** 2025-12-20

---

## Mark Price Features

### D_N_markCloseDeviation_pct_N
**Formula:** `(markClose - close) / close`
**Groups/Categories:** Derivative (D), Normalized (N)
**Form:** Percentage (unbounded)
**Normalization:** _N (scale-invariant)
**Pros:**
- Perpetual-specific — mark triggers liquidations, close is market price
- Identifies liquidation risk zones — divergence signals stress
- Scale-invariant — percentage of price
- Different from markIndexSpread (mark vs index, not mark vs trade)
**Cons:**
- Usually very small values → signal may be in tail events
**Rationale:** When mark and trade prices diverge, liquidation pressure exists. This captures that divergence directly.
**Data Validation (8h BTCUSDT):**
- Range: -0.45% to +1.03%
- Mean: 0.0025%, Std: 0.047%
**Uses Raw:** `RAW_P_markClose_abs_NN`, `RAW_P_close_abs_NN`
**Approved:** 2025-12-20

### D_N_V_markAtrRatio_{n}_rat_N
**Formula:** `markAtr(n) / atr(n)` where both use EMA smoothing
**Groups/Categories:** Derivative (D), Normalized (N), Volatility (V)
**Form:** Ratio (typically 0.9-1.1)
**Normalization:** _N (scale-invariant — ratio of same-unit values)
**Periods:** 3, 6, 12
**Pros:**
- Scale-invariant — ratio of two ATRs
- Captures mark vs trade volatility regime over time (smoothed)
- Different from markCloseRange (0.71 correlation) — smoothed vs single-bar
- >1 = mark more volatile (liquidation pressure), <1 = trade more volatile
**Cons:**
- Requires ATR computation for both price types → accepted overhead
**Rationale:** Smoothed ratio of mark to trade volatility. When mark ATR exceeds trade ATR, fair price is moving more than market — potential liquidation pressure.
**Data Validation (8h BTCUSDT, n=6):**
- Range: 0.67 to 1.09
- Mean: ~1.0
- Correlation with markCloseRange: 0.71 (different signal)
**Uses Raw:** `RAW_P_markOpen_abs_NN`, `RAW_P_markHigh_abs_NN`, `RAW_P_markLow_abs_NN`, `RAW_P_markClose_abs_NN`, `RAW_P_high_abs_NN`, `RAW_P_low_abs_NN`, `RAW_P_close_abs_NN`
**Approved:** 2025-12-20
**Note:** Replaces absolute V_markAtr (scale-dependent). Ratio version is normalized.

### D_N_V_markCloseRange_rat_N
**Formula:** `(markHigh - markLow) / (high - low)`
**Groups/Categories:** Derivative (D), Normalized (N), Volatility (V)
**Form:** Ratio (typically 0.8-1.2)
**Normalization:** _N (scale-invariant — ratio of same-unit values)
**Pros:**
- Scale-invariant — ratio of two ranges
- Single-bar comparison — captures intrabar divergence
- >1 = mark more volatile (liquidation pressure)
- <1 = trading more volatile (speculation)
- Different from markAtrRatio (0.71 correlation) — single-bar vs smoothed
**Cons:**
- Single bar can be noisy → use with smoothed features
**Rationale:** Compares fair price range to trading range within single bar. Captures liquidation vs speculation pressure.
**Data Validation (8h BTCUSDT):**
- Range: 0.39 to 1.20
- Mean: 0.98, Median: 0.98
**Uses Raw:** `RAW_P_high_abs_NN`, `RAW_P_low_abs_NN`, `RAW_P_markHigh_abs_NN`, `RAW_P_markLow_abs_NN`
**Approved:** 2025-12-20

### M_P_D_markReturnDiff_pct_N
**Formula:** `ln(markClose_t / markClose_{t-1}) - ln(close_t / close_{t-1})`
**Groups/Categories:** Momentum (M), Price (P), Derivative (D)
**Form:** Percentage (unbounded, typically ±1%)
**Normalization:** _N (scale-invariant — difference of log returns)
**Pros:**
- Captures divergence between mark and trade returns — the unique signal
- Scale-invariant — difference of percentages
- Isolates the 5.7% of bars where mark and trade differ meaningfully
- Better than raw markLogReturn (0.9996 correlation with logReturn)
**Cons:**
- Usually very small values → signal is in divergence events
**Rationale:** Raw markLogReturn is 99.96% correlated with logReturn — near-duplicate. The DIFFERENCE captures the unique information: when fair price moves differently than market price.
**Data Validation (8h BTCUSDT):**
- Range: -0.96% to +0.94%
- Cases where |diff| > 0.1%: 309 (5.7%)
**Uses Raw:** `RAW_P_markClose_abs_NN`, `RAW_P_close_abs_NN`
**Approved:** 2025-12-20
**Note:** Created instead of M_P_markLogReturn (rejected as near-duplicate). This captures the unique divergence signal.

### D_N_closeVsMarkVol_{n}_pct_N
**Formula:** `std(close - markClose, n) / close`
**Groups/Categories:** Derivative (D), Normalized (N)
**Form:** Percentage (unbounded, typically 0-0.4%)
**Normalization:** _N (scale-invariant)
**Periods:** 6, 12
**Pros:**
- Captures volatility of divergence between price types
- High values = unstable relationship (may precede liquidations)
- Scale-invariant — normalized by price
- Rare signal may be valuable — tail events matter for risk
**Cons:**
- Very small values (mean 0.019%) → signal may be noise, monitor in validation
**Rationale:** Close and markClose usually track tightly, but instability in their relationship may precede liquidation cascades. Small values don't mean no signal — they mean signal is rare.
**Data Validation (8h BTCUSDT, n=6):**
- Range: 0.00% to 0.37%
- Mean: 0.019%
**Uses Raw:** `RAW_P_close_abs_NN`, `RAW_P_markClose_abs_NN`
**Approved:** 2025-12-20
**Note:** Monitor predictive power in validation — very small values may or may not be useful.

---

## Volatility Regime Features

### N_V_atrPercentile_{n}_rnk_N
**Formula:** `percentile_rank(ATR_t, ATR_{t-n:t})`
**Groups/Categories:** Normalized (N), Volatility (V)
**Form:** Percentile Rank (0-100)
**Normalization:** _N (bounded, scale-invariant)
**Periods:** 21, 42, 63 (1wk, 2wk, 3wk in 8h bars)
**Pros:**
- Bounded 0-100 — well-behaved for ML
- Tells WHERE in distribution (not magnitude) — regime identification
- Different from raw ATR — rank vs level
- Scale-invariant by construction
**Cons:**
- Lookback period affects regime detection → use multiple periods
**Rationale:** Current ATR relative to recent history. "Is volatility high or low compared to recent past?" Bounded regime indicator.
**Data Validation (8h BTCUSDT, n=21):**
- Range: 4.8 to 100.0
- Mean: 49.1 — well-centered as expected
**Uses Raw:** `RAW_P_high_abs_NN`, `RAW_P_low_abs_NN`, `RAW_P_close_abs_NN`
**Approved:** 2025-12-20

### M_N_V_rangeExpansion_{n}_rat_N
**Formula:** `(high - low) / SMA(high - low, n)`
**Groups/Categories:** Momentum (M), Normalized (N), Volatility (V)
**Form:** Ratio (typically 0.5-2.0)
**Normalization:** _N (scale-invariant — ratio)
**Periods:** 6, 12, 21
**Pros:**
- Scale-invariant — ratio to moving average
- >1 = expanding volatility (breakout)
- <1 = contracting volatility (consolidation)
- Captures volatility momentum — is range growing or shrinking?
- Different from atrPercentile — ratio vs rank
**Cons:**
- Single bar in numerator can be noisy → combine with smoothed features
**Rationale:** Range relative to recent average. Identifies volatility expansion (breakouts) and contraction (consolidation).
**Data Validation (8h BTCUSDT, n=6):**
- Range: 0.20 to 3.52
- Mean: 0.99
**Uses Raw:** `RAW_P_high_abs_NN`, `RAW_P_low_abs_NN`
**Approved:** 2025-12-20

### V_volOfVol_{n}_pct_N
**Formula:** `std(V_returnStd_{m}, n)` — standard deviation of rolling volatility
**Groups/Categories:** Volatility (V)
**Form:** Percentage (std of std)
**Normalization:** _N (scale-invariant — derived from normalized feature)
**Periods:** base m=6, rolling n=12
**Pros:**
- Second-order feature — volatility OF volatility
- High = volatile volatility (regime uncertainty)
- Low = stable volatility regime
- Scale-invariant — std of percentage values
**Cons:**
- Second-order features can be noisy → use with first-order features
- Requires V_returnStd as dependency → already in Part 3 ✓
**Rationale:** How stable is the volatility regime? High vol-of-vol indicates regime transitions or uncertainty.
**Academic Support:** Volatility clustering literature
**Data Validation (8h BTCUSDT, m=6, n=12):**
- Range: 0.037% to 2.55%
- Mean: 0.44%
**Uses Raw:** Derived from `V_returnStd_{n}_pct_N`
**Approved:** 2025-12-20

### D_N_premiumRange_rat_N
**Formula:** `(premiumHigh - premiumLow) / atrPct(n)`
**Groups/Categories:** Derivative (D), Normalized (N)
**Form:** Ratio (typically 0-0.5)
**Normalization:** _N (scale-invariant — ratio)
**Periods:** Uses atrPct_6 for normalization
**Pros:**
- Captures intraperiod premium volatility — arbitrage instability
- Normalized by price volatility (atrPct) — not absolute premium
- Well-bounded after formula fix
- Scale-invariant
**Cons:**
- Premium can be noisy → smoothed features may help
**Rationale:** Premium range relative to price volatility. High values = unstable arbitrage conditions relative to market movement.
**Data Validation (8h BTCUSDT, using atrPct_6):**
- Range: 0.00 to 0.32
- Mean: 0.018
**Uses Raw:** `RAW_D_F_S_premiumHigh_pct_N`, `RAW_D_F_S_premiumLow_pct_N`, `V_atrPct_{n}_pct_N`
**Approved:** 2025-12-20
**Note:** Formula changed from original `/ |premiumClose|` which caused division-by-zero when premiumClose ≈ 0 (2.5% of data). Now uses atrPct for stable normalization.

---

## Distribution Shape Features

### V_skew_{n}_rat_N
**Formula:** `returns.rolling(n).skew()` where `returns = ln(close_t / close_{t-1})`
**Groups/Categories:** Volatility (V)
**Form:** Ratio (unbounded, typically -3 to +3)
**Normalization:** _N (scale-invariant — computed on returns)
**Periods:** 6, 12, 21, 42 (2d, 4d, 1wk, 2wk)
**Pros:**
- Captures distribution asymmetry — negative skew = crash risk, positive = momentum
- Regime indicator — skew changes precede volatility regime shifts
- Proven predictor in crypto markets
- Unique signal — no existing feature captures 3rd moment
**Cons:**
- Unbounded → clip at ±5 for extreme cases
- Needs sufficient window for statistical validity (min ~20 observations)
**Rationale:** Third moment of returns distribution; captures crash risk vs momentum asymmetry
**Academic Support:**
- Kraus & Litzenberger (1976) "Skewness Preference and Portfolio Choice" [JSTOR](https://www.jstor.org/stable/2326930)
- Harvey & Siddique (2000) "Conditional Skewness in Asset Pricing" [paper](https://doi.org/10.1111/0022-1082.00247)
- Amaya et al. (2015) "Realized volatility, skewness, and kurtosis in stock returns" [paper](https://doi.org/10.1016/j.jempfin.2015.03.016)
**Uses Raw:** `RAW_P_close_abs_NN`
**Approved:** 2025-12-21

### V_kurtosis_{n}_rat_N
**Formula:** `returns.rolling(n).kurt()` (excess kurtosis, normal = 0)
**Groups/Categories:** Volatility (V)
**Form:** Ratio (unbounded, typically 0 to 10 for financial returns)
**Normalization:** _N (scale-invariant — computed on returns)
**Periods:** 6, 12, 21, 42 (2d, 4d, 1wk, 2wk)
**Pros:**
- Captures tail risk — high kurtosis = fat tails = extreme events likely
- Combined with skew forms complete distribution picture
- Regime indicator — kurtosis spikes during volatility events
**Cons:**
- Unbounded → log-transform recommended, then clip
- Needs sufficient window for statistical validity
**Rationale:** Fourth moment of returns distribution; captures tail risk regime
**Academic Support:**
- Harvey & Siddique (2000) "Conditional Skewness in Asset Pricing"
- Amaya et al. (2015) "Realized volatility, skewness, and kurtosis in stock returns"
- Jondeau & Rockinger (2003) "Conditional Volatility, Skewness, and Kurtosis" [paper](https://doi.org/10.1016/S0304-405X(03)00148-6)
**Uses Raw:** `RAW_P_close_abs_NN`
**Approved:** 2025-12-21

---

## Risk Management Features

### V_maxDrawdown_{n}_pct_N
**Formula:** `(close_t - max(close_{t-n:t})) / max(close_{t-n:t})`
**Groups/Categories:** Volatility (V)
**Form:** Percentage (bounded [-1, 0])
**Normalization:** _N (scale-invariant)
**Periods:** 6, 12, 21, 42 (2d, 4d, 1wk, 2wk)
**Pros:**
- Bounded [-1, 0] — well-behaved for ML
- Captures "pain" — asymmetric downside focus distinct from symmetric volatility
- Position within drawdown matters for mean reversion
**Cons:**
- None significant — bounded and scale-invariant by construction
**Rationale:** Asymmetric downside risk measure; captures position within recent decline
**Academic Support:**
- Magdon-Ismail & Atiya (2004) "Maximum Drawdown" [paper](https://doi.org/10.1080/14697680400000023)
- Chekhlov et al. (2005) "Drawdown Measure in Portfolio Optimization" [paper](https://doi.org/10.1142/S0219024905003001)
**Uses Raw:** `RAW_P_close_abs_NN`
**Approved:** 2025-12-21

### M_V_sharpe_{n}_rat_N
**Formula:** `mean(returns, n) / std(returns, n)` (annualization-free)
**Groups/Categories:** Momentum (M), Volatility (V)
**Form:** Ratio (unbounded, typically -3 to +3)
**Normalization:** _N (scale-invariant)
**Periods:** 6, 12, 21, 42 (2d, 4d, 1wk, 2wk)
**Pros:**
- Risk-adjusted momentum — quality not just magnitude
- Combines return and volatility into single signal
- Industry standard metric
**Cons:**
- Unbounded → clip outliers at ±5
- Division by std can be unstable when std → 0 → add small epsilon
**Rationale:** Risk-adjusted momentum signal; captures efficiency of recent returns
**Academic Support:**
- Sharpe (1994) "The Sharpe Ratio" [paper](https://doi.org/10.2469/faj.v50.n1.66)
- Lo (2002) "The Statistics of Sharpe Ratios" [paper](https://doi.org/10.2469/faj.v58.n4.2453)
**Uses Raw:** `RAW_P_close_abs_NN`
**Edge Case:** If `std < 1e-8`, return 0 (no movement = no signal)
**Approved:** 2025-12-21

### M_V_sortino_{n}_rat_N
**Formula:** `mean(returns, n) / downside_std(returns, n)` where `downside_std = std(returns[returns < 0])`
**Groups/Categories:** Momentum (M), Volatility (V)
**Form:** Ratio (unbounded, typically -3 to +5)
**Normalization:** _N (scale-invariant)
**Periods:** 6, 12, 21, 42 (2d, 4d, 1wk, 2wk)
**Pros:**
- Downside-risk-adjusted — only penalizes negative volatility
- More relevant for trading than Sharpe (asymmetric preferences)
- Academic consensus: Sortino > Sharpe for asymmetric returns
**Cons:**
- Unbounded → clip outliers
- Needs negative returns in window for denominator → edge case handling
**Rationale:** Downside-risk-adjusted momentum; penalizes only bad volatility
**Academic Support:**
- Sortino & Price (1994) "Performance Measurement in a Downside Risk Framework" [paper](https://doi.org/10.3905/jpm.1994.409480)
- Sortino & van der Meer (1991) "Downside Risk" [paper](https://doi.org/10.3905/jpm.1991.409343)
**Uses Raw:** `RAW_P_close_abs_NN`
**Edge Case:** If no negative returns in window, use Sharpe formula (full std)
**Approved:** 2025-12-21

### M_V_calmar_{n}_rat_N
**Formula:** `(close_t / close_{t-n} - 1) / abs(maxDrawdown_n)` = cumulative return / |MDD|
**Groups/Categories:** Momentum (M), Volatility (V)
**Form:** Ratio (unbounded, typically -10 to +10)
**Normalization:** _N (scale-invariant)
**Periods:** 12, 21, 42 (needs longer windows for meaningful drawdown)
**Pros:**
- Drawdown-adjusted return — different risk perspective than volatility
- Return per unit of pain
- Commonly used in fund evaluation
**Cons:**
- Unbounded → clip outliers
- MDD can be very small (all-up periods) → add epsilon
**Rationale:** Return efficiency relative to maximum pain experienced
**Academic Support:**
- Young (1991) "Calmar Ratio: A Smoother Tool" [Futures Magazine](https://www.futuresmag.com/)
- Eling & Schuhmacher (2007) "Does the Choice of Performance Measure Influence Evaluation?" [paper](https://doi.org/10.1016/j.jbankfin.2006.12.004)
**Uses Raw:** `RAW_P_close_abs_NN`
**Edge Case:** If `|MDD| < 1e-6`, return sign(cumReturn) * 10 (cap at extreme)
**Approved:** 2025-12-21

---

## Regime Detection Features

### V_autocorr_{n}_bnd_N
**Formula:** `corr(returns_t, returns_{t-1})` over rolling window n
**Groups/Categories:** Volatility (V)
**Form:** Bounded [-1, +1] by definition (correlation coefficient)
**Normalization:** _N (scale-invariant)
**Periods:** 6, 12, 21, 42 (2d, 4d, 1wk, 2wk)
**Pros:**
- Bounded [-1, +1] — perfect for ML
- Regime indicator — positive = trending, negative = mean-reverting
- Critical for strategy selection (momentum vs mean-reversion)
**Cons:**
- Noisy at short windows → use n ≥ 6
**Rationale:** Return persistence indicator; identifies trending vs mean-reverting regimes
**Academic Support:**
- Lo & MacKinlay (1988) "Stock Market Prices Do Not Follow Random Walks" [paper](https://doi.org/10.1093/rfs/1.1.41)
- Campbell et al. (1997) "The Econometrics of Financial Markets" [book](https://press.princeton.edu/books/hardcover/9780691043012)
**Uses Raw:** `RAW_P_close_abs_NN`
**Approved:** 2025-12-21

### N_P_zScore_{n}_zsc_N
**Formula:** `(close_t - SMA(close, n)) / std(close, n)`
**Groups/Categories:** Normalized (N), Price (P)
**Form:** Z-score (unbounded, typically -3 to +3)
**Normalization:** _N (standardized by construction)
**Periods:** 6, 12, 21, 42 (2d, 4d, 1wk, 2wk)
**Pros:**
- Pure statistical deviation — foundation for mean-reversion
- Already standardized — comparable across assets/periods
- Well-behaved — approximately normal
**Cons:**
- Similar concept to priceSmaDeviation but different normalization
**Rationale:** Statistical deviation from mean; mean-reversion signal
**Academic Support:**
- Avellaneda & Lee (2010) "Statistical Arbitrage in the US Equities Market" [paper](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1032305)
- Gatev et al. (2006) "Pairs Trading" [paper](https://doi.org/10.1093/rfs/hhj020)
**Uses Raw:** `RAW_P_close_abs_NN`
**Note:** Distinct from `N_P_T_priceSmaDeviation_{n}_pct_N` — this uses std normalization (z-score), that uses SMA normalization (percentage)
**Approved:** 2025-12-21

---

## Momentum Quality Features

### V_volMomentum_{n}_pct_N
**Formula:** `(std(returns, m) / std(returns, m).shift(n)) - 1` where m = n/2 (inner vol window)
**Groups/Categories:** Volatility (V)
**Form:** Percentage (unbounded)
**Normalization:** _N (ratio of same-scale quantities)
**Periods:** 6, 12, 21 (with inner window m = 3, 6, 10)
**Pros:**
- Captures volatility regime transitions — expansion vs contraction
- Different from rangeExpansion — this is close-to-close vol, that is ATR-based
- Leads price breakouts — volatility compression precedes moves
**Cons:**
- Unbounded → clip outliers
- Two windows to define (inner vol + comparison lag)
**Rationale:** Volatility momentum; identifies vol regime transitions
**Academic Support:**
- GARCH literature: Bollerslev (1986) [paper](https://doi.org/10.1016/0304-4076(86)90063-1)
- Poon & Granger (2003) "Forecasting Volatility in Financial Markets" [paper](https://doi.org/10.1257/002205103765762743)
**Uses Raw:** `RAW_P_close_abs_NN`
**Approved:** 2025-12-21

### B_consecutiveUp_bnd_N
**Formula:** Count consecutive periods where `return > 0`, normalized by cap (10)
**Groups/Categories:** Binary/Count (B)
**Form:** Bounded [0, 1] (count/10)
**Normalization:** _N (normalized by cap)
**Cap:** 10 periods (streak > 10 = 1.0)
**Pros:**
- Bounded [0, 1] — well-behaved
- Streak detection — long up streaks may mean-revert
- Behavioral signal — gambler's fallacy studies
**Cons:**
- Loses information above cap → acceptable (rare)
**Rationale:** Up streak counter; momentum persistence indicator
**Academic Support:**
- Rabin (2002) "Inference by Believers in the Law of Small Numbers" [paper](https://doi.org/10.1162/003355302760193896)
- Behavioral finance literature on hot hand fallacy
**Uses Raw:** `RAW_P_close_abs_NN`
**Approved:** 2025-12-21

### B_consecutiveDown_bnd_N
**Formula:** Count consecutive periods where `return < 0`, normalized by cap (10)
**Groups/Categories:** Binary/Count (B)
**Form:** Bounded [0, 1] (count/10)
**Normalization:** _N (normalized by cap)
**Cap:** 10 periods
**Pros:**
- Bounded [0, 1] — well-behaved
- Down streak detection — capitulation signal
- Behavioral signal
**Cons:**
- Same as consecutiveUp
**Rationale:** Down streak counter; capitulation indicator
**Academic Support:**
- Same as consecutiveUp
**Uses Raw:** `RAW_P_close_abs_NN`
**Approved:** 2025-12-21

### M_winRate_{n}_bnd_N
**Formula:** `sum(returns > 0) / n` over rolling window
**Groups/Categories:** Momentum (M)
**Form:** Bounded [0, 1] (proportion)
**Normalization:** _N (proportion is scale-invariant)
**Periods:** 6, 12, 21, 42 (2d, 4d, 1wk, 2wk)
**Pros:**
- Bounded [0, 1] — perfect for ML
- Momentum quality decomposition — frequency vs magnitude
- Intuitive interpretation — "what % of periods were positive"
**Cons:**
- Ignores magnitude → pair with avgWin/avgLoss if needed
**Rationale:** Win frequency; momentum quality indicator
**Academic Support:**
- Standard momentum decomposition in trading systems
- Thaler & Johnson (1990) "Gambling with House Money" [paper](https://doi.org/10.1287/mnsc.36.6.643)
**Uses Raw:** `RAW_P_close_abs_NN`
**Approved:** 2025-12-21

---

## Volume-Price Analysis Features

### L_M_S_obv_{n}_zsc_N
**Formula:** 
```
OBV_t = OBV_{t-1} + sign(close_t - close_{t-1}) × volume_t
OBV_normalized = (OBV - OBV.rolling(n).mean()) / OBV.rolling(n).std()
```
**Groups/Categories:** Liquidity (L), Momentum (M), Sentiment (S)
**Form:** Z-score (unbounded, ~normal distribution)
**Normalization:** _N (z-score makes it scale-invariant)
**Periods:** 6, 12, 21, 42 (2d, 4d, 1wk, 2wk)
**Pros:**
- Volume precedes price — classic Granville principle
- Accumulation/distribution detection
- Identifies divergences (price up, OBV down = weak rally)
- Proven in crypto trading literature
**Cons:**
- Cumulative — raw OBV is non-stationary, but z-score normalization fixes this
**Rationale:** Cumulative volume direction; identifies smart money accumulation/distribution
**Academic Support:**
- Granville (1963) "New Key to Stock Market Profits" [book](https://www.amazon.com/Granvilles-Stock-Market-Profits/dp/0137078686)
- arXiv 2024 - Bitcoin ML features paper lists OBV as standard feature
**Uses Raw:** `RAW_P_close_abs_NN`, `RAW_L_volume_abs_NN`
**Approved:** 2025-12-21

### L_M_S_mfi_{n}_bnd_N
**Formula:**
```
TypicalPrice = (high + low + close) / 3
RawMoneyFlow = TypicalPrice × volume
PositiveMF = sum(RMF where TP > TP_{t-1}, n periods)
NegativeMF = sum(RMF where TP < TP_{t-1}, n periods)
MoneyRatio = PositiveMF / NegativeMF
MFI = 100 - (100 / (1 + MoneyRatio))
```
**Groups/Categories:** Liquidity (L), Momentum (M), Sentiment (S)
**Form:** Bounded [0, 100]
**Normalization:** _N (bounded by construction)
**Periods:** 6, 12, 21 (2d, 4d, 1wk)
**Pros:**
- "Volume-weighted RSI" — RSI with volume confirmation
- Bounded 0-100 — well-behaved for ML
- Identifies overbought/oversold with volume conviction
- Leading indicator (volume-based)
**Cons:**
- Requires high/low — but we have them
**Rationale:** Volume-weighted momentum oscillator; RSI with volume conviction
**Academic Support:**
- Quong & Soudack (1989) — MFI creators
- arXiv 2024 - Bitcoin ML features paper includes MFI
**Uses Raw:** `RAW_P_high_abs_NN`, `RAW_P_low_abs_NN`, `RAW_P_close_abs_NN`, `RAW_L_volume_abs_NN`
**Approved:** 2025-12-21

### L_M_S_cmf_{n}_bnd_N
**Formula:**
```
MoneyFlowMultiplier = ((close - low) - (high - close)) / (high - low)
MoneyFlowVolume = MoneyFlowMultiplier × volume
CMF = sum(MoneyFlowVolume, n) / sum(volume, n)
```
**Groups/Categories:** Liquidity (L), Momentum (M), Sentiment (S)
**Form:** Bounded [-1, +1]
**Normalization:** _N (bounded by construction)
**Periods:** 6, 12, 21 (2d, 4d, 1wk)
**Pros:**
- Bounded [-1, +1] — perfect for ML
- Close position within bar × volume — buying vs selling pressure
- Different from MFI — measures where close is within H-L range
**Cons:**
- Can be zero when high = low (rare) → handle edge case
**Rationale:** Volume-weighted close position; measures buying vs selling pressure
**Academic Support:**
- Chaikin, Marc (1980s) — CMF creator
- arXiv 2024 - Bitcoin ML features paper includes CMF
**Uses Raw:** `RAW_P_high_abs_NN`, `RAW_P_low_abs_NN`, `RAW_P_close_abs_NN`, `RAW_L_volume_abs_NN`
**Edge Case:** If `high == low`, set multiplier = 0
**Approved:** 2025-12-21

---

## Trend Strength Features

### M_T_V_adx_{n}_bnd_N
**Formula:**
```
+DM = max(high_t - high_{t-1}, 0) if (high_t - high_{t-1}) > (low_{t-1} - low_t) else 0
-DM = max(low_{t-1} - low_t, 0) if (low_{t-1} - low_t) > (high_t - high_{t-1}) else 0
TR = max(high - low, |high - close_{t-1}|, |low - close_{t-1}|)
+DI = 100 × smoothed(+DM, n) / smoothed(TR, n)
-DI = 100 × smoothed(-DM, n) / smoothed(TR, n)
DX = 100 × |+DI - -DI| / (+DI + -DI)
ADX = smoothed(DX, n)
```
**Groups/Categories:** Momentum (M), Trend (T), Volatility (V)
**Form:** Bounded [0, 100]
**Normalization:** _N (bounded by construction)
**Periods:** 6, 12 (2d, 4d)
**Pros:**
- Bounded 0-100 — perfect for ML
- Direction-agnostic trend strength — doesn't care if up or down
- Wilder smoothing reduces noise
- <20 = no trend, 25-50 = strong trend, >50 = very strong
**Cons:**
- Lagging (smoothed) → accepted tradeoff
- Complex calculation → but standard
**Rationale:** Trend strength regardless of direction; identifies trending vs ranging markets
**Academic Support:**
- Wilder (1978) "New Concepts in Technical Trading Systems" [book](https://www.amazon.com/dp/0894590278) — ADX creator
**Uses Raw:** `RAW_P_high_abs_NN`, `RAW_P_low_abs_NN`, `RAW_P_close_abs_NN`
**Approved:** 2025-12-21

### M_T_V_diDiff_{n}_bnd_N
**Formula:** `(+DI - -DI) / 100` (from ADX calculation above)
**Groups/Categories:** Momentum (M), Trend (T), Volatility (V)
**Form:** Bounded [-1, +1]
**Normalization:** _N (normalized by 100)
**Periods:** 6, 12 (2d, 4d)
**Pros:**
- Bounded [-1, +1] — well-behaved
- Direction signal — positive = bullish trend, negative = bearish
- Complements ADX (strength) with direction
**Cons:**
- Derived from same calculation as ADX
**Rationale:** Trend direction signal; bullish vs bearish with magnitude
**Academic Support:**
- Wilder (1978) — same as ADX
**Uses Raw:** `RAW_P_high_abs_NN`, `RAW_P_low_abs_NN`, `RAW_P_close_abs_NN`
**Approved:** 2025-12-21

### N_M_cci_{n}_zsc_N
**Formula:**
```
TypicalPrice = (high + low + close) / 3
SMA_TP = SMA(TypicalPrice, n)
MeanDeviation = mean(|TypicalPrice - SMA_TP|, n)
CCI = (TypicalPrice - SMA_TP) / (0.015 × MeanDeviation)
```
**Groups/Categories:** Normalized (N), Momentum (M)
**Form:** Z-score-like (unbounded, typically -200 to +200)
**Normalization:** _N (deviation-normalized)
**Periods:** 6, 12, 21 (2d, 4d, 1wk)
**Pros:**
- Mean-reversion signal — >100 overbought, <-100 oversold
- Uses mean deviation (more robust than std)
- Classic indicator with proven track record
**Cons:**
- Unbounded → clip at ±300
**Rationale:** Deviation from statistical mean; overbought/oversold signal
**Academic Support:**
- Lambert, Donald (1980) "Commodity Channel Index" [Commodities Magazine]
- arXiv 2024 - Bitcoin ML features paper lists CCI
**Uses Raw:** `RAW_P_high_abs_NN`, `RAW_P_low_abs_NN`, `RAW_P_close_abs_NN`
**Approved:** 2025-12-21

---

## Perpetual-Specific Composite Features

### L_S_oiVolumeRatio_{n}_rat_N
**Formula:** `openInterest / SMA(volume, n)`
**Groups/Categories:** Liquidity (L), Sentiment (S)
**Form:** Ratio (unbounded, typically 0.5 to 50)
**Normalization:** _N (ratio is scale-invariant)
**Periods:** 6, 12, 21 (2d, 4d, 1wk)
**Pros:**
- Leverage indicator — high ratio = positions held longer (more conviction)
- Low ratio = high turnover (day trading / scalping dominant)
- Perpetual-specific insight
**Cons:**
- Unbounded → log-transform or standardize
**Rationale:** Position commitment vs trading activity; conviction indicator
**Academic Support:**
- Ledger Journal 2024 - "Reconciling Open Interest with Traded Volume in Perpetuals" [paper](https://ledgerjournal.org/ojs/ledger/article/view/325/265)
- CME Group education materials on OI/Volume analysis
**Uses Raw:** `RAW_L_S_openInterest_abs_NN`, `RAW_L_volume_abs_NN`
**Note:** Related but distinct from `L_N_volOiRatio_rat_N` (which is volume/OI without smoothing). This is OI/SMA(volume) — different perspective (conviction vs turnover).
**Approved:** 2025-12-21

---

## Cross-References

- **Naming convention:** [Part 0: Convention](Part_0_Convention.md#naming-convention)
- **Groups/Categories explained:** [Part 1: Groups](Part_1_Groups.md)
- **Form suffixes explained:** [Part 1: Form Suffixes](Part_1_Groups.md#form-suffixes-representation-type)
- **Raw features (dependencies):** [Part 2: Raw](Part_2_Raw.md)
- **Suggestions to review:** [Part 4: Suggestions](Part_4_Suggestions.md)
- **Rejected features:** [Part 5: Disapproved](Part_5_Disapproved.md)

---

## Approval Process

Per [Part 0: Process](Part_0_Convention.md#process):

1. New feature ideas go to Part 4 as suggestions with proposed group/category assignments
2. We discuss usefulness, group/category assignments, and potential conflicts
3. Only after mutual agreement, feature moves here (Part 3)
4. If not approved, feature moves to [Part 5: Disapproved](Part_5_Disapproved.md) with reasoning

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
