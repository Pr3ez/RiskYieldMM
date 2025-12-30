# ML Trading Strategy Validation & Testing Research

**Date**: 2025-12-23  
**Purpose**: Research-backed plan for validating RiskYieldMM ML trading pipeline  
**Status**: Research complete, ready for implementation decisions

---

## 📚 Executive Summary

Research reveals that **over 90% of academic trading strategies fail** when implemented with real capital (Harvey et al., 2016). The key issues:

1. **Backtest Overfitting** - Parameter optimization finds patterns in noise
2. **Multiple Testing Bias** - Testing many strategies guarantees some look good by chance
3. **Regime Dependence** - Strategies work in some market conditions, fail in others
4. **Publication Bias** - Only "successful" backtests get reported

**Our Current Status**: We have solid walk-forward validation + conformal prediction. Research suggests additional layers needed for production-grade validation.

---

## 🔬 Literature Review Findings

### Paper 1: "Interpretable Hypothesis-Driven Trading" (arXiv:2512.12924, Dec 2024)

**The most relevant paper found - establishes modern walk-forward framework:**

| Metric | Their Result | Typical Published | Notes |
|--------|--------------|-------------------|-------|
| Annualized Return | **0.55%** | 15-30% | Honest vs overfitted |
| Sharpe Ratio | **0.33** | 1.35-5.8 | Real vs data-mined |
| p-value | **0.34** | <0.05 | Not significant! |
| Max Drawdown | -2.76% | -10-20% | Conservative risk |

**Key Methodological Innovations:**
1. **34 independent test periods** (quarterly for 10 years)
2. **Rolling 252-day train / 63-day test** windows
3. **Deflated Sharpe Ratio** for multiple testing correction
4. **Regime-conditional analysis** - separates high-vol vs low-vol periods

**Critical Finding**: Performance is **regime-dependent**:
- High volatility (2020-2024): **+0.60%** quarterly
- Low volatility (2015-2019): **-0.16%** quarterly

**Implication for us**: Our crypto/futures market has high volatility → may favor our strategy, but we need regime conditioning.

---

### Paper 2: "Backtest Overfitting in the Machine Learning Era" (SSRN:4778909, Nov 2024)

**Compares cross-validation methods for ML finance:**

| Method | PBO Score | DSR Test Statistic | Verdict |
|--------|-----------|-------------------|---------|
| **CPCV** | Lowest | Highest | **BEST** |
| Purged K-Fold | Medium | Medium | Second |
| K-Fold | High | Low | Problematic |
| Walk-Forward | Highest | Lowest | Industry standard but flawed |

**Key Concept - Probability of Backtest Overfitting (PBO)**:
```
PBO = P(Strategy ranked best in-sample performs worst out-of-sample)
```

**Key Concept - Combinatorial Purged Cross-Validation (CPCV)**:
- Creates **all possible train/test combinations** from time series
- Purges data between train/test to prevent leakage
- Computes PBO across all combinations
- Better at detecting overfitting than single walk-forward

**Implication for us**: Consider adding CPCV as secondary validation layer.

---

### Paper 3: Conformal Prediction for Finance (Multiple Papers)

**Papers found:**
- "Distribution-informed Online CP" (COP, arXiv:2512.07770)
- "Dual-Splitting CP for Multi-Step Time Series" (DSCP, arXiv:2503.21251)
- "Conformal Predictive Portfolio Selection" (CPPS, arXiv:2410.16333)
- "A Gentle Introduction to Conformal Time Series Forecasting" (arXiv:2511.13608)

**Key Methods Beyond Our Current ACI:**

| Method | Enhancement | Paper |
|--------|-------------|-------|
| **COP** | Uses estimated CDF for tighter intervals | 2512.07770 |
| **DSCP** | Multi-step forecasting via clustering | 2503.21251 |
| **CPPS** | Conformal intervals → portfolio weights | 2410.16333 |
| **NEXCP** | Non-exchangeable CP for adversarial streams | Barber et al. |
| **HopCPT** | Long time series optimization | Mentioned |
| **STACI** | Spatio-temporal with network topology | 2503.04981 |

**ACI Algorithm (what we implemented):**
```
α_{t+1} = α_t + γ(α_target - error_t)
```
- Our γ = 0.04 (validated on electricity prices)
- Stabilizes in 150-200 samples (we have 150 calibration)

**Advanced: CP-Traj (Trajectory-based)**:
- Optimizes across **entire forecast horizon** jointly
- Captures inter-step correlations
- Better for our multi-horizon predictions (1/3/6/12 bar)

---

### Paper 4: Distribution Shift & Concept Drift

**"DoubleAdapt: Meta-learning for Incremental Learning" (arXiv:2306.09862)**
- Addresses concept drift in stock forecasting
- Two types of shift:
  - **Covariate shift**: Feature distributions change
  - **Concept drift**: Relationship between features and target changes

**"An Early Warning System for Emerging Markets" (arXiv:2404.03319)**
- Online detection of concept drift
- EWS (Early Warning System) for regime changes

**"Out-of-Distribution Generalization in Time Series" (arXiv:2503.13868)**
- Survey of distribution shift methods
- Covers detection and adaptation strategies

---

## 📊 Validation Methodology Comparison

| Method | Detects | Our Status | Priority |
|--------|---------|------------|----------|
| Walk-Forward | Basic overfitting | ✅ Implemented | Core |
| Conformal Prediction | Uncertainty calibration | ✅ Implemented | Core |
| ACI | Non-stationary coverage | ✅ Implemented | Core |
| Deflated Sharpe Ratio | Multiple testing | ❌ Missing | **HIGH** |
| PBO (Probability Backtest Overfitting) | Strategy reliability | ❌ Missing | **HIGH** |
| CPCV | Combinatorial overfitting | ❌ Missing | MEDIUM |
| Regime Analysis | Conditional performance | ❌ Missing | **HIGH** |
| Concept Drift Detection | Model staleness | ❌ Missing | MEDIUM |
| Covariate Shift Monitoring | Feature distribution | ❌ Missing | MEDIUM |
| Economic Simulation | Real-world viability | ❌ Missing | HIGH |

---

## 🎯 Recommended Testing Plan

### Phase A: Statistical Rigor (HIGH PRIORITY)

**A1. Implement Deflated Sharpe Ratio**
```python
# Bailey & de Prado (2014) formula
DSR = SR * (1 - γ*skew/6 + (γ^2 - 3)*kurt/24) * sqrt(T/(T-1))
# Where γ = annualization factor, T = observations
```

**A2. Calculate PBO (Probability of Backtest Overfitting)**
- Run N different parameter combinations
- Track in-sample vs out-of-sample rank
- PBO = proportion where best IS = worst OOS

**A3. Multiple Testing Correction**
- Bonferroni: α_adjusted = α / n_tests
- Benjamini-Hochberg: Control FDR
- Apply to all 20 config comparisons

---

### Phase B: Regime Analysis (HIGH PRIORITY)

**B1. Define Volatility Regimes**
```python
# Simple approach
realized_vol = returns.rolling(20).std() * sqrt(252)
high_vol = realized_vol > realized_vol.quantile(0.75)
low_vol = realized_vol < realized_vol.quantile(0.25)
normal = ~high_vol & ~low_vol
```

**B2. Regime-Conditional Metrics**
- Compute IC/AUC separately for each regime
- Check if conformal coverage holds per regime
- Report regime-weighted performance

**B3. Transition Analysis**
- Performance at regime transitions
- Early warning of regime change
- Adaptive position sizing by regime

---

### Phase C: Conformal Enhancement (MEDIUM PRIORITY)

**C1. Coverage Stability Analysis**
```python
# Track rolling coverage
rolling_coverage = coverage.rolling(50).mean()
coverage_std = coverage.rolling(50).std()
# Alert if coverage drops below 85%
```

**C2. Multi-Horizon Correlation (CP-Traj idea)**
- Currently: Independent conformal per horizon
- Enhancement: Joint optimization across horizons
- Benefit: Captures 1bar→3bar→6bar dependencies

**C3. Interval Width Monitoring**
```python
# Uninformative if intervals too wide
avg_width = prediction_interval_width.mean()
signal_ratio = avg_width / realized_volatility
# Good: ratio < 2, Bad: ratio > 5
```

---

### Phase D: Distribution Shift (MEDIUM PRIORITY)

**D1. Covariate Shift Detection**
```python
# PSI (Population Stability Index)
PSI = sum((actual_pct - expected_pct) * log(actual_pct / expected_pct))
# PSI < 0.1: No shift, 0.1-0.25: Moderate, > 0.25: Significant
```

**D2. Concept Drift Monitoring**
```python
# Track rolling IC/AUC
rolling_ic = ic.rolling(50).mean()
if rolling_ic < threshold:
    trigger_retraining()
```

**D3. Model Staleness Alert**
- Compare recent performance to historical
- Automatic retraining trigger
- Cooldown period to prevent thrashing

---

### Phase E: Economic Simulation (HIGH PRIORITY)

**E1. Realistic Transaction Costs**
```python
# Per the walk-forward paper
commission = $1 per trade  # Or percentage
slippage = 0.05% * |position_size|  # 5 bps
```

**E2. Position Sizing with Conformal Intervals**
```python
# Kelly-style with uncertainty
kelly_fraction = edge / variance
confidence_adjusted = kelly_fraction * (1 - uncertainty)
position_size = min(confidence_adjusted, max_position)
```

**E3. Drawdown Analysis**
- Max drawdown by regime
- Recovery time analysis
- Tail risk metrics (CVaR, etc.)

---

## 📈 Implementation Roadmap

### Stage 1: Statistical Foundation (1 week)
- [ ] Implement Deflated Sharpe Ratio calculator
- [ ] Create PBO estimation module
- [ ] Add multiple testing corrections to summary reports
- [ ] Update ARCHITECTURE.md with statistical rigor section

### Stage 2: Regime Conditioning (1 week)
- [ ] Create regime classifier (volatility-based initially)
- [ ] Implement regime-conditional metrics
- [ ] Add regime column to all outputs
- [ ] Visualize performance by regime

### Stage 3: Monitoring Infrastructure (2 weeks)
- [ ] Coverage stability dashboard
- [ ] Covariate shift alerts
- [ ] Concept drift detection
- [ ] Automated retraining triggers

### Stage 4: Economic Validation (1 week)
- [ ] Transaction cost model
- [ ] Conformal-aware position sizing
- [ ] Drawdown/recovery analysis
- [ ] Paper trading simulation

---

## 📋 Key Metrics to Track (Summary)

| Category | Metric | Target | Alert Threshold |
|----------|--------|--------|-----------------|
| **Model** | IC (regression) | > 0.05 | < 0.02 |
| **Model** | AUC (classification) | > 0.55 | < 0.52 |
| **Statistical** | Deflated SR | > 0 | < 0 |
| **Statistical** | PBO | < 0.3 | > 0.5 |
| **Conformal** | Coverage | 87-93% | < 80% or > 97% |
| **Conformal** | Interval width | < 2x vol | > 5x vol |
| **Regime** | High-vol IC | Same as overall | -50% vs overall |
| **Drift** | PSI (features) | < 0.1 | > 0.25 |
| **Economic** | Sharpe after costs | > 0.5 | < 0 |
| **Economic** | Max drawdown | < 20% | > 30% |

---

## 📚 References

1. Harvey, C. R., et al. (2016). "...and the Cross-Section of Expected Returns." Review of Financial Studies.
2. Bailey, D., & de Prado, M. L. (2014). "The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting, and Non-Normality."
3. Bailey, D., & de Prado, M. L. (2015). "The Probability of Backtest Overfitting."
4. Pardo, R. (2008). "The Evaluation and Optimization of Trading Strategies."
5. Gibbs, I., & Candès, E. (2021). "Adaptive Conformal Inference Under Distribution Shift."
6. Deep, G., et al. (2024). "Interpretable Hypothesis-Driven Trading." arXiv:2512.12924.
7. Arian, H. R., et al. (2024). "Backtest Overfitting in the Machine Learning Era." SSRN:4778909.

---

## ❓ Decision Points for Przem

1. **Deflated Sharpe Ratio**: Implement immediately or wait?
2. **CPCV**: Worth the complexity vs walk-forward improvement?
3. **Regime Partitioning**: Use volatility? HMM states? Both?
4. **Position Sizing**: Simple Kelly or conformal-aware?
5. **Monitoring Frequency**: Daily? Per-prediction? Rolling window?

---

*Research compiled by Astra, 2025-12-23*
