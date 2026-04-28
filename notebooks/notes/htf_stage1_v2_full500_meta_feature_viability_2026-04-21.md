# HTF Stage-1-v2 Full-500 Meta-Feature Viability

Date: 2026-04-21
Scope: full fixed-policy `8h/B` replay window
Run: `stage1_catboost_8h_b_v2_fixed_policy_pb5170_5669_live`

## Goal

Repeat the combo-relationship audits on the completed full `500`-step fixed-policy
window and compare the result against the earlier partial `186`-step window.

The key question remains the same:

- do combo agreement/conflict structures generalize well enough to justify building
  meta-features for later winner estimation?

## Runs Audited

- earlier partial window: `5170..5355` (`186` steps)
- full window: `5170..5669` (`500` steps)

The full fixed-policy replay is complete and contains `500` `stage1_v2_step_summary.json`
files.

## Artifacts

Full-window pairwise relationship audit:

- [summary.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/stage1_v2_pairwise_prediction_audit_20260421_8h_b_pb5170_5669/summary.json)
- [per_combo_conflict_advantage.csv](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/stage1_v2_pairwise_prediction_audit_20260421_8h_b_pb5170_5669/per_combo_conflict_advantage.csv)

Full-window step-level train/test audits:

- [direction summary.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/stage1_v2_step_direction_disagreement_audit_20260421_8h_b_pb5170_5669/summary.json)
- [direction pair_stability_summary.csv](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/stage1_v2_step_direction_disagreement_audit_20260421_8h_b_pb5170_5669/pair_stability_summary.csv)
- [class summary.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/stage1_v2_step_class_disagreement_audit_20260421_8h_b_pb5170_5669/summary.json)
- [class pair_stability_summary.csv](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/stage1_v2_step_class_disagreement_audit_20260421_8h_b_pb5170_5669/pair_stability_summary.csv)

Earlier-window comparison references:

- [186-step direction summary.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/stage1_v2_step_direction_disagreement_audit_20260421_8h_b_pb5170_5355/summary.json)
- [186-step class summary.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/stage1_v2_step_class_disagreement_audit_20260421_8h_b_pb5170_5355/summary.json)

## Descriptive Pairwise Map: Full 500 Steps

### Global relationship metrics

- mean direction agreement: `0.6281`
- mean exact-class agreement: `0.4301`
- mean opposite-direction rate: `0.3719`

Compared with the `186`-step window:

- direction agreement fell slightly: `0.6341 -> 0.6281`
- class agreement fell slightly: `0.4347 -> 0.4301`
- opposite-direction rate rose slightly: `0.3659 -> 0.3719`

So the larger sample did not simplify the combo structure. If anything, it showed
slightly more disagreement.

### Current strongest directional alignment pairs

| combo_a | combo_b | direction_agreement_rate | class_agreement_rate |
| --- | --- | ---: | ---: |
| `f2_v1_t5` | `f2_v1_t6` | `0.7181` | `0.5380` |
| `f2_v1_t5` | `f2_v2_t4` | `0.7039` | `0.5178` |
| `f2_v2_t10` | `f2_v3_t9` | `0.6931` | `0.5284` |
| `f2_v2_t10` | `f2_v2_t8` | `0.6898` | `0.5274` |
| `f2_v2_t8` | `f2_v3_t9` | `0.6673` | `0.4852` |

### Conflict-advantage leaders changed

In the `186`-step window, the descriptive disagreement winners were:

- `f2_v1_t5`
- `f2_v2_t4`
- `f2_v1_t6`

In the full `500`-step window they are now:

- `f2_v2_t4` (`+0.0644` weighted edge)
- `f2_v2_t10` (`+0.0210`)
- `f2_v2_t8` (`+0.0111`)

This change matters. It means the descriptive conflict hierarchy is not stable enough to
be trusted as a hard rule yet.

## Train/Test Viability: 500 Steps

Chronological split:

- train steps: `350`
- test steps: `150`

### Direction mode

Headline:

- mean train disagreement rate: `0.3390`
- mean test disagreement rate: `0.3288`
- mean held-out rule win rate: `0.5169`
- same-side train/test dominance rate: `0.6667`
- stable useful pairs under the current thresholds: `0 / 28`

This is materially better than the earlier `186`-step directional audit:

- mean held-out rule win rate improved from `0.4698 -> 0.5169`
- same-side dominance improved from `0.40 -> 0.6667`

But it is still not enough. No pair clears the current viability bar.

Best directional near-misses:

| combo_a | combo_b | train dominant side | train win rate | test win rate | test Wilson lower bound |
| --- | --- | --- | ---: | ---: | ---: |
| `f2_v1_t5` | `f2_v2_t4` | `f2_v2_t4` | `0.5641` | `0.5814` | `0.4333` |
| `f2_v1_t3` | `f2_v1_t6` | `f2_v1_t6` | `0.5085` | `0.5745` | `0.4328` |
| `f2_v1_t3` | `f2_v2_t4` | `f2_v2_t4` | `0.5042` | `0.5636` | `0.4327` |

The held-out win rates are above neutral, but the train-side dominance is still too weak
or the Wilson lower bound is still too low.

### Exact-class mode

Headline:

- mean train disagreement rate: `0.5197`
- mean test disagreement rate: `0.5305`
- mean held-out rule win rate: `0.4919`
- same-side train/test dominance rate: `0.6154`
- stable useful pairs under the current thresholds: `0 / 28`

This is the critical reversal relative to the `186`-step audit.

Earlier, exact-class mode looked more promising than direction mode.
With the full `500` steps, that advantage disappeared:

- class mean held-out rule win rate fell from `0.5078 -> 0.4919`
- direction mean held-out rule win rate rose from `0.4698 -> 0.5169`

So on the fuller sample, **direction mode is now the better of the two**, even though
neither is strong enough.

### The earlier best class pair degraded

On the `186`-step window, the best class near-miss was:

- `f2_v2_t10` vs `f2_v3_t9`
- train win rate `0.6136`
- test win rate `0.6000`

On the full `500`-step window, the same pair becomes:

- train win rate `0.6081`
- test win rate `0.5094`
- test Wilson lower bound `0.3788`

That is exactly the kind of degradation we needed the larger sample to detect.

## What The Full 500 Steps Tell Us

### 1. The descriptive map is still real

There are persistent relationship structures:

- aligned clusters still exist
- disagreement coverage is strong
- combo behavior is not random

So continuing to log these descriptors is still justified.

### 2. But the actionable rule set is still not reliable

The bigger sample did not produce any pair that satisfies the current stability bar.

That is the main decision point.

If the extra `314` steps had created even a small set of stable useful pairs, the
meta-feature direction would have become much more credible. That did not happen.

### 3. The exact-class story weakened

This is probably the most important new finding.

With the smaller sample, class-level disagreement looked more promising than
direction-only disagreement.

With the larger sample, that does not hold anymore.

So we should not currently privilege class-level conflict logic as the default next step.

### 4. Direction mode improved, but still not enough

The only real improvement from the full window is that direction-mode train/test
consistency is better than before.

But “better than before” is not the same as “ready to use.”

## Bottom Line

After repeating the audit on the full `500`-step fixed-policy window:

- **yes**, the relationship map is worth keeping as a descriptive diagnostic
- **no**, it still does not justify turning support/conflict agreement into actual
  winner-estimation meta-features
- **no**, the full `500` steps did not validate the earlier class-level promise

Current best conclusion:

- keep these audits as diagnostics
- do not build winner-selection logic around them yet
- if meta-features are pursued later, they need a different source of stable signal than
  the current pairwise disagreement rules alone

