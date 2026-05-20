"""Stage-1 label-anomaly validation runner.

This script promotes the exploratory `notebooks/noise_removal.ipynb` workflow
into a reproducible experiment runner. It reads merged Stage-1 multi-asset
datasets, derives parent-conditioned anomaly labels from time-safe OOF
predictions, and compares the original 4-class target against experimental
8-class anomaly models collapsed back to the original four classes.

The runner is intentionally conservative:

- `target_4class` is never overwritten.
- OOF scoring uses expanding time folds inside the training split.
- Suspicious same-direction rows can become `k + 4` anomaly labels.
- High-confidence opposite-direction rows are exported for review instead of
  being automatically flipped.
"""

from __future__ import annotations

import argparse
import gc
import json
import math
import sys
import time
import warnings
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import polars as pl
from sklearn.cluster import MiniBatchKMeans
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, f1_score, log_loss
from sklearn.preprocessing import StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.feature_engineering.htf_asset_registry import normalize_htf_asset_id
from scripts.htf_backtest.catboost.stage1_multiasset_dataset import (
    STAGE1_MULTIASSET_ROOT_LAYOUTS,
    build_context_set_hash,
    parse_stage1_context_assets,
    parse_stage1_target_assets,
)
from scripts.htf_backtest.catboost.utils import get_feature_columns


TARGET_COL = "target_4class"
TF = "1m"
FEATURE_TARGET_COL = TARGET_COL
PRIMARY_DETECTOR = "full_hybrid"
PRIMARY_OPPOSITE_POLICY = "exclude_review"
PRIMARY_THRESHOLD_PCT = 0.03

CLASS_NAMES_4 = {
    0: "DOWN_BALANCED",
    1: "DOWN_EXPANSION",
    2: "UP_BALANCED",
    3: "UP_EXPANSION",
}
CLASS_NAMES_8 = {
    **CLASS_NAMES_4,
    4: "DOWN_BALANCED_ANOMALY",
    5: "DOWN_EXPANSION_ANOMALY",
    6: "UP_BALANCED_ANOMALY",
    7: "UP_EXPANSION_ANOMALY",
}
DIRECTION_NAMES = {0: "DOWN", 1: "UP"}

DETECTOR_WEIGHTS: dict[str, dict[str, float]] = {
    "label_conflict": {
        "label_conflict_score_rank": 1.0,
    },
    "conflict_temporal": {
        "label_conflict_score_rank": 0.75,
        "temporal_inconsistency_rank": 0.25,
    },
    "conflict_temporal_outlier": {
        "label_conflict_score_rank": 0.60,
        "temporal_inconsistency_rank": 0.20,
        "class_conditional_outlier_score_rank": 0.20,
    },
    "full_hybrid": {
        "label_conflict_score_rank": 0.50,
        "ensemble_disagreement_proxy_rank": 0.20,
        "temporal_inconsistency_rank": 0.15,
        "class_conditional_outlier_score_rank": 0.15,
    },
}

OPPOSITE_POLICIES = ("keep_clean", "low_weight", "exclude_review")
MODEL_CHOICES = ("catboost", "structured")


@dataclass(frozen=True)
class AblationConfig:
    """One anomaly-labeling configuration."""

    threshold_pct: float
    detector: str
    opposite_policy: str

    @property
    def config_id(self) -> str:
        pct = f"{100.0 * self.threshold_pct:.1f}".replace(".", "p")
        return f"thr{pct}_{self.detector}_{self.opposite_policy}"

    @property
    def is_primary(self) -> bool:
        return (
            math.isclose(self.threshold_pct, PRIMARY_THRESHOLD_PCT)
            and self.detector == PRIMARY_DETECTOR
            and self.opposite_policy == PRIMARY_OPPOSITE_POLICY
        )


@dataclass(frozen=True)
class ExperimentParams:
    """Resolved runtime controls used in manifests and tests."""

    max_rows: int | None
    max_features: int
    oof_folds: int
    min_oof_train_batches: int
    outlier_feature_count: int
    opposite_high_confidence: float
    random_seed: int
    catboost_iterations: int
    catboost_depth: int
    catboost_learning_rate: float
    catboost_thread_count: int
    structured_epochs: int
    structured_batch_size: int
    structured_learning_rate: float
    structured_hidden_dim: int
    structured_dropout: float
    calibration_bins: int


@dataclass(frozen=True)
class MergedDatasetPaths:
    """Resolved paths for one target/root/context merged Stage-1 dataset."""

    manifest_path: Path
    feature_dir: Path
    label_dir: Path
    manifest: dict[str, Any]


@dataclass
class LoadedUnitData:
    """Selected-width in-memory data for one target/root experiment unit."""

    pdf: pd.DataFrame
    train_df: pd.DataFrame
    val_df: pd.DataFrame
    test_df: pd.DataFrame
    batch_meta: pd.DataFrame
    selected_features: list[str]
    feature_variance: pd.Series
    split_summary: pd.DataFrame


@dataclass
class TabularModelBundle:
    """Fitted tabular classifier plus preprocessing needed for prediction."""

    model: Any
    imputer: SimpleImputer
    n_classes: int
    backend: str


class ConstantProbabilityModel:
    """Degenerate classifier used when a training slice has one class."""

    def __init__(self, class_id: int) -> None:
        self.classes_ = np.array([int(class_id)], dtype=int)
        self.class_id = int(class_id)

    def predict_proba(self, x: np.ndarray) -> np.ndarray:
        return np.ones((len(x), 1), dtype=np.float64)


def collapse_8_to_4(values: Iterable[int] | np.ndarray) -> np.ndarray:
    """Collapse anomaly leaves back to their parent 4-class labels."""
    arr = np.asarray(values, dtype=int)
    return np.where(arr >= 4, arr - 4, arr)


def to_direction(values: Iterable[int] | np.ndarray) -> np.ndarray:
    """Return 0 for DOWN classes and 1 for UP classes."""
    arr4 = collapse_8_to_4(values)
    return np.where(np.isin(arr4, [0, 1]), 0, 1)


def to_regime(values: Iterable[int] | np.ndarray) -> np.ndarray:
    """Return 0 for BALANCED classes and 1 for EXPANSION classes."""
    arr4 = collapse_8_to_4(values)
    return np.where(np.isin(arr4, [0, 2]), 0, 1)


def collapse_proba_8_to_4(proba: np.ndarray) -> np.ndarray:
    """Collapse 8-class probabilities into parent 4-class probabilities."""
    proba = np.asarray(proba, dtype=np.float64)
    if proba.shape[1] == 4:
        out = proba.copy()
    else:
        out = np.zeros((proba.shape[0], 4), dtype=np.float64)
        out[:, 0] = proba[:, 0] + proba[:, 4]
        out[:, 1] = proba[:, 1] + proba[:, 5]
        out[:, 2] = proba[:, 2] + proba[:, 6]
        out[:, 3] = proba[:, 3] + proba[:, 7]
    row_sum = out.sum(axis=1, keepdims=True)
    return np.divide(out, row_sum, out=np.full_like(out, 0.25), where=row_sum > 0)


def multiclass_brier_score(y_true4: np.ndarray, proba4: np.ndarray) -> float:
    """Mean multiclass Brier score for the collapsed 4-class task."""
    y_true4 = np.asarray(y_true4, dtype=int)
    proba4 = collapse_proba_8_to_4(proba4)
    one_hot = np.zeros_like(proba4, dtype=np.float64)
    one_hot[np.arange(len(y_true4)), y_true4] = 1.0
    return float(np.mean(np.sum((proba4 - one_hot) ** 2, axis=1)))


def expected_calibration_error(
    y_true4: np.ndarray,
    proba4: np.ndarray,
    *,
    n_bins: int = 15,
) -> tuple[float, pd.DataFrame]:
    """Compute confidence-based ECE and reliability-bin diagnostics."""
    y_true4 = np.asarray(y_true4, dtype=int)
    proba4 = collapse_proba_8_to_4(proba4)
    confidence = proba4.max(axis=1)
    pred = proba4.argmax(axis=1)
    correct = (pred == y_true4).astype(float)
    bins = np.linspace(0.0, 1.0, int(n_bins) + 1)
    rows: list[dict[str, Any]] = []
    ece = 0.0
    for idx in range(n_bins):
        left = bins[idx]
        right = bins[idx + 1]
        if idx == n_bins - 1:
            mask = (confidence >= left) & (confidence <= right)
        else:
            mask = (confidence >= left) & (confidence < right)
        count = int(mask.sum())
        if count == 0:
            rows.append(
                {
                    "bin": idx,
                    "left": float(left),
                    "right": float(right),
                    "count": 0,
                    "accuracy": np.nan,
                    "confidence": np.nan,
                    "abs_gap": np.nan,
                }
            )
            continue
        acc = float(correct[mask].mean())
        conf = float(confidence[mask].mean())
        gap = abs(acc - conf)
        ece += (count / max(1, len(y_true4))) * gap
        rows.append(
            {
                "bin": idx,
                "left": float(left),
                "right": float(right),
                "count": count,
                "accuracy": acc,
                "confidence": conf,
                "abs_gap": float(gap),
            }
        )
    return float(ece), pd.DataFrame(rows)


def compute_eval_metrics(
    y_true4: np.ndarray,
    pred_labels: np.ndarray,
    pred_proba: np.ndarray | None = None,
    *,
    calibration_bins: int = 15,
) -> tuple[dict[str, float], pd.DataFrame | None]:
    """Primary model-quality metrics, always evaluated on collapsed classes."""
    y_true4 = np.asarray(y_true4, dtype=int)
    pred4 = collapse_8_to_4(pred_labels)
    true_dir = to_direction(y_true4)
    pred_dir = to_direction(pred4)
    metrics: dict[str, float] = {
        "collapsed_4_accuracy": float(accuracy_score(y_true4, pred4)),
        "macro_f1_4": float(
            f1_score(
                y_true4,
                pred4,
                labels=[0, 1, 2, 3],
                average="macro",
                zero_division=0,
            )
        ),
        "direction_accuracy": float(accuracy_score(true_dir, pred_dir)),
        "cross_direction_error": float(np.mean(true_dir != pred_dir)),
    }
    bins_df: pd.DataFrame | None = None
    if pred_proba is not None:
        proba4 = collapse_proba_8_to_4(pred_proba)
        metrics["logloss_4"] = float(log_loss(y_true4, proba4, labels=[0, 1, 2, 3]))
        metrics["brier_4"] = multiclass_brier_score(y_true4, proba4)
        ece, bins_df = expected_calibration_error(
            y_true4,
            proba4,
            n_bins=calibration_bins,
        )
        metrics["ece_4"] = ece
    metrics["primary_score"] = float(
        metrics["collapsed_4_accuracy"]
        - 3.0 * metrics["cross_direction_error"]
        - 0.25 * metrics.get("ece_4", 0.0)
    )
    return metrics, bins_df


def make_expanding_oof_folds(
    batch_ids: Iterable[int],
    *,
    n_folds: int,
    min_train_batches: int,
) -> list[tuple[int, np.ndarray, np.ndarray]]:
    """Create expanding OOF folds where every validation batch is future data."""
    batches = np.array(sorted(set(int(x) for x in batch_ids)), dtype=int)
    if len(batches) <= min_train_batches + n_folds:
        min_train_batches = max(3, len(batches) // 3)
    val_span = max(1, (len(batches) - min_train_batches) // max(n_folds, 1))
    folds: list[tuple[int, np.ndarray, np.ndarray]] = []
    start = min_train_batches
    fold_id = 0
    while start < len(batches) and fold_id < n_folds:
        end = min(len(batches), start + val_span)
        train_part = batches[:start]
        val_part = batches[start:end]
        if len(train_part) and len(val_part):
            if int(train_part.max()) >= int(val_part.min()):
                raise AssertionError("OOF fold violates chronological ordering")
            folds.append((fold_id, train_part, val_part))
        start = end
        fold_id += 1
    return folds


def apply_detector_score(score_df: pd.DataFrame, detector: str) -> pd.DataFrame:
    """Apply one named detector-weight preset to precomputed rank signals."""
    if detector not in DETECTOR_WEIGHTS:
        known = ", ".join(sorted(DETECTOR_WEIGHTS))
        raise ValueError(f"Unknown detector {detector!r}. Known detectors: {known}")
    out = score_df.copy()
    score = np.zeros(len(out), dtype=np.float64)
    for col, weight in DETECTOR_WEIGHTS[detector].items():
        score += float(weight) * out[col].astype(float).to_numpy()
    out["noise_score"] = score
    out["detector"] = detector
    return out


def apply_anomaly_decisions(
    score_df: pd.DataFrame,
    *,
    threshold_pct: float,
    opposite_policy: str,
    opposite_high_confidence: float,
    target_col: str = TARGET_COL,
) -> pd.DataFrame:
    """Assign anomaly/review training actions from class-local noise scores."""
    if opposite_policy not in OPPOSITE_POLICIES:
        known = ", ".join(OPPOSITE_POLICIES)
        raise ValueError(f"Unknown opposite policy {opposite_policy!r}: {known}")
    if not (0.0 < float(threshold_pct) < 1.0):
        raise ValueError("threshold_pct must be between 0 and 1")

    out = score_df.copy()
    thresholds = (
        out.groupby(target_col)["noise_score"]
        .quantile(1.0 - float(threshold_pct))
        .rename("class_threshold")
        .reset_index()
    )
    out = out.merge(thresholds, on=target_col, how="left")
    out["suspicious"] = out["noise_score"] >= out["class_threshold"]
    out["true_direction"] = to_direction(out[target_col].to_numpy())
    out["pred_direction"] = to_direction(out["pred_label"].to_numpy())
    out["opposite_direction_prediction"] = (
        out["true_direction"] != out["pred_direction"]
    )
    out["high_conf_opposite"] = (
        out["suspicious"]
        & out["opposite_direction_prediction"]
        & (out["model_confidence"] >= float(opposite_high_confidence))
    )
    out["same_direction_suspicious"] = (
        out["suspicious"] & ~out["opposite_direction_prediction"]
    )
    out["low_conf_opposite_suspicious"] = (
        out["suspicious"]
        & out["opposite_direction_prediction"]
        & ~out["high_conf_opposite"]
    )

    out["training_action"] = "clean"
    out["target_8class_anomaly"] = out[target_col].astype(int)
    out["sample_weight_anomaly"] = 1.0

    same_mask = out["same_direction_suspicious"]
    out.loc[same_mask, "training_action"] = "same_parent_anomaly"
    out.loc[same_mask, "target_8class_anomaly"] = (
        out.loc[same_mask, target_col].astype(int) + 4
    )

    opposite_mask = out["suspicious"] & out["opposite_direction_prediction"]
    if opposite_policy == "keep_clean":
        out.loc[opposite_mask, "training_action"] = "opposite_keep_clean"
    elif opposite_policy == "low_weight":
        out.loc[opposite_mask, "training_action"] = "opposite_low_weight"
        out.loc[opposite_mask, "sample_weight_anomaly"] = 0.35
    else:
        high_mask = out["high_conf_opposite"]
        low_mask = out["low_conf_opposite_suspicious"]
        out.loc[low_mask, "training_action"] = "low_weight_opposite"
        out.loc[low_mask, "sample_weight_anomaly"] = 0.35
        out.loc[high_mask, "training_action"] = "review_exclude"
        out.loc[high_mask, "sample_weight_anomaly"] = 0.0

    out["threshold_pct"] = float(threshold_pct)
    out["opposite_policy"] = opposite_policy
    return out


def attach_anomaly_decisions(
    train_df: pd.DataFrame,
    decisions: pd.DataFrame,
    *,
    target_col: str = TARGET_COL,
) -> pd.DataFrame:
    """Attach OOF-derived decisions to all train rows; unscored rows stay clean."""
    cols = [
        "row_id",
        "noise_score",
        "class_threshold",
        "detector",
        "threshold_pct",
        "opposite_policy",
        "training_action",
        "target_8class_anomaly",
        "sample_weight_anomaly",
        "high_conf_opposite",
        "opposite_direction_prediction",
    ]
    out = train_df.merge(decisions[cols], on="row_id", how="left")
    out["training_action"] = out["training_action"].fillna("clean_no_oof")
    out["target_8class_anomaly"] = (
        out["target_8class_anomaly"].fillna(out[target_col]).astype(int)
    )
    out["sample_weight_anomaly"] = (
        out["sample_weight_anomaly"].fillna(1.0).astype(float)
    )
    out["noise_score"] = out["noise_score"].fillna(np.nan)
    out["target_8class_name"] = out["target_8class_anomaly"].map(CLASS_NAMES_8)
    return out


def train_model(
    x_df: pd.DataFrame,
    y: np.ndarray,
    *,
    n_classes: int,
    params: ExperimentParams,
    sample_weight: np.ndarray | None = None,
    seed: int | None = None,
) -> TabularModelBundle:
    """Fit CatBoost with a sklearn fallback for lightweight environments."""
    seed = params.random_seed if seed is None else int(seed)
    x_df = x_df.replace([np.inf, -np.inf], np.nan)
    imputer = SimpleImputer(strategy="median")
    x = imputer.fit_transform(x_df).astype(np.float32, copy=False)
    y = np.asarray(y, dtype=int)
    unique = np.unique(y)
    if len(unique) == 1:
        return TabularModelBundle(
            model=ConstantProbabilityModel(int(unique[0])),
            imputer=imputer,
            n_classes=int(n_classes),
            backend="constant",
        )
    try:
        from catboost import CatBoostClassifier

        model = CatBoostClassifier(
            loss_function="MultiClass",
            iterations=int(params.catboost_iterations),
            depth=int(params.catboost_depth),
            learning_rate=float(params.catboost_learning_rate),
            random_seed=seed,
            verbose=False,
            allow_writing_files=False,
            task_type="CPU",
            thread_count=int(params.catboost_thread_count),
        )
        model.fit(x, y, sample_weight=sample_weight)
        backend = "catboost"
    except Exception as exc:  # pragma: no cover - exercised only without CatBoost.
        warnings.warn(
            f"CatBoost unavailable or failed ({exc}); using HistGradientBoosting.",
            RuntimeWarning,
            stacklevel=2,
        )
        model = HistGradientBoostingClassifier(
            max_iter=max(60, int(params.catboost_iterations)),
            learning_rate=float(params.catboost_learning_rate),
            max_leaf_nodes=31,
            random_state=seed,
        )
        model.fit(x, y, sample_weight=sample_weight)
        backend = "hist_gradient_boosting"
    return TabularModelBundle(
        model=model,
        imputer=imputer,
        n_classes=int(n_classes),
        backend=backend,
    )


def predict_proba_model(bundle: TabularModelBundle, x_df: pd.DataFrame) -> np.ndarray:
    """Predict normalized probabilities with stable class-column ordering."""
    x_df = x_df.replace([np.inf, -np.inf], np.nan)
    x = bundle.imputer.transform(x_df).astype(np.float32, copy=False)
    raw = np.asarray(bundle.model.predict_proba(x), dtype=np.float64)
    full = np.zeros((len(x_df), int(bundle.n_classes)), dtype=np.float64)
    classes = getattr(bundle.model, "classes_", np.arange(raw.shape[1]))
    for raw_idx, cls in enumerate(np.asarray(classes, dtype=int)):
        if 0 <= cls < bundle.n_classes:
            full[:, cls] = raw[:, raw_idx]
    row_sum = full.sum(axis=1, keepdims=True)
    return np.divide(
        full,
        row_sum,
        out=np.full_like(full, 1.0 / max(1, bundle.n_classes)),
        where=row_sum > 0,
    )


def resolve_merged_dataset(
    *,
    target_asset: str,
    context_assets: tuple[str, ...],
    root_key: str,
    dataset_dir: Path,
) -> MergedDatasetPaths:
    """Resolve the manifest and batch roots for one merged dataset."""
    target_asset = normalize_htf_asset_id(target_asset)
    context_hash = build_context_set_hash(
        target_asset=target_asset,
        context_assets=context_assets,
    )
    layout = STAGE1_MULTIASSET_ROOT_LAYOUTS[root_key]
    manifest_path = (
        Path(dataset_dir)
        / target_asset.lower()
        / context_hash
        / layout.root_id
        / "manifest.json"
    )
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Merged dataset manifest not found: {manifest_path}\n"
            "Build it first, for example:\n"
            "python scripts/analysis/htf_stage1_regime_family_walkforward.py "
            "--build-merged-dataset "
            f"--target-assets {target_asset} "
            "--context-assets core-ex-target "
            f"--roots {root_key} --plan-only"
        )
    manifest = json.loads(manifest_path.read_text())
    feature_dir = (
        Path(manifest["output_paths"]["features_dir"]) / TF / FEATURE_TARGET_COL
    )
    label_dir = Path(manifest["output_paths"]["labels_dir"]) / TF
    return MergedDatasetPaths(
        manifest_path=manifest_path,
        feature_dir=feature_dir,
        label_dir=label_dir,
        manifest=manifest,
    )


def _batch_id_from_path(path: Path) -> int:
    stem = path.stem
    if not stem.startswith("batch_"):
        raise ValueError(f"Unexpected batch filename: {path.name}")
    return int(stem.removeprefix("batch_"))


def _select_feature_paths_for_row_cap(
    metadata: pd.DataFrame,
    *,
    max_rows: int | None,
) -> pd.DataFrame:
    """Keep latest batches needed for `max_rows`, preserving chronological order."""
    if max_rows is None or metadata["feature_rows"].sum() <= max_rows:
        return metadata.copy()
    chosen: list[int] = []
    running = 0
    for idx, row in metadata.sort_values("batch_id", ascending=False).iterrows():
        chosen.append(idx)
        running += int(row["feature_rows"])
        if running >= int(max_rows):
            break
    return metadata.loc[sorted(chosen)].sort_values("batch_id").reset_index(drop=True)


def discover_batch_metadata(
    *,
    feature_dir: Path,
    label_dir: Path,
    max_rows: int | None,
) -> tuple[pd.DataFrame, list[str]]:
    """Scan merged batch files without materializing model features."""
    feature_paths = sorted(Path(feature_dir).glob("batch_*.parquet"))
    if not feature_paths:
        raise FileNotFoundError(f"No feature batches found under {feature_dir}")

    feature_schema = pl.read_parquet(feature_paths[0], n_rows=0)
    feature_cols = get_feature_columns(feature_schema, target_col=TARGET_COL)
    records: list[dict[str, Any]] = []
    for feature_path in feature_paths:
        label_path = Path(label_dir) / feature_path.name
        if not label_path.exists():
            raise FileNotFoundError(f"Missing label batch for {feature_path.name}")
        meta = pl.read_parquet(feature_path, columns=["timestamp", "batch_id"])
        label_schema = pl.read_parquet(label_path, n_rows=0).schema
        label_cols = ["timestamp", "batch_id", TARGET_COL]
        optional_label_cols = [
            col
            for col in ["target_name", "target_name_4", "direction_4"]
            if col in label_schema
        ]
        labels = pl.read_parquet(label_path, columns=[*label_cols, *optional_label_cols])
        batch_id = _batch_id_from_path(feature_path)
        records.append(
            {
                "batch_id": int(batch_id),
                "feature_path": str(feature_path),
                "label_path": str(label_path),
                "feature_rows": int(meta.height),
                "label_rows": int(labels.height),
                "timestamp_min": meta["timestamp"].min(),
                "timestamp_max": meta["timestamp"].max(),
            }
        )
    metadata = pd.DataFrame(records).sort_values("batch_id").reset_index(drop=True)
    metadata = _select_feature_paths_for_row_cap(metadata, max_rows=max_rows)
    return metadata, feature_cols


def assign_chronological_splits(
    batch_meta: pd.DataFrame,
    *,
    train_share: float = 0.60,
    val_share: float = 0.20,
) -> tuple[pd.DataFrame, set[int], set[int], set[int]]:
    """Assign train/val/test splits by sorted batch ids."""
    out = batch_meta.copy()
    unique_batches = np.array(sorted(out["batch_id"].unique()), dtype=int)
    if len(unique_batches) < 10:
        raise RuntimeError("Not enough batches for chronological train/val/test split")
    train_cut = int(len(unique_batches) * train_share)
    val_cut = int(len(unique_batches) * (train_share + val_share))
    train_batches = set(int(x) for x in unique_batches[:train_cut])
    val_batches = set(int(x) for x in unique_batches[train_cut:val_cut])
    test_batches = set(int(x) for x in unique_batches[val_cut:])
    out["split"] = np.select(
        [
            out["batch_id"].isin(train_batches),
            out["batch_id"].isin(val_batches),
            out["batch_id"].isin(test_batches),
        ],
        ["train", "val", "test"],
        default="unused",
    )
    return out, train_batches, val_batches, test_batches


def select_train_variance_features(
    batch_meta: pd.DataFrame,
    feature_cols: list[str],
    *,
    max_features: int,
) -> pd.Series:
    """Compute train-only variance one parquet batch at a time."""
    n_features = len(feature_cols)
    if n_features == 0:
        raise RuntimeError("No model feature columns found")
    feature_sum = np.zeros(n_features, dtype=np.float64)
    feature_sumsq = np.zeros(n_features, dtype=np.float64)
    feature_count = np.zeros(n_features, dtype=np.float64)
    train_paths = batch_meta.loc[batch_meta["split"] == "train", "feature_path"].to_list()
    if not train_paths:
        raise RuntimeError("No train batches available for feature selection")
    for raw_path in train_paths:
        batch = pl.read_parquet(Path(raw_path), columns=feature_cols)
        arr = batch.to_numpy().astype(np.float64, copy=False)
        finite = np.isfinite(arr)
        arr_clean = np.where(finite, arr, 0.0)
        feature_sum += arr_clean.sum(axis=0)
        feature_sumsq += (arr_clean * arr_clean).sum(axis=0)
        feature_count += finite.sum(axis=0)
        del batch, arr, finite, arr_clean
    valid = feature_count > 1
    variance_values = np.full(n_features, np.nan, dtype=np.float64)
    variance_values[valid] = (
        feature_sumsq[valid] - (feature_sum[valid] ** 2 / feature_count[valid])
    ) / (feature_count[valid] - 1.0)
    variance = (
        pd.Series(variance_values, index=feature_cols, dtype="float64")
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
        .sort_values(ascending=False)
    )
    if variance.empty:
        raise RuntimeError("Train-only variance selection found no usable features")
    return variance.head(min(int(max_features), len(variance)))


def load_selected_unit_data(
    *,
    paths: MergedDatasetPaths,
    params: ExperimentParams,
) -> LoadedUnitData:
    """Load selected-width merged data for one target/root."""
    batch_meta, feature_cols_all = discover_batch_metadata(
        feature_dir=paths.feature_dir,
        label_dir=paths.label_dir,
        max_rows=params.max_rows,
    )
    batch_meta, train_batches, val_batches, test_batches = assign_chronological_splits(
        batch_meta
    )
    variance = select_train_variance_features(
        batch_meta,
        feature_cols_all,
        max_features=params.max_features,
    )
    selected_features = variance.index.to_list()
    frames: list[pl.DataFrame] = []
    for _, row in batch_meta.iterrows():
        features = pl.read_parquet(
            Path(row["feature_path"]),
            columns=["timestamp", "batch_id", *selected_features],
        )
        labels = pl.read_parquet(
            Path(row["label_path"]),
            columns=["timestamp", "batch_id", TARGET_COL],
        )
        frames.append(features.join(labels, on=["timestamp", "batch_id"], how="inner"))
    selected_df = pl.concat(frames, how="vertical_relaxed").sort(
        ["batch_id", "timestamp"]
    )
    del frames
    selected_df = selected_df.filter(pl.col(TARGET_COL).is_between(0, 3))
    if params.max_rows is not None and selected_df.height > int(params.max_rows):
        selected_df = selected_df.tail(int(params.max_rows))
    selected_df = selected_df.with_row_index("row_id").with_columns(
        [
            pl.col(TARGET_COL).replace_strict(CLASS_NAMES_4).alias("target_name_4"),
            pl.when(pl.col(TARGET_COL).is_in([0, 1]))
            .then(pl.lit(0))
            .otherwise(pl.lit(1))
            .alias("direction_4"),
        ]
    ).with_columns(
        pl.col("direction_4").replace_strict(DIRECTION_NAMES).alias("direction_name")
    )
    pdf = selected_df.to_pandas()
    del selected_df
    gc.collect()
    feature_block = pdf[selected_features].apply(
        pd.to_numeric,
        errors="coerce",
        downcast="float",
    )
    pdf = pd.concat([pdf.drop(columns=selected_features), feature_block], axis=1).copy()
    pdf["split"] = np.select(
        [
            pdf["batch_id"].isin(train_batches),
            pdf["batch_id"].isin(val_batches),
            pdf["batch_id"].isin(test_batches),
        ],
        ["train", "val", "test"],
        default="unused",
    )
    train_df = pdf.loc[pdf["split"] == "train"].reset_index(drop=True)
    val_df = pdf.loc[pdf["split"] == "val"].reset_index(drop=True)
    test_df = pdf.loc[pdf["split"] == "test"].reset_index(drop=True)
    split_summary = (
        pdf.groupby("split")
        .agg(
            rows=("row_id", "count"),
            batches=("batch_id", "nunique"),
            ts_min=("timestamp", "min"),
            ts_max=("timestamp", "max"),
        )
        .reset_index()
    )
    return LoadedUnitData(
        pdf=pdf,
        train_df=train_df,
        val_df=val_df,
        test_df=test_df,
        batch_meta=batch_meta,
        selected_features=selected_features,
        feature_variance=variance,
        split_summary=split_summary,
    )


def run_baseline(
    data: LoadedUnitData,
    *,
    params: ExperimentParams,
) -> tuple[TabularModelBundle, dict[str, dict[str, np.ndarray]], list[dict[str, Any]], list[pd.DataFrame]]:
    """Train and evaluate the baseline 4-class model."""
    model = train_model(
        data.train_df[data.selected_features],
        data.train_df[TARGET_COL].astype(int).to_numpy(),
        n_classes=4,
        params=params,
    )
    prediction_store: dict[str, dict[str, np.ndarray]] = {}
    metric_rows: list[dict[str, Any]] = []
    reliability_parts: list[pd.DataFrame] = []
    for split_name, split_df in [("val", data.val_df), ("test", data.test_df)]:
        proba = predict_proba_model(model, split_df[data.selected_features])
        pred = proba.argmax(axis=1)
        metrics, bins = compute_eval_metrics(
            split_df[TARGET_COL].astype(int).to_numpy(),
            pred,
            proba,
            calibration_bins=params.calibration_bins,
        )
        metric_rows.append(
            {
                "model": "baseline_4class",
                "config_id": "baseline",
                "detector": None,
                "threshold_pct": None,
                "opposite_policy": None,
                "split": split_name,
                "backend": model.backend,
                **metrics,
            }
        )
        if bins is not None:
            bins = bins.assign(
                model="baseline_4class",
                config_id="baseline",
                split=split_name,
            )
            reliability_parts.append(bins)
        prediction_store[split_name] = {"proba": proba, "pred": pred}
    return model, prediction_store, metric_rows, reliability_parts


def run_oof_predictions(
    data: LoadedUnitData,
    *,
    params: ExperimentParams,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Generate expanding-fold OOF probabilities for train rows."""
    train_batches = sorted(data.train_df["batch_id"].unique())
    folds = make_expanding_oof_folds(
        train_batches,
        n_folds=params.oof_folds,
        min_train_batches=params.min_oof_train_batches,
    )
    fold_rows: list[dict[str, Any]] = []
    oof_parts: list[pd.DataFrame] = []
    for fold_id, fold_train_batches, fold_val_batches in folds:
        fold_train = data.train_df[
            data.train_df["batch_id"].isin(fold_train_batches)
        ].copy()
        fold_val = data.train_df[data.train_df["batch_id"].isin(fold_val_batches)].copy()
        if fold_train.empty or fold_val.empty:
            continue
        fold_model = train_model(
            fold_train[data.selected_features],
            fold_train[TARGET_COL].astype(int).to_numpy(),
            n_classes=4,
            params=params,
            seed=params.random_seed + fold_id + 1,
        )
        proba = predict_proba_model(fold_model, fold_val[data.selected_features])
        pred = proba.argmax(axis=1)
        part = fold_val[
            ["row_id", "timestamp", "batch_id", TARGET_COL, "direction_4"]
        ].copy()
        for cls in range(4):
            part[f"prob_{cls}"] = proba[:, cls].astype(np.float32)
        part["pred_label"] = pred.astype(np.int8)
        part["model_confidence"] = proba.max(axis=1).astype(np.float32)
        part["fold_id"] = int(fold_id)
        part["fold_train_batch_max"] = int(fold_train_batches.max())
        part["fold_val_batch_min"] = int(fold_val_batches.min())
        part["oof_backend"] = fold_model.backend
        oof_parts.append(part)
        metrics, _ = compute_eval_metrics(
            part[TARGET_COL].to_numpy(),
            pred,
            proba,
            calibration_bins=params.calibration_bins,
        )
        fold_rows.append(
            {
                "fold_id": int(fold_id),
                "train_batches": int(len(fold_train_batches)),
                "val_batches": int(len(fold_val_batches)),
                "val_rows": int(len(fold_val)),
                "train_batch_max": int(fold_train_batches.max()),
                "val_batch_min": int(fold_val_batches.min()),
                **{f"oof_{key}": value for key, value in metrics.items()},
            }
        )
        del fold_train, fold_val, fold_model, proba, pred
        gc.collect()
    oof_df = pd.concat(oof_parts, ignore_index=True) if oof_parts else pd.DataFrame()
    fold_summary = pd.DataFrame(fold_rows)
    return oof_df, fold_summary


def centered_direction_inconsistency(frame: pd.DataFrame, *, window: int = 9) -> pd.DataFrame:
    """Offline temporal-neighborhood disagreement score inside train data."""
    ordered = frame.sort_values(["batch_id", "timestamp"]).copy()
    direction = ordered["direction_4"].astype(float)
    rolling_sum = direction.rolling(
        window=window,
        center=True,
        min_periods=2,
    ).sum() - direction
    rolling_count = direction.rolling(
        window=window,
        center=True,
        min_periods=2,
    ).count() - 1
    neighbor_up_rate = (rolling_sum / rolling_count.replace(0, np.nan)).fillna(direction)
    inconsistency = np.where(direction == 1.0, 1.0 - neighbor_up_rate, neighbor_up_rate)
    ordered["temporal_inconsistency"] = np.clip(inconsistency, 0.0, 1.0)
    return ordered[["row_id", "temporal_inconsistency"]]


def class_conditional_outlier_scores(
    train_source: pd.DataFrame,
    score_source: pd.DataFrame,
    feature_subset: list[str],
    *,
    seed: int,
) -> pd.DataFrame:
    """Class-local KMeans distance percentile used as a weak outlier signal."""
    rows: list[pd.DataFrame] = []
    for cls in [0, 1, 2, 3]:
        cls_train = train_source[train_source[TARGET_COL] == cls]
        cls_score = score_source[score_source[TARGET_COL] == cls]
        if cls_train.empty or cls_score.empty:
            continue
        n_clusters = min(4, max(1, len(cls_train) // 500))
        imputer = SimpleImputer(strategy="median")
        scaler = StandardScaler()
        x_train = imputer.fit_transform(
            cls_train[feature_subset].replace([np.inf, -np.inf], np.nan)
        ).astype(np.float32, copy=False)
        x_score = imputer.transform(
            cls_score[feature_subset].replace([np.inf, -np.inf], np.nan)
        ).astype(np.float32, copy=False)
        x_train = scaler.fit_transform(x_train).astype(np.float32, copy=False)
        x_score = scaler.transform(x_score).astype(np.float32, copy=False)
        km = MiniBatchKMeans(
            n_clusters=n_clusters,
            random_state=int(seed) + cls,
            batch_size=4096,
            n_init="auto",
        )
        km.fit(x_train)
        train_dist = km.transform(x_train).min(axis=1)
        score_dist = km.transform(x_score).min(axis=1)
        pct = np.searchsorted(np.sort(train_dist), score_dist, side="right") / max(
            len(train_dist),
            1,
        )
        rows.append(
            pd.DataFrame(
                {
                    "row_id": cls_score["row_id"].to_numpy(),
                    "class_conditional_outlier_score": pct.astype(np.float32),
                }
            )
        )
        del cls_train, cls_score, x_train, x_score, train_dist, score_dist, km
        gc.collect()
    if not rows:
        return pd.DataFrame(columns=["row_id", "class_conditional_outlier_score"])
    return pd.concat(rows, ignore_index=True)


def build_base_noise_table(
    data: LoadedUnitData,
    oof_df: pd.DataFrame,
    *,
    params: ExperimentParams,
) -> pd.DataFrame:
    """Build detector-neutral score table with rank-normalized signal columns."""
    if oof_df.empty:
        raise RuntimeError("OOF predictions are required before scoring label noise")
    score_df = oof_df.copy()
    for cls in range(4):
        score_df.loc[:, f"prob_{cls}"] = score_df[f"prob_{cls}"].astype(np.float32)
    prob_matrix = score_df[[f"prob_{cls}" for cls in range(4)]].to_numpy(
        dtype=np.float32,
        copy=False,
    )
    true_idx = score_df[TARGET_COL].to_numpy(dtype=np.int64, copy=False)
    score_df["p_true"] = prob_matrix[np.arange(len(score_df)), true_idx].astype(
        np.float32
    )
    score_df["label_conflict_score"] = 1.0 - score_df["p_true"]
    score_df["ensemble_disagreement_proxy"] = (
        score_df["pred_label"] != score_df[TARGET_COL]
    ).astype(float)
    score_df = score_df.merge(
        centered_direction_inconsistency(data.train_df),
        on="row_id",
        how="left",
    )
    outlier_features = data.selected_features[
        : min(int(params.outlier_feature_count), len(data.selected_features))
    ]
    score_source = data.train_df.loc[
        data.train_df["row_id"].isin(score_df["row_id"]),
        ["row_id", TARGET_COL, *outlier_features],
    ].copy()
    outlier_df = class_conditional_outlier_scores(
        data.train_df,
        score_source,
        outlier_features,
        seed=params.random_seed,
    )
    score_df = score_df.merge(outlier_df, on="row_id", how="left")
    score_df["temporal_inconsistency"] = score_df["temporal_inconsistency"].fillna(0.0)
    score_df["class_conditional_outlier_score"] = score_df[
        "class_conditional_outlier_score"
    ].fillna(0.0)
    signal_cols = [
        "label_conflict_score",
        "ensemble_disagreement_proxy",
        "temporal_inconsistency",
        "class_conditional_outlier_score",
    ]
    for col in signal_cols:
        score_df[f"{col}_rank"] = score_df.groupby(TARGET_COL)[col].rank(
            pct=True,
            method="average",
        )
    return score_df


def build_ablation_configs(
    *,
    threshold_pcts: list[float],
    detectors: list[str],
    opposite_policies: list[str],
    mode: str,
) -> list[AblationConfig]:
    """Build a safe staged ablation schedule or a full Cartesian schedule."""
    if mode == "primary-only":
        return [
            AblationConfig(
                threshold_pct=PRIMARY_THRESHOLD_PCT,
                detector=PRIMARY_DETECTOR,
                opposite_policy=PRIMARY_OPPOSITE_POLICY,
            )
        ]
    configs: dict[str, AblationConfig] = {}
    primary_threshold = (
        PRIMARY_THRESHOLD_PCT
        if any(math.isclose(x, PRIMARY_THRESHOLD_PCT) for x in threshold_pcts)
        else float(threshold_pcts[0])
    )

    def add(config: AblationConfig) -> None:
        configs[config.config_id] = config

    if mode == "cartesian":
        for threshold_pct in threshold_pcts:
            for detector in detectors:
                for policy in opposite_policies:
                    add(AblationConfig(float(threshold_pct), detector, policy))
    elif mode == "staged":
        for threshold_pct in threshold_pcts:
            add(AblationConfig(float(threshold_pct), PRIMARY_DETECTOR, PRIMARY_OPPOSITE_POLICY))
        for detector in detectors:
            add(AblationConfig(primary_threshold, detector, PRIMARY_OPPOSITE_POLICY))
        for policy in opposite_policies:
            add(AblationConfig(primary_threshold, PRIMARY_DETECTOR, policy))
    else:
        raise ValueError(f"Unknown ablation mode: {mode}")
    return list(configs.values())


def summarize_actions(
    train8_df: pd.DataFrame,
    *,
    config: AblationConfig,
) -> pd.DataFrame:
    """Count train actions and anomaly classes for one config."""
    summary = (
        train8_df.groupby(["training_action", TARGET_COL])
        .agg(
            rows=("row_id", "count"),
            avg_weight=("sample_weight_anomaly", "mean"),
        )
        .reset_index()
    )
    summary["class_name"] = summary[TARGET_COL].map(CLASS_NAMES_4)
    summary["config_id"] = config.config_id
    summary["detector"] = config.detector
    summary["threshold_pct"] = config.threshold_pct
    summary["opposite_policy"] = config.opposite_policy
    return summary


def _prediction_frame(
    split_df: pd.DataFrame,
    *,
    model_name: str,
    config_id: str,
    split_name: str,
    pred_leaf: np.ndarray,
    proba: np.ndarray,
) -> pd.DataFrame:
    """Create a compact prediction artifact frame."""
    frame = split_df[["row_id", "timestamp", "batch_id", TARGET_COL]].copy()
    frame["model"] = model_name
    frame["config_id"] = config_id
    frame["split"] = split_name
    frame["pred_leaf"] = pred_leaf.astype(np.int16)
    frame["pred_4class"] = collapse_8_to_4(pred_leaf).astype(np.int16)
    frame["true_direction"] = to_direction(frame[TARGET_COL].to_numpy()).astype(np.int8)
    frame["pred_direction"] = to_direction(frame["pred_4class"].to_numpy()).astype(
        np.int8
    )
    for cls in range(proba.shape[1]):
        frame[f"prob_{cls}"] = proba[:, cls].astype(np.float32)
    return frame


def _review_frame(decisions: pd.DataFrame) -> pd.DataFrame:
    """Columns exported for high-confidence opposite-direction manual review."""
    review = decisions.loc[decisions["high_conf_opposite"]].copy()
    required_cols = [
        "timestamp",
        "batch_id",
        TARGET_COL,
        "pred_label",
        "prob_0",
        "prob_1",
        "prob_2",
        "prob_3",
        "model_confidence",
        "noise_score",
        "temporal_inconsistency",
        "class_conditional_outlier_score",
        "training_action",
    ]
    for col in required_cols:
        if col not in review.columns:
            review[col] = np.nan
    review = review[required_cols].sort_values(
        ["noise_score", "model_confidence"],
        ascending=[False, False],
    )
    duplicate_count = int(review.duplicated(["timestamp", "batch_id"]).sum())
    if duplicate_count:
        raise ValueError(f"Review set contains duplicate timestamp,batch_id rows: {duplicate_count}")
    return review


def export_review_set(
    decisions: pd.DataFrame,
    *,
    output_dir: Path,
    config: AblationConfig,
) -> dict[str, Any]:
    """Write high-confidence opposite-direction rows for manual inspection."""
    output_dir.mkdir(parents=True, exist_ok=True)
    review = _review_frame(decisions)
    parquet_path = output_dir / f"{config.config_id}_review_set.parquet"
    csv_path = output_dir / f"{config.config_id}_review_set.csv"
    review.to_parquet(parquet_path, index=False)
    review.to_csv(csv_path, index=False)
    return {
        "config_id": config.config_id,
        "rows": int(len(review)),
        "parquet_path": str(parquet_path),
        "csv_path": str(csv_path),
    }


def run_catboost_anomaly_model(
    data: LoadedUnitData,
    train8_df: pd.DataFrame,
    *,
    params: ExperimentParams,
    config: AblationConfig,
) -> tuple[list[dict[str, Any]], list[pd.DataFrame], list[pd.DataFrame]]:
    """Train flat 8-class CatBoost anomaly model and evaluate collapsed output."""
    train8_fit = train8_df[train8_df["sample_weight_anomaly"] > 0].copy()
    if train8_fit["target_8class_anomaly"].nunique() < 2:
        raise RuntimeError("Anomaly target has fewer than two classes after filtering")
    model = train_model(
        train8_fit[data.selected_features],
        train8_fit["target_8class_anomaly"].astype(int).to_numpy(),
        n_classes=8,
        sample_weight=train8_fit["sample_weight_anomaly"].to_numpy(),
        params=params,
        seed=params.random_seed + 100,
    )
    metric_rows: list[dict[str, Any]] = []
    prediction_parts: list[pd.DataFrame] = []
    reliability_parts: list[pd.DataFrame] = []
    for split_name, split_df in [("val", data.val_df), ("test", data.test_df)]:
        y_true4 = split_df[TARGET_COL].astype(int).to_numpy()
        proba8 = predict_proba_model(model, split_df[data.selected_features])
        pred8 = proba8.argmax(axis=1)
        metrics, bins = compute_eval_metrics(
            y_true4,
            pred8,
            proba8,
            calibration_bins=params.calibration_bins,
        )
        metrics["macro_f1_8_proxy_on_collapsed_truth"] = float(
            f1_score(
                y_true4,
                pred8,
                labels=list(range(8)),
                average="macro",
                zero_division=0,
            )
        )
        metric_rows.append(
            {
                "model": "catboost_8class_collapsed",
                "config_id": config.config_id,
                "detector": config.detector,
                "threshold_pct": config.threshold_pct,
                "opposite_policy": config.opposite_policy,
                "split": split_name,
                "backend": model.backend,
                **metrics,
            }
        )
        if bins is not None:
            reliability_parts.append(
                bins.assign(
                    model="catboost_8class_collapsed",
                    config_id=config.config_id,
                    split=split_name,
                )
            )
        prediction_parts.append(
            _prediction_frame(
                split_df,
                model_name="catboost_8class_collapsed",
                config_id=config.config_id,
                split_name=split_name,
                pred_leaf=pred8,
                proba=proba8,
            )
        )
    return metric_rows, prediction_parts, reliability_parts


class StructuredMLP:  # pragma: no cover - thin wrapper around optional torch.
    """Namespace for the optional PyTorch structured prototype."""

    @staticmethod
    def fit_predict(
        data: LoadedUnitData,
        train8_df: pd.DataFrame,
        *,
        params: ExperimentParams,
        device: str,
    ) -> dict[str, np.ndarray]:
        import torch
        import torch.nn as nn
        import torch.nn.functional as F
        from torch.utils.data import DataLoader, TensorDataset

        class Net(nn.Module):
            def __init__(self, n_features: int) -> None:
                super().__init__()
                hidden = int(params.structured_hidden_dim)
                self.backbone = nn.Sequential(
                    nn.Linear(n_features, hidden),
                    nn.ReLU(),
                    nn.Dropout(float(params.structured_dropout)),
                    nn.Linear(hidden, hidden),
                    nn.ReLU(),
                    nn.Dropout(float(params.structured_dropout)),
                )
                self.leaf = nn.Linear(hidden, 8)
                self.direction = nn.Linear(hidden, 2)
                self.regime = nn.Linear(hidden, 2)
                self.anomaly = nn.Linear(hidden, 1)

            def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
                z = self.backbone(x)
                return self.leaf(z), self.direction(z), self.regime(z), self.anomaly(z)

        torch.manual_seed(int(params.random_seed))
        np.random.seed(int(params.random_seed))
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        train_fit = train8_df[train8_df["sample_weight_anomaly"] > 0].copy()
        imputer = SimpleImputer(strategy="median")
        scaler = StandardScaler()
        x_train = imputer.fit_transform(
            train_fit[data.selected_features].replace([np.inf, -np.inf], np.nan)
        ).astype(np.float32, copy=False)
        x_train = scaler.fit_transform(x_train).astype(np.float32, copy=False)
        y_leaf = train_fit["target_8class_anomaly"].astype(int).to_numpy()
        y_dir = to_direction(y_leaf).astype(np.int64)
        y_regime = to_regime(y_leaf).astype(np.int64)
        y_anom = (y_leaf >= 4).astype(np.float32)
        weight = train_fit["sample_weight_anomaly"].to_numpy(dtype=np.float32)

        dataset = TensorDataset(
            torch.from_numpy(x_train),
            torch.from_numpy(y_leaf.astype(np.int64)),
            torch.from_numpy(y_dir),
            torch.from_numpy(y_regime),
            torch.from_numpy(y_anom),
            torch.from_numpy(weight),
        )
        loader = DataLoader(
            dataset,
            batch_size=int(params.structured_batch_size),
            shuffle=False,
        )
        net = Net(len(data.selected_features)).to(device)
        opt = torch.optim.AdamW(
            net.parameters(),
            lr=float(params.structured_learning_rate),
            weight_decay=1e-4,
        )
        for _epoch in range(int(params.structured_epochs)):
            net.train()
            for xb, leaf, direction, regime, anomaly, sample_weight in loader:
                xb = xb.to(device)
                leaf = leaf.to(device)
                direction = direction.to(device)
                regime = regime.to(device)
                anomaly = anomaly.to(device)
                sample_weight = sample_weight.to(device)
                leaf_logits, dir_logits, regime_logits, anomaly_logits = net(xb)
                leaf_loss = F.cross_entropy(leaf_logits, leaf, reduction="none")
                dir_loss = F.cross_entropy(dir_logits, direction, reduction="none")
                regime_loss = F.cross_entropy(regime_logits, regime, reduction="none")
                anomaly_loss = F.binary_cross_entropy_with_logits(
                    anomaly_logits.squeeze(1),
                    anomaly,
                    reduction="none",
                )
                leaf_proba = F.softmax(leaf_logits, dim=1)
                true_down = direction == 0
                opposite_mass = torch.where(
                    true_down,
                    leaf_proba[:, [2, 3, 6, 7]].sum(dim=1),
                    leaf_proba[:, [0, 1, 4, 5]].sum(dim=1),
                )
                total = (
                    1.0 * leaf_loss
                    + 0.8 * dir_loss
                    + 0.4 * regime_loss
                    + 0.3 * anomaly_loss
                    + 0.5 * opposite_mass
                )
                loss = (total * sample_weight).sum() / torch.clamp(
                    sample_weight.sum(),
                    min=1.0,
                )
                opt.zero_grad(set_to_none=True)
                loss.backward()
                opt.step()

        def predict(split_df: pd.DataFrame) -> np.ndarray:
            x = imputer.transform(
                split_df[data.selected_features].replace([np.inf, -np.inf], np.nan)
            ).astype(np.float32, copy=False)
            x = scaler.transform(x).astype(np.float32, copy=False)
            net.eval()
            parts: list[np.ndarray] = []
            with torch.no_grad():
                for start in range(0, len(x), int(params.structured_batch_size)):
                    xb = torch.from_numpy(x[start : start + int(params.structured_batch_size)]).to(device)
                    leaf_logits, _, _, _ = net(xb)
                    parts.append(F.softmax(leaf_logits, dim=1).cpu().numpy())
            return np.vstack(parts) if parts else np.zeros((0, 8), dtype=np.float32)

        return {
            "val": predict(data.val_df),
            "test": predict(data.test_df),
            "device": np.array([device], dtype=object),
        }


def run_structured_model(
    data: LoadedUnitData,
    train8_df: pd.DataFrame,
    *,
    params: ExperimentParams,
    config: AblationConfig,
    device: str,
) -> tuple[list[dict[str, Any]], list[pd.DataFrame], list[pd.DataFrame]]:
    """Train structured MLP prototype and evaluate collapsed output."""
    metric_rows: list[dict[str, Any]] = []
    prediction_parts: list[pd.DataFrame] = []
    reliability_parts: list[pd.DataFrame] = []
    try:
        outputs = StructuredMLP.fit_predict(
            data,
            train8_df,
            params=params,
            device=device,
        )
        backend = f"structured_mlp_{str(outputs['device'][0])}"
    except Exception as exc:  # pragma: no cover - defensive runtime path.
        warnings.warn(f"Structured model failed and will be skipped: {exc}")
        return metric_rows, prediction_parts, reliability_parts

    for split_name, split_df in [("val", data.val_df), ("test", data.test_df)]:
        y_true4 = split_df[TARGET_COL].astype(int).to_numpy()
        proba8 = outputs[split_name]
        pred8 = proba8.argmax(axis=1)
        metrics, bins = compute_eval_metrics(
            y_true4,
            pred8,
            proba8,
            calibration_bins=params.calibration_bins,
        )
        metrics["macro_f1_8_proxy_on_collapsed_truth"] = float(
            f1_score(
                y_true4,
                pred8,
                labels=list(range(8)),
                average="macro",
                zero_division=0,
            )
        )
        metric_rows.append(
            {
                "model": "structured_8class_collapsed",
                "config_id": config.config_id,
                "detector": config.detector,
                "threshold_pct": config.threshold_pct,
                "opposite_policy": config.opposite_policy,
                "split": split_name,
                "backend": backend,
                **metrics,
            }
        )
        if bins is not None:
            reliability_parts.append(
                bins.assign(
                    model="structured_8class_collapsed",
                    config_id=config.config_id,
                    split=split_name,
                )
            )
        prediction_parts.append(
            _prediction_frame(
                split_df,
                model_name="structured_8class_collapsed",
                config_id=config.config_id,
                split_name=split_name,
                pred_leaf=pred8,
                proba=proba8,
            )
        )
    return metric_rows, prediction_parts, reliability_parts


def compare_to_baseline(metrics_df: pd.DataFrame) -> pd.DataFrame:
    """Compute model minus baseline deltas per target/root/split."""
    baseline = metrics_df[metrics_df["model"] == "baseline_4class"].copy()
    other = metrics_df[metrics_df["model"] != "baseline_4class"].copy()
    key_cols = ["target_asset", "root", "split"]
    merged = other.merge(
        baseline[
            [
                *key_cols,
                "collapsed_4_accuracy",
                "macro_f1_4",
                "direction_accuracy",
                "cross_direction_error",
                "logloss_4",
                "brier_4",
                "ece_4",
                "primary_score",
            ]
        ],
        on=key_cols,
        suffixes=("", "_baseline"),
        how="left",
    )
    for col in [
        "collapsed_4_accuracy",
        "macro_f1_4",
        "direction_accuracy",
        "cross_direction_error",
        "logloss_4",
        "brier_4",
        "ece_4",
        "primary_score",
    ]:
        merged[f"{col}_delta"] = merged[col] - merged[f"{col}_baseline"]
    merged["pass_accuracy_up"] = merged["collapsed_4_accuracy_delta"] > 0
    merged["pass_macro_f1_stable_or_up"] = merged["macro_f1_4_delta"] >= -0.002
    merged["pass_direction_accuracy_up"] = merged["direction_accuracy_delta"] > 0
    merged["pass_cross_direction_error_down"] = merged["cross_direction_error_delta"] < 0
    merged["passes_acceptance"] = (
        merged["pass_accuracy_up"]
        & merged["pass_macro_f1_stable_or_up"]
        & merged["pass_direction_accuracy_up"]
        & merged["pass_cross_direction_error_down"]
    )
    return merged


def run_unit(
    *,
    target_asset: str,
    context_assets: tuple[str, ...],
    root_key: str,
    dataset_dir: Path,
    unit_output_dir: Path,
    params: ExperimentParams,
    ablation_configs: list[AblationConfig],
    models: set[str],
    structured_sweep: str,
    export_review: bool,
    save_predictions: bool,
    structured_device: str,
) -> dict[str, Any]:
    """Run all configured anomaly experiments for one target/root."""
    unit_output_dir.mkdir(parents=True, exist_ok=True)
    paths = resolve_merged_dataset(
        target_asset=target_asset,
        context_assets=context_assets,
        root_key=root_key,
        dataset_dir=dataset_dir,
    )
    data = load_selected_unit_data(paths=paths, params=params)
    print(
        f"[UNIT] {target_asset} {root_key} rows={len(data.pdf):,} "
        f"features={len(data.selected_features)}",
        flush=True,
    )

    baseline_model, baseline_predictions, metric_rows, reliability_parts = run_baseline(
        data,
        params=params,
    )
    prediction_parts: list[pd.DataFrame] = []
    if save_predictions:
        for split_name, split_df in [("val", data.val_df), ("test", data.test_df)]:
            prediction_parts.append(
                _prediction_frame(
                    split_df,
                    model_name="baseline_4class",
                    config_id="baseline",
                    split_name=split_name,
                    pred_leaf=baseline_predictions[split_name]["pred"],
                    proba=baseline_predictions[split_name]["proba"],
                )
            )
    del baseline_model
    gc.collect()

    oof_df, fold_summary = run_oof_predictions(data, params=params)
    base_noise = build_base_noise_table(data, oof_df, params=params)
    action_summaries: list[pd.DataFrame] = []
    review_manifests: list[dict[str, Any]] = []
    label_dir = unit_output_dir / "anomaly_labels"
    label_dir.mkdir(parents=True, exist_ok=True)
    primary_config = next(
        (config for config in ablation_configs if config.is_primary),
        ablation_configs[0],
    )

    for config in ablation_configs:
        scored = apply_detector_score(base_noise, config.detector)
        decisions = apply_anomaly_decisions(
            scored,
            threshold_pct=config.threshold_pct,
            opposite_policy=config.opposite_policy,
            opposite_high_confidence=params.opposite_high_confidence,
        )
        train8_df = attach_anomaly_decisions(data.train_df, decisions)
        action_summaries.append(summarize_actions(train8_df, config=config))
        labels_out = train8_df[
            [
                "row_id",
                "timestamp",
                "batch_id",
                TARGET_COL,
                "target_8class_anomaly",
                "sample_weight_anomaly",
                "training_action",
                "noise_score",
            ]
        ].copy()
        labels_out.to_parquet(label_dir / f"{config.config_id}.parquet", index=False)
        is_primary_run_config = config.config_id == primary_config.config_id
        if export_review and is_primary_run_config:
            review_manifests.append(
                export_review_set(
                    decisions,
                    output_dir=unit_output_dir / "review_sets",
                    config=config,
                )
            )
        if "catboost" in models:
            rows, preds, reliability = run_catboost_anomaly_model(
                data,
                train8_df,
                params=params,
                config=config,
            )
            metric_rows.extend(rows)
            reliability_parts.extend(reliability)
            if save_predictions:
                prediction_parts.extend(preds)
        if "structured" in models and (
            is_primary_run_config or structured_sweep == "all"
        ):
            rows, preds, reliability = run_structured_model(
                data,
                train8_df,
                params=params,
                config=config,
                device=structured_device,
            )
            metric_rows.extend(rows)
            reliability_parts.extend(reliability)
            if save_predictions:
                prediction_parts.extend(preds)
        del train8_df, decisions, scored
        gc.collect()

    context_hash = build_context_set_hash(
        target_asset=target_asset,
        context_assets=context_assets,
    )
    unit_tags = {
        "target_asset": normalize_htf_asset_id(target_asset),
        "context_assets": ",".join(context_assets),
        "context_hash": context_hash,
        "root": root_key,
        "root_id": STAGE1_MULTIASSET_ROOT_LAYOUTS[root_key].root_id,
    }
    metrics_df = pd.DataFrame(metric_rows).assign(**unit_tags)
    metrics_df.to_parquet(unit_output_dir / "metrics.parquet", index=False)
    metrics_df.to_csv(unit_output_dir / "metrics.csv", index=False)
    if action_summaries:
        action_df = pd.concat(action_summaries, ignore_index=True).assign(**unit_tags)
        action_df.to_parquet(unit_output_dir / "action_summary.parquet", index=False)
        action_df.to_csv(unit_output_dir / "action_summary.csv", index=False)
    if reliability_parts:
        reliability_df = pd.concat(reliability_parts, ignore_index=True).assign(
            **unit_tags
        )
        reliability_df.to_parquet(unit_output_dir / "reliability_bins.parquet", index=False)
    if save_predictions and prediction_parts:
        predictions_df = pd.concat(prediction_parts, ignore_index=True).assign(
            **unit_tags
        )
        predictions_df.to_parquet(unit_output_dir / "predictions.parquet", index=False)
    fold_summary = fold_summary.assign(**unit_tags)
    fold_summary.to_parquet(unit_output_dir / "oof_fold_summary.parquet", index=False)
    data.split_summary.to_csv(unit_output_dir / "split_summary.csv", index=False)
    data.feature_variance.reset_index().rename(
        columns={"index": "feature", 0: "train_variance"}
    ).to_csv(unit_output_dir / "selected_feature_variance.csv", index=False)
    (unit_output_dir / "selected_features.json").write_text(
        json.dumps(data.selected_features, indent=2)
    )

    unit_manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **unit_tags,
        "context_assets": list(context_assets),
        "source_manifest_path": str(paths.manifest_path),
        "input_manifest": {
            key: paths.manifest.get(key)
            for key in [
                "output_rows",
                "rows_dropped_by_missing_context",
                "rows_dropped_by_null_features",
                "duplicate_count",
                "null_feature_count",
                "feature_columns_count",
                "timestamp_min",
                "timestamp_max",
            ]
        },
        "params": asdict(params),
        "rows": {
            "all": int(len(data.pdf)),
            "train": int(len(data.train_df)),
            "val": int(len(data.val_df)),
            "test": int(len(data.test_df)),
            "oof_scored": int(len(oof_df)),
        },
        "selected_features": int(len(data.selected_features)),
        "ablation_configs": [asdict(config) | {"config_id": config.config_id} for config in ablation_configs],
        "models": sorted(models),
        "review_sets": review_manifests,
    }
    (unit_output_dir / "manifest.json").write_text(
        json.dumps(unit_manifest, indent=2, default=str)
    )
    return {
        "manifest": unit_manifest,
        "metrics_df": metrics_df,
    }


def _parse_csv(raw: str | None) -> list[str]:
    if raw is None:
        return []
    return [part.strip() for part in str(raw).split(",") if part.strip()]


def _parse_thresholds(raw: str) -> list[float]:
    values = [float(part.strip()) for part in str(raw).split(",") if part.strip()]
    if not values:
        raise ValueError("At least one threshold pct is required")
    for value in values:
        if not (0.0 < value < 1.0):
            raise ValueError(f"Invalid threshold pct {value}; expected 0 < pct < 1")
    return values


def _expand_selectors(raw: str | None, *, known: Iterable[str], default_all: bool) -> list[str]:
    known_list = list(known)
    if raw is None or not raw.strip():
        return known_list if default_all else []
    token = raw.strip().lower()
    if token == "all":
        return known_list
    selected = _parse_csv(raw)
    unknown = sorted(set(selected) - set(known_list))
    if unknown:
        raise ValueError(f"Unknown selector values {unknown}; known values: {known_list}")
    return selected


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Stage-1 label-anomaly validation experiments.",
    )
    parser.add_argument("--target-assets", default="BTCUSDT")
    parser.add_argument(
        "--context-assets",
        default="core-ex-target",
        help="Context selector per target: core-ex-target, core, empty, or CSV.",
    )
    parser.add_argument(
        "--roots",
        nargs="*",
        choices=sorted(STAGE1_MULTIASSET_ROOT_LAYOUTS),
        default=["8h/B"],
    )
    parser.add_argument(
        "--multiasset-dataset-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "htf_multiasset_merged",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "test_output" / "stage1_label_anomaly_experiments",
    )
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--threshold-pcts", default="0.03")
    parser.add_argument(
        "--models",
        default="catboost",
        help="Comma-separated subset: catboost,structured.",
    )
    parser.add_argument(
        "--detectors",
        default="all",
        help="all or CSV of label_conflict,conflict_temporal,conflict_temporal_outlier,full_hybrid.",
    )
    parser.add_argument(
        "--opposite-policies",
        default="all",
        help="all or CSV of keep_clean,low_weight,exclude_review.",
    )
    parser.add_argument(
        "--ablation-mode",
        choices=["primary-only", "staged", "cartesian"],
        default="staged",
        help="Staged avoids the full threshold x detector x policy explosion.",
    )
    parser.add_argument(
        "--structured-sweep",
        choices=["primary", "all"],
        default="primary",
        help="Run structured model only on the primary config or every config.",
    )
    parser.add_argument("--max-rows", type=int, default=180_000)
    parser.add_argument("--max-features", type=int, default=250)
    parser.add_argument("--oof-folds", type=int, default=5)
    parser.add_argument("--min-oof-train-batches", type=int, default=120)
    parser.add_argument("--outlier-feature-count", type=int, default=250)
    parser.add_argument("--opposite-high-confidence", type=float, default=0.80)
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument("--catboost-iterations", type=int, default=220)
    parser.add_argument("--catboost-depth", type=int, default=6)
    parser.add_argument("--catboost-learning-rate", type=float, default=0.05)
    parser.add_argument("--catboost-thread-count", type=int, default=4)
    parser.add_argument("--structured-epochs", type=int, default=25)
    parser.add_argument("--structured-batch-size", type=int, default=2048)
    parser.add_argument("--structured-learning-rate", type=float, default=1e-3)
    parser.add_argument("--structured-hidden-dim", type=int, default=256)
    parser.add_argument("--structured-dropout", type=float, default=0.10)
    parser.add_argument("--structured-device", default="auto")
    parser.add_argument("--calibration-bins", type=int, default=15)
    parser.add_argument("--export-review-set", action="store_true")
    parser.add_argument(
        "--save-predictions",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--skip-missing",
        action="store_true",
        help="Skip target/root pairs whose merged manifests do not exist.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    target_assets = parse_stage1_target_assets(args.target_assets)
    threshold_pcts = _parse_thresholds(args.threshold_pcts)
    detectors = _expand_selectors(
        args.detectors,
        known=DETECTOR_WEIGHTS.keys(),
        default_all=True,
    )
    opposite_policies = _expand_selectors(
        args.opposite_policies,
        known=OPPOSITE_POLICIES,
        default_all=True,
    )
    models = set(_expand_selectors(args.models, known=MODEL_CHOICES, default_all=False))
    if not models:
        raise ValueError("--models must include at least one model")
    params = ExperimentParams(
        max_rows=None if args.max_rows <= 0 else int(args.max_rows),
        max_features=int(args.max_features),
        oof_folds=int(args.oof_folds),
        min_oof_train_batches=int(args.min_oof_train_batches),
        outlier_feature_count=int(args.outlier_feature_count),
        opposite_high_confidence=float(args.opposite_high_confidence),
        random_seed=int(args.random_seed),
        catboost_iterations=int(args.catboost_iterations),
        catboost_depth=int(args.catboost_depth),
        catboost_learning_rate=float(args.catboost_learning_rate),
        catboost_thread_count=int(args.catboost_thread_count),
        structured_epochs=int(args.structured_epochs),
        structured_batch_size=int(args.structured_batch_size),
        structured_learning_rate=float(args.structured_learning_rate),
        structured_hidden_dim=int(args.structured_hidden_dim),
        structured_dropout=float(args.structured_dropout),
        calibration_bins=int(args.calibration_bins),
    )
    ablation_configs = build_ablation_configs(
        threshold_pcts=threshold_pcts,
        detectors=detectors,
        opposite_policies=opposite_policies,
        mode=str(args.ablation_mode),
    )
    run_id = args.run_id or datetime.now(timezone.utc).strftime(
        "stage1_label_anomaly_%Y%m%d_%H%M%S"
    )
    run_dir = Path(args.output_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()
    print("=" * 78)
    print("STAGE-1 LABEL-ANOMALY EXPERIMENT")
    print("=" * 78)
    print(f"Run ID: {run_id}")
    print(f"Targets: {target_assets}")
    print(f"Roots: {tuple(args.roots)}")
    print(f"Models: {sorted(models)}")
    print(f"Ablation configs: {len(ablation_configs)}")
    print(f"Output: {run_dir}")

    all_metrics: list[pd.DataFrame] = []
    unit_manifests: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for target_asset in target_assets:
        context_assets = parse_stage1_context_assets(
            args.context_assets,
            target_asset=target_asset,
        )
        for root_key in args.roots:
            root_id = STAGE1_MULTIASSET_ROOT_LAYOUTS[root_key].root_id
            unit_output_dir = run_dir / normalize_htf_asset_id(target_asset).lower() / root_id
            try:
                result = run_unit(
                    target_asset=target_asset,
                    context_assets=context_assets,
                    root_key=root_key,
                    dataset_dir=Path(args.multiasset_dataset_dir),
                    unit_output_dir=unit_output_dir,
                    params=params,
                    ablation_configs=ablation_configs,
                    models=models,
                    structured_sweep=str(args.structured_sweep),
                    export_review=bool(args.export_review_set),
                    save_predictions=bool(args.save_predictions),
                    structured_device=str(args.structured_device),
                )
            except FileNotFoundError as exc:
                if not args.skip_missing:
                    raise
                print(f"[SKIP] {target_asset} {root_key}: {exc}", flush=True)
                errors.append(
                    {
                        "target_asset": target_asset,
                        "root": root_key,
                        "error": str(exc),
                        "skipped": True,
                    }
                )
                continue
            except Exception as exc:
                errors.append(
                    {
                        "target_asset": target_asset,
                        "root": root_key,
                        "error": repr(exc),
                        "skipped": False,
                    }
                )
                raise
            all_metrics.append(result["metrics_df"])
            unit_manifests.append(result["manifest"])

    if all_metrics:
        metrics_df = pd.concat(all_metrics, ignore_index=True)
        metrics_df.to_parquet(run_dir / "metrics.parquet", index=False)
        metrics_df.to_csv(run_dir / "metrics.csv", index=False)
        comparison_df = compare_to_baseline(metrics_df)
        comparison_df.to_parquet(run_dir / "comparison_to_baseline.parquet", index=False)
        comparison_df.to_csv(run_dir / "comparison_to_baseline.csv", index=False)
        matrix_summary = (
            comparison_df.groupby(["model", "config_id", "split"])
            .agg(
                units=("target_asset", "count"),
                median_accuracy_delta=("collapsed_4_accuracy_delta", "median"),
                median_macro_f1_delta=("macro_f1_4_delta", "median"),
                median_direction_accuracy_delta=("direction_accuracy_delta", "median"),
                median_cross_direction_error_delta=("cross_direction_error_delta", "median"),
                pass_rate=("passes_acceptance", "mean"),
            )
            .reset_index()
        )
        matrix_summary.to_csv(run_dir / "matrix_summary.csv", index=False)
        matrix_summary.to_json(
            run_dir / "matrix_summary.json",
            orient="records",
            indent=2,
        )
        print("\nMATRIX SUMMARY")
        print(matrix_summary.sort_values(["split", "pass_rate"], ascending=[True, False]).head(30))
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "duration_seconds": round(time.time() - started, 3),
        "params": asdict(params),
        "target_assets": list(target_assets),
        "roots": list(args.roots),
        "context_assets_selector": args.context_assets,
        "models": sorted(models),
        "ablation_configs": [asdict(config) | {"config_id": config.config_id} for config in ablation_configs],
        "unit_count": len(unit_manifests),
        "units": unit_manifests,
        "errors": errors,
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    print("=" * 78)
    print(f"Complete: {run_dir}")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
