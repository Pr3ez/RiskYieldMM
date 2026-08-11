# Candle Construction and Causal 1m Replay Audit

Date: 2026-07-11
Scope: `Risk_Yield_Meta_Model_Analyst_0_0_1`, canonical OHLCV ingestion, and
indicator optimization for the eight core assets and seven canonical
timeframes.

## Outcome

The Analyst now has a canonical-only replay path that consumes finalized 1m
bars, constructs every selected timeframe incrementally, commits signals only
at scheduled UTC candle close, and fills at the first eligible real 1m open.
It plots fills, normalized equity, drawdown, and position beside the existing
CUSUM, EWMA, volatility-scaled trend, and prototype-regime diagnostics.

This is deliberately called a **current-canonical replay**, not an as-was-live
backtest. The stored parquet rows do not include first-seen time, revision time,
provider vintage, or the time at which a synthetic missing minute became known.

## Audited candle contract

- All canonical timestamps are UTC bar-open timestamps.
- The canonical source is 1m OHLCV.
- Fixed UTC anchors are used for 15m, 1h, 4h, 8h, 12h, and 1d bars.
- Aggregation is first open, maximum high, minimum low, last close, and summed
  volume.
- BTCUSDT and ETHUSDT use a 24/7 calendar.
- CL, ES, EURUSD, GC, NQ, and USDJPY use observed futures sessions. EURUSD is
  based on 6E and USDJPY on inverted 6J; neither is a spot-FX candle series.
- Session gaps longer than 45 minutes are absent. Shorter missing minutes are
  carry-forward zero-volume synthetic rows in the offline canonical artifact.
- Offline `session_minutes_to_close`, close flags, and historical session-tail
  completeness use future rows and are not exposed to replay decisions.

The relevant batch implementation remains
`scripts/feature_engineering/htf_trading_calendar.py`. The replay implementation
is `Risk_Yield_Meta_Model_Analyst_0_0_1/minute_replay.py`.

## Correctness fixes made before replay

1. Bybit could persist the currently forming kline and then resume strictly
   after it, freezing a partial candle. The fetcher now:

   - waits until interval close plus a five-second safety lag;
   - removes an already persisted unclosed tail;
   - refetches and replaces one closed overlap bar on every resume;
   - filters checkpoints and returned rows to the same safe boundary.

   This is required because Bybit documents the REST close as the latest traded
   price when a candle is not closed, and its WebSocket contract separately
   exposes a `confirm` finality flag. See the official
   [REST kline documentation](https://bybit-exchange.github.io/docs/v5/market/kline)
   and [WebSocket kline documentation](https://bybit-exchange.github.io/docs/v5/websocket/public/kline).

2. Session minute-of-day calculations used an Int8 result. Late clock times
   overflowed and could collide with a different historical close minute. Hour
   and minute are now widened to Int32 before arithmetic.

3. Root `update_data.py --end-date` constrained source fetching but did not
   constrain canonical rematerialization unless a second cutoff was supplied.
   Canonical refresh now inherits `--end-date`; an explicit
   `--canonical-end-date` still takes precedence.

## Replay event order

For each real canonical 1m row at time `m`:

1. Finalize any non-empty selected-timeframe bucket whose scheduled UTC end is
   at or before `m`.
2. Advance the causal online trend/EWMA/prototype forward filter and stateful
   CUSUM engine exactly once for that closed target bar.
3. Create or replace the pending desired position. The signal records source
   bar open, availability time, execution eligibility, config hash, and reason.
4. Mark the prior position from the previous real close to the current real
   open.
5. Fill the pending target at this 1m open, after configured latency, fee, and
   adverse slippage.
6. Mark the new position from current open to close.
7. Add the finalized 1m row to the currently forming target candle.

Synthetic rows are excluded. The current files do not reveal when a synthetic
row became inferable, so treating it as known at its nominal timestamp would be
a hidden future-data dependency. Session-tail candles are finalized only at
their scheduled UTC end; the offline historical-close heuristic is not reused.

## Executable indicator mapping

- **CUSUM Trend** supplies a directional agreement gate.
- **EWMA volatility** supplies fast/slow stress rejection and volatility-scaled
  exposure.
- **Volatility-scaled trend** supplies direction, alignment, path quality, and
  developing/aligned thresholds. Its score continues to use prior-bar
  volatility.
- **Prototype regime** supplies a forward-filtered change-risk veto. The
  prototypes are fixed and untrained, so direction gating is optional and the
  values are not presented as calibrated probabilities.

The default mapping is intentionally conservative and is not presumed to have
alpha. A current 365-day BTCUSDT/1h baseline at 1 bp fee plus 1 bp slippage per
unit turnover was negative in the implementation smoke test; that is a useful
rejection, not a parameter-tuning failure to hide.

## Walk-forward optimization contract

The optimizer searches a fixed, bounded grid across CUSUM sensitivity,
EWMA/trend horizon templates and thresholds, prototype change-risk threshold,
and the fast/slow volatility gate.

- Hidden rows before the requested research start warm recursive state only.
- Development validation is chronological and expanding-prefix based.
- The selection objective is median fold net Sharpe at 2x supplied costs minus
  one-half of the fold Sharpe interquartile range.
- Minimum fills and maximum drawdown are hard constraints.
- The latest 20% of the requested research period is opened only after one
  configuration has been selected.
- Every candidate, fold, cost assumption, result, and hash is appended to a
  JSONL registry.
- The strongest possible status is `accepted_for_paper_trading`; live capital
  is never automatically authorized.

This separation matters because optimizing a finite-sample selection criterion
can itself overfit; see Cawley and Talbot,
[On Over-fitting in Model Selection](https://jmlr.org/papers/v11/cawley10a.html).
Finance-specific multiple-testing risks are described by
[The Probability of Backtest Overfitting](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253),
[The Deflated Sharpe Ratio](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551),
and White's
[Reality Check for Data Snooping](https://onlinelibrary.wiley.com/doi/abs/10.1111/1468-0262.00152).

## What the current PnL does and does not mean

The replay ledger is a normalized economic proxy. It includes next-open
execution timing, fractional turnover, fees, adverse slippage, minute
mark-to-market, equity, drawdown, exposure, and breakeven all-in cost.

It does **not** yet model instrument-specific contract multipliers, tick sizes,
continuous-futures rolls, funding, borrow, historical spread, queue position,
partial fills, volume participation, or nonlinear market impact. Real trading
costs vary by trade size, security, time, and venue; a single universal bps
assumption is not production evidence. See Frazzini, Israel, and Moskowitz,
[Trading Costs](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3229719).

## Forward validation added after this audit

The first, second, and sixth items from the original production-gate list now
have a concrete implementation. Root `update_data.py --live-start` runs a
background finalized-1m service, journals immutable first-seen and revision
events in a SHA-256 chained SQLite WAL store, checkpoints all indicator/ledger
state, and exposes 56 forward paper streams in the chart. Catch-up signals are
suppressed, and actual provider observation time controls fill eligibility.

The current signal mapping remains rejected rather than promoted: 13 of 14
BTCUSDT/ES baseline selections lost after 1 bp fee plus 1 bp slippage, and the
only winner had four round trips. See
`docs/research/background_live_data_and_forward_paper_2026-07-11.md` for the
runtime commands, provider-grade matrix, and verification results.

## Remaining production gates

Before any strategy is eligible for live capital:

1. Add licensed Databento Live coverage for the six CME-linked assets; Yahoo is
   deliberately shown as delayed rather than trading-grade live.
2. Add exchange calendars or provider watermarks for early session closes.
3. Add an instrument registry and complete execution-cost model.
4. Add DSR/SPA or Reality-Check multiple-testing gates and parameter-neighbor
   stability checks to the paper-trading promotion stage.
5. Require a predeclared minimum forward duration/trade count and positive
   doubled-cost paper evidence before human live review.
