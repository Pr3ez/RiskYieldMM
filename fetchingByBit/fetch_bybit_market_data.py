#!/usr/bin/env python3
"""
Bybit v5 Market Data downloader → Parquet (resumable, sorted, verified)
- Supports: spot | linear | inverse
- Forward pagination (oldest → newest)
- Fetches: OHLCV klines, funding rates, open interest, mark/index prices
- Resumable: appends only data after the last saved timestamp
- Post-run integrity check across all written files
"""

import json
import logging
import os
import re
import time
from datetime import datetime, timezone

import polars as pl
import requests

# ────────────────── CONFIG ──────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # Current script directory
SYMBOL = "BTCUSDT"  # e.g. BTCUSDT (linear/spot), BTCUSD (inverse)
CATEGORY = "linear"  # spot | linear | inverse
START_DATE = "2021-01-01"
END_DATE = "now"  # supports "now", "today", ISO strings, YYYY-MM-DD

# What data to fetch
FETCH_KLINES = True
FETCH_FUNDING_RATE = True  # linear/inverse perpetuals only
FETCH_OPEN_INTEREST = True  # derivatives only
FETCH_MARK_PRICE = True  # derivatives only
FETCH_INDEX_PRICE = True  # derivatives only
FETCH_PREMIUM_INDEX = True  # perpetuals only
FETCH_LONG_SHORT_RATIO = True  # linear/inverse perpetuals only

INTERVALS = ["1", "5", "15", "60", "240", "D"]
LABELS = {
    "1": "1m",
    "5": "5m",
    "15": "15m",
    "60": "1h",
    "240": "4h",
    "D": "1d",
    "W": "1w",
    "M": "1M",
}

# Open Interest API uses different interval format
# Note: OI API does NOT support 1-minute granularity
OI_INTERVAL_MAP = {"5": "5min", "15": "15min", "60": "1h", "240": "4h", "D": "1d"}

# Long/Short Ratio API periods (not standard intervals)
# Maps our interval to API period: 5min, 15min, 30min, 1h, 4h, 1d
# Note: 1m and 8h are not available. The HTF workflow uses 5m for 1m
# broadcast and 15m natively for 15m feature rows.
LS_RATIO_PERIOD_MAP = {
    "5": "5min",
    "15": "15min",
    "60": "1h",
    "240": "4h",
    "D": "1d",
}

BYBIT_URL = "https://api.bybit.com/v5/market/kline"
SESSION = requests.Session()

# Logging setup
LOG_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    f"fetch_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# kline start-to-start (ms)
INTERVAL_MS = {
    "1": 60_000,
    "3": 180_000,
    "5": 300_000,
    "15": 900_000,
    "30": 1_800_000,
    "60": 3_600_000,
    "120": 7_200_000,
    "240": 14_400_000,
    "360": 21_600_000,
    "720": 43_200_000,
    "D": 86_400_000,
    "W": 7 * 86_400_000,
    "M": 30 * 86_400_000,
}

# zero-pad width for batch indices if starting fresh
DEFAULT_PAD_WIDTH = 6
TIMESTAMP_DTYPE = pl.Datetime("ms", "UTC")

# Performance & safety
REQUEST_SLEEP = 0.1  # seconds between requests (was 0.25)
CHECKPOINT_INTERVAL = 500  # save progress every N pages

# Progress tracking
PROGRESS_FILE = os.path.join(BASE_DIR, ".fetch_progress.json")


def save_progress(source: str, interval: str, last_ts: int, status: str):
    """Save fetch progress to resume after interruptions."""
    progress = {}
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE) as f:
                progress = json.load(f)
        except Exception:
            pass

    key = f"{SYMBOL}_{CATEGORY}_{source}_{interval}"
    progress[key] = {
        "last_timestamp_ms": last_ts,
        "last_update": datetime.now(timezone.utc).isoformat(),
        "status": status,
    }

    try:
        with open(PROGRESS_FILE, "w") as f:
            json.dump(progress, f, indent=2)
    except Exception as e:
        logger.warning(f"Failed to save progress: {e}")


def load_progress(source: str, interval: str) -> dict | None:
    """Load saved progress."""
    if not os.path.exists(PROGRESS_FILE):
        return None
    try:
        with open(PROGRESS_FILE) as f:
            progress = json.load(f)
        key = f"{SYMBOL}_{CATEGORY}_{source}_{interval}"
        return progress.get(key)
    except Exception:
        return None


# ────────────────── HELPERS ──────────────────
def _utc_from_ms(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)


def _fmt_ms(ms: int) -> str:
    return _utc_from_ms(ms).strftime("%Y-%m-%d %H:%M:%S")


def _normalize_timestamp_dtype(df: pl.DataFrame) -> pl.DataFrame:
    """Keep persisted timestamps stable across Polars versions.

    Existing local parquet files use millisecond UTC timestamps. Recent Polars
    constructors can infer microsecond UTC timestamps for newly fetched rows,
    and `pl.concat` refuses to stack those schemas without an explicit cast.
    """
    if "timestamp" not in df.columns:
        return df
    return df.with_columns(pl.col("timestamp").cast(TIMESTAMP_DTYPE))


def _to_ms(ts_like: str | datetime) -> int:
    """Return epoch ms from string or datetime, always UTC."""
    if isinstance(ts_like, datetime):
        dt = ts_like if ts_like.tzinfo else ts_like.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    else:
        # Parse string dates
        if ts_like.lower() in ("now", "today"):
            return int(datetime.now(timezone.utc).timestamp() * 1000)
        # Use polars for faster date parsing with explicit format
        dt_polars = (
            pl.Series([ts_like])
            .str.to_datetime("%Y-%m-%d")
            .dt.replace_time_zone("UTC")[0]
        )
        # Convert to epoch milliseconds
        return int(dt_polars.timestamp() * 1000)


def respect_rate_limit(resp: requests.Response) -> None:
    # Be defensive – Bybit headers vary by route
    remain = resp.headers.get("X-Bapi-Limit-Status") or resp.headers.get(
        "X-Bapi-Limit-Remaining"
    )
    reset = resp.headers.get("X-Bapi-Limit-Reset-Timestamp")
    try:
        if remain is not None and int(str(remain).split("/")[0]) <= 1 and reset:
            wait = max(0.0, (int(reset) - int(time.time() * 1000)) / 1000.0)
            if wait > 0:
                time.sleep(wait)
    except Exception:
        pass


def _klines_to_df(
    klines: list[list[str | float | int]], interval_label: str
) -> pl.DataFrame:
    # Bybit v5 returns: [start, open, high, low, close, volume, turnover, ...]
    cols = ["start", "open", "high", "low", "close", "volume", "turnover"]
    df = pl.DataFrame([dict(zip(cols, k[:7])) for k in klines])

    df = (
        df.with_columns(
            [
                pl.col("start").cast(pl.Int64).alias("timestamp_ms"),
                pl.col("open").cast(pl.Float64),
                pl.col("high").cast(pl.Float64),
                pl.col("low").cast(pl.Float64),
                pl.col("close").cast(pl.Float64),
                pl.col("volume").cast(pl.Float64),
                pl.col("turnover").cast(pl.Float64),
            ]
        )
        .with_columns(
            [
                pl.from_epoch("timestamp_ms", time_unit="ms")
                .dt.replace_time_zone("UTC")
                .alias("timestamp")
            ]
        )
        .with_columns([pl.lit(interval_label).alias("interval")])
        .select(
            [
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "turnover",
                "interval",
            ]
        )
    )

    return _normalize_timestamp_dtype(df)


def _list_existing_files(
    output_dir: str, sym_prefix: str
) -> list[tuple[int, str, int]]:
    """Return sorted list of (idx, fname, pad_digits) for existing symbol files."""
    files = []
    rx = re.compile(rf"^{re.escape(sym_prefix)}(\d+)\.parquet$")
    for fname in os.listdir(output_dir):
        m = rx.match(fname)
        if m:
            idx_str = m.group(1)
            files.append((int(idx_str), fname, len(idx_str)))
    files.sort(key=lambda x: x[0])
    return files


def _read_last_timestamp_ms(parquet_path: str) -> int | None:
    df = pl.read_parquet(parquet_path, columns=["timestamp"])
    if df.height == 0:
        return None
    return int(df["timestamp"][-1].timestamp() * 1000)


def _read_first_timestamp_ms(parquet_path: str) -> int | None:
    df = pl.read_parquet(parquet_path, columns=["timestamp"])
    if df.height == 0:
        return None
    return int(df["timestamp"][0].timestamp() * 1000)


def _read_rows(parquet_path: str) -> int:
    return pl.read_parquet(parquet_path, columns=["timestamp"]).height


def detect_gaps_in_pages(
    page_dfs: list[pl.DataFrame], step_ms: int, label: str
) -> list[str]:
    """Detect gaps between fetched pages in real-time."""
    if not page_dfs or len(page_dfs) < 2:
        return []

    gaps = []
    for i in range(1, len(page_dfs)):
        prev_last = int(page_dfs[i - 1]["timestamp"][-1].timestamp() * 1000)
        curr_first = int(page_dfs[i]["timestamp"][0].timestamp() * 1000)
        expected_gap = step_ms
        actual_gap = curr_first - prev_last

        if actual_gap > expected_gap:
            gap_duration = (actual_gap - expected_gap) / 1000 / 60  # minutes
            gap_msg = f"Gap between page {i - 1} and {i}: {_fmt_ms(prev_last)} -> {_fmt_ms(curr_first)} (missing {gap_duration:.1f} min)"
            gaps.append(gap_msg)
            logger.warning(f"[{label}] {gap_msg}")

    return gaps


def save_checkpoint(
    page_dfs: list[pl.DataFrame],
    output_dir: str,
    sym_prefix: str,
    label: str,
    checkpoint_num: int,
) -> None:
    """Save checkpoint of accumulated pages."""
    if not page_dfs:
        return

    checkpoint_file = os.path.join(output_dir, f".checkpoint_{checkpoint_num}.parquet")
    try:
        df = pl.concat([_normalize_timestamp_dtype(page) for page in page_dfs])
        df = df.unique(subset=["timestamp"], keep="last")
        df = df.sort("timestamp")
        _normalize_timestamp_dtype(df).write_parquet(checkpoint_file)
        logger.info(f"[{label}] Checkpoint {checkpoint_num}: saved {df.height} rows")
        print(f"💾 Checkpoint {checkpoint_num}: {df.height} rows saved")
    except Exception as e:
        logger.error(f"[{label}] Checkpoint save failed: {e}")


def load_checkpoint(output_dir: str) -> pl.DataFrame | None:
    """Load most recent checkpoint if exists."""
    import glob

    checkpoints = sorted(glob.glob(os.path.join(output_dir, ".checkpoint_*.parquet")))
    if not checkpoints:
        return None

    try:
        latest = checkpoints[-1]
        df = _normalize_timestamp_dtype(pl.read_parquet(latest))
        logger.info(
            f"Loaded checkpoint: {df.height} rows from {os.path.basename(latest)}"
        )
        print(f"📂 Loaded checkpoint: {df.height} rows")
        return df
    except Exception as e:
        logger.warning(f"Failed to load checkpoint: {e}")
        return None


def clean_checkpoints(output_dir: str) -> None:
    """Remove checkpoint files after successful completion."""
    import glob

    for cp in glob.glob(os.path.join(output_dir, ".checkpoint_*.parquet")):
        try:
            os.remove(cp)
        except Exception:
            pass


def _verify_integrity(output_dir: str, sym_prefix: str, step_ms: int) -> None:
    """
    Checks:
      • inside-file ascending + step anomalies
      • cross-file boundary ascending + step anomalies
    Prints a compact summary.
    """
    import glob

    files = sorted(glob.glob(os.path.join(output_dir, f"{sym_prefix}*.parquet")))
    if not files:
        print("⚠️  Verify: no files found.")
        return

    gaps = overlaps = irregular = 0
    b_gaps = b_overlaps = b_irregular = 0
    bad_files = []
    last_ms = None

    for fp in files:
        df = pl.read_parquet(fp, columns=["timestamp"])
        if df.height == 0:
            bad_files.append(os.path.basename(fp) + " (empty)")
            continue

        # Inside-file checks
        ms = (df["timestamp"].dt.epoch(time_unit="ms")).to_list()
        diffs = [ms[i] - ms[i - 1] for i in range(1, len(ms))]

        file_overlaps = sum(1 for d in diffs if d <= 0)
        file_gaps = sum(1 for d in diffs if d > step_ms)
        file_irregular = sum(1 for d in diffs if 0 < d < step_ms)

        overlaps += file_overlaps
        gaps += file_gaps
        irregular += file_irregular

        is_monotonic = all(ms[i] > ms[i - 1] for i in range(1, len(ms)))
        if not is_monotonic or file_overlaps or file_gaps or file_irregular:
            bad_files.append(os.path.basename(fp))

        # Cross-file boundary check
        if last_ms is not None:
            delta = ms[0] - last_ms
            if delta <= 0:
                b_overlaps += 1
            elif delta > step_ms:
                b_gaps += 1
            elif 0 < delta < step_ms:
                b_irregular += 1

        last_ms = ms[-1]

    print("── Integrity Check ─────────────────────────────────")
    print(f"Files checked          : {len(files)}")
    print(f"Inside-file  overlaps  : {overlaps}")
    print(f"Inside-file  gaps      : {gaps}")
    print(f"Inside-file  irregular : {irregular}")
    print(f"Boundary     overlaps  : {b_overlaps}")
    print(f"Boundary     gaps      : {b_gaps}")
    print(f"Boundary     irregular : {b_irregular}")
    if bad_files:
        sample = ", ".join(bad_files[:5]) + (" …" if len(bad_files) > 5 else "")
        print(f"⚠️  Files with issues   : {len(bad_files)} → {sample}")
    else:
        print("✓ All files strictly ascending; no anomalies detected.")
    print("───────────────────────────────────────────────────")


# ────────────────── CORE ──────────────────
def fetch_and_save(
    symbol: str,
    category: str,
    interval: str,
    label: str,
    start_date: str,
    end_date: str,
) -> None:
    """
    Resumable downloader:
      - Fetches oldest→newest pages from Bybit (forward pagination)
      - Merges and globally sorts (oldest→newest)
      - Writes/extends chunked parquet files in sorted-{label}-bybit-{category}
      - On resume, fetches ONLY candles strictly after the max saved timestamp
      - Keeps fixed chunk size and numbering; tops up last partial file first
      - Verifies sorting/step integrity at the end
    """
    logger.info(f"=== Starting fetch: {category.upper()} {symbol} {label} ===")
    print(f"\n=== {category.upper()} {symbol} {label} ===")

    req_start_ts = _to_ms(start_date)
    req_end_ts = _to_ms(end_date)
    now_ts = int(datetime.now(timezone.utc).timestamp() * 1000)
    end_ts = min(req_end_ts, now_ts)

    output_dir = os.path.join(BASE_DIR, f"sorted-{label}-bybit-{category}")
    os.makedirs(output_dir, exist_ok=True)
    sym_prefix = f"{symbol.lower()}_{category}_sorted_batch_"
    step_ms = INTERVAL_MS[interval]

    existing = _list_existing_files(output_dir, sym_prefix)
    is_resume = len(existing) > 0

    # Determine resume point and chunk size
    start_ts = req_start_ts
    start_index = 0
    pad_width = DEFAULT_PAD_WIDTH

    if is_resume:
        last_idx, last_fname, pad_digits = existing[-1]
        pad_width = max(pad_width, pad_digits)
        last_path = os.path.join(output_dir, last_fname)
        last_ts_ms = _read_last_timestamp_ms(last_path)
        first_ts_ms = _read_first_timestamp_ms(os.path.join(output_dir, existing[0][1]))
        if last_ts_ms is not None:
            # fetch strictly after the last saved candle
            start_ts = max(req_start_ts, last_ts_ms + step_ms)
        start_index = last_idx + 1

        # Infer chunk size from first file (stable reference)
        chunk_size = _read_rows(os.path.join(output_dir, existing[0][1]))
        print(
            f"Resuming from {label} {symbol}: files {existing[0][0]}..{last_idx}, "
            f"first_ts={_fmt_ms(first_ts_ms) if first_ts_ms else 'N/A'}, "
            f"last_ts={_fmt_ms(last_ts_ms) if last_ts_ms else 'N/A'}, "
            f"chunk_size={chunk_size}"
        )
    else:
        chunk_size = None  # derive after initial download

    if start_ts > end_ts:
        msg = "Up-to-date: no new data to fetch."
        print(msg)
        logger.info(msg)
        # Verify existing set anyway
        _verify_integrity(output_dir, sym_prefix, step_ms)
        save_progress("klines", label, end_ts, "up-to-date")
        return

    # ── Forward pagination (oldest → newest) ──
    step_window_ms = step_ms * 1000  # up to 1000 bars per call
    batch_no = 0
    cur_start = start_ts
    total_ms = max(1, end_ts - start_ts)
    page_dfs: list[pl.DataFrame] = []
    checkpoint_counter = 0
    last_checkpoint_page = 0
    fetch_start_time = time.time()

    # Try loading checkpoint if exists
    checkpoint_df = load_checkpoint(output_dir)
    if checkpoint_df is not None and checkpoint_df.height > 0:
        last_checkpoint_ts = int(checkpoint_df["timestamp"].max().timestamp() * 1000)
        if last_checkpoint_ts > start_ts:
            start_ts = last_checkpoint_ts + step_ms
            cur_start = start_ts
            page_dfs.append(checkpoint_df)
            print(f"Resuming from checkpoint: {_fmt_ms(last_checkpoint_ts)}")
            logger.info(f"Resuming from checkpoint: {checkpoint_df.height} rows loaded")

    while cur_start <= end_ts:
        cur_end = min(cur_start + step_window_ms - step_ms, end_ts)

        params = {
            "category": category,
            "symbol": symbol,
            "interval": interval,
            "start": cur_start,
            "end": cur_end,
            "limit": 1000,
        }

        try:
            resp = SESSION.get(BYBIT_URL, params=params, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            if data.get("retCode") != 0:
                error_msg = f"Bybit error: {data}"
                print(error_msg)
                logger.error(error_msg)
                if data.get("retCode") in (10006, 10016):
                    time.sleep(2)
                    continue
                raise RuntimeError(f"retCode {data['retCode']}: {data.get('retMsg')}")
            klines = data["result"]["list"]
            respect_rate_limit(resp)
        except Exception as e:
            error_msg = f"API error: {e}; retrying in 5 s"
            print(f"❌ {error_msg}")
            logger.error(error_msg)
            time.sleep(5)
            continue

        if not klines:
            # no data: jump past this window
            cur_start = cur_end + step_ms
            continue

        # within-page: oldest→newest
        klines_sorted = sorted(klines, key=lambda x: int(x[0]))
        first_ts = int(klines_sorted[0][0])
        last_ts = int(klines_sorted[-1][0])

        batch_no += 1
        print(
            f"→ page {batch_no:>4}: {len(klines_sorted):>4} rows "
            f"[{_fmt_ms(first_ts)} .. {_fmt_ms(last_ts)}]"
        )

        page_dfs.append(_klines_to_df(klines_sorted, label))

        # Advance window strictly after last bar
        cur_start = last_ts + step_ms

        # Progress reporting with speed metrics
        elapsed = time.time() - fetch_start_time
        rate = batch_no / elapsed if elapsed > 0 else 0
        pct = (last_ts - start_ts) / total_ms * 100
        eta_sec = (
            ((end_ts - last_ts) / (last_ts - start_ts) * elapsed)
            if last_ts > start_ts
            else 0
        )
        print(
            f"[{label:>3} {batch_no:>4}] {pct:6.2f}% | {rate:.2f} pg/s | ETA {eta_sec / 60:.1f}m"
        )

        # Checkpoint save every N pages
        if batch_no - last_checkpoint_page >= CHECKPOINT_INTERVAL:
            gaps = detect_gaps_in_pages(page_dfs, step_ms, label)
            if gaps:
                print(f"⚠️  {len(gaps)} gaps detected:")
                for gap in gaps[:3]:  # show first 3
                    print(f"   {gap}")

            checkpoint_counter += 1
            save_checkpoint(page_dfs, output_dir, sym_prefix, label, checkpoint_counter)
            last_checkpoint_page = batch_no

        time.sleep(REQUEST_SLEEP)

    if not page_dfs:
        msg = "No pages returned; nothing to write."
        print(msg)
        logger.warning(msg)
        _verify_integrity(output_dir, sym_prefix, step_ms)
        save_progress("klines", label, end_ts, "no-data")
        return

    # Final gap check before writing
    gaps = detect_gaps_in_pages(page_dfs, step_ms, label)
    if gaps:
        print(f"\n⚠️  WARNING: {len(gaps)} gaps detected in fetched data!")
        logger.error(f"[{label}] {len(gaps)} gaps detected:")
        for gap in gaps:
            logger.error(f"  {gap}")
        print("Check log file for details.\n")

    # Build new sorted block
    print(f"Merging {len(page_dfs)} pages...")
    new_df = pl.concat([_normalize_timestamp_dtype(page) for page in page_dfs])
    print(f"Deduplicating {new_df.height} rows...")
    new_df = new_df.unique(subset=["timestamp"], keep="last")
    print(f"Sorting {new_df.height} unique rows...")
    new_df = _normalize_timestamp_dtype(new_df.sort("timestamp"))

    # ── Initial build: create fixed-size chunks ──
    if not is_resume:
        print(f"Writing sorted files → {output_dir}")
        # Define chunk_size from page count (≈1000 rows per file)
        n_pages = len(page_dfs)
        chunk_size = max(1, new_df.height // max(1, n_pages))

        # Clean old files for this symbol
        for _, fname, _ in _list_existing_files(output_dir, sym_prefix):
            try:
                os.remove(os.path.join(output_dir, fname))
            except Exception:
                pass

        # Write equal chunks + leftover
        n_written = 0
        n_full = new_df.height // chunk_size
        for i in range(n_full):
            chunk = new_df.slice(i * chunk_size, chunk_size)
            out_path = os.path.join(
                output_dir, f"{sym_prefix}{i:0{DEFAULT_PAD_WIDTH}}.parquet"
            )
            _normalize_timestamp_dtype(chunk).write_parquet(out_path)
            n_written += chunk.height
            print(f"✓ {os.path.basename(out_path)}  ({chunk.height} rows)")

        leftover = new_df.slice(n_written)
        if leftover.height > 0:
            out_path = os.path.join(
                output_dir, f"{sym_prefix}{n_full:0{DEFAULT_PAD_WIDTH}}.parquet"
            )
            _normalize_timestamp_dtype(leftover).write_parquet(out_path)
            print(f"✓ {os.path.basename(out_path)}  ({leftover.height} rows)")

        # Clean up checkpoints and verify integrity
        clean_checkpoints(output_dir)
        _verify_integrity(output_dir, sym_prefix, step_ms)

        elapsed_total = time.time() - fetch_start_time
        final_msg = f"Done: {symbol} {label}  total_rows={new_df.height}  files={n_full + (1 if leftover.height > 0 else 0)}  time={elapsed_total / 60:.1f}m  speed={batch_no / elapsed_total:.2f} pg/s"
        print(final_msg)
        logger.info(final_msg)
        save_progress(
            "klines",
            label,
            int(new_df["timestamp"].max().timestamp() * 1000),
            "complete",
        )
        return

    # ── Resume: top-up last file, then append fixed-size chunks ──
    print(f"Appending sorted rows → {output_dir}")
    if not chunk_size or chunk_size <= 0:
        chunk_size = new_df.height

    # 1) Top-up last partial file (if any)
    last_idx, last_fname, _ = existing[-1]
    last_path = os.path.join(output_dir, last_fname)
    last_rows = _read_rows(last_path)
    consumed = 0

    if last_rows < chunk_size and new_df.height > 0:
        need = min(chunk_size - last_rows, new_df.height)
        if need > 0:
            last_df = _normalize_timestamp_dtype(pl.read_parquet(last_path))
            combined = pl.concat(
                [last_df, _normalize_timestamp_dtype(new_df.slice(0, need))]
            )
            combined = _normalize_timestamp_dtype(combined.sort("timestamp"))
            combined.write_parquet(last_path)
            consumed = need
            print(f"↻ topped-up {last_fname}: {last_rows} → {combined.height} rows")

    # 2) Write remaining in fixed-size chunks
    remaining = new_df.slice(consumed)
    if remaining.height == 0:
        _verify_integrity(output_dir, sym_prefix, step_ms)
        print("No more rows after top-up. Done.")
        return

    n_full = remaining.height // chunk_size
    for i in range(n_full):
        chunk = remaining.slice(i * chunk_size, chunk_size)
        out_path = os.path.join(
            output_dir, f"{sym_prefix}{(start_index + i):0{DEFAULT_PAD_WIDTH}}.parquet"
        )
        _normalize_timestamp_dtype(chunk).write_parquet(out_path)
        print(f"✓ {os.path.basename(out_path)}  ({chunk.height} rows)")

    leftover = remaining.slice(n_full * chunk_size)
    if leftover.height > 0:
        out_path = os.path.join(
            output_dir,
            f"{sym_prefix}{(start_index + n_full):0{DEFAULT_PAD_WIDTH}}.parquet",
        )
        _normalize_timestamp_dtype(leftover).write_parquet(out_path)
        print(f"✓ {os.path.basename(out_path)}  ({leftover.height} rows)")

    # Clean up checkpoints and verify integrity
    clean_checkpoints(output_dir)
    _verify_integrity(output_dir, sym_prefix, step_ms)

    elapsed_total = time.time() - fetch_start_time
    final_msg = f"Done (resume): {symbol} {label}  added_rows={new_df.height}  new_files={n_full + (1 if leftover.height > 0 else 0)}  time={elapsed_total / 60:.1f}m  speed={batch_no / elapsed_total:.2f} pg/s"
    print(final_msg)
    logger.info(final_msg)
    save_progress(
        "klines", label, int(new_df["timestamp"].max().timestamp() * 1000), "complete"
    )


# ────────────────── ADDITIONAL DATA FETCHERS ──────────────────
def fetch_funding_rate(
    symbol: str, category: str, start_date: str, end_date: str
) -> None:
    """Fetch historical funding rates (perpetuals only)."""
    if category not in ["linear", "inverse"]:
        return

    print(f"\n=== FUNDING RATE {category.upper()} {symbol} ===")

    req_start_ts = _to_ms(start_date)
    req_end_ts = _to_ms(end_date)
    now_ts = int(datetime.now(timezone.utc).timestamp() * 1000)
    end_ts = min(req_end_ts, now_ts)

    output_dir = os.path.join(BASE_DIR, f"funding-rate-bybit-{category}")
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f"{symbol.lower()}_funding_rate.parquet")

    # Check resume point
    start_ts = req_start_ts
    if os.path.exists(output_file):
        existing_df = pl.read_parquet(output_file)
        if existing_df.height > 0:
            last_ts = int(existing_df["fundingRateTimestamp"].max())
            start_ts = max(req_start_ts, last_ts + 1)
            print(f"Resuming from {_fmt_ms(last_ts)}")

    if start_ts > end_ts:
        print("Up-to-date: no new funding rate data.")
        return

    # Fetch data
    all_data = []
    url = "https://api.bybit.com/v5/market/funding/history"
    cur_end = end_ts  # Paginate backwards from end (API returns newest first)

    while cur_end >= start_ts:
        params = {
            "category": category,
            "symbol": symbol,
            "startTime": start_ts,
            "endTime": cur_end,
            "limit": 200,
        }

        try:
            resp = SESSION.get(url, params=params, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            if data.get("retCode") != 0:
                print(f"Error: {data}")
                break

            records = data["result"]["list"]
            if not records:
                break

            all_data.extend(records)
            # API returns DESCENDING order (newest first)
            # records[-1] is the OLDEST record in this batch
            oldest_time = int(records[-1]["fundingRateTimestamp"])
            newest_time = int(records[0]["fundingRateTimestamp"])
            print(
                f"Fetched {len(records)} funding records: {_fmt_ms(oldest_time)} to {_fmt_ms(newest_time)}"
            )

            # Move window backwards to fetch older data
            cur_end = oldest_time - 1

            respect_rate_limit(resp)
            time.sleep(0.2)

        except Exception as e:
            print(f"Error: {e}")
            break

    if all_data:
        new_df = pl.DataFrame(all_data)
        new_df = new_df.with_columns(
            [
                pl.col("fundingRateTimestamp").cast(pl.Int64),
                pl.col("fundingRate").cast(pl.Float64),
            ]
        ).with_columns(
            [
                pl.from_epoch("fundingRateTimestamp", time_unit="ms")
                .dt.replace_time_zone("UTC")
                .alias("timestamp")
            ]
        )

        new_df = _normalize_timestamp_dtype(new_df)

        if os.path.exists(output_file):
            old_df = _normalize_timestamp_dtype(pl.read_parquet(output_file))
            combined = pl.concat([old_df, new_df])
            combined = combined.unique(subset=["fundingRateTimestamp"], keep="last")
            combined = _normalize_timestamp_dtype(
                combined.sort("fundingRateTimestamp")
            )
            combined.write_parquet(output_file)
            print(f"✓ Updated: {combined.height} total records")
        else:
            new_df = _normalize_timestamp_dtype(new_df.sort("fundingRateTimestamp"))
            new_df.write_parquet(output_file)
            print(f"✓ Created: {new_df.height} records")


def fetch_open_interest(
    symbol: str,
    category: str,
    interval: str,
    label: str,
    start_date: str,
    end_date: str,
) -> None:
    """Fetch historical open interest data (derivatives only)."""
    if category == "spot":
        return

    # Check if interval is supported for Open Interest API
    if interval not in OI_INTERVAL_MAP:
        print(
            f"\n=== OPEN INTEREST {category.upper()} {symbol} {label} === SKIPPED (1m not supported)"
        )
        return

    oi_interval = OI_INTERVAL_MAP[interval]  # Convert to OI API format
    print(
        f"\n=== OPEN INTEREST {category.upper()} {symbol} {label} (API interval: {oi_interval}) ==="
    )

    req_start_ts = _to_ms(start_date)
    req_end_ts = _to_ms(end_date)
    now_ts = int(datetime.now(timezone.utc).timestamp() * 1000)
    end_ts = min(req_end_ts, now_ts)

    output_dir = os.path.join(BASE_DIR, f"open-interest-{label}-bybit-{category}")
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f"{symbol.lower()}_oi.parquet")

    # Check resume
    start_ts = req_start_ts
    if os.path.exists(output_file):
        existing_df = pl.read_parquet(output_file)
        if existing_df.height > 0:
            last_ts = int(existing_df["timestamp"].dt.epoch(time_unit="ms").max())
            start_ts = max(req_start_ts, last_ts + INTERVAL_MS[interval])
            print(f"Resuming from {_fmt_ms(last_ts)}")

    if start_ts > end_ts:
        print("Up-to-date.")
        return

    # Fetch
    all_data = []
    url = "https://api.bybit.com/v5/market/open-interest"
    cur_start = start_ts
    step_ms = INTERVAL_MS[interval]
    window_ms = step_ms * 200

    while cur_start <= end_ts:
        cur_end = min(cur_start + window_ms, end_ts)
        params = {
            "category": category,
            "symbol": symbol,
            "intervalTime": oi_interval,  # Use converted interval format
            "startTime": cur_start,
            "endTime": cur_end,
            "limit": 200,
        }

        try:
            resp = SESSION.get(url, params=params, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            if data.get("retCode") != 0:
                print(f"Error: {data}")
                break

            records = data["result"]["list"]
            if not records:
                cur_start = cur_end + step_ms
                continue

            # API returns DESCENDING order - sort to ASCENDING
            records_sorted = sorted(records, key=lambda x: int(x["timestamp"]))
            all_data.extend(records_sorted)

            oldest_time = int(records_sorted[0]["timestamp"])
            newest_time = int(records_sorted[-1]["timestamp"])
            cur_start = newest_time + step_ms
            print(
                f"Fetched {len(records_sorted)} OI records: {_fmt_ms(oldest_time)} to {_fmt_ms(newest_time)}"
            )
            respect_rate_limit(resp)
            time.sleep(0.2)

        except Exception as e:
            print(f"Error: {e}")
            break

    if all_data:
        new_df = pl.DataFrame(all_data)
        new_df = new_df.with_columns(
            [
                pl.col("timestamp").cast(pl.Int64).alias("timestamp_ms"),
                pl.col("openInterest").cast(pl.Float64),
            ]
        ).with_columns(
            [
                pl.from_epoch("timestamp_ms", time_unit="ms")
                .dt.replace_time_zone("UTC")
                .alias("timestamp")
            ]
        )

        new_df = _normalize_timestamp_dtype(new_df)

        if os.path.exists(output_file):
            old_df = _normalize_timestamp_dtype(pl.read_parquet(output_file))
            combined = pl.concat([old_df, new_df])
            combined = combined.unique(subset=["timestamp_ms"], keep="last")
            combined = _normalize_timestamp_dtype(combined.sort("timestamp"))
            combined.write_parquet(output_file)
            print(f"✓ Updated: {combined.height} total records")
        else:
            new_df = _normalize_timestamp_dtype(new_df.sort("timestamp"))
            new_df.write_parquet(output_file)
            print(f"✓ Created: {new_df.height} records")


def fetch_mark_index_premium(
    symbol: str,
    category: str,
    interval: str,
    label: str,
    start_date: str,
    end_date: str,
    data_type: str,
) -> None:
    """Fetch mark/index/premium price klines."""
    if category == "spot" and data_type != "index":
        return

    type_label = {
        "mark": "MARK PRICE",
        "index": "INDEX PRICE",
        "premium": "PREMIUM INDEX",
    }[data_type]
    print(f"\n=== {type_label} {category.upper()} {symbol} {label} ===")

    req_start_ts = _to_ms(start_date)
    req_end_ts = _to_ms(end_date)
    now_ts = int(datetime.now(timezone.utc).timestamp() * 1000)
    end_ts = min(req_end_ts, now_ts)

    output_dir = os.path.join(BASE_DIR, f"{data_type}-price-{label}-bybit-{category}")
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f"{symbol.lower()}_{data_type}.parquet")

    # Check resume
    start_ts = req_start_ts
    if os.path.exists(output_file):
        existing_df = pl.read_parquet(output_file)
        if existing_df.height > 0:
            last_ts = int(existing_df["timestamp"].dt.epoch(time_unit="ms").max())
            start_ts = max(req_start_ts, last_ts + INTERVAL_MS[interval])
            print(f"Resuming from {_fmt_ms(last_ts)}")

    if start_ts > end_ts:
        print("Up-to-date.")
        return

    # Fetch
    url_map = {
        "mark": "https://api.bybit.com/v5/market/mark-price-kline",
        "index": "https://api.bybit.com/v5/market/index-price-kline",
        "premium": "https://api.bybit.com/v5/market/premium-index-price-kline",
    }
    url = url_map[data_type]

    all_data = []
    cur_start = start_ts
    step_ms = INTERVAL_MS[interval]
    # Match the kline fetcher semantics exactly: 1000 bars per request with an
    # inclusive end timestamp. Without subtracting one step from `cur_end`, a
    # [start, end] request spans 1001 timestamps while the API still returns at
    # most 1000 rows, which drops one boundary bar every page.
    window_ms = step_ms * 1000

    while cur_start <= end_ts:
        cur_end = min(cur_start + window_ms - step_ms, end_ts)
        params = {
            "category": category,
            "symbol": symbol,
            "interval": interval,
            "start": cur_start,
            "end": cur_end,
            "limit": 1000,
        }

        try:
            resp = SESSION.get(url, params=params, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            if data.get("retCode") != 0:
                print(f"Error: {data}")
                break

            records = data["result"]["list"]
            if not records:
                cur_start = cur_end + step_ms
                continue

            # API returns DESCENDING order - sort to ASCENDING
            records_sorted = sorted(records, key=lambda x: int(x[0]))

            # Parse: [start, open, high, low, close]
            for rec in records_sorted:
                all_data.append(
                    {
                        "timestamp_ms": int(rec[0]),
                        "open": float(rec[1]),
                        "high": float(rec[2]),
                        "low": float(rec[3]),
                        "close": float(rec[4]),
                    }
                )

            oldest_time = int(records_sorted[0][0])
            newest_time = int(records_sorted[-1][0])
            cur_start = newest_time + step_ms
            print(
                f"Fetched {len(records_sorted)} {data_type} records: {_fmt_ms(oldest_time)} to {_fmt_ms(newest_time)}"
            )
            respect_rate_limit(resp)
            time.sleep(0.2)

        except Exception as e:
            print(f"Error: {e}")
            break

    if all_data:
        new_df = pl.DataFrame(all_data)
        new_df = new_df.with_columns(
            [
                pl.from_epoch("timestamp_ms", time_unit="ms")
                .dt.replace_time_zone("UTC")
                .alias("timestamp")
            ]
        )

        new_df = _normalize_timestamp_dtype(new_df)

        if os.path.exists(output_file):
            old_df = _normalize_timestamp_dtype(pl.read_parquet(output_file))
            combined = pl.concat([old_df, new_df])
            combined = combined.unique(subset=["timestamp_ms"], keep="last")
            combined = _normalize_timestamp_dtype(combined.sort("timestamp"))
            combined.write_parquet(output_file)
            print(f"✓ Updated: {combined.height} total records")
        else:
            new_df = _normalize_timestamp_dtype(new_df.sort("timestamp"))
            new_df.write_parquet(output_file)
            print(f"✓ Created: {new_df.height} records")


def fetch_long_short_ratio(
    symbol: str,
    category: str,
    interval: str,
    label: str,
    start_date: str,
    end_date: str,
) -> None:
    """
    Fetch historical long/short account ratio data (perpetuals only).

    This is crowd sentiment data - % of accounts long vs short.
    Useful for contrarian signals (extreme readings often precede reversals).

    API: GET /v5/market/account-ratio
    Periods: 5min, 15min, 30min, 1h, 4h, 1d (8h not available)
    Uses startTime/endTime plus cursor pagination. On resume, fetches only
    records strictly after the latest local timestamp.
    """
    if category not in ["linear", "inverse"]:
        return

    # Check if interval is supported
    if interval not in LS_RATIO_PERIOD_MAP:
        print(
            f"\n=== LONG/SHORT RATIO {category.upper()} {symbol} {label} === SKIPPED (period not supported)"
        )
        return

    ls_period = LS_RATIO_PERIOD_MAP[interval]
    print(
        f"\n=== LONG/SHORT RATIO {category.upper()} {symbol} {label} (API period: {ls_period}) ==="
    )

    req_start_ts = _to_ms(start_date)
    req_end_ts = _to_ms(end_date)
    now_ts = int(datetime.now(timezone.utc).timestamp() * 1000)
    end_ts = min(req_end_ts, now_ts)

    output_dir = os.path.join(BASE_DIR, f"long-short-ratio-{label}-bybit-{category}")
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f"{symbol.lower()}_ls_ratio.parquet")
    step_ms = INTERVAL_MS[interval]

    # Check resume point from the local parquet, same policy as the other
    # time-series fetchers.
    start_ts = req_start_ts
    existing_min_ts = None
    existing_max_ts = None
    if os.path.exists(output_file):
        existing_df = pl.read_parquet(output_file)
        if existing_df.height > 0:
            existing_min_ts = int(
                existing_df["timestamp"].dt.epoch(time_unit="ms").min()
            )
            existing_max_ts = int(
                existing_df["timestamp"].dt.epoch(time_unit="ms").max()
            )
            print(
                f"Existing data: {_fmt_ms(existing_min_ts)} to {_fmt_ms(existing_max_ts)} ({existing_df.height} rows)"
            )
            start_ts = max(req_start_ts, existing_max_ts + step_ms)
            print(f"Resuming from {_fmt_ms(existing_max_ts)}")

    if start_ts > end_ts:
        print("Up-to-date: no new long/short ratio data.")
        save_progress(
            "long_short_ratio",
            label,
            existing_max_ts if existing_max_ts is not None else end_ts,
            "up-to-date",
        )
        return

    # Fetch only the missing date range using cursor pagination.
    all_data = []
    url = "https://api.bybit.com/v5/market/account-ratio"
    cursor = None
    page = 0
    print(f"Requesting {_fmt_ms(start_ts)} to {_fmt_ms(end_ts)}")

    while True:
        params = {
            "category": category,
            "symbol": symbol,
            "period": ls_period,
            "limit": 500,
            "startTime": str(start_ts),
            "endTime": str(end_ts),
        }
        if cursor:
            params["cursor"] = cursor

        try:
            resp = SESSION.get(url, params=params, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            if data.get("retCode") != 0:
                print(f"Error: {data}")
                break

            records = data["result"]["list"]
            if not records:
                break

            # Parse all records
            batch_data = []
            for rec in records:
                ts = int(rec["timestamp"])
                # Be defensive even though the API should honor start/end.
                if start_ts <= ts <= end_ts:
                    batch_data.append(
                        {
                            "timestamp_ms": ts,
                            "buyRatio": float(rec["buyRatio"]),
                            "sellRatio": float(rec["sellRatio"]),
                        }
                    )

            all_data.extend(batch_data)

            # Progress
            batch_times = [int(rec["timestamp"]) for rec in records]
            oldest_in_batch = min(batch_times)
            newest_in_batch = max(batch_times)
            page += 1
            print(
                f"Page {page}: {len(batch_data)} in range, {_fmt_ms(oldest_in_batch)} to {_fmt_ms(newest_in_batch)}"
            )

            # Get next cursor
            next_cursor = data["result"].get("nextPageCursor", "")
            if not next_cursor:
                print("No more pages available")
                break
            if next_cursor == cursor:
                logger.warning("L/S ratio cursor did not advance; stopping pagination")
                break

            cursor = next_cursor
            respect_rate_limit(resp)
            time.sleep(0.2)

        except Exception as e:
            print(f"Error: {e}")
            break

    if all_data:
        new_df = pl.DataFrame(all_data)
        new_df = new_df.with_columns(
            [
                pl.from_epoch("timestamp_ms", time_unit="ms")
                .dt.replace_time_zone("UTC")
                .alias("timestamp")
            ]
        )

        # Dedupe and sort
        new_df = new_df.unique(subset=["timestamp_ms"], keep="last")
        new_df = _normalize_timestamp_dtype(new_df.sort("timestamp"))

        if os.path.exists(output_file):
            old_df = _normalize_timestamp_dtype(pl.read_parquet(output_file))
            combined = pl.concat([old_df, new_df])
            combined = combined.unique(subset=["timestamp_ms"], keep="last")
            combined = _normalize_timestamp_dtype(combined.sort("timestamp"))
            combined.write_parquet(output_file)
            print(
                f"✓ Updated: {combined.height} total records ({_fmt_ms(int(combined['timestamp_ms'].min()))} to {_fmt_ms(int(combined['timestamp_ms'].max()))})"
            )
            latest_ts = int(combined["timestamp_ms"].max())
        else:
            new_df = _normalize_timestamp_dtype(new_df)
            new_df.write_parquet(output_file)
            print(
                f"✓ Created: {new_df.height} records ({_fmt_ms(int(new_df['timestamp_ms'].min()))} to {_fmt_ms(int(new_df['timestamp_ms'].max()))})"
            )
            latest_ts = int(new_df["timestamp_ms"].max())
        save_progress("long_short_ratio", label, latest_ts, "complete")
    else:
        print("No new data fetched.")
        save_progress(
            "long_short_ratio",
            label,
            existing_max_ts if existing_max_ts is not None else start_ts,
            "no-data",
        )


# ────────────────── MAIN ──────────────────
if __name__ == "__main__":
    start_time = datetime.now(timezone.utc)
    logger.info("=" * 70)
    logger.info("BYBIT MARKET DATA FETCHER - SESSION START")
    logger.info("=" * 70)
    logger.info(f"Base directory: {BASE_DIR}")
    logger.info(f"Symbol: {SYMBOL} | Category: {CATEGORY}")
    logger.info(f"Date range: {START_DATE} → {END_DATE}")
    logger.info(f"Log file: {LOG_FILE}")

    print(f"Base directory: {BASE_DIR}")
    print(f"Symbol: {SYMBOL} | Category: {CATEGORY}")
    print(f"Date range: {START_DATE} → {END_DATE}\n")

    fetch_summary = {
        "sources_attempted": 0,
        "sources_completed": 0,
        "sources_failed": 0,
    }

    # 1. OHLCV Klines
    if FETCH_KLINES:
        for itv in INTERVALS:
            lbl = LABELS[itv]
            fetch_summary["sources_attempted"] += 1
            try:
                fetch_and_save(SYMBOL, CATEGORY, itv, lbl, START_DATE, END_DATE)
                fetch_summary["sources_completed"] += 1
            except Exception as e:
                fetch_summary["sources_failed"] += 1
                logger.error(f"Failed to fetch klines {lbl}: {e}")

    # 2. Funding Rate (perpetuals only)
    if FETCH_FUNDING_RATE and CATEGORY in ["linear", "inverse"]:
        fetch_summary["sources_attempted"] += 1
        try:
            fetch_funding_rate(SYMBOL, CATEGORY, START_DATE, END_DATE)
            fetch_summary["sources_completed"] += 1
        except Exception as e:
            fetch_summary["sources_failed"] += 1
            logger.error(f"Failed to fetch funding rate: {e}")

    # 3. Open Interest (derivatives only)
    if FETCH_OPEN_INTEREST and CATEGORY != "spot":
        for itv in INTERVALS:
            lbl = LABELS[itv]
            fetch_summary["sources_attempted"] += 1
            try:
                fetch_open_interest(SYMBOL, CATEGORY, itv, lbl, START_DATE, END_DATE)
                fetch_summary["sources_completed"] += 1
            except Exception as e:
                fetch_summary["sources_failed"] += 1
                logger.error(f"Failed to fetch OI {lbl}: {e}")

    # 4. Mark Price (derivatives only)
    if FETCH_MARK_PRICE and CATEGORY != "spot":
        for itv in INTERVALS:
            lbl = LABELS[itv]
            fetch_summary["sources_attempted"] += 1
            try:
                fetch_mark_index_premium(
                    SYMBOL, CATEGORY, itv, lbl, START_DATE, END_DATE, "mark"
                )
                fetch_summary["sources_completed"] += 1
            except Exception as e:
                fetch_summary["sources_failed"] += 1
                logger.error(f"Failed to fetch mark price {lbl}: {e}")

    # 5. Index Price
    if FETCH_INDEX_PRICE:
        for itv in INTERVALS:
            lbl = LABELS[itv]
            fetch_summary["sources_attempted"] += 1
            try:
                fetch_mark_index_premium(
                    SYMBOL, CATEGORY, itv, lbl, START_DATE, END_DATE, "index"
                )
                fetch_summary["sources_completed"] += 1
            except Exception as e:
                fetch_summary["sources_failed"] += 1
                logger.error(f"Failed to fetch index price {lbl}: {e}")

    # 6. Premium Index (perpetuals only)
    if FETCH_PREMIUM_INDEX and CATEGORY in ["linear", "inverse"]:
        for itv in INTERVALS:
            lbl = LABELS[itv]
            fetch_summary["sources_attempted"] += 1
            try:
                fetch_mark_index_premium(
                    SYMBOL, CATEGORY, itv, lbl, START_DATE, END_DATE, "premium"
                )
                fetch_summary["sources_completed"] += 1
            except Exception as e:
                fetch_summary["sources_failed"] += 1
                logger.error(f"Failed to fetch premium index {lbl}: {e}")

    # 7. Long/Short Ratio (perpetuals only)
    if FETCH_LONG_SHORT_RATIO and CATEGORY in ["linear", "inverse"]:
        for itv in INTERVALS:
            if itv in LS_RATIO_PERIOD_MAP:  # Only supported intervals
                lbl = LABELS[itv]
                fetch_summary["sources_attempted"] += 1
                try:
                    fetch_long_short_ratio(
                        SYMBOL, CATEGORY, itv, lbl, START_DATE, END_DATE
                    )
                    fetch_summary["sources_completed"] += 1
                except Exception as e:
                    fetch_summary["sources_failed"] += 1
                    logger.error(f"Failed to fetch L/S ratio {lbl}: {e}")

    # Final summary
    end_time = datetime.now(timezone.utc)
    duration = (end_time - start_time).total_seconds()

    print("\n" + "=" * 60)
    print("FETCH SESSION COMPLETE")
    print("=" * 60)
    print(f"Duration: {duration / 60:.1f} minutes")
    print(f"Sources attempted: {fetch_summary['sources_attempted']}")
    print(f"Sources completed: {fetch_summary['sources_completed']}")
    print(f"Sources failed: {fetch_summary['sources_failed']}")
    print(f"Log file: {LOG_FILE}")
    print("=" * 60 + "\n")

    logger.info("=" * 70)
    logger.info("FETCH SESSION COMPLETE")
    logger.info(f"Duration: {duration / 60:.1f} minutes")
    logger.info(f"Sources attempted: {fetch_summary['sources_attempted']}")
    logger.info(f"Sources completed: {fetch_summary['sources_completed']}")
    logger.info(f"Sources failed: {fetch_summary['sources_failed']}")
    logger.info("=" * 70)

    # Suggest running quality monitor
    if fetch_summary["sources_completed"] > 0:
        print("Next steps:")
        print("  1. Run data quality monitor:")
        print(f"     python data_quality_monitor.py --base-dir {BASE_DIR}")
        print("  2. Check for gaps:")
        print(f"     python gap_filler.py --base-dir {BASE_DIR} --dry-run")
        print()
