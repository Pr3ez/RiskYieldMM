"""
Conformal Prediction Calibration Module

Provides uncertainty quantification for ML predictions using MAPIE.
Includes Adaptive Conformal Inference (ACI) for distribution shift handling.

Components:
- ConformalConfig: Configuration dataclass
- ConformalClassifier: Wrapper for classification models
- ConformalRegressor: Wrapper for regression models
- AdaptiveConformalInference: Dynamic alpha adjustment
- CoverageMonitor: Rolling coverage tracking with alerts

Validated methods (Phase 4):
- Classification: LAC (only option for binary, best for multiclass)
- Regression: EnbPI via TimeSeriesRegressor

Required: MAPIE v1.2.0 with sklearn 1.8.0 monkey-patch applied.
"""

from .aci import AdaptiveConformalInference
from .classifier import ConformalClassifier
from .config import ConformalConfig
from .coverage_monitor import (
    CoverageAlert,
    CoverageMonitor,
    CoverageStats,
    RegimeAwareCoverageMonitor,
)
from .cqr import CQRConfig, CQRRegressor, create_cqr_from_conformal_config
from .patches import apply_mapie_patches
from .regressor import ConformalRegressor

__all__ = [
    "ConformalConfig",
    "ConformalClassifier",
    "ConformalRegressor",
    "AdaptiveConformalInference",
    "apply_mapie_patches",
    # CQR (Conformalized Quantile Regression)
    "CQRConfig",
    "CQRRegressor",
    "create_cqr_from_conformal_config",
    # Coverage monitoring
    "CoverageMonitor",
    "CoverageAlert",
    "CoverageStats",
    "RegimeAwareCoverageMonitor",
]
