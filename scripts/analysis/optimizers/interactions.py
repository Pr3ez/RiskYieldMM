"""
Interaction Features Optimizer (Causal)
=======================================

Generates cross-domain interaction features by multiplying
top features from different domains.

CAUSAL GUARANTEE:
    Standardization uses EXPANDING mean/std — only past data.
    Feature selection in fit() uses training data (acceptable).
    Transform at row N uses only rows 0..N-1 for normalization.

Research basis:
- momAtr_3 × volumeRoc_3 has IC=+0.055 (better than either alone)
- Interactions capture non-linear relationships
- Cross-domain interactions often uncover hidden signals

Usage:
    optimizer = InteractionOptimizer(top_k=5, n_interactions=10)
    X_with_interactions = optimizer.fit_transform(X, y)
"""

import numpy as np
import pandas as pd
from scipy import stats

from scripts.analysis.optimizers.base import BaseOptimizer


class InteractionOptimizer(BaseOptimizer):
    """
    Generate CAUSAL interaction features from top features across domains.

    For each pair of top features from different domains:
        interaction = expanding_standardize(f1) * expanding_standardize(f2)

    CAUSAL: Standardization uses expanding mean/std (only past data).

    Selection criteria:
        - Features must be from different domains
        - Correlation between features < max_correlation
        - Keep top n_interactions by IC

    Args:
        top_k: Number of top features to consider per domain
        n_interactions: Number of interactions to create
        max_correlation: Skip pairs with higher correlation
        min_ic: Minimum IC for interaction to be kept
        min_periods: Minimum observations for expanding stats (default 252)
        domain_map: Optional domain classification for features
    """

    name = "Interactions"

    def __init__(
        self,
        top_k: int = 3,
        n_interactions: int = 10,
        max_correlation: float = 0.5,
        min_ic: float = 0.02,
        min_periods: int = 252,
        domain_map: dict[str, str] | None = None,
    ) -> None:
        super().__init__()
        self.top_k = top_k
        self.n_interactions = n_interactions
        self.max_correlation = max_correlation
        self.min_ic = min_ic
        self.min_periods = min_periods
        self.domain_map = domain_map

        # Learned parameters (only which pairs to use, not global stats)
        self._interactions: list[tuple[str, str, float]] = []  # (f1, f2, ic)

    def _classify_feature(self, feature: str) -> str:
        """Classify a feature into a domain."""
        if self.domain_map and feature in self.domain_map:
            return self.domain_map[feature]

        # Simple heuristic based on prefix
        prefixes = {
            "M_P_": "Momentum",
            "M_N_": "Momentum",
            "M_T_": "Trend",
            "V_": "Volatility",
            "N_V_": "Volatility",
            "L_M_": "Volume",
            "L_V_": "Volume",
            "L_S_": "Volume",
            "F_I_": "Funding",
            "D_F_": "Premium",
            "S_": "Sentiment",
            "C_": "Candlestick",
        }
        for prefix, domain in prefixes.items():
            if feature.startswith(prefix):
                return domain
        return "Other"

    def fit(
        self, X: pd.DataFrame, y: pd.Series | None = None
    ) -> "InteractionOptimizer":
        """
        Identify best interaction pairs.

        Args:
            X: Feature DataFrame
            y: Target series for IC calculation

        Returns:
            self
        """
        if y is None:
            raise ValueError("InteractionOptimizer requires y for fitting")

        self._feature_names_in = list(X.columns)
        y_vals = y.values

        # Compute IC for each feature
        feature_ics = []
        for col in X.columns:
            x_vals = X[col].values
            mask = ~np.isnan(x_vals) & ~np.isnan(y_vals)
            if mask.sum() > 100:
                ic, _ = stats.spearmanr(x_vals[mask], y_vals[mask])
                if not np.isnan(ic):
                    feature_ics.append((col, abs(ic), self._classify_feature(col)))

        # Group by domain and get top_k per domain
        domain_features: dict[str, list[tuple[str, float]]] = {}
        for col, ic, domain in feature_ics:
            if domain not in domain_features:
                domain_features[domain] = []
            domain_features[domain].append((col, ic))

        top_by_domain = {}
        for domain, features in domain_features.items():
            sorted_feats = sorted(features, key=lambda x: -x[1])[: self.top_k]
            top_by_domain[domain] = [f[0] for f in sorted_feats]

        # Generate candidate interactions
        candidates = []
        domains = list(top_by_domain.keys())

        for i, d1 in enumerate(domains):
            for d2 in domains[i + 1 :]:
                for f1 in top_by_domain[d1]:
                    for f2 in top_by_domain[d2]:
                        # Check correlation
                        corr = X[[f1, f2]].corr().iloc[0, 1]
                        if abs(corr) > self.max_correlation:
                            continue

                        # Compute interaction
                        x1 = (X[f1] - X[f1].mean()) / (X[f1].std() + 1e-10)
                        x2 = (X[f2] - X[f2].mean()) / (X[f2].std() + 1e-10)
                        interaction = x1 * x2

                        # Compute IC
                        mask = ~np.isnan(interaction) & ~np.isnan(y_vals)
                        if mask.sum() > 100:
                            ic, _ = stats.spearmanr(
                                interaction.values[mask], y_vals[mask]
                            )
                            if not np.isnan(ic) and abs(ic) >= self.min_ic:
                                candidates.append((f1, f2, ic))

        # Select top interactions
        candidates.sort(key=lambda x: -abs(x[2]))
        self._interactions = candidates[: self.n_interactions]

        # NOTE: We do NOT store global mean/std anymore.
        # Standardization is done causally in transform() using expanding windows.

        # Output feature names
        self._feature_names_out = list(X.columns)
        for f1, f2, _ in self._interactions:
            name = f"{f1[:20]}×{f2[:20]}"
            self._feature_names_out.append(name)

        self.is_fitted = True
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """
        Add CAUSAL interaction features using expanding standardization.

        At each row, standardization uses only data from previous rows.

        Args:
            X: Feature DataFrame

        Returns:
            DataFrame with interaction features appended
        """
        if not self.is_fitted:
            raise RuntimeError("Must call fit() before transform()")

        result = X.copy()

        for f1, f2, _ in self._interactions:
            if f1 in X.columns and f2 in X.columns:
                # Compute expanding mean/std (shifted to avoid using current row)
                expanding_mean_1 = (
                    X[f1].expanding(min_periods=self.min_periods).mean().shift(1)
                )
                expanding_std_1 = (
                    X[f1].expanding(min_periods=self.min_periods).std().shift(1)
                )
                expanding_mean_2 = (
                    X[f2].expanding(min_periods=self.min_periods).mean().shift(1)
                )
                expanding_std_2 = (
                    X[f2].expanding(min_periods=self.min_periods).std().shift(1)
                )

                # Standardize causally
                x1 = (X[f1] - expanding_mean_1) / (expanding_std_1 + 1e-10)
                x2 = (X[f2] - expanding_mean_2) / (expanding_std_2 + 1e-10)

                name = f"{f1[:20]}×{f2[:20]}"
                result[name] = x1 * x2

        return result

    def get_interactions_info(self) -> pd.DataFrame:
        """Get summary of generated interactions."""
        rows = []
        for f1, f2, ic in self._interactions:
            rows.append(
                {
                    "feature_1": f1,
                    "feature_2": f2,
                    "interaction_name": f"{f1[:20]}×{f2[:20]}",
                    "ic": ic,
                }
            )
        return pd.DataFrame(rows).sort_values("ic", key=abs, ascending=False)
