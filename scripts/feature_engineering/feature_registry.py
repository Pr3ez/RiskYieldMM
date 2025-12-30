"""
Feature Registry for RiskYieldMM
================================
Extensible feature registration system for ML pipeline.

Design Goals:
1. Easy to add new features without modifying core logic
2. Automatic validation of feature specs
3. Feature metadata tracking (domain, form, periods)
4. Batch computation with dependency resolution

Usage:
    from feature_registry import FEATURE_REGISTRY, compute_features

    # Register new feature
    @register_feature(
        name='myFeature',
        domain='Momentum',
        form='pct',
        periods=[3, 6, 12],
        dependencies=['close']
    )
    def compute_my_feature(df, n):
        return df['close'].pct_change(n)

Author: RiskYieldMM Project
Created: 2025-12-20
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

# =============================================================================
# FEATURE SPECIFICATION
# =============================================================================


@dataclass
class FeatureSpec:
    """Specification for a single feature or feature family."""

    # Identity
    name: str  # Base name (e.g., 'roc', 'fundingMa')
    groups: str  # Group prefix (e.g., 'M_P', 'F_I_T')
    form: str  # Form suffix (e.g., 'pct', 'bnd', 'rat')
    normalized: bool = True  # _N or _NN suffix

    # Domain classification
    domain: str = "Other"  # For correlation analysis

    # Computation
    compute_fn: Callable = None  # Function to compute feature
    periods: list[int] = None  # If multi-period feature
    period_pairs: list[tuple] = None  # For dual-period features like PPO
    dependencies: list[str] = field(default_factory=list)  # Raw columns needed

    # Validation bounds
    expected_min: float = None  # For sanity check
    expected_max: float = None  # For sanity check
    bounded: bool = False  # If feature is bounded [min, max]

    # Documentation
    formula: str = ""  # Human-readable formula
    approved_date: str = ""  # When feature was approved
    doc_reference: str = ""  # Link to Part 3 documentation

    def full_name(self, period: int | None = None, period_pair: tuple = None) -> str:
        """Generate full feature name with naming convention."""
        norm_suffix = "_N" if self.normalized else "_NN"

        if period_pair:
            return f"{self.groups}_{self.name}_{period_pair[0]}_{period_pair[1]}_{self.form}{norm_suffix}"
        elif period:
            return f"{self.groups}_{self.name}_{period}_{self.form}{norm_suffix}"
        else:
            return f"{self.groups}_{self.name}_{self.form}{norm_suffix}"

    def validate(self, series: pd.Series) -> dict[str, Any]:
        """Validate computed feature against spec."""
        results = {"valid": True, "issues": []}

        clean = series.dropna()

        # Check bounds
        if self.bounded:
            if self.expected_min is not None and clean.min() < self.expected_min - 0.01:
                results["issues"].append(
                    f"Below expected min: {clean.min():.4f} < {self.expected_min}"
                )
                results["valid"] = False
            if self.expected_max is not None and clean.max() > self.expected_max + 0.01:
                results["issues"].append(
                    f"Above expected max: {clean.max():.4f} > {self.expected_max}"
                )
                results["valid"] = False

        # Check for infinite values
        if np.isinf(clean).any():
            results["issues"].append("Contains infinite values")
            results["valid"] = False

        # Check for constant values
        if clean.std() < 1e-10:
            results["issues"].append("Constant feature (std < 1e-10)")
            results["valid"] = False

        return results


# =============================================================================
# FEATURE REGISTRY
# =============================================================================


class FeatureRegistry:
    """Central registry for all features."""

    def __init__(self):
        self._features: dict[str, FeatureSpec] = {}
        self._by_domain: dict[str, list[str]] = {}

    def register(self, spec: FeatureSpec) -> None:
        """Register a feature specification."""
        self._features[spec.name] = spec

        # Index by domain
        if spec.domain not in self._by_domain:
            self._by_domain[spec.domain] = []
        self._by_domain[spec.domain].append(spec.name)

    def get(self, name: str) -> FeatureSpec | None:
        """Get feature spec by name."""
        return self._features.get(name)

    def list_features(self) -> list[str]:
        """List all registered feature names."""
        return list(self._features.keys())

    def list_by_domain(self, domain: str) -> list[str]:
        """List features in a domain."""
        return self._by_domain.get(domain, [])

    def list_domains(self) -> list[str]:
        """List all domains."""
        return list(self._by_domain.keys())

    def get_all_full_names(self) -> list[str]:
        """Get all feature column names that will be generated."""
        names = []
        for spec in self._features.values():
            if spec.periods:
                for n in spec.periods:
                    names.append(spec.full_name(period=n))
            elif spec.period_pairs:
                for pair in spec.period_pairs:
                    names.append(spec.full_name(period_pair=pair))
            else:
                names.append(spec.full_name())
        return names

    def compute_all(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute all registered features."""
        features = pd.DataFrame()
        features["timestamp"] = df["timestamp"]

        for spec in self._features.values():
            if spec.compute_fn is None:
                continue

            try:
                if spec.periods:
                    for n in spec.periods:
                        col_name = spec.full_name(period=n)
                        features[col_name] = spec.compute_fn(df, n)
                elif spec.period_pairs:
                    for pair in spec.period_pairs:
                        col_name = spec.full_name(period_pair=pair)
                        features[col_name] = spec.compute_fn(df, pair[0], pair[1])
                else:
                    col_name = spec.full_name()
                    features[col_name] = spec.compute_fn(df)
            except Exception as e:
                print(f"Error computing {spec.name}: {e}")

        return features

    def validate_all(self, features: pd.DataFrame) -> dict[str, dict]:
        """Validate all computed features against specs."""
        results = {}

        for spec in self._features.values():
            if spec.periods:
                for n in spec.periods:
                    col_name = spec.full_name(period=n)
                    if col_name in features.columns:
                        results[col_name] = spec.validate(features[col_name])
            elif spec.period_pairs:
                for pair in spec.period_pairs:
                    col_name = spec.full_name(period_pair=pair)
                    if col_name in features.columns:
                        results[col_name] = spec.validate(features[col_name])
            else:
                col_name = spec.full_name()
                if col_name in features.columns:
                    results[col_name] = spec.validate(features[col_name])

        return results

    def summary(self) -> pd.DataFrame:
        """Get summary of all registered features."""
        data = []
        for spec in self._features.values():
            n_features = 1
            if spec.periods:
                n_features = len(spec.periods)
            elif spec.period_pairs:
                n_features = len(spec.period_pairs)

            data.append(
                {
                    "name": spec.name,
                    "domain": spec.domain,
                    "form": spec.form,
                    "groups": spec.groups,
                    "periods": spec.periods or spec.period_pairs or [None],
                    "n_columns": n_features,
                    "bounded": spec.bounded,
                    "approved": spec.approved_date,
                }
            )

        return pd.DataFrame(data)


# Global registry instance
REGISTRY = FeatureRegistry()


# =============================================================================
# DECORATOR FOR EASY REGISTRATION
# =============================================================================


def register_feature(
    name: str,
    groups: str,
    form: str,
    domain: str,
    normalized: bool = True,
    periods: list[int] = None,
    period_pairs: list[tuple] = None,
    dependencies: list[str] = None,
    expected_min: float = None,
    expected_max: float = None,
    bounded: bool = False,
    formula: str = "",
    approved_date: str = "",
):
    """Decorator to register a feature computation function."""

    def decorator(fn: Callable):
        spec = FeatureSpec(
            name=name,
            groups=groups,
            form=form,
            domain=domain,
            normalized=normalized,
            compute_fn=fn,
            periods=periods,
            period_pairs=period_pairs,
            dependencies=dependencies or [],
            expected_min=expected_min,
            expected_max=expected_max,
            bounded=bounded,
            formula=formula,
            approved_date=approved_date,
        )
        REGISTRY.register(spec)
        return fn

    return decorator


# =============================================================================
# EXAMPLE: REGISTERING A FEATURE
# =============================================================================

# This is how to add a new feature - just define function with decorator:
#
# @register_feature(
#     name='newIndicator',
#     groups='M_P',
#     form='pct',
#     domain='Momentum',
#     periods=[3, 6, 12],
#     formula='(close - close_{t-n}) / close_{t-n}',
#     approved_date='2025-12-20'
# )
# def compute_new_indicator(df, n):
#     return (df['close'] - df['close'].shift(n)) / df['close'].shift(n)


# =============================================================================
# USAGE EXAMPLE
# =============================================================================

if __name__ == "__main__":
    print("Feature Registry Module")
    print("=" * 60)
    print("\nTo use this module:")
    print("1. Import: from feature_registry import REGISTRY, register_feature")
    print("2. Define features with @register_feature decorator")
    print("3. Compute: features = REGISTRY.compute_all(df)")
    print("4. Validate: results = REGISTRY.validate_all(features)")
