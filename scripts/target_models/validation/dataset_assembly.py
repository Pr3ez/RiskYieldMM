"""
Dataset Assembly Module

Assembles continuous prediction datasets from precomputed L1 iterations.
Each assembled.parquet contains one row per walk-forward iteration (the prediction row).

Usage:
    from scripts.target_models.validation.dataset_assembly import (
        assemble_config,
        assemble_all,
        update_assembled,
        update_all,
        check_assembly_status,
        validate_assembled,
    )

    # Assemble single config (full rebuild)
    df = assemble_config("direction_1bar")

    # Assemble all 20 configs (full rebuild)
    results = assemble_all()

    # Check if updates needed
    status = check_assembly_status("direction_1bar")
    print(f"Missing: {status.missing_rows} rows")

    # Incremental update (only new iterations)
    result = update_assembled("direction_1bar")
    print(f"Added: {result.n_new_rows} new rows")

    # Update all configs incrementally
    results = update_all()  # Only processes configs with new iterations

    # Validate assembled dataset
    is_valid, report = validate_assembled("direction_1bar")
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

# Centralized config generation (Single Source of Truth)
# DO NOT HARDCODE CONFIG LISTS - add new targets to config.py → WORKFLOW_TARGETS
from scripts.workflow.config import get_all_configs

# All configs (WORKFLOW_TARGETS × ALL_HORIZONS)
# Auto-generated from config.py - DO NOT HARDCODE
ALL_CONFIGS = get_all_configs()


@dataclass
class AssemblyResult:
    """Result of assembling a config's dataset."""

    config_name: str
    n_rows: int
    n_features: int
    first_timestamp: str
    last_timestamp: str
    elapsed_sec: float
    output_path: str
    n_new_rows: int = 0  # For incremental updates


@dataclass
class AssemblyStatus:
    """Status of assembled dataset vs available iterations."""

    config_name: str
    assembled_rows: int
    available_rows: int
    missing_rows: int
    needs_update: bool
    last_assembled_timestamp: str | None
    last_available_timestamp: str | None


def _parse_timestamp_from_filename(filename: str) -> pd.Timestamp:
    """
    Parse timestamp from filename like '2022-10-27_16h.parquet'.

    Returns timezone-aware UTC timestamp.
    """
    # filename: YYYY-MM-DD_HHh.parquet
    stem = filename.replace(".parquet", "")  # 2022-10-27_16h
    date_part, hour_part = stem.split("_")  # 2022-10-27, 16h
    hour = hour_part.replace("h", "")  # 16
    ts_str = f"{date_part}T{hour}:00:00+00:00"
    return pd.Timestamp(ts_str)


def assemble_config(
    config_name: str,
    precomputed_dir: Path | str | None = None,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Assemble a continuous dataset from precomputed L1 iterations.

    Extracts the last row (prediction row) from each parquet file,
    sorts chronologically, and returns a single DataFrame indexed by timestamp.

    Args:
        config_name: Configuration name (e.g., "direction_1bar")
        precomputed_dir: Path to precomputed directory (default: data/precomputed)
        verbose: Print progress messages

    Returns:
        DataFrame with shape (n_iterations, n_features + 1)
        - Index: timestamp (timezone-aware UTC)
        - Columns: 91 helper features + 'pred_idx'
    """
    if precomputed_dir is None:
        precomputed_dir = Path("data/precomputed")
    precomputed_dir = Path(precomputed_dir)

    config_dir = precomputed_dir / config_name
    if not config_dir.exists():
        raise FileNotFoundError(f"Config directory not found: {config_dir}")

    # Load index.json for pred_idx mapping
    index_path = config_dir / "index.json"
    if not index_path.exists():
        raise FileNotFoundError(f"index.json not found: {index_path}")

    with open(index_path) as f:
        index_data = json.load(f)

    # Create filename -> pred_idx mapping
    filename_to_pred_idx = {
        entry["filename"]: entry["pred_idx"] for entry in index_data
    }

    # Get sorted parquet files (alphabetical = chronological for YYYY-MM-DD_HHh format)
    # Exclude assembled.parquet (output file)
    parquet_files = sorted(
        f for f in config_dir.glob("*.parquet") if f.name != "assembled.parquet"
    )

    if len(parquet_files) == 0:
        raise ValueError(f"No parquet files found in {config_dir}")

    if verbose:
        print(f"  Assembling {config_name}: {len(parquet_files)} files...")

    # Extract prediction rows
    rows = []
    timestamps = []
    pred_idxs = []

    for pq_file in parquet_files:
        # Load parquet and extract last row
        df = pd.read_parquet(pq_file)
        pred_row = df.iloc[-1].to_dict()

        # Parse timestamp from filename
        ts = _parse_timestamp_from_filename(pq_file.name)

        # Get pred_idx from index.json
        pred_idx = filename_to_pred_idx.get(pq_file.name)

        rows.append(pred_row)
        timestamps.append(ts)
        pred_idxs.append(pred_idx)

    # Build DataFrame
    assembled = pd.DataFrame(rows)
    assembled["timestamp"] = timestamps
    assembled["pred_idx"] = pred_idxs
    assembled = assembled.set_index("timestamp").sort_index()

    # Reorder columns: put pred_idx first, then all helper features
    cols = ["pred_idx"] + [c for c in assembled.columns if c != "pred_idx"]
    assembled = assembled[cols]

    # Save to assembled.parquet
    output_path = config_dir / "assembled.parquet"
    assembled.to_parquet(output_path)

    if verbose:
        print(
            f"    ✓ {len(assembled)} rows × {len(assembled.columns)} cols → {output_path.name}"
        )

    return assembled


def check_assembly_status(
    config_name: str,
    precomputed_dir: Path | str | None = None,
) -> AssemblyStatus:
    """
    Check if assembled dataset needs updating (new iterations available).

    Args:
        config_name: Configuration name
        precomputed_dir: Path to precomputed directory

    Returns:
        AssemblyStatus with comparison of assembled vs available rows
    """
    if precomputed_dir is None:
        precomputed_dir = Path("data/precomputed")
    precomputed_dir = Path(precomputed_dir)

    config_dir = precomputed_dir / config_name
    assembled_path = config_dir / "assembled.parquet"

    # Count available iteration files (exclude assembled.parquet)
    parquet_files = [
        f for f in config_dir.glob("*.parquet") if f.name != "assembled.parquet"
    ]
    available_rows = len(parquet_files)

    # Get last available timestamp from sorted filenames
    if parquet_files:
        last_file = sorted(parquet_files)[-1]
        last_available_ts = str(_parse_timestamp_from_filename(last_file.name))
    else:
        last_available_ts = None

    # Check assembled dataset
    if assembled_path.exists():
        df = pd.read_parquet(assembled_path)
        assembled_rows = len(df)
        last_assembled_ts = str(df.index.max()) if len(df) > 0 else None
    else:
        assembled_rows = 0
        last_assembled_ts = None

    missing_rows = available_rows - assembled_rows
    needs_update = missing_rows > 0

    return AssemblyStatus(
        config_name=config_name,
        assembled_rows=assembled_rows,
        available_rows=available_rows,
        missing_rows=missing_rows,
        needs_update=needs_update,
        last_assembled_timestamp=last_assembled_ts,
        last_available_timestamp=last_available_ts,
    )


def update_assembled(
    config_name: str,
    precomputed_dir: Path | str | None = None,
    verbose: bool = True,
) -> AssemblyResult:
    """
    Incrementally update assembled dataset with new iterations.

    Only processes new parquet files that aren't already in assembled.parquet.
    Much faster than full reassembly when only a few new iterations exist.

    Args:
        config_name: Configuration name
        precomputed_dir: Path to precomputed directory
        verbose: Print progress

    Returns:
        AssemblyResult with n_new_rows indicating how many were added
    """
    if precomputed_dir is None:
        precomputed_dir = Path("data/precomputed")
    precomputed_dir = Path(precomputed_dir)

    config_dir = precomputed_dir / config_name
    assembled_path = config_dir / "assembled.parquet"
    index_path = config_dir / "index.json"

    t0 = time.time()

    # Load index.json for pred_idx mapping
    with open(index_path) as f:
        index_data = json.load(f)
    filename_to_pred_idx = {
        entry["filename"]: entry["pred_idx"] for entry in index_data
    }

    # Get all available parquet files
    all_parquet_files = sorted(
        f for f in config_dir.glob("*.parquet") if f.name != "assembled.parquet"
    )

    # Load existing assembled if exists
    if assembled_path.exists():
        existing_df = pd.read_parquet(assembled_path)
        existing_timestamps = set(existing_df.index)
        if verbose:
            print(f"  {config_name}: {len(existing_df)} existing rows")
    else:
        existing_df = None
        existing_timestamps = set()
        if verbose:
            print(f"  {config_name}: No existing assembled dataset")

    # Find new files (not already assembled)
    new_files = []
    for pq_file in all_parquet_files:
        ts = _parse_timestamp_from_filename(pq_file.name)
        if ts not in existing_timestamps:
            new_files.append(pq_file)

    if len(new_files) == 0:
        if verbose:
            print("    ⏭️  No new iterations to add")
        elapsed = time.time() - t0
        return AssemblyResult(
            config_name=config_name,
            n_rows=len(existing_df) if existing_df is not None else 0,
            n_features=len(existing_df.columns) - 1 if existing_df is not None else 0,
            first_timestamp=str(existing_df.index.min())
            if existing_df is not None
            else "",
            last_timestamp=str(existing_df.index.max())
            if existing_df is not None
            else "",
            elapsed_sec=round(elapsed, 2),
            output_path=str(assembled_path),
            n_new_rows=0,
        )

    if verbose:
        print(f"    Adding {len(new_files)} new iterations...")

    # Extract prediction rows from new files
    new_rows = []
    new_timestamps = []
    new_pred_idxs = []

    for pq_file in new_files:
        df = pd.read_parquet(pq_file)
        pred_row = df.iloc[-1].to_dict()
        ts = _parse_timestamp_from_filename(pq_file.name)
        pred_idx = filename_to_pred_idx.get(pq_file.name)

        new_rows.append(pred_row)
        new_timestamps.append(ts)
        new_pred_idxs.append(pred_idx)

    # Build new rows DataFrame
    new_df = pd.DataFrame(new_rows)
    new_df["timestamp"] = new_timestamps
    new_df["pred_idx"] = new_pred_idxs
    new_df = new_df.set_index("timestamp")

    # Combine with existing
    if existing_df is not None:
        combined = pd.concat([existing_df, new_df]).sort_index()
    else:
        combined = new_df.sort_index()

    # Reorder columns
    cols = ["pred_idx"] + [c for c in combined.columns if c != "pred_idx"]
    combined = combined[cols]

    # Save updated assembled
    combined.to_parquet(assembled_path)

    elapsed = time.time() - t0

    if verbose:
        print(
            f"    ✓ {len(combined)} rows total (+{len(new_files)} new) in {elapsed:.1f}s"
        )

    return AssemblyResult(
        config_name=config_name,
        n_rows=len(combined),
        n_features=len(combined.columns) - 1,
        first_timestamp=str(combined.index.min()),
        last_timestamp=str(combined.index.max()),
        elapsed_sec=round(elapsed, 2),
        output_path=str(assembled_path),
        n_new_rows=len(new_files),
    )


def update_all(
    precomputed_dir: Path | str | None = None,
    configs: list[str] | None = None,
    verbose: bool = True,
) -> list[AssemblyResult]:
    """
    Incrementally update all assembled datasets with new iterations.

    Only processes configs that have new iterations available.

    Args:
        precomputed_dir: Path to precomputed directory
        configs: List of config names (default: all 20)
        verbose: Print progress

    Returns:
        List of AssemblyResult for each updated config
    """
    if precomputed_dir is None:
        precomputed_dir = Path("data/precomputed")
    precomputed_dir = Path(precomputed_dir)

    if configs is None:
        configs = ALL_CONFIGS

    results = []
    total_t0 = time.time()

    if verbose:
        print("=" * 60)
        print("CHECKING FOR NEW ITERATIONS")
        print("=" * 60)

    # Check status of all configs
    configs_to_update = []
    for config_name in configs:
        status = check_assembly_status(config_name, precomputed_dir)
        if status.needs_update:
            configs_to_update.append((config_name, status))
            if verbose:
                print(f"  🔄 {config_name}: +{status.missing_rows} new iterations")
        else:
            if verbose:
                print(f"  ✓ {config_name}: up to date ({status.assembled_rows} rows)")

    if len(configs_to_update) == 0:
        if verbose:
            print("\n✓ All configs are up to date. Nothing to do.")
        return results

    if verbose:
        print(f"\n{len(configs_to_update)} configs need updating...")
        print()

    # Update configs with new iterations
    for config_name, status in configs_to_update:
        result = update_assembled(config_name, precomputed_dir, verbose=verbose)
        results.append(result)

    total_elapsed = time.time() - total_t0

    if verbose:
        total_new = sum(r.n_new_rows for r in results)
        print()
        print("=" * 60)
        print("UPDATE COMPLETE")
        print("=" * 60)
        print(f"  Configs updated: {len(results)}")
        print(f"  Total new rows: {total_new}")
        print(f"  Time: {total_elapsed:.1f}s")

    return results


def assemble_all(
    precomputed_dir: Path | str | None = None,
    configs: list[str] | None = None,
    verbose: bool = True,
) -> list[AssemblyResult]:
    """
    Assemble all (or specified) config datasets.

    Args:
        precomputed_dir: Path to precomputed directory
        configs: List of config names (default: all 20)
        verbose: Print progress

    Returns:
        List of AssemblyResult for each config
    """
    if precomputed_dir is None:
        precomputed_dir = Path("data/precomputed")
    precomputed_dir = Path(precomputed_dir)

    if configs is None:
        configs = ALL_CONFIGS

    results = []
    total_t0 = time.time()

    if verbose:
        print("=" * 60)
        print("ASSEMBLING PREDICTION DATASETS")
        print("=" * 60)
        print(f"  Configs: {len(configs)}")
        print("  Output: assembled.parquet per config")
        print()

    for i, config_name in enumerate(configs, start=1):
        if verbose:
            print(f"[{i}/{len(configs)}] {config_name}")

        t0 = time.time()

        try:
            df = assemble_config(config_name, precomputed_dir, verbose=verbose)
            elapsed = time.time() - t0

            result = AssemblyResult(
                config_name=config_name,
                n_rows=len(df),
                n_features=len(df.columns) - 1,  # -1 for pred_idx
                first_timestamp=str(df.index.min()),
                last_timestamp=str(df.index.max()),
                elapsed_sec=round(elapsed, 2),
                output_path=str(precomputed_dir / config_name / "assembled.parquet"),
            )
            results.append(result)

        except Exception as e:
            if verbose:
                print(f"    ✗ ERROR: {e}")
            continue

    total_elapsed = time.time() - total_t0

    if verbose:
        print()
        print("=" * 60)
        print("ASSEMBLY COMPLETE")
        print("=" * 60)
        total_rows = sum(r.n_rows for r in results)
        print(f"  Configs assembled: {len(results)}/{len(configs)}")
        print(f"  Total prediction rows: {total_rows:,}")
        print(f"  Time: {total_elapsed:.1f}s")

    return results


def validate_assembled(
    config_name: str,
    precomputed_dir: Path | str | None = None,
) -> tuple[bool, dict[str, Any]]:
    """
    Validate an assembled dataset.

    Checks:
    1. Row count matches index.json length
    2. No duplicate timestamps
    3. Timestamp range matches metadata.json
    4. No NaN or Inf values in features
    5. pred_idx values are valid (positive integers)

    Args:
        config_name: Configuration name
        precomputed_dir: Path to precomputed directory

    Returns:
        (is_valid, report_dict)
    """
    if precomputed_dir is None:
        precomputed_dir = Path("data/precomputed")
    precomputed_dir = Path(precomputed_dir)

    config_dir = precomputed_dir / config_name
    assembled_path = config_dir / "assembled.parquet"
    index_path = config_dir / "index.json"
    metadata_path = config_dir / "metadata.json"

    report = {
        "config_name": config_name,
        "checks": {},
        "errors": [],
        "n_rows": 0,  # Default to 0 for early returns
        "n_features": 0,
        "is_valid": False,
    }

    # Check assembled.parquet exists
    if not assembled_path.exists():
        report["errors"].append(f"assembled.parquet not found: {assembled_path}")
        return False, report

    # Load data
    df = pd.read_parquet(assembled_path)

    with open(index_path) as f:
        index_data = json.load(f)

    with open(metadata_path) as f:
        metadata = json.load(f)

    # Check 1: Row count matches index.json
    expected_rows = len(index_data)
    actual_rows = len(df)
    check_rows = actual_rows == expected_rows
    report["checks"]["row_count"] = {
        "passed": check_rows,
        "expected": expected_rows,
        "actual": actual_rows,
    }
    if not check_rows:
        report["errors"].append(f"Row count mismatch: {actual_rows} vs {expected_rows}")

    # Check 2: No duplicate timestamps
    n_duplicates = df.index.duplicated().sum()
    check_dups = n_duplicates == 0
    report["checks"]["no_duplicates"] = {
        "passed": check_dups,
        "n_duplicates": int(n_duplicates),
    }
    if not check_dups:
        report["errors"].append(f"Found {n_duplicates} duplicate timestamps")

    # Check 3: Timestamp range matches metadata
    # Normalize: metadata uses 'T', pandas str uses ' '
    meta_first = metadata.get("first_pred_timestamp", "")[:19].replace("T", " ")
    meta_last = metadata.get("last_pred_timestamp", "")[:19].replace("T", " ")
    actual_first = str(df.index.min())[:19]
    actual_last = str(df.index.max())[:19]
    check_range = (actual_first == meta_first) and (actual_last == meta_last)
    report["checks"]["timestamp_range"] = {
        "passed": check_range,
        "expected_first": meta_first,
        "actual_first": actual_first,
        "expected_last": meta_last,
        "actual_last": actual_last,
    }
    if not check_range:
        report["errors"].append("Timestamp range mismatch")

    # Check 4: No NaN or Inf in features
    feature_cols = [c for c in df.columns if c != "pred_idx"]
    n_nan = df[feature_cols].isna().sum().sum()
    has_inf = any(
        (df[feature_cols] == float("inf")).any()
        | (df[feature_cols] == float("-inf")).any()
    )
    check_values = n_nan == 0 and not has_inf
    report["checks"]["no_nan_inf"] = {
        "passed": check_values,
        "n_nan": int(n_nan),
        "has_inf": has_inf,
    }
    if not check_values:
        report["errors"].append(f"Found NaN ({n_nan}) or Inf values")

    # Check 5: pred_idx values valid
    pred_idx_valid = (df["pred_idx"] >= 0).all() and df["pred_idx"].notna().all()
    report["checks"]["pred_idx_valid"] = {
        "passed": bool(pred_idx_valid),
        "min": int(df["pred_idx"].min()) if df["pred_idx"].notna().any() else None,
        "max": int(df["pred_idx"].max()) if df["pred_idx"].notna().any() else None,
    }
    if not pred_idx_valid:
        report["errors"].append("Invalid pred_idx values")

    # Overall result
    is_valid = len(report["errors"]) == 0
    report["is_valid"] = is_valid
    report["n_rows"] = actual_rows
    report["n_features"] = len(feature_cols)

    return is_valid, report


def validate_all(
    precomputed_dir: Path | str | None = None,
    configs: list[str] | None = None,
    verbose: bool = True,
) -> tuple[bool, list[dict[str, Any]]]:
    """
    Validate all assembled datasets.

    Returns:
        (all_valid, list_of_reports)
    """
    if precomputed_dir is None:
        precomputed_dir = Path("data/precomputed")
    precomputed_dir = Path(precomputed_dir)

    if configs is None:
        configs = ALL_CONFIGS

    reports = []
    all_valid = True

    if verbose:
        print("=" * 60)
        print("VALIDATING ASSEMBLED DATASETS")
        print("=" * 60)

    for config_name in configs:
        is_valid, report = validate_assembled(config_name, precomputed_dir)
        reports.append(report)

        if verbose:
            status = "✓" if is_valid else "✗"
            print(f"  {status} {config_name}: {report['n_rows']} rows")
            if not is_valid:
                for err in report["errors"]:
                    print(f"      {err}")

        if not is_valid:
            all_valid = False

    if verbose:
        print()
        valid_count = sum(1 for r in reports if r.get("is_valid", False))
        print(f"Result: {valid_count}/{len(configs)} configs valid")

    return all_valid, reports


def load_assembled(
    config_name: str,
    precomputed_dir: Path | str | None = None,
) -> pd.DataFrame:
    """
    Load an assembled prediction dataset.

    Args:
        config_name: Configuration name (e.g., "direction_1bar")
        precomputed_dir: Path to precomputed directory

    Returns:
        DataFrame indexed by timestamp with pred_idx and helper features
    """
    if precomputed_dir is None:
        precomputed_dir = Path("data/precomputed")
    precomputed_dir = Path(precomputed_dir)

    assembled_path = precomputed_dir / config_name / "assembled.parquet"

    if not assembled_path.exists():
        raise FileNotFoundError(
            f"Assembled dataset not found: {assembled_path}\n"
            f"Run assemble_config('{config_name}') first."
        )

    return pd.read_parquet(assembled_path)


# CLI support
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Assemble prediction datasets")
    parser.add_argument("--config", type=str, help="Single config to assemble")
    parser.add_argument(
        "--validate", action="store_true", help="Validate after assembly"
    )
    parser.add_argument(
        "--validate-only", action="store_true", help="Only validate, don't assemble"
    )
    args = parser.parse_args()

    if args.validate_only:
        if args.config:
            is_valid, report = validate_assembled(args.config)
            print(json.dumps(report, indent=2))
        else:
            validate_all()
    else:
        if args.config:
            df = assemble_config(args.config)
            if args.validate:
                validate_assembled(args.config)
        else:
            assemble_all()
            if args.validate:
                validate_all()
