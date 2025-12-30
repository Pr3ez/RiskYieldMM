"""
Rolling Meta Buffer - accumulates VAL window predictions for meta-stacker training.
See WF_DOCS.md for architecture details.
"""

import numpy as np


class RollingMetaBuffer:
    """
    Rolling buffer for accumulating VAL window predictions for meta-stacker training.
    
    Key properties:
    - Stores (cb_probs, lgb_probs, labels) from past VAL windows
    - Strictly historical: only completed VAL windows with known labels
    - Configurable max windows and max samples
    - Provides combined buffer for training LogisticRegression meta-stacker
    - Adapts to changing market conditions by including recent data
    """
    def __init__(self, max_windows=8, max_samples=8000, name='meta_buffer'):
        self.windows = []  # list of (cb_probs, lgb_probs, labels)
        self.max_windows = max_windows
        self.max_samples = max_samples
        self.name = name
    
    def append(self, cb_probs, lgb_probs, labels):
        """Add new VAL window calibrated predictions to buffer."""
        cb_probs = np.asarray(cb_probs).reshape(-1)
        lgb_probs = np.asarray(lgb_probs).reshape(-1)
        labels = np.asarray(labels).reshape(-1)
        self.windows.append((cb_probs.copy(), lgb_probs.copy(), labels.copy()))
        
        # Drop oldest windows if exceed count
        if len(self.windows) > self.max_windows:
            self.windows = self.windows[-self.max_windows:]
        
        # Drop oldest until sample cap satisfied
        while self.size() > self.max_samples and len(self.windows) > 1:
            self.windows.pop(0)
    
    def get_buffer(self):
        """Get concatenated features (X) and labels (y) from all windows."""
        if not self.windows:
            return np.array([]).reshape(0, 2), np.array([])
        cb_probs = np.concatenate([w[0] for w in self.windows])
        lgb_probs = np.concatenate([w[1] for w in self.windows])
        labels = np.concatenate([w[2] for w in self.windows])
        X = np.column_stack([cb_probs, lgb_probs])
        return X, labels
    
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
