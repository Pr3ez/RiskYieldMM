"""Sparse-safe walk-forward window planning for RPF optimization."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import polars as pl


@dataclass(frozen=True)
class RPFWindow:
    step_idx: int
    pred_pos: int
    pred_batch_id: int
    train_batch_ids: tuple[int, ...]
    val_batch_ids: tuple[int, ...]
    train_start_ts: datetime | None = None
    train_end_ts: datetime | None = None
    val_start_ts: datetime | None = None
    val_end_ts: datetime | None = None
    pred_start_ts: datetime | None = None
    pred_end_ts: datetime | None = None
    train_valid_row_count: int | None = None
    val_valid_row_count: int | None = None
    pred_valid_row_count: int | None = None


def build_windows(
    batch_index: pl.DataFrame,
    *,
    lookback_batches: int,
    val_batches: int,
    embargo_batches: int = 0,
    n_steps: int = 0,
) -> list[RPFWindow]:
    if batch_index.is_empty():
        return []
    rows = batch_index.sort("rpf_available_pos").to_dicts()
    windows: list[RPFWindow] = []
    for pos_idx, row in enumerate(rows):
        pred_pos = int(row["rpf_available_pos"])
        val_end_idx = pos_idx - int(embargo_batches)
        val_start_idx = val_end_idx - int(val_batches)
        train_end_idx = val_start_idx
        train_start_idx = train_end_idx - int(lookback_batches)
        if train_start_idx < 0 or val_start_idx < 0 or val_end_idx > pos_idx:
            continue
        train_ids = tuple(int(rows[i]["batch_id"]) for i in range(train_start_idx, train_end_idx))
        val_ids = tuple(int(rows[i]["batch_id"]) for i in range(val_start_idx, val_end_idx))
        if len(train_ids) != int(lookback_batches) or len(val_ids) != int(val_batches):
            continue
        train_rows = rows[train_start_idx:train_end_idx]
        val_rows = rows[val_start_idx:val_end_idx]
        windows.append(
            RPFWindow(
                step_idx=len(windows),
                pred_pos=pred_pos,
                pred_batch_id=int(row["batch_id"]),
                train_batch_ids=train_ids,
                val_batch_ids=val_ids,
                train_start_ts=train_rows[0].get("batch_start_ts"),
                train_end_ts=train_rows[-1].get("batch_end_ts"),
                val_start_ts=val_rows[0].get("batch_start_ts"),
                val_end_ts=val_rows[-1].get("batch_end_ts"),
                pred_start_ts=row.get("batch_start_ts"),
                pred_end_ts=row.get("batch_end_ts"),
                train_valid_row_count=sum(int(item.get("valid_row_count") or 0) for item in train_rows),
                val_valid_row_count=sum(int(item.get("valid_row_count") or 0) for item in val_rows),
                pred_valid_row_count=int(row.get("valid_row_count") or 0),
            )
        )
    return windows[-int(n_steps) :] if n_steps > 0 else windows


def windows_to_frame(windows: list[RPFWindow]) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "step_idx": int(window.step_idx),
                "pred_pos": int(window.pred_pos),
                "pred_batch_id": int(window.pred_batch_id),
                "train_batch_ids": list(window.train_batch_ids),
                "val_batch_ids": list(window.val_batch_ids),
                "train_batch_count": int(len(window.train_batch_ids)),
                "val_batch_count": int(len(window.val_batch_ids)),
                "train_start_ts": window.train_start_ts,
                "train_end_ts": window.train_end_ts,
                "val_start_ts": window.val_start_ts,
                "val_end_ts": window.val_end_ts,
                "pred_start_ts": window.pred_start_ts,
                "pred_end_ts": window.pred_end_ts,
                "train_valid_row_count": window.train_valid_row_count,
                "val_valid_row_count": window.val_valid_row_count,
                "pred_valid_row_count": window.pred_valid_row_count,
            }
            for window in windows
        ],
        infer_schema_length=None,
    )


def windows_from_frame(frame: pl.DataFrame) -> list[RPFWindow]:
    return [
        RPFWindow(
            step_idx=int(row["step_idx"]),
            pred_pos=int(row["pred_pos"]),
            pred_batch_id=int(row["pred_batch_id"]),
            train_batch_ids=tuple(int(value) for value in row["train_batch_ids"]),
            val_batch_ids=tuple(int(value) for value in row["val_batch_ids"]),
            train_start_ts=row.get("train_start_ts"),
            train_end_ts=row.get("train_end_ts"),
            val_start_ts=row.get("val_start_ts"),
            val_end_ts=row.get("val_end_ts"),
            pred_start_ts=row.get("pred_start_ts"),
            pred_end_ts=row.get("pred_end_ts"),
            train_valid_row_count=_optional_int(row.get("train_valid_row_count")),
            val_valid_row_count=_optional_int(row.get("val_valid_row_count")),
            pred_valid_row_count=_optional_int(row.get("pred_valid_row_count")),
        )
        for row in frame.to_dicts()
    ]


def write_windows(path: Path, windows: list[RPFWindow]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    windows_to_frame(windows).write_parquet(path)
    return path


def read_windows(path: Path) -> list[RPFWindow]:
    if not path.exists():
        raise FileNotFoundError(f"Frozen RPF windows not found: {path}")
    return windows_from_frame(pl.read_parquet(path))


def _optional_int(value: object) -> int | None:
    return None if value is None else int(value)
