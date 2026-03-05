# Research Note: Horizon Selection + Leakage-Safe Walk-Forward (8h Regime)

Date: 2026-03-05
Scope: 1m/target_4class directional alignment with 8h regime prediction

## 1) Objective
Define a research-backed method to:
- choose the **correct 8h trend horizon**,
- evaluate with **strict no-lookahead walk-forward**,
- preserve realistic deployment behavior (train `< t`, predict `t+H`).

## 2) Primary Sources Reviewed

1. Tashman (2000), *Out-of-sample tests of forecasting accuracy* (rolling-origin framework)
- https://www.sciencedirect.com/science/article/pii/S0169207000000650

2. Cerqueira et al. (2019), *Evaluating time series forecasting models* (evaluation protocols)
- https://arxiv.org/abs/1905.11744

3. Ben Taieb et al. (2012), *A review and comparison of strategies for multi-step ahead time series forecasting based on ML*
- https://www.sciencedirect.com/science/article/pii/S0169207012000637

4. Ben Taieb & Hyndman (2012), *Recursive and direct multi-step forecasting: the best of both worlds* (Rectify)
- https://robjhyndman.com/papers/rectify.pdf

5. Bergmeir et al. (2012), *Use of CV for time series predictor evaluation* (dependence-aware CV caveats)
- https://link.springer.com/article/10.1007/s10844-011-0177-8

6. scikit-learn `TimeSeriesSplit` docs (`gap` parameter for leakage buffer)
- https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html

7. Diebold & Mariano (1995), *Comparing predictive accuracy*
- https://www.nber.org/papers/t0169

8. Clark & West (2007), *Approximately normal tests for equal predictive accuracy in nested models*
- https://www.nber.org/papers/t0326

9. Gibbs & Candès (2021), *Adaptive Conformal Inference Under Distribution Shift*
- https://proceedings.neurips.cc/paper/2021/hash/0d441de75945e5acbc865406fc9a2559-Abstract.html

10. Geifman & El-Yaniv (2017), *Selective classification for deep neural networks* (risk-coverage framing)
- https://arxiv.org/abs/1705.08500

## 3) What These Sources Imply for Our Setup

1. Use **rolling-origin / walk-forward** as primary protocol; avoid random CV for model selection in dependent series.
2. Treat horizon selection as **multi-step forecasting design** problem (`H` in 8h steps), not only threshold tuning.
3. Compare horizon methods with forecast-accuracy tests (DM / Clark-West where applicable).
4. Add explicit **leakage buffer (`gap`)** when labels use forward windows or overlap windows.
5. For live deployment goals, evaluate via **risk-coverage** curves (selective prediction), not only raw accuracy.

## 4) Recommended Protocol (Implementation-Ready)

### 4.1 Horizon candidates
Evaluate horizons in 8h steps:
- `H ∈ {1,2,3,4,6,9,12,21}`
- Interpretation: 8h, 16h, 24h, 32h, 48h, 72h, 96h, 1 week.

### 4.2 Lookback candidates
Use dependence-aware windows:
- `L ∈ {21,90,270,540,all}` rows (1w, 1m, 3m, 6m, expanding).

### 4.3 Labeling
For each time `t`, train with information at `t` and predict `t+H`:
- Direction label from 1m aggregate for future horizon block.
- For 4-class compatibility, evaluate both:
  - binary direction (`DOWN={0,1}`, `UP={2,3}`),
  - optional 3-regime (`bull/bear/chop`) via volatility-scaled return bands.

### 4.4 Walk-forward split
For each outer step `t` in holdout:
- Train on `[t-L, ..., t-gap]` (or expanding until `t-gap`),
- Predict on `t` only,
- Advance by 1 batch.

Set `gap = H` (minimum) when target uses forward horizon windows.

### 4.5 Selection objective
Primary objective per horizon:
- maximize `directional_active_safe_accuracy` under constraints:
  - opposite-direction risk cap,
  - minimum coverage,
  - cadence constraint.

Secondary objective:
- maximize coverage at same or lower opposite-FP risk.

### 4.6 Statistical comparison
For shortlisted horizons/methods, apply:
- DM test on per-step loss differences,
- Clark-West for nested model comparisons.

## 5) Current Data Sanity Check (Oracle-style, not deployable)
Artifact:
- `prediction_analysis/one_minute_target4class_8h_regime_outputs/research_20260305_horizon_diagnostic.csv`

This diagnostic compares sign of **future** 8h return (`ret_h`) to next-batch 1m directional label, to estimate alignment of horizon definitions.

Observed top overall alignment:
- `H=1`: accuracy `0.8012`
- `H=2`: accuracy `0.6913`
- `H=3`: accuracy `0.6595`

Interpretation:
- The target is most aligned with immediate next 8h direction (`H=1`), then decays with longer horizon.
- This is a **label-alignment diagnostic**, not a tradable predictor, because it uses future return directly.

## 6) Next Concrete Implementation Steps

1. Add `--trend-horizon-steps` to `prediction_analysis/one_minute_target4class_8h_regime_pipeline.py`.
2. Enforce `gap >= trend_horizon_steps` in walk-forward splits.
3. Build horizon sweep runner over `H × L × method` with identical holdout.
4. Export per-horizon risk-coverage table + DM/Clark-West pairwise tests.
5. Promote only horizons/methods that pass risk constraints and remain stable across subperiod slices.

