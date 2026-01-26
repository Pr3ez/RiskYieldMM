#!/usr/bin/env python3
"""
Full CatBoost Optimization Across All 28 Targets

This script:
1. Loads REAL data for each target (not mock data)
2. Runs full 4-stage optimization
3. Stores optimal parameters to JSON
4. Reports summary of results

Usage:
    # Run all targets
    python run_full_catboost_optimization.py

    # Run specific target types
    python run_full_catboost_optimization.py --targets direction volatility

    # Run specific horizons
    python run_full_catboost_optimization.py --horizons 1 3

    # Dry run (show what would be optimized)
    python run_full_catboost_optimization.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

# Add paths for imports
project_root = Path(__file__).parent.parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

backtest_root = Path(__file__).parent.parent
sys.path.insert(0, str(backtest_root))

# ruff: noqa: E402
from backtest.adapters.data_loader import load_config_data
from backtest.domain.config import SyncBacktestConfig
from backtest.models.catboost_model import (
    characterize_data,
    generate_candidate_configs,
    refine_hyperparameters,
    validate_configs_on_holdout,
)
from backtest.models.optimal_storage import (
    ALL_TARGETS,
    DataCharacteristicsSnapshot,
    OptimalConfig,
    OptimalParamsEntry,
    ValidationScores,
    load_optimal_params,
    print_optimization_summary,
    save_optimal_params,
)

# Default config for loading data - uses sensible defaults
DEFAULT_CONFIG = SyncBacktestConfig(
    train_window=800,
    step_size=1,
    enable_optuna=False,
    n_optuna_trials=0,
    random_state=42,
)


def optimize_single_target(
    target_info: dict,
    min_samples: int = 1000,
    verbose: bool = True,
) -> OptimalParamsEntry | None:
    """Run full optimization for a single target.

    Args:
        target_info: Dict with name, task_type, n_classes, horizon
        min_samples: Minimum samples required
        verbose: Print progress

    Returns:
        OptimalParamsEntry with results, or None if failed
    """
    target_name = target_info["name"]
    task_type = target_info["task_type"]
    n_classes = target_info["n_classes"]
    horizon = target_info["horizon"]

    if verbose:
        print(f"\n{'=' * 60}")
        print(f"Optimizing: {target_name}")
        print(f"  Task: {task_type}, Classes: {n_classes}, Horizon: {horizon}")
        print("=" * 60)

    start_time = time.time()

    # Load real data
    try:
        if verbose:
            print("  Loading data...")
        data = load_config_data(target_name, DEFAULT_CONFIG)
        X_full = data.X_features
        y_full = data.y_target
    except Exception as e:
        print(f"  ERROR loading data: {e}")
        return None

    # Check minimum samples
    n_samples = len(X_full)
    if n_samples < min_samples:
        print(f"  SKIP: Only {n_samples} samples (need {min_samples})")
        return None

    if verbose:
        print(f"  Loaded {n_samples} samples, {len(X_full.columns)} features")

    # Stage 1: Characterize data
    if verbose:
        print("  Stage 1: Characterizing data...")
    try:
        characteristics = characterize_data(X_full, y_full, task_type)
    except Exception as e:
        print(f"  ERROR in characterization: {e}")
        return None

    if verbose:
        print(f"    Class balance: {characteristics.class_balance}")
        print(f"    Stationary: {characteristics.is_stationary}")
        print(f"    Volatility: {characteristics.volatility_level}")

    # Stage 2: Generate candidates
    if verbose:
        print("  Stage 2: Generating candidates...")
    try:
        candidates = generate_candidate_configs(characteristics, target_name, horizon)
        if verbose:
            print(f"    Generated {len(candidates)} candidate configs")
    except Exception as e:
        print(f"  ERROR generating candidates: {e}")
        return None

    # Stage 3: Holdout validation
    if verbose:
        print("  Stage 3: Holdout validation...")
    try:
        best_config, validation_results = validate_configs_on_holdout(
            X_full, y_full, candidates, task_type, n_classes
        )
        best_score = validation_results["best_score"]
        if verbose:
            print(f"    Best combined score: {best_score.get('combined_score', 0):.4f}")
    except Exception as e:
        print(f"  ERROR in validation: {e}")
        return None

    # Stage 4: Hyperparameter refinement
    if verbose:
        print("  Stage 4: Hyperparameter refinement (Optuna)...")
    try:
        final_config = refine_hyperparameters(
            X_full=X_full,
            y_full=y_full,
            base_config=best_config,
            task_type=task_type,
            n_classes=n_classes,
            previous_best=None,
            n_trials=25,
            timeout=60.0,
        )
        if verbose:
            print(
                f"    Final config: depth={final_config.max_depth}, "
                f"lr={final_config.learning_rate:.4f}, "
                f"window={final_config.train_window}"
            )
    except Exception as e:
        print(f"  ERROR in refinement: {e}")
        final_config = best_config

    elapsed = time.time() - start_time

    # Build result entry
    entry = OptimalParamsEntry(
        target_name=target_name,
        task_type=task_type,
        n_classes=n_classes,
        horizon=horizon,
        last_optimized=datetime.now().isoformat(),
        optimization_data_size=n_samples,
        data_characteristics=DataCharacteristicsSnapshot(
            task_type=characteristics.task_type,
            n_classes=characteristics.n_classes,
            class_balance=characteristics.class_balance,
            class_imbalance_ratio=characteristics.class_imbalance_ratio,
            is_stationary=characteristics.is_stationary,
            rolling_mean_drift=characteristics.rolling_mean_drift,
            rolling_std_drift=characteristics.rolling_std_drift,
            volatility_level=characteristics.volatility_level,
            volatility_ratio=characteristics.volatility_ratio,
            n_features=characteristics.n_features,
            n_samples=characteristics.n_samples,
            mean_correlation=characteristics.mean_correlation,
        ),
        optimal_config=OptimalConfig(
            train_window=final_config.train_window,
            train_ratio=final_config.train_ratio,
            val_ratio=final_config.val_ratio,
            cal_ratio=final_config.cal_ratio,
            feature_selection_ratio=final_config.feature_selection_ratio,
            n_estimators=final_config.n_estimators,
            max_depth=final_config.max_depth,
            learning_rate=final_config.learning_rate,
            l2_leaf_reg=final_config.l2_leaf_reg,
            early_stopping_rounds=30,
            feature_selection=final_config.feature_selection,
            min_features=final_config.min_features,
        ),
        validation_scores=ValidationScores(
            combined_score=best_score.get("combined_score", 0),
            accuracy=best_score.get("accuracy"),
            log_loss=best_score.get("log_loss"),
            rmse=best_score.get("rmse"),
            mae=best_score.get("mae"),
        ),
        optimization_time_seconds=elapsed,
        avg_step_time_ms=None,
    )

    if verbose:
        print(f"  DONE in {elapsed:.1f}s")

    return entry


def run_full_optimization(
    target_types: list[str] | None = None,
    horizons: list[int] | None = None,
    dry_run: bool = False,
    verbose: bool = True,
) -> dict[str, OptimalParamsEntry]:
    """Run optimization across all or selected targets.

    Args:
        target_types: Filter by target type (e.g., ["direction", "volatility"])
        horizons: Filter by horizon (e.g., [1, 3])
        dry_run: Just print what would be optimized
        verbose: Print progress

    Returns:
        Dict of target_name -> OptimalParamsEntry
    """
    # Filter targets
    targets_to_run = ALL_TARGETS.copy()

    if target_types:
        targets_to_run = [
            t
            for t in targets_to_run
            if any(t["name"].startswith(tt) for tt in target_types)
        ]

    if horizons:
        targets_to_run = [t for t in targets_to_run if t["horizon"] in horizons]

    print(f"\n{'=' * 60}")
    print("FULL CATBOOST OPTIMIZATION")
    print(f"{'=' * 60}")
    print(f"Targets to optimize: {len(targets_to_run)}")
    print(f"Target types: {target_types or 'all'}")
    print(f"Horizons: {horizons or 'all'}")

    if dry_run:
        print("\nDRY RUN - Would optimize:")
        for t in targets_to_run:
            existing = load_optimal_params(t["name"])
            status = "EXISTS" if existing else "NEW"
            print(f"  [{status}] {t['name']}: {t['task_type']}, h={t['horizon']}")
        return {}

    results = {}
    success_count = 0
    fail_count = 0

    for i, target_info in enumerate(targets_to_run, 1):
        print(f"\n[{i}/{len(targets_to_run)}]", end="")

        try:
            entry = optimize_single_target(target_info, verbose=verbose)
            if entry:
                # Save to storage
                path = save_optimal_params(entry)
                print(f"  Saved to: {path}")
                results[entry.target_name] = entry
                success_count += 1
            else:
                fail_count += 1
        except Exception as e:
            print(f"  EXCEPTION: {e}")
            fail_count += 1

    # Final summary
    print(f"\n{'=' * 60}")
    print("OPTIMIZATION COMPLETE")
    print(f"{'=' * 60}")
    print(f"Success: {success_count}/{len(targets_to_run)}")
    print(f"Failed: {fail_count}/{len(targets_to_run)}")

    if results:
        print("\nResults Summary:")
        for name, entry in results.items():
            score = entry.validation_scores.combined_score
            print(
                f"  {name:25s}: score={score:.4f}, "
                f"time={entry.optimization_time_seconds:.1f}s"
            )

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Run full CatBoost optimization across all targets"
    )
    parser.add_argument(
        "--targets",
        nargs="+",
        help="Target types to optimize (e.g., direction volatility)",
    )
    parser.add_argument(
        "--horizons",
        nargs="+",
        type=int,
        help="Horizons to optimize (e.g., 1 3 6 12)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be optimized without running",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Just print summary of existing optimal params",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Less verbose output",
    )

    args = parser.parse_args()

    if args.summary:
        print_optimization_summary()
        return

    run_full_optimization(
        target_types=args.targets,
        horizons=args.horizons,
        dry_run=args.dry_run,
        verbose=not args.quiet,
    )


if __name__ == "__main__":
    main()
