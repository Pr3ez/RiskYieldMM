"""
ICIR (Information Coefficient Information Ratio) Computation.

This module provides the core algorithms for:
1. Rolling ICIR computation - IC stability over time
2. Correlation filtering - remove redundant features

Separated from ensemble.py for:
- Unit testing in isolation
- Reuse in other contexts
- Clear algorithm documentation

Mathematical Background:
    IC (Information Coefficient) = Spearman correlation between feature and target
    ICIR = mean(IC) / std(IC) across rolling windows

    ICIR measures signal CONSISTENCY, not just strength:
    - High IC, low ICIR = strong but unstable signal (dangerous)
    - Moderate IC, high ICIR = consistent signal (preferable)

Research:
    - ICIR > 0.3 considered informative (Li et al 2024)
    - ICIR > 0.5 considered strong
    - mRMR (min-redundancy max-relevance) for correlation filtering
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
from scipy.stats import ConstantInputWarning, spearmanr

if TYPE_CHECKING:
    from .icir_config import ICIRConfig


def compute_single_ic(
    feature: np.ndarray,
    target: np.ndarray,
    min_samples: int = 10,
) -> float | None:
    """Compute single Spearman IC between feature and target.

    Args:
        feature: Feature values (1D array)
        target: Target values (1D array)
        min_samples: Minimum valid samples required

    Returns:
        Spearman correlation or None if insufficient data
    """
    mask = np.isfinite(feature) & np.isfinite(target)
    if mask.sum() < min_samples:
        return None

    feat_valid = feature[mask]
    tgt_valid = target[mask]

    # If either side is constant, Spearman IC is undefined.
    if feat_valid.min() == feat_valid.max() or tgt_valid.min() == tgt_valid.max():
        return None

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=ConstantInputWarning)
        ic, _ = spearmanr(feat_valid, tgt_valid)
    return ic if not np.isnan(ic) else None


def compute_rolling_icir(
    features: pd.DataFrame,
    target: np.ndarray,
    config: ICIRConfig,
) -> dict[str, dict]:
    """Compute Rolling ICIR for all features.

    Algorithm:
    1. Split data into n_rolling_windows non-overlapping windows
    2. For each feature, compute IC in each window
    3. ICIR = mean(IC) / std(IC) across windows
    4. Features with too few valid windows get ICIR = None

    Args:
        features: DataFrame of feature values (n_samples x n_features)
        target: Target values (n_samples,)
        config: ICIRConfig with parameters

    Returns:
        Dict mapping feature_name → {
            'icir': float | None,
            'mean_ic': float | None,
            'std_ic': float | None,
            'n_valid_windows': int,
            'window_ics': list[float | None],
        }
    """
    n_samples = len(features)
    n_windows = config.n_rolling_windows

    # Check if we have enough data
    if n_samples < config.min_samples_required:
        if config.verbose:
            print(
                f"ICIR: Insufficient data ({n_samples} < {config.min_samples_required})"
            )
        # Return empty results - caller should fall back
        return {
            col: {
                "icir": None,
                "mean_ic": None,
                "std_ic": None,
                "n_valid_windows": 0,
                "window_ics": [],
            }
            for col in features.columns
        }

    # Compute window boundaries (non-overlapping)
    window_size = n_samples // n_windows
    windows = []
    for i in range(n_windows):
        start = i * window_size
        end = start + window_size if i < n_windows - 1 else n_samples
        windows.append((start, end))

    if config.verbose:
        print(f"ICIR: {n_windows} windows, ~{window_size} samples each")

    # Compute IC for each feature in each window
    results = {}
    for col in features.columns:
        feature_vals = features[col].values
        window_ics = []

        for start, end in windows:
            ic = compute_single_ic(
                feature_vals[start:end],
                target[start:end],
                min_samples=max(10, config.min_window_size // 2),
            )
            window_ics.append(ic)

        # Count valid windows
        valid_ics = [ic for ic in window_ics if ic is not None]
        n_valid = len(valid_ics)

        if n_valid >= config.min_valid_windows:
            mean_ic = np.mean(valid_ics)
            std_ic = np.std(valid_ics, ddof=1) if n_valid > 1 else 0.0
            # ICIR = mean / std (handle zero std)
            icir = mean_ic / std_ic if std_ic > 1e-10 else np.sign(mean_ic) * 10.0
        else:
            mean_ic = None
            std_ic = None
            icir = None

        results[col] = {
            "icir": icir,
            "mean_ic": mean_ic,
            "std_ic": std_ic,
            "n_valid_windows": n_valid,
            "window_ics": window_ics,
        }

    return results


def select_features_by_icir(
    icir_results: dict[str, dict],
    config: ICIRConfig,
) -> list[str]:
    """Select features that pass ICIR threshold.

    Args:
        icir_results: Output from compute_rolling_icir()
        config: ICIRConfig with thresholds

    Returns:
        List of selected feature names (sorted by |ICIR| descending)
    """
    selected = []
    for feature, stats in icir_results.items():
        icir = stats.get("icir")
        if icir is not None and abs(icir) >= config.icir_threshold:
            selected.append((feature, abs(icir)))

    # Sort by |ICIR| descending
    selected.sort(key=lambda x: x[1], reverse=True)
    return [f[0] for f in selected]


def compute_feature_correlations(
    features: pd.DataFrame,
    method: str = "pearson",
) -> pd.DataFrame:
    """Compute correlation matrix for features.

    Args:
        features: DataFrame of feature values
        method: "pearson" or "spearman"

    Returns:
        Correlation matrix (DataFrame)
    """
    if method == "spearman":
        return features.corr(method="spearman")
    return features.corr()


def apply_correlation_filter(
    features: pd.DataFrame,
    icir_results: dict[str, dict],
    config: ICIRConfig,
    preselected: list[str] | None = None,
) -> tuple[list[str], list[str]]:
    """Remove highly correlated features, keeping higher ICIR.

    Algorithm (greedy):
    1. Compute correlation matrix
    2. For each pair with |corr| > threshold:
       - Keep the feature with higher |ICIR|
       - Mark the other for removal
    3. Iteratively remove until no pairs exceed threshold

    Args:
        features: DataFrame of feature values
        icir_results: Output from compute_rolling_icir()
        config: ICIRConfig with correlation_threshold
        preselected: If provided, only filter within these features

    Returns:
        Tuple of (kept_features, dropped_features)
    """
    # Filter to preselected if provided
    if preselected is not None:
        cols = [c for c in preselected if c in features.columns]
        features = features[cols]

    if len(features.columns) <= 1:
        return list(features.columns), []

    # Compute correlation matrix
    corr_matrix = compute_feature_correlations(features, config.correlation_method)

    # Get |ICIR| for ranking (use 0 if None)
    def get_abs_icir(f):
        stats = icir_results.get(f, {})
        icir = stats.get("icir")
        return abs(icir) if icir is not None else 0.0

    # Greedy removal
    dropped = set()
    remaining = set(features.columns)

    while True:
        # Find most correlated pair among remaining
        max_corr = 0
        worst_pair = None

        for f1 in remaining:
            for f2 in remaining:
                if f1 >= f2:  # Skip self and duplicates
                    continue
                corr = abs(corr_matrix.loc[f1, f2])
                if corr > max_corr:
                    max_corr = corr
                    worst_pair = (f1, f2)

        # Check if we need to remove anything
        if worst_pair is None or max_corr <= config.correlation_threshold:
            break

        f1, f2 = worst_pair
        icir1, icir2 = get_abs_icir(f1), get_abs_icir(f2)

        # Drop the one with lower |ICIR|
        to_drop = f2 if icir1 >= icir2 else f1
        dropped.add(to_drop)
        remaining.remove(to_drop)

        if config.verbose:
            print(
                f"ICIR corr filter: {f1} vs {f2}, corr={max_corr:.3f}, "
                f"dropping {to_drop} (ICIR={get_abs_icir(to_drop):.3f})"
            )

    return list(remaining), list(dropped)


def select_features_full_pipeline(
    features: pd.DataFrame,
    target: np.ndarray,
    config: ICIRConfig,
) -> dict:
    """Run full ICIR + correlation filter pipeline.

    This is the main entry point for feature selection.

    Args:
        features: DataFrame of raw features
        target: Target values
        config: ICIRConfig

    Returns:
        Dict with:
            'selected_features': list[str] - final selected features
            'dropped_by_icir': list[str] - features below ICIR threshold
            'dropped_by_correlation': list[str] - features removed for redundancy
            'icir_results': dict - full ICIR stats per feature
            'n_original': int
            'n_selected': int
            'method': str - 'icir' or 'ic_fallback'
    """
    n_original = len(features.columns)

    if not config.enable_icir:
        # Legacy IC-based selection
        return _select_by_simple_ic(features, target, config)

    # Step 1: Compute Rolling ICIR
    icir_results = compute_rolling_icir(features, target, config)

    # Check if ICIR succeeded (enough valid windows)
    any_valid = any(r["icir"] is not None for r in icir_results.values())

    if not any_valid:
        if config.fallback_to_ic:
            if config.verbose:
                print("ICIR: No valid ICIR computed, falling back to simple IC")
            return _select_by_simple_ic(features, target, config)
        else:
            # Return all features if no fallback
            return {
                "selected_features": list(features.columns),
                "dropped_by_icir": [],
                "dropped_by_correlation": [],
                "icir_results": icir_results,
                "n_original": n_original,
                "n_selected": n_original,
                "method": "none",
            }

    # Step 2: Select by ICIR threshold
    icir_selected = select_features_by_icir(icir_results, config)
    dropped_by_icir = [f for f in features.columns if f not in icir_selected]

    # Edge case: if ALL features dropped, keep top-K by |ICIR|
    if not icir_selected:
        # Sort by |ICIR| even if below threshold
        sorted_by_icir = sorted(
            [
                (f, abs(r["icir"]) if r["icir"] is not None else 0)
                for f, r in icir_results.items()
            ],
            key=lambda x: x[1],
            reverse=True,
        )
        icir_selected = [
            f[0] for f in sorted_by_icir[: max(5, config.top_k_interactions)]
        ]
        dropped_by_icir = [f for f in features.columns if f not in icir_selected]
        if config.verbose:
            print(f"ICIR: All below threshold, keeping top {len(icir_selected)}")

    # Step 3: Correlation filter (if enabled)
    if config.enable_correlation_filter and len(icir_selected) > 1:
        final_selected, dropped_by_corr = apply_correlation_filter(
            features[icir_selected],
            icir_results,
            config,
        )
    else:
        final_selected = icir_selected
        dropped_by_corr = []

    return {
        "selected_features": final_selected,
        "dropped_by_icir": dropped_by_icir,
        "dropped_by_correlation": dropped_by_corr,
        "icir_results": icir_results,
        "n_original": n_original,
        "n_selected": len(final_selected),
        "method": "icir",
    }


def _select_by_simple_ic(
    features: pd.DataFrame,
    target: np.ndarray,
    config: ICIRConfig,
) -> dict:
    """Fallback: Select features by simple IC threshold (legacy behavior).

    This is the original _learn_boosting_weights logic.
    """
    # Compute IC for each feature
    ic_values = {}
    for col in features.columns:
        ic = compute_single_ic(features[col].values, target)
        if ic is not None:
            ic_values[col] = ic

    # Select by threshold
    selected = [
        f for f, ic in ic_values.items() if abs(ic) >= config.fallback_ic_threshold
    ]

    # Edge case: keep at least top-K
    if not selected:
        sorted_by_ic = sorted(ic_values.items(), key=lambda x: abs(x[1]), reverse=True)
        selected = [f[0] for f in sorted_by_ic[: max(5, config.top_k_interactions)]]

    dropped = [f for f in features.columns if f not in selected]

    # Create minimal icir_results for compatibility
    icir_results = {
        f: {
            "icir": None,
            "mean_ic": ic,
            "std_ic": None,
            "n_valid_windows": 1,
            "window_ics": [ic],
        }
        for f, ic in ic_values.items()
    }

    return {
        "selected_features": selected,
        "dropped_by_icir": dropped,
        "dropped_by_correlation": [],
        "icir_results": icir_results,
        "n_original": len(features.columns),
        "n_selected": len(selected),
        "method": "ic_fallback",
    }


# =============================================================================
# ADDITIONAL FEATURE SELECTION METHODS (Per-Model Optimization)
# =============================================================================


def select_features_by_importance(
    model,
    feature_cols: list[str],
    ratio: float = 0.6,
    min_features: int = 20,
) -> list[str]:
    """Select top features by tree model importance.

    Works with CatBoost and LightGBM models that have get_feature_importance().

    Args:
        model: Trained CatBoost or LightGBM model with get_feature_importance()
        feature_cols: All feature column names (in same order as training data)
        ratio: Keep top X% of features (0.0-1.0)
        min_features: Minimum features to keep (floor)

    Returns:
        List of selected feature names, ordered by importance (descending)

    Example:
        cb_model.fit(X_train, y_train)
        selected = select_features_by_importance(cb_model, X_train.columns, ratio=0.6)
        X_selected = X_train[selected]
    """
    # Get importance scores
    try:
        importances = model.get_feature_importance()
    except AttributeError:
        # LightGBM uses feature_importances_ attribute
        importances = getattr(model, "feature_importances_", None)
        if importances is None:
            # Fall back: return all features
            return feature_cols

    importances = np.array(importances)

    # Calculate how many to keep
    n_keep = max(int(len(feature_cols) * ratio), min_features)
    n_keep = min(n_keep, len(feature_cols))  # Can't keep more than we have

    # Get indices of top features
    indices = np.argsort(importances)[::-1][:n_keep]

    # Return feature names in importance order
    return [feature_cols[i] for i in indices]


def select_features_by_variance(
    X: pd.DataFrame,
    ratio: float = 0.8,
    min_features: int = 20,
) -> list[str]:
    """Select features by variance (remove low-variance features).

    Low-variance features provide little information and can hurt models
    that are sensitive to scaling (like LSTM).

    Args:
        X: Feature DataFrame (samples x features)
        ratio: Keep top X% by variance (0.0-1.0)
        min_features: Minimum features to keep (floor)

    Returns:
        List of selected feature names, ordered by variance (descending)

    Example:
        selected = select_features_by_variance(X_train, ratio=0.8)
        X_selected = X_train[selected]
    """
    # Compute variance for each column
    variances = X.var()

    # Calculate how many to keep
    n_keep = max(int(len(X.columns) * ratio), min_features)
    n_keep = min(n_keep, len(X.columns))

    # Get top columns by variance
    top_cols = variances.nlargest(n_keep).index.tolist()
    return top_cols


def apply_feature_selection(
    X: pd.DataFrame,
    method: str,
    model=None,
    target: np.ndarray | None = None,
    ratio: float = 1.0,
    min_features: int = 20,
    icir_config: ICIRConfig | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """Apply feature selection based on specified method.

    Unified wrapper for all feature selection methods:
    - "none": Keep all features
    - "importance": Tree model importance (requires trained model)
    - "variance": Remove low-variance features
    - "icir": Rolling ICIR selection (requires target)

    Args:
        X: Feature DataFrame
        method: Selection method ("none", "importance", "variance", "icir")
        model: Trained model (required for "importance" method)
        target: Target values (required for "icir" method)
        ratio: Keep top X% of features (0.0-1.0)
        min_features: Minimum features to keep
        icir_config: ICIRConfig for ICIR method (optional, uses defaults)

    Returns:
        Tuple of (filtered DataFrame, list of selected column names)

    Example:
        # After training CatBoost
        X_cb, selected_cb = apply_feature_selection(
            X_train, method="importance", model=cb_model, ratio=0.6
        )

        # For LSTM (variance-based)
        X_lstm, selected_lstm = apply_feature_selection(
            X_train, method="variance", ratio=0.8
        )
    """
    if method == "none" or ratio >= 1.0:
        return X, X.columns.tolist()

    elif method == "importance":
        if model is None:
            # No model provided, return all
            return X, X.columns.tolist()
        selected = select_features_by_importance(
            model, X.columns.tolist(), ratio=ratio, min_features=min_features
        )
        return X[selected], selected

    elif method == "variance":
        selected = select_features_by_variance(
            X, ratio=ratio, min_features=min_features
        )
        return X[selected], selected

    elif method == "icir":
        if target is None:
            # No target provided, return all
            return X, X.columns.tolist()

        # Use existing ICIR selection
        from .icir_config import DEFAULT_ICIR_CONFIG

        config = icir_config if icir_config is not None else DEFAULT_ICIR_CONFIG
        result = select_features_full_pipeline(X, target, config)
        selected = result.get("selected_features", X.columns.tolist())

        # Ensure minimum features
        if len(selected) < min_features:
            # Fall back to keeping top by |IC|
            ic_values = {}
            for col in X.columns:
                ic = compute_single_ic(X[col].values, target)
                if ic is not None:
                    ic_values[col] = abs(ic)
            sorted_by_ic = sorted(ic_values.items(), key=lambda x: x[1], reverse=True)
            selected = [f[0] for f in sorted_by_ic[:min_features]]

        return X[selected], selected

    else:
        # Unknown method, return all
        return X, X.columns.tolist()
