"""
Analyze Window Grid Search Results

Visualize and compare results from window_grid_search.py experiments.

Usage:
    python scripts/experiments/analyze_window_results.py data/experiments/window_grid_search/window_search_*_final.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

PROJECT_ROOT = Path("/media/przem/linux_data/RiskYieldMM (Copy)")


def load_results(csv_paths: list[str]) -> pd.DataFrame:
    """Load and combine results from multiple CSV files."""
    dfs = []
    for path in csv_paths:
        df = pd.read_csv(path)
        df["source_file"] = Path(path).stem
        dfs.append(df)
    return pd.concat(dfs, ignore_index=True)


def plot_window_vs_accuracy(df: pd.DataFrame, output_dir: Path) -> None:
    """Plot window size vs accuracy for each model."""

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("Window Size vs Accuracy by Model", fontsize=14)

    models = ["catboost", "lightgbm", "lstm", "linear"]

    for ax, model in zip(axes.flat, models):
        model_df = df[df["model"] == model]

        if model_df.empty or model_df["accuracy"].isna().all():
            ax.set_title(f"{model} (no data)")
            continue

        # Group by config and window
        for config_name in model_df["config_name"].unique():
            config_df = model_df[model_df["config_name"] == config_name]
            ax.plot(
                config_df["window_size"],
                config_df["accuracy"],
                marker="o",
                label=config_name,
                alpha=0.7,
            )

        ax.set_xlabel("Window Size")
        ax.set_ylabel("Accuracy")
        ax.set_title(f"{model.upper()}")
        ax.legend(fontsize=8, loc="best")
        ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_dir / "window_vs_accuracy.png", dpi=150)
    plt.close()
    print(f"Saved: {output_dir / 'window_vs_accuracy.png'}")


def plot_heatmap_accuracy(df: pd.DataFrame, output_dir: Path) -> None:
    """Heatmap of accuracy by model and window size."""

    # Aggregate across configs (mean accuracy)
    pivot = df.pivot_table(
        values="accuracy",
        index="model",
        columns="window_size",
        aggfunc="mean",
    )

    plt.figure(figsize=(12, 6))
    sns.heatmap(
        pivot,
        annot=True,
        fmt=".3f",
        cmap="RdYlGn",
        center=pivot.mean().mean(),
    )
    plt.title("Mean Accuracy by Model and Window Size")
    plt.tight_layout()
    plt.savefig(output_dir / "heatmap_accuracy.png", dpi=150)
    plt.close()
    print(f"Saved: {output_dir / 'heatmap_accuracy.png'}")


def plot_window_distribution(df: pd.DataFrame, output_dir: Path) -> None:
    """Box plot of accuracy distribution by window size."""

    plt.figure(figsize=(14, 6))

    # Order by window size
    window_order = sorted(df["window_size"].unique())

    sns.boxplot(
        data=df,
        x="window_size",
        y="accuracy",
        hue="model",
        order=window_order,
    )

    plt.xlabel("Window Size")
    plt.ylabel("Accuracy")
    plt.title("Accuracy Distribution by Window Size and Model")
    plt.legend(title="Model")
    plt.tight_layout()
    plt.savefig(output_dir / "boxplot_accuracy.png", dpi=150)
    plt.close()
    print(f"Saved: {output_dir / 'boxplot_accuracy.png'}")


def find_optimal_windows(df: pd.DataFrame) -> pd.DataFrame:
    """Find optimal window for each model × config combination."""

    results = []

    for model in df["model"].unique():
        model_df = df[df["model"] == model]

        for config_name in model_df["config_name"].unique():
            config_df = model_df[model_df["config_name"] == config_name]

            if config_df["accuracy"].notna().any():
                # Best by accuracy
                best_idx = config_df["accuracy"].idxmax()
                best_row = config_df.loc[best_idx]

                results.append(
                    {
                        "model": model,
                        "config": config_name,
                        "optimal_window": int(best_row["window_size"]),
                        "best_accuracy": best_row["accuracy"],
                        "best_auc": best_row.get("auc"),
                    }
                )

            elif config_df["ic"].notna().any():
                # Best by IC (regression)
                best_idx = config_df["ic"].idxmax()
                best_row = config_df.loc[best_idx]

                results.append(
                    {
                        "model": model,
                        "config": config_name,
                        "optimal_window": int(best_row["window_size"]),
                        "best_ic": best_row["ic"],
                        "best_rmse": best_row.get("rmse"),
                    }
                )

    return pd.DataFrame(results)


def print_summary(df: pd.DataFrame) -> None:
    """Print summary statistics."""

    print("\n" + "=" * 70)
    print("GRID SEARCH RESULTS SUMMARY")
    print("=" * 70)

    # Experiments loaded
    print(f"\nTotal experiments: {len(df)}")
    print(f"Models tested: {df['model'].unique().tolist()}")
    print(f"Windows tested: {sorted(df['window_size'].unique())}")
    print(f"Configs tested: {df['config_name'].nunique()}")

    # Find optimal windows
    optimal = find_optimal_windows(df)

    print("\n" + "-" * 50)
    print("OPTIMAL WINDOWS (by accuracy/IC)")
    print("-" * 50)

    for model in optimal["model"].unique():
        model_opt = optimal[optimal["model"] == model]

        print(f"\n{model.upper()}:")

        # Most common optimal window
        window_counts = model_opt["optimal_window"].value_counts()
        most_common = window_counts.index[0]
        count = window_counts.iloc[0]
        total = len(model_opt)

        print(f"  Most common optimal: {most_common} ({count}/{total} configs)")
        print(
            f"  Window range: {model_opt['optimal_window'].min()} - {model_opt['optimal_window'].max()}"
        )

        if "best_accuracy" in model_opt.columns:
            print(f"  Best accuracy: {model_opt['best_accuracy'].max():.4f}")

    # Overall recommendation
    print("\n" + "-" * 50)
    print("RECOMMENDED WINDOWS")
    print("-" * 50)

    for model in optimal["model"].unique():
        model_opt = optimal[optimal["model"] == model]
        recommended = int(model_opt["optimal_window"].median())
        print(f"  {model}: {recommended}")


def main():
    parser = argparse.ArgumentParser(description="Analyze window grid search results")
    parser.add_argument(
        "csv_files", nargs="+", help="CSV result files from grid search"
    )
    parser.add_argument(
        "--output-dir", type=str, default=None, help="Output directory for plots"
    )

    args = parser.parse_args()

    # Load data
    df = load_results(args.csv_files)

    if df.empty:
        print("No data loaded!")
        return

    # Output directory
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = (
            PROJECT_ROOT / "data" / "experiments" / "window_grid_search" / "analysis"
        )
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate analysis
    print_summary(df)

    if df["accuracy"].notna().any():
        plot_window_vs_accuracy(df, output_dir)
        plot_heatmap_accuracy(df, output_dir)
        plot_window_distribution(df, output_dir)

    # Save optimal windows
    optimal = find_optimal_windows(df)
    optimal_file = output_dir / "optimal_windows.csv"
    optimal.to_csv(optimal_file, index=False)
    print(f"\nOptimal windows saved: {optimal_file}")


if __name__ == "__main__":
    main()
