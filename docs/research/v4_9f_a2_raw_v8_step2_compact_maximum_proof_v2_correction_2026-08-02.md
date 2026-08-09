# Raw V8 Step-2 compact maximum-proof V2 correction

Date: 2026-08-02  
Status: **ACCEPTED NORMATIVE CORRECTION — IMPLEMENTATION REMAINS NO-GO**

## 1. Decision and scope

This document defines the accepted successor correction to the rejected
`riskyieldmm.raw_v8_step2_external_schema_v2.maximum_protocol.v1` proof shape.
It changes only the proof and publication requirements for the Raw V8 Step-2
constructive byte maxima and the separate local-shutdown minimality result. It
does not change:

- the 52-node External Schema V2 graph;
- its 49 concrete records and three finite unions;
- the 236 value schemas, 42 rules, eight applications, or two resolvers;
- the 408 V3 maximum-constraint scope profiles;
- the 474 required maximum rows or their order;
- any production codec ceiling; or
- the requirement that each accepted maximum have a completely legal attaining
  witness.

This document is now an accepted normative design authority. Raw V8 Step 2
remains **NO-GO** until the V3 inventory is superseded by an accepted V4
inventory, a counting-only full-row feasibility preflight passes under
immutable limits, and a separately frozen V2 protocol and independent
implementation pass their acceptance matrix.

## 2. Why V1 is rejected

The accepted V1 feasibility rejection physically pins the rejected protocol
and registry and independently derives this unavoidable lower bound from
intrinsic row 62, `TargetFieldRegistryV1`:

```text
185 fixed descriptors
* (1 variable value_shape_keys cardinality + 512 text occurrences)
= 94,905 pre-search choice coordinates
```

V1 requires a prefix proof node for every coordinate. Its immutable seed limits
permit at most 65,536 component coordinates, 65,536 proof nodes, and proof
depth 65,536. Even before any other member or base node is counted, row 62
therefore requires at least:

```text
component coordinates             = 94,905
total proof nodes                 >= 94,906
maximum proof depth               >= 94,906
```

The violations are respectively 29,369, at least 29,370, and at least 29,370.
The stronger intrinsic row-17 cross-check contains four arrays with maximum
cardinality 524,288 and one with maximum 4,096. Once their event-reference
members are classified under the pinned `NESTED_PAYLOAD` roles and the V1 rule
that all five arrays and contents are optimized, those arrays alone require at
least 2,101,253 coordinates. That also exceeds V1's 1,048,576 proof-edge cap.
Row 62 remains the primary rejection proof because it is sufficient and has no
classification ambiguity.

The seed caps cannot be repaired by a pilot or final rounding rule. Raising
them would define another protocol. Continuing V1 winner-digest,
per-coordinate evidence, or prefix-chain implementation is prohibited.

## 3. Narrow normative supersession

This document supersedes only the following parts of
`v4_9f_a2_raw_v8_step2_external_schema_v2_correction_2026-07-28.md`:

1. Section 2's statement that the exact V3 schema literal and four-input array
   are the sole authority, only to the extent replaced by Section 12's explicit
   V4 schema literal, five-input order, and migration rules;
2. the Section 11 row member `ordered_component_choice_evidence`;
3. Section 11.3's second and third optimization objectives that globally
   minimize measured-record and constructed-context primitive vectors;
4. Section 11's requirement that every attainable-length gap, residue, and
   per-position choice be serialized rather than independently recomputed;
5. the requirement for one supporting proof-node position per primitive
   coordinate;
6. the V1 maximum-witness, upper-bound-certificate, resource, context-object,
   context-page, context-manifest, row-manifest, and proof identity versions;
7. Section 13's V1 proof-verification steps and Section 14's V1 protocol
   migration step;
8. Section 16's V1 maximum-witness/proof artifact paths and required files;
9. Section 17 gate 3's narrow V3 correction-byte refreeze and gates 4–5's V1
   proof protocol/artifact requirements, replacing them with the V4/V2 order in
   Sections 12–13 here;
10. acceptance-matrix clauses that exist only to prove the removed global
   leastness objective or authenticate its coordinate-prefix chain; and
11. the migration instruction that the already accepted correction document
   itself must be edited in place; and
12. Section 12's V1 `ordered_proof_nodes` encoding for the otherwise preserved
   local-shutdown minimality objective.

The following requirements remain binding:

- maximize compact-canonical measured witness byte length over the complete
  legal constraint scope;
- prove independently that no legal value is longer;
- retain and independently validate a legal witness that attains that bound;
- preserve exact descriptor, rule, application, identity, Unicode, codec,
  context-closure, filesystem, and resource semantics;
- keep analytic maxima distinct from production codec admission ceilings;
- keep solver/generator and verifier implementations independent; and
- keep the local-shutdown minimality question separate from byte maximization.

This successor is an additive normative authority rather than an in-place edit
to an accepted historical file. Its accepted physical identity must
be added to a versioned V4 inventory as a new role. The predecessor correction
remains byte-stable evidence of the earlier decision.

The amendment contains no final V2 protocol hash. This ordering is mandatory:
the V4 inventory binds the amendment, then the separate V2 protocol binds the
accepted V4 inventory and amendment. Making the inventory bind a protocol that
itself binds the inventory would create an impossible hash cycle.

The second successor will be a separate
`v4_9f_a2_raw_v8_step2_constructive_maximum_protocol_v2_freeze_<date>.md`.
It is not an inventory input. It must pin the accepted V4 inventory, this
amendment, registry, literal/Unicode/canonicalization authorities, exact
derivation and recurrence catalogs, file/work/resource limits, and every V2
identity schema. Validators and artifacts then pin that protocol's final
physical SHA-256.

## 4. Exact maximum theorem

For each pinned constraint scope `s`, let:

```text
x   = (measured witness, complete legality context)
D_s = the complete set of legal witness-context pairs under the authorities
L(x) = compact-canonical length of the exact measured typed path within x
U_s = the upper bound independently derived by the V2 verifier
W_s = the retained candidate witness-context pair
```

The V2 verifier may accept a mathematical maximum only after establishing all
three premises:

```text
P1  W_s is an element of D_s.
P2  For every x in D_s, L(x) <= U_s.
P3  L(W_s) = U_s.
```

Then, directly:

```text
max_{x in D_s} L(x) = U_s = L(W_s).
```

If the verifier proves `D_s` is a subset of a relaxed domain `R_s` and proves
`L(r) <= U_s` for every `r` in `R_s`, P2 remains sound. It need not prove that
`U_s` is itself the exact maximum of `R_s`. The candidate still passes only if
a fully legal `W_s` attains `U_s`; a loose relaxation that produces an
unattainable upper endpoint cannot be accepted.

No global leastness premise is needed for this theorem. Two different legal
witnesses may both attain the same exact maximum. Mathematical acceptance and
artifact publication are therefore distinct decisions.

## 5. Trust and independence boundary

The producer may propose a witness, context closure, and diagnostic search
output. It may not supply an authoritative upper bound, recurrence,
relaxation direction, state partition, cache key, resource count, or proof
plan.

The independent verifier must:

- import neither the generator/solver nor `riskyieldmm`;
- reconstruct the legal domain from physically pinned normative files, the
  accepted V4 inventory, the registry, and literal/Unicode authorities;
- derive the upper-bound recurrence and every cache key itself;
- parse candidate files only through bounded, no-follow, regular-file reads;
- derive the complete resource claim from observed verifier events;
- validate the witness and context from retained bytes;
- recompute every semantic identity and canonical measurement; and
- fail closed if an exact upper bound, attaining witness, or complete
  accounting result is unavailable.

The verifier also may not invoke a producer through a subprocess, inspect
producer reflection or annotations, or treat producer-generated Python/code as
an authority.

The verifier is the proof checker. A producer transcript, solver assertion,
opaque proof payload, or certificate field that merely repeats `U_s` is not a
proof.

## 6. Upper-bound phase

### 6.1 Verifier-derived problem

Before reading any candidate row, the verifier derives every one of the 474
publication rows and 475 verifier-owned scope cases:

- the exact measured root and owner relationship;
- all descriptor and union domains;
- all reachable intrinsic rules;
- the exact root/application schedule;
- every V4-carried, V3-profile-preserving authority substitution;
- the complete set of ancestor-observable rule states;
- the exact compact-canonical syntax contribution; and
- all codec and owner ceilings.

Values fixed by accepted authority pointers are resolved from retained pinned
bytes. Semantic IDs and hashes remain consequences of payloads, never reverse
lookup authorities for their own payload.

### 6.2 Exact recurrence

The preferred core is a bounded dynamic program over a finite state signature.
Each state key must include every property that can affect an ancestor rule,
application, identity, codec, or canonical length. At minimum, as applicable,
the key contains:

```text
descriptor/value-schema position
occurrence and array ordinal
union branch and nullable state
relevant cardinalities and boundary values
rule-visible equality/order/normalization summaries
identity dependency state
owner and root-profile position
application invocation and observation ordinal
canonical syntax boundary state
```

Transitions combine exact compact length with these semantic summaries.
Repeated independent occurrences may use a batched recurrence only when the
verifier proves it is equivalent to the corresponding unbatched transition
sequence. Batching may reduce retained states and serialized evidence; it must
not erase occurrence, boundary, rule, or identity distinctions.

The exact algebra is protocol-owned. The implementation must not assume that a
simple scalar `(max,+)` recurrence is sufficient when rules observe additional
state. A product state may use maximum length as one component only after all
observable semantic components are present in the key.

### 6.3 Safe relaxation

A relaxation is permitted only through a closed protocol enum whose direction
the verifier establishes as domain enlargement. Examples may include dropping
a constraining predicate or replacing a coupled legal set with a documented
superset. The relaxed domain must retain the exact measured typed path,
canonicalization, owner/nested codec ceilings, and serialization semantics. The
following reject:

- narrowing a domain;
- using a witness, producer frontier, or solver result to choose the relaxed
  domain;
- merging states whose distinction is read by any ancestor;
- treating a derived identity as authority for the payload that derives it;
- assuming an unproved monotonicity relation; or
- accepting a relaxed upper bound that the legal witness does not attain.

The certificate records the ordered relaxation rule IDs used, but the verifier
derives that list. Unknown or producer-selected relaxations reject.

### 6.4 Independent differential challengers

Small finite schemas must be exhaustively enumerated and compared with the V2
recurrence. A separately encoded pseudo-Boolean or SMT optimization may be
used as a bounded differential challenger. It is not the production proof core
unless its translation, proof format, checker, and resource closure receive a
separate acceptance. A commitment or Merkle tree can bind a large artifact but
does not by itself prove an optimization bound.

## 7. Attainment and legality phase

After deriving `U_s`, the verifier loads the proposed witness and required
context closure and independently performs:

1. strict bounded I-JSON decoding and canonical round-trip;
2. exact structural and scalar/value-schema validation;
3. pinned Unicode normalization/profile validation;
4. union, nullable, array-cardinality, and owner-dispatch validation;
5. every reachable intrinsic rule in dependency order;
6. every required cross-record application in the exact V3 schedule;
7. all semantic identity and reference recomputation;
8. production codec relation and owner-ceiling validation;
9. exact measured compact-canonical length and SHA-256 recomputation; and
10. equality `measured_length == U_s`.

An invalid witness of the correct byte length rejects. A legal witness of
length `U_s - 1` rejects. A correct producer claim with a verifier-derived
different `U_s` rejects. No probability, heuristic confidence, or tolerance is
allowed.

## 8. V2 artifact schemas

### 8.1 Mathematical maximum row

Every V2 row uses the new scope-ID domain:

```text
RiskYieldMMA2MStep2ExternalSchemaV2MaximumConstraintScopeV2V4_9F_RawV8
```

over the unchanged predecessor payload order:

```text
constraint_scope
measured_type_name
alternative_name
measurement_binding
constraint_scope_profile_id
external_schema_registry_id
rule_literal_authority_sha256
maximum_protocol_sha256
source_inventory_sha256
evaluation_semantics
```

The six measurement-binding forms and evaluation-semantics literal remain
exactly those in predecessor Section 11.2. Intrinsic rows retain null profile
and source-inventory fields; non-intrinsic rows bind the accepted V4 semantic
inventory ID and one unchanged profile ID.

The row version becomes:

```text
riskyieldmm.raw_v8_step2_external_schema_v2.maximum_attainer.v2
```

The V2 row has exactly these members in this order; V1
`ordered_component_choice_evidence` is absent:

```text
artifact_version
canonicalization_version
measurement_schema_version
maximum_protocol_sha256
source_inventory_sha256
external_schema_registry_id
rule_literal_authority_sha256
type_name
alternative_name | null
constraint_scope
constraint_scope_id
constraint_scope_profile_id | null
witness_kind
canonical_byte_length
certified_analytic_maximum_octets
codec_byte_bound_relation
codec_octet_limit
codec_slack_octets
canonical_sha256
witness_record
scope_witness_context | null
required_context_object_count
ordered_required_context_object_ids
row_context_closure_id
upper_bound_certificate
proof_resource_report
maximum_attainer_id
```

`witness_kind` is
`INDEPENDENTLY_VALIDATED_LEGAL_MAXIMUM_ATTAINER`. The three exact lengths agree:

```text
canonical_byte_length
= certified_analytic_maximum_octets
= upper_bound_certificate.certified_upper_bound_octets
```

The null intrinsic `source_inventory_sha256` rule applies only inside the
constraint-scope identity payload. Every row-level `source_inventory_sha256`
equals the accepted V4 semantic inventory identity, including intrinsic rows;
it is artifact provenance and does not enlarge `D_s`. The row-context-closure
identity payload uses that same V4 value.

The V2 `maximum_attainer_id` covers every preceding member under a new domain.
It identifies one accepted attainer; it does not claim to be the globally least
attainer or the publication-selected attainer.

`ordered_required_context_object_ids` is strictly increasing by lowercase
semantic ID and contains every and only recursively required `CONTEXT_OBJECT`
reference reachable from `scope_witness_context`; it excludes the inline
witness and V4 authority pointers. The count equals its length. The row closure
ID domain is:

```text
RiskYieldMMA2MStep2ExternalSchemaV2MaximumRowContextClosureV2V4_9F_RawV8
```

over exactly:

```text
maximum_protocol_sha256
source_inventory_sha256
constraint_scope_id
required_context_object_count
ordered_required_context_object_ids
```

The mathematical row deliberately does not bind a global context-object
manifest. This permits two equal legal attainers with different exact per-row
closures to remain independently valid before publication.

The row ID domain is:

```text
RiskYieldMMA2MStep2ExternalSchemaV2MaximumAttainerV2V4_9F_RawV8
```

### 8.2 Compact upper-bound certificate

The certificate version and ID domain become:

```text
riskyieldmm.raw_v8_step2_external_schema_v2.upper_bound_certificate.v2
RiskYieldMMA2MStep2ExternalSchemaV2UpperBoundCertificateV2V4_9F_RawV8
```

Its exact member order is:

```text
certificate_version
maximum_protocol_sha256
derivation_scope_id
upper_bound_mode
derivation_catalog_id
derivation_plan_id
ordered_safe_relaxation_rule_ids
certified_upper_bound_octets
streamed_derivation_result_sha256
upper_bound_certificate_id
```

`upper_bound_mode` is exactly `EXACT_LEGAL_DOMAIN` or
`LEGAL_DOMAIN_SUPERSET_WITH_LEGAL_ATTAINMENT`. The verifier derives every field
other than the pinned scope/protocol reference, reruns the bounded recurrence,
and compares the candidate. The streamed digest binds the verifier's canonical
derivation result but is never accepted without recomputation. The certificate
contains no coordinate catalog, primitive choice vector, prefix proof node,
frontier transcript, winner digest, supporting proof-node position, or resource
claim. `upper_bound_certificate_id` covers every preceding member in the order
shown.

For an ordinary maximum row,
`derivation_scope_id = constraint_scope_id`. For the local prospective proof,
`derivation_scope_id = local_shutdown_proof_scope_id`, and the derivation domain
masks exactly the frozen outer
`CapacityMeasurementOperationResultEvidence LT 524288` codec coordinate while
retaining every other schema, scalar, intrinsic, identity, signed-spec, and
operational relation.

### 8.3 Separate proof-resource report

Resource evidence has its own version and identity:

```text
riskyieldmm.raw_v8_step2_external_schema_v2.maximum_proof_resource_report.v2
RiskYieldMMA2MStep2ExternalSchemaV2MaximumProofResourceReportV2V4_9F_RawV8
```

Its exact members are:

```text
resource_report_version
maximum_protocol_sha256
derivation_scope_id
derivation_plan_id
derivation_certificate_id
resource_limit_catalog_id
ordered_resource_measurements
proof_resource_report_id
```

The verifier derives the ordered measurements from observed atomic events and
checks them against the already frozen limit catalog. Keeping the report
outside the certificate prevents certificate length/hash/resource identity
from recreating V1's self-referential fixed point. Certificate/report raw
octets and hash-preimage bytes are bounded by their containing artifact layer.

The semantic proof meter closes before resource-report serialization. The
report never charges its own encoding, ID preimage, or hash. Certificate,
report, row, and containing-file bytes are checked by the row/publication
layers only after their final bytes exist. `proof_resource_report_id` covers
every preceding member in the order shown.

### 8.4 Context closure

The bounded local context-object architecture remains required because complete
constructed records are needed for legality and cannot fit inline in the known
full-67 root case. Candidate rows may be checked in a bounded non-authoritative
staging root; their identities are path-independent and bind only their exact
per-row object IDs. After row selection, publication unions and deduplicates
those IDs and builds the exact accepted V2 closure paths:

```text
tests/raw_v8_step2_external_schema_v2_maximum_attainers_v2_v49f/
  context_object_manifest.json
  context_object_manifest_pages/<six-digit-one-based-page-position>.json
  context_objects/<first-two-lowercase-id-characters>/<maximum-context-object-id>.json
  rows/<first-two-lowercase-id-characters>/<maximum-attainer-id>.json
```

The context-object identity payload remains exactly:

```text
maximum_protocol_sha256
source_inventory_sha256
external_schema_registry_id
rule_literal_authority_sha256
record_type_name
record_identity_field
record_identity
record_canonical_byte_length
record_canonical_sha256
record
```

Its V2 domain is:

```text
RiskYieldMMA2MStep2ExternalSchemaV2MaximumContextObjectV2V4_9F_RawV8
```

The context-object file remains the exact compact-canonical record bytes, not a
wrapper. All four permitted record types, standalone-legality checks,
deduplication, reference-closure rules, and type/count ceilings from predecessor
Section 11.3 remain unchanged.

Semantic IDs and measured lengths use compact
`riskyieldmm_canonical_json_v1`. Row, page, context-root, and publication files
use deterministic UTF-8 JSON with sorted keys, two-space indentation, and one
terminal LF. Context-object files use exact compact canonical bytes with no
BOM, LF, wrapper, or trailing bytes.

`MaximumRecordReferenceV2` retains exactly these three forms and member order:

```text
WITNESS_RECORD:
  reference_kind
  record_type_name
  record_identity_field
  record_identity
  record_canonical_byte_length
  record_canonical_sha256
  maximum_record_reference_id

CONTEXT_OBJECT:
  reference_kind
  maximum_context_object_id
  record_type_name
  record_identity_field
  record_identity
  record_canonical_byte_length
  record_canonical_sha256
  maximum_record_reference_id

V4_INVENTORY_POINTER:
  reference_kind
  source_inventory_sha256
  inventory_json_pointer
  record_type_name
  record_identity_field
  record_identity
  record_canonical_byte_length
  record_canonical_sha256
  maximum_record_reference_id
```

Its ID domain is:

```text
RiskYieldMMA2MStep2ExternalSchemaV2MaximumRecordReferenceV2V4_9F_RawV8
```

The closed V4 pointer surfaces and their profile positions are byte-identical
to the predecessor V3 profile authorities; only the reference tag and source
inventory identity change. A V3 pointer tag inside V2 rejects.

The exact non-null `scope_witness_context` forms remain:

```text
SELF_VALUE:
  context_kind

OWNER_MEMBER:
  context_kind
  owner_record_reference
  payload_typed_member_path

OUTER_RESULT_APPLICATION:
  context_kind
  constraint_scope_profile_id
  operation_result_record_reference
  operation_spec_authority_reference
  ordered_application_invocations

ROOT_APPLICATION:
  context_kind
  constraint_scope_profile_id
  selected_root_family_position
  measured_sequence_ordinal
  root_record_reference
  selector_authority_reference | null
  target_field_registry_authority_reference
  marker_contract_authority_reference
  ordered_observation_record_references
  ordered_application_invocations
```

All predecessor cardinality, ordinal, selected-witness, root-ID, application-
schedule, and complete-record-resolution rules remain unchanged.

A page has exactly:

```text
artifact_version
canonicalization_version
measurement_schema_version
maximum_protocol_sha256
source_inventory_sha256
external_schema_registry_id
rule_literal_authority_sha256
page_position
first_context_object_position
last_context_object_position
context_object_count
total_context_object_octets
ordered_context_object_entries
maximum_context_object_page_id
```

Its version/domain are:

```text
riskyieldmm.raw_v8_step2_external_schema_v2.maximum_context_object_page.v2
RiskYieldMMA2MStep2ExternalSchemaV2MaximumContextObjectPageV2V4_9F_RawV8
```

Each `ordered_context_object_entries` item has exactly:

```text
context_object_position
maximum_context_object_id
record_type_name
record_identity_field
record_identity
record_canonical_byte_length
record_canonical_sha256
repository_relative_path
raw_octet_count
raw_sha256
```

The root context-object manifest has exactly:

```text
artifact_version
canonicalization_version
measurement_schema_version
maximum_protocol_sha256
source_inventory_sha256
external_schema_registry_id
rule_literal_authority_sha256
context_object_count
context_object_page_entry_limit
context_object_page_raw_octet_limit
context_object_page_count
total_context_object_octets
ordered_context_object_page_entries
maximum_context_object_manifest_id
```

Its version/domain are:

```text
riskyieldmm.raw_v8_step2_external_schema_v2.maximum_context_object_manifest.v2
RiskYieldMMA2MStep2ExternalSchemaV2MaximumContextObjectManifestV2V4_9F_RawV8
```

Each root page entry has exactly:

```text
page_position
first_context_object_position
last_context_object_position
context_object_count
total_context_object_octets
first_maximum_context_object_id
last_maximum_context_object_id
repository_relative_path
raw_octet_count
raw_sha256
maximum_context_object_page_id
```

The page entry and raw-octet limits remain exactly 1,024 and 1,048,576. Every
individual pretty JSON row/page/manifest remains strictly below 16,777,216 raw
octets. V2 retains all predecessor exact paging, sorted-ID, hash-prefix,
deduplication, closure, retained-byte, regular-file, single-link, unique-inode,
no-follow/nonblocking-open, re-enumeration, atomic-staging, synchronization,
and publish-root-last rules. The final protocol freezes the smaller practical
aggregate closure/file/work caps before pilot.

The selected publication closure contains exactly the union of every selected
row's `ordered_required_context_object_ids`. It contains no object used only by
an unselected candidate. Every selected row closure must be a subset of the
published root, and the publication validator independently proves exact union,
deduplication, path, object, page, and root-manifest equality.

No V1 maximum artifact, path root, pointer tag, identity, or version may be
relabelled as V2. Regeneration and independent validation are mandatory.

## 9. Deterministic publication is separate

Before publication, more than one V2 row may validly prove the same
mathematical maximum. Publication freezes exactly one accepted attainer per row
through a separate manifest with:

```text
artifact_version
canonicalization_version
measurement_schema_version
maximum_protocol_sha256
source_inventory_sha256
external_schema_registry_id
rule_literal_authority_sha256
selection_policy = PINNED_ACCEPTED_ATTAINER_V1
maximum_context_object_manifest_id
context_object_manifest_repository_relative_path
context_object_manifest_raw_octet_count
context_object_manifest_raw_sha256
generator_recipe_entry
independent_validation_report_entry
row_count = 474
ordered_selected_attainer_entries
maximum_publication_manifest_id
```

Its exact path, version, and ID domain are:

```text
tests/raw_v8_step2_external_schema_v2_maximum_attainers_v2_v49f.json
riskyieldmm.raw_v8_step2_external_schema_v2.maximum_publication_manifest.v2
RiskYieldMMA2MStep2ExternalSchemaV2MaximumPublicationManifestV2V4_9F_RawV8
```

`generator_recipe_entry` and `independent_validation_report_entry` each have
exactly:

```text
repository_relative_path
raw_octet_count
raw_sha256
```

Each selected-row entry binds:

```text
row_position
constraint_scope
constraint_scope_id
constraint_scope_profile_id | null
type_name
alternative_name | null
selected_maximum_attainer_id
selected_upper_bound_certificate_id
selected_row_context_closure_id
selected_witness_canonical_byte_length
selected_witness_canonical_sha256
row_repository_relative_path
row_raw_octet_count
row_raw_sha256
```

Selected row paths are exactly the V2 hash-prefix row paths in Section 8.4.
The publication-manifest ID covers every preceding member in the order above.

The generator-recipe and independent-validation entries bind their exact local
paths, raw counts, and hashes and reject extra/open fields. The generator recipe
is reproducibility provenance, never proof authority. The independent report
covers the exact selected row set and exact selected global context closure but
must not contain the final publication-manifest ID or hash, which would create
an identity cycle. The publication validator revalidates the manifest, selected
rows, report pins, and closure independently; the report never substitutes for
verification. A report/manifest row-set mismatch rejects. The selection
authority is the separately reviewed manifest freeze over already verified
candidate rows.

After publication, a different equal-length legal attainer remains
mathematically valid but is not publication-valid. Replacing it requires a new
publication-manifest identity and the normal review/promotion process. No claim
of global lexicographic leastness follows.

## 10. Resource model and non-circular seed process

V2 must not derive safety caps from a successful pilot and then pretend those
caps constrained that pilot. Resource acceptance has four ordered phases.

### Phase F0 — bootstrap and immutable seed ceilings

Before any V2 artifact or full-row report exists, a candidate V2 protocol
freezes conservative platform/seed ceilings and recurrence strategy rules for:

- each pinned normative input and candidate file;
- total candidate closure bytes and entry count;
- checked-integer width;
- maximum parser nesting;
- wall-clock/CPU budget for the offline preflight; and
- temporary storage and resident memory.

These are denial-of-service ceilings, not claims that the proof fits. Their
selection rationale and any rounding rule must be declared before F1 results
exist; F1 or a pilot cannot raise them. Wall-clock, CPU-time, RSS, and storage
watchdogs are platform abort limits, not portable semantic proof metrics.

### Phase F1 — counting-only full-row preflight

Two independent implementations derive worst-case verifier work for all 475
verifier-owned scope cases (the 474 maximum scopes plus the separate
local-shutdown problem) without allocating one object
per potential value, array item, primitive coordinate, or proof node. They use
checked arithmetic and stream/batch formulas. Required counts include:

```text
scope count
descriptor occurrences
recurrence states
recurrence transitions
batch applications
cache entries and key bytes
derivation canonicalization input/output octets
derivation hash preimage octets
rule and application evaluations
maximum recursion/iteration depth
```

Only the deterministic semantic count payloads from the two implementations
must be byte-identical after canonicalization. Tool identities, timings,
watchdog observations, and diagnostics remain outside that equality. The
semantic payloads must agree with hand-checkable boundary formulas for repeated
0/1/2/511/512/185 and 524,288-cardinality cases.

### Phase F2 — immutable protocol limits

Only after F1 passes are final V2 limits derived using the predeclared F0
rounding rule. Each final limit must be:

- at least the independently derived worst case needed for every required
  scope;
- no greater than its predeclared F0 platform ceiling;
- no greater than the corresponding immutable F0 seed ceiling;
- bound into the physically final V2 protocol before any pilot witness is
  read; and
- enforced atomically before allocation or mutation.

If no interval satisfies those conditions, V2 is rejected. A pilot may not
raise a limit. The two preflight implementations must rerun against the exact
physically frozen protocol bytes before pilot authorization.

### Phase F3 — pilot and production verification

The pilot validates actual counts against the already immutable F2 limits. A
smaller observation does not tighten a cap automatically; an excess rejects
the protocol or implementation. Final acceptance reports both derived
worst-case and observed counts without conflating them.

### Phase A — selected-artifact admissibility

Publication resources are distinct from authority-derived proof work. F0
freezes per-file, entry, page, row, and aggregate selected-closure caps before
candidate witnesses exist. The theoretical 7,003,576,276-octet context ceiling
does not have to fit the practical aggregate cap. Instead, the actual 474
selected rows and exact union of their per-row context closures must fit every
fixed artifact cap.

An oversize candidate may be replaced by another independently validated legal
equal maximum with a smaller context closure. If no complete selected bundle
fits, publication is NO-GO; the proof caps are not raised and an unproved
shorter witness is not substituted. Actual selected object/page/closure octets,
peak retained validation bytes, and containing-file bytes are measured only
after the selected bytes exist and are checked by the artifact/publication
layers.

## 11. Local-shutdown minimality remains separate

The legal `LOCAL_SHUTDOWN` outer-result maximum for the exact accepted signed
spec profile is one of the four outer-result rows and therefore one of the 474
byte maxima. The separate object here is the unrepresentable-plan
counterexample and minimality result. It asks for the least nonzero mutation
under the exact frozen objective over the permitted plan-limit fields whose
prospective operational result reaches or exceeds the outer wrapper ceiling
while the unchanged runtime still rejects at exactly that codec coordinate.

V2 retains that objective but gives it a separate versioned certificate and
resource account. Its verifier may use a finite boundary-candidate recurrence
or exhaustive enumeration when the frozen mutable-limit domain permits it. It
must prove:

```text
minimize (
  changed_limit_field_count,
  sum_absolute_integer_deltas,
  changed_member_names_in_lexical_order,
  resulting_changed_values_in_that_same_order
)
```

It must additionally prove:

- the baseline and mutation authorities;
- the exact permitted mutable members;
- nonzero, in-range deltas;
- every prospective-result validation other than the one explicitly masked
  outer `CapacityMeasurementOperationResultEvidence LT 524288` codec check;
- prospective canonical length at least 524,288;
- unchanged-runtime rejection at that exact unmasked outer codec coordinate;
- no second validation mask or malformed nested value; and
- absence of a better objective tuple.

The separate file path becomes:

```text
tests/raw_v8_step2_external_schema_v2_local_shutdown_unrepresentable_v2_v49f.json
```

Its exact root members remain the predecessor Section 12 members in the same
order except that `proof_resource_report` is inserted immediately after
`minimality_certificate`:

```text
artifact_version
canonicalization_version
measurement_schema_version
maximum_protocol_sha256
source_inventory_sha256
external_schema_registry_id
rule_literal_authority_sha256
constraint_scope_profile_id
baseline_spec_record_reference
mutated_limit_members
mutated_spec
changed_limit_field_count
sum_absolute_integer_deltas
prospective_result
prospective_result_canonical_byte_length
outer_codec_byte_bound_relation
outer_codec_octet_limit
expected_rejection_coordinate
minimality_certificate
proof_resource_report
local_shutdown_unrepresentable_id
```

Its version and ID domain are:

```text
riskyieldmm.raw_v8_step2_external_schema_v2.local_shutdown_unrepresentable.v2
RiskYieldMMA2MStep2ExternalSchemaV2LocalShutdownUnrepresentableV2V4_9F_RawV8
```

`local_shutdown_unrepresentable_id` covers every preceding root member in the
order shown.

The V2 minimality certificate has exactly:

```text
certificate_version
maximum_protocol_sha256
source_inventory_sha256
constraint_scope_profile_id
baseline_operation_spec_id
mutated_operation_spec_id
local_shutdown_proof_scope_id
winning_objective
minimality_derivation_catalog_id
minimality_derivation_plan_id
ordered_safe_relaxation_rule_ids
winning_prospective_bound_certificate
better_objective_exclusion_result_sha256
local_shutdown_minimality_certificate_id
```

Its version and ID domain are:

```text
riskyieldmm.raw_v8_step2_external_schema_v2.local_shutdown_minimality_certificate.v2
RiskYieldMMA2MStep2ExternalSchemaV2LocalShutdownMinimalityCertificateV2V4_9F_RawV8
```

`local_shutdown_minimality_certificate_id` covers every preceding certificate
member in the order shown.

`winning_prospective_bound_certificate` is the complete embedded Section 8.2
certificate with `derivation_scope_id = local_shutdown_proof_scope_id`. The
independent verifier reconstructs its exact masked-domain recurrence, recomputes
the complete certificate and ID, and compares the embedded object. A bare,
unresolved, wrong-domain, or wrong-mask certificate ID is never proof and
rejects.

`local_shutdown_proof_scope_id` uses domain:

```text
RiskYieldMMA2MStep2ExternalSchemaV2LocalShutdownProofScopeV2V4_9F_RawV8
```

over exactly:

```text
maximum_protocol_sha256
source_inventory_sha256
constraint_scope_profile_id
baseline_operation_spec_id
mutated_operation_spec_id
```

The local proof-resource report uses the exact Section 8.3 member schema with:

```text
riskyieldmm.raw_v8_step2_external_schema_v2.local_shutdown_proof_resource_report.v2
RiskYieldMMA2MStep2ExternalSchemaV2LocalShutdownProofResourceReportV2V4_9F_RawV8
```

It sets `derivation_scope_id = local_shutdown_proof_scope_id` and places the
local minimality certificate ID in `derivation_certificate_id`; a maximum-row
report uses its row constraint-scope and upper-bound-certificate IDs. The
independent verifier recomputes the full strictly-better mutation domain result
and digest rather than trusting a producer claim.

It must not reuse the rejected global primitive-vector prefix chain. A failure
of local minimality cannot be hidden by success of the 474 byte maxima.

## 12. V4 successor inventory and authority migration

The accepted canonical V3 inventory currently pins the predecessor correction
at physical SHA-256
`29ec141e53adeb1c0afd51f205f5b57eb784b8859b5ba40958299abd1b713b55`.
Before V2 preflight or pilot:

```text
inventory schema_version = riskyieldmm.raw_v8_step2_inventory.v4
external schema profile  = riskyieldmm_raw_v8_step2_external_schema_v2
```

The V4 root retains exactly the V3 logical keys:

```text
schema_version
normative_document_inputs
invariants
target_field_registry
operation_counter_schema
marker_contract
checkpoint_selector_catalog
ingress_logical_oracle_profile_catalog
external_schema_registry_v2
operation_contracts
fixture_records
inventory_sha256
```

1. independently review and accept this successor correction;
2. define inventory schema V4 and add this amendment as a fifth normative input
   with role
   `STEP2_COMPACT_MAXIMUM_PROOF_V2_CORRECTION`;
3. add exact invariants stating that global leastness and per-coordinate proof
   evidence are not maximum-safety requirements and that publication uses
   `PINNED_ACCEPTED_ATTAINER_V1`;
4. regenerate the canonical V4 inventory and all authority mirrors from the
   accepted V3 golden plus the new authority/invariants;
5. require the external-schema registry bytes/ID, literal authority bytes,
   every one of the 408 scope-profile objects/IDs, the 474 row universe/order,
   and every unrelated invariant to remain byte-identical;
6. require only the new normative-document entry, its invariant mirrors, the
   narrowly added proof/publication invariants, schema version, and the root
   inventory identity to change; and
7. re-run the complete focused inventory/security and migrated-consumer suites
   before accepting the new V4 physical and semantic identities.

The exact V4 normative-input order is:

```text
1 PARENT_MARKER_OPERATION_TARGET_PROTOCOL
2 STEP2_V2_CONTRACT_FREEZE
3 STEP2_EXTERNAL_SCHEMA_V2_CORRECTION
4 STEP2_COMPACT_MAXIMUM_PROOF_V2_CORRECTION
5 STEP3_TARGET_AND_LIFECYCLE_CORRECTION
```

V4 adds `normative_document_input_count = 5` and the amendment's exact
authority-mirror entry. Profile IDs remain unchanged because their identity
payload does not contain the inventory root. Non-intrinsic scope IDs later
change because they bind the V4 inventory identity, and all V2 scope IDs change
under their new protocol/domain. Context, attainer, certificate, resource,
page, and manifest identities consequently regenerate.

V4 also adds exactly this invariant object:

```text
compact_maximum_proof_v2_contract:
  mathematical_acceptance_rule = SOUND_UPPER_BOUND_PLUS_LEGAL_ATTAINMENT_V1
  global_least_attainer_required = false
  ordered_component_choice_evidence_required = false
  proof_resource_report_is_separate = true
  publication_selection_policy = PINNED_ACCEPTED_ATTAINER_V1
  maximum_publication_row_count = 474
  verifier_owned_scope_case_count = 475
```

No other V3 invariant changes except `inventory_schema_version`,
`counts.normative_document_input_count`, the normative-document hash mirror,
and the root inventory identity.

Any registry, profile, row-universe, authority-pointer, or unrelated-invariant
drift is STOP/NO-GO, not a routine migration effect.

The accepted V3 artifact remains the immutable predecessor; it is not edited or
relabeled as V4. The V4 generator and validator must reject a four-input V3
artifact relabeled as V4, a V4 artifact missing either correction authority,
and any V3 consumer silently treating the fifth input as optional.

The rejected V1 validator remains pinned to its V1/V3 authorities and
acceptance barrier. V2 uses a separate validator; implementation must not turn
V1 acceptance on or silently reinterpret V1 records.

## 13. Required implementation sequence

```text
accepted V1 feasibility rejection
  -> independently accepted V2 correction
  -> V4 successor inventory generation and acceptance
  -> V2 seed-protocol candidate freezes exact grammar, recurrence/state
     semantics, meter catalog, deterministic strategy, and F0 seed ceilings
  -> two independent counting-only full-row feasibility preflights
  -> insert derived F2 limits and physically freeze the V2 protocol without
     changing its strategy or proof semantics
  -> repeat both preflights against the final protocol bytes
  -> independent full verifier implementation
  -> independent generator/solver implementation
  -> six-case replacement pilot
  -> 474 maxima and local-shutdown result
  -> separate complete runtime-work accounting
  -> production differential adapters
  -> Raw V7/final-tree compatibility
  -> Raw V8 Step-2 acceptance
```

No later arrow may be treated as evidence for an earlier one.

## 14. Falsification matrix

At minimum, acceptance must include these tests:

1. two different legal equal-length maxima both pass mathematical verification
   before publication freeze;
2. after one is pinned, the other remains mathematically valid but fails
   publication validation;
3. a non-lexicographically-least legal attainer passes maximum verification;
4. a legal witness of `U - 1` rejects;
5. an illegal same-length witness rejects;
6. wrong producer `U`, witness hash, recurrence ID, relaxation list, or resource
   claim rejects;
7. exhaustive small schemas agree exactly with the V2 recurrence;
8. batched and unbatched recurrences agree for every bounded small case;
9. 0, 1, 2, 511, 512, 524,287, and 524,288 item boundaries plus 185 repeats
   agree with direct formulas;
10. each omitted cache-key component is caught by a targeted mutation whose
    correct results otherwise collide;
11. Unicode NFC boundary and pinned-version drift reject;
12. invalid UTF-8, duplicate JSON keys, lone surrogates, non-I-JSON numbers,
    wrong key order, and trailing bytes reject before semantic use;
13. a narrowed or direction-reversed relaxation rejects;
14. protocol, correction, inventory, registry, or literal-authority shift
    rejects transitively;
15. every resource cap passes at the exact cap and rejects at cap plus one
    before allocation;
16. symlink, FIFO, device, socket, hard-link alias, path traversal, unstable
    file, unexpected file, and stale retained-byte attacks reject;
17. bounded independent exhaustive/PB/SMT differential checks agree where
    their separately frozen translations apply;
18. no V1 coordinate catalog, prefix node, winner digest, V1 artifact version,
    or V1 identity domain is accepted inside a V2 closure;
19. a safe relaxation whose upper endpoint is not legally attainable fails P3;
20. context-object substitution, incomplete application schedule, derived-ID
    inversion, and wrong selected observation ordinal reject; and
21. all 474 publication rows and all 475 verifier-owned scope cases appear in
    the deterministic counting preflight and fit every F2 limit before the
    first pilot artifact is loaded;
22. a V3 inventory supplied where V4 is required rejects without migration;
23. the verifier rejects producer imports, reflection, and subprocess calls;
24. a validation report containing the publication ID/hash, open recipe/report
    entries, an orphan/unselected context object, a row closure outside the
    publication closure, or a report/manifest row-set mismatch rejects;
25. two equal attainers with different per-row closures can be selected without
    changing either mathematical row ID;
26. F1 semantic count payloads remain equal while nonsemantic diagnostics may
    differ;
27. a theoretical context ceiling may exceed the practical artifact cap while
    an actual selected closure still passes;
28. `V3_INVENTORY_POINTER` inside any V2 artifact rejects;
29. a resource report attempting to charge its own serialization, ID preimage,
    or hash rejects;
30. both `U - 1` and a producer `U + 1` reject through failed attainment
    equality;
31. the legal ordinary `LOCAL_SHUTDOWN` outer-result maximum row remains in the
    474-row set while the separate minimality object validates independently;
    and
32. local-shutdown wrong objective, skipped better mutation, second mask,
    unresolved/wrong-domain prospective certificate, and changed runtime-
    rejection-coordinate cases reject.

## 15. Acceptance criteria and abandon conditions

The compact design may advance to implementation only when:

- two independent reviewers agree that P1/P2/P3 establish the required exact
  byte maximum;
- the narrow supersession has no unresolved conflict with descriptor, codec,
  application, identity, or context-closure semantics;
- the successor V4 inventory changes only the explicitly permitted authority,
  schema-version,
  invariant surfaces;
- two independent F1 implementations agree on all full-row counts;
- every required count fits between the immutable F0 and F2 ceilings;
- the proposed recurrence state is sufficient for every ancestor-observable
  rule and application; and
- the independent verifier can reject producer evidence without importing the
  producer.

Abandon or redesign this direction if:

- a complete sound state signature still requires per-coordinate global
  serialization beyond the platform ceiling;
- a safe upper bound cannot be made attainable by any independently validated
  legal witness;
- exact recurrence and exhaustive bounded controls disagree;
- V3-carried profile or registry semantics drift during V4 generation;
- the independent verifier cannot remain smaller and more auditable than the
  producer; or
- any required file/work/resource cap is exceeded.

Failure is a valid result. It must leave Raw V8 Step 2 closed rather than
relaxing proof or legality requirements silently.

## 16. Research basis and limits

The proof-checker separation follows the certifying-algorithm principle: an
algorithm returns an output plus a witness that an independent checker can use
to establish correctness without trusting the producer. The survey by
McConnell, Mehlhorn, Näher, and Schweitzer supports that design principle; it
does not prove this repository's recurrence or resource feasibility:

- [McConnell et al., *Certifying algorithms*](https://doi.org/10.1016/j.cosrev.2010.09.009)

The batched recurrence direction is informed by general semiring dynamic-
programming frameworks, which show how path computations can be composed over
appropriate algebraic states. Applicability here is conditional: the RiskYield
state must include every rule-visible component, and equivalence must be tested
against exhaustive small domains:

- [Mohri, *Semiring Frameworks and Algorithms for Shortest-Distance Problems*](https://cs.nyu.edu/~mohri/pub/jalc.pdf)

Pseudo-Boolean proof logging is a credible differential option for bounded
combinatorial optimization, but its translation and proof/checker resource
cost are additional trusted surfaces. It is therefore experimental evidence,
not the accepted V2 core:

- [Koops et al., *Practically Feasible Proof Logging for Pseudo-Boolean Optimization*](https://doi.org/10.4230/LIPIcs.CP.2025.21)
- [VeriPB project and proof checker](https://veripb.org/)

The project retains its pinned `riskyieldmm_canonical_json_v1` semantics. RFC
8785 is supporting evidence for deterministic JSON serialization and I-JSON
constraints, not permission to substitute its UTF-16 property-order rule for
the project's frozen ordering:

- [RFC 8785, JSON Canonicalization Scheme](https://www.rfc-editor.org/rfc/rfc8785.html)

Unicode behavior remains pinned to the repository's accepted Unicode 15.0.0
authority. Normalization must be versioned and tested rather than delegated to
the host runtime:

- [Unicode Standard Annex #15, Unicode Normalization Forms, Version 15.0.0](https://www.unicode.org/reports/tr15/tr15-52.html)

None of these sources proves that the local 474-row/475-scope problem fits the
proposed limits. Only the authority transition, full-row preflight, independent verifier,
attaining witnesses, adversarial tests, and final acceptance evidence can do
that.

## 17. Current gate state

```text
V1 feasibility rejection                 ACCEPTED
V2 compact-proof correction              ACCEPTED
V4 successor inventory                   NOT STARTED
V2 full-row counting preflight           NOT STARTED
V2 immutable protocol freeze             NOT STARTED
V2 pilot                                 NOT AUTHORIZED
474 constructive maxima                  NOT STARTED
local-shutdown V2 result                 NOT STARTED
runtime-work accounting                  INCOMPLETE
production adapters / compatibility      INCOMPLETE
Raw V8 Step-2 acceptance                 NO-GO
A2-M / A2-E / Stage 1                    INCOMPLETE
```
