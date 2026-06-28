"""EMA-regime batch selection and row filtering for RPF classification."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import polars as pl

from regression_feature_engineering.core.alignment import TIMEFRAME_MINUTES
from regression_feature_engineering.core.paths import canonical_ohlcv_path
from regression_feature_engineering.walkforward.data import RPFDataContext, VALID_COL, available_batch_ids
from regression_feature_engineering.walkforward.windows import RPFWindow


UP_EXTREME = "target_reg_distance_up_extreme_hvol_v2"
DOWN_EXTREME = "target_reg_distance_down_extreme_hvol_v2"
SIDE_UP = "up"
SIDE_DOWN = "down"
EMA_REGIME_BANK = "ema_regime_bank"
CHRONOLOGICAL_RECENT = "chronological_recent"
WINDOW_MODES = (CHRONOLOGICAL_RECENT, EMA_REGIME_BANK)


@dataclass(frozen=True)
class EMARegimeWindowConfig:
    timeframe: str
    side: str
    dominance_rate: float = 0.80
    train_batches: int = 120
    val_batches: int = 20
    candidate_lookback_batches: int = 2000
    label_maturity_embargo_batches: int = 1
    buffer: float = 0.0


@dataclass(frozen=True)
class EMARegimeFilter:
    timeframe: str
    side: str
    buffer: float
    current_close: pl.DataFrame
    ema: pl.DataFrame


def build_ema_regime_inventory(
    context: RPFDataContext,
    *,
    asset: str,
    timeframe: str,
    data_root: Path,
    buffer: float = 0.0,
    batch_chunk_size: int = 32,
    min_batch_id: int | None = None,
    max_batch_id: int | None = None,
) -> pl.DataFrame:
    """Build batch-level rates for rows above/below closed EMA200."""

    batch_ids = available_batch_ids(context.feature_root, context.label_root)
    if min_batch_id is not None:
        batch_ids = [batch_id for batch_id in batch_ids if int(batch_id) >= int(min_batch_id)]
    if max_batch_id is not None:
        batch_ids = [batch_id for batch_id in batch_ids if int(batch_id) <= int(max_batch_id)]
    if not batch_ids:
        return _empty_inventory()
    current_close = load_current_close(asset=asset, data_root=data_root)
    ema = load_closed_ema200(asset=asset, timeframe=timeframe, data_root=data_root)
    rows: list[pl.DataFrame] = []
    for chunk_ids in _chunks(batch_ids, max(1, int(batch_chunk_size))):
        label_paths = [context.label_root / f"batch_{batch_id:04d}.parquet" for batch_id in chunk_ids]
        labels = (
            pl.scan_parquet(label_paths, extra_columns="ignore")
            .select(["timestamp", "batch_id", VALID_COL, UP_EXTREME, DOWN_EXTREME, "label_window_batch_id"])
            .filter(
                pl.col(VALID_COL).fill_null(False)
                & pl.col(UP_EXTREME).is_not_null()
                & pl.col(DOWN_EXTREME).is_not_null()
                & pl.col(UP_EXTREME).is_finite()
                & pl.col(DOWN_EXTREME).is_finite()
                & pl.col("label_window_batch_id").is_not_null()
            )
            .collect()
        )
        if labels.is_empty():
            continue
        ts_min = labels["timestamp"].min()
        ts_max = labels["timestamp"].max()
        current_slice = current_close.filter((pl.col("timestamp") >= ts_min) & (pl.col("timestamp") <= ts_max))
        with_regime = attach_ema_regime(
            labels,
            current_close=current_slice,
            ema=ema,
            timeframe=timeframe,
            buffer=buffer,
        )
        rows.append(_aggregate_ema_inventory_chunk(with_regime))
    if not rows:
        return _empty_inventory()
    return pl.concat(rows, how="vertical").sort("batch_id")


def build_ema_regime_windows(
    base_windows: list[RPFWindow],
    inventory: pl.DataFrame,
    *,
    config: EMARegimeWindowConfig,
) -> tuple[list[RPFWindow], list[dict[str, Any]]]:
    if inventory.is_empty():
        raise ValueError("EMA-regime inventory is empty")
    rows_by_batch = {int(row["batch_id"]): row for row in inventory.to_dicts()}
    out_windows: list[RPFWindow] = []
    audit_rows: list[dict[str, Any]] = []
    rate_col = _rate_col(config.side)
    for base in base_windows:
        selected = _select_ema_regime_ids(inventory, pred_batch_id=int(base.pred_batch_id), rate_col=rate_col, config=config)
        train_ids = selected["train_ids"]
        val_ids = selected["val_ids"]
        if not train_ids or not val_ids:
            raise ValueError(
                f"EMA-regime window selected empty train/val ids for pred batch {base.pred_batch_id}: "
                f"train={len(train_ids)} val={len(val_ids)} candidates={selected['candidate_count']}"
            )
        out_windows.append(
            RPFWindow(
                step_idx=base.step_idx,
                pred_pos=base.pred_pos,
                pred_batch_id=base.pred_batch_id,
                train_batch_ids=train_ids,
                val_batch_ids=val_ids,
                train_start_ts=_min_ts(rows_by_batch, train_ids, "batch_start_ts"),
                train_end_ts=_max_ts(rows_by_batch, train_ids, "batch_end_ts"),
                val_start_ts=_min_ts(rows_by_batch, val_ids, "batch_start_ts"),
                val_end_ts=_max_ts(rows_by_batch, val_ids, "batch_end_ts"),
                pred_start_ts=base.pred_start_ts,
                pred_end_ts=base.pred_end_ts,
                train_valid_row_count=_row_sum(rows_by_batch, train_ids),
                val_valid_row_count=_row_sum(rows_by_batch, val_ids),
                pred_valid_row_count=base.pred_valid_row_count,
            )
        )
        audit_rows.append(
            {
                "step_idx": int(base.step_idx),
                "pred_batch_id": int(base.pred_batch_id),
                "window_mode": EMA_REGIME_BANK,
                "ema_timeframe": config.timeframe,
                "ema_side": config.side,
                "ema_buffer": float(config.buffer),
                "mature_cutoff_batch_id": selected["mature_cutoff_batch_id"],
                "candidate_count": selected["candidate_count"],
                "train_batch_count": len(train_ids),
                "val_batch_count": len(val_ids),
                "train_batch_ids": list(train_ids),
                "val_batch_ids": list(val_ids),
                "train_regime_rate_weighted": _weighted_rate(rows_by_batch, train_ids, rate_col),
                "val_regime_rate_weighted": _weighted_rate(rows_by_batch, val_ids, rate_col),
                "pred_batch_regime_rate": _row_rate(rows_by_batch, int(base.pred_batch_id), rate_col),
                "max_train_label_window_batch_id": _max_field(rows_by_batch, train_ids, "label_window_batch_id_max"),
                "max_val_label_window_batch_id": _max_field(rows_by_batch, val_ids, "label_window_batch_id_max"),
            }
        )
    return out_windows, audit_rows


def filter_ema_prediction_windows(
    base_windows: list[RPFWindow],
    inventory: pl.DataFrame,
    *,
    side: str,
    min_rate: float = 0.0,
) -> list[RPFWindow]:
    """Keep prediction windows where the selected EMA regime is active."""

    if inventory.is_empty():
        return []
    rate_col = _rate_col(side)
    rows_by_batch = {int(row["batch_id"]): row for row in inventory.to_dicts()}
    out: list[RPFWindow] = []
    for window in base_windows:
        rate = _row_rate(rows_by_batch, int(window.pred_batch_id), rate_col)
        if rate is None:
            continue
        if float(min_rate) <= 0.0:
            keep = float(rate) > 0.0
        else:
            keep = float(rate) >= float(min_rate)
        if keep:
            out.append(window)
    return out


def make_ema_regime_filter(*, asset: str, timeframe: str, side: str, buffer: float, data_root: Path) -> EMARegimeFilter:
    return EMARegimeFilter(
        timeframe=timeframe,
        side=side,
        buffer=float(buffer),
        current_close=load_current_close(asset=asset, data_root=data_root),
        ema=load_closed_ema200(asset=asset, timeframe=timeframe, data_root=data_root),
    )


def filter_frame_to_ema_regime(
    frame: pl.DataFrame,
    regime_filter: EMARegimeFilter,
    *,
    allow_empty: bool = False,
) -> pl.DataFrame:
    row_order = "_ema_regime_filter_row_order"
    regime_keys = attach_ema_regime(
        frame.with_row_index(row_order).select([row_order, "timestamp"]),
        current_close=regime_filter.current_close,
        ema=regime_filter.ema,
        timeframe=regime_filter.timeframe,
        buffer=regime_filter.buffer,
    )
    active_col = "ema_regime_above" if regime_filter.side == SIDE_UP else "ema_regime_below"
    keep = regime_keys.filter(pl.col(active_col) == 1).select(row_order)
    out = (
        frame.with_row_index(row_order)
        .join(keep, on=row_order, how="inner")
        .sort(row_order)
        .drop(row_order)
    )
    if out.is_empty() and not allow_empty:
        raise ValueError(
            f"EMA-regime row filter removed all rows: timeframe={regime_filter.timeframe} side={regime_filter.side}"
        )
    return out


def _aggregate_ema_inventory_chunk(with_regime: pl.DataFrame) -> pl.DataFrame:
    return (
        with_regime.group_by("batch_id")
        .agg(
            [
                pl.len().alias("rows"),
                pl.col("timestamp").min().alias("batch_start_ts"),
                pl.col("timestamp").max().alias("batch_end_ts"),
                pl.col("label_window_batch_id").max().alias("label_window_batch_id_max"),
                pl.col("ema_regime_above").mean().alias("above_ema_rate"),
                pl.col("ema_regime_below").mean().alias("below_ema_rate"),
                pl.col("ema_distance_pct").mean().alias("ema_distance_pct_mean"),
                pl.col("ema_distance_pct").quantile(0.20).alias("ema_distance_pct_q20"),
                pl.col("ema_distance_pct").quantile(0.80).alias("ema_distance_pct_q80"),
            ]
        )
        .sort("batch_id")
    )


def attach_ema_regime(
    rows: pl.DataFrame,
    *,
    current_close: pl.DataFrame,
    ema: pl.DataFrame,
    timeframe: str,
    buffer: float = 0.0,
) -> pl.DataFrame:
    left_order = "_ema_regime_row_order"
    joined = (
        rows.with_row_index(left_order)
        .join(current_close, on="timestamp", how="inner")
        .sort("timestamp")
        .join_asof(ema, left_on="timestamp", right_on="ema_bar_close_ts", strategy="backward")
        .sort(left_order)
        .drop(left_order)
    )
    return joined.with_columns(
        [
            pl.lit(timeframe).alias("ema_regime_timeframe"),
            ((pl.col("current_close") - pl.col("ema200")) / pl.col("ema200")).alias("ema_distance_pct"),
            (pl.col("current_close") > pl.col("ema200") * (1.0 + float(buffer)))
            .cast(pl.Int8)
            .alias("ema_regime_above"),
            (pl.col("current_close") < pl.col("ema200") * (1.0 - float(buffer)))
            .cast(pl.Int8)
            .alias("ema_regime_below"),
        ]
    )


def load_current_close(*, asset: str, data_root: Path) -> pl.DataFrame:
    path = canonical_ohlcv_path(data_root, asset, "1m")
    return pl.read_parquet(path, columns=["timestamp", "close"]).rename({"close": "current_close"})


def load_closed_ema200(*, asset: str, timeframe: str, data_root: Path) -> pl.DataFrame:
    if timeframe not in TIMEFRAME_MINUTES:
        known = ", ".join(sorted(TIMEFRAME_MINUTES))
        raise ValueError(f"Unsupported timeframe {timeframe!r}; expected one of: {known}")
    path = canonical_ohlcv_path(data_root, asset, timeframe)
    if not path.exists():
        raise FileNotFoundError(f"Canonical OHLCV not found: {path}")
    minutes = TIMEFRAME_MINUTES[timeframe]
    return (
        pl.read_parquet(path, columns=["timestamp", "close"])
        .sort("timestamp")
        .with_row_index("_ema_row_idx")
        .with_columns(
            [
                (pl.col("timestamp") + timedelta(minutes=minutes)).alias("ema_bar_close_ts"),
                pl.col("close").ewm_mean(span=200, adjust=False).alias("_ema200_raw"),
            ]
        )
        .with_columns(
            pl.when(pl.col("_ema_row_idx") >= 199)
            .then(pl.col("_ema200_raw"))
            .otherwise(None)
            .alias("ema200")
        )
        .select(["ema_bar_close_ts", pl.col("close").alias("ema_source_close"), "ema200"])
        .drop_nulls(["ema200"])
        .sort("ema_bar_close_ts")
    )


def _select_ema_regime_ids(
    inventory: pl.DataFrame,
    *,
    pred_batch_id: int,
    rate_col: str,
    config: EMARegimeWindowConfig,
) -> dict[str, Any]:
    mature_cutoff = int(pred_batch_id) - 1 - int(config.label_maturity_embargo_batches)
    min_batch = int(pred_batch_id) - int(config.candidate_lookback_batches)
    candidates = inventory.filter(
        (pl.col("batch_id") <= mature_cutoff)
        & (pl.col("batch_id") >= min_batch)
        & (pl.col("label_window_batch_id_max") <= mature_cutoff)
        & (pl.col(rate_col) >= float(config.dominance_rate))
    ).sort("batch_id", descending=True)
    val_ids = _take_ids(candidates, 0, int(config.val_batches))
    train_ids = _take_ids(candidates, int(config.val_batches), int(config.train_batches))
    return {
        "train_ids": tuple(sorted(train_ids)),
        "val_ids": tuple(sorted(val_ids)),
        "mature_cutoff_batch_id": mature_cutoff,
        "candidate_count": candidates.height,
    }


def _rate_col(side: str) -> str:
    if side == SIDE_UP:
        return "above_ema_rate"
    if side == SIDE_DOWN:
        return "below_ema_rate"
    raise ValueError(f"Unsupported EMA side: {side}")


def _take_ids(frame: pl.DataFrame, start: int, count: int) -> tuple[int, ...]:
    if count <= 0 or frame.is_empty():
        return ()
    return tuple(int(value) for value in frame.slice(int(start), int(count))["batch_id"].to_list())


def _chunks(values: list[int], size: int) -> list[list[int]]:
    return [values[idx : idx + int(size)] for idx in range(0, len(values), int(size))]


def _weighted_rate(rows_by_batch: dict[int, dict[str, Any]], batch_ids: tuple[int, ...], rate_col: str) -> float | None:
    numerator = 0.0
    denominator = 0.0
    for batch_id in batch_ids:
        row = rows_by_batch.get(int(batch_id))
        if row is None:
            continue
        weight = float(row.get("rows") or 0.0)
        rate = row.get(rate_col)
        if rate is None:
            continue
        numerator += weight * float(rate)
        denominator += weight
    return None if denominator == 0.0 else float(numerator / denominator)


def _row_rate(rows_by_batch: dict[int, dict[str, Any]], batch_id: int, rate_col: str) -> float | None:
    row = rows_by_batch.get(int(batch_id))
    if row is None:
        return None
    value = row.get(rate_col)
    return None if value is None else float(value)


def _row_sum(rows_by_batch: dict[int, dict[str, Any]], batch_ids: tuple[int, ...]) -> int:
    return int(sum(int(rows_by_batch.get(int(batch_id), {}).get("rows") or 0) for batch_id in batch_ids))


def _max_field(rows_by_batch: dict[int, dict[str, Any]], batch_ids: tuple[int, ...], field: str) -> int | None:
    values = [
        int(row[field])
        for batch_id in batch_ids
        if (row := rows_by_batch.get(int(batch_id))) is not None and row.get(field) is not None
    ]
    return max(values) if values else None


def _min_ts(rows_by_batch: dict[int, dict[str, Any]], batch_ids: tuple[int, ...], col: str) -> Any:
    values = [rows_by_batch[int(batch_id)].get(col) for batch_id in batch_ids if int(batch_id) in rows_by_batch]
    values = [value for value in values if value is not None]
    return min(values) if values else None


def _max_ts(rows_by_batch: dict[int, dict[str, Any]], batch_ids: tuple[int, ...], col: str) -> Any:
    values = [rows_by_batch[int(batch_id)].get(col) for batch_id in batch_ids if int(batch_id) in rows_by_batch]
    values = [value for value in values if value is not None]
    return max(values) if values else None


def _empty_inventory() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "batch_id": pl.Int64,
            "rows": pl.Int64,
            "batch_start_ts": pl.Datetime(time_zone="UTC"),
            "batch_end_ts": pl.Datetime(time_zone="UTC"),
            "label_window_batch_id_max": pl.Int64,
            "above_ema_rate": pl.Float64,
            "below_ema_rate": pl.Float64,
            "ema_distance_pct_mean": pl.Float64,
            "ema_distance_pct_q20": pl.Float64,
            "ema_distance_pct_q80": pl.Float64,
        }
    )
