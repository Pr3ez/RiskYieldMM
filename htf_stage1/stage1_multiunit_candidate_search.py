#!/usr/bin/env python3
"""Stage-1 remaining-unit candidate discovery with Cell 14A winner-logic parity.

This script processes the 5 remaining Stage-1 units, extracts per-step winners
from prediction payloads (current + archive_legacy), aggregates combo metrics,
and builds an exact 12-candidate set per unit with deterministic fill rules.

Outputs are written to a versioned run directory only.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

DEFAULT_PROJECT_ROOT = Path("/media/przem/linux_data/RiskYieldMM (Copy)")
DEFAULT_RUN_ID = "stage1_catboost_live"
DEFAULT_MODEL_NAME = "catboost"
DEFAULT_SOURCE_SCOPE = "current+archive"
DEFAULT_TARGET_CANDIDATE_COUNT = 12
DEFAULT_FILL_MIN_SUPPORT_STEPS = 20
DEFAULT_UNITS = [
    "1m/target_breakfree",
    "5m/target_4class",
    "5m/target_breakfree",
    "15m/target_4class",
    "15m/target_breakfree",
]
SHARE_THRESHOLDS = [0.90, 0.80, 0.70, 0.60, 0.50]
ACTION_KEY_PATTERN = re.compile(r"^f(?P<f>\d+)_v(?P<v>\d+)_t(?P<t>\d+)$")


@dataclass(frozen=True)
class SnapshotPaths:
    snapshot_label: str
    combo_index_path: Path
    pred_payload_path: Path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Discover exact-12 Stage-1 candidate triplets for remaining units "
            "using current+archive winner extraction parity with Cell 14A."
        )
    )
    parser.add_argument(
        "--project-root",
        type=str,
        default=str(DEFAULT_PROJECT_ROOT),
        help=f"Project root path (default: {DEFAULT_PROJECT_ROOT})",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default=DEFAULT_RUN_ID,
        help=f"Stage-1 run id (default: {DEFAULT_RUN_ID})",
    )
    parser.add_argument(
        "--model-name",
        type=str,
        default=DEFAULT_MODEL_NAME,
        help=f"Model folder name (default: {DEFAULT_MODEL_NAME})",
    )
    parser.add_argument(
        "--units",
        nargs="*",
        default=DEFAULT_UNITS,
        help=(
            "Units to process in <timeframe>/<target> format. "
            "Can be space-separated and/or comma-separated."
        ),
    )
    parser.add_argument(
        "--source-scope",
        type=str,
        default=DEFAULT_SOURCE_SCOPE,
        choices=["current", "archive", "current+archive"],
        help=f"Snapshot source scope (default: {DEFAULT_SOURCE_SCOPE})",
    )
    parser.add_argument(
        "--target-candidate-count",
        type=int,
        default=DEFAULT_TARGET_CANDIDATE_COUNT,
        help=f"Exact candidates to select per unit (default: {DEFAULT_TARGET_CANDIDATE_COUNT})",
    )
    parser.add_argument(
        "--fill-min-support-steps",
        type=int,
        default=DEFAULT_FILL_MIN_SUPPORT_STEPS,
        help=f"Support threshold for fill candidates (default: {DEFAULT_FILL_MIN_SUPPORT_STEPS})",
    )
    parser.add_argument(
        "--output-tag",
        type=str,
        default="",
        help="Optional suffix added to run directory name.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-step progress.",
    )
    return parser.parse_args()


def _normalize_units(raw_units: list[str]) -> list[str]:
    units: list[str] = []
    for raw in raw_units:
        for part in str(raw).split(","):
            unit = part.strip()
            if not unit:
                continue
            if "/" not in unit:
                raise ValueError(
                    f"Invalid unit format (expected <tf>/<target>): {unit!r}"
                )
            units.append(unit)
    seen: set[str] = set()
    deduped: list[str] = []
    for unit in units:
        if unit not in seen:
            seen.add(unit)
            deduped.append(unit)
    return deduped


def _to_float(value: Any, default: float) -> float:
    if value is None:
        return default
    try:
        out = float(value)
    except Exception:
        return default
    if not math.isfinite(out):
        return default
    return out


def _safe_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _safe_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_safe_json(v) for v in value]
    if isinstance(value, tuple):
        return [_safe_json(v) for v in value]
    if isinstance(value, np.generic):
        return _safe_json(value.item())
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    return value


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_safe_json(payload), f, indent=2, ensure_ascii=False)


def _parse_batch_id(batch_dir_name: str) -> int | None:
    try:
        return int(str(batch_dir_name).split("_", 1)[1])
    except Exception:
        return None


def _target_num_classes(target: str) -> int:
    if target == "target_4class":
        return 4
    if target == "target_breakfree":
        return 3
    raise ValueError(f"Unsupported target: {target!r}")


def _target_direction_label(target: str, values: np.ndarray) -> np.ndarray:
    if target == "target_4class":
        # DOWN={0,1}, UP={2,3}
        return np.where(values >= 2, 1, 0).astype(np.int8, copy=False)
    if target == "target_breakfree":
        # UP=0, DOWN=1, HOLD=2(neutral)
        out = np.full(values.shape[0], -1, dtype=np.int8)
        out[values == 0] = 1
        out[values == 1] = 0
        return out
    raise ValueError(f"Unsupported target: {target!r}")


def _macro_f1_multiclass(
    y_true: np.ndarray, y_pred: np.ndarray, n_classes: int
) -> float:
    f1_values: list[float] = []
    for c in range(int(n_classes)):
        tp = int(((y_true == c) & (y_pred == c)).sum())
        fp = int(((y_true != c) & (y_pred == c)).sum())
        fn = int(((y_true == c) & (y_pred != c)).sum())
        if tp == 0 and fp == 0 and fn == 0:
            f1_values.append(0.0)
            continue
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (
            (2.0 * precision * recall / (precision + recall))
            if (precision + recall) > 0
            else 0.0
        )
        f1_values.append(float(f1))
    return float(np.mean(f1_values)) if f1_values else 0.0


def _cross_direction_error(
    y_true: np.ndarray, y_pred: np.ndarray, target: str
) -> float:
    if y_true.size == 0:
        return 0.0
    true_dir = _target_direction_label(target=target, values=y_true)
    pred_dir = _target_direction_label(target=target, values=y_pred)
    directional_mask = true_dir >= 0
    if not bool(directional_mask.any()):
        return 0.0
    # Opposite-direction risk on directional truth rows only.
    opp = (
        (true_dir[directional_mask] >= 0)
        & (pred_dir[directional_mask] >= 0)
        & (true_dir[directional_mask] != pred_dir[directional_mask])
    )
    return float(opp.mean())


def _probability_metrics(
    *,
    y_true: np.ndarray,
    prob_matrix: np.ndarray,
    n_classes: int,
) -> tuple[float | None, float | None, int]:
    if y_true.size == 0 or prob_matrix.size == 0:
        return None, None, 0

    valid_rows = np.isfinite(prob_matrix).all(axis=1)
    if not bool(valid_rows.any()):
        return None, None, 0

    y = y_true[valid_rows].astype(np.int64, copy=False)
    probs = prob_matrix[valid_rows].astype(np.float64, copy=True)
    class_mask = (y >= 0) & (y < int(n_classes))
    if not bool(class_mask.any()):
        return None, None, 0

    y = y[class_mask]
    probs = probs[class_mask]

    probs = np.clip(probs, 1e-12, np.inf)
    row_sums = probs.sum(axis=1, keepdims=True)
    sum_mask = row_sums[:, 0] > 0
    if not bool(sum_mask.any()):
        return None, None, 0
    probs = probs[sum_mask] / row_sums[sum_mask]
    y = y[sum_mask]
    n = int(y.shape[0])
    if n == 0:
        return None, None, 0

    idx = np.arange(n)
    logloss = float(-np.log(np.clip(probs[idx, y], 1e-12, 1.0)).mean())
    onehot = np.zeros((n, int(n_classes)), dtype=np.float64)
    onehot[idx, y] = 1.0
    brier = float(np.mean(np.sum((probs - onehot) ** 2, axis=1)))
    return logloss, brier, n


def _iter_snapshots(step_stage1_dir: Path, source_scope: str) -> list[SnapshotPaths]:
    snapshots: list[SnapshotPaths] = []
    include_current = source_scope in {"current", "current+archive"}
    include_archive = source_scope in {"archive", "current+archive"}

    if include_current:
        combo_idx = step_stage1_dir / "stage1_combo_index.parquet"
        pred_payload = step_stage1_dir / "stage1_pred_batch_predictions.parquet"
        if combo_idx.exists() and pred_payload.exists():
            snapshots.append(
                SnapshotPaths(
                    snapshot_label="current",
                    combo_index_path=combo_idx,
                    pred_payload_path=pred_payload,
                )
            )

    if include_archive:
        archive_root = step_stage1_dir / "archive_legacy"
        if archive_root.exists():
            for snapshot_dir in sorted(
                [p for p in archive_root.iterdir() if p.is_dir()]
            ):
                combo_idx = snapshot_dir / "stage1_combo_index.parquet"
                pred_payload = snapshot_dir / "stage1_pred_batch_predictions.parquet"
                if combo_idx.exists() and pred_payload.exists():
                    snapshots.append(
                        SnapshotPaths(
                            snapshot_label=f"archive:{snapshot_dir.name}",
                            combo_index_path=combo_idx,
                            pred_payload_path=pred_payload,
                        )
                    )
    return snapshots


def _load_step_summary(
    step_stage1_dir: Path,
) -> tuple[dict[str, Any] | None, Path | None]:
    summary_path = step_stage1_dir / "stage1_step_summary.json"
    if not summary_path.exists():
        return None, None
    try:
        with open(summary_path, encoding="utf-8") as f:
            return json.load(f), summary_path
    except Exception:
        return None, summary_path


def _snapshot_combo_metric_rows(
    snapshot: SnapshotPaths,
    *,
    target: str,
) -> tuple[list[dict[str, Any]], int, str | None]:
    try:
        combo_idx = pl.read_parquet(snapshot.combo_index_path)
        pred = pl.read_parquet(snapshot.pred_payload_path)
    except Exception as exc:
        return [], 0, f"read_error:{exc}"

    required_combo_cols = {"combo_id", "action_key"}
    if not required_combo_cols.issubset(set(combo_idx.columns)):
        return (
            [],
            0,
            f"missing_combo_cols:{sorted(required_combo_cols - set(combo_idx.columns))}",
        )

    required_pred_cols = {"combo_id", "y_true", "y_pred"}
    if not required_pred_cols.issubset(set(pred.columns)):
        return (
            [],
            0,
            f"missing_pred_cols:{sorted(required_pred_cols - set(pred.columns))}",
        )

    if "scope" in pred.columns:
        pred = pred.filter(pl.col("scope") == "pred_batch")
    if pred.is_empty():
        return [], 0, None

    combo_map = (
        combo_idx.select(
            [
                pl.col("combo_id").cast(pl.Int64, strict=False),
                pl.col("action_key").cast(pl.Utf8, strict=False),
            ]
        )
        .drop_nulls(["combo_id"])
        .unique(subset=["combo_id"], keep="first")
    )
    pred = pred.with_columns(pl.col("combo_id").cast(pl.Int64, strict=False))
    pred = pred.drop_nulls(["combo_id", "y_true", "y_pred"])
    if pred.is_empty():
        return [], 0, None

    if "action_key" in pred.columns:
        pred = pred.with_columns(pl.col("action_key").cast(pl.Utf8, strict=False))
        pred = pred.join(combo_map, on="combo_id", how="left", suffix="_idx")
        pred = pred.with_columns(
            pl.coalesce([pl.col("action_key"), pl.col("action_key_idx")]).alias(
                "action_key"
            )
        ).drop("action_key_idx")
    else:
        pred = pred.join(combo_map, on="combo_id", how="left")

    pred = pred.drop_nulls(["action_key", "y_true", "y_pred"])
    if pred.is_empty():
        return [], 0, None

    n_classes = _target_num_classes(target)
    prob_cols = [f"prob_class_{i}" for i in range(n_classes)]
    prob_cols_available = all(col in pred.columns for col in prob_cols)

    rows: list[dict[str, Any]] = []
    combo_instances = 0
    for combo_key, group in pred.group_by("combo_id", maintain_order=True):
        combo_id = int(combo_key[0] if isinstance(combo_key, tuple) else combo_key)
        action_key = group["action_key"][0]
        if action_key in (None, ""):
            continue
        y_true = group["y_true"].cast(pl.Int16, strict=False).to_numpy()
        y_pred = group["y_pred"].cast(pl.Int16, strict=False).to_numpy()
        if y_true.size == 0:
            continue

        combo_instances += 1
        acc = float((y_true == y_pred).mean())
        macro_f1 = _macro_f1_multiclass(
            y_true=y_true, y_pred=y_pred, n_classes=n_classes
        )
        cross_error = _cross_direction_error(
            y_true=y_true, y_pred=y_pred, target=target
        )
        logloss: float | None = None
        brier_score: float | None = None
        prob_rows: int = 0
        if prob_cols_available:
            prob_matrix = np.column_stack(
                [
                    group[col].cast(pl.Float64, strict=False).to_numpy()
                    for col in prob_cols
                ]
            )
            logloss, brier_score, prob_rows = _probability_metrics(
                y_true=y_true,
                prob_matrix=prob_matrix,
                n_classes=n_classes,
            )
        rows.append(
            {
                "combo_id": combo_id,
                "action_key": str(action_key),
                "accuracy": acc,
                "macro_f1": macro_f1,
                "cross_direction_error": cross_error,
                "logloss": logloss,
                "brier_score": brier_score,
                "prob_rows": int(prob_rows),
                "pred_rows": int(y_true.size),
                "snapshot": snapshot.snapshot_label,
            }
        )
    return rows, combo_instances, None


def _is_better_step_action_record(
    new_row: dict[str, Any], prev_row: dict[str, Any]
) -> bool:
    new_key = (
        _to_float(new_row.get("accuracy"), -1e18),
        _to_float(new_row.get("macro_f1"), -1e18),
        -_to_float(new_row.get("cross_direction_error"), 1e18),
        -_to_float(new_row.get("logloss"), 1e18),
        -_to_float(new_row.get("brier_score"), 1e18),
        _to_float(new_row.get("prob_rows"), 0.0),
        int(new_row.get("pred_rows") or 0),
        -int(new_row.get("combo_id") or 0),
    )
    prev_key = (
        _to_float(prev_row.get("accuracy"), -1e18),
        _to_float(prev_row.get("macro_f1"), -1e18),
        -_to_float(prev_row.get("cross_direction_error"), 1e18),
        -_to_float(prev_row.get("logloss"), 1e18),
        -_to_float(prev_row.get("brier_score"), 1e18),
        _to_float(prev_row.get("prob_rows"), 0.0),
        int(prev_row.get("pred_rows") or 0),
        -int(prev_row.get("combo_id") or 0),
    )
    return new_key > prev_key


def _pick_step_winner(step_best_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not step_best_rows:
        return None
    ordered = sorted(
        step_best_rows,
        key=lambda r: (
            -_to_float(r.get("accuracy"), -1e18),
            -_to_float(r.get("macro_f1"), -1e18),
            _to_float(r.get("cross_direction_error"), 1e18),
            _to_float(r.get("logloss"), 1e18),
            _to_float(r.get("brier_score"), 1e18),
            str(r.get("action_key") or ""),
        ),
    )
    winner = dict(ordered[0])
    winner["winner_selection_scope"] = "all_tested_combos_current_plus_archive"
    return winner


def _build_combo_stats(
    *,
    winners_df: pl.DataFrame,
    combo_metrics_df: pl.DataFrame,
    n_steps: int,
) -> pl.DataFrame:
    combo_schema = {
        "action_key": pl.Utf8,
        "steps_seen": pl.Int64,
        "all_steps_accuracy_mean": pl.Float64,
        "all_steps_macro_f1_mean": pl.Float64,
        "all_steps_cross_direction_error_mean": pl.Float64,
        "all_steps_logloss_mean": pl.Float64,
        "all_steps_brier_score_mean": pl.Float64,
        "all_steps_prob_rows_sum": pl.Int64,
        "all_steps_acc_ge_090_share": pl.Float64,
        "all_steps_acc_ge_080_share": pl.Float64,
        "all_steps_acc_ge_070_share": pl.Float64,
        "all_steps_acc_ge_060_share": pl.Float64,
        "all_steps_acc_ge_050_share": pl.Float64,
        "winner_wins": pl.Int64,
        "winner_share": pl.Float64,
        "winner_accuracy_mean": pl.Float64,
        "winner_accuracy_median": pl.Float64,
        "winner_accuracy_min": pl.Float64,
        "winner_accuracy_p90": pl.Float64,
        "winner_accuracy_max": pl.Float64,
        "winner_macro_f1_mean": pl.Float64,
        "winner_cross_direction_error_mean": pl.Float64,
        "winner_logloss_mean": pl.Float64,
        "winner_brier_score_mean": pl.Float64,
        "winner_prob_rows_sum": pl.Int64,
        "winner_acc_ge_090_share": pl.Float64,
        "winner_acc_ge_080_share": pl.Float64,
        "winner_acc_ge_070_share": pl.Float64,
        "winner_acc_ge_060_share": pl.Float64,
        "winner_acc_ge_050_share": pl.Float64,
    }
    if combo_metrics_df.is_empty():
        return pl.DataFrame(schema=combo_schema)

    combo_agg = combo_metrics_df.group_by("action_key").agg(
        [
            pl.len().alias("steps_seen"),
            pl.col("accuracy").mean().alias("all_steps_accuracy_mean"),
            pl.col("macro_f1").mean().alias("all_steps_macro_f1_mean"),
            pl.col("cross_direction_error")
            .mean()
            .alias("all_steps_cross_direction_error_mean"),
            pl.col("logloss").mean().alias("all_steps_logloss_mean"),
            pl.col("brier_score").mean().alias("all_steps_brier_score_mean"),
            pl.col("prob_rows").sum().alias("all_steps_prob_rows_sum"),
            (pl.col("accuracy") >= 0.90).mean().alias("all_steps_acc_ge_090_share"),
            (pl.col("accuracy") >= 0.80).mean().alias("all_steps_acc_ge_080_share"),
            (pl.col("accuracy") >= 0.70).mean().alias("all_steps_acc_ge_070_share"),
            (pl.col("accuracy") >= 0.60).mean().alias("all_steps_acc_ge_060_share"),
            (pl.col("accuracy") >= 0.50).mean().alias("all_steps_acc_ge_050_share"),
        ]
    )

    winner_only = winners_df.drop_nulls(["winner_combo_key", "winner_accuracy"])
    if winner_only.is_empty():
        winner_agg = pl.DataFrame(
            schema={
                "action_key": pl.Utf8,
                "winner_wins": pl.Int64,
                "winner_accuracy_mean": pl.Float64,
                "winner_accuracy_median": pl.Float64,
                "winner_accuracy_min": pl.Float64,
                "winner_accuracy_p90": pl.Float64,
                "winner_accuracy_max": pl.Float64,
                "winner_macro_f1_mean": pl.Float64,
                "winner_cross_direction_error_mean": pl.Float64,
                "winner_logloss_mean": pl.Float64,
                "winner_brier_score_mean": pl.Float64,
                "winner_prob_rows_sum": pl.Int64,
                "winner_acc_ge_090_share": pl.Float64,
                "winner_acc_ge_080_share": pl.Float64,
                "winner_acc_ge_070_share": pl.Float64,
                "winner_acc_ge_060_share": pl.Float64,
                "winner_acc_ge_050_share": pl.Float64,
            }
        )
    else:
        winner_agg = (
            winner_only.group_by("winner_combo_key")
            .agg(
                [
                    pl.len().alias("winner_wins"),
                    pl.col("winner_accuracy").mean().alias("winner_accuracy_mean"),
                    pl.col("winner_accuracy").median().alias("winner_accuracy_median"),
                    pl.col("winner_accuracy").min().alias("winner_accuracy_min"),
                    pl.col("winner_accuracy")
                    .quantile(0.90)
                    .alias("winner_accuracy_p90"),
                    pl.col("winner_accuracy").max().alias("winner_accuracy_max"),
                    pl.col("winner_macro_f1").mean().alias("winner_macro_f1_mean"),
                    pl.col("winner_cross_direction_error")
                    .mean()
                    .alias("winner_cross_direction_error_mean"),
                    pl.col("winner_logloss").mean().alias("winner_logloss_mean"),
                    pl.col("winner_brier_score")
                    .mean()
                    .alias("winner_brier_score_mean"),
                    pl.col("winner_prob_rows").sum().alias("winner_prob_rows_sum"),
                    (pl.col("winner_accuracy") >= 0.90)
                    .mean()
                    .alias("winner_acc_ge_090_share"),
                    (pl.col("winner_accuracy") >= 0.80)
                    .mean()
                    .alias("winner_acc_ge_080_share"),
                    (pl.col("winner_accuracy") >= 0.70)
                    .mean()
                    .alias("winner_acc_ge_070_share"),
                    (pl.col("winner_accuracy") >= 0.60)
                    .mean()
                    .alias("winner_acc_ge_060_share"),
                    (pl.col("winner_accuracy") >= 0.50)
                    .mean()
                    .alias("winner_acc_ge_050_share"),
                ]
            )
            .rename({"winner_combo_key": "action_key"})
        )

    n_steps_safe = float(max(int(n_steps), 1))
    merged = (
        combo_agg.join(winner_agg, on="action_key", how="left")
        .with_columns(
            [
                pl.col("winner_wins").fill_null(0).cast(pl.Int64),
                pl.col("winner_acc_ge_090_share").fill_null(0.0),
                pl.col("winner_acc_ge_080_share").fill_null(0.0),
                pl.col("winner_acc_ge_070_share").fill_null(0.0),
                pl.col("winner_acc_ge_060_share").fill_null(0.0),
                pl.col("winner_acc_ge_050_share").fill_null(0.0),
                pl.col("winner_prob_rows_sum").fill_null(0).cast(pl.Int64),
            ]
        )
        .with_columns(
            (pl.col("winner_wins") / pl.lit(n_steps_safe)).alias("winner_share")
        )
        .sort(
            ["winner_wins", "all_steps_accuracy_mean", "action_key"],
            descending=[True, True, False],
        )
    )
    return merged.select(list(combo_schema.keys()))


def _parse_action_triplet(action_key: str) -> tuple[int, int, int] | None:
    m = ACTION_KEY_PATTERN.match(str(action_key))
    if not m:
        return None
    return (
        int(m.group("f")),
        int(m.group("v")),
        int(m.group("t")),
    )


def _winner_rank_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        -int(row.get("winner_wins") or 0),
        -_to_float(row.get("winner_accuracy_mean"), -1e18),
        -_to_float(row.get("all_steps_accuracy_mean"), -1e18),
        -_to_float(row.get("all_steps_macro_f1_mean"), -1e18),
        _to_float(row.get("all_steps_cross_direction_error_mean"), 1e18),
        _to_float(row.get("all_steps_logloss_mean"), 1e18),
        _to_float(row.get("all_steps_brier_score_mean"), 1e18),
        str(row.get("action_key") or ""),
    )


def _fill_rank_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        -_to_float(row.get("all_steps_accuracy_mean"), -1e18),
        -_to_float(row.get("all_steps_macro_f1_mean"), -1e18),
        _to_float(row.get("all_steps_cross_direction_error_mean"), 1e18),
        _to_float(row.get("all_steps_logloss_mean"), 1e18),
        _to_float(row.get("all_steps_brier_score_mean"), 1e18),
        -int(row.get("steps_seen") or 0),
        str(row.get("action_key") or ""),
    )


def _select_candidate12(
    *,
    combo_stats_df: pl.DataFrame,
    target_count: int,
    min_support_steps: int,
) -> tuple[pl.DataFrame, pl.DataFrame, dict[str, Any]]:
    candidate_schema = {
        "candidate_rank": pl.Int64,
        "action_key": pl.Utf8,
        "fold_count": pl.Int64,
        "val_batches_per_fold": pl.Int64,
        "train_batches_per_fold": pl.Int64,
        "candidate_source": pl.Utf8,
        "steps_seen": pl.Int64,
        "winner_wins": pl.Int64,
        "winner_share": pl.Float64,
        "winner_accuracy_mean": pl.Float64,
        "all_steps_accuracy_mean": pl.Float64,
        "all_steps_macro_f1_mean": pl.Float64,
        "all_steps_cross_direction_error_mean": pl.Float64,
        "all_steps_logloss_mean": pl.Float64,
        "all_steps_brier_score_mean": pl.Float64,
    }
    rejection_schema = {
        "action_key": pl.Utf8,
        "is_winner": pl.Boolean,
        "steps_seen": pl.Int64,
        "winner_wins": pl.Int64,
        "all_steps_accuracy_mean": pl.Float64,
        "all_steps_macro_f1_mean": pl.Float64,
        "all_steps_cross_direction_error_mean": pl.Float64,
        "all_steps_logloss_mean": pl.Float64,
        "all_steps_brier_score_mean": pl.Float64,
        "rejection_reason": pl.Utf8,
    }
    if combo_stats_df.is_empty():
        raise RuntimeError("Cannot select candidates: combo_stats_df is empty.")

    rows = combo_stats_df.to_dicts()
    winners = [r for r in rows if int(r.get("winner_wins") or 0) > 0]
    non_winners = [r for r in rows if int(r.get("winner_wins") or 0) == 0]
    winners.sort(key=_winner_rank_key)
    non_winners.sort(key=_fill_rank_key)

    selected_rows: list[dict[str, Any]] = []
    selected_keys: set[str] = set()
    invalid_action_keys: set[str] = set()
    source_counts = {
        "winner": 0,
        "fill_non_winner": 0,
        "fill_non_winner_relaxed_support": 0,
    }
    support_relaxed_used = False

    def try_add(row: dict[str, Any], source: str) -> bool:
        action_key = str(row.get("action_key") or "")
        if not action_key or action_key in selected_keys:
            return False
        triplet = _parse_action_triplet(action_key)
        if triplet is None:
            invalid_action_keys.add(action_key)
            return False
        source_counts[source] = int(source_counts.get(source, 0)) + 1
        selected_keys.add(action_key)
        selected_rows.append(
            {
                "candidate_rank": len(selected_rows) + 1,
                "action_key": action_key,
                "fold_count": int(triplet[0]),
                "val_batches_per_fold": int(triplet[1]),
                "train_batches_per_fold": int(triplet[2]),
                "candidate_source": source,
                "steps_seen": int(row.get("steps_seen") or 0),
                "winner_wins": int(row.get("winner_wins") or 0),
                "winner_share": _to_float(row.get("winner_share"), 0.0),
                "winner_accuracy_mean": _to_float(row.get("winner_accuracy_mean"), 0.0),
                "all_steps_accuracy_mean": _to_float(
                    row.get("all_steps_accuracy_mean"), 0.0
                ),
                "all_steps_macro_f1_mean": _to_float(
                    row.get("all_steps_macro_f1_mean"), 0.0
                ),
                "all_steps_cross_direction_error_mean": _to_float(
                    row.get("all_steps_cross_direction_error_mean"),
                    1.0,
                ),
                "all_steps_logloss_mean": (
                    _to_float(row.get("all_steps_logloss_mean"), 0.0)
                    if row.get("all_steps_logloss_mean") is not None
                    else None
                ),
                "all_steps_brier_score_mean": (
                    _to_float(row.get("all_steps_brier_score_mean"), 0.0)
                    if row.get("all_steps_brier_score_mean") is not None
                    else None
                ),
            }
        )
        return True

    for row in winners:
        if len(selected_rows) >= target_count:
            break
        try_add(row, "winner")

    if len(selected_rows) < target_count:
        for row in non_winners:
            if len(selected_rows) >= target_count:
                break
            if int(row.get("steps_seen") or 0) < int(min_support_steps):
                continue
            try_add(row, "fill_non_winner")

    if len(selected_rows) < target_count:
        support_relaxed_used = True
        for row in non_winners:
            if len(selected_rows) >= target_count:
                break
            if str(row.get("action_key") or "") in selected_keys:
                continue
            try_add(row, "fill_non_winner_relaxed_support")

    if len(selected_rows) != int(target_count):
        raise RuntimeError(
            "Unable to produce exact candidate count. "
            f"selected={len(selected_rows)}, target={target_count}, "
            f"invalid_action_keys={len(invalid_action_keys)}."
        )

    candidate_df = (
        pl.DataFrame(selected_rows).cast(candidate_schema).sort("candidate_rank")
    )
    if candidate_df["action_key"].n_unique() != len(candidate_df):
        raise RuntimeError("Duplicate action_key detected in candidate selection.")

    rejection_rows: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda r: str(r.get("action_key") or "")):
        action_key = str(row.get("action_key") or "")
        if not action_key or action_key in selected_keys:
            continue
        triplet = _parse_action_triplet(action_key)
        winner_wins = int(row.get("winner_wins") or 0)
        steps_seen = int(row.get("steps_seen") or 0)
        if triplet is None:
            reason = "invalid_action_key_format"
        elif winner_wins == 0 and steps_seen < int(min_support_steps):
            reason = "low_support"
        else:
            reason = "not_top_ranked"
        rejection_rows.append(
            {
                "action_key": action_key,
                "is_winner": bool(winner_wins > 0),
                "steps_seen": steps_seen,
                "winner_wins": winner_wins,
                "all_steps_accuracy_mean": _to_float(
                    row.get("all_steps_accuracy_mean"), 0.0
                ),
                "all_steps_macro_f1_mean": _to_float(
                    row.get("all_steps_macro_f1_mean"), 0.0
                ),
                "all_steps_cross_direction_error_mean": _to_float(
                    row.get("all_steps_cross_direction_error_mean"),
                    1.0,
                ),
                "all_steps_logloss_mean": (
                    _to_float(row.get("all_steps_logloss_mean"), 0.0)
                    if row.get("all_steps_logloss_mean") is not None
                    else None
                ),
                "all_steps_brier_score_mean": (
                    _to_float(row.get("all_steps_brier_score_mean"), 0.0)
                    if row.get("all_steps_brier_score_mean") is not None
                    else None
                ),
                "rejection_reason": reason,
            }
        )
    rejections_df = (
        pl.DataFrame(rejection_rows)
        .cast(rejection_schema)
        .sort(["rejection_reason", "action_key"])
        if rejection_rows
        else pl.DataFrame(schema=rejection_schema)
    )

    selection_meta = {
        "winners_total": int(len(winners)),
        "winners_selected": int(source_counts["winner"]),
        "fill_non_winner_selected": int(source_counts["fill_non_winner"]),
        "fill_non_winner_relaxed_selected": int(
            source_counts["fill_non_winner_relaxed_support"]
        ),
        "support_relaxed_used": bool(support_relaxed_used),
        "invalid_action_key_count": int(len(invalid_action_keys)),
        "invalid_action_keys": sorted(invalid_action_keys),
    }
    return candidate_df, rejections_df, selection_meta


def _build_share_map(series: pl.Series) -> dict[str, float]:
    shares: dict[str, float] = {}
    for thr in SHARE_THRESHOLDS:
        shares[f"{thr:.2f}"] = float((series >= thr).mean()) if len(series) else 0.0
    return shares


def _process_unit(
    *,
    project_root: Path,
    run_id: str,
    model_name: str,
    unit: str,
    source_scope: str,
    target_candidate_count: int,
    fill_min_support_steps: int,
    verbose: bool,
) -> dict[str, Any]:
    tf, target = unit.split("/", 1)
    unit_dir = (
        project_root
        / "data"
        / "htf_backtest_results"
        / run_id
        / model_name
        / tf
        / target
    )
    if not unit_dir.exists():
        raise FileNotFoundError(f"Unit directory does not exist: {unit_dir}")

    step_dirs = [p for p in unit_dir.glob("batch_*") if p.is_dir()]
    step_dirs = sorted(
        step_dirs,
        key=lambda p: (
            _parse_batch_id(p.name) is None,
            _parse_batch_id(p.name),
            p.name,
        ),
    )
    if not step_dirs:
        raise RuntimeError(f"No batch_* directories found for unit: {unit}")

    winner_rows: list[dict[str, Any]] = []
    step_best_combo_rows: list[dict[str, Any]] = []
    missing_payload_pred_batches: list[int] = []
    missing_summary_pred_batches: list[int] = []
    snapshot_error_rows: list[dict[str, Any]] = []

    for idx, batch_dir in enumerate(step_dirs, start=1):
        pred_batch = _parse_batch_id(batch_dir.name)
        if pred_batch is None:
            continue
        stage1_dir = batch_dir / "stage1"
        summary, summary_path = _load_step_summary(stage1_dir)
        if summary_path is None:
            missing_summary_pred_batches.append(int(pred_batch))

        snapshots = _iter_snapshots(stage1_dir, source_scope=source_scope)
        snapshots_seen = 0
        combo_instances_seen = 0
        best_by_action: dict[str, dict[str, Any]] = {}

        for snapshot in snapshots:
            snapshots_seen += 1
            snapshot_rows, combo_instances, snapshot_error = (
                _snapshot_combo_metric_rows(
                    snapshot,
                    target=target,
                )
            )
            combo_instances_seen += int(combo_instances)
            if snapshot_error is not None:
                snapshot_error_rows.append(
                    {
                        "pred_batch": int(pred_batch),
                        "snapshot": snapshot.snapshot_label,
                        "error": snapshot_error,
                    }
                )
            for row in snapshot_rows:
                action_key = str(row.get("action_key") or "")
                if not action_key:
                    continue
                prev = best_by_action.get(action_key)
                if prev is None or _is_better_step_action_record(row, prev):
                    best_by_action[action_key] = row

        step_best_rows = sorted(
            best_by_action.values(),
            key=lambda r: str(r.get("action_key") or ""),
        )
        for row in step_best_rows:
            step_best_combo_rows.append(
                {
                    "pred_batch": int(pred_batch),
                    "action_key": str(row.get("action_key") or ""),
                    "combo_id": int(row.get("combo_id") or 0),
                    "accuracy": _to_float(row.get("accuracy"), 0.0),
                    "macro_f1": _to_float(row.get("macro_f1"), 0.0),
                    "cross_direction_error": _to_float(
                        row.get("cross_direction_error"), 1.0
                    ),
                    "logloss": (
                        _to_float(row.get("logloss"), 0.0)
                        if row.get("logloss") is not None
                        else None
                    ),
                    "brier_score": (
                        _to_float(row.get("brier_score"), 0.0)
                        if row.get("brier_score") is not None
                        else None
                    ),
                    "prob_rows": int(row.get("prob_rows") or 0),
                    "pred_rows": int(row.get("pred_rows") or 0),
                    "snapshot": str(row.get("snapshot") or ""),
                    "step_stage1_dir": str(stage1_dir),
                }
            )

        winner = _pick_step_winner(step_best_rows)
        if winner is None:
            missing_payload_pred_batches.append(int(pred_batch))

        winner_rows.append(
            {
                "pred_batch": int(pred_batch),
                "summary_winner_combo_key": (
                    str(summary.get("winner_combo_key"))
                    if isinstance(summary, dict)
                    and summary.get("winner_combo_key") not in (None, "")
                    else None
                ),
                "winner_combo_key": (
                    str(winner.get("action_key"))
                    if winner is not None and winner.get("action_key") not in (None, "")
                    else None
                ),
                "winner_accuracy": (
                    _to_float(winner.get("accuracy"), 0.0)
                    if winner is not None
                    else None
                ),
                "winner_macro_f1": (
                    _to_float(winner.get("macro_f1"), 0.0)
                    if winner is not None
                    else None
                ),
                "winner_cross_direction_error": (
                    _to_float(winner.get("cross_direction_error"), 1.0)
                    if winner is not None
                    else None
                ),
                "winner_logloss": (
                    _to_float(winner.get("logloss"), 0.0)
                    if winner is not None and winner.get("logloss") is not None
                    else None
                ),
                "winner_brier_score": (
                    _to_float(winner.get("brier_score"), 0.0)
                    if winner is not None and winner.get("brier_score") is not None
                    else None
                ),
                "winner_prob_rows": int(winner.get("prob_rows") or 0)
                if winner is not None
                else None,
                "winner_pred_rows": int(winner.get("pred_rows") or 0)
                if winner is not None
                else None,
                "winner_source_snapshot": str(winner.get("snapshot") or "")
                if winner is not None
                else None,
                "winner_selection_source": (
                    "pred_payload_all_tested_combos"
                    if winner is not None
                    else "missing_payload"
                ),
                "unique_actions_tested": int(len(step_best_rows)),
                "combo_instances_seen": int(combo_instances_seen),
                "snapshots_seen": int(snapshots_seen),
                "has_payload": bool(winner is not None),
                "summary_quality_pass": (
                    bool(summary.get("quality_pass"))
                    if isinstance(summary, dict)
                    else None
                ),
                "summary_quality_unresolved": (
                    bool(summary.get("quality_unresolved"))
                    if isinstance(summary, dict)
                    else None
                ),
                "summary_probe_exhausted": (
                    bool(summary.get("probe_exhausted"))
                    if isinstance(summary, dict)
                    else None
                ),
                "summary_runtime_s": (
                    _to_float(summary.get("runtime_s"), 0.0)
                    if isinstance(summary, dict)
                    and summary.get("runtime_s") is not None
                    else None
                ),
                "summary_path": str(summary_path) if summary_path is not None else None,
                "step_stage1_dir": str(stage1_dir),
            }
        )

        if verbose and (idx == 1 or idx % 50 == 0 or idx == len(step_dirs)):
            print(
                f"[{unit}] step {idx}/{len(step_dirs)} pred_batch={pred_batch} "
                f"tested_actions={len(step_best_rows)} winner={winner.get('action_key') if winner else 'None'}"
            )

    winners_schema = {
        "pred_batch": pl.Int64,
        "step_idx": pl.Int64,
        "summary_winner_combo_key": pl.Utf8,
        "winner_combo_key": pl.Utf8,
        "winner_accuracy": pl.Float64,
        "winner_macro_f1": pl.Float64,
        "winner_cross_direction_error": pl.Float64,
        "winner_logloss": pl.Float64,
        "winner_brier_score": pl.Float64,
        "winner_prob_rows": pl.Int64,
        "winner_pred_rows": pl.Int64,
        "winner_source_snapshot": pl.Utf8,
        "winner_selection_source": pl.Utf8,
        "unique_actions_tested": pl.Int64,
        "combo_instances_seen": pl.Int64,
        "snapshots_seen": pl.Int64,
        "has_payload": pl.Boolean,
        "summary_quality_pass": pl.Boolean,
        "summary_quality_unresolved": pl.Boolean,
        "summary_probe_exhausted": pl.Boolean,
        "summary_runtime_s": pl.Float64,
        "summary_path": pl.Utf8,
        "step_stage1_dir": pl.Utf8,
    }
    winners_df = (
        pl.DataFrame(winner_rows)
        if winner_rows
        else pl.DataFrame(
            schema={k: v for k, v in winners_schema.items() if k != "step_idx"}
        )
    )
    if not winners_df.is_empty():
        winners_df = (
            winners_df.sort("pred_batch")
            .with_row_index(name="step_idx", offset=1)
            .select(list(winners_schema.keys()))
            .cast(winners_schema)
        )

    combo_metrics_schema = {
        "pred_batch": pl.Int64,
        "action_key": pl.Utf8,
        "combo_id": pl.Int64,
        "accuracy": pl.Float64,
        "macro_f1": pl.Float64,
        "cross_direction_error": pl.Float64,
        "logloss": pl.Float64,
        "brier_score": pl.Float64,
        "prob_rows": pl.Int64,
        "pred_rows": pl.Int64,
        "snapshot": pl.Utf8,
        "step_stage1_dir": pl.Utf8,
    }
    combo_metrics_df = (
        pl.DataFrame(step_best_combo_rows).cast(combo_metrics_schema)
        if step_best_combo_rows
        else pl.DataFrame(schema=combo_metrics_schema)
    )
    if not combo_metrics_df.is_empty():
        combo_metrics_df = combo_metrics_df.sort(
            ["pred_batch", "action_key", "accuracy"],
            descending=[False, False, True],
        )

    combo_stats_df = _build_combo_stats(
        winners_df=winners_df,
        combo_metrics_df=combo_metrics_df,
        n_steps=len(step_dirs),
    )
    candidate_df, rejection_df, selection_meta = _select_candidate12(
        combo_stats_df=combo_stats_df,
        target_count=target_candidate_count,
        min_support_steps=fill_min_support_steps,
    )
    triplets = [
        [
            int(r["fold_count"]),
            int(r["val_batches_per_fold"]),
            int(r["train_batches_per_fold"]),
        ]
        for r in candidate_df.select(
            ["fold_count", "val_batches_per_fold", "train_batches_per_fold"]
        ).to_dicts()
    ]

    if len({tuple(t) for t in triplets}) != len(triplets):
        raise RuntimeError(f"Duplicate candidate triplets detected for unit {unit}.")
    if len(triplets) != target_candidate_count:
        raise RuntimeError(
            f"Unit {unit} produced {len(triplets)} candidates; expected {target_candidate_count}."
        )

    winner_accuracy_series = (
        winners_df["winner_accuracy"].fill_null(-1.0)
        if not winners_df.is_empty()
        else pl.Series([], dtype=pl.Float64)
    )
    winner_shares = _build_share_map(winner_accuracy_series)

    summary = {
        "unit": unit,
        "run_id": run_id,
        "model_name": model_name,
        "source_scope": source_scope,
        "discovered_steps": int(len(step_dirs)),
        "rows_extracted": int(len(winners_df)),
        "steps_missing_summary": int(len(missing_summary_pred_batches)),
        "steps_missing_payload": int(len(missing_payload_pred_batches)),
        "missing_payload_pred_batches": sorted(missing_payload_pred_batches),
        "missing_summary_pred_batches": sorted(missing_summary_pred_batches),
        "winners_unique_count": (
            int(winners_df["winner_combo_key"].drop_nulls().n_unique())
            if not winners_df.is_empty()
            else 0
        ),
        "target_candidate_count": int(target_candidate_count),
        "selected_candidate_count": int(len(candidate_df)),
        "selection_meta": selection_meta,
        "winner_accuracy_share_ge_threshold": winner_shares,
        "probability_metrics_coverage": {
            "combo_metric_rows": int(combo_metrics_df.height),
            "rows_with_prob_metrics": (
                int(combo_metrics_df.filter(pl.col("prob_rows") > 0).height)
                if not combo_metrics_df.is_empty()
                else 0
            ),
            "prob_rows_total": (
                int(combo_metrics_df["prob_rows"].sum())
                if not combo_metrics_df.is_empty()
                else 0
            ),
            "winner_prob_rows_total": (
                int(winners_df["winner_prob_rows"].drop_nulls().sum())
                if not winners_df.is_empty()
                else 0
            ),
        },
        "snapshot_errors_count": int(len(snapshot_error_rows)),
    }

    snapshot_error_df = (
        pl.DataFrame(snapshot_error_rows).sort(["pred_batch", "snapshot"])
        if snapshot_error_rows
        else pl.DataFrame(
            schema={"pred_batch": pl.Int64, "snapshot": pl.Utf8, "error": pl.Utf8}
        )
    )

    return {
        "unit": unit,
        "tf": tf,
        "target": target,
        "unit_dir": unit_dir,
        "winners_df": winners_df,
        "combo_metrics_df": combo_metrics_df,
        "combo_stats_df": combo_stats_df,
        "candidate_df": candidate_df,
        "rejection_df": rejection_df,
        "snapshot_error_df": snapshot_error_df,
        "triplets": triplets,
        "summary": summary,
    }


def _write_unit_outputs(
    *,
    unit_result: dict[str, Any],
    run_output_root: Path,
) -> dict[str, str]:
    tf = unit_result["tf"]
    target = unit_result["target"]
    out_dir = run_output_root / tf / target
    out_dir.mkdir(parents=True, exist_ok=True)

    winners_parquet = out_dir / "winners_all_steps_v2.parquet"
    winners_csv = out_dir / "winners_all_steps_v2.csv"
    combo_metrics_parquet = out_dir / "combo_metrics_all_tested_v2.parquet"
    combo_metrics_csv = out_dir / "combo_metrics_all_tested_v2.csv"
    candidate_parquet = out_dir / "candidate12_v2.parquet"
    candidate_csv = out_dir / "candidate12_v2.csv"
    candidate_triplets_json = out_dir / "candidate12_triplets_v2.json"
    rejections_parquet = out_dir / "candidate_selection_rejections_v2.parquet"
    rejections_csv = out_dir / "candidate_selection_rejections_v2.csv"
    combo_stats_parquet = out_dir / "combo_stats_all_tested_v2.parquet"
    combo_stats_csv = out_dir / "combo_stats_all_tested_v2.csv"
    snapshot_errors_parquet = out_dir / "snapshot_errors_v2.parquet"
    snapshot_errors_csv = out_dir / "snapshot_errors_v2.csv"
    summary_json = out_dir / "candidate_search_summary_v2.json"

    unit_result["winners_df"].write_parquet(winners_parquet)
    unit_result["winners_df"].write_csv(winners_csv)
    unit_result["combo_metrics_df"].write_parquet(combo_metrics_parquet)
    unit_result["combo_metrics_df"].write_csv(combo_metrics_csv)
    unit_result["combo_stats_df"].write_parquet(combo_stats_parquet)
    unit_result["combo_stats_df"].write_csv(combo_stats_csv)
    unit_result["candidate_df"].write_parquet(candidate_parquet)
    unit_result["candidate_df"].write_csv(candidate_csv)
    unit_result["rejection_df"].write_parquet(rejections_parquet)
    unit_result["rejection_df"].write_csv(rejections_csv)
    unit_result["snapshot_error_df"].write_parquet(snapshot_errors_parquet)
    unit_result["snapshot_error_df"].write_csv(snapshot_errors_csv)

    _write_json(
        candidate_triplets_json,
        {
            "unit": unit_result["unit"],
            "triplets": unit_result["triplets"],
            "action_keys": unit_result["candidate_df"]["action_key"].to_list(),
        },
    )

    summary_payload = dict(unit_result["summary"])
    summary_payload["artifacts"] = {
        "winners_all_steps_v2_parquet": str(winners_parquet),
        "winners_all_steps_v2_csv": str(winners_csv),
        "combo_metrics_all_tested_v2_parquet": str(combo_metrics_parquet),
        "combo_metrics_all_tested_v2_csv": str(combo_metrics_csv),
        "combo_stats_all_tested_v2_parquet": str(combo_stats_parquet),
        "combo_stats_all_tested_v2_csv": str(combo_stats_csv),
        "candidate12_v2_parquet": str(candidate_parquet),
        "candidate12_v2_csv": str(candidate_csv),
        "candidate12_triplets_v2_json": str(candidate_triplets_json),
        "candidate_selection_rejections_v2_parquet": str(rejections_parquet),
        "candidate_selection_rejections_v2_csv": str(rejections_csv),
        "snapshot_errors_v2_parquet": str(snapshot_errors_parquet),
        "snapshot_errors_v2_csv": str(snapshot_errors_csv),
    }
    _write_json(summary_json, summary_payload)

    return {
        "winners_all_steps_v2_parquet": str(winners_parquet),
        "winners_all_steps_v2_csv": str(winners_csv),
        "combo_metrics_all_tested_v2_parquet": str(combo_metrics_parquet),
        "combo_metrics_all_tested_v2_csv": str(combo_metrics_csv),
        "combo_stats_all_tested_v2_parquet": str(combo_stats_parquet),
        "combo_stats_all_tested_v2_csv": str(combo_stats_csv),
        "candidate12_v2_parquet": str(candidate_parquet),
        "candidate12_v2_csv": str(candidate_csv),
        "candidate12_triplets_v2_json": str(candidate_triplets_json),
        "candidate_selection_rejections_v2_parquet": str(rejections_parquet),
        "candidate_selection_rejections_v2_csv": str(rejections_csv),
        "snapshot_errors_v2_parquet": str(snapshot_errors_parquet),
        "snapshot_errors_v2_csv": str(snapshot_errors_csv),
        "candidate_search_summary_v2_json": str(summary_json),
    }


def _build_snippet(triplet_grid: dict[str, list[list[int]]]) -> str:
    lines = ["STAGE1_TRIPLET_GRID_BY_UNIT = {"]
    for unit in sorted(triplet_grid.keys()):
        triplets = triplet_grid[unit]
        tuple_str = ", ".join(f"({t[0]}, {t[1]}, {t[2]})" for t in triplets)
        lines.append(f'    "{unit}": [{tuple_str}],')
    lines.append("}")
    return "\n".join(lines) + "\n"


def main() -> None:
    args = _parse_args()
    project_root = Path(args.project_root).expanduser().resolve()
    units = _normalize_units(list(args.units))
    run_id = str(args.run_id)
    model_name = str(args.model_name)
    source_scope = str(args.source_scope)
    target_candidate_count = int(args.target_candidate_count)
    fill_min_support_steps = int(args.fill_min_support_steps)
    verbose = bool(args.verbose)

    if target_candidate_count <= 0:
        raise ValueError("--target-candidate-count must be > 0")
    if fill_min_support_steps < 0:
        raise ValueError("--fill-min-support-steps must be >= 0")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    tag = str(args.output_tag).strip().replace(" ", "_")
    run_dir_name = f"run_{stamp}" + (f"_{tag}" if tag else "")
    run_output_root = (
        project_root
        / "data"
        / "htf_backtest_results"
        / run_id
        / model_name
        / "candidate_search_v2"
        / run_dir_name
    )
    run_output_root.mkdir(parents=True, exist_ok=False)

    print("Stage-1 multi-unit candidate discovery (v2)")
    print(f"  Project root: {project_root}")
    print(f"  Run/model: {run_id}/{model_name}")
    print(f"  Source scope: {source_scope}")
    print(f"  Units ({len(units)}): {units}")
    print(f"  Candidate target per unit: {target_candidate_count}")
    print(f"  Fill min support steps: {fill_min_support_steps}")
    print(f"  Output run dir: {run_output_root}")

    unit_run_rows: list[dict[str, Any]] = []
    unit_summaries: dict[str, Any] = {}
    combined_triplet_grid: dict[str, list[list[int]]] = {}

    for unit in units:
        print(f"\n[{unit}] processing...")
        unit_result = _process_unit(
            project_root=project_root,
            run_id=run_id,
            model_name=model_name,
            unit=unit,
            source_scope=source_scope,
            target_candidate_count=target_candidate_count,
            fill_min_support_steps=fill_min_support_steps,
            verbose=verbose,
        )
        artifacts = _write_unit_outputs(
            unit_result=unit_result, run_output_root=run_output_root
        )
        summary = dict(unit_result["summary"])
        summary["artifacts"] = artifacts
        unit_summaries[unit] = summary
        combined_triplet_grid[unit] = unit_result["triplets"]

        unit_run_rows.append(
            {
                "unit": unit,
                "discovered_steps": int(summary["discovered_steps"]),
                "rows_extracted": int(summary["rows_extracted"]),
                "steps_missing_summary": int(summary["steps_missing_summary"]),
                "steps_missing_payload": int(summary["steps_missing_payload"]),
                "winners_unique_count": int(summary["winners_unique_count"]),
                "selected_candidate_count": int(summary["selected_candidate_count"]),
                "winners_selected": int(summary["selection_meta"]["winners_selected"]),
                "fill_selected": int(
                    summary["selection_meta"]["fill_non_winner_selected"]
                    + summary["selection_meta"]["fill_non_winner_relaxed_selected"]
                ),
                "support_relaxed_used": bool(
                    summary["selection_meta"]["support_relaxed_used"]
                ),
                "invalid_action_key_count": int(
                    summary["selection_meta"]["invalid_action_key_count"]
                ),
                "share_winner_accuracy_ge_070": float(
                    summary["winner_accuracy_share_ge_threshold"].get("0.70", 0.0)
                ),
                "prob_rows_total": int(
                    summary["probability_metrics_coverage"]["prob_rows_total"]
                ),
            }
        )
        print(
            f"[{unit}] done: steps={summary['discovered_steps']} "
            f"winners={summary['winners_unique_count']} "
            f"candidate12={summary['selected_candidate_count']} "
            f"fill={summary['selection_meta']['fill_non_winner_selected'] + summary['selection_meta']['fill_non_winner_relaxed_selected']} "
            f"missing_payload={summary['steps_missing_payload']}"
        )

    combined_grid_json = run_output_root / "candidate_triplet_grid_remaining5_v2.json"
    snippet_txt = (
        run_output_root / "candidate_triplet_grid_remaining5_v2.py_snippet.txt"
    )
    run_table_parquet = run_output_root / "candidate_search_run_table_v2.parquet"
    run_table_csv = run_output_root / "candidate_search_run_table_v2.csv"
    run_summary_json = run_output_root / "candidate_search_run_summary_v2.json"

    _write_json(combined_grid_json, combined_triplet_grid)
    snippet_txt.write_text(_build_snippet(combined_triplet_grid), encoding="utf-8")
    run_table_df = pl.DataFrame(unit_run_rows).sort("unit")
    run_table_df.write_parquet(run_table_parquet)
    run_table_df.write_csv(run_table_csv)

    run_summary = {
        "run_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "project_root": str(project_root),
        "run_id": run_id,
        "model_name": model_name,
        "source_scope": source_scope,
        "target_candidate_count": target_candidate_count,
        "fill_min_support_steps": fill_min_support_steps,
        "units": units,
        "unit_summaries": unit_summaries,
        "artifacts": {
            "candidate_triplet_grid_remaining5_v2_json": str(combined_grid_json),
            "candidate_triplet_grid_remaining5_v2_py_snippet": str(snippet_txt),
            "candidate_search_run_table_v2_parquet": str(run_table_parquet),
            "candidate_search_run_table_v2_csv": str(run_table_csv),
            "candidate_search_run_summary_v2_json": str(run_summary_json),
        },
    }
    _write_json(run_summary_json, run_summary)

    print("\nCompleted.")
    print(f"  Combined grid JSON: {combined_grid_json}")
    print(f"  Python snippet: {snippet_txt}")
    print(f"  Run table: {run_table_parquet}")
    print(f"  Run summary: {run_summary_json}")


if __name__ == "__main__":
    main()
