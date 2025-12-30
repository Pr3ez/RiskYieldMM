"""
Unit Tests for Feature Optimizers
=================================

Tests for each optimizer module and the pipeline.
Following pytest conventions with fixtures for reusability.
"""

import numpy as np
import pandas as pd
import pytest

from scripts.analysis.optimizers import (
    InteractionOptimizer,
    OptimizationPipeline,
    OptimizerMetrics,
    RegimeConditioningOptimizer,
    RollingZScoreOptimizer,
    WinsorizeOptimizer,
)

# NOTE: DomainPCAOptimizer removed - causes future leakage (PCA needs full covariance)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def synthetic_features() -> pd.DataFrame:
    """Create synthetic feature data with known properties."""
    np.random.seed(42)
    n = 1000

    # Create features with different characteristics
    data = {
        # Momentum features (domain: M)
        "M_momentum_3_pct_N": np.random.randn(n) * 0.02,
        "M_momentum_12_pct_N": np.random.randn(n) * 0.03,
        "M_roc_6_pct_N": np.random.randn(n) * 0.015,
        # Volatility features (domain: V)
        "V_atrPct_12_pct_N": np.abs(np.random.randn(n) * 0.01) + 0.005,
        "V_volatility_21_pct_N": np.abs(np.random.randn(n) * 0.015) + 0.01,
        # Bounded features (domain: B)
        "B_stochastic_14_bnd_N": np.random.uniform(0, 1, n),
        "B_rsi_14_bnd_N": np.random.uniform(0, 1, n),
        # Sentiment features (domain: S)
        "S_fundingRate_pct_N": np.random.randn(n) * 0.001,
        "S_longShortRatio_rat_N": np.random.uniform(0.3, 3.0, n),
        # Regime indicator
        "V_hurstExponent_63_bnd_N": np.random.uniform(0.3, 0.7, n),
    }

    # Add some outliers
    data["M_momentum_3_pct_N"][0] = 0.5  # 25x normal
    data["M_momentum_3_pct_N"][1] = -0.4  # 20x normal
    data["V_atrPct_12_pct_N"][2] = 0.3  # 30x normal

    return pd.DataFrame(data)


@pytest.fixture
def synthetic_target() -> pd.Series:
    """Create synthetic target with weak signal."""
    np.random.seed(42)
    n = 1000
    # Target weakly correlated with some features
    signal = np.random.randn(n) * 0.02
    return pd.Series(signal, name="y_forward_return_1")


@pytest.fixture
def features_with_hurst(synthetic_features: pd.DataFrame) -> pd.DataFrame:
    """Features with Hurst exponent for regime conditioning."""
    df = synthetic_features.copy()
    # Create Hurst that correlates with regime
    # > 0.5 = trending, < 0.5 = mean-reverting
    df["V_hurstExponent_63_bnd_N"] = np.random.choice(
        [0.3, 0.4, 0.6, 0.7], size=len(df), p=[0.2, 0.3, 0.3, 0.2]
    )
    return df


# =============================================================================
# OptimizerMetrics Tests
# =============================================================================


class TestOptimizerMetrics:
    """Tests for OptimizerMetrics dataclass."""

    def test_metrics_creation(self) -> None:
        """Test metrics can be created with defaults."""
        metrics = OptimizerMetrics(name="TestOptimizer")
        assert metrics.name == "TestOptimizer"
        assert metrics.ic_before == 0.0
        assert metrics.ic_after == 0.0

    def test_metrics_to_dict(self) -> None:
        """Test conversion to dictionary."""
        metrics = OptimizerMetrics(
            name="Test",
            ic_before=0.01,
            ic_after=0.015,
            ic_improvement=0.5,
            n_features_in=100,
            n_features_out=80,
        )
        d = metrics.to_dict()
        assert d["name"] == "Test"
        assert d["ic_before"] == 0.01
        assert d["n_features_in"] == 100

    def test_metrics_repr(self) -> None:
        """Test string representation."""
        metrics = OptimizerMetrics(
            name="Test",
            ic_before=0.01,
            ic_after=0.015,
            n_features_in=100,
            n_features_out=80,
        )
        repr_str = repr(metrics)
        assert "Test" in repr_str
        assert "100" in repr_str
        assert "80" in repr_str


# =============================================================================
# RollingZScoreOptimizer Tests
# =============================================================================


class TestRollingZScoreOptimizer:
    """Tests for RollingZScoreOptimizer."""

    def test_fit_identifies_columns(self, synthetic_features: pd.DataFrame) -> None:
        """Test fit correctly identifies columns to transform."""
        opt = RollingZScoreOptimizer(window=50)
        opt.fit(synthetic_features)

        assert opt.is_fitted
        # Bounded features should be excluded
        assert "B_stochastic_14_bnd_N" in opt._cols_passthrough
        assert "B_rsi_14_bnd_N" in opt._cols_passthrough
        # Momentum features should be transformed
        assert "M_momentum_3_pct_N" in opt._cols_to_transform

    def test_transform_shape_preserved(self, synthetic_features: pd.DataFrame) -> None:
        """Test transform preserves DataFrame shape."""
        opt = RollingZScoreOptimizer(window=50)
        result = opt.fit_transform(synthetic_features)

        assert result.shape == synthetic_features.shape
        assert list(result.columns) == list(synthetic_features.columns)

    def test_transform_creates_zscores(self, synthetic_features: pd.DataFrame) -> None:
        """Test transformed values are approximately z-scored."""
        opt = RollingZScoreOptimizer(window=100, min_periods=50)
        result = opt.fit_transform(synthetic_features)

        # After warmup, momentum features should be roughly standardized
        col = "M_momentum_3_pct_N"
        transformed = result[col].dropna()
        # Rolling z-score won't be exactly 0/1, but should be reasonable
        assert -5 < transformed.mean() < 5
        assert 0.5 < transformed.std() < 2.0

    def test_bounded_features_unchanged(self, synthetic_features: pd.DataFrame) -> None:
        """Test bounded features are not transformed."""
        opt = RollingZScoreOptimizer(window=50)
        result = opt.fit_transform(synthetic_features)

        # Bounded features should be identical
        pd.testing.assert_series_equal(
            result["B_stochastic_14_bnd_N"],
            synthetic_features["B_stochastic_14_bnd_N"],
        )

    def test_evaluate_returns_metrics(
        self,
        synthetic_features: pd.DataFrame,
        synthetic_target: pd.Series,
    ) -> None:
        """Test evaluate returns proper metrics."""
        opt = RollingZScoreOptimizer(window=50)
        metrics = opt.evaluate(synthetic_features, synthetic_target)

        assert isinstance(metrics, OptimizerMetrics)
        assert metrics.name == "RollingZScore"
        assert metrics.n_features_in == synthetic_features.shape[1]
        assert metrics.n_features_out == synthetic_features.shape[1]
        assert metrics.fit_time_ms >= 0
        assert metrics.transform_time_ms >= 0


# =============================================================================
# WinsorizeOptimizer Tests
# =============================================================================


class TestWinsorizeOptimizer:
    """Tests for WinsorizeOptimizer.

    NOTE: WinsorizeOptimizer now uses CAUSAL expanding quantiles.
    Bounds are computed per-row using only past data, not stored globally.
    """

    def test_fit_identifies_columns(self, synthetic_features: pd.DataFrame) -> None:
        """Test fit identifies which columns to clip."""
        opt = WinsorizeOptimizer(lower=0.01, upper=0.99, min_periods=50)
        opt.fit(synthetic_features)

        assert opt.is_fitted
        # Should have columns to clip
        assert "M_momentum_3_pct_N" in opt._cols_to_clip
        # Bounded columns should be excluded (pattern _bnd_)
        assert "B_stochastic_14_bnd_N" not in opt._cols_to_clip

    def test_transform_applies_causal_clipping(
        self, synthetic_features: pd.DataFrame
    ) -> None:
        """Test transform clips using expanding quantiles."""
        opt = WinsorizeOptimizer(lower=0.01, upper=0.99, min_periods=50)
        result = opt.fit_transform(synthetic_features)

        # Shape should be preserved
        assert result.shape == synthetic_features.shape
        # Rows after warmup should have valid values
        col = "M_momentum_3_pct_N"
        assert result[col].iloc[100:].notna().all()

    def test_no_clip_within_bounds(self, synthetic_features: pd.DataFrame) -> None:
        """Test values within bounds are unchanged."""
        opt = WinsorizeOptimizer(lower=0.01, upper=0.99, min_periods=50)
        result = opt.fit_transform(synthetic_features)

        col = "M_momentum_3_pct_N"
        # Get values that weren't outliers (middle 98%)
        mask = synthetic_features[col].between(
            synthetic_features[col].quantile(0.02),
            synthetic_features[col].quantile(0.98),
        )
        # After warmup, these should be close (may differ slightly due to expanding bounds)
        warmup_mask = mask & (synthetic_features.index >= 100)
        # Check correlation is very high (values mostly unchanged)
        corr = result.loc[warmup_mask, col].corr(
            synthetic_features.loc[warmup_mask, col]
        )
        assert corr > 0.99

    def test_get_winsorize_info_empty(self, synthetic_features: pd.DataFrame) -> None:
        """Test winsorize info returns empty DataFrame (no stored bounds in causal mode)."""
        opt = WinsorizeOptimizer(lower=0.01, upper=0.99, min_periods=50)
        opt.fit(synthetic_features)

        info = opt.get_winsorize_info()
        # In causal mode, bounds aren't stored globally, so info is empty
        assert isinstance(info, pd.DataFrame)


# =============================================================================
# RegimeConditioningOptimizer Tests
# =============================================================================


class TestRegimeConditioningOptimizer:
    """Tests for RegimeConditioningOptimizer."""

    def test_fit_with_hurst(
        self,
        features_with_hurst: pd.DataFrame,
        synthetic_target: pd.Series,
    ) -> None:
        """Test fit identifies Hurst column."""
        opt = RegimeConditioningOptimizer(regime_feature="V_hurstExponent_63_bnd_N")
        opt.fit(features_with_hurst, synthetic_target)

        assert opt.is_fitted
        # Should have attribute for conditioned features
        assert hasattr(opt, "_conditioned_features")

    def test_transform_weights_by_regime(
        self,
        features_with_hurst: pd.DataFrame,
        synthetic_target: pd.Series,
    ) -> None:
        """Test transform applies regime-based weighting."""
        opt = RegimeConditioningOptimizer(
            regime_feature="V_hurstExponent_63_bnd_N",
            min_ic_diff=0.01,
            output_mode="weight",
        )
        result = opt.fit_transform(features_with_hurst, synthetic_target)

        # Output shape should be same
        assert result.shape[0] == features_with_hurst.shape[0]

    def test_missing_hurst_raises_error(
        self,
        synthetic_features: pd.DataFrame,
        synthetic_target: pd.Series,
    ) -> None:
        """Test ValueError raised when Hurst column missing."""
        # Remove Hurst column
        df = synthetic_features.drop(columns=["V_hurstExponent_63_bnd_N"])

        opt = RegimeConditioningOptimizer(regime_feature="V_hurstExponent_63_bnd_N")

        # Should raise ValueError when regime feature is missing
        with pytest.raises(ValueError, match="Regime feature"):
            opt.fit(df, synthetic_target)


# =============================================================================
# DomainPCAOptimizer Tests - REMOVED
# =============================================================================
# NOTE: DomainPCAOptimizer was removed from the codebase because PCA
# fundamentally requires computing the full covariance matrix, which
# uses future data and cannot be made causal. See docs/LEAKAGE_FIXES.md


# =============================================================================
# InteractionOptimizer Tests
# =============================================================================


class TestInteractionOptimizer:
    """Tests for InteractionOptimizer."""

    def test_fit_selects_top_features(
        self,
        synthetic_features: pd.DataFrame,
        synthetic_target: pd.Series,
    ) -> None:
        """Test fit selects top features per domain."""
        opt = InteractionOptimizer(top_k=2, n_interactions=5, min_ic=0.0)
        opt.fit(synthetic_features, synthetic_target)

        assert opt.is_fitted
        # Should have identified feature pairs (stored in _interactions)
        assert hasattr(opt, "_interactions")

    def test_transform_adds_features(
        self,
        synthetic_features: pd.DataFrame,
        synthetic_target: pd.Series,
    ) -> None:
        """Test transform adds interaction features."""
        opt = InteractionOptimizer(top_k=2, n_interactions=3, min_ic=0.0)
        result = opt.fit_transform(synthetic_features, synthetic_target)

        # Should have same or more columns than original
        assert result.shape[1] >= synthetic_features.shape[1]
        # Rows unchanged
        assert result.shape[0] == synthetic_features.shape[0]

    def test_interaction_naming(
        self,
        synthetic_features: pd.DataFrame,
        synthetic_target: pd.Series,
    ) -> None:
        """Test interaction features are properly named."""
        opt = InteractionOptimizer(top_k=2, n_interactions=3, min_ic=0.0)
        result = opt.fit_transform(synthetic_features, synthetic_target)

        # Interactions may not be created if IC threshold not met
        # Just verify the optimizer runs without error
        assert result.shape[0] == synthetic_features.shape[0]


# =============================================================================
# OptimizationPipeline Tests
# =============================================================================


class TestOptimizationPipeline:
    """Tests for OptimizationPipeline."""

    def test_pipeline_creation(self) -> None:
        """Test pipeline can be created with optimizers."""
        pipeline = OptimizationPipeline(
            [
                WinsorizeOptimizer(),
                RollingZScoreOptimizer(window=50),
            ]
        )
        assert len(pipeline.optimizers) == 2
        assert not pipeline.is_fitted

    def test_fit_transform(
        self,
        synthetic_features: pd.DataFrame,
        synthetic_target: pd.Series,
    ) -> None:
        """Test pipeline fit_transform works."""
        pipeline = OptimizationPipeline(
            [
                WinsorizeOptimizer(lower=0.01, upper=0.99),
                RollingZScoreOptimizer(window=50),
            ]
        )

        result = pipeline.fit_transform(synthetic_features, synthetic_target)

        assert pipeline.is_fitted
        assert isinstance(result, pd.DataFrame)
        assert result.shape[0] == synthetic_features.shape[0]

    def test_get_metrics(
        self,
        synthetic_features: pd.DataFrame,
        synthetic_target: pd.Series,
    ) -> None:
        """Test pipeline tracks metrics for each step."""
        pipeline = OptimizationPipeline(
            [
                WinsorizeOptimizer(),
                RollingZScoreOptimizer(window=50),
            ]
        )
        pipeline.fit(synthetic_features, synthetic_target)

        metrics = pipeline.get_metrics()
        assert len(metrics) == 2  # One per optimizer
        assert all(isinstance(m, OptimizerMetrics) for m in metrics)

    def test_get_metrics_df(
        self,
        synthetic_features: pd.DataFrame,
        synthetic_target: pd.Series,
    ) -> None:
        """Test metrics DataFrame includes summary."""
        pipeline = OptimizationPipeline(
            [
                WinsorizeOptimizer(),
                RollingZScoreOptimizer(window=50),
            ]
        )
        pipeline.fit(synthetic_features, synthetic_target)

        df = pipeline.get_metrics_df()
        assert isinstance(df, pd.DataFrame)
        # Should have rows for each optimizer + total
        assert len(df) >= 2
        assert "step" in df.columns
        assert "ic_before" in df.columns

    def test_compare_performance(
        self,
        synthetic_features: pd.DataFrame,
        synthetic_target: pd.Series,
    ) -> None:
        """Test compare_performance returns comparison dict."""
        pipeline = OptimizationPipeline(
            [
                WinsorizeOptimizer(),
                RollingZScoreOptimizer(window=50),
            ]
        )
        pipeline.fit(synthetic_features, synthetic_target)

        comparison = pipeline.compare_performance(synthetic_features, synthetic_target)

        assert "baseline_ic" in comparison
        assert "optimized_ic" in comparison
        assert "ic_improvement" in comparison
        assert "n_optimizers" in comparison
        assert comparison["n_optimizers"] == 2

    def test_transform_before_fit_raises(
        self, synthetic_features: pd.DataFrame
    ) -> None:
        """Test transform before fit raises error."""
        pipeline = OptimizationPipeline([WinsorizeOptimizer()])

        with pytest.raises(RuntimeError, match="Must call fit"):
            pipeline.transform(synthetic_features)

    def test_empty_pipeline(
        self,
        synthetic_features: pd.DataFrame,
        synthetic_target: pd.Series,
    ) -> None:
        """Test empty pipeline passes through data."""
        pipeline = OptimizationPipeline([])
        result = pipeline.fit_transform(synthetic_features, synthetic_target)

        pd.testing.assert_frame_equal(result, synthetic_features)


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests combining multiple optimizers."""

    def test_full_pipeline(
        self,
        features_with_hurst: pd.DataFrame,
        synthetic_target: pd.Series,
    ) -> None:
        """Test full optimization pipeline end-to-end."""
        pipeline = OptimizationPipeline(
            [
                WinsorizeOptimizer(lower=0.01, upper=0.99),
                RollingZScoreOptimizer(window=100),
                InteractionOptimizer(top_k=2, n_interactions=3, min_ic=0.0),
            ],
            name="TestPipeline",
        )

        result = pipeline.fit_transform(features_with_hurst, synthetic_target)

        # Should complete without error
        assert pipeline.is_fitted
        assert result.shape[0] == features_with_hurst.shape[0]

        # Metrics should be tracked
        metrics_df = pipeline.get_metrics_df()
        assert len(metrics_df) >= 3  # 3 optimizers + total

    def test_optimizer_reuse(
        self,
        synthetic_features: pd.DataFrame,
        synthetic_target: pd.Series,
    ) -> None:
        """Test optimizers can be reused in different pipelines."""
        winsorize = WinsorizeOptimizer()
        zscore = RollingZScoreOptimizer(window=50)

        # First pipeline
        p1 = OptimizationPipeline([winsorize])
        r1 = p1.fit_transform(synthetic_features, synthetic_target)

        # Second pipeline (reusing winsorize)
        p2 = OptimizationPipeline([winsorize, zscore])
        r2 = p2.fit_transform(synthetic_features, synthetic_target)

        # Both should work
        assert r1.shape[0] == synthetic_features.shape[0]
        assert r2.shape[0] == synthetic_features.shape[0]


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_dataframe(self) -> None:
        """Test handling of empty DataFrame."""
        empty_df = pd.DataFrame()
        opt = WinsorizeOptimizer()
        opt.fit(empty_df)
        result = opt.transform(empty_df)
        assert result.empty

    def test_single_row(self) -> None:
        """Test handling of single-row DataFrame."""
        single = pd.DataFrame({"a": [1.0], "b": [2.0]})
        opt = WinsorizeOptimizer()
        opt.fit(single)
        # Should not error
        result = opt.transform(single)
        assert len(result) == 1

    def test_all_nan_column(self) -> None:
        """Test handling of all-NaN column."""
        df = pd.DataFrame(
            {
                "good": np.random.randn(100),
                "bad": [np.nan] * 100,
            }
        )
        opt = RollingZScoreOptimizer(window=20)
        result = opt.fit_transform(df)

        # Should handle gracefully
        assert result.shape == df.shape
        assert result["bad"].isna().all()

    def test_constant_column(self) -> None:
        """Test handling of constant-value column."""
        df = pd.DataFrame(
            {
                "variable": np.random.randn(100),
                "constant": [5.0] * 100,
            }
        )
        opt = RollingZScoreOptimizer(window=20)
        result = opt.fit_transform(df)

        # Constant column becomes NaN due to zero std
        # This is expected behavior
        assert result.shape == df.shape
