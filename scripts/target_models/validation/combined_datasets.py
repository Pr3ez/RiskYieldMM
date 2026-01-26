"""
Combined Datasets Module
========================

Creates comprehensive feature datasets combining:
1. Raw features (170 base features from feature engineering)
2. Helper features (91 L1 helper-derived features)
3. Interaction features (2-5 per config, target-optimized)

Total: ~263 features per config

These datasets are designed for:
- Robust feature selection experiments
- Model comparison with full feature access
- Feature importance analysis

Usage:
    from scripts.target_models.validation.combined_datasets import (
        create_combined_dataset,
        create_all_combined_datasets,
        load_combined_dataset,
    )

    # Create for one config
    df = create_combined_dataset('direction_1bar')

    # Create for all 16 configs
    results = create_all_combined_datasets()

    # Load existing
    df = load_combined_dataset('direction_1bar')
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd
import polars as pl

# Centralized config generation (Single Source of Truth)
# DO NOT HARDCODE CONFIG LISTS - add new targets to config.py → WORKFLOW_TARGETS
from scripts.workflow.config import get_all_configs

logger = logging.getLogger(__name__)

# All target configurations (WORKFLOW_TARGETS × ALL_HORIZONS)
# Auto-generated from config.py - DO NOT HARDCODE
ALL_CONFIGS = get_all_configs()

# Columns to exclude from features (targets and metadata)
EXCLUDE_PREFIXES = ("y_", "timestamp")
EXCLUDE_EXACT = {"open", "high", "low", "close", "volume", "pred_idx"}


def _get_feature_columns(columns: list[str]) -> list[str]:
    """Filter to only feature columns (exclude targets and metadata)."""
    return [
        c
        for c in columns
        if not any(c.startswith(p) for p in EXCLUDE_PREFIXES) and c not in EXCLUDE_EXACT
    ]


def _get_target_columns(columns: list[str]) -> list[str]:
    """Get target columns (y_*)."""
    return [c for c in columns if c.startswith("y_")]


def create_combined_dataset(
    config: str,
    datasets_dir: Path | str = "data/datasets",
    precomputed_dir: Path | str = "data/precomputed",
    output_dir: Path | str = "data/combined_datasets",
    save: bool = True,
) -> pd.DataFrame:
    """
    Create a combined dataset with all features for a single config.

    Combines:
    - Raw features from datasets/{config}.parquet
    - Helper features from precomputed/{config}/assembled.parquet
    - Interaction features (already in both, deduplicated)

    Parameters
    ----------
    config : str
        Configuration name (e.g., 'direction_1bar')
    datasets_dir : Path or str
        Directory containing raw feature datasets
    precomputed_dir : Path or str
        Directory containing L1 precomputed helper features
    output_dir : Path or str
        Directory to save combined datasets
    save : bool
        Whether to save the result to parquet

    Returns
    -------
    pd.DataFrame
        Combined dataset with all features and targets
    """
    datasets_dir = Path(datasets_dir)
    precomputed_dir = Path(precomputed_dir)
    output_dir = Path(output_dir)

    # Load raw dataset
    raw_path = datasets_dir / f"{config}.parquet"
    if not raw_path.exists():
        raise FileNotFoundError(f"Raw dataset not found: {raw_path}")

    raw_df = pl.read_parquet(raw_path).to_pandas()
    logger.info(f"Loaded raw dataset: {raw_df.shape}")

    # Load assembled helper features
    assembled_path = precomputed_dir / config / "assembled.parquet"
    if not assembled_path.exists():
        raise FileNotFoundError(f"Assembled dataset not found: {assembled_path}")

    assembled_df = pd.read_parquet(assembled_path)
    logger.info(f"Loaded assembled dataset: {assembled_df.shape}")

    # Get pred_idx and timestamps for alignment
    # assembled_df has timestamp as index (from L1 precompute)
    if "pred_idx" not in assembled_df.columns:
        raise ValueError("assembled.parquet missing pred_idx column")

    pred_idx = assembled_df["pred_idx"].values.astype(int)

    # Get timestamps from assembled_df index (this is the authoritative source)
    # These timestamps were recorded during L1 precompute and are correct
    # NOTE: Use the index directly (DatetimeIndex), not .values (numpy loses timezone)
    if assembled_df.index.name == "timestamp":
        timestamps = assembled_df.index
    else:
        # Fallback: try to get from column if index was reset
        if "timestamp" in assembled_df.columns:
            timestamps = pd.DatetimeIndex(assembled_df["timestamp"])
        else:
            raise ValueError(
                "assembled.parquet missing timestamp (neither in index nor columns)"
            )

    # Use TIMESTAMP-based alignment instead of pred_idx as row index
    # This is robust to dataset size changes (new data prepended/appended)
    raw_feature_cols = _get_feature_columns(raw_df.columns.tolist())
    target_cols = _get_target_columns(raw_df.columns.tolist())

    # Set timestamp as index on raw_df for efficient lookup
    if "timestamp" not in raw_df.columns:
        raise ValueError(f"Raw dataset {config} missing timestamp column")

    raw_df_indexed = raw_df.set_index("timestamp")

    # Use .loc for timestamp lookup - handles dtype differences (ns vs ms) correctly
    # Unlike reindex, .loc properly matches timestamps across different precisions
    try:
        raw_subset = raw_df_indexed.loc[timestamps]
    except KeyError:
        # Some timestamps may not exist in raw (data gaps)
        missing_ts = [ts for ts in timestamps if ts not in raw_df_indexed.index]
        print(
            f"  WARNING: {len(missing_ts)}/{len(timestamps)} timestamps not found in raw dataset"
        )
        # Fall back to reindex which fills missing with NaN
        raw_subset = raw_df_indexed.reindex(timestamps)

    # Extract raw features at timestamp positions
    raw_features = raw_subset[raw_feature_cols].reset_index(drop=True)

    # Extract targets at timestamp positions
    targets = raw_subset[target_cols].reset_index(drop=True)

    # Extract helper features (exclude pred_idx and interactions already in raw)
    helper_cols = [c for c in assembled_df.columns if c.startswith("H_")]
    helper_features = assembled_df[helper_cols].reset_index(drop=True)

    # Build combined dataset
    combined = pd.DataFrame()

    # Add pred_idx first (for reference)
    combined["pred_idx"] = pred_idx

    # Add timestamp column (authoritative source from assembled.parquet)
    combined["timestamp"] = timestamps

    # Add raw features
    for col in raw_features.columns:
        combined[col] = raw_features[col].values

    # Add helper features
    for col in helper_features.columns:
        combined[col] = helper_features[col].values

    # Add targets last
    for col in targets.columns:
        combined[col] = targets[col].values

    # Summary
    n_raw = len(
        [
            c
            for c in combined.columns
            if not c.startswith("H_")
            and not c.startswith("y_")
            and c not in ("pred_idx", "timestamp")
        ]
    )
    n_helper = len([c for c in combined.columns if c.startswith("H_")])
    n_interactions = len([c for c in combined.columns if "×" in c])
    n_targets = len([c for c in combined.columns if c.startswith("y_")])

    logger.info(f"Combined dataset for {config}:")
    logger.info(f"  Raw features: {n_raw}")
    logger.info(f"  Helper features: {n_helper}")
    logger.info(f"  Interaction features: {n_interactions}")
    logger.info(f"  Targets: {n_targets}")
    logger.info(f"  Total columns: {len(combined.columns)}")
    logger.info(f"  Rows: {len(combined)}")

    # Save if requested
    if save:
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{config}.parquet"
        combined.to_parquet(output_path, index=False)
        logger.info(f"Saved to {output_path}")

    return combined


def create_all_combined_datasets(
    configs: list[str] | None = None,
    datasets_dir: Path | str = "data/datasets",
    precomputed_dir: Path | str = "data/precomputed",
    output_dir: Path | str = "data/combined_datasets",
    verbose: bool = True,
) -> dict[str, dict[str, Any]]:
    """
    Create combined datasets for all (or specified) configurations.

    Parameters
    ----------
    configs : list[str] or None
        List of configs to process. If None, processes all 16 configs.
    datasets_dir, precomputed_dir, output_dir : Path or str
        Directory paths
    verbose : bool
        Print progress

    Returns
    -------
    dict
        Results for each config with shape and feature counts
    """
    if configs is None:
        configs = ALL_CONFIGS

    results = {}

    for i, config in enumerate(configs, 1):
        if verbose:
            print(f"[{i}/{len(configs)}] Creating combined dataset for {config}...")

        try:
            df = create_combined_dataset(
                config=config,
                datasets_dir=datasets_dir,
                precomputed_dir=precomputed_dir,
                output_dir=output_dir,
                save=True,
            )

            n_raw = len(
                [
                    c
                    for c in df.columns
                    if not c.startswith("H_")
                    and not c.startswith("y_")
                    and c != "pred_idx"
                ]
            )
            n_helper = len([c for c in df.columns if c.startswith("H_")])
            n_interactions = len([c for c in df.columns if "×" in c])

            results[config] = {
                "status": "success",
                "rows": len(df),
                "total_cols": len(df.columns),
                "raw_features": n_raw,
                "helper_features": n_helper,
                "interaction_features": n_interactions,
            }

            if verbose:
                print(
                    f"    ✅ {len(df)} rows × {len(df.columns)} cols "
                    f"(raw={n_raw}, helper={n_helper}, interactions={n_interactions})"
                )

        except Exception as e:
            results[config] = {
                "status": "error",
                "error": str(e),
            }
            if verbose:
                print(f"    ❌ Error: {e}")

    return results


def load_combined_dataset(
    config: str,
    output_dir: Path | str = "data/combined_datasets",
    add_signal_labels: bool = True,
) -> pd.DataFrame:
    """
    Load a previously created combined dataset with optimized labels for each target type.

    Parameters
    ----------
    config : str
        Configuration name (e.g., 'direction_1bar', 'volatility_regime_3bar')
    output_dir : Path or str
        Directory containing combined datasets
    add_signal_labels : bool
        Whether to add optimized signal labels based on target type:
        - direction_*: 3-class tristate (DOWN/UP/NEUTRAL) from triple barrier
        - returns_*: Regression - continuous target (no additional labels)
        - volatility_*: Regression - continuous target (no additional labels)
        - volatility_regime_*: Uses existing y_volatility_regime (binary DECREASE/INCREASE)
        - trend_regime_*: Uses existing y_trend_regime (already binary)

    Returns
    -------
    pd.DataFrame
        Combined dataset with appropriate labels for target type
    """
    output_dir = Path(output_dir)
    path = output_dir / f"{config}.parquet"

    if not path.exists():
        raise FileNotFoundError(
            f"Combined dataset not found: {path}\n"
            f"Run create_combined_dataset('{config}') first."
        )

    df = pd.read_parquet(path)

    if not add_signal_labels:
        return df

    # Import labeling utilities
    from scripts.analysis.signal_labels import (
        LabelingConfig,
        add_all_signal_labels,
        get_config_task_type,
        get_target_type_from_config,
    )

    target_type = get_target_type_from_config(config)
    task_type = get_config_task_type(config)

    # For direction targets: add 3-class tristate labels from triple barrier
    if target_type == "direction":
        # Need triple barrier columns for direction labeling
        if "y_tb_return" not in df.columns:
            logger.info("Loading triple barrier data for direction signal labels...")
            analysis_path = Path("data/analysis_8h.parquet")
            if analysis_path.exists() and "pred_idx" in df.columns:
                import polars as pl

                analysis_df = pl.read_parquet(analysis_path).to_pandas()
                pred_idx = df["pred_idx"].values.astype(int)

                # Extract TB columns at pred_idx
                tb_cols = ["y_tb_return", "y_tb_barrier", "y_tb_direction"]
                for col in tb_cols:
                    if col in analysis_df.columns:
                        df[col] = analysis_df.loc[pred_idx, col].values

        # Add signal labels if TB columns now exist
        if "y_tb_return" in df.columns and "y_tb_barrier" in df.columns:
            if "y_signal_3c" not in df.columns:
                label_config = LabelingConfig(
                    threshold_sigma=0.5,
                    min_threshold=0.005,
                    max_threshold=0.05,
                    vol_lookback=21,
                    use_triple_barrier=True,
                )
                df = add_all_signal_labels(df, label_config)
                logger.info(
                    "Added direction signal labels: y_signal_3c, y_signal_5c, y_signal_4c"
                )

    # For volatility_regime and trend_regime: labels already exist (y_volatility_regime, y_trend_regime)
    # For returns and volatility: regression targets, no additional labels needed

    logger.info(
        f"Loaded {config}: {task_type} task, target_type={target_type}, "
        f"rows={len(df)}, cols={len(df.columns)}"
    )

    return df


def get_feature_groups(df: pd.DataFrame) -> dict[str, list[str]]:
    """
    Categorize features into groups for analysis.

    Parameters
    ----------
    df : pd.DataFrame
        Combined dataset

    Returns
    -------
    dict
        Feature groups: raw_base, raw_interaction, helper, targets
    """
    cols = df.columns.tolist()

    return {
        "raw_base": [
            c
            for c in cols
            if not c.startswith("H_")
            and not c.startswith("y_")
            and c != "pred_idx"
            and "×" not in c
        ],
        "raw_interaction": [c for c in cols if "×" in c and not c.startswith("H_")],
        "helper": [c for c in cols if c.startswith("H_")],
        "targets": [c for c in cols if c.startswith("y_")],
        "meta": ["pred_idx"] if "pred_idx" in cols else [],
    }


def summarize_combined_datasets(
    output_dir: Path | str = "data/combined_datasets",
) -> pd.DataFrame:
    """
    Summarize all combined datasets.

    Returns
    -------
    pd.DataFrame
        Summary with rows, columns, feature counts per config
    """
    output_dir = Path(output_dir)

    if not output_dir.exists():
        raise FileNotFoundError(f"Combined datasets directory not found: {output_dir}")

    summaries = []

    for config in ALL_CONFIGS:
        path = output_dir / f"{config}.parquet"
        if path.exists():
            df = pd.read_parquet(path)
            groups = get_feature_groups(df)

            summaries.append(
                {
                    "config": config,
                    "rows": len(df),
                    "total_cols": len(df.columns),
                    "raw_base": len(groups["raw_base"]),
                    "raw_interaction": len(groups["raw_interaction"]),
                    "helper": len(groups["helper"]),
                    "targets": len(groups["targets"]),
                }
            )
        else:
            summaries.append(
                {
                    "config": config,
                    "rows": None,
                    "total_cols": None,
                    "raw_base": None,
                    "raw_interaction": None,
                    "helper": None,
                    "targets": None,
                }
            )

    return pd.DataFrame(summaries)


# ============================================================================
# PRED_IDX ALIGNMENT UTILITIES
# ============================================================================


def compute_common_pred_idx_range(
    configs: list[str] | None = None,
    output_dir: Path | str = "data/combined_datasets",
) -> dict[str, Any]:
    """
    Compute the common valid pred_idx range across all configs.

    Different configs have different start/end pred_idx due to:
    - Different interaction features with varying NaN patterns
    - Different target horizons

    This function finds the range where ALL configs have valid data,
    enabling synchronized walk-forward backtesting.

    Parameters
    ----------
    configs : list[str] or None
        List of configs to analyze. If None, uses all 16 configs.
    output_dir : Path or str
        Directory containing combined datasets

    Returns
    -------
    dict with keys:
        - common_start: First pred_idx valid for ALL configs
        - common_end: Last pred_idx valid for ALL configs
        - common_length: Number of pred_idx values in common range
        - config_ranges: Dict mapping config -> {start, end, rows}
        - config_row_mappings: Dict mapping config -> {pred_idx -> row_idx}
    """
    output_dir = Path(output_dir)
    configs_list = configs or ALL_CONFIGS

    config_ranges = {}
    all_pred_idx_sets = []

    for config in configs_list:
        path = output_dir / f"{config}.parquet"
        if not path.exists():
            logger.warning(f"Config {config} not found, skipping")
            continue

        df = pd.read_parquet(path)
        if "pred_idx" not in df.columns:
            logger.warning(f"Config {config} has no pred_idx, skipping")
            continue

        pred_idx = df["pred_idx"].values.astype(int)
        config_ranges[config] = {
            "start": int(pred_idx.min()),
            "end": int(pred_idx.max()),
            "rows": len(pred_idx),
            "pred_idx": pred_idx,
        }
        all_pred_idx_sets.append(set(pred_idx))

    if not config_ranges:
        raise ValueError("No valid configs found")

    # Find common pred_idx range (intersection of all configs)
    common_pred_idx = set.intersection(*all_pred_idx_sets)
    common_start = min(common_pred_idx)
    common_end = max(common_pred_idx)
    common_length = len(common_pred_idx)

    # Verify the common range is contiguous
    expected_length = common_end - common_start + 1
    if common_length != expected_length:
        logger.warning(
            f"Common pred_idx range has gaps: {common_length} values "
            f"in range {common_start}-{common_end} (expected {expected_length})"
        )

    # Build row index mappings for each config (pred_idx -> row_idx)
    config_row_mappings = {}
    for config, info in config_ranges.items():
        pred_idx = info["pred_idx"]
        # Create mapping: pred_idx value -> row index in this config's dataframe
        mapping = {int(p): i for i, p in enumerate(pred_idx)}
        config_row_mappings[config] = mapping

    logger.info(
        f"Common pred_idx range: {common_start} to {common_end} "
        f"({common_length} values)"
    )

    return {
        "common_start": common_start,
        "common_end": common_end,
        "common_length": common_length,
        "config_ranges": {
            k: {"start": v["start"], "end": v["end"], "rows": v["rows"]}
            for k, v in config_ranges.items()
        },
        "config_row_mappings": config_row_mappings,
    }


def load_combined_dataset_aligned(
    config: str,
    common_range: dict[str, Any] | None = None,
    output_dir: Path | str = "data/combined_datasets",
    add_signal_labels: bool = True,
) -> pd.DataFrame:
    """
    Load a combined dataset filtered to the common pred_idx range.

    This ensures all configs have the same length and aligned pred_idx values,
    enabling synchronized walk-forward backtesting.

    Parameters
    ----------
    config : str
        Configuration name (e.g., 'direction_1bar')
    common_range : dict or None
        Result from compute_common_pred_idx_range(). If None, computes it.
    output_dir : Path or str
        Directory containing combined datasets
    add_signal_labels : bool
        Whether to add signal labels (see load_combined_dataset)

    Returns
    -------
    pd.DataFrame
        Combined dataset filtered to common pred_idx range
    """
    # Load full dataset
    df = load_combined_dataset(config, output_dir, add_signal_labels)

    # Compute common range if not provided
    if common_range is None:
        common_range = compute_common_pred_idx_range(output_dir=output_dir)

    common_start = common_range["common_start"]
    common_end = common_range["common_end"]

    # Filter to common range
    mask = (df["pred_idx"] >= common_start) & (df["pred_idx"] <= common_end)
    df_aligned = df[mask].reset_index(drop=True)

    logger.info(
        f"Loaded {config} aligned: {len(df)} -> {len(df_aligned)} rows "
        f"(pred_idx {common_start}-{common_end})"
    )

    return df_aligned


if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    print("=" * 80)
    print("CREATING COMBINED DATASETS (All Features)")
    print("=" * 80)

    # Allow specifying configs on command line
    if len(sys.argv) > 1:
        configs = sys.argv[1:]
    else:
        configs = None  # All configs

    results = create_all_combined_datasets(configs=configs, verbose=True)

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    success = sum(1 for r in results.values() if r["status"] == "success")
    failed = sum(1 for r in results.values() if r["status"] == "error")

    print(f"✅ Success: {success}/{len(results)}")
    if failed:
        print(f"❌ Failed: {failed}")
        for config, r in results.items():
            if r["status"] == "error":
                print(f"   - {config}: {r['error']}")
