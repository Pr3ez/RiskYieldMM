"""Hidden Markov Model helpers for regime detection.

HMM-4: Market regime (4 states: bullish, bearish, neutral, volatile)
HMM-5: Volatility regime (5 states: very_low to very_high)

Uses hmmlearn for implementation with Gaussian emissions.
Rust backend available for ~10-20x speedup.
"""

from __future__ import annotations

import logging
import warnings

import numpy as np
import pandas as pd
from hmmlearn import hmm

# Try to import Rust backend
try:
    import riskyield_rust

    HAS_RUST = True
except ImportError:
    HAS_RUST = False

# Suppress hmmlearn's verbose logging about transmat_ zero sum rows
# This warning is expected when some HMM states are rarely visited in early iterations
# We already handle this properly in _sanitize_fitted_model()
logging.getLogger("hmmlearn.base").setLevel(logging.ERROR)

from scripts.target_models.helpers.base import BaseHelper, HelperConfig


class HMMHelper(BaseHelper):
    """Hidden Markov Model for regime detection.

    Detects hidden regimes in the data using Gaussian HMM.
    Outputs regime probabilities and regime-based features.

    Rust backend available for ~10-20x speedup when HAS_RUST=True.
    """

    def __init__(
        self,
        config: HelperConfig,
        n_states: int = 4,
        regime_type: str = "market",
        n_iter: int = 100,
        covariance_type: str = "diag",
        use_rust: bool = True,
    ):
        """Initialize HMM helper.

        Args:
            config: Helper configuration
            n_states: Number of hidden states (4 for market, 5 for volatility)
            regime_type: Type of regime detection ("market" or "volatility")
            n_iter: Number of EM iterations for fitting
            covariance_type: Covariance type ('diag', 'full', 'spherical', 'tied')
            use_rust: Whether to use Rust backend if available (default: True)
        """
        super().__init__(config)
        self.n_states = n_states
        self.regime_type = regime_type
        self.n_iter = n_iter
        self.covariance_type = covariance_type
        self.model: hmm.GaussianHMM | None = None
        self._model_fitted = False
        self._incremental_n_iter = 20  # Fewer iterations for incremental updates
        self._use_rust = use_rust and HAS_RUST
        self._rust_seed = config.random_state if config.random_state is not None else 42

        # State labels for interpretability
        if regime_type == "market" and n_states == 4:
            self.state_labels = ["bullish", "bearish", "neutral", "volatile"]
        elif regime_type == "volatility" and n_states == 5:
            self.state_labels = ["very_low", "low", "medium", "high", "very_high"]
        else:
            self.state_labels = [f"state_{i}" for i in range(n_states)]

    @property
    def supports_incremental(self) -> bool:
        """HMM supports incremental training via init_params=''."""
        return True

    @property
    def helper_name(self) -> str:
        """Unique name identifier for this helper."""
        return f"hmm{self.n_states}"

    def _prepare_observations(self, X: np.ndarray) -> np.ndarray:
        """Prepare observation sequence for HMM.

        For market regime: use returns and volatility
        For volatility regime: use absolute returns and rolling vol
        """
        if self.regime_type == "market":
            # Compute pseudo-returns from first column
            col0 = X[:, 0]
            returns = np.diff(col0, prepend=col0[0])
            # Rolling volatility (window=20)
            vol = pd.Series(returns).rolling(20, min_periods=1).std().values
            # Combine as observations
            obs = np.column_stack([returns, vol])
        else:
            # Volatility regime: use absolute returns
            col0 = X[:, 0]
            returns = np.diff(col0, prepend=col0[0])
            abs_returns = np.abs(returns)
            vol = pd.Series(returns).rolling(20, min_periods=1).std().values
            obs = np.column_stack([abs_returns, vol])

        # Handle NaN/Inf
        obs = np.nan_to_num(obs, nan=0.0, posinf=0.0, neginf=0.0)

        return obs

    def _rust_transform(self, X: np.ndarray) -> np.ndarray:
        """Transform using Rust backend (fit + transform combined).

        The Rust implementation does fit + transform in a single call for efficiency.
        Returns features array with shape (n_samples, n_states + 5).
        """
        obs = self._prepare_observations(X)
        # Ensure arrays are C-contiguous for Rust backend
        returns = np.ascontiguousarray(obs[:, 0], dtype=np.float64)
        volatility = np.ascontiguousarray(obs[:, 1], dtype=np.float64)

        # Call Rust HMM transform
        features = riskyield_rust.py_hmm_transform(
            returns,
            volatility,
            self.n_states,
            self.n_iter,
            1e-2,  # tolerance
            1e-3,  # min_covar
            self._rust_seed,
        )

        return np.asarray(features)

    def _sanitize_fitted_model(self, obs: np.ndarray) -> bool:
        """Repair/validate fitted HMM parameters.

        hmmlearn can emit warnings like:
        - RuntimeWarning: invalid value encountered in divide (means_ update)
        - Some rows of transmat_ have zero sum...

        Those situations can yield NaNs in model parameters and then NaNs in
        downstream helper features. We enforce a hard invariant:
        **no NaN/inf leaves this helper**.
        """
        if self.model is None:
            return False

        n_states = int(self.n_states)

        # 1) Start probabilities
        startprob = getattr(self.model, "startprob_", None)
        if (
            startprob is None
            or (not np.isfinite(startprob).all())
            or float(np.sum(startprob)) <= 0.0
        ):
            startprob = np.ones(n_states, dtype=float) / n_states
        else:
            s = float(np.sum(startprob))
            startprob = startprob / s
        self.model.startprob_ = startprob

        # 2) Transition matrix
        transmat = getattr(self.model, "transmat_", None)
        if transmat is None or transmat.shape != (n_states, n_states):
            transmat = np.ones((n_states, n_states), dtype=float) / n_states
        else:
            transmat = np.asarray(transmat, dtype=float)
            # Replace non-finite rows or zero-sum rows with uniform.
            row_sums = np.sum(transmat, axis=1)
            for i in range(n_states):
                if (not np.isfinite(transmat[i]).all()) or float(row_sums[i]) <= 0.0:
                    transmat[i] = 1.0 / n_states
            # Renormalize
            row_sums = np.sum(transmat, axis=1, keepdims=True)
            row_sums[row_sums <= 0.0] = 1.0
            transmat = transmat / row_sums
        self.model.transmat_ = transmat

        # 3) Means / covars: if any component never got responsibility, hmmlearn
        # may produce NaNs; replace invalid components with global stats.
        obs_mean = np.mean(obs, axis=0)
        obs_var = np.var(obs, axis=0) + 1e-6

        means = getattr(self.model, "means_", None)
        if means is None or means.shape != (n_states, obs.shape[1]):
            means = np.tile(obs_mean, (n_states, 1))
        else:
            means = np.asarray(means, dtype=float)
            for i in range(n_states):
                if not np.isfinite(means[i]).all():
                    means[i] = obs_mean
        self.model.means_ = means

        covars = getattr(self.model, "covars_", None)
        if self.covariance_type == "diag":
            if covars is None or covars.shape != (n_states, obs.shape[1]):
                covars = np.tile(obs_var, (n_states, 1))
            else:
                covars = np.asarray(covars, dtype=float)
                for i in range(n_states):
                    if (not np.isfinite(covars[i]).all()) or np.any(covars[i] <= 0.0):
                        covars[i] = obs_var
        else:
            # Conservative fallback for non-diag covars
            if covars is not None and not np.isfinite(np.asarray(covars)).all():
                covars = None
        if covars is not None:
            self.model.covars_ = covars

        # Final invariants
        ok = (
            np.isfinite(self.model.startprob_).all()
            and np.isfinite(self.model.transmat_).all()
            and np.isfinite(self.model.means_).all()
            and (
                getattr(self.model, "covars_", None) is None
                or np.isfinite(self.model.covars_).all()
            )
        )
        return bool(ok)

    def _fit_impl(self, X: np.ndarray, y: np.ndarray | None = None) -> None:
        """Fit HMM to training data."""
        obs = self._prepare_observations(X)

        # Fit Gaussian HMM
        self.model = hmm.GaussianHMM(
            n_components=self.n_states,
            covariance_type=self.covariance_type,
            n_iter=self.n_iter,
            random_state=self.config.random_state,
        )

        try:
            with warnings.catch_warnings():
                # hmmlearn can warn on degenerate components; we repair after fit.
                warnings.filterwarnings(
                    "ignore",
                    message=r"Some rows of transmat_ have zero sum.*",
                    category=RuntimeWarning,
                )
                warnings.filterwarnings(
                    "ignore",
                    message=r"invalid value encountered in divide",
                    category=RuntimeWarning,
                )
                self.model.fit(obs)
            self._model_fitted = self._sanitize_fitted_model(obs)
        except Exception as e:
            # Fallback: create dummy model
            print(f"HMM fitting failed: {e}, using fallback")
            self._model_fitted = False

    def _partial_fit_impl(
        self,
        X: np.ndarray,
        y: np.ndarray | None,
        n_samples_seen: int,
    ) -> None:
        """Incrementally update HMM with new data.

        Uses init_params='' to keep existing model parameters and
        only run a few more EM iterations on the new data.

        Args:
            X: Full feature matrix
            y: Optional target (not used for HMM)
            n_samples_seen: Number of samples from previous fit
        """
        if not self._model_fitted or self.model is None:
            # No existing model, do full fit
            self._fit_impl(X, y)
            return

        obs = self._prepare_observations(X)

        # Continue training with existing parameters
        # Set init_params='' to not reinitialize
        self.model.init_params = ""
        self.model.n_iter = self._incremental_n_iter

        try:
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message=r"Some rows of transmat_ have zero sum.*",
                    category=RuntimeWarning,
                )
                warnings.filterwarnings(
                    "ignore",
                    message=r"invalid value encountered in divide",
                    category=RuntimeWarning,
                )
                self.model.fit(obs)
            self._model_fitted = self._sanitize_fitted_model(obs)
        except Exception as e:
            # If incremental fails, try full refit
            if self.config.verbose:
                print(f"HMM incremental fit failed: {e}, doing full refit")
            self.model.init_params = "stmc"
            self.model.n_iter = 100
            try:
                with warnings.catch_warnings():
                    warnings.filterwarnings(
                        "ignore",
                        message=r"Some rows of transmat_ have zero sum.*",
                        category=RuntimeWarning,
                    )
                    warnings.filterwarnings(
                        "ignore",
                        message=r"invalid value encountered in divide",
                        category=RuntimeWarning,
                    )
                    self.model.fit(obs)
                self._model_fitted = self._sanitize_fitted_model(obs)
            except Exception:
                pass  # Keep existing model

    def _transform_impl(self, X: np.ndarray) -> np.ndarray:
        """Transform data to regime features.

        Uses Rust backend if available for ~10-20x speedup.
        """
        # Use Rust backend if available (does fit+transform in one call)
        if self._use_rust:
            return self._rust_transform(X)

        # Python/hmmlearn path
        n_samples = X.shape[0]
        obs = self._prepare_observations(X)

        # Get state probabilities and most likely sequence
        if self._model_fitted and self.model is not None:
            try:
                probs = self.model.predict_proba(obs)
                states = self.model.predict(obs)
            except Exception:
                # Fallback to uniform
                probs = np.ones((n_samples, self.n_states)) / self.n_states
                states = np.zeros(n_samples, dtype=int)
        else:
            probs = np.ones((n_samples, self.n_states)) / self.n_states
            states = np.zeros(n_samples, dtype=int)

        # Guard against any numerical weirdness leaking out.
        probs = np.asarray(probs, dtype=float)
        if probs.shape != (n_samples, self.n_states) or (not np.isfinite(probs).all()):
            probs = np.ones((n_samples, self.n_states), dtype=float) / self.n_states
        else:
            row_sums = probs.sum(axis=1, keepdims=True)
            bad = (~np.isfinite(row_sums)).ravel() | (row_sums.ravel() <= 0.0)
            if np.any(bad):
                probs[bad] = 1.0 / self.n_states
                row_sums = probs.sum(axis=1, keepdims=True)
            probs = probs / row_sums

        states = np.asarray(states)
        if states.shape != (n_samples,) or (
            not np.isfinite(states.astype(float)).all()
        ):
            states = np.zeros(n_samples, dtype=int)

        # Build features array
        # Features: n_states probs + state + entropy + confidence + duration + change
        # Total: n_states + 5 features
        n_features = self.n_states + 5
        features = np.zeros((n_samples, n_features))

        # 1. State probabilities (n_states features)
        features[:, : self.n_states] = probs

        # 2. Current state
        features[:, self.n_states] = states.astype(float)

        # 3. State entropy (uncertainty measure)
        entropy = -np.sum(probs * np.log(probs + 1e-10), axis=1)
        features[:, self.n_states + 1] = entropy

        # 4. Max probability (confidence)
        features[:, self.n_states + 2] = np.max(probs, axis=1)

        # 5. State duration (how long in current state)
        duration = self._compute_state_duration(states)
        features[:, self.n_states + 3] = duration.astype(float)

        # 6. State change indicator
        state_change = np.zeros(n_samples)
        state_change[1:] = (states[1:] != states[:-1]).astype(float)
        features[:, self.n_states + 4] = state_change

        return features

    def _compute_state_duration(self, states: np.ndarray) -> np.ndarray:
        """Compute how long we've been in current state."""
        duration = np.zeros(len(states))
        duration[0] = 1

        for i in range(1, len(states)):
            if states[i] == states[i - 1]:
                duration[i] = duration[i - 1] + 1
            else:
                duration[i] = 1

        return duration

    def _get_feature_names(self) -> list[str]:
        """Get names of features this helper generates."""
        prefix = f"H_{self.config.target}_{self.config.horizon}_{self.helper_name}_"

        names = []
        # Probability features for each state
        for label in self.state_labels:
            names.append(f"{prefix}prob_{label}")

        # Additional features
        names.extend(
            [
                f"{prefix}state",
                f"{prefix}entropy",
                f"{prefix}confidence",
                f"{prefix}duration",
                f"{prefix}change",
            ]
        )

        return names

    def optimize(
        self, X_cal: np.ndarray | pd.DataFrame, y_cal: np.ndarray | None = None
    ) -> dict:
        """Optimize HMM parameters on calibration data."""
        # For now, just validate on calibration data
        return self.validate(X_cal, y_cal)

    def validate(
        self, X_val: np.ndarray | pd.DataFrame, y_val: np.ndarray | None = None
    ) -> dict:
        """Validate HMM on validation data."""
        if isinstance(X_val, pd.DataFrame):
            X_val = X_val.values

        obs = self._prepare_observations(X_val)

        if self._model_fitted and self.model is not None:
            try:
                probs = self.model.predict_proba(obs)
                states = self.model.predict(obs)
                log_likelihood = self.model.score(obs)

                # State distribution
                state_dist = {}
                for i, label in enumerate(self.state_labels):
                    state_dist[label] = float(np.mean(states == i))

                # Mean entropy
                entropy = -np.sum(probs * np.log(probs + 1e-10), axis=1)

                return {
                    "log_likelihood": float(log_likelihood),
                    "mean_entropy": float(np.mean(entropy)),
                    "state_distribution": state_dist,
                    "n_transitions": int(np.sum(states[1:] != states[:-1])),
                }
            except Exception as e:
                return {"error": str(e)}
        else:
            return {"error": "Model not fitted"}

    def get_transition_matrix(self) -> np.ndarray | None:
        """Get the transition matrix from the fitted HMM."""
        if self._model_fitted and self.model is not None:
            return self.model.transmat_
        return None


class MarketRegimeHMM(HMMHelper):
    """4-state HMM for market regime detection.

    States:
    - bullish: strong upward momentum
    - bearish: strong downward momentum
    - neutral: sideways/low volatility
    - volatile: high volatility, no clear direction
    """

    def __init__(self, config: HelperConfig):
        super().__init__(config, n_states=4, regime_type="market")


class VolatilityRegimeHMM(HMMHelper):
    """5-state HMM for volatility regime detection.

    States:
    - very_low: extremely calm market
    - low: below average volatility
    - medium: normal volatility
    - high: above average volatility
    - very_high: extreme volatility (crisis)
    """

    def __init__(self, config: HelperConfig):
        super().__init__(config, n_states=5, regime_type="volatility")


# Factory functions
def create_market_regime_hmm(
    target: str, horizon: int, random_state: int = 42
) -> MarketRegimeHMM:
    """Create a 4-state market regime HMM helper."""
    config = HelperConfig(target=target, horizon=horizon, random_state=random_state)
    return MarketRegimeHMM(config)


def create_volatility_regime_hmm(
    target: str, horizon: int, random_state: int = 42
) -> VolatilityRegimeHMM:
    """Create a 5-state volatility regime HMM helper."""
    config = HelperConfig(target=target, horizon=horizon, random_state=random_state)
    return VolatilityRegimeHMM(config)


if __name__ == "__main__":
    # Quick test
    from scripts.target_models.registry import load_target_data

    X, y, spec = load_target_data("volatility", 6, verbose=False)
    print(f"Data shape: {X.shape}")

    # Test HMM-4
    hmm4 = create_market_regime_hmm("volatility", 6)
    hmm4.fit(X.iloc[:800])
    out4 = hmm4.transform(X.iloc[800:1300])
    print(f"\nHMM-4 output: {out4}")
    print(f"Features: {out4.feature_names}")

    # Test HMM-5
    hmm5 = create_volatility_regime_hmm("volatility", 6)
    hmm5.fit(X.iloc[:800])
    out5 = hmm5.transform(X.iloc[800:1300])
    print(f"\nHMM-5 output: {out5}")
    print(f"Features: {out5.feature_names}")
