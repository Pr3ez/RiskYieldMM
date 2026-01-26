# L1 Helper Features

L1 helpers generate derived features at each walk-forward iteration.
These enrich the base features with model-based signals.

Source: [scripts/target_models/helpers/](../../scripts/target_models/helpers/)

---

## Summary Table

| Helper | Features | Purpose |
|--------|----------|---------|
| `if` | ~12 | Isolation Forest anomaly detection (3 levels) |
| `cusum` | ~8 | CUSUM changepoint detection |
| `garch` | ~8 | GARCH(1,1) volatility modeling |
| `hmm4` | ~10 | 4-state market regime (HMM) |
| `hmm5` | ~10 | 5-state volatility regime (HMM) |
| `kalman` | ~6 | Kalman filter state estimation |
| `evt` | ~6 | Extreme Value Theory (POT) |
| `ou` | ~6 | Ornstein-Uhlenbeck mean reversion |
| `bocpd` | ~6 | Bayesian Online Changepoint Detection |
| `egarch` | ~8 | Exponential GARCH asymmetric volatility |

**Total:** ~91 features (EXPECTED_FEATURES in config)

---

## Helper Details

### 1. Isolation Forest (`if`)

**Purpose:** Multi-level anomaly detection

**Levels:**
- Extreme (1%): High precision, severe anomalies
- Moderate (5%): Balanced detection
- Mild (10%): High recall

**Features per level:**
- `_score`: Raw anomaly score
- `_is`: Binary flag
- `_severity`: Normalized severity

**Aggregates:**
- `_mean_score`: Mean across levels
- `_max_severity`: Max severity
- `_n_anomalies`: Count of levels triggered

**Reference:** [helpers/isolation_forest.py](../../scripts/target_models/helpers/isolation_forest.py)

---

### 2. GARCH (`garch`)

**Purpose:** Conditional volatility estimation via GARCH(1,1)

**Features:**
- `_cond_vol`: Conditional volatility estimate
- `_vol_forecast`: Multi-step forecast
- `_vol_zscore`: Vol relative to 63-day mean
- `_vol_shock`: Standardized residuals (ε/σ)
- `_persistence`: α + β (volatility persistence)
- `_vol_regime`: 0=LOW, 1=MED, 2=HIGH
- `_vol_change`: Δ conditional vol
- `_vol_ratio`: Current vol / long-run vol

**Rust backend:** ~360x speedup when available

**Reference:** [helpers/garch.py](../../scripts/target_models/helpers/garch.py)

---

### 3. HMM-4 (`hmm4`)

**Purpose:** 4-state market regime detection

**States:**
| State | Label | Meaning |
|-------|-------|---------|
| 0 | Bullish | Uptrend regime |
| 1 | Bearish | Downtrend regime |
| 2 | Neutral | Low activity |
| 3 | Volatile | High uncertainty |

**Features:**
- `_regime`: Most likely state
- `_prob_*`: Probability per state (4 features)
- `_confidence`: Max probability
- `_stability`: Duration in current regime
- `_entropy`: Regime uncertainty

**Rust backend:** ~10-20x speedup when available

**Reference:** [helpers/hmm.py](../../scripts/target_models/helpers/hmm.py)

---

### 4. HMM-5 (`hmm5`)

**Purpose:** 5-state volatility regime detection

**States:**
| State | Label |
|-------|-------|
| 0 | Very Low |
| 1 | Low |
| 2 | Medium |
| 3 | High |
| 4 | Very High |

**Features:** Same structure as HMM-4 (regime, probs, confidence, stability, entropy)

**Reference:** [helpers/hmm.py](../../scripts/target_models/helpers/hmm.py)

---

### 5. CUSUM (`cusum`)

**Purpose:** Changepoint detection via cumulative sum

**Features:**
- `_stat`: CUSUM statistic
- `_change`: Change since last point
- `_regime`: Current regime
- `_time_since`: Bars since last changepoint
- `_magnitude`: Size of last change

**Reference:** [helpers/cusum.py](../../scripts/target_models/helpers/cusum.py)

---

### 6. Kalman Filter (`kalman`)

**Purpose:** State estimation and filtering

**Features:**
- `_state`: Estimated state
- `_prediction`: One-step prediction
- `_error`: Prediction error
- `_gain`: Kalman gain
- `_variance`: State variance

**Reference:** [helpers/kalman.py](../../scripts/target_models/helpers/kalman.py)

---

### 7. EVT-POT (`evt`)

**Purpose:** Extreme Value Theory (Peaks Over Threshold)

**Features:**
- `_tail_prob`: Probability of extreme event
- `_var`: Value at Risk
- `_es`: Expected Shortfall
- `_shape`: Tail shape parameter (ξ)
- `_scale`: Tail scale parameter (σ)

**Reference:** [helpers/evt_pot.py](../../scripts/target_models/helpers/evt_pot.py)

---

### 8. Ornstein-Uhlenbeck (`ou`)

**Purpose:** Mean-reversion modeling

**Features:**
- `_level`: Long-run mean
- `_speed`: Mean-reversion speed (κ)
- `_deviation`: Distance from mean
- `_halflife`: Mean-reversion half-life
- `_zscore`: Standardized deviation

**Reference:** [helpers/ou.py](../../scripts/target_models/helpers/ou.py)

---

### 9. BOCPD (`bocpd`)

**Purpose:** Bayesian Online Changepoint Detection

**Features:**
- `_run_length`: Expected run length
- `_change_prob`: Probability of changepoint
- `_regime`: Current regime estimate
- `_posterior`: Posterior distribution metrics

**Reference:** [helpers/bocpd.py](../../scripts/target_models/helpers/bocpd.py)

---

### 10. EGARCH (`egarch`)

**Purpose:** Exponential GARCH for asymmetric volatility

**Key advantage:** Captures leverage effect (negative returns → higher vol)

**Features:**
- `_log_vol`: Log conditional volatility
- `_vol`: Conditional volatility
- `_asymmetry`: Asymmetry parameter (γ)
- `_persistence`: Persistence (β)
- `_leverage`: Leverage effect estimate

**Reference:** [helpers/egarch.py](../../scripts/target_models/helpers/egarch.py)

---

## Incremental Training

All helpers support incremental training for efficiency:
- `supports_incremental` property = True
- `partial_fit()` method updates with new data
- Used by expanding L1 window

**Reference:** [helpers/base.py#L10-12](../../scripts/target_models/helpers/base.py)

---

## Rust Acceleration

Some helpers have Rust backends for significant speedup:
- GARCH: ~360x faster
- HMM: ~10-20x faster

**Check availability:** `import riskyield_rust; print(riskyield_rust.__version__)`

---

## Configuration

In [scripts/workflow/config.py](../../scripts/workflow/config.py):

```python
L1_HELPERS = [
    "if", "cusum", "garch", "hmm4", "hmm5",
    "kalman", "evt", "ou", "bocpd", "egarch"
]
EXPECTED_FEATURES = 91
```
