"""
PositionSizer: Fractional Kelly position sizing with regime adjustment.

This module implements optimal position sizing that:
1. Uses fractional Kelly criterion (conservative)
2. Adjusts for volatility regime
3. Scales with prediction confidence
4. Respects maximum position limits

Key formulas:
- Kelly: f* = (p × b - q) / b where p=win_rate, b=avg_win/avg_loss, q=1-p
- Position = kelly_fraction × f* × regime_mult × confidence_mult × capital

References:
- Kelly (1956): "A New Interpretation of Information Rate"
- Thorp: "The Kelly Criterion in Blackjack, Sports Betting, and the Stock Market"
- López de Prado: "Advances in Financial Machine Learning" (Meta-labeling)
"""

from dataclasses import dataclass

import numpy as np


@dataclass
class PositionSizingConfig:
    """Configuration for position sizing.

    Attributes:
        kelly_fraction: Fraction of Kelly to use (0.25 = quarter Kelly)
        max_position_pct: Maximum position as % of capital
        min_position_pct: Minimum position as % of capital
        regime_multipliers: Position multipliers by volatility regime
        use_confidence_scaling: Whether to scale by prediction confidence
    """

    # Kelly settings
    kelly_fraction: float = 0.25  # Quarter Kelly (conservative)

    # Position limits (as fraction of capital)
    max_position_pct: float = 0.30  # Max 30% of capital
    min_position_pct: float = 0.01  # Min 1% of capital

    # Regime multipliers
    regime_multiplier_low: float = 1.3  # Increase in low vol
    regime_multiplier_medium: float = 1.0  # Base
    regime_multiplier_high: float = 0.5  # Decrease in high vol

    # Confidence scaling
    use_confidence_scaling: bool = True
    min_confidence_mult: float = 0.5  # Minimum multiplier for low confidence

    # Safety
    max_kelly_raw: float = 0.5  # Cap raw Kelly at 50% even before fraction


@dataclass
class PositionSizeResult:
    """Result of position size calculation.

    Attributes:
        position_size: Final position size in capital units
        position_pct: Position as percentage of capital
        kelly_raw: Raw Kelly fraction (before applying kelly_fraction)
        kelly_adjusted: Kelly after applying fraction
        regime_mult: Regime multiplier applied
        confidence_mult: Confidence multiplier applied
        was_capped: Whether position was capped by max limit
    """

    position_size: float
    position_pct: float
    kelly_raw: float
    kelly_adjusted: float
    regime_mult: float
    confidence_mult: float
    was_capped: bool


@dataclass
class TradeStats:
    """Historical trade statistics for Kelly calculation.

    Can be computed from backtest results or estimated from model metrics.
    """

    win_rate: float  # Probability of winning trade
    avg_win: float  # Average winning trade return (positive)
    avg_loss: float  # Average losing trade return (positive, will be negated)
    n_trades: int = 0  # Number of trades in sample

    @classmethod
    def from_returns(cls, returns: np.ndarray) -> "TradeStats":
        """Compute trade stats from array of trade returns.

        Args:
            returns: Array of trade returns (positive and negative)

        Returns:
            TradeStats instance
        """
        returns = np.asarray(returns)
        wins = returns[returns > 0]
        losses = returns[returns < 0]

        win_rate = len(wins) / len(returns) if len(returns) > 0 else 0.5
        avg_win = np.mean(wins) if len(wins) > 0 else 0.01
        avg_loss = np.abs(np.mean(losses)) if len(losses) > 0 else 0.01

        return cls(
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            n_trades=len(returns),
        )

    @classmethod
    def from_model_accuracy(
        cls,
        accuracy: float,
        avg_return: float = 0.02,
        return_asymmetry: float = 1.0,
    ) -> "TradeStats":
        """Estimate trade stats from model accuracy.

        Useful when we don't have actual trade returns but know model accuracy.

        Args:
            accuracy: Model accuracy (e.g., 0.70 for 70%)
            avg_return: Expected average absolute return per trade
            return_asymmetry: avg_win / avg_loss ratio (1.0 = symmetric)

        Returns:
            TradeStats instance
        """
        # If asymmetry > 1, wins are larger than losses
        # If asymmetry < 1, losses are larger than wins
        avg_loss = avg_return / (1 + return_asymmetry)
        avg_win = avg_return - avg_loss

        return cls(
            win_rate=accuracy,
            avg_win=avg_win,
            avg_loss=avg_loss,
            n_trades=0,
        )


class PositionSizer:
    """Calculate optimal position size using fractional Kelly.

    This sizer implements a conservative Kelly approach:
    1. Compute raw Kelly fraction from trade statistics
    2. Apply fractional Kelly (e.g., 0.25 = quarter Kelly)
    3. Adjust for volatility regime
    4. Scale by prediction confidence
    5. Cap at maximum position limit

    Example:
        >>> config = PositionSizingConfig(kelly_fraction=0.25)
        >>> sizer = PositionSizer(config)
        >>> stats = TradeStats(win_rate=0.70, avg_win=0.03, avg_loss=0.02)
        >>> result = sizer.calculate(
        ...     capital=10000,
        ...     trade_stats=stats,
        ...     vol_regime="MEDIUM",
        ...     confidence=0.8,
        ... )
        >>> print(f"Position: ${result.position_size:.2f}")
    """

    def __init__(self, config: PositionSizingConfig | None = None):
        """Initialize with configuration.

        Args:
            config: PositionSizingConfig instance, or None for defaults
        """
        self.config = config or PositionSizingConfig()

    def calculate_kelly(self, trade_stats: TradeStats) -> float:
        """Calculate raw Kelly fraction from trade statistics.

        Kelly formula: f* = (p × b - q) / b
        Where:
            p = probability of winning
            b = win/loss ratio (avg_win / avg_loss)
            q = probability of losing (1 - p)

        Args:
            trade_stats: Historical trade statistics

        Returns:
            Raw Kelly fraction (can be > 1 or negative)
        """
        p = trade_stats.win_rate
        q = 1 - p

        # Avoid division by zero
        if trade_stats.avg_loss <= 0:
            return 0.0

        b = trade_stats.avg_win / trade_stats.avg_loss

        # Kelly formula
        kelly = (p * b - q) / b

        return kelly

    def get_regime_multiplier(self, vol_regime: str) -> float:
        """Get position multiplier for volatility regime.

        Args:
            vol_regime: Volatility regime ("LOW", "MEDIUM", "HIGH")

        Returns:
            Multiplier to apply to position size
        """
        cfg = self.config
        vol_regime = vol_regime.upper()

        if vol_regime == "LOW":
            return cfg.regime_multiplier_low
        elif vol_regime == "HIGH":
            return cfg.regime_multiplier_high
        else:  # MEDIUM or unknown
            return cfg.regime_multiplier_medium

    def get_confidence_multiplier(self, confidence: float) -> float:
        """Get position multiplier based on prediction confidence.

        Args:
            confidence: Confidence score in [0, 1]

        Returns:
            Multiplier in [min_confidence_mult, 1.0]
        """
        if not self.config.use_confidence_scaling:
            return 1.0

        confidence = np.clip(confidence, 0.0, 1.0)
        min_mult = self.config.min_confidence_mult

        # Linear scaling: confidence=1 → mult=1, confidence=0 → mult=min_mult
        return min_mult + confidence * (1.0 - min_mult)

    def calculate(
        self,
        capital: float,
        trade_stats: TradeStats,
        vol_regime: str = "MEDIUM",
        confidence: float = 1.0,
        max_leverage: float | None = None,
    ) -> PositionSizeResult:
        """Calculate optimal position size.

        Args:
            capital: Total available capital
            trade_stats: Historical trade statistics
            vol_regime: Current volatility regime
            confidence: Prediction confidence [0, 1]
            max_leverage: Optional leverage cap from LeverageCalculator

        Returns:
            PositionSizeResult with all details
        """
        cfg = self.config

        # Step 1: Calculate raw Kelly
        kelly_raw = self.calculate_kelly(trade_stats)

        # Cap raw Kelly for safety
        kelly_raw = np.clip(kelly_raw, -cfg.max_kelly_raw, cfg.max_kelly_raw)

        # Step 2: Apply fractional Kelly
        kelly_adjusted = kelly_raw * cfg.kelly_fraction

        # Step 3: Get multipliers
        regime_mult = self.get_regime_multiplier(vol_regime)
        conf_mult = self.get_confidence_multiplier(confidence)

        # Step 4: Calculate position as fraction of capital
        position_pct = kelly_adjusted * regime_mult * conf_mult

        # Step 5: Apply position limits
        was_capped = False
        if position_pct > cfg.max_position_pct:
            position_pct = cfg.max_position_pct
            was_capped = True
        elif position_pct < cfg.min_position_pct:
            position_pct = cfg.min_position_pct

        # If Kelly is negative (no edge), don't trade
        if kelly_raw <= 0:
            position_pct = 0.0

        # Step 6: Apply leverage cap if provided
        if max_leverage is not None and position_pct > 0:
            # position_pct represents notional, leverage affects margin
            # This is a simplification - actual leverage affects margin usage
            # For now, we cap position_pct at max_leverage * base_margin
            # where base_margin is typically 10% for 10x leverage
            max_from_leverage = 1.0 / max_leverage  # Inverse relationship
            if position_pct > max_from_leverage:
                position_pct = min(position_pct, cfg.max_position_pct)

        # Calculate absolute position size
        position_size = position_pct * capital

        return PositionSizeResult(
            position_size=position_size,
            position_pct=position_pct,
            kelly_raw=kelly_raw,
            kelly_adjusted=kelly_adjusted,
            regime_mult=regime_mult,
            confidence_mult=conf_mult,
            was_capped=was_capped,
        )

    def calculate_from_accuracy(
        self,
        capital: float,
        accuracy: float,
        avg_return: float = 0.02,
        vol_regime: str = "MEDIUM",
        confidence: float = 1.0,
    ) -> PositionSizeResult:
        """Convenience method to calculate position from model accuracy.

        Args:
            capital: Total available capital
            accuracy: Model accuracy (e.g., 0.70)
            avg_return: Expected average trade return
            vol_regime: Current volatility regime
            confidence: Prediction confidence [0, 1]

        Returns:
            PositionSizeResult
        """
        trade_stats = TradeStats.from_model_accuracy(accuracy, avg_return)
        return self.calculate(capital, trade_stats, vol_regime, confidence)


class AdaptivePositionSizer(PositionSizer):
    """Position sizer that adapts based on recent performance.

    Reduces position size during drawdowns, increases after winning streaks.
    """

    def __init__(
        self,
        config: PositionSizingConfig | None = None,
        drawdown_threshold: float = 0.10,  # 10% drawdown
        drawdown_reduction: float = 0.5,  # Reduce to 50%
        winning_streak_threshold: int = 5,
        winning_streak_boost: float = 1.2,  # Increase by 20%
    ):
        super().__init__(config)
        self.drawdown_threshold = drawdown_threshold
        self.drawdown_reduction = drawdown_reduction
        self.winning_streak_threshold = winning_streak_threshold
        self.winning_streak_boost = winning_streak_boost

    def calculate_with_performance(
        self,
        capital: float,
        trade_stats: TradeStats,
        current_drawdown: float,
        consecutive_wins: int,
        vol_regime: str = "MEDIUM",
        confidence: float = 1.0,
    ) -> PositionSizeResult:
        """Calculate position with performance adjustment.

        Args:
            capital: Total available capital
            trade_stats: Historical trade statistics
            current_drawdown: Current drawdown as positive decimal
            consecutive_wins: Number of consecutive winning trades
            vol_regime: Current volatility regime
            confidence: Prediction confidence

        Returns:
            PositionSizeResult with performance adjustment
        """
        # Get base position
        result = self.calculate(capital, trade_stats, vol_regime, confidence)

        # Apply drawdown reduction
        performance_mult = 1.0
        if current_drawdown > self.drawdown_threshold:
            performance_mult *= self.drawdown_reduction

        # Apply winning streak boost (capped)
        if consecutive_wins >= self.winning_streak_threshold:
            performance_mult *= min(self.winning_streak_boost, 1.5)

        # Adjust position
        adjusted_size = result.position_size * performance_mult
        adjusted_pct = result.position_pct * performance_mult

        # Cap at maximum
        if adjusted_pct > self.config.max_position_pct:
            adjusted_pct = self.config.max_position_pct
            adjusted_size = adjusted_pct * capital

        return PositionSizeResult(
            position_size=adjusted_size,
            position_pct=adjusted_pct,
            kelly_raw=result.kelly_raw,
            kelly_adjusted=result.kelly_adjusted * performance_mult,
            regime_mult=result.regime_mult,
            confidence_mult=result.confidence_mult * performance_mult,
            was_capped=adjusted_pct >= self.config.max_position_pct,
        )


# Convenience function
def calculate_position_size(
    capital: float,
    win_rate: float,
    avg_win: float,
    avg_loss: float,
    kelly_fraction: float = 0.25,
    vol_regime: str = "MEDIUM",
    confidence: float = 1.0,
) -> float:
    """Quick position calculation without creating sizer instance.

    Args:
        capital: Total available capital
        win_rate: Historical win rate
        avg_win: Average winning trade return
        avg_loss: Average losing trade return (positive)
        kelly_fraction: Fraction of Kelly to use
        vol_regime: Volatility regime
        confidence: Prediction confidence

    Returns:
        Position size in capital units
    """
    config = PositionSizingConfig(kelly_fraction=kelly_fraction)
    sizer = PositionSizer(config)
    stats = TradeStats(win_rate=win_rate, avg_win=avg_win, avg_loss=avg_loss)
    result = sizer.calculate(capital, stats, vol_regime, confidence)
    return result.position_size
