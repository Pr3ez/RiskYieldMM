"""Calendar-aware canonical OHLCV preparation for HTF materialization.

Workflow position:
- called before HTF combined batches are assigned;
- receives already fetched provider OHLCV rows;
- returns a canonical market-open grid plus explicit session/fill metadata.

Temporal/data contract:
- raw provider files are not modified;
- crypto uses every minute between first and latest timestamp;
- session assets infer open segments from local parquet timestamps;
- small open-session gaps are synthetic zero-volume carry-forward bars;
- closed sessions, maintenance breaks, and weekends are not filled.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import polars as pl

CALENDAR_CRYPTO_24_7 = "crypto_24_7"
CALENDAR_FUTURES_SESSION_OBSERVED = "futures_session_observed"

CANONICAL_BAR_COLUMNS = [
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "asset_id",
    "calendar_id",
    "is_market_open",
    "is_synthetic_no_trade",
    "is_open_session_gap_fill",
    "minutes_since_prev_real_bar",
    "session_id",
    "session_date",
    "session_bar_pos",
    "session_minutes_to_close",
    "is_session_open_bar",
    "is_session_close_bar",
    "is_weekly_open_bar",
    "is_weekly_close_bar",
]

CANONICAL_DERIVED_TIMEFRAMES = ("15m", "1h", "4h", "8h", "12h", "1d")
CANONICAL_TIMEFRAME_ALIASES = {"24h": "1d"}
_CANONICAL_TIMEFRAME_MINUTES = {
    "1m": 1,
    "15m": 15,
    "1h": 60,
    "4h": 240,
    "8h": 480,
    "12h": 720,
    "1d": 1440,
}


@dataclass(frozen=True)
class CanonicalizationSummary:
    """Small metadata payload written beside canonicalized HTF bars."""

    asset_id: str
    calendar_id: str
    timeframe: str
    raw_rows: int
    canonical_rows: int
    synthetic_rows: int
    session_count: int
    min_ts: datetime | None
    max_ts: datetime | None

    def as_dict(self) -> dict[str, Any]:
        """Return JSON-serializable summary metadata for artifact sidecars."""
        return {
            "asset_id": self.asset_id,
            "calendar_id": self.calendar_id,
            "timeframe": self.timeframe,
            "raw_rows": int(self.raw_rows),
            "canonical_rows": int(self.canonical_rows),
            "synthetic_rows": int(self.synthetic_rows),
            "session_count": int(self.session_count),
            "min_ts": self.min_ts,
            "max_ts": self.max_ts,
        }


def timeframe_minutes(tf: str) -> int:
    """Parse a supported canonical timeframe into minutes."""
    normalized = normalize_canonical_timeframe(tf)
    value = _CANONICAL_TIMEFRAME_MINUTES[normalized]
    if value <= 0:
        raise ValueError(f"Timeframe minutes must be positive: {tf!r}")
    return value


def normalize_canonical_timeframe(tf: str) -> str:
    """Return the canonical on-disk timeframe id, accepting documented aliases."""
    normalized = tf.strip().lower()
    normalized = CANONICAL_TIMEFRAME_ALIASES.get(normalized, normalized)
    if normalized not in _CANONICAL_TIMEFRAME_MINUTES:
        allowed = ", ".join((*CANONICAL_DERIVED_TIMEFRAMES, "24h"))
        raise ValueError(f"Unsupported canonical timeframe {tf!r}. Allowed: {allowed}")
    return normalized


def _session_break_threshold_minutes(tf_minutes: int) -> int:
    # One missing 15m bar creates a 30-minute delta and should be fillable.
    # The observed daily maintenance breaks are materially larger.
    return max(45, tf_minutes * 3)


def _normalize_raw_ohlcv(df: pl.DataFrame) -> pl.DataFrame:
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Raw OHLCV frame is missing required columns: {missing}")

    return (
        df.select(
            [
                pl.col("timestamp")
                .dt.replace_time_zone(None)
                .cast(pl.Datetime("us"))
                .alias("timestamp"),
                pl.col("open").cast(pl.Float64),
                pl.col("high").cast(pl.Float64),
                pl.col("low").cast(pl.Float64),
                pl.col("close").cast(pl.Float64),
                pl.col("volume").cast(pl.Float64),
            ]
        )
        .sort("timestamp")
        .unique(subset=["timestamp"], keep="last", maintain_order=True)
    )


def _observed_segments(
    raw: pl.DataFrame,
    *,
    calendar_id: str,
    tf_minutes: int,
) -> pl.DataFrame:
    if raw.is_empty():
        return pl.DataFrame(
            schema={
                "timestamp": pl.Datetime("us"),
                "session_id_num": pl.Int64,
            }
        )

    threshold = _session_break_threshold_minutes(tf_minutes)
    if calendar_id == CALENDAR_CRYPTO_24_7:
        return raw.select(
            [
                "timestamp",
                pl.lit(1).cast(pl.Int64).alias("session_id_num"),
            ]
        )

    return (
        raw.select("timestamp")
        .sort("timestamp")
        .with_columns(
            (pl.col("timestamp").diff().dt.total_minutes().fill_null(0) > threshold)
            .cast(pl.Int64)
            .alias("_new_segment")
        )
        .with_columns(pl.col("_new_segment").cum_sum().alias("session_id_num"))
        .drop("_new_segment")
    )


def _expected_timestamps(
    raw: pl.DataFrame,
    *,
    calendar_id: str,
    tf_minutes: int,
) -> pl.DataFrame:
    segments = _observed_segments(
        raw,
        calendar_id=calendar_id,
        tf_minutes=tf_minutes,
    )
    if segments.is_empty():
        return pl.DataFrame(
            schema={
                "timestamp": pl.Datetime("us"),
                "session_id_num": pl.Int64,
            }
        )

    if calendar_id == CALENDAR_CRYPTO_24_7:
        start = raw["timestamp"].min()
        end = raw["timestamp"].max()
        if start is None or end is None:
            return segments
        return pl.DataFrame(
            {
                "timestamp": pl.datetime_range(
                    start,
                    end,
                    interval=f"{tf_minutes}m",
                    eager=True,
                ),
                "session_id_num": 1,
            }
        )

    expected_parts: list[pl.DataFrame] = []
    bounds = (
        segments.group_by("session_id_num")
        .agg(
            [
                pl.col("timestamp").min().alias("start"),
                pl.col("timestamp").max().alias("end"),
            ]
        )
        .sort("session_id_num")
    )
    for row in bounds.iter_rows(named=True):
        start = row["start"]
        end = row["end"]
        session_id_num = int(row["session_id_num"])
        expected_parts.append(
            pl.DataFrame(
                {
                    "timestamp": pl.datetime_range(
                        start,
                        end,
                        interval=f"{tf_minutes}m",
                        eager=True,
                    ),
                    "session_id_num": session_id_num,
                }
            )
        )

    return pl.concat(expected_parts, how="vertical") if expected_parts else segments


def canonicalize_ohlcv(
    df: pl.DataFrame,
    *,
    asset_id: str,
    calendar_id: str,
    timeframe: str,
) -> tuple[pl.DataFrame, CanonicalizationSummary]:
    """Return canonical OHLCV rows and explicit calendar/fill metadata.

    Raw rows are not changed in place. For session assets, gaps larger than the
    observed break threshold split sessions and are not filled. Smaller missing
    open-session timestamps are carry-forward synthetic no-trade bars.
    """

    tf_minutes = timeframe_minutes(timeframe)
    raw = _normalize_raw_ohlcv(df)
    raw_rows = len(raw)
    if raw.is_empty():
        empty = pl.DataFrame(schema=dict.fromkeys(CANONICAL_BAR_COLUMNS, pl.Null))
        return empty, CanonicalizationSummary(
            asset_id=asset_id,
            calendar_id=calendar_id,
            timeframe=timeframe,
            raw_rows=0,
            canonical_rows=0,
            synthetic_rows=0,
            session_count=0,
            min_ts=None,
            max_ts=None,
        )

    expected = _expected_timestamps(
        raw,
        calendar_id=calendar_id,
        tf_minutes=tf_minutes,
    )
    canonical = (
        expected.join(
            raw.with_columns(pl.lit(True).alias("_has_real_bar")),
            on="timestamp",
            how="left",
        )
        .sort(["session_id_num", "timestamp"])
        .with_columns(
            [
                pl.col("_has_real_bar").fill_null(False).alias("_has_real_bar"),
                pl.col("close").forward_fill().alias("_carry_close"),
            ]
        )
        .filter(pl.col("_carry_close").is_not_null())
        .with_columns(
            [
                pl.when(pl.col("_has_real_bar"))
                .then(pl.col("open"))
                .otherwise(pl.col("_carry_close"))
                .cast(pl.Float64)
                .alias("open"),
                pl.when(pl.col("_has_real_bar"))
                .then(pl.col("high"))
                .otherwise(pl.col("_carry_close"))
                .cast(pl.Float64)
                .alias("high"),
                pl.when(pl.col("_has_real_bar"))
                .then(pl.col("low"))
                .otherwise(pl.col("_carry_close"))
                .cast(pl.Float64)
                .alias("low"),
                pl.col("_carry_close").cast(pl.Float64).alias("close"),
                pl.when(pl.col("_has_real_bar"))
                .then(pl.col("volume"))
                .otherwise(pl.lit(0.0))
                .fill_null(0.0)
                .cast(pl.Float64)
                .alias("volume"),
            ]
        )
        .with_columns(
            [
                (~pl.col("_has_real_bar")).alias("is_synthetic_no_trade"),
                (~pl.col("_has_real_bar")).alias("is_open_session_gap_fill"),
                pl.lit(True).alias("is_market_open"),
            ]
        )
    )

    real_times = raw.select(
        [
            pl.col("timestamp").alias("_prev_real_ts"),
            pl.col("timestamp").alias("timestamp"),
        ]
    )
    canonical = canonical.join_asof(
        real_times,
        on="timestamp",
        strategy="backward",
    ).with_columns(
        (pl.col("timestamp") - pl.col("_prev_real_ts"))
        .dt.total_minutes()
        .fill_null(0)
        .cast(pl.Int32)
        .alias("minutes_since_prev_real_bar")
    )

    canonical = canonical.with_columns(
        [
            pl.col("session_id_num").cast(pl.Int64),
            pl.col("timestamp").dt.date().cast(pl.Utf8).alias("session_date"),
            pl.concat_str(
                [
                    pl.lit(asset_id),
                    pl.lit("_"),
                    pl.col("session_id_num").cast(pl.Utf8),
                ]
            ).alias("session_id"),
            pl.col("timestamp")
            .rank("ordinal")
            .over("session_id_num")
            .sub(1)
            .cast(pl.Int32)
            .alias("session_bar_pos"),
        ]
    )
    canonical = canonical.with_columns(
        (pl.col("timestamp").max().over("session_id_num") - pl.col("timestamp"))
        .dt.total_minutes()
        .cast(pl.Int32)
        .alias("session_minutes_to_close")
    )
    canonical = canonical.with_columns(
        [
            pl.col("timestamp")
            .dt.replace_time_zone("UTC")
            .cast(pl.Datetime("us", "UTC"))
            .alias("timestamp"),
            (pl.col("session_bar_pos") == 0).alias("is_session_open_bar"),
            (pl.col("session_minutes_to_close") == 0).alias("is_session_close_bar"),
            (
                (pl.col("session_bar_pos") == 0)
                & (
                    pl.col("timestamp").diff().dt.total_minutes().fill_null(10_000)
                    > 24 * 60
                )
            ).alias("is_weekly_open_bar"),
            (
                (pl.col("session_minutes_to_close") == 0)
                & (
                    pl.col("timestamp")
                    .shift(-1)
                    .sub(pl.col("timestamp"))
                    .dt.total_minutes()
                    .fill_null(10_000)
                    > 24 * 60
                )
            ).alias("is_weekly_close_bar"),
            pl.lit(asset_id).alias("asset_id"),
            pl.lit(calendar_id).alias("calendar_id"),
        ]
    )

    canonical = canonical.select(CANONICAL_BAR_COLUMNS).sort("timestamp")
    synthetic_rows = int(canonical["is_open_session_gap_fill"].sum())
    session_count = int(canonical["session_id"].n_unique())
    summary = CanonicalizationSummary(
        asset_id=asset_id,
        calendar_id=calendar_id,
        timeframe=timeframe,
        raw_rows=raw_rows,
        canonical_rows=len(canonical),
        synthetic_rows=synthetic_rows,
        session_count=session_count,
        min_ts=canonical["timestamp"].min(),
        max_ts=canonical["timestamp"].max(),
    )
    return canonical, summary


def _bucket_start_expr(tf: str) -> pl.Expr:
    minutes = timeframe_minutes(tf)
    if minutes == 1440:
        return pl.col("timestamp").dt.truncate("1d")
    return pl.col("timestamp").dt.truncate(f"{minutes}m")


def _utc_bucket_end_expr(tf: str) -> pl.Expr:
    minutes = timeframe_minutes(tf)
    return pl.col("_bucket").dt.replace_time_zone(None) + pl.duration(minutes=minutes)


def _historical_session_close_minutes(df_1m: pl.DataFrame) -> set[int]:
    """Return repeated observed close minutes used to recognize real session tails."""
    if df_1m.is_empty() or "is_session_close_bar" not in df_1m.columns:
        return set()
    close_counts = (
        df_1m.filter(pl.col("is_session_close_bar"))
        .select(
            (
                pl.col("timestamp").dt.hour().cast(pl.Int32) * 60
                + pl.col("timestamp").dt.minute().cast(pl.Int32)
            ).alias("_close_minute")
        )
        .group_by("_close_minute")
        .len()
    )
    return {
        int(row["_close_minute"])
        for row in close_counts.iter_rows(named=True)
        if int(row["len"]) >= 2
    }


def aggregate_canonical_ohlcv(
    df_1m: pl.DataFrame,
    *,
    target_timeframe: str,
    drop_incomplete: bool = True,
) -> tuple[pl.DataFrame, dict[str, Any]]:
    """Aggregate canonical 1m bars into a higher canonical OHLCV timeframe.

    Crypto bars require full wall-clock coverage. Session assets keep buckets
    that are complete by the observed market-open calendar, so maintenance
    breaks and weekend closures are not filled or counted as missing rows.
    """

    target_timeframe = normalize_canonical_timeframe(target_timeframe)

    if df_1m.is_empty():
        return df_1m, {
            "target_timeframe": target_timeframe,
            "source_rows": 0,
            "output_rows": 0,
            "dropped_incomplete_buckets": 0,
            "target_minutes": timeframe_minutes(target_timeframe),
        }

    missing = sorted(set(CANONICAL_BAR_COLUMNS) - set(df_1m.columns))
    if missing:
        raise ValueError(f"Canonical 1m frame is missing required columns: {missing}")

    target_minutes = timeframe_minutes(target_timeframe)
    calendar_id = str(df_1m["calendar_id"].drop_nulls().to_list()[0])
    is_crypto = calendar_id == CALENDAR_CRYPTO_24_7
    close_minutes = _historical_session_close_minutes(df_1m)
    source_max_ts = df_1m["timestamp"].max()
    if source_max_ts is not None and source_max_ts.tzinfo is not None:
        source_max_ts = source_max_ts.replace(tzinfo=None)

    grouped = (
        df_1m.with_columns(_bucket_start_expr(target_timeframe).alias("_bucket"))
        .group_by("_bucket")
        .agg(
            [
                pl.col("open").sort_by("timestamp").first().alias("open"),
                pl.col("high").max().alias("high"),
                pl.col("low").min().alias("low"),
                pl.col("close").sort_by("timestamp").last().alias("close"),
                pl.col("volume").sum().alias("volume"),
                pl.col("asset_id").first().alias("asset_id"),
                pl.col("calendar_id").first().alias("calendar_id"),
                pl.col("is_market_open").any().alias("is_market_open"),
                pl.col("is_synthetic_no_trade").all().alias("is_synthetic_no_trade"),
                pl.col("is_open_session_gap_fill")
                .any()
                .alias("is_open_session_gap_fill"),
                pl.col("minutes_since_prev_real_bar")
                .max()
                .alias("minutes_since_prev_real_bar"),
                pl.col("session_id").first().alias("session_id"),
                pl.col("session_date").first().alias("session_date"),
                pl.col("session_bar_pos").min().alias("session_bar_pos"),
                pl.col("session_minutes_to_close")
                .min()
                .alias("session_minutes_to_close"),
                pl.col("is_session_open_bar").any().alias("is_session_open_bar"),
                pl.col("is_session_close_bar").any().alias("is_session_close_bar"),
                pl.col("is_weekly_open_bar").any().alias("is_weekly_open_bar"),
                pl.col("is_weekly_close_bar").any().alias("is_weekly_close_bar"),
                pl.len().alias("_source_row_count"),
                pl.col("timestamp").max().alias("_bucket_max_ts"),
            ]
        )
        .sort("_bucket")
    )

    grouped = grouped.with_columns(
        [
            _utc_bucket_end_expr(target_timeframe).alias("_bucket_end"),
            (
                pl.col("_bucket_max_ts").dt.hour().cast(pl.Int32) * 60
                + pl.col("_bucket_max_ts").dt.minute().cast(pl.Int32)
            ).alias("_bucket_max_minute"),
        ]
    )
    complete_expr = pl.col("_source_row_count") == target_minutes
    if not is_crypto:
        source_seen_through_bucket = pl.col("_bucket_end") <= pl.lit(
            source_max_ts + timedelta(minutes=1)
        )
        real_observed_close = pl.col("is_session_close_bar") & pl.col(
            "_bucket_max_minute"
        ).is_in(sorted(close_minutes))
        complete_expr = complete_expr | source_seen_through_bucket | real_observed_close
    grouped = grouped.with_columns(complete_expr.alias("_is_complete_bucket"))
    dropped_incomplete = (
        int((~grouped["_is_complete_bucket"]).sum()) if drop_incomplete else 0
    )
    if drop_incomplete:
        grouped = grouped.filter(pl.col("_is_complete_bucket"))

    out = (
        grouped.rename({"_bucket": "timestamp"})
        .select(CANONICAL_BAR_COLUMNS)
        .sort("timestamp")
    )
    metadata = {
        "target_timeframe": target_timeframe,
        "target_minutes": target_minutes,
        "source_rows": int(len(df_1m)),
        "output_rows": int(len(out)),
        "dropped_incomplete_buckets": dropped_incomplete,
        "calendar_id": calendar_id,
        "aggregation_anchor": "UTC",
        "first_timestamp": out["timestamp"].min() if len(out) else None,
        "last_timestamp": out["timestamp"].max() if len(out) else None,
        "synthetic_rows": int(out["is_synthetic_no_trade"].sum()) if len(out) else 0,
        "gap_fill_rows": int(out["is_open_session_gap_fill"].sum()) if len(out) else 0,
    }
    return out, metadata


def aggregate_canonical_15m(df_1m: pl.DataFrame) -> pl.DataFrame:
    """Backward-compatible wrapper for canonical 1m -> canonical 15m."""
    out, _ = aggregate_canonical_ohlcv(df_1m, target_timeframe="15m")
    return out
