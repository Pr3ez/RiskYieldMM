# RIS-85: Why safe directional accuracy collapsed and what to do next

## Current evidence from 1m/target_4class (24 configs, 3500/500)

- Best recent holdout point above 0.70 safe accuracy:
  - run: `20260227_215602_prod_full3500_cfg24_shift_reject_rollingq_covcon_v1`
  - `directional_active_safe_accuracy=0.7037`
  - `coverage=0.054` (27/500), cadence `18.52` batches/signal
  - `opposite_fp_rate_active=0.2963`
- Tuned primal-dual run increased activity but lost quality:
  - run: `20260227_223004_prod_full3500_cfg24_shift_reject_rollingq_primaldual_tuned1`
  - `directional_active_safe_accuracy=0.5333`
  - `coverage=0.060` (30/500)
  - `opposite_fp_rate_active=0.4667`

## Root-cause check (data says ranking is near-random)

Using `per_config_best_probabilities.parquet` from the tuned run:

- Per-config hit predictor quality on holdout (all `(batch, config)` rows):
  - AUC: `0.5095`
  - AP: `0.2950` (base hit-rate `0.2869`)
- Top-1 by predicted `p_hit` only:
  - hit-rate `0.322` (small lift over base `0.2869`)
  - mean selected directional acc `0.5280`

Interpretation: router scores are not separating "good config now" vs "bad config now" strongly enough.

## Oracle headroom (so problem is selection, not candidate availability)

Holdout (500 batches):
- mean best-config directional accuracy per batch: `0.8257`
- batches with at least one config `>=0.70`: `82.6%`
- average number of configs `>=0.70` per batch: `6.89`
- oracle selective policy (choose best config when max>=0.70):
  - coverage `0.826`
  - safe accuracy `0.8758`

Interpretation: there is large recoverable signal; current routing/gating is failing to identify it causally.

## Research-backed next methods (priority)

### P0 — Train-time selective objective (not post-hoc thresholding)

- Use a dual-head model jointly learning:
  1) config ranking utility,
  2) accept/reject probability.
- Optimize a constrained objective with Lagrangian multipliers for:
  - max opposite-fp-active,
  - max opposite-fp-covered,
  - minimum coverage band.
- Why: selective learning literature shows end-to-end reject learning improves risk-coverage frontier compared to confidence-threshold-only methods.

### P1 — Class-conditional risk control + weighted conformal

- Calibrate separate thresholds for UP and DOWN risk (different tails).
- Use weighted conformal under covariate shift with rolling density-ratio proxy.
- Why: your primary risk is opposite-direction errors; class-conditional control is more aligned than single global threshold.

### P2 — Dynamic model averaging / loss-discounted expert weights for nonstationarity

- Replace static/slow score aggregation with dynamic loss-discounting over configs.
- Use recency-discounted losses and regime-adaptive forgetting factors.
- Why: evidence from forecasting literature shows dynamic weighting handles structural change better than fixed combinations.

## Initial implementation target for next run

- Keep current causal protocol and holdout split.
- Add features beyond probability geometry:
  - batch-level regime descriptors from training window used by each config (volatility/trend/imbalance proxies already available in stage artifacts),
  - config-train geometry (`fold_count`, `val_len`, `train_len`, recency offsets),
  - cross-config rank features (percentile rank, distance to top-k consensus).
- Replace single-stage router with two-stage:
  1) rank top-k candidates,
  2) selective accept head on chosen candidate.
- Select operating point by constrained optimization on pre-holdout only.

## Key references

- Selective classification with risk guarantees: https://arxiv.org/abs/1705.08500
- End-to-end reject-option training (SelectiveNet): https://arxiv.org/abs/1901.09192
- Abstention loss design (Deep Gamblers): https://arxiv.org/abs/1907.00208
- Conformal Risk Control: https://arxiv.org/abs/2208.02814
- Adaptive conformal under shift: https://arxiv.org/abs/2106.00170
- Weighted conformal under covariate shift: https://arxiv.org/abs/1904.06019
- Dynamic model averaging (original): https://pmc.ncbi.nlm.nih.gov/articles/PMC2895940/
- DMA for practitioners (eDMA): https://www.jstatsoft.org/article/view/v084i11
- Loss-discounted model averaging (2024): https://www.sciencedirect.com/science/article/pii/S0169207024000268
