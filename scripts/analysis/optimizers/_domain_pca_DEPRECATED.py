"""
Domain PCA Optimizer
====================

Reduces feature redundancy by applying PCA within each feature domain.
High-redundancy domains (Oscillator, Sentiment, Funding) can be compressed
to 1-2 components without losing much signal.

Research basis:
- 148 redundant feature pairs (|r| > 0.9) identified
- Some domains have 74% variance in PC1 (Oscillator)
- PCA reduces dimensionality while preserving signal

Usage:
    optimizer = DomainPCAOptimizer(variance_threshold=0.9)
    X_reduced = optimizer.fit_transform(X)
"""

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

from scripts.analysis.optimizers.base import BaseOptimizer

# Default domain classification
DOMAIN_PREFIXES = {
    "Momentum": ["M_P_", "M_N_"],
    "Volatility": ["V_", "N_V_"],
    "Oscillator": ["M_N_T_stochastic", "M_N_rsi", "N_M_cci"],
    "Trend": ["M_T_"],
    "Volume": ["L_M_", "L_V_", "L_S_"],
    "Funding": ["F_I_", "F_TM_"],
    "Premium": ["D_F_"],
    "Sentiment": ["S_"],
    "OpenInterest": ["L_S_oi", "L_N_oi"],
    "Candlestick": ["C_"],
    "Other": [],  # Catch-all
}


class DomainPCAOptimizer(BaseOptimizer):
    """
    Apply PCA within each feature domain to reduce redundancy.

    For each domain:
        1. Standardize features
        2. Apply PCA
        3. Keep components explaining variance_threshold
        4. Name output: {domain}_PC1, {domain}_PC2, etc.

    Args:
        variance_threshold: Keep components until this cumulative variance
        max_components: Maximum components per domain (None = no limit)
        min_components: Minimum components per domain
        domains_to_reduce: Specific domains to apply PCA (None = all)
        passthrough_domains: Domains to skip PCA
    """

    name = "DomainPCA"

    def __init__(
        self,
        variance_threshold: float = 0.90,
        max_components: int | None = None,
        min_components: int = 1,
        domains_to_reduce: list[str] | None = None,
        passthrough_domains: list[str] | None = None,
    ) -> None:
        super().__init__()
        self.variance_threshold = variance_threshold
        self.max_components = max_components
        self.min_components = min_components
        self.domains_to_reduce = domains_to_reduce
        self.passthrough_domains = passthrough_domains or ["Other"]

        # Learned parameters
        self._domain_mapping: dict[str, list[str]] = {}
        self._pca_models: dict[str, PCA] = {}
        self._scalers: dict[str, StandardScaler] = {}
        self._n_components: dict[str, int] = {}

    def _classify_feature(self, feature: str) -> str:
        """Classify a feature into a domain."""
        for domain, prefixes in DOMAIN_PREFIXES.items():
            if domain == "Other":
                continue
            for prefix in prefixes:
                if feature.startswith(prefix) or prefix in feature:
                    return domain
        return "Other"

    def fit(self, X: pd.DataFrame, y: pd.Series | None = None) -> "DomainPCAOptimizer":
        """
        Fit PCA models for each domain.

        Args:
            X: Feature DataFrame
            y: Not used

        Returns:
            self
        """
        self._feature_names_in = list(X.columns)

        # Classify features into domains
        self._domain_mapping = {}
        for col in X.columns:
            domain = self._classify_feature(col)
            if domain not in self._domain_mapping:
                self._domain_mapping[domain] = []
            self._domain_mapping[domain].append(col)

        # Determine which domains to reduce
        domains_to_process = self.domains_to_reduce or list(self._domain_mapping.keys())
        domains_to_process = [
            d for d in domains_to_process if d not in self.passthrough_domains
        ]

        self._pca_models = {}
        self._scalers = {}
        self._n_components = {}
        output_cols = []

        for domain in sorted(self._domain_mapping.keys()):
            domain_cols = self._domain_mapping[domain]

            if domain in self.passthrough_domains or domain not in domains_to_process:
                # Passthrough: keep original features
                output_cols.extend(domain_cols)
                continue

            if len(domain_cols) < 3:
                # Too few features for PCA
                output_cols.extend(domain_cols)
                continue

            # Prepare data
            X_domain = X[domain_cols].dropna()
            if len(X_domain) < 100:
                output_cols.extend(domain_cols)
                continue

            # Standardize
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X_domain)

            # Fit PCA
            n_max = min(len(domain_cols), self.max_components or len(domain_cols))
            pca = PCA(n_components=n_max)
            pca.fit(X_scaled)

            # Determine number of components to keep
            cumvar = np.cumsum(pca.explained_variance_ratio_)
            n_keep = np.searchsorted(cumvar, self.variance_threshold) + 1
            n_keep = max(self.min_components, min(n_keep, n_max))

            self._pca_models[domain] = pca
            self._scalers[domain] = scaler
            self._n_components[domain] = n_keep

            # Output column names
            for i in range(n_keep):
                output_cols.append(f"{domain}_PC{i + 1}")

        self._feature_names_out = output_cols
        self.is_fitted = True
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """
        Transform features using fitted PCA models.

        Args:
            X: Feature DataFrame

        Returns:
            Reduced DataFrame with PCA components
        """
        if not self.is_fitted:
            raise RuntimeError("Must call fit() before transform()")

        result_data = {}

        for domain in sorted(self._domain_mapping.keys()):
            domain_cols = self._domain_mapping[domain]

            if domain not in self._pca_models:
                # Passthrough
                for col in domain_cols:
                    if col in X.columns:
                        result_data[col] = X[col].values
            else:
                # Apply PCA
                X_domain = X[domain_cols].copy()

                # Handle NaN: fill with column means
                X_domain = X_domain.fillna(X_domain.mean())

                scaler = self._scalers[domain]
                pca = self._pca_models[domain]
                n_keep = self._n_components[domain]

                X_scaled = scaler.transform(X_domain)
                X_pca = pca.transform(X_scaled)

                for i in range(n_keep):
                    result_data[f"{domain}_PC{i + 1}"] = X_pca[:, i]

        return pd.DataFrame(result_data, index=X.index)

    def get_pca_info(self) -> pd.DataFrame:
        """Get summary of PCA transformation per domain."""
        rows = []
        for domain, pca in self._pca_models.items():
            n_keep = self._n_components[domain]
            var_explained = sum(pca.explained_variance_ratio_[:n_keep])
            n_original = len(self._domain_mapping[domain])
            rows.append(
                {
                    "domain": domain,
                    "n_features_in": n_original,
                    "n_components_out": n_keep,
                    "variance_explained": var_explained,
                    "reduction_ratio": n_keep / n_original,
                }
            )
        return pd.DataFrame(rows).sort_values("variance_explained", ascending=False)
