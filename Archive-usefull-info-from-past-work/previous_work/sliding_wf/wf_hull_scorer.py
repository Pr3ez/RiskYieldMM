"""
Hull Competition Scorer - tracks Hull Tactical competition score on a rolling basis.
See WF_DOCS.md for architecture details.
"""

import numpy as np
from typing import Dict, Tuple


class HullScorer:
    """
    Track Hull Tactical competition score on a rolling basis.
    
    Competition metric is an adjusted Sharpe ratio with penalties for:
    1. Excess volatility (if strategy_vol > 1.2 * market_vol)
    2. Return underperformance (if strategy_return < market_return)
    
    Position interpretation (signal 0-2):
    - 0.0 = 0% equity (100% risk-free)
    - 1.0 = 100% equity (buy and hold)
    - 2.0 = 200% equity (max leverage)
    
    Strategy return = rf * (1 - position) + position * market_return
    """
    
    def __init__(self, annualization_factor: int = 252, min_samples: int = 30):
        """
        Initialize Hull scorer.
        
        Args:
            annualization_factor: Trading days per year (252 for daily)
            min_samples: Minimum samples before computing score
        """
        self.annualization_factor = annualization_factor
        self.min_samples = min_samples
        
        # Rolling history for score calculation
        self.history = []  # List of dicts: {position, market_return, risk_free_rate}
        
        # Track scores over time
        self.score_history = []
    
    def update(self, position: float, market_return: float, risk_free_rate: float) -> None:
        """
        Add a new observation to the history.
        
        Args:
            position: Position size (0-2 scale)
            market_return: Actual market return for this period
            risk_free_rate: Risk-free rate for this period
        """
        self.history.append({
            'position': position,
            'market_return': market_return,
            'risk_free_rate': risk_free_rate,
        })
    
    def calculate_score(self, window: int = None) -> Tuple[float, Dict]:
        """
        Calculate Hull competition score on recent history.
        
        Args:
            window: Number of recent samples to use (None = all history)
            
        Returns:
            Tuple of (adjusted_sharpe, metadata_dict)
        """
        if len(self.history) < self.min_samples:
            return np.nan, {'status': 'insufficient_samples', 'n_samples': len(self.history)}
        
        # Get relevant history
        if window is not None and window < len(self.history):
            data = self.history[-window:]
        else:
            data = self.history
        
        # Extract arrays
        positions = np.array([d['position'] for d in data])
        market_returns = np.array([d['market_return'] for d in data])
        risk_free_rates = np.array([d['risk_free_rate'] for d in data])
        
        # Calculate strategy returns
        strategy_returns = risk_free_rates * (1 - positions) + positions * market_returns
        
        # Calculate excess returns
        strategy_excess = strategy_returns - risk_free_rates
        market_excess = market_returns - risk_free_rates
        
        # Calculate volatilities (daily std, then annualize for penalty)
        # NOTE: pandas .std() uses ddof=0 by default, so we match that
        strategy_vol_daily = np.std(strategy_returns, ddof=0)
        market_vol_daily = np.std(market_returns, ddof=0)
        strategy_vol_annual = strategy_vol_daily * np.sqrt(self.annualization_factor) * 100  # as percentage
        market_vol_annual = market_vol_daily * np.sqrt(self.annualization_factor) * 100  # as percentage
        
        # Calculate cumulative excess returns (geometric, matching competition)
        strategy_excess_cumulative = np.prod(1 + strategy_excess)
        market_excess_cumulative = np.prod(1 + market_excess)
        
        # Calculate geometric mean excess return (matching competition formula)
        n_samples = len(data)
        strategy_mean_excess = strategy_excess_cumulative ** (1 / n_samples) - 1
        market_mean_excess = market_excess_cumulative ** (1 / n_samples) - 1
        
        # Calculate Sharpe ratio (using daily std, annualized)
        if strategy_vol_daily > 1e-8:
            sharpe = (strategy_mean_excess / strategy_vol_daily) * np.sqrt(self.annualization_factor)
        else:
            sharpe = 0.0
        
        # Calculate volatility penalty (annualized vol ratio)
        vol_ratio = strategy_vol_annual / market_vol_annual if market_vol_annual > 1e-8 else 1.0
        vol_penalty = 1 + max(0, vol_ratio - 1.2)
        
        # Calculate return penalty (annualized gap, matching competition * 100 * 252)
        # market_mean_excess - strategy_mean_excess is daily, multiply by 252 to annualize, then by 100 for %
        return_gap = max(0, (market_mean_excess - strategy_mean_excess) * 100 * self.annualization_factor)
        return_penalty = 1 + (return_gap ** 2) / 100
        
        # Calculate adjusted Sharpe
        adjusted_sharpe = sharpe / (vol_penalty * return_penalty)
        
        # Build metadata
        metadata = {
            'status': 'ok',
            'n_samples': len(data),
            'sharpe': sharpe,
            'adjusted_sharpe': adjusted_sharpe,
            'strategy_vol': strategy_vol_annual,
            'market_vol': market_vol_annual,
            'vol_ratio': vol_ratio,
            'vol_penalty': vol_penalty,
            'strategy_mean_excess': strategy_mean_excess,
            'market_mean_excess': market_mean_excess,
            'strategy_excess_cum': strategy_excess_cumulative,
            'market_excess_cum': market_excess_cumulative,
            'return_gap_pct': return_gap,
            'return_penalty': return_penalty,
            'avg_position': np.mean(positions),
            'position_std': np.std(positions),
        }
        
        # Store in score history
        self.score_history.append({
            'n_samples': len(self.history),
            'adjusted_sharpe': adjusted_sharpe,
            **{k: v for k, v in metadata.items() if k not in ['status']}
        })
        
        return adjusted_sharpe, metadata
    
    def get_latest_score(self) -> Tuple[float, Dict]:
        """Get the most recent score without recalculating."""
        if not self.score_history:
            return np.nan, {'status': 'no_scores'}
        last = self.score_history[-1]
        return last['adjusted_sharpe'], last
    
    def get_summary(self) -> Dict:
        """Get summary statistics for all scores over time."""
        if not self.score_history:
            return {'status': 'no_scores'}
        
        scores = [s['adjusted_sharpe'] for s in self.score_history if not np.isnan(s['adjusted_sharpe'])]
        if not scores:
            return {'status': 'all_nan'}
        
        return {
            'n_evaluations': len(scores),
            'final_score': scores[-1],
            'mean_score': np.mean(scores),
            'std_score': np.std(scores),
            'min_score': np.min(scores),
            'max_score': np.max(scores),
            'score_trend': 'improving' if len(scores) >= 10 and np.mean(scores[-5:]) > np.mean(scores[:5]) else 'stable_or_declining',
        }
