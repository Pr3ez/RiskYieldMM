"""
Shared Utilities for HTF LightGBM Backtest
==========================================

Data loading, feature utilities, class weighting.
Used by both 5m and 15m optimizers.
"""

import json
import optuna
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

import lightgbm as lgb
import numpy as np
import polars as pl
from sklearn.feature_selection import mutual_info_classif
from sklearn.metrics import f1_score


# ============================================================================
# BASE CONFIGURATION
# ============================================================================

# Base 4-class names
BASE_CLASS_NAMES = (
    "DOWN_BALANCED",
    "DOWN_EXPANSION",
    "UP_BALANCED",
    "UP_EXPANSION",
)
@dataclass
class BaseOptimizerConfig:
    """Base configuration for HTF optimizer."""

    project_root: Path = field(
        default_factory=lambda: Path("/media/przem/linux_data/RiskYieldMM (Copy)")
    )

    @property
    def features_dir(self) -> Path:
        return self.project_root / "data" / "htf_with_helpers"

    @property
    def labels_dir(self) -> Path:
        return self.project_root / "data" / "htf_4class_labels"

    @property
    def output_dir(self) -> Path:
        return self.project_root / "data" / "htf_backtest_results"

    # Target settings
    target: str = "target_4class"
    feature_target: str | None = None
    n_classes: int = 4
    class_names: tuple = BASE_CLASS_NAMES
    # Optional tail exclusion (fraction of last rows per batch)
    exclude_tail_pct: float = 0.0
    # Track prediction-batch metrics for every Optuna trial (extra compute)
    track_pred_metrics: bool = False
    # Optional stratified shuffle for train/val split
    shuffle_split: bool = False
    shuffle_seed: int = 42
    shuffle_val_ratio: float | None = None
    # Optional shuffle of batch order (keeps row order within each batch)
    shuffle_batches: bool = False
    shuffle_batches_seed: int = 42
    # Optional class balancing via resampling
    balance_strategy: Literal["none", "upsample", "downsample"] = "none"
    balance_apply_to: Literal["train", "train_val"] = "train"
    # Allowed class-weight methods for Optuna categorical search.
    # Set to a single value to freeze (e.g., ("balanced",)).
    class_weight_choices: tuple[str, ...] = ("none", "balanced", "sqrt")

    # Train/val split
    train_val_split: float = 0.85

    # LightGBM base params (fixed)
    lgb_base_params: dict = field(
        default_factory=lambda: {
            "objective": "multiclass",
            "num_class": 4,
            "metric": "multi_logloss",
            "boosting_type": "gbdt",
            "device": "gpu",
            "gpu_platform_id": 0,
            "gpu_device_id": 0,
            "verbose": -1,
            "seed": 42,
        }
    )

    def __post_init__(self) -> None:
        # Keep LightGBM num_class aligned with n_classes
        if self.lgb_base_params.get("num_class") != self.n_classes:
            self.lgb_base_params = dict(self.lgb_base_params)
            self.lgb_base_params["num_class"] = self.n_classes

    # Optuna settings
    optuna_trials: int = 20
    optuna_timeout: int = 120
    optuna_metric: str = (
        "accuracy"  # accuracy, log_loss, balanced_accuracy, macro_f1, macro_f1_up, macro_f1_down, directional_accuracy, directional_precision_up, directional_precision_down, cross_direction_error
    )

    def optuna_direction(self) -> str:
        """Optimization direction for the configured metric."""
        if self.optuna_metric in {"log_loss", "cross_direction_error"}:
            return "minimize"
        return "maximize"


@dataclass
class WindowSearchSpace:
    """Search space for data window optimization."""

    lookback_min: int = 50
    lookback_max: int = 500
    lookback_grid: list[int] | None = None
    # Window planner mode:
    # - legacy_grid: previous distribution-matching sweep over lookback + val ratio
    # - deterministic_solver: deterministic contiguous train/val windows
    window_selection_mode: Literal["legacy_grid", "deterministic_solver"] = "legacy_grid"
    # Train share bounds used by deterministic solver
    train_share_min: float = 0.70
    train_share_max: float = 0.80
    # Reference distribution mode used by deterministic solver:
    # - all_history: use full history distribution up to train_end
    # - recent_only: use only recent batches from loaded window
    # - blend_recent_all: weighted blend of recent + full history
    reference_distribution_mode: Literal[
        "all_history", "recent_only", "blend_recent_all"
    ] = "blend_recent_all"
    recent_ref_batches: int = 96
    recent_ref_weight: float = 0.70
    # Active-class validation coverage constraints (deterministic solver)
    active_class_min_frac: float = 0.02
    min_val_samples_per_active_class: int = 5
    # Optional embargo controls used by deterministic solver
    embargo_mode: Literal["none", "fixed", "auto_tf"] = "none"
    embargo_train_val_batches: int | None = None
    embargo_val_pred_batches: int | None = None
    # Step size for deterministic lookback candidate sweep
    solver_step_batches: int = 1
    decay_min: float = 0.95
    decay_max: float = 0.999
    min_samples_per_class: int = 50


@dataclass
class FeatureSearchSpace:
    """Search space for feature selection optimization."""

    feature_k_min: int = 20
    feature_k_max: int = 100
    corr_threshold_min: float = 0.7
    corr_threshold_max: float = 0.95
    var_threshold_min: float = 0.001
    var_threshold_max: float = 0.01


@dataclass
class ModelSearchSpace:
    """Search space for LightGBM hyperparameters."""

    learning_rate_min: float = 0.01
    learning_rate_max: float = 0.2
    num_leaves_min: int = 16
    num_leaves_max: int = 128
    max_depth_min: int = 4
    max_depth_max: int = 12
    min_child_samples_min: int = 10
    min_child_samples_max: int = 100
    reg_lambda_min: float = 1e-6
    reg_lambda_max: float = 10.0
    reg_alpha_min: float = 1e-6
    reg_alpha_max: float = 10.0
    subsample_min: float = 0.5
    subsample_max: float = 1.0
    colsample_bytree_min: float = 0.5
    colsample_bytree_max: float = 1.0
    feature_fraction_bynode_min: float = 0.5
    feature_fraction_bynode_max: float = 1.0
    num_boost_round_min: int = 100
    num_boost_round_max: int = 1000


# ============================================================================
# DATA LOADING
# ============================================================================
def load_batch(
    features_dir: Path,
    labels_dir: Path,
    tf: str,
    batch_idx: int,
    target_col: str = "target_4class",
    feature_target_col: str | None = None,
    exclude_tail_pct: float = 0.0,
) -> pl.DataFrame:
    """Load features and join with labels for a single batch."""
    feature_target = feature_target_col or target_col
    feat_path = features_dir / tf / feature_target / f"batch_{batch_idx:04d}.parquet"
    if not feat_path.exists():
        raise FileNotFoundError(f"Features not found: {feat_path}")

    df_feat = pl.read_parquet(feat_path)

    labels_path = labels_dir / tf / f"batch_{batch_idx:04d}.parquet"
    if not labels_path.exists():
        raise FileNotFoundError(f"Labels not found: {labels_path}")

    df_labels = pl.read_parquet(labels_path)
    if target_col not in df_labels.columns:
        raise ValueError(
            f"Target column '{target_col}' not found in labels: {labels_path}. "
            f"Available columns: {df_labels.columns}"
        )
    label_cols = ["timestamp", "batch_id", target_col]
    name_col = None
    target_name_col = f"{target_col}_name"
    if target_name_col in df_labels.columns:
        name_col = target_name_col
    elif target_col == "target_4class" and "target_name" in df_labels.columns:
        name_col = "target_name"
    if name_col:
        label_cols.append(name_col)

    df = df_feat.join(
        df_labels.select(label_cols),
        on=["timestamp", "batch_id"],
        how="left",
    )
    if exclude_tail_pct and exclude_tail_pct > 0 and "bar_in_batch_norm" in df.columns:
        cutoff = 1.0 - exclude_tail_pct
        df = df.filter(pl.col("bar_in_batch_norm") <= cutoff)
    return df


def load_batches_range(
    features_dir: Path,
    labels_dir: Path,
    tf: str,
    start: int,
    end: int,
    target_col: str = "target_4class",
    feature_target_col: str | None = None,
    exclude_tail_pct: float = 0.0,
) -> pl.DataFrame:
    """Load range of batches with features and labels."""
    dfs = []
    for i in range(start, end):
        try:
            dfs.append(
                load_batch(
                    features_dir,
                    labels_dir,
                    tf,
                    i,
                    target_col=target_col,
                    feature_target_col=feature_target_col,
                    exclude_tail_pct=exclude_tail_pct,
                )
            )
        except FileNotFoundError:
            pass
    if not dfs:
        raise ValueError(f"No batches in [{start}, {end})")
    return pl.concat(dfs)


def compute_label_distribution(
    labels_dir: Path,
    tf: str,
    target_col: str,
    exclude_tail_pct: float = 0.0,
) -> pl.DataFrame:
    """Compute class counts and percentages across all batches for a target."""
    label_glob = labels_dir / tf / "batch_*.parquet"
    scan = pl.scan_parquet(str(label_glob))
    schema = scan.collect_schema()
    if target_col not in schema.names():
        return pl.DataFrame()

    cols = [target_col]
    if "bar_in_batch_norm" in schema.names():
        cols.append("bar_in_batch_norm")

    df = scan.select(cols).filter(pl.col(target_col) >= 0)
    if exclude_tail_pct and exclude_tail_pct > 0 and "bar_in_batch_norm" in schema.names():
        cutoff = 1.0 - exclude_tail_pct
        df = df.filter(pl.col("bar_in_batch_norm") <= cutoff)

    counts = (
        df.group_by(target_col)
        .len()
        .collect()
        .sort(target_col)
        .rename({target_col: "class_id", "len": "count"})
    )
    if counts.is_empty():
        return counts

    total = float(counts["count"].sum())
    counts = counts.with_columns((pl.col("count") / total * 100.0).alias("pct"))
    return counts


def compute_class_counts_up_to(
    labels_dir: Path,
    tf: str,
    target_col: str,
    n_classes: int,
    train_end: int,
) -> np.ndarray:
    """Compute class counts from label files up to (and including) train_end batch."""
    counts = np.zeros(n_classes, dtype=np.int64)
    label_glob = labels_dir / tf / "batch_*.parquet"
    scan = pl.scan_parquet(str(label_glob))
    schema = scan.collect_schema()
    if target_col not in schema.names():
        return counts

    df = (
        scan.filter((pl.col("batch_id") <= int(train_end)) & (pl.col(target_col) >= 0))
        .group_by(target_col)
        .len()
        .collect()
    )
    for row in df.iter_rows(named=True):
        c = int(row[target_col])
        if 0 <= c < n_classes:
            counts[c] = int(row["len"])
    return counts


def get_batch_count(labels_dir: Path, tf: str) -> int:
    """Get number of batches for a timeframe."""
    tf_dir = labels_dir / tf
    return len(list(tf_dir.glob("batch_*.parquet")))


def get_valid_batches(
    features_dir: Path,
    labels_dir: Path,
    tf: str,
    min_rows: int | None = None,
    target_col: str = "target_4class",
    feature_target_col: str | None = None,
    exclude_tail_pct: float = 0.0,
    validity_target_col: str | None = None,
) -> list[int]:
    """
    Validate all batches and return list of valid batch indices.

    A batch is valid if it has at least min_rows rows with non-negative labels
    on a selected validity target (default: target_col). This allows using a
    common mask target (for example target_4class) for batch completeness checks
    across multiple targets.

    If min_rows is None, the threshold is inferred from observed per-batch
    valid-row counts:
      1) find the modal valid-row count across batches
      2) set threshold to 70% of that mode
    This supports different labeling regimes (for example full 8h vs first 4h)
    without hardcoded row assumptions.

    Args:
        features_dir: Path to features directory
        labels_dir: Path to labels directory
        tf: Timeframe ("5m" or "15m")
        min_rows: Minimum rows a batch must have (default: auto based on tf)

    Returns:
        Sorted list of valid batch indices
    """
    batch_count = get_batch_count(labels_dir, tf)
    valid_rows_by_batch = {}
    ref_target_col = validity_target_col or target_col

    for batch_idx in range(1, batch_count + 1):
        try:
            df = load_batch(
                features_dir,
                labels_dir,
                tf,
                batch_idx,
                target_col=ref_target_col,
                feature_target_col=feature_target_col,
                # Do not apply tail exclusion when determining batch validity
                exclude_tail_pct=0.0,
            )
            # Count only rows that can actually be used by training/prediction.
            valid_rows = int(len(df.filter(pl.col(ref_target_col) >= 0)))
            valid_rows_by_batch[batch_idx] = valid_rows
        except FileNotFoundError:
            valid_rows_by_batch[batch_idx] = 0

    if min_rows is None:
        nonzero_counts = np.array(
            [v for v in valid_rows_by_batch.values() if v > 0], dtype=np.int32
        )
        if nonzero_counts.size == 0:
            return []

        values, counts = np.unique(nonzero_counts, return_counts=True)
        mode_count = int(values[np.argmax(counts)])
        min_rows = max(1, int(np.floor(mode_count * 0.7)))

    valid_batches = [
        batch_idx
        for batch_idx, valid_rows in valid_rows_by_batch.items()
        if valid_rows >= min_rows
    ]
    return sorted(valid_batches)


# ============================================================================
# FEATURE UTILITIES
# ============================================================================
def get_feature_columns(
    df: pl.DataFrame, target_col: str = "target_4class"
) -> list[str]:
    """Extract feature column names (exclude metadata and labels)."""
    exclude = {
        "timestamp",
        "batch_id",
        target_col,
        "target_name",
    }
    return [c for c in df.columns if c not in exclude and not c.endswith("_right")]


def prepare_features_target(
    df: pl.DataFrame,
    feature_cols: list[str] | None = None,
    target_col: str = "target_4class",
) -> tuple:
    """Prepare features and target from dataframe."""
    if target_col not in df.columns:
        raise ValueError(f"Target column not found: {target_col}")

    df = df.filter(pl.col(target_col) >= 0)

    if len(df) == 0:
        return None, None, None, None

    if feature_cols is None:
        feature_cols = get_feature_columns(df, target_col)

    feature_cols = [c for c in feature_cols if c in df.columns]

    X = df.select(feature_cols).to_numpy()
    y = df[target_col].to_numpy().astype(int)
    timestamps = df["timestamp"].to_list()

    return X, y, feature_cols, timestamps


def apply_sample_weights(n_samples: int, decay_weight: float) -> np.ndarray:
    """Generate exponential decay weights for samples (newer = higher weight)."""
    indices = np.arange(n_samples)
    weights = decay_weight ** (n_samples - indices - 1)
    return weights


def select_features_by_mi(
    X: np.ndarray,
    y: np.ndarray,
    feature_cols: list[str],
    k: int,
    random_state: int = 42,
) -> list[str]:
    """Select top-K features by mutual information."""
    X_clean = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    mi_scores = mutual_info_classif(
        X_clean, y, random_state=random_state, n_neighbors=5
    )
    top_k_idx = np.argsort(mi_scores)[-k:]
    return [feature_cols[i] for i in top_k_idx]


def drop_correlated_features(
    X: np.ndarray, feature_cols: list[str], threshold: float = 0.9
) -> list[str]:
    """Drop features that are highly correlated with each other."""
    X_clean = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    # Filter zero-variance features first
    variances = np.var(X_clean, axis=0)
    valid_mask = variances > 1e-10

    if not valid_mask.any():
        return []

    valid_indices = np.where(valid_mask)[0]
    X_valid = X_clean[:, valid_mask]
    valid_features = [feature_cols[i] for i in valid_indices]

    corr_matrix = np.corrcoef(X_valid.T)

    to_drop = set()
    n_valid = len(valid_features)

    for i in range(n_valid):
        if i in to_drop:
            continue
        for j in range(i + 1, n_valid):
            if j in to_drop:
                continue
            if abs(corr_matrix[i, j]) > threshold:
                to_drop.add(j)

    return [valid_features[i] for i in range(n_valid) if i not in to_drop]


def drop_low_variance_features(
    X: np.ndarray, feature_cols: list[str], threshold: float = 0.001
) -> list[str]:
    """Drop features with variance below threshold."""
    variances = np.nanvar(X, axis=0)
    mask = variances >= threshold
    return [feature_cols[i] for i in range(len(feature_cols)) if mask[i]]


# ============================================================================
# CLASS WEIGHTING
# ============================================================================
def compute_class_weights(
    y: np.ndarray, method: Literal["none", "balanced", "sqrt", "log"] = "balanced"
) -> dict[int, float] | None:
    """Compute class weights for imbalanced classification."""
    if method == "none":
        return None

    classes, counts = np.unique(y, return_counts=True)
    n_samples = len(y)
    n_classes = len(classes)

    if method == "balanced":
        weights = n_samples / (n_classes * counts)
    elif method == "sqrt":
        weights = np.sqrt(n_samples / (n_classes * counts))
    elif method == "log":
        weights = np.log1p(n_samples / counts)
    else:
        raise ValueError(f"Unknown method: {method}")

    return {int(c): float(w) for c, w in zip(classes, weights)}


def weights_to_sample_weights(
    y: np.ndarray, class_weights: dict[int, float] | None
) -> np.ndarray | None:
    """Convert class weights to per-sample weights."""
    if class_weights is None:
        return None
    return np.array([class_weights.get(int(yi), 1.0) for yi in y])


# ============================================================================
# DIRECTIONAL METRICS
# ============================================================================
def _direction_from_name(name: str | None) -> int | None:
    if not name:
        return None
    up_keys = ("UP", "ABOVE", "BULL")
    down_keys = ("DOWN", "BELOW", "BEAR")
    name_u = name.upper()
    if any(k in name_u for k in down_keys):
        return 0
    if any(k in name_u for k in up_keys):
        return 1
    return None


def _direction_lookup(class_names: list[str] | tuple) -> list[int]:
    """Map class ids to direction ids (0=down, 1=up)."""
    n_classes = len(class_names)
    directions = []
    for i in range(n_classes):
        name = class_names[i] if i < len(class_names) else None
        directions.append(_direction_from_name(name))

    if all(d is None for d in directions):
        # Fallback when labels have no directional names.
        if n_classes == 2:
            directions = [0, 1]
        else:
            mid = max(1, n_classes // 2)
            directions = [0 if i < mid else 1 for i in range(n_classes)]

    # Replace unknowns with down-side fallback for determinism.
    return [0 if d is None else int(d) for d in directions]


def _to_direction_series(
    y: np.ndarray, class_names: list[str] | tuple
) -> np.ndarray:
    """Convert class ids to direction ids (0/1)."""
    lookup = _direction_lookup(class_names)
    return np.array([lookup[int(c)] for c in y], dtype=np.int8)


def compute_directional_accuracy(
    y_true: np.ndarray, y_pred: np.ndarray, class_names: list[str] | tuple
) -> float:
    """Directional accuracy: counts correct if direction matches (up vs down)."""
    dir_true = _to_direction_series(y_true, class_names)
    dir_pred = _to_direction_series(y_pred, class_names)
    if len(dir_true) == 0:
        return 0.0
    return float((dir_true == dir_pred).mean())


def _direction_class_ids(
    class_names: list[str] | tuple, direction: int
) -> list[int]:
    directions = _direction_lookup(class_names)
    return [i for i, d in enumerate(directions) if d == direction]


def compute_directional_macro_f1(
    y_true: np.ndarray, y_pred: np.ndarray, class_names: list[str] | tuple, direction: int
) -> float:
    """Macro-F1 over classes belonging to a direction (0=down, 1=up)."""
    class_ids = _direction_class_ids(class_names, direction)
    if not class_ids:
        return 0.0
    return float(
        f1_score(
            y_true,
            y_pred,
            labels=class_ids,
            average="macro",
            zero_division=0,
        )
    )


def compute_directional_precision(
    y_true: np.ndarray, y_pred: np.ndarray, class_names: list[str] | tuple, direction: int
) -> float:
    """Directional precision for UP (1) or DOWN (0)."""
    dir_true = _to_direction_series(y_true, class_names)
    dir_pred = _to_direction_series(y_pred, class_names)
    pred_mask = dir_pred == int(direction)
    if pred_mask.sum() == 0:
        return 0.0
    tp = ((dir_true == int(direction)) & pred_mask).sum()
    return float(tp / pred_mask.sum())


def compute_directional_recall(
    y_true: np.ndarray, y_pred: np.ndarray, class_names: list[str] | tuple, direction: int
) -> float:
    """Directional recall for UP (1) or DOWN (0)."""
    dir_true = _to_direction_series(y_true, class_names)
    dir_pred = _to_direction_series(y_pred, class_names)
    true_mask = dir_true == int(direction)
    if true_mask.sum() == 0:
        return 0.0
    tp = ((dir_pred == int(direction)) & true_mask).sum()
    return float(tp / true_mask.sum())


def compute_cross_direction_error_rate(
    y_true: np.ndarray, y_pred: np.ndarray, class_names: list[str] | tuple
) -> float:
    """Rate of predictions where UP/DOWN direction is wrong."""
    return float(1.0 - compute_directional_accuracy(y_true, y_pred, class_names))


def stratified_split_indices(
    y: np.ndarray, val_ratio: float, seed: int = 42
) -> tuple[np.ndarray, np.ndarray]:
    """Return stratified train/val indices preserving class distribution."""
    rng = np.random.default_rng(seed)
    train_idx = []
    val_idx = []
    classes = np.unique(y)
    for c in classes:
        idx = np.where(y == c)[0]
        if len(idx) == 0:
            continue
        rng.shuffle(idx)
        n = len(idx)
        # Keep at least one sample in train and val whenever class count allows.
        if n == 1:
            n_val = 0
        else:
            n_val = int(round(n * val_ratio))
            n_val = max(1, min(n_val, n - 1))
        val_idx.extend(idx[:n_val])
        train_idx.extend(idx[n_val:])
    train_idx = np.array(train_idx, dtype=int)
    val_idx = np.array(val_idx, dtype=int)
    rng.shuffle(train_idx)
    rng.shuffle(val_idx)
    return train_idx, val_idx


def balanced_resample_indices(
    y: np.ndarray,
    strategy: Literal["upsample", "downsample"],
    seed: int = 42,
) -> np.ndarray:
    """Return indices that balance classes by up/down-sampling within y."""
    rng = np.random.default_rng(seed)
    classes = np.unique(y)
    class_indices = [np.where(y == c)[0] for c in classes]
    # Drop empty classes (should not happen for np.unique, but guard anyway)
    class_indices = [idx for idx in class_indices if len(idx) > 0]
    if not class_indices:
        return np.arange(len(y), dtype=int)

    if strategy == "downsample":
        target = min(len(idx) for idx in class_indices)
        sampled = [
            rng.choice(idx, size=target, replace=False)
            for idx in class_indices
        ]
    elif strategy == "upsample":
        target = max(len(idx) for idx in class_indices)
        sampled = [
            rng.choice(idx, size=target, replace=True)
            for idx in class_indices
        ]
    else:
        raise ValueError(f"Unknown balance strategy: {strategy}")

    out = np.concatenate(sampled)
    rng.shuffle(out)
    return out


def estimate_lookback_and_split(
    df: pl.DataFrame,
    target_col: str,
    n_classes: int,
    lookback_min: int,
    lookback_max: int,
    lookback_grid: list[int] | None = None,
    min_samples_per_class: int = 0,
    preferred_train_split: float = 0.85,
    val_ratio_grid: list[float] | None = None,
    reference_class_counts: np.ndarray | list[int] | None = None,
    window_selection_mode: Literal["legacy_grid", "deterministic_solver"] = "legacy_grid",
    train_share_min: float = 0.70,
    train_share_max: float = 0.80,
    embargo_mode: Literal["none", "fixed", "auto_tf"] = "none",
    embargo_train_val_batches: int | None = None,
    embargo_val_pred_batches: int | None = None,
    solver_step_batches: int = 1,
    reference_distribution_mode: Literal[
        "all_history", "recent_only", "blend_recent_all"
    ] = "blend_recent_all",
    recent_ref_batches: int = 96,
    recent_ref_weight: float = 0.70,
    active_class_min_frac: float = 0.02,
    min_val_samples_per_active_class: int = 5,
) -> dict:
    """
    Estimate lookback and train/val split by matching class distributions.

    The selected window and split minimize distribution mismatch between:
    - overall available data distribution (up to current train_end),
    - train split distribution,
    - validation split distribution.

    Uses only rows with target >= 0 and only batches already loaded for the step.
    """
    def _prepare_counts() -> tuple[list[int], np.ndarray, np.ndarray]:
        df_valid = df.filter(pl.col(target_col) >= 0).select(["batch_id", target_col])
        if len(df_valid) == 0:
            raise ValueError(
                f"No valid rows for target '{target_col}' while estimating window"
            )

        batch_ids = sorted(df_valid["batch_id"].unique().to_list())
        n_batches = len(batch_ids)
        if n_batches < 2:
            raise ValueError(
                f"Not enough batches ({n_batches}) to estimate lookback/split for target '{target_col}'"
            )

        counts_mat = np.zeros((n_batches, n_classes), dtype=np.int64)
        batch_pos = {int(b): i for i, b in enumerate(batch_ids)}
        counts_df = (
            df_valid.group_by(["batch_id", target_col])
            .len()
            .rename({"len": "count"})
            .sort(["batch_id", target_col])
        )
        for row in counts_df.iter_rows(named=True):
            b = int(row["batch_id"])
            c = int(row[target_col])
            if 0 <= c < n_classes:
                counts_mat[batch_pos[b], c] = int(row["count"])

        if reference_class_counts is None:
            overall_counts = counts_mat.sum(axis=0)
        else:
            overall_counts = np.asarray(reference_class_counts, dtype=np.int64).copy()
            if overall_counts.shape[0] != n_classes:
                raise ValueError(
                    f"reference_class_counts length mismatch: expected {n_classes}, "
                    f"got {overall_counts.shape[0]}"
                )
        if int(overall_counts.sum()) == 0:
            raise ValueError(
                f"Overall class counts are zero for target '{target_col}' while estimating window"
            )
        return batch_ids, counts_mat, overall_counts

    def _dist(counts: np.ndarray) -> np.ndarray:
        total = float(counts.sum())
        if total <= 0:
            return np.zeros_like(counts, dtype=np.float64)
        return counts.astype(np.float64) / total

    def _mse(a: np.ndarray, b: np.ndarray) -> float:
        d = a - b
        return float(np.mean(d * d))

    def _resolve_embargo(
        mode: Literal["none", "fixed", "auto_tf"],
        tv: int | None,
        vp: int | None,
    ) -> tuple[int, int]:
        if mode == "none":
            return 0, 0
        if mode == "fixed":
            return int(max(0, tv or 0)), int(max(0, vp or 0))
        # auto_tf: conservative defaults independent of target
        return int(max(0, tv if tv is not None else 1)), int(
            max(0, vp if vp is not None else 1)
        )

    def _estimate_legacy(
        batch_ids: list[int],
        counts_mat: np.ndarray,
        overall_counts: np.ndarray,
    ) -> dict:
        nonlocal val_ratio_grid
        if val_ratio_grid is None:
            val_ratio_grid = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35]

        n_batches = len(batch_ids)
        overall_dist = _dist(overall_counts)
        cum = np.cumsum(counts_mat, axis=0)

        max_lb = min(int(lookback_max), n_batches)
        min_lb = max(2, int(lookback_min))
        if min_lb > max_lb:
            raise ValueError(
                f"lookback range invalid after clipping: min={min_lb}, max={max_lb}, "
                f"available_batches={n_batches}"
            )

        if lookback_grid:
            candidate_lookbacks = sorted(
                {int(v) for v in lookback_grid if min_lb <= int(v) <= max_lb}
            )
        else:
            candidate_lookbacks = list(range(min_lb, max_lb + 1))

        if not candidate_lookbacks:
            raise ValueError("No candidate lookback values after filtering")

        best = None
        for lookback in candidate_lookbacks:
            start_idx = n_batches - lookback
            window_counts = cum[-1] - (cum[start_idx - 1] if start_idx > 0 else 0)
            if min_samples_per_class and (window_counts < min_samples_per_class).any():
                continue

            window_dist = _dist(window_counts)
            window_mse = _mse(window_dist, overall_dist)
            window_total = int(window_counts.sum())
            if window_total <= 0:
                continue

            for val_ratio in val_ratio_grid:
                val_batches = max(1, int(round(lookback * float(val_ratio))))
                if val_batches >= lookback:
                    val_batches = lookback - 1
                if val_batches < 1:
                    continue

                train_batches = lookback - val_batches
                train_end_idx = start_idx + train_batches - 1
                val_start_idx = train_end_idx + 1

                train_counts = (
                    cum[train_end_idx] - (cum[start_idx - 1] if start_idx > 0 else 0)
                )
                val_counts = window_counts - train_counts
                train_total = int(train_counts.sum())
                val_total = int(val_counts.sum())
                if train_total <= 0 or val_total <= 0:
                    continue

                train_dist = _dist(train_counts)
                val_dist = _dist(val_counts)
                train_mse = _mse(train_dist, overall_dist)
                val_mse = _mse(val_dist, overall_dist)
                missing_train = int((train_counts == 0).sum())
                missing_val = int((val_counts == 0).sum())
                coverage_penalty = 10.0 * (missing_train + missing_val)
                train_share = train_total / float(window_total)
                ratio_penalty = 0.10 * abs(train_share - float(preferred_train_split))

                score = (
                    train_mse
                    + val_mse
                    + 0.5 * window_mse
                    + ratio_penalty
                    + coverage_penalty
                )
                candidate = {
                    "score": float(score),
                    "window_selection_mode": "legacy_grid_v1",
                    "lookback_batches": int(lookback),
                    "train_val_split": float(train_share),
                    "val_ratio": float(1.0 - train_share),
                    "window_start_batch": int(batch_ids[start_idx]),
                    "window_end_batch": int(batch_ids[-1]),
                    "train_start_batch": int(batch_ids[start_idx]),
                    "train_end_batch": int(batch_ids[train_end_idx]),
                    "val_start_batch": int(batch_ids[val_start_idx]),
                    "val_end_batch": int(batch_ids[-1]),
                    "embargo_train_val_batches": 0,
                    "embargo_val_pred_batches": 0,
                    "window_class_counts": window_counts.astype(int).tolist(),
                    "train_class_counts": train_counts.astype(int).tolist(),
                    "val_class_counts": val_counts.astype(int).tolist(),
                    "overall_class_counts": overall_counts.astype(int).tolist(),
                    "missing_classes_train": missing_train,
                    "missing_classes_val": missing_val,
                    "distribution_mse_train": float(train_mse),
                    "distribution_mse_val": float(val_mse),
                    "distribution_mse_window": float(window_mse),
                    "distribution_mse_train_val": float(_mse(train_dist, val_dist)),
                }
                if best is None or candidate["score"] < best["score"]:
                    best = candidate
        if best is None:
            raise ValueError(
                "Could not estimate lookback/split with current constraints "
                f"(target={target_col}, lookback_min={lookback_min}, lookback_max={lookback_max}, "
                f"min_samples_per_class={min_samples_per_class})"
            )
        return best

    def _estimate_deterministic(
        batch_ids: list[int],
        counts_mat: np.ndarray,
        overall_counts: np.ndarray,
    ) -> dict:
        n_batches = len(batch_ids)
        overall_dist = _dist(overall_counts)
        recent_span = max(1, min(int(recent_ref_batches), n_batches))
        recent_counts = counts_mat[-recent_span:].sum(axis=0)
        recent_dist = _dist(recent_counts)
        ref_mode = str(reference_distribution_mode or "blend_recent_all")
        if ref_mode == "all_history":
            ref_dist = overall_dist
        elif ref_mode == "recent_only":
            ref_dist = recent_dist
        else:
            w = float(np.clip(recent_ref_weight, 0.0, 1.0))
            ref_dist = (w * recent_dist) + ((1.0 - w) * overall_dist)

        active_frac = float(max(0.0, min(1.0, active_class_min_frac)))
        active_ids = [i for i in range(n_classes) if ref_dist[i] >= active_frac]
        if not active_ids:
            # Keep at least one active class to avoid a no-op constraint.
            active_ids = [int(np.argmax(ref_dist))]
        min_val_active = max(1, int(min_val_samples_per_active_class))

        cum = np.cumsum(counts_mat, axis=0)

        min_lb = max(2, int(lookback_min))
        max_lb = min(int(lookback_max), n_batches)
        if min_lb > max_lb:
            raise ValueError(
                f"lookback range invalid after clipping: min={min_lb}, max={max_lb}, "
                f"available_batches={n_batches}"
            )
        step = max(1, int(solver_step_batches))
        candidate_lookbacks = list(range(min_lb, max_lb + 1, step))
        if candidate_lookbacks[-1] != max_lb:
            candidate_lookbacks.append(max_lb)

        train_share_lo = float(min(train_share_min, train_share_max))
        train_share_hi = float(max(train_share_min, train_share_max))
        train_share_lo = min(max(train_share_lo, 0.5), 0.95)
        train_share_hi = min(max(train_share_hi, train_share_lo), 0.99)
        ratio_target = 0.5 * (train_share_lo + train_share_hi)

        embargo_tv, embargo_vp = _resolve_embargo(
            embargo_mode, embargo_train_val_batches, embargo_val_pred_batches
        )

        best = None
        last_idx = n_batches - 1
        val_end_idx = last_idx - embargo_vp
        if val_end_idx < 1:
            raise ValueError(
                f"Embargo too large for available data: embargo_val_pred_batches={embargo_vp}, "
                f"available_batches={n_batches}"
            )

        for lookback in candidate_lookbacks:
            val_min = max(1, int(np.ceil(lookback * (1.0 - train_share_hi))))
            val_max = min(lookback - 1, int(np.floor(lookback * (1.0 - train_share_lo))))
            if val_min > val_max:
                continue

            for val_batches in range(val_min, val_max + 1):
                train_batches = lookback - val_batches
                if train_batches < 1:
                    continue

                val_start_idx = val_end_idx - val_batches + 1
                train_end_idx = val_start_idx - embargo_tv - 1
                train_start_idx = train_end_idx - train_batches + 1
                if train_start_idx < 0 or val_start_idx < 0:
                    continue
                if train_end_idx < train_start_idx or val_end_idx < val_start_idx:
                    continue

                train_counts = (
                    cum[train_end_idx]
                    - (cum[train_start_idx - 1] if train_start_idx > 0 else 0)
                )
                val_counts = (
                    cum[val_end_idx]
                    - (cum[val_start_idx - 1] if val_start_idx > 0 else 0)
                )
                window_counts = train_counts + val_counts
                if int(window_counts.sum()) <= 0:
                    continue

                # Hard train coverage constraint for stability.
                if min_samples_per_class and (train_counts < min_samples_per_class).any():
                    continue

                train_total = int(train_counts.sum())
                val_total = int(val_counts.sum())
                if train_total <= 0 or val_total <= 0:
                    continue

                # Enforce minimal validation support for active classes.
                if any(int(val_counts[c]) < min_val_active for c in active_ids):
                    continue

                train_dist = _dist(train_counts)
                val_dist = _dist(val_counts)
                window_dist = _dist(window_counts)
                train_mse = _mse(train_dist, ref_dist)
                val_mse = _mse(val_dist, ref_dist)
                window_mse = _mse(window_dist, ref_dist)
                train_val_mse = _mse(train_dist, val_dist)

                missing_train = int((train_counts == 0).sum())
                missing_val = int((val_counts == 0).sum())
                coverage_penalty = 10.0 * missing_train + 6.0 * missing_val
                train_share = train_total / float(train_total + val_total)
                ratio_penalty = 0.05 * abs(train_share - ratio_target)

                score = (
                    train_mse
                    + val_mse
                    + 0.40 * window_mse
                    + 0.20 * train_val_mse
                    + ratio_penalty
                    + coverage_penalty
                )

                candidate = {
                    "score": float(score),
                    "window_selection_mode": "deterministic_solver_v1",
                    "lookback_batches": int(lookback),
                    "train_val_split": float(train_share),
                    "val_ratio": float(1.0 - train_share),
                    "window_start_batch": int(batch_ids[train_start_idx]),
                    "window_end_batch": int(batch_ids[val_end_idx]),
                    "train_start_batch": int(batch_ids[train_start_idx]),
                    "train_end_batch": int(batch_ids[train_end_idx]),
                    "val_start_batch": int(batch_ids[val_start_idx]),
                    "val_end_batch": int(batch_ids[val_end_idx]),
                    "embargo_train_val_batches": int(embargo_tv),
                    "embargo_val_pred_batches": int(embargo_vp),
                    "reference_distribution_mode": ref_mode,
                    "recent_ref_batches": int(recent_span),
                    "recent_ref_weight": float(
                        np.clip(recent_ref_weight, 0.0, 1.0)
                    ),
                    "active_class_min_frac": float(active_frac),
                    "min_val_samples_per_active_class": int(min_val_active),
                    "active_class_ids": [int(c) for c in active_ids],
                    "reference_distribution": ref_dist.astype(float).tolist(),
                    "recent_class_counts": recent_counts.astype(int).tolist(),
                    "window_class_counts": window_counts.astype(int).tolist(),
                    "train_class_counts": train_counts.astype(int).tolist(),
                    "val_class_counts": val_counts.astype(int).tolist(),
                    "overall_class_counts": overall_counts.astype(int).tolist(),
                    "missing_classes_train": missing_train,
                    "missing_classes_val": missing_val,
                    "distribution_mse_train": float(train_mse),
                    "distribution_mse_val": float(val_mse),
                    "distribution_mse_window": float(window_mse),
                    "distribution_mse_train_val": float(train_val_mse),
                }
                if best is None or candidate["score"] < best["score"]:
                    best = candidate

        if best is None:
            raise ValueError(
                "Could not estimate deterministic lookback/split with current constraints "
                f"(target={target_col}, lookback_min={lookback_min}, lookback_max={lookback_max}, "
                f"train_share_min={train_share_lo}, train_share_max={train_share_hi}, "
                f"embargo_mode={embargo_mode}, min_samples_per_class={min_samples_per_class}, "
                f"ref_mode={reference_distribution_mode}, recent_ref_batches={recent_ref_batches}, "
                f"active_class_min_frac={active_class_min_frac}, "
                f"min_val_samples_per_active_class={min_val_samples_per_active_class})"
            )
        return best

    batch_ids, counts_mat, overall_counts = _prepare_counts()
    mode = str(window_selection_mode or "legacy_grid")
    if mode == "deterministic_solver":
        return _estimate_deterministic(batch_ids, counts_mat, overall_counts)
    return _estimate_legacy(batch_ids, counts_mat, overall_counts)


# ============================================================================
# PERSISTENCE
# ============================================================================
def format_timestamp_for_folder(ts: str | datetime) -> str:
    """Format timestamp for folder naming."""
    if isinstance(ts, datetime):
        return ts.strftime("%Y-%m-%dT%H-%M-%S")
    return ts.replace(" ", "T").replace(":", "-")


def save_step_results(
    opt_result: dict,
    model: lgb.Booster,
    step_dir: Path,
    timeframe: str,
    step: int,
    start_timestamp: str | datetime,
    end_timestamp: str | datetime,
    model_name: str | None = None,
    target_col: str = "target_4class",
    class_names: list[str] | None = None,
) -> dict[str, Path]:
    """Save all optimization results for a prediction step."""
    saved_files = {}

    # 1. Save optimization.json
    result_json = {
        "step": step,
        "timeframe": timeframe,
        "model_name": model_name,
        "target": target_col,
        "class_names": class_names or [],
        "optimization_timestamp": datetime.now().isoformat(),
        "batch_start": str(start_timestamp),
        "batch_end": str(end_timestamp),
        "best_accuracy": float(opt_result["best_accuracy"]),
        "n_features": int(opt_result["n_features"]),
        "selected_features": opt_result["selected_features"],
        "lookback_batches": int(opt_result["lookback_batches"]),
        "train_val_split": float(opt_result.get("train_val_split", 0.0)),
        "val_ratio": float(opt_result.get("val_ratio", 0.0)),
        "window_selection_mode": opt_result.get("window_selection_mode"),
        "train_start_batch": (
            int(opt_result["train_start_batch"])
            if opt_result.get("train_start_batch") is not None
            else None
        ),
        "train_end_batch": (
            int(opt_result["train_end_batch"])
            if opt_result.get("train_end_batch") is not None
            else None
        ),
        "val_start_batch": (
            int(opt_result["val_start_batch"])
            if opt_result.get("val_start_batch") is not None
            else None
        ),
        "val_end_batch": (
            int(opt_result["val_end_batch"])
            if opt_result.get("val_end_batch") is not None
            else None
        ),
        "embargo_train_val_batches": (
            int(opt_result["embargo_train_val_batches"])
            if opt_result.get("embargo_train_val_batches") is not None
            else None
        ),
        "embargo_val_pred_batches": (
            int(opt_result["embargo_val_pred_batches"])
            if opt_result.get("embargo_val_pred_batches") is not None
            else None
        ),
        "window_distribution_score": float(
            opt_result.get("window_distribution_score", 0.0)
        ),
        "distribution_mse_train": float(opt_result.get("distribution_mse_train", 0.0)),
        "distribution_mse_val": float(opt_result.get("distribution_mse_val", 0.0)),
        "distribution_mse_window": float(opt_result.get("distribution_mse_window", 0.0)),
        "distribution_mse_train_val": float(
            opt_result.get("distribution_mse_train_val", 0.0)
        ),
        "missing_classes_train": int(opt_result.get("missing_classes_train", 0)),
        "missing_classes_val": int(opt_result.get("missing_classes_val", 0)),
        "directional_accuracy": (
            float(opt_result["directional_accuracy"])
            if opt_result.get("directional_accuracy") is not None
            else None
        ),
        "directional_precision_up": (
            float(opt_result["directional_precision_up"])
            if opt_result.get("directional_precision_up") is not None
            else None
        ),
        "directional_precision_down": (
            float(opt_result["directional_precision_down"])
            if opt_result.get("directional_precision_down") is not None
            else None
        ),
        "cross_direction_error": (
            float(opt_result["cross_direction_error"])
            if opt_result.get("cross_direction_error") is not None
            else None
        ),
        "leakage_guard": opt_result.get("leakage_guard"),
        "reference_distribution_mode": opt_result.get("reference_distribution_mode"),
        "recent_ref_batches": (
            int(opt_result["recent_ref_batches"])
            if opt_result.get("recent_ref_batches") is not None
            else None
        ),
        "recent_ref_weight": (
            float(opt_result["recent_ref_weight"])
            if opt_result.get("recent_ref_weight") is not None
            else None
        ),
        "active_class_min_frac": (
            float(opt_result["active_class_min_frac"])
            if opt_result.get("active_class_min_frac") is not None
            else None
        ),
        "min_val_samples_per_active_class": (
            int(opt_result["min_val_samples_per_active_class"])
            if opt_result.get("min_val_samples_per_active_class") is not None
            else None
        ),
        "active_class_ids": [int(c) for c in opt_result.get("active_class_ids", [])],
        "reference_distribution": [
            float(v) for v in opt_result.get("reference_distribution", [])
        ],
        "recent_class_counts": [
            int(v) for v in opt_result.get("recent_class_counts", [])
        ],
        "window_class_counts": [
            int(v) for v in opt_result.get("window_class_counts", [])
        ],
        "train_class_counts": [
            int(v) for v in opt_result.get("train_class_counts", [])
        ],
        "val_class_counts": [int(v) for v in opt_result.get("val_class_counts", [])],
        "total_class_counts": [
            int(v) for v in opt_result.get("total_class_counts", [])
        ],
        "decay_weight": float(opt_result["decay_weight"]),
        "class_weight_method": opt_result["class_weight_method"],
        "num_boost_round": int(opt_result["num_boost_round"]),
        "lgb_params": {
            k: float(v) if isinstance(v, (int, float)) else v
            for k, v in opt_result["lgb_params"].items()
        },
    }

    opt_path = step_dir / "optimization.json"
    with open(opt_path, "w") as f:
        json.dump(result_json, f, indent=2)
    saved_files["optimization"] = opt_path

    # 2. Save model
    model_path = step_dir / "model.txt"
    model.save_model(str(model_path))
    saved_files["model"] = model_path

    # 3. Save class metrics as parquet
    class_metrics_data = []
    per_class_acc = opt_result.get("per_class_accuracy", {})
    per_class_count = opt_result.get("per_class_count", {})

    if not class_names:
        n_classes = max(per_class_acc.keys() | per_class_count.keys(), default=7) + 1
        class_names = [f"class_{i}" for i in range(n_classes)]

    for class_id in range(len(class_names)):
        class_metrics_data.append(
            {
                "class_id": class_id,
                "class_name": class_names[class_id],
                "accuracy": per_class_acc.get(class_id, 0.0),
                "val_count": per_class_count.get(class_id, 0),
            }
        )

    metrics_df = pl.DataFrame(class_metrics_data)
    metrics_path = step_dir / "class_metrics.parquet"
    metrics_df.write_parquet(metrics_path)
    saved_files["class_metrics"] = metrics_path

    return saved_files


def export_study_trials(
    study: optuna.study.Study,
    step_dir: Path,
    model_name: str,
    timeframe: str,
    target_col: str,
    step: int,
    train_end: int,
    pred_batch: int,
    start_timestamp: str | datetime,
    end_timestamp: str | datetime,
    feature_target_col: str | None = None,
) -> dict[str, Path]:
    """Export all Optuna trial params/metrics for a step to parquet + jsonl."""
    if study is None:
        return {}

    trials = study.trials
    if not trials:
        return {}

    # Collect all param and attr keys across trials
    param_keys = set()
    attr_keys = set()
    for t in trials:
        param_keys.update(t.params.keys())
        attr_keys.update(t.user_attrs.keys())

    param_keys = sorted(param_keys)
    attr_keys = sorted(attr_keys)

    best_number = None
    try:
        best_number = study.best_trial.number
    except Exception:
        best_number = None

    records = []
    for t in trials:
        record = {
            "step": int(step),
            "model_name": model_name,
            "timeframe": timeframe,
            "target": target_col,
            "feature_target": feature_target_col or target_col,
            "train_end": int(train_end),
            "pred_batch": int(pred_batch),
            "batch_start": str(start_timestamp),
            "batch_end": str(end_timestamp),
            "trial_number": int(t.number),
            "trial_id": int(t._trial_id) if hasattr(t, "_trial_id") else None,
            "state": str(t.state),
            "value": float(t.value) if t.value is not None else None,
            "datetime_start": t.datetime_start.isoformat()
            if t.datetime_start
            else None,
            "datetime_complete": t.datetime_complete.isoformat()
            if t.datetime_complete
            else None,
            "duration_seconds": (
                (t.datetime_complete - t.datetime_start).total_seconds()
                if t.datetime_start and t.datetime_complete
                else None
            ),
            "is_best": (best_number is not None and t.number == best_number),
        }

        for k in param_keys:
            record[f"param_{k}"] = t.params.get(k)

        for k in attr_keys:
            v = t.user_attrs.get(k)
            if isinstance(v, (dict, list, tuple)):
                v = json.dumps(v)
            record[f"attr_{k}"] = v

        records.append(record)

    df = pl.DataFrame(records)

    saved = {}
    parquet_path = step_dir / "trials.parquet"
    df.write_parquet(parquet_path)
    saved["trials_parquet"] = parquet_path

    jsonl_path = step_dir / "trials.jsonl"
    with open(jsonl_path, "w") as f:
        for row in records:
            f.write(json.dumps(row, default=str) + "\n")
    saved["trials_jsonl"] = jsonl_path

    return saved
