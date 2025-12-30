# Bybit API V5 Documentation - Overview

## Introduction

The V5 API brings uniformity and efficiency to Bybit's product lines, unifying Spot, Derivatives, and Options in one set of specifications.

## Base URLs

### Testnet
- REST API: `https://api-testnet.bybit.com`

### Mainnet
- REST API: `https://api.bybit.com` or `https://api.bytick.com`
- Regional endpoints:
  - Netherlands: `https://api.bybit.nl`
  - Turkey: `https://api.bybit-tr.com`
  - Kazakhstan: `https://api.bybit.kz`
  - Georgia: `https://api.bybitgeorgia.ge`
  - UAE: `https://api.bybit.ae`

### WebSocket
- `stream.bybit.com` (and regional variants)

## API Coverage

| Account Type | Linear | Inverse | Spot | Options |
|--------------|--------|---------|------|---------|
| Unified Trading Account | ✓ | ✓ | ✓ | ✓ |
| Classic Account | ✓ | - | ✓ | ✓ |

**Supported Products:**
- USDT Perpetual / USDC Perpetual / USDC Futures
- Inverse Perpetual / Inverse Futures
- Spot Trading
- Options

## API Structure

```
{host}/{version}/{module}
Example: api.bybit.com/v5/market/recent-trade
```

### Main Modules

| Module | Purpose |
|--------|---------|
| `v5/market/` | Market data (candlesticks, orderbook, tickers, trades) |
| `v5/order/` | Order management (create, amend, cancel orders) |
| `v5/position/` | Position management |
| `v5/account/` | Account operations (wallet, fees, etc.) |
| `v5/asset/` | Asset management (deposits, withdrawals, transfers) |
| `v5/spot-lever-token/` | Leveraged tokens |
| `v5/spot-margin-trade/` | Margin trading |

## Key Features

### Unified Account
- Share and cross-utilize funds across Spot, USDT Perpetual, USDC Perpetual, and Options
- Offset profit/loss across different positions
- Borrowing support across multiple assets as collateral

### Portfolio Margin Mode
- Combined margin between Inverse Perpetuals, Inverse Futures, USDT Perpetual, USDC Perpetual, USDC Futures, and Options

### Order Types Supported
- **Market Orders**: Execute at best available price
- **Limit Orders**: Execute at specified price or better
- **Conditional Orders**: Triggered when price reaches trigger level
- **TP/SL Orders**: Take profit and stop loss orders
- **Post-Only**: Ensure order goes on orderbook

### Time in Force Options
- `GTC` - Good Till Cancel
- `IOC` - Immediate or Cancel
- `FOK` - Fill or Kill
- `PostOnly` - Only add liquidity (cancelled if would take)
- `RPI` - Retail Price Improvement (market makers only)

## Common Response Format

All API responses follow this structure:

```json
{
    "retCode": 0,
    "retMsg": "OK",
    "result": {},
    "retExtInfo": {},
    "time": 1671017382656
}
```

| Field | Type | Description |
|-------|------|-------------|
| retCode | number | Success/Error code (0 = success) |
| retMsg | string | Success/Error message |
| result | Object | Business data result |
| retExtInfo | Object | Extended info (usually empty) |
| time | number | Current timestamp (ms) |

## Official SDKs

- **Python**: [pybit](https://github.com/bybit-exchange/pybit)
- **Go**: [bybit-go-api](https://github.com/bybit-exchange/bybit.go.api)
- **Java**: [bybit-java-api](https://github.com/bybit-exchange/bybit-java-api)
- **.NET**: [bybit.net.api](https://github.com/bybit-exchange/bybit.net.api)
- **Node.js** (community): [bybit-api](https://www.npmjs.com/package/bybit-api)

## Resources

- [API Usage Examples](https://github.com/bybit-exchange/api-usage-examples)
- [Postman Collection](https://github.com/bybit-exchange/QuickStartWithPostman)
- [Historical Market Data (CSV)](https://public.bybit.com/)
- [Help Center](https://www.bybit.com/en-US/help-center/bybitHC_Guides)

## Support Channels

- **Telegram (English)**: https://t.me/BybitAPI
- **Telegram (Chinese)**: https://t.me/BybitChineseAPI
- **Discord**: https://discord.gg/VBwVwS2HUs

## Documentation Generated

Date: December 18, 2025
