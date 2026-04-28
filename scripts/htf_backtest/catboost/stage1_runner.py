"""
CatBoost Stage-1 Runner (Isolated)
==================================

Dedicated walk-forward Stage-1 runner:
- exhaustive fold grid only
- raw payload artifacts only
- no standard Optuna/final-model prediction reporting path
"""

from __future__ import annotations

import json
import shutil
import time
from collections import defaultdict
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from .stage1_optimizer import build_stage1_combo_grid, evaluate_stage1_grid
from .stage1_selector_step import (
    Stage1SelectorUnitConfig,
    collect_stage1_v2_step_artifacts,
)
from .stage1_v2_contract import (
    STAGE1_V2_ARTIFACT_CONTRACT_VERSION,
    STAGE1_V2_EXECUTION_MODE_FIXED_POLICY,
    STAGE1_V2_ROOT_ARTIFACTS,
    build_stage1_v2_selector_config,
    normalize_stage1_version,
    stage1_mode_name,
    stage1_v2_contract_payload,
)
from .utils import compute_label_distribution, get_valid_batches


def _stage1_required_artifact_paths(step_dir: Path) -> dict[str, Path]:
    stage1_dir = step_dir / "stage1"
    return {
        "batch_metadata": step_dir / "batch_metadata.json",
        "summary": stage1_dir / "stage1_step_summary.json",
        "config_snapshot": stage1_dir / "stage1_config_snapshot.json",
        "combo_index": stage1_dir / "stage1_combo_index.parquet",
        "fold_windows": stage1_dir / "stage1_fold_windows.parquet",
        "val_predictions": stage1_dir / "stage1_val_predictions.parquet",
        "pred_batch_predictions": stage1_dir / "stage1_pred_batch_predictions.parquet",
        "predecision_context_json": stage1_dir / "stage1_predecision_context.json",
        "predecision_context_parquet": stage1_dir / "stage1_predecision_context.parquet",
        "runtime_profile": stage1_dir / "stage1_runtime_profile.json",
    }


def _stage1_combo_key_from_record(record: dict[str, Any]) -> tuple[int, int, int]:
    return (
        int(record["fold_count"]),
        int(record["val_batches_per_fold"]),
        int(record["train_batches_per_fold"]),
    )


def _stage1_expected_combo_maps(expected_combos: list[dict[str, Any]]) -> tuple[list[tuple[int, int, int]], dict[tuple[int, int, int], int]]:
    ordered_keys = [_stage1_combo_key_from_record(c) for c in expected_combos]
    key_to_new_id = {k: i for i, k in enumerate(ordered_keys)}
    return ordered_keys, key_to_new_id


def _stage1_collect_combo_coverage(
    combo_index_path: Path,
    expected_combos: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    try:
        combo_df = pl.read_parquet(combo_index_path)
    except Exception:
        return {
            "ok": False,
            "reason": "combo_index_unreadable",
        }

    if combo_df.is_empty():
        return {
            "ok": False,
            "reason": "combo_index_empty",
        }

    required_cols = {
        "combo_id",
        "fold_count",
        "val_batches_per_fold",
        "train_batches_per_fold",
        "status",
    }
    if not required_cols.issubset(set(combo_df.columns)):
        return {
            "ok": False,
            "reason": "combo_index_missing_columns",
        }

    complete_df = combo_df.filter(pl.col("status") == "complete")
    complete_records = complete_df.to_dicts()
    key_to_old_combo_id: dict[tuple[int, int, int], int] = {}
    for row in complete_records:
        key = (
            int(row["fold_count"]),
            int(row["val_batches_per_fold"]),
            int(row["train_batches_per_fold"]),
        )
        # Keep first occurrence if duplicates exist.
        key_to_old_combo_id.setdefault(key, int(row["combo_id"]))

    coverage = {
        "ok": True,
        "reason": "ok",
        "complete_count": int(len(complete_records)),
        "key_to_old_combo_id": key_to_old_combo_id,
    }

    if expected_combos is None:
        return coverage

    ordered_keys, key_to_new_id = _stage1_expected_combo_maps(expected_combos)
    expected_set = set(ordered_keys)
    available_set = set(key_to_old_combo_id.keys())
    missing_keys = [k for k in ordered_keys if k not in available_set]
    extra_keys = sorted(available_set - expected_set)
    needs_migration = bool(extra_keys)
    # Migration also needed when IDs are not canonical 0..N-1 for expected ordering.
    if not needs_migration and not missing_keys:
        for key in ordered_keys:
            old_id = int(key_to_old_combo_id[key])
            new_id = int(key_to_new_id[key])
            if old_id != new_id:
                needs_migration = True
                break

    coverage.update(
        {
            "expected_keys": ordered_keys,
            "expected_count": int(len(ordered_keys)),
            "expected_key_to_new_id": key_to_new_id,
            "missing_keys": missing_keys,
            "missing_count": int(len(missing_keys)),
            "extra_keys": extra_keys,
            "extra_count": int(len(extra_keys)),
            "needs_migration": bool(needs_migration),
        }
    )
    return coverage


def _stage1_migrate_step_to_expected_grid(
    *,
    step_dir: Path,
    expected_combos: list[dict[str, Any]],
    coverage: dict[str, Any],
) -> dict[str, Any]:
    """
    Keep only expected combos in canonical stage1 files and archive everything else.
    This is used to adapt old wider-grid steps to a new reduced triplet setup
    without deleting historical data.
    """
    if not coverage.get("ok", False):
        return {"migrated": False, "reason": str(coverage.get("reason", "coverage_not_ok"))}
    if int(coverage.get("missing_count", 0)) > 0:
        return {"migrated": False, "reason": "missing_expected_combos"}

    stage1_dir = step_dir / "stage1"
    files = _stage1_required_artifact_paths(step_dir)

    # Archive original artifacts before rewriting canonical active-grid files.
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_dir = stage1_dir / "archive_legacy" / f"grid_migration_{ts}"
    archive_dir.mkdir(parents=True, exist_ok=True)

    archive_keys = [
        "summary",
        "combo_index",
        "fold_windows",
        "val_predictions",
        "pred_batch_predictions",
        "runtime_profile",
    ]
    archived_paths: dict[str, str] = {}
    for key in archive_keys:
        src = files[key]
        if src.exists():
            dst = archive_dir / src.name
            shutil.move(str(src), str(dst))
            archived_paths[key] = str(dst)

    combo_df = pl.read_parquet(archive_dir / "stage1_combo_index.parquet")
    fold_df = pl.read_parquet(archive_dir / "stage1_fold_windows.parquet")
    val_df = pl.read_parquet(archive_dir / "stage1_val_predictions.parquet")
    pred_df = pl.read_parquet(archive_dir / "stage1_pred_batch_predictions.parquet")
    old_summary = {}
    try:
        with open(archive_dir / "stage1_step_summary.json", "r") as f:
            old_summary = json.load(f)
    except Exception:
        old_summary = {}

    expected_keys, expected_key_to_new_id = _stage1_expected_combo_maps(expected_combos)
    key_to_old = dict(coverage["key_to_old_combo_id"])
    old_to_new = {int(key_to_old[k]): int(expected_key_to_new_id[k]) for k in expected_keys}
    old_ids = list(old_to_new.keys())

    def _remap_combo_id(df: pl.DataFrame) -> pl.DataFrame:
        if df.is_empty():
            return df
        mapping_expr = pl.col("combo_id").replace(old_to_new, default=-1).cast(pl.Int32)
        return df.with_columns(mapping_expr.alias("combo_id")).filter(pl.col("combo_id") >= 0)

    # Rewrite canonical active-grid artifacts.
    combo_keep = combo_df.filter(pl.col("combo_id").is_in(old_ids))
    combo_keep = _remap_combo_id(combo_keep).sort("combo_id")
    # Force canonical combo metadata rows in expected order.
    combo_rows = []
    for combo in expected_combos:
        key = _stage1_combo_key_from_record(combo)
        old_id = int(key_to_old[key])
        new_id = int(expected_key_to_new_id[key])
        row = combo_df.filter(pl.col("combo_id") == old_id).head(1).to_dicts()
        base = row[0] if row else {}
        base.update(
            {
                "combo_id": int(new_id),
                "fold_count": int(key[0]),
                "val_batches_per_fold": int(key[1]),
                "train_batches_per_fold": int(key[2]),
                "status": "complete",
            }
        )
        combo_rows.append(base)
    combo_keep = pl.DataFrame(combo_rows) if combo_rows else combo_keep
    combo_keep.write_parquet(files["combo_index"])

    fold_keep = fold_df.filter(pl.col("combo_id").is_in(old_ids))
    fold_keep = _remap_combo_id(fold_keep).sort(["combo_id", "fold_id"])
    fold_keep.write_parquet(files["fold_windows"])

    val_keep = val_df.filter(pl.col("combo_id").is_in(old_ids))
    val_keep = _remap_combo_id(val_keep).sort(["combo_id", "fold_id", "timestamp"])
    val_keep.write_parquet(files["val_predictions"])

    pred_keep = pred_df.filter(pl.col("combo_id").is_in(old_ids))
    pred_keep = _remap_combo_id(pred_keep).sort(["combo_id", "timestamp"])
    pred_keep.write_parquet(files["pred_batch_predictions"])

    new_summary = dict(old_summary) if isinstance(old_summary, dict) else {}
    new_summary.update(
        {
            "combo_count_total": int(len(expected_combos)),
            "combo_count_completed": int(len(expected_combos)),
            "combo_count_failed": 0,
            "val_payload_rows": int(len(val_keep)),
            "pred_payload_rows": int(len(pred_keep)),
            "stage1_grid_migration": {
                "applied_at": datetime.now().isoformat(),
                "from_combo_count_total": int(old_summary.get("combo_count_total", len(combo_df))),
                "to_combo_count_total": int(len(expected_combos)),
                "extra_combos_archived": int(coverage.get("extra_count", 0)),
                "archive_dir": str(archive_dir),
            },
        }
    )
    with open(files["summary"], "w") as f:
        json.dump(new_summary, f, indent=2)

    runtime_profile = {
        "summary": new_summary,
        "migration": {
            "archive_dir": str(archive_dir),
            "archived_files": archived_paths,
        },
    }
    with open(files["runtime_profile"], "w") as f:
        json.dump(runtime_profile, f, indent=2)

    migration_note = {
        "applied_at": datetime.now().isoformat(),
        "reason": "adapt_to_expected_stage1_triplet_grid",
        "archive_dir": str(archive_dir),
        "expected_combos": [
            {
                "fold_count": int(c["fold_count"]),
                "val_batches_per_fold": int(c["val_batches_per_fold"]),
                "train_batches_per_fold": int(c["train_batches_per_fold"]),
            }
            for c in expected_combos
        ],
        "old_to_new_combo_id": {str(k): int(v) for k, v in old_to_new.items()},
    }
    with open(stage1_dir / "stage1_grid_migration.json", "w") as f:
        json.dump(migration_note, f, indent=2)

    return {
        "migrated": True,
        "reason": "ok",
        "archive_dir": str(archive_dir),
        "expected_combo_count": int(len(expected_combos)),
    }


def _stage1_step_artifact_status(
    step_dir: Path,
    expected_combos: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    files = _stage1_required_artifact_paths(step_dir)
    missing = [name for name, path in files.items() if not path.exists()]
    if missing:
        return {
            "is_complete": False,
            "missing": missing,
            "reason": "missing_artifacts",
        }

    # Basic sanity check for summary payload.
    try:
        with open(files["summary"], "r") as f:
            summary = json.load(f)
    except Exception:
        return {
            "is_complete": False,
            "missing": [],
            "reason": "summary_unreadable",
        }

    combo_total = int(summary.get("combo_count_total", 0) or 0)
    combo_completed = int(summary.get("combo_count_completed", 0) or 0)
    if combo_total <= 0:
        return {
            "is_complete": False,
            "missing": [],
            "reason": "invalid_combo_total",
        }
    if combo_completed <= 0:
        return {
            "is_complete": False,
            "missing": [],
            "reason": "zero_completed_combos",
        }

    if expected_combos is not None:
        coverage = _stage1_collect_combo_coverage(files["combo_index"], expected_combos)
        if not coverage.get("ok", False):
            return {
                "is_complete": False,
                "missing": [],
                "reason": str(coverage.get("reason", "combo_coverage_error")),
            }
        if int(coverage.get("missing_count", 0)) > 0:
            return {
                "is_complete": False,
                "missing": [],
                "reason": "missing_expected_combos",
                "missing_expected_count": int(coverage.get("missing_count", 0)),
                "missing_expected_keys": coverage.get("missing_keys", []),
                "coverage": coverage,
            }
        if bool(coverage.get("needs_migration", False)):
            return {
                "is_complete": True,
                "missing": [],
                "reason": "ok_needs_grid_migration",
                "coverage": coverage,
            }

    return {
        "is_complete": True,
        "missing": [],
        "reason": "ok",
    }


def _stage1_action_key_from_triplet(fold_count: int, val_batches: int, train_batches: int) -> str:
    return f"f{int(fold_count)}_v{int(val_batches)}_t{int(train_batches)}"


def _stage1_triplet_from_action_key(action_key: str) -> tuple[int, int, int] | None:
    try:
        s = str(action_key).strip()
        if not (s.startswith("f") and "_v" in s and "_t" in s):
            return None
        f_part, rest = s[1:].split("_v", 1)
        v_part, t_part = rest.split("_t", 1)
        return int(f_part), int(v_part), int(t_part)
    except Exception:
        return None


def _stage1_detect_direction_indices(class_names: list[str]) -> tuple[set[int], set[int]]:
    up: set[int] = set()
    down: set[int] = set()
    for i, name in enumerate(class_names):
        token = str(name).upper()
        if "UP" in token:
            up.add(int(i))
        if "DOWN" in token:
            down.add(int(i))
    return up, down


def _stage1_cross_direction_error(
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


def _stage1_macro_f1(y_true: np.ndarray, y_pred: np.ndarray, n_classes: int) -> float:
    if y_true.size == 0:
        return 0.0
    cm = np.zeros((int(n_classes), int(n_classes)), dtype=np.int64)
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


def _stage1_rank_metric_row(row: dict[str, Any]) -> tuple[float, float, float, str]:
    acc = float(row.get("accuracy", 0.0) or 0.0)
    macro = float(row.get("macro_f1", 0.0) or 0.0)
    cde = row.get("cross_direction_error")
    cde_sort = float(cde) if cde is not None else 1e9
    action_key = str(row.get("action_key", ""))
    return (-acc, -macro, cde_sort, action_key)


def _stage1_compute_combo_metrics_from_payload(
    *,
    combo_df: pl.DataFrame,
    pred_df: pl.DataFrame,
    n_classes: int,
    class_names: list[str],
) -> list[dict[str, Any]]:
    if combo_df.is_empty() or pred_df.is_empty():
        return []
    combo_df_local = combo_df
    if "status" in combo_df_local.columns:
        combo_df_local = combo_df_local.filter(pl.col("status") == "complete")
    if combo_df_local.is_empty():
        return []
    up_idx, down_idx = _stage1_detect_direction_indices(class_names)
    combo_rows = combo_df_local.select(
        [c for c in ["combo_id", "action_key", "fold_count", "val_batches_per_fold", "train_batches_per_fold"] if c in combo_df_local.columns]
    ).to_dicts()
    combo_id_to_meta: dict[int, dict[str, Any]] = {}
    for row in combo_rows:
        combo_id = int(row["combo_id"])
        action_key = str(
            row.get("action_key")
            or _stage1_action_key_from_triplet(
                int(row.get("fold_count", 0) or 0),
                int(row.get("val_batches_per_fold", 0) or 0),
                int(row.get("train_batches_per_fold", 0) or 0),
            )
        )
        combo_id_to_meta[combo_id] = {
            "combo_id": combo_id,
            "action_key": action_key,
            "fold_count": int(row.get("fold_count", 0) or 0),
            "val_batches_per_fold": int(row.get("val_batches_per_fold", 0) or 0),
            "train_batches_per_fold": int(row.get("train_batches_per_fold", 0) or 0),
        }

    pred_df_local = pred_df.select(
        [c for c in ["combo_id", "y_true", "y_pred"] if c in pred_df.columns]
    )
    if set(pred_df_local.columns) != {"combo_id", "y_true", "y_pred"}:
        return []

    out: list[dict[str, Any]] = []
    for combo_key, grp in pred_df_local.group_by("combo_id"):
        combo_id = int(combo_key[0] if isinstance(combo_key, tuple) else combo_key)
        meta = combo_id_to_meta.get(combo_id)
        if meta is None:
            continue
        y_true = grp["y_true"].to_numpy().astype(np.int32, copy=False)
        y_pred = grp["y_pred"].to_numpy().astype(np.int32, copy=False)
        acc = float((y_true == y_pred).mean()) if y_true.size > 0 else 0.0
        macro = _stage1_macro_f1(y_true, y_pred, int(n_classes))
        cde = _stage1_cross_direction_error(y_true, y_pred, up_idx, down_idx)
        out.append(
            {
                **meta,
                "accuracy": float(acc),
                "macro_f1": float(macro),
                "cross_direction_error": cde,
                "pred_rows": int(y_true.size),
            }
        )
    out.sort(key=_stage1_rank_metric_row)
    return out


def _stage1_get_step_winner_metrics(
    *,
    stage1_dir: Path,
    n_classes: int,
    class_names: list[str],
) -> dict[str, Any] | None:
    combo_path = stage1_dir / "stage1_combo_index.parquet"
    pred_path = stage1_dir / "stage1_pred_batch_predictions.parquet"
    if not combo_path.exists() or not pred_path.exists():
        return None
    try:
        combo_df = pl.read_parquet(combo_path)
        pred_df = pl.read_parquet(pred_path)
    except Exception:
        return None
    metrics = _stage1_compute_combo_metrics_from_payload(
        combo_df=combo_df,
        pred_df=pred_df,
        n_classes=int(n_classes),
        class_names=list(class_names),
    )
    if not metrics:
        return None
    winner = dict(metrics[0])
    winner["combos_ranked"] = int(len(metrics))
    return winner


def _stage1_update_step_summary_quality(
    *,
    stage1_dir: Path,
    quality_threshold: float,
    winner: dict[str, Any] | None,
    quality_unresolved: bool,
    probe_exhausted: bool,
    probe_enabled: bool,
    probe_tiers_run: int,
    probe_candidates_evaluated: int,
) -> dict[str, Any]:
    summary_path = stage1_dir / "stage1_step_summary.json"
    try:
        with open(summary_path, "r") as f:
            summary = json.load(f)
    except Exception:
        summary = {}
    winner_acc = float(winner.get("accuracy", 0.0) or 0.0) if winner else None
    quality_pass = bool(winner_acc is not None and winner_acc >= float(quality_threshold))
    summary.update(
        {
            "winner_combo_key": str(winner.get("action_key")) if winner else None,
            "winner_accuracy": winner_acc,
            "winner_macro_f1": float(winner.get("macro_f1", 0.0) or 0.0) if winner else None,
            "winner_cross_direction_error": (
                float(winner["cross_direction_error"])
                if winner and winner.get("cross_direction_error") is not None
                else None
            ),
            "quality_threshold": float(quality_threshold),
            "quality_pass": bool(quality_pass),
            "quality_unresolved": bool(quality_unresolved),
            "probe_exhausted": bool(probe_exhausted),
            "probe_enabled": bool(probe_enabled),
            "probe_tiers_run": int(probe_tiers_run),
            "probe_candidates_evaluated": int(probe_candidates_evaluated),
        }
    )
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    return summary


def _stage1_merge_probe_log(step_stage1_dir: Path, rows: list[dict[str, Any]]) -> Path:
    path = step_stage1_dir / "stage1_probe_log.parquet"
    new_df = pl.DataFrame(rows) if rows else pl.DataFrame()
    if path.exists():
        old_df = pl.read_parquet(path)
        if not new_df.is_empty():
            # Probe log schema can evolve across runs; keep merges tolerant so
            # resume/backfill can append new columns without failing.
            merged = pl.concat([old_df, new_df], how="diagonal_relaxed").unique(
                subset=["unit", "pred_batch", "tier_idx", "phase"],
                keep="last",
            )
        else:
            merged = old_df
    else:
        merged = new_df
    if merged.is_empty():
        pl.DataFrame(
            {
                "unit": [],
                "pred_batch": [],
                "phase": [],
                "tier_idx": [],
                "evaluated_count": [],
                "winner_before": [],
                "winner_after": [],
                "quality_pass_after": [],
                "stop_reason": [],
            }
        ).write_parquet(path)
    else:
        merged.write_parquet(path)
    return path


def _stage1_scan_unit_history_candidates(
    *,
    unit_dir: Path,
    source_scope: str,
    n_classes: int,
    class_names: list[str],
    quality_threshold: float,
) -> dict[str, dict[str, Any]]:
    include_current = source_scope in {"current", "current+archive"}
    include_archive = source_scope in {"archive", "current+archive"}
    stats: dict[str, dict[str, Any]] = {}

    for batch_dir in sorted(unit_dir.glob("batch_*")):
        try:
            pred_batch = int(batch_dir.name.split("_")[1])
        except Exception:
            continue
        stage1_dir = batch_dir / "stage1"
        if not stage1_dir.exists():
            continue
        snapshots: list[tuple[str, Path, Path]] = []
        if include_current:
            combo_path = stage1_dir / "stage1_combo_index.parquet"
            pred_path = stage1_dir / "stage1_pred_batch_predictions.parquet"
            if combo_path.exists() and pred_path.exists():
                snapshots.append((f"batch_{pred_batch}", combo_path, pred_path))
        if include_archive:
            archive_root = stage1_dir / "archive_legacy"
            if archive_root.exists():
                for snap_dir in sorted([p for p in archive_root.iterdir() if p.is_dir()]):
                    combo_path = snap_dir / "stage1_combo_index.parquet"
                    pred_path = snap_dir / "stage1_pred_batch_predictions.parquet"
                    if combo_path.exists() and pred_path.exists():
                        snapshots.append((f"archive:{snap_dir.name}", combo_path, pred_path))

        step_best_by_combo: dict[str, dict[str, Any]] = {}
        for snap_tag, combo_path, pred_path in snapshots:
            try:
                combo_df = pl.read_parquet(combo_path)
                pred_df = pl.read_parquet(pred_path)
            except Exception:
                continue
            combo_metrics = _stage1_compute_combo_metrics_from_payload(
                combo_df=combo_df,
                pred_df=pred_df,
                n_classes=int(n_classes),
                class_names=list(class_names),
            )
            for row in combo_metrics:
                ck = str(row["action_key"])
                existing = step_best_by_combo.get(ck)
                row_local = dict(row)
                row_local["snapshot_tag"] = snap_tag
                if existing is None or _stage1_rank_metric_row(row_local) < _stage1_rank_metric_row(existing):
                    step_best_by_combo[ck] = row_local

        for ck, row in step_best_by_combo.items():
            triplet = _stage1_triplet_from_action_key(ck)
            if triplet is None:
                continue
            s = stats.setdefault(
                ck,
                {
                    "combo_key": ck,
                    "fold_count": int(triplet[0]),
                    "val_batches_per_fold": int(triplet[1]),
                    "train_batches_per_fold": int(triplet[2]),
                    "steps_seen": set(),
                    "high_steps": set(),
                    "acc_values": [],
                    "macro_values": [],
                    "cde_values": [],
                    "source_tags": set(),
                },
            )
            s["steps_seen"].add(int(pred_batch))
            acc = float(row.get("accuracy", 0.0) or 0.0)
            s["acc_values"].append(acc)
            s["macro_values"].append(float(row.get("macro_f1", 0.0) or 0.0))
            cde_val = row.get("cross_direction_error")
            if cde_val is not None:
                s["cde_values"].append(float(cde_val))
            if acc >= float(quality_threshold):
                s["high_steps"].add(int(pred_batch))
            s["source_tags"].add(str(row.get("snapshot_tag", "")))

    for ck, s in stats.items():
        acc_values = list(s.get("acc_values", []))
        macro_values = list(s.get("macro_values", []))
        cde_values = list(s.get("cde_values", []))
        s["steps_seen_count"] = int(len(s.get("steps_seen", set())))
        s["high_steps_count"] = int(len(s.get("high_steps", set())))
        s["accuracy_mean"] = float(np.mean(acc_values)) if acc_values else 0.0
        s["macro_f1_mean"] = float(np.mean(macro_values)) if macro_values else 0.0
        s["cross_direction_error_mean"] = float(np.mean(cde_values)) if cde_values else None
        s["discovered_from"] = ",".join(sorted(str(v) for v in s.get("source_tags", set()) if str(v)))
    return stats


def _stage1_rank_probe_candidates(
    *,
    history_stats: dict[str, dict[str, Any]],
    active_combo_keys: set[str],
    existing_step_combo_keys: set[str],
    quality_threshold: float,
    max_candidates: int,
) -> list[dict[str, Any]]:
    covered_high_steps: set[int] = set()
    for ck in active_combo_keys:
        s = history_stats.get(ck)
        if s is None:
            continue
        covered_high_steps |= set(s.get("high_steps", set()))

    ranked: list[tuple[tuple[float, float, float, str], dict[str, Any]]] = []
    for ck, s in history_stats.items():
        if ck in existing_step_combo_keys:
            continue
        triplet = (
            int(s.get("fold_count", 0)),
            int(s.get("val_batches_per_fold", 0)),
            int(s.get("train_batches_per_fold", 0)),
        )
        if min(triplet) <= 0:
            continue
        high_steps = set(s.get("high_steps", set()))
        new_high = high_steps - covered_high_steps
        support = int(s.get("steps_seen_count", 0))
        mean_acc = float(s.get("accuracy_mean", 0.0) or 0.0)
        score = (-float(len(new_high)), -mean_acc, -float(support), str(ck))
        ranked.append(
            (
                score,
                {
                    "action_key": str(ck),
                    "fold_count": int(triplet[0]),
                    "val_batches_per_fold": int(triplet[1]),
                    "train_batches_per_fold": int(triplet[2]),
                    "new_high_steps": int(len(new_high)),
                    "mean_accuracy": float(mean_acc),
                    "support_steps": int(support),
                    "discovered_from": str(s.get("discovered_from", "")),
                    "quality_threshold": float(quality_threshold),
                },
            )
        )
    ranked.sort(key=lambda x: x[0])
    return [r[1] for r in ranked[: int(max(0, max_candidates))]]


def _stage1_load_dynamic_registry(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"units": {}}
    try:
        with open(path, "r") as f:
            obj = json.load(f)
        if not isinstance(obj, dict):
            return {"units": {}}
        if "units" not in obj or not isinstance(obj["units"], dict):
            obj["units"] = {}
        return obj
    except Exception:
        return {"units": {}}


def _stage1_save_dynamic_registry(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)


def _stage1_v2_write_frame(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        pl.from_dicts(rows, infer_schema_length=None).write_parquet(path)
    else:
        pl.DataFrame().write_parquet(path)
    return path


def _stage1_v2_load_fixed_policy_registry(
    selector_config: Any,
    base_run_dir: Path,
) -> tuple[dict[str, Any], str]:
    registry_path_raw = getattr(selector_config, "fixed_policy_registry_path", None)
    registry_path = (
        Path(str(registry_path_raw)).expanduser()
        if registry_path_raw is not None and str(registry_path_raw).strip() != ""
        else base_run_dir / "stage1_v2_fixed_policy_registry.json"
    )
    if not registry_path.is_absolute():
        registry_path = registry_path.resolve()
    if not registry_path.exists():
        raise FileNotFoundError(
            f"Stage-1-v2 fixed policy registry not found: {registry_path}"
        )
    with open(registry_path, "r") as f:
        payload = json.load(f)
    combos = payload.get("combos")
    if not isinstance(combos, dict) or not combos:
        raise ValueError(
            f"Stage-1-v2 fixed policy registry has no usable combo payload: {registry_path}"
        )
    return payload, str(registry_path)


def _stage1_v2_write_root_artifacts(
    *,
    base_run_dir: Path,
    run_id: str,
    stage1_v2_cfg: Any,
    progress_rows: list[dict[str, Any]],
    baseline_vs_selected_rows: list[dict[str, Any]],
    feature_importance_rows: list[dict[str, Any]],
    feature_mask_rows: list[dict[str, Any]],
) -> dict[str, str]:
    artifact_paths: dict[str, str] = {}

    progress_path = base_run_dir / STAGE1_V2_ROOT_ARTIFACTS["progress"]
    _stage1_v2_write_frame(progress_path, progress_rows)
    artifact_paths["progress"] = str(progress_path)

    baseline_vs_selected_path = (
        base_run_dir / STAGE1_V2_ROOT_ARTIFACTS["baseline_vs_selected_root"]
    )
    _stage1_v2_write_frame(baseline_vs_selected_path, baseline_vs_selected_rows)
    artifact_paths["baseline_vs_selected_root"] = str(baseline_vs_selected_path)

    winner_change_summary_path = base_run_dir / STAGE1_V2_ROOT_ARTIFACTS["winner_change_summary"]
    winner_change_rows: list[dict[str, Any]] = []
    if baseline_vs_selected_rows:
        winner_change_df = pl.from_dicts(
            baseline_vs_selected_rows, infer_schema_length=None
        )
        if {"timeframe", "target", "winner_changed"}.issubset(set(winner_change_df.columns)):
            winner_change_rows = (
                winner_change_df.group_by(["timeframe", "target"])
                .agg(
                    [
                        pl.len().alias("steps"),
                        pl.col("winner_changed")
                        .cast(pl.Int64)
                        .sum()
                        .alias("winner_changed_steps"),
                    ]
                )
                .with_columns(
                    (
                        pl.col("winner_changed_steps") / pl.col("steps").clip(lower_bound=1)
                    ).alias("winner_changed_rate")
                )
                .to_dicts()
            )
    _stage1_v2_write_frame(winner_change_summary_path, winner_change_rows)
    artifact_paths["winner_change_summary"] = str(winner_change_summary_path)

    importance_path = base_run_dir / STAGE1_V2_ROOT_ARTIFACTS["feature_importance_global"]
    _stage1_v2_write_frame(importance_path, feature_importance_rows)
    artifact_paths["feature_importance_global"] = str(importance_path)

    feature_mask_path = base_run_dir / STAGE1_V2_ROOT_ARTIFACTS["feature_mask_global"]
    _stage1_v2_write_frame(feature_mask_path, feature_mask_rows)
    artifact_paths["feature_mask_global"] = str(feature_mask_path)

    stability_path = base_run_dir / STAGE1_V2_ROOT_ARTIFACTS["feature_stability"]
    stability_rows: list[dict[str, Any]] = []
    if feature_importance_rows:
        importance_df = pl.from_dicts(feature_importance_rows, infer_schema_length=None)
        if {"timeframe", "target", "feature", "importance"}.issubset(set(importance_df.columns)):
            stability_rows = (
                importance_df.group_by(["timeframe", "target", "feature"])
                .agg(
                    [
                        pl.len().alias("n_rows"),
                        pl.col("importance").mean().alias("mean_importance"),
                        pl.col("importance").median().alias("median_importance"),
                        pl.col("importance").std(ddof=1).alias("std_importance"),
                        pl.col("is_selected_step")
                        .cast(pl.Float64)
                        .mean()
                        .alias("selected_step_freq")
                        if "is_selected_step" in importance_df.columns
                        else pl.lit(None).alias("selected_step_freq"),
                    ]
                )
                .to_dicts()
            )
    _stage1_v2_write_frame(stability_path, stability_rows)
    artifact_paths["feature_stability"] = str(stability_path)

    run_summary_path = base_run_dir / STAGE1_V2_ROOT_ARTIFACTS["run_summary"]
    run_summary = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "run_id": str(run_id),
        "artifact_contract_version": STAGE1_V2_ARTIFACT_CONTRACT_VERSION,
        "execution_mode": str(stage1_v2_cfg.execution_mode),
        "selector_config": asdict(stage1_v2_cfg),
        "step_rows": int(len(progress_rows)),
        "baseline_vs_selected_rows": int(len(baseline_vs_selected_rows)),
        "feature_importance_rows": int(len(feature_importance_rows)),
        "feature_mask_rows": int(len(feature_mask_rows)),
        "artifacts": artifact_paths,
    }
    with open(run_summary_path, "w") as f:
        json.dump(run_summary, f, indent=2)
    artifact_paths["run_summary"] = str(run_summary_path)

    return artifact_paths


def run_walk_forward_stage1_grid(
    n_steps: int | None = None,
    timeframes: list[str] | None = None,
    run_description: str = "Stage-1 fold-grid dataset generation (CatBoost)",
    verbose: bool = True,
    debug_batches: bool = False,
    optuna_overrides: dict | None = None,
    run_id: str | None = None,
    resume: bool = False,
    resume_mode: str = "continue",
    allow_override_mismatch: bool = False,  # kept for signature compatibility
    model_name: str = "catboost",
    optuna_overrides_by_model: dict | None = None,
    targets_by_model: dict | None = None,
    n_classes_by_model: dict | None = None,
    class_names_by_model: dict | None = None,
    feature_source_by_model: dict | None = None,
    target_registry: dict | None = None,
    stage1_quality_accuracy_threshold: float = 0.70,
    stage1_probe_enabled: bool = True,
    stage1_probe_tier_sizes: list[int] | None = None,
    stage1_probe_max_extra_candidates: int = 32,
    stage1_probe_source_scope: str = "current+archive",
    stage1_backfill_low_quality_completed: bool = True,
    stage1_promotion_mode: str = "global",
    stage1_promoted_combo_cap_per_unit: int = 8,
    stage1_version: str = "v1",
    stage1_v2_selector_config: dict | None = None,
    pred_batch_min: int | None = None,
    pred_batch_max: int | None = None,
) -> dict:
    """Run isolated Stage-1 fold grid and store raw payload artifacts."""
    from .tf_1m import Config1m, FeatureSpace1m, ModelSpace1m, Optimizer1m, WindowSpace1m
    from .tf_5m import Config5m, FeatureSpace5m, ModelSpace5m, Optimizer5m, WindowSpace5m
    from .tf_15m import (
        Config15m,
        FeatureSpace15m,
        ModelSpace15m,
        Optimizer15m,
        WindowSpace15m,
    )

    if model_name != "catboost":
        raise ValueError(
            f"run_walk_forward_stage1_grid supports only model_name='catboost', got '{model_name}'"
        )
    if resume_mode not in {"continue", "skip_completed"}:
        raise ValueError("resume_mode must be 'continue' or 'skip_completed'")
    if resume and not run_id:
        raise ValueError("resume=True requires run_id")

    if timeframes is None:
        timeframes = ["1m", "5m", "15m"]

    stage1_print_label_distribution = False
    stage1_version = normalize_stage1_version(stage1_version)
    stage1_mode = stage1_mode_name(stage1_version)
    stage1_v2_cfg = (
        build_stage1_v2_selector_config(stage1_v2_selector_config)
        if stage1_version == "v2"
        else None
    )
    stage1_quality_accuracy_threshold = float(stage1_quality_accuracy_threshold)
    stage1_probe_enabled = bool(stage1_probe_enabled)
    stage1_runtime_mode = "adaptive" if stage1_probe_enabled else "routine"
    if stage1_probe_tier_sizes is None:
        stage1_probe_tier_sizes = [8, 8, 8, 8]
    stage1_probe_tier_sizes = [int(max(0, x)) for x in stage1_probe_tier_sizes]
    stage1_probe_max_extra_candidates = int(max(0, stage1_probe_max_extra_candidates))
    stage1_probe_source_scope = str(stage1_probe_source_scope)
    if pred_batch_min is not None:
        pred_batch_min = int(pred_batch_min)
    if pred_batch_max is not None:
        pred_batch_max = int(pred_batch_max)
    if (
        pred_batch_min is not None
        and pred_batch_max is not None
        and int(pred_batch_min) > int(pred_batch_max)
    ):
        raise ValueError("pred_batch_min must be <= pred_batch_max")
    if stage1_probe_source_scope not in {"current", "archive", "current+archive"}:
        raise ValueError(
            "stage1_probe_source_scope must be one of: current, archive, current+archive"
        )
    stage1_backfill_low_quality_completed = bool(stage1_backfill_low_quality_completed)
    stage1_promotion_mode = str(stage1_promotion_mode)
    if stage1_promotion_mode not in {"global", "step_local", "repeat"}:
        raise ValueError("stage1_promotion_mode must be one of: global, step_local, repeat")
    stage1_promoted_combo_cap_per_unit = int(max(1, stage1_promoted_combo_cap_per_unit))

    if optuna_overrides_by_model is not None:
        optuna_overrides = optuna_overrides_by_model.get(model_name, optuna_overrides)

    target_map = (targets_by_model or {}).get(model_name, {}) if targets_by_model else {}
    n_classes_map = (n_classes_by_model or {}).get(model_name, {}) if n_classes_by_model else {}
    class_names_map = (class_names_by_model or {}).get(model_name, {}) if class_names_by_model else {}
    feature_source_map = (
        (feature_source_by_model or {}).get(model_name, {})
        if feature_source_by_model
        else {}
    )

    def _normalize_target_list(value: Any, default_target: str) -> list[str]:
        if value is None:
            return [default_target]
        if isinstance(value, str):
            values = [value]
        elif isinstance(value, (list, tuple, set)):
            values = [str(v) for v in value if v is not None]
        else:
            raise ValueError(f"Invalid target config type: {type(value)}")
        out: list[str] = []
        for v in values:
            if v not in out:
                out.append(v)
        if not out:
            raise ValueError("Target list cannot be empty")
        return out

    def _resolve_n_classes(tf: str, target_col: str, default_n: int) -> int:
        tf_val = (n_classes_map or {}).get(tf)
        if isinstance(tf_val, dict):
            return int(tf_val.get(target_col, default_n))
        if tf_val is None:
            return int(default_n)
        return int(tf_val)

    def _resolve_class_names(
        tf: str,
        target_col: str,
        default_names: list[str],
        n_classes: int,
    ) -> list[str]:
        tf_val = (class_names_map or {}).get(tf, default_names)
        if isinstance(tf_val, dict):
            names = tf_val.get(target_col, default_names)
        else:
            names = tf_val
        names = list(names) if names else []
        if len(names) != n_classes:
            names = [f"class_{i}" for i in range(n_classes)]
        return names

    def _resolve_feature_target(tf: str, target_col: str) -> str:
        tf_val = (feature_source_map or {}).get(tf)
        if isinstance(tf_val, dict):
            return str(tf_val.get(target_col, target_col))
        if isinstance(tf_val, str):
            return tf_val
        return target_col

    override_keys = {
        "optuna_trials",
        "optuna_timeout",
        "optuna_metric",
        "exclude_tail_pct",
        "track_pred_metrics",
        "shuffle_split",
        "shuffle_seed",
        "shuffle_val_ratio",
        "shuffle_batches",
        "shuffle_batches_seed",
        "balance_strategy",
        "balance_apply_to",
        "class_weight_choices",
        "stage1_print_label_distribution",
        "cb_base_params",
        "window_space",
        "feature_space",
        "model_space",
        "stage1_validity_target_col",
        "stage1_quality_accuracy_threshold",
        "stage1_runtime_mode",
        "stage1_probe_enabled",
        "stage1_probe_tier_sizes",
        "stage1_probe_max_extra_candidates",
        "stage1_probe_source_scope",
        "stage1_backfill_low_quality_completed",
        "stage1_promotion_mode",
        "stage1_promoted_combo_cap_per_unit",
        "stage1_version",
        "stage1_v2_selector_config",
        "features_dir_override",
        "labels_dir_override",
    }

    def _resolve_overrides(tf: str, target_col: str) -> dict:
        tf_overrides = (optuna_overrides or {}).get(tf, {})
        if not isinstance(tf_overrides, dict):
            raise ValueError(
                f"Invalid optuna_overrides entry for tf={tf}: {type(tf_overrides)}"
            )
        if any(k in tf_overrides for k in override_keys):
            return tf_overrides
        target_overrides = tf_overrides.get(target_col, {})
        if not isinstance(target_overrides, dict):
            raise ValueError(
                f"Invalid target override for tf={tf}, target={target_col}: {type(target_overrides)}"
            )
        return target_overrides

    def _build_base_components(tf: str):
        if tf == "1m":
            cfg = Config1m()
            win = WindowSpace1m()
            feat = FeatureSpace1m()
            model = ModelSpace1m()
            opt_cls = Optimizer1m
        elif tf == "5m":
            cfg = Config5m()
            win = WindowSpace5m()
            feat = FeatureSpace5m()
            model = ModelSpace5m()
            opt_cls = Optimizer5m
        elif tf == "15m":
            cfg = Config15m()
            win = WindowSpace15m()
            feat = FeatureSpace15m()
            model = ModelSpace15m()
            opt_cls = Optimizer15m
        else:
            raise ValueError(f"Unknown timeframe: {tf}")
        return cfg, win, feat, model, opt_cls

    execution_units = []
    for tf in timeframes:
        base_cfg, _, _, _, _ = _build_base_components(tf)
        tf_targets = _normalize_target_list(target_map.get(tf), base_cfg.target)
        for target_col in tf_targets:
            cfg, win, feat, model, opt_cls = _build_base_components(tf)
            overrides = _resolve_overrides(tf, target_col)

            if "exclude_tail_pct" in overrides:
                cfg = replace(cfg, exclude_tail_pct=overrides["exclude_tail_pct"])
            if "features_dir_override" in overrides:
                cfg = replace(
                    cfg,
                    features_dir_override=Path(overrides["features_dir_override"]),
                )
            if "labels_dir_override" in overrides:
                cfg = replace(
                    cfg,
                    labels_dir_override=Path(overrides["labels_dir_override"]),
                )
            if "cb_base_params" in overrides:
                merged_cb = dict(cfg.cb_base_params)
                merged_cb.update(dict(overrides["cb_base_params"]))
                cfg = replace(cfg, cb_base_params=merged_cb)
            if "window_space" in overrides:
                win = replace(win, **overrides["window_space"])
            if "feature_space" in overrides:
                feat = replace(feat, **overrides["feature_space"])
            if "model_space" in overrides:
                model = replace(model, **overrides["model_space"])
            if "stage1_print_label_distribution" in overrides:
                stage1_print_label_distribution = bool(
                    overrides["stage1_print_label_distribution"]
                )
            if "stage1_quality_accuracy_threshold" in overrides:
                stage1_quality_accuracy_threshold = float(
                    overrides["stage1_quality_accuracy_threshold"]
                )
            if "stage1_runtime_mode" in overrides:
                stage1_runtime_mode = str(overrides["stage1_runtime_mode"]).strip().lower()
            if "stage1_probe_enabled" in overrides:
                stage1_probe_enabled = bool(overrides["stage1_probe_enabled"])
            if "stage1_probe_tier_sizes" in overrides:
                stage1_probe_tier_sizes = [
                    int(max(0, x))
                    for x in list(overrides["stage1_probe_tier_sizes"] or [])
                ]
            if "stage1_probe_max_extra_candidates" in overrides:
                stage1_probe_max_extra_candidates = int(
                    max(0, overrides["stage1_probe_max_extra_candidates"])
                )
            if "stage1_probe_source_scope" in overrides:
                stage1_probe_source_scope = str(overrides["stage1_probe_source_scope"])
            if "stage1_backfill_low_quality_completed" in overrides:
                stage1_backfill_low_quality_completed = bool(
                    overrides["stage1_backfill_low_quality_completed"]
                )
            if "stage1_promotion_mode" in overrides:
                stage1_promotion_mode = str(overrides["stage1_promotion_mode"])
            if "stage1_promoted_combo_cap_per_unit" in overrides:
                stage1_promoted_combo_cap_per_unit = int(
                    max(1, overrides["stage1_promoted_combo_cap_per_unit"])
                )
            if "stage1_version" in overrides:
                stage1_version = normalize_stage1_version(overrides["stage1_version"])
                stage1_mode = stage1_mode_name(stage1_version)
            if "stage1_v2_selector_config" in overrides and stage1_version == "v2":
                stage1_v2_cfg = build_stage1_v2_selector_config(
                    overrides["stage1_v2_selector_config"]
                )

            if str(getattr(win, "window_selection_mode", "")) != "stage1_fold_cv":
                raise ValueError(
                    f"Stage-1 runner requires window_selection_mode='stage1_fold_cv'. "
                    f"Got tf={tf}, target={target_col}, mode={getattr(win, 'window_selection_mode', None)}"
                )

            # Stage-1 validation should use a stable completeness mask.
            # Default behavior:
            # - target_4class validates against itself
            # - other targets validate against target_4class unless explicitly overridden
            validity_target_col = overrides.get("stage1_validity_target_col")
            if validity_target_col is None:
                validity_target_col = (
                    target_col if str(target_col) == "target_4class" else "target_4class"
                )
            validity_target_col = str(validity_target_col)

            feature_target_col = _resolve_feature_target(tf, target_col)
            if target_registry and target_col in target_registry:
                target_def = target_registry[target_col]
                n_classes = int(
                    target_def.get(
                        "n_classes",
                        _resolve_n_classes(tf, target_col, cfg.n_classes),
                    )
                )
                class_names = list(
                    target_def.get(
                        "class_names",
                        _resolve_class_names(
                            tf, target_col, list(cfg.class_names), n_classes
                        ),
                    )
                )
            else:
                n_classes = _resolve_n_classes(tf, target_col, cfg.n_classes)
                class_names = _resolve_class_names(
                    tf, target_col, list(cfg.class_names), n_classes
                )

            cfg = replace(
                cfg,
                target=target_col,
                feature_target=feature_target_col,
                n_classes=n_classes,
                class_names=tuple(class_names),
            )
            cfg.cb_base_params = cfg.cb_base_params.copy()
            if int(cfg.n_classes) == 2:
                cfg.cb_base_params["loss_function"] = "Logloss"
                cfg.cb_base_params["eval_metric"] = "Logloss"
            else:
                cfg.cb_base_params["loss_function"] = "MultiClass"
                cfg.cb_base_params["eval_metric"] = "MultiClass"

            optimizer = opt_cls(
                config=cfg,
                window_space=win,
                feature_space=feat,
                model_space=model,
            )
            stage1_combo_grid = build_stage1_combo_grid(win)
            execution_units.append(
                {
                    "tf": tf,
                    "target_col": target_col,
                    "feature_target_col": feature_target_col,
                    "validity_target_col": validity_target_col,
                    "overrides": overrides,
                    "optimizer": optimizer,
                    "stage1_combo_grid": stage1_combo_grid,
                    "selector_unit": Stage1SelectorUnitConfig(
                        timeframe=tf,
                        target=str(target_col),
                        feature_target=str(feature_target_col),
                        n_classes=int(cfg.n_classes),
                        class_names=list(cfg.class_names),
                        exclude_tail_pct=float(cfg.exclude_tail_pct),
                        cb_base_params=dict(cfg.cb_base_params),
                        num_boost_round=int(max(10, model.num_boost_round_min)),
                        selection_metric=str(cfg.optuna_metric),
                        selection_direction=(
                            "minimize"
                            if str(cfg.optuna_metric) in {"log_loss", "cross_direction_error"}
                            else "maximize"
                        ),
                        allowed_combo_keys=None,
                        features_dir=cfg.features_dir,
                        labels_dir=cfg.labels_dir,
                    ),
                }
            )

    if not execution_units:
        raise ValueError("No execution units were built.")

    if stage1_version == "v2":
        if stage1_v2_cfg is None:
            stage1_v2_cfg = build_stage1_v2_selector_config(None)
    else:
        stage1_v2_cfg = None

    ref_cfg = execution_units[0]["optimizer"].config
    default_run_id = f"stage1_run_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
    base_run_dir = ref_cfg.output_dir / (run_id or default_run_id)
    if not run_id:
        run_id = base_run_dir.name
    if resume and not base_run_dir.exists():
        raise FileNotFoundError(f"run_id not found: {base_run_dir}")

    run_config_path = base_run_dir / "run_config.json"
    if run_config_path.exists():
        with open(run_config_path, "r") as f:
            existing_run_config = json.load(f)
        existing_mode = str(existing_run_config.get("mode", ""))
        if existing_mode != stage1_mode:
            raise ValueError(
                "run_id points to non-stage1 run. "
                f"Expected mode={stage1_mode!r}, got mode={existing_mode!r} "
                f"for run_id={run_id}"
            )

    stage1_v2_fixed_policy_registry: dict[str, Any] | None = None
    stage1_v2_fixed_policy_registry_path: str | None = None
    if (
        stage1_v2_cfg is not None
        and str(stage1_v2_cfg.execution_mode) == STAGE1_V2_EXECUTION_MODE_FIXED_POLICY
    ):
        (
            stage1_v2_fixed_policy_registry,
            stage1_v2_fixed_policy_registry_path,
        ) = _stage1_v2_load_fixed_policy_registry(stage1_v2_cfg, base_run_dir)

    run_dir = base_run_dir / model_name
    run_dir.mkdir(parents=True, exist_ok=True)

    if stage1_runtime_mode not in {"routine", "adaptive"}:
        stage1_runtime_mode = "adaptive" if stage1_probe_enabled else "routine"
    if stage1_runtime_mode == "routine":
        stage1_probe_enabled = False
    if stage1_probe_max_extra_candidates <= 0 or not any(stage1_probe_tier_sizes):
        stage1_probe_enabled = False
        if stage1_runtime_mode != "routine":
            stage1_runtime_mode = "routine"

    run_config = {
        "run_id": run_id,
        "model_name": model_name,
        "mode": stage1_mode,
        "stage1_version": str(stage1_version),
        "run_description": run_description,
        "stage1_runtime_mode": str(stage1_runtime_mode),
        "stage1_quality_accuracy_threshold": float(stage1_quality_accuracy_threshold),
        "stage1_probe_enabled": bool(stage1_probe_enabled),
        "stage1_probe_tier_sizes": [int(v) for v in stage1_probe_tier_sizes],
        "stage1_probe_max_extra_candidates": int(stage1_probe_max_extra_candidates),
        "stage1_probe_source_scope": str(stage1_probe_source_scope),
        "stage1_backfill_low_quality_completed": bool(stage1_backfill_low_quality_completed),
        "stage1_promotion_mode": str(stage1_promotion_mode),
        "stage1_promoted_combo_cap_per_unit": int(stage1_promoted_combo_cap_per_unit),
        "timeframes": sorted({u["tf"] for u in execution_units}),
        "targets": {
            tf: sorted({u["target_col"] for u in execution_units if u["tf"] == tf})
            for tf in sorted({u["tf"] for u in execution_units})
        },
        "execution_units": [
            {
                "timeframe": str(u["tf"]),
                "target": str(u["target_col"]),
                "feature_target": str(u["feature_target_col"]),
                "features_dir": str(u["optimizer"].config.features_dir),
                "labels_dir": str(u["optimizer"].config.labels_dir),
            }
            for u in execution_units
        ],
        "created_at": datetime.now().isoformat(),
    }
    if pred_batch_min is not None:
        run_config["pred_batch_min"] = int(pred_batch_min)
    if pred_batch_max is not None:
        run_config["pred_batch_max"] = int(pred_batch_max)
    if stage1_v2_cfg is not None:
        run_config["stage1_v2_artifact_contract_version"] = (
            STAGE1_V2_ARTIFACT_CONTRACT_VERSION
        )
        run_config["stage1_v2_selector_config"] = asdict(stage1_v2_cfg)
        run_config["stage1_v2_execution_mode"] = str(stage1_v2_cfg.execution_mode)
        if stage1_v2_fixed_policy_registry_path is not None:
            run_config["stage1_v2_fixed_policy_registry_path"] = str(
                stage1_v2_fixed_policy_registry_path
            )
    with open(base_run_dir / "run_config.json", "w") as f:
        json.dump(run_config, f, indent=2)

    if stage1_v2_cfg is not None:
        contract_path = base_run_dir / "stage1_v2_artifact_contract.json"
        with open(contract_path, "w") as f:
            json.dump(stage1_v2_contract_payload(stage1_v2_cfg), f, indent=2)

    if stage1_probe_source_scope not in {"current", "archive", "current+archive"}:
        stage1_probe_source_scope = "current+archive"
    if stage1_promotion_mode not in {"global", "step_local", "repeat"}:
        stage1_promotion_mode = "global"

    dynamic_registry_path: Path | None = None
    dynamic_registry: dict[str, Any] = {"units": {}}
    if stage1_probe_enabled:
        dynamic_registry_path = base_run_dir / "stage1_dynamic_combo_registry.json"
        dynamic_registry = _stage1_load_dynamic_registry(dynamic_registry_path)
        _stage1_save_dynamic_registry(dynamic_registry_path, dynamic_registry)

    unit_history_stats: dict[str, dict[str, dict[str, Any]]] = {}
    unit_promoted_triplets: dict[str, list[tuple[int, int, int]]] = {}
    for unit in execution_units:
        tf = str(unit["tf"])
        target_col = str(unit["target_col"])
        model_key_unit = f"{tf}/{target_col}"
        safe_target = str(target_col).replace("/", "_")
        unit_dir = run_dir / tf / safe_target
        cfg_local = unit["optimizer"].config

        if stage1_probe_enabled:
            try:
                history = _stage1_scan_unit_history_candidates(
                    unit_dir=unit_dir,
                    source_scope=stage1_probe_source_scope,
                    n_classes=int(cfg_local.n_classes),
                    class_names=list(cfg_local.class_names),
                    quality_threshold=float(stage1_quality_accuracy_threshold),
                )
            except Exception:
                history = {}
        else:
            history = {}
        unit_history_stats[model_key_unit] = history

        promoted_rows = (
            dynamic_registry.get("units", {}).get(model_key_unit, {}).get("combos", {})
            if stage1_probe_enabled
            else {}
        )
        promoted_triplets: list[tuple[int, int, int]] = []
        if isinstance(promoted_rows, dict):
            for _, row in promoted_rows.items():
                tri_raw = row.get("triplet")
                if isinstance(tri_raw, (list, tuple)) and len(tri_raw) == 3:
                    try:
                        promoted_triplets.append(
                            (int(tri_raw[0]), int(tri_raw[1]), int(tri_raw[2]))
                        )
                    except Exception:
                        continue
        unit_promoted_triplets[model_key_unit] = promoted_triplets

    if verbose:
        print("=" * 100)
        print("HTF STAGE-1 WALK-FORWARD (CATBOOST, ISOLATED)")
        print("=" * 100)
        print(f"\nRun ID: {run_id}")
        print(f"Description: {run_description}")
        print(f"Stage1 version: {stage1_version}")
        if pred_batch_min is not None or pred_batch_max is not None:
            print(
                "Prediction batch filter: "
                f"min={pred_batch_min if pred_batch_min is not None else '-inf'}, "
                f"max={pred_batch_max if pred_batch_max is not None else '+inf'}"
            )
        print(
            "Stage1 adaptive quality: "
            f"runtime_mode={stage1_runtime_mode}, "
            f"threshold={stage1_quality_accuracy_threshold:.3f}, "
            f"probe_enabled={bool(stage1_probe_enabled)}, "
            f"probe_scope={stage1_probe_source_scope}, "
            f"probe_tiers={stage1_probe_tier_sizes}, "
            f"probe_cap={stage1_probe_max_extra_candidates}, "
            f"backfill_low_quality={bool(stage1_backfill_low_quality_completed)}, "
            f"promotion_mode={stage1_promotion_mode}, "
            f"promotion_cap={stage1_promoted_combo_cap_per_unit}"
        )
        if stage1_v2_cfg is not None:
            print(
                "Stage1-v2 foundation: "
                f"execution_mode={stage1_v2_cfg.execution_mode}, "
                f"selector={stage1_v2_cfg.feature_selector_method}, "
                f"importance={stage1_v2_cfg.feature_importance_type}"
            )

        for unit in execution_units:
            tf = unit["tf"]
            cfg = unit["optimizer"].config
            win = unit["optimizer"].window_space
            combos = build_stage1_combo_grid(win)
            fold_grid = sorted(
                {int(v) for v in (getattr(win, "stage1_fold_grid", []) or [])}
            )
            val_grid = list(getattr(win, "stage1_val_batches_grid", []) or [])
            if not val_grid:
                val_grid = [int(getattr(win, "stage1_val_batches_per_fold", 1))]
            triplet_grid_raw = list(getattr(win, "stage1_triplet_grid", []) or [])
            triplet_grid = []
            for item in triplet_grid_raw:
                if isinstance(item, dict):
                    f = item.get("fold_count", item.get("fold"))
                    v = item.get("val_batches_per_fold", item.get("val"))
                    t = item.get("train_batches_per_fold", item.get("train"))
                    if f is not None and v is not None and t is not None:
                        triplet_grid.append((int(f), int(v), int(t)))
                elif isinstance(item, (list, tuple)) and len(item) >= 3:
                    triplet_grid.append((int(item[0]), int(item[1]), int(item[2])))
            triplet_grid = sorted(set(triplet_grid))
            pair_grid_raw = list(getattr(win, "stage1_pair_grid", []) or [])
            pair_grid = []
            for item in pair_grid_raw:
                if isinstance(item, dict):
                    v = item.get("val_batches_per_fold", item.get("val"))
                    t = item.get("train_batches_per_fold", item.get("train"))
                    if v is not None and t is not None:
                        pair_grid.append((int(v), int(t)))
                elif isinstance(item, (list, tuple)) and len(item) >= 2:
                    pair_grid.append((int(item[0]), int(item[1])))
            pair_grid = sorted(set(pair_grid))
            train_mult_grid = list(getattr(win, "stage1_train_multiplier_grid", []) or [])
            train_grid = list(getattr(win, "stage1_train_batches_grid", []) or [])
            print(f"\n  {tf}/{cfg.target}:")
            if triplet_grid:
                print(
                    "    stage1_grid: "
                    f"triplets={triplet_grid}, "
                    f"combinations={len(combos)}"
                )
            elif pair_grid:
                print(
                    "    stage1_grid: "
                    f"folds={(fold_grid if fold_grid else f'{int(win.stage1_folds_min)}-{int(win.stage1_folds_max)}')}, "
                    f"pairs={pair_grid}, "
                    f"combinations={len(combos)}"
                )
            elif train_mult_grid:
                print(
                    "    stage1_grid: "
                    f"folds={(fold_grid if fold_grid else f'{int(win.stage1_folds_min)}-{int(win.stage1_folds_max)}')}, "
                    f"val_grid={val_grid}, "
                    f"train=val*x{train_mult_grid} "
                    f"(fallback_train_grid={train_grid}), "
                    f"combinations={len(combos)}"
                )
            else:
                print(
                    "    stage1_grid: "
                    f"folds={(fold_grid if fold_grid else f'{int(win.stage1_folds_min)}-{int(win.stage1_folds_max)}')}, "
                    f"val_grid={val_grid}, "
                    f"train_grid={train_grid}, "
                    f"combinations={len(combos)}"
                )
            if stage1_print_label_distribution:
                label_dist = compute_label_distribution(
                    cfg.labels_dir,
                    tf,
                    cfg.target,
                    exclude_tail_pct=cfg.exclude_tail_pct,
                )
                if not label_dist.is_empty():
                    print("    label_distribution:")
                    for row in label_dist.iter_rows(named=True):
                        class_idx = int(row["class_id"])
                        label_name = (
                            cfg.class_names[class_idx]
                            if 0 <= class_idx < len(cfg.class_names)
                            else f"class_{class_idx}"
                        )
                        print(
                            f"      {label_name}: {int(row['count'])} ({float(row['pct']):.1f}%)"
                        )

    valid_by_unit: dict[tuple[str, str], list[int]] = {}
    for unit in execution_units:
        tf = unit["tf"]
        cfg = unit["optimizer"].config
        validity_target_col = str(unit.get("validity_target_col") or cfg.target)
        batches = get_valid_batches(
            cfg.features_dir,
            cfg.labels_dir,
            tf,
            min_rows=None,
            target_col=cfg.target,
            feature_target_col=(cfg.feature_target or cfg.target),
            exclude_tail_pct=cfg.exclude_tail_pct,
            validity_target_col=validity_target_col,
        )
        valid_by_unit[(tf, cfg.target)] = batches
        if verbose:
            total = len(list((cfg.labels_dir / tf).glob("batch_*.parquet")))
            invalid = max(0, total - len(batches))
            validity_note = (
                ""
                if validity_target_col == cfg.target
                else f", validity_target={validity_target_col}"
            )
            print(
                f"  {tf}/{cfg.target}: {len(batches)}/{total} valid batches "
                f"({invalid} below threshold{validity_note})"
            )

    common_valid = None
    for batches in valid_by_unit.values():
        s = set(batches)
        common_valid = s if common_valid is None else (common_valid & s)
    common_valid_desc = sorted(common_valid or [], reverse=True)
    if verbose:
        print(f"  Common valid across all units: {len(common_valid_desc)} batches")

    if not common_valid_desc:
        raise ValueError("No common valid batches across execution units")

    max_lookback_min = max(int(u["optimizer"].window_space.lookback_min) for u in execution_units)
    eligible_desc = [b for b in common_valid_desc if b > max_lookback_min]
    if pred_batch_min is not None:
        eligible_desc = [b for b in eligible_desc if int(b) >= int(pred_batch_min)]
    if pred_batch_max is not None:
        eligible_desc = [b for b in eligible_desc if int(b) <= int(pred_batch_max)]
    if not eligible_desc:
        raise ValueError(
            f"No valid batches with sufficient training data. Need batch > {max_lookback_min}, have 0 valid."
        )

    max_steps = len(eligible_desc)
    if n_steps is None:
        n_steps = max_steps
    n_steps = min(int(n_steps), max_steps)
    step_batches = list(reversed(eligible_desc[:n_steps]))

    if verbose:
        print(f"\n  Running {n_steps} steps (max possible: {max_steps})")
        print("  Walk direction: oldest_to_newest")
        print(f"  First prediction batch: {step_batches[0]}")
        print(f"  Last prediction batch: {step_batches[-1]}")
        if resume:
            print("\n  Resume coverage against active triplet grid:")
            for unit in execution_units:
                tf = unit["tf"]
                target_col = unit["target_col"]
                safe_target = str(target_col).replace("/", "_")
                expected_stage1_combos = list(unit.get("stage1_combo_grid") or [])
                complete_steps = 0
                needs_migration_steps = 0
                partial_steps = 0
                missing_steps = 0
                for pred_batch in step_batches:
                    step_dir = run_dir / tf / safe_target / f"batch_{int(pred_batch):04d}"
                    st = _stage1_step_artifact_status(
                        step_dir,
                        expected_combos=(
                            None if stage1_probe_enabled else expected_stage1_combos
                        ),
                    )
                    if not st.get("is_complete", False):
                        if st.get("reason") == "missing_expected_combos":
                            partial_steps += 1
                        else:
                            missing_steps += 1
                        continue
                    if st.get("reason") == "ok_needs_grid_migration":
                        needs_migration_steps += 1
                    else:
                        complete_steps += 1
                print(
                    f"    {tf}/{target_col}: "
                    f"complete={complete_steps}, "
                    f"needs_migration={needs_migration_steps}, "
                    f"partial={partial_steps}, "
                    f"missing={missing_steps}"
                )

    step_results: dict[str, list[dict[str, Any]]] = defaultdict(list)
    model_index_entries: list[dict[str, Any]] = []
    progress_rows: list[dict[str, Any]] = []
    stage1_v2_progress_rows: list[dict[str, Any]] = []
    stage1_v2_baseline_vs_selected_rows: list[dict[str, Any]] = []
    stage1_v2_feature_importance_rows: list[dict[str, Any]] = []
    stage1_v2_feature_mask_rows: list[dict[str, Any]] = []
    t_start = time.time()

    for step_idx, pred_batch in enumerate(step_batches, start=1):
        train_end = int(pred_batch) - 1
        step_t0 = time.time()
        if verbose:
            print("\n" + "#" * 80)
            print(
                f"#  STEP {step_idx}/{n_steps} | Train batches 1-{train_end} → Predict batch {pred_batch}"
            )
            print("#" * 80)

        for unit in execution_units:
            tf = unit["tf"]
            optimizer = unit["optimizer"]
            cfg = optimizer.config
            target_col = unit["target_col"]
            feature_target_col = unit["feature_target_col"]
            expected_stage1_combos = list(unit.get("stage1_combo_grid") or [])
            model_key = f"{model_name}/{tf}/{target_col}"
            safe_target = str(target_col).replace("/", "_")
            step_dir = run_dir / tf / safe_target / f"batch_{int(pred_batch):04d}"
            stage1_dir = step_dir / "stage1"
            step_dir.mkdir(parents=True, exist_ok=True)
            stage1_dir.mkdir(parents=True, exist_ok=True)
            summary_path = stage1_dir / "stage1_step_summary.json"

            try:
                unit_key = f"{tf}/{target_col}"
                probe_log_rows: list[dict[str, Any]] = []
                probe_enrich_only = False
                probe_tiers_run = 0
                probe_candidates_evaluated = 0
                quality_unresolved = False
                probe_exhausted = False

                base_triplets: list[tuple[int, int, int]] = [
                    (
                        int(c["fold_count"]),
                        int(c["val_batches_per_fold"]),
                        int(c["train_batches_per_fold"]),
                    )
                    for c in expected_stage1_combos
                ]
                promoted_triplets = list(unit_promoted_triplets.get(unit_key, []))
                active_triplets: list[tuple[int, int, int]] = []
                seen_triplets: set[tuple[int, int, int]] = set()
                for tri in base_triplets + promoted_triplets:
                    if tri in seen_triplets:
                        continue
                    seen_triplets.add(tri)
                    active_triplets.append((int(tri[0]), int(tri[1]), int(tri[2])))

                if resume and resume_mode == "skip_completed":
                    artifact_status = _stage1_step_artifact_status(
                        step_dir,
                        expected_combos=(
                            None if stage1_probe_enabled else expected_stage1_combos
                        ),
                    )
                    if (
                        not stage1_probe_enabled
                        and
                        artifact_status["is_complete"]
                        and artifact_status.get("reason") == "ok_needs_grid_migration"
                    ):
                        coverage = artifact_status.get("coverage") or {}
                        migration = _stage1_migrate_step_to_expected_grid(
                            step_dir=step_dir,
                            expected_combos=expected_stage1_combos,
                            coverage=coverage,
                        )
                        if migration.get("migrated"):
                            if verbose:
                                print(f"\n  {model_key}:")
                                print(
                                    "    Resume: migrated existing step to active triplet grid; "
                                    f"archived extras at {migration.get('archive_dir')}"
                                )
                            # Re-check status after migration.
                            artifact_status = _stage1_step_artifact_status(
                                step_dir,
                                expected_combos=expected_stage1_combos,
                            )
                        elif verbose:
                            print(f"\n  {model_key}:")
                            print(
                                "    Resume: grid migration skipped; "
                                f"reason={migration.get('reason')}"
                            )

                    if artifact_status["is_complete"]:
                        if stage1_probe_enabled and stage1_backfill_low_quality_completed:
                            winner_existing = _stage1_get_step_winner_metrics(
                                stage1_dir=stage1_dir,
                                n_classes=int(cfg.n_classes),
                                class_names=list(cfg.class_names),
                            )
                            winner_acc_existing = (
                                float(winner_existing.get("accuracy", 0.0) or 0.0)
                                if winner_existing
                                else 0.0
                            )
                            if winner_existing is None or winner_acc_existing < float(
                                stage1_quality_accuracy_threshold
                            ):
                                probe_enrich_only = True
                                if verbose:
                                    print(f"\n  {model_key}:")
                                    print(
                                        "    Resume: completed step below quality threshold; "
                                        "running probe enrichment."
                                    )
                            else:
                                if verbose:
                                    print(f"\n  {model_key}:")
                                    print("    Resume: stage1 step already completed; skipping.")
                                progress_rows.append(
                                    {
                                        "model_key": model_key,
                                        "timeframe": tf,
                                        "target": target_col,
                                        "pred_batch": int(pred_batch),
                                        "step": int(step_idx),
                                        "status": "skipped_completed",
                                        "reason": "artifacts_complete_quality_pass",
                                        "runtime_s": 0.0,
                                    }
                                )
                                continue
                        else:
                            if verbose:
                                print(f"\n  {model_key}:")
                                print("    Resume: stage1 step already completed; skipping.")
                            progress_rows.append(
                                {
                                    "model_key": model_key,
                                    "timeframe": tf,
                                    "target": target_col,
                                    "pred_batch": int(pred_batch),
                                    "step": int(step_idx),
                                    "status": "skipped_completed",
                                    "reason": "artifacts_complete",
                                    "runtime_s": 0.0,
                                }
                            )
                            continue
                    if summary_path.exists() and verbose and not probe_enrich_only:
                        reason = str(artifact_status.get("reason", "incomplete"))
                        missing = list(artifact_status.get("missing", []))
                        missing_expected_count = int(
                            artifact_status.get("missing_expected_count", 0) or 0
                        )
                        print(f"\n  {model_key}:")
                        if missing:
                            print(
                                "    Resume: found incomplete stage1 artifacts; rebuilding. "
                                f"reason={reason}, missing={missing}"
                            )
                        elif missing_expected_count > 0:
                            print(
                                "    Resume: found partial active-grid coverage; rebuilding. "
                                f"reason={reason}, missing_expected_combos={missing_expected_count}"
                            )
                        else:
                            print(
                                "    Resume: found incomplete stage1 artifacts; rebuilding. "
                                f"reason={reason}"
                            )

                if verbose:
                    print(f"\n  {model_key}:")
                    if probe_enrich_only:
                        print("    Running stage1 probe enrichment on existing artifacts...")
                    else:
                        print("    Running isolated stage1 full-grid payload generation...")

                step_optimizer = optimizer.create_step_optimizer()
                stage1_t0 = time.time()
                if not probe_enrich_only:
                    base_combo_override = [
                        {
                            "fold_count": int(tri[0]),
                            "val_batches_per_fold": int(tri[1]),
                            "train_batches_per_fold": int(tri[2]),
                            "action_key": _stage1_action_key_from_triplet(
                                int(tri[0]),
                                int(tri[1]),
                                int(tri[2]),
                            ),
                        }
                        for tri in active_triplets
                    ]
                    result = evaluate_stage1_grid(
                        step_optimizer=step_optimizer,
                        train_end=int(train_end),
                        pred_batch=int(pred_batch),
                        step_stage1_dir=stage1_dir,
                        combo_grid_override=base_combo_override,
                        append_mode=False,
                        candidate_source="base_grid",
                        probe_tier=0,
                        discovered_from="active_triplet_grid",
                    )
                else:
                    with open(summary_path, "r") as f:
                        existing_summary = json.load(f)
                    result = {
                        "summary": existing_summary,
                        "artifacts": {
                            "stage1_step_summary": str(stage1_dir / "stage1_step_summary.json"),
                            "stage1_combo_index": str(stage1_dir / "stage1_combo_index.parquet"),
                            "stage1_fold_windows": str(stage1_dir / "stage1_fold_windows.parquet"),
                            "stage1_val_predictions": str(stage1_dir / "stage1_val_predictions.parquet"),
                            "stage1_pred_batch_predictions": str(stage1_dir / "stage1_pred_batch_predictions.parquet"),
                            "stage1_predecision_context": str(stage1_dir / "stage1_predecision_context.json"),
                            "stage1_predecision_context_parquet": str(stage1_dir / "stage1_predecision_context.parquet"),
                            "stage1_runtime_profile": str(stage1_dir / "stage1_runtime_profile.json"),
                        },
                        "config_snapshot": {
                            "config": asdict(cfg),
                            "window_space": asdict(optimizer.window_space),
                            "feature_space": asdict(optimizer.feature_space),
                            "model_space": asdict(optimizer.model_space),
                        },
                    }

                winner_before = _stage1_get_step_winner_metrics(
                    stage1_dir=stage1_dir,
                    n_classes=int(cfg.n_classes),
                    class_names=list(cfg.class_names),
                )
                winner_before_acc = (
                    float(winner_before.get("accuracy", 0.0) or 0.0)
                    if winner_before
                    else 0.0
                )

                if (
                    stage1_probe_enabled
                    and winner_before_acc < float(stage1_quality_accuracy_threshold)
                    and stage1_probe_max_extra_candidates > 0
                ):
                    combo_index_path = stage1_dir / "stage1_combo_index.parquet"
                    existing_step_combo_keys: set[str] = set()
                    if combo_index_path.exists():
                        combo_index_df = pl.read_parquet(combo_index_path)
                        if "action_key" in combo_index_df.columns:
                            existing_step_combo_keys = {
                                str(v)
                                for v in combo_index_df["action_key"].to_list()
                                if v is not None and str(v) != ""
                            }
                    active_combo_keys = {
                        _stage1_action_key_from_triplet(int(t[0]), int(t[1]), int(t[2]))
                        for t in active_triplets
                    }
                    ranked_candidates = _stage1_rank_probe_candidates(
                        history_stats=unit_history_stats.get(unit_key, {}),
                        active_combo_keys=active_combo_keys,
                        existing_step_combo_keys=existing_step_combo_keys,
                        quality_threshold=float(stage1_quality_accuracy_threshold),
                        max_candidates=int(stage1_probe_max_extra_candidates),
                    )
                    consumed = 0
                    winner_current = winner_before
                    winner_current_acc = winner_before_acc
                    for tier_idx, tier_size in enumerate(stage1_probe_tier_sizes, start=1):
                        if tier_size <= 0:
                            continue
                        if consumed >= int(stage1_probe_max_extra_candidates):
                            break
                        remaining = ranked_candidates[consumed : int(stage1_probe_max_extra_candidates)]
                        if not remaining:
                            break
                        tier_take = min(int(tier_size), len(remaining))
                        tier_candidates = remaining[:tier_take]
                        consumed += tier_take
                        probe_tiers_run += 1
                        probe_candidates_evaluated += int(tier_take)

                        tier_combo_override = [
                            {
                                "fold_count": int(c["fold_count"]),
                                "val_batches_per_fold": int(c["val_batches_per_fold"]),
                                "train_batches_per_fold": int(c["train_batches_per_fold"]),
                                "action_key": str(c["action_key"]),
                            }
                            for c in tier_candidates
                        ]
                        discovered_from = ";".join(
                            sorted(
                                {
                                    str(c.get("discovered_from", ""))
                                    for c in tier_candidates
                                    if str(c.get("discovered_from", ""))
                                }
                            )
                        )
                        evaluate_stage1_grid(
                            step_optimizer=step_optimizer,
                            train_end=int(train_end),
                            pred_batch=int(pred_batch),
                            step_stage1_dir=stage1_dir,
                            combo_grid_override=tier_combo_override,
                            append_mode=True,
                            candidate_source="archive_probe",
                            probe_tier=int(tier_idx),
                            discovered_from=(discovered_from or "history_artifacts"),
                        )

                        winner_after = _stage1_get_step_winner_metrics(
                            stage1_dir=stage1_dir,
                            n_classes=int(cfg.n_classes),
                            class_names=list(cfg.class_names),
                        )
                        winner_after_acc = (
                            float(winner_after.get("accuracy", 0.0) or 0.0)
                            if winner_after
                            else 0.0
                        )
                        quality_pass_after = bool(
                            winner_after_acc >= float(stage1_quality_accuracy_threshold)
                        )
                        probe_log_rows.append(
                            {
                                "unit": unit_key,
                                "pred_batch": int(pred_batch),
                                "phase": "probe_tier",
                                "tier_idx": int(tier_idx),
                                "evaluated_count": int(tier_take),
                                "winner_before": float(winner_current_acc),
                                "winner_after": float(winner_after_acc),
                                "quality_pass_after": bool(quality_pass_after),
                                "stop_reason": (
                                    "quality_reached" if quality_pass_after else "continue"
                                ),
                            }
                        )
                        winner_current = winner_after
                        winner_current_acc = winner_after_acc
                        if quality_pass_after:
                            break
                    if winner_current is not None:
                        winner_before = winner_current
                        winner_before_acc = winner_current_acc
                    if winner_before_acc < float(stage1_quality_accuracy_threshold):
                        quality_unresolved = True
                        probe_exhausted = True

                summary_updated = _stage1_update_step_summary_quality(
                    stage1_dir=stage1_dir,
                    quality_threshold=float(stage1_quality_accuracy_threshold),
                    winner=winner_before,
                    quality_unresolved=bool(quality_unresolved),
                    probe_exhausted=bool(probe_exhausted),
                    probe_enabled=bool(stage1_probe_enabled),
                    probe_tiers_run=int(probe_tiers_run),
                    probe_candidates_evaluated=int(probe_candidates_evaluated),
                )
                probe_log_path = _stage1_merge_probe_log(stage1_dir, probe_log_rows)
                result.setdefault("artifacts", {})
                result["artifacts"]["stage1_probe_log"] = str(probe_log_path)

                winner_key = str(summary_updated.get("winner_combo_key") or "")
                winner_acc = summary_updated.get("winner_accuracy")
                winner_pass = bool(summary_updated.get("quality_pass", False))
                if (
                    stage1_probe_enabled
                    and stage1_promotion_mode == "global"
                    and winner_key
                    and winner_pass
                ):
                    base_action_keys = {
                        _stage1_action_key_from_triplet(int(t[0]), int(t[1]), int(t[2]))
                        for t in base_triplets
                    }
                    if winner_key not in base_action_keys:
                        tri = _stage1_triplet_from_action_key(winner_key)
                        if tri is not None:
                            units_obj = dynamic_registry.setdefault("units", {})
                            unit_obj = units_obj.setdefault(unit_key, {})
                            combos_obj = unit_obj.setdefault("combos", {})
                            row = combos_obj.setdefault(
                                winner_key,
                                {
                                    "triplet": [int(tri[0]), int(tri[1]), int(tri[2])],
                                    "promoted_at_step": int(pred_batch),
                                    "quality_hits": 0,
                                    "quality_hit_steps": [],
                                    "last_quality_accuracy": None,
                                },
                            )
                            row["quality_hits"] = int(row.get("quality_hits", 0)) + 1
                            hit_steps = [int(v) for v in list(row.get("quality_hit_steps", []))]
                            if int(pred_batch) not in hit_steps:
                                hit_steps.append(int(pred_batch))
                            row["quality_hit_steps"] = sorted(set(hit_steps))
                            row["last_quality_accuracy"] = (
                                float(winner_acc) if winner_acc is not None else None
                            )
                            row["updated_at"] = datetime.now().isoformat()
                            ranked_keys = sorted(
                                combos_obj.keys(),
                                key=lambda k: (
                                    -int(combos_obj[k].get("quality_hits", 0)),
                                    -float(combos_obj[k].get("last_quality_accuracy", 0.0) or 0.0),
                                    str(k),
                                ),
                            )
                            keep_keys = ranked_keys[: int(stage1_promoted_combo_cap_per_unit)]
                            unit_obj["combos"] = {k: combos_obj[k] for k in keep_keys}
                            dynamic_registry["units"][unit_key] = unit_obj
                            _stage1_save_dynamic_registry(dynamic_registry_path, dynamic_registry)
                            unit_promoted_triplets[unit_key] = [
                                _stage1_triplet_from_action_key(k)
                                for k in keep_keys
                                if _stage1_triplet_from_action_key(k) is not None
                            ]

                runtime = time.time() - stage1_t0

                snapshot_path = stage1_dir / "stage1_config_snapshot.json"
                with open(snapshot_path, "w") as f:
                    json.dump(result["config_snapshot"], f, indent=2, default=str)

                stage1_v2_result = None
                if stage1_v2_cfg is not None:
                    stage1_v2_result = collect_stage1_v2_step_artifacts(
                        unit=unit["selector_unit"],
                        step_dir=step_dir,
                        step_idx=int(step_idx),
                        total_steps=int(n_steps),
                        selector_config=stage1_v2_cfg,
                        fixed_policy_registry=stage1_v2_fixed_policy_registry,
                        fixed_policy_registry_path=stage1_v2_fixed_policy_registry_path,
                        verbose=bool(
                            verbose
                            and stage1_v2_cfg.execution_mode != "parity"
                            and int(n_steps) <= 3
                        ),
                    )
                    result["artifacts"]["stage1_v2_step_summary"] = str(
                        stage1_v2_result["artifacts"]["summary"]
                    )
                    stage1_v2_progress_rows.append(
                        {
                            "model_key": model_key,
                            **stage1_v2_result["progress_row"],
                        }
                    )
                    stage1_v2_baseline_vs_selected_rows.append(
                        {
                            "model_key": model_key,
                            **stage1_v2_result["baseline_vs_selected_row"],
                        }
                    )
                    stage1_v2_feature_importance_rows.extend(
                        stage1_v2_result.get("feature_importance_rows", [])
                    )
                    stage1_v2_feature_mask_rows.extend(
                        stage1_v2_result.get("feature_mask_rows", [])
                    )

                batch_metadata = {
                    "run_id": run_id,
                    "mode": stage1_mode,
                    "stage1_version": str(stage1_version),
                    "model_name": model_name,
                    "timeframe": tf,
                    "target": target_col,
                    "feature_target": feature_target_col,
                    "pred_batch": int(pred_batch),
                    "train_end": int(train_end),
                    "step": int(step_idx),
                    "stage1_summary": summary_updated,
                    "artifacts": result["artifacts"],
                    "completed_at": datetime.now().isoformat(),
                }
                if stage1_v2_result is not None:
                    batch_metadata["stage1_v2_summary"] = stage1_v2_result["summary"]
                    batch_metadata["stage1_v2_artifacts"] = stage1_v2_result["artifacts"]
                with open(step_dir / "batch_metadata.json", "w") as f:
                    json.dump(batch_metadata, f, indent=2)

                model_index_entries.append(
                    {
                        "model_name": model_name,
                        "timeframe": tf,
                        "target": target_col,
                        "feature_target": feature_target_col,
                        "pred_batch": int(pred_batch),
                        "step": int(step_idx),
                        "batch_dir": str(step_dir),
                        "stage1_summary": summary_updated,
                    }
                )

                step_results[model_key].append(
                    {
                        "step": int(step_idx),
                        "pred_batch": int(pred_batch),
                        "train_end": int(train_end),
                        "runtime_s": float(runtime),
                        "summary": summary_updated,
                    }
                )
                progress_rows.append(
                    {
                        "model_key": model_key,
                        "timeframe": tf,
                        "target": target_col,
                        "pred_batch": int(pred_batch),
                        "step": int(step_idx),
                        "status": "completed",
                        "reason": (
                            "quality_unresolved"
                            if bool(summary_updated.get("quality_unresolved"))
                            else "ok"
                        ),
                        "runtime_s": float(runtime),
                    }
                )

                if verbose:
                    s = summary_updated
                    print(
                        "    Stage1 done: "
                        f"winner={s.get('winner_combo_key')}, "
                        f"winner_acc={float(s.get('winner_accuracy') or 0.0):.4f}, "
                        f"quality_pass={bool(s.get('quality_pass'))}, "
                        f"probe_tiers={int(s.get('probe_tiers_run', 0) or 0)}, "
                        f"probe_eval={int(s.get('probe_candidates_evaluated', 0) or 0)}, "
                        f"time={runtime:.1f}s"
                    )
                    print(
                        "    Saved: stage1_step_summary.json, stage1_combo_index.parquet, "
                        "stage1_fold_windows.parquet, stage1_val_predictions.parquet, "
                        "stage1_pred_batch_predictions.parquet, stage1_probe_log.parquet, "
                        "stage1_predecision_context.json, stage1_predecision_context.parquet"
                    )
                    if stage1_v2_result is not None:
                        v2_summary = stage1_v2_result["summary"]
                        print(
                            "    Stage1-v2 step: "
                            f"mode={v2_summary.get('execution_mode')}, "
                            f"winner_changed={bool(v2_summary.get('winner_changed'))}, "
                            f"combos={int(v2_summary.get('combo_count', 0) or 0)}"
                        )
            except Exception as e:
                if verbose:
                    print(f"  {model_key}: ERROR - {e}")
                step_results[model_key].append(
                    {
                        "step": int(step_idx),
                        "pred_batch": int(pred_batch),
                        "train_end": int(train_end),
                        "error": str(e),
                    }
                )
                progress_rows.append(
                    {
                        "model_key": model_key,
                        "timeframe": tf,
                        "target": target_col,
                        "pred_batch": int(pred_batch),
                        "step": int(step_idx),
                        "status": "error",
                        "reason": str(e),
                        "runtime_s": None,
                    }
                )

        if verbose:
            print(f"\n  Step {step_idx} completed in {time.time() - step_t0:.1f}s")

    idx_path = base_run_dir / "run_model_index.json"
    if idx_path.exists():
        with open(idx_path, "r") as f:
            idx_data = json.load(f)
    else:
        idx_data = {"run_id": run_id, "entries": []}
    idx_data["entries"].extend(model_index_entries)
    with open(idx_path, "w") as f:
        json.dump(idx_data, f, indent=2)

    progress_df = pl.DataFrame(progress_rows) if progress_rows else pl.DataFrame()
    if not progress_df.is_empty():
        progress_path = base_run_dir / "stage1_progress.parquet"
        progress_df.write_parquet(progress_path)
    else:
        progress_path = None

    stage1_v2_root_artifacts: dict[str, str] = {}
    if stage1_v2_cfg is not None:
        stage1_v2_root_artifacts = _stage1_v2_write_root_artifacts(
            base_run_dir=base_run_dir,
            run_id=str(run_id),
            stage1_v2_cfg=stage1_v2_cfg,
            progress_rows=stage1_v2_progress_rows,
            baseline_vs_selected_rows=stage1_v2_baseline_vs_selected_rows,
            feature_importance_rows=stage1_v2_feature_importance_rows,
            feature_mask_rows=stage1_v2_feature_mask_rows,
        )

    final = {
        "run_id": run_id,
        "mode": stage1_mode,
        "stage1_version": str(stage1_version),
        "model_name": model_name,
        "n_steps": int(n_steps),
        "stage1_runtime_mode": str(stage1_runtime_mode),
        "stage1_quality_accuracy_threshold": float(stage1_quality_accuracy_threshold),
        "stage1_probe_enabled": bool(stage1_probe_enabled),
        "stage1_probe_tier_sizes": [int(v) for v in stage1_probe_tier_sizes],
        "stage1_probe_max_extra_candidates": int(stage1_probe_max_extra_candidates),
        "stage1_probe_source_scope": str(stage1_probe_source_scope),
        "stage1_backfill_low_quality_completed": bool(stage1_backfill_low_quality_completed),
        "stage1_promotion_mode": str(stage1_promotion_mode),
        "stage1_promoted_combo_cap_per_unit": int(stage1_promoted_combo_cap_per_unit),
        "timeframes": sorted({u["tf"] for u in execution_units}),
        "step_batches": [int(b) for b in step_batches],
        "results": {k: v for k, v in step_results.items()},
        "runtime_s": float(time.time() - t_start),
        "dynamic_combo_registry": (
            str(dynamic_registry_path) if dynamic_registry_path is not None else None
        ),
        "completed_at": datetime.now().isoformat(),
    }
    if pred_batch_min is not None:
        final["pred_batch_min"] = int(pred_batch_min)
    if pred_batch_max is not None:
        final["pred_batch_max"] = int(pred_batch_max)
    if stage1_v2_cfg is not None:
        final["stage1_v2_artifact_contract_version"] = (
            STAGE1_V2_ARTIFACT_CONTRACT_VERSION
        )
        final["stage1_v2_selector_config"] = asdict(stage1_v2_cfg)
        final["stage1_v2_execution_mode"] = str(stage1_v2_cfg.execution_mode)
        final["stage1_v2_root_artifacts"] = dict(stage1_v2_root_artifacts)
        if stage1_v2_fixed_policy_registry_path is not None:
            final["stage1_v2_fixed_policy_registry_path"] = str(
                stage1_v2_fixed_policy_registry_path
            )
    with open(base_run_dir / "run_summary.json", "w") as f:
        json.dump(final, f, indent=2)

    run_state = {
        "run_id": run_id,
        "mode": stage1_mode,
        "stage1_version": str(stage1_version),
        "model_name": model_name,
        "resume": bool(resume),
        "resume_mode": str(resume_mode),
        "requested_n_steps": int(n_steps),
        "max_steps_available": int(max_steps),
        "stage1_runtime_mode": str(stage1_runtime_mode),
        "stage1_quality_accuracy_threshold": float(stage1_quality_accuracy_threshold),
        "stage1_probe_enabled": bool(stage1_probe_enabled),
        "stage1_probe_tier_sizes": [int(v) for v in stage1_probe_tier_sizes],
        "stage1_probe_max_extra_candidates": int(stage1_probe_max_extra_candidates),
        "stage1_probe_source_scope": str(stage1_probe_source_scope),
        "stage1_backfill_low_quality_completed": bool(stage1_backfill_low_quality_completed),
        "stage1_promotion_mode": str(stage1_promotion_mode),
        "stage1_promoted_combo_cap_per_unit": int(stage1_promoted_combo_cap_per_unit),
        "step_batches": [int(b) for b in step_batches],
        "execution_units": [
            {
                "timeframe": u["tf"],
                "target": u["target_col"],
                "feature_target": u["feature_target_col"],
                "lookback_min": int(u["optimizer"].window_space.lookback_min),
                "features_dir": str(u["optimizer"].config.features_dir),
                "labels_dir": str(u["optimizer"].config.labels_dir),
            }
            for u in execution_units
        ],
        "progress_artifact": str(progress_path) if progress_path is not None else None,
        "dynamic_combo_registry": (
            str(dynamic_registry_path) if dynamic_registry_path is not None else None
        ),
        "updated_at": datetime.now().isoformat(),
    }
    if pred_batch_min is not None:
        run_state["pred_batch_min"] = int(pred_batch_min)
    if pred_batch_max is not None:
        run_state["pred_batch_max"] = int(pred_batch_max)
    if stage1_v2_cfg is not None:
        run_state["stage1_v2_artifact_contract_version"] = (
            STAGE1_V2_ARTIFACT_CONTRACT_VERSION
        )
        run_state["stage1_v2_selector_config"] = asdict(stage1_v2_cfg)
        run_state["stage1_v2_execution_mode"] = str(stage1_v2_cfg.execution_mode)
        run_state["stage1_v2_root_artifacts"] = dict(stage1_v2_root_artifacts)
        if stage1_v2_fixed_policy_registry_path is not None:
            run_state["stage1_v2_fixed_policy_registry_path"] = str(
                stage1_v2_fixed_policy_registry_path
            )
    with open(base_run_dir / "stage1_run_state.json", "w") as f:
        json.dump(run_state, f, indent=2)

    if verbose:
        print("\n" + "#" * 80)
        print("#  STAGE-1 SUMMARY")
        print("#" * 80)
        print(f"Run ID: {run_id}")
        print(f"Runtime: {final['runtime_s']:.1f}s")
        for key, rows in final["results"].items():
            ok = len([r for r in rows if "error" not in r])
            err = len(rows) - ok
            print(f"{key}: steps_ok={ok}, steps_error={err}")

    return final
