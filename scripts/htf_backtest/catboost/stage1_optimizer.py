"""
Stage-1 Grid Evaluator (CatBoost)
=================================

Dedicated, leakage-safe stage-1 evaluator used to generate raw payloads for
offline analysis:
- fold validation predictions for every grid combo
- prediction-batch inference payload for every grid combo

This module intentionally does NOT compute heavy runtime metrics/tables.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from .utils import (
    coerce_stage1_batch_ids,
    get_feature_columns,
    load_batch,
    load_batches_by_ids,
    load_batches_range,
    prepare_features_target,
)

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
except Exception:  # pragma: no cover - fallback is handled at runtime
    pa = None
    pq = None


def _stage1_val_values(window_space: Any) -> list[int]:
    fixed_val = int(max(1, getattr(window_space, "stage1_val_batches_per_fold", 1)))
    val_min = int(max(1, getattr(window_space, "stage1_val_batches_min", fixed_val)))
    val_max = int(max(val_min, getattr(window_space, "stage1_val_batches_max", val_min)))
    val_grid = getattr(window_space, "stage1_val_batches_grid", None)
    if val_grid:
        vals = sorted(
            {
                int(v)
                for v in val_grid
                if val_min <= int(v) <= val_max and int(v) >= 1
            }
        )
    else:
        vals = list(range(val_min, val_max + 1))
    return vals or [fixed_val]


def _stage1_train_values(window_space: Any, val_batches_per_fold: int) -> list[int]:
    train_min = int(max(1, getattr(window_space, "stage1_train_batches_min", 1)))
    train_max = int(max(train_min, getattr(window_space, "stage1_train_batches_max", train_min)))
    multiplier_grid = getattr(window_space, "stage1_train_multiplier_grid", None)
    if multiplier_grid:
        vals = sorted(
            {
                int(val_batches_per_fold) * int(m)
                for m in multiplier_grid
                if int(m) >= 1
                and train_min <= int(val_batches_per_fold) * int(m) <= train_max
            }
        )
        if vals:
            return vals
    grid = getattr(window_space, "stage1_train_batches_grid", None)
    if grid:
        vals = sorted(
            {int(v) for v in grid if train_min <= int(v) <= train_max}
        )
        if vals:
            return vals
    return list(range(train_min, train_max + 1))


def _stage1_pair_values(window_space: Any) -> list[tuple[int, int]]:
    raw_pairs = getattr(window_space, "stage1_pair_grid", None)
    if not raw_pairs:
        return []

    fixed_val = int(max(1, getattr(window_space, "stage1_val_batches_per_fold", 1)))
    val_min = int(max(1, getattr(window_space, "stage1_val_batches_min", fixed_val)))
    val_max = int(max(val_min, getattr(window_space, "stage1_val_batches_max", val_min)))
    train_min = int(max(1, getattr(window_space, "stage1_train_batches_min", 1)))
    train_max = int(max(train_min, getattr(window_space, "stage1_train_batches_max", train_min)))

    pairs: set[tuple[int, int]] = set()
    for item in raw_pairs:
        val_batches = None
        train_batches = None
        if isinstance(item, dict):
            val_batches = item.get("val_batches_per_fold", item.get("val"))
            train_batches = item.get("train_batches_per_fold", item.get("train"))
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            val_batches = item[0]
            train_batches = item[1]

        if val_batches is None or train_batches is None:
            continue

        v = int(val_batches)
        t = int(train_batches)
        if v < val_min or v > val_max:
            continue
        if t < train_min or t > train_max:
            continue
        pairs.add((v, t))

    return sorted(pairs)


def _stage1_triplet_values(window_space: Any) -> list[tuple[int, int, int]]:
    raw_triplets = getattr(window_space, "stage1_triplet_grid", None)
    if not raw_triplets:
        return []

    folds_min = int(max(1, getattr(window_space, "stage1_folds_min", 1)))
    folds_max = int(max(folds_min, getattr(window_space, "stage1_folds_max", folds_min)))
    fixed_val = int(max(1, getattr(window_space, "stage1_val_batches_per_fold", 1)))
    val_min = int(max(1, getattr(window_space, "stage1_val_batches_min", fixed_val)))
    val_max = int(max(val_min, getattr(window_space, "stage1_val_batches_max", val_min)))
    train_min = int(max(1, getattr(window_space, "stage1_train_batches_min", 1)))
    train_max = int(max(train_min, getattr(window_space, "stage1_train_batches_max", train_min)))

    triplets: set[tuple[int, int, int]] = set()
    for item in raw_triplets:
        fold_count = None
        val_batches = None
        train_batches = None

        if isinstance(item, dict):
            fold_count = item.get("fold_count", item.get("fold"))
            val_batches = item.get("val_batches_per_fold", item.get("val"))
            train_batches = item.get("train_batches_per_fold", item.get("train"))
        elif isinstance(item, (list, tuple)) and len(item) >= 3:
            fold_count = item[0]
            val_batches = item[1]
            train_batches = item[2]

        if fold_count is None or val_batches is None or train_batches is None:
            continue

        f = int(fold_count)
        v = int(val_batches)
        t = int(train_batches)
        if f < folds_min or f > folds_max:
            continue
        if v < val_min or v > val_max:
            continue
        if t < train_min or t > train_max:
            continue
        triplets.add((f, v, t))

    return sorted(triplets)


def build_stage1_combo_grid(window_space: Any) -> list[dict[str, int]]:
    folds_min = int(max(1, getattr(window_space, "stage1_folds_min", 1)))
    folds_max = int(max(folds_min, getattr(window_space, "stage1_folds_max", folds_min)))
    fold_grid = getattr(window_space, "stage1_fold_grid", None)
    if fold_grid:
        fold_values = sorted({int(v) for v in fold_grid if int(v) >= 1})
        if not fold_values:
            fold_values = list(range(folds_min, folds_max + 1))
    else:
        fold_values = list(range(folds_min, folds_max + 1))
    triplet_values = _stage1_triplet_values(window_space)
    pair_values = _stage1_pair_values(window_space)
    combos: list[dict[str, int]] = []
    combo_id = 0
    if triplet_values:
        for fold_count, val_batches, train_batches in triplet_values:
            combos.append(
                {
                    "combo_id": int(combo_id),
                    "fold_count": int(fold_count),
                    "val_batches_per_fold": int(val_batches),
                    "train_batches_per_fold": int(train_batches),
                }
            )
            combo_id += 1
    elif pair_values:
        for fold_count in fold_values:
            for val_batches, train_batches in pair_values:
                combos.append(
                    {
                        "combo_id": int(combo_id),
                        "fold_count": int(fold_count),
                        "val_batches_per_fold": int(val_batches),
                        "train_batches_per_fold": int(train_batches),
                    }
                )
                combo_id += 1
    else:
        for fold_count in fold_values:
            for val_batches in _stage1_val_values(window_space):
                for train_batches in _stage1_train_values(window_space, val_batches):
                    combos.append(
                        {
                            "combo_id": int(combo_id),
                            "fold_count": int(fold_count),
                            "val_batches_per_fold": int(val_batches),
                            "train_batches_per_fold": int(train_batches),
                        }
                    )
                    combo_id += 1
    return combos


def fit_catboost_with_fallback_stage1(
    *,
    params: dict[str, Any],
    iterations: int,
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
) -> tuple[Any, bool]:
    """
    Stage-1 CatBoost fit with the same fallback semantics used in Step-1:
    - GPU first with eval_set/use_best_model
    - if eval contains unseen classes, retry without eval_set
    - if GPU fails, fallback to CPU (same retry behavior)
    """
    try:
        from catboost import CatBoostClassifier
    except Exception as e:  # pragma: no cover
        raise RuntimeError("CatBoost is required for Stage-1") from e

    def _is_unseen_val_class_error(exc: Exception) -> bool:
        msg = str(exc)
        return (
            "contains class label" in msg
            and "not present in the learn dataset" in msg
        )

    def _fit_once(fit_params: dict[str, Any], use_eval: bool) -> Any:
        model = CatBoostClassifier(**fit_params, iterations=int(iterations))
        if use_eval:
            model.fit(
                X_train,
                y_train,
                eval_set=(X_val, y_val),
                use_best_model=True,
                early_stopping_rounds=50,
                verbose=False,
            )
        else:
            # Fallback for folds where validation has unseen classes.
            model.fit(
                X_train,
                y_train,
                use_best_model=False,
                verbose=False,
            )
        return model

    try:
        return _fit_once(params, use_eval=True), False
    except Exception as gpu_err:
        if _is_unseen_val_class_error(gpu_err):
            try:
                return _fit_once(params, use_eval=False), False
            except Exception:
                pass

        params_cpu = dict(params)
        params_cpu["task_type"] = "CPU"
        params_cpu.pop("devices", None)

        try:
            return _fit_once(params_cpu, use_eval=True), True
        except Exception as cpu_err:
            if _is_unseen_val_class_error(cpu_err):
                return _fit_once(params_cpu, use_eval=False), True
            raise


class _PayloadWriter:
    """Incremental parquet writer for stage-1 payloads."""

    def __init__(self, path: Path, n_classes: int):
        self.path = Path(path)
        self.n_classes = int(n_classes)
        self._writer = None
        self._frames: list[pl.DataFrame] = []
        self._row_count = 0
        self._has_pyarrow = pa is not None and pq is not None

    def write(
        self,
        *,
        combo_id: int,
        fold_id: int,
        scope: str,
        action_key: str,
        candidate_source: str | None = None,
        probe_tier: int | None = None,
        discovered_from: str | None = None,
        timestamps: np.ndarray,
        batch_ids: np.ndarray,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        proba: np.ndarray,
    ) -> None:
        n = int(len(y_true))
        if n <= 0:
            return
        self._row_count += n
        proba = np.asarray(proba, dtype=np.float32)
        payload: dict[str, Any] = {
            "combo_id": np.full(n, int(combo_id), dtype=np.int32),
            "fold_id": np.full(n, int(fold_id), dtype=np.int16),
            "scope": np.full(n, str(scope), dtype=object),
            "action_key": np.full(n, str(action_key), dtype=object),
            "candidate_source": np.full(
                n,
                str(candidate_source or "base_grid"),
                dtype=object,
            ),
            "probe_tier": np.full(
                n,
                int(probe_tier if probe_tier is not None else -1),
                dtype=np.int16,
            ),
            "discovered_from": np.full(
                n,
                str(discovered_from or ""),
                dtype=object,
            ),
            "timestamp": timestamps[:n],
            "batch_id": np.asarray(batch_ids[:n], dtype=np.int32),
            "y_true": np.asarray(y_true[:n], dtype=np.int16),
            "y_pred": np.asarray(y_pred[:n], dtype=np.int16),
        }
        for c in range(self.n_classes):
            payload[f"prob_class_{c}"] = proba[:n, c]

        if self._has_pyarrow:
            table = pa.table(payload)
            if self._writer is None:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self._writer = pq.ParquetWriter(
                    str(self.path),
                    table.schema,
                    compression="zstd",
                )
            self._writer.write_table(table)
        else:
            self._frames.append(pl.DataFrame(payload))

    def close(self) -> None:
        if self._writer is not None:
            self._writer.close()
            self._writer = None
            return
        if self._frames:
            df = pl.concat(self._frames)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            df.write_parquet(self.path)
            self._frames.clear()
            return
        empty_cols: dict[str, list[Any]] = {
            "combo_id": [],
            "fold_id": [],
            "scope": [],
            "action_key": [],
            "candidate_source": [],
            "probe_tier": [],
            "discovered_from": [],
            "timestamp": [],
            "batch_id": [],
            "y_true": [],
            "y_pred": [],
        }
        for c in range(self.n_classes):
            empty_cols[f"prob_class_{c}"] = []
        self.path.parent.mkdir(parents=True, exist_ok=True)
        pl.DataFrame(empty_cols).write_parquet(self.path)

    @property
    def row_count(self) -> int:
        return int(self._row_count)


def evaluate_stage1_grid(
    *,
    step_optimizer: Any,
    train_end: int,
    pred_batch: int,
    step_stage1_dir: Path,
    available_batch_ids: list[int] | None = None,
    batch_positions: dict[int, int] | None = None,
    pred_pos: int | None = None,
    combo_grid_override: list[dict[str, Any]] | None = None,
    append_mode: bool = False,
    candidate_source: str = "base_grid",
    probe_tier: int | None = None,
    discovered_from: str | None = None,
) -> dict[str, Any]:
    """
    Evaluate full stage-1 fold grid and persist raw payload artifacts.

    Returns a lightweight step summary dict (no heavy metrics).
    """
    cfg = step_optimizer.config
    win = step_optimizer.window_space
    step_stage1_dir = Path(step_stage1_dir)
    step_stage1_dir.mkdir(parents=True, exist_ok=True)

    if str(getattr(win, "window_selection_mode", "")) != "stage1_fold_cv":
        raise ValueError("evaluate_stage1_grid requires window_selection_mode=stage1_fold_cv")

    t0 = time.perf_counter()
    lookback_max = int(max(1, getattr(win, "lookback_max", 300)))
    if available_batch_ids is not None:
        ordered_available = [int(v) for v in available_batch_ids]
        if int(pred_batch) in ordered_available:
            pred_local_pos = ordered_available.index(int(pred_batch))
            available_train_batches = ordered_available[:pred_local_pos]
        else:
            available_train_batches = [
                int(v) for v in ordered_available if int(v) <= int(train_end)
            ]
        if not available_train_batches:
            raise ValueError("No available Stage-1 train batches before prediction batch")
        lookback_batch_ids = available_train_batches[-lookback_max:]
        range_start = int(lookback_batch_ids[0])
        df_all = load_batches_by_ids(
            cfg.features_dir,
            cfg.labels_dir,
            step_optimizer.TIMEFRAME,
            lookback_batch_ids,
            target_col=cfg.target,
            feature_target_col=(cfg.feature_target or cfg.target),
            exclude_tail_pct=cfg.exclude_tail_pct,
        )
    else:
        range_start = max(1, int(train_end) - lookback_max + 1)
        lookback_batch_ids = list(range(range_start, int(train_end) + 1))
        df_all = load_batches_range(
            cfg.features_dir,
            cfg.labels_dir,
            step_optimizer.TIMEFRAME,
            range_start,
            int(train_end) + 1,
            target_col=cfg.target,
            feature_target_col=(cfg.feature_target or cfg.target),
            exclude_tail_pct=cfg.exclude_tail_pct,
        )
    df_all = df_all.filter(pl.col(cfg.target) >= 0).sort(["batch_id", "timestamp"])
    if len(df_all) == 0:
        raise ValueError("No stage1 rows available in lookback window")
    if int(df_all["batch_id"].max()) > int(train_end):
        raise ValueError("leakage guard failed: stage1 train data exceeds train_end")

    all_feature_cols = get_feature_columns(df_all, cfg.target)
    batch_cache = step_optimizer._build_stage1_batch_cache(df_all, all_feature_cols)
    if not batch_cache:
        raise ValueError("No batch cache entries for stage1 evaluation")

    ts_by_batch: dict[int, np.ndarray] = {}
    for df_b in df_all.partition_by("batch_id", maintain_order=True):
        if len(df_b) == 0:
            continue
        bid = int(df_b["batch_id"][0])
        ts_by_batch[bid] = np.asarray(df_b["timestamp"].to_numpy())

    available_batches = sorted(batch_cache.keys())
    min_batch = int(available_batches[0])

    x_chunks: list[np.ndarray] = []
    y_chunks: list[np.ndarray] = []
    ts_chunks: list[np.ndarray] = []
    bid_chunks: list[np.ndarray] = []
    batch_bounds: dict[int, tuple[int, int]] = {}
    cursor = 0
    for bid in available_batches:
        X_b, y_b = batch_cache[int(bid)]
        ts_b = ts_by_batch.get(int(bid))
        if ts_b is None:
            continue
        n = int(min(len(y_b), len(ts_b)))
        if n <= 0:
            continue
        X_b = X_b[:n]
        y_b = y_b[:n]
        ts_b = ts_b[:n]
        batch_bounds[int(bid)] = (cursor, cursor + n)
        cursor += n
        x_chunks.append(X_b)
        y_chunks.append(y_b)
        ts_chunks.append(ts_b)
        bid_chunks.append(np.full(n, int(bid), dtype=np.int32))

    if not x_chunks:
        raise ValueError("No compact stage1 arrays available")

    X_compact = np.vstack(x_chunks)
    y_compact = np.concatenate(y_chunks)
    ts_compact = np.concatenate(ts_chunks)
    bid_compact = np.concatenate(bid_chunks)

    x_chunks.clear()
    y_chunks.clear()
    ts_chunks.clear()
    bid_chunks.clear()
    batch_cache.clear()

    available_batch_set = set(batch_bounds.keys())
    range_cache: dict[tuple[int, ...], tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = {}

    # Pre-decision context snapshot for downstream meta-learning.
    def _class_dist(arr: np.ndarray, n_classes: int) -> tuple[list[int], list[float]]:
        if arr is None or len(arr) == 0:
            return [0] * int(n_classes), [0.0] * int(n_classes)
        counts = np.bincount(arr.astype(np.int32), minlength=int(n_classes))[: int(n_classes)]
        total = float(np.sum(counts))
        if total <= 0:
            return [int(v) for v in counts.tolist()], [0.0] * int(n_classes)
        return [int(v) for v in counts.tolist()], [float(v / total) for v in counts.tolist()]

    rows_per_batch = [int(end - start) for (start, end) in batch_bounds.values()]
    recent_n = int(max(1, getattr(win, "recent_ref_batches", 96)))
    recent_batches = sorted(batch_bounds.keys())[-recent_n:]
    if recent_batches:
        recent_batch_set = set(recent_batches)
        recent_mask = np.array([int(b) in recent_batch_set for b in bid_compact], dtype=bool)
        y_recent = y_compact[recent_mask]
    else:
        y_recent = np.array([], dtype=np.int32)

    lookback_counts, lookback_pct = _class_dist(y_compact, cfg.n_classes)
    recent_counts, recent_pct = _class_dist(y_recent, cfg.n_classes)

    predecision_context = {
        "train_end_batch": int(train_end),
        "pred_batch": int(pred_batch),
        "target": str(cfg.target),
        "feature_target": str(cfg.feature_target or cfg.target),
        "n_classes": int(cfg.n_classes),
        "lookback_range_start_batch": int(range_start),
        "lookback_range_end_batch": int(train_end),
        "stage1_window_index_mode": (
            "available_batch_pos" if available_batch_ids is not None else "numeric_batch_id"
        ),
        "pred_pos": None if pred_pos is None else int(pred_pos),
        "lookback_available_batch_count": int(len(lookback_batch_ids)),
        "lookback_first_available_batch": (
            int(lookback_batch_ids[0]) if lookback_batch_ids else None
        ),
        "lookback_last_available_batch": (
            int(lookback_batch_ids[-1]) if lookback_batch_ids else None
        ),
        "lookback_numeric_gap_count": int(
            max(0, int(lookback_batch_ids[-1]) - int(lookback_batch_ids[0]) + 1 - len(set(lookback_batch_ids)))
            if lookback_batch_ids
            else 0
        ),
        "available_batches": int(len(batch_bounds)),
        "lookback_rows": int(len(y_compact)),
        "rows_per_batch_min": int(min(rows_per_batch)) if rows_per_batch else 0,
        "rows_per_batch_median": int(np.median(rows_per_batch)) if rows_per_batch else 0,
        "rows_per_batch_max": int(max(rows_per_batch)) if rows_per_batch else 0,
        "recent_batches_n": int(min(recent_n, len(batch_bounds))),
        "recent_batches_start": int(recent_batches[0]) if recent_batches else None,
        "recent_batches_end": int(recent_batches[-1]) if recent_batches else None,
        "recent_rows": int(len(y_recent)),
        "class_counts_lookback": {
            str(c): int(lookback_counts[c]) for c in range(int(cfg.n_classes))
        },
        "class_pct_lookback": {
            str(c): float(lookback_pct[c]) for c in range(int(cfg.n_classes))
        },
        "class_counts_recent": {
            str(c): int(recent_counts[c]) for c in range(int(cfg.n_classes))
        },
        "class_pct_recent": {
            str(c): float(recent_pct[c]) for c in range(int(cfg.n_classes))
        },
    }

    def _slice_batch_ids(batch_ids: list[int]):
        ids = [int(v) for v in batch_ids]
        key = tuple(ids)
        cached = range_cache.get(key)
        if cached is not None:
            return cached, None
        missing = [b for b in ids if b not in available_batch_set]
        if missing:
            return None, f"missing_batch:{','.join(str(b) for b in missing)}"
        parts = [batch_bounds[int(batch_id)] for batch_id in ids]
        start_idx = int(parts[0][0])
        end_idx = int(parts[-1][1])
        sliced = (
            X_compact[start_idx:end_idx],
            y_compact[start_idx:end_idx],
            ts_compact[start_idx:end_idx],
            bid_compact[start_idx:end_idx],
        )
        range_cache[key] = sliced
        return sliced, None

    def _batch_ids_from_window(row: dict[str, Any], prefix: str, start_batch: int, end_batch: int) -> list[int]:
        ids = coerce_stage1_batch_ids(row.get(f"{prefix}_batch_ids"))
        if ids:
            return ids
        return list(range(int(start_batch), int(end_batch) + 1))

    pred_X = None
    pred_y = None
    pred_ts = None
    pred_bids = None
    try:
        pred_df = load_batch(
            cfg.features_dir,
            cfg.labels_dir,
            step_optimizer.TIMEFRAME,
            int(pred_batch),
            target_col=cfg.target,
            feature_target_col=(cfg.feature_target or cfg.target),
            exclude_tail_pct=cfg.exclude_tail_pct,
        ).filter(pl.col(cfg.target) >= 0)
        if len(pred_df) > 0:
            pred_X, pred_y, _, _ = prepare_features_target(
                pred_df, all_feature_cols, cfg.target
            )
            pred_X = np.nan_to_num(pred_X, nan=0.0, posinf=0.0, neginf=0.0)
            pred_ts = np.asarray(pred_df["timestamp"].to_numpy())
            pred_bids = np.asarray(pred_df["batch_id"].to_numpy(), dtype=np.int32)
            predecision_context["pred_rows"] = int(len(pred_y))
            predecision_context["pred_timestamp_start"] = (
                str(pred_ts[0]) if len(pred_ts) > 0 else None
            )
            predecision_context["pred_timestamp_end"] = (
                str(pred_ts[-1]) if len(pred_ts) > 0 else None
            )
    except Exception:
        pred_X = None
        pred_y = None
        pred_ts = None
        pred_bids = None
        predecision_context["pred_rows"] = 0
        predecision_context["pred_timestamp_start"] = None
        predecision_context["pred_timestamp_end"] = None

    combo_index_path = step_stage1_dir / "stage1_combo_index.parquet"
    fold_windows_path = step_stage1_dir / "stage1_fold_windows.parquet"
    val_payload_path = step_stage1_dir / "stage1_val_predictions.parquet"
    pred_payload_path = step_stage1_dir / "stage1_pred_batch_predictions.parquet"

    existing_combo_df = (
        pl.read_parquet(combo_index_path)
        if append_mode and combo_index_path.exists()
        else pl.DataFrame()
    )
    existing_action_keys: set[str] = set()
    existing_max_combo_id = -1
    if not existing_combo_df.is_empty():
        if "action_key" in existing_combo_df.columns:
            existing_action_keys = {
                str(v)
                for v in existing_combo_df["action_key"].to_list()
                if v is not None and str(v) != ""
            }
        else:
            for row in existing_combo_df.select(
                ["fold_count", "val_batches_per_fold", "train_batches_per_fold"]
            ).iter_rows(named=True):
                existing_action_keys.add(
                    f"f{int(row['fold_count'])}_v{int(row['val_batches_per_fold'])}_t{int(row['train_batches_per_fold'])}"
                )
        if "combo_id" in existing_combo_df.columns:
            existing_max_combo_id = int(existing_combo_df["combo_id"].max())

    raw_combos = combo_grid_override if combo_grid_override is not None else build_stage1_combo_grid(win)
    next_combo_id = existing_max_combo_id + 1 if append_mode else 0
    combos: list[dict[str, int]] = []
    for raw in raw_combos:
        fold_count = int(raw.get("fold_count", 0))
        val_batches = int(raw.get("val_batches_per_fold", 0))
        train_batches = int(raw.get("train_batches_per_fold", 0))
        if fold_count <= 0 or val_batches <= 0 or train_batches <= 0:
            continue
        action_key = str(
            raw.get("action_key")
            or f"f{int(fold_count)}_v{int(val_batches)}_t{int(train_batches)}"
        )
        if append_mode and action_key in existing_action_keys:
            continue
        combos.append(
            {
                "combo_id": int(next_combo_id),
                "fold_count": int(fold_count),
                "val_batches_per_fold": int(val_batches),
                "train_batches_per_fold": int(train_batches),
                "action_key": action_key,
            }
        )
        next_combo_id += 1

    val_new_path = (
        step_stage1_dir / "stage1_val_predictions.__append_new__.parquet"
        if append_mode
        else val_payload_path
    )
    pred_new_path = (
        step_stage1_dir / "stage1_pred_batch_predictions.__append_new__.parquet"
        if append_mode
        else pred_payload_path
    )

    val_writer = _PayloadWriter(val_new_path, cfg.n_classes)
    pred_writer = _PayloadWriter(pred_new_path, cfg.n_classes)

    combo_records: list[dict[str, Any]] = []
    fold_window_records: list[dict[str, Any]] = []
    fail_counter: Counter[str] = Counter()

    train_model_cache: dict[tuple[int, ...], Any] = {}
    train_model_cache_hits = 0
    train_model_cache_misses = 0
    fold_count_total = 0
    fold_count_completed = 0

    base_params = dict(cfg.cb_base_params)
    baseline_iterations = int(max(10, step_optimizer.model_space.num_boost_round_min))

    for combo in combos:
        combo_id = int(combo["combo_id"])
        fold_count = int(combo["fold_count"])
        val_batches = int(combo["val_batches_per_fold"])
        train_batches = int(combo["train_batches_per_fold"])
        action_key = str(
            combo.get("action_key")
            or f"f{int(fold_count)}_v{int(val_batches)}_t{int(train_batches)}"
        )
        combo_t0 = time.perf_counter()

        windows = step_optimizer._build_stage1_fold_windows(
            train_end=int(train_end),
            fold_count=fold_count,
            train_batches_per_fold=train_batches,
            val_batches_per_fold=val_batches,
            min_batch=min_batch,
            available_batches=available_batches if available_batch_ids is not None else None,
            batch_positions=batch_positions,
            pred_pos=pred_pos,
        )
        for w in windows:
            train_batch_ids = _batch_ids_from_window(
                w,
                "train",
                int(w["train_start_batch"]),
                int(w["train_end_batch"]),
            )
            val_batch_ids = _batch_ids_from_window(
                w,
                "val",
                int(w["val_start_batch"]),
                int(w["val_end_batch"]),
            )
            fold_window_records.append(
                {
                    "combo_id": combo_id,
                    "action_key": action_key,
                    "fold_id": int(w["fold_id"]),
                    "train_start_batch": int(w["train_start_batch"]),
                    "train_end_batch": int(w["train_end_batch"]),
                    "val_start_batch": int(w["val_start_batch"]),
                    "val_end_batch": int(w["val_end_batch"]),
                    "val_batch": int(w["val_batch"]),
                    "train_start_pos": w.get("train_start_pos"),
                    "train_end_pos": w.get("train_end_pos"),
                    "val_start_pos": w.get("val_start_pos"),
                    "val_end_pos": w.get("val_end_pos"),
                    "pred_pos": w.get("pred_pos"),
                    "train_batch_ids": train_batch_ids,
                    "val_batch_ids": val_batch_ids,
                    "train_batch_count": int(len(train_batch_ids)),
                    "val_batch_count": int(len(val_batch_ids)),
                    "window_is_sparse": bool(w.get("window_is_sparse", False)),
                    "candidate_source": str(candidate_source or "base_grid"),
                    "probe_tier": int(probe_tier if probe_tier is not None else -1),
                    "discovered_from": str(discovered_from or ""),
                }
            )

        if len(windows) < fold_count:
            fail_reason = "not_enough_history_for_requested_folds"
            fail_counter[fail_reason] += 1
            combo_records.append(
                {
                    "combo_id": combo_id,
                    "action_key": action_key,
                    "fold_count": fold_count,
                    "val_batches_per_fold": val_batches,
                    "train_batches_per_fold": train_batches,
                    "status": "failed",
                    "fail_reason": fail_reason,
                    "folds_expected": fold_count,
                    "folds_completed": 0,
                    "runtime_s": float(time.perf_counter() - combo_t0),
                }
            )
            continue

        combo_ok = True
        combo_fail_reason = None
        folds_completed = 0
        nearest_model = None

        for w in windows:
            fold_count_total += 1
            train_start_batch = int(w["train_start_batch"])
            train_end_batch = int(w["train_end_batch"])
            val_start_batch = int(w["val_start_batch"])
            val_end_batch = int(w["val_end_batch"])
            train_batch_ids = _batch_ids_from_window(
                w,
                "train",
                train_start_batch,
                train_end_batch,
            )
            val_batch_ids = _batch_ids_from_window(
                w,
                "val",
                val_start_batch,
                val_end_batch,
            )

            if (
                train_start_batch > int(train_end)
                or train_end_batch > int(train_end)
                or val_start_batch > int(train_end)
                or val_end_batch > int(train_end)
            ):
                combo_ok = False
                combo_fail_reason = "leakage_guard_fold_batch_exceeds_train_end"
                break

            train_data, train_fail = _slice_batch_ids(train_batch_ids)
            if train_fail is not None:
                combo_ok = False
                combo_fail_reason = f"{train_fail}:train"
                break
            val_data, val_fail = _slice_batch_ids(val_batch_ids)
            if val_fail is not None:
                combo_ok = False
                combo_fail_reason = f"{val_fail}:val"
                break

            X_train, y_train, _, _ = train_data
            X_val, y_val, ts_val, bid_val = val_data
            if len(y_train) < 50 or len(y_val) < 5:
                combo_ok = False
                combo_fail_reason = "insufficient_fold_samples"
                break
            if len(np.unique(y_train)) < 2:
                combo_ok = False
                combo_fail_reason = "insufficient_class_diversity_in_fold_train"
                break

            train_key = tuple(train_batch_ids)
            model = train_model_cache.get(train_key)
            if model is None:
                train_model_cache_misses += 1
                try:
                    model, _ = fit_catboost_with_fallback_stage1(
                        params=base_params,
                        iterations=baseline_iterations,
                        X_train=X_train,
                        y_train=y_train,
                        X_val=X_val,
                        y_val=y_val,
                    )
                except Exception as e:
                    combo_ok = False
                    combo_fail_reason = f"fold_train_failed:{e}"
                    break
                train_model_cache[train_key] = model
            else:
                train_model_cache_hits += 1

            if nearest_model is None:
                nearest_model = model

            pred_proba, y_pred = step_optimizer._to_full_class_proba_and_pred(
                model, model.predict_proba(X_val)
            )
            val_writer.write(
                combo_id=combo_id,
                fold_id=int(w["fold_id"]),
                scope="val_fold",
                action_key=action_key,
                candidate_source=candidate_source,
                probe_tier=probe_tier,
                discovered_from=discovered_from,
                timestamps=ts_val,
                batch_ids=bid_val,
                y_true=y_val,
                y_pred=y_pred,
                proba=pred_proba,
            )
            folds_completed += 1
            fold_count_completed += 1

        if combo_ok and nearest_model is not None and pred_X is not None and pred_y is not None:
            pred_proba, pred_labels = step_optimizer._to_full_class_proba_and_pred(
                nearest_model,
                nearest_model.predict_proba(pred_X),
            )
            pred_writer.write(
                combo_id=combo_id,
                fold_id=0,
                scope="pred_batch",
                action_key=action_key,
                candidate_source=candidate_source,
                probe_tier=probe_tier,
                discovered_from=discovered_from,
                timestamps=pred_ts if pred_ts is not None else np.array([], dtype="datetime64[ns]"),
                batch_ids=pred_bids if pred_bids is not None else np.array([], dtype=np.int32),
                y_true=pred_y,
                y_pred=pred_labels,
                proba=pred_proba,
            )

        status = "complete" if combo_ok else "failed"
        if not combo_ok:
            fail_reason = str(combo_fail_reason or "unknown")
            fail_counter[fail_reason] += 1
        else:
            fail_reason = None

        combo_records.append(
            {
                "combo_id": combo_id,
                "action_key": action_key,
                "fold_count": fold_count,
                "val_batches_per_fold": val_batches,
                "train_batches_per_fold": train_batches,
                "status": status,
                "fail_reason": fail_reason,
                "folds_expected": fold_count,
                "folds_completed": int(folds_completed),
                "runtime_s": float(time.perf_counter() - combo_t0),
                "candidate_source": str(candidate_source or "base_grid"),
                "probe_tier": int(probe_tier if probe_tier is not None else -1),
                "discovered_from": str(discovered_from or ""),
            }
        )

    val_writer.close()
    pred_writer.close()

    if combo_records:
        new_combo_df = pl.DataFrame(combo_records)
    else:
        new_combo_df = pl.DataFrame(
            {
                "combo_id": pl.Series([], dtype=pl.Int32),
                "action_key": pl.Series([], dtype=pl.Utf8),
                "fold_count": pl.Series([], dtype=pl.Int32),
                "val_batches_per_fold": pl.Series([], dtype=pl.Int32),
                "train_batches_per_fold": pl.Series([], dtype=pl.Int32),
                "status": pl.Series([], dtype=pl.Utf8),
                "fail_reason": pl.Series([], dtype=pl.Utf8),
                "folds_expected": pl.Series([], dtype=pl.Int32),
                "folds_completed": pl.Series([], dtype=pl.Int32),
                "runtime_s": pl.Series([], dtype=pl.Float64),
                "candidate_source": pl.Series([], dtype=pl.Utf8),
                "probe_tier": pl.Series([], dtype=pl.Int16),
                "discovered_from": pl.Series([], dtype=pl.Utf8),
            }
        )
    if append_mode and combo_index_path.exists():
        merged_combo_df = pl.concat(
            [pl.read_parquet(combo_index_path), new_combo_df],
            how="diagonal_relaxed",
        ).unique(subset=["action_key"], keep="first")
        combo_index_df = merged_combo_df.sort("combo_id")
    else:
        combo_index_df = new_combo_df
    combo_index_df.write_parquet(combo_index_path)

    if fold_window_records:
        new_fold_windows_df = pl.DataFrame(fold_window_records)
    else:
        new_fold_windows_df = pl.DataFrame(
            {
                "combo_id": pl.Series([], dtype=pl.Int32),
                "action_key": pl.Series([], dtype=pl.Utf8),
                "fold_id": pl.Series([], dtype=pl.Int16),
                "train_start_batch": pl.Series([], dtype=pl.Int32),
                "train_end_batch": pl.Series([], dtype=pl.Int32),
                "val_start_batch": pl.Series([], dtype=pl.Int32),
                "val_end_batch": pl.Series([], dtype=pl.Int32),
                "val_batch": pl.Series([], dtype=pl.Int32),
                "train_start_pos": pl.Series([], dtype=pl.Int32),
                "train_end_pos": pl.Series([], dtype=pl.Int32),
                "val_start_pos": pl.Series([], dtype=pl.Int32),
                "val_end_pos": pl.Series([], dtype=pl.Int32),
                "pred_pos": pl.Series([], dtype=pl.Int32),
                "train_batch_ids": pl.Series([], dtype=pl.List(pl.Int32)),
                "val_batch_ids": pl.Series([], dtype=pl.List(pl.Int32)),
                "train_batch_count": pl.Series([], dtype=pl.Int32),
                "val_batch_count": pl.Series([], dtype=pl.Int32),
                "window_is_sparse": pl.Series([], dtype=pl.Boolean),
                "candidate_source": pl.Series([], dtype=pl.Utf8),
                "probe_tier": pl.Series([], dtype=pl.Int16),
                "discovered_from": pl.Series([], dtype=pl.Utf8),
            }
        )
    if append_mode and fold_windows_path.exists():
        merged_fold_df = pl.concat(
            [pl.read_parquet(fold_windows_path), new_fold_windows_df],
            how="diagonal_relaxed",
        ).unique(
            subset=[
                "action_key",
                "fold_id",
                "train_start_batch",
                "train_end_batch",
                "val_start_batch",
                "val_end_batch",
            ],
            keep="first",
        )
        fold_windows_df = merged_fold_df.sort(["combo_id", "fold_id"])
    else:
        fold_windows_df = new_fold_windows_df
    fold_windows_df.write_parquet(fold_windows_path)

    if append_mode:
        def _merge_payload(old_path: Path, new_path: Path) -> int:
            if not new_path.exists():
                return 0
            new_df = pl.read_parquet(new_path)
            if old_path.exists():
                old_df = pl.read_parquet(old_path)
                merged = pl.concat([old_df, new_df], how="diagonal_relaxed").unique(
                    subset=["combo_id", "fold_id", "scope", "timestamp", "batch_id"],
                    keep="last",
                )
            else:
                merged = new_df
            merged.write_parquet(old_path)
            try:
                new_path.unlink()
            except Exception:
                pass
            return int(len(merged))

        val_rows_after_merge = _merge_payload(val_payload_path, val_new_path)
        pred_rows_after_merge = _merge_payload(pred_payload_path, pred_new_path)
    else:
        val_rows_after_merge = int(val_writer.row_count)
        pred_rows_after_merge = int(pred_writer.row_count)

    # Write pre-decision context in both json and parquet forms for easy
    # sequence-model dataset assembly.
    context_json_path = step_stage1_dir / "stage1_predecision_context.json"
    with open(context_json_path, "w") as f:
        json.dump(predecision_context, f, indent=2)

    context_row = {
        "train_end_batch": int(predecision_context["train_end_batch"]),
        "pred_batch": int(predecision_context["pred_batch"]),
        "target": str(predecision_context["target"]),
        "feature_target": str(predecision_context["feature_target"]),
        "n_classes": int(predecision_context["n_classes"]),
        "lookback_range_start_batch": int(predecision_context["lookback_range_start_batch"]),
        "lookback_range_end_batch": int(predecision_context["lookback_range_end_batch"]),
        "available_batches": int(predecision_context["available_batches"]),
        "lookback_rows": int(predecision_context["lookback_rows"]),
        "rows_per_batch_min": int(predecision_context["rows_per_batch_min"]),
        "rows_per_batch_median": int(predecision_context["rows_per_batch_median"]),
        "rows_per_batch_max": int(predecision_context["rows_per_batch_max"]),
        "recent_batches_n": int(predecision_context["recent_batches_n"]),
        "recent_batches_start": (
            int(predecision_context["recent_batches_start"])
            if predecision_context["recent_batches_start"] is not None
            else None
        ),
        "recent_batches_end": (
            int(predecision_context["recent_batches_end"])
            if predecision_context["recent_batches_end"] is not None
            else None
        ),
        "recent_rows": int(predecision_context["recent_rows"]),
        "pred_rows": int(predecision_context["pred_rows"]),
        "pred_timestamp_start": predecision_context["pred_timestamp_start"],
        "pred_timestamp_end": predecision_context["pred_timestamp_end"],
    }
    for c in range(int(cfg.n_classes)):
        context_row[f"lookback_class_count_{c}"] = int(predecision_context["class_counts_lookback"][str(c)])
        context_row[f"lookback_class_pct_{c}"] = float(predecision_context["class_pct_lookback"][str(c)])
        context_row[f"recent_class_count_{c}"] = int(predecision_context["class_counts_recent"][str(c)])
        context_row[f"recent_class_pct_{c}"] = float(predecision_context["class_pct_recent"][str(c)])
    context_parquet_path = step_stage1_dir / "stage1_predecision_context.parquet"
    pl.DataFrame([context_row]).write_parquet(context_parquet_path)

    combo_total = int(len(combo_index_df)) if len(combo_index_df) else int(len(combos))
    combo_completed = int((combo_index_df["status"] == "complete").sum()) if len(combo_index_df) else 0
    combo_failed = combo_total - combo_completed

    summary = {
        "window_selection_mode": "stage1_fold_cv_v2",
        "leakage_guard": "pass",
        "train_end_batch": int(train_end),
        "pred_batch": int(pred_batch),
        "target": str(cfg.target),
        "feature_target": str(cfg.feature_target or cfg.target),
        "n_classes": int(cfg.n_classes),
        "combo_count_total": combo_total,
        "combo_count_completed": combo_completed,
        "combo_count_failed": combo_failed,
        "combo_count_new_this_run": int(len(new_combo_df)),
        "append_mode": bool(append_mode),
        "candidate_source": str(candidate_source or "base_grid"),
        "probe_tier": int(probe_tier if probe_tier is not None else -1),
        "discovered_from": str(discovered_from or ""),
        "fold_windows_total": int(fold_count_total),
        "fold_windows_completed": int(fold_count_completed),
        "val_payload_rows": int(val_rows_after_merge),
        "pred_payload_rows": int(pred_rows_after_merge),
        "train_model_cache_hits": int(train_model_cache_hits),
        "train_model_cache_misses": int(train_model_cache_misses),
        "train_model_cache_unique": int(len(train_model_cache)),
        "lookback_range_start_batch": int(range_start),
        "lookback_range_end_batch": int(train_end),
        "stage1_grid": {
            "folds_min": int(getattr(win, "stage1_folds_min", 1)),
            "folds_max": int(getattr(win, "stage1_folds_max", 1)),
            "fold_grid": (
                sorted({int(v) for v in (getattr(win, "stage1_fold_grid", []) or [])})
            ),
            "val_batches_grid": _stage1_val_values(win),
            "triplet_grid": [
                {
                    "fold_count": int(f),
                    "val_batches_per_fold": int(v),
                    "train_batches_per_fold": int(t),
                }
                for (f, v, t) in _stage1_triplet_values(win)
            ],
            "pair_grid": [
                {
                    "val_batches_per_fold": int(v),
                    "train_batches_per_fold": int(t),
                }
                for (v, t) in _stage1_pair_values(win)
            ],
            "train_multiplier_grid": list(getattr(win, "stage1_train_multiplier_grid", []) or []),
            "train_batches_grid": list(getattr(win, "stage1_train_batches_grid", []) or []),
        },
        "fail_reasons": dict(fail_counter),
        "runtime_s": float(time.perf_counter() - t0),
    }
    step_summary_path = step_stage1_dir / "stage1_step_summary.json"
    with open(step_summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    runtime_profile = {
        "combo_runtime_top10": sorted(
            [
                {
                    "combo_id": int(r["combo_id"]),
                    "runtime_s": float(r["runtime_s"]),
                    "status": str(r["status"]),
                }
                for r in combo_records
                if r.get("runtime_s") is not None
            ],
            key=lambda r: float(r["runtime_s"]),
            reverse=True,
        )[:10],
        "summary": summary,
    }
    runtime_profile_path = step_stage1_dir / "stage1_runtime_profile.json"
    with open(runtime_profile_path, "w") as f:
        json.dump(runtime_profile, f, indent=2)

    return {
        "summary": summary,
        "artifacts": {
            "stage1_step_summary": str(step_summary_path),
            "stage1_combo_index": str(combo_index_path),
            "stage1_fold_windows": str(fold_windows_path),
            "stage1_val_predictions": str(step_stage1_dir / "stage1_val_predictions.parquet"),
            "stage1_pred_batch_predictions": str(step_stage1_dir / "stage1_pred_batch_predictions.parquet"),
            "stage1_predecision_context": str(context_json_path),
            "stage1_predecision_context_parquet": str(context_parquet_path),
            "stage1_runtime_profile": str(runtime_profile_path),
        },
        "config_snapshot": {
            "config": asdict(cfg),
            "window_space": asdict(win),
            "feature_space": asdict(step_optimizer.feature_space),
            "model_space": asdict(step_optimizer.model_space),
        },
    }
