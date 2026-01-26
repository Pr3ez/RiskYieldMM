"""
Window Size Grid Search for L2 Backtest

Full empirical grid search to find optimal window sizes for each model.
Runs complete L2 walk-forward backtest for each window configuration.

Usage:
    python scripts/experiments/window_grid_search.py --model catboost --windows 300,400,500
    python scripts/experiments/window_grid_search.py --all-models --coarse
    python scripts/experiments/window_grid_search.py --model lstm --fine --base 500

Results saved to: data/experiments/window_grid_search/
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

# Setup path
PROJECT_ROOT = Path("/media/przem/linux_data/RiskYieldMM (Copy)")
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "target_models" / "validation"))
os.chdir(PROJECT_ROOT)

from backtest.domain.config import PerModelConfig, SyncBacktestConfig

from scripts.target_models.validation.l2_backtest_sync import run_sync_backtest
from scripts.workflow.config import L2BacktestDefaults, get_workflow_configs

# =============================================================================
# GRID SEARCH CONFIGURATION
# =============================================================================

# Window size ranges to test
WINDOW_GRIDS = {
    "coarse": [250, 300, 400, 500, 600, 700, 800],  # 7 values
    "medium": [250, 300, 350, 400, 450, 500, 550, 600, 700, 800],  # 10 values
    "fine": lambda base: [
        base - 100,
        base - 50,
        base - 25,
        base,
        base + 25,
        base + 50,
        base + 100,
    ],
}

# Model-specific baseline windows (current defaults)
CURRENT_BASELINES = {
    "catboost": 400,
    "lightgbm": 400,
    "lstm": 600,
    "linear": 800,
}

# Output directory
OUTPUT_DIR = PROJECT_ROOT / "data" / "experiments" / "window_grid_search"


@dataclass
class GridSearchConfig:
    """Configuration for a single grid search run."""

    model: str  # catboost, lightgbm, lstm, linear
    window_sizes: list[int]

    # Which configs to test (target × horizon combinations)
    configs: list[str] | None = None  # None = all available

    # Backtest settings
    n_steps: int | None = None  # None = full backtest
    enable_optuna: bool = False  # Disable for speed (test window only)

    # Output
    experiment_name: str = "window_search"

    def __post_init__(self):
        if self.model not in ["catboost", "lightgbm", "lstm", "linear", "all"]:
            raise ValueError(f"Unknown model: {self.model}")
        self.window_sizes = sorted(set(self.window_sizes))


@dataclass
class GridSearchResult:
    """Results from a single grid search experiment."""

    model: str
    window_size: int
    config_name: str

    # Metrics
    accuracy: float | None = None
    auc: float | None = None
    ic: float | None = None
    rmse: float | None = None
    sharpe: float | None = None

    # Meta
    n_steps: int = 0
    runtime_seconds: float = 0.0
    timestamp: str = ""


# =============================================================================
# GRID SEARCH FUNCTIONS
# =============================================================================


def create_model_config(model: str, window_size: int) -> PerModelConfig:
    """Create PerModelConfig with specified window size."""

    # Base configs per model type
    base_configs = {
        "catboost": {
            "train_window": window_size,
            "train_ratio": 0.60,
            "val_ratio": 0.20,
            "cal_ratio": 0.20,
            "feature_selection": "importance",
            "feature_selection_ratio": 0.6,
            "min_features": 30,
        },
        "lightgbm": {
            "train_window": window_size,
            "train_ratio": 0.60,
            "val_ratio": 0.20,
            "cal_ratio": 0.20,
            "feature_selection": "importance",
            "feature_selection_ratio": 0.6,
            "min_features": 30,
        },
        "lstm": {
            "train_window": window_size,
            "train_ratio": 0.70,
            "val_ratio": 0.15,
            "cal_ratio": 0.15,
            "feature_selection": "variance",
            "feature_selection_ratio": 0.8,
            "min_features": 40,
        },
        "linear": {
            "train_window": window_size,
            "train_ratio": 0.50,
            "val_ratio": 0.20,
            "cal_ratio": 0.30,
            "feature_selection": "variance",
            "feature_selection_ratio": 0.5,
            "min_features": 20,
        },
    }

    return PerModelConfig(**base_configs[model])


def create_backtest_config(
    model: str,
    window_size: int,
    grid_config: GridSearchConfig,
    output_subdir: str,
) -> SyncBacktestConfig:
    """Create SyncBacktestConfig with specified window for target model."""

    defaults = L2BacktestDefaults()

    # Override for grid search
    defaults.n_steps = grid_config.n_steps
    defaults.enable_optuna = grid_config.enable_optuna
    defaults.output_dir = str(OUTPUT_DIR / output_subdir)

    # Create per-model configs (all models use baseline except target)
    cb_config = create_model_config(
        "catboost",
        window_size if model == "catboost" else CURRENT_BASELINES["catboost"],
    )
    lgb_config = create_model_config(
        "lightgbm",
        window_size if model == "lightgbm" else CURRENT_BASELINES["lightgbm"],
    )
    lstm_config = create_model_config(
        "lstm", window_size if model == "lstm" else CURRENT_BASELINES["lstm"]
    )
    linear_config = create_model_config(
        "linear", window_size if model == "linear" else CURRENT_BASELINES["linear"]
    )

    # Convert defaults to kwargs
    kwargs = defaults.to_sync_config_kwargs()

    # Override per-model configs
    kwargs["cb_config"] = cb_config
    kwargs["lgb_config"] = lgb_config
    kwargs["lstm_config"] = lstm_config
    kwargs["linear_config"] = linear_config

    return SyncBacktestConfig(**kwargs)


def extract_metrics(result: dict) -> dict:
    """Extract key metrics from backtest result."""
    metrics = result.get("metrics", {})

    return {
        "accuracy": metrics.get("accuracy"),
        "auc": metrics.get("auc"),
        "ic": metrics.get("ic"),
        "rmse": metrics.get("rmse"),
        "sharpe": metrics.get("sharpe"),
        "n_steps": metrics.get("n_steps", 0),
    }


def run_single_experiment(
    model: str,
    window_size: int,
    config_names: list[str],
    grid_config: GridSearchConfig,
    logger: logging.Logger,
) -> list[GridSearchResult]:
    """Run backtest for a single model/window configuration."""

    import time

    start_time = time.time()

    output_subdir = f"{grid_config.experiment_name}/{model}/window_{window_size}"

    logger.info(f"\n{'=' * 60}")
    logger.info(f"Model: {model} | Window: {window_size}")
    logger.info(f"{'=' * 60}")

    # Create config
    sync_config = create_backtest_config(model, window_size, grid_config, output_subdir)

    # Run backtest
    try:
        results = run_sync_backtest(
            configs=config_names,
            config=sync_config,
            verbose=True,
        )
    except Exception as e:
        logger.error(f"Backtest failed: {e}")
        return []

    runtime = time.time() - start_time
    timestamp = datetime.now().isoformat()

    # Extract results
    search_results = []
    for config_name, result in results.items():
        metrics = extract_metrics(result)

        search_results.append(
            GridSearchResult(
                model=model,
                window_size=window_size,
                config_name=config_name,
                accuracy=metrics["accuracy"],
                auc=metrics["auc"],
                ic=metrics["ic"],
                rmse=metrics["rmse"],
                sharpe=metrics["sharpe"],
                n_steps=metrics["n_steps"],
                runtime_seconds=runtime / len(results),
                timestamp=timestamp,
            )
        )

    return search_results


def run_grid_search(grid_config: GridSearchConfig) -> pd.DataFrame:
    """Run full grid search for specified configuration."""

    # Setup logging
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    log_file = OUTPUT_DIR / f"{grid_config.experiment_name}.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(),
        ],
    )
    logger = logging.getLogger(__name__)

    logger.info("=" * 70)
    logger.info("WINDOW SIZE GRID SEARCH")
    logger.info("=" * 70)
    logger.info(f"Model(s): {grid_config.model}")
    logger.info(f"Windows: {grid_config.window_sizes}")
    logger.info(f"N steps: {grid_config.n_steps or 'all'}")
    logger.info(f"Optuna: {grid_config.enable_optuna}")

    # Get available configs
    all_configs = get_workflow_configs()

    # Filter to ready configs (have combined dataset)
    COMBINED_DIR = PROJECT_ROOT / "data" / "combined_datasets"
    configs_ready = [
        cfg for cfg in all_configs if (COMBINED_DIR / f"{cfg}.parquet").exists()
    ]

    if grid_config.configs:
        config_names = [c for c in grid_config.configs if c in configs_ready]
    else:
        config_names = configs_ready

    logger.info(f"Configs to test: {len(config_names)}")
    for cfg in config_names:
        logger.info(f"  - {cfg}")

    if not config_names:
        logger.error("No configs ready! Run Step 9b first.")
        return pd.DataFrame()

    # Determine models to test
    if grid_config.model == "all":
        models = ["catboost", "lightgbm", "lstm", "linear"]
    else:
        models = [grid_config.model]

    # Run grid search
    all_results = []
    total_experiments = len(models) * len(grid_config.window_sizes)
    current = 0

    for model in models:
        for window_size in grid_config.window_sizes:
            current += 1
            logger.info(
                f"\n[{current}/{total_experiments}] {model} @ window={window_size}"
            )

            results = run_single_experiment(
                model=model,
                window_size=window_size,
                config_names=config_names,
                grid_config=grid_config,
                logger=logger,
            )
            all_results.extend(results)

            # Save intermediate results
            if all_results:
                df = pd.DataFrame([asdict(r) for r in all_results])
                intermediate_file = (
                    OUTPUT_DIR / f"{grid_config.experiment_name}_intermediate.csv"
                )
                df.to_csv(intermediate_file, index=False)
                logger.info(f"Intermediate results saved: {intermediate_file}")

    # Final results
    if all_results:
        df = pd.DataFrame([asdict(r) for r in all_results])
        final_file = OUTPUT_DIR / f"{grid_config.experiment_name}_final.csv"
        df.to_csv(final_file, index=False)
        logger.info(f"\n{'=' * 70}")
        logger.info("GRID SEARCH COMPLETE")
        logger.info(f"Results saved: {final_file}")
        logger.info(f"{'=' * 70}")

        # Print summary
        print_summary(df, logger)

        return df

    return pd.DataFrame()


def print_summary(df: pd.DataFrame, logger: logging.Logger) -> None:
    """Print summary of grid search results."""

    logger.info("\n" + "=" * 70)
    logger.info("SUMMARY: Best Window per Model")
    logger.info("=" * 70)

    # Group by model and find best window for each metric
    for model in df["model"].unique():
        model_df = df[df["model"] == model]

        logger.info(f"\n{model.upper()}:")

        # Best by accuracy (for classification)
        if model_df["accuracy"].notna().any():
            best_acc = model_df.loc[model_df["accuracy"].idxmax()]
            logger.info(
                f"  Best accuracy: window={best_acc['window_size']} → {best_acc['accuracy']:.4f}"
            )

        # Best by AUC
        if model_df["auc"].notna().any():
            best_auc = model_df.loc[model_df["auc"].idxmax()]
            logger.info(
                f"  Best AUC: window={best_auc['window_size']} → {best_auc['auc']:.4f}"
            )

        # Best by IC (for regression)
        if model_df["ic"].notna().any():
            best_ic = model_df.loc[model_df["ic"].idxmax()]
            logger.info(
                f"  Best IC: window={best_ic['window_size']} → {best_ic['ic']:.4f}"
            )

        # Lowest RMSE
        if model_df["rmse"].notna().any():
            best_rmse = model_df.loc[model_df["rmse"].idxmin()]
            logger.info(
                f"  Best RMSE: window={best_rmse['window_size']} → {best_rmse['rmse']:.4f}"
            )

    # Overall ranking by accuracy
    if df["accuracy"].notna().any():
        logger.info("\n" + "-" * 50)
        logger.info("TOP 10 by Accuracy:")
        top10 = df.nlargest(10, "accuracy")[
            ["model", "window_size", "config_name", "accuracy"]
        ]
        for _, row in top10.iterrows():
            logger.info(
                f"  {row['model']:10} w={row['window_size']:4} {row['config_name']:25} acc={row['accuracy']:.4f}"
            )


# =============================================================================
# CLI
# =============================================================================


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""

    parser = argparse.ArgumentParser(
        description="Window Size Grid Search for L2 Backtest",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Coarse search for CatBoost
  python window_grid_search.py --model catboost --coarse
  
  # Fine search around base 400 for LightGBM  
  python window_grid_search.py --model lightgbm --fine --base 400
  
  # Custom windows for LSTM
  python window_grid_search.py --model lstm --windows 400,500,600,700,800
  
  # All models with coarse grid (WARNING: very slow)
  python window_grid_search.py --all-models --coarse
  
  # Quick test (100 steps only)
  python window_grid_search.py --model catboost --coarse --n-steps 100
  
  # Specific configs only
  python window_grid_search.py --model catboost --coarse --configs direction_1bar,direction_3bar
        """,
    )

    # Model selection
    model_group = parser.add_mutually_exclusive_group(required=True)
    model_group.add_argument(
        "--model",
        choices=["catboost", "lightgbm", "lstm", "linear"],
        help="Single model to test",
    )
    model_group.add_argument(
        "--all-models", action="store_true", help="Test all 4 models"
    )

    # Window grid selection
    grid_group = parser.add_mutually_exclusive_group(required=True)
    grid_group.add_argument(
        "--coarse", action="store_true", help="Coarse grid: 250,300,400,500,600,700,800"
    )
    grid_group.add_argument(
        "--medium",
        action="store_true",
        help="Medium grid: 250,300,350,...,800 (10 values)",
    )
    grid_group.add_argument(
        "--fine", action="store_true", help="Fine grid around --base value (±100)"
    )
    grid_group.add_argument(
        "--windows", type=str, help="Custom windows (comma-separated, e.g. 300,400,500)"
    )

    # Fine grid base
    parser.add_argument(
        "--base", type=int, default=400, help="Base window for fine grid (default: 400)"
    )

    # Backtest settings
    parser.add_argument(
        "--n-steps",
        type=int,
        default=None,
        help="Number of backtest steps (default: all)",
    )
    parser.add_argument(
        "--enable-optuna",
        action="store_true",
        help="Enable Optuna tuning (slower but more accurate)",
    )

    # Config selection
    parser.add_argument(
        "--configs",
        type=str,
        default=None,
        help="Specific configs to test (comma-separated)",
    )

    # Experiment name
    parser.add_argument(
        "--name", type=str, default=None, help="Experiment name (for output files)"
    )

    return parser.parse_args()


def main():
    """Main entry point."""

    args = parse_args()

    # Determine model
    model = "all" if args.all_models else args.model

    # Determine window grid
    if args.coarse:
        window_sizes = WINDOW_GRIDS["coarse"]
    elif args.medium:
        window_sizes = WINDOW_GRIDS["medium"]
    elif args.fine:
        window_sizes = WINDOW_GRIDS["fine"](args.base)
    else:
        window_sizes = [int(w) for w in args.windows.split(",")]

    # Filter valid windows
    window_sizes = [w for w in window_sizes if 200 <= w <= 1000]

    # Determine configs
    configs = args.configs.split(",") if args.configs else None

    # Experiment name
    if args.name:
        experiment_name = args.name
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        experiment_name = f"window_search_{model}_{timestamp}"

    # Create config
    grid_config = GridSearchConfig(
        model=model,
        window_sizes=window_sizes,
        configs=configs,
        n_steps=args.n_steps,
        enable_optuna=args.enable_optuna,
        experiment_name=experiment_name,
    )

    print("\n" + "=" * 70)
    print("WINDOW SIZE GRID SEARCH")
    print("=" * 70)
    print(f"Model: {grid_config.model}")
    print(f"Windows: {grid_config.window_sizes}")
    print(f"N steps: {grid_config.n_steps or 'all'}")
    print(f"Optuna: {grid_config.enable_optuna}")
    print(f"Output: {OUTPUT_DIR / experiment_name}")
    print("=" * 70)

    confirm = input("\nStart grid search? [y/N]: ")
    if confirm.lower() != "y":
        print("Aborted.")
        return

    # Run
    results_df = run_grid_search(grid_config)

    if not results_df.empty:
        print("\n✓ Grid search complete!")
        print(f"  Results: {OUTPUT_DIR / experiment_name}_final.csv")


if __name__ == "__main__":
    main()
