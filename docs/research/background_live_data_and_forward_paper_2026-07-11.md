# Background finalized-1m data and forward paper validation

Date: 2026-07-11
Scope: eight core assets, seven canonical timeframes, root `update_data.py`,
and the Risk Yield Meta Model Analyst chart.

## Outcome

The repository now has a persistent finalized-one-minute service with an
append-only first-seen journal and 56 independent normalized paper streams.
It does not send real orders.

Commands:

```bash
# Start all 8 assets x all 7 timeframes in the background.
python update_data.py --live-start

# Inspect PID, heartbeat, source grade, latest bar, and paper metrics.
python update_data.py --live-status

# Orderly stop after verifying that the PID still belongs to this service.
python update_data.py --live-stop

# Deterministic foreground smoke/catch-up. It does not backdate paper signals.
python update_data.py --live-1m --once
```

Runtime data defaults to
`$XDG_STATE_HOME/riskyieldmm/forward_paper`, or
`~/.local/state/riskyieldmm/forward_paper` when `XDG_STATE_HOME` is unset. It
can be overridden with `RISKYIELDMM_STATE_DIR` or `--live-state-dir`.

The chart at <http://localhost:8765> has a **Forward paper validation** panel.
It shows whether the selected asset is live or delayed, first-observed time,
source watermark, cohort status, position, fills, costs, normalized return,
and drawdown. The status API is:

```text
/api/paper/status?asset=BTCUSDT&timeframe=1h
```

## Provider truth table

| Assets | Current adapter | Grade shown in UI | Meaning |
|---|---|---|---|
| BTCUSDT, ETHUSDT | Bybit public finalized 1m REST | `live` | Near-real-time closed bars with a five-second finality guard |
| CL, ES, EURUSD, GC, NQ, USDJPY | Yahoo front-futures fallback | `delayed` | Forward-observed but delayed/indicative; not execution-quality live data |

The six non-crypto canonical series are CME continuous-futures proxies.
`EURUSD` maps to 6E and `USDJPY` to inverted 6J; silently replacing them with
spot FX would change the instrument definition. Honest real-time coverage for
those six assets requires a licensed futures source such as Databento Live.

`--require-live-feeds` fails closed when a delayed asset is selected. With the
currently implemented adapters it can therefore be used only with BTCUSDT
and/or ETHUSDT.

The service heartbeat remains one minute. Bybit is polled on each finalized
minute; delayed Yahoo assets are polled at their ten-minute provider cadence to
avoid pretending that more frequent requests create fresher data.

Official source contracts:

- [Bybit REST kline](https://bybit-exchange.github.io/docs/v5/market/kline)
- [Bybit WebSocket kline finality](https://bybit-exchange.github.io/docs/v5/websocket/public/kline)
- [Databento Live API](https://databento.com/docs/api-reference-live)
- [Databento OHLCV schema](https://databento.com/docs/schemas-and-data-formats/ohlcv)
- [yfinance download API](https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html)

## Causality and recovery contract

1. Provider rows must be UTC, minute-aligned, finite, positive-price OHLCV and
   safely finalized.
2. The first observed version of a source minute becomes authoritative.
   Identical overlap rows are idempotent. A changed overlap appends a revision
   incident and never rewrites issued signals, fills, or PnL.
3. Historical/bootstrap rows warm state but emit no paper orders or fills.
   Downtime catch-up signals are explicitly suppressed.
4. A signal is eligible only after the later of its scheduled target-candle
   close and its actual provider observation time, plus configured latency,
   rounded to a later whole-minute open. Delayed data therefore cannot fill at
   an already-passed market open.
5. One observed 1m row fans into 1m, 15m, 1h, 4h, 8h, 12h, and 1d state
   machines. Existing canonical target bars seed recursive indicators without
   generating historical trades.
6. The SQLite journal uses WAL mode, `synchronous=FULL`, foreign keys, a
   singleton `fcntl` writer lock, immutable-table triggers, per-run SHA-256
   event chains, and atomic event/snapshot/checkpoint transactions.
7. Restart verifies the hash chain, restores checksummed stream snapshots, and
   deterministically replays later first-seen source events. A code/config/cost
   change creates a new cohort rather than mutating an old one.

## Profitability evidence as of implementation

The current signal mapping has **not** demonstrated a robust edge. A fixed
1 bp fee plus 1 bp slippage baseline replayed successfully for BTCUSDT and ES
across all seven timeframes, but 13 of 14 selections were negative. BTCUSDT
1d was positive over its 60-day window, but it had only four completed round
trips and is not credible evidence.

The bounded 24-configuration chronological optimizer also returned
`rejected`. The running paper cohort is therefore visibly labelled
`historical_optimizer_rejected_observe_only` /
`collecting_unaccepted_baseline`. This is intentional: the service collects
honest new evidence without promoting a losing historical configuration or
tuning toward one lucky holdout.

No future profit can be guaranteed. A later candidate should remain paper-only
until it has, at minimum:

- positive post-cost chronological development folds and untouched holdout;
- positive return at doubled costs;
- sufficient trades and calendar duration, not one sparse lucky window;
- acceptable drawdown and stable neighbouring parameters;
- complete source coverage with no unresolved revision/integrity incident;
- positive forward paper return and expectancy over a predeclared evaluation
  horizon.

Even a passing forward cohort would only become eligible for human live-review;
it must never enable real order routing automatically.

## Verification performed

- All 56 canonical asset/timeframe streams bootstrapped from 400 safely closed
  target bars with no failure.
- An all-assets foreground pass produced 56 paper stream statuses: two `live`
  Bybit feeds and six `delayed` Yahoo feeds.
- Background start, status, verified-PID stop, and restart recovery were
  exercised against isolated runtime directories.
- The live chart API returned the selected feed and paper metrics, and the
  browser panel rendered those values alongside the existing signal charts.
- Focused tests cover provider finality, weekend overlap, immutable revisions,
  journal rollback/tamper detection, snapshot parity, delayed-observation
  timing, service restart, all-56 selection coverage, and process supervision.

## Remaining production work

- Add a persistent Databento Live adapter and entitlement checks for the six
  CME-linked assets.
- Add broker-specific instruments, multipliers, currencies, rolls, tick sizes,
  spread/impact, funding, and borrow accounting.
- Promote only optimizer-accepted, human-approved immutable cohorts.
- Add forward evidence gates such as minimum 90 days, 30 completed round
  trips, doubled-cost profitability, confidence bounds on expectancy, and a
  multiple-testing adjustment.
- Keep real order execution in a separate, explicitly authorized project.
