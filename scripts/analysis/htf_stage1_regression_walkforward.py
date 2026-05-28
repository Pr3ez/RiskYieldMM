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
RAW_OHLCV_BASE_NAMES = {"open", "high", "low", "close", "volume"}
LEAKAGE_NAME_RE = re.compile(
    r"(^|__)target_|(^|__)tb_|label_window|future|diagnostic",
    re.IGNORECASE,
)


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


@dataclass(frozen=True)
class FeaturePolicyResult:
    selected_features: tuple[str, ...]
    clip_bounds: dict[str, tuple[float, float]]
    detail: pl.DataFrame


def build_regression_run_id(dataset: RegressionDataset) -> str:
    slug = _target_slug(dataset.target_col)
    return (
        f"stage1_regression_{dataset.target_asset.lower()}_"
        f"{dataset.root_id}_ctx_{dataset.context_hash}_{slug}_live"
    )


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
    task_type: str,
    thread_count: int,
    feature_policy_config: FeaturePolicyConfig | None = None,
    output_root: Path = OUTPUT_ROOT,
) -> dict[str, Any]:
    """Run a compact sparse-aware CatBoostRegressor walk-forward evaluation."""
    feature_policy_config = feature_policy_config or FeaturePolicyConfig()
    batch_index = _load_batch_index(dataset.batch_index_path, target_col=dataset.target_col)
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

    run_id = build_regression_run_id(dataset)
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    step_rows: list[dict[str, Any]] = []
    pred_frames: list[pl.DataFrame] = []
    feature_policy_frames: list[pl.DataFrame] = []
    selected_feature_counter: Counter[str] = Counter()
    selected_feature_counts: list[int] = []
    feature_cols_ref: list[str] | None = None
    for step in steps:
        train_df = load_batches_by_ids(
            dataset.features_dir,
            dataset.labels_dir,
            "1m",
            step.train_batch_ids,
            target_col=dataset.target_col,
            feature_target_col=dataset.feature_target_col,
        )
        val_df = load_batches_by_ids(
            dataset.features_dir,
            dataset.labels_dir,
            "1m",
            step.val_batch_ids,
            target_col=dataset.target_col,
            feature_target_col=dataset.feature_target_col,
        )
        pred_df = load_batches_by_ids(
            dataset.features_dir,
            dataset.labels_dir,
            "1m",
            (step.pred_batch_id,),
            target_col=dataset.target_col,
            feature_target_col=dataset.feature_target_col,
        )

        base_feature_cols = get_feature_columns(train_df, target_col=dataset.target_col)
        if feature_policy_config.policy == FEATURE_POLICY_TARGET_SPECIFIC_V1:
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
        X_val, y_val, _, _ = prepare_regression_frame(
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
            continue
        feature_cols_ref = feature_cols if feature_cols_ref is None else feature_cols_ref
        model = fit_catboost_regressor(
            X_train,
            y_train,
            X_val,
            y_val,
            iterations=iterations,
            depth=depth,
            learning_rate=learning_rate,
            task_type=task_type,
            thread_count=thread_count,
        )
        y_pred = np.asarray(model.predict(X_pred), dtype=float)
        metrics = regression_metrics(y_pred_true, y_pred)
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
                **metrics,
            }
        )
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
    step_metrics = pl.DataFrame(step_rows).sort("step_idx")
    feature_policy_detail = (
        pl.concat(feature_policy_frames, how="diagonal_relaxed")
        if feature_policy_frames
        else pl.DataFrame()
    )
    selected_frequency = _selected_feature_frequency_frame(selected_feature_counter, len(step_rows))
    aggregate = regression_metrics(
        predictions["y_true"].to_numpy(),
        predictions["y_pred"].to_numpy(),
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
        "n_requested_steps": int(n_steps),
        "n_completed_steps": int(step_metrics.height),
        "lookback_batches": int(lookback_batches),
        "val_batches": int(val_batches),
        "embargo_batches": int(embargo_batches),
        "feature_count": int(len(feature_cols_ref or [])),
        "model": {
            "type": "CatBoostRegressor",
            "iterations": int(iterations),
            "depth": int(depth),
            "learning_rate": float(learning_rate),
            "task_type": str(task_type),
        },
        "feature_policy": {
            "policy": feature_policy_config.policy,
            "max_features": int(feature_policy_config.max_features),
            "min_abs_spearman": float(feature_policy_config.min_abs_spearman),
            "dedupe_corr_threshold": float(feature_policy_config.dedupe_corr_threshold),
            "clip_quantiles": list(feature_policy_config.clip_quantiles),
            "selected_feature_count_min": int(min(selected_feature_counts)) if selected_feature_counts else 0,
            "selected_feature_count_max": int(max(selected_feature_counts)) if selected_feature_counts else 0,
            "selected_feature_count_mean": _safe_float(np.mean(selected_feature_counts)) if selected_feature_counts else None,
        },
        "aggregate_metrics": aggregate,
        "outputs": {
            "predictions": str(run_dir / "predictions.parquet"),
            "step_metrics": str(run_dir / "step_metrics.parquet"),
            "feature_policy_detail": str(run_dir / "feature_policy_detail.parquet") if not feature_policy_detail.is_empty() else None,
            "selected_feature_frequency": str(run_dir / "selected_feature_frequency.parquet"),
            "feature_policy_summary": str(run_dir / "feature_policy_summary.md"),
            "summary": str(run_dir / "summary.json"),
        },
    }
    predictions.write_parquet(run_dir / "predictions.parquet")
    step_metrics.write_parquet(run_dir / "step_metrics.parquet")
    if not feature_policy_detail.is_empty():
        feature_policy_detail.write_parquet(run_dir / "feature_policy_detail.parquet")
    selected_frequency.write_parquet(run_dir / "selected_feature_frequency.parquet")
    (run_dir / "summary.json").write_text(json.dumps(payload, indent=2, default=str))
    _write_markdown_report(run_dir / "summary.md", payload, step_metrics)
    _write_feature_policy_summary(run_dir / "feature_policy_summary.md", payload, selected_frequency)
    return payload


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
        stability = _stability_score(y, values, segments=3)
        abs_pearson = abs(float(pearson or 0.0))
        abs_spearman = abs(float(spearman or 0.0))
        rank_score = abs_spearman + 0.5 * abs_pearson + 0.25 * max(stability, 0.0)
        scored_rows.append(
            _feature_policy_row(
                feature,
                selected=False,
                drop_reason="candidate",
                pearson=pearson,
                spearman=spearman,
                stability_score=stability,
                rank_score=rank_score,
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
    if len(threshold_rows) >= 50:
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

    detail = pl.DataFrame([*base_rows, *scored_rows])
    return FeaturePolicyResult(
        selected_features=tuple(selected),
        clip_bounds=clip_bounds,
        detail=detail,
    )


def _static_feature_drop_reason(feature: str) -> str | None:
    base = feature.split("__", 1)[-1]
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
    iterations: int,
    depth: int,
    learning_rate: float,
    task_type: str,
    thread_count: int,
) -> Any:
    try:
        from catboost import CatBoostRegressor
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("CatBoost is required for regression walk-forward") from exc

    params = {
        "loss_function": "RMSE",
        "eval_metric": "RMSE",
        "iterations": int(iterations),
        "depth": int(depth),
        "learning_rate": float(learning_rate),
        "random_seed": 42,
        "allow_writing_files": False,
        "verbose": False,
        "thread_count": int(thread_count),
        "task_type": str(task_type).upper(),
    }
    if params["task_type"] == "GPU":
        params["devices"] = "0"
    model = CatBoostRegressor(**params)
    try:
        model.fit(
            X_train,
            y_train,
            eval_set=(X_val, y_val),
            use_best_model=True,
            early_stopping_rounds=50,
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
            early_stopping_rounds=50,
            verbose=False,
        )
        return model


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
            "bias": None,
        }
    error = y_pred - y_true
    ss_res = float(np.sum(error**2))
    ss_tot = float(np.sum((y_true - np.mean(y_true)) ** 2))
    return {
        "rows": n,
        "mae": _safe_float(np.mean(np.abs(error))),
        "rmse": _safe_float(math.sqrt(np.mean(error**2))),
        "median_abs_error": _safe_float(np.median(np.abs(error))),
        "r2": _safe_float(1.0 - ss_res / ss_tot) if ss_tot > 0 else None,
        "pearson": _correlation(y_true, y_pred),
        "spearman": _correlation(_rankdata_average(y_true), _rankdata_average(y_pred)),
        "bias": _safe_float(np.mean(error)),
        "target_mean": _safe_float(np.mean(y_true)),
        "pred_mean": _safe_float(np.mean(y_pred)),
        "target_p50": _safe_float(np.quantile(y_true, 0.50)),
        "pred_p50": _safe_float(np.quantile(y_pred, 0.50)),
        "target_p95": _safe_float(np.quantile(y_true, 0.95)),
        "pred_p95": _safe_float(np.quantile(y_pred, 0.95)),
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


def _correlation(a: np.ndarray, b: np.ndarray) -> float | None:
    if len(a) < 2 or np.std(a) == 0 or np.std(b) == 0:
        return None
    return _safe_float(np.corrcoef(a, b)[0, 1])


def _safe_float(value: Any) -> float | None:
    value = float(value)
    if math.isnan(value) or math.isinf(value):
        return None
    return value


def _target_slug(target_col: str) -> str:
    slug = str(target_col)
    if slug.startswith("target_"):
        slug = slug[len("target_") :]
    slug = re.sub(r"[^A-Za-z0-9_]+", "_", slug).strip("_").lower()
    return slug or "target"


def _write_markdown_report(path: Path, payload: dict[str, Any], step_metrics: pl.DataFrame) -> None:
    metrics = payload["aggregate_metrics"]
    lines = [
        "# Stage-1 Regression Walk-Forward Summary",
        "",
        f"Run ID: `{payload['run_id']}`",
        f"Target: `{payload['target_col']}`",
        f"Asset/root: `{payload['target_asset']} {payload['root']}`",
        f"Completed steps: {payload['n_completed_steps']} / {payload['n_requested_steps']}",
        f"Rows: {metrics.get('rows')}",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    for key in ("mae", "rmse", "median_abs_error", "r2", "pearson", "spearman", "bias", "target_mean", "pred_mean"):
        value = metrics.get(key)
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
    parser.add_argument("--task-type", choices=["CPU", "GPU"], default="CPU")
    parser.add_argument("--thread-count", type=int, default=-1)
    parser.add_argument(
        "--feature-policy",
        choices=[FEATURE_POLICY_FULL, FEATURE_POLICY_TARGET_SPECIFIC_V1],
        default=FEATURE_POLICY_FULL,
    )
    parser.add_argument("--max-features", type=int, default=300)
    parser.add_argument("--min-abs-spearman", type=float, default=0.01)
    parser.add_argument("--dedupe-corr-threshold", type=float, default=0.995)
    parser.add_argument("--clip-quantiles", default="0.001,0.999")
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
            task_type=str(args.task_type),
            thread_count=int(args.thread_count),
            feature_policy_config=feature_policy_config,
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
