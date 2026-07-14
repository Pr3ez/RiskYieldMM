# Professional paper/replay execution contract

Date: 2026-07-12
Scope: `Risk_Yield_Meta_Model_Analyst_0_0_1`
Tracking: Linear RIS-256

## Decision

RiskYieldMM will treat historical causal replay and forward paper validation as
two adapters around one explicit execution contract.  Strategy logic, target
candle integrity, order eligibility, normalized cost arithmetic, identifiers,
and result names must match.  The clocks and source vintage intentionally differ:

- causal replay uses the latest canonical revision and scheduled bar-close time;
- forward paper uses append-only first-seen rows and actual observation time.

The current paper streams are **independent shadow experiments**.  Each
asset/timeframe stream starts with normalized equity 1.0.  They are not a
capital-netted portfolio and their results must not be summed into a portfolio
profitability claim.  Real order routing remains disabled.

## Primary-source design evidence

- NautilusTrader runs the same strategies and execution algorithms in backtest
  and live contexts, with adapters feeding a common downstream engine.  It also
  separates external event time from object initialization/availability time
  (`ts_event` and `ts_init`) and orders backtests by availability time:
  [live engine parity](https://nautilustrader.io/docs/latest/concepts/live/),
  [data timestamps and flow](https://nautilustrader.io/docs/latest/concepts/data/).
- NautilusTrader documents that order-book, quote, trade, and bar inputs have
  progressively lower execution realism.  Bar simulation is useful, but it
  cannot reconstruct queue position or market depth:
  [backtesting and fill modeling](https://nautilustrader.io/docs/latest/concepts/backtesting/).
- QuantConnect documents that live/backtest differences arise from data timing,
  revisions, fill, fee, slippage, brokerage, and market-impact assumptions.  It
  recommends acting only when fresh price data is received and maintaining
  state across restarts:
  [live reconciliation differences](https://www.quantconnect.com/docs/v2/writing-algorithms/live-trading/reconciliation).
- Bybit order submission is asynchronous, requires a unique client order ID for
  robust correlation, and must be followed through order/execution streams.
  Cancel/fill races can produce duplicate terminal messages:
  [create order](https://bybit-exchange.github.io/docs/v5/order/create-order),
  [private order stream](https://bybit-exchange.github.io/docs/v5/websocket/private/order).
- Even broker paper systems are not execution proof.  IBKR documents top-of-book
  simulation and partial/complex-order differences:
  [IBKR paper limitations](https://ibkrcampus.com/campus/glossary-terms/paper-trading-account/).

## Audit findings that triggered this contract

1. Historical 1m replay replaced the pending signal before filling it.  A
   one-minute or longer latency therefore produced zero fills, while forward
   paper retained and filled its pending order.
2. Sparse continuous-market minutes could close and trade an incomplete BTC/ETH
   target candle.  Chart overlay validation already rejected the same shape, so
   chart and execution paths could disagree.
3. Replay retained every signal in memory and JSON.  A seven-day BTC 1m response
   was 5.8 MB; extrapolating the 365-day UI default produced an unsafe response
   and cache footprint.  The running chart server reached roughly 2.2 GB RSS.
4. Replay used zero-minute latency while paper used one minute.  The UI hid this
   mismatch and most data-vintage/execution assumptions.
5. Paper and replay used different drawdown signs and different metric names.
6. Round-trip replay returns excluded entry cost and mishandled reversal cost,
   although total equity was still internally consistent.
7. An optimizer winner could not be frozen into the paper service from the CLI;
   paper always used the hard-coded default strategy.

## Versioned bar-execution contract

### Clocks

Every decision distinguishes:

1. source bar open/event time;
2. scheduled target candle close;
3. first observed/available time;
4. order eligibility time;
5. fill minute open/event time;
6. fill observation/journal time.

Historical replay has no genuine first-seen timestamp and is therefore marked
`current_canonical_replay`, never `as_was_live`.  Forward paper eligibility uses
`max(scheduled_close, observed_at) + configured_latency`, rounded to a whole
minute.  An existing order is processed at a minute open before the newly closed
target candle can create another order.

### Candle integrity

BTCUSDT and ETHUSDT are continuous markets.  A tradable target candle must:

- start on its exact UTC bucket boundary;
- contain the exact expected number of unique source minutes;
- have consecutive one-minute timestamps;
- end immediately before its scheduled target close.

An incomplete continuous-market target is journaled/reported but cannot update
the trading signal or create an order.  Session assets retain an explicit
session-partial policy until an exchange-calendar completeness model replaces
the current causal session-open evidence.

### Orders and fills

The implemented OHLCV simulator supports one deliberately narrow policy:

- normalized market order targeting a position in `[-1, 1]`;
- one immutable pending order at a time;
- full all-or-none fill at the first real 1m open at/after eligibility;
- deterministic signal, order, and fill IDs;
- explicit created/pending/filled/suppressed states;
- no fill on synthetic or incomplete continuous-market bars.

It does **not** support venue acknowledgement, rejection, cancel/replace,
expiration, partial fills, queue position, or order-book liquidity.  These fields
must stay visibly marked unsupported rather than silently approximated.

### Costs and accounting

Normalized equity is fill-derived and marked open-to-close each real minute.
Each change in target exposure charges, per unit turnover:

- configured fee;
- configured slippage scenario;
- half of the configured full bid/ask spread on each execution side.

Spread is a scenario input because historical quotes are unavailable.  Contract
multipliers, tick values, futures rolls, funding, borrow, FX conversion, margin,
liquidation, and market impact are still absent.  Metrics therefore remain an
economic proxy, not broker-grade PnL.

### Bounded evidence

Full metrics are computed over every eligible minute.  Browser audit arrays are
bounded and report total/returned/truncated counts.  Optimizer development and
stressed-holdout trials request metrics-only replay; only the final selected
holdout replay captures chart/audit output.  The in-process HTTP LRU is kept
small.  Durable first-seen evidence belongs in the append-only SQLite journal.

## Implemented and verified on 2026-07-12

- Replay now retains one pending order until fill or an explicit continuous-data
  incident.  One-minute replays with 1, 2, and 5 minutes of configured latency
  all produce eligible later-open fills instead of silently losing every order.
- BTCUSDT/ETHUSDT target candles require exact minute continuity.  Incomplete
  candles are counted and rejected; detectors reset across a continuous-market
  source gap, and a working order whose fill history became unknowable is not
  moved to a later observed open.
- Replay and paper share the v2 eligibility, adverse-price, fee, slippage, and
  half-spread arithmetic.  Round-trip accounting includes entry and exit costs
  and allocates reversal costs between the closing and newly opening legs.
- Signals, orders, fills, markers, and chart series are bounded independently of
  full-period metrics.  A measured 30-day BTCUSDT 1m request evaluated 41,309
  real minutes and 3,830 fills while returning at most 2,000 audit events and
  12,000 chart points in a 5.85 MB response.
- The canonical latest-window path reads only the required Parquet row groups.
  In an isolated default 1m chart request, resident chart-server memory fell
  from roughly 1.44 GB to 262 MB while still returning 5,000 candles and all
  four indicator layers.
- The forward service restarted as `forward_paper_service_v2` with 56 independent
  streams, an immutable engine contract, append-only first-seen vintage, and
  real routing disabled.  BTCUSDT and ETHUSDT caught up to the current finalized
  minute after restart; delayed Yahoo fallbacks remain visibly classified as
  delayed rather than live.
- A headless Chromium run rendered the chart, paper contract, order lifecycle,
  replay metrics/fills, and parity status with no JavaScript or network failures.
  The visible parity result confirmed matching strategy, costs, and execution
  timing while explicitly identifying the replay/paper vintage difference.
- Final verification: 250 targeted Analyst/update-service tests, Ruff, JavaScript
  syntax checking, Python compilation, and `git diff --check` all passed.

These measurements validate mechanics and resource bounds only.  The measured
returns remain research output and do not establish profitable trading.

## Mode comparison

| Property | Causal replay | Forward paper |
|---|---|---|
| Source vintage | Current canonical revision | Append-only first-seen journal |
| Availability | Scheduled close assumption | Actual observed time |
| Clock | Deterministic historical event clock | Wall clock plus provider arrival |
| Strategy | Request/frozen optimizer config | Frozen cohort config |
| Order policy | Shared normalized next-open model | Shared normalized next-open model |
| Execution evidence | Simulated from OHLCV | Simulated from forward observations |
| Portfolio | One selected experiment | 56 independent shadow experiments |
| Real routing | Disabled | Disabled |
| Profitability proof | No | No |

## Required before broker/demo routing

The following are deliberately deferred rather than faked:

1. A portfolio allocation policy resolving conflicting timeframes and assets,
   with net/gross exposure, cash, margin, and correlation controls.
2. Instrument masters for multiplier, tick, currency, roll, funding, and borrow.
3. Quote/order-book adapters and versioned volume/queue/partial-fill models.
4. A venue OMS with submit/ack/reject/partial/cancel/expire states and idempotent
   client IDs.
5. Startup and continuous reconciliation of orders, executions, positions,
   balances, and fees against venue reports.
6. Pre-trade stale-feed, loss, drawdown, leverage, order-rate, and notional gates.
7. Crash tests at every ambiguous command/journal boundary and independent
   journal-to-ledger reconstruction checks.
8. Delta checkpoints, run rotation, disk budgets, and incremental chain checks
   for multi-month forward operation.
9. Asynchronous optimizer jobs with progress/cancellation, frozen experiment
   manifests, and holdout-reuse governance.

Bybit demo or another broker paper adapter should initially validate protocol,
state-machine, restart, and reconciliation behavior only.  It must not be used
as evidence of realistic liquidity or future profitability.
