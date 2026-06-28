"""CLI for the active RPF binary classification walk-forward."""

from __future__ import annotations

import argparse
import itertools
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl

from regression_feature_engineering.walkforward.ablation import select_ablation_features
from regression_feature_engineering.walkforward.classification.metrics import (
    DECISION_POLICIES,
    DECISION_POLICY_THRESHOLD_ONLY,
    flatten_metrics,
    fmt_metric,
    none_to_bad,
    parse_floats,
    parse_ints,
    threshold_values,
    validate_decision_policy_signal_grid,
)
from regression_feature_engineering.walkforward.classification.model import (
    MODEL_CATBOOST,
    MODEL_FAMILIES,
)
from regression_feature_engineering.walkforward.classification.runner import (
    SELECTOR_REFIT_MODES,
    SELECTOR_REFIT_VALIDATION_MASK,
    run_classification_windows,
)
from regression_feature_engineering.walkforward.classification.sequence import (
    SEQUENCE_EMBEDDING_MODES,
    SEQUENCE_NONE,
    SequenceEmbeddingConfig,
)
from regression_feature_engineering.walkforward.classification.targets import (
    TARGET_BINARY_UP_2X_DOWN,
    UP_EXTREME,
    positive_rule_description,
    side_from_target,
)
from regression_feature_engineering.walkforward.config import load_clean_config
from regression_feature_engineering.walkforward.data import resolve_context
from regression_feature_engineering.walkforward.ema_regime import (
    CHRONOLOGICAL_RECENT,
    EMA_REGIME_BANK,
    WINDOW_MODES,
    EMARegimeWindowConfig,
    build_ema_regime_inventory,
    build_ema_regime_windows,
    filter_ema_prediction_windows,
    make_ema_regime_filter,
)
from regression_feature_engineering.walkforward.policy import (
    ALL_MANIFEST_FEATURES,
    ELASTICNET_LOGISTIC_V1,
    FROZEN_PANEL,
    FeaturePolicyConfig,
    load_panel_features,
)
from regression_feature_engineering.walkforward.reports import write_json, write_markdown, write_trials
from regression_feature_engineering.walkforward.windows import read_windows
from scripts.project_paths import ensure_project_root_on_path


PROJECT_ROOT = ensure_project_root_on_path(Path(__file__))
OUTPUT_ROOT = PROJECT_ROOT / "test_output" / "rpf_clean_classification"


def main() -> int:
    args = parse_args()
    config = load_clean_config(args.config)
    asset = str(args.asset or config.asset)
    root = str(args.root or config.root)
    target_col = str(args.target_col)
    positive_rule = positive_rule_description(target_col)
    context = resolve_context(project_root=PROJECT_ROOT, asset=asset, root=root, target_col=UP_EXTREME)
    run_root = run_root_for_args(args, target_col)
    run_root.mkdir(parents=True, exist_ok=True)
    print(
        "[rpf-cls] start "
        f"asset={asset} root={root} target={target_col} run={run_root}",
        flush=True,
    )
    all_windows = read_windows(Path(args.base_run) / "frozen_windows.parquet")
    n_steps = int(args.n_steps)
    windows = all_windows[-n_steps:] if n_steps > 0 else all_windows
    if not windows:
        raise ValueError("No frozen windows to run")

    ema_regime_filter = None
    if str(args.window_mode) == EMA_REGIME_BANK:
        side = side_from_target(target_col)
        search_count = int(args.ema_regime_prediction_search_windows)
        base_search_windows = (
            all_windows[-max(n_steps, search_count) :]
            if n_steps > 0 and search_count > 0
            else all_windows
        )
        ema_config = EMARegimeWindowConfig(
            timeframe=str(args.ema_regime_timeframe),
            side=side,
            dominance_rate=float(args.ema_regime_dominance_rate),
            train_batches=int(args.ema_regime_train_batches),
            val_batches=int(args.ema_regime_val_batches),
            candidate_lookback_batches=int(args.ema_regime_candidate_lookback_batches),
            label_maturity_embargo_batches=int(args.ema_regime_label_maturity_embargo_batches),
            buffer=float(args.ema_regime_buffer),
        )
        ema_inventory = build_ema_regime_inventory(
            context,
            asset=asset,
            timeframe=ema_config.timeframe,
            data_root=PROJECT_ROOT / "data",
            buffer=ema_config.buffer,
            batch_chunk_size=int(args.ema_regime_inventory_chunk_batches),
            min_batch_id=min(int(window.pred_batch_id) for window in base_search_windows)
            - int(ema_config.candidate_lookback_batches),
            max_batch_id=max(int(window.pred_batch_id) for window in base_search_windows),
        )
        ema_inventory.write_parquet(run_root / f"ema_regime_inventory_{ema_config.timeframe}.parquet")
        prediction_eligible_windows = filter_ema_prediction_windows(
            base_search_windows,
            ema_inventory,
            side=side,
            min_rate=float(args.ema_regime_prediction_min_rate),
        )
        windows = prediction_eligible_windows[-n_steps:] if n_steps > 0 else prediction_eligible_windows
        if not windows:
            raise ValueError(
                "No EMA-regime prediction windows after filtering: "
                f"timeframe={ema_config.timeframe} side={side} "
                f"prediction_min_rate={float(args.ema_regime_prediction_min_rate)} "
                f"search_windows={len(base_search_windows)}"
            )
        windows, ema_regime_audit = build_ema_regime_windows(windows, ema_inventory, config=ema_config)
        write_rows_parquet(run_root / "window_ema_regime.parquet", ema_regime_audit)
        if bool(args.ema_regime_filter_rows):
            ema_regime_filter = make_ema_regime_filter(
                asset=asset,
                timeframe=ema_config.timeframe,
                side=side,
                buffer=ema_config.buffer,
                data_root=PROJECT_ROOT / "data",
            )
        print(
            "[rpf-cls] ema_regime "
            f"timeframe={ema_config.timeframe} side={side} windows={len(windows)} "
            f"eligible_prediction_windows={len(prediction_eligible_windows)} "
            f"searched_prediction_windows={len(base_search_windows)} "
            f"train_batches={ema_config.train_batches} val_batches={ema_config.val_batches} "
            f"filter_rows={bool(args.ema_regime_filter_rows)}",
            flush=True,
        )

    tuning_windows, holdout_windows = split_tuning_holdout_windows(windows, holdout_steps=int(args.holdout_steps))
    if not tuning_windows:
        raise ValueError("No tuning windows after applying --holdout-steps")

    feature_columns = select_ablation_features(context.manifest.feature_columns, str(args.feature_ablation))
    if args.candidate_panel_path:
        feature_columns = load_panel_features(args.candidate_panel_path, feature_columns)
    sequence_feature_columns = (
        load_panel_features(args.sequence_panel_path, context.manifest.feature_columns)
        if args.sequence_panel_path
        else ()
    )
    base_policy = base_policy_from_args(args)
    sequence_config = sequence_config_from_args(args)

    trials: list[dict[str, Any]] = []
    window_rows: list[dict[str, Any]] = []
    validation_score_rows: list[dict[str, Any]] = []
    prediction_score_rows: list[dict[str, Any]] = []
    selected_feature_rows: list[dict[str, Any]] = []
    thresholds = threshold_values(
        threshold_mode=str(args.threshold_mode),
        decision_threshold=float(args.decision_threshold),
        threshold_grid=str(args.threshold_grid),
    )
    max_signals_grid = validate_decision_policy_signal_grid(
        str(args.decision_policy),
        tuple(parse_ints(args.max_signals_grid)),
    )
    choices = model_choice_grid(args)
    for trial_number, config_updates in enumerate(choices[: int(args.max_configs)]):
        policy = policy_for_trial(base_policy, config_updates)
        model_updates = model_updates_for_trial(args, config_updates)
        print(
            "[rpf-cls] trial_start "
            f"trial={trial_number} windows={len(windows)} model={args.model_family} "
            f"features={feature_label(policy, len(feature_columns))} {model_label(model_updates)}",
            flush=True,
        )
        try:
            payload = run_classification_windows(
                context=context,
                windows=tuning_windows,
                target_col=target_col,
                feature_columns=feature_columns,
                policy=policy,
                model_updates=model_updates,
                model_family=str(args.model_family),
                task_type=str(args.task_type),
                thread_count=int(args.thread_count),
                threshold_mode=str(args.threshold_mode),
                fixed_threshold=float(args.decision_threshold),
                threshold_grid=thresholds,
                max_signals_grid=max_signals_grid,
                decision_policy=str(args.decision_policy),
                objective_metric=str(args.objective_metric),
                trial_objective_split=str(args.trial_objective_split),
                fp_cost=float(args.fp_cost),
                fn_cost=float(args.fn_cost),
                tp_reward=float(args.tp_reward),
                fbeta_beta=float(args.fbeta_beta),
                min_validation_recall=float(args.min_validation_recall),
                min_validation_precision=float(args.min_validation_precision),
                min_validation_predicted_positive_rate=float(args.min_validation_predicted_positive_rate),
                max_validation_false_positive_rate=float(args.max_validation_false_positive_rate),
                min_threshold_pass_rate=float(args.min_threshold_pass_rate),
                max_prediction_zero_positive_window_rate=float(args.max_prediction_zero_positive_window_rate),
                max_prediction_all_positive_window_rate=float(args.max_prediction_all_positive_window_rate),
                prediction_all_positive_rate_threshold=float(args.prediction_all_positive_rate_threshold),
                max_prediction_high_fpr_window_rate=float(args.max_prediction_high_fpr_window_rate),
                max_prediction_window_false_positive_rate=float(args.max_prediction_window_false_positive_rate),
                max_prediction_high_cost_window_rate=float(args.max_prediction_high_cost_window_rate),
                max_prediction_window_decision_cost_per_row=float(args.max_prediction_window_decision_cost_per_row),
                prediction_high_target_positive_rate_threshold=float(args.prediction_high_target_positive_rate_threshold),
                min_prediction_high_target_window_recall=float(args.min_prediction_high_target_window_recall),
                min_prediction_high_target_window_signal_rate=float(args.min_prediction_high_target_window_signal_rate),
                max_prediction_missed_high_target_window_rate=float(args.max_prediction_missed_high_target_window_rate),
                prediction_low_target_positive_rate_threshold=float(args.prediction_low_target_positive_rate_threshold),
                max_prediction_low_target_all_positive_window_rate=float(
                    args.max_prediction_low_target_all_positive_window_rate
                ),
                selector_refit_mode=str(args.selector_refit_mode),
                log_every_windows=int(args.log_every_windows),
                sequence_config=sequence_config,
                sequence_feature_columns=sequence_feature_columns,
                ema_regime_filter=ema_regime_filter,
            )
            status = "ok"
            if not bool(payload.get("threshold_constraints_pass")):
                status = "rejected:threshold_constraints"
            if not bool(payload.get("prediction_window_stability_pass")):
                status = "rejected:window_stability"
            if payload["prediction_metrics"]["prob_unique"] <= int(args.min_prediction_unique):
                status = "rejected:low_prediction_unique"
            if float(payload["prediction_metrics"]["prob_std"] or 0.0) <= float(args.min_prediction_std):
                status = "rejected:low_prediction_std"
            row = trial_row(args, policy, payload, model_updates, trial_number, status)
            row.update(policy_trial_fields(policy))
            trials.append(row)
            for window_row in payload["window_metrics"]:
                window_rows.append({"trial_number": trial_number, **window_row})
            validation_score_rows.extend({"trial_number": trial_number, **item} for item in payload["validation_scores"])
            prediction_score_rows.extend({"trial_number": trial_number, **item} for item in payload["prediction_scores"])
            selected_feature_rows.extend({"trial_number": trial_number, **item} for item in payload["selected_feature_rows"])
            write_partial_outputs(
                run_root=run_root,
                trials=trials,
                window_rows=window_rows,
                validation_score_rows=validation_score_rows,
                prediction_score_rows=prediction_score_rows,
                selected_feature_rows=selected_feature_rows,
            )
            print_trial_done(trial_number, status, row)
        except Exception as exc:
            row = {
                "trial_number": trial_number,
                "status": "error",
                "objective_metric": str(args.objective_metric),
                "trial_objective_split": str(args.trial_objective_split),
                "objective_direction": "minimize",
                "objective_value": 1e9,
                "error": str(exc),
                "feature_ablation": str(args.feature_ablation),
                "feature_policy": base_policy.policy,
                "model_family": str(args.model_family),
                "sequence_panel_path": None if args.sequence_panel_path is None else str(args.sequence_panel_path),
                **model_updates,
                **policy_trial_fields(policy),
            }
            trials.append(row)
            write_partial_outputs(
                run_root=run_root,
                trials=trials,
                window_rows=window_rows,
                validation_score_rows=validation_score_rows,
                prediction_score_rows=prediction_score_rows,
                selected_feature_rows=selected_feature_rows,
            )
            print(f"[rpf-cls] trial_error trial={trial_number} error={exc}", flush=True)

    best = best_trial(trials)
    write_trials(run_root / "trials.parquet", trials)
    write_rows_parquet(run_root / "window_metrics.parquet", window_rows)
    write_rows_parquet(run_root / "validation_scores.parquet", validation_score_rows)
    write_rows_parquet(run_root / "prediction_scores.parquet", prediction_score_rows)
    write_rows_parquet(run_root / "selected_features.parquet", selected_feature_rows)
    write_json(run_root / "best_config.json", best_config_payload(args, asset, root, target_col, positive_rule, base_policy, best))
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
                "tuning_windows": len(tuning_windows),
                "holdout_windows": len(holdout_windows),
                "feature_ablation": str(args.feature_ablation),
                "feature_policy": base_policy.policy,
                "sequence_embedding_mode": sequence_config.mode,
                "sequence_panel_path": None if args.sequence_panel_path is None else str(args.sequence_panel_path),
                "window_mode": str(args.window_mode),
                "threshold_mode": str(args.threshold_mode),
                "decision_policy": str(args.decision_policy),
                "objective_metric": str(args.objective_metric),
                "trial_objective_split": str(args.trial_objective_split),
                "fp_cost": float(args.fp_cost),
                "fn_cost": float(args.fn_cost),
                "tp_reward": float(args.tp_reward),
            },
        },
    )
    if holdout_windows and best is not None and str(best.get("status", "")).startswith("ok"):
        run_holdout(
            args=args,
            context=context,
            run_root=run_root,
            target_col=target_col,
            feature_columns=feature_columns,
            base_policy=base_policy,
            best=best,
            windows=holdout_windows,
            thresholds=thresholds,
            max_signals_grid=max_signals_grid,
            decision_policy=str(args.decision_policy),
            sequence_config=sequence_config,
            sequence_feature_columns=sequence_feature_columns,
            ema_regime_filter=ema_regime_filter,
        )
    print(f"[rpf-cls] done run={run_root}", flush=True)
    return 0


def split_tuning_holdout_windows(windows: list[Any], *, holdout_steps: int) -> tuple[list[Any], list[Any]]:
    holdout_count = int(holdout_steps)
    if holdout_count <= 0:
        return list(windows), []
    if holdout_count >= len(windows):
        raise ValueError(
            f"--holdout-steps={holdout_count} leaves no tuning windows from {len(windows)} total windows"
        )
    return list(windows[:-holdout_count]), list(windows[-holdout_count:])


def write_partial_outputs(
    *,
    run_root: Path,
    trials: list[dict[str, Any]],
    window_rows: list[dict[str, Any]],
    validation_score_rows: list[dict[str, Any]],
    prediction_score_rows: list[dict[str, Any]],
    selected_feature_rows: list[dict[str, Any]],
) -> None:
    write_trials(run_root / "trials.partial.parquet", trials)
    write_rows_parquet(run_root / "window_metrics.partial.parquet", window_rows)
    write_rows_parquet(run_root / "validation_scores.partial.parquet", validation_score_rows)
    write_rows_parquet(run_root / "prediction_scores.partial.parquet", prediction_score_rows)
    write_rows_parquet(run_root / "selected_features.partial.parquet", selected_feature_rows)


def run_holdout(
    *,
    args: argparse.Namespace,
    context: Any,
    run_root: Path,
    target_col: str,
    feature_columns: tuple[str, ...],
    base_policy: FeaturePolicyConfig,
    best: dict[str, Any],
    windows: list[Any],
    thresholds: tuple[float, ...],
    max_signals_grid: tuple[int, ...],
    decision_policy: str,
    sequence_config: SequenceEmbeddingConfig,
    sequence_feature_columns: tuple[str, ...],
    ema_regime_filter: Any | None,
) -> None:
    policy = policy_from_best(base_policy, best)
    model_updates = model_updates_from_best(best)
    print(
        "[rpf-cls] holdout_start "
        f"windows={len(windows)} model={args.model_family} "
        f"features={feature_label(policy, len(feature_columns))} {model_label(model_updates)}",
        flush=True,
    )
    payload = run_classification_windows(
        context=context,
        windows=windows,
        target_col=target_col,
        feature_columns=feature_columns,
        policy=policy,
        model_updates=model_updates,
        model_family=str(args.model_family),
        task_type=str(args.task_type),
        thread_count=int(args.thread_count),
        threshold_mode=str(args.threshold_mode),
        fixed_threshold=float(args.decision_threshold),
        threshold_grid=thresholds,
        max_signals_grid=max_signals_grid,
        decision_policy=str(decision_policy),
        objective_metric=str(args.objective_metric),
        trial_objective_split="prediction",
        fp_cost=float(args.fp_cost),
        fn_cost=float(args.fn_cost),
        tp_reward=float(args.tp_reward),
        fbeta_beta=float(args.fbeta_beta),
        min_validation_recall=float(args.min_validation_recall),
        min_validation_precision=float(args.min_validation_precision),
        min_validation_predicted_positive_rate=float(args.min_validation_predicted_positive_rate),
        max_validation_false_positive_rate=float(args.max_validation_false_positive_rate),
        min_threshold_pass_rate=float(args.min_threshold_pass_rate),
        max_prediction_zero_positive_window_rate=float(args.max_prediction_zero_positive_window_rate),
        max_prediction_all_positive_window_rate=float(args.max_prediction_all_positive_window_rate),
        prediction_all_positive_rate_threshold=float(args.prediction_all_positive_rate_threshold),
        max_prediction_high_fpr_window_rate=float(args.max_prediction_high_fpr_window_rate),
        max_prediction_window_false_positive_rate=float(args.max_prediction_window_false_positive_rate),
        max_prediction_high_cost_window_rate=float(args.max_prediction_high_cost_window_rate),
        max_prediction_window_decision_cost_per_row=float(args.max_prediction_window_decision_cost_per_row),
        prediction_high_target_positive_rate_threshold=float(args.prediction_high_target_positive_rate_threshold),
        min_prediction_high_target_window_recall=float(args.min_prediction_high_target_window_recall),
        min_prediction_high_target_window_signal_rate=float(args.min_prediction_high_target_window_signal_rate),
        max_prediction_missed_high_target_window_rate=float(args.max_prediction_missed_high_target_window_rate),
        prediction_low_target_positive_rate_threshold=float(args.prediction_low_target_positive_rate_threshold),
        max_prediction_low_target_all_positive_window_rate=float(args.max_prediction_low_target_all_positive_window_rate),
        selector_refit_mode=str(args.selector_refit_mode),
        log_every_windows=int(args.log_every_windows),
        sequence_config=sequence_config,
        sequence_feature_columns=sequence_feature_columns,
        ema_regime_filter=ema_regime_filter,
    )
    holdout_summary = {
        "source_best_trial_number": best.get("trial_number"),
        "source_objective_value": best.get("objective_value"),
        "window_count": len(windows),
        "objective_metric": payload["objective_metric"],
        "trial_objective_split": payload["trial_objective_split"],
        "objective_direction": payload["objective_direction"],
        "objective_value": payload["objective_value"],
        "decision_policy": str(decision_policy),
        "decision_policy_live_safe": bool(payload["decision_policy_live_safe"]),
        "threshold_constraints_pass": payload["threshold_constraints_pass"],
        "threshold_constraints_reason": payload["threshold_constraints_reason"],
        "prediction_window_stability_pass": payload["prediction_window_stability_pass"],
        "prediction_window_stability_reason": payload["prediction_window_stability_reason"],
        **flatten_objective_components(payload.get("objective_components", {})),
        **flatten_stability(payload["prediction_window_stability"], "prediction"),
        **flatten_metrics(payload["validation_metrics"], "validation"),
        **flatten_metrics(payload["prediction_metrics"], "prediction"),
        **model_updates,
        **policy_trial_fields(policy),
    }
    write_json(run_root / "holdout_summary.json", holdout_summary)
    write_rows_parquet(run_root / "holdout_window_metrics.parquet", payload["window_metrics"])
    write_rows_parquet(run_root / "holdout_validation_scores.parquet", payload["validation_scores"])
    write_rows_parquet(run_root / "holdout_prediction_scores.parquet", payload["prediction_scores"])
    write_rows_parquet(run_root / "holdout_selected_features.parquet", payload["selected_feature_rows"])
    print(
        "[rpf-cls] holdout_done "
        f"objective={fmt_metric(holdout_summary.get('objective_value'))} "
        f"pred_cost={fmt_metric(holdout_summary.get('prediction_decision_cost_per_row'))} "
        f"pred_precision={fmt_metric(holdout_summary.get('prediction_precision'))} "
        f"pred_recall={fmt_metric(holdout_summary.get('prediction_recall'))} "
        f"pred_fpr={fmt_metric(holdout_summary.get('prediction_false_positive_rate'))}",
        flush=True,
    )


def trial_row(
    args: argparse.Namespace,
    policy: FeaturePolicyConfig,
    payload: dict[str, Any],
    model_updates: dict[str, Any],
    trial_number: int,
    status: str,
) -> dict[str, Any]:
    return {
        "trial_number": trial_number,
        "status": status,
        "objective_metric": payload["objective_metric"],
        "trial_objective_split": payload["trial_objective_split"],
        "objective_direction": payload["objective_direction"],
        "objective_value": payload["objective_value"],
        "feature_ablation": str(args.feature_ablation),
        "feature_policy": policy.policy,
        "selector_refit_mode": str(args.selector_refit_mode),
        "model_family": str(args.model_family),
        "sequence_embedding_mode": str(args.sequence_embedding_mode),
        "sequence_length": int(args.sequence_length),
        "sequence_embedding_dim": int(args.sequence_embedding_dim),
        "sequence_conv_channels": int(args.sequence_conv_channels),
        "sequence_kernel_size": int(args.sequence_kernel_size),
        "sequence_dropout": float(args.sequence_dropout),
        "sequence_epochs": int(args.sequence_epochs),
        "sequence_batch_size": int(args.sequence_batch_size),
        "sequence_learning_rate": float(args.sequence_learning_rate),
        "sequence_max_train_rows": int(args.sequence_max_train_rows),
        "requested_window_count": int(args.n_steps),
        "holdout_window_count": int(args.holdout_steps),
        "window_mode": str(args.window_mode),
        "ema_regime_timeframe": str(args.ema_regime_timeframe) if str(args.window_mode) == EMA_REGIME_BANK else None,
        "ema_regime_buffer": float(args.ema_regime_buffer) if str(args.window_mode) == EMA_REGIME_BANK else None,
        "ema_regime_filter_rows": bool(args.ema_regime_filter_rows) if str(args.window_mode) == EMA_REGIME_BANK else False,
        "ema_regime_inventory_chunk_batches": int(args.ema_regime_inventory_chunk_batches)
        if str(args.window_mode) == EMA_REGIME_BANK
        else None,
        "ema_regime_prediction_min_rate": float(args.ema_regime_prediction_min_rate)
        if str(args.window_mode) == EMA_REGIME_BANK
        else None,
        "ema_regime_prediction_search_windows": int(args.ema_regime_prediction_search_windows)
        if str(args.window_mode) == EMA_REGIME_BANK
        else None,
        "threshold_mode": str(args.threshold_mode),
        "decision_policy": str(args.decision_policy),
        "decision_policy_live_safe": bool(payload["decision_policy_live_safe"]),
        "selected_threshold": payload["selected_threshold"],
        "selected_threshold_min": payload["selected_threshold_min"],
        "selected_threshold_max": payload["selected_threshold_max"],
        "selected_max_signals": payload["selected_max_signals"],
        "selected_max_signals_min": payload["selected_max_signals_min"],
        "selected_max_signals_max": payload["selected_max_signals_max"],
        "threshold_constraints_pass": payload["threshold_constraints_pass"],
        "threshold_constraints_pass_rate": payload["threshold_constraints_pass_rate"],
        "min_threshold_pass_rate": payload["min_threshold_pass_rate"],
        "threshold_constraints_reason": payload["threshold_constraints_reason"],
        "prediction_window_stability_pass": payload["prediction_window_stability_pass"],
        "prediction_window_stability_reason": payload["prediction_window_stability_reason"],
        "fp_cost": float(args.fp_cost),
        "fn_cost": float(args.fn_cost),
        "tp_reward": float(args.tp_reward),
        "fbeta_beta": float(args.fbeta_beta),
        **model_updates,
        **flatten_objective_components(payload.get("objective_components", {})),
        **flatten_metrics(payload["validation_metrics"], "validation"),
        **flatten_metrics(payload["prediction_metrics"], "prediction"),
        **flatten_stability(payload["prediction_window_stability"], "prediction"),
        "selected_feature_count_min": payload["selected_feature_count_min"],
        "selected_feature_count_mean": payload["selected_feature_count_mean"],
        "attempted_window_count": payload["attempted_window_count"],
        "executed_window_count": payload["executed_window_count"],
        "skipped_window_count": payload["skipped_window_count"],
        "skipped_window_rate": payload["skipped_window_rate"],
    }


def flatten_stability(stability: dict[str, Any], prefix: str) -> dict[str, Any]:
    return {f"{prefix}_{key}": value for key, value in stability.items()}


def flatten_objective_components(components: dict[str, Any]) -> dict[str, Any]:
    return {f"objective_component_{key}": value for key, value in components.items()}


def best_config_payload(
    args: argparse.Namespace,
    asset: str,
    root: str,
    target_col: str,
    positive_rule: str,
    policy: FeaturePolicyConfig,
    best: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "target_col": target_col,
        "positive_rule": positive_rule,
        "asset": asset,
        "root": root,
        "feature_ablation": str(args.feature_ablation),
        "feature_policy": policy.policy,
        "model_family": str(args.model_family),
        "sequence_embedding": {
            "mode": str(args.sequence_embedding_mode),
            "sequence_length": int(args.sequence_length),
            "embedding_dim": int(args.sequence_embedding_dim),
            "conv_channels": int(args.sequence_conv_channels),
            "kernel_size": int(args.sequence_kernel_size),
            "dropout": float(args.sequence_dropout),
            "epochs": int(args.sequence_epochs),
            "batch_size": int(args.sequence_batch_size),
            "learning_rate": float(args.sequence_learning_rate),
            "max_train_rows": int(args.sequence_max_train_rows),
            "device": str(args.sequence_device),
        },
        "requested_window_count": int(args.n_steps),
        "holdout_window_count": int(args.holdout_steps),
        "policy": best_policy_fields(best) or policy_trial_fields(policy),
        "candidate_panel_path": None if args.candidate_panel_path is None else str(args.candidate_panel_path),
        "sequence_panel_path": None if args.sequence_panel_path is None else str(args.sequence_panel_path),
        "frozen_panel_path": None if args.frozen_panel_path is None else str(args.frozen_panel_path),
        "selector_refit_mode": str(args.selector_refit_mode),
        "window_mode": str(args.window_mode),
        "ema_regime": {
            "timeframe": str(args.ema_regime_timeframe),
            "dominance_rate": float(args.ema_regime_dominance_rate),
            "train_batches": int(args.ema_regime_train_batches),
            "val_batches": int(args.ema_regime_val_batches),
            "candidate_lookback_batches": int(args.ema_regime_candidate_lookback_batches),
            "label_maturity_embargo_batches": int(args.ema_regime_label_maturity_embargo_batches),
            "buffer": float(args.ema_regime_buffer),
            "filter_rows": bool(args.ema_regime_filter_rows),
            "inventory_chunk_batches": int(args.ema_regime_inventory_chunk_batches),
            "prediction_min_rate": float(args.ema_regime_prediction_min_rate),
            "prediction_search_windows": int(args.ema_regime_prediction_search_windows),
        }
        if str(args.window_mode) == EMA_REGIME_BANK
        else None,
        "threshold_mode": str(args.threshold_mode),
        "decision_policy": str(args.decision_policy),
        "max_signals_grid": str(args.max_signals_grid),
        "objective_metric": str(args.objective_metric),
        "trial_objective_split": str(args.trial_objective_split),
        "fp_cost": float(args.fp_cost),
        "fn_cost": float(args.fn_cost),
        "tp_reward": float(args.tp_reward),
        "min_threshold_pass_rate": float(args.min_threshold_pass_rate),
        "max_prediction_zero_positive_window_rate": float(args.max_prediction_zero_positive_window_rate),
        "max_prediction_all_positive_window_rate": float(args.max_prediction_all_positive_window_rate),
        "prediction_all_positive_rate_threshold": float(args.prediction_all_positive_rate_threshold),
        "max_prediction_high_fpr_window_rate": float(args.max_prediction_high_fpr_window_rate),
        "max_prediction_window_false_positive_rate": float(args.max_prediction_window_false_positive_rate),
        "max_prediction_high_cost_window_rate": float(args.max_prediction_high_cost_window_rate),
        "max_prediction_window_decision_cost_per_row": float(args.max_prediction_window_decision_cost_per_row),
        "prediction_high_target_positive_rate_threshold": float(args.prediction_high_target_positive_rate_threshold),
        "min_prediction_high_target_window_recall": float(args.min_prediction_high_target_window_recall),
        "min_prediction_high_target_window_signal_rate": float(args.min_prediction_high_target_window_signal_rate),
        "max_prediction_missed_high_target_window_rate": float(args.max_prediction_missed_high_target_window_rate),
        "prediction_low_target_positive_rate_threshold": float(args.prediction_low_target_positive_rate_threshold),
        "max_prediction_low_target_all_positive_window_rate": float(args.max_prediction_low_target_all_positive_window_rate),
        "best": best,
    }


def print_trial_done(trial_number: int, status: str, row: dict[str, Any]) -> None:
    print(
        "[rpf-cls] trial_done "
        f"trial={trial_number} status={status} "
        f"objective={fmt_metric(row.get('objective_value'))} "
        f"threshold={fmt_metric(row.get('selected_threshold'))} "
        f"max_signals={fmt_metric(row.get('selected_max_signals'))} "
        f"decision_policy={row.get('decision_policy')} "
        f"val_cost={fmt_metric(row.get('validation_decision_cost_per_row'))} "
        f"val_precision={fmt_metric(row.get('validation_precision'))} "
        f"val_recall={fmt_metric(row.get('validation_recall'))} "
        f"val_fpr={fmt_metric(row.get('validation_false_positive_rate'))} "
        f"pred_cost={fmt_metric(row.get('prediction_decision_cost_per_row'))} "
        f"pred_precision={fmt_metric(row.get('prediction_precision'))} "
        f"pred_recall={fmt_metric(row.get('prediction_recall'))} "
        f"pred_fpr={fmt_metric(row.get('prediction_false_positive_rate'))} "
        f"pred_pos_rate={fmt_metric(row.get('prediction_predicted_positive_rate'))} "
        f"zero_win_rate={fmt_metric(row.get('prediction_zero_positive_window_rate'))} "
        f"all_win_rate={fmt_metric(row.get('prediction_all_positive_window_rate'))} "
        f"miss_high_rate={fmt_metric(row.get('prediction_missed_high_target_window_rate'))} "
        f"low_all_rate={fmt_metric(row.get('prediction_low_target_all_positive_window_rate'))}",
        flush=True,
    )


def best_trial(trials: list[dict[str, Any]]) -> dict[str, Any] | None:
    non_error_trials = [trial for trial in trials if str(trial.get("status", "")) != "error"]
    if non_error_trials and str(non_error_trials[0].get("objective_metric")) == "stable_prediction_quality":
        pool = non_error_trials
    else:
        ok_trials = [trial for trial in trials if str(trial.get("status", "")).startswith("ok")]
        pool = ok_trials or non_error_trials or trials
    if not pool:
        return None
    direction = str(pool[0].get("objective_direction") or "minimize")
    key = lambda row: none_to_bad(row.get("objective_value"), minimize=(direction == "minimize"))
    return min(pool, key=key) if direction == "minimize" else max(pool, key=key)


def model_choice_grid(args: argparse.Namespace) -> list[dict[str, Any]]:
    keys: tuple[tuple[str, list[Any]], ...] = (
        ("iterations", parse_ints(args.iterations_choices)),
        ("depth", parse_ints(args.depth_choices)),
        ("learning_rate", parse_floats(args.learning_rate_choices)),
        ("l2_leaf_reg", parse_floats(args.l2_leaf_reg_choices)),
        ("early_stopping_rounds", parse_ints(args.early_stopping_rounds_choices)),
        ("od_wait", parse_ints(args.od_wait_choices)),
    )
    if str(args.feature_policy) == ELASTICNET_LOGISTIC_V1:
        keys = (
            *keys,
            ("elasticnet_c", parse_floats(args.elasticnet_c_choices)),
            ("elasticnet_l1_ratio", parse_floats(args.elasticnet_l1_ratio_choices)),
            ("elasticnet_max_features", parse_ints(args.elasticnet_max_features_choices)),
            ("elasticnet_coef_epsilon", elasticnet_coef_epsilon_choices(args)),
            ("elasticnet_prefilter_features", elasticnet_prefilter_feature_choices(args)),
        )
    return [dict(zip((key for key, _ in keys), values)) for values in itertools.product(*(values for _, values in keys))]


def model_updates_for_trial(args: argparse.Namespace, config_updates: dict[str, Any]) -> dict[str, Any]:
    keys = ("iterations", "depth", "learning_rate", "l2_leaf_reg", "early_stopping_rounds", "od_wait")
    return {key: config_updates[key] for key in keys}


def model_label(model_updates: dict[str, Any]) -> str:
    return (
        f"it={model_updates['iterations']} depth={model_updates['depth']} "
        f"lr={model_updates['learning_rate']}"
    )


def base_policy_from_args(args: argparse.Namespace) -> FeaturePolicyConfig:
    if args.frozen_panel_path:
        return FeaturePolicyConfig(
            policy=FROZEN_PANEL,
            frozen_panel_path=str(args.frozen_panel_path),
            min_selected_features=1,
        )
    policy_name = str(args.feature_policy)
    if policy_name == ALL_MANIFEST_FEATURES:
        return FeaturePolicyConfig(policy=ALL_MANIFEST_FEATURES)
    if policy_name == ELASTICNET_LOGISTIC_V1:
        coef_epsilon_choices = elasticnet_coef_epsilon_choices(args)
        return FeaturePolicyConfig(
            policy=ELASTICNET_LOGISTIC_V1,
            max_features=int(parse_ints(args.elasticnet_max_features_choices)[0]),
            min_selected_features=int(args.elasticnet_min_selected_features),
            elasticnet_c=float(parse_floats(args.elasticnet_c_choices)[0]),
            elasticnet_l1_ratio=float(parse_floats(args.elasticnet_l1_ratio_choices)[0]),
            elasticnet_max_iter=int(args.elasticnet_max_iter),
            elasticnet_tol=float(args.elasticnet_tol),
            elasticnet_class_weight=None
            if str(args.elasticnet_class_weight).lower() in {"none", ""}
            else str(args.elasticnet_class_weight),
            elasticnet_coef_epsilon=float(coef_epsilon_choices[0]),
            elasticnet_prefilter_features=int(elasticnet_prefilter_feature_choices(args)[0]),
        )
    raise ValueError(f"Unsupported classifier feature policy: {policy_name}")


def policy_for_trial(base_policy: FeaturePolicyConfig, config_updates: dict[str, Any]) -> FeaturePolicyConfig:
    if base_policy.policy != ELASTICNET_LOGISTIC_V1:
        return base_policy
    return replace(
        base_policy,
        elasticnet_c=float(config_updates.get("elasticnet_c", base_policy.elasticnet_c)),
        elasticnet_l1_ratio=float(config_updates.get("elasticnet_l1_ratio", base_policy.elasticnet_l1_ratio)),
        max_features=int(config_updates.get("elasticnet_max_features", base_policy.max_features)),
        elasticnet_coef_epsilon=float(
            config_updates.get("elasticnet_coef_epsilon", base_policy.elasticnet_coef_epsilon)
        ),
        elasticnet_prefilter_features=int(
            config_updates.get("elasticnet_prefilter_features", base_policy.elasticnet_prefilter_features)
        ),
    )


def policy_trial_fields(policy: FeaturePolicyConfig) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "policy_max_features": int(policy.max_features),
        "policy_min_selected_features": int(policy.min_selected_features),
    }
    if policy.policy == ELASTICNET_LOGISTIC_V1:
        fields.update(
            {
                "elasticnet_c": float(policy.elasticnet_c),
                "elasticnet_l1_ratio": float(policy.elasticnet_l1_ratio),
                "elasticnet_max_iter": int(policy.elasticnet_max_iter),
                "elasticnet_tol": float(policy.elasticnet_tol),
                "elasticnet_class_weight": policy.elasticnet_class_weight,
                "elasticnet_coef_epsilon": float(policy.elasticnet_coef_epsilon),
                "elasticnet_prefilter_features": int(policy.elasticnet_prefilter_features),
            }
        )
    return fields


def best_policy_fields(best: dict[str, Any] | None) -> dict[str, Any]:
    if not best:
        return {}
    keys = (
        "policy_max_features",
        "policy_min_selected_features",
        "elasticnet_c",
        "elasticnet_l1_ratio",
        "elasticnet_max_iter",
        "elasticnet_tol",
        "elasticnet_class_weight",
        "elasticnet_coef_epsilon",
        "elasticnet_prefilter_features",
    )
    return {key: best[key] for key in keys if key in best}


def policy_from_best(base_policy: FeaturePolicyConfig, best: dict[str, Any]) -> FeaturePolicyConfig:
    if base_policy.policy != ELASTICNET_LOGISTIC_V1:
        return base_policy
    return replace(
        base_policy,
        max_features=int(best.get("policy_max_features", base_policy.max_features)),
        min_selected_features=int(best.get("policy_min_selected_features", base_policy.min_selected_features)),
        elasticnet_c=float(best.get("elasticnet_c", base_policy.elasticnet_c)),
        elasticnet_l1_ratio=float(best.get("elasticnet_l1_ratio", base_policy.elasticnet_l1_ratio)),
        elasticnet_max_iter=int(best.get("elasticnet_max_iter", base_policy.elasticnet_max_iter)),
        elasticnet_tol=float(best.get("elasticnet_tol", base_policy.elasticnet_tol)),
        elasticnet_class_weight=best.get("elasticnet_class_weight", base_policy.elasticnet_class_weight),
        elasticnet_coef_epsilon=float(best.get("elasticnet_coef_epsilon", base_policy.elasticnet_coef_epsilon)),
        elasticnet_prefilter_features=int(best.get("elasticnet_prefilter_features", base_policy.elasticnet_prefilter_features)),
    )


def sequence_config_from_args(args: argparse.Namespace) -> SequenceEmbeddingConfig:
    return SequenceEmbeddingConfig(
        mode=str(args.sequence_embedding_mode),
        sequence_length=int(args.sequence_length),
        embedding_dim=int(args.sequence_embedding_dim),
        conv_channels=int(args.sequence_conv_channels),
        kernel_size=int(args.sequence_kernel_size),
        dropout=float(args.sequence_dropout),
        epochs=int(args.sequence_epochs),
        batch_size=int(args.sequence_batch_size),
        learning_rate=float(args.sequence_learning_rate),
        max_train_rows=int(args.sequence_max_train_rows),
        device=str(args.sequence_device),
    )


def model_updates_from_best(best: dict[str, Any]) -> dict[str, Any]:
    return {
        "iterations": int(best["iterations"]),
        "depth": int(best["depth"]),
        "learning_rate": float(best["learning_rate"]),
        "l2_leaf_reg": float(best["l2_leaf_reg"]),
        "early_stopping_rounds": int(best["early_stopping_rounds"]),
        "od_wait": int(best["od_wait"]),
    }


def write_rows_parquet(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        pl.DataFrame(rows, infer_schema_length=None).write_parquet(path)
    else:
        pl.DataFrame().write_parquet(path)


def elasticnet_coef_epsilon_choices(args: argparse.Namespace) -> list[float]:
    values = str(args.elasticnet_coef_epsilon_choices or "").strip()
    if values:
        return parse_floats(values)
    return [float(args.elasticnet_coef_epsilon)]


def elasticnet_prefilter_feature_choices(args: argparse.Namespace) -> list[int]:
    values = str(args.elasticnet_prefilter_features_choices or "").strip()
    if values:
        return parse_ints(values)
    return [int(args.elasticnet_prefilter_features)]


def feature_label(policy: FeaturePolicyConfig, feature_count: int) -> str:
    if policy.policy == FROZEN_PANEL:
        return f"frozen_panel:{policy.frozen_panel_path}"
    if policy.policy == ELASTICNET_LOGISTIC_V1:
        return (
            f"elasticnet:max{policy.max_features}:C{policy.elasticnet_c}:"
            f"l1{policy.elasticnet_l1_ratio}:eps{policy.elasticnet_coef_epsilon}:"
            f"pref{policy.elasticnet_prefilter_features}"
        )
    return str(feature_count)


def run_root_for_args(args: argparse.Namespace, target_col: str) -> Path:
    now = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    target_slug = target_col.replace("target_", "")[:44]
    return Path(args.output_dir) / f"{now}_classification_{target_slug}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run RPF binary classification walk-forward.")
    parser.add_argument("--asset", default=None)
    parser.add_argument("--root", default=None)
    parser.add_argument("--target-col", default=TARGET_BINARY_UP_2X_DOWN)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--base-run", type=Path, required=True)
    parser.add_argument("--feature-ablation", default="all")
    parser.add_argument("--feature-policy", choices=[ALL_MANIFEST_FEATURES, ELASTICNET_LOGISTIC_V1], default=ALL_MANIFEST_FEATURES)
    parser.add_argument("--model-family", choices=MODEL_FAMILIES, default=MODEL_CATBOOST)
    parser.add_argument("--sequence-embedding-mode", choices=SEQUENCE_EMBEDDING_MODES, default=SEQUENCE_NONE)
    parser.add_argument("--sequence-length", type=int, default=16)
    parser.add_argument("--sequence-embedding-dim", type=int, default=8)
    parser.add_argument("--sequence-conv-channels", type=int, default=16)
    parser.add_argument("--sequence-kernel-size", type=int, default=3)
    parser.add_argument("--sequence-dropout", type=float, default=0.10)
    parser.add_argument("--sequence-epochs", type=int, default=3)
    parser.add_argument("--sequence-batch-size", type=int, default=512)
    parser.add_argument("--sequence-learning-rate", type=float, default=0.001)
    parser.add_argument("--sequence-max-train-rows", type=int, default=12000)
    parser.add_argument("--sequence-device", default="cpu")
    parser.add_argument(
        "--candidate-panel-path",
        type=Path,
        default=None,
        help=(
            "Optional frozen panel used only as the candidate feature universe. "
            "ElasticNet can still select train-only features inside this panel."
        ),
    )
    parser.add_argument(
        "--sequence-panel-path",
        type=Path,
        default=None,
        help=(
            "Optional frozen panel used only by the causal CNN sequence branch. "
            "ElasticNet/CatBoost tabular candidate features are controlled separately by "
            "--feature-ablation and --candidate-panel-path."
        ),
    )
    parser.add_argument("--frozen-panel-path", type=Path, default=None)
    parser.add_argument(
        "--selector-refit-mode",
        choices=SELECTOR_REFIT_MODES,
        default=SELECTOR_REFIT_VALIDATION_MASK,
        help=(
            "How ElasticNet is handled for the final train+validation CatBoost refit. "
            "validation_mask freezes the validation-selected feature mask so threshold calibration transfers; "
            "train_val_reselect preserves the older behavior and reruns ElasticNet on train+validation."
        ),
    )
    parser.add_argument("--window-mode", choices=WINDOW_MODES, default=CHRONOLOGICAL_RECENT)
    parser.add_argument("--ema-regime-timeframe", choices=["15m", "1h", "4h", "1d"], default="1h")
    parser.add_argument("--ema-regime-dominance-rate", type=float, default=0.80)
    parser.add_argument("--ema-regime-train-batches", type=int, default=120)
    parser.add_argument("--ema-regime-val-batches", type=int, default=20)
    parser.add_argument("--ema-regime-candidate-lookback-batches", type=int, default=2000)
    parser.add_argument("--ema-regime-label-maturity-embargo-batches", type=int, default=1)
    parser.add_argument("--ema-regime-buffer", type=float, default=0.0)
    parser.add_argument("--ema-regime-inventory-chunk-batches", type=int, default=32)
    parser.add_argument("--ema-regime-prediction-min-rate", type=float, default=0.0)
    parser.add_argument("--ema-regime-prediction-search-windows", type=int, default=250)
    parser.add_argument("--ema-regime-filter-rows", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--n-steps", type=int, default=15)
    parser.add_argument("--holdout-steps", type=int, default=0)
    parser.add_argument("--max-configs", type=int, default=12)
    parser.add_argument("--log-every-windows", type=int, default=1)
    parser.add_argument("--task-type", choices=["CPU", "GPU"], default="CPU")
    parser.add_argument("--thread-count", type=int, default=-1)
    parser.add_argument("--iterations-choices", default="400,800")
    parser.add_argument("--depth-choices", default="2,3")
    parser.add_argument("--learning-rate-choices", default="0.01,0.02")
    parser.add_argument("--l2-leaf-reg-choices", default="10,30")
    parser.add_argument("--early-stopping-rounds-choices", default="100")
    parser.add_argument("--od-wait-choices", default="100")
    parser.add_argument("--elasticnet-c-choices", default="0.03,0.1,0.3")
    parser.add_argument("--elasticnet-l1-ratio-choices", default="0.25,0.5,0.75")
    parser.add_argument("--elasticnet-max-features-choices", default="80,160,320")
    parser.add_argument("--elasticnet-min-selected-features", type=int, default=20)
    parser.add_argument("--elasticnet-max-iter", type=int, default=1000)
    parser.add_argument("--elasticnet-tol", type=float, default=0.001)
    parser.add_argument("--elasticnet-class-weight", choices=["balanced", "none"], default="balanced")
    parser.add_argument("--elasticnet-coef-epsilon", type=float, default=1e-8)
    parser.add_argument("--elasticnet-coef-epsilon-choices", default=None)
    parser.add_argument("--elasticnet-prefilter-features", type=int, default=0)
    parser.add_argument("--elasticnet-prefilter-features-choices", default=None)
    parser.add_argument("--min-prediction-unique", type=int, default=10)
    parser.add_argument("--min-prediction-std", type=float, default=1e-6)
    parser.add_argument(
        "--objective-metric",
        choices=[
            "validation_logloss",
            "validation_decision_cost",
            "validation_false_positive_rate",
            "validation_precision",
            "validation_precision_lift",
            "validation_fbeta",
            "validation_balanced_accuracy",
            "validation_pr_auc",
            "validation_mcc",
            "stable_prediction_quality",
            "stable_signal_quality",
        ],
        default="validation_logloss",
    )
    parser.add_argument("--trial-objective-split", choices=["validation", "prediction"], default="prediction")
    parser.add_argument("--threshold-mode", choices=["fixed", "validation_sweep"], default="fixed")
    parser.add_argument("--decision-threshold", type=float, default=0.5)
    parser.add_argument(
        "--decision-policy",
        choices=DECISION_POLICIES,
        default=DECISION_POLICY_THRESHOLD_ONLY,
        help=(
            "How thresholded probabilities become signals. threshold_only is live-safe; "
            "causal_signal_budget is live-safe if rows are timestamp ordered; "
            "batch_topk_offline is diagnostic only because it ranks the full prediction batch."
        ),
    )
    parser.add_argument(
        "--threshold-grid",
        default="0.05,0.10,0.15,0.20,0.25,0.30,0.35,0.40,0.45,0.50,0.55,0.60,0.65,0.70,0.75,0.80,0.85,0.90,0.95",
    )
    parser.add_argument(
        "--max-signals-grid",
        default="0",
        help="Comma-separated per-batch signal caps considered with threshold selection; 0 means unlimited.",
    )
    parser.add_argument("--fp-cost", type=float, default=1.0)
    parser.add_argument("--fn-cost", type=float, default=1.0)
    parser.add_argument("--tp-reward", type=float, default=0.0)
    parser.add_argument("--fbeta-beta", type=float, default=0.5)
    parser.add_argument("--min-validation-recall", type=float, default=0.0)
    parser.add_argument("--min-validation-precision", type=float, default=0.0)
    parser.add_argument("--min-validation-predicted-positive-rate", type=float, default=0.0)
    parser.add_argument("--max-validation-false-positive-rate", type=float, default=1.0)
    parser.add_argument("--min-threshold-pass-rate", type=float, default=1.0)
    parser.add_argument("--max-prediction-zero-positive-window-rate", type=float, default=1.0)
    parser.add_argument("--max-prediction-all-positive-window-rate", type=float, default=1.0)
    parser.add_argument("--prediction-all-positive-rate-threshold", type=float, default=0.95)
    parser.add_argument("--max-prediction-high-fpr-window-rate", type=float, default=1.0)
    parser.add_argument("--max-prediction-window-false-positive-rate", type=float, default=1.0)
    parser.add_argument("--max-prediction-high-cost-window-rate", type=float, default=1.0)
    parser.add_argument("--max-prediction-window-decision-cost-per-row", type=float, default=1e9)
    parser.add_argument("--prediction-high-target-positive-rate-threshold", type=float, default=0.70)
    parser.add_argument("--min-prediction-high-target-window-recall", type=float, default=0.05)
    parser.add_argument("--min-prediction-high-target-window-signal-rate", type=float, default=0.01)
    parser.add_argument("--max-prediction-missed-high-target-window-rate", type=float, default=1.0)
    parser.add_argument("--prediction-low-target-positive-rate-threshold", type=float, default=0.35)
    parser.add_argument("--max-prediction-low-target-all-positive-window-rate", type=float, default=1.0)
    return parser.parse_args()
