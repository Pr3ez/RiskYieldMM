# Research Refresh: Why 1m/target_4class Is Underperforming and What to Implement Next

Date: 2026-02-27

## Local evidence (what is working vs failing)

### Working
- Data contract and leakage checks are passing in all recent runs.
- There is strong per-batch opportunity in the candidate pool:
  - On holdout (last 500), per-batch oracle max config dir-accuracy mean is ~0.826.
  - 413/500 batches have at least one config with dir-accuracy >= 0.70.

### Failing
- Real-time selector/routing quality remains low:
  - Best fixed config on holdout is ~0.51 directional accuracy.
  - Router top-1 raw direction is ~0.526 in cost-sensitive run (still weak).
- Score calibration/drift is unstable across train->holdout:
  - Cost-sensitive run (`20260227_144749`) holdout top router score max is ~0.479, so selected threshold 0.5 yields zero active signals.
- Risk-first operating targets are still missed even with posthoc thresholding:
  - Best cadence-band posthoc point (cost-sensitive): safe ~0.571, opp_active ~0.429, opp_cov ~0.036.

## Research takeaways relevant to this case

1. **Combine forecasts, do not rely on static winner selection**
- Forecast combination literature strongly supports combination/stacking over single best model.
- Sources:
  - Timmermann, *Forecast Combinations* (Handbook): https://doi.org/10.1016/S1574-0706(05)01004-9
  - M4 findings: https://doi.org/10.1016/j.ijforecast.2018.06.001

2. **Optimize probabilities with proper scoring, then make decisions with explicit utility/cost**
- Proper scoring rules are necessary for calibrated probability forecasting.
- But trading action should be selected by decision utility/cost, not only Brier/logloss.
- Source: Gneiting & Raftery (2007): https://doi.org/10.1198/016214506000001437

3. **Time-varying weights/online adaptation are appropriate under regime drift**
- Online combination methods and dynamic averaging are designed for nonstationarity.
- Sources:
  - Freund & Schapire (1997): https://doi.org/10.1006/jcss.1997.1504
  - Berrisch & Ziel (2022): https://doi.org/10.1016/j.ijforecast.2021.11.009
  - Raftery et al. DMA reference: https://doi.org/10.1198/TECH.2010.08174

4. **Use selective prediction / abstention as a first-class objective**
- Your setup is effectively selective classification with abstain (`HOLD`).
- Coverage-risk tradeoff should be optimized directly, not indirectly by score threshold chosen on misaligned target.
- Sources:
  - SelectiveNet (Geifman & El-Yaniv 2019): https://proceedings.mlr.press/v97/geifman19a.html
  - Conformal risk control style framing: https://arxiv.org/abs/2107.07511

5. **Calibration matters and can collapse under shift**
- Score distribution shift train->holdout can invalidate fixed thresholds.
- Source: Guo et al. (2017): https://proceedings.mlr.press/v70/guo17a.html

## Root-cause hypothesis for current pipeline

The main bottleneck is not data integrity, but **objective mismatch**:
- Router currently predicts either `hit>=0.7` or `dir_acc` proxy, then downstream thresholding attempts to satisfy trading-risk constraints.
- This separates training objective from deployment utility.
- Under shift, threshold behavior collapses (either too many risky signals or zero signals).

## Next implementation (recommended)

Implement a **direct utility router** trained on per-(batch, config) utility target that encodes your risk policy:

- Utility per row `u` (example):
  - correct directional prediction: `+1.0`
  - opposite-direction prediction: `-lambda_opp` (e.g. `2.0-3.0`)
  - hold/abstain baseline: `0.0`
- Train router to predict expected utility `E[u | features]` causally.
- At inference per batch:
  1. pick top config by expected utility
  2. emit direction only if `E[u] >= tau`, else HOLD
- Tune `lambda_opp` and `tau` on train WF only; freeze on holdout.

Why this matches research + your target:
- Directly aligns training with opposite-direction risk minimization and safe-accuracy goals.
- Preserves selective abstention framework.
- Avoids indirect proxy mismatch from current `hit`/`dir_acc` targets.

## Acceptance gates for next run

- Same strict causality/leakage checks.
- Holdout (last 500) promotion criteria unchanged:
  - `directional_active_safe_accuracy >= 0.70`
  - `opposite_fp_rate_active <= 0.25`
  - `opposite_fp_rate_covered <= 0.03`
  - cadence in `10-15` batches per signal.

## Additional sources reviewed
- Stacking / super learner:
  - Wolpert (1992): https://www.sciencedirect.com/science/article/pii/S0893608005800231
  - Super Learner (van der Laan et al. 2007): https://pubmed.ncbi.nlm.nih.gov/17910531/
- Attention/sequence models caveat:
  - Transformer: https://arxiv.org/abs/1706.03762
  - Attention not explanation: https://aclanthology.org/N19-1357/
