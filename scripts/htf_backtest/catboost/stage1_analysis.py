"""
Stage-1 Offline Analysis (CatBoost)
===================================

Analyze isolated Stage-1 artifacts and generate candidate grid metadata
for the next Stage-1 run.

Outputs:
- stage1_meta/<model>/<run_id>/candidate_selection.json
- stage1_meta/<model>/<run_id>/pair_stats.parquet
- stage1_meta/<model>/<run_id>/fold_stats.parquet
- stage1_meta/<model>/<run_id>/combo_stats.parquet
- stage1_meta/<model>/latest_candidate_selection.json (optional copy)
"""

from __future__ import annotations

import json
import math
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import numpy as np
import polars as pl

from scripts.project_paths import resolve_project_root


def _as_int_key(value: Any) -> int:
    if isinstance(value, tuple):
        value = value[0]
    return int(value)


def _f1_macro(y_true: np.ndarray, y_pred: np.ndarray, n_classes: int) -> float:
    if y_true.size == 0:
        return 0.0
    cm = np.zeros((n_classes, n_classes), dtype=np.int64)
    np.add.at(cm, (y_true, y_pred), 1)
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


def _accuracy(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    if y_true.size == 0:
        return 0.0
    return float((y_true == y_pred).mean())


def _resolve_stage1_run_dir(
    run_id_or_path: str | Path,
    project_root: Path,
) -> Path:
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


def _load_unit_meta_from_snapshot(
    unit_dir: Path,
) -> tuple[int, list[str], str]:
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


def _primary_metric_for_unit(target: str, class_names: list[str]) -> tuple[str, str]:
    target_u = str(target).lower()
    if "breakfree" in target_u:
        return "macro_f1", "maximize"
    up_idx, down_idx = _detect_direction_indices(class_names)
    if up_idx and down_idx:
        return "cross_direction_error", "minimize"
    return "macro_f1", "maximize"


def _combo_metrics_from_predictions(
    pred_df: pl.DataFrame,
    n_classes: int,
    up_idx: set[int],
    down_idx: set[int],
) -> dict[int, dict[str, float | None]]:
    out: dict[int, dict[str, float | None]] = {}
    for combo_key, grp in pred_df.group_by("combo_id"):
        combo_id = _as_int_key(combo_key)
        y_true = grp["y_true"].to_numpy().astype(np.int32, copy=False)
        y_pred = grp["y_pred"].to_numpy().astype(np.int32, copy=False)
        out[combo_id] = {
            "accuracy": _accuracy(y_true, y_pred),
            "macro_f1": _f1_macro(y_true, y_pred, n_classes=n_classes),
            "cross_direction_error": _cross_direction_error(
                y_true, y_pred, up_indices=up_idx, down_indices=down_idx
            ),
            "n_rows": int(y_true.size),
        }
    return out


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def analyze_stage1_run(
    *,
    run_id_or_path: str | Path,
    project_root: str | Path | None = None,
    model_name: str = "catboost",
    top_pairs_per_unit: int = 10,
    top_folds_per_unit: int = 6,
    min_step_coverage: float = 0.7,
    stability_weight: float = 0.20,
    selection_source: str = "prediction",
    write_latest: bool = True,
) -> dict[str, Any]:
    """
    Analyze Stage-1 payload artifacts and generate candidate grid metadata.

    The candidate list is ranked by selected metric source and stability.
    selection_source:
    - "prediction": rank by prediction-batch performance from historical run
    - "validation": rank by fold-validation performance (meta-learning safe)
    """
    selection_source = str(selection_source).strip().lower()
    if selection_source not in {"prediction", "validation"}:
        raise ValueError(
            f"selection_source must be 'prediction' or 'validation', got {selection_source!r}"
        )
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

    unit_pair_stats_rows: list[dict[str, Any]] = []
    unit_fold_stats_rows: list[dict[str, Any]] = []
    unit_combo_stats_rows: list[dict[str, Any]] = []
    units_summary: dict[str, Any] = {}

    for tf_dir in sorted(model_dir.iterdir()):
        if not tf_dir.is_dir():
            continue
        tf = tf_dir.name
        for target_dir in sorted(tf_dir.iterdir()):
            if not target_dir.is_dir():
                continue
            unit_key = f"{tf}/{target_dir.name}"
            try:
                n_classes, class_names, target_col = _load_unit_meta_from_snapshot(
                    target_dir
                )
            except Exception:
                continue

            up_idx, down_idx = _detect_direction_indices(class_names)
            primary_metric, primary_direction = _primary_metric_for_unit(
                target_col, class_names
            )

            step_rows: list[dict[str, Any]] = []
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

                combo_df = pl.read_parquet(combo_path).filter(
                    pl.col("status") == "complete"
                )
                if len(combo_df) == 0:
                    continue
                combo_df = combo_df.select(
                    [
                        "combo_id",
                        "fold_count",
                        "val_batches_per_fold",
                        "train_batches_per_fold",
                    ]
                )

                val_df = pl.read_parquet(val_path).select(["combo_id", "y_true", "y_pred"])
                pred_df = pl.read_parquet(pred_path).select(
                    ["combo_id", "y_true", "y_pred"]
                )

                val_metrics = _combo_metrics_from_predictions(
                    val_df, n_classes=n_classes, up_idx=up_idx, down_idx=down_idx
                )
                pred_metrics = _combo_metrics_from_predictions(
                    pred_df, n_classes=n_classes, up_idx=up_idx, down_idx=down_idx
                )

                for row in combo_df.iter_rows(named=True):
                    combo_id = int(row["combo_id"])
                    if combo_id not in val_metrics or combo_id not in pred_metrics:
                        continue
                    vm = val_metrics[combo_id]
                    pm = pred_metrics[combo_id]
                    step_rows.append(
                        {
                            "unit": unit_key,
                            "timeframe": tf,
                            "target": target_col,
                            "step": step_id,
                            "combo_id": combo_id,
                            "fold_count": int(row["fold_count"]),
                            "val_batches_per_fold": int(row["val_batches_per_fold"]),
                            "train_batches_per_fold": int(row["train_batches_per_fold"]),
                            "val_accuracy": _safe_float(vm["accuracy"]),
                            "val_macro_f1": _safe_float(vm["macro_f1"]),
                            "val_cross_direction_error": _safe_float(
                                vm["cross_direction_error"]
                            ),
                            "pred_accuracy": _safe_float(pm["accuracy"]),
                            "pred_macro_f1": _safe_float(pm["macro_f1"]),
                            "pred_cross_direction_error": _safe_float(
                                pm["cross_direction_error"]
                            ),
                            "pred_rows": int(pm["n_rows"] or 0),
                        }
                    )

            if not step_rows:
                continue

            df = pl.DataFrame(step_rows)
            steps_total = int(df["step"].n_unique())
            min_steps_required = max(1, int(math.ceil(steps_total * min_step_coverage)))

            pred_col = f"pred_{primary_metric}"
            val_col = f"val_{primary_metric}"
            if pred_col not in df.columns:
                continue
            if val_col not in df.columns:
                continue

            # Track how well validation aligns with prediction-batch outcomes
            # for the unit's primary metric (for later meta-learning stages).
            val_pred_corr = None
            try:
                val_arr = df[val_col].to_numpy().astype(np.float64)
                pred_arr = df[pred_col].to_numpy().astype(np.float64)
                mask = np.isfinite(val_arr) & np.isfinite(pred_arr)
                if int(mask.sum()) >= 2:
                    val_pred_corr = float(np.corrcoef(val_arr[mask], pred_arr[mask])[0, 1])
            except Exception:
                val_pred_corr = None

            score_mean_col = "pred_mean" if selection_source == "prediction" else "val_mean"
            score_std_col = "pred_std" if selection_source == "prediction" else "val_std"

            # Per-pair aggregation
            pair_stats = (
                df.group_by(["val_batches_per_fold", "train_batches_per_fold"])
                .agg(
                    [
                        pl.len().alias("n_records"),
                        pl.col("step").n_unique().alias("steps_covered"),
                        pl.col(pred_col).mean().alias("pred_mean"),
                        pl.col(pred_col).std().alias("pred_std"),
                        pl.col(val_col).mean().alias("val_mean"),
                        pl.col(val_col).std().alias("val_std"),
                    ]
                )
                .with_columns(
                    [
                        pl.col("pred_std").fill_null(0.0),
                        pl.col("val_std").fill_null(0.0),
                        pl.col(score_mean_col).alias("score_mean"),
                        (
                            pl.col("steps_covered") >= pl.lit(min_steps_required)
                        ).alias("is_eligible"),
                    ]
                )
            )
            pair_stats = pair_stats.with_columns(pl.col(score_std_col).alias("score_std"))
            if primary_direction == "minimize":
                pair_stats = pair_stats.with_columns(
                    (
                        pl.col("score_mean")
                        + pl.lit(stability_weight) * pl.col("score_std")
                    ).alias("selection_score")
                ).sort(
                    ["is_eligible", "selection_score", "score_mean"],
                    descending=[True, False, False],
                )
            else:
                pair_stats = pair_stats.with_columns(
                    (
                        pl.col("score_mean")
                        - pl.lit(stability_weight) * pl.col("score_std")
                    ).alias("selection_score")
                ).sort(
                    ["is_eligible", "selection_score", "score_mean"],
                    descending=[True, True, True],
                )

            eligible_pairs = pair_stats.filter(pl.col("is_eligible"))
            if eligible_pairs.is_empty():
                eligible_pairs = pair_stats
            selected_pairs_df = eligible_pairs.head(int(max(1, top_pairs_per_unit)))

            # Per-fold aggregation
            fold_stats = (
                df.group_by("fold_count")
                .agg(
                    [
                        pl.len().alias("n_records"),
                        pl.col("step").n_unique().alias("steps_covered"),
                        pl.col(pred_col).mean().alias("pred_mean"),
                        pl.col(pred_col).std().alias("pred_std"),
                        pl.col(val_col).mean().alias("val_mean"),
                        pl.col(val_col).std().alias("val_std"),
                    ]
                )
                .with_columns(
                    [
                        pl.col("pred_std").fill_null(0.0),
                        pl.col("val_std").fill_null(0.0),
                        pl.col(score_mean_col).alias("score_mean"),
                        (
                            pl.col("steps_covered") >= pl.lit(min_steps_required)
                        ).alias("is_eligible"),
                    ]
                )
            )
            fold_stats = fold_stats.with_columns(pl.col(score_std_col).alias("score_std"))
            if primary_direction == "minimize":
                fold_stats = fold_stats.with_columns(
                    (
                        pl.col("score_mean")
                        + pl.lit(stability_weight) * pl.col("score_std")
                    ).alias("selection_score")
                ).sort(
                    ["is_eligible", "selection_score", "score_mean"],
                    descending=[True, False, False],
                )
            else:
                fold_stats = fold_stats.with_columns(
                    (
                        pl.col("score_mean")
                        - pl.lit(stability_weight) * pl.col("score_std")
                    ).alias("selection_score")
                ).sort(
                    ["is_eligible", "selection_score", "score_mean"],
                    descending=[True, True, True],
                )
            eligible_folds = fold_stats.filter(pl.col("is_eligible"))
            if eligible_folds.is_empty():
                eligible_folds = fold_stats
            selected_folds_df = eligible_folds.head(int(max(1, top_folds_per_unit)))

            # Persist flat stats rows for parquet outputs
            for r in pair_stats.iter_rows(named=True):
                unit_pair_stats_rows.append(
                    {
                        "unit": unit_key,
                        "timeframe": tf,
                        "target": target_col,
                        "primary_metric": primary_metric,
                        "primary_direction": primary_direction,
                        "selection_source": selection_source,
                        **r,
                    }
                )
            for r in fold_stats.iter_rows(named=True):
                unit_fold_stats_rows.append(
                    {
                        "unit": unit_key,
                        "timeframe": tf,
                        "target": target_col,
                        "primary_metric": primary_metric,
                        "primary_direction": primary_direction,
                        "selection_source": selection_source,
                        **r,
                    }
                )
            for r in df.iter_rows(named=True):
                unit_combo_stats_rows.append(r)

            selected_pairs = [
                {
                    "val_batches_per_fold": int(r["val_batches_per_fold"]),
                    "train_batches_per_fold": int(r["train_batches_per_fold"]),
                    "selection_score": float(r["selection_score"]),
                    "selection_mean": float(r["score_mean"]),
                    "selection_std": float(r["score_std"]),
                    "pred_mean": float(r["pred_mean"]),
                    "pred_std": float(r["pred_std"]),
                    "val_mean": float(r["val_mean"]),
                    "val_std": float(r["val_std"]),
                    "steps_covered": int(r["steps_covered"]),
                }
                for r in selected_pairs_df.iter_rows(named=True)
            ]
            selected_folds = [
                int(r["fold_count"]) for r in selected_folds_df.iter_rows(named=True)
            ]
            units_summary[unit_key] = {
                "timeframe": tf,
                "target": target_col,
                "n_classes": n_classes,
                "class_names": class_names,
                "primary_metric": primary_metric,
                "primary_direction": primary_direction,
                "selection_source": selection_source,
                "steps_total": steps_total,
                "min_steps_required": min_steps_required,
                "val_pred_primary_metric_corr": val_pred_corr,
                "selected_pairs": selected_pairs,
                "selected_fold_grid": sorted(set(selected_folds)),
            }

    meta_root = project_root_path / "data" / "htf_backtest_results" / "stage1_meta" / model_name
    out_dir = meta_root / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    pair_stats_df = pl.DataFrame(unit_pair_stats_rows) if unit_pair_stats_rows else pl.DataFrame()
    fold_stats_df = pl.DataFrame(unit_fold_stats_rows) if unit_fold_stats_rows else pl.DataFrame()
    combo_stats_df = pl.DataFrame(unit_combo_stats_rows) if unit_combo_stats_rows else pl.DataFrame()

    pair_stats_path = out_dir / "pair_stats.parquet"
    fold_stats_path = out_dir / "fold_stats.parquet"
    combo_stats_path = out_dir / "combo_stats.parquet"
    pair_stats_df.write_parquet(pair_stats_path)
    fold_stats_df.write_parquet(fold_stats_path)
    combo_stats_df.write_parquet(combo_stats_path)

    metadata = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "source_run_id": run_id,
        "source_run_path": str(run_dir),
        "model_name": model_name,
        "params": {
            "top_pairs_per_unit": int(top_pairs_per_unit),
            "top_folds_per_unit": int(top_folds_per_unit),
            "min_step_coverage": float(min_step_coverage),
            "stability_weight": float(stability_weight),
            "selection_source": selection_source,
        },
        "units": units_summary,
        "artifacts": {
            "pair_stats": str(pair_stats_path),
            "fold_stats": str(fold_stats_path),
            "combo_stats": str(combo_stats_path),
        },
    }
    meta_path = out_dir / "candidate_selection.json"
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2)

    if write_latest:
        latest_path = meta_root / "latest_candidate_selection.json"
        shutil.copyfile(meta_path, latest_path)
        metadata["artifacts"]["latest_candidate_selection"] = str(latest_path)

    return metadata


def load_stage1_candidate_selection(path: str | Path) -> dict[str, Any]:
    with open(path, "r") as f:
        return json.load(f)


def _combo_key_from_triplet(fold_count: int, val_batches: int, train_batches: int) -> str:
    return f"f{int(fold_count)}_v{int(val_batches)}_t{int(train_batches)}"


def _triplet_from_combo_key(combo_key: str) -> tuple[int, int, int] | None:
    m = re.match(r"^f(\d+)_v(\d+)_t(\d+)$", str(combo_key).strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def _rank_winner_key(row: dict[str, Any]) -> tuple[float, float, float, str]:
    """Winner ranking: accuracy desc, macro_f1 desc, cross_dir_error asc."""
    acc = float(row.get("accuracy", 0.0) or 0.0)
    macro = float(row.get("macro_f1", 0.0) or 0.0)
    cde = row.get("cross_direction_error")
    cde_sort = float(cde) if cde is not None else 1e9
    combo_key = str(row.get("combo_key", ""))
    return (-acc, -macro, cde_sort, combo_key)


def _compute_combo_metrics_table_from_snapshot(
    *,
    combo_path: Path,
    pred_path: Path,
    n_classes: int,
    class_names: list[str],
) -> list[dict[str, Any]]:
    combo_df = pl.read_parquet(combo_path)
    if "status" in combo_df.columns:
        combo_df = combo_df.filter(pl.col("status") == "complete")
    if combo_df.is_empty():
        return []

    cols = ["combo_id", "fold_count", "val_batches_per_fold", "train_batches_per_fold"]
    if "action_key" in combo_df.columns:
        cols.append("action_key")
    combo_df = combo_df.select([c for c in cols if c in combo_df.columns])

    pred_df = pl.read_parquet(pred_path)
    need = [c for c in ["combo_id", "y_true", "y_pred"] if c in pred_df.columns]
    if set(need) != {"combo_id", "y_true", "y_pred"}:
        return []
    pred_df = pred_df.select(["combo_id", "y_true", "y_pred"])
    if pred_df.is_empty():
        return []

    up_idx, down_idx = _detect_direction_indices(class_names)
    metrics = _combo_metrics_from_predictions(
        pred_df, n_classes=n_classes, up_idx=up_idx, down_idx=down_idx
    )
    out: list[dict[str, Any]] = []
    for row in combo_df.iter_rows(named=True):
        combo_id = int(row["combo_id"])
        m = metrics.get(combo_id)
        if m is None:
            continue
        fold_count = int(row.get("fold_count", 0) or 0)
        val_batches = int(row.get("val_batches_per_fold", 0) or 0)
        train_batches = int(row.get("train_batches_per_fold", 0) or 0)
        combo_key = str(row.get("action_key") or _combo_key_from_triplet(fold_count, val_batches, train_batches))
        out.append(
            {
                "combo_id": combo_id,
                "combo_key": combo_key,
                "fold_count": fold_count,
                "val_batches_per_fold": val_batches,
                "train_batches_per_fold": train_batches,
                "accuracy": _safe_float(m.get("accuracy")),
                "macro_f1": _safe_float(m.get("macro_f1")),
                "cross_direction_error": _safe_float(m.get("cross_direction_error")),
                "pred_rows": int(m.get("n_rows") or 0),
            }
        )
    return out


def _collect_stage1_prediction_rows(
    *,
    run_dir: Path,
    model_name: str,
    source_scope: Literal["current", "archive", "current+archive"],
) -> pl.DataFrame:
    model_dir = run_dir / model_name
    if not model_dir.exists():
        raise FileNotFoundError(f"Model directory not found: {model_dir}")

    include_current = source_scope in {"current", "current+archive"}
    include_archive = source_scope in {"archive", "current+archive"}
    rows: list[dict[str, Any]] = []

    for tf_dir in sorted([p for p in model_dir.iterdir() if p.is_dir()]):
        tf = tf_dir.name
        for target_dir in sorted([p for p in tf_dir.iterdir() if p.is_dir()]):
            try:
                n_classes, class_names, target_col = _load_unit_meta_from_snapshot(target_dir)
            except Exception:
                continue
            unit_key = f"{tf}/{target_col}"

            for batch_dir in sorted(target_dir.glob("batch_*")):
                try:
                    pred_batch = int(batch_dir.name.split("_")[1])
                except Exception:
                    continue
                stage1_dir = batch_dir / "stage1"
                if not stage1_dir.exists():
                    continue

                snapshots: list[tuple[str, str, Path, Path]] = []
                if include_current:
                    combo_path = stage1_dir / "stage1_combo_index.parquet"
                    pred_path = stage1_dir / "stage1_pred_batch_predictions.parquet"
                    if combo_path.exists() and pred_path.exists():
                        snapshots.append(("current", "current", combo_path, pred_path))
                if include_archive:
                    archive_root = stage1_dir / "archive_legacy"
                    if archive_root.exists():
                        for snap_dir in sorted([p for p in archive_root.iterdir() if p.is_dir()]):
                            combo_path = snap_dir / "stage1_combo_index.parquet"
                            pred_path = snap_dir / "stage1_pred_batch_predictions.parquet"
                            if combo_path.exists() and pred_path.exists():
                                snapshots.append(
                                    (
                                        "archive_legacy",
                                        f"archive:{snap_dir.name}",
                                        combo_path,
                                        pred_path,
                                    )
                                )

                for snapshot_source, snapshot_tag, combo_path, pred_path in snapshots:
                    try:
                        combo_rows = _compute_combo_metrics_table_from_snapshot(
                            combo_path=combo_path,
                            pred_path=pred_path,
                            n_classes=n_classes,
                            class_names=class_names,
                        )
                    except Exception:
                        continue
                    for r in combo_rows:
                        rows.append(
                            {
                                "unit": unit_key,
                                "timeframe": tf,
                                "target": target_col,
                                "pred_batch": pred_batch,
                                "snapshot_source": snapshot_source,
                                "snapshot_tag": snapshot_tag,
                                **r,
                            }
                        )

    if not rows:
        return pl.DataFrame()
    df = pl.DataFrame(rows).unique(
        subset=["unit", "pred_batch", "snapshot_tag", "combo_key"], keep="first"
    )
    return df.sort(["unit", "pred_batch", "snapshot_tag", "combo_key"])


def _evaluate_combo_set(
    *,
    contexts: dict[str, dict[str, dict[str, Any]]],
    combo_keys: list[str],
) -> dict[str, Any]:
    if not contexts:
        return {
            "mean_best_acc": 0.0,
            "cov70": 0.0,
            "cov80": 0.0,
            "n_contexts": 0,
            "high70_context_ids": set(),
        }
    best_vals: list[float] = []
    high70: set[str] = set()
    high80: set[str] = set()
    combo_set = set(combo_keys)
    for ctx_id, combo_map in contexts.items():
        vals = [
            float(combo_map[c]["accuracy"] or 0.0)
            for c in combo_set
            if c in combo_map
        ]
        best = max(vals) if vals else 0.0
        best_vals.append(best)
        if best >= 0.70:
            high70.add(ctx_id)
        if best >= 0.80:
            high80.add(ctx_id)
    n = len(best_vals)
    return {
        "mean_best_acc": float(np.mean(best_vals)) if n > 0 else 0.0,
        "cov70": float(len(high70) / n) if n > 0 else 0.0,
        "cov80": float(len(high80) / n) if n > 0 else 0.0,
        "n_contexts": n,
        "high70_context_ids": high70,
    }


def _coerce_triplet_list(value: Any) -> list[tuple[int, int, int]]:
    out: list[tuple[int, int, int]] = []
    if not isinstance(value, list):
        return out
    for item in value:
        if not isinstance(item, (list, tuple)) or len(item) != 3:
            continue
        try:
            out.append((int(item[0]), int(item[1]), int(item[2])))
        except Exception:
            continue
    return out


def build_stage1_winner_portfolio(
    *,
    run_id_or_path: str | Path,
    project_root: str | Path | None = None,
    model_name: str = "catboost",
    source_scope: Literal["current", "archive", "current+archive"] = "current+archive",
    dynamic_cap: int = 8,
    min_support_steps: int = 40,
    min_new_highwin_steps: int = 5,
    min_mean_best_gain: float = 0.002,
    min_cov70_gain: float = 0.01,
    high_accuracy_threshold: float = 0.70,
    target_high_accuracy_coverage: float = 0.95,
    overlap_penalty: float = 0.25,
    context_granularity: Literal["step", "snapshot"] = "step",
    require_70_mean_if_possible: bool = True,
    seed_size: int = 3,
    redundancy_max_mean_drop: float = 0.0005,
    redundancy_max_cov70_drop: float = 0.005,
    safety_max_mean_best_drop: float = 0.001,
    safety_max_cov70_drop: float = 0.005,
    fallback_triplet_grid_by_unit: dict[str, list[tuple[int, int, int]]] | None = None,
    write_latest: bool = True,
    verbose: bool = False,
) -> dict[str, Any]:
    """
    Build winner-focused Stage-1 combo portfolios (dynamic up to `dynamic_cap`).
    """
    if source_scope not in {"current", "archive", "current+archive"}:
        raise ValueError(f"Invalid source_scope: {source_scope!r}")
    if context_granularity not in {"step", "snapshot"}:
        raise ValueError(f"Invalid context_granularity: {context_granularity!r}")
    dynamic_cap = max(3, int(dynamic_cap))
    seed_size = max(1, min(int(seed_size), dynamic_cap))
    min_support_steps = max(1, int(min_support_steps))
    high_accuracy_threshold = float(high_accuracy_threshold)
    target_high_accuracy_coverage = float(target_high_accuracy_coverage)
    overlap_penalty = float(overlap_penalty)
    fallback_triplet_grid_by_unit = fallback_triplet_grid_by_unit or {}

    project_root_path = (
        Path(project_root).expanduser().resolve()
        if project_root is not None
        else resolve_project_root(Path(__file__))
    )
    run_dir = _resolve_stage1_run_dir(run_id_or_path, project_root=project_root_path)
    run_id = run_dir.name

    all_rows_df = _collect_stage1_prediction_rows(
        run_dir=run_dir, model_name=model_name, source_scope=source_scope
    )
    if all_rows_df.is_empty():
        raise ValueError(
            f"No Stage-1 prediction rows found for run '{run_id}' (scope={source_scope})."
        )

    portfolio_rows: list[dict[str, Any]] = []
    rejection_rows: list[dict[str, Any]] = []
    unit_summary: dict[str, Any] = {}
    autogen_map: dict[str, list[list[int]]] = {}

    for unit in sorted(all_rows_df["unit"].unique().to_list()):
        unit_df = all_rows_df.filter(pl.col("unit") == unit)
        if unit_df.is_empty():
            continue
        tf = str(unit_df["timeframe"][0])
        target_col = str(unit_df["target"][0])

        contexts: dict[str, dict[str, dict[str, Any]]] = {}
        contexts_step: dict[str, dict[str, dict[str, Any]]] = {}
        contexts_snapshot: dict[str, dict[str, dict[str, Any]]] = {}
        combo_profile: dict[str, dict[str, Any]] = {}
        combo_triplet: dict[str, tuple[int, int, int]] = {}

        # Build context table:
        # - snapshot mode: one context per (pred_batch, snapshot_tag)
        # - step mode: one context per pred_batch (best row per combo across snapshots)
        for r in unit_df.iter_rows(named=True):
            pred_batch = int(r["pred_batch"])
            snapshot_tag = str(r["snapshot_tag"])
            ctx_snapshot = f"{pred_batch}@{snapshot_tag}"
            ctx_step = str(pred_batch)
            combo_key = str(r["combo_key"])
            row = {
                "combo_key": combo_key,
                "accuracy": float(r.get("accuracy") or 0.0),
                "macro_f1": float(r.get("macro_f1") or 0.0),
                "cross_direction_error": _safe_float(r.get("cross_direction_error")),
                "fold_count": int(r.get("fold_count") or 0),
                "val_batches_per_fold": int(r.get("val_batches_per_fold") or 0),
                "train_batches_per_fold": int(r.get("train_batches_per_fold") or 0),
                "pred_batch": pred_batch,
                "snapshot_tag": snapshot_tag,
                "snapshot_source": str(r.get("snapshot_source")),
            }
            combo_triplet[combo_key] = (
                row["fold_count"],
                row["val_batches_per_fold"],
                row["train_batches_per_fold"],
            )
            if ctx_snapshot not in contexts_snapshot:
                contexts_snapshot[ctx_snapshot] = {}
            existing_s = contexts_snapshot[ctx_snapshot].get(combo_key)
            if existing_s is None or _rank_winner_key(row) < _rank_winner_key(existing_s):
                contexts_snapshot[ctx_snapshot][combo_key] = row
            if ctx_step not in contexts_step:
                contexts_step[ctx_step] = {}
            existing_p = contexts_step[ctx_step].get(combo_key)
            if existing_p is None or _rank_winner_key(row) < _rank_winner_key(existing_p):
                contexts_step[ctx_step][combo_key] = row

        contexts = contexts_step if context_granularity == "step" else contexts_snapshot
        context_ids = sorted(contexts.keys())
        n_contexts = len(context_ids)
        step_ids = sorted(
            {
                int(str(ctx).split("@", 1)[0])
                for ctx in context_ids
            }
        )

        # Winner table per context
        winner_rows: list[dict[str, Any]] = []
        for ctx_id in context_ids:
            entries = list(contexts[ctx_id].values())
            if not entries:
                continue
            winner = sorted(entries, key=_rank_winner_key)[0]
            winner_rows.append({"context_id": ctx_id, **winner})

        # Combo profile
        combo_step_support: dict[str, set[int]] = {}
        combo_winner_acc: dict[str, list[float]] = {}
        for ctx_id, cmap in contexts.items():
            step_id = int(ctx_id.split("@", 1)[0])
            for ck, entry in cmap.items():
                combo_step_support.setdefault(ck, set()).add(step_id)
                combo_profile.setdefault(ck, {})
                combo_profile[ck].setdefault("all_contexts", set()).add(ctx_id)
                if float(entry.get("accuracy", 0.0) or 0.0) >= high_accuracy_threshold:
                    combo_profile[ck].setdefault("highwin_contexts_any", set()).add(ctx_id)

        for wr in winner_rows:
            ck = str(wr["combo_key"])
            combo_winner_acc.setdefault(ck, []).append(float(wr.get("accuracy", 0.0) or 0.0))

        combo_stats: list[dict[str, Any]] = []
        for ck in sorted(combo_step_support.keys()):
            steps_seen = len(combo_step_support.get(ck, set()))
            seen_contexts = sorted(combo_profile.get(ck, {}).get("all_contexts", set()))
            all_accs = [
                float(contexts[cid][ck].get("accuracy", 0.0) or 0.0)
                for cid in seen_contexts
                if cid in contexts and ck in contexts[cid]
            ]
            combo_acc_mean = float(np.mean(all_accs)) if all_accs else 0.0
            combo_hit70_rate = (
                float(np.mean(np.asarray(all_accs) >= high_accuracy_threshold))
                if all_accs
                else 0.0
            )
            winner_accs = combo_winner_acc.get(ck, [])
            winner_count = len(winner_accs)
            winner_share = float(winner_count / n_contexts) if n_contexts > 0 else 0.0
            winner_acc_mean = float(np.mean(winner_accs)) if winner_accs else 0.0
            winner_hit70_rate = (
                float(np.mean(np.asarray(winner_accs) >= high_accuracy_threshold))
                if winner_accs
                else 0.0
            )
            seed_score = (
                0.55 * combo_acc_mean
                + 0.20 * combo_hit70_rate
                + 0.15 * winner_acc_mean
                + 0.05 * winner_hit70_rate
                + 0.15 * winner_share
            )
            fold_count, val_batches, train_batches = combo_triplet[ck]
            combo_stats.append(
                {
                    "unit": unit,
                    "timeframe": tf,
                    "target": target_col,
                    "combo_key": ck,
                    "fold_count": int(fold_count),
                    "val_batches_per_fold": int(val_batches),
                    "train_batches_per_fold": int(train_batches),
                    "steps_seen": int(steps_seen),
                    "winner_count": int(winner_count),
                    "winner_share": winner_share,
                    "combo_acc_mean": combo_acc_mean,
                    "combo_hit70_rate": combo_hit70_rate,
                    "winner_acc_mean": winner_acc_mean,
                    "winner_hit70_rate": winner_hit70_rate,
                    "seed_score": seed_score,
                    "eligible_support": bool(steps_seen >= min_support_steps),
                }
            )

        combo_stats_sorted = sorted(combo_stats, key=lambda x: x["seed_score"], reverse=True)
        eligible = [r for r in combo_stats_sorted if r["eligible_support"]]
        for r in combo_stats_sorted:
            if not r["eligible_support"]:
                rejection_rows.append(
                    {
                        "unit": unit,
                        "timeframe": tf,
                        "target": target_col,
                        "combo_key": r["combo_key"],
                        "fold_count": r["fold_count"],
                        "val_batches_per_fold": r["val_batches_per_fold"],
                        "train_batches_per_fold": r["train_batches_per_fold"],
                        "reason": "insufficient_support",
                        "detail": (
                            f"steps_seen={r['steps_seen']} < "
                            f"min_support_steps={min_support_steps}"
                        ),
                    }
                )

        # Coverage-first candidate pool:
        # prefer combos that can sustain >=threshold mean accuracy across contexts,
        # fallback to all supported combos if that pool is empty.
        high_mean_pool = [
            r
            for r in eligible
            if float(r.get("combo_acc_mean", 0.0) or 0.0) >= high_accuracy_threshold
        ]
        selection_pool = high_mean_pool if (require_70_mean_if_possible and high_mean_pool) else eligible
        if require_70_mean_if_possible and high_mean_pool:
            dropped_for_mean = [r for r in eligible if r["combo_key"] not in {x["combo_key"] for x in high_mean_pool}]
            for r in dropped_for_mean:
                rejection_rows.append(
                    {
                        "unit": unit,
                        "timeframe": tf,
                        "target": target_col,
                        "combo_key": r["combo_key"],
                        "fold_count": r["fold_count"],
                        "val_batches_per_fold": r["val_batches_per_fold"],
                        "train_batches_per_fold": r["train_batches_per_fold"],
                        "reason": "below_70_mean_filter",
                        "detail": (
                            f"combo_acc_mean={float(r.get('combo_acc_mean', 0.0) or 0.0):.6f} "
                            f"< threshold={high_accuracy_threshold:.2f}"
                        ),
                    }
                )

        selected: list[str] = []
        current_set_metrics = _evaluate_combo_set(contexts=contexts, combo_keys=selected)
        covered_high = set()
        pool_by_key = {r["combo_key"]: r for r in selection_pool}
        remaining = [r["combo_key"] for r in selection_pool]

        while len(selected) < dynamic_cap and remaining:
            best_candidate = None
            best_score = None
            best_metrics = None
            best_new_high = 0
            best_new_cov = 0.0
            for ck in remaining:
                row = pool_by_key.get(ck, {})
                high_set = set(combo_profile.get(ck, {}).get("highwin_contexts_any", set()))
                new_high = len(high_set - covered_high)
                gain_cov = float(new_high / n_contexts) if n_contexts > 0 else 0.0
                overlap = (
                    float(len(high_set & covered_high) / max(1, len(high_set)))
                    if len(high_set) > 0
                    else 1.0
                )

                trial_set = selected + [ck]
                trial_metrics = _evaluate_combo_set(contexts=contexts, combo_keys=trial_set)
                gain_mean = trial_metrics["mean_best_acc"] - current_set_metrics["mean_best_acc"]
                gain_cov70 = trial_metrics["cov70"] - current_set_metrics["cov70"]

                if selected:
                    # Keep portfolio non-overlapping: every added combo must
                    # contribute at least one newly covered high-accuracy context.
                    if new_high <= 0:
                        continue
                    if (
                        new_high < int(min_new_highwin_steps)
                        and gain_mean < float(min_mean_best_gain)
                        and gain_cov70 < float(min_cov70_gain)
                    ):
                        continue

                score = (
                    3.0 * gain_cov
                    + 0.9 * max(gain_mean, 0.0)
                    + 0.35 * float(row.get("combo_acc_mean", 0.0) or 0.0)
                    + 0.20 * float(row.get("winner_acc_mean", 0.0) or 0.0)
                    - overlap_penalty * overlap
                )
                rank = (score, new_high, gain_cov, float(row.get("seed_score", 0.0) or 0.0))
                if best_score is None or rank > best_score:
                    best_score = rank
                    best_candidate = ck
                    best_metrics = trial_metrics
                    best_new_high = new_high
                    best_new_cov = gain_cov

            if best_candidate is None:
                break

            selected.append(best_candidate)
            remaining = [ck for ck in remaining if ck != best_candidate]
            current_set_metrics = best_metrics or current_set_metrics
            covered_high = set(current_set_metrics.get("high70_context_ids", set()))

            # Stop early once high-accuracy coverage target is reached;
            # this keeps the selected set minimal.
            if (
                current_set_metrics["cov70"] >= target_high_accuracy_coverage
                and len(selected) >= 1
            ):
                break

            # Additional stop if no meaningful gains are possible.
            if best_new_high <= 0 and best_new_cov <= 0.0 and len(selected) >= seed_size:
                break

        if not selected and combo_stats_sorted:
            selected = [combo_stats_sorted[0]["combo_key"]]
            current_set_metrics = _evaluate_combo_set(contexts=contexts, combo_keys=selected)

        # Rejections for supported combos that were not selected
        for ck in [r["combo_key"] for r in selection_pool if r["combo_key"] not in selected]:
            row = next((x for x in combo_stats_sorted if x["combo_key"] == ck), None)
            if row is None:
                continue
            rejection_rows.append(
                {
                    "unit": unit,
                    "timeframe": tf,
                    "target": target_col,
                    "combo_key": ck,
                    "fold_count": row["fold_count"],
                    "val_batches_per_fold": row["val_batches_per_fold"],
                    "train_batches_per_fold": row["train_batches_per_fold"],
                    "reason": "not_selected_coverage_first",
                    "detail": "did not improve high-accuracy coverage or mean-best enough",
                }
            )

        # Redundancy pruning
        changed = True
        while changed and len(selected) > 1:
            changed = False
            for ck in list(selected):
                trial = [x for x in selected if x != ck]
                trial_metrics = _evaluate_combo_set(contexts=contexts, combo_keys=trial)
                mean_drop = current_set_metrics["mean_best_acc"] - trial_metrics["mean_best_acc"]
                cov70_drop = current_set_metrics["cov70"] - trial_metrics["cov70"]
                if (
                    mean_drop <= float(redundancy_max_mean_drop)
                    and cov70_drop <= float(redundancy_max_cov70_drop)
                ):
                    selected = trial
                    current_set_metrics = trial_metrics
                    row = next((x for x in combo_stats_sorted if x["combo_key"] == ck), None)
                    rejection_rows.append(
                        {
                            "unit": unit,
                            "timeframe": tf,
                            "target": target_col,
                            "combo_key": ck,
                            "fold_count": row["fold_count"] if row else None,
                            "val_batches_per_fold": row["val_batches_per_fold"] if row else None,
                            "train_batches_per_fold": row["train_batches_per_fold"] if row else None,
                            "reason": "redundant",
                            "detail": (
                                f"mean_drop={mean_drop:.6f}, cov70_drop={cov70_drop:.6f}"
                            ),
                        }
                    )
                    changed = True
                    break

        auto_selected = list(selected)
        auto_metrics = dict(current_set_metrics)
        auto_metrics.pop("high70_context_ids", None)

        manual_triplets = _coerce_triplet_list(fallback_triplet_grid_by_unit.get(unit, []))
        manual_keys = [
            _combo_key_from_triplet(f, v, t) for (f, v, t) in manual_triplets
        ]
        manual_metrics_raw = _evaluate_combo_set(contexts=contexts, combo_keys=manual_keys) if manual_keys else _evaluate_combo_set(contexts=contexts, combo_keys=[])
        manual_metrics = dict(manual_metrics_raw)
        manual_metrics.pop("high70_context_ids", None)

        selected_source = "auto"
        final_selected = list(auto_selected)
        final_metrics_raw = _evaluate_combo_set(contexts=contexts, combo_keys=final_selected)
        if manual_keys:
            auto_ok = (
                auto_metrics["mean_best_acc"]
                >= (manual_metrics["mean_best_acc"] - float(safety_max_mean_best_drop))
            ) and (
                auto_metrics["cov70"]
                >= (manual_metrics["cov70"] - float(safety_max_cov70_drop))
            )
            if not auto_ok:
                final_selected = list(manual_keys)
                final_metrics_raw = manual_metrics_raw
                selected_source = "manual_fallback"
                for ck in auto_selected:
                    row = next((x for x in combo_stats_sorted if x["combo_key"] == ck), None)
                    rejection_rows.append(
                        {
                            "unit": unit,
                            "timeframe": tf,
                            "target": target_col,
                            "combo_key": ck,
                            "fold_count": row["fold_count"] if row else None,
                            "val_batches_per_fold": row["val_batches_per_fold"] if row else None,
                            "train_batches_per_fold": row["train_batches_per_fold"] if row else None,
                            "reason": "safety_guard_manual_fallback",
                            "detail": (
                                f"auto_mean={auto_metrics['mean_best_acc']:.6f}, "
                                f"manual_mean={manual_metrics['mean_best_acc']:.6f}, "
                                f"auto_cov70={auto_metrics['cov70']:.6f}, "
                                f"manual_cov70={manual_metrics['cov70']:.6f}"
                            ),
                        }
                    )

        final_metrics = dict(final_metrics_raw)
        final_metrics.pop("high70_context_ids", None)
        final_triplets: list[list[int]] = []
        for ck in final_selected:
            tri = combo_triplet.get(ck) or _triplet_from_combo_key(ck)
            if tri is None:
                continue
            final_triplets.append([int(tri[0]), int(tri[1]), int(tri[2])])

        # Ensure unique + bounded + deterministic
        dedup_triplets: list[list[int]] = []
        seen_tri = set()
        for tri in final_triplets:
            key = tuple(tri)
            if key in seen_tri:
                continue
            seen_tri.add(key)
            dedup_triplets.append(tri)
        dedup_triplets = dedup_triplets[:dynamic_cap]
        autogen_map[unit] = dedup_triplets

        stats_by_key = {r["combo_key"]: r for r in combo_stats_sorted}
        for rank, tri in enumerate(dedup_triplets, start=1):
            ck = _combo_key_from_triplet(tri[0], tri[1], tri[2])
            s = stats_by_key.get(ck, {})
            portfolio_rows.append(
                {
                    "unit": unit,
                    "timeframe": tf,
                    "target": target_col,
                    "selected_source": selected_source,
                    "rank_in_unit": rank,
                    "combo_key": ck,
                    "fold_count": int(tri[0]),
                    "val_batches_per_fold": int(tri[1]),
                    "train_batches_per_fold": int(tri[2]),
                    "steps_seen": int(s.get("steps_seen", 0) or 0),
                    "winner_count": int(s.get("winner_count", 0) or 0),
                    "winner_share": float(s.get("winner_share", 0.0) or 0.0),
                    "winner_acc_mean": float(s.get("winner_acc_mean", 0.0) or 0.0),
                    "winner_hit70_rate": float(s.get("winner_hit70_rate", 0.0) or 0.0),
                    "seed_score": float(s.get("seed_score", 0.0) or 0.0),
                    "portfolio_mean_best_acc": float(final_metrics["mean_best_acc"]),
                    "portfolio_cov70": float(final_metrics["cov70"]),
                    "portfolio_cov80": float(final_metrics["cov80"]),
                }
            )

        unit_summary[unit] = {
            "timeframe": tf,
            "target": target_col,
            "source_scope": source_scope,
            "context_granularity": context_granularity,
            "n_contexts": n_contexts,
            "n_steps": len(step_ids),
            "thresholds": {
                "dynamic_cap": int(dynamic_cap),
                "min_support_steps": int(min_support_steps),
                "min_new_highwin_steps": int(min_new_highwin_steps),
                "min_mean_best_gain": float(min_mean_best_gain),
                "min_cov70_gain": float(min_cov70_gain),
                "high_accuracy_threshold": float(high_accuracy_threshold),
                "target_high_accuracy_coverage": float(target_high_accuracy_coverage),
                "overlap_penalty": float(overlap_penalty),
                "require_70_mean_if_possible": bool(require_70_mean_if_possible),
                "redundancy_max_mean_drop": float(redundancy_max_mean_drop),
                "redundancy_max_cov70_drop": float(redundancy_max_cov70_drop),
                "safety_max_mean_best_drop": float(safety_max_mean_best_drop),
                "safety_max_cov70_drop": float(safety_max_cov70_drop),
            },
            "selected_source": selected_source,
            "manual_triplets": [list(t) for t in manual_triplets],
            "manual_metrics": manual_metrics,
            "auto_metrics": auto_metrics,
            "selected_metrics": final_metrics,
            "selected_combo_keys": [_combo_key_from_triplet(*t) for t in dedup_triplets],
            "selected_triplets": dedup_triplets,
            "candidate_count_total": len(combo_stats_sorted),
            "candidate_count_eligible": len(eligible),
            "candidate_count_pool": len(selection_pool),
            "combo_stats": combo_stats_sorted,
        }

        if verbose:
            print(
                f"[stage1_portfolio] {unit}: source={selected_source}, "
                f"selected={len(dedup_triplets)}, "
                f"mean_best_acc={final_metrics['mean_best_acc']:.6f}, "
                f"cov70={final_metrics['cov70']:.6f}"
            )

    meta_root = project_root_path / "data" / "htf_backtest_results" / "stage1_meta" / model_name
    out_dir = meta_root / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    portfolio_df = pl.DataFrame(portfolio_rows) if portfolio_rows else pl.DataFrame()
    rejections_df = pl.DataFrame(rejection_rows) if rejection_rows else pl.DataFrame()

    portfolio_json_path = out_dir / "candidate_portfolio_v2.json"
    portfolio_parquet_path = out_dir / "candidate_portfolio_v2.parquet"
    rejection_parquet_path = out_dir / "candidate_portfolio_v2_rejections.parquet"
    autogen_path = out_dir / "candidate_triplet_grid_autogen.json"

    if not portfolio_df.is_empty():
        portfolio_df.write_parquet(portfolio_parquet_path)
    else:
        pl.DataFrame().write_parquet(portfolio_parquet_path)
    if not rejections_df.is_empty():
        rejections_df.write_parquet(rejection_parquet_path)
    else:
        pl.DataFrame().write_parquet(rejection_parquet_path)
    with open(autogen_path, "w") as f:
        json.dump(autogen_map, f, indent=2)

    result = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "source_run_id": run_id,
        "source_run_path": str(run_dir),
        "model_name": model_name,
        "source_scope": source_scope,
        "params": {
            "context_granularity": context_granularity,
            "dynamic_cap": int(dynamic_cap),
            "min_support_steps": int(min_support_steps),
            "min_new_highwin_steps": int(min_new_highwin_steps),
            "min_mean_best_gain": float(min_mean_best_gain),
            "min_cov70_gain": float(min_cov70_gain),
            "high_accuracy_threshold": float(high_accuracy_threshold),
            "target_high_accuracy_coverage": float(target_high_accuracy_coverage),
            "overlap_penalty": float(overlap_penalty),
            "require_70_mean_if_possible": bool(require_70_mean_if_possible),
            "seed_size": int(seed_size),
            "redundancy_max_mean_drop": float(redundancy_max_mean_drop),
            "redundancy_max_cov70_drop": float(redundancy_max_cov70_drop),
            "safety_max_mean_best_drop": float(safety_max_mean_best_drop),
            "safety_max_cov70_drop": float(safety_max_cov70_drop),
        },
        "units": unit_summary,
        "artifacts": {
            "candidate_portfolio_v2_json": str(portfolio_json_path),
            "candidate_portfolio_v2_parquet": str(portfolio_parquet_path),
            "candidate_portfolio_v2_rejections_parquet": str(rejection_parquet_path),
            "candidate_triplet_grid_autogen_json": str(autogen_path),
        },
    }
    with open(portfolio_json_path, "w") as f:
        json.dump(result, f, indent=2)

    if write_latest:
        latest_path = meta_root / "latest_candidate_portfolio_v2.json"
        shutil.copyfile(portfolio_json_path, latest_path)
        result["artifacts"]["latest_candidate_portfolio_v2_json"] = str(latest_path)

    return result


__all__ = [
    "analyze_stage1_run",
    "build_stage1_winner_portfolio",
    "load_stage1_candidate_selection",
]
