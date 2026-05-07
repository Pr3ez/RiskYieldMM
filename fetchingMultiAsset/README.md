# Multi-Asset Source Layer

This directory stores non-crypto OHLCV/OHLC bars normalized to the same core
parquet contract as the current Bybit kline layer:

```text
timestamp, open, high, low, close, volume, turnover, interval
```

Provider and asset metadata stays in `asset_config.py` and progress/manifests so
the model-facing parquet files remain compatible with HTF feature code that
expects plain OHLCV bars.

Configured Twelve Data fallback/reference assets:

- `EURUSD` from `EUR/USD`
- `USDJPY` from `USD/JPY`
- `XAUUSD` from `XAU/USD`
- `WTIUSD` from `WTI/USD` pending provider symbol verification
- `SPX` from `SPX`
- `NDX` from `NDX`

Configured Databento futures proxies:

- `EURUSD` from `6E.v.0`
- `USDJPY` from `6J.v.0`, inverted to USD/JPY-like prices
- `GC` from `GC.v.0`
- `CL` from `CL.v.0`
- `ES` from `ES.v.0`
- `NQ` from `NQ.v.0`

Configured Yahoo Finance recent-tail futures proxies:

- `EURUSD` from `6E=F`
- `USDJPY` from `6J=F`, inverted to USD/JPY-like prices
- `GC` from `GC=F`
- `CL` from `CL=F`
- `ES` from `ES=F`
- `NQ` from `NQ=F`

## Commands

Store provider keys in the ignored local file:

```bash
cp local_secrets.example.env local_secrets.env
# edit local_secrets.env and set DATABENTO_API_KEY=...
# TWELVE_DATA_API_KEY is optional fallback/reference only
```

`local_secrets.env` is ignored by Git. The fetcher reads it automatically, and
an exported shell variable still takes precedence.

For Databento futures and Yahoo recent-tail checks/fetches, install the optional
market-data adapters once:

```bash
python -m pip install databento yfinance
```

```bash
cd fetchingMultiAsset

# Check Databento access and optional Twelve Data fallback mappings before any
# real backfill.
python preflight_providers.py

# Inspect local coverage for the intended production source mix.
python update_data.py --status --core --htf-only

# Preview the HTF source plan without writes. Auto routing tries Yahoo first
# for recent tails and plans Databento only for assets Yahoo cannot continue.
python update_data.py --core --dry-run --htf-only

# Run the same auto source explicitly.
python update_data.py --providers auto --core --dry-run --htf-only

# Optional Twelve Data fallback/reference checks only.
python update_data.py --providers twelvedata --discover-symbols

# Explicit Databento-only estimate before spending historical-data credits.
python update_data.py --providers databento --core --estimate-only --htf-only

# Explicit Databento-only fetch. A positive cost ceiling is required for actual
# historical fetches; 1m is fetched and requested higher intervals are derived
# locally from those 1m bars.
python update_data.py --providers databento --core --htf-only --max-databento-cost-usd 50

# Explicit Yahoo-only recent-tail plan. Normal --core auto routing already uses
# this path whenever the local gap is inside Yahoo's safe range.
python update_data.py --providers yfinance --core --dry-run --htf-only

# Audit every configured adapter, including Twelve fallback symbols for
# gold/oil/indexes. Do not use this as the normal production fetch command.
python update_data.py --all --dry-run --htf-only
```

Databento futures are deliberately behind explicit cost/fetch gates:

```bash
# Output-path plan only; no credits.
python fetch_databento.py --dry-run

# Metadata cost estimate for a small range before a fetch.
python fetch_databento.py --estimate-cost --assets ES --start 2024-01-02T14:30:00Z --end 2024-01-02T15:30:00Z

# Tiny guarded probe. The command refuses if the estimate is above the ceiling.
python fetch_databento.py --fetch --assets ES --start 2024-01-02T14:30:00Z --end 2024-01-02T14:35:00Z --max-cost-usd 0.01

# Derive the HTF-required 15m futures source locally from fetched 1m bars.
python aggregate_ohlcv.py --symbols ES --provider databento --market futures --source-interval 1m --target-interval 15m
```

Outputs are written as sorted batch files:

```text
fetchingMultiAsset/
  sorted-1m-databento-futures/
    eurusd_databento_sorted_batch_000000.parquet
  sorted-15m-databento-futures/
    eurusd_databento_sorted_batch_000000.parquet
  sorted-1m-yfinance-futures/
    eurusd_yfinance_sorted_batch_000000.parquet
```

The unified fetcher resumes from the latest local timestamp. In `auto` mode,
Yahoo is used for eligible recent tails and Databento is used only when the
local Databento anchor is missing or too old for Yahoo's intraday retention
window. Databento resumes from the latest stored `1m` bar, then derives
requested higher intervals locally. `end-date=now` is capped to a
provider-safe/account-entitled available end whenever Databento is needed. The
fetcher does not synthesize weekend or closed-session candles.

Every multi-asset update starts with a local parquet inventory before any
provider estimate or fetch. The scan is local-only and reports per-asset files,
rows, timestamp ranges, resume boundaries, long missing prefixes, and fragmented
probe-shaped layouts. Use `--skip-local-scan` only when you intentionally want a
faster run without that guard.

Databento may emit degraded-quality day warnings from provider metadata. Treat
those as data-quality notes, not fetch failures. If you ran tiny probes before a
full backfill, remove the ignored local output batches for that asset before the
production run; otherwise resume logic will start from the newest local `1m`
bar it finds.

The parquet schema matches the core Bybit kline OHLCV contract. Non-crypto
sources do not include Bybit-specific auxiliary derivative streams such as
funding, open interest, mark/index premium, or account ratios.

Yahoo Finance is a recent-tail continuation source, not a Databento historical
replacement. The adapter fetches overlap rows first, compares them with recent
Databento closes, drops the current incomplete Yahoo bar, and writes only the
accepted tail into separate `yfinance` roots.
