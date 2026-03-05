# Research Continuation (2026-02-27): Online Abstention Policy-Pool + Next Fixes

## Scope

- Continue primary-source research for risk-first directional routing.
- Implement and evaluate a causal online abstention policy-pool gate on top of current 1m/target_4class pipeline.
- Compare against prior Phase A / Phase B / patched conformal baseline.

## Primary-source findings used in this iteration

1. **Online learning with abstention is a principled formulation for "act vs abstain"** and supports regret-style adaptation in nonstationary settings.
- Source: Cortes et al., ICML 2018 (PMLR)  
  https://proceedings.mlr.press/v80/cortes18a.html

2. **Conformal risk control remains the right layer for risk guarantees**, but it calibrates decision risk around a score; it does not create separability by itself.
- Source: Conformal Risk Control  
  https://arxiv.org/abs/2208.02814

3. **Weighted conformal under covariate shift is appropriate for recency weighting** in drifting time series.
- Source: Conformal Prediction Under Covariate Shift  
  https://arxiv.org/abs/1904.06019

4. **Model-selection under nonstationarity should be online/adaptive**, not static one-shot.
- Source: Online Conformal Model Selection for Nonstationary Time Series  
  https://arxiv.org/abs/2506.05544

5. **Selective prediction quality improves when reject behavior is part of training objective**, rather than only post-hoc thresholding.
- Source: SelectiveNet  
  https://arxiv.org/abs/1901.09192

6. **Adaptive weighting baselines from econometrics remain strong in finance drift regimes**.
- Source: eDMA (JSS)  
  https://www.jstatsoft.org/article/view/v084i11

## Implementation added

File:
- `prediction_analysis/one_minute_target4class_config_activation_meta.py`

Added:
- CLI options:
  - `--use-online-policy-pool`
  - `--online-policy-eta-grid`
  - `--online-policy-hold-loss-grid`
  - `--online-policy-topn-grid`
  - `--online-policy-warmup-frac`
  - `--online-policy-min-warmup-batches`
- Causal online policy-pool logic (multiplicative-weights update, abstention-aware loss).
- Optional artifacts:
  - `online_policy_pool_grid.parquet/.csv`
  - `online_policy_pool_holdout_selection.parquet/.csv`
- Leakage accounting for the online selector (`online_policy_pool` section in `leakage_guard_report.json`).

All updates preserve no-lookahead:
- per-batch prediction uses weights from history only;
- updates occur only after observed batch outcome.

## Full run result (3500/500)

Run:
- `prediction_analysis/one_minute_target4class_pattern_outputs/20260227_194352_prod_full3500_cfg24_online_policy_pool_v1`

Holdout metrics:
- `directional_active_safe_accuracy = 0.4828`
- `opposite_fp_rate_active = 0.5172`
- `opposite_fp_rate_covered = 0.0600`
- `batches_per_signal = 8.6207`
- `pass_production_gate = false`

Leakage:
- `leakage_guard_report.json`: all sections pass (0 violations).

## Interpretation

The online policy-pool layer is implemented correctly and causal, but it does **not** improve core separability in this dataset. It mostly reorders existing threshold policies and cannot materially reduce opposite-direction risk if base router scores are weak in difficult regions.

## Next implementation (recommended)

1. **Selective-training router objective (next highest priority)**
- Train router with explicit abstention-aware objective (risk-coverage style), not just post-hoc gate search.
- Keep cost asymmetry: opposite-direction > hold > correct.

2. **Direction-conditional gating**
- Separate control for UP and DOWN active decisions, with per-direction constraints on opposite error.

3. **Online adaptive fallback weighting (DMA-style)**
- Keep dynamic low-variance fallback policy to reduce regime-shift fragility.

These are consistent with the cited literature and target the observed bottleneck (score separability), not only calibration.
