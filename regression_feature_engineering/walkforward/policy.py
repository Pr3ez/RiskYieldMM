"""RPF feature policy for walk-forward modeling."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from regression_feature_engineering.walkforward.metrics import _correlation, _rankdata_average


ALL_MANIFEST_FEATURES = "all_manifest_features"
TARGET_SPECIFIC_V2 = "target_specific_v2"
FROZEN_PANEL = "frozen_panel"
ELASTICNET_LOGISTIC_V1 = "elasticnet_logistic_v1"


@dataclass(frozen=True)
class FeaturePolicyConfig:
    policy: str = ALL_MANIFEST_FEATURES
    max_features: int = 300
    min_abs_spearman: float = 0.02
    min_selected_features: int = 20
    dedupe_corr_threshold: float = 0.995
    clip_quantiles: tuple[float, float] = (0.001, 0.999)
    stability_segments: int = 5
    tail_quantile: float = 0.80
    frozen_panel_path: str | None = None
    elasticnet_c: float = 0.1
    elasticnet_l1_ratio: float = 0.5
    elasticnet_max_iter: int = 1000
    elasticnet_tol: float = 0.001
    elasticnet_class_weight: str | None = "balanced"
    elasticnet_coef_epsilon: float = 1e-8
    elasticnet_prefilter_features: int = 0


@dataclass(frozen=True)
class FeaturePolicyResult:
    selected_features: tuple[str, ...]
    clip_bounds: dict[str, tuple[float, float]]
    detail: pl.DataFrame


def select_features(
    train: pl.DataFrame,
    *,
    target_col: str,
    feature_columns: tuple[str, ...],
    config: FeaturePolicyConfig,
) -> FeaturePolicyResult:
    if config.policy == ALL_MANIFEST_FEATURES:
        selected = tuple(feature_columns)
        detail = pl.DataFrame(
            {
                "feature": list(selected),
                "final_status": ["selected_all_manifest"] * len(selected),
                "drop_reason": [None] * len(selected),
            }
        )
        return FeaturePolicyResult(selected_features=selected, clip_bounds={}, detail=detail)
    if config.policy == FROZEN_PANEL:
        selected = load_panel_features(config.frozen_panel_path, feature_columns)
        detail = pl.DataFrame(
            {
                "feature": list(feature_columns),
                "final_status": [
                    "selected_frozen_panel" if feature in selected else "not_in_frozen_panel"
                    for feature in feature_columns
                ],
                "drop_reason": [
                    None if feature in selected else "not_in_frozen_panel"
                    for feature in feature_columns
                ],
            }
        )
        return FeaturePolicyResult(selected_features=selected, clip_bounds={}, detail=detail)
    if config.policy == ELASTICNET_LOGISTIC_V1:
        return select_elasticnet_logistic_features(
            train,
            target_col=target_col,
            feature_columns=feature_columns,
            config=config,
        )
    if config.policy != TARGET_SPECIFIC_V2:
        raise ValueError(f"Unsupported clean RPF feature policy: {config.policy}")
    y = train[target_col].to_numpy().astype("float64")
    y_is_finite = np.isfinite(y)
    y_rank_all = _rankdata_average(y) if y_is_finite.all() else None
    rows: list[dict[str, Any]] = []
    for feature in feature_columns:
        values = train[feature].to_numpy().astype("float64")
        finite = np.isfinite(values) & y_is_finite
        drop_reason = None
        if finite.sum() < 3:
            drop_reason = "too_few_finite_rows"
        elif float(np.std(values[finite])) <= 1e-12:
            drop_reason = "constant"
        pearson = None
        spearman = None
        stability = 0.0
        tail_spread = 0.0
        if drop_reason is None:
            x = values[finite]
            yy = y[finite]
            yy_rank = y_rank_all[finite] if y_rank_all is not None else _rankdata_average(yy)
            pearson = _correlation(yy, x)
            spearman = _correlation(yy_rank, _rankdata_average(x))
            stability = _signed_stability(yy, x, segments=config.stability_segments)
            tail_spread = _tail_spread(yy, x, tail_quantile=config.tail_quantile)
            if abs(float(spearman or 0.0)) < float(config.min_abs_spearman):
                drop_reason = "below_min_abs_spearman"
            elif stability < 0.0:
                drop_reason = "unstable_sign"
        score = abs(float(spearman or 0.0)) + 0.25 * abs(float(pearson or 0.0)) + 0.20 * max(stability, 0.0) + 0.10 * abs(tail_spread)
        rows.append(
            {
                "feature": feature,
                "pearson": pearson,
                "spearman": spearman,
                "abs_spearman": abs(float(spearman or 0.0)),
                "signed_stability": stability,
                "tail_spread": tail_spread,
                "score": score,
                "drop_reason": drop_reason,
            }
        )
    detail = pl.DataFrame(rows, infer_schema_length=None)
    candidates = detail.filter(pl.col("drop_reason").is_null()).sort("score", descending=True)
    if candidates.height < int(config.min_selected_features):
        raise ValueError(
            f"Only {candidates.height} RPF features passed target_specific_v2; "
            f"min_selected_features={config.min_selected_features}"
        )
    ranked = [str(value) for value in candidates["feature"].to_list()]
    selected = _dedupe_features(train, ranked, max_features=config.max_features, threshold=config.dedupe_corr_threshold)
    if len(selected) < int(config.min_selected_features):
        raise ValueError(
            f"Only {len(selected)} RPF features survived dedupe; "
            f"min_selected_features={config.min_selected_features}"
        )
    selected = tuple(selected[: int(config.max_features)])
    bounds = train_clip_bounds(train, selected, config.clip_quantiles)
    detail = detail.with_columns(
        pl.when(pl.col("feature").is_in(selected))
        .then(pl.lit("selected"))
        .otherwise(pl.col("drop_reason"))
        .alias("final_status")
    )
    return FeaturePolicyResult(selected_features=selected, clip_bounds=bounds, detail=detail)


def select_elasticnet_logistic_features(
    train: pl.DataFrame,
    *,
    target_col: str,
    feature_columns: tuple[str, ...],
    config: FeaturePolicyConfig,
) -> FeaturePolicyResult:
    try:
        from sklearn.linear_model import LogisticRegression
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("scikit-learn is required for elasticnet_logistic_v1 feature selection") from exc

    y = train[target_col].to_numpy().astype("int64")
    if len(np.unique(y)) < 2:
        raise ValueError("elasticnet_logistic_v1 requires two train classes")
    X = train.select(feature_columns).to_numpy().astype("float64", copy=False)
    finite_columns = np.isfinite(X).all(axis=0)
    means = np.nanmean(X, axis=0)
    stds = np.nanstd(X, axis=0)
    usable_columns = finite_columns & np.isfinite(means) & np.isfinite(stds) & (stds > 1e-12)
    usable_idx = np.flatnonzero(usable_columns)
    if usable_idx.size < int(config.min_selected_features):
        raise ValueError(
            f"Only {usable_idx.size} usable finite/nonconstant features for elasticnet_logistic_v1; "
            f"min_selected_features={config.min_selected_features}"
        )
    prefilter_rank_by_global_idx, prefilter_score_by_global_idx = elasticnet_prefilter_scores(
        X,
        y,
        usable_idx,
        means,
        stds,
    )
    elasticnet_idx = elasticnet_candidate_indexes(
        usable_idx,
        prefilter_rank_by_global_idx,
        max_candidates=int(config.elasticnet_prefilter_features),
        min_selected_features=int(config.min_selected_features),
    )
    X_use = X[:, elasticnet_idx]
    means_use = means[elasticnet_idx]
    stds_use = stds[elasticnet_idx]
    X_scaled = (X_use - means_use) / stds_use
    X_scaled = np.nan_to_num(X_scaled, copy=False, nan=0.0, posinf=0.0, neginf=0.0)
    class_weight = None if config.elasticnet_class_weight in {None, "", "none", "None"} else str(config.elasticnet_class_weight)
    model = LogisticRegression(
        solver="saga",
        C=float(config.elasticnet_c),
        l1_ratio=float(config.elasticnet_l1_ratio),
        class_weight=class_weight,
        max_iter=int(config.elasticnet_max_iter),
        tol=float(config.elasticnet_tol),
        random_state=42,
    )
    model.fit(X_scaled, y)
    coef = np.asarray(model.coef_[0], dtype=float)
    abs_coef = np.abs(coef)
    selected_mask = abs_coef > float(config.elasticnet_coef_epsilon)
    selected_idx = np.flatnonzero(selected_mask)
    if selected_idx.size < int(config.min_selected_features):
        raise ValueError(
            f"Only {selected_idx.size} nonzero elasticnet_logistic_v1 features; "
            f"min_selected_features={config.min_selected_features}"
        )
    order = selected_idx[np.argsort(abs_coef[selected_idx])[::-1]]
    selected_usable_idx = order[: int(config.max_features)] if int(config.max_features) > 0 else order
    selected_global_idx = elasticnet_idx[selected_usable_idx]
    selected = tuple(str(feature_columns[idx]) for idx in selected_global_idx)
    if len(selected) < int(config.min_selected_features):
        raise ValueError(
            f"Only {len(selected)} elasticnet_logistic_v1 features after max_features cap; "
            f"min_selected_features={config.min_selected_features}"
        )

    usable_rank_by_global_idx = {
        int(elasticnet_idx[idx]): rank
        for rank, idx in enumerate(np.argsort(abs_coef)[::-1], start=1)
    }
    coef_by_global_idx = {int(elasticnet_idx[idx]): float(coef[idx]) for idx in range(len(elasticnet_idx))}
    elasticnet_candidate_set = {int(idx) for idx in elasticnet_idx}
    rows: list[dict[str, Any]] = []
    selected_set = set(selected)
    for idx, feature in enumerate(feature_columns):
        if not bool(finite_columns[idx]):
            drop_reason = "nonfinite"
        elif not np.isfinite(means[idx]) or not np.isfinite(stds[idx]) or float(stds[idx]) <= 1e-12:
            drop_reason = "constant_or_invalid_scale"
        elif str(feature) in selected_set:
            drop_reason = None
        elif int(idx) not in elasticnet_candidate_set:
            drop_reason = "below_elasticnet_prefilter"
        else:
            coef_value = coef_by_global_idx.get(idx, 0.0)
            drop_reason = "zero_coefficient" if abs(coef_value) <= float(config.elasticnet_coef_epsilon) else "below_top_max_features"
        coef_value = coef_by_global_idx.get(idx)
        rows.append(
            {
                "feature": str(feature),
                "coefficient": coef_value,
                "abs_coefficient": None if coef_value is None else abs(float(coef_value)),
                "elasticnet_rank": usable_rank_by_global_idx.get(idx),
                "elasticnet_prefilter_rank": prefilter_rank_by_global_idx.get(idx),
                "elasticnet_prefilter_score": prefilter_score_by_global_idx.get(idx),
                "feature_mean_train": float(means[idx]) if np.isfinite(means[idx]) else None,
                "feature_std_train": float(stds[idx]) if np.isfinite(stds[idx]) else None,
                "final_status": "selected" if str(feature) in selected_set else drop_reason,
                "drop_reason": drop_reason,
            }
        )
    return FeaturePolicyResult(selected_features=selected, clip_bounds={}, detail=pl.DataFrame(rows, infer_schema_length=None))


def elasticnet_prefilter_scores(
    X: np.ndarray,
    y: np.ndarray,
    usable_idx: np.ndarray,
    means: np.ndarray,
    stds: np.ndarray,
) -> tuple[dict[int, int], dict[int, float]]:
    pos = y == 1
    neg = y == 0
    if int(pos.sum()) == 0 or int(neg.sum()) == 0:
        return {int(idx): rank for rank, idx in enumerate(usable_idx, start=1)}, {int(idx): 0.0 for idx in usable_idx}
    X_use = X[:, usable_idx]
    X_scaled = (X_use - means[usable_idx]) / stds[usable_idx]
    X_scaled = np.nan_to_num(X_scaled, copy=False, nan=0.0, posinf=0.0, neginf=0.0)
    scores = np.abs(np.mean(X_scaled[pos], axis=0) - np.mean(X_scaled[neg], axis=0))
    order = np.argsort(scores)[::-1]
    rank_by_idx = {int(usable_idx[idx]): rank for rank, idx in enumerate(order, start=1)}
    score_by_idx = {int(usable_idx[idx]): float(scores[idx]) for idx in range(len(usable_idx))}
    return rank_by_idx, score_by_idx


def elasticnet_candidate_indexes(
    usable_idx: np.ndarray,
    prefilter_rank_by_global_idx: dict[int, int],
    *,
    max_candidates: int,
    min_selected_features: int,
) -> np.ndarray:
    if int(max_candidates) <= 0 or int(max_candidates) >= int(usable_idx.size):
        return usable_idx
    candidate_count = max(int(max_candidates), int(min_selected_features))
    ordered = sorted((int(idx) for idx in usable_idx), key=lambda idx: prefilter_rank_by_global_idx.get(idx, 10**12))
    return np.asarray(ordered[:candidate_count], dtype=int)


def load_panel_features(path_value: str | Path | None, feature_columns: tuple[str, ...]) -> tuple[str, ...]:
    if not path_value:
        raise ValueError("RPF panel path is required")
    path = Path(path_value)
    if not path.exists():
        raise FileNotFoundError(f"Frozen RPF panel not found: {path}")
    payload = json.loads(path.read_text())
    selected = tuple(str(feature) for feature in payload.get("selected_features", ()))
    if not selected:
        raise ValueError(f"Frozen RPF panel has no selected_features: {path}")
    allowed = set(feature_columns)
    missing = [feature for feature in selected if feature not in allowed]
    if missing:
        raise ValueError(f"Frozen RPF panel contains features outside current feature universe: {missing[:5]}")
    return selected


def train_clip_bounds(
    frame: pl.DataFrame,
    features: tuple[str, ...] | list[str],
    quantiles: tuple[float, float],
) -> dict[str, tuple[float, float]]:
    low_q, high_q = quantiles
    bounds: dict[str, tuple[float, float]] = {}
    for feature in features:
        series = frame[feature].drop_nulls()
        low = float(series.quantile(low_q))
        high = float(series.quantile(high_q))
        if not np.isfinite(low) or not np.isfinite(high) or low > high:
            low, high = 0.0, 0.0
        bounds[str(feature)] = (low, high)
    return bounds


def apply_clip_bounds(frame: pl.DataFrame, bounds: dict[str, tuple[float, float]]) -> pl.DataFrame:
    exprs = [pl.col(feature).clip(low, high).alias(feature) for feature, (low, high) in bounds.items()]
    return frame.with_columns(exprs) if exprs else frame


def _dedupe_features(frame: pl.DataFrame, ranked: list[str], *, max_features: int, threshold: float) -> list[str]:
    selected: list[str] = []
    arrays: dict[str, np.ndarray] = {}
    for feature in ranked:
        values = frame[feature].to_numpy().astype("float64")
        keep = True
        for existing in selected:
            corr = _correlation(values, arrays[existing])
            if corr is not None and abs(float(corr)) >= float(threshold):
                keep = False
                break
        if keep:
            selected.append(feature)
            arrays[feature] = values
        if len(selected) >= int(max_features):
            break
    return selected


def _signed_stability(y: np.ndarray, x: np.ndarray, *, segments: int) -> float:
    if segments <= 1 or len(y) < segments * 3:
        return 0.0
    scores: list[float] = []
    global_corr = _correlation(_rankdata_average(y), _rankdata_average(x))
    if global_corr is None:
        return -1.0
    global_sign = np.sign(global_corr)
    for idx in np.array_split(np.arange(len(y)), int(segments)):
        if len(idx) < 3:
            continue
        corr = _correlation(_rankdata_average(y[idx]), _rankdata_average(x[idx]))
        if corr is None:
            continue
        scores.append(float(np.sign(corr) == global_sign))
    return float(np.mean(scores)) if scores else -1.0


def _tail_spread(y: np.ndarray, x: np.ndarray, *, tail_quantile: float) -> float:
    cut = float(np.quantile(y, tail_quantile))
    top = x[y >= cut]
    rest = x[y < cut]
    if len(top) == 0 or len(rest) == 0:
        return 0.0
    scale = float(np.std(x))
    if scale == 0.0:
        return 0.0
    return float((np.mean(top) - np.mean(rest)) / scale)
