# Part 2: Raw Features

> **Navigation:** [README](README.md) | [Part 0: Convention](Part_0_Convention.md) | [Part 1: Groups](Part_1_Groups.md) | **Part 2: Raw** | [Part 3: Approved](Part_3_Approved.md) | [Part 3 (2)](Part_3_Approved2.md) | [Part 4: Suggestions](Part_4_Suggestions.md) | [Part 5: Disapproved](Part_5_Disapproved.md)

---

These are unmodified columns from our data sources. No engineering applied.
This part documents what data we have available—the foundation for all engineered features.
Prefix convention: `RAW_[groups]_featureName_[form]_[norm]`

**Normalization suffix:** `_N` = Normalized (scale-invariant), `_NN` = Not Normalized (scale-dependent)

**Academic Reference:** He, Manela, Ross & von Wachter (2024). *"Fundamentals of Perpetual Futures."* arXiv:2212.06888v6

### Price Features (RAW_P_*_abs_NN)

Absolute price levels from different price types.

| Feature | Groups/Categories | Form | Description |
|---------|-------------------|------|-------------|
| `RAW_P_open_abs_NN` | Price | Absolute | First traded price in 8h period |
| `RAW_P_high_abs_NN` | Price | Absolute | Highest traded price in 8h period |
| `RAW_P_low_abs_NN` | Price | Absolute | Lowest traded price in 8h period |
| `RAW_P_close_abs_NN` | Price | Absolute | Last traded price in 8h period |
| `RAW_P_markOpen_abs_NN` | Price | Absolute | Fair price at period start (used for PnL/liquidations) |
| `RAW_P_markHigh_abs_NN` | Price | Absolute | Highest fair price in period |
| `RAW_P_markLow_abs_NN` | Price | Absolute | Lowest fair price in period |
| `RAW_P_markClose_abs_NN` | Price | Absolute | Fair price at period end |
| `RAW_P_indexOpen_abs_NN` | Price | Absolute | Weighted avg spot price (multiple exchanges) at period start |
| `RAW_P_indexHigh_abs_NN` | Price | Absolute | Highest spot price in period |
| `RAW_P_indexLow_abs_NN` | Price | Absolute | Lowest spot price in period |
| `RAW_P_indexClose_abs_NN` | Price | Absolute | Spot price at period end |

### Temporal Features (RAW_TM_*)

Calendar and timing data for time-based feature engineering.

| Feature | Groups/Categories | Form | Description |
|---------|-------------------|------|-------------|
| `RAW_TM_timestamp` | Temporal | Datetime | Period start timestamp (UTC). Used for temporal features. |

### Liquidity Features (RAW_L_*_abs_NN)

Market activity and participation measures.

| Feature | Groups/Categories | Form | Description |
|---------|-------------------|------|-------------|
| `RAW_L_volume_abs_NN` | Liquidity | Absolute | Total BTC volume traded in 8h period |
| `RAW_L_turnover_abs_NN` | Liquidity | Absolute | Total USD value traded (volume × price) |

### Liquidity + Sentiment Features (RAW_L_S_*_abs_NN)

Market activity that also reveals positioning.

| Feature | Groups/Categories | Form | Description |
|---------|-------------------|------|-------------|
| `RAW_L_S_openInterest_abs_NN` | Liquidity, Sentiment | Absolute | Total open contracts (BTC) at period end. Rising = new money, falling = closing. |

### Funding Features (RAW_F_I_S_*_pct_N)

Perpetual-specific mechanism with interest and sentiment implications.

| Feature | Groups/Categories | Form | Description |
|---------|-------------------|------|-------------|
| `RAW_F_I_S_fundingRate_pct_N` | Funding, Interest, Sentiment | Percentage | Rate paid between longs/shorts every 8h. Positive = longs pay (bullish crowd). Range: -0.01% to +0.03% |

### Derivative/Spread Features (RAW_D_F_S_*_pct_N)

Bybit Premium Index — measures persistent premium/discount of perpetual vs spot. Drives funding rate calculation.

| Feature | Groups/Categories | Form | Description |
|---------|-------------------|------|-------------|
| `RAW_D_F_S_premiumOpen_pct_N` | Derivative, Funding, Sentiment | Percentage | Premium index at period start (Bybit's internal calculation) |
| `RAW_D_F_S_premiumHigh_pct_N` | Derivative, Funding, Sentiment | Percentage | Highest premium index in period |
| `RAW_D_F_S_premiumLow_pct_N` | Derivative, Funding, Sentiment | Percentage | Lowest premium index in period |
| `RAW_D_F_S_premiumClose_pct_N` | Derivative, Funding, Sentiment | Percentage | Premium index at period end |

**Note:** Premium Index ≠ simple (Mark-Index)/Index. Bybit calculates it from order book depth. Values typically range ±0.1%.

### Sentiment Features (RAW_S_*_rat_N)

Direct positioning data from exchange.

| Feature | Groups/Categories | Form | Description |
|---------|-------------------|------|-------------|
| `RAW_S_longShortRatio_rat_N` | Sentiment | Ratio | Ratio of long vs short accounts. >1 = more longs, <1 = more shorts. Typical range 0.8-1.5 |
| `RAW_S_buyRatio_bnd_N` | Sentiment | Bounded | Percentage of accounts that are long. Range 0-1 (or 0-100%) |
| `RAW_S_sellRatio_bnd_N` | Sentiment | Bounded | Percentage of accounts that are short. Range 0-1 (or 0-100%). Note: buyRatio + sellRatio = 1 |

**Note:** Long/Short Ratio data available from 2021-05-28. This is **account-based** positioning (how many accounts are long vs short), NOT value-weighted. Small retail accounts count same as whales.

---

## Data Architecture: File → Feature Mapping

### Source File Schemas

This section documents the **exact column names** in the raw parquet files and how they map to our feature naming convention.

#### OHLCV (sorted-8h-bybit-linear)
```
File columns: timestamp, open, high, low, close, volume, turnover, interval
```
| File Column | → Feature Name | Timing |
|-------------|----------------|--------|
| `timestamp` | `RAW_TM_timestamp` | Period START (T) |
| `open` | `RAW_P_open_abs_NN` | Known at T ✅ |
| `high` | `RAW_P_high_abs_NN` | Known at T+8h ⚠️ |
| `low` | `RAW_P_low_abs_NN` | Known at T+8h ⚠️ |
| `close` | `RAW_P_close_abs_NN` | Known at T+8h ⚠️ |
| `volume` | `RAW_L_volume_abs_NN` | Known at T+8h ⚠️ |
| `turnover` | `RAW_L_turnover_abs_NN` | Known at T+8h ⚠️ |
| `interval` | (metadata, not used) | — |

#### Mark Price (mark-price-8h-bybit-linear)
```
File columns: timestamp, open, high, low, close
```
| File Column | → Feature Name | Timing |
|-------------|----------------|--------|
| `timestamp` | (same as OHLCV) | Period START (T) |
| `open` | `RAW_P_markOpen_abs_NN` | Known at T ✅ |
| `high` | `RAW_P_markHigh_abs_NN` | Known at T+8h ⚠️ |
| `low` | `RAW_P_markLow_abs_NN` | Known at T+8h ⚠️ |
| `close` | `RAW_P_markClose_abs_NN` | Known at T+8h ⚠️ |

#### Index Price (index-price-8h-bybit-linear)
```
File columns: timestamp, open, high, low, close
```
| File Column | → Feature Name | Timing |
|-------------|----------------|--------|
| `timestamp` | (same as OHLCV) | Period START (T) |
| `open` | `RAW_P_indexOpen_abs_NN` | Known at T ✅ |
| `high` | `RAW_P_indexHigh_abs_NN` | Known at T+8h ⚠️ |
| `low` | `RAW_P_indexLow_abs_NN` | Known at T+8h ⚠️ |
| `close` | `RAW_P_indexClose_abs_NN` | Known at T+8h ⚠️ |

#### Premium Index (premium-price-8h-bybit-linear)
```
File columns: timestamp, open, high, low, close
```
| File Column | → Feature Name | Timing |
|-------------|----------------|--------|
| `timestamp` | (same as OHLCV) | Period START (T) |
| `open` | `RAW_D_F_S_premiumOpen_pct_N` | Known at T ✅ |
| `high` | `RAW_D_F_S_premiumHigh_pct_N` | Known at T+8h ⚠️ |
| `low` | `RAW_D_F_S_premiumLow_pct_N` | Known at T+8h ⚠️ |
| `close` | `RAW_D_F_S_premiumClose_pct_N` | Known at T+8h ⚠️ |

**Note:** Premium values are already in decimal form (0.0005 = 0.05% = 5 bps). Multiply by 100 for percentage display.

#### Open Interest (open-interest-8h-bybit-linear)
```
File columns: timestamp, openInterest
```
| File Column | → Feature Name | Timing |
|-------------|----------------|--------|
| `timestamp` | (period start label) | Label is T |
| `openInterest` | `RAW_L_S_openInterest_abs_NN` | **Measured at T+4h** ⚠️ |

**⚠️ VERIFIED:** Our 8h OI is aggregated from Bybit's 4h API. The 8h value at timestamp T equals the 4h snapshot taken at T+4h (first 4h value in the 8h window). Not available at period start.

**Bybit 4h OI API pattern:** timestamps 04:00, 08:00, 12:00... (offset by 4h from standard times)

#### Funding Rate (funding-rate-bybit-linear)
```
File columns: symbol, fundingRate, fundingRateTimestamp, timestamp
```
| File Column | → Feature Name | Timing |
|-------------|----------------|--------|
| `timestamp` | (settlement time) | Funding settles at T |
| `fundingRate` | `RAW_F_I_S_fundingRate_pct_N` | Known at T ✅ |
| `symbol` | (metadata, always BTCUSDT) | — |
| `fundingRateTimestamp` | (redundant ms timestamp) | — |

**Note:** Funding rate is announced ~8h before settlement, so it's safe to use at its timestamp.

#### Long/Short Ratio (long-short-ratio-8h-bybit-linear)
```
File columns: timestamp_ms, buyRatio, sellRatio, timestamp
```
| File Column | → Feature Name | Timing |
|-------------|----------------|--------|
| `timestamp` | (period start label) | Label is T |
| `buyRatio` | `RAW_S_buyRatio_bnd_N` | **Mean of T to T+4h** ⚠️ |
| `sellRatio` | `RAW_S_sellRatio_bnd_N` | **Mean of T to T+4h** ⚠️ |
| `timestamp_ms` | (redundant ms timestamp) | — |

**Derived:** `RAW_S_longShortRatio_rat_N = buyRatio / sellRatio`

**⚠️ VERIFIED:** Our 8h L/S is the MEAN of two 4h values within each 8h window. Latest measurement in the average is at T+4h. Not available at period start.

---

## ⚠️ TIMING SAFETY FRAMEWORK

### Data Structure (Verified)

**Timestamp = Bar START.** Each row's timestamp marks when the bar opens.

```
Row timestamp  │  Bar Period         │  open    │  close
───────────────┼─────────────────────┼──────────┼────────
00:00 UTC      │  [00:00 → 08:00]    │  at 00:00│  at 08:00
08:00 UTC      │  [08:00 → 16:00]    │  at 08:00│  at 16:00
16:00 UTC      │  [16:00 → 00:00+1d] │  at 16:00│  at 00:00+1d
```

**Proof:** Row N's close = Row N+1's open (continuous price).

### Prediction Setup

> **Prediction happens at bar close (= funding settlement time).**
> 
> At time 08:00 UTC, the bar timestamped "00:00" has just completed.
> Funding row timestamped "08:00" has just settled.

### The Golden Rule

> **Use data from completed bars only. The row's timestamp tells you when that bar STARTED, not when it's available.**

### Feature Availability Timeline

```
═══════════════════════════════════════════════════════════════════════════
        COMPLETED BAR (row timestamp T)          FUTURE BAR (row timestamp T+8h)
              [T ──────────► T+8h]                  [T+8h ──────────► T+16h]
═══════════════════════════════════════════════════════════════════════════

T (bar open)        T+4h              T+8h (NOW)                   T+16h
│                   │                    │                          │
▼                   ▼                    ▼                          ▼
├───────────────────┼────────────────────┤──────────────────────────┤
│   First half      │    Second half     │      FUTURE BAR          │
│                   │                    │                          │
│                   │                    │  AVAILABLE NOW AT T+8h:  │
│                   │                    │  ├─ Row T: ALL data ✅   │
│                   │                    │  │   (open,high,low,     │
│                   │                    │  │    close,vol,OI,L/S)  │
│                   │                    │  ├─ Row T+8h: funding ✅ │
│                   │                    │  └─ Row T+8h: open ✅    │
│  OI snapshot ─────┼────────────────────┤                          │
│  at ~T+4h         │                    │                          │
└───────────────────┴────────────────────┴──────────────────────────┘

Row timestamp T = bar that just completed
Row timestamp T+8h = bar just starting (only open known)
```

### Key Insight (Verified Dec 2025)

At prediction time (e.g., 08:00 UTC):
- Row with `timestamp = 00:00` is the **completed bar** → ALL columns available
- Row with `timestamp = 08:00` is the **current bar** → only `open` and `fundingRate` available
- Funding settles at bar boundaries (00:00, 08:00, 16:00 UTC)

---

## ⭐ PRODUCTION DATA CONTRACT (Critical for No Leakage)

### Models Only Run at 8h Boundaries

> **In production, models ONLY execute at 00:00, 08:00, 16:00 UTC.**
> **No partial/intraday data is ever seen.**

When the model runs at 08:00 UTC:
- The bar [00:00→08:00] **just closed** → all OHLCV available
- The bar [08:00→16:00] **hasn't started in our data** → doesn't exist yet
- Funding at 08:00 **just settled** → available

**This is the simplest possible setup: last row = just-closed bar = prediction row.**

### What the Model Sees

```
At model execution time 08:00 UTC:

┌─────────────────────┬────────┬─────────┬──────────┬─────────────┐
│ timestamp           │ open   │ close   │ volume   │ openInterest│
├─────────────────────┼────────┼─────────┼──────────┼─────────────┤
│ 2025-12-17 08:00    │ 87000  │ 87185   │ 1000     │ 50000       │  ← historical
│ 2025-12-17 16:00    │ 87185  │ 86197   │ 1200     │ 51000       │  ← historical
│ 2025-12-18 00:00    │ 86197  │ 86794   │ 800      │ 50500       │  ← LAST ROW (just closed)
└─────────────────────┴────────┴─────────┴──────────┴─────────────┘
                                                                    
Row 08:00 doesn't exist yet — model runs BEFORE new bar data arrives
```

**Key:** The model never sees partial bars or data from the current open bar.

### Why compute_features.py is Correct

```python
# At prediction time, last row IS the completed bar
# Features computed on this row use only closed bar data

log_return = np.log(df["close"] / df["close"].shift(1))
# At last row (00:00):
#   close = 86794 (bar [00:00→08:00] that just closed)
#   close.shift(1) = 86197 (previous closed bar)
# = return between two CLOSED bars = ✅ NO LEAKAGE
```

### Funding Table

```
┌─────────────────────┬─────────────┐
│ timestamp           │ fundingRate │
├─────────────────────┼─────────────┤
│ 2025-12-18 00:00    │ 0.000046    │  ← settled 8h ago
│ 2025-12-18 08:00    │ 0.000075    │  ← JUST SETTLED (available)
└─────────────────────┴─────────────┘
```

Funding at 08:00 settles exactly when the model runs → available.

### Two Sources, Different Timestamp Semantics

| Source | Timestamp Meaning | At prediction time T |
|--------|-------------------|---------------------|
| OHLCV/OI/L/S | Bar START | Last fetched row = completed bar |
| Funding | Settlement time | Row T = just settled (use directly) |

### Practical Implementation

#### How Data is Joined
```python
import polars as pl

# Load data - contains ONLY complete bars
ohlcv = pl.read_parquet("sorted-8h-bybit-linear/btcusdt_8h.parquet")
funding = pl.read_parquet("funding-rate-bybit-linear/btcusdt_funding_rate.parquet")

# Funding settles at bar CLOSE, not bar start
# To align: funding timestamp T matches OHLCV row timestamp T-8h (that bar's close)
funding_aligned = funding.with_columns(
    (pl.col("timestamp") - pl.duration(hours=8)).alias("bar_timestamp")
)

# Now join on bar_timestamp
df = ohlcv.join(
    funding_aligned.select(["bar_timestamp", "fundingRate"]),
    left_on="timestamp",
    right_on="bar_timestamp",
    how="left"
)
# Result: each OHLCV row now has the funding rate that settled at its bar's CLOSE
```

#### Feature Computation (No Output Shift Needed!)

Since we only fetch complete rows, features computed on the last row are prediction-time safe:

```python
# Internal shift(1) is for comparing to PREVIOUS bar within features
# This is CORRECT - it computes return from previous completed bar to current completed bar

def compute_log_return(df):
    # At last row (timestamp 00:00, completed bar):
    # close = bar [00:00→08:00] close
    # close.shift(1) = bar [16:00→00:00] close (previous completed bar)
    return np.log(df["close"] / df["close"].shift(1))

# NO additional shift at output level - the last row IS our prediction row
features = compute_all_features(df)
# features.iloc[-1] = features for current prediction (from completed bars only)
```

**Key insight:** The `shift(1)` inside feature calculations is for temporal relationships (e.g., "change from previous bar"), NOT for alignment. Alignment is handled by only fetching complete rows.
```

### Why Internal shift(1) Works in Features

The `shift(1)` inside feature calculations computes relationships to the **previous** bar:

```
DataFrame (complete rows only):

Index   │ timestamp │ close    │ close.shift(1) │ log_return
────────┼───────────┼──────────┼────────────────┼─────────────────
i-2     │ T-16h     │ 87185    │ 87000          │ ln(87185/87000)
i-1     │ T-8h      │ 86197    │ 87185          │ ln(86197/87185)
i       │ T (LAST)  │ 86794    │ 86197          │ ln(86794/86197) ← prediction row

log_return at last row = ln(86794/86197) 
                       = ln(bar[T,T+8h].close / bar[T-8h,T].close)
                       = return of LAST completed bar vs PREVIOUS completed bar
                       = ✅ CORRECT - both are complete!
```

**This is NOT for alignment** — it's for computing temporal relationships within features.

**Memory Aid:**
> **shift(1) inside features = "compare to previous bar"**
> **No shift at output = "last row IS the prediction row"**

---

## Data Source Availability & Timestamps

### Timestamp Semantics Summary (Verified Dec 2025)

| Source | Row Timestamp = | Data Becomes Available At |
|--------|-----------------|--------------------------|
| OHLCV | Bar START | Bar END (timestamp + 8h) |
| Mark Price | Bar START | Bar END (timestamp + 8h) |
| Index Price | Bar START | Bar END (timestamp + 8h) |
| Premium Index | Bar START | Bar END (timestamp + 8h) |
| Open Interest | Bar START | ~T+4h (mid-bar snapshot) |
| Long/Short Ratio | Bar START | ~T+4h (mid-bar average) |
| **Funding Rate** | **Settlement time** | **At timestamp (pre-announced)** |

### Critical Rule

At prediction time T:
- **OHLCV row T-8h** = completed bar → ALL fields available
- **OHLCV row T** = current bar → only `open` available
- **Funding row T** = just settled → `fundingRate` available

### Data Coverage by Source

| Source | Start Date | End Date | Notes |
|--------|------------|----------|-------|
| OHLCV | 2021-01-01 | Present | Full history |
| Mark Price | 2021-01-01 | Present | Full history |
| Index Price | 2021-01-01 | Present | Full history |
| Premium Index | 2021-01-01 | Present | Full history |
| Open Interest | 2021-01-01 | Present | Full history |
| Funding Rate | 2021-01-01 | Present | Full history |
| **Long/Short Ratio** | **2021-05-28** | Present | **Starts ~5 months later** |

---

## Quick Reference: Feature Extraction at Prediction Time

### Our Fetch Contract
- **Only complete rows are fetched**
- **Last row = just-completed bar = prediction row**
- **No output-level shift needed**

### Feature Computation Rules

| Feature Type | Internal shift() | Example |
|--------------|------------------|---------|
| Single-bar value | None | `close` → last bar's close |
| Change from previous | shift(1) | `close / close.shift(1)` → return |
| Rolling window | None (uses past N rows) | `close.rolling(3).mean()` → SMA of last 3 bars |
| Funding features | None (already aligned) | `fundingRate` → settled at bar close |

### Code Example
```python
# At prediction time 08:00 UTC, last row is timestamp 00:00 (bar [00:00→08:00])

# Features that use current completed bar directly
last_close = df["close"].iloc[-1]           # Close of bar [00:00→08:00]
last_volume = df["volume"].iloc[-1]         # Volume of bar [00:00→08:00]

# Features that compare to previous bar (use shift internally)
log_return = np.log(df["close"] / df["close"].shift(1)).iloc[-1]
# = ln(close[00:00] / close[16:00_prev]) = return of last bar

# Rolling features (no shift - just use past N complete bars)  
sma_3 = df["close"].rolling(3).mean().iloc[-1]
# = mean of closes from bars [00:00], [16:00_prev], [08:00_prev]
```

### Memory Aid
> **Complete rows only → last row = prediction row → no output shift**
> **Internal shift(1) = "compare to previous bar" (for returns, changes, etc.)**

### Verification Note (Dec 2025)
Verified against actual Bybit data:
- OHLCV rows: `timestamp` = bar start, `open` of row N+1 = `close` of row N (continuous)
- Funding rows: `timestamp` = settlement time (00:00, 08:00, 16:00 UTC)
- Alignment confirmed: funding @ 08:00 settles when OHLCV bar [00:00→08:00] closes
- **compute_features.py verified correct** under "fetch complete rows only" approach

---

## Cross-References

- **Groups/Categories explained:** [Part 1: Groups](Part_1_Groups.md)
- **Form suffixes explained:** [Part 1: Form Suffixes](Part_1_Groups.md#form-suffixes-representation-type)
- **Naming convention:** [Part 0: Convention](Part_0_Convention.md#naming-convention)
