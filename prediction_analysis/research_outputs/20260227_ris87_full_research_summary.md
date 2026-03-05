# RIS-87 Full Research Summary and Next Improvement Plan

## Objective
Maintain `directional_active_safe_accuracy >= 0.70` while increasing active coverage for `1m/target_4class` (24 configs), under strict no-lookahead walk-forward evaluation.

## What we ran (key outcomes)

### Multitimeframe references (full 3500-ish historical context)
- `20260220_182828_specialist_prod_relaxed_full` (`history_brier_ewma + strict_agreement_margin`)
  - directional_active_accuracy: `0.5731`
  - directional_active_coverage: `0.0551`
  - opposite_fp_rate_covered: `0.0235`
- `20260225_203425_full3500_strict_winner_011059_live`
  - directional_active_accuracy: `0.5351`
  - directional_active_coverage: `0.0601`
  - opposite_fp_rate_covered: `0.0279`
- `20260226_011654_full3500_dual_diversity_141257_live`
  - directional_active_accuracy: `0.5236`
  - directional_active_coverage: `0.1321`
  - opposite_fp_rate_covered: `0.0629`

Observed tradeoff: more coverage usually increases opposite-direction errors.

### 1m/target_4class focused program
Best run so far for safe directional accuracy:
- `20260227_215602_prod_full3500_cfg24_shift_reject_rollingq_covcon_v1`
  - holdout safe accuracy: `0.7037`
  - coverage: `0.054` (27/500)
  - opposite_fp_rate_active: `0.2963`
  - opposite_fp_rate_covered: `0.016`

Recent P0 dual-head constrained run:
- `20260227_225312_prod_full3500_cfg24_p0_dual_head_constrained_v1`
  - holdout safe accuracy: `0.4359`
  - coverage: `0.078` (39/500)
  - opposite_fp_rate_active: `0.5641`
  - opposite_fp_rate_covered: `0.044`

Result: P0 implementation increased activity but quality collapsed.

## Root cause (data-backed)

Using `per_config_best_probabilities.parquet` (holdout):
- per-config hit prediction AUC: `0.5095`
- AP: `0.2950` vs base hit rate `0.2869`
- top-1-by-score selected config mean directional accuracy: `0.5280`

Interpretation: router ranking signal is close to random in the current feature/target setup.

## Oracle headroom (problem is selection, not candidate availability)

Holdout batches (500):
- batches with >=1 config at dir-acc >=0.70: `82.6%`
- average configs >=0.70 per batch: `6.89`
- oracle selective policy (if best config known):
  - coverage: `0.826`
  - safe accuracy: `0.8758`

So high-quality opportunities exist frequently; current router cannot identify them causally.

## Research synthesis (primary sources)

- Selective classification with risk guarantees: Geifman & El-Yaniv (2017) — https://arxiv.org/abs/1705.08500
- End-to-end selective model (SelectiveNet): Geifman et al. (2019) — https://arxiv.org/abs/1901.09192
- Abstention loss design (Deep Gamblers): Liu et al. (NeurIPS 2019) — https://papers.nips.cc/paper_files/paper/2019/hash/0c4b1eeb45c90b52bfb9d07943d855ab-Abstract.html
- Conformal Risk Control: Angelopoulos et al. (2022) — https://arxiv.org/abs/2208.02814
- Adaptive conformal inference under distribution shift: Gibbs & Candès (2021) — https://arxiv.org/abs/2106.00170
- Weighted conformal under covariate shift: Tibshirani et al. (2019) — https://arxiv.org/abs/1904.06019
- Dynamic Model Averaging: Raftery et al. (2010) — https://pmc.ncbi.nlm.nih.gov/articles/PMC2895940/
- eDMA package/practical DMA: Catania & Nonejad (2018) — https://www.jstatsoft.org/article/view/v084i11
- Hedge / multiplicative weights theory: Freund & Schapire (1997) — https://doi.org/10.1006/jcss.1997.1504

## Recommended next path (ordered)

### Step 1 (highest ROI): Pairwise ranking objective per batch (not binary hit)
Current issue is poor ranking separation. Replace router target with pairwise/listwise ranking loss:
- train to rank winning config above non-winning configs within each batch
- combine with explicit opposite-direction penalty
- keep selective gate on top of ranking score
Expected: better ordering quality (AUC/rank-lift), prerequisite for any coverage increase.

### Step 2: Class-conditional selective heads and constraints
Separate UP and DOWN accept/reject heads + separate risk constraints:
- independent thresholds for UP and DOWN
- independent opposite-FP constraints by direction
Expected: reduce opposite-direction active errors where one side is noisier.

### Step 3: Shift-aware online weighting on top-K
On each batch, after ranking:
- keep top-K shortlist (e.g., K=3)
- apply recency-discounted expert weights (Hedge/DMA-style) over shortlist only
- activate only if weighted consensus margin exceeds class-conditional gate
Expected: improved stability without large coverage collapse.

### Step 4: Coverage schedule instead of fixed cadence band during training
Use rolling coverage target (e.g., 4%->8% slowly) to avoid aggressive jump to noisy regions.
Expected: maintain >0.70 while gradually expanding active subset.

## Immediate acceptance criteria for next run
- Holdout safe accuracy >= `0.70`
- Holdout opposite_fp_rate_covered <= `0.03`
- Holdout opposite_fp_rate_active <= `0.30` (relaxed to current realistic boundary)
- Coverage target phase-1: `0.05-0.08`

If phase-1 passes, then expand coverage in controlled increments.
