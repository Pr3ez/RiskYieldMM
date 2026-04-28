# HTF Helper Source-Backed Validity Audit

Date: 2026-04-12  
Scope: `OU`, `GARCH`, `EGARCH`, `CUSUM`, `Kalman` helper features used by the HTF helper stage and downstream CatBoost walk-forward diagnostics.

## Objective

Verify, using:

- local implementation audit,
- empirical causality/reproducibility checks on real HTF data,
- and primary or academically trusted sources,

whether each helper family is:

1. theoretically valid,
2. implemented correctly,
3. free of lookahead bias under the current production chunking path,
4. reproducible in live market-data generation.

## Sources Used

Primary / academically trusted references:

- Tim Bollerslev, 1986, *Generalized autoregressive conditional heteroskedasticity*  
  https://ideas.repec.org/a/eee/econom/v31y1986i3p307-327.html
- Daniel B. Nelson, 1991, *Conditional Heteroskedasticity in Asset Returns: A New Approach*  
  https://econpapers.repec.org/RePEc:ecm:emetrp:v:59:y:1991:i:2:p:347-70
- R. E. Kalman, 1960, *A New Approach to Linear Filtering and Prediction Problems*  
  https://www.cs.unc.edu/~welch/kalman/media/pdf/Kalman1960.pdf
- E. S. Page, 1954, *Continuous Inspection Schemes*  
  https://academic.oup.com/biomet/article/41/1-2/100/456627
- Oldrich Vasicek, 1977, *An equilibrium characterization of the term structure*  
  https://www.sciencedirect.com/science/article/abs/pii/0304405X77900162
- Jize Zhang, Tim Leung, Aleksandr Aravkin, 2018, *Mean Reverting Portfolios via Penalized OU-Likelihood Estimation*  
  https://arxiv.org/abs/1803.06460
- Zachary David, 2019, *Information leakage in financial machine learning research*  
  https://journals.sagepub.com/doi/10.3233/AF-190900

## Local Artifacts

- Helper usage audit:
  - `test_output/htf_helper_feature_audit/20260412_201750`
- Helper causality / live-reproducibility audit:
  - `test_output/htf_helper_causality_audit/20260412_184017`
- Main code paths:
  - `scripts/feature_engineering/htf_helper_cache.py`
  - `scripts/target_models/helpers/ou.py`
  - `scripts/target_models/helpers/garch.py`
  - `scripts/target_models/helpers/egarch.py`
  - `scripts/target_models/helpers/cusum.py`
  - `scripts/target_models/helpers/kalman.py`
  - `riskyield_rust/src/ou.rs`
  - `riskyield_rust/src/garch.rs`
  - `riskyield_rust/src/egarch.rs`
  - `riskyield_rust/src/cusum.rs`
  - `riskyield_rust/src/kalman.rs`

## Standard for “No Lookahead”

I am using the stricter finance-ML standard from David (2019):

- a feature at time `t` must not use information from after `t`,
- preprocessing, normalization, denoising, or feature construction must not use future data,
- warm-up periods and hidden context windows count as part of the leakage surface.

This matters because the production helper pipeline:

- fits on the historical prefix,
- then calls `ensemble.transform(X_chunk)` on the prediction chunk,
- and writes those helper rows directly into model-facing HTF outputs.

So any future fill or full-chunk shortcut inside `transform(X_chunk)` is real leakage for the offline corpus and breaks exact live reproducibility.

## How the Current Helper Pipeline Works

Current production helper inputs are prepared from:

- `raw_returns`
- `raw_volatility`
- `close`
- optional `open`, `high`, `low`, `volume`

from `scripts/feature_engineering/htf_helper_cache.py`.

Then each chunk does:

1. fit helper ensemble on `X_train = X[:chunk_start]`
2. transform only `X_chunk = X[pred_start:chunk_end]`

This means:

- helper transforms do **not** receive the training tail as transform context,
- helper families that need prior state or rolling history must either:
  - carry it internally, or
  - recompute it causally from available prefix,
- otherwise the first rows of every chunk are at risk.

## Empirical Causality Audit

The empirical audit compared, on real HTF data:

1. `batch transform` vs `prefix-only transform`
   - checks for within-chunk future dependence
2. `batch transform` vs `context + chunk transform`
   - checks chunk-boundary instability and live reproducibility with more history

Summary from `helper_overall_summary.csv`:

| helper | prefix_all_pass | context_all_pass | interpretation |
|---|---:|---:|---|
| `cusum` | yes | no | causal inside chunk, boundary-sensitive |
| `garch` | yes | no | causal inside chunk, boundary-sensitive |
| `egarch` | no | no | not strictly causal / stable under current chunk path |
| `kalman` | no | no | not stable under current chunk path |
| `ou` | no | no | early-window future fill present |

Important refinement from the detailed diffs:

- `GARCH`, `CUSUM`, and `OU` converge once enough chunk history accumulates.
- `EGARCH` and `Kalman` still show non-trivial late-chunk differences, especially in z-score / regime style outputs.

## Family-by-Family Verdict

### 1. GARCH

**Theory**

Bollerslev (1986) generalizes ARCH by allowing conditional variance to depend on past conditional variances as well as past shocks. That supports:

- conditional volatility,
- volatility persistence,
- volatility forecasts,
- volatility regime features.

**Implemented features**

- `garch_cond_vol`
- `garch_vol_forecast`
- `garch_vol_zscore`
- `garch_vol_shock`
- `garch_persistence`
- `garch_vol_regime`
- `garch_vol_change`
- `garch_vol_ratio`

**Code assessment**

- recursion is causal in both Python and Rust
- transform uses fitted params from training
- no future fill found inside the chunk

**Empirical assessment**

- prefix-only causality: pass
- context sensitivity: yes, mainly near chunk start
- late-chunk stability: good

**Verdict**

- `garch_cond_vol`: valid and usable
- `garch_vol_forecast`: valid and usable
- `garch_vol_zscore`: valid and usable, but boundary-sensitive
- `garch_vol_shock`: valid and usable
- `garch_vol_regime`: valid and usable
- `garch_vol_change`: valid and usable
- `garch_vol_ratio`: valid and usable
- `garch_persistence`: theoretically valid but coarse; safe, not strong

**Live-parity requirement**

Use a historical buffer or exact chunking contract. Without buffer, first rows of a new chunk will not match a long continuous stream exactly.

### 2. CUSUM

**Theory**

Page (1954) introduced cumulative-sum change detection. The current implementation extends that into standard derived diagnostics:

- positive/negative cumulative sums,
- up/down changepoint flags,
- any changepoint,
- changepoint magnitude,
- time since last changepoint,
- rolling changepoint count.

These derived fields are not in Page’s original paper as named features, but they are legitimate causal transforms of the sequential changepoint process.

**Implemented features**

- `cusum_ret_pos`
- `cusum_ret_neg`
- `cusum_vol_pos`
- `cusum_vol_neg`
- `cp_ret_up`
- `cp_ret_down`
- `cp_vol_up`
- `cp_vol_down`
- `cp_any`
- `cp_magnitude`
- `days_since_cp`
- `cp_count_21`

**Code assessment**

- Rust and Python both implement sequential cumulative updates
- local rolling normalization is trailing-only
- no future fill found

**Empirical assessment**

- prefix-only causality: pass
- context sensitivity: yes, near chunk start
- late-chunk stability: good

**Verdict**

All current CUSUM features are valid and causally safe under the current transform contract.

**Live-parity requirement**

For exact parity, live generation should carry a context buffer so that early chunk rows do not reset changepoint memory.

### 3. OU / AR(1) Mean-Reversion

**Theory**

The OU process is a standard mean-reverting diffusion. Vasicek (1977) uses a diffusion-rate framework, and Zhang et al. (2018) explicitly note that OU is the continuous-time version of a discrete-time autoregressive model. That supports:

- mean-reversion coefficient / AR(1) coefficient
- speed of mean reversion (`kappa`)
- half-life
- deviation z-score
- stationarity and regime classifications

**Implemented features**

- `ou_phi`
- `ou_kappa`
- `ou_halflife`
- `ou_zscore`
- `ou_zscore_abs`
- `ou_is_stationary`
- `ou_halflife_regime`
- `ou_reverting`

**Code assessment**

The current Rust implementation computes rolling AR(1) features causally for rows with enough history, but then does this:

- fills early `phi/kappa/halflife/is_stationary/halflife_regime` rows with the **first later valid value**
- fills early `zscore/zscore_abs` rows with the **first later valid z-score**

This is a direct future-to-past fill inside the transform chunk.

**Empirical assessment**

- prefix-only causality: fail
- context sensitivity: fail
- later-row stability after enough history: acceptable

**Verdict**

- `ou_phi`: conceptually valid, current implementation not strict-causal at chunk start
- `ou_kappa`: same issue
- `ou_halflife`: same issue
- `ou_is_stationary`: same issue
- `ou_halflife_regime`: same issue
- `ou_zscore`: conceptually valid, current implementation future-fills early rows
- `ou_zscore_abs`: same issue
- `ou_reverting`: inherits the early-window issue

**Live-parity verdict**

Not safe as currently implemented if the requirement is strict no-lookahead and exact live reproducibility.

**Required fix**

Do not backfill early rows from the first later valid value. Use:

- `NaN`,
- neutral sentinel,
- or explicit “insufficient history” mask

until enough trailing history exists.

### 4. EGARCH

**Theory**

Nelson (1991) introduced EGARCH specifically to model asymmetric volatility responses and persistence without the same parameter-constraint problems as standard GARCH. That supports:

- volatility level,
- log volatility,
- leverage / asymmetry,
- persistence,
- shock impact / news impact,
- volatility regime logic.

**Implemented features**

- `egarch_vol`
- `egarch_log_vol`
- `egarch_asymmetry`
- `egarch_persistence`
- `egarch_news_impact`
- `egarch_vol_zscore`
- `egarch_vol_regime`
- `egarch_leverage_active`

**Code assessment**

- `egarch_asymmetry` and `egarch_persistence` are constant fitted parameters per transform
- those two are safe from leakage, but they are coarse fitted-state artifacts rather than rich row-level signals
- dynamic outputs are generated from fitted params on the chunk

The empirical audit shows more serious problems:

- prefix-only causality fails for:
  - `egarch_vol_zscore`
  - `egarch_vol_regime`
  - `egarch_news_impact`
  - `egarch_leverage_active`
- context sensitivity persists even late in the chunk, especially for:
  - `egarch_vol_zscore`
  - `egarch_log_vol`
  - `egarch_vol`

So even though the feature family is theoretically valid, the current transform contract is not stable enough to certify as strict live-safe.

**Verdict**

- `egarch_vol`: conceptually valid, current implementation needs redesign / stricter state contract
- `egarch_log_vol`: same
- `egarch_news_impact`: same
- `egarch_vol_zscore`: same
- `egarch_vol_regime`: same
- `egarch_leverage_active`: same
- `egarch_asymmetry`: safe but weak and globally degenerate in current data
- `egarch_persistence`: safe but weak and globally degenerate in current data

**Live-parity verdict**

Not safe to certify for live use under the current chunk transform.

**Required fix**

Rework EGARCH transform so batch and prefix generation are invariant, and add state/context handling at chunk boundaries.

### 5. Kalman

**Theory**

Kalman (1960) is a recursive state-estimation framework based on state transition and sequential covariance updates. That supports:

- filtered deviation,
- latent velocity and acceleration,
- prediction error / innovation,
- z-score of innovation,
- regime from standardized velocity.

**Implemented features**

- `kalman_filtered_dev`
- `kalman_velocity`
- `kalman_acceleration`
- `kalman_pred_error`
- `kalman_innovation`
- `kalman_zscore`
- `kalman_regime`

**Code assessment**

The Python path warms state on the training prefix and can continue state.  
The Rust path currently cold-starts from `signal[0]` inside each transform chunk and ignores the trained end state.

That is not classical lookahead, but it breaks exact chunk-to-live continuation.

**Empirical assessment**

- prefix-only causality: fail, especially `kalman_zscore` and `kalman_regime`
- context sensitivity: fail across all features
- late-chunk differences remain non-trivial

**Verdict**

- `kalman_filtered_dev`: conceptually valid, implementation not live-stable
- `kalman_velocity`: same
- `kalman_acceleration`: same
- `kalman_pred_error`: same
- `kalman_innovation`: same
- `kalman_zscore`: same, and the most visibly unstable
- `kalman_regime`: same

**Live-parity verdict**

Not safe to certify for exact live generation under the current Rust path.

**Required fix**

Add explicit state handoff across chunks or a contextful transform path that starts from the training-end filter state.

## Feature-Level Final Classification

### Safe now

- All CUSUM features
- GARCH dynamic features:
  - `garch_cond_vol`
  - `garch_vol_forecast`
  - `garch_vol_zscore`
  - `garch_vol_shock`
  - `garch_vol_regime`
  - `garch_vol_change`
  - `garch_vol_ratio`

### Safe but weak / coarse

- `garch_persistence`
- `egarch_asymmetry`
- `egarch_persistence`

### Valid in theory, but current implementation is not strict-causal / not live-certified

- All OU features
- EGARCH dynamic features:
  - `egarch_vol`
  - `egarch_log_vol`
  - `egarch_news_impact`
  - `egarch_vol_zscore`
  - `egarch_vol_regime`
  - `egarch_leverage_active`
- All Kalman features

## What This Means for CatBoost

If the goal is “valid information for CatBoost without lookahead and reproducible live features,” the current helper families split into three groups:

1. **Good to keep**
- CUSUM
- GARCH dynamic block

2. **Keep only if treated as coarse fitted-state context**
- `garch_persistence`
- `egarch_asymmetry`
- `egarch_persistence`

3. **Do not trust yet for live-equivalent model training**
- OU block
- Kalman block
- EGARCH dynamic block

## Required Cleanup Plan

### Immediate

- remove or block globally degenerate helper outputs from model-facing training:
  - `H_4class_1_egarch_asymmetry`
  - `H_4class_1_egarch_persistence`

### Next

- OU:
  - remove future backfill at chunk start
  - emit neutral / missing until enough history exists
- Kalman:
  - carry state across chunks
  - stop cold-starting each transform chunk
- EGARCH:
  - make transform prefix-invariant
  - define explicit chunk state contract

### Validation

Add automated tests for every helper family:

- prefix invariance
- context invariance after enough history
- no future-fill on early rows
- batch vs live-stream equivalence

## Bottom Line

The helper block is **not globally invalid**, but it is also **not safe as a whole**.

Current source-backed verdict:

- `CUSUM`: valid and safe
- `GARCH`: valid and safe enough with context buffer
- `OU`: conceptually right, implementation currently leaks future information at chunk start
- `Kalman`: conceptually right, implementation currently breaks exact live continuation
- `EGARCH`: conceptually right, but current transform contract is not stable enough to certify as strict live-safe

So if we want helper features that can be regenerated live without lookahead bias:

- keep `CUSUM` and most of `GARCH`,
- treat `OU`, `Kalman`, and dynamic `EGARCH` as cleanup-required before further model development.
