"""
Fractional Differentiation (AFML Ch.5)
======================================

Fixed-Width Window Fractional Differentiation (FFD) implementation.
Preserves memory while achieving stationarity - key for price series transformation.

The key insight is that standard differencing (d=1) removes ALL memory,
while fractional differencing (0 < d < 1) removes just enough memory
to achieve stationarity while retaining predictive information.

Typical optimal d values for financial series: 0.3 - 0.7

References:
- López de Prado: "Advances in Financial Machine Learning" (Ch. 5)
- Hosking (1981): "Fractional Differencing"
"""

from typing import Literal

import numpy as np
import pandas as pd

__all__ = [
    "get_ffd_weights",
    "compute_ffd",
    "find_optimal_d",
    "compute_ffd_features",
]


def get_ffd_weights(
    d: float,
    threshold: float = 1e-5,
    max_window: int = 100,
) -> np.ndarray:
    """
    Compute FFD weights using binomial expansion.

    The weights follow the formula:
        w[k] = (-1)^k × prod_{i=0}^{k-1}(d-i) / k!
             = w[k-1] × (k-1-d) / k

    This is equivalent to the binomial expansion of (1-B)^d where B is
    the backshift operator.

    Args:
        d: Differentiation order (0 < d < 1 for fractional)
        threshold: Stop when |w[k]| < threshold
        max_window: Maximum number of weights to compute

    Returns:
        Array of weights [w_0, w_1, ..., w_k] where w_0 = 1

    Example:
        >>> weights = get_ffd_weights(0.5, threshold=1e-4)
        >>> len(weights)  # Number of weights before cutoff
        100
    """
    weights = [1.0]  # w_0 = 1

    for k in range(1, max_window):
        # Recursive formula: w_k = w_{k-1} × (k-1-d) / k
        w_k = weights[-1] * (k - 1 - d) / k
        if abs(w_k) < threshold:
            break
        weights.append(w_k)

    return np.array(weights, dtype=np.float64)


def compute_ffd(
    series: pd.Series | np.ndarray,
    d: float,
    threshold: float = 1e-5,
    max_window: int = 100,
) -> np.ndarray:
    """
    Apply Fixed-Width Window Fractional Differentiation.

    FFD formula for each point t:
        X_t^(d) = sum_{k=0}^{window} w_k × X_{t-k}

    where w_k are the FFD weights.

    Args:
        series: Price or volume series (1D array-like)
        d: Differentiation order (0 < d < 1, typically 0.3-0.7)
        threshold: Weight cutoff for efficiency
        max_window: Maximum lookback for weights

    Returns:
        Fractionally differenced series (same length, NaN-padded at start)

    Example:
        >>> prices = pd.Series([100, 101, 99, 102, 103])
        >>> ffd = compute_ffd(prices, d=0.5)
        >>> ffd[~np.isnan(ffd)]  # Valid values after warmup
    """
    if isinstance(series, pd.Series):
        values = series.values
    else:
        values = np.asarray(series)

    n = len(values)
    weights = get_ffd_weights(d, threshold, max_window)
    width = len(weights)

    # Output array (NaN-padded)
    result = np.full(n, np.nan, dtype=np.float64)

    # Apply convolution for each valid point
    for t in range(width - 1, n):
        # Slice of past values (most recent first)
        window_values = values[t - width + 1 : t + 1][::-1]
        result[t] = np.dot(weights, window_values)

    return result


def find_optimal_d(
    series: pd.Series | np.ndarray,
    min_d: float = 0.0,
    max_d: float = 1.0,
    step: float = 0.1,
    p_value_threshold: float = 0.05,
    adf_regression: Literal["c", "ct", "ctt", "n"] = "c",
    verbose: bool = False,
) -> dict:
    """
    Find minimum d that achieves stationarity (ADF test).

    Searches from min_d to max_d in steps, returning the smallest d
    where the ADF test rejects the null hypothesis of a unit root.

    Args:
        series: Price series to test
        min_d: Minimum d to try
        max_d: Maximum d to try
        step: Step size for d search
        p_value_threshold: ADF p-value threshold for stationarity
        adf_regression: ADF regression type ('c'=constant, 'ct'=trend)
        verbose: Print progress

    Returns:
        Dictionary with:
        - optimal_d: Minimum d achieving stationarity
        - adf_stat: ADF statistic at optimal d
        - p_value: p-value at optimal d
        - is_stationary: Whether stationarity achieved
        - search_results: Full search results

    Example:
        >>> result = find_optimal_d(prices, verbose=True)
        >>> print(f"Optimal d: {result['optimal_d']:.2f}")
    """
    from statsmodels.tsa.stattools import adfuller

    if isinstance(series, pd.Series):
        values = series.values
    else:
        values = np.asarray(series)

    # Remove NaN for ADF test
    values = values[~np.isnan(values)]

    results = []
    optimal_d = None
    optimal_stat = None
    optimal_pval = None

    d_values = np.arange(min_d, max_d + step / 2, step)

    for d in d_values:
        if d == 0:
            # d=0 means original series
            ffd_values = values
        else:
            ffd_values = compute_ffd(values, d)
            ffd_values = ffd_values[~np.isnan(ffd_values)]

        if len(ffd_values) < 50:
            continue

        try:
            adf_result = adfuller(ffd_values, regression=adf_regression)
            adf_stat, p_value = adf_result[0], adf_result[1]
        except Exception:
            continue

        results.append(
            {
                "d": d,
                "adf_stat": adf_stat,
                "p_value": p_value,
                "is_stationary": p_value < p_value_threshold,
            }
        )

        if verbose:
            status = "✓" if p_value < p_value_threshold else "✗"
            print(f"  d={d:.2f}: ADF={adf_stat:.3f}, p={p_value:.4f} {status}")

        # Find first d that achieves stationarity
        if optimal_d is None and p_value < p_value_threshold:
            optimal_d = d
            optimal_stat = adf_stat
            optimal_pval = p_value

    return {
        "optimal_d": optimal_d,
        "adf_stat": optimal_stat,
        "p_value": optimal_pval,
        "is_stationary": optimal_d is not None,
        "search_results": results,
    }


def compute_ffd_features(
    df: pd.DataFrame,
    price_col: str = "close",
    volume_col: str | None = "volume",
    d_values: list[float] | None = None,
    prefix: str = "M_P",
) -> pd.DataFrame:
    """
    Compute fractional differentiation features for multiple d values.

    Args:
        df: DataFrame with price/volume data
        price_col: Column name for price series
        volume_col: Column name for volume (None to skip)
        d_values: List of d values to compute (default: [0.3, 0.5, 0.7])
        prefix: Feature name prefix

    Returns:
        DataFrame with FFD feature columns added

    Example:
        >>> df = compute_ffd_features(df, price_col='close')
        >>> ffd_cols = [c for c in df.columns if 'fracdiff' in c]
    """
    if d_values is None:
        d_values = [0.3, 0.5, 0.7]

    result = df.copy()

    # Price FFD features
    if price_col in df.columns:
        for d in d_values:
            col_name = f"{prefix}_close_fracdiff_{d}_pct_N"
            ffd = compute_ffd(df[price_col].values, d=d)
            result[col_name] = ffd

    # Volume FFD features (optional)
    if volume_col and volume_col in df.columns:
        for d in [0.5]:  # Single d for volume
            col_name = f"L_V_volume_fracdiff_{d}_N"
            ffd = compute_ffd(df[volume_col].values, d=d)
            result[col_name] = ffd

    return result


def validate_ffd_features(df: pd.DataFrame) -> dict:
    """
    Validate FFD features and return summary statistics.

    Args:
        df: DataFrame with FFD feature columns

    Returns:
        Dictionary with validation metrics
    """
    ffd_cols = [c for c in df.columns if "fracdiff" in c]

    if not ffd_cols:
        return {"error": "No fracdiff columns found"}

    results = {}
    for col in ffd_cols:
        values = df[col].values
        valid_mask = ~np.isnan(values)
        valid_count = np.sum(valid_mask)

        results[col] = {
            "valid_count": int(valid_count),
            "valid_pct": 100 * valid_count / len(values),
            "nan_count": int(len(values) - valid_count),
            "mean": float(np.nanmean(values)),
            "std": float(np.nanstd(values)),
            "min": float(np.nanmin(values)),
            "max": float(np.nanmax(values)),
        }

    return {
        "n_features": len(ffd_cols),
        "features": ffd_cols,
        "stats": results,
    }


if __name__ == "__main__":
    # Quick test with synthetic data
    print("Testing FFD implementation...")

    # Create synthetic price series (random walk)
    np.random.seed(42)
    n = 1000
    returns = np.random.randn(n) * 0.02  # 2% daily vol
    prices = 100 * np.exp(np.cumsum(returns))

    print(f"\nTest series: {n} points, starting at {prices[0]:.2f}")

    # Test weights
    print("\n1. FFD Weights (d=0.5):")
    weights = get_ffd_weights(0.5, threshold=1e-4)
    print(f"   Number of weights: {len(weights)}")
    print(f"   First 5 weights: {weights[:5]}")
    print(f"   Sum of weights: {np.sum(weights):.4f}")

    # Test FFD computation
    print("\n2. FFD Computation:")
    for d in [0.3, 0.5, 0.7, 1.0]:
        ffd = compute_ffd(prices, d=d)
        valid = ~np.isnan(ffd)
        print(
            f"   d={d}: valid={np.sum(valid)}, mean={np.nanmean(ffd):.4f}, std={np.nanstd(ffd):.4f}"
        )

    # Test optimal d finder
    print("\n3. Find Optimal d:")
    result = find_optimal_d(prices, verbose=True)
    print(f"\n   Optimal d: {result['optimal_d']}")
    print(f"   ADF p-value: {result['p_value']:.4f}")

    print("\n✓ All tests completed!")
