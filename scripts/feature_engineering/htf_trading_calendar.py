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
from datetime import datetime
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
    """Parse a minute timeframe string such as `1m` or `15m`."""
    if not tf.endswith("m"):
        raise ValueError(f"Only minute timeframes are supported here: {tf!r}")
    value = int(tf[:-1])
    if value <= 0:
        raise ValueError(f"Timeframe minutes must be positive: {tf!r}")
    return value


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
            (
                pl.col("timestamp").diff().dt.total_minutes().fill_null(0)
                > threshold
            )
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
        empty = pl.DataFrame(schema={col: pl.Null for col in CANONICAL_BAR_COLUMNS})
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
    canonical = (
        canonical.join_asof(
            real_times,
            on="timestamp",
            strategy="backward",
        )
        .with_columns(
            (pl.col("timestamp") - pl.col("_prev_real_ts"))
            .dt.total_minutes()
            .fill_null(0)
            .cast(pl.Int32)
            .alias("minutes_since_prev_real_bar")
        )
    )

    canonical = canonical.with_columns(
        [
            pl.col("session_id_num").cast(pl.Int64),
            pl.col("timestamp")
            .dt.date()
            .cast(pl.Utf8)
            .alias("session_date"),
            pl.concat_str(
                [
                    pl.lit(asset_id),
                    pl.lit("_"),
                    pl.col("session_id_num").cast(pl.Utf8),
                ]
            ).alias("session_id"),
            pl.col("timestamp").rank("ordinal").over("session_id_num")
            .sub(1)
            .cast(pl.Int32)
            .alias("session_bar_pos"),
        ]
    )
    canonical = canonical.with_columns(
        (
            pl.col("timestamp").max().over("session_id_num") - pl.col("timestamp")
        )
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


def aggregate_canonical_15m(df_1m: pl.DataFrame) -> pl.DataFrame:
    """Aggregate canonical 1m bars into canonical 15m bars.

    This helper is used by tests and future materialization paths. The current
    HTF pipeline still accepts provider 15m files, but this contract makes flag
    preservation explicit.
    """

    if df_1m.is_empty():
        return df_1m

    grouped = (
        df_1m.with_columns(pl.col("timestamp").dt.truncate("15m").alias("_bucket"))
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
                pl.col("is_open_session_gap_fill").any().alias("is_open_session_gap_fill"),
                pl.col("minutes_since_prev_real_bar").max().alias("minutes_since_prev_real_bar"),
                pl.col("session_id").first().alias("session_id"),
                pl.col("session_date").first().alias("session_date"),
                pl.col("session_bar_pos").min().alias("session_bar_pos"),
                pl.col("session_minutes_to_close").min().alias("session_minutes_to_close"),
                pl.col("is_session_open_bar").any().alias("is_session_open_bar"),
                pl.col("is_session_close_bar").any().alias("is_session_close_bar"),
                pl.col("is_weekly_open_bar").any().alias("is_weekly_open_bar"),
                pl.col("is_weekly_close_bar").any().alias("is_weekly_close_bar"),
            ]
        )
        .rename({"_bucket": "timestamp"})
        .select(CANONICAL_BAR_COLUMNS)
        .sort("timestamp")
    )
    return grouped
