"""RPF-native regime-gate walk-forward experiments."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from regression_feature_engineering.walkforward.ablation import select_ablation_features
from regression_feature_engineering.walkforward.classify import (
    DOWN_EXTREME,
    UP_EXTREME,
    _flatten,
    _model_choice_grid,
    _threshold_values,
    binary_metrics,
    classification_objective,
    fit_classifier,
    select_decision_threshold,
)
from regression_feature_engineering.walkforward.classification.model import (
    MODEL_CATBOOST,
    prediction_probability,
    validation_probability,
)
from regression_feature_engineering.walkforward.config import load_clean_config
from regression_feature_engineering.walkforward.data import RPFDataContext, VALID_COL, resolve_context
from regression_feature_engineering.walkforward.reports import (
    append_event,
    write_json,
    write_markdown,
    write_stage_status,
    write_trials,
)
from regression_feature_engineering.walkforward.signal_bank import (
    CHRONOLOGICAL_RECENT,
    SignalBankConfig,
    build_batch_signal_inventory,
    build_signal_bank_windows,
    WINDOW_MODES,
)
from regression_feature_engineering.walkforward.windows import RPFWindow, read_windows
from scripts.project_paths import ensure_project_root_on_path


PROJECT_ROOT = ensure_project_root_on_path(Path(__file__))
OUTPUT_ROOT = PROJECT_ROOT / "test_output" / "rpf_regime_gate"

GATE_UP_DOMINANT = "future_up_dominant"
GATE_DOWN_DOMINANT = "future_down_dominant"
GATE_TWO_SIDED = "future_two_sided"
GATE_LOW_EDGE = "future_low_edge"
GATE_TARGETS = (GATE_UP_DOMINANT, GATE_DOWN_DOMINANT, GATE_TWO_SIDED, GATE_LOW_EDGE)


def main() -> int:
    args = _parse_args()
    config = load_clean_config(args.config)
    asset = str(args.asset or config.asset)
    root = str(args.root or config.root)
    gate_target = str(args.gate_target)
    context = resolve_context(project_root=PROJECT_ROOT, asset=asset, root=root, target_col=UP_EXTREME)
    run_root = _run_root(args, gate_target)
    run_root.mkdir(parents=True, exist_ok=True)
    events = run_root / "events.jsonl"
    append_event(
        events,
        "stage_start",
        stage="regime_gate",
        asset=asset,
        root=root,
        gate_target=gate_target,
        run=str(run_root),
    )
    print(
        "[rpf-gate] start "
        f"asset={asset} root={root} gate={gate_target} run={run_root}",
        flush=True,
    )

    windows = read_windows(Path(args.base_run) / "frozen_windows.parquet")
    n_steps = int(args.n_steps)
    windows = windows[-n_steps:] if n_steps > 0 else windows
    if not windows:
        raise ValueError("No frozen windows to run")
    signal_bank_rows = []
    if str(args.window_mode) == CHRONOLOGICAL_RECENT:
        signal_bank_config = SignalBankConfig(mode=CHRONOLOGICAL_RECENT)
        _, signal_bank_rows = build_signal_bank_windows(
            windows,
            pl.DataFrame(),
            gate_target=gate_target,
            config=signal_bank_config,
        )
    else:
        inventory = build_batch_signal_inventory(context)
        inventory.write_parquet(run_root / "batch_signal_inventory.parquet")
        signal_bank_config = SignalBankConfig(
            mode=str(args.window_mode),
            positive_batch_min_rate=float(args.positive_batch_min_rate),
            opposite_batch_max_rate=float(args.opposite_batch_max_rate),
            train_positive_batches=int(args.train_positive_batches),
            train_negative_batches=int(args.train_negative_batches),
            val_positive_batches=int(args.val_positive_batches),
            val_negative_batches=int(args.val_negative_batches),
            candidate_lookback_batches=int(args.candidate_lookback_batches),
            label_maturity_embargo_batches=int(args.label_maturity_embargo_batches),
            recent_train_batches=int(args.recent_train_batches),
            recent_val_batches=int(args.recent_val_batches),
        )
        windows, signal_bank_rows = build_signal_bank_windows(
            windows,
            inventory,
            gate_target=gate_target,
            config=signal_bank_config,
        )
    _write_rows_parquet(run_root / "window_signal_bank.parquet", signal_bank_rows)
    feature_columns = select_ablation_features(context.manifest.feature_columns, str(args.feature_ablation))
    thresholds = _threshold_values(args)
    choices = _model_choice_grid(args)

    trials: list[dict[str, Any]] = []
    window_rows: list[dict[str, Any]] = []
    gate_score_rows: list[dict[str, Any]] = []
    for trial_number, model_updates in enumerate(choices[: int(args.max_configs)]):
        append_event(
            events,
            "trial_start",
            trial_number=trial_number,
            windows=len(windows),
            feature_ablation=str(args.feature_ablation),
            feature_count=len(feature_columns),
            **model_updates,
        )
        print(
            "[rpf-gate] trial_start "
            f"trial={trial_number} windows={len(windows)} gate={gate_target} "
            f"features={len(feature_columns)} it={model_updates['iterations']} "
            f"depth={model_updates['depth']} lr={model_updates['learning_rate']}",
            flush=True,
        )
        try:
            payload = run_gate_windows(
                context=context,
                windows=windows,
                gate_target=gate_target,
                feature_columns=feature_columns,
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
                gate_high_quantile=float(args.gate_high_quantile),
                gate_low_quantile=float(args.gate_low_quantile),
            )
            status = "ok"
            if payload["prediction_metrics"]["prob_unique"] <= int(args.min_prediction_unique):
                status = "rejected:low_prediction_unique"
            if float(payload["prediction_metrics"]["prob_std"] or 0.0) <= float(args.min_prediction_std):
                status = "rejected:low_prediction_std"
            row = {
                "trial_number": trial_number,
                "status": status,
                "gate_target": gate_target,
                "feature_ablation": str(args.feature_ablation),
                "feature_count": len(feature_columns),
                "window_mode": str(args.window_mode),
                "positive_batch_min_rate": float(args.positive_batch_min_rate),
                "opposite_batch_max_rate": float(args.opposite_batch_max_rate),
                "train_positive_batches": int(args.train_positive_batches),
                "train_negative_batches": int(args.train_negative_batches),
                "val_positive_batches": int(args.val_positive_batches),
                "val_negative_batches": int(args.val_negative_batches),
                "candidate_lookback_batches": int(args.candidate_lookback_batches),
                "label_maturity_embargo_batches": int(args.label_maturity_embargo_batches),
                "threshold_mode": str(args.threshold_mode),
                "selected_threshold": payload["selected_threshold"],
                "threshold_constraints_pass": payload["threshold_constraints_pass"],
                "threshold_constraints_reason": payload["threshold_constraints_reason"],
                "objective_metric": payload["objective_metric"],
                "objective_direction": payload["objective_direction"],
                "objective_value": payload["objective_value"],
                "fp_cost": float(args.fp_cost),
                "fn_cost": float(args.fn_cost),
                "tp_reward": float(args.tp_reward),
                "fbeta_beta": float(args.fbeta_beta),
                "gate_high_quantile": float(args.gate_high_quantile),
                "gate_low_quantile": float(args.gate_low_quantile),
                **model_updates,
                **_flatten(payload["validation_metrics"], "validation"),
                **_flatten(payload["prediction_metrics"], "prediction"),
            }
            trials.append(row)
            window_rows.extend({"trial_number": trial_number, **item} for item in payload["window_metrics"])
            gate_score_rows.extend({"trial_number": trial_number, **item} for item in payload["gate_scores"])
            append_event(
                events,
                "trial_done",
                trial_number=trial_number,
                status=status,
                objective_value=row["objective_value"],
                validation_decision_cost=row.get("validation_decision_cost_per_row"),
                prediction_false_positive_rate=row.get("prediction_false_positive_rate"),
            )
            print(
                "[rpf-gate] trial_done "
                f"trial={trial_number} status={status} objective={row['objective_value']:.6f} "
                f"val_cost={row['validation_decision_cost_per_row']} "
                f"pred_fpr={row['prediction_false_positive_rate']}",
                flush=True,
            )
        except Exception as exc:
            row = {
                "trial_number": trial_number,
                "status": "error",
                "gate_target": gate_target,
                "feature_ablation": str(args.feature_ablation),
                "feature_count": len(feature_columns),
                "window_mode": str(args.window_mode),
                "objective_metric": str(args.objective_metric),
                "objective_direction": "minimize",
                "objective_value": 1e9,
                "error": str(exc),
                **model_updates,
            }
            trials.append(row)
            append_event(events, "trial_error", trial_number=trial_number, error=str(exc))
            print(f"[rpf-gate] trial_error trial={trial_number} error={exc}", flush=True)

    best = _best_trial(trials)
    write_trials(run_root / "trials.parquet", trials)
    _write_rows_parquet(run_root / "window_metrics.parquet", window_rows)
    _write_rows_parquet(run_root / "gate_scores.parquet", gate_score_rows)
    gated_decision_rows = evaluate_gated_decisions(
        gate_scores=gate_score_rows,
        best_trial=best,
        classifier_score_path=args.classifier_score_path,
        classifier_side=str(args.classifier_side),
        classifier_trial_number=args.classifier_trial_number,
        classifier_threshold=float(args.classifier_threshold),
    )
    _write_rows_parquet(run_root / "gated_decision_metrics.parquet", gated_decision_rows)
    write_json(
        run_root / "best_config.json",
        {
            "asset": asset,
            "root": root,
            "gate_target": gate_target,
            "gate_rule": gate_rule_description(gate_target),
            "feature_ablation": str(args.feature_ablation),
            "window_mode": str(args.window_mode),
            "signal_bank_config": signal_bank_config.__dict__,
            "objective_metric": str(args.objective_metric),
            "threshold_mode": str(args.threshold_mode),
            "fp_cost": float(args.fp_cost),
            "fn_cost": float(args.fn_cost),
            "best": best,
            "classifier_score_path": None if args.classifier_score_path is None else str(args.classifier_score_path),
        },
    )
    write_markdown(
        run_root / "report.md",
        title="RPF Regime-Gate Walk-Forward",
        sections={
            "Gate": {
                "gate_target": gate_target,
                "gate_rule": gate_rule_description(gate_target),
                "asset": asset,
                "root": root,
            },
            "Run": {
                "windows": len(windows),
                "feature_ablation": str(args.feature_ablation),
                "feature_count": len(feature_columns),
                "window_mode": str(args.window_mode),
                "objective_metric": str(args.objective_metric),
                "threshold_mode": str(args.threshold_mode),
                "fp_cost": float(args.fp_cost),
                "fn_cost": float(args.fn_cost),
            },
            "Best": best or {},
            "Gated Decision Evaluation": (
                gated_decision_rows
                if gated_decision_rows
                else "No classifier score path was provided, so gated decision metrics are empty."
            ),
        },
    )
    write_stage_status(
        run_root / "stage_status.json",
        stage="regime_gate",
        status="ok",
        asset=asset,
        root=root,
        gate_target=gate_target,
        run=str(run_root),
        trials=len(trials),
        windows=len(windows),
        window_mode=str(args.window_mode),
        best=best,
    )
    append_event(events, "stage_done", stage="regime_gate", run=str(run_root))
    print(f"[rpf-gate] done run={run_root}", flush=True)
    return 0


def run_gate_windows(
    *,
    context: RPFDataContext,
    windows: list[RPFWindow],
    gate_target: str,
    feature_columns: tuple[str, ...],
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
    gate_high_quantile: float,
    gate_low_quantile: float,
) -> dict[str, Any]:
    val_true: list[np.ndarray] = []
    val_prob: list[np.ndarray] = []
    pred_true: list[np.ndarray] = []
    pred_prob: list[np.ndarray] = []
    window_payloads: list[dict[str, Any]] = []
    for window in windows:
        train_base = load_joined_gate_batches(
            context,
            window.train_batch_ids,
            feature_columns=feature_columns,
            gate_target=None,
        )
        thresholds = train_gate_thresholds(
            train_base,
            high_quantile=gate_high_quantile,
            low_quantile=gate_low_quantile,
        )
        train = add_gate_target(train_base, gate_target=gate_target, thresholds=thresholds)
        val = load_joined_gate_batches(
            context,
            window.val_batch_ids,
            feature_columns=feature_columns,
            gate_target=gate_target,
            thresholds=thresholds,
        )
        pred = load_joined_gate_batches(
            context,
            (window.pred_batch_id,),
            feature_columns=feature_columns,
            gate_target=gate_target,
            thresholds=thresholds,
        )
        X_train, y_train, _ = gate_frame_to_numpy(train, gate_target=gate_target, features=feature_columns)
        X_val, y_val, val_meta = gate_frame_to_numpy(val, gate_target=gate_target, features=feature_columns)
        X_pred, y_pred, pred_meta = gate_frame_to_numpy(pred, gate_target=gate_target, features=feature_columns)
        if len(np.unique(y_train)) < 2:
            raise ValueError(f"Training gate window has one class only: step={window.step_idx}")
        model = fit_classifier(
            X_train,
            y_train,
            X_val,
            y_val,
            model_family=MODEL_CATBOOST,
            feature_names=feature_columns,
            model_updates=model_updates,
            task_type=task_type,
            thread_count=thread_count,
        )
        val_p = validation_probability(model, X_val)
        pred_p = prediction_probability(model, X_pred)
        val_true.append(y_val)
        val_prob.append(val_p)
        pred_true.append(y_pred)
        pred_prob.append(pred_p)
        window_payloads.append(
            {
                "step_idx": int(window.step_idx),
                "pred_batch_id": int(window.pred_batch_id),
                "feature_count": len(feature_columns),
                "train_rows": int(len(y_train)),
                "val_rows": int(len(y_val)),
                "pred_rows": int(len(y_pred)),
                "train_positive_rate": float(np.mean(y_train)) if len(y_train) else None,
                "val_positive_rate": float(np.mean(y_val)) if len(y_val) else None,
                "pred_positive_rate": float(np.mean(y_pred)) if len(y_pred) else None,
                "threshold_up_high": thresholds["up_high"],
                "threshold_down_high": thresholds["down_high"],
                "threshold_up_low": thresholds["up_low"],
                "threshold_down_low": thresholds["down_low"],
                "y_val": y_val,
                "val_prob": val_p,
                "val_meta": val_meta,
                "y_pred": y_pred,
                "pred_prob": pred_p,
                "pred_meta": pred_meta,
                **_model_diagnostics(model),
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
    gate_scores: list[dict[str, Any]] = []
    for payload in window_payloads:
        val_y = payload.pop("y_val")
        val_p = payload.pop("val_prob")
        payload.pop("val_meta")
        pred_y = payload.pop("y_pred")
        pred_p = payload.pop("pred_prob")
        pred_meta = payload.pop("pred_meta")
        val_m = binary_metrics(
            val_y,
            val_p,
            threshold=threshold,
            fp_cost=fp_cost,
            fn_cost=fn_cost,
            tp_reward=tp_reward,
            fbeta_beta=fbeta_beta,
        )
        pred_m = binary_metrics(
            pred_y,
            pred_p,
            threshold=threshold,
            fp_cost=fp_cost,
            fn_cost=fn_cost,
            tp_reward=tp_reward,
            fbeta_beta=fbeta_beta,
        )
        window_metrics.append(
            {
                "gate_target": gate_target,
                **payload,
                "selected_threshold": threshold,
                **_flatten(val_m, "validation"),
                **_flatten(pred_m, "prediction"),
            }
        )
        gate_scores.extend(
            gate_score_rows(
                meta=pred_meta,
                y_true=pred_y,
                prob=pred_p,
                threshold=threshold,
                gate_target=gate_target,
                step_idx=int(payload["step_idx"]),
                pred_batch_id=int(payload["pred_batch_id"]),
            )
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
        "window_metrics": window_metrics,
        "gate_scores": gate_scores,
    }


def load_joined_gate_batches(
    context: RPFDataContext,
    batch_ids: tuple[int, ...] | list[int],
    *,
    feature_columns: tuple[str, ...],
    gate_target: str | None,
    thresholds: dict[str, float] | None = None,
) -> pl.DataFrame:
    if not batch_ids:
        raise ValueError("No batch ids requested")
    missing = [col for col in feature_columns if col not in context.manifest.feature_columns]
    if missing:
        raise ValueError(f"Requested columns not present in RPF manifest: {missing[:5]}")
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
            .drop(VALID_COL)
        )
        if gate_target is not None:
            joined = add_gate_target(joined, gate_target=gate_target, thresholds=thresholds or {})
        frames.append(joined)
    out = pl.concat(frames, how="vertical") if frames else pl.DataFrame()
    if out.is_empty():
        raise ValueError(f"Joined RPF regime-gate batches are empty: {batch_ids}")
    return out.sort(["batch_id", "timestamp"])


def train_gate_thresholds(frame: pl.DataFrame, *, high_quantile: float, low_quantile: float) -> dict[str, float]:
    return {
        "up_high": _finite_quantile(frame[UP_EXTREME], high_quantile),
        "down_high": _finite_quantile(frame[DOWN_EXTREME], high_quantile),
        "up_low": _finite_quantile(frame[UP_EXTREME], low_quantile),
        "down_low": _finite_quantile(frame[DOWN_EXTREME], low_quantile),
    }


def add_gate_target(frame: pl.DataFrame, *, gate_target: str, thresholds: dict[str, float]) -> pl.DataFrame:
    return frame.with_columns(gate_target_expr(gate_target, thresholds))


def gate_target_expr(gate_target: str, thresholds: dict[str, float]) -> pl.Expr:
    if gate_target == GATE_UP_DOMINANT:
        expr = pl.col(UP_EXTREME) >= 2.0 * pl.col(DOWN_EXTREME)
    elif gate_target == GATE_DOWN_DOMINANT:
        expr = pl.col(DOWN_EXTREME) >= 2.0 * pl.col(UP_EXTREME)
    elif gate_target == GATE_TWO_SIDED:
        expr = (pl.col(UP_EXTREME) >= float(thresholds["up_high"])) & (
            pl.col(DOWN_EXTREME) >= float(thresholds["down_high"])
        )
    elif gate_target == GATE_LOW_EDGE:
        expr = (pl.col(UP_EXTREME) <= float(thresholds["up_low"])) & (
            pl.col(DOWN_EXTREME) <= float(thresholds["down_low"])
        )
    else:
        known = ", ".join(GATE_TARGETS)
        raise ValueError(f"Unsupported regime gate target {gate_target!r}; expected one of: {known}")
    return expr.cast(pl.Int8).alias(gate_target)


def gate_rule_description(gate_target: str) -> str:
    if gate_target == GATE_UP_DOMINANT:
        return "up_extreme >= 2 * down_extreme"
    if gate_target == GATE_DOWN_DOMINANT:
        return "down_extreme >= 2 * up_extreme"
    if gate_target == GATE_TWO_SIDED:
        return "up_extreme and down_extreme are both above train-window high quantiles"
    if gate_target == GATE_LOW_EDGE:
        return "up_extreme and down_extreme are both below train-window low quantiles"
    known = ", ".join(GATE_TARGETS)
    raise ValueError(f"Unsupported regime gate target {gate_target!r}; expected one of: {known}")


def gate_frame_to_numpy(
    frame: pl.DataFrame,
    *,
    gate_target: str,
    features: tuple[str, ...],
) -> tuple[np.ndarray, np.ndarray, pl.DataFrame]:
    model_frame = frame.select(["timestamp", "batch_id", gate_target, *features]).drop_nulls([gate_target, *features])
    X = model_frame.select(features).to_numpy().astype("float64")
    y = model_frame[gate_target].to_numpy().astype("int64")
    mask = np.isfinite(X).all(axis=1)
    meta = (
        model_frame.select(["timestamp", "batch_id"])
        .with_columns(pl.Series("_model_row_mask", mask))
        .filter(pl.col("_model_row_mask"))
        .drop("_model_row_mask")
    )
    return X[mask], y[mask], meta


def gate_score_rows(
    *,
    meta: pl.DataFrame,
    y_true: np.ndarray,
    prob: np.ndarray,
    threshold: float,
    gate_target: str,
    step_idx: int,
    pred_batch_id: int,
) -> list[dict[str, Any]]:
    active = (np.asarray(prob, dtype=float) >= float(threshold)).astype(int)
    rows: list[dict[str, Any]] = []
    timestamps = meta["timestamp"].to_list()
    batch_ids = meta["batch_id"].to_list()
    for idx, value in enumerate(prob):
        rows.append(
            {
                "gate_target": gate_target,
                "step_idx": int(step_idx),
                "pred_batch_id": int(pred_batch_id),
                "timestamp": timestamps[idx],
                "batch_id": int(batch_ids[idx]),
                "gate_label": int(y_true[idx]),
                "gate_prob": float(value),
                "gate_active": int(active[idx]),
                "gate_threshold": float(threshold),
            }
        )
    return rows


def evaluate_gated_decisions(
    *,
    gate_scores: list[dict[str, Any]],
    best_trial: dict[str, Any] | None,
    classifier_score_path: Path | None,
    classifier_side: str,
    classifier_trial_number: int | None,
    classifier_threshold: float,
) -> list[dict[str, Any]]:
    if classifier_score_path is None or best_trial is None:
        return []
    path = Path(classifier_score_path)
    if not path.exists():
        raise FileNotFoundError(f"Classifier score path not found: {path}")
    trial_number = int(best_trial["trial_number"])
    gate_frame = pl.DataFrame([row for row in gate_scores if int(row["trial_number"]) == trial_number])
    if gate_frame.is_empty():
        return []
    scores = pl.read_parquet(path)
    selected_classifier_trial = classifier_trial_number
    if "trial_number" in scores.columns:
        if selected_classifier_trial is None:
            selected_classifier_trial = _best_classifier_trial_from_run(path.parent)
        if selected_classifier_trial is not None:
            scores = scores.filter(pl.col("trial_number") == int(selected_classifier_trial))
        else:
            raise ValueError(
                "Classifier score file contains multiple trials. Pass --classifier-trial-number "
                "or keep best_config.json beside the score file."
            )
    prob_col = _first_existing(scores, ("prob", "prediction_prob", "classifier_prob", "positive_probability"))
    target_col = _first_existing(scores, ("target", "label", "y_true", "classifier_target"))
    classifier = scores.select(["timestamp", "batch_id", target_col, prob_col]).rename(
        {target_col: "classifier_target", prob_col: "classifier_prob"}
    )
    joined = classifier.join(
        gate_frame.select(["timestamp", "batch_id", "gate_prob", "gate_active", "gate_threshold"]),
        on=["timestamp", "batch_id"],
        how="inner",
    )
    if joined.is_empty():
        return []
    y = joined["classifier_target"].to_numpy().astype("int64")
    prob = joined["classifier_prob"].to_numpy().astype("float64")
    gate_active = joined["gate_active"].to_numpy().astype("int64") == 1
    ungated_pred = (prob >= float(classifier_threshold)).astype("int64")
    gated_pred = ungated_pred * gate_active.astype("int64")
    ungated = metrics_from_binary_prediction(y, ungated_pred)
    gated = metrics_from_binary_prediction(y, gated_pred)
    return [
        {
            "trial_number": trial_number,
            "classifier_side": classifier_side,
            "classifier_score_path": str(path),
            "classifier_trial_number": selected_classifier_trial,
            "rows": int(len(y)),
            "gate_active_rate": float(np.mean(gate_active)) if len(gate_active) else None,
            "ungated_precision": ungated["precision"],
            "ungated_recall": ungated["recall"],
            "ungated_false_positive_rate": ungated["false_positive_rate"],
            "ungated_predicted_positive_rate": ungated["predicted_positive_rate"],
            "ungated_tp": ungated["tp"],
            "ungated_fp": ungated["fp"],
            "ungated_tn": ungated["tn"],
            "ungated_fn": ungated["fn"],
            "gated_precision": gated["precision"],
            "gated_recall": gated["recall"],
            "gated_false_positive_rate": gated["false_positive_rate"],
            "gated_predicted_positive_rate": gated["predicted_positive_rate"],
            "gated_tp": gated["tp"],
            "gated_fp": gated["fp"],
            "gated_tn": gated["tn"],
            "gated_fn": gated["fn"],
            "both_suppressed_rate": float(np.mean((ungated_pred == 1) & (~gate_active))) if len(y) else None,
            "both_active_conflict_rate": None,
            "false_positive_reduction": _relative_reduction(ungated["fp"], gated["fp"]),
            "recall_retained": _safe_ratio(gated["recall"], ungated["recall"]),
            "precision_improvement": _safe_difference(gated["precision"], ungated["precision"]),
        }
    ]


def metrics_from_binary_prediction(y_true: np.ndarray, pred: np.ndarray) -> dict[str, Any]:
    y_true = np.asarray(y_true, dtype=int)
    pred = np.asarray(pred, dtype=int)
    positives = y_true == 1
    negatives = y_true == 0
    tp = int(np.sum((pred == 1) & positives))
    tn = int(np.sum((pred == 0) & negatives))
    fp = int(np.sum((pred == 1) & negatives))
    fn = int(np.sum((pred == 0) & positives))
    precision = None if tp + fp == 0 else float(tp / (tp + fp))
    recall = None if tp + fn == 0 else float(tp / (tp + fn))
    false_positive_rate = None if fp + tn == 0 else float(fp / (fp + tn))
    predicted_positive_rate = float(np.mean(pred)) if len(pred) else None
    return {
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "false_positive_rate": false_positive_rate,
        "predicted_positive_rate": predicted_positive_rate,
    }


def _best_classifier_trial_from_run(run_root: Path) -> int | None:
    path = Path(run_root) / "best_config.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text())
    best = payload.get("best") or {}
    if "trial_number" not in best:
        return None
    return int(best["trial_number"])


def _finite_quantile(series: pl.Series, quantile: float) -> float:
    values = np.asarray(series.to_numpy(), dtype=float)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        raise ValueError("Cannot compute gate quantile from empty finite values")
    return float(np.quantile(values, float(quantile)))


def _first_existing(frame: pl.DataFrame, names: tuple[str, ...]) -> str:
    for name in names:
        if name in frame.columns:
            return name
    raise ValueError(f"Expected one of columns {names}, found {frame.columns}")


def _relative_reduction(before: int | float | None, after: int | float | None) -> float | None:
    if before is None or after is None or float(before) == 0.0:
        return None
    return float((float(before) - float(after)) / float(before))


def _safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or float(denominator) == 0.0:
        return None
    return float(float(numerator) / float(denominator))


def _safe_difference(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return float(float(left) - float(right))


def _best_trial(trials: list[dict[str, Any]]) -> dict[str, Any] | None:
    ok_trials = [trial for trial in trials if str(trial.get("status", "")).startswith("ok")]
    pool = ok_trials or trials
    if not pool:
        return None
    direction = str(pool[0].get("objective_direction") or "minimize")
    key = lambda row: _none_to_bad(row.get("objective_value"), minimize=(direction == "minimize"))
    return min(pool, key=key) if direction == "minimize" else max(pool, key=key)


def _none_to_bad(value: Any, *, minimize: bool) -> float:
    if value is None:
        return 1e9 if minimize else -1e9
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 1e9 if minimize else -1e9
    if not np.isfinite(number):
        return 1e9 if minimize else -1e9
    return number


def _model_diagnostics(model: Any) -> dict[str, int | None]:
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


def _write_rows_parquet(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        pl.DataFrame(rows, infer_schema_length=None).write_parquet(path)
    else:
        pl.DataFrame().write_parquet(path)


def _run_root(args: argparse.Namespace, gate_target: str) -> Path:
    now = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return Path(args.output_dir) / f"{now}_regime_gate_{gate_target}"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run RPF regime-gate walk-forward experiments.")
    parser.add_argument("--asset", default=None)
    parser.add_argument("--root", default=None)
    parser.add_argument("--gate-target", choices=GATE_TARGETS, default=GATE_UP_DOMINANT)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--base-run", type=Path, required=True)
    parser.add_argument("--feature-ablation", default="all")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--n-steps", type=int, default=15)
    parser.add_argument("--max-configs", type=int, default=12)
    parser.add_argument("--window-mode", choices=WINDOW_MODES, default=CHRONOLOGICAL_RECENT)
    parser.add_argument("--positive-batch-min-rate", type=float, default=0.80)
    parser.add_argument("--opposite-batch-max-rate", type=float, default=0.20)
    parser.add_argument("--train-positive-batches", type=int, default=80)
    parser.add_argument("--train-negative-batches", type=int, default=160)
    parser.add_argument("--val-positive-batches", type=int, default=20)
    parser.add_argument("--val-negative-batches", type=int, default=40)
    parser.add_argument("--candidate-lookback-batches", type=int, default=2000)
    parser.add_argument("--label-maturity-embargo-batches", type=int, default=1)
    parser.add_argument("--recent-train-batches", type=int, default=40)
    parser.add_argument("--recent-val-batches", type=int, default=10)
    parser.add_argument("--task-type", choices=["CPU", "GPU"], default="CPU")
    parser.add_argument("--thread-count", type=int, default=-1)
    parser.add_argument("--iterations-choices", default="400,800")
    parser.add_argument("--depth-choices", default="2,3")
    parser.add_argument("--learning-rate-choices", default="0.01,0.02")
    parser.add_argument("--l2-leaf-reg-choices", default="10,30")
    parser.add_argument("--early-stopping-rounds-choices", default="100")
    parser.add_argument("--od-wait-choices", default="100")
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
        default="validation_decision_cost",
    )
    parser.add_argument("--threshold-mode", choices=["fixed", "validation_sweep"], default="validation_sweep")
    parser.add_argument("--decision-threshold", type=float, default=0.5)
    parser.add_argument(
        "--threshold-grid",
        default="0.10,0.15,0.20,0.25,0.30,0.35,0.40,0.45,0.50,0.55,0.60,0.65,0.70,0.75,0.80,0.85,0.90",
    )
    parser.add_argument("--fp-cost", type=float, default=3.0)
    parser.add_argument("--fn-cost", type=float, default=1.0)
    parser.add_argument("--tp-reward", type=float, default=0.0)
    parser.add_argument("--fbeta-beta", type=float, default=0.5)
    parser.add_argument("--min-validation-recall", type=float, default=0.0)
    parser.add_argument("--min-validation-precision", type=float, default=0.0)
    parser.add_argument("--min-validation-predicted-positive-rate", type=float, default=0.0)
    parser.add_argument("--max-validation-false-positive-rate", type=float, default=1.0)
    parser.add_argument("--min-prediction-unique", type=int, default=10)
    parser.add_argument("--min-prediction-std", type=float, default=1e-6)
    parser.add_argument("--gate-high-quantile", type=float, default=0.70)
    parser.add_argument("--gate-low-quantile", type=float, default=0.30)
    parser.add_argument("--classifier-score-path", type=Path, default=None)
    parser.add_argument("--classifier-side", choices=["up", "down"], default="up")
    parser.add_argument("--classifier-trial-number", type=int, default=None)
    parser.add_argument("--classifier-threshold", type=float, default=0.5)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
