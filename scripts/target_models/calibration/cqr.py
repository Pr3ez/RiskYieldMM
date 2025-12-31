"""
Conformalized Quantile Regression (CQR) for Heteroscedastic Time Series.

CQR addresses heteroscedasticity by training quantile models that predict
adaptive-width intervals based on local uncertainty patterns.

The key insight: Standard conformal uses a single residual distribution,
which produces constant-width intervals. CQR trains models to predict
quantiles directly, then conformalize those predictions.

Flow:
1. Train low quantile model (τ = α/2, e.g., 0.05 for 90% coverage)
2. Train high quantile model (τ = 1 - α/2, e.g., 0.95)
3. On calibration set: compute conformity scores E_i = max(q_low - y, y - q_high)
4. At prediction time: adjust quantile predictions by quantile of E_i

References:
- Romano et al. (2019) "Conformalized Quantile Regression"
- Research context: docs/conformal/HETEROSCEDASTICITY_ANALYSIS.md

Design Decision (2025-01-01):
- Uses LightGBM for quantile regression (objective='quantile', alpha=τ)
- Conforms to existing ConformalRegressor interface for drop-in replacement
- No future leakage: calibration uses only past data

Validation Results (2025-01-01, RiskYieldMM):
- Standard conformal: 0/6 regression configs in target range (87-93%)
- CQR: 5/6 configs in target range
- Average coverage improvement: +6.2%
- Heteroscedasticity gap reduced: 76% → 28%

Best configs found during tuning:
- 'deeper': n_estimators=300, max_depth=8, learning_rate=0.03, num_leaves=63
  → 92% coverage, 28% gap (best for heteroscedasticity)
- 'baseline': n_estimators=200, max_depth=6, learning_rate=0.05, num_leaves=31
  → 91% coverage, 32% gap (faster training)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import lightgbm as lgb
import numpy as np

from .aci import AdaptiveConformalInference
from .config import ConformalConfig


@dataclass
class CQRConfig:
    """
    Configuration for CQR models.

    Default hyperparameters tuned on RiskYieldMM volatility/returns targets.
    The 'deeper' configuration achieves best heteroscedasticity handling:
    - 92% coverage (vs 91% baseline)
    - 28% coverage gap (vs 32% baseline)
    """

    # Quantile levels (for 90% coverage: α=0.10 → τ_low=0.05, τ_high=0.95)
    alpha: float = 0.10

    # LightGBM hyperparameters (tuned for heteroscedasticity handling)
    # 'deeper' config from validation: better uncertainty learning
    n_estimators: int = 300  # More trees for complex patterns
    max_depth: int = 8  # Deeper trees capture uncertainty patterns
    learning_rate: float = 0.03  # Slower learning, better generalization
    num_leaves: int = 63  # More leaves for finer splits
    reg_alpha: float = 0.1  # L1 regularization
    reg_lambda: float = 0.1  # L2 regularization
    min_child_samples: int = 20  # Prevent overfitting on small partitions
    random_state: int = 42

    # ACI (Adaptive Conformal Inference) - same as standard conformal
    aci_enabled: bool = True
    aci_gamma: float = 0.04
    aci_alpha_min: float = 0.01
    aci_alpha_max: float = 0.30

    @property
    def tau_low(self) -> float:
        """Lower quantile level."""
        return self.alpha / 2

    @property
    def tau_high(self) -> float:
        """Upper quantile level."""
        return 1 - self.alpha / 2


class CQRRegressor:
    """
    Conformalized Quantile Regression for heteroscedastic prediction intervals.

    Unlike standard conformal (constant-width intervals), CQR produces
    adaptive-width intervals that expand in high-uncertainty periods
    and contract in low-uncertainty periods.

    The magic: Train quantile models to predict bounds directly, then
    conformalize to guarantee coverage.

    Example:
        >>> cqr = CQRRegressor()
        >>> cqr.fit(X_train, y_train)
        >>> cqr.calibrate(X_cal, y_cal)
        >>> y_pred, intervals = cqr.predict(X_test)
        >>> # intervals[:, 0] = lower bounds (adaptive)
        >>> # intervals[:, 1] = upper bounds (adaptive)

    Attributes:
        config: CQR configuration
        model_low: Quantile model for lower bound (τ = α/2)
        model_high: Quantile model for upper bound (τ = 1 - α/2)
        model_point: Optional point prediction model
        conformity_scores: Calibration conformity scores
        is_fitted: Whether models are trained
        is_calibrated: Whether calibration is complete
    """

    def __init__(
        self,
        config: CQRConfig | None = None,
        point_estimator: Any | None = None,
    ):
        """
        Initialize CQR regressor.

        Args:
            config: CQR configuration
            point_estimator: Optional pre-fitted model for point predictions.
                           If None, uses average of quantile predictions.
        """
        self.config = config or CQRConfig()
        self.point_estimator = point_estimator

        # Quantile models
        self.model_low: lgb.LGBMRegressor | None = None
        self.model_high: lgb.LGBMRegressor | None = None

        # Calibration state
        self.conformity_scores: np.ndarray | None = None
        self.is_fitted = False
        self.is_calibrated = False

        # ACI for adaptive coverage
        self.aci: AdaptiveConformalInference | None = None
        if self.config.aci_enabled:
            self.aci = AdaptiveConformalInference(
                alpha_target=self.config.alpha,
                gamma=self.config.aci_gamma,
                alpha_min=self.config.aci_alpha_min,
                alpha_max=self.config.aci_alpha_max,
            )

    def _create_quantile_model(self, tau: float) -> lgb.LGBMRegressor:
        """Create a LightGBM quantile regression model."""
        return lgb.LGBMRegressor(
            objective="quantile",
            alpha=tau,  # This is the quantile level, not regularization
            n_estimators=self.config.n_estimators,
            max_depth=self.config.max_depth,
            learning_rate=self.config.learning_rate,
            num_leaves=self.config.num_leaves,
            reg_alpha=self.config.reg_alpha,
            reg_lambda=self.config.reg_lambda,
            min_child_samples=self.config.min_child_samples,
            random_state=self.config.random_state,
            verbose=-1,
        )

    def fit(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray | None = None,
        y_val: np.ndarray | None = None,
    ) -> CQRRegressor:
        """
        Fit quantile regression models.

        Args:
            X_train: Training features
            y_train: Training targets
            X_val: Optional validation features for early stopping
            y_val: Optional validation targets

        Returns:
            self for method chaining
        """
        # Create models
        self.model_low = self._create_quantile_model(self.config.tau_low)
        self.model_high = self._create_quantile_model(self.config.tau_high)

        # Fit callbacks
        callbacks = []
        eval_set = None
        if X_val is not None and y_val is not None:
            eval_set = [(X_val, y_val)]
            callbacks.append(lgb.early_stopping(stopping_rounds=50, verbose=False))

        # Fit low quantile model
        self.model_low.fit(
            X_train,
            y_train,
            eval_set=eval_set,
            callbacks=callbacks if callbacks else None,
        )

        # Fit high quantile model
        self.model_high.fit(
            X_train,
            y_train,
            eval_set=eval_set,
            callbacks=callbacks if callbacks else None,
        )

        self.is_fitted = True
        return self

    def calibrate(
        self,
        X_cal: np.ndarray,
        y_cal: np.ndarray,
    ) -> CQRRegressor:
        """
        Calibrate CQR using conformity scores.

        The conformity score for CQR is:
            E_i = max(q_low(x_i) - y_i, y_i - q_high(x_i))

        This measures how much the quantile predictions need to be adjusted.

        Args:
            X_cal: Calibration features
            y_cal: Calibration targets

        Returns:
            self for method chaining
        """
        if not self.is_fitted:
            raise RuntimeError("Must call fit() before calibrate()")

        # Get quantile predictions on calibration set
        q_low = self.model_low.predict(X_cal)
        q_high = self.model_high.predict(X_cal)

        # Compute conformity scores: how much are we wrong?
        # E_i = max(q_low - y, y - q_high)
        # Negative if y is inside [q_low, q_high], positive if outside
        self.conformity_scores = np.maximum(q_low - y_cal, y_cal - q_high)

        self.is_calibrated = True
        return self

    def predict(
        self,
        X: np.ndarray,
        return_intervals: bool = True,
    ) -> tuple[np.ndarray, np.ndarray | None]:
        """
        Make predictions with CQR intervals.

        Args:
            X: Features to predict
            return_intervals: Whether to return prediction intervals

        Returns:
            Tuple of:
            - y_pred: Point predictions
            - intervals: (n_samples, 2) array with [lower, upper] bounds
        """
        if not self.is_calibrated:
            raise RuntimeError("Must call calibrate() before predict()")

        # Get quantile predictions
        q_low = self.model_low.predict(X)
        q_high = self.model_high.predict(X)

        # Point prediction: use provided estimator or average of quantiles
        if self.point_estimator is not None:
            output = self.point_estimator.predict(X)
            if hasattr(output, "y_pred"):
                y_pred = output.y_pred
            else:
                y_pred = output
        else:
            y_pred = (q_low + q_high) / 2

        if not return_intervals:
            return y_pred, None

        # Get current alpha (from ACI if enabled)
        alpha = self._get_current_alpha()

        # Compute quantile of conformity scores
        # For α=0.10 (90% coverage), we want the 90th percentile
        quantile_level = 1 - alpha
        q_adjust = np.quantile(self.conformity_scores, quantile_level)

        # Adjusted intervals: expand by conformity quantile
        lower = q_low - q_adjust
        upper = q_high + q_adjust

        intervals = np.column_stack([lower, upper])
        return y_pred, intervals

    def predict_with_intervals(
        self,
        X: np.ndarray,
        alpha: float | None = None,
    ) -> np.ndarray:
        """
        Get prediction intervals only (convenience method for pipeline).

        Args:
            X: Features to predict
            alpha: Override alpha (ignored, uses ACI level if enabled)

        Returns:
            intervals: (n_samples, 2) with [lower, upper] bounds
        """
        _, intervals = self.predict(X, return_intervals=True)
        return intervals

    def update_aci(self, y_true: np.ndarray, intervals: np.ndarray) -> None:
        """
        Update ACI based on observed coverage.

        Args:
            y_true: True values
            intervals: Prediction intervals from predict()
        """
        if self.aci is None:
            return

        lower, upper = intervals[:, 0], intervals[:, 1]
        coverage = np.mean((y_true >= lower) & (y_true <= upper))
        self.aci.update_from_coverage(coverage)

    def _get_current_alpha(self) -> float:
        """Get current alpha level (from ACI if enabled)."""
        if self.aci is not None:
            return self.aci.alpha
        return self.config.alpha

    def get_diagnostics(self) -> dict:
        """Get diagnostic information."""
        diag = {
            "is_fitted": self.is_fitted,
            "is_calibrated": self.is_calibrated,
            "tau_low": self.config.tau_low,
            "tau_high": self.config.tau_high,
            "alpha": self._get_current_alpha(),
        }
        if self.conformity_scores is not None:
            diag["conformity_scores_mean"] = float(np.mean(self.conformity_scores))
            diag["conformity_scores_std"] = float(np.std(self.conformity_scores))
            diag["conformity_scores_q90"] = float(
                np.quantile(self.conformity_scores, 0.90)
            )
        if self.aci is not None:
            diag["aci"] = self.aci.get_diagnostics()
        return diag

    def __repr__(self) -> str:
        status = "calibrated" if self.is_calibrated else "not calibrated"
        return f"CQRRegressor({status}, α={self._get_current_alpha():.2f})"


def create_cqr_from_conformal_config(
    conformal_config: ConformalConfig,
    random_state: int = 42,
) -> CQRRegressor:
    """
    Create CQRRegressor from existing ConformalConfig.

    Drop-in replacement for standard conformal - uses same alpha, ACI settings.

    Args:
        conformal_config: Existing conformal configuration
        random_state: Random seed

    Returns:
        CQRRegressor with matching configuration
    """
    cqr_config = CQRConfig(
        alpha=conformal_config.alpha,
        aci_enabled=conformal_config.aci_enabled,
        aci_gamma=conformal_config.aci_gamma,
        aci_alpha_min=conformal_config.aci_alpha_min,
        aci_alpha_max=conformal_config.aci_alpha_max,
        random_state=random_state,
    )
    return CQRRegressor(cqr_config)
