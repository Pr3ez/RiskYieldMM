# Meta Model Analyst Indicator Certification

**Date:** 2026-07-12
**Scope:** `Risk_Yield_Meta_Model_Analyst_0_0_1`
**Matrix:** 8 canonical assets x 7 canonical timeframes = 56 selections

## Executive conclusion

The four existing indicator families are now internally causal, numerically
bounded, and explicit about what they can and cannot say. A fifth layer,
**Cross-Timeframe Context**, has been added using closed-bar availability
alignment.

This work does **not** certify universal profitability or universal parameter
optimality. Professional sources support the statistical purpose of CUSUM,
EWMA volatility, forward HMM filtering, and multi-horizon momentum research;
they do not support presenting any one of them as an automatic Buy/Sell rule
for every instrument and bar size. Promotion to trading still requires locked
walk-forward holdouts, realistic costs, and append-only forward-paper evidence.

## Certification matrix

| Layer | What it is allowed to mean | Certification after this work | Remaining limitation |
|---|---|---|---|
| Standardized CUSUM Trend | Sequential candidate shift in the Hull residual; bull/bear regime and trailing reference | Causal, prior-scale, price-scale invariant, no pre-scale trigger, next-bar plotted | Its `k`/`h` presets are chart heuristics, not per-selection average-run-length calibration |
| EWMA Volatility | Expected close-to-close dispersion per observed bar | Exact half-life recursion, price-scale invariant, mature/warming state, next-bar plotted | `% per bar` must not be compared directly across different timeframe durations |
| Volatility-Scaled Trend | Bounded custom directional/path-quality diagnostic | Causal prior-volatility denominator, prefix invariant, bounded `[-1, 1]`, next-bar plotted | Combined formula and thresholds are not a calibrated probability model |
| Prototype Regime | Forward weights under a fixed four-state Gaussian prototype HMM | Forward-only filtering, normalized weights, formal pairwise filtered switch probability | Emissions/transitions are untrained; weights are not empirical probabilities or confidence |
| Cross-Timeframe Context | Closed-bar alignment/conflict/caution across a fixed timeframe map | Backward-as-of on actual availability, including first-seen delay where journaled | Versioned context heuristic, not an entry order or proven performance gate |

## Professional-source comparison

### CUSUM

NIST's tabular two-sided CUSUM accumulates standardized departures from a
reference mean and signals after crossing a decision interval. It is a
sequential mean-shift detector; the reference value and threshold are normally
chosen for a desired shift size and average run length. See the
[NIST CUSUM control-chart reference](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc323.htm)
and [Page (1954)](https://academic.oup.com/biomet/article-abstract/41/1-2/100/456627).

The prior implementation accumulated raw price residuals while substituting an
absolute `0.001` scale before residual volatility existed. That made warm-up
signals depend on whether an instrument traded near `0.001`, `100`, or
`100,000`.

The corrected recurrence is:

```text
z_t   = (close_t - HMA_t) / prior_residual_std_(t-1)
S+_t  = max(0, S+_(t-1) + z_t - k)
S-_t  = max(0, S-_(t-1) - z_t - k)
event = S+_t > h or S-_t > h
```

No pressure is accumulated until the prior residual scale is mature and
numerically non-degenerate. The UI keeps the legacy API labels for snapshot and
optimizer compatibility, but displays their actual bar lengths: 14, 21, and
50 bars. Markers say `CUSUM bull shift` / `CUSUM bear shift`, not Buy / Sell.

### EWMA volatility

The implementation follows the RiskMetrics-style variance recursion:

```text
lambda(H) = exp(-log(2) / H)
v_t       = lambda * v_(t-1) + (1 - lambda) * r_t^2
sigma_t   = sqrt(v_t)
```

See the [MSCI RiskMetrics Technical Document](https://www.msci.com/research-and-insights/paper/1996-riskmetrics-technical-document).
The Analyst uses log close-to-close returns and half-lives of 12, 48, and 192
**observed bars**. It does not silently annualize them or transplant a daily
decay to intraday bars.

The seed from the first valid squared return is now visible through a maturity
contract. `10 x 192 = 1,920` return observations leave less than 0.1% of the
initial variance weight. `Expanding >= 1.20x` and `Contracting <= 0.85x`
fast/slow ratios remain explicitly versioned chart heuristics.

### Volatility-scaled trend

Moskowitz, Ooi, and Pedersen document time-series momentum across many futures
and forwards, mainly at one-to-twelve-month horizons. That supports testing
multi-horizon own-return direction, but it does not prove minute-bar alpha. See
[Time Series Momentum](https://pages.stern.nyu.edu/~lpederse/papers/TimeSeriesMomentum.pdf).

The Analyst's exact combination is custom:

```text
component_h = path_efficiency_h * tanh(vol_scaled_net_return_h / 2)
score       = mean(component_12, component_48, component_192)
```

The denominator is prior EWMA volatility. Every component remains in `[-1, 1]`;
path quality remains in `[0, 1]`. The layer is a directional-quality diagnostic,
not probability or calibrated expected return.

### Prototype HMM / regime

Rabiner's forward recursion and Hamilton's nonlinear filter support causal
latent-state inference. Forward-backward smoothing and full-sequence decoding
use later observations and are forbidden in a prediction-time layer. See
[Rabiner (1989)](https://doi.org/10.1109/5.18626) and
[Hamilton (1989)](https://doi.org/10.2307/1912559).

The code uses only a one-step forward filter. This audit additionally replaced
posterior total-variation change with the formal filtered pairwise switch mass:

```text
P(S_t != S_(t-1) | y_1:t)
  = sum_(i != j) normalized[p_(t-1,i) * A_ij * likelihood_j(y_t)]
```

The displayed `change caution` is the maximum of that switch mass and the
weight of the explicit transition prototype. It remains a heuristic because
all emission means, variances, transition probabilities, and initial weights
are fixed defaults. It no longer vetoes replay/paper execution by default. An
optimizer may test it only through the explicit
`enable_experimental_prototype_regime_gate` ablation.

The matrix audit found mean top prototype weights of roughly 92.1% to 98.4%
depending on selection. That concentration is why the UI consistently says
`prototype weight`, never confidence or calibrated probability.

## Cross-timeframe contract

The first additional layer is a context matrix, not another oscillator. Its
mapping is frozen before performance testing:

| Chart timeframe | Primary context | Macro context |
|---|---|---|
| 1m | 15m | 1h |
| 15m | 1h | 4h |
| 1h | 4h | 1d |
| 4h | 8h | 1d |
| 8h | 12h | 1d |
| 12h | 1d | - |
| 1d | - | - |

For source timeframe `H` and active decision time `D`:

```text
scheduled_close = source_bar_open + H
available_at     = max(scheduled_close, first_seen_at when journaled)
selected_value  = latest value with available_at <= D
```

The alignment is backward-as-of. A forming higher-timeframe candle can never be
selected. The 1d chart says `No higher canonical timeframe`; it does not invent
weekly context. The matrix reports current, primary, and macro rows with trend,
path quality, within-timeframe EWMA ratio, untrained prototype weight, formal
filtered switch probability, heuristic caution, and exact availability age.

The context classes are descriptive:

- `trend_aligned`
- `countertrend_conflict`
- `range_context`
- `transition_risk`
- `insufficient_or_stale`

They do not independently mean open long, open short, or mean-revert.

## 56-selection numerical audit

The audit replayed up to 2,000 recent canonical bars for every selection.

```text
Selections:                  56
Bars inspected:             110,258
Numerical/contract issues:  0
CUSUM shift candidates:     4,868
Trend starts:               1,945
Prototype-risk starts:      1,367
```

Observed per-selection ranges:

| Diagnostic | Minimum | Median | Maximum |
|---|---:|---:|---:|
| CUSUM events / 1,000 scale-ready bars | 38.344 | 44.990 | 51.125 |
| Trend starts / 1,000 scale-ready bars | 6.646 | 18.149 | 34.254 |
| Prototype-risk starts / 1,000 scale-ready bars | 2.045 | 12.270 | 29.141 |
| Mean top prototype weight | 0.9210 | 0.9529 | 0.9836 |
| Mean filtered switch probability | 0.0123 | 0.0311 | 0.0501 |
| Mean change-caution heuristic | 0.0505 | 0.1639 | 0.2976 |
| Occupied prototype states | 2 | 3 | 4 |

The checks covered finite values, CUSUM band ordering, no pre-scale CUSUM
event, price-scale invariance, bounded trend/quality/risk outputs, weights
summing to one, exact next-bar timestamps, batch/stream parity, prefix
invariance, and causal cross-timeframe availability for all 56 selections.

These are implementation certifications, not predictive-value or profitability
metrics.

## UI and chart corrections

- The initial viewport now shows the latest 240 bars while retaining up to
  5,000 loaded bars for scrolling.
- CUSUM/EWMA values are plotted at earliest next-bar action time.
- CUSUM, trend, and prototype events are analytically named; Buy/Sell remains
  reserved for simulated fills.
- Legend colors match rendered series and the trend score is high-contrast.
- Trend and prototype panes have fixed `[-1, 1]` and `[0, 1]` scale contracts.
- Canonical instrument display precision replaces the forced four-decimal
  formatting that produced values such as `64123.1000` for BTC.
- Crosshair output now includes CUSUM bands/trail and all three EWMA values.
- The Cross-TF matrix is a compact table instead of six additional chart panes.
- The mobile chart height scales with active panes, the legend scrolls
  horizontally, and source freshness remains visible.
- Each layer has an in-product guide with purpose, units, timing, and limitation.

## What should be implemented next

Ranked by likely incremental decision value and data integrity:

1. **Prior structure and available room**: prior-only rolling channel,
   previous-session high/low, channel position, and upside/downside room in
   volatility units. This helps distinguish breakout, continuation, rejection,
   and poor reward-to-risk location.
2. **Comparable volatility state**: within-asset/timeframe volatility
   percentile plus range-based volatility. Parkinson and Yang-Zhang are useful
   references, but session assumptions must be respected. See
   [Parkinson (1980)](https://doi.org/10.1086/296071) and
   [Yang and Zhang (2000)](https://ideas.repec.org/a/ucp/jnlbus/v73y2000i3p477-91.html).
3. **Seasonality-adjusted participation**: relative-volume percentile/z-score
   conditioned on asset, timeframe, and session phase. Candle-signed volume
   must remain labelled a proxy, not true order flow.
4. **Bayesian online change-point detection**: causal run-length posterior,
   change probability, and surprise, with no direction claim. See
   [Adams and MacKay](https://arxiv.org/abs/0710.3742).
5. **Crypto-only derivatives context**: funding, mark/index premium, and open
   interest change as crowding/carry context, never as automatic direction.
6. **Locked cross-asset research**: pair-specific relative strength/correlation
   for BTC/ETH and ES/NQ, then breadth only after availability/calendar audit.

Do not add more RSI/MACD/Stochastic/ADX copies before measuring whether the
families already materialized elsewhere in the repository add incremental
out-of-sample value.

## Optimization and promotion gate

The repository's optimizer remains the correct place for parameter selection:

- fixed, predeclared 24-candidate grid;
- expanding chronological development folds;
- latest 20% untouched holdout;
- doubled-cost selection objective;
- minimum fill and drawdown constraints;
- final normal-cost replay only after selection;
- append-only trial registry; and
- mandatory forward paper before any real routing.

The grid now compares the fixed prototype-risk gate **off versus explicitly
experimental on**, instead of tuning two arbitrary probability thresholds.

Run optimization separately per selection only when enough history and fills
exist, but do not promote 56 independently best historical configurations by
pooled profit. Repeated selection over the same history requires a data-snooping
control such as [White's Reality Check](https://doi.org/10.1111/1468-0262.00152)
or the [Deflated Sharpe Ratio](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551).

Required promotion evidence remains:

1. baseline versus one new context at a time;
2. nested/locked walk-forward folds with embargo appropriate to the label;
3. realistic fees, spread, slippage, latency, funding/borrow where applicable;
4. per-asset/timeframe return, drawdown, turnover, fill coverage, and stability;
5. improvement distribution across folds, not only pooled PnL; and
6. append-only forward-paper results on the exact frozen configuration.

## Operational verification

- Analyst tests: `251 passed`.
- Live chart API: all 56 canonical asset/timeframe Cross-TF selections passed;
  1d correctly returned `no_higher_timeframe` and every aligned source
  availability was less than or equal to its active decision time.
- Default 5,000-bar BTCUSDT 1h response with all five layers completed in
  approximately 1.3 seconds after bounding the context history to 512 displayed
  decisions plus hidden warm-up.
- Browser checks passed at 1440x1000 and 390x844 with no application console,
  runtime, or network errors; five layer controls, latest-240 viewport, internal
  mobile scrolling, and canonical price precision were verified.
- The forward-paper service was restarted because algorithm/config digests
  changed. It opened a new append-only cohort rather than mixing old and new
  logic: run `7c7e750c...`, 56 streams, prototype gate `false`, BTC/ETH live,
  six multi-asset feeds explicitly delayed, historical research gate rejected,
  and real-order routing disabled.
