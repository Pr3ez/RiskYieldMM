# Research Continuation (2026-02-27): Training-Time Safety-Margin Selective Router

## Objective

Proceed with a training-time reject-aware router objective (not post-hoc-only threshold variants) for `1m/target_4class`.

## Research grounding (primary sources)

1. Selective prediction/reject option should be part of the learning objective, not only thresholding confidence:
- SelectiveNet: https://arxiv.org/abs/1901.09192
- Selective Classification for Deep Neural Networks: https://arxiv.org/abs/1705.08500

2. Risk control under abstention/coverage constraints:
- Conformal Risk Control: https://arxiv.org/abs/2208.02814
- Distribution-Free Risk-Controlling Prediction Sets: https://arxiv.org/abs/2101.02703

3. Nonstationary adaptation considerations:
- Conformal under Covariate Shift: https://arxiv.org/abs/1904.06019
- Online Conformal Model Selection for Nonstationary Time Series: https://arxiv.org/abs/2506.05544

4. Online abstention theory reference:
- Online Learning with Abstention: https://proceedings.mlr.press/v80/cortes18a.html

## Implemented method

File:
- `prediction_analysis/one_minute_target4class_config_activation_meta.py`

Added training-time objective variant:
- `router_target=safety_margin`
- `--safety-margin-opposite-weight`

Mechanism:
- Train model A to predict `P(correct_direction)`.
- Train model B to predict `P(opposite_direction)`.
- Construct training-time risk-aware score:
  - `score = P(correct) - λ * P(opposite)`
  - `p_hit_router = (score + λ) / (1 + λ)` clipped to `[0,1]`
- Continue standard causal thresholding/consensus and conformal risk evaluation.

This is training-time risk shaping (opposite-direction explicitly modeled), not only post-hoc threshold tuning.

## Full 3500/500 result

Run:
- `prediction_analysis/one_minute_target4class_pattern_outputs/20260227_204109_prod_full3500_cfg24_safety_margin_v1`

Holdout metrics:
- `active_batches = 0`
- `coverage = 0.0000`
- `directional_active_safe_accuracy = 0.0000`
- `opposite_fp_rate_active = 0.0000` (no active predictions)
- `opposite_fp_rate_covered = 0.0000`
- `batches_per_signal = inf`
- `pass_production_gate = false`

Leakage guard:
- pass (`0` violations)

## Interpretation

The implementation is causal/correct, but this formulation over-suppressed activation under current constraints and calibration bounds, producing no tradable signals on holdout.

## Conclusion and next move

Training-time selective objective direction is valid, but this specific safety-margin formulation is too conservative under current configuration.

Next recommended implementation:
- **Dual-head calibrated utility router**:
  - train calibrated `P(correct)` and `P(opposite)` heads,
  - optimize a direct expected utility target with bounded activation regularization,
  - enforce minimum active set during train-time model selection (avoid degenerate all-hold solutions),
  - then evaluate with the same 3500/500 protocol.
