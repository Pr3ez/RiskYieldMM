"""
Stage-1 Reward Builder (CatBoost)
=================================

Offline utility that converts Stage-1 raw payload artifacts into a unified
per-combo reward table.

This module is intentionally independent from Stage-1 runtime execution.
"""

from __future__ import annotations

import json
import math
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from scripts.project_paths import resolve_project_root


def _resolve_stage1_run_dir(run_id_or_path: str | Path, project_root: Path) -> Path:
    maybe_path = Path(run_id_or_path)
    if maybe_path.exists():
        return maybe_path
    run_dir = project_root / "data" / "htf_backtest_results" / str(run_id_or_path)
    if run_dir.exists():
        return run_dir
    raise FileNotFoundError(
        f"Stage-1 run not found from '{run_id_or_path}'. "
        f"Checked '{maybe_path}' and '{run_dir}'."
    )


def _load_unit_meta_from_snapshot(unit_dir: Path) -> tuple[int, list[str], str]:
    snapshots = sorted(unit_dir.glob("batch_*/stage1/stage1_config_snapshot.json"))
    if not snapshots:
        raise FileNotFoundError(f"No stage1_config_snapshot.json in {unit_dir}")
    with open(snapshots[0], "r") as f:
        snap = json.load(f)

    cfg = snap.get("config", {})
    n_classes = int(cfg.get("n_classes", 0))
    class_names = [str(v) for v in cfg.get("class_names", [])]
    target = str(cfg.get("target", unit_dir.name))

    if n_classes <= 1:
        raise ValueError(f"Invalid n_classes in {snapshots[0]}: {n_classes}")
    if len(class_names) != n_classes:
        class_names = [f"class_{i}" for i in range(n_classes)]
    return n_classes, class_names, target


def _detect_direction_indices(class_names: list[str]) -> tuple[set[int], set[int]]:
    up = set()
    down = set()
    for i, name in enumerate(class_names):
        token = str(name).upper()
        if "UP" in token:
            up.add(i)
        if "DOWN" in token:
            down.add(i)
    return up, down


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        v = float(value)
    except Exception:
        return None
    if not math.isfinite(v):
        return None
    return v


def _accuracy(y_true: np.ndarray, y_pred: np.ndarray) -> float | None:
    if y_true.size == 0:
        return None
    return float((y_true == y_pred).mean())


def _f1_macro(y_true: np.ndarray, y_pred: np.ndarray, n_classes: int) -> float | None:
    if y_true.size == 0:
        return None
    y_true = y_true.astype(np.int32, copy=False)
    y_pred = y_pred.astype(np.int32, copy=False)
    valid = (
        (y_true >= 0)
        & (y_true < int(n_classes))
        & (y_pred >= 0)
        & (y_pred < int(n_classes))
    )
    if int(valid.sum()) == 0:
        return None

    cm = np.zeros((int(n_classes), int(n_classes)), dtype=np.int64)
    np.add.at(cm, (y_true[valid], y_pred[valid]), 1)

    tp = np.diag(cm).astype(np.float64)
    fp = cm.sum(axis=0).astype(np.float64) - tp
    fn = cm.sum(axis=1).astype(np.float64) - tp

    precision = np.divide(tp, tp + fp, out=np.zeros_like(tp), where=(tp + fp) > 0)
    recall = np.divide(tp, tp + fn, out=np.zeros_like(tp), where=(tp + fn) > 0)
    f1 = np.divide(
        2 * precision * recall,
        precision + recall,
        out=np.zeros_like(precision),
        where=(precision + recall) > 0,
    )
    return float(np.mean(f1))


def _cross_direction_error(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    up_indices: set[int],
    down_indices: set[int],
) -> float | None:
    if y_true.size == 0 or not up_indices or not down_indices:
        return None

    true_up = np.isin(y_true, list(up_indices))
    true_down = np.isin(y_true, list(down_indices))
    pred_up = np.isin(y_pred, list(up_indices))
    pred_down = np.isin(y_pred, list(down_indices))

    mask = true_up | true_down
    denom = int(mask.sum())
    if denom <= 0:
        return None

    wrong = (true_up & pred_down) | (true_down & pred_up)
    return float((wrong & mask).sum() / denom)


def _logloss(y_true: np.ndarray, proba: np.ndarray, n_classes: int) -> float | None:
    if y_true.size == 0:
        return None
    if proba.ndim != 2 or proba.shape[0] != y_true.size:
        return None

    y_true = y_true.astype(np.int32, copy=False)
    valid = (y_true >= 0) & (y_true < int(n_classes))
    if int(valid.sum()) == 0:
        return None

    rows = np.where(valid)[0]
    cols = y_true[valid]
    picked = proba[rows, cols]
    picked = np.clip(picked, 1e-15, 1.0 - 1e-15)
    return float(-np.mean(np.log(picked)))


def _extract_proba(grp: pl.DataFrame, n_classes: int) -> np.ndarray | None:
    cols = [c for c in grp.columns if c.startswith("prob_class_")]
    if not cols:
        return None

    def _class_id(col: str) -> int:
        try:
            return int(col.split("prob_class_")[1])
        except Exception:
            return 10**9

    cols = sorted(cols, key=_class_id)
    expected = [f"prob_class_{i}" for i in range(int(n_classes))]
    if cols != expected:
        return None

    arrays = [grp[c].to_numpy().astype(np.float64, copy=False) for c in cols]
    return np.column_stack(arrays)


def _combo_metrics_from_payload(
    payload_df: pl.DataFrame,
    n_classes: int,
    up_idx: set[int],
    down_idx: set[int],
) -> dict[int, dict[str, float | None]]:
    out: dict[int, dict[str, float | None]] = {}
    if payload_df.is_empty():
        return out

    required = {"combo_id", "y_true", "y_pred"}
    if not required.issubset(set(payload_df.columns)):
        return out

    for combo_key, grp in payload_df.group_by("combo_id"):
        combo_id = int(combo_key[0] if isinstance(combo_key, tuple) else combo_key)
        y_true = grp["y_true"].to_numpy().astype(np.int32, copy=False)
        y_pred = grp["y_pred"].to_numpy().astype(np.int32, copy=False)
        proba = _extract_proba(grp, n_classes=n_classes)

        out[combo_id] = {
            "accuracy": _accuracy(y_true, y_pred),
            "macro_f1": _f1_macro(y_true, y_pred, n_classes=n_classes),
            "cross_direction_error": _cross_direction_error(
                y_true,
                y_pred,
                up_indices=up_idx,
                down_indices=down_idx,
            ),
            "logloss": _logloss(y_true, proba, n_classes=n_classes)
            if proba is not None
            else None,
            "n_rows": float(int(y_true.size)),
        }
    return out


def _reward_from_metrics(metrics: dict[str, float | None], weights: dict[str, float]) -> float | None:
    macro_f1 = _safe_float(metrics.get("macro_f1"))
    cross_err = _safe_float(metrics.get("cross_direction_error"))
    accuracy = _safe_float(metrics.get("accuracy"))
    logloss = _safe_float(metrics.get("logloss"))

    parts: list[float] = []
    if macro_f1 is not None:
        parts.append(float(weights.get("macro_f1", 1.0)) * macro_f1)
    if cross_err is not None:
        parts.append(float(weights.get("cross_direction_error", 1.0)) * (-cross_err))
    if accuracy is not None:
        parts.append(float(weights.get("accuracy", 0.0)) * accuracy)
    if logloss is not None:
        parts.append(float(weights.get("logloss", 0.0)) * (-logloss))

    if not parts:
        return None
    return float(np.sum(parts))


def build_stage1_reward_table(
    *,
    run_id_or_path: str | Path,
    project_root: str | Path | None = None,
    model_name: str = "catboost",
    selection_source: str = "prediction",
    reward_weights: dict[str, float] | None = None,
    write_latest: bool = True,
) -> dict[str, Any]:
    """
    Build Stage-1 reward tables from raw payload artifacts.

    selection_source:
    - "prediction": rank/label combos by prediction-batch reward
    - "validation": rank/label combos by fold-validation reward
    """
    selection_source = str(selection_source).strip().lower()
    if selection_source not in {"prediction", "validation"}:
        raise ValueError(
            f"selection_source must be 'prediction' or 'validation', got {selection_source!r}"
        )

    weights = {
        "macro_f1": 1.0,
        "cross_direction_error": 1.0,
        "accuracy": 0.0,
        "logloss": 0.0,
    }
    if reward_weights:
        weights.update({k: float(v) for k, v in reward_weights.items()})

    project_root_path = (
        Path(project_root).expanduser().resolve()
        if project_root is not None
        else resolve_project_root(Path(__file__))
    )
    run_dir = _resolve_stage1_run_dir(run_id_or_path, project_root=project_root_path)
    run_id = run_dir.name

    model_dir = run_dir / model_name
    if not model_dir.exists():
        raise FileNotFoundError(f"Model directory not found: {model_dir}")

    rows: list[dict[str, Any]] = []

    for tf_dir in sorted(model_dir.iterdir()):
        if not tf_dir.is_dir():
            continue
        tf = tf_dir.name
        for target_dir in sorted(tf_dir.iterdir()):
            if not target_dir.is_dir():
                continue

            unit = f"{tf}/{target_dir.name}"
            try:
                n_classes, class_names, target_col = _load_unit_meta_from_snapshot(target_dir)
            except Exception:
                continue

            up_idx, down_idx = _detect_direction_indices(class_names)

            for batch_dir in sorted(target_dir.glob("batch_*")):
                step_stage1 = batch_dir / "stage1"
                combo_path = step_stage1 / "stage1_combo_index.parquet"
                val_path = step_stage1 / "stage1_val_predictions.parquet"
                pred_path = step_stage1 / "stage1_pred_batch_predictions.parquet"
                if not (combo_path.exists() and val_path.exists() and pred_path.exists()):
                    continue

                try:
                    step_id = int(batch_dir.name.split("_")[1])
                except Exception:
                    continue

                combo_df = pl.read_parquet(combo_path)
                if "status" in combo_df.columns:
                    combo_df = combo_df.filter(pl.col("status") == "complete")
                if combo_df.is_empty():
                    continue

                combo_df = combo_df.select(
                    [
                        "combo_id",
                        "action_key",
                        "fold_count",
                        "val_batches_per_fold",
                        "train_batches_per_fold",
                    ]
                )

                val_df = pl.read_parquet(val_path)
                pred_df = pl.read_parquet(pred_path)

                val_metrics = _combo_metrics_from_payload(
                    val_df,
                    n_classes=n_classes,
                    up_idx=up_idx,
                    down_idx=down_idx,
                )
                pred_metrics = _combo_metrics_from_payload(
                    pred_df,
                    n_classes=n_classes,
                    up_idx=up_idx,
                    down_idx=down_idx,
                )

                for combo_row in combo_df.iter_rows(named=True):
                    combo_id = int(combo_row["combo_id"])
                    vm = val_metrics.get(combo_id, {})
                    pm = pred_metrics.get(combo_id, {})

                    val_reward = _reward_from_metrics(vm, weights)
                    pred_reward = _reward_from_metrics(pm, weights)
                    selected_reward = pred_reward if selection_source == "prediction" else val_reward

                    rows.append(
                        {
                            "unit": unit,
                            "timeframe": tf,
                            "target": target_col,
                            "step": int(step_id),
                            "combo_id": combo_id,
                            "action_key": str(combo_row["action_key"]),
                            "fold_count": int(combo_row["fold_count"]),
                            "val_batches_per_fold": int(combo_row["val_batches_per_fold"]),
                            "train_batches_per_fold": int(combo_row["train_batches_per_fold"]),
                            "val_accuracy": _safe_float(vm.get("accuracy")),
                            "val_macro_f1": _safe_float(vm.get("macro_f1")),
                            "val_cross_direction_error": _safe_float(vm.get("cross_direction_error")),
                            "val_logloss": _safe_float(vm.get("logloss")),
                            "val_rows": int(vm.get("n_rows") or 0),
                            "pred_accuracy": _safe_float(pm.get("accuracy")),
                            "pred_macro_f1": _safe_float(pm.get("macro_f1")),
                            "pred_cross_direction_error": _safe_float(pm.get("cross_direction_error")),
                            "pred_logloss": _safe_float(pm.get("logloss")),
                            "pred_rows": int(pm.get("n_rows") or 0),
                            "reward_validation": _safe_float(val_reward),
                            "reward_prediction": _safe_float(pred_reward),
                            "selected_reward": _safe_float(selected_reward),
                            "selection_source": selection_source,
                        }
                    )

    if not rows:
        raise ValueError("No Stage-1 payload data found to build reward table")

    reward_df = pl.DataFrame(rows)
    reward_df = reward_df.with_columns(
        pl.col("selected_reward").fill_null(float("-inf")).alias("_selected_reward")
    )
    reward_df = reward_df.with_columns(
        [
            pl.col("_selected_reward")
            .rank("dense", descending=True)
            .over(["unit", "step"])
            .cast(pl.Int32)
            .alias("reward_rank"),
            (
                pl.col("_selected_reward")
                == pl.col("_selected_reward").max().over(["unit", "step"])
            ).alias("is_step_best"),
        ]
    ).drop("_selected_reward")

    combo_stats_df = (
        reward_df.group_by(
            [
                "unit",
                "timeframe",
                "target",
                "action_key",
                "fold_count",
                "val_batches_per_fold",
                "train_batches_per_fold",
            ]
        )
        .agg(
            [
                pl.len().alias("n_records"),
                pl.col("step").n_unique().alias("steps_covered"),
                pl.col("selected_reward").mean().alias("selected_reward_mean"),
                pl.col("selected_reward").std().fill_null(0.0).alias("selected_reward_std"),
                pl.col("reward_validation").mean().alias("reward_validation_mean"),
                pl.col("reward_prediction").mean().alias("reward_prediction_mean"),
                pl.col("pred_macro_f1").mean().alias("pred_macro_f1_mean"),
                pl.col("pred_cross_direction_error").mean().alias("pred_cross_direction_error_mean"),
                pl.col("val_macro_f1").mean().alias("val_macro_f1_mean"),
                pl.col("val_cross_direction_error").mean().alias("val_cross_direction_error_mean"),
                pl.col("is_step_best").sum().cast(pl.Int32).alias("step_best_hits"),
            ]
        )
        .sort(["unit", "selected_reward_mean"], descending=[False, True])
    )

    unit_stats_df = (
        reward_df.group_by(["unit", "timeframe", "target"])
        .agg(
            [
                pl.col("step").n_unique().alias("steps"),
                pl.len().alias("rows"),
                pl.col("selected_reward").mean().alias("selected_reward_mean"),
                pl.col("reward_validation").mean().alias("reward_validation_mean"),
                pl.col("reward_prediction").mean().alias("reward_prediction_mean"),
            ]
        )
        .sort("unit")
    )

    meta_root = project_root_path / "data" / "htf_backtest_results" / "stage1_meta" / model_name
    out_dir = meta_root / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    reward_table_path = out_dir / "reward_table.parquet"
    combo_stats_path = out_dir / "reward_combo_stats.parquet"
    unit_stats_path = out_dir / "reward_unit_stats.parquet"

    reward_df.write_parquet(reward_table_path)
    combo_stats_df.write_parquet(combo_stats_path)
    unit_stats_df.write_parquet(unit_stats_path)

    metadata: dict[str, Any] = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "source_run_id": run_id,
        "source_run_path": str(run_dir),
        "model_name": model_name,
        "selection_source": selection_source,
        "reward_weights": weights,
        "row_count": int(len(reward_df)),
        "unit_count": int(reward_df["unit"].n_unique()),
        "step_count": int(
            reward_df.select(
                pl.struct(["unit", "step"]).n_unique().alias("n_step_pairs")
            )["n_step_pairs"][0]
        ),
        "artifacts": {
            "reward_table": str(reward_table_path),
            "reward_combo_stats": str(combo_stats_path),
            "reward_unit_stats": str(unit_stats_path),
        },
    }

    metadata_path = out_dir / "reward_metadata.json"
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)

    if write_latest:
        latest_path = meta_root / "latest_reward_metadata.json"
        shutil.copyfile(metadata_path, latest_path)
        metadata["artifacts"]["latest_reward_metadata"] = str(latest_path)

    return metadata


def load_stage1_reward_metadata(path: str | Path) -> dict[str, Any]:
    with open(path, "r") as f:
        return json.load(f)


__all__ = [
    "build_stage1_reward_table",
    "load_stage1_reward_metadata",
]
