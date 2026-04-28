"""
Position Sizing Meta-Model for Hull Competition
================================================

Objective: Optimal position sizing (0.0 to 2.0) for S&P 500 daily returns.

This implements a reward-risk-yield meta-model that combines:
1. Direction confidence (P(UP))
2. Expected magnitude (volatility-scaled returns)
3. Model performance tracking (EMA-based)
4. Risk regime awareness (vol regime, drawdown protection)
5. Kelly criterion-inspired sizing with fractional adjustment

Competition constraints:
- Long-only (no short positions)
- Position range: 0.0 (cash) to 2.0 (2x leverage)
- Metric: Adjusted Sharpe with volatility and return penalties
"""

import numpy as np
from typing import Dict, Tuple, Optional, List
from dataclasses import dataclass


@dataclass
class PositionSizingConfig:
    """Configuration for the position sizing meta-model."""
    
    # Kelly fraction (typically 0.25-0.5 for risk management)
    kelly_fraction: float = 0.35
    
    # Confidence thresholds
    min_confidence_to_trade: float = 0.52  # Below this = 0 position
    high_confidence_threshold: float = 0.58  # Above this = can use leverage
    
    # Volatility regime thresholds
    low_vol_percentile: float = 25  # Below = calm market
    high_vol_percentile: float = 75  # Above = volatile market
    
    # Model performance thresholds (EMA-based)
    ema_declining_threshold: float = 0.95  # StEMA/LtEMA below this = reduce
    ema_improving_threshold: float = 1.05  # StEMA/LtEMA above this = increase
    
    # Risk budget
    max_position: float = 2.0  # Maximum leverage
    min_position: float = 0.0  # Full cash
    base_position: float = 1.0  # Neutral = 100% equity
    
    # Drawdown protection
    max_drawdown_trigger: float = 0.05  # 5% drawdown = reduce exposure
    drawdown_reduction_factor: float = 0.5  # Cut position by half
    
    # Position smoothing
    max_position_change: float = 0.5  # Max change per iteration
    
    # Performance decay (recent predictions matter more)
    performance_ema_fast: int = 10
    performance_ema_slow: int = 50


class PositionSizingMetaModel:
    """
    Reward-Risk-Yield Meta-Model for optimal position sizing.
    
    Philosophy:
    - Markets are not fully efficient, but edges are small
    - Size positions based on confidence AND expected magnitude
    - Protect capital during uncertain regimes
    - Adapt to model performance (reduce when failing, increase when winning)
    """
    
    def __init__(self, config: PositionSizingConfig = None):
        self.config = config or PositionSizingConfig()
        
        # Track historical data for adaptive sizing
        self.returns_history: List[float] = []
        self.predictions_history: List[Dict] = []
        self.position_history: List[float] = []
        self.performance_history: List[int] = []  # 1 = TP, 0 = FP/TN, -1 = FN
        
        # Computed metrics
        self.vol_percentiles: Dict[str, float] = {}
        self.running_drawdown: float = 0.0
        self.peak_equity: float = 1.0
        self.current_equity: float = 1.0
    
    def update_history(self, 
                       actual_return: float, 
                       prediction_correct: bool,
                       position_taken: float) -> None:
        """Update historical data after observing actual outcome."""
        self.returns_history.append(actual_return)
        self.position_history.append(position_taken)
        
        # Update performance tracking
        if position_taken > 0.1:  # Had a position
            self.performance_history.append(1 if prediction_correct else -1)
        else:
            self.performance_history.append(0)  # No position
        
        # Update drawdown tracking
        self.current_equity *= (1 + position_taken * actual_return)
        self.peak_equity = max(self.peak_equity, self.current_equity)
        self.running_drawdown = (self.peak_equity - self.current_equity) / self.peak_equity
        
        # Recalculate volatility percentiles
        if len(self.returns_history) >= 30:
            abs_returns = np.abs(self.returns_history[-252:])  # Last year
            self.vol_percentiles = {
                'p25': np.percentile(abs_returns, 25),
                'p50': np.percentile(abs_returns, 50),
                'p75': np.percentile(abs_returns, 75),
            }
    
    def calculate_kelly_position(self,
                                  win_probability: float,
                                  win_return: float,
                                  loss_return: float) -> float:
        """
        Kelly Criterion position sizing.
        
        Kelly formula: f* = (p * b - q) / b
        Where:
            p = probability of winning
            q = probability of losing (1 - p)
            b = odds (win_return / |loss_return|)
        
        Returns fraction of capital to risk.
        """
        if win_probability <= 0.5 or win_return <= 0 or loss_return >= 0:
            return 0.0
        
        p = win_probability
        q = 1 - p
        b = win_return / abs(loss_return)
        
        kelly_f = (p * b - q) / b
        
        # Apply fractional Kelly for risk management
        kelly_f *= self.config.kelly_fraction
        
        # Clamp to valid range
        return np.clip(kelly_f, 0.0, self.config.max_position)
    
    def calculate_optimal_position(self,
                                    prob_up: float,
                                    expected_return: float,
                                    expected_volatility: float,
                                    model_performance: Dict,
                                    market_regime: Dict,
                                    verbose: bool = False) -> Tuple[float, Dict]:
        """
        Calculate optimal position size given all available information.
        
        Args:
            prob_up: Calibrated probability of positive return (0-1)
            expected_return: Ridge model's predicted return magnitude
            expected_volatility: Predicted volatility (vol model output)
            model_performance: Dict with EMA metrics (lt_ema, st_ema, lt_rsi, st_rsi)
            market_regime: Dict with regime info (vol_regime, uptrend, hmm_regime)
            
        Returns:
            Tuple of (position_size, metadata_dict)
        """
        cfg = self.config
        
        # Initialize metadata
        meta = {
            'prob_up': prob_up,
            'expected_return': expected_return,
            'expected_volatility': expected_volatility,
            'components': {},
            'adjustments': {},
            'gates': {},
        }
        
        # ═══════════════════════════════════════════════════════════════
        # GATE 1: MINIMUM CONFIDENCE
        # ═══════════════════════════════════════════════════════════════
        if prob_up < cfg.min_confidence_to_trade:
            meta['gates']['confidence'] = 'FAIL'
            meta['reason'] = f'Low confidence: {prob_up:.3f} < {cfg.min_confidence_to_trade}'
            meta['final_position'] = 0.0
            return 0.0, meta
        meta['gates']['confidence'] = 'PASS'
        
        # ═══════════════════════════════════════════════════════════════
        # GATE 2: DRAWDOWN PROTECTION
        # ═══════════════════════════════════════════════════════════════
        if self.running_drawdown > cfg.max_drawdown_trigger:
            meta['gates']['drawdown'] = 'TRIGGERED'
            meta['adjustments']['drawdown_reduction'] = cfg.drawdown_reduction_factor
        else:
            meta['gates']['drawdown'] = 'OK'
            meta['adjustments']['drawdown_reduction'] = 1.0
        
        # ═══════════════════════════════════════════════════════════════
        # COMPONENT 1: KELLY-BASED POSITION
        # ═══════════════════════════════════════════════════════════════
        # Estimate win/loss returns based on expected volatility and direction
        avg_daily_vol = expected_volatility if expected_volatility > 0 else 0.01
        
        # Expected returns conditional on direction
        expected_up_return = abs(expected_return) if expected_return > 0 else avg_daily_vol
        expected_down_return = -avg_daily_vol  # Conservative loss estimate
        
        kelly_position = self.calculate_kelly_position(
            win_probability=prob_up,
            win_return=expected_up_return,
            loss_return=expected_down_return
        )
        meta['components']['kelly'] = kelly_position
        
        # ═══════════════════════════════════════════════════════════════
        # COMPONENT 2: CONFIDENCE SCALING
        # ═══════════════════════════════════════════════════════════════
        # Scale position based on how far confidence is from threshold
        confidence_excess = (prob_up - cfg.min_confidence_to_trade) / (1.0 - cfg.min_confidence_to_trade)
        confidence_multiplier = 0.5 + confidence_excess  # 0.5 to 1.5 range
        meta['components']['confidence_multiplier'] = confidence_multiplier
        
        # ═══════════════════════════════════════════════════════════════
        # COMPONENT 3: VOLATILITY REGIME ADJUSTMENT
        # ═══════════════════════════════════════════════════════════════
        vol_regime = market_regime.get('vol_regime', 'normal')
        high_vol = market_regime.get('high_vol_regime', False)
        
        if high_vol or vol_regime == 'high':
            # High volatility = reduce exposure
            vol_adjustment = 0.7
            meta['adjustments']['vol_regime'] = 'HIGH_VOL (-30%)'
        elif vol_regime == 'low' or (self.vol_percentiles and 
             expected_volatility < self.vol_percentiles.get('p25', 0.005)):
            # Low volatility = can increase slightly
            vol_adjustment = 1.15
            meta['adjustments']['vol_regime'] = 'LOW_VOL (+15%)'
        else:
            vol_adjustment = 1.0
            meta['adjustments']['vol_regime'] = 'NORMAL'
        
        meta['components']['vol_adjustment'] = vol_adjustment
        
        # ═══════════════════════════════════════════════════════════════
        # COMPONENT 4: MODEL PERFORMANCE SCALING (EMA-BASED)
        # ═══════════════════════════════════════════════════════════════
        lt_ema = model_performance.get('long_term_ema', 1.0)
        st_ema = model_performance.get('short_term_ema', 1.0)
        lt_rsi = model_performance.get('long_term_rsi', 50)
        st_rsi = model_performance.get('short_term_rsi', 50)
        
        ema_ratio = st_ema / lt_ema if lt_ema > 0 else 1.0
        
        if ema_ratio > cfg.ema_improving_threshold:
            # Model improving - increase exposure
            ema_adjustment = 1.15
            meta['adjustments']['model_ema'] = 'IMPROVING (+15%)'
        elif ema_ratio < cfg.ema_declining_threshold:
            # Model declining - reduce exposure
            ema_adjustment = 0.75
            meta['adjustments']['model_ema'] = 'DECLINING (-25%)'
        else:
            ema_adjustment = 1.0
            meta['adjustments']['model_ema'] = 'STABLE'
        
        # Danger zone: high EMA + high RSI (overconfidence)
        if lt_ema > 1.1 and st_rsi > 65:
            ema_adjustment *= 0.75
            meta['adjustments']['danger_zone'] = 'ACTIVE (-25%)'
        else:
            meta['adjustments']['danger_zone'] = 'INACTIVE'
        
        meta['components']['ema_adjustment'] = ema_adjustment
        
        # ═══════════════════════════════════════════════════════════════
        # COMPONENT 5: REGIME OVERLAY
        # ═══════════════════════════════════════════════════════════════
        uptrend = market_regime.get('uptrend_regime', 1)
        hmm_regime = market_regime.get('hmm_regime', 1)
        
        if uptrend == 1 and hmm_regime in [0, 1]:
            # Bullish regime
            regime_adjustment = 1.1
            meta['adjustments']['market_regime'] = 'BULLISH (+10%)'
        elif uptrend == 0 and hmm_regime == 2:
            # Bearish regime - be cautious
            regime_adjustment = 0.7
            meta['adjustments']['market_regime'] = 'BEARISH (-30%)'
        else:
            regime_adjustment = 1.0
            meta['adjustments']['market_regime'] = 'NEUTRAL'
        
        meta['components']['regime_adjustment'] = regime_adjustment
        
        # ═══════════════════════════════════════════════════════════════
        # COMBINE ALL COMPONENTS
        # ═══════════════════════════════════════════════════════════════
        # Base position from Kelly
        base = kelly_position
        
        # Apply all adjustments multiplicatively
        raw_position = (
            base 
            * confidence_multiplier 
            * vol_adjustment 
            * ema_adjustment 
            * regime_adjustment 
            * meta['adjustments']['drawdown_reduction']
        )
        
        meta['raw_position'] = raw_position
        
        # ═══════════════════════════════════════════════════════════════
        # LEVERAGE DECISION
        # ═══════════════════════════════════════════════════════════════
        # Only use leverage if:
        # 1. High confidence (prob > high_confidence_threshold)
        # 2. Model is performing well (EMA improving)
        # 3. Low volatility regime
        # 4. No drawdown concerns
        
        can_leverage = (
            prob_up >= cfg.high_confidence_threshold and
            ema_ratio >= 1.0 and
            not high_vol and
            self.running_drawdown < 0.02  # Less than 2% drawdown
        )
        
        if can_leverage:
            max_allowed = cfg.max_position  # 2.0
            meta['leverage_allowed'] = True
        else:
            max_allowed = cfg.base_position  # 1.0
            meta['leverage_allowed'] = False
        
        # ═══════════════════════════════════════════════════════════════
        # FINAL POSITION WITH SMOOTHING
        # ═══════════════════════════════════════════════════════════════
        # Clamp to allowed range
        position = np.clip(raw_position, cfg.min_position, max_allowed)
        
        # Apply position change smoothing (if we have history)
        if self.position_history:
            last_position = self.position_history[-1]
            position_change = position - last_position
            
            if abs(position_change) > cfg.max_position_change:
                # Limit the change
                position = last_position + np.sign(position_change) * cfg.max_position_change
                meta['smoothing_applied'] = True
            else:
                meta['smoothing_applied'] = False
        
        # Final clamp
        position = np.clip(position, cfg.min_position, max_allowed)
        
        meta['final_position'] = position
        meta['max_allowed'] = max_allowed
        
        if verbose:
            print(f"  [PosSizing] Kelly={kelly_position:.2f}, Conf={confidence_multiplier:.2f}, "
                  f"Vol={vol_adjustment:.2f}, EMA={ema_adjustment:.2f}, Regime={regime_adjustment:.2f}")
            print(f"  [PosSizing] Raw={raw_position:.2f}, Max={max_allowed:.1f}, Final={position:.2f}")
        
        return position, meta
    
    def get_position_description(self, position: float) -> str:
        """Human-readable description of position."""
        if position < 0.05:
            return "💰 CASH (0% equity - no trade)"
        elif position < 0.3:
            return "🔻 MINIMAL (5-30% equity - very cautious)"
        elif position < 0.6:
            return "⬇️ UNDERWEIGHT (30-60% equity - cautious)"
        elif position < 0.9:
            return "↘️ SLIGHT_UNDER (60-90% equity - slightly cautious)"
        elif position < 1.1:
            return "➡️ NEUTRAL (90-110% equity - baseline)"
        elif position < 1.4:
            return "↗️ OVERWEIGHT (110-140% equity - moderately bullish)"
        elif position < 1.7:
            return "⬆️ STRONG_LONG (140-170% equity - bullish)"
        else:
            return "🚀 MAX_LEVERAGE (170-200% equity - maximum conviction)"


class PositionSizingEnsemble:
    """
    Ensemble of position sizing strategies for robustness.
    
    Combines multiple approaches:
    1. Kelly-based (probability + magnitude)
    2. Risk parity (volatility targeting)
    3. Performance adaptive (EMA-based)
    
    Uses weighted average with weights based on recent performance.
    """
    
    def __init__(self):
        # Individual strategies
        self.kelly_model = PositionSizingMetaModel(PositionSizingConfig(kelly_fraction=0.4))
        self.conservative_model = PositionSizingMetaModel(PositionSizingConfig(kelly_fraction=0.25, min_confidence_to_trade=0.54))
        self.aggressive_model = PositionSizingMetaModel(PositionSizingConfig(kelly_fraction=0.5, high_confidence_threshold=0.55))
        
        # Track which strategy is performing best
        self.strategy_performance = {
            'kelly': [],
            'conservative': [],
            'aggressive': []
        }
        
        # Adaptive weights
        self.weights = {'kelly': 0.4, 'conservative': 0.4, 'aggressive': 0.2}
    
    def calculate_ensemble_position(self,
                                     prob_up: float,
                                     expected_return: float,
                                     expected_volatility: float,
                                     model_performance: Dict,
                                     market_regime: Dict,
                                     verbose: bool = False) -> Tuple[float, Dict]:
        """
        Calculate position using weighted ensemble of strategies.
        """
        positions = {}
        metas = {}
        
        # Get position from each strategy
        for name, model in [('kelly', self.kelly_model), 
                            ('conservative', self.conservative_model),
                            ('aggressive', self.aggressive_model)]:
            pos, meta = model.calculate_optimal_position(
                prob_up, expected_return, expected_volatility,
                model_performance, market_regime, verbose=False
            )
            positions[name] = pos
            metas[name] = meta
        
        # Weighted average
        ensemble_position = sum(
            positions[name] * self.weights[name] 
            for name in positions
        )
        
        if verbose:
            print(f"  [Ensemble] Kelly={positions['kelly']:.2f}, Cons={positions['conservative']:.2f}, "
                  f"Agg={positions['aggressive']:.2f} → Ens={ensemble_position:.2f}")
        
        return ensemble_position, {
            'individual_positions': positions,
            'weights': self.weights,
            'ensemble_position': ensemble_position
        }
    
    def update_weights(self, actual_return: float, positions_taken: Dict[str, float]) -> None:
        """
        Update strategy weights based on performance.
        
        Strategies that would have performed well get higher weight.
        """
        for name, position in positions_taken.items():
            strategy_return = position * actual_return
            self.strategy_performance[name].append(strategy_return)
        
        # Recalculate weights based on recent Sharpe ratios
        if all(len(v) >= 30 for v in self.strategy_performance.values()):
            sharpes = {}
            for name, returns in self.strategy_performance.items():
                recent = returns[-100:]  # Last 100 trades
                if np.std(recent) > 0:
                    sharpes[name] = np.mean(recent) / np.std(recent)
                else:
                    sharpes[name] = 0
            
            # Softmax weighting
            total = sum(np.exp(s) for s in sharpes.values())
            if total > 0:
                self.weights = {name: np.exp(s) / total for name, s in sharpes.items()}


# ═══════════════════════════════════════════════════════════════════════
# SIMPLE POSITION SIZING FUNCTION (for direct integration)
# ═══════════════════════════════════════════════════════════════════════

def calculate_position_v2(
    prob_up: float,
    threshold: float,
    expected_return: float,
    expected_volatility: float,
    risk_free_rate: float,
    dual_ema_data: Dict,
    past_ratio: float,
    market_regime: Dict,
    running_drawdown: float = 0.0,
    verbose: bool = False
) -> Tuple[float, Dict]:
    """
    Simplified position sizing function combining all factors.
    
    This is the main entry point for the walk-forward loop.
    
    Args:
        prob_up: Calibrated P(return > 0)
        threshold: Decision threshold (from config selection)
        expected_return: Predicted return magnitude
        expected_volatility: Predicted volatility
        risk_free_rate: Current risk-free rate
        dual_ema_data: Model performance metrics (lt_ema, st_ema, etc.)
        past_ratio: Historical TP/FP ratio
        market_regime: Dict with regime indicators
        running_drawdown: Current drawdown from peak
        
    Returns:
        position (0.0 to 2.0), metadata dict
    """
    meta = {
        'prob_up': prob_up,
        'threshold': threshold,
        'expected_return': expected_return,
        'expected_volatility': expected_volatility,
        'past_ratio': past_ratio,
        'running_drawdown': running_drawdown,
    }
    
    # ════════════════════════════════════════════════════════════════
    # REDESIGNED: STABILITY + PRECISION BASED POSITION SIZING
    # ════════════════════════════════════════════════════════════════
    # 
    # KEY INSIGHT: We should NOT use model classification threshold
    # for position sizing. That threshold is for model gating (classification).
    #
    # For position sizing, we use:
    # 1. TP/FP ratio from past performance (precision indicator)
    # 2. EMA-weighted model performance (stability indicator)
    # 3. Probability edge (how far above 0.50)
    #
    # The "threshold" parameter is IGNORED for position sizing.
    # We only care about: ratio, EMA trend, and probability edge.
    
    # ────────────────────────────────────────────────────────────────
    # STEP 1: PROBABILITY EDGE (how much better than random)
    # ────────────────────────────────────────────────────────────────
    # This is the RAW edge, independent of threshold
    prob_edge = max(0, prob_up - 0.50)  # 0 to 0.50 range
    meta['prob_edge'] = prob_edge
    
    # Minimum edge to consider trading at all
    MIN_EDGE = 0.01  # Must be at least 51% confident
    if prob_edge < MIN_EDGE:
        meta['gate'] = 'NO_EDGE'
        if verbose:
            print(f"  [PosV2] NO EDGE: prob={prob_up:.3f}, edge={prob_edge:.3f} < {MIN_EDGE}")
        return 0.0, meta
    
    # ────────────────────────────────────────────────────────────────
    # STEP 2: RATIO-BASED CONFIDENCE (precision from past TP/FP)
    # ────────────────────────────────────────────────────────────────
    # past_ratio = TP/FP from rolling history
    # This is our PRIMARY reliability indicator
    
    if past_ratio is None:
        # Warmup: use moderate confidence
        ratio_confidence = 0.5
        meta['ratio_mode'] = 'WARMUP'
    elif past_ratio < 0.5:
        # Very poor performance: minimal or no position
        ratio_confidence = 0.1
        meta['ratio_mode'] = 'POOR'
    elif past_ratio < 0.8:
        # Below breakeven: cautious
        ratio_confidence = 0.2 + (past_ratio - 0.5) * 0.5  # 0.2 to 0.35
        meta['ratio_mode'] = 'CAUTIOUS'
    elif past_ratio < 1.0:
        # Near breakeven: moderate
        ratio_confidence = 0.35 + (past_ratio - 0.8) * 1.5  # 0.35 to 0.65
        meta['ratio_mode'] = 'MODERATE'
    elif past_ratio < 1.3:
        # Good performance: confident
        ratio_confidence = 0.65 + (past_ratio - 1.0) * 1.0  # 0.65 to 0.95
        meta['ratio_mode'] = 'GOOD'
    else:
        # Excellent performance: high confidence
        ratio_confidence = min(0.95 + (past_ratio - 1.3) * 0.2, 1.3)  # 0.95 to 1.3
        meta['ratio_mode'] = 'EXCELLENT'
    
    meta['ratio_confidence'] = ratio_confidence
    
    # ────────────────────────────────────────────────────────────────
    # STEP 3: EMA STABILITY SCORE (model consistency over time)
    # ────────────────────────────────────────────────────────────────
    # Uses dual EMA crossover to detect improving vs declining model
    
    if dual_ema_data.get('has_data', False):
        st_ema = dual_ema_data.get('short_term_ema', 1.0)
        lt_ema = dual_ema_data.get('long_term_ema', 1.0)
        st_rsi = dual_ema_data.get('short_term_rsi', 50)
        
        # EMA crossover: short/long ratio
        ema_crossover = st_ema / lt_ema if lt_ema > 0 else 1.0
        
        # Stability score based on crossover direction and magnitude
        if ema_crossover > 1.1:
            stability_score = 1.3  # Strong improvement
            meta['stability_mode'] = 'IMPROVING_STRONG'
        elif ema_crossover > 1.0:
            stability_score = 1.0 + (ema_crossover - 1.0) * 3  # 1.0 to 1.3
            meta['stability_mode'] = 'IMPROVING'
        elif ema_crossover > 0.9:
            stability_score = 0.7 + (ema_crossover - 0.9) * 3  # 0.7 to 1.0
            meta['stability_mode'] = 'STABLE'
        else:
            stability_score = max(0.3, 0.7 - (0.9 - ema_crossover) * 2)  # 0.3 to 0.7
            meta['stability_mode'] = 'DECLINING'
        
        # RSI adjustment: penalize extremes
        if st_rsi > 75:
            stability_score *= 0.8  # Overbought danger
            meta['rsi_warning'] = 'OVERBOUGHT'
        elif st_rsi < 25:
            stability_score *= 0.9  # Oversold caution
            meta['rsi_warning'] = 'OVERSOLD'
        else:
            meta['rsi_warning'] = 'NORMAL'
        
        meta['ema_crossover'] = ema_crossover
        meta['stability_score'] = stability_score
    else:
        # Warmup: neutral stability
        stability_score = 0.8
        meta['ema_crossover'] = 1.0
        meta['stability_score'] = 0.8
        meta['stability_mode'] = 'WARMUP'
    
    # ────────────────────────────────────────────────────────────────
    # STEP 4: COMBINE INTO POSITION SIZE
    # ────────────────────────────────────────────────────────────────
    # Position = edge × ratio_confidence × stability_score
    # 
    # This creates a smooth 0-2 range:
    # - edge: 0-0.50 (how confident in direction)
    # - ratio_confidence: 0.1-1.3 (how good is past performance)
    # - stability_score: 0.3-1.3 (is model improving or declining)
    
    # Scale edge to 0-2 base range
    base_from_edge = prob_edge * 4  # 0.01→0.04, 0.10→0.40, 0.25→1.0, 0.50→2.0
    
    # Apply modifiers
    raw_position = base_from_edge * ratio_confidence * stability_score
    meta['base_from_edge'] = base_from_edge
    meta['raw_position'] = raw_position
    
    if verbose:
        print(f"  [PosV2] edge={prob_edge:.3f}→base={base_from_edge:.2f}, "
              f"ratio_conf={ratio_confidence:.2f}, stab={stability_score:.2f} → raw={raw_position:.2f}")
    
    # ────────────────────────────────────────────────────────────────
    # STEP 5: VOLATILITY ADJUSTMENT
    # ────────────────────────────────────────────────────────────────
    
    high_vol = market_regime.get('high_vol_regime', False)
    if high_vol:
        vol_mult = 0.70  # -30% in high vol
        meta['vol_regime'] = 'HIGH'
    else:
        vol_mult = 1.0
        meta['vol_regime'] = 'NORMAL'
    
    meta['vol_mult'] = vol_mult
    
    # ────────────────────────────────────────────────────────────────
    # STEP 6: DRAWDOWN PROTECTION
    # ────────────────────────────────────────────────────────────────
    
    if running_drawdown > 0.05:
        dd_mult = 0.50
        meta['dd_protection'] = 'ACTIVE'
    elif running_drawdown > 0.03:
        dd_mult = 0.75
        meta['dd_protection'] = 'CAUTION'
    else:
        dd_mult = 1.0
        meta['dd_protection'] = 'NONE'
    
    meta['dd_mult'] = dd_mult
    
    # ────────────────────────────────────────────────────────────────
    # STEP 7: FINAL POSITION
    # ────────────────────────────────────────────────────────────────
    
    final_position = raw_position * vol_mult * dd_mult
    
    # Leverage decision: allow >1.0 only with very strong signals
    # Require: ratio > 1.2, stability improving, not high vol
    can_leverage = (
        past_ratio is not None and past_ratio >= 1.2 and
        stability_score >= 1.0 and
        not high_vol and
        running_drawdown < 0.02
    )
    
    max_position = 2.0 if can_leverage else 1.0
    meta['leverage_allowed'] = can_leverage
    meta['max_position'] = max_position
    
    final_position = np.clip(final_position, 0.0, max_position)
    meta['final_position'] = final_position
    meta['gate'] = 'PASSED'
    
    if verbose:
        print(f"  [PosV2] Final={final_position:.2f} (vol={vol_mult:.2f}, dd={dd_mult:.2f}, max={max_position:.1f})")
    
    return final_position, meta


# ═══════════════════════════════════════════════════════════════════════
# TESTING
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Test the position sizing
    print("=" * 70)
    print("POSITION SIZING META-MODEL TEST")
    print("=" * 70)
    
    # Test scenarios
    scenarios = [
        {"name": "Low confidence", "prob": 0.51, "ret": 0.002, "vol": 0.01, "ratio": 1.2},
        {"name": "Medium confidence", "prob": 0.55, "ret": 0.003, "vol": 0.01, "ratio": 1.2},
        {"name": "High confidence", "prob": 0.60, "ret": 0.005, "vol": 0.01, "ratio": 1.5},
        {"name": "High conf + high vol", "prob": 0.60, "ret": 0.005, "vol": 0.02, "ratio": 1.5},
        {"name": "Very high conf + low vol + strong ratio", "prob": 0.65, "ret": 0.008, "vol": 0.008, "ratio": 1.8},
        {"name": "Low ratio (weak)", "prob": 0.55, "ret": 0.003, "vol": 0.01, "ratio": 0.85},
        {"name": "Very low ratio", "prob": 0.55, "ret": 0.003, "vol": 0.01, "ratio": 0.60},
    ]
    
    dual_ema = {
        'has_data': True,
        'short_term_ema': 1.1,
        'long_term_ema': 1.0,
        'short_term_rsi': 55,
        'long_term_rsi': 50,
    }
    
    market = {
        'high_vol_regime': False,
        'uptrend_regime': 1,
        'hmm_regime': 1,
    }
    
    print("\n" + "-" * 70)
    for s in scenarios:
        if 'high vol' in s['name'].lower():
            market['high_vol_regime'] = True
        else:
            market['high_vol_regime'] = False
            
        pos, meta = calculate_position_v2(
            prob_up=s['prob'],
            threshold=0.52,  # Ignored in new approach
            expected_return=s['ret'],
            expected_volatility=s['vol'],
            risk_free_rate=0.0001,
            dual_ema_data=dual_ema,
            past_ratio=s['ratio'],
            market_regime=market,
            running_drawdown=0.01,
            verbose=True
        )
        
        gate = meta.get('gate', 'PASSED')
        ratio_mode = meta.get('ratio_mode', 'N/A')
        stab_mode = meta.get('stability_mode', 'N/A')
        
        print(f"{s['name']:40s} | P={s['prob']:.2f} | R={s['ratio']:.1f} | "
              f"Pos={pos:.2f} | Gate={gate} | RatioMode={ratio_mode} | StabMode={stab_mode}")
        print()
    
    print("-" * 70)
    print("\nDone.")
