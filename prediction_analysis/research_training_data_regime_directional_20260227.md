# Research Note: Training-Data Regime Signals for Directional Routing

Date: 2026-02-27
Scope: 1m/target_4class, 24 configs, full 3500/500 workflow

## Current observed failure mode

From latest full run (`20260227_211102_prod_full3500_cfg24_dualhead_anticollapse`):
- Router train looked usable (`anti_collapse_max_active_coverage=0.5425` for selected candidate).
- Holdout collapsed to all-HOLD (`active_batches=0`, `coverage=0`).
- Holdout max router confidence compressed (`max selected_p_hit ~= 0.5267`) while selected threshold was `0.60`.

Implication: the main issue is not only thresholding; it is regime/distribution mismatch between train and holdout that de-calibrates router scores.

## Research-backed direction

1. Covariate-shift-aware training/selection
- Importance-weighted model selection under covariate shift (IWCV) should replace plain in-sample selection when train/test distributions differ.

2. Time-varying model weights and forgetting
- Dynamic Model Averaging and dynamic logistic formulations are explicitly designed for changing data-generating mechanisms and binary directional classification.

3. Explicit selective prediction objective
- Selective prediction should be optimized during training (risk-coverage objective), not only via post-hoc thresholds.

4. Calibrated uncertainty under shift
- Post-hoc calibration and adaptive conformal methods are needed because confidence calibration drifts over time.

5. Overfitting control for many candidate recipes
- Large model/candidate search increases backtest-overfitting risk; selection must remain nested-WF and drift-robust.

## Practical implementation plan (next)

1. Add training-data regime features per batch (not prediction-only):
- realized volatility/range,
- trend strength,
- class prevalence drift,
- volume/liquidity proxies,
- distance-to-training-regime statistics.

2. Add covariate-shift weighting in router fit:
- estimate density-ratio proxy between recent live-like window vs older training window,
- use weights in router training and candidate selection objective.

3. Replace pure Brier selection with reject-aware utility objective + minimum coverage regularizer:
- optimize utility with explicit opposite-direction penalty,
- include train-time coverage lower bound regularization to avoid confidence collapse.

4. Add class-conditional calibration and adaptive conformal gate on pre-holdout calibration slice:
- separate UP/DOWN risk control,
- use adaptive update for drift.

5. Keep strict leakage controls:
- nested walk-forward,
- no future joins,
- purge/embargo on split boundaries,
- fixed untouched final holdout.

## Why this should improve directional quality

The current collapse is consistent with distribution shift and confidence miscalibration. Methods above directly target those failure sources:
- shift-aware fitting,
- time-varying model weighting,
- training-time selective objective,
- calibrated risk control.

This is the highest-probability path to improve safe directional accuracy without lookahead.

## Sources

- Covariate shift / IWCV: https://jmlr.org/beta/papers/v8/sugiyama07a.html
- Dynamic logistic + DMA (binary): https://academic.oup.com/biometrics/article/68/1/23/7390679
- Dynamic model averaging in large spaces: https://arxiv.org/abs/1410.7799
- DMA package paper (economics/finance practice): https://www.jstatsoft.org/article/view/v084i11
- Conformal Risk Control: https://arxiv.org/abs/2208.02814
- Adaptive conformal under shift: https://arxiv.org/abs/2106.00170
- Calibration (temperature scaling): https://proceedings.mlr.press/v70/guo17a.html
- Selective training (risk-coverage): https://arxiv.org/abs/1901.09192
- Backtest overfitting risk (SSRN): https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253
