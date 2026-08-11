from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from copy import copy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl

_REPO_BOOTSTRAP_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_BOOTSTRAP_ROOT))

try:  # noqa: E402
    import optuna
except Exception:  # pragma: no cover
    optuna = None  # type: ignore[assignment]

from scripts.analysis.htf_stage1_regression_walkforward import (  # noqa: E402
    FEATURE_POLICY_FULL,
    FEATURE_POLICY_TARGET_SPECIFIC_V1,
    FEATURE_POLICY_TARGET_SPECIFIC_V2,
    FEATURE_SOURCE_MODES,
    FEATURE_SOURCE_REGRESSION_ONLY,
    REGRESSION_FEATURE_SET,
    CatBoostModelConfig,
    FeaturePolicyConfig,
    FeatureSourceConfig,
    build_catboost_params,
    plan_regression_steps,
    regression_steps_to_frame,
    regression_path_feature_root,
    resolve_or_build_dataset,
    run_regression_walkforward,
)
from scripts.analysis.materialize_stage1_regression_targets import all_target_cols  # noqa: E402
from scripts.htf_backtest.catboost.stage1_multiasset_dataset import (  # noqa: E402
    MULTIASSET_MERGED_ROOT,
    STAGE1_MULTIASSET_ROOT_LAYOUTS,
    parse_stage1_target_assets,
)
from scripts.project_paths import ensure_project_root_on_path  # noqa: E402


PROJECT_ROOT = ensure_project_root_on_path(Path(__file__))
OUTPUT_ROOT = PROJECT_ROOT / "test_output" / "stage1_regression_optuna"
WALKFORWARD_OUTPUT_ROOT = PROJECT_ROOT / "test_output" / "stage1_regression_walkforward"
STAGE_READINESS = "readiness"
STAGE_GEOMETRY = "geometry"
STAGE_FEATURE_POLICY = "feature_policy"
STAGE_CORE_MODEL = "core_model"
STAGE_SAMPLING = "sampling"
STAGE_TREE_POLICY = "tree_policy"
STAGE_CONFIRMATION = "confirmation"
OPTIMIZATION_STAGES = (
    STAGE_READINESS,
    STAGE_GEOMETRY,
    STAGE_FEATURE_POLICY,
    STAGE_CORE_MODEL,
    STAGE_SAMPLING,
    STAGE_TREE_POLICY,
    STAGE_CONFIRMATION,
)
LOCK_FILE_BY_STAGE = {
    STAGE_GEOMETRY: "locked_window_config.json",
    STAGE_FEATURE_POLICY: "locked_feature_policy_config.json",
    STAGE_CORE_MODEL: "locked_core_model_config.json",
    STAGE_SAMPLING: "locked_regularized_model_config.json",
    STAGE_TREE_POLICY: "locked_advanced_model_config.json",
    STAGE_CONFIRMATION: "final_confirmation_config.json",
}


def default_effective_config(args: argparse.Namespace | None = None) -> dict[str, Any]:
    """Return the conservative staged optimization defaults."""

    return {
        "window": {
            "lookback_batches": 120,
            "val_batches": 20,
            "embargo_batches": 0,
        },
        "feature": {
            "feature_source_mode": FEATURE_SOURCE_REGRESSION_ONLY,
            "feature_policy": FEATURE_POLICY_TARGET_SPECIFIC_V2,
            "max_features": 300,
            "min_abs_spearman": 0.02,
            "min_selected_features": 20,
            "dedupe_corr_threshold": 0.995,
            "clip_quantiles": [0.001, 0.999],
            "stability_segments": 5,
            "tail_quantile": 0.80,
        },
        "model": {
            "iterations": 200,
            "depth": 4,
            "learning_rate": 0.03,
            "l2_leaf_reg": 10.0,
            "loss_function": "RMSE",
            "eval_metric": "RMSE",
            "early_stopping_rounds": 50,
            "od_type": "Iter",
            "od_wait": None,
            "random_strength": None,
            "bootstrap_type": None,
            "bagging_temperature": None,
            "subsample": None,
            "mvs_reg": None,
            "border_count": None,
            "grow_policy": None,
            "min_data_in_leaf": None,
            "max_leaves": None,
            "leaf_estimation_method": None,
            "leaf_estimation_iterations": None,
            "boosting_type": None,
            "has_time": True,
            "gpu_ram_part": None,
        },
        "objective": {
            "objective_metric": "validation_composite",
        },
    }


def validation_objective_score(metrics: dict[str, Any], args: argparse.Namespace) -> float:
    """Return a validation-only score. Higher is better."""

    spearman = _metric(metrics, "spearman")
    pearson = _metric(metrics, "pearson")
    r2 = _metric(metrics, "r2")
    rmse = _metric(metrics, "rmse")
    mae = _metric(metrics, "mae")
    tail_rmse = _metric(metrics, "tail_rmse")
    coverage = _metric(metrics, "p95_coverage_ratio")
    bias = abs(_metric(metrics, "bias"))

    if str(args.objective_metric) == "validation_spearman":
        return spearman
    if str(args.objective_metric) == "validation_rmse_negative":
        return -rmse

    coverage_penalty = abs(math.log(max(coverage, 1e-9))) if coverage > 0 else 20.0
    return float(
        float(args.weight_spearman) * spearman
        + float(args.weight_pearson) * pearson
        + float(args.weight_r2) * r2
        - float(args.weight_rmse) * rmse
        - float(args.weight_mae) * mae
        - float(args.weight_tail_rmse) * tail_rmse
        - float(args.weight_p95_coverage) * coverage_penalty
        - float(args.weight_bias) * bias
    )


def suggest_trial_config(
    trial: Any,
    args: argparse.Namespace,
    base_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Suggest one staged, leakage-safe walk-forward configuration."""

    base = _normalize_effective_config(base_config or default_effective_config(args))
    stage = str(getattr(args, "optimization_stage", STAGE_FEATURE_POLICY))
    if stage == STAGE_READINESS:
        return base
    if stage == STAGE_GEOMETRY:
        _suggest_geometry(trial, args, base)
    elif stage == STAGE_FEATURE_POLICY:
        _suggest_feature_policy(trial, args, base)
    elif stage == STAGE_CORE_MODEL:
        _suggest_core_model(trial, args, base)
    elif stage == STAGE_SAMPLING:
        _suggest_sampling_model(trial, args, base)
    elif stage == STAGE_TREE_POLICY:
        _suggest_tree_policy_model(trial, args, base)
    elif stage == STAGE_CONFIRMATION:
        return base
    else:
        raise ValueError(f"Unsupported optimization stage: {stage}")
    _validate_effective_config(base, task_type=str(getattr(args, "task_type", "CPU")))
    return base


def main() -> int:
    args = _parse_args()
    if optuna is None:  # pragma: no cover
        raise RuntimeError("Optuna is required. Install the project environment with optuna>=3.5.")

    run_root = Path(args.output_dir) / _run_slug()
    run_root.mkdir(parents=True, exist_ok=True)
    event_log_path = run_root / "optimizer_events.jsonl"
    base_config = _load_base_config(args)
    target_assets = parse_stage1_target_assets(args.target_assets)
    roots = tuple(args.roots)
    target_cols = _parse_target_cols(args.stage1_target_cols)
    _validate_feature_source_modes(args.feature_source_modes)
    _optuna_progress(
        f"[optuna] start stage={args.optimization_stage} assets={','.join(target_assets)} "
        f"roots={','.join(roots)} targets={len(target_cols)} trials={args.n_trials} "
        f"output={run_root}"
    )
    _append_event(
        event_log_path,
        "optimizer_start",
        optimization_stage=args.optimization_stage,
        target_assets=target_assets,
        roots=list(roots),
        target_cols=list(target_cols),
        n_trials=int(args.n_trials),
        n_steps=int(args.n_steps),
        output_dir=str(run_root),
    )

    if args.plan_only:
        total_studies = len(target_assets) * len(roots) * len(target_cols)
        print(
            f"Plan only: stage={args.optimization_stage} studies={total_studies} "
            f"trials_per_study={args.n_trials} output={run_root}"
        )
        return 0

    if args.optimization_stage == STAGE_READINESS:
        payload = _write_readiness_lock(run_root, args, target_assets, roots, target_cols, base_config)
        _append_event(
            event_log_path,
            "readiness_done",
            path=payload["path"],
            frozen_step_index_path=payload.get("frozen_step_index_path"),
            dataset_count=len(payload.get("datasets", [])),
        )
        print(f"Readiness lock: {payload['path']}")
        return 0

    storage = str(args.storage or f"sqlite:///{(run_root / 'optuna_study.db').resolve()}")
    study_rows: list[dict[str, Any]] = []
    for target_asset in target_assets:
        for root_key in roots:
            for target_col in target_cols:
                target_args = copy(args)
                target_args.stage1_target_col = target_col
                dataset = resolve_or_build_dataset(
                    target_args,
                    target_asset=target_asset,
                    root_key=root_key,
                )
                study_slug = _study_slug(target_asset, dataset.root_id, target_col)
                study_dir = run_root / study_slug
                study_dir.mkdir(parents=True, exist_ok=True)
                study_name = str(args.study_name or f"rpf_{args.optimization_stage}_{study_slug}")
                sampler = _build_sampler(args)
                pruner = _build_pruner(args)
                study = optuna.create_study(
                    study_name=study_name,
                    storage=storage,
                    direction="maximize",
                    sampler=sampler,
                    pruner=pruner,
                    load_if_exists=bool(args.resume),
                )
                _optuna_progress(
                    f"[optuna] study stage={args.optimization_stage} name={study.study_name} "
                    f"target={target_col} root={root_key}"
                )
                _append_event(
                    event_log_path,
                    "study_start",
                    study_name=study.study_name,
                    study_dir=str(study_dir),
                    target_asset=target_asset,
                    root=root_key,
                    target_col=target_col,
                )

                def objective(trial: Any) -> float:
                    config = suggest_trial_config(trial, args, base_config)
                    run_suffix = _trial_suffix(args.optimization_stage, study_slug, trial.number, config)
                    _optuna_progress(
                        f"[optuna] trial_start stage={args.optimization_stage} trial={trial.number} "
                        f"fs={config['feature']['feature_source_mode']} "
                        f"lb={config['window']['lookback_batches']} val={config['window']['val_batches']} "
                        f"mf={config['feature']['max_features']} it={config['model']['iterations']} "
                        f"depth={config['model']['depth']} lr={config['model']['learning_rate']}"
                    )
                    _append_event(
                        event_log_path,
                        "trial_start",
                        study_name=study.study_name,
                        trial_number=int(trial.number),
                        optimization_stage=args.optimization_stage,
                        effective_config=config,
                    )
                    try:
                        payload = run_regression_walkforward(
                            dataset=dataset,
                            n_steps=int(args.n_steps),
                            lookback_batches=int(config["window"]["lookback_batches"]),
                            val_batches=int(config["window"]["val_batches"]),
                            embargo_batches=int(config["window"]["embargo_batches"]),
                            iterations=int(config["model"]["iterations"]),
                            depth=int(config["model"]["depth"]),
                            learning_rate=float(config["model"]["learning_rate"]),
                            task_type=str(args.task_type),
                            thread_count=int(args.thread_count),
                            l2_leaf_reg=float(config["model"]["l2_leaf_reg"]),
                            catboost_model_config=_catboost_config_from_effective_config(config),
                            feature_policy_config=_feature_policy_config_from_effective_config(config),
                            feature_source_config=FeatureSourceConfig(
                                mode=str(config["feature"]["feature_source_mode"]),
                                regression_feature_set=str(args.regression_feature_set),
                                data_root=PROJECT_ROOT / "data",
                            ),
                            frozen_step_index_path=args.frozen_step_index_path,
                            step_callback=_trial_step_callback(trial, args),
                            log_every_steps=int(args.log_every_steps),
                            run_suffix=run_suffix,
                            output_root=Path(args.walkforward_output_dir),
                        )
                        validation_metrics = payload["validation_metrics"]
                        prediction_metrics = payload["prediction_metrics"]
                        score = validation_objective_score(validation_metrics, args)
                        if not math.isfinite(score):
                            raise optuna.TrialPruned("Non-finite validation objective")
                        trial.set_user_attr("effective_config", config)
                        trial.set_user_attr("run_id", payload["run_id"])
                        trial.set_user_attr("summary_path", payload["outputs"]["summary"])
                        trial.set_user_attr("n_completed_steps", payload["n_completed_steps"])
                        trial.set_user_attr("optimization_stage", args.optimization_stage)
                        trial.set_user_attr("optimization_decision_basis", payload["optimization_decision_basis"])
                        for key, value in validation_metrics.items():
                            trial.set_user_attr(f"validation_{key}", value)
                        for key, value in prediction_metrics.items():
                            trial.set_user_attr(f"prediction_{key}", value)
                        _optuna_progress(
                            f"[optuna] trial_done trial={trial.number} score={_fmt(score)} "
                            f"val_spearman={_fmt(validation_metrics.get('spearman'))} "
                            f"val_rmse={_fmt(validation_metrics.get('rmse'))} "
                            f"pred_spearman={_fmt(prediction_metrics.get('spearman'))}"
                        )
                        _append_event(
                            event_log_path,
                            "trial_done",
                            study_name=study.study_name,
                            trial_number=int(trial.number),
                            value=score,
                            run_id=payload["run_id"],
                            summary_path=payload["outputs"]["summary"],
                            validation_metrics=validation_metrics,
                            prediction_metrics=prediction_metrics,
                        )
                        return score
                    except Exception as exc:
                        _append_event(
                            event_log_path,
                            "trial_error",
                            study_name=study.study_name,
                            trial_number=int(trial.number),
                            error=str(exc),
                        )
                        _optuna_progress(f"[optuna] trial_error trial={trial.number} error={exc}")
                        raise

                def callback(study_obj: Any, _: Any) -> None:
                    _write_study_outputs(study_dir, study_obj, args)

                study.optimize(
                    objective,
                    n_trials=int(args.n_trials),
                    timeout=args.timeout,
                    gc_after_trial=True,
                    callbacks=[callback],
                    catch=(ValueError, RuntimeError),
                )
                _write_study_outputs(study_dir, study, args)
                best = _best_trial_or_none(study)
                best_config = _best_effective_config(best, base_config)
                best_config_path = _write_best_config(study_dir, args.optimization_stage, best_config)
                study_rows.append(
                    {
                        "target_asset": target_asset,
                        "root": root_key,
                        "target_col": target_col,
                        "study_name": study.study_name,
                        "study_dir": str(study_dir),
                        "best_trial": int(best.number) if best else None,
                        "best_value": float(best.value) if best and best.value is not None else None,
                        "best_config_path": str(best_config_path),
                    }
                )
                _append_event(
                    event_log_path,
                    "study_done",
                    study_name=study.study_name,
                    study_dir=str(study_dir),
                    best_trial=int(best.number) if best else None,
                    best_value=float(best.value) if best and best.value is not None else None,
                    best_config_path=str(best_config_path),
                )
    _write_run_index(run_root, study_rows)
    _append_event(event_log_path, "optimizer_done", studies=study_rows)
    _optuna_progress(f"[optuna] done output={run_root}")
    print(f"Optuna output: {run_root}")
    return 0


def _suggest_geometry(trial: Any, args: argparse.Namespace, config: dict[str, Any]) -> None:
    lookback = trial.suggest_categorical("lookback_batches", _parse_int_list(args.lookback_choices))
    val_choices = [value for value in _parse_int_list(args.val_choices) if value < int(lookback)]
    if not val_choices:
        raise optuna.TrialPruned(f"No val_batches choice is smaller than lookback={lookback}")
    config["window"]["lookback_batches"] = int(lookback)
    config["window"]["val_batches"] = int(trial.suggest_categorical("val_batches", val_choices))
    config["window"]["embargo_batches"] = int(
        trial.suggest_categorical("embargo_batches", _parse_int_list(args.embargo_choices))
    )


def _suggest_feature_policy(trial: Any, args: argparse.Namespace, config: dict[str, Any]) -> None:
    config["feature"]["feature_source_mode"] = trial.suggest_categorical(
        "feature_source_mode",
        _parse_str_list(args.feature_source_modes),
    )
    config["feature"]["max_features"] = int(
        trial.suggest_categorical("max_features", _parse_int_list(args.max_features_choices))
    )
    config["feature"]["min_abs_spearman"] = float(
        trial.suggest_categorical("min_abs_spearman", _parse_float_list(args.min_abs_spearman_choices))
    )
    config["feature"]["min_selected_features"] = int(
        trial.suggest_categorical("min_selected_features", _parse_int_list(args.min_selected_features_choices))
    )
    config["feature"]["dedupe_corr_threshold"] = float(
        trial.suggest_categorical("dedupe_corr_threshold", _parse_float_list(args.dedupe_corr_choices))
    )
    config["feature"]["clip_quantiles"] = list(_parse_clip_quantiles(
        trial.suggest_categorical("clip_quantiles", _parse_clip_quantile_choices(args.clip_quantiles_choices))
    ))
    config["feature"]["stability_segments"] = int(
        trial.suggest_categorical("stability_segments", _parse_int_list(args.stability_segments_choices))
    )
    config["feature"]["tail_quantile"] = float(
        trial.suggest_categorical("tail_quantile", _parse_float_list(args.tail_quantile_choices))
    )


def _suggest_core_model(trial: Any, args: argparse.Namespace, config: dict[str, Any]) -> None:
    config["model"]["iterations"] = int(
        trial.suggest_categorical("iterations", _parse_int_list(args.iterations_choices))
    )
    config["model"]["depth"] = int(trial.suggest_categorical("depth", _parse_int_list(args.depth_choices)))
    config["model"]["learning_rate"] = float(
        trial.suggest_categorical("learning_rate", _parse_float_list(args.learning_rate_choices))
    )
    config["model"]["l2_leaf_reg"] = float(
        trial.suggest_categorical("l2_leaf_reg", _parse_float_list(args.l2_leaf_reg_choices))
    )
    config["model"]["early_stopping_rounds"] = int(
        trial.suggest_categorical("early_stopping_rounds", _parse_int_list(args.early_stopping_rounds_choices))
    )
    config["model"]["od_wait"] = int(trial.suggest_categorical("od_wait", _parse_int_list(args.od_wait_choices)))


def _suggest_sampling_model(trial: Any, args: argparse.Namespace, config: dict[str, Any]) -> None:
    model = config["model"]
    model["random_strength"] = float(
        trial.suggest_categorical("random_strength", _parse_float_list(args.random_strength_choices))
    )
    model["border_count"] = int(trial.suggest_categorical("border_count", _parse_int_list(args.border_count_choices)))
    bootstrap = trial.suggest_categorical("bootstrap_type", _parse_str_list(args.bootstrap_type_choices))
    model["bootstrap_type"] = None if bootstrap == "None" else bootstrap
    model["bagging_temperature"] = None
    model["subsample"] = None
    model["mvs_reg"] = None
    if model["bootstrap_type"] == "Bayesian":
        model["bagging_temperature"] = float(
            trial.suggest_categorical("bagging_temperature", _parse_float_list(args.bagging_temperature_choices))
        )
    elif model["bootstrap_type"] in {"Bernoulli", "Poisson"}:
        model["subsample"] = float(trial.suggest_categorical("subsample", _parse_float_list(args.subsample_choices)))
    elif model["bootstrap_type"] == "MVS":
        model["subsample"] = float(trial.suggest_categorical("subsample", _parse_float_list(args.subsample_choices)))
        if str(args.task_type).upper() != "GPU":
            model["mvs_reg"] = float(trial.suggest_categorical("mvs_reg", _parse_float_list(args.mvs_reg_choices)))


def _suggest_tree_policy_model(trial: Any, args: argparse.Namespace, config: dict[str, Any]) -> None:
    model = config["model"]
    grow_policy = trial.suggest_categorical("grow_policy", _parse_str_list(args.grow_policy_choices))
    model["grow_policy"] = None if grow_policy == "None" else grow_policy
    model["leaf_estimation_method"] = trial.suggest_categorical(
        "leaf_estimation_method",
        _parse_str_list(args.leaf_estimation_method_choices),
    )
    model["leaf_estimation_iterations"] = int(
        trial.suggest_categorical("leaf_estimation_iterations", _parse_int_list(args.leaf_estimation_iterations_choices))
    )
    model["min_data_in_leaf"] = None
    model["max_leaves"] = None
    if model["grow_policy"] in {"Depthwise", "Lossguide"}:
        model["min_data_in_leaf"] = int(
            trial.suggest_categorical("min_data_in_leaf", _parse_int_list(args.min_data_in_leaf_choices))
        )
    if model["grow_policy"] == "Lossguide":
        model["max_leaves"] = int(trial.suggest_categorical("max_leaves", _parse_int_list(args.max_leaves_choices)))


def _write_readiness_lock(
    run_root: Path,
    args: argparse.Namespace,
    target_assets: list[str],
    roots: tuple[str, ...],
    target_cols: tuple[str, ...],
    base_config: dict[str, Any],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    frozen_step_path = Path(args.frozen_step_index_path) if args.frozen_step_index_path else run_root / "frozen_step_index.parquet"
    first_steps: list[Any] | None = None
    for target_asset in target_assets:
        for root_key in roots:
            for target_col in target_cols:
                target_args = copy(args)
                target_args.stage1_target_col = target_col
                dataset = resolve_or_build_dataset(target_args, target_asset=target_asset, root_key=root_key)
                batch_index = pl.read_parquet(dataset.batch_index_path)
                key_dupes = int(
                    batch_index.group_by("batch_id")
                    .len()
                    .filter(pl.col("len") > 1)
                    .height
                )
                steps = plan_regression_steps(
                    batch_index,
                    n_steps=int(args.n_steps),
                    lookback_batches=int(base_config["window"]["lookback_batches"]),
                    val_batches=int(base_config["window"]["val_batches"]),
                    embargo_batches=int(base_config["window"]["embargo_batches"]),
                )
                if first_steps is None:
                    first_steps = steps
                rpf_root = regression_path_feature_root(
                    dataset,
                    FeatureSourceConfig(
                        mode="regression_only",
                        regression_feature_set=str(args.regression_feature_set),
                        data_root=PROJECT_ROOT / "data",
                    ),
                )
                rows.append(
                    {
                        "target_asset": target_asset,
                        "root": root_key,
                        "root_id": dataset.root_id,
                        "target_col": target_col,
                        "features_dir": str(dataset.features_dir),
                        "labels_dir": str(dataset.labels_dir),
                        "batch_index_path": str(dataset.batch_index_path),
                        "batch_index_rows": int(batch_index.height),
                        "batch_id_duplicate_count": key_dupes,
                        "valid_batch_count": int(batch_index.filter(pl.col("valid_row_count") > 0).height),
                        "planned_step_count": int(len(steps)),
                        "first_pred_batch_id": int(steps[0].pred_batch_id) if steps else None,
                        "last_pred_batch_id": int(steps[-1].pred_batch_id) if steps else None,
                        "rpf_root": str(rpf_root),
                        "rpf_root_exists": bool(rpf_root.exists()),
                        "rpf_manifest_exists": bool((rpf_root / "manifest.json").exists()),
                    }
                )
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "optimization_stage": STAGE_READINESS,
        "base_config": base_config,
        "frozen_step_index_path": str(frozen_step_path),
        "datasets": rows,
    }
    path = run_root / "optimization_readiness.json"
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    pl.DataFrame(rows).write_parquet(run_root / "optimization_readiness.parquet")
    frozen_step_path.parent.mkdir(parents=True, exist_ok=True)
    regression_steps_to_frame(first_steps or []).write_parquet(frozen_step_path)
    _write_stage_summary(run_root / "stage_summary.md", args, rows, None)
    payload["path"] = str(path)
    return payload


def _trial_step_callback(trial: Any, args: argparse.Namespace) -> Any | None:
    if str(args.pruner) == "none":
        return None

    def callback(completed_step_count: int, validation_metrics: dict[str, Any], _: Any) -> None:
        score = validation_objective_score(validation_metrics, args)
        trial.report(score, step=int(completed_step_count))
        if trial.should_prune():
            raise optuna.TrialPruned(f"Pruned after {completed_step_count} walk-forward step(s)")

    return callback


def _write_study_outputs(study_dir: Path, study: Any, args: argparse.Namespace) -> None:
    rows = [_trial_row(trial) for trial in study.trials]
    (study_dir / "trials.json").write_text(json.dumps(rows, indent=2, default=str) + "\n")
    if rows:
        frame = pl.DataFrame(rows)
        frame.write_parquet(study_dir / "trials.parquet")
        frame.write_csv(study_dir / "trials.csv")
    _write_study_markdown(study_dir / "summary.md", study, rows, args)
    _write_stage_summary(study_dir / "stage_summary.md", args, rows, _best_trial_or_none(study))


def _trial_row(trial: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "number": int(trial.number),
        "state": str(trial.state.name),
        "value": float(trial.value) if trial.value is not None else None,
    }
    row.update({f"param_{key}": _table_safe(value) for key, value in trial.params.items()})
    row.update({f"attr_{key}": _table_safe(value) for key, value in trial.user_attrs.items()})
    return row


def _write_study_markdown(path: Path, study: Any, rows: list[dict[str, Any]], args: argparse.Namespace) -> None:
    complete = [row for row in rows if row.get("state") == "COMPLETE"]
    best = _best_trial_or_none(study) if complete else None
    lines = [
        "# Stage-1 Regression Optuna Study",
        "",
        f"Stage: `{args.optimization_stage}`",
        f"Study: `{study.study_name}`",
        f"Objective metric: `{args.objective_metric}`",
        "Decision basis: `validation_metrics` only",
        "",
        f"Trials: `{len(rows)}`",
        f"Completed: `{len(complete)}`",
    ]
    if best is not None:
        lines.extend(
            [
                "",
                "## Best Trial",
                "",
                f"- trial: `{best.number}`",
                f"- value: `{best.value:.6g}`",
                f"- summary: `{best.user_attrs.get('summary_path')}`",
                "",
                "## Best Parameters",
                "",
            ]
        )
        for key, value in sorted(best.params.items()):
            lines.append(f"- `{key}`: `{value}`")
        lines.extend(["", "## Best Validation Metrics", ""])
        for key, value in sorted(best.user_attrs.items()):
            if key.startswith("validation_"):
                lines.append(f"- `{key}`: `{_fmt(value)}`")
    lines.append("")
    path.write_text("\n".join(lines) + "\n")


def _write_stage_summary(path: Path, args: argparse.Namespace, rows: list[dict[str, Any]], best: Any | None) -> None:
    lines = [
        "# Stage-1 Regression Staged Optimization Summary",
        "",
        f"Stage: `{args.optimization_stage}`",
        f"Decision basis: `validation_metrics`",
        "",
        f"Rows/trials recorded: `{len(rows)}`",
    ]
    if best is not None:
        lines.extend(
            [
                f"Best trial: `{best.number}`",
                f"Best value: `{_fmt(best.value)}`",
                "",
                "Best config path is written beside this file.",
            ]
        )
    lines.append("")
    path.write_text("\n".join(lines) + "\n")


def _best_trial_or_none(study: Any) -> Any | None:
    try:
        return study.best_trial
    except ValueError:
        return None


def _best_effective_config(best: Any | None, fallback: dict[str, Any]) -> dict[str, Any]:
    if best is None:
        return _normalize_effective_config(fallback)
    value = best.user_attrs.get("effective_config")
    if isinstance(value, dict):
        return _normalize_effective_config(value)
    return _normalize_effective_config(fallback)


def _write_best_config(study_dir: Path, stage: str, config: dict[str, Any]) -> Path:
    filename = LOCK_FILE_BY_STAGE.get(stage, "best_config.json")
    path = study_dir / filename
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "optimization_stage": stage,
        "effective_config": _normalize_effective_config(config),
    }
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    (study_dir / "best_config.json").write_text(json.dumps(payload, indent=2, default=str) + "\n")
    return path


def _write_run_index(run_root: Path, rows: list[dict[str, Any]]) -> None:
    (run_root / "studies.json").write_text(json.dumps(rows, indent=2, default=str) + "\n")
    if rows:
        frame = pl.DataFrame(rows)
        frame.write_parquet(run_root / "studies.parquet")
        frame.write_csv(run_root / "studies.csv")


def _build_sampler(args: argparse.Namespace) -> Any:
    if str(args.sampler) == "random":
        return optuna.samplers.RandomSampler(seed=int(args.seed))
    return optuna.samplers.TPESampler(
        seed=int(args.seed),
        multivariate=True,
        n_startup_trials=int(args.n_startup_trials),
    )


def _build_pruner(args: argparse.Namespace) -> Any:
    if str(args.pruner) == "none":
        return optuna.pruners.NopPruner()
    if str(args.pruner) == "hyperband":
        return optuna.pruners.HyperbandPruner()
    return optuna.pruners.MedianPruner(n_startup_trials=int(args.n_startup_trials))


def _trial_suffix(stage: str, study_slug: str, number: int, config: dict[str, Any]) -> str:
    lr = str(config["model"]["learning_rate"]).replace(".", "p")
    ms = str(config["feature"]["min_abs_spearman"]).replace(".", "p")
    dd = str(config["feature"]["dedupe_corr_threshold"]).replace(".", "p")
    payload = json.dumps(
        {
            "stage": stage,
            "study_slug": study_slug,
            "number": int(number),
            "config": config,
        },
        sort_keys=True,
        default=str,
    )
    digest = hashlib.blake2s(payload.encode("utf-8"), digest_size=5).hexdigest()
    return (
        f"opt_{_stage_slug(stage)}_{digest}_t{int(number):04d}"
        f"_fs_{config['feature']['feature_source_mode']}"
        f"_lb{config['window']['lookback_batches']}_val{config['window']['val_batches']}"
        f"_mf{config['feature']['max_features']}_ms{ms}_dedupe{dd}"
        f"_it{config['model']['iterations']}_d{config['model']['depth']}_lr{lr}"
    )


def _stage_slug(stage: str) -> str:
    value = _slug(stage)
    aliases = {
        STAGE_GEOMETRY: "geo",
        STAGE_FEATURE_POLICY: "feat",
        STAGE_CORE_MODEL: "core",
        STAGE_SAMPLING: "samp",
        STAGE_TREE_POLICY: "tree",
        STAGE_CONFIRMATION: "conf",
        STAGE_READINESS: "ready",
    }
    return aliases.get(value, value[:8])


def _study_slug(target_asset: str, root_id: str, target_col: str) -> str:
    return f"{_slug(target_asset)}_{_slug(root_id)}_{_target_slug(target_col)}"


def _target_slug(target_col: str) -> str:
    value = str(target_col)
    if value.startswith("target_"):
        value = value[len("target_") :]
    return _slug(value)


def _slug(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in str(value)).strip("_")


def _metric(metrics: dict[str, Any], key: str) -> float:
    value = metrics.get(key)
    if value is None:
        return 0.0
    value = float(value)
    if not math.isfinite(value):
        return 0.0
    return value


def _load_base_config(args: argparse.Namespace) -> dict[str, Any]:
    config = default_effective_config(args)
    if args.base_config_json is None:
        return config
    path = Path(args.base_config_json)
    payload = json.loads(path.read_text())
    effective = payload.get("effective_config", payload)
    if not isinstance(effective, dict):
        raise ValueError(f"Base config does not contain an object: {path}")
    _deep_update(config, effective)
    return _normalize_effective_config(config)


def _deep_update(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = value


def _normalize_effective_config(config: dict[str, Any]) -> dict[str, Any]:
    base = default_effective_config(None)
    _deep_update(base, config)
    base["feature"]["clip_quantiles"] = list(base["feature"]["clip_quantiles"])
    return base


def _validate_effective_config(config: dict[str, Any], *, task_type: str) -> None:
    if int(config["window"]["val_batches"]) >= int(config["window"]["lookback_batches"]):
        raise ValueError("val_batches must be smaller than lookback_batches")
    if str(config["feature"]["feature_source_mode"]) not in FEATURE_SOURCE_MODES:
        raise ValueError(f"Unsupported feature_source_mode: {config['feature']['feature_source_mode']}")
    build_catboost_params(_catboost_config_from_effective_config(config), task_type=task_type, thread_count=-1)


def _feature_policy_config_from_effective_config(config: dict[str, Any]) -> FeaturePolicyConfig:
    feature = config["feature"]
    return FeaturePolicyConfig(
        policy=str(feature["feature_policy"]),
        max_features=int(feature["max_features"]),
        min_abs_spearman=float(feature["min_abs_spearman"]),
        dedupe_corr_threshold=float(feature["dedupe_corr_threshold"]),
        clip_quantiles=(float(feature["clip_quantiles"][0]), float(feature["clip_quantiles"][1])),
        min_selected_features=int(feature["min_selected_features"]),
        stability_segments=int(feature["stability_segments"]),
        tail_quantile=float(feature["tail_quantile"]),
    )


def _catboost_config_from_effective_config(config: dict[str, Any]) -> CatBoostModelConfig:
    model = config["model"]
    return CatBoostModelConfig(
        iterations=int(model["iterations"]),
        depth=int(model["depth"]),
        learning_rate=float(model["learning_rate"]),
        l2_leaf_reg=float(model["l2_leaf_reg"]),
        loss_function=str(model["loss_function"]),
        eval_metric=str(model["eval_metric"]),
        early_stopping_rounds=int(model["early_stopping_rounds"]),
        od_type=model.get("od_type"),
        od_wait=model.get("od_wait"),
        random_strength=model.get("random_strength"),
        bootstrap_type=model.get("bootstrap_type"),
        bagging_temperature=model.get("bagging_temperature"),
        subsample=model.get("subsample"),
        mvs_reg=model.get("mvs_reg"),
        border_count=model.get("border_count"),
        grow_policy=model.get("grow_policy"),
        min_data_in_leaf=model.get("min_data_in_leaf"),
        max_leaves=model.get("max_leaves"),
        leaf_estimation_method=model.get("leaf_estimation_method"),
        leaf_estimation_iterations=model.get("leaf_estimation_iterations"),
        boosting_type=model.get("boosting_type"),
        has_time=bool(model.get("has_time", True)),
        gpu_ram_part=model.get("gpu_ram_part"),
    )


def _parse_target_cols(raw: str) -> tuple[str, ...]:
    allowed = set(all_target_cols())
    values = tuple(_parse_str_list(raw))
    unknown = [value for value in values if value not in allowed]
    if unknown:
        raise ValueError(f"Unknown regression target columns: {unknown}")
    return values


def _validate_feature_source_modes(raw: str) -> None:
    unknown = [value for value in _parse_str_list(raw) if value not in FEATURE_SOURCE_MODES]
    if unknown:
        raise ValueError(f"Unsupported feature source mode(s): {unknown}")


def _parse_str_list(raw: str) -> list[str]:
    return [part.strip() for part in str(raw).split(",") if part.strip()]


def _parse_int_list(raw: str) -> list[int]:
    return [int(value) for value in _parse_str_list(raw)]


def _parse_float_list(raw: str) -> list[float]:
    return [float(value) for value in _parse_str_list(raw)]


def _parse_clip_quantiles(raw: str) -> tuple[float, float]:
    values = _parse_float_list(raw)
    if len(values) != 2:
        raise ValueError("--clip-quantiles must be two comma-separated floats")
    low, high = values
    if not (0.0 <= low < high <= 1.0):
        raise ValueError("--clip-quantiles must satisfy 0 <= low < high <= 1")
    return low, high


def _parse_clip_quantile_choices(raw: str) -> list[str]:
    value = str(raw).strip()
    if not value:
        return []
    if ";" in value:
        return [part.strip() for part in value.split(";") if part.strip()]
    if "|" in value:
        return [part.strip() for part in value.split("|") if part.strip()]
    _parse_clip_quantiles(value)
    return [value]


def _run_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    value = float(value)
    if not math.isfinite(value):
        return "-"
    return f"{value:.6g}"


def _append_event(path: Path, event: str, **fields: Any) -> None:
    payload = {
        "event": event,
        "ts": datetime.now(timezone.utc).isoformat(),
        **fields,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(payload, default=str) + "\n")


def _optuna_progress(message: str) -> None:
    print(message, flush=True)


def _table_safe(value: Any) -> Any:
    if isinstance(value, dict | list | tuple):
        return json.dumps(value, sort_keys=True, default=str)
    return value


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Staged Optuna optimization wrapper for Stage-1 regression walk-forward."
    )
    parser.add_argument("--build-merged-dataset", action="store_true")
    parser.add_argument("--target-assets", default="BTCUSDT")
    parser.add_argument("--context-assets", default=None)
    parser.add_argument("--roots", nargs="*", choices=sorted(STAGE1_MULTIASSET_ROOT_LAYOUTS), default=["8h/B"])
    parser.add_argument(
        "--stage1-target-cols",
        default="target_reg_distance_up_extreme_hvol_v2",
        help="Comma-separated regression target columns.",
    )
    parser.add_argument("--multiasset-dataset-dir", type=Path, default=PROJECT_ROOT / "data" / MULTIASSET_MERGED_ROOT)
    parser.add_argument("--merged-batch-min", type=int, default=None)
    parser.add_argument("--merged-batch-max", type=int, default=None)
    parser.add_argument("--merged-batch-limit", type=int, default=None)
    parser.add_argument("--optimization-stage", choices=OPTIMIZATION_STAGES, default=STAGE_FEATURE_POLICY)
    parser.add_argument("--base-config-json", type=Path, default=None)
    parser.add_argument("--write-best-config", action="store_true", default=True)
    parser.add_argument("--frozen-step-index-path", type=Path, default=None)
    parser.add_argument("--feature-source-modes", default="htf_only,regression_only,htf_plus_regression")
    parser.add_argument("--regression-feature-set", default=REGRESSION_FEATURE_SET)
    parser.add_argument(
        "--feature-policy",
        choices=[FEATURE_POLICY_FULL, FEATURE_POLICY_TARGET_SPECIFIC_V1, FEATURE_POLICY_TARGET_SPECIFIC_V2],
        default=FEATURE_POLICY_TARGET_SPECIFIC_V2,
    )
    parser.add_argument("--lookback-choices", default="80,120,180")
    parser.add_argument("--val-choices", default="10,20")
    parser.add_argument("--embargo-choices", default="0")
    parser.add_argument("--max-features-choices", default="100,150,300")
    parser.add_argument("--min-abs-spearman-choices", default="0.02,0.03,0.05")
    parser.add_argument("--min-selected-features-choices", default="20")
    parser.add_argument("--dedupe-corr-choices", default="0.98,0.995")
    parser.add_argument("--clip-quantiles-choices", default="0.001,0.999")
    parser.add_argument("--stability-segments-choices", default="5")
    parser.add_argument("--tail-quantile-choices", default="0.8")
    parser.add_argument("--iterations-choices", default="200,300")
    parser.add_argument("--depth-choices", default="4,6")
    parser.add_argument("--learning-rate-choices", default="0.03,0.05")
    parser.add_argument("--l2-leaf-reg-choices", default="3,10,30")
    parser.add_argument("--early-stopping-rounds-choices", default="50")
    parser.add_argument("--od-wait-choices", default="50")
    parser.add_argument("--random-strength-choices", default="1,5,10")
    parser.add_argument("--bootstrap-type-choices", default="None,Bayesian,Bernoulli")
    parser.add_argument("--bagging-temperature-choices", default="0.25,0.5,1.0")
    parser.add_argument("--subsample-choices", default="0.66,0.8,0.9")
    parser.add_argument("--mvs-reg-choices", default="0.1,1.0")
    parser.add_argument("--border-count-choices", default="64,128,254")
    parser.add_argument("--grow-policy-choices", default="None,SymmetricTree,Depthwise,Lossguide")
    parser.add_argument("--min-data-in-leaf-choices", default="20,50,100")
    parser.add_argument("--max-leaves-choices", default="31,63")
    parser.add_argument("--leaf-estimation-method-choices", default="Newton,Gradient")
    parser.add_argument("--leaf-estimation-iterations-choices", default="1,3,5")
    parser.add_argument("--n-steps", type=int, default=20)
    parser.add_argument("--task-type", choices=["CPU", "GPU"], default="CPU")
    parser.add_argument("--thread-count", type=int, default=-1)
    parser.add_argument("--n-trials", type=int, default=24)
    parser.add_argument("--timeout", type=int, default=None)
    parser.add_argument("--log-every-steps", type=int, default=1)
    parser.add_argument("--sampler", choices=["tpe", "random"], default="tpe")
    parser.add_argument("--pruner", choices=["none", "median", "hyperband"], default="none")
    parser.add_argument("--n-startup-trials", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--study-name", default=None)
    parser.add_argument("--storage", default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--objective-metric",
        choices=["validation_composite", "validation_spearman", "validation_rmse_negative"],
        default="validation_composite",
    )
    parser.add_argument("--weight-spearman", type=float, default=1.0)
    parser.add_argument("--weight-pearson", type=float, default=0.15)
    parser.add_argument("--weight-r2", type=float, default=0.20)
    parser.add_argument("--weight-rmse", type=float, default=0.25)
    parser.add_argument("--weight-mae", type=float, default=0.0)
    parser.add_argument("--weight-tail-rmse", type=float, default=0.10)
    parser.add_argument("--weight-p95-coverage", type=float, default=0.20)
    parser.add_argument("--weight-bias", type=float, default=0.05)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--walkforward-output-dir", type=Path, default=WALKFORWARD_OUTPUT_ROOT)
    parser.add_argument("--plan-only", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
