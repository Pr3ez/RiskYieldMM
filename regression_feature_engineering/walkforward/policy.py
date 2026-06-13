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
        selected = _load_frozen_panel_features(config.frozen_panel_path, feature_columns)
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
    detail = pl.DataFrame(rows)
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


def _load_frozen_panel_features(path_value: str | None, feature_columns: tuple[str, ...]) -> tuple[str, ...]:
    if not path_value:
        raise ValueError("feature_policy=frozen_panel requires policy.frozen_panel_path")
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
