"""
Stable Config Ensemble - combines stable configs for probability & position sizing.
See WF_DOCS.md for architecture details.
"""

import numpy as np
from typing import Dict, List, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from wf_adaptive_scorer import AdaptiveMultiPeriodScorerV3


class StableConfigEnsemble:
    """
    Combines stable configs to estimate probability and generate position signal.
    
    Uses weighted averaging of raw probabilities where weights are based on
    each config's rolling TP/FP ratio (reliability measure).
    
    Signal range (BUY-ONLY):
      0.0 = OUT (0% equity, 100% cash)
      1.0 = HOLD (100% equity baseline)
      2.0 = MAX LONG (200% equity, max leverage)
    """
    
    def __init__(self, 
                 config_scorer: 'AdaptiveMultiPeriodScorerV3',
                 min_ratio: float = 1.05,
                 n_configs: int = 5,
                 min_samples: int = 30,
                 ratio_window: int = 10):
        """
        Args:
            config_scorer: The V3 scorer tracking config performance
            min_ratio: Minimum TP/FP ratio to be considered "stable"
            n_configs: Number of top configs to use in ensemble
            min_samples: Minimum samples before config is considered
            ratio_window: Window for TP/FP ratio calculation (default 10 = recent performance)
        """
        self.scorer = config_scorer
        self.min_ratio = min_ratio
        self.n_configs = n_configs
        self.min_samples = min_samples
        self.ratio_window = ratio_window
        
        # History for tracking
        self.signal_history: List[Dict] = []
    
    def get_stable_configs(self, current_iter: int) -> List[Dict]:
        """Get top N stable configs by rolling TP/FP ratio (using SHORT window)."""
        if current_iter < self.min_samples:
            return []
        
        # ⭐ Use short ratio_window (default 10) instead of cumulative 180
        top_configs = self.scorer.get_top_configs(current_iter, n=self.n_configs * 2, 
                                                   ratio_window=self.ratio_window)
        # ⭐ Also use ratio_window for min_samples check
        stable = [c for c in top_configs if c['ratio'] >= self.min_ratio and (c['tp'] + c['fp']) >= min(self.min_samples, self.ratio_window)]
        return stable[:self.n_configs]
    
    def calculate_ensemble_signal(self,
                                   config_probs: Dict[str, float],
                                   current_iter: int,
                                   precision_zone: str = None,
                                   net_signal: int = None,
                                   market_ratio: float = None,
                                   verbose: bool = False) -> Tuple[float, Dict]:
        """
        Calculate ensemble probability and position signal from stable configs.
        
        Uses direction-aware precision + market ratio scaling.
        
        Args:
            config_probs: Dict mapping config_name -> raw probability (0-1)
            current_iter: Current iteration number
            precision_zone: Current precision zone
            net_signal: Current net signal (n_bullish - n_bearish)
            market_ratio: Rolling UP/DOWN ratio from actual market
            verbose: Print debug info
            
        Returns:
            (signal, metadata_dict) where signal is 0.0-2.0
        """
        stable_configs = self.get_stable_configs(current_iter)
        
        # Fallback if no stable configs yet - STAY OUT OF MARKET
        if not stable_configs:
            status = 'BUILDING' if current_iter < self.min_samples else 'NO_STABLE_CONFIGS'
            return 0.0, {
                'status': status,
                'probability': 0.5,
                'weighted_precision': 0.5,
                'agreement': 0.0,
                'signal': 0.0,
                'n_stable': 0,
                'precision_zone': precision_zone,
                'net_signal': net_signal,
                'reason': f'Need {self.min_samples} iterations and stable configs with ratio >= {self.min_ratio}',
            }
        
        # Extract scores and precisions
        names = [c['name'] for c in stable_configs]
        scores = np.array([c['score'] for c in stable_configs])
        precisions = np.array([c['precision'] for c in stable_configs])
        ratios = np.array([c['ratio'] for c in stable_configs])
        
        # Get raw probs for each config
        probs = np.array([config_probs.get(name, 0.5) for name in names])
        
        # Direction-aware P(UP) calculation
        # For BULLISH prediction (prob > 0.5): P(UP) = precision
        # For BEARISH prediction (prob < 0.5): P(UP) = 1 - precision
        p_up_per_config = np.where(
            probs > 0.5,
            precisions,
            1.0 - precisions
        )
        
        # Weight by score AND ratio
        combined_weights = scores * np.sqrt(ratios)
        
        # Weighted average of direction-aware P(UP)
        if np.sum(combined_weights) > 0:
            weighted_p_up = np.sum(combined_weights * p_up_per_config) / np.sum(combined_weights)
        else:
            weighted_p_up = 0.5
        
        # Legacy calculations for logging
        if np.sum(scores) > 0:
            weighted_precision = np.sum(scores * precisions) / np.sum(scores)
        else:
            weighted_precision = np.mean(precisions) if len(precisions) > 0 else 0.5
        
        weighted_prob = np.sum(ratios * probs) / np.sum(ratios) if np.sum(ratios) > 0 else 0.5
        
        # Agreement measure
        p_up_std = np.std(p_up_per_config) if len(p_up_per_config) > 1 else 0.0
        agreement = 1.0 - min(1.0, p_up_std * 5.0)
        
        avg_stability = np.mean(scores)
        
        # Get momentum from best config
        best_config_name = stable_configs[0]['name']
        _, momentum_signal = self.scorer.get_true_momentum(best_config_name, current_iter)
        
        # === SIGNAL CALCULATION WITH RISK ADJUSTMENTS ===
        
        # 1. Base signal from direction-aware P(UP)
        base_signal = weighted_p_up * 2.0
        
        # 2. Agreement adjustment
        if agreement < 0.5:
            signal = 1.0 + (base_signal - 1.0) * (0.5 + agreement)
        else:
            signal = base_signal
        
        # 3. Stability adjustment
        if avg_stability < 0.3:
            signal = 1.0 + (signal - 1.0) * 0.3
        elif avg_stability < 0.6:
            signal = 1.0 + (signal - 1.0) * 0.6
        
        # 4. Momentum adjustment
        if momentum_signal == 'DECLINING':
            signal = 1.0 + (signal - 1.0) * 0.7
        elif momentum_signal == 'WEAKENING':
            signal = 1.0 + (signal - 1.0) * 0.85
        elif momentum_signal == 'IMPROVING':
            signal = 1.0 + (signal - 1.0) * 1.1
        elif momentum_signal == 'STRENGTHENING':
            signal = 1.0 + (signal - 1.0) * 1.05
        
        # 5. Market ratio adjustment
        mkt_adjustment = 1.0
        if market_ratio is not None and market_ratio > 0:
            mkt_factor = np.sqrt(market_ratio)
            avg_config_ratio = np.mean(ratios) if len(ratios) > 0 else 1.0
            
            if signal > 1.0:  # Bullish prediction
                if mkt_factor > 1.0 and avg_config_ratio >= 1.0:
                    mkt_adjustment = min(1.3, 0.7 + 0.3 * mkt_factor * min(avg_config_ratio, 1.5))
                elif mkt_factor < 1.0:
                    mkt_adjustment = 0.5 + 0.5 * mkt_factor
                else:
                    mkt_adjustment = 1.0
            elif signal < 1.0:  # Bearish prediction
                if mkt_factor < 1.0 and avg_config_ratio >= 1.0:
                    mkt_adjustment = 0.7 + 0.3 / max(0.5, mkt_factor)
                elif mkt_factor > 1.0:
                    mkt_adjustment = 0.5 + 0.5 / mkt_factor
                else:
                    mkt_adjustment = 1.0
            
            signal = 1.0 + (signal - 1.0) * mkt_adjustment
        
        # 6. Clamp to valid range
        signal = max(0.0, min(2.0, signal))
        
        # Build metadata
        metadata = {
            'status': 'OK',
            'probability': weighted_prob,
            'weighted_p_up': weighted_p_up,
            'weighted_precision': weighted_precision,
            'agreement': agreement,
            'avg_stability': avg_stability,
            'momentum': momentum_signal,
            'market_ratio': market_ratio,
            'mkt_adjustment': mkt_adjustment,
            'avg_config_ratio': np.mean(ratios) if len(ratios) > 0 else 1.0,
            'base_signal': base_signal,
            'signal': signal,
            'n_stable': len(stable_configs),
            'stable_configs': names,
            'scores': scores.tolist(),
            'precisions': precisions.tolist(),
            'ratios': ratios.tolist(),
            'probs': probs.tolist(),
            'p_up_per_config': p_up_per_config.tolist(),
            'combined_weights': combined_weights.tolist(),
            'precision_zone': precision_zone,
            'net_signal': net_signal,
        }
        
        # Store history
        self.signal_history.append({
            'iter': current_iter,
            'signal': signal,
            'weighted_p_up': weighted_p_up,
            'probability': weighted_prob,
            'weighted_precision': weighted_precision,
            'agreement': agreement,
            'market_ratio': market_ratio,
            'mkt_adjustment': mkt_adjustment,
            'precision_zone': precision_zone,
            'net_signal': net_signal,
        })
        
        if verbose:
            mkt_str = f", mkt={market_ratio:.2f}→×{mkt_adjustment:.2f}" if market_ratio else ""
            print(f"  [Ensemble] P(UP)={weighted_p_up:.1%}, prec={weighted_precision:.1%}, agree={agreement:.2f}, "
                  f"stab={avg_stability:.2f}, mom={momentum_signal}{mkt_str}, signal={signal:.2f}")
        
        return signal, metadata
    
    def calculate_benchmark_signal(self,
                                    probability: float,
                                    threshold: float,
                                    estimated_return: float,
                                    risk_free_rate: float,
                                    verbose: bool = False) -> Tuple[float, Dict]:
        """
        BENCHMARK SIGNAL - Gates-only, works from iteration 1.
        
        NO EMA/RSI scaling - purely gate-based signal for fair comparison.
        
        Gates (must pass BOTH to enter position):
        1. Alpha Gate: estimated_return > risk_free_rate
        2. Direction Gate: probability >= threshold
        
        If both gates pass → signal = 1.0 (100% position)
        If any gate fails → signal = 0.0 (no position)
        """
        metadata = {
            'probability': probability,
            'threshold': threshold,
            'estimated_return': estimated_return,
            'risk_free_rate': risk_free_rate,
            'alpha_excess': estimated_return - risk_free_rate,
            'gate_failed': None,
        }
        
        # GATE 1: ALPHA CHECK
        if estimated_return <= risk_free_rate:
            metadata['status'] = 'ALPHA_GATE_FAIL'
            metadata['gate_failed'] = 'alpha'
            metadata['signal'] = 0.0
            if verbose:
                print(f"  [Benchmark] ALPHA GATE FAIL: est_ret={estimated_return:.5f} <= rf={risk_free_rate:.5f}")
            return 0.0, metadata
        
        # GATE 2: DIRECTION CHECK
        if probability < threshold:
            metadata['status'] = 'DIRECTION_GATE_FAIL'
            metadata['gate_failed'] = 'direction'
            metadata['signal'] = 0.0
            if verbose:
                print(f"  [Benchmark] DIRECTION GATE FAIL: prob={probability:.3f} < thr={threshold:.3f}")
            return 0.0, metadata
        
        # BOTH GATES PASSED
        metadata['status'] = 'SIGNAL_GENERATED'
        metadata['signal'] = 1.0
        
        if verbose:
            print(f"  [Benchmark] PASSED: prob={probability:.3f}≥{threshold:.3f}, "
                  f"alpha={estimated_return-risk_free_rate:.5f} → signal=1.0")
        
        return 1.0, metadata
    
    def calculate_position_size_baseline(self,
                                          probability: float,
                                          threshold: float,
                                          estimated_return: float,
                                          risk_free_rate: float,
                                          dual_ema_data: Dict,
                                          past_ratio: float = None,
                                          verbose: bool = False) -> Tuple[float, Dict]:
        """
        BASELINE POSITION SIZING - Evidence-based with gates + Model Performance scaling.
        
        Gates (must pass ALL to enter position):
        1. Alpha Gate: estimated_return > risk_free_rate
        2. Direction Gate: probability >= threshold
        3. Ratio Gate: past_ratio >= 1.0 (skip if None/warmup)
        
        Position Scaling (after gates pass, when EMA data available):
        Based on empirical analysis from DUAL_EMA_RSI_TP_FP_ANALYSIS_REPORT.md
        
        Uses MODEL PERFORMANCE EMA/RSI (NOT traditional TA indicators!):
        These measure how well the MODEL has been performing, not market price action.
        
        RULE 1: EMA Crossover (STRONGEST signal)
           - StEMA > LtEMA: Model improving → Precision 62% → +15% position
           - StEMA <= LtEMA: Model declining → Precision 44% → -10% position
        
        RULE 2: LtEMA Quartile (CONTRARIAN effect)
           - Low LtEMA (Q1 ≤0.95): Bad performance → BETTER next predictions → +5%
           - High LtEMA (Q4 >1.47): Good performance → regression expected → -8%
        
        RULE 3: Danger Zone (CRITICAL)
           - High LtEMA (>median) AND High StRSI (>60): Precision 36%! → -25%
           - This is model overconfidence, NOT traditional overbought
        
        Multiplied: position = 1.0 × (1+crossover) × (1+quartile) × (1+danger)
        """
        ema_has_data = dual_ema_data.get('has_data', False)
        metadata = {
            'probability': probability,
            'threshold': threshold,
            'estimated_return': estimated_return,
            'risk_free_rate': risk_free_rate,
            'alpha_excess': estimated_return - risk_free_rate,
            'past_ratio': past_ratio,
            'ema_has_data': ema_has_data,
            'ema_crossover_adj': 0.0,
            'lt_ema_quartile_adj': 0.0,
            'danger_zone_adj': 0.0,
            'gate_failed': None,
        }
        
        # GATE 1: ALPHA CHECK
        if estimated_return <= risk_free_rate:
            metadata['status'] = 'ALPHA_GATE_FAIL'
            metadata['gate_failed'] = 'alpha'
            metadata['signal'] = 0.0
            if verbose:
                print(f"  [Baseline] ALPHA GATE FAIL: est_ret={estimated_return:.5f} <= rf={risk_free_rate:.5f}")
            return 0.0, metadata
        
        # GATE 2: DIRECTION CHECK
        if probability < threshold:
            metadata['status'] = 'DIRECTION_GATE_FAIL'
            metadata['gate_failed'] = 'direction'
            metadata['signal'] = 0.0
            if verbose:
                print(f"  [Baseline] DIRECTION GATE FAIL: prob={probability:.3f} < thr={threshold:.3f}")
            return 0.0, metadata
        
        # GATE 3: RATIO CHECK (skip during warmup)
        if past_ratio is not None and past_ratio < 1.0:
            metadata['status'] = 'RATIO_GATE_FAIL'
            metadata['gate_failed'] = 'ratio'
            metadata['signal'] = 0.0
            if verbose:
                print(f"  [Baseline] RATIO GATE FAIL: past_ratio={past_ratio:.2f} < 1.0")
            return 0.0, metadata
        
        # ════════════════════════════════════════════════════════════════════
        # ALL GATES PASSED - Calculate position with Performance EMA/RSI scaling
        # Based on empirical analysis from DUAL_EMA_RSI_TP_FP_ANALYSIS_REPORT.md
        # ════════════════════════════════════════════════════════════════════
        position = 1.0  # Base position = 100% equity
        
        ema_crossover_adj = 0.0
        lt_ema_quartile_adj = 0.0
        danger_zone_adj = 0.0
        
        if dual_ema_data.get('has_data', False):
            st_ema = dual_ema_data.get('short_term_ema', 1.0)
            lt_ema = dual_ema_data.get('long_term_ema', 1.0)
            st_rsi = dual_ema_data.get('short_term_rsi', 50.0)
            lt_rsi = dual_ema_data.get('long_term_rsi', 50.0)
            
            # Thresholds from empirical analysis
            LT_EMA_Q1 = 0.95    # Low EMA threshold (Q1)
            LT_EMA_Q4 = 1.474   # High EMA threshold (Q4)
            LT_EMA_MEDIAN = 1.078
            
            # ─────────────────────────────────────────────────────────────────
            # RULE 1: EMA CROSSOVER (THE STRONGEST SIGNAL)
            # StEMA > LtEMA: Precision 62.2%, Return +0.21% → BOOST (+15%)
            # StEMA <= LtEMA: Precision 43.6%, Return -0.17% → REDUCE (-10%)
            # ─────────────────────────────────────────────────────────────────
            if st_ema > lt_ema:
                ema_crossover_adj = 0.15  # +15% confidence boost
            else:
                ema_crossover_adj = -0.10  # -10% confidence reduction
            
            # ─────────────────────────────────────────────────────────────────
            # RULE 2: LtEMA QUARTILE EFFECT (CONTRARIAN)
            # Low LtEMA (Q1 ≤0.95): Precision 54.5%, Return +0.23% → BOOST (+5%)
            # High LtEMA (Q4 >1.474): Precision 45.5%, Return -0.27% → REDUCE (-8%)
            # Mean reversion: bad performance predicts BETTER next predictions
            # ─────────────────────────────────────────────────────────────────
            if lt_ema < LT_EMA_Q1:
                lt_ema_quartile_adj = 0.05  # +5% contrarian boost
            elif lt_ema > LT_EMA_Q4:
                lt_ema_quartile_adj = -0.08  # -8% reduction
            
            # ─────────────────────────────────────────────────────────────────
            # RULE 3: DANGER ZONE (High EMA + High RSI)
            # When both EMA AND RSI are elevated → Precision CRASHES to 36%
            # Average return: -0.45% (worst zone)
            # → Strong reduction (-25%)
            # ─────────────────────────────────────────────────────────────────
            if lt_ema > LT_EMA_MEDIAN and st_rsi > 60:
                danger_zone_adj = -0.25  # -25% danger zone penalty
            
            # ─────────────────────────────────────────────────────────────────
            # COMBINE ALL ADJUSTMENTS (multiplicative as per report)
            # adjustment = 1.0 * (1 + crossover) * (1 + quartile) * (1 + danger)
            # ─────────────────────────────────────────────────────────────────
            adjustment_multiplier = (
                (1.0 + ema_crossover_adj) * 
                (1.0 + lt_ema_quartile_adj) * 
                (1.0 + danger_zone_adj)
            )
            
            position = 1.0 * adjustment_multiplier
            
            # Store in metadata
            metadata['st_ema'] = st_ema
            metadata['lt_ema'] = lt_ema
            metadata['st_rsi'] = st_rsi
            metadata['lt_rsi'] = lt_rsi
            metadata['ema_crossover_adj'] = ema_crossover_adj
            metadata['lt_ema_quartile_adj'] = lt_ema_quartile_adj
            metadata['danger_zone_adj'] = danger_zone_adj
            metadata['adjustment_multiplier'] = adjustment_multiplier
            metadata['ema_crossover'] = 'BULLISH' if st_ema > lt_ema else 'BEARISH'
            metadata['lt_ema_zone'] = 'Q1_LOW' if lt_ema < LT_EMA_Q1 else ('Q4_HIGH' if lt_ema > LT_EMA_Q4 else 'NEUTRAL')
            metadata['danger_zone'] = lt_ema > LT_EMA_MEDIAN and st_rsi > 60
            metadata['status'] = 'SIGNAL_GENERATED'
        else:
            metadata['status'] = 'SIGNAL_WARMUP'
            metadata['adjustment_multiplier'] = 1.0
        
        # Clamp to valid range [0.0, 2.0]
        position = np.clip(position, 0.0, 2.0)
        
        metadata['signal'] = position
        metadata['base_position'] = 1.0
        metadata['final_position'] = position
        
        if verbose:
            if ema_has_data:
                cross_str = metadata.get('ema_crossover', '?')
                zone_str = metadata.get('lt_ema_zone', '?')
                danger_str = " DANGER!" if metadata.get('danger_zone', False) else ""
                mult_str = f", mult={metadata.get('adjustment_multiplier', 1.0):.2f}"
            else:
                cross_str = "?"
                zone_str = "WARMUP"
                danger_str = ""
                mult_str = ""
            print(f"  [Baseline] PASSED [{cross_str}/{zone_str}{danger_str}]: prob={probability:.3f}≥{threshold:.3f}, "
                  f"alpha={estimated_return-risk_free_rate:.5f}{mult_str} → pos={position:.2f}")
        
        return position, metadata
    
    def get_position_recommendation(self, signal: float) -> str:
        """Convert signal to human-readable position recommendation."""
        if signal < 0.1:
            return "OUT (0% equity - insufficient data or low confidence)"
        elif signal < 0.5:
            return "MINIMAL (10-50% equity - very cautious)"
        elif signal < 0.8:
            return "UNDERWEIGHT (50-80% equity - cautious)"
        elif signal < 1.0:
            return "SLIGHT_UNDER (80-100% equity - slightly cautious)"
        elif signal < 1.2:
            return "HOLD (100-120% equity - baseline/neutral)"
        elif signal < 1.5:
            return "OVERWEIGHT (120-150% equity - bullish)"
        elif signal < 1.8:
            return "STRONG_LONG (150-180% equity - very bullish)"
        else:
            return "MAX_LONG (180-200% equity - maximum conviction)"
