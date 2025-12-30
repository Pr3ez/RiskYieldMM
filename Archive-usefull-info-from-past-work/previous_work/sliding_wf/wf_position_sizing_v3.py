"""
Position Sizing V3 - Clean, Modular, Tunable

Pipeline:
    Step 1: Gate Check (prob >= threshold)
    Step 2: Rolling EMA Ratio (recent TP/FP performance)
    Step 3: Config Alignment (Top10 agreement)
    Step 4: Volatility Adjustment
    Step 5: Final Position (combine all factors)

Each step is independent and can be tuned/extended.
"""

import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from collections import deque


# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION - All tunable parameters in one place
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class PositionSizingConfig:
    """All tunable parameters for position sizing."""
    
    # Step 1: Gates
    min_prob: float = 0.50  # Minimum probability to consider (below = no signal)
    
    # Step 1a: ADAPTIVE THRESHOLD (lower threshold in strong trends)
    # NOTE: DISABLED when using Hull-optimal (Hull-optimal handles confidence scaling)
    # Analysis: In STRONG BULL, avg prob=0.512 vs thr=0.512 → missing +1200% in FN
    # Solution: Lower threshold when LtEMA is high (momentum = follow trend)
    use_adaptive_threshold: bool = False  # DISABLED - Hull-optimal handles this via confidence scaling
    adaptive_threshold_strong_bull_reduction: float = 0.04  # Reduce threshold by this in strong bull (LtEMA >= 2.0)
    adaptive_threshold_mild_bull_reduction: float = 0.02  # Reduce threshold by this in mild bull (1.0 <= LtEMA < 2.0)
    adaptive_threshold_bear_increase: float = 0.01  # Increase threshold by this in bear (LtEMA < 1.0)
    adaptive_threshold_ema_scale: float = 0.01  # Additional reduction per LtEMA unit above 2.0
    
    # Step 1b: Alpha Gate (expected_return > risk_free)
    use_alpha_gate: bool = True  # Enable alpha gate
    
    # Step 1c: Danger Zone Gate (LtEMA > median AND StRSI > 60)
    # NOTE: DISABLED when Hybrid3 is active - Hybrid3 handles regime detection better
    use_danger_zone_gate: bool = False  # DISABLED - analysis showed it blocks good days
    danger_zone_ltema_threshold: float = 1.078  # LtEMA median from analysis
    danger_zone_strsi_threshold: float = 60.0  # StRSI threshold
    
    # Step 2: Rolling EMA Ratio
    ratio_window: int = 50  # Rolling window for TP/FP tracking
    ratio_ema_alpha: float = 0.1  # EMA decay (higher = more weight to recent)
    ratio_min_trades: int = 10  # Minimum trades before using ratio
    
    # Step 3: Config Alignment
    alignment_min_configs: int = 3  # Minimum configs needed for alignment
    alignment_weight: float = 1.0  # How much alignment affects position
    
    # Step 3b: EMA Crossover Scaling (StEMA vs LtEMA)
    use_ema_crossover_scale: bool = True  # Enable EMA crossover scaling
    ema_crossover_boost: float = 0.15  # +15% when StEMA > LtEMA
    ema_crossover_reduce: float = 0.10  # -10% when StEMA <= LtEMA
    
    # Step 3c: LtEMA Quartile Scaling
    use_ltema_quartile_scale: bool = True  # Enable LtEMA quartile scaling
    ltema_q1_threshold: float = 0.95  # Q1 threshold (contrarian boost)
    ltema_q4_threshold: float = 1.47  # Q4 threshold (regression reduce)
    ltema_q1_boost: float = 0.05  # +5% at Q1
    ltema_q4_reduce: float = 0.08  # -8% at Q4
    
    # Step 4: Volatility
    high_vol_reduction: float = 0.70  # Multiply by this in high vol
    
    # Step 5: Position scaling
    base_position: float = 1.0  # Neutral position (100% equity)
    max_position: float = 2.0  # Maximum position (200% = 2x leverage)
    min_position: float = 0.0  # Minimum position (0% = cash)
    
    # Leverage rules
    leverage_min_ratio: float = 1.3  # Minimum ratio to allow >1.0
    leverage_min_alignment: float = 0.7  # Minimum alignment to allow >1.0
    
    # Step 6: Ratio Gate (GATE - hard stop when ratio < threshold)
    # NOTE: DISABLED - Analysis showed gate blocks winners (63% WR) more than losers (33% WR)
    use_ratio_gate: bool = False  # DISABLED - use inverse scale instead
    ratio_gate_threshold: float = 1.0  # Ratio below this → position = 0
    ratio_gate_min_trades: int = 20  # Minimum trades before gate activates
    
    # Step 6b: Inverse Ratio Scale (SCALE UP when ratio is LOW - mean reversion)
    # Based on analysis: Low ratio (< 0.8) → 62% WR next trade, High ratio (> 1.2) → 33% WR
    use_ratio_inverse_scale: bool = True  # Enable inverse ratio scaling
    disable_momentum_scale_when_inverse: bool = True  # Disable Step 2 momentum when inverse is active
    ratio_inverse_low_threshold: float = 0.8  # Below this → INCREASE position (mean reversion)
    ratio_inverse_high_threshold: float = 1.2  # Above this → DECREASE position
    ratio_inverse_low_scale: float = 1.20  # Scale UP when ratio is low (62% WR expected)
    ratio_inverse_high_scale: float = 0.80  # Scale DOWN when ratio is high (33% WR expected)
    ratio_inverse_min_trades: int = 20  # Minimum trades before inverse scale activates
    
    # Step 7: Drawdown Protection (SCALE - reduce position during drawdowns)
    use_drawdown_protection: bool = True  # Enable drawdown protection
    drawdown_caution_threshold: float = 0.03  # 3% drawdown → reduce by 25%
    drawdown_serious_threshold: float = 0.05  # 5% drawdown → reduce by 50%
    drawdown_severe_threshold: float = 0.08  # 8% drawdown → reduce by 75%
    drawdown_caution_scale: float = 0.75  # Position multiplier at caution
    drawdown_serious_scale: float = 0.50  # Position multiplier at serious
    drawdown_severe_scale: float = 0.25  # Position multiplier at severe
    
    # Step 8: Hybrid3 Regime-Adaptive Sizing (LEGACY - replaced by Hull-optimal)
    # Based on analysis: 100% win rate on 180-day windows, Hull=1.9
    # Bull (LtEMA >= 1.0): Full position works best
    # Bear (LtEMA < 1.0): Inverted signal works best (mean reversion)
    use_hybrid3_sizing: bool = False  # DISABLED by default - use Hull-optimal instead
    hybrid3_ema_threshold: float = 1.0  # LtEMA threshold for bull/bear regime
    
    # Step 9: REGIME OVERRIDE (Bypass gates in strong bull markets)
    # NOTE: DISABLED when using Hull-optimal (Hull-optimal handles regime scaling)
    # Analysis showed we MISS +122% in bull markets due to threshold gate
    # When regime is clearly bullish, bypass gates and take full position
    use_regime_override: bool = False  # DISABLED - Hull-optimal handles regime scaling
    regime_strong_bull_ema: float = 2.0  # LtEMA >= 2.0 = strong bull
    regime_strong_bull_rsi: float = 50.0  # LtRSI >= 50 = bullish momentum
    regime_strong_bull_position: float = 1.0  # Full position in strong bull
    regime_mild_bull_ema: float = 1.0  # LtEMA >= 1.0 = mild bull (bypass gates)
    regime_mild_bull_rsi: float = 40.0  # LtRSI >= 40 = mild bullish
    regime_mild_bull_position: float = 0.75  # 75% position in mild bull
    regime_bear_ema: float = 1.0  # LtEMA < 1.0 = bear regime
    regime_bear_min_position: float = 0.25  # Min position in bear (inverted)
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Step 10: HULL-OPTIMAL POSITION SIZING (New - targets consistent Hull score)
    # ═══════════════════════════════════════════════════════════════════════════
    # Key insights from Hull formula analysis:
    # - Hull = adjusted_sharpe = sharpe / (vol_penalty * return_penalty)
    # - vol_penalty = 1 + max(0, strategy_vol/market_vol - 1.2)
    # - return_penalty = 1 + (return_gap^2)/100
    #
    # To maximize Hull:
    # 1. Keep strategy volatility <= 1.2 * market volatility
    # 2. Don't underperform market significantly (avoid return_penalty)
    # 3. Generate positive Sharpe (beat risk-free consistently)
    #
    # Strategy:
    # - Conservative base position (0.5-0.7) to reduce volatility
    # - Only scale up to 1.0+ when BOTH model AND market momentum align
    # - Scale down to 0.0-0.3 when model or market shows bearish signs
    # ═══════════════════════════════════════════════════════════════════════════
    use_hull_optimal: bool = True  # Enable Hull-optimal sizing (replaces hybrid3)
    
    # Base position (conservative to keep volatility low)
    # NOTE: Lower base = lower volatility = better Hull when losing
    hull_base_position: float = 0.40  # Conservative base (40% exposure) - was 0.55
    
    # Confidence scaling: How much probability affects position
    # Higher prob = more confident = bigger position
    hull_confidence_scale: float = 0.50  # Max +50% from base when prob=1.0 (0.4 → 0.6)
    
    # Market momentum scaling based on LtEMA (TP/FP ratio EMA)
    # LtEMA > 1.0 = model is correct more often than wrong
    # LtEMA < 1.0 = model is wrong more often than correct
    hull_strong_bull_scale: float = 1.50  # +50% in strong bull (LtEMA >= 1.5) - aggressive when winning
    hull_mild_bull_scale: float = 1.20  # +20% in mild bull (1.0 <= LtEMA < 1.5)
    hull_neutral_scale: float = 0.80  # -20% in neutral (0.9 <= LtEMA < 1.0) - reduce when uncertain
    hull_bear_scale: float = 0.30  # -70% in bear (LtEMA < 0.9) - very cautious when model is wrong
    
    # Thresholds for regime classification
    hull_strong_bull_ema: float = 1.50  # LtEMA >= 1.5 = strong bull (model very reliable)
    hull_mild_bull_ema: float = 1.00  # LtEMA >= 1.0 = mild bull (model reliable)
    hull_neutral_ema: float = 0.90  # LtEMA >= 0.9 = neutral (model mixed)
    hull_strong_bear_ema: float = 0.70  # LtEMA < 0.7 = strong bear → sit out
    
    # Strategy performance scaling (based on rolling strategy return vs market)
    hull_winning_streak_scale: float = 1.15  # +15% when strategy beats market
    hull_losing_streak_scale: float = 0.60  # -40% when strategy trails market
    hull_streak_window: int = 20  # Window for comparing strategy vs market
    
    # Position limits for Hull optimization
    hull_max_position: float = 1.00  # Cap at 1.0 (no leverage) - was 1.2, keeps vol low
    hull_min_position: float = 0.05  # Floor at 5% (almost cash) - was 0.1
    
    # Bear market handling
    hull_bear_sit_out: bool = True  # In strong bear, position = 0.0 (protect capital)


# ═══════════════════════════════════════════════════════════════════════════
# ROLLING RATIO TRACKER - Tracks recent TP/FP with EMA weighting
# ═══════════════════════════════════════════════════════════════════════════

class RollingRatioTracker:
    """
    Tracks TP/FP ratio using rolling window + EMA weighting.
    
    - Rolling window ensures we use recent performance only
    - EMA weighting emphasizes most recent trades even within window
    - Adapts quickly to changing market conditions
    """
    
    def __init__(self, window_size: int = 50, ema_alpha: float = 0.1):
        self.window_size = window_size
        self.ema_alpha = ema_alpha
        
        # Rolling window of results: 1 = TP, 0 = FP, -1 = TN, -2 = FN
        self.results: deque = deque(maxlen=window_size)
        
        # EMA-weighted ratio (updated incrementally)
        self.ema_ratio: float = 1.0
        self.total_trades: int = 0
    
    def update(self, result: str) -> None:
        """
        Add a new trade result.
        
        Args:
            result: 'TP', 'FP', 'TN', or 'FN'
        """
        # Map result to numeric
        result_map = {'TP': 1, 'FP': 0, 'TN': -1, 'FN': -2}
        result_val = result_map.get(result, -1)
        
        self.results.append(result_val)
        self.total_trades += 1
        
        # Update EMA ratio (only for positive predictions: TP and FP)
        if result in ['TP', 'FP']:
            # Current trade success: 1 for TP, 0 for FP
            success = 1.0 if result == 'TP' else 0.0
            self.ema_ratio = self.ema_alpha * success + (1 - self.ema_alpha) * self.ema_ratio
    
    def get_rolling_ratio(self) -> Tuple[float, Dict]:
        """
        Calculate rolling TP/FP ratio from recent window.
        
        Returns:
            ratio: TP/FP ratio (inf if no FP, 0 if no TP)
            meta: Dictionary with details
        """
        if len(self.results) == 0:
            return 1.0, {'mode': 'NO_DATA', 'tp': 0, 'fp': 0}
        
        # Count TP and FP in window
        tp = sum(1 for r in self.results if r == 1)
        fp = sum(1 for r in self.results if r == 0)
        
        if fp == 0:
            ratio = float('inf') if tp > 0 else 1.0
        else:
            ratio = tp / fp
        
        return ratio, {
            'mode': 'ROLLING',
            'tp': tp,
            'fp': fp,
            'window_size': len(self.results),
            'total_trades': self.total_trades,
        }
    
    def get_ema_ratio(self) -> float:
        """Get EMA-weighted success rate (0 to 1)."""
        return self.ema_ratio
    
    def get_combined_ratio(self) -> Tuple[float, Dict]:
        """
        Get combined ratio using both rolling and EMA.
        
        The combined approach:
        - Rolling ratio gives discrete TP/FP count
        - EMA ratio gives smooth trend indication
        - We use rolling ratio but adjust by EMA trend
        """
        rolling_ratio, meta = self.get_rolling_ratio()
        ema_ratio = self.get_ema_ratio()
        
        # If not enough data, use EMA
        if meta['tp'] + meta['fp'] < 5:
            meta['mode'] = 'EMA_ONLY'
            meta['ema_ratio'] = ema_ratio
            return ema_ratio * 2, meta  # Scale EMA (0-1) to ratio-like (0-2)
        
        # Combine: rolling ratio adjusted by EMA trend
        # EMA > 0.5 means recent trades are better than average
        ema_adjustment = 0.8 + 0.4 * ema_ratio  # 0.8 to 1.2
        combined = rolling_ratio * ema_adjustment
        
        meta['mode'] = 'COMBINED'
        meta['ema_ratio'] = ema_ratio
        meta['ema_adjustment'] = ema_adjustment
        meta['combined_ratio'] = combined
        
        return combined, meta


# ═══════════════════════════════════════════════════════════════════════════
# CONFIG ALIGNMENT CALCULATOR
# ═══════════════════════════════════════════════════════════════════════════

def calculate_config_alignment(
    config_predictions: List[Dict],
    min_configs: int = 3
) -> Tuple[float, Dict]:
    """
    Calculate alignment from Top N config predictions.
    
    Args:
        config_predictions: List of dicts with 'prob' and 'threshold' keys
        min_configs: Minimum configs needed
        
    Returns:
        alignment: 0.0 to 1.0 (fraction predicting UP)
        meta: Details
    """
    if len(config_predictions) < min_configs:
        return 0.5, {'mode': 'INSUFFICIENT_CONFIGS', 'n_configs': len(config_predictions)}
    
    # Count how many predict UP (prob >= threshold)
    votes_up = 0
    votes_total = 0
    
    for cfg in config_predictions:
        prob = cfg.get('prob', 0.5)
        threshold = cfg.get('threshold', 0.5)
        
        if prob >= threshold:
            votes_up += 1
        votes_total += 1
    
    alignment = votes_up / votes_total if votes_total > 0 else 0.5
    
    return alignment, {
        'mode': 'ALIGNMENT',
        'votes_up': votes_up,
        'votes_down': votes_total - votes_up,
        'n_configs': votes_total,
        'alignment': alignment,
    }


# ═══════════════════════════════════════════════════════════════════════════
# MAIN POSITION SIZING FUNCTION
# ═══════════════════════════════════════════════════════════════════════════

def calculate_position_v3(
    prob_up: float,
    threshold: float,
    rolling_ratio: float,
    alignment: float,
    high_vol: bool = False,
    config: Optional[PositionSizingConfig] = None,
    verbose: bool = False,
    # New parameters for EMA integration
    expected_return: float = None,
    risk_free_rate: float = None,
    dual_ema_data: Optional[Dict] = None,
    total_trades: int = 0,  # Total trades for inverse scale warmup check
) -> Tuple[float, Dict]:
    """
    Calculate position size using clean pipeline with EMA integration.
    
    Pipeline:
        1. Gates: prob >= threshold, alpha > 0, danger zone check
        2. Ratio: Scale by recent TP/FP
        3. EMA Scales: Crossover and quartile adjustments
        4. Alignment: Scale by config agreement
        5. Volatility: Reduce in high vol
        6. Final: Clamp to [0, max]
    
    Args:
        prob_up: Model probability of UP
        threshold: Classification threshold
        rolling_ratio: Recent TP/FP ratio from RollingRatioTracker
        alignment: Config alignment (0.0 to 1.0)
        high_vol: Whether in high volatility regime
        config: Tunable parameters
        verbose: Print debug info
        expected_return: Expected return (for alpha gate)
        risk_free_rate: Risk-free rate (for alpha gate)
        dual_ema_data: Dict with LtEMA, StEMA, LtRSI, StRSI (for EMA gates/scales)
        
    Returns:
        position: 0.0 to max_position
        meta: Dictionary with step-by-step details
    """
    if config is None:
        config = PositionSizingConfig()
    
    meta = {
        'prob_up': prob_up,
        'threshold': threshold,
        'rolling_ratio': rolling_ratio,
        'alignment': alignment,
        'high_vol': high_vol,
        'total_trades': total_trades,
    }
    
    # ════════════════════════════════════════════════════════════════
    # STEP 0: REGIME OVERRIDE (Bypass gates in clear bull/bear regimes)
    # Analysis: We MISS +122% in bull markets due to gates blocking
    # Solution: Check regime FIRST, bypass gates in strong bull
    # NOTE: Drawdown protection is applied AFTER this function in the
    #       AdaptivePositionSizer class, so we don't need to handle it here
    # ════════════════════════════════════════════════════════════════
    
    if config.use_regime_override and dual_ema_data and dual_ema_data.get('has_data', False):
        lt_ema = dual_ema_data.get('long_term_ema', 1.0)
        lt_rsi = dual_ema_data.get('long_term_rsi', 50.0)
        
        # ════════════════════════════════════════════════════════════════
        # ADAPTIVE THRESHOLD: Lower threshold in strong trends
        # Analysis: In STRONG BULL, we miss +1200% due to prob being just below threshold
        # Solution: In strong momentum, lower the bar for entry (follow the trend)
        # ════════════════════════════════════════════════════════════════
        adaptive_threshold = threshold  # Start with base threshold
        
        if config.use_adaptive_threshold:
            if lt_ema >= 2.0:
                # STRONG BULL: Significantly lower threshold
                # More LtEMA = more confidence in trend = lower threshold
                extra_reduction = (lt_ema - 2.0) * config.adaptive_threshold_ema_scale
                adaptive_threshold = threshold - config.adaptive_threshold_strong_bull_reduction - extra_reduction
                meta['adaptive_threshold_regime'] = 'STRONG_BULL'
            elif lt_ema >= 1.0:
                # MILD BULL: Slightly lower threshold
                adaptive_threshold = threshold - config.adaptive_threshold_mild_bull_reduction
                meta['adaptive_threshold_regime'] = 'MILD_BULL'
            else:
                # BEAR: Slightly raise threshold (be more selective)
                adaptive_threshold = threshold + config.adaptive_threshold_bear_increase
                meta['adaptive_threshold_regime'] = 'BEAR'
            
            # Clamp adaptive threshold to reasonable bounds [0.45, 0.60]
            adaptive_threshold = max(0.45, min(0.60, adaptive_threshold))
            meta['original_threshold'] = threshold
            meta['adaptive_threshold'] = adaptive_threshold
            
            if verbose and adaptive_threshold != threshold:
                print(f"  [V3] ADAPTIVE THR: {threshold:.3f} → {adaptive_threshold:.3f} (LtEMA={lt_ema:.2f})")
        
        # ⚠️ FIX: Regime override only applies when MODEL PREDICTS POSITIVE
        # Use ADAPTIVE threshold instead of original threshold
        model_predicts_positive = prob_up >= adaptive_threshold
        
        # Strong Bull: LtEMA >= 2.0 AND LtRSI >= 50 → Full position, bypass gates
        if lt_ema >= config.regime_strong_bull_ema and lt_rsi >= config.regime_strong_bull_rsi:
            meta['step0_regime_override'] = 'STRONG_BULL'
            meta['regime_lt_ema'] = lt_ema
            meta['regime_lt_rsi'] = lt_rsi
            
            if not model_predicts_positive:
                # Model says no trade - respect it even in bull regime
                meta['regime_override_skipped'] = 'MODEL_PREDICTS_NEGATIVE'
                if verbose:
                    print(f"  [V3] REGIME STRONG_BULL but model P=0 (prob={prob_up:.3f}<adp_thr={adaptive_threshold:.3f}) → pos=0")
                return 0.0, meta
            
            position = config.regime_strong_bull_position
            meta['position_before_clamp'] = position
            
            # Clamp to max and return (drawdown applied by caller)
            position = min(position, config.max_position)
            meta['final_position'] = position
            if verbose:
                print(f"  [V3] REGIME OVERRIDE: STRONG_BULL (LtEMA={lt_ema:.2f}, LtRSI={lt_rsi:.1f}) → pos={position:.2f}")
            return position, meta
        
        # Mild Bull: LtEMA >= 1.0 AND LtRSI >= 40 → 75% position, bypass gates
        elif lt_ema >= config.regime_mild_bull_ema and lt_rsi >= config.regime_mild_bull_rsi:
            meta['step0_regime_override'] = 'MILD_BULL'
            meta['regime_lt_ema'] = lt_ema
            meta['regime_lt_rsi'] = lt_rsi
            
            if not model_predicts_positive:
                # Model says no trade - respect it even in bull regime
                meta['regime_override_skipped'] = 'MODEL_PREDICTS_NEGATIVE'
                if verbose:
                    print(f"  [V3] REGIME MILD_BULL but model P=0 (prob={prob_up:.3f}<adp_thr={adaptive_threshold:.3f}) → pos=0")
                return 0.0, meta
            
            position = config.regime_mild_bull_position
            meta['position_before_clamp'] = position
            
            # Clamp to max and return (drawdown applied by caller)
            position = min(position, config.max_position)
            meta['final_position'] = position
            if verbose:
                print(f"  [V3] REGIME OVERRIDE: MILD_BULL (LtEMA={lt_ema:.2f}, LtRSI={lt_rsi:.1f}) → pos={position:.2f}")
            return position, meta
        
        # Bear: LtEMA < 1.0 → Use inverted/mean-reversion position, keep gates
        elif lt_ema < config.regime_bear_ema:
            # In bear, we WANT the gates to filter, but use inverse sizing if gates pass
            meta['step0_regime_override'] = 'BEAR_NOTED'
            meta['regime_lt_ema'] = lt_ema
            meta['regime_lt_rsi'] = lt_rsi
            if verbose:
                print(f"  [V3] REGIME NOTED: BEAR (LtEMA={lt_ema:.2f}) → gates active, inverse sizing")
            # Don't return - continue to normal gate processing
        
        else:
            # Neutral zone (1.0 <= LtEMA < 1.5 or RSI conditions not met)
            meta['step0_regime_override'] = 'NEUTRAL'
            meta['regime_lt_ema'] = lt_ema
            meta['regime_lt_rsi'] = lt_rsi
            if verbose:
                print(f"  [V3] REGIME NEUTRAL (LtEMA={lt_ema:.2f}, LtRSI={lt_rsi:.1f}) → normal gates")
            # Don't return - continue to normal gate processing
    
    # ════════════════════════════════════════════════════════════════
    # STEP 1: GATES (Any fail → position = 0)
    # ════════════════════════════════════════════════════════════════
    
    # Gate 1a: Minimum probability
    if prob_up < config.min_prob:
        meta['step1_gate'] = 'FAIL_MIN_PROB'
        if verbose:
            print(f"  [V3] GATE FAIL: prob={prob_up:.3f} < min_prob={config.min_prob}")
        return 0.0, meta
    
    # Gate 1b: Probability vs threshold
    if prob_up < threshold:
        meta['step1_gate'] = 'FAIL_THRESHOLD'
        if verbose:
            print(f"  [V3] GATE FAIL: prob={prob_up:.3f} < threshold={threshold:.3f}")
        return 0.0, meta
    
    # Gate 1c: Alpha gate (expected_return > risk_free)
    if config.use_alpha_gate and expected_return is not None and risk_free_rate is not None:
        alpha = expected_return - risk_free_rate
        if verbose:
            print(f"  [V3] Alpha check: exp_ret={expected_return:.5f}, rf={risk_free_rate:.5f}, alpha={alpha:.5f}")
        if expected_return <= risk_free_rate:
            meta['step1_gate'] = 'FAIL_ALPHA'
            meta['expected_return'] = expected_return
            meta['risk_free_rate'] = risk_free_rate
            if verbose:
                print(f"  [V3] GATE FAIL: alpha={alpha:.5f} <= 0")
            return 0.0, meta
    
    # Gate 1d: Danger Zone (LtEMA > threshold AND StRSI > threshold)
    in_danger_zone = False
    if config.use_danger_zone_gate and dual_ema_data and dual_ema_data.get('has_data', False):
        lt_ema = dual_ema_data.get('long_term_ema', 1.0)
        st_ema = dual_ema_data.get('short_term_ema', 1.0)
        st_rsi = dual_ema_data.get('short_term_rsi', 50.0)
        
        if verbose:
            print(f"  [V3] EMA data: LtEMA={lt_ema:.3f}, StEMA={st_ema:.3f}, StRSI={st_rsi:.1f}")
        
        in_danger_zone = (
            lt_ema > config.danger_zone_ltema_threshold and 
            st_rsi > config.danger_zone_strsi_threshold
        )
        
        meta['danger_zone_check'] = {
            'lt_ema': lt_ema,
            'st_rsi': st_rsi,
            'lt_ema_threshold': config.danger_zone_ltema_threshold,
            'st_rsi_threshold': config.danger_zone_strsi_threshold,
            'in_danger_zone': in_danger_zone,
        }
        
        if in_danger_zone:
            meta['step1_gate'] = 'FAIL_DANGER_ZONE'
            if verbose:
                print(f"  [V3] GATE FAIL: DANGER ZONE (LtEMA={lt_ema:.2f} > {config.danger_zone_ltema_threshold:.2f} "
                      f"AND StRSI={st_rsi:.0f} > {config.danger_zone_strsi_threshold:.0f})")
            return 0.0, meta
    
    # Gate 1e: Ratio Gate (hard stop when ratio < 1.0)
    # NOTE: Primary check with warmup happens in PositionSizingManager
    # This is a backup check for direct function calls (no warmup handling here)
    if config.use_ratio_gate:
        if rolling_ratio < config.ratio_gate_threshold:
            meta['step1_gate'] = 'FAIL_RATIO'
            meta['rolling_ratio_at_gate'] = rolling_ratio
            if verbose:
                print(f"  [V3] GATE FAIL: RATIO ({rolling_ratio:.2f} < {config.ratio_gate_threshold:.2f})")
            return 0.0, meta
    
    meta['step1_gate'] = 'PASS'
    
    # ════════════════════════════════════════════════════════════════
    # HULL-OPTIMAL V2: MARKET-AWARE POSITION SIZING
    # ════════════════════════════════════════════════════════════════
    # KEY INSIGHT from backtest analysis:
    # Hull = Sharpe / (Vol_Penalty × Return_Penalty)
    #
    # THE PARADOX:
    # - BEAR market: Low position → Low vol → Good Hull ✅
    # - BULL market: Low position → Miss gains → Return penalty kills Hull ❌
    #
    # SOLUTION: Use MARKET DIRECTION (cumulative returns), not just model accuracy (LtEMA)
    # - Bull market + low confidence → MODERATE position (avoid return penalty)
    # - Bear market + any confidence → LOW position (avoid vol penalty)
    #
    # Formula:
    #   position = market_base × model_accuracy_scale × confidence_boost
    #   - market_base: depends on market direction (higher in bull)
    #   - model_accuracy_scale: LtEMA-based trust adjustment
    #   - confidence_boost: probability-based scaling
    
    lt_ema_available = (dual_ema_data and 
                        dual_ema_data.get('long_term_ema', 0) > 0)
    
    if config.use_hull_optimal and lt_ema_available:
        lt_ema = dual_ema_data.get('long_term_ema', 1.0)
        lt_rsi = dual_ema_data.get('long_term_rsi', 50.0)
        cumulative_mkt = dual_ema_data.get('cumulative_market_return', 0.0)  # NEW: market direction
        
        # ════════════════════════════════════════════════════════════════
        # STEP 1: DETERMINE MARKET REGIME (based on cumulative market return)
        # ════════════════════════════════════════════════════════════════
        # This is the KEY fix - use actual market direction, not model accuracy
        if cumulative_mkt >= 0.10:  # Market up 10%+ = strong bull
            market_regime = 'BULL_STRONG'
            market_base = 0.55  # Higher base in strong bull to capture gains
        elif cumulative_mkt >= 0.03:  # Market up 3-10% = mild bull  
            market_regime = 'BULL_MILD'
            market_base = 0.45  # Moderate base in mild bull
        elif cumulative_mkt >= -0.03:  # Market flat (-3% to +3%) = neutral
            market_regime = 'NEUTRAL'
            market_base = 0.30  # Conservative in uncertain market
        elif cumulative_mkt >= -0.10:  # Market down 3-10% = mild bear
            market_regime = 'BEAR_MILD'
            market_base = 0.15  # Low in mild bear
        else:  # Market down 10%+ = strong bear
            market_regime = 'BEAR_STRONG'
            market_base = 0.05  # Minimal in strong bear
        
        # ════════════════════════════════════════════════════════════════
        # STEP 2: MODEL ACCURACY ADJUSTMENT (based on LtEMA)
        # ════════════════════════════════════════════════════════════════
        # LtEMA > 1.0 = model is correct more often → trust it more
        # LtEMA < 1.0 = model is wrong more often → trust it less
        if lt_ema >= 1.5:
            model_trust = 1.30  # High trust - model very reliable
            model_label = 'HIGH'
        elif lt_ema >= 1.0:
            model_trust = 1.10  # Good trust - model reliable
            model_label = 'GOOD'
        elif lt_ema >= 0.85:
            model_trust = 0.90  # Reduced trust - model mixed
            model_label = 'MIXED'
        elif lt_ema >= 0.70:
            model_trust = 0.70  # Low trust - model unreliable
            model_label = 'LOW'
        else:
            model_trust = 0.30  # Very low trust - model very unreliable
            model_label = 'VLOW'
        
        # ════════════════════════════════════════════════════════════════
        # STEP 3: CONFIDENCE BOOST (based on probability)
        # ════════════════════════════════════════════════════════════════
        # Only boost when high confidence (prob > 0.6)
        confidence = max(0.0, (prob_up - 0.5) * 2)  # 0 to 1
        confidence_boost = 1.0 + confidence * 0.40  # Max +40% boost at prob=1.0
        
        # ════════════════════════════════════════════════════════════════
        # STEP 4: ASYMMETRIC SCALING (key insight from backtest)
        # ════════════════════════════════════════════════════════════════
        # In BULL markets: Don't reduce too much even with low model trust
        #   → Return penalty hurts more than vol penalty
        # In BEAR markets: Reduce aggressively with low model trust
        #   → Vol penalty is the main concern
        
        if market_regime.startswith('BULL'):
            # Bull market: Floor position at 0.30 to avoid return penalty
            # model_trust adjusts within 0.30-0.70 range based on LtEMA
            min_bull_position = 0.30  # Don't go below this in bull
            raw_position = max(min_bull_position, market_base * model_trust * confidence_boost)
            regime_name = f"{market_regime}_{model_label}"
        elif market_regime == 'NEUTRAL':
            # Neutral: Let model trust fully apply
            raw_position = market_base * model_trust * confidence_boost
            regime_name = f"NEUTRAL_{model_label}"
        else:
            # Bear market: Model trust fully applies, can go very low
            raw_position = market_base * model_trust * confidence_boost
            regime_name = f"{market_regime}_{model_label}"
            
            # Strong bear with very unreliable model → sit out
            if market_regime == 'BEAR_STRONG' and lt_ema < 0.70:
                if config.hull_bear_sit_out:
                    meta['hull_optimal'] = True
                    meta['hull_regime'] = 'SITOUT'
                    meta['hull_lt_ema'] = lt_ema
                    meta['hull_cumulative_mkt'] = cumulative_mkt
                    meta['final_position'] = 0.0
                    if verbose:
                        print(f"  [V3] HULL-V2: SITOUT (Mkt={cumulative_mkt:+.1%}, LtEMA={lt_ema:.2f}) → pos=0.0")
                    return 0.0, meta
        
        # Clamp to bounds
        final_position = np.clip(raw_position, config.hull_min_position, config.hull_max_position)
        
        # Store metadata
        meta['hull_optimal'] = True
        meta['hull_market_regime'] = market_regime
        meta['hull_market_base'] = market_base
        meta['hull_model_trust'] = model_trust
        meta['hull_confidence_boost'] = confidence_boost
        meta['hull_regime'] = regime_name
        meta['hull_raw_position'] = raw_position
        meta['hull_lt_ema'] = lt_ema
        meta['hull_cumulative_mkt'] = cumulative_mkt
        meta['final_position'] = final_position
        
        if verbose:
            print(f"  [V3] HULL-V2: {regime_name} (Mkt={cumulative_mkt:+.1%}, LtEMA={lt_ema:.2f}) | "
                  f"base={market_base:.2f} × trust={model_trust:.2f} × conf={confidence_boost:.2f} "
                  f"= {raw_position:.2f} → {final_position:.2f}")
        
        return final_position, meta
    
    # ════════════════════════════════════════════════════════════════
    # HYBRID3: REGIME-ADAPTIVE POSITION SIZING (fallback if Hull-optimal disabled)
    # ════════════════════════════════════════════════════════════════
    # Based on walk-forward analysis showing:
    # - In bull (LtEMA >= 1.0): Full position works best (trend following)
    # - In bear (LtEMA < 1.0): Inverted signal works best (mean reversion)
    # This achieves 100% win rate on 180-day windows with mean Hull=1.9
    # and minimum Hull=0.85 (never negative!)
    
    # Check if we have usable LtEMA data - match display condition (no n_windows gate)
    # LtEMA is available as soon as ANY config tracking data exists
    lt_ema_available = (dual_ema_data and 
                        dual_ema_data.get('long_term_ema', 0) > 0)  # Just need positive EMA
    
    if config.use_hybrid3_sizing and lt_ema_available:
        lt_ema = dual_ema_data.get('long_term_ema', 1.0)
        
        # LtEMA is already from previous iteration in walk-forward (lagged)
        lt_ema_lag = lt_ema
        
        if lt_ema_lag >= config.hybrid3_ema_threshold:
            # BULL MARKET: Full position (trend following)
            final_position = 1.0
            meta['hybrid3_regime'] = 'BULL'
            meta['hybrid3_position_logic'] = 'FULL_POSITION'
        else:
            # BEAR MARKET: Inverted signal (mean reversion)
            # High model confidence → LOW position (model is wrong in bear)
            # Low model confidence → HIGH position (contrarian)
            baseline_signal = prob_up  # Use probability as signal
            final_position = 1.0 - baseline_signal
            final_position = np.clip(final_position, config.min_position, 1.0)
            meta['hybrid3_regime'] = 'BEAR'
            meta['hybrid3_position_logic'] = 'INVERTED_SIGNAL'
            meta['hybrid3_original_signal'] = baseline_signal
        
        meta['hybrid3_lt_ema'] = lt_ema_lag
        meta['hybrid3_threshold'] = config.hybrid3_ema_threshold
        meta['final_position'] = final_position
        
        if verbose:
            print(f"  [V3] HYBRID3: LtEMA={lt_ema_lag:.3f}, regime={meta['hybrid3_regime']}, pos={final_position:.3f}")
        
        return final_position, meta
    
    # ════════════════════════════════════════════════════════════════
    # FALLBACK: Original position sizing (if Hybrid3 disabled or no EMA data)
    # ════════════════════════════════════════════════════════════════
    
    # ════════════════════════════════════════════════════════════════
    # STEP 2: RATIO SCALING (Momentum-based)
    # ════════════════════════════════════════════════════════════════
    # Scale position based on recent TP/FP ratio
    # NOTE: This is MOMENTUM scaling (high ratio → high position)
    #       It CONFLICTS with inverse scaling in Step 5b
    #       When inverse scale is enabled, we skip this step
    #
    # Mapping (when active):
    #   ratio < 0.5  → factor = 0.3 (very cautious)
    #   ratio = 0.8  → factor = 0.6
    #   ratio = 1.0  → factor = 1.0 (neutral)
    #   ratio = 1.5  → factor = 1.3
    #   ratio > 2.0  → factor = 1.5 (max boost)
    
    ratio_factor = 1.0  # Default: neutral
    
    # Skip momentum scaling if inverse scale is active (they conflict!)
    if config.use_ratio_inverse_scale and config.disable_momentum_scale_when_inverse:
        # Inverse scale handles ratio-based adjustments in Step 5b
        meta['step2_ratio_factor'] = 1.0
        meta['step2_reason'] = 'SKIPPED_INVERSE_ACTIVE'
    else:
        # Traditional momentum scaling
        if rolling_ratio >= 2.0:
            ratio_factor = 1.5
        elif rolling_ratio >= 1.0:
            ratio_factor = 1.0 + (rolling_ratio - 1.0) * 0.5
        elif rolling_ratio >= 0.5:
            ratio_factor = 0.5 + (rolling_ratio - 0.5) * 1.0
        else:
            ratio_factor = 0.3 + rolling_ratio * 0.4
        meta['step2_ratio_factor'] = ratio_factor
        meta['step2_reason'] = 'MOMENTUM_SCALING'
    
    # ════════════════════════════════════════════════════════════════
    # STEP 3: EMA SCALING (when available)
    # ════════════════════════════════════════════════════════════════
    
    ema_crossover_factor = 1.0
    ema_quartile_factor = 1.0
    
    if dual_ema_data and dual_ema_data.get('has_data', False):
        lt_ema = dual_ema_data.get('long_term_ema', 1.0)
        st_ema = dual_ema_data.get('short_term_ema', 1.0)
        
        # Step 3a: EMA Crossover (StEMA vs LtEMA)
        if config.use_ema_crossover_scale:
            if st_ema > lt_ema:
                # Model improving: boost position
                ema_crossover_factor = 1.0 + config.ema_crossover_boost
                meta['ema_crossover'] = 'IMPROVING'
            else:
                # Model declining: reduce position
                ema_crossover_factor = 1.0 - config.ema_crossover_reduce
                meta['ema_crossover'] = 'DECLINING'
            meta['step3a_ema_crossover_factor'] = ema_crossover_factor
        
        # Step 3b: LtEMA Quartile (contrarian)
        if config.use_ltema_quartile_scale:
            if lt_ema < config.ltema_q1_threshold:
                # Q1: Bad performance → contrarian boost (expect improvement)
                ema_quartile_factor = 1.0 + config.ltema_q1_boost
                meta['ltema_zone'] = 'Q1_LOW'
            elif lt_ema > config.ltema_q4_threshold:
                # Q4: Very good performance → expect regression
                ema_quartile_factor = 1.0 - config.ltema_q4_reduce
                meta['ltema_zone'] = 'Q4_HIGH'
            else:
                meta['ltema_zone'] = 'NEUTRAL'
            meta['step3b_ema_quartile_factor'] = ema_quartile_factor
        
        meta['ema_data'] = {
            'lt_ema': lt_ema,
            'st_ema': st_ema,
            'lt_rsi': dual_ema_data.get('long_term_rsi', 50),
            'st_rsi': dual_ema_data.get('short_term_rsi', 50),
        }
    else:
        meta['ema_data'] = None
    
    # ════════════════════════════════════════════════════════════════
    # STEP 4: ALIGNMENT SCALING
    # ════════════════════════════════════════════════════════════════
    # Scale by config agreement
    #
    # Mapping:
    #   alignment = 0.5 → factor = 0.7 (50/50 split = uncertain)
    #   alignment = 0.7 → factor = 1.0 (70% agree)
    #   alignment = 0.9 → factor = 1.2 (90% agree = high conviction)
    #   alignment = 1.0 → factor = 1.3 (100% agree)
    
    if alignment >= 0.9:
        alignment_factor = 1.2 + (alignment - 0.9) * 1.0  # 1.2 to 1.3
    elif alignment >= 0.7:
        alignment_factor = 1.0 + (alignment - 0.7) * 1.0  # 1.0 to 1.2
    elif alignment >= 0.5:
        alignment_factor = 0.7 + (alignment - 0.5) * 1.5  # 0.7 to 1.0
    else:
        # Below 50% - configs disagree with our prediction
        alignment_factor = 0.3 + alignment * 0.8  # 0.3 to 0.7
    
    alignment_factor *= config.alignment_weight
    meta['step4_alignment_factor'] = alignment_factor
    
    # ════════════════════════════════════════════════════════════════
    # STEP 5: VOLATILITY ADJUSTMENT
    # ════════════════════════════════════════════════════════════════
    
    if high_vol:
        vol_factor = config.high_vol_reduction
        meta['step5_vol_regime'] = 'HIGH'
    else:
        vol_factor = 1.0
        meta['step5_vol_regime'] = 'NORMAL'
    
    meta['step5_vol_factor'] = vol_factor
    
    # ════════════════════════════════════════════════════════════════
    # STEP 5b: INVERSE RATIO SCALE (Mean Reversion)
    # ════════════════════════════════════════════════════════════════
    # Based on analysis: LOW ratio predicts HIGH next win rate (mean reversion)
    # - Ratio < 0.8  → 62% WR next trade → INCREASE position
    # - Ratio > 1.2  → 33% WR next trade → DECREASE position
    # This is OPPOSITE to traditional momentum scaling!
    
    ratio_inverse_factor = 1.0
    meta['step5b_inverse_scale'] = 'NOT_USED'
    
    if config.use_ratio_inverse_scale:
        if total_trades < config.ratio_inverse_min_trades:
            # Warmup period
            meta['step5b_inverse_scale'] = 'WARMUP'
            meta['step5b_inverse_trades_until'] = config.ratio_inverse_min_trades - total_trades
        elif rolling_ratio < config.ratio_inverse_low_threshold:
            # LOW ratio → SCALE UP (mean reversion: bad streak ending)
            ratio_inverse_factor = config.ratio_inverse_low_scale
            meta['step5b_inverse_scale'] = 'SCALE_UP'
            if verbose:
                print(f"  [V3] INVERSE SCALE UP: ratio {rolling_ratio:.2f} < {config.ratio_inverse_low_threshold} → scale {ratio_inverse_factor:.2f}")
        elif rolling_ratio > config.ratio_inverse_high_threshold:
            # HIGH ratio → SCALE DOWN (mean reversion: good streak ending)
            ratio_inverse_factor = config.ratio_inverse_high_scale
            meta['step5b_inverse_scale'] = 'SCALE_DOWN'
            if verbose:
                print(f"  [V3] INVERSE SCALE DOWN: ratio {rolling_ratio:.2f} > {config.ratio_inverse_high_threshold} → scale {ratio_inverse_factor:.2f}")
        else:
            meta['step5b_inverse_scale'] = 'NEUTRAL'
    
    meta['step5b_inverse_factor'] = ratio_inverse_factor
    
    # ════════════════════════════════════════════════════════════════
    # STEP 6: COMBINE AND CLAMP
    # ════════════════════════════════════════════════════════════════
    
    raw_position = (config.base_position * ratio_factor * 
                    ema_crossover_factor * ema_quartile_factor * 
                    alignment_factor * vol_factor * ratio_inverse_factor)
    meta['step6_raw_position'] = raw_position
    
    # Determine max position (leverage allowed?)
    can_leverage = (
        rolling_ratio >= config.leverage_min_ratio and
        alignment >= config.leverage_min_alignment and
        not high_vol and
        not in_danger_zone  # No leverage in danger zone (even if we didn't gate)
    )
    
    max_pos = config.max_position if can_leverage else 1.0
    meta['step6_can_leverage'] = can_leverage
    meta['step6_max_position'] = max_pos
    
    # Clamp to valid range
    final_position = np.clip(raw_position, config.min_position, max_pos)
    meta['final_position'] = final_position
    
    if verbose:
        ema_str = ""
        if dual_ema_data and dual_ema_data.get('has_data'):
            ema_str = f", ema_cross={ema_crossover_factor:.2f}, ema_q={ema_quartile_factor:.2f}"
        print(f"  [V3] PASS: ratio_f={ratio_factor:.2f}, align_f={alignment_factor:.2f}, "
              f"vol_f={vol_factor:.2f}{ema_str} → raw={raw_position:.2f} → final={final_position:.2f}")
    
    return final_position, meta


# ═══════════════════════════════════════════════════════════════════════════
# POSITION SIZING MANAGER - Stateful wrapper for use in backtest
# ═══════════════════════════════════════════════════════════════════════════

class PositionSizingManager:
    """
    Stateful manager for position sizing.
    
    Maintains:
    - Rolling ratio tracker
    - Equity tracking (for drawdown protection)
    - Config for tunable parameters
    - Optional: ConfigVotingSystem for weighted voting
    
    Use this in the main backtest loop.
    """
    
    def __init__(self, config: Optional[PositionSizingConfig] = None, use_voting: bool = True):
        self.config = config or PositionSizingConfig()
        self.ratio_tracker = RollingRatioTracker(
            window_size=self.config.ratio_window,
            ema_alpha=self.config.ratio_ema_alpha,
        )
        
        # Equity tracking for drawdown protection
        self.current_equity: float = 1.0  # Start at 1.0 (normalized)
        self.peak_equity: float = 1.0  # Track peak for drawdown calculation
        self.drawdown: float = 0.0  # Current drawdown (0.0 to 1.0)
        self.running_drawdown: float = 0.0  # Alias for drawdown (used in position calc)
        self.last_position: float = 0.0  # Store last position for equity update
        self.equity_history: List[float] = []  # Track equity curve
        
        # Optional voting system integration
        self.use_voting = use_voting
        self.voting_system = None
        if use_voting:
            try:
                from wf_config_voting import ConfigVotingSystem
                self.voting_system = ConfigVotingSystem()
            except ImportError:
                self.use_voting = False
    
    def update_result(self, result: str, market_return: float = None) -> None:
        """
        Update with trade result after seeing actual outcome.
        
        Args:
            result: 'TP', 'FP', 'TN', or 'FN'
            market_return: Actual market return for equity tracking (optional)
        """
        self.ratio_tracker.update(result)
        
        # Update equity if market return provided
        if market_return is not None:
            self.update_equity(market_return)
    
    def update_equity(self, market_return: float, position: float = None) -> None:
        """
        Update equity curve with actual market return.
        
        Strategy return = position * market_return
        (Assumes we went long with 'position' weight)
        
        Args:
            market_return: Actual market return for this period
            position: Position size used (if None, use last_position)
        """
        pos = position if position is not None else self.last_position
        
        # Strategy return based on position
        strategy_return = pos * market_return
        
        # Update equity
        self.current_equity *= (1 + strategy_return)
        self.equity_history.append(self.current_equity)
        
        # Update peak and drawdown
        self.peak_equity = max(self.peak_equity, self.current_equity)
        if self.peak_equity > 0:
            self.drawdown = (self.peak_equity - self.current_equity) / self.peak_equity
            self.running_drawdown = self.drawdown  # Keep in sync
        else:
            self.drawdown = 0.0
            self.running_drawdown = 0.0
    
    def get_drawdown_scale(self) -> Tuple[float, str]:
        """
        Get position scale factor based on current drawdown.
        
        Returns:
            scale: Multiplier for position (0.25 to 1.0)
            level: 'NONE', 'CAUTION', 'SERIOUS', or 'SEVERE'
        """
        if not self.config.use_drawdown_protection:
            return 1.0, 'DISABLED'
        
        if self.drawdown >= self.config.drawdown_severe_threshold:
            return self.config.drawdown_severe_scale, 'SEVERE'
        elif self.drawdown >= self.config.drawdown_serious_threshold:
            return self.config.drawdown_serious_scale, 'SERIOUS'
        elif self.drawdown >= self.config.drawdown_caution_threshold:
            return self.config.drawdown_caution_scale, 'CAUTION'
        else:
            return 1.0, 'NONE'
    
    def update_voting_roles(self, config_stats: List[Dict], current_iter: int) -> None:
        """
        Update voting system with latest config performance.
        
        Args:
            config_stats: List of dicts with config performance
            current_iter: Current iteration
        """
        if self.voting_system:
            self.voting_system.update_roles(config_stats, current_iter)
    
    def calculate_position(
        self,
        prob_up: float,
        threshold: float,
        config_predictions: List[Dict],
        high_vol: bool = False,
        expected_return: Optional[float] = None,
        risk_free_rate: float = 0.0,
        dual_ema_data: Optional[Dict] = None,
        best_top10_ratio: float = 1.0,  # ⭐ Best ratio from Top10 configs
        verbose: bool = False,
    ) -> Tuple[float, Dict]:
        """
        Calculate position size with optional voting system integration.
        
        Args:
            prob_up: Model probability
            threshold: Classification threshold
            config_predictions: List of Top10 config predictions (now with 'name' field for voting)
            high_vol: High volatility regime
            expected_return: Expected return from model (for Alpha Gate)
            risk_free_rate: Risk-free rate for Alpha Gate comparison
            dual_ema_data: Dict with LtEMA/StEMA/LtRSI/StRSI metrics (from scorer)
            best_top10_ratio: Best TP/FP ratio from Top10 configs (for regime override)
            verbose: Debug output
            
        Returns:
            position: 0.0 to max
            meta: Details
        """
        # Get rolling ratio
        rolling_ratio, ratio_meta = self.ratio_tracker.get_combined_ratio()
        
        # ⭐ Use best_top10_ratio if it's better than our rolling ratio
        # This allows regime override to capture bull markets even when selected config has poor ratio
        effective_ratio = max(rolling_ratio, best_top10_ratio)
        ratio_meta['best_top10_ratio'] = best_top10_ratio
        ratio_meta['effective_ratio'] = effective_ratio
        
        # ─────────────────────────────────────────────────────────────────────
        # RATIO GATE (Manager-level check with warmup)
        # ─────────────────────────────────────────────────────────────────────
        total_trades = ratio_meta.get('total_trades', 0)
        ratio_gate_active = False
        
        if self.config.use_ratio_gate:
            if total_trades < self.config.ratio_gate_min_trades:
                # Warmup period - gate not yet active
                ratio_meta['ratio_gate_warmup'] = True
                ratio_meta['trades_until_gate'] = self.config.ratio_gate_min_trades - total_trades
                if verbose:
                    print(f"  [V3] Ratio gate warmup: {total_trades}/{self.config.ratio_gate_min_trades} trades")
            else:
                # Warmup complete - check ratio gate
                ratio_meta['ratio_gate_warmup'] = False
                if rolling_ratio < self.config.ratio_gate_threshold:
                    # HARD GATE - ratio below threshold, position = 0
                    ratio_gate_active = True
                    if verbose:
                        print(f"  [V3] RATIO GATE FAIL: {rolling_ratio:.2f} < {self.config.ratio_gate_threshold:.2f} → position=0")
                    return 0.0, {
                        'step1_gate': 'FAIL_RATIO_MANAGER',
                        'rolling_ratio': rolling_ratio,
                        'ratio_gate_threshold': self.config.ratio_gate_threshold,
                        'total_trades': total_trades,
                        'ratio_meta': ratio_meta,
                    }
        
        # ─────────────────────────────────────────────────────────────────────
        # VOTING SYSTEM (if enabled)
        # ─────────────────────────────────────────────────────────────────────
        voting_result = None
        gatekeeper_veto = False
        voting_scale = 1.0
        
        if self.use_voting and self.voting_system:
            from wf_config_voting import VotingResult
            voting_result = self.voting_system.calculate_vote(config_predictions, verbose=verbose)
            
            # Check for gatekeeper veto
            if voting_result.gatekeeper_veto:
                gatekeeper_veto = True
                if verbose:
                    print(f"  [V3] GATEKEEPER VETO: {voting_result.n_gatekeepers} gatekeepers "
                          f"with alignment={voting_result.gatekeeper_alignment:.2f}")
            
            # Use voting scaling factor
            voting_scale = voting_result.scaling_factor
        
        # ─────────────────────────────────────────────────────────────────────
        # ALIGNMENT (fallback if voting not available)
        # ─────────────────────────────────────────────────────────────────────
        if voting_result:
            # Use weighted alignment from voting
            alignment = voting_result.weighted_alignment
            align_meta = {
                'mode': 'VOTING_WEIGHTED',
                'weighted_alignment': voting_result.weighted_alignment,
                'simple_alignment': voting_result.simple_alignment,
                'gatekeeper_alignment': voting_result.gatekeeper_alignment,
                'n_gatekeepers': voting_result.n_gatekeepers,
                'n_precision': voting_result.n_precision,
            }
        else:
            # Fallback to simple alignment
            alignment, align_meta = calculate_config_alignment(
                config_predictions,
                min_configs=self.config.alignment_min_configs,
            )
        
        # ─────────────────────────────────────────────────────────────────────
        # CALCULATE BASE POSITION
        # ⭐ Use effective_ratio = max(rolling_ratio, best_top10_ratio)
        # This ensures we use the best available ratio for position sizing
        # ─────────────────────────────────────────────────────────────────────
        position, pos_meta = calculate_position_v3(
            prob_up=prob_up,
            threshold=threshold,
            rolling_ratio=effective_ratio,  # ⭐ Use best of our ratio or Top10's best
            alignment=alignment,
            high_vol=high_vol,
            expected_return=expected_return,
            risk_free_rate=risk_free_rate,
            dual_ema_data=dual_ema_data,
            config=self.config,
            verbose=verbose,
            total_trades=total_trades,  # For inverse ratio scale warmup
        )
        
        # ─────────────────────────────────────────────────────────────────────
        # APPLY GATEKEEPER VETO (overrides position)
        # ⭐ BUT: Skip veto if regime override is active (STRONG_BULL or MILD_BULL)
        # Rationale: In clear bull regimes, we trust the regime signal over gatekeepers
        # ─────────────────────────────────────────────────────────────────────
        regime_override_active = pos_meta.get('step0_regime_override') in ['STRONG_BULL', 'MILD_BULL']
        
        if gatekeeper_veto and position > 0 and not regime_override_active:
            pos_meta['gatekeeper_veto'] = True
            pos_meta['position_before_veto'] = position
            position = 0.0
            if verbose:
                print(f"  [V3] Position vetoed by gatekeepers → 0.0")
        elif gatekeeper_veto and regime_override_active:
            pos_meta['gatekeeper_veto_skipped'] = True
            pos_meta['gatekeeper_veto_reason'] = 'REGIME_OVERRIDE_ACTIVE'
            if verbose:
                print(f"  [V3] Gatekeeper veto SKIPPED: regime override active ({pos_meta.get('step0_regime_override')})")
        
        # ─────────────────────────────────────────────────────────────────────
        # APPLY VOTING SCALE (if not vetoed)
        # ─────────────────────────────────────────────────────────────────────
        if not gatekeeper_veto and voting_result and position > 0:
            position_before_scale = position
            position = position * voting_scale
            # Re-clamp after scaling
            max_pos = self.config.max_position if pos_meta.get('step6_can_leverage') else 1.0
            position = np.clip(position, 0.0, max_pos)
            pos_meta['voting_scale'] = voting_scale
            pos_meta['position_before_voting'] = position_before_scale
            if verbose:
                print(f"  [V3] Voting scale: {voting_scale:.2f} → {position:.2f}")
        
        # ─────────────────────────────────────────────────────────────────────
        # APPLY DRAWDOWN PROTECTION SCALE (after voting, before final clamp)
        # Three tiers: caution (3%), serious (5%), severe (8%)
        # ─────────────────────────────────────────────────────────────────────
        drawdown_scale = 1.0
        if self.config.use_drawdown_protection and position > 0:
            drawdown = self.running_drawdown
            
            if drawdown >= self.config.drawdown_severe_threshold:
                # Severe drawdown (8%+) → -75% position
                drawdown_scale = self.config.drawdown_severe_scale
                position_before_dd = position
                position = position * drawdown_scale
                pos_meta['drawdown_severe'] = True
                pos_meta['position_before_drawdown'] = position_before_dd
                if verbose:
                    print(f"  [V3] Drawdown SEVERE: {drawdown:.1%} >= {self.config.drawdown_severe_threshold:.1%} → scale={drawdown_scale:.2f} → {position:.2f}")
            elif drawdown >= self.config.drawdown_serious_threshold:
                # Serious drawdown (5%+) → -50% position
                drawdown_scale = self.config.drawdown_serious_scale
                position_before_dd = position
                position = position * drawdown_scale
                pos_meta['drawdown_serious'] = True
                pos_meta['position_before_drawdown'] = position_before_dd
                if verbose:
                    print(f"  [V3] Drawdown SERIOUS: {drawdown:.1%} → scale={drawdown_scale:.2f} → {position:.2f}")
            elif drawdown >= self.config.drawdown_caution_threshold:
                # Caution drawdown (3%+) → -25% position
                drawdown_scale = self.config.drawdown_caution_scale
                position_before_dd = position
                position = position * drawdown_scale
                pos_meta['drawdown_caution'] = True
                pos_meta['position_before_drawdown'] = position_before_dd
                if verbose:
                    print(f"  [V3] Drawdown CAUTION: {drawdown:.1%} → scale={drawdown_scale:.2f} → {position:.2f}")
            
            pos_meta['drawdown_scale'] = drawdown_scale
            pos_meta['running_drawdown'] = drawdown
        
        # Merge all metadata
        meta = {
            **pos_meta,
            'ratio_meta': ratio_meta,
            'align_meta': align_meta,
        }
        
        # Add voting metadata if available
        if voting_result:
            meta['voting'] = {
                'weighted_alignment': voting_result.weighted_alignment,
                'gatekeeper_alignment': voting_result.gatekeeper_alignment,
                'gatekeeper_veto': voting_result.gatekeeper_veto,
                'scaling_factor': voting_result.scaling_factor,
                'n_gatekeepers': voting_result.n_gatekeepers,
                'n_precision': voting_result.n_precision,
            }
        
        return position, meta
    
    def get_voting_state(self) -> Optional[Dict]:
        """Get voting system state for checkpointing."""
        if self.voting_system:
            return self.voting_system.get_state()
        return None
    
    def load_voting_state(self, state: Dict) -> None:
        """Load voting system state from checkpoint."""
        if self.voting_system and state:
            self.voting_system.load_state(state)
    
    def update_equity(self, market_return: float, position: float, verbose: bool = False) -> Dict:
        """
        Update equity tracking after each iteration.
        
        Call this AFTER the iteration completes with the actual market return.
        
        Args:
            market_return: The actual market return for this period (e.g., 0.01 for +1%)
            position: The position size that was used (0.0 to 2.0)
            verbose: Debug output
            
        Returns:
            Dict with equity tracking info
        """
        # Calculate PnL for this period
        # Position 1.0 = 100% exposure, 2.0 = 200% exposure (leveraged)
        pnl = market_return * position
        
        # Update equity
        old_equity = self.current_equity
        self.current_equity = self.current_equity * (1 + pnl)
        
        # Update peak equity (high water mark)
        if self.current_equity > self.peak_equity:
            self.peak_equity = self.current_equity
        
        # Calculate running drawdown from peak
        if self.peak_equity > 0:
            self.running_drawdown = (self.peak_equity - self.current_equity) / self.peak_equity
        else:
            self.running_drawdown = 0.0
        
        if verbose:
            print(f"  [V3-EQUITY] pnl={pnl:.4f}, equity={self.current_equity:.4f}, "
                  f"peak={self.peak_equity:.4f}, drawdown={self.running_drawdown:.2%}")
        
        return {
            'pnl': pnl,
            'old_equity': old_equity,
            'new_equity': self.current_equity,
            'peak_equity': self.peak_equity,
            'running_drawdown': self.running_drawdown,
        }
    
    def reset_equity(self, initial_equity: float = 1.0) -> None:
        """Reset equity tracking (e.g., at start of new window)."""
        self.peak_equity = initial_equity
        self.current_equity = initial_equity
        self.running_drawdown = 0.0
    
    def get_equity_state(self) -> Dict:
        """Get equity state for checkpointing."""
        return {
            'peak_equity': self.peak_equity,
            'current_equity': self.current_equity,
            'running_drawdown': self.running_drawdown,
        }
    
    def load_equity_state(self, state: Dict) -> None:
        """Load equity state from checkpoint."""
        if state:
            self.peak_equity = state.get('peak_equity', 1.0)
            self.current_equity = state.get('current_equity', 1.0)
            self.running_drawdown = state.get('running_drawdown', 0.0)


# ═══════════════════════════════════════════════════════════════════════════
# TESTING
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 70)
    print("POSITION SIZING V3 - CLEAN PIPELINE TEST")
    print("=" * 70)
    
    # Create manager
    manager = PositionSizingManager()
    
    # Simulate some history
    print("\n--- Simulating 20 trades (12 TP, 8 FP) ---")
    for i in range(12):
        manager.update_result('TP')
    for i in range(8):
        manager.update_result('FP')
    
    rolling_ratio, ratio_meta = manager.ratio_tracker.get_combined_ratio()
    print(f"Rolling ratio: {rolling_ratio:.2f}")
    print(f"Ratio meta: {ratio_meta}")
    
    # Test scenarios
    print("\n" + "-" * 70)
    print("Test Scenarios:")
    print("-" * 70)
    
    scenarios = [
        {
            "name": "Gate fail (prob < threshold)",
            "prob": 0.48, "threshold": 0.51,
            "configs": [{"prob": 0.52, "threshold": 0.50}] * 5,
            "high_vol": False,
        },
        {
            "name": "Low alignment (50%)",
            "prob": 0.55, "threshold": 0.51,
            "configs": [{"prob": 0.52, "threshold": 0.50}] * 5 + [{"prob": 0.48, "threshold": 0.50}] * 5,
            "high_vol": False,
        },
        {
            "name": "High alignment (80%)",
            "prob": 0.55, "threshold": 0.51,
            "configs": [{"prob": 0.55, "threshold": 0.50}] * 8 + [{"prob": 0.45, "threshold": 0.50}] * 2,
            "high_vol": False,
        },
        {
            "name": "Perfect alignment (100%)",
            "prob": 0.60, "threshold": 0.51,
            "configs": [{"prob": 0.60, "threshold": 0.50}] * 10,
            "high_vol": False,
        },
        {
            "name": "High vol reduction",
            "prob": 0.60, "threshold": 0.51,
            "configs": [{"prob": 0.60, "threshold": 0.50}] * 10,
            "high_vol": True,
        },
    ]
    
    for scenario in scenarios:
        position, meta = manager.calculate_position(
            prob_up=scenario["prob"],
            threshold=scenario["threshold"],
            config_predictions=scenario["configs"],
            high_vol=scenario["high_vol"],
            verbose=False,
        )
        
        gate = meta.get('step1_gate', 'N/A')
        ratio_f = meta.get('step2_ratio_factor', 0)
        align_f = meta.get('step3_alignment_factor', 0)
        vol_f = meta.get('step4_vol_factor', 1)
        
        print(f"{scenario['name']:35} | Pos={position:.2f} | Gate={gate:12} | "
              f"R={ratio_f:.2f} A={align_f:.2f} V={vol_f:.2f}")
    
    # Test with better ratio
    print("\n--- After 20 more TPs (32 TP, 8 FP = ratio 4.0) ---")
    for i in range(20):
        manager.update_result('TP')
    
    rolling_ratio, ratio_meta = manager.ratio_tracker.get_combined_ratio()
    print(f"Rolling ratio: {rolling_ratio:.2f}")
    
    position, meta = manager.calculate_position(
        prob_up=0.60,
        threshold=0.51,
        config_predictions=[{"prob": 0.60, "threshold": 0.50}] * 10,
        high_vol=False,
        verbose=True,
    )
    print(f"Final position: {position:.2f}")
    print(f"Can leverage: {meta.get('step5_can_leverage', False)}")
    
    print("\n" + "=" * 70)
    print("Done.")
