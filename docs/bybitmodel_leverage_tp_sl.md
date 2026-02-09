# Bybit model leverage, take profit, and stop loss

Scope: `Archive/previous_work/position_manage/bybitmodel.py`.

## Leverage calculation

1. Kelly-based default leverage (`calculate_kelly_criterion`).

Formula:
```text
kelly_fraction = (win_prob * win_ratio - loss_prob * loss_ratio) / (win_ratio * loss_ratio)
kelly_fraction = clamp(kelly_fraction, 0, 1)
leverage = int(min_leverage + kelly_fraction * (max_leverage - min_leverage))
```

Notes:
- `min_leverage = 12` and `max_leverage = 15` in code (the inline comment mentions 10 to 25, but the implementation uses 12 to 15).
- On division by zero the function returns `12`.
- This value is used to set `DEFAULT_LEVERAGE` after fetching trade stats.

2. ATR/Bollinger risk-based leverage (`calculate_max_leverage`).

Inputs and steps:
- Fetch 1h and 4h market data with Bollinger bands and SMA_20.
- Compute 1/5 band deltas per timeframe. Buy: `delta = (upper - middle) / 5`. Sell: `delta = (middle - lower) / 5`.
- Compute take-profit candidate. Buy: `take_profit = max(upper_1h - delta_1h, upper_4h - delta_4h)`. Sell: `take_profit = min(lower_1h + delta_1h, lower_4h + delta_4h)`.
- Compute stop distance as one-third of the profit target: `profit_dist = abs(take_profit - entry_price)` and `stop_dist = profit_dist / 3`.
- Convert stop distance to a loss percentage and solve leverage: `loss_pct = stop_dist / entry_price` and `leverage = max(1, floor(risk_pct / loss_pct))`.
- `risk_pct` defaults to `0.10` (10% of equity).
- Optional rounding of `take_profit` to tick size (stop loss rounding is commented out in this function).

3. Which leverage is used in live signals.

- `DEFAULT_LEVERAGE` is attached to raw trade signals but is not the final leverage.
- In `generate_trade_signal`, the system computes `leverage_atr = calculate_max_leverage(...)` and uses that value in the final trade signal.
- `execute_trade` applies the selected leverage on Bybit (only if it differs from current leverage).

## Take-profit and stop-loss calculation

## Entry price levels (LONG/SHORT)

Primary entry logic (inside `evaluate_generic_conditions` when signals pass scoring):
- LONG entry price is derived from 15m and 1h Bollinger levels. `midpoint_15 = (Bollinger_Lower_15m + Bollinger_Middle_15m) / 2`. If `midpoint_15 < Bollinger_Lower_1h`, then `entry_long = Bollinger_Lower_1h`, else `entry_long = midpoint_15`. The last 15m close must be `<= entry_long` for the LONG to trigger.
- SHORT entry price is derived from 5m and 1h Bollinger levels. `midpoint_5 = (Bollinger_Upper_5m + Bollinger_Middle_5m) / 2`. If `midpoint_5 > Bollinger_Upper_1h`, then `entry_short = Bollinger_Upper_1h`, else `entry_short = midpoint_5`. The last 5m close must be `>= entry_short` for the SHORT to trigger.

Fallback entry logic (used only when no signals were generated and volatility is high enough):
- LONG fallback if `close > KC_Upper`: `entry_price = KC_Upper + 0.15 * ATR`.
- SHORT fallback if `close < KC_Lower`: `entry_price = KC_Lower - 0.15 * ATR`.

## Indicators and timeframes used (entry → SL/TP updates)

All indicators are computed per timeframe in `fetch_market_data_with_indicators()` and then consumed by the trading logic. Timeframes used in the open/SL/TP flow are 1d, 4h, 1h, 15m, and 5m.

Indicators computed per timeframe (as used by the trading flow):
- RSI (`RSI_14`, plus `RSI_9`, `RSI_21`, and `RSI_21_LOW/HIGH`): `RSIIndicator` on close (and special low/high variants via `compute_rsi_low_high`).
- SMA (`SMA_5`, `SMA_20`, `SMA_50`, `SMA_200`): `SMAIndicator` on close.
- EMA (`EMA_9`, `EMA_14`, `EMA_20`, `EMA_21`, `EMA_50`, `EMA_200`): `EMAIndicator` on close.
- ATR (`ATR_14`): `AverageTrueRange` on high/low/close.
- MACD (`MACD_Line`, `Signal_Line`, `MACD_Histogram`): `MACD` on close, plus abs/mean variants.
- Bollinger Bands (`Bollinger_Upper`, `Bollinger_Middle`, `Bollinger_Lower`): `BollingerBands` on close.
- Keltner Channels (`KC_Upper`, `KC_Middle`, `KC_Lower`): EMA(20) midline plus ATR(14) × 2.
- VWAP: `VolumeWeightedAveragePrice`.
- CCI (`CCI_14`): `CCIIndicator` on high/low/close.
- Momentum (`Momentum` / ROC 14): `ROCIndicator` on close.
- Price Volatility (`Price_Volatility`): `(high - low) / close`.
- Support/Resistance (`Support`, `Resistance`): rolling low/high over 20 bars.
- OBV: `OnBalanceVolumeIndicator`.
- Stochastic (`Stochastic_%K`, `Stochastic_%D`): `StochasticOscillator` with window 14 and smooth 3.
- Williams %R (`Williams_%R`): `WilliamsRIndicator` with lbp 14.
- ADX (`ADX`, `DI+`, `DI-`, `ADX_MA`): `ADXIndicator` with window 14 plus a 10‑bar SMA of ADX.
- Volume Oscillator (`Volume_Oscillator`, `Volume_Oscillator_Signal`): 12/26 volume SMAs and 9‑span EMA signal.
- Volume SMAs (`Volume_SMA_5`, `Volume_SMA_20`): rolling means on volume.
- Fibonacci levels (`Fib_0.382`, `Fib_0.5`, `Fib_0.618`): computed from max high and min low across the fetched window.

Where each timeframe is used in the position lifecycle:
- 4h timeframe: regime classification (via `classify_market_regime`), low‑volatility skip check (`ATR_14`), and entry‑score evaluation when regime is trending. Also used for leverage (`calculate_max_leverage`) and SL/TP updates in `get_position_details`.
- 1h timeframe: entry‑score evaluation in non‑trending regimes, entry price construction (1h Bollinger), take‑profit selection (`SMA_20` or 1h Bollinger), and SL/TP updates (`get_position_details`).
- 15m timeframe: long entry price construction (15m Bollinger lower/middle) and gating with last 15m close.
- 5m timeframe: short entry price construction (5m Bollinger upper/middle) and gating with last 5m close.
- 1d timeframe: breakout skip conditions using ADX, Bollinger, Keltner, Support/Resistance, and close/high.

Indicators actually referenced during entry and SL/TP update:
- Entry scoring and gating (primarily `determine_entry_price` and `evaluate_generic_conditions`): `RSI_14`, `MACD_Line`, `ADX`, `Stochastic_%K`, `Stochastic_%D`, `CCI`/`CCI_14`, `Williams_%R`, `Bollinger_*`, `KC_*`, `EMA_20`, `EMA_50`, `EMA_200`, `ATR_14`, `Support`, `Resistance`, `Volume_SMA_5`, `Volume_SMA_20`, `close`, `high`, `low`, and `volume`.
- Entry price levels: 15m and 1h Bollinger (LONG), 5m and 1h Bollinger (SHORT), and fallback Keltner (4h/1h depending on the `latest` row used).
- Take profit levels: 1h `SMA_20` for LONG, 1h `Bollinger_Lower` for SHORT, or fallback `entry_price ± adjusted_atr`.
- Stop loss levels: `adjusted_atr = ATR_14 * atr_multiplier` for new entries; or Bollinger mid‑band offsets and 1/3 of profit target for dynamic updates in `get_position_details`.
- Leverage calculation uses 1h and 4h Bollinger + SMA_20 and the entry price to size leverage to a risk budget.

## Timeframe usage summary (entry → management)

- 1d: only used for breakout skip filters before taking a trade.
- 4h: regime classification, volatility gate (ATR), leverage sizing inputs, and dynamic TP/SL updates.
- 1h: core entry evaluation, entry price anchors, TP targets, and dynamic TP/SL updates.
- 15m: long entry price construction and gating.
- 5m: short entry price construction and gating.

## How to merge lower TF rows into higher TF safely (no future leakage)

Goal: for each higher‑TF bar (e.g., 1h), attach the latest fully closed lower‑TF bars (e.g., 5m/15m) without using any data after the higher‑TF bar close.

Principles:
- Use close times, not open times, for alignment.
- Only use fully closed bars (`is_forming=False`).
- The lower‑TF timestamp must be `<=` the higher‑TF bar close time.

Practical approach (pandas example using `merge_asof`):
- Build a `close_time` for each TF bar (start time + TF duration).
- Sort both DataFrames by `close_time`.
- `merge_asof` lower→higher with `direction="backward"` so each higher‑TF bar gets the most recent lower‑TF bar that closed at or before the higher‑TF close.

Example sketch:
```python
# higher: 1h bars, lower: 5m bars
df_1h["close_time"] = df_1h["startTime"] + pd.Timedelta(hours=1)
df_5m["close_time"] = df_5m["startTime"] + pd.Timedelta(minutes=5)

df_1h = df_1h.sort_values("close_time")
df_5m = df_5m.sort_values("close_time")

merged = pd.merge_asof(
    df_1h,
    df_5m,
    on="close_time",
    direction="backward",
    suffixes=("", "_5m")
)
```

Notes:
- If you want multiple lower‑TF features (e.g., last 3 closed 5m bars per 1h), you can pre‑aggregate the 5m data into rolling features and then merge once.
- If using Polars, use an `asof` join on `close_time` with `strategy="backward"`.

## Sources (online)

These sources describe the safe “backward” as‑of join semantics (last row with key <= left key) and the need to avoid look‑ahead bias in backtests.
- pandas `merge_asof` documentation.
- Polars `join_asof` documentation.
- Polars user guide example for trade/quote alignment using `join_asof` backward.
- Baquero, ter Horst, Verbeek (JFQA): “Survival, Look‑Ahead Bias, and Persistence in Hedge Fund Performance.”

### New entry signals (in `evaluate_generic_conditions`)

Shared inputs:
- `adjusted_atr = ATR_14 * atr_multiplier` (default `atr_multiplier = 1.5`).

LONG signals:
- Entry price. `midpoint_15 = (Bollinger_Lower_15m + Bollinger_Middle_15m) / 2`. If `midpoint_15 < Bollinger_Lower_1h`, then `entry_long = Bollinger_Lower_1h`, else `entry_long = midpoint_15`.
- Gate: last 15m close must be `<= entry_long`.
- Take profit: `tp_long = SMA_20_1h`, and it must satisfy `tp_long >= entry_long * 1.006`.
- Stop loss: `stop_loss = entry_long - adjusted_atr`.

SHORT signals:
- Entry price. `midpoint_5 = (Bollinger_Upper_5m + Bollinger_Middle_5m) / 2`. If `midpoint_5 > Bollinger_Upper_1h`, then `entry_short = Bollinger_Upper_1h`, else `entry_short = midpoint_5`.
- Gate: last 5m close must be `>= entry_short`.
- Take profit: `tp_short = Bollinger_Lower_1h`, and it must satisfy `tp_short <= entry_short * 0.994`.
- Stop loss: `stop_loss = entry_short + adjusted_atr`.

### Fallback Keltner-channel signals (when no signals are found)

- If `close > KC_Upper`, then `entry_price = KC_Upper + 0.15 * ATR`, `stop_loss = entry_price - adjusted_atr`, and `take_profit = entry_price + adjusted_atr`.
- If `close < KC_Lower`, then `entry_price = KC_Lower - 0.15 * ATR`, `stop_loss = entry_price + adjusted_atr`, and `take_profit = entry_price - adjusted_atr`.

### Existing position management (`get_position_details`)

Bollinger band deltas:
- `delta_top = (upper - middle) / 5`.
- `delta_bot = (middle - lower) / 5`.

BUY positions:
- Take profit: `tp_1h = upper_1h - delta_top_1h`, `tp_4h = upper_4h - delta_top_4h`, and `take_profit = max(tp_1h, tp_4h)`.
- Stop loss: if existing stop loss equals `middle_1h - delta_bot_1h`, reuse it. Else if previous 1h close is above middle, use `middle_1h - delta_bot_1h`. Else use `entry_price - (take_profit - entry_price) / 3`.

SELL positions:
- Take profit: `tp_1h = lower_1h + delta_bot_1h`, `tp_4h = lower_4h + delta_bot_4h`, and `take_profit = min(tp_1h, tp_4h)`.
- Stop loss: if existing stop loss equals `middle_1h + delta_top_1h`, reuse it. Else if previous 1h close is below middle, use `middle_1h + delta_top_1h`. Else use `entry_price - (take_profit - entry_price) / 3`, which equals `entry_price + (entry_price - take_profit) / 3` when `take_profit < entry_price`.

Rounding:
- `get_position_details` rounds `stop_loss` and `take_profit` to tick size when available.
- `place_stop_loss_take_profit` also rounds TP/SL to tick size before placing orders.

## Notes

- `place_or_update_sl_tp_orders` and `place_stop_loss_take_profit` do not compute TP or SL. They only place or update orders using the values provided.
