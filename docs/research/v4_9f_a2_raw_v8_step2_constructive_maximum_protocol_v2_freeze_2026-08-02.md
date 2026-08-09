# Raw V8 Step-2 constructive-maximum proof protocol V2

Date: 2026-08-02
Status: **CANDIDATE — F0 DESIGN REVIEW FAILED; F1 NOT AUTHORIZED**
Protocol version: `riskyieldmm.raw_v8_step2_external_schema_v2.maximum_protocol.v2`

## 0. Decision boundary

This protocol defines the compact constructive proof required for the 474 Raw
V8 Step-2 External Schema V2 byte maxima and the separate local-shutdown
minimality result. It implements the accepted
`SOUND_UPPER_BOUND_PLUS_LEGAL_ATTAINMENT_V1` rule:

```text
P1  retained witness/context is legal in D_s
P2  every legal x in D_s has L(x) <= U_s
P3  retained witness length L(W_s) = U_s

therefore max_{x in D_s} L(x) = U_s = L(W_s)
```

The verifier may prove P2 over a documented superset of the legal domain, but
P1 and P3 remain exact. A loose upper endpoint that no fully legal witness
attains is a controlled proof failure. No global least attainer is required.
Publication later selects one already verified attainer under
`PINNED_ACCEPTED_ATTAINER_V1`.

This candidate freezes the proof grammar, recurrence, state and cache keys,
meter, deterministic strategy, immutable F0 safety ceilings, F2 rounding
rule, file paths, and report schemas before either F1 implementation runs. It
contains no F1 result and authorizes no candidate witness, pilot, maximum,
production adapter, Raw V8 Step-2 acceptance, A2-M/A2-E acceptance, live
factory, trading, or Stage 1 exit.

The rejected V1 protocol remains historical evidence. No V1 proof artifact,
prefix-chain implementation, or acceptance result is authority for V2.

## 1. Physically and semantically bound authorities

The F1 implementations and future verifier must securely read and pin the
following authorities before semantic use:

| Authority | Repository path or source | Raw octets | Physical SHA-256 / semantic identity |
|---|---|---:|---|
| Accepted compact-proof correction | `docs/research/v4_9f_a2_raw_v8_step2_compact_maximum_proof_v2_correction_2026-08-02.md` | 49,849 | `f4d35405ef1e66a8ba1c59027fc2097a56563d50408eb72cc48895d2127b71b4` |
| Accepted V4 inventory | `tests/raw_v8_step2_inventory_v4_v49f.json` | 5,265,855 | raw `de91eac92d1c36cf1670b2484392fbf1c633d75f928c8e70fcd5e71ae798db2`; semantic `d1435d11a6c9e110b5afb6dacb312f7cd92be71868b2ebe1c8f69ba7f1def3fd` |
| External Schema V2 registry | `scripts/tests/raw_v8_step2_external_schema_v2_structural_registry_v49f.json` | 1,469,663 | raw `9160297ff316c5931737c92f8b359f0a1e2ec22f0aa996ef3b09cf830dc96bf3`; semantic `5dc95a3e99c5646e912b6a7e9c3970cf2489d560ea890b0a19d38af4c51c2140` |
| Rule-literal authority | `scripts/tests/raw_v8_step2_external_schema_v2_rule_literal_authority_v49f.json` | 484,301 | `aba3461059367904734e2eb9ae404787b9aab5ed4c3fbcd292925a364926cce2` |
| V4 row universe | derived from the registry and 408 V4 profiles | 474 rows | compact-canonical digest `836db59c1111080882dea078a27847b130d18eed474a8982ebad2e062d532d1c` |
| V4 profile sequence | 408 complete profile objects | 408 profiles | compact-canonical ID-list digest `b50b97b682d5707062867f2789a204e0488bdc95be7977f9ddc408959d1c9e0e` |

The V4 inventory's five normative documents and their order remain binding.
The six Unicode 15.0.0 source records in the registry are a closed authority
manifest:

```text
DerivedNormalizationProps.txt 837,688  d5687a48c95c7d6e1ec59cb29c0f2e8b052018eb069a4371b7368d0561e12a29
NormalizationTest.txt       2,625,136  fb9ac8cc154a80cad6caac9897af55a4e75176af6f4e2bb6edc2bf8b1d57f326
PropList.txt                  132,360  e05c0a2811d113dae4abd832884199a3ea8d187ee1b872d8240a788a96540bfd
CompositionExclusions.txt      8,911  3b019c0a33c3140cbc920c078f4f9af2680ba4f71869c8d4de5190667c70b6a3
ReadMe.txt                        635  53672c0d0b5185e3cf04c8e970d544c3af81ae7c8eeba0b9cf6d355aa954ae1f
UnicodeData.txt             1,913,704  806e9aed65037197f1ec85e12be6e8cd870fc5608b4de0fffd990f689f376a73
```

The semantic Unicode authority-manifest ID uses domain
`RiskYieldMMA2MStep2ExternalSchemaV2UnicodeAuthorityManifestV1V4_9F_RawV8`
over the six complete registry records in the printed order. Host
`unicodedata` is never authority for proof semantics.

All inputs are opened component-by-component beneath the repository root with
`O_NOFOLLOW`, `O_NONBLOCK`, and close-on-exec where available. Every input must
be a direct regular, single-link file with a unique `(device,inode)` pair.
Size is checked before and after a bounded read; an additional byte must be
EOF; bytes and inode metadata are checked again before publication. Symlinks,
hard-link aliases, FIFOs, devices, sockets, traversal, unstable bytes, duplicate
keys, invalid UTF-8, BOMs, lone surrogates, floats, non-finite values, Boolean
integers, non-I-JSON integers, excessive nesting, and trailing bytes reject.

## 2. Exact verifier-owned case universe

There are exactly 475 top-level verifier-owned cases:

```text
cases 1..474  = the accepted V4 publication-row universe in exact row order
case 475      = the separate LOCAL_SHUTDOWN_UNREPRESENTABLE_MINIMALITY problem
```

The 474 maximum rows are exactly:

```text
49 RECORD descriptors
+ 17 alternatives from the three TAGGED_UNION descriptors
= 66 intrinsic rows

+ 4 OUTER_RESULT_BOUNDARY_FIXTURE profiles
+ 4 NON_CHECKPOINT_ROOT_FAMILY profiles
+ 400 CHECKPOINT_ROOT_COORDINATE profiles
= 474 rows
```

Cases 1..474 bind `row_position`, `row_kind`, `type_name`, nullable
`alternative_name`, and nullable `constraint_scope_profile_id`. Case 475 has no
publication row position. It binds counterexample kind
`LOCAL_SHUTDOWN_UNREPRESENTABLE_MINIMALITY`, ordinary local-shutdown row 69,
profile position 3, profile ID
`92a80f3b2dc5d4b9a6284adfb6819823de7e2546d4141b2b12c5c7c9afff21f4`,
the V2 objective in the accepted correction, and the exact masked prospective
outer-codec coordinate. It neither replaces nor duplicates row 69.

The 408 contextual profiles independently expand to 475 internal scope
subcases and 33 synthetic scope axes under the frozen V3-carried profile
semantics. Those are internal product-domain cross-checks aggregated into their
408 owning maximum cases. They are not the top-level 475-case universe.

## 3. Independence and phase order

The producer may propose witnesses and context bytes. It may not provide an
authoritative bound, recurrence, state partition, cache key, relaxation,
resource count, or proof plan.

The verifier and both F1 implementations import neither a producer nor
`riskyieldmm`; invoke neither through a subprocess; and do not inspect their
source, reflection, annotations, output, cache, pilot, or candidate files.
They derive the case universe, plan, state, safe relaxation, and resource
counts from the pinned authorities and this protocol.

The mandatory order is:

```text
F0  freeze this candidate, strategy, schemas, F0 ceilings, and rounding
F1  freeze A/B source identities; run two independent counting-only preflights
F2  derive limits mechanically; change only the patch allowlist; freeze V2
F2R rerun both preflights against the final physical protocol bytes
F3  implement independent verifier and producer; run the replacement pilot
A   validate selected publication resources against separately frozen caps
```

No later result repairs or supplies evidence for an earlier phase. A pilot
cannot raise an F2 limit. Any disagreement or cap excess is NO-GO.

## 4. Closed derivation grammar

### 4.1 Registry grammar

The accepted registry contains exactly 52 type descriptors: 49 `RECORD` and
three `TAGGED_UNION`. It contains exactly 236 value schemas:

```text
109 TEXT
45  OBJECT_REF
43  ARRAY
37  SAFE_INTEGER
2   EXACT_BOOLEAN
```

The exact value-schema members are:

```text
array_item_value_schema_id
array_maximum_items
array_minimum_items
boolean_literal
integer_maximum
integer_minimum
nullable
referenced_type_name
schema_kind
text_language_id
value_schema_id
```

Record member order is `member_position`; union alternative order is
`alternative_position`. The text-language catalog is closed to `LITERAL`,
`ENUM`, `ASCII_DFA`, `UNICODE_IDENTIFIER`, and `BUILTIN`. Built-in semantics
are exactly `RFC3339_UTC`, `CANONICAL_BASE64`, `LOWERCASE_SHA256`,
`UINT128_DECIMAL`, and `RAW_CANONICAL_JSON_STRING`.

### 4.2 Typed locations and codec coordinates

A typed path is an array of exact steps with members:

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

`step_kind` is exactly `RECORD_MEMBER`, `ARRAY_ITEM`,
`EXTERNAL_SEQUENCE_ITEM`, `UNION_ALTERNATIVE`, or `NULLABLE_BRANCH`. Positions
are contiguous one-based. Array and external-sequence ordinals are zero-based.

A codec coordinate has exactly:

```text
validation_root_type_name
codec_owner_type_name
codec_owner_typed_member_path
codec_byte_bound_relation
codec_octet_limit
```

An `LE L` coordinate has inclusive ceiling `L`; `LT L` has inclusive ceiling
`L - 1`. All subtraction is checked before use.

### 4.3 Derivation kinds

`COMPACT_PRODUCT_RECURRENCE_V2` admits exactly these derivation kinds:

```text
FIXED_AUTHORITY
EXACT_BOOLEAN
SAFE_INTEGER_BAND
TEXT_LITERAL
TEXT_ENUM
ASCII_DFA
UNICODE15_NFC_IDENTIFIER
BUILTIN_RFC3339_UTC
BUILTIN_CANONICAL_BASE64
BUILTIN_LOWERCASE_SHA256
BUILTIN_UINT128_DECIMAL
BUILTIN_RAW_CANONICAL_JSON_STRING
NULLABLE_BRANCH
OBJECT_REFERENCE
ARRAY_STREAM_FOLD
ARRAY_BINARY_LIFT_FOLD
RECORD_MEMBER_FOLD
TAGGED_UNION_BRANCH
DERIVED_IDENTITY_FIXED_WIDTH
EXACT_RULE_FILTER
SAFE_RELAXATION
SCOPE_CASE_UNION
APPLICATION_SCHEDULE_FOLD
CODEC_INTERSECTION
LOCAL_MUTATION_BOUNDARY_SWEEP
```

Unknown kinds reject. V1 frontier nodes, bitmap runs, aliases, maximum-slice
prefix nodes, choice coordinates, and winner-digest nodes are not derivation
kinds.

### 4.4 Closed safe-relaxation enum

Only these relaxations exist:

```text
DROP_COMPLETE_NAMED_CONSTRAINT_TO_SUPERSET_V1
DROP_ARRAY_ORDER_AND_UNIQUENESS_TO_SEQUENCE_SUPERSET_V1
DERIVED_IDENTITY_FIXED_WIDTH_PAYLOAD_SUPERSET_V1
```

The verifier proves the direction of each relaxation from the exact input and
output schemas. A relaxation retains the measured typed path, compact
canonicalization, member punctuation, nullable/union structure, cardinality
limits, nested and owner codec coordinates, and fixed identity output width.
It may not narrow a domain, change serialization, insert padding, drop a record
member, use an identity to recover its payload, or depend on producer/witness
data. Relaxation IDs are derived in authority order.

### 4.5 Plan, state, cache, and result schemas

A `DerivationPlanV2` has exactly:

```text
plan_version
maximum_protocol_sha256
derivation_scope_id
upper_bound_mode
derivation_catalog_id
ordered_safe_relaxation_rule_ids
ordered_derivation_steps
root_derivation_step_position
derivation_plan_id
```

Each derivation step has exactly:

```text
step_position
derivation_kind
subject_locator
value_schema_id | null
type_name | null
alternative_name | null
effective_canonical_octet_ceiling
ordered_child_step_positions
state_signature_id
cache_key_schema_id
recurrence_parameters
batch_equivalence_id | null
derivation_step_id
```

Steps are postorder, positions are contiguous one-based, children precede the
parent, and the last reachable step is the root. No unreachable or duplicate
step is legal.

Every state signature is an exact ordered subset of these component kinds:

```text
DESCRIPTOR_POSITION
VALUE_SCHEMA_POSITION
OCCURRENCE_ORDINAL
ARRAY_ORDINAL
UNION_ALTERNATIVE_POSITION
NULLABILITY_BRANCH
CARDINALITY_BOUNDARY
SAFE_INTEGER_BAND
TEXT_DFA_STATE
TEXT_SOURCE_LENGTH
TEXT_CANONICAL_LENGTH
UNICODE_NORMALIZATION_SEGMENT
TEXT_RELATION_CLASS
ARRAY_ORDER_SUMMARY
ARRAY_UNIQUENESS_SUMMARY
IDENTITY_DEPENDENCY_STATE
OWNER_PROFILE_POSITION
ROOT_FAMILY_POSITION
MODE_ATTEMPT_POSITION
APPLICATION_INVOCATION_ORDINAL
OBSERVATION_ORDINAL
CANONICAL_SYNTAX_BOUNDARY
```

The reverse dependency walk includes every component read by a surviving
ancestor rule, application, identity, codec, or syntax transfer. A relaxation
may remove only the components read exclusively by the dropped predicate. A
max merge is legal only for byte-equal complete keys; an incomplete scalar
`(max,+)` key is forbidden.

The full cache key has exactly:

```text
cache_key_version
derivation_scope_id
derivation_plan_id
derivation_step_position
recurrence_kind
occurrence_ordinal
array_ordinal | null
owner_profile_position | null
application_invocation_ordinal | null
observation_ordinal | null
effective_canonical_octet_ceiling
ordered_state_components
```

Complete compact-canonical key bytes, not their digest or a host hash, are
equality authority. Cache lifetime is one verifier-owned case. The first
insertion of a full key charges one cache entry and its complete key octets.
Lookups do not charge another entry or key bytes. Entries are released in
reverse last-parent order after the root result and streamed digest consume
them. Recomputing a released entry is forbidden.

A result cell has exactly:

```text
ordered_state_components
maximum_attainable_canonical_octets
```

A streamed derivation result has exactly:

```text
result_version
maximum_protocol_sha256
derivation_scope_id
derivation_plan_id
upper_bound_mode
ordered_safe_relaxation_rule_ids
ordered_step_result_commitments
certified_upper_bound_octets
```

Each step commitment has `step_position`, `state_count`,
`maximum_attainable_canonical_octets`, and `ordered_result_cell_digest`. The
stream is in step then complete-key byte order. It contains no witness,
representative, coordinate choice, or least-attainer data.

## 5. Exact recurrence semantics

### 5.1 Minimum and effective-ceiling pass

Before recurrence construction, the verifier computes exact compact minimum
bytes and a safe structural maximum for every reachable occurrence.

- fixed/literal/enum values use exact compact bytes;
- an exact Boolean uses its literal bytes;
- a safe integer uses the least/greatest decimal-width endpoint as applicable;
- a text value includes quotes and exact JSON escaping;
- a 64-character lowercase semantic identity occupies 66 compact octets;
- nullable minimum is `min(4, child_minimum)` and its maximum is the maximum
  of the null and non-null branches;
- an array of `n` items occupies `2 + sum(item_octets) + max(0,n-1)`;
- a record occupies two braces, commas, each compact member-name string, each
  colon, and every member value;
- a tagged union follows the exact selected alternative/owner serialization;
- object references recurse to the referenced type; and
- every type result intersects its own codec ceiling.

The top-down selected-path ceiling subtracts exact syntax and sibling minima
from every ancestor and then intersects the child's own ceiling. It never
subtracts an estimated, witness-derived, or negative value. Fixed root/profile
values resolve from pinned retained authority bytes.

### 5.2 Scalars

`EXACT_BOOLEAN` visits the one frozen literal. `SAFE_INTEGER_BAND` partitions
the inclusive range only at zero, sign, decimal-width, codec, and surviving
rule boundaries. It emits one state per nonempty band and attempts each band
endpoint required to prove its maximum compact width.

Literal and enum text visits every frozen literal in catalog order. ASCII DFA
uses `(input_octet_position, dfa_state, json_cost, relation_state)` and charges
one transition before each admitted-byte transfer. Unicode identifiers use
`(source_scalar_position, normalized_utf8_octets, json_cost, trim_class,
open_normalization_segment, relation_state)` under the pinned Unicode 15.0.0
tables. An open normalization segment is retained by complete scalar bytes,
not a host normalization digest.

Built-ins use their exact frozen grammar. Base64 derives encoded width from
decoded length; SHA-256 is 64 lowercase ASCII characters; UInt128 decimal
partitions at decimal widths; RFC3339 UTC uses the frozen exact form; raw JSON
string uses the complete legal scalar/escape cost classes under the inherited
ceiling. Every scalar DP uses checked formula counts in F1 and bounded streaming
states in the verifier.

### 5.3 Nullable, array, record, union, and identity

Nullable evaluates null and non-null branches. Records fold members in
`member_position` order. Tagged unions fold the fixed row alternative or every
authority-admitted alternative in `alternative_position` order. Derived IDs
are removed from the free primitive domain, recomputed from complete payload
bytes, and reintroduced as fixed-width values.

An array uses `ARRAY_BINARY_LIFT_FOLD` only when all of these are proven:

1. the repeated item transfer is homogeneous;
2. no surviving rule, application, identity, ordering, uniqueness, or
   canonical-boundary observer distinguishes item ordinals;
3. the batched state contains every summary read by an ancestor; and
4. exhaustive unbatched equality has passed for cardinalities 0 through 16.

Otherwise it uses `ARRAY_STREAM_FOLD` in increasing zero-based ordinal order.
The stream retains only the prior fold state and the cached homogeneous item
transfer; it does not allocate one object per possible item.

For homogeneous transfer `T` repeated `n` times, binary lifting uses increasing
bit positions of the canonical binary representation of `n`. The exact number
of composition events is:

```text
binary_lift_compositions(0) = 0
binary_lift_compositions(1) = 0
binary_lift_compositions(n) = floor(log2(n)) + popcount(n) - 1, n >= 2
```

The logical unbatched-equivalent transition count remains `n` times the
single-item transfer count. A batch never erases that metric. Variable arrays
evaluate every cardinality boundary needed by a surviving predicate; under a
complete order/uniqueness relaxation, positive item minima make maximum
cardinality the unique structural maximum-cardinality candidate, while the
exact minimum pass still uses the declared minimum cardinality.

### 5.4 Rules, applications, and strategy selection

Rules execute in intrinsic dependency postorder and then lexical application
name / invocation ordinal order. Strategy is selected before candidate bytes:

1. exact descriptor, canonicalization, nullable/union, identity-width, nested
   codec, and owner-codec transfers are never relaxed;
2. a complete named rule or application predicate uses `EXACT_RULE_FILTER`
   only when its full product-state upper count is at most 65,536 entries and
   its transition upper count is at most 4,194,304;
3. otherwise that complete predicate uses
   `DROP_COMPLETE_NAMED_CONSTRAINT_TO_SUPERSET_V1` in authority order;
4. an ordered/unique array may additionally use the closed sequence superset
   only when no surviving observer reads order or uniqueness; and
5. a payload-derived identity may use the fixed-width payload superset only
   for P2; P1 recomputes the exact identity.

All count estimates use checked UInt128 saturating tests at the F0 value plus
one. No wall time, memory observation, producer result, witness content, hash
table behavior, or F1/F2 result selects a strategy. The final exact candidate
legality pass executes every rule and application even when P2 relaxed it.

### 5.5 Codec and local-shutdown roots

`CODEC_INTERSECTION` applies every nested and owner coordinate and returns the
largest surviving structural/product-state bound. For ordinary rows this is
`U_s`. The legal candidate must independently attain the same value.

Case 475 uses `LOCAL_MUTATION_BOUNDARY_SWEEP` over the exact permitted mutable
limit members. It enumerates signed-range/decimal-width/codec/application
breakpoints, then evaluates candidates in the exact objective order:

```text
changed_limit_field_count
sum_absolute_integer_deltas
changed_member_names_in_lexical_order
resulting_changed_values_in_that_same_order
```

It keeps the single accepted prospective outer-codec mask and no other mask.
Every strictly better objective interval is excluded before the winning
candidate is accepted. It does not reuse V1's global coordinate prefix chain.

## 6. Atomic semantic resource meter

All arithmetic is checked unsigned 128-bit. Published values must fit
`0..9007199254740991`. For a sum event the verifier computes the prospective
value, rejects on arithmetic or limit excess, commits the increment, and only
then allocates, appends, inserts, canonicalizes, hashes, or mutates. A maximum
uses the same order before materializing the value that establishes it.

A transition attempt is charged before state deduplication. A logical
descriptor occurrence uses maximum-cardinality unbatched multiplicity even
when executed as a batch. A recurrence state is charged when a complete result
cell is emitted before byte-key merging. A batch application is one binary
composition or one protocol-defined closed-form homogeneous transfer. Cache
entries/key bytes are charged only on first full-key insertion. Canonical input
octets are complete cache-key and transition-token bytes presented to the
canonicalizer; canonical output octets are their emitted compact bytes plus
complete result-cell compact bytes. Hash-preimage octets are the exact bytes
passed to SHA-256 for derivation plans, steps, state signatures, cache schemas,
stream commitments, and result identities. Authority-file physical hashing is
outside the per-case semantic meter.

An intrinsic-rule evaluation is one execution of a complete intrinsic
expression root for one recurrence state. A cross-rule evaluation is one
execution of a complete cross-record rule root for one application invocation.
An application evaluation is one complete invocation before its rule root.
Expression-node interpreter steps are included in recurrence transitions and
are not a fourth rule counter. Maximum derivation depth is leaf one and parent
one plus maximum child depth. Maximum iteration depth is the greatest
sequential stream-fold, scalar-input, application, or local-boundary length;
binary-lift depth is `ceil(log2(n))` for `n > 1` and zero otherwise.

Peak retained derivation octets use the fixed postorder last-parent schedule:
retain child result cells, cache keys, and commitments through their last
parent; charge the live child set, then the set plus the prospective parent;
release a child immediately after its last parent. Equal bytes in distinct
live entries count separately. A batched repeated item is retained once plus
its fold accumulator. Recomputing released data is forbidden.

The semantic metric catalog is exactly:

| Pos. | Metric | Per-case aggregation | Full-run aggregation | Per-case F0 | Full-run F0 | F2 rounding |
|---:|---|---|---|---:|---:|---:|
| 1 | `SCOPE_CASE_COUNT` | exact | sum | 1 | 475 | 1 |
| 2 | `LOGICAL_DESCRIPTOR_OCCURRENCE_COUNT` | sum | sum | 4,294,967,296 | 1,099,511,627,776 | 1,024 |
| 3 | `RECURRENCE_STATE_ENTRY_COUNT` | sum | sum | 4,194,304 | 268,435,456 | 1,024 |
| 4 | `RECURRENCE_TRANSITION_ATTEMPT_COUNT` | sum | sum | 134,217,728 | 2,147,483,648 | 1,024 |
| 5 | `LOGICAL_UNBATCHED_TRANSITION_EQUIVALENT_COUNT` | sum | sum | 1,099,511,627,776 | 281,474,976,710,656 | 1,024 |
| 6 | `RECURRENCE_BATCH_APPLICATION_COUNT` | sum | sum | 1,048,576 | 134,217,728 | 1,024 |
| 7 | `CACHE_ENTRY_COUNT` | sum | sum | 1,048,576 | 134,217,728 | 1,024 |
| 8 | `CACHE_KEY_CANONICAL_OCTETS` | sum | sum | 268,435,456 | 17,179,869,184 | per case 4,096; full run 1,048,576 |
| 9 | `DERIVATION_CANONICALIZATION_INPUT_OCTETS` | sum | sum | 536,870,912 | 34,359,738,368 | per case 4,096; full run 1,048,576 |
| 10 | `DERIVATION_CANONICALIZATION_OUTPUT_OCTETS` | sum | sum | 536,870,912 | 34,359,738,368 | per case 4,096; full run 1,048,576 |
| 11 | `DERIVATION_HASH_PREIMAGE_OCTETS` | sum | sum | 536,870,912 | 34,359,738,368 | per case 4,096; full run 1,048,576 |
| 12 | `INTRINSIC_RULE_EVALUATION_COUNT` | sum | sum | 134,217,728 | 2,147,483,648 | 1,024 |
| 13 | `CROSS_RULE_EVALUATION_COUNT` | sum | sum | 134,217,728 | 2,147,483,648 | 1,024 |
| 14 | `APPLICATION_EVALUATION_COUNT` | sum | sum | 16,777,216 | 536,870,912 | 1,024 |
| 15 | `MAXIMUM_DERIVATION_DEPTH` | maximum | maximum | 65,536 | 65,536 | 1 |
| 16 | `MAXIMUM_ITERATION_DEPTH` | maximum | maximum | 1,048,576 | 1,048,576 | 1 |
| 17 | `PEAK_RETAINED_DERIVATION_OCTETS` | maximum | maximum | 1,073,741,824 | 1,073,741,824 | 4,096 |
| 18 | `DERIVATION_RESULT_CANONICAL_OCTETS` | sum | sum | 16,773,120 | 4,294,967,296 | per case 4,096; full run 1,048,576 |

No V1 component-coordinate, prefix-node, winner-digest, bitmap-frontier,
proof-node, or certificate-self-size metric exists in V2.

## 7. Immutable F0 platform and artifact ceilings

These denial-of-service ceilings are frozen before F1. They are not claims
that the proof fits:

| Resource | Immutable F0 ceiling |
|---|---:|
| Any individual authority, candidate, report, row, page, or manifest | strictly below 16,777,216 bytes |
| Total pinned input bytes | 67,108,864 |
| Input file count | 64 |
| JSON nesting depth | 96 |
| Decoded JSON nodes | 2,097,152 |
| Any decoded JSON array | 1,048,576 entries |
| F1 wall-clock watchdog | 14,400 seconds |
| F1 CPU watchdog | 28,800 CPU-seconds |
| F1 peak RSS | 2,147,483,648 bytes |
| F1 temporary storage | 4,294,967,296 bytes |
| Publication staging storage | 8,589,934,592 bytes |

Wall/CPU/RSS/storage observations are nonsemantic watchdog telemetry and never
enter F1 equality or F2 derivation. A watchdog abort removes only the private
temporary staging root and publishes no partial output.

Phase A also freezes:

```text
selected rows exactly                         474
context objects at most                    262144
context pages at most                          256
total closure entries at most              263168
aggregate row raw octets at most        2147483648
aggregate context compact octets at most 2147483648
page/manifest/directory metadata at most  536870912
complete published closure at most       4294967296
peak retained validation octets at most  1073741824
```

The already accepted page limits remain 1,024 entries and 1,048,576 raw
octets. The theoretical 7,003,576,276-octet context ceiling is not a practical
authorization. Failure of an actual selected closure to fit is publication
NO-GO or requires selection of another independently verified equal maximum.

## 8. F1 semantic payload and independent reports

Implementation A is a descriptor-forward recursive symbolic counter.
Implementation B is a separately authored flat-ledger iterative counter using
prefix sums, a stable merge, and quotient/remainder batch algebra. Both are
standard-library-only Python programs, share no executable module, and may
share only the frozen authorities and this protocol.

Exact implementation paths:

```text
scripts/tests/preflight_raw_v8_step2_maximum_protocol_v2_a_v49f.py
scripts/tests/preflight_raw_v8_step2_maximum_protocol_v2_b_v49f.py
scripts/tests/compare_raw_v8_step2_maximum_protocol_v2_preflights_v49f.py
```

Seed reports:

```text
scripts/tests/raw_v8_step2_maximum_protocol_v2_preflight_a_seed_v49f.json
scripts/tests/raw_v8_step2_maximum_protocol_v2_preflight_b_seed_v49f.json
scripts/tests/raw_v8_step2_maximum_protocol_v2_preflight_comparison_seed_v49f.json
```

Final-protocol reports use the same names with `_seed` removed. A report has a
semantic payload plus a nonsemantic execution envelope. The semantic payload
has exactly:

```text
schema_version
canonicalization_version
measurement_schema_version
protocol_counting_semantics_id
maximum_protocol_sha256
source_inventory_sha256
external_schema_registry_id
rule_literal_authority_sha256
unicode_authority_manifest_id
f0_seed_ceiling_catalog_id
recurrence_catalog_id
resource_metric_catalog_id
maximum_row_universe_count
maximum_row_universe_canonical_json_sha256
contextual_profile_count
contextual_internal_subcase_count
contextual_synthetic_axis_count
verifier_owned_scope_case_count
ordered_case_count_records
ordered_metric_summary_records
semantic_count_vector_sha256
semantic_count_payload_id
```

Each case record has exactly:

```text
case_position
case_kind
case_binding
ordered_resource_measurements
derivation_event_stream_sha256
case_count_record_id
```

Each resource measurement has exactly:

```text
metric_position
metric_name
measured_value
```

Each metric summary has exactly:

```text
metric_position
metric_name
full_run_aggregation
full_run_value
maximum_case_value
ordered_maximum_case_positions
```

`semantic_count_vector_sha256` hashes only the ordered case bindings,
measurements, event-stream digests, and summaries. It deliberately excludes
the phase-changing protocol hash and protocol-bound semantic IDs. Seed/final
runs must have the same count-vector digest. `semantic_count_payload_id`
covers every preceding semantic-root member.

The nonsemantic execution envelope has exactly:

```text
implementation_id
implementation_repository_relative_path
implementation_raw_octet_count
implementation_raw_sha256
python_implementation
python_version
watchdog_wall_seconds
watchdog_cpu_seconds
observed_wall_nanoseconds
observed_cpu_nanoseconds
observed_peak_rss_octets
observed_temporary_storage_octets
diagnostic_chunk_size
```

It is excluded from semantic equality, identities, limits, and F2. Each report
root has exactly `semantic_payload` then `execution_envelope`.

The comparator independently verifies both report schemas and identities,
cases 1..475, exact 474-row digest/order, separate case 475, metric order,
summaries, checked bounds, source separation, and byte equality of pretty and
compact semantic payloads. It never repairs or merges disagreement.

## 9. F1 controls and acceptance

Both implementations must agree with independently reviewed hand formulas for
cardinalities:

```text
0, 1, 2, 185, 511, 512, 524287, 524288
```

Required composed controls include row 62's `185 * (1 + 512)` historical V1
shape and row 17's four 524,288 arrays plus one 4,096 array. These controls
prove batching/count algebra only; they do not resurrect V1 coordinates.
Batch and unbatched transitions must be exhaustively equal for every generated
small schema/cardinality through 16.

F1 rejects on a missing/duplicate/reordered case, V3 relabelled as V4,
registry/profile/alternative/pointer drift, row 69/case 475 conflation,
internal-subcase/top-level-case conflation, omitted cache-key component,
sum/maximum error, off-by-one application/rule count, batch-boundary error,
skipped local breakpoint, overflow, unsafe JSON/file input, source overlap,
attempted producer/V1/pilot read, nondeterminism, or any F0 excess.

## 10. F2 derivation and patch allowlist

For each sum metric, required per-case value is the maximum across 475 cases
and required full-run value is the exact sum. For each maximum metric, both are
the exact maximum. `SCOPE_CASE_COUNT` remains exactly 1/475.

F2 uses the table's fixed rounding unit:

```text
round_up(x,u) = the least integer y such that y >= x and y mod u = 0
```

There is no percentage headroom. Each F2 value must satisfy:

```text
required F1 value <= F2 value <= corresponding immutable F0 value
```

If no such value exists, the protocol is rejected. The candidate-to-final
physical patch allowlist consists only of:

1. the exact Status line;
2. the seed-protocol raw count/SHA fields below;
3. the six seed source/report raw count/SHA fields below; and
4. the 36 `F1_PENDING` cells in the F2 table.

No recurrence, state, key, batching, relaxation, meter, rounding, identity,
path, case, schema, prose, whitespace, or F0 value may change.

```text
seed_protocol_raw_octet_count = SEED_PROTOCOL_PENDING
seed_protocol_raw_sha256 = SEED_PROTOCOL_PENDING
implementation_a_raw_octet_count = IMPLEMENTATION_A_PENDING
implementation_a_raw_sha256 = IMPLEMENTATION_A_PENDING
implementation_b_raw_octet_count = IMPLEMENTATION_B_PENDING
implementation_b_raw_sha256 = IMPLEMENTATION_B_PENDING
seed_report_a_raw_octet_count = SEED_REPORT_A_PENDING
seed_report_a_raw_sha256 = SEED_REPORT_A_PENDING
seed_report_b_raw_octet_count = SEED_REPORT_B_PENDING
seed_report_b_raw_sha256 = SEED_REPORT_B_PENDING
seed_comparison_raw_octet_count = SEED_COMPARISON_PENDING
seed_comparison_raw_sha256 = SEED_COMPARISON_PENDING
```

| Pos. | Metric | F2 per case | F2 full run |
|---:|---|---:|---:|
| 1 | `SCOPE_CASE_COUNT` | `F1_PENDING` | `F1_PENDING` |
| 2 | `LOGICAL_DESCRIPTOR_OCCURRENCE_COUNT` | `F1_PENDING` | `F1_PENDING` |
| 3 | `RECURRENCE_STATE_ENTRY_COUNT` | `F1_PENDING` | `F1_PENDING` |
| 4 | `RECURRENCE_TRANSITION_ATTEMPT_COUNT` | `F1_PENDING` | `F1_PENDING` |
| 5 | `LOGICAL_UNBATCHED_TRANSITION_EQUIVALENT_COUNT` | `F1_PENDING` | `F1_PENDING` |
| 6 | `RECURRENCE_BATCH_APPLICATION_COUNT` | `F1_PENDING` | `F1_PENDING` |
| 7 | `CACHE_ENTRY_COUNT` | `F1_PENDING` | `F1_PENDING` |
| 8 | `CACHE_KEY_CANONICAL_OCTETS` | `F1_PENDING` | `F1_PENDING` |
| 9 | `DERIVATION_CANONICALIZATION_INPUT_OCTETS` | `F1_PENDING` | `F1_PENDING` |
| 10 | `DERIVATION_CANONICALIZATION_OUTPUT_OCTETS` | `F1_PENDING` | `F1_PENDING` |
| 11 | `DERIVATION_HASH_PREIMAGE_OCTETS` | `F1_PENDING` | `F1_PENDING` |
| 12 | `INTRINSIC_RULE_EVALUATION_COUNT` | `F1_PENDING` | `F1_PENDING` |
| 13 | `CROSS_RULE_EVALUATION_COUNT` | `F1_PENDING` | `F1_PENDING` |
| 14 | `APPLICATION_EVALUATION_COUNT` | `F1_PENDING` | `F1_PENDING` |
| 15 | `MAXIMUM_DERIVATION_DEPTH` | `F1_PENDING` | `F1_PENDING` |
| 16 | `MAXIMUM_ITERATION_DEPTH` | `F1_PENDING` | `F1_PENDING` |
| 17 | `PEAK_RETAINED_DERIVATION_OCTETS` | `F1_PENDING` | `F1_PENDING` |
| 18 | `DERIVATION_RESULT_CANONICAL_OCTETS` | `F1_PENDING` | `F1_PENDING` |

After the final physical bytes are frozen, both implementations rerun without
source edits. Their final semantic payloads must be byte-identical, their
count-vector digest must equal the seed digest, and every final count must fit
the F2 table before a verifier or pilot is authorized.

## 11. V2 proof artifact schemas

The accepted correction's mathematical row, context/reference, page,
publication, and local-shutdown schemas remain exact. The compact upper-bound
certificate has exactly:

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
`LEGAL_DOMAIN_SUPERSET_WITH_LEGAL_ATTAINMENT`. The certificate contains no
resource claim.

The separate resource report has exactly:

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

Its measurement item is the three-member Section 8 record. The semantic meter
closes before report serialization; the report never charges its own encoding,
ID preimage, or hash. The containing row/publication layers bound those bytes.

## 12. Required adversarial evidence

Before protocol acceptance, tests must cover at least:

- exhaustive small-schema equality and batched/unbatched equality;
- two different legal equal maxima both mathematically valid before selection;
- a non-lexicographically-least attainer accepted mathematically;
- legal `U-1`, illegal same-length, producer `U+1`, and unattainable relaxed
  endpoint rejection;
- every omitted state/cache-key component caught by a collision mutation;
- narrowing/reversed relaxation and derived-ID inversion rejection;
- Unicode NFC/source drift, invalid UTF-8/I-JSON/key order/trailing data;
- exact cap success and cap-plus-one pre-allocation rejection for every metric;
- full filesystem attack matrix and second-snapshot instability;
- all 474 rows plus separate local case, with row 69 retained;
- V3/V1 tag/path/version/domain rejection inside every V2 closure;
- local wrong objective, skipped better interval, second mask, and wrong
  runtime-rejection coordinate;
- seed/final unauthorized patch or strategy drift; and
- independent verifier/producer import, reflection, subprocess, and output
  contamination controls.

## 13. Acceptance and abandon conditions

The seed gate may advance to F2 only when two independent F1 implementations
produce byte-identical semantic payloads for all 475 cases, every hand formula
and adversarial control passes, and every required value fits F0. The frozen
protocol may authorize verifier work only after both implementations rerun on
the final bytes and reproduce the same count vector within F2.

Abandon or redesign V2 if the complete state key cannot preserve every
ancestor-observable distinction within F0, independent counts disagree, a
batch fails unbatched equivalence, an exact recurrence disagrees with bounded
exhaustive control, a safe bound is not legally attainable, the verifier
cannot remain independent and auditable, or any proof/publication cap is
exceeded. Failure leaves Raw V8 Step 2 and Stage 1 closed.

## 14. Research basis and limits

The certifying-algorithm boundary follows McConnell, Mehlhorn, Näher, and
Schweitzer, [*Certifying algorithms*](https://doi.org/10.1016/j.cosrev.2010.09.009).
The compositional recurrence direction is informed by Mohri,
[*Semiring Frameworks and Algorithms for Shortest-Distance Problems*](https://cs.nyu.edu/~mohri/pub/jalc.pdf).
These sources support independent checking and algebraic composition; they do
not prove this local state signature, counts, or feasibility.

RFC 8785 supports deterministic JSON representation, while this project keeps
its already frozen `riskyieldmm_canonical_json_v1` key ordering and I-JSON
profile. Unicode normalization remains pinned to UAX #15 version 15.0.0.
Pseudo-Boolean/SMT proof logging may be used only as a separately frozen
differential challenger.

No source or architecture guarantees profitability, predictive edge, or even
that every maximum is feasible under these limits. Only the complete causal
proof, execution evidence, and later trading-system validation can establish
their respective claims.

## 15. Current gate state

```text
V1 feasibility rejection                 ACCEPTED
V2 compact-proof correction              ACCEPTED
V4 successor inventory                   ACCEPTED
V2 F0 seed protocol candidate            REVIEW FAILED / REVISION REQUIRED
V2 independent F1 preflights             NOT STARTED
V2 immutable F2 protocol                 NOT FROZEN
V2 verifier / producer / pilot           NOT AUTHORIZED
474 constructive maxima                  NOT STARTED
local-shutdown V2 result                 NOT STARTED
runtime-work accounting                  INCOMPLETE
production adapters / compatibility      INCOMPLETE
Raw V8 Step-2 acceptance                 NO-GO
A2-M / A2-E / Stage 1                    INCOMPLETE
```
