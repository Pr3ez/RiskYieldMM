# HTF Stage-1-v2 Pairwise Prediction Audit

Date: 2026-04-20
Scope: selected fixed-policy predictions only
Run: `stage1_catboost_8h_b_v2_fixed_policy_pb5170_5355_live`

## Goal

Build a pairwise relationship map between the 8 fixed-policy combos for the completed
`8h/B` available-step window, then check whether combo agreement/disagreement can help
estimate which combo is more trustworthy on a given step.

This audit uses the persisted per-row selected prediction files written under each
`batch_*/stage1_v2/` directory. It does not rely on the root-level resumed run summary.

## Coverage

- steps: `186`
- prediction rows per step: `240`
- total shared prediction rows: `44,640`
- combos: `8`
- pairwise combo relations: `28`

## Direction Mapping

The active `target_4class` directional split is the same one used elsewhere in the
walkforward diagnostics:

- classes `< 2` => down-direction
- classes `>= 2` => up-direction

Metrics in this note:

- `direction_agreement_rate`: same predicted direction on the same row
- `class_agreement_rate`: same exact class on the same row
- `conflict_dir_edge_a_minus_b`: on rows where the two combos predict opposite
  directions, directional accuracy of combo A minus directional accuracy of combo B

## Main Result

There is a usable relationship map here, but it is **not** a simple “follow consensus”
story.

- Average pairwise directional agreement is moderately high: `0.6341`
- Average pairwise exact-class agreement is much lower: `0.4347`
- Average opposite-direction rate is still large: `0.3659`

So the combos often agree on direction, but still disagree often enough for pairwise
conflict behavior to matter.

The practical implication is:

- agreement structure can help rank trust
- conflict behavior can help identify which combo tends to win disagreements
- but consensus alone is not enough, because some combos benefit from consensus while
  others do not

## Strongest Alignment Pairs

| combo_a | combo_b | direction_agreement_rate | class_agreement_rate | note |
| --- | --- | ---: | ---: | --- |
| `f2_v2_t10` | `f2_v3_t9` | `0.7227` | `0.5615` | strongest aligned pair |
| `f2_v1_t5` | `f2_v1_t6` | `0.7031` | `0.5377` | strong same-family alignment |
| `f2_v2_t8` | `f2_v3_t9` | `0.6923` | `0.5078` | aligned cluster with `f2_v2_t10` |
| `f2_v2_t10` | `f2_v2_t8` | `0.6923` | `0.5057` | aligned cluster with `f2_v3_t9` |
| `f2_v1_t3` | `f2_v1_t5` | `0.6892` | `0.4848` | aligned, but conflict edge favors `f2_v1_t5` |

This gives one obvious directional cluster:

- `f2_v2_t10`
- `f2_v2_t8`
- `f2_v3_t9`

## Weakest Alignment / Most Separate Pairs

| combo_a | combo_b | direction_agreement_rate | class_agreement_rate |
| --- | --- | ---: | ---: |
| `f2_v1_t3` | `f2_v3_t9` | `0.5376` | `0.3137` |
| `f2_v1_t3` | `f2_v2_t10` | `0.5666` | `0.3480` |
| `f2_v3_t9` | `f7_v1_t4` | `0.5702` | `0.3425` |
| `f2_v2_t10` | `f7_v1_t4` | `0.5712` | `0.3656` |
| `f2_v1_t3` | `f2_v2_t8` | `0.5915` | `0.3767` |

These are the pairs where disagreement information is most likely to be useful.

## Conflict Winners

Weighted by the number of conflict rows against all other combos, the best disagreement
winners are:

| action_key | weighted_conflict_dir_edge_vs_others | mean_direction_agreement_rate | interpretation |
| --- | ---: | ---: | --- |
| `f2_v1_t5` | `0.0601` | `0.6585` | strongest overall disagreement winner |
| `f2_v2_t4` | `0.0526` | `0.6281` | also wins conflicts consistently |
| `f2_v1_t6` | `0.0364` | `0.6487` | milder positive conflict edge |
| `f2_v1_t3` | `-0.0052` | `0.6189` | near neutral to slightly losing |
| `f7_v1_t4` | `-0.0184` | `0.6247` | mild conflict loser |
| `f2_v2_t10` | `-0.0212` | `0.6332` | mild conflict loser |
| `f2_v2_t8` | `-0.0294` | `0.6386` | moderate conflict loser |
| `f2_v3_t9` | `-0.0676` | `0.6224` | strongest overall conflict loser |

Most important pairwise conflict edges:

| winner_side | loser_side | conflict_rows | winner_edge |
| --- | --- | ---: | ---: |
| `f2_v1_t5` | `f2_v3_t9` | `17,431` | `+0.1032` |
| `f2_v2_t4` | `f2_v3_t9` | `17,669` | `+0.0997` |
| `f2_v1_t6` | `f2_v3_t9` | `16,958` | `+0.0882` |
| `f2_v1_t5` | `f7_v1_t4` | `14,506` | `+0.0739` |
| `f2_v1_t5` | `f2_v2_t8` | `16,623` | `+0.0732` |

This matters operationally: if later live logic sees `f2_v1_t5` disagreeing with
`f2_v3_t9`, history in this window says the `f2_v1_t5` side has had a clear
directional edge.

## Does Peer Support Improve Accuracy?

This is the critical part for later “trust by map” logic.

For each combo, I measured whether step-level directional accuracy rises when its
predictions are supported by more peers.

### Combos that benefit from peer support

| action_key | corr_support_vs_step_direction_accuracy | majority_supported_dir_accuracy_lift |
| --- | ---: | ---: |
| `f2_v1_t3` | `0.0665` | `+0.0661` |
| `f2_v3_t9` | `0.0358` | `+0.0327` |
| `f2_v2_t8` | `0.0117` | `+0.0046` |
| `f2_v1_t6` | `-0.0077` | `+0.0279` |
| `f2_v1_t5` | `-0.0103` | `+0.0561` |

The correlation is weak, but the majority-vs-split lift is still useful for
`f2_v1_t3`, `f2_v1_t5`, and `f2_v3_t9`.

### Combos that do **not** benefit from peer support

| action_key | corr_support_vs_step_direction_accuracy | majority_supported_dir_accuracy_lift |
| --- | ---: | ---: |
| `f2_v2_t10` | `0.0695` | `-0.0051` |
| `f7_v1_t4` | `-0.0596` | `-0.0481` |
| `f2_v2_t4` | `-0.0781` | `-0.0636` |

This is the most important warning from the audit:

- peer agreement is **not** universally good
- for `f2_v2_t4` and `f7_v1_t4`, the combo is often more useful when it is less aligned
  with the pack

So any later meta-selector must be **combo-specific**, not a single global consensus
rule.

## Practical Interpretation

The relationship map is useful, but only if we use it carefully.

Useful now:

- build a pairwise trust graph
- detect aligned clusters
- learn which combo tends to win when two combos disagree on direction
- use combo-specific support rules instead of a single consensus rule

Not safe yet:

- blindly choosing the combo with the most peer agreement
- assuming the strongest cluster is the most accurate cluster
- assuming this same-window descriptive map is live-safe without train-only calibration

## Recommended Next Use

The best next step is to convert this descriptive audit into a train-only meta-feature
set for winner estimation:

1. For each combo on each step, compute:
   - peer direction support
   - peer exact-class support
   - weighted conflict edge against currently disagreeing peers
   - cluster support from historically aligned peers only
2. Train/evaluate the meta-selector only on past steps.
3. Compare that against the current winner-selection flow.

That would turn this audit from a descriptive map into a live-usable trust estimator.

## Artifacts

- `test_output/stage1_v2_pairwise_prediction_audit_20260420_8h_b_pb5170_5355/summary.json`
- `test_output/stage1_v2_pairwise_prediction_audit_20260420_8h_b_pb5170_5355/pairwise_prediction_relationships.csv`
- `test_output/stage1_v2_pairwise_prediction_audit_20260420_8h_b_pb5170_5355/direction_agreement_matrix.csv`
- `test_output/stage1_v2_pairwise_prediction_audit_20260420_8h_b_pb5170_5355/class_agreement_matrix.csv`
- `test_output/stage1_v2_pairwise_prediction_audit_20260420_8h_b_pb5170_5355/conflict_direction_edge_matrix.csv`
- `test_output/stage1_v2_pairwise_prediction_audit_20260420_8h_b_pb5170_5355/per_combo_conflict_advantage.csv`
- `test_output/stage1_v2_pairwise_prediction_audit_20260420_8h_b_pb5170_5355/per_combo_support_bucket_summary.csv`
- `test_output/stage1_v2_pairwise_prediction_audit_20260420_8h_b_pb5170_5355/per_combo_step_support_summary.csv`
- `test_output/stage1_v2_pairwise_prediction_audit_20260420_8h_b_pb5170_5355/per_combo_support_correlation.csv`

