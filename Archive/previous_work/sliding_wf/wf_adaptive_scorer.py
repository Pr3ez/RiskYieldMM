"""
Adaptive Multi-Period Config Scorer V3 - selects best config based on rolling TP/FP stability.
See WF_DOCS.md for architecture details.

V3.1 ADDITIONS:
- Market regime detection using:
  * MODEL PERFORMANCE EMA/RSI (not TA indicators!) - measures config reliability
  * Actual market ratio (UP/DOWN days) - measures real market condition
  
- Model Performance EMA/RSI interpretation (from DUAL_EMA_RSI_TP_FP_ANALYSIS_REPORT.md):
  * EMA Crossover: StEMA > LtEMA → Precision 62% (model reliable)
  * LtEMA Quartile: Low LtEMA → BETTER precision (contrarian/mean reversion)
  * Danger Zone: High LtEMA + High StRSI → Precision 36% (model overconfident)

- Regime-adaptive config selection:
  * Bearish market → "very precise" configs (high precision, fewer signals)
  * Stable market → "balanced" configs (balanced TP/FP ratio)
  * Bullish market → "very stable" configs (consistent performance)
"""

import numpy as np
from typing import Dict, List, Tuple, Optional

from wf_config_history import ConfigHistoryV3


# Market regime constants
REGIME_BEARISH = 'BEARISH'
REGIME_STABLE = 'STABLE'
REGIME_BULLISH = 'BULLISH'


class AdaptiveMultiPeriodScorerV3:
    """
    V3 Adaptive Config Scorer with fixes:
    1. Normalized scores - divide by √(window) so windows are comparable
    2. True momentum - compare score NOW vs score 20 iters ago
    3. Stricter thresholds - 15% min for declining path, 25% to leave current
    4. Score floor - don't switch to weak configs
    5. Hysteresis - asymmetric thresholds for switching
    6. Multi-window scoring across range [5, 180] for robust selection
    7. Dual EMA scoring (long-term + short-term) across 161 windows [20..180]
    """
    
    # Dense window range for comprehensive evaluation
    # Sample every 5 iterations for efficiency: [5, 10, 15, ..., 180]
    DENSE_WINDOWS = list(range(5, 181, 5))  # 36 windows total
    
    # Full window range for dual EMA scoring
    # All windows from 20 to 180, step 1 = 161 windows
    FULL_WINDOWS = list(range(20, 181))  # 161 windows: [20, 21, 22, ..., 180]
    EMA_SPAN = 161  # EMA span equals number of windows
    
    # Legacy windows (for backward compatibility)
    BASE_WINDOWS = [10, 20, 40, 80, 160, 250]
    WINDOW_UNLOCK_ITERS = [10, 20, 40, 80, 160, 250]
    ADDITIONAL_WINDOW_INTERVAL = 80
    
    def __init__(self, 
                 min_samples_per_window: int = 3,
                 switch_threshold: float = 0.20,        # 20% to switch TO new config
                 leave_threshold: float = 0.25,         # 25% improvement needed to LEAVE current
                 declining_threshold: float = 0.15,     # 15% when current is declining
                 min_score_floor: float = 2.0,          # Don't switch to configs below this
                 switch_cooldown: int = 5,
                 use_dense_windows: bool = True):
        
        self.config_histories: Dict[str, ConfigHistoryV3] = {}
        self.min_samples = min_samples_per_window
        self.switch_threshold = switch_threshold
        self.leave_threshold = leave_threshold
        self.declining_threshold = declining_threshold
        self.min_score_floor = min_score_floor
        self.switch_cooldown = switch_cooldown
        self.use_dense_windows = use_dense_windows
        
        self.current_config: Optional[str] = None
        self.last_switch_iter: int = -999
        self.switch_history: List[Tuple[int, str, str, str]] = []
        
        # Dual EMA history for RSI calculation
        self.dual_ema_history: Dict[int, Dict] = {}
        self.rsi_lookback: int = 14  # RSI lookback period
        
        # ⭐ NEW: Track ACTUAL Top10 ratios used each iteration for LtEMA/StEMA
        self.actual_ratio_history: List[Tuple[int, float]] = []  # [(iter, avg_ratio), ...]
        self.lt_ema_span: int = 60   # Long-term EMA span (slow, ~60 iterations)
        self.st_ema_span: int = 14   # Short-term EMA span (fast, ~14 iterations)

    def get_state(self) -> Dict:
        """Serialize scorer state for checkpointing."""
        return {
            'config_histories': {
                name: hist.outcomes[:] for name, hist in self.config_histories.items()
            },
            'dual_ema_history': {k: v.copy() for k, v in self.dual_ema_history.items()},
            'current_config': self.current_config,
            'last_switch_iter': self.last_switch_iter,
            'switch_history': list(self.switch_history),
            'rsi_lookback': self.rsi_lookback,
        }

    def restore_state(self, state: Dict, rebase_to_zero: bool = False):
        """Restore scorer state; optionally rebase iteration indices to start at 0.

        rebase_to_zero is used for features-only resume so past EMA/RSI values
        are available immediately while TP/FP display counters are reset.
        """
        if not state:
            return

        config_histories = state.get('config_histories', {})
        dual_ema_history = state.get('dual_ema_history', {})

        # Determine shift to rebase historical iterations to start at 0
        shift = 0
        if rebase_to_zero:
            max_iter_hist = 0
            for outcomes in config_histories.values():
                if outcomes:
                    max_iter_hist = max(max_iter_hist, max(it for it, *_ in outcomes))
            if dual_ema_history:
                max_iter_hist = max(max_iter_hist, max(dual_ema_history.keys()))
            shift = max_iter_hist

        # Rebuild config histories
        self.config_histories = {}
        for name, outcomes in config_histories.items():
            rebased = [(it - shift, tp, fp, tn, fn) for (it, tp, fp, tn, fn) in outcomes]
            self.config_histories[name] = ConfigHistoryV3(outcomes=rebased)

        # Restore dual EMA history (shift keys if rebasing)
        self.dual_ema_history = {}
        for it, rec in dual_ema_history.items():
            new_it = it - shift
            self.dual_ema_history[new_it] = rec.copy()
            self.dual_ema_history[new_it]['iter'] = new_it

        # Other scalar state
        self.current_config = state.get('current_config')
        self.last_switch_iter = state.get('last_switch_iter', -999) - shift
        self.switch_history = [
            (it - shift, old, new, reason) for (it, old, new, reason) in state.get('switch_history', [])
        ]
        self.rsi_lookback = state.get('rsi_lookback', self.rsi_lookback)
    
    def ensure_config(self, config_name: str):
        """Ensure config history exists"""
        if config_name not in self.config_histories:
            self.config_histories[config_name] = ConfigHistoryV3()
    
    def get_dense_windows(self, current_iter: int) -> List[int]:
        """Get dense windows [5, 10, 15, ..., min(180, current_iter)]"""
        max_window = min(180, current_iter - 1)
        if max_window < 5:
            return []
        return [w for w in self.DENSE_WINDOWS if w <= max_window]
    
    def get_full_windows(self, current_iter: int) -> List[int]:
        """Get full windows [20, 21, 22, ..., min(180, current_iter)]"""
        max_window = min(180, current_iter - 1)
        if max_window < 20:
            return []
        return [w for w in self.FULL_WINDOWS if w <= max_window]
    
    def get_full_window_stats(self, config_name: str, current_iter: int) -> Dict[int, Dict]:
        """Get TP/FP/ratio/stability for each of 161 windows [20..180]."""
        windows = self.get_full_windows(current_iter)
        history = self.config_histories.get(config_name)
        
        if not history or not windows:
            return {}
        
        stats = {}
        for window in windows:
            tp, fp, sample_count = history.get_rolling_stats(current_iter, window)
            ratio = tp / max(fp, 1)
            stability = self.calculate_normalized_stability(tp, fp, sample_count, window)
            stats[window] = {
                'tp': tp,
                'fp': fp,
                'ratio': ratio,
                'stability': stability,
                'n': sample_count
            }
        return stats

    def get_active_windows(self, current_iter: int) -> List[int]:
        windows = []
        for window, unlock_iter in zip(self.BASE_WINDOWS, self.WINDOW_UNLOCK_ITERS):
            if current_iter >= unlock_iter:
                windows.append(window)
        if current_iter > 250:
            extra_windows = (current_iter - 250) // self.ADDITIONAL_WINDOW_INTERVAL
            for i in range(1, extra_windows + 1):
                new_window = 250 + i * self.ADDITIONAL_WINDOW_INTERVAL
                if new_window <= current_iter:
                    windows.append(new_window)
        return sorted(windows)
    
    def update(self, config_name: str, iteration: int, tp: int, fp: int, tn: int, fn: int):
        self.ensure_config(config_name)
        self.config_histories[config_name].add_outcome(iteration, tp, fp, tn, fn)
    
    def calculate_normalized_stability(self, tp: int, fp: int, sample_count: int, window_size: int) -> float:
        """Normalized stability: ratio × √(TP) / √(window)"""
        if sample_count < self.min_samples or tp < self.min_samples:
            return 0.0
        ratio = tp / max(fp, 1)
        raw_score = ratio * np.sqrt(tp)
        return raw_score / np.sqrt(window_size)
    
    def get_rolling_stability_scores(self, config_name: str, current_iter: int) -> Dict[int, float]:
        """Get NORMALIZED stability score for each active window"""
        windows = self.get_active_windows(current_iter)
        history = self.config_histories.get(config_name)
        if not history:
            return {w: 0.0 for w in windows}
        
        scores = {}
        for window in windows:
            tp, fp, sample_count = history.get_rolling_stats(current_iter, window)
            scores[window] = self.calculate_normalized_stability(tp, fp, sample_count, window)
        return scores
    
    def get_dense_window_scores(self, config_name: str, current_iter: int) -> Dict[str, any]:
        """Calculate scores across ALL windows in range [5, 180]."""
        windows = self.get_dense_windows(current_iter)
        history = self.config_histories.get(config_name)
        
        if not history or not windows:
            return {
                'window_scores': {},
                'best_window': None,
                'best_score': 0.0,
                'avg_score': 0.0,
                'consistency': 0.0,
                'tp_fp_by_window': {},
                'n_profitable_windows': 0,
                'n_valid_windows': 0,
            }
        
        window_scores = {}
        tp_fp_by_window = {}
        profitable_count = 0
        valid_scores = []
        
        for window in windows:
            tp, fp, sample_count = history.get_rolling_stats(current_iter, window)
            
            ratio = tp / max(fp, 1)
            tp_fp_by_window[window] = {'tp': tp, 'fp': fp, 'ratio': ratio, 'n': sample_count}
            
            norm_score = self.calculate_normalized_stability(tp, fp, sample_count, window)
            window_scores[window] = norm_score
            
            if sample_count >= self.min_samples:
                if ratio > 1.0:
                    profitable_count += 1
                if norm_score > 0:
                    valid_scores.append(norm_score)
        
        if window_scores:
            best_window = max(window_scores, key=lambda w: window_scores[w])
            best_score = window_scores[best_window]
        else:
            best_window = None
            best_score = 0.0
        
        avg_score = np.mean(valid_scores) if valid_scores else 0.0
        n_valid = len(valid_scores)
        consistency = profitable_count / len(windows) if windows else 0.0
        
        return {
            'window_scores': window_scores,
            'best_window': best_window,
            'best_score': best_score,
            'avg_score': avg_score,
            'consistency': consistency,
            'tp_fp_by_window': tp_fp_by_window,
            'n_profitable_windows': profitable_count,
            'n_valid_windows': n_valid,
        }
    
    def get_multi_window_composite_score(self, config_name: str, current_iter: int) -> Dict:
        """Calculate composite score using dense windows [5, 180]."""
        dense_data = self.get_dense_window_scores(config_name, current_iter)
        
        avg_score = dense_data['avg_score']
        consistency = dense_data['consistency']
        best_window = dense_data['best_window']
        best_score = dense_data['best_score']
        
        momentum, signal = self.get_true_momentum(config_name, current_iter)
        
        consistency_bonus = max(0, (consistency - 0.5) * 0.5)
        
        if signal == 'DECLINING':
            momentum_mult = 0.7
        elif signal == 'WEAKENING':
            momentum_mult = 0.9
        elif signal == 'IMPROVING':
            momentum_mult = 1.1
        elif signal == 'STRENGTHENING':
            momentum_mult = 1.05
        else:
            momentum_mult = 1.0
        
        final_score = avg_score * (1 + consistency_bonus) * momentum_mult
        
        history = self.config_histories.get(config_name)
        total_tp, total_fp = history.get_total_tp_fp() if history else (0, 0)
        
        return {
            'config': config_name,
            'dense_data': dense_data,
            'avg_score': avg_score,
            'consistency': consistency,
            'consistency_bonus': consistency_bonus,
            'best_window': best_window,
            'best_score': best_score,
            'momentum': momentum,
            'momentum_signal': signal,
            'momentum_mult': momentum_mult,
            'final_score': final_score,
            'total_tp': total_tp,
            'total_fp': total_fp,
            'n_profitable_windows': dense_data['n_profitable_windows'],
            'n_valid_windows': dense_data['n_valid_windows'],
        }

    def select_best_per_window(self, current_iter: int) -> Dict[int, Dict]:
        """For each window [20..180], select the best config and return its ratio.
        
        ⭐ ALIGNED with get_top_configs(): Uses same ranking formula (score × √ratio)
        to ensure LtEMA/StEMA reflect performance of configs we actually select.
        """
        windows = self.get_full_windows(current_iter)
        if not windows or not self.config_histories:
            return {}
        
        # Get composite scores for all configs (same as get_top_configs uses)
        all_config_composite = {}
        for cfg_name in self.config_histories:
            if self.use_dense_windows and current_iter >= 10:
                all_config_composite[cfg_name] = self.get_multi_window_composite_score(cfg_name, current_iter)
            else:
                all_config_composite[cfg_name] = self.get_composite_score(cfg_name, current_iter)
        
        # Get per-window stats for ratio/stability
        all_config_stats = {}
        for cfg_name in self.config_histories:
            all_config_stats[cfg_name] = self.get_full_window_stats(cfg_name, current_iter)
        
        best_per_window = {}
        for window in windows:
            best_cfg = None
            best_combined_score = -1.0
            best_ratio = 0.0
            best_stability = 0.0
            best_base_score = 0.0
            
            for cfg_name, stats in all_config_stats.items():
                if window not in stats:
                    continue
                ws = stats[window]
                ratio = ws['ratio']
                stability = ws['stability']
                
                # ⭐ Use same formula as get_top_configs: score × √ratio
                base_score = all_config_composite.get(cfg_name, {}).get('final_score', 0.0)
                combined_score = base_score * np.sqrt(max(ratio, 0.01))
                
                if combined_score > best_combined_score:
                    best_combined_score = combined_score
                    best_cfg = cfg_name
                    best_ratio = ratio
                    best_stability = stability
                    best_base_score = base_score
            
            if best_cfg is not None:
                best_per_window[window] = {
                    'config': best_cfg,
                    'ratio': best_ratio,
                    'stability': best_stability,
                    'score': best_combined_score,
                    'base_score': best_base_score,
                }
        
        return best_per_window

    def calculate_dual_ema_scores(self, current_iter: int) -> Dict:
        """Calculate dual EMA scores from best-per-window ratios."""
        best_per_window = self.select_best_per_window(current_iter)
        
        if not best_per_window:
            return {
                'long_term_ema': 1.0,
                'short_term_ema': 1.0,
                'long_term_stability': 0.0,
                'short_term_stability': 0.0,
                'n_windows': 0,
                'best_per_window': {},
            }
        
        windows_sorted = sorted(best_per_window.keys())
        n_windows = len(windows_sorted)
        
        if n_windows == 0:
            return {
                'long_term_ema': 1.0,
                'short_term_ema': 1.0,
                'long_term_stability': 0.0,
                'short_term_stability': 0.0,
                'n_windows': 0,
                'best_per_window': best_per_window,
            }
        
        alpha = 2.0 / (self.EMA_SPAN + 1)
        
        # EMA_LONG: Process 20→180 (long windows get most weight)
        ema_long_ratio = best_per_window[windows_sorted[0]]['ratio']
        ema_long_stab = best_per_window[windows_sorted[0]]['stability']
        
        for w in windows_sorted[1:]:
            ema_long_ratio = alpha * best_per_window[w]['ratio'] + (1 - alpha) * ema_long_ratio
            ema_long_stab = alpha * best_per_window[w]['stability'] + (1 - alpha) * ema_long_stab
        
        # EMA_SHORT: Process 180→20 (short windows get most weight)
        windows_reversed = list(reversed(windows_sorted))
        ema_short_ratio = best_per_window[windows_reversed[0]]['ratio']
        ema_short_stab = best_per_window[windows_reversed[0]]['stability']
        
        for w in windows_reversed[1:]:
            ema_short_ratio = alpha * best_per_window[w]['ratio'] + (1 - alpha) * ema_short_ratio
            ema_short_stab = alpha * best_per_window[w]['stability'] + (1 - alpha) * ema_short_stab
        
        return {
            'long_term_ema': ema_long_ratio,
            'short_term_ema': ema_short_ratio,
            'long_term_stability': ema_long_stab,
            'short_term_stability': ema_short_stab,
            'n_windows': n_windows,
            'best_per_window': best_per_window,
        }

    def get_dual_ema_composite_score(
        self, 
        current_iter: int, 
        long_term_weight: float = 0.6,
        short_term_weight: float = 0.4
    ) -> Dict:
        """Calculate composite score from dual EMAs for config selection."""
        MIN_EMA_WINDOWS = 161
        
        dual_ema = self.calculate_dual_ema_scores(current_iter)
        
        if dual_ema['n_windows'] < MIN_EMA_WINDOWS:
            return {
                'composite_score': 0.0,
                'long_term_ema': 0.0,
                'short_term_ema': 0.0,
                'long_term_stability': 0.0,
                'short_term_stability': 0.0,
                'n_windows': dual_ema['n_windows'],
                'has_data': False,
            }
        
        composite_ratio = (
            long_term_weight * dual_ema['long_term_ema'] + 
            short_term_weight * dual_ema['short_term_ema']
        )
        
        composite_stability = (
            long_term_weight * dual_ema['long_term_stability'] + 
            short_term_weight * dual_ema['short_term_stability']
        )
        
        composite_score = composite_ratio * (1.0 + composite_stability * 0.1)
        
        if dual_ema['long_term_ema'] > 0.1:
            trend_ratio = dual_ema['short_term_ema'] / dual_ema['long_term_ema']
        else:
            trend_ratio = 1.0
        
        if trend_ratio > 1.2:
            trend = 'IMPROVING'
            composite_score *= 1.05
        elif trend_ratio > 1.0:
            trend = 'STABLE_UP'
        elif trend_ratio > 0.8:
            trend = 'STABLE_DOWN'
        else:
            trend = 'DECLINING'
            composite_score *= 0.95
        
        return {
            'composite_score': composite_score,
            'composite_ratio': composite_ratio,
            'composite_stability': composite_stability,
            'long_term_ema': dual_ema['long_term_ema'],
            'short_term_ema': dual_ema['short_term_ema'],
            'long_term_stability': dual_ema['long_term_stability'],
            'short_term_stability': dual_ema['short_term_stability'],
            'trend_ratio': trend_ratio,
            'trend': trend,
            'n_windows': dual_ema['n_windows'],
            'has_data': True,
        }

    def _calculate_rsi(self, values: List[float], lookback: int = 14) -> float:
        """Calculate RSI (Relative Strength Index) from a series of values."""
        if len(values) < lookback + 1:
            return 50.0
        
        changes = [values[i] - values[i-1] for i in range(1, len(values))]
        recent_changes = changes[-(lookback):]
        
        gains = [c if c > 0 else 0 for c in recent_changes]
        losses = [-c if c < 0 else 0 for c in recent_changes]
        
        avg_gain = sum(gains) / lookback
        avg_loss = sum(losses) / lookback
        
        if avg_loss == 0:
            return 100.0 if avg_gain > 0 else 50.0
        
        rs = avg_gain / avg_loss
        rsi = 100.0 - (100.0 / (1.0 + rs))
        
        return rsi

    def update_dual_ema_history(self, current_iter: int) -> Dict:
        """Calculate dual EMAs for current iteration, store in history, and compute RSI.
        
        Returns values as soon as available (expanding window) for display purposes.
        The 'has_data' flag indicates if we have enough windows for reliable signals.
        """
        MIN_EMA_WINDOWS_FOR_SIGNAL = 161  # Full reliability for signal generation
        MIN_EMA_WINDOWS_FOR_DISPLAY = 5   # Minimum for showing expanding values
        
        dual_ema = self.calculate_dual_ema_scores(current_iter)
        
        # Return early display values even with few windows
        if dual_ema['n_windows'] < MIN_EMA_WINDOWS_FOR_DISPLAY:
            return {
                'iter': current_iter,
                'has_data': False,
                'long_term_ema': 0.0,
                'short_term_ema': 0.0,
                'long_term_rsi': 50.0,
                'short_term_rsi': 50.0,
                'n_windows': dual_ema['n_windows'],
                'min_required': MIN_EMA_WINDOWS_FOR_SIGNAL,
            }
        
        # Store in history for RSI calculation
        self.dual_ema_history[current_iter] = {
            'long_term_ema': dual_ema['long_term_ema'],
            'short_term_ema': dual_ema['short_term_ema'],
            'long_term_stability': dual_ema['long_term_stability'],
            'short_term_stability': dual_ema['short_term_stability'],
            'n_windows': dual_ema['n_windows'],
        }
        
        sorted_iters = sorted(self.dual_ema_history.keys())
        
        long_term_series = [self.dual_ema_history[it]['long_term_ema'] for it in sorted_iters]
        short_term_series = [self.dual_ema_history[it]['short_term_ema'] for it in sorted_iters]
        
        long_term_rsi = self._calculate_rsi(long_term_series, self.rsi_lookback)
        short_term_rsi = self._calculate_rsi(short_term_series, self.rsi_lookback)
        
        self.dual_ema_history[current_iter]['long_term_rsi'] = long_term_rsi
        self.dual_ema_history[current_iter]['short_term_rsi'] = short_term_rsi
        
        def interpret_rsi(rsi: float) -> str:
            if rsi >= 70:
                return 'OVERBOUGHT'
            elif rsi >= 60:
                return 'BULLISH'
            elif rsi <= 30:
                return 'OVERSOLD'
            elif rsi <= 40:
                return 'BEARISH'
            else:
                return 'NEUTRAL'
        
        long_term_signal = interpret_rsi(long_term_rsi)
        short_term_signal = interpret_rsi(short_term_rsi)
        
        # has_data=True only when we have enough for reliable signals
        has_reliable_data = dual_ema['n_windows'] >= MIN_EMA_WINDOWS_FOR_SIGNAL
        
        return {
            'iter': current_iter,
            'has_data': has_reliable_data,
            'long_term_ema': dual_ema['long_term_ema'],
            'short_term_ema': dual_ema['short_term_ema'],
            'long_term_stability': dual_ema['long_term_stability'],
            'short_term_stability': dual_ema['short_term_stability'],
            'long_term_rsi': long_term_rsi,
            'short_term_rsi': short_term_rsi,
            'long_term_signal': long_term_signal,
            'short_term_signal': short_term_signal,
            'history_length': len(sorted_iters),
            'n_windows': dual_ema['n_windows'],
        }

    # ════════════════════════════════════════════════════════════════════════════
    # ⭐ Track STRATEGY's rolling ratio and compute LtEMA/StEMA from it
    # ════════════════════════════════════════════════════════════════════════════
    
    def update_strategy_ratio_ema(self, current_iter: int, rolling_ratio: float) -> Dict:
        """
        Update LtEMA/StEMA based on the STRATEGY's rolling TP/FP ratio.
        This is the ratio visible in the log's "Ratio" column.
        
        Args:
            current_iter: Current iteration number
            rolling_ratio: The strategy's rolling TP/FP ratio (e.g., 0.91 from 39/43)
            
        Returns:
            Dict with LtEMA, StEMA, LtRSI, StRSI based on strategy ratio history
        """
        # Store in history
        self.actual_ratio_history.append((current_iter, rolling_ratio))
        
        # Not enough data yet - need at least 5 points
        if len(self.actual_ratio_history) < 5:
            return {
                'has_data': False,
                'long_term_ema': rolling_ratio,
                'short_term_ema': rolling_ratio,
                'long_term_rsi': 50.0,
                'short_term_rsi': 50.0,
                'current_ratio': rolling_ratio,
                'n_samples': len(self.actual_ratio_history),
            }
        
        # Extract ratio series
        ratio_series = [r for _, r in self.actual_ratio_history]
        
        # Calculate EMAs
        lt_alpha = 2.0 / (self.lt_ema_span + 1)  # ~0.033 for span=60
        st_alpha = 2.0 / (self.st_ema_span + 1)  # ~0.133 for span=14
        
        # Long-term EMA (slow)
        lt_ema = ratio_series[0]
        for r in ratio_series[1:]:
            lt_ema = lt_alpha * r + (1 - lt_alpha) * lt_ema
        
        # Short-term EMA (fast)
        st_ema = ratio_series[0]
        for r in ratio_series[1:]:
            st_ema = st_alpha * r + (1 - st_alpha) * st_ema
        
        # Calculate RSI from ratio series
        lt_rsi = self._calculate_rsi(ratio_series, min(self.rsi_lookback, len(ratio_series) - 1))
        st_rsi = self._calculate_rsi(ratio_series, min(7, len(ratio_series) - 1))  # Shorter RSI for StEMA
        
        return {
            'has_data': len(self.actual_ratio_history) >= 10,
            'long_term_ema': lt_ema,
            'short_term_ema': st_ema,
            'long_term_rsi': lt_rsi,
            'short_term_rsi': st_rsi,
            'current_ratio': rolling_ratio,
            'n_samples': len(self.actual_ratio_history),
        }
    
    def record_actual_top10_ratios(self, current_iter: int, top10_configs: List[Dict], 
                                    short_window: int = 10) -> Dict:
        """
        Record the ACTUAL ratios of Top10 configs we're using this iteration.
        Calculate LtEMA/StEMA from these real ratios (not theoretical best-per-window).
        
        ⭐ KEY CHANGE: Uses SHORT-TERM (last N iters) ratio instead of cumulative ratio
        This makes EMAs more responsive to recent config performance.
        
        Args:
            current_iter: Current iteration number
            top10_configs: List of Top10 config dicts with 'ratio' field
            short_window: Window for short-term ratio calculation (default 10)
            
        Returns:
            Dict with actual LtEMA, StEMA, LtRSI, StRSI based on real config ratios
        """
        # ⭐ ONLY record when we have actual configs - don't pollute with 1.0 defaults
        if not top10_configs:
            # No configs yet - return defaults, don't record
            if len(self.actual_ratio_history) > 0:
                # Return last known EMA values
                ratio_series = [r for _, r in self.actual_ratio_history]
                lt_alpha = 2.0 / (self.lt_ema_span + 1)
                st_alpha = 2.0 / (self.st_ema_span + 1)
                lt_ema = ratio_series[0]
                st_ema = ratio_series[0]
                for r in ratio_series[1:]:
                    lt_ema = lt_alpha * r + (1 - lt_alpha) * lt_ema
                    st_ema = st_alpha * r + (1 - st_alpha) * st_ema
                return {
                    'has_data': False,
                    'long_term_ema': lt_ema,
                    'short_term_ema': st_ema,
                    'long_term_rsi': 50.0,
                    'short_term_rsi': 50.0,
                    'avg_ratio': 1.0,
                    'max_ratio': 1.0,
                    'min_ratio': 1.0,
                    'n_samples': len(self.actual_ratio_history),
                }
            else:
                return {
                    'has_data': False,
                    'long_term_ema': 1.0,
                    'short_term_ema': 1.0,
                    'long_term_rsi': 50.0,
                    'short_term_rsi': 50.0,
                    'avg_ratio': 1.0,
                    'max_ratio': 1.0,
                    'min_ratio': 1.0,
                    'n_samples': 0,
                }
        
        # ⭐ Calculate SHORT-TERM ratio for each config (last N iterations, not cumulative)
        short_term_ratios = []
        for cfg in top10_configs:
            cfg_name = cfg.get('name', '')
            # Get short-term TP/FP from config history
            history = self.config_histories.get(cfg_name)
            if history:
                st_tp, st_fp, _ = history.get_rolling_stats(current_iter, short_window)
                if st_fp > 0:
                    st_ratio = st_tp / st_fp
                elif st_tp > 0:
                    st_ratio = 5.0  # Cap at 5.0 for all-TP
                else:
                    st_ratio = 1.0  # No data in short window
            else:
                # Fallback to cumulative ratio if history unavailable
                st_ratio = cfg.get('ratio', 1.0)
            short_term_ratios.append(st_ratio)
        
        # Calculate average short-term ratio of Top10 configs this iteration
        avg_ratio = sum(short_term_ratios) / len(short_term_ratios)
        max_ratio = max(short_term_ratios)
        min_ratio = min(short_term_ratios)
        
        # Store in history (only when we have real data)
        self.actual_ratio_history.append((current_iter, avg_ratio))
        
        # Not enough data yet
        if len(self.actual_ratio_history) < 5:
            return {
                'has_data': False,
                'long_term_ema': avg_ratio,
                'short_term_ema': avg_ratio,
                'long_term_rsi': 50.0,
                'short_term_rsi': 50.0,
                'avg_ratio': avg_ratio,
                'max_ratio': max_ratio,
                'min_ratio': min_ratio,
                'n_samples': len(self.actual_ratio_history),
            }
        
        # Extract ratio series
        ratio_series = [r for _, r in self.actual_ratio_history]
        
        # Calculate EMAs
        lt_alpha = 2.0 / (self.lt_ema_span + 1)  # ~0.033 for span=60
        st_alpha = 2.0 / (self.st_ema_span + 1)  # ~0.133 for span=14
        
        # Long-term EMA (slow)
        lt_ema = ratio_series[0]
        for r in ratio_series[1:]:
            lt_ema = lt_alpha * r + (1 - lt_alpha) * lt_ema
        
        # Short-term EMA (fast)
        st_ema = ratio_series[0]
        for r in ratio_series[1:]:
            st_ema = st_alpha * r + (1 - st_alpha) * st_ema
        
        # Calculate RSI from ratio series
        lt_rsi = self._calculate_rsi(ratio_series, min(self.rsi_lookback, len(ratio_series) - 1))
        st_rsi = self._calculate_rsi(ratio_series, min(7, len(ratio_series) - 1))  # Shorter RSI for StEMA
        
        return {
            'has_data': len(self.actual_ratio_history) >= 10,
            'long_term_ema': lt_ema,
            'short_term_ema': st_ema,
            'long_term_rsi': lt_rsi,
            'short_term_rsi': st_rsi,
            'avg_ratio': avg_ratio,
            'max_ratio': max_ratio,
            'min_ratio': min_ratio,
            'n_samples': len(self.actual_ratio_history),
        }

    def get_dual_ema_analysis(self, current_iter: int) -> Dict:
        """Get comprehensive dual EMA analysis with RSI momentum indicators."""
        if current_iter not in self.dual_ema_history:
            self.update_dual_ema_history(current_iter)
        
        sorted_iters = sorted(self.dual_ema_history.keys())
        
        history_records = []
        for it in sorted_iters:
            record = {'iter': it}
            record.update(self.dual_ema_history[it])
            history_records.append(record)
        
        current = self.dual_ema_history.get(current_iter, {})
        
        if len(sorted_iters) >= 2:
            long_emas = [self.dual_ema_history[it]['long_term_ema'] for it in sorted_iters]
            short_emas = [self.dual_ema_history[it]['short_term_ema'] for it in sorted_iters]
            
            summary = {
                'long_term_ema_mean': np.mean(long_emas),
                'long_term_ema_std': np.std(long_emas),
                'long_term_ema_min': min(long_emas),
                'long_term_ema_max': max(long_emas),
                'short_term_ema_mean': np.mean(short_emas),
                'short_term_ema_std': np.std(short_emas),
                'short_term_ema_min': min(short_emas),
                'short_term_ema_max': max(short_emas),
            }
        else:
            summary = {}
        
        return {
            'current': current,
            'history': history_records,
            'summary': summary,
            'n_records': len(sorted_iters),
        }

    def get_true_momentum(self, config_name: str, current_iter: int) -> Tuple[float, str]:
        """Calculate TRUE momentum by comparing current vs past performance."""
        history = self.config_histories.get(config_name)

        
        current_score = history.get_score_at_iter(current_iter, lookback=10)
        past_score = history.get_score_at_iter(current_iter - 20, lookback=10)
        
        if past_score < 0.01 or current_score < 0.01:
            # Low scores = no momentum data, just STABLE
            return 1.0, 'STABLE'
        
        momentum = current_score / past_score
        
        if momentum < 0.5:
            signal = 'DECLINING'
        elif momentum < 0.8:
            signal = 'WEAKENING'
        elif momentum > 1.5:
            signal = 'IMPROVING'
        elif momentum > 1.2:
            signal = 'STRENGTHENING'
        else:
            signal = 'STABLE'
        
        return momentum, signal
    
    def get_composite_score(self, config_name: str, current_iter: int) -> Dict:
        """Calculate composite score with normalized windows and true momentum"""
        scores = self.get_rolling_stability_scores(config_name, current_iter)
        windows = self.get_active_windows(current_iter)
        
        valid_scores = [s for s in scores.values() if s > 0]
        avg_stability = np.mean(valid_scores) if valid_scores else 0.0
        
        momentum, signal = self.get_true_momentum(config_name, current_iter)
        
        final_score = avg_stability
        
        if signal == 'DECLINING':
            final_score *= 0.7
        elif signal == 'WEAKENING':
            final_score *= 0.9
        elif signal == 'IMPROVING':
            final_score *= 1.1
        elif signal == 'STRENGTHENING':
            final_score *= 1.05
        
        history = self.config_histories.get(config_name)
        total_tp, total_fp = history.get_total_tp_fp() if history else (0, 0)
        
        return {
            'config': config_name,
            'window_scores': scores,
            'avg_stability': avg_stability,
            'momentum': momentum,
            'momentum_signal': signal,
            'final_score': final_score,
            'active_windows': windows,
            'total_tp': total_tp,
            'total_fp': total_fp,
        }
    
    def get_rolling_tp_fp(self, config_name: str, current_iter: int, window: int = 180) -> Tuple[int, int]:
        """Get TP/FP for last N iterations (for display)"""
        history = self.config_histories.get(config_name)
        if not history:
            return 0, 0
        tp, fp, _ = history.get_rolling_stats(current_iter, window)
        return tp, fp
    
    def select_best_config(self, current_iter: int, use_dual_ema: bool = False) -> Tuple[str, Dict]:
        """Select best config with hysteresis and score floor protection."""
        if not self.config_histories:
            return None, {'decision': 'NO_DATA'}
        
        if use_dual_ema and current_iter >= 30:
            dual_ema_score = self.get_dual_ema_composite_score(current_iter)
            
            if not dual_ema_score['has_data']:
                all_scores = {cfg: self.get_composite_score(cfg, current_iter) 
                              for cfg in self.config_histories}
            else:
                best_per_window = self.calculate_dual_ema_scores(current_iter).get('best_per_window', {})
                
                config_wins = {}
                for w, data in best_per_window.items():
                    cfg = data['config']
                    config_wins[cfg] = config_wins.get(cfg, 0) + 1
                
                all_scores = {}
                for cfg in self.config_histories:
                    cfg_data = self.get_composite_score(cfg, current_iter)
                    win_fraction = config_wins.get(cfg, 0) / max(len(best_per_window), 1)
                    cfg_data['window_wins'] = config_wins.get(cfg, 0)
                    cfg_data['win_fraction'] = win_fraction
                    cfg_data['final_score'] = cfg_data['final_score'] * (1.0 + win_fraction * 0.5)
                    all_scores[cfg] = cfg_data
                
                best_name = max(all_scores, key=lambda x: all_scores[x]['final_score'])
                all_scores[best_name]['dual_ema'] = dual_ema_score
                
        elif self.use_dense_windows and current_iter >= 10:
            all_scores = {cfg: self.get_multi_window_composite_score(cfg, current_iter) 
                          for cfg in self.config_histories}
        else:
            all_scores = {cfg: self.get_composite_score(cfg, current_iter) 
                          for cfg in self.config_histories}
        
        best_name = max(all_scores, key=lambda x: all_scores[x]['final_score'])
        best_data = all_scores[best_name]
        best_score = best_data['final_score']
        
        iters_since_switch = current_iter - self.last_switch_iter
        in_cooldown = iters_since_switch < self.switch_cooldown
        
        if self.current_config is None:
            self.current_config = best_name
            self.last_switch_iter = current_iter
            return best_name, {'decision': 'INITIAL_SELECT', 'config': best_name, 'all_scores': all_scores}
        
        if best_name == self.current_config:
            return best_name, {'decision': 'CONTINUE', 'config': best_name, 'all_scores': all_scores}
        
        current_data = all_scores.get(self.current_config, {'final_score': 0, 'momentum_signal': 'STABLE'})
        current_score = current_data.get('final_score', 0)
        current_signal = current_data.get('momentum_signal', 'STABLE')
        
        improvement = (best_score - current_score) / max(current_score, 0.001)
        current_declining = current_signal in ['DECLINING', 'WEAKENING']
        
        should_switch = False
        reason = ""
        
        if in_cooldown:
            reason = f"COOLDOWN ({self.switch_cooldown - iters_since_switch} left)"
        elif best_score < self.min_score_floor:
            reason = f"SCORE_FLOOR (best={best_score:.1f} < {self.min_score_floor})"
        elif improvement >= self.leave_threshold:
            should_switch = True
            reason = f"STRONG +{improvement:.0%}"
        elif current_declining and improvement >= self.declining_threshold:
            should_switch = True
            reason = f"CURRENT_{current_signal[:4]} +{improvement:.0%}"
        else:
            reason = f"HOLD (+{improvement:.0%} < thr)"
        
        if should_switch:
            old_config = self.current_config
            self.current_config = best_name
            self.last_switch_iter = current_iter
            self.switch_history.append((current_iter, old_config, best_name, reason))
            return best_name, {'decision': 'SWITCH', 'from': old_config, 'to': best_name, 
                              'reason': reason, 'improvement': improvement, 'all_scores': all_scores}
        else:
            return self.current_config, {'decision': 'HOLD', 'current': self.current_config,
                                         'candidate': best_name, 'reason': reason, 
                                         'improvement': improvement, 'all_scores': all_scores}
    
    def get_top_configs(self, current_iter: int, n: int = 5, use_dual_ema: bool = False, 
                        ratio_window: int = 10) -> List[Dict]:
        """
        Get top N configs by score for display.
        
        Args:
            current_iter: Current iteration
            n: Number of configs to return
            use_dual_ema: Whether to use dual EMA scoring
            ratio_window: Window for TP/FP ratio calculation (default 10 = recent performance)
        """
        all_scores = []
        
        dual_ema_data = None
        config_wins = {}
        if use_dual_ema and current_iter >= 30:
            dual_ema_data = self.calculate_dual_ema_scores(current_iter)
            best_per_window = dual_ema_data.get('best_per_window', {})
            for w, data in best_per_window.items():
                cfg = data['config']
                config_wins[cfg] = config_wins.get(cfg, 0) + 1
        
        for cfg in self.config_histories:
            if use_dual_ema and current_iter >= 30:
                data = self.get_composite_score(cfg, current_iter)
                win_count = config_wins.get(cfg, 0)
                win_fraction = win_count / max(len(dual_ema_data.get('best_per_window', {})), 1)
                best_window = None
                consistency = None
            elif self.use_dense_windows and current_iter >= 10:
                data = self.get_multi_window_composite_score(cfg, current_iter)
                best_window = data.get('best_window')
                consistency = data.get('consistency', 0.0)
                win_count = None
                win_fraction = None
            else:
                data = self.get_composite_score(cfg, current_iter)
                best_window = None
                consistency = None
                win_count = None
                win_fraction = None
            
            # ⭐ Use SHORT window for ratio calculation (recent 10 iters, not cumulative 180)
            tp, fp = self.get_rolling_tp_fp(cfg, current_iter, window=ratio_window)
            ratio = tp / max(fp, 1)
            precision = tp / max(tp + fp, 1)
            
            all_scores.append({
                'name': cfg,
                'score': data['final_score'],
                'momentum': data['momentum_signal'],
                'tp': tp,
                'fp': fp,
                'ratio': ratio,
                'precision': precision,
                'best_window': best_window,
                'consistency': consistency,
                'window_wins': win_count,
                'win_fraction': win_fraction,
            })
        
        all_scores.sort(key=lambda x: x['score'] * np.sqrt(x['ratio']), reverse=True)
        return all_scores[:n]
    
    def get_best_window_for_config(self, config_name: str, current_iter: int) -> Tuple[int, Dict]:
        """Find the optimal window for a specific config."""
        dense_data = self.get_dense_window_scores(config_name, current_iter)
        best_window = dense_data['best_window']
        
        if best_window is None:
            return None, {}
        
        tp_fp_data = dense_data['tp_fp_by_window'].get(best_window, {})
        return best_window, {
            'window': best_window,
            'tp': tp_fp_data.get('tp', 0),
            'fp': tp_fp_data.get('fp', 0),
            'ratio': tp_fp_data.get('ratio', 0),
            'score': dense_data['window_scores'].get(best_window, 0),
        }

    # ════════════════════════════════════════════════════════════════════════════
    # ⭐ V3.1: MARKET REGIME DETECTION AND ADAPTIVE CONFIG SELECTION
    # ════════════════════════════════════════════════════════════════════════════
    
    def detect_market_regime(self, current_iter: int, market_ratio: float = None) -> Dict:
        """
        Detect market regime using multiple indicators:
        1. Dual EMA trend (short-term vs long-term performance EMAs)
        2. RSI of performance EMAs (momentum/overbought/oversold)
        3. Market ratio (UP/DOWN days ratio from actual market data)
        4. Momentum signal from config performance
        
        Returns:
            Dict with:
              - regime: 'BEARISH' | 'STABLE' | 'BULLISH'
              - confidence: 0.0-1.0
              - indicators: detailed breakdown
        """
        # Default: neutral regime until we have data
        default_result = {
            'regime': REGIME_STABLE,
            'confidence': 0.0,
            'indicators': {},
            'reason': 'INSUFFICIENT_DATA'
        }
        
        if current_iter < 50:
            default_result['reason'] = f'Need 50+ iterations (have {current_iter})'
            return default_result
        
        # Ensure dual EMA history is updated
        if current_iter not in self.dual_ema_history:
            self.update_dual_ema_history(current_iter)
        
        ema_data = self.dual_ema_history.get(current_iter, {})
        if not ema_data or not ema_data.get('long_term_ema'):
            # Not enough windows yet for dual EMA
            default_result['reason'] = 'EMA_NOT_READY'
            return default_result
        
        # ─────────────────────────────────────────────────────────────────────
        # INDICATOR 1: MODEL PERFORMANCE EMA Crossover (THE STRONGEST SIGNAL)
        # From analysis: StEMA > LtEMA → Precision 62%, Return +0.21%
        #                StEMA <= LtEMA → Precision 44%, Return -0.17%
        # This tells us if MODEL is performing well recently vs historically
        # ─────────────────────────────────────────────────────────────────────
        long_ema = ema_data.get('long_term_ema', 1.0)
        short_ema = ema_data.get('short_term_ema', 1.0)
        
        # Model performance crossover
        if short_ema > long_ema:
            # Model performing better recently → configs are reliable
            ema_signal = 'MODEL_STRONG'
            ema_score = 0.6  # Strong positive signal
        else:
            # Model performing worse recently → configs less reliable
            ema_signal = 'MODEL_WEAK'
            ema_score = 0.4  # Weak signal
        
        # ─────────────────────────────────────────────────────────────────────
        # INDICATOR 2: MODEL PERFORMANCE LtEMA Quartile (CONTRARIAN)
        # From analysis: Low LtEMA (Q1 ≤0.95) → Precision 54.5% (BETTER!)
        #                High LtEMA (Q4 >1.47) → Precision 45.5% (WORSE!)
        # Contrarian: Bad model performance predicts BETTER next predictions
        # ─────────────────────────────────────────────────────────────────────
        LT_EMA_Q1 = 0.95
        LT_EMA_Q4 = 1.474
        
        if long_ema < LT_EMA_Q1:
            # Low performance historically → mean reversion → expect BETTER
            quartile_signal = 'CONTRARIAN_BULLISH'
            quartile_score = 0.55
        elif long_ema > LT_EMA_Q4:
            # High performance historically → regression expected → expect WORSE
            quartile_signal = 'CONTRARIAN_BEARISH'
            quartile_score = 0.45
        else:
            quartile_signal = 'NEUTRAL'
            quartile_score = 0.5
        
        # ─────────────────────────────────────────────────────────────────────
        # INDICATOR 3: DANGER ZONE (High EMA + High RSI = 36% precision!)
        # From analysis: When both LtEMA > median AND StRSI > 60
        # → Precision CRASHES to 36%, Return -0.45%
        # This is NOT overbought in TA sense - it's model overconfidence
        # ─────────────────────────────────────────────────────────────────────
        short_rsi = ema_data.get('short_term_rsi', 50.0)
        LT_EMA_MEDIAN = 1.078
        
        if long_ema > LT_EMA_MEDIAN and short_rsi > 60:
            danger_signal = 'DANGER_ZONE'
            danger_score = 0.36  # Very low precision expected
        else:
            danger_signal = 'SAFE'
            danger_score = 0.0
        
        # ─────────────────────────────────────────────────────────────────────
        # INDICATOR 4: Market ratio (actual UP/DOWN days - THIS is real market)
        # ─────────────────────────────────────────────────────────────────────
        if market_ratio is not None and market_ratio > 0:
            if market_ratio > 1.3:
                market_signal = 'BULLISH'
                market_score = min(1.0, (market_ratio - 1.0) * 2)
            elif market_ratio < 0.7:
                market_signal = 'BEARISH'
                market_score = min(1.0, (1.0 - market_ratio) * 2)
            else:
                market_signal = 'STABLE'
                market_score = 0.0
        else:
            market_signal = 'UNKNOWN'
            market_score = 0.0
        
        # ─────────────────────────────────────────────────────────────────────
        # INDICATOR 5: Momentum from top config
        # ─────────────────────────────────────────────────────────────────────
        top_configs = self.get_top_configs(current_iter, n=3)
        if top_configs:
            momentum_signals = [c.get('momentum', 'STABLE') for c in top_configs]
            bullish_count = sum(1 for s in momentum_signals if s in ['IMPROVING', 'STRENGTHENING'])
            bearish_count = sum(1 for s in momentum_signals if s in ['DECLINING', 'WEAKENING'])
            
            if bullish_count >= 2:
                mom_signal = 'BULLISH'
                mom_score = bullish_count / 3.0
            elif bearish_count >= 2:
                mom_signal = 'BEARISH'
                mom_score = bearish_count / 3.0
            else:
                mom_signal = 'STABLE'
                mom_score = 0.0
        else:
            mom_signal = 'UNKNOWN'
            mom_score = 0.0
        
        # ─────────────────────────────────────────────────────────────────────
        # COMBINE INDICATORS FOR REGIME DETECTION
        # Model performance indicators affect CONFIG SELECTION reliability
        # Market ratio is the actual MARKET condition
        # ─────────────────────────────────────────────────────────────────────
        
        # Model reliability score (from model EMA/RSI - affects config selection confidence)
        model_reliability = ema_score  # 0.4-0.6 based on crossover
        if danger_signal == 'DANGER_ZONE':
            model_reliability *= 0.5  # Cut reliability in half in danger zone
        if quartile_signal == 'CONTRARIAN_BULLISH':
            model_reliability *= 1.1  # Boost slightly (mean reversion)
        elif quartile_signal == 'CONTRARIAN_BEARISH':
            model_reliability *= 0.9  # Reduce slightly
        
        # Market regime determination (from actual market data + config momentum)
        bullish_total = 0.0
        bearish_total = 0.0
        
        # Market ratio contributes to regime
        if market_signal == 'BULLISH':
            bullish_total += market_score * 0.5
        elif market_signal == 'BEARISH':
            bearish_total += market_score * 0.5
        
        # Config momentum contributes to regime
        if mom_signal == 'BULLISH':
            bullish_total += mom_score * 0.3
        elif mom_signal == 'BEARISH':
            bearish_total += mom_score * 0.3
        
        # Determine regime (based on MARKET, not model performance)
        if bearish_total > bullish_total and bearish_total > 0.15:
            regime = REGIME_BEARISH
            confidence = min(1.0, bearish_total + (1 - model_reliability) * 0.3)
        elif bullish_total > bearish_total and bullish_total > 0.15:
            regime = REGIME_BULLISH
            confidence = min(1.0, bullish_total * model_reliability)
        else:
            regime = REGIME_STABLE
            confidence = model_reliability
        
        return {
            'regime': regime,
            'confidence': confidence,
            'model_reliability': model_reliability,
            'bullish_score': bullish_total,
            'bearish_score': bearish_total,
            'indicators': {
                'model_ema_crossover': {'signal': ema_signal, 'st_ema': short_ema, 'lt_ema': long_ema, 'score': ema_score},
                'model_quartile': {'signal': quartile_signal, 'lt_ema': long_ema, 'score': quartile_score},
                'danger_zone': {'signal': danger_signal, 'lt_ema': long_ema, 'st_rsi': short_rsi, 'score': danger_score},
                'market': {'signal': market_signal, 'ratio': market_ratio, 'score': market_score},
                'momentum': {'signal': mom_signal, 'score': mom_score},
            },
            'reason': f'{regime} (model_rel={model_reliability:.2f}, mkt_bull={bullish_total:.2f}, mkt_bear={bearish_total:.2f})'
        }

    def select_regime_adapted_config(
        self, 
        current_iter: int, 
        market_ratio: float = None,
        n_top: int = 5
    ) -> Tuple[str, Dict]:
        """
        Select best config from top N, adapted to current market regime.
        
        Strategy:
        - BEARISH market → choose "very precise" config (highest precision)
          Rationale: In bearish conditions, minimize false positives to avoid losses
        
        - STABLE market → choose "balanced" config (best ratio score)
          Rationale: Normal market - use standard optimization for balanced performance
        
        - BULLISH market → choose "very stable" config (highest consistency)
          Rationale: In bullish conditions, maximize exposure with consistent performer
        
        Args:
            current_iter: Current walk-forward iteration
            market_ratio: Optional UP/DOWN market ratio from actual data
            n_top: Number of top configs to consider
            
        Returns:
            (selected_config_name, selection_info_dict)
        """
        # Get top N configs by standard scoring
        top_configs = self.get_top_configs(current_iter, n=n_top)
        
        if not top_configs:
            return None, {'decision': 'NO_CONFIGS', 'regime': REGIME_STABLE}
        
        # Detect current market regime
        regime_info = self.detect_market_regime(current_iter, market_ratio)
        regime = regime_info['regime']
        confidence = regime_info['confidence']
        
        # If only 1 config or low confidence, use standard selection
        if len(top_configs) == 1 or confidence < 0.2:
            selected = top_configs[0]['name']
            return selected, {
                'decision': 'DEFAULT_TOP1',
                'regime': regime,
                'confidence': confidence,
                'n_candidates': len(top_configs),
                'selected': selected,
                'regime_info': regime_info
            }
        
        # ─────────────────────────────────────────────────────────────────────
        # REGIME-SPECIFIC SELECTION CRITERIA
        # ─────────────────────────────────────────────────────────────────────
        
        if regime == REGIME_BEARISH:
            # BEARISH: Select config with HIGHEST PRECISION
            # Precision = TP / (TP + FP) - minimizes false positives
            # Sort by precision (descending), break ties with ratio
            ranked = sorted(
                top_configs, 
                key=lambda c: (c['precision'], c['ratio']), 
                reverse=True
            )
            selection_metric = 'precision'
            selection_rationale = 'Bearish regime → minimize FP with highest precision'
            
        elif regime == REGIME_BULLISH:
            # BULLISH: Select config with HIGHEST CONSISTENCY
            # Consistency = fraction of windows where ratio > 1.0
            # Sort by consistency (descending), break ties with score
            ranked = sorted(
                top_configs,
                key=lambda c: (c.get('consistency', 0.0), c['score']),
                reverse=True
            )
            selection_metric = 'consistency'
            selection_rationale = 'Bullish regime → maximize exposure with most consistent'
            
        else:  # REGIME_STABLE
            # STABLE: Use standard scoring (already sorted by score * sqrt(ratio))
            # This is the balanced approach
            ranked = top_configs  # Already sorted
            selection_metric = 'balanced_score'
            selection_rationale = 'Stable regime → balanced TP/FP optimization'
        
        # Select top of regime-ranked list
        selected_config = ranked[0]
        selected_name = selected_config['name']
        
        # Apply cooldown check (use parent class logic)
        iters_since_switch = current_iter - self.last_switch_iter
        in_cooldown = iters_since_switch < self.switch_cooldown
        
        if in_cooldown and self.current_config is not None:
            # Stay with current config during cooldown
            return self.current_config, {
                'decision': 'COOLDOWN',
                'regime': regime,
                'confidence': confidence,
                'cooldown_left': self.switch_cooldown - iters_since_switch,
                'would_select': selected_name,
                'current': self.current_config,
                'selection_metric': selection_metric,
                'regime_info': regime_info
            }
        
        # Check if switch is warranted
        if self.current_config is None:
            # First selection
            self.current_config = selected_name
            self.last_switch_iter = current_iter
            return selected_name, {
                'decision': 'INITIAL_REGIME_SELECT',
                'regime': regime,
                'confidence': confidence,
                'selected': selected_name,
                'selection_metric': selection_metric,
                'rationale': selection_rationale,
                'candidates': [c['name'] for c in ranked[:3]],
                'regime_info': regime_info
            }
        
        # Check if we're switching to a different config
        if selected_name != self.current_config:
            # Get improvement metric based on regime
            current_data = next((c for c in top_configs if c['name'] == self.current_config), None)
            
            if current_data:
                if regime == REGIME_BEARISH:
                    current_metric = current_data.get('precision', 0)
                    new_metric = selected_config.get('precision', 0)
                elif regime == REGIME_BULLISH:
                    current_metric = current_data.get('consistency', 0)
                    new_metric = selected_config.get('consistency', 0)
                else:
                    current_metric = current_data.get('score', 0)
                    new_metric = selected_config.get('score', 0)
                
                improvement = (new_metric - current_metric) / max(current_metric, 0.01)
                
                # Apply threshold based on confidence
                # Higher confidence → lower threshold needed to switch
                switch_threshold = self.switch_threshold * (1.0 - 0.3 * confidence)
                
                if improvement >= switch_threshold:
                    old_config = self.current_config
                    self.current_config = selected_name
                    self.last_switch_iter = current_iter
                    self.switch_history.append((
                        current_iter, old_config, selected_name, 
                        f'REGIME_{regime}_{selection_metric}'
                    ))
                    
                    return selected_name, {
                        'decision': 'REGIME_SWITCH',
                        'regime': regime,
                        'confidence': confidence,
                        'from': old_config,
                        'to': selected_name,
                        'improvement': improvement,
                        'threshold': switch_threshold,
                        'selection_metric': selection_metric,
                        'rationale': selection_rationale,
                        'regime_info': regime_info
                    }
                else:
                    return self.current_config, {
                        'decision': 'REGIME_HOLD',
                        'regime': regime,
                        'confidence': confidence,
                        'current': self.current_config,
                        'candidate': selected_name,
                        'improvement': improvement,
                        'threshold': switch_threshold,
                        'reason': f'Improvement {improvement:.1%} < threshold {switch_threshold:.1%}',
                        'regime_info': regime_info
                    }
            else:
                # Current config not in top N anymore - switch
                old_config = self.current_config
                self.current_config = selected_name
                self.last_switch_iter = current_iter
                self.switch_history.append((
                    current_iter, old_config, selected_name,
                    f'REGIME_{regime}_CURRENT_DROPPED'
                ))
                
                return selected_name, {
                    'decision': 'REGIME_SWITCH_DROPPED',
                    'regime': regime,
                    'confidence': confidence,
                    'from': old_config,
                    'to': selected_name,
                    'reason': 'Current config dropped from top N',
                    'selection_metric': selection_metric,
                    'regime_info': regime_info
                }
        
        # No switch needed - staying with current
        return self.current_config, {
            'decision': 'REGIME_CONTINUE',
            'regime': regime,
            'confidence': confidence,
            'selected': self.current_config,
            'selection_metric': selection_metric,
            'regime_info': regime_info
        }
