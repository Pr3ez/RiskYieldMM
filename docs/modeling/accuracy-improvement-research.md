# Academic Research: Improving Direction Prediction Accuracy

> Historical note
>
> This research note predates the current multi-asset source and HTF
> materialization branch. References to BTC-only features describe the older
> state. Current HTF outputs can be prepared per asset, and Stage-1 can build
> exact-timestamp target/context merged datasets; as-of/freshness context joins
> and downstream diagnostics remain future work.

**Date:** 2025-12-31  
**Context:** RiskYieldMM BTC perpetual futures, 8h timeframe  
**Current state:** 52% baseline, 67.5% in optimal regime  
**Break-even:** ~55% with 10bps costs

---

## Executive Summary

Based on systematic review of academic literature, here are **evidence-based methods** to improve direction prediction accuracy, ranked by expected impact and implementation complexity.

---

## 🥇 TIER 1: High Impact, Strong Evidence

### 1. Triple Barrier Labeling (Lopez de Prado, 2018)
**Source:** "Advances in Financial Machine Learning" - Chapter 3

**What it is:** Instead of simple direction labels (up/down), use outcome-based labels:
- **+1**: Price hits take-profit first
- **-1**: Price hits stop-loss first  
- **0**: Neither hit within time horizon

**Why it helps:**
- Aligns labels with actual trading outcomes
- Reduces noise from small, unprofitable moves
- Foundation for meta-labeling

**Expected impact:** +5-10% accuracy improvement  
**Implementation complexity:** Medium  
**Our status:** ✅ Already using in strategy backtest, but NOT in model training

**ACTION:** Re-train direction models with triple-barrier labels instead of simple return sign.

---

### 2. Meta-Labeling (Lopez de Prado, 2018)
**Source:** "Advances in Financial Machine Learning" - Chapter 3.6

**What it is:** Two-stage approach:
1. Primary model predicts direction (side)
2. Secondary model predicts if the trade will be profitable (size/confidence)

**Why it helps:**
- Separates "which way" from "will it work"
- Can filter low-confidence signals
- Reduces false positives significantly

**Expected impact:** +10-15% precision improvement (trades taken)  
**Implementation complexity:** Medium  
**Our status:** ❌ Not implemented

**ACTION:** Train a meta-model that predicts P(profitable | direction_signal, regime, features)

---

### 3. Sample Weighting by Uniqueness (Lopez de Prado, 2018)
**Source:** "Advances in Financial Machine Learning" - Chapter 4

**What it is:** Weight training samples by:
- **Return attribution:** Higher weight to larger moves
- **Sample uniqueness:** Down-weight overlapping labels
- **Time decay:** More recent samples weighted higher

**Why it helps:**
- Overlapping labels cause information leakage
- Standard weighting treats all samples equally (wrong for finance)
- Return attribution focuses on samples that matter economically

**Expected impact:** +3-5% accuracy, +significant robustness  
**Implementation complexity:** Medium  
**Our status:** ❌ Only have `class_weight='balanced'`, not uniqueness weighting

**ACTION:** Implement `sample_weight` based on return attribution and label uniqueness.

---

### 4. Fractional Differentiation (Lopez de Prado, 2018)
**Source:** "Advances in Financial Machine Learning" - Chapter 5

**What it is:** Instead of full differencing (returns) which loses memory, use fractional order d ∈ (0, 1):
- d=0: raw prices (non-stationary, has memory)
- d=1: returns (stationary, no memory)
- d=0.3-0.5: optimal balance (stationary AND has memory)

**Why it helps:**
- Standard returns throw away valuable long-term memory
- Fractionally differenced prices remain stationary
- Preserves predictive information

**Expected impact:** +2-5% IC improvement on features  
**Implementation complexity:** Low-Medium  
**Our status:** ❌ Using standard returns

**ACTION:** Apply fractional differentiation to price features with d optimized via ADF test.

---

## 🥈 TIER 2: Moderate Impact, Good Evidence

### 5. Signal Denoising (Feiler, 2024 - arXiv:2408.05690)
**Source:** "Strong denoising of financial time-series"

**What it is:** 
- Paired autoencoders trained on related inputs
- "Conversation" process where models reconcile predictions
- Mutual regularization discovers common signal

**Why it helps:**
- Financial data is extremely noisy (~95%+ noise)
- Denoising reveals underlying regularities
- Can be applied to both features and targets

**Alternative approaches:**
- **CEEMDAN + wavelet:** Empirical mode decomposition + wavelet threshold
- **VMD:** Variational Mode Decomposition

**Expected impact:** +3-8% signal-to-noise improvement  
**Implementation complexity:** High  
**Our status:** ❌ Not implemented

**ACTION:** Test CEEMDAN denoising on price series before feature engineering.

---

### 6. Crypto-Specific Features (Multiple sources, 2023-2025)

**Derivative market signals with predictive power:**

| Feature | Academic Support | Status |
|---------|-----------------|--------|
| Funding rate | Inan (2024), Gate.com | ✅ Have data, ❌ not used |
| Open interest | SSRN 5576424 | ✅ Have data, ❌ not used |
| Long/short ratio | Multiple | ✅ Have data, ❌ not used |
| Basis (spot-futures) | Wiley fut.22425 | ❌ Not computed |
| Basis momentum | Wiley fut.22425 | ❌ Not computed |
| Liquidation data | Gate.com 2025 | ❌ No data |

**Expected impact:** +3-7% from derivatives features  
**Implementation complexity:** Low (data already available)  
**Our status:** Data exists in `fetchingByBit/` but NOT integrated into features

**ACTION:** Engineer features from funding_rate, open_interest, long_short_ratio.

---

### 7. Cross-Asset Features

**What it is:** Include correlated asset signals:
- ETH/BTC ratio (altcoin momentum)
- DXY (dollar index) or inverse proxy
- SPX/VIX for risk-on/risk-off
- Gold (safe haven correlation)

**Why it helps:**
- BTC doesn't trade in isolation
- Cross-asset momentum and mean-reversion patterns
- Risk regime shifts visible in other assets first

**Expected impact:** +2-5% accuracy  
**Implementation complexity:** Medium (need data)  
**Historical status at note time:** BTC-only features

**ACTION:** Add ETH/BTC ratio and consider macro proxies.

---

## 🥉 TIER 3: Lower Impact or Higher Uncertainty

### 8. Model Architecture Changes

**Research findings:**
- **TabNet:** "Often outperformed by XGBoost" (ResearchGate)
- **TFT (Temporal Fusion Transformer):** Mixed results vs traditional
- **TabPFN:** Promising but limited to small datasets (<1000 samples)
- **LSTM/CNN:** Only outperform on very large datasets (>100k samples)

**Conclusion:** GBDT (LightGBM/CatBoost) remains best for tabular financial data.  
**Our status:** ✅ Already using optimal architecture

**ACTION:** Keep current ensemble. Focus on features/labels instead.

---

### 9. Ensemble Stacking (WJARR, 2025)

**What it is:** 
- Level-1: Multiple base models (XGB, LGB, CatBoost, Ridge)
- Level-2: Meta-learner combines Level-1 predictions

**Why it helps:**
- Different models capture different patterns
- Meta-learner learns optimal combination
- Reduces variance without increasing bias

**Expected impact:** +1-3% accuracy  
**Implementation complexity:** Medium  
**Our status:** ⚠️ Have ensemble but not proper stacking

**ACTION:** Implement proper stacking with held-out meta-training set.

---

## 📋 Prioritized Action Plan

| Priority | Action | Expected Lift | Effort | Dependencies |
|----------|--------|---------------|--------|--------------|
| **1** | Triple-barrier labels for training | +5-10% | Medium | None |
| **2** | Meta-labeling secondary model | +10-15% precision | Medium | #1 |
| **3** | Derivatives features (funding, OI) | +3-7% | Low | None |
| **4** | Sample weighting (uniqueness) | +3-5% | Medium | None |
| **5** | Fractional differentiation | +2-5% IC | Low | None |
| **6** | Cross-asset features (ETH/BTC) | +2-5% | Medium | Data |
| **7** | Signal denoising (CEEMDAN) | +3-8% | High | None |
| **8** | Proper stacking ensemble | +1-3% | Medium | None |

---

## Key Academic Sources

1. **Lopez de Prado, M. (2018)** - "Advances in Financial Machine Learning" - Wiley
   - Triple barrier, meta-labeling, sample weighting, fractional differentiation
   - The foundational text for financial ML

2. **Feiler, M.J. (2024)** - "Strong denoising of financial time-series" - arXiv:2408.05690
   - Autoencoder-based denoising method

3. **Inan, E. (2024)** - "Predictability of Funding Rates" - SSRN 5576424
   - Bitcoin perpetual futures funding rate predictive power

4. **Akşehir, Z.D. (2024)** - "2LE-CEEMDAN method" - PubMed 38435596
   - Denoising approach for financial time series

5. **Ali, A. (2024)** - "Four-factor crypto asset pricing" - SSRN 5527518
   - Momentum, reversal, illiquidity factors for crypto

6. **Wiley fut.22425 (2023)** - "Risk factors in cryptocurrency futures"
   - Basis and basis-momentum as predictive factors

---

## What NOT to Pursue (Evidence-Based)

| Approach | Why Not |
|----------|---------|
| TabNet | Consistently underperforms XGBoost |
| LSTM/CNN | Need much larger datasets than we have |
| LLM sentiment | Requires infrastructure, uncertain lift |
| Deep RL | High complexity, poor reproducibility |
| GANs for data augmentation | Mode collapse risk, hard to tune |

---

## Conclusion

**The biggest opportunities are:**
1. **Label engineering** (triple-barrier, meta-labeling) - This changes WHAT we predict
2. **Feature engineering** (derivatives data, fractional diff) - This changes INPUT signal
3. **Sample engineering** (uniqueness weighting) - This changes HOW we train

Model architecture changes are unlikely to help significantly. The literature strongly suggests our LightGBM/CatBoost ensemble is near-optimal for tabular financial data. The gains come from better data preparation, not model complexity.

**Recommended next step:** Implement triple-barrier labeling for model training and test accuracy improvement before moving to meta-labeling.
