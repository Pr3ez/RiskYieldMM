# Indicator-driven trade policy for RiskYieldMM Analyst

Date: 2026-07-12
Tracking: Linear `RIS-261`
Related audit: Linear `RIS-260`
Status: architecture selected; implementation and profitability validation not yet performed

## Decision

The professional solution that best matches RiskYieldMM is a **hybrid,
stateful, volatility-targeted trend policy with protective order management**.
Indicators should create a versioned trade intent; they should not submit orders
or independently choose position size.

```text
finalized bars and causal indicators
                |
                v
        SignalPolicy / TradeIntent
                |
                v
  PortfolioConstruction + RiskPolicy
                |
                v
     PositionPlan with stop and size
                |
                v
     restart-safe Order/Trade state
                |
                v
 venue adapter, fills, reconciliation
```

This follows the professional separation of alpha, portfolio construction, risk
and execution. RiskYieldMM should use a hybrid rather than a completely isolated
framework because entry, protective children, trailing state and exit precedence
must share a `setup_id` and actual fill state.

The current strategy is not this system yet. It is a causal target-position
rebalancer. A finalized target bar produces a normalized desired exposure, and
one market order fills at the first eligible real one-minute open. There is no
executable stop-loss, take-profit, trailing-stop state, risk-per-stop sizing or
bracket/OCO lifecycle.

Nothing in this document establishes a profitable policy. The prior 180-day
audit had negative median performance and every 1m and 15m selection lost.
Adding exits may change the loss distribution, but it cannot be assumed to
create entry edge.

## Current executable indicator roles

The current `_desired_position` path uses only:

- volatility-scaled trend sign and path quality for direction;
- CUSUM regime agreement;
- fast/slow EWMA volatility ratio as a shock gate and relative exposure haircut;
- optionally, the fixed prototype-regime gate and direction flags, which are off
  by default.

It then emits a normalized target fraction. It does not use absolute volatility,
stop distance, account risk, point value, tick value, margin or shared portfolio
capital.

The following visible layers remain descriptive/chart-only:

- the plotted CUSUM `trail_stop` and bands;
- cross-timeframe context;
- prior structure;
- Rogers-Satchell comparable volatility;
- phase-adjusted participation.

The fixed-prototype HMM is explicitly untrained. It must remain diagnostic until
trained, calibrated and separately qualified.

## Correct role for each existing indicator

| Indicator | Proposed professional role | Initial production status |
| --- | --- | --- |
| Volatility-Scaled Trend | Primary setup direction, strength and thesis invalidation | Keep as the frozen entry baseline |
| CUSUM | Direction-change confirmation; later, one trailing-stop candidate | Agreement remains active; trail requires ablation |
| EWMA Volatility | Lagged absolute risk scale, volatility target and shock gate | Add absolute-vol sizing; retain ratio gate |
| Prior Structure | Prior-only trigger and logical invalidation anchor | Experimental risk/entry ablation |
| Comparable Volatility | Intrabar range-risk floor and abnormal-volatility filter | Experimental risk ablation |
| Cross-TF Context | Conflict block or portfolio-risk haircut | Experimental; never seven separate positions |
| Phase Participation | Mature activity filter | Experimental; not executable liquidity |
| Prototype HMM | Diagnostic regime/change-risk display | Excluded from baseline money decisions |

Indicator values should initially decide **eligibility**, not multiply quantity
as if they were confidence probabilities. The present scores are not calibrated
expected returns or probabilities.

## Selected baseline: risk-managed trend, not fixed-target trading

RiskYieldMM currently has trend/change-detection alpha, not a validated
mean-reversion alpha. Therefore the first exit policy should be:

1. an immutable initial protective stop;
2. next-bar signal invalidation when trend/CUSUM no longer support the thesis;
3. a monotonic structure/volatility trailing stop;
4. an optional time stop tested separately;
5. **no fixed full-position take-profit in the baseline**.

A fixed target can truncate the few large moves on which a trend policy may
depend. That is an inference from the strategy family, not a universal theorem.
A fixed-R target, an opposing-structure target and a partial-target-plus-runner
policy should remain separately registered ablations. A full-position target is
more natural for a future validated range/mean-reversion policy, which the
system does not currently have.

## Causal risk scale

The current EWMA and Rogers-Satchell outputs are useful but not sufficient by
themselves for a protective price distance. Rogers-Satchell excludes interbar
gaps, while close-to-close EWMA does not measure the intrabar range. Add one
causal True Range/ATR risk primitive:

```text
TR_t = max(
    high_t - low_t,
    abs(high_t - close_(t-1)),
    abs(low_t  - close_(t-1))
)

ATR_t = prior-state EWM updated with finalized TR_t
```

For an entry that can only be placed after finalized bar `t`, bar `t` may update
the risk scale because its result is unavailable until the bar closes. The
result becomes usable on the next real one-minute observation.

A conservative common price-distance scale is:

```text
R_t = max(
    ATR_t,
    close_t * EWMA_slow_sigma_t,
    close_t * RS_slow_sigma_t
)
```

The implementation must normalize percent versus fractional sigma correctly.
Require mature, finite, positive inputs; expose which component determined the
maximum. No universal ATR half-life or multiplier is asserted here.

## Initial stop contract

The stop must represent thesis invalidation while remaining outside ordinary
noise. Let `A_t` be a strictly prior-only structural anchor selected by the
versioned setup type, `R_t` the risk scale, and `P_limit` the worst acceptable
entry price.

Long candidate:

```text
structure_stop = A_t - structure_buffer * R_t
volatility_stop = P_limit - stop_multiplier * R_t
initial_stop = min(structure_stop, volatility_stop)
```

Short candidate:

```text
structure_stop = A_t + structure_buffer * R_t
volatility_stop = P_limit + stop_multiplier * R_t
initial_stop = max(structure_stop, volatility_stop)
```

Taking the wider level prevents the structure anchor from placing the stop
inside the declared ordinary-volatility floor. The resulting smaller quantity,
not a tighter arbitrary stop, should enforce account risk.

Reject the trade intent when:

- the structure or risk inputs are immature, stale or degraded;
- the stop is on the wrong side of the worst acceptable entry;
- the stop distance is below the instrument/noise floor;
- the stop distance exceeds the configured maximum-risk distance;
- the calculated quantity is below the minimum lot;
- any portfolio, margin, freshness or operational gate fails.

The exact anchor rule and all multipliers must be frozen before evaluation.
Examples such as “2 ATR” or “2R” are candidate parameters, not professional
constants.

## Position sizing

The executable system needs an instrument master containing tick size, lot/size
increment, contract multiplier or point value, settlement/quote currency,
margin rules, session calendar, roll identity, fees and funding/borrow rules.
The chart's `min_move` mapping is display formatting and must not be reused as an
execution contract.

```text
trade_risk_budget = min(
    portfolio_equity * configured_risk_fraction,
    remaining_portfolio_open_stop_risk
)

loss_per_unit =
    abs(P_limit - initial_stop) * point_value
    + expected_roundtrip_cost_per_unit
    + conservative_gap_and_slippage_cushion

quantity = floor_to_lot(trade_risk_budget / loss_per_unit)
```

Then apply limits for:

- per-asset notional and stop-risk;
- aggregate open-stop risk;
- gross and net exposure;
- leverage, margin and buying-power buffer;
- correlated clusters such as BTC/ETH and ES/NQ;
- order size/rate and duplicate orders;
- portfolio volatility.

There is no universal risk fraction. It is a governance/risk-limit decision,
not a parameter to maximize on the inspected backtest.

## Entry contract

The first experiment should freeze the existing trend/CUSUM entry conditions so
that exit changes can be attributed correctly.

A finalized target bar creates an immutable `TradeIntent` containing at least:

```text
setup_id
policy_digest
asset / target timeframe
direction and reason codes
source bar and available_at
valid_until / entry TTL
entry reference and worst acceptable entry
initial stop and risk-scale components
risk budget and proposed quantity
data-quality and evidence status
```

Use a bounded marketable-limit entry with a TTL when a maximum entry price is
required to preserve the risk calculation. A plain market order can gap beyond
the pre-entry risk budget. Pending entry must cancel if its setup expires,
freshness fails or the thesis invalidates before fill.

The protective order is activated only after confirmed entry fill and resized
to actual filled quantity. Native venue bracket/conditional orders are
preferred where their semantics are verified; local emulation still requires
persistence, monitoring and reconciliation.

## Trailing and signal exits

For a long position, a research trailing candidate is:

```text
candidate_t = max(
    prior_support_t - structure_buffer * R_t,
    favorable_high_water_mark_(t-1) - trail_multiplier * R_t,
    validated_CUSUM_trail_t
)

effective_stop_t = max(effective_stop_(t-1), candidate_t)
```

The short rule is symmetric with `min`. The stop can tighten but never loosen.
The CUSUM component must be omitted until its incremental ablation passes; it is
currently a post-close chart diagnostic and can be unavailable during warm-up.

The high-water mark and new indicator values from minute/bar `t` may update the
stop only after that observation is finalized. They cannot retroactively trigger
a tighter stop inside the same bar.

Signal invalidation remains a separate soft exit: a flat/opposite trend with
the required CUSUM confirmation creates a close intent at the next eligible
real-minute open. Reversal must be close-first, confirm flat, then create a new
setup; the current atomic `long -> short` target change should not be used for a
broker lifecycle.

A stop closes its `setup_id`. Persistent indicator direction cannot immediately
reopen the same stopped setup; a fresh setup event and optional cooldown are
required.

## Take-profit alternatives

The order engine should support an optional reduce-only take-profit sibling,
but the baseline keeps it disabled.

Registered alternatives should be tested one at a time:

- fixed full-position R-multiple target;
- partial R-multiple target plus trailing remainder;
- opposing strictly prior-only structure target;
- higher-timeframe opposing structure target after cross-TF qualification;
- no target, trail/signal exit only.

If a target and stop are both present, they form an OCO relationship: one fill
cancels or resizes the other. Cancel/fill races and partial fills must still be
reconciled rather than assumed impossible.

## Trade and order state machine

```text
FLAT
  -> ARMED
  -> PENDING_ENTRY
  -> OPEN_PROTECTED
  -> EXIT_PENDING
  -> COOLDOWN
  -> FLAT
```

Required event precedence for each real one-minute observation:

1. kill switch and data-quality incident handling;
2. existing protective stop / liquidation guard;
3. existing target or trailing exit;
4. signal flatten/invalidation;
5. close-before-reversal completion;
6. new entry or rebalance;
7. portfolio and venue reconciliation.

Each command/event needs stable idempotency IDs, `setup_id`, parent/child IDs,
created/acknowledged/partial/filled/canceled/rejected/expired states, quantities,
prices, trigger source, timestamps and reason codes. State must survive restart.

## One-minute replay semantics

Risk exits must be evaluated on every real one-minute candle, independently of
the slower target timeframe. Indicator decisions still use only finalized
target bars.

For a working stop:

- gap beyond the stop fills at the first adverse executable open, not at the
  stale stop price;
- an orderly high/low crossing can use the stop trigger plus the declared
  spread/slippage scenario;
- a stop-limit may remain unfilled and is not the default catastrophic-risk
  exit;
- after an intraminute exit, PnL must not keep the old position through that
  minute's close.

If stop and target both fall inside one 1m candle, OHLC does not reveal which
came first. The primary result should use a conservative stop-first path and
report an optimistic target-first bound. If the conclusion depends on this
choice, evidence is insufficient and trade/quote data is required.

Processing should be:

```text
previous close -> current open mark
gap/working-order processing
intraminute protective-order processing
remaining-position open -> close mark
finalize one-minute observation
update trailing state and commit newly closed target signal
```

## Portfolio rule across assets and timeframes

The 56 streams should remain independent research experiments. They must not
become 56 independent capital allocations.

An executable portfolio needs one net position per instrument. Until signal
scores are calibrated, the safest first cohort chooses one frozen strategy and
timeframe per asset. A later portfolio-construction experiment may aggregate
multiple timeframes under one risk budget, but it must never open seven full
positions for the same asset.

High-timeframe rows identified after the prior matrix are hypotheses for a new
forward cohort, not validated winners. All 1m and 15m default-policy rows failed
the historical audit and should remain outside the candidate cohort unless a
new, frozen experiment passes realistic costs and independent forward evidence.

## Leakage-safe validation sequence

Freeze entry logic and compare exit families incrementally:

| Experiment | Change from frozen entry baseline |
| --- | --- |
| E0 | Existing signal flatten/reversal only |
| E1 | Add immutable catastrophic protective stop |
| E2 | Add structure-plus-volatility initial stop and risk sizing |
| E3 | Add monotonic structure/volatility trail |
| E4 | Add a fixed full-position target |
| E5 | Replace E4 with partial target plus trailing runner |
| E6 | Add one context gate/haircut at a time |

Do not tune these thresholds on the already inspected 180-day matrix. Use
chronological development folds, one untouched holdout, a complete append-only
trial registry, normal and stressed costs, gap scenarios, and parameter-neighbor
stability. Apply multiple-testing controls such as Deflated Sharpe and
Probability of Backtest Overfitting where the trial count permits.

Add trade-level diagnostics:

- initial and realized risk in currency and R units;
- maximum adverse/favorable excursion;
- stop/target/trailing/signal/time exit reason;
- gap slippage and ambiguous-bar counts;
- holding time, turnover and cost share;
- expectancy, tail loss, drawdown and risk-of-ruin scenarios;
- per-selection and capital-netted portfolio results;
- rejected intents and failed risk/data gates.

Only then start a newly frozen append-only forward paper cohort. A venue demo
adapter validates command, bracket, restart and reconciliation mechanics; it
does not validate liquidity or profitability. Real routing remains off until
instrument contracts, portfolio limits, OMS reconciliation, kill switch and
approved evidence gates exist.

## Implementation sequence

1. Introduce versioned `SignalPolicy`, `TradeIntent`, `RiskPolicy`,
   `PositionPlan` and `TradeState` contracts with current behavior reproduced as
   E0.
2. Add an instrument master; do not reuse chart display precision.
3. Extend the common replay/paper ledger with per-minute stops, entry/exit
   priority, partial quantities and restart-safe state.
4. Add initial-stop and risk-size E1/E2 experiments without changing entry.
5. Add trailing and optional target experiments separately.
6. Add a keyed policy registry per asset/timeframe and a capital-netted
   portfolio constructor.
7. Display planned/active entry, stop, optional target, R risk, quantity,
   lifecycle state, data freshness and blocking reason on the chart.
8. Build a venue adapter only after parity, fault-injection and reconciliation
   tests pass; keep real routing disabled.

## Explicitly rejected shortcuts

- Do not connect every visible indicator directly to an order.
- Do not treat the plotted CUSUM trail as the only initial stop.
- Do not use the untrained HMM as money confidence.
- Do not call phase-adjusted volume executable liquidity.
- Do not size from the fast/slow volatility ratio alone.
- Do not optimize entry, stop, target, trail and context gates jointly on one
  window.
- Do not assume a stop fills at its trigger through a gap.
- Do not let seven timeframe streams create seven positions in one asset.
- Do not infer that a fixed take-profit is required merely because brackets can
  support one.

## Professional and primary references

- QuantConnect, separation of Alpha, Portfolio Construction, Risk and Execution,
  and when special order types require a classic/hybrid design:
  <https://www.quantconnect.com/docs/v2/writing-algorithms/algorithm-framework/overview>
- CME, stops at logical invalidation outside normal movement and position size
  derived from stop distance plus account risk:
  <https://www.cmegroup.com/education/courses/trade-and-risk-management/proper-position-size>
- Moskowitz, Ooi and Pedersen, lagged volatility estimates and inverse-volatility
  sizing in time-series momentum:
  <https://w4.stern.nyu.edu/facdir/lpederse/papers/TimeSeriesMomentum.pdf>
- Moreira and Muir, volatility-managed portfolio evidence:
  <https://www.nber.org/papers/w22208>
- Kaminski and Lo, conditions under which stop-loss rules add or subtract value:
  <https://papers.ssrn.com/sol3/papers.cfm?abstract_id=968338>
- Alpaca, bracket/OCO activation, cancel races, partial quantities and trailing
  high-water-mark behavior:
  <https://docs.alpaca.markets/us/docs/orders-at-alpaca>
- IBKR, parent with take-profit and stop-loss child orders:
  <https://ibkrcampus.com/campus/ibkr-api-page/order-types/>
- Bybit, TP/SL, reduce-only, close-on-trigger, unique client IDs and asynchronous
  order acknowledgement:
  <https://bybit-exchange.github.io/docs/v5/order/create-order>
- NautilusTrader, bar execution limitations, gap-through stops and need for
  finer-grained data when stops/targets are tight:
  <https://nautilustrader.io/docs/latest/concepts/backtesting/>
- SEC staff FAQ, automated pre-trade credit/capital, price, size and duplicate
  order controls:
  <https://www.sec.gov/rules-regulations/staff-guidance/trading-markets-frequently-asked-questions/divisionsmarketregfaq-0>
- FINRA, development, independent testing, limited pilots, monitoring and
  reconciliation for algorithmic strategies:
  <https://www.finra.org/rules-guidance/notices/15-09>
- CFTC, simulated-result, spread, impact, cost and profit-guarantee limitations:
  <https://www.cftc.gov/LearnAndProtect/AdvisoriesAndArticles/fraudadv_tradingsystem.html>
