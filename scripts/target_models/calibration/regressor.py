"""
Conformal Regressor wrapper for regression models.

Uses MAPIE TimeSeriesRegressor with EnbPI (Ensemble Batch Prediction Intervals)
- designed for time series data with potential distribution shift.

Validated in Phase 4: EnbPI achieves ~88-90% coverage.
Uses confidence=0.93 nominal to achieve ~90% actual coverage.
"""

from typing import Any

import numpy as np

from .aci import AdaptiveConformalInference
from .config import ConformalConfig
from .patches import apply_mapie_patches

# Apply patches on import
apply_mapie_patches()


class _SklearnRegressorWrapper:
    """
    Wrapper to make ModelEnsemble sklearn-compatible for MAPIE.

    ModelEnsemble.predict() returns EnsembleOutput object, but MAPIE
    expects raw numpy arrays from predict(). This wrapper intercepts
    predict() calls and extracts the y_pred attribute.
    """

    def __init__(self, estimator: Any):
        """Wrap an estimator that returns EnsembleOutput from predict()."""
        self._estimator = estimator

    def fit(self, X: np.ndarray, y: np.ndarray) -> "_SklearnRegressorWrapper":
        """Delegate fit to wrapped estimator."""
        self._estimator.fit(X, y)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Return raw array predictions, extracting from EnsembleOutput if needed."""
        output = self._estimator.predict(X)
        # Handle EnsembleOutput (has y_pred attribute)
        if hasattr(output, "y_pred"):
            return output.y_pred
        # Fallback: already a raw array
        return output

    def __sklearn_is_fitted__(self) -> bool:
        """Check if wrapped estimator is fitted."""
        # Check for common fitted attributes
        if hasattr(self._estimator, "__sklearn_is_fitted__"):
            return self._estimator.__sklearn_is_fitted__()
        # Check for trailing underscore attributes (sklearn convention)
        fitted_attrs = [
            v
            for v in vars(self._estimator)
            if v.endswith("_") and not v.startswith("__")
        ]
        return len(fitted_attrs) > 0

    def __sklearn_tags__(self):
        """Return sklearn tags for regressor."""
        # Try to delegate to wrapped estimator first
        if hasattr(self._estimator, "__sklearn_tags__"):
            return self._estimator.__sklearn_tags__()
        # Fallback: construct proper regressor tags for sklearn 1.8.0
        from sklearn.utils._tags import InputTags, RegressorTags, Tags, TargetTags

        return Tags(
            estimator_type="regressor",
            target_tags=TargetTags(required=True, one_d_labels=True),
            input_tags=InputTags(allow_nan=True, two_d_array=True),
            regressor_tags=RegressorTags(poor_score=False),
        )

    def __getattr__(self, name: str) -> Any:
        """Delegate all other attribute access to wrapped estimator."""
        return getattr(self._estimator, name)


class ConformalRegressor:
    """
    Conformal prediction wrapper for regression models.

    Wraps a fitted sklearn-compatible regressor with MAPIE's
    TimeSeriesRegressor using EnbPI method.

    Note: Uses adjusted confidence (0.93) to achieve ~90% actual coverage
    due to systematic undercoverage in time series setting.

    Attributes:
        estimator: The fitted base regressor
        config: Conformal configuration
        aci: Optional ACI for adaptive alpha (if enabled)
        mapie: The underlying MAPIE regressor (after calibration)
        is_calibrated: Whether calibration has been performed

    Example:
        >>> from lightgbm import LGBMRegressor
        >>> model = LGBMRegressor().fit(X_train, y_train)
        >>> conf_reg = ConformalRegressor(model)
        >>> conf_reg.calibrate(X_cal, y_cal)
        >>> y_pred, intervals = conf_reg.predict(X_test)
        >>> # intervals[:, 0] = lower bounds, intervals[:, 1] = upper bounds
    """

    def __init__(
        self,
        estimator: Any,
        config: ConformalConfig | None = None,
    ):
        """
        Initialize conformal regressor.

        Args:
            estimator: Fitted sklearn-compatible regressor or ModelEnsemble
            config: Conformal configuration (uses DEFAULT_CONFIG if None)
        """
        from mapie.regression import TimeSeriesRegressor

        self.estimator = estimator
        self.config = config or ConformalConfig()
        self.mapie: TimeSeriesRegressor | None = None
        self.is_calibrated = False

        # Initialize ACI if enabled
        self.aci: AdaptiveConformalInference | None = None
        if self.config.aci_enabled:
            self.aci = AdaptiveConformalInference(
                alpha_target=self.config.alpha,
                gamma=self.config.aci_gamma,
                alpha_min=self.config.aci_alpha_min,
                alpha_max=self.config.aci_alpha_max,
            )

    def _wrap_estimator(self, estimator: Any) -> Any:
        """
        Wrap estimator for sklearn compatibility if needed.

        ModelEnsemble.predict() returns EnsembleOutput, but MAPIE needs
        raw array predictions. This wrapper intercepts predict() calls.
        """
        # Check if estimator has our custom predict that returns EnsembleOutput
        if hasattr(estimator, "predict_labels"):
            # It's our ModelEnsemble - wrap it
            return _SklearnRegressorWrapper(estimator)
        return estimator

    def calibrate(self, X_cal: np.ndarray, y_cal: np.ndarray) -> "ConformalRegressor":
        """
        Calibrate conformal predictor on calibration data.

        Args:
            X_cal: Calibration features (n_samples, n_features)
            y_cal: Calibration targets (n_samples,)

        Returns:
            self for method chaining

        Raises:
            ValueError: If calibration samples < min_cal_samples
        """
        from mapie.regression import TimeSeriesRegressor

        if len(X_cal) < self.config.min_cal_samples:
            raise ValueError(
                f"Need at least {self.config.min_cal_samples} calibration samples, "
                f"got {len(X_cal)}"
            )

        # Wrap estimator for sklearn compatibility
        wrapped_estimator = self._wrap_estimator(self.estimator)

        self.mapie = TimeSeriesRegressor(
            estimator=wrapped_estimator,
            cv="prefit",
        )
        self.mapie.fit(X_cal, y_cal)
        self.is_calibrated = True

        return self

    def predict(
        self,
        X: np.ndarray,
        return_intervals: bool = True,
    ) -> tuple[np.ndarray, np.ndarray | None]:
        """
        Make predictions with prediction intervals.

        Args:
            X: Features (n_samples, n_features)
            return_intervals: Whether to return prediction intervals

        Returns:
            Tuple of:
            - y_pred: Point predictions (n_samples,)
            - intervals: Prediction intervals (n_samples, 2) if return_intervals=True
                        intervals[:, 0] = lower bounds
                        intervals[:, 1] = upper bounds

        Raises:
            RuntimeError: If not calibrated
        """
        if not self.is_calibrated:
            raise RuntimeError("Must call calibrate() before predict()")

        confidence = self._get_current_confidence()

        if return_intervals:
            y_pred, intervals = self.mapie.predict(X, confidence_level=confidence)
            # intervals shape: (n_samples, 2, 1) -> squeeze last dim
            intervals = intervals[:, :, 0]
            return y_pred, intervals
        else:
            y_pred = self.mapie.predict(X)
            if isinstance(y_pred, tuple):
                y_pred = y_pred[0]
            return y_pred, None

    def predict_with_intervals(
        self,
        X: np.ndarray,
        alpha: float | None = None,
    ) -> np.ndarray:
        """
        Get prediction intervals only (convenience method for pipeline).

        Args:
            X: Features (n_samples, n_features)
            alpha: Override alpha (ignored for now, uses ACI level)

        Returns:
            intervals: Prediction intervals (n_samples, 2)
                      intervals[:, 0] = lower bounds
                      intervals[:, 1] = upper bounds
        """
        _, intervals = self.predict(X, return_intervals=True)
        return intervals

    def update_aci(self, y_true: np.ndarray, intervals: np.ndarray) -> None:
        """
        Update ACI based on observed coverage.

        Call after each prediction batch to adapt confidence for next batch.

        Args:
            y_true: True values (n_samples,)
            intervals: Prediction intervals from predict() (n_samples, 2)
        """
        if self.aci is None:
            return

        # Calculate coverage: fraction where true value is in interval
        lower, upper = intervals[:, 0], intervals[:, 1]
        coverage = np.mean((y_true >= lower) & (y_true <= upper))
        self.aci.update_from_coverage(coverage)

    def _get_current_confidence(self) -> float:
        """Get current confidence level (from ACI if enabled, otherwise adjusted)."""
        if self.aci is not None:
            return self.aci.confidence_level
        return self.config.get_reg_confidence()

    def get_diagnostics(self) -> dict:
        """Get diagnostic information."""
        diag = {
            "is_calibrated": self.is_calibrated,
            "confidence_level": self._get_current_confidence(),
            "method": self.config.reg_method,
        }
        if self.aci is not None:
            diag["aci"] = self.aci.get_diagnostics()
        return diag

    def __repr__(self) -> str:
        status = "calibrated" if self.is_calibrated else "not calibrated"
        return (
            f"ConformalRegressor({status}, "
            f"conf={self._get_current_confidence():.2f}, "
            f"method={self.config.reg_method})"
        )
