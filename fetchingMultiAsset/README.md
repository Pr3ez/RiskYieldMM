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

## Commands

Store provider keys in the ignored local file:

```bash
cp local_secrets.example.env local_secrets.env
# edit local_secrets.env and set DATABENTO_API_KEY=...
# TWELVE_DATA_API_KEY is optional fallback/reference only
```

`local_secrets.env` is ignored by Git. The fetcher reads it automatically, and
an exported shell variable still takes precedence.

For Databento futures checks/fetches, install the optional SDK once:

```bash
python -m pip install databento
```

```bash
cd fetchingMultiAsset

# Check Databento access and optional Twelve Data fallback mappings before any
# real backfill.
python preflight_providers.py

# Inspect local coverage for the intended production source mix:
# Databento EURUSD/USDJPY/GC/CL/ES/NQ.
python update_data.py --status --core --htf-only

# Preview the HTF source plan without writes. Databento uses metadata cost
# estimation before any historical fetch.
python update_data.py --core --dry-run --htf-only

# Optional Twelve Data fallback/reference checks only.
python update_data.py --providers twelvedata --discover-symbols

# Estimate selected Databento futures before spending historical-data credits.
python update_data.py --providers databento --core --estimate-only --htf-only

# Fetch selected Databento futures. A positive cost ceiling is required for
# actual historical fetches; 1m is fetched and requested higher intervals are
# derived locally from those 1m bars.
python update_data.py --providers databento --core --htf-only --max-databento-cost-usd 50

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
```

The unified fetcher resumes from the latest local timestamp. Databento resumes
from the latest stored `1m` bar, then derives requested higher intervals
locally. `end-date=now` is capped to a provider-safe/account-entitled available
end for Databento. The fetcher does not synthesize weekend or closed-session
candles.

Databento may emit degraded-quality day warnings from provider metadata. Treat
those as data-quality notes, not fetch failures. If you ran tiny probes before a
full backfill, remove the ignored local output batches for that asset before the
production run; otherwise resume logic will start from the newest local `1m`
bar it finds.

The parquet schema matches the core Bybit kline OHLCV contract. Non-crypto
sources do not include Bybit-specific auxiliary derivative streams such as
funding, open interest, mark/index premium, or account ratios.
