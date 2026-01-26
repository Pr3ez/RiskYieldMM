"""
Pipeline state detection for the RiskYieldMM ML pipeline.

Detects when new data has been fetched and downstream files need recomputation.
"""

from dataclasses import dataclass
from pathlib import Path

import polars as pl

from scripts.analysis.pipeline_state import PipelineState


@dataclass
class DataStatus:
    """Status of pipeline data files."""

    raw_rows: int
    raw_timestamp: str | None
    merged_rows: int
    features_rows: int
    analysis_rows: int
    new_data_detected: bool
    new_rows: int
    sync_reason: str | None


def get_data_status(project_root: Path) -> DataStatus:
    """
    Get the current status of all pipeline data files.

    Args:
        project_root: Path to the project root directory

    Returns:
        DataStatus with information about all data files
    """
    # Check raw 8h data
    raw_8h_file = (
        project_root / "fetchingByBit" / "sorted-8h-bybit-linear" / "btcusdt_8h.parquet"
    )
    if raw_8h_file.exists():
        raw_df = pl.read_parquet(raw_8h_file)
        raw_rows = len(raw_df)
        raw_timestamp = str(raw_df.select("timestamp").max().item())
    else:
        raw_rows = 0
        raw_timestamp = None

    # Check downstream files
    merged_file = project_root / "data" / "merged_8h_raw.parquet"
    merged_rows = len(pl.read_parquet(merged_file)) if merged_file.exists() else 0

    features_file = project_root / "data" / "features_8h.parquet"
    features_rows = len(pl.read_parquet(features_file)) if features_file.exists() else 0

    analysis_file = project_root / "data" / "analysis_8h.parquet"
    analysis_rows = len(pl.read_parquet(analysis_file)) if analysis_file.exists() else 0

    # Detect if new data / sync needed
    new_data_detected = False
    new_rows = 0
    sync_reason = None

    if raw_rows == 0:
        new_data_detected = True
        sync_reason = "Raw 8h data not found"
    elif merged_rows == 0:
        new_data_detected = True
        sync_reason = "Merged file missing"
    elif merged_rows != raw_rows:
        new_data_detected = True
        new_rows = raw_rows - merged_rows
        sync_reason = f"Row mismatch: merged={merged_rows}, raw={raw_rows}"
    elif features_rows != raw_rows:
        new_data_detected = True
        new_rows = raw_rows - features_rows
        sync_reason = f"Row mismatch: features={features_rows}, raw={raw_rows}"
    elif analysis_rows != raw_rows:
        new_data_detected = True
        new_rows = raw_rows - analysis_rows
        sync_reason = f"Row mismatch: analysis={analysis_rows}, raw={raw_rows}"

    return DataStatus(
        raw_rows=raw_rows,
        raw_timestamp=raw_timestamp,
        merged_rows=merged_rows,
        features_rows=features_rows,
        analysis_rows=analysis_rows,
        new_data_detected=new_data_detected,
        new_rows=new_rows,
        sync_reason=sync_reason,
    )


def detect_new_data(
    project_root: Path,
    pipeline_state: PipelineState | None = None,
    verbose: bool = True,
) -> tuple[bool, int]:
    """
    Detect if new data has been fetched and downstream files need recomputation.

    Args:
        project_root: Path to the project root directory
        pipeline_state: Optional existing PipelineState (loads if not provided)
        verbose: Whether to print status messages

    Returns:
        Tuple of (new_data_detected, current_raw_rows)
    """
    if pipeline_state is None:
        pipeline_state = PipelineState.load(project_root)

    status = get_data_status(project_root)

    if verbose:
        if status.new_data_detected:
            if status.new_rows > 0:
                print(f"\n🔄 NEW DATA DETECTED: {status.new_rows} new 8h bars")
            else:
                print(f"\n🔄 DATA SYNC REQUIRED: {status.sync_reason}")
            print("   All downstream steps will be recomputed to ensure consistency")
        else:
            print("\n✓ Data is in sync - can skip unchanged steps")

    # Update pipeline state with current raw info
    if status.raw_rows > 0:
        pipeline_state.update_step(
            "raw_8h",
            row_count=status.raw_rows,
            last_timestamp=status.raw_timestamp,
        )

    return status.new_data_detected, status.raw_rows


def check_file_sync(
    project_root: Path,
    file_name: str,
    expected_rows: int,
    verbose: bool = True,
) -> tuple[bool, int]:
    """
    Check if a specific file is in sync with expected row count.

    Args:
        project_root: Path to the project root directory
        file_name: Name of the file to check (in data/ directory)
        expected_rows: Expected number of rows
        verbose: Whether to print status messages

    Returns:
        Tuple of (is_current, current_rows)
    """
    file_path = project_root / "data" / file_name
    if not file_path.exists():
        if verbose:
            print(f"⚠️ {file_name} not found - needs computation")
        return False, 0

    df = pl.read_parquet(file_path)
    current_rows = len(df)

    if current_rows == expected_rows:
        if verbose:
            print(f"✓ {file_name} is current ({current_rows} rows)")
        return True, current_rows
    else:
        if verbose:
            print(f"⚠️ {file_name}: row mismatch ({current_rows} vs {expected_rows})")
        return False, current_rows


def check_optimized_files(
    project_root: Path,
    targets: list[str],
    horizons: list[int],
    expected_rows: int,
    verbose: bool = True,
) -> bool:
    """
    Check if all optimized feature files exist and have correct row counts.

    Args:
        project_root: Path to the project root directory
        targets: List of target types
        horizons: List of horizons
        expected_rows: Expected number of rows
        verbose: Whether to print status messages

    Returns:
        True if all files exist and are current
    """
    all_exist = True
    for target in targets:
        for horizon in horizons:
            opt_file = (
                project_root
                / "data"
                / f"features_8h_optimized_{target}_{horizon}bar.parquet"
            )
            if not opt_file.exists():
                if verbose:
                    print(f"⚠️ Missing: {opt_file.name}")
                all_exist = False
                continue

            opt_df = pl.read_parquet(opt_file)
            if len(opt_df) != expected_rows:
                if verbose:
                    print(
                        f"⚠️ {opt_file.name}: row mismatch ({len(opt_df)} vs {expected_rows})"
                    )
                all_exist = False

    if all_exist and verbose:
        print("✓ All optimized files exist and are current")

    return all_exist
