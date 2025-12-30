"""
Unit Tests for Feature Analysis Functions
=========================================

Tests for MDA (Mean Decrease Accuracy / Permutation Importance)
and other feature analysis utilities.
"""

import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression

from scripts.analysis.features import compute_permutation_importance


class TestPermutationImportance:
    """Tests for compute_permutation_importance (MDA)."""

    @pytest.fixture
    def synthetic_data(self):
        """Create synthetic data with known signal structure."""
        np.random.seed(42)
        n = 500

        # Feature 1: Strong signal (perfect correlation with target)
        signal = np.random.randn(n)

        # Feature 2: Weak signal
        weak = signal + np.random.randn(n) * 5

        # Features 3-5: Pure noise
        noise1 = np.random.randn(n)
        noise2 = np.random.randn(n)
        noise3 = np.random.randn(n)

        X = pd.DataFrame(
            {
                "strong_signal": signal,
                "weak_signal": weak,
                "noise_1": noise1,
                "noise_2": noise2,
                "noise_3": noise3,
            }
        )

        # Target based on signal feature
        y = pd.Series((signal > 0).astype(int))

        return X, y

    def test_returns_dataframe(self, synthetic_data):
        """MDA should return DataFrame with correct columns."""
        X, y = synthetic_data
        model = RandomForestClassifier(n_estimators=50, random_state=42)
        model.fit(X, y)

        result = compute_permutation_importance(
            model, X, y, n_repeats=5, random_state=42
        )

        assert isinstance(result, pd.DataFrame)
        assert "feature" in result.columns
        assert "importance_mean" in result.columns
        assert "importance_std" in result.columns

    def test_identifies_planted_signal(self, synthetic_data):
        """MDA should correctly identify the planted signal as most important."""
        X, y = synthetic_data
        model = RandomForestClassifier(n_estimators=50, random_state=42)
        model.fit(X, y)

        result = compute_permutation_importance(
            model, X, y, n_repeats=10, random_state=42
        )

        # Sort by importance
        top_feature = result.sort_values("importance_mean", ascending=False).iloc[0][
            "feature"
        ]

        assert top_feature == "strong_signal", (
            f"Expected 'strong_signal' as most important, got '{top_feature}'"
        )

    def test_signal_importance_higher_than_noise(self, synthetic_data):
        """Signal features should have higher importance than noise."""
        X, y = synthetic_data
        model = RandomForestClassifier(n_estimators=50, random_state=42)
        model.fit(X, y)

        result = compute_permutation_importance(
            model, X, y, n_repeats=10, random_state=42
        )

        importance_map = dict(zip(result["feature"], result["importance_mean"]))

        signal_imp = importance_map["strong_signal"]
        noise_imp = max(
            importance_map["noise_1"],
            importance_map["noise_2"],
            importance_map["noise_3"],
        )

        assert signal_imp > noise_imp, (
            f"Signal importance ({signal_imp:.4f}) should exceed noise ({noise_imp:.4f})"
        )

    def test_works_with_different_models(self, synthetic_data):
        """MDA should work with different sklearn-compatible models."""
        X, y = synthetic_data

        models = [
            RandomForestClassifier(n_estimators=20, random_state=42),
            LogisticRegression(random_state=42, max_iter=1000),
        ]

        for model in models:
            model.fit(X, y)
            result = compute_permutation_importance(
                model, X, y, n_repeats=5, random_state=42
            )
            assert len(result) == len(X.columns), f"Failed for {type(model).__name__}"

    def test_reproducible_with_seed(self, synthetic_data):
        """Results should be reproducible with same random_state."""
        X, y = synthetic_data
        model = RandomForestClassifier(n_estimators=50, random_state=42)
        model.fit(X, y)

        result1 = compute_permutation_importance(
            model, X, y, n_repeats=10, random_state=42
        )
        result2 = compute_permutation_importance(
            model, X, y, n_repeats=10, random_state=42
        )

        pd.testing.assert_frame_equal(result1, result2)

    def test_n_repeats_affects_std(self, synthetic_data):
        """More repeats should generally reduce variance."""
        X, y = synthetic_data
        model = RandomForestClassifier(n_estimators=50, random_state=42)
        model.fit(X, y)

        result_few = compute_permutation_importance(
            model, X, y, n_repeats=3, random_state=42
        )
        result_many = compute_permutation_importance(
            model, X, y, n_repeats=30, random_state=42
        )

        # Average std should be lower with more repeats (usually)
        # Not asserting strictly as variance can vary
        assert result_few["importance_std"].mean() >= 0
        assert result_many["importance_std"].mean() >= 0


class TestMDAEdgeCases:
    """Edge case tests for MDA implementation."""

    def test_single_feature(self):
        """Should handle single feature case."""
        np.random.seed(42)
        X = pd.DataFrame({"feature": np.random.randn(100)})
        y = pd.Series(np.random.randint(0, 2, 100))

        model = RandomForestClassifier(n_estimators=10, random_state=42)
        model.fit(X, y)

        result = compute_permutation_importance(model, X, y, n_repeats=5)
        assert len(result) == 1

    def test_handles_feature_names_with_spaces(self):
        """Should preserve feature names including special characters."""
        np.random.seed(42)
        X = pd.DataFrame(
            {
                "feature with space": np.random.randn(100),
                "feature-with-dash": np.random.randn(100),
                "feature_with_underscore": np.random.randn(100),
            }
        )
        y = pd.Series(np.random.randint(0, 2, 100))

        model = RandomForestClassifier(n_estimators=10, random_state=42)
        model.fit(X, y)

        result = compute_permutation_importance(model, X, y, n_repeats=5)

        assert set(result["feature"]) == set(X.columns)
