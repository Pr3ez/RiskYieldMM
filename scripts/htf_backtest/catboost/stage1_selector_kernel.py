from __future__ import annotations

from typing import Any

import numpy as np
import polars as pl
from catboost import EFeaturesSelectionAlgorithm, EShapCalcType, Pool
from sklearn.metrics import f1_score

from .stage1_optimizer import fit_catboost_with_fallback_stage1


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


def _compute_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    *,
    n_classes: int,
    class_names: list[str],
) -> dict[str, float | None]:
    if y_true.size == 0:
        return {
            "accuracy": None,
            "macro_f1": None,
            "cross_direction_error": None,
        }
    up_idx, down_idx = _detect_direction_indices(class_names)
    return {
        "accuracy": float((y_true == y_pred).mean()),
        "macro_f1": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
        "cross_direction_error": _cross_direction_error(
            y_true, y_pred, up_indices=up_idx, down_indices=down_idx
        ),
    }


def _format_action_key(fold_count: int, val_batches: int, train_batches: int) -> str:
    return f"f{int(fold_count)}_v{int(val_batches)}_t{int(train_batches)}"


def _combo_key_from_row(row: dict[str, Any]) -> tuple[int, int, int]:
    return (
        int(row["fold_count"]),
        int(row["val_batches_per_fold"]),
        int(row["train_batches_per_fold"]),
    )


def _metric_value(metrics: dict[str, float | None], metric_name: str) -> float | None:
    val = metrics.get(metric_name)
    if val is None:
        return None
    try:
        return float(val)
    except Exception:
        return None


def _metric_direction(metric_name: str) -> str:
    metric_name = str(metric_name).strip().lower()
    return "minimize" if metric_name in {"log_loss", "cross_direction_error"} else "maximize"


def _is_better_metric(
    *,
    candidate: float | None,
    current_best: float | None,
    direction: str,
    min_improvement: float,
) -> bool:
    if candidate is None:
        return False
    if current_best is None:
        return True
    if str(direction) == "minimize":
        return float(candidate) < (float(current_best) - float(min_improvement))
    return float(candidate) > (float(current_best) + float(min_improvement))


def _list_combo_metrics_from_pred_payload(
    *,
    pred_payload: pl.DataFrame,
    combo_index: pl.DataFrame,
    allowed_combo_keys: set[tuple[int, int, int]] | None,
    selection_metric: str,
    selection_direction: str,
    n_classes: int,
    class_names: list[str],
) -> list[dict[str, Any]]:
    if pred_payload.is_empty() or combo_index.is_empty():
        return []

    complete_idx = combo_index.filter(pl.col("status") == "complete")
    if complete_idx.is_empty():
        return []

    metrics_rows = []
    for combo_key, grp in pred_payload.group_by("combo_id"):
        combo_id = int(combo_key[0] if isinstance(combo_key, tuple) else combo_key)
        combo_row = complete_idx.filter(pl.col("combo_id") == combo_id).head(1)
        if combo_row.is_empty():
            continue
        row = combo_row.to_dicts()[0]
        key = (
            int(row["fold_count"]),
            int(row["val_batches_per_fold"]),
            int(row["train_batches_per_fold"]),
        )
        if allowed_combo_keys and key not in allowed_combo_keys:
            continue
        y_true = grp["y_true"].to_numpy().astype(np.int32, copy=False)
        y_pred = grp["y_pred"].to_numpy().astype(np.int32, copy=False)
        metrics = _compute_metrics(
            y_true,
            y_pred,
            n_classes=n_classes,
            class_names=class_names,
        )
        metric_val = _metric_value(metrics, selection_metric)
        if metric_val is None:
            continue
        metrics_rows.append(
            {
                "combo_id": int(combo_id),
                "combo_key": key,
                "action_key": str(
                    row.get(
                        "action_key",
                        _format_action_key(
                            int(key[0]),
                            int(key[1]),
                            int(key[2]),
                        ),
                    )
                ),
                "fold_count": int(key[0]),
                "val_batches_per_fold": int(key[1]),
                "train_batches_per_fold": int(key[2]),
                "selection_metric": selection_metric,
                "selection_direction": selection_direction,
                "selection_value": float(metric_val),
                "accuracy": metrics["accuracy"],
                "macro_f1": metrics["macro_f1"],
                "cross_direction_error": metrics["cross_direction_error"],
                "pred_rows": int(len(y_true)),
            }
        )

    if not metrics_rows:
        return []
    if selection_direction == "minimize":
        metrics_rows.sort(key=lambda row: (float(row["selection_value"]), int(row["combo_id"])))
    else:
        metrics_rows.sort(
            key=lambda row: (-float(row["selection_value"]), int(row["combo_id"]))
        )
    return metrics_rows


def _resolve_shap_calc_type(shap_calc_type: str) -> EShapCalcType:
    token = str(shap_calc_type).strip().lower()
    mapping = {
        "regular": EShapCalcType.Regular,
        "approximate": EShapCalcType.Approximate,
        "exact": EShapCalcType.Exact,
    }
    if token not in mapping:
        raise ValueError(
            "selector_shap_calc_type must be one of: Regular, Approximate, Exact"
        )
    return mapping[token]


def _extract_selected_feature_names(
    selector_result: dict[str, Any],
    feature_names: list[str],
) -> list[str]:
    selected_names = selector_result.get("selected_features_names")
    if isinstance(selected_names, (list, tuple)) and selected_names:
        return list(dict.fromkeys(str(value) for value in selected_names))

    selected = selector_result.get("selected_features")
    if isinstance(selected, (list, tuple)) and selected:
        output: list[str] = []
        for value in selected:
            if isinstance(value, str):
                output.append(str(value))
                continue
            try:
                idx = int(value)
            except Exception:
                continue
            if 0 <= idx < len(feature_names):
                output.append(str(feature_names[idx]))
        if output:
            return list(dict.fromkeys(output))

    eliminated = selector_result.get("eliminated_features")
    if isinstance(eliminated, (list, tuple)):
        eliminated_idx = set()
        for value in eliminated:
            try:
                idx = int(value)
            except Exception:
                continue
            if 0 <= idx < len(feature_names):
                eliminated_idx.add(idx)
        keep = [
            str(feature_names[idx])
            for idx in range(len(feature_names))
            if idx not in eliminated_idx
        ]
        if keep:
            return keep

    return list(feature_names)


def _full_proba_and_pred(
    proba_raw: np.ndarray,
    classes: np.ndarray | None,
    n_classes: int,
) -> tuple[np.ndarray, np.ndarray]:
    proba_raw = np.asarray(proba_raw, dtype=np.float64)
    if proba_raw.ndim == 1:
        proba_raw = np.column_stack([1.0 - proba_raw, proba_raw])
    if proba_raw.ndim != 2:
        raise ValueError(f"Invalid probability output shape: {proba_raw.shape}")

    if classes is None:
        if proba_raw.shape[1] == int(n_classes):
            full = proba_raw
        else:
            full = np.full((proba_raw.shape[0], int(n_classes)), 1e-12, dtype=np.float64)
            cols = min(proba_raw.shape[1], int(n_classes))
            full[:, :cols] = proba_raw[:, :cols]
    else:
        classes_arr = np.asarray(classes, dtype=int).reshape(-1)
        full = np.full((proba_raw.shape[0], int(n_classes)), 1e-12, dtype=np.float64)
        for idx, class_id in enumerate(classes_arr):
            if 0 <= int(class_id) < int(n_classes):
                full[:, int(class_id)] = proba_raw[:, idx]

    row_sum = full.sum(axis=1, keepdims=True)
    row_sum[row_sum <= 0] = 1.0
    full = full / row_sum
    pred = np.argmax(full, axis=1).astype(np.int32)
    return full, pred


def _fit_catboost_model(
    *,
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_eval: np.ndarray,
    y_eval: np.ndarray,
    cb_params: dict,
    iterations: int,
):
    params = dict(cb_params)
    params["verbose"] = False
    params["allow_writing_files"] = False
    if len(np.unique(y_train)) <= 2 and int(np.max(y_train)) <= 1:
        params["loss_function"] = "Logloss"
        params["eval_metric"] = "Logloss"
    else:
        params["loss_function"] = "MultiClass"
        params["eval_metric"] = "MultiClass"
    model, _ = fit_catboost_with_fallback_stage1(
        params=params,
        iterations=int(max(10, iterations)),
        X_train=X_train,
        y_train=y_train,
        X_val=X_eval,
        y_val=y_eval,
    )
    return model


def _select_features_with_fallback(
    model,
    *,
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    n_features_total: int,
    n_features_select: int,
    selector_steps: int,
    selector_shap_mode: EShapCalcType,
) -> tuple[dict[str, Any], str]:
    train_pool = Pool(X_train, y_train.astype(np.int32))
    eval_pool = Pool(X_val, y_val.astype(np.int32))
    common_kwargs = dict(
        features_for_select=list(range(n_features_total)),
        num_features_to_select=int(n_features_select),
        steps=int(selector_steps),
        algorithm=EFeaturesSelectionAlgorithm.RecursiveByShapValues,
        shap_calc_type=selector_shap_mode,
        train_final_model=False,
        logging_level="Silent",
    )
    train_classes = set(np.unique(y_train).astype(int).tolist())
    eval_classes = set(np.unique(y_val).astype(int).tolist())
    use_eval = bool(eval_classes.issubset(train_classes))
    if use_eval:
        try:
            return (
                model.select_features(
                    train_pool,
                    eval_set=eval_pool,
                    **common_kwargs,
                ),
                "train_plus_eval",
            )
        except Exception as exc:
            msg = str(exc)
            if "contains class label" not in msg or "not present in the learn dataset" not in msg:
                raise
    return model.select_features(train_pool, **common_kwargs), "train_only"

