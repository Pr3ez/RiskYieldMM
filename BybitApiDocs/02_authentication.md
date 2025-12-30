# Authentication

## API Key Types

### System-Generated API Keys (HMAC)
- Uses HMAC-SHA256 encryption
- Bybit generates both public and private keys
- Treat keys as passwords and keep them secure
- Follow [HMAC sample scripts](https://github.com/bybit-exchange/api-usage-examples)

### Self-Generated API Keys (RSA)
- Uses RSA-SHA256 encryption
- You generate your own private/public key pair
- Only provide public key to Bybit
- Bybit never holds your private key
- Use [api-rsa-generator](https://github.com/bybit-exchange/api-rsa-generator)
- Follow [RSA sample scripts](https://github.com/bybit-exchange/api-usage-examples)

## Required HTTP Headers

| Header | Required | Description |
|--------|----------|-------------|
| `X-BAPI-API-KEY` | Yes | Your API key |
| `X-BAPI-TIMESTAMP` | Yes | UTC timestamp in milliseconds |
| `X-BAPI-SIGN` | Yes | Signature derived from request parameters |
| `X-BAPI-RECV-WINDOW` | No | Request validity window in ms (default: 5000, max: 60000) |
| `X-Referer` or `Referer` | No | For broker users only |
| `cdn-request-id` | No | Optional unique ID for advanced network diagnostics |

## Creating Authenticated Requests

### Timestamp Rules

Your timestamp must satisfy:
```
server_time - recv_window <= timestamp < server_time + 1000
```

- Use local device time synchronized with NTP
- Query server time via `/v5/market/time` endpoint
- Keep `X-BAPI-RECV-WINDOW` small for security (but not too small to avoid transmission failures)

### Signature Generation Process

#### For GET Requests
1. Create string to sign: `timestamp + api_key + recv_window + queryString`
2. Sign using HMAC_SHA256 or RSA_SHA256
3. Convert to lowercase HEX (HMAC) or base64 (RSA)

**Example:**
```
timestamp = "1658384314791"
api_key = "XXXXXXXXXX"
recv_window = "5000"
queryString = "category=option&symbol=BTC-29JUL22-25000-C"

# String to sign:
"1658384314791XXXXXXXXXX5000category=option&symbol=BTC-29JUL22-25000-C"

# Resulting HMAC signature:
"410e0f387bafb7afd0f1722c068515e09945610124fa11774da1da857b72f30b"
```

#### For POST Requests
1. Create string to sign: `timestamp + api_key + recv_window + jsonBodyString`
2. Sign using HMAC_SHA256 or RSA_SHA256
3. Convert to lowercase HEX (HMAC) or base64 (RSA)

### Example GET Request

```http
GET /v5/order/realtime?category=option&symbol=BTC-29JUL22-25000-C HTTP/1.1
Host: api-testnet.bybit.com
X-BAPI-SIGN: 410e0f387bafb7afd0f1722c068515e09945610124fa11774da1da857b72f30b
X-BAPI-API-KEY: XXXXXXXXXX
X-BAPI-TIMESTAMP: 1658384314791
X-BAPI-RECV-WINDOW: 5000
```

### Example POST Request

```http
POST /v5/order/create HTTP/1.1
Host: api-testnet.bybit.com
X-BAPI-SIGN: XXXXX
X-BAPI-API-KEY: XXXXXXXXXX
X-BAPI-TIMESTAMP: 1672211928338
X-BAPI-RECV-WINDOW: 5000
Content-Type: application/json

{
    "category": "spot",
    "symbol": "BTCUSDT",
    "side": "Buy",
    "orderType": "Limit",
    "qty": "0.01",
    "price": "28000",
    "timeInForce": "GTC"
}
```

## Obtaining API Keys

### Testnet
Create API keys at: https://testnet.bybit.com/app/user/api-management

### Mainnet
Create API keys at: https://www.bybit.com/app/user/api-management

## Security Best Practices

1. **Never share your API keys** - especially private keys
2. **Use IP whitelisting** - restrict API access to specific IPs
3. **Set appropriate permissions** - only enable required permissions
4. **Use small recv_window** - reduces replay attack window
5. **Rotate keys regularly** - especially if compromised
6. **Monitor API usage** - watch for unusual activity
7. **Use read-only keys** - for non-trading operations

## Example Code (Python)

```python
import time
import hmac
import hashlib
import requests

api_key = "YOUR_API_KEY"
api_secret = "YOUR_API_SECRET"

# Generate signature
timestamp = str(int(time.time() * 1000))
recv_window = "5000"
query_string = "category=linear&symbol=BTCUSDT"

param_str = timestamp + api_key + recv_window + query_string
signature = hmac.new(
    api_secret.encode('utf-8'),
    param_str.encode('utf-8'),
    hashlib.sha256
).hexdigest()

# Make request
headers = {
    'X-BAPI-API-KEY': api_key,
    'X-BAPI-TIMESTAMP': timestamp,
    'X-BAPI-SIGN': signature,
    'X-BAPI-RECV-WINDOW': recv_window
}

url = "https://api.bybit.com/v5/order/realtime"
params = {"category": "linear", "symbol": "BTCUSDT"}

response = requests.get(url, headers=headers, params=params)
print(response.json())
```

## Signature Verification Examples

See complete examples for all languages:
https://github.com/bybit-exchange/api-usage-examples
