"""Causal signal-bank batch selection for RPF gate training."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import polars as pl

from regression_feature_engineering.walkforward.classify import DOWN_EXTREME, UP_EXTREME
from regression_feature_engineering.walkforward.data import RPFDataContext, VALID_COL, available_batch_ids
from regression_feature_engineering.walkforward.windows import RPFWindow


GATE_UP_DOMINANT = "future_up_dominant"
GATE_DOWN_DOMINANT = "future_down_dominant"
CHRONOLOGICAL_RECENT = "chronological_recent"
SIGNAL_BANK = "signal_bank"
HYBRID_RECENT_SIGNAL_BANK = "hybrid_recent_signal_bank"
WINDOW_MODES = (CHRONOLOGICAL_RECENT, SIGNAL_BANK, HYBRID_RECENT_SIGNAL_BANK)


@dataclass(frozen=True)
class SignalBankConfig:
    mode: str = CHRONOLOGICAL_RECENT
    positive_batch_min_rate: float = 0.80
    opposite_batch_max_rate: float = 0.20
    train_positive_batches: int = 80
    train_negative_batches: int = 160
    val_positive_batches: int = 20
    val_negative_batches: int = 40
    candidate_lookback_batches: int = 2000
    label_maturity_embargo_batches: int = 1
    recent_train_batches: int = 40
    recent_val_batches: int = 10


def build_batch_signal_inventory(context: RPFDataContext) -> pl.DataFrame:
    """Create batch-level clean UP/DOWN signal rates from mature label files."""

    batch_ids = available_batch_ids(context.feature_root, context.label_root)
    if not batch_ids:
        return _empty_inventory()
    paths = [context.label_root / f"batch_{batch_id:04d}.parquet" for batch_id in batch_ids]
    up = pl.col(UP_EXTREME)
    down = pl.col(DOWN_EXTREME)
    valid = (
        pl.col(VALID_COL).fill_null(False)
        & up.is_not_null()
        & down.is_not_null()
        & up.is_finite()
        & down.is_finite()
    )
    frame = (
        pl.scan_parquet(paths, extra_columns="ignore")
        .select(
            [
                "timestamp",
                "batch_id",
                VALID_COL,
                UP_EXTREME,
                DOWN_EXTREME,
                "label_window_batch_id",
                "label_window_end",
            ]
        )
        .filter(valid)
        .with_columns(
            [
                (up >= 2.0 * down).cast(pl.Int8).alias("up_dom"),
                (down >= 2.0 * up).cast(pl.Int8).alias("down_dom"),
                ((up > 0.0) & (down > 0.0) & (up < 2.0 * down) & (down < 2.0 * up))
                .cast(pl.Int8)
                .alias("mixed"),
                (up + down).alias("extreme_total"),
            ]
        )
        .group_by("batch_id")
        .agg(
            [
                pl.len().alias("rows"),
                pl.col("timestamp").min().alias("batch_start_ts"),
                pl.col("timestamp").max().alias("batch_end_ts"),
                pl.col("label_window_batch_id").max().alias("label_window_batch_id_max"),
                pl.col("label_window_end").max().alias("label_window_end_max"),
                pl.col("up_dom").mean().alias("up_dom_rate"),
                pl.col("down_dom").mean().alias("down_dom_rate"),
                pl.col("mixed").mean().alias("mixed_rate"),
                pl.col("extreme_total").mean().alias("extreme_total_mean"),
                pl.col("extreme_total").quantile(0.80).alias("extreme_total_q80"),
                up.mean().alias("up_extreme_mean"),
                down.mean().alias("down_extreme_mean"),
            ]
        )
        .sort("batch_id")
        .collect()
    )
    return frame


def build_signal_bank_windows(
    base_windows: list[RPFWindow],
    inventory: pl.DataFrame,
    *,
    gate_target: str,
    config: SignalBankConfig,
) -> tuple[list[RPFWindow], list[dict[str, Any]]]:
    if config.mode == CHRONOLOGICAL_RECENT:
        rows = [_chronological_row(window, config.mode) for window in base_windows]
        return base_windows, rows
    if config.mode not in WINDOW_MODES:
        known = ", ".join(WINDOW_MODES)
        raise ValueError(f"Unsupported signal-bank window mode {config.mode!r}; expected one of: {known}")
    pos_col, opposite_col = _target_rate_columns(gate_target)
    inv = inventory.sort("batch_id")
    rows_by_batch = {int(row["batch_id"]): row for row in inv.to_dicts()}
    out_windows: list[RPFWindow] = []
    audit_rows: list[dict[str, Any]] = []
    for base in base_windows:
        selected = _select_signal_bank_ids(
            inv,
            pred_batch_id=int(base.pred_batch_id),
            positive_rate_col=pos_col,
            opposite_rate_col=opposite_col,
            config=config,
        )
        train_ids = selected["train_ids"]
        val_ids = selected["val_ids"]
        if config.mode == HYBRID_RECENT_SIGNAL_BANK:
            mature_cutoff = int(base.pred_batch_id) - 1 - int(config.label_maturity_embargo_batches)
            recent_train = _mature_recent_ids(
                base.train_batch_ids,
                rows_by_batch,
                mature_cutoff=mature_cutoff,
                limit=int(config.recent_train_batches),
            )
            recent_val = _mature_recent_ids(
                base.val_batch_ids,
                rows_by_batch,
                mature_cutoff=mature_cutoff,
                limit=int(config.recent_val_batches),
            )
            train_ids = _sorted_unique((*train_ids, *recent_train))
            val_ids = _sorted_unique((*val_ids, *recent_val))
        if not train_ids or not val_ids:
            raise ValueError(f"Signal-bank window selected empty train/val ids for pred batch {base.pred_batch_id}")
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
                "window_mode": config.mode,
                "mature_cutoff_batch_id": selected["mature_cutoff_batch_id"],
                "eligible_candidate_count": selected["eligible_candidate_count"],
                "positive_candidate_count": selected["positive_candidate_count"],
                "negative_candidate_count": selected["negative_candidate_count"],
                "bank_train_positive_count": selected["train_positive_count"],
                "bank_train_negative_count": selected["train_negative_count"],
                "bank_val_positive_count": selected["val_positive_count"],
                "bank_val_negative_count": selected["val_negative_count"],
                "train_batch_count": len(train_ids),
                "val_batch_count": len(val_ids),
                "train_batch_ids": list(train_ids),
                "val_batch_ids": list(val_ids),
                "train_target_rate_weighted": _weighted_rate(rows_by_batch, train_ids, pos_col),
                "val_target_rate_weighted": _weighted_rate(rows_by_batch, val_ids, pos_col),
                "pred_batch_target_rate": _row_rate(rows_by_batch, int(base.pred_batch_id), pos_col),
                "max_train_label_window_batch_id": _max_label_window_batch_id(rows_by_batch, train_ids),
                "max_val_label_window_batch_id": _max_label_window_batch_id(rows_by_batch, val_ids),
            }
        )
    return out_windows, audit_rows


def _select_signal_bank_ids(
    inventory: pl.DataFrame,
    *,
    pred_batch_id: int,
    positive_rate_col: str,
    opposite_rate_col: str,
    config: SignalBankConfig,
) -> dict[str, Any]:
    mature_cutoff = int(pred_batch_id) - 1 - int(config.label_maturity_embargo_batches)
    min_batch = int(pred_batch_id) - int(config.candidate_lookback_batches)
    eligible = inventory.filter(
        (pl.col("batch_id") <= mature_cutoff)
        & (pl.col("batch_id") >= min_batch)
        & (pl.col("label_window_batch_id_max") <= mature_cutoff)
    )
    positives = eligible.filter(
        (pl.col(positive_rate_col) >= float(config.positive_batch_min_rate))
        & (pl.col(opposite_rate_col) <= float(config.opposite_batch_max_rate))
    ).sort("batch_id", descending=True)
    negatives = eligible.filter(
        pl.col(positive_rate_col) <= float(config.opposite_batch_max_rate)
    ).sort("batch_id", descending=True)
    val_pos = _take_batch_ids(positives, 0, int(config.val_positive_batches))
    train_pos = _take_batch_ids(positives, int(config.val_positive_batches), int(config.train_positive_batches))
    val_neg = _take_batch_ids(negatives, 0, int(config.val_negative_batches))
    train_neg = _take_batch_ids(negatives, int(config.val_negative_batches), int(config.train_negative_batches))
    if not train_pos or not train_neg:
        raise ValueError(
            f"Insufficient signal-bank train candidates for pred batch {pred_batch_id}: "
            f"positive={len(train_pos)} negative={len(train_neg)}"
        )
    if not val_pos or not val_neg:
        raise ValueError(
            f"Insufficient signal-bank validation candidates for pred batch {pred_batch_id}: "
            f"positive={len(val_pos)} negative={len(val_neg)}"
        )
    return {
        "train_ids": _sorted_unique((*train_pos, *train_neg)),
        "val_ids": _sorted_unique((*val_pos, *val_neg)),
        "mature_cutoff_batch_id": mature_cutoff,
        "eligible_candidate_count": eligible.height,
        "positive_candidate_count": positives.height,
        "negative_candidate_count": negatives.height,
        "train_positive_count": len(train_pos),
        "train_negative_count": len(train_neg),
        "val_positive_count": len(val_pos),
        "val_negative_count": len(val_neg),
    }


def _target_rate_columns(gate_target: str) -> tuple[str, str]:
    if gate_target == GATE_UP_DOMINANT:
        return "up_dom_rate", "down_dom_rate"
    if gate_target == GATE_DOWN_DOMINANT:
        return "down_dom_rate", "up_dom_rate"
    raise ValueError("signal_bank window mode currently supports future_up_dominant and future_down_dominant only")


def _take_batch_ids(frame: pl.DataFrame, start: int, count: int) -> tuple[int, ...]:
    if count <= 0:
        return ()
    rows = frame.slice(start, count)
    return tuple(int(value) for value in rows["batch_id"].to_list())


def _sorted_unique(values: tuple[int, ...]) -> tuple[int, ...]:
    return tuple(sorted({int(value) for value in values}))


def _mature_recent_ids(
    batch_ids: tuple[int, ...],
    rows_by_batch: dict[int, dict[str, Any]],
    *,
    mature_cutoff: int,
    limit: int,
) -> tuple[int, ...]:
    if limit <= 0:
        return ()
    selected: list[int] = []
    for batch_id in reversed(tuple(int(value) for value in batch_ids)):
        row = rows_by_batch.get(batch_id)
        if row is None:
            continue
        if int(row.get("label_window_batch_id_max") or batch_id) <= mature_cutoff:
            selected.append(batch_id)
        if len(selected) >= limit:
            break
    return tuple(reversed(selected))


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


def _max_label_window_batch_id(rows_by_batch: dict[int, dict[str, Any]], batch_ids: tuple[int, ...]) -> int | None:
    values = [
        int(rows_by_batch[int(batch_id)]["label_window_batch_id_max"])
        for batch_id in batch_ids
        if int(batch_id) in rows_by_batch and rows_by_batch[int(batch_id)].get("label_window_batch_id_max") is not None
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


def _chronological_row(window: RPFWindow, mode: str) -> dict[str, Any]:
    return {
        "step_idx": int(window.step_idx),
        "pred_batch_id": int(window.pred_batch_id),
        "window_mode": mode,
        "mature_cutoff_batch_id": None,
        "eligible_candidate_count": None,
        "positive_candidate_count": None,
        "negative_candidate_count": None,
        "bank_train_positive_count": None,
        "bank_train_negative_count": None,
        "bank_val_positive_count": None,
        "bank_val_negative_count": None,
        "train_batch_count": len(window.train_batch_ids),
        "val_batch_count": len(window.val_batch_ids),
        "train_batch_ids": list(window.train_batch_ids),
        "val_batch_ids": list(window.val_batch_ids),
        "train_target_rate_weighted": None,
        "val_target_rate_weighted": None,
        "pred_batch_target_rate": None,
        "max_train_label_window_batch_id": None,
        "max_val_label_window_batch_id": None,
    }


def _empty_inventory() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "batch_id": pl.Int64,
            "rows": pl.Int64,
            "batch_start_ts": pl.Datetime(time_zone="UTC"),
            "batch_end_ts": pl.Datetime(time_zone="UTC"),
            "label_window_batch_id_max": pl.Int64,
            "label_window_end_max": pl.Datetime(time_zone="UTC"),
            "up_dom_rate": pl.Float64,
            "down_dom_rate": pl.Float64,
            "mixed_rate": pl.Float64,
            "extreme_total_mean": pl.Float64,
            "extreme_total_q80": pl.Float64,
            "up_extreme_mean": pl.Float64,
            "down_extreme_mean": pl.Float64,
        }
    )
