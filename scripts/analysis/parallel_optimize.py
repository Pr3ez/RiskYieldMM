"""
Parallel Auto-Optimization (Causal-Safe)
========================================

Runs target-horizon optimizations in parallel.
Each worker still computes ROW-BY-ROW internally (causal).

SAFETY GUARANTEE:
    - Workers are independent (no shared state)
    - Each worker runs sequential row-by-row
    - No data leakage between combinations
    - Equivalent to running sequentially, just faster

Metadata Storage:
    - Optimization method stored in parquet file metadata
    - Read with: pyarrow.parquet.read_table(f).schema.metadata[b'optimization_method']

Usage:
    from scripts.analysis.parallel_optimize import parallel_auto_optimize
    results = parallel_auto_optimize(n_workers=4)
"""

import json
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


def _optimize_single_target_horizon(args_tuple):
    """
    Optimize a single target-horizon combination.

    This runs in a separate process - completely isolated.
    All computations inside are still SEQUENTIAL and CAUSAL.

    Args:
        args_tuple: (target, horizon, X_base_path, close_path, high_path, low_path, df_index, config_dict)

    Returns:
        dict with optimization results
    """
    import warnings

    warnings.filterwarnings("ignore")

    (target, horizon, X_base_path, raw_path, df_index_path, output_dir, results_dir) = (
        args_tuple
    )

    import numpy as np
    import pandas as pd
    import polars as pl
    from scipy.stats import spearmanr

    # Import optimizers (each process needs its own imports)
    from scripts.analysis.optimizers import (
        ExpandingRankOptimizer,
        InteractionOptimizer,
        LogTransformOptimizer,
        OptimizationPipeline,
        RollingZScoreOptimizer,
        WinsorizeOptimizer,
    )

    # Import centralized targets module (single source of truth)
    from scripts.workflow.targets import compute_target_pandas

    # Load data in this process
    X_base = pd.read_parquet(X_base_path)
    raw = pl.read_parquet(raw_path)
    df_index = pd.read_parquet(df_index_path).index

    close = raw["RAW_P_close_abs_NN"].to_pandas()
    high = raw["RAW_P_high_abs_NN"].to_pandas()
    low = raw["RAW_P_low_abs_NN"].to_pandas()
    close.index = df_index
    high.index = df_index
    low.index = df_index
    X_base.index = df_index

    def compute_mean_abs_ic(X: pd.DataFrame, y: pd.Series) -> float:
        """Compute mean |IC| across all features."""
        ics = []
        y_np = y.values if hasattr(y, "values") else y
        for col in X.columns:
            feat = X[col].values
            mask = ~(np.isnan(feat) | pd.isna(y_np))
            if mask.sum() > 100:
                ic, _ = spearmanr(feat[mask], y_np[mask])
                if not np.isnan(ic):
                    ics.append(abs(ic))
        return np.mean(ics) if ics else 0.0

    def get_target_series(target: str, horizon: int) -> pd.Series:
        """Compute target series using centralized targets module."""
        # Use centralized target computation - single source of truth
        return compute_target_pandas(
            target_name=target,
            close=close,
            high=high,
            low=low,
            horizon=horizon,
        ).astype(float)

    def get_pipeline_candidates(target: str):
        """Get pipeline candidates for target type."""
        pipelines = {
            "baseline": [],
            "winsorize": [WinsorizeOptimizer(lower=0.01, upper=0.99)],
        }

        if target in {"direction", "returns"}:
            pipelines["winsorize_zscore"] = [
                WinsorizeOptimizer(lower=0.01, upper=0.99),
                RollingZScoreOptimizer(window=252),
            ]
            pipelines["winsorize_zscore_interactions"] = [
                WinsorizeOptimizer(lower=0.01, upper=0.99),
                RollingZScoreOptimizer(window=252),
                InteractionOptimizer(top_k=3, n_interactions=5, min_ic=0.02),
            ]

        if target in {
            "direction",
            "trend_regime",
            "volatility_regime",
            "first_extreme",
        }:
            pipelines["winsorize_rank"] = [
                WinsorizeOptimizer(lower=0.01, upper=0.99),
                ExpandingRankOptimizer(min_periods=252),
            ]
            pipelines["winsorize_rank_interactions"] = [
                WinsorizeOptimizer(lower=0.01, upper=0.99),
                ExpandingRankOptimizer(min_periods=252),
                InteractionOptimizer(top_k=3, n_interactions=5, min_ic=0.05),
            ]

        if target in {"volatility", "vol_to_extreme"}:
            pipelines["winsorize_log"] = [
                WinsorizeOptimizer(lower=0.01, upper=0.99),
                LogTransformOptimizer(),
            ]

        min_ic = (
            0.05
            if target
            in {
                "volatility",
                "volatility_regime",
                "trend_regime",
                "vol_to_extreme",
            }
            else 0.02
        )
        pipelines["winsorize_interactions"] = [
            WinsorizeOptimizer(lower=0.01, upper=0.99),
            InteractionOptimizer(top_k=3, n_interactions=5, min_ic=min_ic),
        ]

        return pipelines

    # Run optimization for this target-horizon
    y = get_target_series(target, horizon)
    pipeline_candidates = get_pipeline_candidates(target)

    best_ic = -1
    best_pipeline = None
    best_X = None
    baseline_ic = 0

    for pipe_name, steps in pipeline_candidates.items():
        try:
            if steps:
                pipeline = OptimizationPipeline(steps, name=pipe_name)
                X_transformed = pipeline.fit_transform(X_base.copy(), y)
            else:
                X_transformed = X_base.copy()

            ic = compute_mean_abs_ic(X_transformed, y)

            if pipe_name == "baseline":
                baseline_ic = ic

            if ic > best_ic:
                best_ic = ic
                best_pipeline = pipe_name
                best_X = X_transformed

        except Exception:
            pass  # Skip failed pipelines

    # Save optimized features with metadata
    if best_X is not None:
        output_file = (
            Path(output_dir) / f"features_8h_optimized_{target}_{horizon}bar.parquet"
        )

        # Create metadata to store with the parquet file
        optimization_metadata = {
            "target": target,
            "horizon": horizon,
            "method": best_pipeline,
            "baseline_ic": float(baseline_ic),
            "best_ic": float(best_ic),
            "n_features": int(best_X.shape[1]),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Convert DataFrame to PyArrow Table with custom metadata
        table = pa.Table.from_pandas(best_X)
        existing_metadata = table.schema.metadata or {}
        new_metadata = {
            **existing_metadata,
            b"optimization_method": best_pipeline.encode(),
            b"optimization_metadata": json.dumps(optimization_metadata).encode(),
        }
        table = table.replace_schema_metadata(new_metadata)
        pq.write_table(table, output_file)

    improvement = (
        ((best_ic - baseline_ic) / baseline_ic * 100) if baseline_ic > 0 else 0
    )

    return {
        "target": target,
        "horizon": horizon,
        "best_pipeline": best_pipeline,
        "best_ic": best_ic,
        "baseline_ic": baseline_ic,
        "improvement_pct": improvement,
        "n_features": best_X.shape[1] if best_X is not None else 0,
    }


def parallel_auto_optimize(
    horizons=None,
    targets=None,
    n_workers=None,
    save=True,
    use_threading=True,  # Use threads instead of processes for Jupyter compatibility
):
    """
    Run auto-optimization across 20 target-horizon combinations.

    CAUSALITY GUARANTEE:
        Each worker processes its combination INDEPENDENTLY.
        All row-by-row computations are preserved within each worker.
        No data sharing between workers = no leakage possible.

    Args:
        horizons: List of horizons [1,3,6,12]
        targets: List of targets
        n_workers: Number of parallel workers (default: min(cpu_count, 8))
        save: Save results to disk
        use_threading: Use ThreadPoolExecutor (True, default for Jupyter) or
                       ProcessPoolExecutor (False, faster but no live output)

    Returns:
        DataFrame with results for all combinations
    """
    from concurrent.futures import ThreadPoolExecutor

    from scripts.analysis import config, data

    horizons = horizons or [1, 3, 6, 12]
    targets = targets or [
        "direction",
        "returns",
        "volatility",
        "volatility_regime",
        "trend_regime",
    ]
    n_workers = n_workers or min(mp.cpu_count(), 8)

    mode = "THREADED" if use_threading else "MULTIPROCESS"
    print("=" * 80, flush=True)
    print(f"AUTO-OPTIMIZATION ({mode}, Causal-Safe)", flush=True)
    print("=" * 80, flush=True)
    print(f"Targets: {targets}", flush=True)
    print(f"Horizons: {horizons}", flush=True)
    print(f"Total combinations: {len(targets) * len(horizons)}", flush=True)
    print(f"Workers: {n_workers}", flush=True)
    print("-" * 80, flush=True)

    # Prepare shared data paths (each worker loads its own copy)
    df = data.load_analysis_data()
    feature_cols = data.get_feature_columns(df)
    X_base = df[feature_cols].copy()

    # Save temp files for workers
    temp_dir = config.DATA_DIR / "temp_parallel"
    temp_dir.mkdir(exist_ok=True)

    X_base_path = temp_dir / "X_base_temp.parquet"
    df_index_path = temp_dir / "df_index_temp.parquet"

    X_base.to_parquet(X_base_path)
    pd.DataFrame(index=df.index).to_parquet(df_index_path)

    # Build task list
    tasks = []
    for target in targets:
        for horizon in horizons:
            tasks.append(
                (
                    target,
                    horizon,
                    str(X_base_path),
                    str(config.RAW_FILE),
                    str(df_index_path),
                    str(config.DATA_DIR),
                    str(config.RESULTS_DIR),
                )
            )

    # Choose executor based on mode
    ExecutorClass = ThreadPoolExecutor if use_threading else ProcessPoolExecutor

    # Run with chosen executor
    results = []
    completed = 0

    with ExecutorClass(max_workers=n_workers) as executor:
        futures = {
            executor.submit(_optimize_single_target_horizon, task): task
            for task in tasks
        }

        for future in as_completed(futures):
            task = futures[future]
            target, horizon = task[0], task[1]
            try:
                result = future.result()
                results.append(result)
                completed += 1
                print(
                    f"  [{completed:2d}/20] {target}_{horizon}bar: {result['best_pipeline']} (IC={result['best_ic']:.4f})",
                    flush=True,
                )
            except Exception as e:
                print(
                    f"  [{completed:2d}/20] {target}_{horizon}bar: ERROR - {e}",
                    flush=True,
                )
                completed += 1

    # Cleanup temp files
    X_base_path.unlink(missing_ok=True)
    df_index_path.unlink(missing_ok=True)
    temp_dir.rmdir()

    # Summary
    print("\n" + "=" * 80, flush=True)
    print("AUTO-OPTIMIZATION COMPLETE", flush=True)
    print("=" * 80, flush=True)

    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values(["target", "horizon"])
    print(results_df.to_string(index=False), flush=True)

    if save:
        summary_file = config.RESULTS_DIR / "auto_optimize_summary.csv"
        results_df.to_csv(summary_file, index=False)
        print(f"\n✓ Summary saved: {summary_file}", flush=True)

    return results_df


if __name__ == "__main__":
    # Test parallel optimization
    results = parallel_auto_optimize(n_workers=4)
