# Bybit API V5 Documentation - Quick Reference

## Table of Contents

1. [Overview](01_overview.md) - API introduction, structure, and resources
2. [Authentication](02_authentication.md) - API key types and request signing
3. [Rate Limits](03_rate_limits.md) - IP limits and endpoint rate limits
4. [Order Management](04_order_management.md) - Creating and managing orders
5. [Market Data](05_market_data.md) - Public market data endpoints
6. [WebSocket](06_websocket.md) - Real-time data streams
7. [Historical Data](07_historical_data.md) - **Bulk downloads and historical data access**

## Quick Start

### 1. Get API Keys
- **Testnet**: https://testnet.bybit.com/app/user/api-management
- **Mainnet**: https://www.bybit.com/app/user/api-management

### 2. Base URLs

**REST API:**
- Testnet: `https://api-testnet.bybit.com`
- Mainnet: `https://api.bybit.com`

**WebSocket:**
- Public: `wss://stream.bybit.com/v5/public/{category}`
- Private: `wss://stream.bybit.com/v5/private`

### 3. Common Order Flow

```python
import hmac
import time
import requests

# Authentication
api_key = "YOUR_API_KEY"
api_secret = "YOUR_API_SECRET"
timestamp = str(int(time.time() * 1000))
recv_window = "5000"

# Order parameters
order_data = {
    "category": "linear",
    "symbol": "BTCUSDT",
    "side": "Buy",
    "orderType": "Limit",
    "qty": "0.01",
    "price": "30000",
    "timeInForce": "GTC"
}

# Create signature
param_str = timestamp + api_key + recv_window + json.dumps(order_data)
signature = hmac.new(
    api_secret.encode('utf-8'),
    param_str.encode('utf-8'),
    hashlib.sha256
).hexdigest()

# Send request
headers = {
    'X-BAPI-API-KEY': api_key,
    'X-BAPI-TIMESTAMP': timestamp,
    'X-BAPI-SIGN': signature,
    'X-BAPI-RECV-WINDOW': recv_window,
    'Content-Type': 'application/json'
}

response = requests.post(
    'https://api.bybit.com/v5/order/create',
    headers=headers,
    json=order_data
)
```

## Essential Endpoints

### Market Data (Public)
- `GET /v5/market/kline` - Historical candlesticks
- `GET /v5/market/orderbook` - Orderbook snapshot
- `GET /v5/market/tickers` - Latest prices and 24h stats
- `GET /v5/market/recent-trade` - Recent trades
- `GET /v5/market/instruments-info` - Trading rules

### Trading (Private)
- `POST /v5/order/create` - Place order
- `POST /v5/order/amend` - Modify order
- `POST /v5/order/cancel` - Cancel order
- `POST /v5/order/cancel-all` - Cancel all orders
- `GET /v5/order/realtime` - Query active orders
- `GET /v5/execution/list` - Query trade history

### Account (Private)
- `GET /v5/account/wallet-balance` - Get wallet balance
- `GET /v5/position/list` - Get positions
- `GET /v5/account/fee-rate` - Get trading fees

## Key Parameters

### Product Categories
- `spot` - Spot trading
- `linear` - USDT/USDC perpetual and futures
- `inverse` - Inverse perpetual and futures
- `option` - Options

### Order Types
- `Market` - Execute at best price
- `Limit` - Execute at specified price or better

### Order Sides
- `Buy` - Long/buy order
- `Sell` - Short/sell order

### Time in Force
- `GTC` - Good Till Cancel (default)
- `IOC` - Immediate or Cancel
- `FOK` - Fill or Kill
- `PostOnly` - Maker only

### Position Modes
- `0` - One-way mode
- `1` - Hedge mode (Buy side)
- `2` - Hedge mode (Sell side)

## Rate Limits Summary

### IP Limits
- **600 requests per 5 seconds** per IP (HTTP)
- **500 connections per 5 minutes** per IP (WebSocket)

### Common Endpoint Limits
- Create order: 10/s (linear/inverse), 20/s (spot)
- Cancel order: 10/s (linear/inverse), 20/s (spot)
- Query orders: 50/s
- Wallet balance: 50/s

## WebSocket Streams

### Public Streams
- `orderbook.{depth}.{symbol}` - Orderbook updates
- `publicTrade.{symbol}` - Public trades
- `ticker.{symbol}` - Ticker data
- `kline.{interval}.{symbol}` - Candlestick updates

### Private Streams (require authentication)
- `order` - Order updates
- `position` - Position changes
- `execution` - Trade executions
- `wallet` - Wallet balance changes

## Error Codes

| Code | Message | Description |
|------|---------|-------------|
| 0 | OK | Success |
| 10001 | Parameter error | Invalid parameters |
| 10002 | Request expired | Timestamp too old |
| 10003 | Invalid API key | API key incorrect |
| 10004 | Invalid signature | Signature validation failed |
| 10005 | Permission denied | Insufficient permissions |
| 10006 | Too many visits | Rate limit exceeded |
| 10016 | Service temporarily unavailable | System maintenance |
| 110001 | Order not exists | Order ID not found |
| 110003 | Insufficient balance | Not enough funds |
| 110007 | Position not exists | Position not found |

## SDKs

### Official
- **Python**: `pip install pybit`
- **Go**: `go get github.com/bybit-exchange/bybit.go.api`
- **Java**: Maven/Gradle via GitHub
- **.NET**: NuGet package

### Usage Example (Python)

```python
from pybit.unified_trading import HTTP

session = HTTP(
    testnet=True,
    api_key="YOUR_API_KEY",
    api_secret="YOUR_API_SECRET"
)

# Place order
order = session.place_order(
    category="linear",
    symbol="BTCUSDT",
    side="Buy",
    orderType="Limit",
    qty="0.01",
    price="30000",
    timeInForce="GTC"
)

# Get orderbook
orderbook = session.get_orderbook(
    category="linear",
    symbol="BTCUSDT",
    limit=50
)
```

## Support & Resources

- **Documentation**: https://bybit-exchange.github.io/docs/
- **API Examples**: https://github.com/bybit-exchange/api-usage-examples
- **Telegram (EN)**: https://t.me/BybitAPI
- **Telegram (CN)**: https://t.me/BybitChineseAPI
- **Discord**: https://discord.gg/VBwVwS2HUs

## Best Practices

1. **Use testnet first** - Test thoroughly before mainnet
2. **Handle rate limits** - Implement backoff strategies
3. **Use WebSocket** - For real-time data instead of polling
4. **Validate responses** - Check retCode before processing
5. **Keep keys secure** - Never expose API keys
6. **Monitor order status** - Use WebSocket for confirmations
7. **Implement error handling** - Retry with exponential backoff
8. **Log all trades** - Maintain audit trail
9. **Use batch endpoints** - For multiple orders (more efficient)
10. **NTP sync time** - Keep system clock synchronized

## Common Pitfalls

❌ **Don't:**
- Store API keys in code
- Poll REST API for real-time data
- Ignore rate limit headers
- Submit orders without validation
- Trust order placement success without confirmation

✅ **Do:**
- Use environment variables for keys
- Use WebSocket for real-time updates
- Implement exponential backoff
- Validate all parameters
- Confirm order status via WebSocket

## Additional Notes

- All timestamps are in **milliseconds**
- All prices and quantities are **strings**
- Order IDs are **unique per category**
- WebSocket requires **authentication** for private streams
- Market orders may be **rejected** due to slippage limits
- **reduceOnly** orders automatically split if too large

---

**Documentation Version**: V5  
**Last Updated**: December 18, 2025  
**Official Docs**: https://bybit-exchange.github.io/docs/v5/intro
