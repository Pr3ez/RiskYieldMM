# Probability-First Directional Prediction Research (24 configs, 1m/target_4class)

## Scope
Define how to use:
1. **Training-context data** (config geometry / walk-forward structure), and
2. **Per-batch probability streams** from 24 configs,

to improve directional prediction under strict causal constraints (history `< t` only).

## What Research Supports

1. **Optimize probabilistic forecasts with proper scoring rules first**
- Directional routing quality improves when probabilities are calibrated and trained with proper losses (log-loss/Brier), not only argmax accuracy.
- Practical implication: train/select meta models by `brier/logloss`, then apply directional/risk gates for execution.

2. **Stacking / super learner is a strong base for probability combination**
- A learned meta-combiner over base probabilities is statistically well-grounded and usually stronger than single-model choice.
- Practical implication: maintain linear/logistic stacker baselines before complex gates.

3. **Time-varying weights are essential in nonstationary series**
- Online expert weighting and adaptive forecast combinations are robust under drift.
- Practical implication: keep online EWAF/Hedge-style combiners in benchmark set.

4. **Attention/gating can help, but only after strong baselines**
- Transformers are strong sequence models, but attention weights are weak explanations.
- Practical implication: use attention as predictive mechanism (not explanation), and only after simpler causal baselines plateau.

5. **Forecast combinations generally outperform selecting one static winner**
- Empirical forecasting literature (including M4) supports combining over single-model selection.
- Practical implication: move from hard winner-picking to probability-aware routing + combination.

## Recommended Architecture for Your Data

### Level A: Per-config activation models (already implemented)
For each config `c`, predict:
- `P(hit_c,t)` where `hit_c,t = 1` iff `dir_acc_c,t >= 0.70`.
- Tune `lookback_c` separately (causal WF, no future).

Why: each config has different regime memory.

### Level B: Cross-config global router (next step)
Train one global model on rows `(batch, config)` with target `hit_c,t` and features from both domains:

- **Training-context features** (static per config):
  - `fold_count`, `val_batches_per_fold`, `train_batches_per_fold`, `train/val ratio`, `effective train window`.
- **Probability-stream features** (dynamic per batch/config):
  - `p_up_mean`, `p_down_mean`, `margin`, `entropy proxy`, `top-class concentration`,
  - lagged hit-rate / lagged dir-acc,
  - rank within-batch (`margin rank`, `confidence rank`),
  - agreement/disagreement with other configs.

Output:
- `P(hit_c,t)` for all 24 configs; select top-k or top-1 with threshold.

### Level C: Direction/risk gate
After selecting candidates, apply risk-first gate:
- emit only if `max P(hit_c,t) >= tau`,
- optional direction-consistency gate (top-2 selected configs agree),
- abstain (`HOLD`) otherwise.

## Strict Causality Protocol (must keep)

1. Build features at batch `t` using only data available by `t`.
2. Train on history `< t` only.
3. If any horizon overlap exists in labels, use purge/embargo around split boundaries.
4. Calibrate probabilities on history-only validation slice.

## Metrics to Optimize (risk-first)

Primary:
- `opposite_fp_rate_active`
- `opposite_fp_rate_covered`

Secondary:
- `directional_active_safe_accuracy`
- cadence target (`~1 signal / 10-15 batches`)

Support:
- Brier, log-loss, ECE-like calibration diagnostics, coverage.

## Decision Rule for Production Promotion
Promote method only if:
1. improves both opposite-direction error metrics vs current baseline,
2. keeps cadence in target band,
3. maintains or improves directional safe accuracy,
4. reproducible under fixed seed and same walk-forward slices.

## Immediate Next Experiments

1. Run full 3500-batch per-config activation model (current script).
2. Add global router model using `(batch, config)` rows with static + dynamic features.
3. Compare against:
   - fixed best config,
   - online EWAF,
   - logistic stacker,
   - activation+router.
4. Select threshold by risk-first objective, not by raw accuracy.

## Sources
- Vaswani et al., *Attention Is All You Need* (NeurIPS 2017): https://arxiv.org/abs/1706.03762
- Jain & Wallace, *Attention is not Explanation* (NAACL 2019): https://aclanthology.org/N19-1357/
- Guo et al., *On Calibration of Modern Neural Networks* (ICML 2017): https://proceedings.mlr.press/v70/guo17a.html
- Yao et al., *Using Stacking to Average Bayesian Predictive Distributions* (Bayesian Analysis): https://projecteuclid.org/euclid.ba/1516093227
- van der Laan et al., *Super Learner* (Statistical Applications in Genetics and Molecular Biology, 2007): https://pubmed.ncbi.nlm.nih.gov/17910531/
- Freund & Schapire, *A Decision-Theoretic Generalization of On-Line Learning and an Application to Boosting* (JCSS 1997): https://doi.org/10.1006/jcss.1997.1504
- Berrisch & Ziel, *Online forecast combinations using Bayesian updating* (IJF 2022): https://doi.org/10.1016/j.ijforecast.2021.11.009
- Timmermann, *Forecast Combinations* (Handbook of Economic Forecasting): https://doi.org/10.1016/S1574-0706(05)01004-9
- Makridakis et al., *The M4 Competition* (IJF 2018): https://doi.org/10.1016/j.ijforecast.2018.06.001
- Gneiting & Raftery, *Strictly Proper Scoring Rules...* (JASA 2007): https://doi.org/10.1198/016214506000001437
