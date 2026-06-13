"""Clean RPF-native staged walk-forward optimizer."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from regression_feature_engineering.walkforward.config import (
    CleanWalkForwardConfig,
    config_to_dict,
    load_clean_config,
    merge_config,
)
from regression_feature_engineering.walkforward.data import (
    RPFDataContext,
    build_batch_index,
    build_label_window_index,
    frame_to_numpy,
    load_joined_batches,
    resolve_context,
)
from regression_feature_engineering.walkforward.ablation import FAMILY_PREFIXES, select_ablation_features
from regression_feature_engineering.walkforward.metrics import (
    objective_score,
    prediction_collapse_reason,
    regression_metrics,
)
from regression_feature_engineering.walkforward.model import (
    CatBoostConfig,
    fit_catboost,
    model_diagnostics,
)
from regression_feature_engineering.walkforward.policy import (
    ALL_MANIFEST_FEATURES,
    FROZEN_PANEL,
    FeaturePolicyConfig,
    apply_clip_bounds,
    select_features,
)
from regression_feature_engineering.walkforward.reports import (
    append_event,
    write_json,
    write_markdown,
    write_stage_status,
    write_trials,
)
from regression_feature_engineering.walkforward.windows import (
    RPFWindow,
    build_windows,
    read_windows,
    windows_to_frame,
    write_windows,
)
from scripts.project_paths import ensure_project_root_on_path


PROJECT_ROOT = ensure_project_root_on_path(Path(__file__))
OUTPUT_ROOT = PROJECT_ROOT / "test_output" / "rpf_clean_walkforward"
STAGES = (
    "readiness",
    "baseline_probe",
    "geometry",
    "core_model",
    "sampling",
    "confirmation",
)


def main() -> int:
    args = _parse_args()
    config = load_clean_config(args.config)
    config = merge_config(
        config,
        asset=args.asset or config.asset,
        root=args.root or config.root,
        target_col=args.target_col or config.target_col,
        feature_ablation=args.feature_ablation or config.feature_ablation,
        n_steps=int(args.n_steps if args.n_steps is not None else config.n_steps),
    )
    if args.frozen_panel_path:
        config = merge_config(
            config,
            feature_policy=FROZEN_PANEL,
            policy={
                **asdict(config.policy),
                "policy": FROZEN_PANEL,
                "frozen_panel_path": str(Path(args.frozen_panel_path)),
                "min_selected_features": 1,
            },
        )
    run_root = _run_root(args, config)
    run_root.mkdir(parents=True, exist_ok=True)
    events = run_root / "events.jsonl"
    _log(
        "stage_start",
        stage=args.stage,
        asset=config.asset,
        root=config.root,
        target=config.target_col,
        run=str(run_root),
    )
    append_event(events, "stage_start", stage=args.stage, config=config_to_dict(config), run_root=str(run_root))
    context = resolve_context(
        project_root=PROJECT_ROOT,
        asset=config.asset,
        root=config.root,
        target_col=config.target_col,
    )
    if args.stage == "readiness":
        run_readiness(context, config, run_root, events, args)
    else:
        if args.base_run is None:
            raise ValueError("--base-run is required for non-readiness clean RPF stages")
        run_optuna_stage(context, config, run_root, events, args)
    append_event(events, "stage_done", stage=args.stage, run_root=str(run_root))
    _log("stage_done", stage=args.stage, run=str(run_root))
    return 0


def run_readiness(
    context: RPFDataContext,
    config: CleanWalkForwardConfig,
    run_root: Path,
    events: Path,
    args: argparse.Namespace,
) -> dict[str, Any]:
    run_root.mkdir(parents=True, exist_ok=True)
    batch_index = build_batch_index(context)
    label_window_index = build_label_window_index(context, batch_index["batch_id"].to_list() if not batch_index.is_empty() else [])
    lookback_batches = int(args.lookback_batches or config.lookback_batches)
    val_batches = int(args.val_batches or config.val_batches)
    embargo_batches = int(args.embargo_batches if args.embargo_batches is not None else config.embargo_batches)
    effective_config = merge_config(
        config,
        lookback_batches=lookback_batches,
        val_batches=val_batches,
        embargo_batches=embargo_batches,
        n_steps=int(args.n_steps or config.n_steps),
    )
    windows = build_windows(
        batch_index,
        lookback_batches=lookback_batches,
        val_batches=val_batches,
        embargo_batches=embargo_batches,
        n_steps=effective_config.n_steps,
    )
    label_window_safety, label_window_rows = _label_window_safety(windows, label_window_index, embargo_batches)
    if label_window_safety["status"] != "pass":
        raise ValueError(f"RPF label-window safety failed: {label_window_safety}")
    target_summary = _target_summary(context, batch_index)
    feature_integrity = _feature_integrity(context)
    ablation_features = select_ablation_features(context.manifest.feature_columns, effective_config.feature_ablation)
    target_drift_rows = _readiness_window_target_rows(context, windows)
    target_drift_by_step = {int(row["step_idx"]): row for row in target_drift_rows}
    readiness_window_rows = [
        {**row, **target_drift_by_step.get(int(row["step_idx"]), {})}
        for row in label_window_rows
    ]
    readiness = {
        "asset": context.asset,
        "root": context.root_key,
        "root_id": context.root_id,
        "target_col": context.target_col,
        "feature_root": str(context.feature_root),
        "label_root": str(context.label_root),
        "feature_count": int(context.manifest.feature_count),
        "manifest_feature_columns": len(context.manifest.feature_columns),
        "manifest_duplicate_count": int(context.manifest.duplicate_count),
        "manifest_null_feature_count": int(context.manifest.null_feature_count),
        "feature_integrity": feature_integrity,
        "available_batch_count": int(batch_index.height),
        "window_count": len(windows),
        "target_summary": target_summary,
        "label_window_safety": label_window_safety,
        "feature_source": "regression_only",
        "lookback_batches": effective_config.lookback_batches,
        "val_batches": effective_config.val_batches,
        "embargo_batches": effective_config.embargo_batches,
        "feature_ablation": effective_config.feature_ablation,
        "ablation_feature_count": len(ablation_features),
    }
    batch_index.write_parquet(run_root / "batch_index.parquet")
    label_window_index.write_parquet(run_root / "label_window_index.parquet")
    write_windows(run_root / "frozen_windows.parquet", windows)
    _write_rows_parquet(run_root / "window_metrics.parquet", readiness_window_rows, schema={"step_idx": pl.Int64})
    write_json(run_root / "readiness.json", readiness)
    write_json(run_root / "best_config.json", config_to_dict(effective_config))
    write_trials(run_root / "trials.parquet", [])
    write_stage_status(run_root / "stage_status.json", stage="readiness", status="ok", readiness=readiness)
    write_markdown(
        run_root / "report.md",
        title="Clean RPF Walk-Forward Readiness",
        sections={
            "Summary": {
                "asset": context.asset,
                "root": context.root_key,
                "target_col": context.target_col,
                "feature_count": context.manifest.feature_count,
                "available_batch_count": batch_index.height,
                "window_count": len(windows),
                "lookback_batches": effective_config.lookback_batches,
                "val_batches": effective_config.val_batches,
                "embargo_batches": effective_config.embargo_batches,
                "feature_ablation": effective_config.feature_ablation,
                "ablation_feature_count": len(ablation_features),
            },
            "Target": target_summary,
            "Feature Integrity": feature_integrity,
            "Label Window Safety": label_window_safety,
        },
    )
    append_event(events, "readiness_done", **readiness)
    _log(
        "readiness_done",
        features=context.manifest.feature_count,
        batches=batch_index.height,
        windows=len(windows),
        valid_rows=target_summary.get("valid_rows"),
        label_window_safety=label_window_safety.get("status"),
        zero_rate=target_summary.get("zero_rate"),
        one_rate=target_summary.get("one_rate"),
    )
    return readiness


def run_optuna_stage(
    context: RPFDataContext,
    config: CleanWalkForwardConfig,
    run_root: Path,
    events: Path,
    args: argparse.Namespace,
) -> None:
    run_root.mkdir(parents=True, exist_ok=True)
    optuna = _import_optuna()
    base_run = Path(args.base_run)
    loaded_base_config = _load_base_config(base_run, config)
    base_config = _apply_current_fixed_contract(loaded_base_config, config)
    if loaded_base_config.feature_policy != base_config.feature_policy or loaded_base_config.policy != base_config.policy:
        _log(
            "fixed_policy_override",
            old_policy=loaded_base_config.feature_policy,
            new_policy=base_config.feature_policy,
            old_features=_feature_label(loaded_base_config),
            new_features=_feature_label(base_config),
        )
        append_event(
            events,
            "fixed_policy_override",
            old_policy=loaded_base_config.feature_policy,
            new_policy=base_config.feature_policy,
            old_policy_config=asdict(loaded_base_config.policy),
            new_policy_config=asdict(base_config.policy),
        )
    batch_index = build_batch_index(context) if args.stage == "geometry" else pl.DataFrame()
    frozen_windows = _load_base_windows(base_run)
    sampler = _sampler_for_stage(optuna, args.stage, args)
    _log("sampler", stage=args.stage, sampler=type(sampler).__name__)
    append_event(events, "sampler", stage=args.stage, sampler=type(sampler).__name__)
    study = optuna.create_study(direction="minimize", sampler=sampler)
    trials: list[dict[str, Any]] = []
    window_metric_rows: list[dict[str, Any]] = []
    best_payload: dict[str, Any] | None = None

    def objective(trial: Any) -> float:
        trial_config = suggest_stage_config(trial, args.stage, base_config, args)
        windows = _windows_for_stage(args.stage, batch_index, frozen_windows, trial_config, args)
        _log(
            "trial_start",
            stage=args.stage,
            trial=trial.number,
            windows=len(windows),
            lb=trial_config.lookback_batches,
            val=trial_config.val_batches,
            features=_feature_label(trial_config),
            it=trial_config.model.iterations,
            depth=trial_config.model.depth,
            lr=trial_config.model.learning_rate,
        )
        append_event(events, "trial_start", trial_number=int(trial.number), config=config_to_dict(trial_config))
        try:
            payload = run_windows(
                context,
                trial_config,
                windows,
                task_type=str(args.task_type),
                thread_count=int(args.thread_count),
            )
            collapse = prediction_collapse_reason(
                payload["prediction_metrics"],
                min_unique=int(trial_config.min_prediction_unique),
                min_std=float(trial_config.min_prediction_std),
            )
            collapse = collapse or window_collapse_reason(
                payload.get("collapse_metrics", {}),
                max_collapsed_window_rate=float(trial_config.max_collapsed_window_rate),
                min_prediction_to_target_std_ratio=float(trial_config.min_prediction_to_target_std_ratio),
            )
            selected_features = int(payload.get("selected_feature_count_min") or 0)
            if selected_features < int(trial_config.policy.min_selected_features):
                collapse = collapse or "too_few_selected_features"
            hard_reject = collapse is not None and args.stage != "confirmation"
            status = "ok" if collapse is None or args.stage == "confirmation" else f"rejected:{collapse}"
            score = objective_score(payload["validation_metrics"])
            if hard_reject:
                score = 1e9
            row = {
                "trial_number": int(trial.number),
                "status": status,
                "objective_metric": "validation_rmse",
                "objective_direction": "minimize",
                "objective_value": float(score),
                "score": float(score),
                "collapse_reason": collapse,
                **_trial_config_columns(trial_config),
                **_flatten_metrics(payload["validation_metrics"], "validation"),
                **_flatten_metrics(payload["prediction_metrics"], "prediction"),
                **payload.get("baseline_metrics", {}),
                **payload.get("collapse_metrics", {}),
                "ablation_feature_count": payload.get("ablation_feature_count"),
                "selected_feature_count_min": payload.get("selected_feature_count_min"),
                "config_json": json.dumps(config_to_dict(trial_config), sort_keys=True, default=str),
            }
            trials.append(row)
            for window_row in payload.get("window_metrics", []):
                window_metric_rows.append({"trial_number": int(trial.number), **window_row})
            trial.set_user_attr("status", status)
            trial.set_user_attr("effective_config", config_to_dict(trial_config))
            trial.set_user_attr("prediction_metrics", payload["prediction_metrics"])
            trial.set_user_attr("validation_metrics", payload["validation_metrics"])
            append_event(events, "trial_done", **row)
            _log(
                "trial_done",
                stage=args.stage,
                trial=trial.number,
                status=status,
                objective_value=round(float(score), 6),
                val_spearman=payload["validation_metrics"].get("spearman"),
                val_rmse=payload["validation_metrics"].get("rmse"),
                pred_spearman=payload["prediction_metrics"].get("spearman"),
                pred_std=payload["prediction_metrics"].get("pred_std"),
                pred_unique=payload["prediction_metrics"].get("pred_unique"),
            )
            return float(score)
        except Exception as exc:
            row = {
                "trial_number": int(trial.number),
                "status": "error",
                "objective_metric": "validation_rmse",
                "objective_direction": "minimize",
                "objective_value": 1e9,
                "score": 1e9,
                "error": str(exc),
                **_trial_config_columns(trial_config),
                "config_json": json.dumps(config_to_dict(trial_config), sort_keys=True, default=str),
            }
            trials.append(row)
            append_event(events, "trial_error", **row)
            _log("trial_error", stage=args.stage, trial=trial.number, error=str(exc))
            return 1e9

    study.optimize(objective, n_trials=int(args.n_trials), timeout=args.timeout)
    if trials:
        best = min(trials, key=lambda row: float(row.get("objective_value", row.get("score", 1e9)) or 1e9))
        best_config = _config_from_payload(json.loads(best["config_json"]), base_config)
        best_payload = {
            "stage": args.stage,
            "objective_metric": "validation_rmse",
            "objective_direction": "minimize",
            "best_trial_number": best["trial_number"],
            "best_objective_value": best.get("objective_value", best["score"]),
            "best_score": best.get("objective_value", best["score"]),
            "best_status": best["status"],
            "config": config_to_dict(best_config),
        }
    else:
        best_config = base_config
        best_payload = {
            "stage": args.stage,
            "objective_metric": "validation_rmse",
            "objective_direction": "minimize",
            "best_status": "no_trials",
            "config": config_to_dict(best_config),
        }
    best_windows = _windows_for_stage(args.stage, batch_index, frozen_windows, best_config, args)
    write_windows(run_root / "frozen_windows.parquet", best_windows)
    write_trials(run_root / "trials.parquet", trials)
    _write_rows_parquet(run_root / "window_metrics.parquet", window_metric_rows, schema={"trial_number": pl.Int64})
    write_json(run_root / "best_config.json", best_payload["config"])
    write_json(run_root / f"locked_{args.stage}_config.json", best_payload["config"])
    write_stage_status(run_root / "stage_status.json", stage=args.stage, status="ok", best=best_payload)
    write_markdown(
        run_root / "report.md",
        title=f"Clean RPF Walk-Forward {args.stage}",
        sections={"Best": best_payload, "Trials": {"count": len(trials)}},
    )
    _log(
        "stage_best",
        stage=args.stage,
        status=best_payload.get("best_status"),
        objective_value=best_payload.get("best_objective_value"),
        trial=best_payload.get("best_trial_number"),
    )


def run_windows(
    context: RPFDataContext,
    config: CleanWalkForwardConfig,
    windows: list[RPFWindow],
    *,
    task_type: str,
    thread_count: int,
) -> dict[str, Any]:
    if not windows:
        raise ValueError("No RPF walk-forward windows to run")
    val_true: list[np.ndarray] = []
    val_pred: list[np.ndarray] = []
    pred_true: list[np.ndarray] = []
    pred_pred: list[np.ndarray] = []
    selected_counts: list[int] = []
    model_rows: list[dict[str, Any]] = []
    window_metric_rows: list[dict[str, Any]] = []
    feature_columns = select_ablation_features(context.manifest.feature_columns, config.feature_ablation)
    previous_prediction_target_mean: float | None = None
    for window in windows:
        train = load_joined_batches(context, window.train_batch_ids)
        val = load_joined_batches(context, window.val_batch_ids)
        pred = load_joined_batches(context, (window.pred_batch_id,))
        policy_result = select_features(
            train,
            target_col=context.target_col,
            feature_columns=feature_columns,
            config=config.policy,
        )
        selected = policy_result.selected_features
        selected_counts.append(len(selected))
        train = apply_clip_bounds(train, policy_result.clip_bounds)
        val = apply_clip_bounds(val, policy_result.clip_bounds)
        pred = apply_clip_bounds(pred, policy_result.clip_bounds)
        X_train, y_train, _ = frame_to_numpy(train, target_col=context.target_col, feature_columns=selected)
        X_val, y_val, _ = frame_to_numpy(val, target_col=context.target_col, feature_columns=selected)
        X_pred, y_pred_true, _ = frame_to_numpy(pred, target_col=context.target_col, feature_columns=selected)
        if X_train.size == 0 or X_val.size == 0 or X_pred.size == 0:
            raise ValueError("Empty model matrix after RPF feature/label filtering")
        model = fit_catboost(
            X_train,
            y_train,
            X_val,
            y_val,
            config=config.model,
            task_type=task_type,
            thread_count=thread_count,
        )
        y_val_pred = np.asarray(model.predict(X_val), dtype=float)
        y_pred = np.asarray(model.predict(X_pred), dtype=float)
        val_metrics = regression_metrics(y_val, y_val_pred)
        pred_metrics = regression_metrics(y_pred_true, y_pred)
        diagnostics = model_diagnostics(model)
        train_target_mean = _finite_mean(y_train)
        validation_target_mean = _finite_mean(y_val)
        window_baselines = {
            **_baseline_window_metrics(
                y_val,
                prefix="validation",
                train_target_mean=train_target_mean,
                validation_target_mean=validation_target_mean,
                previous_prediction_target_mean=previous_prediction_target_mean,
            ),
            **_baseline_window_metrics(
                y_pred_true,
                prefix="prediction",
                train_target_mean=train_target_mean,
                validation_target_mean=validation_target_mean,
                previous_prediction_target_mean=previous_prediction_target_mean,
            ),
        }
        window_collapse = _window_prediction_collapse_metrics(
            pred_metrics,
            min_std=float(config.min_prediction_std),
            min_prediction_to_target_std_ratio=float(config.min_prediction_to_target_std_ratio),
        )
        val_true.append(y_val)
        val_pred.append(y_val_pred)
        pred_true.append(y_pred_true)
        pred_pred.append(y_pred)
        model_rows.append(diagnostics)
        window_metric_rows.append(
            {
                "step_idx": int(window.step_idx),
                "pred_batch_id": int(window.pred_batch_id),
                "train_batch_count": len(window.train_batch_ids),
                "val_batch_count": len(window.val_batch_ids),
                "selected_feature_count": len(selected),
                "feature_ablation": config.feature_ablation,
                "train_start_ts": window.train_start_ts,
                "train_end_ts": window.train_end_ts,
                "val_start_ts": window.val_start_ts,
                "val_end_ts": window.val_end_ts,
                "pred_start_ts": window.pred_start_ts,
                "pred_end_ts": window.pred_end_ts,
                "train_rows": int(len(y_train)),
                "val_rows": int(len(y_val)),
                "pred_rows": int(len(y_pred_true)),
                **_target_distribution(y_train, "train_target"),
                **_target_distribution(y_val, "val_target"),
                **_target_distribution(y_pred_true, "pred_target"),
                **window_baselines,
                **_flatten_metrics(val_metrics, "validation"),
                **_flatten_metrics(pred_metrics, "prediction"),
                **window_collapse,
                **diagnostics,
            }
        )
        previous_prediction_target_mean = _finite_mean(y_pred_true)
    validation_metrics = regression_metrics(np.concatenate(val_true), np.concatenate(val_pred))
    prediction_metrics = regression_metrics(np.concatenate(pred_true), np.concatenate(pred_pred))
    baseline_metrics = _aggregate_baseline_metrics(window_metric_rows)
    collapse_metrics = _aggregate_collapse_metrics(window_metric_rows, prediction_metrics)
    return {
        "validation_metrics": validation_metrics,
        "prediction_metrics": prediction_metrics,
        "baseline_metrics": baseline_metrics,
        "collapse_metrics": collapse_metrics,
        "ablation_feature_count": len(feature_columns),
        "selected_feature_count_min": min(selected_counts) if selected_counts else 0,
        "selected_feature_count_mean": float(np.mean(selected_counts)) if selected_counts else 0.0,
        "model_diagnostics": model_rows,
        "window_metrics": window_metric_rows,
    }


def _baseline_window_metrics(
    y_true: np.ndarray,
    *,
    prefix: str,
    train_target_mean: float | None,
    validation_target_mean: float | None,
    previous_prediction_target_mean: float | None,
) -> dict[str, float | None]:
    return {
        f"{prefix}_baseline_constant_0p5_rmse": _rmse_against_constant(y_true, 0.5),
        f"{prefix}_baseline_train_target_mean_rmse": _rmse_against_constant(y_true, train_target_mean),
        f"{prefix}_baseline_validation_target_mean_rmse": _rmse_against_constant(y_true, validation_target_mean),
        f"{prefix}_baseline_previous_prediction_batch_mean_rmse": _rmse_against_constant(
            y_true,
            previous_prediction_target_mean,
        ),
    }


def _aggregate_baseline_metrics(window_rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for prefix in ("validation", "prediction"):
        for baseline in (
            "constant_0p5",
            "train_target_mean",
            "validation_target_mean",
            "previous_prediction_batch_mean",
        ):
            key = f"{prefix}_baseline_{baseline}_rmse"
            out[key] = _weighted_window_rmse(window_rows, metric_col=key, rows_col=f"{prefix}_rows")
        model_key = f"{prefix}_rmse"
        train_mean_key = f"{prefix}_baseline_train_target_mean_rmse"
        model_rmse = _weighted_window_rmse(window_rows, metric_col=model_key, rows_col=f"{prefix}_rows")
        baseline_rmse = out.get(train_mean_key)
        out[f"{prefix}_model_rmse_window_weighted"] = model_rmse
        out[f"{prefix}_model_rmse_minus_train_mean_baseline"] = (
            None if model_rmse is None or baseline_rmse is None else float(model_rmse) - float(baseline_rmse)
        )
        out[f"{prefix}_beats_train_mean_baseline"] = (
            None if model_rmse is None or baseline_rmse is None else bool(float(model_rmse) < float(baseline_rmse))
        )
    return out


def _window_prediction_collapse_metrics(
    pred_metrics: dict[str, Any],
    *,
    min_std: float,
    min_prediction_to_target_std_ratio: float,
) -> dict[str, Any]:
    target_std = pred_metrics.get("target_std")
    pred_std = pred_metrics.get("pred_std")
    pred_unique = int(pred_metrics.get("pred_unique") or 0)
    ratio = _safe_ratio(pred_std, target_std)
    reasons: list[str] = []
    if pred_unique <= 1:
        reasons.append("window_low_prediction_unique")
    if float(pred_std or 0.0) <= float(min_std):
        reasons.append("window_low_prediction_std")
    if ratio is not None and float(ratio) < float(min_prediction_to_target_std_ratio):
        reasons.append("window_low_prediction_to_target_std_ratio")
    return {
        "prediction_to_target_std_ratio_window": ratio,
        "prediction_mean_bias_window": _safe_difference(pred_metrics.get("pred_mean"), pred_metrics.get("target_mean")),
        "prediction_window_collapsed": bool(reasons),
        "prediction_window_collapse_reason": ",".join(reasons) if reasons else None,
    }


def _aggregate_collapse_metrics(
    window_rows: list[dict[str, Any]],
    prediction_metrics: dict[str, Any],
) -> dict[str, Any]:
    if not window_rows:
        return {
            "collapsed_window_count": 0,
            "collapsed_window_rate": 0.0,
            "prediction_pred_unique_min": None,
            "prediction_pred_std_min": None,
            "prediction_pred_std_mean": None,
            "prediction_to_target_std_ratio": _safe_ratio(
                prediction_metrics.get("pred_std"),
                prediction_metrics.get("target_std"),
            ),
            "prediction_mean_bias": _safe_difference(
                prediction_metrics.get("pred_mean"),
                prediction_metrics.get("target_mean"),
            ),
        }
    collapsed = [bool(row.get("prediction_window_collapsed")) for row in window_rows]
    pred_unique = [int(row.get("prediction_pred_unique") or 0) for row in window_rows]
    pred_std = [float(row["prediction_pred_std"]) for row in window_rows if row.get("prediction_pred_std") is not None]
    ratios = [
        float(row["prediction_to_target_std_ratio_window"])
        for row in window_rows
        if row.get("prediction_to_target_std_ratio_window") is not None
    ]
    return {
        "collapsed_window_count": int(sum(collapsed)),
        "collapsed_window_rate": float(sum(collapsed) / len(window_rows)),
        "prediction_pred_unique_min": int(min(pred_unique)) if pred_unique else None,
        "prediction_pred_std_min": float(min(pred_std)) if pred_std else None,
        "prediction_pred_std_mean": float(np.mean(pred_std)) if pred_std else None,
        "prediction_to_target_std_ratio": _safe_ratio(
            prediction_metrics.get("pred_std"),
            prediction_metrics.get("target_std"),
        ),
        "prediction_to_target_std_ratio_window_min": float(min(ratios)) if ratios else None,
        "prediction_to_target_std_ratio_window_mean": float(np.mean(ratios)) if ratios else None,
        "prediction_mean_bias": _safe_difference(
            prediction_metrics.get("pred_mean"),
            prediction_metrics.get("target_mean"),
        ),
    }


def window_collapse_reason(
    collapse_metrics: dict[str, Any],
    *,
    max_collapsed_window_rate: float,
    min_prediction_to_target_std_ratio: float,
) -> str | None:
    if float(collapse_metrics.get("collapsed_window_rate") or 0.0) > float(max_collapsed_window_rate):
        return "high_collapsed_window_rate"
    ratio = collapse_metrics.get("prediction_to_target_std_ratio")
    if ratio is not None and float(ratio) < float(min_prediction_to_target_std_ratio):
        return "low_prediction_to_target_std_ratio"
    pred_unique_min = collapse_metrics.get("prediction_pred_unique_min")
    if pred_unique_min is not None and int(pred_unique_min) <= 1:
        return "low_window_prediction_unique"
    return None


def _rmse_against_constant(y_true: np.ndarray, value: float | None) -> float | None:
    if value is None:
        return None
    y_true = np.asarray(y_true, dtype=float)
    mask = np.isfinite(y_true)
    if not mask.any() or not np.isfinite(float(value)):
        return None
    error = y_true[mask] - float(value)
    return float(math.sqrt(np.mean(error**2)))


def _weighted_window_rmse(
    window_rows: list[dict[str, Any]],
    *,
    metric_col: str,
    rows_col: str,
) -> float | None:
    weighted_sse = 0.0
    total_rows = 0.0
    for row in window_rows:
        metric = row.get(metric_col)
        rows = row.get(rows_col)
        if metric is None or rows is None:
            continue
        rows_float = float(rows)
        weighted_sse += float(metric) ** 2 * rows_float
        total_rows += rows_float
    if total_rows <= 0.0:
        return None
    return float(math.sqrt(weighted_sse / total_rows))


def _finite_mean(values: np.ndarray) -> float | None:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return None
    return float(np.mean(values))


def _safe_ratio(numerator: Any, denominator: Any) -> float | None:
    if numerator is None or denominator is None:
        return None
    denominator_float = float(denominator)
    if denominator_float <= 0.0 or not np.isfinite(denominator_float):
        return None
    numerator_float = float(numerator)
    if not np.isfinite(numerator_float):
        return None
    return float(numerator_float / denominator_float)


def _safe_difference(left: Any, right: Any) -> float | None:
    if left is None or right is None:
        return None
    left_float = float(left)
    right_float = float(right)
    if not np.isfinite(left_float) or not np.isfinite(right_float):
        return None
    return float(left_float - right_float)


def suggest_stage_config(
    trial: Any,
    stage: str,
    base: CleanWalkForwardConfig,
    args: argparse.Namespace,
) -> CleanWalkForwardConfig:
    if stage == "baseline_probe":
        return merge_config(base, model=_suggest_core_model(trial, args))
    if stage == "geometry":
        return merge_config(
            base,
            lookback_batches=trial.suggest_categorical("lookback_batches", _parse_ints(args.lookback_choices)),
            val_batches=trial.suggest_categorical("val_batches", _parse_ints(args.val_choices)),
            embargo_batches=trial.suggest_categorical("embargo_batches", _parse_ints(args.embargo_choices)),
        )
    if stage == "core_model":
        return merge_config(base, model=_suggest_core_model(trial, args))
    if stage == "sampling":
        bootstrap = trial.suggest_categorical("bootstrap_type", _parse_optional_strings(args.bootstrap_type_choices))
        updates: dict[str, Any] = {"bootstrap_type": bootstrap}
        if bootstrap == "Bayesian":
            updates["bagging_temperature"] = trial.suggest_categorical("bagging_temperature", _parse_floats(args.bagging_temperature_choices))
        elif bootstrap in {"Bernoulli", "Poisson"}:
            updates["subsample"] = trial.suggest_categorical("subsample", _parse_floats(args.subsample_choices))
        updates["random_strength"] = trial.suggest_categorical("random_strength", _parse_floats(args.random_strength_choices))
        updates["border_count"] = trial.suggest_categorical("border_count", _parse_ints(args.border_count_choices))
        return merge_config(base, model=updates)
    if stage == "confirmation":
        return base
    raise ValueError(f"Unsupported clean RPF stage: {stage}")


def _suggest_core_model(trial: Any, args: argparse.Namespace) -> dict[str, Any]:
    return {
        "iterations": trial.suggest_categorical("iterations", _parse_ints(args.iterations_choices)),
        "depth": trial.suggest_categorical("depth", _parse_ints(args.depth_choices)),
        "learning_rate": trial.suggest_categorical("learning_rate", _parse_floats(args.learning_rate_choices)),
        "l2_leaf_reg": trial.suggest_categorical("l2_leaf_reg", _parse_floats(args.l2_leaf_reg_choices)),
        "early_stopping_rounds": trial.suggest_categorical("early_stopping_rounds", _parse_ints(args.early_stopping_rounds_choices)),
        "od_wait": trial.suggest_categorical("od_wait", _parse_ints(args.od_wait_choices)),
    }


def _windows_for_stage(
    stage: str,
    batch_index: pl.DataFrame,
    frozen: list[RPFWindow],
    config: CleanWalkForwardConfig,
    args: argparse.Namespace,
) -> list[RPFWindow]:
    if stage == "geometry":
        return build_windows(
            batch_index,
            lookback_batches=config.lookback_batches,
            val_batches=config.val_batches,
            embargo_batches=config.embargo_batches,
            n_steps=int(args.n_steps if args.n_steps is not None else config.n_steps),
        )
    n_steps = int(args.n_steps if args.n_steps is not None else config.n_steps)
    windows = frozen[-n_steps:] if n_steps > 0 else frozen
    if not windows:
        raise ValueError("Base run has no frozen windows")
    return windows


def _config_from_payload(payload: dict[str, Any], fallback: CleanWalkForwardConfig) -> CleanWalkForwardConfig:
    policy_payload = payload.get("policy", {})
    model_payload = payload.get("model", {})
    return CleanWalkForwardConfig(
        asset=str(payload.get("asset", fallback.asset)),
        root=str(payload.get("root", fallback.root)),
        root_id=str(payload.get("root_id", fallback.root_id)),
        feature_set=str(payload.get("feature_set", fallback.feature_set)),
        target_variant=str(payload.get("target_variant", fallback.target_variant)),
        target_col=str(payload.get("target_col", fallback.target_col)),
        feature_source=str(payload.get("feature_source", fallback.feature_source)),
        feature_policy=str(payload.get("feature_policy", fallback.feature_policy)),
        feature_ablation=str(payload.get("feature_ablation", fallback.feature_ablation)),
        lookback_batches=int(payload.get("lookback_batches", fallback.lookback_batches)),
        val_batches=int(payload.get("val_batches", fallback.val_batches)),
        embargo_batches=int(payload.get("embargo_batches", fallback.embargo_batches)),
        n_steps=int(payload.get("n_steps", fallback.n_steps)),
        min_prediction_unique=int(payload.get("min_prediction_unique", fallback.min_prediction_unique)),
        min_prediction_std=float(payload.get("min_prediction_std", fallback.min_prediction_std)),
        max_collapsed_window_rate=float(payload.get("max_collapsed_window_rate", fallback.max_collapsed_window_rate)),
        min_prediction_to_target_std_ratio=float(
            payload.get("min_prediction_to_target_std_ratio", fallback.min_prediction_to_target_std_ratio)
        ),
        policy=FeaturePolicyConfig(**policy_payload),
        model=CatBoostConfig(**model_payload),
    )


def _load_base_config(base_run: Path, fallback: CleanWalkForwardConfig) -> CleanWalkForwardConfig:
    for name in ("best_config.json", "locked_baseline_probe_config.json", "locked_geometry_config.json"):
        path = base_run / name
        if path.exists():
            payload = json.loads(path.read_text())
            if "config" in payload:
                payload = payload["config"]
            return _config_from_payload(payload, fallback)
    return fallback


def _apply_current_fixed_contract(
    base: CleanWalkForwardConfig,
    current: CleanWalkForwardConfig,
) -> CleanWalkForwardConfig:
    """Keep locked tuning state, but never inherit stale fixed RPF contract values."""

    return merge_config(
        base,
        asset=current.asset,
        root=current.root,
        root_id=current.root_id,
        feature_set=current.feature_set,
        target_variant=current.target_variant,
        target_col=current.target_col,
        feature_source=current.feature_source,
        feature_policy=current.feature_policy,
        feature_ablation=current.feature_ablation,
        min_prediction_unique=current.min_prediction_unique,
        min_prediction_std=current.min_prediction_std,
        max_collapsed_window_rate=current.max_collapsed_window_rate,
        min_prediction_to_target_std_ratio=current.min_prediction_to_target_std_ratio,
        policy=asdict(current.policy),
    )


def _feature_label(config: CleanWalkForwardConfig) -> str | int:
    if config.policy.policy == ALL_MANIFEST_FEATURES:
        return "all"
    if config.policy.policy == FROZEN_PANEL:
        return "frozen_panel"
    return int(config.policy.max_features)


def _trial_config_columns(config: CleanWalkForwardConfig) -> dict[str, Any]:
    model = config.model
    return {
        "feature_policy": config.feature_policy,
        "feature_ablation": config.feature_ablation,
        "feature_count_mode": _feature_label(config),
        "max_collapsed_window_rate": float(config.max_collapsed_window_rate),
        "min_prediction_to_target_std_ratio": float(config.min_prediction_to_target_std_ratio),
        "lookback_batches": int(config.lookback_batches),
        "val_batches": int(config.val_batches),
        "embargo_batches": int(config.embargo_batches),
        "iterations": int(model.iterations),
        "depth": int(model.depth),
        "learning_rate": float(model.learning_rate),
        "l2_leaf_reg": float(model.l2_leaf_reg),
        "early_stopping_rounds": int(model.early_stopping_rounds),
        "od_wait": None if model.od_wait is None else int(model.od_wait),
        "bootstrap_type": model.bootstrap_type,
        "bagging_temperature": model.bagging_temperature,
        "subsample": model.subsample,
        "random_strength": model.random_strength,
        "border_count": model.border_count,
        "loss_function": model.loss_function,
        "eval_metric": model.eval_metric,
        "has_time": bool(model.has_time),
    }


def _sampler_for_stage(optuna: Any, stage: str, args: argparse.Namespace) -> Any:
    search_space = _grid_search_space(stage, args)
    if search_space:
        return optuna.samplers.GridSampler(search_space, seed=int(args.seed))
    return optuna.samplers.TPESampler(seed=int(args.seed))


def _grid_search_space(stage: str, args: argparse.Namespace) -> dict[str, list[Any]]:
    if stage == "geometry":
        return {
            "lookback_batches": _parse_ints(args.lookback_choices),
            "val_batches": _parse_ints(args.val_choices),
            "embargo_batches": _parse_ints(args.embargo_choices),
        }
    if stage in {"baseline_probe", "core_model"}:
        return {
            "iterations": _parse_ints(args.iterations_choices),
            "depth": _parse_ints(args.depth_choices),
            "learning_rate": _parse_floats(args.learning_rate_choices),
            "l2_leaf_reg": _parse_floats(args.l2_leaf_reg_choices),
            "early_stopping_rounds": _parse_ints(args.early_stopping_rounds_choices),
            "od_wait": _parse_ints(args.od_wait_choices),
        }
    return {}


def _load_base_windows(base_run: Path) -> list[RPFWindow]:
    return read_windows(base_run / "frozen_windows.parquet")


def _target_summary(context: RPFDataContext, batch_index: pl.DataFrame) -> dict[str, Any]:
    if batch_index.is_empty():
        return {"valid_rows": 0}
    paths = [context.label_root / f"batch_{int(row['batch_id']):04d}.parquet" for row in batch_index.to_dicts()]
    target = pl.col(context.target_col)
    df = (
        pl.scan_parquet(paths)
        .select([context.target_col, "target_reg_distance_valid_v2"])
        .filter(pl.col("target_reg_distance_valid_v2").fill_null(False) & pl.col(context.target_col).is_not_null())
        .select(
            pl.len().alias("valid_rows"),
            target.min().alias("min"),
            target.max().alias("max"),
            target.mean().alias("mean"),
            target.std().alias("std"),
            target.quantile(0.01).alias("p01"),
            target.quantile(0.05).alias("p05"),
            target.quantile(0.5).alias("p50"),
            target.quantile(0.95).alias("p95"),
            target.quantile(0.99).alias("p99"),
            target.n_unique().alias("n_unique"),
            (target.abs() <= 1e-12).mean().alias("zero_rate"),
            ((target - 1.0).abs() <= 1e-12).mean().alias("one_rate"),
        )
        .collect()
        .to_dicts()[0]
    )
    return df


def _feature_integrity(context: RPFDataContext) -> dict[str, Any]:
    counts = _feature_family_counts(context.manifest.feature_columns)
    return {
        "feature_count": int(context.manifest.feature_count),
        "manifest_feature_columns": len(context.manifest.feature_columns),
        "manifest_duplicate_count": int(context.manifest.duplicate_count),
        "manifest_null_feature_count": int(context.manifest.null_feature_count),
        "source_fingerprint": context.manifest.source_fingerprint,
        "family_counts": counts,
        "unmapped_feature_count": int(counts.get("unmapped", 0)),
    }


def _feature_family_counts(feature_columns: tuple[str, ...]) -> dict[str, int]:
    counts = {family: 0 for family in FAMILY_PREFIXES}
    counts["unmapped"] = 0
    for feature in feature_columns:
        matched = False
        for family, prefixes in FAMILY_PREFIXES.items():
            if feature.startswith(prefixes):
                counts[family] += 1
                matched = True
                break
        if not matched:
            counts["unmapped"] += 1
    return counts


def _readiness_window_target_rows(context: RPFDataContext, windows: list[RPFWindow]) -> list[dict[str, Any]]:
    batch_ids = sorted(
        {
            int(batch_id)
            for window in windows
            for batch_id in (*window.train_batch_ids, *window.val_batch_ids, window.pred_batch_id)
        }
    )
    stats = _target_batch_stats(context, batch_ids)
    rows: list[dict[str, Any]] = []
    for window in windows:
        train_stats = _combine_batch_stats(stats, window.train_batch_ids, "train_target")
        val_stats = _combine_batch_stats(stats, window.val_batch_ids, "val_target")
        pred_stats = _combine_batch_stats(stats, (window.pred_batch_id,), "pred_target")
        rows.append(
            {
                "step_idx": int(window.step_idx),
                "pred_batch_id": int(window.pred_batch_id),
                **train_stats,
                **val_stats,
                **pred_stats,
                "target_mean_drift_val_minus_train": _safe_difference(
                    val_stats.get("val_target_mean"),
                    train_stats.get("train_target_mean"),
                ),
                "target_mean_drift_pred_minus_train": _safe_difference(
                    pred_stats.get("pred_target_mean"),
                    train_stats.get("train_target_mean"),
                ),
                "target_mean_drift_pred_minus_val": _safe_difference(
                    pred_stats.get("pred_target_mean"),
                    val_stats.get("val_target_mean"),
                ),
            }
        )
    return rows


def _target_batch_stats(context: RPFDataContext, batch_ids: list[int]) -> dict[int, dict[str, Any]]:
    if not batch_ids:
        return {}
    paths = [context.label_root / f"batch_{int(batch_id):04d}.parquet" for batch_id in batch_ids]
    target = pl.col(context.target_col)
    frame = (
        pl.scan_parquet(paths, extra_columns="ignore")
        .select(["batch_id", "target_reg_distance_valid_v2", context.target_col])
        .filter(pl.col("target_reg_distance_valid_v2").fill_null(False) & target.is_not_null() & target.is_finite())
        .group_by("batch_id")
        .agg(
            pl.len().alias("rows"),
            target.sum().alias("sum"),
            (target * target).sum().alias("sum_sq"),
            target.min().alias("min"),
            target.max().alias("max"),
        )
        .collect()
    )
    return {int(row["batch_id"]): row for row in frame.to_dicts()}


def _combine_batch_stats(
    stats_by_batch: dict[int, dict[str, Any]],
    batch_ids: tuple[int, ...],
    prefix: str,
) -> dict[str, float | int | None]:
    rows = [stats_by_batch[batch_id] for batch_id in batch_ids if int(batch_id) in stats_by_batch]
    count = int(sum(int(row["rows"]) for row in rows))
    if count == 0:
        return {
            f"{prefix}_rows": 0,
            f"{prefix}_mean": None,
            f"{prefix}_std": None,
            f"{prefix}_min": None,
            f"{prefix}_max": None,
        }
    total = float(sum(float(row["sum"]) for row in rows))
    total_sq = float(sum(float(row["sum_sq"]) for row in rows))
    mean = total / count
    variance = max(total_sq / count - mean * mean, 0.0)
    return {
        f"{prefix}_rows": count,
        f"{prefix}_mean": float(mean),
        f"{prefix}_std": float(math.sqrt(variance)),
        f"{prefix}_min": float(min(float(row["min"]) for row in rows)),
        f"{prefix}_max": float(max(float(row["max"]) for row in rows)),
    }


def _label_window_safety(
    windows: list[RPFWindow],
    label_window_index: pl.DataFrame,
    embargo_batches: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if label_window_index.is_empty():
        return {"status": "fail", "reason": "empty_label_window_index", "violation_count": 1}, []
    rows_by_batch = {int(row["batch_id"]): row for row in label_window_index.to_dicts()}
    rows: list[dict[str, Any]] = []
    violations = 0
    missing_batches = 0
    cross_batch_label_rows = 0
    max_horizon = 0.0
    for window in windows:
        train_rows = [rows_by_batch.get(batch_id) for batch_id in window.train_batch_ids]
        val_rows = [rows_by_batch.get(batch_id) for batch_id in window.val_batch_ids]
        pred_row = rows_by_batch.get(window.pred_batch_id)
        if any(row is None for row in train_rows) or any(row is None for row in val_rows) or pred_row is None:
            missing_batches += 1
            violations += 1
            continue
        train_rows_typed = [row for row in train_rows if row is not None]
        val_rows_typed = [row for row in val_rows if row is not None]
        train_label_end = max(row["label_window_end_max"] for row in train_rows_typed)
        val_entry_start = min(row["entry_start_ts"] for row in val_rows_typed)
        val_label_end = max(row["label_window_end_max"] for row in val_rows_typed)
        pred_entry_start = pred_row["entry_start_ts"]
        train_val_overlap = train_label_end > val_entry_start
        val_pred_overlap = val_label_end > pred_entry_start
        window_cross_batch = (
            sum(int(row["cross_batch_label_count"] or 0) for row in train_rows_typed)
            + sum(int(row["cross_batch_label_count"] or 0) for row in val_rows_typed)
            + int(pred_row["cross_batch_label_count"] or 0)
        )
        cross_batch_label_rows += window_cross_batch
        max_horizon = max(
            max_horizon,
            max(float(row["horizon_minutes_max"] or 0.0) for row in train_rows_typed),
            max(float(row["horizon_minutes_max"] or 0.0) for row in val_rows_typed),
            float(pred_row["horizon_minutes_max"] or 0.0),
        )
        violation = bool(train_val_overlap or val_pred_overlap or (int(embargo_batches) == 0 and window_cross_batch > 0))
        violations += int(violation)
        rows.append(
            {
                "step_idx": int(window.step_idx),
                "pred_batch_id": int(window.pred_batch_id),
                "train_label_end_max": train_label_end,
                "val_entry_start_ts": val_entry_start,
                "val_label_end_max": val_label_end,
                "pred_entry_start_ts": pred_entry_start,
                "train_val_label_overlap": bool(train_val_overlap),
                "val_pred_label_overlap": bool(val_pred_overlap),
                "cross_batch_label_rows": int(window_cross_batch),
                "label_window_violation": violation,
                "train_batch_count": len(window.train_batch_ids),
                "val_batch_count": len(window.val_batch_ids),
            }
        )
    status = "pass" if violations == 0 and missing_batches == 0 else "fail"
    return (
        {
            "status": status,
            "window_count": len(windows),
            "violation_count": int(violations),
            "missing_batch_count": int(missing_batches),
            "cross_batch_label_rows": int(cross_batch_label_rows),
            "max_horizon_minutes": float(max_horizon),
            "embargo_batches": int(embargo_batches),
        },
        rows,
    )


def _target_distribution(values: np.ndarray, prefix: str) -> dict[str, float | int | None]:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return {f"{prefix}_rows": 0, f"{prefix}_mean": None, f"{prefix}_std": None, f"{prefix}_min": None, f"{prefix}_max": None}
    return {
        f"{prefix}_rows": int(len(values)),
        f"{prefix}_mean": float(np.mean(values)),
        f"{prefix}_std": float(np.std(values)),
        f"{prefix}_min": float(np.min(values)),
        f"{prefix}_max": float(np.max(values)),
    }


def _write_rows_parquet(path: Path, rows: list[dict[str, Any]], *, schema: dict[str, pl.DataType]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        pl.DataFrame(rows, infer_schema_length=None).write_parquet(path)
    else:
        pl.DataFrame(schema=schema).write_parquet(path)
    return path


def _run_root(args: argparse.Namespace, config: CleanWalkForwardConfig) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    slug = _short_slug(f"{config.asset}_{config.root_id}_{config.target_col}_{args.stage}")
    return Path(args.output_dir) / f"{stamp}_{args.stage}_{slug}"


def _short_slug(value: str) -> str:
    clean = "".join(ch.lower() if ch.isalnum() else "_" for ch in str(value)).strip("_")
    digest = hashlib.blake2s(clean.encode("utf-8"), digest_size=4).hexdigest()
    return f"{clean[:48]}_{digest}"


def _log(message: str, **fields: Any) -> None:
    parts = [f"[rpf-wf] {message}"]
    for key, value in fields.items():
        if value is None:
            continue
        parts.append(f"{key}={value}")
    print(" ".join(parts), flush=True)


def _flatten_metrics(metrics: dict[str, Any], prefix: str) -> dict[str, Any]:
    return {f"{prefix}_{key}": value for key, value in metrics.items()}


def _parse_ints(raw: str) -> list[int]:
    return [int(value) for value in _parse_strings(raw)]


def _parse_floats(raw: str) -> list[float]:
    return [float(value) for value in _parse_strings(raw)]


def _parse_optional_strings(raw: str) -> list[str | None]:
    out: list[str | None] = []
    for value in _parse_strings(raw):
        out.append(None if value.lower() in {"none", "null"} else value)
    return out


def _parse_strings(raw: str) -> list[str]:
    return [value.strip() for value in str(raw).split(",") if value.strip()]


def _parse_clip_quantiles(raw: str) -> tuple[float, float]:
    parts = [float(value) for value in str(raw).split(",")]
    if len(parts) != 2 or not (0.0 <= parts[0] < parts[1] <= 1.0):
        raise ValueError(f"Invalid clip quantiles: {raw}")
    return parts[0], parts[1]


def _import_optuna() -> Any:
    try:
        import optuna
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("Optuna is required for clean RPF optimization") from exc
    return optuna


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clean RPF-native walk-forward optimizer.")
    parser.add_argument("--stage", choices=STAGES, required=True)
    parser.add_argument("--asset", default=None)
    parser.add_argument("--root", default=None)
    parser.add_argument("--target-col", default=None)
    parser.add_argument("--feature-ablation", default=None)
    parser.add_argument("--frozen-panel-path", type=Path, default=None)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--base-run", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--lookback-batches", type=int, default=None)
    parser.add_argument("--val-batches", type=int, default=None)
    parser.add_argument("--embargo-batches", type=int, default=None)
    parser.add_argument("--n-steps", type=int, default=None)
    parser.add_argument("--n-trials", type=int, default=12)
    parser.add_argument("--timeout", type=int, default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--task-type", choices=["CPU", "GPU"], default="CPU")
    parser.add_argument("--thread-count", type=int, default=-1)
    parser.add_argument("--lookback-choices", default="80,120,160,180")
    parser.add_argument("--val-choices", default="8,10,12")
    parser.add_argument("--embargo-choices", default="0")
    parser.add_argument("--iterations-choices", default="400,800,1200")
    parser.add_argument("--depth-choices", default="3,4")
    parser.add_argument("--learning-rate-choices", default="0.005,0.01,0.02")
    parser.add_argument("--l2-leaf-reg-choices", default="100,200,300")
    parser.add_argument("--early-stopping-rounds-choices", default="50,100,150")
    parser.add_argument("--od-wait-choices", default="50,100,150")
    parser.add_argument("--bootstrap-type-choices", default="None,Bayesian,Bernoulli")
    parser.add_argument("--bagging-temperature-choices", default="0.25,0.5,1.0")
    parser.add_argument("--subsample-choices", default="0.66,0.8,0.9")
    parser.add_argument("--random-strength-choices", default="1,5,10")
    parser.add_argument("--border-count-choices", default="64,128,254")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
