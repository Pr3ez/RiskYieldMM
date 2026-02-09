# Dynamic TP/SL management (Bybit positions)

Scope: `Archive/previous_work/position_manage/bybitmodel.py` → `get_position_details()` and order placement helpers.

This document describes **how take‑profit (TP) and stop‑loss (SL) are dynamically computed and updated** for existing positions, separately for BUY and SELL.

## Data inputs and timeframe usage

`get_position_details()` fetches indicator‑enriched market data for **1h and 4h** timeframes using `fetch_market_data_with_indicators()` and uses:
- 1h Bollinger bands and SMA_20 (middle) for the primary reference.
- 4h Bollinger bands and SMA_20 for a higher‑timeframe TP anchor.
- The previous **fully closed** 1h candle (`prev_close = df_1h["close"].iloc[-2]`) for SL selection.

Bollinger deltas are computed per timeframe:
- `delta_top = (upper - middle) / 5`
- `delta_bot = (middle - lower) / 5`

## BUY positions (side = Buy)

### Take profit
- Compute:
  - `tp_1h = upper_1h - delta_top_1h`
  - `tp_4h = upper_4h - delta_top_4h`
- Select TP:
  - `take_profit = max(tp_1h, tp_4h)`

### Stop loss
- If an existing SL equals `middle_1h - delta_bot_1h`, reuse it.
- Else if the previous 1h close is above the 1h middle band:
  - `stop_loss = middle_1h - delta_bot_1h`
- Else (price below middle band), use a risk‑balanced SL at one‑third of the TP distance:
  - `stop_loss = entry_price - (take_profit - entry_price) / 3`

## SELL positions (side = Sell)

### Take profit
- Compute:
  - `tp_1h = lower_1h + delta_bot_1h`
  - `tp_4h = lower_4h + delta_bot_4h`
- Select TP:
  - `take_profit = min(tp_1h, tp_4h)`

### Stop loss
- If an existing SL equals `middle_1h + delta_top_1h`, reuse it.
- Else if the previous 1h close is below the 1h middle band:
  - `stop_loss = middle_1h + delta_top_1h`
- Else (price above middle band), use a risk‑balanced SL at one‑third of the TP distance:
  - `stop_loss = entry_price - (take_profit - entry_price) / 3`
  - Equivalent form when `take_profit < entry_price`:
    - `stop_loss = entry_price + (entry_price - take_profit) / 3`

## Rounding rules

- `get_position_details()` rounds `stop_loss` and `take_profit` to the symbol tick size when available.
- `place_stop_loss_take_profit()` also rounds TP/SL to tick size before placing orders.

## How updates are applied

- `get_position_details()` returns the computed `stop_loss` and `take_profit` for the current open position.
- `place_or_update_sl_tp_orders()` is responsible for **canceling existing TP/SL orders** and placing new reduce‑only conditional orders at the updated prices.

## Notes

- The SL/TP update logic is **dynamic** because it re‑computes Bollinger‑based bands and uses the latest 1h/4h values on each call.
- If indicator data is missing or cannot be fetched, `get_position_details()` returns `None` and does not update orders.
