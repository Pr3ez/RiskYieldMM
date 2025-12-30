# Phase 1: Task-Specific Preprocessing Pipeline Design

**Date**: 2025-12-24
**Status**: IN PROGRESS

---

## Overview

Based on Phase 0 audits, we design **3 distinct preprocessing pipelines** for **5 target types** × **4 horizons** = **20 workflows**.

### Pipeline Summary

| Task Type | Targets | Base Pipeline | Helper Pipeline |
|-----------|---------|---------------|-----------------|
| **Regression (Returns)** | returns (1,3,6,12) | Winsorize → RollingZScore | Winsorize |
| **Regression (Volatility)** | volatility (1,3,6,12) | Winsorize → Log → ExpandingZScore | Winsorize |
| **Classification** | direction, trend_regime, vol_regime (12 total) | Winsorize → ExpandingRank | ExpandingRank |

---

## 1.1 Feature Groups Definition

Based on Phase 0.2 audit (166 base features + 58 helper features):

### Base Feature Groups (166 total)

```python
FEATURE_GROUPS = {
    # Already bounded [0,1] — NO preprocessing needed
    "BOUNDED": [
        # 36 features with _bnd_, _bin, _rnk_ suffix
        "N_P_V_pctB_*_bnd_N",       # Bollinger %B
        "C_N_*_bnd_N",              # Candle patterns
        "B_C_candleDirection_bin",  # Binary
        "M_N_rsi_*_bnd_N",          # RSI
        "M_N_stochasticK_*_bnd_N",  # Stochastic
        "M_N_T_stochasticD_*_bnd_N",
        "F_TM_*_bin",               # Temporal binary
        "B_TM_*_bin",
        "N_V_atrPercentile_*_rnk_N", # Ranks
        "V_autocorr_*_bnd_N",       # Autocorrelation
        "B_consecutive*_bnd_N",     # Consecutive counts
        "M_winRate_*_bnd_N",        # Win rate
        "L_M_S_mfi_*_bnd_N",        # MFI
        "L_M_S_cmf_*_bnd_N",        # CMF
        "M_T_V_adx_*_bnd_N",        # ADX
        "M_T_V_diDiff_*_bnd_N",     # DI difference
    ],
    
    # Already z-scored — LIGHT preprocessing only (winsorize extreme)
    "ZSCORE": [
        # 12 features with _zsc_ suffix
        "F_I_N_S_fundingZscore_*_zsc_N",
        "D_F_N_S_premiumZscore_*_zsc_N",
        "N_P_zScore_*_zsc_N",
        "L_M_S_obv_*_zsc_N",
        "N_M_cci_*_zsc_N",
    ],
    
    # Returns/Momentum — symmetric, regime-adaptive
    "RETURNS": [
        # ~32 features
        "M_P_logReturn_pct_N",
        "M_P_roc_*_pct_N",
        "M_P_V_momAtr_*_rat_N",
        "M_T_ppo_*_pct_N",
        "N_P_T_price*Deviation_*_pct_N",
        "M_N_rocAccel_*_dif_N",
        "M_P_L_vwapReturn_pct_N",
        "M_P_S_W_oiWeightedReturn_pct_N",
        "M_P_D_markReturnDiff_pct_N",
    ],
    
    # Volatility — right-skewed, need log transform
    "VOLATILITY": [
        # ~58 features
        "V_atrPct_*_pct_N",
        "V_returnStd_*_pct_N",
        "N_V_bollingerBandwidth_*_pct_N",
        "V_volOfVol_*_pct_N",
        "V_skew_*_rat_N",
        "V_kurtosis_*_rat_N",
        "V_maxDrawdown_*_pct_N",
        "M_V_sharpe_*_rat_N",
        "M_V_sortino_*_rat_N",
        "M_V_calmar_*_rat_N",
        "V_volMomentum_*_pct_N",
        "V_parkinson_*_pct_N",
        "V_garmanKlass_*_pct_N",
        "V_rogersSatchell_*_pct_N",
        "V_yangZhang_*_pct_N",
        "V_hurstExponent_*_rat_N",
        "D_N_closeVsMarkVol_*_pct_N",
        "M_N_V_rangeExpansion_*_rat_N",
        "V_D_F_S_premiumRange_pct_N",
        "D_N_premiumRange_rat_N",
    ],
    
    # Volume/OI — right-skewed
    "VOLUME": [
        # ~29 features
        "L_M_N_volumeRoc_*_pct_N",
        "L_N_volumeRatio_*_rat_N",
        "L_M_N_S_oiPctChange_pct_N",
        "L_N_volOiRatio_rat_N",
        "L_M_N_S_oiRoc_*_pct_N",
        "L_N_S_oiRatio_*_rat_N",
        "L_V_amihudIlliquidity_*_rat_N",
        "L_S_oiVolumeRatio_*_rat_N",
    ],
    
    # Sentiment/Funding — can be positive or negative
    "SENTIMENT": [
        # ~27 features
        "F_I_fundingCumulative_*_pct_N",
        "F_I_T_fundingMa_*_pct_N",
        "F_I_M_fundingMaDiff_*_pct_N",
        "D_F_T_premiumMa_*_pct_N",
        "D_F_basis_pct_N",
        "D_markIndexSpread_pct_N",
        "M_D_F_S_premiumChange_pct_N",
        "S_longShortRatio_rat_N",
        "S_N_longShortZscore_*_zsc_N",
        "S_M_longShortChange_*_pct_N",
    ],
    
    # Mark price deviations
    "MARK": [
        "D_N_markCloseDeviation_pct_N",
        "D_N_V_markCloseRange_rat_N",
        "D_N_V_markAtrRatio_*_rat_N",
        "N_P_L_vwapDeviation_pct_N",
    ],
}
```

### Helper Feature Groups (58 total)

```python
HELPER_GROUPS = {
    # Already bounded [0,1] or discrete — NO preprocessing
    "BOUNDED": [
        # 14 features
        "H_*_if_*_is",              # Binary anomaly flags
        "H_*_if_*_severity",        # Severity [0,1]
        "H_*_hmm*_prob_*",          # HMM probabilities [0,1]
        "H_*_hmm*_confidence",      # Confidence [0,1]
        "H_*_cp_*",                 # Changepoint binaries
    ],
    
    # Discrete states — NO preprocessing
    "DISCRETE": [
        # 5 features
        "H_*_hmm*_state",           # HMM state (0,1,2,3,4)
        "H_*_garch_vol_regime",     # GARCH regime (0,1,2)
        "H_*_kalman_regime",        # Kalman regime (0,1,2)
        "H_*_if_n_anomalies",       # Count (0,1,2,3)
    ],
    
    # Unbounded scores — NEED preprocessing
    "UNBOUNDED": [
        # 30 features
        "H_*_if_*_score",           # IF anomaly scores
        "H_*_cusum_*",              # CUSUM values (pos/neg)
        "H_*_garch_*",              # GARCH features (except regime)
        "H_*_hmm*_entropy",         # HMM entropy
        "H_*_hmm*_duration",        # HMM duration
        "H_*_kalman_*",             # Kalman features (except regime)
    ],
}
```

---

## 1.2 Returns Preprocessing Pipeline (4 horizons)

### Target
```python
# Net candle return (captures intracandle volatility)
future_high = high.shift(-horizon)
future_low = low.shift(-horizon)
up_move = (future_high - close) / close
down_move = (close - future_low) / close
y_returns = up_move - down_move
```

### Task Type: Regression (continuous)

### Base Pipeline
```python
class ReturnsPipeline:
    """Preprocessing for returns prediction (regression)."""
    
    def __init__(self):
        self.winsorizer = ExpandingWinsorizer(lower=0.01, upper=0.99, min_periods=252)
        self.zscore = RollingZScoreScaler(window=63, min_periods=21)
    
    def fit_transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """
        Pipeline:
        1. BOUNDED group: pass through
        2. ZSCORE group: light winsorize only (already standardized)
        3. All others: Winsorize → RollingZScore
        """
        result = X.copy()
        
        # Identify groups
        bounded = get_features_by_group(X.columns, "BOUNDED")
        zscore_feats = get_features_by_group(X.columns, "ZSCORE")
        others = set(X.columns) - bounded - zscore_feats
        
        # Step 1: Bounded — pass through
        # (no change needed)
        
        # Step 2: Z-score features — light winsorize only
        for col in zscore_feats:
            result[col] = self.winsorizer.transform(X[[col]])[col]
        
        # Step 3: All others — Winsorize → RollingZScore
        for col in others:
            winsorized = self.winsorizer.transform(X[[col]])
            result[col] = self.zscore.transform(winsorized)[col]
        
        return result
```

### Helper Pipeline
```python
class ReturnsHelperPipeline:
    """Light preprocessing for helper features in returns prediction."""
    
    def __init__(self):
        self.winsorizer = ExpandingWinsorizer(lower=0.01, upper=0.99, min_periods=126)
    
    def fit_transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """
        Pipeline:
        1. BOUNDED/DISCRETE helper groups: pass through
        2. UNBOUNDED helper group: light winsorize only
        
        Note: Helper features are already somewhat normalized by their
        algorithms. Heavy preprocessing could destroy their signal.
        """
        result = X.copy()
        
        bounded = get_helper_features_by_group(X.columns, "BOUNDED")
        discrete = get_helper_features_by_group(X.columns, "DISCRETE")
        unbounded = get_helper_features_by_group(X.columns, "UNBOUNDED")
        
        # Only winsorize unbounded helper features
        for col in unbounded:
            result[col] = self.winsorizer.transform(X[[col]])[col]
        
        return result
```

### Rationale
- **RollingZScore**: Returns are regime-dependent (high vol vs low vol). Rolling Z-score adapts to current regime.
- **Window=63**: ~21 days of 8h bars. Balances responsiveness vs stability.
- **Light helper preprocessing**: Helper models already output normalized features. Heavy preprocessing destroys their signal.

---

## 1.3 Volatility Preprocessing Pipeline (4 horizons)

### Target
```python
y_volatility = df["close"].pct_change(1).abs().rolling(horizon).mean()  # Realized vol
# OR simply:
y_volatility = df["close"].pct_change(horizon).abs()  # Absolute return
```

### Task Type: Regression (continuous, right-skewed)

### Base Pipeline
```python
class VolatilityPipeline:
    """Preprocessing for volatility prediction (regression)."""
    
    def __init__(self):
        self.winsorizer = ExpandingWinsorizer(lower=0.01, upper=0.99, min_periods=252)
        self.log_transform = SignedLogTransformer()
        self.zscore = ExpandingZScoreScaler(min_periods=252)
    
    def fit_transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """
        Pipeline:
        1. BOUNDED group: pass through
        2. ZSCORE group: light winsorize only
        3. VOLATILITY group: Winsorize → Log → ExpandingZScore
        4. All others: Winsorize → ExpandingZScore
        
        Note: Expanding (not rolling) to preserve magnitude information.
        Volatility prediction cares about absolute level, not just relative.
        """
        result = X.copy()
        
        bounded = get_features_by_group(X.columns, "BOUNDED")
        zscore_feats = get_features_by_group(X.columns, "ZSCORE")
        vol_feats = get_features_by_group(X.columns, "VOLATILITY")
        others = set(X.columns) - bounded - zscore_feats - vol_feats
        
        # Step 1: Bounded — pass through
        
        # Step 2: Z-score features — light winsorize
        for col in zscore_feats:
            result[col] = self.winsorizer.transform(X[[col]])[col]
        
        # Step 3: Volatility features — Winsorize → Log → ExpandingZScore
        for col in vol_feats:
            winsorized = self.winsorizer.transform(X[[col]])
            logged = self.log_transform.transform(winsorized)
            result[col] = self.zscore.transform(logged)[col]
        
        # Step 4: Others — Winsorize → ExpandingZScore
        for col in others:
            winsorized = self.winsorizer.transform(X[[col]])
            result[col] = self.zscore.transform(winsorized)[col]
        
        return result
```

### Helper Pipeline
Same as Returns — light winsorize only.

### Rationale
- **Log transform**: Volatility is right-skewed. Log makes distribution more Gaussian.
- **ExpandingZScore (not rolling)**: Volatility prediction cares about absolute level. Rolling would normalize away magnitude information.
- **Volatility features get special treatment**: They're already measuring volatility-like quantities.

---

## 1.4 Classification Preprocessing Pipeline (12 horizons)

### Targets
```python
# Direction (binary) - uses net candle return
future_high = high.shift(-horizon)
future_low = low.shift(-horizon)
up_move = (future_high - close) / close
down_move = (close - future_low) / close
net_candle_ret = up_move - down_move
y_direction = (net_candle_ret > 0).astype(int)

# Trend regime (binary)
y_trend_regime = ... # From HMM or momentum indicator

# Vol regime (multiclass)
y_vol_regime = pd.qcut(realized_vol, q=3, labels=[0, 1, 2])  # LOW/MED/HIGH
```

### Task Type: Binary/Multiclass Classification

### Base Pipeline
```python
class ClassificationPipeline:
    """Preprocessing for classification (direction, trend_regime, vol_regime)."""
    
    def __init__(self):
        self.winsorizer = ExpandingWinsorizer(lower=0.01, upper=0.99, min_periods=252)
        self.rank_transform = ExpandingRankTransformer(min_periods=252)
    
    def fit_transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """
        Pipeline:
        1. BOUNDED group: pass through
        2. All others: Winsorize → ExpandingRank → [0, 1]
        
        Note: Classification benefits from rank-based features.
        Ranks preserve monotonicity while eliminating scale effects.
        Tree-based models (CatBoost, LightGBM) work well with ranks.
        """
        result = X.copy()
        
        bounded = get_features_by_group(X.columns, "BOUNDED")
        others = set(X.columns) - bounded
        
        # Step 1: Bounded — pass through
        
        # Step 2: All others — Winsorize → ExpandingRank
        for col in others:
            winsorized = self.winsorizer.transform(X[[col]])
            result[col] = self.rank_transform.transform(winsorized)[col]
        
        return result
```

### Helper Pipeline
```python
class ClassificationHelperPipeline:
    """Preprocessing for helper features in classification."""
    
    def __init__(self):
        self.winsorizer = ExpandingWinsorizer(lower=0.01, upper=0.99, min_periods=126)
        self.rank_transform = ExpandingRankTransformer(min_periods=126)
    
    def fit_transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """
        Pipeline:
        1. BOUNDED/DISCRETE helper groups: pass through
        2. UNBOUNDED helper group: Winsorize → ExpandingRank
        
        Note: Classification models work better with ranked features.
        This transforms unbounded helper outputs to [0,1] percentiles.
        """
        result = X.copy()
        
        bounded = get_helper_features_by_group(X.columns, "BOUNDED")
        discrete = get_helper_features_by_group(X.columns, "DISCRETE")
        unbounded = get_helper_features_by_group(X.columns, "UNBOUNDED")
        
        # Bounded/Discrete — pass through
        
        # Unbounded — Winsorize → ExpandingRank
        for col in unbounded:
            winsorized = self.winsorizer.transform(X[[col]])
            result[col] = self.rank_transform.transform(winsorized)[col]
        
        return result
```

### Rationale
- **ExpandingRank**: Classification doesn't care about absolute values, only relative ordering.
- **[0, 1] output**: All features become percentiles. This:
  - Eliminates scale differences between features
  - Handles outliers naturally (extreme values → 0 or 1)
  - Works well with tree-based models
- **Helper features also ranked**: Consistent preprocessing for classification

---

## 1.5 Summary Table: All 20 Workflows

| # | Target | Horizon | Task | Base Pipeline | Helper Pipeline |
|---|--------|---------|------|---------------|-----------------|
| 1 | returns | 1 | regression | Winsorize → RollingZScore | Winsorize |
| 2 | returns | 3 | regression | Winsorize → RollingZScore | Winsorize |
| 3 | returns | 6 | regression | Winsorize → RollingZScore | Winsorize |
| 4 | returns | 12 | regression | Winsorize → RollingZScore | Winsorize |
| 5 | volatility | 1 | regression | Winsorize → Log → ExpandingZScore | Winsorize |
| 6 | volatility | 3 | regression | Winsorize → Log → ExpandingZScore | Winsorize |
| 7 | volatility | 6 | regression | Winsorize → Log → ExpandingZScore | Winsorize |
| 8 | volatility | 12 | regression | Winsorize → Log → ExpandingZScore | Winsorize |
| 9 | direction | 1 | binary | Winsorize → ExpandingRank | ExpandingRank |
| 10 | direction | 3 | binary | Winsorize → ExpandingRank | ExpandingRank |
| 11 | direction | 6 | binary | Winsorize → ExpandingRank | ExpandingRank |
| 12 | direction | 12 | binary | Winsorize → ExpandingRank | ExpandingRank |
| 13 | trend_regime | 1 | binary | Winsorize → ExpandingRank | ExpandingRank |
| 14 | trend_regime | 3 | binary | Winsorize → ExpandingRank | ExpandingRank |
| 15 | trend_regime | 6 | binary | Winsorize → ExpandingRank | ExpandingRank |
| 16 | trend_regime | 12 | binary | Winsorize → ExpandingRank | ExpandingRank |
| 17 | vol_regime | 1 | multiclass | Winsorize → ExpandingRank | ExpandingRank |
| 18 | vol_regime | 3 | multiclass | Winsorize → ExpandingRank | ExpandingRank |
| 19 | vol_regime | 6 | multiclass | Winsorize → ExpandingRank | ExpandingRank |
| 20 | vol_regime | 12 | multiclass | Winsorize → ExpandingRank | ExpandingRank |

---

## 1.6 Implementation Requirements

### Preprocessors Needed (Phase 2)

| Preprocessor | Status | Notes |
|--------------|--------|-------|
| **ExpandingWinsorizer** | ✅ EXISTS (optimizers/) | May need adaptation |
| **RollingZScoreScaler** | ✅ EXISTS (optimizers/) | Already causal |
| **ExpandingZScoreScaler** | ❌ NEW | For volatility targets |
| **ExpandingRankTransformer** | ❌ NEW | For classification targets |
| **SignedLogTransformer** | ❌ NEW | Stateless, for volatility features |

### Pipeline Classes (Phase 3)

```python
# Base preprocessing pipelines (before helpers)
class ReturnsPipeline:      # For returns_* targets
class VolatilityPipeline:   # For volatility_* targets
class ClassificationPipeline:  # For direction_*, trend_regime_*, vol_regime_*

# Helper preprocessing pipelines (after helpers, before models)
class RegressionHelperPipeline:  # For returns/volatility targets
class ClassificationHelperPipeline:  # For direction/trend_regime/vol_regime targets
```

### Registry (Phase 3)

```python
PIPELINE_REGISTRY = {
    # Base pipelines by target name
    "returns": ReturnsPipeline,
    "volatility": VolatilityPipeline,
    "direction": ClassificationPipeline,
    "trend_regime": ClassificationPipeline,
    "vol_regime": ClassificationPipeline,
    
    # Helper pipelines by task type
    "regression_helper": RegressionHelperPipeline,
    "classification_helper": ClassificationHelperPipeline,
}

def get_pipeline_for_target(target: str, pipeline_type: str = "base"):
    """Factory function to create appropriate pipeline."""
    if pipeline_type == "base":
        return PIPELINE_REGISTRY[target]()
    elif pipeline_type == "helper":
        task_type = TARGET_SPECS[target].task_type
        if task_type == "regression":
            return RegressionHelperPipeline()
        else:
            return ClassificationHelperPipeline()
```

---

## Phase 1 Completion Status

- [x] 1.1 Define feature groups for selective preprocessing
- [x] 1.2 Design returns preprocessing pipeline
- [x] 1.3 Design volatility preprocessing pipeline
- [x] 1.4 Design classification preprocessing pipeline
- [x] 1.5 Create summary table of all 20 workflows
- [x] 1.6 Identify implementation requirements

**Status**: COMPLETE ✅

**Next**: Phase 2 — Implement causal preprocessors
