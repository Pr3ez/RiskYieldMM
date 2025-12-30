#!/usr/bin/env python
"""
Precompute L1 features for all 20 configs and validate against production.

This script:
1. Precomputes L1 helper_features for all 20 configs (5 targets × 4 horizons)
2. Validates each precomputed iteration matches what production pipeline generates
3. Reports any mismatches

Usage:
    python scripts/target_models/validation/precompute_and_validate_all.py
"""

from __future__ import annotations

import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl

warnings.filterwarnings("ignore")

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.target_models.core.aligned_dual_window import (  # noqa: E402
    AlignedDualConfig,
    DualLayerEngine,
    SlidingL2Config,
)
from scripts.target_models.helpers import create_helper_ensemble  # noqa: E402
from scripts.target_models.validation.l1_precompute import (  # noqa: E402
    L1PrecomputeConfig,
    get_all_config_names,
    load_precomputed_l1,
    precompute_l1_for_config,
)


def validate_iteration_exact(
    config_name: str,
    iteration: int,
    cfg: L1PrecomputeConfig,
    X: pd.DataFrame,
    y: pd.Series,
    window,
    target: str,
    horizon: int,
) -> dict:
    """
    Validate a single iteration matches production exactly.

    Returns dict with validation results.
    """
    # Compute fresh (exactly as production does)
    ensemble = create_helper_ensemble(target, horizon, cfg.random_state + iteration)

    l1 = window.l1
    ensemble.fit(X.iloc[l1.train.start_idx : l1.train.end_idx])
    ensemble.optimize(
        X.iloc[l1.val.start_idx : l1.val.end_idx],
        y.iloc[l1.val.start_idx : l1.val.end_idx],
    )

    l2 = window.l2
    fresh = ensemble.transform(X.iloc[l2.train.start_idx : l2.pred.end_idx]).features

    # Load precomputed
    precomputed = load_precomputed_l1(config_name, iteration, cfg)

    # Compare
    result = {
        "iteration": iteration,
        "fresh_shape": fresh.shape,
        "precomputed_shape": precomputed.shape,
        "shape_match": fresh.shape == precomputed.shape,
        "cols_match": list(fresh.columns) == list(precomputed.columns),
        "values_match": False,
        "max_diff": None,
    }

    if result["shape_match"] and result["cols_match"]:
        # Check values match
        diff = np.abs(fresh.values - precomputed.values)
        max_diff = np.max(diff)
        result["values_match"] = max_diff < 1e-10
        result["max_diff"] = float(max_diff)

    return result


def validate_config_full(
    config_name: str,
    cfg: L1PrecomputeConfig,
    n_iterations_to_check: int = 5,
) -> dict:
    """
    Validate precomputed features for a config against fresh computation.

    Checks first N iterations for exact match.
    """
    # Parse config
    parts = config_name.rsplit("_", 1)
    target = parts[0]
    horizon = int(parts[1].replace("bar", ""))

    # Load data (match `l1_precompute.precompute_l1_for_config` and production NA filtering)
    data_path = cfg.data_dir / f"{config_name}.parquet"
    df_pl = pl.read_parquet(data_path)

    if "timestamp" not in df_pl.columns:
        raise ValueError(f"No timestamp column in {config_name} data")

    y_cols = [c for c in df_pl.columns if c.startswith("y_")]
    feature_cols = [
        c for c in df_pl.columns if not c.startswith("y_") and c != "timestamp"
    ]

    y_col = f"y_{target}"
    if y_col not in df_pl.columns:
        y_col = y_cols[0] if y_cols else None
    if y_col is None:
        raise ValueError(f"No target column found for {config_name}")

    not_null_exprs = [pl.col(c).is_not_null() for c in feature_cols]
    not_null_exprs.append(pl.col(y_col).is_not_null())
    df_pl = df_pl.filter(pl.all_horizontal(not_null_exprs))

    df = df_pl.to_pandas()
    X = df[feature_cols]
    y = df[y_col]

    # Create engine (match horizon-aligned production config)
    dual_config = AlignedDualConfig(
        backtest_rows=cfg.backtest_rows,
        target_name=target,
        horizon=horizon,
        l2=SlidingL2Config(pred_size=horizon),
    )
    engine = DualLayerEngine(X, y, dual_config)

    # Validate iterations
    results = []
    for iteration, window in enumerate(engine.iterate()):
        if iteration >= n_iterations_to_check:
            break

        result = validate_iteration_exact(
            config_name, iteration, cfg, X, y, window, target, horizon
        )
        results.append(result)

    # Summary
    all_shape_match = all(r["shape_match"] for r in results)
    all_cols_match = all(r["cols_match"] for r in results)
    all_values_match = all(r["values_match"] for r in results)

    return {
        "config_name": config_name,
        "iterations_checked": len(results),
        "all_shape_match": all_shape_match,
        "all_cols_match": all_cols_match,
        "all_values_match": all_values_match,
        "passed": all_shape_match and all_cols_match and all_values_match,
        "details": results,
    }


def precompute_and_validate_all(
    backtest_rows: int = 200,
    validate_iterations: int = 5,
    configs: list[str] | None = None,
) -> pd.DataFrame:
    """
    Precompute L1 for all configs and validate.

    Args:
        backtest_rows: Number of backtest iterations
        validate_iterations: Number of iterations to validate per config
        configs: List of configs (default: all 20)

    Returns:
        DataFrame with validation results
    """
    cfg = L1PrecomputeConfig(backtest_rows=backtest_rows)
    configs = configs or get_all_config_names()

    print("=" * 70)
    print("PRECOMPUTE AND VALIDATE ALL CONFIGS")
    print(f"Backtest rows: {backtest_rows}")
    print(f"Validate iterations: {validate_iterations}")
    print(f"Configs: {len(configs)}")
    print("=" * 70)

    results = []
    total_start = time.time()

    for i, config_name in enumerate(configs):
        print(f"\n[{i + 1}/{len(configs)}] {config_name}")
        print("-" * 50)

        # Step 1: Precompute
        print("  Precomputing L1...")
        precompute_start = time.time()
        try:
            metadata = precompute_l1_for_config(config_name, cfg, verbose=False)
            precompute_time = time.time() - precompute_start
            print(
                f"  ✓ Precomputed {metadata.total_iterations} iterations in {precompute_time:.1f}s"
            )
        except Exception as e:
            print(f"  ✗ Precompute failed: {e}")
            results.append(
                {
                    "config": config_name,
                    "precompute_ok": False,
                    "validation_ok": False,
                    "error": str(e),
                }
            )
            continue

        # Step 2: Validate
        print(f"  Validating {validate_iterations} iterations...")
        validate_start = time.time()
        try:
            validation = validate_config_full(config_name, cfg, validate_iterations)
            validate_time = time.time() - validate_start

            status = "✓ PASSED" if validation["passed"] else "✗ FAILED"
            print(f"  {status} in {validate_time:.1f}s")

            if not validation["passed"]:
                for d in validation["details"]:
                    if not (d["shape_match"] and d["cols_match"] and d["values_match"]):
                        print(
                            f"    Iter {d['iteration']}: shape={d['shape_match']}, "
                            f"cols={d['cols_match']}, values={d['values_match']}"
                        )

            results.append(
                {
                    "config": config_name,
                    "precompute_ok": True,
                    "precompute_time_s": round(precompute_time, 1),
                    "n_iterations": metadata.total_iterations,
                    "validation_ok": validation["passed"],
                    "shape_match": validation["all_shape_match"],
                    "cols_match": validation["all_cols_match"],
                    "values_match": validation["all_values_match"],
                    "validate_time_s": round(validate_time, 1),
                }
            )

        except Exception as e:
            print(f"  ✗ Validation failed: {e}")
            results.append(
                {
                    "config": config_name,
                    "precompute_ok": True,
                    "precompute_time_s": round(precompute_time, 1),
                    "validation_ok": False,
                    "error": str(e),
                }
            )

    total_time = time.time() - total_start

    # Summary
    df = pd.DataFrame(results)

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    precompute_ok = df["precompute_ok"].sum()
    validation_ok = df["validation_ok"].sum()

    print(f"Precompute: {precompute_ok}/{len(configs)} OK")
    print(f"Validation: {validation_ok}/{len(configs)} OK")
    print(f"Total time: {total_time / 60:.1f} minutes")

    if validation_ok == len(configs):
        print(
            "\n🎉 ALL CONFIGS PASSED - Precomputed features match production exactly!"
        )
    else:
        failed = df[~df["validation_ok"]]["config"].tolist()
        print(f"\n⚠️  FAILED CONFIGS: {failed}")

    # Save results
    output_path = cfg.output_dir / "validation_results.csv"
    df.to_csv(output_path, index=False)
    print(f"\nResults saved to: {output_path}")

    return df


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Precompute and validate L1 features")
    parser.add_argument(
        "--backtest-rows", type=int, default=200, help="Number of backtest rows"
    )
    parser.add_argument(
        "--validate-iters", type=int, default=5, help="Iterations to validate"
    )
    parser.add_argument(
        "--config", type=str, default=None, help="Single config to process"
    )
    args = parser.parse_args()

    configs = [args.config] if args.config else None

    df = precompute_and_validate_all(
        backtest_rows=args.backtest_rows,
        validate_iterations=args.validate_iters,
        configs=configs,
    )

    print("\nFinal Results:")
    print(df.to_string())
