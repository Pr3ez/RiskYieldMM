"""RPF-native binary classification walk-forward runner."""

from __future__ import annotations

import argparse
import itertools
import json
import math
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from regression_feature_engineering.walkforward.ablation import select_ablation_features
from regression_feature_engineering.walkforward.config import load_clean_config
from regression_feature_engineering.walkforward.data import RPFDataContext, VALID_COL, resolve_context
from regression_feature_engineering.walkforward.policy import FROZEN_PANEL, FeaturePolicyConfig, select_features
from regression_feature_engineering.walkforward.reports import write_json, write_markdown, write_trials
from regression_feature_engineering.walkforward.windows import RPFWindow, read_windows
from scripts.project_paths import ensure_project_root_on_path


PROJECT_ROOT = ensure_project_root_on_path(Path(__file__))
OUTPUT_ROOT = PROJECT_ROOT / "test_output" / "rpf_clean_classification"
UP_EXTREME = "target_reg_distance_up_extreme_hvol_v2"
DOWN_EXTREME = "target_reg_distance_down_extreme_hvol_v2"
TARGET_BINARY_UP_2X_DOWN = "target_cls_extreme_up_ge_2x_down_hvol_v2"
TARGET_BINARY_DOWN_2X_UP = "target_cls_extreme_down_ge_2x_up_hvol_v2"


def main() -> int:
    args = _parse_args()
    config = load_clean_config(args.config)
    asset = str(args.asset or config.asset)
    root = str(args.root or config.root)
    target_col = str(args.target_col)
    positive_rule = positive_rule_description(target_col)
    context = resolve_context(project_root=PROJECT_ROOT, asset=asset, root=root, target_col=UP_EXTREME)
    run_root = _run_root(args, target_col)
    run_root.mkdir(parents=True, exist_ok=True)
    print(
        "[rpf-cls] start "
        f"asset={asset} root={root} target={target_col} run={run_root}",
        flush=True,
    )
    windows = read_windows(Path(args.base_run) / "frozen_windows.parquet")
    n_steps = int(args.n_steps)
    windows = windows[-n_steps:] if n_steps > 0 else windows
    if not windows:
        raise ValueError("No frozen windows to run")
    feature_columns = select_ablation_features(context.manifest.feature_columns, str(args.feature_ablation))
    policy = FeaturePolicyConfig()
    if args.frozen_panel_path:
        policy = replace(
            policy,
            policy=FROZEN_PANEL,
            frozen_panel_path=str(args.frozen_panel_path),
            min_selected_features=1,
        )
    trials: list[dict[str, Any]] = []
    window_rows: list[dict[str, Any]] = []
    thresholds = _threshold_values(args)
    choices = _model_choice_grid(args)
    for trial_number, model_updates in enumerate(choices[: int(args.max_configs)]):
        print(
            "[rpf-cls] trial_start "
            f"trial={trial_number} windows={len(windows)} features={_feature_label(policy, len(feature_columns))} "
            f"it={model_updates['iterations']} depth={model_updates['depth']} lr={model_updates['learning_rate']}",
            flush=True,
        )
        try:
            payload = run_classification_windows(
                context=context,
                windows=windows,
                target_col=target_col,
                feature_columns=feature_columns,
                policy=policy,
                model_updates=model_updates,
                task_type=str(args.task_type),
                thread_count=int(args.thread_count),
                threshold_mode=str(args.threshold_mode),
                fixed_threshold=float(args.decision_threshold),
                threshold_grid=thresholds,
                objective_metric=str(args.objective_metric),
                fp_cost=float(args.fp_cost),
                fn_cost=float(args.fn_cost),
                tp_reward=float(args.tp_reward),
                fbeta_beta=float(args.fbeta_beta),
                min_validation_recall=float(args.min_validation_recall),
                min_validation_precision=float(args.min_validation_precision),
                min_validation_predicted_positive_rate=float(args.min_validation_predicted_positive_rate),
                max_validation_false_positive_rate=float(args.max_validation_false_positive_rate),
            )
            status = "ok"
            if payload["prediction_metrics"]["prob_unique"] <= int(args.min_prediction_unique):
                status = "rejected:low_prediction_unique"
            if float(payload["prediction_metrics"]["prob_std"] or 0.0) <= float(args.min_prediction_std):
                status = "rejected:low_prediction_std"
            row = {
                "trial_number": trial_number,
                "status": status,
                "objective_metric": payload["objective_metric"],
                "objective_direction": payload["objective_direction"],
                "objective_value": payload["objective_value"],
                "feature_ablation": str(args.feature_ablation),
                "feature_policy": policy.policy,
                "threshold_mode": str(args.threshold_mode),
                "selected_threshold": payload["selected_threshold"],
                "threshold_constraints_pass": payload["threshold_constraints_pass"],
                "threshold_constraints_reason": payload["threshold_constraints_reason"],
                "fp_cost": float(args.fp_cost),
                "fn_cost": float(args.fn_cost),
                "tp_reward": float(args.tp_reward),
                "fbeta_beta": float(args.fbeta_beta),
                **model_updates,
                **_flatten(payload["validation_metrics"], "validation"),
                **_flatten(payload["prediction_metrics"], "prediction"),
                "selected_feature_count_min": payload["selected_feature_count_min"],
                "selected_feature_count_mean": payload["selected_feature_count_mean"],
            }
            trials.append(row)
            for window_row in payload["window_metrics"]:
                window_rows.append({"trial_number": trial_number, **window_row})
            print(
                "[rpf-cls] trial_done "
                f"trial={trial_number} status={status} val_logloss={row['validation_logloss']:.6f} "
                f"val_auc={row['validation_auc']} pred_auc={row['prediction_auc']} "
                f"pred_bal_acc={row['prediction_balanced_accuracy']}",
                flush=True,
            )
        except Exception as exc:
            row = {
                "trial_number": trial_number,
                "status": "error",
                "objective_metric": str(args.objective_metric),
                "objective_direction": "minimize",
                "objective_value": 1e9,
                "error": str(exc),
                "feature_ablation": str(args.feature_ablation),
                "feature_policy": policy.policy,
                **model_updates,
            }
            trials.append(row)
            print(f"[rpf-cls] trial_error trial={trial_number} error={exc}", flush=True)
    best = _best_trial(trials)
    write_trials(run_root / "trials.parquet", trials)
    _write_rows_parquet(run_root / "window_metrics.parquet", window_rows)
    write_json(
        run_root / "best_config.json",
        {
            "target_col": target_col,
            "positive_rule": positive_rule,
            "asset": asset,
            "root": root,
            "feature_ablation": str(args.feature_ablation),
            "feature_policy": policy.policy,
            "frozen_panel_path": None if args.frozen_panel_path is None else str(args.frozen_panel_path),
            "threshold_mode": str(args.threshold_mode),
            "objective_metric": str(args.objective_metric),
            "fp_cost": float(args.fp_cost),
            "fn_cost": float(args.fn_cost),
            "tp_reward": float(args.tp_reward),
            "best": best,
        },
    )
    write_markdown(
        run_root / "report.md",
        title="RPF Binary Classification Walk-Forward",
        sections={
            "Target": {
                "target_col": target_col,
                "positive_rule": positive_rule,
            },
            "Best": best or {},
            "Run": {
                "asset": asset,
                "root": root,
                "windows": len(windows),
                "feature_ablation": str(args.feature_ablation),
                "feature_policy": policy.policy,
                "threshold_mode": str(args.threshold_mode),
                "objective_metric": str(args.objective_metric),
                "fp_cost": float(args.fp_cost),
                "fn_cost": float(args.fn_cost),
                "tp_reward": float(args.tp_reward),
            },
        },
    )
    print(f"[rpf-cls] done run={run_root}", flush=True)
    return 0


def run_classification_windows(
    *,
    context: RPFDataContext,
    windows: list[RPFWindow],
    target_col: str,
    feature_columns: tuple[str, ...],
    policy: FeaturePolicyConfig,
    model_updates: dict[str, Any],
    task_type: str,
    thread_count: int,
    threshold_mode: str,
    fixed_threshold: float,
    threshold_grid: tuple[float, ...],
    objective_metric: str,
    fp_cost: float,
    fn_cost: float,
    tp_reward: float,
    fbeta_beta: float,
    min_validation_recall: float,
    min_validation_precision: float,
    min_validation_predicted_positive_rate: float,
    max_validation_false_positive_rate: float,
) -> dict[str, Any]:
    val_true: list[np.ndarray] = []
    val_prob: list[np.ndarray] = []
    pred_true: list[np.ndarray] = []
    pred_prob: list[np.ndarray] = []
    selected_counts: list[int] = []
    window_payloads: list[dict[str, Any]] = []
    for window in windows:
        train = load_joined_classification_batches(context, window.train_batch_ids, feature_columns=feature_columns, target_col=target_col)
        val = load_joined_classification_batches(context, window.val_batch_ids, feature_columns=feature_columns, target_col=target_col)
        pred = load_joined_classification_batches(context, (window.pred_batch_id,), feature_columns=feature_columns, target_col=target_col)
        policy_result = select_features(train, target_col=target_col, feature_columns=feature_columns, config=policy)
        selected = policy_result.selected_features
        selected_counts.append(len(selected))
        X_train, y_train = _classification_numpy(train, target_col=target_col, features=selected)
        X_val, y_val = _classification_numpy(val, target_col=target_col, features=selected)
        X_pred, y_pred = _classification_numpy(pred, target_col=target_col, features=selected)
        if len(np.unique(y_train)) < 2:
            raise ValueError(f"Training window has one class only: step={window.step_idx}")
        model = fit_classifier(
            X_train,
            y_train,
            X_val,
            y_val,
            model_updates=model_updates,
            task_type=task_type,
            thread_count=thread_count,
        )
        val_p = _positive_probability(model, X_val)
        pred_p = _positive_probability(model, X_pred)
        val_true.append(y_val)
        val_prob.append(val_p)
        pred_true.append(y_pred)
        pred_prob.append(pred_p)
        window_payloads.append(
            {
                "step_idx": int(window.step_idx),
                "pred_batch_id": int(window.pred_batch_id),
                "selected_feature_count": len(selected),
                "train_rows": int(len(y_train)),
                "val_rows": int(len(y_val)),
                "pred_rows": int(len(y_pred)),
                "train_positive_rate": float(np.mean(y_train)),
                "y_val": y_val,
                "val_prob": val_p,
                "y_pred": y_pred,
                "pred_prob": pred_p,
                **model_diagnostics(model),
            }
        )
    y_val_all = np.concatenate(val_true)
    val_prob_all = np.concatenate(val_prob)
    y_pred_all = np.concatenate(pred_true)
    pred_prob_all = np.concatenate(pred_prob)
    threshold_result = select_decision_threshold(
        y_val_all,
        val_prob_all,
        threshold_mode=threshold_mode,
        fixed_threshold=fixed_threshold,
        threshold_grid=threshold_grid,
        objective_metric=objective_metric,
        fp_cost=fp_cost,
        fn_cost=fn_cost,
        tp_reward=tp_reward,
        fbeta_beta=fbeta_beta,
        min_recall=min_validation_recall,
        min_precision=min_validation_precision,
        min_predicted_positive_rate=min_validation_predicted_positive_rate,
        max_false_positive_rate=max_validation_false_positive_rate,
    )
    threshold = float(threshold_result["threshold"])
    window_metrics: list[dict[str, Any]] = []
    for payload in window_payloads:
        val_m = binary_metrics(
            payload.pop("y_val"),
            payload.pop("val_prob"),
            threshold=threshold,
            fp_cost=fp_cost,
            fn_cost=fn_cost,
            tp_reward=tp_reward,
            fbeta_beta=fbeta_beta,
        )
        pred_m = binary_metrics(
            payload.pop("y_pred"),
            payload.pop("pred_prob"),
            threshold=threshold,
            fp_cost=fp_cost,
            fn_cost=fn_cost,
            tp_reward=tp_reward,
            fbeta_beta=fbeta_beta,
        )
        window_metrics.append(
            {
                **payload,
                "selected_threshold": threshold,
                **_flatten(val_m, "validation"),
                **_flatten(pred_m, "prediction"),
            }
        )
    validation_metrics = binary_metrics(
        y_val_all,
        val_prob_all,
        threshold=threshold,
        fp_cost=fp_cost,
        fn_cost=fn_cost,
        tp_reward=tp_reward,
        fbeta_beta=fbeta_beta,
    )
    prediction_metrics = binary_metrics(
        y_pred_all,
        pred_prob_all,
        threshold=threshold,
        fp_cost=fp_cost,
        fn_cost=fn_cost,
        tp_reward=tp_reward,
        fbeta_beta=fbeta_beta,
    )
    objective_direction, objective_value = classification_objective(validation_metrics, objective_metric)
    if not threshold_result["constraints_pass"]:
        objective_value = 1e9 if objective_direction == "minimize" else -1e9
    return {
        "validation_metrics": validation_metrics,
        "prediction_metrics": prediction_metrics,
        "objective_metric": objective_metric,
        "objective_direction": objective_direction,
        "objective_value": objective_value,
        "selected_threshold": threshold,
        "threshold_constraints_pass": bool(threshold_result["constraints_pass"]),
        "threshold_constraints_reason": str(threshold_result["constraints_reason"]),
        "selected_feature_count_min": min(selected_counts) if selected_counts else 0,
        "selected_feature_count_mean": float(np.mean(selected_counts)) if selected_counts else 0.0,
        "window_metrics": window_metrics,
    }


def load_joined_classification_batches(
    context: RPFDataContext,
    batch_ids: tuple[int, ...] | list[int],
    *,
    feature_columns: tuple[str, ...],
    target_col: str,
) -> pl.DataFrame:
    frames: list[pl.DataFrame] = []
    for batch_id in sorted({int(value) for value in batch_ids}):
        feature_path = context.feature_root / f"batch_{batch_id:04d}.parquet"
        label_path = context.label_root / f"batch_{batch_id:04d}.parquet"
        features = pl.read_parquet(feature_path, columns=["timestamp", "batch_id", *feature_columns])
        labels = pl.read_parquet(label_path, columns=["timestamp", "batch_id", VALID_COL, UP_EXTREME, DOWN_EXTREME])
        joined = (
            labels.join(features, on=["timestamp", "batch_id"], how="inner")
            .filter(
                pl.col(VALID_COL).fill_null(False)
                & pl.col(UP_EXTREME).is_not_null()
                & pl.col(DOWN_EXTREME).is_not_null()
                & pl.col(UP_EXTREME).is_finite()
                & pl.col(DOWN_EXTREME).is_finite()
            )
            .with_columns(binary_target_expr(target_col))
            .drop(VALID_COL)
        )
        frames.append(joined)
    out = pl.concat(frames, how="vertical") if frames else pl.DataFrame()
    if out.is_empty():
        raise ValueError(f"Joined RPF classification batches are empty: {batch_ids}")
    return out.sort(["batch_id", "timestamp"])


def binary_target_expr(target_col: str = TARGET_BINARY_UP_2X_DOWN) -> pl.Expr:
    if target_col == TARGET_BINARY_UP_2X_DOWN:
        expr = (pl.col(UP_EXTREME) > 0.0) & (pl.col(UP_EXTREME) >= 2.0 * pl.col(DOWN_EXTREME))
    elif target_col == TARGET_BINARY_DOWN_2X_UP:
        expr = (pl.col(DOWN_EXTREME) > 0.0) & (pl.col(DOWN_EXTREME) >= 2.0 * pl.col(UP_EXTREME))
    else:
        raise ValueError(f"Unsupported RPF binary target: {target_col}")
    return expr.cast(pl.Int8).alias(target_col)


def positive_rule_description(target_col: str) -> str:
    if target_col == TARGET_BINARY_UP_2X_DOWN:
        return "up_extreme > 0 and up_extreme >= 2 * down_extreme"
    if target_col == TARGET_BINARY_DOWN_2X_UP:
        return "down_extreme > 0 and down_extreme >= 2 * up_extreme"
    raise ValueError(f"Unsupported RPF binary target: {target_col}")


def fit_classifier(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    *,
    model_updates: dict[str, Any],
    task_type: str,
    thread_count: int,
) -> Any:
    try:
        from catboost import CatBoostClassifier
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("CatBoost is required for RPF classification") from exc
    params = {
        "loss_function": "Logloss",
        "eval_metric": "Logloss",
        "iterations": int(model_updates["iterations"]),
        "depth": int(model_updates["depth"]),
        "learning_rate": float(model_updates["learning_rate"]),
        "l2_leaf_reg": float(model_updates["l2_leaf_reg"]),
        "random_seed": 42,
        "allow_writing_files": False,
        "verbose": False,
        "thread_count": int(thread_count),
        "task_type": str(task_type).upper(),
        "has_time": True,
        "od_type": "Iter",
        "od_wait": int(model_updates["od_wait"]),
    }
    if str(task_type).upper() == "GPU":
        params["devices"] = "0"
    model = CatBoostClassifier(**params)
    try:
        model.fit(
            X_train,
            y_train,
            eval_set=(X_val, y_val),
            use_best_model=True,
            early_stopping_rounds=int(model_updates["early_stopping_rounds"]),
            verbose=False,
        )
    except Exception:
        if params["task_type"] != "GPU":
            raise
        params["task_type"] = "CPU"
        params.pop("devices", None)
        model = CatBoostClassifier(**params)
        model.fit(
            X_train,
            y_train,
            eval_set=(X_val, y_val),
            use_best_model=True,
            early_stopping_rounds=int(model_updates["early_stopping_rounds"]),
            verbose=False,
        )
    return model


def binary_metrics(
    y_true: np.ndarray,
    prob: np.ndarray,
    *,
    threshold: float = 0.5,
    fp_cost: float = 1.0,
    fn_cost: float = 1.0,
    tp_reward: float = 0.0,
    fbeta_beta: float = 1.0,
) -> dict[str, Any]:
    y_true = np.asarray(y_true, dtype=int)
    prob = np.asarray(prob, dtype=float)
    mask = np.isfinite(prob)
    y_true = y_true[mask]
    prob = np.clip(prob[mask], 1e-9, 1.0 - 1e-9)
    pred = (prob >= float(threshold)).astype(int)
    positives = y_true == 1
    negatives = y_true == 0
    tp = int(np.sum((pred == 1) & positives))
    tn = int(np.sum((pred == 0) & negatives))
    fp = int(np.sum((pred == 1) & negatives))
    fn = int(np.sum((pred == 0) & positives))
    tpr = _safe_div(tp, tp + fn)
    tnr = _safe_div(tn, tn + fp)
    precision = _safe_div(tp, tp + fp)
    recall = tpr
    f1 = None if precision is None or recall is None or precision + recall == 0 else float(2 * precision * recall / (precision + recall))
    beta_sq = float(fbeta_beta) ** 2
    fbeta = (
        None
        if precision is None or recall is None or (beta_sq * precision + recall) == 0
        else float((1.0 + beta_sq) * precision * recall / (beta_sq * precision + recall))
    )
    false_positive_rate = _safe_div(fp, fp + tn)
    false_negative_rate = _safe_div(fn, fn + tp)
    false_discovery_rate = _safe_div(fp, fp + tp)
    decision_cost = float(fp_cost * fp + fn_cost * fn - tp_reward * tp)
    decision_cost_per_row = None if len(y_true) == 0 else float(decision_cost / len(y_true))
    utility = float(tp_reward * tp - fp_cost * fp - fn_cost * fn)
    return {
        "rows": int(len(y_true)),
        "threshold": float(threshold),
        "positive_rate": float(np.mean(y_true)) if len(y_true) else None,
        "predicted_positive_rate": float(np.mean(pred)) if len(pred) else None,
        "prob_mean": float(np.mean(prob)) if len(prob) else None,
        "prob_std": float(np.std(prob)) if len(prob) else None,
        "prob_unique": int(len(np.unique(np.round(prob, 8)))) if len(prob) else 0,
        "accuracy": float(np.mean(pred == y_true)) if len(y_true) else None,
        "balanced_accuracy": None if tpr is None or tnr is None else float((tpr + tnr) / 2.0),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "fbeta": fbeta,
        "false_positive_rate": false_positive_rate,
        "false_negative_rate": false_negative_rate,
        "false_discovery_rate": false_discovery_rate,
        "specificity": tnr,
        "decision_cost": decision_cost,
        "decision_cost_per_row": decision_cost_per_row,
        "utility": utility,
        "utility_per_row": None if len(y_true) == 0 else float(utility / len(y_true)),
        "logloss": float(-np.mean(y_true * np.log(prob) + (1 - y_true) * np.log(1 - prob))) if len(y_true) else None,
        "brier": float(np.mean((prob - y_true) ** 2)) if len(y_true) else None,
        "auc": _auc_rank(y_true, prob),
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
    }


def select_decision_threshold(
    y_true: np.ndarray,
    prob: np.ndarray,
    *,
    threshold_mode: str,
    fixed_threshold: float,
    threshold_grid: tuple[float, ...],
    objective_metric: str,
    fp_cost: float,
    fn_cost: float,
    tp_reward: float,
    fbeta_beta: float,
    min_recall: float,
    min_precision: float,
    min_predicted_positive_rate: float,
    max_false_positive_rate: float,
) -> dict[str, Any]:
    if threshold_mode == "fixed":
        metrics = binary_metrics(
            y_true,
            prob,
            threshold=fixed_threshold,
            fp_cost=fp_cost,
            fn_cost=fn_cost,
            tp_reward=tp_reward,
            fbeta_beta=fbeta_beta,
        )
        return {
            "threshold": float(fixed_threshold),
            "constraints_pass": _threshold_constraints_pass(
                metrics,
                min_recall=min_recall,
                min_precision=min_precision,
                min_predicted_positive_rate=min_predicted_positive_rate,
                max_false_positive_rate=max_false_positive_rate,
            ),
            "constraints_reason": _threshold_constraints_reason(
                metrics,
                min_recall=min_recall,
                min_precision=min_precision,
                min_predicted_positive_rate=min_predicted_positive_rate,
                max_false_positive_rate=max_false_positive_rate,
            ),
            "metrics": metrics,
        }
    if threshold_mode != "validation_sweep":
        raise ValueError(f"Unsupported threshold mode: {threshold_mode}")
    candidates: list[dict[str, Any]] = []
    for threshold in threshold_grid:
        metrics = binary_metrics(
            y_true,
            prob,
            threshold=threshold,
            fp_cost=fp_cost,
            fn_cost=fn_cost,
            tp_reward=tp_reward,
            fbeta_beta=fbeta_beta,
        )
        direction, value = classification_objective(metrics, objective_metric)
        constraints_pass = _threshold_constraints_pass(
            metrics,
            min_recall=min_recall,
            min_precision=min_precision,
            min_predicted_positive_rate=min_predicted_positive_rate,
            max_false_positive_rate=max_false_positive_rate,
        )
        candidates.append(
            {
                "threshold": float(threshold),
                "metrics": metrics,
                "objective_direction": direction,
                "objective_value": value,
                "constraints_pass": constraints_pass,
                "constraints_reason": _threshold_constraints_reason(
                    metrics,
                    min_recall=min_recall,
                    min_precision=min_precision,
                    min_predicted_positive_rate=min_predicted_positive_rate,
                    max_false_positive_rate=max_false_positive_rate,
                ),
            }
        )
    if not candidates:
        raise ValueError("Threshold grid is empty")
    passing = [candidate for candidate in candidates if candidate["constraints_pass"]]
    pool = passing if passing else candidates
    direction = str(pool[0]["objective_direction"])
    key = lambda candidate: float(candidate["objective_value"])
    best = min(pool, key=key) if direction == "minimize" else max(pool, key=key)
    if not passing:
        best = {**best, "constraints_pass": False, "constraints_reason": "no_threshold_satisfied_constraints"}
    return best


def classification_objective(metrics: dict[str, Any], objective_metric: str) -> tuple[str, float]:
    metric = str(objective_metric)
    if metric == "validation_logloss":
        return "minimize", _none_to_bad(metrics.get("logloss"), minimize=True)
    if metric == "validation_decision_cost":
        return "minimize", _none_to_bad(metrics.get("decision_cost_per_row"), minimize=True)
    if metric == "validation_false_positive_rate":
        return "minimize", _none_to_bad(metrics.get("false_positive_rate"), minimize=True)
    if metric == "validation_precision":
        return "maximize", _none_to_bad(metrics.get("precision"), minimize=False)
    if metric == "validation_fbeta":
        return "maximize", _none_to_bad(metrics.get("fbeta"), minimize=False)
    if metric == "validation_balanced_accuracy":
        return "maximize", _none_to_bad(metrics.get("balanced_accuracy"), minimize=False)
    raise ValueError(f"Unsupported classification objective metric: {objective_metric}")


def _threshold_constraints_pass(
    metrics: dict[str, Any],
    *,
    min_recall: float,
    min_precision: float,
    min_predicted_positive_rate: float,
    max_false_positive_rate: float,
) -> bool:
    return _threshold_constraints_reason(
        metrics,
        min_recall=min_recall,
        min_precision=min_precision,
        min_predicted_positive_rate=min_predicted_positive_rate,
        max_false_positive_rate=max_false_positive_rate,
    ) == "pass"


def _threshold_constraints_reason(
    metrics: dict[str, Any],
    *,
    min_recall: float,
    min_precision: float,
    min_predicted_positive_rate: float,
    max_false_positive_rate: float,
) -> str:
    recall = metrics.get("recall")
    precision = metrics.get("precision")
    predicted_positive_rate = metrics.get("predicted_positive_rate")
    false_positive_rate = metrics.get("false_positive_rate")
    if float(min_recall) > 0.0 and (recall is None or float(recall) < float(min_recall)):
        return "low_recall"
    if float(min_precision) > 0.0 and (precision is None or float(precision) < float(min_precision)):
        return "low_precision"
    if float(min_predicted_positive_rate) > 0.0 and (
        predicted_positive_rate is None or float(predicted_positive_rate) < float(min_predicted_positive_rate)
    ):
        return "low_predicted_positive_rate"
    if float(max_false_positive_rate) < 1.0 and (
        false_positive_rate is None or float(false_positive_rate) > float(max_false_positive_rate)
    ):
        return "high_false_positive_rate"
    return "pass"


def _none_to_bad(value: Any, *, minimize: bool) -> float:
    if value is None:
        return 1e9 if minimize else -1e9
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 1e9 if minimize else -1e9
    if not math.isfinite(number):
        return 1e9 if minimize else -1e9
    return number


def model_diagnostics(model: Any) -> dict[str, int | None]:
    best_iteration = None
    get_best_iteration = getattr(model, "get_best_iteration", None)
    if callable(get_best_iteration):
        value = get_best_iteration()
        best_iteration = None if value is None else int(value)
    tree_count = getattr(model, "tree_count_", None)
    return {
        "model_best_iteration": best_iteration,
        "model_tree_count": None if tree_count is None else int(tree_count),
    }


def _classification_numpy(frame: pl.DataFrame, *, target_col: str, features: tuple[str, ...]) -> tuple[np.ndarray, np.ndarray]:
    model_frame = frame.select([target_col, *features]).drop_nulls([target_col, *features])
    X = model_frame.select(features).to_numpy().astype("float64")
    y = model_frame[target_col].to_numpy().astype("int64")
    mask = np.isfinite(X).all(axis=1)
    return X[mask], y[mask]


def _positive_probability(model: Any, X: np.ndarray) -> np.ndarray:
    proba = np.asarray(model.predict_proba(X), dtype=float)
    return proba[:, 1]


def _auc_rank(y_true: np.ndarray, score: np.ndarray) -> float | None:
    y_true = np.asarray(y_true, dtype=int)
    score = np.asarray(score, dtype=float)
    pos = y_true == 1
    neg = y_true == 0
    n_pos = int(pos.sum())
    n_neg = int(neg.sum())
    if n_pos == 0 or n_neg == 0:
        return None
    ranks = _rankdata_average(score)
    rank_sum_pos = float(ranks[pos].sum())
    return float((rank_sum_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))


def _rankdata_average(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=float)
    sorted_values = values[order]
    start = 0
    while start < len(values):
        end = start + 1
        while end < len(values) and sorted_values[end] == sorted_values[start]:
            end += 1
        rank = (start + end - 1) / 2.0 + 1.0
        ranks[order[start:end]] = rank
        start = end
    return ranks


def _safe_div(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    return float(numerator / denominator)


def _flatten(metrics: dict[str, Any], prefix: str) -> dict[str, Any]:
    return {f"{prefix}_{key}": value for key, value in metrics.items()}


def _best_trial(trials: list[dict[str, Any]]) -> dict[str, Any] | None:
    ok_trials = [trial for trial in trials if str(trial.get("status", "")).startswith("ok")]
    pool = ok_trials or trials
    if not pool:
        return None
    direction = str(pool[0].get("objective_direction") or "minimize")
    key = lambda row: _none_to_bad(row.get("objective_value"), minimize=(direction == "minimize"))
    return min(pool, key=key) if direction == "minimize" else max(pool, key=key)


def _model_choice_grid(args: argparse.Namespace) -> list[dict[str, Any]]:
    keys = (
        ("iterations", _parse_ints(args.iterations_choices)),
        ("depth", _parse_ints(args.depth_choices)),
        ("learning_rate", _parse_floats(args.learning_rate_choices)),
        ("l2_leaf_reg", _parse_floats(args.l2_leaf_reg_choices)),
        ("early_stopping_rounds", _parse_ints(args.early_stopping_rounds_choices)),
        ("od_wait", _parse_ints(args.od_wait_choices)),
    )
    return [dict(zip((key for key, _ in keys), values)) for values in itertools.product(*(values for _, values in keys))]


def _parse_ints(raw: str) -> list[int]:
    return [int(value.strip()) for value in str(raw).split(",") if value.strip()]


def _parse_floats(raw: str) -> list[float]:
    return [float(value.strip()) for value in str(raw).split(",") if value.strip()]


def _threshold_values(args: argparse.Namespace) -> tuple[float, ...]:
    if str(args.threshold_mode) == "fixed":
        return (float(args.decision_threshold),)
    values = tuple(sorted(set(_parse_floats(str(args.threshold_grid)))))
    if not values:
        raise ValueError("--threshold-grid produced no thresholds")
    bad = [value for value in values if value <= 0.0 or value >= 1.0]
    if bad:
        raise ValueError(f"Thresholds must be between 0 and 1 exclusive: {bad}")
    return values


def _write_rows_parquet(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        pl.DataFrame(rows, infer_schema_length=None).write_parquet(path)
    else:
        pl.DataFrame().write_parquet(path)


def _feature_label(policy: FeaturePolicyConfig, feature_count: int) -> str:
    return f"frozen_panel:{policy.frozen_panel_path}" if policy.policy == FROZEN_PANEL else str(feature_count)


def _run_root(args: argparse.Namespace, target_col: str) -> Path:
    now = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    target_slug = target_col.replace("target_", "")[:44]
    return Path(args.output_dir) / f"{now}_classification_{target_slug}"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run RPF binary classification walk-forward.")
    parser.add_argument("--asset", default=None)
    parser.add_argument("--root", default=None)
    parser.add_argument("--target-col", default=TARGET_BINARY_UP_2X_DOWN)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--base-run", type=Path, required=True)
    parser.add_argument("--feature-ablation", default="all")
    parser.add_argument("--frozen-panel-path", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--n-steps", type=int, default=15)
    parser.add_argument("--max-configs", type=int, default=12)
    parser.add_argument("--task-type", choices=["CPU", "GPU"], default="CPU")
    parser.add_argument("--thread-count", type=int, default=-1)
    parser.add_argument("--iterations-choices", default="400,800")
    parser.add_argument("--depth-choices", default="2,3")
    parser.add_argument("--learning-rate-choices", default="0.01,0.02")
    parser.add_argument("--l2-leaf-reg-choices", default="10,30")
    parser.add_argument("--early-stopping-rounds-choices", default="100")
    parser.add_argument("--od-wait-choices", default="100")
    parser.add_argument("--min-prediction-unique", type=int, default=10)
    parser.add_argument("--min-prediction-std", type=float, default=1e-6)
    parser.add_argument(
        "--objective-metric",
        choices=[
            "validation_logloss",
            "validation_decision_cost",
            "validation_false_positive_rate",
            "validation_precision",
            "validation_fbeta",
            "validation_balanced_accuracy",
        ],
        default="validation_logloss",
    )
    parser.add_argument("--threshold-mode", choices=["fixed", "validation_sweep"], default="fixed")
    parser.add_argument("--decision-threshold", type=float, default=0.5)
    parser.add_argument(
        "--threshold-grid",
        default="0.05,0.10,0.15,0.20,0.25,0.30,0.35,0.40,0.45,0.50,0.55,0.60,0.65,0.70,0.75,0.80,0.85,0.90,0.95",
    )
    parser.add_argument("--fp-cost", type=float, default=1.0)
    parser.add_argument("--fn-cost", type=float, default=1.0)
    parser.add_argument("--tp-reward", type=float, default=0.0)
    parser.add_argument("--fbeta-beta", type=float, default=0.5)
    parser.add_argument("--min-validation-recall", type=float, default=0.0)
    parser.add_argument("--min-validation-precision", type=float, default=0.0)
    parser.add_argument("--min-validation-predicted-positive-rate", type=float, default=0.0)
    parser.add_argument("--max-validation-false-positive-rate", type=float, default=1.0)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
