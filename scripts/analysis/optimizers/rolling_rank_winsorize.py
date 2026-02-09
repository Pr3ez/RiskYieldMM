"""
Rolling Rank-Winsorize Transformer (Causal, Streaming)
======================================================

CORRECT winsorize-rank implementation:
1. Rank transform: u_t = percentile of x_t vs past L values (t-L..t-1)
2. Clip ranks: u_t' = clip(u_t, p_min, p_max)
3. Optional post-transform: uniform, signed, or gaussianized

CAUSAL GUARANTEE:
    At time t, rank is computed from t-L..t-1 only (not including t).
    Rolling window ensures bounded memory O(L) per feature.

STREAMING:
    State (rolling buffer per feature) carries across batches.
    Call transform_streaming() with state to process sequentially.

Usage:
    transformer = RollingRankWinsorizeTransformer(
        window=96,           # Rolling window size
        p_min=0.02,          # Clip ranks below this
        p_max=0.98,          # Clip ranks above this
        post_transform="uniform"  # "uniform", "signed", or "gauss"
    )

    # Streaming mode (across batches):
    state = None
    for batch in batches:
        df_out, state = transformer.transform_streaming(batch, state)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd
from numba import njit, prange
from scipy.stats import norm


@njit(cache=True)
def _rolling_rank_single(values: np.ndarray, window: int) -> np.ndarray:
    """
    Compute rolling rank for a single feature (causal).

    At time t, rank = (count of values in [t-window..t-1] <= x_t) / window
    Output is in [0, 1].
    """
    n = len(values)
    ranks = np.full(n, np.nan, dtype=np.float64)

    for t in range(window, n):
        x_t = values[t]
        if np.isnan(x_t):
            continue

        # Count values in past window that are <= x_t
        count = 0
        valid = 0
        for i in range(t - window, t):
            x_i = values[i]
            if not np.isnan(x_i):
                valid += 1
                if x_i <= x_t:
                    count += 1

        if valid > 0:
            ranks[t] = count / valid

    return ranks


@njit(parallel=True, cache=True)
def _rolling_rank_batch(
    data: np.ndarray,  # (n_rows, n_features)
    window: int,
) -> np.ndarray:
    """Compute rolling rank for all features in parallel."""
    n_rows, n_features = data.shape
    result = np.full((n_rows, n_features), np.nan, dtype=np.float64)

    for col in prange(n_features):
        result[:, col] = _rolling_rank_single(data[:, col], window)

    return result


@njit(cache=True)
def _rolling_rank_streaming_single(
    values: np.ndarray,
    buffer: np.ndarray,
    buffer_pos: int,
    buffer_count: int,
    window: int,
) -> tuple[np.ndarray, np.ndarray, int, int]:
    """
    Streaming rolling rank for a single feature.

    Uses circular buffer to maintain past L values.
    Returns: (ranks, updated_buffer, new_pos, new_count)
    """
    n = len(values)
    ranks = np.full(n, np.nan, dtype=np.float64)

    for t in range(n):
        x_t = values[t]

        if not np.isnan(x_t):
            # Compute rank against buffer (past values)
            if buffer_count > 0:
                count = 0
                for i in range(buffer_count):
                    if buffer[i] <= x_t:
                        count += 1
                ranks[t] = count / buffer_count

            # Update buffer (circular)
            buffer[buffer_pos] = x_t
            buffer_pos = (buffer_pos + 1) % window
            if buffer_count < window:
                buffer_count += 1

    return ranks, buffer, buffer_pos, buffer_count


@dataclass
class RollingRankWinsorizeTransformer:
    """
    Rolling Rank-Winsorize transformer (causal, streaming).

    Correct order: RANK first, then CLIP ranks.

    Args:
        window: Rolling window size L (past L values used for rank)
        p_min: Lower clip bound for ranks (e.g., 0.02)
        p_max: Upper clip bound for ranks (e.g., 0.98)
        post_transform: "uniform" (keep [0,1]), "signed" ([-1,1]), "gauss" (Φ⁻¹)
        exclude_patterns: Feature name patterns to exclude
    """

    window: int = 96
    p_min: float = 0.02
    p_max: float = 0.98
    post_transform: Literal["uniform", "signed", "gauss"] = "uniform"
    exclude_patterns: list[str] = field(
        default_factory=lambda: [
            "_bin",  # Binary features
            "_state",  # Discrete state
            "_regime",  # Regime (categorical)
        ]
    )

    def __post_init__(self):
        self._feature_cols: list[str] = []
        self._state: dict | None = None

    def _should_transform(self, col: str) -> bool:
        """Check if column should be transformed."""
        return not any(pattern in col for pattern in self.exclude_patterns)

    def _apply_post_transform(self, ranks: np.ndarray) -> np.ndarray:
        """Apply post-transform to clipped ranks."""
        if self.post_transform == "uniform":
            return ranks
        elif self.post_transform == "signed":
            return 2 * ranks - 1  # [0,1] -> [-1,1]
        elif self.post_transform == "gauss":
            # Clip to avoid inf at 0 and 1
            eps = 1e-6
            clipped = np.clip(ranks, eps, 1 - eps)
            return norm.ppf(clipped)
        else:
            return ranks

    def transform(
        self,
        X: pd.DataFrame,
        feature_cols: list[str] | None = None,
    ) -> pd.DataFrame:
        """
        Transform entire DataFrame (non-streaming, for single batch use).

        Note: For proper cross-batch continuity, use transform_streaming().
        """
        if feature_cols is None:
            feature_cols = [c for c in X.columns if self._should_transform(c)]

        self._feature_cols = feature_cols
        result = X.copy()

        # Extract feature data
        data = X[feature_cols].values.astype(np.float64)

        # Compute rolling ranks
        ranks = _rolling_rank_batch(data, self.window)

        # Clip ranks
        ranks = np.clip(ranks, self.p_min, self.p_max)

        # Apply post-transform
        ranks = self._apply_post_transform(ranks)

        # Put back
        for i, col in enumerate(feature_cols):
            result[col] = ranks[:, i]

        return result

    def transform_streaming(
        self,
        X: pd.DataFrame,
        state: dict | None = None,
        feature_cols: list[str] | None = None,
    ) -> tuple[pd.DataFrame, dict]:
        """
        Transform DataFrame with state carry-over (streaming mode).

        Args:
            X: Input DataFrame (one batch)
            state: Previous state dict (None for first batch)
            feature_cols: Columns to transform

        Returns:
            (transformed_df, new_state)
        """
        if feature_cols is None:
            feature_cols = [c for c in X.columns if self._should_transform(c)]

        self._feature_cols = feature_cols
        result = X.copy()

        # Initialize state if needed
        if state is None:
            state = {
                "buffers": {col: np.full(self.window, np.nan) for col in feature_cols},
                "positions": dict.fromkeys(feature_cols, 0),
                "counts": dict.fromkeys(feature_cols, 0),
            }

        # Process each feature
        for col in feature_cols:
            if col not in X.columns:
                continue

            values = X[col].values.astype(np.float64)
            buffer = state["buffers"][col]
            pos = state["positions"][col]
            count = state["counts"][col]

            # Compute streaming ranks
            ranks, new_buffer, new_pos, new_count = _rolling_rank_streaming_single(
                values, buffer, pos, count, self.window
            )

            # Clip ranks
            ranks = np.clip(ranks, self.p_min, self.p_max)

            # Apply post-transform
            ranks = self._apply_post_transform(ranks)

            # Store result
            result[col] = ranks

            # Update state
            state["buffers"][col] = new_buffer
            state["positions"][col] = new_pos
            state["counts"][col] = new_count

        return result, state

    def get_config(self) -> dict:
        """Return configuration dict."""
        return {
            "window": self.window,
            "p_min": self.p_min,
            "p_max": self.p_max,
            "post_transform": self.post_transform,
        }


def get_winsorize_rank_candidates(tf: str) -> list[dict]:
    """
    Get hyperparameter candidates for winsorize-rank tuning.

    Parameters scaled per timeframe to cover ~8h worth of history.

    Args:
        tf: Timeframe string ("5m", "15m", "1h")

    Returns:
        List of config dicts with keys: window, p_min, p_max, post_transform
    """
    # Window sizes (roughly 4h, 8h, 16h worth of bars)
    window_map = {
        "1m": [240, 480, 960],
        "5m": [48, 96, 192],
        "15m": [16, 32, 64],
        "1h": [4, 8, 16],
    }

    windows = window_map.get(tf, [48, 96, 192])

    # Clip bounds
    clip_bounds = [
        (0.01, 0.99),
        (0.02, 0.98),
        (0.05, 0.95),
    ]

    # Post-transforms
    post_transforms = [
        "uniform",
        "signed",
    ]  # gauss can be added but often not needed for trees

    candidates = []
    for window in windows:
        for p_min, p_max in clip_bounds:
            for post in post_transforms:
                candidates.append(
                    {
                        "window": window,
                        "p_min": p_min,
                        "p_max": p_max,
                        "post_transform": post,
                    }
                )

    return candidates
