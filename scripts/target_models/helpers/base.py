"""
Base classes for Layer 1 helper models.

Provides:
- BaseHelper: Abstract base class with common interface
- HelperConfig: Configuration dataclass for helpers
- HelperOutput: Container for helper-generated features

Incremental Training Support:
- supports_incremental: Property indicating if helper can be incrementally updated
- partial_fit(): Update model with new data without full retraining
- Used by expanding L1 window to efficiently update helpers each iteration
"""

import warnings
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
import pandas as pd
import polars as pl


# =============================================================================
# CONFIGURATION
# =============================================================================
@dataclass
class HelperConfig:
    """
    Configuration for a helper model.

    Contains both model-specific params and target-horizon context.
    """

    # Target-horizon context
    target: str = ""
    horizon: int = 1
    task_type: Literal["regression", "binary", "multiclass"] = "regression"

    # Common helper settings
    random_state: int = 42
    verbose: bool = False

    # Feature generation control
    prefix: str = ""  # Prefix for generated feature names

    @property
    def identifier(self) -> str:
        return f"{self.target}_{self.horizon}bar"


# =============================================================================
# OUTPUT CONTAINER
# =============================================================================
@dataclass
class HelperOutput:
    """
    Container for helper-generated features.

    Provides consistent interface for combining outputs from
    multiple helpers into enriched feature set.
    """

    features: pd.DataFrame  # Generated features (n_samples × n_features)
    feature_names: list[str]  # Names of generated features
    helper_name: str  # Name of helper that generated these
    metadata: dict[str, Any] = field(default_factory=dict)  # Optional metadata

    @property
    def n_samples(self) -> int:
        return len(self.features)

    @property
    def n_features(self) -> int:
        return len(self.feature_names)

    def to_polars(self) -> pl.DataFrame:
        """Convert to Polars DataFrame."""
        return pl.from_pandas(self.features)

    def to_numpy(self) -> np.ndarray:
        """Convert to numpy array."""
        return self.features.values

    def __repr__(self) -> str:
        return (
            f"HelperOutput({self.helper_name}: "
            f"{self.n_samples}×{self.n_features} features)"
        )


# =============================================================================
# BASE HELPER CLASS
# =============================================================================
class BaseHelper(ABC):
    """
    Abstract base class for all Layer 1 helper models.

    Helpers are unsupervised or semi-supervised models that:
    1. Fit on Layer 1 train window
    2. Optionally optimize hyperparameters on Layer 1 cal window
    3. Validate quality on Layer 1 val window
    4. Generate features for Layer 2 data (train, cal, val, pred)

    Subclasses must implement:
    - _fit_impl: Core fitting logic
    - _transform_impl: Core feature generation logic
    - _get_feature_names: Names of features generated
    - helper_name: Unique identifier for this helper
    """

    def __init__(self, config: HelperConfig | None = None):
        self.config = config or HelperConfig()
        self.is_fitted = False
        self._fit_params: dict[str, Any] = {}
        self._n_samples_seen: int = 0  # Track samples seen for incremental

    # =========================================================================
    # INCREMENTAL TRAINING SUPPORT
    # =========================================================================
    @property
    def supports_incremental(self) -> bool:
        """
        Whether this helper supports incremental/partial fitting.

        Override in subclass to return True if the helper can be
        updated with new data without full retraining.

        Default: False (full refit required)
        """
        return False

    def partial_fit(
        self,
        X: pd.DataFrame | np.ndarray,
        y: pd.Series | np.ndarray | None = None,
    ) -> "BaseHelper":
        """
        Incrementally update helper with new data.

        For expanding L1 window, this is called each iteration with
        the full expanding window. The helper should efficiently
        update using only the new data when possible.

        If supports_incremental is False, this just calls fit().

        Args:
            X: Feature matrix (full expanding window)
            y: Optional target

        Returns:
            self (for chaining)
        """
        if not self.supports_incremental:
            # Fall back to full refit
            return self.fit(X, y)

        # Convert to numpy
        X_np = X.values if isinstance(X, pd.DataFrame) else X
        y_np = y.values if isinstance(y, pd.Series) else y

        n_new_samples = X_np.shape[0]

        if not self.is_fitted:
            # First call - do full fit
            return self.fit(X, y)

        # Check if we have new data
        if n_new_samples <= self._n_samples_seen:
            # No new data, skip update
            return self

        # Call subclass implementation for incremental update
        self._partial_fit_impl(X_np, y_np, self._n_samples_seen)

        # Update sample count
        self._n_samples_seen = n_new_samples

        return self

    def _partial_fit_impl(
        self,
        X: np.ndarray,
        y: np.ndarray | None,
        n_samples_seen: int,
    ) -> None:
        """
        Core incremental fitting logic (override in subclass).

        Only called if supports_incremental is True.

        Args:
            X: Full feature matrix (n_samples, n_features)
            y: Optional target
            n_samples_seen: Number of samples from previous fit
                           (new data is X[n_samples_seen:])
        """
        # Default: refit on full data
        self._fit_impl(X, y)

    # =========================================================================
    # ABSTRACT METHODS (must implement)
    # =========================================================================
    @property
    @abstractmethod
    def helper_name(self) -> str:
        """Unique name identifier for this helper (e.g., 'hmm4', 'garch')."""
        pass

    @abstractmethod
    def _fit_impl(self, X: np.ndarray, y: np.ndarray | None = None) -> None:
        """
        Core fitting logic (implemented by subclass).

        Args:
            X: Feature matrix (n_samples, n_features)
            y: Optional target (for semi-supervised helpers)
        """
        pass

    @abstractmethod
    def _transform_impl(self, X: np.ndarray) -> np.ndarray:
        """
        Core feature generation logic (implemented by subclass).

        Args:
            X: Feature matrix (n_samples, n_features)

        Returns:
            Generated features (n_samples, n_generated_features)
        """
        pass

    @abstractmethod
    def _get_feature_names(self) -> list[str]:
        """
        Get names of features this helper generates.

        Returns:
            List of feature names (with appropriate prefix)
        """
        pass

    # =========================================================================
    # PUBLIC API
    # =========================================================================
    def fit(
        self,
        X: pd.DataFrame | np.ndarray,
        y: pd.Series | np.ndarray | None = None,
    ) -> "BaseHelper":
        """
        Fit helper on training data.

        Args:
            X: Feature matrix (pandas DataFrame or numpy array)
            y: Optional target (for semi-supervised helpers)

        Returns:
            self (for chaining)
        """
        # Convert to numpy for consistent processing
        X_np = X.values if isinstance(X, pd.DataFrame) else X
        y_np = y.values if isinstance(y, pd.Series) else y

        # Store input shape for validation
        self._n_features_in = X_np.shape[1]

        # Call subclass implementation
        self._fit_impl(X_np, y_np)

        # Track samples seen for incremental updates
        self._n_samples_seen = X_np.shape[0]

        self.is_fitted = True
        return self

    def transform(
        self,
        X: pd.DataFrame | np.ndarray,
    ) -> HelperOutput:
        """
        Generate features for given data.

        Args:
            X: Feature matrix (pandas DataFrame or numpy array)

        Returns:
            HelperOutput containing generated features
        """
        if not self.is_fitted:
            raise RuntimeError(f"{self.helper_name} not fitted. Call fit() first.")

        # Convert to numpy
        X_np = X.values if isinstance(X, pd.DataFrame) else X

        # Validate shape
        if X_np.shape[1] != self._n_features_in:
            raise ValueError(
                f"X has {X_np.shape[1]} features, but {self.helper_name} "
                f"was fitted with {self._n_features_in} features"
            )

        # Call subclass implementation
        features_np = self._transform_impl(X_np)

        # Get feature names
        feature_names = self._get_feature_names()

        # Validate output shape
        if features_np.shape[1] != len(feature_names):
            raise RuntimeError(
                f"{self.helper_name}._transform_impl returned {features_np.shape[1]} "
                f"features but _get_feature_names returned {len(feature_names)} names"
            )

        # Convert to DataFrame
        features_df = pd.DataFrame(features_np, columns=feature_names)

        return HelperOutput(
            features=features_df,
            feature_names=feature_names,
            helper_name=self.helper_name,
            metadata={
                "config": self.config,
                "fit_params": self._fit_params,
            },
        )

    def fit_transform(
        self,
        X: pd.DataFrame | np.ndarray,
        y: pd.Series | np.ndarray | None = None,
    ) -> HelperOutput:
        """Fit and transform in one call."""
        return self.fit(X, y).transform(X)

    # =========================================================================
    # OPTIONAL METHODS (can override)
    # =========================================================================
    def optimize(
        self,
        X_cal: pd.DataFrame | np.ndarray,
        y_cal: pd.Series | np.ndarray | None = None,
    ) -> dict[str, Any]:
        """
        Optimize hyperparameters on calibration data.

        Default implementation computes IC (information coefficient) between
        helper features and target y. Override in subclass for more
        sophisticated optimization.

        Args:
            X_cal: Calibration features
            y_cal: Calibration targets (REQUIRED for target-aware optimization)

        Returns:
            Dict with optimization results including feature ICs
        """
        if y_cal is None:
            return {"warning": "No target provided, skipping optimization"}

        # Generate features for calibration data
        output = self.transform(X_cal)
        features = output.features

        # Convert y to numpy
        y_np = y_cal.values if hasattr(y_cal, "values") else y_cal

        # Compute IC (Spearman correlation) for each feature
        from scipy.stats import ConstantInputWarning, spearmanr

        feature_ics = {}
        for col in features.columns:
            feat = features[col].values
            # Remove non-finite pairs (NaN/Inf)
            mask = np.isfinite(feat) & np.isfinite(y_np)
            if mask.sum() <= 10:  # Need enough samples
                feature_ics[col] = 0.0
                continue

            feat_valid = feat[mask]
            y_valid = y_np[mask]

            # If either side is constant, Spearman IC is undefined (no signal).
            if feat_valid.min() == feat_valid.max() or y_valid.min() == y_valid.max():
                feature_ics[col] = 0.0
                continue

            with warnings.catch_warnings():
                warnings.simplefilter("ignore", category=ConstantInputWarning)
                ic, _ = spearmanr(feat_valid, y_valid)
            feature_ics[col] = float(ic) if not np.isnan(ic) else 0.0

        # Store for later use
        self._fit_params["feature_ics"] = feature_ics
        self._fit_params["mean_abs_ic"] = np.mean(np.abs(list(feature_ics.values())))

        return {
            "feature_ics": feature_ics,
            "mean_abs_ic": self._fit_params["mean_abs_ic"],
            "n_features": len(feature_ics),
        }

    def validate(
        self,
        X_val: pd.DataFrame | np.ndarray,
        y_val: pd.Series | np.ndarray | None = None,
    ) -> dict[str, float]:
        """
        Validate helper quality on validation data.

        Default implementation computes IC on validation set to check
        for overfitting vs calibration set. Override in subclass
        for helper-specific metrics.

        Args:
            X_val: Validation features
            y_val: Validation targets (REQUIRED for IC computation)

        Returns:
            Dict of validation metrics including IC
        """
        if y_val is None:
            return {"warning": "No target provided, skipping validation"}

        # Generate features for validation data
        output = self.transform(X_val)
        features = output.features

        # Convert y to numpy
        y_np = y_val.values if hasattr(y_val, "values") else y_val

        # Compute IC for each feature
        from scipy.stats import ConstantInputWarning, spearmanr

        feature_ics = {}
        for col in features.columns:
            feat = features[col].values
            mask = np.isfinite(feat) & np.isfinite(y_np)
            if mask.sum() <= 10:
                feature_ics[col] = 0.0
                continue

            feat_valid = feat[mask]
            y_valid = y_np[mask]
            if feat_valid.min() == feat_valid.max() or y_valid.min() == y_valid.max():
                feature_ics[col] = 0.0
                continue

            with warnings.catch_warnings():
                warnings.simplefilter("ignore", category=ConstantInputWarning)
                ic, _ = spearmanr(feat_valid, y_valid)
            feature_ics[col] = float(ic) if not np.isnan(ic) else 0.0

        mean_abs_ic = np.mean(np.abs(list(feature_ics.values())))

        # Compare to calibration IC if available
        cal_ic = self._fit_params.get("mean_abs_ic", None)
        ic_degradation = None
        if cal_ic is not None and cal_ic > 0:
            ic_degradation = (cal_ic - mean_abs_ic) / cal_ic

        return {
            "val_mean_abs_ic": mean_abs_ic,
            "cal_mean_abs_ic": cal_ic,
            "ic_degradation": ic_degradation,
            "n_features": len(feature_ics),
        }

    def get_params(self) -> dict[str, Any]:
        """
        Get current hyperparameters.

        Default returns fit_params. Override for more detail.
        """
        return {
            "helper_name": self.helper_name,
            "is_fitted": self.is_fitted,
            **self._fit_params,
        }

    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    def _make_feature_name(self, name: str) -> str:
        """Create feature name with helper prefix."""
        prefix = self.config.prefix or self.helper_name
        return f"H_{prefix}_{name}"

    def __repr__(self) -> str:
        status = "fitted" if self.is_fitted else "not fitted"
        return f"{self.__class__.__name__}({self.helper_name}, {status})"


# =============================================================================
# HELPER FACTORY
# =============================================================================
def get_helper_config(
    target: str,
    horizon: int,
    task_type: str = "regression",
) -> HelperConfig:
    """
    Create HelperConfig for a specific target-horizon.

    Args:
        target: Target name (volatility, direction, etc.)
        horizon: Prediction horizon (1, 3, 6, 12)
        task_type: Task type (regression, binary, multiclass)

    Returns:
        HelperConfig configured for this target-horizon
    """
    return HelperConfig(
        target=target,
        horizon=horizon,
        task_type=task_type,
        prefix=f"{target[:3]}_{horizon}",  # e.g., "vol_6"
    )
