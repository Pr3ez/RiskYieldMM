"""
Configuration for conformal prediction calibration.

Based on validation results from Phases 3-5:
- Calibration: 150 samples minimum (cal_ratio=0.30)
- Classification: LAC method
- Regression: EnbPI method with conf=0.93 for 90% actual
- ACI: gamma=0.04-0.10, batch-level updates
"""

from dataclasses import dataclass
from typing import Literal


@dataclass
class ConformalConfig:
    """
    Configuration for conformal prediction.

    Attributes:
        enabled: Whether to apply conformal calibration
        confidence_level: Target coverage (e.g., 0.90 for 90%)
        min_cal_samples: Minimum calibration samples required
        cal_ratio: Fraction of L2 window for calibration (default 0.30 for 150 samples)

        # Classification settings
        cls_method: Conformity score for classification ('lac' only for binary)

        # Regression settings
        reg_method: Method for regression ('enbpi')
        reg_confidence_adj: Adjustment to nominal confidence for regression
                           (0.93 to achieve ~90% actual coverage)

        # ACI settings
        aci_enabled: Whether to use adaptive alpha
        aci_gamma: Learning rate for ACI updates (0.04-0.10)
        aci_alpha_min: Minimum alpha bound
        aci_alpha_max: Maximum alpha bound
    """

    # Core settings
    enabled: bool = True
    confidence_level: float = 0.90
    min_cal_samples: int = 100
    cal_ratio: float = 0.30  # 150 samples from 500 L2 window

    # Classification settings
    cls_method: Literal["lac"] = "lac"  # Only LAC works for binary

    # Regression settings
    reg_method: Literal["enbpi"] = "enbpi"
    reg_confidence_adj: float = 0.93  # Use 0.93 nominal for 90% actual

    # ACI settings
    aci_enabled: bool = True
    aci_gamma: float = 0.04  # Conservative, use 0.10 for more responsive
    aci_alpha_min: float = 0.02
    aci_alpha_max: float = 0.30

    def __post_init__(self):
        """Validate configuration."""
        if not 0.5 <= self.confidence_level <= 0.99:
            raise ValueError(
                f"confidence_level must be in [0.5, 0.99], got {self.confidence_level}"
            )
        if self.min_cal_samples < 20:
            raise ValueError(
                f"min_cal_samples should be >= 20, got {self.min_cal_samples}"
            )
        if not 0.001 <= self.aci_gamma <= 0.5:
            raise ValueError(f"aci_gamma must be in [0.001, 0.5], got {self.aci_gamma}")

    @property
    def alpha(self) -> float:
        """Miscoverage rate (1 - confidence_level)."""
        return 1 - self.confidence_level

    def get_cls_confidence(self) -> float:
        """Get confidence level for classification."""
        return self.confidence_level

    def get_reg_confidence(self) -> float:
        """Get adjusted confidence level for regression."""
        return self.reg_confidence_adj


# Default configurations
DEFAULT_CONFIG = ConformalConfig()

CONSERVATIVE_CONFIG = ConformalConfig(
    confidence_level=0.95,
    aci_gamma=0.02,
)

RESPONSIVE_CONFIG = ConformalConfig(
    confidence_level=0.90,
    aci_gamma=0.10,
)
