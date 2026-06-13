from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

_REPO_BOOTSTRAP_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_BOOTSTRAP_ROOT))

from scripts.analysis.materialize_stage1_regression_targets import (  # noqa: E402
    UP_EXTREME_COL,
    all_target_cols,
)
from scripts.feature_engineering.htf_asset_registry import normalize_htf_asset_id  # noqa: E402
from scripts.htf_backtest.catboost.stage1_multiasset_dataset import (  # noqa: E402
    FEATURE_TARGET_COL,
    MULTIASSET_MERGED_ROOT,
    STAGE1_MULTIASSET_ROOT_LAYOUTS,
    build_context_set_hash,
    build_multiasset_stage1_dataset,
    build_stage1_dataset_variant_id,
    parse_stage1_context_assets,
    parse_stage1_target_assets,
)
from scripts.htf_backtest.catboost.utils import (  # noqa: E402
    get_feature_columns,
    load_batches_by_ids,
)
from scripts.project_paths import ensure_project_root_on_path  # noqa: E402


PROJECT_ROOT = ensure_project_root_on_path(Path(__file__))
OUTPUT_ROOT = PROJECT_ROOT / "test_output" / "stage1_regression_walkforward"
FEATURE_POLICY_FULL = "full"
FEATURE_POLICY_TARGET_SPECIFIC_V1 = "target_specific_v1"
FEATURE_POLICY_TARGET_SPECIFIC_V2 = "target_specific_v2"
FEATURE_POLICIES = (
    FEATURE_POLICY_FULL,
    FEATURE_POLICY_TARGET_SPECIFIC_V1,
    FEATURE_POLICY_TARGET_SPECIFIC_V2,
)
FEATURE_SOURCE_HTF_ONLY = "htf_only"
FEATURE_SOURCE_REGRESSION_ONLY = "regression_only"
FEATURE_SOURCE_HTF_PLUS_REGRESSION = "htf_plus_regression"
FEATURE_SOURCE_MODES = (
    FEATURE_SOURCE_HTF_ONLY,
    FEATURE_SOURCE_REGRESSION_ONLY,
    FEATURE_SOURCE_HTF_PLUS_REGRESSION,
)
REGRESSION_FEATURE_SET = "regression_path_features_v1"
RAW_OHLCV_BASE_NAMES = {"open", "high", "low", "close", "volume"}
LEAKAGE_NAME_RE = re.compile(
    r"(^|__)target_|(^|__)tb_|label_window|future|diagnostic",
    re.IGNORECASE,
)
REGRESSION_FEATURE_METADATA_PREFIXES = ("rpf_align_",)


@dataclass(frozen=True)
class RegressionDataset:
    target_asset: str
    context_assets: tuple[str, ...]
    context_hash: str
    root_key: str
    root_id: str
    target_col: str
    feature_target_col: str
    features_dir: Path
    labels_dir: Path
    manifest_path: Path
    batch_index_path: Path


@dataclass(frozen=True)
class RegressionStep:
    step_idx: int
    pred_pos: int
    pred_batch_id: int
    train_batch_ids: tuple[int, ...]
    val_batch_ids: tuple[int, ...]


@dataclass(frozen=True)
class FeaturePolicyConfig:
    policy: str = FEATURE_POLICY_FULL
    max_features: int = 300
    min_abs_spearman: float = 0.01
    dedupe_corr_threshold: float = 0.995
    clip_quantiles: tuple[float, float] = (0.001, 0.999)
    min_selected_features: int = 20
    stability_segments: int = 5
    tail_quantile: float = 0.80


@dataclass(frozen=True)
class FeatureSourceConfig:
    """Control which feature roots are visible to the regression walk-forward."""

    mode: str = FEATURE_SOURCE_HTF_ONLY
    regression_feature_set: str = REGRESSION_FEATURE_SET
    data_root: Path = PROJECT_ROOT / "data"


@dataclass(frozen=True)
class CatBoostModelConfig:
    """CatBoost parameters that are safe to record and replay for one WF run."""

    iterations: int = 200
    depth: int = 6
    learning_rate: float = 0.05
    l2_leaf_reg: float = 3.0
    loss_function: str = "RMSE"
    eval_metric: str = "RMSE"
    early_stopping_rounds: int = 50
    od_type: str = "Iter"
    od_wait: int | None = None
    random_strength: float | None = None
    bootstrap_type: str | None = None
    bagging_temperature: float | None = None
    subsample: float | None = None
    mvs_reg: float | None = None
    border_count: int | None = None
    grow_policy: str | None = None
    min_data_in_leaf: int | None = None
    max_leaves: int | None = None
    leaf_estimation_method: str | None = None
    leaf_estimation_iterations: int | None = None
    boosting_type: str | None = None
    has_time: bool = True
    gpu_ram_part: float | None = None


@dataclass(frozen=True)
class FeaturePolicyResult:
    selected_features: tuple[str, ...]
    clip_bounds: dict[str, tuple[float, float]]
    detail: pl.DataFrame


def build_regression_run_id(
    dataset: RegressionDataset,
    *,
    feature_source_config: FeatureSourceConfig | None = None,
    run_suffix: str | None = None,
) -> str:
    slug = _target_slug(dataset.target_col)
    feature_source_config = feature_source_config or FeatureSourceConfig()
    run_id = (
        f"stage1_regression_{dataset.target_asset.lower()}_"
        f"{dataset.root_id}_ctx_{dataset.context_hash}_{slug}_live"
    )
    if feature_source_config.mode != FEATURE_SOURCE_HTF_ONLY:
        run_id = f"{run_id}_feat_{_slug(feature_source_config.mode)}"
    if run_suffix:
        run_id = f"{run_id}_{_slug(run_suffix)}"
    return run_id


def run_regression_walkforward(
    *,
    dataset: RegressionDataset,
    n_steps: int,
    lookback_batches: int,
    val_batches: int,
    embargo_batches: int,
    iterations: int,
    depth: int,
    learning_rate: float,
    l2_leaf_reg: float = 3.0,
    task_type: str,
    thread_count: int,
    catboost_model_config: CatBoostModelConfig | None = None,
    feature_policy_config: FeaturePolicyConfig | None = None,
    feature_source_config: FeatureSourceConfig | None = None,
    frozen_step_index_path: Path | None = None,
    step_callback: Any | None = None,
    log_every_steps: int = 1,
    run_suffix: str | None = None,
    output_root: Path = OUTPUT_ROOT,
) -> dict[str, Any]:
    """Run a compact sparse-aware CatBoostRegressor walk-forward evaluation."""
    feature_policy_config = feature_policy_config or FeaturePolicyConfig()
    feature_source_config = feature_source_config or FeatureSourceConfig()
    catboost_model_config = catboost_model_config or CatBoostModelConfig(
        iterations=int(iterations),
        depth=int(depth),
        learning_rate=float(learning_rate),
        l2_leaf_reg=float(l2_leaf_reg),
    )
    _validate_feature_source_config(feature_source_config)
    batch_index = _load_batch_index(dataset.batch_index_path, target_col=dataset.target_col)
    if frozen_step_index_path is not None:
        steps = load_regression_steps_from_index(Path(frozen_step_index_path))
    else:
        steps = plan_regression_steps(
            batch_index,
            n_steps=n_steps,
            lookback_batches=lookback_batches,
            val_batches=val_batches,
            embargo_batches=embargo_batches,
        )
    if not steps:
        raise ValueError(
            "No eligible regression walk-forward steps. Reduce lookback/val/embargo "
            "or build more merged batches."
        )

    run_id = build_regression_run_id(
        dataset,
        feature_source_config=feature_source_config,
        run_suffix=run_suffix,
    )
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    event_log_path = run_dir / "run_events.jsonl"
    _append_event(
        event_log_path,
        "run_start",
        run_id=run_id,
        target_asset=dataset.target_asset,
        root=dataset.root_key,
        target_col=dataset.target_col,
        requested_steps=int(n_steps),
        planned_steps=int(len(steps)),
        lookback_batches=int(lookback_batches),
        val_batches=int(val_batches),
        embargo_batches=int(embargo_batches),
        feature_source_mode=feature_source_config.mode,
        feature_policy=feature_policy_config.policy,
        frozen_step_index_path=str(frozen_step_index_path) if frozen_step_index_path else None,
    )
    _progress(
        f"[wf] start run={run_id} target={dataset.target_col} steps={len(steps)} "
        f"source={feature_source_config.mode} policy={feature_policy_config.policy}"
    )

    step_rows: list[dict[str, Any]] = []
    pred_frames: list[pl.DataFrame] = []
    val_frames: list[pl.DataFrame] = []
    val_true_chunks: list[np.ndarray] = []
    val_pred_chunks: list[np.ndarray] = []
    feature_policy_frames: list[pl.DataFrame] = []
    selected_feature_counter: Counter[str] = Counter()
    selected_feature_counts: list[int] = []
    feature_cols_ref: list[str] | None = None
    total_steps = len(steps)
    for planned_idx, step in enumerate(steps, start=1):
        should_log_step = _should_log_step(planned_idx, total_steps, log_every_steps)
        if should_log_step:
            _progress(
                f"[wf] step {planned_idx}/{total_steps} pred_batch={step.pred_batch_id} "
                f"train={len(step.train_batch_ids)} val={len(step.val_batch_ids)}"
            )
        _append_event(
            event_log_path,
            "step_start",
            run_id=run_id,
            planned_step_index=int(planned_idx),
            planned_step_count=int(total_steps),
            pred_batch_id=int(step.pred_batch_id),
            pred_pos=int(step.pred_pos),
            train_batch_count=int(len(step.train_batch_ids)),
            val_batch_count=int(len(step.val_batch_ids)),
        )
        train_df = load_regression_feature_frame(
            dataset,
            step.train_batch_ids,
            feature_source_config=feature_source_config,
        )
        val_df = load_regression_feature_frame(
            dataset,
            step.val_batch_ids,
            feature_source_config=feature_source_config,
        )
        pred_df = load_regression_feature_frame(
            dataset,
            (step.pred_batch_id,),
            feature_source_config=feature_source_config,
        )

        base_feature_cols = get_feature_columns(train_df, target_col=dataset.target_col)
        if feature_policy_config.policy in {
            FEATURE_POLICY_TARGET_SPECIFIC_V1,
            FEATURE_POLICY_TARGET_SPECIFIC_V2,
        }:
            policy_result = select_target_specific_features(
                train_df,
                dataset.target_col,
                base_feature_cols,
                config=feature_policy_config,
            )
            feature_cols = list(policy_result.selected_features)
            selected_feature_counter.update(feature_cols)
            selected_feature_counts.append(len(feature_cols))
            feature_policy_frames.append(
                policy_result.detail.with_columns(
                    [
                        pl.lit(int(step.step_idx)).alias("step_idx"),
                        pl.lit(int(step.pred_batch_id)).alias("pred_batch_id"),
                    ]
                )
            )
            clip_bounds = policy_result.clip_bounds
        else:
            feature_cols = base_feature_cols
            selected_feature_counter.update(feature_cols)
            selected_feature_counts.append(len(feature_cols))
            clip_bounds = None

        X_train, y_train, feature_cols, _ = prepare_regression_frame(
            train_df,
            dataset.target_col,
            feature_cols=feature_cols,
            clip_bounds=clip_bounds,
        )
        X_val, y_val, _, val_meta = prepare_regression_frame(
            val_df,
            dataset.target_col,
            feature_cols=feature_cols,
            clip_bounds=clip_bounds,
        )
        X_pred, y_pred_true, _, pred_meta = prepare_regression_frame(
            pred_df,
            dataset.target_col,
            feature_cols=feature_cols,
            clip_bounds=clip_bounds,
        )
        if X_train.size == 0 or X_val.size == 0 or X_pred.size == 0:
            _append_event(
                event_log_path,
                "step_skipped_empty_frame",
                run_id=run_id,
                planned_step_index=int(planned_idx),
                pred_batch_id=int(step.pred_batch_id),
                train_size=int(X_train.size),
                val_size=int(X_val.size),
                pred_size=int(X_pred.size),
            )
            continue
        feature_cols_ref = feature_cols if feature_cols_ref is None else feature_cols_ref
        model = fit_catboost_regressor(
            X_train,
            y_train,
            X_val,
            y_val,
            model_config=catboost_model_config,
            task_type=task_type,
            thread_count=thread_count,
        )
        model_diagnostics = catboost_model_diagnostics(model)
        y_val_pred = np.asarray(model.predict(X_val), dtype=float)
        y_pred = np.asarray(model.predict(X_pred), dtype=float)
        validation_metrics = regression_metrics(y_val, y_val_pred)
        prediction_metrics = regression_metrics(y_pred_true, y_pred)
        if should_log_step:
            _progress(
                f"[wf] done {planned_idx}/{total_steps} pred_batch={step.pred_batch_id} "
                f"features={len(feature_cols)} "
                f"val_spearman={_fmt(validation_metrics.get('spearman'))} "
                f"val_rmse={_fmt(validation_metrics.get('rmse'))} "
                f"pred_spearman={_fmt(prediction_metrics.get('spearman'))} "
                f"pred_std={_fmt(prediction_metrics.get('pred_std'))} "
                f"pred_unique={prediction_metrics.get('pred_unique')} "
                f"best_iter={model_diagnostics.get('model_best_iteration')}"
            )
        _append_event(
            event_log_path,
            "step_done",
            run_id=run_id,
            planned_step_index=int(planned_idx),
            pred_batch_id=int(step.pred_batch_id),
            selected_feature_count=int(len(feature_cols)),
            **model_diagnostics,
            validation_spearman=validation_metrics.get("spearman"),
            validation_rmse=validation_metrics.get("rmse"),
            validation_p95_coverage_ratio=validation_metrics.get("p95_coverage_ratio"),
            validation_pred_std=validation_metrics.get("pred_std"),
            validation_spearman_null_reason=validation_metrics.get("spearman_null_reason"),
            prediction_spearman=prediction_metrics.get("spearman"),
            prediction_rmse=prediction_metrics.get("rmse"),
            prediction_p95_coverage_ratio=prediction_metrics.get("p95_coverage_ratio"),
            prediction_pred_std=prediction_metrics.get("pred_std"),
            prediction_pred_unique=prediction_metrics.get("pred_unique"),
            prediction_spearman_null_reason=prediction_metrics.get("spearman_null_reason"),
        )
        val_true_chunks.append(y_val)
        val_pred_chunks.append(y_val_pred)
        step_rows.append(
            {
                "step_idx": int(step.step_idx),
                "pred_pos": int(step.pred_pos),
                "pred_batch_id": int(step.pred_batch_id),
                "train_batch_count": int(len(step.train_batch_ids)),
                "val_batch_count": int(len(step.val_batch_ids)),
                "train_start_batch_id": int(step.train_batch_ids[0]),
                "train_end_batch_id": int(step.train_batch_ids[-1]),
                "val_start_batch_id": int(step.val_batch_ids[0]),
                "val_end_batch_id": int(step.val_batch_ids[-1]),
                "selected_feature_count": int(len(feature_cols)),
                **model_diagnostics,
                **prediction_metrics,
                **_prefix_metrics(prediction_metrics, "prediction"),
                **_prefix_metrics(validation_metrics, "validation"),
            }
        )
        val_frames.append(
            val_meta.with_columns(
                [
                    pl.Series("y_true", y_val),
                    pl.Series("y_pred", y_val_pred),
                    pl.lit(int(step.step_idx)).alias("step_idx"),
                    pl.lit(int(step.pred_pos)).alias("pred_pos"),
                    pl.lit(int(step.pred_batch_id)).alias("pred_batch_id"),
                    (pl.Series("y_pred", y_val_pred) - pl.Series("y_true", y_val)).alias("error"),
                ]
            )
        )
        if step_callback is not None:
            cumulative_validation = regression_metrics(
                np.concatenate(val_true_chunks),
                np.concatenate(val_pred_chunks),
            )
            step_callback(int(len(step_rows)), cumulative_validation, step)
        pred_frames.append(
            pred_meta.with_columns(
                [
                    pl.Series("y_true", y_pred_true),
                    pl.Series("y_pred", y_pred),
                    pl.lit(int(step.step_idx)).alias("step_idx"),
                    pl.lit(int(step.pred_pos)).alias("pred_pos"),
                    pl.lit(int(step.pred_batch_id)).alias("pred_batch_id"),
                    (pl.Series("y_pred", y_pred) - pl.Series("y_true", y_pred_true)).alias("error"),
                ]
            )
        )

    if not pred_frames:
        raise ValueError("No regression steps produced predictions")

    predictions = pl.concat(pred_frames, how="diagonal_relaxed").sort(["step_idx", "timestamp"])
    validation_predictions = pl.concat(val_frames, how="diagonal_relaxed").sort(["step_idx", "timestamp"])
    step_metrics = pl.DataFrame(step_rows).sort("step_idx")
    feature_policy_detail = (
        pl.concat(feature_policy_frames, how="diagonal_relaxed")
        if feature_policy_frames
        else pl.DataFrame()
    )
    selected_frequency = _selected_feature_frequency_frame(selected_feature_counter, len(step_rows))
    prediction_aggregate = regression_metrics(
        predictions["y_true"].to_numpy(),
        predictions["y_pred"].to_numpy(),
    )
    validation_aggregate = regression_metrics(
        validation_predictions["y_true"].to_numpy(),
        validation_predictions["y_pred"].to_numpy(),
    )
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "target_asset": dataset.target_asset,
        "context_assets": list(dataset.context_assets),
        "context_hash": dataset.context_hash,
        "root": dataset.root_key,
        "root_id": dataset.root_id,
        "target_col": dataset.target_col,
        "feature_target_col": dataset.feature_target_col,
        "features_dir": str(dataset.features_dir),
        "labels_dir": str(dataset.labels_dir),
        "manifest_path": str(dataset.manifest_path),
        "batch_index_path": str(dataset.batch_index_path),
        "frozen_step_index_path": str(frozen_step_index_path) if frozen_step_index_path else None,
        "feature_source": {
            "mode": feature_source_config.mode,
            "regression_feature_set": feature_source_config.regression_feature_set,
            "data_root": str(feature_source_config.data_root),
            "target_regression_feature_root": str(
                regression_path_feature_root(dataset, feature_source_config)
            )
            if feature_source_config.mode != FEATURE_SOURCE_HTF_ONLY
            else None,
        },
        "n_requested_steps": int(n_steps),
        "n_completed_steps": int(step_metrics.height),
        "lookback_batches": int(lookback_batches),
        "val_batches": int(val_batches),
        "embargo_batches": int(embargo_batches),
        "feature_count": int(len(feature_cols_ref or [])),
        "model": {
            "type": "CatBoostRegressor",
            **_catboost_model_config_payload(catboost_model_config),
            "task_type": str(task_type),
        },
        "feature_policy": {
            "policy": feature_policy_config.policy,
            "max_features": int(feature_policy_config.max_features),
            "min_abs_spearman": float(feature_policy_config.min_abs_spearman),
            "dedupe_corr_threshold": float(feature_policy_config.dedupe_corr_threshold),
            "clip_quantiles": list(feature_policy_config.clip_quantiles),
            "min_selected_features": int(feature_policy_config.min_selected_features),
            "stability_segments": int(feature_policy_config.stability_segments),
            "tail_quantile": float(feature_policy_config.tail_quantile),
            "selected_feature_count_min": int(min(selected_feature_counts)) if selected_feature_counts else 0,
            "selected_feature_count_max": int(max(selected_feature_counts)) if selected_feature_counts else 0,
            "selected_feature_count_mean": _safe_float(np.mean(selected_feature_counts)) if selected_feature_counts else None,
        },
        "aggregate_metrics": prediction_aggregate,
        "prediction_metrics": prediction_aggregate,
        "validation_metrics": validation_aggregate,
        "selection_metrics": validation_aggregate,
        "optimization_decision_basis": "validation_metrics",
        "outputs": {
            "run_events": str(event_log_path),
            "predictions": str(run_dir / "predictions.parquet"),
            "validation_predictions": str(run_dir / "validation_predictions.parquet"),
            "step_metrics": str(run_dir / "step_metrics.parquet"),
            "feature_policy_detail": str(run_dir / "feature_policy_detail.parquet") if not feature_policy_detail.is_empty() else None,
            "selected_feature_frequency": str(run_dir / "selected_feature_frequency.parquet"),
            "feature_policy_summary": str(run_dir / "feature_policy_summary.md"),
            "summary": str(run_dir / "summary.json"),
        },
    }
    predictions.write_parquet(run_dir / "predictions.parquet")
    validation_predictions.write_parquet(run_dir / "validation_predictions.parquet")
    step_metrics.write_parquet(run_dir / "step_metrics.parquet")
    if not feature_policy_detail.is_empty():
        feature_policy_detail.write_parquet(run_dir / "feature_policy_detail.parquet")
    selected_frequency.write_parquet(run_dir / "selected_feature_frequency.parquet")
    (run_dir / "summary.json").write_text(json.dumps(payload, indent=2, default=str))
    _write_markdown_report(run_dir / "summary.md", payload, step_metrics)
    _write_feature_policy_summary(run_dir / "feature_policy_summary.md", payload, selected_frequency)
    _append_event(
        event_log_path,
        "run_done",
        run_id=run_id,
        completed_steps=int(step_metrics.height),
        prediction_spearman=prediction_aggregate.get("spearman"),
        prediction_rmse=prediction_aggregate.get("rmse"),
        validation_spearman=validation_aggregate.get("spearman"),
        validation_rmse=validation_aggregate.get("rmse"),
        summary_path=str(run_dir / "summary.json"),
    )
    _progress(
        f"[wf] done run={run_id} completed={step_metrics.height}/{len(steps)} "
        f"val_spearman={_fmt(validation_aggregate.get('spearman'))} "
        f"pred_spearman={_fmt(prediction_aggregate.get('spearman'))}"
    )
    return payload


def load_regression_feature_frame(
    dataset: RegressionDataset,
    batch_ids: list[int] | tuple[int, ...] | np.ndarray,
    *,
    feature_source_config: FeatureSourceConfig,
) -> pl.DataFrame:
    """Load Stage-1 rows and optionally join target regression-path features.

    The merged HTF dataset remains the row authority. Regression-path features are
    joined by exact `timestamp,batch_id` for the target asset only in v1.
    """

    base = load_batches_by_ids(
        dataset.features_dir,
        dataset.labels_dir,
        "1m",
        batch_ids,
        target_col=dataset.target_col,
        feature_target_col=dataset.feature_target_col,
    )
    if feature_source_config.mode == FEATURE_SOURCE_HTF_ONLY:
        return base

    regression_features = load_target_regression_path_features(
        dataset,
        batch_ids,
        feature_source_config=feature_source_config,
    )
    regression_feature_cols = [
        col for col in regression_features.columns if col not in {"timestamp", "batch_id"}
    ]
    if not regression_feature_cols:
        raise ValueError("Regression feature source has no model-facing columns")

    if feature_source_config.mode == FEATURE_SOURCE_REGRESSION_ONLY:
        keep_cols = ["timestamp", "batch_id"]
        for col in (dataset.feature_target_col, dataset.target_col):
            if col in base.columns and col not in keep_cols:
                keep_cols.append(col)
        joined = base.select(keep_cols).join(
            regression_features,
            on=["timestamp", "batch_id"],
            how="left",
        )
    elif feature_source_config.mode == FEATURE_SOURCE_HTF_PLUS_REGRESSION:
        joined = base.join(
            regression_features,
            on=["timestamp", "batch_id"],
            how="left",
        )
    else:
        raise ValueError(f"Unsupported feature source mode: {feature_source_config.mode}")

    null_count = int(
        joined.select(pl.sum_horizontal([pl.col(col).is_null() for col in regression_feature_cols]))
        .to_series()
        .sum()
    )
    if null_count:
        raise ValueError(
            f"Regression feature join produced {null_count} null feature values "
            f"for {dataset.target_asset} {dataset.root_key}. "
            "Materialize regression_path_features_v1 for this asset/root first."
        )
    return joined


def load_target_regression_path_features(
    dataset: RegressionDataset,
    batch_ids: list[int] | tuple[int, ...] | np.ndarray,
    *,
    feature_source_config: FeatureSourceConfig,
) -> pl.DataFrame:
    """Load target-asset regression-path features for explicit batch ids."""

    root = regression_path_feature_root(dataset, feature_source_config)
    if not root.exists():
        raise FileNotFoundError(f"Regression feature root not found: {root}")

    manifest_feature_cols = _regression_path_manifest_feature_columns(root)
    frames: list[pl.DataFrame] = []
    seen: set[int] = set()
    for raw_batch_id in batch_ids:
        batch_id = int(raw_batch_id)
        if batch_id in seen:
            continue
        seen.add(batch_id)
        path = root / f"batch_{batch_id:04d}.parquet"
        if not path.exists():
            raise FileNotFoundError(f"Regression feature batch not found: {path}")
        df = pl.read_parquet(path)
        feature_cols = _regression_path_model_feature_columns(
            df,
            manifest_feature_cols=manifest_feature_cols,
            path=path,
        )
        rename = {col: f"T_{dataset.target_asset}__{col}" for col in feature_cols}
        frames.append(df.select(["timestamp", "batch_id", *feature_cols]).rename(rename))
    if not frames:
        raise ValueError(f"No regression feature batches requested: {list(batch_ids)}")
    return pl.concat(frames, how="diagonal_relaxed").sort(["batch_id", "timestamp"])


def _regression_path_manifest_feature_columns(root: Path) -> tuple[str, ...] | None:
    """Return the model-facing RPF feature contract from manifest.json if present."""

    path = root / "manifest.json"
    if not path.exists():
        return None
    manifest = json.loads(path.read_text())
    raw = manifest.get("feature_columns")
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"Regression feature manifest has no feature_columns list: {path}")
    cols = tuple(str(col) for col in raw)
    bad = [col for col in cols if not col.startswith("rpf_")]
    if bad:
        raise ValueError(f"Regression feature manifest contains non-rpf feature columns: {bad[:5]}")
    return cols


def _regression_path_model_feature_columns(
    df: pl.DataFrame,
    *,
    manifest_feature_cols: tuple[str, ...] | None,
    path: Path,
) -> list[str]:
    """Return model-facing RPF columns and exclude diagnostic alignment metadata."""

    if manifest_feature_cols is not None:
        missing = [col for col in manifest_feature_cols if col not in df.columns]
        if missing:
            raise ValueError(
                f"Regression feature batch is missing manifest feature columns: {path}; "
                f"missing={missing[:10]}"
            )
        non_numeric = [
            col
            for col in manifest_feature_cols
            if not _is_model_numeric_dtype(df.schema[col])
        ]
        if non_numeric:
            raise ValueError(
                f"Regression feature manifest contains non-numeric model columns: {path}; "
                f"non_numeric={non_numeric[:10]}"
            )
        return list(manifest_feature_cols)

    return [
        col
        for col, dtype in df.schema.items()
        if col not in {"timestamp", "batch_id", "asset_id", "root_id", "feature_set"}
        and col.startswith("rpf_")
        and not col.startswith(REGRESSION_FEATURE_METADATA_PREFIXES)
        and _is_model_numeric_dtype(dtype)
    ]


def regression_path_feature_root(
    dataset: RegressionDataset,
    feature_source_config: FeatureSourceConfig,
) -> Path:
    """Return the target-asset regression-path feature root for this dataset."""

    return (
        Path(feature_source_config.data_root)
        / "htf_multiasset"
        / dataset.target_asset.lower()
        / feature_source_config.regression_feature_set
        / dataset.root_id
        / "1m"
    )


def prepare_regression_frame(
    df: pl.DataFrame,
    target_col: str,
    *,
    feature_cols: list[str] | None = None,
    clip_bounds: dict[str, tuple[float, float]] | None = None,
) -> tuple[np.ndarray, np.ndarray, list[str], pl.DataFrame]:
    """Return model arrays after filtering rows with null/non-finite targets."""
    if target_col not in df.columns:
        raise ValueError(f"Target column not found: {target_col}")
    if feature_cols is None:
        feature_cols = get_feature_columns(df, target_col=target_col)
    feature_cols = [col for col in feature_cols if col in df.columns]
    clean = df.filter(pl.col(target_col).is_not_null() & pl.col(target_col).is_finite())
    if clean.is_empty():
        return (
            np.empty((0, len(feature_cols)), dtype=float),
            np.empty((0,), dtype=float),
            feature_cols,
            clean.select(["timestamp", "batch_id"]),
        )
    X = clean.select(feature_cols).to_numpy().astype(float)
    if clip_bounds:
        X = _apply_clip_bounds(X, feature_cols, clip_bounds)
    y = clean[target_col].to_numpy().astype(float)
    meta = clean.select(["timestamp", "batch_id"])
    return X, y, feature_cols, meta


def select_target_specific_features(
    train_df: pl.DataFrame,
    target_col: str,
    feature_cols: list[str],
    *,
    config: FeaturePolicyConfig,
) -> FeaturePolicyResult:
    """Select and clip features using training rows only."""
    if config.policy not in {FEATURE_POLICY_TARGET_SPECIFIC_V1, FEATURE_POLICY_TARGET_SPECIFIC_V2}:
        raise ValueError(f"Unsupported target-specific feature policy: {config.policy}")
    if int(config.min_selected_features) < 1:
        raise ValueError("min_selected_features must be positive")
    if int(config.stability_segments) < 2:
        raise ValueError("stability_segments must be at least 2")
    if not (0.5 < float(config.tail_quantile) < 1.0):
        raise ValueError("tail_quantile must satisfy 0.5 < tail_quantile < 1")
    clean = train_df.filter(pl.col(target_col).is_not_null() & pl.col(target_col).is_finite())
    if clean.is_empty():
        raise ValueError("Cannot select regression features from an empty training frame")

    base_rows: list[dict[str, Any]] = []
    candidate_cols: list[str] = []
    for feature in feature_cols:
        reason = _static_feature_drop_reason(feature)
        if reason:
            base_rows.append(_feature_policy_row(feature, selected=False, drop_reason=reason))
        else:
            candidate_cols.append(feature)

    if not candidate_cols:
        raise ValueError("No candidate features remain after static feature filtering")

    x_all = clean.select(candidate_cols).to_numpy().astype(float)
    y = clean[target_col].to_numpy().astype(float)
    valid_target = np.isfinite(y)
    if not valid_target.all():
        x_all = x_all[valid_target]
        y = y[valid_target]

    scored_rows: list[dict[str, Any]] = []
    kept_indices: list[int] = []
    for idx, feature in enumerate(candidate_cols):
        values = x_all[:, idx]
        reason = _train_feature_drop_reason(values)
        if reason:
            scored_rows.append(_feature_policy_row(feature, selected=False, drop_reason=reason))
            continue
        pearson = _correlation(y, values)
        spearman = _correlation(_rankdata_average(y), _rankdata_average(values))
        abs_pearson = abs(float(pearson or 0.0))
        abs_spearman = abs(float(spearman or 0.0))
        if config.policy == FEATURE_POLICY_TARGET_SPECIFIC_V2:
            stability = _signed_stability_score(
                y,
                values,
                global_corr=spearman,
                segments=int(config.stability_segments),
            )
            tail_score = _tail_spread_score(
                y,
                values,
                quantile=float(config.tail_quantile),
            )
            p95_score = _p95_separation_score(y, values)
            rank_score = (
                abs_spearman
                + 0.35 * max(float(stability["signed_stability_score"]), 0.0)
                + 0.25 * max(float(tail_score), 0.0)
                + 0.15 * max(float(p95_score), 0.0)
                + 0.10 * abs_pearson
            )
            extra_scores = {
                "stability_score": float(stability["signed_stability_score"]),
                "sign_consistency": float(stability["sign_consistency"]),
                "segment_abs_spearman_mean": float(stability["segment_abs_spearman_mean"]),
                "segment_abs_spearman_std": float(stability["segment_abs_spearman_std"]),
                "tail_spread_score": float(tail_score),
                "p95_separation_score": float(p95_score),
            }
        else:
            stability = _stability_score(y, values, segments=3)
            rank_score = abs_spearman + 0.5 * abs_pearson + 0.25 * max(stability, 0.0)
            extra_scores = {"stability_score": stability}
        scored_rows.append(
            _feature_policy_row(
                feature,
                selected=False,
                drop_reason="candidate",
                pearson=pearson,
                spearman=spearman,
                rank_score=rank_score,
                **extra_scores,
            )
        )
        kept_indices.append(idx)

    if not kept_indices:
        raise ValueError("No candidate features remain after train-only quality filtering")

    rows_by_feature = {row["feature"]: row for row in [*base_rows, *scored_rows]}
    candidate_rows = [
        rows_by_feature[candidate_cols[idx]]
        for idx in kept_indices
    ]
    candidate_rows.sort(key=lambda row: float(row["rank_score"] or 0.0), reverse=True)
    threshold_rows = [
        row
        for row in candidate_rows
        if float(row["abs_spearman"] or 0.0) >= float(config.min_abs_spearman)
    ]
    if config.policy == FEATURE_POLICY_TARGET_SPECIFIC_V2:
        threshold_features = {row["feature"] for row in threshold_rows}
        for row in candidate_rows:
            if row["feature"] not in threshold_features:
                row["drop_reason"] = "below_min_abs_spearman"
        if len(threshold_rows) < int(config.min_selected_features):
            raise ValueError(
                "target_specific_v2 found too few train-only eligible features: "
                f"{len(threshold_rows)} < {int(config.min_selected_features)} "
                f"with min_abs_spearman={float(config.min_abs_spearman):.6g}"
            )
        eligible_rows = threshold_rows
    elif len(threshold_rows) >= 50:
        eligible_rows = threshold_rows
        threshold_features = {row["feature"] for row in threshold_rows}
        for row in candidate_rows:
            if row["feature"] not in threshold_features:
                row["drop_reason"] = "below_min_abs_spearman"
    else:
        eligible_rows = candidate_rows

    selected = _dedupe_and_select_features(
        eligible_rows,
        x_all,
        candidate_cols,
        max_features=int(config.max_features),
        threshold=float(config.dedupe_corr_threshold),
    )
    if (
        config.policy == FEATURE_POLICY_TARGET_SPECIFIC_V2
        and len(selected) < int(config.min_selected_features)
    ):
        raise ValueError(
            "target_specific_v2 selected too few features after dedupe: "
            f"{len(selected)} < {int(config.min_selected_features)}"
        )
    selected_set = set(selected)
    selected_indices = [candidate_cols.index(feature) for feature in selected]
    clip_bounds = _clip_bounds(
        x_all[:, selected_indices],
        selected,
        quantiles=config.clip_quantiles,
    ) if selected_indices else {}

    for row in candidate_rows:
        feature = row["feature"]
        if feature in selected_set:
            row["selected"] = True
            row["drop_reason"] = None
            row["clip_low"] = clip_bounds[feature][0]
            row["clip_high"] = clip_bounds[feature][1]
        elif row["drop_reason"] == "candidate":
            row["drop_reason"] = "rank_below_selected"

    detail = pl.DataFrame([*base_rows, *scored_rows], infer_schema_length=None)
    return FeaturePolicyResult(
        selected_features=tuple(selected),
        clip_bounds=clip_bounds,
        detail=detail,
    )


def _static_feature_drop_reason(feature: str) -> str | None:
    base = feature.split("__", 1)[-1]
    if base.startswith(REGRESSION_FEATURE_METADATA_PREFIXES):
        return "regression_feature_metadata"
    if base in RAW_OHLCV_BASE_NAMES:
        return "raw_ohlcv_unscaled"
    if LEAKAGE_NAME_RE.search(feature) or LEAKAGE_NAME_RE.search(base):
        return "leakage_name_pattern"
    return None


def _train_feature_drop_reason(values: np.ndarray) -> str | None:
    finite = np.isfinite(values)
    if not finite.all():
        return "null_or_nonfinite"
    if len(values) == 0:
        return "empty"
    min_value = float(np.min(values))
    max_value = float(np.max(values))
    if min_value == max_value:
        return "constant"
    if float(np.max(np.abs(values))) >= 1_000_000.0:
        return "extreme_abs_ge_1e6"
    if float(np.std(values)) <= 1e-12:
        return "near_constant"
    p01 = float(np.quantile(values, 0.01))
    p99 = float(np.quantile(values, 0.99))
    if p01 == p99:
        return "near_constant"
    zero_rate = float(np.mean(values == 0.0))
    if zero_rate >= 0.995:
        return "near_constant"
    return None


def _feature_policy_row(
    feature: str,
    *,
    selected: bool,
    drop_reason: str | None,
    pearson: float | None = None,
    spearman: float | None = None,
    stability_score: float | None = None,
    sign_consistency: float | None = None,
    segment_abs_spearman_mean: float | None = None,
    segment_abs_spearman_std: float | None = None,
    tail_spread_score: float | None = None,
    p95_separation_score: float | None = None,
    rank_score: float | None = None,
) -> dict[str, Any]:
    return {
        "feature": feature,
        "selected": bool(selected),
        "drop_reason": drop_reason,
        "pearson": pearson,
        "spearman": spearman,
        "abs_pearson": abs(float(pearson)) if pearson is not None else None,
        "abs_spearman": abs(float(spearman)) if spearman is not None else None,
        "stability_score": stability_score,
        "sign_consistency": sign_consistency,
        "segment_abs_spearman_mean": segment_abs_spearman_mean,
        "segment_abs_spearman_std": segment_abs_spearman_std,
        "tail_spread_score": tail_spread_score,
        "p95_separation_score": p95_separation_score,
        "rank_score": rank_score,
        "clip_low": None,
        "clip_high": None,
    }


def _stability_score(y: np.ndarray, x: np.ndarray, *, segments: int) -> float:
    if len(y) < segments * 3:
        return 0.0
    scores: list[float] = []
    for idx in np.array_split(np.arange(len(y)), segments):
        if len(idx) < 3:
            continue
        corr = _correlation(y[idx], x[idx])
        if corr is not None:
            scores.append(abs(float(corr)))
    if not scores:
        return 0.0
    return float(np.mean(scores) - np.std(scores))


def _signed_stability_score(
    y: np.ndarray,
    x: np.ndarray,
    *,
    global_corr: float | None,
    segments: int,
) -> dict[str, float]:
    """Return a signed train-only stability score for chronological subwindows."""
    if len(y) < segments * 3:
        return {
            "signed_stability_score": 0.0,
            "sign_consistency": 0.0,
            "segment_abs_spearman_mean": 0.0,
            "segment_abs_spearman_std": 0.0,
        }
    global_sign = _sign(global_corr)
    scores: list[float] = []
    matching = 0
    for idx in np.array_split(np.arange(len(y)), segments):
        if len(idx) < 3:
            continue
        corr = _correlation(_rankdata_average(y[idx]), _rankdata_average(x[idx]))
        if corr is None:
            continue
        corr = float(corr)
        scores.append(corr)
        if global_sign != 0 and _sign(corr) == global_sign:
            matching += 1
    if not scores:
        return {
            "signed_stability_score": 0.0,
            "sign_consistency": 0.0,
            "segment_abs_spearman_mean": 0.0,
            "segment_abs_spearman_std": 0.0,
        }
    abs_scores = np.abs(np.asarray(scores, dtype=float))
    sign_consistency = float(matching / len(scores)) if global_sign != 0 else 0.0
    stability = float(np.mean(abs_scores) - np.std(abs_scores))
    signed_multiplier = (2.0 * sign_consistency) - 1.0
    return {
        "signed_stability_score": stability * signed_multiplier,
        "sign_consistency": sign_consistency,
        "segment_abs_spearman_mean": float(np.mean(abs_scores)),
        "segment_abs_spearman_std": float(np.std(abs_scores)),
    }


def _tail_spread_score(y: np.ndarray, x: np.ndarray, *, quantile: float) -> float:
    """Measure target separation between high and low feature quantile bins."""
    if len(y) < 10:
        return 0.0
    low_q = max(0.0, min(0.49, 1.0 - float(quantile)))
    high_q = min(1.0, max(0.51, float(quantile)))
    low_cut = float(np.quantile(x, low_q))
    high_cut = float(np.quantile(x, high_q))
    low_mask = x <= low_cut
    high_mask = x >= high_cut
    if int(low_mask.sum()) < 3 or int(high_mask.sum()) < 3:
        return 0.0
    scale = float(np.std(y))
    if scale <= 0.0:
        return 0.0
    return float(abs(np.mean(y[high_mask]) - np.mean(y[low_mask])) / scale)


def _p95_separation_score(y: np.ndarray, x: np.ndarray) -> float:
    """Measure whether high feature values separate high target-tail rows."""
    if len(y) < 20:
        return 0.0
    high_cut = float(np.quantile(x, 0.95))
    rest_cut = float(np.quantile(x, 0.50))
    high_mask = x >= high_cut
    rest_mask = x <= rest_cut
    if int(high_mask.sum()) < 3 or int(rest_mask.sum()) < 3:
        return 0.0
    scale = float(np.std(y))
    if scale <= 0.0:
        return 0.0
    return float(abs(np.mean(y[high_mask]) - np.mean(y[rest_mask])) / scale)


def _sign(value: float | None) -> int:
    if value is None:
        return 0
    value = float(value)
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def _dedupe_and_select_features(
    eligible_rows: list[dict[str, Any]],
    x_all: np.ndarray,
    candidate_cols: list[str],
    *,
    max_features: int,
    threshold: float,
) -> list[str]:
    if max_features <= 0:
        raise ValueError("max_features must be positive")
    pool_size = min(len(eligible_rows), max(max_features * 3, 50), 1000)
    pool = eligible_rows[:pool_size]
    pool_features = [row["feature"] for row in pool]
    pool_indices = [candidate_cols.index(feature) for feature in pool_features]
    values = x_all[:, pool_indices].astype(float)
    std = values.std(axis=0)
    valid = std > 0
    standardized = np.zeros_like(values, dtype=float)
    standardized[:, valid] = (values[:, valid] - values[:, valid].mean(axis=0)) / std[valid]
    denom = max(len(values) - 1, 1)
    corr = np.abs((standardized.T @ standardized) / denom)
    selected_pool_indices: list[int] = []
    selected_features: list[str] = []
    for pool_idx, row in enumerate(pool):
        if len(selected_features) >= max_features:
            row["drop_reason"] = "rank_below_max_features"
            continue
        duplicate_of: str | None = None
        for kept_pool_idx in selected_pool_indices:
            if corr[pool_idx, kept_pool_idx] >= threshold:
                duplicate_of = pool_features[kept_pool_idx]
                break
        if duplicate_of:
            row["drop_reason"] = f"near_duplicate_of:{duplicate_of}"
            continue
        selected_pool_indices.append(pool_idx)
        selected_features.append(row["feature"])
    selected_set = set(selected_features)
    for row in eligible_rows:
        if row["feature"] in selected_set:
            continue
        if row["drop_reason"] in {None, "candidate"}:
            row["drop_reason"] = "rank_below_selected"
    return selected_features


def _clip_bounds(
    x: np.ndarray,
    feature_cols: list[str],
    *,
    quantiles: tuple[float, float],
) -> dict[str, tuple[float, float]]:
    low_q, high_q = quantiles
    if not (0.0 <= low_q < high_q <= 1.0):
        raise ValueError("clip quantiles must satisfy 0 <= low < high <= 1")
    bounds: dict[str, tuple[float, float]] = {}
    for idx, feature in enumerate(feature_cols):
        values = x[:, idx]
        bounds[feature] = (
            float(np.quantile(values, low_q)),
            float(np.quantile(values, high_q)),
        )
    return bounds


def _apply_clip_bounds(
    x: np.ndarray,
    feature_cols: list[str],
    bounds: dict[str, tuple[float, float]],
) -> np.ndarray:
    if not bounds:
        return x
    out = np.asarray(x, dtype=float).copy()
    for idx, feature in enumerate(feature_cols):
        if feature not in bounds:
            continue
        low, high = bounds[feature]
        out[:, idx] = np.clip(out[:, idx], low, high)
    return out


def _prefix_metrics(metrics: dict[str, float | int | None], prefix: str) -> dict[str, float | int | None]:
    return {f"{prefix}_{key}": value for key, value in metrics.items()}


def _selected_feature_frequency_frame(counter: Counter[str], step_count: int) -> pl.DataFrame:
    rows = [
        {
            "feature": feature,
            "selected_steps": int(count),
            "selected_rate": float(count / step_count) if step_count else 0.0,
        }
        for feature, count in counter.most_common()
    ]
    if not rows:
        return pl.DataFrame({"feature": [], "selected_steps": [], "selected_rate": []})
    return pl.DataFrame(rows)


def fit_catboost_regressor(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    *,
    model_config: CatBoostModelConfig,
    task_type: str,
    thread_count: int,
) -> Any:
    try:
        from catboost import CatBoostRegressor
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("CatBoost is required for regression walk-forward") from exc

    params = build_catboost_params(
        model_config,
        task_type=task_type,
        thread_count=thread_count,
    )
    model = CatBoostRegressor(**params)
    try:
        model.fit(
            X_train,
            y_train,
            eval_set=(X_val, y_val),
            use_best_model=True,
            early_stopping_rounds=int(model_config.early_stopping_rounds),
            verbose=False,
        )
        return model
    except Exception:
        if params["task_type"] != "GPU":
            raise
        params["task_type"] = "CPU"
        params.pop("devices", None)
        model = CatBoostRegressor(**params)
        model.fit(
            X_train,
            y_train,
            eval_set=(X_val, y_val),
            use_best_model=True,
            early_stopping_rounds=int(model_config.early_stopping_rounds),
            verbose=False,
        )
        return model


def catboost_model_diagnostics(model: Any) -> dict[str, int | None]:
    """Return compact model diagnostics that show whether early stopping fired."""

    best_iteration = None
    get_best_iteration = getattr(model, "get_best_iteration", None)
    if callable(get_best_iteration):
        try:
            value = get_best_iteration()
            best_iteration = None if value is None else int(value)
        except Exception:
            best_iteration = None
    tree_count = getattr(model, "tree_count_", None)
    try:
        tree_count = None if tree_count is None else int(tree_count)
    except Exception:
        tree_count = None
    return {
        "model_best_iteration": best_iteration,
        "model_tree_count": tree_count,
    }


def build_catboost_params(
    model_config: CatBoostModelConfig,
    *,
    task_type: str,
    thread_count: int,
) -> dict[str, Any]:
    """Build validated CatBoostRegressor parameters for the current backend."""

    task = str(task_type).upper()
    if task not in {"CPU", "GPU"}:
        raise ValueError(f"Unsupported CatBoost task_type: {task_type!r}")
    if int(model_config.iterations) <= 0:
        raise ValueError("CatBoost iterations must be positive")
    if int(model_config.depth) <= 0:
        raise ValueError("CatBoost depth must be positive")
    if float(model_config.learning_rate) <= 0:
        raise ValueError("CatBoost learning_rate must be positive")
    if float(model_config.l2_leaf_reg) < 0:
        raise ValueError("CatBoost l2_leaf_reg must be nonnegative")
    if int(model_config.early_stopping_rounds) <= 0:
        raise ValueError("CatBoost early_stopping_rounds must be positive")

    params: dict[str, Any] = {
        "loss_function": str(model_config.loss_function),
        "eval_metric": str(model_config.eval_metric),
        "iterations": int(model_config.iterations),
        "depth": int(model_config.depth),
        "learning_rate": float(model_config.learning_rate),
        "l2_leaf_reg": float(model_config.l2_leaf_reg),
        "random_seed": 42,
        "allow_writing_files": False,
        "verbose": False,
        "thread_count": int(thread_count),
        "task_type": task,
        "has_time": bool(model_config.has_time),
    }
    if model_config.od_type is not None:
        params["od_type"] = str(model_config.od_type)
    if model_config.od_wait is not None:
        params["od_wait"] = int(model_config.od_wait)
    if model_config.random_strength is not None:
        params["random_strength"] = float(model_config.random_strength)
    if model_config.border_count is not None:
        params["border_count"] = int(model_config.border_count)
    if model_config.grow_policy is not None:
        params["grow_policy"] = str(model_config.grow_policy)
    if model_config.leaf_estimation_method is not None:
        params["leaf_estimation_method"] = str(model_config.leaf_estimation_method)
    if model_config.leaf_estimation_iterations is not None:
        params["leaf_estimation_iterations"] = int(model_config.leaf_estimation_iterations)
    if model_config.boosting_type is not None:
        params["boosting_type"] = str(model_config.boosting_type)
    if model_config.gpu_ram_part is not None:
        if task != "GPU":
            raise ValueError("gpu_ram_part is only valid for GPU CatBoost runs")
        params["gpu_ram_part"] = float(model_config.gpu_ram_part)

    bootstrap_type = str(model_config.bootstrap_type) if model_config.bootstrap_type else None
    if bootstrap_type:
        params["bootstrap_type"] = bootstrap_type
    if model_config.bagging_temperature is not None:
        if bootstrap_type != "Bayesian":
            raise ValueError("bagging_temperature is valid only with bootstrap_type=Bayesian")
        params["bagging_temperature"] = float(model_config.bagging_temperature)
    if model_config.subsample is not None:
        if bootstrap_type not in {"Bernoulli", "Poisson", "MVS"}:
            raise ValueError("subsample requires bootstrap_type Bernoulli, Poisson, or MVS")
        if bootstrap_type == "Poisson" and task != "GPU":
            raise ValueError("bootstrap_type=Poisson is GPU-only in CatBoost")
        params["subsample"] = float(model_config.subsample)
    if model_config.mvs_reg is not None:
        if bootstrap_type != "MVS":
            raise ValueError("mvs_reg is valid only with bootstrap_type=MVS")
        if task == "GPU":
            raise ValueError("mvs_reg is not enabled for GPU-first staged runs")
        params["mvs_reg"] = float(model_config.mvs_reg)

    grow_policy = str(model_config.grow_policy) if model_config.grow_policy else None
    if model_config.min_data_in_leaf is not None:
        if grow_policy not in {"Depthwise", "Lossguide"}:
            raise ValueError("min_data_in_leaf requires grow_policy Depthwise or Lossguide")
        params["min_data_in_leaf"] = int(model_config.min_data_in_leaf)
    if model_config.max_leaves is not None:
        if grow_policy != "Lossguide":
            raise ValueError("max_leaves requires grow_policy=Lossguide")
        if int(model_config.max_leaves) > 64:
            raise ValueError("max_leaves is capped at 64 for staged RPF optimization")
        params["max_leaves"] = int(model_config.max_leaves)
    if params.get("grow_policy") != "Lossguide" and "max_leaves" in params:
        raise ValueError("max_leaves can only be passed with Lossguide")
    if task == "GPU":
        params["devices"] = "0"
    return params


def _catboost_model_config_payload(model_config: CatBoostModelConfig) -> dict[str, Any]:
    return {
        key: value
        for key, value in model_config.__dict__.items()
        if value is not None
    }


def plan_regression_steps(
    batch_index: pl.DataFrame,
    *,
    n_steps: int,
    lookback_batches: int,
    val_batches: int,
    embargo_batches: int,
) -> list[RegressionStep]:
    """Plan sparse-safe train/validation/prediction windows by dense position."""
    if batch_index.is_empty():
        return []
    ordered = batch_index.sort("stage1_available_pos")
    rows = [row for row in ordered.iter_rows(named=True) if int(row["valid_row_count"]) > 0]
    steps: list[RegressionStep] = []
    for pos_idx in range(len(rows)):
        pred_pos = int(rows[pos_idx]["stage1_available_pos"])
        val_end_idx = pos_idx - int(embargo_batches)
        val_start_idx = val_end_idx - int(val_batches)
        train_end_idx = val_start_idx
        train_start_idx = train_end_idx - int(lookback_batches)
        if train_start_idx < 0 or val_start_idx < 0 or val_end_idx > pos_idx:
            continue
        train_ids = tuple(int(rows[i]["batch_id"]) for i in range(train_start_idx, train_end_idx))
        val_ids = tuple(int(rows[i]["batch_id"]) for i in range(val_start_idx, val_end_idx))
        if len(train_ids) != int(lookback_batches) or len(val_ids) != int(val_batches):
            continue
        steps.append(
            RegressionStep(
                step_idx=len(steps),
                pred_pos=pred_pos,
                pred_batch_id=int(rows[pos_idx]["batch_id"]),
                train_batch_ids=train_ids,
                val_batch_ids=val_ids,
            )
        )
    return steps[-int(n_steps) :] if n_steps > 0 else steps


def regression_steps_to_frame(steps: list[RegressionStep]) -> pl.DataFrame:
    """Serialize sparse walk-forward steps with explicit train/val batch ids."""

    return pl.DataFrame(
        [
            {
                "step_idx": int(step.step_idx),
                "pred_pos": int(step.pred_pos),
                "pred_batch_id": int(step.pred_batch_id),
                "train_batch_ids": list(step.train_batch_ids),
                "val_batch_ids": list(step.val_batch_ids),
                "train_batch_count": int(len(step.train_batch_ids)),
                "val_batch_count": int(len(step.val_batch_ids)),
            }
            for step in steps
        ],
        infer_schema_length=None,
    )


def load_regression_steps_from_index(path: Path) -> list[RegressionStep]:
    """Load explicit frozen sparse walk-forward steps."""

    if not Path(path).exists():
        raise FileNotFoundError(f"Frozen regression step index not found: {path}")
    frame = pl.read_parquet(path).sort("step_idx")
    required = {"step_idx", "pred_pos", "pred_batch_id", "train_batch_ids", "val_batch_ids"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Frozen regression step index is missing columns {sorted(missing)}: {path}")
    steps: list[RegressionStep] = []
    for row in frame.iter_rows(named=True):
        steps.append(
            RegressionStep(
                step_idx=int(row["step_idx"]),
                pred_pos=int(row["pred_pos"]),
                pred_batch_id=int(row["pred_batch_id"]),
                train_batch_ids=tuple(int(value) for value in row["train_batch_ids"]),
                val_batch_ids=tuple(int(value) for value in row["val_batch_ids"]),
            )
        )
    return steps


def regression_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float | int | None]:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    mask = np.isfinite(y_true) & np.isfinite(y_pred)
    y_true = y_true[mask]
    y_pred = y_pred[mask]
    n = int(len(y_true))
    if n == 0:
        return {
            "rows": 0,
            "mae": None,
            "rmse": None,
            "median_abs_error": None,
            "r2": None,
            "pearson": None,
            "spearman": None,
            "spearman_null_reason": "too_few_rows",
            "bias": None,
            "target_std": None,
            "pred_std": None,
            "target_unique": 0,
            "pred_unique": 0,
            "target_p95": None,
            "pred_p95": None,
            "p95_coverage_ratio": None,
            "tail_rows": 0,
            "tail_mae": None,
            "tail_rmse": None,
        }
    error = y_pred - y_true
    ss_res = float(np.sum(error**2))
    ss_tot = float(np.sum((y_true - np.mean(y_true)) ** 2))
    target_std = float(np.std(y_true))
    pred_std = float(np.std(y_pred))
    target_unique = int(len(np.unique(np.round(y_true, 12))))
    pred_unique = int(len(np.unique(np.round(y_pred, 12))))
    pearson = _correlation(y_true, y_pred)
    spearman = _correlation(_rankdata_average(y_true), _rankdata_average(y_pred))
    target_p95 = float(np.quantile(y_true, 0.95))
    pred_p95 = float(np.quantile(y_pred, 0.95))
    tail_cut = float(np.quantile(y_true, 0.80))
    tail_mask = y_true >= tail_cut
    tail_error = error[tail_mask]
    return {
        "rows": n,
        "mae": _safe_float(np.mean(np.abs(error))),
        "rmse": _safe_float(math.sqrt(np.mean(error**2))),
        "median_abs_error": _safe_float(np.median(np.abs(error))),
        "r2": _safe_float(1.0 - ss_res / ss_tot) if ss_tot > 0 else None,
        "pearson": pearson,
        "spearman": spearman,
        "spearman_null_reason": _correlation_null_reason(y_true, y_pred) if spearman is None else None,
        "bias": _safe_float(np.mean(error)),
        "target_mean": _safe_float(np.mean(y_true)),
        "pred_mean": _safe_float(np.mean(y_pred)),
        "target_std": _safe_float(target_std),
        "pred_std": _safe_float(pred_std),
        "target_unique": target_unique,
        "pred_unique": pred_unique,
        "target_p50": _safe_float(np.quantile(y_true, 0.50)),
        "pred_p50": _safe_float(np.quantile(y_pred, 0.50)),
        "target_p95": _safe_float(target_p95),
        "pred_p95": _safe_float(pred_p95),
        "p95_coverage_ratio": _safe_float(pred_p95 / target_p95) if target_p95 > 0 else None,
        "tail_rows": int(tail_mask.sum()),
        "tail_mae": _safe_float(np.mean(np.abs(tail_error))) if len(tail_error) else None,
        "tail_rmse": _safe_float(math.sqrt(np.mean(tail_error**2))) if len(tail_error) else None,
    }


def resolve_or_build_dataset(args: argparse.Namespace, *, target_asset: str, root_key: str) -> RegressionDataset:
    context_assets = parse_stage1_context_assets(args.context_assets, target_asset=target_asset)
    if bool(args.build_merged_dataset):
        assembly = build_multiasset_stage1_dataset(
            project_root=PROJECT_ROOT,
            target_asset=target_asset,
            context_assets=context_assets,
            root_key=root_key,
            output_base_dir=Path(args.multiasset_dataset_dir),
            input_base_dir=PROJECT_ROOT / "data" / "htf_multiasset",
            target_col=str(args.stage1_target_col),
            feature_target_col=FEATURE_TARGET_COL,
            max_batches=args.merged_batch_limit,
            batch_id_min=args.merged_batch_min,
            batch_id_max=args.merged_batch_max,
        )
        manifest_path = assembly.manifest_path
    else:
        manifest_path = _existing_manifest_path(
            target_asset=target_asset,
            context_assets=context_assets,
            root_key=root_key,
            target_col=str(args.stage1_target_col),
            multiasset_dataset_dir=Path(args.multiasset_dataset_dir),
        )
    manifest = json.loads(manifest_path.read_text())
    return RegressionDataset(
        target_asset=normalize_htf_asset_id(target_asset),
        context_assets=tuple(context_assets),
        context_hash=str(manifest["context_hash"]),
        root_key=str(manifest["root"]),
        root_id=str(manifest["root_id"]),
        target_col=str(manifest["target_col"]),
        feature_target_col=str(manifest["feature_target_col"]),
        features_dir=Path(manifest["output_paths"]["features_dir"]),
        labels_dir=Path(manifest["output_paths"]["labels_dir"]),
        manifest_path=manifest_path,
        batch_index_path=Path(manifest["output_paths"]["stage1_batch_index"]),
    )


def _existing_manifest_path(
    *,
    target_asset: str,
    context_assets: tuple[str, ...],
    root_key: str,
    target_col: str,
    multiasset_dataset_dir: Path,
) -> Path:
    target_asset = normalize_htf_asset_id(target_asset)
    layout = STAGE1_MULTIASSET_ROOT_LAYOUTS[root_key]
    context_hash = build_context_set_hash(
        target_asset=target_asset,
        context_assets=context_assets,
    )
    variant_id = build_stage1_dataset_variant_id(
        target_col=target_col,
        include_ta_flags=False,
    )
    root_dir = Path(multiasset_dataset_dir) / target_asset.lower() / context_hash
    if variant_id != "base":
        root_dir = root_dir / variant_id
    path = root_dir / layout.root_id / "manifest.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Merged regression dataset manifest not found: {path}. "
            "Run with --build-merged-dataset first."
        )
    return path


def _load_batch_index(path: Path, *, target_col: str) -> pl.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Stage-1 batch index not found: {path}")
    df = pl.read_parquet(path)
    required = {"stage1_available_pos", "batch_id", "valid_row_count"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Batch index missing columns {sorted(missing)}: {path}")
    if "target_col" in df.columns:
        mismatched = df.filter(pl.col("target_col") != str(target_col))
        if mismatched.height:
            raise ValueError(f"Batch index target_col does not match {target_col}: {path}")
    return df


def _rankdata_average(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    order = np.argsort(values, kind="mergesort")
    sorted_values = values[order]
    ranks = np.empty(len(values), dtype=float)
    i = 0
    while i < len(values):
        j = i + 1
        while j < len(values) and sorted_values[j] == sorted_values[i]:
            j += 1
        avg_rank = (i + j - 1) / 2.0 + 1.0
        ranks[order[i:j]] = avg_rank
        i = j
    return ranks


def _correlation_null_reason(a: np.ndarray, b: np.ndarray) -> str | None:
    if len(a) < 2:
        return "too_few_rows"
    if np.std(a) == 0:
        return "constant_target"
    if np.std(b) == 0:
        return "constant_prediction"
    return None


def _correlation(a: np.ndarray, b: np.ndarray) -> float | None:
    if len(a) < 2 or np.std(a) == 0 or np.std(b) == 0:
        return None
    return _safe_float(np.corrcoef(a, b)[0, 1])


def _safe_float(value: Any) -> float | None:
    value = float(value)
    if math.isnan(value) or math.isinf(value):
        return None
    return value


def _is_model_numeric_dtype(dtype: pl.DataType) -> bool:
    return dtype in {
        pl.Float32,
        pl.Float64,
        pl.Int8,
        pl.Int16,
        pl.Int32,
        pl.Int64,
        pl.UInt8,
        pl.UInt16,
        pl.UInt32,
        pl.UInt64,
        pl.Boolean,
    }


def _validate_feature_source_config(config: FeatureSourceConfig) -> None:
    if config.mode not in FEATURE_SOURCE_MODES:
        raise ValueError(
            f"Unsupported feature source mode {config.mode!r}; "
            f"expected one of {list(FEATURE_SOURCE_MODES)}"
        )
    if not str(config.regression_feature_set).strip():
        raise ValueError("regression_feature_set cannot be empty")


def _target_slug(target_col: str) -> str:
    slug = str(target_col)
    if slug.startswith("target_"):
        slug = slug[len("target_") :]
    return _slug(slug) or "target"


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", str(value)).strip("_").lower()


def _write_markdown_report(path: Path, payload: dict[str, Any], step_metrics: pl.DataFrame) -> None:
    pred_metrics = payload["prediction_metrics"]
    val_metrics = payload["validation_metrics"]
    lines = [
        "# Stage-1 Regression Walk-Forward Summary",
        "",
        f"Run ID: `{payload['run_id']}`",
        f"Target: `{payload['target_col']}`",
        f"Asset/root: `{payload['target_asset']} {payload['root']}`",
        f"Completed steps: {payload['n_completed_steps']} / {payload['n_requested_steps']}",
        f"Prediction rows: {pred_metrics.get('rows')}",
        f"Validation rows: {val_metrics.get('rows')}",
        f"Optimization decision basis: `{payload['optimization_decision_basis']}`",
        "",
        "## Validation Metrics",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    metric_keys = (
        "mae",
        "rmse",
        "median_abs_error",
        "r2",
        "pearson",
        "spearman",
        "bias",
        "target_mean",
        "pred_mean",
        "target_p95",
        "pred_p95",
        "p95_coverage_ratio",
        "tail_mae",
        "tail_rmse",
    )
    for key in metric_keys:
        value = val_metrics.get(key)
        lines.append(f"| `{key}` | {_fmt(value)} |")
    lines.extend(["", "## Prediction Metrics", "", "| Metric | Value |", "|---|---:|"])
    for key in metric_keys:
        value = pred_metrics.get(key)
        lines.append(f"| `{key}` | {_fmt(value)} |")
    if not step_metrics.is_empty():
        lines.extend(["", "Per-step metrics are stored in `step_metrics.parquet`."])
    path.write_text("\n".join(lines) + "\n")


def _write_feature_policy_summary(path: Path, payload: dict[str, Any], selected_frequency: pl.DataFrame) -> None:
    policy = payload["feature_policy"]
    lines = [
        "# Stage-1 Regression Feature Policy Summary",
        "",
        f"Run ID: `{payload['run_id']}`",
        f"Target: `{payload['target_col']}`",
        f"Policy: `{policy['policy']}`",
        f"Completed steps: {payload['n_completed_steps']} / {payload['n_requested_steps']}",
        "",
        "| Field | Value |",
        "|---|---:|",
        f"| `max_features` | {policy['max_features']} |",
        f"| `min_abs_spearman` | {_fmt(policy['min_abs_spearman'])} |",
        f"| `dedupe_corr_threshold` | {_fmt(policy['dedupe_corr_threshold'])} |",
        f"| `min_selected_features` | {policy['min_selected_features']} |",
        f"| `stability_segments` | {policy['stability_segments']} |",
        f"| `tail_quantile` | {_fmt(policy['tail_quantile'])} |",
        f"| `selected_feature_count_min` | {policy['selected_feature_count_min']} |",
        f"| `selected_feature_count_mean` | {_fmt(policy['selected_feature_count_mean'])} |",
        f"| `selected_feature_count_max` | {policy['selected_feature_count_max']} |",
        "",
        "## Most Frequently Selected Features",
        "",
        "| Feature | Selected Steps | Selected Rate |",
        "|---|---:|---:|",
    ]
    for row in selected_frequency.head(50).to_dicts():
        lines.append(
            f"| `{row['feature']}` | {row['selected_steps']} | {_fmt(row['selected_rate'])} |"
        )
    path.write_text("\n".join(lines) + "\n")


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    return f"{float(value):.6g}"


def _append_event(path: Path, event: str, **fields: Any) -> None:
    payload = {
        "event": event,
        "ts": datetime.now(timezone.utc).isoformat(),
        **fields,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(payload, default=str) + "\n")


def _progress(message: str) -> None:
    print(message, flush=True)


def _should_log_step(step_index: int, total_steps: int, log_every_steps: int) -> bool:
    if int(log_every_steps) <= 0:
        return False
    return step_index == 1 or step_index == total_steps or step_index % int(log_every_steps) == 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sparse-aware CatBoostRegressor walk-forward for Stage-1 regression targets."
    )
    parser.add_argument("--build-merged-dataset", action="store_true")
    parser.add_argument("--target-assets", default="BTCUSDT")
    parser.add_argument("--context-assets", default=None)
    parser.add_argument("--roots", nargs="*", choices=sorted(STAGE1_MULTIASSET_ROOT_LAYOUTS), default=["8h/B"])
    parser.add_argument("--stage1-target-col", default=UP_EXTREME_COL, choices=all_target_cols())
    parser.add_argument("--multiasset-dataset-dir", type=Path, default=PROJECT_ROOT / "data" / MULTIASSET_MERGED_ROOT)
    parser.add_argument("--merged-batch-min", type=int, default=None)
    parser.add_argument("--merged-batch-max", type=int, default=None)
    parser.add_argument("--merged-batch-limit", type=int, default=None)
    parser.add_argument("--n-steps", type=int, default=20)
    parser.add_argument("--lookback-batches", type=int, default=120)
    parser.add_argument("--val-batches", type=int, default=20)
    parser.add_argument("--embargo-batches", type=int, default=0)
    parser.add_argument("--iterations", type=int, default=200)
    parser.add_argument("--depth", type=int, default=6)
    parser.add_argument("--learning-rate", type=float, default=0.05)
    parser.add_argument("--l2-leaf-reg", type=float, default=3.0)
    parser.add_argument("--loss-function", default="RMSE")
    parser.add_argument("--eval-metric", default="RMSE")
    parser.add_argument("--early-stopping-rounds", type=int, default=50)
    parser.add_argument("--od-type", default="Iter")
    parser.add_argument("--od-wait", type=int, default=None)
    parser.add_argument("--random-strength", type=float, default=None)
    parser.add_argument("--bootstrap-type", default=None)
    parser.add_argument("--bagging-temperature", type=float, default=None)
    parser.add_argument("--subsample", type=float, default=None)
    parser.add_argument("--mvs-reg", type=float, default=None)
    parser.add_argument("--border-count", type=int, default=None)
    parser.add_argument("--grow-policy", default=None)
    parser.add_argument("--min-data-in-leaf", type=int, default=None)
    parser.add_argument("--max-leaves", type=int, default=None)
    parser.add_argument("--leaf-estimation-method", default=None)
    parser.add_argument("--leaf-estimation-iterations", type=int, default=None)
    parser.add_argument("--boosting-type", default=None)
    parser.add_argument("--has-time", dest="has_time", action="store_true", default=True)
    parser.add_argument("--no-has-time", dest="has_time", action="store_false")
    parser.add_argument("--gpu-ram-part", type=float, default=None)
    parser.add_argument("--task-type", choices=["CPU", "GPU"], default="CPU")
    parser.add_argument("--thread-count", type=int, default=-1)
    parser.add_argument(
        "--feature-policy",
        choices=list(FEATURE_POLICIES),
        default=FEATURE_POLICY_FULL,
    )
    parser.add_argument("--max-features", type=int, default=300)
    parser.add_argument("--min-abs-spearman", type=float, default=0.01)
    parser.add_argument("--min-selected-features", type=int, default=20)
    parser.add_argument("--stability-segments", type=int, default=5)
    parser.add_argument("--tail-quantile", type=float, default=0.80)
    parser.add_argument("--dedupe-corr-threshold", type=float, default=0.995)
    parser.add_argument("--clip-quantiles", default="0.001,0.999")
    parser.add_argument(
        "--feature-source-mode",
        choices=list(FEATURE_SOURCE_MODES),
        default=FEATURE_SOURCE_HTF_ONLY,
        help=(
            "Feature roots visible to the regressor. `htf_only` preserves current behavior; "
            "`regression_only` uses target regression_path_features_v1 only; "
            "`htf_plus_regression` joins both."
        ),
    )
    parser.add_argument("--regression-feature-set", default=REGRESSION_FEATURE_SET)
    parser.add_argument("--frozen-step-index-path", type=Path, default=None)
    parser.add_argument("--log-every-steps", type=int, default=1)
    parser.add_argument("--run-suffix", default=None)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--plan-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    targets = parse_stage1_target_assets(args.target_assets)
    roots = tuple(args.roots)
    entries: list[RegressionDataset] = []
    for target_asset in targets:
        for root_key in roots:
            dataset = resolve_or_build_dataset(args, target_asset=target_asset, root_key=root_key)
            entries.append(dataset)
            print(
                f"Resolved {dataset.target_asset} {dataset.root_key} {dataset.target_col}: "
                f"features={dataset.features_dir} labels={dataset.labels_dir}"
            )
    if args.plan_only:
        print(f"Plan only: {len(entries)} dataset(s) resolved.")
        return 0

    feature_policy_config = FeaturePolicyConfig(
        policy=str(args.feature_policy),
        max_features=int(args.max_features),
        min_abs_spearman=float(args.min_abs_spearman),
        dedupe_corr_threshold=float(args.dedupe_corr_threshold),
        clip_quantiles=_parse_clip_quantiles(str(args.clip_quantiles)),
        min_selected_features=int(args.min_selected_features),
        stability_segments=int(args.stability_segments),
        tail_quantile=float(args.tail_quantile),
    )
    feature_source_config = FeatureSourceConfig(
        mode=str(args.feature_source_mode),
        regression_feature_set=str(args.regression_feature_set),
        data_root=PROJECT_ROOT / "data",
    )
    catboost_model_config = CatBoostModelConfig(
        iterations=int(args.iterations),
        depth=int(args.depth),
        learning_rate=float(args.learning_rate),
        l2_leaf_reg=float(args.l2_leaf_reg),
        loss_function=str(args.loss_function),
        eval_metric=str(args.eval_metric),
        early_stopping_rounds=int(args.early_stopping_rounds),
        od_type=str(args.od_type) if args.od_type is not None else None,
        od_wait=args.od_wait,
        random_strength=args.random_strength,
        bootstrap_type=args.bootstrap_type,
        bagging_temperature=args.bagging_temperature,
        subsample=args.subsample,
        mvs_reg=args.mvs_reg,
        border_count=args.border_count,
        grow_policy=args.grow_policy,
        min_data_in_leaf=args.min_data_in_leaf,
        max_leaves=args.max_leaves,
        leaf_estimation_method=args.leaf_estimation_method,
        leaf_estimation_iterations=args.leaf_estimation_iterations,
        boosting_type=args.boosting_type,
        has_time=bool(args.has_time),
        gpu_ram_part=args.gpu_ram_part,
    )
    for dataset in entries:
        payload = run_regression_walkforward(
            dataset=dataset,
            n_steps=int(args.n_steps),
            lookback_batches=int(args.lookback_batches),
            val_batches=int(args.val_batches),
            embargo_batches=int(args.embargo_batches),
            iterations=int(args.iterations),
            depth=int(args.depth),
            learning_rate=float(args.learning_rate),
            l2_leaf_reg=float(args.l2_leaf_reg),
            task_type=str(args.task_type),
            thread_count=int(args.thread_count),
            catboost_model_config=catboost_model_config,
            feature_policy_config=feature_policy_config,
            feature_source_config=feature_source_config,
            frozen_step_index_path=args.frozen_step_index_path,
            log_every_steps=int(args.log_every_steps),
            run_suffix=args.run_suffix,
            output_root=Path(args.output_dir),
        )
        metrics = payload["aggregate_metrics"]
        print(
            f"DONE {payload['run_id']}: steps={payload['n_completed_steps']} "
            f"rows={metrics['rows']} rmse={_fmt(metrics['rmse'])} "
            f"mae={_fmt(metrics['mae'])} spearman={_fmt(metrics['spearman'])}"
        )
        print(f"Summary: {payload['outputs']['summary']}")
    return 0


def _parse_clip_quantiles(raw: str) -> tuple[float, float]:
    parts = [part.strip() for part in str(raw).split(",") if part.strip()]
    if len(parts) != 2:
        raise ValueError("--clip-quantiles must be two comma-separated floats, e.g. 0.001,0.999")
    low, high = float(parts[0]), float(parts[1])
    if not (0.0 <= low < high <= 1.0):
        raise ValueError("--clip-quantiles must satisfy 0 <= low < high <= 1")
    return low, high


if __name__ == "__main__":
    raise SystemExit(main())
