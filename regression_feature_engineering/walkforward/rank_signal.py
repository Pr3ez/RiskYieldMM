"""RPF ranked-signal walk-forward runner.

This command is intentionally separate from the binary classifier runner.  It
optimizes the row ordering inside each prediction batch, then applies a
live-safe causal signal budget in timestamp order.
"""

from __future__ import annotations

import argparse
import json
import time
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from regression_feature_engineering.walkforward.ablation import select_ablation_features
from regression_feature_engineering.walkforward.classification.sequence import (
    SEQUENCE_CAUSAL_CNN_V1,
    SEQUENCE_NONE,
    CausalCNNEmbedder,
    SequenceEmbeddingConfig,
    fit_causal_cnn_embedder,
)
from regression_feature_engineering.walkforward.classification.targets import (
    DOWN_EXTREME,
    UP_EXTREME,
)
from regression_feature_engineering.walkforward.config import load_clean_config
from regression_feature_engineering.walkforward.data import RPFDataContext, VALID_COL, resolve_context
from regression_feature_engineering.walkforward.policy import load_panel_features
from regression_feature_engineering.walkforward.reports import (
    append_event,
    write_json,
    write_markdown,
    write_stage_status,
    write_trials,
)
from regression_feature_engineering.walkforward.windows import RPFWindow, build_windows, read_windows
from scripts.project_paths import ensure_project_root_on_path


PROJECT_ROOT = ensure_project_root_on_path(Path(__file__))
OUTPUT_ROOT = PROJECT_ROOT / "test_output" / "rpf_ranked_signal"

SIDE_UP = "up"
SIDE_DOWN = "down"
SIDES = (SIDE_UP, SIDE_DOWN)

FEATURE_SELECTOR_ELASTICNET_RELEVANCE_V1 = "elasticnet_relevance_v1"
FEATURE_SELECTORS = (FEATURE_SELECTOR_ELASTICNET_RELEVANCE_V1,)

SEQUENCE_CAUSAL_ROCKET_V1 = "causal_rocket_v1"
SEQUENCE_MODES = (SEQUENCE_NONE, SEQUENCE_CAUSAL_ROCKET_V1, SEQUENCE_CAUSAL_CNN_V1)

RANK_LOSSES = ("YetiRank", "PairLogit", "QueryRMSE")
BATCH_STATE_GATE_OFF = "off"
BATCH_STATE_GATE_LOGISTIC_PREFIX_V1 = "logistic_prefix_v1"
BATCH_STATE_GATE_MODES = (BATCH_STATE_GATE_OFF, BATCH_STATE_GATE_LOGISTIC_PREFIX_V1)


@dataclass(frozen=True)
class ElasticNetRelevanceConfig:
    alpha: float = 0.01
    l1_ratio: float = 0.5
    max_features: int = 80
    min_features: int = 10
    coef_eps: float = 1e-8
    prefilter_features: int = 160
    max_iter: int = 2000
    tol: float = 0.001


@dataclass(frozen=True)
class RocketConfig:
    mode: str = SEQUENCE_NONE
    sequence_length: int = 16
    n_kernels: int = 128
    seed: int = 42
    cnn_embedding_dim: int = 8
    cnn_conv_channels: int = 16
    cnn_kernel_size: int = 3
    cnn_epochs: int = 1
    cnn_batch_size: int = 512
    cnn_max_train_rows: int = 8000
    cnn_device: str = "cpu"


@dataclass(frozen=True)
class RankModelConfig:
    rank_loss: str = "YetiRank"
    iterations: int = 400
    depth: int = 3
    learning_rate: float = 0.01
    l2_leaf_reg: float = 100.0
    random_strength: float = 1.0
    early_stopping_rounds: int = 100
    od_wait: int = 100


@dataclass(frozen=True)
class DecisionConfig:
    threshold_quantile: float = 0.95
    max_signals_per_batch: int = 10
    fp_cost: float = 5.0
    fn_cost: float = 1.0
    high_target_positive_rate_threshold: float = 0.20
    high_false_positive_rate_threshold: float = 0.30


@dataclass(frozen=True)
class BatchStateGateConfig:
    mode: str = BATCH_STATE_GATE_OFF
    prefix_rows: int = 60
    min_positive_rate: float = 0.20
    probability_threshold: float = 0.55
    c: float = 0.5
    max_iter: int = 1000
    min_train_batches: int = 20
    min_positive_batches: int = 3
    min_negative_batches: int = 3


@dataclass(frozen=True)
class RankTrialConfig:
    train_batches: int = 120
    val_batches: int = 10
    elasticnet: ElasticNetRelevanceConfig = ElasticNetRelevanceConfig()
    sequence: RocketConfig = RocketConfig()
    model: RankModelConfig = RankModelConfig()
    decision: DecisionConfig = DecisionConfig()
    batch_state_gate: BatchStateGateConfig = BatchStateGateConfig()


@dataclass(frozen=True)
class ElasticNetSelectionResult:
    selected_features: tuple[str, ...]
    selected_indexes: np.ndarray
    means: np.ndarray
    stds: np.ndarray
    detail: pl.DataFrame


@dataclass(frozen=True)
class RocketKernel:
    channel: int
    length: int
    weights: tuple[float, ...]
    bias: float


def main() -> int:
    args = parse_args()
    try:
        import optuna
    except Exception as exc:  # pragma: no cover - depends on active environment
        raise RuntimeError("Optuna is required for ranked-signal optimization") from exc

    config = load_clean_config(args.config)
    asset = str(args.asset or config.asset)
    root = str(args.root or config.root)
    side = str(args.side)
    context_target_col = UP_EXTREME if side == SIDE_UP else DOWN_EXTREME
    context = resolve_context(project_root=PROJECT_ROOT, asset=asset, root=root, target_col=context_target_col)
    run_root = run_root_for_args(args, asset=asset, root=root, side=side)
    run_root.mkdir(parents=True, exist_ok=True)
    events_path = run_root / "events.jsonl"
    append_event(events_path, "stage_start", command="rank_signal", asset=asset, root=root, side=side)

    all_base_windows = read_windows(Path(args.base_run) / "frozen_windows.parquet")
    if not all_base_windows:
        raise ValueError("No frozen windows found in --base-run")
    batch_index_path = Path(args.base_run) / "batch_index.parquet"
    batch_index = pl.read_parquet(batch_index_path) if batch_index_path.exists() else None

    feature_columns = select_ablation_features(context.manifest.feature_columns, str(args.feature_ablation))
    if args.tabular_panel_path:
        feature_columns = load_panel_features(args.tabular_panel_path, feature_columns)
    sequence_feature_columns = (
        load_panel_features(args.sequence_panel_path, context.manifest.feature_columns)
        if args.sequence_panel_path
        else ()
    )
    if str(args.sequence_mode) != SEQUENCE_NONE and not sequence_feature_columns:
        raise ValueError("--sequence-panel-path is required when --sequence-mode is not none")

    search_space = build_search_space(args)
    sampler = optuna.samplers.GridSampler(search_space, seed=int(args.seed))
    study = optuna.create_study(direction="maximize", sampler=sampler)

    trials: list[dict[str, Any]] = []
    window_rows: list[dict[str, Any]] = []
    score_rows: list[dict[str, Any]] = []
    decision_rows: list[dict[str, Any]] = []
    selected_feature_rows: list[dict[str, Any]] = []
    sequence_rows: list[dict[str, Any]] = []

    print(
        "[rpf-rank] start "
        f"asset={asset} root={root} side={side} trials={int(args.n_trials)} "
        f"features={len(feature_columns)} sequence_features={len(sequence_feature_columns)} run={run_root}",
        flush=True,
    )

    def objective(trial: Any) -> float:
        trial_config = trial_config_from_trial(trial, args)
        windows = windows_for_trial(
            base_windows=all_base_windows,
            batch_index=batch_index,
            trial_config=trial_config,
            n_steps=int(args.n_steps),
            window_end_offset_steps=int(args.window_end_offset_steps),
        )
        tuning_windows, _ = split_tuning_holdout_windows(windows, int(args.holdout_steps))
        if not tuning_windows:
            raise ValueError("No tuning windows after applying --holdout-steps")
        trial_number = int(trial.number)
        print(
            "[rpf-rank] trial_start "
            f"trial={trial_number} windows={len(tuning_windows)} side={side} "
            f"rank_loss={trial_config.model.rank_loss} seq={trial_config.sequence.mode} "
            f"features=elasticnet:max{trial_config.elasticnet.max_features}:a{trial_config.elasticnet.alpha}:"
            f"l1{trial_config.elasticnet.l1_ratio} "
            f"it={trial_config.model.iterations} depth={trial_config.model.depth} "
            f"lr={trial_config.model.learning_rate}",
            flush=True,
        )
        try:
            payload = run_rank_windows(
                context=context,
                windows=tuning_windows,
                side=side,
                feature_columns=feature_columns,
                sequence_feature_columns=sequence_feature_columns,
                config=trial_config,
                task_type=str(args.task_type),
                thread_count=int(args.thread_count),
                log_every_windows=int(args.log_every_windows),
            )
            status = "ok"
        except Exception as exc:
            payload = failed_payload(exc)
            status = "error"
            append_event(
                events_path,
                "trial_error",
                trial_number=trial_number,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            print(
                "[rpf-rank] trial_error "
                f"trial={trial_number} error_type={type(exc).__name__} error={str(exc)}",
                flush=True,
            )
        row = trial_summary_row(trial_number, status, trial_config, payload)
        row["optuna_params_json"] = json.dumps(dict(trial.params), sort_keys=True)
        trials.append(row)
        for item in payload.get("window_metrics", []):
            window_rows.append({"trial_number": trial_number, **item})
        for item in payload.get("prediction_scores", []):
            score_rows.append({"trial_number": trial_number, **item})
            if int(item.get("decision", 0)) == 1:
                decision_rows.append({"trial_number": trial_number, **item})
        selected_feature_rows.extend({"trial_number": trial_number, **item} for item in payload.get("selected_features", []))
        sequence_rows.extend({"trial_number": trial_number, **item} for item in payload.get("sequence_diagnostics", []))
        print(
            "[rpf-rank] trial_done "
            f"trial={trial_number} status={status} score={float(payload.get('objective_value', -1e9)):.6g} "
            f"precision={fmt(payload.get('prediction_precision'))} "
            f"lift={fmt(payload.get('prediction_precision_lift'))} "
            f"active_windows={fmt(payload.get('prediction_active_window_rate'))} "
            f"missed_high={fmt(payload.get('prediction_missed_high_target_window_rate'))}",
            flush=True,
        )
        write_partial_outputs(run_root, trials, window_rows, score_rows, decision_rows, selected_feature_rows, sequence_rows)
        return float(payload.get("objective_value", -1e9))

    study.optimize(objective, n_trials=int(args.n_trials))
    best = max(trials, key=lambda row: float(row.get("objective_value", -1e9))) if trials else {}
    best_config = json.loads(str(best.get("trial_config_json", "{}"))) if best else {}
    write_json(run_root / "best_config.json", {"best_trial": best, "best_config": best_config})

    holdout_payload = {"status": "skipped:no_holdout_windows"}
    wrote_holdout_tables = False
    if best_config:
        holdout_windows = holdout_windows_for_best(
            base_windows=all_base_windows,
            batch_index=batch_index,
            best_config=best_config,
            n_steps=int(args.n_steps),
            holdout_steps=int(args.holdout_steps),
            window_end_offset_steps=int(args.window_end_offset_steps),
        )
        if holdout_windows:
            holdout_payload = run_rank_windows(
                context=context,
                windows=holdout_windows,
                side=side,
                feature_columns=feature_columns,
                sequence_feature_columns=sequence_feature_columns,
                config=trial_config_from_payload(best_config),
                task_type=str(args.task_type),
                thread_count=int(args.thread_count),
                log_every_windows=int(args.log_every_windows),
            )
            write_rows_parquet(run_root / "holdout_window_metrics.parquet", holdout_payload["window_metrics"])
            write_rows_parquet(run_root / "holdout_prediction_scores.parquet", holdout_payload["prediction_scores"])
            wrote_holdout_tables = True
    if not wrote_holdout_tables:
        write_rows_parquet(run_root / "holdout_window_metrics.parquet", [])
        write_rows_parquet(run_root / "holdout_prediction_scores.parquet", [])
    write_json(run_root / "holdout_summary.json", summarize_holdout(holdout_payload))

    write_partial_outputs(run_root, trials, window_rows, score_rows, decision_rows, selected_feature_rows, sequence_rows)
    write_stage_status(
        run_root / "stage_status.json",
        stage="rank_signal",
        status="complete",
        summary={
            "asset": asset,
            "root": root,
            "side": side,
            "trial_count": len(trials),
            "n_steps": int(args.n_steps),
            "holdout_steps": int(args.holdout_steps),
            "window_end_offset_steps": int(args.window_end_offset_steps),
            "best_objective_value": best.get("objective_value") if best else None,
            "best_status": best.get("status") if best else None,
            "holdout_status": holdout_payload.get("status", "ok") if isinstance(holdout_payload, dict) else "ok",
        },
    )
    write_rank_report(run_root, asset=asset, root=root, side=side, best=best, holdout=holdout_payload)
    append_event(events_path, "stage_done", run=str(run_root), best_objective=best.get("objective_value") if best else None)
    print(f"[rpf-rank] done run={run_root}", flush=True)
    return 0


def run_rank_windows(
    *,
    context: RPFDataContext,
    windows: list[RPFWindow],
    side: str,
    feature_columns: tuple[str, ...],
    sequence_feature_columns: tuple[str, ...],
    config: RankTrialConfig,
    task_type: str,
    thread_count: int,
    log_every_windows: int,
) -> dict[str, Any]:
    prediction_scores: list[dict[str, Any]] = []
    selected_feature_rows: list[dict[str, Any]] = []
    sequence_diagnostics: list[dict[str, Any]] = []
    window_metrics: list[dict[str, Any]] = []
    all_y: list[np.ndarray] = []
    all_decisions: list[np.ndarray] = []
    selected_counts: list[int] = []
    log_every = max(0, int(log_every_windows))
    for window_idx, window in enumerate(windows, start=1):
        started = time.perf_counter()
        if log_every and (window_idx == 1 or window_idx == len(windows) or window_idx % log_every == 0):
            print(f"[rpf-rank] window_start {window_idx}/{len(windows)} pred_batch={window.pred_batch_id}", flush=True)
        fold = run_rank_fold(
            context=context,
            window=window,
            side=side,
            feature_columns=feature_columns,
            sequence_feature_columns=sequence_feature_columns,
            config=config,
            task_type=task_type,
            thread_count=thread_count,
            started=started,
        )
        selected_counts.append(int(fold["selected_feature_count"]))
        sequence_diagnostics.append(fold["sequence_diagnostics"])
        window_row = fold["prediction_window_metric"]
        window_metrics.append(window_row)
        all_y.append(fold["prediction_y_binary"])
        all_decisions.append(fold["prediction_decision"])
        prediction_scores.extend(fold["prediction_scores"])
        selected_feature_rows.extend(fold["selected_features"])
        if log_every and (window_idx == 1 or window_idx == len(windows) or window_idx % log_every == 0):
            print(
                "[rpf-rank] window_done "
                f"{window_idx}/{len(windows)} pred_batch={window.pred_batch_id} "
                f"features={int(fold['selected_feature_count'])} threshold={float(fold['threshold']):.6g} "
                f"max_signals={int(fold['max_signals'])} precision={fmt(window_row.get('precision'))} "
                f"signals={window_row.get('predicted_positive_count')} elapsed_s={window_row.get('elapsed_s'):.2f}",
                flush=True,
            )
    if not all_y:
        raise ValueError("No executable ranked-signal windows")
    aggregate = aggregate_prediction_metrics(
        np.concatenate(all_y),
        np.concatenate(all_decisions),
        window_metrics,
        fp_cost=float(config.decision.fp_cost),
        fn_cost=float(config.decision.fn_cost),
        selected_feature_count_mean=float(np.mean(selected_counts)) if selected_counts else 0.0,
    )
    payload = {
        "objective_value": aggregate["ranked_signal_quality"],
        "prediction_precision": aggregate["precision"],
        "prediction_precision_lift": aggregate["precision_lift"],
        "prediction_active_window_rate": aggregate["active_window_rate"],
        "prediction_missed_high_target_window_rate": aggregate["missed_high_target_window_rate"],
        "prediction_metrics": aggregate,
        "window_metrics": window_metrics,
        "prediction_scores": prediction_scores,
        "selected_features": selected_feature_rows,
        "sequence_diagnostics": sequence_diagnostics,
    }
    return payload


def run_rank_fold(
    *,
    context: RPFDataContext,
    window: RPFWindow,
    side: str,
    feature_columns: tuple[str, ...],
    sequence_feature_columns: tuple[str, ...],
    config: RankTrialConfig,
    task_type: str,
    thread_count: int,
    started: float | None = None,
) -> dict[str, Any]:
    started = time.perf_counter() if started is None else float(started)
    load_cols = tuple(dict.fromkeys((*feature_columns, *sequence_feature_columns)))
    train = load_joined_rank_batches(context, window.train_batch_ids, feature_columns=load_cols, side=side)
    val = load_joined_rank_batches(context, window.val_batch_ids, feature_columns=load_cols, side=side)
    pred = load_joined_rank_batches(context, (window.pred_batch_id,), feature_columns=load_cols, side=side)

    X_train_all, X_seq_train, y_rel_train, y_bin_train, group_train, _ = rank_numpy_with_sequence(
        train,
        features=feature_columns,
        sequence_features=sequence_feature_columns,
    )
    X_val_all, X_seq_val, y_rel_val, y_bin_val, group_val, val_meta = rank_numpy_with_sequence(
        val,
        features=feature_columns,
        sequence_features=sequence_feature_columns,
    )
    X_pred_all, X_seq_pred, y_rel_pred, y_bin_pred, group_pred, pred_meta = rank_numpy_with_sequence(
        pred,
        features=feature_columns,
        sequence_features=sequence_feature_columns,
    )
    ensure_two_relevance_levels(y_rel_train)
    selection = select_elasticnet_relevance_features(
        X_train_all,
        y_rel_train,
        feature_columns,
        config.elasticnet,
    )
    X_train = transform_selected(X_train_all, selection)
    X_val = transform_selected(X_val_all, selection)
    X_pred = transform_selected(X_pred_all, selection)
    X_train, X_val, X_pred, seq_rows = append_sequence_features(
        X_train=X_train,
        X_val=X_val,
        X_pred=X_pred,
        X_seq_train=X_seq_train,
        X_seq_val=X_seq_val,
        X_seq_pred=X_seq_pred,
        y_binary_train=y_bin_train,
        config=config.sequence,
    )
    model = fit_catboost_ranker(
        X_train,
        y_rel_train,
        group_train,
        X_val,
        y_rel_val,
        group_val,
        config=config.model,
        task_type=task_type,
        thread_count=thread_count,
    )
    val_score = np.asarray(model.predict(X_val), dtype=float)
    threshold, max_signals, val_threshold_metrics = select_rank_decision_rule(
        y_bin_val,
        val_score,
        group_val,
        val_meta,
        config.decision,
    )
    val_decision = causal_signal_budget_decisions(
        val_score,
        group_val,
        val_meta["timestamp"].to_list(),
        threshold=threshold,
        max_signals=max_signals,
    )
    pred_score = np.asarray(model.predict(X_pred), dtype=float)
    pred_decision = causal_signal_budget_decisions(
        pred_score,
        group_pred,
        pred_meta["timestamp"].to_list(),
        threshold=threshold,
        max_signals=max_signals,
    )
    val_decision_raw = val_decision.copy()
    pred_decision_raw = pred_decision.copy()
    batch_gate = fit_apply_batch_state_gate(
        X_train=X_train,
        y_train=y_bin_train,
        group_train=group_train,
        X_val=X_val,
        y_val=y_bin_val,
        group_val=group_val,
        X_pred=X_pred,
        y_pred=y_bin_pred,
        group_pred=group_pred,
        config=config.batch_state_gate,
    )
    val_decision = apply_batch_state_gate_to_decisions(
        val_decision,
        group_val,
        batch_gate.get("validation_group_pass", {}),
        prefix_rows=int(config.batch_state_gate.prefix_rows),
        mode=str(config.batch_state_gate.mode),
    )
    pred_decision = apply_batch_state_gate_to_decisions(
        pred_decision,
        group_pred,
        batch_gate.get("prediction_group_pass", {}),
        prefix_rows=int(config.batch_state_gate.prefix_rows),
        mode=str(config.batch_state_gate.mode),
    )
    validation_window_metrics = group_metric_rows(
        split="validation",
        step_idx=int(window.step_idx),
        pred_batch_id=int(window.pred_batch_id),
        meta=val_meta,
        y_binary=y_bin_val,
        score=val_score,
        decision=val_decision,
        config=config.decision,
        selected_feature_count=len(selection.selected_features),
        threshold=threshold,
        max_signals=max_signals,
        elapsed_s=None,
        validation_threshold_score=val_threshold_metrics.get("ranked_signal_quality"),
    )
    validation_window_metrics = add_batch_gate_to_group_metrics(
        validation_window_metrics,
        batch_gate.get("validation_group_diagnostics", {}),
    )
    validation_metrics = aggregate_prediction_metrics(
        y_bin_val,
        val_decision,
        validation_window_metrics,
        fp_cost=float(config.decision.fp_cost),
        fn_cost=float(config.decision.fn_cost),
        selected_feature_count_mean=float(len(selection.selected_features)),
    )
    prediction_window_metric = window_metric_row(
        split="prediction",
        window=window,
        y_binary=y_bin_pred,
        score=pred_score,
        decision=pred_decision,
        config=config.decision,
        selected_feature_count=len(selection.selected_features),
        threshold=threshold,
        max_signals=max_signals,
        elapsed_s=time.perf_counter() - started,
        validation_threshold_score=val_threshold_metrics.get("ranked_signal_quality"),
    )
    prediction_window_metric.update(batch_gate.get("prediction_diagnostics", {}))
    validation_scores = score_rows(
        split="validation",
        side=side,
        target_col=binary_col(side),
        window=window,
        meta=val_meta,
        y_relevance=y_rel_val,
        y_binary=y_bin_val,
        score=val_score,
        decision=val_decision,
        threshold=threshold,
        max_signals=max_signals,
    )
    prediction_scores = score_rows(
        split="prediction",
        side=side,
        target_col=binary_col(side),
        window=window,
        meta=pred_meta,
        y_relevance=y_rel_pred,
        y_binary=y_bin_pred,
        score=pred_score,
        decision=pred_decision,
        threshold=threshold,
        max_signals=max_signals,
    )
    add_score_gate_fields(validation_scores, val_decision_raw, batch_gate.get("validation_group_diagnostics", {}), config.batch_state_gate)
    add_score_gate_fields(prediction_scores, pred_decision_raw, batch_gate.get("prediction_group_diagnostics", {}), config.batch_state_gate)
    return {
        "window": window,
        "selected_feature_count": int(len(selection.selected_features)),
        "threshold": float(threshold),
        "max_signals": int(max_signals),
        "validation_metrics": validation_metrics,
        "validation_window_metrics": validation_window_metrics,
        "validation_y_binary": y_bin_val,
        "validation_decision": val_decision,
        "validation_decision_raw": val_decision_raw,
        "validation_scores": validation_scores,
        "prediction_window_metric": prediction_window_metric,
        "prediction_y_binary": y_bin_pred,
        "prediction_decision": pred_decision,
        "prediction_decision_raw": pred_decision_raw,
        "prediction_scores": prediction_scores,
        "batch_state_gate": gate_payload_without_arrays(batch_gate),
        "selected_features": selected_feature_detail_rows(
            selection,
            step_idx=int(window.step_idx),
            pred_batch_id=int(window.pred_batch_id),
            side=side,
        ),
        "sequence_diagnostics": {
            "step_idx": int(window.step_idx),
            "pred_batch_id": int(window.pred_batch_id),
            **seq_rows,
        },
    }


def load_joined_rank_batches(
    context: RPFDataContext,
    batch_ids: tuple[int, ...] | list[int],
    *,
    feature_columns: tuple[str, ...],
    side: str,
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
            .with_columns(
                relevance_expr(side).alias(relevance_col(side)),
                binary_expr(side).alias(binary_col(side)),
            )
            .drop(VALID_COL)
        )
        frames.append(joined)
    if not frames:
        raise ValueError("No batch ids supplied")
    out = pl.concat(frames, how="vertical")
    if out.is_empty():
        raise ValueError(f"Joined ranked-signal batches are empty: {batch_ids}")
    return out.sort(["batch_id", "timestamp"])


def relevance_expr(side: str) -> pl.Expr:
    denominator = pl.col(UP_EXTREME) + pl.col(DOWN_EXTREME) + 1e-12
    if side == SIDE_UP:
        return (pl.col(UP_EXTREME) / denominator).clip(0.0, 1.0)
    if side == SIDE_DOWN:
        return (pl.col(DOWN_EXTREME) / denominator).clip(0.0, 1.0)
    raise ValueError(f"Unsupported side: {side}")


def binary_expr(side: str) -> pl.Expr:
    if side == SIDE_UP:
        return ((pl.col(UP_EXTREME) > 0.0) & (pl.col(UP_EXTREME) >= 2.0 * pl.col(DOWN_EXTREME))).cast(pl.Int8)
    if side == SIDE_DOWN:
        return ((pl.col(DOWN_EXTREME) > 0.0) & (pl.col(DOWN_EXTREME) >= 2.0 * pl.col(UP_EXTREME))).cast(pl.Int8)
    raise ValueError(f"Unsupported side: {side}")


def relevance_col(side: str) -> str:
    return f"rpf_rank_{side}_relevance"


def binary_col(side: str) -> str:
    return f"rpf_rank_{side}_binary_positive"


def rank_numpy_with_sequence(
    frame: pl.DataFrame,
    *,
    features: tuple[str, ...],
    sequence_features: tuple[str, ...],
) -> tuple[np.ndarray, np.ndarray | None, np.ndarray, np.ndarray, np.ndarray, pl.DataFrame]:
    rel_cols = [col for col in frame.columns if col.startswith("rpf_rank_") and col.endswith("_relevance")]
    bin_cols = [col for col in frame.columns if col.startswith("rpf_rank_") and col.endswith("_binary_positive")]
    if len(rel_cols) != 1 or len(bin_cols) != 1:
        raise ValueError("Rank frame must contain exactly one relevance and one binary target column")
    all_features = tuple(dict.fromkeys((*features, *sequence_features)))
    cols = [rel_cols[0], bin_cols[0], *all_features]
    model_frame = frame.select(cols).drop_nulls(cols)
    X_all = model_frame.select(all_features).to_numpy().astype("float32", copy=False)
    finite = np.isfinite(X_all).all(axis=1)
    X_tab = model_frame.select(features).to_numpy().astype("float32", copy=False)[finite]
    X_seq = (
        model_frame.select(sequence_features).to_numpy().astype("float32", copy=False)[finite]
        if sequence_features
        else None
    )
    y_rel = model_frame[rel_cols[0]].to_numpy().astype("float32", copy=False)[finite]
    y_bin = model_frame[bin_cols[0]].to_numpy().astype("int8", copy=False)[finite]
    meta = (
        frame.select(["timestamp", "batch_id", rel_cols[0], bin_cols[0], *all_features])
        .drop_nulls([rel_cols[0], bin_cols[0], *all_features])
        .select(["timestamp", "batch_id"])
        .with_columns(pl.Series("_finite", finite))
        .filter(pl.col("_finite"))
        .drop("_finite")
    )
    groups = meta["batch_id"].to_numpy().astype("int64", copy=False)
    return X_tab, X_seq, y_rel, y_bin, groups, meta


def select_elasticnet_relevance_features(
    X_train: np.ndarray,
    y_relevance: np.ndarray,
    feature_columns: tuple[str, ...],
    config: ElasticNetRelevanceConfig,
) -> ElasticNetSelectionResult:
    try:
        from sklearn.linear_model import ElasticNet
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("scikit-learn is required for elasticnet_relevance_v1") from exc

    X = np.asarray(X_train, dtype=np.float32)
    y = np.asarray(y_relevance, dtype=np.float32)
    means = np.nanmean(X, axis=0).astype("float32")
    stds = np.nanstd(X, axis=0).astype("float32")
    usable = np.isfinite(means) & np.isfinite(stds) & (stds > 1e-12) & np.isfinite(X).all(axis=0)
    usable_idx = np.flatnonzero(usable)
    if usable_idx.size < int(config.min_features):
        raise ValueError(f"Only {usable_idx.size} usable rank features; min_features={config.min_features}")
    candidate_idx = relevance_prefilter_indexes(
        X,
        y,
        usable_idx,
        means,
        stds,
        max_candidates=int(config.prefilter_features),
        min_features=int(config.min_features),
    )
    X_use = ((X[:, candidate_idx] - means[candidate_idx]) / stds[candidate_idx]).astype("float32", copy=False)
    X_use = np.nan_to_num(X_use, copy=False, nan=0.0, posinf=0.0, neginf=0.0)
    model = ElasticNet(
        alpha=float(config.alpha),
        l1_ratio=float(config.l1_ratio),
        max_iter=int(config.max_iter),
        tol=float(config.tol),
        random_state=42,
        selection="cyclic",
    )
    model.fit(X_use, y)
    coef = np.asarray(model.coef_, dtype=float)
    nonzero = np.flatnonzero(np.abs(coef) > float(config.coef_eps))
    if nonzero.size < int(config.min_features):
        raise ValueError(f"Only {nonzero.size} nonzero ElasticNet relevance features; min_features={config.min_features}")
    order = nonzero[np.argsort(np.abs(coef[nonzero]))[::-1]]
    selected_candidate_idx = order[: int(config.max_features)] if int(config.max_features) > 0 else order
    selected_idx = candidate_idx[selected_candidate_idx]
    selected = tuple(str(feature_columns[idx]) for idx in selected_idx)
    candidate_rank = {int(idx): rank for rank, idx in enumerate(candidate_idx, start=1)}
    coef_by_idx = {int(candidate_idx[idx]): float(coef[idx]) for idx in range(len(candidate_idx))}
    selected_set = set(int(idx) for idx in selected_idx)
    rows: list[dict[str, Any]] = []
    for idx, feature in enumerate(feature_columns):
        coef_value = coef_by_idx.get(idx)
        if idx in selected_set:
            status = "selected"
            drop_reason = None
        elif not bool(usable[idx]):
            status = "constant_or_nonfinite"
            drop_reason = status
        elif idx not in candidate_rank:
            status = "below_elasticnet_prefilter"
            drop_reason = status
        elif coef_value is None or abs(coef_value) <= float(config.coef_eps):
            status = "zero_coefficient"
            drop_reason = status
        else:
            status = "below_top_max_features"
            drop_reason = status
        rows.append(
            {
                "feature": str(feature),
                "coefficient": coef_value,
                "abs_coefficient": None if coef_value is None else abs(float(coef_value)),
                "elasticnet_prefilter_rank": candidate_rank.get(idx),
                "feature_mean_train": float(means[idx]) if np.isfinite(means[idx]) else None,
                "feature_std_train": float(stds[idx]) if np.isfinite(stds[idx]) else None,
                "final_status": status,
                "drop_reason": drop_reason,
            }
        )
    return ElasticNetSelectionResult(
        selected_features=selected,
        selected_indexes=selected_idx.astype(np.int64, copy=False),
        means=means,
        stds=stds,
        detail=pl.DataFrame(rows, infer_schema_length=None),
    )


def relevance_prefilter_indexes(
    X: np.ndarray,
    y: np.ndarray,
    usable_idx: np.ndarray,
    means: np.ndarray,
    stds: np.ndarray,
    *,
    max_candidates: int,
    min_features: int,
) -> np.ndarray:
    if int(max_candidates) <= 0 or int(max_candidates) >= int(usable_idx.size):
        return usable_idx
    y_std = float(np.std(y))
    if y_std <= 1e-12:
        scores = np.zeros(len(usable_idx), dtype=float)
    else:
        yz = (y - float(np.mean(y))) / y_std
        Xz = (X[:, usable_idx] - means[usable_idx]) / stds[usable_idx]
        Xz = np.nan_to_num(Xz, copy=False, nan=0.0, posinf=0.0, neginf=0.0)
        scores = np.abs(np.mean(Xz * yz.reshape(-1, 1), axis=0))
    take = max(int(max_candidates), int(min_features))
    order = np.argsort(scores)[::-1][:take]
    return usable_idx[order]


def transform_selected(X: np.ndarray, selection: ElasticNetSelectionResult) -> np.ndarray:
    idx = selection.selected_indexes
    out = (np.asarray(X, dtype=np.float32)[:, idx] - selection.means[idx]) / selection.stds[idx]
    return np.nan_to_num(out, copy=False, nan=0.0, posinf=0.0, neginf=0.0).astype("float32", copy=False)


def append_sequence_features(
    *,
    X_train: np.ndarray,
    X_val: np.ndarray,
    X_pred: np.ndarray,
    X_seq_train: np.ndarray | None,
    X_seq_val: np.ndarray | None,
    X_seq_pred: np.ndarray | None,
    y_binary_train: np.ndarray,
    config: RocketConfig,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    if config.mode == SEQUENCE_NONE:
        return X_train, X_val, X_pred, {"sequence_mode": SEQUENCE_NONE, "sequence_feature_count": 0}
    if X_seq_train is None or X_seq_val is None or X_seq_pred is None:
        raise ValueError(f"Sequence panel is required for sequence mode {config.mode}")
    X_seq_train, X_seq_val, X_seq_pred, scaler_diag = standardize_sequence_panel(X_seq_train, X_seq_val, X_seq_pred)
    if config.mode == SEQUENCE_CAUSAL_ROCKET_V1:
        kernels = make_rocket_kernels(
            input_features=X_seq_train.shape[1],
            n_kernels=int(config.n_kernels),
            sequence_length=int(config.sequence_length),
            seed=int(config.seed),
        )
        train_embed = causal_rocket_transform(X_seq_train, np.arange(X_seq_train.shape[0]), kernels, int(config.sequence_length))
        val_full = np.vstack([X_seq_train, X_seq_val])
        val_anchors = np.arange(X_seq_train.shape[0], X_seq_train.shape[0] + X_seq_val.shape[0])
        val_embed = causal_rocket_transform(val_full, val_anchors, kernels, int(config.sequence_length))
        pred_full = np.vstack([X_seq_train, X_seq_val, X_seq_pred])
        pred_anchors = np.arange(
            X_seq_train.shape[0] + X_seq_val.shape[0],
            X_seq_train.shape[0] + X_seq_val.shape[0] + X_seq_pred.shape[0],
        )
        pred_embed = causal_rocket_transform(pred_full, pred_anchors, kernels, int(config.sequence_length))
        diag = {
            "sequence_mode": config.mode,
            "sequence_input_features": int(X_seq_train.shape[1]),
            "sequence_feature_count": int(train_embed.shape[1]),
            "sequence_length": int(config.sequence_length),
            "rocket_kernels": int(config.n_kernels),
            **scaler_diag,
        }
        return append_columns(X_train, train_embed), append_columns(X_val, val_embed), append_columns(X_pred, pred_embed), diag
    if config.mode == SEQUENCE_CAUSAL_CNN_V1:
        cnn_config = SequenceEmbeddingConfig(
            mode=SEQUENCE_CAUSAL_CNN_V1,
            sequence_length=int(config.sequence_length),
            embedding_dim=int(config.cnn_embedding_dim),
            conv_channels=int(config.cnn_conv_channels),
            kernel_size=int(config.cnn_kernel_size),
            epochs=int(config.cnn_epochs),
            batch_size=int(config.cnn_batch_size),
            max_train_rows=int(config.cnn_max_train_rows),
            device=str(config.cnn_device),
        )
        embedder: CausalCNNEmbedder = fit_causal_cnn_embedder(X_seq_train, y_binary_train, config=cnn_config)
        train_embed = embedder.transform(X_seq_train, np.arange(X_seq_train.shape[0]))
        val_full = np.vstack([X_seq_train, X_seq_val])
        val_embed = embedder.transform(val_full, np.arange(X_seq_train.shape[0], val_full.shape[0]))
        pred_full = np.vstack([X_seq_train, X_seq_val, X_seq_pred])
        pred_embed = embedder.transform(pred_full, np.arange(X_seq_train.shape[0] + X_seq_val.shape[0], pred_full.shape[0]))
        diag = {
            "sequence_mode": config.mode,
            "sequence_input_features": int(X_seq_train.shape[1]),
            "sequence_feature_count": int(train_embed.shape[1]),
            "sequence_length": int(config.sequence_length),
            "cnn_train_rows": int(embedder.train_rows),
            **scaler_diag,
        }
        return append_columns(X_train, train_embed), append_columns(X_val, val_embed), append_columns(X_pred, pred_embed), diag
    raise ValueError(f"Unsupported sequence mode: {config.mode}")


def standardize_sequence_panel(
    X_train: np.ndarray,
    X_val: np.ndarray,
    X_pred: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    mean = np.nanmean(X_train, axis=0).astype("float32")
    std = np.nanstd(X_train, axis=0).astype("float32")
    std = np.where(np.isfinite(std) & (std > 1e-12), std, 1.0).astype("float32")
    mean = np.where(np.isfinite(mean), mean, 0.0).astype("float32")
    return (
        np.nan_to_num((X_train - mean) / std, nan=0.0, posinf=0.0, neginf=0.0).astype("float32", copy=False),
        np.nan_to_num((X_val - mean) / std, nan=0.0, posinf=0.0, neginf=0.0).astype("float32", copy=False),
        np.nan_to_num((X_pred - mean) / std, nan=0.0, posinf=0.0, neginf=0.0).astype("float32", copy=False),
        {"sequence_scaler_fit_rows": int(X_train.shape[0])},
    )


def append_columns(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    return np.hstack([left, right]).astype("float32", copy=False)


def make_rocket_kernels(
    *,
    input_features: int,
    n_kernels: int,
    sequence_length: int,
    seed: int,
) -> tuple[RocketKernel, ...]:
    if int(input_features) <= 0:
        raise ValueError("causal_rocket_v1 requires at least one sequence input feature")
    rng = np.random.default_rng(int(seed))
    lengths = np.asarray([3, 5, 7], dtype=int)
    lengths = lengths[lengths <= int(sequence_length)]
    if lengths.size == 0:
        lengths = np.asarray([max(1, int(sequence_length))], dtype=int)
    kernels: list[RocketKernel] = []
    for _ in range(int(n_kernels)):
        length = int(rng.choice(lengths))
        weights = rng.normal(0.0, 1.0, size=length).astype("float32")
        weights = weights - float(weights.mean())
        kernels.append(
            RocketKernel(
                channel=int(rng.integers(0, int(input_features))),
                length=length,
                weights=tuple(float(value) for value in weights),
                bias=float(rng.uniform(-1.0, 1.0)),
            )
        )
    return tuple(kernels)


def causal_rocket_transform(
    full_matrix: np.ndarray,
    anchor_indexes: np.ndarray,
    kernels: tuple[RocketKernel, ...],
    sequence_length: int,
) -> np.ndarray:
    X = np.asarray(full_matrix, dtype=np.float32)
    anchors = np.asarray(anchor_indexes, dtype=np.int64)
    out = np.empty((len(anchors), len(kernels) * 3), dtype=np.float32)
    by_channel: dict[int, list[tuple[int, RocketKernel]]] = {}
    for idx, kernel in enumerate(kernels):
        by_channel.setdefault(int(kernel.channel), []).append((idx, kernel))
    for channel, channel_kernels in by_channel.items():
        seq = causal_lag_matrix(X[:, channel], anchors, int(sequence_length))
        for idx, kernel in channel_kernels:
            weights = np.asarray(kernel.weights, dtype=np.float32)
            conv_parts = [
                seq[:, start : start + int(kernel.length)] @ weights + float(kernel.bias)
                for start in range(0, int(sequence_length) - int(kernel.length) + 1)
            ]
            conv = np.stack(conv_parts, axis=1)
            out[:, idx * 3] = np.mean(conv > 0.0, axis=1)
            out[:, idx * 3 + 1] = np.max(conv, axis=1)
            out[:, idx * 3 + 2] = np.mean(conv, axis=1)
    return np.nan_to_num(out, copy=False, nan=0.0, posinf=0.0, neginf=0.0)


def causal_lag_matrix(values: np.ndarray, anchor_indexes: np.ndarray, sequence_length: int) -> np.ndarray:
    values = np.asarray(values, dtype=np.float32)
    anchors = np.asarray(anchor_indexes, dtype=np.int64)
    offsets = np.arange(int(sequence_length) - 1, -1, -1, dtype=np.int64)
    positions = anchors.reshape(-1, 1) - offsets.reshape(1, -1)
    valid = positions >= 0
    out = np.zeros((len(anchors), int(sequence_length)), dtype=np.float32)
    out[valid] = values[positions[valid]]
    return out


def fit_catboost_ranker(
    X_train: np.ndarray,
    y_train: np.ndarray,
    group_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    group_val: np.ndarray,
    *,
    config: RankModelConfig,
    task_type: str,
    thread_count: int,
) -> Any:
    try:
        from catboost import CatBoostRanker, Pool
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("CatBoost is required for ranked-signal modeling") from exc
    params = catboost_ranker_params(config=config, task_type=task_type, thread_count=thread_count)
    train_pool = Pool(X_train, label=y_train, group_id=group_train)
    val_pool = Pool(X_val, label=y_val, group_id=group_val)
    model = CatBoostRanker(**params)
    try:
        model.fit(
            train_pool,
            eval_set=val_pool,
            use_best_model=True,
            early_stopping_rounds=int(config.early_stopping_rounds),
            verbose=False,
        )
    except Exception:
        if params["task_type"] != "GPU":
            raise
        params["task_type"] = "CPU"
        params.pop("devices", None)
        model = CatBoostRanker(**params)
        model.fit(
            train_pool,
            eval_set=val_pool,
            use_best_model=True,
            early_stopping_rounds=int(config.early_stopping_rounds),
            verbose=False,
        )
    return model


def catboost_ranker_params(*, config: RankModelConfig, task_type: str, thread_count: int) -> dict[str, Any]:
    if config.rank_loss not in RANK_LOSSES:
        raise ValueError(f"Unsupported CatBoost rank loss: {config.rank_loss}")
    params = {
        "loss_function": config.rank_loss,
        "iterations": int(config.iterations),
        "depth": int(config.depth),
        "learning_rate": float(config.learning_rate),
        "l2_leaf_reg": float(config.l2_leaf_reg),
        "random_strength": float(config.random_strength),
        "random_seed": 42,
        "allow_writing_files": False,
        "verbose": False,
        "thread_count": int(thread_count),
        "task_type": str(task_type).upper(),
        "has_time": True,
        "od_type": "Iter",
        "od_wait": int(config.od_wait),
    }
    if str(task_type).upper() == "GPU":
        params["devices"] = "0"
    return params


def select_rank_decision_rule(
    y_binary: np.ndarray,
    score: np.ndarray,
    group_id: np.ndarray,
    meta: pl.DataFrame,
    config: DecisionConfig,
) -> tuple[float, int, dict[str, Any]]:
    quantile = float(config.threshold_quantile)
    threshold = float(np.quantile(score[np.isfinite(score)], quantile))
    max_signals = int(config.max_signals_per_batch)
    decision = causal_signal_budget_decisions(
        score,
        group_id,
        meta["timestamp"].to_list(),
        threshold=threshold,
        max_signals=max_signals,
    )
    metrics = aggregate_prediction_metrics(
        np.asarray(y_binary, dtype=int),
        decision,
        [
            simple_window_metric_row(
                np.asarray(y_binary, dtype=int),
                decision,
                fp_cost=float(config.fp_cost),
                fn_cost=float(config.fn_cost),
                high_target_positive_rate_threshold=float(config.high_target_positive_rate_threshold),
                high_false_positive_rate_threshold=float(config.high_false_positive_rate_threshold),
            )
        ],
        fp_cost=float(config.fp_cost),
        fn_cost=float(config.fn_cost),
        selected_feature_count_mean=0.0,
    )
    return threshold, max_signals, metrics


def causal_signal_budget_decisions(
    score: np.ndarray,
    group_id: np.ndarray,
    timestamps: list[Any],
    *,
    threshold: float,
    max_signals: int,
) -> np.ndarray:
    score = np.asarray(score, dtype=float)
    group_id = np.asarray(group_id)
    order = sorted(range(len(score)), key=lambda idx: (int(group_id[idx]), timestamps[idx]))
    counts: dict[int, int] = {}
    decisions = np.zeros(len(score), dtype=np.int8)
    cap = max(0, int(max_signals))
    for idx in order:
        group = int(group_id[idx])
        if cap > 0 and counts.get(group, 0) >= cap:
            continue
        if np.isfinite(score[idx]) and float(score[idx]) >= float(threshold):
            decisions[idx] = 1
            counts[group] = counts.get(group, 0) + 1
    return decisions


def fit_apply_batch_state_gate(
    *,
    X_train: np.ndarray,
    y_train: np.ndarray,
    group_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    group_val: np.ndarray,
    X_pred: np.ndarray,
    y_pred: np.ndarray,
    group_pred: np.ndarray,
    config: BatchStateGateConfig,
) -> dict[str, Any]:
    if str(config.mode) == BATCH_STATE_GATE_OFF:
        return batch_state_gate_off(group_val, group_pred)
    if str(config.mode) != BATCH_STATE_GATE_LOGISTIC_PREFIX_V1:
        raise ValueError(f"Unsupported batch-state gate mode: {config.mode}")
    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("scikit-learn is required for batch-state gate logistic_prefix_v1") from exc

    train_X, train_y, train_diag = batch_state_prefix_matrix(
        X_train,
        y_train,
        group_train,
        config=config,
        split="train",
    )
    val_X, val_y, val_diag = batch_state_prefix_matrix(X_val, y_val, group_val, config=config, split="validation")
    pred_X, pred_y, pred_diag = batch_state_prefix_matrix(X_pred, y_pred, group_pred, config=config, split="prediction")
    positives = int(np.sum(train_y == 1))
    negatives = int(np.sum(train_y == 0))
    diagnostics: dict[str, Any] = {
        "batch_state_gate_mode": str(config.mode),
        "batch_state_gate_status": "ok",
        "batch_state_gate_prefix_rows": int(config.prefix_rows),
        "batch_state_gate_min_positive_rate": float(config.min_positive_rate),
        "batch_state_gate_probability_threshold": float(config.probability_threshold),
        "batch_state_gate_train_batches": int(len(train_y)),
        "batch_state_gate_train_positive_batches": positives,
        "batch_state_gate_train_negative_batches": negatives,
    }
    if (
        len(train_y) < int(config.min_train_batches)
        or positives < int(config.min_positive_batches)
        or negatives < int(config.min_negative_batches)
    ):
        diagnostics["batch_state_gate_status"] = "insufficient_train_state_classes"
        return {
            **diagnostics,
            "validation_group_pass": {int(row["batch_id"]): False for row in val_diag},
            "prediction_group_pass": {int(row["batch_id"]): False for row in pred_diag},
            "validation_group_diagnostics": gate_group_diagnostics(val_diag, np.full(len(val_diag), np.nan), np.zeros(len(val_diag), dtype=bool)),
            "prediction_group_diagnostics": gate_group_diagnostics(pred_diag, np.full(len(pred_diag), np.nan), np.zeros(len(pred_diag), dtype=bool)),
            "prediction_diagnostics": batch_gate_prediction_summary(pred_diag, np.full(len(pred_diag), np.nan), np.zeros(len(pred_diag), dtype=bool)),
        }

    scaler = StandardScaler()
    train_scaled = scaler.fit_transform(train_X)
    model = LogisticRegression(
        C=float(config.c),
        max_iter=int(config.max_iter),
        class_weight="balanced",
        random_state=42,
    )
    model.fit(train_scaled, train_y)
    val_prob = model.predict_proba(scaler.transform(val_X))[:, 1] if len(val_X) else np.asarray([], dtype=float)
    pred_prob = model.predict_proba(scaler.transform(pred_X))[:, 1] if len(pred_X) else np.asarray([], dtype=float)
    val_pass = val_prob >= float(config.probability_threshold)
    pred_pass = pred_prob >= float(config.probability_threshold)
    diagnostics.update(
        {
            "batch_state_gate_val_pass_rate": float(np.mean(val_pass)) if len(val_pass) else None,
            "batch_state_gate_pred_pass_rate": float(np.mean(pred_pass)) if len(pred_pass) else None,
        }
    )
    return {
        **diagnostics,
        "validation_group_pass": {int(row["batch_id"]): bool(val_pass[idx]) for idx, row in enumerate(val_diag)},
        "prediction_group_pass": {int(row["batch_id"]): bool(pred_pass[idx]) for idx, row in enumerate(pred_diag)},
        "validation_group_diagnostics": gate_group_diagnostics(val_diag, val_prob, val_pass),
        "prediction_group_diagnostics": gate_group_diagnostics(pred_diag, pred_prob, pred_pass),
        "prediction_diagnostics": {
            **diagnostics,
            **batch_gate_prediction_summary(pred_diag, pred_prob, pred_pass),
        },
    }


def batch_state_gate_off(group_val: np.ndarray, group_pred: np.ndarray) -> dict[str, Any]:
    val_groups = sorted({int(value) for value in np.asarray(group_val)})
    pred_groups = sorted({int(value) for value in np.asarray(group_pred)})
    val_diag = {
        group: {
            "batch_state_gate_mode": BATCH_STATE_GATE_OFF,
            "batch_state_gate_status": "off",
            "batch_state_gate_probability": None,
            "batch_state_gate_passed": True,
            "batch_state_gate_prefix_rows": 0,
        }
        for group in val_groups
    }
    pred_diag = {
        group: {
            "batch_state_gate_mode": BATCH_STATE_GATE_OFF,
            "batch_state_gate_status": "off",
            "batch_state_gate_probability": None,
            "batch_state_gate_passed": True,
            "batch_state_gate_prefix_rows": 0,
        }
        for group in pred_groups
    }
    return {
        "batch_state_gate_mode": BATCH_STATE_GATE_OFF,
        "batch_state_gate_status": "off",
        "validation_group_pass": {group: True for group in val_groups},
        "prediction_group_pass": {group: True for group in pred_groups},
        "validation_group_diagnostics": val_diag,
        "prediction_group_diagnostics": pred_diag,
        "prediction_diagnostics": {
            "batch_state_gate_mode": BATCH_STATE_GATE_OFF,
            "batch_state_gate_status": "off",
            "batch_state_gate_probability": None,
            "batch_state_gate_passed": True,
            "batch_state_gate_prefix_rows": 0,
        },
    }


def batch_state_prefix_matrix(
    X: np.ndarray,
    y_binary: np.ndarray,
    group_id: np.ndarray,
    *,
    config: BatchStateGateConfig,
    split: str,
) -> tuple[np.ndarray, np.ndarray, list[dict[str, Any]]]:
    X = np.asarray(X, dtype=np.float32)
    y = np.asarray(y_binary, dtype=int)
    groups = np.asarray(group_id, dtype=np.int64)
    rows: list[np.ndarray] = []
    labels: list[int] = []
    diagnostics: list[dict[str, Any]] = []
    for group in sorted({int(value) for value in groups}):
        idx = np.flatnonzero(groups == int(group))
        prefix_count = min(max(1, int(config.prefix_rows)), int(idx.size))
        prefix_idx = idx[:prefix_count]
        prefix = X[prefix_idx]
        mean = np.mean(prefix, axis=0)
        std = np.std(prefix, axis=0)
        last = prefix[-1]
        summary = np.concatenate([mean, std, last]).astype("float32", copy=False)
        positive_rate = float(np.mean(y[idx])) if idx.size else 0.0
        rows.append(np.nan_to_num(summary, copy=False, nan=0.0, posinf=0.0, neginf=0.0))
        labels.append(int(positive_rate >= float(config.min_positive_rate)))
        diagnostics.append(
            {
                "split": split,
                "batch_id": int(group),
                "rows": int(idx.size),
                "prefix_rows_used": int(prefix_count),
                "positive_rate": positive_rate,
                "batch_state_target": int(positive_rate >= float(config.min_positive_rate)),
            }
        )
    if rows:
        return np.vstack(rows).astype("float32", copy=False), np.asarray(labels, dtype=int), diagnostics
    return np.empty((0, X.shape[1] * 3), dtype="float32"), np.asarray([], dtype=int), diagnostics


def gate_group_diagnostics(diag_rows: list[dict[str, Any]], probability: np.ndarray, passed: np.ndarray) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for idx, row in enumerate(diag_rows):
        prob = float(probability[idx]) if idx < len(probability) and np.isfinite(float(probability[idx])) else None
        is_passed = bool(passed[idx]) if idx < len(passed) else False
        out[int(row["batch_id"])] = {
            "batch_state_gate_mode": BATCH_STATE_GATE_LOGISTIC_PREFIX_V1,
            "batch_state_gate_status": "ok",
            "batch_state_gate_probability": prob,
            "batch_state_gate_passed": is_passed,
            "batch_state_gate_prefix_rows": int(row.get("prefix_rows_used") or 0),
            "batch_state_gate_target": int(row.get("batch_state_target") or 0),
            "batch_state_gate_positive_rate": row.get("positive_rate"),
        }
    return out


def batch_gate_prediction_summary(diag_rows: list[dict[str, Any]], probability: np.ndarray, passed: np.ndarray) -> dict[str, Any]:
    if not diag_rows:
        return {
            "batch_state_gate_probability": None,
            "batch_state_gate_passed": False,
            "batch_state_gate_target": None,
            "batch_state_gate_positive_rate": None,
        }
    prob = float(probability[0]) if len(probability) and np.isfinite(float(probability[0])) else None
    return {
        "batch_state_gate_probability": prob,
        "batch_state_gate_passed": bool(passed[0]) if len(passed) else False,
        "batch_state_gate_target": int(diag_rows[0].get("batch_state_target") or 0),
        "batch_state_gate_positive_rate": diag_rows[0].get("positive_rate"),
    }


def apply_batch_state_gate_to_decisions(
    decision: np.ndarray,
    group_id: np.ndarray,
    group_pass: dict[int, bool],
    *,
    prefix_rows: int,
    mode: str,
) -> np.ndarray:
    if str(mode) == BATCH_STATE_GATE_OFF:
        return np.asarray(decision, dtype=np.int8)
    out = np.asarray(decision, dtype=np.int8).copy()
    groups = np.asarray(group_id, dtype=np.int64)
    for group in sorted({int(value) for value in groups}):
        idx = np.flatnonzero(groups == int(group))
        if not bool(group_pass.get(int(group), False)):
            out[idx] = 0
            continue
        warmup = min(max(0, int(prefix_rows)), int(idx.size))
        if warmup > 0:
            out[idx[:warmup]] = 0
    return out


def add_batch_gate_to_group_metrics(rows: list[dict[str, Any]], group_diag: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        group = int(row.get("metric_batch_id", row.get("batch_id", -1)))
        out.append({**row, **group_diag.get(group, {})})
    return out


def add_score_gate_fields(
    rows: list[dict[str, Any]],
    raw_decision: np.ndarray,
    group_diag: dict[int, dict[str, Any]],
    config: BatchStateGateConfig,
) -> None:
    groups_seen: dict[int, int] = {}
    for idx, row in enumerate(rows):
        group = int(row["batch_id"])
        pos = groups_seen.get(group, 0)
        groups_seen[group] = pos + 1
        diag = group_diag.get(group, {})
        row["raw_decision_before_batch_state_gate"] = int(raw_decision[idx]) if idx < len(raw_decision) else int(row.get("decision", 0))
        row["batch_state_gate_mode"] = str(config.mode)
        row["batch_state_gate_probability"] = diag.get("batch_state_gate_probability")
        row["batch_state_gate_passed"] = diag.get("batch_state_gate_passed", True)
        row["batch_state_gate_prefix_rows"] = int(config.prefix_rows) if str(config.mode) != BATCH_STATE_GATE_OFF else 0
        row["batch_state_gate_prefix_warmup"] = bool(str(config.mode) != BATCH_STATE_GATE_OFF and pos < int(config.prefix_rows))
        row["decision_policy"] = (
            "causal_signal_budget_plus_batch_state_gate"
            if str(config.mode) != BATCH_STATE_GATE_OFF
            else "causal_signal_budget"
        )


def gate_payload_without_arrays(payload: dict[str, Any]) -> dict[str, Any]:
    excluded = {"validation_group_pass", "prediction_group_pass", "validation_group_diagnostics", "prediction_group_diagnostics"}
    return {key: value for key, value in payload.items() if key not in excluded}


def group_metric_rows(
    *,
    split: str,
    step_idx: int,
    pred_batch_id: int,
    meta: pl.DataFrame,
    y_binary: np.ndarray,
    score: np.ndarray,
    decision: np.ndarray,
    config: DecisionConfig,
    selected_feature_count: int,
    threshold: float,
    max_signals: int,
    elapsed_s: float | None,
    validation_threshold_score: float | None,
) -> list[dict[str, Any]]:
    groups = meta["batch_id"].to_numpy().astype("int64", copy=False)
    rows: list[dict[str, Any]] = []
    for group in sorted({int(value) for value in groups}):
        mask = groups == int(group)
        row = simple_window_metric_row(
            np.asarray(y_binary, dtype=int)[mask],
            np.asarray(decision, dtype=int)[mask],
            fp_cost=float(config.fp_cost),
            fn_cost=float(config.fn_cost),
            high_target_positive_rate_threshold=float(config.high_target_positive_rate_threshold),
            high_false_positive_rate_threshold=float(config.high_false_positive_rate_threshold),
        )
        group_score = np.asarray(score, dtype=float)[mask]
        row.update(
            {
                "split": split,
                "step_idx": int(step_idx),
                "pred_batch_id": int(pred_batch_id),
                "metric_batch_id": int(group),
                "selected_feature_count": int(selected_feature_count),
                "threshold": float(threshold),
                "threshold_quantile": float(config.threshold_quantile),
                "max_signals_per_batch": int(max_signals),
                "score_mean": float(np.mean(group_score)) if len(group_score) else None,
                "score_std": float(np.std(group_score)) if len(group_score) else None,
                **offline_topk_diagnostic_metrics(np.asarray(y_binary, dtype=int)[mask], group_score, int(max_signals)),
                "elapsed_s": elapsed_s,
                "validation_threshold_score": validation_threshold_score,
            }
        )
        rows.append(row)
    return rows


def window_metric_row(
    *,
    split: str,
    window: RPFWindow,
    y_binary: np.ndarray,
    score: np.ndarray,
    decision: np.ndarray,
    config: DecisionConfig,
    selected_feature_count: int,
    threshold: float,
    max_signals: int,
    elapsed_s: float,
    validation_threshold_score: float | None,
) -> dict[str, Any]:
    row = simple_window_metric_row(
        y_binary,
        decision,
        fp_cost=float(config.fp_cost),
        fn_cost=float(config.fn_cost),
        high_target_positive_rate_threshold=float(config.high_target_positive_rate_threshold),
        high_false_positive_rate_threshold=float(config.high_false_positive_rate_threshold),
    )
    row.update(
        {
            "split": split,
            "step_idx": int(window.step_idx),
            "pred_batch_id": int(window.pred_batch_id),
            "selected_feature_count": int(selected_feature_count),
            "threshold": float(threshold),
            "threshold_quantile": float(config.threshold_quantile),
            "max_signals_per_batch": int(max_signals),
            "score_mean": float(np.mean(score)) if len(score) else None,
            "score_std": float(np.std(score)) if len(score) else None,
            **offline_topk_diagnostic_metrics(y_binary, score, int(max_signals)),
            "elapsed_s": float(elapsed_s),
            "validation_threshold_score": validation_threshold_score,
        }
    )
    return row


def simple_window_metric_row(
    y_binary: np.ndarray,
    decision: np.ndarray,
    *,
    fp_cost: float,
    fn_cost: float,
    high_target_positive_rate_threshold: float,
    high_false_positive_rate_threshold: float,
) -> dict[str, Any]:
    metrics = binary_decision_metrics(y_binary, decision, fp_cost=fp_cost, fn_cost=fn_cost)
    positive_rate = float(np.mean(y_binary)) if len(y_binary) else 0.0
    return {
        **metrics,
        "positive_rate": positive_rate,
        "high_target_window": bool(positive_rate >= float(high_target_positive_rate_threshold)),
        "active_window": bool(metrics["predicted_positive_count"] > 0),
        "captured_high_target_window": bool(
            positive_rate >= float(high_target_positive_rate_threshold) and metrics["true_positive_count"] > 0
        ),
        "missed_high_target_window": bool(
            positive_rate >= float(high_target_positive_rate_threshold) and metrics["true_positive_count"] == 0
        ),
        "high_false_positive_window": bool(finite(metrics["false_positive_rate"], 0.0) >= float(high_false_positive_rate_threshold)),
    }


def binary_decision_metrics(y_binary: np.ndarray, decision: np.ndarray, *, fp_cost: float, fn_cost: float) -> dict[str, Any]:
    y = np.asarray(y_binary, dtype=int)
    pred = np.asarray(decision, dtype=int)
    tp = int(np.sum((y == 1) & (pred == 1)))
    fp = int(np.sum((y == 0) & (pred == 1)))
    fn = int(np.sum((y == 1) & (pred == 0)))
    tn = int(np.sum((y == 0) & (pred == 0)))
    rows = int(len(y))
    predicted_positive = tp + fp
    positives = tp + fn
    negatives = fp + tn
    precision = safe_div(tp, predicted_positive)
    recall = safe_div(tp, positives)
    fpr = safe_div(fp, negatives)
    base = safe_div(positives, rows)
    return {
        "rows": rows,
        "positive_count": positives,
        "negative_count": negatives,
        "predicted_positive_count": predicted_positive,
        "true_positive_count": tp,
        "false_positive_count": fp,
        "false_negative_count": fn,
        "true_negative_count": tn,
        "precision": precision,
        "recall": recall,
        "false_positive_rate": fpr,
        "false_discovery_rate": safe_div(fp, predicted_positive),
        "predicted_positive_rate": safe_div(predicted_positive, rows),
        "base_positive_rate": base,
        "precision_lift": safe_div(precision, base) if precision is not None and base > 0 else None,
        "decision_cost": float(fp_cost) * fp + float(fn_cost) * fn,
        "decision_cost_per_row": safe_div(float(fp_cost) * fp + float(fn_cost) * fn, rows),
        "decision_cost_per_signal": safe_div(float(fp_cost) * fp + float(fn_cost) * fn, predicted_positive),
    }


def offline_topk_diagnostic_metrics(y_binary: np.ndarray, score: np.ndarray, k: int) -> dict[str, Any]:
    """Future-aware top-k diagnostic for ranking quality.

    This intentionally sorts the whole scored batch, so it is never a live
    decision rule.  It is stored only to tell whether score ordering contains
    any useful signal before the causal budget is applied.
    """

    y = np.asarray(y_binary, dtype=int)
    scores = np.asarray(score, dtype=float)
    valid = np.flatnonzero(np.isfinite(scores))
    k = min(max(0, int(k)), int(valid.size))
    if k <= 0:
        return {
            "offline_topk_diagnostic_only": True,
            "offline_topk_k": 0,
            "offline_topk_precision": None,
            "offline_topk_recall": None,
        }
    ranked = valid[np.argsort(-scores[valid], kind="mergesort")[:k]]
    tp = int(np.sum(y[ranked] == 1))
    positives = int(np.sum(y == 1))
    return {
        "offline_topk_diagnostic_only": True,
        "offline_topk_k": int(k),
        "offline_topk_precision": safe_div(tp, k),
        "offline_topk_recall": safe_div(tp, positives),
    }


def aggregate_prediction_metrics(
    y_binary: np.ndarray,
    decision: np.ndarray,
    window_metrics: list[dict[str, Any]],
    *,
    fp_cost: float,
    fn_cost: float,
    selected_feature_count_mean: float,
) -> dict[str, Any]:
    metrics = binary_decision_metrics(y_binary, decision, fp_cost=fp_cost, fn_cost=fn_cost)
    total_windows = max(1, len(window_metrics))
    active = sum(1 for row in window_metrics if bool(row.get("active_window")))
    high_target = [row for row in window_metrics if bool(row.get("high_target_window"))]
    missed_high = sum(1 for row in high_target if bool(row.get("missed_high_target_window")))
    captured_high = sum(1 for row in high_target if bool(row.get("captured_high_target_window")))
    high_fp = sum(1 for row in window_metrics if bool(row.get("high_false_positive_window")))
    metrics.update(
        {
            "active_window_rate": active / total_windows,
            "zero_signal_window_rate": 1.0 - active / total_windows,
            "high_target_window_count": len(high_target),
            "high_target_window_capture_rate": safe_div(captured_high, len(high_target)) if high_target else 0.0,
            "missed_high_target_window_rate": safe_div(missed_high, len(high_target)) if high_target else 0.0,
            "high_false_positive_window_rate": high_fp / total_windows,
            "selected_feature_count_mean": float(selected_feature_count_mean),
        }
    )
    metrics["ranked_signal_quality"] = ranked_signal_quality(metrics)
    return metrics


def ranked_signal_quality(metrics: dict[str, Any]) -> float:
    precision = finite(metrics.get("precision"), 0.0)
    precision_lift = finite(metrics.get("precision_lift"), 0.0)
    active_window_rate = finite(metrics.get("active_window_rate"), 0.0)
    high_capture = finite(metrics.get("high_target_window_capture_rate"), 0.0)
    fdr = finite(metrics.get("false_discovery_rate"), 1.0)
    zero_signal = finite(metrics.get("zero_signal_window_rate"), 1.0)
    missed_high = finite(metrics.get("missed_high_target_window_rate"), 1.0)
    high_fp = finite(metrics.get("high_false_positive_window_rate"), 1.0)
    selected_count = finite(metrics.get("selected_feature_count_mean"), 160.0)
    return float(
        2.0 * max(0.0, precision_lift - 1.0)
        + 1.0 * precision
        + 0.6 * active_window_rate
        + 0.6 * high_capture
        - 1.5 * fdr
        - 1.0 * zero_signal
        - 1.0 * missed_high
        - 0.5 * high_fp
        - 0.25 * selected_count / 160.0
    )


def score_rows(
    *,
    split: str,
    side: str,
    target_col: str,
    window: RPFWindow,
    meta: pl.DataFrame,
    y_relevance: np.ndarray,
    y_binary: np.ndarray,
    score: np.ndarray,
    decision: np.ndarray,
    threshold: float,
    max_signals: int,
) -> list[dict[str, Any]]:
    timestamps = meta["timestamp"].to_list()
    batch_ids = meta["batch_id"].to_list()
    rows: list[dict[str, Any]] = []
    for idx, value in enumerate(score):
        rows.append(
            {
                "split": split,
                "side": side,
                "target_col": target_col,
                "step_idx": int(window.step_idx),
                "pred_batch_id": int(window.pred_batch_id),
                "timestamp": timestamps[idx],
                "batch_id": int(batch_ids[idx]),
                "target_relevance": float(y_relevance[idx]),
                "target_binary": int(y_binary[idx]),
                "rank_score": float(value),
                "decision": int(decision[idx]),
                "threshold": float(threshold),
                "max_signals_per_batch": int(max_signals),
                "decision_policy": "causal_signal_budget",
                "offline_topk_diagnostic_only": False,
            }
        )
    return rows


def selected_feature_detail_rows(
    selection: ElasticNetSelectionResult,
    *,
    step_idx: int,
    pred_batch_id: int,
    side: str,
) -> list[dict[str, Any]]:
    rows = []
    for row in selection.detail.filter(pl.col("final_status") == "selected").to_dicts():
        rows.append(
            {
                "step_idx": int(step_idx),
                "pred_batch_id": int(pred_batch_id),
                "side": side,
                "feature_selector": FEATURE_SELECTOR_ELASTICNET_RELEVANCE_V1,
                **row,
            }
        )
    return rows


def write_partial_outputs(
    run_root: Path,
    trials: list[dict[str, Any]],
    window_rows: list[dict[str, Any]],
    score_rows_: list[dict[str, Any]],
    decision_rows: list[dict[str, Any]],
    selected_feature_rows: list[dict[str, Any]],
    sequence_rows: list[dict[str, Any]],
) -> None:
    write_trials(run_root / "trials.parquet", trials)
    write_rows_parquet(run_root / "window_metrics.parquet", window_rows)
    write_rows_parquet(run_root / "prediction_scores.parquet", score_rows_)
    write_rows_parquet(run_root / "rank_decisions.parquet", decision_rows)
    write_rows_parquet(run_root / "selected_features.parquet", selected_feature_rows)
    write_rows_parquet(run_root / "sequence_diagnostics.parquet", sequence_rows)


def write_rows_parquet(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        pl.DataFrame(rows, infer_schema_length=None).write_parquet(path)
    else:
        pl.DataFrame({"empty": []}).write_parquet(path)


def split_tuning_holdout_windows(windows: list[RPFWindow], holdout_steps: int) -> tuple[list[RPFWindow], list[RPFWindow]]:
    holdout = max(0, int(holdout_steps))
    if holdout <= 0:
        return list(windows), []
    if holdout >= len(windows):
        raise ValueError("--holdout-steps must be smaller than selected --n-steps")
    return list(windows[:-holdout]), list(windows[-holdout:])


def windows_for_trial(
    *,
    base_windows: list[RPFWindow],
    batch_index: pl.DataFrame | None,
    trial_config: RankTrialConfig,
    n_steps: int,
    window_end_offset_steps: int = 0,
) -> list[RPFWindow]:
    if batch_index is None:
        windows = list(base_windows)
        if windows:
            first = windows[-1]
            if len(first.train_batch_ids) != int(trial_config.train_batches) or len(first.val_batch_ids) != int(trial_config.val_batches):
                raise ValueError("Changing train/val batches requires batch_index.parquet in --base-run")
    else:
        windows = build_windows(
            batch_index,
            lookback_batches=int(trial_config.train_batches),
            val_batches=int(trial_config.val_batches),
            embargo_batches=0,
            n_steps=0,
        )
    return select_window_block(windows, n_steps=int(n_steps), window_end_offset_steps=int(window_end_offset_steps))


def select_window_block(
    windows: list[RPFWindow],
    *,
    n_steps: int,
    window_end_offset_steps: int = 0,
) -> list[RPFWindow]:
    if int(window_end_offset_steps) < 0:
        raise ValueError("--window-end-offset-steps must be non-negative")
    end = len(windows) - int(window_end_offset_steps)
    if end <= 0:
        return []
    start = 0 if int(n_steps) <= 0 else max(0, end - int(n_steps))
    return list(windows[start:end])


def holdout_windows_for_best(
    *,
    base_windows: list[RPFWindow],
    batch_index: pl.DataFrame | None,
    best_config: dict[str, Any],
    n_steps: int,
    holdout_steps: int,
    window_end_offset_steps: int = 0,
) -> list[RPFWindow]:
    windows = windows_for_trial(
        base_windows=base_windows,
        batch_index=batch_index,
        trial_config=trial_config_from_payload(best_config),
        n_steps=n_steps,
        window_end_offset_steps=window_end_offset_steps,
    )
    _, holdout = split_tuning_holdout_windows(windows, holdout_steps)
    return holdout


def build_search_space(args: argparse.Namespace) -> dict[str, list[Any]]:
    space: dict[str, list[Any]] = {
        "train_batches": parse_ints(args.train_batches_choices),
        "val_batches": parse_ints(args.val_batches_choices),
        "rank_loss": parse_strings(args.rank_loss_choices or args.rank_loss),
        "iterations": parse_ints(args.iterations_choices),
        "depth": parse_ints(args.depth_choices),
        "learning_rate": parse_floats(args.learning_rate_choices),
        "l2_leaf_reg": parse_floats(args.l2_leaf_reg_choices),
        "random_strength": parse_floats(args.random_strength_choices),
        "elasticnet_alpha": parse_floats(args.elasticnet_alpha_choices),
        "elasticnet_l1_ratio": parse_floats(args.elasticnet_l1_ratio_choices),
        "elasticnet_max_features": parse_ints(args.elasticnet_max_features_choices),
        "elasticnet_prefilter_features": parse_ints(args.elasticnet_prefilter_features_choices),
        "elasticnet_coef_eps": parse_floats(args.elasticnet_coef_eps_choices),
        "threshold_quantile": parse_floats(args.threshold_quantile_grid),
        "max_signals_per_batch": parse_ints(args.max_signals_grid),
    }
    if args.sequence_mode == SEQUENCE_CAUSAL_ROCKET_V1:
        space["sequence_length"] = parse_ints(args.sequence_length_choices)
        space["rocket_kernels"] = parse_ints(args.rocket_kernels_choices)
    if args.sequence_mode == SEQUENCE_CAUSAL_CNN_V1:
        space["sequence_length"] = parse_ints(args.sequence_length_choices)
        space["cnn_embedding_dim"] = parse_ints(args.cnn_embedding_dim_choices)
    return {key: unique_values(values) for key, values in space.items()}


def trial_config_from_trial(trial: Any, args: argparse.Namespace) -> RankTrialConfig:
    params = {
        key: trial.suggest_categorical(key, values)
        for key, values in build_search_space(args).items()
    }
    return RankTrialConfig(
        train_batches=int(params["train_batches"]),
        val_batches=int(params["val_batches"]),
        elasticnet=ElasticNetRelevanceConfig(
            alpha=float(params["elasticnet_alpha"]),
            l1_ratio=float(params["elasticnet_l1_ratio"]),
            max_features=int(params["elasticnet_max_features"]),
            min_features=int(args.elasticnet_min_features),
            coef_eps=float(params["elasticnet_coef_eps"]),
            prefilter_features=int(params["elasticnet_prefilter_features"]),
        ),
        sequence=RocketConfig(
            mode=str(args.sequence_mode),
            sequence_length=int(params.get("sequence_length", args.sequence_length)),
            n_kernels=int(params.get("rocket_kernels", args.rocket_kernels)),
            cnn_embedding_dim=int(params.get("cnn_embedding_dim", args.cnn_embedding_dim)),
            cnn_conv_channels=int(args.cnn_conv_channels),
            cnn_kernel_size=int(args.cnn_kernel_size),
            cnn_epochs=int(args.cnn_epochs),
            cnn_batch_size=int(args.cnn_batch_size),
            cnn_max_train_rows=int(args.cnn_max_train_rows),
            cnn_device=str(args.cnn_device),
        ),
        model=RankModelConfig(
            rank_loss=str(params["rank_loss"]),
            iterations=int(params["iterations"]),
            depth=int(params["depth"]),
            learning_rate=float(params["learning_rate"]),
            l2_leaf_reg=float(params["l2_leaf_reg"]),
            random_strength=float(params["random_strength"]),
            early_stopping_rounds=int(args.early_stopping_rounds),
            od_wait=int(args.od_wait),
        ),
        decision=DecisionConfig(
            threshold_quantile=float(params["threshold_quantile"]),
            max_signals_per_batch=int(params["max_signals_per_batch"]),
            fp_cost=float(args.fp_cost),
            fn_cost=float(args.fn_cost),
            high_target_positive_rate_threshold=float(args.high_target_positive_rate_threshold),
            high_false_positive_rate_threshold=float(args.high_false_positive_rate_threshold),
        ),
        batch_state_gate=BatchStateGateConfig(
            mode=str(args.batch_state_gate_mode),
            prefix_rows=int(args.batch_state_gate_prefix_rows),
            min_positive_rate=float(args.batch_state_gate_min_positive_rate),
            probability_threshold=float(args.batch_state_gate_probability_threshold),
            c=float(args.batch_state_gate_c),
            max_iter=int(args.batch_state_gate_max_iter),
            min_train_batches=int(args.batch_state_gate_min_train_batches),
            min_positive_batches=int(args.batch_state_gate_min_positive_batches),
            min_negative_batches=int(args.batch_state_gate_min_negative_batches),
        ),
    )


def trial_config_from_payload(payload: dict[str, Any]) -> RankTrialConfig:
    return RankTrialConfig(
        train_batches=int(payload["train_batches"]),
        val_batches=int(payload["val_batches"]),
        elasticnet=ElasticNetRelevanceConfig(**payload["elasticnet"]),
        sequence=RocketConfig(**payload["sequence"]),
        model=RankModelConfig(**payload["model"]),
        decision=DecisionConfig(**payload["decision"]),
        batch_state_gate=BatchStateGateConfig(**payload.get("batch_state_gate", {})),
    )


def trial_summary_row(
    trial_number: int,
    status: str,
    config: RankTrialConfig,
    payload: dict[str, Any],
) -> dict[str, Any]:
    metrics = payload.get("prediction_metrics", {})
    config_payload = trial_config_payload(config)
    return {
        "trial_number": int(trial_number),
        "status": status,
        "objective_value": float(payload.get("objective_value", -1e9)),
        "train_batches": int(config.train_batches),
        "val_batches": int(config.val_batches),
        "sequence_mode": config.sequence.mode,
        "rank_loss": config.model.rank_loss,
        "selected_feature_count_mean": metrics.get("selected_feature_count_mean"),
        "prediction_precision": metrics.get("precision"),
        "prediction_precision_lift": metrics.get("precision_lift"),
        "prediction_recall": metrics.get("recall"),
        "prediction_false_positive_rate": metrics.get("false_positive_rate"),
        "prediction_false_discovery_rate": metrics.get("false_discovery_rate"),
        "prediction_active_window_rate": metrics.get("active_window_rate"),
        "prediction_zero_signal_window_rate": metrics.get("zero_signal_window_rate"),
        "prediction_high_target_window_capture_rate": metrics.get("high_target_window_capture_rate"),
        "prediction_missed_high_target_window_rate": metrics.get("missed_high_target_window_rate"),
        "prediction_decision_cost_per_row": metrics.get("decision_cost_per_row"),
        "trial_config_json": json.dumps(config_payload, sort_keys=True),
        "error_type": payload.get("error_type"),
        "error_message": payload.get("error_message"),
        "error_traceback": payload.get("error_traceback"),
    }


def trial_config_payload(config: RankTrialConfig) -> dict[str, Any]:
    return {
        "train_batches": int(config.train_batches),
        "val_batches": int(config.val_batches),
        "elasticnet": asdict(config.elasticnet),
        "sequence": asdict(config.sequence),
        "model": asdict(config.model),
        "decision": asdict(config.decision),
        "batch_state_gate": asdict(config.batch_state_gate),
    }


def failed_payload(exc: Exception) -> dict[str, Any]:
    return {
        "objective_value": -1e9,
        "error_type": type(exc).__name__,
        "error_message": str(exc),
        "error_traceback": traceback.format_exc(),
        "prediction_precision": None,
        "prediction_precision_lift": None,
        "prediction_active_window_rate": None,
        "prediction_missed_high_target_window_rate": None,
        "prediction_metrics": {},
        "window_metrics": [],
        "prediction_scores": [],
        "selected_features": [],
        "sequence_diagnostics": [],
    }


def summarize_holdout(payload: dict[str, Any]) -> dict[str, Any]:
    metrics = payload.get("prediction_metrics", {}) if isinstance(payload, dict) else {}
    return {
        "status": payload.get("status", "ok") if isinstance(payload, dict) else "ok",
        "objective_value": payload.get("objective_value") if isinstance(payload, dict) else None,
        "prediction_metrics": metrics,
    }


def write_rank_report(run_root: Path, *, asset: str, root: str, side: str, best: dict[str, Any], holdout: dict[str, Any]) -> None:
    write_markdown(
        run_root / "report.md",
        title="RPF Ranked Signal Report",
        sections={
            "Scope": {"asset": asset, "root": root, "side": side},
            "Best Trial": best or {"status": "none"},
            "Holdout": summarize_holdout(holdout),
            "Decision Contract": [
                "CatBoostRanker learns continuous up/down relevance grouped by batch_id.",
                "Prediction decisions use a validation-calibrated threshold and causal timestamp-order signal budget.",
                "Full prediction-batch top-k sorting is not used for live decisions.",
            ],
        },
    )


def ensure_two_relevance_levels(y: np.ndarray) -> None:
    if len(np.unique(np.round(np.asarray(y, dtype=float), decimals=8))) < 2:
        raise ValueError("Ranker training requires nonconstant relevance labels")


def safe_div(num: float, den: float) -> float | None:
    if num is None or den is None:
        return None
    return None if float(den) == 0.0 else float(num) / float(den)


def finite(value: Any, default: float) -> float:
    if value is None:
        return float(default)
    try:
        out = float(value)
    except Exception:
        return float(default)
    return out if np.isfinite(out) else float(default)


def fmt(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.6g}"
    except Exception:
        return str(value)


def parse_ints(raw: str) -> list[int]:
    return [int(part.strip()) for part in str(raw).split(",") if part.strip()]


def parse_floats(raw: str) -> list[float]:
    return [float(part.strip()) for part in str(raw).split(",") if part.strip()]


def parse_strings(raw: str) -> list[str]:
    return [part.strip() for part in str(raw).split(",") if part.strip()]


def unique_values(values: list[Any]) -> list[Any]:
    out: list[Any] = []
    for value in values:
        if value not in out:
            out.append(value)
    return out


def run_root_for_args(args: argparse.Namespace, *, asset: str, root: str, side: str) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    root_id = str(root).lower().replace("/", "_")
    return OUTPUT_ROOT / f"{timestamp}_rank_signal_{asset.lower()}_{root_id}_{side}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset", default=None)
    parser.add_argument("--root", default=None)
    parser.add_argument("--side", choices=SIDES, required=True)
    parser.add_argument("--base-run", required=True)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--feature-ablation", default="all")
    parser.add_argument("--tabular-panel-path", default=None)
    parser.add_argument("--sequence-panel-path", default=None)
    parser.add_argument("--feature-selector", choices=FEATURE_SELECTORS, default=FEATURE_SELECTOR_ELASTICNET_RELEVANCE_V1)
    parser.add_argument("--sequence-mode", choices=SEQUENCE_MODES, default=SEQUENCE_NONE)
    parser.add_argument("--rank-loss", choices=RANK_LOSSES, default="YetiRank")
    parser.add_argument("--rank-loss-choices", default=None)
    parser.add_argument("--n-steps", type=int, default=30)
    parser.add_argument("--holdout-steps", type=int, default=10)
    parser.add_argument("--window-end-offset-steps", type=int, default=0)
    parser.add_argument("--n-trials", type=int, default=8)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--train-batches-choices", default="120")
    parser.add_argument("--val-batches-choices", default="10")
    parser.add_argument("--max-signals-grid", default="5,10,20")
    parser.add_argument("--threshold-quantile-grid", default="0.90,0.95,0.975,0.99")
    parser.add_argument("--fp-cost", type=float, default=5.0)
    parser.add_argument("--fn-cost", type=float, default=1.0)
    parser.add_argument("--high-target-positive-rate-threshold", type=float, default=0.20)
    parser.add_argument("--high-false-positive-rate-threshold", type=float, default=0.30)
    parser.add_argument("--batch-state-gate-mode", choices=BATCH_STATE_GATE_MODES, default=BATCH_STATE_GATE_OFF)
    parser.add_argument("--batch-state-gate-prefix-rows", type=int, default=60)
    parser.add_argument("--batch-state-gate-min-positive-rate", type=float, default=0.20)
    parser.add_argument("--batch-state-gate-probability-threshold", type=float, default=0.55)
    parser.add_argument("--batch-state-gate-c", type=float, default=0.5)
    parser.add_argument("--batch-state-gate-max-iter", type=int, default=1000)
    parser.add_argument("--batch-state-gate-min-train-batches", type=int, default=20)
    parser.add_argument("--batch-state-gate-min-positive-batches", type=int, default=3)
    parser.add_argument("--batch-state-gate-min-negative-batches", type=int, default=3)
    parser.add_argument("--iterations-choices", default="200,400")
    parser.add_argument("--depth-choices", default="2,3")
    parser.add_argument("--learning-rate-choices", default="0.005,0.01")
    parser.add_argument("--l2-leaf-reg-choices", default="30,100")
    parser.add_argument("--random-strength-choices", default="1,5")
    parser.add_argument("--early-stopping-rounds", type=int, default=100)
    parser.add_argument("--od-wait", type=int, default=100)
    parser.add_argument("--elasticnet-alpha-choices", default="0.001,0.003,0.01,0.03")
    parser.add_argument("--elasticnet-l1-ratio-choices", default="0.25,0.5,0.75")
    parser.add_argument("--elasticnet-prefilter-features-choices", default="160,320")
    parser.add_argument("--elasticnet-max-features-choices", default="40,80,160")
    parser.add_argument("--elasticnet-min-features", type=int, default=10)
    parser.add_argument("--elasticnet-coef-eps-choices", default="1e-8,1e-6")
    parser.add_argument("--sequence-length", type=int, default=16)
    parser.add_argument("--sequence-length-choices", default="8,16,32")
    parser.add_argument("--rocket-kernels", type=int, default=128)
    parser.add_argument("--rocket-kernels-choices", default="128,256")
    parser.add_argument("--cnn-embedding-dim", type=int, default=8)
    parser.add_argument("--cnn-embedding-dim-choices", default="8")
    parser.add_argument("--cnn-conv-channels", type=int, default=16)
    parser.add_argument("--cnn-kernel-size", type=int, default=3)
    parser.add_argument("--cnn-epochs", type=int, default=1)
    parser.add_argument("--cnn-batch-size", type=int, default=512)
    parser.add_argument("--cnn-max-train-rows", type=int, default=8000)
    parser.add_argument("--cnn-device", default="cpu")
    parser.add_argument("--task-type", choices=["CPU", "GPU"], default="CPU")
    parser.add_argument("--thread-count", type=int, default=8)
    parser.add_argument("--log-every-windows", type=int, default=1)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
