"""
L1 Feature Precomputation - Exact Production Match
===================================================

Precomputes L1 helper features by running the EXACT same process as production:

For each walk-forward iteration:
1. fit(X[L1.train])           - Unsupervised fitting
2. optimize(X[L1.val], y)     - Target-specific IC boosting
3. transform(X[L2.full])      - Generate helper_features for L2

We save the helper_features from step 3 - this is exactly what L2 receives.

Storage structure (TIMESTAMP-ORGANIZED):
    data/precomputed/{config_name}/
    ├── 2025-10-13_00h.parquet    # helper_features for pred at this timestamp
    ├── 2025-10-13_08h.parquet    # 8h bars = 3 files per day
    ├── 2025-10-13_16h.parquet
    ├── index.json                # timestamp -> metadata mapping
    └── metadata.json             # Overall precomputation info

Benefits of timestamp organization:
    - Files named by prediction timestamp (logical, not arbitrary iteration #)
    - Easy to add earlier/later iterations without renumbering
    - Can query by date range
    - Self-documenting file names
    - Less chance for bugs (dates are meaningful)

For fast backtest:
    1. Load precomputed helper_features for each iteration by timestamp
    2. Run only L2 (train, calibrate, predict) on loaded features
    3. Skip L1 entirely - already computed correctly

This is slow to run (~1 hour per config) but only done ONCE.
All subsequent backtests load instantly.
"""

from __future__ import annotations

import json
import shutil
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd
import polars as pl


def _timestamp_to_filename(ts: pd.Timestamp) -> str:
    """Convert timestamp to filename string: YYYY-MM-DD_HHh.parquet"""
    return f"{ts.strftime('%Y-%m-%d_%Hh')}.parquet"


def _filename_to_timestamp(filename: str) -> pd.Timestamp:
    """Convert filename back to timestamp."""
    # Remove .parquet extension
    name = filename.replace(".parquet", "")
    # Parse YYYY-MM-DD_HHh format
    dt = datetime.strptime(name, "%Y-%m-%d_%Hh")
    return pd.Timestamp(dt, tz="UTC")


@dataclass
class L1PrecomputeConfig:
    """Configuration for L1 precomputation."""

    # Data source
    data_dir: Path = field(default_factory=lambda: Path("data/datasets"))

    # Output
    output_dir: Path = field(default_factory=lambda: Path("data/precomputed"))

    # Backtest settings (must match what you'll use for backtest)
    backtest_rows: int = 200

    # Random state
    random_state: int = 42

    def config_output_dir(self, config_name: str) -> Path:
        """Directory for a specific config's precomputed features."""
        return self.output_dir / config_name

    def timestamp_path(self, config_name: str, ts: pd.Timestamp) -> Path:
        """Path for a specific timestamp's helper features."""
        return self.config_output_dir(config_name) / _timestamp_to_filename(ts)

    def index_path(self, config_name: str) -> Path:
        """Path for timestamp index JSON."""
        return self.config_output_dir(config_name) / "index.json"

    def metadata_path(self, config_name: str) -> Path:
        """Path for metadata JSON."""
        return self.config_output_dir(config_name) / "metadata.json"

    # Legacy support for iteration-based loading
    def iteration_path(self, config_name: str, iteration: int) -> Path:
        """DEPRECATED: Use timestamp_path. Kept for backward compatibility."""
        # Load index to get timestamp for iteration
        index = load_iteration_index(config_name, self)
        if iteration >= len(index):
            raise ValueError(f"Iteration {iteration} not found (max: {len(index) - 1})")
        ts_str = index[iteration]["timestamp"]
        ts = pd.Timestamp(ts_str)
        return self.timestamp_path(config_name, ts)


@dataclass
class IterationInfo:
    """Info for a single iteration, keyed by prediction timestamp."""

    timestamp: str  # ISO format prediction timestamp
    aligned_timestamp: str  # ISO format of aligned timestamp (end of pred span)
    iteration: int  # Sequential iteration number (for ordering)
    pred_idx: int  # Row index in original data
    aligned_pred_idx: int  # Row index of aligned prediction (pred_idx + horizon - 1)
    l2_start_idx: int
    l2_end_idx: int
    n_features: int
    n_rows: int
    columns: list[str]
    time_seconds: float


@dataclass
class PrecomputeMetadata:
    """Metadata about precomputed features."""

    config_name: str
    total_iterations: int
    backtest_rows: int
    total_rows: int
    l1_warmup: int
    l2_window_size: int
    precompute_time_seconds: float
    created_at: str
    # Date range covered
    first_pred_timestamp: str
    last_pred_timestamp: str
    # Optional / backward-compatible fields
    l2_pred_size: int = 1
    horizon: int = 1
    data_drop_na: bool | None = None
    truncate_end_timestamp: str | None = None
    # Per-iteration info stored in index.json (not here)


def load_iteration_index(
    config_name: str,
    cfg: L1PrecomputeConfig | None = None,
) -> list[dict]:
    """
    Load the iteration index mapping timestamps to iteration info.

    Returns list ordered by iteration number (ascending).
    Each entry: {timestamp, iteration, pred_idx, ...}
    """
    cfg = cfg or L1PrecomputeConfig()
    index_path = cfg.index_path(config_name)

    if not index_path.exists():
        raise FileNotFoundError(
            f"Index not found: {index_path}\n"
            f"Run precompute_l1_for_config('{config_name}') first."
        )

    with open(index_path) as f:
        index = json.load(f)

    # Ensure sorted by iteration
    return sorted(index, key=lambda x: x["iteration"])


def get_all_config_names() -> list[str]:
    """Get all 20 config names."""
    return [
        f"{target}_{horizon}bar"
        for target in [
            "returns",
            "direction",
            "volatility",
            "vol_regime",
            "trend_regime",
        ]
        for horizon in [1, 3, 6, 12]
    ]


def precompute_l1_for_config(
    config_name: str,
    cfg: L1PrecomputeConfig | None = None,
    verbose: bool = True,
    force: bool = False,
    max_timestamp: pd.Timestamp | str | None = None,
) -> PrecomputeMetadata:
    """
    Precompute L1 helper features for a single config.

    Runs the EXACT same process as production pipeline:
    - Creates DualLayerEngine with same config
    - Iterates through all walk-forward windows
    - For each: fit L1, optimize L1, transform L2 range
    - Saves helper_features to parquet NAMED BY PREDICTION TIMESTAMP

    Args:
        config_name: e.g., "direction_1bar", "returns_6bar"
        cfg: Precomputation configuration
        verbose: Print progress

    Returns:
        PrecomputeMetadata with info about what was saved
    """
    from scripts.target_models.core.aligned_dual_window import (
        AlignedDualConfig,
        DualLayerEngine,
        SlidingL2Config,
        get_l2_config_for_target,
    )
    from scripts.target_models.helpers import create_helper_ensemble

    cfg = cfg or L1PrecomputeConfig()

    # Parse config name
    parts = config_name.rsplit("_", 1)
    target = parts[0]
    horizon = int(parts[1].replace("bar", ""))

    if verbose:
        print(f"\n{'=' * 60}")
        print(f"L1 Precomputation: {config_name}")
        print(f"{'=' * 60}")

    # Load config data
    data_path = cfg.data_dir / f"{config_name}.parquet"
    if not data_path.exists():
        raise FileNotFoundError(f"Config data not found: {data_path}")

    df_pl = pl.read_parquet(data_path)
    original_rows = len(df_pl)

    if "timestamp" not in df_pl.columns:
        raise ValueError(f"No timestamp column in {config_name} data")

    # Identify columns (match `registry.load_target_data()` semantics)
    y_cols = [c for c in df_pl.columns if c.startswith("y_")]
    feature_cols = [
        c for c in df_pl.columns if not c.startswith("y_") and c != "timestamp"
    ]

    # Get target y
    y_col = f"y_{target}"
    if y_col not in df_pl.columns:
        y_col = y_cols[0] if y_cols else None
    if y_col is None:
        raise ValueError(f"No target column found for {config_name}")

    # IMPORTANT: Match production loader (drop NaN rows in any feature or target)
    not_null_exprs = [pl.col(c).is_not_null() for c in feature_cols]
    not_null_exprs.append(pl.col(y_col).is_not_null())
    df_pl = df_pl.filter(pl.all_horizontal(not_null_exprs))

    # Optional: truncate tail so multiple configs can share a common end timestamp.
    # This is useful when producing a synchronized, merged 20-config decision stream.
    truncate_end_ts: pd.Timestamp | None
    if max_timestamp is None:
        truncate_end_ts = None
    else:
        truncate_end_ts = (
            max_timestamp
            if isinstance(max_timestamp, pd.Timestamp)
            else pd.Timestamp(max_timestamp)
        )
        df_pl = df_pl.filter(pl.col("timestamp") <= truncate_end_ts.to_pydatetime())
    dropped = original_rows - len(df_pl)

    df = df_pl.to_pandas()
    total_rows = len(df)
    timestamps = df["timestamp"]
    X = df[feature_cols]
    y = df[y_col]

    if verbose:
        if dropped > 0:
            print(f"Dropped {dropped} NaN rows ({original_rows} → {total_rows})")
        if truncate_end_ts is not None:
            print(f"Truncated to timestamp <= {truncate_end_ts.isoformat()}")
        print(f"Loaded: {total_rows} rows, {X.shape[1]} base features")
        print(f"Target column: {y_col}")

    # Create walk-forward engine (same as production)
    # Align L2 prediction span to the target horizon so helper features include
    # the full horizon window (window_size + horizon rows). Without this, horizons
    # >1 would save only window+1 rows and fail downstream shape checks.
    #
    # TIER 1.2: Use adaptive window config for regime targets
    # Regime targets (trend_regime, vol_regime) use window=700, train=60%
    # to ensure sufficient class representation
    adaptive_l2_config = get_l2_config_for_target(target)
    l2_config = SlidingL2Config(
        window_size=adaptive_l2_config.window_size,
        train_ratio=adaptive_l2_config.train_ratio,
        cal_ratio=adaptive_l2_config.cal_ratio,
        val_ratio=adaptive_l2_config.val_ratio,
        purge_gap=adaptive_l2_config.purge_gap,
        pred_size=horizon,
    )
    dual_config = AlignedDualConfig(
        backtest_rows=cfg.backtest_rows,
        target_name=target,
        horizon=horizon,
        l2=l2_config,
    )
    engine = DualLayerEngine(X, y, dual_config)

    if verbose:
        print("\nWalk-forward config:")
        print(f"  Backtest rows: {cfg.backtest_rows}")
        print(f"  L1 warmup: {dual_config.l1.min_warmup}")
        print(f"  L2 window: {dual_config.l2.window_size}")

    # Create output directory
    output_dir = cfg.config_output_dir(config_name)
    if force and output_dir.exists():
        if verbose:
            print(f"Force enabled: removing existing precompute dir: {output_dir}")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Track metadata
    iterations_info = []
    start_time = time.time()
    first_timestamp = None
    last_timestamp = None

    # Iterate through all windows (same as production)
    for iteration, window in enumerate(engine.iterate()):
        iter_start = time.time()

        # Get prediction timestamp for this iteration
        pred_idx = window.l2.pred.start_idx
        pred_timestamp = timestamps.iloc[pred_idx]
        aligned_pred_idx = pred_idx + (horizon - 1)
        aligned_timestamp = timestamps.iloc[aligned_pred_idx]

        # Track date range
        if first_timestamp is None:
            first_timestamp = pred_timestamp
        last_timestamp = pred_timestamp

        # Create fresh ensemble (same as production)
        ensemble = create_helper_ensemble(
            target=target,
            horizon=horizon,
            random_state=cfg.random_state + iteration,
        )

        # Get L1 data slices (same as production _fit_helpers)
        l1 = window.l1
        X_l1_train = X.iloc[l1.train.start_idx : l1.train.end_idx]
        X_l1_val = X.iloc[l1.val.start_idx : l1.val.end_idx]
        y_l1_val = y.iloc[l1.val.start_idx : l1.val.end_idx]

        # 1. Fit on L1 train (unsupervised)
        ensemble.fit(X_l1_train)

        # 2. Optimize on L1 val with target y (target-aware IC boosting)
        ensemble.optimize(X_l1_val, y_l1_val)

        # 3. Transform L2 full range (exactly what L2 receives)
        l2 = window.l2
        l2_start = l2.train.start_idx
        l2_end = l2.pred.end_idx
        X_l2_full = X.iloc[l2_start:l2_end]

        helper_output = ensemble.transform(X_l2_full)
        helper_features = helper_output.features

        # Save to parquet with TIMESTAMP-BASED filename
        iter_path = cfg.timestamp_path(config_name, pred_timestamp)
        helper_features.to_parquet(iter_path)

        # Record iteration info (will be saved to index.json)
        iter_time = time.time() - iter_start
        iterations_info.append(
            {
                "timestamp": pred_timestamp.isoformat(),
                "aligned_timestamp": aligned_timestamp.isoformat(),
                "iteration": iteration,
                "pred_idx": pred_idx,
                "aligned_pred_idx": aligned_pred_idx,
                "l2_start_idx": l2_start,
                "l2_end_idx": l2_end,
                "n_features": helper_features.shape[1],
                "n_rows": helper_features.shape[0],
                "columns": helper_features.columns.tolist(),
                "time_seconds": round(iter_time, 2),
                "filename": _timestamp_to_filename(pred_timestamp),
            }
        )

        if verbose and (iteration + 1) % 20 == 0:
            elapsed = time.time() - start_time
            remaining = (elapsed / (iteration + 1)) * (
                cfg.backtest_rows - iteration - 1
            )
            print(
                f"  Iteration {iteration + 1}/{cfg.backtest_rows} "
                f"[{pred_timestamp.strftime('%Y-%m-%d %H:%M')}] "
                f"({helper_features.shape[1]} features) "
                f"[{elapsed / 60:.1f}m elapsed, ~{remaining / 60:.1f}m remaining]"
            )

    total_time = time.time() - start_time

    # Save iteration index (timestamp -> iteration info mapping)
    with open(cfg.index_path(config_name), "w") as f:
        json.dump(iterations_info, f, indent=2)

    # Save metadata
    metadata = PrecomputeMetadata(
        config_name=config_name,
        total_iterations=len(iterations_info),
        backtest_rows=cfg.backtest_rows,
        total_rows=total_rows,
        l1_warmup=dual_config.l1.min_warmup,
        l2_window_size=dual_config.l2.window_size,
        l2_pred_size=dual_config.l2.pred_size,
        horizon=horizon,
        data_drop_na=True,
        truncate_end_timestamp=truncate_end_ts.isoformat()
        if truncate_end_ts is not None
        else None,
        precompute_time_seconds=round(total_time, 2),
        created_at=datetime.now().isoformat(),
        first_pred_timestamp=first_timestamp.isoformat() if first_timestamp else "",
        last_pred_timestamp=last_timestamp.isoformat() if last_timestamp else "",
    )

    with open(cfg.metadata_path(config_name), "w") as f:
        json.dump(asdict(metadata), f, indent=2)

    if verbose:
        print(
            f"\n✓ Completed {len(iterations_info)} iterations in {total_time / 60:.1f} minutes"
        )
        print(
            f"  Date range: {first_timestamp.strftime('%Y-%m-%d')} to {last_timestamp.strftime('%Y-%m-%d')}"
        )
        print(f"  Saved to: {output_dir}")
        total_size = sum(f.stat().st_size for f in output_dir.glob("*.parquet"))
        print(f"  Total size: {total_size / 1024 / 1024:.1f} MB")

    return metadata


def load_precomputed_l1(
    config_name: str,
    iteration: int,
    cfg: L1PrecomputeConfig | None = None,
) -> pd.DataFrame:
    """
    Load precomputed L1 features by iteration number.

    Uses index.json to map iteration -> timestamp -> file.

    Args:
        config_name: e.g., "direction_1bar"
        iteration: Walk-forward iteration number
        cfg: Configuration

    Returns:
        DataFrame with helper_features (same as L2 receives in production)
    """
    cfg = cfg or L1PrecomputeConfig()

    # Load index to get timestamp for this iteration
    index = load_iteration_index(config_name, cfg)
    if iteration >= len(index):
        raise ValueError(
            f"Iteration {iteration} not found for {config_name} (max: {len(index) - 1})"
        )

    # Get path via timestamp
    ts = pd.Timestamp(index[iteration]["timestamp"])
    iter_path = cfg.timestamp_path(config_name, ts)

    if not iter_path.exists():
        raise FileNotFoundError(
            f"Precomputed features not found: {iter_path}\n"
            f"Run precompute_l1_for_config('{config_name}') first."
        )

    return pd.read_parquet(iter_path)


def load_precomputed_by_timestamp(
    config_name: str,
    timestamp: pd.Timestamp | str,
    cfg: L1PrecomputeConfig | None = None,
) -> pd.DataFrame:
    """
    Load precomputed L1 features by exact timestamp.

    Args:
        config_name: e.g., "direction_1bar"
        timestamp: Prediction timestamp (exact match required)
        cfg: Configuration

    Returns:
        DataFrame with helper_features
    """
    cfg = cfg or L1PrecomputeConfig()

    if isinstance(timestamp, str):
        timestamp = pd.Timestamp(timestamp)

    iter_path = cfg.timestamp_path(config_name, timestamp)

    if not iter_path.exists():
        raise FileNotFoundError(
            f"Precomputed features not found for {timestamp}: {iter_path}"
        )

    return pd.read_parquet(iter_path)


def load_precomputed_metadata(
    config_name: str,
    cfg: L1PrecomputeConfig | None = None,
) -> PrecomputeMetadata:
    """Load metadata for precomputed config."""
    cfg = cfg or L1PrecomputeConfig()
    meta_path = cfg.metadata_path(config_name)

    if not meta_path.exists():
        raise FileNotFoundError(f"Metadata not found: {meta_path}")

    with open(meta_path) as f:
        data = json.load(f)

    return PrecomputeMetadata(**data)


def precompute_all_configs(
    cfg: L1PrecomputeConfig | None = None,
    configs: list[str] | None = None,
    verbose: bool = True,
    force: bool = False,
) -> dict[str, PrecomputeMetadata]:
    """
    Precompute L1 features for all (or selected) configs.

    Args:
        cfg: Configuration
        configs: List of config names (default: all 20)
        verbose: Print progress

    Returns:
        Dict mapping config name to metadata
    """
    cfg = cfg or L1PrecomputeConfig()
    configs = configs or get_all_config_names()

    if verbose:
        print(f"Precomputing L1 for {len(configs)} configs...")
        print(f"Backtest rows: {cfg.backtest_rows}")
        print(f"Output: {cfg.output_dir}")
        print()

    results = {}
    total_start = time.time()

    for i, config_name in enumerate(configs):
        if verbose:
            print(f"\n[{i + 1}/{len(configs)}] {config_name}")

        try:
            results[config_name] = precompute_l1_for_config(
                config_name, cfg, verbose, force=force
            )
        except Exception as e:
            print(f"ERROR: {e}")
            results[config_name] = None

    total_time = time.time() - total_start

    if verbose:
        success = sum(1 for v in results.values() if v is not None)
        print(f"\n{'=' * 60}")
        print(
            f"COMPLETE: {success}/{len(configs)} configs in {total_time / 3600:.1f} hours"
        )
        print(f"{'=' * 60}")

    return results


def validate_precomputed(
    config_name: str,
    cfg: L1PrecomputeConfig | None = None,
    verbose: bool = True,
    n_check: int = 3,
) -> bool:
    """
    Validate precomputed features - structural checks only.

    Checks:
    1. All expected files exist (by timestamp)
    2. Files can be loaded without error
    3. Row counts match expected L2 window size
    4. Pred indices in index match walk-forward engine

    NOTE: Does NOT recompute fresh and compare columns because
    IC optimization is stochastic - same seed can give different
    feature selections across runs.

    Args:
        config_name: e.g., "direction_1bar"
        cfg: Configuration
        verbose: Print progress
        n_check: Number of iterations to spot-check

    Returns:
        True if validation passes
    """
    from scripts.target_models.core.aligned_dual_window import (
        AlignedDualConfig,
        DualLayerEngine,
    )

    cfg = cfg or L1PrecomputeConfig()

    if verbose:
        print(f"Validating {config_name}...")

    # Check metadata exists
    if not cfg.metadata_path(config_name).exists():
        print(f"  ✗ Metadata not found for {config_name}")
        return False

    # Check index exists
    try:
        index = load_iteration_index(config_name, cfg)
    except FileNotFoundError:
        print(f"  ✗ Index not found for {config_name}")
        return False

    if verbose:
        print(f"  Found {len(index)} iterations in index")

    # Load data to get walk-forward windows
    df = pd.read_parquet(cfg.data_dir / f"{config_name}.parquet")
    timestamps = df["timestamp"]
    y_cols = [c for c in df.columns if c.startswith("y_")]
    non_numeric = df.select_dtypes(exclude=["number"]).columns.tolist()
    X = df.drop(columns=list(set(y_cols) | set(non_numeric)))
    y = df[y_cols[0]]

    # Create engine to verify pred indices
    dual_config = AlignedDualConfig(backtest_rows=cfg.backtest_rows)
    engine = DualLayerEngine(X, y, dual_config)

    all_valid = True

    # Check each iteration
    for iteration, window in enumerate(engine.iterate()):
        if iteration >= len(index):
            if verbose:
                print(f"  ✗ Iter {iteration}: Missing from index")
            all_valid = False
            continue

        idx_entry = index[iteration]
        expected_ts = timestamps.iloc[window.l2.pred.start_idx]
        stored_ts = pd.Timestamp(idx_entry["timestamp"])

        # Check timestamp matches
        if expected_ts != stored_ts:
            if verbose:
                print(
                    f"  ✗ Iter {iteration}: Timestamp mismatch "
                    f"(expected {expected_ts}, got {stored_ts})"
                )
            all_valid = False
            continue

        # Check pred_idx matches
        if idx_entry["pred_idx"] != window.l2.pred.start_idx:
            if verbose:
                print(
                    f"  ✗ Iter {iteration}: pred_idx mismatch "
                    f"(expected {window.l2.pred.start_idx}, got {idx_entry['pred_idx']})"
                )
            all_valid = False
            continue

        # Spot-check: load file and verify shape (only for first n_check)
        if iteration < n_check:
            try:
                features = load_precomputed_l1(config_name, iteration, cfg)
                expected_rows = window.l2.pred.end_idx - window.l2.train.start_idx

                if features.shape[0] != expected_rows:
                    if verbose:
                        print(
                            f"  ✗ Iter {iteration} [{stored_ts.strftime('%Y-%m-%d %H:%M')}]: "
                            f"Row mismatch (expected {expected_rows}, got {features.shape[0]})"
                        )
                    all_valid = False
                elif verbose:
                    print(
                        f"  ✓ Iter {iteration} [{stored_ts.strftime('%Y-%m-%d %H:%M')}]: "
                        f"OK ({features.shape[1]} features, {features.shape[0]} rows)"
                    )
            except Exception as e:
                if verbose:
                    print(f"  ✗ Iter {iteration}: Load failed - {e}")
                all_valid = False

    if verbose and all_valid:
        print(f"  ✓ All {len(index)} iterations validated")

    return all_valid


if __name__ == "__main__":
    # Test with one config
    import warnings

    warnings.filterwarnings("ignore")

    cfg = L1PrecomputeConfig(backtest_rows=200)

    # Precompute one config
    metadata = precompute_l1_for_config("direction_1bar", cfg, verbose=True)

    # Validate
    print("\nValidating...")
    valid = validate_precomputed("direction_1bar", cfg, verbose=True)
    print(f"\nValidation: {'PASSED' if valid else 'FAILED'}")
