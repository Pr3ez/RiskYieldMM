# Master TODO: 20 Target-Horizon Optimized Preprocessing Workflows

## Overview

**Goal**: Create 20 optimized preprocessing pipelines (5 targets × 4 horizons) that:
1. Provide best possible input for Layer 2 ensemble models
2. Support 1-window-forward sliding prediction
3. Enable Layer 3 to combine 20 predictions into final output
4. Have ZERO future information leakage

---

## PHASE 0: AUDIT CURRENT STATE [CRITICAL]

### 0.1 Audit Current Helper Features (58 features)
- [ ] **0.1.1** List all 58 helper features from ensemble output
- [ ] **0.1.2** Check each feature for potential leakage:
  - Does it use global statistics?
  - Does it look ahead in any way?
  - What data does `fit()` vs `transform()` use?
- [ ] **0.1.3** Document feature distributions per task type
- [ ] **0.1.4** Identify features that need different preprocessing per target

### 0.2 Audit Current Base Features (166 features)
- [ ] **0.2.1** List all 166 base features from dataset
- [ ] **0.2.2** Classify by type:
  - Price-derived (returns, ratios)
  - Volume-derived
  - Volatility-derived
  - Sentiment (L/S ratio, funding)
  - Technical indicators
- [ ] **0.2.3** Check existing preprocessing in compute_features.py:
  - What rolling windows are used?
  - Any global normalization happening?
- [ ] **0.2.4** Document which features are already scale-invariant

### 0.3 Audit Current Optimizers (scripts/analysis/optimizers/)
- [ ] **0.3.1** Review WinsorizeOptimizer — is it truly causal?
- [ ] **0.3.2** Review RollingZScoreOptimizer — correct window usage?
- [ ] **0.3.3** Review InteractionOptimizer — any leakage in IC computation?
- [ ] **0.3.4** Review RegimeConditioningOptimizer — safe thresholds?
- [ ] **0.3.5** Document what's usable vs what needs fixing

### 0.4 Audit AlignedDualEngine Flow
- [ ] **0.4.1** Trace data flow from aligned data → L1 → L2 → prediction
- [ ] **0.4.2** Identify WHERE preprocessing should happen:
  - Before L1 helpers? (on base features)
  - After L1 helpers? (on helper features)
  - Both?
- [ ] **0.4.3** Document current transform pipeline order
- [ ] **0.4.4** Identify missing preprocessing steps

---

## PHASE 1: DESIGN TASK-SPECIFIC PREPROCESSING

### 1.1 Define Feature Groups
- [ ] **1.1.1** Create feature groups for selective preprocessing:
  ```
  PRICE_FEATURES: returns, log_returns, price_ratios
  VOLUME_FEATURES: volume, OI, turnover
  VOLATILITY_FEATURES: ATR, realized_vol, vol_ratios
  BOUNDED_FEATURES: RSI, stochastic, percentiles (already [0,1])
  UNBOUNDED_FEATURES: z-scores, momentum, acceleration
  HELPER_FEATURES: HMM states, IF scores, GARCH, Kalman
  ```
- [ ] **1.1.2** Map feature groups → valid transformations

### 1.2 Design Returns Preprocessing (4 horizons)
- [ ] **1.2.1** Document target: `y_returns = up_move - down_move` (net candle return)
  - `up_move = (future_high - close) / close`
  - `down_move = (close - future_low) / close`
  - Captures intracandle volatility, not just close-to-close
- [ ] **1.2.2** Define pipeline:
  ```
  BASE → ExpandingWinsorize(1%, 99%)
       → RollingZScore(63) for unbounded features only
       → Keep bounded features as-is
  HELPER → ExpandingWinsorize(1%, 99%) only
  ```
- [ ] **1.2.3** Justify: Returns are symmetric, regime-adaptive scaling helps
- [ ] **1.2.4** Test on returns_1bar, returns_6bar

### 1.3 Design Volatility Preprocessing (4 horizons)
- [ ] **1.3.1** Document target: `y_volatility = |returns|`
- [ ] **1.3.2** Define pipeline:
  ```
  BASE → ExpandingWinsorize(1%, 99%)
       → Log transform for volatility features
       → ExpandingZScore (NOT rolling — preserve magnitude)
  HELPER → ExpandingWinsorize(1%, 99%) only
  ```
- [ ] **1.3.3** Justify: Volatility is right-skewed, log normalizes
- [ ] **1.3.4** Test on volatility_1bar, volatility_6bar

### 1.4 Design Direction Preprocessing (4 horizons)
- [ ] **1.4.1** Document target: `y_direction = 1 if (up_move - down_move) > 0 else 0`
  - Uses net candle return: `up_move - down_move`
  - 1 if price moved more up than down within the horizon candle
- [ ] **1.4.2** Define pipeline:
  ```
  BASE → ExpandingWinsorize(1%, 99%)
       → ExpandingRank → [0, 1] for all unbounded
  HELPER → ExpandingRank → [0, 1]
  ```
- [ ] **1.4.3** Justify: Classification needs monotonic transform, not scaling
- [ ] **1.4.4** Test on direction_1bar, direction_6bar

### 1.5 Design Trend Regime Preprocessing (4 horizons)
- [ ] **1.5.1** Document target: `y_trend_regime = trend_state`
- [ ] **1.5.2** Define pipeline: Same as Direction
- [ ] **1.5.3** Justify: Binary classification, same needs
- [ ] **1.5.4** Test on trend_regime_1bar, trend_regime_6bar

### 1.6 Design Vol Regime Preprocessing (4 horizons)
- [ ] **1.6.1** Document target: `y_vol_regime = LOW/MED/HIGH (0/1/2)`
- [ ] **1.6.2** Define pipeline:
  ```
  BASE → ExpandingWinsorize(1%, 99%)
       → ExpandingRank → [0, 1]
  HELPER → ExpandingRank → [0, 1]
  ```
- [ ] **1.6.3** Justify: Multiclass needs uniform distribution
- [ ] **1.6.4** Test on vol_regime_1bar, vol_regime_6bar

---

## PHASE 2: IMPLEMENT CAUSAL PREPROCESSORS

### 2.1 Implement ExpandingWinsorizer
- [ ] **2.1.1** Create class with incremental quantile tracking (t-digest)
- [ ] **2.1.2** Implement `fit(X)` — initialize t-digest per feature
- [ ] **2.1.3** Implement `partial_fit(X)` — update t-digest with new data
- [ ] **2.1.4** Implement `transform(X)` — clip using stored quantiles
- [ ] **2.1.5** Add min_samples parameter (default 252)
- [ ] **2.1.6** Unit tests: verify no future data used

### 2.2 Implement ExpandingZScoreScaler
- [ ] **2.2.1** Create class with Welford's online algorithm
- [ ] **2.2.2** Implement `fit(X)` — initialize running stats per feature
- [ ] **2.2.3** Implement `partial_fit(X)` — update running mean/var
- [ ] **2.2.4** Implement `transform(X)` — standardize using stored stats
- [ ] **2.2.5** Handle edge cases: constant features, division by zero
- [ ] **2.2.6** Unit tests: verify matches sklearn on full data

### 2.3 Implement ExpandingRankTransformer
- [ ] **2.3.1** Create class with histogram-based CDF estimate
- [ ] **2.3.2** Implement `fit(X)` — initialize histogram bins per feature
- [ ] **2.3.3** Implement `partial_fit(X)` — update bin counts
- [ ] **2.3.4** Implement `transform(X)` — map to [0, 1] percentile
- [ ] **2.3.5** Handle edge cases: values outside observed range
- [ ] **2.3.6** Unit tests: verify monotonic output

### 2.4 Implement RollingZScoreScaler
- [ ] **2.4.1** Create class (simpler — uses pandas rolling)
- [ ] **2.4.2** Implement `transform(X, window=63)` — rolling normalization
- [ ] **2.4.3** Handle warmup period (first `window` rows)
- [ ] **2.4.4** No `fit()` needed — stateless transformation
- [ ] **2.4.5** Unit tests: verify window boundaries

### 2.5 Implement LogTransformer
- [ ] **2.5.1** Create class for signed log: `sign(x) * log(1 + |x|)`
- [ ] **2.5.2** Stateless — no fit needed
- [ ] **2.5.3** Handle zeros and negatives gracefully
- [ ] **2.5.4** Unit tests: verify invertibility

---

## PHASE 3: CREATE PREPROCESSING PIPELINES

### 3.1 Create PreprocessorPipeline Class
- [ ] **3.1.1** Design pipeline that chains preprocessors
- [ ] **3.1.2** Implement `fit(X)` — fit all stages in order
- [ ] **3.1.3** Implement `partial_fit(X)` — update all stages
- [ ] **3.1.4** Implement `transform(X)` — apply all stages in order
- [ ] **3.1.5** Implement feature name tracking through pipeline

### 3.2 Create PreprocessorRegistry
- [ ] **3.2.1** Define registry similar to helper_selection.py:
  ```python
  PREPROCESSOR_PIPELINES = {
      ('returns', 'regression'): [ExpandingWinsorizer, RollingZScoreScaler],
      ('volatility', 'regression'): [ExpandingWinsorizer, LogTransformer, ExpandingZScoreScaler],
      ('direction', 'binary'): [ExpandingWinsorizer, ExpandingRankTransformer],
      ('trend_regime', 'binary'): [ExpandingWinsorizer, ExpandingRankTransformer],
      ('vol_regime', 'multiclass'): [ExpandingWinsorizer, ExpandingRankTransformer],
  }
  ```
- [ ] **3.2.2** Implement `get_pipeline_for_target(target, task_type)`
- [ ] **3.2.3** Implement `create_pipeline(target, horizon)` factory

### 3.3 Create Per-Target Configuration
- [ ] **3.3.1** Create config dataclass:
  ```python
  @dataclass
  class PreprocessConfig:
      target: str
      horizon: int
      task_type: str
      base_pipeline: list[str]
      helper_pipeline: list[str]
      feature_groups: dict[str, list[str]]
  ```
- [ ] **3.3.2** Create all 20 configurations
- [ ] **3.3.3** Store in YAML or Python dict for maintainability

---

## PHASE 4: INTEGRATE INTO ALIGNED DUAL ENGINE

### 4.1 Modify AlignedDualWindow
- [ ] **4.1.1** Add preprocessing hook points:
  ```
  L1 EXPANDING WINDOW:
    raw_X → [base_preprocessor.partial_fit] → preprocessed_X
    helpers.fit(preprocessed_X)
    
  L2 SLIDING WINDOW:
    raw_X → [base_preprocessor.transform] → preprocessed_X
    helper_features = helpers.transform(preprocessed_X)
    helper_features → [helper_preprocessor.transform] → final_X
  ```
- [ ] **4.1.2** Ensure preprocessor state persists across iterations
- [ ] **4.1.3** Handle the transition from L1 to L2 correctly

### 4.2 Create TargetWorkflow Class
- [ ] **4.2.1** Design workflow that encapsulates everything for one target:
  ```python
  class TargetWorkflow:
      def __init__(self, target: str, horizon: int):
          self.spec = get_target_spec(target, horizon)
          self.base_preprocessor = create_pipeline(target, horizon, 'base')
          self.helper_preprocessor = create_pipeline(target, horizon, 'helper')
          self.helpers = HelperEnsemble(target, horizon)
          self.model = create_layer2_model(self.spec.task_type)
  ```
- [ ] **4.2.2** Implement `fit(window)` — fit L1 components
- [ ] **4.2.3** Implement `transform(window)` — generate L2 features
- [ ] **4.2.4** Implement `predict(window)` — make prediction

### 4.3 Create WorkflowOrchestrator
- [ ] **4.3.1** Orchestrate all 20 workflows in parallel:
  ```python
  class WorkflowOrchestrator:
      def __init__(self):
          self.workflows = {
              (target, horizon): TargetWorkflow(target, horizon)
              for target, horizon in iterate_all_targets()
          }
      
      def predict_all(self, aligned_window) -> dict:
          """Return 20 predictions for same timestamp."""
          return {
              key: workflow.predict(aligned_window)
              for key, workflow in self.workflows.items()
          }
  ```
- [ ] **4.3.2** Implement checkpoint/resume for long runs
- [ ] **4.3.3** Add progress tracking and logging

---

## PHASE 5: VALIDATE NO LEAKAGE

### 5.1 Permutation Test
- [ ] **5.1.1** For each of 20 workflows:
  - Fit preprocessor on X
  - Transform X
  - Compute IC with real y vs 100 shuffled y
  - z-score > 2 confirms real signal
- [ ] **5.1.2** Document results in validation report

### 5.2 Time-Shift Test
- [ ] **5.2.1** For each of 20 workflows:
  - Shift y by [-12, -6, -3, 0, +3, +6, +12]
  - IC should be highest at 0, decrease for positive shifts
- [ ] **5.2.2** Document results — any anomalies indicate leakage

### 5.3 Expanding vs Fixed Window Test
- [ ] **5.3.1** Compare:
  - A: Preprocessor fit on L1 only (correct)
  - B: Preprocessor fit on all data (wrong)
- [ ] **5.3.2** If IC(B) >> IC(A), there's leakage being prevented
- [ ] **5.3.3** Document the difference

### 5.4 Walk-Forward OOS Test
- [ ] **5.4.1** Run 100 iterations of walk-forward
- [ ] **5.4.2** Compare in-sample IC vs out-of-sample IC
- [ ] **5.4.3** Gap > 30% suggests overfitting
- [ ] **5.4.4** Document per-target-horizon results

---

## PHASE 6: OPTIMIZE FOR LAYER 2

### 6.1 Feature Selection Per Target
- [ ] **6.1.1** For each of 20 workflows:
  - Compute feature IC on L1 cal window
  - Select features with |IC| > threshold
  - Document selected features
- [ ] **6.1.2** Create feature selection config per target

### 6.2 Tune Preprocessing Hyperparameters
- [ ] **6.2.1** Winsorize percentiles: test 1/99, 2/98, 5/95
- [ ] **6.2.2** Rolling window size: test 21, 42, 63, 126
- [ ] **6.2.3** Expanding minimum samples: test 126, 252, 504
- [ ] **6.2.4** Select best per target based on L1 val IC

### 6.3 Validate Layer 2 Model Performance
- [ ] **6.3.1** For each of 20 workflows:
  - Train L2 model (CatBoost/LightGBM/Ridge)
  - Evaluate on L2 val window
  - Document metrics (IC, RMSE, AUC depending on task)
- [ ] **6.3.2** Compare: with preprocessing vs without
- [ ] **6.3.3** Document improvement per target-horizon

---

## PHASE 7: PREPARE FOR LAYER 3

### 7.1 Document Layer 2 Output Format
- [ ] **7.1.1** Define standard output per target:
  ```python
  @dataclass
  class Layer2Output:
      target: str
      horizon: int
      prediction: float  # or array for classification probs
      confidence: float
      timestamp: pd.Timestamp
      model_used: str
  ```
- [ ] **7.1.2** Ensure all 20 workflows return same format

### 7.2 Create Layer 2 → Layer 3 Interface
- [ ] **7.2.1** Design aggregation function:
  ```python
  def aggregate_predictions(outputs: list[Layer2Output]) -> Layer3Input:
      """Combine 20 predictions into format Layer 3 expects."""
  ```
- [ ] **7.2.2** Include all information Layer 3 needs:
  - Direction predictions (4 horizons)
  - Returns predictions (4 horizons)
  - Volatility predictions (4 horizons)
  - Regime predictions (8 horizons: vol + trend)
- [ ] **7.2.3** Document the contract between layers

### 7.3 Validation: Full Pipeline Test
- [ ] **7.3.1** Run full pipeline:
  - Raw data → Preprocessing → L1 → L2 → 20 predictions
- [ ] **7.3.2** Verify all 20 predictions are for SAME timestamp
- [ ] **7.3.3** Verify no NaN/Inf in outputs
- [ ] **7.3.4** Document end-to-end latency

---

## PHASE 8: DOCUMENTATION & CLEANUP

### 8.1 Code Documentation
- [ ] **8.1.1** Docstrings for all new classes
- [ ] **8.1.2** Type hints throughout
- [ ] **8.1.3** Example usage in module docstrings

### 8.2 Architecture Documentation
- [ ] **8.2.1** Update session.md with new architecture
- [ ] **8.2.2** Create docs/preprocessing/README.md
- [ ] **8.2.3** Add diagrams showing data flow

### 8.3 Test Suite
- [ ] **8.3.1** Unit tests for each preprocessor
- [ ] **8.3.2** Integration tests for pipelines
- [ ] **8.3.3** Leakage tests as regression suite

---

## SUMMARY: 20 Workflows

| # | Target | Horizon | Task | Base Pipeline | Helper Pipeline |
|---|--------|---------|------|---------------|-----------------|
| 1 | returns | 1 | regression | Winsorize→RollingZScore | Winsorize |
| 2 | returns | 3 | regression | Winsorize→RollingZScore | Winsorize |
| 3 | returns | 6 | regression | Winsorize→RollingZScore | Winsorize |
| 4 | returns | 12 | regression | Winsorize→RollingZScore | Winsorize |
| 5 | volatility | 1 | regression | Winsorize→Log→ExpandingZScore | Winsorize |
| 6 | volatility | 3 | regression | Winsorize→Log→ExpandingZScore | Winsorize |
| 7 | volatility | 6 | regression | Winsorize→Log→ExpandingZScore | Winsorize |
| 8 | volatility | 12 | regression | Winsorize→Log→ExpandingZScore | Winsorize |
| 9 | direction | 1 | binary | Winsorize→ExpandingRank | ExpandingRank |
| 10 | direction | 3 | binary | Winsorize→ExpandingRank | ExpandingRank |
| 11 | direction | 6 | binary | Winsorize→ExpandingRank | ExpandingRank |
| 12 | direction | 12 | binary | Winsorize→ExpandingRank | ExpandingRank |
| 13 | trend_regime | 1 | binary | Winsorize→ExpandingRank | ExpandingRank |
| 14 | trend_regime | 3 | binary | Winsorize→ExpandingRank | ExpandingRank |
| 15 | trend_regime | 6 | binary | Winsorize→ExpandingRank | ExpandingRank |
| 16 | trend_regime | 12 | binary | Winsorize→ExpandingRank | ExpandingRank |
| 17 | vol_regime | 1 | multiclass | Winsorize→ExpandingRank | ExpandingRank |
| 18 | vol_regime | 3 | multiclass | Winsorize→ExpandingRank | ExpandingRank |
| 19 | vol_regime | 6 | multiclass | Winsorize→ExpandingRank | ExpandingRank |
| 20 | vol_regime | 12 | multiclass | Winsorize→ExpandingRank | ExpandingRank |

---

## EXECUTION ORDER

```
PHASE 0 (Audit) ───────────► PHASE 1 (Design) ───────────► PHASE 2 (Implement)
    │                              │                              │
    └── 0.1-0.4 (1-2 days)        └── 1.1-1.6 (1 day)           └── 2.1-2.5 (2-3 days)
                                                                       │
                                                                       ▼
PHASE 3 (Pipelines) ◄────── PHASE 4 (Integrate) ◄────── PHASE 5 (Validate)
    │                              │                              │
    └── 3.1-3.3 (1 day)           └── 4.1-4.3 (2 days)          └── 5.1-5.4 (1-2 days)
                                                                       │
                                                                       ▼
PHASE 6 (Optimize) ───────► PHASE 7 (Layer 3 Prep) ───► PHASE 8 (Docs)
    │                              │                              │
    └── 6.1-6.3 (2 days)          └── 7.1-7.3 (1 day)           └── 8.1-8.3 (1 day)
```

**Estimated Total: 12-15 days**

---

## CURRENT STATUS

- [x] PHASE 0.0: Research completed (PREPROCESSING_RESEARCH.md)
- [ ] PHASE 0.1: Audit helper features — **START HERE**
- [ ] All other phases pending

---

## NOTES

- Each phase should be completed and validated before moving to next
- Checkpoints after each phase for review
- All code must have unit tests before integration
- Document decisions in ADR format
