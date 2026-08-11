# Raw V8 Step-2 V2 contract and inventory freeze

**Freeze date:** 2026-07-26  
**Status:** Normative implementation input; **NO-GO** until the independent
inventory, production codecs, isolated adversarial harness, Raw V7 regressions,
and final-tree acceptance all pass  
**Supersedes:** the V1 ingress, subscription, local-shutdown, checkpoint, and
target-observation surfaces accepted historically on 2026-07-25  
**Preserves:** ACK-deadline-expiry V1, all 185 target-field IDs and measurement
definitions, the 66-field counter schema, the shared canonical envelope, and
all Raw V7 bytes; the V2 checkpoint-placeholder policy regenerates the Raw V8
descriptors and registry identity

**2026-07-28 re-audit notice:** Step-2 technical acceptance is reopened.
Sections 2 and 9, plus the dependent V2-root/V1-registry language in Section
11, are superseded by
[`v4_9f_a2_raw_v8_step2_external_schema_v2_correction_2026-07-28.md`](v4_9f_a2_raw_v8_step2_external_schema_v2_correction_2026-07-28.md).
The complete V3 inventory, V2 external registry, typed rule/application
ledger, constructive maxima, production adapters, and independent acceptance
have not yet passed. The existing canonical inventory is historical input
only and must not be promoted into a target-bound universe.

Normative parents:

- [`v4_9f_a2_marker_operation_target_v8_protocol_freeze_2026-07-22.md`](v4_9f_a2_marker_operation_target_v8_protocol_freeze_2026-07-22.md)
- [`v4_9f_a2_raw_v8_step3_projection_lifecycle_protocol_freeze_2026-07-25.md`](v4_9f_a2_raw_v8_step3_projection_lifecycle_protocol_freeze_2026-07-25.md)
- [`v4_9f_a2_raw_v8_step3_target_and_lifecycle_correction_2026-07-26.md`](v4_9f_a2_raw_v8_step3_target_and_lifecycle_correction_2026-07-26.md)

The historical Step-2 acceptance audit remains immutable evidence for its old
surface. It is not authority for this breaking V2 generation.

## 1. Decision and trust boundary

Step-2 V2 remains a pure contract layer. It does not authorize an effect,
create a candidate, call the transport, select a target-bound plan, or claim
Raw V8/Stage 1 acceptance. It supplies the exact typed input that the later
universe builder, sealed bound generator, independent verifier, lifecycle
layer, and live implementation must consume.

The independent inventory generator:

```text
scripts/tests/generate_raw_v8_step2_inventory_v49f.py
```

uses only the Python standard library and the three normative documents above.
It never imports `riskyieldmm`, production contracts, a later bound-generator
module, or a generated JSON file as semantic authority. The production module
and isolated harness independently reconstruct and validate the same records.

## 2. Inventory V2 root and identity

The inventory schema literal is:

```text
riskyieldmm.raw_v8_step2_inventory.v2
```

Its complete root has exactly these keys:

```text
schema_version
normative_document_inputs
invariants
target_field_registry
operation_counter_schema
marker_contract
checkpoint_selector_catalog
ingress_logical_oracle_profile_catalog
external_type_registry
operation_contracts
fixture_records
inventory_sha256
```

`normative_document_inputs` is the exact three-record array, ordered by
`document_role`:

```text
PARENT_MARKER_OPERATION_TARGET_PROTOCOL
STEP2_V2_CONTRACT_FREEZE
STEP3_TARGET_AND_LIFECYCLE_CORRECTION
```

Each record has exactly:

```text
document_role
repository_relative_path
raw_octet_count
raw_sha256
```

The path is the literal repository-relative POSIX path. Count and digest are
recomputed from exact bytes with no newline normalization. The inventory never
embeds its own raw-file hash, a target-bound inventory ID, admitted-plan ID,
or any downstream artifact identity.

`inventory_sha256` is lowercase raw SHA-256 of
`canonical_json_bytes(root_without_inventory_sha256)`. The published file is
pretty, UTF-8 JSON with sorted object keys, two-space indentation, and one
terminal newline for human review. Its semantic hash is over compact canonical
JSON, not the pretty file bytes. A second generation must reproduce both the
semantic hash and complete published bytes.

The V2 root groupings are exact:

```text
invariants:
  document identities, schema literals, exact counts, frozen IDs,
  byte maxima, V1-removal assertions, and generated boundary proofs

target_field_registry:
  the complete 185-field registry with the exact V2 placeholder-policy
  amendment in Section 8

operation_counter_schema:
  the complete unchanged 66-field counter-schema record

marker_contract:
  the one complete MarkerContractV1 record in Section 6

checkpoint_selector_catalog:
  the exact nine-selector catalog in Section 7

ingress_logical_oracle_profile_catalog:
  the one complete profile in Section 5

external_type_registry:
  complete type descriptors required by Step-2 and later bound replay

operation_contracts:
  exact tags, member schemas, domain/identity mapping, enums, and
  cross-field rule records

fixture_records:
  one valid spec/result for each operation, one declaration, supporting
  evidence, selector/context/observation/root fixtures, counter snapshot,
  maximum-bound fixtures, and one-field mutation metadata
```

Every catalog is sorted by its terminal semantic identity. Unknown grouping,
unknown record, duplicate identity, unequal bytes under one identity, missing
required type, or downstream identity contamination rejects.

## 3. Shared semantic envelope and version separation

The measurement schema remains exactly:

```text
riskyieldmm_physical_transport_a2m_raw_v49f_v8
```

The outer operation-spec and operation-result domains remain:

```text
RiskYieldMMA2MOperationSpecV4_9F_RawV8
RiskYieldMMA2MOperationResultEvidenceV4_9F_RawV8
```

Their identity payloads remain:

```text
operation_kind
spec_type | result_type
spec | result
```

The tag and exact nested-key body provide breaking separation. Current V2
decoding accepts only:

```text
ACK_DEADLINE_EXPIRY:
  ACK_DEADLINE_EXPIRY_SPEC_V1
  ACK_DEADLINE_EXPIRY_RESULT_EVIDENCE_V1

INGRESS:
  INGRESS_OPERATION_SPEC_V2
  INGRESS_RESULT_EVIDENCE_V2

LOCAL_SHUTDOWN:
  LOCAL_SHUTDOWN_SPEC_V2
  LOCAL_SHUTDOWN_RESULT_EVIDENCE_V2

SUBSCRIPTION_DISPATCH:
  SUBSCRIPTION_DISPATCH_SPEC_V2
  SUBSCRIPTION_DISPATCH_RESULT_EVIDENCE_V2
```

The three displaced V1 tags are forbidden in current enums, tag maps,
production decoders, fixture catalogs, and admission matrices:

```text
INGRESS_OPERATION_SPEC_V1
LOCAL_SHUTDOWN_SPEC_V1
SUBSCRIPTION_DISPATCH_SPEC_V1
INGRESS_RESULT_EVIDENCE_V1
LOCAL_SHUTDOWN_RESULT_EVIDENCE_V1
SUBSCRIPTION_DISPATCH_RESULT_EVIDENCE_V1
```

Historical JSON using those tags is diagnostic evidence only. Relabelling its
old body with a V2 tag rejects by exact keys.

All standalone records serialize the existing exact prefix:

```text
canonicalization_version
measurement_schema_version
record_domain
```

followed by the exact identity payload and identity field. Semantic IDs use
the existing Raw V8 `semantic_id()` algorithm. Boolean-as-integer, numeric
subclasses, floats, nonfinite values, unknown/missing/duplicate keys, Unicode
aliases, and forged dataclass subclasses reject.

## 4. Corrected operation specs and results

### 4.1 Ingress V2

The ingress spec has exactly:

```text
workload_family
ordered_input_chunks_base64
input_chunk_count
input_octet_count
input_sha256
raw_ingress_batch_sha256
timeout_seconds
logical_oracle_profile_id
expected_parser_unit_count
expected_completed_application_message_count
expected_logical_output_frame_count
expected_logical_output_payload_octets
expected_logical_output_frames_sha256
```

Input chunks retain the V1 canonical padded RFC-4648/base64, count, aggregate,
digest, and raw-batch identity rules. Bounds are:

```text
input chunks                              1..128
input octets                              1..65,536
timeout seconds                           1..300
expected parser units                     0..32,768
expected completed application messages  0..32,768
expected logical output frames            0..32,768
expected logical output payload octets    0..65,536
```

The three expected counts and payload total must be mutually achievable under
the complete oracle profile, but the spec carries no expected frame array.
`expected_logical_output_frames_sha256` is the streamed semantic digest over
the exact ordered logical `CLOSE`/`PONG` frames under the unchanged
`RiskYieldMMA2MExactLogicalOutputFramesV4_9F` preimage. The empty sequence has
its real derived digest, never SHA-256(empty).

The V2 result has exactly:

```text
ingress_progress_evidence_id
final_parser_cursor_id
final_retained_tail_id
final_retained_tail_octets
final_retained_tail_sha256
sealed_pending_input_id
ingress_oracle_baseline_id
observed_consumed_new_input_octets
observed_parser_unit_count
observed_completed_application_message_count
observed_logical_output_frame_count
observed_logical_output_payload_octets
observed_logical_output_frames_sha256
```

All IDs/digests are lowercase SHA-256. Counts are safe unsigned integers.
Returned-success validation requires every observed count/digest to equal its
spec expectation, consumed octets to equal the exact sealed input, and every
identity to recompute from the retained authoritative prefix as specified by
the correction. The Step-2 constructor can validate spec/result equality and
local scalar relationships; the later prefix replayer remains authority for
cursor/tail/progress/RAW lineage.

### 4.2 Fresh subscription V2

The subscription spec has exactly:

```text
workload_family
idempotency_key
transport_subscription_policy_id
adapter_policy_id
expected_topic
expected_operation
expected_logical_opcode
expected_dispatch_disposition
```

`expected_operation` is exactly `subscribe`; `expected_logical_opcode` is
exactly `TEXT`. Both policy members are lowercase SHA-256 identities.
Idempotency retains the exact 1..128 ASCII grammar. Topic truth is frozen in
Section 5.

The result has exactly:

```text
outbound_subscription_intent_id
generated_request_id
generated_request_command_sha256
generated_logical_opcode
generated_logical_payload_sha256
generated_logical_payload_octets
dispatch_window_evidence
dispatch_window_evidence_id
outbound_wire_prepared_event_id
tls_ciphertext_prepared_event_id
ordered_kernel_attempt_event_ids
ordered_kernel_result_event_ids
outbound_dispatch_completed_event_id
submitted_ciphertext_octets
local_dispatch_disposition
```

The generated opcode is exactly `TEXT`; request-command and logical-payload
digests are equal. Request ID retains the 1..36 ASCII grammar. Payload octets
are `1..65,536`. Kernel tuples have equal cardinality `1..256`; all IDs are
lowercase hashes, unique within each tuple, and positionally paired. Submitted
ciphertext octets are positive. Dispatch-window evidence is the complete
existing strict envelope and its duplicated ID must recompute. Local
disposition equals the signed expected disposition and is
`COMPLETE_LOCAL_SUBMISSION` for returned success.

Topic, request-command reconstruction, target receipt order, KA/KR pairing,
wire/TLS linkage, and final `D` truth are independently replayed from the
authoritative prefix. Step-2 does not fabricate generated facts as sampler
inputs.

### 4.3 Local shutdown V2

The local-shutdown spec has exactly the historical five members followed by
the complete signed limit vector:

```text
workload_family
timeout_seconds
expected_terminal_outcome
expected_local_close_code
expected_local_close_reason_sha256
maximum_terminal_ingress_batches
maximum_terminal_ingress_ciphertext_octets
maximum_terminal_ingress_plaintext_octets
maximum_terminal_socket_receive_calls
maximum_terminal_tls_records
maximum_terminal_tls_unwrap_iterations
maximum_terminal_zero_progress_iterations
maximum_terminal_ingress_parser_units
maximum_terminal_ingress_automatic_outputs
maximum_websocket_send_attempts
maximum_tls_control_send_attempts
maximum_peer_shutdown_polls
```

The historical timeout/outcome/Close rules remain. All twelve limits are
positive safe integers except that no implied runtime action is authorized by
their positivity. `maximum_peer_shutdown_polls` is exactly two. Required
relations are:

```text
maximum_terminal_ingress_plaintext_octets
  <= 16,384 * maximum_terminal_ingress_batches

maximum_terminal_ingress_parser_units
  <= floor(maximum_terminal_ingress_plaintext_octets / 2)

maximum_terminal_ingress_parser_units <= 4,096

maximum_terminal_tls_records
  <= maximum_terminal_ingress_batches

maximum_terminal_ingress_automatic_outputs
  <= maximum_terminal_ingress_parser_units

maximum_websocket_send_attempts
  <= 256 * (1 + maximum_terminal_ingress_automatic_outputs)

maximum_tls_control_send_attempts <= 256
maximum_peer_shutdown_polls = 2
```

All arithmetic is checked safe-uint arithmetic. Target-entry, result,
operation-batch, closed-prefix, and work bounds remain later pre-admission
requirements; passing these local relations is not plan admission.

The V2 result has exactly:

```text
local_shutdown_started_event_id
local_shutdown_deadline_evidence_event_id | null
local_close_dispatch_completion_event_id | null
ordered_terminal_ingress_read_attempt_event_ids
ordered_terminal_ingress_read_result_event_ids
ordered_terminal_raw_ingress_commit_ids
ordered_terminal_raw_ingress_actor_event_ids
ordered_terminal_parser_transition_event_ids
websocket_close_received_transition_event_id | null
shutdown_trace_step_count
shutdown_trace_root_sha256
final_terminal_ingress_batch_count
final_terminal_ingress_ciphertext_octets
final_terminal_ingress_plaintext_octets
final_terminal_socket_receive_call_count
final_terminal_tls_record_count
final_terminal_tls_unwrap_iteration_count
final_terminal_zero_progress_iteration_count
final_terminal_ingress_parser_unit_count
final_terminal_ingress_automatic_output_count
final_websocket_send_attempt_count
final_tls_control_send_attempt_count
final_peer_shutdown_poll_count
final_terminal_tls_staging_state_id
decisive_terminal_transition_event_id
transport_session_termination_id
terminal_outcome
```

Every non-null ID is a lowercase hash. Attempt and result tuples have equal
cardinality `0..maximum_terminal_ingress_batches`. The two terminal RAW tuples
have equal cardinality and cannot exceed the result tuple. Parser-transition
IDs cannot exceed the parser-unit limit. All tuples are unique internally.
Every final counter is a safe uint no greater than its signed matching limit;
the final batch count equals the attempt/result cardinality. Trace-step count
is safe, its root is a hash, and the final outcome equals the signed expected
outcome. Prefix replay enforces exact DATA subsequences, trace steps, DFA
transitions, staging-state resolution, decisive transition, and termination.

The complete outer operation-result evidence remains below 524,288 canonical
bytes. The independent generator must materialize the legal maximum for each
plan fixture and prove the strict bound; exceeding it rejects the plan before
candidate creation.

### 4.4 ACK V1

The exact accepted ACK spec/result bodies, due-decision clock evidence, tag
mapping, and spec/result validation remain byte-for-byte unchanged. The
regenerated V2 inventory must reproduce their semantic IDs from the new
normative-document hashes without changing their nested bodies.

## 5. Ingress logical-oracle profile and topic language

The inventory contains exactly one
`CapacityMeasurementIngressLogicalOracleProfileV1` record with domain:

```text
RiskYieldMMA2MIngressLogicalOracleProfileV1V4_9F_RawV8
```

and identity field `logical_oracle_profile_id`. Its exact identity payload is:

```text
profile_version = riskyieldmm_ingress_logical_oracle_profile_v1
oracle_kind = INDEPENDENT_RESTRICTED_WASM_RFC6455_STREAM
input_chunk_semantics = EXACT_ORDERED_DECRYPTED_APPLICATION_OCTETS
requires_empty_fragmentation_baseline = true
requires_empty_complete_unit_baseline = true
maximum_input_chunks = 128
maximum_input_octets = 65,536
maximum_parser_units = 32,768
maximum_completed_application_messages = 32,768
maximum_logical_output_frames = 32,768
maximum_logical_output_payload_octets = 65,536
logical_output_frame_domain =
  RiskYieldMMA2MExactLogicalOutputFramesV4_9F
raw_ingress_batch_domain =
  RiskYieldMMExactOrderedDecryptedIngressChunksV4_5
streamed_digest_algorithm = CANONICAL_JSON_SHA256_INCREMENTAL_V1
parser_oracle_descriptor_requirement =
  COMPLETE_DESCRIPTOR_AND_CONFORMANCE_CORPUS_IN_TARGET_BOUND_UNIVERSE
```

The profile ID is `semantic_id()` over those members. The Step-2 inventory
does not embed a self-selected Wasm body. The later universe manifest must
resolve one complete parser-oracle descriptor and corpus whose declared
profile ID byte-equals this ID; no runtime parser import or profile alias is
permitted.

`expected_topic` is the exact current transport canonical-identifier language:

- JSON string, nonempty and already trimmed;
- NFC-normalized Unicode;
- no U+0000..U+001F or U+007F control character;
- at most 256 Unicode code points under Python's code-point length semantics;
- valid UTF-8 and at most 1,024 UTF-8 octets.

The 1,024-octet ceiling is the constructive maximum for 256 valid Unicode code
points and closes byte materialization. No case-folding, whitespace rewrite,
provider-specific regex, or ASCII-only reinterpretation occurs at Step-2.
Provider/policy equality remains an exact later precondition.

## 6. Marker contract record

The inventory contains one complete `MarkerContractV1` under:

```text
domain = RiskYieldMMA2MMarkerContractV1V4_9F_RawV8
identity field = marker_contract_id
```

Its exact identity payload is:

```text
contract_version = riskyieldmm_raw_v8_marker_contract_v1
ordered_marker_kinds
ordered_full_checkpoint_marker_kinds
ordered_checkpoint_operation_records
forbidden_full_checkpoint_marker_kinds
minimum_marker_ring_capacity = 8
maximum_marker_ring_capacity = 4,096
maximum_checkpoint_selector_length = 64
stable_checkpoint_requires_attempt = true
```

`ordered_marker_kinds` is the exact 19-member UTF-8 lexical tuple in the
parent. Full-checkpoint kinds are the exact 13-member lexical tuple:

```text
ACK_DEADLINE_NOT_DUE
ACK_DEADLINE_TERMINAL_CONVERGED
DISPATCH_RETURN_READY
INGRESS_RETURN_READY
KERNEL_SEND_RESULT_CONVERGED
LOCAL_CLOSE_DISPATCH_CONVERGED
OUTBOUND_ARTIFACTS_PREPARED
PARSER_UNIT_CONVERGED
RAW_PREFIX_COMMITTED
SHUTDOWN_TERMINAL_CONVERGED
TARGET_ESCAPE_OBSERVED
TCP_HALF_CLOSE_CONVERGED
TLS_CONTROL_CONVERGED
```

Each checkpoint-operation record has exactly
`{checkpoint_marker_kind,applicable_operation_kinds}` and is sorted by marker
kind. Operation tuples are UTF-8 sorted and reproduce the historical exact
map. The forbidden tuple is exactly:

```text
ADMISSION_CANDIDATE_COMMITTED
ADMISSION_GRANTED
ADMISSION_NOT_GRANTED
ADMISSION_TICKET_ACCEPTED
TARGET_EFFECT_ENTRY
```

It is disjoint from full-checkpoint kinds. The marker-contract ID is required
by every later target budget, plan, candidate, attempt, closure, and bound
artifact; none may recompute a local alternative.

## 7. Checkpoint selector catalog

Selector entry and selector domains/identity fields are the exact correction
domains. Entry payload:

```text
selector_position
operation_kind
checkpoint_marker_kind
occurrence_index_within_kind
```

Selector payload:

```text
operation_kind
selector_length
ordered_checkpoint_selector_entry_ids
```

The complete selector also embeds `ordered_entries`, whose records must
recompute the IDs, operation, positions `1..N`, and count. Length is `0..64`;
occurrences are positive safe integers. An entry must use one full-checkpoint
kind applicable to its operation. Duplicate `(kind,occurrence)` pairs reject.

The catalog contains exactly nine named complete selectors:

```text
ACK_EMPTY
ACK_COVERAGE
INGRESS_EMPTY
INGRESS_COVERAGE
INGRESS_MAX64_PARSER_UNITS
LOCAL_SHUTDOWN_EMPTY
LOCAL_SHUTDOWN_COVERAGE
SUBSCRIPTION_EMPTY
SUBSCRIPTION_COVERAGE
```

Names are inventory catalog labels, not identity members. Empty selectors
have no entries. Coverage selectors have occurrence one in this exact
operation-DFA-compatible order:

```text
ACK_COVERAGE:
  ACK_DEADLINE_NOT_DUE
  ACK_DEADLINE_TERMINAL_CONVERGED
  TARGET_ESCAPE_OBSERVED

INGRESS_COVERAGE:
  RAW_PREFIX_COMMITTED
  PARSER_UNIT_CONVERGED
  INGRESS_RETURN_READY
  TARGET_ESCAPE_OBSERVED

LOCAL_SHUTDOWN_COVERAGE:
  LOCAL_CLOSE_DISPATCH_CONVERGED
  TLS_CONTROL_CONVERGED
  TCP_HALF_CLOSE_CONVERGED
  SHUTDOWN_TERMINAL_CONVERGED
  TARGET_ESCAPE_OBSERVED

SUBSCRIPTION_COVERAGE:
  OUTBOUND_ARTIFACTS_PREPARED
  KERNEL_SEND_RESULT_CONVERGED
  DISPATCH_RETURN_READY
  TARGET_ESCAPE_OBSERVED
```

`INGRESS_MAX64_PARSER_UNITS` contains exactly positions `1..64`, each
`PARSER_UNIT_CONVERGED`, with occurrence indices `1..64`. It is the root
cardinality/boundary fixture, not permission for an unproved workload.

These nine selectors are the complete Stage-1 admissible selector catalog.
A later plan may choose only one complete catalog selector for its operation;
an arbitrary caller-built selector is structurally valid evidence but is not
plan-admissible. Expanding the catalog requires a new inventory identity,
target-bound universe, plan proof, and acceptance run.

## 8. V2 observation codecs

### 8.1 Clock span

`TargetObservationClockSpanV2` has exactly:

```text
clock_domain
span_status
started_offset_nanoseconds | null
completed_offset_nanoseconds | null
unavailable_reason | null
```

Available spans require two ordered safe uint offsets and null reason.
Unavailable spans require null offsets and exactly one:

```text
ARTIFACT_BOUND_EXCEEDED
OBSERVER_INTERNAL_ERROR
PROCESS_LOSS_VOLATILE_MARKER_STATE
SOURCE_CLOCK_UNAVAILABLE
TARGET_BOUNDARY_NOT_REACHED
```

### 8.2 Context and binding truth

`TargetObservationContextV2` is the exact standalone record under the
correction domain. Its identity payload has exactly:

```text
observation_role
operation_kind
instrumentation_mode
candidate_id
attempt_id | null
target_field_registry_id
marker_ordinal | null
checkpoint_marker_kind | null
full_checkpoint_selector_id | null
checkpoint_selector_position | null
checkpoint_selector_entry_id | null
expected_checkpoint_marker_kind | null
expected_occurrence_index_within_kind | null
checkpoint_binding_status | null
checkpoint_binding_unavailable_reason | null
observer_clock_span
boottime_clock_span
loop_clock_span
```

followed by `observation_context_id`. Every non-checkpoint role has all
selector/binding members null. A stable checkpoint requires the exact selector
ID, position, entry ID, expected kind/occurrence, and one binding state:

```text
EXACT_MARKER
UNAVAILABLE_MARKER_OBSERVER_FAILURE
UNAVAILABLE_TARGET_BOUNDARY_NOT_REACHED
```

Truth is exactly the correction table. Marker-failure error mapping is exact;
`MARKER_OBSERVER_FAILURE` is never serialized as a span reason. Placeholder
precedence is exact marker, then conclusively not reached, then observer
failure.

### 8.3 Observation and root

`TargetObservationV2` identity payload has exactly:

```text
observation_context
observation_context_id
field_observations
```

followed by `observation_id`. The complete embedded V2 context recomputes to
the duplicated ID. The field tuple contains exactly 185 current
field-observation envelopes in registry order, all bound to that V2 context
ID. Their envelope/domain shape is unchanged, but they resolve the regenerated
V2 registry policy and ID.

`TargetObservationRootV2` identity payload has exactly:

```text
candidate_id
attempt_id | null
operation_kind
instrumentation_mode
target_field_registry_id
full_checkpoint_selector_id | null
observation_count
ordered_observation_ids
```

followed by `target_observation_root_sha256`.

Root order and selector truth are:

```text
attempted ON:
  non-null catalog selector, including the operation's empty selector
  BEFORE, positions 1..N, AFTER, AGGREGATE

OFF or no-attempt:
  null selector
  BEFORE, AFTER, AGGREGATE

startup recovery:
  null selector and null attempt
  exactly one RECOVERY observation
```

Attempted ON count is `N+3`, so the maximum catalog selector produces exactly
67 observations. Exact-marker ordinals strictly increase across exact-marker
positions; placeholders are ordered only by selector position. A placeholder
contains all 185 fields with `UNAVAILABLE`, `NOT_ATTEMPTED`, and
`NOT_APPLICABLE` adapter spans. Source adapters are never called. Field reason
mapping is exact:

```text
TARGET_BOUNDARY_NOT_REACHED
  -> CHECKPOINT_PLACEHOLDER_TARGET_BOUNDARY_NOT_REACHED

SOURCE_CLOCK_UNAVAILABLE
  -> CHECKPOINT_PLACEHOLDER_SOURCE_CLOCK_UNAVAILABLE

ARTIFACT_BOUND_EXCEEDED
  -> CHECKPOINT_PLACEHOLDER_ARTIFACT_BOUND_EXCEEDED

OBSERVER_INTERNAL_ERROR
  -> CHECKPOINT_PLACEHOLDER_OBSERVER_INTERNAL_ERROR
```

The four new field-level status reasons admit only null value, `UNAVAILABLE`,
`NOT_ATTEMPTED`, method `NOT_ATTEMPTED`, adapter `NOT_APPLICABLE`, null
adapter offsets, `NONE` censoring/failure phase, and no error metadata. They
use the exact new policy context predicates:

```text
CHECKPOINT_PLACEHOLDER_TARGET_BOUNDARY_NOT_REACHED
  -> V2_CHECKPOINT_PLACEHOLDER_TARGET_BOUNDARY_NOT_REACHED

CHECKPOINT_PLACEHOLDER_SOURCE_CLOCK_UNAVAILABLE
  -> V2_CHECKPOINT_PLACEHOLDER_SOURCE_CLOCK_UNAVAILABLE

CHECKPOINT_PLACEHOLDER_ARTIFACT_BOUND_EXCEEDED
  -> V2_CHECKPOINT_PLACEHOLDER_ARTIFACT_BOUND

CHECKPOINT_PLACEHOLDER_OBSERVER_INTERNAL_ERROR
  -> V2_CHECKPOINT_PLACEHOLDER_OBSERVER_INTERNAL_ERROR
```

The field envelope validates the reason's closed attempt/error form.
`TargetObservationV2` discharges the predicate only when the complete context
is `STABLE_CHECKPOINT`, has the exact placeholder binding state and
position-matched source context reason, and every one of its 185 fields uses
the corresponding dedicated reason. Any wrong, mixed, null, non-checkpoint,
or exact-marker context rejects. The status-reason vocabulary therefore has
26 members and the context-predicate vocabulary has six.

The historical `TARGET_BOUNDARY_NOT_REACHED`, `SOURCE_CLOCK_UNAVAILABLE`,
`ARTIFACT_BOUND_EXCEEDED`, and `OBSERVER_INTERNAL_ERROR` policy rules and
eligibility remain unchanged. All 185 field definitions and their order
remain unchanged: IDs, value types, units, methods, roles, and operation
applicability do not move. Every descriptor adds all four dedicated
checkpoint-placeholder reasons to its `allowed_status_reasons` tuple. Each
complete descriptor record, the shared policy/vocabulary, and
`target_field_registry_id` regenerate; preserving the historical V1
descriptor or registry ID is forbidden.

The 262,144-byte target-observation ceiling remains provisional until the V2
registry-aware generator proves every operation, binding state, selector
position, and legal value-shape maximum remains strictly below it. A failure
is design NO-GO; the implementation may not truncate or silently raise the
ceiling. The published proof contains a canonical-byte summary for each
operation's independently generated legal-value maximum and, for every entry
of every non-empty catalog selector, the exact-marker state plus all four
placeholder causes. Its witnessed
`(catalog_name, operation_kind, selector_position, binding_state_or_cause)`
set must equal the independently derived required set. Position 64 therefore
has materialized evidence; a literal coverage boolean without the witness set
rejects.

## 9. External type registry

The registry contains exact descriptors for every Step-2 record plus every
external record referenced by a V2 spec, result, selector, observation,
precondition, target-bound descriptor, or replay rule. One descriptor has:

```text
type_name
type_version_tag
type_role = NESTED | STANDALONE
described_record_domain | null
identity_field | null
maximum_canonical_bytes
ordered_member_descriptors
ordered_cross_field_rule_ids
external_type_descriptor_id
```

The descriptor itself is a standalone envelope whose outer
`record_domain` is always
`RiskYieldMMA2MStep2ExternalTypeDescriptorV1V4_9F_RawV8`.
`described_record_domain` is the distinct identity-payload member for the
domain of the type being described: it is non-null exactly for a
`STANDALONE` described type and null exactly for a `NESTED` described type.
Using `record_domain` for this payload member is forbidden because it would
collide with and overwrite the descriptor envelope discriminator.

Member descriptors have exactly:

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

The descriptor ID uses
`RiskYieldMMA2MStep2ExternalTypeDescriptorV1V4_9F_RawV8`. Member positions
start at one and are contiguous; enum tuples and rule IDs are exact and
sorted only where the referenced type defines set rather than sequence
semantics.

The minimum required catalog is:

```text
CapacityMeasurementAckDeadlineExpirySpecV1
CapacityMeasurementAckDeadlineExpiryResultEvidenceV1
CapacityMeasurementDispatchWindowEvidenceV1
CapacityMeasurementDueDecisionClockEvidenceV1
CapacityMeasurementIngressLogicalOracleProfileV1
CapacityMeasurementIngressOperationSpecV2
CapacityMeasurementIngressResultEvidenceV2
CapacityMeasurementLocalShutdownSpecV2
CapacityMeasurementLocalShutdownResultEvidenceV2
CapacityMeasurementLogicalOutputFrameV1
CapacityMeasurementOperationDeclarationV1
CapacityMeasurementOperationSpec
CapacityMeasurementOperationResultEvidence
CapacityMeasurementSubscriptionDispatchSpecV2
CapacityMeasurementSubscriptionDispatchResultEvidenceV2
CheckpointSelectorEntryV1
CheckpointSelectorV1
MarkerContractV1
TargetObservationClockSpanV2
TargetObservationContextV2
TargetFieldObservationV1
TargetObservationV2
TargetObservationRootV2
TargetFieldRegistryV1
OperationCounterSnapshotSchemaV1
OperationCounterSnapshotV1
SourceErrorDetailV1
```

The correction's later external/runtime descriptors are added to this same
registry before target-bound universe acceptance. Step-2 V2 acceptance may be
split into a core-codec subgate and a complete-external-registry subgate, but
the root is not accepted as the target-bound input until the latter contains
every identity named by the universe. Hash-only type assertions, Python
reflection, runtime imports, or schema inference from fixture values are
forbidden.

## 10. Frozen boundary fixture

The independent inventory includes one deliberately small, internally valid
local-shutdown spec fixture:

```text
maximum_terminal_ingress_batches = 1
maximum_terminal_ingress_ciphertext_octets = 16,645
maximum_terminal_ingress_plaintext_octets = 16,384
maximum_terminal_socket_receive_calls = 4
maximum_terminal_tls_records = 1
maximum_terminal_tls_unwrap_iterations = 2
maximum_terminal_zero_progress_iterations = 2
maximum_terminal_ingress_parser_units = 1
maximum_terminal_ingress_automatic_outputs = 1
maximum_websocket_send_attempts = 2
maximum_tls_control_send_attempts = 2
maximum_peer_shutdown_polls = 2
```

This fixture exercises one TLS record, one parser unit, one automatic output,
and both poll positions. It is not a published admissible plan. The later
target-bound generator may accept or reject it only through the canonical
coordinate/ceiling protocol; Step-2 cannot label it profitable, representative
of production load, or sufficient for all shutdown paths.

Boundary fixtures also cover:

- ingress parser/frame counts at 0 and 32,768 and exact plus-one rejection;
- selector lengths 0 and 64 and exact plus-one rejection, including an
  attempted-ON empty-selector root with non-null selector ID;
- root counts 3 and 67 and exact plus-one rejection;
- result bytes immediately below and at/above the 524,288 ceiling;
- every local limit relation at equality and independent one-field violation;
- subscription KA/KR cardinality 1 and 256 and exact plus-one rejection; and
- all three checkpoint-binding states with one-field falsification.

## 11. Required implementation and acceptance evidence

Implementation order is:

1. freeze exact document bytes and update the parent/correction cross-links;
2. implement V2 tags, nested spec/result records, validators, selector,
   marker-contract, oracle-profile, and observation codecs in the private
   production module;
3. independently encode the V2 inventory generator without production imports;
4. update the isolated child harness and parent process-isolation tests;
5. explicitly write the new golden once, then require `--check`;
6. run full Step-2 mutation, byte, import, and semantic replay tests;
7. re-run Raw V7 inventory and final-tree compatibility;
8. publish a new V2 acceptance audit with exact hashes only after one stable
   tree passes.

Mandatory adversarial evidence includes:

- all six removed V1 tags and relabelled old bodies reject;
- tag/body/operation cross-product mutations reject;
- every V2 field missing, extra, null, wrong type, wrong bound, and wrong
  duplicated ID rejects;
- every spec/result equality and local-shutdown limit relation is independently
  falsified;
- topic trimming, NFC, control, 256/257-code-point, and 1,024-byte boundaries;
- selector wrong operation/kind/order/position/occurrence/ID, duplicate entry,
  empty selector, and 64-entry selector;
- exact-marker and both placeholder states, error mapping, span truth, and all
  185 placeholder fields;
- V1/V2 observation/context/root substitution and flattened/embedded shape
  substitution;
- canonical worst-case observations/results remain under their ceilings;
- inventory duplicate-key, noncanonical number, nonfinite, path/hash,
  grouping, catalog-order, type-descriptor, and semantic-ID mutations reject;
- generator code has no `riskyieldmm` import and runs under `python -I -B`;
- production package exports remain unchanged and V8 types remain private;
- Raw V7 schema, fingerprints, record bytes, and accepted regression inventory
  remain unchanged.

Acceptance commands must include:

```text
python scripts/tests/generate_raw_v8_step2_inventory_v49f.py \
  --check --repository-root .

python -I -B tests/_raw_v8_step2_contract_harness_v49f.py

python -m pytest -q \
  tests/test_trading_physical_transport_capacity_contracts_v49f_v8_isolated.py

python scripts/tests/verify_raw_v7_regression_inventory_v49f.py --check
```

Compilation, scoped Ruff check/format check, `git diff --check`, exact artifact
hashes, temporary-output cleanup, public-surface audit, and explicit worktree
review are required. Passing this gate establishes only a reproducible causal
contract input. It does not establish target-bound admissibility, runtime
neutrality, live-trading readiness, predictive edge, or profitability.
