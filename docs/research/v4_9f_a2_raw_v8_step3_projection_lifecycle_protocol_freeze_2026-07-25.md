# V4.9F-A2 Raw V8 Step-3 Projection and Lifecycle Protocol Freeze

**Freeze date:** 2026-07-25  
**Status:** Design correction is active after an independent implementation
readiness audit returned NO-GO on 2026-07-26. Projection fingerprinting and
lifecycle implementation are halted until the recovery, identity, byte-bound,
truth-table, timing, initialization, and parent-protocol corrections below are
reconciled and independently rechecked. Nothing in this document accepts Raw
V8, A2-M, a threshold, A2-E, the public live factory, Stage 1, production
readiness, trading edge, or profitability.

**Parent protocol:**
[`v4_9f_a2_marker_operation_target_v8_protocol_freeze_2026-07-22.md`](v4_9f_a2_marker_operation_target_v8_protocol_freeze_2026-07-22.md)

**Historical Step-2 V1 predecessor:**
[`v4_9f_a2_raw_v8_step2_acceptance_audit_2026-07-25.md`](v4_9f_a2_raw_v8_step2_acceptance_audit_2026-07-25.md)

**Current Step-2 V2 machine-contract input:**
[`v4_9f_a2_raw_v8_step2_v2_contract_freeze_2026-07-26.md`](v4_9f_a2_raw_v8_step2_v2_contract_freeze_2026-07-26.md)

**Initializer sub-slice:**
[`v4_9f_a2_raw_v8_initializer_technical_acceptance_2026-07-26.md`](v4_9f_a2_raw_v8_initializer_technical_acceptance_2026-07-26.md)

**Normative active correction:**
[`v4_9f_a2_raw_v8_step3_target_and_lifecycle_correction_2026-07-26.md`](v4_9f_a2_raw_v8_step3_target_and_lifecycle_correction_2026-07-26.md)

The correction and current Step-2 V2 freeze govern every conflicting
target-span, operation-shape, checkpoint, marker/probe, finalization, recovery,
and bound statement in this child until the text is fully reconciled and
reaccepted. A conflict between those two current documents is global NO-GO.

## 1. Decision

Step 3 introduces a fresh, immutable Raw V8 projection profile and exact
candidate-to-closure lifecycle. It must reuse one authoritative
`canonical_records` / `receipts` / `operation_batches` chain with the existing
RAW and actor records. It must not:

- reinterpret a Raw V7 attempt as a V8 candidate;
- add V8 tables to an already initialized Raw V7 database;
- migrate a Raw V7 ledger in place;
- use a sidecar database for lifecycle records;
- change Raw V7 domains, table definitions, codecs, constants, or default
  store behavior; or
- expose a caller-selected schema-mode flag.

The exact projection identities are:

```text
schema_version     = riskyieldmm_physical_projection_v4_9f_raw_v8
validation_version = riskyieldmm_physical_projection_validation_v4_9f_raw_v8
fingerprint_domain = RiskYieldMMPhysicalProjectionSchemaFingerprintV4_9F_RawV8
max_object_bytes   = 25165824
```

The 25,165,824-byte store ceiling is exactly 24 MiB, the frozen maximum for one
canonical marker closure. The record-specific ceilings are 4 MiB for a
candidate and 1 MiB each for an attempt and terminal. A fresh V8 store uses a
new schema fingerprint and ledger identity. A V7 store rejects the V8
metadata/fingerprint/schema, while a V8 store rejects V7 metadata/fingerprint
and any nonempty inherited V7 lifecycle surface.

The implementation modules are:

```text
riskyieldmm/trading/physical_transport_capacity_lifecycle_v49f_v8.py
riskyieldmm/trading/physical_projection_v49f_v8.py
```

The first is a pure canonical contract/replay layer. The second is a new
`PhysicalProjectionStoreV49FV8` over a narrowly profile-aware reuse of the
accepted projection engine. The existing `PhysicalProjectionStoreV4` remains
unconditionally pinned to the exact Raw V7 profile.

## 2. Why the profile boundary is mandatory

The current Raw V7 projection code hard-codes its schema and validation
versions and certifies the complete SQLite schema. Adding tables to an opened
V7 database would change the schema fingerprint while leaving V7 metadata
behind. A sidecar would break the required receipt order:

```text
candidate
optional attempt
existing target RAW / actor records
terminal
marker closure
```

and could not atomically commit terminal plus closure.

The pre-refactor Raw V7 preservation goldens are:

| Surface | Frozen value |
|---|---|
| `_SCHEMA_SQL` UTF-8 bytes | 121,640 |
| `_SCHEMA_SQL` SHA-256 | `d288f934fba970b1e7240a62ada0e5a11e9901aa25d7e43351a473e4fd3192b7` |
| `_FULL_SCHEMA_SQL` UTF-8 bytes | 136,483 |
| `_FULL_SCHEMA_SQL` SHA-256 | `d4b311050f20f03159cd7d121421535e36f45a1d56d42022345ab9fdfcf088e5` |
| Certified schema fingerprint | `7aefd863c3c6773d357d2ec638bf1c212055fcacfbec406e10030e184f599d98` |

The profile refactor must preserve all five values and the existing Raw V7
ledger/record/receipt/request identities.

## 3. Initialization and transaction correction

Python 3.12 documents that `sqlite3.Connection.executescript()` implicitly
commits a pending transaction before executing the script. A direct probe of
the qualified runtime confirmed:

```text
BEGIN IMMEDIATE       -> in_transaction = true
executescript(schema) -> in_transaction = false
```

Therefore V8 does not copy the historical V7 sequence
`BEGIN IMMEDIATE` followed by `executescript(schema)` and then assume the
metadata insert shares that transaction. Its exact profile places
`BEGIN IMMEDIATE;` at the beginning of the one static schema script, leaves
that transaction open, inserts parameterized metadata, and explicitly commits.

The atomicity claim is about committed database state, not about filesystem
path absence. SQLite may leave a zero-length main file or journal/WAL artifacts
without any committed schema. After an interrupted initialization, reopening
under the same provisioning authority must classify exactly one of:

```text
INITIALIZED
  complete certified V8 schema, exactly one matching metadata row, exact
  ledger derivation, and successful full verification

UNINITIALIZED
  no committed application schema and no committed metadata row

CORRUPT_OR_WRONG_PROFILE
  every other state, including a partial schema, metadata without the exact
  schema, wrong-profile metadata, or an unverifiable initialized database
```

Initialization uses the Linux local-filesystem provisioning profile:

```text
database path:
  absolute lexical path; no supported symlink/hard-link alias

parent directory:
  exact final path component is a directory
  owned by the effective UID
  no group-write or world-write bit

lease path:
  <parent>/.<database-filename>.riskyieldmm-projection-provision.lock

lease open:
  O_RDWR | O_CREAT | O_CLOEXEC | O_NOFOLLOW
  requested mode 0600
  exact regular file, one link, effective-UID owner
  no group/world permission bit
  opened descriptor and named path have the same device/inode

lease acquisition:
  LOCK_EX | LOCK_NB
  retry for at most 5.0 observer-monotonic seconds
  then typed busy rejection
```

The lease is acquired before the first database existence/stat/open decision
and retained through schema commit, fresh-connection commit-outcome replay,
connection close, and failure handling. The descriptor/path identity is
revalidated before the database-state decision, before COMMIT resolution, and
before release. The persistent lock inode is never unlinked: deleting it after
unlock can split waiters across different inodes.

The exact `UNINITIALIZED` committed-state query, after opening/configuring
SQLite so any hot journal can be resolved, is:

```sql
SELECT count(*)
FROM sqlite_schema
WHERE name NOT LIKE 'sqlite_%' AND sql IS NOT NULL
```

Only exact integer zero is `UNINITIALIZED`. A query error, missing result,
nonzero partial schema, unreadable/non-SQLite bytes, wrong metadata, wrong
fingerprint, or failed verification is `CORRUPT_OR_WRONG_PROFILE`. V8 failure
handling is deliberately non-destructive: it never unlinks the main file or
sidecars. A later lease-held opener can initialize a zero-object path or
diagnose retained corrupt evidence without a check-to-unlink race.

Two supported V8 creators serialize under the lease; the second reopens and
validates the winner. Supported cross-profile provisioning uses the same
profile-neutral lease. This lease is the sole permitted Raw V7 constructor
safety correction: Raw V7 schema bytes, identities, transaction statements,
codecs, and public semantics remain unchanged and the complete V7 inventory
must be reaccepted. Sequential V7/V8 profile substitution still rejects
through metadata and certified schema replay.

`flock()` is advisory. The guarantee covers participating constructors in one
owned protected directory, not a malicious same-UID namespace mutator or a
process that ignores the lease. Stronger hostile-operator protection requires
a supervisor-owned directory or external lock authority and is outside this
local profile.

Fault tests must therefore prove that a failed/crashed initialization leaves
either `UNINITIALIZED` committed state or one complete self-consistent V8
database. File absence is permitted but not required. A fault after COMMIT but
before acknowledgement is resolved through a newly opened connection to the
same retained device/inode under the lease; it must not use a possibly poisoned
connection or unlink the committed database. `SQLITE_BUSY` with an active
transaction is explicitly rolled back and reported, not misclassified as a
committed acknowledgement loss.

SQLite permits only one write transaction at a time, `BEGIN IMMEDIATE` may
return `SQLITE_BUSY`, a failed `COMMIT` can leave a transaction active, and
`FULL` / `IOERR` / `INTERRUPT` / `NOMEM` can affect either the current statement
or the whole transaction. The store must query its actual transaction state,
roll back explicitly when possible, and resolve uncertain outcomes by replay.
It must not map every SQLite error to “not committed.”

## 4. Exact domains and record kinds

The lifecycle schema literal remains:

```text
riskyieldmm_physical_transport_a2m_raw_v49f_v8
```

New canonical domains:

```text
RiskYieldMMA2MAdmissionOutcomeEvidenceV4_9F_RawV8
RiskYieldMMA2MOperationCandidateV4_9F_RawV8
RiskYieldMMA2MOperationAttemptV4_9F_RawV8
RiskYieldMMA2MOperationTerminalV4_9F_RawV8
RiskYieldMMA2MMarkerV4_9F_RawV8
RiskYieldMMA2MLoopProbeV4_9F_RawV8
RiskYieldMMA2MMarkerClosureV4_9F_RawV8
RiskYieldMMA2MRecoveredOperationPrefixV4_9F_RawV8
RiskYieldMMA2MOperationPrefixV4_9F_RawV8
RiskYieldMMA2MFinalizationObservationV4_9F_RawV8
RiskYieldMMPhysicalProjectionRequestV4_9F_RawV8
```

Exactly four new kinds receive projection receipts:

```text
CAPACITY_MEASUREMENT_OPERATION_CANDIDATE_V49F_V8
CAPACITY_MEASUREMENT_OPERATION_ATTEMPT_V49F_V8
CAPACITY_MEASUREMENT_OPERATION_TERMINAL_V49F_V8
CAPACITY_MEASUREMENT_MARKER_CLOSURE_V49F_V8
```

Individual markers, extrema, probes, observation contexts, field
observations, target observations, target roots, and operation results remain
strict nested records. They do not create projection receipts.

## 5. Exact lifecycle vocabularies

Step 3 reuses the exact Step-2 operation, instrumentation, marker-kind,
status-reason, result, target-field, availability, and observation enums. It
adds:

```text
AdmissionWaitEvidenceV8
  EXACT
  RIGHT_CENSORED_LOWER_BOUND
  NOT_APPLICABLE_IMMEDIATE_REJECTION
  UNAVAILABLE_PROCESS_LOSS

AdmissionGateAfterSnapshotAvailabilityV8
  EXACT
  UNAVAILABLE_OBSERVER_FAILURE
  UNAVAILABLE_PROCESS_LOSS

TargetAuthorizationOutcomeV8
  NOT_REACHED_NON_GRANT
  ATTEMPT_COMMITTED
  ATTEMPT_PERSISTENCE_FAILED
  UNRESOLVED_PROCESS_LOSS

LifecycleTerminalTriggerV8
  RETURNED
  RAISED_EXCEPTION
  CANCELLED
  INTERRUPTED
  RECOVERED_ORPHAN

LifecycleTerminalWriterV8
  SAME_TASK
  STARTUP_RECOVERY

LifecycleCancellationV8
  NONE
  ASYNCIO_CANCELLED_ERROR
  PROCESS_LOSS_UNKNOWN

LifecycleEffectCertaintyV8
  NO_DURABLE_EFFECT
  EXACT_COMPLETED_PREFIX
  COMPLETE
  UNKNOWN

LifecycleProgressAvailabilityV8
  EXACT_RETURNED_RESULT
  EXACT_DURABLE_PREFIX
  UNAVAILABLE

LifecycleProgressUnavailableReasonV8
  TARGET_NOT_AUTHORIZED

SessionTerminalAuthorityV8
  DURABLE_ACTOR_TERMINAL
  VOLATILE_RUNTIME_FAULT_LATCHED
  NONTERMINAL_RUNTIME
  UNAVAILABLE_AFTER_ORPHAN

OperationResultUnavailableReasonV8
  TARGET_RAISED_EXCEPTION
  TARGET_CANCELLED
  TARGET_INTERRUPTED
  PROCESS_LOSS_BEFORE_RESULT
  RESULT_EVIDENCE_BOUND_EXCEEDED
  RESULT_EVIDENCE_VALIDATION_FAILED
  UNKNOWN_DELIVERY_PREFIX

MarkerCaptureStatusV8
  COMPLETE
  PARTIAL
  UNAVAILABLE

MarkerObserverErrorCodeV8
  CAPABILITY_MISMATCH
  CLOCK_READ_FAILED
  CLOCK_REGRESSION
  COUNTER_ACCUMULATOR_FAILED
  MARKER_SLOT_CONVERSION_FAILED
  SAFE_INTEGER_OR_BOUND_EXCEEDED

MarkerObserverFailurePhaseV8
  NONE
  BEFORE_FIRST_TRUTHFUL_MARKER
  AFTER_TRUTHFUL_MARKER_PREFIX
  MARKER_SLOT_CONVERSION
  CLOSURE_SEAL_CLOCKS

LoopProbeObserverErrorCodeV8
  CLOCK_READ_FAILED
  CLOCK_REGRESSION
  PROBE_ARITHMETIC_FAILED
  PROBE_CALLBACK_FAILED
  PROBE_SCHEDULE_FAILED
  PROBE_SLOT_CONVERSION_FAILED
  SAFE_INTEGER_OR_BOUND_EXCEEDED

LoopProbeObserverFailurePhaseV8
  NONE
  BEFORE_FIRST_SCHEDULE
  AFTER_SCHEDULE_BEFORE_FIRST_CALLBACK
  AFTER_CALLBACK_PREFIX
  PROBE_SLOT_CONVERSION

LoopProbeStatusV8
  DISABLED
  COMPLETE
  PARTIAL
  UNAVAILABLE

ClosureClockAvailabilityV8
  EXACT_SAME_PROCESS
  NOT_OBSERVED_INSTRUMENTATION_OFF
  UNAVAILABLE_OBSERVER_FAILURE
  UNAVAILABLE_PROCESS_LOSS

FinalizationAvailabilityV8
  EXACT_SAME_PROCESS
  UNAVAILABLE_OBSERVER_FAILURE
  UNAVAILABLE_COMMIT_ACKNOWLEDGEMENT
  UNAVAILABLE_PROCESS_LOSS

AttemptPreconditionTypeV8
  INGRESS_PRECONDITION_V1
  SUBSCRIPTION_DISPATCH_PRECONDITION_V1
  ACK_DEADLINE_EXPIRY_PRECONDITION_V1
  LOCAL_SHUTDOWN_PRECONDITION_V1
```

The ambiguous prose alias `NO_DURABLE_TARGET_EFFECT` is rejected.
`NO_DURABLE_EFFECT` is the only canonical spelling. V8 uses
`EXACT_RETURNED_RESULT`, not V7's ingress-specific returned-progress spelling.

## 6. A1 snapshot and admission outcome

`CapacityMeasurementA1CounterSnapshotV49FV8` contains exactly:

```text
policy_id
admission_epoch
closed
terminal_barrier_admission_sequence | null
terminal_barrier_committed
active_admission_sequence | null
active_command_kind | null
waiting_admission_sequences
waiting_command_kinds
oldest_waiting_age_nanoseconds
reserved_work_units
maximum_observed_admitted_commands
maximum_observed_reserved_work_units
last_started_queue_wait_nanoseconds
maximum_observed_queue_wait_nanoseconds
rejected_commands
duplicate_kind_rejections
terminal_barrier_rejections
capacity_rejections
closed_rejections
timed_out_commands
cancelled_before_entry_commands
closed_before_entry_commands
released_commands
```

`active_count` and `waiting_count` are derived and never duplicated.

`CapacityMeasurementAdmissionOutcomeEvidenceV49FV8` contains:

```text
candidate_id
outcome
policy_id
admission_epoch
command_kind
reservation_work_units
admission_sequence | null
admitted_loop_time_ns | null
started_loop_time_ns | null
start_deadline_loop_time_ns | null
wait_duration_evidence
wait_duration_nanoseconds | null
rejection_class | null
gate_counter_snapshot_before
gate_counter_snapshot_after_availability
gate_counter_snapshot_after | null
outcome_evidence_id
```

Truth table:

| Outcome path | Ticket coordinates | Wait evidence | Rejection | After snapshot |
|---|---|---|---|---|
| `GRANTED` | sequence and all three loop times required | `EXACT`; wait equals `started - admitted` | null | exact or explicitly unavailable after observer failure |
| Immediate `REJECTED` | all null | `NOT_APPLICABLE_IMMEDIATE_REJECTION`; wait null | capacity, duplicate-kind, or terminal-barrier | exact or explicitly unavailable after observer failure |
| Ticketed non-grant | sequence, admitted time, and deadline required; started null | `RIGHT_CENSORED_LOWER_BOUND`; wait non-null | exact matching class | exact or explicitly unavailable after observer failure |
| Same-process non-ticket close/failure/interruption/cancellation | all null | `NOT_APPLICABLE_IMMEDIATE_REJECTION`; wait null | exact matching class | exact or explicitly unavailable after observer failure |
| `UNRESOLVED_PROCESS_LOSS` | all volatile ticket coordinates null | `UNAVAILABLE_PROCESS_LOSS`; wait null | null | `UNAVAILABLE_PROCESS_LOSS`, snapshot null |

`CANCELLED_BEFORE_ENTRY`, `CLOSED_BEFORE_ENTRY`, `TIMED_OUT`,
`INTERRUPTED_BEFORE_ENTRY`, and `FAILED_BEFORE_ENTRY` require their matching
rejection class whenever same-process evidence exists. The candidate embeds
the exact before-snapshot; the outcome's before-snapshot must match it
byte-for-byte.

The before snapshot is never nullable: inability to construct it prevents
candidate persistence. `gate_counter_snapshot_after_availability=EXACT` is
equivalent to a present after snapshot. Either unavailable value requires a
null after snapshot. `UNAVAILABLE_OBSERVER_FAILURE` is same-process only and
does not erase already observed direct outcome or grant facts or change target
control flow. `UNAVAILABLE_PROCESS_LOSS` is legal only for candidate-only
startup recovery with outcome and authorization
`UNRESOLVED_PROCESS_LOSS`, no attempt, unavailable wait evidence, null
rejection, and null volatile ticket coordinates. Attempted recovery reuses the
byte-exact outcome already committed in the attempt. It never reconstructs or
re-samples A1. Copying the before snapshot into an unknown after position is
forbidden.

When both snapshots are exact, validation checks the observable ticket
transition: a grant moves the target sequence/kind to active and fixes its
queue wait; an immediate rejection increments its exact rejection class
without a ticket; a ticketed non-grant removes the ticket and releases its
reservation. Pre-A1 cancellation, interruption, or failure cannot fabricate a
gate mutation.

## 7. Candidate and durable baseline

`CapacityMeasurementOperationCandidateV49FV8` contains:

```text
declaration
declaration_id
operation_spec_id
operation_kind
previous_operation_terminal_id | null

transport_session_id
driver_evidence_nonce_sha256
kernel_socket_identity
socket_lease_id
transport_capacity_policy
transport_capacity_policy_id

projection_ledger_id
projection_schema_version
projection_validation_version
projection_schema_fingerprint
projection_store_observation_id
writer_fence_token_sha256
writer_fence_generation
pre_candidate_receipt_sequence
pre_candidate_receipt_hash

pre_admission_gate_snapshot
pre_admission_baseline

instrumentation_mode
marker_contract_id
target_field_registry_id

observer_origin_ns
boottime_origin_ns
loop_time_origin_ns
process_cpu_origin_ns
thread_cpu_origin_ns
monotonic_clock_domain_id

candidate_precommit_observer_offset_ns
candidate_precommit_boottime_offset_ns
candidate_precommit_loop_offset_ns
candidate_precommit_process_cpu_offset_ns
candidate_precommit_thread_cpu_offset_ns
candidate_precommit_wall_time
candidate_id
```

The candidate embeds the one byte-exact Step-2 declaration and binds its
declaration/spec identities and operation tag. This makes a candidate-only
startup recovery self-contained even when the external manifest is
unavailable. The declaration body occurs nowhere else in the operation prefix
or sample. Replay also resolves its identity against the signed
manifest/workload schedule and rejects a missing, duplicated, substituted, or
tag-mismatched declaration.

The candidate clock members are normatively
`candidate_precommit_*`: they are sampled once after every other candidate
member and preallocated observer state is fixed and immediately before
`BEGIN IMMEDIATE`. They are not candidate-commit timestamps. The candidate
receipt is the durable boundary. Absolute origins are canonical unsigned
uint128 decimal text. Relative offsets are safe unsigned integers. Wall time
is forensic UTC only.

`previous_operation_terminal_id` is null exactly for operation sequence one.
Otherwise it identifies the immediately preceding V8 terminal in the same
campaign and session, and that terminal must have its matching closure.

`CapacityMeasurementDurableBaselineV49FV8` contains:

```text
raw_ingress_sequence
raw_ingress_commit_id | null
retained_raw_dependencies

actor_event_count
actor_tail_event_id | null
actor_event_kind_counts

parser_cursor
parser_cursor_id
retained_ingress_tail_id
retained_ingress_tail_octets
initial_pending_raw_ingress_present

runtime_state
actor_terminal_state
actor_terminal_state_id
actor_fault_latched
actor_activation_in_progress
oldest_outbound_wire_event_id | null
pending_automatic_protocol_output
last_terminal_convergence_event_id | null

fragmented_message_octets
fragmented_message_parser_event_ids

retained_subscription_intent_id | null
dispatch_window_evidence_id | null
subscription_ack_binding_id | null
```

Retained RAW witnesses use the V7 receipt shape and are limited to 64.
Fragment/parser sequences use the existing bounded cursor limits. The exact
25-position actor-kind tuple is ascending UTF-8:

```text
ACK_DEADLINE_EXPIRED
APPLICATION_MESSAGE_COMMITTED
KERNEL_SEND_ATTEMPT
KERNEL_SEND_FAILURE
KERNEL_SEND_RESULT
LOCAL_SHUTDOWN_COMMAND_STARTED
LOCAL_SHUTDOWN_DEADLINE_EVIDENCE
OUTBOUND_DISPATCH_COMPLETED
OUTBOUND_WIRE_PREPARED
PARSER_TRANSITION
RAW_INGRESS_COMMITTED
SUBSCRIPTION_ACK_BOUND
TCP_HALF_CLOSE_ATTEMPT
TCP_HALF_CLOSE_RESULT
TERMINAL_INGRESS_FAILURE
TERMINAL_TRANSITION
TLS_CIPHERTEXT_PREPARED
TLS_CONTROL_CIPHERTEXT_PREPARED
TLS_CONTROL_KERNEL_SEND_ATTEMPT
TLS_CONTROL_KERNEL_SEND_FAILURE
TLS_CONTROL_KERNEL_SEND_RESULT
TLS_PROTOCOL_OPERATION_FAILED
TLS_PROTOCOL_OPERATION_STARTED
TLS_SHUTDOWN_OBSERVED
WRITE_PERMIT_CONSUMED
```

The tuple sums to `actor_event_count`. Zero actor count requires a null tail
and 25 zero counts. The attempt's durable coordinates equal the candidate's in
the base serial profile. Any intervening receipt before the attempt rejects.

## 8. Attempt and operation preconditions

`CapacityMeasurementOperationAttemptV49FV8` contains:

```text
candidate_id
admission_outcome_evidence
admission_outcome_evidence_id

declaration_id
operation_spec_id
operation_kind
previous_operation_terminal_id | null

transport/session/socket/policy authority duplicated from candidate
projection/store/writer-fence authority duplicated from candidate

pre_attempt_receipt_sequence
pre_attempt_receipt_hash
durable_baseline
operation_precondition

instrumentation_mode
marker_contract_id
marker_capacity
full_checkpoint_selector_id
loop_probe_interval_ns
loop_probe_capacity
target_field_registry_id

attempt_precommit_observer_offset_ns
attempt_precommit_boottime_offset_ns
attempt_precommit_loop_offset_ns
attempt_precommit_process_cpu_offset_ns
attempt_precommit_thread_cpu_offset_ns
attempt_precommit_wall_time
attempt_id
```

The admission outcome must be exact `GRANTED`.
`pre_attempt_receipt_sequence/hash` identify the candidate receipt itself.
No durable record may intervene. The attempt does not duplicate the candidate's
declaration body; it binds the exact candidate/declaration/spec/tag and embeds
the granted outcome once.

The `attempt_precommit_*` clocks are sampled after the exact grant and
precondition are fixed and before the attempt transaction. They measure
authorization-persistence latency, not target-effect start. The authoritative
target-effect start is `TARGET_EFFECT_ENTRY`, emitted after the attempt receipt
commits and immediately before the first target mutation. OFF and process-loss
paths make no target-duration claim from precommit-clock subtraction.

The exact precondition variants are:

```text
IngressPreconditionV1
  runtime_state
  parser_cursor_id
  parser_state
  retained_ingress_tail_id
  retained_ingress_tail_octets
  initial_pending_raw_ingress_present
  actor_terminal_state_id
  actor_fault_latched
  actor_activation_in_progress
  oldest_outbound_wire_event_id
  pending_automatic_protocol_output

SubscriptionDispatchPreconditionV1
  runtime_state
  retained_subscription_intent_id
  retained_request_id
  retained_command_sha256
  retained_logical_payload_sha256
  parser_cursor_id
  parser_state
  retained_ingress_tail_octets
  initial_pending_raw_ingress_present
  actor_terminal_state_id
  actor_fault_latched
  actor_activation_in_progress
  oldest_outbound_wire_event_id
  pending_automatic_protocol_output
  application_fence_token_sha256
  application_fence_generation

AckDeadlineExpiryPreconditionV1
  runtime_state
  retained_subscription_intent_id
  dispatch_window_evidence
  dispatch_window_evidence_id
  committed_ack_deadline_at
  committed_ack_deadline_monotonic_ns
  monotonic_clock_domain_id
  parser_cursor_id
  parser_state
  retained_ingress_tail_octets
  initial_pending_raw_ingress_present
  subscription_ack_binding_id
  actor_terminal_state_id
  actor_fault_latched
  actor_activation_in_progress
  oldest_outbound_wire_event_id
  pending_automatic_protocol_output

LocalShutdownPreconditionV1
  runtime_state
  parser_cursor_id
  parser_state
  retained_ingress_tail_octets
  initial_pending_raw_ingress_present
  fragmented_message_octets
  fragmented_message_parser_event_ids
  actor_terminal_state
  actor_terminal_state_id
  peer_first_close_converged
  actor_fault_latched
  actor_activation_in_progress
  oldest_outbound_wire_event_id
  pending_automatic_protocol_output
  last_terminal_convergence_event_id
```

The variant tag must equal the declaration operation kind.

The current shutdown runtime creates the command deadline inside
`start_local_shutdown_command_v49e()`, after effect entry. Persisting that
deadline in the attempt is impossible without moving a target mutation before
the pre-effect receipt. The attempt therefore contains only the signed timeout
and exact precondition; the durable shutdown-command prefix/result proves the
created deadline. The implementation must not change target ordering merely to
make a measurement field easier to populate.

The ACK attempt may retain its already committed deadline and dispatch window.
The governed due-decision bracket is a target result/prefix fact, not a
pre-attempt fact.

## 9. Terminal

`CapacityMeasurementOperationTerminalV49FV8` contains:

```text
candidate_id
attempt_id | null
operation_kind
previous_operation_terminal_id | null

admission_outcome_evidence | null
admission_outcome_evidence_id
target_authorization_outcome

terminal_writer
terminal_trigger
cancellation_classification
effect_certainty
progress_availability
progress_unavailable_reason | null
operation_error_code | null

surfaced_exception_class | null
exception_class_chain
exception_message_sha256_chain

operation_result_evidence | null
result_evidence_id | null
operation_result_unavailable_reason | null

terminal_raw_ingress_sequence
terminal_raw_ingress_commit_id | null
terminal_actor_event_count
terminal_actor_tail_event_id | null
parser_cursor_id_after
runtime_state_after | null
actor_terminal_state_id_after
actor_terminal_outcome | null
actor_terminal_cause_code | null
session_terminal_authority

recovered_prefix_id

terminal_preobservation_observer_offset_ns | null
terminal_preobservation_boottime_offset_ns | null
terminal_preobservation_loop_offset_ns | null
terminal_preobservation_process_cpu_offset_ns | null
terminal_preobservation_thread_cpu_offset_ns | null
terminal_preobservation_wall_time | null
terminal_id
```

The attempt/outcome body is serialized exactly once. An attempted terminal
stores only the outcome ID already committed inside the attempt and requires
`admission_outcome_evidence=null`. A no-attempt terminal embeds its exact
outcome and matching ID.

Trigger and authorization truth:

| Durable path | Writer / trigger / cancellation | Authorization |
|---|---|---|
| Same-process `REJECTED`, `TIMED_OUT`, `CLOSED_BEFORE_ENTRY`, or `FAILED_BEFORE_ENTRY` | `SAME_TASK / RAISED_EXCEPTION / NONE` | `NOT_REACHED_NON_GRANT` |
| Same-process `CANCELLED_BEFORE_ENTRY` | `SAME_TASK / CANCELLED / ASYNCIO_CANCELLED_ERROR` | `NOT_REACHED_NON_GRANT` |
| Same-process `INTERRUPTED_BEFORE_ENTRY` | `SAME_TASK / INTERRUPTED / NONE` | `NOT_REACHED_NON_GRANT` |
| Exact `GRANTED`, attempt conclusively absent after persistence failure | same-process trigger/cancellation matching the actual persistence exit | `ATTEMPT_PERSISTENCE_FAILED` |
| Candidate-only process-loss recovery | `STARTUP_RECOVERY / RECOVERED_ORPHAN / PROCESS_LOSS_UNKNOWN` | `UNRESOLVED_PROCESS_LOSS` |
| Durable attempt, target returned/raised/cancelled/interrupted | `SAME_TASK` and the exact matching trigger/cancellation | `ATTEMPT_COMMITTED` |
| Durable attempted process-loss recovery | `STARTUP_RECOVERY / RECOVERED_ORPHAN / PROCESS_LOSS_UNKNOWN` | `ATTEMPT_COMMITTED` |

An attempt is present exactly for `ATTEMPT_COMMITTED`. Result/progress truth:

An attempt-persistence exit is terminalled only after fresh projection replay
conclusively proves that the attempt receipt is absent. Its exact mapping is:

| Persistence exit | Writer / trigger / cancellation / error | Exception evidence |
|---|---|---|
| ordinary `Exception` other than cancellation | `SAME_TASK / RAISED_EXCEPTION / NONE / PYTHON_EXCEPTION` | bounded safe chain required |
| `asyncio.CancelledError` | `SAME_TASK / CANCELLED / ASYNCIO_CANCELLED_ERROR / ASYNCIO_CANCELLED_ERROR` | head exactly `asyncio.exceptions.CancelledError` |
| non-cancellation `BaseException` | `SAME_TASK / INTERRUPTED / NONE / PYTHON_BASE_EXCEPTION` | bounded safe chain required |

There is no `RETURNED` attempt-persistence-failure terminal. An unresolved
commit acknowledgement is replayed under the store lease. If replay cannot
prove exactly present or absent, no terminal is written and the open locator
remains operator-visible.

| Path | Result evidence | Result-unavailable reason | Progress |
|---|---|---|---|
| Any no-attempt path | null | null | `UNAVAILABLE / TARGET_NOT_AUTHORIZED` |
| Returned, valid operation-exact result | required | null | `EXACT_RETURNED_RESULT`, no progress reason |
| Returned, result conversion exceeds its bound | null | `RESULT_EVIDENCE_BOUND_EXCEEDED` | `EXACT_DURABLE_PREFIX`, no progress reason |
| Returned, result conversion/contract validation fails | null | `RESULT_EVIDENCE_VALIDATION_FAILED` | `EXACT_DURABLE_PREFIX`, no progress reason |
| Target raised | null | `TARGET_RAISED_EXCEPTION` | `EXACT_DURABLE_PREFIX`, no progress reason |
| Target cancelled | null | `TARGET_CANCELLED` | `EXACT_DURABLE_PREFIX`, no progress reason |
| Target interrupted | null | `TARGET_INTERRUPTED` | `EXACT_DURABLE_PREFIX`, no progress reason |
| Subscription has an exact unresolved local-delivery prefix | null | `UNKNOWN_DELIVERY_PREFIX` | `EXACT_DURABLE_PREFIX`, no progress reason |
| Attempted process-loss recovery | null | `PROCESS_LOSS_BEFORE_RESULT` | `EXACT_DURABLE_PREFIX`, no progress reason |

An attempted-prefix replay failure or corruption does not become
"unavailable": no terminal is created, the locator stays open, and recovery
fails closed. A present result's tagged operation must equal the declaration
and is checked by
`validate_capacity_measurement_result_against_spec_v49f_v8()`.
`UNKNOWN_DELIVERY_PREFIX` is subscription-only and requires an unmatched
durable local-send state.

Error codes are exact: `RETURNED -> null`,
`RAISED_EXCEPTION -> PYTHON_EXCEPTION`,
`CANCELLED -> ASYNCIO_CANCELLED_ERROR`,
`INTERRUPTED -> PYTHON_BASE_EXCEPTION`, and
`RECOVERED_ORPHAN -> PROCESS_LOSS_UNKNOWN`. Returned and recovery paths have
no surfaced exception chain. Raised/cancelled/interrupted paths retain the
bounded safe chain; cancellation's head is exactly
`asyncio.exceptions.CancelledError`.

The non-serialized `DurableEffectPrefixClassV8` is derived only by
projection/actor replay as `EMPTY`, `EXACT_STABLE_PREFIX`, or
`UNRESOLVED_EFFECT`; callers cannot supply it. Effect certainty is:

| Path | Effect certainty |
|---|---|
| Any no-attempt path | `NO_DURABLE_EFFECT` |
| Returned with a valid result and complete operation oracle | `COMPLETE` |
| Same-process return with unusable result, raise, cancellation, or interruption | prefix class: empty `NO_DURABLE_EFFECT`; stable `EXACT_COMPLETED_PREFIX`; unresolved `UNKNOWN` |
| Subscription unknown-delivery path | `UNKNOWN` |
| Attempted recovery with empty prefix | `UNKNOWN` |
| Attempted recovery with nonempty stable prefix | `EXACT_COMPLETED_PREFIX` |
| Attempted recovery with unresolved effect state | `UNKNOWN` |

`NO_DURABLE_EFFECT` means only that no durable target-effect record exists; it
does not prove that no physical I/O occurred. In particular, an attempted
process can consume owner input before RAW persistence, and ACK-not-due can
return without an actor record. Therefore an empty attempted recovery prefix
is always `UNKNOWN`.

RAW sequence/tail, actor count/tail, parser cursor ID, and actor terminal-state
ID are reconstructed from the candidate baseline plus the exact
operation-owned receipt span on every path. Callers cannot supply any after
coordinate or terminal-authority field.

The following fieldwise derivation is exhaustive:

| Writer and replayed actor state | Runtime and six preobservation clocks | Actor outcome / cause | Authority |
|---|---|---|---|
| `SAME_TASK`, terminal actor state | exact observed runtime; all six clocks required | exact replayed non-null outcome; exact replayed nullable cause | `DURABLE_ACTOR_TERMINAL` |
| `SAME_TASK`, nonterminal actor state and runtime `FAULT_LATCHED` | exact `FAULT_LATCHED`; all six clocks required | both null | `VOLATILE_RUNTIME_FAULT_LATCHED` |
| `SAME_TASK`, nonterminal actor state and any other legal runtime state | exact observed state; all six clocks required | both null | `NONTERMINAL_RUNTIME` |
| `STARTUP_RECOVERY`, terminal actor state in the durable baseline/prefix | runtime and all six clocks null | exact replayed non-null outcome; exact replayed nullable cause | `DURABLE_ACTOR_TERMINAL` |
| `STARTUP_RECOVERY`, nonterminal actor state in the durable baseline/prefix | runtime and all six clocks null | both null | `UNAVAILABLE_AFTER_ORPHAN` |

`DURABLE_ACTOR_TERMINAL` is therefore equivalent to a non-null replayed actor
outcome; its cause is null only for `CLEAN_ALL_LAYERS`.
`VOLATILE_RUNTIME_FAULT_LATCHED` is legal only with same-process
`runtime_state_after=FAULT_LATCHED` and no durable actor outcome.
`NONTERMINAL_RUNTIME` is legal only in the same process with a non-fault-latched
runtime and no durable actor outcome. Recovery forbids both volatile authority
values. Restart never erases durable terminal evidence or invents volatile
state.

For a no-attempt path the six clocks are sampled after the admission outcome
or conclusively absent attempt-persistence exit is fixed. For an attempted
path they are sampled after the target exit is fixed. Both happen before
target-observation conversion. These clocks measure lifecycle latency; they
are not relabelled as the target-effect end.

## 10. Marker, extrema, and loop probe records

The 4-KiB `CapacityMeasurementMarkerV49FV8` contains:

```text
candidate_id
attempt_id | null
marker_ordinal
marker_kind
operation_kind
observer_before_offset_ns
observer_after_offset_ns
boottime_offset_ns
loop_time_offset_ns
thread_cpu_offset_ns
anchor_receipt_sequence
anchor_receipt_hash
actor_event_count
actor_tail_event_id | null
parser_cursor_id | null
raw_ingress_sequence | null
raw_ingress_commit_id | null
operation_counter_snapshot
target_checkpoint_id | null
target_checkpoint_unavailable_reason | null
marker_id
```

The authoritative same-process target interval is
`TARGET_EFFECT_ENTRY` through exactly one operation/path end marker:

| Path | End marker |
|---|---|
| Ingress returned | `INGRESS_RETURN_READY` |
| Subscription returned | `DISPATCH_RETURN_READY` |
| ACK returned false | `ACK_DEADLINE_NOT_DUE` |
| ACK returned true | `ACK_DEADLINE_TERMINAL_CONVERGED` |
| Shutdown returned | `SHUTDOWN_TERMINAL_CONVERGED` |
| Target raised, cancelled, or was interrupted | `TARGET_ESCAPE_OBSERVED`, after existing cleanup |

Target-effect duration is available only when both boundary markers survive
with exact compatible clock domains. OFF has no marker-derived duration.
Recovery has no surviving volatile interval. Attempt-precommit or
terminal-preobservation subtraction must never be relabelled as target-effect
duration. Process CPU uses its independently bracketed operation counter or is
unavailable.

`CapacityMeasurementMarkerExtremumV49FV8` is nested, not standalone, and is
limited to 1 KiB:

```text
counter_field_id
available_count
unavailable_count
minimum_value | null
minimum_first_ordinal | null
maximum_value | null
maximum_first_ordinal | null
last_available_value | null
last_available_ordinal | null
```

There are exactly 66 extrema in counter-schema order.

The 1-KiB `CapacityMeasurementLoopProbeV49FV8` contains:

```text
callback_ordinal
phase_index
expected_loop_offset_ns
actual_loop_offset_ns
exact_delay_ns
observer_callback_started_offset_ns
observer_callback_completed_offset_ns
probe_id
```

`CapacityMeasurementLoopProbeSummaryV49FV8` contains:

```text
status
unavailable_reason | null
interval_ns
capacity
start_loop_offset_ns | null
first_expected_loop_offset_ns | null
probes_scheduled | null
probes_fired | null
retained_count
overwritten_count | null
first_callback_ordinal | null
last_callback_ordinal | null
first_phase_index | null
last_phase_index | null
retained_probes
probe_phases_missed | null
fired_delay_total_ns | null
maximum_fired_delay_ns | null
maximum_fired_delay_first_callback_ordinal | null
last_fired_delay_ns | null
last_fired_delay_callback_ordinal | null
next_phase_index | null
next_expected_loop_offset_ns | null
pending_handle_cancelled | null
final_unfired_delay_lower_bound_ns | null
callback_observer_span_total_ns | null
callback_observer_span_maximum_ns | null
observer_failure_phase
observer_error_code | null
observer_error_class | null
```

`pending_handle_cancelled` is mandatory because the parent freeze requires
proof that the single scheduled handle was cancelled at closure.

## 11. Marker closure

`CapacityMeasurementMarkerClosureV49FV8` contains:

```text
candidate_id
attempt_id | null
terminal_id
operation_kind
marker_contract_id
target_field_registry_id
operation_counter_schema_id
instrumentation_mode
marker_capture_status
marker_unavailable_reason | null

emitted_total | null
retained_count
overwritten_count | null
first_emitted_ordinal | null
last_emitted_ordinal | null

marker_kind_counts | null
marker_kind_first_ordinals | null
marker_kind_last_ordinals | null
retained_markers
numeric_extrema | null

field_available_counts
field_not_applicable_counts
field_unavailable_counts
field_censored_counts
status_reason_counts

loop_probe_summary

target_observation_count
ordered_target_observation_ids
target_observation_root_sha256
target_observations

marker_observer_failure_phase
marker_observer_error_code | null
marker_observer_error_class | null
closure_clock_availability
observer_collection_sealed_observer_offset_ns | null
observer_collection_sealed_boottime_offset_ns | null
observer_collection_sealed_loop_offset_ns | null
closure_id
```

Aggregate representations are exact:

| Surface | Exact representation |
|---|---|
| marker-kind counts | fixed 19-key map in Step-2 marker UTF-8 order |
| marker-kind first/last ordinals | 19-position optional-uint tuples in the same order |
| numeric extrema | 66-position tuple in counter-schema order |
| each field availability count | 185-position tuple in target-registry order |
| status-reason counts | fixed 26-key map in current Step-2 V2 reason UTF-8 order |

Each fixed-key map contains every key exactly once, including zeros, and
rejects missing/extra keys. Each field-availability coordinate sums to
`target_observation_count`; the status-reason map counts every non-null nested
field reason.

Marker observer codes map to the closure reason exactly:

| Marker observer code | Closure reason |
|---|---|
| `CLOCK_READ_FAILED` | `SOURCE_CLOCK_UNAVAILABLE` |
| `SAFE_INTEGER_OR_BOUND_EXCEEDED` | `ARTIFACT_BOUND_EXCEEDED` |
| `CAPABILITY_MISMATCH`, `CLOCK_REGRESSION`, `COUNTER_ACCUMULATOR_FAILED`, or `MARKER_SLOT_CONVERSION_FAILED` | `OBSERVER_INTERNAL_ERROR` |

Closure truth:

| Mode/path | Capture status/reason | Marker/extrema evidence | Probe | Target observations | Seal clocks |
|---|---|---|---|---|---|
| OFF, same process | `UNAVAILABLE / INSTRUMENTATION_DISABLED` | exact zero emitted/retained/overwritten; 19-key zero map; null ordinal positions; empty retained tuple; exact 66 zero-count extrema | disabled | exactly 3 | `NOT_OBSERVED_INSTRUMENTATION_OFF` |
| OFF, recovery | same exact disabled status | same exact configured-zero evidence | disabled | exactly 1 `STARTUP_RECOVERY` | `NOT_OBSERVED_INSTRUMENTATION_OFF` |
| ON, complete | `COMPLETE / null` | complete ring, mandatory hooks, and extrema; no overwrite | complete | `3 + selected_checkpoint_count` | `EXACT_SAME_PROCESS` |
| ON, marker overwrite | `PARTIAL / MARKER_RING_OVERWROTE_PREFIX` | exact first-plus-tail/loss accounting and extrema | independently valid | exact | `EXACT_SAME_PROCESS` |
| ON, probe degradation only | `PARTIAL / exact probe reason` | otherwise complete | partial/unavailable same-process row | exact | exact unless its clock failed |
| ON, observer failure after at least one truthful marker | `PARTIAL / exact code-mapped reason` | exact prefix through the last successful marker; failed marker excluded | exact independently sealed state | structurally complete | exact, or unavailable only for a seal-clock failure |
| ON, observer failure before the first truthful marker | `UNAVAILABLE / exact code-mapped reason` | exact zero emitted/retained/overwritten; 19-key zero map; null ordinal positions; empty retained tuple; exact 66 zero-count extrema | exact independently sealed state | structurally complete | exact, or unavailable only for a seal-clock failure |
| ON, marker-slot conversion failure | `UNAVAILABLE / OBSERVER_INTERNAL_ERROR` | emitted/overwritten/kind structures/extrema null; retained zero/empty; ordinals null | exact independently sealed state | structurally complete | exact unless seal clocks also fail |
| ON, closure-seal clock failure | `PARTIAL / SOURCE_CLOCK_UNAVAILABLE` unless an earlier higher-precedence observer reason applies | otherwise exact sealed marker evidence | exact independently sealed state | structurally complete | `UNAVAILABLE_OBSERVER_FAILURE` |
| ON, recovery | `UNAVAILABLE / PROCESS_LOSS_VOLATILE_MARKER_STATE` | emitted/overwritten/kind structures/extrema null; retained zero/empty; ordinals null | unavailable recovery row | exactly 1 | `UNAVAILABLE_PROCESS_LOSS` |

OFF remains exact configured-zero evidence even after process restart because
the signed mode proves that no marker/probe capability was created. The
process-loss-null rule applies to ON volatile state only. Observer code/class
and phase are respectively null/null/`NONE` for OFF and process loss.

Marker failure is sticky. After the first failure the owner emits no later
marker or marker-derived checkpoint. A failed marker never increments
`emitted_total`, enters the ring, or contributes to counts/extrema. An
`AFTER_TRUTHFUL_MARKER_PREFIX` row obeys the ordinary ring equations exactly
through its last successful ordinal. Slot conversion is all-or-nothing into a
temporary tuple: any conversion failure publishes no partial slot tuple and
uses the exact unavailable row above.

`marker_observer_error_code` is null exactly when
`marker_observer_failure_phase=NONE`. Its class is a bounded qualified class
name exactly when a caught exception caused the failure; deterministic
validation failures have a null class. Exception messages and digests are not
stored here. A serialization/canonicalization failure after construction is
not observer degradation: the final transaction fails closed and writes
neither terminal nor closure.

Primary closure-reason precedence is marker/closure observer error, marker
overwrite, probe observer error, probe overwrite, then probe no-fire.
Secondary probe loss remains visible in the probe summary. A missing mandatory
hook without a matching failure is invalid.

Target observations are ordered `BEFORE_OPERATION`, selected checkpoints by
increasing marker ordinal, `AFTER_OPERATION`, `OPERATION_AGGREGATE`; recovery
contains only `STARTUP_RECOVERY`. No-attempt and OFF paths have no checkpoints.

Probe observer codes map to the probe reason exactly:

| Probe observer code | Probe reason |
|---|---|
| `CLOCK_READ_FAILED` | `SOURCE_CLOCK_UNAVAILABLE` |
| `SAFE_INTEGER_OR_BOUND_EXCEEDED` | `ARTIFACT_BOUND_EXCEEDED` |
| `CLOCK_REGRESSION`, `PROBE_ARITHMETIC_FAILED`, `PROBE_CALLBACK_FAILED`, `PROBE_SCHEDULE_FAILED`, or `PROBE_SLOT_CONVERSION_FAILED` | `OBSERVER_INTERNAL_ERROR` |

Probe truth:

| Path | Status/reason | Exact state |
|---|---|---|
| OFF, including recovery | `DISABLED / INSTRUMENTATION_DISABLED` | signed interval/capacity retained; scheduled/fired/retained/overwritten/missed and delay/callback totals zero; retained empty; timing/ordinals/next/max/last null; pending-cancelled false |
| ON, closes before first phase | `COMPLETE / null` | scheduled 1, fired/retained/overwritten/missed zero; next phase/expected present; one live successor synchronously cancelled and observed cancelled |
| ON, healthy callbacks | `COMPLETE / null` | scheduled = fired + 1; missed/overwritten zero; retained = fired <= capacity; exact totals/max/last; one successor cancelled |
| ON, ring overwrite | `PARTIAL / PROBE_RING_OVERWROTE_PREFIX` | retained = capacity; overwritten = fired - capacity; exact first-plus-tail; live successor cancelled |
| ON, due-unfired phase | `PARTIAL / PERIODIC_PROBE_DID_NOT_FIRE` | missed positive; closure-due case has exact censored lower bound excluded from fired extrema |
| ON, failure before first schedule | `UNAVAILABLE / exact code-mapped reason` | scheduled/fired/retained/overwritten/missed and totals exact zero; retained empty; timing that could not be observed null; no successor; pending-cancelled false |
| ON, failure after schedule but before first callback | `PARTIAL / exact code-mapped reason` | scheduled exactly one; fired/retained/overwritten/missed and totals zero; exact known schedule clocks retained; no invented successor; `pending_handle_cancelled=true` only if that live handle was synchronously cancelled and observed cancelled |
| ON, failure after truthful callback prefix | `PARTIAL / exact code-mapped reason` | exact state through last successful callback; failed callback excluded; no invented successor; `pending_handle_cancelled=true` only for a live handle synchronously cancelled and observed cancelled |
| ON, probe-slot conversion failure | `UNAVAILABLE / OBSERVER_INTERNAL_ERROR` | retained zero/empty; all volatile counts/times/extrema/next fields and pending-cancelled null |
| ON, recovery | `UNAVAILABLE / PROCESS_LOSS_VOLATILE_MARKER_STATE` | retained zero/empty; all volatile counts/times/extrema/next fields and pending-cancelled null; no synthetic observer error |

For ordinary ON firing,
`retained_count=min(probes_fired, capacity)` and
`overwritten_count=max(0, probes_fired-capacity)`, with the frozen
first-plus-tail equation. Zero fires gives zero delay/callback totals and null
max/last. `pending_handle_cancelled=true` proves the same-loop owner called
`cancel()` on the one live handle and immediately observed
`handle.cancelled()`; it says nothing about a pre-crash handle.

Probe failure is sticky. A failed callback is excluded from fired counts,
delay/extrema totals, and the ring, and it schedules no successor. Slot
conversion is all-or-nothing through a temporary tuple. `observer_error_code`
is null exactly when `observer_failure_phase=NONE`; its class is present
exactly for a caught exception and otherwise null. OFF and recovery use phase
`NONE` with null code/class; recovery does not manufacture a process-loss
observer exception.

The three observer-collection-sealed clocks are sampled after marker/probe
sealing and target-observation construction but before closure
canonicalization. `EXACT_SAME_PROCESS` requires all three; every other
availability value requires all three null. They do not claim closure
serialization, SQLite body, or COMMIT completion.

## 12. Prefix and cycle-free identity order

Receipt evidence retains the existing shape:

```text
ledger_id
global_sequence
receipt_hash
previous_receipt_hash
record_kind
identity_id
content_hash
committed_at
```

V8 does not copy those bodies into parallel typed fields plus base64 opaque
records. It uses one strict `CapacityMeasurementProjectionEntryV49FV8`:

```text
receipt
record
```

`record` is one strict canonical typed JSON object. Re-encoding it once must
equal the typed-table canonical blob; its SHA-256, semantic identity, and
record-kind codec must equal the paired receipt. No
`canonical_record_base64` copy exists. Candidate, optional attempt, target
records, terminal, closure, new RAW, actor, and other operation views are
derived from this one ordered entry tuple and are not serialized again.
Retained pre-candidate RAW dependencies use the same entry shape, ordered by
their original receipts, and are disjoint from the operation span.

The inner recovered identity uses the standard Step-2 semantic envelope with
domain
`RiskYieldMMA2MRecoveredOperationPrefixV4_9F_RawV8` and exact payload:

```text
pre_terminal_projection_entries
retained_raw_dependency_entries
```

The outer/final/export prefix uses domain
`RiskYieldMMA2MOperationPrefixV4_9F_RawV8`; no
`FinalOperationPrefix` alias exists. Its exact identity payload is:

```text
projection_entries
recovered_prefix_id
retained_raw_dependency_entries
finalization_observation
```

`recovered_prefix_id` hashes the pre-terminal entries and dependencies and
excludes terminal, closure, and post-commit finalization. `prefix_id` hashes
the complete closed outer structure. Neither ID occurs in its own preimage.
The serialized outer prefix adds only canonicalization version, lifecycle
schema version, record domain, and `prefix_id`; large bodies still occur once.

Every operation entry tuple is one ledger, contiguous, and hash-linked:

```text
no attempt: candidate -> terminal -> closure
attempted:  candidate -> attempt -> TARGET* -> terminal -> closure
```

The candidate is exactly its pre-candidate anchor plus one. The optional
attempt is candidate plus one and matches its pre-attempt anchor. Terminal and
closure are always the final consecutive pair. `entries[:-2]` is exactly the
`pre_terminal_projection_entries` tuple; the recovered-prefix preimage also
contains the retained dependency entries. Missing, extra, duplicated,
reordered, unknown-kind, wrong-ledger, wrong-content, wrong typed-row, or
noncontiguous entries reject.
Dependency entries are exactly the candidate baseline witness set: RAW-only,
pre-candidate, ordered, unique, same ledger/session/writer/clock, and disjoint
from the operation span.

The exact acyclic construction DAG is:

```text
spec -> declaration -> candidate -> candidate receipt
-> admission outcome -> optional attempt -> attempt receipt
-> collect bounded BEFORE/checkpoint/AFTER source slots and compact
   marker/probe/extrema slots at their causal runtime boundaries
-> seal all marker/probe/observation slots
-> canonicalize the captured BEFORE_OPERATION observation
-> for each selected checkpoint in marker-ordinal order:
     source-error detail -> context -> fields -> checkpoint observation
     -> canonical marker referencing that checkpoint observation
-> canonicalize every remaining marker, probe, and extremum
-> source-error detail -> context -> fields -> AFTER_OPERATION observation
-> derive OPERATION_AGGREGATE from the sealed marker/probe/extrema state
   -> aggregate source errors/context/fields/observation
-> ordered BEFORE/checkpoint/AFTER/AGGREGATE target-observation root
-> recovered_prefix_id
-> terminal -> terminal receipt -> closure -> closure receipt
-> post-commit finalization observation -> prefix_id
```

No root is constructed before the aggregate observation. Per checkpoint, the
target observation is canonicalized before the marker that references it.
Outcome binds candidate but candidate does not bind outcome;
checkpoint observation binds candidate/optional attempt/marker ordinal/kind,
never marker ID; closure binds terminal but terminal does not bind closure;
neither projection record binds the final outer ID.

`CapacityMeasurementObserverSpanV49FV8` is a strict nested pair:

```text
started_observer_offset_ns
completed_observer_offset_ns
```

Both members are safe unsigned integers in the candidate's exact
`observer_origin_ns` and `monotonic_clock_domain_id`, with
`started <= completed`.

`CapacityMeasurementFinalizationObservationV49FV8` is a strict nested semantic
envelope, bounded to 8 KiB and present only in the outer prefix/sample:

```text
candidate_id
terminal_id
closure_id
availability
closure_serialization_span | null
closure_validation_span | null
final_transaction_begin_span | null
final_transaction_body_span | null
final_transaction_commit_span | null
seal_to_commit_return_span | null
finalization_observation_id
```

Its ID uses domain
`RiskYieldMMA2MFinalizationObservationV4_9F_RawV8` and hashes every member
except itself under the standard semantic envelope. It is created only after
COMMIT returns or fresh-connection replay conclusively resolves the
transaction. `EXACT_SAME_PROCESS` requires every span. The independent
`seal_to_commit_return_span` begins immediately after the immutable closure
input is fixed and before serialization, regardless of OFF/ON mode; when an
exact closure-seal observer offset exists it must not precede that offset.
Its completion equals `final_transaction_commit_span.completed`. The other
spans are nonoverlapping and ordered exactly:

```text
seal/reference start
<= closure serialization
<= closure validation
<= transaction BEGIN
<= transaction body
<= transaction COMMIT return
```

`UNAVAILABLE_OBSERVER_FAILURE`,
`UNAVAILABLE_COMMIT_ACKNOWLEDGEMENT`, and
`UNAVAILABLE_PROCESS_LOSS` require all six spans null. Observer-clock failure
does not alter transaction control. The record is absent from terminal/closure
identity, the durable operation-batch result, and every projection receipt, so
it cannot create a write-completion cycle. The final lifecycle transaction is
excluded from closure-nested SQLite target counters and appears only here.

V8 idempotency uses domain
`RiskYieldMMPhysicalProjectionRequestV4_9F_RawV8`, the V8 projection schema,
the exact operation token, and exact canonical request payload. It never uses
the inherited V4 request domain. Exact operation tokens are:

```text
APPEND_CAPACITY_MEASUREMENT_OPERATION_CANDIDATE_V49F_V8
APPEND_CAPACITY_MEASUREMENT_OPERATION_ATTEMPT_V49F_V8
FINALIZE_CAPACITY_MEASUREMENT_OPERATION_V49F_V8
RECOVER_CAPACITY_MEASUREMENT_OPERATION_V49F_V8
```

Candidate/attempt requests contain their complete record. Finalize contains
all caller-owned terminal/closure inputs plus candidate/attempt identities and
the expected pre-terminal anchor.

Startup recovery first constructs one
`CapacityMeasurementStartupRecoverySnapshotV49FV8`:

```text
projection_ledger_id
projection_store_observation_id
snapshot_head_receipt_sequence
snapshot_head_receipt_hash
recovery_nonce                         # exact 32-byte random value as hex
ordered_open_locator_entries           # candidate ID, schedule coordinate,
                                       # kind, candidate receipt sequence/hash
open_locator_root_sha256
recovery_snapshot_id
```

Locator entries are ordered by candidate receipt. Their domain-separated root
and snapshot ID bind the complete tuple. A one-shot process/thread/store
capability binds the snapshot. Each recovery request contains the snapshot ID,
candidate ID, zero-based candidate position, and expected pre-terminal anchor;
the store derives the process-loss terminal/closure. A restarted unfinished
recovery creates a new snapshot/nonce, but an uncommitted request left no
operation batch and a committed final transaction removed the locator
atomically.

Keys are
globally unique operation-namespaced
`v49f-v8:<candidate|attempt|finalize|recover>:<candidate_id>`. Replay requires
identical operation, request hash, canonical result bytes, and receipt span.
Batch results freeze first/last receipt sequences/hashes and candidate,
optional attempt, terminal, closure, and recovered-prefix IDs as applicable.
They never contain `finalization_observation_id` or `prefix_id`; those are
post-COMMIT artifact outputs. Reassembly after acknowledgement loss or restart
uses an unavailable finalization variant and may therefore have a different
artifact-only prefix ID from an exact same-process observation that was never
durably published. It never rewrites the durable batch result.

## 13. SQLite tables and atomic operations

The V8 schema is the byte-identical accepted Raw V7 full schema, one LF
separator, and the exact V8 extension. This deliberately means that a V8
database contains the three inherited V7 lifecycle tables. Those tables,
their V7 record kinds, and their V7 operation-batch tokens are permanently
forbidden from containing rows in the V8 profile. Conversely, a V7 database
does not contain any V8 table. Metadata and certified fingerprint checks reject
profile substitution in both directions; table presence itself is therefore
asymmetric and must not be described as symmetric absence.

The V8 extension adds exactly:

```text
capacity_measurement_operation_candidates_v49f_v8
capacity_measurement_operation_attempts_v49f_v8
capacity_measurement_operation_terminals_v49f_v8
capacity_measurement_marker_closures_v49f_v8
capacity_measurement_open_candidates_v49f_v8
```

The current exact empty-profile candidate is pinned for implementation audit
by these byte counts and SHA-256 values:

| SQL text | UTF-8 bytes | SHA-256 |
|---|---:|---|
| accepted Raw V7 `_FULL_SCHEMA_SQL` | 136,483 | `d4b311050f20f03159cd7d121421535e36f45a1d56d42022345ab9fdfcf088e5` |
| Raw V8 `_RAW_V8_SCHEMA_EXTENSION_SQL_V49F` | 8,356 | `a2bd6ea860ad100f83c148f51ce045e6f3dc9bc899faf0cba42b02f0134e4e3f` |
| exact concatenated Raw V8 full SQL | 144,839 | `92f3b635aa9909c1bd859b6a9a7ca798ec0aae47c042c70cd619c49858c0fc03` |

The independently replayed candidate schema fingerprint is
`13e6fbb2e8c29153fb2f4856bcc544c5463fca0f0ac07fd9a9b07fbb7f648d81`.
These values are not a Step-3 acceptance claim and must change if later
protocol correction changes the schema.

The extension has exactly two indexes:

```text
capacity_measurement_first_candidate_session_v49f_v8
capacity_measurement_candidates_campaign_v49f_v8
```

It has exactly nine triggers:

```text
capacity_measurement_operation_candidates_v49f_v8_no_update
capacity_measurement_operation_candidates_v49f_v8_no_delete
capacity_measurement_operation_attempts_v49f_v8_no_update
capacity_measurement_operation_attempts_v49f_v8_no_delete
capacity_measurement_operation_terminals_v49f_v8_no_update
capacity_measurement_operation_terminals_v49f_v8_no_delete
capacity_measurement_marker_closures_v49f_v8_no_update
capacity_measurement_marker_closures_v49f_v8_no_delete
capacity_measurement_open_candidates_v49f_v8_no_update
```

Required constraints:

- candidate ID is a primary key and foreign key to `canonical_records`;
  declaration ID and source receipt are unique; campaign/sample/operation is
  unique; operation kind is exactly one of the four V8 kinds; session is a
  foreign key to the admitted transport-session table;
- a non-null previous-terminal ID is unique and references a V8 terminal; a
  partial unique index permits only one first candidate per session;
- attempt ID is a canonical-record primary/foreign key; candidate and source
  receipt are independently unique foreign keys;
- terminal ID is a canonical-record primary/foreign key; candidate and source
  receipt are independently unique; its nullable attempt is unique and a
  foreign key;
- closure ID is a canonical-record primary/foreign key; candidate, terminal,
  and source receipt are independently unique; its nullable attempt is unique
  and a foreign key;
- the locator candidate is a primary/foreign key; session, schedule coordinate,
  and candidate receipt are unique; its operation kind uses the same exact
  four-value check;
- no `UPDATE` on any lifecycle or locator row;
- immutable lifecycle rows forbid `DELETE`;
- locator deletion is private to finalization and never referenced by a
  durable attempt foreign key; and
- canonical and typed identity sets remain exactly bijective.

SQLite constraints establish local shape and uniqueness. Replay additionally
proves that every typed row's ID, kind, content hash, receipt identity/sequence,
candidate/session/schedule coordinate, optional attempt, and previous terminal
equal the canonical body. Cross-row semantic equality is never inferred from
foreign-key existence alone.

Candidate transaction:

```text
BEGIN IMMEDIATE
append canonical candidate and receipt
insert typed candidate
insert exact open-candidate locator
finish one operation batch
COMMIT
```

Attempt transaction:

```text
BEGIN IMMEDIATE
validate exact locator and current candidate receipt
validate exact GRANTED outcome and duplicated coordinates
append canonical attempt and receipt
insert typed attempt
finish one operation batch
COMMIT
```

Final transaction:

```text
BEGIN IMMEDIATE
validate exact locator and complete prefix
construct and validate terminal and closure
append canonical terminal and receipt
insert typed terminal
append canonical closure and consecutive receipt
insert typed closure
delete exactly one locator
finish one two-receipt operation batch
COMMIT
```

Calling two ordinary append methods is forbidden because it exposes a terminal
without its closure.

Idempotent replay compares complete canonical request/record bytes and the
exact receipt span, not identity strings alone. A same key with different
bytes rejects.

Initialization is a distinct atomic operation:

```text
acquire exclusive path provisioning lease
recheck path and inode identity
open/configure connection
if initialized: validate metadata + full replay and return
if uninitialized:
    BEGIN IMMEDIATE inside the schema script
    execute exact certified schema
    insert parameterized exact metadata in the same transaction
    COMMIT
    resolve acknowledgement uncertainty by replay
release only after validation or non-destructive retained-state failure handling
```

The initializer slice is implemented and received an independent technical GO
on 2026-07-26: its focused V7/V8 suite passed 32 tests before the permanent
symlink-alias regression was added; lint, bytecode compilation, real
pre/post-COMMIT process-death probes, poisoned-connection replay, contention,
path replacement, hard-link alias, symlink alias, and lock replacement were
covered. V8 failure handling is non-destructive and retains uncertain files
for the next lease-held classifier. This sub-slice does not accept Step 3:
full V7/adjacent reacceptance, exact lifecycle/receipt grammar, generated
bounds, and the remaining acceptance matrix are still required.

## 14. Startup recovery

Before any ordinary V8 mutation, the store snapshots open candidates in
candidate-receipt order and issues one process/thread/store-bound recovery
capability.

Candidate without attempt:

- do not infer rejection or a lost grant;
- retain the candidate's exact before snapshot;
- construct admission outcome `UNRESOLVED_PROCESS_LOSS` with
  `gate_counter_snapshot_after_availability=UNAVAILABLE_PROCESS_LOSS` and null
  after snapshot;
- use authorization `UNRESOLVED_PROCESS_LOSS`;
- write no result fields; and
- atomically write a process-loss terminal and the mode-exact closure: exact
  disabled-zero evidence for signed `OFF`, or unavailable volatile state for
  `ON`.

Candidate with attempt:

- replay its durable target prefix;
- reuse the exact admission outcome already committed inside the attempt;
- use authorization `ATTEMPT_COMMITTED`;
- use result-unavailable reason `PROCESS_LOSS_BEFORE_RESULT`;
- atomically write a recovery terminal and the same mode-exact recovery
  closure rule; and
- never call A1 or retry the target.

A crash after final commit leaves terminal plus closure durable and replay is
idempotent. A crash before commit leaves neither final record and preserves the
locator. Attempted recovery with a corrupt, noncontiguous, unknown-kind, or
operation-illegal prefix writes nothing and leaves the locator open for
operator-visible failure. Recovery is complete only when every snapshot
candidate was consumed in order and no open locator remains.

## 15. Independent bound generator

The Step-3 generator must not import production modules. It consumes literal
protocol/Step-2 inventory inputs and builds actual canonical records. For each
operation, instrumentation mode, and recovery class it exercises:

1. the exact maximum Step-2 target observation bodies legal for that operation;
2. the selected legal checkpoint count;
3. maximum compact markers with all 66 coordinates;
4. the exact first-plus-tail retained sequence;
5. all 66 maximum extrema;
6. maximum retained probe records and summary;
7. the exact 19- and 26-key maps plus the 19-position ordinal, 66-position
   extrema, and four 185-position availability tuples;
8. complete framing, roots, identities, terminal, closure, prefix, and sample;
   and
9. strict structural scanning before materialization.

It proves:

```text
declaration             <= 3 MiB
operation spec          <= 2 MiB
admission outcome       <= 512 KiB
candidate               <= 4 MiB
attempt                 <= 1 MiB
terminal                <= 1 MiB
closure                 <= 24 MiB
target projection entries <= 48 MiB aggregate
retained dependencies    <= 8 MiB aggregate
outer prefix shell       <= 10 MiB
closed prefix            <= 96 MiB
one sample               <= 128 MiB
sample-only framing      <= 32 MiB
```

The closed-prefix ceiling is an explicit additive budget, not an assumption
that independent maxima can silently overlap:

```text
candidate 4 + attempt 1 + target entries 48 + terminal 1
+ closure 24 + retained dependencies 8 + outer shell 10 = 96 MiB
```

The outer shell includes the at-most-8-KiB finalization observation, receipt
envelopes, roots, identities, and canonical framing not charged to a typed
body. The 128-MiB sample is exactly the 96-MiB closed prefix plus at most
32 MiB of sample-only framing. A no-attempt branch simply omits the 1-MiB
attempt budget; it does not reallocate it.

The 67 maximum Step-2 observations consume exactly
`67 * 259090 = 17,359,030` bytes, or about 16.554861 MiB. A 24-MiB closure then
has 7,806,794 bytes left before its own framing, markers, extrema, probes,
roots, and aggregate structures. Typed records are serialized once: a
parallel base64 copy is forbidden. The individual maxima do not all coexist.
The generator must derive and freeze the admissible
`(checkpoint_count, marker_capacity, probe_capacity)` region for every signed
plan and reject an oversized plan before candidate persistence.

Every ceiling is tested with actual canonical materialization at the exact
maximum and with an independently constructed one-byte/one-element-over
rejection. No V8 schema/profile fingerprint is frozen until this generator and
the exact schema literal both pass independent reproduction.

## 16. Step-3 acceptance matrix

| Area | Required evidence |
|---|---|
| V7 preservation | Exact frozen V7 SQL bytes/hashes/fingerprint, record/request/receipt identities, reopen, schema checks, codecs, and accepted regressions remain unchanged |
| V7/V8 separation | Metadata/fingerprint/schema substitution rejects both ways; V8's inherited V7 lifecycle tables remain exactly empty; V7 has no V8 tables; no in-place migration exists |
| Schema initialization | Shared path lease, concurrent creators, busy handling, non-destructive retained-state failure handling, alias/path/inode checks, and faults/crashes before/inside/after schema/metadata/COMMIT yield `UNINITIALIZED` committed state or one complete self-consistent V8 database |
| Candidate atomicity | Fault before/after canonical insert, receipt, typed insert, locator insert, batch finish, and commit yields candidate plus locator or neither |
| Attempt atomicity | Every analogous fault yields zero or one exact attempt; no target authorization exists without a resolved committed receipt |
| Final atomicity | Fault before/after terminal, closure, locator deletion, batch finish, and commit yields both terminal and closure or neither |
| Receipt replay | Candidate/attempt adjacency, branch-exhaustive operation-specific target-prefix grammar, terminal/closure adjacency, content hashes, roots, and typed bijection replay independently |
| Truth tables | Every admission/attempt/authorization/result/recovery combination accepts or rejects exactly as frozen |
| Substitution | Candidate, outcome, attempt, operation, spec, session, socket, policy, writer fence, baseline, precondition, result, terminal, closure, and locator substitutions reject |
| Constraints | Duplicate candidate/attempt/terminal/closure, wrong prior terminal, schedule gap, wrong session, missing/forged locator, and post-terminal append reject |
| Idempotency | Same key and exact request replays; same key with different bytes rejects; commit-acknowledgement loss resolves by replay |
| Recovery | Candidate-only and attempted orphans close in deterministic order; A1 and target call counters remain zero |
| Recovery censoring | Candidate-only A1 after-state is unavailable; ON volatile marker/probe/time facts are null/unavailable; signed OFF configured-zero evidence and durable/static facts remain independently checkable |
| Bounds | Independent generator proves exact-max materialization, one-over rejection, nonduplication, every record/prefix/sample ceiling, and plan-region rejection before candidate persistence |
| Corruption | Direct table/receipt/canonical/locator mutation fails reopen/full verification |
| Public surface | No V8 type or V8 store is exported through `riskyieldmm.trading`; public live factory remains closed |
| Adjacent regression | Raw V7 direct/adjacent groups and relevant projection, actor, parser, terminal, clock, and public-denial tests pass |
| Leftovers | No placeholder, schema alias, test-only production branch, temporary database, generated cache, or unreviewed symbol remains |

## 17. Implementation sequence

1. Freeze the exact Raw V7 projection goldens.
2. Extract private pinned schema-profile hooks with V7 only and prove no
   identity or behavior drift.
3. Reconcile this corrected child protocol with the parent; regenerate and
   reaccept Step 2 because its inventory pins the parent protocol hash.
4. Add the shared path provisioning lease and non-destructive V8 failure hook;
   rerun the full accepted V7 inventory. The implementation and focused
   preservation checks are complete; full V7 inventory reacceptance remains.
5. Add the fresh V8 profile/store and prove schema creation, reopen, mutual
   rejection, committed-state classification, and atomic schema/metadata
   initialization before lifecycle writes. The initializer implementation has
   independent technical GO; formal Step-3 acceptance remains gated by item 4
   and the later lifecycle/bound rows.
6. Implement pure V8 lifecycle, marker, probe, closure, and prefix records plus
   the independent bound generator.
7. Add candidate plus locator persistence and its complete fault matrix.
8. Add candidate-to-attempt persistence, GRANTED truth, zero-span replay,
   one-shot process-local effect capability, and faults.
9. Add the one-transaction terminal-plus-closure finalizer and faults.
10. Add full replay, typed bijection, idempotency, corruption, exact
    operation-prefix grammar, and bounds.
11. Add startup recovery for candidate-only and attempted prefixes without A1
   or target retry.
12. Run final V7/V8/adjacent/static/leftover checks and reconcile status only
    from one stable tree.

Step 3 defines synthetic exact marker/probe/closure records for persistence
tests. It does not implement preallocated rings, live marker/probe
capabilities, the private A1 observer, source hooks, runtime counter adapters,
or target-field collection. Those remain Sections 18 Steps 4 through 8.

## 18. Primary-source support and limits

- [SQLite transaction semantics](https://www.sqlite.org/lang_transaction.html)
  establish `BEGIN IMMEDIATE`, one-writer behavior, `COMMIT`-busy state, and
  error-dependent rollback uncertainty. They do not define RiskYieldMM
  lifecycle classifications.
- [SQLite atomic commit](https://www.sqlite.org/atomiccommit.html) explains why
  changes in one rollback-journal transaction appear all-or-none under its
  stated VFS/filesystem assumptions. It is not external anti-equivocation or
  proof against broken storage.
- [SQLite file locking and hot-journal recovery](https://www.sqlite.org/lockingv3.html)
  requires a reader to resolve a hot journal before trusting database state.
  This is why V8 reopens/replays an uncertain outcome and never blindly deletes
  a possibly hot journal. It does not provide the separate pre-open
  cross-profile provisioning decision.
- [SQLite foreign keys](https://www.sqlite.org/foreignkeys.html) supports
  relational constraints and explains immediate/deferred enforcement. It does
  not replace semantic receipt replay.
- [SQLite STRICT tables](https://www.sqlite.org/stricttables.html) narrows
  storage classes but does not validate hashes, enum truth tables, or canonical
  JSON.
- [Python 3.12 `sqlite3`](https://docs.python.org/3.12/library/sqlite3.html)
  documents `isolation_level=None`, `in_transaction`, explicit transaction
  control, and `executescript()`'s implicit-commit behavior.
- [Python 3.12 `fcntl`](https://docs.python.org/3.12/library/fcntl.html)
  provides Unix `flock()` and nonblocking exclusive-lock primitives used by
  the local provisioning lease. The lease remains advisory: every supported
  creator must participate, and its correctness still depends on the host
  filesystem's locking semantics.

These sources justify the storage mechanisms and the initialization correction.
They do not demonstrate observer neutrality, sufficient marker capacity,
acceptable overhead, live safety, or economic edge.
