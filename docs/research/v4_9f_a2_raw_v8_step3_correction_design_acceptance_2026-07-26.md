# Raw V8 Step-3 correction design acceptance

**Date:** 2026-07-26  
**Scope:** Raw V8 Step-3 target, lifecycle, bound, admission, and
materializability correction  
**Design verdict:** **RE-AUDIT IN PROGRESS** after a late all-field
placeholder-policy inconsistency invalidated the prior accepted bytes  
**Execution verdict:** **NO-GO** until the remaining Step-2 constructive
maxima, work certification, production-adapter, and compatibility gates plus
the Step-3 generator/verifier, runtime integration, and final-tree acceptance
all pass

## 1. Refrozen normative input under re-audit

The refrozen correction under re-audit is:

```text
path =
  docs/research/v4_9f_a2_raw_v8_step3_target_and_lifecycle_correction_2026-07-26.md
raw_octet_count = 435478
raw_sha256 =
  635952095b0b20089d5ec2c13104255ebeeff11535c8f94131a4983a1a9fec0a
repository_head_at_audit =
  4b3e9eda62c09564ce4626087383eeed9f5faea9
```

The raw SHA-256 is over exact file bytes with no newline normalization. The
prior `e935d555...` generation is superseded. Any edit to the correction
invalidates this re-audit generation and requires both audits and all
downstream hashes to be regenerated.

## 2. Independent audit result

Two independent read-only audits pinned the same correction generation:

1. The DFA/bound/admission audit covered operation/symbol namespaces,
   fixed-point and Bellman construction, metric-to-rule and rule-to-metric
   projections, emergency universal proof closure, plan dependency topology,
   dispositions, and inventory identity closure.
2. The strict schema/materializability audit covered exact-key schemas,
   nullable and array rule typing, sequence and receipt reservation,
   candidate/attempt identity amendments, no-attempt finalization, descriptor
   scoping, resource/work caps, sealed execution, artifact commands, and
   independent reproduction order.

The first audit generation exposed cumulative-work loopholes in repeated
fixed-point raw successors/tables. Successive adversarial generations then
found pre-filter cell products, finite-automaton DP/product cells, Bellman
option scans, abstract-array slots, schema/AST visits, byte operators, and
sealed-source copying that were locally but not globally bounded. Each finding
was amended before acceptance. Both final auditors independently pinned
`8d20621d...` for the cap generation. A final cross-document audit of the new
Step-2 V2 freeze then found one P0: the parser descriptor could not carry the
required logical-oracle profile binding. The descriptor gained the exact
nullable identity member and kind-safe truth rule, after which both auditors
pinned `371b407e...`. Implementation then exposed a second P0: two legal
marker-failure placeholders could not satisfy the inherited attempted-adapter
field policy. That generation added two explicit context-gated field reasons.
A later implementation audit exposed a third P0: the same placeholder rule
reused historical target-boundary and source-clock reasons that are excluded
from four of the 185 descriptors, while the historical source-clock
not-attempted form also requires `FIRST_CLOCK_READ` rather than the frozen
placeholder `NONE` phase.

The refrozen design now uses four dedicated checkpoint-only field reasons,
adds all four to every descriptor, preserves all historical reason rules, and
supersedes the closure/bound surface with an exact 26-key reason map and six
context predicates. The current correction is `63595209...`, the Step-2
freeze is `199bfd20...`, and the inherited Step-3 freeze is `40abf7d7...`.
Final independent cross-document re-audit is still required before restoring
the design verdict to accepted. No design verdict is evidence that any
required implementation or artifact exists.

## 3. Mechanical evidence

The refrozen generation currently passes:

```text
git diff --check -- \
  docs/research/v4_9f_a2_raw_v8_step3_target_and_lifecycle_correction_2026-07-26.md

code_fence_count = 490
code_fence_parity = even
```

The stale-pattern scan found no remaining active use of the removed
exact-attainment/witness admission path, Bellman `K+1` stabilization,
emergency metric diagnostic purpose, ambiguous path domain, undefined safe
uint constant, or downstream admitted-plan dependency inside the universal
certificate.

## 4. What is frozen for re-audit

The refrozen correction now specifies:

- operation-qualified symbol bounds and exact DFA/rule/finalizer semantics;
- conservative canonical symbol, edge, root, component, and full-prefix
  bounds;
- causal target-full-path then emergency-universal then emergency-metric
  certificate dependency order;
- deterministic synchronous node fixed point followed by final edge closure;
- finite-horizon Bellman bounds backed by explicit normal/emergency ranks;
- exact pre-admission emergency selection and must-execution proof domains;
- bidirectional rule/metric abstract-domain conversion;
- exact array/null/object-member rule typing and bounded suffix-result history;
- candidate/attempt admitted-plan identity linkage and receipt reservation;
- candidate-only/no-attempt finalization without fabricating target results;
- total per-operation and run-aggregate computation/artifact limits;
- fifteen exact run-total work counters covering pre-filter, retained,
  automaton, Bellman, schema/rule, byte, table, and restricted-Wasm work plus
  bounded sealed-source traversal/copying;
- canonical universe/inventory paths, sealed generator launcher, two
  independent manifest/inventory verifiers, and byte-reproduction commands.

## 5. Remaining execution gate

The next dependency is Step-2 reconciliation, not target-bound generation.
At this acceptance point:

```text
python scripts/tests/generate_raw_v8_step2_inventory_v49f.py \
  --check --repository-root .

result = FAIL
reason =
  frozen inventory differs from independently regenerated bytes
```

At this dated checkpoint, the then-current golden also predated the corrected
V2 selector, marker, observation, candidate/attempt plan-link, and related
external-type inputs required by the accepted correction. That failed check
is preserved above as historical evidence. The corrected external-schema V2
and canonical V3 inventory have since been independently accepted as narrow
components; they do not supply maxima or accept Step 2. The current mandatory
order is:

1. reconcile the parent and Step-3 lifecycle contracts with this correction;
2. construct and independently verify the 474 frozen Step-2 byte maxima and
   separate work certificates;
3. implement production adapters and re-run Step-2, Raw V7, and final-tree
   compatibility acceptance;
4. implement and independently verify the corrected Raw V8 Step-3 universe
   and bound inventory;
5. only then implement runtime lifecycle/recovery and publish Step-3 GO
   evidence.

No missing artifact is reclassified as a documentation-only task, and no
design acceptance is presented as trading profitability or predictive edge.
