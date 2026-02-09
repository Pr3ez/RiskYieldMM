"""
Rolling Calibration Buffer - accumulates CAL window predictions for Platt calibration.
See WF_DOCS.md for architecture details.
"""

import numpy as np


class RollingCalBuffer:
    """
    Rolling buffer for accumulating CAL window predictions for calibration.
    
    Key properties:
    - Stores (scores, labels) pairs from past CAL windows
    - Strictly historical: never includes VAL/PRED data
    - Configurable max windows and max samples
    - Provides combined buffer for fitting Platt calibrator
    """
    def __init__(self, max_windows=6, max_samples=5000, name='buffer'):
        self.windows = []  # list of (scores_np, labels_np)
        self.max_windows = max_windows
        self.max_samples = max_samples
        self.name = name
    
    def append(self, scores, labels):
        """Add new CAL window predictions to buffer."""
        scores = np.asarray(scores).reshape(-1)
        labels = np.asarray(labels).reshape(-1)
        self.windows.append((scores.copy(), labels.copy()))
        
        # Drop oldest windows if exceed count
        if len(self.windows) > self.max_windows:
            self.windows = self.windows[-self.max_windows:]
        
        # Drop oldest until sample cap satisfied
        while self.size() > self.max_samples and len(self.windows) > 1:
            self.windows.pop(0)
    
    def get_buffer(self):
        """Get concatenated scores and labels from all windows."""
        if not self.windows:
            return np.array([]), np.array([])
        scores = np.concatenate([w[0] for w in self.windows])
        labels = np.concatenate([w[1] for w in self.windows])
        return scores, labels
    
    def size(self):
        """Total number of samples in buffer."""
        return sum(w[0].size for w in self.windows)
    
    def n_windows(self):
        """Number of windows in buffer."""
        return len(self.windows)
    
    def n_positives(self):
        """Number of positive samples in buffer."""
        if not self.windows:
            return 0
        _, labels = self.get_buffer()
        return int(labels.sum())
