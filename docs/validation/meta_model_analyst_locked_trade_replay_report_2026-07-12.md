# Analyst locked trade replay validation

Date: 2026-07-12
Scope: `Risk_Yield_Meta_Model_Analyst_0_0_1`
Machine result: `docs/validation/meta_model_analyst_locked_trade_replay_2026-07-12.json`
Validator: `scripts/analysis/validate_analyst_locked_trade_replay.py`

## Decision

The current locked strategy is **not ready for live capital or broker/demo
routing as a trading candidate**.  Its causal replay mechanics work, but the
180-day common-window matrix is negative in the majority of selections and the
young append-only forward sample is also negative.  Keep real routing disabled
and continue the current 56-stream shadow observation.

This does not mean that every selection lacks signal.  Nine selections passed
the predeclared descriptive checks, concentrated in BTCUSDT, ETHUSDT, GC and NQ
at 8h through 1d, plus GC 1h.  They are candidates for a newly frozen forward
cohort, not permission to trade: the matrix was inspected after evaluation,
session-asset candles still have sparse-boundary limitations, and there is no
portfolio or broker-grade execution model.

## Locked protocol

The protocol was fixed before results were inspected:

- common evaluation window: `2026-01-11T21:00:00Z` through
  `2026-07-10T21:00:00Z` (180 days);
- all 8 canonical assets and all 7 canonical timeframes, 56 independent
  normalized streams;
- strategy digest `b5713acf6b482ae3`, the unoptimized default strategy used by
  the forward-paper service;
- cost digest `7d607c892d81d7b4`: fee 1 bps, adverse slippage 1 bps, quoted
  full spread 0 bps, and one configured minute of execution latency;
- current-revision canonical 1m candles, target signals committed only at the
  scheduled target close, historical observation scenario delayed by 5 seconds,
  and full fill at the first later real 1m open at/after eligibility;
- synthetic/no-trade minutes excluded from signal input and fill eligibility;
- no parameter optimization, candidate selection or replay-dependent mutation;
- metrics evaluated on every real minute, with event and chart arrays disabled;
- protocol digest
  `304c9f9e285006a555e17687ea55a852d338a4a75aae2b7fda640d50a49d3171`.

The checks were descriptive, not a selection objective: at least 20 fills,
positive net return, positive annualized minute-return Sharpe, drawdown no more
than 20%, and gross breakeven cost above a doubled 4 bps one-way cost scenario.

## Full-matrix result

| Measure | Result |
|---|---:|
| Completed selections | 56 / 56 |
| Replay failures | 0 |
| Positive net selections | 18 / 56 (32.14%) |
| Passed every descriptive check | 9 / 56 (16.07%) |
| Median net return | -4.315% |
| Median annualized Sharpe | -1.423 |
| Total independent-stream fills | 152,597 |
| Total independent-stream round trips | 67,735 |
| Summed excluded synthetic rows | 178,338 |

The synthetic total is summed across independently loaded selection windows and
must not be read as a unique-row count.

Timeframe concentration was material:

| Timeframe | Positive / 8 | All checks / 8 | Median net return | Median Sharpe |
|---|---:|---:|---:|---:|
| 1m | 0 | 0 | -95.068% | -51.673 |
| 15m | 0 | 0 | -26.447% | -4.553 |
| 1h | 3 | 1 | -6.552% | -1.561 |
| 4h | 1 | 0 | -4.268% | -0.805 |
| 8h | 4 | 3 | -0.066% | -0.231 |
| 12h | 4 | 4 | 3.894% | 0.793 |
| 1d | 6 | 1 | 4.274% | 0.787 |

The 1m strategy is decisively unsuitable in its current form.  All eight 1m
selections lost money after costs.  Some gross paths were also negative; CL 1m
had positive gross return but only a 0.378 bps breakeven cost, far below the
modeled 2 bps one-way cost, so turnover erased it.

## Selections that passed every descriptive check

| Asset | Timeframe | Net return | Sharpe | Max drawdown | Fills | Breakeven cost |
|---|---|---:|---:|---:|---:|---:|
| BTCUSDT | 8h | 5.757% | 0.563 | 13.101% | 81 | 10.93 bps |
| BTCUSDT | 12h | 20.498% | 1.618 | 11.323% | 52 | 49.43 bps |
| BTCUSDT | 1d | 33.268% | 2.881 | 7.340% | 25 | 200.70 bps |
| ETHUSDT | 12h | 31.040% | 1.689 | 15.512% | 41 | 88.85 bps |
| GC | 1h | 5.930% | 0.886 | 10.067% | 326 | 4.47 bps |
| GC | 8h | 20.571% | 2.693 | 8.563% | 44 | 73.35 bps |
| GC | 12h | 19.110% | 2.230 | 9.681% | 27 | 126.48 bps |
| NQ | 8h | 1.356% | 0.333 | 7.272% | 49 | 6.07 bps |
| NQ | 12h | 7.867% | 1.627 | 4.772% | 35 | 38.58 bps |

ETHUSDT 1d had the largest net return, 42.105%, but failed the predeclared
minimum-fill check with only 19 fills.  CL 1d was positive but also had only 17
fills.  These results should not have their thresholds relaxed after inspection.

The continuous crypto candidates used exact target candles.  The positive GC
and NQ candidates included target candles classified as scheduled session gaps,
sparse boundaries, or sparse-unverified session candles.  Until authoritative
exchange-calendar and roll provenance is available, those futures results are
weaker evidence than their headline returns suggest.

## Worst selections

| Asset | Timeframe | Net return | Gross return | Sharpe | Max drawdown | Fills |
|---|---|---:|---:|---:|---:|---:|
| BTCUSDT | 1m | -99.285% | -24.704% | -42.321 | 99.285% | 27,092 |
| ETHUSDT | 1m | -99.261% | -30.067% | -31.935 | 99.262% | 26,516 |
| ES | 1m | -96.009% | -6.323% | -86.396 | 96.009% | 18,293 |
| NQ | 1m | -95.921% | -5.212% | -62.795 | 95.921% | 18,003 |
| GC | 1m | -94.216% | -11.321% | -36.332 | 94.238% | 16,053 |

## Append-only forward-paper snapshot

The local forward-paper service was independently verified through
`/api/paper/status` at heartbeat `2026-07-12T21:31:05.422764Z`:

- service running since `2026-07-12T19:50:35.282551Z` with real routing off;
- research status `historical_optimizer_rejected_observe_only`;
- 2 healthy live Bybit assets and 6 delayed yfinance assets;
- 56 independent streams, but only BTCUSDT 1m and ETHUSDT 1m had fills;
- BTCUSDT 1m: 101 evaluated forward minutes, 7 fills / 3 round trips,
  -0.182% net, -0.042% gross, 0% round-trip win rate;
- ETHUSDT 1m: 101 evaluated forward minutes, 11 fills / 5 round trips,
  -0.044% net, +0.176% gross;
- the other 54 streams had zero fills because they were still warming up or had
  no new finalized data.

This sample is far too short to estimate profitability.  It is useful only as
evidence that the append-only source, clock, order and fill path is operating.
The delayed non-crypto feeds cannot presently provide true live validation.

## Core integrity finding and correction

The audit found that `indicator_optimizer._specification_from_config()` restored
only 7 of the 16 serialized `IndicatorStrategyConfig` fields.  If the winning
configuration enabled `enable_experimental_prototype_regime_gate`, for example,
`best_config` and the trial registry reported `true` while holdout and final
replay silently instantiated the default `false` value.  The reported winner
was therefore not necessarily the strategy used for final evaluation.

This was corrected during the audit.  The round trip now preserves every
strategy field, restores tuple-valued constructor inputs, and rejects missing or
unknown fields.  Regression tests prove that the selected experimental gate
reaches both stressed holdout and final replay.  Optimizer results created
before this correction should not be treated as verified evidence.

This defect did not affect the locked matrix above because it did not invoke the
optimizer and its strategy digest matched the running forward-paper service.

## What the simulation did not validate

- Market Context v1 (Prior Structure, Comparable Volatility and Phase-Adjusted
  Participation) is displayed as chart diagnostics but is not used by
  `_desired_position`; this replay does not prove those new layers improve PnL.
- The canonical history is the current revision, not an as-was-live historical
  journal.  Append-only evidence exists only from the current forward run.
- Futures multipliers, contract rolls, tick values, funding, borrow, FX
  conversion, margin, liquidation and historical costs are absent.
- Bar-open fills cannot model quotes, depth, queue position, partial fills,
  rejection, cancel races or market impact.
- Annualized Sharpe is calculated from one-minute marked returns and can be
  unstable for sparse/high-timeframe exposure; it is only one diagnostic.
- The 56 streams are independent normalized experiments, not a portfolio.
- Inspecting the nine winners creates a new hypothesis.  They need a frozen,
  forward-only cohort and must not be declared validated on this same window.

## Required next action

1. Keep 1m and 15m out of the candidate cohort unless a separately frozen
   experiment later passes realistic costs and forward checks.
2. Freeze the nine descriptive candidates as an observation-only cohort; do not
   retune them on this window.
3. Continue append-only forward collection through multiple market regimes,
   with minimum sample sizes and a fixed review date declared in advance.
4. Add authoritative session/roll provenance and instrument-specific cost
   models before interpreting GC/NQ/CL/ES/FX PnL economically.
5. Add and test pre-trade exposure/notional limits, stale-data rejection,
   duplicate-order protection, drawdown stops, a kill switch, alerts, broker
   acknowledgement/fill/cancel handling, and post-trade reconciliation.
6. Only after that, run separate one-at-a-time ablations for the three Market
   Context layers; do not add them all to execution and credit them jointly.

## Decision workspace delivered with the audit

The chart now starts with an evidence-first seven-step rail: feed freshness,
conservative readiness, directional agreement/conflict, context and risk,
routing and next allowed action, historical replay evidence, and independent
forward-paper evidence.  Without an explicitly frozen policy, readiness remains
`NO TRADE · INSUFFICIENT` or `NO TRADE · BLOCKED`.  Stale feeds and directional
conflict hard-block the view, real routing is visibly off, historical and
forward vintages stay separate, and the detailed context panels remain
available through progressive disclosure.

This presentation follows the professional principle that simulated and actual
evidence must be clearly identified and separated, while testing, risk controls,
monitoring, and reconciliation remain explicit production gates.

## Professional references

- CFTC on hypothetical-result, spread, impact, cost, and profit-guarantee
  limitations:
  <https://www.cftc.gov/LearnAndProtect/AdvisoriesAndArticles/fraudadv_tradingsystem.html>
- NFA on hypothetical-performance limitations and equally prominent actual
  evidence:
  <https://www.nfa.futures.org/rulebooksql/rules.aspx?RuleID=9025&Section=9>
- FINRA on testing, independent validation, limited pilots, controls, monitoring,
  and reconciliation:
  <https://www.finra.org/rules-guidance/notices/15-09>
- Bailey and Lopez de Prado on the Deflated Sharpe Ratio and selection bias:
  <https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551>
- Alpaca on simulated paper fills and possible paper/live divergence:
  <https://alpaca.markets/support/difference-paper-live-trading>

## Reproduction and checks

```bash
python scripts/analysis/validate_analyst_locked_trade_replay.py

curl -sS --get http://127.0.0.1:8765/api/backtest \
  --data-urlencode asset=BTCUSDT \
  --data-urlencode timeframe=1h \
  --data-urlencode source=canonical \
  --data-urlencode start=2026-01-11T21:00:00Z \
  --data-urlencode end=2026-07-10T21:00:00Z \
  --data-urlencode fee_bps=1 \
  --data-urlencode slippage_bps=1 \
  --data-urlencode spread_bps=0 \
  --data-urlencode execution_latency_minutes=1 \
  --data-urlencode event_limit=0

pytest -q \
  tests/test_analyst_locked_trade_replay_validator.py \
  tests/test_analyst_minute_replay.py \
  tests/test_analyst_indicator_optimizer.py \
  tests/test_analyst_chart_server.py
ruff check \
  scripts/analysis/validate_analyst_locked_trade_replay.py \
  tests/test_analyst_locked_trade_replay_validator.py
python -m py_compile scripts/analysis/validate_analyst_locked_trade_replay.py
git diff --check -- \
  scripts/analysis/validate_analyst_locked_trade_replay.py \
  tests/test_analyst_locked_trade_replay_validator.py \
  docs/validation/meta_model_analyst_locked_trade_replay_2026-07-12.json \
  docs/validation/meta_model_analyst_locked_trade_replay_report_2026-07-12.md
```

The exact BTCUSDT 1h API replay matched the matrix on all compared metrics:
net/gross return, drawdown, Sharpe, fill count, round trips and breakeven cost.
Focused validation finished with 74 passing tests and zero Ruff, compilation,
JSON, or whitespace errors.
