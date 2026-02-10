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
    get_feature_columns,
    load_batch,
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


def build_stage1_combo_grid(window_space: Any) -> list[dict[str, int]]:
    folds_min = int(max(1, getattr(window_space, "stage1_folds_min", 1)))
    folds_max = int(max(folds_min, getattr(window_space, "stage1_folds_max", folds_min)))
    fold_values = list(range(folds_min, folds_max + 1))
    combos: list[dict[str, int]] = []
    combo_id = 0
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
    range_start = max(1, int(train_end) - lookback_max + 1)
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
    range_cache: dict[tuple[int, int], tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = {}

    def _slice_batch_range(start_batch: int, end_batch: int):
        key = (int(start_batch), int(end_batch))
        cached = range_cache.get(key)
        if cached is not None:
            return cached, None
        missing = [b for b in range(key[0], key[1] + 1) if b not in available_batch_set]
        if missing:
            return None, f"missing_batch:{','.join(str(b) for b in missing)}"
        start_idx = int(batch_bounds[key[0]][0])
        end_idx = int(batch_bounds[key[1]][1])
        sliced = (
            X_compact[start_idx:end_idx],
            y_compact[start_idx:end_idx],
            ts_compact[start_idx:end_idx],
            bid_compact[start_idx:end_idx],
        )
        range_cache[key] = sliced
        return sliced, None

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
    except Exception:
        pred_X = None
        pred_y = None
        pred_ts = None
        pred_bids = None

    combos = build_stage1_combo_grid(win)
    val_writer = _PayloadWriter(step_stage1_dir / "stage1_val_predictions.parquet", cfg.n_classes)
    pred_writer = _PayloadWriter(
        step_stage1_dir / "stage1_pred_batch_predictions.parquet",
        cfg.n_classes,
    )

    combo_records: list[dict[str, Any]] = []
    fold_window_records: list[dict[str, Any]] = []
    fail_counter: Counter[str] = Counter()

    train_model_cache: dict[tuple[int, int], Any] = {}
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
        combo_t0 = time.perf_counter()

        windows = step_optimizer._build_stage1_fold_windows(
            train_end=int(train_end),
            fold_count=fold_count,
            train_batches_per_fold=train_batches,
            val_batches_per_fold=val_batches,
            min_batch=min_batch,
        )
        for w in windows:
            fold_window_records.append(
                {
                    "combo_id": combo_id,
                    "fold_id": int(w["fold_id"]),
                    "train_start_batch": int(w["train_start_batch"]),
                    "train_end_batch": int(w["train_end_batch"]),
                    "val_start_batch": int(w["val_start_batch"]),
                    "val_end_batch": int(w["val_end_batch"]),
                    "val_batch": int(w["val_batch"]),
                }
            )

        if len(windows) < fold_count:
            fail_reason = "not_enough_history_for_requested_folds"
            fail_counter[fail_reason] += 1
            combo_records.append(
                {
                    "combo_id": combo_id,
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

            if (
                train_start_batch > int(train_end)
                or train_end_batch > int(train_end)
                or val_start_batch > int(train_end)
                or val_end_batch > int(train_end)
            ):
                combo_ok = False
                combo_fail_reason = "leakage_guard_fold_batch_exceeds_train_end"
                break

            train_data, train_fail = _slice_batch_range(train_start_batch, train_end_batch)
            if train_fail is not None:
                combo_ok = False
                combo_fail_reason = f"{train_fail}:train"
                break
            val_data, val_fail = _slice_batch_range(val_start_batch, val_end_batch)
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

            train_key = (train_start_batch, train_end_batch)
            model = train_model_cache.get(train_key)
            if model is None:
                train_model_cache_misses += 1
                try:
                    model, _ = step_optimizer._fit_catboost_with_fallback(
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
                "fold_count": fold_count,
                "val_batches_per_fold": val_batches,
                "train_batches_per_fold": train_batches,
                "status": status,
                "fail_reason": fail_reason,
                "folds_expected": fold_count,
                "folds_completed": int(folds_completed),
                "runtime_s": float(time.perf_counter() - combo_t0),
            }
        )

    val_writer.close()
    pred_writer.close()

    combo_index_df = pl.DataFrame(combo_records)
    combo_index_path = step_stage1_dir / "stage1_combo_index.parquet"
    combo_index_df.write_parquet(combo_index_path)

    fold_windows_df = pl.DataFrame(fold_window_records)
    fold_windows_path = step_stage1_dir / "stage1_fold_windows.parquet"
    fold_windows_df.write_parquet(fold_windows_path)

    combo_total = int(len(combos))
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
        "fold_windows_total": int(fold_count_total),
        "fold_windows_completed": int(fold_count_completed),
        "val_payload_rows": int(val_writer.row_count),
        "pred_payload_rows": int(pred_writer.row_count),
        "train_model_cache_hits": int(train_model_cache_hits),
        "train_model_cache_misses": int(train_model_cache_misses),
        "train_model_cache_unique": int(len(train_model_cache)),
        "lookback_range_start_batch": int(range_start),
        "lookback_range_end_batch": int(train_end),
        "stage1_grid": {
            "folds_min": int(getattr(win, "stage1_folds_min", 1)),
            "folds_max": int(getattr(win, "stage1_folds_max", 1)),
            "val_batches_grid": _stage1_val_values(win),
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
            "stage1_runtime_profile": str(runtime_profile_path),
        },
        "config_snapshot": {
            "config": asdict(cfg),
            "window_space": asdict(win),
            "feature_space": asdict(step_optimizer.feature_space),
            "model_space": asdict(step_optimizer.model_space),
        },
    }

