"""
Regime Conditioning Optimizer (Causal)
======================================

Adjusts feature weights based on market regime (trending vs mean-reverting).
Uses Hurst exponent as the regime indicator.

CAUSAL GUARANTEE:
    Uses FIXED threshold of 0.5 (theoretical Hurst boundary).
    H > 0.5 = trending, H < 0.5 = mean-reverting.
    No data-dependent threshold — no future leakage.

Research basis:
- Features like momentum (roc, momAtr) have opposite effects in different regimes
- In trending markets: momentum positive IC
- In reverting markets: momentum negative IC or zero
- Regime-conditioning can improve signal stability

Usage:
    optimizer = RegimeConditioningOptimizer(regime_feature='V_hurstExponent_63_rat_N')
    X_conditioned = optimizer.fit_transform(X, y)
"""

import numpy as np
import pandas as pd
from scipy import stats

from scripts.analysis.optimizers.base import BaseOptimizer


class RegimeConditioningOptimizer(BaseOptimizer):
    """
    Condition features on market regime using Hurst exponent.

    For features that show regime-dependent behavior:
        - Compute IC in trending regime (H > threshold)
        - Compute IC in reverting regime (H <= threshold)
        - If signs differ significantly, create regime-weighted version

    Output options:
        - 'weight': Multiply feature by regime weight
        - 'gate': Zero out feature in wrong regime
        - 'split': Create separate trend/revert versions

    Args:
        regime_feature: Name of Hurst exponent feature to use
        regime_threshold: Threshold for trending vs reverting (default 0.5)
        min_ic_diff: Minimum IC difference to trigger conditioning
        output_mode: How to handle regime ('weight', 'gate', 'split')
        target_features: Specific features to condition (None = auto-detect)
    """

    name = "RegimeConditioning"

    def __init__(
        self,
        regime_feature: str = "V_hurstExponent_63_rat_N",
        regime_threshold: float | None = None,  # None = use median
        min_ic_diff: float = 0.03,
        output_mode: str = "weight",
        target_features: list[str] | None = None,
    ) -> None:
        super().__init__()
        self.regime_feature = regime_feature
        self.regime_threshold = regime_threshold
        self.min_ic_diff = min_ic_diff
        self.output_mode = output_mode
        self.target_features = target_features

        # Learned parameters
        self._regime_median: float = 0.5
        self._feature_weights: dict[str, dict[str, float]] = {}
        self._conditioned_features: list[str] = []

    def fit(
        self, X: pd.DataFrame, y: pd.Series | None = None
    ) -> "RegimeConditioningOptimizer":
        """
        Learn which features need regime conditioning and their weights.

        Args:
            X: Feature DataFrame (must include regime_feature)
            y: Target series for IC calculation

        Returns:
            self
        """
        if y is None:
            raise ValueError("RegimeConditioningOptimizer requires y for fitting")

        if self.regime_feature not in X.columns:
            raise ValueError(f"Regime feature '{self.regime_feature}' not in X")

        self._feature_names_in = list(X.columns)

        # Determine regime threshold
        # CAUSAL: Use fixed theoretical threshold (0.5) instead of data-dependent median
        # Hurst exponent interpretation: H > 0.5 = trending, H < 0.5 = mean-reverting
        if self.regime_threshold is None:
            self._regime_median = 0.5  # Theoretical boundary, not data-dependent
        else:
            self._regime_median = self.regime_threshold

        # Get hurst values
        hurst = X[self.regime_feature].values

        # Create regime masks
        trending_mask = (hurst > self._regime_median) & ~np.isnan(y.values)
        reverting_mask = (hurst <= self._regime_median) & ~np.isnan(y.values)

        # Features to analyze
        if self.target_features:
            features_to_check = [f for f in self.target_features if f in X.columns]
        else:
            # Auto-detect: check features likely to be regime-dependent
            features_to_check = [
                c
                for c in X.columns
                if any(
                    pattern in c
                    for pattern in [
                        "roc_",
                        "momAtr_",
                        "pctB_",
                        "priceEma",
                        "priceSma",
                        "stochastic",
                        "rsi_",
                        "cci_",
                    ]
                )
            ]

        y_vals = y.values
        self._feature_weights = {}
        self._conditioned_features = []

        for col in features_to_check:
            x_vals = X[col].values

            # Compute IC in each regime
            mask_t = trending_mask & ~np.isnan(x_vals)
            mask_r = reverting_mask & ~np.isnan(x_vals)

            if mask_t.sum() > 100 and mask_r.sum() > 100:
                ic_trend, _ = stats.spearmanr(x_vals[mask_t], y_vals[mask_t])
                ic_revert, _ = stats.spearmanr(x_vals[mask_r], y_vals[mask_r])

                # Check if regime-dependent
                ic_diff = abs(ic_trend - ic_revert)
                if ic_diff >= self.min_ic_diff:
                    self._conditioned_features.append(col)
                    self._feature_weights[col] = {
                        "ic_trend": ic_trend,
                        "ic_revert": ic_revert,
                        "ic_diff": ic_diff,
                        # Weight based on which regime has better IC
                        "trend_weight": 1.0 if abs(ic_trend) > abs(ic_revert) else 0.5,
                        "revert_weight": 1.0 if abs(ic_revert) > abs(ic_trend) else 0.5,
                    }

        # Output feature names depend on mode
        if self.output_mode == "split":
            self._feature_names_out = list(X.columns)
            for col in self._conditioned_features:
                self._feature_names_out.append(f"{col}_trend")
                self._feature_names_out.append(f"{col}_revert")
        else:
            self._feature_names_out = list(X.columns)

        self.is_fitted = True
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """
        Apply regime conditioning to features.

        Args:
            X: Feature DataFrame

        Returns:
            Conditioned DataFrame
        """
        if not self.is_fitted:
            raise RuntimeError("Must call fit() before transform()")

        result = X.copy()
        hurst = X[self.regime_feature].values

        # Create regime indicator (1 = trending, 0 = reverting)
        is_trending = (hurst > self._regime_median).astype(float)
        is_reverting = 1 - is_trending

        for col in self._conditioned_features:
            if col not in X.columns:
                continue

            weights = self._feature_weights[col]

            if self.output_mode == "weight":
                # Multiply by regime-appropriate weight
                regime_weight = (
                    is_trending * weights["trend_weight"]
                    + is_reverting * weights["revert_weight"]
                )
                result[col] = X[col] * regime_weight

            elif self.output_mode == "gate":
                # Zero out in low-IC regime
                if weights["ic_trend"] > weights["ic_revert"]:
                    result[col] = X[col] * is_trending
                else:
                    result[col] = X[col] * is_reverting

            elif self.output_mode == "split":
                # Create separate features for each regime
                result[f"{col}_trend"] = X[col] * is_trending
                result[f"{col}_revert"] = X[col] * is_reverting

        return result

    def get_conditioning_info(self) -> pd.DataFrame:
        """Get summary of regime conditioning applied."""
        if not self._feature_weights:
            return pd.DataFrame()

        rows = []
        for col, weights in self._feature_weights.items():
            rows.append(
                {
                    "feature": col,
                    "ic_trending": weights["ic_trend"],
                    "ic_reverting": weights["ic_revert"],
                    "ic_difference": weights["ic_diff"],
                    "trend_weight": weights["trend_weight"],
                    "revert_weight": weights["revert_weight"],
                }
            )
        return pd.DataFrame(rows).sort_values("ic_difference", ascending=False)
