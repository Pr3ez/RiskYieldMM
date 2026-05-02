# Ensemble Methods for Financial Time Series Prediction

## Research Documentation

**Date**: January 2025  
**Purpose**: Validate and document ensemble methodology for RiskYieldMM 4-model backtest  
**Models**: CatBoost + LightGBM + LSTM + Linear Ridge Regression

---

## 1. Executive Summary

This document synthesizes academic research on ensemble methods for financial forecasting to validate our 4-model ensemble implementation. Key findings:

1. **Model Diversity is Critical**: Heterogeneous ensembles (different model architectures) consistently outperform homogeneous ones
2. **The Forecast Combination Puzzle**: Simple averaging often beats "optimal" learned weights due to estimation error
3. **CatBoost + LightGBM + LSTM Combination**: Academically validated (arXiv:2505.23084) as effective hybrid
4. **Weighting Strategy**: Fixed weights may be more robust than learned weights for walk-forward scenarios

---

## 2. Theoretical Foundation: Forecast Combination

### 2.1 The Bates-Granger Framework (1969)

The seminal work by Bates and Granger established the theoretical foundation for forecast combination:

> "The main conclusion is that the composite set of forecasts can yield lower mean-square error than either of the original forecasts." — Bates & Granger, 1969

**Key Insight**: Even if individual forecasts are unbiased, combining them reduces forecast variance:

$$\text{Var}(\bar{f}) = \frac{1}{n^2} \sum_{i=1}^{n} \text{Var}(f_i) + \frac{1}{n^2} \sum_{i \neq j} \text{Cov}(f_i, f_j)$$

**Implication for our implementation**: When model predictions are not perfectly correlated, combination provides variance reduction.

### 2.2 The Forecast Combination Puzzle

**Source**: Qian et al. (2019) "On the Forecast Combination Puzzle" - Econometrics 7(3):39

**The Puzzle**: "Simple averaging of candidate forecasts is more robust than sophisticated combining methods" — repeatedly observed empirically.

**Causes identified**:
1. **Estimation Error**: Optimizing weights requires estimating covariance structure, which adds noise
2. **Structural Breaks**: Optimal weights become invalid when data distribution shifts
3. **Scenario Mismatch**: Using CFI (Combining for Improvement) methods in CFA (Combining for Adaptation) scenarios

**Key Finding**:
> "If the optimal combining weights are equal or close to equality, a simple average of competing forecasts is expected to be more accurate" — Smith & Wallis (2009)

**Implication for our implementation**: Our fixed weights (CB=0.30, LGB=0.30, LSTM=0.25, Linear=0.15) may be MORE robust than learned weights, especially with per-step retraining.

### 2.3 Two Forecast Combination Scenarios

From Qian et al. (2019):

| Scenario | Description | Goal | Recommended Approach |
|----------|-------------|------|---------------------|
| **CFA** (Combining for Adaptation) | One model is clearly best | Match best individual | AFTER method, simple averaging |
| **CFI** (Combining for Improvement) | Models capture different signals | Beat all individuals | Weighted combination |

**Our Situation**: We're likely in **CFI territory** because:
- Tree models (CB, LGB) capture non-linear interactions
- LSTM captures temporal dependencies
- Linear captures stable relationships
- Different architectures = different information extraction

---

## 3. Model Diversity: The Key to Ensemble Success

### 3.1 Why Diversity Matters

**Source**: Research on ensemble learner diversity

> "Model diversity is essential: ρ (correlation between forecasts) is correlated to the best ensemble RMSE by more than 70%. A low ρ between forecasts tends to increase ensemble performance."

**Variance Reduction Formula** for n diverse models:
$$\text{Ensemble Variance} = \frac{\sigma^2}{n} \cdot (1 + (n-1)\rho)$$

Where $\rho$ is average pairwise correlation between model predictions.

**Key Point**: Variance drops as $1/n$ **only if models are diverse**. If $\rho = 1$ (identical predictions), there's no benefit from combining.

### 3.2 Why Our 4-Model Ensemble is Well-Diversified

| Model | Architecture | What It Captures | Strengths |
|-------|--------------|------------------|-----------|
| **CatBoost** | Gradient Boosted Trees | Non-linear feature interactions, handles categoricals | Robust to noise, ordered boosting |
| **LightGBM** | Gradient Boosted Trees (GOSS) | Similar to CatBoost, different optimization | Faster training, leaf-wise growth |
| **LSTM** | Recurrent Neural Network | Temporal sequences, long-term dependencies | Sequential patterns, memory |
| **Linear Ridge** | Penalized Linear Regression | Linear relationships, stable features | Interpretable, regularized, fast |

**Expected Diversity**:
- **CB vs LGB**: Low-medium correlation (similar architecture, different implementation)
- **Trees vs LSTM**: Medium correlation (different pattern recognition)
- **Trees/LSTM vs Linear**: Medium-low correlation (non-linear vs linear patterns)

### 3.3 Academic Validation of Tree + LSTM Combination

**Source**: arXiv:2505.23084 "Gradient Boosting Decision Tree with LSTM for Investment Prediction" (Yu et al., 2025)

> "This paper proposes a hybrid framework combining LSTM with LightGBM and CatBoost for stock price prediction... Experimental results show that the proposed framework improves accuracy by 10 to 15 percent compared to individual models and reduces error during market changes."

**Key Findings**:
- The specific combination of **CatBoost + LightGBM + LSTM** is academically validated
- Ensemble approach handles market regime changes better than individual models
- 10-15% improvement over single models

**Our Implementation Aligns**: We use exactly this combination (plus Linear for regularization).

---

## 4. Weight Selection Strategies

### 4.1 Fixed Weights vs. Learned Weights

| Strategy | Pros | Cons | Best When |
|----------|------|------|-----------|
| **Equal Weights** | Simple, robust to estimation error | Ignores model quality differences | Models are similarly skilled |
| **Fixed Weights** | Domain knowledge incorporated, stable | Suboptimal if model qualities shift | Historical performance is stable guide |
| **Learned Weights** | Adapts to data, potentially optimal | Estimation error, overfitting risk | Large validation set, stable regime |

### 4.2 Our Weight Choice Rationale

Current weights: **CB=0.30, LGB=0.30, LSTM=0.25, Linear=0.15**

**Justification**:
1. **Tree models get 60% total**: Strong performance on tabular data (documented in ML literature)
2. **LSTM gets 25%**: Captures temporal patterns trees may miss, but harder to train
3. **Linear gets 15%**: Stable baseline, regularization effect, prevents overfitting

**Alternative Considered**: Learning weights via Optuna
- **Risk**: Estimation error compounds with per-step retraining
- **Research Suggests**: For walk-forward with small windows, fixed weights may be more robust

### 4.3 The mAFTER Strategy (Multi-level AFTER)

From Qian et al. (2019), a theoretically sound adaptive approach:

1. Create candidate forecasts: SA (simple average), AFTER, LinReg
2. Apply AFTER algorithm to combine these candidates
3. Automatically adapts to CFA vs CFI scenario

**Consideration for Future**: Could implement mAFTER as a validation experiment.

---

## 5. Ensemble for Classification vs. Regression

### 5.1 Classification (Direction Prediction, Volatility Regime)

**Combining Probabilities** (our approach):
$$p_{ensemble}(y=k) = \sum_{m=1}^{M} w_m \cdot p_m(y=k)$$

**Alternative Approaches**:
- Voting (majority vote for class)
- Stacking (meta-learner on probabilities)
- Calibrated ensemble (probability calibration first, then average)

**Our Implementation**: Weighted average of class probabilities
- Advantage: Preserves probability interpretation
- Calibration applied post-ensemble (conformal)

### 5.2 Regression (Return Magnitude, Volatility)

**Combining Predictions** (our approach):
$$\hat{y}_{ensemble} = \sum_{m=1}^{M} w_m \cdot \hat{y}_m$$

**Standard and well-supported by literature.**

---

## 6. Time Series Specific Considerations

### 6.1 Walk-Forward Validation

Our approach (walk-forward with expanding window) is standard for time series:

```
Step 1: Train on [0, 500], Predict step 501
Step 2: Train on [0, 501], Predict step 502
...
```

**Key Properties**:
- No future information leakage
- Models adapt to new data
- Mimics actual trading deployment

### 6.2 Non-Stationarity Handling

Financial time series are non-stationary. Research recommendations:

1. **Rolling Windows**: Use recent data only (we use expanding with all data)
2. **Regime Detection**: Different models for different regimes (we handle via diverse ensemble)
3. **Adaptive Weights**: Time-varying combination weights

**From Hendry & Clements (2004)**:
> "When candidate forecasting models are all misspecified and breaks occur in the information variables, forecast combination methods that target the optimal weight may not perform as well as simple average."

**Our Mitigation**: 
- Diverse models capture different regimes
- Fixed weights avoid estimation error during regime shifts
- Per-step Optuna tunes hyperparameters (not weights) to adapt

### 6.3 Estimation Error in Time Series Context

The forecast combination puzzle is **amplified** in time series:

1. Serial correlation in errors
2. Changing optimal weights over time
3. Limited effective sample size

**Implication**: Our choice of fixed weights is **more defensible** than learned weights.

---

## 7. Implementation Recommendations

### 7.1 Current Implementation Assessment

| Aspect | Our Implementation | Academic Recommendation | Assessment |
|--------|-------------------|------------------------|------------|
| Model Diversity | CB, LGB, LSTM, Linear | Use heterogeneous models | ✅ Excellent |
| Weight Strategy | Fixed (0.30, 0.30, 0.25, 0.15) | Fixed or equal often best | ✅ Good |
| Combination Method | Weighted average of predictions | Standard approach | ✅ Standard |
| Calibration | Post-ensemble conformal | Apply calibration | ✅ Good |
| Validation | Walk-forward | Required for time series | ✅ Correct |

### 7.2 Potential Improvements (Future Work)

1. **Weight Sensitivity Analysis**: Test equal weights (0.25 each) vs. current weights
2. **Model Agreement Metrics**: Track pairwise prediction correlations
3. **Regime-Conditional Weights**: Different weights for different volatility regimes
4. **mAFTER Implementation**: Adaptive scenario-aware combination
5. **Dynamic Weight Learning**: Learn weights on validation fold, apply to test

### 7.3 Warning Signs to Monitor

- **High Model Correlation**: If predictions become too similar, diversity benefit lost
- **Consistent Underperformer**: If one model consistently worst, consider removing or reweighting
- **Weight Sensitivity**: If small weight changes cause large performance swings, weights may be unstable

---

## 8. Key Academic References

### Primary Sources

1. **Bates, J.M. & Granger, C.W.J. (1969)**. "The Combination of Forecasts." *Operations Research Quarterly*, 20(4), 451-468.
   - Foundational paper on forecast combination

2. **Qian, W., Rolling, C.A., Cheng, G., & Yang, Y. (2019)**. "On the Forecast Combination Puzzle." *Econometrics*, 7(3), 39.
   - Comprehensive analysis of why simple averaging beats optimal weights
   - Introduces mAFTER strategy

3. **Yu, C. et al. (2025)**. "Gradient Boosting Decision Tree with LSTM for Investment Prediction." *arXiv:2505.23084*.
   - Validates CB + LGB + LSTM combination for financial forecasting
   - Reports 10-15% improvement over individual models

4. **Shahhosseini, M., Hu, G., & Pham, H. (2019)**. "Optimizing Ensemble Weights and Hyperparameters of Machine Learning Models for Regression Problems." *arXiv:1908.05287*.
   - GEM-ITH method for weight optimization
   - Shows importance of diversity in base learners

### Supporting Sources

5. **Smith, J. & Wallis, K.F. (2009)**. "A Simple Explanation of the Forecast Combination Puzzle." *Oxford Bulletin of Economics and Statistics*, 71(3), 331-355.
   - When optimal weights are close to equal, simple average is more accurate

6. **Timmermann, A. (2006)**. "Forecast Combinations." *Handbook of Economic Forecasting*, 1, 135-196.
   - Comprehensive survey of combination methods

7. **Stock, J.H. & Watson, M.W. (2004)**. "Combination Forecasts of Output Growth in a Seven-Country Data Set." *Journal of Forecasting*, 23(6), 405-430.
   - Coined "forecast combination puzzle" term
   - Empirical evidence that simple methods dominate

8. **Hendry, D.F. & Clements, M.P. (2004)**. "Pooling of Forecasts." *The Econometrics Journal*, 7(1), 1-31.
   - Analysis of combination under structural breaks

---

## 9. Conclusion

Our 4-model ensemble implementation (CatBoost + LightGBM + LSTM + Linear) is **well-aligned with academic best practices**:

1. **Model Selection**: The specific combination of gradient boosting + LSTM is academically validated for financial forecasting
2. **Diversity**: Four architecturally different models provide the diversity needed for effective combination
3. **Weight Strategy**: Fixed weights are defensible given the forecast combination puzzle - estimation error from learning weights may outweigh any optimization benefit
4. **Walk-Forward**: Proper temporal validation prevents information leakage

**Key Takeaway**: 
> "The apparent puzzle in forecast combination—that simple averages often beat optimal linear weights—is explained by the estimation error in the estimated optimal weights."

Our fixed weights (CB=0.30, LGB=0.30, LSTM=0.25, Linear=0.15) represent a reasonable prior based on:
- Tree models' documented strength on tabular data
- LSTM's ability to capture temporal patterns
- Linear's regularization and stability properties

**Recommendation**: Continue with current implementation. Consider equal-weight comparison as sensitivity analysis.

---

*Document generated: January 2025*  
*Sources: arXiv, MDPI Econometrics, academic journals*
