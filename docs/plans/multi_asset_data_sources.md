# Multi-Asset Data Source Plan

Created: 2026-05-06

Current branch decision: the production core fetch uses Bybit for crypto
(`BTCUSDT`, `ETHUSDT`) and Databento GLBX.MDP3 continuous futures proxies for
all non-crypto markets (`EURUSD`, `USDJPY`, `GC`, `CL`, `ES`, `NQ`). Twelve
Data remains implemented as a manual fallback/reference adapter only, because
its historical request limits are not suitable for the full 2021-to-now
backfill.

## Goal

Extend the current Bybit BTC/ETH raw source layer to these non-crypto markets:

- EUR/USD
- USD/JPY
- Gold
- Oil
- S&P 500 index
- Nasdaq index

The target storage contract should stay close to the existing Bybit OHLCV parquet
contract so the later HTF materialization work can compute labels/features per
instrument and merge them into one CatBoost Stage-1 v2 analysis dataset.

## Current Local Contract

The current Bybit fetcher writes time-series parquet files with:

- `timestamp`: UTC, millisecond precision, bar-start timestamp
- `open`, `high`, `low`, `close`
- `volume`
- optional `turnover`
- `interval`

The active HTF workflow currently expects native `1m` and `15m` OHLCV sources,
plus crypto-specific auxiliary streams when available. For non-crypto assets we
should start with OHLCV/OHLC only and add explicit source-availability masks
rather than pretending funding, open interest, long/short ratio, mark, premium,
or Bybit index-price streams exist for every asset.

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

Yahoo/yfinance is suitable only for quick prototypes or daily/limited-recent
checks. The official yfinance docs state that intraday data cannot extend beyond
the last 60 days. That is incompatible with a 2021-to-now HTF backfill.

Conclusion: do not use as a production source for this dataset.

## Implemented Strategy

### Provider-neutral OHLCV adapter contract

The new non-Bybit source layer writes normalized OHLCV files, not a
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

Model-facing parquet columns must stay exactly aligned with the current Bybit
kline contract:

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
sidecar progress/manifests, not in the parquet bars. This keeps the new files
usable by the same HTF OHLCV logic that currently consumes Bybit klines.

Keep the Bybit crypto roots as they are for now. The repo-root orchestrator
coordinates both source layers with the same default period:

```bash
python update_data.py --core
```

That command runs:

```text
Bybit BTCUSDT/ETHUSDT -> Databento EURUSD/USDJPY/GC/CL/ES/NQ
```

Use `python update_data.py --core --dry-run` or
`python update_data.py --core --estimate-only` before a real historical run.
Databento real fetches require a positive `--max-databento-cost-usd` guard.

The later HTF source discovery layer should become asset-aware and accept a
registry instead of hardcoding `btcusdt` file patterns.

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

## Key Design Decisions Captured

1. Gold and oil use exchange-traded futures proxies (`GC`, `CL`) for the core
   dataset.
2. S&P/Nasdaq use futures proxies (`ES`, `NQ`) for the core dataset.
3. FX uses futures proxies for the core dataset: `6E` for `EURUSD`, and `6J`
   inverted into USD/JPY-like OHLC for `USDJPY`.
4. For non-24/7 assets, labels should be computed on each asset's own available
   bar calendar. Do not forward-fill closed-market bars into synthetic candles.
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
