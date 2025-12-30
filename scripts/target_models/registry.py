"""
Target-Horizon Registry and Data Loading Utilities.

Central registry for all 20 target-horizon combinations with:
- Data loading with validation (Polars for speed, converts to pandas for models)
- Task type inference
- Purge gap calculation
- Cross-target testing infrastructure
- TIMESTAMP-ALIGNED DATA for synchronized 20-target predictions

Performance:
- Uses Polars for fast parquet reading (~3x faster than pandas)
- Uses Polars for NaN filtering (~2x faster, less memory)
- Converts to pandas/numpy at output (models expect pandas)
- ~40% less peak memory usage during loading

Usage:
    from scripts.target_models.registry import (
        get_target_spec,
        load_target_data,
        load_aligned_data,  # NEW: All 20 targets aligned by timestamp
        iterate_all_targets,
        validate_all_targets,
    )

    # Load specific target-horizon
    X, y, spec = load_target_data("volatility", 6)

    # Load ALL 20 targets aligned by timestamp (for synchronized prediction)
    aligned = load_aligned_data()
    # aligned.X = features (4679 x 166)
    # aligned.targets = dict of 20 target Series, all same timestamps

    # Iterate all 20 combinations
    for target, horizon, X, y, spec in iterate_all_targets():
        print(f"{target}_{horizon}bar: {X.shape}")

    # Validate all targets load correctly
    results = validate_all_targets()
"""

from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
import polars as pl

# =============================================================================
# PATHS
# =============================================================================
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DATASETS_DIR = DATA_DIR / "datasets"


# =============================================================================
# TARGET SPECIFICATION
# =============================================================================
@dataclass(frozen=True)
class TargetSpec:
    """
    Complete specification for a target-horizon combination.

    Immutable dataclass with all info needed to load, train, and evaluate.
    """

    target: str
    horizon: int
    task_type: Literal["regression", "binary", "multiclass"]
    target_column: str
    primary_metric: str
    secondary_metrics: tuple[str, ...]
    n_classes: int = 2  # For classification (binary=2, vol_regime=3)

    @property
    def identifier(self) -> str:
        """Unique identifier: target_horizon"""
        return f"{self.target}_{self.horizon}bar"

    @property
    def dataset_path(self) -> Path:
        """Path to parquet dataset."""
        return DATASETS_DIR / f"{self.identifier}.parquet"

    @property
    def purge_gap(self) -> int:
        """
        Recommended purge gap for temporal CV.

        Rule: max(21, horizon + 15) to ensure no leakage from:
        - Feature lookback (max 21 bars)
        - Target horizon overlap
        """
        return max(21, self.horizon + 15)

    @property
    def embargo_gap(self) -> int:
        """
        Recommended embargo gap after test set.

        Rule: horizon + 5 bars safety buffer
        """
        return self.horizon + 5

    def __repr__(self) -> str:
        return (
            f"TargetSpec({self.identifier}, {self.task_type}, "
            f"metric={self.primary_metric})"
        )


# =============================================================================
# REGISTRY: ALL 20 TARGET-HORIZON COMBINATIONS
# =============================================================================
def _build_registry() -> dict[tuple[str, int], TargetSpec]:
    """Build complete registry of all 20 target-horizon specs."""

    registry = {}
    horizons = (1, 3, 6, 12)

    # Volatility: Regression
    for h in horizons:
        registry[("volatility", h)] = TargetSpec(
            target="volatility",
            horizon=h,
            task_type="regression",
            target_column="y_volatility",
            primary_metric="ic",  # Information Coefficient for regression
            secondary_metrics=("rmse", "mae", "r2"),
        )

    # Returns: Regression
    for h in horizons:
        registry[("returns", h)] = TargetSpec(
            target="returns",
            horizon=h,
            task_type="regression",
            target_column="y_returns",
            primary_metric="ic",
            secondary_metrics=("rmse", "mae", "r2"),
        )

    # Direction: Binary classification
    for h in horizons:
        registry[("direction", h)] = TargetSpec(
            target="direction",
            horizon=h,
            task_type="binary",
            target_column="y_direction",
            primary_metric="auc",
            secondary_metrics=("accuracy", "f1", "log_loss"),
            n_classes=2,
        )

    # Vol Regime: Multiclass (LOW=0, MED=1, HIGH=2)
    for h in horizons:
        registry[("vol_regime", h)] = TargetSpec(
            target="vol_regime",
            horizon=h,
            task_type="multiclass",
            target_column="y_vol_regime",
            primary_metric="accuracy",
            secondary_metrics=("f1_macro", "log_loss"),
            n_classes=3,
        )

    # Trend Regime: Binary classification
    for h in horizons:
        registry[("trend_regime", h)] = TargetSpec(
            target="trend_regime",
            horizon=h,
            task_type="binary",
            target_column="y_trend_regime",
            primary_metric="auc",
            secondary_metrics=("accuracy", "f1"),
            n_classes=2,
        )

    return registry


# Singleton registry
TARGET_REGISTRY: dict[tuple[str, int], TargetSpec] = _build_registry()

# All valid targets and horizons
ALL_TARGETS = ("volatility", "returns", "direction", "vol_regime", "trend_regime")
ALL_HORIZONS = (1, 3, 6, 12)


# =============================================================================
# ACCESSOR FUNCTIONS
# =============================================================================
def get_target_spec(target: str, horizon: int) -> TargetSpec:
    """
    Get specification for a target-horizon combination.

    Args:
        target: One of: volatility, returns, direction, vol_regime, trend_regime
        horizon: One of: 1, 3, 6, 12

    Returns:
        TargetSpec with all configuration

    Raises:
        KeyError: If target-horizon combination not found
    """
    key = (target, horizon)
    if key not in TARGET_REGISTRY:
        raise KeyError(
            f"Unknown target-horizon: {target}_{horizon}bar. "
            f"Valid targets: {ALL_TARGETS}, horizons: {ALL_HORIZONS}"
        )
    return TARGET_REGISTRY[key]


def list_all_specs() -> list[TargetSpec]:
    """Get list of all 20 target specs in standard order."""
    specs = []
    for target in ALL_TARGETS:
        for horizon in ALL_HORIZONS:
            specs.append(TARGET_REGISTRY[(target, horizon)])
    return specs


# =============================================================================
# DATA LOADING (Polars-optimized)
# =============================================================================
def load_target_data(
    target: str,
    horizon: int,
    drop_na: bool = True,
    verbose: bool = True,
    as_numpy: bool = False,
) -> tuple[pd.DataFrame | np.ndarray, pd.Series | np.ndarray, TargetSpec]:
    """
    Load dataset for a specific target-horizon combination.

    Uses Polars internally for fast loading and NaN filtering,
    converts to pandas/numpy at output for model compatibility.

    Performs:
    1. Path validation
    2. Fast parquet read with Polars
    3. Feature selection (exclude y_*, timestamp)
    4. NaN filtering with Polars (faster than pandas)
    5. Convert to pandas DataFrame / numpy array

    Args:
        target: Target name
        horizon: Prediction horizon
        drop_na: Whether to drop rows with NaN (default True)
        verbose: Print loading summary
        as_numpy: Return numpy arrays instead of pandas (faster for some models)

    Returns:
        X: Feature DataFrame or ndarray (clean)
        y: Target Series or ndarray (clean)
        spec: TargetSpec for this combination

    Raises:
        FileNotFoundError: If dataset doesn't exist
        ValueError: If target column not found
    """
    spec = get_target_spec(target, horizon)

    if not spec.dataset_path.exists():
        raise FileNotFoundError(
            f"Dataset not found: {spec.dataset_path}\n"
            f"Run: python -m scripts.analysis.run build-datasets"
        )

    # Fast read with Polars
    df = pl.read_parquet(spec.dataset_path)
    original_len = len(df)

    # Validate target column exists
    if spec.target_column not in df.columns:
        raise ValueError(
            f"Target column '{spec.target_column}' not found in {spec.identifier}. "
            f"Available: {[c for c in df.columns if c.startswith('y_')]}"
        )

    # Identify feature columns (exclude y_* and timestamp)
    feature_cols = [
        c for c in df.columns if not c.startswith("y_") and c != "timestamp"
    ]

    # Clean NaN with Polars (much faster than pandas)
    if drop_na:
        # Build filter: all features not null AND target not null
        not_null_exprs = [pl.col(c).is_not_null() for c in feature_cols]
        not_null_exprs.append(pl.col(spec.target_column).is_not_null())

        # Apply filter
        df = df.filter(pl.all_horizontal(not_null_exprs))

        dropped = original_len - len(df)
        if verbose and dropped > 0:
            print(
                f"  {spec.identifier}: Dropped {dropped} NaN rows "
                f"({original_len} → {len(df)})"
            )

    # Extract X and y
    if as_numpy:
        # Direct to numpy (fastest for sklearn models)
        X = df.select(feature_cols).to_numpy()
        y = df.select(spec.target_column).to_numpy().ravel()
    else:
        # Convert to pandas (for models that need DataFrames)
        X = df.select(feature_cols).to_pandas()
        y = df.select(spec.target_column).to_pandas().iloc[:, 0]

    if verbose:
        shape = X.shape if hasattr(X, "shape") else (len(X), len(feature_cols))
        print(f"Loaded {spec.identifier}: X={shape}, y={len(y)}, task={spec.task_type}")

    return X, y, spec


def load_target_data_polars(
    target: str,
    horizon: int,
    drop_na: bool = True,
) -> tuple[pl.DataFrame, pl.Series, TargetSpec]:
    """
    Load dataset returning native Polars objects (no conversion).

    Use this when doing Polars-native operations like feature engineering.
    For model training, use load_target_data() which returns pandas.

    Returns:
        X: Feature DataFrame (Polars)
        y: Target Series (Polars)
        spec: TargetSpec
    """
    spec = get_target_spec(target, horizon)

    if not spec.dataset_path.exists():
        raise FileNotFoundError(f"Dataset not found: {spec.dataset_path}")

    df = pl.read_parquet(spec.dataset_path)

    # Identify feature columns
    feature_cols = [
        c for c in df.columns if not c.startswith("y_") and c != "timestamp"
    ]

    # Clean NaN
    if drop_na:
        not_null_exprs = [pl.col(c).is_not_null() for c in feature_cols]
        not_null_exprs.append(pl.col(spec.target_column).is_not_null())
        df = df.filter(pl.all_horizontal(not_null_exprs))

    X = df.select(feature_cols)
    y = df.select(spec.target_column).to_series()

    return X, y, spec


def load_all_targets(
    drop_na: bool = True,
    verbose: bool = False,
    as_numpy: bool = False,
) -> dict[str, tuple[pd.DataFrame | np.ndarray, pd.Series | np.ndarray, TargetSpec]]:
    """
    Load all 20 datasets into memory.

    Args:
        drop_na: Drop NaN rows
        verbose: Print loading info
        as_numpy: Return numpy arrays instead of pandas

    Returns:
        Dict mapping identifier → (X, y, spec)
    """
    all_data = {}

    for spec in list_all_specs():
        X, y, _ = load_target_data(
            spec.target,
            spec.horizon,
            drop_na=drop_na,
            verbose=verbose,
            as_numpy=as_numpy,
        )
        all_data[spec.identifier] = (X, y, spec)

    return all_data


# =============================================================================
# ITERATION UTILITIES
# =============================================================================
def iterate_all_targets(
    targets: tuple[str, ...] = None,
    horizons: tuple[int, ...] = None,
    drop_na: bool = True,
    verbose: bool = False,
) -> Generator[tuple[str, int, pd.DataFrame, pd.Series, TargetSpec], None, None]:
    """
    Iterate over target-horizon combinations, yielding loaded data.

    Args:
        targets: Subset of targets (default all)
        horizons: Subset of horizons (default all)
        drop_na: Whether to drop NaN rows
        verbose: Print loading info

    Yields:
        (target, horizon, X, y, spec) for each combination

    Example:
        for target, horizon, X, y, spec in iterate_all_targets():
            model = train_model(X, y, spec.task_type)
    """
    targets = targets or ALL_TARGETS
    horizons = horizons or ALL_HORIZONS

    for target in targets:
        for horizon in horizons:
            X, y, spec = load_target_data(
                target, horizon, drop_na=drop_na, verbose=verbose
            )
            yield target, horizon, X, y, spec


def iterate_by_task_type(
    task_type: Literal["regression", "binary", "multiclass"],
    drop_na: bool = True,
    verbose: bool = False,
) -> Generator[tuple[str, int, pd.DataFrame, pd.Series, TargetSpec], None, None]:
    """
    Iterate only targets with specific task type.

    Example:
        # Train all regression models
        for target, horizon, X, y, spec in iterate_by_task_type("regression"):
            ridge = Ridge().fit(X, y)
    """
    for target, horizon, X, y, spec in iterate_all_targets(
        drop_na=drop_na, verbose=verbose
    ):
        if spec.task_type == task_type:
            yield target, horizon, X, y, spec


# =============================================================================
# VALIDATION & TESTING
# =============================================================================
@dataclass
class ValidationResult:
    """Result from validating a single target-horizon."""

    identifier: str
    success: bool
    n_rows: int
    n_features: int
    n_nan_dropped: int
    target_dtype: str
    task_type: str
    error: str | None = None

    def __repr__(self) -> str:
        status = "✓" if self.success else "✗"
        return f"{status} {self.identifier}: {self.n_rows}×{self.n_features} ({self.task_type})"


def validate_target(target: str, horizon: int) -> ValidationResult:
    """
    Validate a single target-horizon dataset using Polars.

    Checks:
    - File exists
    - Target column present
    - Can load and clean data
    - Reasonable number of rows after NaN drop
    """
    spec = get_target_spec(target, horizon)

    try:
        # Check file exists
        if not spec.dataset_path.exists():
            return ValidationResult(
                identifier=spec.identifier,
                success=False,
                n_rows=0,
                n_features=0,
                n_nan_dropped=0,
                target_dtype="",
                task_type=spec.task_type,
                error=f"File not found: {spec.dataset_path}",
            )

        # Load with Polars (fast) to count original
        df = pl.read_parquet(spec.dataset_path)
        original_len = len(df)

        # Check target column
        if spec.target_column not in df.columns:
            return ValidationResult(
                identifier=spec.identifier,
                success=False,
                n_rows=0,
                n_features=0,
                n_nan_dropped=0,
                target_dtype="",
                task_type=spec.task_type,
                error=f"Target column '{spec.target_column}' not found",
            )

        # Get target dtype from Polars
        target_dtype = str(df.schema[spec.target_column])

        # Load with NaN drop
        X, y, _ = load_target_data(target, horizon, drop_na=True, verbose=False)
        n_nan_dropped = original_len - len(X)

        # Count features
        n_features = X.shape[1] if hasattr(X, "shape") else len(X.columns)

        # Validate reasonable data
        if len(X) < 100:
            return ValidationResult(
                identifier=spec.identifier,
                success=False,
                n_rows=len(X),
                n_features=n_features,
                n_nan_dropped=n_nan_dropped,
                target_dtype=target_dtype,
                task_type=spec.task_type,
                error=f"Too few rows after NaN drop: {len(X)}",
            )

        return ValidationResult(
            identifier=spec.identifier,
            success=True,
            n_rows=len(X),
            n_features=n_features,
            n_nan_dropped=n_nan_dropped,
            target_dtype=target_dtype,
            task_type=spec.task_type,
        )

    except Exception as e:
        return ValidationResult(
            identifier=spec.identifier,
            success=False,
            n_rows=0,
            n_features=0,
            n_nan_dropped=0,
            target_dtype="",
            task_type=spec.task_type,
            error=str(e),
        )


def validate_all_targets(verbose: bool = True) -> list[ValidationResult]:
    """
    Validate all 20 target-horizon datasets.

    Returns list of ValidationResults and optionally prints summary.
    """
    results = []

    for spec in list_all_specs():
        result = validate_target(spec.target, spec.horizon)
        results.append(result)

        if verbose:
            print(result)

    if verbose:
        n_pass = sum(1 for r in results if r.success)
        n_fail = len(results) - n_pass
        print(f"\nValidation: {n_pass}/{len(results)} pass, {n_fail} fail")

    return results


def get_summary_table() -> pd.DataFrame:
    """
    Get summary DataFrame of all 20 target-horizon combinations.

    Useful for documentation and verification.
    """
    rows = []

    for spec in list_all_specs():
        result = validate_target(spec.target, spec.horizon)
        rows.append(
            {
                "target": spec.target,
                "horizon": spec.horizon,
                "identifier": spec.identifier,
                "task_type": spec.task_type,
                "n_rows": result.n_rows,
                "n_features": result.n_features,
                "n_nan_dropped": result.n_nan_dropped,
                "target_dtype": result.target_dtype,
                "primary_metric": spec.primary_metric,
                "purge_gap": spec.purge_gap,
                "valid": result.success,
            }
        )

    return pd.DataFrame(rows)


# =============================================================================
# TIMESTAMP-ALIGNED DATA LOADING
# =============================================================================
@dataclass
class AlignedData:
    """
    Container for timestamp-aligned data across all 20 targets.

    All targets share the same timestamps, enabling synchronized predictions.
    """

    timestamps: pd.DatetimeIndex  # Common timestamps (index)
    X: pd.DataFrame  # Features (same for all targets)
    targets: dict[str, pd.Series]  # target_identifier → y series
    specs: dict[str, TargetSpec]  # target_identifier → spec

    @property
    def n_rows(self) -> int:
        """Number of common aligned rows."""
        return len(self.timestamps)

    @property
    def n_features(self) -> int:
        """Number of features."""
        return self.X.shape[1]

    @property
    def n_targets(self) -> int:
        """Number of targets."""
        return len(self.targets)

    def get_target(self, target: str, horizon: int) -> tuple[pd.Series, TargetSpec]:
        """Get specific target and its spec."""
        identifier = f"{target}_{horizon}bar"
        return self.targets[identifier], self.specs[identifier]

    def __repr__(self) -> str:
        return (
            f"AlignedData(rows={self.n_rows}, features={self.n_features}, "
            f"targets={self.n_targets}, "
            f"range=[{self.timestamps[0]} → {self.timestamps[-1]}])"
        )


def load_aligned_data(
    targets: tuple[str, ...] | None = None,
    horizons: tuple[int, ...] | None = None,
    verbose: bool = True,
) -> AlignedData:
    """
    Load all target-horizon combinations aligned by timestamp.

    This ensures all 20 targets can make predictions for the SAME timestamp.
    Only rows where ALL requested targets have valid data are included.

    Pipeline Design:
    - L1 expanding: Uses all history from start to L2 start
    - L2 sliding: Fixed window (e.g., 500 rows)
    - Prediction: Same timestamp for all targets

    Args:
        targets: Subset of targets to load (default: all 5)
        horizons: Subset of horizons to load (default: all 4)
        verbose: Print loading summary

    Returns:
        AlignedData with synchronized timestamps across all targets
    """
    targets = targets or ALL_TARGETS
    horizons = horizons or ALL_HORIZONS

    # Step 1: Load all raw data with timestamps
    raw_data: dict[str, pl.DataFrame] = {}
    all_specs: dict[str, TargetSpec] = {}

    for target in targets:
        for horizon in horizons:
            spec = get_target_spec(target, horizon)
            identifier = spec.identifier

            if not spec.dataset_path.exists():
                raise FileNotFoundError(f"Dataset not found: {spec.dataset_path}")

            df = pl.read_parquet(spec.dataset_path)
            raw_data[identifier] = df
            all_specs[identifier] = spec

    if verbose:
        print(f"Loaded {len(raw_data)} raw datasets")

    # Step 2: Find common valid timestamp range
    # For each dataset, get timestamps where features AND target are valid

    valid_ts_sets: list[set] = []

    # Get feature columns (same across all)
    first_df = list(raw_data.values())[0]
    feature_cols = [
        c for c in first_df.columns if not c.startswith("y_") and c != "timestamp"
    ]

    for identifier, df in raw_data.items():
        spec = all_specs[identifier]

        # Build validity filter: all features + target not null
        not_null_exprs = [pl.col(c).is_not_null() for c in feature_cols]
        not_null_exprs.append(pl.col(spec.target_column).is_not_null())

        valid_df = df.filter(pl.all_horizontal(not_null_exprs))
        # Use epoch nanoseconds for consistent comparison (int64)
        valid_timestamps = set(
            valid_df.select(pl.col("timestamp").dt.epoch("ns")).to_series().to_list()
        )
        valid_ts_sets.append(valid_timestamps)

    # Intersection of all valid timestamps
    common_ts_ns = sorted(set.intersection(*valid_ts_sets))

    if verbose:
        print(f"Common valid timestamps: {len(common_ts_ns)}")
        # Convert back for display
        first_ts = pd.Timestamp(common_ts_ns[0], unit="ns", tz="UTC")
        last_ts = pd.Timestamp(common_ts_ns[-1], unit="ns", tz="UTC")
        print(f"  First: {first_ts}")
        print(f"  Last: {last_ts}")

    # Step 3: Extract aligned data
    # Use first dataset for features (they're identical across targets)
    first_identifier = list(raw_data.keys())[0]
    first_df = raw_data[first_identifier]

    # Filter to common timestamps using epoch comparison
    aligned_df = first_df.filter(pl.col("timestamp").dt.epoch("ns").is_in(common_ts_ns))

    # Extract features and timestamps
    timestamps = pd.DatetimeIndex(aligned_df["timestamp"].to_list())
    X = aligned_df.select(feature_cols).to_pandas()
    X.index = timestamps  # Use timestamp as index

    # Extract each target aligned to common timestamps
    aligned_targets: dict[str, pd.Series] = {}

    for identifier, df in raw_data.items():
        spec = all_specs[identifier]

        # Filter to common timestamps
        aligned = df.filter(pl.col("timestamp").dt.epoch("ns").is_in(common_ts_ns))

        # Extract target column
        y = aligned.select(spec.target_column).to_pandas().iloc[:, 0]
        y.index = timestamps
        y.name = identifier
        aligned_targets[identifier] = y

    if verbose:
        print(f"Aligned data: X={X.shape}, targets={len(aligned_targets)}")

    return AlignedData(
        timestamps=timestamps,
        X=X,
        targets=aligned_targets,
        specs=all_specs,
    )


def get_common_timestamp_range() -> tuple[pd.Timestamp, pd.Timestamp, int]:
    """
    Get the common valid timestamp range across all 20 targets.

    Returns:
        (first_timestamp, last_timestamp, n_rows)
    """
    aligned = load_aligned_data(verbose=False)
    return aligned.timestamps[0], aligned.timestamps[-1], len(aligned.timestamps)


# =============================================================================
# CLI CONVENIENCE
# =============================================================================
def main():
    """CLI entry point for validation."""
    import sys

    print("=" * 60)
    print("TARGET-HORIZON REGISTRY VALIDATION")
    print("=" * 60)
    print()

    results = validate_all_targets(verbose=True)

    print()
    print("=" * 60)
    print("SUMMARY TABLE")
    print("=" * 60)
    df = get_summary_table()
    print(df.to_string(index=False))

    # Exit with error if any failed
    n_fail = sum(1 for r in results if not r.success)
    sys.exit(n_fail)


if __name__ == "__main__":
    main()
