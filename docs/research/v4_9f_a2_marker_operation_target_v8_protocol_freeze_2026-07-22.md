# V4.9F-A2 Stable Marker, Operation Union, and Target Coverage Raw V8 Protocol Freeze

**Design-freeze date:** 2026-07-22

**Status:** The original design freeze is under a breaking Step-3 correction.
Section 18 Step 2 was locally accepted on 2026-07-25 for its then-frozen
surface, but that acceptance is now historical until its V2 operation shapes,
checkpoint cardinality, lifecycle truth, parent hash, and generated inventory
are reconciled and reaccepted. Raw V8 as a whole remains incomplete and
unaccepted. Its Raw V7 predecessor passed its recorded acceptance matrix on
2026-07-22 and must be rerun on the final corrected tree. Nothing in this
document accepts A2-M, a numeric threshold, A2-E, the public live factory,
Stage 1, production trading, or profitability.

**Normative active correction:**
[`v4_9f_a2_raw_v8_step3_target_and_lifecycle_correction_2026-07-26.md`](v4_9f_a2_raw_v8_step3_target_and_lifecycle_correction_2026-07-26.md)

**Current Step-2 V2 machine-contract input:**
[`v4_9f_a2_raw_v8_step2_v2_contract_freeze_2026-07-26.md`](v4_9f_a2_raw_v8_step2_v2_contract_freeze_2026-07-26.md)

Where this historical parent conflicts with that correction, the correction
and the current Step-2 V2 freeze govern together. A conflict between those two
current documents is global NO-GO. This historical parent must be rewritten
and independently reaccepted before any conflicting section can regain frozen
status.

**Historical Step-2 V1 acceptance evidence:**
[`v4_9f_a2_raw_v8_step2_acceptance_audit_2026-07-25.md`](v4_9f_a2_raw_v8_step2_acceptance_audit_2026-07-25.md)

**Roadmap position:** Stage 1 critical corrections, inside V4.9F-A2-M Step 3,
after the historical Step-2 checkpoint and before the
physical-event normalizer and fixture-level neutrality oracles, independent
correctness finalization, campaign isolation, atomic external publication,
full matched OFF/OFF--ON/ON--OFF/ON campaigns and frozen workload execution,
calibration, confirmation, threshold selection, or enforcement.

**Parent protocol:**
[`v4_9f_a2_measurement_and_enforcement_protocol_freeze_2026-07-20.md`](v4_9f_a2_measurement_and_enforcement_protocol_freeze_2026-07-20.md)

**Required predecessor:**
[`v4_9f_a2_failed_prefix_cancellation_v7_protocol_freeze_2026-07-21.md`](v4_9f_a2_failed_prefix_cancellation_v7_protocol_freeze_2026-07-21.md)

## 1. Decision

Raw V8 is a new evidence domain. It does not add nullable fields to Raw V7,
change the meaning of a Raw V7 attempt or terminal, or expand Raw V7's
ingress-only operation enum in place.

The new schema is:

```text
riskyieldmm_physical_transport_a2m_raw_v49f_v8
```

It freezes five profiles:

```text
operation_lifecycle_profile = PRE_ADMISSION_CANDIDATE_ATTEMPT_TERMINAL_CLOSURE_V2
operation_union_profile     = EXACT_A1_FOUR_COMMAND_TAGGED_UNION_V1
stable_marker_profile       = FIRST_PLUS_OVERWRITE_TAIL_EXACT_LOSS_V1
target_registry_profile     = COMPLETE_TYPED_FIELD_AVAILABILITY_V1
loop_probe_profile          = PHASE_LOCKED_BOUNDED_NO_CATCHUP_V1
```

The selected architecture is:

```text
fresh observed local authority + V8 signature
  -> exact predeclared four-command workload
  -> V8 candidate committed before A1 admission
  -> exact A1 outcome; V8 attempt committed after grant and before target effect
  -> synchronous no-await markers at stable causal boundaries
  -> bounded periodic event-loop probe
  -> exact target-field observations or typed unavailability
  -> V8 terminal + marker closure in one SQLite transaction
  -> prefix/marker/field replay in a distinct four-member Raw V8 artifact
```

The marker path is intentionally not an enforcement path. No measured value,
ring state, dropped-marker count, observer failure, or provisional high-water
value may alter a read, parse, send, journal, deadline, retry, shutdown, or
admission decision. Measurement failure invalidates or censors measurement
evidence; it does not manufacture a different transport outcome.

## 2. Confirmed implementation facts that force a new version

These are freeze-time facts from the source tree inspected on 2026-07-22. Raw
V7 was subsequently accepted on the post-format tree; V8 implementation must
still regenerate this audit before relying on any fact below.

| Current surface | Confirmed fact | V8 consequence |
|---|---|---|
| Raw V7 lifecycle | `CapacityMeasurementLifecycleOperationV49F` has exactly one member, `INGRESS`; the declaration explicitly rejects every other operation | Expanding that enum would reinterpret signed Raw V7 bytes. V8 needs a new tagged operation union and new domains |
| A1 admission | The exact command set is `INGRESS`, `SUBSCRIPTION_DISPATCH`, `ACK_DEADLINE_EXPIRY`, and `LOCAL_SHUTDOWN`; all use the same FIFO gate and orchestration mutex | Measurement must cover the exact four operations without creating a fifth operational path or bypassing A1 |
| Raw V7 admission cutoff | The durable Raw V7 attempt contains an already-started A1 grant, so rejection, timeout, and cancellation before entry cannot be represented by that attempt | V8 needs a durable pre-admission candidate followed by an optional post-grant attempt, not an inferred rejection from counter deltas |
| Existing layer snapshot | Raw V6/V7 reuse a flat, partial layer snapshot. It covers socket buffer/queue counts, BIO counts, selected runtime queues, five A1 counters, three actor counters, file sizes, RSS/PSS/cgroup memory, and one loop-lag value | The missing target surface needs a strict registry; null extension of the old type is insufficient and ambiguous |
| Existing in-operation state | The current ingress runner constructs an all-null snapshot with `NO_STABLE_IN_OPERATION_HOOK` | V8 must add explicit source-owned stable hooks; a fieldwise maximum synthesized from before/after observations remains forbidden |
| Existing loop probe | `_ScheduledLoopLagProbeV49F` schedules one `call_soon()` callback and records one delay | One callback is not a series, a maximum, or proof of loop behavior during synchronous SQLite/CPU stalls |
| Actor cost | Candidate append validates the retained chain, writes synchronously through the projection journal, appends to the Python list, and rebuilds state | V8 must time validation, journal append, and rebuild separately where the code boundary permits; it must not claim that a parser count bounds these costs |
| Projection cost | Projection writes use synchronous `BEGIN IMMEDIATE`; the actor journal has no suspension point around the call | Transaction spans must be measured inside the existing call path. An asyncio timeout cannot preempt the synchronous SQLite work |
| Socket observation | Current Linux flow observation has `SO_RCVBUF`, `SO_SNDBUF`, `SIOCINQ`, and `SIOCOUTQ`, but not readiness masks and per-field errno evidence in the raw target schema | V8 must preserve literal Linux values and add exact readiness/error availability, without inferring headroom or peer receipt |
| Operation APIs | Subscription dispatch accepts only an idempotency key; ACK expiry accepts no injected clock and may return `False`; local shutdown accepts a bounded timeout and returns a termination | Each operation needs a different spec/result type. A generic bytes-in/bytes-out record would be false |
| Actor event set | The durable actor chain already distinguishes RAW, parser, application, outbound preparation, TLS preparation, kernel attempt/result/failure, dispatch completion, ACK expiry, shutdown/TLS/TCP markers, and terminal transition | Stable markers must reference these existing durable boundaries; marker records must not enter or reorder the actor chain |
| Raw V7 crash model | A pre-effect attempt and exactly one terminal make process-loss recovery possible; volatile in-operation state cannot be reconstructed after a hard crash | V8 must record process-loss marker state as censored/unavailable, never as an empty ring or zero peak |

The implementation must regenerate this audit against the final Raw V7 tree.
Any changed operation, event, projection, source-inventory, or lifecycle fact
requires a new review before V8 code is accepted.

## 3. Designs considered

| Candidate | Decision | Reason |
|---|---|---|
| Add marker fields and three operation enum values to Raw V7 | Rejected | It changes the interpretation of an already versioned signed schema and invalidates historical V7 mutual-rejection guarantees |
| Reuse the ingress workload shape for every command | Rejected | Subscription dispatch, deadline expiry, and shutdown have different authority, inputs, returns, terminal effects, and no RAW batch |
| Periodically inspect the runtime from an independent thread | Rejected | It races the single-thread/event-loop owner, cannot obtain a coherent causal cutoff, and would introduce cross-thread socket/SQLite access |
| Schedule only an asyncio timer callback | Rejected as the stable-marker mechanism | A callback cannot run while the loop is blocked; it can quantify lateness after the stall but cannot identify the durable state crossed inside it |
| Perform a full procfs/socket/SQLite observation at every parser or send unit | Rejected as the default | The syscalls, file reads, parsing, and connection re-entry would dominate small operations and materially alter the quantity being measured |
| Write every marker immediately to SQLite | Rejected | It adds one transaction per stable unit, directly changes actor/projection contention, and can turn measurement rate into unbounded durable history |
| Keep an unbounded Python event list | Rejected | A2-M is specifically required to expose bounded observer cost and exact evidence loss |
| Stop or fail the target operation when the ring is full | Rejected | That is enforcement and changes transport behavior before any threshold is accepted |
| Drop new markers when full | Rejected | It preferentially loses terminal-adjacent evidence, which is the most useful evidence for failure and cancellation diagnosis |
| Overwrite the oldest marker silently | Rejected | A bounded buffer without exact loss accounting can be mistaken for complete evidence |
| Preserve the first marker, overwrite the oldest tail marker, and retain exact emitted/retained/dropped counts plus extrema | **Selected** | It bounds memory and O(1) append work, preserves entrance and terminal-adjacent state, and makes every loss explicit |
| Memory-map or fsync a crash-surviving marker ring | Deferred | It would add a second durability protocol and I/O path inside the operation; Raw V8 truthfully censors volatile marker state after process loss |
| Generic nullable JSON dictionary for target fields | Rejected | Missing keys, null, zero, wrong units, and unsupported observations would remain ambiguous |
| Exact ordered field registry with typed availability/censoring | **Selected** | It makes omissions, wrong units, wrong methods, and fabricated zero values mechanically rejectable |
| Start the V8 lifecycle only after A1 grants entry | Rejected | It would still lose rejected, timed-out, closed, and cancelled-before-entry candidates and could not supply the requested exact rejection/wait evidence |
| Commit a candidate before A1, then an attempt only after grant | **Selected** | It preserves exact pre-effect ordering while representing every A1 outcome without fabricating a grant |
| Embed and reinterpret a whole Raw V7 campaign as the V8 operation plan | Rejected | V7 is ingress-only and its schedule is not the V8 four-operation schedule |
| Fresh current observed-authority predecessor plus a distinct V8 outer authority that pins the accepted V7 contract | **Selected** | It reuses the hardened local authority graph without pretending a V7 ingress schedule authorizes V8 operations |

The Linux perf ring-buffer documentation distinguishes overwrite and
non-overwrite modes and explicitly accounts lost records in the latter. The
OpenTelemetry tracing SDK likewise requires exporters to be able to report
counts dropped by collection limits. Those sources support explicit bounded
loss accounting, not this project's exact first-plus-tail policy; the latter
remains a RiskYieldMM design that must be tested
([Linux perf ring buffer](https://www.kernel.org/doc/html/latest/userspace-api/perf_ring_buffer.html),
[OpenTelemetry tracing SDK](https://opentelemetry.io/docs/specs/otel/trace/sdk/)).

## 4. Version, authority, and artifact separation

### 4.1 Domain separation

At minimum V8 defines distinct exact domains for:

```text
RiskYieldMMA2MManifestV4_9F_RawV8
RiskYieldMMA2MManifestAuthoritySubjectV4_9F_RawV8
RiskYieldMMA2MManifestAuthorityAttestationV4_9F_RawV8
RiskYieldMMA2MOperationDeclarationV4_9F_RawV8
RiskYieldMMA2MOperationSpecV4_9F_RawV8
RiskYieldMMA2MOperationResultEvidenceV4_9F_RawV8
RiskYieldMMA2MDispatchWindowEvidenceV4_9F_RawV8
RiskYieldMMA2MDueDecisionClockEvidenceV4_9F_RawV8
RiskYieldMMA2MOperationCandidateV4_9F_RawV8
RiskYieldMMA2MOperationAttemptV4_9F_RawV8
RiskYieldMMA2MOperationTerminalV4_9F_RawV8
RiskYieldMMA2MMarkerV4_9F_RawV8
RiskYieldMMA2MMarkerClosureV4_9F_RawV8
RiskYieldMMA2MTargetFieldRegistryV4_9F_RawV8
RiskYieldMMA2MTargetFieldObservationV4_9F_RawV8
RiskYieldMMA2MSourceErrorDetailV4_9F_RawV8
RiskYieldMMA2MTargetObservationContextV4_9F_RawV8
RiskYieldMMA2MTargetObservationV4_9F_RawV8
RiskYieldMMA2MTargetObservationRootV4_9F_RawV8
RiskYieldMMA2MOperationCounterSnapshotSchemaV4_9F_RawV8
RiskYieldMMA2MOperationPrefixV4_9F_RawV8
RiskYieldMMA2MSampleV4_9F_RawV8
RiskYieldMMA2MCorrectnessV4_9F_RawV8
RiskYieldMMA2MIntegrityV4_9F_RawV8
```

V6, V7, and V8 top-level codecs mutually reject. V8 may embed an explicitly
typed fresh observed-authority predecessor, decoded by its unchanged codec,
but it may not hydrate an earlier sample, terminal, or marker. The outer V8
signature is a new one-shot runtime authorization bound to the exact process,
thread, event loop, asyncio task, fork generation, session, projection writer
fence, source closure, workload plan, marker contract, and target registry.

The V8 static deployment expectation must independently pin the accepted Raw
V7 lifecycle schema/protocol identity and the exact implementation/source
closure admitted for V8. An embedded self-signing key remains
self-authentication only. V8 cannot declare Raw V7 accepted merely by naming
it.

### 4.2 Manifest composition

```text
CapacityMeasurementManifestV49FV8
  observed_authority_predecessor
  raw_v7_predecessor_contract_reference
  source_inventory_v8
  operation_union_contract_v8
  lifecycle_contract_v8
  marker_contract_v8
  target_field_registry_v8
  workload_plan_v8
  projection_authority_v8
  actor_parser_runtime_baseline_v8
  manifest_authority_v8
  campaign_manifest_id
```

The signed subject binds every nested record identity, the exact four command
kinds, exact operation specs and order, exact marker capacities/cadence/full-
checkpoint selector, target-field registry ID, source observation, projection
schema/fingerprint/validation version, actor/parser baseline, three clock
origins/resolutions, GC-observer profile, and `promotion_eligible=false`.

The source inventory count is deliberately not guessed in this pre-
implementation freeze. At implementation review it becomes one exact sorted
module set with exactly one CRITICAL and one LOADED role per admitted module.
Adding the V8 marker/registry implementation necessarily changes the observed
source closure and requires a fresh authority signature.

## 5. V8 durable lifecycle and projection contract

### 5.1 Record sequence

For every scheduled candidate the authoritative receipt sequence is one of:

```text
... prior projection receipt
V8 OPERATION_CANDIDATE

# no attempt: A1 non-grant, or conclusive attempt-persistence failure
V8 OPERATION_TERMINAL
V8 MARKER_CLOSURE

# or exact A1 grant
V8 OPERATION_ATTEMPT
... zero or more existing RAW / actor / projection records from target work
V8 OPERATION_TERMINAL
V8 MARKER_CLOSURE
```

The candidate is committed before the A1 gate is called. It contains no grant
and authorizes no target effect. An admitted path commits the attempt, with the
exact active grant, after A1 entry and before the first socket/TLS/parser/
actor/projection target mutation. A rejected, timed-out, closed, or cancelled-
before-entry path has no attempt and closes the candidate directly. A grant
still authorizes no target effect until the attempt receipt commits.

The candidate and its open-candidate locator are first inserted in one store-
owned transaction; neither may be visible alone. An attempt insert requires
that exact open locator, candidate ID, grant evidence, and schedule coordinate,
and a unique constraint prevents a second attempt.

The terminal and marker closure are inserted in one store-owned
`BEGIN IMMEDIATE` transaction. Their receipt sequences are consecutive. The
open-candidate locator is removed only after both inserts succeed. A reader can
therefore observe either neither final record or both after transaction commit;
it cannot observe a completed V8 candidate with no marker-availability
statement.

Exactly one candidate, at most one attempt, at most one terminal, and at most
one marker closure are allowed for a schedule coordinate. Every raw sample,
including a failed one, requires one candidate, one terminal, and one closure.
An attempt is required exactly when the V8 target-authorization boundary was
reached. It implies `GRANTED`; `GRANTED` without an attempt is allowed only for
a conclusively resolved attempt-persistence failure before target invocation.
The marker closure binds the terminal ID; the terminal does not include the
closure ID, avoiding a hash cycle. The artifact sample binds all present IDs
and receipts.

Marker writes are volatile and do not enter the projection receipt chain
during admission or target effect. Existing RAW, actor, terminal, and
projection records remain the only causal transport authority.

### 5.2 Candidate and A1 outcome schema

`CapacityMeasurementOperationCandidateV49FV8` contains:

```text
campaign / manifest-authority / design / workload / trial coordinates
previous V8 operation-terminal ID
operation_spec_id and exact operation kind
transport session / driver nonce / socket / A1 policy authority
projection ledger / schema / validation / fingerprint / store observation
writer-fence token digest and generation
pre-candidate receipt sequence and hash
actor/parser/RAW/runtime pre-admission baseline
marker contract and target-field registry IDs
observer / BOOTTIME / loop / process-CPU / thread-CPU start evidence
candidate wall time for forensic correlation only
candidate_id
```

The A1 gate exposes a new private measurement observer capability, bound to the
same candidate/task/loop/thread/process/fork authority. It may report only
ticket lifecycle facts the gate already computed. It cannot change queue
ordering, wakeups, deadlines, reservations, or exception classes. The exact
terminal/attempt-linked union is:

```text
CapacityMeasurementAdmissionOutcomeEvidenceV49FV8
  outcome: GRANTED | REJECTED | TIMED_OUT | CANCELLED_BEFORE_ENTRY |
           CLOSED_BEFORE_ENTRY | INTERRUPTED_BEFORE_ENTRY |
           FAILED_BEFORE_ENTRY | UNRESOLVED_PROCESS_LOSS
  policy_id / epoch / command_kind / reservation
  admission_sequence | null
  admitted_loop_time_ns | null
  started_loop_time_ns | null
  start_deadline_loop_time_ns | null
  wait_duration_evidence: EXACT | RIGHT_CENSORED_LOWER_BOUND |
                          NOT_APPLICABLE_IMMEDIATE_REJECTION |
                          UNAVAILABLE_PROCESS_LOSS
  wait_duration_nanoseconds | null
  rejection_class | null
  gate_counter_snapshot_before / after
  outcome_evidence_id
```

Only `GRANTED` permits an attempt and requires all grant timestamps.
`REJECTED`, `TIMED_OUT`, `CANCELLED_BEFORE_ENTRY`,
`CLOSED_BEFORE_ENTRY`, `INTERRUPTED_BEFORE_ENTRY`, and
`FAILED_BEFORE_ENTRY` forbid an attempt and require their exact bounded reason.
`UNRESOLVED_PROCESS_LOSS` is permitted only during startup recovery when the
candidate is durable but neither an attempt nor a durable A1 outcome is
provable. Unknown or observer-lost ticket facts are explicit unavailable field
evidence; they are not reconstructed from a cumulative counter difference.

Every candidate marker is emitted by that candidate's owner task. The ticket-
accepted marker is emitted after the owner has synchronously completed ticket
insertion/counter updates and before it awaits. A different active task that
releases the gate may wake the ticket but must not invoke the waiting
candidate's capability. The grant marker is emitted only when the candidate
owner resumes and the existing A1 started/deadline recheck has fixed the exact
grant values. This preserves the task-bound capability and prevents a release
callback from impersonating another candidate.

### 5.3 Attempt schema

`CapacityMeasurementOperationAttemptV49FV8` contains:

```text
candidate_id and exact GRANTED admission-outcome evidence
campaign / manifest-authority / design / workload / trial coordinates
previous V8 operation-terminal ID
operation_spec_id and exact operation kind
transport session / driver nonce / socket / A1 policy authority
projection ledger / schema / validation / fingerprint / store observation
writer-fence token digest and generation
pre-attempt receipt sequence and hash
actor count/tail and complete event-kind-count baseline
full parser cursor and parser-cursor ID
RAW dependency baseline and pending-ingress presence
runtime state and operation-specific precondition evidence
exact A1 grant and absolute loop-clock values
marker contract ID, capacity, full-checkpoint selector, and probe cadence
target-field registry ID
observer, BOOTTIME, loop, process-CPU, and thread-CPU effect-start evidence
started wall time for forensic correlation only
attempt ID
```

The attempt duplicates authority-critical candidate coordinates and exact A1
facts so offline replay can reject candidate/attempt substitution. The
candidate-to-attempt projection-receipt span is empty in the base serial V8
profile because A1 ticket/marker facts are volatile until the attempt/terminal.
Any intervening durable record rejects that sample; it cannot be silently
attributed to this candidate.

Absolute nanosecond readings are canonical unsigned 128-bit decimal strings.
Relative offsets, counts, and durations stay in `0 .. 2^53 - 1` and are valid
only within their named origin/domain. RFC 7493 warns that JSON receivers
cannot be expected to retain integer exactness beyond `2^53 - 1` and recommends
strings when exact larger numbers are required
([RFC 7493 section 2.2](https://www.rfc-editor.org/rfc/rfc7493.html#section-2.2)).

### 5.4 Terminal schema

`CapacityMeasurementOperationTerminalV49FV8` binds the candidate ID, optional
attempt ID, exact admission outcome, target-authorization outcome
(`NOT_REACHED_NON_GRANT`, `ATTEMPT_COMMITTED`,
`ATTEMPT_PERSISTENCE_FAILED`, or `UNRESOLVED_PROCESS_LOSS`), and the Raw V7
trigger, effect-certainty, progress-availability, cancellation, exception-
chain, session-terminal-authority, runtime-state, prefix, and recovery
distinctions. It generalizes returned evidence with an exact tagged result
union:

```text
IngressResultEvidenceV8
SubscriptionDispatchResultEvidenceV8
AckDeadlineExpiryResultEvidenceV8
LocalShutdownResultEvidenceV8
```

A target result is forbidden when no attempt exists. A returned result and an
unavailable-result reason are exactly complementary on attempted operations.
No result is reconstructed as a default. Exception class capture must use the
bounded safe Raw V7 rule and must not call arbitrary exception `__str__`.

The exact terminal members are `operation_result_evidence | null` and
`operation_result_unavailable_reason | null`. With no attempt both are null.
With an attempt exactly one is non-null. The unavailable-result enum is:

```text
TARGET_RAISED_EXCEPTION
TARGET_CANCELLED
TARGET_INTERRUPTED
PROCESS_LOSS_BEFORE_RESULT
RESULT_EVIDENCE_BOUND_EXCEEDED
RESULT_EVIDENCE_VALIDATION_FAILED
UNKNOWN_DELIVERY_PREFIX
```

`UNKNOWN_DELIVERY_PREFIX` is subscription-only and requires the durable prefix
to prove the local uncertainty; it is not a returned dispatch disposition.
Bound/validation failure in observer-owned result conversion cannot replace a
successful target return or alter its durable prefix: it makes measurement
evidence unavailable and keeps the sample provisional.

### 5.5 Marker closure schema

```text
CapacityMeasurementMarkerClosureV49FV8
  candidate_id
  attempt_id | null
  terminal_id
  marker_contract_id
  instrumentation_mode: OFF | ON
  marker_capture_status: COMPLETE | PARTIAL | UNAVAILABLE
  marker_unavailable_reason: exact reason | null
  emitted_total: uint | null
  retained_count: uint
  overwritten_count: uint | null
  first_emitted_ordinal: uint | null
  last_emitted_ordinal: uint | null
  marker_kind_counts | null           # fixed 19-key map
  marker_kind_first_ordinals | null   # fixed 19-position optional-uint tuple
  marker_kind_last_ordinals | null    # fixed 19-position optional-uint tuple
  retained_markers: ordered tuple[CapacityMeasurementMarkerV49FV8]
  numeric_extrema: exact ordered tuple[CapacityMeasurementMarkerExtremumV49FV8] | null
  field_available_counts              # fixed registry-order tuple
  field_not_applicable_counts         # fixed registry-order tuple
  field_unavailable_counts            # fixed registry-order tuple
  field_censored_counts               # fixed registry-order tuple
  status_reason_counts                # exact frozen reason-enum map
  loop_probe_summary                   # exact bounded typed record
  target_observation_count
  ordered_target_observation_ids
  target_observation_root_sha256
  target_observations                  # exact ordered canonical tuple
  marker_observer_error_code: bounded enum | null
  marker_observer_error_class: bounded safe class | null
  closure_completed observer / BOOTTIME / loop clock evidence
  closure_id
```

The bounded marker observer-error enum is exact:

```text
CAPABILITY_MISMATCH
CLOCK_READ_FAILED
CLOCK_REGRESSION
COUNTER_ACCUMULATOR_FAILED
MARKER_SLOT_CONVERSION_FAILED
PROBE_ARITHMETIC_FAILED
PROBE_CALLBACK_FAILED
PROBE_SCHEDULE_FAILED
SAFE_INTEGER_OR_BOUND_EXCEEDED
SERIALIZATION_FAILED
```

`COMPLETE` requires a null marker-unavailable reason/error code, every
conditionally required marker, and exact ring/probe equations. `PARTIAL`
requires either `MARKER_RING_OVERWROTE_PREFIX` with a null observer-error code,
or an exact observer-error code with its compatible frozen status reason;
retained facts remain checkable. `UNAVAILABLE` requires an exact reason and no
claim of a complete ordinary series. `OFF` and process-loss recovery have a
null observer-error code because they are declared disabled/lost states, not
observer exceptions. An unknown code, code/reason mismatch, or arbitrary error
message rejects replay.

The compatibility map is fixed: `CLOCK_READ_FAILED` maps to
`SOURCE_CLOCK_UNAVAILABLE`; `SAFE_INTEGER_OR_BOUND_EXCEEDED` maps to
`ARTIFACT_BOUND_EXCEEDED`; every other observer-error code above maps to
`OBSERVER_INTERNAL_ERROR`. `PERIODIC_PROBE_DID_NOT_FIRE` is a no-fire evidence
reason, not an exception code.

For `OFF`, emitted and retained counts are exact zero,
`overwritten_count=0`, and the status is `UNAVAILABLE` with
`marker_unavailable_reason=INSTRUMENTATION_DISABLED`; the marker-kind counts
are all zero with null ordinals, and `numeric_extrema` is its exact 66-record
all-zero-count tuple. Zero is valid because the absence was
directly configured, not inferred from observer loss. For startup recovery
after process loss, `emitted_total`, `overwritten_count`, and
`numeric_extrema` and all three marker-kind structures are null, not zero,
retained/first/last are respectively zero/null/null, and status is `UNAVAILABLE` with
`marker_unavailable_reason=PROCESS_LOSS_VOLATILE_MARKER_STATE`.

`status_reason_counts` has every frozen Section 10.1 reason key in ascending
UTF-8 order, including zero values, and counts every non-null field-observation
reason across the nested target-observation tuple. It therefore preserves
`NOT_APPLICABLE` reasons separately instead of mislabelling them unavailable.

Before the terminal transaction, the runtime constructs every mandatory
target-observation record that can truthfully be constructed, including
structurally complete unavailable records after an observer failure. The
closure stores their exact ordered canonical records, identities, and a domain-
separated root in the same terminal transaction. The tuple is not a later
volatile sidecar. The sample reuses those byte-exact nested records from the
durable closure; it does not serialize an independently replaceable second
copy. A caller cannot replace target values and merely rehash the outer four-
member bundle, and a crash after closure COMMIT cannot erase the only copy of
the observation bodies. For each registry coordinate, the four availability-
count tuples sum to `target_observation_count`; `NOT_APPLICABLE` and `CENSORED`
are never folded into `UNAVAILABLE`. A minimal observer-error or recovery
closure still stores the exact structurally complete unavailable/recovery
observation set. Failure to construct even that bounded set leaves the
candidate open for startup reconciliation; it does not create an unbound
sample.

### 5.6 Transaction and recovery rules

- Candidate persistence failure prevents the A1 call and target operation.
- A1 non-grant closes the candidate with no attempt and no target effect.
- If A1 grants but attempt persistence fails or is uncertain, the target is not
  invoked and the runtime is fenced while SQLite outcome is reconciled. A
  conclusive absent attempt closes as `ATTEMPT_PERSISTENCE_FAILED` with exact
  `GRANTED` evidence; a committed attempt is recovered by identity. A restart
  that cannot recover the volatile grant uses `UNRESOLVED_PROCESS_LOSS`.
- Same-task return, exception, cancellation, and interruption derive the exact
  target prefix before committing terminal plus closure.
- Cancellation is re-raised only after that transaction commits. V8 does not
  suppress, replace, or call `uncancel()` on `CancelledError`.
- If a marker observer fails, the store writes a minimal bounded closure with
  `UNAVAILABLE` or `PARTIAL`; it does not omit the candidate terminal.
- If the terminal/closure transaction fails or is uncertain, the candidate
  remains open and the runtime is fenced according to Raw V7 precedence. It
  must not return a fabricated terminal.
- Startup recovery runs before the next runtime command. It reconstructs the
  durable target prefix where an attempt exists, writes a recovery terminal
  and an unavailable marker closure in one transaction, and never retries A1
  admission or the target effect.
- Crash after commit but before caller acknowledgement leaves both terminal
  and closure durable; replay is idempotent.
- Crash before commit leaves neither; SQLite recovery decides the transaction,
  then startup reconciliation closes the candidate.

SQLite documents that `BEGIN IMMEDIATE` can fail with `SQLITE_BUSY`, that only
one write transaction can exist at once, and that FULL/IOERR/INTERRUPT may
roll back a statement or the whole transaction depending on the failure point.
V8 therefore records exact transaction stage and resulting state rather than
assuming every error has the same effect
([SQLite transactions](https://www.sqlite.org/lang_transaction.html),
[SQLite result codes](https://www.sqlite.org/rescode.html)).

Cancellation or fatal interruption before the first candidate commit produces
no V8 operation record and therefore no V8 artifact. Between operations, a
prefix is artifact-eligible only if its last durable terminal is independently
run-ending under the signed schedule. Otherwise a cancellation/interruption
before the next candidate commit permanently makes that campaign artifact-
ineligible. The runner must perform all synchronous pre-candidate checks,
candidate construction, and candidate commit without an intervening await;
it may not publish an ordinary successful prefix as if it proved why
the next operation is missing.

## 6. Exact four-command operation union

### 6.1 Common declaration

`CapacityMeasurementOperationDeclarationV49FV8` has common campaign,
workload, sample, trial, repetition, warm-up, stage, timeout-policy, and
operation-sequence fields plus exactly one typed spec. The union tag and exact
spec type must agree. Unknown keys, a second spec, a null spec, aliases, and
duck-typed mappings reject.

```text
operation_kind = INGRESS
  -> CapacityMeasurementIngressOperationSpecV49FV8
operation_kind = SUBSCRIPTION_DISPATCH
  -> CapacityMeasurementSubscriptionDispatchSpecV49FV8
operation_kind = ACK_DEADLINE_EXPIRY
  -> CapacityMeasurementAckDeadlineExpirySpecV49FV8
operation_kind = LOCAL_SHUTDOWN
  -> CapacityMeasurementLocalShutdownSpecV49FV8
```

The production dispatcher has exactly these four call shapes and no generic
callback branch:

```text
INGRESS              -> await runtime.process_next_ingress_v49d(
                            timeout_seconds=spec.timeout_seconds)
SUBSCRIPTION_DISPATCH -> await runtime.dispatch_subscription_v49c(
                            idempotency_key=spec.idempotency_key)
ACK_DEADLINE_EXPIRY  -> await runtime.expire_ack_if_due_v49e()
LOCAL_SHUTDOWN       -> await runtime.shutdown_current_v49e(
                            timeout_seconds=spec.timeout_seconds)
```

The manifest value is passed explicitly where a timeout exists; Python method
defaults are not an unsigned workload choice. ACK expiry has no timeout or
clock argument, and the sampler may not add one.

### 6.2 Operation-specific schemas and oracles

| Kind | Exact predeclared spec | Runtime-owned attempt facts | Exact result/oracle |
|---|---|---|---|
| `INGRESS` | Ordered bounded input chunks, input/batch hashes, timeout, ordered expected logical Pong/Close frames | Initial-pending flag, RAW/parser baseline, A1 grant | Existing V7-style RAW/parser/application/automatic-output prefix plus exact returned ingress result; logical oracle is independent of random client masking |
| `SUBSCRIPTION_DISPATCH` | Bounded idempotency key, expected retained intent/request/command identities and expected local dispatch disposition | Exact retained intent, application fence, parser-open/quiescent precondition, A1 grant | Durable prepared logical wire, TLS ciphertext, ordered kernel attempt/results, local accepted-octet prefix, dispatch completion, and returned dispatch-window identity; never peer receipt |
| `ACK_DEADLINE_EXPIRY` | Expected due/not-due scenario and exact retained intent identity; no caller clock | Committed wall/monotonic deadline, clock-domain evidence, parser/output quiescence, A1 grant | `expired=false` plus the exact governed due-decision clock bracket, or `expired=true` plus ACK-expired/terminal atomic pair and termination identity |
| `LOCAL_SHUTDOWN` | Bounded timeout and expected terminal class; no injected Close bytes, code, socket, TLS artifact, or effect callback | Exact command deadline, parser/output precondition, actor/driver/owner state, A1 grant | Ordered local Close, TLS control, kernel results, half-close, peer-shutdown observation, terminal convergence, and returned termination identity as far as the durable prefix proves |

The runner invokes the existing owner-derived public/internal runtime operation;
it does not duplicate its implementation or expose new effect callbacks.
Operation-specific test seams may inject deterministic clocks, sockets, and
faults only in non-live exact test profiles.

### 6.3 Schedule/state legality

One V8 campaign manifest still binds one exact transport session. A schedule
is accepted only if each operation's candidate-time precondition follows from
the previous durable terminal/prefix. In particular:

- pending complete ingress and automatic output must not be overtaken by a
  subscription, ACK-expiry, or shutdown command;
- subscription dispatch is legal only in its existing committed-session state;
- ACK expiry is legal only for the exact retained awaiting-ACK intent;
- a terminal ACK expiry or local shutdown is the last operation for that
  session;
- a workload requiring a fresh session is a separate manifest/campaign, not a
  hidden reset inside one schedule; and
- covering all four kinds may require several single-session campaigns. This
  is not multi-session scheduling and creates no V4.9F-B claim.

The base V8 profile permits only one open measured candidate per session and
does not manufacture A1 contention. It can record whatever exact queue state is
already present at a boundary, but ambient or undeclared work invalidates a
campaign sample. Queued/rejection lifecycle paths are still falsified with the
exact non-live A1 test profiles in the acceptance matrix. A future campaign
that needs concurrently open measured commands requires a new versioned same-
session launch/schedule profile (and likely a new raw domain); it may not
silently raise the one-candidate bound. This is distinct from V4.9F-B multi-
session scheduling.

The exact schedule is predeclared. The runner may stop only under the same
complete-schedule or locally issued, structurally replayed run-ending-prefix
rules as Raw V7, generalized to all four terminal types and pre-admission
candidate outcomes. This local rule does not attest the provenance or
completeness of the post-run suffix. The runner may not choose the next
operation after inspecting a measured marker or provisional threshold.

### 6.4 Per-operation effect certainty

| Operation/outcome | Strongest permissible local statement |
|---|---|
| A1 rejected/timed out/closed/cancelled/interrupted/failed before entry | exact admission outcome and `NO_DURABLE_TARGET_EFFECT`; no operation attempt |
| A1 granted but V8 attempt persistence conclusively failed | exact `GRANTED` plus `ATTEMPT_PERSISTENCE_FAILED` and `NO_DURABLE_TARGET_EFFECT`; failed raw sample remains included |
| Ingress returned with prefix replay equality | `COMPLETE` locally; no remote-data claim |
| Subscription returned after exact dispatch completion | `COMPLETE_LOCAL_SUBMISSION`; kernel acceptance is not peer receipt |
| ACK expiry returned `False` | Exact completed no-terminal decision at its clock bracket; not evidence the deadline was never due later |
| ACK expiry returned `True` | Exact durable deadline/terminal pair |
| Local shutdown returned | Exact durable terminal and proven local physical prefix; peer receipt only where existing protocol evidence proves it |
| Raised/cancelled with exact nonempty prefix | `EXACT_COMPLETED_PREFIX` |
| Raised/cancelled after grant but before any durable target record | `NO_DURABLE_EFFECT` |
| Positive send result with missing durable resolution or ambiguous storage | `UNKNOWN`; never retry authority |
| Startup-recovered orphan | strongest prefix-derived certainty, with marker state unavailable and only truthfully bounded duration fields censored |

## 7. Stable in-operation marker contract

### 7.1 Stable means causal, not instantaneous

A marker hook is legal only after an indivisible admission/target transition
has reached its existing stable or durable convergence point and before the
next target mutation. It records a sequential observation bracket, not the
exact instant at which the target effect occurred. Its anchor is the latest
projection receipt and, where applicable, A1 ticket state, actor event, or
parser cursor already stable at that cutoff.

A hook is forbidden:

- between a parser mutation and its durable parser event;
- between generated Pong/Close bytes and exact dispatch completion or terminal
  uncertainty;
- inside an unresolved kernel send attempt;
- inside an unresolved SQLite transaction;
- between a shutdown observation and its required paired marker/terminal; or
- while a mutable actor candidate has not yet been journal-confirmed.

### 7.2 Frozen marker kinds and anchors

The following rows are conditionally mandatory in `ON` mode when their stated
lifecycle/state is reached. `OFF` mode emits none of them and proves that fact
through its disabled closure; a missing required `ON` marker is not excused as
ordinary unavailability.

| Operation | Required marker kind | Minimum stable/durable anchor |
|---|---|---|
| All | `ADMISSION_CANDIDATE_COMMITTED` | committed V8 candidate receipt, before the A1 call; no ticket or target effect is implied |
| All A1-accepted tickets | `ADMISSION_TICKET_ACCEPTED` | exact A1 sequence/reservation and fully updated stable gate state, whether the ticket is waiting or active; no caller target effect |
| All granted | `ADMISSION_GRANTED` | exact active A1 grant, before V8 attempt/target effect |
| All non-grants | `ADMISSION_NOT_GRANTED` | exact A1 rejection/timeout/closed/cancellation/interruption/failure outcome; no V8 attempt |
| All attempted | `TARGET_EFFECT_ENTRY` | committed V8 attempt and active A1 grant, before first target mutation |
| Ingress | `RAW_PREFIX_COMMITTED` | RAW commit receipt and matching `RAW_INGRESS_COMMITTED` actor event |
| Ingress | `PARSER_UNIT_CONVERGED` | parser transition plus any application commit and automatic output completion/uncertainty attributable to that unit |
| Ingress | `INGRESS_RETURN_READY` | final parser cursor, retained tail, output obligations, and returned prefix stable |
| Subscription | `OUTBOUND_ARTIFACTS_PREPARED` | application wire and TLS-ciphertext prepared events durable |
| Subscription | `KERNEL_SEND_RESULT_CONVERGED` | matching attempt plus result/failure durable; accepted prefix known |
| Subscription | `DISPATCH_RETURN_READY` | `OUTBOUND_DISPATCH_COMPLETED` durable and dispatch window fixed |
| ACK expiry | `ACK_DEADLINE_NOT_DUE` | exact clock bracket fixed, no target actor mutation, returned `False` fixed |
| ACK expiry | `ACK_DEADLINE_TERMINAL_CONVERGED` | consecutive expiry/terminal pair and session termination durable |
| Local shutdown | `SHUTDOWN_COMMAND_STARTED` | command/deadline evidence durable |
| Local shutdown | `LOCAL_CLOSE_DISPATCH_CONVERGED` | local WebSocket Close dispatch complete or exact uncertainty durable |
| Local shutdown | `TLS_CONTROL_CONVERGED` | TLS-control result/failure durable |
| Local shutdown | `TCP_HALF_CLOSE_CONVERGED` | half-close result durable |
| Local shutdown | `SHUTDOWN_TERMINAL_CONVERGED` | terminal convergence pair durable |
| All adverse exits | `TARGET_ESCAPE_OBSERVED` | latest exact durable prefix after target cleanup, before V8 terminal construction |

If an existing operation has no legal hook matching a required row, V8 is not
implemented for that operation. A marker must not be moved earlier merely to
obtain a timestamp.

The exact marker-kind key tuple, serialized in ascending UTF-8 order, is:

```text
ACK_DEADLINE_NOT_DUE
ACK_DEADLINE_TERMINAL_CONVERGED
ADMISSION_CANDIDATE_COMMITTED
ADMISSION_GRANTED
ADMISSION_NOT_GRANTED
ADMISSION_TICKET_ACCEPTED
DISPATCH_RETURN_READY
INGRESS_RETURN_READY
KERNEL_SEND_RESULT_CONVERGED
LOCAL_CLOSE_DISPATCH_CONVERGED
OUTBOUND_ARTIFACTS_PREPARED
PARSER_UNIT_CONVERGED
RAW_PREFIX_COMMITTED
SHUTDOWN_COMMAND_STARTED
SHUTDOWN_TERMINAL_CONVERGED
TARGET_EFFECT_ENTRY
TARGET_ESCAPE_OBSERVED
TCP_HALF_CLOSE_CONVERGED
TLS_CONTROL_CONVERGED
```

### 7.3 Compact marker schema

```text
CapacityMeasurementMarkerV49FV8
  candidate_id
  attempt_id | null
  marker_ordinal                       # starts at 1, strictly increasing
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
  operation_counter_snapshot           # fixed typed counters, no dictionary
  target_checkpoint_id | null
  target_checkpoint_unavailable_reason | null
  marker_id
```

The canonical record above is **not** constructed by the stable hook. The hook
runs synchronously in the candidate owner task or in the same-loop A1 gate
transition for pre-entry markers. It performs no await, lock acquisition,
canonical serialization, hashing, source-currentness check, filesystem read,
socket ioctl, SQLite query/write, logging, or exporter call. The ring and fixed
internal slots are allocated before the candidate is committed. The hook may
read already-owned scalar/counter references, sample the frozen clocks, and
replace one slot with a fixed-layout internal payload containing primitive
values and retained object identities only.

After the target has reached its return/escape boundary and the marker ring is
sealed, the closure builder converts retained internal slots to immutable
`CapacityMeasurementMarkerV49FV8` records in ordinal order, performs canonical
serialization and hashing, and cross-checks every copied primitive against the
sealed slot. A checkpoint observation refers to the candidate and marker
ordinal, not to `marker_id`; its observation ID is then inserted into the
canonical marker as `target_checkpoint_id`, avoiding a hash cycle. Slot
conversion or hashing failure sets the bounded closure error and produces
partial/unavailable evidence without entering target control flow. No slot is
mutated after sealing, and neither a slot nor a canonical marker is public or
caller-constructible.

Expensive full target checkpoints are a separate, predeclared selector. A
selected checkpoint runs immediately after the compact marker, still before
the next target mutation, and records its own sequential adapter spans. The
manifest fixes marker kinds/ordinals eligible for full checkpoints and a hard
maximum count. No observed occupancy, delay, error, or provisional high-water
value can trigger an extra checkpoint.

Full checkpoints are forbidden at `ADMISSION_CANDIDATE_COMMITTED`,
`ADMISSION_TICKET_ACCEPTED`, `ADMISSION_GRANTED`, `ADMISSION_NOT_GRANTED`, and
`TARGET_EFFECT_ENTRY`: external adapters at those seams could change A1 queue
or target-start timing. The selector may name only an operation-specific
target-convergence marker or `TARGET_ESCAPE_OBSERVED`, and only after a source
review proves that the checkpoint sits outside an active SQLite transaction and
that no target mutation remains unresolved.

### 7.4 Ring semantics

Let the manifest capacity be `C`, with `8 <= C <= 4096`.

```text
emitted_total == 0:
    retained = []
    retained_count = 0
    overwritten_count = 0
    first_emitted_ordinal = null
    last_emitted_ordinal = null

1 <= emitted_total <= C:
    retained = markers[1 .. emitted_total]
    retained_count = emitted_total
    overwritten_count = 0
    first_emitted_ordinal = 1
    last_emitted_ordinal = emitted_total

emitted_total > C:
    retained = marker[1]
             + markers[(emitted_total - (C - 2)) .. emitted_total]
    retained_count = C
    overwritten_count = emitted_total - C
    first_emitted_ordinal = 1
    last_emitted_ordinal = emitted_total
```

Thus slot zero permanently retains ordinal 1 and the remaining `C - 1` slots
form an overwrite-tail ring. The inclusive tail range in the formula contains
exactly `C - 1` markers. Retained markers serialize in increasing ordinal
order. Gaps are permitted only when `overwritten_count > 0`, and the exact
ordinal formula above must explain every gap.

The 19 kind counters and first/last-ordinal tuples are updated before a slot is
eligible for overwrite and survive ring loss. Their counts sum to
`emitted_total`; a zero count requires null first/last ordinals, while a
positive count requires `1 <= first <= last <= emitted_total`. Retained marker
kinds/ordinals must agree with these accumulators. Offline replay cross-checks
each conditionally mandatory kind/count against the A1 outcome and exact
durable target prefix, so overflow cannot hide whether a required hook was
ever emitted. It still cannot recover the complete lost series; overflow
remains series-ineligible as stated below.

These equations apply only when the ordinary same-process ring counters are
known. Process-loss recovery uses the explicit null/empty closure defined in
Section 5.5 and must not run this equation with a fabricated zero. Arithmetic
is checked before increment; reaching `2^53 - 1` seals measurement as partial
with `ARTIFACT_BOUND_EXCEEDED` and never wraps the counter or raises into the
target.

Each of the exact 66 compact-snapshot coordinates frozen in Section 12.3 also
has an O(1) accumulator containing:

```text
available_count
unavailable_count
minimum value + first ordinal
maximum value + first ordinal
last available value + ordinal
```

`numeric_extrema` contains exactly 66 records in that same positional order.
For ordinary same-process capture, each record satisfies
`available_count + unavailable_count = emitted_total`; zero available values
requires null minimum/maximum/last values and ordinals, while a positive count
requires all three. First-ordinal ties are stable. In `OFF`, both counts are
zero. Process-loss recovery marks this entire volatile extrema tuple
unavailable rather than manufacturing 66 zero-count histories.

These extrema survive ring overwrite. They are observer evidence, not a
threshold. If accumulator update fails, the closure is partial and the value
is unavailable; it is never reconstructed from retained markers alone while
claiming completeness.

Ring exhaustion never waits, raises into the target, expands storage, changes
checkpoint cadence, or switches to synchronous durable writes. Calibration or
confirmation analysis requiring a complete series must reject any closure
with overwrites. A preregistered analysis may use an exact extremum from a
partial ring only if its derivation and available/unavailable counts are
complete and that use was declared before results were inspected.

Python's bounded `deque` automatically discards from the opposite end when
full, but Raw V8 uses an explicit preallocated first-plus-tail structure
because it must preserve ordinal 1 and exact loss accounting; the standard
library behavior is mechanism context, not the V8 evidence contract
([Python 3.12 `collections.deque`](https://docs.python.org/3.12/library/collections.html#collections.deque)).

### 7.5 Marker capability

The runtime creates one sealed marker capability before candidate persistence.
It is valid only for the exact process, thread, event loop, current asyncio
task, fork generation, candidate ID, optional attempt ID after binding,
operation kind, and ring instance. It is never exported. Clone, reuse after
closure, cross-task use, cross-loop use, post-fork use, wrong marker kind,
nonmonotone ordinal, wrong anchor, or a hook outside the candidate lifecycle
rejects the measurement path and sets a bounded observer error. It must not
authorize A1 admission or a target effect.

## 8. Periodic event-loop probe

The loop probe complements stable hooks; it does not replace them.

In `ON` mode it starts after `ADMISSION_CANDIDATE_COMMITTED` and before the A1
call, so the series covers queue wait as well as an admitted target. Scheduling
failure sets the bounded observer error and does not suppress or delay the A1
call through retry. `OFF` mode never creates a timer handle.

The timer owns a separate sealed loop/thread/process/fork/candidate probe
capability. It is not the task-bound stable-marker capability, carries no target
effect authority, and cannot emit a stable marker or full checkpoint. This is
required because an asyncio callback is not execution by the candidate task.

The manifest fixes an integer interval `P`, a maximum retained probe count,
the exact loop implementation, the `loop.time()`-to-integer conversion profile,
and a measured clock-resolution field. Raw V8 admits exactly
`FLOOR_SECONDS_TIMES_1E9_V1`: every non-negative `loop.time()` float is
converted once as `floor(value * 1_000_000_000)`. The manifest stores
`loop_clock_resolution_ns = max(1, ceil(get_clock_info('monotonic').resolution
* 1_000_000_000))` and
`early_tolerance_ns = loop_clock_resolution_ns + 1`; all three values and the
source float representation are bound by the source observation. Overflow or
a different conversion profile rejects admission. Immediately after the
candidate marker slot is written, the owner samples an integer loop offset
`s`; phase index zero
has `expected_0 = s + P` and is the first and only scheduled callback. A fired
probe retains its phase index `q`, not merely its callback ordinal:

```text
expected_q = expected_0 + q * P
delay_q    = max(0, actual_q - expected_q)
```

After phase `q` fires at integer loop offset `a`, the next phase is exactly:

```text
if a < expected_0:
    q_next = q + 1
else:
    q_next = max(q + 1, floor((a - expected_0) / P) + 1)

newly_missed = q_next - q - 1
next_expected = expected_0 + q_next * P
```

The callback atomically adds `newly_missed`, writes one preallocated probe slot,
and schedules exactly one successor at `next_expected`. It never schedules the
missed phases and never invokes a callback recursively, so a late wake-up
cannot create a catch-up storm. All additions and multiplications are checked
against the safe-integer and manifest bounds before scheduling; overflow sets
the sticky observer error and stops the probe without affecting the target.

`probes_scheduled` increments only after a `call_at` handle is successfully
created: once for the initial handle and once for each successful successor.
Skipped original phases are counted only in `probe_phases_missed`, not as
scheduled handles. `probes_fired` increments on callback entry. Before closure,
a healthy active probe therefore has one more scheduled than fired; after
closure its sole pending handle is recorded as cancelled, not fired.

The internal probe slot freezes:

```text
callback_ordinal
phase_index
expected_loop_offset_ns
actual_loop_offset_ns
exact_delay_ns
observer_callback_started_offset_ns
observer_callback_completed_offset_ns
```

As with stable markers, canonical probe records and identities are constructed
only after sealing, outside the callback. The strict summary contains the
probe status/reason, `P`, capacity, `s`, `expected_0`, scheduled/fired/retained/
overwritten counts, first/last callback ordinals and phase indices, exact
retained records, phases missed, exact fired-delay total, maximum plus first
ordinal, last fired delay plus ordinal, next phase/expected offset, optional
right-censored final lower bound, callback observer-span total/maximum, and a
bounded observer error. No generic map or unbounded callback list is allowed.

Probe status is exactly `DISABLED`, `COMPLETE`, `PARTIAL`, or `UNAVAILABLE`.
`DISABLED` is legal only in instrumentation `OFF` with
`INSTRUMENTATION_DISABLED`; `COMPLETE` has no reason/error; `PARTIAL` uses
`PROBE_RING_OVERWROTE_PREFIX`, `PERIODIC_PROBE_DID_NOT_FIRE`, or the exact
observer-code/reason map from Section 5.5; `UNAVAILABLE` is reserved for no
truthful probe series after process loss or initial scheduling/clock failure.
Closing before the first phase becomes due is a complete observed zero-fire
series with one cancelled scheduled handle and no no-fire reason. A due but
unexecuted phase is the right-censored partial case.

Let probe capacity be `L`, with `4 <= L <= 4096`. Fired probes use the same
first-plus-overwrite-tail retention equation as markers with `C := L`; their
own exact fired/retained/overwritten counts, ordinal range, total delay, maximum
delay plus first ordinal, and last delay survive overwrite. The probe summary
is a strict typed record, not a dictionary. `probe_phases_missed` includes both
phases skipped when a late callback schedules its successor and original-phase
deadlines already due at terminal closure whose callback could not run. A
censored final delay is never added to the exact fired-delay total or maximum.

At candidate closure, after cancelling the one live handle, let `c` be the
terminal loop offset and let `(q_next, next_expected)` be the one pending phase.
If `c >= next_expected`, closure adds exactly
`floor((c - next_expected) / P) + 1` due phases to `probe_phases_missed` and
records `c - next_expected` as the right-censored lower bound for the first
unfired due callback. It does not add any censored value to exact fired-delay
totals or maxima. Therefore:

- the handle is cancelled;
- callbacks already executed remain evidence;
- a due callback that never executed produces a right-censored lower bound
  from its expected loop time to the terminal loop observation; and
- cancellation-before-first-fire is distinct from an observed zero delay.

That terminal formula applies only when the initial or successor handle was
successfully created and remains pending. If initial/successor scheduling or
counter arithmetic already stopped the probe, pending phase/expected fields
and the final delay bound are null, the exact sticky observer error makes the
summary partial/unavailable, and closure does not invent post-failure missed
phases.

Python 3.12 documents that `call_at()` uses the loop clock and that equal-time
callback order is undefined. The CPython 3.12.12 default loop implementation
also moves timers whose deadline is below `loop.time() + _clock_resolution`
into the ready queue; the 3.13 API documentation states the corresponding
one-resolution-early behavior explicitly. V8 therefore admits this early-
execution tolerance only for the exact manifest-bound CPython implementation,
stores expected and actual values, floors a negative delay only when its
magnitude is at most the exact signed `early_tolerance_ns`, and marks
a larger early observation partial. A different event-loop implementation
requires its own source observation, timing-semantics profile, and tests; the
CPython rule is not generalized by assumption
([Python 3.12 asyncio event-loop scheduling](https://docs.python.org/3.12/library/asyncio-eventloop.html#scheduling-delayed-callbacks),
[CPython 3.12.12 `BaseEventLoop._run_once`](https://github.com/python/cpython/blob/v3.12.12/Lib/asyncio/base_events.py),
[Python 3.13 asyncio event-loop scheduling](https://docs.python.org/3.13/library/asyncio-eventloop.html#scheduling-delayed-callbacks)).

## 9. Clock and information-cutoff rules

V8 retains separate domains:

| Domain | Source | Permitted use |
|---|---|---|
| observer monotonic | `time.monotonic_ns()` | local observer spans under the manifest-bound implementation; suspend inclusion is not inferred |
| governed BOOTTIME | `clock_gettime_ns(CLOCK_BOOTTIME)` | physical/freshness durations that include suspend |
| event-loop clock | each `loop.time()` reading converted exactly once to integer ns under the signed conversion profile | A1 queue and callback-scheduling relationships within that exact loop |
| process CPU | `time.process_time_ns()` | process CPU deltas, not elapsed time |
| owner-thread CPU | `time.thread_time_ns()` | owner-thread CPU deltas, not elapsed time or other threads |
| wall time | governed signed clock evidence | forensic correlation and committed deadlines only |

Python documents that `CLOCK_BOOTTIME` includes system suspend, monotonic clock
reference points are undefined and only differences are meaningful, and
thread CPU excludes sleep and is thread-specific. V8 does not subtract across
these domains or describe CPU time as latency
([Python 3.12 `time`](https://docs.python.org/3.12/library/time.html)).

For one marker the exact cutoff is:

```text
stable/durable admission or target boundary completed
-> observer_before
-> copy stable owner counters and durable anchor IDs
-> sample BOOTTIME / loop / thread CPU in the frozen order
-> optional predeclared sequential full checkpoint
-> observer_after
-> next target mutation may begin
```

Each external field carries its own adapter begin/end offsets. Kernel, TLS,
runtime, SQLite, procfs, cgroup, and loop values are never claimed to be one
atomic state. A marker only proves that its stable admission/target boundary
preceded the observer bracket and the next governed mutation followed it in the
same owner task.

## 10. Complete typed target-field schema

### 10.1 Exact value and availability union

Every field is described by one immutable descriptor in
`CapacityMeasurementTargetFieldRegistryV49FV8`. Canonical order is ascending
UTF-8 `field_id`; the registry ID commits the complete ordered descriptor
array. A descriptor fixes:

```text
field_id
layer
value_kind
unit
value_constraint_id
observation_method_role_pairs
allowed_checkpoint_marker_kinds
applicable_operation_kinds
allowed_status_reasons
status_reason_policy_id
censoring_allowed
later_threshold_action_if_unavailable
value_shape_id
value_shape_keys
cross_field_constraint_ids
```

`observation_method_role_pairs` is an ordered tuple of
`{observation_method, allowed_roles}` records. It is deliberately not two
independent sets: a method is legal only in the roles paired with it. The
checkpoint-marker tuple, operation tuple, status-reason tuple, exact value
constraint, fixed value-shape key tuple, and cross-field constraint IDs are
also committed directly by the descriptor. There is therefore no implicit
Cartesian product or schema-external enum assignment for an implementation to
interpret. The display-only profile spelling is generator metadata and is not
serialized in the descriptor; its fully expanded members above are the
identity authority.

`NOT_ATTEMPTED` is not a method-role pair. It is admitted only by the exact
non-available status combinations in this section. Absence of an available
method for a role does not itself make a field semantically not applicable:
at `STARTUP_RECOVERY`, an applicable pre-crash volatile fact is
`UNAVAILABLE/PROCESS_LOSS_VOLATILE_MARKER_STATE`; it is
`NOT_APPLICABLE_TO_REACHED_STATE` only when the lifecycle proves that the
field's semantic state (for example, target entry) was never reached.

The strict value union is:

```text
UINT                 {kind, value}
BOOL                 {kind, value}
TEXT                 {kind, value}
OPTIONAL_UINT        {kind, present, value|null}
OPTIONAL_TEXT        {kind, present, value|null}
UINT_LIST            {kind, values[]}
TEXT_LIST            {kind, values[]}
FIXED_UINT_MAP       {kind, ordered [{key, value}]}
DURATION_BOUND       {kind, relation: EXACT|LOWER_BOUND|UPPER_BOUND|INTERVAL,
                       lower_nanoseconds|null,
                       upper_nanoseconds|null}
```

Integers use the I-JSON-safe range. An absolute nanosecond clock is `TEXT`
validated as canonical uint128 decimal. Fixed maps have a schema-frozen key
set and order; arbitrary mappings are forbidden.

The optional and duration variants have no permissive third state.
`OPTIONAL_UINT` and `OPTIONAL_TEXT` require
`present=false <=> value=null` and `present=true <=> value!=null`.
`DURATION_BOUND` uses this exact endpoint table:

| Relation | Lower | Upper |
|---|---|---|
| `EXACT` | required | required and equal to lower |
| `LOWER_BOUND` | required | null |
| `UPPER_BOUND` | null | required |
| `INTERVAL` | required | required and greater than or equal to lower |

No relation admits a superfluous endpoint. Every endpoint is an I-JSON-safe
unsigned integer. These rules apply before the availability/censoring table;
an exact duration is `AVAILABLE`, while lower/upper/interval bounds are legal
only in the corresponding `CENSORED` state.

`CapacityMeasurementTargetFieldObservationV49FV8` contains:

```text
target_field_registry_id
observation_context_id
field_id
availability: AVAILABLE | NOT_APPLICABLE | UNAVAILABLE | CENSORED
value: exact value union | null
observation_method: exact registered method | NOT_ATTEMPTED
observation_attempt: NOT_ATTEMPTED | ATTEMPTED
adapter_span_status: AVAILABLE | NOT_APPLICABLE | UNAVAILABLE
observation_started_offset_nanoseconds | null
observation_completed_offset_nanoseconds | null
unavailable_reason: exact reason | null
censoring: NONE | LEFT | RIGHT | INTERVAL
source_errno_number: uint | null
source_errno_name: bounded identifier | null
source_failure_phase: NONE | FIRST_CLOCK_READ | SECOND_CLOCK_READ |
                      SOURCE_ADAPTER | VALUE_VALIDATION
source_error_class: bounded safe class name | null
source_error_detail_sha256: hash | null
field_observation_id
```

`field_observation_id` hashes the exact domain
`RiskYieldMMA2MTargetFieldObservationV4_9F_RawV8`, the field-observation schema
version, and the complete canonical record without its ID. It is not a caller-
supplied label. Binding `target_field_registry_id` prevents the same bytes from
being reinterpreted under a different descriptor or enum assignment. Binding
`observation_context_id` prevents a valid field record from being replayed
across a different candidate, attempt, role, operation, marker, or clock span.

Rules are exact:

- `AVAILABLE` requires one correctly typed value, `censoring=NONE`, and no
  unavailable reason. Its observation was attempted, has an exact span, and
  uses `source_failure_phase=NONE`. A `DURATION_BOUND` available value uses
  `relation=EXACT` with equal non-null lower and upper values.
- `NOT_APPLICABLE` requires null value, `censoring=NONE`, and an exact
  `NOT_APPLICABLE_TO_OPERATION` or
  `NOT_APPLICABLE_TO_REACHED_STATE` reason. It does not mean unsupported;
  `observation_method=NOT_ATTEMPTED`, `observation_attempt=NOT_ATTEMPTED`, and
  no adapter span are required, with `source_failure_phase=NONE`.
- `UNAVAILABLE` requires null value and a reason. It is never converted to an
  empty list, false, or zero. `ATTEMPTED` plus a span distinguishes adapter
  failure from `NOT_ATTEMPTED` because the mode/state precluded observation.
- `CENSORED` is admitted only when the descriptor has
  `value_kind=DURATION_BOUND` and `censoring_allowed=true`. It requires a
  non-null `DURATION_BOUND`, an attempted registered method and ordered span,
  no unavailable reason, and `source_failure_phase=NONE`. `LEFT` maps to
  `UPPER_BOUND`, `RIGHT` maps to
  `LOWER_BOUND`, and `INTERVAL` maps to `INTERVAL`; required endpoints are
  non-null and an interval has `lower <= upper`. If even one truthful bound is
  unavailable, the status is `UNAVAILABLE` with a reason, never `CENSORED`
  with null.
- `ATTEMPTED` normally requires `adapter_span_status=AVAILABLE` and both
  offsets in order. The sole exception is the exact second-bracket-read
  `UNAVAILABLE/SOURCE_CLOCK_UNAVAILABLE` path in Section 10.2, which requires
  `adapter_span_status=UNAVAILABLE`, null offsets, a registered source method,
  and discarding the source value. A first-bracket-read failure does not invoke
  the source and therefore uses `NOT_ATTEMPTED`, the sentinel method, the
  not-applicable span, and null offsets. Every other `NOT_ATTEMPTED` case also
  requires `adapter_span_status=NOT_APPLICABLE`, forbids both offsets, and
  requires the `NOT_ATTEMPTED` method; zero is never used as a stand-in for no
  observation.
- errno number/name are present together only for an OS error; the symbolic
  name is checked against the captured runtime platform mapping.
- an arbitrary exception message is never serialized. Only a safe exact class
  name and the exact reconstructable error-detail identity below are admitted.
- wrong field, unit, method, role, operation applicability, value kind, or
  span order rejects the complete observation.

An `UNAVAILABLE/ATTEMPTED` OS failure carries the registered OS method, its
span status under the rule above, errno number/name, and either both the
bounded safe class and metadata digest or neither. An
`UNAVAILABLE/ATTEMPTED` non-OS failure forbids errno and requires both the
bounded safe class and metadata digest. An `UNAVAILABLE/NOT_ATTEMPTED` value
uses method `NOT_ATTEMPTED`, has no span or source-error tuple, and is legal
only for a descriptor-admitted disabled, unreached, unsupported, unsafe-to-
observe, no-policy, no-source, process-loss, or bound reason. These combinations
are part of the registry descriptor and are not selected by callers.

The frozen reason enum is:

```text
INSTRUMENTATION_DISABLED
NOT_APPLICABLE_TO_OPERATION
NOT_APPLICABLE_TO_REACHED_STATE
TARGET_BOUNDARY_NOT_REACHED
NO_FROZEN_PRESSURE_POLICY
UNSUPPORTED_BY_KERNEL
UNSUPPORTED_BY_PYTHON_RUNTIME
PERMISSION_DENIED
OS_OBSERVATION_ERROR
OBSERVER_INTERNAL_ERROR
OBSERVATION_WOULD_MUTATE_TARGET
OBSERVATION_WOULD_REENTER_TARGET_LOCK
OBSERVATION_WOULD_REENTER_ACTIVE_SQLITE_TRANSACTION
NO_STABLE_SLOW_CALLBACK_SOURCE
MARKER_RING_OVERWROTE_PREFIX
PERIODIC_PROBE_DID_NOT_FIRE
PROBE_RING_OVERWROTE_PREFIX
PROCESS_LOSS_VOLATILE_MARKER_STATE
SOURCE_DURABLE_RECORD_ABSENT
SOURCE_COUNTER_NOT_INSTRUMENTED
SOURCE_CLOCK_UNAVAILABLE
ARTIFACT_BOUND_EXCEEDED
```

New reasons require a new registry/schema. Free-form fallback reasons are
forbidden. `later_threshold_action_if_unavailable` is always `FAIL_CLOSED` for
a field used by a future policy. That field is descriptive metadata; Raw V8
does not execute the action.

#### 10.1.1 Exact descriptor vocabulary

The registry uses only these observation methods, in this exact lexical form:

```text
A1_OUTCOME_CAPABILITY
A1_OWNER_SNAPSHOT
ACTOR_OWNER_SNAPSHOT
CGROUP_V2_MEMORY_CURRENT
DURABLE_GOVERNED_CLOCK_DERIVATION
DURABLE_PREFIX_REPLAY
EXACT_REGISTERED_FIELD_DERIVATION
FILESYSTEM_STAT
GC_CALLBACK_ACCUMULATOR
GC_GET_COUNT
INGRESS_OWNER_SCALAR
LINUX_GETSOCKOPT
LINUX_IOCTL
LINUX_POLL
LINUX_SOCKET_IDENTITY
LOOP_MANIFEST_CONFIGURATION
LOOP_PROBE_ACCUMULATOR
LOOP_RUNTIME_CONFIGURATION
MANIFEST_IDENTITY_LINK
MARKER_ACCUMULATOR
NOT_ATTEMPTED
OPERATION_COUNTER_ACCUMULATOR
OWNER_THREAD_CPU_CLOCK
PARSER_OWNER_SCALAR
PROCESS_CPU_CLOCK
PROCFS_SMAPS_ROLLUP
PROCFS_STATM
PROCFS_STATUS
SQLITE_CONNECTION_CONFIGURATION
SQLITE_QUIESCENT_PRAGMA
SQLITE_TRANSACTION_ACCUMULATOR
TLS_OWNER_SCALAR
```

This is exactly **32** lexical tokens: 31 methods that may occur in a
descriptor method-role pair plus the `NOT_ATTEMPTED` sentinel. The previously
drafted but unreferenced `GOVERNED_CLOCK_DERIVATION` token is deliberately
removed by this pre-implementation clarification; durable and non-durable
field derivations already have the distinct exact methods named above. Adding
an unused or new token requires a new registry identity.

The role abbreviations used by the 185-row expansion are exact aliases:

```text
B = BEFORE_OPERATION
C = STABLE_CHECKPOINT
A = AFTER_OPERATION
G = OPERATION_AGGREGATE
R = STARTUP_RECOVERY
```

`ALL4` means the sorted exact operation tuple `ACK_DEADLINE_EXPIRY`, `INGRESS`,
`LOCAL_SHUTDOWN`, `SUBSCRIPTION_DISPATCH`. `ACK` and `SHUTDOWN` mean the
corresponding singleton. `CP_TARGET` means the exact checkpoint-marker set:

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

The set intentionally excludes every admission marker, `TARGET_EFFECT_ENTRY`,
and `SHUTDOWN_COMMAND_STARTED`; Section 7.3 forbids full adapters there. A `C`
value may be available only when the checkpoint's operation tag is also in the
descriptor operation set. A dash means no checkpoint marker can carry an
available value for that descriptor.

The exact unavailability profiles are:

```text
U_OWNER = {
  INSTRUMENTATION_DISABLED, TARGET_BOUNDARY_NOT_REACHED,
  UNSUPPORTED_BY_PYTHON_RUNTIME, OBSERVER_INTERNAL_ERROR,
  OBSERVATION_WOULD_MUTATE_TARGET,
  OBSERVATION_WOULD_REENTER_TARGET_LOCK,
  PROCESS_LOSS_VOLATILE_MARKER_STATE, SOURCE_DURABLE_RECORD_ABSENT,
  SOURCE_COUNTER_NOT_INSTRUMENTED, SOURCE_CLOCK_UNAVAILABLE,
  ARTIFACT_BOUND_EXCEEDED
}
U_OS = U_OWNER + {
  UNSUPPORTED_BY_KERNEL, PERMISSION_DENIED, OS_OBSERVATION_ERROR
}
U_SQLITE = U_OS + {
  OBSERVATION_WOULD_REENTER_ACTIVE_SQLITE_TRANSACTION
}
U_COUNTER = {
  INSTRUMENTATION_DISABLED, TARGET_BOUNDARY_NOT_REACHED,
  UNSUPPORTED_BY_PYTHON_RUNTIME, OBSERVER_INTERNAL_ERROR,
  PROCESS_LOSS_VOLATILE_MARKER_STATE, SOURCE_DURABLE_RECORD_ABSENT,
  SOURCE_COUNTER_NOT_INSTRUMENTED, SOURCE_CLOCK_UNAVAILABLE,
  ARTIFACT_BOUND_EXCEEDED
}
U_LOOP = U_COUNTER + {
  NO_STABLE_SLOW_CALLBACK_SOURCE, PERIODIC_PROBE_DID_NOT_FIRE,
  PROBE_RING_OVERWROTE_PREFIX
}
U_GC = U_COUNTER
U_MARKER = U_COUNTER + {MARKER_RING_OVERWROTE_PREFIX}
U_POLICY = {NO_FROZEN_PRESSURE_POLICY}
U_STATIC = {}
```

Every profile also permits `NOT_APPLICABLE_TO_OPERATION` exactly when its
operation set excludes the current tag, and
`NOT_APPLICABLE_TO_REACHED_STATE` when its available-role/state boundary was
not reached. Those are `NOT_APPLICABLE`, not `UNAVAILABLE`. No other reason is
admitted by that descriptor. `U_STATIC` fields are authority links: if their
manifest identity is absent or invalid, collection/replay fails instead of
emitting an unavailable target value.

The serialized `allowed_status_reasons` member is always the ascending UTF-8
tuple

```text
sorted(U_profile union {
  NOT_APPLICABLE_TO_OPERATION,
  NOT_APPLICABLE_TO_REACHED_STATE
})
```

including for `U_STATIC`. Presence in that tuple is necessary but not
sufficient: the two `NOT_APPLICABLE` reasons remain legal only when their
operation/reached-state predicates are true. Every descriptor serializes
`status_reason_policy_id=RAW_V8_STATUS_REASON_ATTEMPT_ERROR_POLICY_V1`, which
commits this exact additional truth table:

| Reason | Attempt policy | Error form |
|---|---|---|
| `INSTRUMENTATION_DISABLED` | `NOT_ATTEMPTED` only | none |
| `NOT_APPLICABLE_TO_OPERATION` | `NOT_ATTEMPTED` only | none |
| `NOT_APPLICABLE_TO_REACHED_STATE` | `NOT_ATTEMPTED` only | none |
| `TARGET_BOUNDARY_NOT_REACHED` | `NOT_ATTEMPTED` only | none |
| `NO_FROZEN_PRESSURE_POLICY` | `NOT_ATTEMPTED` only | none |
| `UNSUPPORTED_BY_KERNEL` | `ATTEMPTED` only | OS |
| `UNSUPPORTED_BY_PYTHON_RUNTIME` | `ATTEMPTED` or `NOT_ATTEMPTED` | non-OS exception when attempted; none otherwise |
| `PERMISSION_DENIED` | `ATTEMPTED` only | OS |
| `OS_OBSERVATION_ERROR` | `ATTEMPTED` only | OS |
| `OBSERVER_INTERNAL_ERROR` | `ATTEMPTED` only | non-OS exception |
| `OBSERVATION_WOULD_MUTATE_TARGET` | `NOT_ATTEMPTED` only | none |
| `OBSERVATION_WOULD_REENTER_TARGET_LOCK` | `NOT_ATTEMPTED` only | none |
| `OBSERVATION_WOULD_REENTER_ACTIVE_SQLITE_TRANSACTION` | `NOT_ATTEMPTED` only | none |
| `NO_STABLE_SLOW_CALLBACK_SOURCE` | `NOT_ATTEMPTED` only | none |
| `MARKER_RING_OVERWROTE_PREFIX` | `ATTEMPTED` only | status only |
| `PERIODIC_PROBE_DID_NOT_FIRE` | `ATTEMPTED` only | status only |
| `PROBE_RING_OVERWROTE_PREFIX` | `ATTEMPTED` only | status only |
| `PROCESS_LOSS_VOLATILE_MARKER_STATE` | `NOT_ATTEMPTED` only | none |
| `SOURCE_DURABLE_RECORD_ABSENT` | `NOT_ATTEMPTED` only | none |
| `SOURCE_COUNTER_NOT_INSTRUMENTED` | `NOT_ATTEMPTED` only | none |
| `SOURCE_CLOCK_UNAVAILABLE` | `ATTEMPTED` or `NOT_ATTEMPTED` | OS or non-OS exception when attempted; none otherwise |
| `ARTIFACT_BOUND_EXCEEDED` | `ATTEMPTED` only | status only |

An OS form requires the errno number/name pair; its safe exception class and
bounded metadata digest are both present or both absent. A non-OS exception
form requires both the safe class and metadata digest and forbids errno. A status-
only or none form forbids the errno/class/digest members. When the table permits
either attempt state, `ATTEMPTED` still requires a descriptor-registered
method and normally an available span; only the exact attempted
`SOURCE_CLOCK_UNAVAILABLE` rule permits its typed unavailable span.
`NOT_ATTEMPTED` requires the sentinel and no span. The
platform-context replay validator—not the pure structural constructor—checks
the errno symbolic name against the manifest-bound integer/name map.

`source_errno_number` is a positive safe integer and `source_errno_name`
matches `[A-Z][A-Z0-9_]{0,63}` before platform replay. A safe exception class
is 1..256 ASCII bytes matching
`[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*`. When that class is
present, `source_error_detail_sha256` is the Section 12.4 semantic identity
under `RiskYieldMMA2MSourceErrorDetailV4_9F_RawV8` of this exact payload:

```text
field_id
observation_method
source_failure_phase
source_errno_number | null
source_errno_name | null
source_error_class
```

Its complete canonical semantic preimage is bounded to 2 KiB. The digest is
recomputed from the observation and is never caller-authored exception text;
there are no additional metadata keys. If the class is null, the digest is
null. The errno pair and class values in this preimage must equal their field-
observation members. Observation offsets are safe unsigned integers and
completion is not earlier than start.

Failure phase is also exact when no detail digest is present. A first clock
read failure is `FIRST_CLOCK_READ`; the source is not invoked and the error
form remains `NONE`. A second clock read failure is `SECOND_CLOCK_READ`. An
exception raised by the registered source is `SOURCE_ADAPTER`; failure while
validating its returned exact type/value is `VALUE_VALIDATION`. Every
available, censored, not-applicable, status-only, disabled, unreached,
process-loss, or other not-attempted case uses `NONE`. An attempted
`OBSERVER_INTERNAL_ERROR` permits `SOURCE_ADAPTER` or `VALUE_VALIDATION`;
attempted OS/non-OS reasons other than clock failure permit only
`SOURCE_ADAPTER`. No caller chooses a different phase for the same path.

The descriptor-profile expansion is normative. In the method-role column,
`METHOD@B,C,A` is one exact method-role pair; semicolon separates pairs.

| Profile | Exact method-role pairs | Checkpoint markers | Operations | Reason profile | Censoring | Later action |
|---|---|---|---|---|---|---|
| `P_A1_POINT` | `A1_OWNER_SNAPSHOT@B,C,A` | `CP_TARGET` | `ALL4` | `U_OWNER` | no | `FAIL_CLOSED` |
| `P_A1_OUTCOME` | `A1_OUTCOME_CAPABILITY@C,A,G;DURABLE_PREFIX_REPLAY@R` | `CP_TARGET` | `ALL4` | `U_COUNTER` | no | `FAIL_CLOSED` |
| `P_A1_BOUND` | `A1_OUTCOME_CAPABILITY@C,A,G;DURABLE_PREFIX_REPLAY@R` | `CP_TARGET` | `ALL4` | `U_COUNTER` | yes | `FAIL_CLOSED` |
| `P_KERNEL_ID` | `LINUX_SOCKET_IDENTITY@B,C,A` | `CP_TARGET` | `ALL4` | `U_OS` | no | `FAIL_CLOSED` |
| `P_KERNEL_SOCKOPT` | `LINUX_GETSOCKOPT@B,C,A` | `CP_TARGET` | `ALL4` | `U_OS` | no | `FAIL_CLOSED` |
| `P_KERNEL_IOCTL` | `LINUX_IOCTL@B,C,A` | `CP_TARGET` | `ALL4` | `U_OS` | no | `FAIL_CLOSED` |
| `P_KERNEL_POLL` | `LINUX_POLL@B,C,A` | `CP_TARGET` | `ALL4` | `U_OS` | no | `FAIL_CLOSED` |
| `P_POINT_DERIVED` | `EXACT_REGISTERED_FIELD_DERIVATION@B,C,A` | `CP_TARGET` | `ALL4` | `U_OWNER` | no | `FAIL_CLOSED` |
| `P_OP_ACCUM` | `OPERATION_COUNTER_ACCUMULATOR@C,A,G` | `CP_TARGET` | `ALL4` | `U_COUNTER` | no | `FAIL_CLOSED` |
| `P_OP_DURABLE` | `DURABLE_PREFIX_REPLAY@C,A,G,R` | `CP_TARGET` | `ALL4` | `U_COUNTER` | no | `FAIL_CLOSED` |
| `P_TLS_POINT` | `TLS_OWNER_SCALAR@B,C,A` | `CP_TARGET` | `ALL4` | `U_OWNER` | no | `FAIL_CLOSED` |
| `P_INGRESS_POINT` | `INGRESS_OWNER_SCALAR@B,C,A;DURABLE_PREFIX_REPLAY@R` | `CP_TARGET` | `ALL4` | `U_OWNER` | no | `FAIL_CLOSED` |
| `P_PARSER_POINT` | `PARSER_OWNER_SCALAR@B,C,A;DURABLE_PREFIX_REPLAY@R` | `CP_TARGET` | `ALL4` | `U_OWNER` | no | `FAIL_CLOSED` |
| `P_ACTOR_POINT` | `ACTOR_OWNER_SNAPSHOT@B,C,A;DURABLE_PREFIX_REPLAY@R` | `CP_TARGET` | `ALL4` | `U_OWNER` | no | `FAIL_CLOSED` |
| `P_SQLITE_CONFIG` | `SQLITE_CONNECTION_CONFIGURATION@B,C,A,R` | `CP_TARGET` | `ALL4` | `U_SQLITE` | no | `FAIL_CLOSED` |
| `P_SQLITE_OP` | `SQLITE_TRANSACTION_ACCUMULATOR@C,A,G` | `CP_TARGET` | `ALL4` | `U_SQLITE` | no | `FAIL_CLOSED` |
| `P_SQLITE_FILE` | `FILESYSTEM_STAT@B,C,A,R` | `CP_TARGET` | `ALL4` | `U_SQLITE` | no | `FAIL_CLOSED` |
| `P_SQLITE_PRAGMA` | `SQLITE_QUIESCENT_PRAGMA@B,C,A,R` | `CP_TARGET` | `ALL4` | `U_SQLITE` | no | `FAIL_CLOSED` |
| `P_LOOP_STATIC` | `LOOP_MANIFEST_CONFIGURATION@B,C,A,G,R` | `CP_TARGET` | `ALL4` | `U_STATIC` | no | `FAIL_CLOSED` |
| `P_LOOP_OP` | `LOOP_PROBE_ACCUMULATOR@C,A,G` | `CP_TARGET` | `ALL4` | `U_LOOP` | no | `FAIL_CLOSED` |
| `P_LOOP_BOUND` | `LOOP_PROBE_ACCUMULATOR@C,A,G` | `CP_TARGET` | `ALL4` | `U_LOOP` | yes | `FAIL_CLOSED` |
| `P_LOOP_CONFIG` | `LOOP_RUNTIME_CONFIGURATION@B,C,A` | `CP_TARGET` | `ALL4` | `U_LOOP` | no | `FAIL_CLOSED` |
| `P_PROCESS_POINT` | exact row-selected `PROCFS_*` or `CGROUP_V2_MEMORY_CURRENT`, paired with `B,C,A,R` | `CP_TARGET` | `ALL4` | `U_OS` | no | `FAIL_CLOSED` |
| `P_PROCESS_CPU` | exact row-selected `PROCESS_CPU_CLOCK` or `OWNER_THREAD_CPU_CLOCK`, paired with `C,A,G` | `CP_TARGET` | `ALL4` | `U_COUNTER` | no | `FAIL_CLOSED` |
| `P_GC_BEFORE` | `GC_GET_COUNT@B` | - | `ALL4` | `U_GC` | no | `FAIL_CLOSED` |
| `P_GC_AFTER` | `GC_GET_COUNT@A` | - | `ALL4` | `U_GC` | no | `FAIL_CLOSED` |
| `P_GC_OP` | `GC_CALLBACK_ACCUMULATOR@C,A,G` | `CP_TARGET` | `ALL4` | `U_GC` | no | `FAIL_CLOSED` |
| `P_STATIC_LINK` | `MANIFEST_IDENTITY_LINK@B,C,A,G,R` | `CP_TARGET` | `ALL4` | `U_STATIC` | no | `FAIL_CLOSED` |
| `P_FRESH_STATE` | `DURABLE_GOVERNED_CLOCK_DERIVATION@B,C,A,R` | `CP_TARGET` | `ALL4` | `U_COUNTER` | no | `FAIL_CLOSED` |
| `P_POLICY_ABSENT` | none | - | `ALL4` | `U_POLICY` | no | `FAIL_CLOSED` |
| `P_FRESH_UNITS` | `DURABLE_PREFIX_REPLAY@C,A,G,R` | `CP_TARGET` | `ALL4` | `U_COUNTER` | no | `FAIL_CLOSED` |
| `P_FRESH_LATENCY` | `DURABLE_GOVERNED_CLOCK_DERIVATION@C,A,G,R` | `CP_TARGET` | `ALL4` | `U_COUNTER` | no | `FAIL_CLOSED` |
| `P_FRESH_ACK` | `A1_OUTCOME_CAPABILITY@C,A,G;DURABLE_PREFIX_REPLAY@R` | `CP_TARGET` | `ACK` | `U_COUNTER` | no | `FAIL_CLOSED` |
| `P_FRESH_SHUTDOWN` | `A1_OUTCOME_CAPABILITY@C,A,G;DURABLE_PREFIX_REPLAY@R` | `CP_TARGET` | `SHUTDOWN` | `U_COUNTER` | no | `FAIL_CLOSED` |
| `P_CANDIDATE_BOUND` | `DURABLE_GOVERNED_CLOCK_DERIVATION@A,G,R` | - | `ALL4` | `U_COUNTER` | yes | `FAIL_CLOSED` |
| `P_TARGET_BOUND` | `DURABLE_GOVERNED_CLOCK_DERIVATION@A,G,R` | - | `ALL4` | `U_COUNTER` | yes | `FAIL_CLOSED` |
| `P_MARKER_AGE` | `MARKER_ACCUMULATOR@A,G` | - | `ALL4` | `U_MARKER` | no | `FAIL_CLOSED` |

For `P_PROCESS_POINT` and `P_PROCESS_CPU`, the row expansion names the exact
method in parentheses; no implementation chooses among the alternatives at
runtime. The only legal parameterized spellings are the six spellings present
in Section 11.9: four process-point methods and two process-CPU methods. A
profile identifier not present in this table, or any other parenthesized
argument, is invalid. All method-role pairs, checkpoint tuples, operation
tuples, reason tuples, and enum tuples serialize in ascending UTF-8 order,
regardless of their presentation order above.

### 10.2 Observation containers

```text
CapacityMeasurementTargetObservationV49FV8
  observation_role:
      BEFORE_OPERATION | STABLE_CHECKPOINT | AFTER_OPERATION |
      OPERATION_AGGREGATE | STARTUP_RECOVERY
  operation_kind
  instrumentation_mode: OFF | ON
  candidate_id
  attempt_id | null
  target_field_registry_id
  observation_context_id
  marker_ordinal | null
  checkpoint_marker_kind | null
  observer_clock_span
  boottime_clock_span
  loop_clock_span
  field_observations   # exactly one for every registry field, exact order
  observation_id
```

Each clock span is the exact typed record:

```text
clock_domain: OBSERVER_MONOTONIC | BOOTTIME | EVENT_LOOP
span_status: AVAILABLE | UNAVAILABLE
started_offset_nanoseconds | null
completed_offset_nanoseconds | null
unavailable_reason: SOURCE_CLOCK_UNAVAILABLE |
                    PROCESS_LOSS_VOLATILE_MARKER_STATE | null
```

`AVAILABLE` requires two ordered safe unsigned offsets and null reason.
`UNAVAILABLE` requires null offsets and exactly one listed reason. The member's
clock-domain tag must match its container position. This permits truthful
OFF/source-failure/recovery records without inventing a zero span.

`observation_context_id` is the Section 12.4 semantic hash under
`RiskYieldMMA2MTargetObservationContextV4_9F_RawV8` of every container member
above except `field_observations`, `observation_id`, and the context ID itself.
Every nested field observation must carry that exact derived ID. This avoids a
hash cycle while making the field records context-bound. The observation root
and every nested context must agree on candidate, optional attempt, operation,
instrumentation mode, and registry; a mode-relabeled context rejects.

`field_observations` contains the complete standalone field-observation
envelopes—including canonicalization version, measurement schema, record
domain, complete payload, and `field_observation_id`—in exact registry order.
The target-observation constructor recomputes every nested ID and canonical
byte representation before deriving `observation_id`; an ID-only or stripped
payload substitution rejects.

The identity domains are exact:

```text
RiskYieldMMA2MTargetObservationV4_9F_RawV8
RiskYieldMMA2MTargetObservationRootV4_9F_RawV8
```

`observation_id` hashes the first domain, the V8 target-observation schema
version, and the complete canonical observation without `observation_id`. The
root hashes the second domain, `candidate_id`, `target_field_registry_id`,
exact observation count, and the ordered observation-ID tuple. Same-process order is `BEFORE_OPERATION`, then
selected checkpoints in increasing marker ordinal, then `AFTER_OPERATION`,
then `OPERATION_AGGREGATE`; recovery order contains its single
`STARTUP_RECOVERY` observation. Duplicate role/ordinal coordinates reject.
`closure_id` commits this root and its ordered IDs, and sample replay recomputes
both identities from the embedded byte-exact records before trusting any
availability count.

Available clock members are safe unsigned offsets from the candidate-bound
origins and are ordered within their own domains; values from different clock
domains are never subtracted. `STABLE_CHECKPOINT` requires a non-null marker
ordinal, one of the exact 13 full-checkpoint kinds, and an attempt. Every other
role requires null marker/checkpoint members. The operation tag is always
present and is checked against every descriptor's applicability and the
checkpoint's operation. This deliberately makes standalone semantic
validation possible instead of relying on an unrecorded caller context.

For that check, the Section 7.2 operation column is normative:
`ACK_DEADLINE_NOT_DUE` and `ACK_DEADLINE_TERMINAL_CONVERGED` are ACK-only;
`INGRESS_RETURN_READY`, `PARSER_UNIT_CONVERGED`, and
`RAW_PREFIX_COMMITTED` are ingress-only; `DISPATCH_RETURN_READY`,
`KERNEL_SEND_RESULT_CONVERGED`, and `OUTBOUND_ARTIFACTS_PREPARED` are
subscription-only; `LOCAL_CLOSE_DISPATCH_CONVERGED`,
`SHUTDOWN_TERMINAL_CONVERGED`, `TCP_HALF_CLOSE_CONVERGED`, and
`TLS_CONTROL_CONVERGED` are shutdown-only; and `TARGET_ESCAPE_OBSERVED` is
admitted for all four operations. Membership in the common 13-kind tuple alone
is insufficient.

Every field adapter offset is in the observer-monotonic domain and, when both
spans are available, lies inside the containing observation's observer span.
If that container span is unavailable, no field may claim an available adapter
span; an attempted field can then be only the exact
`SOURCE_CLOCK_UNAVAILABLE` unavailable case. This cross-record rule is checked
before the target-observation ID is accepted.

Clock-bracket failure is not collapsed into one ambiguous state. For a field
adapter, failure of the first observer-clock read means the source adapter is
not invoked: the field is `UNAVAILABLE/SOURCE_CLOCK_UNAVAILABLE`, uses
`observation_attempt=NOT_ATTEMPTED`, `observation_method=NOT_ATTEMPTED`,
`adapter_span_status=NOT_APPLICABLE`, and has two null offsets. If the source
adapter runs but the second read fails, its returned value is discarded: the
field uses `observation_attempt=ATTEMPTED`, its registered method,
`adapter_span_status=UNAVAILABLE`, two null offsets, and the same reason. A
complete bracket uses `adapter_span_status=AVAILABLE` with both ordered
offsets. The two failures use `FIRST_CLOCK_READ` and `SECOND_CLOCK_READ`,
respectively. A lone endpoint is deliberately not serialized because it proves
no complete duration. The same endpoint rule applies to each container clock
span: failure of either endpoint produces `UNAVAILABLE`, two null offsets, and
the exact clock reason. Same-process `OFF` still records these always-on
closure-construction spans; “no compact marker clocks” does not erase the
lifecycle closure's clock truth.

Before, after, and operation-aggregate containers are mandatory for every
same-process closed candidate, including a non-grant with no attempt. In `ON`
mode their fields follow the registry and reached-state rules. In `OFF` mode
the complete arrays remain structurally present; only facts already mandatory
in the V8 candidate/terminal or static manifest may remain available, and every
field requiring an ON observer is
`UNAVAILABLE/INSTRUMENTATION_DISABLED`. A bounded number of full stable
checkpoints is admitted by the signed selector. Startup recovery has exactly
one recovery observation: a volatile duration is censored only when a truthful
bound survives under its descriptor; other volatile fields are unavailable,
while durable-prefix-derived fields may remain available.

Consequently, a same-process sample contains exactly `3 + selected_checkpoint_count`
target observations, in the range 3..67 under Section 16; `OFF` contains
exactly three, and startup recovery contains exactly one. The closure count,
ID tuple, root, and four per-field availability-count tuples must agree with
that cardinality.

An operation aggregate is computed only from exact operation-local counters,
transaction-stage accumulators, GC/loop probes, retained markers/extrema, and durable
prefix replay. It cannot infer an unseen peak from before/after values.
An operation-local counter is an available zero only after an attempted target
operation directly observed zero occurrences. When no attempt exists, target-
operation counters are `NOT_APPLICABLE_TO_REACHED_STATE`, not fabricated zeros.

The pre-implementation audit found that the earlier sentence was not precise
enough for standalone validation: the compact coordinate tuple contains both
operation-local accumulators and point/current-state fields, and several
operation-local fields are outside that tuple. The exact context rule is now
frozen as follows. If `attempt_id` is null, every operation-applicable field in
this exact ascending UTF-8 tuple is
`NOT_APPLICABLE/NOT_APPLICABLE_TO_REACHED_STATE`, with
`observation_attempt=NOT_ATTEMPTED`, method `NOT_ATTEMPTED`, no adapter span,
null value, `censoring=NONE`, and no source-error metadata:

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

This tuple has exactly **85** fields: the 84 fields expanded from
`P_OP_ACCUM`, `P_OP_DURABLE`, `P_SQLITE_OP`, `P_LOOP_OP`, `P_LOOP_BOUND`,
both `P_PROCESS_CPU(...)` profiles, `P_GC_OP`, `P_FRESH_UNITS`, and
`P_FRESH_LATENCY`, plus the explicitly attempt-bounded
`freshness.target_effect_elapsed_boottime_ns`. It contains exactly 58 of the
66 compact coordinates. The other eight compact coordinates are point/current
state, not operation-local accumulators:

```text
actor.event_count
actor.pending_control_obligations
actor.pending_control_octets
actor.pending_wire_obligations
actor.pending_wire_octets
ingress.durable_buffer_octets
ingress.pending_raw_chunks
ingress.pending_raw_octets
```

Those eight and other point/static/A1 fields are not made unavailable merely
because the target attempt is absent; their ordinary operation, role, mode,
method, and reached-state rules still apply. Operation exclusion has precedence
over the attempt rule and remains `NOT_APPLICABLE_TO_OPERATION`.

The frozen `OFF` profile is likewise exact rather than caller-selected. After
operation applicability and the null-attempt rule above are applied,
`loop.probe_interval_ns`,
`process.filesystem_mount_cgroup_identity_id`, and
`process.runtime_environment_id` remain the three always-available signed
static copies; `freshness.analysis_pressure_episode_age_boottime_ns` retains
`UNAVAILABLE/NO_FROZEN_PRESSURE_POLICY`; every other applicable field is
`UNAVAILABLE/INSTRUMENTATION_DISABLED`. `ON` forbids
`INSTRUMENTATION_DISABLED`. `OFF` forbids `STABLE_CHECKPOINT` but permits the
single `STARTUP_RECOVERY` context required to recover an orphan from an OFF
campaign. This precedence makes OFF, ON, non-grant, and recovery records
deterministic and prevents a caller from relabelling a fully rehashed context.

An in-operation adapter runs only at a source-reviewed seam under the ownership
already held by the target task. It must not call the existing public quiescent
flow observer when that would reacquire the orchestration, owner-I/O, driver-
actor, or SQLite ownership already held by the operation. It may read stable
owner scalars directly through a private read-only capability and perform only
the predeclared sequential OS observations. If a field requires an await,
cross-thread access, lock re-entry, or state mutation at that seam, it is
`UNAVAILABLE/OBSERVATION_WOULD_REENTER_TARGET_LOCK` or
`UNAVAILABLE/OBSERVATION_WOULD_MUTATE_TARGET`; the adapter must not risk a
deadlock to avoid an unavailable value.

## 11. Frozen target registry

The following **185** field IDs are the complete V8 target surface: 35 A1, 16
kernel, 22 TLS, 11 ingress, 16 parser, 19 actor, 25 SQLite, 12 loop, 16 process,
and 13 freshness fields. The table is normative. Implementations may reuse one
adapter span for multiple fields, but may not omit a field from the observation
array. A generated test must derive these counts from the frozen descriptor
tuple; the prose count is not a second authority.

Each row now carries one exact descriptor profile and shape. To expand the
displayed `value / unit` cell, split once on the exact delimiter ` / `; reject
zero or multiple delimiters. For each half, uppercase ASCII and replace each
maximal non-empty run of ASCII space or hyphen with one underscore. Thus
`optional text / absolute ns` becomes `OPTIONAL_TEXT` and `ABSOLUTE_NS`, while
`fixed uint map / events` becomes `FIXED_UINT_MAP` and `EVENTS`. The normalized
left token must name one value-union kind in Section 10.1. The layer is the
uppercased field-ID prefix before the first dot. These transformations, the
profile expansion in Section 10.1.1, and the exact shape below supply every
descriptor member from Section 10.1. Tables are presentation-grouped; the
canonical descriptor tuple is the 185 expanded records sorted by UTF-8
`field_id`.

### 11.0 Exact registry identity envelope

The registry is one standalone semantic record with this exact payload order
(canonical JSON still sorts object keys):

```text
CapacityMeasurementTargetFieldRegistryV49FV8
  target_registry_profile = COMPLETE_TYPED_FIELD_AVAILABILITY_V1
  status_reason_policy_definition
  ordered_vocabulary_definitions
  ordered_value_shape_definitions
  ordered_value_constraint_definitions
  ordered_cross_field_constraint_definitions
  field_count = 185
  descriptors
  target_field_registry_id
```

The serialized semantic envelope uses exact keys
`canonicalization_version`, `measurement_schema_version`, `record_domain`, the
payload fields above, and `target_field_registry_id`. The ID is the Section
12.4 semantic hash under
`RiskYieldMMA2MTargetFieldRegistryV4_9F_RawV8` of the complete payload without
its ID. Vocabulary, shape, constraint, reason-policy, and cross-field
definition records are sorted by their exact ID; descriptors are sorted by
`field_id`. Every nested tuple is serialized as a JSON array. The registry
carries no display-profile alias and no unordered mapping.

The nested definition records have exact keys:

```text
VocabularyDefinition
  vocabulary_id
  members                         # unique ascending UTF-8 strings

ValueShapeDefinition
  value_shape_id
  container_kind                  # SCALAR | LIST | FIXED_MAP
  minimum_items | null
  maximum_items | null
  ordered_keys                    # empty except FIXED_MAP

ValueConstraintDefinition
  value_constraint_id
  value_kind
  scalar_profile                  # SAFE_IJSON_UINT | EXACT_BOOL | SHA256 |
                                  # UINT128_DECIMAL | PLATFORM_ERRNO |
                                  # ENUM | SAFE_IJSON_COLLECTION |
                                  # DURATION_BOUND
  vocabulary_id | null
  integer_minimum | null
  integer_maximum | null
  text_minimum_utf8_bytes | null
  text_maximum_utf8_bytes | null
  text_ascii_pattern | null
  decimal_maximum | null          # canonical decimal text when used
  collection_item_constraint_id | null
  external_authority_profile | null

StatusReasonPolicyDefinition
  status_reason_policy_id
  availability_state_rules
  reason_rules
  error_form_definitions

AvailabilityStateRule
  availability
  value_policy                     # REQUIRED | FORBIDDEN |
                                   # DURATION_BOUND_REQUIRED
  reason_policy                    # FORBIDDEN | NOT_APPLICABLE_REQUIRED |
                                   # UNAVAILABLE_REQUIRED
  censoring_policy                 # NONE_ONLY | DESCRIPTOR_BOUND_MAPPING
  attempt_policy                   # ATTEMPTED_ONLY | NOT_ATTEMPTED_ONLY |
                                   # REASON_RULE
  adapter_span_policy              # AVAILABLE_ONLY | NOT_APPLICABLE_ONLY |
                                   # REASON_RULE

StatusReasonRule
  reason
  required_availability            # NOT_APPLICABLE | UNAVAILABLE
  context_predicate | null         # OPERATION_EXCLUDED |
                                   # REACHED_STATE_EXCLUDED
  attempt_state_error_forms        # ordered records below

AttemptStateErrorForms
  attempt_state
  permitted_error_forms
  permitted_failure_phases
  adapter_span_policy              # AVAILABLE_ONLY | NOT_APPLICABLE_ONLY |
                                   # UNAVAILABLE_ONLY

ErrorFormDefinition
  error_form                       # NONE | STATUS_ONLY | OS | NON_OS
  errno_pair_policy                # FORBIDDEN | REQUIRED
  error_class_policy               # FORBIDDEN | OPTIONAL | REQUIRED
  error_digest_policy              # FORBIDDEN | OPTIONAL | REQUIRED
  class_digest_pair_policy         # BOTH_FORBIDDEN | BOTH_OR_NEITHER |
                                   # BOTH_REQUIRED

CrossFieldConstraintDefinition
  cross_field_constraint_id
  count_field_id
  sequence_field_id
  kind_field_id
  activation_condition             # ALL_MEMBERS_AVAILABLE
  maximum_items
  sequence_order                   # STRICTLY_INCREASING_UNIQUE
  cardinality_rule                 # COUNT_EQUALS_BOTH_ARRAY_LENGTHS
  pairing_rule                     # SAME_INDEX
```

The vocabulary tuple commits all reusable Step-2 lexical sets used directly by
observations and descriptors: operations, roles, all 19 markers, the 13 full-
checkpoint subset, methods, reasons, availability, attempt state, span status,
failure phase, clock domain, instrumentation mode, censoring, value kinds, duration
relations, later action, A1 command/outcome/rejection enums, SQLite primary
results, actor-map keys, SQLite stage-result keys, GC-generation keys, and
error forms. Closed policy-local tokens such as `REQUIRED`, `FORBIDDEN`, and
`BOTH_OR_NEITHER` are committed directly in their exact nested definition
records and are not redundantly declared as external vocabularies. The one
status-policy record reproduces both the four availability rules
in Section 10.1 and the exact 22-row table in Section 10.1.1; reason,
attempt-state, and form tuples are sorted. Availability-state rules sort by
`availability`; error-form definitions sort by `error_form`. Definition,
constraint, condition,
cardinality, ordering, and pairing IDs are the exact uppercase strings frozen
in this document, not hashes or free-form prose.

Thus the serialized availability-rule order is exactly
`AVAILABLE,CENSORED,NOT_APPLICABLE,UNAVAILABLE`, and the serialized error-form
definition order is exactly `NONE,NON_OS,OS,STATUS_ONLY`; display order never
overrides this array order.

The four serialized error-form definitions are exactly:

| `error_form` | `errno_pair_policy` | `error_class_policy` | `error_digest_policy` | `class_digest_pair_policy` |
|---|---|---|---|---|
| `NONE` | `FORBIDDEN` | `FORBIDDEN` | `FORBIDDEN` | `BOTH_FORBIDDEN` |
| `NON_OS` | `FORBIDDEN` | `REQUIRED` | `REQUIRED` | `BOTH_REQUIRED` |
| `OS` | `REQUIRED` | `OPTIONAL` | `OPTIONAL` | `BOTH_OR_NEITHER` |
| `STATUS_ONLY` | `FORBIDDEN` | `FORBIDDEN` | `FORBIDDEN` | `BOTH_FORBIDDEN` |

This pair policy is registry-committed. It rejects class-only and digest-only
OS records even though each member is individually optional in that form.

The exact vocabulary IDs are:

| `vocabulary_id` | Exact member authority |
|---|---|
| `RAW_V8_OPERATION_KIND` | four Section 6 operation tags |
| `RAW_V8_OBSERVATION_ROLE` | five Section 10.2 roles |
| `RAW_V8_MARKER_KIND` | all 19 Section 7.2 marker kinds |
| `RAW_V8_FULL_CHECKPOINT_MARKER_KIND` | exact 13-member `CP_TARGET` tuple |
| `RAW_V8_OBSERVATION_METHOD` | exact 32-token Section 10.1.1 vocabulary |
| `RAW_V8_STATUS_REASON` | exact 22-member reason enum |
| `RAW_V8_AVAILABILITY` | `AVAILABLE,CENSORED,NOT_APPLICABLE,UNAVAILABLE` |
| `RAW_V8_OBSERVATION_ATTEMPT` | `ATTEMPTED,NOT_ATTEMPTED` |
| `RAW_V8_SOURCE_FAILURE_PHASE` | `FIRST_CLOCK_READ,NONE,SECOND_CLOCK_READ,SOURCE_ADAPTER,VALUE_VALIDATION` |
| `RAW_V8_ADAPTER_SPAN_STATUS` | `AVAILABLE,NOT_APPLICABLE,UNAVAILABLE` |
| `RAW_V8_CLOCK_SPAN_STATUS` | `AVAILABLE,UNAVAILABLE` |
| `RAW_V8_CLOCK_DOMAIN` | `BOOTTIME,EVENT_LOOP,OBSERVER_MONOTONIC` |
| `RAW_V8_INSTRUMENTATION_MODE` | `OFF,ON` |
| `RAW_V8_CENSORING` | `INTERVAL,LEFT,NONE,RIGHT` |
| `RAW_V8_VALUE_KIND` | exact nine Section 10.1 kinds |
| `RAW_V8_DURATION_RELATION` | `EXACT,INTERVAL,LOWER_BOUND,UPPER_BOUND` |
| `RAW_V8_LATER_ACTION` | `FAIL_CLOSED` |
| `RAW_V8_A1_COMMAND_KIND` | exact `A1_COMMAND_KIND` members |
| `RAW_V8_A1_ADMISSION_OUTCOME` | exact `A1_ADMISSION_OUTCOME` members |
| `RAW_V8_A1_REJECTION_CLASS` | exact `A1_REJECTION_CLASS` members |
| `RAW_V8_SQLITE_PRIMARY_RESULT` | exact `SQLITE_PRIMARY_RESULT` members |
| `RAW_V8_ACTOR_KIND_MAP_KEY` | exact `M_ACTOR_KINDS_25` keys |
| `RAW_V8_SQLITE_STAGE_RESULT_MAP_KEY` | exact `M_SQLITE_STAGE_RESULTS_32` keys |
| `RAW_V8_GC_GENERATION_MAP_KEY` | exact `M_GC_GENERATIONS_3` keys |
| `RAW_V8_ERROR_FORM` | `NONE,NON_OS,OS,STATUS_ONLY` |

Every member array is unique and sorted by UTF-8 before serialization; the
comma-separated presentations above denote those exact arrays, not one string.
No implementation may choose its own vocabulary-ID spelling.

The four availability rows are exactly:

```text
AVAILABLE:
  REQUIRED, FORBIDDEN, NONE_ONLY, ATTEMPTED_ONLY, AVAILABLE_ONLY
NOT_APPLICABLE:
  FORBIDDEN, NOT_APPLICABLE_REQUIRED, NONE_ONLY,
  NOT_ATTEMPTED_ONLY, NOT_APPLICABLE_ONLY
UNAVAILABLE:
  FORBIDDEN, UNAVAILABLE_REQUIRED, NONE_ONLY, REASON_RULE, REASON_RULE
CENSORED:
  DURATION_BOUND_REQUIRED, FORBIDDEN, DESCRIPTOR_BOUND_MAPPING,
  ATTEMPTED_ONLY, AVAILABLE_ONLY
```

Each line after the state follows the exact member order
`value_policy, reason_policy, censoring_policy, attempt_policy,
adapter_span_policy`. The two N/A reason rows carry their exact context
predicate; every other reason row has null. In each reason's attempted-state
record, `adapter_span_policy=AVAILABLE_ONLY` except that attempted
`SOURCE_CLOCK_UNAVAILABLE` is `UNAVAILABLE_ONLY`; every not-attempted record is
`NOT_APPLICABLE_ONLY`. This serializes the first-read/second-read distinction
inside the registry identity rather than leaving it behind the policy ID. The
matching `permitted_failure_phases` tuple is exact: attempted
`SOURCE_CLOCK_UNAVAILABLE` has only `SECOND_CLOCK_READ`; not-attempted
`SOURCE_CLOCK_UNAVAILABLE` has only `FIRST_CLOCK_READ`; attempted
`OBSERVER_INTERNAL_ERROR` has `SOURCE_ADAPTER,VALUE_VALIDATION`; every other
attempted OS or non-OS row has only `SOURCE_ADAPTER`; and every status-only or
remaining not-attempted row has only `NONE`. Each tuple is serialized in
ascending UTF-8 order.
Error-form definitions are:

```text
NONE:        FORBIDDEN, FORBIDDEN, FORBIDDEN, BOTH_FORBIDDEN
STATUS_ONLY: FORBIDDEN, FORBIDDEN, FORBIDDEN, BOTH_FORBIDDEN
OS:          REQUIRED,  OPTIONAL,  OPTIONAL,  BOTH_OR_NEITHER
NON_OS:      FORBIDDEN, REQUIRED,  REQUIRED,  BOTH_REQUIRED
```

in member order `errno_pair_policy, error_class_policy,
error_digest_policy, class_digest_pair_policy`. Reason rows sort by `reason`;
attempt-state records and form tuples sort lexically. These literal records—
not a parser's hard-coded interpretation of a policy label—enter the registry
hash.

The constraint parameters are not inferred from profile labels. Safe unsigned
integer, optional-integer, list, map, and duration constraints serialize
`integer_minimum=0` and `integer_maximum=9007199254740991`. SHA-256 constraints
serialize byte length 64 and ASCII pattern `[0-9a-f]{64}`. The uint128-decimal
constraint serializes byte length 1..39, pattern `0|[1-9][0-9]*`, and
`decimal_maximum=340282366920938463463374607431768211455`. Platform errno
serializes byte length 1..64, pattern `[A-Z][A-Z0-9_]{0,63}`, and
`external_authority_profile=MANIFEST_BOUND_PLATFORM_ERRNO_MAP_AND_DURABLE_SEND_PREFIX_V1`.
Enum constraints name their exact vocabulary and use the registry-wide 1..256
UTF-8-byte ceiling. Collection constraints name their scalar item constraint.
All inapplicable parameter members are explicitly null. Consequently a bound,
pattern, external authority, or item-rule change changes the registry bytes,
not only the prose behind a stable label.

`UINT_LOOP_PROBE_INTERVAL_NS` instead serializes
`integer_minimum=1000000` and `integer_maximum=60000000000`, binding the
Section 16 design range directly to its sole field descriptor. Every
`text_ascii_pattern` is an ASCII-only whole-string/full-match grammar;
substring search and Unicode character-class interpretation are forbidden.

An implementation must publish one literal golden registry ID generated from
this envelope and independently reproduce it from the machine inventory. A
self-computed import-time value without an independent golden is insufficient
acceptance evidence.

Exact shapes are:

```text
shape_id                     container_kind  min   max   ordered_keys
S                            SCALAR          null  null  []
L_A1_FIFO_4                  LIST            0     4     []
L_GC_GENERATIONS_3           LIST            3     3     []
M_ACTOR_KINDS_25             FIXED_MAP       25    25    exact 25-key tuple below
M_SQLITE_STAGE_RESULTS_32    FIXED_MAP       32    32    exact 32-key tuple below
M_GC_GENERATIONS_3           FIXED_MAP       3     3     exact 3-key tuple below
```

The spaces above are presentation only; each row is the exact five-member
`ValueShapeDefinition` record. Fixed-map values include zero and serialize as
the ordered key/value array defined by their value union, never as an unordered
JSON object.

`UINT` members and every list/map integer are `0 .. 2^53-1`; an optional
unsigned value, when present, uses the same range. Hash text is exactly 64
lowercase hexadecimal characters. Absolute-nanosecond text is canonical uint128
decimal in `0 .. 2^128-1`. Other non-identity text is bounded by Section 16
and enum text must belong to its named source registry. Empty lists/maps are
not aliases for unavailable observations.

Every expanded descriptor carries one of these exact `value_constraint_id`
values. The assignment is mechanical and identity-bearing:

```text
UINT_SAFE_IJSON                 all UINT fields except loop.probe_interval_ns
UINT_LOOP_PROBE_INTERVAL_NS     loop.probe_interval_ns
OPTIONAL_UINT_SAFE_IJSON        all OPTIONAL_UINT fields
BOOL_EXACT                      all BOOL fields
TEXT_SHA256                     TEXT with unit IDENTITY or HASH
OPTIONAL_TEXT_SHA256            OPTIONAL_TEXT with unit IDENTITY or HASH
OPTIONAL_TEXT_UINT128_DECIMAL   OPTIONAL_TEXT with unit ABSOLUTE_NS
OPTIONAL_TEXT_PLATFORM_ERRNO    OPTIONAL_TEXT with unit ERRNO
UINT_LIST_SAFE_IJSON            all UINT_LIST fields
FIXED_UINT_MAP_SAFE_IJSON       all FIXED_UINT_MAP fields
DURATION_BOUND_SAFE_IJSON       all DURATION_BOUND fields
TEXT_ENUM_A1_COMMAND_KIND       a1.target_command_kind
OPTIONAL_TEXT_ENUM_A1_COMMAND_KIND
                                 a1.active_kind
TEXT_LIST_ENUM_A1_COMMAND_KIND  a1.waiting_kinds
TEXT_ENUM_A1_ADMISSION_OUTCOME  a1.target_admission_outcome
OPTIONAL_TEXT_ENUM_A1_REJECTION_CLASS
                                 a1.target_rejection_class
TEXT_ENUM_SQLITE_PRIMARY_RESULT sqlite.last_primary_result_class
```

The resulting 17 definition records have these exact non-null assignments;
every definition member not named in its row is null:

| `value_constraint_id` | `value_kind` | `scalar_profile` | Additional non-null members |
|---|---|---|---|
| `UINT_SAFE_IJSON` | `UINT` | `SAFE_IJSON_UINT` | `integer_minimum=0`; `integer_maximum=9007199254740991` |
| `UINT_LOOP_PROBE_INTERVAL_NS` | `UINT` | `SAFE_IJSON_UINT` | `integer_minimum=1000000`; `integer_maximum=60000000000` |
| `OPTIONAL_UINT_SAFE_IJSON` | `OPTIONAL_UINT` | `SAFE_IJSON_UINT` | `integer_minimum=0`; `integer_maximum=9007199254740991` |
| `BOOL_EXACT` | `BOOL` | `EXACT_BOOL` | none |
| `TEXT_SHA256` | `TEXT` | `SHA256` | `text_minimum_utf8_bytes=64`; `text_maximum_utf8_bytes=64`; `text_ascii_pattern=[0-9a-f]{64}` |
| `OPTIONAL_TEXT_SHA256` | `OPTIONAL_TEXT` | `SHA256` | same exact 64-byte SHA-256 text members |
| `OPTIONAL_TEXT_UINT128_DECIMAL` | `OPTIONAL_TEXT` | `UINT128_DECIMAL` | `text_minimum_utf8_bytes=1`; `text_maximum_utf8_bytes=39`; `text_ascii_pattern=0\|[1-9][0-9]*`; `decimal_maximum=340282366920938463463374607431768211455` |
| `OPTIONAL_TEXT_PLATFORM_ERRNO` | `OPTIONAL_TEXT` | `PLATFORM_ERRNO` | `text_minimum_utf8_bytes=1`; `text_maximum_utf8_bytes=64`; `text_ascii_pattern=[A-Z][A-Z0-9_]{0,63}`; `external_authority_profile=MANIFEST_BOUND_PLATFORM_ERRNO_MAP_AND_DURABLE_SEND_PREFIX_V1` |
| `UINT_LIST_SAFE_IJSON` | `UINT_LIST` | `SAFE_IJSON_COLLECTION` | `integer_minimum=0`; `integer_maximum=9007199254740991`; `collection_item_constraint_id=UINT_SAFE_IJSON` |
| `FIXED_UINT_MAP_SAFE_IJSON` | `FIXED_UINT_MAP` | `SAFE_IJSON_COLLECTION` | `integer_minimum=0`; `integer_maximum=9007199254740991`; `collection_item_constraint_id=UINT_SAFE_IJSON` |
| `DURATION_BOUND_SAFE_IJSON` | `DURATION_BOUND` | `DURATION_BOUND` | `integer_minimum=0`; `integer_maximum=9007199254740991` |
| `TEXT_ENUM_A1_COMMAND_KIND` | `TEXT` | `ENUM` | `vocabulary_id=RAW_V8_A1_COMMAND_KIND`; text byte bounds `1..256` |
| `OPTIONAL_TEXT_ENUM_A1_COMMAND_KIND` | `OPTIONAL_TEXT` | `ENUM` | `vocabulary_id=RAW_V8_A1_COMMAND_KIND`; text byte bounds `1..256` |
| `TEXT_LIST_ENUM_A1_COMMAND_KIND` | `TEXT_LIST` | `SAFE_IJSON_COLLECTION` | `vocabulary_id=RAW_V8_A1_COMMAND_KIND`; text byte bounds `1..256`; `collection_item_constraint_id=TEXT_ENUM_A1_COMMAND_KIND` |
| `TEXT_ENUM_A1_ADMISSION_OUTCOME` | `TEXT` | `ENUM` | `vocabulary_id=RAW_V8_A1_ADMISSION_OUTCOME`; text byte bounds `1..256` |
| `OPTIONAL_TEXT_ENUM_A1_REJECTION_CLASS` | `OPTIONAL_TEXT` | `ENUM` | `vocabulary_id=RAW_V8_A1_REJECTION_CLASS`; text byte bounds `1..256` |
| `TEXT_ENUM_SQLITE_PRIMARY_RESULT` | `TEXT` | `ENUM` | `vocabulary_id=RAW_V8_SQLITE_PRIMARY_RESULT`; text byte bounds `1..256` |

“Text byte bounds `1..256`” means
`text_minimum_utf8_bytes=1` and `text_maximum_utf8_bytes=256`; it does not add
an unlisted pattern. The text-list row commits both the vocabulary and the
scalar item constraint so a generic free-form text list cannot substitute.

No other kind/unit combination is present. The four named enum vocabularies
below and the platform errno mapping are therefore part of registry replay,
not comments adjacent to a generic text field.

`value_shape_keys` is empty for `S`, `L_A1_FIFO_4`, and
`L_GC_GENERATIONS_3`; it is the exact 25-, 32-, or 3-key tuple for the three
fixed-map shapes. `cross_field_constraint_ids` is empty except that
`a1.waiting_count`, `a1.waiting_sequences`, and `a1.waiting_kinds` all carry
`A1_FIFO_SEQUENCE_KIND_LENGTH_AND_ORDER_V1`. That constraint requires both
arrays to have equal length, to agree with `a1.waiting_count` when all three
fields are available in one observation, to contain at most four positions,
to contain strictly increasing unique admission sequences, and to pair each
sequence with the command kind at the same FIFO position. The definition's
named field members are exactly `a1.waiting_count`, `a1.waiting_sequences`, and
`a1.waiting_kinds`. Definition/reference
closure is bidirectional: every descriptor reference resolves and every
definition is referenced. The registry envelope separately commits the complete
ordered shape- and vocabulary-definition records, so changing a bound,
map key, enum member, assignment, or paired-list rule changes the registry ID.

For this registry, `IDENTITY` and `HASH` text values are exactly 64 lowercase
hexadecimal characters. An available field value with unit `ERRNO` is the
target operation's durable last-send symbolic errno. It is checked against the
manifest-bound platform map and durable send-failure prefix, and it forbids the
observation source-error tuple just like every AVAILABLE value. This is
distinct from `source_errno_number/source_errno_name`, which describes why an
UNAVAILABLE attempted adapter failed and is governed by the Section 10.1.1 OS
error form. The field-ID-specific enum constraints are:

```text
A1_COMMAND_KIND =
  ACK_DEADLINE_EXPIRY | INGRESS | LOCAL_SHUTDOWN | SUBSCRIPTION_DISPATCH
  fields: a1.active_kind, a1.waiting_kinds, a1.target_command_kind

A1_ADMISSION_OUTCOME =
  CANCELLED_BEFORE_ENTRY | CLOSED_BEFORE_ENTRY | FAILED_BEFORE_ENTRY |
  GRANTED | INTERRUPTED_BEFORE_ENTRY | REJECTED | TIMED_OUT |
  UNRESOLVED_PROCESS_LOSS
  field: a1.target_admission_outcome

A1_REJECTION_CLASS =
  CANCELLED_BEFORE_ENTRY | CAPACITY_REJECTED | CLOSED_BEFORE_ENTRY |
  DUPLICATE_KIND_REJECTED | FAILED_BEFORE_ENTRY |
  INTERRUPTED_BEFORE_ENTRY | TERMINAL_BARRIER_REJECTED | TIMED_OUT
  field: a1.target_rejection_class

SQLITE_PRIMARY_RESULT =
  BEGIN.BUSY | BEGIN.FULL | BEGIN.INTERRUPT | BEGIN.IOERR | BEGIN.LOCKED |
  BEGIN.NOMEM | BEGIN.OK | BEGIN.OTHER |
  BODY.BUSY | BODY.FULL | BODY.INTERRUPT | BODY.IOERR | BODY.LOCKED |
  BODY.NOMEM | BODY.OK | BODY.OTHER |
  COMMIT.BUSY | COMMIT.FULL | COMMIT.INTERRUPT | COMMIT.IOERR |
  COMMIT.LOCKED | COMMIT.NOMEM | COMMIT.OK | COMMIT.OTHER | NONE
  field: sqlite.last_primary_result_class
```

The A1 rejection field is available optional-none for `GRANTED`, uses the exact
class compatible with every same-process non-grant outcome, and is unavailable
for `UNRESOLVED_PROCESS_LOSS`. `SQLITE_PRIMARY_RESULT` intentionally excludes
rollback: "primary" means the latest attempted `BEGIN|BODY|COMMIT` stage. A
different enum member or field-to-enum assignment changes the registry.

`M_ACTOR_KINDS_25` is the sorted exact tuple:

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

`M_SQLITE_STAGE_RESULTS_32` is the lexical cross-product of stages
`BEGIN,BODY,COMMIT,ROLLBACK` and classes
`BUSY,FULL,INTERRUPT,IOERR,LOCKED,NOMEM,OK,OTHER`, serialized as
`STAGE.CLASS`. One `BODY.OK` is counted only when every target statement in
that transaction body completed; otherwise the first body failure contributes
its exact class. A stage not attempted contributes no result. This preserves
where `COMMIT.BUSY` occurred instead of collapsing it into an operation-wide
BUSY count. `sqlite.last_primary_result_class` stores the exact latest
`STAGE.CLASS`, or `NONE` when no stage was attempted.

`M_GC_GENERATIONS_3` has exact keys `GENERATION_0`, `GENERATION_1`, and
`GENERATION_2`. A different actor enum, SQLite stage/class set, Python GC
generation profile, value shape, method, role, marker set, applicability,
censoring flag, reason set, or fail-closed action creates a different registry
and Raw schema; it cannot be accepted by relabelling V8.

### 11.1 A1 admission

| Field ID | Value / unit | Descriptor profile | Shape | Required source and meaning |
|---|---|---|---|---|
| `a1.policy_id` | text / identity | `P_A1_POINT` | `S` | Exact signed A1 policy |
| `a1.epoch` | uint / epoch | `P_A1_POINT` | `S` | Snapshot epoch |
| `a1.closed` | bool / state | `P_A1_POINT` | `S` | Gate closed state |
| `a1.terminal_barrier_sequence` | optional uint / admission | `P_A1_POINT` | `S` | Exact optional barrier sequence; optional representation prevents null/unavailable ambiguity |
| `a1.terminal_barrier_committed` | bool / state | `P_A1_POINT` | `S` | Durable barrier state |
| `a1.active_count` | uint / commands | `P_A1_POINT` | `S` | Exact current count |
| `a1.active_sequence` | optional uint / admission | `P_A1_POINT` | `S` | Exact optional active admission |
| `a1.active_kind` | optional text / enum | `P_A1_POINT` | `S` | Exact optional active kind |
| `a1.waiting_count` | uint / commands | `P_A1_POINT` | `S` | Exact waiting count |
| `a1.waiting_sequences` | uint-list / admissions | `P_A1_POINT` | `L_A1_FIFO_4` | FIFO order |
| `a1.waiting_kinds` | text-list / enums | `P_A1_POINT` | `L_A1_FIFO_4` | Same cardinality/order as sequences |
| `a1.oldest_waiting_age_ns` | uint / ns | `P_A1_POINT` | `S` | Age in the loop-clock domain at snapshot |
| `a1.reserved_work_units` | uint / abstract work | `P_A1_POINT` | `S` | Current reservation, not empirical cost |
| `a1.maximum_observed_admitted_commands` | uint / commands | `P_A1_POINT` | `S` | A1 historical counter |
| `a1.maximum_observed_reserved_work_units` | uint / abstract work | `P_A1_POINT` | `S` | A1 historical counter |
| `a1.last_started_queue_wait_ns` | optional uint / ns | `P_A1_POINT` | `S` | Exact prior-start wait or observed no prior start |
| `a1.maximum_observed_queue_wait_ns` | uint / ns | `P_A1_POINT` | `S` | A1 historical maximum |
| `a1.released_commands` | uint / commands | `P_A1_POINT` | `S` | Cumulative exact counter |
| `a1.rejected_commands` | uint / commands | `P_A1_POINT` | `S` | Cumulative exact counter |
| `a1.duplicate_kind_rejections` | uint / commands | `P_A1_POINT` | `S` | Exact rejection class counter |
| `a1.terminal_barrier_rejections` | uint / commands | `P_A1_POINT` | `S` | Exact rejection class counter |
| `a1.capacity_rejections` | uint / commands | `P_A1_POINT` | `S` | Exact counter; no assumption it is reachable |
| `a1.closed_rejections` | uint / commands | `P_A1_POINT` | `S` | Exact rejection class counter |
| `a1.timed_out_commands` | uint / commands | `P_A1_POINT` | `S` | Exact pre-entry timeout counter |
| `a1.cancelled_before_entry_commands` | uint / commands | `P_A1_POINT` | `S` | Exact cancellation counter |
| `a1.closed_before_entry_commands` | uint / commands | `P_A1_POINT` | `S` | Exact closed-before-entry counter |
| `a1.target_admission_outcome` | text / enum | `P_A1_OUTCOME` | `S` | Exact candidate outcome, including unresolved process-loss classification |
| `a1.target_admission_sequence` | optional uint / admission | `P_A1_OUTCOME` | `S` | Exact ticket sequence when accepted; available optional-none only for a proven immediate rejection, and unavailable after unresolved process loss |
| `a1.target_command_kind` | text / enum | `P_A1_OUTCOME` | `S` | Must equal operation-union tag |
| `a1.target_reservation_work_units` | uint / abstract work | `P_A1_OUTCOME` | `S` | Exact signed reservation |
| `a1.target_admitted_loop_time_ns` | optional text / absolute ns | `P_A1_OUTCOME` | `S` | Canonical uint128 decimal when A1 accepted a ticket |
| `a1.target_started_loop_time_ns` | optional text / absolute ns | `P_A1_OUTCOME` | `S` | Canonical uint128 decimal only for `GRANTED` |
| `a1.target_start_deadline_loop_time_ns` | optional text / absolute ns | `P_A1_OUTCOME` | `S` | Canonical uint128 decimal when A1 accepted a ticket |
| `a1.target_queue_wait_ns` | duration bound / ns | `P_A1_BOUND` | `S` | Exact admitted-to-start/outcome wait, a declared censored bound, or not applicable for an immediate rejection |
| `a1.target_rejection_class` | optional text / enum | `P_A1_OUTCOME` | `S` | Exact bounded class for rejection/failure; observed none for other same-process outcomes, and unavailable when process loss erased it |

The target outcome comes from the private runtime-owned A1 observer capability,
not from before/after inference. A sequence and admitted/deadline clocks exist
only after A1 accepts a ticket; a started clock exists only for `GRANTED`.
Waiting arrays and ages come from the exact A1 snapshot. An empty observed FIFO
is available evidence with empty arrays and zero count, not unavailability.

### 11.2 Linux kernel socket

| Field ID | Value / unit | Descriptor profile | Shape | Required source and limitation |
|---|---|---|---|---|
| `kernel.socket_identity` | text / hash | `P_KERNEL_ID` | `S` | Runtime-owned socket identity |
| `kernel.so_rcvbuf_literal_octets` | uint / bytes | `P_KERNEL_SOCKOPT` | `S` | Literal `getsockopt(SO_RCVBUF)` result |
| `kernel.so_sndbuf_literal_octets` | uint / bytes | `P_KERNEL_SOCKOPT` | `S` | Literal `getsockopt(SO_SNDBUF)` result |
| `kernel.siocinq_unread_octets` | uint / bytes | `P_KERNEL_IOCTL` | `S` | Point `SIOCINQ` observation |
| `kernel.siocoutq_unsent_octets` | uint / bytes | `P_KERNEL_IOCTL` | `S` | Point `SIOCOUTQ` observation |
| `kernel.read_poll_mask` | uint / bit mask | `P_KERNEL_POLL` | `S` | Exact zero-timeout poll mask |
| `kernel.write_poll_mask` | uint / bit mask | `P_KERNEL_POLL` | `S` | Exact zero-timeout poll mask |
| `kernel.read_ready` | bool / state | `P_POINT_DERIVED` | `S` | Derived only from recorded `POLLIN` mask bit |
| `kernel.write_ready` | bool / state | `P_POINT_DERIVED` | `S` | Derived only from recorded `POLLOUT` mask bit |
| `kernel.operation_recv_calls` | uint / calls | `P_OP_ACCUM` | `S` | Operation-local owner counter |
| `kernel.operation_recv_ciphertext_octets` | uint / bytes | `P_OP_ACCUM` | `S` | Exact positive recv results |
| `kernel.operation_send_attempts` | uint / attempts | `P_OP_DURABLE` | `S` | Durable attempt count in prefix |
| `kernel.operation_send_positive_results` | uint / results | `P_OP_DURABLE` | `S` | Durable positive result count |
| `kernel.operation_send_accepted_octets` | uint / bytes | `P_OP_DURABLE` | `S` | Sum of exact local kernel acceptance |
| `kernel.operation_send_failures` | uint / failures | `P_OP_DURABLE` | `S` | Durable failure count |
| `kernel.operation_last_send_errno` | optional text / errno | `P_OP_DURABLE` | `S` | Exact durable error where present |

Linux documents that `SIOCINQ` is queued unread data and `SIOCOUTQ` is unsent
data. It also documents that `getsockopt()` returns Linux's doubled SO_RCVBUF
and SO_SNDBUF values. V8 retains those literal meanings and never derives
available headroom or peer receipt
([Linux `tcp(7)`](https://man7.org/linux/man-pages/man7/tcp.7.html),
[Linux `socket(7)`](https://man7.org/linux/man-pages/man7/socket.7.html)).
`POLLIN` and `POLLOUT` are readiness states at the poll point; they are not a
future nonblocking guarantee or capacity watermark
([Python 3.12 `select`](https://docs.python.org/3.12/library/select.html)).

### 11.3 TLS and driver flow

| Field ID | Value / unit | Descriptor profile | Shape | Required source and meaning |
|---|---|---|---|---|
| `tls.incoming_memory_bio_pending_octets` | uint / bytes | `P_TLS_POINT` | `S` | Direct `MemoryBIO.pending` |
| `tls.outgoing_memory_bio_pending_octets` | uint / bytes | `P_TLS_POINT` | `S` | Direct `MemoryBIO.pending` |
| `tls.ssl_plaintext_pending_octets` | uint / bytes | `P_TLS_POINT` | `S` | Direct SSL-object pending plaintext |
| `tls.operation_read_calls` | uint / calls | `P_OP_ACCUM` | `S` | Operation-local driver counter |
| `tls.operation_ciphertext_fed_octets` | uint / bytes | `P_OP_ACCUM` | `S` | Exact bytes written to incoming BIO |
| `tls.operation_plaintext_produced_octets` | uint / bytes | `P_OP_ACCUM` | `S` | Exact plaintext returned from TLS |
| `tls.operation_write_calls` | uint / calls | `P_OP_ACCUM` | `S` | Operation-local SSL write calls |
| `tls.operation_plaintext_accepted_octets` | uint / bytes | `P_OP_ACCUM` | `S` | Exact plaintext accepted by SSL write |
| `tls.operation_ciphertext_produced_octets` | uint / bytes | `P_OP_ACCUM` | `S` | Exact outgoing BIO bytes staged |
| `tls.operation_want_read_count` | uint / exceptions | `P_OP_ACCUM` | `S` | Exact caught WANT_READ count |
| `tls.operation_want_write_count` | uint / exceptions | `P_OP_ACCUM` | `S` | Exact caught WANT_WRITE count |
| `tls.protocol_output_chunks` | uint / chunks | `P_TLS_POINT` | `S` | Current driver queue count |
| `tls.protocol_output_octets` | uint / bytes | `P_TLS_POINT` | `S` | Current driver queue bytes |
| `tls.staged_websocket_wire_chunks` | uint / chunks | `P_TLS_POINT` | `S` | Current staged wire count |
| `tls.staged_websocket_wire_octets` | uint / bytes | `P_TLS_POINT` | `S` | Current staged wire bytes |
| `tls.pending_ciphertext_octets` | uint / bytes | `P_TLS_POINT` | `S` | Current pending batch total |
| `tls.remaining_pending_ciphertext_octets` | uint / bytes | `P_TLS_POINT` | `S` | Current unsent suffix |
| `tls.staged_ciphertext_octets` | uint / bytes | `P_TLS_POINT` | `S` | Current application batch total |
| `tls.remaining_staged_ciphertext_octets` | uint / bytes | `P_TLS_POINT` | `S` | Current application unsent suffix |
| `tls.staged_control_ciphertext_octets` | uint / bytes | `P_TLS_POINT` | `S` | Current control batch total |
| `tls.remaining_staged_control_ciphertext_octets` | uint / bytes | `P_TLS_POINT` | `S` | Current control unsent suffix |
| `tls.pending_send_eof` | bool / state | `P_TLS_POINT` | `S` | Existing driver EOF state |

Python exposes `MemoryBIO.pending` as the number of bytes currently in the
memory buffer. It is a local buffer observation, not network delivery
([Python 3.12 `ssl.MemoryBIO`](https://docs.python.org/3.12/library/ssl.html#ssl.MemoryBIO)).

### 11.4 Durable ingress and freshness ownership

| Field ID | Value / unit | Descriptor profile | Shape | Required source and meaning |
|---|---|---|---|---|
| `ingress.pending_raw_chunks` | uint / chunks | `P_INGRESS_POINT` | `S` | Current retained RAW batch count |
| `ingress.pending_raw_octets` | uint / bytes | `P_INGRESS_POINT` | `S` | Current retained RAW bytes |
| `ingress.durable_buffer_octets` | uint / bytes | `P_INGRESS_POINT` | `S` | Parser-owned durable bytes |
| `ingress.has_complete_durable_unit` | bool / state | `P_INGRESS_POINT` | `S` | Existing exact parser-ready test |
| `ingress.retained_incomplete_tail_octets` | uint / bytes | `P_INGRESS_POINT` | `S` | Cursor-to-RAW-end tail only |
| `ingress.oldest_unparsed_raw_age_boottime_ns` | uint / ns | `P_INGRESS_POINT` | `S` | BOOTTIME age of first still-unparsed durable byte |
| `ingress.oldest_unparsed_raw_commit_id` | optional text / hash | `P_INGRESS_POINT` | `S` | Exact dependency or observed none |
| `ingress.latest_raw_sequence` | optional uint / RAW sequence | `P_INGRESS_POINT` | `S` | Exact current sequence or observed none |
| `ingress.latest_raw_commit_id` | optional text / hash | `P_INGRESS_POINT` | `S` | Exact current RAW identity or observed none |
| `ingress.operation_new_raw_count` | uint / RAW records | `P_OP_DURABLE` | `S` | Prefix-derived operation delta |
| `ingress.operation_new_raw_octets` | uint / bytes | `P_OP_DURABLE` | `S` | Prefix-derived operation delta |

Oldest age uses the original durable RAW receipt's governed BOOTTIME evidence;
it is not reset by a parser continuation or service turn. If the old record
does not contain a compatible clock, the field is unavailable rather than
estimated from wall time.

### 11.5 Parser and application work

| Field ID | Value / unit | Descriptor profile | Shape | Required source and meaning |
|---|---|---|---|---|
| `parser.operation_units` | uint / units | `P_OP_DURABLE` | `S` | Complete frame or parser-error units reached |
| `parser.operation_complete_frames` | uint / frames | `P_OP_DURABLE` | `S` | Prefix-derived exact count |
| `parser.operation_error_units` | uint / errors | `P_OP_DURABLE` | `S` | Prefix-derived exact count |
| `parser.operation_source_octets` | uint / bytes | `P_OP_DURABLE` | `S` | Exact consumed source slices |
| `parser.operation_payload_octets` | uint / bytes | `P_OP_DURABLE` | `S` | Exact payload bytes |
| `parser.operation_fragment_units` | uint / fragments | `P_OP_DURABLE` | `S` | Exact fragment transitions |
| `parser.current_fragment_payload_octets` | uint / bytes | `P_PARSER_POINT` | `S` | Current retained fragment size |
| `parser.operation_application_completions` | uint / messages | `P_OP_DURABLE` | `S` | Durable application commits |
| `parser.operation_automatic_output_chunks` | uint / chunks | `P_OP_DURABLE` | `S` | Exact generated wire chunks |
| `parser.operation_automatic_output_octets` | uint / bytes | `P_OP_DURABLE` | `S` | Exact generated wire bytes |
| `parser.last_unit_elapsed_ns` | uint / ns | `P_OP_ACCUM` | `S` | Observer-monotonic bracket for last unit |
| `parser.total_unit_elapsed_ns` | uint / ns | `P_OP_ACCUM` | `S` | Sum of individually bracketed units |
| `parser.maximum_unit_elapsed_ns` | uint / ns | `P_OP_ACCUM` | `S` | Exact maximum and marker ordinal in extrema |
| `parser.last_unit_thread_cpu_ns` | uint / ns | `P_OP_ACCUM` | `S` | Owner-thread CPU for last unit |
| `parser.total_unit_thread_cpu_ns` | uint / ns | `P_OP_ACCUM` | `S` | Sum of unit CPU deltas |
| `parser.maximum_unit_thread_cpu_ns` | uint / ns | `P_OP_ACCUM` | `S` | Exact maximum and marker ordinal in extrema |

The per-unit end cutoff is after any application commit and generated
automatic output has durably converged. Parser elapsed therefore includes the
unit's required causal consequences. Separate actor/SQLite/TLS fields allow
decomposition; no subtraction of overlapping spans is treated as an exact
exclusive CPU attribution.

### 11.6 Actor

| Field ID | Value / unit | Descriptor profile | Shape | Required source and meaning |
|---|---|---|---|---|
| `actor.event_count` | uint / events | `P_ACTOR_POINT` | `S` | Current retained count |
| `actor.tail_event_id` | optional text / hash | `P_ACTOR_POINT` | `S` | Current tail or observed empty chain |
| `actor.event_kind_counts` | fixed uint map / events | `P_ACTOR_POINT` | `M_ACTOR_KINDS_25` | Every frozen actor-event enum member, including zeros |
| `actor.operation_single_append_calls` | uint / calls | `P_OP_ACCUM` | `S` | Exact single-event append calls |
| `actor.operation_batch_append_calls` | uint / calls | `P_OP_ACCUM` | `S` | Exact batch append calls |
| `actor.operation_appended_events` | uint / events | `P_OP_DURABLE` | `S` | Events committed by those calls |
| `actor.single_append_total_elapsed_ns` | uint / ns | `P_OP_ACCUM` | `S` | Inclusive single-event append spans |
| `actor.single_append_maximum_elapsed_ns` | uint / ns | `P_OP_ACCUM` | `S` | Exact single-event maximum plus first ordinal |
| `actor.batch_append_total_elapsed_ns` | uint / ns | `P_OP_ACCUM` | `S` | Inclusive batch append spans |
| `actor.batch_append_maximum_elapsed_ns` | uint / ns | `P_OP_ACCUM` | `S` | Exact batch maximum plus first ordinal |
| `actor.validation_total_elapsed_ns` | uint / ns | `P_OP_ACCUM` | `S` | Chain-validation spans where separable |
| `actor.validation_maximum_elapsed_ns` | uint / ns | `P_OP_ACCUM` | `S` | Exact max plus first ordinal |
| `actor.rebuild_total_elapsed_ns` | uint / ns | `P_OP_ACCUM` | `S` | `_rebuild_state` spans |
| `actor.rebuild_maximum_elapsed_ns` | uint / ns | `P_OP_ACCUM` | `S` | Exact max plus first ordinal |
| `actor.pending_wire_obligations` | uint / events | `P_ACTOR_POINT` | `S` | Current wire queue |
| `actor.pending_wire_octets` | uint / bytes | `P_ACTOR_POINT` | `S` | Current exact queued bytes |
| `actor.pending_control_obligations` | uint / events | `P_ACTOR_POINT` | `S` | Current automatic/terminal control obligations |
| `actor.pending_control_octets` | uint / bytes | `P_ACTOR_POINT` | `S` | Current exact control bytes where derivable |
| `actor.oldest_wire_obligation_age_boottime_ns` | uint / ns | `P_ACTOR_POINT` | `S` | Age from durable preparation receipt |

Event-kind counts must be incrementally observed without changing actor
reduction semantics and independently checked against full prefix replay.
Raw V8 does not replace the retained list or cumulative validation/rebuild;
that remains A3.

### 11.7 SQLite and projection

| Field ID | Value / unit | Descriptor profile | Shape | Required source and meaning |
|---|---|---|---|---|
| `sqlite.busy_timeout_milliseconds` | uint / ms | `P_SQLITE_CONFIG` | `S` | Exact active connection configuration |
| `sqlite.operation_transactions_attempted` | uint / transactions | `P_SQLITE_OP` | `S` | Every target-caused transaction entry |
| `sqlite.operation_transactions_begun` | uint / transactions | `P_SQLITE_OP` | `S` | Successful BEGIN count |
| `sqlite.operation_transactions_committed` | uint / transactions | `P_SQLITE_OP` | `S` | Successful COMMIT count |
| `sqlite.operation_rollbacks_attempted` | uint / transactions | `P_SQLITE_OP` | `S` | Explicit rollback attempts |
| `sqlite.operation_transactions_rolled_back` | uint / transactions | `P_SQLITE_OP` | `S` | Conclusive rollback count |
| `sqlite.operation_transactions_uncertain` | uint / transactions | `P_SQLITE_OP` | `S` | Outcome not locally provable |
| `sqlite.begin_total_elapsed_ns` | uint / ns | `P_SQLITE_OP` | `S` | Existing call bracket |
| `sqlite.begin_maximum_elapsed_ns` | uint / ns | `P_SQLITE_OP` | `S` | Exact maximum |
| `sqlite.body_total_elapsed_ns` | uint / ns | `P_SQLITE_OP` | `S` | BEGIN-success to COMMIT/rollback start |
| `sqlite.body_maximum_elapsed_ns` | uint / ns | `P_SQLITE_OP` | `S` | Exact maximum |
| `sqlite.commit_total_elapsed_ns` | uint / ns | `P_SQLITE_OP` | `S` | COMMIT call brackets |
| `sqlite.commit_maximum_elapsed_ns` | uint / ns | `P_SQLITE_OP` | `S` | Exact maximum |
| `sqlite.rollback_total_elapsed_ns` | uint / ns | `P_SQLITE_OP` | `S` | Rollback call brackets |
| `sqlite.rollback_maximum_elapsed_ns` | uint / ns | `P_SQLITE_OP` | `S` | Exact maximum |
| `sqlite.result_class_counts` | fixed uint map / results | `P_SQLITE_OP` | `M_SQLITE_STAGE_RESULTS_32` | Exact stage-qualified BEGIN/BODY/COMMIT/ROLLBACK result counts |
| `sqlite.last_primary_result_class` | text / enum | `P_SQLITE_OP` | `S` | Exact latest `STAGE.CLASS`, or `NONE` when no stage was attempted |
| `sqlite.operation_rows_written` | uint / rows | `P_SQLITE_OP` | `S` | Rows known to the projection append plan |
| `sqlite.operation_canonical_record_octets` | uint / bytes | `P_SQLITE_OP` | `S` | Canonical record bytes submitted, not file growth |
| `sqlite.database_file_octets` | uint / bytes | `P_SQLITE_FILE` | `S` | Sequential `stat()` observation |
| `sqlite.journal_file_octets` | uint / bytes | `P_SQLITE_FILE` | `S` | Sequential `stat()`; observed absence is exact zero only for that directory lookup |
| `sqlite.wal_file_octets` | uint / bytes | `P_SQLITE_FILE` | `S` | Sequential `stat()` |
| `sqlite.shm_file_octets` | uint / bytes | `P_SQLITE_FILE` | `S` | Sequential `stat()` |
| `sqlite.page_count` | uint / pages | `P_SQLITE_PRAGMA` | `S` | Quiescent same-connection PRAGMA only |
| `sqlite.freelist_count` | uint / pages | `P_SQLITE_PRAGMA` | `S` | Quiescent same-connection PRAGMA only |

Each instrumented transaction stage updates fixed preallocated count, total,
maximum-plus-first-ordinal, and result-class accumulators only after that
stage's outcome is known. V8 adds no transaction-span list and emits no compact
marker inside an unresolved transaction. Page/freelist PRAGMAs are not run
inside a transaction or through a second unbound connection. If a neutral
quiescent read seam is unavailable, both fields use
`OBSERVATION_WOULD_REENTER_ACTIVE_SQLITE_TRANSACTION` and block any later
threshold that requires them. SQLite defines `freelist_count` as unused pages;
it is not derivable from file length
([SQLite PRAGMA](https://www.sqlite.org/pragma.html)).

In particular, `SQLITE_BUSY` from `COMMIT` alone proves neither commit nor
rollback: SQLite documents that the transaction remains active and COMMIT may
be retried. V8 records the exact COMMIT result and the target's subsequent
existing rollback/retry/recovery path; the observer adds neither a retry nor a
rollback and never upgrades BUSY to a conclusive outcome.

The transaction accumulator follows this exact state machine without changing
the existing projection wrapper:

1. increment `transactions_attempted` immediately before the existing
   `BEGIN IMMEDIATE` call;
2. after each attempted `BEGIN`, body, `COMMIT`, or existing rollback call,
   increment exactly one `STAGE.CLASS` coordinate and its stage span; a body
   that runs every planned statement is `BODY.OK`, and its first failure is
   classified once;
3. derive `CLASS` from the SQLite primary result code (extended codes are
   reduced to their documented primary code); missing/non-SQLite exception
   metadata is `OTHER`, never guessed from exception text;
4. increment `transactions_begun` only for `BEGIN.OK`, and
   `rollbacks_attempted` only when the existing target wrapper actually calls
   rollback;
5. after an error and after any existing rollback call, read the same
   connection's non-mutating transaction-state indicator. `COMMIT.BUSY` with
   an active transaction remains active until the existing path resolves it;
6. count `committed` only after `COMMIT.OK` or byte-exact durable-prefix replay
   resolves acknowledgement loss; count `rolled_back` only after a successful
   explicit rollback or an SQLite-reported automatic rollback with no matching
   durable prefix; otherwise count `uncertain`; and
7. set `last_primary_result_class` to the latest attempted non-rollback
   `BEGIN|BODY|COMMIT` stage and class, or `NONE` when none was attempted.

At target convergence the exact invariant is
`attempted = committed + rolled_back + uncertain`. A transaction may be still
active only in an internal hook slot while the target's existing synchronous
error cleanup is running; it may not survive as a fourth terminal category. If
it remains active at the target boundary, it contributes to `uncertain` and
the runtime fence remains. No observer branch chooses whether to retry, roll
back, or commit.

### 11.8 Event loop

| Field ID | Value / unit | Descriptor profile | Shape | Required source and meaning |
|---|---|---|---|---|
| `loop.probe_interval_ns` | uint / ns | `P_LOOP_STATIC` | `S` | Exact signed design value |
| `loop.probes_scheduled` | uint / callbacks | `P_LOOP_OP` | `S` | Timer handles successfully created; skipped phases excluded |
| `loop.probes_fired` | uint / callbacks | `P_LOOP_OP` | `S` | Callbacks actually executed |
| `loop.probe_phases_missed` | uint / phases | `P_LOOP_OP` | `S` | Original phases not executed before the successor callback or terminal closure |
| `loop.probe_last_delay_ns` | duration bound / ns | `P_LOOP_BOUND` | `S` | Exact or censored last value |
| `loop.probe_total_delay_ns` | uint / ns | `P_LOOP_OP` | `S` | Sum of fired exact delays only |
| `loop.probe_maximum_delay_ns` | uint / ns | `P_LOOP_OP` | `S` | Fired maximum only |
| `loop.final_unfired_delay_lower_bound_ns` | duration bound / ns | `P_LOOP_BOUND` | `S` | Right-censored terminal lower bound |
| `loop.debug_enabled` | bool / state | `P_LOOP_CONFIG` | `S` | Observed loop debug configuration; never changed by V8 |
| `loop.slow_callback_threshold_ns` | uint / ns | `P_LOOP_CONFIG` | `S` | Observed configuration when available |
| `loop.slow_callback_events` | uint / callbacks | `P_LOOP_OP` | `S` | Only from a separately admitted stable source |
| `loop.probe_ring_overwritten` | uint / callbacks | `P_LOOP_OP` | `S` | Exact loss count |

`NO_STABLE_SLOW_CALLBACK_SOURCE` is acceptable raw evidence but prevents a
later claim of slow-callback corroboration. V8 must not install a global log
handler or enable asyncio debug merely to populate the field.

### 11.9 Process, cgroup, and GC

| Field ID | Value / unit | Descriptor profile | Shape | Required source and meaning |
|---|---|---|---|---|
| `process.rss_approximate_octets` | uint / bytes | `P_PROCESS_POINT(PROCFS_STATM)` | `S` | `/proc/self/statm`; explicitly approximate |
| `process.pss_rollup_octets` | uint / bytes | `P_PROCESS_POINT(PROCFS_SMAPS_ROLLUP)` | `S` | `/proc/self/smaps_rollup` |
| `process.rss_high_water_octets` | uint / bytes | `P_PROCESS_POINT(PROCFS_STATUS)` | `S` | `/proc/self/status` `VmHWM`, process-lifetime scope |
| `process.cgroup_memory_current_octets` | uint / bytes | `P_PROCESS_POINT(CGROUP_V2_MEMORY_CURRENT)` | `S` | cgroup-v2 `memory.current`, including descendants |
| `process.operation_process_cpu_ns` | uint / ns | `P_PROCESS_CPU(PROCESS_CPU_CLOCK)` | `S` | `process_time_ns` delta |
| `process.operation_owner_thread_cpu_ns` | uint / ns | `P_PROCESS_CPU(OWNER_THREAD_CPU_CLOCK)` | `S` | same-thread `thread_time_ns` delta |
| `process.gc_count_before` | uint-list / generation counters | `P_GC_BEFORE` | `L_GC_GENERATIONS_3` | Exact `gc.get_count()` tuple |
| `process.gc_count_after` | uint-list / generation counters | `P_GC_AFTER` | `L_GC_GENERATIONS_3` | Exact `gc.get_count()` tuple |
| `process.gc_collections_by_generation` | fixed uint map / collections | `P_GC_OP` | `M_GC_GENERATIONS_3` | Operation-local callback deltas |
| `process.gc_collected_objects_by_generation` | fixed uint map / objects | `P_GC_OP` | `M_GC_GENERATIONS_3` | Callback-reported totals |
| `process.gc_uncollectable_by_generation` | fixed uint map / objects | `P_GC_OP` | `M_GC_GENERATIONS_3` | Callback-reported totals |
| `process.gc_pause_count` | uint / pauses | `P_GC_OP` | `S` | Completed start/stop callback pairs |
| `process.gc_pause_total_elapsed_ns` | uint / ns | `P_GC_OP` | `S` | Observer-monotonic duration sum |
| `process.gc_pause_maximum_elapsed_ns` | uint / ns | `P_GC_OP` | `S` | Exact maximum |
| `process.runtime_environment_id` | text / identity | `P_STATIC_LINK` | `S` | Static manifest link |
| `process.filesystem_mount_cgroup_identity_id` | text / identity | `P_STATIC_LINK` | `S` | Static manifest link |

Linux warns that RSS accounting can be asynchronous and imprecise, while
`smaps_rollup` is more detailed but more expensive. V8 labels both instead of
treating them as interchangeable. The cgroup-v2 documentation defines
`memory.current` as total current memory for the cgroup and descendants, so it
must not be labelled process-only
([Linux procfs](https://docs.kernel.org/filesystems/proc.html),
[Linux cgroup v2](https://docs.kernel.org/admin-guide/cgroup-v2.html)).

The GC observer is installed before a measured run and removed afterward
under exact campaign ownership. It records callback start/stop pairs without
calling `gc.collect()`, changing thresholds, disabling GC, or serializing the
callback's mutable dictionary. Unsupported or unmatched callbacks make the
GC pause fields partial. Python exposes the phase and generation, with
collected/uncollectable counts on the stop phase; it supplies no pause duration,
so V8's start/stop clock bracket is observer-added evidence and is not overhead-
free
([Python 3.12 `gc`](https://docs.python.org/3.12/library/gc.html#gc.callbacks)).

GC callback totals are interpreter/process-window observations, not exclusive
CPU attribution to the target task. Activity from other admitted interpreter
work remains visible contamination until the later campaign-isolation gate; it
must not be subtracted through an unobserved estimate.

### 11.10 Freshness and control latency

| Field ID | Value / unit | Descriptor profile | Shape | Required source and meaning |
|---|---|---|---|---|
| `freshness.oldest_unparsed_durable_byte_age_boottime_ns` | uint / ns | `P_FRESH_STATE` | `S` | Same exact source as ingress oldest age |
| `freshness.analysis_pressure_episode_age_boottime_ns` | uint / ns | `P_POLICY_ABSENT` | `S` | Unavailable with `NO_FROZEN_PRESSURE_POLICY` until a separate analysis definition exists |
| `freshness.ping_units` | uint / controls | `P_FRESH_UNITS` | `S` | Exact parsed Ping count |
| `freshness.ping_to_pong_terminal_last_ns` | uint / ns | `P_FRESH_LATENCY` | `S` | BOOTTIME from parser event to dispatch completion/uncertainty |
| `freshness.ping_to_pong_terminal_maximum_ns` | uint / ns | `P_FRESH_LATENCY` | `S` | Exact maximum |
| `freshness.close_units` | uint / controls | `P_FRESH_UNITS` | `S` | Exact parsed Close count |
| `freshness.close_to_response_terminal_last_ns` | uint / ns | `P_FRESH_LATENCY` | `S` | BOOTTIME from parser Close to response completion/uncertainty |
| `freshness.close_to_response_terminal_maximum_ns` | uint / ns | `P_FRESH_LATENCY` | `S` | Exact maximum |
| `freshness.ack_command_queue_wait_ns` | uint / ns | `P_FRESH_ACK` | `S` | Exact A1 wait for ACK-expiry operation; not applicable elsewhere |
| `freshness.shutdown_command_queue_wait_ns` | uint / ns | `P_FRESH_SHUTDOWN` | `S` | Exact A1 wait for shutdown operation; not applicable elsewhere |
| `freshness.candidate_elapsed_boottime_ns` | duration bound / ns | `P_CANDIDATE_BOUND` | `S` | Candidate start to terminal observer cutoff, includes A1 wait and suspend |
| `freshness.target_effect_elapsed_boottime_ns` | duration bound / ns | `P_TARGET_BOUND` | `S` | Attempt effect-start to stable target return/escape boundary; not applicable without an attempt |
| `freshness.marker_last_age_at_terminal_ns` | uint / ns | `P_MARKER_AGE` | `S` | Same-domain age of last retained stable marker |

When an operation contains zero Ping or Close units, its count is an available
zero and latency fields are `NOT_APPLICABLE_TO_REACHED_STATE`; the latencies
are not available zeros. A terminal uncertainty remains part of the latency
endpoint classification and is not discarded to improve results.

### 11.11 Static environment coverage

Kernel, CPU/affinity, Python, event-loop implementation/resolution, OpenSSL,
SQLite, websockets, filesystem, mount, storage, cgroup, process namespaces,
clock domains, and source/runtime identities remain exact signed manifest
facts. The per-operation registry links their manifest identities rather than
copying mutable version strings into every marker. A static fact whose current
collector cannot observe it is an authority-collection failure, not a target
field zero.

## 12. Exact operation-spec, result, and counter records

### 12.1 Spec records

The operation spec ID is the domain-separated hash of one exact record. The
exact identity payloads are:

```text
CapacityMeasurementIngressOperationSpecV49FV8
  workload_family
  ordered_input_chunks_base64
  input_chunk_count
  input_octet_count
  input_sha256
  raw_ingress_batch_sha256
  timeout_seconds
  ordered_expected_logical_output_frames
  expected_output_frame_count
  expected_output_frames_sha256

CapacityMeasurementSubscriptionDispatchSpecV49FV8
  workload_family
  idempotency_key
  expected_outbound_subscription_intent_id
  expected_request_id
  expected_request_command_sha256
  expected_logical_opcode
  expected_logical_payload_sha256
  expected_logical_payload_octets
  expected_dispatch_disposition

CapacityMeasurementAckDeadlineExpirySpecV49FV8
  workload_family
  expected_outbound_subscription_intent_id
  due_scenario: DUE | NOT_DUE
  expected_terminal_cause_code | null

CapacityMeasurementLocalShutdownSpecV49FV8
  workload_family
  timeout_seconds
  expected_terminal_outcome
  expected_local_close_code
  expected_local_close_reason_sha256
```

The subscription logical bytes, deadline, and shutdown Close values are
checked against existing retained runtime authority; they are not effect
capabilities. If the current API does not expose one expected field safely,
the implementation must remove it through a new review or add an owner-derived
read-only authority record. It must not let the sampler inject it.

### 12.2 Result records

```text
CapacityMeasurementIngressResultEvidenceV49FV8
  ingress_progress_evidence_id
  final_parser_cursor_id

CapacityMeasurementSubscriptionDispatchResultEvidenceV49FV8
  outbound_subscription_intent_id
  dispatch_window_evidence
  dispatch_window_evidence_id
  outbound_wire_prepared_event_id
  tls_ciphertext_prepared_event_id
  ordered_kernel_attempt_event_ids
  ordered_kernel_result_event_ids
  outbound_dispatch_completed_event_id
  submitted_ciphertext_octets
  local_dispatch_disposition

CapacityMeasurementAckDeadlineExpiryResultEvidenceV49FV8
  expired
  due_decision_clock_evidence
  due_decision_clock_evidence_id
  ack_deadline_expired_event_id | null
  terminal_transition_event_id | null
  transport_session_termination_id | null

CapacityMeasurementLocalShutdownResultEvidenceV49FV8
  local_shutdown_started_event_id
  local_shutdown_deadline_evidence_event_id | null
  local_close_dispatch_completion_event_id | null
  tls_control_terminal_event_ids
  tcp_half_close_result_event_id | null
  tls_shutdown_observed_event_id | null
  terminal_transition_event_id
  transport_session_termination_id
  terminal_outcome
```

Every durable ID is re-derived from the exact projection/actor prefix. The
not-due ACK decision's clock evidence is runtime-owned volatile evidence
captured before terminal persistence and authenticated by the exact V8
operation capability; it is not reconstructable from an absent actor event.
Its bracket and result are therefore mandatory. A caller-authored boolean is
insufficient.

### 12.3 Compact operation counter snapshot

To keep stable hooks bounded, every marker stores one fixed positional counter
structure, not the full target registry:

```text
CapacityMeasurementOperationCounterSnapshotV49FV8
  counter_schema_id    # derived 64-hex ID under the
                       # RiskYieldMMA2MOperationCounterSnapshotSchemaV4_9F_RawV8
                       # domain; never the domain literal itself
  availability_bitmap   # exactly 66 ASCII 0/1 characters
  values                # exactly 66 UINT-or-null positions
```

Bit/position `i` names the same coordinate in this exact ascending UTF-8 tuple:

```text
actor.batch_append_maximum_elapsed_ns
actor.batch_append_total_elapsed_ns
actor.event_count
actor.operation_appended_events
actor.operation_batch_append_calls
actor.operation_single_append_calls
actor.pending_control_obligations
actor.pending_control_octets
actor.pending_wire_obligations
actor.pending_wire_octets
actor.rebuild_maximum_elapsed_ns
actor.rebuild_total_elapsed_ns
actor.single_append_maximum_elapsed_ns
actor.single_append_total_elapsed_ns
actor.validation_maximum_elapsed_ns
actor.validation_total_elapsed_ns
ingress.durable_buffer_octets
ingress.operation_new_raw_count
ingress.operation_new_raw_octets
ingress.pending_raw_chunks
ingress.pending_raw_octets
kernel.operation_recv_calls
kernel.operation_recv_ciphertext_octets
kernel.operation_send_accepted_octets
kernel.operation_send_attempts
kernel.operation_send_failures
kernel.operation_send_positive_results
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
sqlite.begin_maximum_elapsed_ns
sqlite.begin_total_elapsed_ns
sqlite.body_maximum_elapsed_ns
sqlite.body_total_elapsed_ns
sqlite.commit_maximum_elapsed_ns
sqlite.commit_total_elapsed_ns
sqlite.operation_canonical_record_octets
sqlite.operation_rollbacks_attempted
sqlite.operation_rows_written
sqlite.operation_transactions_attempted
sqlite.operation_transactions_begun
sqlite.operation_transactions_committed
sqlite.operation_transactions_rolled_back
sqlite.operation_transactions_uncertain
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

A bitmap `1` requires a safe unsigned value at the same position; `0` requires
null. The hook never substitutes zero for an unavailable coordinate. Counter
schema identity, tuple length, lexical order, bitmap/value agreement, and every
value bound are checked when the slot is sealed and again when the canonical
marker is built. The SQLite stage-result map and nonnumeric last-result enum
remain in full/aggregate observations and are deliberately absent from this
compact structure; loop and GC have their own fixed accumulators.

Fifty-eight coordinates are operation-local accumulators. The eight point/
current coordinates are `actor.event_count`, the four actor pending
obligation/octet gauges, and the three ingress durable/pending buffer gauges.
`actor.event_count` is the sole current cumulative coordinate despite its
legacy registry spelling. Section 12.4.4 freezes the exact 57-coordinate
monotone subset. Offline replay checks final counter equality against durable
prefixes and the operation aggregate.
Intermediate values that cannot be derived from durable evidence remain
observer facts and are not upgraded into causal authority.

### 12.4 Step-2 canonical envelope and exact type clarification

This subsection closes the pre-implementation byte ambiguities in Sections 4,
6, 10, 11, and 12. It is normative when a prior field-name sketch is less
specific.

#### 12.4.1 One schema key and one semantic-ID preimage

Every standalone Raw V8 Step-2 record uses:

```text
measurement_schema_version = riskyieldmm_physical_transport_a2m_raw_v49f_v8
```

There is no unstated per-record schema literal. Earlier references to a field-
observation, target-observation, spec, result, or counter schema version mean
this exact Raw V8 literal. Every semantic ID is lowercase SHA-256 over canonical
JSON of:

```json
{
  "canonicalization_version": "riskyieldmm_canonical_json_v1",
  "domain": "<exact record domain>",
  "payload": "<the exact JSON object described for that record>",
  "schema_version": "riskyieldmm_physical_transport_a2m_raw_v49f_v8"
}
```

The persisted standalone envelope is the exact flat object:

```text
canonicalization_version
measurement_schema_version
record_domain
... exact identity payload members ...
... exact identity field ...
```

Unknown, missing, duplicate, aliased, or subclass/duck-typed members reject.
Canonical decoding is bounded bytes -> structural scan -> strict JSON -> exact
keys/types -> typed reconstruction -> ID recomputation -> byte-for-byte
canonical re-encoding. Only the pure shared canonicalization primitives may be
imported; no V6/V7 lifecycle/runtime type is an authority for these bytes.

#### 12.4.2 Tagged operation-spec and declaration envelopes

The four spec variants share
`RiskYieldMMA2MOperationSpecV4_9F_RawV8`. Their identity payload is exactly:

```text
operation_kind
spec_type
spec
```

where `spec` is one exact variant body and the tag/type mapping is:

```text
INGRESS               -> INGRESS_OPERATION_SPEC_V1
SUBSCRIPTION_DISPATCH -> SUBSCRIPTION_DISPATCH_SPEC_V1
ACK_DEADLINE_EXPIRY   -> ACK_DEADLINE_EXPIRY_SPEC_V1
LOCAL_SHUTDOWN        -> LOCAL_SHUTDOWN_SPEC_V1
```

The standalone envelope adds `operation_spec_id`. It does not infer a variant
from key presence and never accepts both an outer tag and a contradictory
inner tag.

`CapacityMeasurementOperationDeclarationV49FV8` is independently identified
under `RiskYieldMMA2MOperationDeclarationV4_9F_RawV8`. Its exact identity
payload is:

```text
campaign_manifest_id              SHA-256 identity
manifest_authority_id             SHA-256 identity
measurement_design_id             SHA-256 identity
workload_plan_id                  SHA-256 identity
workload_id                       1..256 UTF-8 bytes
workload_sha256                   SHA-256 digest
sample_sequence                   safe uint, >= 1
operation_sequence                safe uint, >= 1
trial_index                       safe uint
repetition_index                  safe uint
is_warmup                         exact bool
stage                             1..128 UTF-8 bytes
timeout_policy_id                 SHA-256 identity
operation_kind                    exact four-operation enum
operation_spec                    exact complete tagged spec envelope
operation_spec_id                 exact duplicate of the nested derived ID
```

The standalone envelope adds `declaration_id`. A declaration may not replace
the nested spec with only its ID: retaining both exact bytes and derived ID
makes workload replay self-contained and detects substitution before candidate
persistence. `timeout_policy_id` binds the manifest's timeout semantics even
for ACK expiry, whose spec correctly contains no caller timeout.

`workload_family` in every variant is a 1..128 UTF-8-byte canonical identifier
bound by the signed workload plan; it is deliberately not a runtime-selected
enum. Changing it changes the spec ID.

The ingress body has the exact keys already listed in Section 12.1 and these
rules:

- `ordered_input_chunks_base64` is a JSON array of 1..128 canonical, non-empty
  byte strings; each uses standard RFC 4648 base64 with required padding,
  ASCII only, no whitespace or URL-safe alphabet, strict validation, and
  byte-for-byte decode/re-encode equality; decoded aggregate length is
  1..65,536 octets;
- `input_chunk_count` and `input_octet_count` equal the decoded array;
- `input_sha256` is SHA-256 over the raw concatenation in array order;
- `raw_ingress_batch_sha256` is the canonical semantic digest of
  `{"domain":"RiskYieldMMExactOrderedDecryptedIngressChunksV4_5",
  "ordered_chunks_base64":[...]}`; this preserves the existing input authority
  without importing its implementation;
- `timeout_seconds` is a safe integer in 1..300;
- every expected frame is exactly
  `{"opcode":"CLOSE|PONG","payload_base64":"..."}` with a canonical
  standard-base64 payload under the same strict rule and of at most 125
  octets; CLOSE length/code/UTF-8 reason rules are the existing RFC-control
  rules, and a one-octet CLOSE payload rejects;
- an empty CLOSE payload is legal; a CLOSE payload of at least two octets uses
  one big-endian status code from `1000,1001,1002,1003,1007,1008,1009,1010,
  1011,1012,1013,1014` or `3000..4999`, followed by a strictly valid UTF-8
  reason; no other status code is admitted;
- there are 0..4,096 frames and at most 65,536 aggregate decoded payload
  octets; `expected_output_frame_count` is exact; and
- `expected_output_frames_sha256` is the canonical semantic digest of
  `{"domain":"RiskYieldMMA2MExactLogicalOutputFramesV4_9F",
  "ordered_frames":[...]}`.

The subscription body uses exact current-runtime snapshots:

- `idempotency_key` is 1..128 ASCII characters matching
  `[A-Za-z0-9][A-Za-z0-9._:-]{0,127}`;
- `expected_outbound_subscription_intent_id`,
  `expected_request_command_sha256`, and
  `expected_logical_payload_sha256` are SHA-256 values;
- `expected_request_id` is 1..36 ASCII letters, digits, underscore, or hyphen;
- `expected_logical_opcode` is exactly `TEXT`;
- `expected_logical_payload_octets` is 1..65,536; and
- `expected_request_command_sha256` equals
  `expected_logical_payload_sha256`, because the retained command bytes are the
  exact TEXT-frame logical payload; and
- `expected_dispatch_disposition` is `COMPLETE_LOCAL_SUBMISSION` or
  `UNKNOWN_DELIVERY`, the exact `OutboundDispatchDispositionV49C` value
  snapshot. It never means peer receipt. `SENT` belongs to the separate V4
  control-dispatch path and is forbidden here.

The 128-byte idempotency grammar is an intentional signed Raw V8 workload-
profile restriction; the underlying runtime's broader canonical identifier is
not silently reinterpreted as part of this evidence protocol.

The ACK body admits only `DUE` and `NOT_DUE`. `DUE` requires
`expected_terminal_cause_code=ACK_DEADLINE_EXPIRED`; `NOT_DUE` requires null.
The retained intent is a SHA-256 identity. There is no timeout or injected
clock member.

The local-shutdown body snapshots the current owner-derived command exactly:
`timeout_seconds` is 1..300, `expected_terminal_outcome` is one of
`CLEAN_ALL_LAYERS`, `TRUNCATED`, `TIMEOUT`, `FATAL`, `STORAGE_FAILURE`, or
`UNKNOWN_SEND`, `expected_local_close_code` is exactly 1000, and
`expected_local_close_reason_sha256` is exactly SHA-256 of the empty UTF-8
reason (`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`).
These are expectations checked against owner authority, not Close-byte effect
capabilities.

#### 12.4.3 Tagged result-evidence envelope

Returned evidence is a compact, independently identified nested semantic
record under `RiskYieldMMA2MOperationResultEvidenceV4_9F_RawV8`. Its exact
identity payload is:

```text
candidate_id
attempt_id
operation_kind
result_type
result
```

and its envelope adds `result_evidence_id`. The mapping is:

```text
INGRESS               -> INGRESS_RESULT_EVIDENCE_V1
SUBSCRIPTION_DISPATCH -> SUBSCRIPTION_DISPATCH_RESULT_EVIDENCE_V1
ACK_DEADLINE_EXPIRY   -> ACK_DEADLINE_EXPIRY_RESULT_EVIDENCE_V1
LOCAL_SHUTDOWN        -> LOCAL_SHUTDOWN_RESULT_EVIDENCE_V1
```

Two current runtime return/bracket values have no historical semantic ID, so
V8 freezes independent compact copies rather than hashing an opaque Python
object.

`CapacityMeasurementDispatchWindowEvidenceV49FV8` uses domain
`RiskYieldMMA2MDispatchWindowEvidenceV4_9F_RawV8`. Its exact identity payload
is:

```text
transport_session_id
outbound_subscription_intent_id
socket_lease_id
monotonic_clock_domain_id
dispatch_started_at
dispatch_completed_at
dispatch_started_monotonic_ns
dispatch_completed_monotonic_ns
```

The first four members are SHA-256 identities; wall times are canonical UTC
RFC3339 (`Z`, seconds or exactly six fractional digits); monotonic values are
canonical uint128 decimal text. Completion wall time is not earlier than start
and completion monotonic time is strictly greater. Its standalone envelope
adds `dispatch_window_evidence_id`. The subscription result embeds that exact
standalone envelope and separately repeats `dispatch_window_evidence_id`; the
nested ID is recomputed first and both copies must agree.

`CapacityMeasurementAckDueDecisionClockEvidenceV49FV8` uses domain
`RiskYieldMMA2MDueDecisionClockEvidenceV4_9F_RawV8`. Its exact identity payload
is:

```text
transport_session_id
outbound_subscription_intent_id
dispatch_window_evidence
dispatch_window_evidence_id
clock_source_manifest_id
monotonic_clock_domain_id
wall_before_at
sampled_at
wall_after_at
monotonic_before_ns
monotonic_sampled_ns
monotonic_after_ns
uncertainty_milliseconds
synchronized
valid_until
clock_resolution_ns | null
source_observation_sha256 | null
selectable_source_count | null
chronyd_launch_id | null
chronyd_runtime_observation_sha256 | null
committed_ack_deadline_at
committed_ack_deadline_monotonic_ns
due_scenario
```

Identity fields/hashes are 64-hex; wall times use canonical UTC RFC3339;
monotonic readings/deadline are uint128 decimal text and bracket the sampled
value; uncertainty is 0..3,600,000 ms; resolution, when present, is positive;
source count is 1..64; chronyd IDs are present together; `synchronized` is
exactly true; and `valid_until` is not before `sampled_at`. The nested dispatch
window is its complete standalone envelope, its ID is recomputed, and the
separate duplicate must agree. Session, intent, and monotonic-domain members
must match that nested window. The wall bracket satisfies
`wall_before_at <= sampled_at <= wall_after_at`; the monotonic bracket satisfies
`monotonic_before_ns <= monotonic_sampled_ns <= monotonic_after_ns`. `DUE`
requires both bracket beginnings to be at or after the committed
wall/monotonic deadline. `NOT_DUE` requires at least one beginning to be
earlier. The committed deadline is after the nested dispatch-window completion
in both domains. The normalized `source_observation_sha256` member is the current
runtime `ClockEvidenceV4.observation_sha256` value without semantic widening;
all other renamed members have the same one-to-one source mapping. This record
is a non-capability copy checked against runtime-owned authority; the sampler
cannot inject a clock. Its standalone envelope adds
`due_decision_clock_evidence_id`. The ACK result embeds that exact standalone
envelope and separately repeats `due_decision_clock_evidence_id`; the nested ID
is recomputed first and both copies must agree.

The operation result embeds its applicable supporting envelope and duplicated
ID exactly as specified above. The later terminal embeds the complete tagged
operation-result envelope and its duplicated `result_evidence_id`; no
additional projection record kind is introduced in Step 2. The result is
evidence only. Its event IDs are independently rederived from the closed
durable prefix during later terminal integration.

`candidate_id` and `attempt_id` are required SHA-256 identities and bind the
result before terminal integration. The terminal later binds this result and
the separately replayed operation prefix; no result body contains a cyclic
“closed prefix” ID.

The ingress result replaces the ambiguous phrase “existing exact ingress-
progress evidence” with the exact SHA-256 field
`ingress_progress_evidence_id`, followed by `final_parser_cursor_id`, also a
SHA-256 identity. The full ingress progress and
actor/RAW facts remain in the closed prefix; duplicating their potentially
large arrays inside a 512-KiB terminal would violate the frozen bound and
create two authorities for the same prefix.

The subscription result keeps the Section 12.2 fields, including the full
dispatch-window envelope plus its duplicated ID. Every scalar ID is a SHA-256
identity. The two ordered kernel tuples contain 1..256 unique IDs,
have equal length, and pair `KERNEL_SEND_ATTEMPT` position `i` with its
`KERNEL_SEND_RESULT` at position `i`; returned evidence never contains a send
failure. The tuples are mutually disjoint. `submitted_ciphertext_octets` is a
safe integer in 1..4,194,304, the current retained TLS-ciphertext bound rather
than the smaller plaintext/WebSocket bound. `local_dispatch_disposition` is the exact
`COMPLETE_LOCAL_SUBMISSION` value for returned evidence and must equal the spec
expectation. `UNKNOWN_DELIVERY` is represented by an unavailable result plus
its durable prefix, never by a successful return record.

The ACK result has an exact truth table. Its full due-decision clock envelope
and duplicated `due_decision_clock_evidence_id` are always required. When
`expired=false`, `ack_deadline_expired_event_id`,
`terminal_transition_event_id`, and `transport_session_termination_id` are all
null. When `expired=true`, all three are required SHA-256 identities and are
pairwise distinct. The result must agree with the spec's due scenario.

The local-shutdown result requires SHA-256 IDs for command start, terminal
transition, and termination. Deadline evidence
is null on the clean owner-observation path and required only when the durable
prefix contains `LOCAL_SHUTDOWN_DEADLINE_EVIDENCE` for a consumed
no-observation, deadline, or clock-disagreement classification; it may never be
fabricated merely because a deadline existed. The TLS-control
terminal tuple contains 0..256 unique SHA-256 IDs. Every member is an ordered
`TLS_CONTROL_KERNEL_SEND_RESULT` or `TLS_CONTROL_KERNEL_SEND_FAILURE` event for
the local `close_notify` operation; no application-send ID is legal. Its
optional prefix members
obey this monotone causal rule: if local Close completion is null, the TLS
tuple is empty and TCP-half-close/TLS-shutdown IDs are null; if the TLS tuple
is empty, both later IDs are null; and a TLS-shutdown observation requires a
TCP-half-close result. Present IDs are distinct. `terminal_outcome` uses the
same six-member snapshot as the spec and must equal it. Later prefix replay
enforces the stronger event-kind and receipt ordering.

If peer-first convergence means the referenced local-Close completion predates
the measured attempt, the later V8 operation-prefix record must carry its exact
receipt-backed retained-dependency witness. A syntactically valid prior event
ID alone is not self-contained semantic evidence. The singular
`tls_shutdown_observed_event_id` is the final convergence-causing
`TLS_SHUTDOWN_OBSERVED` event; any earlier observations remain ordered prefix
facts and are not substituted for it.

#### 12.4.4 Registry, observation-root, and counter identities

The exact target-observation-root record is:

```text
candidate_id
attempt_id | null
operation_kind
instrumentation_mode: OFF | ON
target_field_registry_id
observation_count
ordered_observation_ids
target_observation_root_sha256
```

under `RiskYieldMMA2MTargetObservationRootV4_9F_RawV8`. Count is 1..67 and
equals the unique ordered ID tuple. The ID field is the semantic ID of every
preceding member; it is not a plain concatenation hash. Every nested
observation context must agree with candidate, attempt, operation,
instrumentation mode, and registry. `OFF` permits exactly the three non-
checkpoint same-process roles;
startup recovery has its one recovery context; other `ON` cardinalities follow
Section 10.2.

The compact-counter schema is independently identified under
`RiskYieldMMA2MOperationCounterSnapshotSchemaV4_9F_RawV8` from:

```text
counter_field_count = 66
ordered_counter_field_ids
monotone_counter_field_ids
```

`counter_schema_id` is the resulting 64-hex semantic ID, not the domain
literal. For this exact payload its frozen value is
`5181eb89788d511ffeb2ccc65264b81e9e0d3ae977043820524f8b08dfa58fc3`.
The Step-2 inventory publishes that literal while tests independently
regenerate it from the complete preimage. A snapshot serializes that ID, an
exact 66-character ASCII bitmap, and an exact 66-position UINT-or-null array.
The monotone subset is frozen in the Step-2 golden inventory as the 57-
coordinate lexical tuple obtained from the 66 fields by excluding exactly:

```text
actor.pending_control_obligations
actor.pending_control_octets
actor.pending_wire_obligations
actor.pending_wire_octets
ingress.durable_buffer_octets
ingress.pending_raw_chunks
ingress.pending_raw_octets
parser.last_unit_elapsed_ns
parser.last_unit_thread_cpu_ns
```

For each monotone coordinate, replay projects the complete emitted-marker
sequence onto positions where that coordinate is available. That projected
value sequence must be monotonically nondecreasing; an unavailable position
does not reset the last available value. The exact zero-based monotone
positions are `0..5`, `10..15`, `17..18`, `21..26`, and `29..65`, totaling 57.
With ring overwrite, replay may validate the retained subsequence and the
independently maintained extrema but must not claim that those records alone
proved ordering across the lost prefix. `actor.event_count` is a session-
current but monotonically nondecreasing coordinate; the seven pending/buffer
gauges and two last-value coordinates above may legitimately decrease. This
replaces the overbroad phrase “monotonically nondecreasing where appropriate”
with a machine rule.

The pure record constructor validates syntax, registry membership, and the
frozen structural truth tables. Platform errno-name agreement, prefix-derived
IDs, operation state/reached-state, and cross-record temporal progression are
separate explicit replay-validator contexts; syntax alone never becomes
semantic acceptance.

## 13. Measurement-neutrality constraints

### 13.1 Forbidden behavior changes

V8 instrumentation must not alter:

- socket blocking mode, buffer size, read length, poll timeout, retry, or send
  slice;
- TLS call order, BIO reads/writes, WANT handling, shutdown, or generated
  bytes;
- WebSocket parser input, unit order, source slices, masking, application
  completion, or automatic output;
- actor event content/order, validation decision, rebuild result, final-writer
  precedence, or retained causal history;
- projection journal mode, busy timeout, transaction boundary, statement
  order, commit/rollback decision, clock authority, or writer fence;
- A1 capacity policy, ticket order, deadline, reservation, rejection,
  cancellation, release, or terminal barrier;
- GC enabled state, thresholds, explicit collection, or generation policy;
- event-loop debug mode, slow-callback threshold, task factory, exception
  handler, scheduling policy, or callback ordering;
- public exports, construction capabilities, live-factory denial, or
  promotion eligibility; or
- operation selection, later workload order, risk decision, or trading state.

Read-only observation is not assumed to have zero overhead. Clock calls,
`poll(0)`, ioctl, procfs, GC callbacks, counter updates, and terminal
serialization all consume resources. That effect is measured and later tested
through matched campaigns; it is not hidden by the word “read-only.”

### 13.2 Observer failure firewall

The compact hook has no await and must be designed not to raise. Ordinary
observer failures set a preallocated sticky error code and return. They do not
change target control flow. `asyncio.CancelledError`, `KeyboardInterrupt`, and
`SystemExit` retain Raw V7 interruption precedence and are never swallowed by
an observer wrapper. Python documents that `CancelledError` is injected on a
later loop cycle, may be caught for cleanup, and should normally be propagated;
it is a `BaseException`, not an ordinary `Exception`
([Python 3.12 task cancellation](https://docs.python.org/3.12/library/asyncio-task.html#asyncio.Task.cancel),
[Python 3.12 asyncio exceptions](https://docs.python.org/3.12/library/asyncio-exceptions.html#asyncio.CancelledError)).

If an expensive checkpoint adapter fails, the adapter records exact field
unavailability and stops only its own remaining observations according to the
predeclared adapter order. It does not retry dynamically, lengthen the target
deadline, or fail the transport. If even the availability record cannot be
constructed, the terminal transaction emits the minimal observer-error
closure.

### 13.3 OFF and ON semantics

Raw V8 supports exact `OFF` and `ON` instrumentation modes under the same
always-on V8 candidate/optional-attempt/terminal/closure lifecycle:

- `OFF` executes no compact marker clocks/counter copies, no periodic loop
  probe, no target adapter, no full checkpoint, and no GC callback. It still
  writes the complete target-observation container shapes; lifecycle/static
  facts may be copied from already mandatory evidence, while every field that
  requires an ON observer is `INSTRUMENTATION_DISABLED`. It writes the minimal
  disabled marker closure after the admission/target outcome.
- `ON` executes exactly the signed marker/probe/checkpoint/GC plan.
- both modes use identical target operation specs, A1 admission, runtime,
  source, storage, and session authority;
- neither mode may observe the other mode's result and change a later
  operation; paired trial order comes only from the signed seeded plan.

Raw V8 acceptance requires source-level non-interference tests plus deterministic
fixture equality of target call order, target arguments/bytes, operation-
specific return or exception class, and physical effect classification. It does
**not** require byte equality of the full projection receipt chain: OFF and ON
carry different versioned measurement records/timestamps, so their receipt
hashes can legitimately differ and cascade. V8 introduces no ad hoc stripping
rule to hide that fact. The reviewed physical alpha-normalizer and its
fixture-level deterministic oracles are the immediate next A2-M gate. Full
matched neutrality campaigns wait until the independent finalizer, campaign
isolation, and atomic publisher are accepted, so campaign results cannot outrun
their evidence and publication prerequisites.

### 13.4 Overhead accounting

Every sample reports:

```text
compact hook call count and total/max observer span
full checkpoint count and total/max span by adapter
loop-probe callback count and total/max callback body span
GC callback count and observer span
terminal marker serialization/validation/write spans
marker memory allocation before the candidate
ring overwrite and observer-error counts
```

Allocation before candidate is reported separately and is excluded from both
candidate and target-effect elapsed, but not from campaign resource accounting.
Terminal marker publication occurs after the admission/target outcome and is
excluded from target-effect elapsed, but included in end-to-end cancellation/
runner latency.

## 14. Cancellation, fatal interruption, crash, and bounds failure

### 14.1 Cancellation ordering

Once the V8 candidate is committed, cancellation has two frozen paths.
Before an attempt exists:

```text
same candidate task receives CancelledError
-> existing A1 path releases/discards any accepted ticket under its unchanged rules
-> private observer records the resulting bounded outcome without mutation
-> exact CANCELLED_BEFORE_ENTRY evidence is sealed; no target prefix exists
-> candidate terminal + marker closure commit atomically
-> same CancelledError is re-raised
```

After the V8 attempt is committed:

```text
target receives CancelledError
-> existing target cleanup / owner abort / terminal convergence runs
-> periodic probe is disabled without awaiting another task
-> volatile marker state is sealed
-> exact durable target prefix is reconstructed
-> CANCELLED terminal + marker closure commit atomically
-> same CancelledError is re-raised
```

Cancellation before candidate commit produces no operation sample. Cancellation
after candidate commit but before the A1 call still produces the no-attempt
candidate closure above. Cancellation after target return but before terminal
commit is still `CANCELLED` unless the accepted Raw V7 precedence proves the
operation return already crossed its frozen terminal boundary. The
implementation must exhaustively test every await/callback boundary rather than
infer this ordering from one happy path.

A full checkpoint is synchronous and must not add an await. Ordinary
`Task.cancel()` is therefore observed only at an existing suspension point
before or after that checkpoint. The acceptance case described as cancellation
"during checkpoint" means a controlled `BaseException` fault at each
synchronous adapter seam plus a pending cancellation delivered at the next
existing await; it does not authorize an artificial checkpoint suspension
point.

### 14.2 KeyboardInterrupt and SystemExit

Fatal interruption uses `INTERRUPTED`; before an attempt it also binds
`INTERRUPTED_BEFORE_ENTRY`, and after an attempt it retains the exact granted
outcome. It follows the same best-effort synchronous terminal/closure protocol
and then propagates. Failure to persist cannot be masked by returning a
measurement error. Startup recovery later records the orphan, unavailable
marker state, and only any truthfully surviving duration bound as censored.

### 14.3 Process loss

The ring is deliberately volatile. On startup recovery:

- `emitted_total`, overwritten count, intermediate extrema, periodic probes,
  GC pause data, and non-durable result facts are unknown;
- retained markers are empty with
  `PROCESS_LOSS_VOLATILE_MARKER_STATE`, never an exact empty series;
- a candidate with no durable attempt is classified
  `UNRESOLVED_PROCESS_LOSS`; replay does not infer whether A1 rejected,
  queued, granted, or was about to return;
- a durable attempt proves `GRANTED` and bounds any possible target work to the
  exact post-attempt durable prefix;
- actor/RAW/projection facts are reconstructed from the ledger;
- boundary/static fields which can be observed only after restart are labelled
  recovery observations and are never relabelled as pre-crash values; and
- no target effect is retried.

This gives honest crash evidence but not crash-surviving in-operation peaks.
If later threshold acceptance requires those peaks under process-kill tests, a
separate durable marker-buffer protocol must be designed and re-neutralized.

### 14.4 Bound failure

An artifact, field, checkpoint, or serialization bound failure after target
effect does not erase the operation lifecycle. The terminal transaction writes
a minimal `ARTIFACT_BOUND_EXCEEDED` marker closure when possible, the raw run
remains failed/partial, and no analyzer may exclude it silently. A manifest
whose declared fixed plan exceeds a bound rejects before the candidate.

## 15. Raw V8 artifact and replay

Raw V8 retains the exact four-member logical layout:

```text
v4_9f_a2_measurement/<evidence_bundle_id>/
    manifest.json
    samples.jsonl
    correctness.json
    integrity.json
```

No fifth marker file is admitted. Each sample embeds:

```text
committed V8 candidate + receipt
optional committed V8 attempt + receipt, present exactly when target authorization was reached
committed V8 terminal + receipt
committed V8 marker closure + receipt
complete closed operation prefix and record bytes/receipts
the closure's nested before / checkpoint / after / aggregate target observations,
or its one nested startup-recovery observation, without a second serialized copy
exact tagged operation result or explicit unavailability
sample identity
```

Replay performs, in order:

1. byte/member/media/count/size closure before nested materialization;
2. exact V8 manifest and separately admitted static expectation validation;
3. strict field-registry reconstruction and registry-ID equality;
4. exact workload schedule and operation-spec tagged-union validation;
5. projection receipt/record replay, candidate-before-admission,
   attempt-only-after-grant, attempt-before-effect, exact no-attempt
   authorization classification, terminal/closure adjacency, and no-open-
   candidate-locator proof;
6. actor/RAW/parser prefix replay under existing authoritative registries;
7. marker ordinal/ring/extrema/loss-accounting verification;
8. marker anchor membership and monotonic coordinate verification;
9. full field presence, type, unit, method, role, availability, errno, and
   clock-span verification;
10. operation-specific returned-result derivation/cross-check;
11. schedule completion or locally issued, structurally replayed run-ending-
    prefix validation, without claiming post-run suffix provenance; and
12. fail-closed provisional correctness validation.

As in Raw V7, `correctness.json` remains independently unfinalized. Every V8
correctness record must retain both
`CORRECTNESS_FINALIZER_NOT_IMPLEMENTED` and
`POST_RUN_SUFFIX_PROVENANCE_UNATTESTED`; removing either disclosure rejects
replay. The receipt chain and unsigned four-member closure establish bounded
self-consistency, not issuance authenticity or proof that no suffix was
replaced. Caller-authored lineage, coverage, neutrality, cleanup, or PASS
booleans remain rejected. Raw V8 adds evidence required by a future signed or
independently anchored finalizer but does not implement that finalizer.

The in-memory four-member closure is not durable external publication. Temp
files, file and directory `fsync`, rename/collision rules, restart cleanup,
immutability, and external anchors remain a later gate.

## 16. Frozen parser and resource bounds

These bounds protect the observer and decoder. They are not measured capacity,
production thresholds, or recommended settings.

| Surface | V8 hard bound |
|---|---:|
| Open V8 candidates per session | 1 |
| Attempts per candidate | 0 or 1; exactly 1 only for `GRANTED` |
| Terminals per candidate | 1 |
| Marker closures per candidate | 1 |
| Marker ring capacity `C` | 8 to 4,096 |
| Reserved first markers | 1 |
| One canonical compact marker | 4 KiB |
| One marker closure | 24 MiB |
| Emitted marker counter | `0 .. 2^53 - 1` |
| Periodic loop-probe retained slots | 4 to 4,096 |
| One canonical loop-probe record | 1 KiB |
| Periodic loop-probe interval `P` | 1,000,000 to 60,000,000,000 ns |
| Compact snapshot coordinates/extrema | exactly 66 |
| One canonical marker extremum | 1 KiB |
| Marker-kind count/ordinal coordinates | exactly 19 |
| Full stable target checkpoints per operation | 64 |
| Same-process target observations per sample | 3 to 67 |
| Startup-recovery target observations per sample | exactly 1 |
| Field observations per target observation | exactly 185 |
| One strict value-union record | 3 KiB |
| One source-error-detail semantic preimage | 2 KiB |
| One target-field observation | 4 KiB |
| One target-observation clock span | 512 bytes |
| One target-observation context | 2 KiB |
| Ordered target-observation IDs per sample | 1 to 67 |
| One complete target observation | 256 KiB |
| Target-field registry record | 2 MiB |
| Target-observation-root record | 8 KiB |
| Compact counter schema record | 8 KiB |
| Compact counter snapshot record | 2 KiB |
| Operation input chunks | 128 |
| Ingress input octets | 65,536 |
| Expected logical output frames | 4,096 |
| Expected logical output payload octets | 65,536 aggregate; 125 per frame |
| One operation-spec record | 2 MiB |
| One operation-declaration record | 3 MiB |
| One operation-result-evidence record | 512 KiB |
| Operation timeout | 1 to 300 seconds where the operation exposes one |
| RAW dependencies in one prefix | 64 |
| Actor events in one prefix | 262,144 |
| Canonical closed prefix | 48 MiB |
| One V8 candidate | 512 KiB |
| One V8 attempt | 512 KiB |
| One V8 terminal | 512 KiB |
| One V8 sample JSONL record | 96 MiB |
| V8 manifest JSON | 48 MiB |
| V8 samples JSONL | 512 MiB |
| V8 correctness JSON | 4 MiB |
| V8 integrity JSON | 1 MiB |
| Complete in-memory four-member closure | 565 MiB |
| V8 samples/trials | 100,000, subject to byte bounds |
| Identifier/reason text | 256 UTF-8 bytes unless a narrower existing bound applies |
| Canonical JSON nesting depth | 64 |
| Canonical JSON object members | 512 per object |
| Canonical JSON array elements | 524,288 per array |
| Safe exception chain | Raw V7 depth and byte bounds, unchanged |
| Absolute new V8 nanosecond values | canonical uint128 decimal text |
| Relative offsets/counts/durations | exact I-JSON-safe integers |

Before allocating an array or decoding base64, the parser checks the enclosing
byte/count bounds. Cross-products are checked: a candidate cannot separately
pass marker count and marker size while exceeding closure/sample/member limits.
In particular, retained markers, retained loop probes, extrema, the nested
target-observation tuple, IDs, and closure framing must together fit the 24 MiB
closure bound. The independent maxima for ring capacity and checkpoint count
are not promised to coexist; a signed plan whose exact worst-case cross-product
does not fit rejects before its first candidate.

The V8 structural scanner uses the stable errors
`V8_JSON_DEPTH_LIMIT_EXCEEDED`, `V8_JSON_OBJECT_MEMBER_LIMIT_EXCEEDED`,
`V8_JSON_ARRAY_ELEMENT_LIMIT_EXCEEDED`, and
`V8_JSON_MALFORMED_STRUCTURE`. It is a V8-local copy of the proven scanning
order, not an import of V7-branded code. One ingress chunk's encoded text is
prechecked at at most 87,384 ASCII bytes before decoding; one logical-frame
payload is prechecked at at most 168. The parser maintains the decoded
aggregate counters incrementally and rejects before concatenation or an
unbounded intermediate allocation.

After that broad scan, Step-2 typed records impose the narrower exact limits:
nesting depth at most 16, at most 32 members in one object, exactly 185 target
field-array entries, 1..67 root IDs, exactly 66 counter bitmap/value/extremum
positions, and at most 32 entries in the largest fixed map. No separate
undefined “node” metric is used; the exact byte, depth, member, and array
limits are the complete Step-2 materialization guard. These structural limits
are not permission to ignore the smaller byte bounds above.

Plan admission computes exact canonical worst-case member lengths from the
chosen capacities and declared variant bounds, including JSON array commas and
object framing. It requires:

```text
closure_fixed_framing
  + C * maximum_compact_marker_bytes
  + probe_slots * maximum_loop_probe_record_bytes
  + 66 * maximum_extremum_record_bytes
  + target_observation_count * maximum_target_observation_bytes
  + ordered_ID_and_count_framing
  <= 24 MiB
```

and separately checks the 96-MiB sample and enclosing member limits. This is a
conservative admission calculation; actual canonical records are checked
again. A registry-aware worst-case generator must exercise all 185 exact
shapes, maximum safe integers, the largest fixed maps, the maximum safe
exception class, hashes, permitted OS tuples, repeated registry/context IDs,
container metadata, and clock spans. The earlier draft calculation of
approximately 211,533 bytes preceded the final full nested-envelope and source-
failure-phase clarifications and is not current bound evidence. The generated
test must recompute exact final bytes from the literal registry and reject the
design if the result is not below 262,144 bytes; the implementation may not
silently truncate fields or reinterpret the ceiling.
Multiplying an independent per-field maximum by 185 is invalid: the outer
bound and exact registry-shape cross-product reject before materialization.

The 4,096-marker maximum does not claim that a Python object graph has a fixed
portable resident-byte size. The implementation must preallocate on the
qualified interpreter, measure actual resident/allocation cost, and bind the
interpreter/build in the manifest. If it cannot demonstrate bounded allocation
under the hard plan, the capacity must be reduced and a new design identity
created before results are inspected.

## 17. Acceptance matrix

Raw V8 remains unaccepted until every row passes against one stable final tree.
Focused success counts from intermediate implementations are diagnostic only.

| Group | Required falsification/acceptance evidence |
|---|---|
| Version separation | V6/V7/V8 top-level and nested substitutions, relabelled domains, old signatures, wrong predecessor protocol, and unknown fields all reject |
| Source/authority | Fresh current source inventory, loaded/critical role closure, one-shot V8 signature, static expectation contradiction, task/loop/thread/process/fork misuse, expiry, clone, and reuse all reject |
| Projection schema | New candidate/attempt/terminal/closure kinds, exact typed tables, schema fingerprint/validation version, unique constraints, atomic candidate-plus-locator insert, candidate-attempt relation, receipt adjacency, open-candidate locator, and parser registry replay are tested |
| Pre-effect persistence faults | Fault before/after candidate insert, locator insert, candidate COMMIT/acknowledgement, A1 grant, attempt insert, and attempt COMMIT/acknowledgement; target is never called without a resolved attempt receipt, conclusive no-attempt grant failure remains included, and uncertain state fences until replay resolves it |
| Atomic closure | Fault at every statement and before/after BEGIN/terminal insert/closure insert/open-candidate-locator delete/COMMIT yields both terminal+closure or neither; restart is idempotent |
| Operation union | Exact success, no-effect return, ordinary error, partial effect, every A1 non-grant class, cancellation, interruption, and orphan recovery for all four operation tags |
| Operation mismatch | Wrong spec type/tag, extra/null spec, unauthorized callback/socket/clock/bytes, wrong runtime precondition, wrong return type, and wrong durable prefix reject |
| Schedule legality | State-machine-valid multi-operation schedules pass; post-terminal, pending-ingress overtaking, wrong intent, hidden session reset, missing middle, reordering, duplicate coordinate, and structurally unauthorized short prefix reject |
| Stable cutoff | Every required hook is after its exact durable boundary and before the next mutation; hooks at each forbidden unstable seam are asserted absent by source-level tests |
| Adapter ownership | Every full adapter is tested at its real lock/transaction seam; public-observer re-entry, await, cross-thread access, mutation, and lock-order inversion are rejected or produce the exact unavailable reason without deadlock |
| Marker capability | Wrong task/loop/thread/process/fork/candidate/optional-attempt/kind/anchor, reuse after close, ordinal regression, clone, and public/caller construction reject without authorizing admission or target effects |
| Ring no-overflow | Capacities 8, boundary `C`, exact retained sequence, ordinal order, extrema, counts, and deterministic replay pass |
| Ring overflow | `C+1`, repeated wrap, very large emitted count, first-marker preservation, exact tail formula, overwritten count, extrema survival, and series-ineligible classification pass |
| Observer faults | Clock/counter/checkpoint/GC/probe/serialization failures yield exact partial/unavailable evidence, identical target invocation/effect oracle, and no measured-value target branch; raw measurement receipts may differ |
| Marker bounds | Oversized marker, closure, checkpoint, reason, list, map, nested value, count/byte cross-product, and preallocation plan reject before unsafe materialization |
| Clock domains | Absolute value above `2^53`, canonical decimal rejection cases, origin mismatch, offset overflow, resolution, clock regression, suspend/resume, and cross-domain subtraction mutations reject |
| Loop series | On-time, early within resolution, late, same-deadline undefined order, missed phases, no catch-up storm, cancellation before/after fire, ring overflow, synchronous stall, and right-censored final delay |
| Field registry | For every field: missing, duplicate, unknown, wrong order, type, unit, method, role, operation applicability, attempted/not-attempted span pairing, availability/value pairing, censoring, errno, and reason mutations reject |
| A1 fields | Empty/one/full FIFO, every command kind, queue age, immediate rejection without ticket, accepted ticket, target grant, every rejection/timeout/cancellation/closed/interruption/failure class, unresolved process loss, counter regression, sequence-kind mismatch, and unreachable-capacity counter neutrality |
| Kernel fields | SIOCINQ/SIOCOUTQ/SO_RCVBUF/SO_SNDBUF success and each errno, literal doubled-buffer semantics, poll masks/errors/HUP, readiness races, accepted send prefix, and zero-vs-unavailable separation |
| TLS fields | BIO/plaintext pending, read/write octets, WANT_READ/WANT_WRITE, staged/remaining invariants, partial sends, automatic and shutdown output, driver failure, and unsupported observation |
| Durable/parser fields | Complete/incomplete cross-RAW units, every split, fragmentation, parser error, application completion, automatic output, retained tail, oldest age, and per-unit elapsed/CPU accounting |
| Actor fields | Every event kind, empty/nonempty tail, single/batch append, validation/rebuild timing, queue/control obligations, 1k/10k/100k diagnostic histories where feasible, and differential full replay |
| SQLite fields | 0/1/10/100/500/5000 ms contention, BEGIN/body/COMMIT/rollback spans, BUSY/LOCKED/FULL/IOERR/INTERRUPT/NOMEM/uncertain outcomes, rows/bytes, sidecar races, quiescent PRAGMAs, and no active-transaction re-entry |
| Process/GC | statm approximation, smaps permission/error, VmHWM lifetime scope, cgroup descendants, process/thread CPU distinction, GC phases/generations/unmatched callbacks, and no GC-setting mutation |
| Freshness/control | zero/one/multiple Ping and Close, exact causal endpoints, terminal uncertainty, ACK/shutdown queue waits, oldest durable byte across continuations, suspend, and no-policy pressure-age unavailability |
| Cancellation | Before candidate, after candidate before A1, while queued, after grant before attempt, after attempt, every target await/stable hook, during checkpoint, during target cleanup, before terminal transaction, commit acknowledgement loss, and propagation identity/precedence |
| Process loss | Kill after candidate commit, every A1 transition, attempt commit, core transition, and terminal-transaction boundary; durable prefix recovers, no-attempt outcome stays unresolved, volatile marker facts are unavailable, only truthful duration bounds are censored, no zero fabrication, no retry, no later runtime command before reconciliation |
| Measurement firewall | Forced marker/probe/checkpoint faults never change socket/TLS/parser/actor/projection/A1 behavior; no measured value appears in a target decision branch |
| Focused OFF/ON | Deterministic target call order, arguments/bytes, return-or-exception class, and physical effect classification match for each operation with OFF/OFF, ON/ON, and OFF/ON fixture pairs; this row explicitly does not claim full raw receipt/hash equality or complete matched-campaign neutrality |
| Static audits | No V8 marker type is an actor event, no per-marker SQLite write, no unbounded list/deque/dict, no arbitrary error stringification, no generic nullable field mapping, no threshold/enforcement type, no public export, and public live factory remains closed |
| Artifact replay | Complete schedule and locally issued/structurally replayed run-ending prefix, exact four members, marker/target closure, byte/count bounds, forged in-memory records, alternate self-consistent suffixes, V7 substitution, both mandatory provisional disclosures, and provisional-PASS rejection; no suffix-provenance claim is admitted |
| Adjacent regressions | Final Raw V7 suite plus accepted V4.9A-E, A1, clock, source authority, TLS, parser, actor, projection, terminal, public-factory-denial, and full repository tests remain green |
| Leftover audit | No placeholder IDs, test-only production branch, stale schema alias, temporary output, orphan fixture, obsolete “current V6/V7” claim, or unreviewed public symbol remains |

Acceptance also produces a machine-readable coverage matrix with one row per
registry field and columns for every operation, boundary/checkpoint/aggregate
role, success/error/cancel/recovery path, AVAILABLE/NOT_APPLICABLE/UNAVAILABLE/
CENSORED result, test ID, and future fail-closed threshold implication. A prose
claim of “all fields covered” is insufficient.

## 18. Implementation sequence

Implementation must proceed in this order:

1. **COMPLETE — finish and independently accept Raw V7.** Its full source,
   lifecycle, projection, fault, recovery, runtime, artifact, and regression
   matrix passed on the recorded post-format tree.
2. **COMPLETE — freeze the exact V8 field-registry constants and operation
   spec/result types in a new module/domain.** The corrected isolated contract,
   independently generated inventory, strict mapping/byte/bound tests, and
   targeted Raw V7 regressions passed on 2026-07-25.
3. **ACTIVE — add V8 projection candidate/attempt/terminal/marker-closure
   records, tables, unique constraints, candidate-attempt replay,
   open-candidate locator, atomic final transaction, and startup recovery.**
   Keep V7 tables/codecs unchanged.
4. Implement the preallocated marker/probe/extrema structures and sealed
   task-bound capability. Prove ring semantics and fault firewall in isolation.
5. Add the private A1 observer and prove immediate-reject, queued, granted,
   timeout, cancellation, close, interruption, failure, and process-loss paths;
   it must never add an await or mutate gate decisions.
6. Add source-owned compact hooks one operation at a time, starting with
   ingress, then subscription, ACK expiry, and shutdown. At each hook perform a
   source review proving the durable cutoff and absence of target branching.
7. Add exact operation-local counters for TLS, kernel, parser, actor, and
   SQLite spans. Cross-check final counts against durable prefix replay.
8. Implement sequential target adapters and typed unavailability. Generate the
   machine-readable complete coverage matrix and close every field or explicit
   reason before adding artifact claims.
9. Add the V8 collector, exact workload-plan builder, fresh source/runtime/
   projection authority capture, independent expectation, one-shot signer,
   session runner, and operation-specific deterministic fixtures.
10. Add V8 sample/correctness/integrity classes and strict four-member codec.
   Preserve the unfinalized correctness invariant.
11. Run the complete V8 acceptance matrix, final Raw V7 and adjacent regression
    groups, static serialization/public-export audits, compilation/lint,
    `git diff --check`, and explicit worktree/leftover review.
12. Reconcile the parent A2-M protocol and roadmap only from final evidence.
    Mark Raw V8 accepted only if one stable tree supplies all claimed results.
13. Proceed next to physical event-field normalization and fixture-level
    deterministic neutrality oracles. Then implement the independent finalizer,
    campaign isolation, and atomic publisher before running full matched
    neutrality or frozen workload campaigns. Calibration, thresholds, and
    enforcement remain later gates.

An unsuccessful direction is abandoned when it cannot preserve the accepted
target prefix/outcome, cannot bind a stable causal cutoff, requires unbounded
observer state, silently loses fields/markers, makes marker values influence
target decisions, weakens Raw V7, or cannot be replayed within frozen bounds.

## 19. Primary-source synthesis and limits

| Source | What it establishes | Limitation | V8 use |
|---|---|---|---|
| [RFC 7493](https://www.rfc-editor.org/rfc/rfc7493.html#section-2.2) | JSON integer exactness above `2^53-1` cannot be assumed; strings are recommended for exact larger numbers | It does not define RiskYieldMM clocks or canonicalization | New absolute nanosecond values are canonical decimal text; offsets stay safe integers |
| [Python 3.12 `time`](https://docs.python.org/3.12/library/time.html) | Nanosecond APIs, monotonic semantics, suspend-aware BOOTTIME, process CPU, and thread CPU meanings | Clock availability/resolution is platform dependent | Separate clock domains and explicit resolution/availability |
| [Python 3.12 asyncio event loop](https://docs.python.org/3.12/library/asyncio-eventloop.html#scheduling-delayed-callbacks) | `call_at` uses the loop clock and equal-time callback order is undefined | The 3.12 API page does not state the one-resolution-early rule and does not guarantee callback execution during a blocked loop | Phase-locked probe with missed phases and right-censoring, not a stable-state oracle |
| [CPython 3.12.12 `BaseEventLoop._run_once`](https://github.com/python/cpython/blob/v3.12.12/Lib/asyncio/base_events.py) and [Python 3.13 asyncio event loop](https://docs.python.org/3.13/library/asyncio-eventloop.html#scheduling-delayed-callbacks) | The frozen CPython source promotes timers below `time() + _clock_resolution`; the 3.13 API page explicitly documents one-resolution-early execution | Source behavior is implementation/version specific and cannot be generalized to another loop | Admit early tolerance only for the exact manifest-bound implementation and conversion profile |
| [Python 3.12 cancellation](https://docs.python.org/3.12/library/asyncio-task.html#asyncio.Task.cancel) and [`CancelledError`](https://docs.python.org/3.12/library/asyncio-exceptions.html#asyncio.CancelledError) | Cancellation is injected on a later loop cycle, cleanup may run before propagation, and cancellation is a `BaseException` | It does not make arbitrary persistence cancellation-safe | Preserve Raw V7 synchronous terminal ordering and re-raise |
| [Linux `tcp(7)`](https://man7.org/linux/man-pages/man7/tcp.7.html) | SIOCINQ is unread queued data and SIOCOUTQ is unsent queued data | Values are point observations, not cross-layer snapshots or peer state | Literal queue fields with spans and errno |
| [Linux `socket(7)`](https://man7.org/linux/man-pages/man7/socket.7.html) | Linux doubles SO_RCVBUF/SO_SNDBUF for bookkeeping and returns the doubled values | A buffer size is not current free capacity | Preserve literal values; forbid inferred headroom |
| [Python 3.12 `select`](https://docs.python.org/3.12/library/select.html) | Poll masks identify current readiness/error/hangup states | Readiness may change immediately and is not delivery | Exact point masks and derived booleans only |
| [Python 3.12 `ssl`](https://docs.python.org/3.12/library/ssl.html#ssl.MemoryBIO) | MemoryBIO exposes pending local bytes | It says nothing about remote receipt or complete TLS work | Direct pending counts plus separate operation counters |
| [SQLite transactions](https://www.sqlite.org/lang_transaction.html) and [result codes](https://www.sqlite.org/rescode.html) | One writer, BEGIN/COMMIT BUSY behavior, COMMIT-BUSY leaves the transaction active and retryable, and FULL/IOERR/INTERRUPT/other outcomes are distinct | It does not define project effect certainty or observer neutrality | Stage-specific spans and exact result classes; COMMIT-BUSY alone is never commit/rollback; no timeout-preemption claim |
| [SQLite PRAGMA](https://www.sqlite.org/pragma.html) | `page_count`, `freelist_count`, and `busy_timeout` have exact connection semantics | PRAGMA reads add work and may be illegal at the current owned seam | Quiescent observation only or explicit fail-closed unavailability |
| [Linux procfs](https://docs.kernel.org/filesystems/proc.html) | statm RSS can be imprecise; smaps_rollup is more detailed and costly; VmHWM is process high water | Snapshots are sequential and observer-expensive | Label scope/precision and measure adapter span |
| [Linux cgroup v2](https://docs.kernel.org/admin-guide/cgroup-v2.html) | `memory.current` includes the cgroup and descendants | It is not process-only RSS | Keep a separate labelled field |
| [Python 3.12 GC](https://docs.python.org/3.12/library/gc.html#gc.callbacks) | GC supplies start/stop phase, generation, and stop-phase collected/uncollectable information | It supplies no pause duration; V8 clock calls are an added observer and unmatched phases are possible | Predeclared callback profile, exact pairing/bracketing, no GC mutation |
| [Python 3.12 `collections.deque`](https://docs.python.org/3.12/library/collections.html#collections.deque) | A bounded deque discards from the opposite end when full | It neither preserves the first element nor supplies V8 identity/loss proofs | Mechanism context only; V8 implements and tests its own first-plus-tail ring |
| [Linux perf ring buffer](https://www.kernel.org/doc/html/latest/userspace-api/perf_ring_buffer.html) and [OpenTelemetry tracing SDK](https://opentelemetry.io/docs/specs/otel/trace/sdk/) | Bounded telemetry can lose records and loss counts must remain visible | Neither source validates V8's particular ring or trading transport | Explicit retained/dropped accounting and partial-series status |

These sources support mechanism semantics and known limitations. They do not
show that a 4,096-marker ring is sufficient, that this instrumentation is
neutral, that any threshold is safe, or that the trading system has edge.
Those are repository-specific hypotheses requiring the acceptance matrix and
later matched campaigns.

## 20. Explicit nonclaims and next gate

Even after Raw V8 acceptance, it will not establish:

- accepted Raw V7 unless Raw V7 passed independently first;
- complete marker evidence after process loss;
- simultaneous cross-layer state or an unseen in-operation peak;
- zero observer effect or accepted physical alpha-normalization;
- full matched neutrality, campaign isolation, or immutable publication;
- independently finalized correctness or a replayable PASS;
- calibrated/confirmed numeric low, high, hard, age, latency, byte, work, or
  parser-quantum values;
- A2-E pressure transitions, read pausing, parser continuation, overload
  terminal enforcement, or a safe WebSocket Close policy;
- bounded actor history, rebuild complexity, or memory (A3);
- concurrently open measured commands or a same-session contention campaign;
- multi-session capacity/fairness (B);
- external/build/host attestation or crash-surviving live TLS/socket state;
- provider conformance, public live-factory authority, paper/live trading
  safety, predictive accuracy, economic edge, profitability, or Stage 1 exit.

Historical V4.9C actor records may contain absolute monotonic integers under
their existing schema. Raw V8 embeds their exact canonical bytes and does not
silently reinterpret or repair a historical long-uptime I-JSON limitation.
Any migration of those actor fields requires its own new actor schema and
compatibility review.

The immediate gate after accepted Raw V8 is the reviewed physical event-field
normalizer plus fixture-level deterministic OFF/OFF, ON/ON, and OFF/ON oracles.
Only after that may work proceed to independent evidence-derived correctness
finalization, campaign isolation, and atomic publication. Complete matched
neutrality/overhead and frozen workload campaigns run through those accepted
surfaces. Numeric calibration, independent confirmation, signed thresholds,
and enforcement remain later and separate.
