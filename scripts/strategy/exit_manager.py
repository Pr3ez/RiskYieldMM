"""
ExitManager: Triple barrier exit strategy with ATR-based stops.

This module implements optimal exit timing using:
1. Triple Barrier Method (López de Prado)
   - Take Profit barrier (upper)
   - Stop Loss barrier (lower)
   - Time Exit barrier (vertical)
2. ATR-based dynamic barrier placement
3. Trailing stops for profit protection
4. Signal reversal exits

References:
- López de Prado: "Advances in Financial Machine Learning" (Ch. 3)
- arXiv 2104.09700: "Stock Market Trend Analysis Using HMM and LSTM"
"""

from dataclasses import dataclass
from enum import Enum
from typing import Literal

import numpy as np


class ExitReason(Enum):
    """Reason for position exit."""

    TAKE_PROFIT = "TAKE_PROFIT"
    STOP_LOSS = "STOP_LOSS"
    TIME_EXIT = "TIME_EXIT"
    SIGNAL_REVERSAL = "SIGNAL_REVERSAL"
    TRAILING_STOP = "TRAILING_STOP"
    MANUAL = "MANUAL"
    LIQUIDATION_RISK = "LIQUIDATION_RISK"


@dataclass
class ExitConfig:
    """Configuration for exit management.

    Attributes:
        atr_multiplier_tp: ATR multiplier for take profit
        atr_multiplier_sl: ATR multiplier for stop loss
        max_holding_bars: Maximum bars to hold position
        use_trailing_stop: Whether to use trailing stops
        trailing_activation_atr: ATR profit before trailing activates
        trailing_distance_atr: Trailing stop distance in ATR
        use_signal_reversal: Exit on signal reversal
        asymmetric_barriers: Allow different TP and SL multipliers
    """

    # Take profit / Stop loss barriers
    atr_multiplier_tp: float = 2.0  # Take profit at 2x ATR
    atr_multiplier_sl: float = 2.0  # Stop loss at 2x ATR (can be asymmetric)

    # Time barrier
    max_holding_bars: int = 3  # Exit after N bars
    min_holding_bars: int = 0  # Minimum bars before exit (avoid noise)

    # Trailing stop
    use_trailing_stop: bool = True
    trailing_activation_atr: float = 1.0  # Activate after 1x ATR profit
    trailing_distance_atr: float = 1.5  # Trail at 1.5x ATR

    # Signal-based exit
    use_signal_reversal: bool = True
    reversal_requires_confidence: float = 0.6  # Min confidence for reversal exit

    # Safety
    use_liquidation_guard: bool = True
    liquidation_guard_pct: float = 0.8  # Exit if 80% to liquidation


@dataclass
class Barriers:
    """Computed barrier levels for a position.

    Attributes:
        take_profit: Price level for take profit
        stop_loss: Price level for stop loss
        time_limit: Maximum bars to hold
        trailing_activation: Price level to activate trailing
        direction: Position direction
    """

    take_profit: float
    stop_loss: float
    time_limit: int
    trailing_activation: float | None
    direction: Literal["LONG", "SHORT"]

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "take_profit": self.take_profit,
            "stop_loss": self.stop_loss,
            "time_limit": self.time_limit,
            "trailing_activation": self.trailing_activation,
            "direction": self.direction,
        }


@dataclass
class ExitSignal:
    """Exit signal with reason and details.

    Attributes:
        should_exit: Whether to exit position
        reason: Reason for exit (if exiting)
        exit_price: Suggested exit price
        bars_held: How many bars position was held
        pnl_pct: Unrealized P&L percentage
    """

    should_exit: bool
    reason: ExitReason | None = None
    exit_price: float | None = None
    bars_held: int = 0
    pnl_pct: float = 0.0

    @property
    def reason_str(self) -> str:
        """Get reason as string."""
        return self.reason.value if self.reason else "HOLD"


class ExitManager:
    """Manage position exits using triple barrier method.

    This manager implements López de Prado's triple barrier method
    with ATR-based dynamic barriers and trailing stops.

    Example:
        >>> config = ExitConfig(atr_multiplier_tp=2.0, atr_multiplier_sl=2.0)
        >>> exit_mgr = ExitManager(config)
        >>> barriers = exit_mgr.compute_barriers(
        ...     entry_price=100.0, atr=5.0, direction="LONG"
        ... )
        >>> print(f"TP: {barriers.take_profit}, SL: {barriers.stop_loss}")
    """

    def __init__(self, config: ExitConfig | None = None):
        """Initialize with configuration.

        Args:
            config: ExitConfig instance, or None for defaults
        """
        self.config = config or ExitConfig()

    def compute_barriers(
        self,
        entry_price: float,
        atr: float,
        direction: Literal["LONG", "SHORT"],
    ) -> Barriers:
        """Compute barrier levels for a new position.

        Args:
            entry_price: Position entry price
            atr: Current ATR value (absolute, not percentage)
            direction: "LONG" or "SHORT"

        Returns:
            Barriers with TP, SL, and time limit
        """
        cfg = self.config

        tp_distance = atr * cfg.atr_multiplier_tp
        sl_distance = atr * cfg.atr_multiplier_sl

        if direction == "LONG":
            take_profit = entry_price + tp_distance
            stop_loss = entry_price - sl_distance
            trailing_activation = (
                entry_price + atr * cfg.trailing_activation_atr
                if cfg.use_trailing_stop
                else None
            )
        else:  # SHORT
            take_profit = entry_price - tp_distance
            stop_loss = entry_price + sl_distance
            trailing_activation = (
                entry_price - atr * cfg.trailing_activation_atr
                if cfg.use_trailing_stop
                else None
            )

        return Barriers(
            take_profit=take_profit,
            stop_loss=stop_loss,
            time_limit=cfg.max_holding_bars,
            trailing_activation=trailing_activation,
            direction=direction,
        )

    def compute_trailing_stop(
        self,
        current_price: float,
        high_since_entry: float,
        low_since_entry: float,
        atr: float,
        direction: Literal["LONG", "SHORT"],
        barriers: Barriers,
    ) -> float | None:
        """Compute current trailing stop level.

        Args:
            current_price: Current market price
            high_since_entry: Highest price since entry
            low_since_entry: Lowest price since entry
            atr: Current ATR
            direction: Position direction
            barriers: Original barriers

        Returns:
            Trailing stop price, or None if not activated
        """
        if not self.config.use_trailing_stop:
            return None

        if barriers.trailing_activation is None:
            return None

        cfg = self.config
        trail_distance = atr * cfg.trailing_distance_atr

        if direction == "LONG":
            # Trailing activates when price exceeds activation level
            if high_since_entry >= barriers.trailing_activation:
                # Trail from highest high
                return high_since_entry - trail_distance
        else:  # SHORT
            # Trailing activates when price drops below activation level
            if low_since_entry <= barriers.trailing_activation:
                # Trail from lowest low
                return low_since_entry + trail_distance

        return None

    def check_exit(
        self,
        current_price: float,
        entry_price: float,
        barriers: Barriers,
        bars_held: int,
        high_since_entry: float,
        low_since_entry: float,
        atr: float,
        current_signal: int | None = None,
        signal_confidence: float = 0.0,
        liquidation_price: float | None = None,
    ) -> ExitSignal:
        """Check if position should be exited.

        Priority order:
        1. Stop Loss (risk management)
        2. Liquidation guard
        3. Trailing stop (if active)
        4. Signal reversal
        5. Take Profit
        6. Time limit

        Args:
            current_price: Current market price
            entry_price: Position entry price
            barriers: Position barriers
            bars_held: Number of bars held
            high_since_entry: Highest price since entry
            low_since_entry: Lowest price since entry
            atr: Current ATR
            current_signal: Current model prediction (1=LONG, 0=SHORT)
            signal_confidence: Confidence of current signal
            liquidation_price: Price at which position would be liquidated

        Returns:
            ExitSignal with decision and reason
        """
        cfg = self.config
        direction = barriers.direction

        # Calculate P&L percentage
        if direction == "LONG":
            pnl_pct = (current_price - entry_price) / entry_price
        else:
            pnl_pct = (entry_price - current_price) / entry_price

        # Base exit signal (no exit)
        exit_signal = ExitSignal(
            should_exit=False,
            bars_held=bars_held,
            pnl_pct=pnl_pct,
        )

        # Check minimum holding period
        if bars_held < cfg.min_holding_bars:
            return exit_signal

        # 1. STOP LOSS CHECK (highest priority - risk management)
        if direction == "LONG":
            if current_price <= barriers.stop_loss:
                return ExitSignal(
                    should_exit=True,
                    reason=ExitReason.STOP_LOSS,
                    exit_price=barriers.stop_loss,
                    bars_held=bars_held,
                    pnl_pct=pnl_pct,
                )
        else:  # SHORT
            if current_price >= barriers.stop_loss:
                return ExitSignal(
                    should_exit=True,
                    reason=ExitReason.STOP_LOSS,
                    exit_price=barriers.stop_loss,
                    bars_held=bars_held,
                    pnl_pct=pnl_pct,
                )

        # 2. LIQUIDATION GUARD
        if cfg.use_liquidation_guard and liquidation_price is not None:
            if direction == "LONG":
                distance_to_liq = (current_price - liquidation_price) / current_price
                if (
                    distance_to_liq
                    < (1 - cfg.liquidation_guard_pct)
                    * (entry_price - liquidation_price)
                    / entry_price
                ):
                    return ExitSignal(
                        should_exit=True,
                        reason=ExitReason.LIQUIDATION_RISK,
                        exit_price=current_price,
                        bars_held=bars_held,
                        pnl_pct=pnl_pct,
                    )
            else:  # SHORT
                distance_to_liq = (liquidation_price - current_price) / current_price
                if (
                    distance_to_liq
                    < (1 - cfg.liquidation_guard_pct)
                    * (liquidation_price - entry_price)
                    / entry_price
                ):
                    return ExitSignal(
                        should_exit=True,
                        reason=ExitReason.LIQUIDATION_RISK,
                        exit_price=current_price,
                        bars_held=bars_held,
                        pnl_pct=pnl_pct,
                    )

        # 3. TRAILING STOP CHECK
        trailing_stop = self.compute_trailing_stop(
            current_price,
            high_since_entry,
            low_since_entry,
            atr,
            direction,
            barriers,
        )

        if trailing_stop is not None:
            if direction == "LONG" and current_price <= trailing_stop:
                return ExitSignal(
                    should_exit=True,
                    reason=ExitReason.TRAILING_STOP,
                    exit_price=trailing_stop,
                    bars_held=bars_held,
                    pnl_pct=pnl_pct,
                )
            elif direction == "SHORT" and current_price >= trailing_stop:
                return ExitSignal(
                    should_exit=True,
                    reason=ExitReason.TRAILING_STOP,
                    exit_price=trailing_stop,
                    bars_held=bars_held,
                    pnl_pct=pnl_pct,
                )

        # 4. SIGNAL REVERSAL CHECK
        if cfg.use_signal_reversal and current_signal is not None:
            is_reversal = (direction == "LONG" and current_signal == 0) or (
                direction == "SHORT" and current_signal == 1
            )

            if is_reversal and signal_confidence >= cfg.reversal_requires_confidence:
                return ExitSignal(
                    should_exit=True,
                    reason=ExitReason.SIGNAL_REVERSAL,
                    exit_price=current_price,
                    bars_held=bars_held,
                    pnl_pct=pnl_pct,
                )

        # 5. TAKE PROFIT CHECK
        if direction == "LONG":
            if current_price >= barriers.take_profit:
                return ExitSignal(
                    should_exit=True,
                    reason=ExitReason.TAKE_PROFIT,
                    exit_price=barriers.take_profit,
                    bars_held=bars_held,
                    pnl_pct=pnl_pct,
                )
        else:  # SHORT
            if current_price <= barriers.take_profit:
                return ExitSignal(
                    should_exit=True,
                    reason=ExitReason.TAKE_PROFIT,
                    exit_price=barriers.take_profit,
                    bars_held=bars_held,
                    pnl_pct=pnl_pct,
                )

        # 6. TIME EXIT CHECK
        if bars_held >= barriers.time_limit:
            return ExitSignal(
                should_exit=True,
                reason=ExitReason.TIME_EXIT,
                exit_price=current_price,
                bars_held=bars_held,
                pnl_pct=pnl_pct,
            )

        # No exit triggered
        return exit_signal

    def compute_optimal_barriers(
        self,
        entry_price: float,
        atr: float,
        direction: Literal["LONG", "SHORT"],
        win_rate: float,
        target_profit_factor: float = 1.5,
    ) -> Barriers:
        """Compute optimal asymmetric barriers based on win rate.

        If win rate is high, we can use tighter stops and wider targets.
        If win rate is low, we need wider stops relative to targets.

        Args:
            entry_price: Position entry price
            atr: Current ATR
            direction: Position direction
            win_rate: Historical win rate
            target_profit_factor: Target profit factor to achieve

        Returns:
            Optimized barriers
        """
        # Profit Factor = (win_rate × avg_win) / ((1 - win_rate) × avg_loss)
        # Target: PF = win_rate × tp_mult / ((1 - win_rate) × sl_mult)
        # Solving for ratio: tp_mult / sl_mult = PF × (1 - win_rate) / win_rate

        loss_rate = 1 - win_rate
        ratio = target_profit_factor * loss_rate / win_rate if win_rate > 0 else 1.0

        # Start with base multiplier, adjust TP/SL ratio
        base_mult = self.config.atr_multiplier_sl
        sl_mult = base_mult
        tp_mult = base_mult * ratio

        # Cap at reasonable values
        tp_mult = np.clip(tp_mult, 1.0, 5.0)
        sl_mult = np.clip(sl_mult, 1.0, 3.0)

        tp_distance = atr * tp_mult
        sl_distance = atr * sl_mult

        if direction == "LONG":
            take_profit = entry_price + tp_distance
            stop_loss = entry_price - sl_distance
            trailing_activation = (
                entry_price + atr * self.config.trailing_activation_atr
                if self.config.use_trailing_stop
                else None
            )
        else:
            take_profit = entry_price - tp_distance
            stop_loss = entry_price + sl_distance
            trailing_activation = (
                entry_price - atr * self.config.trailing_activation_atr
                if self.config.use_trailing_stop
                else None
            )

        return Barriers(
            take_profit=take_profit,
            stop_loss=stop_loss,
            time_limit=self.config.max_holding_bars,
            trailing_activation=trailing_activation,
            direction=direction,
        )


# Convenience function
def compute_exit_barriers(
    entry_price: float,
    atr: float,
    direction: Literal["LONG", "SHORT"],
    atr_multiplier: float = 2.0,
    max_holding_bars: int = 3,
) -> dict:
    """Quick barrier computation without creating manager instance.

    Args:
        entry_price: Position entry price
        atr: Current ATR
        direction: "LONG" or "SHORT"
        atr_multiplier: Multiplier for TP and SL
        max_holding_bars: Maximum bars to hold

    Returns:
        Dictionary with barrier levels
    """
    config = ExitConfig(
        atr_multiplier_tp=atr_multiplier,
        atr_multiplier_sl=atr_multiplier,
        max_holding_bars=max_holding_bars,
    )
    manager = ExitManager(config)
    barriers = manager.compute_barriers(entry_price, atr, direction)
    return barriers.to_dict()
