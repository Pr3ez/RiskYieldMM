"""Optuna command surface for chronological RPF binary classification."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from regression_feature_engineering.walkforward.ablation import select_ablation_features
from regression_feature_engineering.walkforward.classification.cli import (
    OUTPUT_ROOT,
    PROJECT_ROOT,
    base_policy_from_args,
    best_config_payload,
    best_trial,
    feature_label,
    flatten_objective_components,
    model_label,
    model_updates_for_trial,
    policy_for_trial,
    policy_trial_fields,
    print_trial_done,
    run_holdout,
    run_root_for_args,
    sequence_config_from_args,
    split_tuning_holdout_windows,
    trial_row,
    write_partial_outputs,
    write_rows_parquet,
)
from regression_feature_engineering.walkforward.classification.metrics import (
    DECISION_POLICIES,
    DECISION_POLICY_CAUSAL_SIGNAL_BUDGET,
    classification_objective,
    none_to_bad,
    parse_floats,
    parse_ints,
    threshold_values,
    validate_decision_policy_signal_grid,
)
from regression_feature_engineering.walkforward.classification.model import MODEL_CATBOOST, MODEL_FAMILIES
from regression_feature_engineering.walkforward.classification.runner import (
    SELECTOR_REFIT_MODES,
    SELECTOR_REFIT_VALIDATION_MASK,
    run_classification_windows,
)
from regression_feature_engineering.walkforward.classification.sequence import SEQUENCE_EMBEDDING_MODES, SEQUENCE_NONE
from regression_feature_engineering.walkforward.classification.targets import (
    TARGET_BINARY_UP_2X_DOWN,
    UP_EXTREME,
    positive_rule_description,
)
from regression_feature_engineering.walkforward.config import load_clean_config
from regression_feature_engineering.walkforward.data import resolve_context
from regression_feature_engineering.walkforward.ema_regime import CHRONOLOGICAL_RECENT
from regression_feature_engineering.walkforward.policy import ALL_MANIFEST_FEATURES, ELASTICNET_LOGISTIC_V1, load_panel_features
from regression_feature_engineering.walkforward.reports import write_json, write_markdown, write_trials
from regression_feature_engineering.walkforward.windows import read_windows


OPTUNA_OUTPUT_ROOT = OUTPUT_ROOT.parent / "rpf_clean_classification_optuna"


def main() -> int:
    args = parse_args()
    try:
        import optuna
    except Exception as exc:  # pragma: no cover - depends on active environment
        raise RuntimeError(
            "Optuna is required for classify_optuna. Run with the ml_env Python "
            "or install optuna in the active environment."
        ) from exc

    config = load_clean_config(args.config)
    asset = str(args.asset or config.asset)
    root = str(args.root or config.root)
    target_col = str(args.target_col)
    positive_rule = positive_rule_description(target_col)
    context = resolve_context(project_root=PROJECT_ROOT, asset=asset, root=root, target_col=UP_EXTREME)
    all_windows = read_windows(Path(args.base_run) / "frozen_windows.parquet")
    windows = all_windows[-int(args.n_steps) :] if int(args.n_steps) > 0 else all_windows
    if not windows:
        raise ValueError("No frozen windows to run")
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
    thresholds = threshold_values(
        threshold_mode=str(args.threshold_mode),
        decision_threshold=float(args.decision_threshold),
        threshold_grid=str(args.threshold_grid),
    )
    max_signals_grid = validate_decision_policy_signal_grid(
        str(args.decision_policy),
        tuple(parse_ints(args.max_signals_grid)),
    )
    direction, _ = classification_objective({}, str(args.objective_metric))
    run_root = run_root_for_args(args, target_col)
    run_root.mkdir(parents=True, exist_ok=True)
    print(
        "[rpf-cls-optuna] start "
        f"asset={asset} root={root} target={target_col} trials={int(args.n_trials)} "
        f"objective={args.objective_metric} direction={direction} run={run_root}",
        flush=True,
    )

    trials: list[dict[str, Any]] = []
    window_rows: list[dict[str, Any]] = []
    validation_score_rows: list[dict[str, Any]] = []
    prediction_score_rows: list[dict[str, Any]] = []
    selected_feature_rows: list[dict[str, Any]] = []

    study = optuna.create_study(direction=direction, sampler=optuna.samplers.TPESampler(seed=int(args.seed)))

    def objective(trial: Any) -> float:
        config_updates = suggest_trial_config(trial, args)
        policy = policy_for_trial(base_policy, config_updates)
        model_updates = model_updates_for_trial(args, config_updates)
        trial_number = int(trial.number)
        print(
            "[rpf-cls-optuna] trial_start "
            f"trial={trial_number} windows={len(tuning_windows)} model={args.model_family} "
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
                ema_regime_filter=None,
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
            if status != "ok" and str(args.objective_metric) not in {"stable_prediction_quality", "stable_signal_quality"}:
                payload = dict(payload)
                payload["objective_value"] = 1e9 if direction == "minimize" else -1e9
            row = trial_row(args, policy, payload, model_updates, trial_number, status)
            row.update(policy_trial_fields(policy))
            row.update(flatten_objective_components(payload.get("objective_components", {})))
            row.update({"optuna_params_json": json.dumps(dict(trial.params), sort_keys=True)})
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
            return float(row["objective_value"])
        except Exception as exc:
            value = 1e9 if direction == "minimize" else -1e9
            row = {
                "trial_number": trial_number,
                "status": "error",
                "objective_metric": str(args.objective_metric),
                "trial_objective_split": str(args.trial_objective_split),
                "objective_direction": direction,
                "objective_value": value,
                "error": str(exc),
                "feature_ablation": str(args.feature_ablation),
                "feature_policy": base_policy.policy,
                "decision_policy": str(args.decision_policy),
                "model_family": str(args.model_family),
                "sequence_panel_path": None if args.sequence_panel_path is None else str(args.sequence_panel_path),
                **model_updates,
                **policy_trial_fields(policy),
                "optuna_params_json": json.dumps(dict(trial.params), sort_keys=True),
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
            print(f"[rpf-cls-optuna] trial_error trial={trial_number} error={exc}", flush=True)
            return float(value)

    study.optimize(objective, n_trials=int(args.n_trials), show_progress_bar=False)
    best = best_trial(trials)
    write_trials(run_root / "trials.parquet", trials)
    write_rows_parquet(run_root / "window_metrics.parquet", window_rows)
    write_rows_parquet(run_root / "validation_scores.parquet", validation_score_rows)
    write_rows_parquet(run_root / "prediction_scores.parquet", prediction_score_rows)
    write_rows_parquet(run_root / "selected_features.parquet", selected_feature_rows)
    write_json(
        run_root / "study_summary.json",
        {
            "objective_metric": str(args.objective_metric),
            "objective_direction": direction,
            "best_value": study.best_value if study.trials else None,
            "best_params": study.best_params if study.trials else {},
            "trial_count": len(study.trials),
        },
    )
    write_json(run_root / "best_config.json", best_config_payload(args, asset, root, target_col, positive_rule, base_policy, best))
    write_markdown(
        run_root / "report.md",
        title="RPF Binary Classification Optuna Walk-Forward",
        sections={
            "Target": {"target_col": target_col, "positive_rule": positive_rule},
            "Run": {
                "asset": asset,
                "root": root,
                "tuning_windows": len(tuning_windows),
                "holdout_windows": len(holdout_windows),
                "objective_metric": str(args.objective_metric),
                "objective_direction": direction,
                "feature_ablation": str(args.feature_ablation),
                "feature_policy": base_policy.policy,
                "decision_policy": str(args.decision_policy),
            },
            "Best": best or {},
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
            ema_regime_filter=None,
        )
    print(f"[rpf-cls-optuna] done run={run_root}", flush=True)
    return 0


def suggest_trial_config(trial: Any, args: argparse.Namespace) -> dict[str, Any]:
    config = {
        "iterations": trial.suggest_categorical("iterations", parse_ints(args.iterations_choices)),
        "depth": trial.suggest_categorical("depth", parse_ints(args.depth_choices)),
        "learning_rate": trial.suggest_categorical("learning_rate", parse_floats(args.learning_rate_choices)),
        "l2_leaf_reg": trial.suggest_categorical("l2_leaf_reg", parse_floats(args.l2_leaf_reg_choices)),
        "early_stopping_rounds": trial.suggest_categorical(
            "early_stopping_rounds",
            parse_ints(args.early_stopping_rounds_choices),
        ),
        "od_wait": trial.suggest_categorical("od_wait", parse_ints(args.od_wait_choices)),
    }
    if str(args.feature_policy) == ELASTICNET_LOGISTIC_V1:
        config.update(
            {
                "elasticnet_c": trial.suggest_categorical("elasticnet_c", parse_floats(args.elasticnet_c_choices)),
                "elasticnet_l1_ratio": trial.suggest_categorical(
                    "elasticnet_l1_ratio",
                    parse_floats(args.elasticnet_l1_ratio_choices),
                ),
                "elasticnet_max_features": trial.suggest_categorical(
                    "elasticnet_max_features",
                    parse_ints(args.elasticnet_max_features_choices),
                ),
                "elasticnet_coef_epsilon": trial.suggest_categorical(
                    "elasticnet_coef_epsilon",
                    elasticnet_coef_epsilon_choices(args),
                ),
                "elasticnet_prefilter_features": trial.suggest_categorical(
                    "elasticnet_prefilter_features",
                    elasticnet_prefilter_feature_choices(args),
                ),
            }
        )
    return config


def elasticnet_coef_epsilon_choices(args: argparse.Namespace) -> list[float]:
    values = str(args.elasticnet_coef_epsilon_choices or "").strip()
    return parse_floats(values) if values else [float(args.elasticnet_coef_epsilon)]


def elasticnet_prefilter_feature_choices(args: argparse.Namespace) -> list[int]:
    values = str(args.elasticnet_prefilter_features_choices or "").strip()
    return parse_ints(values) if values else [int(args.elasticnet_prefilter_features)]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Optuna over chronological RPF binary classification.")
    parser.add_argument("--asset", default=None)
    parser.add_argument("--root", default=None)
    parser.add_argument("--target-col", default=TARGET_BINARY_UP_2X_DOWN)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--base-run", type=Path, required=True)
    parser.add_argument("--feature-ablation", default="all")
    parser.add_argument("--feature-policy", choices=[ALL_MANIFEST_FEATURES, ELASTICNET_LOGISTIC_V1], default=ELASTICNET_LOGISTIC_V1)
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
    parser.add_argument("--output-dir", type=Path, default=OPTUNA_OUTPUT_ROOT)
    parser.add_argument("--n-steps", type=int, default=50)
    parser.add_argument("--holdout-steps", type=int, default=20)
    parser.add_argument("--n-trials", type=int, default=24)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--log-every-windows", type=int, default=1)
    parser.add_argument("--task-type", choices=["CPU", "GPU"], default="CPU")
    parser.add_argument("--thread-count", type=int, default=-1)
    parser.add_argument("--iterations-choices", default="200,400,800")
    parser.add_argument("--depth-choices", default="2,3,4")
    parser.add_argument("--learning-rate-choices", default="0.005,0.01,0.02")
    parser.add_argument("--l2-leaf-reg-choices", default="10,30,100")
    parser.add_argument("--early-stopping-rounds-choices", default="50,100")
    parser.add_argument("--od-wait-choices", default="50,100")
    parser.add_argument("--elasticnet-c-choices", default="0.03,0.1,0.3")
    parser.add_argument("--elasticnet-l1-ratio-choices", default="0.25,0.5,0.75")
    parser.add_argument("--elasticnet-max-features-choices", default="80,160")
    parser.add_argument("--elasticnet-min-selected-features", type=int, default=20)
    parser.add_argument("--elasticnet-max-iter", type=int, default=1000)
    parser.add_argument("--elasticnet-tol", type=float, default=0.001)
    parser.add_argument("--elasticnet-class-weight", choices=["balanced", "none"], default="balanced")
    parser.add_argument("--elasticnet-coef-epsilon", type=float, default=1e-8)
    parser.add_argument("--elasticnet-coef-epsilon-choices", default=None)
    parser.add_argument("--elasticnet-prefilter-features", type=int, default=160)
    parser.add_argument("--elasticnet-prefilter-features-choices", default="160,320")
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
        default="stable_prediction_quality",
    )
    parser.add_argument("--trial-objective-split", choices=["validation", "prediction"], default="prediction")
    parser.add_argument("--threshold-mode", choices=["fixed", "validation_sweep"], default="validation_sweep")
    parser.add_argument("--decision-threshold", type=float, default=0.5)
    parser.add_argument(
        "--decision-policy",
        choices=DECISION_POLICIES,
        default=DECISION_POLICY_CAUSAL_SIGNAL_BUDGET,
        help=(
            "How thresholded probabilities become signals. threshold_only is live-safe; "
            "causal_signal_budget is live-safe if rows are timestamp ordered; "
            "batch_topk_offline is diagnostic only because it ranks the full prediction batch."
        ),
    )
    parser.add_argument("--threshold-grid", default="0.45,0.50,0.55,0.60,0.65,0.70")
    parser.add_argument(
        "--max-signals-grid",
        default="0,5,10,20,40,80",
        help="Comma-separated per-batch signal caps considered with threshold selection; 0 means unlimited.",
    )
    parser.add_argument("--fp-cost", type=float, default=5.0)
    parser.add_argument("--fn-cost", type=float, default=1.0)
    parser.add_argument("--tp-reward", type=float, default=0.0)
    parser.add_argument("--fbeta-beta", type=float, default=0.5)
    parser.add_argument("--min-validation-recall", type=float, default=0.0)
    parser.add_argument("--min-validation-precision", type=float, default=0.0)
    parser.add_argument("--min-validation-predicted-positive-rate", type=float, default=0.0)
    parser.add_argument("--max-validation-false-positive-rate", type=float, default=1.0)
    parser.add_argument("--min-threshold-pass-rate", type=float, default=0.50)
    parser.add_argument("--max-prediction-zero-positive-window-rate", type=float, default=0.50)
    parser.add_argument("--max-prediction-all-positive-window-rate", type=float, default=0.10)
    parser.add_argument("--prediction-all-positive-rate-threshold", type=float, default=0.95)
    parser.add_argument("--max-prediction-high-fpr-window-rate", type=float, default=0.35)
    parser.add_argument("--max-prediction-window-false-positive-rate", type=float, default=0.30)
    parser.add_argument("--max-prediction-high-cost-window-rate", type=float, default=0.35)
    parser.add_argument("--max-prediction-window-decision-cost-per-row", type=float, default=1.0)
    parser.add_argument("--prediction-high-target-positive-rate-threshold", type=float, default=0.70)
    parser.add_argument("--min-prediction-high-target-window-recall", type=float, default=0.05)
    parser.add_argument("--min-prediction-high-target-window-signal-rate", type=float, default=0.01)
    parser.add_argument("--max-prediction-missed-high-target-window-rate", type=float, default=0.50)
    parser.add_argument("--prediction-low-target-positive-rate-threshold", type=float, default=0.35)
    parser.add_argument("--max-prediction-low-target-all-positive-window-rate", type=float, default=0.10)
    args = parser.parse_args()

    # Compatibility fields consumed by shared classifier helpers. The Optuna
    # command is intentionally chronological-only; EMA paths are abandoned for
    # active modeling.
    args.max_configs = int(args.n_trials)
    args.window_mode = CHRONOLOGICAL_RECENT
    args.ema_regime_timeframe = "1h"
    args.ema_regime_dominance_rate = 0.80
    args.ema_regime_train_batches = 120
    args.ema_regime_val_batches = 20
    args.ema_regime_candidate_lookback_batches = 2000
    args.ema_regime_label_maturity_embargo_batches = 1
    args.ema_regime_buffer = 0.0
    args.ema_regime_inventory_chunk_batches = 32
    args.ema_regime_prediction_min_rate = 0.0
    args.ema_regime_prediction_search_windows = 250
    args.ema_regime_filter_rows = True
    return args


if __name__ == "__main__":
    raise SystemExit(main())
