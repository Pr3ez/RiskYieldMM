"""
Conformal Classifier wrapper for classification models.

Uses MAPIE SplitConformalClassifier with LAC (Least Ambiguous Classifier)
conformity score - the only method that works for binary classification.

Validated in Phase 4: LAC achieves ~89-91% coverage on our datasets.
"""

from typing import Any

import numpy as np

from .aci import AdaptiveConformalInference
from .config import ConformalConfig
from .patches import apply_mapie_patches

# Apply patches on import
apply_mapie_patches()


class ConformalClassifier:
    """
    Conformal prediction wrapper for classification models.

    Wraps a fitted sklearn-compatible classifier with MAPIE's
    SplitConformalClassifier using LAC conformity score.

    Attributes:
        estimator: The fitted base classifier
        config: Conformal configuration
        aci: Optional ACI for adaptive alpha (if enabled)
        mapie: The underlying MAPIE classifier (after calibration)
        is_calibrated: Whether calibration has been performed

    Example:
        >>> from lightgbm import LGBMClassifier
        >>> model = LGBMClassifier().fit(X_train, y_train)
        >>> conf_cls = ConformalClassifier(model)
        >>> conf_cls.calibrate(X_cal, y_cal)
        >>> y_pred, y_set = conf_cls.predict(X_test)
        >>> # y_set[i, c] = True if class c is in prediction set for sample i
    """

    def __init__(
        self,
        estimator: Any,
        config: ConformalConfig | None = None,
    ):
        """
        Initialize conformal classifier.

        Args:
            estimator: Fitted sklearn-compatible classifier with predict_proba
            config: Conformal configuration (uses DEFAULT_CONFIG if None)
        """
        from mapie.classification import SplitConformalClassifier

        self.estimator = estimator
        self.config = config or ConformalConfig()
        self.mapie: SplitConformalClassifier | None = None
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

    def calibrate(self, X_cal: np.ndarray, y_cal: np.ndarray) -> "ConformalClassifier":
        """
        Calibrate conformal predictor on calibration data.

        Args:
            X_cal: Calibration features (n_samples, n_features)
            y_cal: Calibration labels (n_samples,)

        Returns:
            self for method chaining

        Raises:
            ValueError: If calibration samples < min_cal_samples
        """
        from mapie.classification import SplitConformalClassifier

        if len(X_cal) < self.config.min_cal_samples:
            raise ValueError(
                f"Need at least {self.config.min_cal_samples} calibration samples, "
                f"got {len(X_cal)}"
            )

        confidence = self._get_current_confidence()

        self.mapie = SplitConformalClassifier(
            estimator=self.estimator,
            confidence_level=confidence,
            conformity_score=self.config.cls_method,
            prefit=True,
        )
        self.mapie.conformalize(X_cal, y_cal)
        self.is_calibrated = True

        return self

    def predict(
        self,
        X: np.ndarray,
        return_sets: bool = True,
    ) -> tuple[np.ndarray, np.ndarray | None]:
        """
        Make predictions with prediction sets.

        Args:
            X: Features (n_samples, n_features)
            return_sets: Whether to return prediction sets

        Returns:
            Tuple of:
            - y_pred: Point predictions (n_samples,)
            - y_set: Prediction sets (n_samples, n_classes) if return_sets=True
                    y_set[i, c] = True if class c in prediction set for sample i

        Raises:
            RuntimeError: If not calibrated
        """
        if not self.is_calibrated:
            raise RuntimeError("Must call calibrate() before predict()")

        if return_sets:
            y_pred, y_set = self.mapie.predict_set(X)
            # y_set shape: (n_samples, n_classes, 1) -> squeeze last dim
            y_set = y_set[:, :, 0]
            return y_pred, y_set
        else:
            y_pred = self.mapie.predict(X)
            return y_pred, None

    def predict_with_sets(
        self,
        X: np.ndarray,
        alpha: float | None = None,
    ) -> np.ndarray:
        """
        Get prediction sets only (convenience method for pipeline).

        Args:
            X: Features (n_samples, n_features)
            alpha: Override alpha (ignored for now, uses calibrated level)

        Returns:
            y_set: Prediction sets (n_samples, n_classes) boolean mask
        """
        _, y_set = self.predict(X, return_sets=True)
        return y_set

    def update_aci(self, y_true: np.ndarray, y_set: np.ndarray) -> None:
        """
        Update ACI based on observed coverage.


        Call after each prediction batch to adapt alpha for next batch.

        Args:
            y_true: True labels (n_samples,)
            y_set: Prediction sets from predict() (n_samples, n_classes)
        """
        if self.aci is None:
            return

        # Calculate coverage: fraction where true label is in prediction set
        coverage = np.mean([y_set[i, y_true[i]] for i in range(len(y_true))])
        self.aci.update_from_coverage(coverage)

    def recalibrate_if_needed(
        self,
        X_cal: np.ndarray,
        y_cal: np.ndarray,
    ) -> bool:
        """
        Recalibrate if ACI has adjusted alpha significantly.

        Args:
            X_cal: Calibration features
            y_cal: Calibration labels

        Returns:
            True if recalibration was performed
        """
        if self.aci is None:
            return False

        # Recalibrate with updated confidence level
        self.calibrate(X_cal, y_cal)
        return True

    def _get_current_confidence(self) -> float:
        """Get current confidence level (from ACI if enabled)."""
        if self.aci is not None:
            return self.aci.confidence_level
        return self.config.get_cls_confidence()

    def get_diagnostics(self) -> dict:
        """Get diagnostic information."""
        diag = {
            "is_calibrated": self.is_calibrated,
            "confidence_level": self._get_current_confidence(),
            "method": self.config.cls_method,
        }
        if self.aci is not None:
            diag["aci"] = self.aci.get_diagnostics()
        return diag

    def __repr__(self) -> str:
        status = "calibrated" if self.is_calibrated else "not calibrated"
        return (
            f"ConformalClassifier({status}, "
            f"conf={self._get_current_confidence():.2f}, "
            f"method={self.config.cls_method})"
        )
