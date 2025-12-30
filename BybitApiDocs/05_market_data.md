# Market Data Endpoints

All market data endpoints are public and do not require authentication.

## Get Kline (Candlestick Data)

**Endpoint**: `GET /v5/market/kline`

Query historical klines/candlesticks.

**Covers**: Spot / USDT contract / USDC contract / Inverse contract

### Request Parameters

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| category | No | string | `spot`, `linear`, `inverse` (default: `linear`) |
| symbol | Yes | string | Symbol name (e.g., BTCUSDT), uppercase only |
| interval | Yes | string | Kline interval: `1`, `3`, `5`, `15`, `30`, `60`, `120`, `240`, `360`, `720`, `D`, `W`, `M` |
| start | No | integer | Start timestamp (ms) |
| end | No | integer | End timestamp (ms) |
| limit | No | integer | Data per page [1, 1000], default: 200 |

### Response Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| category | string | Product type |
| symbol | string | Symbol name |
| list | array | Candle data (sorted by startTime descending) |
| > list[0] | string | Start time of candle (ms) |
| > list[1] | string | Open price |
| > list[2] | string | High price |
| > list[3] | string | Low price |
| > list[4] | string | Close price (last traded price if candle not closed) |
| > list[5] | string | Volume (base coin for USDT/USDC, quote coin for Inverse) |
| > list[6] | string | Turnover (quote coin for USDT/USDC, base coin for Inverse) |

### Example Request

```
GET /v5/market/kline?category=inverse&symbol=BTCUSD&interval=60&start=1670601600000&end=1670608800000
```

### Example Response

```json
{
    "retCode": 0,
    "retMsg": "OK",
    "result": {
        "symbol": "BTCUSD",
        "category": "inverse",
        "list": [
            [
                "1670608800000",
                "17071",
                "17073",
                "17027",
                "17055.5",
                "268611",
                "15.74462667"
            ]
        ]
    },
    "retExtInfo": {},
    "time": 1672025956592
}
```

---

## Get Orderbook

**Endpoint**: `GET /v5/market/orderbook`

Query for orderbook depth data (snapshot format).

**Covers**: Spot / USDT contract / USDC contract / Inverse contract / Option

**Depth Levels:**
- Contract: 1000-level
- Spot: 1000-level  
- Option: 25-level

### Request Parameters

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| category | Yes | string | `spot`, `linear`, `inverse`, `option` |
| symbol | Yes | string | Symbol name (e.g., BTCUSDT), uppercase only |
| limit | No | integer | Spot: [1, 200] default 1; Linear/Inverse: [1, 500] default 25; Option: [1, 25] default 1 |

### Response Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| s | string | Symbol name |
| b | array | Bids (sorted by price descending) |
| > b[0] | string | Bid price |
| > b[1] | string | Bid size |
| a | array | Asks (sorted by price ascending) |
| > a[0] | string | Ask price |
| > a[1] | string | Ask size |
| ts | integer | Timestamp when system generated data (ms) |
| u | integer | Update ID (always in sequence) |
| seq | integer | Cross sequence (compare orderbook data freshness) |
| cts | integer | Timestamp from matching engine (ms) |

### Example Request

```
GET /v5/market/orderbook?category=spot&symbol=BTCUSDT
```

### Example Response

```json
{
    "retCode": 0,
    "retMsg": "OK",
    "result": {
        "s": "BTCUSDT",
        "a": [
            ["65557.7", "16.606555"]
        ],
        "b": [
            ["65485.47", "47.081829"]
        ],
        "ts": 1716863719031,
        "u": 230704,
        "seq": 1432604333,
        "cts": 1716863718905
    },
    "retExtInfo": {},
    "time": 1716863719382
}
```

⚠️ **Note**: Retail Price Improvement (RPI) orders not included in response

---

## Get Tickers

**Endpoint**: `GET /v5/market/tickers`

Query latest price snapshot, best bid/ask, and 24h trading volume.

**Covers**: Spot / USDT contract / USDC contract / Inverse contract / Option

### Request Parameters

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| category | Yes | string | `spot`, `linear`, `inverse`, `option` |
| symbol | No | string | Symbol name (e.g., BTCUSDT), uppercase only |
| baseCoin | No | string | Base coin, uppercase (option only) |
| expDate | No | string | Expiry date (e.g., 25DEC22) (option only) |

ℹ️ **Note**: If `category=option`, must pass `symbol` OR `baseCoin`

### Response Parameters (Linear/Inverse)

| Parameter | Type | Description |
|-----------|------|-------------|
| category | string | Product type |
| list | array | Ticker data |
| > symbol | string | Symbol name |
| > lastPrice | string | Last price |
| > indexPrice | string | Index price |
| > markPrice | string | Mark price |
| > prevPrice24h | string | Market price 24h ago |
| > price24hPcnt | string | 24h price change percentage |
| > highPrice24h | string | Highest price in 24h |
| > lowPrice24h | string | Lowest price in 24h |
| > prevPrice1h | string | Market price 1h ago |
| > openInterest | string | Open interest size |
| > openInterestValue | string | Open interest value |
| > turnover24h | string | 24h turnover |
| > volume24h | string | 24h volume |
| > fundingRate | string | Funding rate |
| > nextFundingTime | string | Next funding time (ms) |
| > predictedDeliveryPrice | string | Predicted delivery price (30min before delivery) |
| > basisRate | string | Basis rate |
| > deliveryFeeRate | string | Delivery fee rate |
| > deliveryTime | string | Delivery timestamp (ms) |
| > ask1Size | string | Best ask size |
| > bid1Price | string | Best bid price |
| > ask1Price | string | Best ask price |
| > bid1Size | string | Best bid size |
| > preOpenPrice | string | Pre-market open price estimate |
| > preQty | string | Pre-market open qty estimate |
| > curPreListingPhase | string | Current pre-market phase |
| > fundingIntervalHour | string | Funding interval (hours) |
| > fundingCap | string | Funding rate cap |
| > basisRateYear | string | Annual basis rate (Futures only) |

### Example Request

```
GET /v5/market/tickers?category=inverse&symbol=BTCUSD
```

### Example Response

```json
{
    "retCode": 0,
    "retMsg": "OK",
    "result": {
        "category": "inverse",
        "list": [
            {
                "symbol": "BTCUSD",
                "lastPrice": "120635.50",
                "indexPrice": "114890.92",
                "markPrice": "114898.43",
                "prevPrice24h": "105595.90",
                "price24hPcnt": "0.142425",
                "highPrice24h": "131309.30",
                "lowPrice24h": "102007.60",
                "prevPrice1h": "119806.10",
                "openInterest": "240113967",
                "openInterestValue": "2089.79",
                "turnover24h": "115.6907",
                "volume24h": "13713832.0000",
                "fundingRate": "0.0001",
                "nextFundingTime": "1760371200000",
                "bid1Price": "103401.00",
                "bid1Size": "1063",
                "ask1Price": "109152.80",
                "ask1Size": "9854",
                "fundingIntervalHour": "8",
                "fundingCap": "0.005"
            }
        ]
    },
    "retExtInfo": {},
    "time": 1760352369814
}
```

---

## Other Market Data Endpoints

### Get Instruments Info
- Endpoint: `GET /v5/market/instruments-info`
- Returns: Trading rules, price/qty filters, leverage info

### Get Mark Price Kline
- Endpoint: `GET /v5/market/mark-price-kline`
- Returns: Historical mark price klines

### Get Index Price Kline
- Endpoint: `GET /v5/market/index-price-kline`
- Returns: Historical index price klines

### Get Premium Index Price Kline
- Endpoint: `GET /v5/market/premium-index-price-kline`
- Returns: Historical premium index klines

### Get Recent Trades
- Endpoint: `GET /v5/market/recent-trade`
- Returns: Recent public trades

### Get Open Interest
- Endpoint: `GET /v5/market/open-interest`
- Returns: Open interest data

### Get Historical Volatility
- Endpoint: `GET /v5/market/historical-volatility`
- Returns: Historical volatility (option only)

### Get Insurance
- Endpoint: `GET /v5/market/insurance`
- Returns: Insurance pool data

### Get Risk Limit
- Endpoint: `GET /v5/market/risk-limit`
- Returns: Risk limit information

### Get Delivery Price
- Endpoint: `GET /v5/market/delivery-price`
- Returns: Delivery price for futures

### Get Long Short Ratio
- Endpoint: `GET /v5/market/account-ratio`
- Returns: Long/short account ratio

### Get Server Time
- Endpoint: `GET /v5/market/time`
- Returns: Bybit server time (ms)

---

## Historical Data Availability

### REST API Historical Queries

**Maximum per request**: 1000 records (default: 200)

**Historical depth**: 
- Major pairs: Several years of kline data
- Newer pairs: Since listing date

**Pagination required for large ranges**:
```python
# Example: Download historical data in batches
start_ts = int(datetime(2024, 1, 1).timestamp() * 1000)
end_ts = int(datetime(2024, 2, 1).timestamp() * 1000)

response = requests.get(
    "https://api.bybit.com/v5/market/kline",
    params={
        "category": "linear",
        "symbol": "BTCUSDT",
        "interval": "60",
        "start": start_ts,
        "end": end_ts,
        "limit": 1000
    }
)
```

### Public CSV Downloads (Tick-by-Tick)

For backtesting and deep analysis, Bybit provides **free tick-by-tick trade data** in CSV format:

**📥 Download Portal**: `https://public.bybit.com/`

**Available Data**:
- **Perpetual Contracts**: `https://public.bybit.com/trading/{SYMBOL}/`
- **Spot Markets**: `https://public.bybit.com/spot/{SYMBOL}/`

**Format**: Daily gzipped CSV files (`{SYMBOL}{YYYY-MM-DD}.csv.gz`)

**Coverage**:
- BTCUSDT: From March 2020
- ETHUSDT: From April 2020
- Other major pairs: 2+ years of history
- Updated daily with 1-day lag

**Example URLs**:
```
https://public.bybit.com/trading/BTCUSDT/BTCUSDT2024-12-17.csv.gz
https://public.bybit.com/trading/ETHUSDT/ETHUSDT2024-12-17.csv.gz
https://public.bybit.com/trading/1000PEPEUSDT/1000PEPEUSDT2024-12-17.csv.gz
```

**Quick Download**:
```bash
# Download yesterday's BTCUSDT trades
wget https://public.bybit.com/trading/BTCUSDT/BTCUSDT$(date -d yesterday +%Y-%m-%d).csv.gz
gunzip BTCUSDT*.csv.gz
```

**Python Download Script**:
```python
import requests
import gzip
import pandas as pd
from datetime import datetime, timedelta

def download_bybit_trades(symbol, date):
    date_str = date.strftime("%Y-%m-%d")
    url = f"https://public.bybit.com/trading/{symbol}/{symbol}{date_str}.csv.gz"
    
    response = requests.get(url)
    if response.status_code == 200:
        data = gzip.decompress(response.content)
        return pd.read_csv(pd.io.common.BytesIO(data))
    return None

# Download last 7 days
for i in range(7):
    date = datetime.now() - timedelta(days=i+1)
    df = download_bybit_trades("BTCUSDT", date)
    if df is not None:
        print(f"{date.date()}: {len(df)} trades")
```

### Data Comparison

| Feature | REST API Klines | CSV Downloads |
|---------|-----------------|---------------|
| **Granularity** | 1m to 1M aggregated | Tick-by-tick trades |
| **Best for** | Quick analysis, live data | Backtesting, research |
| **Size** | Small (OHLCV only) | Large (every trade) |
| **Speed** | Fast queries | Initial download slower |
| **Rate limits** | Yes (600 req/5s) | No limits |
| **Latency** | Real-time | 1-day lag |
| **Storage** | No local storage | Requires disk space |

📖 **For complete historical data documentation, see [07_historical_data.md](07_historical_data.md)**

---

## WebSocket Market Data

For real-time market data, use WebSocket instead of polling REST endpoints:

**WebSocket URL**: `wss://stream.bybit.com/v5/public/{category}`

**Available Streams:**
- `orderbook.{depth}.{symbol}` - Orderbook updates
- `publicTrade.{symbol}` - Public trades
- `ticker.{symbol}` - Ticker updates
- `kline.{interval}.{symbol}` - Kline updates
- `liquidation.{symbol}` - Liquidation events

See [06_websocket.md](06_websocket.md) for details.
