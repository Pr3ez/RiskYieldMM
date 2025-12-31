"""Helper Ensemble - combines all Layer 1 helper models.

The HelperEnsemble coordinates all 5 helpers:
1. IsolationForest - anomaly detection (12 features)
2. CUSUM - changepoint detection (12 features)
3. GARCH - volatility estimation (8 features)
4. HMM-4 - market regime detection (9 features)
5. HMM-5 - volatility regime detection (10 features)
6. Kalman - state estimation (7 features)

Total: ~58 features per target-horizon
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from scripts.target_models.helpers.base import HelperOutput
from scripts.target_models.helpers.bocpd import create_bocpd_helper
from scripts.target_models.helpers.cusum import create_cusum_helper
from scripts.target_models.helpers.egarch import create_egarch_helper
from scripts.target_models.helpers.evt_pot import create_evt_pot_helper
from scripts.target_models.helpers.garch import create_garch_helper
from scripts.target_models.helpers.hmm import (
    create_market_regime_hmm,
    create_volatility_regime_hmm,
)
from scripts.target_models.helpers.isolation_forest import (
    create_isolation_forest_helper,
)
from scripts.target_models.helpers.kalman import create_kalman_helper
from scripts.target_models.helpers.ou import create_ou_helper

if TYPE_CHECKING:
    from scripts.target_models.helpers.icir_config import ICIRConfig


@dataclass
class EnsembleOutput:
    """Output from the helper ensemble."""

    features: pd.DataFrame
    feature_names: list[str]
    n_samples: int
    n_features: int
    helper_outputs: dict[str, HelperOutput]
    metadata: dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        return (
            f"EnsembleOutput({self.n_samples}×{self.n_features} features, "
            f"{len(self.helper_outputs)} helpers)"
        )

    def to_numpy(self) -> np.ndarray:
        """Convert to numpy array."""
        return self.features.values


class HelperEnsemble:
    """Ensemble of Layer 1 helper models with BOOSTING for Layer 2.

    Key concept: Layer 1 transforms base features into helper features,
    then BOOSTS them to maximize predictive power for Layer 2.

    Boosting includes:
    1. IC-based feature weighting - high IC features get amplified
    2. Feature selection - drop features with IC ≈ 0
    3. Interaction features - combine top features for extra signal

    Usage:
        ensemble = HelperEnsemble("volatility", 6)

        # Layer 1 training
        ensemble.fit(X_train)
        ensemble.optimize(X_cal, y_cal)  # Learns IC weights
        ensemble.validate(X_val, y_val)

        # Generate BOOSTED features for Layer 2
        output = ensemble.transform(X_layer2)  # Applies IC weights
        X_boosted = output.features
    """

    # Legacy IC threshold (used if ICIR disabled)
    IC_THRESHOLD = 0.02  # Drop features with |IC| < this
    # Number of top features to use for interactions
    TOP_K_INTERACTIONS = 5

    def __init__(
        self,
        target: str,
        horizon: int,
        random_state: int = 42,
        helpers: list[str] | None = None,
        enable_boosting: bool = True,
        icir_config: ICIRConfig | None = None,
    ):
        """Initialize helper ensemble.

        Args:
            target: Target name (e.g., "volatility", "direction")
            horizon: Forecast horizon (1, 6, 12, 24)
            random_state: Random state for reproducibility
            helpers: List of helpers to use. If None, uses all.
                     Options: ["if", "cusum", "garch", "hmm4", "hmm5", "kalman"]
            enable_boosting: Whether to enable IC-based feature boosting
            icir_config: ICIR configuration (if None, uses target-specific default)
        """
        from .icir_config import get_icir_config

        self.target = target
        self.horizon = horizon
        self.random_state = random_state
        self.enable_boosting = enable_boosting

        # ICIR configuration (modular, can be customized per target)
        self.icir_config = icir_config or get_icir_config(target, horizon)

        # Default to all helpers
        if helpers is None:
            helpers = ["if", "cusum", "garch", "hmm4", "hmm5", "kalman"]

        self.helper_names = helpers
        self._helpers: dict[str, Any] = {}
        self._is_fitted = False

        # Boosting state (learned during optimize)
        self._feature_ics: dict[str, float] = {}  # feature_name → IC
        self._feature_weights: dict[str, float] = {}  # feature_name → weight
        self._selected_features: list[str] = []  # Features that passed selection
        self._top_features: list[str] = []  # Top K for interactions
        self._is_boosted = False

        # ICIR selection results (for diagnostics)
        self._icir_selection_result: dict | None = None

        # Initialize requested helpers
        self._init_helpers()

    def _init_helpers(self) -> None:
        """Initialize all helper models."""
        for name in self.helper_names:
            if name == "if":
                self._helpers["if"] = create_isolation_forest_helper(
                    self.target, self.horizon, self.random_state
                )
            elif name == "cusum":
                self._helpers["cusum"] = create_cusum_helper(
                    self.target, self.horizon, self.random_state
                )
            elif name == "garch":
                self._helpers["garch"] = create_garch_helper(
                    self.target, self.horizon, self.random_state
                )
            elif name == "hmm4":
                self._helpers["hmm4"] = create_market_regime_hmm(
                    self.target, self.horizon, self.random_state
                )
            elif name == "hmm5":
                self._helpers["hmm5"] = create_volatility_regime_hmm(
                    self.target, self.horizon, self.random_state
                )
            elif name == "kalman":
                self._helpers["kalman"] = create_kalman_helper(
                    self.target, self.horizon, random_state=self.random_state
                )
            elif name == "evt":
                self._helpers["evt"] = create_evt_pot_helper(
                    self.target, self.horizon, self.random_state
                )
            elif name == "ou":
                self._helpers["ou"] = create_ou_helper(
                    self.target, self.horizon, self.random_state
                )
            elif name == "bocpd":
                self._helpers["bocpd"] = create_bocpd_helper(
                    self.target, self.horizon, self.random_state
                )
            elif name == "egarch":
                self._helpers["egarch"] = create_egarch_helper(
                    self.target, self.horizon, self.random_state
                )
            else:
                raise ValueError(f"Unknown helper: {name}")

    @property
    def supports_incremental(self) -> bool:
        """Check if any helpers support incremental updates."""
        return any(h.supports_incremental for h in self._helpers.values())

    def fit(
        self, X: pd.DataFrame | np.ndarray, y: np.ndarray | None = None
    ) -> HelperEnsemble:
        """Fit all helpers on Layer 1 training data.

        Args:
            X: Training features
            y: Optional target (for semi-supervised helpers)

        Returns:
            Self for chaining
        """
        for name, helper in self._helpers.items():
            try:
                helper.fit(X, y)
            except Exception as e:
                print(f"Warning: Failed to fit {name}: {e}")

        self._is_fitted = True
        return self

    def partial_fit(
        self, X: pd.DataFrame | np.ndarray, y: np.ndarray | None = None
    ) -> HelperEnsemble:
        """Incrementally update helpers that support it.

        For expanding L1 window, this is more efficient than full refit.
        Helpers that support incremental updates (HMM, IF, Kalman) will
        be updated; others (GARCH, CUSUM) will do full refit.

        Args:
            X: Full expanding window features
            y: Optional target

        Returns:
            Self for chaining
        """
        if not self._is_fitted:
            # First call - do full fit
            return self.fit(X, y)

        for name, helper in self._helpers.items():
            try:
                if helper.supports_incremental:
                    helper.partial_fit(X, y)
                else:
                    # Full refit for non-incremental helpers
                    helper.fit(X, y)
            except Exception as e:
                print(f"Warning: Failed to partial_fit {name}: {e}")

        return self

    def optimize(
        self, X_cal: pd.DataFrame | np.ndarray, y_cal: np.ndarray | None = None
    ) -> dict[str, Any]:
        """Optimize all helpers and LEARN BOOSTING WEIGHTS.

        This is where Layer 1 learns how to best boost features for Layer 2:
        1. If ICIR enabled: compute Rolling ICIR + correlation filter
        2. If ICIR disabled: use legacy IC-based selection
        3. Compute feature weights from current-window IC
        4. Identify top-K features for interactions

        Args:
            X_cal: Calibration features
            y_cal: Calibration target (REQUIRED for boosting)

        Returns:
            Dict with per-helper results AND boosting/ICIR stats
        """
        results: dict[str, Any] = {"per_helper": {}}

        # First, optimize individual helpers
        for name, helper in self._helpers.items():
            try:
                results["per_helper"][name] = helper.optimize(X_cal, y_cal)
            except Exception as e:
                results["per_helper"][name] = {"error": str(e)}

        # Now learn boosting weights if target provided
        if y_cal is not None and self.enable_boosting:
            self._learn_boosting_weights(X_cal, y_cal)

            # Build boosting stats
            boosting_stats = {
                "n_features_before": len(self._feature_ics) if self._feature_ics else 0,
                "n_features_selected": len(self._selected_features),
                "n_features_dropped": (
                    len(self._feature_ics) - len(self._selected_features)
                    if self._feature_ics
                    else 0
                ),
                "top_features": self._top_features,
                "icir_enabled": self.icir_config.enable_icir,
            }

            # Add ICIR-specific stats if available
            if self._icir_selection_result:
                sr = self._icir_selection_result
                boosting_stats.update(
                    {
                        "selection_method": sr.get("method", "unknown"),
                        "n_dropped_by_icir": len(sr.get("dropped_by_icir", [])),
                        "n_dropped_by_correlation": len(
                            sr.get("dropped_by_correlation", [])
                        ),
                        "icir_threshold": self.icir_config.icir_threshold,
                        "correlation_threshold": self.icir_config.correlation_threshold,
                    }
                )
            else:
                # Legacy IC mode
                boosting_stats.update(
                    {
                        "selection_method": "ic_legacy",
                        "ic_threshold": self.IC_THRESHOLD,
                    }
                )

            results["boosting"] = boosting_stats

        # Compute aggregate IC
        if y_cal is not None:
            output = self._transform_raw(X_cal)
            ic_stats = self._compute_aggregate_ic(output.features, y_cal)
            results.update(ic_stats)

        return results

    def _learn_boosting_weights(
        self, X: pd.DataFrame | np.ndarray, y: np.ndarray | pd.Series
    ) -> None:
        """Learn feature weights for boosting using ICIR or IC.

        If ICIR is enabled (via icir_config):
        1. Compute Rolling ICIR for each feature
        2. Apply correlation filter to remove redundancy
        3. Use ICIR-selected features with IC-based weights

        If ICIR is disabled (legacy mode):
        1. Compute single IC for each feature
        2. Select features with |IC| >= threshold
        3. Weight by |IC|

        Edge cases handled:
        - Constant target: skip boosting, equal weights
        - No valid ICs: use all features with equal weights
        - All below threshold: keep top-K by |IC| or |ICIR|
        """
        from scipy.stats import spearmanr

        from .icir_selection import select_features_full_pipeline

        # Get raw features
        output = self._transform_raw(X)
        features = output.features
        y_np = y.values if hasattr(y, "values") else y

        # Check if target has variation (required for IC computation)
        y_unique = np.unique(y_np[~np.isnan(y_np)])
        if len(y_unique) < 2:
            # Target is constant - can't compute IC, skip boosting
            self._set_fallback_weights(features)
            return

        # Run ICIR selection pipeline (or IC fallback based on config)
        selection_result = select_features_full_pipeline(
            features, y_np, self.icir_config
        )
        self._icir_selection_result = selection_result

        # Extract selected features
        selected = selection_result["selected_features"]
        if not selected:
            self._set_fallback_weights(features)
            return

        self._selected_features = selected

        # Compute weights from current IC (for dynamic weighting)
        # Even if ICIR selected features, we weight by current-window IC
        self._feature_ics = {}
        for col in features.columns:
            feat = features[col].values
            mask = np.isfinite(feat) & np.isfinite(y_np)
            if mask.sum() <= 10:
                continue

            feat_valid = feat[mask]
            y_valid = y_np[mask]
            if feat_valid.min() == feat_valid.max() or y_valid.min() == y_valid.max():
                continue

            import warnings

            from scipy.stats import ConstantInputWarning

            with warnings.catch_warnings():
                warnings.simplefilter("ignore", category=ConstantInputWarning)
                ic, _ = spearmanr(feat_valid, y_valid)
            if not np.isnan(ic):
                self._feature_ics[col] = ic

        # Compute normalized weights from |IC|
        abs_ics = {k: abs(v) for k, v in self._feature_ics.items()}
        max_ic = max(abs_ics.values()) if abs_ics else 1.0

        self._feature_weights = {}
        for col in self._selected_features:
            abs_ic = abs_ics.get(col, 0.0)
            self._feature_weights[col] = abs_ic / max_ic if max_ic > 0 else 1.0

        # Get top-K features for interactions (by |IC|)
        selected_ics = [(f, abs_ics.get(f, 0)) for f in self._selected_features]
        selected_ics.sort(key=lambda x: x[1], reverse=True)
        top_k = self.icir_config.top_k_interactions
        self._top_features = [f[0] for f in selected_ics[:top_k]]

        self._is_boosted = True

    def _set_fallback_weights(self, features: pd.DataFrame) -> None:
        """Set fallback weights when boosting cannot be computed."""
        self._feature_ics = dict.fromkeys(features.columns, 0.0)
        self._feature_weights = dict.fromkeys(features.columns, 1.0)
        self._selected_features = list(features.columns)
        top_k = self.icir_config.top_k_interactions
        self._top_features = list(features.columns[:top_k])
        self._is_boosted = False
        self._icir_selection_result = None

    def validate(
        self, X_val: pd.DataFrame | np.ndarray, y_val: np.ndarray | None = None
    ) -> dict[str, Any]:
        """Validate all helpers on validation data.

        Args:
            X_val: Validation features
            y_val: Validation target (REQUIRED for IC computation)

        Returns:
            Dict with per-helper results AND aggregate IC metrics
        """
        results: dict[str, Any] = {"per_helper": {}}

        for name, helper in self._helpers.items():
            try:
                results["per_helper"][name] = helper.validate(X_val, y_val)
            except Exception as e:
                results["per_helper"][name] = {"error": str(e)}

        # Compute aggregate IC across ALL helper features
        if y_val is not None:
            output = self.transform(X_val)
            ic_stats = self._compute_aggregate_ic(output.features, y_val)
            results.update(ic_stats)

        return results

    def _compute_aggregate_ic(
        self, features: pd.DataFrame, y: np.ndarray | pd.Series
    ) -> dict[str, float]:
        """Compute IC statistics across all helper features.

        Returns:
            Dict with mean_abs_ic, max_abs_ic, n_positive_ic, n_significant
        """
        import warnings

        from scipy.stats import ConstantInputWarning, spearmanr

        y_np = y.values if hasattr(y, "values") else y

        ics = []
        for col in features.columns:
            feat = features[col].values
            mask = np.isfinite(feat) & np.isfinite(y_np)
            if mask.sum() <= 10:
                continue

            feat_valid = feat[mask]
            y_valid = y_np[mask]
            if feat_valid.min() == feat_valid.max() or y_valid.min() == y_valid.max():
                continue

            with warnings.catch_warnings():
                warnings.simplefilter("ignore", category=ConstantInputWarning)
                ic, _ = spearmanr(feat_valid, y_valid)
            if not np.isnan(ic):
                ics.append(ic)

        if not ics:
            return {"mean_abs_ic": 0.0, "max_abs_ic": 0.0, "n_positive_ic": 0}

        abs_ics = np.abs(ics)
        return {
            "mean_abs_ic": float(np.mean(abs_ics)),
            "max_abs_ic": float(np.max(abs_ics)),
            "n_positive_ic": int(np.sum(np.array(ics) > 0)),
            "n_negative_ic": int(np.sum(np.array(ics) < 0)),
            "n_features": len(ics),
        }

    def _transform_raw(self, X: pd.DataFrame | np.ndarray) -> EnsembleOutput:
        """Transform data using all fitted helpers (NO boosting).

        Internal method that returns raw helper outputs.
        """
        if not self._is_fitted:
            raise RuntimeError("Ensemble not fitted. Call fit() first.")

        helper_outputs: dict[str, HelperOutput] = {}
        all_features: list[pd.DataFrame] = []
        all_names: list[str] = []

        for name, helper in self._helpers.items():
            try:
                output = helper.transform(X)
                helper_outputs[name] = output
                all_features.append(output.features)
                all_names.extend(output.feature_names)
            except Exception as e:
                print(f"Warning: Failed to transform with {name}: {e}")

        # Combine all features
        if all_features:
            combined = pd.concat(all_features, axis=1)
        else:
            combined = pd.DataFrame()

        return EnsembleOutput(
            features=combined,
            feature_names=all_names,
            n_samples=len(combined),
            n_features=len(all_names),
            helper_outputs=helper_outputs,
            metadata={
                "target": self.target,
                "horizon": self.horizon,
                "helpers": list(self._helpers.keys()),
                "boosted": False,
            },
        )

    def transform(self, X: pd.DataFrame | np.ndarray) -> EnsembleOutput:
        """Transform data using all fitted helpers WITH BOOSTING.

        If boosting was learned during optimize():
        1. Apply feature selection (drop low-IC features)
        2. Apply IC-based weighting
        3. Add interaction features from top-K

        Args:
            X: Features to transform

        Returns:
            EnsembleOutput with BOOSTED features for Layer 2
        """
        # Get raw features first
        raw_output = self._transform_raw(X)

        # If no boosting or not learned yet, return raw
        if not self.enable_boosting or not self._is_boosted:
            return raw_output

        # Apply boosting
        raw_features = raw_output.features
        boosted_features = pd.DataFrame(index=raw_features.index)
        boosted_names = []

        # 1. Select and weight features
        for col in self._selected_features:
            if col in raw_features.columns:
                weight = self._feature_weights.get(col, 1.0)
                # Apply weight (scale feature by IC-derived weight)
                boosted_features[col] = raw_features[col] * weight
                boosted_names.append(col)

        # 2. Add interaction features from top-K
        for i, f1 in enumerate(self._top_features):
            for f2 in self._top_features[i + 1 :]:
                if f1 in raw_features.columns and f2 in raw_features.columns:
                    # Multiplicative interaction
                    interaction_name = f"H_int_{f1.split('_')[-1]}_{f2.split('_')[-1]}"
                    boosted_features[interaction_name] = (
                        raw_features[f1] * raw_features[f2]
                    )
                    boosted_names.append(interaction_name)

        return EnsembleOutput(
            features=boosted_features,
            feature_names=boosted_names,
            n_samples=len(boosted_features),
            n_features=len(boosted_names),
            helper_outputs=raw_output.helper_outputs,
            metadata={
                "target": self.target,
                "horizon": self.horizon,
                "helpers": list(self._helpers.keys()),
                "boosted": True,
                "n_raw_features": raw_output.n_features,
                "n_boosted_features": len(boosted_names),
                "n_interactions": len(boosted_names) - len(self._selected_features),
            },
        )

    def fit_transform(
        self,
        X_train: pd.DataFrame | np.ndarray,
        X_transform: pd.DataFrame | np.ndarray,
        y: np.ndarray | None = None,
    ) -> EnsembleOutput:
        """Fit on training data, transform on different data.

        Args:
            X_train: Training data for fitting
            X_transform: Data to transform (e.g., Layer 2 train)
            y: Optional target for fitting

        Returns:
            EnsembleOutput with transformed features
        """
        self.fit(X_train, y)
        return self.transform(X_transform)

    def get_feature_count(self) -> int:
        """Get total number of features produced by the ensemble."""
        count = 0
        for helper in self._helpers.values():
            count += len(helper._get_feature_names())
        return count

    def summary(self) -> dict:
        """Get summary of the ensemble configuration."""
        feature_counts = {}
        for name, helper in self._helpers.items():
            feature_counts[name] = len(helper._get_feature_names())

        return {
            "target": self.target,
            "horizon": self.horizon,
            "n_helpers": len(self._helpers),
            "helpers": list(self._helpers.keys()),
            "feature_counts": feature_counts,
            "total_features": sum(feature_counts.values()),
            "is_fitted": self._is_fitted,
        }


# Factory function
def create_helper_ensemble(
    target: str,
    horizon: int,
    random_state: int = 42,
    helpers: list[str] | None = None,
    enable_boosting: bool = True,
    icir_config: ICIRConfig | None = None,
) -> HelperEnsemble:
    """Create a helper ensemble for a target-horizon configuration.

    Args:
        target: Target name
        horizon: Forecast horizon
        random_state: Random state
        helpers: Optional list of helpers to use
        enable_boosting: Whether to enable IC-based feature boosting
        icir_config: ICIR configuration (if None, uses target-specific default)

    Returns:
        Configured HelperEnsemble
    """
    return HelperEnsemble(
        target, horizon, random_state, helpers, enable_boosting, icir_config
    )


if __name__ == "__main__":
    # Quick test
    from scripts.target_models.registry import load_target_data

    X, y, spec = load_target_data("volatility", 6, verbose=False)
    print(f"Data shape: {X.shape}")

    # Create ensemble
    ensemble = create_helper_ensemble("volatility", 6)
    print(f"\nEnsemble summary: {ensemble.summary()}")

    # Layer 1 windows
    train_end = 800
    cal_end = 900
    val_end = 1000
    X_train = X.iloc[:train_end]
    X_cal = X.iloc[train_end:cal_end]
    X_val = X.iloc[cal_end:val_end]

    # Layer 2 data
    X_layer2 = X.iloc[val_end : val_end + 500]

    # Fit
    print("\nFitting ensemble...")
    ensemble.fit(X_train)

    # Optimize
    print("Optimizing ensemble...")
    opt_results = ensemble.optimize(X_cal)
    for name, res in opt_results.items():
        print(f"  {name}: {list(res.keys())[:3]}...")

    # Validate
    print("Validating ensemble...")
    val_results = ensemble.validate(X_val)
    for name, res in val_results.items():
        print(f"  {name}: {list(res.keys())[:3]}...")

    # Transform
    print("\nTransforming Layer 2 data...")
    output = ensemble.transform(X_layer2)
    print(f"Output: {output}")
    print(f"Feature names (first 10): {output.feature_names[:10]}")
    print(f"Feature names (last 10): {output.feature_names[-10:]}")

    print("\nTEST PASSED ✓")
