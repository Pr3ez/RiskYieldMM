#!/usr/bin/env python3
"""
L2 Backtest Runner
==================
Helper script to run L2 ensemble backtest with proper configuration.

Usage:
    python scripts/run_l2_backtest.py
    python scripts/run_l2_backtest.py --train-window 500 --step-size 1
    python scripts/run_l2_backtest.py --all-configs  # Run all 16 configs instead of 4 1-bar
    python scripts/run_l2_backtest.py --n-steps 100  # Run only last 100 steps
    python scripts/run_l2_backtest.py --configs direction_1bar vol_spike_1bar  # Specific configs
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.target_models.validation.dataset_assembly import ALL_CONFIGS
from scripts.target_models.validation.l2_backtest_sync import (
    REDUCED_CONFIGS,
    SyncBacktestConfig,
    get_configs_1bar,
    run_sync_backtest,
)

# Get CONFIGS_1BAR from the function
CONFIGS_1BAR = get_configs_1bar()


def main():
    parser = argparse.ArgumentParser(
        description="Run L2 ensemble backtest with CatBoost + LightGBM + LSTM + Linear"
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
        "--n-steps",
        type=int,
        default=None,
        help="Number of backtest steps to run (default: ALL available). "
        "Uses most recent N steps of data.",
    )
    parser.add_argument(
        "--spread",
        action="store_true",
        help="Spread n_steps evenly across full data range (first to last). "
        "E.g., --n-steps 100 --spread runs 100 steps spaced evenly over all available data.",
    )
    parser.add_argument(
        "--n-estimators", type=int, default=100, help="Number of trees (default: 100)"
    )
    parser.add_argument(
        "--max-depth", type=int, default=6, help="Max tree depth (default: 6)"
    )
    parser.add_argument(
        "--cb-weight", type=float, default=0.30, help="CatBoost weight (default: 0.30)"
    )
    parser.add_argument(
        "--lgb-weight", type=float, default=0.30, help="LightGBM weight (default: 0.30)"
    )
    parser.add_argument(
        "--lstm-weight", type=float, default=0.25, help="LSTM weight (default: 0.25)"
    )
    parser.add_argument(
        "--1bar",
        dest="use_1bar",
        action="store_true",
        default=True,
        help="Use only 1-bar configs (4 configs) - DEFAULT",
    )
    parser.add_argument(
        "--reduced",
        action="store_true",
        help="Use reduced configs (8 = 1bar+3bar)",
    )
    parser.add_argument(
        "--all-configs",
        action="store_true",
        help="Use all 16 configs",
    )
    parser.add_argument(
        "--configs",
        nargs="+",
        default=None,
        help="Specific config names to run (e.g., --configs direction_1bar vol_spike_1bar). "
        f"Available: {', '.join(ALL_CONFIGS)}",
    )
    parser.add_argument(
        "--quiet", "-q", action="store_true", help="Suppress live progress output"
    )
    args = parser.parse_args()

    # Validate configs if specified
    if args.configs:
        invalid = [c for c in args.configs if c not in ALL_CONFIGS]
        if invalid:
            parser.error(
                f"Invalid config(s): {invalid}. Valid options: {', '.join(ALL_CONFIGS)}"
            )

    linear_weight = 1.0 - args.cb_weight - args.lgb_weight - args.lstm_weight

    # Determine which configs to use
    if args.configs:
        configs_to_use = args.configs
        configs_desc = f"CUSTOM ({len(configs_to_use)}): {', '.join(configs_to_use)}"
    elif args.all_configs:
        configs_to_use = None  # None means ALL_CONFIGS in run_sync_backtest
        configs_desc = "ALL (20)"
    elif args.reduced:
        configs_to_use = REDUCED_CONFIGS
        configs_desc = "REDUCED (10: 1bar+3bar)"
    else:
        # Default: 1-bar only
        configs_to_use = CONFIGS_1BAR
        configs_desc = "1-BAR ONLY (5)"

    print("=" * 80)
    print("L2 ENSEMBLE BACKTEST (4-MODEL)")
    print("=" * 80)
    print(f"  Step Size:     {args.step_size}")
    spread_info = " (SPREAD across full range)" if args.spread else ""
    print(
        f"  N Steps:       {args.n_steps if args.n_steps else 'ALL (maximum available)'}{spread_info}"
    )
    print(f"  CB Weight:     {args.cb_weight}")
    print(f"  LGB Weight:    {args.lgb_weight}")
    print(f"  LSTM Weight:   {args.lstm_weight}")
    print(f"  Linear Weight: {linear_weight:.2f}")
    print(f"  Configs:       {configs_desc}")
    print("=" * 80)

    config = SyncBacktestConfig(
        train_window=args.train_window,
        step_size=args.step_size,
        n_steps=args.n_steps,
        spread_steps=args.spread,
        n_estimators=args.n_estimators,
        max_depth=args.max_depth,
        cb_weight=args.cb_weight,
        lgb_weight=args.lgb_weight,
        lstm_weight=args.lstm_weight,
        cb_learning_rate=0.03,
        lgb_learning_rate=0.03,
    )

    # Run backtest
    results = run_sync_backtest(
        config=config, configs=configs_to_use, verbose=not args.quiet
    )

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
