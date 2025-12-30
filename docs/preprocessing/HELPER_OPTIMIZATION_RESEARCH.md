# Helper Model Optimization Research

**Date**: 2025-12-23
**Status**: Research Complete ✅

---

## Executive Summary

This document summarizes academic research on optimizing the 6 helper models for 20 target-horizon combinations. The key insight is that **different helpers have different optimal configurations depending on the prediction task (regression vs classification) and horizon length**.

---

## 1. HMM (Hidden Markov Models) Optimization

### 1.1 Optimal Number of States

**Academic Consensus** (arXiv:2405.12343, SSRN:4796238):
- **AIC/BIC** are standard model selection criteria
- **Marginal likelihood** provides consistent state selection
- For financial markets, typical range: **2-6 states**

**Key Paper**: "Determine the Number of States in Hidden Markov Models via Marginal Likelihood" (arXiv)
- Proposes consistent method using marginal likelihood
- BIC tends to overestimate, marginal likelihood is more stable

**SSRN:5580230**: "Modeling Financial Volatility with HMM"
- Compares HMM vs SV-HMM for regime classification
- **Volatility regimes**: 3-5 states optimal
- **Market regimes**: 2-4 states optimal

### 1.2 Recommended Configurations to Test

| Task Type | Target | States to Test | Rationale |
|-----------|--------|----------------|-----------|
| Regression (vol) | volatility | 3, 4, 5 | Volatility has distinct regimes (low/med/high/crisis) |
| Regression (ret) | returns | 3, 4 | Returns less regime-dependent |
| Classification | direction | 2, 3, 4 | Up/down + neutral/volatile |
| Classification | vol_regime | 4, 5, 6 | Target IS the regime |
| Classification | trend_regime | 3, 4 | Trend/no-trend + transitions |

### 1.3 Other HMM Hyperparameters

| Parameter | Options | Academic Guidance |
|-----------|---------|-------------------|
| `n_iter` | 50, 100, 200 | 100 usually sufficient, more for complex data |
| `covariance_type` | 'diag', 'full' | 'diag' more stable, 'full' captures correlations |
| `init_params` | 'stmc', 'random' | 'stmc' (spectral) more consistent |

---

## 2. GARCH Model Optimization

### 2.1 Order Selection (p, q)

**Academic Consensus** (QuantStackExchange, ResearchGate):
- **AIC/BIC** for model comparison
- **GARCH(1,1)** is sufficient 90%+ of cases (Bollerslev)
- Higher orders rarely improve OOS performance

**arXiv:2410.00288**: "GARCH-Informed Neural Networks"
- GARCH(1,1) remains competitive benchmark
- Extensions (EGARCH, GJR-GARCH) help for asymmetric effects

### 2.2 Recommended Configurations

| Config | (p, q) | Mean Model | Best For |
|--------|--------|------------|----------|
| Standard | (1, 1) | Zero | General use |
| Extended | (1, 2) | Zero | More persistence |
| Asymmetric | (1, 1) GJR | Zero | When leverage effects matter |
| Mean-reverting | (1, 1) | Constant | Returns prediction |

### 2.3 Forecast Horizon Matching

**Key Insight**: GARCH forecast horizon should match target horizon:
- `volatility_1bar` → forecast_horizon=1
- `volatility_12bar` → forecast_horizon=12

---

## 3. Isolation Forest Optimization

### 3.1 Contamination Parameter

**ScienceDirect (2025)**: "Forecasting Stock Market Anomalies"
- **OPTUNA** for hyperparameter optimization
- Contamination should reflect expected anomaly rate in data

**Academic Guidance**:
- **True anomalies**: 1-5% contamination
- **Market events**: 5-10% contamination (more frequent)
- **Regime transitions**: 10-20% contamination

### 3.2 Recommended Configurations

| Task Type | contamination_extreme | contamination_moderate | contamination_mild |
|-----------|----------------------|------------------------|-------------------|
| Volatility | 0.01 | 0.03 | 0.07 |
| Returns | 0.01 | 0.05 | 0.10 |
| Direction | 0.02 | 0.05 | 0.10 |
| Regimes | 0.05 | 0.10 | 0.15 |

### 3.3 Other IF Parameters

| Parameter | Options | Guidance |
|-----------|---------|----------|
| `n_estimators` | 50, 100, 200 | 100 is standard, more for stability |
| `max_samples` | 'auto', 256, 512 | 256 often sufficient |
| `bootstrap` | True, False | True for more diversity |

---

## 4. Kalman Filter Optimization

### 4.1 Q/R Noise Covariance Ratio

**Medium Article**: "Sensitivity Analysis of Q-R Noise Covariances"
- **Q** = process noise (state evolution uncertainty)
- **R** = measurement noise (observation uncertainty)
- **Q/R ratio** determines filter responsiveness

**Academic Guidance**:
- **High Q/R** (> 1): Trust measurements more → responsive to changes
- **Low Q/R** (< 0.1): Trust model more → smoother estimates

### 4.2 Recommended Q/R Ratios by Task

| Task Type | Q/R Ratio | Behavior |
|-----------|-----------|----------|
| Volatility (short horizon) | 0.5 - 1.0 | Responsive to vol spikes |
| Volatility (long horizon) | 0.1 - 0.3 | Smoother trends |
| Returns | 0.3 - 0.5 | Balanced |
| Direction | 0.5 - 1.0 | Responsive to regime changes |
| Regimes | 0.1 - 0.2 | Stable regime identification |

### 4.3 State Space Dimensionality

Current: 3D state (price level, velocity, acceleration)

Options to test:
- **2D**: (level, velocity) — simpler, less noise
- **3D**: (level, velocity, acceleration) — current default
- **4D**: Add jerk for regime transitions (may overfit)

---

## 5. CUSUM Changepoint Detection

### 5.1 Threshold Selection

**arXiv:1509.01570**: "Real-time Financial Surveillance via CUSUM"
- Threshold determines detection delay vs false positive tradeoff
- **Higher threshold** → fewer false alarms, later detection
- **Lower threshold** → more false alarms, earlier detection

**ScienceDirect (Lazar 2023)**: "Change Point Detection in Risk Measures"
- CUSUM with Wilcoxon statistic for robustness
- Threshold calibration critical for financial data

### 5.2 Recommended Threshold Configurations

| Task Type | Threshold σ | Drift | Rationale |
|-----------|------------|-------|-----------|
| Volatility (short) | 3.0 | 0.5 | Responsive to vol spikes |
| Volatility (long) | 4.0 | 0.25 | Avoid false alarms |
| Returns | 3.5 | 0.5 | Balanced |
| Direction | 3.0 | 0.5 | Sensitive to regime shifts |
| Regimes | 4.0 | 0.25 | Stable regime boundaries |

### 5.3 Window Parameters

| Parameter | Options | Guidance |
|-----------|---------|----------|
| `reference_window` | 50, 100, 252 | Longer for stable reference |
| `detection_window` | 20, 50, 100 | Shorter for fast detection |

---

## 6. Selection Criterion: IC-Based Optimization

### 6.1 Information Coefficient (IC)

**Academic Standard** (Lopez de Prado, Gu-Kelly-Xiu):
- `IC = Spearman(helper_feature, target)`
- Mean |IC| across all helper features for a config
- **Higher IC → better config**

### 6.2 Optimization Procedure

```
For each target-horizon:
    For each helper:
        For each config in helper_configs:
            1. Fit helper on L1 train window
            2. Generate features for L1 cal window
            3. Compute mean |IC| with target
            4. Track best config
    
    Save best config per helper
    Combine into optimal helper ensemble
```

### 6.3 Cross-Validation for Robustness

- Use 3-fold temporal CV within L1 window
- Select config that wins 2/3 or has highest mean IC

---

## 7. Implementation Plan

### 7.1 Helper Config Search Space

```python
HELPER_CONFIGS = {
    "hmm4": [
        {"n_states": 3, "covariance_type": "diag"},
        {"n_states": 4, "covariance_type": "diag"},
        {"n_states": 5, "covariance_type": "diag"},
    ],
    "hmm5": [
        {"n_states": 4, "covariance_type": "diag"},
        {"n_states": 5, "covariance_type": "diag"},
        {"n_states": 6, "covariance_type": "diag"},
    ],
    "garch": [
        {"p": 1, "q": 1, "mean": "Zero"},
        {"p": 1, "q": 1, "mean": "Constant"},
        {"p": 1, "q": 2, "mean": "Zero"},
    ],
    "if": [
        {"contamination_extreme": 0.01, "contamination_moderate": 0.03, "contamination_mild": 0.07},
        {"contamination_extreme": 0.01, "contamination_moderate": 0.05, "contamination_mild": 0.10},
        {"contamination_extreme": 0.02, "contamination_moderate": 0.07, "contamination_mild": 0.15},
    ],
    "kalman": [
        {"q_r_ratio": 0.1},  # Trust model (smooth)
        {"q_r_ratio": 0.5},  # Balanced
        {"q_r_ratio": 1.0},  # Trust measurements (responsive)
    ],
    "cusum": [
        {"threshold": 3.0, "drift": 0.5},   # Sensitive
        {"threshold": 4.0, "drift": 0.25},  # Balanced
        {"threshold": 5.0, "drift": 0.1},   # Conservative
    ],
}
```

### 7.2 Task-Specific Default Overrides

Based on research, certain configs should be preferred for certain tasks:

| Task Type | Helper | Preferred Config |
|-----------|--------|------------------|
| `volatility` | hmm5 | 5 states |
| `volatility` | garch | (1,1) Zero |
| `volatility` | if | Low contamination |
| `volatility` | kalman | Low Q/R (smooth) |
| `direction` | hmm4 | 4 states |
| `direction` | kalman | High Q/R (responsive) |
| `vol_regime` | hmm5 | 5-6 states (match target) |
| `trend_regime` | hmm4 | 3-4 states |

---

## 8. Expected Outcomes

### 8.1 Metrics to Track

- **Base IC**: Helper features with default config
- **Optimized IC**: Helper features with best config
- **IC Improvement**: (Optimized - Base) / Base × 100%

### 8.2 Success Criteria

- Average IC improvement > 5% across 20 targets
- At least 15/20 targets show improvement
- No target shows > 10% degradation

---

## 9. References

1. arXiv:2405.12343 — "Determine the Number of States in HMM via Marginal Likelihood"
2. SSRN:4796238 — "Comparative Analysis of HMM and HSMM for Regime-Based Modeling"
3. SSRN:5580230 — "Modeling Financial Volatility with HMM"
4. arXiv:2410.00288 — "GARCH-Informed Neural Networks for Volatility Prediction"
5. ScienceDirect (2025) — "Forecasting Stock Market Anomalies in Emerging Markets"
6. arXiv:1509.01570 — "Real-time Financial Surveillance via CUSUM"
7. ScienceDirect (Lazar 2023) — "Change Point Detection in Risk Measures"
8. Medium — "Sensitivity Analysis of Q-R Noise Covariances in Kalman Filtering"

---

## 10. Next Steps

1. ✅ Research complete
2. ⬜ Implement HelperOptimizer class
3. ⬜ Add configurable parameters to helper classes
4. ⬜ Run optimization for all 20 target-horizons
5. ⬜ Save optimal configs to YAML
6. ⬜ Update helper_selection.py to use optimal configs
