"""
Feature Analysis Module
======================

Analysis tools for features:
- Domain classification
- IC/ICIR (Information Coefficient) analysis
- Feature importance (LightGBM-based)
- Redundancy detection
- Distribution analysis
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from . import config

# =============================================================================
# DOMAIN CLASSIFICATION
# =============================================================================


def classify_feature_domain(feature_name: str) -> str:
    """Classify a single feature into its domain."""
    name_lower = feature_name.lower()

    for domain, prefixes in config.FEATURE_DOMAIN_PREFIXES.items():
        for prefix in prefixes:
            if prefix.lower() in name_lower or feature_name.startswith(prefix):
                return domain
    return "Other"


def classify_all_features(feature_cols: list[str]) -> dict[str, list[str]]:
    """
    Classify all features into domains.

    Returns:
        Dict mapping domain name to list of features
    """
    domains: dict[str, list[str]] = {}
    for col in feature_cols:
        domain = classify_feature_domain(col)
        if domain not in domains:
            domains[domain] = []
        domains[domain].append(col)
    return domains


# =============================================================================
# IC/ICIR ANALYSIS
# =============================================================================


@dataclass
class ICResult:
    """Results from IC analysis for a single feature."""

    feature: str
    horizon: str
    ic: float  # Information Coefficient (Spearman correlation)
    ic_pvalue: float  # P-value of IC
    icir: float  # IC Information Ratio
    hit_rate: float  # Direction accuracy
    n_samples: int
    is_significant: bool  # FDR-corrected significance


def compute_ic(
    feature: pd.Series, target: pd.Series, min_samples: int = 100
) -> tuple[float, float]:
    """
    Compute Information Coefficient (Spearman rank correlation).

    Returns:
        (IC, p-value)
    """
    mask = feature.notna() & target.notna()
    if mask.sum() < min_samples:
        return np.nan, np.nan

    ic, pvalue = stats.spearmanr(feature[mask], target[mask])
    return ic, pvalue


def compute_rolling_ic(
    feature: pd.Series,
    target: pd.Series,
    window: int | None = None,
    min_periods: int | None = None,
) -> pd.Series:
    """
    Compute rolling IC over time for stability analysis.

    Returns:
        Series of IC values indexed by time
    """
    window = window or config.ANALYSIS_CONFIG.ic_rolling_window
    min_periods = min_periods or config.ANALYSIS_CONFIG.ic_min_periods

    # Align series
    df = pd.DataFrame({"feature": feature, "target": target}).dropna()
    if len(df) < min_periods:
        return pd.Series(dtype=float)

    def rolling_spearman(x):
        return stats.spearmanr(x["feature"], x["target"])[0]

    # Use rolling window
    ic_series = df.rolling(window, min_periods=min_periods).apply(
        lambda x: stats.spearmanr(
            df.loc[x.index, "feature"], df.loc[x.index, "target"]
        )[0]
        if len(x) >= min_periods
        else np.nan,
        raw=False,
    )["feature"]

    return ic_series


def compute_icir(ic_values: pd.Series | np.ndarray) -> float:
    """
    Compute IC Information Ratio (stability measure).

    ICIR = mean(IC) / std(IC)
    Higher ICIR = more stable predictive power
    """
    ic_clean = pd.Series(ic_values).dropna()
    if len(ic_clean) < 2 or ic_clean.std() == 0:
        return np.nan
    return ic_clean.mean() / ic_clean.std()


def compute_hit_rate(predictions: pd.Series, actuals: pd.Series) -> float:
    """Compute directional accuracy (hit rate)."""
    mask = predictions.notna() & actuals.notna()
    if mask.sum() == 0:
        return np.nan
    return (np.sign(predictions[mask]) == np.sign(actuals[mask])).mean()


def benjamini_hochberg_fdr(pvals: np.ndarray, alpha: float = 0.05) -> np.ndarray:
    """
    Benjamini-Hochberg FDR correction for multiple testing.

    Returns:
        Adjusted p-values (q-values)
    """
    pvals = np.asarray(pvals)
    n = len(pvals)
    if n == 0:
        return pvals

    sorted_idx = np.argsort(pvals)
    sorted_pvals = pvals[sorted_idx]

    ranks = np.arange(1, n + 1)
    adjusted = sorted_pvals * n / ranks
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
    adjusted = np.clip(adjusted, 0, 1)

    result = np.empty(n)
    result[sorted_idx] = adjusted
    return result


def compute_ic_analysis(
    df: pd.DataFrame,
    feature_cols: list[str] | None = None,
    target_col: str = "y_forward_return_1",
    alpha: float | None = None,
) -> pd.DataFrame:
    """
    Compute IC analysis for all features against a target.

    Args:
        df: DataFrame with features and targets
        feature_cols: List of feature columns (auto-detected if None)
        target_col: Target column name
        alpha: Significance level for FDR (default from config)

    Returns:
        DataFrame with IC, ICIR, hit_rate, significance for each feature
    """
    from . import data

    alpha = alpha or config.ANALYSIS_CONFIG.significance_level

    if feature_cols is None:
        feature_cols = data.get_feature_columns(df)

    target = df[target_col]
    results = []

    for col in feature_cols:
        ic, pval = compute_ic(df[col], target)
        hit = compute_hit_rate(df[col], target)

        results.append(
            {
                "feature": col,
                "ic": ic,
                "ic_pvalue": pval,
                "hit_rate": hit,
                "n_samples": df[col].notna().sum(),
                "domain": classify_feature_domain(col),
            }
        )

    results_df = pd.DataFrame(results)

    # FDR correction
    pvals = results_df["ic_pvalue"].values
    qvals = benjamini_hochberg_fdr(pvals, alpha)
    results_df["ic_qvalue"] = qvals
    results_df["is_significant"] = qvals < alpha

    # Sort by absolute IC
    results_df["abs_ic"] = results_df["ic"].abs()
    results_df = results_df.sort_values("abs_ic", ascending=False)

    return results_df


def compute_multi_horizon_ic(
    df: pd.DataFrame,
    feature_cols: list[str] | None = None,
    horizons: dict[int, str] | None = None,
    use_non_overlapping: bool = True,
) -> pd.DataFrame:
    """
    Compute IC for all features across multiple forward return horizons.

    For horizons > 1, uses non-overlapping samples to avoid autocorrelation bias.

    Args:
        df: DataFrame with features and targets
        feature_cols: List of feature columns (auto-detected if None)
        horizons: Dict of {bars: label} (default from config.FORWARD_HORIZONS)
        use_non_overlapping: Sample every N bars for N-bar returns (recommended)

    Returns:
        DataFrame with columns: feature, domain, ic_1bar, ic_3bar, ic_6bar, ic_12bar, best_horizon
    """
    from . import data

    if feature_cols is None:
        feature_cols = data.get_feature_columns(df)

    if horizons is None:
        horizons = config.FORWARD_HORIZONS

    results = []

    for col in feature_cols:
        feature_vals = df[col].values
        row = {
            "feature": col,
            "domain": classify_feature_domain(col),
        }

        best_ic = 0
        best_horizon = 1

        for n_bars, _label in horizons.items():
            target_col = f"y_forward_return_{n_bars}"
            if target_col not in df.columns:
                row[f"ic_{n_bars}bar"] = np.nan
                row[f"p_{n_bars}bar"] = np.nan
                row[f"n_{n_bars}bar"] = 0
                continue

            target_vals = df[target_col].values

            # For longer horizons, use non-overlapping samples
            if use_non_overlapping and n_bars > 1:
                indices = np.arange(0, len(df), n_bars)
                mask = ~np.isnan(feature_vals[indices]) & ~np.isnan(
                    target_vals[indices]
                )
                f_vals = feature_vals[indices][mask]
                t_vals = target_vals[indices][mask]
            else:
                mask = ~np.isnan(feature_vals) & ~np.isnan(target_vals)
                f_vals = feature_vals[mask]
                t_vals = target_vals[mask]

            if len(f_vals) > 30:
                ic, pval = stats.spearmanr(f_vals, t_vals)
            else:
                ic, pval = np.nan, np.nan

            row[f"ic_{n_bars}bar"] = ic
            row[f"p_{n_bars}bar"] = pval
            row[f"n_{n_bars}bar"] = len(f_vals)

            # Track best horizon
            if not np.isnan(ic) and abs(ic) > abs(best_ic):
                best_ic = ic
                best_horizon = n_bars

        row["best_horizon"] = best_horizon
        row["best_ic"] = best_ic
        results.append(row)

    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values("best_ic", key=abs, ascending=False)

    return results_df


def compute_horizon_summary(multi_horizon_df: pd.DataFrame) -> pd.DataFrame:
    """
    Summarize which features work best at which horizons.

    Args:
        multi_horizon_df: Output from compute_multi_horizon_ic

    Returns:
        DataFrame with horizon-specific insights
    """
    ic_cols = [
        c for c in multi_horizon_df.columns if c.startswith("ic_") and c.endswith("bar")
    ]

    summary = []
    for _, row in multi_horizon_df.iterrows():
        ics = {col: row[col] for col in ic_cols if not np.isnan(row[col])}
        if not ics:
            continue

        # Find characteristics
        best_col = max(ics.keys(), key=lambda x: abs(ics[x]))
        best_horizon = int(best_col.replace("ic_", "").replace("bar", ""))

        # Check if IC increases with horizon (trend signal) or decreases (short-term signal)
        ic_values = [
            row[f"ic_{h}bar"]
            for h in [1, 3, 6, 12]
            if f"ic_{h}bar" in row and not np.isnan(row[f"ic_{h}bar"])
        ]
        if len(ic_values) >= 2:
            trend = (
                "increasing"
                if abs(ic_values[-1]) > abs(ic_values[0]) * 1.5
                else "stable"
                if abs(ic_values[-1]) > abs(ic_values[0]) * 0.7
                else "decreasing"
            )
        else:
            trend = "unknown"

        summary.append(
            {
                "feature": row["feature"],
                "domain": row["domain"],
                "best_horizon_bars": best_horizon,
                "best_ic": row["best_ic"],
                "ic_trend": trend,
                "ic_1bar": row.get("ic_1bar", np.nan),
                "ic_12bar": row.get("ic_12bar", np.nan),
            }
        )

    return pd.DataFrame(summary).sort_values("best_ic", key=abs, ascending=False)


# =============================================================================
# FEATURE IMPORTANCE
# =============================================================================


def compute_lgb_importance(
    X: pd.DataFrame, y: pd.Series, importance_type: str = "gain"
) -> pd.DataFrame:
    """
    Compute LightGBM feature importance.

    Args:
        X: Features
        y: Target
        importance_type: 'gain' or 'split'

    Returns:
        DataFrame with feature importances
    """
    try:
        from lightgbm import LGBMClassifier
    except ImportError as err:
        raise ImportError("LightGBM required for importance analysis") from err

    model = LGBMClassifier(
        n_estimators=config.MODEL_CONFIG.lgb_n_estimators,
        max_depth=config.MODEL_CONFIG.lgb_max_depth,
        verbose=-1,
        random_state=config.MODEL_CONFIG.random_state,
        importance_type=importance_type,
    )
    model.fit(X, y)

    importances = pd.DataFrame(
        {
            "feature": X.columns,
            "importance": model.feature_importances_,
            "domain": [classify_feature_domain(c) for c in X.columns],
        }
    ).sort_values("importance", ascending=False)

    return importances


def compute_permutation_importance(
    model,
    X_val: pd.DataFrame,
    y_val: pd.Series,
    n_repeats: int = 10,
    random_state: int | None = None,
    scoring: str | None = None,
) -> pd.DataFrame:
    """
    Compute MDA (Mean Decrease Accuracy) via permutation importance.

    Unlike MDI (tree-based importance), MDA:
    - Works for ANY classifier/regressor
    - Is computed out-of-sample on validation data
    - Measures actual predictive contribution

    Academic Reference:
        - Breiman, L. (2001). "Random Forests." Machine Learning, 45, 5-32.
        - Lopez de Prado, M. (2018). AFML, Chapter 8.

    Args:
        model: Fitted sklearn-compatible model
        X_val: Validation features (out-of-sample)
        y_val: Validation target
        n_repeats: Number of times to permute each feature
        random_state: For reproducibility
        scoring: Scorer to use ('roc_auc' for classification,
                 'neg_mean_squared_error' for regression).
                 If None, uses model's default scorer.

    Returns:
        DataFrame with columns: feature, importance_mean, importance_std, domain
        Sorted by importance_mean descending.
    """
    from sklearn.inspection import permutation_importance

    random_state = random_state or config.MODEL_CONFIG.random_state

    result = permutation_importance(
        model,
        X_val,
        y_val,
        n_repeats=n_repeats,
        random_state=random_state,
        scoring=scoring,
        n_jobs=-1,  # Parallel computation
    )

    importances = pd.DataFrame(
        {
            "feature": X_val.columns,
            "importance_mean": result.importances_mean,
            "importance_std": result.importances_std,
            "domain": [classify_feature_domain(c) for c in X_val.columns],
        }
    ).sort_values("importance_mean", ascending=False)

    return importances


# =============================================================================
# REDUNDANCY DETECTION
# =============================================================================


def find_redundant_features(
    df: pd.DataFrame,
    feature_cols: list[str] | None = None,
    threshold: float | None = None,
) -> list[tuple[str, str, float]]:
    """
    Find pairs of highly correlated (redundant) features.

    Returns:
        List of (feature1, feature2, correlation) tuples
    """
    from . import data

    threshold = threshold or config.ANALYSIS_CONFIG.correlation_threshold

    if feature_cols is None:
        feature_cols = data.get_feature_columns(df)

    X = df[feature_cols].dropna()
    if len(X) < 100:
        return []

    corr_matrix = X.corr(method="spearman")
    redundant = []

    for i, col1 in enumerate(feature_cols):
        for j, col2 in enumerate(feature_cols):
            if i < j:  # Upper triangle only
                corr = corr_matrix.loc[col1, col2]
                if abs(corr) >= threshold:
                    redundant.append((col1, col2, corr))

    return sorted(redundant, key=lambda x: abs(x[2]), reverse=True)


# =============================================================================
# DISTRIBUTION ANALYSIS
# =============================================================================


def analyze_distribution(series: pd.Series) -> dict:
    """Analyze distribution statistics for a single feature."""
    clean = series.dropna()
    if len(clean) < 10:
        return {"valid": False}

    return {
        "valid": True,
        "count": len(clean),
        "mean": clean.mean(),
        "std": clean.std(),
        "min": clean.min(),
        "max": clean.max(),
        "median": clean.median(),
        "skew": clean.skew(),
        "kurtosis": clean.kurtosis(),
        "pct_zero": (clean == 0).mean(),
        "pct_nan": series.isna().mean(),
    }


def get_distribution_summary(
    df: pd.DataFrame, feature_cols: list[str] | None = None
) -> pd.DataFrame:
    """Get distribution summary for all features."""
    from . import data

    if feature_cols is None:
        feature_cols = data.get_feature_columns(df)

    results = []
    for col in feature_cols:
        stats_dict = analyze_distribution(df[col])
        stats_dict["feature"] = col
        stats_dict["domain"] = classify_feature_domain(col)
        results.append(stats_dict)

    return pd.DataFrame(results)
