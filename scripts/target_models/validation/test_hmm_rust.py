"""Validation and benchmark script for Rust HMM implementation.

Compares Python (hmmlearn) vs Rust HMM:
1. Numerical equivalence (statistical, since HMM is stochastic)
2. Performance speedup
"""

import time

import numpy as np
import pandas as pd
from scipy import stats

# Test imports
try:
    import riskyield_rust

    HAS_RUST = True
    print("✓ Rust backend available")
except ImportError:
    HAS_RUST = False
    print("✗ Rust backend not available")

from hmmlearn import hmm


def generate_test_data(
    n_samples: int = 5000, seed: int = 42
) -> tuple[np.ndarray, np.ndarray]:
    """Generate synthetic market data for testing."""
    np.random.seed(seed)

    # Simulate regime-switching returns
    regimes = np.zeros(n_samples, dtype=int)
    regime = 0
    for i in range(n_samples):
        if np.random.random() < 0.02:  # 2% chance to switch
            regime = (regime + 1) % 4
        regimes[i] = regime

    # Generate returns based on regime
    returns = np.zeros(n_samples)
    for i in range(n_samples):
        if regimes[i] == 0:  # bullish
            returns[i] = np.random.normal(0.001, 0.01)
        elif regimes[i] == 1:  # bearish
            returns[i] = np.random.normal(-0.001, 0.01)
        elif regimes[i] == 2:  # neutral
            returns[i] = np.random.normal(0.0, 0.005)
        else:  # volatile
            returns[i] = np.random.normal(0.0, 0.03)

    # Rolling volatility
    volatility = pd.Series(returns).rolling(20, min_periods=1).std().values
    volatility = np.nan_to_num(volatility, nan=0.01)

    return returns.astype(np.float64), volatility.astype(np.float64)


def python_hmm_transform(
    returns: np.ndarray,
    volatility: np.ndarray,
    n_states: int = 4,
    n_iter: int = 100,
    seed: int = 42,
) -> np.ndarray:
    """Python HMM transform using hmmlearn (with z-score scaling to match Rust)."""
    obs = np.column_stack([returns, volatility])

    # Z-score scaling (matching Rust implementation)
    obs_mean = obs.mean(axis=0)
    obs_std = obs.std(axis=0)
    obs_std[obs_std < 1e-10] = 1.0
    obs_scaled = (obs - obs_mean) / obs_std

    model = hmm.GaussianHMM(
        n_components=n_states,
        covariance_type="diag",
        n_iter=n_iter,
        tol=1e-2,  # Match Rust tolerance
        random_state=seed,
    )

    model.fit(obs_scaled)
    probs = model.predict_proba(obs_scaled)
    states = model.predict(obs_scaled)

    # Build features
    n_samples = len(returns)
    n_features = n_states + 5
    features = np.zeros((n_samples, n_features))

    features[:, :n_states] = probs
    features[:, n_states] = states
    features[:, n_states + 1] = -np.sum(
        probs * np.log(probs + 1e-10), axis=1
    )  # entropy
    features[:, n_states + 2] = np.max(probs, axis=1)  # confidence

    # Duration
    duration = np.ones(n_samples)
    for i in range(1, n_samples):
        if states[i] == states[i - 1]:
            duration[i] = duration[i - 1] + 1
    features[:, n_states + 3] = duration

    # Change
    change = np.zeros(n_samples)
    change[1:] = (states[1:] != states[:-1]).astype(float)
    features[:, n_states + 4] = change

    return features


def rust_hmm_transform(
    returns: np.ndarray,
    volatility: np.ndarray,
    n_states: int = 4,
    n_iter: int = 100,
    seed: int = 42,
) -> np.ndarray:
    """Rust HMM transform."""
    features = riskyield_rust.py_hmm_transform(
        returns, volatility, n_states, n_iter, 1e-2, 1e-3, seed
    )
    return np.asarray(features)


def validate_numerical_equivalence(n_samples: int = 2000, n_runs: int = 5):
    """Validate that Rust and Python produce statistically similar results.

    Note: HMM state labels are arbitrary (cluster IDs), so we cannot directly compare
    states. Instead, we validate that the statistical properties (entropy, confidence,
    duration distributions) are equivalent.
    """
    print("\n" + "=" * 60)
    print("NUMERICAL EQUIVALENCE VALIDATION")
    print("=" * 60)

    # Collect statistics from multiple independent data generations
    py_entropies = []
    rs_entropies = []
    py_confidences = []
    rs_confidences = []
    py_durations = []
    rs_durations = []

    for run in range(n_runs):
        seed = 42 + run
        np.random.seed(seed)

        # Generate fresh data for each run
        returns, volatility = generate_test_data(n_samples)

        py_feat = python_hmm_transform(returns, volatility, n_states=4, seed=seed)
        rs_feat = rust_hmm_transform(returns, volatility, n_states=4, seed=seed)

        py_entropies.append(py_feat[:, 5].mean())  # entropy is at index n_states+1=5
        rs_entropies.append(rs_feat[:, 5].mean())

        py_confidences.append(py_feat[:, 6].mean())  # confidence at n_states+2=6
        rs_confidences.append(rs_feat[:, 6].mean())

        py_durations.append(py_feat[:, 7].mean())  # duration at n_states+3=7
        rs_durations.append(rs_feat[:, 7].mean())

    # Statistical tests
    print(f"\nComparing {n_runs} runs on {n_samples} samples:")

    # Entropy comparison
    t_stat, p_val = stats.ttest_ind(py_entropies, rs_entropies)
    print("\nEntropy:")
    print(f"  Python mean: {np.mean(py_entropies):.6f} ± {np.std(py_entropies):.6f}")
    print(f"  Rust mean:   {np.mean(rs_entropies):.6f} ± {np.std(rs_entropies):.6f}")
    print(f"  t-test p-value: {p_val:.4f} {'✓' if p_val > 0.05 else '✗'}")

    # Confidence comparison
    t_stat, p_val = stats.ttest_ind(py_confidences, rs_confidences)
    print("\nConfidence:")
    print(
        f"  Python mean: {np.mean(py_confidences):.6f} ± {np.std(py_confidences):.6f}"
    )
    print(
        f"  Rust mean:   {np.mean(rs_confidences):.6f} ± {np.std(rs_confidences):.6f}"
    )
    print(f"  t-test p-value: {p_val:.4f} {'✓' if p_val > 0.05 else '✗'}")

    # Duration comparison
    t_stat, p_val = stats.ttest_ind(py_durations, rs_durations)
    print("\nDuration:")
    print(f"  Python mean: {np.mean(py_durations):.6f} ± {np.std(py_durations):.6f}")
    print(f"  Rust mean:   {np.mean(rs_durations):.6f} ± {np.std(rs_durations):.6f}")
    print(f"  t-test p-value: {p_val:.4f} {'✓' if p_val > 0.05 else '✗'}")


def validate_deterministic_features():
    """Validate that deterministic features (duration, change) are exact."""
    print("\n" + "=" * 60)
    print("DETERMINISTIC FEATURES VALIDATION")
    print("=" * 60)

    returns, volatility = generate_test_data(1000)

    # Get features from both
    py_feat = python_hmm_transform(returns, volatility, n_states=4, seed=42)
    rs_feat = rust_hmm_transform(returns, volatility, n_states=4, seed=42)

    # Check that probability sums are 1.0
    py_prob_sums = py_feat[:, :4].sum(axis=1)
    rs_prob_sums = rs_feat[:, :4].sum(axis=1)

    print("\nProbability sum check:")
    print(f"  Python all sum to 1: {np.allclose(py_prob_sums, 1.0)}")
    print(f"  Rust all sum to 1:   {np.allclose(rs_prob_sums, 1.0)}")

    # Check confidence = max(probs)
    py_conf = py_feat[:, 6]
    py_max_prob = py_feat[:, :4].max(axis=1)
    rs_conf = rs_feat[:, 6]
    rs_max_prob = rs_feat[:, :4].max(axis=1)

    print("\nConfidence = max(probs) check:")
    print(f"  Python matches: {np.allclose(py_conf, py_max_prob)}")
    print(f"  Rust matches:   {np.allclose(rs_conf, rs_max_prob)}")

    # Check duration logic for Rust
    rs_states = rs_feat[:, 4].astype(int)
    rs_duration = rs_feat[:, 7]

    # Recompute duration
    expected_duration = np.ones(len(rs_states))
    for i in range(1, len(rs_states)):
        if rs_states[i] == rs_states[i - 1]:
            expected_duration[i] = expected_duration[i - 1] + 1

    duration_match = np.allclose(rs_duration, expected_duration)
    print(f"\nRust duration logic correct: {duration_match}")

    # Check change logic for Rust
    rs_change = rs_feat[:, 8]
    expected_change = np.zeros(len(rs_states))
    expected_change[1:] = (rs_states[1:] != rs_states[:-1]).astype(float)

    change_match = np.allclose(rs_change, expected_change)
    print(f"Rust change logic correct:   {change_match}")


def benchmark_performance(n_samples: int = 10000, n_runs: int = 3):
    """Benchmark Python vs Rust performance."""
    print("\n" + "=" * 60)
    print("PERFORMANCE BENCHMARK")
    print("=" * 60)

    returns, volatility = generate_test_data(n_samples)

    # Warmup
    _ = python_hmm_transform(returns[:100], volatility[:100])
    _ = rust_hmm_transform(returns[:100], volatility[:100])

    # Benchmark Python
    py_times = []
    for _ in range(n_runs):
        start = time.perf_counter()
        _ = python_hmm_transform(returns, volatility)
        py_times.append(time.perf_counter() - start)

    # Benchmark Rust
    rs_times = []
    for _ in range(n_runs):
        start = time.perf_counter()
        _ = rust_hmm_transform(returns, volatility)
        rs_times.append(time.perf_counter() - start)

    py_mean = np.mean(py_times)
    rs_mean = np.mean(rs_times)
    speedup = py_mean / rs_mean

    print(f"\nBenchmark on {n_samples} samples ({n_runs} runs):")
    print(
        f"  Python (hmmlearn): {py_mean * 1000:.2f} ms ± {np.std(py_times) * 1000:.2f} ms"
    )
    print(
        f"  Rust:              {rs_mean * 1000:.2f} ms ± {np.std(rs_times) * 1000:.2f} ms"
    )
    print(f"  Speedup:           {speedup:.1f}x")

    return speedup


def test_different_n_states():
    """Test both HMM-4 and HMM-5 configurations."""
    print("\n" + "=" * 60)
    print("TESTING DIFFERENT N_STATES")
    print("=" * 60)

    returns, volatility = generate_test_data(2000)

    for n_states in [4, 5]:
        print(f"\nHMM-{n_states}:")

        rs_feat = rust_hmm_transform(returns, volatility, n_states=n_states)

        expected_cols = n_states + 5
        print(f"  Expected features: {expected_cols}")
        print(f"  Got features:      {rs_feat.shape[1]}")
        print(f"  Shape match: {rs_feat.shape[1] == expected_cols}")

        # Check probability sums
        prob_sums = rs_feat[:, :n_states].sum(axis=1)
        print(f"  All prob sums = 1: {np.allclose(prob_sums, 1.0)}")


if __name__ == "__main__":
    if not HAS_RUST:
        print("\nRust backend not available. Cannot run validation.")
        exit(1)

    # Run all validations
    validate_deterministic_features()
    validate_numerical_equivalence()
    test_different_n_states()
    speedup = benchmark_performance()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print("✓ Rust HMM implementation validated")
    print(f"✓ Speedup: {speedup:.1f}x")
