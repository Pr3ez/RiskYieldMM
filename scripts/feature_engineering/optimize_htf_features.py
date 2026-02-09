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

    @property
    def htf_features_dir(self) -> Path:
        return self.project_root / "data" / "htf_features"

    @property
    def htf_labels_dir(self) -> Path:
        return self.project_root / "data" / "htf_8class_labels"

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
        "target_8class",
        "target_name",
        "period_8h_start",
    }
    datetime_types = {pl.Datetime, pl.Date, pl.Time}
    return [
        c
        for c in df.columns
        if c not in meta_cols and df[c].dtype not in datetime_types
    ]


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

    # Handle categorical target (8-class) vs binary
    if target in {"target_8class"}:
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
    For 8-class targets: uses mutual information score

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
    For 8-class targets: score = normalized mutual information
    """
    candidates = get_winsorize_rank_candidates(tf)

    # Determine target type
    target_type = (
        "multiclass" if target in {"target_8class"} else "binary"
    )

    n_classes = int(np.nanmax(y)) + 1 if target_type == "multiclass" else None

    print(f"  Testing {len(candidates)} winsorize-rank configurations...")
    print(f"  Using {config.n_val_folds}-fold walk-forward validation")

    best_score = -float("inf")
    best_config = candidates[0]
    best_mean_ic = 0.0

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

    print(
        f"\n  Best config: L={best_config['window']}, "
        f"clip=({best_config['p_min']:.2f},{best_config['p_max']:.2f}), "
        f"post={best_config['post_transform']} (IC={best_mean_ic:.4f})"
    )

    return best_config


def apply_streaming_to_all_batches(
    tf: str,
    target: str,
    best_config: dict,
    config: HTFOptimizationConfig,
) -> int:
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

    print(
        f"  Applying to {len(feature_files)} batches (streaming, state carries over)..."
    )

    # Create transformer
    transformer = RollingRankWinsorizeTransformer(
        window=best_config["window"],
        p_min=best_config["p_min"],
        p_max=best_config["p_max"],
        post_transform=best_config["post_transform"],
    )

    state = None  # Will be initialized on first batch
    total_rows = 0
    feature_cols = None
    prev_max_ts = None  # For chronological order verification

    for i, (feat_file, label_file) in enumerate(zip(feature_files, label_files)):
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

        # CRITICAL: Verify chronological order across batches
        min_ts = merged["timestamp"].min()
        max_ts = merged["timestamp"].max()
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
        batch_id = feat_file.stem.replace("batch_", "")
        output_file = output_dir / f"batch_{batch_id}.parquet"
        result.write_parquet(output_file, compression="zstd")

        total_rows += len(result)
        del result

        if (i + 1) % 500 == 0:
            print(f"    Processed {i + 1}/{len(feature_files)} batches...")
            gc.collect()

    print(f"  ✓ Saved {len(feature_files)} batch files ({total_rows:,} rows)")
    return total_rows


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

    if cached_config is not None:
        # If outputs already cover all batches, skip heavy processing
        if len(output_files) == len(feature_files) and len(feature_files) > 0:
            print("  ✓ Cached best config found. Outputs already up to date - skipping.")
            return {
                "timeframe": tf,
                "target": target,
                "window": cached_config.get("window"),
                "p_min": cached_config.get("p_min"),
                "p_max": cached_config.get("p_max"),
                "post_transform": cached_config.get("post_transform"),
                "n_batches": len(feature_files),
                "total_rows": cached_meta.get("total_rows", 0) if cached_meta else 0,
            }

        print("  ✓ Cached best config found. Skipping grid search.")
        if len(output_files) != len(feature_files):
            print(
                "  Outputs not complete - reprocessing all batches to preserve streaming state."
            )
        best_config = cached_config
    else:
        # Step 1: Load EARLY batches for walk-forward validation
        X_sample, y_sample = load_early_batches(tf, target, config)

        # Step 2: Select best config using walk-forward validation
        best_config = select_best_config(X_sample, y_sample, tf, target, config)

        del X_sample, y_sample
        gc.collect()

    # Step 3: Apply to all batches in streaming mode
    total_rows = apply_streaming_to_all_batches(tf, target, best_config, config)

    # Re-count batches after processing
    feature_files = list((config.htf_features_dir / tf).glob("batch_*.parquet"))

    # Save metadata
    if config.save_results:
        meta_file = config.htf_optimized_dir / tf / f"optimized_{target}_meta.json"
        metadata = {
            "timeframe": tf,
            "target": target,
            "method": "rolling_rank_winsorize",
            "config": best_config,
            "n_batches": len(feature_files),
            "total_rows": total_rows,
            "validation": {
                "n_early_batches": config.n_early_batches,
                "n_val_folds": config.n_val_folds,
                "stability_lambda": config.stability_lambda,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
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
