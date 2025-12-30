# Historical Market Data

## Overview

Bybit provides comprehensive historical market data in two formats:
1. **REST API** - Query recent historical data programmatically
2. **Public CSV Downloads** - Download complete daily tick-by-tick data

## REST API Historical Data

### Available via API

All endpoints return historical data with pagination and time range filters.

### Kline/Candlestick Data

**Endpoint**: `GET /v5/market/kline`

**Coverage**: Spot / Linear / Inverse contracts

**Time Range**: 
- **Maximum per request**: 1000 candles (default: 200)
- **Historical depth**: Depends on interval and symbol
  - Most major pairs: Several years of data
  - Newer pairs: Since listing date

**Intervals**: `1`, `3`, `5`, `15`, `30`, `60`, `120`, `240`, `360`, `720` minutes, `D` (daily), `W` (weekly), `M` (monthly)

**Pagination Strategy**:
```python
# Example: Download 1 month of 1-minute candles
import time
from datetime import datetime, timedelta

symbol = "BTCUSDT"
interval = "1"
start_date = datetime(2024, 1, 1)
end_date = datetime(2024, 2, 1)

current = start_date
all_data = []

while current < end_date:
    # Request 1000 candles at a time
    start_ts = int(current.timestamp() * 1000)
    end_ts = int((current + timedelta(minutes=1000)).timestamp() * 1000)
    
    response = requests.get(
        "https://api.bybit.com/v5/market/kline",
        params={
            "category": "linear",
            "symbol": symbol,
            "interval": interval,
            "start": start_ts,
            "end": end_ts,
            "limit": 1000
        }
    )
    
    data = response.json()['result']['list']
    all_data.extend(data)
    
    # Move to next batch
    current += timedelta(minutes=1000)
    time.sleep(0.1)  # Respect rate limits
```

**Data Fields**:
- `[0]` - Start time (ms)
- `[1]` - Open price
- `[2]` - High price
- `[3]` - Low price
- `[4]` - Close price
- `[5]` - Volume (base coin for USDT/USDC, quote coin for Inverse)
- `[6]` - Turnover (quote coin for USDT/USDC, base coin for Inverse)

### Mark Price Kline

**Endpoint**: `GET /v5/market/mark-price-kline`

Historical mark price data (same format as regular klines).

### Index Price Kline

**Endpoint**: `GET /v5/market/index-price-kline`

Historical index price data (same format as regular klines).

### Premium Index Kline

**Endpoint**: `GET /v5/market/premium-index-price-kline`

Historical premium index data for perpetuals.

### Funding Rate History

**Endpoint**: `GET /v5/market/funding/history`

**Coverage**: Linear / Inverse perpetuals

**Parameters**:
- `category`: `linear` or `inverse`
- `symbol`: Symbol name
- `startTime`: Start timestamp (ms)
- `endTime`: End timestamp (ms)
- `limit`: [1, 200], default 200

**Example**:
```
GET /v5/market/funding/history?category=linear&symbol=BTCUSDT&limit=200
```

**Response**:
```json
{
    "retCode": 0,
    "retMsg": "OK",
    "result": {
        "category": "linear",
        "list": [
            {
                "symbol": "BTCUSDT",
                "fundingRate": "0.0001",
                "fundingRateTimestamp": "1672041600000"
            }
        ]
    }
}
```

**Note**: Query funding interval via `/v5/market/instruments-info`

### Open Interest History

**Endpoint**: `GET /v5/market/open-interest`

Historical open interest data for derivatives.

### Long/Short Ratio

**Endpoint**: `GET /v5/market/account-ratio`

Historical long/short account ratio data.

---

## Public CSV Downloads

### Trade Data (Tick-by-Tick)

**URL**: `https://public.bybit.com/trading/{SYMBOL}/`

**Coverage**: 
- **Perpetual Contracts**: USDT perpetuals, Inverse perpetuals
- **Historical Depth**: Varies by symbol (major pairs from 2020)
- **Update Frequency**: Daily files uploaded with 1-day lag

**Format**: Gzipped CSV files, one per day

**File Naming**: `{SYMBOL}{YYYY-MM-DD}.csv.gz`

**Example URLs**:
- BTCUSDT: `https://public.bybit.com/trading/BTCUSDT/BTCUSDT2024-12-17.csv.gz`
- ETHUSDT: `https://public.bybit.com/trading/ETHUSDT/ETHUSDT2024-12-17.csv.gz`
- 1000PEPEUSDT: `https://public.bybit.com/trading/1000PEPEUSDT/`

**Data Fields** (typically):
```csv
timestamp,symbol,side,size,price,tickDirection,trdMatchID,grossValue,homeNotional,foreignNotional
```

**Example Download Script**:
```python
import requests
import gzip
import pandas as pd
from datetime import datetime, timedelta

def download_bybit_trades(symbol, date):
    """Download daily trade data for a symbol."""
    date_str = date.strftime("%Y-%m-%d")
    url = f"https://public.bybit.com/trading/{symbol}/{symbol}{date_str}.csv.gz"
    
    response = requests.get(url)
    if response.status_code == 200:
        # Decompress and parse
        data = gzip.decompress(response.content)
        df = pd.read_csv(pd.io.common.BytesIO(data))
        return df
    else:
        print(f"Failed to download {url}")
        return None

# Download last 7 days of BTCUSDT
symbol = "BTCUSDT"
for i in range(7):
    date = datetime.now() - timedelta(days=i+1)
    df = download_bybit_trades(symbol, date)
    if df is not None:
        print(f"{date.date()}: {len(df)} trades")
```

### Spot Market Data

**URL**: `https://public.bybit.com/spot/{SYMBOL}/`

**Coverage**: Spot trading pairs

**Format**: Similar to perpetuals (daily CSV files)

**Example**: `https://public.bybit.com/spot/BTCUSDT/`

### Kline Data for MetaTrader 4

**URL**: `https://public.bybit.com/kline_for_metatrader4/`

Historical kline data formatted for MT4 platform.

### Premium Index Data

**URL**: `https://public.bybit.com/premium_index/`

Historical premium index data.

### Spot Index Data

**URL**: `https://public.bybit.com/spot_index/`

Historical spot index data.

---

## Data Availability Summary

| Data Type | REST API | CSV Download | Historical Depth |
|-----------|----------|--------------|------------------|
| **Kline (1m-1M)** | ✓ | ✗ | Varies by symbol (years for major pairs) |
| **Tick Trades** | Recent only | ✓ | 2020+ for major perpetuals |
| **Orderbook Snapshots** | Current only | ✗ | Real-time via WebSocket only |
| **Funding Rate** | ✓ | ✗ | Complete history available |
| **Mark Price** | ✓ | ✗ | Complete history available |
| **Index Price** | ✓ | ✗ | Complete history available |
| **Open Interest** | ✓ | ✗ | Historical data available |
| **Long/Short Ratio** | ✓ | ✗ | Historical data available |

---

## Data Characteristics

### Trade Data (CSV)
- **Granularity**: Tick-by-tick (every trade)
- **Size**: Varies widely (10MB-500MB+ per day for active pairs)
- **Latency**: 1 day lag (yesterday's data available today)
- **Completeness**: All executed trades
- **No gaps**: Continuous daily coverage once listed

### Kline Data (API)
- **Granularity**: From 1-minute to 1-month intervals
- **Aggregation**: OHLCV + Volume + Turnover
- **Latency**: Real-time (last candle shows current/incomplete)
- **Pagination**: 1000 candles per request
- **Rate limits**: Subject to standard API limits

---

## Best Practices for Historical Data

### For Backtesting

1. **Use CSV downloads for tick data**:
   - Most accurate price action
   - Contains all trades with exact timestamps
   - Better for high-frequency strategy testing

2. **Use API klines for aggregated data**:
   - Faster to download
   - Pre-aggregated OHLCV
   - Good for daily/hourly strategies

### For Analysis

1. **Start with API for exploratory analysis**:
   - Quick to prototype
   - No need to manage large files
   - Sufficient for most statistical analysis

2. **Download CSV for production systems**:
   - Local storage = faster repeated access
   - No API rate limit concerns
   - Complete audit trail

### Data Validation

Always validate downloaded data:

```python
def validate_kline_data(df):
    """Validate kline data integrity."""
    checks = {
        'no_nulls': df.isnull().sum().sum() == 0,
        'positive_volume': (df['volume'] >= 0).all(),
        'high_low_valid': (df['high'] >= df['low']).all(),
        'ohlc_valid': (
            (df['high'] >= df['open']) & 
            (df['high'] >= df['close']) &
            (df['low'] <= df['open']) &
            (df['low'] <= df['close'])
        ).all(),
        'sequential_time': df['timestamp'].is_monotonic_increasing
    }
    
    return all(checks.values()), checks
```

---

## Data Limitations

### REST API Limitations

- **Rate limits**: 600 requests per 5 seconds per IP
- **Pagination required**: Max 1000 records per request
- **No order book history**: Only current snapshots available
- **Recent data focus**: Very old data may require CSV

### CSV Limitations

- **1-day lag**: Yesterday's data available today
- **No intraday updates**: Files are daily only
- **Large files**: Popular pairs can be 100MB+ per day
- **No orderbook**: Only executed trades

### General Limitations

- **Delisted symbols**: Data may be removed
- **Symbol changes**: Rebranded pairs may have gaps
- **Maintenance windows**: Rare data gaps during major upgrades
- **Precision**: Prices/quantities as strings to avoid float errors

---

## Data Download Examples

### Bulk Historical Download

```python
import requests
import gzip
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import time

def bulk_download_trades(symbol, start_date, end_date, output_dir):
    """
    Download all trade data for a symbol between dates.
    
    Args:
        symbol: Trading symbol (e.g., 'BTCUSDT')
        start_date: datetime object
        end_date: datetime object
        output_dir: Directory to save CSV files
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    current = start_date
    while current <= end_date:
        date_str = current.strftime("%Y-%m-%d")
        filename = f"{symbol}{date_str}.csv.gz"
        url = f"https://public.bybit.com/trading/{symbol}/{filename}"
        
        output_path = Path(output_dir) / filename
        
        if output_path.exists():
            print(f"Skipping {date_str} (already downloaded)")
            current += timedelta(days=1)
            continue
        
        print(f"Downloading {date_str}...", end=' ')
        response = requests.get(url)
        
        if response.status_code == 200:
            with open(output_path, 'wb') as f:
                f.write(response.content)
            print(f"✓ ({len(response.content) // 1024} KB)")
        elif response.status_code == 404:
            print("✗ (not available)")
        else:
            print(f"✗ (HTTP {response.status_code})")
        
        current += timedelta(days=1)
        time.sleep(0.2)  # Be nice to the server

# Example: Download all 2024 BTCUSDT data
bulk_download_trades(
    symbol="BTCUSDT",
    start_date=datetime(2024, 1, 1),
    end_date=datetime(2024, 12, 31),
    output_dir="./bybit_data/BTCUSDT/"
)
```

### Process Downloaded Data

```python
def load_daily_trades(filepath):
    """Load and parse a daily trade file."""
    with gzip.open(filepath, 'rt') as f:
        df = pd.read_csv(f)
    
    # Convert timestamp to datetime
    if 'timestamp' in df.columns:
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    
    return df

def aggregate_to_ohlcv(trades_df, frequency='1min'):
    """Aggregate tick trades into OHLCV bars."""
    trades_df = trades_df.set_index('timestamp')
    
    ohlcv = trades_df['price'].resample(frequency).ohlc()
    ohlcv['volume'] = trades_df['size'].resample(frequency).sum()
    ohlcv['trades'] = trades_df['size'].resample(frequency).count()
    
    return ohlcv

# Load a day of trades
df = load_daily_trades("./bybit_data/BTCUSDT/BTCUSDT2024-12-17.csv.gz")

# Create 1-minute OHLCV bars
ohlcv_1m = aggregate_to_ohlcv(df, '1min')
```

---

## Resources

- **Public Data Portal**: https://public.bybit.com/
- **API Documentation**: https://bybit-exchange.github.io/docs/v5/market/kline
- **GitHub Examples**: https://github.com/bybit-exchange/api-usage-examples
- **Historical Data Page**: https://www.bybit.com/en-US/help-center/ (search "historical data")

---

**Last Updated**: December 18, 2025
