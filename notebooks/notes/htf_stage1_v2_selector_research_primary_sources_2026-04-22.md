# HTF Stage-1-v2 Selector Research From Primary Sources

Date: 2026-04-22
Scope: trusted-source literature review for what can realistically improve Stage-1-v2 combo selection above the existing CatBoost combo outputs.

## 1. Current problem in repo terms

We already have a base layer:

- each `action_key` combo trains its own CatBoost model
- Stage-1-v2 produces per-step artifacts for every combo
- fixed-policy replay now lets us evaluate all combos on the same prediction steps

The open question is not "how do we replace CatBoost?"

The open question is:

- how do we choose among the existing combo forecasts at each step
- how do we do it in strict walkforward form
- how do we do it using only information available at prediction time
- how do we optimize for the metric we actually care about, especially filtered cross-directional error (CDE), directional accuracy, and class accuracy

This matters because our own audit on `8h/B` already showed:

- pairwise agreement/conflict structure is descriptively interesting
- but it is not stable enough to be the main winner-selection signal

Reference local artifacts:

- [meta-feature viability note](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/notes/htf_stage1_v2_meta_feature_viability_2026-04-21.md)
- [full-500 viability note](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/notes/htf_stage1_v2_full500_meta_feature_viability_2026-04-21.md)
- [subset reduction note](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/notes/htf_stage1_v2_subset_reduction_audit_2026-04-21.md)

So the research target is narrower:

- metric-aligned dynamic selector
- online expert weighting
- competence estimation above base combo outputs
- uncertainty gating for low-confidence steps

## 2. Primary-source papers with real applicability

### A. Dynamic model averaging / dynamic model selection

#### 1. Raftery, Karny, Ettler (2010)
Source:
- https://sites.stat.washington.edu/raftery/Research/PDF/Karny2010.pdf

Why it matters:

- foundational DMA paper
- explicit setting: online prediction when the best model can change over time
- uses forgetting for both parameter drift and model drift
- computationally lightweight compared with full state switching

What maps to our case:

- each combo can be treated as a candidate model
- combo weights can change over time
- forgetting factor naturally fits walkforward and regime drift

Direct takeaway:

- the "best" combo should be allowed to vary through time
- weights should be driven by recent predictive performance, not global averages

Fit to our stack:

- very high
- especially good as a baseline selector above current combo predictions

#### 2. McCormick, Raftery, Madigan, Burd (2012)
Source:
- https://academic.oup.com/biometrics/article/68/1/23/7390679

Paper:
- Dynamic Logistic Regression and Dynamic Model Averaging for Binary Classification

Why it matters:

- DMA extended to classification
- explicit online adaptation
- adaptive forgetting tuned via predictive likelihood

What maps to our case:

- we are not doing continuous forecasting here, but discrete class prediction
- this paper is much closer to our actual problem than generic forecasting DMA

Limit:

- binary rather than 4-class

Direct takeaway:

- classification-aware DMA is viable
- adaptive forgetting is more defensible than fixed global memory windows

Fit to our stack:

- very high conceptually
- would need multi-class generalization or one-vs-rest style adaptation

#### 3. Beckmann, Koop, Korobilis, Schuessler (working paper 2017, later JAE line)
Source:
- https://repository.essex.ac.uk/20781/1/26_BKKS_c.pdf

Paper:
- Exchange Rate Predictability and Dynamic Bayesian Learning

Why it matters:

- finance-specific
- directly about unstable predictive relationships
- finds fast model switching and that only a small subset of predictors is relevant at a time

What maps to our case:

- exactly the environment we are in: predictive relationships are unstable
- supports the idea that combo usefulness should be dynamic, not static

Direct takeaway:

- we should expect fast shifts in which combo is most useful
- any selector that assumes a fixed globally best combo is misspecified

Fit to our stack:

- high
- especially relevant for regime/family-specific online selection

#### 4. Bernaciak, Griffin (2024)
Source:
- https://www.sciencedirect.com/science/article/pii/S0169207024000268
- arXiv preprint: https://arxiv.org/abs/2201.12045

Paper:
- A loss discounting framework for model averaging and selection in time series models

Why it matters:

- this is the strongest methodological fit to our current question
- it generalizes DMA and dynamic model learning
- weights are updated using a user-chosen loss, not only likelihood
- designed to handle regime changes
- explicitly presented as computationally efficient

What maps to our case:

- we care about filtered CDE, not generic likelihood
- this framework says the selector can and should be driven by the loss we actually want to minimize
- we could define a combo-level step loss such as:
  - filtered CDE
  - weighted blend of filtered CDE and directional error
  - Brier/log-loss on the 4-class probabilities

Direct takeaway:

- this is the cleanest research-backed route for a first serious selector baseline
- it matches our need better than pairwise disagreement heuristics

Fit to our stack:

- highest fit

### B. Discrete-outcome weighting aligned to classification quality

#### 5. Guerin, Leiva-Leon (2017)
Source:
- https://www.sciencedirect.com/science/article/abs/pii/S0165176517302057

Paper:
- Model averaging in Markov-switching models: Predicting national recessions with regional data

Why it matters:

- very important for us conceptually
- they explicitly argue that when the target is discrete, likelihood-based weights may be the wrong scoring rule
- they build weights from past ability to classify discrete outcomes, using quadratic probability score logic

What maps to our case:

- our target is 4-class
- we care about discrete correctness and direction-specific mistakes
- this supports weighting combos using classification-aligned losses, not regression-style fit

Direct takeaway:

- if we build dynamic weights, they should likely use Brier/QPS/log-loss style scoring or directly filtered CDE
- not generic predictive likelihood alone

Fit to our stack:

- very high
- especially if we want a selector optimized for class behavior or directional behavior

### C. Online expert aggregation under drift

#### 6. Kolter, Maloof (2007)
Source:
- https://www.jmlr.org/papers/v8/kolter07a.html

Paper:
- Dynamic Weighted Majority: An Ensemble Method for Drifting Concepts

Why it matters:

- classic drift-handling expert ensemble
- experts are reweighted by recent performance
- poor experts are downweighted/removed and new ones can be added

What maps to our case:

- our combos are effectively experts
- we may not need expert creation/removal initially, but the weight update logic is directly relevant

Direct takeaway:

- a simple online weighted-expert baseline is mandatory before training heavier meta-models

Fit to our stack:

- high as a baseline
- less elegant than loss-discounting for our exact metric, but simpler

#### 7. Soares, Araujo (2015)
Source:
- https://www.sciencedirect.com/science/article/pii/S0952197614002437

Paper:
- An on-line weighted ensemble of regressor models to handle concept drifts

Why it matters:

- online weights updated sample by sample
- explicitly uses discounting of old versus recent performance
- designed for abrupt, gradual, local, global, recurring drifts

What maps to our case:

- even though it is framed for regression, the core idea is directly reusable:
  recent-error-weighted experts with discounting

Direct takeaway:

- recency-weighted combo performance should be treated as a first-class signal

Fit to our stack:

- medium-high
- more useful as a design pattern than as an exact recipe

#### 8. Devaine et al. (2012)
Source:
- https://arxiv.org/abs/1207.1965

Paper:
- Forecasting electricity consumption by aggregating specialized experts

Why it matters:

- specialized experts are not assumed to be equally useful everywhere
- fixed-share / specialist aggregation is robust when expert usefulness changes over time

What maps to our case:

- some combos may only be locally strong in specific market states
- a specialist-style aggregation rule may fit better than one global weighting rule

Direct takeaway:

- later, we can allow combo activation masks or regime-conditioned weights
- but this should come after simpler dynamic weighting baselines

Fit to our stack:

- medium-high

### D. Meta-learning / competence estimation

#### 9. Cruz et al. (2018)
Source:
- https://arxiv.org/abs/1810.01270

Paper:
- META-DES: A Dynamic Ensemble Selection Framework using Meta-Learning

Why it matters:

- this is the main research family behind "estimate which base model is competent for this specific query"
- competence is predicted from meta-features derived from classifier behavior

What maps to our case:

- exactly the idea of a second-layer selector above combo CatBoost outputs
- meta-features could include:
  - lagged combo accuracy/CDE
  - probability margins
  - entropy
  - agreement with peers
  - confidence concentration by class

Important caution from our own repo evidence:

- pairwise agreement/conflict alone did not prove stable enough on the 500-step audit
- so if we use META-DES-style logic, peer features should be secondary, not primary

Fit to our stack:

- high, but only after strong simple baselines exist

#### 10. Cruz et al. (2018 / IJCNN line)
Source:
- https://arxiv.org/abs/1811.01742

Paper:
- META-DES.H: a dynamic ensemble selection technique using meta-learning and a dynamic weighting approach

Why it matters:

- goes beyond hard selection
- combines competence estimation with weighting

What maps to our case:

- instead of choosing a single combo, we could produce weighted combo probabilities at each step
- that might reduce instability compared with hard winner-take-all selection

Direct takeaway:

- a soft selector may be better than a hard selector if winner identity is noisy

Fit to our stack:

- high as a later-stage extension

### E. Meta-learning over ensemble strategies

#### 11. Gastinger et al. (2021)
Source:
- https://arxiv.org/abs/2104.11475

Paper:
- A study on Ensemble Learning for Time Series Forecasting and the need for Meta-Learning

Why it matters:

- large empirical study
- ensembles help, but no single ensemble strategy wins universally
- motivates a meta-learning step to choose the ensemble strategy

What maps to our case:

- supports the idea that even the selector architecture itself may need to be chosen per regime/root/family

Direct takeaway:

- do not assume one selector rule will dominate across all roots

Fit to our stack:

- medium-high
- more strategic than directly implementable

#### 12. Bosch et al. (2025)
Source:
- https://arxiv.org/abs/2511.15350

Paper:
- Multi-layer Stack Ensembles for Time Series Forecasting

Why it matters:

- recent evidence that learned stacking can outperform simple combinations in time series

What maps to our case:

- a stacked selector that learns from combo outputs plus lagged reliability is plausible

Important caveat:

- our setting is small in effective sample size per root
- easy to overfit if we jump straight to a richer stacker

Fit to our stack:

- medium
- promising later, not first

### F. Uncertainty calibration / abstention overlay

#### 13. Zaffran et al. (2022)
Source:
- https://proceedings.mlr.press/v162/zaffran22a.html

Paper:
- Adaptive Conformal Predictions for Time Series

Why it matters:

- focuses on uncertainty under dependency and shift
- uses online expert aggregation to adapt interval behavior over time

What maps to our case:

- not the main selector
- but useful for a confidence/risk overlay:
  - when all combos are uncertain
  - when selector confidence is weak
  - when we may want to abstain, downweight, or flag unstable steps

Fit to our stack:

- medium as a risk-control layer
- low as a direct combo selector

## 3. What has the strongest potential for our exact case

### Highest-priority ideas

#### 1. Loss-discounted dynamic combo selection

Best paper support:

- Bernaciak, Griffin (2024)
- Raftery et al. (2010)
- Guerin, Leiva-Leon (2017)

Why this is first:

- aligns weights with the exact target loss
- online, walkforward-safe
- computationally cheap
- no need to train a large second model initially

What it would look like here:

- for each combo `k` at step `t`, maintain discounted cumulative loss
- choose loss as one of:
  - filtered CDE
  - directional error
  - class log-loss
  - weighted composite
- convert discounted losses into weights or rank scores
- pick min expected loss combo or weighted blend

Why this is better than the current pairwise idea:

- uses the exact objective
- avoids unstable pairwise edge estimation
- needs only past realized combo performance

#### 2. Classification-aware dynamic weighting

Best paper support:

- Guerin, Leiva-Leon (2017)
- McCormick et al. (2012)

Why it matters:

- our target is discrete
- weights should come from discrete predictive quality

What it would look like here:

- combo update loss based on:
  - multi-class Brier / QPS
  - class log-loss
  - directional Brier
  - filtered CDE surrogate

#### 3. Lightweight competence meta-model above combo outputs

Best paper support:

- META-DES
- META-DES.H

Why this is not first:

- higher overfitting risk
- our own 500-step evidence says peer disagreement is weak as a primary signal

What it would look like here:

- one row per `(pred_batch, action_key)`
- target:
  - future filtered CDE
  - or future directional correctness
  - or future filtered rank
- features available at prediction time:
  - lagged EWMA filtered CDE
  - lagged EWMA directional accuracy
  - lagged class accuracy
  - lagged rank / regret
  - current probability margin
  - current entropy
  - current class concentration
  - limited peer-context features

This can make sense, but only after the simple dynamic-weight baselines are beaten.

## 4. What probably does not deserve priority

### Pairwise support/conflict as the main selector

Why not:

- our own 500-step audit already weakened the case substantially
- direction-mode and class-mode pair edges were not stable enough out of sample

Practical conclusion:

- keep pairwise relations as descriptive diagnostics
- do not make them the primary selection engine

### Heavy stacking before strong baselines

Why not:

- effective sample size per root is still limited
- higher model complexity does not solve weak signal
- risk of building a nice-looking selector that does not beat discounted loss rules

## 5. Recommended experiment order

### Stage A. Required baselines

Implement these first:

1. Static global best combo baseline
2. EWMA directional-accuracy selector
3. EWMA filtered-CDE selector
4. Loss-discounted selector with exact metric-aligned loss

Why:

- if a learned selector cannot beat these, it is not worth the extra complexity

### Stage B. Classification-aware variants

Add:

1. Brier/QPS-weighted selector
2. Log-loss-weighted selector
3. composite-loss selector

Goal:

- test whether the best selection signal comes from class calibration, direction quality, or exact CDE alignment

### Stage C. Lightweight meta-selector

Only after Stage A/B:

1. train a small second-layer model on candidate-step rows
2. predict expected combo loss at current step
3. compare against Stage A/B baselines

Use:

- lagged reliability features
- current prediction-shape features
- maybe a very small number of peer-context features

### Stage D. Soft combination / abstention

Later extensions:

1. weighted combo blending instead of hard winner selection
2. uncertainty-based abstention or risk flagging
3. specialist activation masks by regime/context

## 6. Concrete recommendation for this repo

If the goal is maximum value per engineering hour, the next research-backed implementation should be:

### Recommendation

Build a **loss-discounted candidate selector** first.

Target:

- predict the best combo at each step by discounted recent loss

Loss choices to test:

1. filtered CDE
2. directional error
3. multi-class Brier / QPS
4. a blended loss such as:
   - `0.60 * filtered_cde + 0.25 * directional_error + 0.15 * class_error`

Evaluation:

- strict chronological walkforward
- compare against:
  - current winner logic
  - EWMA baselines
  - oracle full-pool ceiling

Why this is the right first move:

- strongest literature support
- most aligned with our actual target
- lowest engineering and overfitting risk
- reuses artifacts we already collect

## 7. Proposed implementation path

### Minimal implementation candidate

New analysis script idea:

- `scripts/analysis/htf_stage1_v2_loss_discounted_selector_audit.py`

Inputs:

- fixed-policy replay artifacts
- per-combo step metrics

For each root:

1. build chronological candidate-step table
2. compute discounted recent losses per combo
3. produce selector decision at each step using only past data
4. evaluate selected combo on:
   - filtered CDE
   - directional accuracy
   - class accuracy
   - regret vs oracle
   - top-1/top-2 capture

Then, only if worthwhile:

- add `scripts/analysis/htf_stage1_v2_meta_selector_audit.py`

## 8. Bottom line

The literature does support moving beyond the current winner logic.

But it does **not** support jumping straight to a complex meta-model or pairwise-agreement engine.

The strongest research-backed path for our exact setup is:

1. dynamic, walkforward-safe weighting/selection
2. weights based on the exact loss we care about
3. classification-aware scoring because the target is discrete
4. only then a lightweight competence meta-model above combo outputs

That is the highest-signal route from the papers and it is also the lowest-risk route given what our own 500-step audit already showed.

