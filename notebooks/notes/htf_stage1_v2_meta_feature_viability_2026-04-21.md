# HTF Stage-1-v2 Meta-Feature Viability Check

Date: 2026-04-21
Scope: `8h/B` fixed-policy replay, available completed window only
Run: `stage1_catboost_8h_b_v2_fixed_policy_pb5170_5355_live`

## Goal

Check whether combo-relationship signals are stable enough to justify building
meta-features for later winner estimation.

The candidate meta-feature families considered here are:

1. pairwise disagreement winner rules
2. peer support / agreement features
3. cluster support features

The first priority was to validate pairwise disagreement rules, because if those do not
hold up out of sample, then the conflict-edge family is not reliable enough to turn into
live decision features.

## What Was Checked

### 1. Step-level pairwise disagreement rules

For each combo pair:

- collapse each combo-step to a step-level majority predicted direction
- mark a disagreement step when the two majority directions differ
- identify which combo actually won that step using the fixed-policy step metrics
- fit the dominant side on train steps only
- test that same rule on later held-out steps

Implementation:

- [htf_stage1_v2_step_disagreement_audit.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/analysis/htf_stage1_v2_step_disagreement_audit.py)

Artifacts:

- [summary.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/stage1_v2_step_disagreement_audit_20260421_8h_b_pb5170_5355/summary.json)
- [pair_stability_summary.csv](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/stage1_v2_step_disagreement_audit_20260421_8h_b_pb5170_5355/pair_stability_summary.csv)
- [combo_meta_feature_readiness.csv](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/stage1_v2_step_disagreement_audit_20260421_8h_b_pb5170_5355/combo_meta_feature_readiness.csv)
- [step_pair_disagreements.csv](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/stage1_v2_step_disagreement_audit_20260421_8h_b_pb5170_5355/step_pair_disagreements.csv)

### 2. Out-of-sample support sanity check

Using the same step/combo frame, check whether a combo tends to perform better when more
peers share its step-level direction in train, and whether that relationship remains in
test.

This was run as a lightweight follow-up using the step-combo artifact written by the
disagreement audit.

## Data Split

- total steps: `186`
- train steps: `130`
- test steps: `56`
- pair count: `28`

The split is chronological.

## Result 1: Disagreement Coverage Is Sufficient

This part is not the problem.

- mean train disagreement steps per pair: `43.68`
- mean test disagreement steps per pair: `19.79`
- min train disagreement steps: `29`
- min test disagreement steps: `11`
- mean train disagreement rate: `0.3360`
- mean test disagreement rate: `0.3533`

So the failure is **not** caused by zero coverage. The pairs do disagree often enough to
evaluate them.

## Result 2: Pairwise Winner Rules Mostly Do Not Generalize

With a direct train/test chronological split, the train-selected dominant side does not
hold up cleanly in held-out steps.

### Hard-threshold result

Using these viability thresholds:

- train disagreement steps `>= 12`
- test disagreement steps `>= 6`
- train dominant win rate `>= 0.60`
- test rule win rate `>= 0.55`
- test Wilson lower bound `>= 0.50`

Result:

- stable useful pairs: `0 / 28`

### Why this matters

This is the strongest current warning against building conflict-edge meta-features too
early.

The mean held-out rule win rate across pairs is only `0.4698`, which is below neutral.

The implied dominant side is also unstable:

- train/test same-side pairs: `10`
- train/test opposite-side pairs: `15`
- same-side rate among non-ties: `0.40`

That means most pair rules either weaken heavily or flip direction in the held-out
window.

## Result 3: There Is One Promising Near-Miss, but It Is Not Proven Yet

Relaxing the filter to:

- train dominant win rate `>= 0.60`
- test rule win rate `>= 0.55`
- sign stable in test
- no Wilson lower-bound requirement

leaves only one pair:

| combo_a | combo_b | train dominant side | train win rate | test win rate | test disagreement steps |
| --- | --- | --- | ---: | ---: | ---: |
| `f2_v2_t10` | `f2_v3_t9` | `f2_v2_t10` | `0.6552` | `0.6364` | `11` |

This pair is interesting, but it is still too weakly supported:

- only `11` held-out disagreement steps
- Wilson lower bound is only `0.3538`

So this is a lead, not a deployable rule.

## Result 4: Peer Support Is Also Inconsistent

The simple support signal tested was:

- how many peers share the combo’s majority direction on a step

What matters is whether more support in train still implies better step outcome in test.

That relationship was inconsistent.

Examples:

- `f2_v1_t5`: train support effect negative, test positive
- `f2_v2_t10`: train positive, test slightly negative on directional proxy
- `f2_v2_t8`: train slightly positive, test strongly negative
- `f2_v2_t4`: train negative, test strongly negative

This means support is not behaving like a stable global confidence feature.

At minimum it would have to be:

- combo-specific
- trained only on past steps
- revalidated on later windows

## Result 5: The Relationship Structure Is Only Partially Stable

There is some stability in who disagrees with whom:

- train/test disagreement-rate correlation across pairs: `0.533`

So the structure of disagreement is not random.

But the direction of pairwise advantage is much less stable:

- same-side dominance only `40%` of non-tied pairs

This is the key distinction:

- structural relationship map: somewhat real
- actionable winner rule from that map: not yet reliable

## What This Means For Meta-Features

### What does make sense now

It still makes sense to **collect** candidate meta-features for later evaluation:

- peer support count / rate
- pairwise conflict edge score
- cluster support score
- disagreement breadth
- support-weighted trust scores

These can be logged as exploratory features.

### What does **not** make sense yet

It does **not** make sense yet to assume these signals are ready for winner estimation
logic or hard-coded selection rules.

Current evidence says:

- raw pairwise disagreement rules are mostly unstable
- simple consensus/support signals are not consistently predictive
- one promising pair exists, but sample size is too small

## Current Decision

On the currently available `186` completed fixed-policy steps:

- relationship analysis is useful descriptively
- meta-feature construction is reasonable as a research direction
- but there is **not yet enough stable out-of-sample evidence** to rely on these
  features for winner estimation

So the correct stance right now is:

- **keep collecting data**
- **do not hard-wire these signals yet**
- **re-run the same audit on the full 500-step fixed-policy window**

## What Should Be Checked Next On The 500-Step Window

The next validation pass should require:

1. at least some pairs with both:
   - held-out disagreement steps comfortably above `20`
   - held-out Wilson lower bound above `0.50`
2. materially better than neutral held-out pair-rule win rates
3. support signals that keep the same sign from train to test
4. combo-specific meta-feature behavior that remains consistent after the sample grows

Only after that should we move from descriptive audits to a real meta-selector design.

## Practical Recommendation

When the full `500`-step `8h/B` fixed-policy replay is ready:

1. rerun the step disagreement audit
2. rerun the support stability audit
3. only then decide whether to:
   - build a train-only meta-feature frame
   - or drop/limit the relationship family because it is too unstable

## Artifacts

- [htf_stage1_v2_step_disagreement_audit.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/analysis/htf_stage1_v2_step_disagreement_audit.py)
- [summary.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/stage1_v2_step_disagreement_audit_20260421_8h_b_pb5170_5355/summary.json)
- [pair_stability_summary.csv](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/stage1_v2_step_disagreement_audit_20260421_8h_b_pb5170_5355/pair_stability_summary.csv)
- [combo_meta_feature_readiness.csv](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/stage1_v2_step_disagreement_audit_20260421_8h_b_pb5170_5355/combo_meta_feature_readiness.csv)
- [step_combo_metrics.csv](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/stage1_v2_step_disagreement_audit_20260421_8h_b_pb5170_5355/step_combo_metrics.csv)
- [step_pair_disagreements.csv](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/stage1_v2_step_disagreement_audit_20260421_8h_b_pb5170_5355/step_pair_disagreements.csv)

