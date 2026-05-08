"""
Tests for target_models registry and data loading.
"""

import pandas as pd
import pytest

pytest.importorskip("polars")

from scripts.target_models.core import (
    DualLayerEngine,
    create_dual_config,
)
from scripts.target_models.registry import (
    ALL_HORIZONS,
    ALL_TARGETS,
    TARGET_REGISTRY,
    TargetSpec,
    get_summary_table,
    get_target_spec,
    iterate_all_targets,
    iterate_by_task_type,
    load_target_data,
    validate_all_targets,
    validate_target,
)

_MISSING_GENERATED_DATASETS = [
    spec.dataset_path
    for spec in TARGET_REGISTRY.values()
    if not spec.dataset_path.exists()
]
requires_generated_target_datasets = pytest.mark.skipif(
    bool(_MISSING_GENERATED_DATASETS),
    reason=(
        "generated target datasets are absent under data/datasets; run "
        "python -m scripts.analysis.run build-datasets"
    ),
)


# =============================================================================
# REGISTRY TESTS
# =============================================================================
class TestRegistry:
    """Test target registry structure."""

    def test_registry_has_20_entries(self):
        """Registry should have exactly 20 target-horizon combinations."""
        assert len(TARGET_REGISTRY) == 20

    def test_all_targets_defined(self):
        """All 5 targets should be defined."""
        assert len(ALL_TARGETS) == 5
        assert set(ALL_TARGETS) == {
            "volatility",
            "returns",
            "direction",
            "vol_regime",
            "trend_regime",
        }

    def test_all_horizons_defined(self):
        """All 4 horizons should be defined."""
        assert ALL_HORIZONS == (1, 3, 6, 12)

    def test_get_target_spec_valid(self):
        """Should return TargetSpec for valid combination."""
        spec = get_target_spec("volatility", 6)
        assert isinstance(spec, TargetSpec)
        assert spec.target == "volatility"
        assert spec.horizon == 6

    def test_get_target_spec_invalid(self):
        """Should raise KeyError for invalid combination."""
        with pytest.raises(KeyError):
            get_target_spec("invalid_target", 6)
        with pytest.raises(KeyError):
            get_target_spec("volatility", 99)


class TestTargetSpec:
    """Test TargetSpec properties."""

    def test_identifier(self):
        """Identifier should be target_horizonbar."""
        spec = get_target_spec("direction", 12)
        assert spec.identifier == "direction_12bar"

    def test_purge_gap_minimum(self):
        """Purge gap should be at least 21."""
        for spec in TARGET_REGISTRY.values():
            assert spec.purge_gap >= 21

    def test_purge_gap_horizon_adjusted(self):
        """Purge gap should increase with horizon."""
        spec_1 = get_target_spec("volatility", 1)
        spec_12 = get_target_spec("volatility", 12)
        assert spec_12.purge_gap >= spec_1.purge_gap

    def test_task_types_correct(self):
        """Task types should match expected."""
        assert get_target_spec("volatility", 1).task_type == "regression"
        assert get_target_spec("returns", 1).task_type == "regression"
        assert get_target_spec("direction", 1).task_type == "binary"
        assert get_target_spec("vol_regime", 1).task_type == "multiclass"
        assert get_target_spec("trend_regime", 1).task_type == "binary"


# =============================================================================
# DATA LOADING TESTS
# =============================================================================
class TestLoadTargetData:
    """Test data loading functionality."""

    pytestmark = requires_generated_target_datasets

    def test_load_returns_correct_types(self):
        """Should return DataFrame, Series, TargetSpec."""
        X, y, spec = load_target_data("volatility", 6, verbose=False)
        assert isinstance(X, pd.DataFrame)
        assert isinstance(y, pd.Series)
        assert isinstance(spec, TargetSpec)

    def test_load_no_nan_in_features(self):
        """X should have no NaN after loading with drop_na=True."""
        X, y, _ = load_target_data("direction", 3, drop_na=True, verbose=False)
        assert X.notna().all().all()

    def test_load_no_nan_in_target(self):
        """y should have no NaN after loading with drop_na=True."""
        X, y, _ = load_target_data("returns", 6, drop_na=True, verbose=False)
        assert y.notna().all()

    def test_load_consistent_length(self):
        """X and y should have same length."""
        X, y, _ = load_target_data("vol_regime", 12, verbose=False)
        assert len(X) == len(y)

    def test_load_reasonable_size(self):
        """Should have at least 4000 rows after cleaning."""
        for target in ALL_TARGETS:
            X, y, _ = load_target_data(target, 1, verbose=False)
            assert len(X) >= 4000, f"{target}_1bar has only {len(X)} rows"


class TestValidation:
    """Test validation functionality."""

    @requires_generated_target_datasets
    def test_validate_single_target(self):
        """Should validate a single target successfully."""
        result = validate_target("volatility", 6)
        assert result.success
        assert result.n_rows > 0
        assert result.n_features > 0

    @requires_generated_target_datasets
    def test_validate_all_pass(self):
        """All 20 targets should validate."""
        results = validate_all_targets(verbose=False)
        assert len(results) == 20
        assert all(r.success for r in results), (
            f"Failed: {[r for r in results if not r.success]}"
        )

    def test_summary_table(self):
        """Summary table should have 20 rows."""
        df = get_summary_table()
        assert len(df) == 20
        assert "target" in df.columns
        assert "horizon" in df.columns
        assert "valid" in df.columns


# =============================================================================
# ITERATION TESTS
# =============================================================================
class TestIteration:
    """Test iteration utilities."""

    pytestmark = requires_generated_target_datasets

    def test_iterate_all_yields_20(self):
        """Should yield exactly 20 combinations."""
        count = sum(1 for _ in iterate_all_targets(verbose=False))
        assert count == 20

    def test_iterate_by_task_type_regression(self):
        """Should yield only regression targets."""
        for target, _horizon, _X, _y, spec in iterate_by_task_type(
            "regression", verbose=False
        ):
            assert spec.task_type == "regression"
            assert target in ("volatility", "returns")

    def test_iterate_by_task_type_binary(self):
        """Should yield only binary targets."""
        for target, _horizon, _X, _y, spec in iterate_by_task_type(
            "binary", verbose=False
        ):
            assert spec.task_type == "binary"
            assert target in ("direction", "trend_regime")

    def test_iterate_by_task_type_multiclass(self):
        """Should yield only multiclass targets."""
        count = 0
        for target, _horizon, _X, _y, spec in iterate_by_task_type(
            "multiclass", verbose=False
        ):
            assert spec.task_type == "multiclass"
            assert target == "vol_regime"
            count += 1
        assert count == 4  # 4 horizons for vol_regime


# =============================================================================
# DUAL-LAYER ENGINE INTEGRATION TESTS
# =============================================================================
class TestDualLayerIntegration:
    """Test dual-layer engine works with all targets."""

    pytestmark = requires_generated_target_datasets

    @pytest.mark.parametrize("target", ALL_TARGETS)
    @pytest.mark.parametrize("horizon", [6])  # Test with 6-bar only for speed
    def test_dual_layer_engine_creates(self, target, horizon):
        """DualLayerEngine should create for each target."""
        X, y, spec = load_target_data(target, horizon, verbose=False)
        config = create_dual_config(target, horizon)

        engine = DualLayerEngine(X, y, config)
        assert engine.n_iterations > 0

    @pytest.mark.parametrize("target", ALL_TARGETS)
    def test_dual_layer_first_window_valid(self, target):
        """First window should have valid indices."""
        X, y, spec = load_target_data(target, 6, verbose=False)
        config = create_dual_config(target, 6)
        engine = DualLayerEngine(X, y, config)

        window = engine.get_window(engine.start_pred_time)

        # Check layer 1 indices are valid
        assert window.layer1.train.start_idx >= 0
        assert window.layer1.val.end_idx <= len(X)

        # Check layer 2 indices are valid
        assert window.layer2.train.start_idx >= 0
        assert window.layer2.pred.end_idx <= len(X)

        # Check temporal ordering: L1 ends before L2 starts
        assert window.layer1.val.end_idx < window.layer2.train.start_idx

    def test_dual_layer_window_data_extraction(self):
        """Should be able to extract actual data from windows."""
        X, y, _ = load_target_data("volatility", 6, verbose=False)
        config = create_dual_config("volatility", 6)
        engine = DualLayerEngine(X, y, config)

        window = engine.get_window(engine.start_pred_time)

        # Extract layer 1 training data
        l1_train_X = window.layer1.train.X
        l1_train_y = window.layer1.train.y

        assert len(l1_train_X) == config.layer1.train_size
        assert len(l1_train_y) == config.layer1.train_size
        assert l1_train_X.notna().all().all()


# =============================================================================
# CONSISTENCY TESTS
# =============================================================================
class TestConsistency:
    """Test consistency across targets."""

    pytestmark = requires_generated_target_datasets

    def test_same_horizon_same_timestamp_range(self):
        """All targets with same horizon should cover same time range."""
        # This would require timestamp column, skip if not available
        pass  # Datasets don't have timestamp after feature extraction

    def test_feature_overlap(self):
        """Most features should be shared across targets."""
        # Load two different targets
        X_vol, _, _ = load_target_data("volatility", 6, verbose=False)
        X_dir, _, _ = load_target_data("direction", 6, verbose=False)

        vol_features = set(X_vol.columns)
        dir_features = set(X_dir.columns)

        # At least 90% overlap in base features
        overlap = vol_features & dir_features
        min_features = min(len(vol_features), len(dir_features))

        assert len(overlap) / min_features >= 0.9, (
            f"Feature overlap too low: {len(overlap)}/{min_features}"
        )
