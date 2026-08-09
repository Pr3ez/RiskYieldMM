# Raw V8 Step-2 maximum protocol V1 feasibility rejection

Date: 2026-08-02  
Status: **ACCEPTED REJECTION OF PROTOCOL V1 — RAW V8 STEP 2 REMAINS NO-GO**

## Decision

`riskyieldmm.raw_v8_step2_external_schema_v2.maximum_protocol.v1` cannot enter
its six-case pilot or production maximum generation. Its verifier-derived
pre-search coordinate catalog exceeds three immutable seed limits on one pinned
intrinsic row before a producer, solver, frontier, certificate, or witness is
read.

This accepts a falsification result, not a constructive maximum, Raw V8 Step-2
acceptance, A2-M completion, production readiness, or Stage 1 exit.

## Bound authorities

| Authority | Bound identity |
|---|---|
| Rejected V1 protocol | 246,093 UTF-8 octets; physical SHA-256 `b3b39b3cb15caa450d9974925db9b5f0b91dd5832a462d2a8687dc19a50c4409` |
| External Schema V2 registry | 1,469,663 octets; physical SHA-256 `9160297ff316c5931737c92f8b359f0a1e2ec22f0aa996ef3b09cf830dc96bf3`; semantic ID `5dc95a3e99c5646e912b6a7e9c3970cf2489d560ea890b0a19d38af4c51c2140` |
| Canonical V3 inventory | physical SHA-256 `f33c1019afa7f49a316aac1bfbef7498e240f391e4fee00dfd95fdcda658669f`; semantic ID `128d07a45dc2300c140f333cc3a45e2497aaa4089684f6e44da048ab403bbf9d` |

The executable audit securely reads and physically pins the first two files.
The V3 identity remains predecessor context; the failing row is intrinsic and
therefore has no profile or source-inventory authority capable of fixing its
payload.

## Independent lower-bound derivation

The registry's expanded intrinsic row order places `TargetFieldRegistryV1` at
row 62. It is descriptor 48 and type 24 in the correction document's
descriptive type list; those three positions are different namespaces and must
not be conflated.

The exact descriptor path is:

```text
TargetFieldRegistryV1.descriptors
  member_position = 11
  ARRAY, nullable = false
  minimum_items = maximum_items = 185
  item = non-null OBJECT_REF CapacityMeasurementTargetFieldDescriptorV1

CapacityMeasurementTargetFieldDescriptorV1.value_shape_keys
  member_position = 14
  ARRAY, nullable = false
  minimum_items = 0
  maximum_items = 512
  item = non-null TEXT

TEXT language
  language_kind = BUILTIN
  built_in_language_kind = RAW_CANONICAL_JSON_STRING
  ordering_semantics = UNICODE_SCALAR_LEXICOGRAPHIC
  ordered_literals = []
```

The V1 emission grammar requires a coordinate for every variable array
cardinality and expands item occurrences through the descriptor maximum. A
noncatalog text language with at least two legal values emits `TEXT_VALUE`.
Therefore every one of the 185 fixed outer items contributes at least:

```text
1 ARRAY_CARDINALITY + 512 TEXT_VALUE = 513 coordinates
```

and the complete row has this strict lower bound:

```text
inner array-cardinality coordinates = 185
inner text coordinates              = 185 * 512 = 94,720
component coordinate lower bound    = 185 * 513 = 94,905
```

This deliberately does not count any other member, nested observer, rule,
application, or scope coordinate. It is a lower bound, not an estimate.

## Why substitution cannot remove it

The row's constraint scope is `INTRINSIC_TYPE`; its profile and source
inventory are null. The `value_shape_keys` values are payload used to derive
the registry identity, not values derived from that identity. Treating the
identity as authority for its own payload would reverse causality.

V1 also states that `authority_substituted_plan_domain` must not depend on
intrinsic/application truth, codec survival, witness bytes, frontier contents,
solver output, or producer evidence. Rule-based pruning therefore cannot be
used to reduce this pre-search catalog. The raw canonical JSON string language
is not a singleton or finite literal catalog.

## Cap contradiction

V1 requires one later prefix proof node for every plan coordinate. Those nodes
form a one-child chain, while leaf depth starts at one. V1 freezes:

```text
SEED_EXECUTION_SAFETY_LIMITS_V1.component_choice_coordinate_count = 65,536
SEED_EXECUTION_SAFETY_LIMITS_V1.proof_node_count                   = 65,536
SEED_EXECUTION_SAFETY_LIMITS_V1.maximum_proof_depth                = 65,536
```

The lower bound violates all three before any other component is counted:

```text
component coordinates             = 94,905  (excess 29,369)
total proof nodes                 >= 94,906  (excess at least 29,370)
maximum proof depth               >= 94,906  (excess at least 29,370)
```

The prefix-only `94,905` proof-node count remains a valid conservative lower
bound. The `94,906` total includes the minimum one leaf/base node required by
the protocol's depth convention.

### Stronger independent cross-check

Intrinsic row 17,
`CapacityMeasurementLocalShutdownResultEvidenceV2`, contains four
`NESTED_PAYLOAD` arrays with maximum cardinality 524,288 and a fifth with
maximum cardinality 4,096. Their items are non-null `LOWERCASE_SHA256` text
references. The intrinsic rule consumes all five arrays, and rejected V1
Section 10 explicitly optimizes every array, content, and identity. They are
therefore source choices rather than identities locally derived from the same
payload.

One large array alone forces:

```text
1 ARRAY_CARDINALITY + 524,288 TEXT_VALUE = 524,289 coordinates
```

All five arrays force at least:

```text
4 * 524,289 + 4,097 = 2,101,253 coordinates
```

The corresponding prefix chain also exceeds the 1,048,576 proof-edge cap.
This cross-check is not needed for the decision; row 62 remains the primary,
least-disputable rejection proof.

Final ceilings must be no greater than their seed limits. Pilot measurement,
rounding, or final rebind therefore cannot repair V1. Silently raising a cap
would change the protocol and require a new seed cycle; it would not turn this
V1 candidate into an accepted protocol.

## Implementation disposition

Retain as reusable, non-accepting verifier foundations:

- pinned authority loading and canonical identity checks;
- the exact 52-type/236-value-schema graph;
- the independently reconstructed 408-profile, 475-case scope hierarchy;
- exact synthetic scope-plan materialization and locator derivation;
- causal recurrence grammars and certificate-owned atomic resource meter;
- adversarial mutation and deterministic no-go infrastructure.

Stop and replace:

- production integration of the V1 one-prefix-node-per-coordinate chain;
- V1 winner-digest completion work that exists only to authenticate that chain;
- the V1 six-case pilot and any guarded publication path;
- final rebinding or maximum-witness generation under the V1 protocol hash.

The dormant pilot files remain absent. The maximum validator must continue to
fail closed and report the accepted rejection, not a candidate awaiting pilot.

## V2 design requirements

The replacement must retain the safety obligation:

```text
independently checked upper bound
= compact-canonical length of one independently validated legal witness
```

It must separate that obligation from the optional preference for one globally
least witness among multiple equal-length maxima. A pinned legal attainer is
sufficient for the byte-bound safety claim unless a separate requirement can
show why global leastness is operationally necessary.

V2 must:

1. use a new protocol version and physical pin;
2. derive plan/occurrence authority without producer evidence;
3. avoid one serialized proof node per global tie-break coordinate;
4. use streaming or batched verification for repeated schema occurrences;
5. preflight exact counts before allocation and keep atomic meter semantics;
6. preserve complete intrinsic/application legality and safe-relaxation checks;
7. validate one attaining witness independently from its producer;
8. define deterministic artifact publication separately from maximum proof;
9. run negative controls, cap-boundary tests, protocol-shift tests, and a
   full-row preflight before any pilot is authorized; and
10. remain NO-GO if even the compact proof cannot fit immutable file/work caps.

## Executable evidence

Audit:

```text
scripts/tests/audit_raw_v8_step2_maximum_protocol_v1_feasibility_v49f.py
```

Focused tests:

```text
tests/test_raw_v8_step2_maximum_protocol_v1_feasibility_v49f.py
```

Verified command:

```bash
python scripts/tests/audit_raw_v8_step2_maximum_protocol_v1_feasibility_v49f.py \
  --repository-root .
python -m pytest -q \
  tests/test_raw_v8_step2_maximum_protocol_v1_feasibility_v49f.py
```

Observed result:

```text
audit_result = PASS
protocol_decision = REJECTED
component_choice_coordinate_lower_bound = 94,905
prefix_proof_node_lower_bound = 94,905
tie_break_proof_node_lower_bound = 94,906
maximum_proof_depth_lower_bound = 94,906
coordinate cap excess = 29,369
node/depth cap excess = 29,370
31 passed
```

The audit is deterministic and machine-readable. Its authority-shape
adversaries reject changed descriptor position, member/type role, outer
cardinality, inner cardinality, item language, and raw-string parameters.
Physical pin drift and special-file substitution reject before semantic use.

## Gate state

Raw V8 Step 2 remains **NO-GO**. Immediate work moves from V1 semantic-kernel
completion to V2 compact-proof design, independent feasibility preflight, and
only then a replacement pilot. Step 3, production adapters, Raw V7 final-tree
compatibility, later A2-M campaigns, and every later Stage 1 gate remain
downstream and closed.
