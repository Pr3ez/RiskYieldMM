"""
Validate Rolling ICIR + Correlation Filter Approach.

This script compares:
1. OLD: Single-window IC (current implementation)
2. NEW: Rolling ICIR with correlation filtering

Uses FULL pre-backtest data (~3700 rows) to get stable estimates.

For each of the 20 targets:
- Fit helpers on training portion
- Compute IC/ICIR on validation portion
- Compare feature selection stability and quality
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.target_models.helpers import create_helper_ensemble
from scripts.target_models.registry import ALL_HORIZONS, ALL_TARGETS, load_target_data


# =============================================================================
# ICIR COMPUTATION FUNCTIONS
# =============================================================================
def compute_single_ic(features: pd.DataFrame, y: np.ndarray) -> dict[str, float]:
    """Current approach: single IC computation."""
    ics = {}
    y_np = y.values if hasattr(y, "values") else y

    for col in features.columns:
        feat = features[col].values
        mask = ~(np.isnan(feat) | np.isnan(y_np))
        if mask.sum() > 10:
            ic, _ = spearmanr(feat[mask], y_np[mask])
            if not np.isnan(ic):
                ics[col] = ic
    return ics


def compute_rolling_icir(
    features: pd.DataFrame, y: np.ndarray, n_windows: int = 5, min_window_size: int = 50
) -> dict[str, dict]:
    """
    New approach: Rolling ICIR computation.

    Splits data into n_windows, computes IC per window,
    returns ICIR = mean(IC) / std(IC) for each feature.

    Higher ICIR = more consistent signal across time.
    """
    n_rows = len(features)
    window_size = n_rows // n_windows

    if window_size < min_window_size:
        n_windows = max(3, n_rows // min_window_size)
        window_size = n_rows // n_windows

    y_np = y.values if hasattr(y, "values") else y

    # Collect ICs per window for each feature
    feature_ics = {col: [] for col in features.columns}

    for w in range(n_windows):
        start = w * window_size
        end = start + window_size if w < n_windows - 1 else n_rows

        for col in features.columns:
            feat = features[col].values[start:end]
            y_window = y_np[start:end]
            mask = ~(np.isnan(feat) | np.isnan(y_window))

            if mask.sum() > 10:
                ic, _ = spearmanr(feat[mask], y_window[mask])
                if not np.isnan(ic):
                    feature_ics[col].append(ic)

    # Compute ICIR for each feature
    results = {}
    for col, ics in feature_ics.items():
        if len(ics) >= 3:  # Need at least 3 windows
            mean_ic = np.mean(ics)
            std_ic = np.std(ics)
            icir = mean_ic / std_ic if std_ic > 0.01 else 0.0
            results[col] = {
                "mean_ic": mean_ic,
                "std_ic": std_ic,
                "icir": icir,
                "n_windows": len(ics),
                "ics": ics,
            }
    return results


def apply_correlation_filter(
    features: pd.DataFrame, icir_scores: dict[str, float], threshold: float = 0.90
) -> list[str]:
    """
    Remove redundant features based on correlation.

    For pairs with |correlation| > threshold, drop the one with lower ICIR.
    """
    # Sort features by ICIR (descending)
    sorted_features = sorted(icir_scores.items(), key=lambda x: abs(x[1]), reverse=True)

    selected = []
    dropped_due_to_corr = []

    for feat, _icir in sorted_features:
        if feat not in features.columns:
            continue

        # Check correlation with already selected features
        is_redundant = False
        for sel_feat in selected:
            corr = features[feat].corr(features[sel_feat])
            if abs(corr) > threshold:
                is_redundant = True
                dropped_due_to_corr.append((feat, sel_feat, corr))
                break

        if not is_redundant:
            selected.append(feat)

    return selected, dropped_due_to_corr


# =============================================================================
# VALIDATION FOR ONE TARGET
# =============================================================================
def validate_target(target: str, horizon: int, verbose: bool = True) -> dict:
    """
    Validate ICIR approach for one target-horizon.

    Returns comparison metrics between old IC and new ICIR approaches.
    """
    if verbose:
        print(f"\n{'=' * 60}")
        print(f"Validating {target}_{horizon}bar")
        print("=" * 60)

    # Load data
    X, y, spec = load_target_data(target, horizon, verbose=False)
    n_total = len(X)

    # Use ~80% for training helpers, ~20% for computing IC/ICIR
    # This simulates having lots of data before backtest
    train_end = int(n_total * 0.8)
    val_start = train_end

    X_train = X.iloc[:train_end]
    X_val = X.iloc[val_start:]
    y_val = y.iloc[val_start:]

    if verbose:
        print(f"  Total rows: {n_total}")
        print(f"  Train (helper fitting): {len(X_train)} rows")
        print(f"  Val (IC/ICIR computation): {len(X_val)} rows")

    # Create and fit helper ensemble
    ensemble = create_helper_ensemble(
        target=target,
        horizon=horizon,
        random_state=42,
    )
    ensemble.fit(X_train)

    # Transform validation data to get features
    output = ensemble._transform_raw(X_val)
    features = output.features

    if verbose:
        print(f"  Helper features: {len(features.columns)}")

    # === OLD APPROACH: Single IC ===
    single_ics = compute_single_ic(features, y_val)
    abs_ics = {k: abs(v) for k, v in single_ics.items()}

    # Old selection: |IC| >= 0.02
    old_threshold = 0.02
    old_selected = [f for f, ic in abs_ics.items() if ic >= old_threshold]

    if verbose:
        print(f"\n  OLD APPROACH (Single IC, threshold={old_threshold}):")
        print(f"    Features with |IC| >= {old_threshold}: {len(old_selected)}")
        if old_selected:
            top_old = sorted(
                [(f, abs_ics[f]) for f in old_selected],
                key=lambda x: x[1],
                reverse=True,
            )[:5]
            print(f"    Top 5: {[(f, f'{ic:.3f}') for f, ic in top_old]}")

    # === NEW APPROACH: Rolling ICIR ===
    icir_results = compute_rolling_icir(features, y_val, n_windows=5)

    # New selection: |ICIR| >= 0.3
    new_threshold = 0.3
    icir_scores = {f: r["icir"] for f, r in icir_results.items()}
    new_selected_icir = [
        f for f, icir in icir_scores.items() if abs(icir) >= new_threshold
    ]

    if verbose:
        print(f"\n  NEW APPROACH (Rolling ICIR, threshold={new_threshold}):")
        print(f"    Features with |ICIR| >= {new_threshold}: {len(new_selected_icir)}")
        if new_selected_icir:
            top_new = sorted(
                [(f, icir_scores[f]) for f in new_selected_icir],
                key=lambda x: abs(x[1]),
                reverse=True,
            )[:5]
            print(f"    Top 5: {[(f, f'{icir:.3f}') for f, icir in top_new]}")

    # === CORRELATION FILTER ===
    final_selected, dropped_pairs = apply_correlation_filter(
        features[new_selected_icir] if new_selected_icir else features,
        {f: icir_scores.get(f, 0) for f in new_selected_icir},
        threshold=0.90,
    )

    if verbose:
        print("\n  AFTER CORRELATION FILTER (|corr| > 0.90):")
        print(f"    Final features: {len(final_selected)}")
        print(f"    Dropped due to correlation: {len(dropped_pairs)}")

    # === STABILITY ANALYSIS ===
    # Compare IC stability: std of IC across rolling windows
    stability_old = []
    stability_new = []

    for f in old_selected:
        if f in icir_results:
            stability_old.append(icir_results[f]["std_ic"])

    for f in new_selected_icir:
        if f in icir_results:
            stability_new.append(icir_results[f]["std_ic"])

    mean_stability_old = np.mean(stability_old) if stability_old else 0
    mean_stability_new = np.mean(stability_new) if stability_new else 0

    if verbose:
        print("\n  STABILITY COMPARISON:")
        print(f"    Old selection mean IC std: {mean_stability_old:.4f}")
        print(f"    New selection mean IC std: {mean_stability_new:.4f}")

        # Lower std = more stable = better
        if mean_stability_new < mean_stability_old:
            improvement = (
                (mean_stability_old - mean_stability_new) / mean_stability_old * 100
            )
            print(f"    ✓ New approach has {improvement:.1f}% more stable features")
        else:
            print("    Similar stability")

    # === OVERLAP ANALYSIS ===
    overlap = set(old_selected) & set(new_selected_icir)
    old_only = set(old_selected) - set(new_selected_icir)
    new_only = set(new_selected_icir) - set(old_selected)

    if verbose:
        print("\n  SELECTION OVERLAP:")
        print(f"    Both methods select: {len(overlap)}")
        print(f"    Only OLD selects: {len(old_only)}")
        print(f"    Only NEW selects: {len(new_only)}")

    # Return summary
    return {
        "target": target,
        "horizon": horizon,
        "n_features": len(features.columns),
        "old_selected": len(old_selected),
        "new_selected_icir": len(new_selected_icir),
        "new_final": len(final_selected),
        "n_corr_dropped": len(dropped_pairs),
        "stability_old": mean_stability_old,
        "stability_new": mean_stability_new,
        "overlap": len(overlap),
        "old_only": len(old_only),
        "new_only": len(new_only),
    }


# =============================================================================
# MAIN VALIDATION
# =============================================================================
def run_full_validation():
    """Run validation across all 20 targets."""
    print("=" * 70)
    print("ROLLING ICIR + CORRELATION FILTER VALIDATION")
    print("=" * 70)
    print()
    print("Comparing:")
    print("  OLD: Single IC, threshold=0.02")
    print("  NEW: Rolling ICIR (5 windows), threshold=0.3, correlation filter")
    print()

    results = []

    for target in ALL_TARGETS:
        for horizon in ALL_HORIZONS:
            try:
                r = validate_target(target, horizon, verbose=True)
                results.append(r)
            except Exception as e:
                print(f"\n  ERROR on {target}_{horizon}bar: {e}")
                continue

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY ACROSS ALL TARGETS")
    print("=" * 70)

    df = pd.DataFrame(results)

    print(f"\nTotal targets validated: {len(df)}")
    print("\nFeature counts:")
    print(f"  OLD method avg: {df['old_selected'].mean():.1f} features")
    print(
        f"  NEW method (ICIR only) avg: {df['new_selected_icir'].mean():.1f} features"
    )
    print(f"  NEW method (final) avg: {df['new_final'].mean():.1f} features")

    print("\nStability (lower = better):")
    print(f"  OLD method avg IC std: {df['stability_old'].mean():.4f}")
    print(f"  NEW method avg IC std: {df['stability_new'].mean():.4f}")

    # How many targets improved?
    improved = (df["stability_new"] < df["stability_old"]).sum()
    print(f"\nTargets with improved stability: {improved}/{len(df)}")

    # Save results
    output_path = Path("data/analysis/icir_validation_results.csv")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"\nResults saved to: {output_path}")

    return df


def quick_test():
    """Quick test on 2 targets."""
    print("Quick validation test on 2 targets...")
    print()

    for target, horizon in [("volatility", 1), ("direction", 6)]:
        validate_target(target, horizon, verbose=True)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--quick", action="store_true", help="Run quick test on 2 targets"
    )
    args = parser.parse_args()

    if args.quick:
        quick_test()
    else:
        run_full_validation()
