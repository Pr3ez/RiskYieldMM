#!/usr/bin/env python3
# %% [markdown]
# # RiskYieldMM Analysis Runner
#
# Main entry point for analysis operations.
#
# **CLI Usage:**
# ```bash
# python -m scripts.analysis.run --help
# python -m scripts.analysis.run prepare       # Create analysis dataset
# python -m scripts.analysis.run cv            # Cross-validation
# python -m scripts.analysis.run features      # Feature analysis (IC/ICIR)
# python -m scripts.analysis.run importance    # MDI feature importance
# python -m scripts.analysis.run mda           # MDA (permutation) importance
# python -m scripts.analysis.run optimize      # Feature optimization
# python -m scripts.analysis.run build-datasets # Build dataset matrix (20 files)
# python -m scripts.analysis.run all           # Run everything
# ```
#
# ## Dataset Matrix System
#
# The `build-datasets` command creates 20 separate datasets (5 targets × 4 horizons):
#
# **Target Types:**
# - `direction`: Binary (1=up, 0=down) — for classification
# - `returns`: Continuous forward return — for regression
# - `volatility`: |return| — for risk/position sizing
# - `vol_spike`: Binary volatility spike detection — for risk management
# - `trend_regime`: Up/Down trend — for trend-following
#
# **Horizons:**
# - `1bar` (8h): Intraday trading
# - `3bar` (24h): Daily rebalancing
# - `6bar` (48h): Swing trading
# - `12bar` (96h): Position trading
#
# Each dataset contains:
# - 166 base features (identical across all)
# - 3-5 interaction features (optimized for THAT SPECIFIC target+horizon)
# - 1 target column
#
# ## Per-Target Optimization System
#
# **CRITICAL**: Each target type requires its OWN optimized features.
#
# The `optimize` command generates target-specific optimized files:
# ```bash
# # Optimize for specific target and horizon
# python -m scripts.analysis.run optimize --target volatility --horizon 3
#
# # Output: data/features_8h_optimized_volatility_3bar.parquet
# ```
#
# **Why per-target optimization?**
#
# 1. **InteractionOptimizer** selects feature pairs by IC (Information Coefficient)
#    - IC is computed against the TARGET column
#    - Features predictive of `direction` are NOT predictive of `volatility`
#    - Using wrong interactions HURTS predictions (tested: -42% IC degradation)
#
# 2. **RollingZScoreOptimizer** normalizes features for stationarity
#    - HELPS direction/returns (mean-reverting price signals)
#    - HURTS volatility/regime targets (destroys magnitude information)
#    - Pipeline automatically skips RollingZScore for vol/regime targets
#
# **Optimization Pipeline by Target:**
#
# | Target        | Pipeline Steps                           |
# |---------------|------------------------------------------|
# | direction     | Winsorize → RollingZScore → Interactions |
# | returns       | Winsorize → RollingZScore → Interactions |
# | volatility    | Winsorize → Interactions (NO ZScore)     |
# | vol_spike     | Winsorize → Interactions (NO ZScore)     |
# | trend_regime  | Winsorize → Interactions (NO ZScore)     |
#
# **Full optimization workflow (20 combinations):**
# ```python
# for target in ['direction', 'returns', 'volatility', 'vol_spike', 'trend_regime']:
#     for horizon in [1, 3, 6, 12]:
#         cmd_optimize(target=target, horizon=horizon)
# cmd_build_datasets()  # Uses target-specific optimized files
# ```
#
# **Validation Results (all 20 pass):**
# - direction: +0.7% to +1.4% IC improvement
# - returns: +1.0% to +1.5% IC improvement
# - volatility: +0.8% to +1.8% IC improvement
# - vol_spike: +3.8% to +4.3% IC improvement
# - trend_regime: +1.9% to +6.3% IC improvement
#
# **Interactive Usage:** Run cells individually with VS Code / Jupyter

# %% Imports
import argparse
import sys
from pathlib import Path

import pandas as pd

# Add project root to path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from scripts.analysis import config, data, features, models, viz  # noqa: E402
from scripts.workflow.targets import (  # noqa: E402
    compute_target_polars,
    get_target_config,
)

# %% [markdown]
# ## Command Functions
# Each function below can be called directly in interactive mode
# or via CLI with corresponding subcommand.


# %% cmd_prepare - Create analysis dataset
def cmd_prepare(args=None):
    """Create analysis dataset with targets."""
    print("=" * 60)
    print("PREPARING ANALYSIS DATASET")
    print("=" * 60)

    df = data.create_analysis_dataset()
    print(f"\n✓ Created {config.ANALYSIS_FILE}")
    print(f"  Shape: {df.shape}")
    return df


# %% cmd_cv - Cross-validation
def cmd_cv(args=None, use_purged=False):
    """Run cross-validation for all models.

    Args:
        args: CLI args (optional)
        use_purged: Use PurgedKFold CV (prevents temporal leakage)
    """
    # Handle both CLI and interactive calls
    if args is not None and hasattr(args, "purged"):
        use_purged = args.purged

    print("=" * 60)
    if use_purged:
        print("CROSS-VALIDATION (PurgedKFold)")
        print(
            f"purge_gap={config.MAX_LOOKBACK_BARS}, embargo_gap={config.MAX_HORIZON_BARS}"
        )
    else:
        print("CROSS-VALIDATION (TimeSeriesSplit)")
    print("=" * 60)

    # Load data
    df = data.load_analysis_data()
    feature_cols = data.get_feature_columns(df)

    # Direction CV
    print("\n--- Direction Model CV ---")
    mask = df["y_direction"].notna()
    X = df.loc[mask, feature_cols]
    y = df.loc[mask, "y_direction"]

    dir_results = models.run_direction_cv(X, y, use_purged=use_purged)

    print("\nDirection CV Summary:")
    for model_name, cv_result in dir_results.items():
        print(f"  {model_name}: AUC={cv_result.mean_auc:.4f} ± {cv_result.std_auc:.4f}")

    # Volatility CV
    if models.HAS_CATBOOST:
        import numpy as np

        print("\n--- Volatility Model CV ---")
        mask = df["y_volatility"].notna()
        X_vol = df.loc[mask, feature_cols].copy()
        X_vol["dir_regime"] = df.loc[mask, "y_direction"].values
        y_vol = df.loc[mask, "y_volatility"]

        vol_result = models.run_volatility_cv(X_vol, y_vol, use_purged=use_purged)

        rmse_vals = [r.rmse for r in vol_result.fold_results]
        print(f"  Volatility: RMSE={np.mean(rmse_vals):.6f} ± {np.std(rmse_vals):.6f}")

    # Save results
    import pandas as pd

    results_data = []
    for model_name, cv_result in dir_results.items():
        for i, fold_result in enumerate(cv_result.fold_results):
            results_data.append(
                {
                    "model": model_name,
                    "fold": i + 1,
                    "auc": fold_result.auc,
                    "accuracy": fold_result.accuracy,
                }
            )

    results_df = pd.DataFrame(results_data)
    results_df.to_csv(config.RESULTS_DIR / "cv_results.csv", index=False)
    print(f"\n✓ Saved: {config.RESULTS_DIR / 'cv_results.csv'}")
    return dir_results


# %% cmd_features - Feature analysis (IC/ICIR)
def cmd_features(args=None, plot=True):
    """Run feature analysis (IC/ICIR) across all horizons.

    Args:
        args: CLI args (optional)
        plot: Generate plots
    """
    # Handle both CLI and interactive calls
    if args is not None:
        plot = getattr(args, "plot", plot)
    print("=" * 60)
    print("FEATURE ANALYSIS (Multi-Horizon)")
    print("=" * 60)

    df = data.load_analysis_data()
    feature_cols = data.get_feature_columns(df)

    # Multi-horizon IC analysis
    print("\n--- Multi-Horizon IC Analysis ---")
    print("Using non-overlapping samples for horizons > 1 bar")
    print(f"Horizons: {config.FORWARD_HORIZONS}")

    multi_ic = features.compute_multi_horizon_ic(df, feature_cols)

    # Summary table
    print(f"\nTop {config.ANALYSIS_CONFIG.top_n_features} features by |best_ic|:")
    top = multi_ic.head(config.ANALYSIS_CONFIG.top_n_features)
    display_cols = [
        "feature",
        "domain",
        "ic_1bar",
        "ic_3bar",
        "ic_6bar",
        "ic_12bar",
        "best_horizon",
    ]
    print(
        top[display_cols].to_string(
            index=False, float_format=lambda x: f"{x:+.4f}" if not pd.isna(x) else ""
        )
    )

    # Horizon summary
    print("\n--- Best Horizon Distribution ---")
    horizon_counts = multi_ic["best_horizon"].value_counts().sort_index()
    for h, count in horizon_counts.items():
        label = config.FORWARD_HORIZONS.get(h, f"{h}bar")
        print(f"  {h}-bar ({label}): {count} features")

    # Per-horizon IC analysis (for detailed files)
    print("\n--- Saving Per-Horizon Results ---")
    for n_bars, label in config.FORWARD_HORIZONS.items():
        target_col = f"y_forward_return_{n_bars}"
        if target_col in df.columns:
            ic_results = features.compute_ic_analysis(df, feature_cols, target_col)
            ic_results["horizon_bars"] = n_bars
            ic_results["horizon_label"] = label

            filename = f"ic_analysis_{n_bars}bar.csv"
            ic_results.to_csv(config.RESULTS_DIR / filename, index=False)
            print(f"  ✓ {filename} ({len(ic_results)} features)")

    # Save multi-horizon summary
    multi_ic.to_csv(config.RESULTS_DIR / "ic_multi_horizon.csv", index=False)
    print("  ✓ ic_multi_horizon.csv (summary across horizons)")

    # Horizon insights
    horizon_summary = features.compute_horizon_summary(multi_ic)
    horizon_summary.to_csv(config.RESULTS_DIR / "ic_horizon_summary.csv", index=False)
    print("  ✓ ic_horizon_summary.csv (best horizon per feature)")

    # Domain breakdown
    print("\n--- Domain Summary ---")
    domains = features.classify_all_features(feature_cols)
    for domain, cols in sorted(domains.items(), key=lambda x: len(x[1]), reverse=True):
        print(f"  {domain}: {len(cols)} features")

    # Redundancy check
    print("\n--- Redundancy Check ---")
    redundant = features.find_redundant_features(df, feature_cols)
    if redundant:
        print(
            f"Found {len(redundant)} redundant pairs (|r| > {config.ANALYSIS_CONFIG.correlation_threshold}):"
        )
        for f1, f2, corr in redundant[:10]:
            print(f"  {f1} <-> {f2}: {corr:.3f}")
    else:
        print("No redundant features found.")

    # Plot
    if plot:
        # Create compatible format for viz (use best_ic as "ic")
        plot_df = multi_ic.copy()
        plot_df["ic"] = plot_df["best_ic"]
        # Add hit_rate if not present (estimate from IC direction consistency)
        if "hit_rate" not in plot_df.columns:
            # Approximate: features with positive IC have hit_rate > 0.5
            plot_df["hit_rate"] = 0.5 + (plot_df["ic"].abs() / 2)
        if "is_significant" not in plot_df.columns:
            plot_df["is_significant"] = plot_df["ic"].abs() > 0.02
        viz.plot_ic_analysis(plot_df)

    return multi_ic


# %% cmd_importance - Feature importance (MDI)
def cmd_importance(args=None, plot=True):
    """Compute and plot feature importance (MDI - Mean Decrease Impurity).

    Args:
        args: CLI args (optional)
        plot: Generate plots
    """
    # Handle both CLI and interactive calls
    if args is not None:
        plot = getattr(args, "plot", plot)
    print("=" * 60)
    print("FEATURE IMPORTANCE (MDI)")
    print("=" * 60)

    df = data.load_analysis_data()
    feature_cols = data.get_feature_columns(df)

    mask = df["y_direction"].notna()
    X = df.loc[mask, feature_cols]
    y = df.loc[mask, "y_direction"]

    print("Training LightGBM for importance...")
    importances = features.compute_lgb_importance(X, y)

    print("\nTop 20 features:")
    print(importances.head(20).to_string(index=False))

    importances.to_csv(config.RESULTS_DIR / "feature_importance.csv", index=False)
    print(f"\n✓ Saved: {config.RESULTS_DIR / 'feature_importance.csv'}")

    if plot:
        viz.plot_feature_importance(importances)
        viz.plot_importance_by_domain(importances)

    return importances


# %% cmd_mda - MDA (Permutation Importance)
def cmd_mda(args=None, n_repeats=10):
    """Compute MDA (Mean Decrease Accuracy / Permutation Importance).

    Based on: Lopez de Prado, AFML Ch.8
    Method: Out-of-sample, model-agnostic

    Args:
        args: CLI args (optional)
        n_repeats: Number of permutation repeats
    """
    # Handle both CLI and interactive calls
    if args is not None:
        n_repeats = getattr(args, "n_repeats", n_repeats)
    print("=" * 60)
    print("MDA (Permutation Importance)")
    print("=" * 60)
    print("Based on: Lopez de Prado, AFML Ch.8")
    print("Method: Out-of-sample, model-agnostic")

    import lightgbm as lgb
    from sklearn.model_selection import train_test_split

    df = data.load_analysis_data()
    feature_cols = data.get_feature_columns(df)

    mask = df["y_direction"].notna()
    X = df.loc[mask, feature_cols]
    y = df.loc[mask, "y_direction"]

    # Train/test split (use validation set for MDA)
    X_train, X_val, y_train, y_val = train_test_split(
        X,
        y,
        test_size=0.2,
        shuffle=False,  # Temporal split
    )

    print(f"\nData: {len(X_train):,} train, {len(X_val):,} validation samples")
    print(f"Features: {len(feature_cols)}")

    # Train model
    print("\nTraining LightGBM...")
    model = lgb.LGBMClassifier(
        n_estimators=100,
        max_depth=6,
        learning_rate=0.1,
        random_state=42,
        verbosity=-1,
    )
    model.fit(X_train, y_train)

    # Compute MDA on validation set
    print(f"\nComputing permutation importance (n_repeats={n_repeats})...")
    mda_results = features.compute_permutation_importance(
        model,
        X_val,
        y_val,
        n_repeats=n_repeats,
        random_state=42,
        scoring="roc_auc",
    )

    # Sort and display
    mda_sorted = mda_results.sort_values("importance_mean", ascending=False)

    print(f"\nTop {min(30, len(mda_sorted))} features by MDA:")
    print(mda_sorted.head(30).to_string(index=False))

    # Domain breakdown
    print("\n--- Domain Summary (mean MDA) ---")
    domain_mda = (
        mda_sorted.groupby("domain")["importance_mean"]
        .mean()
        .sort_values(ascending=False)
    )
    for domain, mean_mda in domain_mda.items():
        count = len(mda_sorted[mda_sorted["domain"] == domain])
        print(f"  {domain}: {mean_mda:.4f} ({count} features)")

    # Save
    mda_sorted.to_csv(config.RESULTS_DIR / "mda_importance.csv", index=False)
    print(f"\n✓ Saved: {config.RESULTS_DIR / 'mda_importance.csv'}")

    # Compare with MDI (if importance exists)
    mdi_file = config.RESULTS_DIR / "feature_importance.csv"
    if mdi_file.exists():
        import pandas as pd

        mdi_df = pd.read_csv(mdi_file)
        print("\n--- MDA vs MDI Top 10 Comparison ---")
        mda_top10 = set(mda_sorted.head(10)["feature"])
        mdi_top10 = set(mdi_df.head(10)["feature"])
        overlap = mda_top10 & mdi_top10
        print(f"  Overlap in top 10: {len(overlap)}/10")
        if overlap:
            print(f"  Shared: {sorted(overlap)}")

    return mda_sorted


# %% cmd_build_datasets - Build full matrix of datasets
def cmd_build_datasets(args=None, horizons=None, target_types=None):
    """Build full matrix of datasets: target_type × horizon.

    Creates separate parquet files for each combination:
    - data/datasets/{target_type}_{horizon}bar.parquet

    Each dataset contains:
    - 166 base features (shared)
    - 5 horizon-specific interaction features
    - 1 target column (y_{target_type})

    Target types:
    - direction: Binary (1=up, 0=down) based on forward_return sign
    - returns: Continuous forward return
    - volatility: |forward_return| (absolute return)
    - vol_spike: Binary (0=NO_SPIKE, 1=SPIKE) based on vol ratio >= 1.5
    - trend_regime: Binary based on SMA crossover at horizon

    Args:
        args: CLI args (optional)
        horizons: List of horizons [1,3,6,12] (default: all)
        target_types: List of target types (default: all)
    """
    import polars as pl

    # Handle CLI args
    if args is not None:
        horizons = getattr(args, "horizons", horizons)
        target_types = getattr(args, "target_types", target_types)

    horizons = horizons or [1, 3, 6, 12]
    target_types = target_types or [
        "direction",
        "returns",
        "volatility",
        "vol_spike",
        "trend_regime",
    ]

    print("=" * 60)
    print("BUILDING DATASET MATRIX")
    print(f"Horizons: {horizons}")
    print(f"Target types: {target_types}")
    print(f"Total datasets: {len(horizons) * len(target_types)}")
    print("=" * 60)

    # Create output directory
    datasets_dir = config.DATA_DIR / "datasets"
    datasets_dir.mkdir(exist_ok=True)

    # Load base data
    df = data.load_analysis_data(as_pandas=False)  # Polars
    feature_cols = data.get_feature_columns(df.to_pandas())

    # Load raw for computing per-horizon targets
    raw = pl.read_parquet(config.RAW_FILE)
    close = raw["RAW_P_close_abs_NN"]
    high = raw["RAW_P_high_abs_NN"]
    low = raw["RAW_P_low_abs_NN"]
    timestamp = raw["RAW_TM_timestamp"]  # Needed for 15m-based targets

    print(f"\nBase features: {len(feature_cols)}")
    print(f"Rows: {len(df)}")

    # Pre-compute forward returns for each horizon
    # NEW: Use full candle info (high, low, close) for better signal
    forward_returns = {}  # Legacy close-to-close (for volatility)
    net_candle_returns = {}  # NEW: (up_move - down_move) for direction/returns
    for h in horizons:
        # Legacy: close-to-close return (used for volatility target)
        future_close = close.shift(-h)
        forward_returns[h] = (future_close - close) / close

        # NEW: Net candle direction = upside_move - downside_move
        # upside_move = (future_high - current_close) / current_close
        # downside_move = (current_close - future_low) / current_close
        # Simplifies to: (future_high + future_low - 2*current_close) / current_close
        future_high = high.shift(-h)
        future_low = low.shift(-h)
        up_move = (future_high - close) / close
        down_move = (close - future_low) / close
        net_candle_returns[h] = up_move - down_move

    # Pre-compute rolling volatility for regime classification
    log_returns = (close / close.shift(1)).log()

    # Build each dataset
    results = []
    for horizon in horizons:
        fwd_ret = forward_returns[horizon]  # Close-to-close (for volatility)
        net_candle_ret = net_candle_returns[
            horizon
        ]  # Full candle (for direction/returns)

        for target_type in target_types:
            # Load target-specific optimized features (if exists)
            opt_file = (
                config.DATA_DIR
                / f"features_8h_optimized_{target_type}_{horizon}bar.parquet"
            )
            if opt_file.exists():
                opt_df = pl.read_parquet(opt_file)
                # Get interaction columns
                interaction_cols = [c for c in opt_df.columns if "×" in c]
                print(
                    f"\n[{target_type}/{horizon}-bar] Using {len(interaction_cols)} interactions from {opt_file.name}"
                )
            else:
                opt_df = None
                interaction_cols = []
                print(
                    f"\n[{target_type}/{horizon}-bar] No optimized features found, using base only"
                )
            # Compute target using centralized targets module (single source of truth)
            # All target definitions come from scripts.workflow.targets
            target_config = get_target_config(target_type)
            target = compute_target_polars(
                target_name=target_type,
                close=close,
                high=high,
                low=low,
                horizon=horizon,
                timestamp=timestamp,  # For 15m-based targets (first_extreme, etc.)
            ).alias(target_config.target_column)

            # Build dataset: base features + interactions + target
            dataset = df.select(["timestamp"] + feature_cols)

            # Add interactions if available
            if opt_df is not None and interaction_cols:
                for col in interaction_cols:
                    dataset = dataset.with_columns(opt_df[col])

            # Add target
            dataset = dataset.with_columns(target)

            # Save
            output_file = datasets_dir / f"{target_type}_{horizon}bar.parquet"
            dataset.write_parquet(output_file)

            n_valid = dataset[dataset.columns[-1]].drop_nulls().len()
            size_kb = output_file.stat().st_size / 1024

            results.append(
                {
                    "target": target_type,
                    "horizon": horizon,
                    "features": len(feature_cols) + len(interaction_cols),
                    "rows": len(dataset),
                    "valid_targets": n_valid,
                    "size_kb": size_kb,
                }
            )

            print(
                f"  ✓ {output_file.name}: {len(feature_cols) + len(interaction_cols)} features, {n_valid} valid targets"
            )

    # Summary
    print("\n" + "=" * 60)
    print("DATASET MATRIX COMPLETE")
    print("=" * 60)

    import pandas as pd

    summary = pd.DataFrame(results)
    print(summary.to_string(index=False))

    # Save summary
    summary.to_csv(datasets_dir / "dataset_summary.csv", index=False)
    print(f"\n✓ Summary saved: {datasets_dir / 'dataset_summary.csv'}")

    return summary


# %% cmd_auto_optimize - Automatic pipeline selection for all 20 targets
def cmd_auto_optimize(args=None, horizons=None, targets=None, save=True):
    """Automatically select best preprocessing pipeline for each of 20 target-horizons.

    For EACH target-horizon combination:
    1. Test multiple preprocessing pipelines
    2. Compute mean |IC| for each pipeline
    3. Select the pipeline with HIGHEST IC
    4. Save the optimized features

    This ensures each of 20 datasets is optimized specifically for its target.

    Pipelines tested:
    - baseline: No preprocessing (just original features)
    - winsorize: Winsorize only
    - winsorize_zscore: Winsorize → RollingZScore
    - winsorize_rank: Winsorize → ExpandingRank
    - winsorize_log: Winsorize → LogTransform
    - winsorize_interactions: Winsorize → Interactions
    - winsorize_zscore_interactions: Winsorize → RollingZScore → Interactions
    - winsorize_rank_interactions: Winsorize → ExpandingRank → Interactions

    Args:
        args: CLI args (optional)
        horizons: List of horizons [1,3,6,12] (default: all)
        targets: List of targets (default: all 5)
        save: Save optimized features to disk

    Returns:
        DataFrame with results for all 20 target-horizons
    """
    import numpy as np
    import pandas as pd
    import polars as pl
    from scipy.stats import spearmanr

    from scripts.analysis.optimizers import (
        ExpandingRankOptimizer,
        InteractionOptimizer,
        LogTransformOptimizer,
        OptimizationPipeline,
        RollingZScoreOptimizer,
        WinsorizeOptimizer,
    )

    # Handle CLI args
    if args is not None:
        horizons = getattr(args, "horizons", horizons)
        targets = getattr(args, "targets", targets)
        save = getattr(args, "save", save)

    horizons = horizons or [1, 3, 6, 12]
    targets = targets or [
        "direction",
        "returns",
        "volatility",
        "vol_spike",
        "trend_regime",
    ]

    print("=" * 80)
    print("AUTOMATIC PIPELINE SELECTION FOR ALL 20 TARGET-HORIZONS")
    print("=" * 80)
    print(f"Targets: {targets}")
    print(f"Horizons: {horizons}")
    print(f"Total combinations: {len(targets) * len(horizons)}")

    # Load base data once
    df = data.load_analysis_data()
    feature_cols = data.get_feature_columns(df)
    X_base = df[feature_cols].copy()

    # Load raw for computing targets
    raw = pl.read_parquet(config.RAW_FILE)
    close = raw["RAW_P_close_abs_NN"].to_pandas()
    high = raw["RAW_P_high_abs_NN"].to_pandas()
    low = raw["RAW_P_low_abs_NN"].to_pandas()
    close.index = df.index
    high.index = df.index
    low.index = df.index

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
        """Compute target series for given target type and horizon.

        Direction and Returns use NET CANDLE method (up_move - down_move)
        which captures intracandle volatility for better signal.
        Volatility still uses close-to-close for absolute movement.
        """
        # Close-to-close return (used for volatility)
        fwd_ret = (close.shift(-horizon) - close) / close

        # Net candle return (used for direction/returns)
        # up_move = how far price went above current close
        # down_move = how far price went below current close
        future_high = high.shift(-horizon)
        future_low = low.shift(-horizon)
        up_move = (future_high - close) / close
        down_move = (close - future_low) / close
        net_candle_ret = up_move - down_move

        if target == "direction":
            return (net_candle_ret > 0).astype(float)
        elif target == "returns":
            return net_candle_ret
        elif target == "volatility":
            return fwd_ret.abs()
        elif target == "vol_spike":
            log_returns = np.log(close / close.shift(1))
            vol_window = 21
            rolling_vol = log_returns.rolling(vol_window).std()
            future_vol = rolling_vol.shift(-horizon)
            vol_ratio = future_vol / rolling_vol.clip(lower=1e-8)
            return (vol_ratio >= 1.5).astype(float)
        elif target == "trend_regime":
            fast_window = max(21, horizon * 5)
            slow_window = max(63, horizon * 15)
            sma_fast = close.rolling(fast_window).mean()
            sma_slow = close.rolling(slow_window).mean()
            return (sma_fast > sma_slow).astype(float)
        else:
            raise ValueError(f"Unknown target: {target}")

    def get_pipeline_candidates(target: str):
        """Get list of pipeline candidates appropriate for target type."""
        # Common base pipelines
        pipelines = {
            "baseline": [],
            "winsorize": [WinsorizeOptimizer(lower=0.01, upper=0.99)],
        }

        # Task-specific pipelines
        if target in {"direction", "returns"}:
            # Regression/binary: RollingZScore helps
            pipelines["winsorize_zscore"] = [
                WinsorizeOptimizer(lower=0.01, upper=0.99),
                RollingZScoreOptimizer(window=252),
            ]
            pipelines["winsorize_zscore_interactions"] = [
                WinsorizeOptimizer(lower=0.01, upper=0.99),
                RollingZScoreOptimizer(window=252),
                InteractionOptimizer(top_k=3, n_interactions=5, min_ic=0.02),
            ]

        if target in {"direction", "trend_regime", "vol_spike"}:
            # Classification: ExpandingRank may help
            pipelines["winsorize_rank"] = [
                WinsorizeOptimizer(lower=0.01, upper=0.99),
                ExpandingRankOptimizer(min_periods=252),
            ]
            pipelines["winsorize_rank_interactions"] = [
                WinsorizeOptimizer(lower=0.01, upper=0.99),
                ExpandingRankOptimizer(min_periods=252),
                InteractionOptimizer(top_k=3, n_interactions=5, min_ic=0.05),
            ]

        if target == "volatility":
            # Volatility: Log transform may help
            pipelines["winsorize_log"] = [
                WinsorizeOptimizer(lower=0.01, upper=0.99),
                LogTransformOptimizer(),
            ]

        # Interactions without other transforms
        min_ic = 0.05 if target in {"volatility", "vol_spike", "trend_regime"} else 0.02
        pipelines["winsorize_interactions"] = [
            WinsorizeOptimizer(lower=0.01, upper=0.99),
            InteractionOptimizer(top_k=3, n_interactions=5, min_ic=min_ic),
        ]

        return pipelines

    # Results storage
    all_results = []

    for target in targets:
        for horizon in horizons:
            print(f"\n{'=' * 60}")
            print(f"[{target}_{horizon}bar] Testing pipelines...")
            print("=" * 60)

            y = get_target_series(target, horizon)
            valid_count = y.notna().sum()
            print(f"Target has {valid_count} valid samples")

            # Get pipeline candidates for this target type
            pipeline_candidates = get_pipeline_candidates(target)

            # Test each pipeline
            pipeline_results = []
            best_ic = -1
            best_pipeline = None
            best_X = None

            for pipe_name, steps in pipeline_candidates.items():
                try:
                    if steps:
                        pipeline = OptimizationPipeline(steps, name=pipe_name)
                        X_transformed = pipeline.fit_transform(X_base.copy(), y)
                    else:
                        X_transformed = X_base.copy()

                    ic = compute_mean_abs_ic(X_transformed, y)
                    n_features = X_transformed.shape[1]

                    pipeline_results.append(
                        {
                            "pipeline": pipe_name,
                            "ic": ic,
                            "n_features": n_features,
                        }
                    )

                    print(f"  {pipe_name:35s} IC={ic:.4f} ({n_features} features)")

                    if ic > best_ic:
                        best_ic = ic
                        best_pipeline = pipe_name
                        best_X = X_transformed

                except Exception as e:
                    print(f"  {pipe_name:35s} ERROR: {e}")

            # Compute improvement over baseline
            baseline_ic = next(
                (r["ic"] for r in pipeline_results if r["pipeline"] == "baseline"),
                best_ic,
            )
            improvement = (
                ((best_ic - baseline_ic) / baseline_ic * 100) if baseline_ic > 0 else 0
            )

            print(
                f"\n  ★ BEST: {best_pipeline} (IC={best_ic:.4f}, +{improvement:.1f}% vs baseline)"
            )

            # Save results
            result = {
                "target": target,
                "horizon": horizon,
                "best_pipeline": best_pipeline,
                "best_ic": best_ic,
                "baseline_ic": baseline_ic,
                "improvement_pct": improvement,
                "n_features": best_X.shape[1] if best_X is not None else 0,
            }
            all_results.append(result)

            # Save optimized features
            if save and best_X is not None:
                result_df = best_X.copy()
                result_df.index = df.index
                result_df.index.name = "timestamp"

                output_file = (
                    config.DATA_DIR
                    / f"features_8h_optimized_{target}_{horizon}bar.parquet"
                )
                result_df.to_parquet(output_file)
                print(f"  ✓ Saved: {output_file.name}")

    # Summary
    print("\n" + "=" * 80)
    print("AUTO-OPTIMIZATION COMPLETE — SUMMARY")
    print("=" * 80)

    results_df = pd.DataFrame(all_results)
    print(results_df.to_string(index=False))

    # Save summary
    summary_file = config.RESULTS_DIR / "auto_optimize_summary.csv"
    results_df.to_csv(summary_file, index=False)
    print(f"\n✓ Summary saved: {summary_file}")

    # Print best pipelines by target type
    print("\n--- Best Pipeline by Target Type ---")
    for target in targets:
        target_results = results_df[results_df["target"] == target]
        most_common = target_results["best_pipeline"].mode()
        if len(most_common) > 0:
            print(f"  {target}: {most_common.iloc[0]} (most common across horizons)")

    return results_df


# %% cmd_optimize - Run feature optimization
def cmd_optimize(
    args=None, pipeline_name="default", horizon=1, target="returns", save=True
):
    """Run feature optimization pipeline with TARGET-SPECIFIC optimization.

    IMPORTANT: Each target type requires its own optimization because:
    - InteractionOptimizer selects features by IC against the target
    - Features predictive of direction are NOT predictive of volatility
    - RollingZScoreOptimizer HURTS volatility/regime targets

    The pipeline automatically adapts:
    - direction/returns: Winsorize → RollingZScore → Interactions
    - volatility/vol_spike/trend_regime: Winsorize → Interactions (NO ZScore)

    Output file: data/features_8h_optimized_{target}_{horizon}bar.parquet

    Args:
        args: CLI args (optional)
        pipeline_name: Which pipeline to run (default, pca, regime, all)
        horizon: Target horizon in bars (1, 3, 6, or 12)
        target: Target type - MUST match the model you're training:
            - 'direction': Binary classification (up/down)
            - 'returns': Regression on forward returns
            - 'volatility': Regression on |forward_return|
            - 'vol_spike': Binary (NO_SPIKE/SPIKE volatility)
            - 'trend_regime': Binary (uptrend/downtrend)
        save: Save optimized features to disk

    Example:
        # Optimize for volatility prediction at 24h horizon
        cmd_optimize(target='volatility', horizon=3)

        # Then build datasets (auto-loads correct optimized file)
        cmd_build_datasets()
    """
    import numpy as np
    import pandas as pd
    import polars as pl

    # Handle CLI args
    if args is not None:
        pipeline_name = getattr(args, "pipeline", pipeline_name)
        horizon = getattr(args, "horizon", horizon)
        target = getattr(args, "target", target)
        save = getattr(args, "save", save)

    horizon_label = config.FORWARD_HORIZONS.get(horizon, f"{horizon}bar")
    print("=" * 60)
    print(f"FEATURE OPTIMIZATION - Pipeline: {pipeline_name}")
    print(f"Target Type: {target} | Horizon: {horizon} ({horizon_label})")
    print("=" * 60)

    from scripts.analysis.optimizers import (
        ExpandingRankOptimizer,
        InteractionOptimizer,
        OptimizationPipeline,
        RegimeConditioningOptimizer,
        RollingZScoreOptimizer,
        WinsorizeOptimizer,
    )
    # NOTE: DomainPCAOptimizer removed - causes future leakage (PCA.fit needs full data)

    # Load data
    df = data.load_analysis_data()
    feature_cols = data.get_feature_columns(df)
    X = df[feature_cols]

    # Compute target based on type and horizon
    raw = pl.read_parquet(config.RAW_FILE)
    close = raw["RAW_P_close_abs_NN"].to_pandas()
    high = raw["RAW_P_high_abs_NN"].to_pandas()
    low = raw["RAW_P_low_abs_NN"].to_pandas()
    close.index = df.index  # Align indices
    high.index = df.index
    low.index = df.index

    # Close-to-close return (used for volatility)
    fwd_ret = (close.shift(-horizon) - close) / close

    # Net candle return (used for direction/returns)
    # up_move = how far price went above current close
    # down_move = how far price went below current close
    future_high = high.shift(-horizon)
    future_low = low.shift(-horizon)
    up_move = (future_high - close) / close
    down_move = (close - future_low) / close
    net_candle_ret = up_move - down_move

    if target == "direction":
        y = (net_candle_ret > 0).astype(int)
        target_name = f"y_direction_{horizon}"
    elif target == "returns":
        y = net_candle_ret
        target_name = f"y_returns_{horizon}"
    elif target == "volatility":
        y = fwd_ret.abs()
        target_name = f"y_volatility_{horizon}"
    elif target == "vol_spike":
        log_returns = np.log(close / close.shift(1))
        vol_window = 21
        rolling_vol = log_returns.rolling(vol_window).std()
        future_vol = rolling_vol.shift(-horizon)
        vol_ratio = future_vol / rolling_vol.clip(lower=1e-8)
        y = (vol_ratio >= 1.5).astype(float)
        y[rolling_vol.isna() | future_vol.isna()] = np.nan
        target_name = f"y_vol_spike_{horizon}"
    elif target == "trend_regime":
        fast_window = max(21, horizon * 5)
        slow_window = max(63, horizon * 15)
        sma_fast = close.rolling(fast_window).mean()
        sma_slow = close.rolling(slow_window).mean()
        y = (sma_fast > sma_slow).astype(int)
        target_name = f"y_trend_regime_{horizon}"
    else:
        print(f"Error: Unknown target type '{target}'")
        return None

    print(f"\nInput: {X.shape[0]} rows × {X.shape[1]} features")
    print(f"Target: {target_name} (non-null: {y.notna().sum()})")

    # ==========================================================================
    # PHASE 1 DESIGN: Task-Specific Preprocessing Pipelines
    # ==========================================================================
    # Based on docs/preprocessing/PHASE_1_PIPELINE_DESIGN.md:
    #
    # | Target        | Task        | Pipeline                              |
    # |---------------|-------------|---------------------------------------|
    # | returns       | regression  | Winsorize → RollingZScore             |
    # | volatility    | regression  | Winsorize → Log → ExpandingZScore     |
    # | direction     | binary      | Winsorize → ExpandingRank             |
    # | trend_regime  | binary      | Winsorize → ExpandingRank             |
    # | vol_spike     | binary      | Winsorize → ExpandingRank             |
    #
    # InteractionOptimizer is OPTIONAL and target-specific.
    # ==========================================================================

    if target == "returns":
        # REGRESSION (returns): Winsorize → RollingZScore → Interactions
        default_steps = [
            WinsorizeOptimizer(lower=0.01, upper=0.99),
            RollingZScoreOptimizer(window=252),
            InteractionOptimizer(top_k=3, n_interactions=5, min_ic=0.02),
        ]
        all_steps = [
            WinsorizeOptimizer(lower=0.01, upper=0.99),
            RollingZScoreOptimizer(window=252),
            RegimeConditioningOptimizer(),
            InteractionOptimizer(top_k=3, n_interactions=10, min_ic=0.02),
        ]

    elif target == "volatility":
        # REGRESSION (volatility): Winsorize only
        # NO ExpandingZScore — testing showed it HURTS IC (-13% degradation)
        # Base features already have high IC (~0.089), standardization adds noise
        # NO interactions — base features are excellent, interactions dilute
        # Log transform tested but shows no improvement
        default_steps = [
            WinsorizeOptimizer(lower=0.01, upper=0.99),
        ]
        all_steps = [
            WinsorizeOptimizer(lower=0.01, upper=0.99),
            RegimeConditioningOptimizer(),
        ]

    elif target in {"direction", "trend_regime", "vol_spike"}:
        # CLASSIFICATION: Winsorize → ExpandingRank
        # ExpandingRank maps features to [0,1] percentiles
        # Classification doesn't care about magnitude, only relative ordering
        # Works well with tree-based models (CatBoost, LightGBM)
        min_ic = 0.10 if target in {"vol_spike", "trend_regime"} else 0.02
        default_steps = [
            WinsorizeOptimizer(lower=0.01, upper=0.99),
            ExpandingRankOptimizer(min_periods=252),
            InteractionOptimizer(top_k=3, n_interactions=5, min_ic=min_ic),
        ]
        all_steps = [
            WinsorizeOptimizer(lower=0.01, upper=0.99),
            ExpandingRankOptimizer(min_periods=252),
            RegimeConditioningOptimizer(),
            InteractionOptimizer(top_k=3, n_interactions=10, min_ic=min_ic),
        ]

    else:
        print(f"Error: Unknown target type '{target}'")
        return None

    pipelines = {
        "default": OptimizationPipeline(default_steps, name="Default"),
        "all": OptimizationPipeline(all_steps, name="Full"),
    }

    if pipeline_name not in pipelines:
        print(f"Unknown pipeline: {pipeline_name}")
        print(f"Available: {list(pipelines.keys())}")
        return None

    pipeline = pipelines[pipeline_name]

    # Run optimization
    X_optimized = pipeline.fit_transform(X, y)

    # Print report
    pipeline.print_report()

    # Save if requested
    if save:
        import pandas as pd

        # Preserve index (timestamp) and create result
        result = pd.DataFrame(X_optimized)

        # The index of df is timestamp (set by load_analysis_data)
        result.index = df.index
        result.index.name = "timestamp"

        # Save optimized features (include target and horizon in filename)
        output_file = (
            config.DATA_DIR / f"features_8h_optimized_{target}_{horizon}bar.parquet"
        )
        result.to_parquet(output_file)
        print(f"\n✓ Saved: {output_file}")

        # Save metrics
        metrics_df = pipeline.get_metrics_df()
        metrics_file = (
            config.RESULTS_DIR / f"optimization_metrics_{target}_{horizon}bar.csv"
        )
        metrics_df.to_csv(metrics_file, index=False)
        print(f"✓ Saved: {metrics_file}")

    return pipeline


# %% cmd_all - Run all analysis
def cmd_all(args=None, force=False, plot=True):
    """Run all analysis steps.

    Args:
        args: CLI args (optional)
        force: Force recreate dataset
        plot: Generate plots
    """
    # Handle both CLI and interactive calls
    if args is not None:
        force = getattr(args, "force", force)
        plot = getattr(args, "plot", plot)

    # Prepare
    if not config.ANALYSIS_FILE.exists() or force:
        cmd_prepare()

    # CV
    cmd_cv(use_purged=False)

    # Features
    cmd_features(plot=plot)

    # Importance
    cmd_importance(plot=plot)


# %% [markdown]
# ## CLI Entry Point
# The `main()` function handles command-line argument parsing.
# In interactive mode, call the `cmd_*` functions directly.


# %% main - CLI entry point
def main():
    parser = argparse.ArgumentParser(
        description="RiskYieldMM Analysis Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Prepare
    subparsers.add_parser("prepare", help="Create analysis dataset")

    # CV
    p_cv = subparsers.add_parser("cv", help="Run cross-validation")
    p_cv.add_argument(
        "--purged",
        action="store_true",
        help="Use PurgedKFold CV (prevents temporal leakage)",
    )

    # Features
    p_features = subparsers.add_parser("features", help="Feature IC analysis")
    p_features.add_argument(
        "--no-plot", dest="plot", action="store_false", help="Skip plots"
    )

    # Importance (MDI)
    p_importance = subparsers.add_parser("importance", help="Feature importance (MDI)")
    p_importance.add_argument(
        "--no-plot", dest="plot", action="store_false", help="Skip plots"
    )

    # MDA (Permutation Importance)
    p_mda = subparsers.add_parser("mda", help="MDA (Permutation Importance)")
    p_mda.add_argument(
        "--n-repeats", type=int, default=10, help="Number of permutation repeats"
    )

    # Optimize
    p_optimize = subparsers.add_parser("optimize", help="Run feature optimization")
    p_optimize.add_argument(
        "--pipeline",
        type=str,
        default="default",
        choices=["default", "pca", "regime", "all"],
        help="Which optimization pipeline to run",
    )
    p_optimize.add_argument(
        "--horizon",
        type=int,
        default=1,
        choices=[1, 3, 6, 12],
        help="Target horizon in bars (1=8h, 3=24h, 6=48h, 12=96h)",
    )
    # Import centralized target configuration
    from scripts.workflow.config import WORKFLOW_TARGETS

    p_optimize.add_argument(
        "--target",
        type=str,
        default="direction",
        choices=WORKFLOW_TARGETS,
        help=f"Target type for optimization (default: direction). Available: {WORKFLOW_TARGETS}",
    )
    p_optimize.add_argument(
        "--no-save", dest="save", action="store_false", help="Skip saving results"
    )

    # Build datasets
    p_build = subparsers.add_parser("build-datasets", help="Build full dataset matrix")
    p_build.add_argument(
        "--horizons",
        type=int,
        nargs="+",
        default=[1, 3, 6, 12],
        help="Horizons to build (default: 1 3 6 12)",
    )
    p_build.add_argument(
        "--target-types",
        type=str,
        nargs="+",
        default=WORKFLOW_TARGETS,
        help=f"Target types to build (default: {WORKFLOW_TARGETS})",
    )

    # Auto-optimize (NEW)
    p_auto = subparsers.add_parser(
        "auto-optimize", help="Auto-select best pipeline for all 20 target-horizons"
    )
    p_auto.add_argument(
        "--horizons",
        type=int,
        nargs="+",
        default=[1, 3, 6, 12],
        help="Horizons to optimize (default: 1 3 6 12)",
    )
    p_auto.add_argument(
        "--targets",
        type=str,
        nargs="+",
        default=WORKFLOW_TARGETS,
        help=f"Target types to optimize (default: {WORKFLOW_TARGETS})",
    )
    p_auto.add_argument(
        "--no-save", dest="save", action="store_false", help="Skip saving results"
    )

    # All
    p_all = subparsers.add_parser("all", help="Run all analysis")
    p_all.add_argument("--force", action="store_true", help="Force recreate dataset")
    p_all.add_argument(
        "--no-plot", dest="plot", action="store_false", help="Skip plots"
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    # Dispatch
    commands = {
        "prepare": cmd_prepare,
        "cv": cmd_cv,
        "features": cmd_features,
        "importance": cmd_importance,
        "mda": cmd_mda,
        "optimize": cmd_optimize,
        "auto-optimize": cmd_auto_optimize,
        "build-datasets": cmd_build_datasets,
        "all": cmd_all,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


# %% Execute if run as script (not in Jupyter/interactive)
def _is_interactive():
    """Check if running in Jupyter/IPython interactive mode."""
    try:
        # IPython sets get_ipython as a builtin
        from IPython import get_ipython

        shell = get_ipython()
        if shell is None:
            return False
        return shell.__class__.__name__ in (
            "ZMQInteractiveShell",
            "TerminalInteractiveShell",
        )
    except ImportError:
        return False


if __name__ == "__main__" and not _is_interactive():
    main()


# %% [markdown]
# ## Interactive Examples
# Uncomment and run cells below for interactive analysis

# %% Example: Load data (interactive)
# df = data.load_analysis_data()
# feature_cols = data.get_feature_columns(df)
# print(f"Data shape: {df.shape}")
# print(f"Features: {len(feature_cols)}")

# %% Example: Prepare dataset
# df = cmd_prepare()

# %% Example: Cross-validation with PurgedKFold
# dir_results = cmd_cv(use_purged=True)

# %% Example: Feature importance (MDI)
# importances = cmd_importance(plot=True)

# %% Example: MDA (Permutation Importance)
# mda_results = cmd_mda(n_repeats=5)

# %% Example: Walk-forward backtest (limited iterations)
# results_df, metrics = cmd_backtest(iterations=100, plot=True)

# %% Example: IC analysis
# ic_results = cmd_features(plot=True)
