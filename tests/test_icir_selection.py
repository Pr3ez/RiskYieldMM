"""Unit tests for ICIR feature selection module.

Tests:
1. compute_single_ic - Spearman correlation computation
2. compute_rolling_icir - Rolling ICIR stability metric
3. apply_correlation_filter - Redundancy removal
4. select_features_full_pipeline - End-to-end selection
"""

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("polars")

from scripts.target_models.helpers.icir_config import (
    DEFAULT_ICIR_CONFIG,
    ICIR_CONFIG_DISABLED,
    ICIRConfig,
)
from scripts.target_models.helpers.icir_selection import (
    apply_correlation_filter,
    compute_rolling_icir,
    compute_single_ic,
    select_features_by_icir,
    select_features_full_pipeline,
)


class TestComputeSingleIC:
    """Tests for compute_single_ic function."""

    def test_perfect_positive_correlation(self):
        """Perfect positive correlation should return IC ≈ 1."""
        feature = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        target = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        ic = compute_single_ic(feature, target)
        assert ic is not None
        assert abs(ic - 1.0) < 0.01

    def test_perfect_negative_correlation(self):
        """Perfect negative correlation should return IC ≈ -1."""
        feature = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        target = np.array([10, 9, 8, 7, 6, 5, 4, 3, 2, 1])
        ic = compute_single_ic(feature, target)
        assert ic is not None
        assert abs(ic + 1.0) < 0.01

    def test_no_correlation(self):
        """Random data should have IC ≈ 0."""
        np.random.seed(42)
        feature = np.random.randn(100)
        target = np.random.randn(100)
        ic = compute_single_ic(feature, target)
        assert ic is not None
        assert abs(ic) < 0.3  # Should be small

    def test_insufficient_samples(self):
        """Should return None if < min_samples."""
        feature = np.array([1, 2, 3])
        target = np.array([1, 2, 3])
        ic = compute_single_ic(feature, target, min_samples=10)
        assert ic is None

    def test_handles_nan_values(self):
        """Should exclude NaN values from computation."""
        feature = np.array([1, 2, np.nan, 4, 5, 6, 7, 8, 9, 10])
        target = np.array([1, 2, 3, 4, 5, np.nan, 7, 8, 9, 10])
        ic = compute_single_ic(feature, target, min_samples=5)
        assert ic is not None


class TestComputeRollingICIR:
    """Tests for compute_rolling_icir function."""

    def test_consistent_feature_has_high_icir(self):
        """A consistently predictive feature should have high ICIR."""
        np.random.seed(42)
        n_samples = 500

        # Feature that's consistently correlated with target
        target = np.random.randn(n_samples)
        feature = target * 0.8 + np.random.randn(n_samples) * 0.2

        features = pd.DataFrame({"consistent": feature})
        config = ICIRConfig(
            n_rolling_windows=5, min_window_size=50, min_valid_windows=3
        )

        results = compute_rolling_icir(features, target, config)

        assert "consistent" in results
        assert results["consistent"]["icir"] is not None
        assert results["consistent"]["icir"] > 0.5  # High ICIR

    def test_unstable_feature_has_low_icir(self):
        """Feature with sign-flipping correlation should have low ICIR."""
        np.random.seed(42)
        n_samples = 500

        target = np.random.randn(n_samples)
        # Feature that flips sign every window
        feature = np.zeros(n_samples)
        for i in range(5):
            start = i * 100
            end = (i + 1) * 100
            sign = 1 if i % 2 == 0 else -1
            feature[start:end] = target[start:end] * sign + np.random.randn(100) * 0.3

        features = pd.DataFrame({"unstable": feature})
        config = ICIRConfig(
            n_rolling_windows=5, min_window_size=50, min_valid_windows=3
        )

        results = compute_rolling_icir(features, target, config)

        assert "unstable" in results
        # ICIR should be lower due to inconsistency
        assert results["unstable"]["icir"] is not None
        assert abs(results["unstable"]["icir"]) < 2  # Lower than consistent feature

    def test_insufficient_data_returns_none(self):
        """Should return None ICIR if insufficient data."""
        features = pd.DataFrame({"f1": [1, 2, 3, 4, 5]})
        target = np.array([1, 2, 3, 4, 5])
        config = ICIRConfig(n_rolling_windows=5, min_window_size=50)

        results = compute_rolling_icir(features, target, config)

        assert results["f1"]["icir"] is None
        assert results["f1"]["n_valid_windows"] == 0


class TestApplyCorrelationFilter:
    """Tests for apply_correlation_filter function."""

    def test_removes_highly_correlated_feature(self):
        """Should remove one of two highly correlated features."""
        np.random.seed(42)
        n_samples = 100

        base = np.random.randn(n_samples)
        features = pd.DataFrame(
            {
                "f1": base,
                "f2": base + np.random.randn(n_samples) * 0.01,  # ~99% corr with f1
                "f3": np.random.randn(n_samples),  # Independent
            }
        )

        # f1 has higher ICIR than f2
        icir_results = {
            "f1": {"icir": 0.6},
            "f2": {"icir": 0.4},
            "f3": {"icir": 0.5},
        }

        config = ICIRConfig(correlation_threshold=0.90)

        kept, dropped = apply_correlation_filter(features, icir_results, config)

        assert "f1" in kept  # Higher ICIR, should be kept
        assert "f2" in dropped  # Correlated with f1, lower ICIR
        assert "f3" in kept  # Independent

    def test_keeps_uncorrelated_features(self):
        """Should keep all uncorrelated features."""
        np.random.seed(42)
        n_samples = 100

        features = pd.DataFrame(
            {
                "f1": np.random.randn(n_samples),
                "f2": np.random.randn(n_samples),
                "f3": np.random.randn(n_samples),
            }
        )

        icir_results = {
            "f1": {"icir": 0.3},
            "f2": {"icir": 0.4},
            "f3": {"icir": 0.5},
        }

        config = ICIRConfig(correlation_threshold=0.90)

        kept, dropped = apply_correlation_filter(features, icir_results, config)

        assert len(kept) == 3
        assert len(dropped) == 0


class TestSelectFeaturesByICIR:
    """Tests for select_features_by_icir function."""

    def test_selects_features_above_threshold(self):
        """Should select features with |ICIR| >= threshold."""
        icir_results = {
            "f1": {"icir": 0.5},
            "f2": {"icir": 0.2},  # Below threshold
            "f3": {"icir": -0.4},  # Negative but above threshold
            "f4": {"icir": None},  # Invalid
        }

        config = ICIRConfig(icir_threshold=0.3)

        selected = select_features_by_icir(icir_results, config)

        assert "f1" in selected
        assert "f2" not in selected
        assert "f3" in selected
        assert "f4" not in selected

    def test_sorted_by_abs_icir(self):
        """Should return features sorted by |ICIR| descending."""
        icir_results = {
            "f1": {"icir": 0.3},
            "f2": {"icir": 0.6},
            "f3": {"icir": -0.5},
        }

        config = ICIRConfig(icir_threshold=0.2)

        selected = select_features_by_icir(icir_results, config)

        assert selected == ["f2", "f3", "f1"]


class TestSelectFeaturesPipeline:
    """Tests for select_features_full_pipeline function."""

    def test_full_pipeline_with_icir(self):
        """Full pipeline should select stable, predictive features."""
        np.random.seed(42)
        n_samples = 500

        target = np.random.randn(n_samples)
        features = pd.DataFrame(
            {
                # Strong, stable signal - should be selected
                "good_signal": target * 0.9 + np.random.randn(n_samples) * 0.1,
            }
        )

        config = ICIRConfig(
            enable_icir=True,
            enable_correlation_filter=True,
            icir_threshold=0.3,
            correlation_threshold=0.90,
        )

        result = select_features_full_pipeline(features, target, config)

        assert result["method"] == "icir"
        assert len(result["selected_features"]) > 0
        assert "good_signal" in result["selected_features"]

    def test_fallback_to_ic_when_disabled(self):
        """Should use IC fallback when ICIR disabled."""
        np.random.seed(42)
        n_samples = 100

        target = np.random.randn(n_samples)
        features = pd.DataFrame(
            {
                "f1": target * 0.8 + np.random.randn(n_samples) * 0.2,
                "f2": np.random.randn(n_samples),
            }
        )

        result = select_features_full_pipeline(features, target, ICIR_CONFIG_DISABLED)

        assert result["method"] == "ic_fallback"
        assert "f1" in result["selected_features"]

    def test_fallback_when_insufficient_data(self):
        """Should fall back to IC when not enough data for ICIR."""
        target = np.array([1, 2, 3, 4, 5])
        features = pd.DataFrame({"f1": [1, 2, 3, 4, 5]})

        config = ICIRConfig(
            enable_icir=True,
            fallback_to_ic=True,
            n_rolling_windows=5,
            min_window_size=50,
        )

        result = select_features_full_pipeline(features, target, config)

        # Should fall back gracefully
        assert result["method"] in ["ic_fallback", "none"]


class TestICIRConfig:
    """Tests for ICIRConfig dataclass."""

    def test_default_values(self):
        """Default config should have expected values."""
        config = DEFAULT_ICIR_CONFIG
        assert config.enable_icir is True
        assert config.icir_threshold == 0.3
        assert config.n_rolling_windows == 5
        assert config.correlation_threshold == 0.90

    def test_min_samples_required_property(self):
        """min_samples_required should be computed correctly."""
        config = ICIRConfig(n_rolling_windows=5, min_window_size=50)
        assert config.min_samples_required == 250

    def test_disabled_config(self):
        """Disabled config should turn off ICIR."""
        config = ICIR_CONFIG_DISABLED
        assert config.enable_icir is False
        assert config.fallback_to_ic is True

    def test_validation_rejects_invalid(self):
        """Should reject invalid configurations."""
        with pytest.raises(ValueError):
            ICIRConfig(icir_threshold=-0.1)

        with pytest.raises(ValueError):
            ICIRConfig(n_rolling_windows=1)

        with pytest.raises(ValueError):
            ICIRConfig(correlation_threshold=1.5)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
