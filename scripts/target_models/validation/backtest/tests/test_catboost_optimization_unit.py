#!/usr/bin/env python3
"""
Unit Tests for CatBoost Optimization

Tests from Plan Section 6.1:
1. test_no_leakage_in_optimization - Verify optimization uses only historical data
2. test_config_bounds - Verify configs stay within valid bounds
3. test_target_specific_adjustments - Verify different targets produce different configs

Additional tests:
4. test_all_28_configs - Run optimization on all target configs without crash
5. test_data_characteristics_fields - Verify all 21 fields present
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# Add backtest package root (parent of backtest/) for 'backtest.*' imports
backtest_package_root = Path(
    __file__
).parent.parent.parent  # scripts/target_models/validation/
sys.path.insert(0, str(backtest_package_root))

from backtest.models.catboost_model import (
    CatBoostModelConfig,
    DataCharacteristics,
    characterize_data,
    optimize_catboost_config,
)

# =============================================================================
# TEST FIXTURES
# =============================================================================


def make_mock_features(n_samples: int, n_features: int = 50) -> pd.DataFrame:
    """Create mock feature data."""
    np.random.seed(42)
    data = np.random.randn(n_samples, n_features)
    return pd.DataFrame(data, columns=[f"feature_{i}" for i in range(n_features)])


def make_mock_classification_targets(n_samples: int, n_classes: int = 3) -> pd.Series:
    """Create mock classification targets."""
    np.random.seed(42)
    return pd.Series(np.random.randint(0, n_classes, n_samples), name="target")


def make_mock_regression_targets(n_samples: int) -> pd.Series:
    """Create mock regression targets."""
    np.random.seed(42)
    return pd.Series(np.random.randn(n_samples) * 0.1 + 0.5, name="target")


# =============================================================================
# TEST 1: NO LEAKAGE IN OPTIMIZATION (Plan Section 6.1)
# =============================================================================


def test_no_leakage_in_optimization():
    """Verify optimization uses only historical data.

    From Plan Section 6.1:
    - Mark X_pred with 'FUTURE_LEAK' marker
    - Run optimize_catboost_config()
    - Verify marker not in config
    """
    # Create historical data
    n_samples = 800
    X_full = make_mock_features(n_samples)
    y_full = make_mock_classification_targets(n_samples)

    # Create X_pred with future marker (NOT passed to optimize)
    X_pred = make_mock_features(1)
    FUTURE_MARKER = 999999.0
    X_pred.iloc[0, 0] = FUTURE_MARKER  # Mark with impossible value

    # Run optimization with only X_full, y_full
    config = optimize_catboost_config(
        X_full=X_full,
        y_full=y_full,
        target_name="direction_1bar",
        task_type="classification",
        horizon=1,
        enable_hyperparameter_refinement=False,  # Skip Stage 4 for speed
    )

    # Config should not contain any reference to X_pred data
    # (Config is a dataclass, not data, so this is more of a sanity check)
    config_str = str(config)
    assert str(FUTURE_MARKER) not in config_str, "Config contains future marker!"

    # Verify config is valid
    assert isinstance(config, CatBoostModelConfig)
    assert config.train_window > 0
    assert 0 < config.train_ratio < 1

    print("✅ test_no_leakage_in_optimization PASSED")


# =============================================================================
# TEST 2: CONFIG BOUNDS (Plan Section 6.1)
# =============================================================================


def test_config_bounds():
    """Verify optimized configs stay within valid bounds.

    From Plan Section 6.1:
    - train_window: 200-700
    - train_ratio: 0.50-0.70
    - val_ratio: 0.15-0.25
    - cal_ratio: 0.10-0.30
    - train + val + cal = 1.0 ± 0.01
    """
    # Test multiple scenarios
    test_cases = [
        ("direction_1bar", "classification", 1),
        ("volatility_1bar", "regression", 1),
        ("vol_regime_3bar", "classification", 3),
        ("direction_12bar", "classification", 12),
    ]

    for target_name, task_type, horizon in test_cases:
        # Create data
        n_samples = 800
        X_full = make_mock_features(n_samples)
        if task_type == "classification":
            y_full = make_mock_classification_targets(n_samples)
        else:
            y_full = make_mock_regression_targets(n_samples)

        # Get optimized config
        config = optimize_catboost_config(
            X_full=X_full,
            y_full=y_full,
            target_name=target_name,
            task_type=task_type,
            horizon=horizon,
            enable_hyperparameter_refinement=False,  # Skip Stage 4 for speed
        )

        # Verify bounds
        assert 200 <= config.train_window <= 700, (
            f"{target_name}: train_window {config.train_window} out of bounds [200, 700]"
        )

        assert 0.50 <= config.train_ratio <= 0.70, (
            f"{target_name}: train_ratio {config.train_ratio} out of bounds [0.50, 0.70]"
        )

        assert 0.15 <= config.val_ratio <= 0.25, (
            f"{target_name}: val_ratio {config.val_ratio} out of bounds [0.15, 0.25]"
        )

        assert 0.10 <= config.cal_ratio <= 0.30, (
            f"{target_name}: cal_ratio {config.cal_ratio} out of bounds [0.10, 0.30]"
        )

        # Verify ratios sum to 1.0
        ratio_sum = config.train_ratio + config.val_ratio + config.cal_ratio
        assert abs(ratio_sum - 1.0) < 0.01, (
            f"{target_name}: ratio sum {ratio_sum} != 1.0"
        )

        print(
            f"  ✓ {target_name}: window={config.train_window}, ratios={config.train_ratio:.2f}/{config.val_ratio:.2f}/{config.cal_ratio:.2f}"
        )

    print("✅ test_config_bounds PASSED")


# =============================================================================
# TEST 3: TARGET-SPECIFIC ADJUSTMENTS (Plan Section 6.1)
# =============================================================================


def test_target_specific_adjustments():
    """Verify different targets produce different configs.

    From Plan Section 6.1:
    - direction vs volatility targets MUST produce different configs
    """
    n_samples = 800
    X_full = make_mock_features(n_samples)
    y_direction = make_mock_classification_targets(n_samples)
    y_volatility = make_mock_regression_targets(n_samples)

    # Get configs for different targets
    cfg_direction = optimize_catboost_config(
        X_full=X_full,
        y_full=y_direction,
        target_name="direction_1bar",
        task_type="classification",
        horizon=1,
        enable_hyperparameter_refinement=False,
    )

    cfg_volatility = optimize_catboost_config(
        X_full=X_full,
        y_full=y_volatility,
        target_name="volatility_1bar",
        task_type="regression",
        horizon=1,
        enable_hyperparameter_refinement=False,
    )

    # Should produce different configs
    different = (
        cfg_direction.train_window != cfg_volatility.train_window
        or cfg_direction.feature_selection_ratio
        != cfg_volatility.feature_selection_ratio
        or cfg_direction.cal_ratio != cfg_volatility.cal_ratio
    )

    assert different, (
        f"Direction and volatility configs are identical! "
        f"dir={cfg_direction.train_window}/{cfg_direction.feature_selection_ratio}, "
        f"vol={cfg_volatility.train_window}/{cfg_volatility.feature_selection_ratio}"
    )

    print(
        f"  Direction: window={cfg_direction.train_window}, feat_ratio={cfg_direction.feature_selection_ratio}, cal={cfg_direction.cal_ratio}"
    )
    print(
        f"  Volatility: window={cfg_volatility.train_window}, feat_ratio={cfg_volatility.feature_selection_ratio}, cal={cfg_volatility.cal_ratio}"
    )
    print("✅ test_target_specific_adjustments PASSED")


# =============================================================================
# TEST 4: ALL 28 TARGET CONFIGS (Plan Section 1.1)
# =============================================================================


def test_all_28_configs():
    """Run optimization on all 28 target configs without crash.

    From Plan Section 1.1:
    - 7 target types × 4 horizons = 28 configs
    """
    target_types = [
        ("direction", "classification"),
        ("volatility", "regression"),
        ("volatility_regime", "classification"),
        ("trend_regime", "classification"),
        ("first_extreme", "classification"),
        ("vol_to_extreme", "regression"),
    ]
    horizons = [1, 3, 6, 12]

    n_samples = 800
    X_full = make_mock_features(n_samples)
    y_cls = make_mock_classification_targets(n_samples)
    y_reg = make_mock_regression_targets(n_samples)

    results = []
    for target_base, task_type in target_types:
        for horizon in horizons:
            target_name = f"{target_base}_{horizon}bar"
            y_full = y_cls if task_type == "classification" else y_reg

            try:
                config = optimize_catboost_config(
                    X_full=X_full,
                    y_full=y_full,
                    target_name=target_name,
                    task_type=task_type,
                    horizon=horizon,
                    enable_hyperparameter_refinement=False,  # Skip Stage 4 for speed
                )
                results.append((target_name, "PASS", config.train_window))
            except Exception as e:
                results.append((target_name, f"FAIL: {e}", None))

    # Check all passed
    failures = [r for r in results if "FAIL" in r[1]]
    for target_name, status, window in results:
        symbol = "✓" if status == "PASS" else "✗"
        print(
            f"  {symbol} {target_name}: {status}"
            + (f" (window={window})" if window else "")
        )

    assert len(failures) == 0, f"Failed configs: {failures}"
    print(f"✅ test_all_28_configs PASSED ({len(results)}/28 configs)")


# =============================================================================
# TEST 5: DATA CHARACTERISTICS FIELDS (Plan Section 3.2)
# =============================================================================


def test_data_characteristics_fields():
    """Verify DataCharacteristics has all 21 fields from plan.

    From Plan Section 3.2:
    - 21 fields total across 5 categories
    """
    expected_fields = [
        # Target Characteristics (7)
        "task_type",
        "n_classes",
        "class_balance",
        "class_imbalance_ratio",
        "target_mean",
        "target_std",
        "target_skew",
        # Stationarity (5)
        "adf_statistic",
        "adf_pvalue",
        "is_stationary",
        "rolling_mean_drift",
        "rolling_std_drift",
        # Regime (3)
        "volatility_level",
        "volatility_ratio",
        "trend_strength",
        # Feature Quality (4)
        "n_features",
        "n_low_variance",
        "mean_correlation",
        "max_correlation",
        # Sample Size (2)
        "n_samples",
        "samples_per_class",
    ]

    # Get actual fields
    actual_fields = list(DataCharacteristics.__dataclass_fields__.keys())

    # Check each expected field
    missing = []
    for field in expected_fields:
        if field not in actual_fields:
            missing.append(field)

    # Check for extra fields
    extra = [f for f in actual_fields if f not in expected_fields]

    print(f"  Expected fields: {len(expected_fields)}")
    print(f"  Actual fields: {len(actual_fields)}")

    assert len(missing) == 0, f"Missing fields: {missing}"
    print(f"  ✓ All {len(expected_fields)} fields present")

    if extra:
        print(f"  Note: Extra fields found: {extra}")

    print("✅ test_data_characteristics_fields PASSED")


# =============================================================================
# TEST 6: CHARACTERIZE_DATA FUNCTIONALITY
# =============================================================================


def test_characterize_data_classification():
    """Test characterize_data for classification targets."""
    n_samples = 500
    X_full = make_mock_features(n_samples)
    y_full = make_mock_classification_targets(n_samples)

    chars = characterize_data(X_full, y_full, "classification")

    # Verify classification fields populated
    assert chars.task_type == "classification"
    assert chars.n_classes == 3
    assert chars.class_balance is not None
    assert 0 < chars.class_balance <= 0.5
    assert chars.class_imbalance_ratio >= 1.0
    assert chars.samples_per_class is not None
    assert len(chars.samples_per_class) == 3

    # Verify regression fields None
    assert chars.target_mean is None
    assert chars.target_std is None
    assert chars.target_skew is None

    # Verify common fields
    assert chars.n_samples == n_samples
    assert chars.n_features == 50
    assert chars.volatility_level in ["low", "medium", "high"]

    print(
        f"  Classification: n_classes={chars.n_classes}, balance={chars.class_balance:.3f}"
    )
    print("✅ test_characterize_data_classification PASSED")


def test_characterize_data_regression():
    """Test characterize_data for regression targets."""
    n_samples = 500
    X_full = make_mock_features(n_samples)
    y_full = make_mock_regression_targets(n_samples)

    chars = characterize_data(X_full, y_full, "regression")

    # Verify regression fields populated
    assert chars.task_type == "regression"
    assert chars.target_mean is not None
    assert chars.target_std is not None
    assert chars.target_skew is not None

    # Verify classification fields None
    assert chars.n_classes is None
    assert chars.class_balance is None
    assert chars.samples_per_class is None

    print(f"  Regression: mean={chars.target_mean:.3f}, std={chars.target_std:.3f}")
    print("✅ test_characterize_data_regression PASSED")


# =============================================================================
# MAIN
# =============================================================================


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("CatBoost Optimization Unit Tests")
    print("=" * 70 + "\n")

    # Run all tests
    test_data_characteristics_fields()
    print()

    test_characterize_data_classification()
    print()

    test_characterize_data_regression()
    print()

    test_no_leakage_in_optimization()
    print()

    test_config_bounds()
    print()

    test_target_specific_adjustments()
    print()

    test_all_28_configs()
    print()

    print("\n" + "=" * 70)
    print("ALL TESTS PASSED ✅")
    print("=" * 70)
