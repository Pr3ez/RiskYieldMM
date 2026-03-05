# Research Continuation (2026-02-27): Direction-Conditional Selective Thresholds

## Goal

Continue improving risk-first directional routing for `1m/target_4class` with strict no-lookahead behavior, focusing on reducing opposite-direction errors while keeping operational cadence.

## Research basis (primary sources)

1. Selective classification / reject-option framing supports abstain-vs-act decisions under risk constraints.  
   - SelectiveNet: https://arxiv.org/abs/1901.09192  
   - Selective Classification for Deep Neural Networks: https://arxiv.org/abs/1705.08500

2. Risk/coverage control is formalized in conformal risk control and related selective prediction methods.  
   - Conformal Risk Control: https://arxiv.org/abs/2208.02814  
   - Distribution-Free Risk-Controlling Prediction Sets: https://arxiv.org/abs/2101.02703

3. Under nonstationarity/covariate shift, weighted conformal and online model-selection are preferred over static calibration assumptions.  
   - Conformal under Covariate Shift: https://arxiv.org/abs/1904.06019  
   - Online Conformal Model Selection for Nonstationary Time Series: https://arxiv.org/abs/2506.05544

4. Abstention should be optimized as a policy objective, not only post-hoc thresholding.  
   - Online Learning with Abstention: https://proceedings.mlr.press/v80/cortes18a.html

## Implemented method

File:
- `prediction_analysis/one_minute_target4class_config_activation_meta.py`

Added:
- `--use-directional-thresholds`
- `--directional-threshold-grid`
- direction-conditional gating function `_selection_by_batch_directional_threshold(...)`
- train/selection sweep over `(threshold_up, threshold_down, consensus_k)`
- holdout application using selected `activation_threshold_up` and `activation_threshold_down`

Correctness constraints:
- no-lookahead preserved (same walk-forward semantics)
- leakage guard remains active for per-config/router stages
- online policy-pool mode cannot be combined with directional-threshold mode in this version (explicit validation)

## Full run result (3500/500)

Run:
- `prediction_analysis/one_minute_target4class_pattern_outputs/20260227_201502_prod_full3500_cfg24_directional_thresholds_v1`

Holdout metrics:
- `directional_active_safe_accuracy = 0.4933`
- `opposite_fp_rate_active = 0.5067`
- `opposite_fp_rate_covered = 0.0760`
- `batches_per_signal = 6.6667`
- `active_batches = 75`
- `pass_production_gate = false`

Best selected operating point in this run:
- `consensus_k = 4`
- `threshold_up = 0.20`
- `threshold_down = 0.25`

## Delta interpretation

Compared to patched conformal baseline (`20260227_192500...phaseB_patched`), directional-threshold v1 is worse on all primary risk-first metrics:
- lower safe directional accuracy
- higher opposite-direction active error
- higher opposite-direction covered error
- more aggressive cadence (too many signals)

## Conclusion

Direction-conditional thresholds are implemented correctly and causally, but they do not resolve the core separability issue in this dataset.

## Next implementation recommendation

Prioritize **selective-training router objective** (training-time reject/abstain-aware loss) with direction-conditional risk penalties, rather than adding more post-hoc threshold structure. This is the next method most aligned with both observed failure mode and literature.
