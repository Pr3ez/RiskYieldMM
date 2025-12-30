"""
Config History V3 - tracks TP/FP/TN/FN history per config with iteration tracking.
See WF_DOCS.md for architecture details.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class ConfigHistoryV3:
    """Track TP/FP/TN/FN history per config with iteration tracking"""
    outcomes: List[Tuple[int, int, int, int, int]] = field(default_factory=list)
    
    def add_outcome(self, iteration: int, tp: int, fp: int, tn: int, fn: int):
        self.outcomes.append((iteration, tp, fp, tn, fn))
    
    def get_rolling_stats(self, current_iter: int, window: int) -> Tuple[int, int, int]:
        """Get TP, FP counts and sample count for last N iterations.
        
        ⚠️ LEAKAGE FIX: Uses strictly PAST iterations only (it < current_iter).
        This ensures we don't use the current iteration's outcome to calculate
        metrics that influence the current prediction.
        """
        if not self.outcomes:
            return 0, 0, 0
        min_iter = current_iter - window
        # ⚠️ CRITICAL: Use it < current_iter (strictly before) to prevent leakage
        recent = [(tp, fp, tn, fn) for (it, tp, fp, tn, fn) in self.outcomes if min_iter < it < current_iter]
        if not recent:
            return 0, 0, 0
        return sum(x[0] for x in recent), sum(x[1] for x in recent), len(recent)
    
    def get_score_at_iter(self, target_iter: int, lookback: int = 10) -> float:
        """Get stability score around a specific iteration (for momentum calc).
        
        ⚠️ LEAKAGE FIX: Uses strictly PAST iterations only (it < target_iter).
        """
        min_iter = target_iter - lookback
        # ⚠️ CRITICAL: Use it < target_iter (strictly before) to prevent leakage
        recent = [(tp, fp) for (it, tp, fp, tn, fn) in self.outcomes if min_iter < it < target_iter]
        if len(recent) < 3:
            return 0.0
        tp_sum = sum(x[0] for x in recent)
        fp_sum = sum(x[1] for x in recent)
        if tp_sum < 3:
            return 0.0
        return (tp_sum / max(fp_sum, 1)) * np.sqrt(tp_sum)
    
    def get_total_tp_fp(self) -> Tuple[int, int]:
        """Get total TP and FP across all history"""
        if not self.outcomes:
            return 0, 0
        return sum(x[1] for x in self.outcomes), sum(x[2] for x in self.outcomes)
