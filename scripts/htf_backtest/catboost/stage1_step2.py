"""
Stage-1 Step-2 (CatBoost): Feature Noise Pruning
=================================================

This module runs an offline Stage-1 Step-2 pass:
1) Read Stage-1 step artifacts.
2) Select best-performing Stage-1 combo per step from prediction payloads.
3) Train baseline CatBoost models for each combo window and collect
   CatBoost built-in feature importance.
4) Identify noisy features per combo and also globally per timeframe/target.
5) Re-train with filtered features and compare prediction metrics vs baseline
   per combo.

The goal is to reduce noisy features without touching Step-1 runtime logic.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
from scripts.project_paths import resolve_project_root

from .stage1_selector_kernel import (
    _combo_key_from_row,
    _compute_metrics,
    _extract_selected_feature_names,
    _fit_catboost_model,
    _format_action_key,
    _full_proba_and_pred,
    _is_better_metric,
    _list_combo_metrics_from_pred_payload,
    _metric_direction,
    _metric_value,
    _resolve_shap_calc_type,
    _select_features_with_fallback,
)
from .stage1_selector_step import process_stage1_selector_step
from .utils import (
    BaseOptimizerConfig,
    ModelSearchSpace,
    WindowSearchSpace,
    coerce_stage1_batch_ids,
    get_feature_columns,
    load_batch,
    load_batches_by_ids,
    prepare_features_target,
)


@dataclass
class _Step2UnitConfig:
    timeframe: str
    target: str
    feature_target: str
    n_classes: int
    class_names: list[str]
    exclude_tail_pct: float
    cb_base_params: dict
    num_boost_round: int
    selection_metric: str
    selection_direction: str
    allowed_combo_keys: set[tuple[int, int, int]] | None
    features_dir: Path
    labels_dir: Path


def _fold_batch_ids(
    fold_row: dict[str, Any],
    *,
    prefix: str,
    start_batch: int,
    end_batch: int,
) -> list[int]:
    ids = coerce_stage1_batch_ids(fold_row.get(f"{prefix}_batch_ids"))
    if ids:
        return ids
    return list(range(int(start_batch), int(end_batch) + 1))


def _fold_order_ok(fold_row: dict[str, Any], *, pred_batch: int) -> bool:
    pos_keys = ("train_end_pos", "val_start_pos", "val_end_pos", "pred_pos")
    if all(fold_row.get(key) is not None for key in pos_keys):
        try:
            return bool(
                int(fold_row["train_end_pos"]) < int(fold_row["val_start_pos"])
                and int(fold_row["val_end_pos"]) < int(fold_row["pred_pos"])
            )
        except Exception:
            pass
    return bool(
        int(fold_row["train_end_batch"]) < int(fold_row["val_start_batch"])
        and int(fold_row["val_end_batch"]) < int(pred_batch)
    )


def _init_step2_unit_state(total_steps: int) -> dict[str, Any]:
    return {
        "baseline_rows_by_combo": {},
        "step_fold_plan_by_combo": {},
        "importance_rows_by_combo": {},
        "selected_features_rows_by_combo": {},
        "selector_fold_rows_by_combo": {},
        "filtered_rows_by_combo": {},
        "selected_prediction_rows_by_combo": {},
        "selected_feature_masks_by_combo": {},
        "all_importance_rows": [],
        "combo_meta": {},
        "failed_steps": [],
        "step_winner_rows": [],
        "step_debug_rows": [],
        "combo_debug_rows": [],
        "processed_steps": 0,
        "selected_combo_rows": 0,
        "reason_counts": {},
        "unit_t0": time.perf_counter(),
        "total_steps": int(total_steps),
    }


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


def _normalize_target_list(value: Any, default_target: str) -> list[str]:
    if value is None:
        return [default_target]
    if isinstance(value, str):
        out = [value]
    elif isinstance(value, (list, tuple, set)):
        out = [str(v) for v in value if v is not None]
    else:
        raise ValueError(f"Invalid target config type: {type(value)}")
    out = list(dict.fromkeys(out))
    if not out:
        raise ValueError("Target list cannot be empty")
    return out


def _resolve_overrides(tf: str, target_col: str, tf_overrides: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(tf_overrides, dict):
        return {}
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
        "cb_base_params",
        "window_space",
        "feature_space",
        "model_space",
        "features_dir_override",
        "labels_dir_override",
    }
    # Backward-compatible shape: {tf: {optuna_trials: ...}}
    if any(k in tf_overrides for k in override_keys):
        return tf_overrides
    # Target-scoped shape: {tf: {target_a: {...}, target_b: {...}}}
    val = tf_overrides.get(target_col, {})
    return val if isinstance(val, dict) else {}


def _resolve_n_classes(n_classes_map: dict[str, Any], tf: str, target: str, default_n: int) -> int:
    tf_val = n_classes_map.get(tf)
    if isinstance(tf_val, dict):
        return int(tf_val.get(target, default_n))
    if tf_val is None:
        return int(default_n)
    return int(tf_val)


def _resolve_class_names(
    class_names_map: dict[str, Any],
    tf: str,
    target: str,
    n_classes: int,
    default_names: list[str],
) -> list[str]:
    tf_val = class_names_map.get(tf, default_names)
    if isinstance(tf_val, dict):
        names = tf_val.get(target, default_names)
    else:
        names = tf_val
    names = list(names) if names else []
    if len(names) != n_classes:
        names = [f"class_{i}" for i in range(n_classes)]
    return names


def _resolve_feature_target(feature_source_map: dict[str, Any], tf: str, target: str) -> str:
    tf_val = feature_source_map.get(tf)
    if isinstance(tf_val, dict):
        return str(tf_val.get(target, target))
    if isinstance(tf_val, str):
        return tf_val
    return target


def _rows_to_debug_df(rows: list[dict[str, Any]]) -> pl.DataFrame:
    """
    Build a robust Polars DataFrame from sparse/mixed debug rows.

    Some debug rows are "failure-only" and others are "processed-only", so keys
    can differ by row. We normalize key sets and ask Polars to infer schema from
    all rows to avoid Null-builder append errors.
    """
    if not rows:
        return pl.DataFrame()
    all_keys = sorted({k for r in rows for k in r.keys()})
    normalized = [{k: r.get(k) for k in all_keys} for r in rows]
    return pl.from_dicts(normalized, infer_schema_length=None)


def _sort_action_key_ranking_rows(
    rows: list[dict[str, Any]],
    *,
    selection_direction: str,
) -> list[dict[str, Any]]:
    def _metric_sort_value(value: float | None) -> float:
        if value is None:
            return float("-inf") if selection_direction != "minimize" else float("inf")
        return float(value)

    reverse_metric = selection_direction != "minimize"
    rows_sorted = sorted(
        rows,
        key=lambda r: (
            -int(r.get("winner_count", 0) or 0),
            (
                -_metric_sort_value(r.get("mean_validation_metric"))
                if reverse_metric
                else _metric_sort_value(r.get("mean_validation_metric"))
            ),
            (
                -_metric_sort_value(r.get("mean_prediction_metric"))
                if reverse_metric
                else _metric_sort_value(r.get("mean_prediction_metric"))
            ),
            str(r.get("action_key", "")),
        ),
    )
    return rows_sorted


def _select_root_topk_action_keys(
    *,
    step_dirs: list[Path],
    unit: _Step2UnitConfig,
    topk_action_keys_per_root: int,
) -> dict[str, Any]:
    val_metric_sum: dict[str, float] = {}
    val_metric_count: dict[str, int] = {}
    pred_metric_sum: dict[str, float] = {}
    pred_metric_count: dict[str, int] = {}
    winner_count: dict[str, int] = {}
    rows_seen: dict[str, int] = {}
    steps_seen = 0
    missing_steps = 0

    for step_dir in step_dirs:
        stage1_dir = step_dir / "stage1"
        combo_path = stage1_dir / "stage1_combo_index.parquet"
        val_path = stage1_dir / "stage1_val_predictions.parquet"
        pred_path = stage1_dir / "stage1_pred_batch_predictions.parquet"
        if not (combo_path.exists() and val_path.exists() and pred_path.exists()):
            missing_steps += 1
            continue

        combo_df = pl.read_parquet(combo_path)
        val_df = pl.read_parquet(val_path)
        pred_df = pl.read_parquet(pred_path)
        if "scope" in val_df.columns:
            val_df = val_df.filter(pl.col("scope") == "val_fold")
        if "scope" in pred_df.columns:
            pred_df = pred_df.filter(pl.col("scope") == "pred_batch")
        if combo_df.is_empty() or val_df.is_empty() or pred_df.is_empty():
            missing_steps += 1
            continue

        val_metrics = _list_combo_metrics_from_pred_payload(
            pred_payload=val_df,
            combo_index=combo_df,
            allowed_combo_keys=unit.allowed_combo_keys,
            selection_metric=unit.selection_metric,
            selection_direction=unit.selection_direction,
            n_classes=unit.n_classes,
            class_names=unit.class_names,
        )
        pred_metrics = _list_combo_metrics_from_pred_payload(
            pred_payload=pred_df,
            combo_index=combo_df,
            allowed_combo_keys=unit.allowed_combo_keys,
            selection_metric=unit.selection_metric,
            selection_direction=unit.selection_direction,
            n_classes=unit.n_classes,
            class_names=unit.class_names,
        )
        if not val_metrics:
            missing_steps += 1
            continue

        steps_seen += 1
        pred_metric_map = {str(r["action_key"]): r for r in pred_metrics}
        for row in val_metrics:
            action_key = str(row["action_key"])
            metric_val = row.get("selection_value")
            if metric_val is not None:
                val_metric_sum[action_key] = val_metric_sum.get(action_key, 0.0) + float(
                    metric_val
                )
                val_metric_count[action_key] = val_metric_count.get(action_key, 0) + 1
            rows_seen[action_key] = rows_seen.get(action_key, 0) + int(row.get("pred_rows", 0) or 0)
            pred_row = pred_metric_map.get(action_key)
            if pred_row is not None and pred_row.get("selection_value") is not None:
                pred_metric_sum[action_key] = pred_metric_sum.get(action_key, 0.0) + float(
                    pred_row["selection_value"]
                )
                pred_metric_count[action_key] = pred_metric_count.get(action_key, 0) + 1

        winner_action_key = str(pred_metrics[0]["action_key"]) if pred_metrics else None
        if winner_action_key:
            winner_count[winner_action_key] = winner_count.get(winner_action_key, 0) + 1

    ranking_rows: list[dict[str, Any]] = []
    action_keys = sorted(
        set(val_metric_sum)
        | set(pred_metric_sum)
        | set(winner_count)
        | set(rows_seen)
    )
    for action_key in action_keys:
        val_n = int(val_metric_count.get(action_key, 0))
        pred_n = int(pred_metric_count.get(action_key, 0))
        ranking_rows.append(
            {
                "action_key": action_key,
                "winner_count": int(winner_count.get(action_key, 0)),
                "winner_rate": (
                    float(winner_count.get(action_key, 0) / steps_seen) if steps_seen else 0.0
                ),
                "validation_steps": val_n,
                "prediction_steps": pred_n,
                "mean_validation_metric": (
                    float(val_metric_sum[action_key] / val_n) if val_n else None
                ),
                "mean_prediction_metric": (
                    float(pred_metric_sum[action_key] / pred_n) if pred_n else None
                ),
                "rows_seen": int(rows_seen.get(action_key, 0)),
            }
        )

    ranking_rows = _sort_action_key_ranking_rows(
        ranking_rows,
        selection_direction=unit.selection_direction,
    )

    selected_action_keys: list[str] = []
    if ranking_rows:
        dominant_winner = str(ranking_rows[0]["action_key"])
        selected_action_keys.append(dominant_winner)
        near_winners = [
            r for r in ranking_rows if str(r["action_key"]) != dominant_winner
        ]
        near_winners = sorted(
            near_winners,
            key=lambda r: (
                (
                    float(r["mean_validation_metric"])
                    if r.get("mean_validation_metric") is not None
                    else (float("inf") if unit.selection_direction == "minimize" else float("-inf"))
                ),
                float(r["mean_prediction_metric"])
                if r.get("mean_prediction_metric") is not None
                else (float("inf") if unit.selection_direction == "minimize" else float("-inf")),
                str(r.get("action_key", "")),
            ),
            reverse=unit.selection_direction != "minimize",
        )
        selected_action_keys.extend(
            str(r["action_key"])
            for r in near_winners[: max(0, int(topk_action_keys_per_root) - 1)]
        )

    return {
        "selected_action_keys": selected_action_keys,
        "ranking_rows": ranking_rows,
        "steps_seen": int(steps_seen),
        "missing_steps": int(missing_steps),
        "selection_metric": str(unit.selection_metric),
        "selection_direction": str(unit.selection_direction),
    }


def _pick_best_combo_from_pred_payload(
    *,
    pred_payload: pl.DataFrame,
    combo_index: pl.DataFrame,
    allowed_combo_keys: set[tuple[int, int, int]] | None,
    selection_metric: str,
    selection_direction: str,
    n_classes: int,
    class_names: list[str],
) -> dict[str, Any] | None:
    rows = _list_combo_metrics_from_pred_payload(
        pred_payload=pred_payload,
        combo_index=combo_index,
        allowed_combo_keys=allowed_combo_keys,
        selection_metric=selection_metric,
        selection_direction=selection_direction,
        n_classes=n_classes,
        class_names=class_names,
    )
    return rows[0] if rows else None


def _build_unit_configs(
    *,
    project_root: Path,
    model_name: str,
    timeframes: list[str],
    targets_by_model: dict | None,
    n_classes_by_model: dict | None,
    class_names_by_model: dict | None,
    feature_source_by_model: dict | None,
    optuna_overrides_by_model: dict | None,
) -> list[_Step2UnitConfig]:
    target_map = (targets_by_model or {}).get(model_name, {}) if targets_by_model else {}
    n_classes_map = (n_classes_by_model or {}).get(model_name, {}) if n_classes_by_model else {}
    class_names_map = (class_names_by_model or {}).get(model_name, {}) if class_names_by_model else {}
    feature_source_map = (
        (feature_source_by_model or {}).get(model_name, {})
        if feature_source_by_model
        else {}
    )
    overrides_map = (
        (optuna_overrides_by_model or {}).get(model_name, {})
        if optuna_overrides_by_model
        else {}
    )

    units: list[_Step2UnitConfig] = []
    for tf in timeframes:
        if tf not in {"1m", "5m", "15m"}:
            raise ValueError(f"Unknown timeframe: {tf}")

        tf_targets = _normalize_target_list(target_map.get(tf), "target_4class")
        tf_overrides = overrides_map.get(tf, {})
        for target in tf_targets:
            # Build fresh objects per (tf, target) to avoid cross-target config bleed.
            cfg = BaseOptimizerConfig(project_root=project_root)
            win = WindowSearchSpace()
            model_space = ModelSearchSpace()
            ov = _resolve_overrides(tf, target, tf_overrides)
            if "exclude_tail_pct" in ov:
                cfg = replace(cfg, exclude_tail_pct=float(ov["exclude_tail_pct"]))
            if "features_dir_override" in ov:
                cfg = replace(
                    cfg,
                    features_dir_override=Path(ov["features_dir_override"]),
                )
            if "labels_dir_override" in ov:
                cfg = replace(
                    cfg,
                    labels_dir_override=Path(ov["labels_dir_override"]),
                )
            if "cb_base_params" in ov:
                merged = dict(cfg.cb_base_params)
                merged.update(dict(ov["cb_base_params"]))
                cfg = replace(cfg, cb_base_params=merged)
            if "window_space" in ov:
                win = replace(win, **dict(ov["window_space"]))
            if "model_space" in ov:
                model_space = replace(model_space, **dict(ov["model_space"]))

            n_classes = _resolve_n_classes(n_classes_map, tf, target, cfg.n_classes)
            class_names = _resolve_class_names(
                class_names_map, tf, target, n_classes, list(cfg.class_names)
            )
            feature_target = _resolve_feature_target(feature_source_map, tf, target)
            selection_metric = str(ov.get("optuna_metric", cfg.optuna_metric))
            selection_direction = "minimize" if selection_metric in {"log_loss", "cross_direction_error"} else "maximize"
            # Step-2 should follow the exact combos stored by Stage-1 artifacts.
            # We keep this unset intentionally to avoid filtering historical combo
            # payloads with today's config maps.
            allowed_combo_keys = None
            units.append(
                _Step2UnitConfig(
                    timeframe=tf,
                    target=str(target),
                    feature_target=str(feature_target),
                    n_classes=int(n_classes),
                    class_names=list(class_names),
                    exclude_tail_pct=float(cfg.exclude_tail_pct),
                    cb_base_params=dict(cfg.cb_base_params),
                    num_boost_round=int(max(10, model_space.num_boost_round_min)),
                    selection_metric=selection_metric,
                    selection_direction=selection_direction,
                    allowed_combo_keys=allowed_combo_keys,
                    features_dir=cfg.features_dir,
                    labels_dir=cfg.labels_dir,
                )
            )
    return units


def run_stage1_step2_feature_pruning(
    *,
    stage1_run_id_or_path: str | Path,
    project_root: str | Path | None = None,
    model_name: str = "catboost",
    timeframes: list[str] | None = None,
    targets_by_model: dict | None = None,
    n_classes_by_model: dict | None = None,
    class_names_by_model: dict | None = None,
    feature_source_by_model: dict | None = None,
    optuna_overrides_by_model: dict | None = None,
    max_steps_per_unit: int | None = None,
    feature_selector_method: str = "recursive_shap",
    selector_shap_calc_type: str = "Regular",
    selector_steps: int = 3,
    selector_keep_ratio: float = 0.7,
    selector_fold_vote_min_frac: float = 0.5,
    selector_step_vote_min_frac: float = 0.5,
    noisy_bottom_quantile: float = 0.25,
    noisy_presence_threshold: float = 0.90,
    min_features_keep: int = 24,
    feature_importance_type: str = "PredictionValuesChange",
    reward_cross_error_weight: float = 0.5,
    promotion_min_reward_delta: float = 0.0,
    promotion_max_cross_direction_error_delta: float = 0.01,
    promotion_min_macro_f1_delta: float = -0.005,
    output_subdir: str = "stage1_step2",
    combo_processing_mode: str = "winner_only",
    selection_scope: str | None = None,
    topk_action_keys_per_root: int = 3,
    progress_every_steps: int = 10,
    comparison_metric_mode: str = "reward",
    winner_metric: str = "accuracy",
    no_worse_accuracy_guard: bool = True,
    skip_prune_if_baseline_accuracy_ge: float = 1.0,
    enforce_step1_combo_alignment: bool = True,
    enforce_step1_fold_alignment: bool = True,
    debug_step_selection: bool = True,
    debug_combo_detail: bool = True,
    debug_artifact_paths: bool = True,
    debug_walkforward: bool = False,
    debug_walkforward_every_steps: int = 1,
    verbose: bool = True,
) -> dict[str, Any]:
    """
    Run Stage-1 Step-2 feature pruning and baseline-vs-filtered comparison.
    """
    project_root = (
        Path(project_root).expanduser().resolve()
        if project_root is not None
        else resolve_project_root(Path(__file__))
    )
    feature_selector_method = str(feature_selector_method).strip().lower()
    if feature_selector_method != "recursive_shap":
        raise ValueError(
            "feature_selector_method currently supports only 'recursive_shap'."
        )
    selector_steps = max(1, int(selector_steps))
    selector_keep_ratio = float(selector_keep_ratio)
    selector_fold_vote_min_frac = float(selector_fold_vote_min_frac)
    selector_step_vote_min_frac = float(selector_step_vote_min_frac)
    if not (0.0 < selector_keep_ratio <= 1.0):
        raise ValueError("selector_keep_ratio must be in (0, 1].")
    if not (0.0 < selector_fold_vote_min_frac <= 1.0):
        raise ValueError("selector_fold_vote_min_frac must be in (0, 1].")
    if not (0.0 < selector_step_vote_min_frac <= 1.0):
        raise ValueError("selector_step_vote_min_frac must be in (0, 1].")
    selector_shap_mode = _resolve_shap_calc_type(selector_shap_calc_type)

    if selection_scope is None:
        selection_scope = combo_processing_mode
    combo_processing_mode = str(selection_scope).strip().lower()
    if combo_processing_mode not in {"winner_only", "all_combos", "root_topk"}:
        raise ValueError(
            "selection_scope must be 'winner_only', 'all_combos' or 'root_topk'"
        )
    topk_action_keys_per_root = max(1, int(topk_action_keys_per_root))
    comparison_metric_mode = str(comparison_metric_mode).strip().lower()
    if comparison_metric_mode not in {"reward", "selection_metric", "accuracy"}:
        raise ValueError(
            "comparison_metric_mode must be 'reward', 'selection_metric' or 'accuracy'"
        )
    winner_metric = str(winner_metric).strip().lower()
    if winner_metric in {"", "selection_metric", "optuna_metric"}:
        winner_metric = "selection_metric"
    if winner_metric not in {"selection_metric", "accuracy", "macro_f1", "cross_direction_error"}:
        raise ValueError(
            "winner_metric must be one of: selection_metric, accuracy, macro_f1, cross_direction_error"
        )
    progress_every_steps = max(1, int(progress_every_steps))
    debug_walkforward_every_steps = max(1, int(debug_walkforward_every_steps))

    run_dir = _resolve_stage1_run_dir(stage1_run_id_or_path, project_root=project_root)
    if timeframes is None:
        timeframes = ["1m", "5m", "15m"]
    units = _build_unit_configs(
        project_root=project_root,
        model_name=model_name,
        timeframes=timeframes,
        targets_by_model=targets_by_model,
        n_classes_by_model=n_classes_by_model,
        class_names_by_model=class_names_by_model,
        feature_source_by_model=feature_source_by_model,
        optuna_overrides_by_model=optuna_overrides_by_model,
    )

    model_dir = run_dir / model_name
    if not model_dir.exists():
        raise FileNotFoundError(f"Model directory not found: {model_dir}")

    step2_root = run_dir / output_subdir / model_name
    step2_root.mkdir(parents=True, exist_ok=True)

    # Synchronize Step-2 over the same prediction-batch set across all units.
    # This keeps walk-forward continuity aligned with Stage-1 step coverage.
    unit_step_batches: dict[str, list[int]] = {}
    for unit in units:
        unit_key = f"{unit.timeframe}/{unit.target}"
        unit_dir = model_dir / unit.timeframe / unit.target
        if not unit_dir.exists():
            continue
        unit_step_dirs = sorted(
            [p for p in unit_dir.glob("batch_*") if p.is_dir()],
            key=lambda p: int(p.name.split("_")[1]),
        )
        if max_steps_per_unit is not None:
            unit_step_dirs = unit_step_dirs[-int(max_steps_per_unit) :]
        unit_step_batches[unit_key] = [int(p.name.split("_")[1]) for p in unit_step_dirs]

    common_step_batches: set[int] | None = None
    for batches in unit_step_batches.values():
        s = set(int(b) for b in batches)
        common_step_batches = s if common_step_batches is None else (common_step_batches & s)
    common_step_batches = common_step_batches or set()
    common_step_batches_sorted = sorted(common_step_batches)
    if verbose:
        print(
            "[Stage1-Step2] synchronized prediction batches across units: "
            f"{len(common_step_batches_sorted)} common steps"
        )
        if common_step_batches_sorted:
            print(
                "[Stage1-Step2] common step range: "
                f"{common_step_batches_sorted[0]}..{common_step_batches_sorted[-1]}"
            )

    def _process_unit_step(
        *,
        unit: _Step2UnitConfig,
        unit_key: str,
        step_dir: Path,
        step_idx: int,
        total_steps: int,
        state: dict[str, Any],
    ) -> None:
        process_stage1_selector_step(
            unit=unit,
            unit_key=unit_key,
            step_dir=step_dir,
            step_idx=step_idx,
            total_steps=total_steps,
            state=state,
            unit_scope_info=unit_scope_info.get(unit_key, {}),
            combo_processing_mode=combo_processing_mode,
            feature_selector_method=feature_selector_method,
            selector_shap_calc_type=selector_shap_calc_type,
            selector_steps=selector_steps,
            selector_keep_ratio=selector_keep_ratio,
            selector_fold_vote_min_frac=selector_fold_vote_min_frac,
            selector_step_vote_min_frac=selector_step_vote_min_frac,
            min_features_keep=min_features_keep,
            feature_importance_type=feature_importance_type,
            winner_metric=winner_metric,
            no_worse_accuracy_guard=no_worse_accuracy_guard,
            skip_prune_if_baseline_accuracy_ge=skip_prune_if_baseline_accuracy_ge,
            enforce_step1_combo_alignment=enforce_step1_combo_alignment,
            enforce_step1_fold_alignment=enforce_step1_fold_alignment,
            debug_step_selection=debug_step_selection,
            debug_combo_detail=debug_combo_detail,
            debug_walkforward=debug_walkforward,
            debug_walkforward_every_steps=debug_walkforward_every_steps,
            verbose=verbose,
        )
        return

        baseline_rows_by_combo = state["baseline_rows_by_combo"]
        step_fold_plan_by_combo = state["step_fold_plan_by_combo"]
        importance_rows_by_combo = state["importance_rows_by_combo"]
        selected_features_rows_by_combo = state["selected_features_rows_by_combo"]
        selector_fold_rows_by_combo = state["selector_fold_rows_by_combo"]
        filtered_rows_by_combo = state["filtered_rows_by_combo"]
        all_importance_rows = state["all_importance_rows"]
        combo_meta = state["combo_meta"]
        failed_steps = state["failed_steps"]
        step_winner_rows = state["step_winner_rows"]
        step_debug_rows = state["step_debug_rows"]
        combo_debug_rows = state["combo_debug_rows"]
        reason_counts = state["reason_counts"]
        unit_t0 = state["unit_t0"]

        try:
            pred_batch = int(step_dir.name.split("_")[1])
        except Exception:
            return
        stage1_dir = step_dir / "stage1"
        combo_path = stage1_dir / "stage1_combo_index.parquet"
        fold_path = stage1_dir / "stage1_fold_windows.parquet"
        val_path = stage1_dir / "stage1_val_predictions.parquet"
        pred_path = stage1_dir / "stage1_pred_batch_predictions.parquet"
        if not (
            combo_path.exists()
            and fold_path.exists()
            and val_path.exists()
            and pred_path.exists()
        ):
            failed_steps.append(
                {"pred_batch": pred_batch, "reason": "missing_stage1_artifacts"}
            )
            reason_counts["missing_stage1_artifacts"] = (
                reason_counts.get("missing_stage1_artifacts", 0) + 1
            )
            return

        combo_df = pl.read_parquet(combo_path)
        fold_df = pl.read_parquet(fold_path)
        val_df = pl.read_parquet(val_path)
        pred_df = pl.read_parquet(pred_path)
        step_summary_path = stage1_dir / "stage1_step_summary.json"
        step_summary: dict[str, Any] = {}
        if step_summary_path.exists():
            try:
                with open(step_summary_path, "r") as f:
                    step_summary = json.load(f)
            except Exception:
                step_summary = {}

        complete_combo_df = combo_df.filter(pl.col("status") == "complete")
        complete_combo_rows = complete_combo_df.to_dicts()
        complete_combo_keys = {_combo_key_from_row(r) for r in complete_combo_rows}
        expected_combo_keys: set[tuple[int, int, int]] | None = None
        triplet_grid = (
            step_summary.get("stage1_grid", {}).get("triplet_grid", [])
            if isinstance(step_summary, dict)
            else []
        )
        if isinstance(triplet_grid, list) and triplet_grid:
            parsed_keys = set()
            for c in triplet_grid:
                try:
                    parsed_keys.add(
                        (
                            int(c["fold_count"]),
                            int(c["val_batches_per_fold"]),
                            int(c["train_batches_per_fold"]),
                        )
                    )
                except Exception:
                    continue
            if parsed_keys:
                expected_combo_keys = parsed_keys

        effective_allowed_combo_keys = expected_combo_keys
        if effective_allowed_combo_keys is None:
            effective_allowed_combo_keys = unit.allowed_combo_keys
        elif unit.allowed_combo_keys:
            effective_allowed_combo_keys = set(effective_allowed_combo_keys).intersection(
                set(unit.allowed_combo_keys)
            )

        combo_missing_count = 0
        combo_extra_count = 0
        if expected_combo_keys is not None:
            combo_missing_count = int(
                len(set(expected_combo_keys).difference(complete_combo_keys))
            )
            combo_extra_count = int(
                len(set(complete_combo_keys).difference(expected_combo_keys))
            )
            if combo_missing_count > 0:
                reason_counts["missing_expected_combo_in_step_artifacts"] = (
                    reason_counts.get("missing_expected_combo_in_step_artifacts", 0)
                    + 1
                )
                if enforce_step1_combo_alignment:
                    failed_steps.append(
                        {
                            "pred_batch": pred_batch,
                            "reason": "missing_expected_combo_in_step_artifacts",
                            "missing_count": combo_missing_count,
                        }
                    )
                    if debug_step_selection and verbose:
                        print(
                            f"[Stage1-Step2][ALIGN] {unit_key} pred={pred_batch}: "
                            f"missing_expected_combo_count={combo_missing_count} "
                            "(skipping step)"
                        )
                    return

        step_winner_metric = (
            unit.selection_metric if winner_metric == "selection_metric" else winner_metric
        )
        step_winner_direction = _metric_direction(step_winner_metric)
        combo_metrics = _list_combo_metrics_from_pred_payload(
            pred_payload=pred_df,
            combo_index=combo_df,
            allowed_combo_keys=effective_allowed_combo_keys,
            selection_metric=step_winner_metric,
            selection_direction=step_winner_direction,
            n_classes=unit.n_classes,
            class_names=unit.class_names,
        )
        if not combo_metrics:
            failed_steps.append({"pred_batch": pred_batch, "reason": "no_valid_combo_for_step"})
            reason_counts["no_valid_combo_for_step"] = (
                reason_counts.get("no_valid_combo_for_step", 0) + 1
            )
            step_debug_rows.append(
                {
                    "pred_batch": int(pred_batch),
                    "status": "failed",
                    "reason": "no_valid_combo_for_step",
                    "combo_rows_total": int(len(combo_df)),
                    "combo_rows_complete": int(len(complete_combo_df)),
                    "pred_payload_rows": int(len(pred_df)),
                    "expected_combo_count": (
                        int(len(expected_combo_keys))
                        if expected_combo_keys is not None
                        else None
                    ),
                    "missing_expected_combo_count": int(combo_missing_count),
                    "extra_combo_count": int(combo_extra_count),
                }
            )
            return

        winner = combo_metrics[0]
        winner_action_key = _format_action_key(
            int(winner["fold_count"]),
            int(winner["val_batches_per_fold"]),
            int(winner["train_batches_per_fold"]),
        )
        step_winner_rows.append(
            {
                "pred_batch": int(pred_batch),
                "combo_id": int(winner["combo_id"]),
                "action_key": str(winner_action_key),
                "selection_metric": str(unit.selection_metric),
                "selection_direction": str(unit.selection_direction),
                "selection_value": float(winner["selection_value"]),
                "winner_metric": str(step_winner_metric),
                "winner_direction": str(step_winner_direction),
                "winner_metric_value": float(winner["selection_value"]),
                "accuracy": winner["accuracy"],
                "macro_f1": winner["macro_f1"],
                "cross_direction_error": winner["cross_direction_error"],
                "pred_rows": int(winner["pred_rows"]),
                "rank": 1,
            }
        )
        if debug_step_selection and verbose:
            print(
                f"[Stage1-Step2][STEP] {unit_key} step {step_idx}/{total_steps} "
                f"pred={pred_batch} combos_complete={len(complete_combo_df)} "
                f"winner={winner_action_key} "
                f"{step_winner_metric}={float(winner['selection_value']):.6f} "
                f"pred_rows={int(winner['pred_rows'])} "
                f"expected_missing={combo_missing_count} extra={combo_extra_count}"
            )

        pred_batch_df = load_batch(
            unit.features_dir,
            unit.labels_dir,
            unit.timeframe,
            pred_batch,
            target_col=unit.target,
            feature_target_col=unit.feature_target,
            exclude_tail_pct=unit.exclude_tail_pct,
        ).filter(pl.col(unit.target) >= 0)
        if len(pred_batch_df) < 5:
            failed_steps.append(
                {"pred_batch": pred_batch, "reason": "insufficient_pred_rows_for_step"}
            )
            reason_counts["insufficient_pred_rows_for_step"] = (
                reason_counts.get("insufficient_pred_rows_for_step", 0) + 1
            )
            return
        if verbose:
            print(f"\n  {unit_key}:")
            if "timestamp" in pred_batch_df.columns and len(pred_batch_df) > 0:
                ts_start = str(pred_batch_df["timestamp"][0])
                ts_end = str(pred_batch_df["timestamp"][-1])
                print(f"    Batch: {ts_start} → {ts_end}")
            print(
                f"    Winner: {winner_action_key} "
                f"({step_winner_metric}={float(winner['selection_value']):.6f})"
            )
            print(
                f"    Pred rows: {len(pred_batch_df)} | "
                f"expected_missing={combo_missing_count}, extra={combo_extra_count}"
            )
        state["processed_steps"] += 1
        combo_index_rows = {
            int(r["combo_id"]): r for r in combo_df.to_dicts()
        }
        step_debug_rows.append(
            {
                "pred_batch": int(pred_batch),
                "status": "ok",
                "reason": "processed",
                "combo_rows_total": int(len(combo_df)),
                "combo_rows_complete": int(len(complete_combo_df)),
                "pred_payload_rows": int(len(pred_df)),
                "expected_combo_count": (
                    int(len(expected_combo_keys))
                    if expected_combo_keys is not None
                    else None
                ),
                "missing_expected_combo_count": int(combo_missing_count),
                "extra_combo_count": int(combo_extra_count),
                "winner_combo_id": int(winner["combo_id"]),
                "winner_action_key": str(winner_action_key),
                "winner_selection_value": float(winner["selection_value"]),
                "winner_metric": str(step_winner_metric),
                "winner_direction": str(step_winner_direction),
                "winner_pred_rows": int(winner["pred_rows"]),
            }
        )
        train_df_cache: dict[tuple[int, int], pl.DataFrame] = {}
        val_df_cache: dict[tuple[int, int], pl.DataFrame] = {}
        selected_action_keys = set(
            unit_scope_info.get(unit_key, {}).get("selected_action_keys", [])
        )
        if combo_processing_mode == "winner_only":
            selected_rows = [winner]
        elif combo_processing_mode == "root_topk":
            selected_rows = [
                row for row in combo_metrics if str(row.get("action_key")) in selected_action_keys
            ]
        else:
            selected_rows = combo_metrics

        for selected in selected_rows:
            combo_id = int(selected["combo_id"])
            combo_row = combo_index_rows.get(combo_id, {})
            fold_rows_df = (
                fold_df.filter(pl.col("combo_id") == combo_id)
                .sort("fold_id")
            )
            if fold_rows_df.is_empty():
                failed_steps.append(
                    {
                        "pred_batch": pred_batch,
                        "combo_id": combo_id,
                        "reason": "no_fold_window_for_combo",
                    }
                )
                combo_debug_rows.append(
                    {
                        "pred_batch": int(pred_batch),
                        "combo_id": int(combo_id),
                        "combo_status": "failed",
                        "action_key": _format_action_key(
                            int(selected["fold_count"]),
                            int(selected["val_batches_per_fold"]),
                            int(selected["train_batches_per_fold"]),
                        ),
                        "reason": "no_fold_window_for_combo",
                    }
                )
                continue
            fold_rows = fold_rows_df.to_dicts()
            expected_fold_count = int(combo_row.get("fold_count", len(fold_rows)))
            actual_fold_ids = sorted(
                [int(fr.get("fold_id", -1)) for fr in fold_rows]
            )
            expected_fold_ids = list(range(1, expected_fold_count + 1))
            fold_alignment_ok = bool(
                len(fold_rows) == expected_fold_count
                and actual_fold_ids == expected_fold_ids
            )
            if not fold_alignment_ok:
                reason_counts["fold_window_alignment_mismatch"] = (
                    reason_counts.get("fold_window_alignment_mismatch", 0) + 1
                )
                combo_debug_rows.append(
                    {
                        "pred_batch": int(pred_batch),
                        "combo_id": int(combo_id),
                        "combo_status": "failed",
                        "action_key": _format_action_key(
                            int(selected["fold_count"]),
                            int(selected["val_batches_per_fold"]),
                            int(selected["train_batches_per_fold"]),
                        ),
                        "reason": "fold_window_alignment_mismatch",
                        "expected_fold_count": int(expected_fold_count),
                        "actual_fold_count": int(len(fold_rows)),
                        "expected_fold_ids": ",".join(str(x) for x in expected_fold_ids),
                        "actual_fold_ids": ",".join(str(x) for x in actual_fold_ids),
                    }
                )
                if debug_combo_detail and verbose:
                    print(
                        f"[Stage1-Step2][ALIGN] {unit_key} pred={pred_batch} "
                        f"combo_id={combo_id}: fold mismatch "
                        f"expected={expected_fold_ids} actual={actual_fold_ids}"
                    )
                if enforce_step1_fold_alignment:
                    failed_steps.append(
                        {
                            "pred_batch": pred_batch,
                            "combo_id": combo_id,
                            "reason": "fold_window_alignment_mismatch",
                        }
                    )
                    continue
            pred_fold = fold_rows[0]
            train_start = int(pred_fold["train_start_batch"])
            train_end = int(pred_fold["train_end_batch"])
            val_start = int(pred_fold["val_start_batch"])
            val_end = int(pred_fold["val_end_batch"])
            action_key = str(
                combo_row.get(
                    "action_key",
                    f"f{selected['fold_count']}_v{selected['val_batches_per_fold']}_t{selected['train_batches_per_fold']}",
                )
            )
            if debug_combo_detail and verbose:
                print(
                    f"[Stage1-Step2][COMBO] {unit_key} pred={pred_batch} "
                    f"action={action_key} mode={combo_processing_mode} "
                    f"sel={unit.selection_metric}:{float(selected['selection_value']):.6f} "
                    f"folds={len(fold_rows)} nearest_train={train_start}-{train_end} "
                    f"nearest_val={val_start}-{val_end}"
                )
            combo_meta.setdefault(
                combo_id,
                {
                    "combo_id": combo_id,
                    "action_key": action_key,
                    "fold_count": int(selected["fold_count"]),
                    "val_batches_per_fold": int(selected["val_batches_per_fold"]),
                    "train_batches_per_fold": int(selected["train_batches_per_fold"]),
                },
            )
            baseline_rows_by_combo.setdefault(combo_id, []).append(
                {
                    "pred_batch": pred_batch,
                    "combo_id": combo_id,
                    "action_key": action_key,
                    "fold_count": int(selected["fold_count"]),
                    "val_batches_per_fold": int(selected["val_batches_per_fold"]),
                    "train_batches_per_fold": int(selected["train_batches_per_fold"]),
                    "selection_metric": unit.selection_metric,
                    "selection_direction": unit.selection_direction,
                    "selection_value": float(selected["selection_value"]),
                    "baseline_accuracy": selected["accuracy"],
                    "baseline_macro_f1": selected["macro_f1"],
                    "baseline_cross_direction_error": selected["cross_direction_error"],
                    "baseline_pred_rows": int(selected["pred_rows"]),
                    "baseline_val_accuracy": None,
                    "baseline_val_macro_f1": None,
                    "baseline_val_cross_direction_error": None,
                    "baseline_val_rows": 0,
                    "train_start_batch": train_start,
                    "train_end_batch": train_end,
                    "val_start_batch": val_start,
                    "val_end_batch": val_end,
                }
            )
            if not val_df.is_empty():
                val_combo = val_df.filter(pl.col("combo_id") == int(combo_id))
                if "scope" in val_combo.columns:
                    val_combo = val_combo.filter(pl.col("scope") == "val_fold")
                if not val_combo.is_empty():
                    y_val_true = val_combo["y_true"].to_numpy().astype(np.int32, copy=False)
                    y_val_pred = val_combo["y_pred"].to_numpy().astype(np.int32, copy=False)
                    m_val = _compute_metrics(
                        y_val_true,
                        y_val_pred,
                        n_classes=unit.n_classes,
                        class_names=unit.class_names,
                    )
                    baseline_rows_by_combo[combo_id][-1]["baseline_val_accuracy"] = m_val["accuracy"]
                    baseline_rows_by_combo[combo_id][-1]["baseline_val_macro_f1"] = m_val["macro_f1"]
                    baseline_rows_by_combo[combo_id][-1]["baseline_val_cross_direction_error"] = (
                        m_val["cross_direction_error"]
                    )
                    baseline_rows_by_combo[combo_id][-1]["baseline_val_rows"] = int(len(y_val_true))
            state["selected_combo_rows"] += 1
            # Keep exact fold windows from Stage-1 for Step-2 replay.
            step_fold_plan_by_combo.setdefault(combo_id, []).append(
                {
                    "pred_batch": pred_batch,
                    "fold_windows": [
                        {
                            "fold_id": int(fw.get("fold_id", 0)),
                            "train_start_batch": int(fw["train_start_batch"]),
                            "train_end_batch": int(fw["train_end_batch"]),
                            "val_start_batch": int(fw["val_start_batch"]),
                            "val_end_batch": int(fw["val_end_batch"]),
                        }
                        for fw in fold_rows
                    ],
                }
            )
            if feature_selector_method == "recursive_shap":
                feat_cols: list[str] | None = None
                fold_ok = True
                fold_selected_feature_lists: list[list[str]] = []
                fold_importances: list[np.ndarray] = []
                selector_fold_rows = []

                for fold_w in fold_rows:
                    fold_id = int(fold_w.get("fold_id", 0))
                    fold_train_start = int(fold_w["train_start_batch"])
                    fold_train_end = int(fold_w["train_end_batch"])
                    fold_val_start = int(fold_w["val_start_batch"])
                    fold_val_end = int(fold_w["val_end_batch"])

                    train_batch_ids = _fold_batch_ids(
                        fold_w,
                        prefix="train",
                        start_batch=fold_train_start,
                        end_batch=fold_train_end,
                    )
                    val_batch_ids = _fold_batch_ids(
                        fold_w,
                        prefix="val",
                        start_batch=fold_val_start,
                        end_batch=fold_val_end,
                    )
                    leakage_ok = _fold_order_ok(fold_w, pred_batch=int(pred_batch))
                    if debug_walkforward and (
                        step_idx % debug_walkforward_every_steps == 0
                    ):
                        print(
                            f"[Stage1-Step2][WF] {unit_key} step {step_idx}/{total_steps} "
                            f"pred={pred_batch} combo={action_key} fold={fold_id} "
                            f"train={fold_train_start}-{fold_train_end} "
                            f"val={fold_val_start}-{fold_val_end} "
                            f"pred_rows={len(pred_batch_df)} leakage_guard="
                            f"{'pass' if leakage_ok else 'fail'}"
                        )
                    if not leakage_ok:
                        failed_steps.append(
                            {
                                "pred_batch": pred_batch,
                                "combo_id": combo_id,
                                "fold_id": fold_id,
                                "reason": "leakage_guard_fold_order_violation",
                            }
                        )
                        reason_counts["leakage_guard_fold_order_violation"] = (
                            reason_counts.get("leakage_guard_fold_order_violation", 0) + 1
                        )
                        fold_ok = False
                        break

                    train_key = tuple(train_batch_ids)
                    if train_key not in train_df_cache:
                        train_df_cache[train_key] = load_batches_by_ids(
                            unit.features_dir,
                            unit.labels_dir,
                            unit.timeframe,
                            train_batch_ids,
                            target_col=unit.target,
                            feature_target_col=unit.feature_target,
                            exclude_tail_pct=unit.exclude_tail_pct,
                        ).filter(pl.col(unit.target) >= 0)
                    train_df = train_df_cache[train_key]
                    if len(train_df) < 20:
                        failed_steps.append(
                            {
                                "pred_batch": pred_batch,
                                "combo_id": combo_id,
                                "fold_id": fold_id,
                                "reason": "insufficient_rows_for_training",
                            }
                        )
                        reason_counts["insufficient_rows_for_training"] = (
                            reason_counts.get("insufficient_rows_for_training", 0) + 1
                        )
                        fold_ok = False
                        break

                    val_key = tuple(val_batch_ids)
                    if val_key not in val_df_cache:
                        val_df_cache[val_key] = load_batches_by_ids(
                            unit.features_dir,
                            unit.labels_dir,
                            unit.timeframe,
                            val_batch_ids,
                            target_col=unit.target,
                            feature_target_col=unit.feature_target,
                            exclude_tail_pct=unit.exclude_tail_pct,
                        ).filter(pl.col(unit.target) >= 0)
                    fold_val_df = val_df_cache[val_key]
                    if len(fold_val_df) < 5:
                        failed_steps.append(
                            {
                                "pred_batch": pred_batch,
                                "combo_id": combo_id,
                                "fold_id": fold_id,
                                "reason": "insufficient_rows_for_eval_fold",
                            }
                        )
                        reason_counts["insufficient_rows_for_eval_fold"] = (
                            reason_counts.get("insufficient_rows_for_eval_fold", 0) + 1
                        )
                        fold_ok = False
                        break

                    fold_feat_cols = get_feature_columns(train_df, unit.target)
                    if len(fold_feat_cols) < 10:
                        failed_steps.append(
                            {
                                "pred_batch": pred_batch,
                                "combo_id": combo_id,
                                "fold_id": fold_id,
                                "reason": "too_few_features",
                            }
                        )
                        reason_counts["too_few_features"] = (
                            reason_counts.get("too_few_features", 0) + 1
                        )
                        fold_ok = False
                        break
                    if feat_cols is None:
                        feat_cols = list(fold_feat_cols)
                    elif list(fold_feat_cols) != feat_cols:
                        failed_steps.append(
                            {
                                "pred_batch": pred_batch,
                                "combo_id": combo_id,
                                "fold_id": fold_id,
                                "reason": "inconsistent_feature_columns_across_folds",
                            }
                        )
                        reason_counts["inconsistent_feature_columns_across_folds"] = (
                            reason_counts.get("inconsistent_feature_columns_across_folds", 0) + 1
                        )
                        fold_ok = False
                        break

                    X_train, y_train, _, _ = prepare_features_target(
                        train_df, feat_cols, unit.target
                    )
                    X_val, y_val, _, _ = prepare_features_target(
                        fold_val_df, feat_cols, unit.target
                    )
                    if len(np.unique(y_train)) < 2:
                        failed_steps.append(
                            {
                                "pred_batch": pred_batch,
                                "combo_id": combo_id,
                                "fold_id": fold_id,
                                "reason": "single_class_train",
                            }
                        )
                        reason_counts["single_class_train"] = (
                            reason_counts.get("single_class_train", 0) + 1
                        )
                        fold_ok = False
                        break

                    X_train_num = np.nan_to_num(X_train, nan=0.0, posinf=0.0, neginf=0.0)
                    X_val_num = np.nan_to_num(X_val, nan=0.0, posinf=0.0, neginf=0.0)
                    model = _fit_catboost_model(
                        X_train=X_train_num,
                        y_train=y_train.astype(np.int32),
                        X_eval=X_val_num,
                        y_eval=y_val.astype(np.int32),
                        cb_params=unit.cb_base_params,
                        iterations=unit.num_boost_round,
                    )
                    try:
                        fold_imp = np.asarray(
                            model.get_feature_importance(type=feature_importance_type),
                            dtype=np.float64,
                        ).reshape(-1)
                    except Exception:
                        fold_imp = np.asarray(
                            model.get_feature_importance(),
                            dtype=np.float64,
                        ).reshape(-1)
                    if fold_imp.shape[0] != len(feat_cols):
                        failed_steps.append(
                            {
                                "pred_batch": pred_batch,
                                "combo_id": combo_id,
                                "fold_id": fold_id,
                                "reason": "feature_importance_size_mismatch",
                            }
                        )
                        reason_counts["feature_importance_size_mismatch"] = (
                            reason_counts.get("feature_importance_size_mismatch", 0) + 1
                        )
                        fold_ok = False
                        break
                    fold_importances.append(fold_imp)

                    n_features_total = int(len(feat_cols))
                    n_features_select = int(
                        max(min_features_keep, round(float(selector_keep_ratio) * n_features_total))
                    )
                    n_features_select = min(n_features_select, n_features_total)
                    selector_result, selector_eval_mode = _select_features_with_fallback(
                        model,
                        X_train=X_train_num,
                        y_train=y_train,
                        X_val=X_val_num,
                        y_val=y_val,
                        n_features_total=n_features_total,
                        n_features_select=n_features_select,
                        selector_steps=selector_steps,
                        selector_shap_mode=selector_shap_mode,
                    )
                    fold_selected_features = _extract_selected_feature_names(
                        selector_result, feat_cols
                    )
                    fold_selected_feature_lists.append(list(fold_selected_features))
                    selector_fold_rows.append(
                        {
                            "pred_batch": int(pred_batch),
                            "combo_id": int(combo_id),
                            "action_key": str(action_key),
                            "fold_id": int(fold_id),
                            "n_features_total": int(n_features_total),
                            "n_selected_fold": int(len(fold_selected_features)),
                            "target_select_count": int(n_features_select),
                            "selected_features_fold": json.dumps(
                                [str(f) for f in fold_selected_features]
                            ),
                            "selector_method": "recursive_shap",
                            "selector_steps": int(selector_steps),
                            "selector_shap_calc_type": str(selector_shap_calc_type),
                            "selector_eval_mode": str(selector_eval_mode),
                        }
                    )
                    if debug_combo_detail and verbose:
                        print(
                            f"[Stage1-Step2][SELECTOR] {unit_key} pred={pred_batch} "
                            f"action={action_key} fold={fold_id} "
                            f"selected={len(fold_selected_features)}/{n_features_total} "
                            f"target={n_features_select}"
                        )

                if (not fold_ok) or feat_cols is None or (not fold_selected_feature_lists):
                    combo_debug_rows.append(
                        {
                            "pred_batch": int(pred_batch),
                            "combo_id": int(combo_id),
                            "combo_status": "failed",
                            "action_key": action_key,
                            "reason": "recursive_shap_selector_failed",
                            "folds_expected": int(expected_fold_count),
                            "folds_used_for_importance": int(len(fold_selected_feature_lists)),
                        }
                    )
                    continue

                selector_fold_rows_by_combo.setdefault(combo_id, []).extend(selector_fold_rows)
                vote_counts: dict[str, int] = {}
                for selected_fold in fold_selected_feature_lists:
                    for f_name in selected_fold:
                        vote_counts[str(f_name)] = vote_counts.get(str(f_name), 0) + 1
                n_fold_votes = int(len(fold_selected_feature_lists))
                min_fold_vote_threshold = int(
                    max(1, np.ceil(n_fold_votes * float(selector_fold_vote_min_frac)))
                )
                target_keep_count = int(
                    max(
                        min_features_keep,
                        round(float(selector_keep_ratio) * int(len(feat_cols))),
                    )
                )
                target_keep_count = int(min(target_keep_count, int(len(feat_cols))))
                mean_importances = np.mean(np.vstack(fold_importances), axis=0)
                imp_map = {
                    str(feat_cols[i]): float(mean_importances[i]) for i in range(len(feat_cols))
                }
                # Rank features by fold support first, then mean importance.
                ranked_features = sorted(
                    [str(f) for f in feat_cols],
                    key=lambda f: (int(vote_counts.get(str(f), 0)), imp_map.get(str(f), 0.0)),
                    reverse=True,
                )
                # Precise (slower) keep-count search: evaluate multiple candidate keep counts.
                ratio_grid = [0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95]
                candidate_keep_counts = sorted(
                    {
                        int(max(min_features_keep, min(len(feat_cols), round(len(feat_cols) * r))))
                        for r in ratio_grid
                    }
                    | {int(target_keep_count), int(min_features_keep), int(len(feat_cols))}
                )
                if debug_combo_detail and verbose:
                    print(
                        f"[Stage1-Step2][SEARCH] {unit_key} pred={pred_batch} action={action_key} "
                        f"candidate_keep_counts={candidate_keep_counts} "
                        f"target_keep={target_keep_count} n_features={len(feat_cols)}"
                    )

                best_candidate = None
                candidate_rows = []
                for keep_count in candidate_keep_counts:
                    candidate_features = ranked_features[: int(keep_count)]
                    filtered_val_true_parts: list[np.ndarray] = []
                    filtered_val_pred_parts: list[np.ndarray] = []
                    nearest_model = None
                    use_features_ref: list[str] | None = None
                    filtered_fold_ok = True
                    fail_reason = None
                    for fold_w in fold_rows:
                        fold_id = int(fold_w.get("fold_id", 0))
                        fold_train_start = int(fold_w["train_start_batch"])
                        fold_train_end = int(fold_w["train_end_batch"])
                        fold_val_start = int(fold_w["val_start_batch"])
                        fold_val_end = int(fold_w["val_end_batch"])

                        train_batch_ids = _fold_batch_ids(
                            fold_w,
                            prefix="train",
                            start_batch=fold_train_start,
                            end_batch=fold_train_end,
                        )
                        val_batch_ids = _fold_batch_ids(
                            fold_w,
                            prefix="val",
                            start_batch=fold_val_start,
                            end_batch=fold_val_end,
                        )
                        train_key = tuple(train_batch_ids)
                        train_df = train_df_cache.get(train_key)
                        if train_df is None:
                            filtered_fold_ok = False
                            fail_reason = "missing_train_cache"
                            break
                        val_key = tuple(val_batch_ids)
                        fold_val_df = val_df_cache.get(val_key)
                        if fold_val_df is None:
                            filtered_fold_ok = False
                            fail_reason = "missing_val_cache"
                            break
                        train_feature_set = set(get_feature_columns(train_df, unit.target))
                        use_features = [f for f in candidate_features if f in train_feature_set]
                        if len(use_features) < 5:
                            filtered_fold_ok = False
                            fail_reason = "too_few_features_after_selection"
                            break
                        if use_features_ref is None:
                            use_features_ref = list(use_features)

                        X_train, y_train, _, _ = prepare_features_target(
                            train_df, use_features, unit.target
                        )
                        X_val, y_val, _, _ = prepare_features_target(
                            fold_val_df, use_features, unit.target
                        )
                        if len(np.unique(y_train)) < 2:
                            filtered_fold_ok = False
                            fail_reason = "single_class_train_filtered"
                            break

                        X_train_num = np.nan_to_num(
                            X_train, nan=0.0, posinf=0.0, neginf=0.0
                        )
                        X_val_num = np.nan_to_num(X_val, nan=0.0, posinf=0.0, neginf=0.0)
                        model = _fit_catboost_model(
                            X_train=X_train_num,
                            y_train=y_train.astype(np.int32),
                            X_eval=X_val_num,
                            y_eval=y_val.astype(np.int32),
                            cb_params=unit.cb_base_params,
                            iterations=unit.num_boost_round,
                        )
                        if int(fold_id) == 1:
                            nearest_model = model
                        val_proba = model.predict_proba(X_val_num)
                        _, y_val_hat = _full_proba_and_pred(
                            proba_raw=val_proba,
                            classes=getattr(model, "classes_", None),
                            n_classes=unit.n_classes,
                        )
                        filtered_val_true_parts.append(y_val.astype(np.int32, copy=False))
                        filtered_val_pred_parts.append(y_val_hat.astype(np.int32, copy=False))

                    if (not filtered_fold_ok) or nearest_model is None or not use_features_ref:
                        candidate_rows.append(
                            {
                                "pred_batch": int(pred_batch),
                                "step_idx": int(step_idx),
                                "combo_id": int(combo_id),
                                "action_key": str(action_key),
                                "combo_status": "candidate_failed",
                                "candidate_keep_count": int(keep_count),
                                "reason": str(fail_reason or "filtered_replay_failed"),
                            }
                        )
                        continue

                    X_pred, y_pred_true, _, _ = prepare_features_target(
                        pred_batch_df, use_features_ref, unit.target
                    )
                    X_pred_num = np.nan_to_num(X_pred, nan=0.0, posinf=0.0, neginf=0.0)
                    pred_proba = nearest_model.predict_proba(X_pred_num)
                    _, y_pred_hat = _full_proba_and_pred(
                        proba_raw=pred_proba,
                        classes=getattr(nearest_model, "classes_", None),
                        n_classes=unit.n_classes,
                    )
                    pred_metrics = _compute_metrics(
                        y_pred_true.astype(np.int32),
                        y_pred_hat.astype(np.int32),
                        n_classes=unit.n_classes,
                        class_names=unit.class_names,
                    )
                    val_true_all = (
                        np.concatenate(filtered_val_true_parts)
                        if filtered_val_true_parts
                        else np.array([], dtype=np.int32)
                    )
                    val_pred_all = (
                        np.concatenate(filtered_val_pred_parts)
                        if filtered_val_pred_parts
                        else np.array([], dtype=np.int32)
                    )
                    val_metrics = _compute_metrics(
                        val_true_all,
                        val_pred_all,
                        n_classes=unit.n_classes,
                        class_names=unit.class_names,
                    )

                    candidate = {
                        "keep_count": int(keep_count),
                        "use_features_ref": list(use_features_ref),
                        "pred_metrics": pred_metrics,
                        "val_metrics": val_metrics,
                    }
                    candidate_rows.append(
                        {
                            "pred_batch": int(pred_batch),
                            "step_idx": int(step_idx),
                            "combo_id": int(combo_id),
                            "action_key": str(action_key),
                            "combo_status": "candidate_ok",
                            "candidate_keep_count": int(keep_count),
                            "candidate_pred_accuracy": float(
                                pred_metrics.get("accuracy", 0.0) or 0.0
                            ),
                            "candidate_pred_macro_f1": float(
                                pred_metrics.get("macro_f1", 0.0) or 0.0
                            ),
                            "candidate_pred_cross_direction_error": float(
                                pred_metrics.get("cross_direction_error", 1.0) or 1.0
                            ),
                            "candidate_val_accuracy": float(
                                val_metrics.get("accuracy", 0.0) or 0.0
                            ),
                        }
                    )
                    if debug_combo_detail and verbose:
                        print(
                            f"[Stage1-Step2][CAND] {unit_key} pred={pred_batch} action={action_key} "
                            f"keep={int(keep_count)} "
                            f"pred_acc={pred_metrics.get('accuracy')} "
                            f"pred_f1={pred_metrics.get('macro_f1')} "
                            f"pred_xerr={pred_metrics.get('cross_direction_error')}"
                        )
                    cand_key = (
                        float(pred_metrics.get("accuracy", 0.0) or 0.0),
                        float(pred_metrics.get("macro_f1", 0.0) or 0.0),
                        -float(pred_metrics.get("cross_direction_error", 1.0) or 1.0),
                        -abs(int(keep_count) - int(target_keep_count)),
                    )
                    if best_candidate is None or cand_key > best_candidate["key"]:
                        best_candidate = {"key": cand_key, "payload": candidate}

                combo_debug_rows.extend(candidate_rows)
                if best_candidate is None:
                    if debug_step_selection and verbose:
                        print(
                            f"[Stage1-Step2][COMPARE] {unit_key} step {step_idx}/{total_steps} "
                            f"pred={pred_batch} action={action_key} "
                            "baseline_acc=NA filtered_acc=NA improved=False "
                            "apply_pruned=False reason=filtered_replay_failed_all_candidates"
                        )
                    combo_debug_rows.append(
                        {
                            "pred_batch": int(pred_batch),
                            "combo_id": int(combo_id),
                            "combo_status": "failed",
                            "action_key": action_key,
                            "reason": "filtered_replay_failed_all_candidates",
                            "folds_expected": int(expected_fold_count),
                            "candidate_keep_counts": json.dumps(
                                [int(k) for k in candidate_keep_counts]
                            ),
                        }
                    )
                    continue

                chosen = best_candidate["payload"]
                step_keep_features = list(chosen["use_features_ref"])
                step_keep_set = set(step_keep_features)
                step_drop_features = [
                    str(f_name) for f_name in feat_cols if str(f_name) not in step_keep_set
                ]
                fold_vote_threshold = int(
                    min((int(vote_counts.get(f, 0)) for f in step_keep_features), default=0)
                )
                if debug_combo_detail and verbose:
                    print(
                        f"[Stage1-Step2][VOTE] {unit_key} pred={pred_batch} action={action_key} "
                        f"selected_keep={len(step_keep_features)} removed={len(step_drop_features)} "
                        f"target_keep={target_keep_count} chosen_keep_count={chosen['keep_count']}"
                    )

                step_imp_rows: list[dict] = []
                for idx, f_name in enumerate(feat_cols):
                    fname = str(f_name)
                    vote = int(vote_counts.get(fname, 0))
                    vote_frac = float(vote / max(1, len(fold_selected_feature_lists)))
                    imp = float(mean_importances[idx])
                    step_imp_rows.append(
                        {
                            "pred_batch": int(pred_batch),
                            "step_idx": int(step_idx),
                            "combo_id": int(combo_id),
                            "action_key": str(action_key),
                            "feature": fname,
                            "importance": imp,
                            "fold_vote_count": vote,
                            "fold_vote_frac": vote_frac,
                            "is_selected_step": bool(fname in step_keep_set),
                            "selection_source": "recursive_shap_fold_vote",
                            "baseline_accuracy_step": None,
                            "filtered_accuracy_step": None,
                            "delta_accuracy_step": None,
                            "improved_step": None,
                            "apply_pruned_step": None,
                        }
                    )

                pred_metrics = chosen["pred_metrics"]
                val_metrics = chosen["val_metrics"]
                baseline_acc_step = (
                    float(selected["accuracy"]) if selected.get("accuracy") is not None else None
                )
                filtered_acc_step = (
                    float(pred_metrics["accuracy"]) if pred_metrics.get("accuracy") is not None else None
                )
                improved_step = bool(
                    baseline_acc_step is not None
                    and filtered_acc_step is not None
                    and filtered_acc_step > baseline_acc_step
                )
                apply_pruned_step = bool(improved_step)
                prune_guard_reason = None
                if (
                    baseline_acc_step is not None
                    and baseline_acc_step >= float(skip_prune_if_baseline_accuracy_ge)
                ):
                    apply_pruned_step = False
                    prune_guard_reason = "baseline_accuracy_at_or_above_threshold"
                elif (
                    bool(no_worse_accuracy_guard)
                    and baseline_acc_step is not None
                    and filtered_acc_step is not None
                    and filtered_acc_step <= baseline_acc_step
                ):
                    apply_pruned_step = False
                    prune_guard_reason = "filtered_accuracy_not_better_than_baseline"

                filtered_rows_by_combo.setdefault(combo_id, []).append(
                    {
                        "pred_batch": int(pred_batch),
                        "combo_id": int(combo_id),
                        "action_key": str(action_key),
                        "filtered_accuracy": pred_metrics["accuracy"],
                        "filtered_macro_f1": pred_metrics["macro_f1"],
                        "filtered_cross_direction_error": pred_metrics["cross_direction_error"],
                        "filtered_pred_rows": int(len(pred_batch_df)),
                        "filtered_val_accuracy": val_metrics["accuracy"],
                        "filtered_val_macro_f1": val_metrics["macro_f1"],
                        "filtered_val_cross_direction_error": val_metrics["cross_direction_error"],
                        "filtered_val_rows": None,
                        "n_features_used": int(len(step_keep_features)),
                        "selected_keep_count_request": int(chosen["keep_count"]),
                        "folds_used_for_filtered_eval": int(len(fold_rows)),
                        "baseline_accuracy_step": baseline_acc_step,
                        "filtered_accuracy_step": filtered_acc_step,
                        "delta_accuracy_step": (
                            float(filtered_acc_step - baseline_acc_step)
                            if baseline_acc_step is not None and filtered_acc_step is not None
                            else None
                        ),
                        "improved_step": bool(improved_step),
                        "apply_pruned_step": bool(apply_pruned_step),
                        "prune_guard_reason": prune_guard_reason,
                    }
                )
                for r in step_imp_rows:
                    r["baseline_accuracy_step"] = baseline_acc_step
                    r["filtered_accuracy_step"] = filtered_acc_step
                    r["delta_accuracy_step"] = (
                        float(filtered_acc_step - baseline_acc_step)
                        if baseline_acc_step is not None and filtered_acc_step is not None
                        else None
                    )
                    r["improved_step"] = bool(improved_step)
                    r["apply_pruned_step"] = bool(apply_pruned_step)
                    importance_rows_by_combo.setdefault(combo_id, []).append(dict(r))
                    selected_features_rows_by_combo.setdefault(combo_id, []).append(dict(r))
                    all_importance_rows.append(dict(r))
                if debug_step_selection and verbose:
                    print(
                        f"[Stage1-Step2][COMPARE] {unit_key} step {step_idx}/{total_steps} "
                        f"pred={pred_batch} action={action_key} "
                        f"baseline_acc={baseline_acc_step} filtered_acc={filtered_acc_step} "
                        f"improved={improved_step} apply_pruned={apply_pruned_step} "
                        f"keep={len(step_keep_features)}"
                    )
                combo_debug_rows.append(
                    {
                        "pred_batch": int(pred_batch),
                        "step_idx": int(step_idx),
                        "combo_id": int(combo_id),
                        "combo_status": "ok",
                        "action_key": action_key,
                        "reason": "recursive_shap_step_processed",
                        "folds_expected": int(expected_fold_count),
                        "folds_used_for_importance": int(len(fold_selected_feature_lists)),
                        "features_total": int(len(feat_cols)),
                        "features_kept_step": int(len(step_keep_features)),
                        "features_removed_step": int(len(step_drop_features)),
                        "selector_method": "recursive_shap",
                        "selector_steps": int(selector_steps),
                        "selector_shap_calc_type": str(selector_shap_calc_type),
                        "fold_vote_threshold": int(fold_vote_threshold),
                        "min_fold_vote_threshold_cfg": int(min_fold_vote_threshold),
                        "target_keep_count": int(target_keep_count),
                        "chosen_keep_count": int(chosen["keep_count"]),
                        "candidate_keep_counts": json.dumps(
                            [int(k) for k in candidate_keep_counts]
                        ),
                    }
                )
                continue

            feat_cols: list[str] | None = None
            fold_importances: list[np.ndarray] = []
            fold_ok = True
            for fold_w in fold_rows:
                fold_id = int(fold_w.get("fold_id", 0))
                fold_train_start = int(fold_w["train_start_batch"])
                fold_train_end = int(fold_w["train_end_batch"])
                fold_val_start = int(fold_w["val_start_batch"])
                fold_val_end = int(fold_w["val_end_batch"])

                train_batch_ids = _fold_batch_ids(
                    fold_w,
                    prefix="train",
                    start_batch=fold_train_start,
                    end_batch=fold_train_end,
                )
                val_batch_ids = _fold_batch_ids(
                    fold_w,
                    prefix="val",
                    start_batch=fold_val_start,
                    end_batch=fold_val_end,
                )
                leakage_ok = _fold_order_ok(fold_w, pred_batch=int(pred_batch))
                if debug_walkforward and (
                    step_idx % debug_walkforward_every_steps == 0
                ):
                    print(
                        f"[Stage1-Step2][WF] {unit_key} step {step_idx}/{total_steps} "
                        f"pred={pred_batch} combo={action_key} fold={fold_id} "
                        f"train={fold_train_start}-{fold_train_end} "
                        f"val={fold_val_start}-{fold_val_end} "
                        f"pred_rows={len(pred_batch_df)} leakage_guard="
                        f"{'pass' if leakage_ok else 'fail'}"
                    )
                if not leakage_ok:
                    failed_steps.append(
                        {
                            "pred_batch": pred_batch,
                            "combo_id": combo_id,
                            "fold_id": fold_id,
                            "reason": "leakage_guard_fold_order_violation",
                        }
                    )
                    reason_counts["leakage_guard_fold_order_violation"] = (
                        reason_counts.get("leakage_guard_fold_order_violation", 0) + 1
                    )
                    fold_ok = False
                    break

                train_key = tuple(train_batch_ids)
                if train_key not in train_df_cache:
                    train_df_cache[train_key] = load_batches_by_ids(
                        unit.features_dir,
                        unit.labels_dir,
                        unit.timeframe,
                        train_batch_ids,
                        target_col=unit.target,
                        feature_target_col=unit.feature_target,
                        exclude_tail_pct=unit.exclude_tail_pct,
                    ).filter(pl.col(unit.target) >= 0)
                train_df = train_df_cache[train_key]
                if len(train_df) < 20:
                    failed_steps.append(
                        {
                            "pred_batch": pred_batch,
                            "combo_id": combo_id,
                            "fold_id": fold_id,
                            "reason": "insufficient_rows_for_training",
                        }
                    )
                    reason_counts["insufficient_rows_for_training"] = (
                        reason_counts.get("insufficient_rows_for_training", 0) + 1
                    )
                    fold_ok = False
                    break

                val_key = tuple(val_batch_ids)
                if val_key not in val_df_cache:
                    val_df_cache[val_key] = load_batches_by_ids(
                        unit.features_dir,
                        unit.labels_dir,
                        unit.timeframe,
                        val_batch_ids,
                        target_col=unit.target,
                        feature_target_col=unit.feature_target,
                        exclude_tail_pct=unit.exclude_tail_pct,
                    ).filter(pl.col(unit.target) >= 0)
                val_df = val_df_cache[val_key]
                if len(val_df) < 5:
                    failed_steps.append(
                        {
                            "pred_batch": pred_batch,
                            "combo_id": combo_id,
                            "fold_id": fold_id,
                            "reason": "insufficient_rows_for_eval_fold",
                        }
                    )
                    reason_counts["insufficient_rows_for_eval_fold"] = (
                        reason_counts.get("insufficient_rows_for_eval_fold", 0) + 1
                    )
                    fold_ok = False
                    break

                fold_feat_cols = get_feature_columns(train_df, unit.target)
                if len(fold_feat_cols) < 10:
                    failed_steps.append(
                        {
                            "pred_batch": pred_batch,
                            "combo_id": combo_id,
                            "fold_id": fold_id,
                            "reason": "too_few_features",
                        }
                    )
                    reason_counts["too_few_features"] = (
                        reason_counts.get("too_few_features", 0) + 1
                    )
                    fold_ok = False
                    break
                if feat_cols is None:
                    feat_cols = list(fold_feat_cols)
                elif list(fold_feat_cols) != feat_cols:
                    failed_steps.append(
                        {
                            "pred_batch": pred_batch,
                            "combo_id": combo_id,
                            "fold_id": fold_id,
                            "reason": "inconsistent_feature_columns_across_folds",
                        }
                    )
                    reason_counts["inconsistent_feature_columns_across_folds"] = (
                        reason_counts.get("inconsistent_feature_columns_across_folds", 0) + 1
                    )
                    fold_ok = False
                    break

                X_train, y_train, _, _ = prepare_features_target(
                    train_df, feat_cols, unit.target
                )
                X_val, y_val, _, _ = prepare_features_target(
                    val_df, feat_cols, unit.target
                )
                if len(np.unique(y_train)) < 2:
                    failed_steps.append(
                        {
                            "pred_batch": pred_batch,
                            "combo_id": combo_id,
                            "fold_id": fold_id,
                            "reason": "single_class_train",
                        }
                    )
                    reason_counts["single_class_train"] = (
                        reason_counts.get("single_class_train", 0) + 1
                    )
                    fold_ok = False
                    break

                model = _fit_catboost_model(
                    X_train=np.nan_to_num(X_train, nan=0.0, posinf=0.0, neginf=0.0),
                    y_train=y_train.astype(np.int32),
                    X_eval=np.nan_to_num(X_val, nan=0.0, posinf=0.0, neginf=0.0),
                    y_eval=y_val.astype(np.int32),
                    cb_params=unit.cb_base_params,
                    iterations=unit.num_boost_round,
                )
                try:
                    fold_imp = np.asarray(
                        model.get_feature_importance(type=feature_importance_type),
                        dtype=np.float64,
                    ).reshape(-1)
                except Exception:
                    fold_imp = np.asarray(
                        model.get_feature_importance(),
                        dtype=np.float64,
                    ).reshape(-1)
                if fold_imp.shape[0] != len(feat_cols):
                    failed_steps.append(
                        {
                            "pred_batch": pred_batch,
                            "combo_id": combo_id,
                            "fold_id": fold_id,
                            "reason": "feature_importance_size_mismatch",
                        }
                    )
                    reason_counts["feature_importance_size_mismatch"] = (
                        reason_counts.get("feature_importance_size_mismatch", 0) + 1
                    )
                    fold_ok = False
                    break
                fold_importances.append(fold_imp)

            if not fold_ok or feat_cols is None:
                combo_debug_rows.append(
                    {
                        "pred_batch": int(pred_batch),
                        "combo_id": int(combo_id),
                        "combo_status": "failed",
                        "action_key": action_key,
                        "reason": "fold_training_failed_or_no_features",
                        "folds_expected": int(expected_fold_count),
                        "folds_used_for_importance": int(len(fold_importances)),
                    }
                )
                continue
            if not fold_importances:
                failed_steps.append(
                    {
                        "pred_batch": pred_batch,
                        "combo_id": combo_id,
                        "reason": "no_valid_folds_for_importance",
                    }
                )
                reason_counts["no_valid_folds_for_importance"] = (
                    reason_counts.get("no_valid_folds_for_importance", 0) + 1
                )
                combo_debug_rows.append(
                    {
                        "pred_batch": int(pred_batch),
                        "combo_id": int(combo_id),
                        "combo_status": "failed",
                        "action_key": action_key,
                        "reason": "no_valid_folds_for_importance",
                        "folds_expected": int(expected_fold_count),
                    }
                )
                continue

            importances = np.mean(np.vstack(fold_importances), axis=0)
            q = float(np.quantile(importances, float(noisy_bottom_quantile)))
            # Step-level selected features for this combo/step.
            step_drop_features = {
                str(f_name)
                for f_name, imp in zip(feat_cols, importances)
                if float(imp) <= q
            }
            step_keep_features = [
                str(f_name) for f_name in feat_cols if str(f_name) not in step_drop_features
            ]
            if len(step_keep_features) < int(min_features_keep):
                ranked_idx = np.argsort(importances)[::-1]
                top_idx = ranked_idx[: int(max(1, min_features_keep))]
                forced_keep = {str(feat_cols[int(i)]) for i in top_idx}
                step_keep_features = [
                    str(f_name) for f_name in feat_cols if str(f_name) in forced_keep
                ]
                step_drop_features = {
                    str(f_name) for f_name in feat_cols if str(f_name) not in forced_keep
                }
            step_keep_set = set(step_keep_features)

            combo_importance_rows = []
            for f_name, imp in zip(feat_cols, importances):
                fname = str(f_name)
                row = {
                    "pred_batch": int(pred_batch),
                        "combo_id": int(combo_id),
                        "action_key": action_key,
                        "feature": fname,
                        "importance": float(imp),
                        "is_noisy_step": bool(float(imp) <= q),
                        "folds_used_for_importance": int(len(fold_importances)),
                    }
                combo_importance_rows.append(row)
                all_importance_rows.append(row)
                selected_features_rows_by_combo.setdefault(combo_id, []).append(
                    {
                        "pred_batch": int(pred_batch),
                        "combo_id": int(combo_id),
                        "action_key": action_key,
                        "feature": fname,
                        "importance": float(imp),
                        "step_noisy_threshold": float(q),
                        "folds_used_for_importance": int(len(fold_importances)),
                        "is_selected_step": bool(fname in step_keep_set),
                    }
                )
            importance_rows_by_combo.setdefault(combo_id, []).extend(
                combo_importance_rows
            )
            combo_debug_rows.append(
                {
                    "pred_batch": int(pred_batch),
                    "combo_id": int(combo_id),
                    "combo_status": "ok",
                    "action_key": action_key,
                    "reason": "importance_collected",
                    "folds_expected": int(expected_fold_count),
                    "folds_used_for_importance": int(len(fold_importances)),
                    "features_total": int(len(feat_cols)),
                    "features_kept_step": int(len(step_keep_features)),
                    "features_removed_step": int(len(step_drop_features)),
                    "step_noisy_threshold": float(q),
                }
            )

        if verbose and (
            step_idx % progress_every_steps == 0 or step_idx == total_steps
        ):
            elapsed = float(time.perf_counter() - unit_t0)
            done = int(state["processed_steps"])
            total = int(state["total_steps"])
            eta = (elapsed / done * (total - done)) if done > 0 else 0.0
            print(
                f"[Stage1-Step2] {unit_key}: {done}/{total} steps, "
                f"processed={done}, winners={len(step_winner_rows)}, "
                f"combo_rows={state['selected_combo_rows']}, failed={len(failed_steps)}, "
                f"elapsed={elapsed/60:.1f}m, eta={eta/60:.1f}m"
            )
            if debug_step_selection and reason_counts:
                top_reasons = sorted(
                    reason_counts.items(), key=lambda kv: kv[1], reverse=True
                )[:3]
                print(
                    f"[Stage1-Step2] {unit_key}: top_fail_reasons="
                    + ", ".join(f"{k}:{v}" for k, v in top_reasons)
                )

    unit_summaries: dict[str, Any] = {}
    global_rows: list[dict[str, Any]] = []
    unit_states: dict[str, dict[str, Any]] = {}
    unit_step_dirs: dict[str, dict[int, Path]] = {}
    unit_scope_info: dict[str, dict[str, Any]] = {}
    ordered_units: list[_Step2UnitConfig] = []

    for unit in units:
        unit_key = f"{unit.timeframe}/{unit.target}"
        unit_dir = model_dir / unit.timeframe / unit.target
        if not unit_dir.exists():
            if verbose:
                print(f"[Stage1-Step2] {unit_key}: no stage1 unit directory, skipping")
            continue

        step_dirs = sorted(
            [p for p in unit_dir.glob("batch_*") if p.is_dir()],
            key=lambda p: int(p.name.split("_")[1]),
        )
        if max_steps_per_unit is not None:
            step_dirs = step_dirs[-int(max_steps_per_unit) :]
        if common_step_batches_sorted:
            step_dirs = [
                p for p in step_dirs if int(p.name.split("_")[1]) in common_step_batches
            ]
        if not step_dirs:
            continue

        step_dir_map = {int(p.name.split("_")[1]): p for p in step_dirs}
        unit_step_dirs[unit_key] = step_dir_map
        unit_states[unit_key] = _init_step2_unit_state(
            len(common_step_batches_sorted) if common_step_batches_sorted else len(step_dirs)
        )
        scope_info = {
            "selected_action_keys": [],
            "ranking_rows": [],
            "steps_seen": 0,
            "missing_steps": 0,
            "selection_metric": str(unit.selection_metric),
            "selection_direction": str(unit.selection_direction),
        }
        if combo_processing_mode == "root_topk":
            scope_info = _select_root_topk_action_keys(
                step_dirs=step_dirs,
                unit=unit,
                topk_action_keys_per_root=topk_action_keys_per_root,
            )
        unit_scope_info[unit_key] = scope_info
        ordered_units.append(unit)

        if verbose:
            print(
                f"[Stage1-Step2] {unit_key}: scanning {len(step_dirs)} steps "
                f"(progress_every_steps={progress_every_steps}, "
                f"mode={combo_processing_mode}, metric={comparison_metric_mode})"
            )
            print(
                f"[Stage1-Step2] {unit_key}: enforce_combo_alignment="
                f"{bool(enforce_step1_combo_alignment)}, "
                f"enforce_fold_alignment={bool(enforce_step1_fold_alignment)}, "
                f"feature_target={unit.feature_target}, "
                f"iterations={unit.num_boost_round}, "
                f"exclude_tail_pct={unit.exclude_tail_pct}, "
                f"winner_metric={winner_metric}"
            )
            first_pred = int(step_dirs[0].name.split("_")[1])
            last_pred = int(step_dirs[-1].name.split("_")[1])
            print(
                f"[Stage1-Step2] {unit_key}: step_batches={first_pred}..{last_pred} "
                f"(n={len(step_dirs)})"
            )
            if combo_processing_mode == "root_topk":
                print(
                    f"[Stage1-Step2] {unit_key}: root_topk selected_action_keys="
                    f"{scope_info.get('selected_action_keys', [])}"
                )

    if not ordered_units:
        return {"unit_summaries": {}, "artifacts": {}}

    step_batches = (
        list(common_step_batches_sorted)
        if common_step_batches_sorted
        else sorted({b for m in unit_step_dirs.values() for b in m.keys()})
    )
    total_steps = len(step_batches)

    for step_idx, pred_batch in enumerate(step_batches, start=1):
        if verbose:
            print("\n" + "#" * 80)
            print(
                f"#  STEP {step_idx}/{total_steps} | "
                f"Train batches 1-{int(pred_batch) - 1} → Predict batch {int(pred_batch)}"
            )
            print("#" * 80)
        for unit in ordered_units:
            unit_key = f"{unit.timeframe}/{unit.target}"
            step_dir = unit_step_dirs.get(unit_key, {}).get(int(pred_batch))
            if step_dir is None:
                continue
            _process_unit_step(
                unit=unit,
                unit_key=unit_key,
                step_dir=step_dir,
                step_idx=step_idx,
                total_steps=total_steps,
                state=unit_states[unit_key],
            )

    for unit in ordered_units:
        unit_key = f"{unit.timeframe}/{unit.target}"
        state = unit_states.get(unit_key, {})
        baseline_rows_by_combo = state.get("baseline_rows_by_combo", {})
        step_fold_plan_by_combo = state.get("step_fold_plan_by_combo", {})
        importance_rows_by_combo = state.get("importance_rows_by_combo", {})
        selected_features_rows_by_combo = state.get("selected_features_rows_by_combo", {})
        selector_fold_rows_by_combo = state.get("selector_fold_rows_by_combo", {})
        filtered_rows_by_combo = state.get("filtered_rows_by_combo", {})
        all_importance_rows = state.get("all_importance_rows", [])
        combo_meta = state.get("combo_meta", {})
        failed_steps = state.get("failed_steps", [])
        step_winner_rows = state.get("step_winner_rows", [])
        step_debug_rows = state.get("step_debug_rows", [])
        combo_debug_rows = state.get("combo_debug_rows", [])
        processed_steps = int(state.get("processed_steps", 0))
        selected_combo_rows = int(state.get("selected_combo_rows", 0))
        reason_counts = state.get("reason_counts", {})
        unit_t0 = float(state.get("unit_t0", time.perf_counter()))
        step_dirs = [
            unit_step_dirs[unit_key][b]
            for b in sorted(unit_step_dirs.get(unit_key, {}).keys())
        ]

        if not baseline_rows_by_combo:
            unit_summaries[unit_key] = {
                "unit": unit_key,
                "steps_seen": int(len(step_dirs)),
                "status": "insufficient_data",
                "combo_processing_mode": combo_processing_mode,
                "selection_scope": combo_processing_mode,
                "selected_action_keys": unit_scope_info.get(unit_key, {}).get(
                    "selected_action_keys", []
                ),
                "failed_steps": failed_steps[:20],
            }
            continue

        out_unit_dir = step2_root / unit.timeframe / unit.target
        out_unit_dir.mkdir(parents=True, exist_ok=True)
        combo_summaries: dict[str, Any] = {}
        winner_df = pl.DataFrame(step_winner_rows) if step_winner_rows else pl.DataFrame()
        winner_path = out_unit_dir / "step2_step_winners.parquet"
        if not winner_df.is_empty():
            winner_df.sort("pred_batch").write_parquet(winner_path)
        step_debug_df = _rows_to_debug_df(step_debug_rows)
        step_debug_path = out_unit_dir / "step2_step_debug.parquet"
        if not step_debug_df.is_empty():
            step_debug_df.sort("pred_batch").write_parquet(step_debug_path)
        combo_debug_df = _rows_to_debug_df(combo_debug_rows)
        combo_debug_path = out_unit_dir / "step2_combo_debug.parquet"
        if not combo_debug_df.is_empty():
            combo_debug_df.sort(["pred_batch", "combo_id"]).write_parquet(combo_debug_path)
        winner_counts: dict[str, int] = {}
        if not winner_df.is_empty():
            winner_counts_df = (
                winner_df.group_by("action_key")
                .agg(pl.len().alias("wins"))
                .sort("wins", descending=True)
            )
            winner_counts = {
                str(r["action_key"]): int(r["wins"])
                for r in winner_counts_df.to_dicts()
            }

        for combo_id in sorted(baseline_rows_by_combo):
            baseline_df = pl.DataFrame(baseline_rows_by_combo.get(combo_id, []))
            importance_df = pl.DataFrame(importance_rows_by_combo.get(combo_id, []))
            selected_step_df = pl.DataFrame(
                selected_features_rows_by_combo.get(combo_id, [])
            )
            selector_fold_df = pl.DataFrame(
                selector_fold_rows_by_combo.get(combo_id, [])
            )
            filtered_df = pl.DataFrame(filtered_rows_by_combo.get(combo_id, []))
            meta = combo_meta.get(combo_id, {"combo_id": combo_id})
            action_key = str(meta.get("action_key", f"combo_{combo_id}"))
            combo_dir = out_unit_dir / "combos" / action_key
            combo_dir.mkdir(parents=True, exist_ok=True)

            if baseline_df.is_empty() or importance_df.is_empty():
                combo_summary = {
                    "combo_id": int(combo_id),
                    "action_key": action_key,
                    "status": "insufficient_data",
                    "combo_processing_mode": combo_processing_mode,
                    "steps_used_for_baseline": int(len(baseline_df)),
                    "failed_steps_sample": failed_steps[:20],
                }
                combo_summaries[action_key] = combo_summary
                continue

            if feature_selector_method == "recursive_shap":
                selected_source_df = selected_step_df
                if (
                    "apply_pruned_step" in selected_step_df.columns
                    and len(
                        selected_step_df.filter(
                            pl.col("apply_pruned_step") == True  # noqa: E712
                        )
                    )
                    > 0
                ):
                    selected_source_df = selected_step_df.filter(
                        pl.col("apply_pruned_step") == True  # noqa: E712
                    )
                feat_summary = (
                    selected_source_df.group_by("feature")
                    .agg(
                        [
                            pl.len().alias("n_step_records"),
                            pl.col("importance").mean().alias("mean_importance"),
                            pl.col("importance").median().alias("median_importance"),
                            pl.col("is_selected_step").mean().alias("selected_step_freq"),
                        ]
                    )
                    .with_columns(
                        (
                            pl.col("selected_step_freq")
                            >= float(selector_step_vote_min_frac)
                        ).alias("keep_candidate")
                    )
                    .sort(["keep_candidate", "mean_importance"], descending=[True, True])
                )
                all_features = (
                    feat_summary.sort("mean_importance", descending=True)["feature"].to_list()
                    if not feat_summary.is_empty()
                    else []
                )
                keep_features = (
                    feat_summary.filter(pl.col("keep_candidate"))["feature"].to_list()
                    if not feat_summary.is_empty()
                    else []
                )
                if len(keep_features) < int(min_features_keep):
                    keep_features = all_features[: int(max(1, min_features_keep))]
                drop_features = [f for f in all_features if f not in set(keep_features)]
            else:
                feat_summary = (
                    importance_df.group_by("feature")
                    .agg(
                        [
                            pl.len().alias("n_step_records"),
                            pl.col("importance").mean().alias("mean_importance"),
                            pl.col("importance").median().alias("median_importance"),
                            pl.col("is_noisy_step").mean().alias("noisy_step_freq"),
                        ]
                    )
                    .with_columns(
                        (pl.col("noisy_step_freq") >= float(noisy_presence_threshold)).alias(
                            "drop_candidate"
                        )
                    )
                    .sort(["drop_candidate", "mean_importance"], descending=[True, False])
                )
                all_features = (
                    feat_summary.sort("mean_importance", descending=True)["feature"].to_list()
                )
                drop_features = (
                    feat_summary.filter(pl.col("drop_candidate"))["feature"].to_list()
                )
                keep_features = [f for f in all_features if f not in set(drop_features)]
                if len(keep_features) < int(min_features_keep):
                    keep_features = all_features[: int(max(1, min_features_keep))]
                    drop_features = [f for f in all_features if f not in set(keep_features)]

            if filtered_df.is_empty():
                filtered_df = pl.DataFrame()
            merged = baseline_df.join(filtered_df, on=["pred_batch", "combo_id", "action_key"], how="left")
            if (
                "baseline_macro_f1" in merged.columns
                and "baseline_cross_direction_error" in merged.columns
            ):
                merged = merged.with_columns(
                    (
                        pl.col("baseline_macro_f1")
                        - pl.lit(float(reward_cross_error_weight))
                        * pl.col("baseline_cross_direction_error")
                    ).alias("baseline_reward")
                )
            if (
                "filtered_macro_f1" in merged.columns
                and "filtered_cross_direction_error" in merged.columns
            ):
                merged = merged.with_columns(
                    (
                        pl.col("filtered_macro_f1")
                        - pl.lit(float(reward_cross_error_weight))
                        * pl.col("filtered_cross_direction_error")
                    ).alias("filtered_reward")
                )

            baseline_accuracy_mean = (
                float(merged["baseline_accuracy"].drop_nulls().mean())
                if "baseline_accuracy" in merged.columns
                and merged["baseline_accuracy"].drop_nulls().len() > 0
                else None
            )
            filtered_accuracy_mean = (
                float(merged["filtered_accuracy"].drop_nulls().mean())
                if "filtered_accuracy" in merged.columns
                and merged["filtered_accuracy"].drop_nulls().len() > 0
                else None
            )
            baseline_val_accuracy_mean = (
                float(merged["baseline_val_accuracy"].drop_nulls().mean())
                if "baseline_val_accuracy" in merged.columns
                and merged["baseline_val_accuracy"].drop_nulls().len() > 0
                else None
            )
            filtered_val_accuracy_mean = (
                float(merged["filtered_val_accuracy"].drop_nulls().mean())
                if "filtered_val_accuracy" in merged.columns
                and merged["filtered_val_accuracy"].drop_nulls().len() > 0
                else None
            )
            baseline_macro_f1_mean = (
                float(merged["baseline_macro_f1"].drop_nulls().mean())
                if "baseline_macro_f1" in merged.columns
                and merged["baseline_macro_f1"].drop_nulls().len() > 0
                else None
            )
            filtered_macro_f1_mean = (
                float(merged["filtered_macro_f1"].drop_nulls().mean())
                if "filtered_macro_f1" in merged.columns
                and merged["filtered_macro_f1"].drop_nulls().len() > 0
                else None
            )
            baseline_cross_err_mean = (
                float(merged["baseline_cross_direction_error"].drop_nulls().mean())
                if "baseline_cross_direction_error" in merged.columns
                and merged["baseline_cross_direction_error"].drop_nulls().len() > 0
                else None
            )
            filtered_cross_err_mean = (
                float(merged["filtered_cross_direction_error"].drop_nulls().mean())
                if "filtered_cross_direction_error" in merged.columns
                and merged["filtered_cross_direction_error"].drop_nulls().len() > 0
                else None
            )
            baseline_reward_mean = (
                float(merged["baseline_reward"].drop_nulls().mean())
                if "baseline_reward" in merged.columns
                and merged["baseline_reward"].drop_nulls().len() > 0
                else None
            )
            filtered_reward_mean = (
                float(merged["filtered_reward"].drop_nulls().mean())
                if "filtered_reward" in merged.columns
                and merged["filtered_reward"].drop_nulls().len() > 0
                else None
            )
            reward_delta = (
                (filtered_reward_mean - baseline_reward_mean)
                if baseline_reward_mean is not None and filtered_reward_mean is not None
                else None
            )
            macro_f1_delta = (
                (filtered_macro_f1_mean - baseline_macro_f1_mean)
                if baseline_macro_f1_mean is not None and filtered_macro_f1_mean is not None
                else None
            )
            cross_err_delta = (
                (filtered_cross_err_mean - baseline_cross_err_mean)
                if baseline_cross_err_mean is not None and filtered_cross_err_mean is not None
                else None
            )
            # Accuracy guard: keep all features if baseline is already perfect or
            # if filtered model is not strictly better on prediction-batch accuracy.
            apply_pruned_features = True
            prune_guard_reason = None
            if (
                baseline_accuracy_mean is not None
                and baseline_accuracy_mean >= float(skip_prune_if_baseline_accuracy_ge)
            ):
                apply_pruned_features = False
                prune_guard_reason = "baseline_accuracy_at_or_above_threshold"
            elif (
                bool(no_worse_accuracy_guard)
                and baseline_accuracy_mean is not None
                and filtered_accuracy_mean is not None
                and filtered_accuracy_mean <= baseline_accuracy_mean
            ):
                apply_pruned_features = False
                prune_guard_reason = "filtered_accuracy_not_better_than_baseline"
            if not apply_pruned_features:
                keep_features = list(all_features)
                drop_features = []

            comparison_metric_name = (
                "reward"
                if comparison_metric_mode == "reward"
                else str(unit.selection_metric)
            )
            baseline_metric_mean = None
            filtered_metric_mean = None
            delta = None
            if comparison_metric_mode == "accuracy":
                comparison_metric_name = "accuracy"
                baseline_metric_mean = baseline_accuracy_mean
                filtered_metric_mean = filtered_accuracy_mean
                delta = (
                    (filtered_metric_mean - baseline_metric_mean)
                    if baseline_metric_mean is not None and filtered_metric_mean is not None
                    else None
                )
                improved = (delta is not None) and (delta > 0)
            elif comparison_metric_mode == "reward":
                baseline_metric_mean = baseline_reward_mean
                filtered_metric_mean = filtered_reward_mean
                delta = reward_delta
                improved = (
                    (delta is not None) and (delta > 0)
                )
            else:
                baseline_metric_col = (
                    "baseline_cross_direction_error"
                    if unit.selection_metric == "cross_direction_error"
                    else "baseline_macro_f1"
                )
                filtered_metric_col = (
                    "filtered_cross_direction_error"
                    if unit.selection_metric == "cross_direction_error"
                    else "filtered_macro_f1"
                )
                baseline_metric_mean = (
                    float(merged[baseline_metric_col].drop_nulls().mean())
                    if baseline_metric_col in merged.columns
                    and merged[baseline_metric_col].drop_nulls().len() > 0
                    else None
                )
                filtered_metric_mean = (
                    float(merged[filtered_metric_col].drop_nulls().mean())
                    if filtered_metric_col in merged.columns
                    and merged[filtered_metric_col].drop_nulls().len() > 0
                    else None
                )
                delta = (
                    (filtered_metric_mean - baseline_metric_mean)
                    if (baseline_metric_mean is not None and filtered_metric_mean is not None)
                    else None
                )
                improved = (
                    (delta is not None)
                    and (
                        (delta < 0)
                        if unit.selection_metric == "cross_direction_error"
                        else (delta > 0)
                    )
                )
            gate_pass = True
            gate_reasons: list[str] = []
            if comparison_metric_mode == "accuracy":
                if baseline_accuracy_mean is None or filtered_accuracy_mean is None:
                    gate_pass = False
                    gate_reasons.append("missing_accuracy_for_comparison")
                elif filtered_accuracy_mean <= baseline_accuracy_mean:
                    gate_pass = False
                    gate_reasons.append("filtered_accuracy_not_better_than_baseline")
                if prune_guard_reason is not None:
                    gate_pass = False
                    gate_reasons.append(prune_guard_reason)
            else:
                if reward_delta is None or reward_delta < float(promotion_min_reward_delta):
                    gate_pass = False
                    gate_reasons.append("reward_delta_below_threshold")
                if macro_f1_delta is None or macro_f1_delta < float(promotion_min_macro_f1_delta):
                    gate_pass = False
                    gate_reasons.append("macro_f1_delta_below_threshold")
                if cross_err_delta is None or cross_err_delta > float(promotion_max_cross_direction_error_delta):
                    gate_pass = False
                    gate_reasons.append("cross_direction_error_delta_above_threshold")

            baseline_path = combo_dir / "step2_baseline_steps.parquet"
            importance_path = combo_dir / "step2_feature_importance_steps.parquet"
            selected_step_path = combo_dir / "step2_selected_features_per_step.parquet"
            selector_fold_path = combo_dir / "step2_selector_fold_outputs.parquet"
            feat_summary_path = combo_dir / "step2_feature_selection_summary.parquet"
            filtered_path = combo_dir / "step2_filtered_steps.parquet"
            compare_path = combo_dir / "step2_baseline_vs_filtered.parquet"
            mask_path = combo_dir / "step2_feature_mask.json"
            summary_path = combo_dir / "step2_summary.json"
            baseline_df.write_parquet(baseline_path)
            importance_df.write_parquet(importance_path)
            if not selector_fold_df.is_empty():
                selector_fold_df.sort(["pred_batch", "fold_id"]).write_parquet(selector_fold_path)
            else:
                pl.DataFrame(
                    {
                        "pred_batch": [],
                        "combo_id": [],
                        "action_key": [],
                        "fold_id": [],
                        "n_features_total": [],
                        "n_selected_fold": [],
                        "target_select_count": [],
                        "selected_features_fold": [],
                        "selector_method": [],
                        "selector_steps": [],
                        "selector_shap_calc_type": [],
                    }
                ).write_parquet(selector_fold_path)
            if not selected_step_df.is_empty():
                selected_step_df.sort(["pred_batch", "feature"]).write_parquet(selected_step_path)
            else:
                pl.DataFrame(
                    {
                        "pred_batch": [],
                        "step_idx": [],
                        "combo_id": [],
                        "action_key": [],
                        "feature": [],
                        "importance": [],
                        "fold_vote_count": [],
                        "fold_vote_frac": [],
                        "is_selected_step": [],
                        "selection_source": [],
                        "baseline_accuracy_step": [],
                        "filtered_accuracy_step": [],
                        "delta_accuracy_step": [],
                        "improved_step": [],
                        "apply_pruned_step": [],
                    }
                ).write_parquet(selected_step_path)
            feat_summary.write_parquet(feat_summary_path)
            filtered_df.write_parquet(filtered_path)
            merged.write_parquet(compare_path)
            feature_mask = {
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "timeframe": unit.timeframe,
                "target": unit.target,
                "feature_target": unit.feature_target,
                "combo_id": int(combo_id),
                "action_key": action_key,
                "fold_count": int(meta.get("fold_count", -1)),
                "val_batches_per_fold": int(meta.get("val_batches_per_fold", -1)),
                "train_batches_per_fold": int(meta.get("train_batches_per_fold", -1)),
                "selection_metric": unit.selection_metric,
                "feature_importance_type": str(feature_importance_type),
                "feature_selector_method": str(feature_selector_method),
                "selector_steps": int(selector_steps),
                "selector_shap_calc_type": str(selector_shap_calc_type),
                "selector_keep_ratio": float(selector_keep_ratio),
                "selector_fold_vote_min_frac": float(selector_fold_vote_min_frac),
                "selector_step_vote_min_frac": float(selector_step_vote_min_frac),
                "comparison_metric_mode": comparison_metric_mode,
                "comparison_metric_name": comparison_metric_name,
                "noisy_bottom_quantile": float(noisy_bottom_quantile),
                "noisy_presence_threshold": float(noisy_presence_threshold),
                "min_features_keep": int(min_features_keep),
                "n_features_total": int(len(all_features)),
                "n_features_removed": int(len(drop_features)),
                "n_features_kept": int(len(keep_features)),
                "kept_features": [str(f) for f in keep_features],
                "removed_features": [str(f) for f in drop_features],
            }
            with open(mask_path, "w") as f:
                json.dump(feature_mask, f, indent=2)

            combo_summary = {
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "run_id": run_dir.name,
                "model_name": model_name,
                "timeframe": unit.timeframe,
                "target": unit.target,
                "combo_id": int(combo_id),
                "action_key": action_key,
                "selection_metric": unit.selection_metric,
                "selection_direction": unit.selection_direction,
                "comparison_metric_mode": comparison_metric_mode,
                "comparison_metric_name": comparison_metric_name,
                "combo_processing_mode": combo_processing_mode,
                "steps_seen": int(len(step_dirs)),
                "steps_used_for_baseline": int(len(baseline_df)),
                "steps_used_for_filtered_eval": int(len(filtered_df)),
                "noisy_bottom_quantile": float(noisy_bottom_quantile),
                "noisy_presence_threshold": float(noisy_presence_threshold),
                "min_features_keep": int(min_features_keep),
                "feature_importance_type": str(feature_importance_type),
                "feature_selector_method": str(feature_selector_method),
                "selector_steps": int(selector_steps),
                "selector_shap_calc_type": str(selector_shap_calc_type),
                "selector_keep_ratio": float(selector_keep_ratio),
                "selector_fold_vote_min_frac": float(selector_fold_vote_min_frac),
                "selector_step_vote_min_frac": float(selector_step_vote_min_frac),
                "n_features_total": int(len(all_features)),
                "n_features_removed": int(len(drop_features)),
                "n_features_kept": int(len(keep_features)),
                "removed_features": [str(f) for f in drop_features],
                "kept_features": [str(f) for f in keep_features],
                "baseline_metric_mean": baseline_metric_mean,
                "filtered_metric_mean": filtered_metric_mean,
                "metric_delta_filtered_minus_baseline": delta,
                "comparison_metric_improved": bool(improved),
                "baseline_accuracy_mean": baseline_accuracy_mean,
                "filtered_accuracy_mean": filtered_accuracy_mean,
                "baseline_val_accuracy_mean": baseline_val_accuracy_mean,
                "filtered_val_accuracy_mean": filtered_val_accuracy_mean,
                "baseline_macro_f1_mean": baseline_macro_f1_mean,
                "filtered_macro_f1_mean": filtered_macro_f1_mean,
                "baseline_cross_direction_error_mean": baseline_cross_err_mean,
                "filtered_cross_direction_error_mean": filtered_cross_err_mean,
                "baseline_reward_mean": baseline_reward_mean,
                "filtered_reward_mean": filtered_reward_mean,
                "reward_cross_error_weight": float(reward_cross_error_weight),
                "reward_delta_filtered_minus_baseline": reward_delta,
                "macro_f1_delta_filtered_minus_baseline": macro_f1_delta,
                "cross_direction_error_delta_filtered_minus_baseline": cross_err_delta,
                "apply_pruned_features": bool(apply_pruned_features),
                "prune_guard_reason": prune_guard_reason,
                "promotion_gate": {
                    "pass": bool(gate_pass),
                    "reasons": gate_reasons,
                    "thresholds": {
                        "promotion_min_reward_delta": float(promotion_min_reward_delta),
                        "promotion_min_macro_f1_delta": float(promotion_min_macro_f1_delta),
                        "promotion_max_cross_direction_error_delta": float(
                            promotion_max_cross_direction_error_delta
                        ),
                    },
                },
                "failed_steps_sample": failed_steps[:20],
                "artifacts": {
                    "baseline_steps": str(baseline_path),
                    "feature_importance_steps": str(importance_path),
                    "selector_fold_outputs": str(selector_fold_path),
                    "selected_features_per_step": str(selected_step_path),
                    "feature_selection_summary": str(feat_summary_path),
                    "filtered_steps": str(filtered_path),
                    "baseline_vs_filtered": str(compare_path),
                    "feature_mask": str(mask_path),
                },
            }
            with open(summary_path, "w") as f:
                json.dump(combo_summary, f, indent=2)
            combo_summaries[action_key] = combo_summary
            global_rows.append(
                {
                    "unit": unit_key,
                    "timeframe": unit.timeframe,
                    "target": unit.target,
                    "combo_id": int(combo_id),
                    "action_key": action_key,
                    "selection_metric": unit.selection_metric,
                    "selection_direction": unit.selection_direction,
                    "comparison_metric_mode": comparison_metric_mode,
                    "comparison_metric_name": comparison_metric_name,
                    "baseline_metric_mean": baseline_metric_mean,
                    "filtered_metric_mean": filtered_metric_mean,
                    "metric_delta_filtered_minus_baseline": delta,
                    "comparison_metric_improved": bool(improved),
                    "baseline_accuracy_mean": baseline_accuracy_mean,
                    "filtered_accuracy_mean": filtered_accuracy_mean,
                    "baseline_val_accuracy_mean": baseline_val_accuracy_mean,
                    "filtered_val_accuracy_mean": filtered_val_accuracy_mean,
                    "baseline_reward_mean": baseline_reward_mean,
                    "filtered_reward_mean": filtered_reward_mean,
                    "reward_delta_filtered_minus_baseline": reward_delta,
                    "promotion_gate_pass": bool(gate_pass),
                    "apply_pruned_features": bool(apply_pruned_features),
                    "prune_guard_reason": prune_guard_reason,
                    "steps_used_for_baseline": int(len(baseline_df)),
                    "steps_used_for_filtered_eval": int(len(filtered_df)),
                    "n_features_removed": int(len(drop_features)),
                    "n_features_kept": int(len(keep_features)),
                }
            )
            if verbose:
                print(
                    f"[Stage1-Step2] {unit_key}/{action_key}: "
                    f"{comparison_metric_name} baseline={baseline_metric_mean}, "
                    f"filtered={filtered_metric_mean}, delta={delta}, "
                    f"improved={bool(improved)}, "
                    f"baseline_acc={baseline_accuracy_mean}, "
                    f"filtered_acc={filtered_accuracy_mean}, "
                    f"apply_pruned={bool(apply_pruned_features)}, "
                    f"removed={len(drop_features)}, kept={len(keep_features)}"
                )
                if debug_artifact_paths:
                    print(
                        f"[Stage1-Step2][PATHS] {unit_key}/{action_key}: "
                        f"dir={combo_dir}, "
                        f"baseline={baseline_path.name}, "
                        f"importance={importance_path.name}, "
                        f"selected_step={selected_step_path.name}, "
                        f"mask={mask_path.name}"
                    )

        # Global feature mask across all combos for this timeframe/target unit.
        global_feature_mask = None
        unit_importance_df = pl.DataFrame(all_importance_rows) if all_importance_rows else pl.DataFrame()
        unit_feature_stability_df = pl.DataFrame()
        unit_feature_noise_df = pl.DataFrame()
        top_features_by_combo_df = pl.DataFrame()
        if all_importance_rows:
            if feature_selector_method == "recursive_shap":
                unit_feat_summary = (
                    unit_importance_df.group_by("feature")
                    .agg(
                        [
                            pl.len().alias("n_step_records"),
                            pl.col("importance").mean().alias("mean_importance"),
                            pl.col("importance").median().alias("median_importance"),
                            pl.col("is_selected_step").mean().alias("selected_step_freq"),
                        ]
                    )
                    .with_columns(
                        (
                            pl.col("selected_step_freq")
                            >= float(selector_step_vote_min_frac)
                        ).alias("keep_candidate")
                    )
                    .sort(["keep_candidate", "mean_importance"], descending=[True, True])
                )
                unit_all_features = (
                    unit_feat_summary.sort("mean_importance", descending=True)["feature"].to_list()
                )
                unit_keep_features = (
                    unit_feat_summary.filter(pl.col("keep_candidate"))["feature"].to_list()
                )
                if len(unit_keep_features) < int(min_features_keep):
                    unit_keep_features = unit_all_features[: int(max(1, min_features_keep))]
                unit_drop_features = [
                    f for f in unit_all_features if f not in set(unit_keep_features)
                ]
            else:
                unit_feat_summary = (
                    unit_importance_df.group_by("feature")
                    .agg(
                        [
                            pl.len().alias("n_step_records"),
                            pl.col("importance").mean().alias("mean_importance"),
                            pl.col("importance").median().alias("median_importance"),
                            pl.col("is_noisy_step").mean().alias("noisy_step_freq"),
                        ]
                    )
                    .with_columns(
                        (pl.col("noisy_step_freq") >= float(noisy_presence_threshold)).alias(
                            "drop_candidate"
                        )
                    )
                    .sort(["drop_candidate", "mean_importance"], descending=[True, False])
                )
                unit_all_features = (
                    unit_feat_summary.sort("mean_importance", descending=True)["feature"].to_list()
                )
                unit_drop_features = (
                    unit_feat_summary.filter(pl.col("drop_candidate"))["feature"].to_list()
                )
                unit_keep_features = [
                    f for f in unit_all_features if f not in set(unit_drop_features)
                ]
                if len(unit_keep_features) < int(min_features_keep):
                    unit_keep_features = unit_all_features[: int(max(1, min_features_keep))]
                    unit_drop_features = [
                        f for f in unit_all_features if f not in set(unit_keep_features)
                    ]
            global_imp_path = out_unit_dir / "step2_feature_importance_global.parquet"
            global_noise_path = out_unit_dir / "step2_feature_selection_summary_global.parquet"
            global_mask_path = out_unit_dir / "step2_feature_mask_global.json"
            unit_importance_df.write_parquet(global_imp_path)
            unit_feat_summary.write_parquet(global_noise_path)
            global_feature_mask = {
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "timeframe": unit.timeframe,
                "target": unit.target,
                "feature_target": unit.feature_target,
                "scope": "global_across_combos",
                "selection_metric": unit.selection_metric,
                "feature_importance_type": str(feature_importance_type),
                "feature_selector_method": str(feature_selector_method),
                "selector_steps": int(selector_steps),
                "selector_shap_calc_type": str(selector_shap_calc_type),
                "selector_keep_ratio": float(selector_keep_ratio),
                "selector_fold_vote_min_frac": float(selector_fold_vote_min_frac),
                "selector_step_vote_min_frac": float(selector_step_vote_min_frac),
                "noisy_bottom_quantile": float(noisy_bottom_quantile),
                "noisy_presence_threshold": float(noisy_presence_threshold),
                "min_features_keep": int(min_features_keep),
                "n_features_total": int(len(unit_all_features)),
                "n_features_removed": int(len(unit_drop_features)),
                "n_features_kept": int(len(unit_keep_features)),
                "kept_features": [str(f) for f in unit_keep_features],
                "removed_features": [str(f) for f in unit_drop_features],
                "artifacts": {
                    "feature_importance_global": str(global_imp_path),
                    "feature_selection_summary_global": str(global_noise_path),
                },
            }
            with open(global_mask_path, "w") as f:
                json.dump(global_feature_mask, f, indent=2)
            global_feature_mask["artifacts"]["feature_mask_global"] = str(global_mask_path)

            stability_aggs = [
                pl.len().alias("n_step_records"),
                pl.col("pred_batch").n_unique().alias("step_count"),
                pl.col("action_key").n_unique().alias("action_key_count"),
                pl.col("importance").mean().alias("mean_importance"),
                pl.col("importance").median().alias("median_importance"),
                pl.col("importance").std(ddof=1).alias("std_importance"),
            ]
            if "is_selected_step" in unit_importance_df.columns:
                stability_aggs.append(
                    pl.col("is_selected_step").mean().alias("selected_step_freq")
                )
            if "is_noisy_step" in unit_importance_df.columns:
                stability_aggs.append(
                    pl.col("is_noisy_step").mean().alias("noisy_step_freq")
                )
            unit_feature_stability_df = (
                unit_importance_df.group_by("feature")
                .agg(stability_aggs)
                .with_columns(
                    pl.when(
                        pl.col("std_importance").is_not_null()
                        & (pl.col("mean_importance").abs() > 1e-12)
                    )
                    .then(pl.col("std_importance") / pl.col("mean_importance").abs())
                    .otherwise(None)
                    .alias("importance_cv")
                )
                .sort("mean_importance", descending=True)
            )

            noise_aggs = [
                pl.len().alias("n_step_records"),
                pl.col("importance").mean().alias("mean_importance"),
                pl.col("importance").median().alias("median_importance"),
                pl.col("action_key").n_unique().alias("action_key_count"),
            ]
            if "is_selected_step" in unit_importance_df.columns:
                noise_aggs.append(
                    pl.col("is_selected_step").mean().alias("selected_step_freq")
                )
            if "is_noisy_step" in unit_importance_df.columns:
                noise_aggs.append(
                    pl.col("is_noisy_step").mean().alias("noisy_step_freq")
                )
            unit_feature_noise_df = (
                unit_importance_df.group_by("feature")
                .agg(noise_aggs)
                .sort("mean_importance", descending=True)
            )

            top_features_by_combo_df = (
                unit_importance_df.group_by(["action_key", "feature"])
                .agg(
                    [
                        pl.len().alias("n_step_records"),
                        pl.col("importance").mean().alias("mean_importance"),
                        pl.col("importance").median().alias("median_importance"),
                        pl.col("pred_batch").n_unique().alias("step_count"),
                        pl.col("is_selected_step").mean().alias("selected_step_freq")
                        if "is_selected_step" in unit_importance_df.columns
                        else pl.lit(None).alias("selected_step_freq"),
                    ]
                )
                .sort(["action_key", "mean_importance"], descending=[False, True])
                .with_columns(
                    pl.int_range(0, pl.len()).over("action_key").alias("rank_idx")
                )
                .filter(pl.col("rank_idx") < 30)
                .with_columns((pl.col("rank_idx") + 1).alias("rank"))
                .drop("rank_idx")
            )

        action_key_ranking_rows = unit_scope_info.get(unit_key, {}).get("ranking_rows", [])
        action_key_ranking_df = (
            pl.DataFrame(action_key_ranking_rows)
            if action_key_ranking_rows
            else pl.DataFrame()
        )
        action_key_ranking_path = out_unit_dir / "step2_action_key_ranking.parquet"
        if not action_key_ranking_df.is_empty():
            action_key_ranking_df.write_parquet(action_key_ranking_path)

        unit_baseline_vs_filtered_df = (
            pl.DataFrame([r for r in global_rows if str(r.get("unit")) == unit_key])
            if global_rows
            else pl.DataFrame()
        )
        baseline_vs_filtered_root_path = out_unit_dir / "step2_baseline_vs_filtered_root.parquet"
        if not unit_baseline_vs_filtered_df.is_empty():
            unit_baseline_vs_filtered_df.sort(
                ["comparison_metric_improved", "metric_delta_filtered_minus_baseline"],
                descending=[True, True],
            ).write_parquet(baseline_vs_filtered_root_path)

        feature_stability_path = out_unit_dir / "step2_feature_importance_stability.parquet"
        if not unit_feature_stability_df.is_empty():
            unit_feature_stability_df.write_parquet(feature_stability_path)

        feature_noise_path = out_unit_dir / "step2_feature_noise_summary.parquet"
        if not unit_feature_noise_df.is_empty():
            unit_feature_noise_df.write_parquet(feature_noise_path)

        top_features_by_combo_path = out_unit_dir / "step2_top_features_by_combo.parquet"
        if not top_features_by_combo_df.is_empty():
            top_features_by_combo_df.write_parquet(top_features_by_combo_path)

        unit_summary = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "run_id": run_dir.name,
            "model_name": model_name,
            "unit": unit_key,
            "timeframe": unit.timeframe,
            "target": unit.target,
            "feature_target": unit.feature_target,
            "selection_metric": unit.selection_metric,
            "selection_direction": unit.selection_direction,
            "combo_processing_mode": combo_processing_mode,
            "selection_scope": combo_processing_mode,
            "selected_action_keys": unit_scope_info.get(unit_key, {}).get(
                "selected_action_keys", []
            ),
            "topk_action_keys_per_root": int(topk_action_keys_per_root),
            "comparison_metric_mode": comparison_metric_mode,
            "feature_selector_method": str(feature_selector_method),
            "selector_steps": int(selector_steps),
            "selector_shap_calc_type": str(selector_shap_calc_type),
            "selector_keep_ratio": float(selector_keep_ratio),
            "selector_fold_vote_min_frac": float(selector_fold_vote_min_frac),
            "selector_step_vote_min_frac": float(selector_step_vote_min_frac),
            "winner_metric": winner_metric,
            "no_worse_accuracy_guard": bool(no_worse_accuracy_guard),
            "skip_prune_if_baseline_accuracy_ge": float(skip_prune_if_baseline_accuracy_ge),
            "enforce_step1_combo_alignment": bool(enforce_step1_combo_alignment),
            "enforce_step1_fold_alignment": bool(enforce_step1_fold_alignment),
            "debug_step_selection": bool(debug_step_selection),
            "debug_combo_detail": bool(debug_combo_detail),
            "debug_artifact_paths": bool(debug_artifact_paths),
            "debug_walkforward": bool(debug_walkforward),
            "debug_walkforward_every_steps": int(debug_walkforward_every_steps),
            "steps_seen": int(len(step_dirs)),
            "combos_evaluated": int(len(combo_summaries)),
            "combo_keys": sorted(combo_summaries.keys()),
            "winner_steps": int(len(step_winner_rows)),
            "winner_counts_by_action_key": winner_counts,
            "action_key_ranking_rows": action_key_ranking_rows,
            "failed_steps_sample": failed_steps[:20],
            "failed_reason_counts": reason_counts,
            "global_feature_mask": global_feature_mask,
            "combo_summaries": combo_summaries,
        }
        unit_summary_path = out_unit_dir / "step2_summary.json"
        with open(unit_summary_path, "w") as f:
            json.dump(unit_summary, f, indent=2)
        unit_summary["artifacts"] = {
            "summary": str(unit_summary_path),
            "step_winners": str(winner_path) if not winner_df.is_empty() else None,
            "step_debug": str(step_debug_path) if not step_debug_df.is_empty() else None,
            "combo_debug": str(combo_debug_path) if not combo_debug_df.is_empty() else None,
            "action_key_ranking": (
                str(action_key_ranking_path) if not action_key_ranking_df.is_empty() else None
            ),
            "baseline_vs_filtered_root": (
                str(baseline_vs_filtered_root_path)
                if not unit_baseline_vs_filtered_df.is_empty()
                else None
            ),
            "feature_importance_stability": (
                str(feature_stability_path) if not unit_feature_stability_df.is_empty() else None
            ),
            "feature_noise_summary": (
                str(feature_noise_path) if not unit_feature_noise_df.is_empty() else None
            ),
            "top_features_by_combo": (
                str(top_features_by_combo_path) if not top_features_by_combo_df.is_empty() else None
            ),
        }
        unit_summaries[unit_key] = unit_summary
        if verbose:
            print(
                f"[Stage1-Step2] {unit_key}: combos={len(combo_summaries)}, "
                f"winner_steps={len(step_winner_rows)}, "
                f"global_mask={'yes' if global_feature_mask else 'no'}, "
                f"step_debug_rows={len(step_debug_rows)}, "
                f"combo_debug_rows={len(combo_debug_rows)}"
            )

    global_df = pl.DataFrame(global_rows) if global_rows else pl.DataFrame()
    global_path = step2_root / "step2_global_summary.parquet"
    if not global_df.is_empty():
        global_df.write_parquet(global_path)
    summary = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "run_id": run_dir.name,
        "model_name": model_name,
        "source_stage1_run_dir": str(run_dir),
        "output_root": str(step2_root),
        "params": {
            "max_steps_per_unit": max_steps_per_unit,
            "noisy_bottom_quantile": float(noisy_bottom_quantile),
            "noisy_presence_threshold": float(noisy_presence_threshold),
            "min_features_keep": int(min_features_keep),
            "feature_importance_type": str(feature_importance_type),
            "feature_selector_method": str(feature_selector_method),
            "selector_steps": int(selector_steps),
            "selector_shap_calc_type": str(selector_shap_calc_type),
            "selector_keep_ratio": float(selector_keep_ratio),
            "selector_fold_vote_min_frac": float(selector_fold_vote_min_frac),
            "selector_step_vote_min_frac": float(selector_step_vote_min_frac),
            "reward_cross_error_weight": float(reward_cross_error_weight),
            "promotion_min_reward_delta": float(promotion_min_reward_delta),
            "promotion_max_cross_direction_error_delta": float(
                promotion_max_cross_direction_error_delta
            ),
            "promotion_min_macro_f1_delta": float(promotion_min_macro_f1_delta),
            "output_subdir": str(output_subdir),
            "combo_processing_mode": combo_processing_mode,
            "selection_scope": combo_processing_mode,
            "topk_action_keys_per_root": int(topk_action_keys_per_root),
            "comparison_metric_mode": comparison_metric_mode,
            "winner_metric": winner_metric,
            "no_worse_accuracy_guard": bool(no_worse_accuracy_guard),
            "skip_prune_if_baseline_accuracy_ge": float(skip_prune_if_baseline_accuracy_ge),
            "enforce_step1_combo_alignment": bool(enforce_step1_combo_alignment),
            "enforce_step1_fold_alignment": bool(enforce_step1_fold_alignment),
            "debug_step_selection": bool(debug_step_selection),
            "debug_combo_detail": bool(debug_combo_detail),
            "debug_artifact_paths": bool(debug_artifact_paths),
            "debug_walkforward": bool(debug_walkforward),
            "debug_walkforward_every_steps": int(debug_walkforward_every_steps),
        },
        "units": unit_summaries,
        "artifacts": {
            "global_summary": str(global_path) if not global_df.is_empty() else None,
        },
    }
    summary_path = step2_root / "step2_run_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    summary["artifacts"]["run_summary"] = str(summary_path)
    return summary


__all__ = ["run_stage1_step2_feature_pruning"]
