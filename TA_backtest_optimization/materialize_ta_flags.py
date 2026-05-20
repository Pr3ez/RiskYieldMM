#!/usr/bin/env python3
"""Materialize leakage-safe TA signal flags from canonical OHLCV bars.

The materializer has two outputs per asset/timeframe:
- HTF event rows: indicator values and signal events on closed HTF bars.
- Expanded 1m flags: binary model-facing flags active only after HTF close.

No provider data is fetched here. The only source is the canonical OHLCV tree
under ``data/htf_multiasset/{asset}/htf_canonical_ohlcv``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import polars as pl

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.feature_engineering.htf_asset_registry import (  # noqa: E402
    CORE_HTF_ASSET_IDS,
    get_htf_asset_spec,
    htf_asset_ids_from_csv,
)
from scripts.feature_engineering.htf_trading_calendar import (  # noqa: E402
    CANONICAL_DERIVED_TIMEFRAMES,
    normalize_canonical_timeframe,
    timeframe_minutes,
)


DEFAULT_TA_TIMEFRAMES = CANONICAL_DERIVED_TIMEFRAMES
TA_METADATA_COLUMNS = (
    "signal_source_tf",
    "signal_bar_open_ts",
    "signal_available_ts",
    "signal_valid_until_ts",
    "signal_valid_rows",
    "signal_params_hash",
)
INDICATOR_PARAMS: dict[str, Any] = {
    "adx_dmi": {"length": 14, "trend_threshold": 25.0, "range_threshold": 20.0},
    "rsi": {"length": 14, "oversold": 30.0, "overbought": 70.0},
    "macd": {"fast": 12, "slow": 26, "signal": 9},
    "vwap": {"anchor": "canonical_session_id"},
    "donchian": {"length": 20},
    "obv": {"ma_length": 20},
    "bollinger": {"length": 20, "std_mult": 2.0, "squeeze_window": 100, "squeeze_quantile": 0.15},
    "pivot": {"source": "previous_session_or_utc_day"},
    "supertrend": {"atr_length": 10, "multiplier": 3.0},
    "aroon": {"length": 14},
    "stochastic": {"k": 14, "smooth_k": 3, "d": 3, "oversold": 20.0, "overbought": 80.0},
}
PARAMS_HASH = hashlib.sha256(
    json.dumps(INDICATOR_PARAMS, sort_keys=True).encode("utf-8")
).hexdigest()[:16]


@dataclass(frozen=True)
class MaterializeTAResult:
    """One asset/timeframe TA materialization or status result."""

    asset_id: str
    timeframe: str
    source_path: Path
    source_1m_path: Path
    events_path: Path
    flags_path: Path
    meta_path: Path
    status: str
    event_rows: int = 0
    flag_rows: int = 0
    flag_columns: int = 0
    min_ts: datetime | None = None
    max_ts: datetime | None = None
    detail: str = ""


def project_root_from_cwd() -> Path:
    """Return the repository root when the command is run from any subfolder."""
    cwd = Path.cwd().resolve()
    for candidate in (cwd, cwd.parent, cwd.parent.parent):
        if (candidate / "data").exists() and (candidate / "scripts").exists():
            return candidate
    return PROJECT_ROOT


def canonical_ohlcv_path(project_root: Path, asset_id: str, timeframe: str) -> Path:
    """Return the canonical OHLCV parquet path for one asset/timeframe."""
    spec = get_htf_asset_spec(asset_id)
    tf = normalize_canonical_timeframe(timeframe)
    return (
        project_root
        / "data"
        / "htf_multiasset"
        / spec.slug
        / "htf_canonical_ohlcv"
        / tf
        / f"{spec.slug}_{tf}_canonical.parquet"
    )


def ta_signal_dir(project_root: Path, asset_id: str, timeframe: str) -> Path:
    """Return the TA signal output directory for one asset/timeframe."""
    spec = get_htf_asset_spec(asset_id)
    tf = normalize_canonical_timeframe(timeframe)
    return project_root / "data" / "htf_multiasset" / spec.slug / "ta_signal_flags" / tf


def ta_events_path(project_root: Path, asset_id: str, timeframe: str) -> Path:
    """Return the HTF TA event parquet path."""
    spec = get_htf_asset_spec(asset_id)
    tf = normalize_canonical_timeframe(timeframe)
    return ta_signal_dir(project_root, asset_id, tf) / f"{spec.slug}_{tf}_ta_events.parquet"


def ta_flags_path(project_root: Path, asset_id: str, timeframe: str) -> Path:
    """Return the expanded 1m TA flags parquet path."""
    spec = get_htf_asset_spec(asset_id)
    tf = normalize_canonical_timeframe(timeframe)
    return ta_signal_dir(project_root, asset_id, tf) / f"{spec.slug}_{tf}_ta_flags.parquet"


def ta_meta_path(project_root: Path, asset_id: str, timeframe: str) -> Path:
    """Return the TA signal metadata sidecar path."""
    return ta_flags_path(project_root, asset_id, timeframe).with_name(
        f"{ta_flags_path(project_root, asset_id, timeframe).stem}_meta.json"
    )


def parse_ta_timeframes(raw: str | tuple[str, ...] | list[str]) -> tuple[str, ...]:
    """Parse, normalize, and deduplicate TA source timeframes."""
    parts = (
        [part.strip() for part in raw.split(",") if part.strip()]
        if isinstance(raw, str)
        else [str(part).strip() for part in raw if str(part).strip()]
    )
    if not parts:
        parts = list(DEFAULT_TA_TIMEFRAMES)
    out: list[str] = []
    for part in parts:
        tf = normalize_canonical_timeframe(part)
        if tf == "1m":
            raise ValueError("TA flags are derived from higher timeframes, not 1m")
        if tf not in out:
            out.append(tf)
    return tuple(out)


def ta_flag_columns(columns: list[str] | tuple[str, ...], timeframe: str | None = None) -> list[str]:
    """Return model-facing TA flag columns from a schema/column list."""
    prefix = f"ta_{normalize_canonical_timeframe(timeframe)}_" if timeframe else "ta_"
    return [col for col in columns if col.startswith(prefix) and col not in TA_METADATA_COLUMNS]


def _json_default(value: Any) -> str:
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _to_pandas(df: pl.DataFrame) -> pd.DataFrame:
    out = df.to_pandas()
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)
    return out.sort_values("timestamp").reset_index(drop=True)


def _rma(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(alpha=1.0 / length, adjust=False, min_periods=length).mean()


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False, min_periods=span).mean()


def _cross_above(current: pd.Series, previous: pd.Series) -> pd.Series:
    return (current > previous) & (current.shift(1) <= previous.shift(1))


def _cross_below(current: pd.Series, previous: pd.Series) -> pd.Series:
    return (current < previous) & (current.shift(1) >= previous.shift(1))


def _bool_flag(value: pd.Series) -> pd.Series:
    return value.fillna(False).astype("int8")


def _rolling_argmax_position(values: pd.Series, length: int) -> pd.Series:
    return values.rolling(length, min_periods=length).apply(
        lambda arr: float(np.argmax(arr) + 1),
        raw=True,
    )


def _rolling_argmin_position(values: pd.Series, length: int) -> pd.Series:
    return values.rolling(length, min_periods=length).apply(
        lambda arr: float(np.argmin(arr) + 1),
        raw=True,
    )


def _session_key(pdf: pd.DataFrame) -> pd.Series:
    if "session_id" in pdf.columns:
        return pdf["session_id"].fillna("__missing_session__").astype(str)
    return pdf["timestamp"].dt.strftime("%Y-%m-%d")


def _pivot_levels(pdf: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series]:
    session_col = "session_date" if "session_date" in pdf.columns else None
    if session_col:
        day_key = pdf[session_col].astype(str)
    else:
        day_key = pdf["timestamp"].dt.strftime("%Y-%m-%d")
    session_ohlc = (
        pd.DataFrame(
            {
                "day_key": day_key,
                "high": pdf["high"],
                "low": pdf["low"],
                "close": pdf["close"],
            }
        )
        .groupby("day_key", sort=True)
        .agg(high=("high", "max"), low=("low", "min"), close=("close", "last"))
    )
    prev = session_ohlc.shift(1)
    pivot = (prev["high"] + prev["low"] + prev["close"]) / 3.0
    r1 = 2.0 * pivot - prev["low"]
    s1 = 2.0 * pivot - prev["high"]
    mapped_pivot = day_key.map(pivot)
    mapped_r1 = day_key.map(r1)
    mapped_s1 = day_key.map(s1)
    return mapped_pivot, mapped_r1, mapped_s1


def _supertrend(close: pd.Series, high: pd.Series, low: pd.Series, atr: pd.Series, multiplier: float) -> pd.Series:
    hl2 = (high + low) / 2.0
    basic_upper = hl2 + multiplier * atr
    basic_lower = hl2 - multiplier * atr
    direction = np.ones(len(close), dtype=np.int8)
    final_upper = basic_upper.to_numpy(copy=True)
    final_lower = basic_lower.to_numpy(copy=True)
    close_arr = close.to_numpy()
    for i in range(1, len(close)):
        if np.isnan(final_upper[i - 1]) or np.isnan(final_lower[i - 1]):
            direction[i] = direction[i - 1]
            continue
        if final_upper[i] >= final_upper[i - 1] and close_arr[i - 1] <= final_upper[i - 1]:
            final_upper[i] = final_upper[i - 1]
        if final_lower[i] <= final_lower[i - 1] and close_arr[i - 1] >= final_lower[i - 1]:
            final_lower[i] = final_lower[i - 1]
        if close_arr[i] > final_upper[i - 1]:
            direction[i] = 1
        elif close_arr[i] < final_lower[i - 1]:
            direction[i] = -1
        else:
            direction[i] = direction[i - 1]
    return pd.Series(direction, index=close.index)


def compute_ta_events(htf_df: pl.DataFrame, timeframe: str) -> pl.DataFrame:
    """Compute indicator values and closed-bar TA event flags for one HTF frame."""
    tf = normalize_canonical_timeframe(timeframe)
    minutes = timeframe_minutes(tf)
    pdf = _to_pandas(htf_df)
    if pdf.empty:
        return pl.DataFrame({"timestamp": []})

    prefix = f"ta_{tf}_"
    high = pdf["high"].astype(float)
    low = pdf["low"].astype(float)
    close = pdf["close"].astype(float)
    open_ = pdf["open"].astype(float)
    volume = pdf["volume"].fillna(0.0).astype(float)
    prev_close = close.shift(1)

    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    atr14 = _rma(tr, 14)
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=pdf.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=pdf.index)
    plus_di = 100.0 * _rma(plus_dm, 14) / atr14
    minus_di = 100.0 * _rma(minus_dm, 14) / atr14
    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    adx = _rma(dx, 14)

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    rs = _rma(gain, 14) / _rma(loss, 14)
    rsi = 100.0 - (100.0 / (1.0 + rs))

    ema_fast = _ema(close, 12)
    ema_slow = _ema(close, 26)
    macd = ema_fast - ema_slow
    macd_signal = _ema(macd, 9)
    macd_hist = macd - macd_signal

    typical_price = (high + low + close) / 3.0
    vwap_source = pd.DataFrame(
        {"session": _session_key(pdf), "tpv": typical_price * volume, "volume": volume}
    )
    cum_tpv = vwap_source.groupby("session", sort=False)["tpv"].cumsum()
    cum_vol = vwap_source.groupby("session", sort=False)["volume"].cumsum()
    vwap = cum_tpv / cum_vol.replace(0.0, np.nan)

    donchian_upper_prev = high.rolling(20, min_periods=20).max().shift(1)
    donchian_lower_prev = low.rolling(20, min_periods=20).min().shift(1)

    obv_delta = np.sign(close.diff().fillna(0.0)) * volume
    obv = pd.Series(obv_delta, index=pdf.index).cumsum()
    obv_ma = _ema(obv, 20)

    bb_mid = close.rolling(20, min_periods=20).mean()
    bb_std = close.rolling(20, min_periods=20).std(ddof=0)
    bb_upper = bb_mid + 2.0 * bb_std
    bb_lower = bb_mid - 2.0 * bb_std
    bb_width = (bb_upper - bb_lower) / bb_mid.replace(0.0, np.nan)
    bb_squeeze_threshold = bb_width.rolling(100, min_periods=100).quantile(0.15)
    bb_squeeze = bb_width <= bb_squeeze_threshold

    pivot, pivot_r1, pivot_s1 = _pivot_levels(pdf)

    atr10 = _rma(tr, 10)
    supertrend_dir = _supertrend(close, high, low, atr10, 3.0)
    supertrend_ready = atr10.notna()
    supertrend_prev_ready = supertrend_ready.shift(1, fill_value=False)

    aroon_up = _rolling_argmax_position(high, 14) / 14.0 * 100.0
    aroon_down = _rolling_argmin_position(low, 14) / 14.0 * 100.0

    stoch_low = low.rolling(14, min_periods=14).min()
    stoch_high = high.rolling(14, min_periods=14).max()
    stoch_raw = 100.0 * (close - stoch_low) / (stoch_high - stoch_low).replace(0.0, np.nan)
    stoch_k = stoch_raw.rolling(3, min_periods=3).mean()
    stoch_d = stoch_k.rolling(3, min_periods=3).mean()

    events = pd.DataFrame(
        {
            "timestamp": pdf["timestamp"],
            "signal_source_tf": tf,
            "signal_bar_open_ts": pdf["timestamp"],
            "signal_available_ts": pdf["timestamp"] + pd.to_timedelta(minutes, unit="m"),
            "signal_valid_until_ts": pdf["timestamp"] + pd.to_timedelta(minutes * 2, unit="m"),
            "signal_valid_rows": minutes,
            "signal_params_hash": PARAMS_HASH,
            f"ind_{tf}_adx": adx,
            f"ind_{tf}_plus_di": plus_di,
            f"ind_{tf}_minus_di": minus_di,
            f"ind_{tf}_rsi": rsi,
            f"ind_{tf}_macd_hist": macd_hist,
            f"ind_{tf}_vwap": vwap,
            f"ind_{tf}_donchian_upper_prev": donchian_upper_prev,
            f"ind_{tf}_donchian_lower_prev": donchian_lower_prev,
            f"ind_{tf}_obv": obv,
            f"ind_{tf}_obv_ma": obv_ma,
            f"ind_{tf}_bb_upper": bb_upper,
            f"ind_{tf}_bb_lower": bb_lower,
            f"ind_{tf}_pivot": pivot,
            f"ind_{tf}_pivot_r1": pivot_r1,
            f"ind_{tf}_pivot_s1": pivot_s1,
            f"ind_{tf}_supertrend_direction": supertrend_dir,
            f"ind_{tf}_aroon_up": aroon_up,
            f"ind_{tf}_aroon_down": aroon_down,
            f"ind_{tf}_stoch_k": stoch_k,
            f"ind_{tf}_stoch_d": stoch_d,
            f"{prefix}adx_dmi_trend_long": _bool_flag((plus_di > minus_di) & (adx > 25.0) & (adx.diff() > 0)),
            f"{prefix}adx_dmi_trend_short": _bool_flag((minus_di > plus_di) & (adx > 25.0) & (adx.diff() > 0)),
            f"{prefix}adx_dmi_trend_state": _bool_flag(adx >= 25.0),
            f"{prefix}adx_dmi_range_state": _bool_flag(adx <= 20.0),
            f"{prefix}rsi_reentry_long": _bool_flag((rsi.shift(1) < 30.0) & (rsi >= 30.0)),
            f"{prefix}rsi_reentry_short": _bool_flag((rsi.shift(1) > 70.0) & (rsi <= 70.0)),
            f"{prefix}rsi_oversold_state": _bool_flag(rsi < 30.0),
            f"{prefix}rsi_overbought_state": _bool_flag(rsi > 70.0),
            f"{prefix}macd_hist_cross_long": _bool_flag((macd_hist > 0) & (macd_hist.shift(1) <= 0)),
            f"{prefix}macd_hist_cross_short": _bool_flag((macd_hist < 0) & (macd_hist.shift(1) >= 0)),
            f"{prefix}macd_bullish_state": _bool_flag(macd_hist > 0),
            f"{prefix}vwap_cross_long": _bool_flag((close > vwap) & (close.shift(1) <= vwap.shift(1))),
            f"{prefix}vwap_cross_short": _bool_flag((close < vwap) & (close.shift(1) >= vwap.shift(1))),
            f"{prefix}vwap_above_state": _bool_flag(close > vwap),
            f"{prefix}donchian_breakout_long": _bool_flag(close > donchian_upper_prev),
            f"{prefix}donchian_breakout_short": _bool_flag(close < donchian_lower_prev),
            f"{prefix}obv_ma_cross_long": _bool_flag((obv > obv_ma) & (obv.shift(1) <= obv_ma.shift(1))),
            f"{prefix}obv_ma_cross_short": _bool_flag((obv < obv_ma) & (obv.shift(1) >= obv_ma.shift(1))),
            f"{prefix}obv_above_ma_state": _bool_flag(obv > obv_ma),
            f"{prefix}bollinger_reentry_long": _bool_flag((close.shift(1) < bb_lower.shift(1)) & (close >= bb_lower)),
            f"{prefix}bollinger_reentry_short": _bool_flag((close.shift(1) > bb_upper.shift(1)) & (close <= bb_upper)),
            f"{prefix}bollinger_squeeze_state": _bool_flag(bb_squeeze),
            f"{prefix}bollinger_squeeze_breakout_long": _bool_flag(bb_squeeze.shift(1).eq(True) & (close > bb_upper)),
            f"{prefix}bollinger_squeeze_breakout_short": _bool_flag(bb_squeeze.shift(1).eq(True) & (close < bb_lower)),
            f"{prefix}pivot_r1_break_long": _bool_flag((close > pivot_r1) & (close.shift(1) <= pivot_r1.shift(1))),
            f"{prefix}pivot_s1_break_short": _bool_flag((close < pivot_s1) & (close.shift(1) >= pivot_s1.shift(1))),
            f"{prefix}pivot_above_state": _bool_flag(close > pivot),
            f"{prefix}supertrend_flip_long": _bool_flag(supertrend_ready & supertrend_prev_ready & (supertrend_dir > 0) & (supertrend_dir.shift(1) < 0)),
            f"{prefix}supertrend_flip_short": _bool_flag(supertrend_ready & supertrend_prev_ready & (supertrend_dir < 0) & (supertrend_dir.shift(1) > 0)),
            f"{prefix}supertrend_long_state": _bool_flag(supertrend_ready & (supertrend_dir > 0)),
            f"{prefix}supertrend_short_state": _bool_flag(supertrend_ready & (supertrend_dir < 0)),
            f"{prefix}aroon_cross_long": _bool_flag((aroon_up > aroon_down) & (aroon_up.shift(1) <= aroon_down.shift(1)) & (aroon_up > 50.0)),
            f"{prefix}aroon_cross_short": _bool_flag((aroon_down > aroon_up) & (aroon_down.shift(1) <= aroon_up.shift(1)) & (aroon_down > 50.0)),
            f"{prefix}aroon_uptrend_state": _bool_flag((aroon_up > 50.0) & (aroon_down < 50.0)),
            f"{prefix}aroon_downtrend_state": _bool_flag((aroon_down > 50.0) & (aroon_up < 50.0)),
            f"{prefix}stoch_cross_long": _bool_flag((stoch_k > stoch_d) & (stoch_k.shift(1) <= stoch_d.shift(1)) & (stoch_k < 20.0)),
            f"{prefix}stoch_cross_short": _bool_flag((stoch_k < stoch_d) & (stoch_k.shift(1) >= stoch_d.shift(1)) & (stoch_k > 80.0)),
            f"{prefix}stoch_oversold_state": _bool_flag(stoch_k < 20.0),
            f"{prefix}stoch_overbought_state": _bool_flag(stoch_k > 80.0),
        }
    )
    return pl.from_pandas(events).with_columns(
        [
            pl.col("timestamp").cast(pl.Datetime("us", "UTC")),
            pl.col("signal_bar_open_ts").cast(pl.Datetime("us", "UTC")),
            pl.col("signal_available_ts").cast(pl.Datetime("us", "UTC")),
            pl.col("signal_valid_until_ts").cast(pl.Datetime("us", "UTC")),
        ]
    )


def _timestamp_us(df: pl.DataFrame, column: str = "timestamp") -> np.ndarray:
    return (
        df.select(pl.col(column).dt.timestamp("us").alias(column))
        .to_series()
        .to_numpy()
    )


def _apply_canonical_valid_until(
    events: pl.DataFrame,
    canonical_1m: pl.DataFrame,
    timeframe: str,
) -> pl.DataFrame:
    """Set valid-until timestamps from the actual canonical 1m expansion grid.

    For crypto this is the same as wall-clock `available + timeframe`. For
    session assets it skips closed rows because canonical 1m has no closed
    session timestamps.
    """
    if events.is_empty() or canonical_1m.is_empty():
        return events
    minutes = timeframe_minutes(timeframe)
    one_minute = canonical_1m.select("timestamp").sort("timestamp")
    one_ts = _timestamp_us(one_minute)
    avail = _timestamp_us(events, "signal_available_ts")
    starts = np.searchsorted(one_ts, avail, side="left")
    until_us: list[int | None] = []
    for start in starts:
        if start >= len(one_ts):
            until_us.append(None)
            continue
        end = int(start) + minutes
        if end < len(one_ts):
            until_us.append(int(one_ts[end]))
        else:
            last_active_idx = len(one_ts) - 1
            until_us.append(int(one_ts[last_active_idx] + 60_000_000))
    return events.with_columns(
        pl.Series("signal_valid_until_ts", until_us).cast(pl.Datetime("us", "UTC"))
    )


def expand_events_to_1m(
    events: pl.DataFrame,
    canonical_1m: pl.DataFrame,
    timeframe: str,
) -> pl.DataFrame:
    """Expand closed-bar TA events onto future 1m canonical rows only."""
    tf = normalize_canonical_timeframe(timeframe)
    minutes = timeframe_minutes(tf)
    one_minute = canonical_1m.select("timestamp").sort("timestamp")
    n_rows = len(one_minute)
    flag_cols = ta_flag_columns(events.columns, tf)
    if n_rows == 0:
        return pl.DataFrame({"timestamp": []})

    out = one_minute
    if not flag_cols or events.is_empty():
        return out.with_columns([pl.lit(0).cast(pl.Int8).alias(col) for col in flag_cols])

    one_ts = _timestamp_us(one_minute)
    avail = _timestamp_us(events, "signal_available_ts")
    starts = np.searchsorted(one_ts, avail, side="left")
    ends = np.minimum(starts + minutes, n_rows)
    valid = starts < n_rows
    columns: list[pl.Series] = []
    for col in flag_cols:
        values = events[col].fill_null(0).cast(pl.Int8).to_numpy()
        active = valid & (values > 0)
        diff = np.zeros(n_rows + 1, dtype=np.int32)
        if np.any(active):
            np.add.at(diff, starts[active], 1)
            np.add.at(diff, ends[active], -1)
        expanded = (np.cumsum(diff[:-1]) > 0).astype(np.int8)
        columns.append(pl.Series(col, expanded, dtype=pl.Int8))
    return out.with_columns(columns)


def materialize_one(
    *,
    project_root: Path,
    asset_id: str,
    timeframe: str,
    dry_run: bool = False,
) -> MaterializeTAResult:
    """Compute and write TA events plus expanded 1m flags for one asset/timeframe."""
    asset_id = get_htf_asset_spec(asset_id).asset_id
    tf = normalize_canonical_timeframe(timeframe)
    source_path = canonical_ohlcv_path(project_root, asset_id, tf)
    source_1m_path = canonical_ohlcv_path(project_root, asset_id, "1m")
    events_path = ta_events_path(project_root, asset_id, tf)
    flags_path = ta_flags_path(project_root, asset_id, tf)
    meta_path = ta_meta_path(project_root, asset_id, tf)
    if not source_path.exists():
        return MaterializeTAResult(
            asset_id,
            tf,
            source_path,
            source_1m_path,
            events_path,
            flags_path,
            meta_path,
            "missing_source_tf",
            detail=f"Missing canonical source: {source_path}",
        )
    if not source_1m_path.exists():
        return MaterializeTAResult(
            asset_id,
            tf,
            source_path,
            source_1m_path,
            events_path,
            flags_path,
            meta_path,
            "missing_source_1m",
            detail=f"Missing canonical 1m source: {source_1m_path}",
        )
    if dry_run:
        return status_one(project_root, asset_id, tf, dry_run=True)

    htf_df = pl.read_parquet(source_path)
    canonical_1m = pl.read_parquet(source_1m_path, columns=["timestamp"])
    events = compute_ta_events(htf_df, tf)
    events = _apply_canonical_valid_until(events, canonical_1m, tf)
    flags = expand_events_to_1m(events, canonical_1m, tf)
    flag_cols = ta_flag_columns(flags.columns, tf)

    flags_path.parent.mkdir(parents=True, exist_ok=True)
    events.write_parquet(events_path)
    flags.write_parquet(flags_path)
    null_flag_count = (
        int(
            sum(
                flags.select(
                    [pl.col(col).is_null().sum().alias(col) for col in flag_cols]
                ).row(0)
            )
        )
        if flag_cols
        else 0
    )
    payload = {
        "asset_id": asset_id,
        "timeframe": tf,
        "source_path": source_path,
        "source_1m_path": source_1m_path,
        "events_path": events_path,
        "flags_path": flags_path,
        "meta_path": meta_path,
        "indicator_params": INDICATOR_PARAMS,
        "signal_params_hash": PARAMS_HASH,
        "signal_timing": "post_close",
        "expansion": "next_timeframe_minutes_over_canonical_1m_market_open_rows",
        "event_rows": len(events),
        "flag_rows": len(flags),
        "flag_columns": flag_cols,
        "flag_columns_count": len(flag_cols),
        "source_min_ts": htf_df["timestamp"].min() if len(htf_df) else None,
        "source_max_ts": htf_df["timestamp"].max() if len(htf_df) else None,
        "flags_min_ts": flags["timestamp"].min() if len(flags) else None,
        "flags_max_ts": flags["timestamp"].max() if len(flags) else None,
        "null_flag_count": null_flag_count,
    }
    meta_path.write_text(json.dumps(payload, indent=2, default=_json_default) + "\n")
    return MaterializeTAResult(
        asset_id=asset_id,
        timeframe=tf,
        source_path=source_path,
        source_1m_path=source_1m_path,
        events_path=events_path,
        flags_path=flags_path,
        meta_path=meta_path,
        status="written",
        event_rows=len(events),
        flag_rows=len(flags),
        flag_columns=len(flag_cols),
        min_ts=flags["timestamp"].min() if len(flags) else None,
        max_ts=flags["timestamp"].max() if len(flags) else None,
    )


def status_one(
    project_root: Path,
    asset_id: str,
    timeframe: str,
    *,
    dry_run: bool = False,
) -> MaterializeTAResult:
    """Return current status for one TA flag output."""
    asset_id = get_htf_asset_spec(asset_id).asset_id
    tf = normalize_canonical_timeframe(timeframe)
    source_path = canonical_ohlcv_path(project_root, asset_id, tf)
    source_1m_path = canonical_ohlcv_path(project_root, asset_id, "1m")
    events_path = ta_events_path(project_root, asset_id, tf)
    flags_path = ta_flags_path(project_root, asset_id, tf)
    meta_path = ta_meta_path(project_root, asset_id, tf)
    if not source_path.exists():
        return MaterializeTAResult(asset_id, tf, source_path, source_1m_path, events_path, flags_path, meta_path, "missing_source_tf")
    if not source_1m_path.exists():
        return MaterializeTAResult(asset_id, tf, source_path, source_1m_path, events_path, flags_path, meta_path, "missing_source_1m")
    if dry_run:
        status = "would_write" if flags_path.exists() else "would_create"
        rows, min_ts, max_ts, flag_cols = _scan_flags(flags_path)
        return MaterializeTAResult(asset_id, tf, source_path, source_1m_path, events_path, flags_path, meta_path, status, flag_rows=rows, flag_columns=flag_cols, min_ts=min_ts, max_ts=max_ts)
    if not events_path.exists() or not flags_path.exists():
        return MaterializeTAResult(asset_id, tf, source_path, source_1m_path, events_path, flags_path, meta_path, "missing_output")
    rows, min_ts, max_ts, flag_cols = _scan_flags(flags_path)
    return MaterializeTAResult(asset_id, tf, source_path, source_1m_path, events_path, flags_path, meta_path, "ok" if rows else "empty_output", flag_rows=rows, flag_columns=flag_cols, min_ts=min_ts, max_ts=max_ts)


def _scan_flags(path: Path) -> tuple[int, datetime | None, datetime | None, int]:
    if not path.exists():
        return 0, None, None, 0
    schema = pl.scan_parquet(path).collect_schema().names()
    flag_cols = len(ta_flag_columns(schema))
    stats = (
        pl.scan_parquet(path)
        .select(
            pl.len().alias("rows"),
            pl.col("timestamp").min().alias("min_ts"),
            pl.col("timestamp").max().alias("max_ts"),
        )
        .collect()
        .row(0, named=True)
    )
    return int(stats["rows"]), stats["min_ts"], stats["max_ts"], flag_cols


def _asset_ids(raw: str) -> tuple[str, ...]:
    return CORE_HTF_ASSET_IDS if raw.strip().lower() == "core" else htf_asset_ids_from_csv(raw)


def print_results(results: list[MaterializeTAResult]) -> None:
    """Print a compact status table."""
    print("| Asset | TF | Status | Flag Rows | Flags | Range UTC |")
    print("|---|---:|---|---:|---:|---|")
    for result in results:
        if result.min_ts is not None and result.max_ts is not None:
            rng = f"{result.min_ts} -> {result.max_ts}"
        else:
            rng = result.detail or "-"
        print(
            f"| {result.asset_id} | {result.timeframe} | {result.status} | "
            f"{result.flag_rows} | {result.flag_columns} | {rng} |"
        )


def build_arg_parser() -> argparse.ArgumentParser:
    """Create CLI parser for TA flag materialization."""
    parser = argparse.ArgumentParser(
        description="Materialize leakage-safe TA signal flags from canonical OHLCV bars.",
    )
    parser.add_argument("--assets", default="core", help="core or comma-separated asset ids")
    parser.add_argument(
        "--timeframes",
        default=",".join(DEFAULT_TA_TIMEFRAMES),
        help="Comma-separated canonical timeframes, e.g. 15m,1h,4h,8h,12h,1d",
    )
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--status", action="store_true", help="Report output status without writing")
    parser.add_argument("--dry-run", action="store_true", help="Preview write targets without writing")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run status, dry-run, or materialization for selected assets/timeframes."""
    args = build_arg_parser().parse_args(argv)
    project_root = Path(args.project_root).resolve() if args.project_root else project_root_from_cwd()
    assets = _asset_ids(args.assets)
    timeframes = parse_ta_timeframes(args.timeframes)
    results: list[MaterializeTAResult] = []
    for asset_id in assets:
        for timeframe in timeframes:
            if args.status:
                results.append(status_one(project_root, asset_id, timeframe))
            else:
                results.append(
                    materialize_one(
                        project_root=project_root,
                        asset_id=asset_id,
                        timeframe=timeframe,
                        dry_run=bool(args.dry_run),
                    )
                )
    print_results(results)
    bad_statuses = {"missing_source_tf", "missing_source_1m", "missing_output", "empty_output"}
    if args.status and any(result.status in bad_statuses for result in results):
        return 1
    if any(result.status.startswith("missing_source") for result in results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
