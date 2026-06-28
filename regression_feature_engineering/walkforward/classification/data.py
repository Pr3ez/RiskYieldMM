"""Data loading and row conversion for RPF binary classification."""

from __future__ import annotations

from typing import Any

import numpy as np
import polars as pl

from regression_feature_engineering.walkforward.classification.targets import DOWN_EXTREME, UP_EXTREME, binary_target_expr
from regression_feature_engineering.walkforward.data import RPFDataContext, VALID_COL


def load_joined_classification_batches(
    context: RPFDataContext,
    batch_ids: tuple[int, ...] | list[int],
    *,
    feature_columns: tuple[str, ...],
    target_col: str,
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
            .with_columns(binary_target_expr(target_col))
            .drop(VALID_COL)
        )
        frames.append(joined)
    out = pl.concat(frames, how="vertical") if frames else pl.DataFrame()
    if out.is_empty():
        raise ValueError(f"Joined RPF classification batches are empty: {batch_ids}")
    return out.sort(["batch_id", "timestamp"])


def classification_numpy(frame: pl.DataFrame, *, target_col: str, features: tuple[str, ...]) -> tuple[np.ndarray, np.ndarray]:
    X, y, _ = classification_numpy_with_meta(frame, target_col=target_col, features=features)
    return X, y


def classification_numpy_with_meta(
    frame: pl.DataFrame,
    *,
    target_col: str,
    features: tuple[str, ...],
) -> tuple[np.ndarray, np.ndarray, pl.DataFrame]:
    model_frame = frame.select([target_col, *features]).drop_nulls([target_col, *features])
    X = model_frame.select(features).to_numpy().astype("float64")
    y = model_frame[target_col].to_numpy().astype("int64")
    mask = np.isfinite(X).all(axis=1)
    meta = (
        frame.select(["timestamp", "batch_id", target_col, *features])
        .drop_nulls([target_col, *features])
        .select(["timestamp", "batch_id"])
        .with_columns(pl.Series("_model_row_mask", mask))
        .filter(pl.col("_model_row_mask"))
        .drop("_model_row_mask")
    )
    return X[mask], y[mask], meta


def classification_numpy_with_extra(
    frame: pl.DataFrame,
    *,
    target_col: str,
    features: tuple[str, ...],
    extra_features: tuple[str, ...],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, pl.DataFrame]:
    """Return aligned model and extra feature matrices.

    This is used when CatBoost's tabular branch and the CNN sequence branch
    intentionally consume different feature panels. Rows are kept only when
    target, tabular features, and extra sequence features are all finite, so
    both matrices describe the exact same anchors.
    """

    all_features = tuple(dict.fromkeys((*features, *extra_features)))
    model_frame = frame.select([target_col, *all_features]).drop_nulls([target_col, *all_features])
    X = model_frame.select(features).to_numpy().astype("float64")
    X_extra = model_frame.select(extra_features).to_numpy().astype("float64")
    y = model_frame[target_col].to_numpy().astype("int64")
    mask = np.isfinite(X).all(axis=1) & np.isfinite(X_extra).all(axis=1)
    meta = (
        frame.select(["timestamp", "batch_id", target_col, *all_features])
        .drop_nulls([target_col, *all_features])
        .select(["timestamp", "batch_id"])
        .with_columns(pl.Series("_model_row_mask", mask))
        .filter(pl.col("_model_row_mask"))
        .drop("_model_row_mask")
    )
    return X[mask], X_extra[mask], y[mask], meta


def classification_score_rows(
    *,
    meta: pl.DataFrame,
    y_true: np.ndarray,
    prob: np.ndarray,
    threshold: float,
    pred: np.ndarray | None = None,
    max_signals: int = 0,
    decision_policy: str = "",
    decision_policy_live_safe: bool | None = None,
    target_col: str,
    step_idx: int,
    pred_batch_id: int,
    split: str,
) -> list[dict[str, Any]]:
    if pred is None:
        pred = (np.asarray(prob, dtype=float) >= float(threshold)).astype(int)
    else:
        pred = np.asarray(pred, dtype=int)
    timestamps = meta["timestamp"].to_list()
    batch_ids = meta["batch_id"].to_list()
    rows: list[dict[str, Any]] = []
    for idx, value in enumerate(prob):
        rows.append(
            {
                "split": split,
                "target_col": target_col,
                "step_idx": int(step_idx),
                "pred_batch_id": int(pred_batch_id),
                "timestamp": timestamps[idx],
                "batch_id": int(batch_ids[idx]),
                "target": int(y_true[idx]),
                "prob": float(value),
                "predicted_positive": int(pred[idx]),
                "threshold": float(threshold),
                "max_signals": int(max_signals),
                "decision_policy": str(decision_policy),
                "decision_policy_live_safe": decision_policy_live_safe,
            }
        )
    return rows
