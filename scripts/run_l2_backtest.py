#!/usr/bin/env python3
"""
L2 Backtest Runner
==================
Helper script to run L2 ensemble backtest with proper configuration.

Usage:
    python scripts/run_l2_backtest.py
    python scripts/run_l2_backtest.py --train-window 500 --step-size 1
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.target_models.validation.l2_backtest_sync import (
    SyncBacktestConfig,
    run_sync_backtest,
)


def main():
    parser = argparse.ArgumentParser(
        description="Run L2 ensemble backtest with CatBoost + LightGBM + Linear"
    )
    parser.add_argument(
        "--train-window",
        type=int,
        default=500,
        help="Training window size (default: 500)",
    )
    parser.add_argument(
        "--step-size", type=int, default=1, help="Step size (default: 1)"
    )
    parser.add_argument(
        "--n-estimators", type=int, default=100, help="Number of trees (default: 100)"
    )
    parser.add_argument(
        "--max-depth", type=int, default=6, help="Max tree depth (default: 6)"
    )
    parser.add_argument(
        "--cb-weight", type=float, default=0.4, help="CatBoost weight (default: 0.4)"
    )
    parser.add_argument(
        "--lgb-weight", type=float, default=0.4, help="LightGBM weight (default: 0.4)"
    )
    parser.add_argument(
        "--quiet", "-q", action="store_true", help="Suppress live progress output"
    )
    args = parser.parse_args()

    print("=" * 80)
    print("L2 ENSEMBLE BACKTEST")
    print("=" * 80)
    print(f"  Train Window:  {args.train_window}")
    print(f"  Step Size:     {args.step_size}")
    print(f"  N Estimators:  {args.n_estimators}")
    print(f"  Max Depth:     {args.max_depth}")
    print(f"  CB Weight:     {args.cb_weight}")
    print(f"  LGB Weight:    {args.lgb_weight}")
    print(f"  Linear Weight: {1.0 - args.cb_weight - args.lgb_weight:.1f}")
    print("=" * 80)

    config = SyncBacktestConfig(
        train_window=args.train_window,
        step_size=args.step_size,
        n_estimators=args.n_estimators,
        max_depth=args.max_depth,
        cb_weight=args.cb_weight,
        lgb_weight=args.lgb_weight,
        cb_learning_rate=0.03,
        lgb_learning_rate=0.03,
    )

    # Run backtest
    results = run_sync_backtest(config=config, verbose=not args.quiet)

    # Final summary table
    print()
    print("=" * 80)
    print("FINAL RESULTS")
    print("=" * 80)

    # Classification
    cls_results = {
        k: v for k, v in results.items() if v["task_type"] == "classification"
    }
    if cls_results:
        print()
        print(f"┌{'─' * 78}┐")
        print(f"│ {'CLASSIFICATION':<76} │")
        print(f"├{'─' * 25}┬{'─' * 12}┬{'─' * 12}┬{'─' * 12}┬{'─' * 12}┤")
        print(
            f"│ {'Config':<23} │ {'Accuracy':^10} │ {'F1':^10} │ {'Coverage':^10} │ {'N':^10} │"
        )
        print(f"├{'─' * 25}┼{'─' * 12}┼{'─' * 12}┼{'─' * 12}┼{'─' * 12}┤")
        for name, r in sorted(cls_results.items()):
            m = r["metrics"]
            print(
                f"│ {name:<23} │ {m.get('accuracy', 0):^10.4f} │ {m.get('f1_weighted', 0):^10.4f} │ {m.get('coverage', 0):^10.4f} │ {m.get('n_predictions', 0):^10} │"
            )
        print(f"└{'─' * 25}┴{'─' * 12}┴{'─' * 12}┴{'─' * 12}┴{'─' * 12}┘")

    # Regression
    reg_results = {k: v for k, v in results.items() if v["task_type"] == "regression"}
    if reg_results:
        print()
        print(f"┌{'─' * 78}┐")
        print(f"│ {'REGRESSION':<76} │")
        print(f"├{'─' * 25}┬{'─' * 12}┬{'─' * 12}┬{'─' * 12}┬{'─' * 12}┤")
        print(
            f"│ {'Config':<23} │ {'IC':^10} │ {'RMSE':^10} │ {'Coverage':^10} │ {'N':^10} │"
        )
        print(f"├{'─' * 25}┼{'─' * 12}┼{'─' * 12}┼{'─' * 12}┼{'─' * 12}┤")
        for name, r in sorted(reg_results.items()):
            m = r["metrics"]
            print(
                f"│ {name:<23} │ {m.get('ic', 0):^10.4f} │ {m.get('rmse', 0):^10.6f} │ {m.get('coverage', 0):^10.4f} │ {m.get('n_predictions', 0):^10} │"
            )
        print(f"└{'─' * 25}┴{'─' * 12}┴{'─' * 12}┴{'─' * 12}┴{'─' * 12}┘")

    print()
    print("✅ Results saved to data/l2_backtest_results/")


if __name__ == "__main__":
    main()
