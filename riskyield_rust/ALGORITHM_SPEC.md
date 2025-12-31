# Rolling Algorithm Specifications for Rust Implementation

## Overview

Each helper needs to produce time-varying parameters by re-estimating on a rolling window.
The key insight: market regimes CHANGE, so parameters should be ADAPTIVE.

**Performance Target:** 100-500x speedup over Python
**Validation:** Output must match Python within 0.01%

---

## 1. OU (Ornstein-Uhlenbeck / AR(1)) Helper

### Purpose
Estimate mean-reversion strength using rolling AR(1) model.

### Algorithm (ROLLING - this is what we need)
```
for t in range(window, n_samples):
    # Get rolling window [t-window:t]
    x = series[t-window:t]
    
    # Estimate AR(1) coefficient via OLS
    # x_t = φ * x_{t-1} + ε_t
    x_lag = x[:-1]
    x_curr = x[1:]
    
    phi[t] = cov(x_curr, x_lag) / var(x_lag)
    
    # Derived quantities
    kappa[t] = -ln(phi[t])  # Mean reversion speed
    halflife[t] = ln(2) / kappa[t]  # Half-life in bars
    
    # Z-score (from shorter window)
    zscore_data = series[t-zscore_window:t]
    zscore[t] = (series[t] - mean(zscore_data)) / std(zscore_data)
```

### Rust Implementation Notes
- Pure arithmetic, easily vectorized
- Can use rayon to parallelize across samples (each t is independent)
- Hot loop: ~63 multiplications per sample for AR(1) estimation

### Features (8 total)
- phi, kappa, halflife (rolling estimated)
- zscore, zscore_abs (rolling window)
- is_stationary, halflife_regime, reverting (derived)

---

## 2. EVT POT (Extreme Value Theory - Peaks Over Threshold)

### Purpose
Estimate tail risk via Generalized Pareto Distribution (GPD).

### Algorithm (ROLLING)
```
for t in range(window, n_samples):
    # Get rolling window
    data = abs(returns[t-window:t])
    
    # Threshold (95th percentile of window)
    u = percentile(data, 95)
    
    # Get exceedances
    exceedances = data[data > u] - u
    
    if len(exceedances) >= min_exceedances:
        # Fit GPD via MLE
        # P(Y ≤ y) = 1 - (1 + ξy/β)^(-1/ξ)
        xi[t], beta[t] = gpd_fit_mle(exceedances)
    else:
        xi[t], beta[t] = default_xi, default_beta
    
    # Derived features
    exceedance_rate[t] = count(data > u) / len(data)
    var95[t] = compute_var(xi[t], beta[t], exceedance_rate[t], 0.95)
    es95[t] = compute_es(xi[t], beta[t], exceedance_rate[t], 0.95)
```

### GPD MLE Fitting (Rust)
The GPD log-likelihood for exceedances y_i:
```
L(ξ, β) = -n*ln(β) - (1 + 1/ξ) * Σ ln(1 + ξ*y_i/β)
```

For ξ ≈ 0 (exponential tail):
```
L(β) = -n*ln(β) - Σ y_i/β
```

Use numerical optimization (e.g., Brent's method for β, Newton for ξ).

### Rust Implementation Notes
- GPD MLE is the bottleneck (scipy does iterative optimization)
- Can implement closed-form estimators (PWM = Probability Weighted Moments)
- PWM estimator for GPD:
  ```
  a0 = mean(exceedances)
  a1 = Σ (i/(n-1)) * y_i[sorted] / n
  ξ = 2 - a0 / (a0 - 2*a1)
  β = 2 * a0 * a1 / (a0 - 2*a1)
  ```
- PWM is O(n log n) due to sorting, vs O(n * iterations) for MLE

### Features (10 total)
- xi, beta (GPD parameters)
- exceedance_rate, var95, var99, es95
- tail_prob_2std, tail_prob_3std
- tail_flag, regime

---

## 3. BOCPD (Bayesian Online Changepoint Detection)

### Purpose
Detect regime shifts in real-time using Bayesian inference.

### Algorithm (ONLINE - already correct design)
```
# Initialize
R[0] = 1.0  # P(run_length = 0) = 1
sum_x, sum_x2, counts = 0, 0, 0

for t in range(n_samples):
    x = series[t]
    
    # Predictive probability P(x_t | r_t = r)
    for r in range(max_run_length):
        pred_prob[r] = student_t_pdf(x, prior_params + sufficient_stats[r])
    
    # Growth: P(r_t = r+1 | r_{t-1} = r) = 1 - hazard
    growth_prob = R[:-1] * pred_prob[:-1] * (1 - hazard)
    
    # Changepoint: reset to r=0
    cp_mass = sum(R * pred_prob * hazard)
    
    # New distribution
    R_new[0] = cp_mass
    R_new[1:] = growth_prob
    R = R_new / sum(R_new)  # Normalize
    
    # Update sufficient statistics
    # (shift and add new observation)
    
    # Output features
    expected_run_length[t] = dot(range(max_rl), R)
    cp_prob[t] = R[0]
```

### Rust Implementation Notes
- Already online (O(n * max_run_length))
- Can parallelize sufficient stats updates across run lengths
- Student-t PDF can be computed efficiently
- max_run_length = 100 is reasonable (500 was excessive)

### Features (7 total)
- run_length, cp_prob, cp_recent
- run_length_norm, regime_age
- cp_intensity, stability

---

## 4. EGARCH (Exponential GARCH) Asymmetric Volatility

### Purpose
Capture leverage effect (negative returns increase volatility more).

### Algorithm (ROLLING - for parameter estimation)
```
for t in range(window, n_samples):
    returns_window = returns[t-window:t]
    
    # Estimate EGARCH params via grid search + log-likelihood
    best_ll = -inf
    for gamma in [-0.2, -0.1, -0.05, 0, 0.05]:
        for beta in [0.7, 0.8, 0.85, 0.9, 0.95]:
            for alpha in [0.05, 0.1, 0.15, 0.2]:
                omega = (1 - beta) * ln(var(returns_window))
                ll = egarch_log_likelihood(returns_window, omega, alpha, gamma, beta)
                if ll > best_ll:
                    best_ll = ll
                    best_params = (omega, alpha, gamma, beta)
    
    omega[t], alpha[t], gamma[t], beta[t] = best_params
    
    # Compute vol using fitted params
    vol[t] = compute_egarch_vol(returns_window, omega[t], alpha[t], gamma[t], beta[t])
```

### EGARCH Log-Likelihood
```
ln(σ²_t) = ω + α*(|ε_{t-1}| - E|ε|) + γ*ε_{t-1} + β*ln(σ²_{t-1})

where ε_t = r_t / σ_t (standardized residual)
      E|ε| ≈ 0.798 for standard normal

Log-likelihood = Σ [-0.5 * (ln(2π) + ln(σ²_t) + r²_t/σ²_t)]
```

### Rust Implementation Notes
- Grid search is embarrassingly parallel (rayon)
- 5 × 5 × 4 = 100 grid points per sample
- Each LL evaluation is O(window) = O(126)
- Total: O(n_samples × 100 × 126) = O(12.6M) ops for 1000 samples
- With SIMD and rayon: should be ~1ms per sample vs ~100ms in Python

### Features (8 total)
- vol, log_vol
- asymmetry (gamma), persistence (beta)
- news_impact, vol_zscore
- vol_regime, leverage_active

---

## Rust Crate Structure

```
riskyield_rust/
├── Cargo.toml
├── src/
│   ├── lib.rs          # PyO3 module definition
│   ├── ou.rs           # OU rolling AR(1)
│   ├── evt.rs          # EVT GPD fitting
│   ├── bocpd.rs        # Bayesian changepoint
│   ├── egarch.rs       # EGARCH estimation
│   └── utils.rs        # Common utilities (stats, etc.)
```

## Python Integration

Each helper will check for Rust availability:
```python
try:
    from riskyield_rust import ou_rolling_transform
    HAS_RUST = True
except ImportError:
    HAS_RUST = False

def _transform_impl(self, X):
    if HAS_RUST and self.config.use_rust:
        return ou_rolling_transform(X, self.config.rolling_window, ...)
    else:
        return self._transform_impl_python(X)
```

## Validation Strategy

1. Generate reference outputs from Python (slow but correct)
2. Run Rust implementation on same data
3. Compare: max(|rust - python|) < 0.0001
4. Benchmark: time(rust) / time(python) > 100x
