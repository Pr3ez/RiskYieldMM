"""
Statistical validation metrics for ML trading strategies.

Implements:
1. Deflated Sharpe Ratio (DSR) - Bailey & de Prado (2014)
2. Probability of Backtest Overfitting (PBO) - Bailey & de Prado (2015)
3. Regime-conditional metrics

References:
- Bailey, D., & de Prado, M. L. (2014). "The Deflated Sharpe Ratio"
- Bailey, D., & de Prado, M. L. (2015). "The Probability of Backtest Overfitting"
"""

from dataclasses import dataclass

import numpy as np
from scipy import stats


@dataclass
class DeflatedSharpeResult:
    """Result from Deflated Sharpe Ratio calculation.

    Attributes:
        sharpe_ratio: Raw Sharpe Ratio
        deflated_sharpe: DSR corrected for multiple testing
        p_value: Probability that DSR is due to chance
        is_significant: Whether DSR passes significance test (p < 0.05)
        n_trials: Number of trials/parameter combinations tested
        variance_of_sharpe: Variance estimate of SR distribution
        skewness: Return distribution skewness
        kurtosis: Return distribution excess kurtosis
    """

    sharpe_ratio: float
    deflated_sharpe: float
    p_value: float
    is_significant: bool
    n_trials: int
    variance_of_sharpe: float
    skewness: float
    kurtosis: float

    def __repr__(self) -> str:
        sig = "✓" if self.is_significant else "✗"
        return (
            f"DSR={self.deflated_sharpe:.3f} (SR={self.sharpe_ratio:.3f}, "
            f"p={self.p_value:.3f} {sig}, n_trials={self.n_trials})"
        )


def compute_sharpe_ratio(
    returns: np.ndarray,
    risk_free_rate: float = 0.0,
    periods_per_year: int = 1095,  # 8-hour bars: 3 per day * 365
) -> float:
    """
    Compute annualized Sharpe Ratio.

    Args:
        returns: Array of period returns
        risk_free_rate: Annualized risk-free rate (default 0)
        periods_per_year: Number of periods per year for annualization

    Returns:
        Annualized Sharpe Ratio
    """
    excess_returns = returns - risk_free_rate / periods_per_year
    mean_return = np.mean(excess_returns)
    std_return = np.std(excess_returns, ddof=1)

    if std_return == 0:
        return 0.0

    # Annualize
    sharpe = mean_return / std_return * np.sqrt(periods_per_year)
    return float(sharpe)


def compute_deflated_sharpe_ratio(
    returns: np.ndarray,
    n_trials: int = 1,
    risk_free_rate: float = 0.0,
    periods_per_year: int = 1095,
) -> DeflatedSharpeResult:
    """
    Compute Deflated Sharpe Ratio (Bailey & de Prado 2014).

    The DSR corrects for:
    1. Multiple testing (number of parameter combinations tried)
    2. Non-normality (skewness and kurtosis of returns)
    3. Short sample size

    Formula:
        DSR = SR * (1 - γ₃*skew/6 + (γ₃²-3)*kurt/24) * sqrt(T/(T-1))

    Where:
        SR = standard Sharpe Ratio
        γ₃ = skewness coefficient
        kurt = excess kurtosis
        T = number of observations

    Args:
        returns: Array of period returns
        n_trials: Number of parameter combinations tested (for multiple testing)
        risk_free_rate: Annualized risk-free rate
        periods_per_year: Periods per year for annualization

    Returns:
        DeflatedSharpeResult with DSR and diagnostics
    """
    T = len(returns)
    if T < 30:
        raise ValueError(f"Need at least 30 returns, got {T}")

    # Step 1: Compute raw Sharpe Ratio
    sharpe = compute_sharpe_ratio(returns, risk_free_rate, periods_per_year)

    # Step 2: Compute higher moments
    skewness = float(stats.skew(returns))
    kurtosis = float(stats.kurtosis(returns))  # excess kurtosis

    # Step 3: Compute variance of Sharpe Ratio estimator
    # Var(SR) ≈ (1 + 0.5*SR² - skew*SR + (kurt+2)/4 * SR²) / (T-1)
    var_sr = (
        1 + 0.5 * sharpe**2 - skewness * sharpe + (kurtosis + 2) / 4 * sharpe**2
    ) / (T - 1)

    # Step 4: Expected maximum SR under null hypothesis
    # E[max(SR)] ≈ sqrt(2*log(n_trials)) * sqrt(Var(SR)) when n_trials large
    # For small n_trials, use exact formula
    if n_trials <= 1:
        expected_max_sr = 0
    else:
        euler_gamma = 0.5772156649  # Euler-Mascheroni constant
        expected_max_sr = (
            np.sqrt(2 * np.log(n_trials))
            - (np.log(np.pi) + euler_gamma) / (2 * np.sqrt(2 * np.log(n_trials)))
        ) * np.sqrt(var_sr)

    # Step 5: Deflate the Sharpe Ratio
    deflated_sharpe = sharpe - expected_max_sr

    # Step 6: Compute p-value
    # Under null, SR ~ N(0, sqrt(var_sr))
    # P(SR > observed) = 1 - Phi(SR / sqrt(var_sr))
    if var_sr > 0:
        z_score = deflated_sharpe / np.sqrt(var_sr)
        p_value = 1 - stats.norm.cdf(z_score)
    else:
        p_value = 1.0

    return DeflatedSharpeResult(
        sharpe_ratio=sharpe,
        deflated_sharpe=deflated_sharpe,
        p_value=p_value,
        is_significant=p_value < 0.05,
        n_trials=n_trials,
        variance_of_sharpe=var_sr,
        skewness=skewness,
        kurtosis=kurtosis,
    )


@dataclass
class RegimeMetrics:
    """Metrics partitioned by volatility regime.

    Attributes:
        high_vol: Metrics during high volatility periods
        low_vol: Metrics during low volatility periods
        normal: Metrics during normal volatility periods
        regime_counts: Number of observations in each regime
    """

    high_vol: dict[str, float]
    low_vol: dict[str, float]
    normal: dict[str, float]
    regime_counts: dict[str, int]


def compute_regime_metrics(
    returns: np.ndarray,
    predictions: np.ndarray,
    volatility: np.ndarray | None = None,
    vol_window: int = 21,
    high_quantile: float = 0.75,
    low_quantile: float = 0.25,
) -> RegimeMetrics:
    """
    Compute metrics partitioned by volatility regime.

    Args:
        returns: Actual returns
        predictions: Predicted returns or probabilities
        volatility: Pre-computed volatility (if None, computed from returns)
        vol_window: Rolling window for volatility calculation
        high_quantile: Quantile threshold for high volatility
        low_quantile: Quantile threshold for low volatility

    Returns:
        RegimeMetrics with metrics for each regime
    """
    n = len(returns)

    # Compute volatility if not provided
    if volatility is None:
        # Rolling standard deviation
        vol = np.full(n, np.nan)
        for i in range(vol_window, n):
            vol[i] = np.std(returns[i - vol_window : i])
        volatility = vol

    # Define regime thresholds
    valid_vol = volatility[~np.isnan(volatility)]
    high_thresh = np.quantile(valid_vol, high_quantile)
    low_thresh = np.quantile(valid_vol, low_quantile)

    # Classify regimes
    high_mask = volatility > high_thresh
    low_mask = volatility < low_thresh
    normal_mask = ~high_mask & ~low_mask & ~np.isnan(volatility)

    def _compute_metrics(mask: np.ndarray) -> dict[str, float]:
        """Compute metrics for a regime subset."""
        if mask.sum() < 10:
            return {
                "ic": np.nan,
                "accuracy": np.nan,
                "sharpe": np.nan,
                "n": int(mask.sum()),
            }

        r = returns[mask]
        p = predictions[mask]

        # IC (Information Coefficient = correlation)
        ic = float(np.corrcoef(p, r)[0, 1]) if len(r) > 1 else np.nan

        # Accuracy (for classification: pred sign matches actual sign)
        accuracy = float(np.mean(np.sign(p) == np.sign(r)))

        # Simple Sharpe (not annualized, just for comparison)
        strategy_returns = r * np.sign(p)  # Long if pred > 0, short if pred < 0
        sharpe = (
            np.mean(strategy_returns) / np.std(strategy_returns)
            if np.std(strategy_returns) > 0
            else 0.0
        )

        return {
            "ic": float(ic) if not np.isnan(ic) else 0.0,
            "accuracy": accuracy,
            "sharpe": float(sharpe),
            "n": int(mask.sum()),
        }

    return RegimeMetrics(
        high_vol=_compute_metrics(high_mask),
        low_vol=_compute_metrics(low_mask),
        normal=_compute_metrics(normal_mask),
        regime_counts={
            "high": int(high_mask.sum()),
            "low": int(low_mask.sum()),
            "normal": int(normal_mask.sum()),
        },
    )


def summarize_regime_metrics(metrics: RegimeMetrics) -> str:
    """Format regime metrics as readable summary."""
    lines = [
        "Regime-Conditional Metrics:",
        "-" * 50,
        f"{'Regime':<12} {'IC':>8} {'Acc':>8} {'Sharpe':>8} {'N':>6}",
        "-" * 50,
    ]

    for regime, data in [
        ("High Vol", metrics.high_vol),
        ("Normal", metrics.normal),
        ("Low Vol", metrics.low_vol),
    ]:
        ic = f"{data['ic']:.3f}" if not np.isnan(data.get("ic", np.nan)) else "N/A"
        acc = (
            f"{data['accuracy']:.1%}"
            if not np.isnan(data.get("accuracy", np.nan))
            else "N/A"
        )
        sharpe = (
            f"{data['sharpe']:.3f}"
            if not np.isnan(data.get("sharpe", np.nan))
            else "N/A"
        )
        n = data.get("n", 0)
        lines.append(f"{regime:<12} {ic:>8} {acc:>8} {sharpe:>8} {n:>6}")

    lines.append("-" * 50)
    return "\n".join(lines)


# =============================================================================
# MULTIPLE TESTING CORRECTION
# =============================================================================


def bonferroni_correction(p_values: np.ndarray) -> np.ndarray:
    """
    Apply Bonferroni correction for multiple testing.

    Args:
        p_values: Array of p-values

    Returns:
        Corrected p-values (capped at 1.0)
    """
    n_tests = len(p_values)
    return np.minimum(p_values * n_tests, 1.0)


def benjamini_hochberg_correction(
    p_values: np.ndarray, fdr: float = 0.05
) -> np.ndarray:
    """
    Apply Benjamini-Hochberg FDR correction.

    Args:
        p_values: Array of p-values
        fdr: Target false discovery rate

    Returns:
        Array of booleans indicating which tests pass
    """
    n_tests = len(p_values)
    sorted_idx = np.argsort(p_values)
    sorted_p = p_values[sorted_idx]

    # BH threshold: p[i] <= (i+1) / n * fdr
    thresholds = np.arange(1, n_tests + 1) / n_tests * fdr
    passing = sorted_p <= thresholds

    # Find largest k where p[k] <= threshold
    if passing.any():
        max_k = np.max(np.where(passing)[0])
        result = np.zeros(n_tests, dtype=bool)
        result[sorted_idx[: max_k + 1]] = True
        return result
    else:
        return np.zeros(n_tests, dtype=bool)


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def validate_strategy_statistically(
    returns: np.ndarray,
    predictions: np.ndarray,
    n_trials: int = 20,
    periods_per_year: int = 1095,
) -> dict:
    """
    Comprehensive statistical validation of a trading strategy.

    Args:
        returns: Actual returns array
        predictions: Model predictions array
        n_trials: Number of parameter combinations tested
        periods_per_year: Periods per year for annualization

    Returns:
        Dictionary with all validation metrics
    """
    # Strategy returns (long if pred > 0, short otherwise)
    strategy_returns = returns * np.sign(predictions)

    # Deflated Sharpe Ratio
    try:
        dsr = compute_deflated_sharpe_ratio(
            strategy_returns, n_trials=n_trials, periods_per_year=periods_per_year
        )
    except ValueError:
        dsr = None

    # Regime metrics
    regime = compute_regime_metrics(returns, predictions)

    # Basic metrics
    ic = float(np.corrcoef(predictions, returns)[0, 1])
    accuracy = float(np.mean(np.sign(predictions) == np.sign(returns)))

    return {
        "ic": ic,
        "accuracy": accuracy,
        "deflated_sharpe": dsr.deflated_sharpe if dsr else None,
        "sharpe_ratio": dsr.sharpe_ratio if dsr else None,
        "dsr_p_value": dsr.p_value if dsr else None,
        "dsr_significant": dsr.is_significant if dsr else False,
        "regime_metrics": regime,
    }
