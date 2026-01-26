"""
Visualization Module
====================

Plotting utilities for analysis:
- Backtest performance charts
- Feature importance plots
- IC/ICIR visualizations
- Distribution analysis plots
"""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import config


def setup_plot_style():
    """Configure matplotlib style."""
    plt.style.use("seaborn-v0_8-whitegrid")
    plt.rcParams["figure.figsize"] = (14, 8)
    plt.rcParams["font.size"] = 11
    plt.rcParams["axes.titlesize"] = 14
    plt.rcParams["axes.labelsize"] = 12


def save_plot(fig: plt.Figure, name: str, dpi: int = 150):
    """Save figure to plots directory."""
    filepath = config.PLOTS_DIR / f"{name}.png"
    fig.savefig(filepath, dpi=dpi, bbox_inches="tight")
    print(f"Saved: {filepath}")
    return filepath


# =============================================================================
# BACKTEST PLOTS
# =============================================================================


def plot_backtest_results(
    results_df: pd.DataFrame,
    save: bool = True,
) -> plt.Figure:
    """
    Plot backtest results: PnL curve, direction probs, positions.

    Args:
        results_df: DataFrame from backtest.run_walk_forward()
        save: Save to file

    Returns:
        Figure object
    """
    setup_plot_style()
    fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True)

    timestamps = results_df["timestamp"]

    # PnL curve
    ax1 = axes[0]
    ax1.plot(timestamps, results_df["cumulative_pnl"], "b-", linewidth=1)
    ax1.axhline(y=0, color="k", linestyle="--", alpha=0.3)
    ax1.fill_between(
        timestamps,
        0,
        results_df["cumulative_pnl"],
        where=results_df["cumulative_pnl"] >= 0,
        alpha=0.3,
        color="green",
    )
    ax1.fill_between(
        timestamps,
        0,
        results_df["cumulative_pnl"],
        where=results_df["cumulative_pnl"] < 0,
        alpha=0.3,
        color="red",
    )
    ax1.set_ylabel("Cumulative PnL")
    ax1.set_title("Walk-Forward Backtest Results")
    ax1.grid(True, alpha=0.3)

    # Direction probability
    ax2 = axes[1]
    ax2.plot(timestamps, results_df["dir_prob"], "b.", alpha=0.3, markersize=2)
    ax2.axhline(y=0.5, color="k", linestyle="--", alpha=0.3)
    ax2.axhline(y=0.55, color="g", linestyle=":", alpha=0.5, label="Threshold")
    ax2.axhline(y=0.45, color="g", linestyle=":", alpha=0.5)
    ax2.set_ylabel("Direction Probability")
    ax2.set_ylim(0, 1)
    ax2.legend()
    ax2.grid(True, alpha=0.3)

    # Position size
    ax3 = axes[2]
    colors = [
        "green" if d == 1 else "red" if d == -1 else "gray"
        for d in results_df["position_dir"]
    ]
    ax3.bar(
        timestamps,
        results_df["position_size"] * results_df["position_dir"],
        color=colors,
        alpha=0.7,
        width=0.3,
    )
    ax3.set_ylabel("Position (+ long, - short)")
    ax3.set_xlabel("Date")
    ax3.grid(True, alpha=0.3)

    plt.tight_layout()

    if save:
        save_plot(fig, "walk_forward_backtest")

    return fig


def plot_pnl_analysis(results_df: pd.DataFrame, save: bool = True) -> plt.Figure:
    """Plot detailed PnL analysis: drawdown, returns distribution."""
    setup_plot_style()
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    returns = results_df["position_return"]
    cum_pnl = results_df["cumulative_pnl"]

    # Cumulative PnL
    ax1 = axes[0, 0]
    ax1.plot(cum_pnl.values, "b-", linewidth=1)
    ax1.set_title("Cumulative PnL")
    ax1.set_xlabel("Iteration")
    ax1.set_ylabel("PnL")
    ax1.grid(True, alpha=0.3)

    # Drawdown
    ax2 = axes[0, 1]
    running_max = (1 + cum_pnl).cummax()
    drawdown = ((1 + cum_pnl) - running_max) / running_max
    ax2.fill_between(range(len(drawdown)), 0, drawdown.values, color="red", alpha=0.5)
    ax2.set_title("Drawdown")
    ax2.set_xlabel("Iteration")
    ax2.set_ylabel("Drawdown")
    ax2.grid(True, alpha=0.3)

    # Returns distribution
    ax3 = axes[1, 0]
    ax3.hist(returns.values, bins=50, alpha=0.7, edgecolor="black")
    ax3.axvline(x=0, color="r", linestyle="--", alpha=0.7)
    ax3.axvline(
        x=returns.mean(),
        color="g",
        linestyle="-",
        alpha=0.7,
        label=f"Mean: {returns.mean():.4f}",
    )
    ax3.set_title("Returns Distribution")
    ax3.set_xlabel("Return")
    ax3.legend()
    ax3.grid(True, alpha=0.3)

    # Rolling Sharpe
    ax4 = axes[1, 1]
    window = 50
    rolling_mean = returns.rolling(window).mean()
    rolling_std = returns.rolling(window).std()
    rolling_sharpe = (rolling_mean / rolling_std) * np.sqrt(3 * 365)  # Annualized
    ax4.plot(rolling_sharpe.values, "b-", linewidth=1)
    ax4.axhline(y=0, color="k", linestyle="--", alpha=0.3)
    ax4.set_title(f"Rolling Sharpe ({window} bars)")
    ax4.set_xlabel("Iteration")
    ax4.set_ylabel("Sharpe Ratio")
    ax4.grid(True, alpha=0.3)

    plt.tight_layout()

    if save:
        save_plot(fig, "pnl_analysis")

    return fig


# =============================================================================
# FEATURE IMPORTANCE PLOTS
# =============================================================================


def plot_feature_importance(
    importances: pd.DataFrame,
    top_n: int = 30,
    save: bool = True,
) -> plt.Figure:
    """
    Plot feature importance bar chart.

    Args:
        importances: DataFrame with 'feature' and 'importance' columns
        top_n: Number of top features to show
        save: Save to file
    """
    setup_plot_style()
    fig, ax = plt.subplots(figsize=(10, 8))

    top_features = importances.head(top_n)

    ax.barh(range(len(top_features)), top_features["importance"].values)
    ax.set_yticks(range(len(top_features)))
    ax.set_yticklabels(top_features["feature"].values)
    ax.invert_yaxis()
    ax.set_xlabel("Importance")
    ax.set_title(f"Top {top_n} Features by Importance")

    plt.tight_layout()

    if save:
        save_plot(fig, "feature_importance")

    return fig


def plot_importance_by_domain(
    importances: pd.DataFrame,
    save: bool = True,
) -> plt.Figure:
    """Plot aggregated importance by feature domain."""
    setup_plot_style()

    if "domain" not in importances.columns:
        from . import features

        importances = importances.copy()
        importances["domain"] = [
            features.classify_feature_domain(f) for f in importances["feature"]
        ]

    domain_importance = (
        importances.groupby("domain")["importance"].sum().sort_values(ascending=True)
    )

    fig, ax = plt.subplots(figsize=(10, 6))
    domain_importance.plot(kind="barh", ax=ax)
    ax.set_xlabel("Total Importance")
    ax.set_title("Feature Importance by Domain")

    plt.tight_layout()

    if save:
        save_plot(fig, "importance_by_domain")

    return fig


# =============================================================================
# IC/ICIR PLOTS
# =============================================================================


def plot_ic_analysis(
    ic_results: pd.DataFrame,
    top_n: int = 20,
    save: bool = True,
) -> plt.Figure:
    """
    Plot IC analysis results.

    Args:
        ic_results: DataFrame from features.compute_ic_analysis()
        top_n: Number of top features to show
    """
    setup_plot_style()
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    top_features = ic_results.head(top_n)

    # IC values
    ax1 = axes[0]
    colors = ["green" if ic > 0 else "red" for ic in top_features["ic"]]
    ax1.barh(range(len(top_features)), top_features["ic"].values, color=colors)
    ax1.set_yticks(range(len(top_features)))
    ax1.set_yticklabels(top_features["feature"].values)
    ax1.invert_yaxis()
    ax1.axvline(x=0, color="k", linestyle="-", alpha=0.3)
    ax1.set_xlabel("Information Coefficient (IC)")
    ax1.set_title(f"Top {top_n} Features by |IC|")

    # Significance
    ax2 = axes[1]
    significant = top_features[top_features["is_significant"]]
    not_significant = top_features[~top_features["is_significant"]]

    ax2.scatter(
        significant["ic"],
        significant["hit_rate"],
        c="green",
        label=f"Significant ({len(significant)})",
        alpha=0.7,
        s=50,
    )
    ax2.scatter(
        not_significant["ic"],
        not_significant["hit_rate"],
        c="gray",
        label=f"Not significant ({len(not_significant)})",
        alpha=0.5,
        s=30,
    )
    ax2.axhline(y=0.5, color="k", linestyle="--", alpha=0.3)
    ax2.axvline(x=0, color="k", linestyle="--", alpha=0.3)
    ax2.set_xlabel("IC")
    ax2.set_ylabel("Hit Rate")
    ax2.set_title("IC vs Hit Rate")
    ax2.legend()

    plt.tight_layout()

    if save:
        save_plot(fig, "ic_analysis")

    return fig


# =============================================================================
# DISTRIBUTION PLOTS
# =============================================================================


def plot_target_distributions(df: pd.DataFrame, save: bool = True) -> plt.Figure:
    """Plot distribution of target variables."""
    setup_plot_style()
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))

    # Direction class balance
    ax1 = axes[0, 0]
    direction_counts = df["y_direction"].value_counts()
    ax1.bar(
        ["Down (0)", "Up (1)"],
        direction_counts.values,
        color=["red", "green"],
        alpha=0.7,
    )
    ax1.set_title("Direction Class Balance")
    ax1.set_ylabel("Count")

    # Volatility distribution
    ax2 = axes[0, 1]
    vol = df["y_volatility"].dropna()
    ax2.hist(vol.values, bins=50, alpha=0.7, edgecolor="black")
    ax2.axvline(
        x=vol.median(), color="r", linestyle="--", label=f"Median: {vol.median():.4f}"
    )
    ax2.set_title("Volatility Distribution")
    ax2.set_xlabel("|Forward Return|")
    ax2.legend()

    # Forward returns
    ax3 = axes[1, 0]
    ret = df["y_forward_return_1"].dropna()
    ax3.hist(ret.values, bins=50, alpha=0.7, edgecolor="black")
    ax3.axvline(x=0, color="r", linestyle="--")
    ax3.set_title("Forward Return (8h) Distribution")
    ax3.set_xlabel("Return")

    # Vol spike distribution
    ax4 = axes[1, 1]
    spike_counts = df["y_vol_spike"].value_counts().sort_index()
    labels = ["NO_SPIKE", "SPIKE"]
    ax4.bar(labels, spike_counts.values, color=["green", "red"], alpha=0.7)
    ax4.set_title("Volatility Spike Distribution")
    ax4.set_ylabel("Count")

    plt.tight_layout()

    if save:
        save_plot(fig, "target_distributions")

    return fig
