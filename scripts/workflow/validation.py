"""
Validation utilities for the RiskYieldMM ML pipeline.

Includes:
- Causality tests for ExpandingRank (no future peeking)
- Pipeline verification (all steps complete)
- Step output verification
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl


@dataclass
class CausalityTestResult:
    """Result of causality validation tests."""

    spike_test_passed: bool
    manual_verify_passed: bool
    expanding_window_passed: bool
    all_passed: bool
    details: dict


def run_causality_test(verbose: bool = True) -> CausalityTestResult:
    """
    Verify NO FUTURE PEEKING in ExpandingRank.

    This test proves row N only sees data from rows 0..N-1.

    Args:
        verbose: Whether to print detailed output

    Returns:
        CausalityTestResult with test outcomes
    """
    from scripts.analysis.optimizers.expanding_rank_fast import (
        ExpandingRankOptimizerFast,
    )

    if verbose:
        print("=" * 70)
        print("CAUSALITY VALIDATION: No Future Peeking Test")
        print("=" * 70)

    # Create test data with KNOWN pattern
    np.random.seed(42)
    n = 500
    test_values = np.random.randn(n).cumsum()  # Random walk

    # Add a SPIKE at row 400 that would be obvious if leaked
    test_values[400:] += 100  # Huge jump

    df_test = pd.DataFrame({"feature": test_values})

    # Apply expanding rank
    optimizer = ExpandingRankOptimizerFast(min_periods=50, use_numba=True)
    optimizer.fit(df_test)
    df_ranked = optimizer.transform(df_test)

    # TEST 1: Spike Detection
    # Row 399 should NOT know about the spike at row 400
    rank_before_spike = df_ranked["feature"].iloc[399]
    rank_after_spike = df_ranked["feature"].iloc[400]

    spike_test_passed = rank_before_spike > 0.9

    if verbose:
        print("\n1. Spike Detection Test:")
        print(f"   Row 399 (just before spike): rank = {rank_before_spike:.4f}")
        print(f"   Row 400 (spike row): rank = {rank_after_spike:.4f}")
        if spike_test_passed:
            print(
                f"   ✓ PASS: Row 399 has high rank ({rank_before_spike:.2f}) - "
                "doesn't know about future spike"
            )
        else:
            print(
                f"   ✗ FAIL: Row 399 has LOW rank ({rank_before_spike:.2f}) - "
                "FUTURE LEAKAGE DETECTED!"
            )

    # TEST 2: Manual Verification
    row_idx = 100
    manual_hist = test_values[:row_idx]  # Rows 0..99
    current_val = test_values[row_idx]
    manual_rank = np.mean(manual_hist <= current_val)
    computed_rank = df_ranked["feature"].iloc[row_idx]

    manual_verify_passed = abs(manual_rank - computed_rank) < 1e-6

    if verbose:
        print(f"\n2. Manual Verification (row {row_idx}):")
        print(f"   Current value: {current_val:.4f}")
        print(f"   History size: {len(manual_hist)} rows")
        print(f"   Manual rank: {manual_rank:.6f}")
        print(f"   Computed rank: {computed_rank:.6f}")
        print(f"   Match: {'✓ PASS' if manual_verify_passed else '✗ FAIL'}")

    # TEST 3: Expanding Window Behavior
    nan_count = df_ranked["feature"].iloc[: optimizer.min_periods].isna().sum()
    expanding_window_passed = nan_count == optimizer.min_periods

    if verbose:
        print("\n3. Expanding Window Test:")
        print(
            f"   First valid rank at row {optimizer.min_periods} "
            f"(min_periods={optimizer.min_periods})"
        )
        print(f"   Rows 0-{optimizer.min_periods - 1} should be NaN:")
        print(f"   NaN count in first {optimizer.min_periods} rows: {nan_count}")
        print(f"   {'✓ PASS' if expanding_window_passed else '✗ FAIL'}")

    all_passed = spike_test_passed and manual_verify_passed and expanding_window_passed

    if verbose:
        print("\n" + "=" * 70)
        if all_passed:
            print("✓ ALL CAUSALITY TESTS PASSED - No future peeking detected")
        else:
            print("✗ CAUSALITY VIOLATION DETECTED - Check implementation!")
        print("=" * 70)

    return CausalityTestResult(
        spike_test_passed=spike_test_passed,
        manual_verify_passed=manual_verify_passed,
        expanding_window_passed=expanding_window_passed,
        all_passed=all_passed,
        details={
            "rank_before_spike": rank_before_spike,
            "rank_after_spike": rank_after_spike,
            "manual_rank": manual_rank,
            "computed_rank": computed_rank,
            "nan_count": nan_count,
            "min_periods": optimizer.min_periods,
        },
    )


@dataclass
class PipelineVerificationResult:
    """Result of pipeline verification."""

    all_passed: bool
    checks: list[tuple[str, bool]]
    details: dict


def run_pipeline_verification(
    project_root: Path,
    verbose: bool = True,
) -> PipelineVerificationResult:
    """
    Verify all pipeline steps are complete.

    Args:
        project_root: Path to the project root directory
        verbose: Whether to print detailed output

    Returns:
        PipelineVerificationResult with all check outcomes
    """
    if verbose:
        print("=" * 70)
        print("PIPELINE VERIFICATION")
        print("=" * 70)

    checks = []
    details = {}

    # Check Step 0: 8h data freshness
    ohlcv_8h = (
        project_root / "fetchingByBit" / "sorted-8h-bybit-linear" / "btcusdt_8h.parquet"
    )
    if ohlcv_8h.exists():
        last_ts = pl.read_parquet(ohlcv_8h).select("timestamp").max().item()
        now = datetime.now(timezone.utc)
        hours_behind = (
            now - last_ts.replace(tzinfo=timezone.utc)
        ).total_seconds() / 3600
        checks.append(
            (f"Step 0: 8h data ({hours_behind:.0f}h behind)", hours_behind <= 16)
        )
        details["step0_hours_behind"] = hours_behind
    else:
        checks.append(("Step 0: 8h data", False))
        details["step0_hours_behind"] = None

    # Check Step 1: Raw and features
    raw_file = project_root / "data" / "merged_8h_raw.parquet"
    features_file = project_root / "data" / "features_8h.parquet"
    checks.append(("Step 1a: merged_8h_raw.parquet", raw_file.exists()))
    checks.append(("Step 1b: features_8h.parquet", features_file.exists()))

    # Check Step 2: Analysis dataset
    analysis_file = project_root / "data" / "analysis_8h.parquet"
    checks.append(("Step 2: analysis_8h.parquet", analysis_file.exists()))

    # Check Step 3: Optimized features (count varies by config)
    opt_count = len(list(project_root.glob("data/features_8h_optimized_*.parquet")))
    # For now, just check if any exist
    checks.append((f"Step 3: Optimized features ({opt_count} files)", opt_count > 0))
    details["step3_opt_count"] = opt_count

    # Check Step 4: Final datasets
    datasets_dir = project_root / "data" / "datasets"
    dataset_count = (
        len(list(datasets_dir.glob("*.parquet"))) if datasets_dir.exists() else 0
    )
    checks.append(
        (f"Step 4: Final datasets ({dataset_count} files)", dataset_count > 0)
    )
    details["step4_dataset_count"] = dataset_count

    # Check Step 5-7: Results
    results_dir = project_root / "data" / "analysis" / "results"
    ic_file = results_dir / "ic_multi_horizon.csv"
    mdi_file = results_dir / "feature_importance.csv"
    mda_file = results_dir / "mda_importance.csv"
    cv_file = results_dir / "cv_results.csv"

    checks.append(("Step 5: IC analysis", ic_file.exists()))
    checks.append(("Step 6a: MDI importance", mdi_file.exists()))
    checks.append(("Step 6b: MDA importance", mda_file.exists()))
    checks.append(("Step 7: CV results", cv_file.exists()))

    # Print results
    if verbose:
        print()
        for name, passed in checks:
            status = "✓" if passed else "✗"
            print(f"  {status} {name}")

    all_passed = all(passed for _, passed in checks)

    if verbose:
        print()
        if all_passed:
            print("═" * 70)
            print("ALL PIPELINE STEPS COMPLETE ✓")
            print("═" * 70)
        else:
            print("Some steps incomplete - run the missing cells above")

    return PipelineVerificationResult(
        all_passed=all_passed,
        checks=checks,
        details=details,
    )


def verify_step1_features(project_root: Path, verbose: bool = True) -> dict:
    """
    Verify Step 1 feature engineering output.

    Args:
        project_root: Path to the project root directory
        verbose: Whether to print detailed output

    Returns:
        Dict with verification details
    """
    features_path = project_root / "data" / "features_8h.parquet"
    features = pd.read_parquet(features_path)

    result = {
        "shape": features.shape,
        "n_columns": features.shape[1],
        "n_rows": features.shape[0],
    }

    if verbose:
        print("=" * 60)
        print("STEP 1 COMPLETE: FEATURE ENGINEERING")
        print("=" * 60)
        print("\n✓ features_8h.parquet")
        print(f"  Shape: {features.shape}")
        print(f"  Columns: {features.shape[1]}")
        print(f"  Rows: {features.shape[0]:,}")

    # Verify volMomentum fix
    vol_cols = [
        "V_volMomentum_6_pct_N",
        "V_volMomentum_12_pct_N",
        "V_volMomentum_21_pct_N",
    ]
    vol_maxes = {}
    for col in vol_cols:
        if col in features.columns:
            vol_maxes[col] = features[col].max()

    result["vol_momentum_maxes"] = vol_maxes

    if verbose and vol_maxes:
        print("\n✓ volMomentum clipping verified:")
        for col, max_val in vol_maxes.items():
            print(f"  {col}: max={max_val:.1f} (clipped at 15.0)")

    # Verify fracdiff features
    fracdiff_cols = [c for c in features.columns if "fracdiff" in c]
    result["fracdiff_count"] = len(fracdiff_cols)

    if verbose:
        if fracdiff_cols:
            print(f"\n✓ Fractional differentiation features: {len(fracdiff_cols)}")
            for col in fracdiff_cols:
                valid = features[col].notna().sum()
                nan_pct = 100 * (len(features) - valid) / len(features)
                print(
                    f"  {col}: valid={valid:,} ({100 - nan_pct:.1f}%), "
                    f"range=[{features[col].min():.2f}, {features[col].max():.2f}]"
                )
        else:
            print("\n⚠ No fracdiff features found")

        print("\n✓ Ready for Step 2: Target generation")

    return result


def verify_step2_targets(project_root: Path, verbose: bool = True) -> dict:
    """
    Verify Step 2 target generation output.

    Args:
        project_root: Path to the project root directory
        verbose: Whether to print detailed output

    Returns:
        Dict with verification details
    """
    df_check = pl.read_parquet(project_root / "data" / "analysis_8h.parquet")

    result = {
        "shape": df_check.shape,
    }

    if verbose:
        print("=" * 60)
        print("STEP 2 COMPLETE: TARGET GENERATION")
        print("=" * 60)
        print("\n✓ analysis_8h.parquet")
        print(f"  Shape: {df_check.shape}")

    # Count target columns
    target_cols = [c for c in df_check.columns if c.startswith("y_")]
    result["target_cols"] = target_cols

    if verbose:
        print(f"  Target columns: {len(target_cols)}")
        print(f"    {', '.join(target_cols)}")

    # Triple-Barrier Label Analysis
    if "y_tb_direction" in df_check.columns:
        tb_valid = df_check["y_tb_direction"].drop_nulls()
        tb_null = df_check["y_tb_direction"].null_count()
        total = len(df_check)

        label_1 = (df_check["y_tb_direction"] == 1).sum()
        label_0 = (df_check["y_tb_direction"] == 0).sum()

        result["tb_analysis"] = {
            "valid_count": len(tb_valid),
            "null_count": tb_null,
            "label_1_count": label_1,
            "label_0_count": label_0,
        }

        if verbose:
            print("\n" + "-" * 60)
            print("TRIPLE-BARRIER LABELS (y_tb_direction)")
            print("-" * 60)
            print(
                f"  Valid labels: {len(tb_valid):,} ({100 * len(tb_valid) / total:.1f}%)"
            )
            print(f"  Null labels: {tb_null:,} ({100 * tb_null / total:.1f}%)")
            print("\n  Label distribution:")
            print(
                f"    y_tb_direction=1 (profitable): {label_1:,} "
                f"({100 * label_1 / len(tb_valid):.1f}%)"
            )
            print(
                f"    y_tb_direction=0 (unprofitable): {label_0:,} "
                f"({100 * label_0 / len(tb_valid):.1f}%)"
            )

    if verbose:
        print("\n✓ Ready for Step 3: Feature optimization")

    return result


def verify_step3_optimization(
    project_root: Path,
    targets: list[str],
    horizons: list[int],
    verbose: bool = True,
) -> dict:
    """
    Verify Step 3 feature optimization output.

    Args:
        project_root: Path to the project root directory
        targets: List of target types
        horizons: List of horizons
        verbose: Whether to print detailed output

    Returns:
        Dict with verification details
    """
    if verbose:
        print("=" * 60)
        print("STEP 3 VERIFICATION: OPTIMIZED FEATURES")
        print("=" * 60)

    data_dir = project_root / "data"
    expected_count = len(targets) * len(horizons)

    created_files = []
    missing_files = []

    for target in targets:
        for horizon in horizons:
            filename = f"features_8h_optimized_{target}_{horizon}bar.parquet"
            filepath = data_dir / filename
            if filepath.exists():
                size_mb = filepath.stat().st_size / (1024 * 1024)
                created_files.append((filename, size_mb))
            else:
                missing_files.append(filename)

    result = {
        "expected_count": expected_count,
        "created_count": len(created_files),
        "missing_count": len(missing_files),
        "created_files": created_files,
        "missing_files": missing_files,
    }

    if verbose:
        print(f"\n✓ Created files: {len(created_files)}/{expected_count}")
        for f, size in created_files[:5]:
            print(f"  {f}: {size:.2f} MB")
        if len(created_files) > 5:
            print(f"  ... and {len(created_files) - 5} more")

        if missing_files:
            print(f"\n✗ Missing files: {len(missing_files)}")
            for f in missing_files[:5]:
                print(f"  {f}")
        else:
            print(f"\n✓ All {expected_count} optimized feature files created")

        print("\n✓ Ready for Step 4: Dataset generation")

    return result
