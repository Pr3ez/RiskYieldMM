# Raw V8 Step-2 external-schema V2 correction

**Date:** 2026-07-28
**Status:** normative correction authority for the superseded clauses listed in
Section 2, amended 2026-08-01 to close the constructive-maximum binding,
deterministic-selection, and bounded-context-artifact contracts; every accepted
V3 inventory must bind these exact document bytes, and constructive-maximum,
production, and target-bound use remain NO-GO until every applicable acceptance
item in Section 17 passes
**Scope:** the independent Raw V8 Step-2 inventory, its external/runtime type
registry, the schema graph used by later target-bound validation, and the
constructive byte-maximum evidence derived from that graph
**Non-scope:** transport execution, plan admission, target projection, lifecycle
replay, trading decisions, profitability, and any change to the accepted Raw V7
contract

## 1. Decision and defect being corrected

The Step-2 V1 external descriptor is lossy. In particular, its member record:

```text
member_position
member_name
value_type
nullable
minimum_integer | null
maximum_integer | null
minimum_items | null
maximum_items | null
maximum_utf8_octets | null
enum_members | null
referenced_type_name | null
```

cannot distinguish all of the following:

- an array of hashes from an array of records or an array of nullable safe
  integers;
- a record reference from any of three finite tagged unions;
- a literal from an enum, or either from an unconstrained text value;
- a byte bound interpreted as `length <= bound` from one interpreted as
  `length < bound`;
- a standalone envelope's serialization order from its identity-payload order;
- intrinsic validation of one record from a rule that binds two records or
  quantifies over a bounded array;
- the Unicode database and normalization algorithm that define a purported
  identifier language.

The V1 generator also assigns member schemas by member-name heuristics. A name
is not a type. Reusing a name in a different record can silently assign an
incorrect nullability, item type, enum, or byte limit.

This correction replaces that representation. It does **not** reinterpret
`RAW_V8_CLOSED_SCHEMA_V1` as a richer dialect. That dialect has no normative
reference node, object-union node, or tagged-union node and therefore cannot
encode this graph without loss. Any artifact claiming that
`RAW_V8_CLOSED_SCHEMA_V1` encoded references or unions is false and rejects.

The initially proposed count of 50 types is also rejected. The exact
transitive Step-2 graph has:

```text
49 concrete runtime record nodes
+ 3 distinct finite tagged-union nodes
= 52 schema graph nodes
```

The three union nodes are the operation-spec body union, operation-result body
union, and target-value union. A wrapper object is not interchangeable with
the body union referenced by one of its members.

## 2. Authority and version transition

This correction supersedes these exact clauses of
`v4_9f_a2_raw_v8_step2_v2_contract_freeze_2026-07-26.md`:

- Section 2's V2 inventory schema literal, exact root, and exact three-record
  normative-document input array;
- Section 9's V1 external descriptor/registry representation;
- Section 11 acceptance language that requires the superseded V2 root or V1
  external registry.

The V3 root, four-input array, and V2 external schema in this correction are
the sole authority for those clauses. All nonconflicting Step-2 freeze
requirements remain in force, including record behavior and boundary
fixtures. This correction does not silently change any runtime record.
Differences between this document's exact record ledger and current
production code are implementation defects unless this correction explicitly
approves the behavior change.

The independent inventory moves to:

```text
inventory schema_version = riskyieldmm.raw_v8_step2_inventory.v3
external schema profile  = riskyieldmm_raw_v8_step2_external_schema_v2
```

The V3 inventory root has exactly these logical keys:

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

`external_schema_registry_v2` is the complete standalone record defined in
Section 3. Its `external_schema_registry_id` occurs only inside that record;
`invariants.exact_semantic_ids` may expose the recomputed value consistently
with the target registry, counter schema, and marker contract, but the
inventory root does not duplicate it. The V1 key `external_type_registry`, a
root `external_schema_registry_id`, any descriptor count at inventory-root
level, and any hash-only replacement of the complete V2 registry reject.

`normative_document_inputs` is the exact four-record array in this semantic
order:

```text
1 PARENT_MARKER_OPERATION_TARGET_PROTOCOL
  docs/research/
  v4_9f_a2_marker_operation_target_v8_protocol_freeze_2026-07-22.md

2 STEP2_V2_CONTRACT_FREEZE
  docs/research/
  v4_9f_a2_raw_v8_step2_v2_contract_freeze_2026-07-26.md

3 STEP2_EXTERNAL_SCHEMA_V2_CORRECTION
  docs/research/
  v4_9f_a2_raw_v8_step2_external_schema_v2_correction_2026-07-28.md

4 STEP3_TARGET_AND_LIFECYCLE_CORRECTION
  docs/research/
  v4_9f_a2_raw_v8_step3_target_and_lifecycle_correction_2026-07-26.md
```

Each input record has exactly
`document_role, repository_relative_path, raw_octet_count, raw_sha256`.
Paths are the literal joined POSIX paths shown above (without visual line
wrapping). Counts and hashes are over exact file bytes with no newline
normalization. The array order above is semantic and is not replaced by hash
or path sorting.

The canonicalization and measurement schema versions remain:

```text
canonicalization_version = riskyieldmm_canonical_json_v1
measurement_schema_version =
  riskyieldmm_physical_transport_a2m_raw_v49f_v8
```

No V1 descriptor, V1 registry list, or V2-inventory/V1-registry mixture is
accepted under the new inventory schema.

### 2.1 Logical order versus canonical JSON key order

All uses of “member order” in this correction mean **logical schema order**
recorded by contiguous `member_position` values or by an explicitly ordered
member-name array. JSON object insertion order is never semantic.

`riskyieldmm_canonical_json_v1` serializes every object with keys in
lexicographic order (`sort_keys = true`), UTF-8 output, no insignificant
whitespace, and the frozen canonical separators. Consequently:

- the logical member order is committed as data in member positions and
  identity-payload member-name arrays;
- canonical object bytes always use lexicographic key order, regardless of
  construction order;
- only JSON arrays have semantic element order;
- an input object with a different key order rejects only because its raw
  bytes differ from the canonical reserialization, not because JSON object
  order has acquired semantic meaning.

### 2.2 Exact local-shutdown operation-contract arrays

Within the V3 root's `operation_contracts` object, each of the following
three keys is required exactly once and has the closed member schema and
semantic array order frozen below. Every relation element is a JSON string
equal to the displayed octets. A missing, duplicated, reordered, altered, or
extra array element rejects.

`local_shutdown_intrinsic_limit_relations` is exactly this five-string array:

```text
1 maximum_terminal_ingress_plaintext_octets<=16384*maximum_terminal_ingress_batches
2 2*maximum_terminal_ingress_parser_units<=maximum_terminal_ingress_plaintext_octets
3 maximum_terminal_tls_records<=maximum_terminal_ingress_batches
4 maximum_terminal_ingress_automatic_outputs<=maximum_terminal_ingress_parser_units
5 maximum_websocket_send_attempts<=256*(1+maximum_terminal_ingress_automatic_outputs)
```

The leading numbers above denote one-based array positions and are not part
of the string values.

`local_shutdown_scalar_limit_domains` is exactly a twelve-record array. Each
record is closed and has exactly these logical members, with the listed JSON
types:

```text
member_name     string
integer_minimum integer
integer_maximum integer
```

Object key order is nonsemantic under Section 2.1; array position and every
member value are semantic. The exact records, in array order, are:

| position | `member_name` | `integer_minimum` | `integer_maximum` |
|---:|---|---:|---:|
| 1 | `maximum_terminal_ingress_batches` | 1 | 9007199254740991 |
| 2 | `maximum_terminal_ingress_ciphertext_octets` | 1 | 9007199254740991 |
| 3 | `maximum_terminal_ingress_plaintext_octets` | 1 | 9007199254740991 |
| 4 | `maximum_terminal_socket_receive_calls` | 1 | 9007199254740991 |
| 5 | `maximum_terminal_tls_records` | 1 | 9007199254740991 |
| 6 | `maximum_terminal_tls_unwrap_iterations` | 1 | 9007199254740991 |
| 7 | `maximum_terminal_zero_progress_iterations` | 1 | 9007199254740991 |
| 8 | `maximum_terminal_ingress_parser_units` | 1 | 4096 |
| 9 | `maximum_terminal_ingress_automatic_outputs` | 1 | 4096 |
| 10 | `maximum_websocket_send_attempts` | 1 | 1048832 |
| 11 | `maximum_tls_control_send_attempts` | 1 | 256 |
| 12 | `maximum_peer_shutdown_polls` | 2 | 2 |

`local_shutdown_operational_result_relations` is exactly this fifteen-string
array:

```text
1 result.terminal_outcome=spec.expected_terminal_outcome
2 result.final_terminal_ingress_batch_count<=spec.maximum_terminal_ingress_batches
3 result.final_terminal_ingress_ciphertext_octets<=spec.maximum_terminal_ingress_ciphertext_octets
4 result.final_terminal_ingress_plaintext_octets<=spec.maximum_terminal_ingress_plaintext_octets
5 result.final_terminal_socket_receive_call_count<=spec.maximum_terminal_socket_receive_calls
6 result.final_terminal_tls_record_count<=spec.maximum_terminal_tls_records
7 result.final_terminal_tls_unwrap_iteration_count<=spec.maximum_terminal_tls_unwrap_iterations
8 result.final_terminal_zero_progress_iteration_count<=spec.maximum_terminal_zero_progress_iterations
9 result.final_terminal_ingress_parser_unit_count<=spec.maximum_terminal_ingress_parser_units
10 result.final_terminal_ingress_automatic_output_count<=spec.maximum_terminal_ingress_automatic_outputs
11 result.final_websocket_send_attempt_count<=spec.maximum_websocket_send_attempts
12 result.final_tls_control_send_attempt_count<=spec.maximum_tls_control_send_attempts
13 result.final_peer_shutdown_poll_count<=spec.maximum_peer_shutdown_polls
14 len(result.ordered_terminal_ingress_read_attempt_event_ids)<=spec.maximum_terminal_ingress_batches
15 len(result.ordered_terminal_parser_transition_event_ids)<=spec.maximum_terminal_ingress_parser_units
```

The leading numbers above again denote one-based array positions and are not
part of the string values. These three arrays separate intrinsic signed-spec
admissibility, scalar domains, and operational result/spec comparisons; no
relation may be moved between them.

## 3. External schema registry V2 root, domain, and identity

`Step2ExternalSchemaRegistryV2` is a standalone record with:

```text
record_domain =
  RiskYieldMMA2MStep2ExternalSchemaRegistryV2V4_9F_RawV8
identity field = external_schema_registry_id
codec_byte_bound_relation = LT
codec_octet_limit = 16,777,216
```

Its complete logical identity-payload order is:

```text
external_schema_profile
unicode_source_catalog
identifier_profile_catalog
ascii_dfa_catalog
text_language_catalog
value_schema_catalog
external_type_descriptor_count
ordered_external_type_descriptors
cross_field_rule_descriptor_count
ordered_cross_field_rule_descriptors
fixed_position_resolver_profile_catalog
rule_application_descriptor_count
ordered_rule_application_descriptors
schema_graph_node_count
ordered_schema_graph_node_names
```

Required scalar values are:

```text
external_schema_profile =
  riskyieldmm_raw_v8_step2_external_schema_v2
external_type_descriptor_count = 52
cross_field_rule_descriptor_count = 42
rule_application_descriptor_count = 8
schema_graph_node_count = 52
```

`ordered_external_type_descriptors` is sorted by `type_name` as Unicode scalar
values, not by descriptor ID and not by locale. Its names exactly equal
`ordered_schema_graph_node_names`. Rule applications are sorted by their
unique `application_name`; the other catalogs are sorted by their respective
semantic IDs. Counts equal materialized array lengths.

The registry ID is:

```text
sha256(canonical_json_bytes({
  "canonicalization_version": "riskyieldmm_canonical_json_v1",
  "domain":
    "RiskYieldMMA2MStep2ExternalSchemaRegistryV2V4_9F_RawV8",
  "payload": <the exact ordered identity payload above>,
  "schema_version":
    "riskyieldmm_physical_transport_a2m_raw_v49f_v8"
}))
```

The logical standalone member positions are:

```text
canonicalization_version
measurement_schema_version
record_domain
<the exact identity-payload order above>
external_schema_registry_id
```

Unknown, missing, duplicate, noncanonical, or null root members reject. A raw
input whose object keys are not already in canonical lexicographic order
rejects on byte inequality after canonical reserialization. The byte limit is
exclusive: a 16,777,216-byte record rejects.

## 4. Metadata records

All metadata records below are exact JSON objects. Every listed member is
required, including members whose value may be null. Missing is never a
synonym for null.

### 4.1 `ExternalTypeDescriptorV2`

This is a nested registry record with members in this exact order:

```text
type_name
type_version_tag
type_role
type_form
described_record_domain
identity_field
identity_payload_member_order
codec_byte_bound_relation
codec_octet_limit
record_member_descriptors
tagged_union_descriptor
ordered_intrinsic_rule_ids
external_type_descriptor_id
```

Meanings and constraints:

```text
type_role = NESTED | STANDALONE
type_form = RECORD | TAGGED_UNION
codec_byte_bound_relation = LE | LT
codec_octet_limit = safe uint >= 1
```

For every descriptor:

```text
type_version_tag =
  "RAW_V8_STEP2_EXTERNAL_SCHEMA_V2/" + type_name
```

Both operands are exact ASCII and the resulting tag is at most 128 octets.
This is a schema-graph version tag, not an operation `spec_type` or
`result_type` discriminator. No per-type guessed alias is permitted.

- `STANDALONE` requires `type_form = RECORD` and non-null
  `described_record_domain`,
  `identity_field`, and `identity_payload_member_order`.
- `NESTED` requires those three members to be null.
- `RECORD` requires a non-null, nonempty
  `record_member_descriptors` array and null
  `tagged_union_descriptor`.
- `TAGGED_UNION` requires `type_role = NESTED`, null
  `record_member_descriptors`, and a non-null tagged-union descriptor.
- `codec_byte_bound_relation` and `codec_octet_limit` describe the parser/codec
  admission ceiling. They do not claim that any legal value reaches that
  ceiling and are not the certified analytic maximum.
- A standalone object's logical member list starts with
  `canonicalization_version`, `measurement_schema_version`, and
  `record_domain`, ends with the exact `identity_field`, and contains every
  identity-payload member between them in exactly
  `identity_payload_member_order`. Other middle members are permitted only
  when explicitly listed with role `ENVELOPE_NON_IDENTITY`; they never enter
  the semantic-ID preimage.
- A nested object's logical member list equals its complete schema payload
  order.
- A `TAGGED_UNION` has no independently serialized envelope and no independent
  runtime record. Its descriptor carries an `LE` graph-evaluation work cap:
  3,145,728 for either operation-body union and 3,072 for the target-value
  union. A selected concrete alternative's tighter relation/bound remains
  authoritative; the union work cap never relaxes it.

`external_type_descriptor_id` is SHA-256 over the exact preceding descriptor
members under:

```text
domain =
  RiskYieldMMA2MStep2ExternalTypeDescriptorV2V4_9F_RawV8
```

It is not the V1 descriptor ID and cannot preserve a V1 ID.

### 4.2 `MemberDescriptorV2`

The exact order is:

```text
member_position
member_name
member_role
value_schema_id
```

`member_position` is a positive safe uint. Positions start at one and are
contiguous. `member_role` is exactly one of:

```text
ENVELOPE_PREFIX
IDENTITY_PAYLOAD
ENVELOPE_NON_IDENTITY
IDENTITY_FIELD
NESTED_PAYLOAD
```

All members are present at runtime. Nullability belongs only to the referenced
`ValueSchemaV2`; it is not a member-presence flag.

For a standalone record, positions 1..3 are respectively
`canonicalization_version`, `measurement_schema_version`, `record_domain`
with role `ENVELOPE_PREFIX`; the final position has role `IDENTITY_FIELD`.
Every middle member is explicitly either `IDENTITY_PAYLOAD` or
`ENVELOPE_NON_IDENTITY`. `identity_payload_member_order` exactly equals the
subsequence of middle member names whose role is `IDENTITY_PAYLOAD`; an
envelope-only member is serialized and validated but excluded from the
semantic-ID preimage. For a nested record every member has role
`NESTED_PAYLOAD`. Union participation is expressed separately by the typed
scope/path records in Section 4.5, so a standalone identity-payload member
never loses its identity role merely because it also participates in union
dispatch.

### 4.3 `ValueSchemaV2`

`ValueSchemaV2` is a normalized graph node. Inline recursive schemas are
forbidden. Its exact order is:

```text
schema_kind
nullable
boolean_literal
integer_minimum
integer_maximum
text_language_id
array_minimum_items
array_maximum_items
array_item_value_schema_id
referenced_type_name
value_schema_id
```

`schema_kind` is:

```text
EXACT_BOOLEAN
SAFE_INTEGER
TEXT
ARRAY
OBJECT_REF
```

The exact shape table is:

| `schema_kind` | non-null constraint members | all other constraint members |
|---|---|---|
| `EXACT_BOOLEAN` | `boolean_literal` may be `true`, `false`, or null for either exact Boolean | null |
| `SAFE_INTEGER` | `integer_minimum`, `integer_maximum` | null |
| `TEXT` | `text_language_id` | null |
| `ARRAY` | `array_minimum_items`, `array_maximum_items`, `array_item_value_schema_id` | null |
| `OBJECT_REF` | `referenced_type_name` | null |

For `SAFE_INTEGER`, both bounds are safe integers and minimum is no greater
than maximum. For `ARRAY`, both bounds are safe uints, minimum is no greater
than maximum, and the item schema exists. An array of objects references an
`OBJECT_REF` value schema as its item schema; an array of nullable integers
references a nullable `SAFE_INTEGER` schema. No array may omit its item schema.

`nullable = true` admits JSON null in addition to the one non-null language
described by the row. It does not make an object member optional, does not
make array items nullable unless the item schema says so, and does not permit
null as a tagged-union selector.

For one typed member path, its value schema carries the strongest restriction
that can be decided from that member value alone: exact nullability, unary
literal or enum subset, scalar grammar/range, item schema, and the actual
accepted array cardinality. A restriction that reads a sibling member,
compares records, validates catalog contents or order, recomputes identity, or
depends on lifecycle/context belongs in a typed rule. Thus an exact root
catalog cardinality may be an array bound while equality to every frozen
catalog item remains a rule. This placement rule is normative and prevents
equivalent constraints from drifting between schema IDs and opaque prose.

The 421 concrete-record member paths project to exactly 200 distinct
strongest-unary member value schemas:

```text
EXACT_BOOLEAN  2
SAFE_INTEGER  29
TEXT          109
ARRAY          37
OBJECT_REF     23
```

This 200-schema projection is not the complete registry
`value_schema_catalog`. Rules and resolver-induced bindings also require
schemas that no serialized member uses directly—for example missing concrete
self `OBJECT_REF` schemas, fixed record sequences, an optional selector
object, ordinals, projected arrays, and rule-only literal/result schemas.
Those rule-derived schemas are materialized by the rule component. The final
registry catalog is the semantic-ID-deduplicated set union of the exact 200
member schemas and the exact reachable rule-derived schemas, sorted by
`value_schema_id`. A rule-derived schema already present in the member set is
reused and must not appear in the additive set; every additive schema must be
reachable from at least one typed rule or resolver-induced binding.

`value_schema_id` is the SHA-256 semantic ID of the exact ten preceding
members, under:

```text
domain = RiskYieldMMA2MStep2ValueSchemaV2V4_9F_RawV8
```

### 4.4 `TextLanguageDescriptorV2`

Every `TEXT` value schema resolves one exact language descriptor; no implicit
text default exists. Its logical order is:

```text
language_kind
ordered_literals
built_in_language_kind
ascii_dfa_id
minimum_utf8_octets
maximum_utf8_octets
minimum_decoded_octets
maximum_decoded_octets
decimal_maximum
unicode_identifier_profile_id
ordering_semantics
text_language_id
```

`language_kind` and its exact non-null form are:

| kind | required form |
|---|---|
| `LITERAL` | `ordered_literals` has exactly one item |
| `ENUM` | `ordered_literals` has at least two unique items in strict Unicode scalar-value lexicographic order |
| `BUILTIN` | non-null `built_in_language_kind` plus its exact parameters |
| `ASCII_DFA` | non-null `ascii_dfa_id`; all numeric members null |
| `UNICODE_IDENTIFIER` | non-null `unicode_identifier_profile_id`; numeric/ASCII/Base64 members null |

Every unused member is null. All numeric minima/maxima are nonnegative safe
integers with minimum no greater than maximum. The closed built-in vocabulary
is:

```text
LOWERCASE_SHA256
CANONICAL_BASE64
RFC3339_UTC
UINT128_DECIMAL
RAW_CANONICAL_JSON_STRING
```

The lexicographic `ENUM` order is registry canonicalization, not a claim that
the accepted values possess that business ordering. Operation sequences,
marker DFAs, tagged-union alternatives, and other semantic orders remain
separate explicitly ordered descriptors or rules.

`ordering_semantics` is always present and is exactly `NONE` or
`UNICODE_SCALAR_LEXICOGRAPHIC`. A language receives
`UNICODE_SCALAR_LEXICOGRAPHIC` only when a reviewed rule compares or
strictly orders values in that language. All other languages, including
`RFC3339_UTC`, use `NONE`; applying a relational or ordering operator to them
rejects at rule type-check time. This prevents the canonical 20-octet
whole-second timestamp form and 27-octet fractional form from being mistaken
for chronological lexical order.

`CANONICAL_BASE64` requires UTF-8 and decoded minima/maxima, the RFC 4648
standard alphabet, exact padding, and decode/re-encode byte equality.
`UINT128_DECIMAL` requires a non-null decimal maximum. Other built-ins require
those parameters null unless their exact catalog row says otherwise.

Persisted `RFC3339_UTC` accepts exactly either:

```text
YYYY-MM-DDTHH:MM:SSZ
YYYY-MM-DDTHH:MM:SS.ffffffZ
```

The first form is exactly 20 ASCII octets. The second is exactly 27 ASCII
octets and its six-digit fractional value is not `000000`. Year is
`0001..9999`; month/day follow the proleptic Gregorian calendar; hour is
`00..23`; minute and second are `00..59`; leap seconds, offsets, lowercase
`t`/`z`, spaces, and other fractional widths reject. Constructors may accept
offset timestamps or 1..5 fractional digits only by normalizing them before
record construction. Raw persisted input must already equal one of the two
canonical forms and rejects when decode/re-encode bytes differ.

`RAW_CANONICAL_JSON_STRING` means any exact JSON string that encodes strictly
as UTF-8 and contains no lone surrogate. It imposes no NFC, trimming, ASCII,
C0/DEL, nonempty, scalar-count, or per-item byte constraint; the enclosing
record's codec bound remains authoritative. The name deliberately does not
claim full RFC 7493 noncharacter enforcement that the current RiskYield
canonical validator does not provide.

For `ASCII_DFA`, length bounds exist only on the referenced
`AsciiDfaDescriptorV2`. The enclosing text-language descriptor's UTF-8 and
decoded-octet bounds are null; duplicating or overriding the DFA bounds
rejects.

No regex string is executable. A non-built-in ASCII language resolves an
`AsciiDfaDescriptorV2` with exact logical fields:

```text
state_count
start_state
ordered_accepting_states
ordered_transition_rows
minimum_octets
maximum_octets
ascii_dfa_id
```

Each transition row is exactly
`source_state, inclusive_byte_minimum, inclusive_byte_maximum, target_state`.
States are safe uints in `0..state_count-1`; rows are sorted by source/minimum;
byte ranges are in `0x00..0x7f`, nonoverlapping per source, and deterministic.
Absent transitions reject. Every state is reachable from the start and can
reach an accepting state. `ascii_dfa_id` is the semantic SHA-256 of the other
fields under
`RiskYieldMMA2MStep2AsciiDfaDescriptorV2V4_9F_RawV8`.

Idempotency key, request ID, field ID, exception class, errno name,
availability bitmap, and every generic length-bounded ASCII language are
materialized as complete DFA rows. Their grammar cannot be represented by an
opaque built-in name or prose. The independent verifier generates exhaustive
accepted/rejected boundary strings from each DFA and differentially checks
the production validator.

`LITERAL` is not `ENUM`, even when an implementation could model a singleton
enum. Lowercase SHA-256, field ID, request ID, idempotency key, errno name,
exception class, timestamp, bitmap, canonical Base64, and uint128 decimal
therefore have distinct language identities. Each descriptor's terminal ID
is the semantic SHA-256 of the exact preceding fields under:

```text
domain = RiskYieldMMA2MStep2TextLanguageDescriptorV2V4_9F_RawV8
```

The complete DFA/text catalogs and every
`ValueSchemaV2 -> text_language_id -> ascii_dfa_id` edge are part of the
external registry identity.

### 4.5 finite tagged unions

`TaggedUnionDescriptorV2` has exact order:

```text
payload_binding_scope
payload_owner_type_name
payload_typed_member_path
ordered_discriminator_descriptors
ordered_alternatives
```

`payload_binding_scope` is `OWNER_MEMBER` or `SELF_VALUE`.

- `OWNER_MEMBER` requires a concrete `payload_owner_type_name` and a nonempty
  `payload_typed_member_path` that resolves to this union.
- `SELF_VALUE` requires null owner and an empty payload path.

`TaggedUnionDiscriminatorDescriptorV2` has exact logical order:

```text
discriminator_position
discriminator_scope
discriminator_owner_type_name
discriminator_typed_member_path
text_language_id
```

`discriminator_scope` is `OWNER_OBJECT` or `SELECTED_VALUE`.

- `OWNER_OBJECT` resolves its nonempty path from the exact concrete owner type
  and requires that owner to equal `payload_owner_type_name`.
- `SELECTED_VALUE` requires null owner and resolves its nonempty path within
  each selected alternative.

Discriminator positions start at one and are contiguous. The referenced text
language is a closed literal/enum language whose value is used by every
alternative binding; no generic text schema is permitted.

`TaggedUnionAlternativeDescriptorV2` has exact order:

```text
alternative_position
alternative_name
ordered_discriminator_literals
referenced_type_name
```

Each discriminator literal has exact logical order:

```text
member_name
text_value
```

For discriminator position `i`, each alternative's literal at position `i`
has `member_name` exactly equal to the terminal member name of that
discriminator descriptor's `discriminator_typed_member_path`. Literal tuple
order equals discriminator-position order. A renamed, reordered, duplicated,
or path-inconsistent `member_name` rejects even when the text values would
otherwise select the same alternative.

Alternative positions start at one and are contiguous. Alternative names and
complete literal tuples are unique. Each alternative references exactly one
concrete `RECORD` type. Dispatch is performed only after exact-key and
exact-text validation. There is no first-match, default, fallback, open
union, subclass, or structural duck-typing behavior.

The exact binding metadata for the three unions is:

| union | payload binding | discriminator bindings |
|---|---|---|
| `CapacityMeasurementOperationSpecBody` | `OWNER_MEMBER`, owner `CapacityMeasurementOperationSpec`, path `["spec"]` | owner paths `["operation_kind"]`, `["spec_type"]` |
| `CapacityMeasurementOperationResultBody` | `OWNER_MEMBER`, owner `CapacityMeasurementOperationResultEvidence`, path `["result"]` | owner paths `["operation_kind"]`, `["result_type"]` |
| `CapacityMeasurementTargetValue` | `SELF_VALUE`, null owner, path `[]` | selected-value path `["kind"]` |

An implementation that stores only discriminator member names, without scope,
owner, and typed path, is V1-lossy and rejects.

## 5. Exact graph inventory

Notation used below:

```text
S[middle members ; identity-payload subsequence ; identity]
  logical member positions =
    canonicalization_version,
    measurement_schema_version,
    record_domain,
    middle members in listed order,
    identity
  identity_payload_member_order = the listed subsequence

  Unless a row states an ENVELOPE_NON_IDENTITY exception, the identity-payload
  subsequence equals all middle members.

N[members]
  logical member positions = exactly the listed members
  identity_payload_member_order = null
```

Every object member gets one explicit `MemberDescriptorV2` and one explicit
`value_schema_id`. Implementations may not infer a value schema from the
member's spelling. `LE n` means canonical byte length `<= n`; `LT n` means
canonical byte length `< n`. These annotations are codec admission bounds;
the separately certified analytic maxima are produced under Section 11.

The 16 standalone `described_record_domain` values are exact:

| type | described record domain |
|---|---|
| `CapacityMeasurementDispatchWindowEvidenceV1` | `RiskYieldMMA2MDispatchWindowEvidenceV4_9F_RawV8` |
| `CapacityMeasurementDueDecisionClockEvidenceV1` | `RiskYieldMMA2MDueDecisionClockEvidenceV4_9F_RawV8` |
| `CapacityMeasurementIngressLogicalOracleProfileV1` | `RiskYieldMMA2MIngressLogicalOracleProfileV1V4_9F_RawV8` |
| `CapacityMeasurementOperationDeclarationV1` | `RiskYieldMMA2MOperationDeclarationV4_9F_RawV8` |
| `CapacityMeasurementOperationSpec` | `RiskYieldMMA2MOperationSpecV4_9F_RawV8` |
| `CapacityMeasurementOperationResultEvidence` | `RiskYieldMMA2MOperationResultEvidenceV4_9F_RawV8` |
| `CheckpointSelectorEntryV1` | `RiskYieldMMA2MCheckpointSelectorEntryV1V4_9F_RawV8` |
| `CheckpointSelectorV1` | `RiskYieldMMA2MCheckpointSelectorV1V4_9F_RawV8` |
| `MarkerContractV1` | `RiskYieldMMA2MMarkerContractV1V4_9F_RawV8` |
| `TargetObservationContextV2` | `RiskYieldMMA2MTargetObservationContextV2V4_9F_RawV8` |
| `TargetFieldObservationV1` | `RiskYieldMMA2MTargetFieldObservationV4_9F_RawV8` |
| `TargetObservationV2` | `RiskYieldMMA2MTargetObservationV2V4_9F_RawV8` |
| `TargetObservationRootV2` | `RiskYieldMMA2MTargetObservationRootV2V4_9F_RawV8` |
| `TargetFieldRegistryV1` | `RiskYieldMMA2MTargetFieldRegistryV4_9F_RawV8` |
| `OperationCounterSnapshotSchemaV1` | `RiskYieldMMA2MOperationCounterSnapshotSchemaV4_9F_RawV8` |
| `SourceErrorDetailV1` | `RiskYieldMMA2MSourceErrorDetailV4_9F_RawV8` |

All other 36 descriptors have `type_role = NESTED` and null
`described_record_domain`/`identity_field`/identity-payload order.

### 5.1 The prior 27 concrete records

1. `CapacityMeasurementAckDeadlineExpirySpecV1`, `N`, `LE 3,145,728`:
   `workload_family, expected_outbound_subscription_intent_id, due_scenario,
   expected_terminal_cause_code`.
2. `CapacityMeasurementAckDeadlineExpiryResultEvidenceV1`, `N`,
   `LE 3,145,728`: `expired, due_decision_clock_evidence,
   due_decision_clock_evidence_id, ack_deadline_expired_event_id,
   terminal_transition_event_id, transport_session_termination_id`.
3. `CapacityMeasurementDispatchWindowEvidenceV1`, `S`, `LE 524,288`:
   `transport_session_id, outbound_subscription_intent_id, socket_lease_id,
   monotonic_clock_domain_id, dispatch_started_at, dispatch_completed_at,
   dispatch_started_monotonic_ns, dispatch_completed_monotonic_ns ;
   dispatch_window_evidence_id`.
4. `CapacityMeasurementDueDecisionClockEvidenceV1`, `S`, `LE 524,288`:
   `transport_session_id, outbound_subscription_intent_id,
   dispatch_window_evidence, dispatch_window_evidence_id,
   clock_source_manifest_id, monotonic_clock_domain_id, wall_before_at,
   sampled_at, wall_after_at, monotonic_before_ns, monotonic_sampled_ns,
   monotonic_after_ns, uncertainty_milliseconds, synchronized, valid_until,
   clock_resolution_ns, source_observation_sha256, selectable_source_count,
   chronyd_launch_id, chronyd_runtime_observation_sha256,
   committed_ack_deadline_at, committed_ack_deadline_monotonic_ns,
   due_scenario ; due_decision_clock_evidence_id`.
5. `CapacityMeasurementIngressLogicalOracleProfileV1`, `S`, `LE 8,192`:
   `profile_version, oracle_kind, input_chunk_semantics,
   requires_empty_fragmentation_baseline,
   requires_empty_complete_unit_baseline, maximum_input_chunks,
   maximum_input_octets, maximum_parser_units,
   maximum_completed_application_messages, maximum_logical_output_frames,
   maximum_logical_output_payload_octets, logical_output_frame_domain,
   raw_ingress_batch_domain, streamed_digest_algorithm,
   parser_oracle_descriptor_requirement ; logical_oracle_profile_id`.
6. `CapacityMeasurementIngressOperationSpecV2`, `N`, `LE 3,145,728`:
   `workload_family, ordered_input_chunks_base64, input_chunk_count,
   input_octet_count, input_sha256, raw_ingress_batch_sha256,
   timeout_seconds, logical_oracle_profile_id, expected_parser_unit_count,
   expected_completed_application_message_count,
   expected_logical_output_frame_count,
   expected_logical_output_payload_octets,
   expected_logical_output_frames_sha256`.
7. `CapacityMeasurementIngressResultEvidenceV2`, `N`, `LE 3,145,728`:
   `ingress_progress_evidence_id, final_parser_cursor_id,
   final_retained_tail_id, final_retained_tail_octets,
   final_retained_tail_sha256, sealed_pending_input_id,
   ingress_oracle_baseline_id, observed_consumed_new_input_octets,
   observed_parser_unit_count, observed_completed_application_message_count,
   observed_logical_output_frame_count,
   observed_logical_output_payload_octets,
   observed_logical_output_frames_sha256`.
8. `CapacityMeasurementLocalShutdownSpecV2`, `N`, `LE 3,145,728`:
   `workload_family, timeout_seconds, expected_terminal_outcome,
   expected_local_close_code, expected_local_close_reason_sha256,
   maximum_terminal_ingress_batches,
   maximum_terminal_ingress_ciphertext_octets,
   maximum_terminal_ingress_plaintext_octets,
   maximum_terminal_socket_receive_calls, maximum_terminal_tls_records,
   maximum_terminal_tls_unwrap_iterations,
   maximum_terminal_zero_progress_iterations,
   maximum_terminal_ingress_parser_units,
   maximum_terminal_ingress_automatic_outputs,
   maximum_websocket_send_attempts, maximum_tls_control_send_attempts,
   maximum_peer_shutdown_polls`.
9. `CapacityMeasurementLocalShutdownResultEvidenceV2`, `N`,
   `LE 3,145,728`: `local_shutdown_started_event_id,
   local_shutdown_deadline_evidence_event_id,
   local_close_dispatch_completion_event_id,
   ordered_terminal_ingress_read_attempt_event_ids,
   ordered_terminal_ingress_read_result_event_ids,
   ordered_terminal_raw_ingress_commit_ids,
   ordered_terminal_raw_ingress_actor_event_ids,
   ordered_terminal_parser_transition_event_ids,
   websocket_close_received_transition_event_id, shutdown_trace_step_count,
   shutdown_trace_root_sha256, final_terminal_ingress_batch_count,
   final_terminal_ingress_ciphertext_octets,
   final_terminal_ingress_plaintext_octets,
   final_terminal_socket_receive_call_count,
   final_terminal_tls_record_count,
   final_terminal_tls_unwrap_iteration_count,
   final_terminal_zero_progress_iteration_count,
   final_terminal_ingress_parser_unit_count,
   final_terminal_ingress_automatic_output_count,
   final_websocket_send_attempt_count,
   final_tls_control_send_attempt_count, final_peer_shutdown_poll_count,
   final_terminal_tls_staging_state_id,
   decisive_terminal_transition_event_id,
   transport_session_termination_id, terminal_outcome`.
10. `CapacityMeasurementLogicalOutputFrameV1`, `N`, `LE 3,145,728`:
    `opcode, payload_base64`.
11. `CapacityMeasurementOperationDeclarationV1`, `S`, `LE 3,145,728`:
    `campaign_manifest_id, manifest_authority_id, measurement_design_id,
    workload_plan_id, workload_id, workload_sha256, sample_sequence,
    operation_sequence, trial_index, repetition_index, is_warmup, stage,
    timeout_policy_id, operation_kind, operation_spec, operation_spec_id ;
    declaration_id`.
12. `CapacityMeasurementOperationSpec`, `S`, `LE 2,097,152`:
    `operation_kind, spec_type, spec ; operation_spec_id`. `spec` references
    `CapacityMeasurementOperationSpecBody`.
13. `CapacityMeasurementOperationResultEvidence`, `S`, `LT 524,288`:
    `candidate_id, attempt_id, operation_kind, result_type, result ;
    result_evidence_id`. `result` references
    `CapacityMeasurementOperationResultBody`.
14. `CapacityMeasurementSubscriptionDispatchSpecV2`, `N`,
    `LE 3,145,728`: `workload_family, idempotency_key,
    transport_subscription_policy_id, adapter_policy_id, expected_topic,
    expected_operation, expected_logical_opcode,
    expected_dispatch_disposition`.
15. `CapacityMeasurementSubscriptionDispatchResultEvidenceV2`, `N`,
    `LE 3,145,728`: `outbound_subscription_intent_id, generated_request_id,
    generated_request_command_sha256, generated_logical_opcode,
    generated_logical_payload_sha256, generated_logical_payload_octets,
    dispatch_window_evidence, dispatch_window_evidence_id,
    outbound_wire_prepared_event_id, tls_ciphertext_prepared_event_id,
    ordered_kernel_attempt_event_ids, ordered_kernel_result_event_ids,
    outbound_dispatch_completed_event_id, submitted_ciphertext_octets,
    local_dispatch_disposition`.
16. `CheckpointSelectorEntryV1`, `S`, `LE 2,048`: `selector_position,
    operation_kind, checkpoint_marker_kind, occurrence_index_within_kind ;
    checkpoint_selector_entry_id`.
17. `CheckpointSelectorV1`, `S`, `LE 262,144`: logical middle members
    `operation_kind, ordered_entries, selector_length,
    ordered_checkpoint_selector_entry_ids`; identity-payload subsequence
    `operation_kind, selector_length, ordered_checkpoint_selector_entry_ids`;
    identity `checkpoint_selector_id`. `ordered_entries` has role
    `ENVELOPE_NON_IDENTITY`; this preserves the production selector-ID
    behavior while the complete entries remain strictly validated.
18. `MarkerContractV1`, `S`, `LE 32,768`: `contract_version,
    ordered_marker_kinds, ordered_full_checkpoint_marker_kinds,
    ordered_checkpoint_operation_records,
    forbidden_full_checkpoint_marker_kinds, minimum_marker_ring_capacity,
    maximum_marker_ring_capacity, maximum_checkpoint_selector_length,
    stable_checkpoint_requires_attempt ; marker_contract_id`.
19. `TargetObservationClockSpanV2`, `N`, `LE 512`: `clock_domain,
    span_status, started_offset_nanoseconds, completed_offset_nanoseconds,
    unavailable_reason`.
20. `TargetObservationContextV2`, `S`, `LE 2,048`:
    `observation_role, operation_kind, instrumentation_mode, candidate_id,
    attempt_id, target_field_registry_id, marker_ordinal,
    checkpoint_marker_kind, full_checkpoint_selector_id,
    checkpoint_selector_position, checkpoint_selector_entry_id,
    expected_checkpoint_marker_kind,
    expected_occurrence_index_within_kind, checkpoint_binding_status,
    checkpoint_binding_unavailable_reason, observer_clock_span,
    boottime_clock_span, loop_clock_span ; observation_context_id`.
21. `TargetFieldObservationV1`, `S`, `LE 4,096`:
    `target_field_registry_id, observation_context_id, field_id,
    availability, value, observation_method, observation_attempt,
    adapter_span_status, observation_started_offset_nanoseconds,
    observation_completed_offset_nanoseconds, unavailable_reason, censoring,
    source_errno_number, source_errno_name, source_failure_phase,
    source_error_class, source_error_detail_sha256 ; field_observation_id`.
    `value` is nullable and its non-null schema references
    `CapacityMeasurementTargetValue`.
22. `TargetObservationV2`, `S`, `LT 262,144`: `observation_context,
    observation_context_id, field_observations ; observation_id`.
23. `TargetObservationRootV2`, `S`, `LE 8,192`: `candidate_id, attempt_id,
    operation_kind, instrumentation_mode, target_field_registry_id,
    full_checkpoint_selector_id, observation_count,
    ordered_observation_ids ; target_observation_root_sha256`.
24. `TargetFieldRegistryV1`, `S`, `LE 2,097,152`:
    `target_registry_profile, status_reason_policy_definition,
    ordered_vocabulary_definitions, ordered_value_shape_definitions,
    ordered_value_constraint_definitions,
    ordered_cross_field_constraint_definitions, field_count, descriptors ;
    target_field_registry_id`.
25. `OperationCounterSnapshotSchemaV1`, `S`, `LE 8,192`:
    `counter_field_count, ordered_counter_field_ids,
    monotone_counter_field_ids ; counter_schema_id`.
26. `OperationCounterSnapshotV1`, `N`, `LE 2,048`:
    `counter_schema_id, availability_bitmap, values`. `values` has exactly 66
    nullable safe-uint items; nullability is on the item schema.
27. `SourceErrorDetailV1`, `S`, `LE 2,048`: `field_id,
    observation_method, source_failure_phase, source_errno_number,
    source_errno_name, source_error_class ; source_error_detail_sha256`.

### 5.2 The 22 omitted concrete records

28. `CapacityMeasurementObservationMethodRolePairV1`, `N`,
    `LE 3,145,728`: `observation_method, allowed_roles`.
29. `CapacityMeasurementVocabularyDefinitionV1`, `N`, `LE 3,145,728`:
    `vocabulary_id, members`.
30. `CapacityMeasurementValueShapeDefinitionV1`, `N`, `LE 3,145,728`:
    `value_shape_id, container_kind, minimum_items, maximum_items,
    ordered_keys`.
31. `CapacityMeasurementValueConstraintDefinitionV1`, `N`,
    `LE 3,145,728`: `value_constraint_id, value_kind, scalar_profile,
    vocabulary_id, integer_minimum, integer_maximum,
    text_minimum_utf8_bytes, text_maximum_utf8_bytes, text_ascii_pattern,
    decimal_maximum, collection_item_constraint_id,
    external_authority_profile`.
32. `CapacityMeasurementAvailabilityStateRuleV1`, `N`, `LE 3,145,728`:
    `availability, value_policy, reason_policy, censoring_policy,
    attempt_policy, adapter_span_policy`.
33. `CapacityMeasurementAttemptStateErrorFormsV1`, `N`,
    `LE 3,145,728`: `attempt_state, permitted_error_forms,
    permitted_failure_phases, adapter_span_policy`.
34. `CapacityMeasurementStatusReasonRuleV1`, `N`, `LE 3,145,728`:
    `reason, required_availability, context_predicate,
    attempt_state_error_forms`.
35. `CapacityMeasurementErrorFormDefinitionV1`, `N`, `LE 3,145,728`:
    `error_form, errno_pair_policy, error_class_policy, error_digest_policy,
    class_digest_pair_policy`.
36. `CapacityMeasurementStatusReasonPolicyDefinitionV1`, `N`,
    `LE 3,145,728`: `status_reason_policy_id, availability_state_rules,
    reason_rules, error_form_definitions`.
37. `CapacityMeasurementCrossFieldConstraintDefinitionV1`, `N`,
    `LE 3,145,728`: `cross_field_constraint_id, count_field_id,
    sequence_field_id, kind_field_id, activation_condition, maximum_items,
    sequence_order, cardinality_rule, pairing_rule`.
38. `CapacityMeasurementTargetFieldDescriptorV1`, `N`, `LE 3,145,728`:
    `field_id, layer, value_kind, unit, value_constraint_id,
    observation_method_role_pairs, allowed_checkpoint_marker_kinds,
    applicable_operation_kinds, allowed_status_reasons,
    status_reason_policy_id, censoring_allowed,
    later_threshold_action_if_unavailable, value_shape_id,
    value_shape_keys, cross_field_constraint_ids`.
39. `CapacityMeasurementCheckpointOperationRecordV1`, `N`,
    `LE 3,145,728`: `checkpoint_marker_kind,
    applicable_operation_kinds`.
40. `CapacityMeasurementUIntValueV1`, `N`, `LE 3,072`:
    `kind, value`.
41. `CapacityMeasurementBoolValueV1`, `N`, `LE 3,072`:
    `kind, value`.
42. `CapacityMeasurementTextValueV1`, `N`, `LE 3,072`:
    `kind, value`.
43. `CapacityMeasurementOptionalUIntValueV1`, `N`, `LE 3,072`:
    `kind, present, value`.
44. `CapacityMeasurementOptionalTextValueV1`, `N`, `LE 3,072`:
    `kind, present, value`.
45. `CapacityMeasurementUIntListValueV1`, `N`, `LE 3,072`:
    `kind, values`.
46. `CapacityMeasurementTextListValueV1`, `N`, `LE 3,072`:
    `kind, values`.
47. `CapacityMeasurementFixedUIntMapEntryV1`, `N`, `LE 3,145,728`:
    `key, value`.
48. `CapacityMeasurementFixedUIntMapValueV1`, `N`, `LE 3,072`:
    `kind, ordered`.
49. `CapacityMeasurementDurationBoundValueV1`, `N`, `LE 3,072`:
    `kind, relation, lower_nanoseconds, upper_nanoseconds`.

The 22 records above are not optional documentation detail. Omitting any one
breaks transitive closure from the prior 27 records.

The legacy concrete V1 records
`CapacityMeasurementClockSpanV1`,
`CapacityMeasurementTargetObservationContextV1`,
`CapacityMeasurementTargetObservationV1`, and
`CapacityMeasurementTargetObservationRootV1` are not in the V2 target-bound
graph. Accepting one of them in this registry is an extra-node failure.
Production also retains the private historical codec class
`_HistoricalCapacityMeasurementLocalShutdownResultEvidenceV1V49FV8`; it is
unreachable from the current result union and is not one of the 49 records.
The explicit production-adapter exclusion set contains this class plus the
four legacy observation classes. Reflection-based discovery without these
five reviewed exclusions is forbidden.

### 5.3 The three distinct union nodes

50. `CapacityMeasurementOperationSpecBody`,
    `NESTED/TAGGED_UNION`, has discriminators in exact order
    `(operation_kind, spec_type)` and alternatives:

    ```text
    (ACK_DEADLINE_EXPIRY, ACK_DEADLINE_EXPIRY_SPEC_V1)
      -> CapacityMeasurementAckDeadlineExpirySpecV1
    (INGRESS, INGRESS_OPERATION_SPEC_V2)
      -> CapacityMeasurementIngressOperationSpecV2
    (LOCAL_SHUTDOWN, LOCAL_SHUTDOWN_SPEC_V2)
      -> CapacityMeasurementLocalShutdownSpecV2
    (SUBSCRIPTION_DISPATCH, SUBSCRIPTION_DISPATCH_SPEC_V2)
      -> CapacityMeasurementSubscriptionDispatchSpecV2
    ```

    The discriminator values are taken from the wrapper; the `spec` member is
    decoded only as the selected alternative.

51. `CapacityMeasurementOperationResultBody`,
    `NESTED/TAGGED_UNION`, has discriminators in exact order
    `(operation_kind, result_type)` and alternatives:

    ```text
    (ACK_DEADLINE_EXPIRY, ACK_DEADLINE_EXPIRY_RESULT_EVIDENCE_V1)
      -> CapacityMeasurementAckDeadlineExpiryResultEvidenceV1
    (INGRESS, INGRESS_RESULT_EVIDENCE_V2)
      -> CapacityMeasurementIngressResultEvidenceV2
    (LOCAL_SHUTDOWN, LOCAL_SHUTDOWN_RESULT_EVIDENCE_V2)
      -> CapacityMeasurementLocalShutdownResultEvidenceV2
    (SUBSCRIPTION_DISPATCH, SUBSCRIPTION_DISPATCH_RESULT_EVIDENCE_V2)
      -> CapacityMeasurementSubscriptionDispatchResultEvidenceV2
    ```

52. `CapacityMeasurementTargetValue`,
    `NESTED/TAGGED_UNION`, has discriminator `(kind)` and
    alternatives:

    ```text
    BOOL           -> CapacityMeasurementBoolValueV1
    DURATION_BOUND -> CapacityMeasurementDurationBoundValueV1
    FIXED_UINT_MAP -> CapacityMeasurementFixedUIntMapValueV1
    OPTIONAL_TEXT  -> CapacityMeasurementOptionalTextValueV1
    OPTIONAL_UINT  -> CapacityMeasurementOptionalUIntValueV1
    TEXT           -> CapacityMeasurementTextValueV1
    TEXT_LIST      -> CapacityMeasurementTextListValueV1
    UINT           -> CapacityMeasurementUIntValueV1
    UINT_LIST      -> CapacityMeasurementUIntListValueV1
    ```

The exact role/form partition is:

```text
16 STANDALONE + 36 NESTED = 52
49 RECORD + 3 TAGGED_UNION = 52
```

The alternative order above is canonical lexical tag order. The concrete
fixed-map entry is referenced by the `ordered` array schema; it is not a tenth
target-value alternative.

## 6. Value-schema requirements that close the current losses

The 200-schema strongest-unary member projection must materialize distinct
schemas for:

- exact booleans, exact Boolean literals, safe integers with every distinct
  minimum/maximum pair, and nullable versions where used;
- each literal text value and each complete enum tuple;
- lowercase SHA-256, canonical Base64 with distinct encoded/decoded limits,
  RFC3339 UTC timestamps, uint128 decimal text, idempotency-key ASCII,
  request-ID ASCII, field-ID ASCII, exception-class ASCII, errno-name ASCII,
  bitmap text, and the three Unicode identifier profiles in Section 7;
- each array cardinality and item-schema combination;
- every concrete object reference and all three union references.

Here “every concrete object reference” means every concrete type reached
directly by a serialized member path. The full registry additionally
materializes a non-null `OBJECT_REF` schema for each exact concrete type used
as an intrinsic or cross-record `RECORD` binding, plus every other reachable
rule-derived schema described above. A concrete graph type with no such
binding or literal reference does not acquire an unreachable self schema
merely to make the catalog symmetrical. The complete typed-rule ledger
freezes the exact additive count and therefore the exact full-catalog count
before registry generation; leaving either count inferred at runtime is
NO-GO.

Literal and enum schemas are not interchangeable:

```text
literal("TEXT") != enum("TEXT", "PONG")
enum order is exact
```

The schema for `ordered_kernel_attempt_event_ids`, for example, is an array of
lowercase-SHA-256 strings with cardinality `1..256`. The schema for
`ordered_entries` is an array of object references to
`CheckpointSelectorEntryV1` with cardinality `0..64`;
`ordered_checkpoint_selector_entry_ids` is an array of hashes with
cardinality `0..64`; and `selector_length` is a safe uint `0..64` equal to
both lengths. The schema for counter snapshot `values` is an array of exactly
66 nullable safe uints. Any generic `ARRAY` entry without these item schemas
rejects.

The machine-readable acceptance report derives this path ledger directly from
the identity-committed `record_member_descriptors`:

```text
(type_name, alternative_name_or_null, member_position, member_name)
  -> value_schema_id
```

Its key set must exactly equal the independently enumerated member set from
all 49 concrete records. It is a validation view, not a second registry-root
member and not a duplicate source of truth. Name-based fallback, a default
text schema, or an unknown-member branch is forbidden.

Every serialized standalone `IDENTITY_FIELD` resolves to the non-null
lowercase-SHA-256 language. A constructor's temporary `None` default before
identity sealing is not part of the serialized schema and must not produce a
nullable identity-field schema.

Three validation layers are distinct:

```text
member codec schema
intrinsic record acceptance
effective frozen-root/cross-record acceptance
```

The member codec schema records the direct parser/constructor language and
cardinality. Intrinsic rules add relations within one complete record.
Rule applications add frozen-root, positional, catalog, or multi-record
requirements. An exact count required only by the accepted frozen registry
must not be copied into a more permissive record codec, while a direct codec
minimum must not be deferred to a root rule.

The same member codec schema governs direct construction, `from_mapping`, and
persisted-byte decode. A constructor that admits an over-cardinality tuple
which `from_mapping` rejects is a production-adapter defect, not a second
admission profile. In particular, the four raw-canonical-string arrays in
Section 6.1 must enforce their stated maxima before serialization on every
entry path.

`TargetFieldObservationV1.value` is structurally a nullable reference to
`CapacityMeasurementTargetValue`, but that union is not sufficient effective
validation. The observation/descriptor positional application must also bind
the complete `TargetFieldRegistryV1` and resolve the descriptor's exact
`value_constraint_id`, `value_shape_id`, optional vocabulary, and shape keys.
It must enforce all 17 frozen value-constraint families, including SHA-256,
uint128 decimal, platform errno, A1/SQLite enums, the loop-interval range,
list cardinality, and fixed-map key order. Missing or duplicate catalog
resolution, a generic-union-only check, or a constraint applied to the wrong
field rejects. The final rule ledger must express this with a reviewed,
closed, registry-bound operator and exact application bindings; until then
this effective-validation item remains NO-GO.

### 6.1 Exact scalar-language corrections

`RAW_CANONICAL_JSON_STRING` applies to exactly these array-item paths:

| path | array cardinality |
|---|---:|
| `CapacityMeasurementVocabularyDefinitionV1.members[]` | `1..512` |
| `CapacityMeasurementValueShapeDefinitionV1.ordered_keys[]` | `0..512` |
| `CapacityMeasurementTargetFieldDescriptorV1.value_shape_keys[]` | `0..512` |
| `CapacityMeasurementTargetFieldDescriptorV1.cross_field_constraint_ids[]` | `0..16` |

No other field receives that permissive language by fallback.

The generic printable-trim ASCII DFAs admit bytes `0x20..0x7e`, require the
first and last byte not to be `0x20`, and have these exact surfaces:

- length `1..128`: vocabulary ID, value-shape ID, value-constraint ID,
  status-policy ID, the eight text members of
  `CapacityMeasurementCrossFieldConstraintDefinitionV1`, target-descriptor
  `unit`, `value_constraint_id`, `status_reason_policy_id`, and
  `value_shape_id`, and fixed-uint-map-entry `key`;
- nullable length `1..256`: value-constraint `vocabulary_id`,
  `text_ascii_pattern`, `collection_item_constraint_id`, and
  `external_authority_profile`.

Dedicated DFA languages are exact:

```text
IDEMPOTENCY_KEY:
  [A-Za-z0-9][A-Za-z0-9._:-]{0,127}

REQUEST_ID:
  [A-Za-z0-9_-]{1,36}

FIELD_ID:
  [a-z][a-z0-9_]*\.[a-z0-9_]+
  total length 3..256

EXCEPTION_CLASS:
  [A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*
  total length 1..256

ERRNO_NAME:
  [A-Z][A-Z0-9_]{0,63}

AVAILABILITY_BITMAP:
  [01]{66}

LAYER:
  [A-Z][A-Z0-9_]{0,253}
```

These lines are grammar notation for this document; the registry materializes
the equivalent complete deterministic transition rows, never executable
regex. The `LAYER` scalar language is necessary but insufficient:
`TargetFieldDescriptorV1.layer` must also equal the ASCII uppercase of the
substring of `field_id` before its one dot. The final typed rule catalog must
materialize that exact relation through a narrowly defined
`FIELD_LAYER_EQUALS_UPPERCASE_FIELD_PREFIX` operator; a prose-only check is
NO-GO.

`CapacityMeasurementSubscriptionDispatchSpecV2.expected_dispatch_disposition`
uses the exact enum
`(COMPLETE_LOCAL_SUBMISSION, UNKNOWN_DELIVERY)`.
`CapacityMeasurementSubscriptionDispatchResultEvidenceV2.local_dispatch_disposition`
is the literal `COMPLETE_LOCAL_SUBMISSION`. Widening the result literal or
narrowing the signed spec enum rejects.

## 7. Unicode 15.0.0 authority and three identifier profiles

Unicode behavior is data, not an ambient Python/runtime property. The registry
contains exact `UnicodeSourceRecordV1` records with:

```text
source_name
unicode_version
official_url
byte_count
sha256
unicode_source_record_id
```

`unicode_source_record_id` is the semantic SHA-256 of the preceding five
logical members under
`RiskYieldMMA2MStep2UnicodeSourceRecordV1V4_9F_RawV8`.

The frozen source catalog is:

| source | official URL | bytes | SHA-256 |
|---|---|---:|---|
| `ReadMe.txt` | https://www.unicode.org/Public/15.0.0/ucd/ReadMe.txt | 635 | `53672c0d0b5185e3cf04c8e970d544c3af81ae7c8eeba0b9cf6d355aa954ae1f` |
| `UnicodeData.txt` | https://www.unicode.org/Public/15.0.0/ucd/UnicodeData.txt | 1,913,704 | `806e9aed65037197f1ec85e12be6e8cd870fc5608b4de0fffd990f689f376a73` |
| `DerivedNormalizationProps.txt` | https://www.unicode.org/Public/15.0.0/ucd/DerivedNormalizationProps.txt | 837,688 | `d5687a48c95c7d6e1ec59cb29c0f2e8b052018eb069a4371b7368d0561e12a29` |
| `CompositionExclusions.txt` | https://www.unicode.org/Public/15.0.0/ucd/CompositionExclusions.txt | 8,911 | `3b019c0a33c3140cbc920c078f4f9af2680ba4f71869c8d4de5190667c70b6a3` |
| `NormalizationTest.txt` | https://www.unicode.org/Public/15.0.0/ucd/NormalizationTest.txt | 2,625,136 | `fb9ac8cc154a80cad6caac9897af55a4e75176af6f4e2bb6edc2bf8b1d57f326` |
| `PropList.txt` | https://www.unicode.org/Public/15.0.0/ucd/PropList.txt | 132,360 | `e05c0a2811d113dae4abd832884199a3ea8d187ee1b872d8240a788a96540bfd` |

NFC conformance follows Unicode Standard Annex #15, Unicode 15.0.0:
https://www.unicode.org/reports/tr15/tr15-53.html. The independent verification
setup downloads or uses an offline cache of the exact hashed sources; online
availability is not required for a test run. These sources provide provenance
and the offline `NormalizationTest.txt` conformance oracle. They are not a
mandate to implement or vendor a second normalization engine.

Every identifier profile requires:

- an exact JSON string containing only Unicode scalar values;
- strict UTF-8 encodability;
- nonempty value;
- no U+0000..U+001F anywhere and no U+007F anywhere;
- NFC under the exact 15.0.0 data above;
- no leading or trailing member of this exact 29-code-point edge-trim set:

  ```text
  U+0009..U+000D
  U+001C..U+001F
  U+0020
  U+0085
  U+00A0
  U+1680
  U+2000..U+200A
  U+2028..U+2029
  U+202F
  U+205F
  U+3000
  ```

- no trimming, normalization, case folding, substitution, or repair by the
  validator.

There are ten unrestricted-Unicode field surfaces but only three distinct
validation profiles. Multiple surfaces with the same language share one
profile identity; inventing use-site-specific aliases would create false
schema distinctions.

`UnicodeIdentifierProfileV1` has this exact logical order:

```text
profile_id
unicode_version
normalization_form
maximum_scalar_values
maximum_utf8_octets
forbidden_code_point_ranges
edge_trim_code_points
unicode_source_record_ids
unicode_identifier_profile_id
```

`normalization_form` is exactly `NFC`;
`forbidden_code_point_ranges` is exactly
`[["U+0000","U+001F"],["U+007F","U+007F"]]`; and
`edge_trim_code_points` is the expanded, strictly increasing 29-element tuple
specified above. `unicode_source_record_ids` contains the six source IDs in
lexical `source_name` order. The terminal profile ID is the semantic SHA-256
of the preceding members under
`RiskYieldMMA2MStep2UnicodeIdentifierProfileV1V4_9F_RawV8`.

The three exact profile records are:

| profile ID | use sites | max scalar values | max UTF-8 octets |
|---|---|---:|---:|
| `RAW_V8_UNICODE_IDENTIFIER_A_V1` | four operation-spec `workload_family` surfaces and declaration `stage` | 128 | 128 |
| `RAW_V8_UNICODE_IDENTIFIER_B_V1` | declaration `workload_id`, target `TEXT.value`, `OPTIONAL_TEXT.value`, and each `TEXT_LIST.values[]` item | 256 | 256 |
| `RAW_V8_UNICODE_IDENTIFIER_C_V1` | subscription `expected_topic` | 256 | 1,024 |

The surface count is exactly `5 + 4 + 1 = 10`. A nullable
`OPTIONAL_TEXT.value` uses profile B when non-null; null is handled by its
`ValueSchemaV2.nullable` flag. The edge-trim set deliberately includes the
four historical information separators U+001C..U+001F in addition to the 25
Unicode White_Space code points. The whole-string C0 ban already rejects
those four and U+0009..U+000D, but the trim set remains frozen independently
so no host `strip()` table can drift.

The private Raw V8 Step-2 contract module uses the host standard-library
`unicodedata` implementation. Module import and UCD-invariant ASCII/hash/
integer diagnostics remain available under another host UCD version.
Construction or decoding of any of the exact ten unrestricted-Unicode field
surfaces fails closed unless
`unicodedata.unidata_version == "15.0.0"` immediately before validating that
surface. There is no fallback to `ucd_3_2_0`, a private alternate module,
normalization repair, or a vendored normalization implementation. Once the
per-surface gate passes, validation uses that runtime's NFC predicate. The
complete hashed `NormalizationTest.txt` corpus is run offline in the
acceptance suite, not on every field validation. Acceptance explicitly tests
this import/capability separation under a simulated mismatched UCD.
Any implementation path in which the ASCII-only validator calls the
unrestricted-Unicode gate is a correction defect and must be removed before
technical acceptance; this paragraph freezes required behavior, not a claim
that every current call path already satisfies it.

## 8. Acyclic references and graph closure

Edges are:

- `OBJECT_REF` value schema -> referenced concrete or union type;
- `ARRAY` value schema -> item value schema;
- union alternative -> referenced concrete type;
- concrete type -> each attached intrinsic rule;
- rule input/result/literal schema -> its value schema;
- composite literal -> every referenced object and array item schema;
- cross-field rule typed path -> the resolved member value schema;
- rule application -> its rule, root/input types, and sequence bindings;
- resolver -> its source root, resolved item type, and every typed source path;
- derived fixed sequence/optional/ordinal binding -> its exact value schema.

The 52-node runtime type DAG is measured separately from the larger combined
value/rule/literal/application dependency DAG. Each must be acyclic after
union nodes are expanded and each has maximum depth 16. Self-reference,
mutual recursion, an unresolved reference, a reference to a legacy V1
observation node, or a runtime-type reference outside the exact 52-node
catalog rejects.

The independent verifier uses Kahn topological sorting with lexical node-name
tie breaking and requires exactly 52 emitted type nodes. Maximum typed depth
is computed over the resolved graph and must not exceed 16. The verifier does
not import production classes or discover types by reflection.

Catalog closure is equality, not a subset check:

```text
reachable value schemas from all 49 RECORD member descriptors,
rule input bindings, rule literals/results, and resolver-induced
application bindings
  = value_schema_catalog IDs

member-path-reachable value schemas
  = exact 200-schema strongest-unary component IDs

(all rule/binding-reachable value schemas - member component IDs)
  = exact additive rule-derived component IDs

member component IDs intersection additive rule-derived component IDs
  = empty set

member component IDs union additive rule-derived component IDs
  = value_schema_catalog IDs

reachable text languages from reachable TEXT schemas
  = text_language_catalog IDs

reachable ASCII DFAs and Unicode profiles from reachable text languages
  = their respective catalog IDs

attached INTRINSIC_RECORD rule IDs
union
application CROSS_RECORD rule IDs
  = {descriptor.rule_id for descriptor in rule catalog}

attached INTRINSIC_RECORD rule IDs
intersection application CROSS_RECORD rule IDs
  = empty set

semantic rule-descriptor IDs materialized in the ordered rule catalog
  = {descriptor.step2_cross_field_rule_descriptor_id}

rule application IDs named by the registry application ledger
  = rule_application_descriptor catalog IDs

fixed-position resolver IDs referenced by rule applications
  = fixed_position_resolver_profile_catalog IDs
```

An extra but well-formed schema, language, DFA, profile, rule, or application
is unreachable semantic ambiguity and rejects just like a missing record.

## 9. Typed intrinsic cross-field rules

Opaque strings such as `LOCAL_SHUTDOWN_V2_LIMIT_VECTOR_V1` are not executable
schema. Each intrinsic rule becomes one `Step2CrossFieldRuleDescriptorV2`
with exact order:

```text
rule_id
rule_version
rule_scope
ordered_rule_input_bindings
maximum_expression_nodes
root_expression_position
ordered_expression_nodes
step2_cross_field_rule_descriptor_id
```

`rule_scope` is `INTRINSIC_RECORD` or `CROSS_RECORD`. A rule input binding has
exact logical members:

```text
binding_name
binding_kind
expected_type_name
expected_value_schema_id
```

`binding_kind` is exactly:

```text
RECORD
SAFE_UINT
FIXED_RECORD_SEQUENCE
OPTIONAL_FIXED_RECORD
```

Every binding references one reachable `expected_value_schema_id`.
`RECORD` requires an exact concrete graph type and a non-null `OBJECT_REF`
schema for that type. `SAFE_UINT` requires a null type name and a non-null
`SAFE_INTEGER` schema. `FIXED_RECORD_SEQUENCE` requires an exact concrete
item type and a non-null `ARRAY` schema whose non-null item is an
`OBJECT_REF` to that type. `OPTIONAL_FIXED_RECORD` requires an exact concrete
type and a nullable `OBJECT_REF` schema for that type. A tagged-union node is
not a legal `expected_type_name`; union selection remains registry-bound
inside the dedicated operators below. Binding names are unique.

`rule_version` is exactly
`riskyieldmm_raw_v8_step2_typed_rule_v2`. Every `rule_id` is one of the exact
slash-delimited symbolic IDs in the final rule attachment/application ledger;
there is no caller-defined rule name or version fallback.

Intrinsic rules have exactly one `RECORD` binding named `self`. Cross-record
rules have at least two effective bindings, including derived sequence
elements and an ordinal `SAFE_UINT` binding when an application iterates.
`INPUT_PATH` with an empty path returns the complete binding under its exact
`expected_value_schema_id`; a nonempty path is permitted only for `RECORD`
and resolves statically through the graph.

An expression node has exact order:

```text
expression_position
operator
result_type_kind
result_value_schema_id
ordered_operand_positions
input_binding_name
typed_member_path
literal_value_schema_id
literal_value
```

Every member is present; unused members are null or empty as fixed by the
operator table. Expression positions start at one, are contiguous, and are
local to one rule. Every operand position is strictly smaller than its
consumer position; `root_expression_position` names the final Boolean node.
There are no independently hashed expression-node identities and therefore
no ambiguous cross-rule node references.

`maximum_expression_nodes` is a positive safe integer no greater than 4,096
and equals the exact materialized length of `ordered_expression_nodes`.
It is a structural evaluation-work bound, not a caller-selected budget.
Every node is reachable from the root node through operand edges. Evaluation
visits each position exactly once in increasing position order, retains that
typed result, and never lazily re-evaluates a shared operand.

`result_type_kind` is `VALUE_SCHEMA`, `INTERNAL_BYTES`,
`INTERNAL_UINT128`, or `INTERNAL_INT128`. `VALUE_SCHEMA` requires a non-null
`result_value_schema_id`; the three internal kinds require it null and cannot
be serialized into a runtime record. The closed operator vocabulary is:

```text
INPUT_PATH
LITERAL
IS_NULL
NOT
AND
OR
IMPLIES
EQ
NE
LT
LE
GT
GE
PRESENT_EQ
PRESENT_LE
SAFE_ADD
SAFE_MULTIPLY
SAFE_FLOOR_DIVIDE
SAFE_CEIL_DIVIDE
ARRAY_LENGTH
ARRAY_UNIQUE
ARRAY_STRICT_ASCENDING
ARRAY_POSITIONAL_EQUAL
ARRAY_PROJECT_REQUIRED_MEMBER
ARRAY_CONTAINS
ARRAY_FIND_UNIQUE_OBJECT_BY_MEMBER
OBJECT_MEMBER
TIMESTAMP_TO_EPOCH_MICROSECONDS
UINT128_PARSE
SAFE_UINT_TO_INTERNAL_UINT128
UINT128_ADD
UINT128_MULTIPLY
BASE64_DECODE
BASE64_ARRAY_DECODE_CONCAT
INTERNAL_BYTES_LENGTH
SHA256_BYTES
RAW_INGRESS_BATCH_ID_RECOMPUTES
RFC6455_CLOSE_PAYLOAD_VALID
FIELD_LAYER_EQUALS_UPPERCASE_FIELD_PREFIX
SEMANTIC_ID_RECOMPUTES
CANONICAL_BYTES_SATISFY_BOUND
CHECKPOINT_SELECTOR_INTRINSIC_VALID
CHECKPOINT_SELECTOR_MARKER_CONTRACT_ADMITTED
FIELD_OBSERVATION_INTRINSIC_VALID
FIELD_OBSERVATION_SATISFIES_DESCRIPTOR_POLICY
V2_FIELD_OBSERVATION_CONTEXT_VALID
SOURCE_ERROR_DETAIL_ID_RECOMPUTES_FROM_FIELD
TARGET_VALUE_SATISFIES_DESCRIPTOR
A1_FIFO_FIELDS_VALID
BITMAP_NULLABILITY_MATCHES
V2_ROOT_SEQUENCE_SELECTOR_VALID
OPERATION_RESULT_MATCHES_SIGNED_SPEC
```

No source code, regex created by a rule, callable name, Python expression,
SQL, JSONPath, or prose predicate is executable.

### 9.1 Exact expression-node shape and primitive operators

`typed_member_path` is an exact array of member names. `INPUT_PATH`,
`ARRAY_PROJECT_REQUIRED_MEMBER`,
`ARRAY_FIND_UNIQUE_OBJECT_BY_MEMBER`, and `OBJECT_MEMBER` are the only
operators permitted to carry a nonempty `typed_member_path`.
`INPUT_PATH` is the only operator permitted a non-null
`input_binding_name`. `LITERAL` is the only operator permitted non-null
`literal_value_schema_id` or `literal_value`. Every other operator requires
those four fields to be respectively null, empty, null, and null.

`LITERAL` requires
`literal_value_schema_id == result_value_schema_id` and accepts any value that
first validates recursively against that reachable value schema. Arrays
retain order. An `OBJECT_REF` literal must be an exact complete record mapping
accepted by the referenced descriptor's generic structural/scalar checks and
every intrinsic rule attached to that descriptor. Every such attached rule
must precede the current rule in the combined dependency DAG; otherwise
registry validation rejects. Composite-literal validation never skips an
attached intrinsic rule and never runs a cross-record application implicitly.
Equality of composite values is then canonical-byte equality. This explicit
composite form closes frozen catalog/root equality and no separate opaque
composite-equality operator exists.

Every expression result is checked against its declared
`result_type_kind` and, for `VALUE_SCHEMA`, its exact
`result_value_schema_id` before any consumer is evaluated. The dependency
graph formed by value-schema references, object/array literals, referenced
record intrinsic rules, and rule-expression operands must be acyclic and have
maximum depth 16. A literal that would re-enter its current rule, directly or
indirectly, rejects during registry validation rather than recursing at
runtime.

Member-path traversal is static and schema-directed. Each path segment must
select one required member of the current concrete `OBJECT_REF`; traversal may
not step through an `ARRAY` or a tagged-union value. A path may terminate at
an array only when the operator's declared result schema is that exact array
schema. `ARRAY_PROJECT_REQUIRED_MEMBER` and
`ARRAY_FIND_UNIQUE_OBJECT_BY_MEMBER` start the declared path independently
from each concrete object item; they never treat the source array as an
implicit path segment. An unresolved, nullable-intermediate, array-crossing,
union-crossing, or result-schema-mismatched path rejects during registry
validation.

In the tables below `S` means one exact reachable value schema, `S?` means
the same schema may be nullable, `A[S]` means a bounded non-null array with
item schema `S`, `R[T]` means a non-null object reference to concrete type
`T`, `B` is the unique non-null unrestricted Boolean schema
(`boolean_literal = null`), `U` is a non-null safe integer, `T[L]` is
non-null text under exact language `L`, and `IB`, `IU128`, and `II128` are
the three nonserializable internal result kinds. “Reject” means deterministic
rule-evaluation failure and therefore record/application rejection; it never
means false, null, truncation, saturation, or coercion.

| operator | exact arity | operand types | result | null/failure semantics |
|---|---:|---|---|---|
| `INPUT_PATH` | 0 | one named binding plus its statically resolved path | exact resolved value schema | unresolved member, illegal nonempty sequence path, union crossing, or type disagreement rejects |
| `LITERAL` | 0 | exact recursively validated literal | declared schema | invalid, noncanonical, or schema-mismatched literal rejects |
| `IS_NULL` | 1 | any exact nullable value schema `S?` | `B` | never propagates null; returns whether the operand is JSON null |
| `NOT` | 1 | `B` | `B` | null/non-Boolean rejects |
| `AND` | 2 | `B, B` | `B` | both operands are evaluated; null/non-Boolean rejects |
| `OR` | 2 | `B, B` | `B` | both operands are evaluated; null/non-Boolean rejects |
| `IMPLIES` | 2 | `B, B` | `B` | exact `not antecedent or consequent`; both operands evaluated |
| `EQ`, `NE` | 2 | same exact value schema, or the same one of `IB`, `IU128`, `II128` | `B` | internal bytes use exact byte equality; null is a value only when the common value schema is nullable; no coercion |
| `LT`, `LE`, `GT`, `GE` | 2 | same non-null `U`, `T[L]`, `IU128`, or `II128` | `B` | null or unlike schemas rejects |
| `PRESENT_EQ` | 2 | nullable scalar `S?`, then non-null scalar `S` with the identical non-null base schema | `B` | returns false when operand one is null; otherwise applies exact equality; no flow refinement or coercion |
| `PRESENT_LE` | 2 | same exact nullable ordered scalar schema `S?` | `B` | returns false when either operand is null; otherwise applies exact `LE`; it never refines or unwraps either operand for another node |
| `SAFE_ADD`, `SAFE_MULTIPLY` | 2 | `U, U` | `U` | result above 9,007,199,254,740,991 rejects |
| `SAFE_FLOOR_DIVIDE` | 2 | `U, U` | `U` | zero denominator rejects; exact mathematical floor |
| `SAFE_CEIL_DIVIDE` | 2 | `U, U` | `U` | zero denominator rejects; computes mathematical ceiling without an overflowing intermediate |
| `TIMESTAMP_TO_EPOCH_MICROSECONDS` | 1 | `T[RFC3339_UTC]` | `II128` | only the frozen 20/27-octet UTC grammar; parse failure rejects |
| `UINT128_PARSE` | 1 | `T[UINT128_DECIMAL]` | `IU128` | noncanonical/out-of-range decimal rejects |
| `SAFE_UINT_TO_INTERNAL_UINT128` | 1 | `U` | `IU128` | exact widening conversion; no serialization or narrowing |
| `UINT128_ADD`, `UINT128_MULTIPLY` | 2 | `IU128, IU128` | `IU128` | exact unsigned arithmetic; mathematical result above `2^128-1` rejects, with no saturation or wraparound |
| `BASE64_DECODE` | 1 | `T[CANONICAL_BASE64]` | `IB` | exact RFC 4648 standard alphabet/padding and decode-re-encode equality; failure rejects |
| `BASE64_ARRAY_DECODE_CONCAT` | 2 | `A[T[CANONICAL_BASE64]], U` | `IB` | decodes and concatenates in array order; aggregate output above operand-two cap rejects |
| `INTERNAL_BYTES_LENGTH` | 1 | `IB` | `U` | output above safe-uint range rejects |
| `SHA256_BYTES` | 1 | `IB` | `T[LOWERCASE_SHA256]` | no null form |
| `FIELD_LAYER_EQUALS_UPPERCASE_FIELD_PREFIX` | 2 | `T[LAYER], T[FIELD_ID]` | `B` | requires exactly one structural dot; ASCII uppercases the prefix without locale |
| `SEMANTIC_ID_RECOMPUTES` | 2 | `R[T], T[LOWERCASE_SHA256]` | `B` | `T` must statically be a standalone type with a non-null domain, identity field, and identity-payload order; wrong type/identity schema rejects |
| `CANONICAL_BYTES_SATISFY_BOUND` | 1 | `R[T]` | `B` | uses only `T`'s registry `LE`/`LT` relation and limit; serialization failure rejects |

For valid text whose language has
`ordering_semantics = UNICODE_SCALAR_LEXICOGRAPHIC`,
`LT`/`LE`/`GT`/`GE` and `ARRAY_STRICT_ASCENDING` use Unicode scalar-value
lexicographic order. For the restricted ASCII languages this is identical to
UTF-8 byte order. A text language with `ordering_semantics = NONE` is not a
legal ordered operand. Locale, normalization repair, case folding, and host
collation are forbidden. Chronology always uses
`TIMESTAMP_TO_EPOCH_MICROSECONDS` and signed-integer comparison.

`TIMESTAMP_TO_EPOCH_MICROSECONDS` produces signed `INTERNAL_INT128` epoch
microseconds. The year-0001..9999 language does not fit the I-JSON safe
integer range, so returning `SAFE_INTEGER` is forbidden.

### 9.2 Collection operators

| operator | exact arity | operand types | result | exact semantics |
|---|---:|---|---|---|
| `ARRAY_LENGTH` | 1 | `A[S]` | `U` | materialized length; an unbounded array is not a legal operand |
| `ARRAY_UNIQUE` | 1 | `A[S]` | `B` | exact scalar equality or canonical-byte equality for composite items |
| `ARRAY_STRICT_ASCENDING` | 1 | `A[S]` where `S` is one non-null ordered scalar schema | `B` | each adjacent item is strictly increasing under the frozen order |
| `ARRAY_POSITIONAL_EQUAL` | 2 | same exact `A[S]` | `B` | equal cardinality and exact equality at every position |
| `ARRAY_PROJECT_REQUIRED_MEMBER` | 1 | `A[R[T]]` plus one statically resolved nonempty per-item object path | declared `A[S]` with exactly the input array's minimum and maximum bounds | applies the path from each object item independently and preserves cardinality/order; path traversal cannot cross an array or union; null item/member rejects unless declared item schema is nullable |
| `ARRAY_CONTAINS` | 2 | `A[S], S` | `B` | exact membership under `S`; unlike schemas reject |
| `ARRAY_FIND_UNIQUE_OBJECT_BY_MEMBER` | 2 | `A[R[T]], S` plus one statically resolved per-item key path to `S` | `R[T]` | applies the key path from each object item independently; exactly one matching object is required; zero or multiple matches rejects; array/union crossing rejects |
| `OBJECT_MEMBER` | 1 | `R[T]` plus one statically resolved nonempty object path | exact member schema | unresolved path, array/union crossing, nullable intermediate, or forbidden null rejects |
| `BITMAP_NULLABILITY_MATCHES` | 2 | exact bitmap text, exact fixed-length `A[U?]` | `B` | equal frozen length; bit `1` iff value non-null and `0` iff null |
| `A1_FIFO_FIELDS_VALID` | 2 | exact field-observation array, exact target registry | `B` | resolves the unique `A1_FIFO_SEQUENCE_KIND_LENGTH_AND_ORDER_V1` cross-field authority record and its three named fields from the supplied registry; when all are available, types are exact, count equals both lengths, length is at most four, and sequences strictly increase; otherwise true |

Projection output, key-path schema, bitmap length, and all collection maxima
are part of expression result schemas and are checked before evaluation.
There is no implicit loop, unbounded scan, sorting, deduplication, truncation,
or Cartesian product.

### 9.3 Registry-bound domain operators

| operator | exact arity | operand types | result | exact authority and behavior |
|---|---:|---|---|---|
| `RAW_INGRESS_BATCH_ID_RECOMPUTES` | 2 | exact ordered Base64 array, lowercase SHA-256 | `B` | recomputes SHA-256 over the canonical JSON bytes of the exact two-member object `{"domain":"RiskYieldMMExactOrderedDecryptedIngressChunksV4_5","ordered_chunks_base64":<array>}`; callers cannot select the domain/key |
| `RFC6455_CLOSE_PAYLOAD_VALID` | 2 | exact `CLOSE\|PONG` opcode, `IB` | `B` | non-`CLOSE` is true; `CLOSE` length one returns false; length at least two returns true only for the production-frozen status-code set and strict UTF-8 remainder |
| `CHECKPOINT_SELECTOR_INTRINSIC_VALID` | 1 | exact selector record | `B` | validates positions `1..N`, common operation, unique marker/occurrence coordinates, the frozen operation-specific rank table, per-marker occurrence strict increase, length, and embedded entry-identity projection; `N=0` is legal |
| `CHECKPOINT_SELECTOR_MARKER_CONTRACT_ADMITTED` | 2 | exact selector record, exact marker-contract record | `B` | validates the selector length against the supplied exact contract and requires every selector entry marker to be admitted for its operation by the unique matching contract record; it does not own selector position, ID, coordinate, or DFA-order truth |
| `FIELD_OBSERVATION_INTRINSIC_VALID` | 1 | exact field-observation record | `B` | validates all registry-independent availability/value/censoring, attempted-method, adapter-span, errno/class/digest-pair, source-phase, and tagged duration-relation branch truth without crossing the target-value union through a typed path |
| `FIELD_OBSERVATION_SATISFIES_DESCRIPTOR_POLICY` | 3 | exact field observation, exact field descriptor, exact target registry | `B` | resolves the unique descriptor and status-policy authority from the supplied registry; validates field/registry identity, descriptor censoring and allowed-reason admission, and the unavailable reason/attempt/adapter-span/failure-phase/error-form policy |
| `V2_FIELD_OBSERVATION_CONTEXT_VALID` | 5 | exact field observation, exact field descriptor, exact target registry, exact V2 observation context, safe-uint field ordinal | `B` | validates zero-based descriptor position, field/registry/context identity, placeholder reason, operation/attempt/instrumentation eligibility, method/role/checkpoint admission, and field adapter-span containment within the observer span |
| `SOURCE_ERROR_DETAIL_ID_RECOMPUTES_FROM_FIELD` | 1 | exact field-observation record | `B` | if error class is present, constructs the exact six-member `SourceErrorDetailV1` preimage and compares the digest; otherwise requires null digest |
| `TARGET_VALUE_SATISFIES_DESCRIPTOR` | 3 | exact field observation, exact field descriptor, exact target registry | `B` | resolves the selected union alternative plus one of 17 constraints, six shapes, and any vocabulary from the supplied frozen registry; validates interval, SHA, uint128, errno, enum, list-cardinality, and fixed-map-key rules |
| `V2_ROOT_SEQUENCE_SELECTOR_VALID` | 3 | exact root, complete fixed observation sequence, optional fixed selector | `B` | validates startup/ordinary role order, selector-free branches, selector length, checkpoint alignment, and filtered exact-marker ordinal strict increase |
| `OPERATION_RESULT_MATCHES_SIGNED_SPEC` | 2 | exact operation-result wrapper, exact operation-spec wrapper | `B` | resolves the operation-kind-indexed spec alternative and the separately typed result alternative from their two exact tagged unions, then applies the frozen subscription/ingress/ACK/shutdown equality and signed-limit matrix |

These operators may resolve only semantic records supplied as operands and
the exact type/union/value-schema descriptors in the registry that contains
the current rule. They may not read module globals, files, databases,
network state, wall clocks, callables, or a caller-selected catalog. Their
finite branch tables and literal domains are part of this normative document
and their adversarial conformance vectors are part of the witness artifact.
Failure to resolve an exact descriptor, alternative, constraint, shape,
vocabulary, or supplied frozen record rejects.

Every registry-bound operator uses one uniform outcome contract. After all
operands have passed their exact declared schemas, a violated business
invariant returns Boolean false. A malformed operand, unresolved/duplicated
authority record, missing catalog entry, type/union mismatch, work-bound
violation, or impossible branch causes deterministic rule-evaluation failure.
It never returns null or silently selects a default. A false rule root and an
evaluation failure both reject the record/application, but the failure class
remains distinguishable in validation evidence.

The `RFC6455_CLOSE_PAYLOAD_VALID` frozen status-code language is exactly
`{1000, 1001, 1002, 1003, 1007, 1008, 1009, 1010, 1011, 1012, 1013, 1014}`
union the inclusive range `3000..4999`. An empty `CLOSE` payload is legal;
one octet returns false; two or more octets use an unsigned big-endian 16-bit
code followed by a strict UTF-8 reason and return false for an inadmissible
code or invalid reason bytes.

#### 9.3.1 Exact selector intrinsic and marker-contract admission

`CHECKPOINT_SELECTOR_INTRINSIC_VALID` uses only the supplied exact selector
and this external-schema-profile rank table:

| operation kind | exact permitted rank order |
|---|---|
| `ACK_DEADLINE_EXPIRY` | `ACK_DEADLINE_NOT_DUE`, `ACK_DEADLINE_TERMINAL_CONVERGED`, `TARGET_ESCAPE_OBSERVED` |
| `INGRESS` | `RAW_PREFIX_COMMITTED`, `PARSER_UNIT_CONVERGED`, `INGRESS_RETURN_READY`, `TARGET_ESCAPE_OBSERVED` |
| `LOCAL_SHUTDOWN` | `LOCAL_CLOSE_DISPATCH_CONVERGED`, `TLS_CONTROL_CONVERGED`, `TCP_HALF_CLOSE_CONVERGED`, `SHUTDOWN_TERMINAL_CONVERGED`, `TARGET_ESCAPE_OBSERVED` |
| `SUBSCRIPTION_DISPATCH` | `OUTBOUND_ARTIFACTS_PREPARED`, `KERNEL_SEND_RESULT_CONVERGED`, `DISPATCH_RETURN_READY`, `TARGET_ESCAPE_OBSERVED` |

For selector length `N` in `0..64`, the operator returns true exactly when:
entry positions are `1..N`; every entry operation equals the selector
operation; every marker occurs in that operation's row above; marker ranks
are nondecreasing; occurrence indices strictly increase within each marker;
`(marker, occurrence)` coordinates are unique; `selector_length == N`; and
the selector's ordered entry-ID array equals the recomputed identities of the
complete entries positionally. Any well-typed disagreement returns false.
This unary operator is the complete intrinsic selector authority and is
always applied before a selector can be used as a composite value or
cross-record input.

`CHECKPOINT_SELECTOR_MARKER_CONTRACT_ADMITTED` then uses the same already
intrinsically valid selector plus the supplied exact marker contract. It
requires `selector_length <= maximum_checkpoint_selector_length`, resolves
exactly one matching `ordered_checkpoint_operation_records` row for each
entry marker, and requires the selector operation in that row's exact
`applicable_operation_kinds`. A missing or duplicate contract record, a
forbidden full-checkpoint marker, or an inconsistent supplied contract is
unresolved authority and fails evaluation. A well-typed selector marker that
is simply not admitted for its operation returns false. This cross operator
does not re-own positions, embedded IDs, coordinate uniqueness, or rank/order
truth.

#### 9.3.2 Exact signed-spec/result matrix

`OPERATION_RESULT_MATCHES_SIGNED_SPEC` first requires equal wrapper
`operation_kind` values and the exact tag/body pair in each separate union:

| kind | spec tag / concrete body | result tag / concrete body |
|---|---|---|
| `ACK_DEADLINE_EXPIRY` | `ACK_DEADLINE_EXPIRY_SPEC_V1` / `CapacityMeasurementAckDeadlineExpirySpecV1` | `ACK_DEADLINE_EXPIRY_RESULT_EVIDENCE_V1` / `CapacityMeasurementAckDeadlineExpiryResultEvidenceV1` |
| `INGRESS` | `INGRESS_OPERATION_SPEC_V2` / `CapacityMeasurementIngressOperationSpecV2` | `INGRESS_RESULT_EVIDENCE_V2` / `CapacityMeasurementIngressResultEvidenceV2` |
| `LOCAL_SHUTDOWN` | `LOCAL_SHUTDOWN_SPEC_V2` / `CapacityMeasurementLocalShutdownSpecV2` | `LOCAL_SHUTDOWN_RESULT_EVIDENCE_V2` / `CapacityMeasurementLocalShutdownResultEvidenceV2` |
| `SUBSCRIPTION_DISPATCH` | `SUBSCRIPTION_DISPATCH_SPEC_V2` / `CapacityMeasurementSubscriptionDispatchSpecV2` | `SUBSCRIPTION_DISPATCH_RESULT_EVIDENCE_V2` / `CapacityMeasurementSubscriptionDispatchResultEvidenceV2` |

The exact per-kind comparisons are:

- subscription: result `generated_logical_opcode` equals spec
  `expected_logical_opcode`, and result `local_dispatch_disposition` equals
  spec `expected_dispatch_disposition`;
- ingress: result `observed_consumed_new_input_octets`,
  `observed_parser_unit_count`,
  `observed_completed_application_message_count`,
  `observed_logical_output_frame_count`,
  `observed_logical_output_payload_octets`, and
  `observed_logical_output_frames_sha256` equal respectively spec
  `input_octet_count`, `expected_parser_unit_count`,
  `expected_completed_application_message_count`,
  `expected_logical_output_frame_count`,
  `expected_logical_output_payload_octets`, and
  `expected_logical_output_frames_sha256`;
- ACK: embedded due-clock `outbound_subscription_intent_id` equals
  `expected_outbound_subscription_intent_id`, and embedded due-clock
  `due_scenario` equals spec `due_scenario`;
- local shutdown: result `terminal_outcome` equals
  `expected_terminal_outcome`; the following twelve result/spec pairs satisfy
  `result <= signed maximum` in the listed order:

  ```text
  final_terminal_ingress_batch_count
    <= maximum_terminal_ingress_batches
  final_terminal_ingress_ciphertext_octets
    <= maximum_terminal_ingress_ciphertext_octets
  final_terminal_ingress_plaintext_octets
    <= maximum_terminal_ingress_plaintext_octets
  final_terminal_socket_receive_call_count
    <= maximum_terminal_socket_receive_calls
  final_terminal_tls_record_count
    <= maximum_terminal_tls_records
  final_terminal_tls_unwrap_iteration_count
    <= maximum_terminal_tls_unwrap_iterations
  final_terminal_zero_progress_iteration_count
    <= maximum_terminal_zero_progress_iterations
  final_terminal_ingress_parser_unit_count
    <= maximum_terminal_ingress_parser_units
  final_terminal_ingress_automatic_output_count
    <= maximum_terminal_ingress_automatic_outputs
  final_websocket_send_attempt_count
    <= maximum_websocket_send_attempts
  final_tls_control_send_attempt_count
    <= maximum_tls_control_send_attempts
  final_peer_shutdown_poll_count
    <= maximum_peer_shutdown_polls
  ```

  and the lengths of
  `ordered_terminal_ingress_read_attempt_event_ids` and
  `ordered_terminal_parser_transition_event_ids` are no greater than
  `maximum_terminal_ingress_batches` and
  `maximum_terminal_ingress_parser_units`, respectively.

A well-typed mismatch in any listed comparison returns false. A missing union
branch or wrong concrete body is an evaluation failure, not false or fallback.

#### 9.3.3 Exact V2 root/sequence/selector branches

`V2_ROOT_SEQUENCE_SELECTOR_VALID` requires the complete resolved observation
sequence to have the root's exact materialized count and ordered recomputed
identities. Every observation context must equal the root on `candidate_id`,
`attempt_id`, `operation_kind`, `instrumentation_mode`, and
`target_field_registry_id`.

It selects exactly one top-level branch:

1. `STARTUP_RECOVERY`: exactly one observation; root attempt and selector ID
   are null; the optional supplied selector is null.
2. `ORDINARY`: at least three observations ordered `BEFORE_OPERATION`, zero or
   more `STABLE_CHECKPOINT`, `AFTER_OPERATION`, `OPERATION_AGGREGATE`.

`ORDINARY` then selects exactly one subbranch:

- selector-free: instrumentation is `OFF` or attempt is null; exactly three
  observations; root selector ID and supplied selector are null;
- selector-bound: instrumentation is `ON` and attempt is non-null; the
  supplied selector is exact and non-null; its operation and recomputed
  identity equal the root; observation count equals selector length plus
  three. Each checkpoint context positionally equals its selector entry on
  selector ID, selector position, entry ID, expected marker, and expected
  occurrence. The subsequence of non-null `marker_ordinal` values from
  `EXACT_MARKER` checkpoint contexts is strictly increasing and unique.

The two top-level branches are disjoint, and the two ordinary subbranches are
disjoint. A well-typed branch mismatch returns false;
resolver/type/identity failure fails evaluation.

#### 9.3.4 Exact target-value null and authority semantics

`TARGET_VALUE_SATISFIES_DESCRIPTOR` requires the supplied descriptor to be
the unique descriptor with the field observation's `field_id` in the
supplied exact registry. Descriptor or registry mismatch is unresolved
authority and fails evaluation. A null field value returns true from this
operator; the separate availability/state rule decides whether null is
allowed. A non-null value must select exactly the descriptor's value-kind
alternative. It then validates the descriptor's referenced one of exactly
17 value constraints, one of six shapes, optional vocabulary, list
cardinality, and fixed-map key order. The constraint IDs are exactly:

```text
BOOL_EXACT
DURATION_BOUND_SAFE_IJSON
FIXED_UINT_MAP_SAFE_IJSON
OPTIONAL_TEXT_ENUM_A1_COMMAND_KIND
OPTIONAL_TEXT_ENUM_A1_REJECTION_CLASS
OPTIONAL_TEXT_PLATFORM_ERRNO
OPTIONAL_TEXT_SHA256
OPTIONAL_TEXT_UINT128_DECIMAL
OPTIONAL_UINT_SAFE_IJSON
TEXT_ENUM_A1_ADMISSION_OUTCOME
TEXT_ENUM_A1_COMMAND_KIND
TEXT_ENUM_SQLITE_PRIMARY_RESULT
TEXT_LIST_ENUM_A1_COMMAND_KIND
TEXT_SHA256
UINT_LIST_SAFE_IJSON
UINT_LOOP_PROBE_INTERVAL_NS
UINT_SAFE_IJSON
```

`UINT_LOOP_PROBE_INTERVAL_NS` is `1,000,000..60,000,000,000`;
SHA constraints use lowercase SHA-256; uint128 uses canonical decimal through
`2^128-1`; platform errno uses the exact errno DFA; enum constraints resolve
only their supplied registry vocabulary; list bounds come from the resolved
shape; fixed-map keys equal the descriptor's exact ordered key array.
For `UINT_LIST`, `TEXT_LIST`, and `FIXED_UINT_MAP`, a non-null
`collection_item_constraint_id` performs exactly one unique lookup in the same
17-record constraint catalog and validates each item value against that
resolved scalar constraint. The resolved item constraint must not itself have
a collection item constraint; a missing, duplicated, cyclic, nested
collection, or item-kind-incompatible lookup fails evaluation.
A well-typed value outside its resolved constraint returns false. An unknown,
duplicated, inconsistent, or wrong-kind constraint/shape/vocabulary fails
evaluation.

#### 9.3.5 Exact field-observation policy partition

The field-observation contract is deliberately split across four rules so a
direct field/registry tuple and a V2 positional application are both
executable without ambient production globals:

1. `FIELD_OBSERVATION_INTRINSIC_VALID(field)` owns only facts available from
   the complete field record itself.
2. `SOURCE_ERROR_DETAIL_ID_RECOMPUTES_FROM_FIELD(field)` owns the source-error
   digest preimage.
3. `FIELD_OBSERVATION_SATISFIES_DESCRIPTOR_POLICY(field, descriptor,
   registry)` owns the registry-resolved descriptor/status policy.
4. `V2_FIELD_OBSERVATION_CONTEXT_VALID(field, descriptor, registry, context,
   ordinal)` owns only V2 position and context policy.

`TARGET_VALUE_SATISFIES_DESCRIPTOR(field, descriptor, registry)` is evaluated
in both registry-bound rule paths and remains the sole selected-union/value
constraint authority. None of the four operators above may duplicate its 17
constraint, six shape, vocabulary, list, or fixed-map validation.

`FIELD_OBSERVATION_INTRINSIC_VALID` returns true exactly when all of these
registry-independent conditions hold:

- `adapter_span_status = AVAILABLE` iff both offsets are non-null and
  `started <= completed`; every other adapter-span status requires both
  offsets null;
- source errno number/name are either both null or both non-null;
  source-error class/digest are either both null or both non-null;
- `AVAILABLE` and `CENSORED` require a non-null value, `ATTEMPTED`, a
  non-sentinel method, an available adapter span, null unavailable reason,
  failure phase `NONE`, and no source-error members;
- `AVAILABLE` additionally requires censoring `NONE`, and a duration-bound
  value has relation `EXACT`;
- `CENSORED` requires a duration-bound value and a non-`NONE` censoring value;
  `LEFT`, `RIGHT`, and `INTERVAL` map exactly to duration relations
  `UPPER_BOUND`, `LOWER_BOUND`, and `INTERVAL`;
- `NOT_APPLICABLE` requires null value, reason
  `NOT_APPLICABLE_TO_OPERATION` or `NOT_APPLICABLE_TO_REACHED_STATE`,
  sentinel method, `NOT_ATTEMPTED`, adapter span `NOT_APPLICABLE`, censoring
  `NONE`, failure phase `NONE`, and no source-error members;
- `UNAVAILABLE` requires null value, a non-null reason, and censoring `NONE`;
  `ATTEMPTED` requires a non-sentinel method and `NOT_ATTEMPTED` requires the
  sentinel method.

The direct tuple rule resolves the descriptor by
`ARRAY_FIND_UNIQUE_OBJECT_BY_MEMBER(registry.descriptors, field.field_id)`
and compares it by canonical bytes with its explicit descriptor operand.
Zero or multiple matches, a descriptor operand that differs from the resolved
record, a field registry ID unequal to the recomputed supplied-registry ID,
or a descriptor status-policy ID unequal to the supplied registry's exact
status-policy record fails authority resolution.

`FIELD_OBSERVATION_SATISFIES_DESCRIPTOR_POLICY` then returns true exactly
when:

- a non-null unavailable reason occurs in the descriptor's exact
  `allowed_status_reasons`;
- `CENSORED` is admitted only when `descriptor.censoring_allowed` is true;
- a non-null reason resolves exactly one reason rule whose
  `required_availability` equals the field availability;
- that reason rule resolves exactly one attempt-state row for the field
  attempt;
- `AVAILABLE_ONLY`, `NOT_APPLICABLE_ONLY`, and `UNAVAILABLE_ONLY` map exactly
  to adapter-span statuses `AVAILABLE`, `NOT_APPLICABLE`, and `UNAVAILABLE`;
- the field failure phase belongs to that row's exact permitted set; and
- the effective error form is `OS` when the errno pair is present, `NON_OS`
  when the class/digest pair is present, otherwise `STATUS_ONLY` when that
  row admits it, and `NONE` otherwise, and that effective form belongs to the
  row's exact permitted set.

The status-policy record is the one supplied inside the registry; a same-named
record from another catalog is not authority. The exact frozen Type-24
payload rule in Section 9.3.6 proves the policy, descriptor, shape,
constraint, vocabulary, and cross-field catalogs are the production-frozen
catalog rather than merely sorted caller-authored records.

`V2_FIELD_OBSERVATION_CONTEXT_VALID` receives the zero-based application
ordinal. It first requires `ordinal < 185`,
`registry.descriptors[ordinal]` to equal the descriptor operand,
`field.field_id == descriptor.field_id`,
`field.target_field_registry_id == context.target_field_registry_id ==
registry.target_field_registry_id`, and
`field.observation_context_id == context.observation_context_id`.

For a V2 placeholder context, its binding reason maps to every field reason
as follows:

| context reason | exact field reason |
|---|---|
| `TARGET_BOUNDARY_NOT_REACHED` | `CHECKPOINT_PLACEHOLDER_TARGET_BOUNDARY_NOT_REACHED` |
| `SOURCE_CLOCK_UNAVAILABLE` | `CHECKPOINT_PLACEHOLDER_SOURCE_CLOCK_UNAVAILABLE` |
| `ARTIFACT_BOUND_EXCEEDED` | `CHECKPOINT_PLACEHOLDER_ARTIFACT_BOUND_EXCEEDED` |
| `OBSERVER_INTERNAL_ERROR` | `CHECKPOINT_PLACEHOLDER_OBSERVER_INTERNAL_ERROR` |

A placeholder field must be `UNAVAILABLE`, null-valued, use the mapped reason,
sentinel method, `NOT_ATTEMPTED`, adapter span `NOT_APPLICABLE` with null
offsets, censoring `NONE`, failure phase `NONE`, and no source-error members.
Outside a placeholder context all four placeholder-only field reasons return
false.

For a non-placeholder context, operation exclusion requires
`NOT_APPLICABLE/NOT_APPLICABLE_TO_OPERATION`; an operation-applicable field
may not use that reason. If the attempt is null and the field ID is in the
following exact 85-member attempt-required table, the field must be
`NOT_APPLICABLE/NOT_APPLICABLE_TO_REACHED_STATE`:

```text
actor.batch_append_maximum_elapsed_ns
actor.batch_append_total_elapsed_ns
actor.operation_appended_events
actor.operation_batch_append_calls
actor.operation_single_append_calls
actor.rebuild_maximum_elapsed_ns
actor.rebuild_total_elapsed_ns
actor.single_append_maximum_elapsed_ns
actor.single_append_total_elapsed_ns
actor.validation_maximum_elapsed_ns
actor.validation_total_elapsed_ns
freshness.close_to_response_terminal_last_ns
freshness.close_to_response_terminal_maximum_ns
freshness.close_units
freshness.ping_to_pong_terminal_last_ns
freshness.ping_to_pong_terminal_maximum_ns
freshness.ping_units
freshness.target_effect_elapsed_boottime_ns
ingress.operation_new_raw_count
ingress.operation_new_raw_octets
kernel.operation_last_send_errno
kernel.operation_recv_calls
kernel.operation_recv_ciphertext_octets
kernel.operation_send_accepted_octets
kernel.operation_send_attempts
kernel.operation_send_failures
kernel.operation_send_positive_results
loop.final_unfired_delay_lower_bound_ns
loop.probe_last_delay_ns
loop.probe_maximum_delay_ns
loop.probe_phases_missed
loop.probe_ring_overwritten
loop.probe_total_delay_ns
loop.probes_fired
loop.probes_scheduled
loop.slow_callback_events
parser.last_unit_elapsed_ns
parser.last_unit_thread_cpu_ns
parser.maximum_unit_elapsed_ns
parser.maximum_unit_thread_cpu_ns
parser.operation_application_completions
parser.operation_automatic_output_chunks
parser.operation_automatic_output_octets
parser.operation_complete_frames
parser.operation_error_units
parser.operation_fragment_units
parser.operation_payload_octets
parser.operation_source_octets
parser.operation_units
parser.total_unit_elapsed_ns
parser.total_unit_thread_cpu_ns
process.gc_collected_objects_by_generation
process.gc_collections_by_generation
process.gc_pause_count
process.gc_pause_maximum_elapsed_ns
process.gc_pause_total_elapsed_ns
process.gc_uncollectable_by_generation
process.operation_owner_thread_cpu_ns
process.operation_process_cpu_ns
sqlite.begin_maximum_elapsed_ns
sqlite.begin_total_elapsed_ns
sqlite.body_maximum_elapsed_ns
sqlite.body_total_elapsed_ns
sqlite.commit_maximum_elapsed_ns
sqlite.commit_total_elapsed_ns
sqlite.last_primary_result_class
sqlite.operation_canonical_record_octets
sqlite.operation_rollbacks_attempted
sqlite.operation_rows_written
sqlite.operation_transactions_attempted
sqlite.operation_transactions_begun
sqlite.operation_transactions_committed
sqlite.operation_transactions_rolled_back
sqlite.operation_transactions_uncertain
sqlite.result_class_counts
sqlite.rollback_maximum_elapsed_ns
sqlite.rollback_total_elapsed_ns
tls.operation_ciphertext_fed_octets
tls.operation_ciphertext_produced_octets
tls.operation_plaintext_accepted_octets
tls.operation_plaintext_produced_octets
tls.operation_read_calls
tls.operation_want_read_count
tls.operation_want_write_count
tls.operation_write_calls
```

With instrumentation `OFF`, exactly
`loop.probe_interval_ns`,
`process.filesystem_mount_cgroup_identity_id`, and
`process.runtime_environment_id` must remain `AVAILABLE`;
`freshness.analysis_pressure_episode_age_boottime_ns` must be
`UNAVAILABLE/NO_FROZEN_PRESSURE_POLICY`; every other otherwise-applicable
field must be `UNAVAILABLE/INSTRUMENTATION_DISABLED`. With instrumentation
`ON`, `INSTRUMENTATION_DISABLED` is forbidden.

An attempted observation method must resolve exactly one descriptor
method/role row admitting the current observation role. At
`STABLE_CHECKPOINT`, the actual checkpoint marker must also belong to the
descriptor's exact allowed-marker array. When the field adapter span is
available, the observer span must be available and
`observer.started <= field.started <= field.completed <=
observer.completed`. The V2 operator does not evaluate A1 FIFO; that remains
the single aggregate application.

#### 9.3.6 Exact frozen-catalog payload equality

A self-consistent semantic ID is not a substitute for the production-frozen
payload. Intrinsic rules therefore enforce:

- Type 18 `MarkerContractV1`: canonical-literal equality of
  `ordered_marker_kinds`, `ordered_full_checkpoint_marker_kinds`,
  `ordered_checkpoint_operation_records`, and
  `forbidden_full_checkpoint_marker_kinds`; its version, three capacity
  values, and Boolean are exact unary schemas;
- Type 24 `TargetFieldRegistryV1`: canonical-literal equality of
  `status_reason_policy_definition`, `ordered_vocabulary_definitions`,
  `ordered_value_shape_definitions`, `ordered_value_constraint_definitions`,
  `ordered_cross_field_constraint_definitions`, and `descriptors`; profile
  and `field_count = 185` are exact unary schemas;
- Type 25 `OperationCounterSnapshotSchemaV1`: canonical-literal equality of
  `ordered_counter_field_ids` and `monotone_counter_field_ids`;
  `counter_field_count = 66` is an exact unary schema;
- Type 39 `CapacityMeasurementCheckpointOperationRecordV1`: the exact
  marker-to-operation functional table below.

The V2 Type-24 status policy contains exactly 26 reason rows. It supersedes
the historical 22-row V1 policy by adding these four rows:

| reason | required availability | context predicate | exact attempt/error row |
|---|---|---|---|
| `CHECKPOINT_PLACEHOLDER_ARTIFACT_BOUND_EXCEEDED` | `UNAVAILABLE` | `V2_CHECKPOINT_PLACEHOLDER_ARTIFACT_BOUND` | `NOT_ATTEMPTED`, error form `NONE`, phase `NONE`, adapter span `NOT_APPLICABLE_ONLY` |
| `CHECKPOINT_PLACEHOLDER_OBSERVER_INTERNAL_ERROR` | `UNAVAILABLE` | `V2_CHECKPOINT_PLACEHOLDER_OBSERVER_INTERNAL_ERROR` | `NOT_ATTEMPTED`, error form `NONE`, phase `NONE`, adapter span `NOT_APPLICABLE_ONLY` |
| `CHECKPOINT_PLACEHOLDER_SOURCE_CLOCK_UNAVAILABLE` | `UNAVAILABLE` | `V2_CHECKPOINT_PLACEHOLDER_SOURCE_CLOCK_UNAVAILABLE` | `NOT_ATTEMPTED`, error form `NONE`, phase `NONE`, adapter span `NOT_APPLICABLE_ONLY` |
| `CHECKPOINT_PLACEHOLDER_TARGET_BOUNDARY_NOT_REACHED` | `UNAVAILABLE` | `V2_CHECKPOINT_PLACEHOLDER_TARGET_BOUNDARY_NOT_REACHED` | `NOT_ATTEMPTED`, error form `NONE`, phase `NONE`, adapter span `NOT_APPLICABLE_ONLY` |

The four values also occur in the exact `RAW_V8_STATUS_REASON` vocabulary and
in every descriptor's admitted reason array through the frozen descriptor
profiles. Therefore the historical target-registry identity
`d09226eddb8b5f10345267132b42706dfd54dd356b434315e39aeebecc135235`
is stale and rejects. Exact payload equality plus generic identity
recomputation yields these current standalone identities:

```text
MarkerContractV1.marker_contract_id =
  1e529cc6ced2f3a67cafca3ec2af5146322c73b89f9cd4385cbd7b72949132b4

TargetFieldRegistryV1.target_field_registry_id =
  ae01f3a8e53163eefdc77bb4a863710dc851aec22738719639a3c21fe683a618

OperationCounterSnapshotSchemaV1.counter_schema_id =
  5181eb89788d511ffeb2ccc65264b81e9e0d3ae977043820524f8b08dfa58fc3
```

| checkpoint marker | exact applicable-operation array |
|---|---|
| `ACK_DEADLINE_NOT_DUE` | `[ACK_DEADLINE_EXPIRY]` |
| `ACK_DEADLINE_TERMINAL_CONVERGED` | `[ACK_DEADLINE_EXPIRY]` |
| `DISPATCH_RETURN_READY` | `[SUBSCRIPTION_DISPATCH]` |
| `INGRESS_RETURN_READY` | `[INGRESS]` |
| `KERNEL_SEND_RESULT_CONVERGED` | `[SUBSCRIPTION_DISPATCH]` |
| `LOCAL_CLOSE_DISPATCH_CONVERGED` | `[LOCAL_SHUTDOWN]` |
| `OUTBOUND_ARTIFACTS_PREPARED` | `[SUBSCRIPTION_DISPATCH]` |
| `PARSER_UNIT_CONVERGED` | `[INGRESS]` |
| `RAW_PREFIX_COMMITTED` | `[INGRESS]` |
| `SHUTDOWN_TERMINAL_CONVERGED` | `[LOCAL_SHUTDOWN]` |
| `TARGET_ESCAPE_OBSERVED` | `[ACK_DEADLINE_EXPIRY, INGRESS, LOCAL_SHUTDOWN, SUBSCRIPTION_DISPATCH]` |
| `TCP_HALF_CLOSE_CONVERGED` | `[LOCAL_SHUTDOWN]` |
| `TLS_CONTROL_CONVERGED` | `[LOCAL_SHUTDOWN]` |

The arrays in the final row use lexical enum-value order. Composite literals
recursively validate their nested Type-28/29/30/31/33/34/36/37/38/39
dependencies before equality. No dependency returns to Types 18, 24, or 25,
so the combined rule/literal DAG remains acyclic. Generic semantic-ID
recomputation is still mandatory; an additional
`identity_field == known_golden_hash` rule is redundant once every payload
member is exact and is therefore forbidden.

Descriptor-level exact-key validation, scalar/member validation, semantic-ID
recomputation, canonical round-trip, and codec bounds are mandatory generic
registry evaluation steps. They are committed by
`ExternalTypeDescriptorV2`, `MemberDescriptorV2`, and `ValueSchemaV2` and are
not duplicated as 49 byte-bound plus 16 identity expression rules.

`step2_cross_field_rule_descriptor_id` is the semantic SHA-256 of all
preceding rule members, including the complete ordered expression array,
under:

```text
domain =
  RiskYieldMMA2MStep2CrossFieldRuleDescriptorV2V4_9F_RawV8
```

`rule_id` is the unique stable symbolic name used by
`ordered_intrinsic_rule_ids` and `RuleApplicationDescriptorV2.rule_id`.
Exactly one rule descriptor has each `rule_id`. The terminal semantic
descriptor ID identifies the complete descriptor bytes and is used only for
catalog ordering, registry identity, and mutation detection. A symbolic
`rule_id` is never compared with, or substituted for, a
`step2_cross_field_rule_descriptor_id`.

`ordered_intrinsic_rule_ids` in each concrete descriptor contains every rule
whose scope is `INTRINSIC_RECORD` for that type. A rule ID without its typed
descriptor, or a typed descriptor not attached or applied anywhere, rejects.

## 10. Cross-record and bounded array-each applications

Rules whose truth requires more than the currently constructed object are
not mislabeled intrinsic. A `RuleApplicationDescriptorV2` has exact order:

```text
application_name
rule_id
application_kind
ordered_root_input_bindings
ordered_sequence_input_bindings
iteration_ordinal_binding_name
maximum_rule_evaluations
requires_equal_cardinality
evaluation_order
rule_application_id
```

`application_name` is the unique slash-delimited ASCII key shown in the exact
application ledger below. It is part of the semantic-ID preimage. Application
catalog order and multi-application evaluation order use
`application_name`, never the opaque hash ID.

`application_kind` is exactly:

```text
RECORD_TUPLE
ARRAY_EACH
FOR_EACH_FIXED_POSITION_BINDING
FIXED_SEQUENCE_AGGREGATE
```

A root input binding has exact order:

```text
binding_name
tuple_position
expected_type_name
```

Every root input is one complete caller-supplied `RECORD` binding and its
type is one of the 49 concrete graph records. Tuple positions start at one
and are contiguous.

A sequence input binding has exact order:

```text
binding_name
binding_mode
source_kind
source_root_binding_name
embedded_array_typed_member_path
fixed_position_resolver_profile_id
expected_item_type_name
```

`binding_mode` is `ITERATED_RECORD`, `COMPLETE_RECORD_SEQUENCE`, or
`OPTIONAL_RECORD`. `source_kind` is `EMBEDDED_ARRAY` or
`EXTERNAL_FIXED_SEQUENCE`. Binding names are unique across roots, sequences,
and the optional ordinal binding.

- `EMBEDDED_ARRAY` requires `ITERATED_RECORD`, a nonempty statically resolved
  path to a bounded `ARRAY` of non-null `OBJECT_REF` items of the exact
  expected type, and a null resolver ID.
- `EXTERNAL_FIXED_SEQUENCE` requires an empty embedded path and one exact
  resolver. The resolver root/item types must match the named root and
  expected item type.
- `ITERATED_RECORD` becomes one effective `RECORD` rule binding per ordinal.
- `COMPLETE_RECORD_SEQUENCE` becomes one effective
  `FIXED_RECORD_SEQUENCE` binding whose exact array schema uses the resolver's
  minimum/maximum and item type.
- `OPTIONAL_RECORD` requires a resolver with minimum zero and maximum one and
  becomes one effective `OPTIONAL_FIXED_RECORD` binding whose exact value
  schema is a nullable object reference to the resolved item type.

For `RECORD_TUPLE`:

- there are at least two root bindings;
- `ordered_sequence_input_bindings` is empty,
  `iteration_ordinal_binding_name` is null,
  `maximum_rule_evaluations` is exactly one, and
  `requires_equal_cardinality` is false;
- `evaluation_order` is `SINGLE_EVALUATION`;
- the caller supplies the complete explicitly typed tuple;
- validation rejects a missing, extra, reordered, or wrong-type record.

For `ARRAY_EACH`:

- there is at least one root and at least one sequence binding;
- every sequence has mode `ITERATED_RECORD` and source
  `EMBEDDED_ARRAY`;
- `iteration_ordinal_binding_name` is a distinct non-null `SAFE_UINT`
  binding;
- `maximum_rule_evaluations` is positive and exactly equals the minimum of
  all resolved embedded-array maxima. A smaller cap would reject structurally
  legal rows and a larger cap would lack a source-derived bound, so either
  rejects;
- when more than one sequence is bound, `requires_equal_cardinality` is true;
  unequal materialized cardinalities reject before the first iteration; one
  bound sequence requires the flag false;
- `evaluation_order` is
  `LEXICAL_APPLICATION_NAME_THEN_SEQUENCE_ORDINAL`;
- evaluation zips all bound sequences by ordinal, binds the same ordinal from
  every source plus the ordinal binding, and evaluates in order from zero;
- evaluation count equals the common materialized cardinality and cannot
  exceed `maximum_rule_evaluations`;
- an unbounded array, absent item schema, item-type mismatch, off-by-one
  maximum, nested implicit loop, truncating zip, or hidden Cartesian product
  rejects.

`FOR_EACH_FIXED_POSITION_BINDING` has the same bounded zipped semantics as
`ARRAY_EACH` but requires at least one
`EXTERNAL_FIXED_SEQUENCE` sequence binding; embedded arrays may be zipped
with it, but an application containing only embedded arrays must use
`ARRAY_EACH`. Every sequence binding has mode `ITERATED_RECORD`. An external
binding requires an empty embedded path and a non-null exact resolver profile.
This makes the two encodings disjoint. A fixed resolver's maximum participates
in the same exact minimum used for `maximum_rule_evaluations`.

`FIXED_SEQUENCE_AGGREGATE` has at least one root and at least one sequence
binding, all sequence bindings use `EXTERNAL_FIXED_SEQUENCE`, and every mode
is `COMPLETE_RECORD_SEQUENCE` or `OPTIONAL_RECORD`. Its ordinal binding is
null, `maximum_rule_evaluations` is exactly one,
`requires_equal_cardinality` is false, and `evaluation_order` is
`SINGLE_EVALUATION`. The complete resolved sequence or optional record is
bound before the rule evaluates once. It is not equivalent to executing zero
or more per-item rules and cannot silently discard the empty optional case.

A `FixedPositionResolverProfileV2` has exact logical members:

```text
profile_name
source_root_type_name
ordered_source_identity_path_descriptors
resolved_item_type_name
minimum_items
maximum_items
resolution_semantics
fixed_position_resolver_profile_id
```

The terminal ID hashes the preceding members under
`RiskYieldMMA2MStep2FixedPositionResolverProfileV2V4_9F_RawV8`.
`resolution_semantics` is exactly
`CALLER_SUPPLIED_COMPLETE_RECORDS_ID_MATCH_IN_SOURCE_ORDER`; the resolver
performs no I/O. It accepts a caller-supplied complete record tuple only when
its cardinality is in range, every record has the exact resolved type, and
each recomputed identity positionally equals the identity obtained from the
root's ordered source paths. Missing, extra, reordered, hash-only, lazily
loaded, or stale records reject.

Each source identity path descriptor has exact logical members:

```text
path_position
typed_member_path
result_kind
null_semantics
```

`result_kind` is `ARRAY`, `REQUIRED_SCALAR`, or `OPTIONAL_SCALAR`.
`ARRAY` and `REQUIRED_SCALAR` use `null_semantics = REJECT_NULL`;
`OPTIONAL_SCALAR` uses `null_semantics = NULL_TO_EMPTY_SEQUENCE`. Path
positions start at one and are contiguous. An `ARRAY` contributes IDs in
array order; either scalar contributes one ID; an optional null contributes
zero. Multiple path results are concatenated in path-position order, with no
sorting or deduplication, and the combined sequence must satisfy the profile
minimum/maximum.

For every external sequence binding, its root binding's
`expected_type_name` equals the resolver's `source_root_type_name`, and its
`expected_item_type_name` equals the resolver's
`resolved_item_type_name`. Each `ARRAY` source path resolves to an array whose
non-null item schema equals the non-null identity-field schema of the resolved
record. Each scalar source path resolves to that same identity-field schema;
its nullability is false for `REQUIRED_SCALAR` and true for
`OPTIONAL_SCALAR`. Any differently typed, multiply nullable, or coercible
path rejects before caller-supplied records are inspected.

The root-observation resolver has one `ARRAY` path
`["ordered_observation_ids"]`. The selector resolver has one
`OPTIONAL_SCALAR` path `["full_checkpoint_selector_id"]`; null resolves to an
empty sequence and non-null resolves to exactly one complete selector.

The exact two resolver records are:

```json
{
  "profile_name": "RAW_V8_V2_ROOT_OBSERVATION_RESOLVER_V1",
  "source_root_type_name": "TargetObservationRootV2",
  "ordered_source_identity_path_descriptors": [
    {
      "path_position": 1,
      "typed_member_path": ["ordered_observation_ids"],
      "result_kind": "ARRAY",
      "null_semantics": "REJECT_NULL"
    }
  ],
  "resolved_item_type_name": "TargetObservationV2",
  "minimum_items": 1,
  "maximum_items": 67,
  "resolution_semantics": "CALLER_SUPPLIED_COMPLETE_RECORDS_ID_MATCH_IN_SOURCE_ORDER",
  "fixed_position_resolver_profile_id": "87224ef058fff2867da671aec58d53c0a06fc9542ae84ad0378af6db48349daf"
}
```

```json
{
  "profile_name": "RAW_V8_V2_ROOT_SELECTOR_RESOLVER_V1",
  "source_root_type_name": "TargetObservationRootV2",
  "ordered_source_identity_path_descriptors": [
    {
      "path_position": 1,
      "typed_member_path": ["full_checkpoint_selector_id"],
      "result_kind": "OPTIONAL_SCALAR",
      "null_semantics": "NULL_TO_EMPTY_SEQUENCE"
    }
  ],
  "resolved_item_type_name": "CheckpointSelectorV1",
  "minimum_items": 0,
  "maximum_items": 1,
  "resolution_semantics": "CALLER_SUPPLIED_COMPLETE_RECORDS_ID_MATCH_IN_SOURCE_ORDER",
  "fixed_position_resolver_profile_id": "73acbeea28d638acb77aab44dad201e08cc5267e830ddd4714d54aa70813b54b"
}
```

The registry catalog order is the lexical order of the terminal semantic IDs:
selector resolver `73ac...54b`, then observation resolver `8722...daf`.

For iterated applications, short-circuiting after a failure is permitted only
after the failing `application_name`, `rule_application_id`, and ordinal have
been recorded. Candidate evaluation counts are charged before predicate
evaluation. Single-evaluation applications record both their name and ID
before predicate evaluation.

The deterministic application-validation result coordinate has exact members
`application_name, rule_application_id, rule_id, iteration_ordinal,
failure_class`. `iteration_ordinal` is null for a single evaluation.
`failure_class` is exactly `BUSINESS_RULE_FALSE`, `MALFORMED_OPERAND`,
`UNRESOLVED_AUTHORITY`, `TYPE_OR_UNION_MISMATCH`, `IMPOSSIBLE_BRANCH`, or
`WORK_BOUND_EXCEEDED`; it is null on acceptance. This coordinate is validator
evidence, not a new runtime graph record or a license for ambient logging
state.

On acceptance there is no failing candidate: both `iteration_ordinal` and
`failure_class` are null for every application kind, and `rule_id` is the
application's referenced cross rule. Per-ordinal success evidence belongs in
the ordered rule-step evidence, not in the result coordinate. The coordinate
is always present; an absent coordinate is not an alternative encoding of
acceptance.

**Application-orchestration clarification (2026-07-29):** the complete
application executor owns the following order. It first converts every
caller-supplied root and external record into a private exact-I-JSON snapshot,
validates the complete declared record graph, and executes every attached
intrinsic rule in dependency post-order, nested occurrences before their
containing record. Only then may it run a fixed-position resolver or a
cross-record rule. The caller cannot claim that a record was prevalidated.
Production adapters must create the snapshot while they own their mutable
source object; the independent evaluator never retains or rereads the caller's
object.

An intrinsic false root or intrinsic evaluation failure rejects the
application before resolver or cross-rule work. Its coordinate uses the exact
failing intrinsic `rule_id`. A resolver, cardinality, binding-ledger, or other
setup failure uses the application's referenced cross `rule_id`. For any
failure before the first cross-rule candidate is charged,
`iteration_ordinal = null` and the charged cross-rule evaluation count is
zero, including failures discovered in a record that would later have become
an iterated element. Once iteration begins, a false or failed cross rule uses
the current zero-based ordinal; a single-evaluation cross rule retains null.
An intrinsic false root and a cross-rule false root both map to
`BUSINESS_RULE_FALSE`; the `rule_id` distinguishes their source.

Every nested occurrence is a logical intrinsic evaluation and is charged
before any cache lookup. After that occurrence's children have been traversed,
an application-local accepted-only cache may suppress a duplicate physical
execution only for the same exact type, intrinsic rule ID, and canonical
bytes. Digest equality without retained canonical-byte equality is
insufficient. Failures are never cached; a cached parent never suppresses
child traversal; caches never cross application calls; and evidence records
logical attempts, physical executions, and cache hits separately.

Runtime `MalformedValue` and `ConstraintViolation` map to
`MALFORMED_OPERAND`; `TypeMismatch` maps to
`TYPE_OR_UNION_MISMATCH`; `UnresolvedReference` maps to
`UNRESOLVED_AUTHORITY`. A structured union-discriminator, selected-
alternative, or concrete-body mismatch maps to `TYPE_OR_UNION_MISMATCH` even
when its rule-runtime exception retains a broader constraint/reference base
class for compatibility; mapping by exception message is forbidden.
Candidate-reachable `ImpossibleState` maps to
`IMPOSSIBLE_BRANCH`; and `WorkBoundExceeded` maps to
`WORK_BOUND_EXCEEDED`. Artifact corruption, a registry/application-plan
disagreement, unknown dispatch, or any unsupported frozen construct is an
evaluator defect and must escape as a fatal error rather than being
misreported as a candidate coordinate.

For every application, construct the complete effective binding ledger from
its root bindings (`RECORD`), iterated elements (`RECORD`), complete sequences
(`FIXED_RECORD_SEQUENCE`), optional records (`OPTIONAL_FIXED_RECORD`), and
ordinal binding (`SAFE_UINT`). The exact expected value schema is derived
from the root type, embedded array, or resolver as specified above. Its
ordered
`(binding_name, binding_kind, expected_type_name, expected_value_schema_id)`
tuple must exactly equal the referenced rule's
`ordered_rule_input_bindings`. Missing, extra, aliased, reordered,
differently typed, or differently bounded bindings reject before evaluation.
The construction order is all root bindings in
`ordered_root_input_bindings` order, followed by all sequence bindings in
`ordered_sequence_input_bindings` order, followed by the ordinal binding when
present. The ordinal uses the unique reachable non-null `SAFE_INTEGER` schema
with bounds `0..maximum_rule_evaluations-1`; no generic safe-uint alias or
one-based ordinal is permitted.

`rule_application_id` is the semantic SHA-256 of every other application
member under:

```text
domain =
  RiskYieldMMA2MStep2RuleApplicationDescriptorV2V4_9F_RawV8
```

The exact application records, already in required lexical
`application_name` order, are:

```json
[
  {
    "application_name": "APPLY/COUNTER_SNAPSHOT_SCHEMA_V1",
    "rule_id": "RULE/CROSS/COUNTER_SNAPSHOT_SCHEMA_V1",
    "application_kind": "RECORD_TUPLE",
    "ordered_root_input_bindings": [
      {
        "binding_name": "counter_snapshot",
        "tuple_position": 1,
        "expected_type_name": "OperationCounterSnapshotV1"
      },
      {
        "binding_name": "counter_schema",
        "tuple_position": 2,
        "expected_type_name": "OperationCounterSnapshotSchemaV1"
      }
    ],
    "ordered_sequence_input_bindings": [],
    "iteration_ordinal_binding_name": null,
    "maximum_rule_evaluations": 1,
    "requires_equal_cardinality": false,
    "evaluation_order": "SINGLE_EVALUATION",
    "rule_application_id": "1011bd624480ce2c9a8bf559c16e876c33fc2167857ee696fcea37cc0cb628f2"
  },
  {
    "application_name": "APPLY/FIELD_OBSERVATION_FROZEN_REGISTRY_V1",
    "rule_id": "RULE/CROSS/FIELD_OBSERVATION_FROZEN_REGISTRY_V1",
    "application_kind": "RECORD_TUPLE",
    "ordered_root_input_bindings": [
      {
        "binding_name": "field_observation",
        "tuple_position": 1,
        "expected_type_name": "TargetFieldObservationV1"
      },
      {
        "binding_name": "target_registry",
        "tuple_position": 2,
        "expected_type_name": "TargetFieldRegistryV1"
      }
    ],
    "ordered_sequence_input_bindings": [],
    "iteration_ordinal_binding_name": null,
    "maximum_rule_evaluations": 1,
    "requires_equal_cardinality": false,
    "evaluation_order": "SINGLE_EVALUATION",
    "rule_application_id": "5fcc7e2bdc01bde47d4cd57c1fb134c1da6888d9609c65ec0bfe431365965b27"
  },
  {
    "application_name": "APPLY/OPERATION_RESULT_SIGNED_SPEC_V1",
    "rule_id": "RULE/CROSS/OPERATION_RESULT_SIGNED_SPEC_V1",
    "application_kind": "RECORD_TUPLE",
    "ordered_root_input_bindings": [
      {
        "binding_name": "result",
        "tuple_position": 1,
        "expected_type_name": "CapacityMeasurementOperationResultEvidence"
      },
      {
        "binding_name": "signed_spec",
        "tuple_position": 2,
        "expected_type_name": "CapacityMeasurementOperationSpec"
      }
    ],
    "ordered_sequence_input_bindings": [],
    "iteration_ordinal_binding_name": null,
    "maximum_rule_evaluations": 1,
    "requires_equal_cardinality": false,
    "evaluation_order": "SINGLE_EVALUATION",
    "rule_application_id": "770d99b0001802ceb6bdc044b9b55ce3cfd319754e9b9716c10d0b3d2e214f18"
  },
  {
    "application_name": "APPLY/SELECTOR_MARKER_CONTRACT_V1",
    "rule_id": "RULE/CROSS/SELECTOR_MARKER_CONTRACT_V1",
    "application_kind": "RECORD_TUPLE",
    "ordered_root_input_bindings": [
      {
        "binding_name": "selector",
        "tuple_position": 1,
        "expected_type_name": "CheckpointSelectorV1"
      },
      {
        "binding_name": "marker_contract",
        "tuple_position": 2,
        "expected_type_name": "MarkerContractV1"
      }
    ],
    "ordered_sequence_input_bindings": [],
    "iteration_ordinal_binding_name": null,
    "maximum_rule_evaluations": 1,
    "requires_equal_cardinality": false,
    "evaluation_order": "SINGLE_EVALUATION",
    "rule_application_id": "30f3a8688435dff87bc5ff329e7a9dd6bbbf40c71de5dd746a4cb1e9008b3ee5"
  },
  {
    "application_name": "APPLY/V2_OBSERVATION_AGGREGATE_REGISTRY_V1",
    "rule_id": "RULE/CROSS/V2_OBSERVATION_AGGREGATE_REGISTRY_V1",
    "application_kind": "RECORD_TUPLE",
    "ordered_root_input_bindings": [
      {
        "binding_name": "observation",
        "tuple_position": 1,
        "expected_type_name": "TargetObservationV2"
      },
      {
        "binding_name": "target_registry",
        "tuple_position": 2,
        "expected_type_name": "TargetFieldRegistryV1"
      }
    ],
    "ordered_sequence_input_bindings": [],
    "iteration_ordinal_binding_name": null,
    "maximum_rule_evaluations": 1,
    "requires_equal_cardinality": false,
    "evaluation_order": "SINGLE_EVALUATION",
    "rule_application_id": "0fff77cbc03f9fcf019e8352875d9b7f49a3ab8a0ed374e9d5b9bb2f7f9a38fb"
  },
  {
    "application_name": "APPLY/V2_OBSERVATION_FIELDS_REGISTRY_V1",
    "rule_id": "RULE/CROSS/V2_OBSERVATION_FIELD_REGISTRY_V1",
    "application_kind": "ARRAY_EACH",
    "ordered_root_input_bindings": [
      {
        "binding_name": "observation",
        "tuple_position": 1,
        "expected_type_name": "TargetObservationV2"
      },
      {
        "binding_name": "target_registry",
        "tuple_position": 2,
        "expected_type_name": "TargetFieldRegistryV1"
      }
    ],
    "ordered_sequence_input_bindings": [
      {
        "binding_name": "field_observation",
        "binding_mode": "ITERATED_RECORD",
        "source_kind": "EMBEDDED_ARRAY",
        "source_root_binding_name": "observation",
        "embedded_array_typed_member_path": ["field_observations"],
        "fixed_position_resolver_profile_id": null,
        "expected_item_type_name": "TargetFieldObservationV1"
      },
      {
        "binding_name": "field_descriptor",
        "binding_mode": "ITERATED_RECORD",
        "source_kind": "EMBEDDED_ARRAY",
        "source_root_binding_name": "target_registry",
        "embedded_array_typed_member_path": ["descriptors"],
        "fixed_position_resolver_profile_id": null,
        "expected_item_type_name": "CapacityMeasurementTargetFieldDescriptorV1"
      }
    ],
    "iteration_ordinal_binding_name": "field_ordinal",
    "maximum_rule_evaluations": 185,
    "requires_equal_cardinality": true,
    "evaluation_order": "LEXICAL_APPLICATION_NAME_THEN_SEQUENCE_ORDINAL",
    "rule_application_id": "87b0ee70e1eab470868e357facd3bb6eb203ce4ed8363cbd6fa30a6ee86c8d63"
  },
  {
    "application_name": "APPLY/V2_ROOT_OBSERVATION_MEMBERSHIP_V1",
    "rule_id": "RULE/CROSS/V2_ROOT_OBSERVATION_MEMBERSHIP_V1",
    "application_kind": "FOR_EACH_FIXED_POSITION_BINDING",
    "ordered_root_input_bindings": [
      {
        "binding_name": "root",
        "tuple_position": 1,
        "expected_type_name": "TargetObservationRootV2"
      }
    ],
    "ordered_sequence_input_bindings": [
      {
        "binding_name": "observation",
        "binding_mode": "ITERATED_RECORD",
        "source_kind": "EXTERNAL_FIXED_SEQUENCE",
        "source_root_binding_name": "root",
        "embedded_array_typed_member_path": [],
        "fixed_position_resolver_profile_id": "87224ef058fff2867da671aec58d53c0a06fc9542ae84ad0378af6db48349daf",
        "expected_item_type_name": "TargetObservationV2"
      }
    ],
    "iteration_ordinal_binding_name": "observation_ordinal",
    "maximum_rule_evaluations": 67,
    "requires_equal_cardinality": false,
    "evaluation_order": "LEXICAL_APPLICATION_NAME_THEN_SEQUENCE_ORDINAL",
    "rule_application_id": "0737d82dae748ff1bf3b19230be2196973c7d6d0fa6c97ef834e9517e09e5f0a"
  },
  {
    "application_name": "APPLY/V2_ROOT_SELECTOR_LIFECYCLE_V1",
    "rule_id": "RULE/CROSS/V2_ROOT_SELECTOR_LIFECYCLE_V1",
    "application_kind": "FIXED_SEQUENCE_AGGREGATE",
    "ordered_root_input_bindings": [
      {
        "binding_name": "root",
        "tuple_position": 1,
        "expected_type_name": "TargetObservationRootV2"
      }
    ],
    "ordered_sequence_input_bindings": [
      {
        "binding_name": "observations",
        "binding_mode": "COMPLETE_RECORD_SEQUENCE",
        "source_kind": "EXTERNAL_FIXED_SEQUENCE",
        "source_root_binding_name": "root",
        "embedded_array_typed_member_path": [],
        "fixed_position_resolver_profile_id": "87224ef058fff2867da671aec58d53c0a06fc9542ae84ad0378af6db48349daf",
        "expected_item_type_name": "TargetObservationV2"
      },
      {
        "binding_name": "selector",
        "binding_mode": "OPTIONAL_RECORD",
        "source_kind": "EXTERNAL_FIXED_SEQUENCE",
        "source_root_binding_name": "root",
        "embedded_array_typed_member_path": [],
        "fixed_position_resolver_profile_id": "73acbeea28d638acb77aab44dad201e08cc5267e830ddd4714d54aa70813b54b",
        "expected_item_type_name": "CheckpointSelectorV1"
      }
    ],
    "iteration_ordinal_binding_name": null,
    "maximum_rule_evaluations": 1,
    "requires_equal_cardinality": false,
    "evaluation_order": "SINGLE_EVALUATION",
    "rule_application_id": "86a3acbf53805768a1a462fe28c75a7e7192487f71579ba021aa03d7992a9a42"
  }
]
```

The result/spec tuple uses `OPERATION_RESULT_MATCHES_SIGNED_SPEC`.
Selector/marker-contract and field/registry tuples prevent hidden global
catalog access. The field/registry tuple derives the unique descriptor from
the supplied registry and requires both
`FIELD_OBSERVATION_SATISFIES_DESCRIPTOR_POLICY` and
`TARGET_VALUE_SATISFIES_DESCRIPTOR`; it does not need a caller-authored third
root binding. Counter snapshot/schema validates the supplied frozen schema
authority. Root observation membership uses the root-observation resolver and
binds one complete observation plus ordinal at a time. It verifies resolver
identity membership and that each observation's `candidate_id`, `attempt_id`,
`operation_kind`, `instrumentation_mode`, and `target_field_registry_id`
equal the root at that ordinal. `APPLY/V2_OBSERVATION_FIELDS_REGISTRY_V1`
zips the exact 185 embedded field records with the exact 185 registry
descriptors and rejects unequal cardinality before ordinal zero. At each
ordinal it applies the same descriptor/value policy plus
`V2_FIELD_OBSERVATION_CONTEXT_VALID` for field/descriptor positional
identity, placeholder-reason mapping, contextual
availability/method/role/checkpoint policy, and observer-span containment.
`APPLY/V2_OBSERVATION_AGGREGATE_REGISTRY_V1` validates only
the named three-field A1 FIFO aggregate relation that cannot be reduced to
independent field iterations. Root selector lifecycle uses one complete
`1..67` observation sequence and one
optional `0..1` selector record, both identity-bound by their resolvers, so
the empty-selector branch is evaluated rather than skipped.

The aggregate lifecycle application intentionally rechecks the root count,
ordered recomputed observation identities, and the same five root/observation
context equalities before selecting a lifecycle branch. This is bounded
defense in depth, not an alternative authority: root membership and lifecycle
must both pass, use the same exact resolver and comparison semantics, and any
disagreement between their evidence is a registry/evaluator conformance
failure. The membership application supplies ordinal-local failure evidence;
the lifecycle application supplies whole-sequence branch evidence.

Complete-record relationships already serialized inside one record—such as
declaration/spec, due-clock/dispatch, subscription-result/dispatch,
and ACK-result/due-clock—remain `INTRINSIC_RECORD` rules with statically
resolved `OBJECT_REF` paths. V2 observation/context identity equality is
intrinsic only where the complete relationship is serialized within one
record; root/observation equality is not intrinsic. Field/descriptor
positional equality, contextual availability, placeholder mapping, and
observer-span containment are assigned only to the fields ARRAY_EACH
application. A1 FIFO is assigned only to the aggregate application. None is
duplicated by an observation intrinsic rule. Tagged wrapper/body selection is
enforced only by the three union descriptors.

The complete application ledger is part of registry identity and cannot be
inferred at runtime.

## 11. Constructive maximum witnesses

The codec admission ceiling and the analytic maximum are separate facts. A
codec bound is accepted only with a constructive legal maximum witness and an
independent proof that no legal value serializes larger. The proof may show a
maximum far below a coarse codec ceiling; that is expected and does not
contradict the codec.

The proof is compositional but cannot be a minimum/maximum interval argument.
For each scope it computes a sound attainable-length frontier, preserving every
gap, residue class, and ancestor-observable semantic state needed by a selected
rule or application; intersects that frontier with every nested descriptor
ceiling and any owner ceiling; applies the exact intrinsic/application-rule
transfers or an explicitly labelled safe upper-domain relaxation; and retains a
legal witness that attains the surviving upper endpoint. Dropping a constraint
may be sound for an upper bound. Narrowing the legal domain without proof is
not. The existing V3 codec ceilings remain production admission behavior;
neither an analytic maximum nor its slack silently tightens a codec.

For every one of the 49 concrete records, and for every alternative of each
union, the independent generator emits:

```text
artifact_version
canonicalization_version
measurement_schema_version
maximum_protocol_sha256
maximum_context_object_manifest_id
maximum_witness_id
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
ordered_component_choice_evidence
upper_bound_certificate
```

`constraint_scope` is exactly `INTRINSIC_TYPE`, `FROZEN_ROOT_APPLICATION`, or
`FROZEN_FIXTURE`. `constraint_scope_id` commits the complete rule/application
or fixture-constraint universe used by the optimizer.
`constraint_scope_profile_id` is null for `INTRINSIC_TYPE` and otherwise
names one of the exact 408 V3 profiles in Section 11.2. Rows with the same
type but a different constraint universe are distinct; silently presenting a
fixture-constrained maximum as the intrinsic type maximum rejects.

`witness_kind` is `CONSTRUCTIVE_LEGAL_MAXIMUM`. The record must round-trip
through the independent schema, recompute all semantic IDs, satisfy every
intrinsic rule, and satisfy the declared `LE` or `LT` bound. It cannot be a
truncated near-bound blob, padding field, unknown key, noncanonical JSON, or
invalid value retained only to inflate bytes.

For an accepted row:

```text
canonical_byte_length = certified_analytic_maximum_octets

LE:
  certified_analytic_maximum_octets <= codec_octet_limit
  codec_slack_octets =
    codec_octet_limit - certified_analytic_maximum_octets

LT:
  certified_analytic_maximum_octets < codec_octet_limit
  codec_slack_octets =
    codec_octet_limit - certified_analytic_maximum_octets - 1
```

A witness is required to reach the certified analytic maximum, not the codec
ceiling. A generator-selected tighter analytic maximum does not silently
tighten the production codec.

Maximum construction works in reverse topological order:

1. Enumerate every literal and enum choice; choose by complete canonical byte
   contribution, not by source-string length.
2. Solve each Unicode profile under both scalar-count and UTF-8-octet limits,
   including JSON escape expansion, and retain the exact maximizing string.
3. Optimize each complete array jointly at every legal cardinality up to its
   maximum. Repeated independent maximum items are permitted only when the
   exact array and enclosing rules allow them. Uniqueness, ordering,
   per-position identities, cross-array cardinality, and coupled member
   relations require retained per-position choices and a joint upper-bound
   certificate.
4. Enumerate every nullable branch rather than assuming non-null is larger.
5. Enumerate all union alternatives.
6. Solve coupled safe-integer constraints with an exact bounded optimizer or
   exhaustive boundary-candidate set whose completeness is proved in the
   witness evidence.
7. Recompute outer identities after all inner maxima are fixed.

If the solver cannot prove maximality, the record is not certified. A Boolean
`maximum_proved = true` without the constructive record and choice trace is
invalid.

### 11.1 Exact maximum row universe and order

The maximum artifact contains exactly 474 byte-maximum rows:

```text
49 concrete RECORD descriptors
+ 4 operation-spec union alternatives
+ 4 operation-result union alternatives
+ 9 target-value union alternatives
= 66 INTRINSIC_TYPE rows

+ 4 FROZEN_FIXTURE outer operation-result rows

+ 4 FROZEN_ROOT_APPLICATION non-checkpoint operation rows
+ 80 exact selector positions * 5 checkpoint outcomes
= 404 FROZEN_ROOT_APPLICATION TargetObservationV2 rows

= 474 total byte-maximum rows
```

The intrinsic rows follow `ordered_external_type_descriptors`. A record emits
one row with `alternative_name = null`; a union emits one row per
`ordered_alternatives` entry and no additional synthetic union row. The four
outer-result rows use this exact operation order:

```text
ACK_DEADLINE_EXPIRY
INGRESS
LOCAL_SHUTDOWN
SUBSCRIPTION_DISPATCH
```

The four non-checkpoint observation rows use the same operation order. The
remaining 400 rows follow the V3 inventory's checkpoint-selector catalog
order, then increasing one-based selector position, then this exact outcome
order:

```text
EXACT_MARKER
ARTIFACT_BOUND_EXCEEDED
OBSERVER_INTERNAL_ERROR
SOURCE_CLOCK_UNAVAILABLE
TARGET_BOUNDARY_NOT_REACHED
```

The nine exact selectors contain 80 entries in aggregate. A missing,
duplicated, reordered, merged, or extra row rejects. These counts establish
the proof obligations only; they do not claim that any maximum has been
proved.

The one-based row positions are therefore exact: positions `1..66` are the
expanded intrinsic descriptor/alternative rows; `67..70` are the four outer
result rows; `71..74` are the four non-checkpoint root rows; and `75..474` are
the checkpoint-coordinate rows. No producer-defined secondary ordering is
permitted.

### 11.2 Constraint-scope identity and union measurement

Every row's `constraint_scope_id` is the semantic ID under:

```text
RiskYieldMMA2MStep2ExternalSchemaV2MaximumConstraintScopeV1V4_9F_RawV8
```

over this exact payload:

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

`measurement_binding` has exactly:

```text
binding_kind
validation_root_type_name
measured_value_typed_member_path
sequence_binding_name
sequence_ordinal
```

`binding_kind` is one of exactly these six forms; the remaining four members
have the stated exact values:

| Binding kind | `validation_root_type_name` | `measured_value_typed_member_path` | `sequence_binding_name` | `sequence_ordinal` |
|---|---|---|---|---|
| `SELF_RECORD` | the measured concrete record type | exact empty path | null | null |
| `SELF_UNION_VALUE` | `CapacityMeasurementTargetValue` | exact empty path | null | null |
| `OWNER_MEMBER_UNION_VALUE` | `CapacityMeasurementOperationSpec` or `CapacityMeasurementOperationResultEvidence`, as selected by the measured union | exactly `["spec"]` or `["result"]`, respectively | null | null |
| `OUTER_RESULT_RECORD` | `CapacityMeasurementOperationResultEvidence` | exact empty path | null | null |
| `ROOT_ANY_NONCHECKPOINT_OBSERVATION` | `TargetObservationRootV2` | exact empty path relative to the selected external sequence item | exact text `observations` | null |
| `ROOT_EXACT_CHECKPOINT_OBSERVATION` | `TargetObservationRootV2` | exact empty path relative to the selected external sequence item | exact text `observations` | the profile's fixed selector position, interpreted as a zero-based observation ordinal |

The 49 concrete intrinsic rows use `SELF_RECORD`. The four operation-spec
body alternatives and four operation-result body alternatives use
`OWNER_MEMBER_UNION_VALUE`; the nine target-value alternatives use
`SELF_UNION_VALUE`. Rows `67..70`, `71..74`, and `75..474` respectively use
`OUTER_RESULT_RECORD`, `ROOT_ANY_NONCHECKPOINT_OBSERVATION`, and
`ROOT_EXACT_CHECKPOINT_OBSERVATION`. A checkpoint selector position is
one-based within the selector, but it equals the selected zero-based
observation ordinal because ordinal zero is `BEFORE_OPERATION`. A
non-checkpoint row selects its ordinal only inside the retained scope context.
Treating the external observation sequence as a member of
`TargetObservationRootV2`, or changing any null/empty-path convention, rejects.

`evaluation_semantics` is exactly:

```text
FULL_GRAPH_EXACT_IJSON_INTRINSIC_DEPENDENCY_POSTORDER_THEN_LEXICAL_APPLICATION_NAME_THEN_INVOCATION_ORDINAL_V1
```

`source_inventory_sha256` means the V3 semantic `inventory_sha256` over the
compact canonical root without that member; it is not the repository file's
raw pretty-byte SHA-256. `rule_literal_authority_sha256` means the physical
SHA-256 of the complete frozen literal-authority file bytes.
`maximum_protocol_sha256` means the physical SHA-256 of the exact separate
constructive-maximum protocol document required below.

Intrinsic rows have null source inventory and profile ID. Fixture/root rows
bind the exact V3 semantic inventory SHA-256 and one pre-frozen scope-profile
ID. The structural registry ID and physical rule-literal-authority SHA-256
are present in every scope. A scope ID from a different inventory, registry,
literal authority, profile, alternative, or measurement binding rejects. A
selected maximizing root, result, role, or schedule is witness evidence and
never changes the pre-frozen constraint universe.

The V3 `operation_contracts` contains an exact
`maximum_constraint_scope_profile_catalog` with 408 records:

```text
4 OUTER_RESULT_BOUNDARY_FIXTURE
4 NON_CHECKPOINT_ROOT_FAMILY
400 CHECKPOINT_ROOT_COORDINATE
```

Each profile has exactly:

```text
profile_position
profile_kind
constraint_scope
measured_type_name
operation_kind
ordered_source_authority_pointers
ordered_source_authority_ids
selector_catalog_position | null
selector_catalog_name | null
checkpoint_selector_id | null
checkpoint_selector_entry_id | null
expected_checkpoint_marker_kind | null
expected_occurrence_index_within_kind | null
selector_position | null
checkpoint_outcome | null
checkpoint_binding_status | null
checkpoint_binding_unavailable_reason | null
checkpoint_field_unavailable_reason | null
ordered_admissible_root_families
application_schedule_formula
maximum_constraint_scope_profile_id
```

The profile ID is the semantic ID over all preceding members under:

```text
RiskYieldMMA2MStep2ExternalSchemaV2MaximumConstraintScopeProfileV1V4_9F_RawV8
```

Profile positions are contiguous one-based integers. The four result profiles
come first in Section 11.1 operation order, followed by the four
non-checkpoint profiles in that order, then the 400 checkpoint profiles in
the exact catalog/position/outcome order. The ID payload does not include the
V3 inventory SHA-256 and therefore creates no self-reference.
`ordered_source_authority_pointers` are absolute JSON pointers into the same
V3 inventory; the ID array has equal cardinality and contains each pointed
record's independently recomputed identity. A pointer outside the inventory,
a pointer to a hash-only replacement, or a profile whose pointed
bytes/identity differ rejects.

Each admissible root-family record has exactly:

```text
root_family_kind
ordered_instrumentation_mode_attempt_presence_pairs
selector_catalog_position | null
selector_catalog_name | null
checkpoint_selector_id | null
selector_length
observation_count
role_sequence_formula
ordered_measured_observation_roles
selector_present
```

Each mode/attempt pair is an exact two-member JSON array
`[instrumentation_mode, attempt_presence]`, where attempt presence is exactly
`NULL` or `NON_NULL`. Pair order is semantic and exactly the order listed
below.

The frozen families are:

- `STARTUP_RECOVERY_ONE`: null attempt, no selector, one
  `STARTUP_RECOVERY` observation, and both exact instrumentation modes;
- `ORDINARY_SELECTOR_FREE_THREE`: no selector and roles
  `BEFORE_OPERATION, AFTER_OPERATION, OPERATION_AGGREGATE`, with exact
  `(OFF, NULL)`, `(OFF, NON_NULL)`, and `(ON, NULL)` mode/attempt pairs;
- `ORDINARY_SELECTOR_BOUND`: `(ON, NON_NULL)`, one exact matching V3
  selector including an empty selector, `selector_length + 3`
  observations, and role formula
  `BEFORE_OPERATION, STABLE_CHECKPOINT * selector_length,
  AFTER_OPERATION, OPERATION_AGGREGATE`.

A non-checkpoint profile enumerates startup, selector-free, and every exact
selector-bound family for its operation. Its measured-role domain is
`STARTUP_RECOVERY` for the startup family and
`BEFORE_OPERATION, AFTER_OPERATION, OPERATION_AGGREGATE` for ordinary
families. A checkpoint profile contains exactly its selector-bound family and
fixes the selected observation to the selector entry, one-based position,
operation, expected marker/occurrence, outcome, exact binding status/context
reason, and exact mapped field reason. The checkpoint coordinate is therefore
identified by catalog position and name, selector and entry IDs, expected
marker/occurrence, position, operation, outcome, and reasons; position alone
is never sufficient. `EXACT_MARKER` has null context and field reasons. The
four unavailable outcomes use the exact status/reason mapping already frozen
in Sections 6.1 and 9.3.

`application_schedule_formula` is exactly one of:

```text
SELECTOR_FREE_2N_PLUS_2_CALLS_187N_PLUS_1_EVALS_1872N_PLUS_4_NODES_V1
SELECTOR_PRESENT_2N_PLUS_3_CALLS_187N_PLUS_2_EVALS_1872N_PLUS_7_NODES_V1
FINITE_UNION_OF_LISTED_ROOT_FAMILY_SCHEDULES_V1
OUTER_RESULT_SIGNED_SPEC_SINGLE_APPLICATION_V1
```

The non-checkpoint profile uses the finite-union formula because its
admissible families have different schedules. The selected family and
materialized schedule are retained only in `scope_witness_context`.

An owner-scoped union row measures the canonical bytes of the selected union
body, because that body is the union codec subject. Its `witness_record` is
the complete selected body. Its `scope_witness_context` is the exact
`OWNER_MEMBER` form defined in Section 11.3.

The spec-body owner is `CapacityMeasurementOperationSpec` at `["spec"]`; the
result-body owner is `CapacityMeasurementOperationResultEvidence` at
`["result"]`. The target-value union is `SELF_VALUE` with no owner. The
complete owner must validate, including its identity and codec bound. Measuring
the wrapper instead of the selected union body, or retaining only an owner
hash, rejects.

For the two owner-scoped unions, `INTRINSIC_TYPE` means the legal
owner-dispatched alternative domain defined by the union descriptor. The
owner codec bound is part of that domain even though only selected-body bytes
are measured. It is not a context-free body maximum. Consequently an
operation-result body that is valid in isolation but makes its owner reach
524,288 bytes is not a legal value in this row. This owner constraint must
appear in both the upper-bound certificate and the retained owner context.

### 11.3 Maximum artifact, row identity, and independent certificate

The required
`tests/raw_v8_step2_external_schema_v2_maximum_witnesses_v49f.json` is a
manifest, not an inline replacement for the 474 complete rows. Each row is a
separate deterministic pretty UTF-8 JSON file at:

```text
tests/raw_v8_step2_external_schema_v2_maximum_witnesses_v49f/
  context_object_manifest.json
  context_object_manifest_pages/<six-digit-one-based-page-position>.json
  context_objects/<first-two-lowercase-hex-characters>/<maximum-context-object-id>.json
  rows/<first-two-lowercase-hex-characters>/<maximum-witness-id>.json
```

Semantic IDs and canonical byte measurements use compact canonical I-JSON.
Repository row and manifest/page files use sorted keys, two-space indentation,
and one terminal LF. A context-object file is instead the exact compact
canonical I-JSON bytes of one complete standalone runtime record, with no BOM,
LF, wrapper, or trailing bytes. Every file remains strictly below 16,777,216
raw octets before decode. Each row embeds the complete `witness_record`; an
archive, compressed blob, recipe-only record, hash-only record, missing local
object, or network lookup rejects.

The former inline `ROOT_APPLICATION` context is expressly revoked. Against the
accepted application witness at
`scripts/tests/raw_v8_step2_external_schema_v2_application_witness_v49f.json`
(697,208 raw octets, SHA-256
`d2f40badc85c58965a72e52fd98bfebbd4caf3335ec5a0415a89294cc3fb3415`),
the independently materialized `ordinary_on_max64_full67` case has 67 compact
observations of 12,660,543 octets (SHA-256
`e1a8ed64c6c94d5f80624e011f474904f872211e671c89e276aa61460fc1cd9f`).
Those observations alone occupy 15,494,052 pretty octets. The former exact
inline context skeleton occupies 16,616,513 pretty octets and the former exact
row-member skeleton occupies 17,459,925 pretty octets (SHA-256
`58992e05d78332ee70e67f27c1715b2d32994728fd9bc433dd6ecb2566362390`),
682,710 octets above the exclusive file ceiling. That row skeleton used empty
choice evidence and proof, one-character application names, one-digit numeric
placeholders, and a nonmaximum selected observation, so it is a strict
understatement rather than a marginal formatting case.

The bounded replacement retains the selected `witness_record` inline, resolves
already-frozen authorities through the accepted V3 inventory, and stores only
constructed complete standalone context records in a local content-addressed
closure. Exactly these record types may be context objects:

```text
CapacityMeasurementOperationSpec             at most 4
CapacityMeasurementOperationResultEvidence   at most 4
TargetObservationRootV2                      at most 404
TargetObservationV2                          at most 26,664
total                                        at most 27,076
```

The observation bound is `404 * 66`: a root profile has at most 67
observations and exactly one selected observation remains inline as the row
witness. Every permitted type is a V3 `STANDALONE` descriptor with a non-null
identity field. A context record independently passes exact structural,
scalar, intrinsic-rule, identity, canonical-round-trip, and codec validation.
Cross-record and root-profile applications execute only after the complete
context has been reconstructed.

`validate_type` success alone is not standalone legality: after strict
canonical decode and typed graph/schema/codec validation, the verifier
recomputes the standalone identity and executes every reachable attached
intrinsic rule in dependency postorder with `require_true`. Only that complete
result may be cached as intrinsically valid. Row-specific cross-record
applications still execute fresh under the row schedule.

That closure-ingest cache is artifact-integrity evidence only. It never
satisfies or skips the unchanged application executor's phase-three intrinsic
walk. Every ordered row application invocation retains its own accepted-only
cache and reexecutes graph/intrinsic checks exactly as Section 11.4 requires;
no closure cache crosses an invocation or row boundary or changes reported
work semantics.

The context-object semantic ID domain is:

```text
RiskYieldMMA2MStep2ExternalSchemaV2MaximumContextObjectV1V4_9F_RawV8
```

Its exact identity payload is:

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

`record` is the complete decoded mapping loaded from the compact object file;
it is part of ID computation even though it is not duplicated in a catalog
entry. The identity field/name/value must equal the exact descriptor and its
independently recomputed semantic identity. The object file's raw count/hash
equal the record's compact-canonical count/hash. Because the four permitted
codec ceilings are respectively `LE 2,097,152`, `LT 524,288`, `LE 8,192`, and
`LT 262,144`, every object file is independently bounded. Object records do
not contain artifact references, so the artifact reference closure is one
level deep.

Every artifact-level `source_inventory_sha256` in the context catalog and its
objects equals the accepted V3 semantic inventory identity, including objects
used only by intrinsic rows. That is closure provenance, not an enlargement of
the intrinsic constraint scope: the intrinsic row's
`constraint_scope_id.source_inventory_sha256` remains null as Section 11.2
requires.

`MaximumRecordReferenceV1` is a finite tagged union. Its semantic ID domain is:

```text
RiskYieldMMA2MStep2ExternalSchemaV2MaximumRecordReferenceV1V4_9F_RawV8
```

Each form ends with `maximum_record_reference_id`, computed over every
preceding member in the order below:

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

V3_INVENTORY_POINTER:
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

A `WITNESS_RECORD` resolves only to the row's complete inline witness. A
`CONTEXT_OBJECT` resolves through the accepted context catalog to one exact
complete local object. A `V3_INVENTORY_POINTER` resolves through the once-read,
independently validated V3 inventory whose semantic `inventory_sha256` equals
`source_inventory_sha256`. The verifier derives, rather than trusts, the
permitted pointer from the row's exact scope profile. Its closed surfaces are:

```text
/fixture_records/operation_specs/<operation-kind>
/target_field_registry
/marker_contract
/checkpoint_selector_catalog/<zero-based-index>/selector
```

The pointer must occur at the corresponding position in the profile's paired
`ordered_source_authority_pointers`/`ordered_source_authority_ids`; complete
decoded-record equality, type, canonical bytes, and recomputed identity are
then checked. Copying a frozen authority into a context object, pointing a
constructed context record into V3, or accepting a hash without the complete
resolved record rejects.

The row identity domain is:

```text
RiskYieldMMA2MStep2ExternalSchemaV2MaximumWitnessV1V4_9F_RawV8
```

The exact row `artifact_version` is:

```text
riskyieldmm.raw_v8_step2_external_schema_v2.maximum_witness.v1
```

`maximum_witness_id` is the semantic ID over every Section 11 row member
except itself, in the exact order printed there.
`maximum_context_object_manifest_id` is the same accepted root catalog ID in
all 474 rows, including rows with no context-object reference; this makes each
row's resolution authority explicit without placing row IDs or reference
counts back into the catalog. `scope_witness_context` is null only for an
intrinsic concrete record. Its closed non-null forms are:

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

`OWNER_MEMBER.owner_record_reference` is `CONTEXT_OBJECT`, and the selected
member at the exact payload path byte-equals the compact canonical
`witness_record`; the owner tag/alternative dispatch, identity, intrinsic
rules, and owner codec all validate. `OUTER_RESULT_APPLICATION` uses a
`WITNESS_RECORD` result reference and the profile's exact
`V3_INVENTORY_POINTER` operation spec; no supporting-record array exists for
the four current applications. `ROOT_APPLICATION` uses a `CONTEXT_OBJECT`
root, null or profile-permitted `V3_INVENTORY_POINTER` selector, and exact V3
registry/marker pointers. Its ordered observation references contain exactly
one `WITNESS_RECORD` at `measured_sequence_ordinal`; every other item is a
`CONTEXT_OBJECT`. Their length equals the selected family's observation count,
their recomputed IDs equal the root's ordered ID sequence positionally, and
the root identity recomputes. `selected_root_family_position` is one-based;
the measured sequence and invocation ordinals are zero-based.

An application invocation has
exactly `application_name, application_invocation_ordinal,
bound_observation_ordinal`; ordinals are zero-based, and the bound ordinal is
null for non-per-observation applications. The verifier reconstructs each
typed application input from retained complete bytes and executes the exact
ordered invocation list. During one row verification, each resolved record's
bytes are retained and never reopened. A substituted selected record, missing
observation, reordered reference, root ID, record hash, or application summary
in place of complete locally resolved context rejects.

Context objects are sorted strictly by `maximum_context_object_id`, assigned
contiguous one-based global positions, deduplicated by exact ID/content, and
partitioned into consecutive ordinal pages of at most 1,024 entries. Page
positions are contiguous one-based integers. Under the exact V1 entry schema,
the independently recomputed maximum-width 1,024-entry pretty page is 815,805
raw octets; every page additionally must be at most 1,048,576 raw octets. The
27,076-object type bound therefore permits at most 27 pages. A page is the
longest remaining consecutive prefix satisfying both caps, so page boundaries
are producer-independent. A monolithic object catalog, hash-prefix-derived
page cardinality, empty page, or alternative partition rejects.

A context-object page has exactly:

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

Its version and identity domain are respectively:

```text
riskyieldmm.raw_v8_step2_external_schema_v2.maximum_context_object_page.v1
RiskYieldMMA2MStep2ExternalSchemaV2MaximumContextObjectPageV1V4_9F_RawV8
```

The page ID covers every preceding member. Each entry has exactly:

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

Positions and IDs are strictly increasing across page boundaries. Object paths
are exactly the hash-prefix path printed above; the shard prefix equals the
first two lowercase hexadecimal ID characters. Counts and hashes are verified
before decode, and `raw_octet_count = record_canonical_byte_length` and
`raw_sha256 = record_canonical_sha256`.

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

Its version and identity domain are respectively:

```text
riskyieldmm.raw_v8_step2_external_schema_v2.maximum_context_object_manifest.v1
RiskYieldMMA2MStep2ExternalSchemaV2MaximumContextObjectManifestV1V4_9F_RawV8
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

Page paths are exactly
`tests/raw_v8_step2_external_schema_v2_maximum_witnesses_v49f/context_object_manifest_pages/<six-digit-page-position>.json`.
`context_object_page_entry_limit` and
`context_object_page_raw_octet_limit` are exactly 1,024 and 1,048,576. The
root manifest ID covers every preceding member. Every listed object is
referenced by at least one row; every row context-object reference resolves one
listed object; and no missing, extra, orphaned, wrong-type, stale, duplicated,
or alternate-path object/page is permitted. Page and root
`total_context_object_octets` values are checked-UInt128 sums of object raw
counts and are recomputed while streaming. The exact type/count ceilings imply
an absolute compact-object bound of 7,003,576,276 octets, but that theoretical
bound is not a practical publication budget. The maximum protocol must freeze
a smaller pilot-supported aggregate closure budget; exceeding it is artifact
NO-GO rather than permission to allocate the theoretical maximum.

The manifest identity domain is:

```text
RiskYieldMMA2MStep2ExternalSchemaV2MaximumWitnessManifestV1V4_9F_RawV8
```

The manifest has exactly:

```text
artifact_version
canonicalization_version
measurement_schema_version
maximum_protocol_sha256
source_inventory_sha256
external_schema_registry_id
rule_literal_authority_sha256
maximum_context_object_manifest_id
context_object_manifest_repository_relative_path
context_object_manifest_raw_octet_count
context_object_manifest_raw_sha256
row_count
ordered_row_entries
maximum_witness_manifest_id
```

Its `artifact_version` is
`riskyieldmm.raw_v8_step2_external_schema_v2.maximum_witness_manifest.v1`.
The manifest ID is the semantic ID over the preceding members in that order;
`row_count` is exactly 474. The context-manifest path is exactly
`tests/raw_v8_step2_external_schema_v2_maximum_witnesses_v49f/context_object_manifest.json`;
its semantic ID, raw count, and raw SHA-256 are validated before resolving a
row reference.

Manifest entries have exactly:

```text
row_position
maximum_witness_id
constraint_scope
type_name
alternative_name
repository_relative_path
raw_octet_count
raw_sha256
```

and follow the row order in Section 11.1. The independent verifier recomputes
every row/scope/manifest identity, validates every retained witness through
the complete registry runtime, and independently checks the closed
upper-bound certificate. Re-running the maximizing search is useful
differential evidence but is not the proof verifier. A certificate accepted
only because it restates the chosen value, trusts a claimed upper bound, or
calls the solver as its verifier rejects.

The exact closed proof-node grammar, scalar/string/array frontier semantics,
certificate identity payloads, solver/verifier separation, and local-shutdown
minimality certificate are frozen in:

```text
docs/research/
  v4_9f_a2_raw_v8_step2_constructive_maximum_protocol_freeze_2026-08-01.md
```

Every row, manifest, scope ID, and counterexample commits that file's exact
physical SHA-256. The V3 scope-profile catalog deliberately does not, so the
inventory has no dependency on a later proof implementation. No maximum row
may be generated until this separate protocol and an independent verifier of
its closed grammar are accepted. An open `proof_payload`, arbitrary code,
solver-specific opaque blob, or certificate grammar inferred from generated
rows rejects.

The semantic identity graph is acyclic:

```text
maximum protocol physical SHA
  -> constraint-scope IDs and context-object IDs
context-object IDs
  -> context-object page IDs
  -> context-object manifest ID
maximum protocol physical SHA + constraint-scope ID + context-object manifest ID
  -> proof-node DAG
  -> upper-bound-certificate IDs
  -> maximum-witness IDs
  -> row raw SHA-256 values

context-object manifest ID + ordered row entries
  -> maximum-witness manifest ID
```

No object/reference/certificate contains a row or main-manifest ID, and no
certificate contains its own parent identity. Proof child positions are
strictly lower than the parent position, every node is reachable from the
single root, and the verifier derives the one permitted node plan and
normalization.

The exact accepted filesystem closure is one main manifest, one context-object
root manifest, its exact nonempty page files, exactly 474 row files, and the
exact listed object files, with only required nonempty directories. All paths
are normalized repository-relative POSIX paths. Absolute paths, `.`/`..`,
alternate separators, uppercase IDs, wrong hash-prefix directories, extra or
empty directories, archives, symlinks, FIFOs, devices, sockets, directories in
place of files, hard-linked aliases, or changed file identity/content between
bounded read and use reject.

The verifier opens the repository/artifact tree through retained directory
descriptors, enumerates exact names without following links, opens with
`openat`, `O_NOFOLLOW`, and `O_NONBLOCK`, requires regular files, performs
bounded complete reads, requires a single link, enforces unique `(st_dev,
st_ino)` across artifact paths, and compares stable before/after `fstat` state. It
retains bytes during use and re-enumerates/rechecks the closure before success.
This is an offline single-writer acceptance boundary; it does not claim safety
against an uncooperative same-directory writer with arbitrary namespace
mutation. Publication builds and independently validates a fresh staging
closure, synchronizes files/directories, and publishes the main manifest last;
an accepted file is never partially overwritten.

Within one legal constraint scope, deterministic selection uses exactly this
objective:

1. maximize measured compact-canonical witness byte length;
2. minimize the verifier-derived measured-record primitive choice vector;
3. minimize the verifier-derived constructed scope-context primitive choice
   vector.

Semantic identity fields, SHA-256 values derived from selected values,
object/reference/row/manifest IDs, repository paths, proof-node IDs and proof
serialization, and values fixed by V3 authority pointers are consequences, not
choice coordinates. Coordinate order is derived recursively from descriptor
`member_position`; arrays contribute cardinality then increasing zero-based
item positions; nullable branch precedes value; union alternatives use
`alternative_position`; root families, mode/attempt pairs, and roles use their
profile order; and ordinals compare numerically. Typed comparison is null
before non-null, `false < true`, mathematical integer order, Unicode
scalar-value lexicographic text order, array cardinality then items, and frozen
catalog position for literals/enums/unions.

`ordered_component_choice_evidence` is the exact verifier-derived coordinate
catalog and binds each coordinate's scope, kind, subject locator, value-schema
ID, derived compact length/hash, and supporting proof-node position. Large
selected values are resolved from the retained witness/context rather than
duplicated as an alternative payload. The separate maximum protocol freezes
its exact closed member schemas and identity domains. Proof bytes are never an
optimization axis; the verifier-owned canonical proof plan has one permitted
encoding. Any unresolved proof ambiguity is protocol NO-GO, not a solver
tie-break.

### 11.4 Application schedule and work-accounting nonclaims

For a V2 root scope, standalone
`APPLY/FIELD_OBSERVATION_FROZEN_REGISTRY_V1` is excluded because
`APPLY/V2_OBSERVATION_FIELDS_REGISTRY_V1` owns the same field/descriptor
policy within the root schedule. The exact schedule is:

1. selector/marker application once when a selector is present;
2. observation aggregate once per observation ordinal;
3. observation fields once per observation ordinal;
4. root observation membership once;
5. root selector lifecycle once.

Applications are ordered lexically by application name; repeated invocations
are ordered by observation ordinal. Each invocation has an application-local
accepted-only cache. No cache, resolver result, validation result, or failure
state crosses an invocation boundary.

For `N` observations with a selector, the schedule has `2N + 3` application
calls, `187N + 2` charged cross-rule evaluations, and `1,872N + 7` direct
cross-expression nodes. The 64-entry selector has `N = 67`, hence 137 calls,
12,531 charged evaluations, and 125,431 direct cross-expression nodes.
Selector-free startup (`N = 1`), selector-free ordinary operation
(`N = 3`), and an exact empty selector (`N = 3`) respectively have:

```text
calls / charged evaluations / direct cross-expression nodes
4 / 188 / 1,876
8 / 562 / 5,620
9 / 563 / 5,623
```

These formulas are structural schedule facts, not aggregate runtime-work
maxima.

Runtime evidence currently exposes these 20 additive scalar fields from
`ApplicationEvaluationEvidence`:

```text
charged_rule_evaluations
completed_rule_evaluations
intrinsic_rule_logical_invocations
intrinsic_rule_physical_executions
intrinsic_rule_cache_hits
resolver_invocations
resolver_source_identity_count
resolver_identity_logical_recomputations
resolver_identity_physical_recomputations
resolver_identity_cache_hits
resolver_logical_comparisons
logical_record_graph_validations
physical_record_graph_validations
record_graph_validation_cache_hits
validation_work_used
snapshot_canonicalized_octets
total_expression_nodes
complex_operator_invocations
complex_row_item_visits
complex_canonicalized_octets
```

Root-scope observed work is the sum of actual per-invocation evidence under
the frozen schedule. None of these fields is yet a certified maximum. The 474
rows are byte maxima only, and only the 404 root-application profiles define
the accepted root work domain. A byte-max witness does not prove a work max
within the same profile. `runtime_work_at_byte_maximum` is not a member of the
exact maximum-row, context, or manifest schemas. If retained, it is a separate
versioned, non-authoritative diagnostic artifact outside every maximum identity
and acceptance decision; the name reports an observation at a byte-max witness
and never claims a work maximum.

These 20 fields are the currently frozen evidence surface, not a claim that
all computational work is charged. Before any total-runtime or admission
budget is certified, an independent accounting-completeness audit must cover
every schema walk, generic array iteration, uniqueness/comparison step,
base64 octet, canonicalization octet, identity preimage octet, resolver step,
rule node, and application iteration. Any presently uncharged loop must gain
an explicit monotone counter and adversarial boundary test, or the resulting
claim must remain narrowly labelled as a maximum of the existing evidence
component only. The conservative 4,202,555 schema-node-visit ceiling and the
catalog sums of 258 evaluations/3,154 direct nodes are not constructive
legal-input aggregate-work maxima.

After the accounting-completeness audit closes, work maxima require a
separate versioned manifest and independent upper-bound certificate for each
frozen counter across every legal value in all 404 root profiles. That
artifact is not counted among the 474 byte rows. Its counter catalog, row
count, identity payload, and accepted/rejected-input domain must be frozen
before generation; this correction does not invent those facts prematurely.
No weighted scalar, unlabelled Pareto point, rejected input called a
constructive legal witness, or cross-invocation cache is permitted.

## 12. Per-operation result maximum evidence

The operation-result wrapper is a strict bound:

```text
canonical_byte_length < 524,288
```

The generator emits four independent outer-wrapper maximum witnesses, one for
each exact operation/result alternative:

```text
ACK_DEADLINE_EXPIRY
INGRESS
LOCAL_SHUTDOWN
SUBSCRIPTION_DISPATCH
```

There is exactly one result scope profile per operation. Each points to the
same operation's exact V3
`/fixture_records/operation_specs/<operation-kind>` record and its recomputed
`operation_spec_id`; these four signed specs are the complete meaning of
“frozen Step-2 boundary fixtures” for this gate. No generated relation case,
small result example, application witness, or future plan silently enlarges
that set. Each maximum row includes the complete wrapper, selected result
body, all nested evidence, nullable-branch choices, array cardinalities,
and recomputed `result_evidence_id` as its inline `witness_record`. Its signed
spec is not copied into the row or context store: the exact profile-authorized
`operation_spec_authority_reference` resolves it from V3. The verifier executes
the signed-spec application over the captured witness and resolved complete V3
spec. The row reports the exact profile-constrained analytic maximum and
positive codec slack from 524,288. This is not a claim about a future plan
universe.

Local shutdown is plan-dependent. The byte-maximum manifest therefore
contains the one legal result row for its exact V3 signed-spec profile. A
separate counterexample artifact contains:

- the smallest syntactically valid fixture/plan-limit mutation whose
  operational worst case would require 524,288 or more canonical octets;
- evidence that this mutation remains syntactically valid at Step-2 but is
  rejected by the later target-bound plan-admission gate as unrepresentable.

The mutation decision vector contains exactly these twelve signed limits.
Their scalar domains are:

| Member | Exact domain |
|---|---|
| `maximum_terminal_ingress_batches` | integer `1..9,007,199,254,740,991` |
| `maximum_terminal_ingress_ciphertext_octets` | integer `1..9,007,199,254,740,991` |
| `maximum_terminal_ingress_plaintext_octets` | integer `1..9,007,199,254,740,991` |
| `maximum_terminal_socket_receive_calls` | integer `1..9,007,199,254,740,991` |
| `maximum_terminal_tls_records` | integer `1..9,007,199,254,740,991` |
| `maximum_terminal_tls_unwrap_iterations` | integer `1..9,007,199,254,740,991` |
| `maximum_terminal_zero_progress_iterations` | integer `1..9,007,199,254,740,991` |
| `maximum_terminal_ingress_parser_units` | integer `1..4,096` |
| `maximum_terminal_ingress_automatic_outputs` | integer `1..4,096` |
| `maximum_websocket_send_attempts` | integer `1..1,048,832` |
| `maximum_tls_control_send_attempts` | integer `1..256` |
| `maximum_peer_shutdown_polls` | exact integer `2` |

Booleans, integer subclasses, floats, strings, and values outside the listed
domains reject. The mutated spec must additionally satisfy these five exact
intrinsic relations:

```text
maximum_terminal_ingress_plaintext_octets
  <= 16,384 * maximum_terminal_ingress_batches
2 * maximum_terminal_ingress_parser_units
  <= maximum_terminal_ingress_plaintext_octets
maximum_terminal_tls_records
  <= maximum_terminal_ingress_batches
maximum_terminal_ingress_automatic_outputs
  <= maximum_terminal_ingress_parser_units
maximum_websocket_send_attempts
  <= 256 * (1 + maximum_terminal_ingress_automatic_outputs)
```

Operational representability separately enforces the signed-spec/result
cross-record matrix: terminal outcome equality; all twelve final counters no
greater than their signed limits; terminal-read-attempt array length no
greater than `maximum_terminal_ingress_batches`; and parser-transition array
length no greater than `maximum_terminal_ingress_parser_units`. This matrix
is not spec-intrinsic validation.

“Smallest” is the deterministic minimum over the finite signed safe-integer
limit domain under this ordering:

```text
(
  changed_limit_field_count,
  sum_of_absolute_integer_deltas,
  changed_member_names_in_lexical_order,
  resulting_changed_values_in_that_same_order
)
```

The optimizer minimizes this tuple lexicographically relative to the exact
fixture. It must retain the complete mutation and proof; a search-order-first
or undocumented notion of smallest rejects.

Only the twelve named limit members contribute to
`changed_limit_field_count` and the absolute-delta sum. The singleton poll
limit therefore cannot change. The sum uses an unbounded mathematical
integer or checked UInt128 arithmetic. The workload, timeout, expected
outcome/code/reason, wrapper tags, and every other member remain byte-equal to
the fixture. `operation_spec_id` is recomputed but is a derived identity, not
an additional changed limit.

`mutated_limit_members` is a nonempty array in strict lexical `member_name`
order. Each entry has exactly:

```text
domain_position
member_name
baseline_value
mutated_value
absolute_delta
```

`domain_position` is the one-based row position in the twelve-member table
above; it is retained even though array order is lexical. Values are exact
mathematical integers, baseline and mutated values differ, and
`absolute_delta = abs(mutated_value - baseline_value) > 0`. The array contains
every and only changed named limit. Duplicate members, the fixed poll member,
or a derived identity as a mutation rejects.

Every result object accepted by the codec is trivially below 524,288 because
the codec enforces `LT 524,288`. That does not prove that every syntactically
valid local-shutdown spec can represent its full authorized operational
outcome. Later plan admission must construct the worst-case result under each
candidate plan's signed limits and reject the plan before candidate creation
when that worst case is `>= 524,288`.

The retained prospective result for the smallest over-limit mutation is an
admission counterexample, not a `CONSTRUCTIVE_LEGAL_MAXIMUM`: by definition it
cannot pass the outer result codec. Its record, canonical bytes, rejected
codec coordinate, mutated spec, and mathematical worst-case derivation must
nevertheless be retained independently; silently feeding it through an
accept-only runtime or calling its expected rejection a legal witness is
invalid.

That separate file is exactly:

```text
tests/raw_v8_step2_external_schema_v2_local_shutdown_unrepresentable_v49f.json
```

with root members:

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
local_shutdown_unrepresentable_id
```

Its version is
`riskyieldmm.raw_v8_step2_external_schema_v2.local_shutdown_unrepresentable.v1`.
Its ID domain is
`RiskYieldMMA2MStep2ExternalSchemaV2LocalShutdownUnrepresentableV1V4_9F_RawV8`
over every preceding member in that order. The file uses the same bounded,
deterministic pretty encoding and path/read rules as Section 11.3 and is not a
474-row manifest entry.

`baseline_spec_record_reference` is the exact `V3_INVENTORY_POINTER` to
`/fixture_records/operation_specs/LOCAL_SHUTDOWN`; no inline baseline copy is
admitted. It resolves profile position 3, whose current profile ID is
`92a80f3b2dc5d4b9a6284adfb6819823de7e2546d4141b2b12c5c7c9afff21f4`,
and the baseline `operation_spec_id` is
`f88cf223f28a146b08b5ffbb3b5ce419fb7ce473563edb27900983d6583a2d21`.
Those IDs are recomputed from complete accepted V3 records rather than trusted
as bare strings.

`expected_rejection_coordinate` has exactly:

```text
record_type_name
typed_member_path
validation_layer
codec_byte_bound_relation
codec_octet_limit
observed_canonical_byte_length
failure_class
```

Its values are respectively
`CapacityMeasurementOperationResultEvidence`, the exact empty typed path,
`CODEC_BOUND`, `LT`, `524288`, the prospective result's measured compact length,
and `CODEC_OCTET_LIMIT_VIOLATION`.

`minimality_certificate` has exactly:

```text
certificate_version
maximum_protocol_sha256
baseline_operation_spec_id
mutated_operation_spec_id
mutable_limit_member_count
ordered_mutable_limit_member_names
winning_objective
ordered_proof_nodes
root_proof_node_position
local_shutdown_minimality_certificate_id
```

Its version is
`riskyieldmm.raw_v8_step2_external_schema_v2.local_shutdown_minimality_certificate.v1`;
its semantic ID domain is
`RiskYieldMMA2MStep2ExternalSchemaV2LocalShutdownMinimalityCertificateV1V4_9F_RawV8`
over every preceding member. The mutable count is exactly eleven and the names
are the twelve-table names except `maximum_peer_shutdown_polls`, in lexical
order. `winning_objective` has exactly
`changed_limit_field_count, sum_of_absolute_integer_deltas,
changed_member_names_in_lexical_order,
resulting_changed_values_in_that_same_order`. The maximum protocol freezes the
closed prior-position proof-node grammar, recurrence, and resource limits; an
opaque search log or solver assertion is not evidence.

The verifier enforces these duplicated-claim equalities exactly:

```text
changed_limit_field_count = len(mutated_limit_members)
sum_absolute_integer_deltas =
  sum(entry.absolute_delta for entry in mutated_limit_members)
prospective_result_canonical_byte_length =
  len(compact_canonical(prospective_result))
outer_codec_byte_bound_relation = "LT"
outer_codec_octet_limit = 524288
expected_rejection_coordinate.observed_canonical_byte_length =
  prospective_result_canonical_byte_length
expected_rejection_coordinate.codec_byte_bound_relation =
  outer_codec_byte_bound_relation
expected_rejection_coordinate.codec_octet_limit = outer_codec_octet_limit
minimality_certificate.baseline_operation_spec_id =
  resolved baseline_spec_record_reference.record_identity
minimality_certificate.mutated_operation_spec_id =
  recomputed mutated_spec.operation_spec_id
minimality_certificate.winning_objective =
  (changed_limit_field_count,
   sum_absolute_integer_deltas,
   mutated_limit_members[*].member_name in retained lexical order,
   mutated_limit_members[*].mutated_value in that same order)
```

Each mutation entry's baseline/mutated value also equals the named member of
the resolved baseline/embedded mutated spec, respectively. Every non-limit
member remains byte-equal apart from the recomputed derived identity. An
internally contradictory duplicate claim rejects before any minimality proof
is evaluated.

The root proof establishes: the unchanged fixture is valid and below the
bound; all eleven mutable domains and five intrinsic inequalities are exact;
the least legal positive and negative delta candidates for each member are
covered; every objective tuple strictly better than the winner is impossible
or remains below the bound; the retained wrapper attains at least 524,288
octets; and every schema, scalar, intrinsic, identity, and signed-spec rule
other than the named outer codec check passes. If a one-member winner exists,
every two-or-more-member mutation loses immediately on changed-field count; if
not, the certificate covers the required finite member subsets and boundary
frontiers explicitly.

Validation uses two separate passes. The independent counterexample pass
validates every exact key, scalar, nested record, intrinsic rule, identity,
signed-spec comparison, and cardinality relation while masking only the named
outer `CapacityMeasurementOperationResultEvidence LT 524288` check. A second
pass invokes the unchanged runtime with no mask and requires rejection at the
exact structured coordinate above. Reusing an accept-only runtime for the
first pass, adding another bypass, or accepting any other malformed value,
failed identity, intrinsic failure, signed-spec false result, or rejection
coordinate invalidates the counterexample.

Step-2 does not demand, compute, or claim a global maximum across all future
admissible plans before the target-bound universe exists.

The 404 `FROZEN_ROOT_APPLICATION` rows, not the local-shutdown mutation
procedure, cover the strict `TargetObservationV2 < 262,144` bound for every
operation kind, exact-marker selector position, and four placeholder causes.
Passing only the small fixture is insufficient.

Each of the four non-checkpoint rows maximizes over every V3-admitted
non-`STABLE_CHECKPOINT` role/root schedule for that operation kind, including
`STARTUP_RECOVERY` and ordinary `BEFORE_OPERATION`, `AFTER_OPERATION`, and
`OPERATION_AGGREGATE` observations wherever the lifecycle permits them.
Selecting only the legacy `AFTER_OPERATION` fixture is insufficient. The row
retains the selected role, instrumentation mode, root schedule, and complete
root/application context. The 400 checkpoint rows cover every exact frozen
selector position independently under the exact marker and each of the four
placeholder causes.

A frozen fixture whose constructive maximum cannot be proven strictly below
the bound is Step-2 design NO-GO. A later candidate plan whose constructive
operational worst case is not strictly below the bound is admission NO-GO.
Raising the bound, dropping evidence, shortening an array, or replacing a
complete nested record with its hash is not an automatic correction.

## 13. Registry self-validation

The independent validator performs these steps in this exact order:

1. Enforce the exclusive 16,777,216-byte registry bound before JSON decode.
2. Apply the frozen structural scanner before decode.
3. Decode strict canonical I-JSON; reject duplicate keys, floats, nonfinite
   values, booleans used as integers, and noncanonical bytes.
4. Validate the root's exact keys, logical member positions, and canonical
   lexicographic object-key bytes.
5. Validate Unicode source records by the frozen byte counts and hashes.
6. Validate the three profile records, their exact ten field surfaces, every
   text-language descriptor, and all value schemas.
7. Validate exactly 52 type names: 49 concrete and three union nodes.
8. Resolve every value-schema, type, union, rule, and application reference.
9. Prove catalog reachability equality with no missing or extra node.
10. Prove acyclicity and maximum typed depth.
11. Type-check every rule expression and application binding.
12. Recompute every metadata ID and registry ID.
13. Validate the exact 408 scope-profile catalog, all inventory pointers,
    profile IDs, selector coordinates, family domains, and schedule formulas.
14. Securely enumerate and validate the exact row, context-object, page, and
    manifest closure and recompute every raw and semantic identity.
15. Resolve every record reference, prove selected-witness equality, replay the
    complete validation/application schedule, and independently verify every
    closed upper-bound certificate.
16. Verify the local-shutdown counterexample, its minimality certificate, and
    the isolated masked/unchanged-runtime two-pass result.

The isolated V3 inventory gate executes steps 1-13 and reports maxima pending.
Steps 14-16 execute only after the V3 semantic inventory SHA-256 and maximum
protocol physical SHA-256 are frozen; this two-phase order is required and is
not a skipped acceptance check.

The constructive solver and independent verifier are separate programs. The
verifier imports neither the solver/generator nor `riskyieldmm`, solver
libraries, production constants, or opaque solver state. It derives the
maximum problem, frontiers, primitive choice vectors, identities, and proof
plan directly from the accepted registry, V3 inventory, protocol, and candidate
artifacts. Calling a producer from the verifier rejects.

Production code is then checked against the independent registry by explicit
class/type adapters. The independent generator and validator may not import
`riskyieldmm`, inspect dataclasses, parse production annotations, or reuse
production constants. Production reflection can be used only by a separate
comparison test after the independent artifact exists.

## 14. Migration and rejection behavior

Migration is regeneration, not in-place reinterpretation:

1. Apply the binding, primitive tie-break, bounded context closure,
   certificate-interface, local-shutdown, security, and resource amendments to
   this correction in one normative edit.
2. Recompute this correction's physical SHA-256 once and update the independent
   V3 validator/tests; sequential partial refreezes reject.
3. Regenerate and independently validate the canonical V3 inventory. Require
   the structural registry ID, rule-literal authority SHA-256, and all 408
   complete profile objects/IDs to remain unchanged. A profile change is
   STOP/NO-GO, not an expected documentation-only migration effect.
4. Reaccept the expected new V3 physical/semantic identities only after the
   focused inventory/security suite and migrated consumer matrix pass again.
5. Freeze the separate constructive-maximum proof protocol, bounded context
   closure, pilot-supported practical resource caps, and genuinely independent
   verifier; bind its physical SHA-256 into every proof scope.
6. Implement the independent solver and generate the complete context closure,
   all 474 byte-maximum rows, and the local-shutdown counterexample.
7. Run the independent verifier plus adversarial, production-differential, Raw
   V7 compatibility, and final-tree suites.
8. Complete work-accounting separately without adding work claims to byte
   maxima artifacts.
9. Implement/validate production V2 adapters and publish final Step-2
   acceptance only when every identity and acceptance report agrees.

The historical V1 golden, drifted V2 candidate, V2 generator output order,
heuristic target-observation bound proof, and subscription-only result bound
proof are provenance only. None is migrated, relabelled, or accepted as a V3
scope profile, constructive maximum, upper-bound certificate, or production
adapter result.

The following inputs reject with a dedicated external-schema-version or
schema-graph error:

- inventory `v3` carrying V1 descriptors;
- inventory `v2` relabeled as `v3`;
- a V1 descriptor converted by guessing array item types or union variants;
- a registry with 50 nodes, 49 nodes, or 52 nodes containing a wrong name;
- either operation wrapper used in place of its body-union node;
- an old V1 observation record admitted into the V2 graph;
- a runtime type not reachable from the exact accepted root set;
- preserved V1 descriptor or registry IDs.

Readers may retain an explicit V2-inventory reader for historical diagnostics,
but it cannot supply target-bound truth and cannot be silently upgraded in
memory.

## 15. Adversarial acceptance matrix

At minimum, acceptance requires deterministic rejection of:

1. missing or extra concrete type;
2. missing, merged, open, or extra union;
3. the rejected 50-node proposal;
4. wrong standalone/nested role;
5. swapped logical member positions/identity-payload members, or selector
   `ordered_entries` incorrectly included in or omitted from the complete
   envelope/identity distinction;
6. envelope `record_domain` confused with `described_record_domain`;
7. nullable member represented as optional or nullable array represented as
   nullable item;
8. array with absent, wrong, or generic item schema, including selector
   entries/IDs rejecting zero or accepting 65;
9. literal widened to enum/text or enum widened/reordered, including narrowed
   signed dispatch disposition or widened result disposition;
10. `LT` changed to `LE` at 524,288 or 262,144;
11. unresolved, cyclic, or legacy reference;
12. member-name heuristic, default schema fallback, or any extra unreachable
    schema/language/DFA/profile/rule/application;
13. unrestricted-Unicode validation under a runtime Unicode version other
    than 15.0.0, or ASCII-only diagnostics incorrectly disabled by that
    mismatch;
14. one-bit mutation, truncation, or substitution of a Unicode source;
15. non-NFC, leading/trailing member of the 29-code-point trim set, control,
    surrogate, 129/257 scalar, or one-octet-over-limit identifier; or
    `RAW_CANONICAL_JSON_STRING` incorrectly subjected to those identifier
    restrictions;
16. Unicode-equivalent but byte-different identity accepted after repair;
17. opaque cross-field rule with no typed expression, executable regex/prose
    text grammar, noncanonical 20/27-byte RFC3339 persisted form, chronology
    comparison without typed RFC3339 conversion, or missing layer/field-prefix
    relation;
18. rule path crossing an array without `ARRAY_EACH`;
19. `ARRAY_EACH` with missing/wrong maximum, wrong item type, skipped ordinal,
    unequal zip accepted, observation/descriptor positional zip omitted,
    external source accepted under both application kinds, or fixed resolver
    ARRAY/scalar/null flattening ambiguity;
20. multi-record rule with a swapped/absent tuple input or application binding
    ledger unequal to the referenced rule binding ledger;
21. safe-arithmetic/uint128/timestamp conversion overflow or type mismatch in
    a rule;
22. claimed maximum without a legal retained witness;
23. maximum selected by string length instead of canonical bytes;
24. one union alternative omitted from maximum construction;
25. syntactically valid local-shutdown plan mutation whose operational worst
    case is unrepresentable accepted by the later admission gate;
26. canonical inventory, rule, application, expression order, DFA, or schema
    changed without every dependent semantic ID changing;
27. independent generator importing or reflecting over production code;
28. any former inline `OWNER_MEMBER`, `OUTER_RESULT_APPLICATION`, or
    `ROOT_APPLICATION` record shape, including the reproducible 17,459,925-byte
    full-67 skeleton;
29. missing, extra, orphaned, duplicated, reordered, stale, substituted,
    wrong-type, hash-only, or alternate-path context object/page;
30. frozen V3 authority copied into the context-object store, constructed
    context replaced by an inventory pointer, or authority pointer outside the
    selected profile's paired pointer/identity sequence;
31. object/reference selected-witness mismatch, root ordered-ID mismatch,
    missing observation, wrong zero/one-based ordinal, or non-checkpoint
    variable ordinal treated as a fixed checkpoint ordinal;
32. monolithic context catalog, hash-distribution-based catalog paging,
    nonmaximal ordinal page partition, page with more than 1,024 entries or
    1,048,576 raw octets, more than 27 pages, wrong total-object octets, or
    protocol aggregate-resource excess;
33. object, page, context-manifest, row, main-manifest, or counterexample
    protocol/inventory/registry/literal-authority identity mismatch;
34. symlink, hard-link alias, special file, unlisted backup/temp file, wrong
    hash-prefix filename, unstable bounded read, or changed directory closure;
35. derived semantic/hash/path/proof value admitted as an optimization choice,
    producer-supplied coordinate order, or proof bytes used as a tie-break;
36. unknown proof node, duplicate/forward/cyclic/unreachable node, noncanonical
    frontier, pruning across unequal ancestor-observable signatures, unsafe
    domain narrowing, or proof resource excess;
37. local-shutdown zero-change proof, non-limit mutation, skipped better
    objective tuple, wrong delta arithmetic, prospective wrapper below the
    bound, additional validation bypass, or different runtime rejection
    coordinate;
38. solver, generator, proof producer, and independent verifier sharing the
    same maximizing implementation or the verifier importing either producer;
39. a structurally and codec-valid context object whose attached intrinsic
    rule evaluates business-false or fails evaluation.

Positive tests cover all 52 graph nodes, every union alternative, every
nullable branch, every array at minimum and maximum cardinality, every byte
bound at its legal edge, all Unicode normalization conformance rows, and every
rule-application kind. They also reconstruct the reference-based equivalent of
the known 67-observation context byte-for-byte, exhaustively compare miniature
bounded schemas against brute-force maxima, and prove that the final complete
row/proof files and complete context closure satisfy their frozen resource
budgets.

## 16. Required acceptance artifacts

The correction is not complete until the repository contains:

```text
docs/research/
  v4_9f_a2_raw_v8_step2_external_schema_v2_acceptance_2026-07-28.md
  v4_9f_a2_raw_v8_step2_constructive_maximum_protocol_freeze_2026-08-01.md

tests/
  raw_v8_step2_inventory_v49f.json
  raw_v8_step2_external_schema_v2_maximum_witnesses_v49f.json
  raw_v8_step2_external_schema_v2_maximum_witnesses_v49f/context_object_manifest.json
  raw_v8_step2_external_schema_v2_maximum_witnesses_v49f/context_object_manifest_pages/...json
  raw_v8_step2_external_schema_v2_maximum_witnesses_v49f/context_objects/...json
  raw_v8_step2_external_schema_v2_maximum_witnesses_v49f/rows/...json
  raw_v8_step2_external_schema_v2_local_shutdown_unrepresentable_v49f.json

scripts/tests/
  generate_raw_v8_step2_inventory_v49f.py
  generate_raw_v8_step2_external_schema_v2_maximum_witnesses_v49f.py
  validate_raw_v8_step2_external_schema_v2_v49f.py
  validate_raw_v8_step2_external_schema_v2_maximum_protocol_v49f.py
  verify_raw_v8_step2_external_schema_v2_maximum_witnesses_v49f.py

tests/
  test_trading_physical_transport_capacity_contracts_v49f_v8_isolated.py
  test_raw_v8_step2_external_schema_v2_adversarial_v49f.py
  test_raw_v8_step2_external_schema_v2_inventory_v3_v49f.py
  test_raw_v8_step2_external_schema_v2_maximum_protocol_v49f.py
  test_raw_v8_step2_external_schema_v2_maximum_witnesses_v49f.py
  test_raw_v8_step2_external_schema_v2_maximum_witnesses_adversarial_v49f.py
```

At the pre-V3 application-runtime checkpoint, the following independently
checkable component inputs, structural assembly, complete 52-operator/42-rule
runtime, and eight-application/two-resolver executor had been materialized.
This paragraph records dated provenance rather than current gate status. At
that checkpoint they were not the V3 inventory, constructive-maximum proof,
production integration, or final acceptance:

```text
scripts/tests/
  raw_v8_step2_external_schema_v2_core_ledger_v49f.json
  raw_v8_step2_external_schema_v2_topology_ledger_v49f.json
  raw_v8_step2_external_schema_v2_scalar_path_ledger_v49f.json
  raw_v8_step2_external_schema_v2_rule_literal_authority_v49f.json
  raw_v8_step2_external_schema_v2_rule_application_ledger_v49f.json
  raw_v8_step2_external_schema_v2_structural_registry_v49f.json
  raw_v8_step2_external_schema_v2_generic_rule_witness_v49f.json
  raw_v8_step2_external_schema_v2_complex_rule_witness_v49f.json
  raw_v8_step2_external_schema_v2_application_witness_v49f.json
  validate_raw_v8_step2_external_schema_v2_foundation_v49f.py
  validate_raw_v8_step2_external_schema_v2_topology_v49f.py
  validate_raw_v8_step2_external_schema_v2_scalar_path_v49f.py
  validate_raw_v8_step2_external_schema_v2_rule_application_v49f.py
  validate_raw_v8_step2_external_schema_v2_rule_runtime_v49f.py
  validate_raw_v8_step2_external_schema_v2_structural_registry_v49f.py
  validate_unicode_15_0_0_normalization_v49f.py
  capture_raw_v8_step2_external_schema_v2_rule_literal_authority_v49f.py

tests/
  test_raw_v8_step2_external_schema_v2_topology_v49f.py
  test_raw_v8_step2_external_schema_v2_scalar_path_v49f.py
  test_raw_v8_step2_external_schema_v2_rule_application_v49f.py
  test_raw_v8_step2_external_schema_v2_rule_runtime_v49f.py
  test_raw_v8_step2_external_schema_v2_generic_rule_witness_v49f.py
  test_raw_v8_step2_external_schema_v2_complex_rule_witness_v49f.py
  test_raw_v8_step2_external_schema_v2_application_witness_v49f.py
  test_raw_v8_step2_external_schema_v2_application_adversarial_v49f.py
  test_raw_v8_step2_external_schema_v2_structural_registry_v49f.py
  test_unicode_15_0_0_normalization_v49f.py
```

The `capture_...rule_literal_authority...` helper is deliberately one-way
production provenance capture. It is not an independent generator or
validator. The frozen literal authority is then a hash-pinned input to the
standard-library-only rule/application validator.

The current isolated rule/application component contains exactly 49
attachment rows, 34 intrinsic rules, eight cross-record rules, eight
applications, two fixed-position resolvers, 36 additive schemas over the
exact 200 member schemas, and 1,057 expression nodes. Its physical ledger is
1,141,506 bytes with SHA-256
`979d7affe2d745d46f5977d9d69a4d1efa473f95c1a374737bf34181d9dac282`;
its semantic component ID is
`0a1e0ffed2bf8d07a94c24c5f247270bb86f9a172e448830600c0ddcecf010a8`.
Its status remains
`RULE_APPLICATION_ONLY_NOT_FULL_REGISTRY`. Composite literals are
structurally and scalarly checked, exact-frozen-selected, and dependency-DAG
checked in this component; execution of every attached intrinsic rule is
still a mandatory responsibility of the complete registry evaluator.

The structural assembly now materializes the exact Section 3 root with no
component-status or wrapper member. It contains six Unicode sources, three
identifier profiles, nine ASCII DFAs, 103 text languages, 236 reachable value
schemas, 52 type descriptors, 42 rules, two resolvers, and eight
applications. The physical artifact is 1,469,663 bytes with SHA-256
`9160297ff316c5931737c92f8b359f0a1e2ec22f0aa996ef3b09cf830dc96bf3`;
its registry ID is
`5dc95a3e99c5646e912b6a7e9c3970cf2489d560ea890b0a19d38af4c51c2140`.
Its report-only status is
`STRUCTURAL_REGISTRY_ONLY_RULE_RUNTIME_AND_MAXIMA_PENDING`. Independent
recomputation confirmed all 52 type IDs, all six Unicode-source IDs, every
accepted-catalog equality, all three union discriminator bindings, and the
root ID. The focused structural suite passed 20 tests and the combined
foundation/topology/scalar/Unicode/rule/structural suite passed 213 tests.
This closes structural assembly only; it does not execute a rule, prove a
maximum, validate a production adapter, replace the canonical inventory, or
change the Step-2 NO-GO decision.

The first executable runtime increment is now materialized in
`validate_raw_v8_step2_external_schema_v2_rule_runtime_v49f.py`, with focused
coverage in
`test_raw_v8_step2_external_schema_v2_rule_runtime_v49f.py`. The validator is
89,310 bytes with SHA-256
`1d04f4324e762727b989d5e117c7532bfb9daff8521a4cda4f32c6e5c25773bf`;
the 54,086-byte test module has SHA-256
`c6ad271d3cb548e7b3df4369a355d0ec73123062fb920ffe9a8ebf45edd29fd0`.
It securely hash-pins and independently decodes the accepted structural and
literal authorities; executes exact Boolean/integer/text/array/object/record
and all three tagged-union value validation; enforces standalone identities,
record and union codec bounds, Unicode 15.0.0 profiles, all nine ASCII DFAs,
the five built-in languages, exact owner/self union dispatch, cyclic-value
rejection, exact binding contracts, and node-result declarations; and reports
a frozen conservative ceiling of 4,202,555 `SCHEMA_NODE_VISIT` units. That
ceiling covers the frozen schema maxima and is explicitly not a constructive
legal-value or aggregate rule-work maximum.

The same runtime now implements the complete 41-operator generic subset and
the complete 11-operator complex subset. Static partitioning records exactly
33 generic-only and nine complex-dependent rules, while public evaluation
executes all 42 rules and all 1,057 direct expression nodes. Evaluation is
eager, visits each frozen expression position once, distinguishes a false
business root from an evaluation failure, and recursively executes every
intrinsic rule attached to a composite literal. The three retained literal
authorities execute exactly 500 intrinsic invocations and 6,081 expression
nodes in aggregate. Direct conformance reaches all 52 dispatch branches,
including the ten generic operators not used by the current rule catalog.

The compact generic-rule witness
`raw_v8_step2_external_schema_v2_generic_rule_witness_v49f.json` is 296,275
bytes with physical SHA-256
`c8a3748755489944c96d7bb22107cb6eb7c54d3731f6d4d2bd070a7789a5b595`
and semantic ID
`10fc6bfd9b1f04baf1bb0335c744185d9f0f0482bd493fa2ad2b0a2a32d370e7`.
Its 13,709-byte independent test has SHA-256
`98d66a597aaaa5aff610ee259cbaf767615e13c5db8ab106b23f614d78aaa183`.
It freezes provenance-pinned extracts rather than reading `test_output` at
test time and supplies one schema-valid true and one schema-valid
business-false witness for every one of the 33 generic rules. It explicitly
states that it is test evidence, not schema, production, inventory, or
acceptance authority.

At that same pre-V3 checkpoint,
`test_output/raw_v8_step2_inventory_v2_candidate.json` was provenance only: it
declared `riskyieldmm.raw_v8_step2_inventory.v2`, not the required V3
inventory, and the then-current generator had subsequently added fixtures
absent from that candidate. This is migration rationale, not a statement about
the current generator or canonical golden. The V2 candidate is never runtime
or acceptance authority. Any complex-rule witness may freeze typed extracts
with both physical provenance pins and explicit nonclaims, while current gate
status is maintained in the implementation roadmap rather than inferred from
this historical paragraph.

Independent adversarial review withheld the generic increment until it closed a
2,000,000-visit false rejection, caller enlargement of the frozen ceiling,
omitted union bounds, canonical fractional-zero timestamp acceptance,
empty-Unicode acceptance, post-decode-only depth handling, unstable/nonscalar
authority reads, a tuple/subclass in-memory authority substitution seam,
quadratic uniqueness at a 524,288-item declared maximum, non-text hostile
mapping keys, unbounded host integer conversion, incomplete binding
nullability checks, result/node declaration drift, and a non-Boolean
`require_true` policy seam. The later complex increment implements supplied-
authority indexes, exact union and identity resolution, every frozen complex
branch table, and per-evaluation row/item and canonical-octet evidence. The
later application increment makes the same runtime 249,268 bytes with
SHA-256
`47aa90d897e8dbae5e244b7c04cbd82dfe036b0292d36ef0f5552c868627ab22`;
the 111,238-byte focused test has SHA-256
`049dad2dba0da86dd1d4229c5d784860d97e4955bf47845251a2720485cfbb10`.
The focused runtime suite passes 124 tests.

The independent complex-rule witness is 456,162 bytes with physical SHA-256
`d74bbc6bd98de6f143bd1bfcc9c2660f8923713ac901911289939dfd12712e4b`
and semantic ID
`ac01e4b1eee0ae3ee394818f230380a71dc778f7d7c688d084da1f9aebb81e2a`.
Its 20,735-byte test has SHA-256
`fe0b648a43575779bea452d6ae2406f7b665ef4bef8759afd622e20f3a0b0125`.
It executes 44 cases across the exact nine complex rules: 27 true, 13
business-false, and four deterministic evaluation failures. It covers all
four signed result kinds, all nine non-null target-value families plus null,
bitmap and A1 behavior, selector lengths 0/1/4/64, and startup, selector-free,
empty-selector, and one-entry selector-bound root branches. It explicitly
does not claim the 67-observation/max64-selector root maximum or application
execution.

The independent application witness is 697,208 bytes with physical SHA-256
`d2f40badc85c58965a72e52fd98bfebbd4caf3335ec5a0415a89294cc3fb3415`
and semantic ID
`1d859520c24a973a5a157139183ae24ef0184ce4cede5531bb4b442227e1a8ba`.
Its 32,704-byte test has SHA-256
`f22941e28e8a166183c8a3f89374bbaf1175a86b8f69147d63d47f5268880729`.
It executes 57 cases across all eight applications and both resolvers: 18
accepts, 26 application failures, and 13 business-false outcomes. The
full-67/max-64 recipe reaches ordinals 0..66; the field application reaches
0..184. No case is feature-detection skipped.

The separate 28,087-byte application-adversarial test has SHA-256
`10e5f4bb3f92306046f4dfc08f043420f3f3a875e58b4fd79a76ae987c17b0d6`
and passes 27 cases. It covers hostile exact-I-JSON boundaries without
executing subclass hooks, global snapshot-before-validation and
validation-before-intrinsic order, source-ordered resolver identity,
accepted-only cache accounting, exact failure coordinates, and fatal
mid-call plan/rule substitution. Independent review found and closed one real
moving-checkpoint defect: a shape-preserving `AND` to `OR` mutation after
entry validation could initially return acceptance. The accepted runtime now
captures exact rule bytes, compares them before every private execution, and
revalidates global authority before returning.

At the dated application-runtime checkpoint, the complete foundation/topology/
scalar/Unicode/rule/structural/runtime and four witness/adversarial suites
passed 375 tests in 120.73 seconds. The application-focused runtime/witness/
adversarial slice passed 156 tests. The runtime report stated
`APPLICATION_RUNTIME_ONLY_MAXIMA_AND_PRODUCTION_INTEGRATION_PENDING`.
No constructive or global-work maximum, production differential adapter,
canonical inventory replacement, or Step-2 acceptance was claimed by that
checkpoint. These counts remain predecessor evidence and do not override the
current status pointer in the implementation roadmap.

The acceptance report records:

- hashes and byte counts for this correction, all normative inputs, the
  generator, validator, canonical inventory, and witness artifact;
- the exact 49 + 3 node inventory and topological order;
- path-ledger coverage counts with zero missing/extra member paths;
- Unicode source verification and normalization-conformance counts;
- rule/type/application coverage;
- per-type and per-alternative maximum bytes;
- the four per-operation outer-result maxima and slack;
- target-observation maxima across all required coordinates;
- context-object counts by type, unique/deduplicated counts, aggregate compact
  bytes, page count, maximum page bytes, and exact reference/catalog set
  equality;
- proof-node/frontier/resource counts, primitive-choice-vector/derived-value
  exclusion tests, and solver/verifier import-separation evidence;
- local-shutdown masked-pass, unchanged-runtime-pass, and universal minimality
  results;
- exact test commands, outcomes, and elapsed times;
- Raw V7 and selected final-tree compatibility results;
- explicit dirty-worktree and leftover scans.

No acceptance statement may infer these results from a narrow unit test.

## 17. Gate decision

This correction establishes the required schema and proof-artifact shape and
makes the previous losses explicit. The implementation gate remains **NO-GO**
until:

1. **Satisfied component gate:** the exact 421-path/200-member-schema
   component is integrated into the complete registry without changing its
   reviewed assignments or reintroducing name heuristics;
2. **Satisfied component gate:** the 42-rule/eight-application component is
   independently executed by the complete registry evaluator. The accepted runtime
   increments cover all 52 operators, all 42 rules, selector groupwise
   occurrence ordering, recursive attached-intrinsic literal evaluation, all
   eight applications, both resolvers, global intrinsic-before-cross
   orchestration, exact failure coordinates, and accepted-only cache
   accounting;
3. an independently accepted V3 inventory binds the exact current correction
   bytes, preserves all 408 complete scope profiles and their IDs, and changes
   no inventory coordinate other than the correction authority count/hash, its
   exact `invariants.normative_document_sha256_by_role` mirror, and the
   resulting root inventory identity;
4. the separate constructive-maximum protocol, closed grammar verifier, and
   pilot-supported resource limits are frozen and accepted before any
   authoritative maximum row is generated;
5. the independent constructive solver and non-importing verifier prove all
   474 concrete/union/profile maxima, especially the four outer operation
   results and all V2 target-observation coordinates, and validate the bounded
   context-object closure and local-shutdown counterexample;
6. **Satisfied component gate:** the isolated 52-node graph and Unicode
   15.0.0 components retain their adversarial results after full-registry
   integration;
7. documentation, production adapters, generator, golden, and tests agree on
   the same registry identity.

Passing this Step-2 gate does not by itself establish trading profitability,
predictive edge, paper/live-trading readiness, A2-M completion, or Stage-1
completion. Runtime-work maxima remain a separately governed claim.

## 18. Open design questions requiring resolution before technical freeze

1. **Intrinsic nested-record ceilings. Resolved for this V3 gate:** retain the
   current codec ceilings exactly. Constructive analytic maxima and positive
   slack are evidence about the legal domain, not an implicit codec change.
   Any future tightening is a separately versioned production behavior change
   with new adapters, inventories, witnesses, and compatibility evidence.
2. **Text-language catalog breadth.** The three Unicode identifier profiles are
   frozen here. **Resolved at the isolated-component boundary:** the exact
   scalar/language ledger materializes 103 text languages, nine ASCII DFAs,
   and three Unicode profiles for all 421 member paths, with no generic
   `TEXT` fallback. Full-registry closure and evaluator conformance are now
   accepted component gates and may not change those assignments silently.
3. **Rule-language sufficiency.** The closed operator set must be checked
   against every current Step-2 intrinsic and cross-record invariant.
   **Resolved for descriptor materialization and the complete rule runtime:**
   the
   isolated component maps 34 intrinsic and eight cross-record rules into the
   exact 52-operator language and eight bounded applications, with static
   arity/type, expression-DAG, resolver, binding, and closure validation. The
   runtime now executes all 41 generic and 11 complex operators, all 42 rules,
   selector-DFA groupwise increasing occurrence, and recursive
   composite-literal dependencies against pinned true, business-false, and
   evaluation-failure witnesses. The complete evaluator also executes all
   eight applications and both resolvers with intrinsic-before-cross
   sequencing against independent and adversarial witnesses. Production
   differential adapters remain open. If that work exposes an inexpressible invariant,
   add one narrowly specified typed operator before the full-registry identity
   is frozen; arbitrary code remains forbidden.
4. **Per-plan local-shutdown admission integration.** Signed limits couple
   result arrays and counters. Step-2 can certify only its frozen fixtures.
   The later target-bound universe must define the exact constructive
   per-plan optimizer and reject every plan whose operational worst case is
   unrepresentable. That integration remains to be frozen; no global
   all-future-plan maximum is asserted here.
5. **Metadata-record self-description.** This draft keeps V2 metadata records
   outside the 52 runtime nodes to avoid self-reference. If later consumers
   need schemas for the metadata records themselves, place them in a separate
   nonrecursive meta-schema registry with a distinct domain and identity; do
   not add them to the runtime graph ad hoc.
