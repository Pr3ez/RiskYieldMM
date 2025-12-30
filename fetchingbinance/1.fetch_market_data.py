#!/usr/bin/env python3
"""
Download Binance Spot BTCUSDT klines to Parquet.

✓ 1-minute candles (change interval if you like)
✓ Resilient pagination up to the current moment
✓ Progress indicator
"""

import os
import time
from datetime import datetime

import pandas as pd
from binance.client import Client  # pip install python-binance

BASE_DIR = r"/media/przem/w/dataset_calc"

# ───────────────────────────────────────────────────────────
# 1. CONFIGURE ME
# ───────────────────────────────────────────────────────────
API_KEY = "YOUR_API_KEY"
API_SECRET = "YOUR_API_SECRET"

INTERVALS = [
    Client.KLINE_INTERVAL_1MINUTE,
    Client.KLINE_INTERVAL_5MINUTE,
    Client.KLINE_INTERVAL_15MINUTE,
    Client.KLINE_INTERVAL_1HOUR,
    Client.KLINE_INTERVAL_4HOUR,
    Client.KLINE_INTERVAL_1DAY,
]

INTERVAL_LABELS = {
    Client.KLINE_INTERVAL_1MINUTE: "1m",
}

START_DATE = "2021-01-01"
END_DATE = "2025-07-22"
SYMBOL = "BTCUSDT"
# ───────────────────────────────────────────────────────────

client = Client(API_KEY, API_SECRET)


def write_batch_to_parquet(batch_klines, out_file, interval_label):
    cols = [
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "close_time",
        "quote_asset_volume",
        "num_trades",
        "taker_buy_base_vol",
        "taker_buy_quote_vol",
        "ignore",
    ]
    df = pd.DataFrame(batch_klines, columns=cols)
    df = df[["timestamp", "open", "high", "low", "close", "volume"]]
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df[["open", "high", "low", "close", "volume"]] = df[
        ["open", "high", "low", "close", "volume"]
    ].astype(float)
    df["interval"] = interval_label
    df.to_parquet(out_file, index=False)


def fetch_and_save_spot(
    symbol, interval, interval_label, start_date, end_date, out_prefix
):
    print(f"Fetching SPOT {symbol} {interval_label} from {start_date} to {end_date}…")
    start_ts = int(pd.to_datetime(start_date).timestamp() * 1000)
    end_ts = int(pd.to_datetime(end_date).timestamp() * 1000)
    now_ts = int(datetime.utcnow().timestamp() * 1000)
    if end_ts > now_ts:
        end_ts = now_ts

    batch_no = 0
    total_ms = end_ts - start_ts
    folder = os.path.dirname(out_prefix)
    cur = start_ts

    # Remove old files
    for fname in os.listdir(folder):
        if fname.startswith(os.path.basename(out_prefix)) and fname.endswith(
            ".parquet"
        ):
            os.remove(os.path.join(folder, fname))

    while cur < end_ts:
        try:
            klines = client.get_klines(
                symbol=symbol,
                interval=interval,
                startTime=cur,
                endTime=end_ts,
                limit=1000,
            )
        except Exception as err:
            print(f"❌ API error: {err}; retrying in 5 s")
            time.sleep(5)
            continue
        if not klines:
            print("✅ No more data.")
            break

        last = klines[-1][0]
        cur = last + 1
        batch_no += 1
        pct = (cur - start_ts) / total_ms * 100
        print(
            f"[{interval_label} Batch {batch_no:>3}] {pct:6.2f}% – Last {datetime.utcfromtimestamp(last / 1000)} UTC"
        )

        out_file = f"{out_prefix}_{interval_label}_batch{batch_no:04d}.parquet"
        write_batch_to_parquet(klines, out_file, interval_label)
        time.sleep(0.5)

    print(
        f"Done fetching {interval_label}. Saved batches as{os.path.basename(out_prefix)}_{interval_label}_batchXXXX.parquet\n"
    )


if __name__ == "__main__":
    for interval in INTERVALS:
        lbl = INTERVAL_LABELS[interval]
        path = os.path.join(BASE_DIR, lbl)
        os.makedirs(path, exist_ok=True)
        prefix = os.path.join(path, f"{SYMBOL.lower()}_futures")
        fetch_and_save_spot(SYMBOL, interval, lbl, START_DATE, END_DATE, prefix)
