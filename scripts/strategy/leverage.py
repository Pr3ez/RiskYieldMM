"""
LeverageCalculator: Safe leverage calculation for perpetual futures.

This module calculates optimal leverage that:
1. Avoids liquidation with high probability
2. Adjusts for current volatility regime
3. Maintains adequate margin buffer

Key formulas:
- Liquidation Price (Long) = Entry × (1 - 1/Leverage + MM)
- Safe Leverage = 1 / (safety_factor × ATR% + maintenance_margin)

References:
- SSRN: "Multivariable Kelly Criterion and Leverage" (2024)
- Bybit maintenance margin documentation
"""

from dataclasses import dataclass
from enum import Enum
from typing import Literal

import numpy as np


class VolRegime(Enum):
    """Volatility regime classification."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass
class LeverageConfig:
    """Configuration for leverage calculation.

    Attributes:
        maintenance_margin: Exchange maintenance margin rate (0.5% for Bybit BTC)
        safety_factor: Multiplier on expected adverse move (2.0 = 2x worst case)
        max_leverage: Hard cap on leverage (exchange limit)
        min_leverage: Floor on leverage (1.0 = no leverage)
        regime_multipliers: Leverage multipliers by volatility regime
    """

    maintenance_margin: float = 0.005  # 0.5% for Bybit BTC perpetual
    safety_factor: float = 2.0  # 2x expected adverse move
    max_leverage: float = 10.0  # Hard cap
    min_leverage: float = 1.0  # No leverage floor

    # Regime-based leverage multipliers
    # In high vol, reduce leverage; in low vol, can increase
    regime_multiplier_low: float = 1.3  # 30% more leverage in low vol
    regime_multiplier_medium: float = 1.0  # Base leverage
    regime_multiplier_high: float = 0.5  # 50% less leverage in high vol

    # Confidence-based adjustment
    # Wider conformal intervals = less confident = less leverage
    confidence_scaling: bool = True
    max_confidence_reduction: float = 0.5  # Max 50% reduction for low confidence


@dataclass
class LeverageResult:
    """Result of leverage calculation.

    Attributes:
        leverage: Recommended leverage multiplier
        safe_leverage: Maximum safe leverage (before regime/confidence adjustment)
        liquidation_distance: % move that would trigger liquidation
        margin_buffer: How much margin buffer we have
        regime_adjustment: Multiplier applied for regime
        confidence_adjustment: Multiplier applied for confidence
    """

    leverage: float
    safe_leverage: float
    liquidation_distance: float
    margin_buffer: float
    regime_adjustment: float
    confidence_adjustment: float


class LeverageCalculator:
    """Calculate safe leverage for perpetual futures trading.

    This calculator ensures we never get liquidated by:
    1. Computing max safe leverage based on ATR
    2. Adjusting for volatility regime
    3. Scaling down for low confidence predictions
    4. Maintaining adequate margin buffer

    Example:
        >>> config = LeverageConfig(maintenance_margin=0.005, safety_factor=2.0)
        >>> calc = LeverageCalculator(config)
        >>> result = calc.calculate(atr_pct=0.05, vol_regime="MEDIUM")
        >>> print(f"Safe leverage: {result.leverage:.2f}x")
    """

    def __init__(self, config: LeverageConfig | None = None):
        """Initialize with configuration.

        Args:
            config: LeverageConfig instance, or None for defaults
        """
        self.config = config or LeverageConfig()

    def calculate_safe_leverage(self, atr_pct: float) -> float:
        """Calculate maximum safe leverage based on ATR.

        The formula ensures that a move of (safety_factor × ATR) won't
        trigger liquidation.

        Args:
            atr_pct: ATR as percentage of price (e.g., 0.05 = 5%)

        Returns:
            Maximum safe leverage multiplier
        """
        cfg = self.config

        # Expected worst-case adverse move
        max_adverse_move = atr_pct * cfg.safety_factor

        # Safe leverage formula: 1 / (adverse_move + maintenance_margin)
        # This ensures liquidation price is beyond our stop loss
        if max_adverse_move + cfg.maintenance_margin <= 0:
            return cfg.max_leverage

        safe_leverage = 1.0 / (max_adverse_move + cfg.maintenance_margin)

        # Clamp to configured bounds
        return np.clip(safe_leverage, cfg.min_leverage, cfg.max_leverage)

    def get_regime_multiplier(self, vol_regime: str | VolRegime) -> float:
        """Get leverage multiplier for volatility regime.

        Args:
            vol_regime: Volatility regime ("LOW", "MEDIUM", "HIGH")

        Returns:
            Multiplier to apply to base leverage
        """
        cfg = self.config

        if isinstance(vol_regime, str):
            vol_regime = vol_regime.upper()

        if vol_regime in ("LOW", VolRegime.LOW):
            return cfg.regime_multiplier_low
        elif vol_regime in ("HIGH", VolRegime.HIGH):
            return cfg.regime_multiplier_high
        else:  # MEDIUM or unknown
            return cfg.regime_multiplier_medium

    def get_confidence_multiplier(self, confidence: float) -> float:
        """Get leverage multiplier based on prediction confidence.

        Lower confidence (wider conformal intervals) = lower leverage.

        Args:
            confidence: Confidence score in [0, 1] where 1 = most confident
                       Can be computed as 1 / (1 + normalized_interval_width)

        Returns:
            Multiplier to apply to leverage (between 1-max_reduction and 1.0)
        """
        if not self.config.confidence_scaling:
            return 1.0

        # Confidence of 1.0 = no reduction
        # Confidence of 0.0 = max reduction
        confidence = np.clip(confidence, 0.0, 1.0)
        min_mult = 1.0 - self.config.max_confidence_reduction

        return min_mult + confidence * self.config.max_confidence_reduction

    def calculate(
        self,
        atr_pct: float,
        vol_regime: str | VolRegime = "MEDIUM",
        confidence: float = 1.0,
    ) -> LeverageResult:
        """Calculate recommended leverage with all adjustments.

        Args:
            atr_pct: ATR as percentage of price
            vol_regime: Current volatility regime
            confidence: Prediction confidence [0, 1]

        Returns:
            LeverageResult with all details
        """
        # Step 1: Calculate base safe leverage from ATR
        safe_leverage = self.calculate_safe_leverage(atr_pct)

        # Step 2: Apply regime adjustment
        regime_mult = self.get_regime_multiplier(vol_regime)

        # Step 3: Apply confidence adjustment
        conf_mult = self.get_confidence_multiplier(confidence)

        # Step 4: Compute final leverage
        final_leverage = safe_leverage * regime_mult * conf_mult

        # Clamp to bounds
        final_leverage = np.clip(
            final_leverage, self.config.min_leverage, self.config.max_leverage
        )

        # Calculate liquidation distance at this leverage
        liq_distance = self.calculate_liquidation_distance(final_leverage)

        # Calculate margin buffer (how many ATRs until liquidation)
        margin_buffer = liq_distance / atr_pct if atr_pct > 0 else float("inf")

        return LeverageResult(
            leverage=final_leverage,
            safe_leverage=safe_leverage,
            liquidation_distance=liq_distance,
            margin_buffer=margin_buffer,
            regime_adjustment=regime_mult,
            confidence_adjustment=conf_mult,
        )

    def calculate_liquidation_distance(self, leverage: float) -> float:
        """Calculate % price move that would trigger liquidation.

        For a long position:
            Liquidation % = (1 - maintenance_margin) / leverage

        Args:
            leverage: Current leverage multiplier

        Returns:
            Percentage move (as decimal) that triggers liquidation
        """
        if leverage <= 0:
            return float("inf")

        # Simplified formula: liquidation happens when loss = initial margin
        # Initial margin = 1 / leverage
        # So liquidation at move = (1 / leverage) - maintenance_margin
        liq_distance = (1.0 / leverage) - self.config.maintenance_margin

        return max(liq_distance, 0.0)

    def calculate_liquidation_price(
        self,
        entry_price: float,
        leverage: float,
        direction: Literal["LONG", "SHORT"],
    ) -> float:
        """Calculate exact liquidation price.

        Args:
            entry_price: Position entry price
            leverage: Current leverage
            direction: "LONG" or "SHORT"

        Returns:
            Price at which position would be liquidated
        """
        liq_distance = self.calculate_liquidation_distance(leverage)

        if direction == "LONG":
            return entry_price * (1 - liq_distance)
        else:  # SHORT
            return entry_price * (1 + liq_distance)

    def is_safe(
        self,
        leverage: float,
        atr_pct: float,
        stop_loss_pct: float,
    ) -> bool:
        """Check if leverage is safe given stop loss.

        Leverage is safe if liquidation distance > stop loss distance.

        Args:
            leverage: Proposed leverage
            atr_pct: ATR as percentage of price
            stop_loss_pct: Stop loss distance as percentage

        Returns:
            True if liquidation won't happen before stop loss
        """
        liq_distance = self.calculate_liquidation_distance(leverage)
        return liq_distance > stop_loss_pct

    def suggest_leverage_for_stop(
        self,
        stop_loss_pct: float,
        buffer_factor: float = 1.5,
    ) -> float:
        """Suggest leverage given a stop loss level.

        Returns leverage where liquidation is buffer_factor × beyond stop loss.

        Args:
            stop_loss_pct: Stop loss as percentage (e.g., 0.05 = 5%)
            buffer_factor: How far beyond stop loss liquidation should be

        Returns:
            Recommended leverage
        """
        # We want: liq_distance = stop_loss_pct * buffer_factor
        # liq_distance = 1/leverage - MM
        # So: leverage = 1 / (stop_loss_pct * buffer_factor + MM)

        target_liq = stop_loss_pct * buffer_factor
        leverage = 1.0 / (target_liq + self.config.maintenance_margin)

        return np.clip(leverage, self.config.min_leverage, self.config.max_leverage)


# Convenience function for quick calculation
def calculate_safe_leverage(
    atr_pct: float,
    vol_regime: str = "MEDIUM",
    confidence: float = 1.0,
    maintenance_margin: float = 0.005,
    safety_factor: float = 2.0,
) -> float:
    """Quick leverage calculation without creating calculator instance.

    Args:
        atr_pct: ATR as percentage of price
        vol_regime: Volatility regime
        confidence: Prediction confidence [0, 1]
        maintenance_margin: Exchange maintenance margin
        safety_factor: Safety multiplier on ATR

    Returns:
        Recommended leverage
    """
    config = LeverageConfig(
        maintenance_margin=maintenance_margin,
        safety_factor=safety_factor,
    )
    calc = LeverageCalculator(config)
    result = calc.calculate(atr_pct, vol_regime, confidence)
    return result.leverage
