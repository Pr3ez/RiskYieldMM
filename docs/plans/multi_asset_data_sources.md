# Multi-Asset Data Source Plan

Created: 2026-05-06
Status: implemented source layer, with Databento historical data plus Yahoo
recent-tail continuation

Current branch decision: the production core fetch uses Bybit for crypto
(`BTCUSDT`, `ETHUSDT`) and an automatic non-crypto route for
`EURUSD`, `USDJPY`, `GC`, `CL`, `ES`, and `NQ`. Databento GLBX.MDP3 continuous
futures remain the historical source of truth. Yahoo Finance is used only for
validated recent-tail continuation when the local Databento anchor is recent
enough; otherwise Databento is the fallback. Twelve Data remains implemented as
a manual fallback/reference adapter only, because its historical request limits
are not suitable for the full 2021-to-now backfill.

## Goal

Maintain one reproducible core raw source workflow for these assets:

- BTCUSDT
- ETHUSDT
- EUR/USD futures proxy
- USD/JPY futures proxy
- Gold futures
- Oil futures
- S&P 500 futures
- Nasdaq futures

The target storage contract follows the shared OHLCV parquet contract so HTF
materialization can compute features and labels per asset. Stage-1 can then
choose one target asset and optionally join causal context from the others.

## Current Local Contract

The shared model-facing raw bar files use:

- `timestamp`: UTC, millisecond precision, bar-start timestamp
- `open`, `high`, `low`, `close`
- `volume`
- optional `turnover`
- `interval`

The active HTF workflow expects native `1m` and `15m` OHLCV sources for every
asset, plus crypto-specific auxiliary streams when available. Non-crypto assets
start as OHLCV-only assets; funding, open interest, long/short ratio, mark,
premium, and Bybit index-price streams are not fabricated for them.

## Provider Findings

### Twelve Data

Twelve Data is implemented as a fallback/reference adapter, not the core
production backfill source. Its `time_series` endpoint returns historical OHLC
time series and volume where applicable for many instrument types, including
examples such as `EUR/USD`. It supports intraday intervals including `1min`,
`5min`, `15min`, `1h`, `4h`, and `8h`, plus date range parameters and
`timezone=UTC`.

Advantages:

- One REST shape for FX, commodities, indices, stocks, ETFs, and crypto.
- Directly maps to our OHLCV parquet contract.
- Supports `1min` and `15min`, which match the current HTF source contract.
- `8h` exists at the API level, though we should still keep local derivation
  available for compatibility.

Risks:

- Historical depth varies by instrument and plan.
- `outputsize` max is 5000 rows per request, so full backfill must paginate and
  can consume too many requests for the 2021-to-now core run.
- Some instruments have no real exchange volume; volume should be nullable and
  accompanied by `volume_type`.
- Symbol names for commodities/indices must be confirmed with the provider's
  search/list endpoints before implementation.

Candidate mapping:

| Canonical id | Likely Twelve Data symbol | Notes |
|---|---|---|
| `EURUSD` | `EUR/USD` | Spot FX. |
| `USDJPY` | `USD/JPY` | Spot FX. |
| `XAUUSD` | `XAU/USD` | Confirm with symbol search. |
| `WTIUSD` | `WTI/USD` or provider-specific oil symbol | Confirm with symbol search. |
| `SPX` | `SPX` / S&P 500 index symbol | Confirm exchange/type. |
| `NDX` or `IXIC` | Nasdaq 100 or Nasdaq Composite symbol | Decide index target first. |

### OANDA v20

OANDA has a clean candlestick endpoint with midpoint, bid, and ask candles,
UTC timestamps, a `complete` flag, and tick-volume-like `volume`. It supports
granularities such as `M1` and `D`, and examples include `EUR_USD` and
`USD_JPY`.

Advantages:

- Very clean candle model for FX-style data.
- Can request bid/ask as well as midpoint, which is useful for later spread
  features.
- Good pagination shape: max 5000 candles per request.
- Account-instruments endpoint can discover the actual tradable instruments for
  the account.

Risks:

- Requires an OANDA account and token.
- Tradeable instruments depend on regulatory division/account. In the US,
  OANDA access is generally FX-focused; CFDs for gold/oil/indices may not be
  available.
- CFD instruments are broker-specific, not exchange prints.

Use OANDA if we have an account whose `/accounts/{accountID}/instruments`
response includes the required metals, oil, and index CFDs. Otherwise it is not
a reliable all-market source for this project.

### Databento

Databento is the best candidate for exchange-traded futures proxies:

- Gold: COMEX `GC`
- Oil: NYMEX `CL`
- S&P 500: CME `ES`
- Nasdaq: CME `NQ`
- Core FX futures proxies: CME `6E` and `6J`

It provides OHLCV schemas such as `ohlcv-1m`, `ohlcv-1h`, and `ohlcv-1d`, with
`ts_event` as the start of the aggregation period.

Advantages:

- Exchange-traded data with real volume.
- Strong fit for tradable futures proxies.
- Good for `GC`, `CL`, `ES`, `NQ`, `6E`, and `6J` when we want futures rather
  than cash/CFD.
- Better data provenance than broker CFD or scraped sources.

Risks:

- Requires paid data/API key and exchange licensing terms.
- Continuous futures need explicit roll policy and possibly back-adjustment.
- Spot FX requested by the user is not the same as currency futures. `6J`
  is quoted differently from USD/JPY and would need normalization/inversion if
  used as a proxy.

The current branch uses Databento for the core non-crypto dataset because the
priority is reproducible, tradable futures exposure with real exchange volume.
For exact spot FX-only experiments, use Twelve Data/OANDA/EODHD explicitly as a
separate reference source.

### EODHD

EODHD is a possible practical source for FX and indices. Its intraday API
supports `1m`, `5m`, and `1h`, returns UTC timestamps plus OHLCV fields, and
documents 1-minute FX/crypto availability since 2009.

Advantages:

- REST response maps cleanly to our OHLCV contract.
- Clear UTC timestamp semantics.
- Useful fallback for FX and potentially indices.

Risks:

- It explicitly warns that CFD/Forex prices are indicative and can differ from
  actual market prices.
- Intraday range is limited per request (`1m` max 120 days), so backfill must
  chunk requests.
- Commodity coverage is newer/beta and should not be assumed to provide the
  same intraday contract.

### Alpha Vantage

Alpha Vantage is useful for supplemental daily data, but not as the main HTF
source. FX intraday exists as a premium endpoint with `1min`, `5min`, `15min`,
`30min`, and `60min` OHLC. Commodity endpoints for gold and WTI are daily or
higher, and index endpoints are daily/weekly/monthly.

Conclusion: not suitable as the primary source if we want `1m`/`15m` HTF-style
multi-asset features across all requested instruments.

### Yahoo/yfinance

Yahoo/yfinance is suitable only for recent-tail continuation and validation
checks. Its intraday retention is too short for the 2021-to-now HTF backfill,
but it can update the newest rows when the local Databento anchor is recent
enough and overlap validation passes.

Conclusion: use Yahoo automatically for eligible recent tails only. Do not use
it as the historical source of truth.

## Implemented Strategy

### Provider-neutral OHLCV adapter contract

The normalized non-crypto source layer writes OHLCV files, not a
provider-specific model-facing dataset. The normal core output roots are
Databento futures roots:

Implementation root:

```text
fetchingMultiAsset/
  sorted-1m-databento-futures/
    {canonical_id}_databento_sorted_batch_000000.parquet
  sorted-15m-databento-futures/
    {canonical_id}_databento_sorted_batch_000000.parquet
```

Model-facing parquet columns must stay aligned with the shared OHLCV contract
used by crypto and non-crypto roots:

```text
timestamp           datetime[ms, UTC], bar start
open                float64
high                float64
low                 float64
close               float64
volume              float64 nullable
turnover            float64 nullable
interval            string
```

Provider metadata (`symbol`, `source_symbol`, `provider`, `asset_class`,
`market_type`, `volume_type`, session notes) belongs in the asset registry and
sidecar progress/manifests, not in the parquet bars. This keeps every source
usable by the same HTF OHLCV logic.

Crypto roots remain in `fetchingByBit/`. The repo-root orchestrator coordinates
both source layers with the same default period:

```bash
python update_data.py --core
```

That command runs:

```text
Bybit BTCUSDT/ETHUSDT -> multi-asset auto source
```

Use `python update_data.py --core --dry-run` or
`python update_data.py --core --estimate-only` before a real historical run.
The multi-asset auto source tries Yahoo Finance first for validated recent
tails and uses Databento only for assets whose local gap is outside Yahoo's
intraday range or whose Databento anchor is missing. Databento real fetches
require a positive `--max-databento-cost-usd` guard.

The HTF source discovery layer is asset-aware through
`scripts/feature_engineering/htf_asset_registry.py`.

### Core Databento mappings

The current core non-crypto source mix is:

| Canonical id | Databento symbol | Normalization |
|---|---|---|
| `EURUSD` | `6E.v.0` | CME Euro FX futures, USD per EUR. |
| `USDJPY` | `6J.v.0` | CME Japanese Yen futures inverted into a USD/JPY-like OHLC path. |
| `GC` | `GC.v.0` | COMEX gold continuous futures. |
| `CL` | `CL.v.0` | NYMEX WTI crude continuous futures. |
| `ES` | `ES.v.0` | CME E-mini S&P 500 continuous futures. |
| `NQ` | `NQ.v.0` | CME E-mini Nasdaq 100 continuous futures. |

Databento fetches `1m` OHLCV once per asset and derives requested higher
intervals locally. `end-date=now` is capped to the provider-safe and
account-entitled available end. Provider degraded-quality day warnings should be
recorded as data-quality notes before model training.

### Twelve Data fallback/reference

Twelve Data remains available for exact/cash-style references:

- `EUR/USD`
- `USD/JPY`
- `XAU/USD`
- WTI crude candidate symbols
- S&P 500 index candidate symbols
- Nasdaq 100 vs Nasdaq Composite candidate symbols

Use it explicitly with `--providers twelvedata` for checks or small reference
fetches. Do not use `--all` as the normal production backfill command, because
it includes fallback adapters and can generate large Twelve Data request plans.

### Yahoo Finance recent-tail continuation

Yahoo Finance can provide the same futures family for recent rows only:

| Canonical id | Yahoo symbol | Normalization |
|---|---|---|
| `EURUSD` | `6E=F` | Euro FX futures, USD per EUR. |
| `USDJPY` | `6J=F` | Japanese Yen futures inverted into a USD/JPY-like OHLC path. |
| `GC` | `GC=F` | Gold futures recent-tail proxy. |
| `CL` | `CL=F` | WTI crude futures recent-tail proxy. |
| `ES` | `ES=F` | E-mini S&P 500 futures recent-tail proxy. |
| `NQ` | `NQ=F` | E-mini Nasdaq 100 futures recent-tail proxy. |

Yahoo rows are stored under separate `sorted-*-yfinance-futures/` roots. They
are accepted only if the fetched overlap matches recent Databento closes within
the configured tolerance. The normal `--core` multi-asset route uses this source
automatically when the local gap is inside Yahoo's safe range, then falls back
to Databento for older/missing spans. This keeps Databento as the historical
source of truth and prevents silent provider mixing.

## Key Design Decisions Captured

1. Gold and oil use exchange-traded futures proxies (`GC`, `CL`) for the core
   dataset.
2. S&P/Nasdaq use futures proxies (`ES`, `NQ`) for the core dataset.
3. FX uses futures proxies for the core dataset: `6E` for `EURUSD`, and `6J`
   inverted into USD/JPY-like OHLC for `USDJPY`.
4. For non-24/7 assets, labels should be computed on each asset's own canonical
   market-open calendar. Do not forward-fill closed-market bars; only small
   missing minutes inside inferred open sessions may be carry-forward filled
   with explicit synthetic/open-gap flags.
5. Volume must be nullable and typed. FX/CFD tick volume is not equivalent to
   exchange volume.

## Source Links

- Twelve Data API documentation: https://twelvedata.com/docs
- Twelve Data historical prices support note: https://support.twelvedata.com/en/articles/5656039-how-to-get-historical-prices
- OANDA instrument candles: https://developer.oanda.com/rest-live-v20/instrument-ep/
- OANDA account instruments: https://developer.oanda.com/rest-live-v20/account-ep/
- Databento schemas and OHLCV formats: https://databento.com/docs/schemas-and-data-formats
- Databento futures data: https://databento.com/futures
- EODHD intraday API: https://eodhd.com/financial-apis/intraday-historical-data-api
- Alpha Vantage documentation: https://www.alphavantage.co/documentation/
- yfinance price history docs: https://ranaroussi.github.io/yfinance/reference/yfinance.price_history.html
