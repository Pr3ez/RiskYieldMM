"""
HTF Feature Optimization (Causal, Streaming, Rolling Rank-Winsorize)
====================================================================

Optimizes HTF features using CORRECT winsorize-rank:
1. Rolling rank: u_t = percentile of x_t vs past L values
2. Clip ranks: u_t' = clip(u_t, p_min, p_max)
3. Post-transform: uniform, signed, or gaussianized

KEY DESIGN DECISIONS:
- Rolling window (not expanding) for bounded memory O(L) per feature
- State carries across batches (no reset at batch boundaries)
- Walk-forward validation on EARLY data only for hyperparameter selection
- Grid search over: window, clip bounds, post-transform

CAUSAL GUARANTEE:
    At row t, rank is computed from t-L..t-1 only (not including t).
    No future leakage.

Usage:
    from scripts.feature_engineering.optimize_htf_features import (
        optimize_htf_features,
        HTFOptimizationConfig,
    )

    config = HTFOptimizationConfig(
        timeframes=["5m", "15m", "1h"],
        targets=["target_long", "target_short"],
    )
    results = optimize_htf_features(config)
"""

from __future__ import annotations

import gc
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from scipy.stats import norm, spearmanr
from sklearn.feature_selection import mutual_info_classif

from scripts.analysis.optimizers.rolling_rank_winsorize import (
    RollingRankWinsorizeTransformer,
    get_winsorize_rank_candidates,
    _rolling_rank_streaming_matrix_from_start,
)
from scripts.feature_engineering.htf_feature_acceptance import (
    FINAL_OUTPUT_FEATURE_POLICY_SIGNATURE,
    FINAL_OUTPUT_FEATURE_POLICY_VERSION,
    FINAL_OUTPUT_LABEL_ONLY_COLUMNS,
    get_final_output_excluded_columns,
)


OPTIMIZER_SELECTION_IMPLEMENTATION_VERSION = "rank-reuse-v1"


@dataclass
class HTFOptimizationConfig:
    """Configuration for HTF feature optimization."""

    # Data paths
    project_root: Path = field(
        default_factory=lambda: Path(__file__).parent.parent.parent
    )
    htf_features_dir_override: Path | None = None
    htf_labels_dir_override: Path | None = None
    htf_optimized_dir_override: Path | None = None

    # Timeframes to process
    timeframes: list[str] = field(default_factory=lambda: ["5m", "15m", "1h"])

    # Targets to optimize for
    targets: list[str] = field(default_factory=lambda: ["target_long", "target_short"])

    # Walk-forward validation settings
    n_early_batches: int = 200  # Use FIRST 200 batches chronologically for tuning
    n_val_folds: int = 3  # Number of walk-forward validation folds

    # Stability penalty for config selection
    stability_lambda: float = 0.5  # score = mean(IC) - lambda * std(IC)

    # Output control
    save_results: bool = True
    recompute: bool = False
    incremental_update: bool = True
    max_state_snapshots: int = 8

    @property
    def htf_features_dir(self) -> Path:
        return self.htf_features_dir_override or (self.project_root / "data" / "htf_features")

    @property
    def htf_labels_dir(self) -> Path:
        return self.htf_labels_dir_override or (self.project_root / "data" / "htf_4class_labels")

    @property
    def htf_optimized_dir(self) -> Path:
        return self.htf_optimized_dir_override or (self.project_root / "data" / "htf_optimized")


OPTIMIZER_META_COLS = {
    "timestamp",
    "batch_id",
    "target_long",
    "target_short",
    "target_4class",
    "target_breakfree",
    "target_name",
    "period_8h_start",
    "batch_family",
    "family_batch_id",
    "family_period_start",
    "family_period_end",
    "family_bar_pos",
    "source_base_batch_id",
    "source_base_period_start",
    "source_half_in_base",
    "is_label_half",
    "batch_regime",
    "batch_duration_hours",
    "family_shift_hours",
    "anchor_utc",
    "entry_window_hours",
}


def _non_nullish_count_expr(col: str, dtype: pl.DataType) -> pl.Expr:
    expr = pl.col(col).is_not_null()
    if dtype.is_float():
        expr = expr & ~pl.col(col).is_nan()
    return expr.sum().alias(col)


def get_feature_cols(df: pl.DataFrame, *, output_stage: str = "optimized") -> list[str]:
    """
    Get transformable feature columns for optimization.

    The optimizer is numeric-only. Multi-regime batches carry additional
    bookkeeping fields like `batch_regime` and `anchor_utc`; these must stay in
    batch metadata and never enter the rolling rank-winsorize transformer.

    Columns that are explicitly blocked by the final-output feature acceptance
    policy are excluded first. Columns that are entirely null/NaN after target
    gating are excluded next. Keeping either class would only preserve
    structurally unusable columns in optimized/helper outputs.
    """
    feature_cols: list[str] = []
    for col in df.columns:
        dtype = df.schema[col]
        if col in OPTIMIZER_META_COLS:
            continue
        if col in FINAL_OUTPUT_LABEL_ONLY_COLUMNS:
            continue
        if not dtype.is_numeric():
            continue
        feature_cols.append(col)

    policy_blocked = get_final_output_excluded_columns(
        feature_cols,
        stage=output_stage,
    )
    if policy_blocked:
        preview = ", ".join(policy_blocked[:8])
        suffix = "" if len(policy_blocked) <= 8 else ", ..."
        print(
            "  → Excluding policy-blocked model feature columns: "
            f"count={len(policy_blocked)} first={preview}{suffix}"
        )
        blocked_set = set(policy_blocked)
        feature_cols = [col for col in feature_cols if col not in blocked_set]

    if not feature_cols or df.is_empty():
        return feature_cols

    non_null_counts = df.select(
        [pl.len().alias("__rows__")]
        + [_non_nullish_count_expr(col, df.schema[col]) for col in feature_cols]
    )
    rows = int(non_null_counts["__rows__"][0]) if len(non_null_counts) > 0 else 0
    if rows <= 0:
        return feature_cols

    kept_cols: list[str] = []
    dropped_cols: list[str] = []
    for col in feature_cols:
        if int(non_null_counts[col][0]) > 0:
            kept_cols.append(col)
        else:
            dropped_cols.append(col)

    if dropped_cols:
        preview = ", ".join(dropped_cols[:8])
        suffix = "" if len(dropped_cols) <= 8 else ", ..."
        print(
            "  → Excluding all-null model feature columns: "
            f"count={len(dropped_cols)} first={preview}{suffix}"
        )

    return kept_cols


def _batch_id_from_stem(stem: str) -> int:
    """Extract batch ID from stem like 'batch_0123'."""
    m = re.match(r"batch_(\d+)$", stem)
    if not m:
        raise ValueError(f"Invalid batch stem: {stem}")
    return int(m.group(1))


def _file_fingerprint(path: Path) -> dict:
    """Lightweight fingerprint for incremental update detection."""
    stat = path.stat()
    return {
        "mtime_ns": int(stat.st_mtime_ns),
        "size_bytes": int(stat.st_size),
    }


def _optimizer_config_signature(config: dict | None) -> dict | None:
    if not config:
        return None
    return {
        "window": int(config["window"]),
        "p_min": float(config["p_min"]),
        "p_max": float(config["p_max"]),
        "post_transform": str(config["post_transform"]),
    }


def _candidate_grid_signature(tf: str) -> list[dict]:
    return [
        _optimizer_config_signature(candidate)
        for candidate in get_winsorize_rank_candidates(tf)
    ]


def _fingerprint_file_list(paths: list[Path]) -> list[dict]:
    return [
        {
            "stem": path.stem,
            "fingerprint": _file_fingerprint(path),
        }
        for path in paths
    ]


def _build_selection_input_signature(
    tf: str,
    target: str,
    config: HTFOptimizationConfig,
) -> dict:
    features_dir = config.htf_features_dir / tf
    labels_dir = config.htf_labels_dir / tf
    feature_files = sorted(features_dir.glob("batch_*.parquet"))
    label_files = sorted(labels_dir.glob("batch_*.parquet"))
    n_batches = min(config.n_early_batches, len(feature_files))

    return {
        "version": OPTIMIZER_SELECTION_IMPLEMENTATION_VERSION,
        "timeframe": tf,
        "target": target,
        "n_early_batches": int(config.n_early_batches),
        "n_val_folds": int(config.n_val_folds),
        "stability_lambda": float(config.stability_lambda),
        "candidate_grid": _candidate_grid_signature(tf),
        "final_output_feature_policy_version": FINAL_OUTPUT_FEATURE_POLICY_VERSION,
        "final_output_feature_policy_signature": FINAL_OUTPUT_FEATURE_POLICY_SIGNATURE,
        "feature_files": _fingerprint_file_list(feature_files[:n_batches]),
        "label_files": _fingerprint_file_list(label_files[:n_batches]),
    }


def _state_snapshot_file(state_dir: Path, batch_id: int) -> Path:
    return state_dir / f"state_after_batch_{batch_id:04d}.npz"


def _save_transformer_state(
    state: dict,
    feature_cols: list[str],
    window: int,
    path: Path,
) -> None:
    """Persist rolling transformer state to compressed npz."""
    if state is None:
        return
    buffers = np.stack([state["buffers"][c] for c in feature_cols], axis=0)
    positions = np.array([int(state["positions"][c]) for c in feature_cols], dtype=np.int64)
    counts = np.array([int(state["counts"][c]) for c in feature_cols], dtype=np.int64)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        feature_cols=np.array(feature_cols, dtype=str),
        window=np.array([int(window)], dtype=np.int64),
        buffers=buffers,
        positions=positions,
        counts=counts,
    )


def _load_transformer_state(path: Path) -> tuple[dict, list[str], int]:
    """Load rolling transformer state from npz."""
    data = np.load(path, allow_pickle=False)
    feature_cols = [str(x) for x in data["feature_cols"].tolist()]
    buffers = data["buffers"]
    positions = data["positions"]
    counts = data["counts"]
    window = int(data["window"][0])
    state = {
        "buffers": {c: buffers[i] for i, c in enumerate(feature_cols)},
        "positions": {c: int(positions[i]) for i, c in enumerate(feature_cols)},
        "counts": {c: int(counts[i]) for i, c in enumerate(feature_cols)},
    }
    return state, feature_cols, window


def _trim_old_snapshots(state_dir: Path, keep_last: int) -> None:
    """Keep only last N state snapshots."""
    if keep_last <= 0 or not state_dir.exists():
        return
    files = sorted(state_dir.glob("state_after_batch_*.npz"))
    if len(files) <= keep_last:
        return
    for p in files[: len(files) - keep_last]:
        p.unlink(missing_ok=True)


def load_early_batches(
    tf: str,
    target: str,
    config: HTFOptimizationConfig,
) -> tuple[pd.DataFrame, pd.Series, list[str]]:
    """
    Load FIRST N batches chronologically for walk-forward validation.

    NOT stratified — purely early data to avoid look-ahead bias.
    """
    features_dir = config.htf_features_dir / tf
    labels_dir = config.htf_labels_dir / tf

    feature_files = sorted(features_dir.glob("batch_*.parquet"))
    label_files = sorted(labels_dir.glob("batch_*.parquet"))

    n_batches = min(config.n_early_batches, len(feature_files))

    print(f"  Loading FIRST {n_batches} batches (chronological, no stratification)")

    # Take first N batches only
    feature_files = feature_files[:n_batches]
    label_files = label_files[:n_batches]

    # Load and merge
    features = pl.concat([pl.read_parquet(f) for f in feature_files])
    labels = pl.concat([pl.read_parquet(f) for f in label_files])

    # Select target column(s) - handle binary and multiclass
    label_cols = ["timestamp", "batch_id"]
    if target in labels.columns:
        label_cols.append(target)
    else:
        raise ValueError(
            f"Target '{target}' not found in labels. Available: {labels.columns}"
        )

    merged = features.join(
        labels.select(label_cols),
        on=["timestamp", "batch_id"],
        how="inner",
    )

    # CRITICAL: Sort by timestamp to ensure causal ordering
    # Without this, ranks could use "future" rows that appear earlier in the file
    merged = merged.sort(["timestamp", "batch_id"])

    del features, labels
    gc.collect()

    print(f"  → {len(merged):,} rows from early history (sorted by timestamp)")

    gated_targets = {"target_4class", "target_breakfree"}
    if target in gated_targets:
        merged = merged.filter(pl.col(target) >= 0)
        print(f"  → Filtered to {len(merged):,} valid rows (target >= 0)")

    # Get feature columns
    feature_cols = get_feature_cols(merged, output_stage="optimized")

    # Convert to pandas
    X = merged.select(feature_cols).to_pandas()

    # Handle categorical target (4-class) vs binary
    if target in {"target_4class"}:
        y = merged[target].to_pandas().astype(int)
    else:
        y = merged[target].to_pandas().astype(float)

    del merged
    gc.collect()

    return X, y, feature_cols


def walk_forward_validate(
    X: pd.DataFrame,
    y: pd.Series,
    transformer: RollingRankWinsorizeTransformer,
    n_folds: int = 3,
    target_type: str = "binary",  # "binary" or "multiclass"
    n_classes: int | None = None,
) -> tuple[float, float]:
    """
    Walk-forward validation for a transformer config.

    Splits data into n_folds sequential folds.
    For each fold: train on earlier, validate on later.

    For binary targets: uses Spearman IC (rank correlation)
    For 4-class targets: uses mutual information score

    Returns: (mean_score, std_score)
    """
    n = len(X)
    fold_size = n // (n_folds + 1)  # +1 because we need train + val

    scores = []
    feature_cols = [c for c in X.columns if transformer._should_transform(c)]

    for fold in range(n_folds):
        # Train: all data before validation fold
        train_end = fold_size * (fold + 1)
        val_start = train_end
        val_end = min(train_end + fold_size, n)

        if val_end <= val_start:
            continue

        # Initialize transformer state with training data
        X_train = X.iloc[:train_end].copy()
        X_val = X.iloc[val_start:val_end].copy()
        y_val = y.iloc[val_start:val_end].copy()

        # Transform training data to build up state
        _, state = transformer.transform_streaming(
            X_train, state=None, feature_cols=feature_cols
        )

        # Transform validation data with state from training
        X_val_transformed, _ = transformer.transform_streaming(
            X_val, state=state, feature_cols=feature_cols
        )

        y_val_np = y_val.values

        if target_type == "multiclass":
            # For multiclass: use mutual information (works with discrete targets)
            # MI measures how much knowing the feature reduces uncertainty about class
            X_val_clean = X_val_transformed[feature_cols].fillna(0)
            try:
                mi_scores = mutual_info_classif(
                    X_val_clean,
                    y_val_np.astype(int),
                    discrete_features=False,
                    random_state=42,
                )
                # Normalize MI by max possible (log2(n_classes))
                n_cls = n_classes or int(np.nanmax(y_val_np)) + 1
                mi_normalized = mi_scores / np.log2(max(n_cls, 2))
                fold_score = np.mean(mi_normalized)
                if not np.isnan(fold_score):
                    scores.append(fold_score)
            except Exception:
                pass
        else:
            # For binary: use Spearman IC (original approach)
            fold_ics = []
            for col in feature_cols:
                if col not in X_val_transformed.columns:
                    continue
                feat = X_val_transformed[col].values
                mask = ~(np.isnan(feat) | np.isnan(y_val_np))
                if mask.sum() > 50:
                    ic, _ = spearmanr(feat[mask], y_val_np[mask])
                    if not np.isnan(ic):
                        fold_ics.append(abs(ic))
            if fold_ics:
                scores.append(np.mean(fold_ics))

        del X_train, X_val, X_val_transformed, y_val
        gc.collect()

    if not scores:
        return 0.0, 1.0

    return np.mean(scores), np.std(scores)


def _score_transformed_fold(
    X_val_transformed: pd.DataFrame,
    y_val_np: np.ndarray,
    feature_cols: list[str],
    *,
    target_type: str,
    n_classes: int | None,
) -> float | None:
    if not feature_cols:
        return None

    if target_type == "multiclass":
        X_val_clean = X_val_transformed[feature_cols].fillna(0)
        try:
            mi_scores = mutual_info_classif(
                X_val_clean,
                y_val_np.astype(int),
                discrete_features=False,
                random_state=42,
            )
            n_cls = n_classes or int(np.nanmax(y_val_np)) + 1
            fold_score = float(np.mean(mi_scores / np.log2(max(n_cls, 2))))
            return fold_score if not np.isnan(fold_score) else None
        except Exception:
            return None

    fold_ics = []
    for col in feature_cols:
        if col not in X_val_transformed.columns:
            continue
        feat = X_val_transformed[col].values
        mask = ~(np.isnan(feat) | np.isnan(y_val_np))
        if mask.sum() > 50:
            ic, _ = spearmanr(feat[mask], y_val_np[mask])
            if not np.isnan(ic):
                fold_ics.append(abs(ic))
    if not fold_ics:
        return None
    return float(np.mean(fold_ics))


def _apply_rank_candidate(
    ranks: pd.DataFrame,
    *,
    p_min: float,
    p_max: float,
    post_transform: str,
) -> pd.DataFrame:
    clipped = ranks.clip(lower=p_min, upper=p_max)
    if post_transform == "uniform":
        return clipped
    if post_transform == "signed":
        return 2 * clipped - 1
    if post_transform == "gauss":
        eps = 1e-6
        values = norm.ppf(np.clip(clipped.to_numpy(dtype=np.float64), eps, 1 - eps))
        return pd.DataFrame(values, columns=clipped.columns, index=clipped.index)
    return clipped


def _validate_window_candidates_with_rank_reuse(
    X: pd.DataFrame,
    y: pd.Series,
    *,
    window: int,
    candidates: list[tuple[int, dict]],
    n_folds: int,
    target_type: str,
    n_classes: int | None,
) -> dict[int, tuple[float, float]]:
    n = len(X)
    fold_size = n // (n_folds + 1)
    raw_transformer = RollingRankWinsorizeTransformer(
        window=window,
        p_min=0.0,
        p_max=1.0,
        post_transform="uniform",
    )
    feature_cols = [c for c in X.columns if raw_transformer._should_transform(c)]

    fold_rank_cache: list[tuple[pd.DataFrame, np.ndarray]] = []
    for fold in range(n_folds):
        train_end = fold_size * (fold + 1)
        val_start = train_end
        val_end = min(train_end + fold_size, n)
        if val_end <= val_start:
            continue

        X_prefix = X.iloc[:val_end]
        X_val_index = X.index[val_start:val_end]
        y_val_np = y.iloc[val_start:val_end].copy().values

        if feature_cols:
            prefix_values = np.ascontiguousarray(
                X_prefix[feature_cols].to_numpy(dtype=np.float64, copy=True)
            )
            prefix_ranks = _rolling_rank_streaming_matrix_from_start(
                prefix_values,
                int(window),
            )
            X_val_ranks = pd.DataFrame(
                prefix_ranks[val_start:val_end],
                columns=feature_cols,
                index=X_val_index,
            )
        else:
            X_val_ranks = pd.DataFrame(index=X_val_index)
        fold_rank_cache.append((X_val_ranks, y_val_np))

        del X_prefix, X_val_ranks
        gc.collect()

    window_results: dict[int, tuple[float, float]] = {}
    for candidate_index, cand in candidates:
        scores = []
        for ranks, y_val_np in fold_rank_cache:
            transformed = _apply_rank_candidate(
                ranks,
                p_min=float(cand["p_min"]),
                p_max=float(cand["p_max"]),
                post_transform=str(cand["post_transform"]),
            )
            fold_score = _score_transformed_fold(
                transformed,
                y_val_np,
                feature_cols,
                target_type=target_type,
                n_classes=n_classes,
            )
            if fold_score is not None:
                scores.append(fold_score)
            del transformed
        if scores:
            window_results[candidate_index] = (float(np.mean(scores)), float(np.std(scores)))
        else:
            window_results[candidate_index] = (0.0, 1.0)

    del fold_rank_cache
    gc.collect()
    return window_results


def select_best_config(
    X: pd.DataFrame,
    y: pd.Series,
    tf: str,
    target: str,
    config: HTFOptimizationConfig,
) -> dict:
    """
    Select best winsorize-rank config using walk-forward validation.

    Score = mean(score) - lambda * std(score)
    For binary targets: score = IC (Spearman correlation)
    For 4-class targets: score = normalized mutual information
    """
    candidates = get_winsorize_rank_candidates(tf)

    # Determine target type
    target_type = (
        "multiclass" if target in {"target_4class"} else "binary"
    )

    n_classes = int(np.nanmax(y)) + 1 if target_type == "multiclass" else None

    print(f"  Testing {len(candidates)} winsorize-rank configurations...")
    print(f"  Using {config.n_val_folds}-fold walk-forward validation")

    best_score = -float("inf")
    best_config = candidates[0]
    best_mean_ic = 0.0
    best_std_ic = 0.0

    candidates_by_window: dict[int, list[tuple[int, dict]]] = {}
    for i, cand in enumerate(candidates):
        candidates_by_window.setdefault(int(cand["window"]), []).append((i, cand))

    validation_results: dict[int, tuple[float, float]] = {}
    for window, window_candidates in candidates_by_window.items():
        validation_results.update(
            _validate_window_candidates_with_rank_reuse(
                X,
                y,
                window=window,
                candidates=window_candidates,
                n_folds=config.n_val_folds,
                target_type=target_type,
                n_classes=n_classes,
            )
        )

    for i, cand in enumerate(candidates):
        mean_ic, std_ic = validation_results.get(i, (0.0, 1.0))

        # Score with stability penalty
        score = mean_ic - config.stability_lambda * std_ic

        if (i + 1) % 6 == 0 or i == 0:  # Print every 6th + first
            print(
                f"    [{i + 1}/{len(candidates)}] L={cand['window']:>3}, "
                f"clip=({cand['p_min']:.2f},{cand['p_max']:.2f}), "
                f"post={cand['post_transform']:<7} → IC={mean_ic:.4f}±{std_ic:.4f}, score={score:.4f}"
            )

        if score > best_score:
            best_score = score
            best_config = cand
            best_mean_ic = mean_ic
            best_std_ic = std_ic

    print(
        f"\n  Best config: L={best_config['window']}, "
        f"clip=({best_config['p_min']:.2f},{best_config['p_max']:.2f}), "
        f"post={best_config['post_transform']} (IC={best_mean_ic:.4f})"
    )

    return {
        "config": best_config,
        "best_mean_ic": float(best_mean_ic),
        "best_std_ic": float(best_std_ic),
        "best_score": float(best_score),
        "target_type": target_type,
        "n_classes": int(n_classes) if n_classes is not None else None,
        "summary": (
            f"L={best_config['window']}, "
            f"clip=({best_config['p_min']:.2f},{best_config['p_max']:.2f}), "
            f"post={best_config['post_transform']} "
            f"(IC={best_mean_ic:.4f}, score={best_score:.4f})"
        ),
    }


def apply_streaming_to_all_batches(
    tf: str,
    target: str,
    best_config: dict,
    config: HTFOptimizationConfig,
    cached_meta: dict | None = None,
    selected_feature_cols: list[str] | None = None,
) -> dict:
    """
    Apply transformer to ALL batches in streaming mode.

    State carries across batches — no reset at boundaries.
    """
    features_dir = config.htf_features_dir / tf
    labels_dir = config.htf_labels_dir / tf
    output_dir = config.htf_optimized_dir / tf / target

    output_dir.mkdir(parents=True, exist_ok=True)

    feature_files = sorted(features_dir.glob("batch_*.parquet"))
    label_files = sorted(labels_dir.glob("batch_*.parquet"))
    label_by_stem = {f.stem: f for f in label_files}
    pairs: list[dict] = []
    missing_label = 0
    for feat_file in feature_files:
        label_file = label_by_stem.get(feat_file.stem)
        if label_file is None:
            missing_label += 1
            continue
        batch_id = _batch_id_from_stem(feat_file.stem)
        pairs.append(
            {
                "batch_id": batch_id,
                "feature_file": feat_file,
                "label_file": label_file,
            }
        )
    pairs = sorted(pairs, key=lambda x: x["batch_id"])
    extra_labels = max(0, len(label_files) - len(pairs))

    print(
        f"  Applying to {len(pairs)} matched batches "
        f"(features={len(feature_files)}, labels={len(label_files)}, "
        f"missing_labels={missing_label}, extra_labels={extra_labels}; "
        "streaming, state carries over)..."
    )

    if not pairs:
        return {
            "saved_batches": 0,
            "skipped_batches": 0,
            "reused_batches": 0,
            "total_rows": 0,
            "start_batch": None,
            "end_batch": None,
            "last_processed_batch": None,
            "last_processed_timestamp": None,
            "resume_reason": "no_pairs",
            "batch_fingerprints": {},
            "per_batch_rows": {},
            "feature_cols": [],
        }

    # Create transformer
    transformer = RollingRankWinsorizeTransformer(
        window=best_config["window"],
        p_min=best_config["p_min"],
        p_max=best_config["p_max"],
        post_transform=best_config["post_transform"],
    )

    # Build current fingerprints
    current_fingerprints: dict[str, dict] = {}
    for rec in pairs:
        bid = str(rec["batch_id"])
        current_fingerprints[bid] = {
            "feature": _file_fingerprint(rec["feature_file"]),
            "label": _file_fingerprint(rec["label_file"]),
        }

    output_files = {
        _batch_id_from_stem(p.stem): p for p in sorted(output_dir.glob("batch_*.parquet"))
    }
    pair_batch_ids = [int(rec["batch_id"]) for rec in pairs]
    pair_batch_id_set = set(pair_batch_ids)
    first_batch = int(pair_batch_ids[0])
    last_batch = int(pair_batch_ids[-1])

    orphan_output_ids = sorted(set(output_files) - pair_batch_id_set)
    if orphan_output_ids:
        print(
            f"  Removing {len(orphan_output_ids)} orphan optimized batches: "
            f"{orphan_output_ids[:5]}"
        )
        for orphan_batch_id in orphan_output_ids:
            orphan_path = output_files.pop(orphan_batch_id, None)
            if orphan_path is not None:
                orphan_path.unlink(missing_ok=True)

    state_dir = output_dir / "_state"
    state_dir.mkdir(parents=True, exist_ok=True)

    state = None  # Transformer state
    state_feature_cols: list[str] | None = (
        list(selected_feature_cols) if selected_feature_cols else None
    )
    start_batch = first_batch
    resume_reason = "full_recompute"

    per_batch_rows: dict[str, int] = {}
    per_batch_last_timestamp: dict[str, str | None] = {}
    if cached_meta and isinstance(cached_meta.get("per_batch_rows"), dict):
        per_batch_rows = {str(k): int(v) for k, v in cached_meta["per_batch_rows"].items()}
    if cached_meta and isinstance(cached_meta.get("per_batch_last_timestamp"), dict):
        per_batch_last_timestamp = {
            str(k): (str(v) if v is not None else None)
            for k, v in cached_meta["per_batch_last_timestamp"].items()
        }
    per_batch_rows = {
        bid: n_rows for bid, n_rows in per_batch_rows.items() if int(bid) in pair_batch_id_set
    }
    per_batch_last_timestamp = {
        bid: ts
        for bid, ts in per_batch_last_timestamp.items()
        if int(bid) in pair_batch_id_set
    }

    if config.incremental_update and not config.recompute and cached_meta:
        prev_fps = cached_meta.get("batch_fingerprints", {})
        policy_changed = (
            cached_meta.get("final_output_feature_policy_version")
            != FINAL_OUTPUT_FEATURE_POLICY_VERSION
            or cached_meta.get("final_output_feature_policy_signature")
            != FINAL_OUTPUT_FEATURE_POLICY_SIGNATURE
        )
        transform_config_changed = (
            _optimizer_config_signature(cached_meta.get("config"))
            != _optimizer_config_signature(best_config)
        )
        first_diff = first_batch if (policy_changed or transform_config_changed) else None
        if not policy_changed and not transform_config_changed:
            for rec in pairs:
                bid = int(rec["batch_id"])
                bid_key = str(bid)
                out_ok = bid in output_files and output_files[bid].exists()
                if (bid_key not in prev_fps) or (prev_fps[bid_key] != current_fingerprints[bid_key]) or (not out_ok):
                    first_diff = bid
                    break

        if first_diff is None:
            total_rows = sum(int(per_batch_rows.get(str(b), 0)) for b in pair_batch_ids)
            return {
                "saved_batches": 0,
                "skipped_batches": 0,
                "reused_batches": len(pair_batch_ids),
                "total_rows": int(total_rows),
                "start_batch": first_batch,
                "end_batch": last_batch,
                "last_processed_batch": None,
                "last_processed_timestamp": cached_meta.get("last_processed_timestamp"),
                "resume_reason": "already_up_to_date",
                "batch_fingerprints": current_fingerprints,
                "per_batch_rows": per_batch_rows,
                "per_batch_last_timestamp": per_batch_last_timestamp,
                "feature_cols": cached_meta.get("feature_cols", []),
            }

        # Try to load most recent snapshot strictly before the first changed
        # batch. A policy change invalidates the prior feature-column set, so
        # snapshots are intentionally ignored in that case.
        snapshot_candidates: list[tuple[int, Path]] = []
        if not policy_changed and not transform_config_changed:
            for p in sorted(state_dir.glob("state_after_batch_*.npz")):
                try:
                    snap_bid = _batch_id_from_stem(p.stem.replace("state_after_", ""))
                except Exception:
                    continue
                if snap_bid < first_diff:
                    snapshot_candidates.append((snap_bid, p))
        snapshot_candidates = sorted(snapshot_candidates, key=lambda x: x[0], reverse=True)

        loaded_snapshot = False
        for snap_bid, snap_path in snapshot_candidates:
            try:
                loaded_state, loaded_cols, loaded_window = _load_transformer_state(snap_path)
                if int(loaded_window) != int(best_config["window"]):
                    continue
                state = loaded_state
                state_feature_cols = loaded_cols
                start_batch = snap_bid + 1
                resume_reason = f"resume_from_snapshot_batch_{snap_bid}"
                loaded_snapshot = True
                break
            except Exception:
                continue

        if not loaded_snapshot:
            start_batch = first_batch
            if policy_changed:
                state_feature_cols = None
                resume_reason = (
                    f"full_recompute_from_{first_batch}_policy_"
                    f"{FINAL_OUTPUT_FEATURE_POLICY_VERSION}"
                )
            elif transform_config_changed:
                resume_reason = f"full_recompute_from_{first_batch}_optimizer_config"
            else:
                resume_reason = f"full_recompute_from_{first_batch}_first_diff_{first_diff}"

    total_rows = 0
    feature_cols = state_feature_cols
    prev_max_ts = None  # For chronological order verification
    saved_batches = 0
    skipped_batches = 0
    reused_batches = 0
    last_processed_batch = None
    last_processed_ts = None

    pairs_to_process = [rec for rec in pairs if int(rec["batch_id"]) >= int(start_batch)]
    reused_batches = len(pairs) - len(pairs_to_process)

    for i, rec in enumerate(pairs_to_process):
        feat_file = rec["feature_file"]
        label_file = rec["label_file"]
        batch_id_int = int(rec["batch_id"])
        # Load batch
        features = pl.read_parquet(feat_file)
        labels = pl.read_parquet(label_file)

        merged = features.join(
            labels.select(["timestamp", "batch_id", target]),
            on=["timestamp", "batch_id"],
            how="inner",
        )

        # CRITICAL: Sort by timestamp within batch to ensure causal ordering
        merged = merged.sort(["timestamp", "batch_id"])

        # Keep only rows with valid labels for gated classification targets.
        # This keeps htf_optimized row counts aligned with label-valid rows
        # (first-4h policy), and avoids carrying unlabeled rows downstream.
        if target in {"target_4class", "target_breakfree"} and target in merged.columns:
            merged = merged.filter(pl.col(target) >= 0)

        # Guard: some batches may have no overlapping rows after join.
        # Skip safely (state is unchanged) instead of crashing on None timestamps.
        if merged.is_empty():
            skipped_batches += 1
            print(
                f"    Warning: {feat_file.stem} produced 0 joined rows "
                f"for target '{target}' (skipping)"
            )
            del features, labels, merged
            continue

        # CRITICAL: Verify chronological order across batches
        min_ts = merged["timestamp"].min()
        max_ts = merged["timestamp"].max()
        if min_ts is None or max_ts is None:
            skipped_batches += 1
            print(
                f"    Warning: {feat_file.stem} has null timestamp bounds "
                f"for target '{target}' (skipping)"
            )
            del features, labels, merged
            continue
        if prev_max_ts is not None and min_ts < prev_max_ts:
            raise ValueError(
                f"Batch {feat_file.stem} has min_ts={min_ts} < prev_max_ts={prev_max_ts}. "
                "Batches are not chronologically ordered - streaming causality broken!"
            )
        prev_max_ts = max_ts

        del features, labels

        # Get feature columns (first batch only)
        if feature_cols is None:
            feature_cols = get_feature_cols(merged, output_stage="optimized")

        # Convert to pandas
        X_pd = merged.select(feature_cols).to_pandas()
        # Preserve only true batch metadata. Any numeric column excluded from
        # `feature_cols` is intentionally being dropped from model-facing
        # outputs and must not leak back in through the metadata side.
        meta_cols = [
            c
            for c in merged.columns
            if c in OPTIMIZER_META_COLS and c not in FINAL_OUTPUT_LABEL_ONLY_COLUMNS
        ]
        meta = merged.select(meta_cols)

        del merged

        # Transform with state carry-over
        X_transformed, state = transformer.transform_streaming(
            X_pd, state=state, feature_cols=feature_cols
        )

        del X_pd

        # Convert back to Polars and preserve all non-feature metadata
        result = pl.from_pandas(X_transformed)
        meta_cols_to_preserve = [
            c for c in meta.columns if c not in {target}
        ]
        meta_no_target = meta.select(meta_cols_to_preserve)
        result = pl.concat([result, meta_no_target], how="horizontal")

        del X_transformed, meta, meta_no_target

        # Save
        output_file = output_dir / f"batch_{batch_id_int:04d}.parquet"
        result.write_parquet(output_file, compression="zstd")

        n_rows_batch = int(len(result))
        per_batch_rows[str(batch_id_int)] = n_rows_batch
        per_batch_last_timestamp[str(batch_id_int)] = (
            str(result["timestamp"].max()) if result["timestamp"].max() is not None else None
        )
        total_rows += n_rows_batch
        saved_batches += 1
        last_processed_batch = batch_id_int
        ts_max = result["timestamp"].max()
        last_processed_ts = ts_max.isoformat() if ts_max is not None else last_processed_ts

        # Persist rolling state snapshot for robust resume/live updates
        if state is not None and feature_cols:
            snapshot_path = _state_snapshot_file(state_dir, batch_id_int)
            _save_transformer_state(
                state=state,
                feature_cols=feature_cols,
                window=int(best_config["window"]),
                path=snapshot_path,
            )
            _trim_old_snapshots(state_dir, keep_last=int(config.max_state_snapshots))

        del result

        if (i + 1) % 500 == 0:
            print(f"    Processed {i + 1}/{len(pairs_to_process)} batches...")
            gc.collect()

    # Ensure total rows reflect all matched batches (reused + processed)
    for bid in pair_batch_ids:
        bid_key = str(bid)
        if bid_key not in per_batch_rows:
            out_path = output_dir / f"batch_{bid:04d}.parquet"
            if out_path.exists():
                try:
                    out_df = pl.read_parquet(out_path, columns=["timestamp"])
                    per_batch_rows[bid_key] = int(len(out_df))
                    per_batch_last_timestamp[bid_key] = (
                        str(out_df["timestamp"].max()) if len(out_df) > 0 else None
                    )
                except Exception:
                    per_batch_rows[bid_key] = 0
                    per_batch_last_timestamp[bid_key] = None
            else:
                per_batch_rows[bid_key] = 0
                per_batch_last_timestamp[bid_key] = None
    total_rows_all = sum(int(per_batch_rows.get(str(b), 0)) for b in pair_batch_ids)

    print(
        f"  ✓ Saved {saved_batches} batch files ({total_rows:,} rows processed), "
        f"reused {reused_batches}, skipped {skipped_batches} empty/null batches"
    )
    return {
        "saved_batches": int(saved_batches),
        "skipped_batches": int(skipped_batches),
        "reused_batches": int(reused_batches),
        "total_rows": int(total_rows_all),
        "start_batch": int(start_batch),
        "end_batch": int(last_batch),
        "last_processed_batch": (
            int(last_processed_batch) if last_processed_batch is not None else None
        ),
        "last_processed_timestamp": last_processed_ts,
        "resume_reason": resume_reason,
        "batch_fingerprints": current_fingerprints,
        "per_batch_rows": per_batch_rows,
        "per_batch_last_timestamp": per_batch_last_timestamp,
        "feature_cols": feature_cols or [],
    }


def optimize_single_tf_target(
    tf: str,
    target: str,
    config: HTFOptimizationConfig,
) -> dict:
    """
    Optimize features for a single timeframe-target combination.
    """
    print(f"\n{'─' * 60}")
    print(f"Optimizing: {tf} / {target}")
    print(f"{'─' * 60}")

    output_dir = config.htf_optimized_dir / tf / target
    output_dir.mkdir(parents=True, exist_ok=True)

    feature_files = list((config.htf_features_dir / tf).glob("batch_*.parquet"))
    output_files = list(output_dir.glob("batch_*.parquet"))

    # Load cached best config if available and recompute=False
    meta_file = config.htf_optimized_dir / tf / f"optimized_{target}_meta.json"
    cached_meta = None
    cached_config = None
    if not config.recompute and meta_file.exists():
        try:
            with open(meta_file, "r") as f:
                cached_meta = json.load(f)
            cached_config = cached_meta.get("config")
        except Exception:
            cached_meta = None
            cached_config = None

    current_selection_signature = _build_selection_input_signature(tf, target, config)
    if cached_config is not None:
        cached_selection_signature = (
            cached_meta.get("selection_input_signature") if cached_meta else None
        )
        if cached_selection_signature != current_selection_signature:
            print(
                "  → Cached best config invalidated by optimizer selection "
                "input signature. Re-running grid search."
            )
            cached_config = None

    policy_changed = bool(
        cached_meta
        and (
            cached_meta.get("final_output_feature_policy_version")
            != FINAL_OUTPUT_FEATURE_POLICY_VERSION
            or cached_meta.get("final_output_feature_policy_signature")
            != FINAL_OUTPUT_FEATURE_POLICY_SIGNATURE
        )
    )

    selection_info = None
    selected_feature_cols: list[str] | None = None
    if cached_config is not None:
        print("  ✓ Cached best config found. Skipping grid search.")
        selection_info = {
            "config": cached_config,
            "best_mean_ic": (
                float(cached_meta.get("best_mean_ic"))
                if cached_meta and cached_meta.get("best_mean_ic") is not None
                else None
            ),
            "best_std_ic": (
                float(cached_meta.get("best_std_ic"))
                if cached_meta and cached_meta.get("best_std_ic") is not None
                else None
            ),
            "best_score": (
                float(cached_meta.get("best_score"))
                if cached_meta and cached_meta.get("best_score") is not None
                else None
            ),
            "target_type": cached_meta.get("target_type", "unknown") if cached_meta else "unknown",
            "n_classes": cached_meta.get("n_classes") if cached_meta else None,
            "summary": cached_meta.get("best_config_summary") if cached_meta else None,
        }
        best_config = cached_config
        if policy_changed:
            print(
                "  → Final-output feature policy changed; cached model-facing "
                "feature column set will be recomputed."
            )
        elif cached_meta and isinstance(cached_meta.get("feature_cols"), list):
            selected_feature_cols = [str(col) for col in cached_meta["feature_cols"]]
    else:
        # Step 1: Load EARLY batches for walk-forward validation
        X_sample, y_sample, selected_feature_cols = load_early_batches(tf, target, config)

        # Step 2: Select best config using walk-forward validation
        selection_info = select_best_config(X_sample, y_sample, tf, target, config)
        selection_info["feature_cols"] = list(selected_feature_cols or X_sample.columns.tolist())
        best_config = selection_info["config"]

        del X_sample, y_sample
        gc.collect()

    # Step 3: Apply to all batches in streaming mode (incremental + resumable)
    apply_info = apply_streaming_to_all_batches(
        tf=tf,
        target=target,
        best_config=best_config,
        config=config,
        cached_meta=cached_meta,
        selected_feature_cols=selected_feature_cols,
    )
    total_rows = int(apply_info["total_rows"])

    # Re-count batches after processing
    feature_files = list((config.htf_features_dir / tf).glob("batch_*.parquet"))

    # Save metadata
    if config.save_results:
        meta_file = config.htf_optimized_dir / tf / f"optimized_{target}_meta.json"
        now_ts = datetime.now(timezone.utc).isoformat()
        best_config_summary = (
            selection_info.get("summary")
            if selection_info is not None
            else None
        )
        if not best_config_summary:
            best_config_summary = (
                f"L={best_config.get('window')}, "
                f"clip=({float(best_config.get('p_min', 0.0)):.2f},{float(best_config.get('p_max', 1.0)):.2f}), "
                f"post={best_config.get('post_transform')}"
            )
        metadata = {
            "timeframe": tf,
            "target": target,
            "method": "rolling_rank_winsorize",
            "config": best_config,
            "best_config_summary": best_config_summary,
            "best_mean_ic": (
                selection_info.get("best_mean_ic") if selection_info is not None else None
            ),
            "best_std_ic": (
                selection_info.get("best_std_ic") if selection_info is not None else None
            ),
            "best_score": (
                selection_info.get("best_score") if selection_info is not None else None
            ),
            "target_type": (
                selection_info.get("target_type") if selection_info is not None else None
            ),
            "n_classes": (
                selection_info.get("n_classes") if selection_info is not None else None
            ),
            "n_batches": len(feature_files),
            "total_rows": total_rows,
            "last_processed_batch": apply_info.get("last_processed_batch"),
            "last_processed_timestamp": apply_info.get("last_processed_timestamp"),
            "resume_reason": apply_info.get("resume_reason"),
            "saved_batches": apply_info.get("saved_batches"),
            "reused_batches": apply_info.get("reused_batches"),
            "skipped_batches": apply_info.get("skipped_batches"),
            "start_batch": apply_info.get("start_batch"),
            "end_batch": apply_info.get("end_batch"),
            "feature_cols": apply_info.get("feature_cols", []),
            "final_output_feature_policy_version": FINAL_OUTPUT_FEATURE_POLICY_VERSION,
            "final_output_feature_policy_signature": FINAL_OUTPUT_FEATURE_POLICY_SIGNATURE,
            "batch_fingerprints": apply_info.get("batch_fingerprints", {}),
            "per_batch_rows": apply_info.get("per_batch_rows", {}),
            "per_batch_last_timestamp": apply_info.get("per_batch_last_timestamp", {}),
            "validation": {
                "n_early_batches": config.n_early_batches,
                "n_val_folds": config.n_val_folds,
                "stability_lambda": config.stability_lambda,
            },
            "selection_input_signature": current_selection_signature,
            "optimizer_selection_implementation_version": (
                OPTIMIZER_SELECTION_IMPLEMENTATION_VERSION
            ),
            "run_options": {
                "recompute": bool(config.recompute),
                "incremental_update": bool(config.incremental_update),
                "max_state_snapshots": int(config.max_state_snapshots),
            },
            "timestamp": now_ts,
        }
        with open(meta_file, "w") as f:
            json.dump(metadata, f, indent=2)

    return {
        "timeframe": tf,
        "target": target,
        "window": best_config["window"],
        "p_min": best_config["p_min"],
        "p_max": best_config["p_max"],
        "post_transform": best_config["post_transform"],
        "n_batches": len(feature_files),
        "total_rows": total_rows,
        "best_config_summary": metadata.get("best_config_summary") if config.save_results else None,
        "last_processed_batch": apply_info.get("last_processed_batch"),
        "last_processed_timestamp": apply_info.get("last_processed_timestamp"),
        "resume_reason": apply_info.get("resume_reason"),
        "saved_batches": apply_info.get("saved_batches"),
        "reused_batches": apply_info.get("reused_batches"),
    }


def optimize_htf_features(
    config: HTFOptimizationConfig | None = None,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Main entry point for HTF feature optimization.

    Uses CORRECT winsorize-rank:
    1. Rolling rank (past L values only)
    2. Clip ranks
    3. Walk-forward validation on early data
    4. Streaming application with state carry-over
    """
    if config is None:
        config = HTFOptimizationConfig()

    config.htf_optimized_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("HTF FEATURE OPTIMIZATION (Rolling Rank-Winsorize)")
    print("=" * 70)
    print(f"Timeframes: {config.timeframes}")
    print(f"Targets: {config.targets}")
    print(f"Early batches for tuning: {config.n_early_batches}")
    print(f"Walk-forward folds: {config.n_val_folds}")
    print(f"Stability penalty λ: {config.stability_lambda}")
    print(f"Recompute: {config.recompute}")

    # Build task list (always include; optimize_single_tf_target handles cached config)
    tasks = [(tf, target) for tf in config.timeframes for target in config.targets]

    if not tasks:
        print("\nNo tasks to run (all exist). Set recompute=True to force.")
        return pd.DataFrame()

    print(f"\nTasks to run: {len(tasks)}")

    results = []
    for i, (tf, target) in enumerate(tasks, 1):
        print(f"\n[{i}/{len(tasks)}]", end="")
        result = optimize_single_tf_target(tf, target, config)
        results.append(result)
        gc.collect()

    return pd.DataFrame(results)
