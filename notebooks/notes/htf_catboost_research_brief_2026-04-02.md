# HTF CatBoost Research Brief - 2026-04-02

## Scope

Primary-source guidance for improving the current HTF `1m / target_4class` walk-forward stack across `8h/24h/7d` and families `B/C`.

This brief uses only:

- official CatBoost documentation
- the CatBoost paper on arXiv
- primary academic sources from arXiv / SSRN
- Google Scholar / Semantic Scholar only as discovery indexes, not as evidence

## Primary Sources

### Official CatBoost

- Feature importances: https://catboost.ai/docs/en/features/feature-importances-calculation
- Feature importance details: https://catboost.ai/docs/en/concepts/fstr.html
- `select_features`: https://catboost.ai/docs/en/concepts/python-reference_catboost_select_features
- SHAP values: https://catboost.ai/docs/en/concepts/shap-values
- Object importance: https://catboost.ai/docs/en/features/object-importances-calcution
- Overfitting detector: https://catboost.ai/docs/en/features/overfitting-detector-desc
- Parameter tuning: https://catboost.ai/docs/en/concepts/parameter-tuning.html

### Primary Papers

- CatBoost paper: Prokhorenkova et al., *CatBoost: unbiased boosting with categorical features*, arXiv  
  https://arxiv.org/abs/1706.09516
- SHAP paper: Lundberg & Lee, *A Unified Approach to Interpreting Model Predictions*, arXiv  
  https://arxiv.org/abs/1706.06060
- Backtest-overfitting caution: Bailey et al., *The Probability of Backtest Overfitting*, SSRN  
  https://ssrn.com/abstract=2326253

## What CatBoost Officially Supports That Matters For Us

### 1. Feature importance modes are not interchangeable

CatBoost distinguishes between:

- `PredictionValuesChange`
  - default regular feature importance for non-ranking tasks
  - best for fast global ranking of features by average impact on predictions
- `LossFunctionChange`
  - dataset-dependent
  - more directly tied to validation loss impact
  - better when we care about whether a feature actually helps the objective on a particular evaluation set
- `ShapValues`
  - local per-object attribution
  - additive and consistent explanation framework
  - best for local reasoning, calibration/debug analysis, and stability checks across time
- `Interaction`
  - useful when we want to understand feature pairs, not just single-feature strength

For our workflow this means:

- use `PredictionValuesChange` for fast root-wide ranking and stability summaries
- use `LossFunctionChange` to verify whether globally strong features also matter on the actual loss surface
- use SHAP-based recursive selection inside Step-2 because CatBoost documents it as the most accurate recursive elimination mode

### 2. `select_features` already matches our intended Step-2 shape

CatBoost documents three recursive selection modes:

- `RecursiveByPredictionValuesChange`
  - fastest
  - least accurate
- `RecursiveByLossFunctionChange`
  - best speed/accuracy trade-off
- `RecursiveByShapValues`
  - most accurate

That validates the current design choice:

- recursive SHAP is the right default for Step-2 when we want trustworthy pruning candidates
- but we still need both `PredictionValuesChange` and `LossFunctionChange` summaries around it, because feature ranking and feature elimination answer different questions

### 3. Object importance is useful, but not for the current multiclass setup

CatBoost object importance is documented as an influence-style diagnostic for how training rows affect evaluation rows, but the official docs currently support it only for:

- `Logloss`
- `CrossEntropy`
- `RMSE`
- `MAE`
- `Quantile`
- related regression losses

Our current Stage-1 models are `MultiClass`, so object importance is **not a safe direct tool for the current six-root evaluation**.

Implication:

- **do not add object importance to the current multiclass root analysis**
- only revisit it if we later run one-vs-rest or binary directional refits with supported losses

### 4. Overfitting control should remain validation-driven

CatBoost’s docs recommend:

- large enough `iterations`
- validation-based best-model selection
- overfitting detection using `od_type`, `od_wait`, and optionally `od_pval`

Implication for our walk-forward setup:

- continue treating each step as a time-ordered train/validation/predict unit
- if we add parameter sweeps, keep validation-controlled stopping in every walk-forward step
- do not optimize solely on raw training fit or post-hoc prediction-batch outcomes

### 5. Parameter families worth studying first

CatBoost’s tuning docs highlight these as the main levers:

- `iterations` with validation-controlled stopping
- `learning_rate`
- `depth`
- `l2_leaf_reg`
- `random_strength`
- `bagging_temperature`
- `border_count`

For our current tree-based walk-forward stack, the first practical sweep order should be:

1. `depth`
2. `learning_rate`
3. `l2_leaf_reg`
4. `random_strength`
5. `bootstrap_type` / `bagging_temperature`
6. `rsm`

This matches the planned Phase D ordering and is consistent with official CatBoost guidance.

## What The Primary Papers Add

### CatBoost paper

The CatBoost paper is directly relevant for us because it motivates:

- ordered / unbiased treatment of information in boosting
- reduction of target leakage / prediction shift from naive categorical handling and boosting procedures

We are not using categorical-heavy finance features in the usual sense, but the broader lesson still applies:

- walk-forward integrity matters
- validation and prediction windows must remain causally ordered
- convenience shortcuts that mix future information into selection or ensembling are unacceptable

### SHAP paper

The SHAP paper supports using local additive explanations when we need:

- per-step or per-window attribution
- feature stability checks across batches
- explanations for why a root wins or degrades in certain windows

Implication:

- SHAP is strongest as a **diagnostic layer**
- not as the only feature-ranking signal
- and not as permission to trust unstable features without null/drift checks

### Backtest-overfitting paper

The PBO / backtest-overfitting line of work is a direct warning for our workflow:

- repeated selection among many candidate combos or ensembles can create false confidence
- even strong directional-accuracy lifts can be selection artifacts if not controlled causally

Implication:

- keep excluding hindsight winner-selection methods from the causal leaderboard
- keep documenting incomplete-combo batch filters explicitly
- treat reduced-coverage methods carefully: high directional accuracy alone is not enough

## Recommended Diagnostic Stack For Our Workflow

### Safe to use now

- `PredictionValuesChange`
  - fast global ranking
  - good for cross-root feature comparisons
- `LossFunctionChange`
  - better proxy for actual objective sensitivity on the evaluation dataset
- recursive SHAP feature selection in Step-2
  - suitable for pruning analysis
- calibration buckets, entropy, margin, confusion matrices
  - all directly relevant for multiclass walk-forward evaluation
- chronological walk-forward validation and causal ensemble comparison

### Needs causal validation

- abstention / agreement methods that improve directional accuracy by reducing coverage
- any meta-model or router that learns across step outputs
- per-root parameter sweeps that change validation or stopping behavior
- feature-drop decisions based only on a single importance mode

### Do not use as improvement signal

- hindsight winner-combo methods
- post-hoc subset methods defined on future knowledge of “good” steps
- object importance on the current `MultiClass` setup
- raw directional lift without coverage, calibration, and causal-batch integrity context

## Decision Table

| Tool / Signal | Status | Why |
| --- | --- | --- |
| `PredictionValuesChange` | safe to use now | official CatBoost feature importance for non-ranking models; efficient global ranking |
| `LossFunctionChange` | safe to use now | dataset-aware loss sensitivity; better for checking whether important features actually move the objective |
| recursive SHAP `select_features` | safe to use now | official CatBoost says SHAP-based RFE is the most accurate selection mode |
| SHAP local explanations | needs causal validation | very useful for window-level diagnosis, but should not be the only basis for pruning decisions |
| object importance | do not use as improvement signal | official support excludes current `MultiClass` setup |
| reduced-coverage agreement filters | needs causal validation | can improve directional accuracy by abstention, but coverage and stability must be evaluated jointly |
| hindsight winner-combo methods | do not use as improvement signal | violate live deployability and invite backtest-overfitting |

## Immediate Implications For The Current HTF Plan

1. Phase B and C should collect **both** `PredictionValuesChange` and `LossFunctionChange`.
2. Step-2 should keep recursive SHAP selection as the pruning engine.
3. Feature-quality ranking must join importance with:
   - null rate
   - drift
   - policy-block flags
4. Model evaluation should continue to report:
   - directional accuracy
   - coverage
   - logloss
   - Brier score
   - calibration
   - worst windows
5. Phase D should begin with:
   - `7d/C`
   - `8h/C`
   - `24h/C`
   - then `B` comparators

## Research Follow-Ups

- arXiv / SSRN search should focus on:
  - tree-ensemble attribution stability
  - calibration of multiclass probability models
  - walk-forward / purged time-series validation
  - backtest-overfitting controls for model-selection workflows
- Google Scholar and Semantic Scholar remain useful **indexes** for finding those papers, but not as evidence by themselves.
