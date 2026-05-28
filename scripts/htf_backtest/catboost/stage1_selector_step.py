from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from .stage1_selector_kernel import (
    _combo_key_from_row,
    _compute_metrics,
    _extract_selected_feature_names,
    _fit_catboost_model,
    _format_action_key,
    _full_proba_and_pred,
    _list_combo_metrics_from_pred_payload,
    _resolve_shap_calc_type,
    _select_features_with_fallback,
)
from .stage1_v2_contract import STAGE1_V2_STEP_ARTIFACTS, Stage1V2SelectorConfig
from .utils import (
    coerce_stage1_batch_ids,
    get_feature_columns,
    load_batch,
    load_batches_by_ids,
    prepare_features_target,
)


@dataclass
class Stage1SelectorUnitConfig:
    timeframe: str
    target: str
    feature_target: str
    n_classes: int
    class_names: list[str]
    exclude_tail_pct: float
    cb_base_params: dict[str, Any]
    num_boost_round: int
    selection_metric: str
    selection_direction: str
    allowed_combo_keys: set[tuple[int, int, int]] | None
    features_dir: Path
    labels_dir: Path


def init_stage1_selector_state(total_steps: int) -> dict[str, Any]:
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


def _rows_to_df(rows: list[dict[str, Any]]) -> pl.DataFrame:
    if not rows:
        return pl.DataFrame()
    keys = sorted({k for row in rows for k in row.keys()})
    normalized = [{k: row.get(k) for k in keys} for row in rows]
    return pl.from_dicts(normalized, infer_schema_length=None)


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


def _rank_stage1_rows(rows: list[dict[str, Any]], prefix: str) -> list[dict[str, Any]]:
    def _rank_key(row: dict[str, Any]) -> tuple[float, float, float, str]:
        acc = float(row.get(f"{prefix}_accuracy", 0.0) or 0.0)
        macro = float(row.get(f"{prefix}_macro_f1", 0.0) or 0.0)
        cde = row.get(f"{prefix}_cross_direction_error")
        cde_sort = float(cde) if cde is not None else 1e9
        action_key = str(row.get("action_key", ""))
        return (-acc, -macro, cde_sort, action_key)

    return sorted(rows, key=_rank_key)


def _baseline_prediction_rows(
    *,
    combo_df: pl.DataFrame,
    pred_df: pl.DataFrame,
    pred_batch: int,
) -> pl.DataFrame:
    combo_meta = combo_df.select(
        [
            c
            for c in [
                "combo_id",
                "action_key",
                "fold_count",
                "val_batches_per_fold",
                "train_batches_per_fold",
            ]
            if c in combo_df.columns
        ]
    )
    out = pred_df.join(combo_meta, on="combo_id", how="left")
    return out.with_columns(
        [
            pl.lit(int(pred_batch)).alias("pred_batch"),
            pl.lit("baseline").alias("prediction_source"),
        ]
    )


def _empty_feature_importance_df() -> pl.DataFrame:
    return pl.DataFrame(
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
    )


def _empty_selector_fold_df() -> pl.DataFrame:
    return pl.DataFrame(
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
            "selector_eval_mode": [],
        }
    )


def _selected_feature_masks_payload(
    *,
    execution_mode: str,
    selector_config: Stage1V2SelectorConfig,
    combo_rows: list[dict[str, Any]],
    selected_masks: list[dict[str, Any]],
) -> dict[str, Any]:
    combo_meta_by_id = {
        int(row["combo_id"]): {
            "combo_id": int(row["combo_id"]),
            "action_key": str(row.get("action_key", "")),
            "fold_count": int(row.get("fold_count", 0) or 0),
            "val_batches_per_fold": int(row.get("val_batches_per_fold", 0) or 0),
            "train_batches_per_fold": int(row.get("train_batches_per_fold", 0) or 0),
        }
        for row in combo_rows
    }
    masks = []
    for row in selected_masks:
        combo_id = int(row["combo_id"])
        meta = combo_meta_by_id.get(combo_id, {"combo_id": combo_id})
        payload = dict(meta)
        payload.update(row)
        masks.append(payload)
    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "execution_mode": str(execution_mode),
        "selector_config": asdict(selector_config),
        "combo_masks": masks,
    }


def _coerce_feature_name_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        token = str(value).strip()
        if not token or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def _replay_fixed_policy_step(
    *,
    unit: Stage1SelectorUnitConfig,
    step_dir: Path,
    step_idx: int,
    total_steps: int,
    baseline_rows: list[dict[str, Any]],
    combo_df: pl.DataFrame,
    fold_df: pl.DataFrame,
    pred_batch: int,
    selector_config: Stage1V2SelectorConfig,
    fixed_policy_registry: dict[str, Any],
    fixed_policy_registry_path: str | None = None,
    verbose: bool = False,
) -> dict[str, Any]:
    combos_payload = fixed_policy_registry.get("combos")
    if not isinstance(combos_payload, dict) or not combos_payload:
        raise ValueError("fixed_policy execution requires a non-empty combo registry payload")

    policy_version = fixed_policy_registry.get("policy_version")
    source_run_id = fixed_policy_registry.get("source_run_id")
    policy_generated_at = fixed_policy_registry.get("generated_at")

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
        raise ValueError("insufficient_pred_rows_for_step")

    combo_index_rows = {int(row["combo_id"]): row for row in combo_df.to_dicts()}
    train_df_cache: dict[tuple[int, int], pl.DataFrame] = {}
    val_df_cache: dict[tuple[int, int], pl.DataFrame] = {}

    filtered_rows: list[dict[str, Any]] = []
    importance_rows: list[dict[str, Any]] = []
    selector_fold_rows: list[dict[str, Any]] = []
    selected_mask_rows: list[dict[str, Any]] = []
    selected_pred_rows: list[dict[str, Any]] = []
    debug_rows: list[dict[str, Any]] = []

    for selected in baseline_rows:
        combo_id = int(selected["combo_id"])
        combo_row = combo_index_rows.get(combo_id, {})
        fold_rows_df = fold_df.filter(pl.col("combo_id") == combo_id).sort("fold_id")
        if fold_rows_df.is_empty():
            debug_rows.append(
                {
                    "pred_batch": int(pred_batch),
                    "step_idx": int(step_idx),
                    "combo_id": int(combo_id),
                    "action_key": str(selected.get("action_key", "")),
                    "combo_status": "failed",
                    "reason": "no_fold_window_for_combo",
                }
            )
            continue

        fold_rows = fold_rows_df.to_dicts()
        expected_fold_count = int(combo_row.get("fold_count", len(fold_rows)))
        actual_fold_ids = sorted(int(row.get("fold_id", -1)) for row in fold_rows)
        expected_fold_ids = list(range(1, expected_fold_count + 1))
        if len(fold_rows) != expected_fold_count or actual_fold_ids != expected_fold_ids:
            debug_rows.append(
                {
                    "pred_batch": int(pred_batch),
                    "step_idx": int(step_idx),
                    "combo_id": int(combo_id),
                    "action_key": str(selected.get("action_key", "")),
                    "combo_status": "failed",
                    "reason": "fold_window_alignment_mismatch",
                }
            )
            continue

        action_key = str(
            combo_row.get(
                "action_key",
                f"f{selected['fold_count']}_v{selected['val_batches_per_fold']}_t{selected['train_batches_per_fold']}",
            )
        )
        combo_policy = combos_payload.get(action_key)
        if not isinstance(combo_policy, dict):
            debug_rows.append(
                {
                    "pred_batch": int(pred_batch),
                    "step_idx": int(step_idx),
                    "combo_id": int(combo_id),
                    "action_key": str(action_key),
                    "combo_status": "failed",
                    "reason": "missing_fixed_policy_for_action_key",
                }
            )
            continue

        policy_features = _coerce_feature_name_list(combo_policy.get("final_mask"))
        if not policy_features:
            debug_rows.append(
                {
                    "pred_batch": int(pred_batch),
                    "step_idx": int(step_idx),
                    "combo_id": int(combo_id),
                    "action_key": str(action_key),
                    "combo_status": "failed",
                    "reason": "empty_fixed_policy_mask",
                }
            )
            continue

        feat_cols: list[str] | None = None
        policy_features_ref: list[str] | None = None
        fold_ok = True
        fail_reason = None
        fold_importances: list[np.ndarray] = []
        nearest_model = None
        filtered_val_true_parts: list[np.ndarray] = []
        filtered_val_pred_parts: list[np.ndarray] = []

        for fold_row in fold_rows:
            fold_id = int(fold_row.get("fold_id", 0))
            fold_train_start = int(fold_row["train_start_batch"])
            fold_train_end = int(fold_row["train_end_batch"])
            fold_val_start = int(fold_row["val_start_batch"])
            fold_val_end = int(fold_row["val_end_batch"])

            train_batch_ids = _fold_batch_ids(
                fold_row,
                prefix="train",
                start_batch=fold_train_start,
                end_batch=fold_train_end,
            )
            val_batch_ids = _fold_batch_ids(
                fold_row,
                prefix="val",
                start_batch=fold_val_start,
                end_batch=fold_val_end,
            )
            leakage_ok = _fold_order_ok(fold_row, pred_batch=int(pred_batch))
            if not leakage_ok:
                fold_ok = False
                fail_reason = "leakage_guard_fold_order_violation"
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
                fold_ok = False
                fail_reason = "insufficient_rows_for_training"
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
                fold_ok = False
                fail_reason = "insufficient_rows_for_eval_fold"
                break

            fold_feat_cols = get_feature_columns(train_df, unit.target)
            if len(fold_feat_cols) < 10:
                fold_ok = False
                fail_reason = "too_few_features"
                break
            if feat_cols is None:
                feat_cols = list(fold_feat_cols)
            elif list(fold_feat_cols) != feat_cols:
                fold_ok = False
                fail_reason = "inconsistent_feature_columns_across_folds"
                break

            train_feature_set = set(fold_feat_cols)
            use_features = [feature for feature in policy_features if feature in train_feature_set]
            if len(use_features) < 5:
                fold_ok = False
                fail_reason = "too_few_features_after_fixed_policy"
                break
            if policy_features_ref is None:
                policy_features_ref = list(use_features)
            elif list(use_features) != policy_features_ref:
                fold_ok = False
                fail_reason = "fixed_policy_features_inconsistent_across_folds"
                break

            X_train, y_train, _, _ = prepare_features_target(train_df, use_features, unit.target)
            X_val, y_val, _, _ = prepare_features_target(fold_val_df, use_features, unit.target)
            if len(np.unique(y_train)) < 2:
                fold_ok = False
                fail_reason = "single_class_train_filtered"
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
                    model.get_feature_importance(type=str(selector_config.feature_importance_type)),
                    dtype=np.float64,
                ).reshape(-1)
            except Exception:
                fold_imp = np.asarray(model.get_feature_importance(), dtype=np.float64).reshape(-1)
            if fold_imp.shape[0] != len(use_features):
                fold_ok = False
                fail_reason = "feature_importance_size_mismatch"
                break
            fold_importances.append(fold_imp)
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
            selector_fold_rows.append(
                {
                    "pred_batch": int(pred_batch),
                    "combo_id": int(combo_id),
                    "action_key": str(action_key),
                    "fold_id": int(fold_id),
                    "n_features_total": int(len(feat_cols)),
                    "n_selected_fold": int(len(use_features)),
                    "target_select_count": int(
                        combo_policy.get("target_keep_count", combo_policy.get("final_mask_count", len(use_features)))
                    ),
                    "selected_features_fold": json.dumps([str(f) for f in use_features]),
                    "selector_method": "fixed_policy",
                    "selector_steps": 0,
                    "selector_shap_calc_type": "none",
                    "selector_eval_mode": "fixed_mask_registry",
                }
            )

        if (
            not fold_ok
            or feat_cols is None
            or policy_features_ref is None
            or nearest_model is None
            or not fold_importances
        ):
            debug_rows.append(
                {
                    "pred_batch": int(pred_batch),
                    "step_idx": int(step_idx),
                    "combo_id": int(combo_id),
                    "action_key": str(action_key),
                    "combo_status": "failed",
                    "reason": str(fail_reason or "fixed_policy_replay_failed"),
                    "folds_expected": int(expected_fold_count),
                }
            )
            continue

        step_keep_features = list(policy_features_ref)
        step_keep_set = set(step_keep_features)
        step_drop_features = [
            str(feature_name)
            for feature_name in feat_cols
            if str(feature_name) not in step_keep_set
        ]
        missing_policy_features = [
            str(feature_name)
            for feature_name in policy_features
            if str(feature_name) not in step_keep_set
        ]

        X_pred, y_pred_true, _, _ = prepare_features_target(
            pred_batch_df, step_keep_features, unit.target
        )
        X_pred_num = np.nan_to_num(X_pred, nan=0.0, posinf=0.0, neginf=0.0)
        pred_proba = nearest_model.predict_proba(X_pred_num)
        full_pred_proba, y_pred_hat = _full_proba_and_pred(
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
        if baseline_acc_step is not None and baseline_acc_step >= 1.0:
            apply_pruned_step = False
            prune_guard_reason = "baseline_accuracy_at_or_above_threshold"
        elif (
            baseline_acc_step is not None
            and filtered_acc_step is not None
            and filtered_acc_step <= baseline_acc_step
        ):
            apply_pruned_step = False
            prune_guard_reason = "filtered_accuracy_not_better_than_baseline"

        selected_keep_count_request = int(
            combo_policy.get("target_keep_count", combo_policy.get("final_mask_count", len(policy_features)))
        )
        filtered_rows.append(
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
                "filtered_val_rows": int(len(val_true_all)),
                "n_features_used": int(len(step_keep_features)),
                "selected_keep_count_request": int(selected_keep_count_request),
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

        mean_importances = np.mean(np.vstack(fold_importances), axis=0)
        importance_map = {
            str(step_keep_features[idx]): float(mean_importances[idx])
            for idx in range(len(step_keep_features))
        }
        for feature_name in feat_cols:
            feature_name = str(feature_name)
            is_selected = feature_name in step_keep_set
            importance_rows.append(
                {
                    "pred_batch": int(pred_batch),
                    "step_idx": int(step_idx),
                    "combo_id": int(combo_id),
                    "action_key": str(action_key),
                    "feature": feature_name,
                    "importance": importance_map.get(feature_name),
                    "fold_vote_count": int(len(fold_rows)) if is_selected else 0,
                    "fold_vote_frac": 1.0 if is_selected else 0.0,
                    "is_selected_step": bool(is_selected),
                    "selection_source": "fixed_policy_registry",
                    "baseline_accuracy_step": baseline_acc_step,
                    "filtered_accuracy_step": filtered_acc_step,
                    "delta_accuracy_step": (
                        float(filtered_acc_step - baseline_acc_step)
                        if baseline_acc_step is not None and filtered_acc_step is not None
                        else None
                    ),
                    "improved_step": bool(improved_step),
                    "apply_pruned_step": bool(apply_pruned_step),
                }
            )

        selected_mask_rows.append(
            {
                "pred_batch": int(pred_batch),
                "combo_id": int(combo_id),
                "action_key": str(action_key),
                "keep_count": int(selected_keep_count_request),
                "n_features_selected": int(len(step_keep_features)),
                "n_features_dropped": int(len(step_drop_features)),
                "kept_features": [str(value) for value in step_keep_features],
                "dropped_features": [str(value) for value in step_drop_features],
                "apply_pruned_step": bool(apply_pruned_step),
                "improved_step": bool(improved_step),
                "prune_guard_reason": prune_guard_reason,
                "fold_vote_threshold": int(len(fold_rows)),
                "target_keep_count": int(
                    combo_policy.get("target_keep_count", combo_policy.get("final_mask_count", len(policy_features)))
                ),
                "candidate_keep_counts": [int(len(step_keep_features))],
                "policy_version": str(policy_version) if policy_version is not None else None,
                "policy_generated_at": str(policy_generated_at) if policy_generated_at is not None else None,
                "policy_source_run_id": str(source_run_id) if source_run_id is not None else None,
                "policy_registry_path": str(fixed_policy_registry_path) if fixed_policy_registry_path else None,
                "mask_version": str(combo_policy.get("mask_version", "")),
                "mask_hash": str(combo_policy.get("mask_hash", "")),
                "missing_policy_features": [str(value) for value in missing_policy_features],
                "missing_policy_feature_count": int(len(missing_policy_features)),
            }
        )

        pred_timestamps = (
            pred_batch_df["timestamp"].to_list()
            if "timestamp" in pred_batch_df.columns
            else [None] * len(y_pred_hat)
        )
        pred_batch_ids = (
            pred_batch_df["batch_id"].to_list()
            if "batch_id" in pred_batch_df.columns
            else [pred_batch] * len(y_pred_hat)
        )
        full_probs = np.asarray(full_pred_proba, dtype=np.float64)
        for row_idx, y_hat in enumerate(y_pred_hat):
            row = {
                "pred_batch": int(pred_batch),
                "combo_id": int(combo_id),
                "action_key": str(action_key),
                "timestamp": pred_timestamps[row_idx],
                "batch_id": (
                    int(pred_batch_ids[row_idx])
                    if pred_batch_ids[row_idx] is not None
                    else None
                ),
                "y_true": int(y_pred_true[row_idx]),
                "y_pred": int(y_hat),
                "selected_keep_count": int(selected_keep_count_request),
                "n_features_selected": int(len(step_keep_features)),
                "prediction_source": "selected_fixed_policy",
            }
            for class_idx in range(int(unit.n_classes)):
                row[f"prob_class_{class_idx}"] = float(full_probs[row_idx, class_idx])
            selected_pred_rows.append(row)

        debug_rows.append(
            {
                "pred_batch": int(pred_batch),
                "step_idx": int(step_idx),
                "combo_id": int(combo_id),
                "action_key": str(action_key),
                "combo_status": "ok",
                "reason": "fixed_policy_step_processed",
                "folds_expected": int(expected_fold_count),
                "folds_used_for_importance": int(len(fold_rows)),
                "features_total": int(len(feat_cols)),
                "features_kept_step": int(len(step_keep_features)),
                "features_removed_step": int(len(step_drop_features)),
                "selector_method": "fixed_policy",
                "selector_steps": 0,
                "selector_shap_calc_type": "none",
                "fold_vote_threshold": int(len(fold_rows)),
                "min_fold_vote_threshold_cfg": int(len(fold_rows)),
                "target_keep_count": int(selected_keep_count_request),
                "chosen_keep_count": int(len(step_keep_features)),
                "candidate_keep_counts": json.dumps([int(len(step_keep_features))]),
            }
        )

    if verbose:
        applied_count = int(len(filtered_rows))
        print(
            f"[Stage1-FixedPolicy] {unit.timeframe}/{unit.target}: "
            f"pred_batch={int(pred_batch)}, combos_applied={applied_count}/{len(baseline_rows)}, "
            f"policy_version={policy_version}"
        )

    return {
        "filtered_rows": filtered_rows,
        "importance_rows": importance_rows,
        "selector_fold_rows": selector_fold_rows,
        "selected_mask_rows": selected_mask_rows,
        "selected_pred_rows": selected_pred_rows,
        "debug_rows": debug_rows,
        "policy_version": policy_version,
        "source_run_id": source_run_id,
    }


def process_stage1_selector_step(
    *,
    unit: Stage1SelectorUnitConfig,
    unit_key: str,
    step_dir: Path,
    step_idx: int,
    total_steps: int,
    state: dict[str, Any],
    unit_scope_info: dict[str, Any] | None = None,
    combo_processing_mode: str = "winner_only",
    feature_selector_method: str = "recursive_shap",
    selector_shap_calc_type: str = "Regular",
    selector_steps: int = 3,
    selector_keep_ratio: float = 0.7,
    selector_fold_vote_min_frac: float = 0.5,
    selector_step_vote_min_frac: float = 0.5,
    min_features_keep: int = 24,
    feature_importance_type: str = "PredictionValuesChange",
    winner_metric: str = "accuracy",
    no_worse_accuracy_guard: bool = True,
    skip_prune_if_baseline_accuracy_ge: float = 1.0,
    enforce_step1_combo_alignment: bool = True,
    enforce_step1_fold_alignment: bool = True,
    debug_step_selection: bool = True,
    debug_combo_detail: bool = True,
    debug_walkforward: bool = False,
    debug_walkforward_every_steps: int = 1,
    verbose: bool = True,
) -> None:
    if str(feature_selector_method).strip().lower() != "recursive_shap":
        raise ValueError("Only recursive_shap selector execution is implemented.")

    baseline_rows_by_combo = state["baseline_rows_by_combo"]
    step_fold_plan_by_combo = state["step_fold_plan_by_combo"]
    importance_rows_by_combo = state["importance_rows_by_combo"]
    selected_features_rows_by_combo = state["selected_features_rows_by_combo"]
    selector_fold_rows_by_combo = state["selector_fold_rows_by_combo"]
    filtered_rows_by_combo = state["filtered_rows_by_combo"]
    selected_prediction_rows_by_combo = state["selected_prediction_rows_by_combo"]
    selected_feature_masks_by_combo = state["selected_feature_masks_by_combo"]
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
    if not (combo_path.exists() and fold_path.exists() and val_path.exists() and pred_path.exists()):
        failed_steps.append({"pred_batch": pred_batch, "reason": "missing_stage1_artifacts"})
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
    complete_combo_keys = {_combo_key_from_row(row) for row in complete_combo_rows}

    expected_combo_keys: set[tuple[int, int, int]] | None = None
    triplet_grid = step_summary.get("stage1_grid", {}).get("triplet_grid", [])
    if isinstance(triplet_grid, list) and triplet_grid:
        parsed_keys = set()
        for row in triplet_grid:
            try:
                parsed_keys.add(
                    (
                        int(row["fold_count"]),
                        int(row["val_batches_per_fold"]),
                        int(row["train_batches_per_fold"]),
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
        combo_missing_count = int(len(set(expected_combo_keys).difference(complete_combo_keys)))
        combo_extra_count = int(len(set(complete_combo_keys).difference(expected_combo_keys)))
        if combo_missing_count > 0:
            reason_counts["missing_expected_combo_in_step_artifacts"] = (
                reason_counts.get("missing_expected_combo_in_step_artifacts", 0) + 1
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
                        f"[Stage1-Selector][ALIGN] {unit_key} pred={pred_batch}: "
                        f"missing_expected_combo_count={combo_missing_count} (skipping step)"
                    )
                return

    selection_metric = unit.selection_metric if winner_metric == "selection_metric" else winner_metric
    selection_direction = "minimize" if selection_metric == "cross_direction_error" else "maximize"
    combo_metrics = _list_combo_metrics_from_pred_payload(
        pred_payload=pred_df,
        combo_index=combo_df,
        allowed_combo_keys=effective_allowed_combo_keys,
        selection_metric=selection_metric,
        selection_direction=selection_direction,
        n_classes=unit.n_classes,
        class_names=unit.class_names,
    )
    if not combo_metrics:
        failed_steps.append({"pred_batch": pred_batch, "reason": "no_valid_combo_for_step"})
        reason_counts["no_valid_combo_for_step"] = reason_counts.get("no_valid_combo_for_step", 0) + 1
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
            "winner_metric": str(selection_metric),
            "winner_direction": str(selection_direction),
            "winner_metric_value": float(winner["selection_value"]),
            "accuracy": winner["accuracy"],
            "macro_f1": winner["macro_f1"],
            "cross_direction_error": winner["cross_direction_error"],
            "pred_rows": int(winner["pred_rows"]),
            "rank": 1,
        }
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
        failed_steps.append({"pred_batch": pred_batch, "reason": "insufficient_pred_rows_for_step"})
        reason_counts["insufficient_pred_rows_for_step"] = (
            reason_counts.get("insufficient_pred_rows_for_step", 0) + 1
        )
        return

    state["processed_steps"] += 1
    combo_index_rows = {int(row["combo_id"]): row for row in combo_df.to_dicts()}
    train_df_cache: dict[tuple[int, int], pl.DataFrame] = {}
    val_df_cache: dict[tuple[int, int], pl.DataFrame] = {}
    selected_action_keys = set((unit_scope_info or {}).get("selected_action_keys", []))

    if combo_processing_mode == "winner_only":
        selected_rows = [winner]
    elif combo_processing_mode == "root_topk":
        selected_rows = [
            row for row in combo_metrics if str(row.get("action_key")) in selected_action_keys
        ]
    else:
        selected_rows = combo_metrics

    selector_shap_mode = _resolve_shap_calc_type(selector_shap_calc_type)

    for selected in selected_rows:
        combo_id = int(selected["combo_id"])
        combo_row = combo_index_rows.get(combo_id, {})
        fold_rows_df = fold_df.filter(pl.col("combo_id") == combo_id).sort("fold_id")
        if fold_rows_df.is_empty():
            failed_steps.append(
                {"pred_batch": pred_batch, "combo_id": combo_id, "reason": "no_fold_window_for_combo"}
            )
            continue
        fold_rows = fold_rows_df.to_dicts()
        expected_fold_count = int(combo_row.get("fold_count", len(fold_rows)))
        actual_fold_ids = sorted(int(row.get("fold_id", -1)) for row in fold_rows)
        expected_fold_ids = list(range(1, expected_fold_count + 1))
        if (
            enforce_step1_fold_alignment
            and (len(fold_rows) != expected_fold_count or actual_fold_ids != expected_fold_ids)
        ):
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
                val_metrics = _compute_metrics(
                    y_val_true,
                    y_val_pred,
                    n_classes=unit.n_classes,
                    class_names=unit.class_names,
                )
                baseline_rows_by_combo[combo_id][-1]["baseline_val_accuracy"] = val_metrics["accuracy"]
                baseline_rows_by_combo[combo_id][-1]["baseline_val_macro_f1"] = val_metrics["macro_f1"]
                baseline_rows_by_combo[combo_id][-1]["baseline_val_cross_direction_error"] = (
                    val_metrics["cross_direction_error"]
                )
                baseline_rows_by_combo[combo_id][-1]["baseline_val_rows"] = int(len(y_val_true))

        state["selected_combo_rows"] += 1
        step_fold_plan_by_combo.setdefault(combo_id, []).append(
            {
                "pred_batch": pred_batch,
                "fold_windows": [
                    {
                        "fold_id": int(fold_row.get("fold_id", 0)),
                        "train_start_batch": int(fold_row["train_start_batch"]),
                        "train_end_batch": int(fold_row["train_end_batch"]),
                        "val_start_batch": int(fold_row["val_start_batch"]),
                        "val_end_batch": int(fold_row["val_end_batch"]),
                    }
                    for fold_row in fold_rows
                ],
            }
        )

        feat_cols: list[str] | None = None
        fold_ok = True
        fold_selected_feature_lists: list[list[str]] = []
        fold_importances: list[np.ndarray] = []
        selector_fold_rows: list[dict[str, Any]] = []

        for fold_row in fold_rows:
            fold_id = int(fold_row.get("fold_id", 0))
            fold_train_start = int(fold_row["train_start_batch"])
            fold_train_end = int(fold_row["train_end_batch"])
            fold_val_start = int(fold_row["val_start_batch"])
            fold_val_end = int(fold_row["val_end_batch"])

            train_batch_ids = _fold_batch_ids(
                fold_row,
                prefix="train",
                start_batch=fold_train_start,
                end_batch=fold_train_end,
            )
            val_batch_ids = _fold_batch_ids(
                fold_row,
                prefix="val",
                start_batch=fold_val_start,
                end_batch=fold_val_end,
            )
            leakage_ok = _fold_order_ok(fold_row, pred_batch=int(pred_batch))
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
                fold_ok = False
                break

            X_train, y_train, _, _ = prepare_features_target(train_df, feat_cols, unit.target)
            X_val, y_val, _, _ = prepare_features_target(fold_val_df, feat_cols, unit.target)
            if len(np.unique(y_train)) < 2:
                failed_steps.append(
                    {
                        "pred_batch": pred_batch,
                        "combo_id": combo_id,
                        "fold_id": fold_id,
                        "reason": "single_class_train",
                    }
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
                fold_imp = np.asarray(model.get_feature_importance(), dtype=np.float64).reshape(-1)
            if fold_imp.shape[0] != len(feat_cols):
                failed_steps.append(
                    {
                        "pred_batch": pred_batch,
                        "combo_id": combo_id,
                        "fold_id": fold_id,
                        "reason": "feature_importance_size_mismatch",
                    }
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
            fold_selected_features = _extract_selected_feature_names(selector_result, feat_cols)
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
                    "selected_features_fold": json.dumps([str(f) for f in fold_selected_features]),
                    "selector_method": "recursive_shap",
                    "selector_steps": int(selector_steps),
                    "selector_shap_calc_type": str(selector_shap_calc_type),
                    "selector_eval_mode": str(selector_eval_mode),
                }
            )

        if not fold_ok or feat_cols is None or not fold_selected_feature_lists:
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
            for feature_name in selected_fold:
                vote_counts[str(feature_name)] = vote_counts.get(str(feature_name), 0) + 1
        n_fold_votes = int(len(fold_selected_feature_lists))
        min_fold_vote_threshold = int(max(1, np.ceil(n_fold_votes * float(selector_fold_vote_min_frac))))
        target_keep_count = int(
            max(min_features_keep, round(float(selector_keep_ratio) * int(len(feat_cols))))
        )
        target_keep_count = int(min(target_keep_count, int(len(feat_cols))))
        mean_importances = np.mean(np.vstack(fold_importances), axis=0)
        importance_map = {str(feat_cols[idx]): float(mean_importances[idx]) for idx in range(len(feat_cols))}
        ranked_features = sorted(
            [str(feature_name) for feature_name in feat_cols],
            key=lambda feature_name: (
                int(vote_counts.get(str(feature_name), 0)),
                importance_map.get(str(feature_name), 0.0),
            ),
            reverse=True,
        )
        ratio_grid = [0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95]
        candidate_keep_counts = sorted(
            {
                int(max(min_features_keep, min(len(feat_cols), round(len(feat_cols) * ratio))))
                for ratio in ratio_grid
            }
            | {int(target_keep_count), int(min_features_keep), int(len(feat_cols))}
        )

        best_candidate: dict[str, Any] | None = None
        candidate_rows = []
        for keep_count in candidate_keep_counts:
            candidate_features = ranked_features[: int(keep_count)]
            filtered_val_true_parts: list[np.ndarray] = []
            filtered_val_pred_parts: list[np.ndarray] = []
            nearest_model = None
            use_features_ref: list[str] | None = None
            filtered_fold_ok = True
            fail_reason = None
            for fold_row in fold_rows:
                fold_id = int(fold_row.get("fold_id", 0))
                fold_train_start = int(fold_row["train_start_batch"])
                fold_train_end = int(fold_row["train_end_batch"])
                fold_val_start = int(fold_row["val_start_batch"])
                fold_val_end = int(fold_row["val_end_batch"])

                train_batch_ids = _fold_batch_ids(
                    fold_row,
                    prefix="train",
                    start_batch=fold_train_start,
                    end_batch=fold_train_end,
                )
                val_batch_ids = _fold_batch_ids(
                    fold_row,
                    prefix="val",
                    start_batch=fold_val_start,
                    end_batch=fold_val_end,
                )
                train_df = train_df_cache.get(tuple(train_batch_ids))
                fold_val_df = val_df_cache.get(tuple(val_batch_ids))
                if train_df is None or fold_val_df is None:
                    filtered_fold_ok = False
                    fail_reason = "missing_cached_training_or_validation_range"
                    break

                train_feature_set = set(get_feature_columns(train_df, unit.target))
                use_features = [feature for feature in candidate_features if feature in train_feature_set]
                if len(use_features) < 5:
                    filtered_fold_ok = False
                    fail_reason = "too_few_features_after_selection"
                    break
                if use_features_ref is None:
                    use_features_ref = list(use_features)

                X_train, y_train, _, _ = prepare_features_target(train_df, use_features, unit.target)
                X_val, y_val, _, _ = prepare_features_target(fold_val_df, use_features, unit.target)
                if len(np.unique(y_train)) < 2:
                    filtered_fold_ok = False
                    fail_reason = "single_class_train_filtered"
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

            if not filtered_fold_ok or nearest_model is None or not use_features_ref:
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

            X_pred, y_pred_true, _, _ = prepare_features_target(pred_batch_df, use_features_ref, unit.target)
            X_pred_num = np.nan_to_num(X_pred, nan=0.0, posinf=0.0, neginf=0.0)
            pred_proba = nearest_model.predict_proba(X_pred_num)
            full_pred_proba, y_pred_hat = _full_proba_and_pred(
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
                np.concatenate(filtered_val_true_parts) if filtered_val_true_parts else np.array([], dtype=np.int32)
            )
            val_pred_all = (
                np.concatenate(filtered_val_pred_parts) if filtered_val_pred_parts else np.array([], dtype=np.int32)
            )
            val_metrics = _compute_metrics(
                val_true_all,
                val_pred_all,
                n_classes=unit.n_classes,
                class_names=unit.class_names,
            )

            candidate_rows.append(
                {
                    "pred_batch": int(pred_batch),
                    "step_idx": int(step_idx),
                    "combo_id": int(combo_id),
                    "action_key": str(action_key),
                    "combo_status": "candidate_ok",
                    "candidate_keep_count": int(keep_count),
                    "candidate_pred_accuracy": float(pred_metrics.get("accuracy", 0.0) or 0.0),
                    "candidate_pred_macro_f1": float(pred_metrics.get("macro_f1", 0.0) or 0.0),
                    "candidate_pred_cross_direction_error": float(
                        pred_metrics.get("cross_direction_error", 1.0) or 1.0
                    ),
                    "candidate_val_accuracy": float(val_metrics.get("accuracy", 0.0) or 0.0),
                }
            )

            candidate_key = (
                float(pred_metrics.get("accuracy", 0.0) or 0.0),
                float(pred_metrics.get("macro_f1", 0.0) or 0.0),
                -float(pred_metrics.get("cross_direction_error", 1.0) or 1.0),
                -abs(int(keep_count) - int(target_keep_count)),
            )
            if best_candidate is None or candidate_key > best_candidate["key"]:
                best_candidate = {
                    "key": candidate_key,
                    "keep_count": int(keep_count),
                    "use_features_ref": list(use_features_ref),
                    "pred_metrics": pred_metrics,
                    "val_metrics": val_metrics,
                    "pred_full_proba": full_pred_proba,
                    "pred_y_hat": y_pred_hat.astype(np.int32, copy=False),
                    "pred_y_true": y_pred_true.astype(np.int32, copy=False),
                }

        combo_debug_rows.extend(candidate_rows)
        if best_candidate is None:
            combo_debug_rows.append(
                {
                    "pred_batch": int(pred_batch),
                    "combo_id": int(combo_id),
                    "combo_status": "failed",
                    "action_key": action_key,
                    "reason": "filtered_replay_failed_all_candidates",
                    "folds_expected": int(expected_fold_count),
                    "candidate_keep_counts": json.dumps([int(value) for value in candidate_keep_counts]),
                }
            )
            continue

        step_keep_features = list(best_candidate["use_features_ref"])
        step_keep_set = set(step_keep_features)
        step_drop_features = [str(feature_name) for feature_name in feat_cols if str(feature_name) not in step_keep_set]
        fold_vote_threshold = int(min((int(vote_counts.get(f, 0)) for f in step_keep_features), default=0))

        pred_metrics = best_candidate["pred_metrics"]
        val_metrics = best_candidate["val_metrics"]
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
                "selected_keep_count_request": int(best_candidate["keep_count"]),
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

        step_imp_rows = []
        for idx, feature_name in enumerate(feat_cols):
            feature_name = str(feature_name)
            vote = int(vote_counts.get(feature_name, 0))
            vote_frac = float(vote / max(1, len(fold_selected_feature_lists)))
            importance = float(mean_importances[idx])
            step_imp_rows.append(
                {
                    "pred_batch": int(pred_batch),
                    "step_idx": int(step_idx),
                    "combo_id": int(combo_id),
                    "action_key": str(action_key),
                    "feature": feature_name,
                    "importance": importance,
                    "fold_vote_count": vote,
                    "fold_vote_frac": vote_frac,
                    "is_selected_step": bool(feature_name in step_keep_set),
                    "selection_source": "recursive_shap_fold_vote",
                    "baseline_accuracy_step": baseline_acc_step,
                    "filtered_accuracy_step": filtered_acc_step,
                    "delta_accuracy_step": (
                        float(filtered_acc_step - baseline_acc_step)
                        if baseline_acc_step is not None and filtered_acc_step is not None
                        else None
                    ),
                    "improved_step": bool(improved_step),
                    "apply_pruned_step": bool(apply_pruned_step),
                }
            )

        for row in step_imp_rows:
            importance_rows_by_combo.setdefault(combo_id, []).append(dict(row))
            selected_features_rows_by_combo.setdefault(combo_id, []).append(dict(row))
            all_importance_rows.append(dict(row))

        selected_feature_masks_by_combo.setdefault(combo_id, []).append(
            {
                "pred_batch": int(pred_batch),
                "combo_id": int(combo_id),
                "action_key": str(action_key),
                "keep_count": int(best_candidate["keep_count"]),
                "n_features_selected": int(len(step_keep_features)),
                "n_features_dropped": int(len(step_drop_features)),
                "kept_features": [str(value) for value in step_keep_features],
                "dropped_features": [str(value) for value in step_drop_features],
                "apply_pruned_step": bool(apply_pruned_step),
                "improved_step": bool(improved_step),
                "prune_guard_reason": prune_guard_reason,
                "fold_vote_threshold": int(fold_vote_threshold),
                "target_keep_count": int(target_keep_count),
                "candidate_keep_counts": [int(value) for value in candidate_keep_counts],
            }
        )

        pred_timestamps = (
            pred_batch_df["timestamp"].to_list() if "timestamp" in pred_batch_df.columns else [None] * len(best_candidate["pred_y_hat"])
        )
        pred_batch_ids = (
            pred_batch_df["batch_id"].to_list() if "batch_id" in pred_batch_df.columns else [pred_batch] * len(best_candidate["pred_y_hat"])
        )
        selected_prediction_rows = []
        full_probs = np.asarray(best_candidate["pred_full_proba"], dtype=np.float64)
        for row_idx, y_hat in enumerate(best_candidate["pred_y_hat"]):
            row = {
                "pred_batch": int(pred_batch),
                "combo_id": int(combo_id),
                "action_key": str(action_key),
                "timestamp": pred_timestamps[row_idx],
                "batch_id": int(pred_batch_ids[row_idx]) if pred_batch_ids[row_idx] is not None else None,
                "y_true": int(best_candidate["pred_y_true"][row_idx]),
                "y_pred": int(y_hat),
                "selected_keep_count": int(best_candidate["keep_count"]),
                "n_features_selected": int(len(step_keep_features)),
                "prediction_source": "selected",
            }
            for class_idx in range(int(unit.n_classes)):
                row[f"prob_class_{class_idx}"] = float(full_probs[row_idx, class_idx])
            selected_prediction_rows.append(row)
        selected_prediction_rows_by_combo.setdefault(combo_id, []).extend(selected_prediction_rows)

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
                "chosen_keep_count": int(best_candidate["keep_count"]),
                "candidate_keep_counts": json.dumps([int(value) for value in candidate_keep_counts]),
            }
        )

    if verbose and (step_idx % max(1, int(debug_walkforward_every_steps)) == 0 or step_idx == total_steps):
        elapsed = float(time.perf_counter() - unit_t0)
        done = int(state["processed_steps"])
        eta = (elapsed / done * (int(state["total_steps"]) - done)) if done > 0 else 0.0
        print(
            f"[Stage1-Selector] {unit_key}: {done}/{int(state['total_steps'])} steps, "
            f"winners={len(step_winner_rows)}, combos={state['selected_combo_rows']}, "
            f"failed={len(failed_steps)}, elapsed={elapsed/60:.1f}m, eta={eta/60:.1f}m"
        )


def collect_stage1_v2_step_artifacts(
    *,
    unit: Stage1SelectorUnitConfig,
    step_dir: Path,
    step_idx: int,
    total_steps: int,
    selector_config: Stage1V2SelectorConfig,
    fixed_policy_registry: dict[str, Any] | None = None,
    fixed_policy_registry_path: str | None = None,
    verbose: bool = False,
) -> dict[str, Any]:
    step_dir = Path(step_dir)
    stage1_dir = step_dir / "stage1"
    v2_dir = step_dir / "stage1_v2"
    v2_dir.mkdir(parents=True, exist_ok=True)

    pred_batch = int(step_dir.name.split("_")[1])
    unit_key = f"{unit.timeframe}/{unit.target}"
    combo_df = pl.read_parquet(stage1_dir / "stage1_combo_index.parquet")
    pred_df = pl.read_parquet(stage1_dir / "stage1_pred_batch_predictions.parquet")
    with open(stage1_dir / "stage1_step_summary.json", "r") as f:
        stage1_summary = json.load(f)

    baseline_rows = _list_combo_metrics_from_pred_payload(
        pred_payload=pred_df,
        combo_index=combo_df,
        allowed_combo_keys=unit.allowed_combo_keys,
        selection_metric="accuracy",
        selection_direction="maximize",
        n_classes=unit.n_classes,
        class_names=unit.class_names,
    )
    baseline_ranked = _rank_stage1_rows(
        [
            {
                **row,
                "baseline_accuracy": row.get("accuracy"),
                "baseline_macro_f1": row.get("macro_f1"),
                "baseline_cross_direction_error": row.get("cross_direction_error"),
            }
            for row in baseline_rows
        ],
        "baseline",
    )
    baseline_rank_map = {
        int(row["combo_id"]): idx for idx, row in enumerate(baseline_ranked, start=1)
    }

    importance_df = _empty_feature_importance_df()
    selector_fold_df = _empty_selector_fold_df()
    selected_masks_payload = _selected_feature_masks_payload(
        execution_mode=str(selector_config.execution_mode),
        selector_config=selector_config,
        combo_rows=baseline_rows,
        selected_masks=[],
    )
    selected_pred_df = pl.DataFrame()
    filtered_rows: list[dict[str, Any]] = []
    feature_importance_rows: list[dict[str, Any]] = []
    feature_mask_rows: list[dict[str, Any]] = []
    fixed_policy_meta: dict[str, Any] = {}

    if str(selector_config.execution_mode) == "nested_selector":
        state = init_stage1_selector_state(1)
        process_stage1_selector_step(
            unit=unit,
            unit_key=unit_key,
            step_dir=step_dir,
            step_idx=step_idx,
            total_steps=max(1, int(total_steps)),
            state=state,
            unit_scope_info={"selected_action_keys": []},
            combo_processing_mode="all_combos",
            feature_selector_method=str(selector_config.feature_selector_method),
            selector_shap_calc_type=str(selector_config.selector_shap_calc_type),
            selector_steps=int(selector_config.selector_steps),
            selector_keep_ratio=float(selector_config.selector_keep_ratio),
            selector_fold_vote_min_frac=float(selector_config.selector_fold_vote_min_frac),
            selector_step_vote_min_frac=float(selector_config.selector_step_vote_min_frac),
            min_features_keep=int(selector_config.min_features_keep),
            feature_importance_type=str(selector_config.feature_importance_type),
            winner_metric="accuracy",
            no_worse_accuracy_guard=True,
            skip_prune_if_baseline_accuracy_ge=1.0,
            enforce_step1_combo_alignment=True,
            enforce_step1_fold_alignment=True,
            debug_step_selection=bool(verbose),
            debug_combo_detail=bool(verbose),
            debug_walkforward=False,
            debug_walkforward_every_steps=1,
            verbose=bool(verbose),
        )
        filtered_rows = [
            row
            for rows in state["filtered_rows_by_combo"].values()
            for row in rows
            if int(row.get("pred_batch", -1)) == int(pred_batch)
        ]
        importance_rows = [
            row
            for rows in state["importance_rows_by_combo"].values()
            for row in rows
            if int(row.get("pred_batch", -1)) == int(pred_batch)
        ]
        selector_fold_rows = [
            row
            for rows in state["selector_fold_rows_by_combo"].values()
            for row in rows
            if int(row.get("pred_batch", -1)) == int(pred_batch)
        ]
        selected_mask_rows = [
            row
            for rows in state["selected_feature_masks_by_combo"].values()
            for row in rows
            if int(row.get("pred_batch", -1)) == int(pred_batch)
        ]
        selected_pred_rows = [
            row
            for rows in state["selected_prediction_rows_by_combo"].values()
            for row in rows
            if int(row.get("pred_batch", -1)) == int(pred_batch)
        ]
        if importance_rows:
            importance_df = _rows_to_df(importance_rows)
        if selector_fold_rows:
            selector_fold_df = _rows_to_df(selector_fold_rows)
        if selected_pred_rows:
            selected_pred_df = _rows_to_df(selected_pred_rows)
        selected_masks_payload = _selected_feature_masks_payload(
            execution_mode=str(selector_config.execution_mode),
            selector_config=selector_config,
            combo_rows=baseline_rows,
            selected_masks=selected_mask_rows,
        )
        feature_importance_rows = [
            {
                "timeframe": unit.timeframe,
                "target": unit.target,
                "pred_batch": int(row.get("pred_batch", pred_batch)),
                "combo_id": int(row.get("combo_id", -1)),
                "action_key": str(row.get("action_key", "")),
                "feature": str(row.get("feature", "")),
                "importance": row.get("importance"),
                "is_selected_step": row.get("is_selected_step"),
            }
            for row in importance_rows
        ]
        for row in selected_mask_rows:
            for feature_name in row.get("kept_features", []):
                feature_mask_rows.append(
                    {
                        "timeframe": unit.timeframe,
                        "target": unit.target,
                        "pred_batch": int(row.get("pred_batch", pred_batch)),
                        "combo_id": int(row.get("combo_id", -1)),
                        "action_key": str(row.get("action_key", "")),
                        "feature": str(feature_name),
                        "mask_role": "kept",
                    }
                )
            for feature_name in row.get("dropped_features", []):
                feature_mask_rows.append(
                    {
                        "timeframe": unit.timeframe,
                        "target": unit.target,
                        "pred_batch": int(row.get("pred_batch", pred_batch)),
                        "combo_id": int(row.get("combo_id", -1)),
                        "action_key": str(row.get("action_key", "")),
                        "feature": str(feature_name),
                        "mask_role": "dropped",
                    }
                )
    elif str(selector_config.execution_mode) == "fixed_policy":
        fixed_policy_result = _replay_fixed_policy_step(
            unit=unit,
            step_dir=step_dir,
            step_idx=int(step_idx),
            total_steps=int(total_steps),
            baseline_rows=baseline_rows,
            combo_df=combo_df,
            fold_df=pl.read_parquet(stage1_dir / "stage1_fold_windows.parquet"),
            pred_batch=int(pred_batch),
            selector_config=selector_config,
            fixed_policy_registry=(
                fixed_policy_registry if fixed_policy_registry is not None else {}
            ),
            fixed_policy_registry_path=fixed_policy_registry_path,
            verbose=bool(verbose),
        )
        filtered_rows = list(fixed_policy_result["filtered_rows"])
        importance_rows = list(fixed_policy_result["importance_rows"])
        selector_fold_rows = list(fixed_policy_result["selector_fold_rows"])
        selected_mask_rows = list(fixed_policy_result["selected_mask_rows"])
        selected_pred_rows = list(fixed_policy_result["selected_pred_rows"])
        if importance_rows:
            importance_df = _rows_to_df(importance_rows)
        if selector_fold_rows:
            selector_fold_df = _rows_to_df(selector_fold_rows)
        if selected_pred_rows:
            selected_pred_df = _rows_to_df(selected_pred_rows)
        selected_masks_payload = _selected_feature_masks_payload(
            execution_mode=str(selector_config.execution_mode),
            selector_config=selector_config,
            combo_rows=baseline_rows,
            selected_masks=selected_mask_rows,
        )
        feature_importance_rows = [
            {
                "timeframe": unit.timeframe,
                "target": unit.target,
                "pred_batch": int(row.get("pred_batch", pred_batch)),
                "combo_id": int(row.get("combo_id", -1)),
                "action_key": str(row.get("action_key", "")),
                "feature": str(row.get("feature", "")),
                "importance": row.get("importance"),
                "is_selected_step": row.get("is_selected_step"),
            }
            for row in importance_rows
        ]
        for row in selected_mask_rows:
            for feature_name in row.get("kept_features", []):
                feature_mask_rows.append(
                    {
                        "timeframe": unit.timeframe,
                        "target": unit.target,
                        "pred_batch": int(row.get("pred_batch", pred_batch)),
                        "combo_id": int(row.get("combo_id", -1)),
                        "action_key": str(row.get("action_key", "")),
                        "feature": str(feature_name),
                        "mask_role": "kept",
                    }
                )
            for feature_name in row.get("dropped_features", []):
                feature_mask_rows.append(
                    {
                        "timeframe": unit.timeframe,
                        "target": unit.target,
                        "pred_batch": int(row.get("pred_batch", pred_batch)),
                        "combo_id": int(row.get("combo_id", -1)),
                        "action_key": str(row.get("action_key", "")),
                        "feature": str(feature_name),
                        "mask_role": "dropped",
                    }
                )
        fixed_policy_meta = {
            "policy_version": fixed_policy_result.get("policy_version"),
            "policy_source_run_id": fixed_policy_result.get("source_run_id"),
            "policy_registry_path": str(fixed_policy_registry_path)
            if fixed_policy_registry_path is not None
            else None,
        }

    combo_metrics_rows = []
    filtered_map = {int(row["combo_id"]): row for row in filtered_rows}
    for row in baseline_rows:
        combo_id = int(row["combo_id"])
        filtered_row = filtered_map.get(combo_id, {})
        combo_metrics_rows.append(
            {
                "pred_batch": int(pred_batch),
                "combo_id": combo_id,
                "action_key": str(row["action_key"]),
                "fold_count": int(row["fold_count"]),
                "val_batches_per_fold": int(row["val_batches_per_fold"]),
                "train_batches_per_fold": int(row["train_batches_per_fold"]),
                "baseline_accuracy": row.get("accuracy"),
                "baseline_macro_f1": row.get("macro_f1"),
                "baseline_cross_direction_error": row.get("cross_direction_error"),
                "baseline_pred_rows": int(row.get("pred_rows", 0) or 0),
                "baseline_rank": int(baseline_rank_map.get(combo_id, 0)),
                "filtered_accuracy": filtered_row.get("filtered_accuracy", row.get("accuracy")),
                "filtered_macro_f1": filtered_row.get("filtered_macro_f1", row.get("macro_f1")),
                "filtered_cross_direction_error": filtered_row.get(
                    "filtered_cross_direction_error",
                    row.get("cross_direction_error"),
                ),
                "filtered_pred_rows": int(
                    filtered_row.get("filtered_pred_rows", row.get("pred_rows", 0) or 0) or 0
                ),
                "selection_applied": bool(combo_id in filtered_map),
                "apply_pruned_step": filtered_row.get("apply_pruned_step", False),
                "improved_step": filtered_row.get("improved_step", False),
                "selected_keep_count_request": filtered_row.get("selected_keep_count_request"),
                "n_features_used": filtered_row.get("n_features_used"),
            }
        )

    selected_ranked = _rank_stage1_rows(combo_metrics_rows, "filtered")
    selected_rank_map = {
        int(row["combo_id"]): idx for idx, row in enumerate(selected_ranked, start=1)
    }
    for row in combo_metrics_rows:
        row["filtered_rank"] = int(selected_rank_map.get(int(row["combo_id"]), 0))

    combo_metrics_df = _rows_to_df(combo_metrics_rows)
    baseline_predictions_df = _baseline_prediction_rows(
        combo_df=combo_df,
        pred_df=pred_df,
        pred_batch=int(pred_batch),
    )
    if selected_pred_df.is_empty():
        selected_pred_df = baseline_predictions_df.with_columns(
            pl.lit("selected_parity").alias("prediction_source")
        )

    baseline_winner = baseline_ranked[0] if baseline_ranked else None
    selected_winner = selected_ranked[0] if selected_ranked else None
    winner_changed = bool(
        baseline_winner is not None
        and selected_winner is not None
        and str(baseline_winner.get("action_key")) != str(selected_winner.get("action_key"))
    )

    summary_payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "timeframe": unit.timeframe,
        "target": unit.target,
        "feature_target": unit.feature_target,
        "pred_batch": int(pred_batch),
        "step_idx": int(step_idx),
        "execution_mode": str(selector_config.execution_mode),
        "selector_config": asdict(selector_config),
        "stage1_summary_path": str(stage1_dir / "stage1_step_summary.json"),
        "stage1_winner_combo_key": stage1_summary.get("winner_combo_key"),
        "baseline_winner": baseline_winner,
        "selected_winner": selected_winner,
        "winner_changed": bool(winner_changed),
        "combo_count": int(len(combo_metrics_rows)),
        "selection_applied_combo_count": int(
            sum(1 for row in combo_metrics_rows if bool(row.get("selection_applied")))
        ),
    }
    if fixed_policy_meta:
        summary_payload["fixed_policy"] = dict(fixed_policy_meta)

    combo_metrics_path = v2_dir / STAGE1_V2_STEP_ARTIFACTS["combo_metrics"]
    importance_path = v2_dir / STAGE1_V2_STEP_ARTIFACTS["feature_importance_steps"]
    selected_features_path = v2_dir / STAGE1_V2_STEP_ARTIFACTS["selected_features"]
    selector_fold_path = v2_dir / STAGE1_V2_STEP_ARTIFACTS["selector_fold_outputs"]
    baseline_pred_path = v2_dir / STAGE1_V2_STEP_ARTIFACTS["predictions_baseline"]
    selected_pred_path = v2_dir / STAGE1_V2_STEP_ARTIFACTS["predictions_selected"]
    summary_path = v2_dir / STAGE1_V2_STEP_ARTIFACTS["summary"]

    combo_metrics_df.sort(["baseline_rank", "combo_id"]).write_parquet(combo_metrics_path)
    importance_df.write_parquet(importance_path)
    selector_fold_df.write_parquet(selector_fold_path)
    baseline_predictions_df.write_parquet(baseline_pred_path)
    selected_pred_df.write_parquet(selected_pred_path)
    with open(selected_features_path, "w") as f:
        json.dump(selected_masks_payload, f, indent=2)
    with open(summary_path, "w") as f:
        json.dump(summary_payload, f, indent=2)

    progress_row = {
        "timeframe": unit.timeframe,
        "target": unit.target,
        "pred_batch": int(pred_batch),
        "step_idx": int(step_idx),
        "execution_mode": str(selector_config.execution_mode),
        "baseline_winner_action_key": (
            str(baseline_winner.get("action_key")) if baseline_winner else None
        ),
        "selected_winner_action_key": (
            str(selected_winner.get("action_key")) if selected_winner else None
        ),
        "baseline_winner_accuracy": (
            baseline_winner.get("baseline_accuracy") if baseline_winner else None
        ),
        "selected_winner_accuracy": (
            selected_winner.get("filtered_accuracy") if selected_winner else None
        ),
        "baseline_winner_macro_f1": (
            baseline_winner.get("baseline_macro_f1") if baseline_winner else None
        ),
        "selected_winner_macro_f1": (
            selected_winner.get("filtered_macro_f1") if selected_winner else None
        ),
        "baseline_winner_cross_direction_error": (
            baseline_winner.get("baseline_cross_direction_error") if baseline_winner else None
        ),
        "selected_winner_cross_direction_error": (
            selected_winner.get("filtered_cross_direction_error") if selected_winner else None
        ),
        "winner_changed": bool(winner_changed),
    }

    return {
        "summary": summary_payload,
        "artifacts": {
            "summary": str(summary_path),
            "combo_metrics": str(combo_metrics_path),
            "feature_importance_steps": str(importance_path),
            "selected_features": str(selected_features_path),
            "selector_fold_outputs": str(selector_fold_path),
            "predictions_baseline": str(baseline_pred_path),
            "predictions_selected": str(selected_pred_path),
        },
        "progress_row": progress_row,
        "baseline_vs_selected_row": dict(progress_row),
        "feature_importance_rows": feature_importance_rows,
        "feature_mask_rows": feature_mask_rows,
    }


__all__ = [
    "Stage1SelectorUnitConfig",
    "collect_stage1_v2_step_artifacts",
    "init_stage1_selector_state",
    "process_stage1_selector_step",
]
