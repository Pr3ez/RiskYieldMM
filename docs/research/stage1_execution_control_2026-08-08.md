# Stage 1 execution control

**Control date:** 2026-08-09
**Formal Stage 1 state:** `NO-GO`
**Active implementation gate:** `S1-A3` — freeze final V2 protocol and F1/F2
authority, then repeat the accepted dual preflight
**Offline Stage 2:** blocked on `S1-R0`
**Paper/live activation:** blocked on `S1-X`

This is the current execution pointer for the remaining Stage 1 work. It
organizes, but does not replace, the normative protocol freezes and dated
acceptance records. When a dated status paragraph disagrees with this file,
use this file for current sequencing and use the original record for what its
specific checkpoint proved.

## Resume card

| Question | Current answer |
|---|---|
| What is accepted? | Foundations `S1-F1` through `S1-F4`, corrected V2 seed `S1-A1`, and independent dual feasibility preflight `S1-A2` |
| What is active? | `S1-A3` only |
| What is the next bounded action? | `A3-T`: add fail-first tests for the canonical finalization manifest, all 36 mechanically derived F2 values, source/evidence drift rejection, resource bounds, and atomic output |
| What closes `S1-A3`? | Final authority and limit identities frozen; A, B, and comparator rerun without semantic or limit tuning; deterministic evidence and scoped leftover audit captured |
| What follows? | `S1-A4` constructive maximum producer/verifier evidence; separately, `S1-D1` can be activated later to reach offline-only readiness `S1-R0` |
| What remains blocked? | Offline Stage 2 until `S1-R0`; paper/live activation until complete exit `S1-X` |

Resume from `A3-T`; do not reopen accepted `S1-A1`/`S1-A2` unless a pinned
source, identity, result, or invariant actually drifts. Do not start the
constructive producer, verifier, or pilot during `S1-A3`.

## 1. Why Stage 1 stalled

The work did not stop because there was no useful implementation. It stalled
because its control structure allowed a prerequisite to expand without a
bounded closure packet:

1. current status was repeated across many dated documents instead of owned by
   one mutable execution ledger;
2. accepted predecessor evidence, fail-first design tests, and current gate
   acceptance were too easy to read as the same kind of progress;
3. independent reviews were started while the seed candidate was still
   changing, so valid review findings created another design layer before a
   stable candidate existed;
4. no per-section byte budget stopped identity-bound profile data from being
   repeated across templates, programs, and case bindings;
5. the generator and generated catalog diverged, leaving tests to compare new
   contracts with an old artifact;
6. the Raw V8/A2 live-evidence path and the offline event/label/split path were
   treated as one serial queue even though the roadmap permits offline Stage 2
   after the latter is independently accepted; and
7. the large mixed worktree makes it difficult to recognize a coherent,
   reproducible checkpoint.

The correction is procedural as well as technical: freeze the queue, finish
one acceptance packet, and make every downstream task wait on an explicit
gate rather than on an informal sense that the design is nearly complete.

## 2. Two readiness milestones

Stage 1 retains one final exit, but it now exposes two different milestones.

### `S1-R0` — offline research readiness

This milestone accepts the causal decision-event, information-cutoff,
eligibility, label-maturity, interval-aware split, and conservative cost
scenario contracts. It permits Stage-2 **offline baseline experiments only**.
It does not permit forward paper trading, venue interaction, production
promotion, or a live-readiness claim.

### `S1-X` — complete Stage 1 exit

This milestone additionally requires Raw V8/A2 correctness, independently
derived evidence, operational qualification, governance/order/fill authority,
provider and clock evidence, campaigns, replay/live parity, and the final
adversarial audit. Only this milestone can unblock paper/live activation.

This separation prevents the maximum-proof work from indefinitely blocking
honest offline baselines while preserving the original live-safety boundary.

## 3. Gate-state and WIP rules

Allowed states are `ACCEPTED`, `ACTIVE`, `READY`, `WAITING`, `HOLD`, and
`REJECTED`.

- There must be exactly one `ACTIVE` mutable implementation gate.
- At most one additional read-only independent audit may run against frozen
  bytes. It may not edit the candidate it reviews.
- A downstream gate cannot become `READY` until every dependency is
  `ACCEPTED`.
- Fail-first tests belong to one gate only. They must not be treated as
  repository acceptance evidence.
- A review begins only after the candidate, source manifest, commands, and
  expected identities are frozen.
- Every work session must either reduce a recorded failure/size gap, produce a
  required acceptance artifact, or record a falsification. More prose without
  one of those outcomes is not progress.
- After two consecutive closure cycles that do not reduce a gate's measured
  blocker, move it to `HOLD` and write a bounded replan. Do not add another
  protocol layer.
- No silent weakening of caps, causal cutoffs, independence, or fail-closed
  behavior is allowed to make a gate pass. Such a change requires a new
  versioned authority and re-review.
- A gate closes only with code, deterministic commands, captured results,
  independent evidence where required, updated current-status documentation,
  and a scoped leftover/worktree review.

## 4. Canonical gate ledger

| Gate | State | Depends on | Required output and acceptance boundary |
|---|---|---|---|
| `S1-F1` causal ledger and local transport foundation | `ACCEPTED` | — | Historical V3 through V4.9E bounded-local checkpoints; retain their explicit nonclaims |
| `S1-F2` bounded transport admission | `ACCEPTED` | `S1-F1` | V4.9F-A1 bounded admission checkpoint |
| `S1-F3` manifest and lifecycle evidence | `ACCEPTED` | `S1-F2` | Raw V6 authority and Raw V7 failure/cancellation lifecycle sub-gates |
| `S1-F4` Step-2 schema/runtime/inventory prerequisites | `ACCEPTED` | `S1-F3` | External Schema V2 components, V1 rejection, compact-proof correction, and V4 inventory; no constructive-maximum claim |
| `S1-A1` executable V2 seed closure | `ACCEPTED` | `S1-F4` | Corrected full-case subject/cardinality, unit-context, local-selector, and per-kernel transition-expansion authority; deterministic corrected acceptance |
| `S1-A2` dual 475-case feasibility preflight | `ACCEPTED` | `S1-A1` | Two independent counting-only implementations agree exactly on every metric and case within immutable F0 ceilings |
| `S1-A3` final V2 freeze | `ACTIVE` | `S1-A2` | Freeze protocol bytes and F1/F2 limits; repeat both preflights against the frozen authority |
| `S1-A4` constructive maximum evidence | `WAITING` | `S1-A3` | Independent verifier, separate producer, six-case pilot, 474 maximum results, and the local-shutdown result |
| `S1-A5` Raw V8 Step-2 exit | `WAITING` | `S1-A4` | Separate work accounting/certification, production differential adapters, final Raw V7 compatibility, independent acceptance |
| `S1-A6` Raw V8 Step-3 lifecycle | `WAITING` | `S1-A5` | Re-audited target-span/finite grammar followed by projection, lineage, replay, recovery, and remaining lifecycle implementation |
| `S1-A7` correctness artifact pipeline | `WAITING` | `S1-A6` | Physical normalizer and fixture oracles, evidence-derived finalizer, campaign isolation, and atomic publisher |
| `S1-A8` A2 measurement and enforcement | `WAITING` | `S1-A7` | Matched neutrality/workload evidence, independent calibration/confirmation, threshold freeze, A2-E, and fresh regression/audit |
| `S1-D1` causal offline experiment contract | `READY` | `S1-F1` | One DecisionEvent/eligibility rule, exact information cutoff, independent labels, label maturity, interval-aware splits, and conservative cost scenarios |
| `S1-D2` completed-bar and instrument authority | `WAITING` | `S1-D1` | First-seen provider status, deterministic completed 1m→HTF derivation, freshness/revision rules, and point-in-time futures mappings |
| `S1-D3` promotion and quarantine boundary | `WAITING` | `S1-D1`, `S1-D2` | Cross-lineage promotion, stale/synthetic/non-tradable exclusion, artifact rebuild, and legacy shadow migration |
| `S1-R0` offline research readiness | `WAITING` | `S1-D1` | Independent acceptance record permits Stage-2 baselines only; no paper/live authority |
| `S1-O1` governance/order/fill bridge | `WAITING` | `S1-A6`, `S1-D1` | Atomic H1/H2/intent/outbox and non-bypassable governance, order, and fill authority |
| `S1-O2` operational qualification | `WAITING` | `S1-A7`, `S1-D2` | Provider/certificate, systemd/chronyd/VM, crash/storage, saturation, fairness, scale, and long no-trading campaigns |
| `S1-O3` replay/live parity and external audit | `WAITING` | `S1-A8`, `S1-D3`, `S1-O1`, `S1-O2` | Operational raw replay/live parity, reconciliation, complete incident disposition, and independent adversarial review |
| `S1-X` complete Stage 1 exit | `WAITING` | `S1-A8`, `S1-D3`, `S1-O3` | Every Stage-1 acceptance criterion closes on one frozen tree; public-live and profitability remain separate claims |

The machine-readable state below is checked by
`scripts/tests/check_stage1_execution_control.py`.

<!-- STAGE1_CONTROL_JSON_START
{
  "active_gate": "S1-A3",
  "control_version": 1,
  "formal_stage1_state": "NO-GO",
  "gate_states": {
    "S1-A1": {"depends_on": ["S1-F4"], "state": "ACCEPTED"},
    "S1-A2": {"depends_on": ["S1-A1"], "state": "ACCEPTED"},
    "S1-A3": {"depends_on": ["S1-A2"], "state": "ACTIVE"},
    "S1-A4": {"depends_on": ["S1-A3"], "state": "WAITING"},
    "S1-A5": {"depends_on": ["S1-A4"], "state": "WAITING"},
    "S1-A6": {"depends_on": ["S1-A5"], "state": "WAITING"},
    "S1-A7": {"depends_on": ["S1-A6"], "state": "WAITING"},
    "S1-A8": {"depends_on": ["S1-A7"], "state": "WAITING"},
    "S1-D1": {"depends_on": ["S1-F1"], "state": "READY"},
    "S1-D2": {"depends_on": ["S1-D1"], "state": "WAITING"},
    "S1-D3": {"depends_on": ["S1-D1", "S1-D2"], "state": "WAITING"},
    "S1-F1": {"depends_on": [], "state": "ACCEPTED"},
    "S1-F2": {"depends_on": ["S1-F1"], "state": "ACCEPTED"},
    "S1-F3": {"depends_on": ["S1-F2"], "state": "ACCEPTED"},
    "S1-F4": {"depends_on": ["S1-F3"], "state": "ACCEPTED"},
    "S1-O1": {"depends_on": ["S1-A6", "S1-D1"], "state": "WAITING"},
    "S1-O2": {"depends_on": ["S1-A7", "S1-D2"], "state": "WAITING"},
    "S1-O3": {"depends_on": ["S1-A8", "S1-D3", "S1-O1", "S1-O2"], "state": "WAITING"},
    "S1-R0": {"depends_on": ["S1-D1"], "state": "WAITING"},
    "S1-X": {"depends_on": ["S1-A8", "S1-D3", "S1-O3"], "state": "WAITING"}
  },
  "live_activation_state": "BLOCKED",
  "offline_stage2_state": "BLOCKED",
  "seed_snapshot": {
    "catalog_raw_octets": 13419905,
    "catalog_sha256": "a75a2f352e8513b7ff0043693a0c65ebbf4bc6f06859354789af69e1162b0e4f",
    "catalog_stale": false,
    "focused_failed": 0,
    "focused_passed": 108,
    "generator_sha256": "47b4ecada8c661185e4087787b99e113b2366ff87ee06e951a21a85b9a4cab4f",
    "operational_headroom_octets": 2308735,
    "operational_output_maximum_octets": 15728640,
    "prospective_raw_octets": 13419905,
    "prospective_seed_catalog_id": "ac22151fa74702ac1488924f01161eaa38574545e6272a290db6b0bbd288ae5f",
    "prospective_sha256": "a75a2f352e8513b7ff0043693a0c65ebbf4bc6f06859354789af69e1162b0e4f",
    "strict_individual_file_upper_octets": 16777216
  }
}
STAGE1_CONTROL_JSON_END -->

## 5. Accepted packet: `S1-A1`

The corrected seed acceptance is
[`v4_9f_a2_raw_v8_step2_maximum_protocol_v2_seed_correction_acceptance_2026-08-09.md`](v4_9f_a2_raw_v8_step2_maximum_protocol_v2_seed_correction_acceptance_2026-08-09.md),
as amended by
[`v4_9f_a2_raw_v8_step2_v2_event_metadata_amendment_2026-08-09.md`](v4_9f_a2_raw_v8_step2_v2_event_metadata_amendment_2026-08-09.md).
Earlier byte identities remain predecessor evidence only.

| Observation | Accepted value |
|---|---:|
| Stored and regenerated seed catalog | 13,419,905 bytes |
| Raw SHA-256 | `a75a2f352e8513b7ff0043693a0c65ebbf4bc6f06859354789af69e1162b0e4f` |
| Seed semantic ID | `ac22151fa74702ac1488924f01161eaa38574545e6272a290db6b0bbd288ae5f` |
| Operational target | `<= 15,728,640` bytes |
| Operational headroom | 2,308,735 bytes |
| Strict individual-file bound | `< 16,777,216` bytes |
| Focused serialized/security matrix | 108 passed, 0 failed |
| Catalog staleness | false |

The correction reduced the measured closure blocker from `1 passed, 3 failed`
to `21 passed, 0 failed`. It binds all 18 transition expansions, every one of
the 16 subject constructors, exact variable cardinalities, ordinary/local unit
contexts, and local endpoint selectors. Fixed-byte probes cover an ordinary
leaf bundle and the complete local 12-state/11-transition tagged-subject
bundle. The amendment additionally binds every event emission to an exact
subject role, ordinal policy, observed-value policy, and ordinary/null step
source. No 475-case expected result vector was added.

## 6. Accepted packet: `S1-A2`

`S1-A2` contains exactly two independent,
counting-only 475-case preflights and their comparator. It must not reuse the
seed generator, import the other preflight, generate witnesses, tune limits,
or change semantics. If either implementation exceeds F0 or they disagree,
the outcome is a falsification and returns to a versioned correction—not a
locally patched limit.

The shared data-only boundary is frozen by
[`v4_9f_a2_raw_v8_step2_v2_preflight_boundary_freeze_2026-08-09.md`](v4_9f_a2_raw_v8_step2_v2_preflight_boundary_freeze_2026-08-09.md)
under contract ID
`6609ad7b9abf21432136e49af178e20c17cb7bc27d3b444a4b6f01a17073fc76`.
It passed 13 boundary/hostile tests and contains no expected case vector.

| S1-A2 packet | Current status | Exit condition |
|---|---|---|
| `A2-B0` shared boundary | `FROZEN` | Input/report/error/resource/import contracts identity-bound |
| `A2-A` iterative counter | `ACCEPTED` | Frozen 475-case candidate payload; 6 focused tests pass; candidate vector still requires B agreement |
| `A2-B` flat-ledger counter | `ACCEPTED` | 6 focused tests pass; complete 1,702,217-byte payload agrees exactly with A |
| `A2-C` isolated comparator | `ACCEPTED` | Parent-owned wait4/resource evidence and durable `EXACT_AGREEMENT` payload |
| `S1-A2-E` final preflight acceptance | `ACCEPTED` | Frozen sources/results/commands, fresh regression, and read-only acceptance record |

`S1-A2-E` is a packet-local label. It is not the transport-wide A2-E
enforcement milestone owned by `S1-A8`.

Ordered work:

1. **Complete:** freeze the read-only seed input, result schema, error taxonomy,
   resource capture boundary, and import-deny policy shared by the comparator;
2. **Complete:** implement and freeze preflight A as an iterative catalog
   interpreter with no generator import and no witness construction;
3. **Complete:** implement preflight B from the same frozen bytes using a
   separately authored traversal/counting architecture and no import from
   preflight A;
4. **Complete:** compare all 475 ordered case records, every one of the 18 exact metrics,
   status, plan identity, and final aggregate identity;
5. **Complete:** enforce the immutable F0 time, CPU, RSS, temporary-storage, and result-size
   ceilings for both isolated runs;
6. **Complete:** reject missing/duplicate/reordered cases, altered metric values or types,
   differing failures, source drift, forbidden imports, and partial output;
7. **Complete:** freeze exact commands, results, resource evidence, and an independent
   read-only acceptance record before activating `S1-A3`.

No verifier, producer, pilot, maximum result, work-accounting implementation,
production adapter, or Step-3 implementation is authorized before `S1-A2` and
`S1-A3` close.

The accepted A2-A packet is
[`v4_9f_a2_raw_v8_step2_v2_preflight_a_acceptance_2026-08-09.md`](v4_9f_a2_raw_v8_step2_v2_preflight_a_acceptance_2026-08-09.md).
Its candidate semantic payload ID is
`d51f81fe078309ee817a4f7ab93be3891ef4fbb5aab45e41b8e0d60ce3103c1b`;
this value was independently reproduced by B and was not a shared expected
vector. The accepted A2-B packet is
[`v4_9f_a2_raw_v8_step2_v2_preflight_b_acceptance_2026-08-09.md`](v4_9f_a2_raw_v8_step2_v2_preflight_b_acceptance_2026-08-09.md).
Parent-owned resource enforcement and durable comparison are accepted by
[`v4_9f_a2_raw_v8_step2_v2_preflight_comparator_acceptance_2026-08-09.md`](v4_9f_a2_raw_v8_step2_v2_preflight_comparator_acceptance_2026-08-09.md).
The combined acceptance and fresh regression decision is frozen by
[`v4_9f_a2_raw_v8_step2_v2_dual_preflight_acceptance_2026-08-09.md`](v4_9f_a2_raw_v8_step2_v2_dual_preflight_acceptance_2026-08-09.md).

## 7. Active packet: `S1-A3`

S1-A3 must freeze one final identity-bound V2 protocol and its F1/F2 limits
from the accepted S1-A1/S1-A2 bytes, then repeat A, B, and the comparator
against that final authority. It may not tune a limit, change counting
semantics, or begin verifier/producer/pilot work. Any changed byte requires an
explicit versioned delta and reacceptance rather than silent absorption.

The initial S1-A3 audit rejected the historical in-place Markdown patch because
the accepted consumers hard-pin the unchanged machine seed. The selected
two-component final authority and ordered sub-gates are frozen in
[`v4_9f_a2_raw_v8_step2_v2_final_freeze_design_correction_2026-08-09.md`](v4_9f_a2_raw_v8_step2_v2_final_freeze_design_correction_2026-08-09.md).
The seed remains the semantic component; a new canonical finalization manifest
will bind the phase/status, accepted evidence, and mechanically rounded F2
limits. `A3-T` fail-first tests are next.

The exit packet must contain the final protocol/limit identities, exact source
manifest, regenerated no-drift evidence, both semantic results, comparator
result, immutable commands, and a scoped leftover audit.

## 8. Parallel queue without semantic collision

While `S1-A3` is active, `S1-D1` remains the only other `READY` gate. It may
receive read-only audit and test-design work, but it cannot become a second
mutable implementation gate. If `S1-A2` enters `HOLD` under the two-cycle rule,
record the replan and explicitly activate `S1-D1`; do not leave both active.

Closing `S1-D1` and its independent acceptance milestone `S1-R0` is the shortest
safe route to Stage-2 offline baselines. It is not a shortcut around the live
activation work.

## 9. Resume and reporting routine

At the start of every Stage-1 session:

```bash
git status --short --branch
python scripts/tests/check_stage1_execution_control.py
python scripts/tests/generate_raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.py --check
pytest -q \
  tests/test_raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.py \
  tests/test_raw_v8_step2_maximum_protocol_v2_local_state_v49f.py \
  tests/test_raw_v8_step2_maximum_protocol_v2_recurrence_v49f.py \
  tests/test_raw_v8_step2_maximum_protocol_v2_profile_conditioning_v49f.py \
  tests/test_raw_v8_step2_maximum_protocol_v2_cell_transfer_v49f.py \
  tests/test_raw_v8_step2_maximum_protocol_v2_event_grammar_v49f.py \
  tests/test_raw_v8_step2_maximum_protocol_v2_full_case_execution_closure_v49f.py \
  tests/test_raw_v8_step2_maximum_protocol_v2_preflight_contract_v49f.py \
  tests/test_raw_v8_step2_maximum_protocol_v2_source_security_v49f.py \
  tests/test_raw_v8_step2_maximum_protocol_v2_preflight_a_v49f.py \
  tests/test_raw_v8_step2_maximum_protocol_v2_preflight_b_v49f.py \
  tests/test_raw_v8_step2_maximum_protocol_v2_preflight_comparator_v49f.py
```

The originally accepted 108-test seed matrix plus the 13 later
boundary/security tests must remain green. A, B, and the comparator must also
remain green on their frozen hashes. Any generator, grammar, seed, contract,
source, result, or input-identity drift blocks S1-A3; it must not be absorbed
silently into the final freeze.

At the end of every session, report only:

1. active gate and state;
2. blocker metric before and after;
3. artifacts changed;
4. commands and exact results;
5. new decisions or falsifications;
6. next single bounded action; and
7. unrelated and unresolved worktree leftovers.

## 10. Nonclaims

This control state accepts the V2 seed and the dual all-case feasibility
preflight only. It does not accept the final V2 freeze, a constructive maximum,
Raw V8 Step 2 or Step 3, transport-wide A2-M/A2-E, Stage 1, provider behavior,
completed-bar authority, paper/live readiness, predictive edge, trading
safety, or profitability.
