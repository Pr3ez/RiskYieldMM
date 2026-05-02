# Part 1: Feature Group/Category Definitions

> **Navigation:** [README](README.md) | [Part 0: Convention](Part_0_Convention.md) | **Part 1: Groups** | [Part 2: Raw](Part_2_Raw.md) | [Part 3: Approved](Part_3_Approved.md) | [Part 3 (2)](Part_3_Approved2.md) | [Part 4: Suggestions](Part_4_Suggestions.md) | [Part 5: Disapproved](Part_5_Disapproved.md)

---

## Group/Category Taxonomy

Each group/category provides unique context from either financial or ML perspective (or both). Features can belong to multiple groups/categories—all relevant ones are included to maximize information.

**Principle: Maximal grouping.** Include ALL groups that apply. More context = more options later. Only omit a group if it's truly redundant (same meaning as another group + suffix combined).

### B — Binary/Categorical
**Financial Context:** Discrete market states, regime indicators, flags.
**ML Pattern Type:** Classification signals, conditional splits, state identification.
**What Models Learn:** Decision boundaries, regime-dependent behavior, categorical effects.
**Examples:** Bullish/bearish direction, weekend flag, funding sign.

### C — Candlestick/Shape
**Financial Context:** Price action patterns within single period, conviction signals.
**ML Pattern Type:** Local spatial structure, shape-based features.
**What Models Learn:** Buying/selling pressure, indecision vs. conviction, reversal patterns.
**Examples:** Body size ratio, upper/lower shadow ratios.

### D — Derivative/Spread
**Financial Context:** Relative value between related instruments, arbitrage signals.
**ML Pattern Type:** Relational features, convergence/divergence dynamics.
**What Models Learn:** Mispricing opportunities, mean-reversion targets, cross-instrument relationships.
**Examples:** Basis (futures-spot), mark-index spread, premium index.

### F — Funding/Perpetual
**Financial Context:** Unique perpetual futures mechanics not found elsewhere.
**ML Pattern Type:** Domain-specific signals, instrument-characteristic features.
**What Models Learn:** Arbitrage dynamics, cost of leverage, perpetual-specific patterns.
**Examples:** Funding rate, funding cumulative, premium.

### I — Interest/Cost
**Financial Context:** Financing cost, cost of carry, rate-like economics.
**ML Pattern Type:** Cost signals, carry-adjusted features.
**What Models Learn:** Economic cost of positions, carry trade opportunities, cost-adjusted returns.
**Examples:** Funding rate as borrowing cost, cumulative funding as total carry.

### L — Liquidity/Volume
**Financial Context:** Market participation, trading activity intensity.
**ML Pattern Type:** Activity/intensity features, participation signals.
**What Models Learn:** Conviction behind moves, speculative vs. holding behavior, liquidity conditions.
**Examples:** Volume, turnover, open interest, vol/OI ratio.

### M — Momentum
**Financial Context:** Velocity and rate of price change (first derivative concept).
**ML Pattern Type:** Rate signals, leading indicators.
**What Models Learn:** Acceleration/deceleration, trend strength, potential reversals (momentum divergence).
**Examples:** ROC, MOM, MACD histogram, log returns.

### N — Normalized/Scaled
**Financial Context:** Scale-invariant representations for cross-time/cross-asset comparison.
**ML Pattern Type:** Bounded features, z-scores, percentiles.
**What Models Learn:** Relative extremes, comparable signals across different scales/periods.
**Examples:** Z-scores, %B, percentage-based features, ratios.

### P — Price
**Financial Context:** All price-related data — raw prices, returns, changes, transformations.
**ML Pattern Type:** Level features, base signals, stationary transformations.
**What Models Learn:** Support/resistance, period-over-period movement, base for other calculations.
**Examples:** OHLC, mark price, index price, log returns, percentage change, SMA, EMA.

### S — Sentiment/Positioning
**Financial Context:** Proxy for market crowd behavior, long/short positioning.
**ML Pattern Type:** Contrarian signals, crowd behavior indicators.
**What Models Learn:** Crowded trades (reversal risk), positioning extremes, market consensus.
**Examples:** Funding sign/level, OI changes, premium direction.

### T — Trend/Smoothed
**Financial Context:** Sustained directional movement, noise-filtered signals.
**ML Pattern Type:** Lagged/smoothed features, trend identification.
**What Models Learn:** Direction persistence, noise filtering, trend-following signals.
**Examples:** SMA, EMA, MACD signal line.

### TM — Temporal/Cyclical
**Financial Context:** Time-based patterns, calendar effects, periodic events.
**ML Pattern Type:** Seasonality, cyclical encodings, periodic features.
**What Models Learn:** Recurring patterns, time-of-day/week effects, event timing.
**Examples:** Day of week, funding cycle position, hour of day.

### V — Volatility/Risk
**Financial Context:** Price dispersion, uncertainty, risk regime.
**ML Pattern Type:** Second derivative concept, variance features.
**What Models Learn:** Risk environment, volatility clustering, regime identification.
**Examples:** ATR, rolling std, Bollinger bandwidth.

### W — Weighted/Composite
**Financial Context:** Combined signals with explicit weighting scheme.
**ML Pattern Type:** Interaction features, multi-signal composites.
**What Models Learn:** Signal interactions, weighted importance, combined effects.
**Examples:** OI-weighted returns, volume-weighted price.

---

## Group/Category Quick Reference

| Prefix | Name | Primary Lens | Key Insight |
|--------|------|--------------|-------------|
| B | Binary/Categorical | ML | Discrete states for splitting |
| C | Candlestick/Shape | Finance + ML | Local structure, conviction |
| D | Derivative/Spread | Finance | Arbitrage, relative value |
| F | Funding/Perpetual | Finance | Domain-specific alpha |
| I | Interest/Cost | Finance | Cost of carry |
| L | Liquidity/Volume | Finance | Participation intensity |
| M | Momentum | Finance + ML | Rate of change (1st derivative) |
| N | Normalized/Scaled | ML | Scale-invariant comparison |
| P | Price | Finance | All price-related data |
| S | Sentiment/Positioning | Finance | Crowd behavior proxy |
| T | Trend/Smoothed | Finance + ML | Noise filtering, direction |
| TM | Temporal/Cyclical | ML | Seasonality, periodicity |
| V | Volatility/Risk | Finance + ML | Dispersion (2nd derivative) |
| W | Weighted/Composite | ML | Signal interactions |

---

## Form Suffixes (Representation Type)

Suffixes describe HOW the feature value is represented. This is separate from WHAT the feature means (groups/categories).

**Normalization suffix:** `_N` = Normalized (scale-invariant), `_NN` = Not Normalized (scale-dependent)

| Suffix | Name | Range | Description | Examples |
|--------|------|-------|-------------|----------|
| `_bnd_N` | Bounded | Fixed (0-100, 0-1, -1 to 1) | Constrained by formula design | RSI, %B, stochastic, candlestick ratios |
| `_pct_N` | Percentage | Unbounded (can exceed ±100%) | Percentage but not constrained | ROC, log_return, pct_change |
| `_zsc_N` | Z-Score | Typically -3 to +3 | Standardized (mean=0, std=1) | funding_zscore, premium_zscore |
| `_rat_N` | Ratio | Typically 0 to +∞ | Relationship between two quantities | vol/OI ratio, volume ratio |
| `_abs_NN` | Absolute | Depends on unit | Raw units (price, volume, USD) | SMA, EMA, ATR, volume, OI |
| `_dif_NN` | Difference | Unbounded (same units) | Subtraction of two values | MOM, MACD histogram, OI change |
| `_rnk_N` | Percentile Rank | 0-100 | Position in distribution | ATR percentile |
| `_bin` | Binary/Discrete | Finite set | Discrete states (N/A for normalization) | candle direction, day of week |

**Why this matters:**
- **_N (Normalized):** Scale-invariant, comparable across assets/timeframes, can use directly
- **_NN (Not Normalized):** Scale-dependent, may need additional normalization for some models
- **_bin:** Categorical — requires special handling (one-hot, embedding, etc.)

**Practical notes per suffix:**
- `_bnd_N` features: Can be used directly, natural thresholds exist (e.g., RSI > 70)
- `_pct_N` features: May need clipping for outliers (unbounded percentages)
- `_zsc_N` features: Already standardized, good for cross-feature comparison
- `_rat_N` features: Watch for division edge cases (denominator → 0)
- `_abs_NN` features: Require normalization before most models (different scales)
- `_dif_NN` features: Same units as input, may need scaling
- `_rnk_N` features: Distribution-free, robust to outliers
- `_bin` features: Categorical handling required (one-hot, leave as-is for trees)

---

## Cross-References

- **Naming convention:** [Part 0: Convention](Part_0_Convention.md#naming-convention)
- **Raw features using these groups:** [Part 2: Raw](Part_2_Raw.md)
- **Engineered features:** [Part 3: Approved](Part_3_Approved.md) | [Part 4: Suggestions](Part_4_Suggestions.md)
