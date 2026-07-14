# Meta Model Analyst Next-Feature Research

**Date:** 2026-07-12
**Tracking:** Linear `RIS-258`
**Scope:** 8 canonical assets x 7 canonical timeframes
**Decision status:** research complete; no new production trade gate promoted

## Executive decision

The next useful work is **not another generic oscillator**. The repository
already contains causal market-structure, volatility-state, breakout,
volume-pressure, cross-asset, and BOCPD implementations. Several are good
engineering prototypes, but none is certified as a universal trading signal,
and two reused estimator families contain material mathematical or data-contract
problems.

The corrected priority is:

1. **Market Context v1:** expose prior structure, one comparable range-volatility
   measure, and seasonality-adjusted participation as three independently
   selectable diagnostics. Do not make them execution gates initially.
2. **Data provenance first for session assets:** carry constituent-minute
   quality, provider cohort, resolved futures instrument, and roll boundaries.
   Without that, volume, previous-session levels, gaps, and range breaks can be
   misinterpreted.
3. **Locked incremental ablation:** baseline versus one context at a time in the
   existing minute replay and append-only forward paper workflow.
4. **Repair and re-certify BOCPD separately:** the existing Python and Rust
   helpers do not have parity and the exposed `cp_prob` semantics are unsafe.
5. **Defer crypto derivatives and broad cross-asset live context:** those paths
   have narrower coverage or unresolved freshness/calendar/roll contracts.

The fixed 56-selection study supports that ordering. Structural location is
highly redundant with the existing trend score and adds almost no median
directional rank association after controlling for trend. Current volatility
state and relative volume carry the strongest consistent relationship with the
**magnitude** of future movement. Rogers-Satchell adds a smaller but distinct
range-versus-close volatility diagnostic.

Nothing in this report proves profitability. It determines what is worth
building and how to build it without lookahead or misleading labels.

## What already exists in the repository

The prior roadmap named concepts that are already implemented outside the
Analyst chart:

| Concept | Existing implementation | Current status |
|---|---|---|
| Prior rolling channel and room | `regression_feature_engineering/features/structural_room.py` | Causal and engineering-valid; useful for total path width, weak for direction, not promoted |
| Breakout/rejection capacity | `regression_feature_engineering/features/spike_breakout.py` | Causal prototype; not predictively promoted |
| Comparable volatility state | `regression_feature_engineering/features/volatility_state.py` | Strong target-scale association in earlier RPF audits; not promoted as a trading rule |
| Volume pressure | `regression_feature_engineering/features/liquidity_volume_pressure.py` | Prior rolling normalization, but not session-phase adjusted; not promoted |
| Session/calendar state | `regression_feature_engineering/features/regime_calendar_state.py` | Causal metadata/context; not promoted |
| Cross-asset context | `regression_feature_engineering/features/cross_asset_context.py` | Implemented research family; live feed/calendar/roll limitations remain |
| Range estimators | `scripts/feature_engineering/compute_features.py` and `compute_htf_features.py` | Parkinson/GK/RS/YZ names exist, but some formulas or error handling must be corrected before reuse |
| BOCPD | `scripts/target_models/helpers/bocpd.py` and `riskyield_rust/src/bocpd.rs` | Not safe to expose; backend parity and probability semantics are unresolved |

The RPF source of truth already says the active next task is model evaluation
and gating, not another formula family. That conclusion remains correct.

### Existing market-structure evidence

The existing structural-room family shifts highs/lows before rolling, so the
current source bar does not enter its own reference channel. Its earlier
`BTCUSDT 8h/B` audit covered roughly 2.81 million rows with zero future-close
violations. The strongest association was with future total path width
(`|Spearman|` about `0.2424`, roughly `0.2521` in the wider-window sweep), while
direct directional imbalance remained weak (maximum about `0.0489`).

That evidence supports structure as price-location and available-room context,
not as another direction engine.

## Trusted-source findings

### Prior structure and trading ranges

Brock, Lakonishok, and LeBaron tested moving-average and prior trading-range
break rules in a historical DJIA sample. The study supports researching prior
levels, but its daily windows and historical result do not establish universal
intraday parameters. See
[Brock, Lakonishok, and LeBaron (1992)](https://doi.org/10.1111/j.1540-6261.1992.tb04681.x).

The multiple-rule problem is central. Sullivan, Timmermann, and White applied a
data-snooping correction to a much larger rule universe, and later fresh-sample
evidence did not justify assuming that a historically good range rule will keep
working. See
[Sullivan, Timmermann, and White (1999)](https://doi.org/10.1111/0022-1082.00163)
and the
[fresh-sample replication](https://doi.org/10.1016/j.rfe.2013.05.004).

Osler found that support/resistance levels supplied by professional FX firms
helped identify intraday trend interruptions, but effectiveness varied across
firms and currencies. This supports displaying levels as context; it does not
justify fading every touch or following every break. See the
[Federal Reserve Bank of New York study](https://www.newyorkfed.org/medialibrary/media/research/epr/00v06n2/0007osle.pdf).

### Range-based volatility

The source-supported estimator roles are:

| Estimator | Main role | Important limitation |
|---|---|---|
| Parkinson | Efficient high-low diffusion estimate | Ignores open/close and gaps; zero-drift continuous-path assumptions |
| Garman-Klass | Uses OHLC under a zero-drift model | Ignores opening jumps and is less appropriate under drift |
| Rogers-Satchell | Intrabar OHLC variance robust to drift | Does not include interbar/session gaps |
| Yang-Zhang | Multi-session variance including opening jumps | Requires meaningful session opens and previous closes |

Primary references:

- [Parkinson (1980)](https://doi.org/10.1086/296071)
- [Garman and Klass (1980)](https://doi.org/10.1086/296072)
- [Rogers and Satchell (1991)](https://doi.org/10.1214/aoap/1177005835)
- [Yang and Zhang (2000)](https://doi.org/10.1086/209650)

Rogers-Satchell is the best first common **intrabar** estimator for the 8x7
matrix because it tolerates drift. It must be paired with a separate known-gap
channel. True Yang-Zhang belongs on exchange-session OHLC, not on arbitrary
UTC intraday buckets or 24/7 pseudo-sessions.

### Seasonality-adjusted participation

Intraday activity has a strong periodic component. Brownlees, Cipollini, and
Gallo decompose volume into daily scale, periodic intraday shape, and dynamic
non-periodic activity; removing the periodic component changes the dependence
structure materially. See
[Intra-daily Volume Modeling and Prediction for Algorithmic Trading](https://doi.org/10.1093/jjfinec/nbq024).

This supports comparing a completed bar with prior comparable session phases,
not merely with the immediately preceding bars. It does not turn candle-signed
volume into true order flow.

### Bayesian online change detection

Adams and MacKay define a causal run-length posterior and one-step predictive
distribution; the method is suitable for online inference and includes a
financial variance-change example. See
[Adams and MacKay](https://arxiv.org/abs/0710.3742).

The useful output is posterior regime age, recent-run mass, and predictive
surprise. Under the standard recurrence with constant hazard `h`, the single
bin `P(run_length = 0)` normalizes to the hazard and is not a data-responsive
alarm. A detector must be defined and calibrated separately. Restarted BOCPD is
one formal alternative with false-alarm/delay analysis; see
[Alami, Maillard, and Feraud (2020)](https://proceedings.mlr.press/v119/alami20a.html).

## Corrected implementation contracts

### 1. Causal market structure

For a completed bar `t` and fixed lookback `L`:

```text
upper_t = max(high[t-L : t-1])
lower_t = min(low [t-L : t-1])
```

Require the complete lookback for the chart layer. For positive prices and a
mature, nonzero prior volatility scale:

```text
position = clip(log(close / lower) / log(upper / lower), 0, 1)

up_room_sigma   = max(0, log(upper / close)) / prior_sigma
down_room_sigma = max(0, log(close / lower)) / prior_sigma

up_break_sigma   = max(0, log(close / upper)) / prior_sigma
down_break_sigma = max(0, log(lower / close)) / prior_sigma
```

Use state names such as `inside_range`, `near_prior_high`,
`closed_above_prior_channel`, and `tested_high_rejected`. Never use Buy/Sell.
The prior channel can be drawn across bar `t`; a classification using bar
`t`'s close/high/low becomes available only after that bar is final.

Previous-level anchors require explicit definitions:

- BTCUSDT/ETHUSDT: name them **previous UTC-day high/low**.
- CL/ES/EURUSD/GC/NQ/USDJPY: use completed exchange trade-date sessions from
  an authoritative calendar, computed from canonical 1m constituents.

Do not use the current crypto `session_id` for this purpose; it represents one
session across the available history.

### 2. Comparable range volatility

For completed OHLC bar `t`:

```text
h = log(high / open)
l = log(low / open)
c = log(close / open)
rs_variance = h * (h - c) + l * (l - c)
```

Valid OHLC ordering implies a nonnegative contribution apart from tiny floating
error. Do not apply `abs()` to a materially negative variance. Reject it as a
data-contract problem and expose status.

Recommended v1 outputs:

```text
rs_fast_sigma
rs_slow_sigma
rs_fast_slow_ratio
rs_range_shock = sqrt(rs_variance_t / prior_rs_slow_variance)
rs_to_close_vol_ratio
known_session_gap
gap_return
```

Do not plot Parkinson, Garman-Klass, and Rogers-Satchell together. The fixed
study found median Parkinson/RS rank correlation `0.9842`; that would add UI
clutter, not independent information.

### 3. Seasonality-adjusted participation

Learn all expected-volume curves from completed 1m constituents and prior
completed sessions only. For prior session `j` and phase slot `s`:

```text
session_total_j = sum_s(volume[j, s])
phase_share[j, s] = volume[j, s] / session_total_j

expected_session_total = prior-only robust EWMA(session_total)
expected_phase_share_s  = prior-only robust EWMA(phase_share[:, s])
expected_volume[d, s]   = expected_session_total * expected_phase_share_s
```

For a completed target bar containing phase slots `S`:

```text
rvol = sum(actual_volume[S]) / sum(expected_volume[S])
log_rvol = log(rvol)
```

For a forming target bar, compare elapsed actual volume only with the same
elapsed expected slots and label the result `provisional`. A backtest must
replay those minute updates; it may not substitute final target-bar volume.

Quality metadata must include comparable-session count, expected-volume floor,
missing/synthetic minute fraction, provider cohort, roll status, and finality.

### 4. BOCPD v1

Do not reuse the current helper output as a chart signal. A safe first research
model is directionless variance-change detection on prior-standardized returns:

```text
return_t    = log(close_t / close_(t-1))
prior_sigma = slow_EWMA_sigma_(t-1)
observation = return_t / prior_sigma
```

Use finalized bars, no backward smoothing, and a zero-mean piecewise-variance
Student-t predictive model. A frozen research baseline may use expected run
length `250` bars and constant hazard `1/250`, but the UI must show its
wall-clock meaning for the selected timeframe.

Chartable outputs should be:

```text
recent_change_mass = P(run_length < 5 | observations_so_far)
predictive_surprise_nll
run_length_mode / mean / median / q10 / q90
discarded_tail_mass and truncation_safe
```

The single-bin reset mass may be retained as a debug invariant, not named or
thresholded as change probability.

## Existing-code corrections required before reuse

### Range estimators

The old feature scripts should not be promoted unchanged:

- Their functions named Yang-Zhang omit the overnight/opening-jump component,
  so they are not true Yang-Zhang for sessioned futures.
- Their open-close variance is calculated with a rolling mean followed by a
  second rolling mean of squared deviations, producing the wrong rolling
  sample-variance contract and excessive warm-up.
- Garman-Klass and Rogers-Satchell apply `abs()` to variance, hiding invalid
  OHLC or formula problems.
- Rogers-Satchell is absent from one HTF export path despite existing in the
  general feature module.

### BOCPD

The current backends materially disagree on a synthetic mean shift:

```text
series: 100 zeros followed by 100 fives
hazard: 1 / 250

Python cp_prob min / median / max: 0.0040 / 0.0040 / 0.004000003
Rust   cp_prob min / median / max: 0.000015 / 0.000508 / 0.878108
maximum backend difference:       0.874108
```

The Python recurrence makes `cp_prob` essentially equal to the constant hazard.
The Rust branch uses a different reset predictive and passes its spike test,
but it does not have parity with Python and its run-length-zero sufficient-state
semantics need re-certification. Thresholding the current `0.3` field therefore
depends on whether the Rust extension happens to be installed.

This is a hard **do not expose** finding, not evidence that the Rust spike is a
profitable detector.

## Fixed 56-selection empirical screen

### Design

The new reproducible harness is:

```text
scripts/analysis/analyst_next_feature_study.py
```

It uses up to 50,000 recent canonical bars per selection, four chronological
diagnostic folds, and fixed future horizons of 1, 3, and 12 bars. Features are
computed on completed bar `t`; every evaluation return begins at `open[t+1]`.
Returns are normalized by prior slow EWMA volatility. No parameter search,
cost model, or strategy selection occurs.

Coverage:

```text
Selections:                         56
Rows inspected:             1,248,307
Median phase-volume coverage:  98.15%
Minimum phase-volume coverage:  66.28%  (1m warm-up)
Median RS feature coverage:      99.99%
Session-anchor-capable selections: 42/56
```

The 1m phase-volume minimum is expected from requiring ten prior comparable
phase occurrences inside a 50,000-bar tail. Production should use the full
available prior history and report maturity explicitly.

### Median selection-level rank associations

`partial` below is a descriptive partial Spearman correlation after controlling
for the existing trend score (direction features) or volatility level
(magnitude features). It is not a fitted strategy result.

| Feature | Target | 1 bar | 3 bars | 12 bars | Median partial at 1/3/12 |
|---|---|---:|---:|---:|---:|
| Existing trend score | signed return | -0.0183 | -0.0275 | -0.0274 | - |
| Channel position | signed return | -0.0166 | -0.0226 | -0.0244 | -0.0046 / -0.0060 / -0.0024 |
| Breakout balance | signed return | -0.0104 | -0.0123 | -0.0156 | -0.0052 / -0.0057 / -0.0020 |
| Room balance | signed return | 0.0172 | 0.0225 | 0.0244 | 0.0045 / 0.0052 / 0.0025 |
| Slow volatility level | absolute return | 0.1220 | 0.1090 | 0.0869 | - |
| Rogers-Satchell / close vol | absolute return | 0.0211 | 0.0342 | 0.0344 | 0.0525 / 0.0595 / 0.0668 |
| Phase-adjusted relative volume | absolute return | 0.1223 | 0.0888 | 0.0612 | 0.1091 / 0.0669 / 0.0522 |
| Unconditioned relative volume | absolute return | 0.1202 | 0.0605 | 0.0380 | 0.1236 / 0.0684 / 0.0388 |

Interpretation:

- Channel position overlaps strongly with the Analyst trend score: median
  Spearman `0.8494`. It does not justify a second direction gate.
- Breakout balance has lower but still material trend overlap: median `0.3809`.
- Structural partial associations are near zero. Structure should initially
  answer **where price is**, not **which direction will profit**.
- Volatility level and relative volume have the strongest stable magnitude
  relationships; the median fold-sign consistency is `1.0` at all three
  horizons.
- Phase-adjusted volume beats the unconditioned measure in `38/56`, `35/56`,
  and `42/56` selections at 1, 3, and 12 bars respectively. Its advantage is
  clearest at longer horizons and higher timeframes.
- Parkinson and Rogers-Satchell are almost duplicates empirically in this
  screen. Keep Rogers-Satchell because its drift assumption is better aligned
  with the common use case, then test it against Parkinson as a research-only
  ablation.
- The small negative short-horizon trend correlation is descriptive and may
  reflect reversal, execution timing, costs, or selection-specific effects. It
  is not permission to invert the current strategy globally.

### Data-quality findings

- All 56 canonical files expose the required OHLCV/session schema.
- The maximum zero-volume rate in the 50,000-bar study tail was `8.47%` for
  USDJPY 1m; EURUSD 1m was `3.42%`. These closely track synthetic no-trade
  rows, so zeros are data-quality/context information, not automatically real
  inactivity.
- Databento's official OHLCV contract emits no record when no trade occurs.
  The repository's carried/synthetic rows are therefore an internal
  materialization choice that must remain distinguishable. See
  [Databento's OHLCV contract](https://databento.com/docs/knowledge-base).
- EURUSD and USDJPY are futures proxies, not decentralized spot-FX volume.
- The six session assets use unadjusted continuous futures. Databento states
  that continuous-contract prices retain roll jumps rather than back-adjusting
  them. See
  [Databento continuous symbology](https://databento.com/docs/standards-and-conventions/symbology).
- Provider, resolved `instrument_id`, and roll event are not preserved in each
  canonical row. Previous-session levels, gap returns, volume baselines, and
  breakout markers must not silently cross an unknown provider/roll boundary.

Bybit explicitly marks a WebSocket candle closed only when `confirm=true`; an
unconfirmed candle remains open and updating. This supports the Analyst's
closed-bar availability contract. See the
[Bybit kline stream contract](https://bybit-exchange.github.io/docs/v5/websocket/public/kline).

## Recommended production sequence

### Phase A: provenance and quality fields

Persist or derive for each canonical bar:

```text
source_minute_count
expected_open_minute_count
synthetic_or_no_trade_count
unknown_missing_minute_count
provider_cohort
resolved_instrument_id
roll_event / roll_direction
first_seen_at
```

For an aggregate bar, do not reduce minute quality to one boolean. EURUSD and
USDJPY higher-timeframe bars frequently contain at least one synthetic/no-trade
minute; a count and rate are needed.

### Phase B: Market Context v1 chart layers

Keep three independent toggles, consistent with the Analyst's multi-layer UI:

1. **Prior Structure** on the price pane:
   - default 48-bar upper/lower channel;
   - optional 4/16 channels;
   - position, room, break/rejection state, maturity, availability;
   - previous UTC-day or exchange-session anchors only after the calendar/roll
     contract is ready.
2. **Comparable Volatility** in one `[0, ...]` pane/card:
   - existing EWMA percentile/relative level;
   - Rogers-Satchell fast/slow and range-shock ratio;
   - separate known-gap state;
   - no Parkinson/GK/YZ copies in the production UI.
3. **Participation** in one compact pane/card:
   - final `log RVOL` for completed bars;
   - cumulative pace only in minute replay/live mode and clearly provisional;
   - zero/synthetic/provider/roll quality badge;
   - candle-signed pressure remains labelled proxy, not order flow.

### Phase C: promotion evidence

Use the exact frozen strategy/config and add only one context at a time:

```text
baseline
baseline + structure continuous values
baseline + structure event states
baseline + comparable volatility
baseline + phase-adjusted participation
baseline + best single context + one predeclared interaction
```

Required evidence:

1. expanding chronological development folds and untouched final holdout;
2. entry at the next eligible real 1m open after actual availability;
3. fees, spread, slippage, latency, funding/borrow, and roll handling;
4. PnL, drawdown, turnover, fill coverage, and stability per selection;
5. fold-level improvement distribution, not pooled profit;
6. Reality Check/Deflated Sharpe or another declared multiple-testing control;
7. append-only forward-paper cohort on the exact frozen code/config digest.

Do not optimize 56 independent best settings and then aggregate the winners.
Prefer shared timeframe-family parameters with shrinkage, followed by explicit
selection-level exceptions only when evidence is sufficient.

### Phase D: BOCPD repair

Before BOCPD enters Analyst charts:

- define run-length timing semantics precisely;
- make Python/Rust streaming, batch, snapshot, and output parity exact;
- test the constant-hazard reset-bin identity;
- expose recent-run mass and predictive surprise, not an ambiguous `cp_prob`;
- use log-space probability arithmetic and account for every truncated tail;
- validate no-change false alarms, variance shifts, contractions, outliers,
  gradual drift, session gaps, rolls, and all 56 canonical streams;
- compare against false-alarm-matched CUSUM and EWMA baselines.

## Deferred branches

### Crypto derivatives

Funding, mark/index premium, open interest, and crowding remain potentially
useful for BTCUSDT/ETHUSDT only. They do not cover the system-wide 8x7 matrix.
The local open-interest snapshot is stale relative to the other crypto data,
and publication/first-seen alignment is not fully certified. Repair freshness
and timestamps before adding any derivative chart or paper-trading gate.

### Cross-asset live context

Pair-specific BTC/ETH and ES/NQ research is more defensible than generic
breadth. Live promotion still needs synchronized first-seen alignment,
compatible sessions, trading-grade feeds, and resolved futures rolls. The six
noncrypto forward-paper feeds are delayed fallbacks, so a historical
cross-asset result would not yet establish live usability.

## Artifacts and reproducibility

- Research harness:
  `scripts/analysis/analyst_next_feature_study.py`
- Machine-readable 56-selection result:
  `docs/validation/meta_model_analyst_next_feature_study_2026-07-12.json`
- Causality/formula tests:
  `tests/test_analyst_next_feature_study.py`
- Prior certification:
  `docs/validation/meta_model_analyst_indicator_certification_2026-07-12.md`

Reproduce the fixed screen:

```bash
python -m scripts.analysis.analyst_next_feature_study \
  --max-bars 50000 \
  --folds 4 \
  --output docs/validation/meta_model_analyst_next_feature_study_2026-07-12.json
```

The generated JSON records formulas, horizons, timing guardrails, every
selection-level fold result, coverage, overlap, and aggregate distributions.
