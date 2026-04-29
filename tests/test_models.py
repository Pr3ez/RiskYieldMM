"""
Unit Tests for Model Training and Cross-Validation
==================================================

Tests for PurgedKFold (temporal CV with purge/embargo)
and other model utilities.
"""

import numpy as np
import pandas as pd
import pytest
from sklearn.model_selection import TimeSeriesSplit

pytest.importorskip("polars")

from scripts.analysis.models import PurgedKFold


class TestPurgedKFold:
    """Tests for PurgedKFold cross-validator."""

    @pytest.fixture
    def sample_data(self):
        """Create sample time-series data."""
        n = 200
        dates = pd.date_range("2020-01-01", periods=n, freq="8h")
        X = pd.DataFrame(
            {
                "timestamp": dates,
                "feature1": np.random.randn(n),
                "feature2": np.random.randn(n),
            }
        )
        y = pd.Series(np.random.randint(0, 2, n))
        return X, y

    def test_returns_correct_number_of_folds(self, sample_data):
        """Should return exactly n_splits folds."""
        X, y = sample_data

        for n_splits in [3, 5, 10]:
            cv = PurgedKFold(n_splits=n_splits)
            folds = list(cv.split(X, y))
            assert len(folds) == n_splits, (
                f"Expected {n_splits} folds, got {len(folds)}"
            )

    def test_no_overlap_between_train_and_test(self, sample_data):
        """Train and test indices should never overlap."""
        X, y = sample_data
        cv = PurgedKFold(n_splits=5, purge_gap=10, embargo_gap=5)

        for fold, (train_idx, test_idx) in enumerate(cv.split(X, y)):
            overlap = set(train_idx) & set(test_idx)
            assert len(overlap) == 0, f"Fold {fold}: Train/test overlap: {overlap}"

    def test_purge_gap_respected(self, sample_data):
        """Purge gap before test set should be maintained."""
        X, y = sample_data
        PURGE_GAP = 15
        cv = PurgedKFold(n_splits=5, purge_gap=PURGE_GAP, embargo_gap=5)

        for fold, (train_idx, test_idx) in enumerate(cv.split(X, y)):
            test_start = min(test_idx)
            train_before_test = [i for i in train_idx if i < test_start]

            if train_before_test:
                max_train_before = max(train_before_test)
                gap = test_start - max_train_before - 1
                assert gap >= PURGE_GAP, (
                    f"Fold {fold}: Purge gap {gap} < required {PURGE_GAP}"
                )

    def test_embargo_gap_respected(self, sample_data):
        """Embargo gap after test set should be maintained."""
        X, y = sample_data
        EMBARGO_GAP = 10
        cv = PurgedKFold(n_splits=5, purge_gap=5, embargo_gap=EMBARGO_GAP)

        for fold, (train_idx, test_idx) in enumerate(cv.split(X, y)):
            test_end = max(test_idx)
            train_after_test = [i for i in train_idx if i > test_end]

            if train_after_test:
                min_train_after = min(train_after_test)
                gap = min_train_after - test_end - 1
                assert gap >= EMBARGO_GAP, (
                    f"Fold {fold}: Embargo gap {gap} < required {EMBARGO_GAP}"
                )

    def test_all_test_indices_covered(self, sample_data):
        """All samples should be in at least one test set (except edges)."""
        X, y = sample_data
        cv = PurgedKFold(n_splits=5, purge_gap=10, embargo_gap=5)

        all_test_idx = set()
        for _train_idx, test_idx in cv.split(X, y):
            all_test_idx.update(test_idx)

        # Should cover most of the data
        coverage = len(all_test_idx) / len(X)
        assert coverage > 0.5, f"Test coverage only {coverage:.1%}"

    def test_default_parameters(self, sample_data):
        """Should work with default parameters."""
        X, y = sample_data
        cv = PurgedKFold()

        assert cv.n_splits == 5
        # Defaults match project config (21 bars purge = max lookback, 12 bars embargo = max horizon)
        assert cv.purge_gap == 21
        assert cv.embargo_gap == 12

        folds = list(cv.split(X, y))
        assert len(folds) == 5


class TestPurgedKFoldVsTimeSeriesSplit:
    """Tests comparing PurgedKFold to standard TimeSeriesSplit."""

    @pytest.fixture
    def time_series_data(self):
        """Create data with temporal structure for leakage testing."""
        n = 300
        X = pd.DataFrame({"feature": np.random.randn(n)})
        y = pd.Series(np.random.randint(0, 2, n))
        return X, y

    def test_purged_has_larger_gaps(self, time_series_data):
        """PurgedKFold should have larger gaps than TimeSeriesSplit."""
        X, y = time_series_data

        # Standard TimeSeriesSplit
        tscv = TimeSeriesSplit(n_splits=5)
        ts_min_gaps = []
        for train_idx, test_idx in tscv.split(X, y):
            test_start = min(test_idx)
            train_end = max(train_idx)
            gap = test_start - train_end - 1
            ts_min_gaps.append(gap)

        # PurgedKFold
        purged_cv = PurgedKFold(n_splits=5, purge_gap=20, embargo_gap=10)
        purged_min_gaps = []
        for train_idx, test_idx in purged_cv.split(X, y):
            test_start = min(test_idx)
            train_before = [i for i in train_idx if i < test_start]
            if train_before:
                train_end = max(train_before)
                gap = test_start - train_end - 1
                purged_min_gaps.append(gap)

        # TimeSeriesSplit has gap=0 (contiguous)
        assert min(ts_min_gaps) == 0, "TimeSeriesSplit should have no gap"
        # PurgedKFold should have gap >= purge_gap
        if purged_min_gaps:
            assert min(purged_min_gaps) >= 20, (
                f"PurgedKFold gap {min(purged_min_gaps)} < required 20"
            )


class TestPurgedKFoldEdgeCases:
    """Edge case tests for PurgedKFold."""

    def test_small_dataset(self):
        """Should handle small datasets gracefully."""
        X = pd.DataFrame({"feature": np.random.randn(50)})
        y = pd.Series(np.random.randint(0, 2, 50))

        cv = PurgedKFold(n_splits=3, purge_gap=5, embargo_gap=3)
        folds = list(cv.split(X, y))

        assert len(folds) == 3
        for train_idx, test_idx in folds:
            assert len(train_idx) > 0
            assert len(test_idx) > 0

    def test_large_gaps_reduce_training_data(self):
        """Large gaps should result in smaller training sets."""
        n = 200
        X = pd.DataFrame({"feature": np.random.randn(n)})
        y = pd.Series(np.random.randint(0, 2, n))

        cv_small_gap = PurgedKFold(n_splits=5, purge_gap=5, embargo_gap=2)
        cv_large_gap = PurgedKFold(n_splits=5, purge_gap=20, embargo_gap=10)

        small_train_sizes = [len(train) for train, _ in cv_small_gap.split(X, y)]
        large_train_sizes = [len(train) for train, _ in cv_large_gap.split(X, y)]

        avg_small = np.mean(small_train_sizes)
        avg_large = np.mean(large_train_sizes)

        assert avg_large < avg_small, (
            f"Large gap should have smaller training: {avg_large} >= {avg_small}"
        )

    def test_zero_gaps_behaves_like_standard_kfold(self):
        """With zero gaps, should behave similar to expanding window."""
        X = pd.DataFrame({"feature": np.random.randn(100)})
        y = pd.Series(np.random.randint(0, 2, 100))

        cv = PurgedKFold(n_splits=5, purge_gap=0, embargo_gap=0)

        for train_idx, test_idx in cv.split(X, y):
            # Should still produce valid splits
            assert len(train_idx) > 0
            assert len(test_idx) > 0
            # No overlap even with zero gaps
            assert len(set(train_idx) & set(test_idx)) == 0

    def test_sklearn_compatible_interface(self):
        """Should be compatible with sklearn's cross-validation interface."""
        X = pd.DataFrame({"feature": np.random.randn(100)})
        y = pd.Series(np.random.randint(0, 2, 100))

        cv = PurgedKFold(n_splits=5)

        # Should have get_n_splits method
        assert hasattr(cv, "get_n_splits")
        assert cv.get_n_splits() == 5

        # Should be iterable
        folds = list(cv.split(X, y))
        assert len(folds) == 5
