# HTF Stage-1-v2 Class Disagreement Viability

Date: 2026-04-21
Scope: exact-class step-level disagreement viability on the completed `8h/B` fixed-policy window
Run: `stage1_catboost_8h_b_v2_fixed_policy_pb5170_5355_live`

## Goal

Check whether exact-class disagreement is more useful than directional disagreement for
later combo-relationship meta-features.

The previous viability check used only step-level majority direction disagreement. This
follow-up reruns the same train/test logic using step-level majority exact class:

- classes: `0, 1, 2, 3`
- step collapse: majority predicted class per combo-step
- disagreement: majority class differs

## Implementation

The existing audit script was extended to support:

- `--disagreement-mode direction`
- `--disagreement-mode class`

File:

- [htf_stage1_v2_step_disagreement_audit.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/analysis/htf_stage1_v2_step_disagreement_audit.py)

Artifacts:

- [summary.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/stage1_v2_step_class_disagreement_audit_20260421_8h_b_pb5170_5355/summary.json)
- [pair_stability_summary.csv](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/stage1_v2_step_class_disagreement_audit_20260421_8h_b_pb5170_5355/pair_stability_summary.csv)
- [combo_meta_feature_readiness.csv](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/stage1_v2_step_class_disagreement_audit_20260421_8h_b_pb5170_5355/combo_meta_feature_readiness.csv)

For direct comparison, the refreshed directional run is here:

- [summary.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/stage1_v2_step_direction_disagreement_audit_20260421_8h_b_pb5170_5355/summary.json)

## Coverage Comparison

| mode | mean train disagreement rate | mean test disagreement rate | mean train disagreement steps per pair | mean test disagreement steps per pair |
| --- | ---: | ---: | ---: | ---: |
| direction | `0.33599` | `0.35332` | `43.68` | `19.79` |
| class | `0.50824` | `0.56250` | `66.07` | `31.50` |

Exact-class disagreement gives much better coverage.

This is a real improvement because pairwise rules have more chances to be evaluated and
do not fail due to sparse conflicts.

## Stability Comparison

| mode | stable useful pairs | mean held-out rule win rate | train/test same-side rate |
| --- | ---: | ---: | ---: |
| direction | `0 / 28` | `0.46975` | `0.40` |
| class | `0 / 28` | `0.50782` | `0.56` |

Exact-class disagreement is **better** than directional disagreement by all three of
these broad indicators:

- higher held-out rule win rate
- better same-side stability
- more disagreement coverage

But it still does **not** cross the threshold for being reliable enough.

## Best Exact-Class Near-Miss

The strongest class-level candidate remains:

| combo_a | combo_b | train dominant side | train win rate | test win rate | test Wilson lower bound | test disagreement steps |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| `f2_v2_t10` | `f2_v3_t9` | `f2_v2_t10` | `0.6136` | `0.6000` | `0.4074` | `25` |

This is better than the directional version of the same pair:

| mode | train win rate | test win rate | test disagreement steps | test Wilson lower bound |
| --- | ---: | ---: | ---: | ---: |
| direction | `0.6552` | `0.6364` | `11` | `0.3538` |
| class | `0.6136` | `0.6000` | `25` | `0.4074` |

Interpretation:

- class mode gives more support
- the apparent edge is slightly weaker in raw win rate
- but statistically it is more credible than the directional version

It is still not enough to pass the current viability bar.

## What This Means

### Exact-class disagreement is more promising than directional disagreement

That part is clear.

The current data says class mode is the better candidate if we want to continue
exploring combo-relationship meta-features.

### But it is still not strong enough yet

Under the current thresholds:

- train dominant win rate `>= 0.60`
- test rule win rate `>= 0.55`
- test Wilson lower bound `>= 0.50`

the result is still:

- stable useful pairs: `0 / 28`

So the correct conclusion is not “use class mode now.”
The correct conclusion is:

- if this research direction survives, it will most likely survive through
  exact-class disagreement rather than direction-only disagreement
- but the currently completed `186` steps are still not enough to trust the rules

## Practical Recommendation

For the next full-window check on the `500`-step fixed-policy replay:

1. rerun the audit in both modes
2. treat class mode as the primary candidate
3. require at least some pairs with:
   - meaningful held-out disagreement count
   - held-out win rate above neutral
   - Wilson lower bound near or above `0.50`
4. only then consider turning pairwise class-conflict structure into train-only
   meta-features

## Bottom Line

Is exact-class disagreement useful?

- **more useful than directional disagreement:** yes
- **already strong enough to trust for meta-features:** no

So the audit result is:

- keep this direction alive
- prioritize class-level relationship features over direction-only ones
- wait for the full `500`-step fixed-policy window before deciding whether it is real

