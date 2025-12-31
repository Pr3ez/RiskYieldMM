"""
Measure baseline helper quality (IC) and execution time.

This script measures:
1. Information Coefficient (IC) per helper feature
2. Execution time per helper
3. Total feature count

Used to establish baseline before quality improvements.
"""

import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

# Import helpers
from scripts.target_models.helpers.base import HelperConfig
from scripts.target_models.helpers.bocpd import BOCPDHelper
from scripts.target_models.helpers.cusum import CUSUMConfig, CUSUMHelper
from scripts.target_models.helpers.egarch import EGARCHHelper
from scripts.target_models.helpers.evt_pot import EVTPOTHelper
from scripts.target_models.helpers.garch import GARCHConfig, GARCHHelper
from scripts.target_models.helpers.hmm import HMMHelper
from scripts.target_models.helpers.kalman import KalmanHelper
from scripts.target_models.helpers.ou import OUHelper


def load_test_data(n_samples: int = 5000) -> tuple[pd.DataFrame, np.ndarray]:
    """Load or generate test data for helper evaluation."""
    # Try to load real data
    data_path = Path("data/datasets/direction_1bar.parquet")
    if data_path.exists():
        df = pd.read_parquet(data_path)
        # Get features (first N numeric columns) and target
        feature_cols = [
            c
            for c in df.columns
            if c.startswith(("f_", "close", "open", "high", "low", "volume"))
        ]
        if not feature_cols:
            feature_cols = df.select_dtypes(include=[np.number]).columns[:50].tolist()

        X = df[feature_cols].iloc[:n_samples].copy()

        # Target: direction (1 = up, 0 = down)
        if "y_direction" in df.columns:
            y = df["y_direction"].iloc[:n_samples].values.astype(float)
        else:
            # Fallback: compute from returns
            y = (
                (df["close"].pct_change().shift(-1) > 0)
                .iloc[:n_samples]
                .values.astype(float)
            )

        return X, y

    # Generate synthetic data if no real data
    print("Warning: Using synthetic data (no real data found)")
    np.random.seed(42)

    # Simulate price-like features
    returns = np.random.normal(0, 0.02, n_samples)
    price = 100 * np.exp(np.cumsum(returns))
    volatility = pd.Series(returns).rolling(20, min_periods=1).std().values

    X = pd.DataFrame(
        {
            "close": price,
            "returns": returns,
            "volatility": volatility,
            "volume": np.random.lognormal(10, 1, n_samples),
        }
    )

    # Binary direction target
    y = (returns > 0).astype(float)

    return X, y


def compute_ic(features: pd.DataFrame, y: np.ndarray) -> dict[str, float]:
    """Compute IC (Spearman correlation) for each feature."""
    ics = {}
    for col in features.columns:
        x = features[col].values

        # Handle NaN/Inf
        valid = np.isfinite(x) & np.isfinite(y)
        if valid.sum() < 30:
            ics[col] = np.nan
            continue

        # Skip constant features
        if np.std(x[valid]) < 1e-10:
            ics[col] = np.nan
            continue

        try:
            ic, _ = spearmanr(x[valid], y[valid])
            ics[col] = ic if np.isfinite(ic) else np.nan
        except Exception:
            ics[col] = np.nan

    return ics


def measure_helper(
    helper_class,
    config,
    X: pd.DataFrame,
    y: np.ndarray,
    name: str,
) -> dict:
    """Measure a single helper's performance."""
    # Initialize
    helper = helper_class(config)

    # Time fit
    start = time.perf_counter()
    helper.fit(X)
    fit_time = (time.perf_counter() - start) * 1000

    # Time transform
    start = time.perf_counter()
    output = helper.transform(X)
    transform_time = (time.perf_counter() - start) * 1000

    features = output.features

    # Compute IC
    ics = compute_ic(features, y)

    # Summary stats
    valid_ics = [v for v in ics.values() if np.isfinite(v)]
    mean_abs_ic = np.mean(np.abs(valid_ics)) if valid_ics else 0.0
    max_abs_ic = np.max(np.abs(valid_ics)) if valid_ics else 0.0

    return {
        "name": name,
        "n_features": len(features.columns),
        "fit_time_ms": fit_time,
        "transform_time_ms": transform_time,
        "total_time_ms": fit_time + transform_time,
        "mean_abs_ic": mean_abs_ic,
        "max_abs_ic": max_abs_ic,
        "feature_ics": ics,
    }


def run_baseline_measurement():
    """Run baseline measurement for all helpers."""
    print("=" * 70)
    print("HELPER QUALITY BASELINE MEASUREMENT")
    print("=" * 70)

    # Load data
    print("\nLoading test data...")
    X, y = load_test_data(n_samples=5000)
    print(f"  Data shape: {X.shape}")
    print(f"  Target distribution: {y.mean():.1%} positive")

    # Base config
    base_config = HelperConfig(
        target="direction",
        horizon=1,
        task_type="binary",
        random_state=42,
    )

    # Define helpers to measure
    helpers_to_measure = [
        ("Kalman", KalmanHelper, base_config),
        ("CUSUM", CUSUMHelper, CUSUMConfig(target="direction", horizon=1)),
        ("GARCH", GARCHHelper, GARCHConfig(target="direction", horizon=1)),
        (
            "HMM-4",
            HMMHelper,
            HelperConfig(target="direction", horizon=1),
            {"n_states": 4, "regime_type": "market"},
        ),
        (
            "HMM-5",
            HMMHelper,
            HelperConfig(target="direction", horizon=1),
            {"n_states": 5, "regime_type": "volatility"},
        ),
        ("OU", OUHelper, base_config),
        ("EVT", EVTPOTHelper, base_config),
        ("BOCPD", BOCPDHelper, base_config),
        ("EGARCH", EGARCHHelper, base_config),
    ]

    results = []
    total_time = 0
    total_features = 0

    print("\n" + "-" * 70)
    print(
        f"{'Helper':<12} {'Features':>8} {'Time (ms)':>10} {'Mean |IC|':>10} {'Max |IC|':>10}"
    )
    print("-" * 70)

    for item in helpers_to_measure:
        if len(item) == 3:
            name, cls, cfg = item
            extra_kwargs = {}
        else:
            name, cls, cfg, extra_kwargs = item

        try:
            if extra_kwargs:
                result = measure_helper(
                    lambda c: cls(c, **extra_kwargs), cfg, X, y, name
                )
            else:
                result = measure_helper(cls, cfg, X, y, name)

            results.append(result)
            total_time += result["total_time_ms"]
            total_features += result["n_features"]

            print(
                f"{name:<12} {result['n_features']:>8} {result['total_time_ms']:>10.1f} "
                f"{result['mean_abs_ic']:>10.4f} {result['max_abs_ic']:>10.4f}"
            )
        except Exception as e:
            print(f"{name:<12} ERROR: {e}")

    print("-" * 70)

    # Compute overall stats
    all_ics = []
    for r in results:
        all_ics.extend([v for v in r["feature_ics"].values() if np.isfinite(v)])

    overall_mean_ic = np.mean(np.abs(all_ics)) if all_ics else 0.0

    print(
        f"{'TOTAL':<12} {total_features:>8} {total_time:>10.1f} {overall_mean_ic:>10.4f}"
    )
    print("=" * 70)

    # Summary
    print("\n📊 BASELINE SUMMARY:")
    print(f"  Total features: {total_features}")
    print(f"  Total time: {total_time:.1f}ms")
    print(f"  Overall mean |IC|: {overall_mean_ic:.4f}")

    # Top features by IC
    print("\n🏆 TOP 10 FEATURES BY |IC|:")
    all_feature_ics = []
    for r in results:
        for feat, ic in r["feature_ics"].items():
            if np.isfinite(ic):
                all_feature_ics.append((feat, abs(ic), ic))

    all_feature_ics.sort(key=lambda x: x[1], reverse=True)
    for i, (feat, abs_ic, ic) in enumerate(all_feature_ics[:10], 1):
        print(f"  {i:2d}. {feat:<40} IC={ic:+.4f}")

    return {
        "total_features": total_features,
        "total_time_ms": total_time,
        "overall_mean_ic": overall_mean_ic,
        "helper_results": results,
    }


if __name__ == "__main__":
    run_baseline_measurement()
