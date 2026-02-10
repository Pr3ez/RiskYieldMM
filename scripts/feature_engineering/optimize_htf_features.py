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
from scipy.stats import spearmanr
from sklearn.feature_selection import mutual_info_classif

from scripts.analysis.optimizers.rolling_rank_winsorize import (
    RollingRankWinsorizeTransformer,
    get_winsorize_rank_candidates,
)


@dataclass
class HTFOptimizationConfig:
    """Configuration for HTF feature optimization."""

    # Data paths
    project_root: Path = field(
        default_factory=lambda: Path(__file__).parent.parent.parent
    )

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
        return self.project_root / "data" / "htf_features"

    @property
    def htf_labels_dir(self) -> Path:
        return self.project_root / "data" / "htf_4class_labels"

    @property
    def htf_optimized_dir(self) -> Path:
        return self.project_root / "data" / "htf_optimized"


def get_feature_cols(df: pl.DataFrame) -> list[str]:
    """Get feature columns (exclude meta and datetime)."""
    meta_cols = {
        "timestamp",
        "batch_id",
        "target_long",
        "target_short",
        "target_4class",
        "target_name",
        "period_8h_start",
    }
    datetime_types = {pl.Datetime, pl.Date, pl.Time}
    return [
        c
        for c in df.columns
        if c not in meta_cols and df[c].dtype not in datetime_types
    ]


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
) -> tuple[pd.DataFrame, pd.Series]:
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

    # Get feature columns
    feature_cols = get_feature_cols(merged)

    # Convert to pandas
    X = merged.select(feature_cols).to_pandas()

    # Handle categorical target (4-class) vs binary
    if target in {"target_4class"}:
        # For multiclass: convert to int, filter valid (-1 = invalid)
        y_raw = merged[target].to_pandas()
        valid_mask = y_raw >= 0
        X = X[valid_mask].reset_index(drop=True)
        y = y_raw[valid_mask].astype(int).reset_index(drop=True)
        print(f"  → Filtered to {len(y):,} valid rows (target >= 0)")
    else:
        y = merged[target].to_pandas().astype(float)

    del merged
    gc.collect()

    return X, y


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

    for i, cand in enumerate(candidates):
        transformer = RollingRankWinsorizeTransformer(
            window=cand["window"],
            p_min=cand["p_min"],
            p_max=cand["p_max"],
            post_transform=cand["post_transform"],
        )

        mean_ic, std_ic = walk_forward_validate(
            X,
            y,
            transformer,
            n_folds=config.n_val_folds,
            target_type=target_type,
            n_classes=n_classes,
        )

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
    first_batch = int(pair_batch_ids[0])
    last_batch = int(pair_batch_ids[-1])

    state_dir = output_dir / "_state"
    state_dir.mkdir(parents=True, exist_ok=True)

    state = None  # Transformer state
    state_feature_cols: list[str] | None = None
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

    if config.incremental_update and not config.recompute and cached_meta:
        prev_fps = cached_meta.get("batch_fingerprints", {})
        first_diff = None
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

        # Try to load most recent snapshot strictly before the first changed batch
        snapshot_candidates: list[tuple[int, Path]] = []
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
            feature_cols = get_feature_cols(merged)

        # Convert to pandas
        X_pd = merged.select(feature_cols).to_pandas()
        meta = merged.select(["timestamp", "batch_id", target])

        del merged

        # Transform with state carry-over
        X_transformed, state = transformer.transform_streaming(
            X_pd, state=state, feature_cols=feature_cols
        )

        del X_pd

        # Convert back to Polars and add metadata (EXCLUDING target - that's in labels dir)
        result = pl.from_pandas(X_transformed)
        meta_no_target = meta.select(["timestamp", "batch_id"])  # Drop target column!
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

    selection_info = None
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
    else:
        # Step 1: Load EARLY batches for walk-forward validation
        X_sample, y_sample = load_early_batches(tf, target, config)

        # Step 2: Select best config using walk-forward validation
        selection_info = select_best_config(X_sample, y_sample, tf, target, config)
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
            "batch_fingerprints": apply_info.get("batch_fingerprints", {}),
            "per_batch_rows": apply_info.get("per_batch_rows", {}),
            "per_batch_last_timestamp": apply_info.get("per_batch_last_timestamp", {}),
            "validation": {
                "n_early_batches": config.n_early_batches,
                "n_val_folds": config.n_val_folds,
                "stability_lambda": config.stability_lambda,
            },
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
