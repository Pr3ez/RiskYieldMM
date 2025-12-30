# Order Management

## Place Order

**Endpoint**: `POST /v5/order/create`

Creates orders for Spot, Margin trading, USDT perpetual, USDT futures, USDC perpetual, USDC futures, Inverse Futures, and Options.

### Request Parameters

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| category | Yes | string | Product type: `linear`, `inverse`, `spot`, `option` |
| symbol | Yes | string | Symbol name (e.g., BTCUSDT), uppercase only |
| side | Yes | string | `Buy` or `Sell` |
| orderType | Yes | string | `Market` or `Limit` |
| qty | Yes | string | Order quantity |
| price | No | string | Order price (required for Limit orders) |
| timeInForce | No | string | `GTC` (default), `IOC`, `FOK`, `PostOnly`, `RPI` |
| orderLinkId | No | string | User customized order ID (max 36 chars) |
| isLeverage | No | integer | Spot only: 0=spot trade (default), 1=margin trade |
| orderFilter | No | string | Spot only: `Order` (default), `tpslOrder`, `StopOrder` |
| positionIdx | No | integer | Position mode: 0=one-way, 1=hedge-Buy, 2=hedge-Sell |
| reduceOnly | No | boolean | If true, only reduces position size |
| closeOnTrigger | No | boolean | Ensures stop loss reduces position regardless of margin |

### Market Orders

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| marketUnit | No | string | Spot market orders: `baseCoin` or `quoteCoin` |
| slippageToleranceType | No | string | `TickSize` or `Percent` |
| slippageTolerance | No | string | TickSize: [1, 10000], Percent: [0.01, 10] |

### Conditional Orders

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| triggerPrice | No | string | Conditional order trigger price |
| triggerDirection | No | integer | 1=rise to trigger, 2=fall to trigger |
| triggerBy | No | string | `LastPrice`, `IndexPrice`, `MarkPrice` |

### Take Profit / Stop Loss

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| takeProfit | No | string | Take profit price |
| stopLoss | No | string | Stop loss price |
| tpTriggerBy | No | string | TP trigger: `MarkPrice`, `IndexPrice`, `LastPrice` (default) |
| slTriggerBy | No | string | SL trigger: `MarkPrice`, `IndexPrice`, `LastPrice` (default) |
| tpslMode | No | string | `Full` (entire position) or `Partial` (partial position) |
| tpOrderType | No | string | `Market` (default) or `Limit` |
| slOrderType | No | string | `Market` (default) or `Limit` |
| tpLimitPrice | No | string | Limit price when TP triggered (if tpOrderType=Limit) |
| slLimitPrice | No | string | Limit price when SL triggered (if slOrderType=Limit) |

### Best Bid/Offer (BBO) Orders

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| bboSideType | No | string | `Queue` or `Counterparty` |
| bboLevel | No | string | 1, 2, 3, 4, or 5 |

### SMP & MMP

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| smpType | No | string | SMP execution type |
| mmp | No | boolean | Market maker protection (option only) |

### Response

```json
{
    "retCode": 0,
    "retMsg": "OK",
    "result": {
        "orderId": "1321003749386327552",
        "orderLinkId": "spot-test-postonly"
    },
    "retExtInfo": {},
    "time": 1672211918471
}
```

⚠️ **Important**: Order acknowledgement is asynchronous. Use WebSocket to confirm order status.

## Example Order Requests

### Spot Limit Order with Market TP/SL

```json
{
    "category": "spot",
    "symbol": "BTCUSDT",
    "side": "Buy",
    "orderType": "Limit",
    "qty": "0.01",
    "price": "28000",
    "timeInForce": "PostOnly",
    "takeProfit": "35000",
    "stopLoss": "27000",
    "tpOrderType": "Market",
    "slOrderType": "Market"
}
```

### Spot Limit Order with Limit TP/SL

```json
{
    "category": "spot",
    "symbol": "BTCUSDT",
    "side": "Buy",
    "orderType": "Limit",
    "qty": "0.01",
    "price": "28000",
    "timeInForce": "PostOnly",
    "takeProfit": "35000",
    "stopLoss": "27000",
    "tpLimitPrice": "36000",
    "slLimitPrice": "27500",
    "tpOrderType": "Limit",
    "slOrderType": "Limit"
}
```

### Spot Market Buy (by value)

```json
{
    "category": "spot",
    "symbol": "BTCUSDT",
    "side": "Buy",
    "orderType": "Market",
    "qty": "200",
    "timeInForce": "IOC",
    "orderLinkId": "spot-test-04",
    "isLeverage": 0,
    "orderFilter": "Order"
}
```

### Linear Perpetual - Open Long (One-Way Mode)

```json
{
    "category": "linear",
    "symbol": "BTCUSDT",
    "side": "Buy",
    "orderType": "Limit",
    "qty": "1",
    "price": "25000",
    "timeInForce": "GTC",
    "positionIdx": 0,
    "orderLinkId": "usdt-test-01",
    "reduceOnly": false,
    "takeProfit": "28000",
    "stopLoss": "20000",
    "tpslMode": "Partial",
    "tpOrderType": "Limit",
    "slOrderType": "Limit",
    "tpLimitPrice": "27500",
    "slLimitPrice": "20500"
}
```

### Linear Perpetual - Close Long (One-Way Mode)

```json
{
    "category": "linear",
    "symbol": "BTCUSDT",
    "side": "Sell",
    "orderType": "Limit",
    "qty": "1",
    "price": "30000",
    "timeInForce": "GTC",
    "positionIdx": 0,
    "orderLinkId": "usdt-test-02",
    "reduceOnly": true
}
```

## Order Limits

### Open Orders Limit

**Perps & Futures:**
- 500 active orders per symbol per account
- 10 conditional orders per symbol per account

**Spot:**
- 500 total orders
- Max 30 TP/SL orders
- Max 30 conditional orders per symbol

**Options:**
- 50 open orders per account

## Order Behavior

### Reduce-Only Orders
- If `reduceOnly=true` and order qty > max order qty, order is automatically split into multiple orders
- Can only reduce position size, never increase

### Close on Trigger
- Ensures stop loss reduces position regardless of margin
- If margin insufficient when triggered, other active orders may be cancelled/reduced

### Market Orders
- Converted to IOC limit orders to protect against slippage
- If no orderbook entries within price slippage limit, order won't execute
- Insufficient liquidity results in cancellation

### PostOnly Orders
- If order would execute immediately, it's cancelled
- Protects against taking liquidity during submission
- Guarantees maker fee (if filled)

## Important Notes

1. **Async Acknowledgement**: Response confirms request accepted, not order filled
2. **Use WebSocket**: Monitor order status changes in real-time
3. **OrderLinkId**: Max 36 characters, unique per category
4. **Price Requirements**: Must be better than liquidation price if you have position
5. **Quantity**: Always positive numbers
6. **Risk Control**: Daily order limits monitored across main/sub accounts

## Rate Limits

See [03_rate_limits.md](03_rate_limits.md) for detailed rate limiting information.
