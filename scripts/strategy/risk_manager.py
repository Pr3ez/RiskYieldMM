"""
RiskManager: Portfolio-level risk controls and circuit breakers.

This module implements safety controls:
1. Daily loss limits (stop trading after X% loss)
2. Drawdown-based position reduction
3. Consecutive loss tracking
4. Margin buffer maintenance
5. Exposure limits

These are PORTFOLIO-LEVEL controls, not individual trade controls.
"""

from dataclasses import dataclass
from enum import Enum


class RiskAction(Enum):
    """Risk management action to take."""

    NORMAL = "NORMAL"  # Trade normally
    REDUCE = "REDUCE"  # Reduce position sizes
    PAUSE = "PAUSE"  # Stop opening new positions
    CLOSE_ALL = "CLOSE_ALL"  # Close all positions immediately


@dataclass
class RiskConfig:
    """Configuration for risk management.

    Attributes:
        max_daily_loss_pct: Stop trading after this daily loss
        max_drawdown_pct: Max drawdown before reducing exposure
        drawdown_reduction_factor: How much to reduce at max drawdown
        max_consecutive_losses: Pause after N consecutive losses
        cooldown_bars: Bars to wait after pause trigger
        margin_buffer: Maintain this buffer above maintenance margin
        max_exposure_pct: Maximum total exposure as % of capital
        max_single_position_pct: Maximum single position size
    """

    # Daily loss limit
    max_daily_loss_pct: float = 0.05  # 5% daily loss → stop trading

    # Drawdown controls
    max_drawdown_pct: float = 0.15  # 15% drawdown → reduce exposure
    drawdown_reduction_factor: float = 0.5  # Reduce to 50% at max DD
    severe_drawdown_pct: float = 0.25  # 25% → close all

    # Consecutive losses
    max_consecutive_losses: int = 5  # Pause after 5 losses
    cooldown_bars: int = 3  # Wait 3 bars after pause

    # Margin safety
    margin_buffer: float = 2.0  # Keep 2x maintenance margin
    min_available_margin_pct: float = 0.30  # Keep 30% margin available

    # Exposure limits
    max_exposure_pct: float = 1.0  # Max 100% notional exposure
    max_single_position_pct: float = 0.30  # Max 30% in one position

    # Recovery
    recovery_win_streak: int = 3  # Exit pause after 3 wins


@dataclass
class RiskState:
    """Current risk state of the portfolio.

    Attributes:
        current_equity: Current portfolio equity
        peak_equity: Peak equity (for drawdown)
        daily_start_equity: Equity at start of day
        consecutive_losses: Number of consecutive losses
        consecutive_wins: Number of consecutive wins
        bars_since_pause: Bars since last pause trigger
        current_exposure: Total current exposure
        available_margin_pct: Available margin as % of equity
    """

    current_equity: float
    peak_equity: float
    daily_start_equity: float
    consecutive_losses: int = 0
    consecutive_wins: int = 0
    bars_since_pause: int = 0
    current_exposure: float = 0.0
    available_margin_pct: float = 1.0
    is_paused: bool = False


@dataclass
class RiskAssessment:
    """Result of risk assessment.

    Attributes:
        action: Recommended action
        position_multiplier: Multiplier to apply to position sizes
        can_open_new: Whether new positions can be opened
        can_increase: Whether existing positions can be increased
        reason: Explanation of the assessment
        metrics: Dictionary of risk metrics
    """

    action: RiskAction
    position_multiplier: float
    can_open_new: bool
    can_increase: bool
    reason: str
    metrics: dict


class RiskManager:
    """Portfolio-level risk management.

    This manager implements circuit breakers and position limits
    to protect capital during adverse conditions.

    Example:
        >>> config = RiskConfig(max_daily_loss_pct=0.05)
        >>> risk_mgr = RiskManager(config)
        >>> state = RiskState(
        ...     current_equity=9500,
        ...     peak_equity=10000,
        ...     daily_start_equity=10000,
        ... )
        >>> assessment = risk_mgr.assess(state)
        >>> if not assessment.can_open_new:
        ...     print("Trading paused:", assessment.reason)
    """

    def __init__(self, config: RiskConfig | None = None):
        """Initialize with configuration.

        Args:
            config: RiskConfig instance, or None for defaults
        """
        self.config = config or RiskConfig()
        self._pause_triggered = False
        self._pause_bar = 0

    def calculate_drawdown(self, state: RiskState) -> float:
        """Calculate current drawdown from peak.

        Args:
            state: Current risk state

        Returns:
            Drawdown as positive decimal (0.10 = 10% drawdown)
        """
        if state.peak_equity <= 0:
            return 0.0
        return (state.peak_equity - state.current_equity) / state.peak_equity

    def calculate_daily_loss(self, state: RiskState) -> float:
        """Calculate daily loss percentage.

        Args:
            state: Current risk state

        Returns:
            Daily loss as positive decimal (0.05 = 5% loss)
        """
        if state.daily_start_equity <= 0:
            return 0.0
        return (
            state.daily_start_equity - state.current_equity
        ) / state.daily_start_equity

    def calculate_position_multiplier(self, drawdown: float) -> float:
        """Calculate position size multiplier based on drawdown.

        Linear reduction from 1.0 at 0% DD to reduction_factor at max_dd.

        Args:
            drawdown: Current drawdown

        Returns:
            Position multiplier between reduction_factor and 1.0
        """
        cfg = self.config

        if drawdown <= 0:
            return 1.0

        if drawdown >= cfg.max_drawdown_pct:
            return cfg.drawdown_reduction_factor

        # Linear interpolation
        dd_ratio = drawdown / cfg.max_drawdown_pct
        return 1.0 - (1.0 - cfg.drawdown_reduction_factor) * dd_ratio

    def check_pause_condition(self, state: RiskState) -> tuple[bool, str]:
        """Check if trading should be paused.

        Args:
            state: Current risk state

        Returns:
            Tuple of (should_pause, reason)
        """
        cfg = self.config

        # Check consecutive losses
        if state.consecutive_losses >= cfg.max_consecutive_losses:
            return True, f"Consecutive losses: {state.consecutive_losses}"

        # Check daily loss
        daily_loss = self.calculate_daily_loss(state)
        if daily_loss >= cfg.max_daily_loss_pct:
            return True, f"Daily loss limit: {daily_loss:.1%}"

        # Check severe drawdown
        drawdown = self.calculate_drawdown(state)
        if drawdown >= cfg.severe_drawdown_pct:
            return True, f"Severe drawdown: {drawdown:.1%}"

        # Check margin
        if state.available_margin_pct < cfg.min_available_margin_pct:
            return True, f"Low margin: {state.available_margin_pct:.1%}"

        return False, ""

    def check_recovery(self, state: RiskState) -> bool:
        """Check if we've recovered from pause condition.

        Args:
            state: Current risk state

        Returns:
            True if we can resume trading
        """
        cfg = self.config

        # Check cooldown period
        if state.bars_since_pause < cfg.cooldown_bars:
            return False

        # Check win streak
        if state.consecutive_wins >= cfg.recovery_win_streak:
            return True

        # Check if pause conditions have cleared
        should_pause, _ = self.check_pause_condition(state)
        if not should_pause:
            return True

        return False

    def assess(self, state: RiskState, current_bar: int = 0) -> RiskAssessment:
        """Perform full risk assessment.

        Args:
            state: Current risk state
            current_bar: Current bar number (for cooldown tracking)

        Returns:
            RiskAssessment with action and metrics
        """
        cfg = self.config

        # Calculate metrics
        drawdown = self.calculate_drawdown(state)
        daily_loss = self.calculate_daily_loss(state)
        position_mult = self.calculate_position_multiplier(drawdown)

        metrics = {
            "drawdown": drawdown,
            "daily_loss": daily_loss,
            "consecutive_losses": state.consecutive_losses,
            "consecutive_wins": state.consecutive_wins,
            "exposure_pct": state.current_exposure / state.current_equity
            if state.current_equity > 0
            else 0,
            "available_margin": state.available_margin_pct,
        }

        # Check for severe drawdown → CLOSE ALL
        if drawdown >= cfg.severe_drawdown_pct:
            return RiskAssessment(
                action=RiskAction.CLOSE_ALL,
                position_multiplier=0.0,
                can_open_new=False,
                can_increase=False,
                reason=f"Severe drawdown: {drawdown:.1%}",
                metrics=metrics,
            )

        # Check pause conditions
        should_pause, pause_reason = self.check_pause_condition(state)

        if should_pause:
            self._pause_triggered = True
            self._pause_bar = current_bar

        # Check if we're in pause mode
        if self._pause_triggered or state.is_paused:
            # Check for recovery
            if self.check_recovery(state):
                self._pause_triggered = False
            else:
                return RiskAssessment(
                    action=RiskAction.PAUSE,
                    position_multiplier=position_mult,
                    can_open_new=False,
                    can_increase=False,
                    reason=pause_reason or "In cooldown period",
                    metrics=metrics,
                )

        # Check if we should reduce positions
        if drawdown >= cfg.max_drawdown_pct * 0.5:  # Start reducing at 50% of max
            return RiskAssessment(
                action=RiskAction.REDUCE,
                position_multiplier=position_mult,
                can_open_new=True,
                can_increase=False,
                reason=f"Elevated drawdown: {drawdown:.1%}",
                metrics=metrics,
            )

        # Check exposure limits
        exposure_ratio = (
            state.current_exposure / state.current_equity
            if state.current_equity > 0
            else 0
        )
        if exposure_ratio >= cfg.max_exposure_pct:
            return RiskAssessment(
                action=RiskAction.REDUCE,
                position_multiplier=position_mult,
                can_open_new=False,
                can_increase=False,
                reason=f"Max exposure reached: {exposure_ratio:.1%}",
                metrics=metrics,
            )

        # Normal operation
        return RiskAssessment(
            action=RiskAction.NORMAL,
            position_multiplier=position_mult,
            can_open_new=True,
            can_increase=True,
            reason="Normal operation",
            metrics=metrics,
        )

    def update_after_trade(
        self,
        state: RiskState,
        trade_pnl: float,
        is_win: bool,
    ) -> RiskState:
        """Update risk state after a trade.

        Args:
            state: Current risk state
            trade_pnl: P&L from the trade
            is_win: Whether trade was a win

        Returns:
            Updated risk state
        """
        new_equity = state.current_equity + trade_pnl
        new_peak = max(state.peak_equity, new_equity)

        if is_win:
            consecutive_losses = 0
            consecutive_wins = state.consecutive_wins + 1
        else:
            consecutive_losses = state.consecutive_losses + 1
            consecutive_wins = 0

        return RiskState(
            current_equity=new_equity,
            peak_equity=new_peak,
            daily_start_equity=state.daily_start_equity,
            consecutive_losses=consecutive_losses,
            consecutive_wins=consecutive_wins,
            bars_since_pause=state.bars_since_pause + 1 if state.is_paused else 0,
            current_exposure=state.current_exposure,
            available_margin_pct=state.available_margin_pct,
            is_paused=state.is_paused,
        )

    def reset_daily(self, state: RiskState) -> RiskState:
        """Reset daily metrics (call at start of each day).

        Args:
            state: Current risk state

        Returns:
            Risk state with daily metrics reset
        """
        return RiskState(
            current_equity=state.current_equity,
            peak_equity=state.peak_equity,
            daily_start_equity=state.current_equity,  # Reset daily start
            consecutive_losses=state.consecutive_losses,
            consecutive_wins=state.consecutive_wins,
            bars_since_pause=state.bars_since_pause,
            current_exposure=state.current_exposure,
            available_margin_pct=state.available_margin_pct,
            is_paused=state.is_paused,
        )

    def get_max_new_position(
        self,
        state: RiskState,
        assessment: RiskAssessment,
    ) -> float:
        """Get maximum allowed new position size.

        Args:
            state: Current risk state
            assessment: Current risk assessment

        Returns:
            Maximum position size as fraction of capital
        """
        if not assessment.can_open_new:
            return 0.0

        cfg = self.config

        # Start with max single position limit
        max_pos = cfg.max_single_position_pct

        # Apply position multiplier from drawdown
        max_pos *= assessment.position_multiplier

        # Check remaining exposure capacity
        current_exposure_pct = (
            state.current_exposure / state.current_equity
            if state.current_equity > 0
            else 0
        )
        remaining_exposure = cfg.max_exposure_pct - current_exposure_pct
        max_pos = min(max_pos, remaining_exposure)

        return max(max_pos, 0.0)


# Convenience function
def assess_portfolio_risk(
    current_equity: float,
    peak_equity: float,
    daily_start_equity: float,
    consecutive_losses: int = 0,
) -> dict:
    """Quick risk assessment without creating manager instance.

    Args:
        current_equity: Current portfolio equity
        peak_equity: Peak equity value
        daily_start_equity: Equity at start of day
        consecutive_losses: Number of consecutive losses

    Returns:
        Dictionary with risk assessment
    """
    config = RiskConfig()
    manager = RiskManager(config)
    state = RiskState(
        current_equity=current_equity,
        peak_equity=peak_equity,
        daily_start_equity=daily_start_equity,
        consecutive_losses=consecutive_losses,
    )
    assessment = manager.assess(state)
    return {
        "action": assessment.action.value,
        "can_open_new": assessment.can_open_new,
        "position_multiplier": assessment.position_multiplier,
        "reason": assessment.reason,
        **assessment.metrics,
    }
