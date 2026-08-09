# Raw V8 Step-2 constructive-maximum proof protocol

Date: 2026-08-02
Status: **REJECTED — PRE-SEARCH PLAN EXCEEDS IMMUTABLE SEED CAPS**
Protocol version: `riskyieldmm.raw_v8_step2_external_schema_v2.maximum_protocol.v1`

This document records the rejected V1 certificate language that was intended
to prove the 474 Raw V8 Step-2 External Schema V2 compact-canonical byte maxima
and the separate local-shutdown unrepresentable-plan counterexample. A
verifier-owned pre-search audit proved that its mandatory complete coordinate
plan cannot fit its own immutable seed limits. The six-case pilot, production
maximum generation, final rebinding, and acceptance are therefore prohibited
under this version. No maximum witness generated under V1 is acceptance
authority.

## 0. Rejection finding and required redesign

The failure is constructive and occurs before any producer, solver, frontier,
or witness is consulted. Intrinsic row 62 is the full-schema
`TargetFieldRegistryV1` row (type 24 in the correction document's descriptive
type list). Its pinned External Schema V2 descriptor contains:

```text
TargetFieldRegistryV1.descriptors
  fixed cardinality = 185
  item type = CapacityMeasurementTargetFieldDescriptorV1

CapacityMeasurementTargetFieldDescriptorV1.value_shape_keys
  cardinality domain = 0..512
  item language = BUILTIN RAW_CANONICAL_JSON_STRING
```

The raw-string language is noncatalog and has more than one legal value. Under
Sections 4.2 and 6.5, each of the 185 inner arrays therefore emits one
`ARRAY_CARDINALITY` coordinate and expands all 512 possible item occurrences,
each of which emits one `TEXT_VALUE` coordinate. This gives the following
strict lower bound without counting any other member, observer, or rule:

```text
185 * (1 + 512) = 94,905 mandatory choice-plan coordinates
```

This lower bound cannot be removed by authority substitution. The row has
`constraint_scope = INTRINSIC_TYPE` and null source-inventory/profile
authority; `value_shape_keys` is identity payload, not a value derived from the
registry identity; and Section 6.5 expressly forbids shrinking the pre-search
plan using intrinsic-rule survival, frontier contents, solver output, or
producer evidence.

V1 requires one prefix proof node for every plan coordinate. The same lower
bound therefore exceeds both immutable seed limits:

```text
component_choice_coordinate_count: 94,905 > 65,536
proof_node_count before base nodes:  94,905 > 65,536
```

Final ceilings must be no greater than the seed limits, so pilot measurement or
rebind cannot repair the contradiction. Raising the limits would change the
candidate protocol and start a new seed cycle; it would not validate V1. The
remaining sections are retained only as rejected design evidence and reusable
semantic definitions.

The replacement protocol must preserve independently checked legal-domain
upper bounds and a legal attaining witness, but it must not serialize one
proof node per global tie-break coordinate. The next design gate is a compact
attainment/selection proof with verifier-derived streaming plan authority,
batched recurrence for repeated schema occurrences where needed, and no claim
that globally least witness selection is a safety requirement unless that
requirement receives a separately feasible proof. The replacement receives a
new protocol version, new pilot, new resource seed, and new acceptance audit.
The executable derivation and adversarial evidence are recorded in
[`v4_9f_a2_raw_v8_step2_maximum_protocol_v1_feasibility_rejection_2026-08-02.md`](v4_9f_a2_raw_v8_step2_maximum_protocol_v1_feasibility_rejection_2026-08-02.md).

## 1. Decision boundary

The certificate is a proof, not a solver transcript and not a Boolean claim.
For each frozen constraint scope it must establish both:

1. an upper bound over every legal value in that scope; and
2. a complete legal witness whose measured compact-canonical byte length
   attains that upper bound.

The accepted value is therefore exact:

```text
legal-domain upper bound = retained legal witness length = certified maximum
```

If a safe relaxation is used, the verifier independently proves that the
relaxed domain is a superset of the legal domain. A relaxed upper bound is
accepted only when a legal retained witness reaches it. The deterministic
tie-break is proved again over the exact legal maximum-length slice; an
illegal value admitted by a relaxation can never win the tie-break.

This protocol does not change any V3 codec ceiling. It proves byte maxima only.
It does not certify runtime work, total CPU, memory, latency, trading edge,
paper/live readiness, or Stage 1 completion.

## 2. Bound authorities

The checker pins and independently validates these predecessor authorities
before reading a certificate:

| Authority | Physical or semantic identity |
|---|---|
| External-schema correction | physical SHA-256 `29ec141e53adeb1c0afd51f205f5b57eb784b8859b5ba40958299abd1b713b55` |
| Canonical V3 inventory | physical SHA-256 `f33c1019afa7f49a316aac1bfbef7498e240f391e4fee00dfd95fdcda658669f`; semantic ID `128d07a45dc2300c140f333cc3a45e2497aaa4089684f6e44da048ab403bbf9d` |
| External Schema V2 registry | physical SHA-256 `9160297ff316c5931737c92f8b359f0a1e2ec22f0aa996ef3b09cf830dc96bf3`; semantic ID `5dc95a3e99c5646e912b6a7e9c3970cf2489d560ea890b0a19d38af4c51c2140` |
| Rule literal authority | 484,301 octets; physical SHA-256 `aba3461059367904734e2eb9ae404787b9aab5ed4c3fbcd292925a364926cce2` |
| Pilot application witness | pilot-only physical SHA-256 `d2f40badc85c58965a72e52fd98bfebbd4caf3335ec5a0415a89294cc3fb3415`; never a production maximum authority |
| Pilot max64/full-67 materialized context | pilot-only path `scripts/tests/raw_v8_step2_external_schema_v2_application_witness_max64_full67_context_v49f.json`; 16,121,125 raw octets; physical SHA-256 `afab90030ac96fa21157bdd3e696dd25798d7755be028c5cb8eaca103f73de97`; compact 12,698,603 octets/SHA-256 `ab67d30d11d19670652b4c1a7aeb2d1483b97f6c4dde7bd673d9f25a3079059e`; never a production maximum authority |
| Canonicalization | `riskyieldmm_canonical_json_v1` |
| Measurement schema | `riskyieldmm_physical_transport_a2m_raw_v49f_v8` |

Every production certificate binds this document's final physical SHA-256.
The document does not contain that digest, avoiding self-reference. The
independent checker and acceptance report pin it after final bytes are frozen.

## 3. Research basis and local applicability

The design follows the certifying-algorithm principle: an optimizer may be
complex, but its answer is accepted only through a separate machine-checkable
proof. Modern pseudo-Boolean work demonstrates that proof-producing
optimization and separate checking are practical, while also showing that
implicit solver simplifications and proof-resource growth are real failure
modes. We use that separation, but do not encode the full JSON, Unicode,
record, and application semantics into a generic pseudo-Boolean solver. Doing
so would create a second large translation trust boundary. The accepted path
is a smaller domain-specific checker whose operators are exactly the frozen
External Schema V2 value constructors and rule transfers. A pseudo-Boolean
encoding may be run later as a differential challenger; it is not authority.

Compact JSON bytes follow the repository's already-frozen exact-I-JSON
canonicalizer. RFC 8785 supports deterministic, hashable JSON representation
and requires duplicate-name rejection and deterministic serialization. This
protocol retains the repository's narrower safe-integer and no-float profile;
it does not silently replace it with all of JCS. JSON syntax and string
interoperability remain grounded in RFC 8259. Identifier normalization remains
the already-pinned Unicode 15.0.0 UAX #15/NFC authority; JCS itself does not
normalize strings, so normalization is an explicit schema rule before
canonicalization rather than an implicit repair.

Primary references:

- IETF, [RFC 8259: JSON](https://www.rfc-editor.org/rfc/rfc8259.html)
- IETF, [RFC 8785: JSON Canonicalization Scheme](https://www.rfc-editor.org/rfc/rfc8785.html)
- Unicode Consortium, [UAX #15: Unicode Normalization Forms](https://www.unicode.org/reports/tr15/)
- Koops et al., [Practically Feasible Proof Logging for Pseudo-Boolean Optimization](https://drops.dagstuhl.de/storage/00lipics/lipics-vol340-cp2025/html/LIPIcs.CP.2025.21/LIPIcs.CP.2025.21.html), CP 2025

These sources support canonical bytes, explicit normalization, and independent
proof checking. They do not prove that this repository's grammar is sound;
that claim requires the local pilot, adversarial tests, and independent
checker specified below.

## 4. Mathematical object being certified

For frozen scope `S`, let `D(S)` be the exact finite legal value/context domain
induced by the accepted V3 descriptors, scalar languages, intrinsic rules,
scope profile, authority pointers, application schedule, nested codec bounds,
and owner codec bound. Let `B(v)` be the number of octets in the compact
canonical encoding of the measured value. Let `M(v)` and `C(v)` be the
verifier-derived measured-record and constructed-context primitive choice
vectors. Derived identities, hashes, paths, proof values, and authority-fixed
values are excluded.

The certified winner is the unique lexicographic optimum:

```text
minimize (-B(v), M(v), C(v)) over v in D(S)
```

Equivalently, maximize bytes, then minimize the measured vector, then minimize
the context vector. The exact coordinate order and typed comparison are those
frozen in correction Section 11.3.

### 4.1 Exact attainable frontier

Every proof node denotes an exact frontier before any explicitly named safe
relaxation. Mathematically it is a set:

```text
F = {(ancestor-observable equivalence-cell key, attainable byte length)}
```

Each cell is the exact disjoint verifier-derived partition defined in Sections
4.3/6.2; a point means at least one legal underlying value in that cell attains
that length, and local transfer retains every correlation an ancestor reads.
Absence means unattainable. This is not a two-number minimum/maximum interval.
The verifier preserves gaps, residues, null/nonnull branches, union
alternatives, cardinalities, ordering/uniqueness state, and every semantic
projection read by an ancestor rule or application.

The canonical frontier encoding uses fixed 256-length bitmap blocks, not an
interval or producer-selected arithmetic progression. A bitmap run is exactly:

```text
first_block_index
last_block_index
attainable_length_bitmap_hex
```

Block `k` covers lengths `256*k .. 256*k+255`; bit `i`, counted from the least
significant bit, states whether length `256*k+i` is attainable. The bitmap is
exactly 64 lowercase hexadecimal characters and nonzero. It is the conventional
big-endian hexadecimal spelling of one 256-bit unsigned integer: the leftmost
character contains bits 255..252, the rightmost character bits 3..0, and bit 0
is the value-one bit of the rightmost character. Leading zero characters are
required to reach width 64. Block indices are
exact nonnegative safe integers, `first <= last`, runs are strictly ordered and
nonoverlapping, and adjacent runs with the same bitmap must be merged. This
fixed representation uniquely preserves arbitrary gaps and residue classes;
it cannot choose a favorable interval decomposition. The semantic frontier is
still the expanded map above.

Each frontier-changing node embeds this frontier in the unique bitmap form and
the checker verifies its local transfer from already-verified child frontiers.
The two semantics-preserving nodes named in Section 6.3 instead carry the
unique direct-child alias form; the checker resolves that authenticated edge
to the already verified materialized origin and never accepts hash equality as
a substitute for the edge. The checker computes a streaming canonical digest
over all expanded points in state-key order then increasing length exactly once
at the materialized origin. The materialized bitmap frontier, its two digests,
and every alias record are proof data; none is accepted without its closed
local transfer or alias check.
Primitive-vector minimization is deliberately separate: the exact legal
maximum-length slice and one prefix-exclusion node per coordinate prove the
measured/context tie-break after the byte upper bound is established.

### 4.2 Ancestor-observable state

The verifier derives state dimensions by a reverse dependency walk from all
selected intrinsic rules, scope applications, codec intersections, and the
tie-break. Exactly these dimension kinds exist:

```text
NULLABILITY_BRANCH
BOOLEAN_VALUE
SAFE_INTEGER_VALUE
TEXT_RELATION_CLASS
TEXT_CANONICAL_LENGTH
ARRAY_CARDINALITY
ARRAY_ORDER_CLASS
ARRAY_UNIQUENESS_CLASS
UNION_ALTERNATIVE_POSITION
CATALOG_POSITION
ROOT_FAMILY_POSITION
MODE_ATTEMPT_POSITION
OBSERVATION_ROLE_POSITION
SEQUENCE_ORDINAL
TEXT_VALUE
```

Before evaluating any frontier, the checker derives one ordinary-dimension
plan for every proof occurrence. It walks that occurrence's schema subtree in
the Section 5 descriptor order, then every downstream intrinsic expression in
constraint order/expression position, every application invocation in the
Section 7.10 order, and finally ordering, uniqueness, identity-preimage, and
codec observers in the fixed node-kind order above. Each observer emits the
applicable kind/locator/schema/comparison/guard record required by Sections
6.2 and 9. Byte-equal candidate keys are one semantic dimension and are
retained at their first traversal occurrence; unequal keys are never merged.
The candidate key is the compact-canonical five-member record
`dimension_kind, subject_locator, value_schema_id, comparison_semantics,
ordered_activation_guard_clauses`, excluding position and ID. After
deduplication, ordinary candidates are sorted by those complete key bytes,
assigned contiguous positions, and only then receive descriptor IDs. Thus
child unions, constraint projections, and maximum-slice reinstatement have one
normative ordinary signature order. This dimension-key deduplication does not
merge proof-plan occurrences or frontier states.

Tie-break dimensions are not part of that ordinary sort. An active prefix
node appends exactly one dimension derived from its coordinate plan under the
Section 6.5 mapping; later active nodes append in plan order. An inactive node
appends none. Consequently every node signature is exactly its sorted live
ordinary subset followed by the already-fixed active tie-break prefix; no
producer may reorder either part. Nullable, variable-cardinality array,
tagged-union, and scope transfers lift their child frontiers into one common
parent signature containing the union of branch candidates. A dimension below
a branch copies that branch's complete choice-plan activation clauses. For
each lifted state, an active branch copies the child cell and every false
branch contributes the exact ordinary-state `INACTIVE_GUARD_SENTINEL` cell
from Section 4.3. This lift, rather than a variable-length key, gives every parent state the
one required key cardinality.

The ordinary candidate emission table is exhaustive. “Always” means one
candidate at the defining exact transfer for every reachable occurrence of
that schema/shape; conditional rows emit in addition to the always rows. No
other observer emits a dimension:

| Reachable schema/observer | Ordinary dimension kind | Comparison semantics | Emission rule |
|---|---|---|---|
| nullable wrapper / null or presence observer | `NULLABILITY_BRANCH` | `NULL_BEFORE_NON_NULL` | always for a nullable occurrence |
| Boolean scalar | `BOOLEAN_VALUE` | `FALSE_BEFORE_TRUE` | always |
| safe-integer scalar, arithmetic operand, or numeric comparison | `SAFE_INTEGER_VALUE` | `MATHEMATICAL_INTEGER` | always for a safe-integer occurrence |
| text scalar canonical serialization length | `TEXT_CANONICAL_LENGTH` | `MATHEMATICAL_INTEGER` | always for a text occurrence |
| text literal/enum/DFA/normalization/equality/order predicate | `TEXT_RELATION_CLASS` | `FROZEN_CATALOG_POSITION` | once per text occurrence iff at least one such predicate reads it; the catalog truth vector contains all readers |
| array shape or length | `ARRAY_CARDINALITY` | `CARDINALITY_THEN_ITEMS` | always for an array occurrence |
| strict array ordering | `ARRAY_ORDER_CLASS` | `FROZEN_CATALOG_POSITION` | iff the descriptor or a reachable rule/application requires ordering |
| array uniqueness | `ARRAY_UNIQUENESS_CLASS` | `FROZEN_CATALOG_POSITION` | iff the descriptor or a reachable rule/application requires uniqueness |
| tagged-union shape | `UNION_ALTERNATIVE_POSITION` | `FROZEN_CATALOG_POSITION` | always for a union occurrence |
| non-text finite catalog, resolver, or exact derived-identity mapping catalog | `CATALOG_POSITION` | `FROZEN_CATALOG_POSITION` | iff that exact catalog projection is read by an ancestor; one per catalog/subject pair |
| scope root family | `ROOT_FAMILY_POSITION` | `FROZEN_CATALOG_POSITION` | iff the scope enumerates more than one family or an application reads it |
| instrumentation mode/attempt pair | `MODE_ATTEMPT_POSITION` | `FROZEN_CATALOG_POSITION` | iff present in the scope case product or read by an application |
| measured observation role | `OBSERVATION_ROLE_POSITION` | `FROZEN_CATALOG_POSITION` | iff present in the scope case product or read by an application |
| external sequence ordinal | `SEQUENCE_ORDINAL` | `FROZEN_CATALOG_POSITION` | iff a positional/zip rule, resolver, or application reads the ordinal |

One text occurrence therefore emits length plus relation class when it has a
text predicate; one exact ordered-unique array emits cardinality, order, and
uniqueness. No ordinary observer emits `TEXT_VALUE`: exact text needed while
building a relation/identity/ordering result lives in the closed transient
catalog, and exact text used by the objective appears only as an active prefix
dimension. A finite text literal/enum may occur as an exact `TEXT` partition
atom inside a verifier-derived relation catalog, but never as a pre-prefix
frontier cell; its choice coordinate is the Section 6.5 frozen catalog
position.

The two safe transfers have closed projection exceptions. An
`ORDERED_LANGUAGE_SAFE_UPPER_DOMAIN` array existentially projects out exactly
its `ARRAY_ORDER_CLASS` and `ARRAY_UNIQUENESS_CLASS` axes, unions equal
remaining keys' length sets, canonically merges runs, and preserves every
other ordinary dimension. Its maximum-slice/prefix recurrence keeps the exact
order/uniqueness state transient and never re-adds those oversized axes. A
`DERIVED_IDENTITY_FIXED_WIDTH_SAFE_UPPER_DOMAIN` node analogously has no
mapping-catalog axis; Section 9.3.1 keeps exact preimage/relation state
transient and never invents or re-adds `CATALOG_POSITION`. Every exact transfer
carries the table-emitted live dimensions, and no other transfer may project a
dimension. These rules close multi-emission, safe projection, and comparison
choice.

`TEXT_RELATION_CLASS` is the verifier-derived finite partition induced by
literal/enum membership, equality/inequality operands, DFA acceptance, and
normalization rules. It is not a producer-supplied label. If a rule requires
an exact value outside a finite partition, the checker retains its exact
canonical bytes in the transient state and charges their octets.

Proof-plan occurrences are never merged or hash-consed, even when their
descriptors happen to be byte-equal. This removes any implicit plan-key
equivalence rule. Frontier pruning within one occurrence is permitted only
across byte-equal complete ordered ancestor-observable cell signatures;
pruning across unequal signatures rejects.

The complete guarded choice-coordinate catalog is also structural rather than
witness-dependent. Before frontier evaluation the checker expands every legal
array position through the descriptor maximum, every nullable branch, every
union alternative, and every scope case in the depth-first order of Section
5. A coordinate that is absent from a particular value remains in that plan
catalog with its closed activation guard, but the plan catalog is metadata and
is not pre-expanded into the maximum-slice state signature. The maximum-slice
signature contains only the ordinary ancestor-observable dimensions needed to
check constraints and exact reinstatement under the empty primitive prefix.
The later prefix chain has one node for every plan coordinate. A false-guard
node carries `INACTIVE` only as its derivation's selected atom and leaves the
frontier signature unchanged; a true-guard node appends its distinct exact
tie-break dimension. Retained component evidence and winner digests contain
only true-guard coordinates. Consequently the complete plan-node count and
guarded coordinate-catalog count are exact pre-search quantities; only the
number of appended tie-break dimensions and active retained coordinates
depends on the winning witness.

### 4.3 Canonical transient frontier preimages

The producer embeds every frontier and the checker independently recomputes
each local transfer. Its two digests have fully specified preimages.
`MaximumTypedPrimitiveAtomV1` has exactly:

```text
atom_kind
boolean_value | null
integer_value | null
text_value | null
position_value | null
canonical_bytes_hex_value | null
```

`atom_kind` is `INACTIVE`, `NULL`, `BOOLEAN`, `SAFE_INTEGER`, `TEXT`,
`POSITION`, or `CANONICAL_BYTES`, and exactly the corresponding value member is non-null
(`INACTIVE` and `NULL` have all five null). `INACTIVE` is permitted only as the
`selected_atom` of a false-guard `LEXICOGRAPHIC_PREFIX_EXCLUSION` derivation.
It is forbidden in every state cell, retained choice vector,
component-choice evidence, guard atom, direct or copied recurrence key/payload
atom array, and retained record. Structurally inactive ordinary state is
represented only by the dedicated cell kind below; it is never a primitive
selected value. A Boolean
never occupies an integer/position
member. `TEXT` contains complete text, not a digest; `POSITION` is a
nonnegative safe integer. `CANONICAL_BYTES` is the even-length lowercase
hexadecimal spelling of complete compact-canonical bytes, including the empty
byte string; it is never a digest.

Generic `CANONICAL_BYTES` syntax establishes only complete lowercase-hex
bytes. A consuming semantic slot must additionally decode those bytes as
strict UTF-8, parse exactly one duplicate-free safe-I-JSON value within the
accepted depth bound, compact-canonicalize it byte-for-byte under
`riskyieldmm_canonical_json_v1`, validate the slot-specific schema, and require
equality with the independently derived value. Arbitrary bytes, a digest,
noncanonical JSON, a valid value of the wrong shape, or producer-supplied
redundant support rejects. The ordered-string slot schemas are closed in
Section 9.2.1; the generic atom validator must not assume that every
`CANONICAL_BYTES` atom contains JSON because the empty raw byte string remains
legal in slots whose own semantics explicitly permit it.

Primitive atoms are used for retained choice vectors and prefix-selected exact
values. Frontier state keys use `MaximumStateCellV1`, with exactly:

```text
cell_kind
exact_atom | null
integer_interval | null
catalog_id | null
catalog_position | null
state_cell_id
```

`cell_kind` is `INACTIVE_GUARD_SENTINEL`, `EXACT_ATOM`,
`SAFE_INTEGER_INTERVAL`, or `VERIFIER_DERIVED_CATALOG_POSITION`.
`INACTIVE_GUARD_SENTINEL` has all four payload members null and is legal only
for an ordinary dimension whose nonempty activation-guard array independently
evaluates false for that complete state. It is forbidden for an unguarded
ordinary dimension, an appended active-prefix dimension, and every direct
recurrence key/payload cell; a recurrence may only copy an already validated
sentinel cell from a child state. The exact form has only an atom and that atom
cannot be `INACTIVE`. The
integer form has only this exact interval record:

```text
inclusive_minimum
inclusive_maximum
decimal_digit_count
ordered_constant_affine_region_ids
```

The interval is nonempty. Every integer in it has the same canonical decimal
width and the same truth/piecewise-affine region for every ordered ancestor
expression; intervals are maximal and strictly ordered. The catalog form has
only a lowercase SHA-256 catalog ID and zero-based position.

`MaximumDerivedStateCatalogV1` has exactly:

```text
catalog_version
catalog_kind
defining_subject_locator
defining_value_schema_id | null
ordered_observable_descriptor_ids
ordered_catalog_entries
```

The version is
`riskyieldmm.raw_v8_step2_external_schema_v2.maximum_state_catalog.v1`.
`catalog_kind` is exactly `TEXT_RELATION_SLICE`, `ARRAY_ORDER_PREFIX`, or
`ARRAY_UNIQUENESS_SET`. Each entry has exactly:

```text
catalog_position
ordered_partition_atoms
ordered_partition_state_cells
canonical_representative_atom | null
ordered_attainable_length_bitmap_runs
```

Positions are contiguous from zero. Entry keys are the pair
`(ordered_partition_atoms, ordered_partition_state_cells)`; entries are unique
and strictly ordered by the compact-canonical bytes of that two-member array,
then assigned positions. State cells inside an entry may reference only already
derived child catalogs, never the catalog being defined or a later catalog.
Runs have Section 4.1's exact grammar and are the complete attainable lengths
for the class. The checker derives the following exact kind payloads:

| Catalog kind | Partition atoms | Partition state cells | Representative |
|---|---|---|---|
| `TEXT_RELATION_SLICE` | one exact Boolean per text-reading predicate in rule/application then expression order | empty | least admitted exact `TEXT` in that truth class |
| `ARRAY_ORDER_PREFIX` | one exact safe-integer cardinality atom | empty at cardinality zero, otherwise the complete last-item child state key | least exact last-item primitive when that child cell is singleton, otherwise null |
| `ARRAY_UNIQUENESS_SET` | cardinality atom followed by strictly increasing exact catalog-position atoms for every used finite child value | the corresponding complete child cells in that same order | null |

`ARRAY_UNIQUENESS_SET` is legal only when the complete finite child value
catalog fits the bootstrap limits; an unrestricted/raw text uniqueness domain
must use the Section 7.6 safe upper plus Section 7.11 exact reinstatement.
`ARRAY_ORDER_PREFIX` retains the last-item class because every future strict-
order decision depends only on it; if another ancestor reads more history,
those additional child cells appear in the complete child state key rather
than an undocumented payload. Inside a derived relation catalog, a finite text
enum is an exact `TEXT` `ordered_partition_atom`; a relation class uses
`TEXT_RELATION_SLICE`. Neither makes `TEXT` a pre-prefix frontier cell. For the
primitive objective, a literal/finite-enum text uses a frozen
`CATALOG_POSITION` coordinate, while a noncatalog text language becomes an
exact `TEXT` atom only at its active prefix node through prefix feasibility.

The catalog ID is the semantic ID under
`RiskYieldMMA2MStep2ExternalSchemaV2MaximumDerivedStateCatalogV1V4_9F_RawV8`
over `maximum_protocol_sha256` followed by every catalog member above. This is
the exact compact-canonical ID preimage; it is not a hash of a host tuple or an
entry-only array. Catalog records are not trusted opaque data: the checker
rebuilds the whole root during the defining local transfer, recomputes its ID,
and accepts a cell position only against that root. The full root's compact
bytes and entry count are charged once per defining occurrence.

`MaximumDerivedStateCatalogV1` is a deterministic verifier-internal object; it
is not embedded as a second producer-controlled certificate member. A
materialized output carries only its recomputed catalog ID and position in each
applicable cell. The checker retains the complete internal root from its
defining transfer through the last live materialized frontier or alias-resolved
frontier containing one of its cells. Because an entry may itself contain cells
from earlier catalogs, liveness is the complete acyclic prior-catalog reference
closure: a child catalog remains live while any live frontier, live derived-
catalog entry, or current transient recurrence key/payload directly or
transitively references it. Every unique defining-occurrence root in that
closure is charged once in the simultaneous peak. The checker charges entries
and compact bytes once at definition. Certificate canonical octets exclude the
internal root because it is not serialized there. An ID without the
independently rebuilt complete root, a position outside that root, a cycle, or
early release of a transitive child rejects.

Transient DP work that does not appear in an output cell uses
`MaximumTransientRecurrenceCatalogV1`, with exactly:

```text
catalog_version
recurrence_kind
defining_subject_locator
recurrence_parameters
ordered_scalar_prefix_records
ordered_primitive_prefix_records
ordered_lex_interval_records
ordered_state_records
recurrence_catalog_id
```

`catalog_version` is
`riskyieldmm.raw_v8_step2_external_schema_v2.maximum_transient_recurrence_catalog.v1`.
`recurrence_kind` is exactly `ASCII_DFA_DYNAMIC_PROGRAM_V1`,
`UNICODE_15_NFC_DYNAMIC_PROGRAM_V1`,
`ORDERED_RAW_STRING_PREFIX_FEASIBILITY_V1`, or
`DERIVED_IDENTITY_PREFIX_FEASIBILITY_V1`. The parameter record and state layout
are the exact kind-specific forms in Sections 9.1, 9.2.1, and 9.3.1; no other
string, atom position, nullable slot, or host cache state is legal.

`MaximumScalarPrefixRecordV1` has exactly:

```text
prefix_position
parent_prefix_position | null
appended_scalar_value | null
appended_scalar_repeat_count
scalar_count
json_value_octets
```

Position zero is the unique empty prefix and has null parent/scalar and all
three counts zero. Every later record has an earlier nonnegative parent, one
non-surrogate Unicode scalar, a positive repeat count, and checked counts equal
to its parent plus that homogeneous run's exact scalar/JSON cost. Adjacent runs
with the same scalar are forbidden; a run is extended by replacing it with the
unique larger-repeat record over the same parent, not by chaining an equal
scalar.

`json_value_octets` is the exact number of compact-canonical JSON bytes
contributed by the reconstructed scalar sequence *inside* the two surrounding
quotation marks; the quotes are excluded. For every nonempty record it is:

```text
parent.json_value_octets
+ appended_scalar_repeat_count
  * canonical_json_scalar_value_octet_cost(appended_scalar_value)
```

with checked multiplication and addition before assignment to a nonnegative
safe integer. The scalar cost is 2 for U+0022, U+005C, U+0008, U+0009,
U+000A, U+000C, and U+000D; 6 for every other U+0000..U+001F scalar; 1 for
every other U+0020..U+007F scalar; 2 for U+0080..U+07FF; 3 for
U+0800..U+FFFF excluding surrogates; and 4 for U+10000..U+10FFFF. A complete
JSON string therefore has canonical length `json_value_octets + 2`.

For a concrete scalar sequence, its canonical scalar-prefix path is its
maximal run-length encoding: starting at position zero, exactly one record per
maximal homogeneous run, whose parent is the preceding run-boundary record and
whose repeat count is that complete run length. The pool is exactly the union
of those paths for every scalar sequence referenced by recurrence parameters,
interval blocks, state keys, or state payloads. “Prefix closure” means closure
under record parent links, not one record per scalar inside a homogeneous run.
If another independently referenced sequence ends partway through a run, its
final record uses the same parent and scalar with its own shorter complete
repeat count; it never chains an equal-scalar record. Reconstructed sequences
are unique and no unused record is legal. After the empty record, records are
strictly ordered by `(scalar_count, reconstructed Unicode-scalar sequence)`
and assigned contiguous zero-based positions. Comparison operates directly on
RLE runs without expanding repeats and never uses numeric prefix position. An
ASCII recurrence additionally requires every scalar `<=127`.

`MaximumPrimitivePrefixRecordV1` has exactly:

```text
prefix_position
parent_prefix_position | null
appended_choice_coordinate_plan_id | null
appended_atom | null
active_atom_count
```

Position zero is the empty active prefix. A later record has an earlier parent,
one exact plan ID, one non-`INACTIVE` atom, and count one above its parent.
The array is the used prefix closure, ordered after zero by `(active_atom_count,
reconstructed typed primitive vector)` with contiguous zero-based positions.

`MaximumRawLexIntervalRecordV1` has exactly
`interval_position, ordered_interval_blocks`. Each block has exactly:

```text
block_position
block_kind
prefix_position
inclusive_next_scalar_minimum | null
inclusive_next_scalar_maximum | null
repeated_lower_bound_scalar | null
minimum_retained_repeat_count | null
maximum_retained_repeat_count | null
```

Kinds `PREFIX_SINGLETON`, `PREFIX_SUBTREE`, and
`STRICT_EXTENSION_SUBTREE` have all five trailing nullable members null.
`NEXT_SCALAR_RANGE_SUBTREES` has two non-null ordered range scalars, null repeat
members, and never crosses a JSON-cost class or surrogate gap.
`HOMOGENEOUS_ANCESTOR_DIVERGENCE_RUN` has null next-scalar ranges and non-null
repeated scalar/minimum/maximum repeat counts. Its prefix is the concrete prefix
before one homogeneous run of the lower-bound string; for every retained-repeat
count from maximum down to minimum it denotes all subtrees obtained by retaining
that many copies and then choosing any valid scalar strictly greater than the
repeated lower-bound scalar. Let the source run be `(ell,h)`, where `h >= 1`,
let `B` be the JSON-value-octet cost before it, let `V` be the bounded
JSON-value-octet ceiling, and let `mu(ell)` be the least JSON scalar cost among
valid scalars strictly greater than `ell`. If the block exists, its exact safe-
integer range is:

```text
minimum_retained_repeat_count = 0
maximum_retained_repeat_count =
  min(h - 1, floor((V - B - mu(ell)) / json_cost(ell)))
```

Existence requires `ell < U+10FFFF`, `V - B >= mu(ell)`, and therefore a
nonnegative maximum. Retaining zero copies is the valid divergence at the
first scalar of the source run, not an empty block. Retaining all `h` copies is
excluded because that case belongs to the earlier strict-extension block. A
positive minimum, maximum above `h-1`, omitted zero candidate, or
producer-selected subrange rejects. The implicit next-scalar ranges are
independently split by JSON-cost class and surrogate gap in increasing scalar
order.
Prefix positions resolve through the scalar pool; full growing text is
forbidden in a block or state key. The language strictly greater than a concrete
RLE prefix has its strict-extension block iff at least one bounded extension is
possible, followed by one homogeneous-ancestor block per source run having a
nonempty bounded retained-repeat range, in right-to-left run order. A
U+10FFFF run has no greater-scalar subtree and is omitted.
Expanding one block per scalar position or emitting an empty ancestor block is
noncanonical. One canonical empty interval is permitted.
Within a nonempty interval, block positions are contiguous one-based.
Unique block arrays are sorted by their complete compact-canonical bytes and
assigned contiguous zero-based positions.

Pool legality is exact:

| Recurrence kind | Scalar prefixes | Primitive prefixes | Lex intervals |
|---|---:|---:|---:|
| `ASCII_DFA_DYNAMIC_PROGRAM_V1` | required | empty | empty |
| `UNICODE_15_NFC_DYNAMIC_PROGRAM_V1` | required | empty | empty |
| `ORDERED_RAW_STRING_PREFIX_FEASIBILITY_V1` | required | empty | required |
| `DERIVED_IDENTITY_PREFIX_FEASIBILITY_V1` | empty | required | empty |

A state record has exactly:

```text
state_position
ordered_state_key_atoms
ordered_state_key_cells
ordered_state_payload_atoms
ordered_state_payload_cells
ordered_attainable_length_bitmap_runs
```

Positions are contiguous one-based. Records are unique and strictly ordered by
the compact-canonical two-member key array, then assigned positions; payload
does not influence order and must equal the one independently derived result
for that key. The checker enumerates transition contributions in each
kind-specific printed order, groups byte-equal complete key atom/cell arrays,
and emits exactly one state per group. Runs merge by set union and Section
4.1 normalization. Scalar/identity payloads retain the least reconstructed
prefix; saturated counts use checked saturation; Boolean support uses exact
support union/convolution; and unrank decisions use Boolean OR while retaining
the least true completion. Duplicate output keys, an unmerged contribution, a
nonleast payload, or merging unequal keys rejects.

The catalog ID semantic domain is
`RiskYieldMMA2MStep2ExternalSchemaV2MaximumTransientRecurrenceCatalogV1V4_9F_RawV8`
over `maximum_protocol_sha256` and every preceding root member. The checker
recomputes `recurrence_catalog_id`. The full compact root, prefix/interval
records, and state records contribute to state-catalog entries and compact
bytes at that defining node. Unlike the two verifier-internal derived catalog
families, a transient recurrence root is embedded in its node derivation, so
its serialized bytes also occur naturally in certificate canonical octets and
the enclosing node-ID preimage. For state-catalog peak it is live throughout
that node's recurrence, output, commitment, and node-ID validation and is then
released; any copied child state cell keeps its independently defined child
catalog live, not this transient root. The transient root itself is never an
opaque output-cell catalog and is not retained merely because its proof node
has a later parent.

The
cell ID semantic domain over all preceding members is
`RiskYieldMMA2MStep2ExternalSchemaV2MaximumStateCellV1V4_9F_RawV8`.

Each affine-region ID is independently derived under
`RiskYieldMMA2MStep2ExternalSchemaV2MaximumAffineRegionV1V4_9F_RawV8` over the
exact payload `source_constraint_id, ordered_expression_positions,
ordered_input_subject_locators, ordered_inclusive_input_intervals,
derived_truth_value, derived_decimal_digit_count`. Input intervals use safe
integer endpoints; the last two fields have verifier-derived nullability. The
checker obtains the affine coefficients from the already-pinned typed
expression DAG and proves, with checked UInt128 endpoint arithmetic, that no
overflow, comparison root, or digit boundary lies inside the cell. The
certificate cannot supply coefficients or an unverified region label.

A state key is an array of cells with cardinality/order equal to its state
signature. Cells denote a disjoint exact partition of the underlying values,
not a relaxation and not a representative value. Canonical state-key order is
lexicographic comparison of each cell's compact canonical bytes; this order is
only an encoding rule and never the primitive tie-break. A measured/context choice
vector is an array of primitive atoms in exact active-coordinate order. The
canonical bitmap frontier is an array, in lexicographic state-key order, of
exact records:

```text
state_key
ordered_length_bitmap_runs
```

whose runs have the exact three-member shape in Section 4.1. The
`canonical_bitmap_run_frontier_sha256` is SHA-256 of that complete compact
canonical JSON array.

The expanded frontier is a compact canonical JSON array of exact records:

```text
state_key
canonical_byte_length
```

ordered first by state key and then increasing byte length. It contains one
record for every set bitmap bit. Its SHA-256 is
`expanded_frontier_sha256`. Both arrays may be streamed byte-for-byte, but
streaming must produce the same brackets, commas, keys, scalars, and UTF-8 as
materialization. `frontier_canonicalized_octets` charges both complete array
preimages.

The two winner digests are SHA-256 of the compact canonical JSON arrays for the
unique measured/context prefix-exclusion winners. Comparison uses the typed
rules from correction Section 11.3, not canonical bytes or hashes. This exact
preimage prevents an implementation-defined tuple/repr/hash from becoming
proof authority.

## 5. Canonical proof plan

The verifier derives the only permitted plan. The producer cannot choose node
order, omit a dependency, introduce a helper node, or select a more favorable
normalization.

1. Resolve the row's exact measurement binding and scope profile.
2. Perform a top-down budget pass from all measured, nested, and owner codec
   coordinates, subtracting exact syntax and proven sibling minima, and freeze
   one inclusive effective ceiling for every plan occurrence.
3. Expand the measured descriptor and every constructed context descriptor in
   dependency postorder. Record members use increasing `member_position`;
   array items follow their item schema; union alternatives use increasing
   `alternative_position`.
4. Add each payload-dependent derived-identity fixed node immediately after all
   of its identity-payload children.
5. Add attached intrinsic rules in dependency postorder.
6. Add owner, fixture, or root-scope transfers.
7. Add applications in lexical `application_name` order and increasing
   invocation ordinal, exactly matching the frozen schedule.
8. Add the exact maximum-slice node and one lexicographic prefix-exclusion node
   per measured then context choice coordinate.
9. For an ordinary or prospective byte-maximum certificate, add one
   codec-intersection/attainment root.

A local-shutdown minimality plan is the one explicit exception to step 9. Its
position 1 is the exact baseline-spec `FIXED_VALUE` node defined in Section
7.13; the local root derives the eleven mutable schema domains and five
intrinsic relations from the pinned authorities rather than treating a
producer frontier as a mutation-domain oracle. The plan next derives each
independently rooted prospective byte-maximum subcertificate in canonical
candidate order, then adds one `LOCAL_SHUTDOWN_MINIMALITY_FRONTIER` node as the
last and sole root of the local certificate. It never wraps that root in a
codec-attainment node.

Node positions are contiguous one-based integers. Every child position is
strictly less than its parent. The root is the last node. Every node is
reachable from that single root. Duplicate, forward, cyclic, unreachable, or
noncanonical plans reject before frontier evaluation.

### 5.1 Exact schema-minimum and ceiling pass

The top-down budget pass uses one verifier-owned schema-only lower-bound
function `schema_minimum_octets`. It deliberately ignores intrinsic and
cross-record constraints, so it can only make a child ceiling looser, never
exclude a legal value. Its recursion is exact: a fixed value uses its measured
compact length; Boolean/integer/text use the least length in their frozen
scalar language; derived identities use the 66-byte compact JSON spelling of a
64-character lowercase hexadecimal ID; nullable uses `min(4, child_minimum)`;
an array takes the minimum over every legal cardinality of brackets, commas,
and item minima; a record adds braces, commas, each compact-canonical member
name plus colon, and member minima; and a tagged union adds the exact registry
tag/wrapper syntax plus the selected alternative minimum. All sums use checked
UInt128 and must fit the safe protocol integer before publication.

The initial inclusive ceiling for a validation root is the minimum of `L-1`
for every applicable `LT L` codec, `L` for every `LE L` codec, and 16,777,215
as the artifact fallback. In a
`PROSPECTIVE_BYTE_MAXIMUM_WITH_ONE_MASKED_OUTER_CODEC` subplan, the checker
first proves that the requested mask byte-equals the one permitted Section 6.1
coordinate, then excludes exactly that coordinate from both this initial
minimum and every descendant/owner ceiling intersection. No syntax octet,
nested codec, distinct owner codec, rule, or application is excluded. An
ordinary byte-maximum plan requires a null mask and excludes nothing. This
exclusion occurs before the top-down pass, so a prospective frontier is not
incorrectly capped at 524,287 before testing whether it reaches 524,288.

For a record-member edge:

```text
child_ceiling = parent_ceiling
  - record_braces_commas_and_all_member_name_colon_octets
  - sum(schema_minimum_octets(other_required_member))
```

For array item position `i`, compute the analogous brackets/commas/other-item
subtraction for every legal cardinality containing `i` and take the largest
result. Nullable passes its ceiling unchanged to the non-null child. A union
subtracts its exact tag/wrapper syntax. Constraint/scope/prefix nodes preserve
the incoming ceiling. Every child then takes the minimum with all of its own
nested or owner codec ceilings other than that one authenticated masked
coordinate. Negative or below-schema-minimum results denote
an empty frontier. Subtraction occurs only after checked comparison, so an
unsigned underflow rejects.

Derived-identity payload children are dependency edges, not serialization
nesting. Their ceilings come from their ordinary record-member occurrences and
are not tightened by the fixed 66-byte identity output. The identity node's
own effective ceiling is exactly 66, or the surrounding member ceiling when
smaller, which makes that record frontier empty.

The validation-root descriptor, selected typed path, legal cardinality set,
member-name bytes, and codec coordinates come only from the registry,
measurement binding, and scope profile. There is no producer-supplied sibling
minimum or discretionary allocation. The checker recomputes every node's
`effective_canonical_octet_ceiling` from this recurrence.

## 6. Closed certificate records

All records below are exact-key records. Unknown, missing, reordered logical
members, Boolean-as-integer, float, non-finite value, integer outside the safe
I-JSON range, duplicate JSON key, or noncanonical scalar rejects.

Every ordinary JSON integer is an exact safe integer. The two quantities that
can exceed that domain, root `sum_absolute_integer_deltas` and
`winning_objective.sum_of_absolute_integer_deltas`, are instead canonical
unsigned-128 decimal text matching exactly `0|[1-9][0-9]{0,38}` and no value
greater than `340282366920938463463374607431768211455`. The checker parses them
digit by digit with checked UInt128 arithmetic. No other decimal-text integer
is admitted. This closes the Python-unbounded-integer versus I-JSON ambiguity.

### 6.1 Typed proof and retained-value locators

A path step has exactly:

```text
step_position
step_kind
member_name | null
member_position | null
array_ordinal | null
sequence_name | null
union_alternative_position | null
nullable_branch | null
```

`step_kind` is `RECORD_MEMBER`, `ARRAY_ITEM`, `EXTERNAL_SEQUENCE_ITEM`,
`UNION_ALTERNATIVE`, or `NULLABLE_BRANCH`. Exactly the fields required by the
kind are non-null. Positions are contiguous one-based. `ARRAY_ITEM` may have a
null ordinal only for a `SCHEMA_DOMAIN` symbolic item; a retained value always
has an exact zero-based ordinal. `nullable_branch` is `NULL` or `NON_NULL`.
Multiple nested arrays/sequences therefore use multiple typed steps rather
than one ambiguous global ordinal.

`MaximumProofSubjectLocatorV1` has exactly:

```text
locator_kind
record_reference_id | null
root_type_name | null
root_value_schema_id | null
ordered_path_steps
transient_state_key | null
transient_source_child_position | null
transient_source_child_proof_node_id | null
```

`locator_kind` is `SCHEMA_DOMAIN`, `WITNESS_RECORD`, `CONTEXT_OBJECT`,
`V3_INVENTORY_POINTER`, or `TRANSIENT_FRONTIER_STATE`. The checker derives the
exact nullability combination from this closed table:

| Locator kind | record reference | root type | root value schema | path | transient state/source |
|---|---|---|---|---|---|
| `SCHEMA_DOMAIN` | null | non-null | non-null | descriptor-valid; symbolic array ordinals allowed | all null |
| `WITNESS_RECORD` | non-null | non-null | null | retained-value concrete | all null |
| `CONTEXT_OBJECT` | non-null | non-null | null | retained-value concrete | all null |
| `V3_INVENTORY_POINTER` | non-null | non-null | null | retained-value concrete | all null |
| `TRANSIENT_FRONTIER_STATE` | null | null | null | empty | all three non-null |

For every descriptor-traversal root, `SCHEMA_DOMAIN.root_value_schema_id` is
the verifier-derived non-null self-reference schema from the exact eleven-
member `ValueSchemaV2` grammar:

```text
schema_kind = OBJECT_REF
nullable = false
boolean_literal = null
integer_minimum = null
integer_maximum = null
text_language_id = null
array_minimum_items = null
array_maximum_items = null
array_item_value_schema_id = null
referenced_type_name = <traversal-root type name>
value_schema_id = semantic ID of the ten preceding members under
  RiskYieldMMA2MStep2ValueSchemaV2V4_9F_RawV8
```

The root type resolves to exactly one pinned external-type descriptor. If the
computed schema occurs in `value_schema_catalog`, it must byte-equal that
entry. Absence is legal because this is a verifier-derived locator anchor, not
a new admitted runtime member schema. A nullable catalog entry for the same
type is not the self anchor. The checker derives the complete type-name/self-
schema index once from the accepted registry snapshot; it neither changes the
registry nor charges those authority-initialization hashes to a certificate.
The measured traversal uses the row's exact type, while each constructed-
context occurrence uses that record's exact type. Repeated occurrences may
therefore have byte-equal locators; plan position and guard ancestry preserve
occurrence identity.

For the transient form, `transient_state_key` is non-null and both source
position/ID fields are non-null; every other form has all three transient
fields null. Schema-domain locators can address absent
nullable/union alternatives and symbolic array items. Transient locators bind
one complete Section 4.3 state key and the exact position/ID of one
already-verified child output; both transient-source fields are non-null only
for that kind. For record locators, `record_reference_id` resolves through the
enclosing row/pilot scope context or, in a local-shutdown certificate, through
the baseline pointer and the checker-derived inline mutated-spec/prospective-
result `WITNESS_RECORD` references plus the exact boundary-witness catalog in
the local root. A boundary root may resolve only the catalog entry that names
its own proof-node position.

The `record_reference_id` scalar grammar is kind-specific for both proof and
retained-value locators. `WITNESS_RECORD` and `CONTEXT_OBJECT` use the exact
lowercase SHA-256 `maximum_record_reference_id` of the independently resolved
correction Section 11.3 reference; local inline records first receive that same
checker-derived reference record and ID. `V3_INVENTORY_POINTER` instead uses
the exact nonempty absolute RFC 6901 JSON Pointer selected by the accepted
profile. It starts with `/`, permits only `~0` and `~1` escapes, and is resolved
after unescaping against the once-read accepted V3 inventory; it is not a
SHA-256 or a URI fragment. `SCHEMA_DOMAIN`, `TRANSIENT_FRONTIER_STATE`, and
`SCOPE_WITNESS_CONTEXT` have null record references as their tables require.
No generic “nonempty text or SHA” fallback is legal.

Before validating any proof or retained-value locator, the checker derives one
exact correction Section 11.3 `WITNESS_RECORD` reference for the complete
inline witness. When the row descriptor has a non-null identity field, the
reference uses that exact field and independently recomputed identity. For a
nested identity-less record or tagged-union row it instead uses:

```text
record_identity_field = "$canonical_sha256"
record_identity = record_canonical_sha256
```

`$canonical_sha256` is a reserved WITNESS-only sentinel, never a runtime member
path, and is forbidden in `CONTEXT_OBJECT` and `V3_INVENTORY_POINTER` forms.
The checker recomputes the complete witness length/SHA and validates a tagged-
union witness against the row's exact non-null `alternative_name`.
`record_type_name` remains the declared row type, including a union. Every
serialized witness reference in the leaf and every witness locator must reuse
that byte-equal derived reference and ID.

`MaximumRetainedValueLocatorV1`, used by choice evidence, has exactly:

```text
retained_source_kind
record_reference_id | null
root_type_name | null
scope_context_member_name | null
ordered_path_steps
projection_kind
```

`retained_source_kind` is `WITNESS_RECORD`, `CONTEXT_OBJECT`,
`V3_INVENTORY_POINTER`, or `SCOPE_WITNESS_CONTEXT`. The first three require a
non-null record-reference scalar and root type and have null scope member:
`WITNESS_RECORD`/`CONTEXT_OBJECT` use the maximum-reference SHA ID, while
`V3_INVENTORY_POINTER` uses the preceding RFC 6901 pointer grammar. The context form
requires a null record-reference/root type and one exact first-level member
name from the frozen scope-context variant. Every step then resolves a complete
retained value. `projection_kind` is exactly `VALUE`, `NULLABILITY_BRANCH`,
`ARRAY_CARDINALITY`, `UNION_ALTERNATIVE_POSITION`, or
`FROZEN_CATALOG_POSITION`; the checker derives which projection is legal from
the coordinate kind. Root-family and sequence positions resolve from scope
context; mode/attempt and observation-role positions resolve from retained
observation fields. The locator cannot address a schema domain, absent branch,
or transient proof state.

Every `measurement_binding` occurrence is the exact five-member record frozen
in correction Section 11.2 (`binding_kind`, `validation_root_type_name`,
`measured_value_typed_member_path`, `sequence_binding_name`, and
`sequence_ordinal`) with the exact six-form null/path table defined there. It
is never replaced by a proof locator.

`MaximumCodecCoordinateV1`, used only where a codec is explicitly named or
masked, has exactly:

```text
validation_root_type_name
codec_owner_type_name
codec_owner_typed_member_path
codec_byte_bound_relation
codec_octet_limit
```

The typed member path is an array of exact member-name strings relative to the
validation root. The relation is `LT` or `LE` and the limit is a positive safe
integer. The local-shutdown masked coordinate is exactly validation/owner type
`CapacityMeasurementOperationResultEvidence`, empty path, relation `LT`, and
limit `524288`. `masked_outer_codec_coordinate` and
`masked_codec_coordinate` contain that byte-equal record in the two
prospective/local-shutdown nodes; every ordinary byte-maximum node has a null
mask.

### 6.2 State-dimension record

Each dimension has exactly:

```text
dimension_position
dimension_kind
subject_locator
value_schema_id | null
comparison_semantics
ordered_activation_guard_clauses
observable_descriptor_id
```

Positions are contiguous one-based integers. `dimension_kind` is one of
Section 4.2. `comparison_semantics` is derived and exactly one of
`NULL_BEFORE_NON_NULL`, `FALSE_BEFORE_TRUE`, `MATHEMATICAL_INTEGER`,
`UNICODE_SCALAR_LEXICAL`, `CARDINALITY_THEN_ITEMS`, or
`FROZEN_CATALOG_POSITION`, or `CANONICAL_OCTET_LEXICAL`.

An unconditionally present ordinary dimension has an empty activation-guard
array. An ordinary dimension below a nullable non-null branch, union
alternative, maximum-cardinality array item, or scope case copies the complete
corresponding guarded choice-coordinate clauses from Section 6.5; nested
branches concatenate their clauses in plan order without duplicates.
Choice-prefix dimensions use their coordinate plan's exact clauses. The
descriptor ID covers the guard array as a preceding member.

The dimension-to-cell mapping is exact:

| Dimension kind | Permitted cell |
|---|---|
| `NULLABILITY_BRANCH` | exact `POSITION`, `0=NULL`, `1=NON_NULL` |
| `BOOLEAN_VALUE` | exact `BOOLEAN` |
| `SAFE_INTEGER_VALUE` | maximal `SAFE_INTEGER_INTERVAL`; exact `SAFE_INTEGER` after its prefix exclusion |
| `TEXT_RELATION_CLASS` | verifier-derived text-slice catalog position |
| `TEXT_CANONICAL_LENGTH` | exact `SAFE_INTEGER` |
| `TEXT_VALUE` | exact `TEXT`; this dimension appears only at/after its active prefix node |
| `ARRAY_CARDINALITY` | exact `SAFE_INTEGER` because every descriptor cardinality set is finite |
| `ARRAY_ORDER_CLASS` | verifier-derived ordered-array DP catalog position |
| `ARRAY_UNIQUENESS_CLASS` | verifier-derived uniqueness DP catalog position |
| `UNION_ALTERNATIVE_POSITION` | exact zero-based `POSITION` in descriptor order |
| `CATALOG_POSITION` | exact zero-based `POSITION` in the named frozen catalog |
| `ROOT_FAMILY_POSITION` | exact one-based `POSITION` in profile order |
| `MODE_ATTEMPT_POSITION` | exact one-based `POSITION` in the selected family |
| `OBSERVATION_ROLE_POSITION` | exact one-based `POSITION` in the selected mode/attempt pair |
| `SEQUENCE_ORDINAL` | exact zero-based `POSITION` |

For an ordinary dimension with a nonempty guard, a false guard requires an
`INACTIVE_GUARD_SENTINEL` state cell and a true guard requires exactly the
table's cell; unguarded dimensions and appended active prefix dimensions reject
the sentinel. The checker evaluates ordinary guards against the same
state's earlier structural branch/cardinality/shape atoms through their plan
IDs. At a false-guard choice prefix, `INACTIVE` occurs only as the node's
selected atom and that node adds no tie-break dimension. An active prefix
exclusion splits the applicable
interval/slice at the least feasible exact primitive or obtains the least
exact text from the closed prefix-feasibility recurrence, appends a distinct
exact tie-break dimension/cell for the retained branch, and proves every
smaller subcell empty under the already fixed prefix. Any ordinary dimension
for the same subject remains in its original position; the appended exact
dimension is intentionally not merged with it. The guarded choice-coordinate
catalog may contain a future `TEXT_VALUE` even though an earlier output state
signature does not; choice plans and frontier state dimensions are distinct
records.

For `TEXT_RELATION_CLASS`, the checker orders all predicates that read the text
by rule/application evaluation order then expression position, evaluates the
complete false-before-true Boolean truth vector, removes unattainable vectors,
and assigns their remaining vectors zero-based lexicographic positions inside
the complete derived text-slice catalog. Array order/uniqueness catalogs retain
the exact child catalog positions or canonical bytes required by their DP and
are rebuilt during local transfer. There is therefore no producer-named class
vocabulary or hidden host tuple.

The descriptor ID domain over every preceding member is:

```text
RiskYieldMMA2MStep2ExternalSchemaV2MaximumObservableDescriptorV1V4_9F_RawV8
```

The state-signature semantic domain is:

```text
RiskYieldMMA2MStep2ExternalSchemaV2MaximumStateSignatureV1V4_9F_RawV8
```

over `ordered_state_dimensions`. Empty signatures are legal and have a
recomputed ID.

### 6.3 Output frontier

`MaximumOutputFrontierV1` has exactly:

```text
frontier_encoding_kind
materialized_frontier | null
direct_child_alias | null
```

`frontier_encoding_kind` is exactly `MATERIALIZED` or `DIRECT_CHILD_ALIAS`.
The materialized form has a non-null `materialized_frontier` and null alias;
the alias form has a non-null alias and null materialized member. A materialized
frontier has exactly:

```text
frontier_soundness
state_signature_id
ordered_observable_descriptor_ids
ordered_state_frontiers
```

`frontier_soundness` is `EXACT_ATTAINABLE` or `SAFE_UPPER_DOMAIN`. The ordered
descriptor IDs are semantic IDs of the complete Section 6.2 dimension records
and have exact equality with the node's ordered dimensions. Each state frontier
has exactly:

```text
state_key
ordered_length_bitmap_runs
```

The state key uses Section 4.3 state cells and matches the signature kind by
kind. Exact-atom, interval, and catalog cells are accepted only where the
dimension-to-cell table below permits them.
State frontiers are strictly increasing under the Section 4.3 canonical
state-cell byte comparison,
unique, and nonempty. Runs have the exact Section 4.1 shape/order/normalization.
An empty frontier is the empty state-frontier array. The checker validates each
materialized output locally from its derivation and already-verified children;
matching hashes without matching, valid complete output rejects.

`direct_child_alias` has exactly:

```text
aliased_child_position
aliased_child_proof_node_id
resolved_materialized_origin_position
```

The alias is mandatory and legal only (a) on an `INACTIVE`
`LEXICOGRAPHIC_PREFIX_EXCLUSION`, where it names
`input_prefix_frontier_child_position`, or (b) on
`CODEC_INTERSECTION_ATTAINMENT`, where it names
`winner_frontier_child_position`. Every other node, including every active
prefix node, must use `MATERIALIZED`. The aliased position/ID must be an exact
pair in the common child arrays and must byte-equal the named derivation child.
The child has already passed node-ID and local-output validation because every
child position is strictly earlier. If the child is materialized,
`resolved_materialized_origin_position` equals that child position; if it is an
alias, the field equals the child's already checked resolved origin. That
origin is earlier and materialized. Forward aliases, sibling aliases, skipped
edges, producer-chosen origins, cycles, and aliases at any other derivation
reject.

The semantic output of an alias is the immutable materialized frontier at its
resolved origin; it is not a second copy and has the child's exact soundness,
signature, descriptors, state keys, and length runs. During proof-position
validation the checker stores the child's resolved-origin handle, compares it
in constant work, and passes that handle forward. It never recursively walks
an alias chain and never redecodes, reallocates, recanonicalizes, or rehashes
the origin frontier. The direct authenticated edge and already verified child
object establish equality; digest equality alone is insufficient. Thus alias
depth is structurally bounded by proof depth while validation work remains one
alias check per alias node. The checker derives alias depth as zero for a
materialized output and checked `child_alias_depth + 1` for an alias; it is not
producer data. It rejects before following or retaining a reference if depth
would exceed the recomputed proof depth, proof-node count, or either accepted
cap. Iterative proof-position resolution is mandatory; recursive host-language
descent is forbidden.

### 6.4 Frontier commitment

`MaximumFrontierCommitmentV1` has exactly:

```text
frontier_version
state_signature_id
state_entry_count
bitmap_run_count
expanded_attainable_point_count
minimum_attainable_octets
maximum_attainable_octets
expanded_frontier_sha256
canonical_bitmap_run_frontier_sha256
least_measured_choice_vector_sha256_at_maximum
least_context_choice_vector_sha256_at_maximum
frontier_commitment_id
```

`frontier_version` is
`riskyieldmm.raw_v8_step2_external_schema_v2.attainable_frontier.v1`.
Counts and extrema are recomputed. An empty frontier is represented by zero
counts and null extrema/all four digests. A nonempty frontier has positive
counts and non-null extrema plus the two frontier digests. Both choice-vector
digests follow this exact stage table, where `EMPTY_SHA` is SHA-256 of the
compact-canonical empty array and every nonempty vector contains active atoms
only:

| Node stage | Measured digest | Context digest |
|---|---|---|
| before maximum slice | null | null |
| maximum slice | `EMPTY_SHA` iff the measured plan catalog is empty, otherwise null | `EMPTY_SHA` iff the context plan catalog is empty, otherwise null |
| measured prefix before its final plan coordinate | null | preserve the maximum-slice value |
| final measured prefix and thereafter | SHA-256 of the complete active measured atom array | preserve the prior context value until its own completion |
| context prefix before its final plan coordinate | preserve completed measured digest | null |
| final context prefix and thereafter | preserve completed measured digest | SHA-256 of the complete active context atom array |
| local-shutdown minimality root | null | null |
| codec root | byte-equal winner-child digests | byte-equal winner-child digests |

This stage table is local to each distinct maximum-slice chain, including every
boundary subcertificate beneath a local-minimality DAG. “Final” means the
final plan coordinate in that scope, not the final active coordinate. The
digest preimage is the compact-canonical array of complete typed primitive atom
objects in increasing plan position, excluding false-guard `INACTIVE` atoms
and all evidence wrappers. `fixed_active_prefix_coordinate_count` equals the
number of active measured plus active context atoms processed so far. It is
derived from the verifier-owned plans and guard results, never from a producer
increment.

The local-shutdown root certifies one mutation objective over several
independently rooted prospective byte-maximum subcertificates; it is not one
measured/context primitive winner. Its own two choice-vector digests are
therefore null. Every boundary codec root retains and validates its own two
winner digests, and the boundary witness binds its own active choice evidence.

An inactive final coordinate still completes its scope and hashes the possibly
empty active array. Therefore an entirely empty choice catalog receives both
`EMPTY_SHA` values at the maximum slice and the codec root can copy that
commitment without a special rewrite. Measured and context are distinct field-
construction events: when both catalogs are empty, the checker processes the
two-byte `[]` preimage twice and charges four hash-preimage octets. A preserved
completed digest, later inactive alias, and codec copy never rehash the array.
The semantic identity domain over every
preceding member is:

```text
RiskYieldMMA2MStep2ExternalSchemaV2MaximumFrontierCommitmentV1V4_9F_RawV8
```

The expanded and bitmap-run digests are both required: the first pins exact
semantic points; the second pins the unique compressed
representation.
The producer cannot provide either frontier as executable or opaque data.

For `MATERIALIZED`, the checker recomputes every commitment member from that
materialized frontier and the node stage. For `DIRECT_CHILD_ALIAS`,
`state_signature_id`, all three counts, both extrema, and both frontier digests
must be byte-equal to the aliased child's already checked commitment; the two
choice-vector digests are independently derived from the current node's stage
table and fixed active prefix. The checker then recomputes the complete current
commitment ID. An inactive final plan coordinate may therefore change one
choice digest while preserving the aliased semantic frontier. The codec root
must preserve both winner-child choice digests and consequently has a
byte-equal complete commitment. No alias causes either frontier digest preimage
to be processed again.

### 6.5 Primitive choice coordinate

The verifier first derives `MaximumChoiceCoordinatePlanV1`, with exactly:

```text
coordinate_plan_position
coordinate_scope
coordinate_kind
subject_locator
value_schema_id | null
ordered_activation_guard_clauses
choice_coordinate_plan_id
```

The plan ID domain over every preceding member is:

```text
RiskYieldMMA2MStep2ExternalSchemaV2MaximumChoiceCoordinatePlanV1V4_9F_RawV8
```

It contains no selected value and creates no edge to row evidence. The exact
maximum-slice/prefix nodes bind only these plan IDs, preserving identity
acyclicity.

Each activation guard clause has exactly:

```text
guard_clause_position
prior_choice_coordinate_plan_id
guard_operator
guard_atom
```

Clause positions are contiguous; the referenced plan position is strictly
earlier. `guard_operator` is `EQUALS` or
`ARRAY_CARDINALITY_GREATER_THAN`. The former activates nullable, union, and
scope branches when the prior atom equals the exact branch/catalog atom. The
latter activates zero-based array item `i` when the prior cardinality atom is
greater than `i`. Guard atoms use Section 4.3. Clauses are ANDed in plan order.
If a referenced prior coordinate's prefix node is `INACTIVE`, either operator
evaluates false without comparing `INACTIVE` to the guard atom; remaining AND
clauses are still validated in clause order. Thus inactivity propagates
through every guarded descendant without making `INACTIVE` a typed value.
The verifier emits one depth-first plan over maximum array cardinalities and
every nullable, union, and scope alternative; a false guard places `INACTIVE`
in that coordinate's later prefix-node `selected_atom` and contributes no
appended tie-break dimension. Independently, guarded ordinary dimensions use
their Section 4.3 `INACTIVE_GUARD_SENTINEL` cell. Every shape decision
precedes its descendants, so two vectors are already ordered before differing
activity can matter. The
checker never compares `INACTIVE` with an active atom as a tie-break value; if
activity differs, an earlier guard coordinate must already have decided order.

The choice-coordinate emission algorithm is exhaustive and has no
producer-selected exclusions. It first traverses the measured record, then the
constructed context. Descriptor-backed coordinates use a `SCHEMA_DOMAIN`
subject locator rooted at the validation occurrence's verifier-derived Section
6.1 non-null self-reference schema and the complete typed path to that
occurrence; concrete
maximum-cardinality item ordinals distinguish array occurrences. Their
`value_schema_id` is that occurrence's value-schema ID, except a type-level
tagged-union alternative has null. Synthetic scope coordinates use a
`V3_INVENTORY_POINTER` locator whose `record_reference_id` is the exact RFC
6901 pointer to the selected profile in
`/operation_contracts/maximum_constraint_scope_profile_catalog`, whose
`root_type_name` is the profile's measured type, and whose path is empty; their
value-schema ID is null. Repeated synthetic axes remain distinct through plan
position and guards even when those anchor locators are byte-equal.

| Source domain in traversal order | Coordinate emitted | Activation and recursion |
|---|---|---|
| fixed schema literal, frozen authority value, discriminator consequence, derived identity/hash/path/record/proof ID, or any legal singleton domain | none | recurse only into a fixed non-scalar child; never create evidence for the fixed value |
| nullable with both branches legal | `NULLABLE_BRANCH` | emit branch first; recurse into non-null child guarded by `EQUALS POSITION(1)` |
| nullable with one legal branch | none | recurse unguarded only when that branch is non-null |
| unrestricted Boolean domain | `BOOLEAN_VALUE` | no child recursion |
| safe-integer interval containing at least two values | `SAFE_INTEGER_VALUE` | no child recursion |
| noncatalog text language containing at least two values | `TEXT_VALUE` | no child recursion |
| frozen literal/enum catalog containing at least two legal values, regardless of scalar base type | `CATALOG_POSITION` | catalog descriptor order, zero-based; no child recursion |
| array with at least two legal cardinalities | `ARRAY_CARDINALITY` | emit cardinality first; expand item positions through the maximum, guarding item `i` by `ARRAY_CARDINALITY_GREATER_THAN i` |
| fixed-cardinality array | none | recurse through exactly that many item positions without a cardinality guard |
| record | none | recurse through members in increasing `member_position` |
| tagged union with at least two legal alternatives | `UNION_ALTERNATIVE_POSITION` | emit alternative first; recurse through each alternative in descriptor order guarded by its zero-based `EQUALS POSITION` atom |
| tagged union with one legal alternative | none | recurse through that alternative unguarded |
| scope with at least two admissible root families | `ROOT_FAMILY_POSITION` | profile order, one-based; each family's descendants carry its equality guard |
| family with at least two admissible mode/attempt pairs | `MODE_ATTEMPT_POSITION` | family order, one-based; descendants carry all outer guards plus this equality guard |
| mode/attempt pair with at least two measured roles | `OBSERVATION_ROLE_POSITION` | role order, one-based; descendants carry all outer guards plus this equality guard |
| measured external sequence with at least two eligible ordinals | `SEQUENCE_ORDINAL` | numerical order, zero-based source ordinal; each referenced context-record subtree carries the ordinal equality guard |

“Legal” in this table means the pre-search
`authority_substituted_plan_domain`, derived only from the pinned unary
`ValueSchemaV2`, exact row type and root alternative, fixed canonical-envelope
literals, fixed discriminator consequences, fixed V3 authorities/aliases, and
a scalar or branch value byte-equal in every scope case admitted by the
selected profile. It must not depend on codec survival, intrinsic or
application truth, witness bytes, frontier contents, solver output, or
producer evidence. Only a domain proven singleton by those authority inputs
omits a coordinate. A structurally multi-valued coordinate remains even when
later exact constraints leave one or zero feasible values.

Measured descriptor coordinates and synthetic scope axes remain distinct
objective dimensions even when both project from the same witness. A
synthetic axis does not suppress a structurally multi-valued measured
occurrence. This preserves all measured positions before all context positions
and prevents a measured guard from referring to a later synthetic plan. In a
singleton checkpoint profile, profile-fixed mode/role/branch values are
authority singletons and emit neither descriptor nor synthetic coordinates.
For a non-checkpoint profile, values varying across admitted cases retain the
measured occurrence and the later synthetic axis separately orders the
constructed context case. A constructed record already beneath one exact case
guard treats that case's fixed values as singleton consequences.

When the row's root descriptor is `TAGGED_UNION`, its non-null
`alternative_name` must name exactly one alternative. That alternative is row
authority and emits no root `UNION_ALTERNATIVE_POSITION`. Traversal starts in
the selected referenced type through one unguarded `UNION_ALTERNATIVE` path
step using the descriptor's one-based alternative position; its owner
discriminator literals are fixed consequences. A nested union not fixed by
row identity or another authority substitution retains the ordinary
multi-alternative coordinate, zero-based atom, and guarded descendants.

For a scope axis with one admissible position, no synthetic coordinate is
emitted and descendants inherit only outer guards. Scope expansion is exactly
this nested order:

```text
derive measured descriptor plan
if the profile has at least two root families:
  emit ROOT_FAMILY_POSITION
for root family in profile order:
  if the family has at least two mode/attempt pairs:
    emit MODE_ATTEMPT_POSITION guarded by the selected root family, if any
  for mode/attempt pair in family order:
    if the family has at least two measured roles:
      emit OBSERVATION_ROLE_POSITION guarded by the selected root and pair axes
    for measured role in family order:
      derive eligible ordinals in numerical order
      if at least two ordinals are eligible:
        emit SEQUENCE_ORDINAL guarded by the selected root, pair, and role axes
      for eligible ordinal in numerical order:
        emit the resulting scope case
        traverse constructed context occurrences
```

Root-family, mode/attempt, and role atoms are one-based; sequence ordinals are
zero-based. Every descendant carries all emitted outer guards in plan order,
and flattened `scope_case_position` follows the same loops. A checkpoint
profile contributes its exact selector ordinal. For
`ORDINARY_BEFORE_CHECKPOINTS_AFTER_AGGREGATE_V1`, `BEFORE_OPERATION` maps to
ordinal zero, stable checkpoint position `p` maps to `p`, `AFTER_OPERATION`
maps to `selector_length + 1`, and `OPERATION_AGGREGATE` maps to
`selector_length + 2`. `STARTUP_RECOVERY_ONE_V1` has only ordinal zero.

Per scope case, constructed records occur in this exact order:

```text
SELF_VALUE: no constructed record
OWNER_MEMBER: owner record; measured payload subtree is an alias
OUTER_RESULT_APPLICATION: no constructed record; result is the measured alias
ROOT_APPLICATION: root record, then every non-witness observation in
                  increasing zero-based ordinal
```

V3 operation specs, selectors, target registries, and marker contracts emit no
descriptor coordinates. Within each constructed record, traversal follows
member position, array ordinal, then union alternative position. Storage-level
content deduplication does not hash-cons plan occurrences; repeated root or
observation occurrences remain distinct. All measured plan positions precede
all context positions. The resulting positions are contiguous, every path is
visited exactly once per occurrence, and the plan-ID array is an exact pre-
search value.

Every synthetic plan coordinate uses a `V3_INVENTORY_POINTER` proof locator
whose `record_reference_id` is exactly
`/operation_contracts/maximum_constraint_scope_profile_catalog/<profile_position-1>`,
whose root type is the profile's measured type, whose root value-schema ID is
null, whose path is empty, and whose transient fields are null. This is a
proof-locator authority pointer, not a `MaximumRecordReferenceV1` and not one
of the profile's `ordered_source_authority_pointers`.

Root-family and sequence evidence use `SCOPE_WITNESS_CONTEXT`, null reference
and root type, empty path, `FROZEN_CATALOG_POSITION`, and respectively the
exact first-level member `selected_root_family_position` or
`measured_sequence_ordinal`. The former resolves a checked one-based
`POSITION`; the latter resolves a checked zero-based source-ordinal
`POSITION`.

Mode/attempt and role evidence use the independently derived measured
`WITNESS_RECORD` reference rooted at `TargetObservationV2`, null scope member,
and `FROZEN_CATALOG_POSITION`. Mode/attempt follows the exact member-position-4
path `observation_context`; role continues through that record's member-
position-4 `observation_role`. For `MODE_ATTEMPT_POSITION`, the checker forms
`[observation_context.instrumentation_mode, "NULL" if attempt_id is null else
"NON_NULL"]`, requires exactly one byte-equal item in the selected family's
ordered pair catalog, and emits one-based `POSITION(index+1)`. For
`OBSERVATION_ROLE_POSITION`, it maps the retained role to exactly one item of
the selected family's role catalog and emits its one-based position. A scalar-
only mode locator, producer pair/position, root-metadata substitute, missing or
duplicate match, wrong member position, or wrong base rejects.

An ordinary structurally guarded dimension uses the same clauses as the
coordinate emitted for its governing nullable/cardinality/union/scope shape.
If a governing shape has a singleton domain and emitted no coordinate, its
descendants have no clause for that shape. An unknown schema form, ambiguous
external-type-reference root, absent profile pointer, catalog with no frozen
order, or domain whose exact cardinality cannot be decided is protocol NO-GO.

Each `ordered_component_choice_evidence` item has exactly:

```text
evidence_position
coordinate_plan_position
coordinate_scope
coordinate_kind
subject_locator
value_schema_id | null
ordered_activation_guard_clauses
choice_coordinate_plan_id
selected_value_kind
selected_value_locator
selected_canonical_byte_length
selected_canonical_sha256
supporting_proof_node_position
component_choice_coordinate_id
```

`coordinate_scope` is `MEASURED_RECORD` or `CONSTRUCTED_CONTEXT`.
`coordinate_kind` is derived and exactly `NULLABLE_BRANCH`, `BOOLEAN_VALUE`,
`SAFE_INTEGER_VALUE`, `TEXT_VALUE`, `ARRAY_CARDINALITY`, `CATALOG_POSITION`,
`UNION_ALTERNATIVE_POSITION`, `ROOT_FAMILY_POSITION`,
`MODE_ATTEMPT_POSITION`, `OBSERVATION_ROLE_POSITION`, or `SEQUENCE_ORDINAL`.
`selected_value_kind` is exactly `RESOLVED_RETAINED_VALUE`.
`selected_value_locator` is an exact `MaximumRetainedValueLocatorV1`; scalar
and large values are both resolved from retained records and never duplicated.
The plan fields and plan ID equal the independently derived active plan at
`coordinate_plan_position`.

`selected_canonical_byte_length` and `selected_canonical_sha256` cover the
compact-canonical `MaximumTypedPrimitiveAtomV1` obtained after applying the
locator's projection, not the enclosing retained object and not a catalog
position record. The checker resolves the retained value, derives that atom,
re-encodes it, and requires exact length/hash equality. This rule is identical
for scalar, nullability, cardinality, frozen-catalog, union, root-family, mode/attempt,
observation-role, and sequence-ordinal coordinates.

For an active prefix, the plan-to-dimension and atom mapping is closed:

| Coordinate kind | Appended dimension kind | Comparison semantics | Exact atom kind |
|---|---|---|---|
| `NULLABLE_BRANCH` | `NULLABILITY_BRANCH` | `NULL_BEFORE_NON_NULL` | `POSITION`, `0=NULL`, `1=NON_NULL` |
| `BOOLEAN_VALUE` | `BOOLEAN_VALUE` | `FALSE_BEFORE_TRUE` | `BOOLEAN` |
| `SAFE_INTEGER_VALUE` | `SAFE_INTEGER_VALUE` | `MATHEMATICAL_INTEGER` | `SAFE_INTEGER` |
| `TEXT_VALUE` | `TEXT_VALUE` | `UNICODE_SCALAR_LEXICAL` | `TEXT` |
| `ARRAY_CARDINALITY` | `ARRAY_CARDINALITY` | `CARDINALITY_THEN_ITEMS` | `SAFE_INTEGER` |
| `CATALOG_POSITION` | `CATALOG_POSITION` | `FROZEN_CATALOG_POSITION` | zero-based `POSITION` |
| `UNION_ALTERNATIVE_POSITION` | `UNION_ALTERNATIVE_POSITION` | `FROZEN_CATALOG_POSITION` | zero-based `POSITION` |
| `ROOT_FAMILY_POSITION` | `ROOT_FAMILY_POSITION` | `FROZEN_CATALOG_POSITION` | one-based `POSITION` |
| `MODE_ATTEMPT_POSITION` | `MODE_ATTEMPT_POSITION` | `FROZEN_CATALOG_POSITION` | one-based `POSITION` |
| `OBSERVATION_ROLE_POSITION` | `OBSERVATION_ROLE_POSITION` | `FROZEN_CATALOG_POSITION` | one-based `POSITION` |
| `SEQUENCE_ORDINAL` | `SEQUENCE_ORDINAL` | `FROZEN_CATALOG_POSITION` | zero-based `POSITION` |

The appended dimension copies the plan's subject locator, value-schema ID,
and guard clauses byte-for-byte, receives position `input_dimension_count +
1`, uses the table's kind/comparison, and has its descriptor ID recomputed.
Its state cell is `EXACT_ATOM` containing the table's atom. A different atom
kind, zero/one-based convention, dimension kind, comparison, locator, schema,
guard, position, or ID rejects.

The coordinate ID domain over every preceding member is:

```text
RiskYieldMMA2MStep2ExternalSchemaV2MaximumComponentChoiceCoordinateV1V4_9F_RawV8
```

Plan positions are contiguous one-based. Evidence positions are contiguous
one-based over only the winner's active coordinates; their plan positions are
strictly increasing and contain every and only true-guard plan. Prefix nodes
exist for every guarded plan coordinate. A false-guard prefix node carries the
exact `INACTIVE` atom and is a checked no-op; it has no retained evidence item.
The maximum-slice frontier contains no choice-plan dimensions: it proves exact
target-length existence under the empty primitive prefix. Each active prefix
node appends one exact dimension in plan order; an inactive node appends none.
Winner digests are over the active atom arrays only and must equal the root
frontier digests. This preserves the correction's variable-length array/union
vectors without a producer-selected shape and keeps the complete plan/node
count structural before search.

`ordered_choice_coordinate_plan_ids` in the maximum-slice derivation is
byte-equal to the complete independently derived plan catalog in contiguous
`coordinate_plan_position` order, including false-guard coordinates. The
prefix chain contains exactly that many nodes and position `p` binds plan ID
`p`. Every active prefix node has exactly one component-evidence item whose
`supporting_proof_node_position` is that node's position and whose plan fields,
resolved selected atom, canonical atom length, and canonical atom SHA-256 all
byte-equal the node derivation. No inactive prefix has evidence, and an
evidence item cannot point to a maximum-slice, later prefix, codec root, or any
other node.

### 6.6 Proof resource claim

The resource claim has exactly:

```text
proof_node_count
proof_edge_count
maximum_proof_depth
maximum_child_count
state_signature_dimension_count
maximum_state_signature_dimension_count
state_catalog_entry_count
state_catalog_canonicalized_octets
peak_retained_state_catalog_octets
frontier_state_entry_count
frontier_bitmap_run_count
frontier_expanded_point_count
maximum_frontier_width
peak_retained_frontier_octets
frontier_transition_count
frontier_canonicalized_octets
hash_preimage_octets
component_choice_coordinate_count
certificate_canonical_octets
```

All values are independently recomputed over the complete DAG. Count fields
named as totals are checked sums; fields named as maxima are checked maxima.
They are deterministic proof-kernel units, not wall-clock, CPU, or
resident-memory claims.
Leaf depth is one; parent depth is one plus maximum child depth.
`state_signature_dimension_count` is the sum across nodes, while
`maximum_state_signature_dimension_count` is the largest one-node count.
The sum has no separate Section 14 cap because it is already bounded by the
checked product of proof-node count and maximum one-node dimension count; it
remains in the claim as an exact accounting cross-check.
`state_catalog_entry_count` and `state_catalog_canonicalized_octets` sum every
complete verifier-derived catalog and its compact preimage once per defining
node. Entry count means derived-state `ordered_catalog_entries`, identity-
mapping `ordered_mapping_records`, and every transient scalar-prefix,
primitive-prefix, lex-interval, and state record, including mandatory empty-
prefix records; catalog root metadata is not an additional entry. Canonicalized
octets mean the compact bytes of the complete catalog root exactly once. Its
semantic-ID envelope is charged separately to `hash_preimage_octets`.
`peak_retained_state_catalog_octets` follows the same last-parent release
schedule as frontiers and includes the complete transitive prior-catalog
reference closure required to interpret every live frontier cell, live catalog
entry, and current recurrence key/payload. Each defining occurrence is charged
once in a simultaneous live set. Recomputing a released catalog instead of
retaining it does not reduce the charged peak or total.
`component_choice_coordinate_count` is the sum, once for every distinct
`MAXIMUM_SLICE_EXACT_FRONTIER` in the complete certificate DAG, of the exact
size of that slice's independently derived complete guarded coordinate-plan
catalog. It includes every false-guard coordinate and equals both the slice's
`ordered_choice_coordinate_plan_ids` length and the number of prefix nodes in
that slice's complete chain. It is not the active retained-evidence length.
A local-minimality DAG therefore sums every embedded boundary subplan; its
local root adds no separate component coordinate. The checker enforces the
applicable count cap before materializing the plan catalog or prefix chain.
`maximum_frontier_width` is the largest number of exact state/length points
in the resolved semantic output at a node boundary, including an aliased
output. `frontier_state_entry_count`, `frontier_bitmap_run_count`, and
`frontier_expanded_point_count` sum entries/runs/points only when their unique
`MATERIALIZED` encoding is validated; a `DIRECT_CHILD_ALIAS` contributes zero
to those three sums because it creates no list, run, or expanded point.
`hash_preimage_octets` charges
every complete semantic-ID and raw SHA preimage processed by the certificate
kernel, including repeated preimages. Counts are incremented and checked
before the corresponding list/index/allocation is created.
`peak_retained_frontier_octets` is the largest checked sum of compact canonical
bytes for simultaneously live materialized frontier objects, alias records,
and frontier commitments under this exact schedule:
visit nodes in proof position order; retain every child until its last common-
parent position; charge the child set, then child set plus the newly validated
output; release a child immediately after that node when no later common parent
names it. A live alias keeps one reference to its materialized origin, so that
origin is retained until the last live descendant alias is released, but its
materialized bytes are charged once regardless of alias count. Each alias
record is charged separately at its exact compact-canonical width; its embedded
origin position is the complete logical handle and no host-pointer width is
charged or trusted. Each node's frontier commitment is a separate live object
retained only through that node's own last common parent. A descendant alias
extends the materialized origin frontier's lifetime, but never the origin
node's commitment lifetime because the alias carries its own complete
commitment. Encoding and commitment lifetimes are therefore metered
independently before summing the peak. The empty live set is zero. This is deterministic allocation
evidence, not RSS.

`frontier_transition_count` charges one for each attempted semantic recurrence
or local state/length candidate before deduplication. Literal/enumeration leaves
charge each admitted candidate; a closed-form scalar language charges each
derived band/transition; ASCII DFA work charges every
`(input_position, source_state, admitted_byte)` transition; Unicode work
charges every `(input_position, source_state, maximal scalar-equivalence
class)` transition; and raw strings charge every JSON-cost/scalar-order class
transition. The complete transient scalar-recurrence state catalog, including
states that emit no frontier point, is also included in state-catalog counts
and canonicalized octets. Nullable charges each null/non-null candidate;
arrays each child-point/item-point/cardinality convolution or ordered-language
prefix-feasibility transition; records each Cartesian child-point combination;
unions, constraints, maximum-slice, prefix-exclusion, and codec intersections
each visited child point. Scope charges one base case-lift transition for every
visited child point plus one additional transition for each ordered
`(child point, application invocation)` pair; a legal case with zero
applications therefore still charges its lift. Local
minimality charges every derived breakpoint extension and every symbolic
interval-exclusion check, exactly matching the complete records mandated by
Section 7.13. A safe relaxation still visits and charges every input point it
actually consumes, while a bootstrap decision made from the closed saturated
bound is charged as one strategy test and never attempts the ruled-out exact
allocation. No implementation-specific loop or hash-table probe is charged.

A mandatory direct-child alias adds exactly one alias-validation transition
after its child has been validated. That transition checks the direct edge,
child ID, resolved origin, permitted derivation kind/activation, resolved
signature/descriptors, and commitment-copy rules. An inactive prefix performs
no frontier-point transfer beyond that one check. A codec root still charges
every upper-child point/codec intersection required to prove the endpoint and
then the one winner-alias check; aliasing its output never erases that work. An
alias cannot be selected where the derivation changes a frontier.

`frontier_canonicalized_octets` is the sum, once per `MATERIALIZED` output, of
the exact complete bitmap-frontier preimage plus complete expanded-frontier
preimage from Section 4.3. A direct-child alias contributes zero because those
preimages were processed at its resolved materialized origin; its own record is
charged by certificate bytes, peak retained bytes, its proof-node-ID preimage,
and its one transition. An empty materialized frontier contributes exactly four
canonicalized octets for the two compact `[]` preimages. Its frontier digest
fields are null, so neither empty preimage is passed to SHA-256 and neither is
charged to `hash_preimage_octets`.

`hash_preimage_octets` is the sum, once per certificate validation, of this
closed event catalog in canonical verifier order:

1. the complete canonical semantic-ID envelope for every independently
   recomputed certificate-contained object, referenced retained record,
   verifier-internal derived-state/identity catalog, embedded transient-
   recurrence catalog, affine region, descriptor, state signature, frontier
   commitment, coordinate plan, component evidence item, proof node,
   proof-scope/context authority, boundary witness, local recurrence record
   carrying an ID, and certificate;
2. the complete four-member canonical semantic-ID envelope for every concrete
   terminal candidate evaluated by
   `DERIVED_IDENTITY_PREFIX_FEASIBILITY_V1`, in printed recurrence order and
   before key merging or enclosing-constraint rejection, including candidates
   later merged or rejected; recomputation of a retained witness, catalog, or
   other ID-bearing certificate-contained object is a separate event under
   item 1, while recomputation of an exact mapping-record identity envelope is
   one separate repeated event under item 3, even when its bytes equal a
   candidate envelope;
3. each canonical raw-SHA preimage in this exhaustive field map at the exact
   occurrence whose field is checked: `fixed_canonical_sha256` hashes the
   resolved fixed value; component evidence `selected_canonical_sha256` hashes
   its complete selected atom; each mapping record first hashes the decoded
   complete `semantic_identity_preimage_canonical_bytes_hex` bytes to obtain
   `derived_identity_text`, then
   `derived_identity_canonical_sha256` hashes that compact JSON identity text;
   `equivalence_state_key_sha256` hashes the complete compact local recurrence
   equivalence key; `attaining_witness_canonical_sha256`,
   every `prospective_result_canonical_sha256` occurrence, and every resolved
   maximum-record-reference `record_canonical_sha256` occurrence hash their
   respective complete canonical objects;
4. the expanded and bitmap frontier preimages exactly once for every nonempty
   `MATERIALIZED` output and never for an alias or empty frontier; and
5. a measured/context choice-vector preimage exactly when that digest is first
   constructed by the stage table, including the compact empty array, but not
   when a later node merely preserves or codec-copies it.

Repeated validation occurrences count repeatedly even if their bytes are
equal; cache lookups and implementation retries do not. Authority-file physical
hashing is outside the per-certificate claim. Every semantic-ID event uses the
protocol's fixed canonical envelope, so nested IDs are charged when their own
objects are recomputed and again only when their bytes naturally occur inside a
different enclosing preimage. An alias charges its current proof-node and
commitment preimages but never repeats the origin's expanded/bitmap frontier
preimages. A producer-supplied event list or repeat count is forbidden.

The certificate's own ID and length form one joint decimal-width fixed point.
Let `H0` be the exact `hash_preimage_octets` total for every event above except
the certificate's own `upper_bound_certificate_id` preimage. For nonnegative
safe integers `H` and `C`, let `U(H,C)` be the complete certificate with
`upper_bound_certificate_id` omitted and with
`proof_resource_claim.hash_preimage_octets = H` and
`proof_resource_claim.certificate_canonical_octets = C`. Define:

```text
I(H,C) = compact({
  "canonicalization_version": CANONICALIZATION_VERSION,
  "domain": CERTIFICATE_DOMAIN,
  "payload": U(H,C),
  "schema_version": MEASUREMENT_SCHEMA_VERSION
})
D(H,C) = lowercase_hex_sha256(I(H,C))
F(H,C) = U(H,C) completed with upper_bound_certificate_id = D(H,C)
```

The accepted pair is the least pair in coordinatewise order satisfying

```text
H = H0 + len(I(H,C))
C = len(compact(F(H,C)))
```

The checker finds it by monotone length-only iteration from `(0,0)`. Trial
iterations neither allocate/hash `I` nor count as hash events; the digest's
fixed 64-character width is sufficient for length calculation. Failure to
stabilize within checked safe-integer arithmetic rejects. After stabilization,
the checker prospectively checks both effective resource caps, commits the
final certificate-preimage meter increment, then materializes and hashes the
final `I(H,C)` exactly once, constructs `F(H,C)`, and
verifies its exact compact length and ID. `certificate_canonical_octets` is
therefore the actual complete certificate length, not a producer-chosen
self-consistent digit width.

That joint recurrence applies only to
`MaximumUpperBoundCertificateV1`, which embeds its resource claim. The
correction's local-shutdown minimality certificate embeds no claim and has no
self-reference: its independently metered `hash_preimage_octets` is the exact
prior event total plus its one final local-certificate-ID preimage, and its
`certificate_canonical_octets` is the direct compact length after inserting
the fixed-width ID. Both values are recorded only in the enclosing pilot or
aggregate validation measurement. Their prospective limits are checked and
meter increments committed before the final local ID preimage is hashed or the
complete local certificate is serialized.

## 7. Closed proof-node union

Every node has exactly these common members:

```text
proof_node_position
proof_node_kind
subject_locator
value_schema_id | null
type_name | null
alternative_name | null
effective_canonical_octet_ceiling
ordered_child_positions
ordered_child_proof_node_ids
ordered_ancestor_observable_dimensions
output_frontier
frontier_commitment
derivation
proof_node_id
```

The node ID domain is:

```text
RiskYieldMMA2MStep2ExternalSchemaV2MaximumProofNodeV1V4_9F_RawV8
```

Its semantic-ID payload is not the bare node. It has exactly
`maximum_protocol_sha256, proof_scope_authority_id,
proof_context_authority_id, node`, where `node` contains every common member
preceding `proof_node_id`. These inherited authorities are derived from the
enclosing artifact and cannot vary by node.

For an upper-bound certificate, `proof_scope_authority_id` is its exact
`constraint_scope_id` and `proof_context_authority_id` is its exact
`maximum_context_object_manifest_id`. For the local-shutdown certificate, the
scope authority is the semantic ID under
`RiskYieldMMA2MStep2ExternalSchemaV2LocalShutdownMaximumProofScopeV1V4_9F_RawV8`
over `maximum_protocol_sha256, source_inventory_sha256,
external_schema_registry_id, rule_literal_authority_sha256,
constraint_scope_profile_id, baseline_operation_spec_id,
ordered_mutable_limit_member_names`. Its context authority is the semantic ID
under
`RiskYieldMMA2MStep2ExternalSchemaV2LocalShutdownMaximumProofContextV1V4_9F_RawV8`
over `maximum_protocol_sha256, mutated_operation_spec_id,
prospective_result_canonical_byte_length,
prospective_result_canonical_sha256`. Those values are resolved from the
enclosing correction Section 12 counterexample before any node ID is checked.
This gives both certificate forms an acyclic, literal proof authority without
inventing a nonexistent local-shutdown context manifest.

`effective_canonical_octet_ceiling` is the verifier-derived inclusive ceiling
propagated from all ancestor/nested/owner codecs before leaf construction. For
an `LT L` coordinate it begins at `L-1`; for `LE L`, at `L`. Each descent
subtracts only exact enclosing syntax and proven minimum contributions of
other required children, then takes the minimum across ancestors. Arrays use
the largest safe per-item ceiling over all legal cardinalities; the array node
still applies exact cardinality-specific budgets. Thus an otherwise unbounded
raw-string language always has a finite proof domain.

Child positions/IDs have equal cardinality and exact positional equality to
already-verified nodes. Child positions within one node are unique; repeated
schema/context occurrences have distinct canonical proof nodes. The dimensions,
effective ceiling, resolved complete output frontier, canonical materialized-
versus-alias encoding, and commitment are checked, not trusted. `derivation`
is a finite tagged union with exactly the variant shape
below; `derivation.derivation_kind` must byte-equal `proof_node_kind`. No
`proof_payload`, note, code, expression string, solver clause,
pickle, archive, or producer extension is admitted.

The complete V1 kind order is exactly:

```text
FIXED_VALUE
BOOLEAN_VALUE_FRONTIER
SAFE_UINT_DIGIT_FRONTIER
TEXT_LANGUAGE_FRONTIER
NULLABLE_CASE_FRONTIER
ARRAY_FRONTIER
RECORD_FRONTIER
TAGGED_UNION_FRONTIER
CONSTRAINT_FRONTIER
SCOPE_FRONTIER
MAXIMUM_SLICE_EXACT_FRONTIER
LEXICOGRAPHIC_PREFIX_EXCLUSION
LOCAL_SHUTDOWN_MINIMALITY_FRONTIER
CODEC_INTERSECTION_ATTAINMENT
```

Boolean/UInt/text nodes have zero children. A fixed literal/authority node has
zero children, while a derived-identity fixed node has every identity-payload
child in member-position order. Nullable and array nodes have one; a record has
exactly one child per member in `member_position` order; a
union has exactly one child per alternative; a constraint, maximum-slice, and
prefix-exclusion node has exactly its one named input child; a scope has
exactly one named child per ordered scope case; a local-minimality recurrence
has its named baseline-domain child followed by its ordered boundary-certificate
roots; and the codec root has exactly the upper-frontier and final exact-winner
children. Every variant child-position member must equal the corresponding
common child position(s); there is no second implicit edge.

### 7.1 `FIXED_VALUE`

```text
derivation_kind
fixed_source_kind
fixed_source_locator
fixed_transfer_kind
fixed_canonical_byte_length
fixed_canonical_sha256 | null
derived_identity_mapping_catalog_id | null
ordered_identity_payload_child_positions
```

`fixed_source_kind` is `SCHEMA_LITERAL`, `FROZEN_AUTHORITY`, or
`DERIVED_IDENTITY`. The checker resolves the complete value and recomputes its
bytes. `fixed_transfer_kind` is `EXACT_FIXED_VALUE`,
`EXACT_DERIVED_IDENTITY_MAPPING`, or
`DERIVED_IDENTITY_FIXED_WIDTH_SAFE_UPPER_DOMAIN`. Literal/authority nodes use
the first, have an empty child array, a non-null raw SHA, and a null mapping-
catalog ID. A derived identity has every non-identity payload member child
required by its semantic-ID domain and that array equals the common children.
Its raw SHA is always null. The exact-derived form has a non-null mapping-
catalog ID. The safe-upper form has a null mapping ID, is selected only when
the Section 9.5 mapping-catalog bound exceeds a bootstrap limit, emits
`SAFE_UPPER_DOMAIN`, and must be named for exact maximum-slice reinstatement.
`fixed_canonical_byte_length` is independently measured for literals and
authorities and is exactly 66 for a derived lowercase-SHA-256 JSON string.

For `EXACT_DERIVED_IDENTITY_MAPPING`, the checker rebuilds
`MaximumDerivedIdentityMappingCatalogV1`, with exactly:

```text
catalog_version
defining_subject_locator
semantic_identity_domain
ordered_mapping_records
```

The version is
`riskyieldmm.raw_v8_step2_external_schema_v2.derived_identity_mapping_catalog.v1`.
Each mapping record has exactly:

```text
semantic_identity_preimage_canonical_bytes_hex
derived_identity_text
derived_identity_canonical_sha256
```

The hexadecimal field is the complete even-length lowercase encoding of the
exact compact-canonical four-member semantic-ID envelope:

```text
{
  "canonicalization_version": CANONICALIZATION_VERSION,
  "domain": <registry domain>,
  "payload": <complete payload object>,
  "schema_version": MEASUREMENT_SCHEMA_VERSION
}
```

The two version values equal the pinned protocol constants. The field is not a
digest. A legacy two-member `domain,payload` object produces the wrong accepted
record identity and rejects. Catalog records are strictly ordered by those decoded bytes and
unique. There is one record for every complete payload value, not one record
per possibly non-singleton frontier cell. The checker hashes each decoded
preimage, requires that result as the 64-character lowercase identity, hashes
that identity's compact JSON string, and rejects any missing/duplicate
preimage.

Exact mapping is selectable only when every payload child cell is singleton or
the checked product of the exact underlying values represented by its
interval/catalog cells remains within both catalog-entry and compact-byte
bootstrap limits. The strategy estimate expands underlying cell cardinality;
counting one interval as one identity is forbidden. Otherwise the checker must
select `DERIVED_IDENTITY_FIXED_WIDTH_SAFE_UPPER_DOMAIN` before materializing
the mapping. The catalog ID is the semantic ID under
`RiskYieldMMA2MStep2ExternalSchemaV2MaximumDerivedIdentityMappingCatalogV1V4_9F_RawV8`
over `maximum_protocol_sha256` and every catalog member above. It equals
`derived_identity_mapping_catalog_id`; its full compact root and entries are charged to the
Section 6.6 state-catalog counters. When an ancestor observes the identity, the
output signature carries the exact preimage's mapping catalog position;
otherwise the identity node may project every value to the common 66-byte
length while the later record transfer still recomputes the selected identity.
The later record node includes this derived child at the identity member
position. Derived identities are consequences and emit no choice coordinate.
One fixed SHA or one non-singleton state key can therefore never stand in for a
payload-dependent identity family.

Like `MaximumDerivedStateCatalogV1`, this mapping catalog is a complete
verifier-internal deterministic object rather than an embedded certificate
record. The derivation carries only its recomputed ID. The checker charges the
complete internal root once and retains it through the last node transfer or
live frontier cell that requires a mapping position; certificate canonical
octets exclude the nonserialized root. A supplied mapping ID is never accepted
without rebuilding every record from the independently resolved payload
domain.

### 7.2 `BOOLEAN_VALUE_FRONTIER`

```text
derivation_kind
ordered_boolean_values
```

For an unrestricted exact-Boolean schema the array is exactly `[false, true]`
in typed choice order. For a Boolean-literal schema it contains only that
literal. JSON byte length (`false` is five, `true` four) and choice order are
both retained; neither can be inferred from the other.

### 7.3 `SAFE_UINT_DIGIT_FRONTIER`

```text
derivation_kind
integer_minimum
integer_maximum
ordered_decimal_digit_bands
```

Each band is exactly `digit_count, inclusive_minimum, inclusive_maximum`.
Bands are verifier-derived, contiguous, nonempty intersections with the schema
domain. Negative integers are not part of the current `SAFE_INTEGER` schema.

### 7.4 `TEXT_LANGUAGE_FRONTIER`

```text
derivation_kind
text_language_id
language_kind
text_solver_kind
unicode_version | null
transient_recurrence_catalog | null
```

`text_solver_kind` is exactly `FINITE_LITERAL_ENUMERATION`,
`BUILTIN_CLOSED_FORM`, `ASCII_DFA_DYNAMIC_PROGRAM`, or
`UNICODE_15_NFC_DYNAMIC_PROGRAM`. The checker rebuilds the accepted language
and accounts for UTF-8 plus JSON quote/escape expansion. Source-string length
is never the objective. The catalog is non-null exactly for the ASCII-DFA and
Unicode-DP solver kinds and has the matching Section 4.3 recurrence kind;
finite enumeration and closed-form solvers require null.

### 7.5 `NULLABLE_CASE_FRONTIER`

```text
derivation_kind
null_branch_enabled
non_null_child_position
```

The checker unions the exact `null` point with the non-null child. It never
assumes non-null is longer.

### 7.6 `ARRAY_FRONTIER`

```text
derivation_kind
array_minimum_items
array_maximum_items
item_child_position
array_semantics
array_transfer_kind
```

`array_semantics` is verifier-derived and exactly `INDEPENDENT_REPEAT`,
`POSITIONAL`, `ORDERED_UNIQUE`, or `CARDINALITY_COUPLED`. Every legal
cardinality is considered. `array_transfer_kind` is exactly
`EXACT_ARRAY_FRONTIER` or `ORDERED_LANGUAGE_SAFE_UPPER_DOMAIN`. The latter is
permitted only for an `ORDERED_UNIQUE` array over one independently verified
text language when the exact ordering-state upper bound from Section 9.5
exceeds a bootstrap limit. It drops only ordering/uniqueness state, emits
`SAFE_UPPER_DOMAIN`, and is named for exact reinstatement by the maximum-slice
node. It is derived before constructing the infeasible exact catalog; it is
not a failed exact allocation followed by relaxation.

Commas and brackets are exact. For `EXACT_ARRAY_FRONTIER`, ordering,
uniqueness, zip equality, position identities, and ancestor-read projections
remain in state. The safe transfer performs only the exact two-axis projection
frozen in Section 4.2; all other axes remain and order/uniqueness are restored
only as transient exact recurrence state at maximum-slice/prefix evaluation.
Independent repetition is legal only when no retained rule distinguishes
positions or relates items.

### 7.7 `RECORD_FRONTIER`

```text
derivation_kind
record_type_name
ordered_member_child_positions
derived_identity_member_name | null
```

Members use exact descriptors and JSON member-name/punctuation contributions.
Canonical key sorting changes byte order but not logical choice order.
Identity members are recomputed after payload selection and never optimized.
Record/array nodes perform schema composition only; attached rule IDs occur
only in subsequent `CONSTRAINT_FRONTIER` nodes, once each in frozen order.

### 7.8 `TAGGED_UNION_FRONTIER`

```text
derivation_kind
union_type_name
ordered_alternative_child_positions
ordered_alternative_names
owner_constraint_present
```

Alternative order equals the descriptor. Owner-scoped spec/result unions
measure the selected body but retain and enforce the complete owner domain.

### 7.9 `CONSTRAINT_FRONTIER`

```text
derivation_kind
constraint_source_kind
ordered_constraint_ids
application_invocation | null
ordered_applicable_scope_case_positions
constraint_transfer_kind
relaxation_direction | null
input_frontier_child_position
```

`constraint_source_kind` is `INTRINSIC_RULE` or
`CROSS_RECORD_APPLICATION`. `constraint_transfer_kind` is exactly:

```text
FINITE_STATE_FILTER
BOUNDED_LINEAR_FRONTIER
EXACT_RULE_EVALUATION
SAFE_UPPER_DOMAIN_RELAXATION
```

A safe relaxation has `relaxation_direction = LEGAL_DOMAIN_SUPERSET`, preserves
the input frontier or widens it by a verifier-owned rule, and can never filter
or replace a state with a smaller domain. All other transfers have null
relaxation direction. `ordered_constraint_ids` has exactly one item. One frozen
intrinsic rule or scheduled application invocation produces exactly one
constraint node. `application_invocation` is null for an intrinsic rule and is
the exact Section 7.10 three-member record for a cross-record invocation;
the applicable-case array is empty for an intrinsic rule and the nonempty
strictly increasing exact scope-case positions for that invocation otherwise.
`input_frontier_child_position` is its sole common child.
`EXACT_RULE_EVALUATION` is the complex-state exact transfer, while
`FINITE_STATE_FILTER` is the primitive finite-state transfer.
For a cross-record node, the transfer applies the invocation to every and only
state whose scope-case position occurs in
`ordered_applicable_scope_case_positions`; every state belonging to a
non-applicable scope case is copied byte-for-byte to the output before global
frontier normalization. Filtering, widening, or charging an invocation against
a non-applicable case rejects. Thus the union-of-invocations plan neither drops
nor re-evaluates cases whose schedules differ.

### 7.10 `SCOPE_FRONTIER`

```text
derivation_kind
constraint_scope
constraint_scope_id
constraint_scope_profile_id | null
measurement_binding
ordered_scope_cases
scope_transfer_kind
```

Each scope case has exactly:

```text
scope_case_position
root_family_position | null
mode_attempt_pair_position | null
observation_role_position | null
measured_sequence_ordinal | null
ordered_application_invocations
scope_case_child_position
```

Positions are contiguous and derived from profile order. A non-checkpoint
profile enumerates every admissible family, every listed mode/attempt pair,
every admitted measured role, every matching ordinal, and its exact differing
schedule. A checkpoint profile enumerates its one fixed coordinate with all
profile-permitted context cases. Owner/fixture/intrinsic scopes use their exact
singleton cases. No selected family/ordinal appears here; selection is
attainment evidence in the codec root and row context.

An application invocation has exactly
`application_name, application_invocation_ordinal,
bound_observation_ordinal`, with the exact zero-based/null semantics frozen in
correction Section 11.3. Each scope case's named child denotes the complete
resolved record/context case before its exact schedule is applied by subsequent
one-invocation `CONSTRAINT_FRONTIER` nodes. The scope node validates and retains
the schedule metadata but does not also execute it. Common
children equal `scope_case_child_position` in case order.
The later application-node catalog is the unique union of these invocation
tuples ordered by `application_name`, invocation ordinal, then null-before-
integer bound ordinal; each node records every case in which that tuple occurs.

`scope_transfer_kind` is `INTRINSIC_SELF`, `OWNER_MEMBER`,
`OUTER_RESULT_APPLICATION`, or `ROOT_APPLICATION`. All fields are derived from
the row and V3 profile. The checker resolves complete records before applying
the later exact constraint-node schedule. No context hash substitutes for a
record.

### 7.11 `MAXIMUM_SLICE_EXACT_FRONTIER`

```text
derivation_kind
target_canonical_byte_length
ordered_exact_constraint_bindings
ordered_exact_domain_reinstatement_node_positions
ordered_choice_coordinate_plan_ids
ordered_transient_recurrence_catalogs
upper_frontier_child_position
```

Each exact constraint binding has exactly `constraint_id,
application_invocation, ordered_applicable_scope_case_positions`; the latter
two fields use the exact Section 7.9 null/array rules. Bindings follow the
canonical constraint-node order and retain repeated application IDs at
distinct invocations.

`ordered_exact_domain_reinstatement_node_positions` is the strictly increasing
complete list of earlier safe descriptor-transfer nodes: exactly
`FIXED_VALUE/DERIVED_IDENTITY_FIXED_WIDTH_SAFE_UPPER_DOMAIN` and
`ARRAY_FRONTIER/ORDERED_LANGUAGE_SAFE_UPPER_DOMAIN`. The checker rejects a
safe descriptor node not named here or an exact node named here. For a safe
identity it invokes `DERIVED_IDENTITY_PREFIX_FEASIBILITY_V1`: propagate exact
semantic-preimage equality/inequality relations over the already fixed payload
prefix, enumerate the remaining bounded payload frontier in canonical plan
order, recompute every concrete candidate identity with the pinned domain, and
return the exact attainable target-length bitmap plus least completing payload.
It canonicalizes partial payload states exactly as Section 9.3.1 requires:
byte-equal complete recurrence keys must collapse to one record retaining the
least completing payload, and unequal keys must never collapse. Every
state/hash preimage is charged, and exceeding a cap is NO-GO rather than an
assumed hash preimage or collision rule.

For each safe array the checker invokes one
`ORDERED_RAW_STRING_PREFIX_FEASIBILITY_V1` root. Under the empty maximum-slice
prefix, and at any active prefix node before or selecting this array's
cardinality coordinate, its query kind is `ALL_LEGAL_CARDINALITIES`; one final
Boolean count frontier proves the exact feasible-cardinality subset and the
cardinality node selects its least feasible atom. This is not 512 repeated
catalog roots or a hidden producer loop. At every later prefix node, the query
kind is `FIXED_CARDINALITY` and its one non-null `array_cardinality` equals the
already fixed atom. `fixed_item_count` and the ordered scalar-prefix positions are exactly
the earlier active item coordinates for that array. The recurrence's only
state, saturation, interval, polynomial, bulk-prefix, ordering, and accounting
semantics are Section 9.2.1. The retained array is then fully re-evaluated item
by item for language membership, strict order, uniqueness, exact bytes, and
every ancestor constraint.

`ordered_transient_recurrence_catalogs` contains every safe-identity root and
exactly one root per invoked safe-array node, ordered by the named safe
proof-node position; an identity/array tie is resolved by recurrence-kind text.
No other root is admitted. An active prefix node contains the roots invoked
under its fixed active prefix in that same order. An inactive prefix node has
an empty catalog array and does not rerun a recurrence. These embedded roots
are covered by the proof-node ID and every catalog byte/count is charged once.

The verifier derives an unserialized `presence_guard(s)` for every safe
reinstatement node `s` from the complete structural and choice traversal. It
contains every nullable non-null branch, union alternative, scope case,
containing-array cardinality, and other shape decision required for that
occurrence to exist. For the assignments fixed through active prefix `p`, a
safe node is viable exactly when at least one legal complete plan assignment
extends that prefix and makes its presence guard true. A referenced inactive
coordinate makes its guard clause false; unresolved later coordinates remain
unknown. The maximum slice invokes every structurally reachable safe node. An
active prefix invokes every and only viable safe node; a definitely false
subtree is absent, while an unresolved but potentially live subtree remains.
An inactive prefix always invokes none because it only checks its mandatory
alias, even when an unrelated safe node remains viable. Each expected
occurrence appears exactly once, sorted by `(safe proof-node position,
recurrence-kind text)`; omission, addition, duplication, reordering, or reuse
rejects.

For a safe-array cardinality coordinate at plan position `k`, the maximum
slice and every active prefix through and including position `k` use
`ALL_LEGAL_CARDINALITIES`: that coordinate was not fixed before the invoking
node. A later active prefix uses `FIXED_CARDINALITY` with the exact earlier
atom, including zero. Fixed item positions contain every and only earlier
active item coordinates; the item currently being unranked is not fixed yet.
Every recurrence occurrence is metered separately at its defining node. A
definitely false subtree and an inactive prefix add no recurrence charge, but
the inactive prefix retains its one alias-validation transition and every
false-guard coordinate remains in `component_choice_coordinate_count`.

The child may be a safe upper-domain frontier. This node retains only the
target length, reinstates every named descriptor relaxation and exactly
evaluates every intrinsic/application constraint in frozen order under the
empty primitive prefix. Its state signature contains exactly the resulting
ordinary ancestor-observable dimensions and no choice-plan dimension. Exact
safe-array order/uniqueness and safe-identity mapping/relation recurrence state
is consumed transiently here and is not re-added to that signature; every
nonprojected ordinary dimension remains. Its
output is `EXACT_ATTAINABLE`; safe reinstatements emit their exact completing
subset or the closed symbolic singleton accepted by the applicable recurrence.
It is an explicit checked frontier, never a Boolean `maximum_slice_exact`
assertion. The following prefix chain, not this node, materializes exact
tie-break atoms.

### 7.12 `LEXICOGRAPHIC_PREFIX_EXCLUSION`

```text
derivation_kind
target_canonical_byte_length
choice_scope
choice_coordinate_plan_id
coordinate_activation
fixed_prefix_coordinate_count
fixed_active_prefix_coordinate_count
selected_atom
ordered_transient_recurrence_catalogs
input_prefix_frontier_child_position
```

These one-child nodes form one chain in coordinate order. The first names the
exact maximum-slice node and every later node names the preceding prefix node.
There is exactly one node for every plan coordinate, including a false guard,
so `fixed_prefix_coordinate_count` equals the current coordinate-plan position
and increases by one at every node. `coordinate_activation` is `ACTIVE` or
`INACTIVE`, derived by evaluating that plan's guard against already fixed
earlier coordinates. `choice_scope` is byte-equal to that plan's scope, and
`target_canonical_byte_length` is byte-equal to the maximum-slice target and
the input frontier's sole attainable length. Digest stage is derived from the
resolved plan scope, never trusted from this repeated field. For `INACTIVE`,
the whole child frontier must share the
false guard, `selected_atom` is the exact Section 4.3 `INACTIVE` atom,
`fixed_active_prefix_coordinate_count` is unchanged, and output equals input
semantically through the mandatory Section 6.3 direct-child alias. The alias
record and current proof-node ID differ, and the current commitment is
recomputed under Section 6.4; the materialized frontier is not copied. For
`ACTIVE`, the whole
child frontier must share the true guard, active count increases by one, and
the checker proves `selected_atom` is the least atom with any exact legal
target-length completion under the fixed prefix. Its output state signature is
the input signature followed by the dimension derived from that coordinate
plan, every output key is the retained input key followed by the exact selected
atom cell, and no earlier dimension is removed, reordered, merged, or replaced.

The maximum-slice node performs the exact reinstatement calculus once with the
empty primitive prefix to prove target-length existence. Each active prefix
node deterministically reruns the same calculus with the already fixed active
prefix and uses finite scanning or the named derived-identity/ordered-string
feasibility recurrence to unrank the least completing atom; an inactive node
does not rerun it. The node emits the exact completing subset or its closed
symbolic singleton when a safe transfer is being reinstated. The final measured
then final context plan node leaves the unique deterministic primitive-vector
winner. Deleting a guarded node, accepting mixed guard truth in one node, or
deleting a losing smaller-prefix completion changes the local transfer and
fails verification.

### 7.13 `LOCAL_SHUTDOWN_MINIMALITY_FRONTIER`

```text
derivation_kind
baseline_spec_record_reference
ordered_mutable_limit_member_names
ordered_intrinsic_relation_ids
prospective_result_attainment_mode
masked_outer_codec_coordinate
baseline_result_inventory_json_pointer
baseline_result_canonical_byte_length
outer_codec_byte_bound_relation
outer_codec_octet_limit
winning_objective
prospective_result_canonical_byte_length
prospective_result_canonical_sha256
baseline_spec_fixed_child_position
ordered_boundary_candidate_root_positions
ordered_boundary_candidate_witness_records
ordered_breakpoint_records
ordered_interval_exclusion_records
ordered_recurrence_state_records
ordered_recurrence_transition_records
ordered_dominance_deletion_records
recurrence_version
```

The exact recurrence version is
`LEXICAL_SUBSET_UINT128_DELTA_AND_PROSPECTIVE_BYTE_FRONTIER_V1`. The boundary
roots are prior-position inner prospective-result certificates for the exact
canonical complete-vector catalog defined below. That catalog contains every
complete feasible recurrence vector and every deterministic complete attaining
vector needed by a prospective-byte breakpoint or interval-exclusion proof; it
does not create roots for domain, decimal, or intrinsic-relation provenance by
itself. Its common children are the position-1 baseline-spec fixed child
followed by those roots in printed order. The closed recurrence records let the
verifier derive the complete objective prefix and feasibility class and bind a
complete feasible state to a prospective-wrapper frontier through its boundary
root; those derived objects are not additional serialized state members. Its
ordinary Section 6.3 output frontier instead has the empty state signature and
one attainable prospective-wrapper length: the winner. The checker validates
every transition and dominance deletion; no opaque subset-DP log or Boolean
minimality assertion is admitted.

`baseline_spec_fixed_child_position` is exactly `1`. That node is the ordinary
`FIXED_VALUE` variant and has no children or observable dimensions. Both its
common subject locator and `fixed_source_locator` are the exact
`V3_INVENTORY_POINTER` locator with pointer
`/fixture_records/operation_specs/LOCAL_SHUTDOWN`, root type
`CapacityMeasurementOperationSpec`, null root value-schema ID, empty path, and
all transient members null. Its common `value_schema_id` is
`4fae771b5c217c12346a142112f49360f7919f9fa6d4d321622471d158ac2edc`,
`type_name` is `CapacityMeasurementOperationSpec`, `alternative_name` is null,
and its effective inclusive ceiling is `2097152`. Its derivation is
`FROZEN_AUTHORITY` plus `EXACT_FIXED_VALUE`, has fixed compact length `1109`,
fixed SHA-256
`292a5c5110b8c98910fae5ad48abb6e384bca17fc0f21c1ab2dde10c4fd026df`,
null mapping-catalog ID, and no identity-payload children. It materializes the
exact singleton length `1109` under the empty signature with null measured and
context winner digests. The verifier resolves and validates the complete
record and requires it to equal `baseline_spec_record_reference`; this fixed
node is provenance/input evidence, not a serialized or trusted mutation-domain
frontier.

`ordered_intrinsic_relation_ids` is not a producer-defined identifier list. It
is exactly the following five V3
`operation_contracts.local_shutdown_intrinsic_limit_relations` strings, in
their frozen array order:

```text
maximum_terminal_ingress_plaintext_octets<=16384*maximum_terminal_ingress_batches
2*maximum_terminal_ingress_parser_units<=maximum_terminal_ingress_plaintext_octets
maximum_terminal_tls_records<=maximum_terminal_ingress_batches
maximum_terminal_ingress_automatic_outputs<=maximum_terminal_ingress_parser_units
maximum_websocket_send_attempts<=256*(1+maximum_terminal_ingress_automatic_outputs)
```

The verifier also requires these five strings to correspond, in that same
order, to comparison-expression positions `25, 26, 27, 28, 29` of registry
rule `RULE/INTRINSIC/CapacityMeasurementLocalShutdownSpecV2/V1`; those nodes
are respectively `LE(4,15)`, `LE(18,4)`, `LE(8,2)`, `LE(10,6)`, and
`LE(12,24)`. The same exact strings, and no synthetic hash aliases, populate
non-null breakpoint `source_relation_id` and transition
`failed_relation_id`. If several relations fail simultaneously, the failed
relation is the first one in this order.

Each `ordered_boundary_candidate_witness_records` item has exactly:

```text
boundary_witness_position
boundary_candidate_root_position
candidate_mutated_spec
prospective_scope_witness_context
prospective_result
ordered_component_choice_evidence
prospective_result_canonical_byte_length
prospective_result_canonical_sha256
boundary_candidate_witness_id
```

Entries are strictly ordered by the strictly increasing boundary root position,
positions are contiguous, and there is exactly one entry for every boundary
root and no other entry. The candidate spec is a complete schema-valid local-
shutdown operation spec with its derived identity recomputed; the scope context
is the complete correction Section 11.3 local fixture context, not a context
hash; and the prospective result is the complete retained attaining wrapper for
that candidate with its derived identities recomputed. Choice evidence follows
Section 6.5 and contains every and only active coordinates for that boundary
winner. The length/hash are recomputed from the complete result and equal the
named codec root's attaining claims. The entry ID domain over every preceding
member plus `maximum_protocol_sha256` is
`RiskYieldMMA2MStep2ExternalSchemaV2LocalShutdownBoundaryCandidateWitnessV1V4_9F_RawV8`.
The checker fully validates the candidate, context, result, rules, applications,
masked-coordinate semantics, and active choice evidence before accepting the
root's upper-bound/attainment result. A length/hash without this resolving
entry rejects. These complete entries count toward certificate, hash-preimage,
row, and per-file ceilings; exceeding a cap is controlled NO-GO, never a reason
to drop boundary attainment.

`prospective_result_attainment_mode` is exactly
`PROSPECTIVE_BYTE_MAXIMUM_WITH_ONE_MASKED_OUTER_CODEC` and the masked coordinate
is exactly the Section 6.1 outer `LT 524288` coordinate.
`baseline_result_inventory_json_pointer` is the exact RFC 6901 pointer
`/fixture_records/operation_results/LOCAL_SHUTDOWN` into the once-read,
independently validated, physically and semantically pinned V3 inventory. It is
a verifier-control locator confined to this non-row local recurrence; it is not
a correction Section 11.3 `MaximumRecordReferenceV1`, does not enlarge that
union's row-authorized V3 pointer surfaces, and cannot appear in a witness or
context-object reference. The verifier resolves the complete record before any
use; validates it as `CapacityMeasurementOperationResultEvidence`; recomputes
its `result_evidence_id` as
`237336c1d3867c7b38d3dcf4d9af455f4dc4675ae2dd1af6ba89b04d010be5db`;
and requires its compact length and `baseline_result_canonical_byte_length` to
equal `2504`, which is strictly below the limit. Because this is a control
pointer rather than a serialized `MaximumRecordReferenceV1`, no maximum-record-
reference ID or record-SHA field event is invented; the independently
recomputed result-identity envelope is still charged to the shared local
certificate meter.
The outer relation/limit are exactly `LT` and `524288`. `winning_objective` has
the correction Section 12 four-member shape and duplicates the enclosing
minimality certificate and retained mutation. The prospective length/hash
duplicate the enclosing retained prospective result and the winning boundary
subcertificate. The node output is the exact singleton prospective-result
length under the empty state key; the complete winning objective remains in
the derivation and enclosing correction certificate. This local
node, not a `CODEC_INTERSECTION_ATTAINMENT` node, is
`minimality_certificate.root_proof_node_position`, equals the proof-node count,
and is the sole root reachable from every preceding baseline/boundary child.

A breakpoint record has exactly:

```text
breakpoint_position
source_state_position
domain_position
member_name
breakpoint_kind
candidate_value
source_relation_id | null
prospective_result_root_position | null
```

Positions are contiguous. The kind is `DOMAIN_MINIMUM`, `DOMAIN_MAXIMUM`,
`BASELINE`, `BASELINE_NEIGHBOR`, `DECIMAL_WIDTH_BOUNDARY`,
`INTRINSIC_RELATION_BOUNDARY`, or `PROSPECTIVE_BYTE_BOUNDARY`. The checker
derives, for each retained prefix state, every in-domain endpoint, baseline and
nearest neighbor, every `10^k-1/10^k` crossing, both integer neighbors of each
five-relation affine root, and both integer neighbors of every inner
prospective-byte frontier change. Relation/root fields are non-null only for
their corresponding kinds. Duplicate candidate values collapse to the first
kind in the printed kind order. The complete array is sorted by
`(source_state_position, domain_position, candidate_value, breakpoint-kind
rank, source_relation_id null-first, prospective_result_root_position
null-first)` and then assigned contiguous positions. For each retained source
state at the next unprocessed domain it contains every and only independently
derived breakpoint; no breakpoint record exists for an infeasible or dominated
source.

Prospective-byte breakpoints and complete-state roots use a noncircular
three-phase derivation.

Phase A performs the entire symbolic prefix expansion without proof-node
positions or complete-state dominance. Every incomplete intrinsically feasible
state is retained. The verifier derives all domain, baseline, decimal,
intrinsic-relation, and prospective-frontier discontinuity candidate values
from the pinned schema, rule, application, and masked-codec transfer. For a
prospective discontinuity at a partial prefix, it considers every legal
complete suffix that realizes that exact discontinuity and selects the typed-
lexicographically least complete eleven-integer vector. If no legal complete
suffix realizes it, the discontinuity emits no breakpoint. Interval-exclusion
analysis uses the same rule: among legal complete vectors that realize its
constant piecewise signature and named attaining endpoint, select the typed-
lexicographically least complete vector. This selection compares mathematical
integers, never decimal strings, JSON bytes, proof positions, IDs, or hashes.

At the end of Phase A the verifier forms one boundary-vector set containing:

1. every distinct complete intrinsically feasible recurrence vector;
2. every complete attaining vector selected for a prospective-byte
   breakpoint; and
3. every complete attaining vector selected for an interval-exclusion record.

Vectors are deduplicated by exact equality of all eleven mathematical integers
and sorted by their typed lexicographic eleven-integer tuple. Phase B
materializes exactly one prospective subplan/root and one boundary witness for
each vector in that order. Boundary root positions and witness positions are
therefore a derived one-to-one catalog over complete vectors.

Phase C attaches the Phase-B root for each complete feasible state and each
prospective-byte or interval record, derives frontier commitments, applies
complete-state dominance, assigns final state/status/transition/deletion
positions and identities, and selects the winner. A complete state reached
only through domain, baseline, decimal, or intrinsic-relation breakpoint kinds
still has its own catalog root because rule 1 included its complete vector.
Only after Phase B has fixed the catalog may a breakpoint or interval record
contain `prospective_result_root_position`. A producer root position can never
influence Phase-A discontinuity discovery, completion selection, vector
inclusion, deduplication, or order.

When the same `(source_state_position, domain_position, candidate_value)` is
derived by more than one provenance, the retained provenance is the minimum of
this complete tuple: breakpoint-kind rank in the printed kind order above;
`source_relation_id` null first and otherwise its index in
`ordered_intrinsic_relation_ids`; then
`prospective_result_root_position` null first and otherwise increasing numeric
position. All other duplicates are absent. Candidate-vector deduplication is
exact equality of all eleven integers, never equality of root IDs, byte lengths,
or hashes. If the retained provenance is `PROSPECTIVE_BYTE_BOUNDARY`, its root
is the Phase-B root of the exact deterministic complete attaining vector
selected in Phase A; no other suffix completion is producer-selectable.

An interval-exclusion record has exactly:

```text
interval_position
source_state_position
domain_position
first_omitted_value
last_omitted_value
dominating_breakpoint_position
prospective_result_root_position
piecewise_signature_id
```

Intervals are the nonempty maximal integer ranges between adjacent derived
breakpoints. The checker symbolically substitutes their prefix state into the
exact schema domains, five checked-affine relations, decimal-width functions,
and prospective-result frontier transfer; it requires all to have one constant
piecewise signature on the interval and proves absolute delta is monotone
toward the named endpoint. The signature ID is over those complete derived
expressions and interval bounds, not a producer label. An interval with a
relation, digit-width, attainable-bitmap, or objective discontinuity rejects.

`piecewise_signature_id` has semantic domain
`RiskYieldMMA2MStep2ExternalSchemaV2LocalShutdownPiecewiseSignatureV1V4_9F_RawV8`
over this exact payload:

```text
source_recurrence_state_id
domain_position
member_name
inclusive_minimum
inclusive_maximum
ordered_schema_domain_affine_region_ids
ordered_intrinsic_affine_region_ids
decimal_digit_count
prospective_result_root_proof_node_id
prospective_result_frontier_commitment_id
absolute_delta_monotonic_direction
dominating_candidate_value
```

The two ordered affine-region arrays use the Section 4.3 affine-region domain
in registry expression order; empty arrays are retained. The prospective root
and commitment are resolved from the non-null interval root position.
`absolute_delta_monotonic_direction` is `TOWARD_LOWER_ENDPOINT` or
`TOWARD_UPPER_ENDPOINT`, and the named endpoint equals the dominating
breakpoint candidate. Thus the ID is a reproducible semantic record, never a
hash of an implementation expression or host tuple. Interval records are
strictly ordered by `(source_state_position, domain_position,
first_omitted_value)`, are disjoint, and together cover every in-domain integer
not present as a breakpoint exactly once.

A recurrence state has exactly:

```text
state_position
processed_mutable_member_count
ordered_processed_values
ordered_changed_domain_positions
sum_absolute_integer_deltas
ordered_intrinsic_relation_states
prospective_result_root_position | null
state_status
recurrence_state_id
```

Processed values follow the eleven lexical member names. Changed positions are
strictly increasing correction-table domain positions. The delta sum is
canonical UInt128 text. The five relation states are `FALSE`, `TRUE`, or
`UNRESOLVED` in frozen relation order. `UNRESOLVED` means at least one mutable
operand is not yet processed; otherwise the verifier evaluates the exact
registry expression with checked UInt128 arithmetic and records `TRUE` or
`FALSE`. A state with any `FALSE` is `INFEASIBLE`, has a null prospective root,
and has no outgoing transitions. At layer eleven, `UNRESOLVED` is forbidden.
Every complete feasible state has a non-null prospective root naming one of the
local node's boundary roots, and that root's boundary witness candidate spec
has exactly the state's eleven values. `state_status` is `RETAINED`,
`INFEASIBLE`, or `DOMINATED`. The state ID domain is
`RiskYieldMMA2MStep2ExternalSchemaV2LocalShutdownRecurrenceStateV1V4_9F_RawV8`
over every preceding member.

For every state the verifier derives, but the producer does not serialize, an
objective-prefix object with exactly:

```text
objective_prefix_version
processed_mutable_member_count
changed_limit_field_count
sum_of_absolute_integer_deltas
changed_member_names_in_lexical_order
resulting_changed_values_in_that_same_order
```

Its version is
`riskyieldmm.raw_v8_step2_external_schema_v2.local_shutdown_objective_prefix.v1`.
The verifier compares each processed value to the corresponding member of the
resolved V3 baseline. The changed count, checked UInt128 sum, lexical changed
names, and corresponding resulting values include every and only differing
processed members. The state's changed domain positions and
`sum_absolute_integer_deltas` must reproduce that object. At layer eleven,
removing the version and processed-count members yields the exact four-member
`winning_objective`. Objective comparison is the typed tuple `(changed count as
integer, delta sum as UInt128, changed-name lexical string sequence, resulting-
value integer sequence)`; decimal strings and compact JSON bytes are never
compared lexically.

The verifier also derives this exact nonserialized recurrence-equivalence key:

```text
equivalence_key_version
processed_mutable_member_count
continuation_equivalence_kind
ordered_exact_processed_values
ordered_intrinsic_relation_states
prospective_result_frontier_commitment_id
```

Its version is
`riskyieldmm.raw_v8_step2_external_schema_v2.local_shutdown_equivalence_key.v1`.
For every incomplete or intrinsically infeasible state,
`continuation_equivalence_kind` is `EXACT_PROCESSED_PREFIX`,
`ordered_exact_processed_values` equals the complete state prefix, and the
commitment ID is null. For a complete feasible state, the kind is
`COMPLETE_PROSPECTIVE_FRONTIER`, processed count is eleven,
`ordered_exact_processed_values` is null, all five relation states are `TRUE`,
and the commitment ID is the resolved boundary root's exact
`frontier_commitment_id`. No partial state may omit its exact prefix: tri-state
relation equality alone is not continuation equivalence.

The state array is complete and canonically ordered by
`(processed_mutable_member_count, compact-canonical ordered_processed_values,
compact-canonical ordered_changed_domain_positions,
sum_absolute_integer_deltas as UInt128, compact-canonical relation states,
prospective_result_root_position null-first, state-status rank RETAINED,
INFEASIBLE, DOMINATED)`, then assigned contiguous positions. It begins with
the unique empty-prefix retained state. It contains every distinct result of
every complete transition; no unreachable state is serialized. At each layer,
byte-equal complete state records before position/status/ID assignment are
merged. Infeasible states are always `INFEASIBLE`; incomplete feasible states
are always `RETAINED`. Only complete feasible states may be grouped by the
derived recurrence-equivalence key. Within each such group the unique least
typed objective is `RETAINED` and every strictly worse objective is
`DOMINATED`. Equal objective prefixes imply the same complete processed vector
and must have merged before serialization. Thus recurrence V1 permits no
partial-state dominance; if this conservative rule exceeds a resource cap, the
result is controlled NO-GO rather than an unproved pruning shortcut.

A transition has exactly:

```text
transition_position
source_state_position
breakpoint_position
result_state_position
transition_kind
failed_relation_id | null
recurrence_transition_id
```

The kind is `EXTEND_RETAINED`, `EXTEND_INFEASIBLE`, or `EXTEND_DOMINATED`; its
result state always exists and has the matching status. Only infeasible has a
failed relation. The transition ID uses domain
`RiskYieldMMA2MStep2ExternalSchemaV2LocalShutdownRecurrenceTransitionV1V4_9F_RawV8`
over preceding members.

Transitions are strictly ordered by `(source_state_position,
breakpoint_position)` and then assigned contiguous positions. There is exactly
one transition for every breakpoint owned by every retained partial source
state, and none for any other pair. Its result has processed count exactly one
larger and appends the breakpoint candidate at the next lexical mutable member.
This coverage rule is independently regenerated; validating only the
producer's serialized transition subset is forbidden.

A dominance deletion has exactly:

```text
deletion_position
deleted_state_position
retained_state_position
equivalence_state_key_sha256
dominance_reason
```

The reason is exactly `BYTE_EQUAL_STATE_KEY_AND_OBJECTIVE_PREFIX_NO_WORSE`.
The checker rebuilds the complete recurrence-equivalence key and objective
prefix, requires the states to be at the same complete layer, requires compact-
canonical byte equality of their complete keys, and requires the retained
state's typed objective to be strictly smaller. It hashes the compact key
itself for `equivalence_state_key_sha256`. Every dominated state has exactly one
deletion to the unique group winner; no retained, infeasible, or partial state
has one. A same-objective duplicate is a state-deduplication error, not a
dominance deletion.
Deletion records are strictly ordered by `deleted_state_position`, and their
positions are contiguous. Every reachable complete feasible state has a
non-null prospective root. The unique retained complete feasible state with
least objective whose prospective maximum is at least the outer limit is the
node winner; every strictly earlier complete feasible state is either below
the limit or has a validated deletion to a no-worse state.

### 7.14 `CODEC_INTERSECTION_ATTAINMENT`

```text
derivation_kind
attainment_mode
codec_byte_bound_relation
codec_octet_limit
owner_codec_byte_bound_relation | null
owner_codec_octet_limit | null
masked_codec_coordinate | null
certified_upper_bound_octets
attaining_witness_canonical_byte_length
attaining_witness_canonical_sha256
attaining_scope_case_position | null
upper_frontier_child_position
winner_frontier_child_position
```

`attainment_mode` is `BYTE_MAXIMUM` or
`PROSPECTIVE_BYTE_MAXIMUM_WITH_ONE_MASKED_OUTER_CODEC`. For an ordinary byte
maximum, the checker
intersects all attainable bitmap blocks with every nested/owner/measured codec and
requires a legal witness at the surviving upper endpoint. The prospective
mode masks exactly the structured outer
`CapacityMeasurementOperationResultEvidence`, empty typed path, `LT 524288`
coordinate and retains every nested codec/rule; it is forbidden elsewhere.
The common `ordered_ancestor_observable_dimensions` are byte-equal to the
winner child, `output_frontier` is the mandatory Section 6.3 direct-child alias
to that winner, and `frontier_commitment` is byte-equal to the winner child. The
winner output must contain exactly one expanded state/length point and be
`EXACT_ATTAINABLE`; the root does not union it with, project it onto, or copy
the broader upper child.

Independently, the checker intersects every upper-child length bitmap with the
measured codec, any distinct owner codec, and every inherited nested codec in
typed-path order, omitting only the authenticated mask in prospective mode.
The greatest surviving length is `certified_upper_bound_octets`. It must equal
the winner's sole length, `attaining_witness_canonical_byte_length`, the
compact-canonical length of the resolved retained witness, and the enclosing
certificate/row duplicated maximum. The witness SHA field must equal the
resolved retained witness's raw compact-canonical SHA-256. The derivation's
measured and owner codec relation/limit fields must byte-equal the independently
derived coordinates, with owner fields both null exactly when there is no
distinct owner codec. Empty intersection, another winner point, a winner below
the upper endpoint, or any copied safe-upper state rejects.

For both modes, `attaining_scope_case_position` selects one previously proved
scope case and matches the retained row context; it is null only when the
independently derived scope has exactly one implicit singleton case. The winner
child is the final prefix-exclusion node, or the exact maximum-slice node when
the complete choice catalog is empty; its frontier contains exactly one
deterministic winner. Local-shutdown objective minimality is certified only by
Section 7.13 and is not a third attainment mode.

## 8. Upper-bound certificate

`upper_bound_certificate` embedded in a maximum row has exactly:

```text
certificate_version
canonicalization_version
measurement_schema_version
maximum_protocol_sha256
source_inventory_sha256 | null
external_schema_registry_id
rule_literal_authority_sha256
maximum_context_object_manifest_id
constraint_scope_id
measured_type_name
alternative_name | null
objective_version
proof_plan_version
frontier_encoding_version
ordered_proof_nodes
root_proof_node_position
measured_choice_root_proof_node_position
context_choice_root_proof_node_position | null
proof_resource_claim
certified_analytic_maximum_octets
winning_measured_choice_vector_sha256
winning_context_choice_vector_sha256
upper_bound_certificate_id
```

`certificate_version` is
`riskyieldmm.raw_v8_step2_external_schema_v2.upper_bound_certificate.v1` and
`objective_version` is
`MAX_BYTES_THEN_MIN_MEASURED_PRIMITIVES_THEN_MIN_CONTEXT_PRIMITIVES_V1`.
`proof_plan_version` is
`TOPDOWN_BUDGET_THEN_DESCRIPTOR_POSTORDER_RULE_APPLICATION_MAX_SLICE_PREFIX_V1` and
`frontier_encoding_version` is
`TAGGED_MATERIALIZED_OR_DIRECT_CHILD_ALIAS_FIXED_256_LENGTH_BITMAP_BLOCKS_V2`.
The legacy `FIXED_256_LENGTH_BITMAP_BLOCKS_V1`, an untagged frontier, and an
optional materialized-versus-alias choice reject.
The semantic identity domain over every preceding member is:

```text
RiskYieldMMA2MStep2ExternalSchemaV2MaximumUpperBoundCertificateV1V4_9F_RawV8
```

The root position equals the node count. The measured-choice root is the last
measured-coordinate prefix node, or the exact maximum-slice node when the
measured catalog is empty. The context-choice root is the last context prefix
node and is null when the context catalog is empty; in that case the root uses
the canonical empty-vector digest. Root maximum, certificate maximum, row
`certified_analytic_maximum_octets`, row `canonical_byte_length`, and the
actual retained measured bytes are equal. The two winning vector digests equal
both the root commitment and the independently resolved measured/context
partitions of the enclosing row's or pilot leaf's
`ordered_component_choice_evidence`. A bare certificate is not accepted
without that enclosing retained evidence.

### 8.1 Local-shutdown minimality certificate binding

The local certificate keeps the exact closed member schema, version, identity
domain, and duplicated equalities frozen in correction Section 12; this
protocol does not add an upper-bound-certificate wrapper around it. Its
`ordered_proof_nodes` use Sections 6–7, its
`root_proof_node_position` is the final
`LOCAL_SHUTDOWN_MINIMALITY_FRONTIER`, and every boundary child root is a prior
`CODEC_INTERSECTION_ATTAINMENT` node in
`PROSPECTIVE_BYTE_MAXIMUM_WITH_ONE_MASKED_OUTER_CODEC` mode. The checker derives
the local proof-scope/context authorities from Section 7's common-node rule,
recomputes the correction's `winning_objective`, and requires exact equality
with the root node, mutated spec, mutation list, and prospective result.

The correction's local certificate intentionally has no embedded
`proof_resource_claim`. During pilot and final validation, the independent
checker nevertheless recomputes the same Section 6.6 counters over its complete
DAG and enforces every per-certificate cap before the corresponding operation.
The pilot's `producer_resource_measurement` must equal those recomputed values;
the final counterexample is accepted only inside the aggregate validator run
that records them in its deterministic validation report. Absence of an
embedded claim is never interpreted as absence of a limit.

## 9. Deterministic transfer semantics

### 9.1 Scalars

Booleans contribute exact `false`/`true` bytes. Safe integers partition at
decimal powers of ten and retain exact integer state when any ancestor reads
the value. Text literals/enums enumerate canonical byte contribution. Built-in
languages use their frozen closed forms. ASCII DFAs use dynamic programming
over `(state, decoded length, canonical length, observable relation class)`.
Unicode identifiers use the pinned Unicode 15.0.0 sources and dynamic
programming over scalar count, UTF-8 count, JSON expansion, NFC state, trim and
forbidden-code-point state. A host runtime Unicode table is never authority.

For `ASCII_DFA_DYNAMIC_PROGRAM_V1`, `recurrence_parameters` has exactly
`text_language_id, effective_canonical_octet_ceiling,
ordered_relation_descriptor_ids`. The language ID resolves one `ASCII_DFA`
language and thereby fixes its DFA ID, start/accepting states, state count,
input-octet limits, and transition rows. Each state has key atoms exactly
`POSITION(input_octet_count), POSITION(dfa_state_position),
SAFE_INTEGER(json_value_octets)`, followed by one
`POSITION(relation_residual_position)` per descriptor; key cells are empty.
Payload atoms contain exactly `POSITION(least_scalar_prefix_position)`, payload
cells are empty, and attainable runs are empty for a nonterminal or the exact
singleton quoted-string length for a legal accepting terminal.

For `UNICODE_15_NFC_DYNAMIC_PROGRAM_V1`, `recurrence_parameters` has the same
three members. Its language ID resolves one `UNICODE_IDENTIFIER` language and
thereby fixes the identifier profile, Unicode version, all six source IDs,
scalar/UTF-8 caps, forbidden ranges, trim set, and NFC form. State key atoms are
exactly `POSITION(input_scalar_count), SAFE_INTEGER(normalized_utf8_octets),
SAFE_INTEGER(json_value_octets), POSITION(leading_trim_class),
POSITION(trailing_trim_class), POSITION(normalization_segment_prefix_position)`,
followed by the ordered relation-residual positions; key cells are empty.
Trim positions are `0=EMPTY`, `1=NON_TRIM`, `2=TRIM`. The segment position
resolves its complete ordered scalars through the Section 4.3 pool. Payload
atoms contain exactly `POSITION(least_source_scalar_prefix_position)`, payload
cells are empty, and runs are empty except for an exact singleton legal NFC
terminal length.

For both kinds, relation-residual records are independently derived complete
predicate residuals after the consumed prefix, deduplicated by byte-equal
frozen semantics, sorted by compact-canonical residual bytes, and numbered
from zero. Terminal truth is derived from the residual; a Boolean “truth so
far” is not a sufficient state. Their scalar prefix pools contain the exact
used prefix closure, and byte-equal state keys merge mandatorily under Section
4.3 while retaining the least reconstructed prefix.

The ASCII-DFA recurrence is exact. Starting with `(input_position=0,
dfa_state=start_state, canonical_value_octets=0, relation_residual_vector)`, visit
input positions increasingly, source states increasingly, and admitted bytes
in numeric order. One transition consumes exactly one ASCII byte, applies the
unique frozen transition row, adds JSON value-byte cost 2 for quote/backslash
and 1 for every other byte admitted by the current DFAs, and updates every
ordered relation predicate. Only lengths within the DFA min/max and accepting
states emit points; the surrounding JSON quotes add two. Missing or overlapping
transition rows reject the authority rather than becoming nondeterminism.

The Unicode recurrence uses only the six pinned Unicode 15.0.0 source tables.
It performs the UAX #15 canonical decomposition, canonical-combining-class
ordering, and canonical composition algorithm incrementally. Normalized output
is partitioned into a `committed_normalized_prefix`, whose bytes cannot be
changed by future source scalars, and one exact `open_normalization_segment`
retained through `normalization_segment_prefix_position`.
`normalized_utf8_octets` and `json_value_octets` count only the committed
prefix. They exclude the open segment, and the latter also excludes JSON's two
surrounding quotation marks. The open segment is the exact canonically
decomposed, canonically ordered, provisionally NFC-composed suffix since the
last normalization-stable flush boundary.

For every consumed source scalar the verifier applies its complete recursive
canonical decomposition, including algorithmic Hangul decomposition; inserts
the result into canonical combining-class order; applies Unicode 15.0.0
composition and blocking inside the open segment; and, when the pinned NFC
`Quick_Check=Yes` authority makes an earlier portion stable, commits every
scalar before the last such boundary while retaining that boundary scalar and
the following suffix. This is the buffering rule of Unicode 15.0.0 UAX #15
revision 53 Section 13.1
(`https://www.unicode.org/reports/tr15/tr15-53.html`): content before the last
`Quick_Check=Yes` character may be ordered/composed and flushed, while the
suffix beginning at that character remains buffered. A newly encountered
starter alone is not a flush authorization.

Relation residuals consume only stabilized NFC output. Let the incremental
normalizer state be `(C, O)`, where `C` is the committed normalized prefix and
`O` is the open provisional segment, and let `rho` be the ordered relation-
residual vector after consuming `C`. A source scalar transition may produce a
newly stable normalized flush `F` and a new open segment `O'`; it updates
`rho' = ADVANCE(rho, F)`. Empty `F` leaves `rho` byte-equal. The raw source
scalar and `O'` are never supplied to `ADVANCE`. At end of input, the checker
finalizes `O` to `Z`, applies `ADVANCE(rho, Z)` exactly once, and derives
terminal truth from that final residual. Feeding a raw scalar, feeding an open
segment, or feeding `F`/`Z` twice rejects. Scalar-class equality therefore
includes byte-equal `F`, `O'`, updated residual, count, and trim effects.
Residual stepping is part of the already charged Unicode-class transition;
end-of-input finalization and terminal evaluation are one terminal-candidate
event and never consult host Unicode or hash tables.

At end of input the checker fully orders and composes the open segment, then
derives:

```text
final_normalized_utf8_octets =
  normalized_utf8_octets + utf8_octets(finalized_open_segment)
final_json_value_octets =
  json_value_octets + json_value_octets(finalized_open_segment)
final_canonical_string_octets = final_json_value_octets + 2
```

Only those final values enter terminal caps and emission. The complete open
segment is retained; the protocol neither inserts CGJ nor applies Stream-Safe
Text transformation because either would change the candidate value. The
implementation must reproduce every pinned Unicode 15.0.0
`NormalizationTest.txt` NFC result and must not consult host Unicode tables.
Its state remains `(input_scalar_count, normalized_utf8_octets,
json_value_octets, leading_trim_class, trailing_trim_class,
open_normalization_segment, relation_residual_vector)`. Candidate scalar
values are visited in numeric code-point order, exclude surrogates and the
profile's forbidden ranges, and are partitioned only when their complete tuple
of decomposition, combining class, composition mappings, UTF-8 width, JSON
escape width, trim membership, and relation-predicate effects is byte-equal.
The least scalar represents each partition and multiplicity never controls
attainability. At emission the complete normalized string must be byte-equal
to its pinned NFC result, within scalar/UTF-8 caps, and have no trim member at
either edge. Full open segments are retained through the exact scalar-prefix
pool and charged once; a host `unicodedata` result is never proof.

The five built-ins are closed as follows: `LOWERCASE_SHA256` is exactly 64
lowercase hexadecimal characters; `UINT128_DECIMAL` is the canonical decimal
language from zero through its descriptor maximum; `CANONICAL_BASE64`
enumerates decoded length and exact RFC 4648 four-character blocks/padding and
re-decodes before emission; `RFC3339_UTC` enumerates exactly the correction's
20-octet `YYYY-MM-DDTHH:MM:SSZ` and 27-octet nonzero-six-fraction
`YYYY-MM-DDTHH:MM:SS.ffffffZ` forms over year 0001..9999 and the proleptic
Gregorian calendar, with hour 00..23 and minute/second 00..59;
and `RAW_CANONICAL_JSON_STRING` admits every Unicode scalar sequence whose
exact compact JSON string bytes fit the inherited ceiling. The raw-string DP
visits scalar values in code-point order and adds 2 bytes for quote/backslash,
2 for the five short control escapes, 6 for other U+0000..U+001F controls, 1
for other ASCII, and exact UTF-8 width otherwise, plus two surrounding quotes.
It retains exact prior item bytes whenever an ancestor requires ordering or
uniqueness. These recurrences enumerate attainable byte points and least
typed witnesses, never a min/max interval.

`RAW_CANONICAL_JSON_STRING` is optimized under its own exact raw-string
language and JSON escaping; identifier trim/NFC restrictions are not applied.
Base64 languages optimize decoded and encoded lengths jointly and verify
padding/canonical decoding. RFC3339 languages enumerate the frozen canonical
forms rather than accepting parser-equivalent alternatives.

### 9.2 Arrays

The frontier is computed at every legal cardinality. Independent arrays use
exact min-plus/max-plus convolution with lexicographic witness retention.
Ordered/unique arrays retain the last item relation class and used finite
catalog state. Positional and zip-coupled arrays retain the ordinal. A
cardinality read by any rule remains an observable dimension. Any array domain
whose verifier-derived exact ordering-state upper bound exceeds a strategy
bootstrap limit takes the Section 7.6 ordered-language safe upper transfer
before that exact state is materialized. The exact maximum-slice and every
active prefix step then use the closed prefix-feasibility/unranking recurrence
to reinstate strict order and uniqueness. If that recurrence exceeds an
accepted resource cap, cannot reproduce the retained sequence, or fails to
reach the relaxed upper length, the scope is protocol NO-GO. No generic
ordered/unique relaxation is permitted for a non-text item language.

### 9.2.1 `ORDERED_RAW_STRING_PREFIX_FEASIBILITY_V1`

This recurrence is permitted only for a strictly ascending/unique array over
`RAW_CANONICAL_JSON_STRING`. The reverse dependency walk must prove that no
remaining rule/application observes an individual item except through its
canonical string length, array cardinality, strict ordering, uniqueness, and
the primitive tie-break. Equality to an external value, identity input,
normalization, or any other item-value observer makes this specialized transfer
NO-GO; it cannot be silently dropped or approximated.

Its `recurrence_parameters` has exactly:

```text
invocation_kind
safe_array_node_position
target_array_octets
cardinality_query_kind
minimum_array_cardinality
maximum_array_cardinality
array_cardinality | null
fixed_item_count
ordered_fixed_item_scalar_prefix_positions
per_string_canonical_octet_ceiling
```

`invocation_kind` is `MAXIMUM_SLICE_FEASIBILITY` or
`PREFIX_FEASIBILITY_OR_UNRANK`. `cardinality_query_kind` is
`ALL_LEGAL_CARDINALITIES` or `FIXED_CARDINALITY`. The former is legal exactly
while this array's cardinality coordinate is not in the already-fixed prefix,
including the maximum slice and the cardinality-coordinate selection node;
it requires null `array_cardinality`, zero fixed items, and
derives one result for every cardinality
`minimum_array_cardinality..maximum_array_cardinality` from a
single count frontier. The latter is legal only after that array's cardinality
coordinate is active in an earlier prefix node, requires a non-null cardinality
in that same closed range, and requires
`fixed_item_count <= array_cardinality`. Every other integer
is nonnegative and non-null; the safe node is prior, `fixed_item_count` equals
the prefix-position array length, positions reconstruct exact earlier fixed
items, and all fields are independently derived from the invoking node/prefix
and schema ceiling. The array-cardinality coordinate is canonically before its
item coordinates, so a prefix invocation cannot have fixed items while its
cardinality is unknown. The two bounds byte-equal the safe array node, satisfy
`0 <= minimum_array_cardinality <= maximum_array_cardinality`, and this
specialized recurrence requires `maximum_array_cardinality <= 512`; a larger
domain is not truncated and is
protocol NO-GO for this safe transfer.

Let `C` be the inherited inclusive per-string canonical ceiling and let the
alphabet be Unicode scalar values `0..D7FF` and `E000..10FFFF`. Its exact JSON
value-byte cost is:

```text
2  for quote, backslash, and U+0008/U+0009/U+000A/U+000C/U+000D
6  for every other U+0000..U+001F scalar
1  for every other ASCII scalar
2  for U+0080..U+07FF
3  for U+0800..U+FFFF excluding surrogates
4  for U+10000..U+10FFFF
```

The five aggregate scalar counts by cost are exactly:

```text
cost 1:        94
cost 2:     1,927
cost 3:    61,440
cost 4: 1,048,576
cost 6:        27
```

They sum to the 1,112,064 Unicode scalar values. Aggregate counts are legal
only for suffix counting. Lexicographic selection instead derives maximal
nonempty contiguous scalar intervals with one cost, never crossing the
surrogate gap. Each ordered class is exactly
`class_position, inclusive_first_scalar, inclusive_last_scalar, scalar_count,
json_value_octet_cost`; it is ordered by first scalar, positions are contiguous
one-based, and count is `last - first + 1`. A lower-bound/unranking split may
divide a class into contiguous subranges but cannot change its cost.
The resulting fourteen fixed runs are `0000..0007/6`, `0008..000A/2`,
`000B/6`, `000C..000D/2`, `000E..001F/6`, `0020..0021/1`, `0022/2`,
`0023..005B/1`, `005C/2`, `005D..007F/1`, `0080..07FF/2`,
`0800..D7FF/3`, `E000..FFFF/3`, and `10000..10FFFF/4`, where the suffix is
JSON value-byte cost. Any missing, split-without-an-unranking-boundary, merged-
across-cost/gap, or reordered run rejects.
The invocation checks the cardinality terminal before constructing this
bounded language. For a fixed query, `K = array_cardinality - fixed_item_count`;
`K == 0` returns true exactly when the checked residual string-octet budget is
zero, and false otherwise. For an all-cardinalities query, the recurrence uses
`K = maximum_array_cardinality` and retains every item-count row `0..K` for the
polynomial even though query results consider only schema-legal cardinalities. Only when
`K > 0` does `C < 2` terminate all positive-cardinality rows false before
allocating a suffix catalog; cardinality zero is checked separately.

Let `V = C - 2`. Two different caps are normative:

```text
SUFFIX_SAT_K(x) = min(x, K + 1)
SELECTION_CAP_K(x) = min(x, K)
```

`SUFFIX_SAT_K` is used by the suffix recurrence and by intermediate
block/suffix contribution aggregation. Its additional level distinguishes
“at least `K+1`” from exactly `K`, which remains necessary when a singleton
support point is structurally excluded during strict-order unranking. Only
after all disjoint interval-block contributions for one canonical string
length are merged does `SELECTION_CAP_K` produce the interval multiplicity
used by factors. Zero multiplicities are omitted. Serialized
`SUFFIX_COUNT_RUN.saturated_count` is in `1..K+1`, while serialized
`INTERVAL_MULTIPLICITY_RUN.capped_multiplicity` and factor exponents are in
`1..K`. `K=0` is resolved by the preceding terminal rule before suffix,
interval, or factor construction, and no positive-multiplicity state is then
materialized. Arithmetic never subtracts from either saturated
representation; removing empty support is a Boolean-support construction
before the applicable factor is folded.

The conceptual exact saturated suffix recurrence over JSON value bytes is:

```text
A[0] = 1
A[t] = SUFFIX_SAT_K(sum(
  aggregate_scalar_count[q] * A[t-q]
  for q in [1,2,3,4,6] where q <= t
))
```

The checker proves and uses the closed form, not one state per `t`. For every
`0 <= K <= 512`, `A[0]=1`; when `V>=1`,
`A[1]=min(94,K+1)`; and for every defined `2<=t<=V`, `A[t]=K+1` because the
1,927 cost-two scalars already saturate `A[2]` and cost-one extensions preserve
saturation. The catalog contains the unique maximal constant
`SUFFIX_COUNT_RUN` partition of `0..V`: at most three records and at most two
when `K<=93`. Values outside `0..V` are undefined. A prefix subtree rooted at
scalar string `P` shifts these runs by `2+value_cost(P)`; a contiguous range of
`m` equal-cost next scalars multiplies each run by `m` with checked saturation.
No individual `t` or scalar becomes a state or transition.

Lex order is Unicode-scalar order with a proper prefix before every extension.
The language strictly greater than concrete string `L` is the disjoint ordered
union of all strict extensions of `L`, followed for `i = len(L)-1 .. 0` by the
subtrees rooted at `L[0:i] + [s]` for `s > L[i]`, with scalar ranges increasing
inside each block. A no-lower-bound sentinel denotes the whole language,
including the empty string. Lex intervals are the Section 4.3 catalog records
whose ordinary blocks shift/multiply the suffix runs directly and whose
`HOMOGENEOUS_ANCESTOR_DIVERGENCE_RUN` represents every divergence position in
one lower-bound RLE run. Every prefix is reconstructed through the parent/run
scalar pool; complete growing text, one block per repeated scalar, and complete
block arrays in state keys are forbidden. Blocks have contiguous positions,
are nonempty/disjoint/in lex order, and ordinary range blocks never cross a
cost class or surrogate gap. The complete compact block-run array, not an
implementation iterator, is the interval descriptor.

Bounded empty pieces are omitted canonically. The strict-extension block exists
iff `value_cost(L)+1 <= V`. For a source run `(ell,h)` with prefix cost `B`, an
ancestor block exists iff `ell < U+10FFFF` and `V-B >= mu(ell)`, using the
piecewise least-greater-scalar cost below; its exact retained-repeat interval is
`0..min(h-1,floor((V-B-mu(ell))/json_cost(ell)))`. Thus every printed block is
nonempty while their union still contains every and only bounded strings
strictly greater than `L`.

For an ordinary block, counts are direct: `PREFIX_SINGLETON` contributes its
one terminal; `PREFIX_SUBTREE` uses suffix `t>=0`;
`STRICT_EXTENSION_SUBTREE` uses `t>=1`; and a next-scalar range of multiplicity
`m`/cost `q` contributes `SUFFIX_SAT_K(m*A[t])` at the shifted length. For a homogeneous
ancestor block, let `B` be the value cost before the source run, `ell` its
scalar/cost `e`, and `k` range over the printed retained-repeat interval. For
every ordered next-scalar cost-class intersection `(q,m)` and suffix-count run
`[u,v] -> z`, it contributes the arithmetic family of closed canonical-length
intervals

```text
[2+B+k*e+q+u, 2+B+k*e+q+v] -> SUFFIX_SAT_K(m*z)
```

for every printed `k`. The checker aggregates this family without expanding
`k`. For each length `y`, the number of contributing repeats is computed in
checked integers as

```text
k_lo = max(k_min, ceil_div(y-(2+B+q)-v, e))
k_hi = min(k_max, floor_div(y-(2+B+q)-u, e))
h(y) = max(0, k_hi-k_lo+1)
contribution(y) = min(K, h(y)*min(m*z,K))
```

where floor/ceiling division have their mathematical signed meanings before
clipping. On each of the at most `e` residue classes, `h(y)` is an exact
rise/plateau/fall trapezoid. The checker emits its maximal constant clipped
runs by jumping between the two affine breakpoints and the at most
`ceil(K/min(m*z,K))` unsaturated levels on each edge. Thus work is bounded by
`e`, `K`, and emitted runs, never by the source repeat count or `C`. It maps the
residue runs back to lengths and merges them in increasing length. All block
contributions are then merged by sorting each maximal piece's start and checked
one-past-end event. On every resulting segment the checker re-adds all active
piece weights from zero in `(block_position, source_piece_position)` order with
`SUFFIX_SAT_K`; it never removes a contribution from an already saturated total.
The result is the unique maximal positive
`INTERVAL_MULTIPLICITY_RUN` partition with value
`m_I[d]=SELECTION_CAP_K(N_I[d])`. Saturated whole-language ranks are never subtracted;
zero-multiplicity lengths are omitted.

The octet truncation is verifier-derived. For an all-cardinalities query,
`Tmax = min(K*C, max(0,target_array_octets-2))`; for a fixed query it is the
nonnegative checked residual string-octet budget below, or zero after a
negative-residual terminal. No producer-supplied tighter bound is admitted.

For interval `I`, a strictly increasing `r`-item sequence is exactly an
`r`-element subset of this finite lex language written in sorted order. The
conceptual Boolean polynomial remains:

```text
G_I(x,y) = product over d=2..C of
  (1 + x*y^d) ^ min(N_I[d], K)
```

It is not evaluated one length or exponent bit at a time. For each maximal
multiplicity run `[a,b] -> m`, choosing `j` of the `m` available strings at each
consecutive length is possible for `0<=j<=m*(b-a+1)`. Write `j=m*q+r`,
`0<=r<m`. The exact attainable total-octet support is every integer in:

```text
lo = j*a + m*q*(q-1)/2 + r*q
hi = j*b - (m*q*(q-1)/2 + r*q)
```

and is empty outside that cardinality range. The checker proves the endpoints
by filling the shortest/longest length buckets to multiplicity `m`; unit
exchanges between consecutive nonfull buckets prove there is no internal gap.
After truncation to item count `K` and the independently derived maximum
relevant total `Tmax`, each `j` interval has the unique Section 4.1 encoding of
at most a first partial, one merged full, and a last partial bitmap run. This is
one `FACTOR_RUN` state per multiplicity run. `FACTOR_FOLD_RUN` states then fold
those factors in increasing `a` by exact Boolean convolution, visiting set-bit
pairs in `(left_item_count, left_octets, right_item_count, right_octets)` order
and truncating after each checked sum. Count frontiers contain one exact bitmap-
run array for every item count `0..K`. Coefficients are Boolean support, not
counts. No `FACTOR_POWER`, per-length factor, or producer-selected convolution
order is legal. Exact support may still require `Theta(K*Tmax)` bits/work; every
accepted cap is checked before allocation and cap excess is controlled NO-GO.

For an all-cardinalities query, let `H` be the final whole-language count
frontier. Cardinality `n` is feasible exactly when
`minimum_array_cardinality<=n<=maximum_array_cardinality`, checked

```text
b_n = target_array_octets - (2 + (0 if n == 0 else n-1))
```

is nonnegative, and bit `b_n` is set in `H[n]`. The exact feasible-cardinality
set is retained as one canonical bitmap-run array and cardinalities are tested
in increasing typed order. This one lookup pass is the meaning of
`ALL_LEGAL_CARDINALITIES`; separate per-cardinality catalogs are forbidden.

For fixed cardinality `n` and already fixed array items `x[0:p]`, first require
`0 <= p <= n`, raw-language membership, and strict scalar-lex order. Then:

```text
remaining_items = n - p
array_punctuation_octets = 2 + (0 if n == 0 else n - 1)
remaining_string_octets = target_array_octets
  - array_punctuation_octets
  - sum(canonical_string_length(x[i]) for i < p)
```

Subtraction is checked first. A negative residual is terminal false, not
unsigned wraparound. The lower bound is the sentinel for `p=0`, otherwise
`x[p-1]`. Feasibility is exactly terminal `(remaining_items,
remaining_string_octets) = (0,0)` or the corresponding coefficient of
`G_{strings strictly greater than lower bound}`. Zero items with nonzero bytes,
a negative residual, or an empty coefficient is false.

When `remaining_items == 1`, feasibility and the least exact string use the
mandatory direct RLE construction rather than a scalar trie. Let `v` be the
required JSON value-byte cost, so required canonical string octets are `v+2`.
Define `LEAST(v)` by `q,r = divmod(v,6)` as `q` copies of U+0000 followed by:

```text
r=0: []
r=1: [U+0020]
r=2: [U+0008]
r=3: [U+0008,U+0020]
r=4: [U+0008,U+0008]
r=5: [U+0008,U+0008,U+0020]
```

With no lower bound, this is the unique scalar-lex least exact-cost string. For
concrete RLE lower bound `L`, a strict extension exists first in lex order iff
`v > value_cost(L)` and is `L || LEAST(v-value_cost(L))`. Otherwise scan source
runs right-to-left. For a run with scalar `ell`, repeat count `h`, and prefix
value cost `B` before that run, define the least possible cost of a scalar
strictly above `ell`:

```text
mu(ell) = 1  when ell < U+007F
          2  when U+007F <= ell < U+07FF
          3  when U+07FF <= ell < U+FFFF
          4  when U+FFFF <= ell < U+10FFFF
          infinity at U+10FFFF
```

The intervals apply only to valid scalar `ell`; crossing the surrogate gap uses
the next valid scalar. If `v-B < mu(ell)`, that run is infeasible. Otherwise the
rightmost feasible divergence retains

```text
k = min(h-1, floor((v-B-mu(ell)) / json_cost(ell)))
R = v-B-k*json_cost(ell)
```

copies. Choose the least valid scalar `s>ell` with `json_cost(s)<=R` by scanning
the fixed ordered contiguous cost classes, then append `LEAST(R-json_cost(s))`.
The first feasible source run is the answer. Strict extensions precede every
divergence; divergence positions are ordered right-to-left; and within one
position the least feasible `s` and least suffix are first, proving global
leastness. `LEAST(0)` is legal after a strict divergence but never counts as a
strict extension. Every concatenation coalesces equal adjacent RLE runs. The
construction visits at most one record per lower-bound RLE run plus the fixed
scalar-cost-class catalog, never one record per scalar.

For `remaining_items >= 2`, least-completion unranking partitions the current
candidate interval in lex order into the exact prefix string first and then
maximal child scalar-cost-class ranges.
For ordered interval `J`, let `J+` contain all strings greater than every string
in `J`. `J` can contain the first selected string exactly when the requested
coefficient of

```text
(G_J with support point [x^0 y^0] deleted) * G_J+
```

is true. Test intervals in lex order. Split any feasible multi-scalar range by
scalar ordinal into the lower `floor(count/2)` and remaining upper range, lower
first, until one scalar remains; then descend that prefix trie, testing its
terminal prefix before children. Prefix strings and strictly-greater intervals
use RLE/ancestor-run records, so repeated scalars are never copied into keys or
block arrays. Once only one item remains, the mandatory direct construction
above terminates even a multi-megabyte homogeneous suffix in bounded RLE work.
Every earlier trie decision is one printed coefficient test and remains subject
to the accepted transition/depth caps; cap excess is controlled NO-GO, never an
approximation. After selecting a string, subtract its length, decrement
remaining items, set it as strict lower bound, and repeat.
Success requires terminal `(0,0)`, then complete item-by-item language, order,
uniqueness, target-byte, and enclosing-constraint revalidation.
“Deleted” above is a Boolean-support operation; arithmetic subtraction of
polynomials or saturated counts is forbidden.

Every invocation materializes a Section 4.3
`MaximumTransientRecurrenceCatalogV1` with this recurrence kind. Every raw state
has empty key cells, payload cells, and ordinary attainable-length runs. After
the leading exact `TEXT(state_kind)` atom, the only state layouts are:

| State kind | Remaining ordered key atoms | Ordered payload atoms |
|---|---|---|
| `SUFFIX_COUNT_RUN` | `SAFE_INTEGER(first_value_octets), SAFE_INTEGER(last_value_octets)` | `SAFE_INTEGER(saturated_count)` |
| `INTERVAL_MULTIPLICITY_RUN` | `POSITION(interval_position), SAFE_INTEGER(first_string_octets), SAFE_INTEGER(last_string_octets)` | `SAFE_INTEGER(capped_multiplicity)` |
| `FACTOR_RUN` | `POSITION(interval_position), POSITION(multiplicity_run_ordinal)` | `CANONICAL_BYTES(count_frontier)` |
| `FACTOR_FOLD_RUN` | `POSITION(interval_position), POSITION(processed_multiplicity_run_count)` | `CANONICAL_BYTES(count_frontier)` |
| `K1_DIRECT_FEASIBILITY` | `SAFE_INTEGER or NULL(required_value_octets), POSITION or NULL(lower_bound_prefix_position)` | `BOOLEAN(decision), POSITION or NULL(least_string_prefix_position)` |
| `BULK_UNRANK_TEST` | `SAFE_INTEGER(remaining_items), SAFE_INTEGER or NULL(remaining_total_octets), POSITION or NULL(candidate_interval), POSITION or NULL(strictly_greater_interval)` | `BOOLEAN(decision), CANONICAL_BYTES or NULL(least_completion_prefix_position_array)` |
| `QUERY_RESULT` | `TEXT(cardinality_query_kind)` | `BOOLEAN(decision), CANONICAL_BYTES or NULL(feasible_cardinality_bitmap_runs), CANONICAL_BYTES or NULL(least_completion_prefix_position_array)` |

The generic `ordered_attainable_length_bitmap_runs` member is empty for
`SUFFIX_COUNT_RUN`, `INTERVAL_MULTIPLICITY_RUN`, `FACTOR_RUN`,
`FACTOR_FOLD_RUN`, `K1_DIRECT_FEASIBILITY`, and `BULK_UNRANK_TEST`; their
support or decision is already encoded by the independently derived payload.
A false `QUERY_RESULT` also has an empty generic run array. A true
`QUERY_RESULT` has exactly the canonical singleton bitmap for
`target_array_octets`. Thus only a successful final query emits an attainable
complete-array length. Internal value-octet, string-octet, and count-frontier
supports never masquerade as complete-array lengths. The recurrence singleton
is part of transient-catalog bytes and one recurrence bitmap event; it does not
increment a proof-node output's `frontier_bitmap_run_count`. The consuming
maximum-slice or active-prefix transfer separately materializes and charges
its output frontier.

Every ordered-string `CANONICAL_BYTES` payload follows the generic strict
decode/canonical-round-trip rule in Section 4.3 and exactly one of these slot
schemas. A `count_frontier` is:

```text
[
  {
    "item_count": 0,
    "ordered_total_octet_bitmap_runs": <Section 4.1 runs>
  },
  ...,
  {
    "item_count": K,
    "ordered_total_octet_bitmap_runs": <Section 4.1 runs>
  }
]
```

It contains exactly `K+1` records with contiguous item counts `0..K`; empty
run arrays are legal; no set bit exceeds verifier-derived `Tmax`; item-count
zero support is exactly `{0}` before factor folding; and factor/fold payloads
byte-equal the independently recomputed frontier.

A `least_completion_prefix_position_array` is exactly
`[p_0,...,p_(remaining_items-1)]`. Every item is a valid nonnegative scalar-
prefix-pool position. Reconstructed strings are strictly scalar-lex
increasing, strictly greater than the fixed lower bound, and together with
earlier fixed parameter positions form the exact full array. The vector is the
independently unranked least completing suffix. A true fixed query with zero
remaining items contains canonical bytes `[]`; false uses typed `NULL`, never
empty raw bytes.

A `feasible_cardinality_bitmap_runs` payload is a Section 4.1 bitmap-run array
over integer cardinalities. Bit `n` denotes cardinality `n`; no bit is outside
the safe node's interval. It may be empty and is non-null for both true and
false `ALL_LEGAL_CARDINALITIES` queries; the decision is true exactly when at
least one set bit exists. None of these three ordered-string slots admits the
zero-length raw byte string; canonical empty arrays are the two bytes `[]`.

Run endpoints are maximal, multiplicities are `1..K`, and multiplicity-run
ordinals are contiguous one-based in increasing first length. A count frontier is the
compact canonical array of exact `item_count,
ordered_total_octet_bitmap_runs` records for every item count `0..K`, including
canonical empty arrays. Negative residuals use the printed typed `NULL` atoms
and false/null payload. `QUERY_RESULT/ALL_LEGAL_CARDINALITIES` has a non-null
cardinality bitmap, null completion, and `decision` true exactly when that
bitmap contains at least one schema-legal cardinality;
`QUERY_RESULT/FIXED_CARDINALITY` has a
null cardinality bitmap and a completion exactly when true. A K1 true result
has its least prefix position; false has null. A bulk-unrank true result has the
complete ordered prefix-position array; false has null. Duplicate, nonmaximal,
per-length/per-scalar, legacy `SUFFIX_COUNT`, `INTERVAL_COUNT`, `FACTOR_POWER`,
`FACTOR_FOLD`, or `UNRANK_TEST` records reject.

Accounting charges one catalog entry/full compact bytes per emitted run/factor/
fold/direct/unrank/query state; five aggregate suffix-cost validations and one
transition per emitted suffix run; one transition per ordinary
block/suffix-run/cost-class tuple; one per homogeneous-ancestor residue and
each emitted unsaturated level, range-event segment, active-piece test/add, and
merged multiplicity run; one per
`(multiplicity_run,j)` support-interval construction; every in-range set-bit
pair examined by Boolean convolution; every cardinality lookup, interval
coefficient test, scalar-range split, lower-bound RLE run scan, and ordered
scalar-cost-class test; and every complete catalog-ID preimage. Every bitmap
block visited/emitted and every compact-canonical payload byte is charged under
the corresponding Section 6.6 counter. Counters advance before event/list/
bitmap allocation. The required 3 MiB pilot therefore has no per-octet suffix
table, no per-length factor chain, and no 524,282-step NUL descent: its maximum
slice uses one all-cardinalities whole-language catalog, its selected
cardinality-one prefix uses the direct RLE construction, and later inactive
item coordinates use Section 6.3 aliases. This removes the previously
guaranteed resource explosion but is not acceptance evidence; the full pilot
must still measure below every frozen cap and the 16 MiB file ceiling. Exact
general-`K` support can require `Theta(K*Tmax)` bits/work. Any catalog, bitmap,
transition, octet, depth, or file cap excess is controlled NO-GO.

### 9.3 Records and identities

Record punctuation and member-name bytes are constants. Member value frontiers
compose in `member_position` choice order. A standalone identity is removed
from the primitive domain, recomputed from the complete selected payload, and
then added as a fixed canonical string contribution. The complete record is
validated through schema, scalar, intrinsic, identity, canonical round-trip,
and codec checks before it can be an attaining witness.

### 9.3.1 `DERIVED_IDENTITY_PREFIX_FEASIBILITY_V1`

This recurrence is legal only for a
`DERIVED_IDENTITY_FIXED_WIDTH_SAFE_UPPER_DOMAIN` node named by the invoking
maximum-slice or active-prefix node. Its `recurrence_parameters` has exactly:

```text
invocation_kind
safe_identity_node_position
semantic_identity_domain
target_enclosing_canonical_octets
input_prefix_frontier_child_position
fixed_active_prefix_coordinate_count
fixed_primitive_prefix_position
ordered_identity_payload_child_positions
ordered_payload_observable_descriptor_ids
ordered_identity_relation_descriptor_ids
```

`invocation_kind` is `MAXIMUM_SLICE_FEASIBILITY` or
`PREFIX_FEASIBILITY_OR_UNRANK`. Positions name the exact earlier safe node,
source child, payload children, and Section 4.3 primitive-prefix record.
Counts, descriptor IDs, relation IDs, semantic domain, target, and arrays are
independently derived from that node, the fixed active plan prefix, and the
registry; arrays are empty only where the derived identity authority permits
the corresponding empty set.

Every state key has atoms exactly `TEXT("PAYLOAD_PREFIX"),
POSITION(next_payload_coordinate_plan_position),
POSITION(current_primitive_prefix_position)`. Its key cells contain exactly
one complete projected source-frontier cell per
`ordered_payload_observable_descriptor_ids`, in that order. Payload atoms are
`POSITION(least_completing_primitive_prefix_position)` or `NULL`, then
`TEXT(derived_identity_text)` or `NULL`, followed by one `BOOLEAN` or `NULL`
per ordered identity relation. Payload cells are empty. Runs are the complete
attainable enclosing-length set from that prefix. A nonterminal has null
identity/relation atoms; a concrete terminal has all of them non-null. A state
without completion has null least-completion position and empty runs.

`POSITION(0)` is the only terminal sentinel for
`next_payload_coordinate_plan_position`; actual plan positions are one-based.
The recurrence emits one merged state record for every verifier-reachable
complete key, including live and dead nonterminals and accepted and rejected
concrete terminals. A rejected terminal is not discarded merely because its
run set is empty. At a concrete terminal the exact identity and every ordered
relation Boolean are always non-null. If accepted, its least completion is the
current primitive-prefix position and its canonical run set is the singleton
`{target_enclosing_canonical_octets}`. If rejected, its least completion is
null and its run set is empty, while identity and relation results remain
non-null. A nonterminal has null identity and relation atoms; its least
completion is the typed-lex least accepted terminal descendant or null, and
its run set is the union of accepted descendant runs. Because the invocation
fixes one target `T`, every nonterminal run set is exactly `{T}` or empty. A
non-target descendant length is never propagated.

Starting from the fixed primitive prefix, the checker visits remaining payload
coordinates in canonical plan order. For every reachable source state it scans
exact atoms in typed order, evaluates guards, appends only active atoms to the
primitive-prefix pool, preserves every listed observable cell, and propagates
exact enclosing lengths. At a complete payload it constructs the complete
payload object, compact-canonicalizes the exact semantic-ID preimage, hashes it
under the pinned domain, derives every identity relation, and re-evaluates all
enclosing constraints. The preimage is the complete fixed four-member
`canonicalization_version`, `domain`, `payload`, and `schema_version` envelope.
Hashing and `hash_preimage_octets` charging occur on every concrete terminal
candidate in printed recurrence order, before key merging or rejection,
including every candidate later merged or rejected. Recomputing an accepted
retained object is a separate repeated occurrence under the closed event
catalog;
partial digest equality, assumed collision resistance, and opaque hash state
never authorize merging.

If no payload coordinate remains after the fixed prefix, the initial state is
terminal with `POSITION(0)` and is evaluated exactly once. A false-guard
payload coordinate advances without appending to the primitive-prefix pool.
Concrete terminals are hashed and evaluated in printed coordinate/source-
state/typed-atom traversal order before key merging or rejection; equal
derived identity text cannot merge unequal complete keys. Every reached
terminal, including a rejected or subsequently merged one, charges one
terminal-candidate transition and its complete semantic-ID preimage. All
emitted empty-run and nonempty-run records count toward transient state-catalog
resources. Their recurrence runs do not increment the proof frontier's bitmap-
run counters.

Byte-equal complete keys merge mandatorily under Section 4.3 and retain the
least completing primitive prefix. Unequal keys never merge. The
maximum-slice invocation returns exact target-length runs under the empty
prefix; an active-prefix invocation returns the least completing atom and
exact surviving subset. All recurrence state remains transient and no mapping
catalog dimension is re-added. Cap excess is controlled NO-GO.

### 9.4 Constraints and safe relaxations

Finite-state filters execute the exact frozen expression semantics over every
retained state. Bounded-linear frontiers partition only at domain ends,
decimal-length changes, inequality boundaries, arithmetic overflow boundaries,
and objective changes; the checker proves that each omitted interior interval
has constant feasibility and byte contribution. Derived identity fixed nodes
recompute their exact semantic preimages. Exact rule evaluation uses the
accepted independent rule/application semantics.

Safe relaxation is permitted only by dropping complete named constraints or
widening a verifier-derived scalar/state domain. It never changes
serialization, inserts padding, changes a codec, drops a record member, or
narrows a legal range. The certificate identifies every dropped constraint.
The root still validates the retained witness against all exact constraints
and requires a separate exact proof of the complete maximum-length slice.

### 9.5 Verifier-owned strategy selection

The producer never selects an exact/relaxed transfer. For each retained
constraint in frozen evaluation order, the checker derives one strategy by
this total decision function:

1. an identity-field consequence uses the payload-dependent
   `FIXED_VALUE/DERIVED_IDENTITY` node from Section 7.1 and is not a constraint;
   it uses the exact mapping only when the saturated payload-state product and
   mapping compact-byte bound fit the catalog limits, otherwise it uses the
   fixed-width safe upper form and exact maximum-slice reinstatement;
2. a rule whose dependency slice contains only safe-integer paths, literals,
   checked UInt128 add and multiplication with at most one non-fixed operand,
   comparisons, Boolean connectives, null tests,
   array lengths, and present-value comparisons uses
   `BOUNDED_LINEAR_FRONTIER`; disjunctions are expanded in expression-position
   order into a finite union;
3. every other rule whose complete verifier-derived observable-state upper
   bound is within the fixed strategy limits below uses
   `FINITE_STATE_FILTER` when every operator is primitive and
   `EXACT_RULE_EVALUATION` otherwise; either choice emits one constraint node;
4. otherwise the checker inserts
   `SAFE_UPPER_DOMAIN_RELAXATION` for that one complete constraint, in frozen
   constraint order, with output exactly equal to its verified input frontier;
   it then requires that constraint in the exact maximum-length-slice filter.

`FINITE_STATE_PRIMITIVE_OPERATOR_SET_V1` is exactly `INPUT_PATH`, `LITERAL`,
`IS_NULL`, `EQ`, `NE`, `GT`, `GE`, `LE`, `NOT`, `AND`, `OR`, `IMPLIES`,
`PRESENT_EQ`, `PRESENT_LE`, `ARRAY_LENGTH`, `ARRAY_UNIQUE`,
`ARRAY_STRICT_ASCENDING`, and `ARRAY_PROJECT_REQUIRED_MEMBER`. Any other
operator in the accepted 42-rule catalog takes `EXACT_RULE_EVALUATION` unless
step 2's narrower checked-linear grammar applies. An unknown operator is
authority failure, not a producer-selected strategy.

Every strategy upper bound is computed with the same checked saturating
arithmetic. Let `SAT(x, L) = min(x, L + 1)`, where `L` is the relevant
bootstrap limit. A finite literal/enum/Boolean alternative contributes its
exact cardinality. A safe-integer dimension contributes one plus the number of
distinct verifier-derived domain, decimal-width, affine-relation, and codec
breakpoints inside its inclusive domain. A text dimension contributes the
product of its reachable automaton-state count, bounded decoded/source-length
count, bounded canonical-length count, and complete relation-truth-class
count. An array contributes the sum, over every legal cardinality, of the
saturating product of its item-state bound and every position/cardinality
state required by its semantics. A record is the saturating Cartesian product
of child bounds; a union is their saturating sum; a scope is the saturating sum
of its case bounds. Derived-catalog axes use the exact recursively computed
catalog-entry upper bound, not a producer count. A catalog compact-byte bound
is the checked sum of brackets/commas and the exact maximum compact record
width obtained from its closed member schema, state-cell width bounds, and
effective scalar ceilings; it is saturated at 8,388,609 before any catalog is
built. After every add or multiply,
the checker applies `SAT` before the next operation, so it never allocates or
constructs a number above `L + 1`.

The one-node state-entry estimate is that closed bound saturated at
`65,537`. The bitmap-run estimate is
`SAT(state_entries * ceil((effective_ceiling + 1) / 256), 262144)`. The
expanded-point estimate is
`SAT(state_entries * (effective_ceiling + 1), 8388608)`. The transition
estimate is the exact transfer arity applied to those saturated child bounds:
sum for nullable/union/filter, the cardinality-indexed convolution product for
arrays, the Cartesian child product for records, child points times
`(1 + invocation_count)` for scope, and source-state times candidate-class
count for scalar and local recurrences; it is saturated at `67,108,865`. An exact transfer is
selected only when dimensions, catalog entries/bytes, states, runs, expanded
points, and transitions are all at or below their printed limits. The array
safe-upper decision in Section 7.6 uses the same calculation on its required
last-item/used-item ordering state. These formulas do not run the producer or
inspect its certificate.

Equal plan occurrences are never hash-consed. Siblings retain descriptor,
rule, application, and ordinal order from Section 5. There is no cost-based,
wall-clock-based, or producer-selected alternative strategy.

The final exact maximum-slice node evaluates every intrinsic and application
constraint, including any relaxed earlier, and proves the exact target-length
slice under an empty primitive prefix. The following complete measured-then-
context prefix chain computes the deterministic primitive-vector tie-break.
Thus a safe relaxation may prove a byte upper bound but can never prove the
deterministic tie-break by itself.

Plan selection never depends on the pilot-derived acceptance ceilings. That
would make the seed plan circular and could change it during final rebinding.
`PROOF_STRATEGY_BOOTSTRAP_LIMITS_V1` is instead fixed at:

| Strategy quantity | Inclusive limit |
|---|---:|
| observable state dimensions at one node | 64 |
| derived state-catalog entries at one node | 65,536 |
| derived state-catalog compact octets at one node | 8,388,608 |
| state entries at one node | 65,536 |
| bitmap runs at one node | 262,144 |
| expanded attainable points at one node | 8,388,608 |
| estimated local frontier transitions | 67,108,864 |

These limits choose exact transfer versus safe relaxation only. They do not
authorize a certificate, allocation, file, or artifact above an accepted
Section 14 resource ceiling. The exact maximum-slice and attainment proof may
not relax omitted rules; if they exceed an accepted cap, the scope is a
controlled protocol NO-GO rather than a different plan.

Seed execution cannot use the not-yet-measured Section 14 values as allocation
authority. `SEED_EXECUTION_SAFETY_LIMITS_V1` is therefore the following fixed,
immutable table used only during `SEED_CAP_DERIVATION`:

| Proof-resource claim field | Inclusive seed limit |
|---|---:|
| `proof_node_count` | 65,536 |
| `proof_edge_count` | 1,048,576 |
| `maximum_proof_depth` | 65,536 |
| `maximum_child_count` | 65,535 |
| `state_signature_dimension_count` | 4,194,304 |
| `maximum_state_signature_dimension_count` | 64 |
| `state_catalog_entry_count` | 1,048,576 |
| `state_catalog_canonicalized_octets` | 16,773,120 |
| `peak_retained_state_catalog_octets` | 16,773,120 |
| `frontier_state_entry_count` | 1,048,576 |
| `frontier_bitmap_run_count` | 1,048,576 |
| `frontier_expanded_point_count` | 8,388,608 |
| `maximum_frontier_width` | 8,388,608 |
| `peak_retained_frontier_octets` | 16,773,120 |
| `frontier_transition_count` | 67,108,864 |
| `frontier_canonicalized_octets` | 536,870,912 |
| `hash_preimage_octets` | 536,870,912 |
| `component_choice_coordinate_count` | 65,536 |
| `certificate_canonical_octets` | 16,773,120 |

The table is part of the candidate protocol before the seed runs, is not
derived from a pilot measurement or producer claim, and does not select an
exact-versus-safe strategy. `16,773,120` is the largest 4,096-byte multiple
strictly below the 16 MiB per-file exclusion boundary. The two 512 MiB limits
bound streamable canonical/hash work, not retained certificate memory. During
final rebinding and production, each independently accepted Section 14 ceiling
replaces its corresponding seed limit and must be no greater than it; otherwise
the candidate is controlled NO-GO. The final uncapped
`state_signature_dimension_count` remains bounded by the checked product of
the accepted proof-node and one-node maximum-dimension ceilings. Changing this
seed table changes the candidate protocol and requires a new seed cycle.

For every charged operation the checker first computes the prospective count
or canonical length with checked safe-integer arithmetic, rejects if it exceeds
the effective limit, commits the meter increment, and only then allocates,
appends, inserts, decodes, emits canonical bytes, or passes bytes to a digest.
Maximum fields use the same order before materializing the object that would
establish a new maximum. Producer claim values never act as limits. Before
whole-object JSON decoding, a bounded path-aware lexical pre-scan enforces file
bytes, nesting, proof/certificate container cardinalities, and every directly
observable structural limit; semantic and derived allocations then use the
same meter. A generic post-`json.loads` array check is not pre-allocation
enforcement.

## 10. Local-shutdown minimality

The separate local-shutdown certificate uses the same prior-position node
grammar and the exact eleven mutable domains/five inequalities frozen in the
correction. Its objective is:

```text
(
  changed_limit_field_count,
  sum_of_absolute_integer_deltas,
  changed_member_names_in_lexical_order,
  resulting_changed_values_in_that_same_order
)
```

The checker derives decimal/inequality/wrapper-byte breakpoints, then performs
the exact Section 7.13 recurrence in lexical mutable-member order. A proof
state retains the complete processed prefix, changed positions, checked
UInt128 delta sum, five tri-state inequalities, and—only when complete and
feasible—the prospective root. The verifier derives the Section 7.13 objective
prefix and recurrence-equivalence key. Incomplete feasible states are never
dominance-pruned: exact prefix values are mandatory because tri-state relation
classes do not encode continuation thresholds. Dominance is confined to
complete feasible states with byte-equal derived prospective-frontier keys and
a strictly better typed objective.

For each syntactically legal candidate spec, `prospective-result byte frontier`
has one exact meaning: run this same protocol's
`PROSPECTIVE_BYTE_MAXIMUM_WITH_ONE_MASKED_OUTER_CODEC` calculus over
the complete `CapacityMeasurementOperationResultEvidence` wrapper, dispatching
the `LOCAL_SHUTDOWN_RESULT_EVIDENCE_V2` body and treating the candidate spec as
the signed-spec authority. Every wrapper member is byte-equal to the accepted
V3 `/fixture_records/operation_results/LOCAL_SHUTDOWN` record except `result`
and the recomputed `result_evidence_id`; the spec baseline is the profile-3
pointer `/fixture_records/operation_specs/LOCAL_SHUTDOWN`, with only the named
limit members and recomputed `operation_spec_id` changing. These pointers and
field equalities are verifier-derived, not certificate choices. The fixture fixes every wrapper/non-limit input;
the optimizer considers every nullable branch, all five result arrays and
their contents/identities, all counters, trace/error fields, nested codecs,
intrinsic rules, and the complete signed-spec matrix. It recomputes every
derived identity and applies the ordinary byte/primitive tie-break while
masking only the outer wrapper `LT 524288` coordinate. Every nested body/array/
record codec remains active. The
prospective result retained in the counterexample must byte-equal this unique
inner winner. A hand-built large result, truncated array, or producer-selected
nullable branch rejects.

The root proves the baseline is legal/below the bound, every strictly better
objective is impossible or below 524,288, and the retained mutation is legal
under every check except the named outer strict codec bound. Validation then
runs the correction's two isolated passes: a pass masking only that exact
outer check, followed by the unchanged runtime requiring the exact structured
rejection coordinate. Here “unchanged runtime” means the exact same independent
verifier validation path with no mask; it does not mean importing production
`riskyieldmm` or a producer. Any second bypass or different failure rejects.

## 11. Identity and filesystem acyclicity

The identity direction is exactly:

```text
protocol physical SHA
  -> scope IDs and context-object IDs
  -> context pages
  -> context manifest
protocol SHA + proof-scope authority ID + proof-context authority ID
  -> proof-node IDs
  -> certificate ID
  -> maximum-witness ID
  -> row raw SHA
context-manifest ID + ordered row entries
  -> main maximum-witness manifest ID
```

No child contains a parent ID. No proof or object contains a row/main-manifest
ID. The independent verifier applies the exact directory-descriptor,
no-follow, regular-file, single-link, stable-read, unique-inode, exact-closure,
and manifest-last publication rules frozen in correction Section 11.3.

The “exact accepted filesystem closure” in correction Section 11.3 is the
maximum-witness directory subclosure: main manifest, context root/pages,
474 rows, and listed context objects. The mandatory
`tests/raw_v8_step2_external_schema_v2_local_shutdown_unrepresentable_v49f.json`
is one separately bounded sibling artifact. Final Step-2 acceptance requires
both subclosures; the counterexample is never a main-manifest row and never
feeds a context/row/main-manifest identity.

## 12. Solver/checker separation

The eventual maximum producer may import neither the independent checker nor
its private functions. The checker may import neither the producer nor
production `riskyieldmm`. Both may consume the same immutable V3 inventory,
registry, Unicode sources, literal authority, pilot application/materialized-
context authorities, and protocol bytes. The checker
uses only the Python standard library and independently implements:

- strict bounded JSON decode and canonicalization;
- authority and identity recomputation;
- proof-plan derivation;
- all fourteen node transfers;
- exact frontier/bitmap-run normalization and digests;
- witness/context resolution and complete rule/application execution; and
- filesystem closure revalidation.

AST/import tests reject direct imports, dynamic file loading, subprocess calls
to the producer, reflection over production modules, pickle/marshal, network
access, and arbitrary expression evaluation. Shared immutable data is not
shared maximizing logic.

## 13. Six-case pre-freeze pilot

Before this document can change to frozen GO, the independent checker must
validate six non-authoritative pilot certificates generated by a distinct
producer:

1. `SMALL_BOOL_SCALAR`: `CapacityMeasurementBoolValueV1`, `INTRINSIC_TYPE`,
   `SELF_RECORD`. The exhaustive two-value oracle must prove that
   `{"kind":"BOOL","value":false}` is the 29-octet maximum and that `true`
   is 28 octets; a producer assertion is insufficient.
2. `OWNER_LOCAL_SHUTDOWN_RESULT_UNION`:
   `CapacityMeasurementOperationResultBody`,
   `OWNER_MEMBER_UNION_VALUE`, alternative
   `LOCAL_SHUTDOWN_RESULT_EVIDENCE_V2`, owner
   `CapacityMeasurementOperationResultEvidence`, path `["result"]`. It measures
   body bytes while retaining the complete owner's strict `< 524288` codec.
3. `RAW_STRING_ARRAY_RECORD`:
   `CapacityMeasurementVocabularyDefinitionV1`, `SELF_RECORD`. Its `members`
   domain is `RAW_CANONICAL_JSON_STRING[1..512]` under strict ascending order
   and the record's `LE 3145728` codec; it exercises escaping, every
   cardinality, ordering, gaps/residues, and the primitive tie-break.
4. `LOCAL_SHUTDOWN_FIXTURE`: outer
   `CapacityMeasurementOperationResultEvidence`, `FROZEN_FIXTURE`, V3 profile
   position 3 / ID
   `92a80f3b2dc5d4b9a6284adfb6819823de7e2546d4141b2b12c5c7c9afff21f4`,
   baseline spec ID
   `f88cf223f28a146b08b5ffbb3b5ce419fb7ce473563edb27900983d6583a2d21`.
   It exercises all five spec-intrinsic and all fifteen signed operational
   relations; the minimality search is metered separately from the fixture row.
5. `MAX64_EXACT_MARKER_ROOT`: selector
   `INGRESS_MAX64_PARSER_UNITS`, selector position 64, outcome `EXACT_MARKER`,
   profile position 369 / ID
   `505dac244288e6fb666919c99567f883c28ed573a898ce2a5dd680744dd57540`.
   It retains the 67-observation reference context and 137-call schedule.
6. `MAX64_PLACEHOLDER_ROOT`: the componentwise resource maximum across all four
   unavailable outcomes at the same selector coordinate, not a
   reason-string-length guess: profile 370 `ARTIFACT_BOUND_EXCEEDED` /
   `b764c8c83c39681fe5de8c4064dd8dd25a97dd48c170f1206ce4e1904be74146`,
   profile 371 `OBSERVER_INTERNAL_ERROR` /
   `323d26f06e1ac00198f8dfe9627b9d1759fcbe856ae4e2b68636c14e15785532`,
   profile 372 `SOURCE_CLOCK_UNAVAILABLE` /
   `46c0032e1f747c59b6e60e1bee4edf92c24d2894e9755c4c27d6362810066a47`,
   and profile 373 `TARGET_BOUNDARY_NOT_REACHED` /
   `ab3d22d821ab9f68654e3f4c692db7021caeaab517cf0271078a38a3397b0cb1`.
   Outcome/state differences cannot be pruned.

The max64 cases must reconstruct the accepted reference-based full-67 context
byte-for-byte and report complete resolved object counts/bytes. Pilot inputs
are labelled non-authoritative and cannot appear in the 474-row manifest.

Each pilot uses the exact Section 13.1 case/binding/certificate/resource
records. Only their deterministic counts are acceptance authority. Elapsed
time, peak resident memory, host/binary identity, warm/cold state, and I/O are
permitted only in a separate unbound telemetry sidecar and never influence a
cap, ID, or acceptance decision.

### 13.1 Pilot and structural-preflight artifact

The distinct producer first writes one non-authoritative but retained seed
artifact against the candidate protocol bytes, then writes the deterministic
final artifact after the resulting caps are inserted and the document bytes
change. Both files are required so a standalone checker can compare the two
runs:

```text
scripts/tests/
  raw_v8_step2_external_schema_v2_maximum_protocol_pilot_seed_protocol_v49f.md
  raw_v8_step2_external_schema_v2_maximum_protocol_pilot_seed_v49f.json
  raw_v8_step2_external_schema_v2_maximum_protocol_pilot_v49f.json
```

Its root has exactly:

```text
artifact_version
canonicalization_version
measurement_schema_version
pilot_phase
seed_protocol_sha256 | null
seed_protocol_raw_octet_count | null
maximum_protocol_sha256
seed_artifact_raw_octet_count | null
seed_artifact_raw_sha256 | null
source_inventory_sha256
external_schema_registry_id
rule_literal_authority_sha256
application_witness_raw_sha256
max64_context_authority_raw_sha256
ordered_pilot_case_records
local_shutdown_minimality_pilot_record
ordered_row_preflight_records
local_shutdown_minimality_preflight_record
metric_rounding_catalog
derived_resource_ceiling_record
phase_invariant_payload_sha256
maximum_protocol_pilot_id
```

The version is
`riskyieldmm.raw_v8_step2_external_schema_v2.maximum_protocol_pilot.v1`.
The pilot ID domain over every preceding member is:

```text
RiskYieldMMA2MStep2ExternalSchemaV2MaximumProtocolPilotV1V4_9F_RawV8
```

The seed has `pilot_phase = SEED_CAP_DERIVATION`, null
`seed_protocol_sha256`, null `seed_protocol_raw_octet_count`, null seed-artifact
count/hash, and binds the candidate document as `maximum_protocol_sha256`. The
producer atomically retains those exact candidate bytes at the fixed
`pilot_seed_protocol` path before writing the seed JSON; it is never acceptance
authority. The final artifact has `pilot_phase = FINAL_PROTOCOL_REBIND`, pins
that securely reread snapshot's exact SHA/count as `seed_protocol_sha256` and
`seed_protocol_raw_octet_count`, binds the final document digest as
`maximum_protocol_sha256`, and pins the securely reread seed JSON's exact raw
count/hash. The snapshot must byte-equal the candidate document used to derive
the seed and may differ from the final document only in the status line,
and the 22 Section 14 accepted-ceiling cells. The only permitted status
replacement is from the exact current candidate text to
`FROZEN GO — PILOT AND INDEPENDENT VERIFIER ACCEPTED`; every ceiling
replacement is from the literal token `PILOT_PENDING` to one canonical
nonnegative decimal integer. No heading, whitespace, date, prose, table order,
or other byte may change during rebind. The independent checker uses the retained
snapshot to validate every seed semantic ID and plan rather than treating its
digest as an opaque salt. `application_witness_raw_sha256` is the pilot-only
application-witness pin and `max64_context_authority_raw_sha256` is exactly the
separate materialized-context physical pin from Section 2.

For `phase_invariant_payload_sha256`, the checker starts with the complete root
before that field and `maximum_protocol_pilot_id`, recursively deletes every
mapping member whose name ends `_id`, `_ids`, or `_sha256`, and additionally
deletes `pilot_phase`, `seed_protocol_raw_octet_count`, and
`seed_artifact_raw_octet_count`. All other members,
including their null values and array positions, remain. It then hashes the
compact canonical remaining value. The
seed and final digests and remaining projected values must be byte-equal. Both
complete artifacts are independently validated first, so deleting identity
and digest fields from this comparison cannot make an invalid identity valid.
This exact projection proves that bindings, embedded frontiers, retained
records, measurements, structural preflights, and caps did not change while
allowing the protocol-dependent identity chain to rebind. A final metric,
plan, frontier, retained-record, preflight, or cap change returns the protocol to
candidate and requires a new seed cycle.

There are exactly six ordered case records in Section 13 order; case six
contains four ordered outcome subrecords and its metrics are their
componentwise maximum. There are exactly 474 structural preflight records in
row order.
Each pilot case record has exactly:

```text
case_position
case_id
case_binding
ordered_outcome_subrecords
pilot_context_manifest | null
pilot_witness_record | null
pilot_scope_witness_context | null
ordered_component_choice_evidence
pilot_upper_bound_certificate | null
producer_resource_measurement
pilot_case_id
```

`case_binding` has exactly:

```text
type_name
alternative_name | null
constraint_scope
constraint_scope_profile_id | null
profile_position | null
measurement_binding
pilot_domain_kind
```

`pilot_domain_kind` is exactly `FULL_FROZEN_SCOPE`; a reduced miniature domain
may exist only in unit tests and cannot enter this artifact or dominate a row.
Cases 1..5 have no outcome subrecords and non-null manifest, retained witness,
and certificate. Their scope context has the exact nullability defined by
correction Section 11.3 and their choice-evidence array may be empty only when
the independently derived catalog is empty. Case 6 has null top-level
manifest/witness/context/certificate, empty top-level choice evidence, and
exactly four outcome subrecords in the frozen outcome order. Each outcome
subrecord is a complete retained leaf and has exactly:

```text
outcome_position
checkpoint_outcome
profile_position
constraint_scope_profile_id
pilot_context_manifest
pilot_witness_record
pilot_scope_witness_context
ordered_component_choice_evidence
pilot_upper_bound_certificate
producer_resource_measurement
pilot_outcome_subrecord_id
```

The case/outcome ID domains over every preceding member are respectively:

```text
RiskYieldMMA2MStep2ExternalSchemaV2MaximumProtocolPilotCaseV1V4_9F_RawV8
RiskYieldMMA2MStep2ExternalSchemaV2MaximumProtocolPilotOutcomeV1V4_9F_RawV8
```

`local_shutdown_minimality_pilot_record` is the separate full-scope pilot for
the counterexample calculus. It has exactly:

```text
counterexample_kind
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
producer_resource_measurement
pilot_local_shutdown_minimality_id
```

`counterexample_kind` is `LOCAL_SHUTDOWN_UNREPRESENTABLE_MINIMALITY`. Every
field from the baseline reference through the certificate has the exact
correction Section 12 schema and duplicated-claim equalities. The certificate
uses this protocol's node grammar and local proof authorities. The pilot ID
domain over all preceding members is
`RiskYieldMMA2MStep2ExternalSchemaV2MaximumProtocolPilotLocalShutdownMinimalityV1V4_9F_RawV8`.
This is non-authoritative pilot evidence, never the final counterexample file;
the later solver must reproduce it under the final accepted artifact path and
full two-pass validation.

The witness, scope-context, record-reference, and component-choice records are
the exact correction Section 11.3 and protocol Section 6.5 records. The
certificate's context-manifest ID equals its enclosing leaf manifest ID; its
witness hash/length and winner digests equal the retained witness and resolved
choice evidence. A certificate hash without those retained values rejects.

`pilot_context_manifest` has exactly:

```text
manifest_version
canonicalization_version
measurement_schema_version
maximum_protocol_sha256
source_inventory_sha256
external_schema_registry_id
rule_literal_authority_sha256
application_witness_raw_sha256
max64_context_authority_raw_sha256
ordered_context_object_entries
maximum_context_object_manifest_id
```

Its version and ID domain are:

```text
riskyieldmm.raw_v8_step2_external_schema_v2.maximum_protocol_pilot_context_manifest.v1
RiskYieldMMA2MStep2ExternalSchemaV2MaximumProtocolPilotContextManifestV1V4_9F_RawV8
```

The ID covers every preceding member. An empty ordered entry array is legal.
Every entry has exactly:

```text
context_object_position
context_source_kind
source_authority_sha256 | null
source_json_pointer | null
derived_record_role | null
derived_sequence_ordinal | null
inline_record | null
maximum_context_object_id
record_type_name
record_identity_field
record_identity
record_canonical_byte_length
record_canonical_sha256
```

Positions are contiguous one-based. Entries are strictly increasing by the
protocol-independent tuple `(record_type_name, record_identity,
record_canonical_sha256, context_source_kind, source_json_pointer with null
first, derived_record_role with null first, derived_sequence_ordinal with null
first)` and unique. They are deliberately not sorted by
`maximum_context_object_id`, because that ID rebinds to the protocol SHA and
could reorder the seed/final phase-invariant array. `context_source_kind` is
`INLINE_PILOT_CONTEXT_RECORD` or `MATERIALIZED_MAX64_CONTEXT_POINTER`. The inline
form has a non-null complete record and null authority/pointer/role/ordinal.
The pointer form has null inline record, the exact Section 2 materialized-
context physical SHA, and an RFC 6901 pointer determined only by role:
`/root` for `ROOT_RECORD`, `/selector` for `SELECTOR_RECORD`, or
`/observations/<ordinal>` for `OBSERVATION_RECORD` with exact zero-based ordinal
in `0..66`. Root/selector roles have null ordinal. Any other pointer, authority,
role/null combination, or JSON Pointer escape rejects.

The checker securely reads and hash-pins the complete 16,121,125-octet
materialized authority, requires its exact three-key root
`observations, root, selector`, checks the compact 12,698,603-octet SHA from
Section 2 and the application witness's root/sequence/ordered-ID expectations,
then fully validates all 67 observations, the 64-entry selector, the root,
12,595 identities, intrinsic rules, 68 cross-application invocations, and both
fixed-position resolver closures. It never executes the witness's five English
`ordered_steps`, imports its generator/validator, or mistakes a recipe object
for a record. The separately retained generator, independent validator, and
six focused tests establish the materialized authority's field-by-field
reconstruction before this protocol binds its physical bytes. The selected max64 witness
observation is replaced by the pilot leaf; consequently its root context is an
`INLINE_PILOT_CONTEXT_RECORD` with recomputed observation ID/root identity,
while unchanged nonselected observations may use pointers. The checker
resolves the complete record before using the remaining entry fields. A V3
authority remains a `V3_INVENTORY_POINTER` in scope context and is never copied
into this manifest.

In V1 every selector used by a root scope is the exact profile-permitted
`V3_INVENTORY_POINTER`. It is never copied into the pilot manifest, converted
to `CONTEXT_OBJECT`, or traversed as a descriptor choice. Although the entry
grammar reserves `SELECTOR_RECORD` for physical-authority decoding, no V1
scope-context reference surface can consume it; therefore any such manifest
entry is orphaned and rejects. The materialized max64 authority's top-level
selector is still independently validated as part of that complete pinned
snapshot. A root leaf retains only its recomputed root and non-witness
observations as context objects; the selected observation remains the inline
witness.

For each resolved record, `maximum_context_object_id` is recomputed under the
exact correction Section 11.3 context-object domain and payload, including the
current protocol SHA and complete record. Type, identity, intrinsic legality,
canonical bytes, and codec are revalidated. The case-local manifest is a
pilot-only pointer closure; it does not weaken or replace the production
content-addressed file/page closure. Every `CONTEXT_OBJECT` reference resolves
exactly one entry, every entry is referenced, and no network or unpinned source
is allowed. This gives the checker complete max64 full-67 contexts without
duplicating their 12,660,543 compact observation octets inside each pilot file.

`producer_resource_measurement` has exactly all fields of Section 6.6 followed
by:

```text
resolved_context_reference_count
resolved_context_object_count
deduplicated_context_reference_count
resolved_context_object_octets
maximum_context_object_octets
observation_count
application_invocation_count
charged_cross_rule_evaluation_count
direct_cross_expression_node_count
row_pretty_octets
choice_evidence_pretty_octets
certificate_pretty_octets
total_staged_raw_octets
```

All are deterministic nonnegative safe integers. The checker recomputes its
own measurement and requires exact equality; producer timings/RSS/I/O are
absent. Case 6's top-level measurement is the fieldwise maximum of its four
subrecords and has zero only for a field that is zero in all four.
For one pilot leaf, `resolved_context_reference_count` is the occurrence count
of every resolved `MaximumRecordReferenceV1` whose `reference_kind` is
`CONTEXT_OBJECT` in the complete validated scope-witness context; repeated
references count repeatedly. `resolved_context_object_count` is the number of
distinct `maximum_context_object_id` values among those occurrences. The
manifest is an exact closure, so this distinct set equals every and only entry
in `ordered_context_object_entries`. The historically named
`deduplicated_context_reference_count` is not the retained-object count: it is
exactly
`resolved_context_reference_count - resolved_context_object_count`, the number
of repeated reference occurrences eliminated by leaf-local content-addressed
retention. Thus it is zero when every referenced object is distinct. Empty
scope context produces zero for all three fields. Proof-node locators and
choice-evidence locators that point into an already resolved witness/context
record do not add record-reference occurrences; their identity/hash work is
charged by Section 6.6 instead.
`resolved_context_object_octets` is the sum of compact-canonical byte lengths
of those distinct complete resolved records, once per object ID, and
`maximum_context_object_octets` is their maximum or zero for the empty set.
`choice_evidence_pretty_octets` and `certificate_pretty_octets` measure those
exact values with sorted keys, two-space indent, and final LF.
`row_pretty_octets` measures the same encoding of the exact six-member pilot
leaf projection `case_binding, pilot_context_manifest, pilot_witness_record,
pilot_scope_witness_context, ordered_component_choice_evidence,
pilot_upper_bound_certificate`. `total_staged_raw_octets` is that leaf count
plus the compact canonical bytes of every resolved context object, counted
once per manifest. These pilot measurements do not substitute for the
later production-row/context hard-cap enforcement.

For `local_shutdown_minimality_pilot_record`, `row_pretty_octets` instead
measures its complete record excluding `producer_resource_measurement` and
`pilot_local_shutdown_minimality_id`; `choice_evidence_pretty_octets` is zero,
and `certificate_pretty_octets` measures `minimality_certificate`.
`total_staged_raw_octets` equals that row count because its baseline is a V3
pointer and its mutated spec/prospective result are already inline.

Each `ordered_row_preflight_records` item has exactly:

```text
row_position
row_kind
type_name
alternative_name | null
constraint_scope_profile_id | null
dimension_vector
derived_proof_plan_node_count
derived_choice_coordinate_count_upper_bound
ordered_exercising_pilot_case_ids
preflight_status
```

`row_kind` is exactly `INTRINSIC_RECORD`,
`INTRINSIC_UNION_ALTERNATIVE`, `FROZEN_FIXTURE_OUTER_RESULT`, or
`FROZEN_ROOT_OBSERVATION`, with the exact position ranges from correction
Section 11.1. The checker independently derives each row, its complete plan,
and this exact dimension vector:

```text
reachable_type_count
reachable_value_schema_count
reachable_intrinsic_rule_count
reachable_intrinsic_expression_node_count
member_occurrence_count
nullable_occurrence_count
union_alternative_count
maximum_array_cardinality
maximum_text_canonical_octets
context_record_reference_count
observation_count
application_invocation_count
charged_cross_rule_evaluation_count
direct_cross_expression_node_count
owner_codec_octet_limit | null
measured_codec_octet_limit
```

All non-null values are nonnegative safe integers and nullability is exact for
owner-only dimensions. The derivation is closed as follows. `reachable_*`
counts unique registry semantic IDs reached by dependency DFS from the row's
validation root, ordered descriptor members, attached rules, owner, and scope
applications; expression nodes are unique by `(constraint_id,
expression_position)`. Member/nullable/union occurrences are plan occurrences
without deduplication. The two maxima range over all reachable occurrences
after applying their Section 5 effective ceilings. Context references,
observations, application invocations, charged evaluations, and direct
expression nodes are checked sums over every canonical scope case and its
frozen schedule, retaining repeated occurrences. Codec limits are the measured
coordinate and optional owner coordinate derived from the binding; the owner
field is null exactly when no distinct owner exists.

`context_record_reference_count` counts non-null
`MaximumRecordReferenceV1` occurrences in those complete scope cases. Thus an
outer-result case contributes two (measured result plus operation-spec
authority); an owner-member intrinsic case contributes one; and a root case
with `N` observations contributes `N + 3 + s`, for its root, all `N`
observation references, target registry, marker contract, and the selector
only when selector-present bit `s = 1`. A null selector field contributes
zero. Storage deduplication does not reduce this occurrence count.

`derived_proof_plan_node_count` is the exact canonical-plan occurrence count
before frontier search. `derived_choice_coordinate_count_upper_bound` is the
exact size of the complete guarded coordinate catalog: expand each array
through maximum cardinality, include every nullable/union/scope alternative,
sum rather than select guarded branches, and retain repeated occurrences. It
is called an upper bound only because a retained winner activates a subset;
its structural value is not witness-dependent. All counts use checked
saturating preflight arithmetic and reject if the exact safe-integer result
cannot be represented.

`ordered_exercising_pilot_case_ids` is exactly all six Section 13 case IDs in
case-position order for every row. This is deliberately protocol-level kernel
coverage metadata, not a claim that one pilot dominates or resembles that row;
using a producer-selected feature-overlap subset is forbidden.
`preflight_status` is exactly
`PLAN_DERIVED_ACTUAL_RESOURCES_PENDING_SOLVE`. Missing, duplicate, reordered,
or non-derived records reject.

`local_shutdown_minimality_preflight_record` has exactly:

```text
counterexample_kind
dimension_vector
derived_proof_plan_node_count
derived_choice_coordinate_count_upper_bound
ordered_exercising_pilot_case_ids
preflight_status
```

`counterexample_kind` is exactly `LOCAL_SHUTDOWN_UNREPRESENTABLE_MINIMALITY`.
Its remaining fields follow the row-preflight semantics, with the exact
minimality plan and ordered pilot IDs
`OWNER_LOCAL_SHUTDOWN_RESULT_UNION`, `LOCAL_SHUTDOWN_FIXTURE`. It makes no claim that the later
complete solve will fit; exceeding a frozen cap is controlled NO-GO.

The preflight deliberately does not infer frontier, transition, certificate,
row, or aggregate costs from coarse structural dimensions. Those costs are not
generally monotone in this vector. The six measurements support selection of
practical hard limits; the later 474-row solver and local-minimality solver must
measure actual deterministic units and fail before exceeding them. Protocol GO
therefore means “the language/checker/caps are usable,” not “all unsolved rows
are already proved to fit.”

Each `metric_rounding_catalog` item has exactly:

```text
metric_position
metric_name
rounding_unit
measured_pilot_maximum
rounded_ceiling
ceiling_slack
```

Positions/names/rounding units equal the Section 14 resource table.
The measurement population contains exactly ten complete leaves: cases 1–5,
the four case-6 outcome leaves, and the separate local-minimality pilot. The
top-level case-6 componentwise summary is excluded so those four leaves are
not double-counted. `measured_pilot_maximum` is mapped exactly as follows:

| Metric positions | Exact pilot aggregation |
|---|---|
| 1–18 | maximum of the explicitly mapped Section 6.6 field below over the ten leaves |
| 19 | maximum `row_pretty_octets` over the ten leaves |
| 20 | sum of compact bytes of distinct resolved context records across the nine ordinary byte-maximum leaves, deduplicated by `(record_type_name, record_identity, record_canonical_sha256)`; local contributes zero |
| 21 | sum of `row_pretty_octets` over the ten leaves |
| 22 | exact retained seed-pilot file raw octets plus metric 20 |

For positions 1–18, the ordered field map is respectively
`proof_node_count`, `proof_edge_count`, `maximum_proof_depth`,
`maximum_child_count`, `maximum_state_signature_dimension_count`,
`state_catalog_entry_count`, `state_catalog_canonicalized_octets`,
`peak_retained_state_catalog_octets`, `frontier_state_entry_count`,
`frontier_bitmap_run_count`, `frontier_expanded_point_count`,
`maximum_frontier_width`, `peak_retained_frontier_octets`,
`frontier_transition_count`, `frontier_canonicalized_octets`,
`hash_preimage_octets`, `component_choice_coordinate_count`, and
`certificate_canonical_octets`. The seed file uses sorted-key two-space-indent
plus final-LF encoding. Because its own metric-22 decimal width affects that
length, the producer and checker solve the least nonnegative safe-integer digit-
width fixed point and then byte-measure the completed file. The final rebind
retains this seed measurement; its own different raw length does not replace
it.

`rounded_ceiling` is an explicitly frozen operational limit, is an integer
multiple of the rounding unit, and is at least the measured maximum.
`ceiling_slack = rounded_ceiling - measured_pilot_maximum`. No percentage,
producer-selected rounding unit, implicit max-versus-sum choice, or case-6
double count is admitted. The acceptance report states the deterministic
rationale for any ceiling above the least enclosing multiple; aggregate caps
may account for the 474-row/one-counterexample production cardinality but may
not rely on an unmeasured deduplication estimate.

`derived_resource_ceiling_record` has exactly one member per Section 14 metric,
using the printed metric name converted to lowercase snake case, in that same
logical order. Its values equal `metric_rounding_catalog[*].rounded_ceiling`.

## 14. Resource ceilings

The final numeric ceilings will be inserted once the six full-scope cases,
local-minimality pilot, and 474-row structural preflight have run on the
accepted authority bytes. These are operational acceptance limits, not a
claim that the still-unsolved 474 frontiers are globally dominated by six
examples. They satisfy all of these rules:

1. each ceiling is at least the measured pilot maximum for its unit;
2. every cap is an integer multiple of the printed fixed unit, percentage
   headroom is forbidden, and its selection rationale is recorded in the
   acceptance report;
3. node/edge/frontier/work ceilings remain low enough for bounded independent
   checking and below the 16 MiB per-file contract;
4. context closure has a practical aggregate byte ceiling strictly below the
   theoretical 7,003,576,276-octet bound; observed or expected deduplication
   never permits the generator to exceed it;
5. row bytes, all row bytes, context bytes, proof work, and total artifact
   bytes have separate ceilings; and
6. wall-clock or RAM observations never substitute for deterministic units.

Until the table below contains accepted integers and the checker enforces
them, protocol status remains candidate:

| Position | Exact metric name | Resource | Rounding unit | Accepted ceiling |
|---:|---|---|---:|---:|
| 1 | `PROOF_NODE_COUNT_PER_CERTIFICATE` | proof nodes per certificate | 1 | `PILOT_PENDING` |
| 2 | `PROOF_EDGE_COUNT_PER_CERTIFICATE` | proof edges per certificate | 1 | `PILOT_PENDING` |
| 3 | `MAXIMUM_PROOF_DEPTH_PER_CERTIFICATE` | proof depth per certificate | 1 | `PILOT_PENDING` |
| 4 | `MAXIMUM_CHILD_COUNT_PER_NODE` | child positions per node | 1 | `PILOT_PENDING` |
| 5 | `MAXIMUM_STATE_SIGNATURE_DIMENSION_COUNT_PER_NODE` | state dimensions per node | 1 | `PILOT_PENDING` |
| 6 | `STATE_CATALOG_ENTRY_COUNT_PER_CERTIFICATE` | derived state-catalog entries | 1,024 | `PILOT_PENDING` |
| 7 | `STATE_CATALOG_CANONICALIZED_OCTETS_PER_CERTIFICATE` | derived state-catalog compact octets | 4,096 | `PILOT_PENDING` |
| 8 | `PEAK_RETAINED_STATE_CATALOG_OCTETS_PER_CERTIFICATE` | peak live derived state-catalog octets | 4,096 | `PILOT_PENDING` |
| 9 | `FRONTIER_STATE_ENTRY_COUNT_PER_CERTIFICATE` | frontier state entries per certificate | 1,024 | `PILOT_PENDING` |
| 10 | `FRONTIER_BITMAP_RUN_COUNT_PER_CERTIFICATE` | frontier bitmap runs per certificate | 1,024 | `PILOT_PENDING` |
| 11 | `EXPANDED_FRONTIER_POINT_COUNT_PER_CERTIFICATE` | expanded frontier points per certificate | 1,024 | `PILOT_PENDING` |
| 12 | `MAXIMUM_LIVE_FRONTIER_WIDTH` | maximum live frontier width | 1,024 | `PILOT_PENDING` |
| 13 | `PEAK_RETAINED_FRONTIER_OCTETS_PER_CERTIFICATE` | peak retained frontier allocation bytes | 4,096 | `PILOT_PENDING` |
| 14 | `FRONTIER_TRANSITION_COUNT_PER_CERTIFICATE` | frontier transitions per certificate | 1,024 | `PILOT_PENDING` |
| 15 | `FRONTIER_CANONICALIZED_OCTETS_PER_CERTIFICATE` | frontier canonicalized octets per certificate | 4,096 | `PILOT_PENDING` |
| 16 | `HASH_PREIMAGE_OCTETS_PER_CERTIFICATE` | hash-preimage octets per certificate | 4,096 | `PILOT_PENDING` |
| 17 | `COMPONENT_CHOICE_COORDINATE_COUNT_PER_ROW` | complete guarded-plan coordinates per certificate | 1 | `PILOT_PENDING` |
| 18 | `CERTIFICATE_CANONICAL_OCTETS` | certificate canonical octets | 4,096 | `PILOT_PENDING` |
| 19 | `MAXIMUM_ROW_RAW_OCTETS` | any one pretty row or counterexample raw octets | 4,096 | `PILOT_PENDING` |
| 20 | `AGGREGATE_CONTEXT_OBJECT_COMPACT_OCTETS` | aggregate context-object compact octets | 1,048,576 | `PILOT_PENDING` |
| 21 | `AGGREGATE_ROW_RAW_OCTETS` | aggregate row raw octets | 1,048,576 | `PILOT_PENDING` |
| 22 | `AGGREGATE_COMPLETE_ARTIFACT_RAW_OCTETS` | aggregate complete artifact raw octets | 1,048,576 | `PILOT_PENDING` |

Every overflow is a controlled artifact NO-GO. The checker increments before
performing the charged operation and rejects before allocating or decoding
beyond the relevant cap.

Metric 21 is the checked sum of all 474 pretty row files plus the separate
local-shutdown counterexample file. Metric 22 is metric 21 plus every compact
context object, context page/root manifest, row manifest, and exact directory
metadata file admitted by the correction's closure. No file may individually
reach 16,777,216 raw octets, regardless of a larger aggregate cap.

## 15. Independent verifier order

The checker performs exactly this fail-closed sequence:

1. securely read and hash-pin protocol, correction, inventory, registry,
   literal authority, pilot application/context authorities when validating the
   pilot, Unicode sources, and artifact closure, then run the path-aware bounded
   lexical pre-scan before whole-object decode;
2. reject noncanonical JSON/scalars/paths/files and any structural seed/final
   limit excess before semantic work;
3. independently validate the V3 inventory and all selected scope profiles;
4. recompute context objects, pages, manifest, references, and identities;
5. derive the row universe/order and the one legal proof plan;
6. validate exact certificate keys, node positions, child identities, and
   reachability; parse resource claims as equality targets only, never limits;
7. validate every embedded output frontier by its closed local transfer from
   already-verified children under the independent meter, recompute both exact
   digests, and never call the producer or rerun its global search;
8. resolve and fully validate the retained witness/context under all exact
   schema, intrinsic, application, owner, and codec rules;
9. compare all 19 recomputed claim fields, solve the joint certificate
   hash/length fixed point, and prove upper-bound equality, exact maximum-slice
   tie-break, row duplicated equalities, scope ID, certificate ID, and witness
   ID;
10. validate local shutdown in its two isolated passes;
11. verify exact filesystem closure and stable bytes/inodes again; and
12. emit one deterministic JSON report only after all 474 rows and the
    counterexample pass.

No per-row success is final until the aggregate closure and second filesystem
snapshot pass.

## 16. Required adversarial matrix

At minimum the protocol suite must reject:

- unknown node/derivation/state kind or any extra/missing key;
- duplicate, noncontiguous, forward, cyclic, or unreachable node;
- wrong child ID, state signature, frontier/bitmap-run/expanded digest, count, or
  resource sum;
- materialized output where a mandatory alias is required, alias on an active
  or frontier-changing node, alias to a nonnamed/sibling/forward child, wrong
  resolved materialized origin, alias cycle/chain walk, repeated origin
  frontier allocation/hash charge, or alias commitment fields not copied and
  stage-updated exactly as Sections 6.3/6.4 require;
- alias liveness that extends an origin commitment instead of only its
  materialized frontier, or releases an origin frontier before its last
  descendant alias;
- forged non-null pre-maximum choice digest, forged active or inactive prefix
  digest, final inactive digest containing `INACTIVE` or omitting a prior active
  atom, repeated completed-array hash charge, or codec-root digest rewrite;
- primitive `INACTIVE` in a state cell, a guard sentinel on an unguarded/true
  dimension, a non-null sentinel payload, or a copied sentinel without the
  independently verified false guarded child state;
- non-null measured/context digests on a local-minimality root, or failure to
  validate the separate boundary-root winner digests;
- producer-embedded/reused opaque derived catalogs, a catalog ID without its
  independently rebuilt root, root metadata counted as an entry, or catalog
  liveness released while a live frontier or live parent catalog transitively
  references it;
- Unicode relation residual fed from a raw source scalar or provisional open
  NFC segment, a stable normalized flush consumed twice, or two scalar classes
  merged despite different normalized flush/residual behavior;
- min/max-only interval substitution, merged gap, lost residue, wrong bitmap
  bit order, unmerged equal adjacent blocks, or noncanonical bitmap-run order;
- omitted nullable branch, union alternative, array cardinality, owner codec,
  nested codec, intrinsic rule, application, or maximum-slice exact filter;
- all-cardinalities query that admits a count-frontier row below the safe
  array's schema minimum, omits a legal endpoint, or supplies mismatched
  minimum/maximum cardinality bounds; or whose decision Boolean disagrees with
  its empty/nonempty feasible-cardinality bitmap;
- safe relaxation that narrows, filters, rewrites serialization, drops a
  member, or claims a direction other than `LEGAL_DOMAIN_SUPERSET`;
- pruning across unequal ancestor-observable signatures;
- producer-supplied coordinate order, derived identity/hash/path/proof value as
  a choice, or proof bytes used in the objective;
- omitted still-viable safe recurrence, recurrence from a definitely false
  sibling, any recurrence on an inactive prefix, wrong all-vs-fixed cardinality
  boundary, or duplicate/reordered recurrence occurrence;
- derived-identity terminal without `POSITION(0)`, omitted rejected terminal,
  null terminal identity/relation result, rejected terminal with a completion
  or run, nonterminal with identity/relation payload, or a nonleast/non-target
  descendant completion;
- witness shorter than the bound, witness invalid under an exact rule, or an
  illegal relaxed-domain tie winner;
- zero-application scope work charged as zero, active-evidence length used as
  the guarded component count, or a repeated local boundary plan omitted;
- malformed/URI-fragment V3 pointer, SHA substituted for a V3 pointer, or a
  non-SHA witness/context record-reference ID;
- nonleast or unstable joint hash/certificate-length fixed point, trial hash
  work counted as real work, empty-frontier SHA work, or any seed/final cap
  excess discovered only after the prohibited allocation/hash;
- local-shutdown zero/non-limit mutation, wrong delta, skipped better tuple,
  second masked failure, or different unchanged-runtime rejection coordinate;
- any numeric/file/context/aggregate resource excess;
- checker import/reflection/subprocess dependence on producer or production
  maximizing code; and
- mutation after the first authority/closure snapshot.

Positive tests cover all fourteen node kinds, every transfer kind, empty/nonempty
state signatures, gaps/residues, decimal boundaries, null-vs-value ties,
cardinality and union ties, safe relaxation with legal attainment, exact
maximum-slice filtering, owner constraints, and both attainment modes.
The local-minimality root is a separate required positive test in addition to
those two codec-attainment modes.
Alias positives include one materialized maximum slice, one active controller
prefix, 511 guarded descendants whose clauses are false under that controller
and therefore produce consecutive inactive prefix aliases, and the codec-root
alias; mixed
active/inactive chains in which each active node materializes and later
inactive nodes alias it; inactive final measured/context coordinates that
complete winner digests without changing the semantic frontier; an empty
choice catalog whose codec root aliases the maximum slice; and alias depth
exactly at the accepted cap with cap-plus-one rejected before allocation.

## 17. Acceptance transition

The machine-readable transition authority has the fixed path:

```text
scripts/tests/raw_v8_step2_external_schema_v2_maximum_protocol_acceptance_v49f.json
```

Its root has exactly:

```text
artifact_version
candidate_protocol_raw_octet_count
candidate_protocol_sha256
final_protocol_raw_octet_count
final_protocol_sha256
ordered_protocol_rebind_patch_records
seed_pilot_raw_octet_count
seed_pilot_raw_sha256
final_pilot_raw_octet_count
final_pilot_raw_sha256
independent_validator_raw_octet_count
independent_validator_raw_sha256
focused_test_raw_octet_count
focused_test_raw_sha256
acceptance_decision
maximum_protocol_acceptance_id
```

The version is
`riskyieldmm.raw_v8_step2_external_schema_v2.maximum_protocol_acceptance.v1`;
the ID domain over every preceding member is
`RiskYieldMMA2MStep2ExternalSchemaV2MaximumProtocolAcceptanceV1V4_9F_RawV8`.
`acceptance_decision` is exactly `GO`. Every count/hash is a secure reread of
the named retained file and is non-null. A patch record has exactly:

```text
patch_position
patch_kind
candidate_start_octet
candidate_end_octet_exclusive
candidate_bytes_hex
final_bytes_hex
```

There are exactly 23 records: one `STATUS_LINE` then 22
`ACCEPTED_CEILING_CELL` records in resource position order. Candidate spans are
strictly increasing, nonoverlapping half-open raw-byte offsets; their decoded
bytes equal the snapshot at those spans. Status and ceiling replacements obey
the exact Section 13.1 grammar. Streaming unchanged candidate bytes plus each
replacement must reproduce the pinned final bytes exactly. This patch catalog,
not prose in a dated report, defines the complete permitted rebind.

This candidate becomes a narrow protocol GO only after all of the following
are true on the same final tree:

1. the independent validator and focused/adversarial tests exist and pass;
2. the distinct pilot producer emits all six cases deterministically;
3. the checker independently reproduces every pilot frontier, identity,
   context measurement, and resource count;
4. the numeric resource table is filled from the accepted measurements and
   every cap has an enforced boundary/one-over test;
5. the document's final physical byte count/SHA-256 and validator/test/pilot
   identities plus the exact 23-record rebind are recorded in the fixed
   machine-readable acceptance authority above;
6. import-separation, static surface, formatting, compilation, and stale-hash
   scans pass; and
7. the roadmap/status pointers say protocol accepted and maxima still pending.

Only then may the independent maximum solver generate the 474 authoritative
rows and local-shutdown counterexample. Passing this protocol gate is not
evidence that any maximum row has yet been proved.

The bootstrap pin is external by design: after the final edit, the focused
test and acceptance report record this document's physical count/SHA-256, and
the validator compares those expected bytes before semantic work. The document
never embeds or derives its own physical digest.
