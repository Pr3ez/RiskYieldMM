#!/usr/bin/env python3
"""HTF walk-forward diagnostics and improvement analysis for six multiregime roots.

This runner ties together:
- current production HTF artifacts
- latest Stage-1 walk-forward outputs
- Stage-1 Step-2 feature-pruning / importance analysis
- latest causal ensemble analysis outputs

Scope:
- `1m / target_4class`
- roots: `8h/24h/7d` and families `B/C`
- current roots first
- no-lookahead only
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
from sklearn.metrics import confusion_matrix, f1_score, precision_recall_fscore_support

PROJECT_ROOT = Path("/media/przem/linux_data/RiskYieldMM (Copy)")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.feature_engineering.htf_feature_acceptance import (
    describe_final_output_exclusions,
)
from scripts.htf_backtest.catboost.stage1_step2 import run_stage1_step2_feature_pruning


CLASS_NAMES_4 = [
    "DOWN_BALANCED",
    "DOWN_EXPANSION",
    "UP_BALANCED",
    "UP_EXPANSION",
]
N_CLASSES = 4
TARGET_COL = "target_4class"
MODEL_NAME = "catboost"
TF = "1m"
DEFAULT_SELECTION_SCOPE = "winner_only"
DEFAULT_TOPK_ACTION_KEYS = 3
FULL_COVERAGE_THRESHOLD = 0.999
DEFAULT_FEATURE_IMPORTANCE_TYPES = ["PredictionValuesChange", "LossFunctionChange"]

STAGE1_CB_BASE_PARAMS = {
    "loss_function": "MultiClass",
    "eval_metric": "MultiClass",
    "task_type": "GPU",
    "devices": "0",
    "random_seed": 42,
    "allow_writing_files": False,
    "verbose": False,
    "thread_count": -1,
    "bootstrap_type": "Bernoulli",
}

ROOTS: dict[str, dict[str, str]] = {
    "8h/B": {
        "run_id": "stage1_catboost_8h_b_live",
        "features_dir": "data/htf_with_helpers",
        "labels_dir": "data/htf_4class_labels",
        "unit_dir": "data/htf_backtest_results/stage1_catboost_8h_b_live/catboost/1m/target_4class",
    },
    "8h/C": {
        "run_id": "stage1_catboost_8h_c_live",
        "features_dir": "data/htf_with_helpers_shift4h",
        "labels_dir": "data/htf_4class_labels_shift4h",
        "unit_dir": "data/htf_backtest_results/stage1_catboost_8h_c_live/catboost/1m/target_4class",
    },
    "24h/B": {
        "run_id": "stage1_catboost_24h_b_live",
        "features_dir": "data/htf_with_helpers_24h",
        "labels_dir": "data/htf_4class_labels_24h",
        "unit_dir": "data/htf_backtest_results/stage1_catboost_24h_b_live/catboost/1m/target_4class",
    },
    "24h/C": {
        "run_id": "stage1_catboost_24h_c_live",
        "features_dir": "data/htf_with_helpers_24h_shift12h",
        "labels_dir": "data/htf_4class_labels_24h_shift12h",
        "unit_dir": "data/htf_backtest_results/stage1_catboost_24h_c_live/catboost/1m/target_4class",
    },
    "7d/B": {
        "run_id": "stage1_catboost_7d_b_live",
        "features_dir": "data/htf_with_helpers_7d",
        "labels_dir": "data/htf_4class_labels_7d",
        "unit_dir": "data/htf_backtest_results/stage1_catboost_7d_b_live/catboost/1m/target_4class",
    },
    "7d/C": {
        "run_id": "stage1_catboost_7d_c_live",
        "features_dir": "data/htf_with_helpers_7d_shift84h",
        "labels_dir": "data/htf_4class_labels_7d_shift84h",
        "unit_dir": "data/htf_backtest_results/stage1_catboost_7d_c_live/catboost/1m/target_4class",
    },
}


@dataclass(frozen=True)
class RootConfig:
    root: str
    run_id: str
    features_dir: Path
    labels_dir: Path
    unit_dir: Path


def _timestamp_tag() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _root_slug(root: str) -> str:
    return root.lower().replace("/", "_")


def _iter_batch_dirs(unit_dir: Path) -> list[Path]:
    return sorted(
        [p for p in unit_dir.glob("batch_*") if p.is_dir()],
        key=lambda p: int(p.name.split("_")[1]),
    )


def _metric_direction(metric_name: str) -> str:
    token = str(metric_name).strip().lower()
    return "minimize" if token in {"log_loss", "cross_direction_error"} else "maximize"


def _compute_cross_direction_error(y_true: np.ndarray, y_pred: np.ndarray) -> float | None:
    if y_true.size == 0:
        return None
    true_up = y_true >= 2
    true_down = y_true < 2
    pred_up = y_pred >= 2
    pred_down = y_pred < 2
    mask = true_up | true_down
    denom = int(mask.sum())
    if denom <= 0:
        return None
    wrong = (true_up & pred_down) | (true_down & pred_up)
    return float((wrong & mask).sum() / denom)


def _compute_cross_direction_error_from_dirs(
    true_dir: np.ndarray,
    pred_dir: np.ndarray,
) -> float | None:
    if true_dir.size == 0:
        return None
    true_dir = true_dir.astype(np.int8, copy=False)
    pred_dir = pred_dir.astype(np.int8, copy=False)
    return float((true_dir != pred_dir).mean())


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        value = float(value)
    except Exception:
        return None
    if math.isnan(value) or math.isinf(value):
        return None
    return value


def _find_latest_causal_run_dir(project_root: Path) -> Path:
    base = project_root / "test_output" / "htf_causal_multiregime_method_analysis"
    candidates = sorted([p for p in base.iterdir() if p.is_dir()], key=lambda p: p.name)
    if not candidates:
        raise FileNotFoundError(f"No causal analysis runs found under {base}")
    return candidates[-1]


def _build_root_configs(project_root: Path) -> dict[str, RootConfig]:
    out: dict[str, RootConfig] = {}
    for root, cfg in ROOTS.items():
        out[root] = RootConfig(
            root=root,
            run_id=str(cfg["run_id"]),
            features_dir=(project_root / cfg["features_dir"]).resolve(),
            labels_dir=(project_root / cfg["labels_dir"]).resolve(),
            unit_dir=(project_root / cfg["unit_dir"]).resolve(),
        )
    return out


def _parse_csv_tokens(raw: str) -> list[str]:
    return [token.strip() for token in str(raw).split(",") if token.strip()]


def _unique_eval_truth_rows(pred_rows: pl.DataFrame, eval_batches: set[int]) -> pl.DataFrame:
    if pred_rows.is_empty() or not eval_batches:
        return pl.DataFrame(
            {
                "pred_batch": [],
                "timestamp": [],
                "batch_id": [],
                "y_true": [],
            }
        )
    return (
        pred_rows.filter(pl.col("pred_batch").is_in(sorted(eval_batches)))
        .select(["pred_batch", "timestamp", "batch_id", "y_true"])
        .unique(subset=["pred_batch", "timestamp", "batch_id"], keep="first")
        .sort(["pred_batch", "timestamp", "batch_id"])
    )


def _detect_probability_columns(df: pl.DataFrame) -> tuple[list[str] | None, str]:
    for cols, mode in [
        ([f"prob_class_{i}" for i in range(N_CLASSES)], "stage1_combo_probs"),
        ([f"hedge_p{i}" for i in range(N_CLASSES)], "hedge_probs"),
        ([f"p_dma_c{i}" for i in range(N_CLASSES)], "dma_probs"),
        ([f"score_c{i}" for i in range(N_CLASSES)], "classspec_scores"),
        ([f"p{i}" for i in range(N_CLASSES)], "direct_probs"),
    ]:
        if all(c in df.columns for c in cols):
            return cols, mode
    return None, "deterministic_proxy"


def _probability_arrays(
    df: pl.DataFrame,
    *,
    prediction_col: str,
    prediction_type: str,
) -> tuple[np.ndarray | None, np.ndarray | None, str]:
    prob_cols, mode = _detect_probability_columns(df)
    class_probs: np.ndarray | None = None
    direction_probs: np.ndarray | None = None

    if prob_cols is not None:
        class_probs = df.select(prob_cols).to_numpy().astype(np.float64, copy=False)
        row_sum = class_probs.sum(axis=1, keepdims=True)
        row_sum[row_sum <= 0] = 1.0
        class_probs = class_probs / row_sum
        direction_probs = np.column_stack(
            [class_probs[:, 0] + class_probs[:, 1], class_probs[:, 2] + class_probs[:, 3]]
        )
        return class_probs, direction_probs, mode

    if prediction_type == "direction" and {"p_down", "p_up"}.issubset(set(df.columns)):
        direction_probs = (
            df.select(["p_down", "p_up"]).to_numpy().astype(np.float64, copy=False)
        )
        row_sum = direction_probs.sum(axis=1, keepdims=True)
        row_sum[row_sum <= 0] = 1.0
        direction_probs = direction_probs / row_sum
        return class_probs, direction_probs, "direction_probs"

    if prediction_type == "class" and prediction_col in df.columns:
        pred = df[prediction_col].to_numpy().astype(np.int32, copy=False)
        class_probs = np.full((len(pred), N_CLASSES), 1e-12, dtype=np.float64)
        valid_mask = (pred >= 0) & (pred < N_CLASSES)
        class_probs[np.arange(len(pred))[valid_mask], pred[valid_mask]] = 1.0 - 3e-12
        direction_probs = np.column_stack(
            [class_probs[:, 0] + class_probs[:, 1], class_probs[:, 2] + class_probs[:, 3]]
        )
        return class_probs, direction_probs, mode

    if prediction_type == "direction" and prediction_col in df.columns:
        pred_dir = df[prediction_col].to_numpy().astype(np.int32, copy=False)
        direction_probs = np.full((len(pred_dir), 2), 1e-12, dtype=np.float64)
        valid_mask = (pred_dir >= 0) & (pred_dir <= 1)
        direction_probs[np.arange(len(pred_dir))[valid_mask], pred_dir[valid_mask]] = 1.0 - 1e-12
        return class_probs, direction_probs, mode

    return None, None, "missing"


def _multiclass_brier(y_true: np.ndarray, probs: np.ndarray) -> float:
    one_hot = np.zeros_like(probs, dtype=np.float64)
    one_hot[np.arange(len(y_true)), y_true.astype(int)] = 1.0
    return float(np.mean(np.sum((probs - one_hot) ** 2, axis=1)))


def _binary_brier(y_true: np.ndarray, probs_up: np.ndarray) -> float:
    return float(np.mean((probs_up - y_true.astype(np.float64)) ** 2))


def _confidence_bucket_summary(
    confidence: np.ndarray,
    correct: np.ndarray,
    *,
    bucket_count: int = 10,
) -> list[dict[str, Any]]:
    if confidence.size == 0:
        return []
    confidence = np.clip(confidence.astype(np.float64, copy=False), 0.0, 1.0)
    edges = np.linspace(0.0, 1.0, bucket_count + 1)
    rows: list[dict[str, Any]] = []
    for idx in range(bucket_count):
        left = float(edges[idx])
        right = float(edges[idx + 1])
        if idx == bucket_count - 1:
            mask = (confidence >= left) & (confidence <= right)
        else:
            mask = (confidence >= left) & (confidence < right)
        n = int(mask.sum())
        if n <= 0:
            continue
        rows.append(
            {
                "bucket_idx": idx + 1,
                "confidence_min": left,
                "confidence_max": right,
                "count": n,
                "mean_confidence": float(confidence[mask].mean()),
                "accuracy": float(correct[mask].mean()),
            }
        )
    return rows


def _step_metric_rows(
    df: pl.DataFrame,
    *,
    prediction_col: str,
    prediction_type: str,
) -> list[dict[str, Any]]:
    if df.is_empty():
        return []

    rows: list[dict[str, Any]] = []
    for pred_batch, grp in df.group_by("pred_batch", maintain_order=True):
        batch = int(pred_batch[0] if isinstance(pred_batch, tuple) else pred_batch)
        active = grp.filter(pl.col(prediction_col).is_not_null())
        if active.is_empty():
            rows.append(
                {
                    "pred_batch": batch,
                    "rows_total": int(grp.height),
                    "rows_active": 0,
                    "row_coverage": 0.0,
                    "class_accuracy": None,
                    "directional_accuracy": None,
                }
            )
            continue

        y_true = active["y_true"].to_numpy().astype(np.int32, copy=False)
        true_dir = (y_true >= 2).astype(np.int8, copy=False)
        if prediction_type == "class":
            y_pred = active[prediction_col].to_numpy().astype(np.int32, copy=False)
            pred_dir = (y_pred >= 2).astype(np.int8, copy=False)
            class_acc = float((y_true == y_pred).mean())
        else:
            y_pred = None
            pred_dir = active[prediction_col].to_numpy().astype(np.int8, copy=False)
            class_acc = None

        rows.append(
            {
                "pred_batch": batch,
                "rows_total": int(grp.height),
                "rows_active": int(active.height),
                "row_coverage": float(active.height / grp.height) if grp.height else 0.0,
                "class_accuracy": class_acc,
                "directional_accuracy": float((true_dir == pred_dir).mean()),
            }
        )
    return rows


def _worst_rolling_windows(
    step_rows: list[dict[str, Any]],
    *,
    window_size: int = 20,
    top_n: int = 5,
) -> list[dict[str, Any]]:
    valid = [
        r
        for r in sorted(step_rows, key=lambda x: int(x["pred_batch"]))
        if r.get("directional_accuracy") is not None
    ]
    if not valid:
        return []
    window_size = max(2, min(int(window_size), len(valid)))
    out: list[dict[str, Any]] = []
    for start in range(0, len(valid) - window_size + 1):
        window = valid[start : start + window_size]
        dir_acc = float(np.mean([float(r["directional_accuracy"]) for r in window]))
        cover = float(np.mean([float(r["row_coverage"]) for r in window]))
        out.append(
            {
                "start_pred_batch": int(window[0]["pred_batch"]),
                "end_pred_batch": int(window[-1]["pred_batch"]),
                "window_size": int(window_size),
                "directional_accuracy_mean": dir_acc,
                "row_coverage_mean": cover,
            }
        )
    out.sort(key=lambda r: (r["directional_accuracy_mean"], r["row_coverage_mean"], r["start_pred_batch"]))
    return out[:top_n]


def _evaluate_prediction_frame(
    df: pl.DataFrame,
    *,
    prediction_col: str,
    prediction_type: str,
    eval_batches: set[int],
) -> dict[str, Any]:
    eval_df = df.filter(pl.col("pred_batch").is_in(sorted(eval_batches)))
    total_rows = int(eval_df.height)
    total_steps = int(eval_df["pred_batch"].n_unique()) if total_rows else 0
    active = eval_df.filter(pl.col(prediction_col).is_not_null())
    active_rows = int(active.height)
    active_steps = int(active["pred_batch"].n_unique()) if active_rows else 0

    if active.is_empty():
        return {
            "rows_total": total_rows,
            "rows_active": active_rows,
            "row_coverage": float(active_rows / total_rows) if total_rows else 0.0,
            "steps_total": total_steps,
            "steps_active": active_steps,
            "step_coverage": float(active_steps / total_steps) if total_steps else 0.0,
            "class_accuracy": None,
            "directional_accuracy": None,
            "macro_f1": None,
            "cross_direction_error": None,
            "logloss": None,
            "brier_score": None,
            "probability_mode": "missing",
            "mean_confidence": None,
            "mean_entropy": None,
            "mean_margin": None,
            "confusion_matrix": [],
            "direction_confusion": [],
            "per_class_precision": {},
            "per_class_recall": {},
            "calibration_buckets": [],
            "worst_steps": [],
            "worst_rolling_windows": [],
        }

    y_true = active["y_true"].to_numpy().astype(np.int32, copy=False)
    true_dir = (y_true >= 2).astype(np.int8, copy=False)

    if prediction_type == "class":
        y_pred = active[prediction_col].to_numpy().astype(np.int32, copy=False)
        pred_dir = (y_pred >= 2).astype(np.int8, copy=False)
        class_accuracy = float((y_true == y_pred).mean())
        macro_f1 = float(f1_score(y_true, y_pred, average="macro", zero_division=0))
        confusion = confusion_matrix(y_true, y_pred, labels=list(range(N_CLASSES))).tolist()
        precision, recall, _, _ = precision_recall_fscore_support(
            y_true,
            y_pred,
            labels=list(range(N_CLASSES)),
            zero_division=0,
        )
        per_class_precision = {
            CLASS_NAMES_4[i]: float(precision[i]) for i in range(N_CLASSES)
        }
        per_class_recall = {CLASS_NAMES_4[i]: float(recall[i]) for i in range(N_CLASSES)}
    else:
        y_pred = None
        pred_dir = active[prediction_col].to_numpy().astype(np.int8, copy=False)
        class_accuracy = None
        macro_f1 = None
        confusion = []
        per_class_precision = {}
        per_class_recall = {}

    class_probs, direction_probs, probability_mode = _probability_arrays(
        active,
        prediction_col=prediction_col,
        prediction_type=prediction_type,
    )

    logloss = None
    brier = None
    mean_confidence = None
    mean_entropy = None
    mean_margin = None
    calibration_buckets: list[dict[str, Any]] = []
    if prediction_type == "class" and class_probs is not None:
        class_probs = np.clip(class_probs, 1e-12, 1.0)
        class_probs = class_probs / class_probs.sum(axis=1, keepdims=True)
        logloss = float(
            -np.mean(np.log(class_probs[np.arange(len(y_true)), y_true.astype(int)]))
        )
        brier = _multiclass_brier(y_true, class_probs)
        confidence = np.max(class_probs, axis=1)
        sorted_probs = np.sort(class_probs, axis=1)
        mean_confidence = float(confidence.mean())
        mean_entropy = float(
            (-np.sum(class_probs * np.log(np.clip(class_probs, 1e-12, 1.0)), axis=1) / math.log(N_CLASSES)).mean()
        )
        mean_margin = float((sorted_probs[:, -1] - sorted_probs[:, -2]).mean())
        calibration_buckets = _confidence_bucket_summary(
            confidence,
            (y_true == y_pred).astype(np.int8, copy=False),
        )
    elif direction_probs is not None:
        direction_probs = np.clip(direction_probs, 1e-12, 1.0)
        direction_probs = direction_probs / direction_probs.sum(axis=1, keepdims=True)
        logloss = float(
            -np.mean(np.log(direction_probs[np.arange(len(true_dir)), true_dir.astype(int)]))
        )
        brier = _binary_brier(true_dir, direction_probs[:, 1])
        confidence = np.max(direction_probs, axis=1)
        sorted_probs = np.sort(direction_probs, axis=1)
        mean_confidence = float(confidence.mean())
        mean_entropy = float(
            (-np.sum(direction_probs * np.log(np.clip(direction_probs, 1e-12, 1.0)), axis=1) / math.log(2)).mean()
        )
        mean_margin = float((sorted_probs[:, -1] - sorted_probs[:, -2]).mean())
        calibration_buckets = _confidence_bucket_summary(
            confidence,
            (true_dir == pred_dir).astype(np.int8, copy=False),
        )

    direction_confusion = confusion_matrix(true_dir, pred_dir, labels=[0, 1]).tolist()
    step_rows = _step_metric_rows(
        eval_df,
        prediction_col=prediction_col,
        prediction_type=prediction_type,
    )
    worst_steps = sorted(
        [r for r in step_rows if r.get("directional_accuracy") is not None],
        key=lambda r: (float(r["directional_accuracy"]), float(r["row_coverage"]), int(r["pred_batch"])),
    )[:5]

    return {
        "rows_total": total_rows,
        "rows_active": active_rows,
        "row_coverage": float(active_rows / total_rows) if total_rows else 0.0,
        "steps_total": total_steps,
        "steps_active": active_steps,
        "step_coverage": float(active_steps / total_steps) if total_steps else 0.0,
        "class_accuracy": class_accuracy,
        "directional_accuracy": float((true_dir == pred_dir).mean()),
        "macro_f1": macro_f1,
        "cross_direction_error": _compute_cross_direction_error_from_dirs(true_dir, pred_dir),
        "logloss": logloss,
        "brier_score": brier,
        "probability_mode": probability_mode,
        "mean_confidence": mean_confidence,
        "mean_entropy": mean_entropy,
        "mean_margin": mean_margin,
        "confusion_matrix": confusion,
        "direction_confusion": direction_confusion,
        "per_class_precision": per_class_precision,
        "per_class_recall": per_class_recall,
        "calibration_buckets": calibration_buckets,
        "worst_steps": worst_steps,
        "worst_rolling_windows": _worst_rolling_windows(step_rows),
    }


def _load_action_key_ranking_from_stage1(
    unit_dir: Path,
    *,
    selection_metric: str = "cross_direction_error",
) -> list[dict[str, Any]]:
    direction = _metric_direction(selection_metric)
    val_sum: dict[str, float] = {}
    val_n: dict[str, int] = {}
    pred_sum: dict[str, float] = {}
    pred_n: dict[str, int] = {}
    winner_count: dict[str, int] = {}
    steps_seen = 0

    for batch_dir in _iter_batch_dirs(unit_dir):
        stage1_dir = batch_dir / "stage1"
        combo_path = stage1_dir / "stage1_combo_index.parquet"
        val_path = stage1_dir / "stage1_val_predictions.parquet"
        pred_path = stage1_dir / "stage1_pred_batch_predictions.parquet"
        summary_path = stage1_dir / "stage1_step_summary.json"
        if not (combo_path.exists() and val_path.exists() and pred_path.exists()):
            continue

        combo_df = pl.read_parquet(combo_path)
        val_df = pl.read_parquet(val_path)
        pred_df = pl.read_parquet(pred_path)
        if "scope" in val_df.columns:
            val_df = val_df.filter(pl.col("scope") == "val_fold")
        if "scope" in pred_df.columns:
            pred_df = pred_df.filter(pl.col("scope") == "pred_batch")
        if combo_df.is_empty() or val_df.is_empty() or pred_df.is_empty():
            continue

        complete_idx = combo_df.filter(pl.col("status") == "complete")
        if complete_idx.is_empty():
            continue

        def combo_metrics(payload: pl.DataFrame) -> list[dict[str, Any]]:
            rows: list[dict[str, Any]] = []
            for combo_id, grp in payload.group_by("combo_id"):
                combo_id_val = int(combo_id[0] if isinstance(combo_id, tuple) else combo_id)
                combo_row = complete_idx.filter(pl.col("combo_id") == combo_id_val).head(1)
                if combo_row.is_empty():
                    continue
                row = combo_row.to_dicts()[0]
                action_key = str(row.get("action_key"))
                y_true = grp["y_true"].to_numpy().astype(np.int32, copy=False)
                y_pred = grp["y_pred"].to_numpy().astype(np.int32, copy=False)
                accuracy = float((y_true == y_pred).mean()) if y_true.size else None
                macro_f1 = (
                    float(f1_score(y_true, y_pred, average="macro", zero_division=0))
                    if y_true.size
                    else None
                )
                cross_err = _compute_cross_direction_error(y_true, y_pred)
                metric_map = {
                    "accuracy": accuracy,
                    "macro_f1": macro_f1,
                    "cross_direction_error": cross_err,
                }
                metric_value = metric_map.get(selection_metric)
                if metric_value is None:
                    continue
                rows.append(
                    {
                        "combo_id": combo_id_val,
                        "action_key": action_key,
                        "selection_value": float(metric_value),
                    }
                )
            rows.sort(
                key=lambda r: (
                    float(r["selection_value"]),
                    str(r["action_key"]),
                ),
                reverse=direction != "minimize",
            )
            if direction == "minimize":
                rows.sort(key=lambda r: (float(r["selection_value"]), str(r["action_key"])))
            return rows

        val_rows = combo_metrics(val_df)
        pred_rows = combo_metrics(pred_df)
        if not val_rows:
            continue

        steps_seen += 1
        pred_map = {r["action_key"]: r for r in pred_rows}
        for row in val_rows:
            action_key = str(row["action_key"])
            val_sum[action_key] = val_sum.get(action_key, 0.0) + float(row["selection_value"])
            val_n[action_key] = val_n.get(action_key, 0) + 1
            pred_row = pred_map.get(action_key)
            if pred_row is not None:
                pred_sum[action_key] = pred_sum.get(action_key, 0.0) + float(
                    pred_row["selection_value"]
                )
                pred_n[action_key] = pred_n.get(action_key, 0) + 1

        winner_action_key = None
        if summary_path.exists():
            try:
                winner_action_key = str(_load_json(summary_path)["winner_combo_key"])
            except Exception:
                winner_action_key = None
        if winner_action_key is None and pred_rows:
            winner_action_key = str(pred_rows[0]["action_key"])
        if winner_action_key:
            winner_count[winner_action_key] = winner_count.get(winner_action_key, 0) + 1

    rows: list[dict[str, Any]] = []
    for action_key in sorted(set(val_sum) | set(pred_sum) | set(winner_count)):
        rows.append(
            {
                "action_key": action_key,
                "winner_count": int(winner_count.get(action_key, 0)),
                "winner_rate": float(winner_count.get(action_key, 0) / steps_seen) if steps_seen else 0.0,
                "mean_validation_metric": (
                    float(val_sum[action_key] / val_n[action_key]) if val_n.get(action_key) else None
                ),
                "mean_prediction_metric": (
                    float(pred_sum[action_key] / pred_n[action_key]) if pred_n.get(action_key) else None
                ),
                "validation_steps": int(val_n.get(action_key, 0)),
                "prediction_steps": int(pred_n.get(action_key, 0)),
            }
        )

    if direction == "minimize":
        rows.sort(
            key=lambda r: (
                -int(r["winner_count"]),
                float(r["mean_validation_metric"])
                if r["mean_validation_metric"] is not None
                else float("inf"),
                float(r["mean_prediction_metric"])
                if r["mean_prediction_metric"] is not None
                else float("inf"),
                str(r["action_key"]),
            )
        )
    else:
        rows.sort(
            key=lambda r: (
                -int(r["winner_count"]),
                -float(r["mean_validation_metric"])
                if r["mean_validation_metric"] is not None
                else float("inf"),
                -float(r["mean_prediction_metric"])
                if r["mean_prediction_metric"] is not None
                else float("inf"),
                str(r["action_key"]),
            )
        )
    return rows


def _select_root_topk_action_keys(ranking_rows: list[dict[str, Any]], topk: int) -> list[str]:
    if not ranking_rows:
        return []
    topk = max(1, int(topk))
    dominant = str(ranking_rows[0]["action_key"])
    near = [r for r in ranking_rows if str(r["action_key"]) != dominant]
    near.sort(
        key=lambda r: (
            -float(r["mean_validation_metric"]) if r["mean_validation_metric"] is not None else float("inf"),
            -float(r["mean_prediction_metric"]) if r["mean_prediction_metric"] is not None else float("inf"),
            str(r["action_key"]),
        )
    )
    return [dominant] + [str(r["action_key"]) for r in near[: max(0, topk - 1)]]


def _workflow_manifest_for_root(
    root_cfg: RootConfig,
    *,
    causal_root_meta: dict[str, Any],
    eval_batches: set[int],
    ranking_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    stage1_run_dir = root_cfg.unit_dir.parents[2]
    batch_dirs = _iter_batch_dirs(root_cfg.unit_dir)
    batch_range = [
        int(batch_dirs[0].name.split("_")[1]),
        int(batch_dirs[-1].name.split("_")[1]),
    ] if batch_dirs else [None, None]
    return {
        "root": root_cfg.root,
        "run_id": root_cfg.run_id,
        "htf_entrypoint": str(PROJECT_ROOT / "notebooks" / "htf_pythonscript.py"),
        "stage1_notebook": str(PROJECT_ROOT / "notebooks" / "htf_stage1.py"),
        "stage1_runner": str(PROJECT_ROOT / "scripts" / "htf_backtest" / "catboost" / "stage1_runner.py"),
        "stage1_step2": str(PROJECT_ROOT / "scripts" / "htf_backtest" / "catboost" / "stage1_step2.py"),
        "causal_analysis_script": str(
            PROJECT_ROOT / "scripts" / "analysis" / "htf_causal_multiregime_method_analysis.py"
        ),
        "unit_dir": str(root_cfg.unit_dir),
        "features_dir": str(root_cfg.features_dir),
        "labels_dir": str(root_cfg.labels_dir),
        "stage1_run_state": str(stage1_run_dir / "stage1_run_state.json"),
        "stage1_progress": str(stage1_run_dir / "stage1_progress.parquet"),
        "winners_all_steps": str(root_cfg.unit_dir / "winners_all_steps.parquet"),
        "stage1_batch_range": batch_range,
        "causal_combo_match_pred_rows": causal_root_meta.get("combo_match_pred_rows"),
        "causal_probability_run_dir": causal_root_meta.get("probability_run_dir"),
        "causal_combo_count": int(causal_root_meta.get("combo_count", 0) or 0),
        "causal_incomplete_combo_batches": causal_root_meta.get("incomplete_combo_batches", []),
        "causal_eval_batches": sorted(int(b) for b in eval_batches),
        "causal_eval_range": [
            int(min(eval_batches)) if eval_batches else None,
            int(max(eval_batches)) if eval_batches else None,
        ],
        "selection_metric": "cross_direction_error",
        "selection_scope_root_topk": _select_root_topk_action_keys(
            ranking_rows, DEFAULT_TOPK_ACTION_KEYS
        ),
        "source_of_truth": {
            "production_data": str(root_cfg.features_dir),
            "stage1_step_payloads": str(root_cfg.unit_dir),
            "causal_method_rows": str(PROJECT_ROOT / "test_output" / "htf_causal_multiregime_method_analysis"),
        },
    }


def _load_stage1_step_summary_rows(unit_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for batch_dir in _iter_batch_dirs(unit_dir):
        summary_path = batch_dir / "stage1" / "stage1_step_summary.json"
        if not summary_path.exists():
            continue
        summary = _load_json(summary_path)
        rows.append(
            {
                "pred_batch": int(summary.get("pred_batch") or batch_dir.name.split("_")[1]),
                "winner_combo_key": str(summary.get("winner_combo_key")),
                "winner_accuracy": _safe_float(summary.get("winner_accuracy")),
                "winner_macro_f1": _safe_float(summary.get("winner_macro_f1")),
                "winner_cross_direction_error": _safe_float(
                    summary.get("winner_cross_direction_error")
                ),
                "quality_pass": bool(summary.get("quality_pass", False)),
                "quality_unresolved": bool(summary.get("quality_unresolved", False)),
                "combo_count_total": int(summary.get("combo_count_total", 0) or 0),
                "combo_count_completed": int(summary.get("combo_count_completed", 0) or 0),
                "runtime_s": _safe_float(summary.get("runtime_s")),
            }
        )
    return rows


def _infer_feature_source_family(feature: str) -> str:
    if feature.startswith("H_"):
        return "helper"
    if feature.startswith("D_dist"):
        return "distance_metric"
    if "funding" in feature.lower():
        return "funding_aux"
    if any(tok in feature.lower() for tok in ("premium", "basis", "mark", "index")):
        return "aux_price_derived"
    if feature.startswith("X_"):
        return "cross_composite"
    if feature.startswith("D_"):
        return "derived_distance_family"
    return "base_or_other"


def _feature_quality_rows(
    *,
    root_cfg: RootConfig,
    eval_batches: set[int],
    features: list[str],
) -> pl.DataFrame:
    if not features or not eval_batches:
        return pl.DataFrame()
    selected = sorted(set(features))
    batch_ids = sorted(int(b) for b in eval_batches)
    first_cut = set(batch_ids[: max(1, len(batch_ids) // 3)])
    last_cut = set(batch_ids[-max(1, len(batch_ids) // 3) :])

    frames: list[pl.DataFrame] = []
    for batch_id in batch_ids:
        path = root_cfg.features_dir / TF / TARGET_COL / f"batch_{batch_id:04d}.parquet"
        if not path.exists():
            continue
        cols = [c for c in selected if c in pl.read_parquet_schema(path)]
        if not cols:
            continue
        df = pl.read_parquet(path, columns=cols + ["batch_id"]).with_columns(
            pl.lit(batch_id).alias("_batch_for_quality")
        )
        frames.append(df)
    if not frames:
        return pl.DataFrame()

    full_df = pl.concat(frames, how="diagonal_relaxed")
    rows: list[dict[str, Any]] = []
    for feature in selected:
        if feature not in full_df.columns:
            continue
        series = full_df[feature]
        null_rate = float(series.null_count() / max(1, len(series)))
        non_null = full_df.filter(pl.col(feature).is_not_null())
        first_df = non_null.filter(pl.col("_batch_for_quality").is_in(sorted(first_cut)))
        last_df = non_null.filter(pl.col("_batch_for_quality").is_in(sorted(last_cut)))
        first_mean = _safe_float(first_df[feature].mean()) if not first_df.is_empty() else None
        last_mean = _safe_float(last_df[feature].mean()) if not last_df.is_empty() else None
        first_std = _safe_float(first_df[feature].std()) if not first_df.is_empty() else None
        last_std = _safe_float(last_df[feature].std()) if not last_df.is_empty() else None
        pooled_std = None
        if first_std is not None or last_std is not None:
            pooled_std = float(
                np.nanmean(
                    [
                        float(first_std) if first_std is not None else np.nan,
                        float(last_std) if last_std is not None else np.nan,
                    ]
                )
            )
            if not np.isfinite(pooled_std):
                pooled_std = None
        drift_score = None
        if first_mean is not None and last_mean is not None:
            denom = pooled_std if pooled_std and pooled_std > 1e-9 else 1.0
            drift_score = abs(float(last_mean - first_mean)) / float(denom)
        if drift_score is None:
            drift_level = "unknown"
        elif drift_score < 0.25:
            drift_level = "low"
        elif drift_score < 0.75:
            drift_level = "medium"
        else:
            drift_level = "high"

        exclusions = describe_final_output_exclusions([feature], stage="helpers")
        suspicious_reason = None
        if exclusions:
            suspicious_reason = exclusions[0]["reason"]
        elif feature.startswith("D_dist") and null_rate > 0.0:
            suspicious_reason = "batch_local_warmup_nulls"
        elif "fundingzscore" in feature.lower():
            suspicious_reason = "funding_zscore_formula_mismatch"

        rows.append(
            {
                "root": root_cfg.root,
                "feature": feature,
                "source_family": _infer_feature_source_family(feature),
                "null_rate": null_rate,
                "drift_score": drift_score,
                "drift_level": drift_level,
                "first_mean": first_mean,
                "last_mean": last_mean,
                "policy_blocked": bool(exclusions),
                "policy_reason": exclusions[0]["reason"] if exclusions else None,
                "suspicious": suspicious_reason is not None,
                "suspicious_reason": suspicious_reason,
            }
        )
    return pl.DataFrame(rows).sort(["policy_blocked", "null_rate", "drift_score"], descending=[True, True, True])


def _build_root_profile(
    *,
    root_cfg: RootConfig,
    causal_root_meta: dict[str, Any],
    causal_scores: pl.DataFrame,
    eval_batches: set[int],
    ranking_rows: list[dict[str, Any]],
) -> tuple[dict[str, Any], pl.DataFrame]:
    combo_match_path = Path(str(causal_root_meta["combo_match_pred_rows"]))
    pred_rows = pl.read_parquet(combo_match_path)
    eval_truth = _unique_eval_truth_rows(pred_rows, eval_batches)
    total_rows = int(eval_truth.height)
    direction_df = eval_truth.with_columns((pl.col("y_true") >= 2).cast(pl.Int8).alias("true_dir"))
    class_counts = (
        direction_df.group_by("y_true").len().sort("y_true").to_dicts() if not direction_df.is_empty() else []
    )
    direction_counts = (
        direction_df.group_by("true_dir").len().sort("true_dir").to_dicts()
        if not direction_df.is_empty()
        else []
    )
    y_true = direction_df["y_true"].to_numpy().astype(np.int32, copy=False) if total_rows else np.array([], dtype=np.int32)
    y_dir = (y_true >= 2).astype(np.int8, copy=False) if total_rows else np.array([], dtype=np.int8)
    majority_direction_baseline = float(max((y_dir == 0).mean(), (y_dir == 1).mean())) if total_rows else None

    step_summary_rows = [
        r
        for r in _load_stage1_step_summary_rows(root_cfg.unit_dir)
        if int(r["pred_batch"]) in eval_batches
    ]
    winner_accuracy_vals = [float(r["winner_accuracy"]) for r in step_summary_rows if r["winner_accuracy"] is not None]
    winner_combo_freq: dict[str, int] = {}
    for row in step_summary_rows:
        winner_combo_freq[str(row["winner_combo_key"])] = winner_combo_freq.get(
            str(row["winner_combo_key"]), 0
        ) + 1

    stage1_run_state = _load_json(root_cfg.unit_dir.parents[2] / "stage1_run_state.json")
    stage1_progress = pl.read_parquet(root_cfg.unit_dir.parents[2] / "stage1_progress.parquet")
    unit_progress = stage1_progress.filter(
        (pl.col("timeframe") == TF) & (pl.col("target") == TARGET_COL)
    )
    progress_eval = unit_progress.filter(pl.col("pred_batch").is_in(sorted(eval_batches)))

    full_coverage_scores = causal_scores.filter(pl.col("row_coverage") >= FULL_COVERAGE_THRESHOLD)
    best_full = (
        full_coverage_scores.sort(
            ["directional_accuracy", "row_coverage", "class_accuracy"],
            descending=[True, True, True],
        ).head(1)
        if not full_coverage_scores.is_empty()
        else pl.DataFrame()
    )
    best_reduced = (
        causal_scores.sort(
            ["directional_accuracy", "row_coverage", "class_accuracy"],
            descending=[True, True, True],
        ).head(1)
        if not causal_scores.is_empty()
        else pl.DataFrame()
    )
    direct_baseline = causal_scores.filter(
        (pl.col("method_family") == "uniform_direction_sum") & (pl.col("config_id") == "direct")
    ).head(1)

    root_profile = {
        "root": root_cfg.root,
        "run_id": root_cfg.run_id,
        "stage1_steps_total": int(len(_iter_batch_dirs(root_cfg.unit_dir))),
        "eval_batches_count": int(len(eval_batches)),
        "eval_batch_min": int(min(eval_batches)) if eval_batches else None,
        "eval_batch_max": int(max(eval_batches)) if eval_batches else None,
        "total_rows_eval": int(total_rows),
        "active_eval_rows": int(total_rows),
        "majority_direction_baseline": majority_direction_baseline,
        "class_distribution_json": json.dumps(class_counts),
        "direction_distribution_json": json.dumps(direction_counts),
        "winner_accuracy_mean": float(np.mean(winner_accuracy_vals)) if winner_accuracy_vals else None,
        "winner_accuracy_median": float(np.median(winner_accuracy_vals)) if winner_accuracy_vals else None,
        "winner_quality_pass_rate": (
            float(np.mean([bool(r["quality_pass"]) for r in step_summary_rows])) if step_summary_rows else None
        ),
        "winner_combo_frequency_json": json.dumps(
            sorted(winner_combo_freq.items(), key=lambda kv: (-kv[1], kv[0]))[:20]
        ),
        "topk_action_keys_json": json.dumps(
            _select_root_topk_action_keys(ranking_rows, DEFAULT_TOPK_ACTION_KEYS)
        ),
        "best_full_coverage_method": best_full["method_family"][0] if len(best_full) else None,
        "best_full_coverage_config": best_full["config_id"][0] if len(best_full) else None,
        "best_full_coverage_directional_accuracy": float(best_full["directional_accuracy"][0])
        if len(best_full)
        else None,
        "best_full_coverage_row_coverage": float(best_full["row_coverage"][0]) if len(best_full) else None,
        "best_reduced_method": best_reduced["method_family"][0] if len(best_reduced) else None,
        "best_reduced_config": best_reduced["config_id"][0] if len(best_reduced) else None,
        "best_reduced_directional_accuracy": float(best_reduced["directional_accuracy"][0])
        if len(best_reduced)
        else None,
        "best_reduced_row_coverage": float(best_reduced["row_coverage"][0]) if len(best_reduced) else None,
        "direct_baseline_directional_accuracy": float(direct_baseline["directional_accuracy"][0])
        if len(direct_baseline)
        else None,
        "direct_baseline_row_coverage": float(direct_baseline["row_coverage"][0]) if len(direct_baseline) else None,
        "gain_vs_direct_full_coverage": (
            float(best_full["directional_accuracy"][0] - direct_baseline["directional_accuracy"][0])
            if len(best_full) and len(direct_baseline)
            else None
        ),
        "gain_vs_direct_best_reduced": (
            float(best_reduced["directional_accuracy"][0] - direct_baseline["directional_accuracy"][0])
            if len(best_reduced) and len(direct_baseline)
            else None
        ),
        "incomplete_combo_batches_count": int(causal_root_meta.get("incomplete_combo_batches_count", 0) or 0),
        "filtered_incomplete_combo_batches_json": json.dumps(
            causal_root_meta.get("incomplete_combo_batches", [])
        ),
        "missing_feature_batches_count": int(
            sum(
                1
                for b in eval_batches
                if not (root_cfg.features_dir / TF / TARGET_COL / f"batch_{int(b):04d}.parquet").exists()
            )
        ),
        "missing_label_batches_count": int(
            sum(
                1
                for b in eval_batches
                if not (root_cfg.labels_dir / TF / f"batch_{int(b):04d}.parquet").exists()
            )
        ),
        "non_completed_stage1_steps_count": int(
            progress_eval.filter(pl.col("status") != "completed").height
        ),
        "quality_unresolved_steps_count": int(
            sum(1 for r in step_summary_rows if bool(r["quality_unresolved"]))
        ),
        "selection_metric": "cross_direction_error",
        "stage1_resume_mode": str(stage1_run_state.get("resume_mode")),
    }

    eval_truth_path = combo_match_path.parent / "eval_truth_rows.parquet"
    if not eval_truth.is_empty():
        eval_truth.write_parquet(eval_truth_path)
    return root_profile, eval_truth


def _build_step2_overrides(root_cfg: RootConfig) -> dict[str, Any]:
    return {
        MODEL_NAME: {
            TF: {
                TARGET_COL: {
                    "optuna_metric": "cross_direction_error",
                    "cb_base_params": dict(STAGE1_CB_BASE_PARAMS),
                    "features_dir_override": str(root_cfg.features_dir),
                    "labels_dir_override": str(root_cfg.labels_dir),
                }
            }
        }
    }


def _run_step2_for_root(
    *,
    root_cfg: RootConfig,
    selection_scope: str,
    feature_importance_type: str,
    output_subdir: str,
) -> dict[str, Any]:
    return run_stage1_step2_feature_pruning(
        stage1_run_id_or_path=root_cfg.run_id,
        project_root=PROJECT_ROOT,
        model_name=MODEL_NAME,
        timeframes=[TF],
        targets_by_model={MODEL_NAME: {TF: [TARGET_COL]}},
        n_classes_by_model={MODEL_NAME: {TF: {TARGET_COL: N_CLASSES}}},
        class_names_by_model={MODEL_NAME: {TF: {TARGET_COL: CLASS_NAMES_4}}},
        feature_source_by_model={MODEL_NAME: {TF: {TARGET_COL: TARGET_COL}}},
        optuna_overrides_by_model=_build_step2_overrides(root_cfg),
        feature_importance_type=feature_importance_type,
        feature_selector_method="recursive_shap",
        selection_scope=selection_scope,
        topk_action_keys_per_root=DEFAULT_TOPK_ACTION_KEYS,
        combo_processing_mode=selection_scope,
        comparison_metric_mode="reward",
        winner_metric="cross_direction_error",
        output_subdir=output_subdir,
        verbose=True,
    )


def _build_recommendations(
    *,
    root_profiles: pl.DataFrame,
    feature_quality_by_root: dict[str, pl.DataFrame],
    top_features_by_root: dict[str, list[str]],
) -> pl.DataFrame:
    rows: list[dict[str, Any]] = []
    for row in root_profiles.to_dicts():
        root = str(row["root"])
        fq = feature_quality_by_root.get(root, pl.DataFrame())
        if not fq.is_empty():
            blocked = fq.filter(pl.col("policy_blocked") == True)  # noqa: E712
            high_null = fq.filter(pl.col("null_rate") >= 0.10)
            high_drift = fq.filter(pl.col("drift_level") == "high")
            if len(blocked) > 0:
                rows.append(
                    {
                        "root": root,
                        "artifact_scope": "feature_quality",
                        "issue_type": "policy_blocked_top_feature",
                        "evidence": json.dumps(blocked.select(["feature", "policy_reason"]).head(5).to_dicts()),
                        "recommended_action": "review why blocked features remain predictive and decide whether to redesign or keep them excluded from training outputs",
                        "priority": "high",
                    }
                )
            if len(high_null) > 0:
                rows.append(
                    {
                        "root": root,
                        "artifact_scope": "feature_quality",
                        "issue_type": "null_heavy_top_feature",
                        "evidence": json.dumps(high_null.select(["feature", "null_rate"]).head(5).to_dicts()),
                        "recommended_action": "audit null-heavy influential features before parameter tuning; treat as data-quality work first",
                        "priority": "high",
                    }
                )
            if len(high_drift) > 0:
                rows.append(
                    {
                        "root": root,
                        "artifact_scope": "feature_quality",
                        "issue_type": "drifting_top_feature",
                        "evidence": json.dumps(high_drift.select(["feature", "drift_score"]).head(5).to_dicts()),
                        "recommended_action": "add drift-aware monitoring or evaluate whether the feature should be normalized or redefined per regime",
                        "priority": "medium",
                    }
                )
        if row.get("gain_vs_direct_full_coverage") is not None and row["gain_vs_direct_full_coverage"] <= 0.0:
            rows.append(
                {
                    "root": root,
                    "artifact_scope": "causal_methods",
                    "issue_type": "no_full_coverage_gain",
                    "evidence": json.dumps(
                        {
                            "best_full_method": row.get("best_full_coverage_method"),
                            "gain_vs_direct_full_coverage": row.get("gain_vs_direct_full_coverage"),
                        }
                    ),
                    "recommended_action": "focus first on base-model quality and feature quality before adding more complex ensemble logic",
                    "priority": "medium",
                }
            )
        if row.get("winner_quality_pass_rate") is not None and row["winner_quality_pass_rate"] < 0.25:
            rows.append(
                {
                    "root": root,
                    "artifact_scope": "stage1_winners",
                    "issue_type": "low_winner_quality_pass_rate",
                    "evidence": json.dumps(
                        {
                            "winner_quality_pass_rate": row["winner_quality_pass_rate"],
                            "topk_action_keys": top_features_by_root.get(root, []),
                        }
                    ),
                    "recommended_action": "prioritize parameter sweeps and label/regime difficulty review for this root before expanding ensemble complexity",
                    "priority": "high",
                }
            )
    return pl.DataFrame(rows) if rows else pl.DataFrame()


def _merge_feature_quality_frames(
    existing: pl.DataFrame | None,
    incoming: pl.DataFrame,
) -> pl.DataFrame:
    if incoming.is_empty():
        return existing if existing is not None else pl.DataFrame()
    if existing is None or existing.is_empty():
        return incoming
    all_df = pl.concat([existing, incoming], how="diagonal_relaxed")
    sort_cols = ["policy_blocked", "null_rate", "drift_score"]
    present_sort_cols = [c for c in sort_cols if c in all_df.columns]
    if present_sort_cols:
        all_df = all_df.sort(
            present_sort_cols,
            descending=[True] * len(present_sort_cols),
            nulls_last=True,
        )
    if "feature" in all_df.columns:
        return all_df.unique(subset=["feature"], keep="first")
    return all_df


def _read_artifact_df(path: str | None) -> pl.DataFrame:
    if not path:
        return pl.DataFrame()
    art_path = Path(path)
    if not art_path.exists():
        return pl.DataFrame()
    return pl.read_parquet(art_path)


def _root_scope_type_dir(
    output_root: Path,
    *,
    selection_scope: str,
    feature_importance_type: str,
    root: str,
) -> Path:
    out_dir = (
        output_root
        / "step2"
        / selection_scope
        / feature_importance_type
        / _root_slug(root)
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def _write_df_if_not_empty(df: pl.DataFrame, path: Path) -> None:
    if df.is_empty():
        return
    if path.suffix == ".csv":
        df.write_csv(path)
    elif path.suffix == ".json":
        path.write_text(json.dumps(df.to_dicts(), indent=2), encoding="utf-8")
    else:
        df.write_parquet(path)


def _build_winner_vs_near_overlap(
    *,
    root: str,
    feature_importance_type: str,
    top_features_df: pl.DataFrame,
    ranking_df: pl.DataFrame,
) -> pl.DataFrame:
    if top_features_df.is_empty() or "action_key" not in top_features_df.columns:
        return pl.DataFrame()
    if ranking_df.is_empty() or "action_key" not in ranking_df.columns:
        return pl.DataFrame()

    ordered_keys = ranking_df["action_key"].to_list()
    if not ordered_keys:
        return pl.DataFrame()
    winner_key = str(ordered_keys[0])
    compare_keys = [str(k) for k in ordered_keys[1:3]]
    winner_features = set(
        top_features_df.filter(pl.col("action_key") == winner_key)["feature"].to_list()
    )
    rows: list[dict[str, Any]] = []
    for other_key in compare_keys:
        other_features = set(
            top_features_df.filter(pl.col("action_key") == other_key)["feature"].to_list()
        )
        if not other_features and not winner_features:
            continue
        overlap = sorted(winner_features & other_features)
        winner_only = sorted(winner_features - other_features)
        other_only = sorted(other_features - winner_features)
        union_size = len(winner_features | other_features)
        rows.append(
            {
                "root": root,
                "feature_importance_type": feature_importance_type,
                "winner_action_key": winner_key,
                "compare_action_key": other_key,
                "winner_feature_count": len(winner_features),
                "compare_feature_count": len(other_features),
                "overlap_count": len(overlap),
                "jaccard_overlap": float(len(overlap) / union_size) if union_size else None,
                "overlap_features_json": json.dumps(overlap),
                "winner_only_features_json": json.dumps(winner_only[:50]),
                "compare_only_features_json": json.dumps(other_only[:50]),
            }
        )
    return pl.DataFrame(rows)


def _write_markdown_workflow_note(
    *,
    output_root: Path,
    workflow_manifest: dict[str, Any],
    root_profiles: pl.DataFrame,
    causal_run_dir: Path,
) -> Path:
    note_path = PROJECT_ROOT / "notebooks" / "notes" / f"htf_walkforward_workflow_audit_{datetime.now().strftime('%Y-%m-%d')}.md"
    lines = [
        f"# HTF Walk-Forward Workflow Audit - {datetime.now().strftime('%Y-%m-%d')}",
        "",
        "## Scope",
        "",
        "Trace the current production HTF workflow from saved production data through Stage-1 walk-forward outputs, Stage-1 Step-2 feature-pruning/importance analysis, causal ensemble analysis, and final evaluation artifacts.",
        "",
        "## Source Of Truth",
        "",
        f"- Production HTF entrypoint: `notebooks/htf_pythonscript.py`",
        f"- Stage-1 notebook: `notebooks/htf_stage1.py`",
        f"- Stage-1 runner: `scripts/htf_backtest/catboost/stage1_runner.py`",
        f"- Stage-1 Step-2: `scripts/htf_backtest/catboost/stage1_step2.py`",
        f"- Latest causal analysis run: `{causal_run_dir}`",
        f"- Machine-readable manifest: `{output_root / 'workflow_manifest.json'}`",
        "",
        "## Root Summary",
        "",
    ]
    for row in root_profiles.sort("root").to_dicts():
        lines.extend(
            [
                f"### {row['root']}",
                "",
                f"- Stage-1 eval batch range: `{row['eval_batch_min']}..{row['eval_batch_max']}` (`n={row['eval_batches_count']}`)",
                f"- Evaluated rows: `{row['active_eval_rows']}`",
                f"- Best full-coverage method: `{row.get('best_full_coverage_method')}` / `{row.get('best_full_coverage_config')}`",
                f"- Best full-coverage directional accuracy: `{row.get('best_full_coverage_directional_accuracy')}`",
                f"- Best reduced-coverage method: `{row.get('best_reduced_method')}` / `{row.get('best_reduced_config')}`",
                f"- Direct baseline directional accuracy: `{row.get('direct_baseline_directional_accuracy')}`",
                f"- Incomplete combo batches filtered: `{row.get('incomplete_combo_batches_count')}`",
                "",
            ]
        )
    note_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return note_path


def _flatten_metrics_row(root: str, scope: str, action_key: str, metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        "root": root,
        "scope": scope,
        "action_key": action_key,
        "rows_total": metrics.get("rows_total"),
        "rows_active": metrics.get("rows_active"),
        "row_coverage": metrics.get("row_coverage"),
        "steps_total": metrics.get("steps_total"),
        "steps_active": metrics.get("steps_active"),
        "step_coverage": metrics.get("step_coverage"),
        "class_accuracy": metrics.get("class_accuracy"),
        "directional_accuracy": metrics.get("directional_accuracy"),
        "macro_f1": metrics.get("macro_f1"),
        "cross_direction_error": metrics.get("cross_direction_error"),
        "logloss": metrics.get("logloss"),
        "brier_score": metrics.get("brier_score"),
        "probability_mode": metrics.get("probability_mode"),
        "mean_confidence": metrics.get("mean_confidence"),
        "mean_entropy": metrics.get("mean_entropy"),
        "mean_margin": metrics.get("mean_margin"),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="HTF walk-forward diagnostics and improvement analysis for current six roots."
    )
    parser.add_argument("--project-root", type=str, default=str(PROJECT_ROOT))
    parser.add_argument(
        "--output-dir",
        type=str,
        default="test_output/htf_walkforward_diagnostics",
    )
    parser.add_argument(
        "--causal-run-dir",
        type=str,
        default="",
        help="Optional path to an existing htf_causal_multiregime_method_analysis run.",
    )
    parser.add_argument(
        "--phases",
        type=str,
        default="audit",
        help="Comma-separated phases: audit,winner_only,root_topk",
    )
    parser.add_argument(
        "--roots",
        type=str,
        default="",
        help="Optional comma-separated subset of roots, e.g. '8h/B,8h/C'. Defaults to all six roots.",
    )
    parser.add_argument(
        "--feature-importance-type",
        type=str,
        default="PredictionValuesChange",
        help="CatBoost feature importance type for Step-2 runs.",
    )
    parser.add_argument(
        "--feature-importance-types",
        type=str,
        default="",
        help=(
            "Optional comma-separated list of CatBoost feature importance types. "
            "If omitted, falls back to --feature-importance-type."
        ),
    )
    parser.add_argument(
        "--topk-action-keys",
        type=int,
        default=DEFAULT_TOPK_ACTION_KEYS,
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    project_root = Path(args.project_root).expanduser().resolve()
    output_root = (project_root / args.output_dir / _timestamp_tag()).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    phases = set(_parse_csv_tokens(args.phases))
    requested_roots = set(_parse_csv_tokens(args.roots))
    feature_importance_types = (
        _parse_csv_tokens(args.feature_importance_types)
        if str(args.feature_importance_types).strip()
        else [str(args.feature_importance_type).strip()]
    )
    causal_run_dir = (
        Path(args.causal_run_dir).expanduser().resolve()
        if str(args.causal_run_dir).strip()
        else _find_latest_causal_run_dir(project_root)
    )
    causal_summary = _load_json(causal_run_dir / "summary.json")
    all_method_scores = pl.read_csv(causal_run_dir / "all_method_scores.csv")
    root_configs = _build_root_configs(project_root)
    if requested_roots:
        unknown_roots = sorted(requested_roots - set(root_configs))
        if unknown_roots:
            raise ValueError(f"Unknown roots requested: {unknown_roots}")
        root_configs = {
            root: cfg for root, cfg in root_configs.items() if root in requested_roots
        }

    workflow_manifest: dict[str, Any] = {}
    root_profile_rows: list[dict[str, Any]] = []
    eval_truth_by_root: dict[str, pl.DataFrame] = {}
    ranking_by_root: dict[str, list[dict[str, Any]]] = {}
    base_model_metrics_rows: list[dict[str, Any]] = []

    for root, root_cfg in root_configs.items():
        causal_root_meta = dict(causal_summary["roots"][root])
        causal_scores = all_method_scores.filter(pl.col("root") == root)
        eval_batches: set[int] = set()
        for row_path in causal_scores["row_path"].to_list():
            df = pl.read_parquet(row_path).select("pred_batch").unique()
            batches = set(int(v) for v in df["pred_batch"].to_list())
            eval_batches = batches if not eval_batches else (eval_batches & batches)
        ranking_rows = _load_action_key_ranking_from_stage1(root_cfg.unit_dir)
        ranking_by_root[root] = ranking_rows
        workflow_manifest[root] = _workflow_manifest_for_root(
            root_cfg,
            causal_root_meta=causal_root_meta,
            eval_batches=eval_batches,
            ranking_rows=ranking_rows,
        )
        root_profile, eval_truth = _build_root_profile(
            root_cfg=root_cfg,
            causal_root_meta=causal_root_meta,
            causal_scores=causal_scores,
            eval_batches=eval_batches,
            ranking_rows=ranking_rows,
        )
        root_profile_rows.append(root_profile)
        eval_truth_by_root[root] = eval_truth

        combo_match_df = pl.read_parquet(Path(str(causal_root_meta["combo_match_pred_rows"])))
        dominant_plus_near = _select_root_topk_action_keys(ranking_rows, args.topk_action_keys)
        for action_key in dominant_plus_near:
            action_df = combo_match_df.filter(pl.col("action_key") == action_key)
            metrics = _evaluate_prediction_frame(
                action_df,
                prediction_col="y_pred",
                prediction_type="class",
                eval_batches=eval_batches,
            )
            base_model_metrics_rows.append(
                _flatten_metrics_row(root, "base_model", action_key, metrics)
            )

    workflow_manifest_path = output_root / "workflow_manifest.json"
    workflow_manifest_path.write_text(
        json.dumps(workflow_manifest, indent=2), encoding="utf-8"
    )

    root_profiles = pl.DataFrame(root_profile_rows).sort("root")
    root_profiles_csv = output_root / "root_profiles.csv"
    root_profiles_json = output_root / "root_profiles.json"
    root_profiles_parquet = output_root / "root_profiles.parquet"
    root_profiles.write_csv(root_profiles_csv)
    root_profiles.write_parquet(root_profiles_parquet)
    root_profiles_json.write_text(
        json.dumps(root_profiles.to_dicts(), indent=2), encoding="utf-8"
    )

    causal_refresh = (
        all_method_scores.join(
            root_profiles.select(["root", "direct_baseline_directional_accuracy"]),
            on="root",
            how="left",
        )
        .with_columns(
            [
                (pl.col("directional_accuracy") - pl.col("direct_baseline_directional_accuracy")).alias(
                    "gain_vs_direct_baseline"
                ),
                (pl.col("row_coverage") >= FULL_COVERAGE_THRESHOLD).alias("is_full_coverage"),
            ]
        )
        .sort(["root", "directional_accuracy", "row_coverage"], descending=[False, True, True])
    )
    causal_refresh.write_csv(output_root / "causal_method_refresh.csv")
    causal_refresh.write_parquet(output_root / "causal_method_refresh.parquet")

    base_model_metrics_df = pl.DataFrame(base_model_metrics_rows).sort(
        ["root", "directional_accuracy"], descending=[False, True]
    )
    if not base_model_metrics_df.is_empty():
        base_model_metrics_df.write_csv(output_root / "base_model_diagnostics.csv")
        base_model_metrics_df.write_parquet(output_root / "base_model_diagnostics.parquet")

    cross_root_summary = (
        root_profiles.select(
            [
                "root",
                "best_full_coverage_method",
                "best_full_coverage_directional_accuracy",
                "best_reduced_method",
                "best_reduced_directional_accuracy",
                "direct_baseline_directional_accuracy",
                "gain_vs_direct_full_coverage",
                "gain_vs_direct_best_reduced",
                "winner_quality_pass_rate",
                "majority_direction_baseline",
            ]
        ).sort("root")
    )
    cross_root_summary.write_csv(output_root / "cross_root_summary.csv")
    cross_root_summary.write_parquet(output_root / "cross_root_summary.parquet")

    workflow_note_path = _write_markdown_workflow_note(
        output_root=output_root,
        workflow_manifest=workflow_manifest,
        root_profiles=root_profiles,
        causal_run_dir=causal_run_dir,
    )

    step2_manifests: dict[str, dict[str, Any]] = {}
    feature_quality_by_root: dict[str, pl.DataFrame] = {}
    top_features_by_root: dict[str, list[str]] = {}
    step2_aggregate_rows: list[dict[str, Any]] = []
    winner_vs_near_overlap_rows: list[pl.DataFrame] = []

    for phase in ["winner_only", "root_topk"]:
        if phase not in phases:
            continue
        phase_scope = phase
        for feature_importance_type in feature_importance_types:
            phase_rows: list[dict[str, Any]] = []
            for root, root_cfg in root_configs.items():
                print(f"[Step2] {root} scope={phase_scope} importance={feature_importance_type}")
                step2_summary = _run_step2_for_root(
                    root_cfg=root_cfg,
                    selection_scope=phase_scope,
                    feature_importance_type=feature_importance_type,
                    output_subdir=f"stage1_step2_{phase_scope}_{feature_importance_type.lower()}",
                )
                step2_manifests.setdefault(phase_scope, {}).setdefault(
                    feature_importance_type, {}
                )[root] = step2_summary
                unit_summary = step2_summary["units"].get(f"{TF}/{TARGET_COL}", {})
                artifacts = unit_summary.get("artifacts", {})
                root_scope_dir = _root_scope_type_dir(
                    output_root,
                    selection_scope=phase_scope,
                    feature_importance_type=feature_importance_type,
                    root=root,
                )
                root_scope_dir.joinpath("step2_summary.json").write_text(
                    json.dumps(unit_summary, indent=2),
                    encoding="utf-8",
                )

                artifact_keys = [
                    "feature_importance_stability",
                    "feature_noise_summary",
                    "baseline_vs_filtered_root",
                    "top_features_by_combo",
                    "action_key_ranking",
                ]
                artifact_frames: dict[str, pl.DataFrame] = {}
                for key in artifact_keys:
                    artifact_path = artifacts.get(key)
                    if artifact_path:
                        phase_rows.append(
                            {
                                "root": root,
                                "selection_scope": phase_scope,
                                "feature_importance_type": feature_importance_type,
                                "artifact_type": key,
                                "path": artifact_path,
                            }
                        )
                    art_df = _read_artifact_df(artifact_path)
                    if art_df.is_empty():
                        continue
                    artifact_frames[key] = art_df
                    enriched = art_df.with_columns(
                        [
                            pl.lit(root).alias("root"),
                            pl.lit(phase_scope).alias("selection_scope"),
                            pl.lit(feature_importance_type).alias("feature_importance_type"),
                        ]
                    )
                    artifact_frames[key] = enriched
                    step2_aggregate_rows.append(
                        {
                            "root": root,
                            "selection_scope": phase_scope,
                            "feature_importance_type": feature_importance_type,
                            "artifact_type": key,
                            "path": artifact_path,
                            "rows": int(enriched.height),
                        }
                    )
                    _write_df_if_not_empty(enriched, root_scope_dir / f"{key}.parquet")
                    _write_df_if_not_empty(enriched, root_scope_dir / f"{key}.csv")

                top_features: list[str] = []
                top_df = artifact_frames.get("top_features_by_combo", pl.DataFrame())
                if not top_df.is_empty() and "feature" in top_df.columns:
                    top_features = top_df["feature"].unique().to_list()
                    top_features_by_root[root] = sorted(
                        set(top_features_by_root.get(root, [])) | set(top_features)
                    )
                    fq = _feature_quality_rows(
                        root_cfg=root_cfg,
                        eval_batches=set(workflow_manifest[root]["causal_eval_batches"]),
                        features=top_features,
                    )
                    feature_quality_by_root[root] = _merge_feature_quality_frames(
                        feature_quality_by_root.get(root),
                        fq,
                    )
                    if root in feature_quality_by_root and not feature_quality_by_root[root].is_empty():
                        root_out_dir = output_root / "feature_quality" / _root_slug(root)
                        root_out_dir.mkdir(parents=True, exist_ok=True)
                        _write_df_if_not_empty(
                            feature_quality_by_root[root],
                            root_out_dir / f"{phase_scope}_{feature_importance_type}_feature_quality.csv",
                        )
                        _write_df_if_not_empty(
                            feature_quality_by_root[root],
                            root_out_dir / f"{phase_scope}_{feature_importance_type}_feature_quality.parquet",
                        )

                if phase_scope == "root_topk":
                    overlap_df = _build_winner_vs_near_overlap(
                        root=root,
                        feature_importance_type=feature_importance_type,
                        top_features_df=artifact_frames.get("top_features_by_combo", pl.DataFrame()),
                        ranking_df=artifact_frames.get("action_key_ranking", pl.DataFrame()),
                    )
                    if not overlap_df.is_empty():
                        winner_vs_near_overlap_rows.append(overlap_df)
                        _write_df_if_not_empty(
                            overlap_df,
                            root_scope_dir / "winner_vs_near_winner_overlap.parquet",
                        )
                        _write_df_if_not_empty(
                            overlap_df,
                            root_scope_dir / "winner_vs_near_winner_overlap.csv",
                        )

            if phase_rows:
                phase_df = pl.DataFrame(phase_rows).sort(
                    ["feature_importance_type", "root", "artifact_type"]
                )
                phase_df.write_csv(
                    output_root / f"step2_{phase_scope}_{feature_importance_type}_artifacts.csv"
                )

    if step2_aggregate_rows:
        step2_aggregate_df = pl.DataFrame(step2_aggregate_rows).sort(
            ["selection_scope", "feature_importance_type", "root", "artifact_type"]
        )
        step2_aggregate_df.write_csv(output_root / "step2_aggregate_artifacts.csv")
        step2_aggregate_df.write_parquet(output_root / "step2_aggregate_artifacts.parquet")

    if winner_vs_near_overlap_rows:
        overlap_df = pl.concat(winner_vs_near_overlap_rows, how="diagonal_relaxed").sort(
            ["feature_importance_type", "root", "compare_action_key"]
        )
        overlap_df.write_csv(output_root / "winner_vs_near_winner_overlap.csv")
        overlap_df.write_parquet(output_root / "winner_vs_near_winner_overlap.parquet")

    recommendations = _build_recommendations(
        root_profiles=root_profiles,
        feature_quality_by_root=feature_quality_by_root,
        top_features_by_root=top_features_by_root,
    )
    if not recommendations.is_empty():
        recommendations.write_csv(output_root / "recommendations.csv")
        recommendations.write_parquet(output_root / "recommendations.parquet")

    run_summary = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "output_root": str(output_root),
        "workflow_manifest": str(workflow_manifest_path),
        "root_profiles": str(root_profiles_parquet),
        "cross_root_summary": str(output_root / "cross_root_summary.csv"),
        "causal_method_refresh": str(output_root / "causal_method_refresh.csv"),
        "workflow_note": str(workflow_note_path),
        "step2_manifests": step2_manifests,
        "roots": sorted(root_configs.keys()),
        "phases": sorted(phases),
        "feature_importance_types": feature_importance_types,
    }
    (output_root / "run_summary.json").write_text(
        json.dumps(run_summary, indent=2), encoding="utf-8"
    )

    print("HTF walk-forward diagnostics complete")
    print(f"  Output root: {output_root}")
    print(f"  Workflow note: {workflow_note_path}")
    for row in cross_root_summary.to_dicts():
        print(
            f"  {row['root']}: full={row['best_full_coverage_method']} "
            f"dir_acc={row['best_full_coverage_directional_accuracy']}"
        )


if __name__ == "__main__":
    main()
