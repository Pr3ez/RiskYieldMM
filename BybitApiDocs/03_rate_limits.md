# Rate Limits

## IP Limits

### HTTP IP Limit
- **600 requests per 5-second window** per IP
- Applies to all traffic directed to `api.bybit.com`, `api.bytick.com`, and regional domains
- If you receive error **"403, access too frequent"**, your IP exceeded the limit
- **Penalty**: Automatic ban for at least 10 minutes
- **Recovery**: Terminate all HTTP sessions and wait

⚠️ **Important**: Do not run applications at the edge of these limits

### WebSocket IP Limit
- **Max 500 connections per 5-minute window**
- Applies to `stream.bybit.com` and regional domains
- Do not frequently connect/disconnect
- **Max 1,000 connections per IP** for market data
- Connection limits counted separately for Spot, Linear, Inverse, and Options

## API Rate Limits

### Rate Limit Headers

Every API response includes these headers:

```
X-Bapi-Limit-Status: 99              # Remaining requests
X-Bapi-Limit: 100                     # Current limit
X-Bapi-Limit-Reset-Timestamp: 1672738134824  # Reset time
```

### Rate Limit Error

When you hit the limit:
```json
{
    "retCode": 10006,
    "retMsg": "Too many visits!"
}
```

## Rate Limit Tables

### Trade Endpoints

| Method | Endpoint | Spot | Linear | Inverse | Option | Upgradable |
|--------|----------|------|--------|---------|--------|------------|
| POST | `/v5/order/create` | 10/s | 10/s | 10/s | 20/s | Yes |
| POST | `/v5/order/amend` | 10/s | 10/s | 10/s | 10/s | Yes |
| POST | `/v5/order/cancel` | 10/s | 10/s | 10/s | 20/s | Yes |
| POST | `/v5/order/cancel-all` | 20/s | 10/s | 10/s | 1/s | Yes |
| POST | `/v5/order/create-batch` | 20/s | 10/s | 10/s | - | Yes |
| POST | `/v5/order/amend-batch` | 20/s | 10/s | 10/s | - | Yes |
| POST | `/v5/order/cancel-batch` | 20/s | 10/s | 10/s | - | Yes |
| POST | `/v5/order/disconnected-cancel-all` | 5/s | 5/s | 5/s | 5/s | No |
| GET | `/v5/order/realtime` | 50/s | 50/s | 50/s | 50/s | No |
| GET | `/v5/order/history` | 50/s | 50/s | 50/s | 50/s | No |
| GET | `/v5/execution/list` | 50/s | 50/s | 50/s | 50/s | No |
| GET | `/v5/order/spot-borrow-check` | 50/s | - | - | - | No |

### Position Endpoints

| Method | Endpoint | Linear | Inverse | Option | Upgradable |
|--------|----------|--------|---------|--------|------------|
| GET | `/v5/position/list` | 50/s | 50/s | 50/s | No |
| GET | `/v5/position/closed-pnl` | 50/s | 50/s | - | No |
| POST | `/v5/position/set-leverage` | 10/s | 10/s | - | No |

### Account Endpoints

| Method | Endpoint | Category | Limit | Upgradable |
|--------|----------|----------|-------|------------|
| GET | `/v5/account/wallet-balance` | UNIFIED | 50/s | No |
| GET | `/v5/account/fee-rate` | linear | 10/s | No |
| GET | `/v5/account/fee-rate` | spot | 5/s | No |
| GET | `/v5/account/fee-rate` | option | 5/s | No |
| GET | `/v5/account/fee-rate` | inverse | 10/s | No |
| GET | `/v5/account/withdrawal` | - | 50/s | No |
| GET | `/v5/account/borrow-history` | - | 50/s | No |
| POST | `/v5/account/borrow` | - | 1/s | No |
| POST | `/v5/account/repay` | - | 1/s | No |
| GET | `/v5/account/collateral-info` | - | 50/s | No |
| GET | `/v5/account/transaction-log` | UNIFIED | 50/s | No |

### Asset Endpoints

| Method | Endpoint | Limit | Upgradable |
|--------|----------|-------|------------|
| GET | `/v5/asset/transfer/query-asset-info` | 60/min | No |
| GET | `/v5/asset/transfer/query-transfer-coin-list` | 60/min | No |
| GET | `/v5/asset/transfer/query-inter-transfer-list` | 60/min | No |
| GET | `/v5/asset/transfer/query-sub-member-list` | 60/min | No |
| GET | `/v5/asset/transfer/query-universal-transfer-list` | 5/s | No |
| GET | `/v5/asset/transfer/query-account-coins-balance` | 5/s | No |
| GET | `/v5/asset/deposit/query-record` | 100/min | No |
| GET | `/v5/asset/deposit/query-address` | 300/min | No |
| GET | `/v5/asset/withdraw/query-record` | 300/min | No |
| GET | `/v5/asset/coin/query-info` | 5/s | No |
| POST | `/v5/asset/transfer/inter-transfer` | 60/min | No |
| POST | `/v5/asset/transfer/universal-transfer` | 5/s | No |
| POST | `/v5/asset/withdraw/create` | 5/s | No |
| POST | `/v5/asset/withdraw/cancel` | 60/min | No |

### User Management Endpoints

| Method | Endpoint | Limit | Upgradable |
|--------|----------|-------|------------|
| POST | `/v5/user/create-sub-member` | 1/s | No |
| POST | `/v5/user/create-sub-api` | 1/s | No |
| POST | `/v5/user/frozen-sub-member` | 5/s | No |
| POST | `/v5/user/update-api` | 5/s | No |
| POST | `/v5/user/delete-api` | 5/s | No |
| GET | `/v5/user/query-sub-members` | 10/s | No |
| GET | `/v5/user/query-api` | 10/s | No |

### Spread Trading Endpoints

| Method | Endpoint | Limit | Upgradable |
|--------|----------|-------|------------|
| POST | Create Spread Order | 20/s | No |
| POST | Amend Spread Order | 20/s | No |
| POST | Cancel Spread Order | 20/s | No |
| POST | Cancel All Spread Orders | 5/s | No |
| GET | Get Spread Open Orders | 50/s | No |
| GET | Get Spread Order History | 50/s | No |
| GET | Get Spread Trade History | 50/s | No |

## Batch Endpoint Behavior

### For linear, spot, inverse

- **Consumption multiplier**: Number of requests × Number of orders in request
- **Example**: 1 batch request with 5 orders = 5 limit consumption
- **Max orders per batch**: 1-10 orders
- **Partial success**: If last batch exceeds limit, successful orders execute, excess orders fail

**Example scenario:**
- Remaining limit in 1s: 5
- Batch request with 8 orders submitted
- Result: First 5 orders succeed, orders 6-8 fail with rate limit error

### Rate Limit Independence

💡 **TIP**: Batch endpoints have separate rate limits from single endpoints

**Example:**
- Single create order: 100/s
- Batch create order: 100/s
- **Total capacity**: Can place 200 orders/second using both endpoints

## Best Practices

1. **Monitor rate limit headers** - Check remaining capacity before requests
2. **Implement exponential backoff** - When approaching limits
3. **Use batch endpoints** - For multiple orders (more efficient)
4. **Cache market data** - Reduce repeated queries
5. **WebSocket for real-time** - Instead of polling REST API
6. **Request upgrades** - Contact support for higher limits if needed

## Requesting Higher Limits

For institutional or high-volume traders:
- Contact your client manager
- Submit application: https://www.bybit.com/future-activity/en-US/institutional-services
- Upgradable endpoints marked with "Y" in tables above

## Risk Control Notice

Bybit monitors API requests. When total daily orders (UTC 0-24) across main account and subaccounts exceed certain limits:

- Platform reserves right to remind, warn, or restrict
- Users accepting API terms agree to cooperate with adjustments
- Applies to aggregated order counts across all accounts
