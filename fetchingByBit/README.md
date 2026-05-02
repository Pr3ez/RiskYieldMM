# Bybit Data Fetching Pipeline

> **Last Updated:** 2026-05-02
> **Data Range:** 2021-01-01 to present  
> **Active HTF Source Contract:** native `1m`/`15m` OHLCV plus derivatives context

For the current HTF workflow, the canonical operational instructions are in the
root [`README.md`](../README.md), section "Fetch and Verify HTF Source Data".
This file is a local reference for the Bybit fetcher directory itself.

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Data Sources](#data-sources)
3. [Directory Structure](#directory-structure)
4. [Scripts](#scripts)
5. [How to Update Data](#how-to-update-data)
6. [8H Aggregation Logic](#8h-aggregation-logic)
7. [Data Quality & Gaps](#data-quality--gaps)
8. [Technical Details](#technical-details)
9. [Troubleshooting](#troubleshooting)

---

## Overview

This pipeline fetches public market data from Bybit API for BTCUSDT linear
perpetual futures and prepares local parquet sources for the ML research
workflow.

### Key Facts

| Aspect | Details |
|--------|---------|
| **Symbol** | BTCUSDT Linear Perpetual |
| **Exchange** | Bybit |
| **Start Date** | 2021-01-01 |
| **Active HTF inputs** | `1m` and `15m` source data plus derivative context |
| **Compatibility output** | 8h aggregate derived from 4h data |
| **Update Frequency** | Run daily or as needed |

### How 8H Aggregation Fits Now

**Bybit API does NOT provide 8h interval data.** Available intervals are: 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d, 1w, 1M.

The current `notebooks/htf_pythonscript.py` materializer does not use 8h files
as primary source data. It uses native `1m`/`15m` data and derives HTF regime
batches internally. The 4h → 8h aggregate is retained for older/supporting
workflows because:
- 8h aligns with funding rate cycles (every 8 hours)
- Reduces noise vs 4h while maintaining responsiveness
- Matches our position holding period

---

## Data Sources

### Primary Sources (from Bybit API)

| Source | Endpoint | Timeframes Fetched | Key Columns |
|--------|----------|-------------------|-------------|
| **OHLCV Klines** | `/v5/market/kline` | 1m, 5m, 15m, 1h, 4h, 1d | open, high, low, close, volume, turnover |
| **Open Interest** | `/v5/market/open-interest` | 5m, 15m, 1h, 4h, 1d | openInterest |
| **Funding Rate** | `/v5/market/funding/history` | 8h (native) | fundingRate, fundingRateTimestamp |
| **Long/Short Ratio** | `/v5/market/account-ratio` | 5m, 15m, 1h, 4h, 1d | buyRatio, sellRatio |
| **Mark Price** | `/v5/market/mark-price-kline` | 1m, 5m, 15m, 1h, 4h, 1d | open, high, low, close |
| **Index Price** | `/v5/market/index-price-kline` | 1m, 5m, 15m, 1h, 4h, 1d | open, high, low, close |
| **Premium Price** | `/v5/market/premium-index-price-kline` | 1m, 5m, 15m, 1h, 4h, 1d | open, high, low, close |

### Aggregated Sources (created locally)

| Source | Created From | Output File |
|--------|--------------|-------------|
| OHLCV 8h | 4h klines | `sorted-8h-bybit-linear/btcusdt_8h.parquet` |
| Open Interest 8h | 4h OI | `open-interest-8h-bybit-linear/btcusdt_open_interest_8h.parquet` |
| Mark Price 8h | 4h mark | `mark-price-8h-bybit-linear/btcusdt_mark_price_8h.parquet` |
| Index Price 8h | 4h index | `index-price-8h-bybit-linear/btcusdt_index_price_8h.parquet` |
| Premium Price 8h | 4h premium | `premium-price-8h-bybit-linear/btcusdt_premium_price_8h.parquet` |
| L/S Ratio 8h | 4h ratio | `long-short-ratio-8h-bybit-linear/btcusdt_ls_ratio.parquet` |

---

## Directory Structure

```
fetchingByBit/
├── README.md                          # This file
├── fetch_bybit_market_data.py         # Main fetcher (1371 lines)
├── aggregate_to_8h.py                 # 4h → 8h aggregation (~683 lines)
├── update_data.py                     # Master update script (~220 lines)
├── gap_filler.py                      # Gap detection/filling utility
├── data_quality_monitor.py            # Data quality checks
│
├── .fetch_progress.json               # Resume state for fetcher
│
├── sorted-{TF}-bybit-linear/          # OHLCV klines by timeframe
│   └── btcusdt_linear_sorted_batch_*.parquet
│
├── open-interest-{TF}-bybit-linear/   # Open Interest
│   └── btcusdt_oi.parquet
│
├── funding-rate-bybit-linear/         # Funding Rate (native 8h)
│   └── btcusdt_funding_rate.parquet
│
├── long-short-ratio-{TF}-bybit-linear/  # Long/Short Ratio
│   └── btcusdt_ls_ratio.parquet
│
├── mark-price-{TF}-bybit-linear/      # Mark Price
│   └── btcusdt_mark.parquet (4h) or btcusdt_mark_price_8h.parquet (8h)
│
├── index-price-{TF}-bybit-linear/     # Index Price
│   └── btcusdt_index.parquet (4h) or btcusdt_index_price_8h.parquet (8h)
│
└── premium-price-{TF}-bybit-linear/   # Premium Price
    └── btcusdt_premium.parquet (4h) or btcusdt_premium_price_8h.parquet (8h)
```

---

## Scripts

### 1. `fetch_bybit_market_data.py` - Main Fetcher

**Purpose:** Fetch raw data from Bybit API for all sources and timeframes.

```bash
# Fetch all sources (resumable)
python fetch_bybit_market_data.py
```

**Key Features:**
- **Resumable:** Saves progress to `.fetch_progress.json`
- **Forward pagination:** Fetches oldest → newest
- **No overwrites:** Creates new batch files (incrementing index)
- **Rate limiting:** Uses request pacing and Bybit response headers where available

For normal operation use `update_data.py`; it wraps fetch, aggregation, and
verification.

### 2. `aggregate_to_8h.py` - 8H Aggregation

**Purpose:** Aggregate all 4h data sources to 8h timeframe.

```bash
# Aggregate all sources
python aggregate_to_8h.py

# Dry run (show what would be done)
python aggregate_to_8h.py --dry-run

# Force rebuild (ignore existing 8h data)
python aggregate_to_8h.py --force

# Verify existing aggregation
python aggregate_to_8h.py --verify
```

**Key Features:**
- **Resumable:** Only processes new 4h data since last 8h timestamp
- **Schema matching:** Adapts output to match existing file schema
- **Deduplication:** Uses `unique(subset=["timestamp"], keep="last")`

### 3. `update_data.py` - Master Update Script

**Purpose:** One command to update everything (fetch + aggregate + verify).

```bash
# Full update (recommended for daily use)
python update_data.py

# Check status only
python update_data.py --status

# Fetch only (no aggregation)
python update_data.py --fetch-only

# Aggregate only (no fetching)
python update_data.py --aggregate-only

# Dry run
python update_data.py --dry-run
```

**Typical Output:**
```
================================================================================
                        BYBIT DATA UPDATE PIPELINE
================================================================================

📊 STATUS CHECK
------------------------------------------------------------
Latest 8h bar: 2026-01-18 08:00:00+00:00
Staleness: 0.4 hours
Status: ✓ UP TO DATE

(or if behind:)
Status: ⚠ STALE - 31.2 days behind

📡 FETCHING NEW DATA
------------------------------------------------------------
[1/34] sorted-1m-bybit-linear: ✓ Up to date
[2/34] sorted-4h-bybit-linear: ✓ Fetched 186 new rows
...

🔄 AGGREGATING 4H → 8H
------------------------------------------------------------
OHLCV klines: ✓ Added 93 new 8h bars
Open Interest: ✓ Added 93 new 8h bars
...

✅ UPDATE COMPLETE
```

---

## How to Update Data

### Daily Update (Recommended)

```bash
cd /media/przem/linux_data/RiskYieldMM\ \(Copy\)/fetchingByBit
conda activate /media/przem/linux_data/conda/envs/ml_env
python update_data.py
```

### With Logging

```bash
python update_data.py 2>&1 | tee update_$(date +%Y%m%d_%H%M%S).log
```

### Cron Job (Optional)

```bash
# Add to crontab -e (run daily at 00:30 UTC)
30 0 * * * cd /path/to/fetchingByBit && /path/to/conda/envs/ml_env/bin/python update_data.py >> /path/to/logs/update.log 2>&1
```

---

## 8H Aggregation Logic

### OHLCV Klines

```
8h bar at timestamp T uses 4h bars from T to T+7:59:59

Example: 8h bar at 08:00 uses:
  - 4h bar at 08:00 (covers 08:00-11:59:59)
  - 4h bar at 12:00 (covers 12:00-15:59:59)

Aggregation rules:
  - open  = FIRST 4h bar's open
  - high  = MAX of both 4h bars' high
  - low   = MIN of both 4h bars' low
  - close = LAST 4h bar's close
  - volume = SUM of both 4h bars' volume
  - turnover = SUM of both 4h bars' turnover
```

### Open Interest

```
OI is a snapshot value (not a flow).
8h bar uses LAST 4h value in the period.

Example: 8h bar at 08:00
  - Uses OI from 12:00 4h bar (end of period)
```

### Long/Short Ratio

```
L/S Ratio represents account positioning sentiment.
8h bar uses MEAN of 4h values (average sentiment).

Example: 8h bar at 08:00
  - buyRatio = mean(08:00_buy, 12:00_buy)
  - sellRatio = mean(08:00_sell, 12:00_sell)
```

### Mark/Index/Premium Prices

```
Same as OHLCV: first/max/min/last for O/H/L/C
(No volume for these sources)
```

### Leakage Prevention

**Critical:** We use `dt.truncate("8h")` which floors timestamps to period START.

```
8h bar timestamp = START of period
  - 00:00 bar covers 00:00-07:59:59
  - 08:00 bar covers 08:00-15:59:59
  - 16:00 bar covers 16:00-23:59:59

This ensures NO FUTURE DATA leaks into the 8h bar.
```

---

## Data Quality & Gaps

### Current Data Status (2026-01-18)

| Source | 8h Rows | 8h Gaps | Start Date | Status |
|--------|---------|---------|------------|--------|
| OHLCV Klines | 5,531 | 0 | 2021-01-01 | ✅ |
| Open Interest | 5,531 | 0 | 2021-01-01 | ✅ |
| Mark Price | 5,531 | 0 | 2021-01-01 | ✅ |
| Index Price | 5,531 | 0 | 2021-01-01 | ✅ |
| Premium Price | 5,531 | 0 | 2021-01-01 | ✅ |
| L/S Ratio | 5,087 | 1 (2 bars) | 2021-05-28 | ⚠️ |
| Funding Rate | 5,531 | 0 | 2021-01-01 | ✅ |

### Known Gaps

#### L/S Ratio Gap
- **Gap:** 2021-08-17 08:00 → 2021-08-18 08:00 (24h = 2 missing 8h bars)
- **Cause:** Historical Bybit API outage
- **Impact:** 2 out of 5,087 rows (0.04%)
- **Recommendation:** Forward-fill in ML pipeline

#### L/S Ratio Late Start
- **Issue:** L/S ratio data starts 2021-05-28 (not 2021-01-01)
- **Missing:** ~444 8h bars at beginning
- **Cause:** Bybit didn't provide L/S ratio data before this date
- **Recommendation:** Use neutral value (0.5) or drop those rows

### Incomplete 8H Bars

Some 8h bars are aggregated from only 1 of 2 expected 4h bars:
- Latest bar (current day) may only have 1 4h bar
- Some historical periods due to 4h API gaps

These are still valid but less precise.

---

## Technical Details

### API Rate Limits

| Endpoint | Rate Limit | Our Delay |
|----------|------------|-----------|
| Market data | 10 req/sec | 0.15 sec between requests |
| All endpoints | 120 req/min | Automatic backoff on 429 |

### Resume Mechanism

**Fetcher (`.fetch_progress.json`):**
```json
{
  "klines_4h": {
    "last_timestamp_ms": 1737187200000,
    "last_batch_index": 42
  },
  ...
}
```

**Aggregator:**
- Reads max timestamp from existing 8h file
- Filters 4h data to only process rows after that timestamp
- Concatenates new 8h bars to existing file

### Data File Formats

All files are **Parquet** format with:
- Timestamp column: `datetime64[ns, UTC]`
- Sorted by timestamp ascending
- No duplicates (deduped on write)

### Validation Checks

The pipeline automatically validates:
1. Timestamps are sorted ascending
2. No duplicate timestamps
3. No gaps > expected interval
4. Column schema matches expected

---

## Troubleshooting

### "Schema mismatch" Error

**Cause:** Existing 8h file has different columns than new aggregated data.

**Fix:** The aggregator now auto-adapts by selecting only columns that exist in the existing file.

### "Rate limit exceeded" (429 Error)

**Cause:** Too many API requests.

**Fix:** 
1. Wait a few minutes
2. Re-run - the script will resume from where it left off

### "No new data to fetch"

**Cause:** Data is already up to date.

**Check:** Run `python update_data.py --status` to see current staleness.

### Gaps in Lower Timeframes (5m, 15m)

**Note:** These are historical Bybit API gaps, not caused by our pipeline.
- 4h and 8h data are clean
- Lower timeframes have ~14,000 gap entries
- Not critical for ML pipeline (we use 8h)

### Missing L/S Ratio Before May 2021

**Cause:** Bybit didn't provide this data before 2021-05-28.

**Handling options:**
1. Fill with neutral (0.5 buyRatio, 0.5 sellRatio)
2. Drop those rows entirely
3. Train separate model for pre-May-2021 period

---

## Appendix: Full Fetch Sources

```python
FETCH_SOURCES = [
    # OHLCV Klines (6 timeframes)
    ("klines", "1m"), ("klines", "5m"), ("klines", "15m"),
    ("klines", "1h"), ("klines", "4h"), ("klines", "1d"),
    
    # Open Interest (6 timeframes)
    ("oi", "5m"), ("oi", "15m"), ("oi", "1h"),
    ("oi", "4h"), ("oi", "8h"), ("oi", "1d"),
    
    # Funding Rate (native 8h only)
    ("funding", "8h"),
    
    # Long/Short Ratio (3 timeframes)
    ("ls_ratio", "1h"), ("ls_ratio", "4h"), ("ls_ratio", "8h"),
    
    # Mark Price (6 timeframes)
    ("mark", "1m"), ("mark", "5m"), ("mark", "15m"),
    ("mark", "1h"), ("mark", "4h"), ("mark", "1d"),
    
    # Index Price (6 timeframes)
    ("index", "1m"), ("index", "5m"), ("index", "15m"),
    ("index", "1h"), ("index", "4h"), ("index", "1d"),
    
    # Premium Price (6 timeframes)
    ("premium", "1m"), ("premium", "5m"), ("premium", "15m"),
    ("premium", "1h"), ("premium", "4h"), ("premium", "1d"),
]
# Total: 34 source/timeframe combinations
```

---

## Quick Reference

```bash
# Check status
python update_data.py --status

# Full update
python update_data.py

# Fetch only
python update_data.py --fetch-only

# Aggregate only
python update_data.py --aggregate-only

# Verify 8h aggregation
python aggregate_to_8h.py --verify
```

---

*For questions or issues, check the troubleshooting section above or review the script source code.*
