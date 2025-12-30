# WebSocket API

## WebSocket URLs

### Public Market Data
- **Mainnet**: `wss://stream.bybit.com/v5/public/{category}`
- **Testnet**: `wss://stream-testnet.bybit.com/v5/public/{category}`

Where `{category}` is: `spot`, `linear`, `inverse`, or `option`

### Private User Data
- **Mainnet**: `wss://stream.bybit.com/v5/private`
- **Testnet**: `wss://stream-testnet.bybit.com/v5/private`

## Connection Limits

- **Max 500 connections per 5 minutes** per IP
- **Max 1,000 connections per IP** for market data
- Do not frequently connect/disconnect
- Connections counted separately for Spot, Linear, Inverse, Options

## Authentication (Private Streams)

### Required Parameters
- `api_key`: Your API key
- `expires`: Unix timestamp (ms) when signature expires
- `signature`: HMAC SHA256 signature

### Authentication Message

```json
{
    "op": "auth",
    "args": [
        "YOUR_API_KEY",
        1234567890000,
        "YOUR_SIGNATURE"
    ]
}
```

### Signature Generation

```python
import hmac
import time

api_key = "YOUR_API_KEY"
api_secret = "YOUR_API_SECRET"

# expires = current time + 10 seconds
expires = int((time.time() + 10) * 1000)

# Signature string: "GET/realtime" + expires
signature = hmac.new(
    api_secret.encode('utf-8'),
    f"GET/realtime{expires}".encode('utf-8'),
    digestmod='sha256'
).hexdigest()
```

## Subscription Format

### Subscribe

```json
{
    "op": "subscribe",
    "args": [
        "orderbook.50.BTCUSDT",
        "publicTrade.BTCUSDT"
    ]
}
```

### Unsubscribe

```json
{
    "op": "unsubscribe",
    "args": [
        "orderbook.50.BTCUSDT"
    ]
}
```

## Public Streams

### Orderbook Stream

**Topic**: `orderbook.{depth}.{symbol}`

**Depth options**: `1`, `50`, `200`, `500` (linear/inverse), `50`, `200` (spot), `25`, `100` (option)

**Message types:**
- `snapshot` - Full orderbook snapshot
- `delta` - Incremental updates

```json
{
    "topic": "orderbook.50.BTCUSDT",
    "type": "snapshot",
    "ts": 1672304484978,
    "data": {
        "s": "BTCUSDT",
        "b": [
            ["16493.50", "0.006"],
            ["16493.00", "0.100"]
        ],
        "a": [
            ["16611.00", "0.029"],
            ["16612.00", "0.213"]
        ],
        "u": 18521288,
        "seq": 7961638724
    }
}
```

### Public Trade Stream

**Topic**: `publicTrade.{symbol}`

```json
{
    "topic": "publicTrade.BTCUSDT",
    "type": "snapshot",
    "ts": 1672304486868,
    "data": [
        {
            "T": 1672304486865,
            "s": "BTCUSDT",
            "S": "Buy",
            "v": "0.001",
            "p": "16578.50",
            "L": "PlusTick",
            "i": "20f43950-d8dd-5b31-9112-a178eb6023af",
            "BT": false
        }
    ]
}
```

### Ticker Stream

**Topic**: `tickers.{symbol}`

```json
{
    "topic": "tickers.BTCUSDT",
    "type": "snapshot",
    "ts": 1672304486868,
    "data": {
        "symbol": "BTCUSDT",
        "lastPrice": "16578.50",
        "highPrice24h": "16900.00",
        "lowPrice24h": "16450.00",
        "prevPrice24h": "16550.00",
        "volume24h": "2345.12",
        "turnover24h": "38930000.00",
        "price24hPcnt": "0.0017"
    }
}
```

### Kline Stream

**Topic**: `kline.{interval}.{symbol}`

**Intervals**: `1`, `3`, `5`, `15`, `30`, `60`, `120`, `240`, `360`, `720`, `D`, `W`, `M`

```json
{
    "topic": "kline.1.BTCUSDT",
    "data": [
        {
            "start": 1672324800000,
            "end": 1672324860000,
            "interval": "1",
            "open": "16590.00",
            "close": "16595.50",
            "high": "16600.00",
            "low": "16588.00",
            "volume": "12.456",
            "turnover": "206789.12",
            "confirm": false,
            "timestamp": 1672324840123
        }
    ],
    "ts": 1672324840123,
    "type": "snapshot"
}
```

### Liquidation Stream

**Topic**: `liquidation.{symbol}`

```json
{
    "topic": "liquidation.BTCUSDT",
    "type": "snapshot",
    "ts": 1672304486868,
    "data": {
        "updatedTime": 1672304486000,
        "symbol": "BTCUSDT",
        "side": "Sell",
        "size": "0.01",
        "price": "16578.50"
    }
}
```

## Private Streams

### Order Stream

**Topics:**
- `order` - All categories (spot, linear, inverse, option)
- `order.spot` - Spot only
- `order.linear` - Linear only
- `order.inverse` - Inverse only
- `order.option` - Option only

⚠️ **Note**: Cannot mix All-In-One topic with Categorised topics in same subscription

**Example subscription:**

```json
{
    "op": "subscribe",
    "args": ["order"]
}
```

**Python example:**

```python
from pybit.unified_trading import WebSocket
from time import sleep

ws = WebSocket(
    testnet=True,
    channel_type="private",
    api_key="YOUR_API_KEY",
    api_secret="YOUR_API_SECRET"
)

def handle_message(message):
    print(message)

ws.order_stream(callback=handle_message)

while True:
    sleep(1)
```

**Stream message:**

```json
{
    "id": "5923240c6880ab-c59f-420b-9adb-3639adc9dd90",
    "topic": "order",
    "creationTime": 1672364262474,
    "data": [
        {
            "symbol": "ETH-30DEC22-1400-C",
            "orderId": "5cf98598-39a7-459e-97bf-76ca765ee020",
            "side": "Sell",
            "orderType": "Market",
            "cancelType": "UNKNOWN",
            "price": "72.5",
            "qty": "1",
            "orderIv": "",
            "timeInForce": "IOC",
            "orderStatus": "Filled",
            "orderLinkId": "",
            "lastPriceOnCreated": "",
            "reduceOnly": false,
            "leavesQty": "",
            "leavesValue": "",
            "cumExecQty": "1",
            "cumExecValue": "75",
            "avgPrice": "75",
            "blockTradeId": "",
            "positionIdx": 0,
            "cumExecFee": "0.358635",
            "closedPnl": "0",
            "createdTime": "1672364262444",
            "updatedTime": "1672364262457",
            "rejectReason": "EC_NoError",
            "stopOrderType": "",
            "tpslMode": "",
            "triggerPrice": "",
            "takeProfit": "",
            "stopLoss": "",
            "tpTriggerBy": "",
            "slTriggerBy": "",
            "tpLimitPrice": "",
            "slLimitPrice": "",
            "triggerDirection": 0,
            "triggerBy": "",
            "closeOnTrigger": false,
            "category": "option",
            "placeType": "price",
            "smpType": "None",
            "smpGroup": 0,
            "smpOrderId": "",
            "feeCurrency": "",
            "cumFeeDetail": {
                "MNT": "0.00242968"
            }
        }
    ]
}
```

### Position Stream

**Topic**: `position`

Updates when position changes.

### Execution Stream

**Topic**: `execution`

Real-time trade execution updates.

### Wallet Stream

**Topic**: `wallet`

Wallet balance updates.

## Heartbeat

### Ping/Pong

Server sends ping every 20 seconds:

```json
{
    "op": "ping"
}
```

Client must respond with pong:

```json
{
    "op": "pong"
}
```

If no pong received within 30 seconds, server closes connection.

## Error Messages

```json
{
    "success": false,
    "ret_msg": "error message",
    "conn_id": "connection-id",
    "op": "subscribe"
}
```

## Best Practices

1. **Handle reconnections**: Implement exponential backoff
2. **Snapshot + Delta**: Apply deltas to orderbook snapshot
3. **Sequence numbers**: Track `u` and `seq` to detect gaps
4. **Subscribe selectively**: Only subscribe to needed streams
5. **Rate limiting**: Respect connection limits
6. **Heartbeat**: Respond to ping messages
7. **Error handling**: Log and handle error messages
8. **Authentication expiry**: Re-authenticate if connection long-lived

## Connection Example (Python)

```python
import websocket
import json
import hmac
import time

def on_message(ws, message):
    print(f"Received: {message}")

def on_error(ws, error):
    print(f"Error: {error}")

def on_close(ws, close_status_code, close_msg):
    print("Connection closed")

def on_open(ws):
    # Public stream - no auth needed
    subscribe_msg = {
        "op": "subscribe",
        "args": ["orderbook.50.BTCUSDT", "publicTrade.BTCUSDT"]
    }
    ws.send(json.dumps(subscribe_msg))

# Connect to public stream
ws = websocket.WebSocketApp(
    "wss://stream.bybit.com/v5/public/linear",
    on_open=on_open,
    on_message=on_message,
    on_error=on_error,
    on_close=on_close
)

ws.run_forever()
```

## WebSocket vs REST

**Use WebSocket for:**
- Real-time orderbook updates
- Trade executions
- Order status changes
- Position updates
- Continuous data streams

**Use REST for:**
- Historical data queries
- One-time operations
- Account management
- Placing/canceling orders (with WebSocket for confirmation)
