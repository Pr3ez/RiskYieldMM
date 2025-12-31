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


# =============================================================================
# PROBABILITY OF BACKTEST OVERFITTING (PBO)
# =============================================================================


@dataclass
class PBOResult:
    """Result from Probability of Backtest Overfitting calculation.

    Bailey & de Prado (2015) methodology:
    - Tests how often the best in-sample strategy ranks poorly out-of-sample
    - Uses combinatorial analysis of train/test splits

    Attributes:
        pbo: Probability of overfitting (0-1, lower = better)
        is_overfit: Whether PBO > 0.5 (strategy likely overfit)
        rank_correlation: Spearman correlation between IS and OOS ranks
        logit_slope: Slope from logit regression of relative OOS rank on IS rank
        n_trials: Number of strategy variations tested
        performance_degradation: Average (IS - OOS) / IS performance drop
    """

    pbo: float
    is_overfit: bool
    rank_correlation: float
    logit_slope: float
    n_trials: int
    performance_degradation: float

    def __repr__(self) -> str:
        status = "⚠️ OVERFIT" if self.is_overfit else "✓ OK"
        return (
            f"PBO={self.pbo:.1%} {status} "
            f"(rank_corr={self.rank_correlation:.2f}, n={self.n_trials})"
        )


def compute_pbo(
    is_scores: np.ndarray | list[float],
    oos_scores: np.ndarray | list[float],
) -> PBOResult:
    """
    Compute Probability of Backtest Overfitting (Bailey & de Prado 2015).

    PBO measures how likely it is that a strategy selected based on in-sample
    performance will underperform out-of-sample. High PBO (>0.5) indicates
    the selection process is no better than random.

    Method:
    1. Rank all N strategies by in-sample performance
    2. Rank same strategies by out-of-sample performance
    3. PBO = P(best IS strategy ranks in bottom half OOS)
    4. Also compute rank correlation as robustness check

    Interpretation:
    - PBO < 0.25: Good - strategy selection process is valid
    - PBO 0.25-0.50: Moderate - some overfitting risk
    - PBO > 0.50: Bad - strategy selection is overfit (worse than random)

    Args:
        is_scores: In-sample performance scores (e.g., Sharpe, IC) for N strategies
        oos_scores: Out-of-sample performance scores for same N strategies

    Returns:
        PBOResult with PBO estimate and diagnostics
    """
    is_arr = np.asarray(is_scores)
    oos_arr = np.asarray(oos_scores)

    if len(is_arr) != len(oos_arr):
        raise ValueError("IS and OOS score arrays must have same length")

    n = len(is_arr)
    if n < 3:
        raise ValueError(f"Need at least 3 trials for PBO, got {n}")

    # Get ranks (higher score = higher rank = better)
    # scipy.stats.rankdata: lowest value gets rank 1
    # We want highest value = highest rank, so negate
    is_ranks = stats.rankdata(-is_arr)  # Best IS gets rank 1
    oos_ranks = stats.rankdata(-oos_arr)  # Best OOS gets rank 1

    # Find index of best IS strategy (rank 1)
    best_is_idx = np.argmin(is_ranks)  # Index where IS rank = 1
    best_is_oos_rank = oos_ranks[best_is_idx]  # OOS rank of best IS strategy

    # PBO = probability best IS is in bottom half OOS
    # Simple estimate: is best IS in bottom half?
    median_rank = (n + 1) / 2
    pbo_simple = float(best_is_oos_rank > median_rank)

    # Better PBO estimate: relative position in OOS ranking
    # pbo_continuous = (oos_rank_of_best_is - 1) / (n - 1)
    # This gives smooth 0-1 estimate
    pbo_continuous = (best_is_oos_rank - 1) / (n - 1) if n > 1 else 0.5

    # Use continuous estimate for final PBO
    pbo = pbo_continuous

    # Rank correlation (Spearman)
    rank_corr, _ = stats.spearmanr(is_arr, oos_arr)
    rank_corr = float(rank_corr) if not np.isnan(rank_corr) else 0.0

    # Logit slope: regress relative OOS rank on IS rank
    # Negative slope = overfitting (high IS → low OOS)
    relative_oos = (oos_ranks - 1) / (n - 1) if n > 1 else oos_ranks
    try:
        slope, _, _, _, _ = stats.linregress(is_ranks, relative_oos)
        logit_slope = float(slope)
    except Exception:
        logit_slope = 0.0

    # Performance degradation: average relative drop from IS to OOS
    # (IS - OOS) / |IS| averaged across all trials
    with np.errstate(divide="ignore", invalid="ignore"):
        degradations = (is_arr - oos_arr) / np.abs(is_arr)
        degradations = np.where(np.isfinite(degradations), degradations, 0)
        avg_degradation = float(np.mean(degradations))

    return PBOResult(
        pbo=pbo,
        is_overfit=pbo > 0.5,
        rank_correlation=rank_corr,
        logit_slope=logit_slope,
        n_trials=n,
        performance_degradation=avg_degradation,
    )


def compute_pbo_from_splits(
    returns_matrix: np.ndarray,
    n_splits: int = 16,
    metric_fn: callable = None,
) -> PBOResult:
    """
    Compute PBO using combinatorial purged cross-validation approach.

    This is closer to the original Bailey & de Prado methodology which
    creates multiple train/test splits and measures overfitting across
    all combinations.

    Args:
        returns_matrix: (n_strategies, n_periods) matrix of strategy returns
        n_splits: Number of time periods to split into (must be even)
        metric_fn: Function to compute performance metric (default: Sharpe)

    Returns:
        PBOResult aggregated across all split combinations
    """
    if metric_fn is None:
        metric_fn = lambda x: np.mean(x) / np.std(x) if np.std(x) > 0 else 0.0

    n_strategies, n_periods = returns_matrix.shape

    if n_splits % 2 != 0:
        n_splits = n_splits - 1  # Make even

    # Split periods into blocks
    block_size = n_periods // n_splits
    blocks = [
        returns_matrix[:, i * block_size : (i + 1) * block_size]
        for i in range(n_splits)
    ]

    # Generate all S = C(n_splits, n_splits/2) combinations
    from itertools import combinations

    n_is = n_splits // 2
    split_combos = list(combinations(range(n_splits), n_is))

    pbo_values = []

    for is_blocks in split_combos:
        oos_blocks = [i for i in range(n_splits) if i not in is_blocks]

        # Concatenate IS and OOS returns
        is_returns = np.hstack([blocks[i] for i in is_blocks])
        oos_returns = np.hstack([blocks[i] for i in oos_blocks])

        # Compute metrics for each strategy
        is_scores = np.array([metric_fn(is_returns[s, :]) for s in range(n_strategies)])
        oos_scores = np.array(
            [metric_fn(oos_returns[s, :]) for s in range(n_strategies)]
        )

        # Get PBO for this split
        try:
            result = compute_pbo(is_scores, oos_scores)
            pbo_values.append(result.pbo)
        except ValueError:
            continue

    if not pbo_values:
        raise ValueError("No valid PBO calculations from splits")

    # Aggregate PBO across all splits
    avg_pbo = float(np.mean(pbo_values))

    # For other metrics, recompute on full IS/OOS (first half / second half)
    mid = n_periods // 2
    is_full = returns_matrix[:, :mid]
    oos_full = returns_matrix[:, mid:]

    is_scores = np.array([metric_fn(is_full[s, :]) for s in range(n_strategies)])
    oos_scores = np.array([metric_fn(oos_full[s, :]) for s in range(n_strategies)])

    rank_corr, _ = stats.spearmanr(is_scores, oos_scores)

    return PBOResult(
        pbo=avg_pbo,
        is_overfit=avg_pbo > 0.5,
        rank_correlation=float(rank_corr) if not np.isnan(rank_corr) else 0.0,
        logit_slope=0.0,  # Not computed for aggregate
        n_trials=n_strategies,
        performance_degradation=float(
            np.mean((is_scores - oos_scores) / np.abs(is_scores + 1e-10))
        ),
    )


# =============================================================================
# REGIME-CONDITIONAL METRICS
# =============================================================================


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
    is_scores: np.ndarray | None = None,
    oos_scores: np.ndarray | None = None,
) -> dict:
    """
    Comprehensive statistical validation of a trading strategy.

    Args:
        returns: Actual returns array
        predictions: Model predictions array
        n_trials: Number of parameter combinations tested
        periods_per_year: Periods per year for annualization
        is_scores: Optional in-sample scores for PBO (e.g., from Optuna trials)
        oos_scores: Optional out-of-sample scores for PBO

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

    # Probability of Backtest Overfitting
    pbo = None
    if is_scores is not None and oos_scores is not None:
        try:
            pbo = compute_pbo(is_scores, oos_scores)
        except ValueError:
            pbo = None

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
        "pbo": pbo.pbo if pbo else None,
        "pbo_is_overfit": pbo.is_overfit if pbo else None,
        "pbo_rank_correlation": pbo.rank_correlation if pbo else None,
        "regime_metrics": regime,
    }


# =============================================================================
# TAIL RISK METRICS (Tier 4)
# =============================================================================


@dataclass
class TailRiskMetrics:
    """Tail risk metrics for strategy evaluation.

    Attributes:
        var_95: Value at Risk at 95% confidence (5th percentile loss)
        var_99: Value at Risk at 99% confidence (1st percentile loss)
        cvar_95: Conditional VaR at 95% (expected loss beyond VaR95)
        cvar_99: Conditional VaR at 99% (expected loss beyond VaR99)
        max_drawdown: Maximum peak-to-trough decline
        max_drawdown_duration: Bars in longest drawdown
    """

    var_95: float
    var_99: float
    cvar_95: float
    cvar_99: float
    max_drawdown: float
    max_drawdown_duration: int

    def __repr__(self) -> str:
        return (
            f"TailRisk(VaR95={self.var_95:.4f}, CVaR95={self.cvar_95:.4f}, "
            f"MaxDD={self.max_drawdown:.2%})"
        )


def compute_tail_risk_metrics(
    returns: np.ndarray,
    confidence_levels: tuple[float, float] = (0.95, 0.99),
) -> TailRiskMetrics:
    """
    Compute tail risk metrics including VaR and CVaR.

    Value at Risk (VaR): Maximum expected loss at confidence level
    Conditional VaR (CVaR): Expected loss given that loss exceeds VaR
                           Also called Expected Shortfall (ES)

    Args:
        returns: Array of period returns
        confidence_levels: Tuple of (level1, level2) for VaR/CVaR

    Returns:
        TailRiskMetrics with VaR, CVaR, and drawdown metrics
    """
    returns = np.asarray(returns)

    if len(returns) < 10:
        return TailRiskMetrics(
            var_95=np.nan,
            var_99=np.nan,
            cvar_95=np.nan,
            cvar_99=np.nan,
            max_drawdown=np.nan,
            max_drawdown_duration=0,
        )

    # VaR: percentile of returns (negative = loss)
    alpha_95 = 1 - confidence_levels[0]  # 0.05
    alpha_99 = 1 - confidence_levels[1]  # 0.01

    var_95 = float(np.percentile(returns, alpha_95 * 100))
    var_99 = float(np.percentile(returns, alpha_99 * 100))

    # CVaR: mean of returns below VaR (expected shortfall)
    cvar_95 = (
        float(np.mean(returns[returns <= var_95]))
        if np.any(returns <= var_95)
        else var_95
    )
    cvar_99 = (
        float(np.mean(returns[returns <= var_99]))
        if np.any(returns <= var_99)
        else var_99
    )

    # Max drawdown and duration
    cumulative = np.cumsum(returns)
    running_max = np.maximum.accumulate(cumulative)
    drawdowns = cumulative - running_max
    max_drawdown = float(np.min(drawdowns))

    # Drawdown duration: longest period below previous peak
    in_drawdown = drawdowns < 0
    max_duration = 0
    current_duration = 0
    for is_dd in in_drawdown:
        if is_dd:
            current_duration += 1
            max_duration = max(max_duration, current_duration)
        else:
            current_duration = 0

    return TailRiskMetrics(
        var_95=var_95,
        var_99=var_99,
        cvar_95=cvar_95,
        cvar_99=cvar_99,
        max_drawdown=max_drawdown,
        max_drawdown_duration=max_duration,
    )


# =============================================================================
# TRADE ANALYSIS METRICS (Tier 4)
# =============================================================================


@dataclass
class TradeMetrics:
    """Trade-level analysis metrics.

    Attributes:
        win_rate: Fraction of profitable trades
        profit_factor: Gross profit / gross loss (>1 = profitable)
        avg_win: Average return on winning trades
        avg_loss: Average return on losing trades
        win_loss_ratio: avg_win / |avg_loss| (reward/risk)
        n_trades: Total number of trades
        n_wins: Number of winning trades
        n_losses: Number of losing trades
        expectancy: Expected return per trade
    """

    win_rate: float
    profit_factor: float
    avg_win: float
    avg_loss: float
    win_loss_ratio: float
    n_trades: int
    n_wins: int
    n_losses: int
    expectancy: float

    def __repr__(self) -> str:
        return (
            f"Trades(WR={self.win_rate:.1%}, PF={self.profit_factor:.2f}, "
            f"E={self.expectancy:.4f}, n={self.n_trades})"
        )


def compute_trade_metrics(returns: np.ndarray) -> TradeMetrics:
    """
    Compute trade-level metrics from strategy returns.

    Args:
        returns: Array of per-trade returns (should exclude flat periods)

    Returns:
        TradeMetrics with win rate, profit factor, etc.
    """
    returns = np.asarray(returns)

    # Filter to actual trades (non-zero returns)
    trades = returns[returns != 0]
    n_trades = len(trades)

    if n_trades == 0:
        return TradeMetrics(
            win_rate=0.0,
            profit_factor=0.0,
            avg_win=0.0,
            avg_loss=0.0,
            win_loss_ratio=0.0,
            n_trades=0,
            n_wins=0,
            n_losses=0,
            expectancy=0.0,
        )

    # Separate wins and losses
    wins = trades[trades > 0]
    losses = trades[trades < 0]

    n_wins = len(wins)
    n_losses = len(losses)

    # Win rate
    win_rate = n_wins / n_trades if n_trades > 0 else 0.0

    # Average win/loss
    avg_win = float(np.mean(wins)) if n_wins > 0 else 0.0
    avg_loss = float(np.mean(losses)) if n_losses > 0 else 0.0

    # Win/loss ratio (reward/risk)
    win_loss_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else float("inf")

    # Profit factor = gross profit / gross loss
    gross_profit = float(np.sum(wins)) if n_wins > 0 else 0.0
    gross_loss = abs(float(np.sum(losses))) if n_losses > 0 else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    # Expectancy = (win_rate * avg_win) - (loss_rate * |avg_loss|)
    expectancy = float(np.mean(trades))

    return TradeMetrics(
        win_rate=win_rate,
        profit_factor=profit_factor,
        avg_win=avg_win,
        avg_loss=avg_loss,
        win_loss_ratio=win_loss_ratio,
        n_trades=n_trades,
        n_wins=n_wins,
        n_losses=n_losses,
        expectancy=expectancy,
    )


def compute_sortino_ratio(
    returns: np.ndarray,
    target_return: float = 0.0,
    periods_per_year: int = 1095,
) -> float:
    """
    Compute Sortino Ratio (downside-deviation Sharpe).

    Unlike Sharpe which penalizes all volatility, Sortino only
    penalizes downside volatility (returns below target).

    Formula: (Mean Return - Target) / Downside Deviation

    Args:
        returns: Array of period returns
        target_return: Minimum acceptable return (default 0)
        periods_per_year: For annualization (1095 for 8h bars)

    Returns:
        Annualized Sortino Ratio
    """
    returns = np.asarray(returns)

    if len(returns) < 10:
        return np.nan

    # Excess returns below target
    downside_returns = returns - target_return
    downside_returns = downside_returns[downside_returns < 0]

    if len(downside_returns) == 0:
        return float("inf")  # No downside, infinite Sortino

    # Downside deviation (std of negative excess returns)
    downside_deviation = np.sqrt(np.mean(downside_returns**2))

    if downside_deviation == 0:
        return float("inf")

    # Annualized Sortino
    mean_excess = np.mean(returns) - target_return
    sortino = (mean_excess / downside_deviation) * np.sqrt(periods_per_year)

    return float(sortino)


# =============================================================================
# CONFORMAL-AWARE POSITION SIZING (Tier 4 - Key Innovation)
# =============================================================================


@dataclass
class ConformalSizingMetrics:
    """Metrics comparing fixed vs conformal-aware position sizing.

    Attributes:
        fixed_sharpe: Sharpe with fixed position size (±1)
        conformal_sharpe: Sharpe with conformal-scaled positions
        fixed_return: Total return with fixed sizing
        conformal_return: Total return with conformal sizing
        avg_position_size: Average position size under conformal sizing
        sizing_benefit: conformal_sharpe - fixed_sharpe
        uncertainty_correlation: Correlation between uncertainty and |error|
    """

    fixed_sharpe: float
    conformal_sharpe: float
    fixed_return: float
    conformal_return: float
    avg_position_size: float
    sizing_benefit: float
    uncertainty_correlation: float

    def __repr__(self) -> str:
        benefit = "+" if self.sizing_benefit > 0 else ""
        return (
            f"ConformalSizing(fixed_SR={self.fixed_sharpe:.3f}, "
            f"conf_SR={self.conformal_sharpe:.3f}, "
            f"benefit={benefit}{self.sizing_benefit:.3f})"
        )


def compute_conformal_sizing_metrics(
    returns: np.ndarray,
    predictions: np.ndarray,
    interval_widths: np.ndarray,
    scaling_factor: float = 1.0,
    min_position: float = 0.1,
    max_position: float = 1.0,
    periods_per_year: int = 1095,
) -> ConformalSizingMetrics:
    """
    Compare fixed vs conformal-aware position sizing.

    Conformal sizing principle:
    - Narrow interval = high confidence = larger position
    - Wide interval = low confidence = smaller position

    Position formula:
        position = clip(base / (1 + k * normalized_width), min, max)

    Where normalized_width = width / median_width

    Args:
        returns: Actual returns (y_true)
        predictions: Model predictions (y_pred)
        interval_widths: Conformal prediction interval widths
        scaling_factor: k in formula (higher = more aggressive scaling)
        min_position: Minimum position size (0.1 = 10%)
        max_position: Maximum position size (1.0 = 100%)
        periods_per_year: For Sharpe annualization

    Returns:
        ConformalSizingMetrics comparing fixed vs conformal sizing
    """
    returns = np.asarray(returns)
    predictions = np.asarray(predictions)
    interval_widths = np.asarray(interval_widths)

    # Handle NaN/Inf in interval widths
    valid_mask = (
        np.isfinite(interval_widths) & np.isfinite(returns) & np.isfinite(predictions)
    )

    if np.sum(valid_mask) < 10:
        return ConformalSizingMetrics(
            fixed_sharpe=np.nan,
            conformal_sharpe=np.nan,
            fixed_return=np.nan,
            conformal_return=np.nan,
            avg_position_size=np.nan,
            sizing_benefit=np.nan,
            uncertainty_correlation=np.nan,
        )

    returns = returns[valid_mask]
    predictions = predictions[valid_mask]
    interval_widths = interval_widths[valid_mask]

    # Direction from predictions
    directions = np.sign(predictions)

    # Fixed sizing: always ±1
    fixed_returns = directions * returns

    # Conformal sizing: scale by inverse of normalized width
    median_width = np.median(interval_widths)
    if median_width <= 0:
        median_width = np.mean(interval_widths)
    if median_width <= 0:
        median_width = 1.0  # Fallback

    normalized_widths = interval_widths / median_width

    # Position size: inverse relationship with uncertainty
    # Higher scaling_factor = more aggressive reduction for uncertain predictions
    position_sizes = max_position / (1 + scaling_factor * normalized_widths)
    position_sizes = np.clip(position_sizes, min_position, max_position)

    # Conformal-sized returns
    conformal_returns = directions * position_sizes * returns

    # Compute Sharpe ratios
    def _sharpe(ret: np.ndarray) -> float:
        if np.std(ret) == 0:
            return 0.0
        return float(np.mean(ret) / np.std(ret) * np.sqrt(periods_per_year))

    fixed_sharpe = _sharpe(fixed_returns)
    conformal_sharpe = _sharpe(conformal_returns)

    # Total returns
    fixed_return = float(np.sum(fixed_returns))
    conformal_return = float(np.sum(conformal_returns))

    # Average position size
    avg_position = float(np.mean(position_sizes))

    # Correlation between uncertainty and actual error
    # If high uncertainty correlates with high error, conformal sizing helps
    errors = np.abs(returns - predictions)
    uncertainty_corr, _ = stats.spearmanr(interval_widths, errors)
    uncertainty_corr = (
        float(uncertainty_corr) if not np.isnan(uncertainty_corr) else 0.0
    )

    return ConformalSizingMetrics(
        fixed_sharpe=fixed_sharpe,
        conformal_sharpe=conformal_sharpe,
        fixed_return=fixed_return,
        conformal_return=conformal_return,
        avg_position_size=avg_position,
        sizing_benefit=conformal_sharpe - fixed_sharpe,
        uncertainty_correlation=uncertainty_corr,
    )


# =============================================================================
# TIER 5: DISTRIBUTION SHIFT DETECTION
# =============================================================================


@dataclass
class PSIResult:
    """Population Stability Index result for a single feature.

    PSI Interpretation:
        - PSI < 0.10: No significant shift
        - 0.10 <= PSI < 0.25: Moderate shift, monitor closely
        - PSI >= 0.25: Significant shift, investigate/retrain

    Reference:
        Siddiqi, N. (2006). "Credit Risk Scorecards"
    """

    feature_name: str
    psi_value: float
    shift_level: str  # 'none', 'moderate', 'significant'
    n_bins: int
    reference_distribution: np.ndarray
    current_distribution: np.ndarray

    def __repr__(self) -> str:
        return f"PSI({self.feature_name})={self.psi_value:.4f} [{self.shift_level}]"


@dataclass
class DistributionShiftResult:
    """Comprehensive distribution shift analysis result."""

    # PSI results per feature
    psi_results: dict[str, PSIResult]
    # Overall shift summary
    mean_psi: float
    max_psi: float
    n_significant_shifts: int
    n_moderate_shifts: int
    shifted_features: list[str]
    # KS test results (feature -> p-value)
    ks_p_values: dict[str, float]
    # Overall assessment
    overall_shift_detected: bool
    shift_severity: str  # 'none', 'low', 'moderate', 'high'

    def __repr__(self) -> str:
        return (
            f"DistributionShift(mean_psi={self.mean_psi:.4f}, "
            f"shifted={self.n_significant_shifts}, severity={self.shift_severity})"
        )


def compute_psi(
    reference: np.ndarray,
    current: np.ndarray,
    n_bins: int = 10,
    epsilon: float = 1e-6,
) -> float:
    """
    Compute Population Stability Index between reference and current distributions.

    PSI = Σ (current% - reference%) × ln(current% / reference%)

    Args:
        reference: Reference (training) distribution
        current: Current (production/test) distribution
        n_bins: Number of bins for discretization
        epsilon: Small value to avoid log(0)

    Returns:
        PSI value (higher = more shift)
    """
    # Handle edge cases
    reference = np.asarray(reference).flatten()
    current = np.asarray(current).flatten()

    if len(reference) < n_bins or len(current) < n_bins:
        return 0.0

    # Remove NaN/Inf
    reference = reference[np.isfinite(reference)]
    current = current[np.isfinite(current)]

    if len(reference) == 0 or len(current) == 0:
        return 0.0

    # Create bins from reference distribution
    _, bin_edges = np.histogram(reference, bins=n_bins)

    # Compute proportions in each bin
    ref_counts, _ = np.histogram(reference, bins=bin_edges)
    cur_counts, _ = np.histogram(current, bins=bin_edges)

    # Convert to proportions
    ref_props = ref_counts / len(reference) + epsilon
    cur_props = cur_counts / len(current) + epsilon

    # PSI formula
    psi = np.sum((cur_props - ref_props) * np.log(cur_props / ref_props))

    return float(psi)


def compute_feature_psi(
    reference_df,
    current_df,
    feature_columns: list[str] | None = None,
    n_bins: int = 10,
) -> dict[str, PSIResult]:
    """
    Compute PSI for multiple features.

    Args:
        reference_df: Reference (training) DataFrame
        current_df: Current (test) DataFrame
        feature_columns: List of columns to analyze. If None, use all numeric.
        n_bins: Number of bins for discretization

    Returns:
        Dictionary of feature name -> PSIResult
    """
    if feature_columns is None:
        # Use all numeric columns present in both DataFrames
        ref_numeric = set(reference_df.select_dtypes(include=[np.number]).columns)
        cur_numeric = set(current_df.select_dtypes(include=[np.number]).columns)
        feature_columns = list(ref_numeric & cur_numeric)

    results = {}
    for col in feature_columns:
        if col not in reference_df.columns or col not in current_df.columns:
            continue

        ref_values = reference_df[col].values
        cur_values = current_df[col].values

        psi_value = compute_psi(ref_values, cur_values, n_bins=n_bins)

        # Determine shift level
        if psi_value < 0.10:
            shift_level = "none"
        elif psi_value < 0.25:
            shift_level = "moderate"
        else:
            shift_level = "significant"

        # Store distributions for analysis
        _, bin_edges = np.histogram(ref_values[np.isfinite(ref_values)], bins=n_bins)
        ref_dist, _ = np.histogram(
            ref_values[np.isfinite(ref_values)], bins=bin_edges, density=True
        )
        cur_dist, _ = np.histogram(
            cur_values[np.isfinite(cur_values)], bins=bin_edges, density=True
        )

        results[col] = PSIResult(
            feature_name=col,
            psi_value=psi_value,
            shift_level=shift_level,
            n_bins=n_bins,
            reference_distribution=ref_dist,
            current_distribution=cur_dist,
        )

    return results


def compute_ks_test(
    reference: np.ndarray,
    current: np.ndarray,
) -> tuple[float, float]:
    """
    Kolmogorov-Smirnov test for distribution difference.

    Args:
        reference: Reference distribution
        current: Current distribution

    Returns:
        Tuple of (KS statistic, p-value)
    """
    reference = np.asarray(reference).flatten()
    current = np.asarray(current).flatten()

    # Remove NaN/Inf
    reference = reference[np.isfinite(reference)]
    current = current[np.isfinite(current)]

    if len(reference) < 5 or len(current) < 5:
        return 0.0, 1.0

    statistic, p_value = stats.ks_2samp(reference, current)
    return float(statistic), float(p_value)


def compute_distribution_shift(
    reference_df,
    current_df,
    feature_columns: list[str] | None = None,
    n_bins: int = 10,
    ks_alpha: float = 0.05,
) -> DistributionShiftResult:
    """
    Comprehensive distribution shift analysis.

    Combines PSI and KS tests to detect covariate shift.

    Args:
        reference_df: Reference (training) DataFrame
        current_df: Current (test) DataFrame
        feature_columns: Features to analyze
        n_bins: Number of bins for PSI
        ks_alpha: Significance level for KS test

    Returns:
        DistributionShiftResult with detailed analysis
    """
    # Compute PSI for all features
    psi_results = compute_feature_psi(reference_df, current_df, feature_columns, n_bins)

    if not psi_results:
        return DistributionShiftResult(
            psi_results={},
            mean_psi=0.0,
            max_psi=0.0,
            n_significant_shifts=0,
            n_moderate_shifts=0,
            shifted_features=[],
            ks_p_values={},
            overall_shift_detected=False,
            shift_severity="none",
        )

    # Compute KS tests
    ks_p_values = {}
    for col in psi_results.keys():
        _, p_value = compute_ks_test(reference_df[col].values, current_df[col].values)
        ks_p_values[col] = p_value

    # Aggregate statistics
    psi_values = [r.psi_value for r in psi_results.values()]
    mean_psi = float(np.mean(psi_values))
    max_psi = float(np.max(psi_values))

    n_significant = sum(
        1 for r in psi_results.values() if r.shift_level == "significant"
    )
    n_moderate = sum(1 for r in psi_results.values() if r.shift_level == "moderate")

    shifted_features = [
        r.feature_name
        for r in psi_results.values()
        if r.shift_level in ("moderate", "significant")
    ]

    # Determine overall severity
    # Significant if: >20% features shifted OR max_psi > 0.25 OR mean_psi > 0.15
    total_features = len(psi_results)
    shift_ratio = (
        (n_significant + n_moderate) / total_features if total_features > 0 else 0
    )

    if n_significant >= 3 or max_psi >= 0.5 or shift_ratio >= 0.3:
        shift_severity = "high"
        overall_shift = True
    elif n_significant >= 1 or max_psi >= 0.25 or shift_ratio >= 0.2:
        shift_severity = "moderate"
        overall_shift = True
    elif n_moderate >= 2 or mean_psi >= 0.10:
        shift_severity = "low"
        overall_shift = True
    else:
        shift_severity = "none"
        overall_shift = False

    return DistributionShiftResult(
        psi_results=psi_results,
        mean_psi=mean_psi,
        max_psi=max_psi,
        n_significant_shifts=n_significant,
        n_moderate_shifts=n_moderate,
        shifted_features=shifted_features,
        ks_p_values=ks_p_values,
        overall_shift_detected=overall_shift,
        shift_severity=shift_severity,
    )


# =============================================================================
# TIER 5: CONCEPT DRIFT DETECTION (Rolling Metrics)
# =============================================================================


@dataclass
class RollingMetricsResult:
    """Rolling performance metrics to detect concept drift."""

    # Time-indexed rolling metrics
    rolling_ic: np.ndarray  # Rolling Information Coefficient
    rolling_sharpe: np.ndarray  # Rolling Sharpe Ratio
    rolling_accuracy: np.ndarray | None  # For classification (optional)

    # Drift detection
    ic_trend: float  # Slope of IC over time (negative = degradation)
    sharpe_trend: float  # Slope of Sharpe over time
    ic_volatility: float  # Std of rolling IC
    sharpe_volatility: float  # Std of rolling Sharpe

    # Degradation flags
    ic_degrading: bool  # True if IC trend significantly negative
    sharpe_degrading: bool  # True if Sharpe trend significantly negative
    recent_vs_early_ic: float  # Ratio of recent IC to early IC
    concept_drift_detected: bool

    def __repr__(self) -> str:
        drift = "DRIFT" if self.concept_drift_detected else "stable"
        return (
            f"RollingMetrics(ic_trend={self.ic_trend:.4f}, "
            f"sharpe_trend={self.sharpe_trend:.4f}, {drift})"
        )


def compute_rolling_ic(
    predictions: np.ndarray,
    actuals: np.ndarray,
    window_size: int = 30,
    min_periods: int = 10,
) -> np.ndarray:
    """
    Compute rolling Information Coefficient (Spearman correlation).

    Args:
        predictions: Model predictions
        actuals: Actual values
        window_size: Rolling window size
        min_periods: Minimum periods for valid calculation

    Returns:
        Array of rolling IC values (NaN where insufficient data)
    """
    n = len(predictions)
    rolling_ic = np.full(n, np.nan)

    for i in range(min_periods - 1, n):
        start_idx = max(0, i - window_size + 1)
        window_pred = predictions[start_idx : i + 1]
        window_actual = actuals[start_idx : i + 1]

        # Need valid data
        valid_mask = np.isfinite(window_pred) & np.isfinite(window_actual)
        if np.sum(valid_mask) >= min_periods:
            corr, _ = stats.spearmanr(
                window_pred[valid_mask], window_actual[valid_mask]
            )
            rolling_ic[i] = corr if np.isfinite(corr) else 0.0

    return rolling_ic


def compute_rolling_sharpe(
    returns: np.ndarray,
    window_size: int = 30,
    min_periods: int = 10,
    periods_per_year: int = 1095,
) -> np.ndarray:
    """
    Compute rolling Sharpe Ratio.

    Args:
        returns: Strategy returns
        window_size: Rolling window size
        min_periods: Minimum periods for valid calculation
        periods_per_year: Annualization factor

    Returns:
        Array of rolling Sharpe values
    """
    n = len(returns)
    rolling_sharpe = np.full(n, np.nan)

    for i in range(min_periods - 1, n):
        start_idx = max(0, i - window_size + 1)
        window_returns = returns[start_idx : i + 1]

        valid_returns = window_returns[np.isfinite(window_returns)]
        if len(valid_returns) >= min_periods:
            mean_ret = np.mean(valid_returns)
            std_ret = np.std(valid_returns, ddof=1)
            if std_ret > 0:
                sharpe = mean_ret / std_ret * np.sqrt(periods_per_year)
                rolling_sharpe[i] = sharpe

    return rolling_sharpe


def compute_rolling_metrics(
    predictions: np.ndarray,
    actuals: np.ndarray,
    returns: np.ndarray | None = None,
    window_size: int = 30,
    min_periods: int = 10,
    degradation_threshold: float = -0.01,
) -> RollingMetricsResult:
    """
    Compute rolling metrics and detect concept drift.

    Concept drift is detected when:
    - IC trend is significantly negative (model losing predictive power)
    - Sharpe trend is significantly negative (strategy degrading)
    - Recent performance << early performance

    Args:
        predictions: Model predictions
        actuals: Actual values
        returns: Strategy returns (optional, uses prediction*actual if None)
        window_size: Rolling window size
        min_periods: Minimum periods for valid calculation
        degradation_threshold: Slope below this indicates degradation

    Returns:
        RollingMetricsResult with drift analysis
    """
    predictions = np.asarray(predictions).flatten()
    actuals = np.asarray(actuals).flatten()

    if returns is None:
        # Use direction-based returns as proxy
        returns = np.sign(predictions) * actuals

    returns = np.asarray(returns).flatten()

    # Compute rolling metrics
    rolling_ic = compute_rolling_ic(predictions, actuals, window_size, min_periods)
    rolling_sharpe = compute_rolling_sharpe(returns, window_size, min_periods)

    # Compute trends (linear regression slope over valid values)
    def _compute_trend(values: np.ndarray) -> float:
        valid_mask = np.isfinite(values)
        if np.sum(valid_mask) < 10:
            return 0.0
        valid_values = values[valid_mask]
        x = np.arange(len(valid_values))
        slope, _, _, _, _ = stats.linregress(x, valid_values)
        return float(slope)

    ic_trend = _compute_trend(rolling_ic)
    sharpe_trend = _compute_trend(rolling_sharpe)

    # Volatility of metrics
    ic_vol = float(np.nanstd(rolling_ic))
    sharpe_vol = float(np.nanstd(rolling_sharpe))

    # Compare early vs recent (first 1/3 vs last 1/3)
    valid_ic = rolling_ic[np.isfinite(rolling_ic)]
    if len(valid_ic) >= 6:
        n_third = len(valid_ic) // 3
        early_ic = np.mean(valid_ic[:n_third])
        recent_ic = np.mean(valid_ic[-n_third:])
        recent_vs_early = recent_ic / early_ic if early_ic != 0 else 1.0
    else:
        recent_vs_early = 1.0

    # Detect degradation
    ic_degrading = ic_trend < degradation_threshold
    sharpe_degrading = sharpe_trend < degradation_threshold

    # Concept drift if either metric is degrading significantly
    # OR recent performance is much worse than early performance
    concept_drift = (
        ic_degrading
        or sharpe_degrading
        or recent_vs_early < 0.5  # Recent IC is less than half of early IC
    )

    return RollingMetricsResult(
        rolling_ic=rolling_ic,
        rolling_sharpe=rolling_sharpe,
        rolling_accuracy=None,  # Could add for classification
        ic_trend=ic_trend,
        sharpe_trend=sharpe_trend,
        ic_volatility=ic_vol,
        sharpe_volatility=sharpe_vol,
        ic_degrading=ic_degrading,
        sharpe_degrading=sharpe_degrading,
        recent_vs_early_ic=float(recent_vs_early),
        concept_drift_detected=concept_drift,
    )
