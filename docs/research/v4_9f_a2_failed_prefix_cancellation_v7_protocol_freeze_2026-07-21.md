# V4.9F-A2 Failed-Prefix and Cancellation Raw V7 Protocol Freeze

**Design-freeze date:** 2026-07-21

**Implementation reconciliation:** 2026-07-22

**Status:** Design frozen, implemented, and locally accepted on 2026-07-22.
Every test and audit in Section 13 passed against one post-format stable tree,
as reconciled in the independent acceptance audit. No accepted durable external
artifact, public-live qualification, A2-M completion, or Stage 1 exit is claimed
by this document.

**Accepted implementation boundary (2026-07-22):** the canonical V7 manifest,
authority/expectation, production collector and one-shot signer, lifecycle
records, integrated measurement runner, startup recovery, receipt-complete
prefix, returned-progress reconstruction, strict four-member codec, offline
replay, projection fault matrix, cancellation/interruption matrix, and
unsigned-suffix trust-ceiling disclosure all have direct evidence. Raw V7 still
does not implement independent correctness finalization, signed post-run
provenance, durable external publication, or physical neutrality campaigns.

**Roadmap position:** Stage 1 critical corrections, inside V4.9F-A2-M Step 2,
after the locally accepted Raw V6 observed-authority sub-gate and before stable
in-operation markers, non-ingress operations, complete A2 target fields,
physical normalization, neutrality, independent finalization, campaign
isolation, atomic external publication, calibration, or enforcement.

**Parent protocol:**
[`v4_9f_a2_measurement_and_enforcement_protocol_freeze_2026-07-20.md`](v4_9f_a2_measurement_and_enforcement_protocol_freeze_2026-07-20.md)

**Accepted predecessor:**
[`v4_9f_a2_authoritative_manifest_v6_protocol_freeze_2026-07-21.md`](v4_9f_a2_authoritative_manifest_v6_protocol_freeze_2026-07-21.md)

## 1. Decision and narrow authority ceiling

The Raw V7 measurement schema is:

```text
riskyieldmm_physical_transport_a2m_raw_v49f_v7
```

It freezes these exact profiles:

```text
operation_lifecycle_profile = DURABLE_PRE_EFFECT_ATTEMPT_EXACTLY_ONE_TERMINAL_V1
failed_prefix_profile       = EXACT_ACTOR_DELTA_WITH_RAW_DEPENDENCIES_V1
cancellation_profile        = PROPAGATE_AFTER_SYNCHRONOUS_TERMINAL_V1
orphan_recovery_profile     = RECONCILE_BEFORE_NEXT_RUNTIME_COMMAND_V1
```

Raw V7 closes one specific Raw V6 gap: a started measured ingress operation no
longer disappears merely because it raises or receives cancellation after
partial durable effects. The protocol requires:

1. one canonical operation-attempt receipt committed before the target ingress
   effect starts;
2. one and only one canonical terminal receipt for that attempt;
3. an exact journal-derived actor delta and every referenced RAW dependency;
4. distinct returned, exception, cancellation, interruption, and restart-
   recovery terminal classes;
5. synchronous terminal persistence before a delivered `CancelledError` is
   re-raised; and
6. startup reconciliation of any durable attempt whose same-task terminal was
   interrupted by process loss.

The protocol records local durable causality. It does not prove peer receipt,
remote application, exchange acknowledgement, filesystem survival after total
storage loss, or immutable external publication. It also does not make the
measurement observer neutral; neutrality remains a later matched-campaign
gate.

## 2. Raw V6 and Raw V7 are different evidence domains

Raw V7 does not reinterpret, mutate, hydrate, or automatically upgrade Raw V6.
The separation is normative:

- Raw V6 codecs continue to admit only exact Raw V6 top-level records and
  reject Raw V7.
- Raw V7 codecs admit only exact Raw V7 top-level records and reject a Raw V6
  artifact presented as V7; only the explicitly typed predecessor field is
  delegated to the unchanged V6 decoder.
- Raw V7 mints a new campaign-manifest identity and a new domain-separated
  manifest-authority signature.
- The Raw V7 signed subject binds the Raw V7 schema, the four fixed profiles
  above, and the exact accepted observed-authority predecessor identity.
- The complete verified Raw V6 manifest is embedded as a self-contained typed
  predecessor inside V7 `manifest.json`; a hash-only external reference is
  forbidden.
- The nested V6 mapping is therefore physically part of the outer V7 bytes,
  but it is reconstructed by the unchanged V6 decoder. V6 bytes never acquire
  V7 semantics, and the V6 signature cannot authorize V7 profiles.
- No historical Raw V6 sample can acquire an attempt, terminal, cancellation,
  failed-prefix, finalization, publication, or promotion claim after the fact.

The V7 manifest-authority signature remains direct, fixed-domain Ed25519, with
the same observed-local trust ceiling as Raw V6. The new signed subject prevents
an otherwise valid V6 authority from being relabelled as permission for the V7
lifecycle profiles.

### 2.1 Self-contained manifest composition

The exact outer composition is:

```text
CapacityMeasurementManifestV49FV7
  predecessor_manifest_v6: CapacityMeasurementManifestV49F
  source_inventory: CapacityMeasurementSourceInventoryV49FV7
  lifecycle_contract: CapacityMeasurementLifecycleContractV49FV7
  projection_authority: CapacityMeasurementProjectionAuthorityV49FV7
  actor_baseline: CapacityMeasurementActorBaselineV49FV7
  manifest_authority_v7: CapacityMeasurementManifestAuthorityV49FV7
  campaign_manifest_id
```

The V6 predecessor is decoded and independently verified under its unchanged
Raw V6 contract before V7 validation proceeds. Nesting reuses its hardened
workload, design, source, runtime, process/environment, session, policy, clock,
and observed-authority graph without duplicating those fields into a second
caller-asserted schema. The outer V7 manifest cross-links every predecessor and
new-component identity. A V5 predecessor, a reference without embedded bytes,
a mutated V6 mapping, or an outer/predecessor authority mismatch rejects.

The V7 domains are distinct and exact:

```text
riskyieldmm_physical_transport_a2m_raw_v49f_v7
RiskYieldMMA2MManifestV4_9F_RawV7
RiskYieldMMA2MManifestAuthoritySubjectV4_9F_RawV7
RiskYieldMMA2MManifestAuthorityAttestationV4_9F_RawV7
RiskYieldMMA2MLifecycleSampleV4_9F_RawV7
RiskYieldMMA2MCorrectnessV4_9F_RawV7
RiskYieldMMA2MIntegrityV4_9F_RawV7
```

### 2.2 Source-inventory revision and V7 signing authority

The historical Raw V6 checkpoint retains its exact 40-module inventory and
continues to decode only under Raw V6. It is **not** a valid embedded V7
predecessor. A V7 collection creates a fresh V6-schema predecessor in the same
collection session, runtime, projection, and source-observation authority as
the outer V7 manifest. That predecessor carries the current exact 41-module
source closure, including
`riskyieldmm.trading.physical_transport_capacity_lifecycle_v49f`, under exactly
one `CRITICAL_MODULE:<module>` and one `LOADED_MODULE:<module>` role per module.
Unknown roles, aliases, duplicates, missing roles, and the historical 40-module
closure all reject under V7.

`CapacityMeasurementSourceInventoryV49FV7` is a compact, versioned declaration
of those 41 names and their new inventory ID. It references the frozen V6
inventory ID as its predecessor; it does not duplicate the observed source
snapshot bytes. The only source snapshot is already embedded in the nested
predecessor, and the outer V7 authority binds that snapshot's identity,
observed tree, and release tree. This prevents two drifting source-byte graphs
inside one manifest while preserving byte-exact historical V6 decoding.

Removing, adding, renaming, alias-loading, filelessly loading, or substituting
the lifecycle module must reject. Source-observer tests which intentionally
load different module sets run in isolated processes; the live observer's
rejection of every extra loaded `riskyieldmm` module remains intentional rather
than being weakened to make test ordering convenient.

V7 uses a second exact one-shot signing authorization; it never reuses the V6
authorization token or signature. The new signing input has this fixed outer
shape:

```text
canonicalization_version
domain = RiskYieldMMA2MManifestAuthoritySubjectV4_9F_RawV7
payload:
  authority_subject_id
  base_observed_authority_id
  predecessor_manifest_id
  predecessor_manifest_authority_id
  v7_source_inventory_id
  v7_source_observation_id
  v7_source_tree_sha256
  v7_release_source_tree_sha256
  lifecycle_schema_id
  projection_ledger_id
  projection_schema_version
  projection_validation_version
  projection_schema_fingerprint
  actor_baseline_id
  collector_attestation_key_id
  deployment_bundle_id
  transport_session_id
  operation_lifecycle_profile
  failed_prefix_profile
  cancellation_profile
  orphan_recovery_profile
schema_version = riskyieldmm_physical_transport_a2m_raw_v49f_v7
```

`base_observed_authority_id` is the exact independently verified observed-local
predecessor authority, not an embedded self-selected key treated as trust. The
signed payload contains `authority_subject_id`; that identity in turn commits
the complete subject, including the inventory-record identity, lifecycle-
contract identity, projection-authority identity, projection ledger, schema
version, validation version, fingerprint, baseline receipt anchor, actor
baseline, predecessor relationship, transport session/driver/socket/A1 policy,
three clock origins, collector release/key, deployment identities, and four
profiles. The V7 public key must equal both the nested V6 authority key and the
independently admitted deployment key. Projection genesis is exact:
`baseline_receipt_sequence == 0` if and only if
`baseline_receipt_hash == 64 * "0"`.

The actor baseline commits the full transport authority surface, RAW sequence
and tail, actor count and tail, the complete `WebSocketParserCursorV49C` body
and its derived ID, one value from the frozen runtime-state enum, and the
projection baseline sequence/hash. A cursor ID without its state, an aliased
runtime state, or a projection anchor outside the signed projection authority
rejects.

As in V6, direct domain-separated Ed25519 is not DSSE, in-toto, SLSA
provenance, or external host attestation; offline acceptance still requires an
independently admitted deployment-static expectation.

The V7 signature authenticates the preregistered manifest subject and starting
authorities; it does not sign each post-run attempt, terminal, sample, or final
receipt root. The receipt chain detects omission, reordering, or replacement
only when a separately trusted final receipt root is available for comparison.
Raw V7 has no such final-result signature or external anchor. Consequently, an
offline editor can construct a different semantically self-consistent suffix
from the public signed baseline and recompute its receipts, sample roots,
correctness identity, and unsigned integrity member without the signing key.
The retained in-process campaign/runner capability prevents that substitution
during local construction, but the four serialized members alone prove only
manifest authenticity plus suffix self-consistency. Independent finalization,
immutable publication, and a signed or external final-result anchor remain
later gates.

## 3. Causal lifecycle

### 3.1 Normative state machine

For each measured operation which reaches the durable attempt boundary after
the started A1 ingress grant and orchestration ownership:

```text
NO RECORD
  -> ATTEMPT_DURABLE
  -> TERMINAL_DURABLE

ATTEMPT_DURABLE
  -> process/storage interruption before same-task terminal
  -> OPEN_ATTEMPT_DISCOVERED_AT_STARTUP
  -> RECOVERY_TERMINAL_DURABLE
```

There is no transition back to `NO RECORD`, no mutation of an attempt into a
terminal, and no retry of an orphaned physical effect. A later operation is a
new operation sequence with a new attempt identity.

The exact ordering for an ordinary entered operation is:

```text
A1 admission reaches STARTED
-> runtime owns orchestration boundary
-> exact actor/parser/runtime before coordinates captured
-> attempt + projection receipt + typed row + open locator COMMIT
-> target ingress effect may begin
-> exact durable actor/RAW prefix and runtime terminal facts captured
-> terminal + projection receipt + typed row + locator deletion COMMIT
-> ordinary return / original exception / original cancellation propagation
```

The durable attempt therefore precedes the target transport effect, not the A1
queueing history already embedded in the attempt. Cancellation or fatal
interruption before attempt commit creates no fake attempt. This includes
cancellation before admission and the narrow interval after an A1 grant while
waiting for orchestration ownership. The A1 counters must still reflect their
true lifecycle, while the execution has no new Raw V7 operation record. Such a
short execution is not automatically an admissible artifact; Section 10's
locally committed last-terminal rule controls.

### 3.2 Exactly-one terminal invariant

For a retained attempt `a`:

```text
terminal_count(a) in {0, 1}
terminal_count(a) == 0  <=>  a is the one open attempt for its session
terminal_count(a) == 1  <=>  no open locator exists for a
```

Zero terminals is an explicitly unresolved on-disk state, not a completed
empty operation. More than one terminal is corruption. The publishable Raw V7
invariant is stronger:

```text
every retained attempt selected for the artifact has exactly one terminal
and no selected session has an open attempt
```

This is a database and artifact invariant. It is not a guarantee against loss
of the entire database, its directory, or its underlying storage.

## 4. Integrated retained projection database

Raw V7 extends the existing authoritative physical-projection SQLite database;
it does not introduce an independent sidecar database. The required SQLite
profile remains:

```text
journal_mode = DELETE
synchronous  = EXTRA
transaction  = BEGIN IMMEDIATE
```

The two new canonical receipt-chained record kinds are:

```text
CAPACITY_MEASUREMENT_OPERATION_ATTEMPT_V49F_V7
CAPACITY_MEASUREMENT_OPERATION_TERMINAL_V49F_V7
```

Their exact domain types are:

```text
CapacityMeasurementOperationAttemptV49F
CapacityMeasurementOperationTerminalV49F
```

The noncanonical, exactly reconstructed read result is:

```text
CapacityMeasurementOperationPrefixV49F
```

The strict typed tables are:

```text
capacity_measurement_operation_attempts_v49f
capacity_measurement_operation_terminals_v49f
capacity_measurement_open_attempts_v49f
```

The first two tables, their canonical records, and their receipts deny
`UPDATE` and `DELETE`. The third is a mutable locator, not evidence: its
session key permits at most one open attempt per transport session, it denies
`UPDATE`, and only the store-owned terminal transaction may delete it.

Attempt insertion is one transaction containing:

```text
canonical attempt record
+ receipt-chain append
+ typed attempt row
+ open-attempt locator
```

Terminal insertion is one transaction containing:

```text
canonical terminal record
+ receipt-chain append
+ typed terminal row
+ exact matching open-locator deletion
```

The typed constraints require a unique attempt ID, unique
`(campaign_manifest_id, operation_sequence)`, one terminal per attempt through
`UNIQUE(attempt_id)`, strict foreign keys, and exact nullable/non-nullable
coordinate combinations for each terminal class. A replayed exact duplicate
may be recognized as the same canonical record; a conflicting duplicate,
foreign link, skipped predecessor, or unmatched locator faults closed.

The projection schema version and fingerprint must change. A database created
under the pre-V7 schema is rejected by a V7 runtime. There is no implicit SQL
migration or evidence conversion.

Measurement lifecycle records are **not** transport-actor events. Injecting
observer events into the actor chain would alter the system under measurement,
make the actor delta self-referential, and weaken later neutrality analysis.

### 4.1 Frozen neutrality-baseline decision

Keeping lifecycle records out of the actor event-kind union does not make their
cost or identity effects disappear. Attempt and terminal writes extend the
projection's global receipt sequence/hash, consume SQLite writer time, and may
therefore change downstream receipt-bound RAW/actor identities and timing
relative to Raw V6 or any no-lifecycle route.

Raw V7 consequently defines lifecycle journaling as an **always-on benchmark-
harness safety baseline** in every later V7 neutrality arm:

```text
V7 BASELINE  = lifecycle attempt/terminal journal ON, resource probes OFF
V7 MEASURED  = lifecycle attempt/terminal journal ON, resource probes ON
```

OFF/OFF replication, ON/ON replication, and OFF/ON comparisons in later A2-M
work toggle only the resource/marker/probe instrumentation layered above this
fixed V7 lifecycle baseline. They never compare V6/no-lifecycle identities to
V7/lifecycle identities and never claim literal byte, receipt-root, or timing
equivalence across those protocols.

This choice makes exception/cancellation accounting structurally available in
every V7 arm, but it does not prove that lifecycle overhead is acceptable for
production. The existing public legacy ingress method remains unchanged for
this sub-gate. V7 uses a measurement-only runtime entry point; production-route
adoption requires a later explicit protocol, overhead evidence, regression
review, and promotion decision.

## 5. Canonical operation attempt

`CapacityMeasurementOperationAttemptV49F` is immutable intent plus the exact
started boundary. Its semantic fields are frozen as follows.

### 5.1 Campaign, sequence, and physical authority

```text
campaign_manifest_id
manifest_authority_id
measurement_design_id
declaration_id
operation_sequence
previous_operation_terminal_id
transport_session_id
driver_evidence_nonce_sha256
kernel_socket_identity
transport_capacity_policy_id
projection_ledger_id
projection_schema_version
projection_validation_version
projection_schema_fingerprint
projection_store_observation_id
writer_fence_token_sha256
writer_fence_generation
pre_attempt_receipt_sequence
pre_attempt_receipt_hash
retained_raw_dependencies
initial_pending_ingress_present_before
```

`operation_sequence` starts at one and is gap-free within the campaign/session
chain. `previous_operation_terminal_id` is absent only for the first operation
and otherwise equals the immediately preceding terminal. A session with an
open attempt cannot admit a new measured attempt. Each retained pending-RAW
source is represented by an attempt-time identity/content/receipt witness; the
final prefix carries the exact `RawIngressCommitV4` bytes needed to satisfy
that witness. `initial_pending_ingress_present_before` is an exact boolean used
to reconstruct whether returned ingress consumed pre-attempt retained bytes.

### 5.2 Workload and schedule coordinates

```text
workload_id
workload_sha256
sample_sequence
trial_index
repetition_index
is_warmup
stage
operation = INGRESS
timeout_seconds
```

Every value is derived from the frozen V7 manifest and deterministic schedule.
The caller cannot substitute a different workload, phase, timeout, or operation
kind after admission. Artifact replay recomputes the entire attempt declaration
from the signed workload and deterministic schedule: design, workload identity,
sample/operation/trial/repetition/warmup coordinates, stage, operation, input
chunk/octet/hash commitments, RAW-batch commitment, timeout, and expected-
output count/hash must all agree exactly.

### 5.3 Exact input and expected-output commitments

```text
input_chunk_count
input_octet_count
input_sha256
raw_ingress_batch_sha256
expected_output_frame_count
expected_output_frames_sha256
```

The input count, octet count, ordered-chunk commitment, and exact RAW-batch
commitment are independently recomputed from the workload. Expected output is
an oracle commitment used by the runner; it is never evidence that output was
actually prepared, sent, accepted, or completed. A returned output/oracle
mismatch may make the trial fail, but it must not erase or reject otherwise
valid RAW, parser, actor, dispatch, or terminal evidence. The evidence codec
reconstructs and checks the internal consistency of the serialized outcome; it
does not authenticate issuance of the unsigned post-run suffix. Correctness
evaluation separately decides whether that reconstructed outcome matched the
preregistered oracle.

### 5.4 Full A1 admission grant

The attempt embeds the exact `TransportCapacityPolicyV49F` and these exact
started-grant fields:

```text
admission_policy_id
admission_epoch
admission_sequence
admission_command_kind
admission_reservation_work_units
admission_admitted_loop_time_ns
admission_started_loop_time_ns
admission_start_deadline_loop_time_ns
admission_queue_wait_nanoseconds
```

`admission_command_kind` is `INGRESS`; the policy and top-level policy identity
must agree. Queue wait is derived exactly as `started - admitted`, never
accepted as an independent caller value. The origin and three absolute
admission-clock values are canonical unsigned 128-bit decimal text so a valid
monotonic timestamp can exceed the I-JSON integer range without lossy
serialization.

### 5.5 Before coordinates and attempt time

```text
baseline_raw_ingress_sequence
baseline_raw_ingress_commit_id
baseline_actor_event_count
baseline_actor_tail_event_id
parser_cursor_before
parser_cursor_id_before
runtime_state_before
observer_start_offset_nanoseconds
boottime_start_offset_nanoseconds
loop_time_start_offset_nanoseconds
loop_time_origin_nanoseconds
started_at
started_monotonic_ns
monotonic_clock_domain_id
attempt_id
```

The RAW tail, actor count/tail pair, complete parser cursor body plus derived
ID, and exact frozen runtime-state value are captured under the runtime's
orchestration boundary before the target ingress effect. Relative offsets stay
within the I-JSON safe-integer range; absolute `loop_time_origin_nanoseconds`
and `started_monotonic_ns` are canonical uint128 decimal text. `attempt_id` is
the canonical identity of the complete attempt; it is not caller supplied.

## 6. Canonical operation terminal

`CapacityMeasurementOperationTerminalV49F` is immutable and links one exact
attempt. It contains:

### 6.1 Terminal classification

```text
attempt_id
previous_operation_terminal_id
terminal_writer
terminal_trigger
cancellation_classification
effect_certainty
progress_availability
progress_unavailable_reason
operation_error_code
surfaced_exception_class
exception_class_chain
exception_message_sha256_chain
```

The closed enums are:

```text
terminal_writer:
  SAME_TASK
  STARTUP_RECOVERY

terminal_trigger:
  RETURNED
  RAISED_EXCEPTION
  CANCELLED
  INTERRUPTED
  RECOVERED_ORPHAN

cancellation_classification:
  NONE
  ASYNCIO_CANCELLED_ERROR
  PROCESS_LOSS_UNKNOWN

effect_certainty:
  NO_DURABLE_EFFECT
  EXACT_COMPLETED_PREFIX
  COMPLETE
  UNKNOWN

progress_availability:
  EXACT_RETURNED_PROGRESS
  EXACT_DURABLE_PREFIX
  UNAVAILABLE
```

`RETURNED`, `RAISED_EXCEPTION`, `CANCELLED`, and `INTERRUPTED` are written by
`SAME_TASK`. `RECOVERED_ORPHAN` is written only by `STARTUP_RECOVERY` and uses
`PROCESS_LOSS_UNKNOWN`. A delivered `asyncio.CancelledError` uses `CANCELLED`
and `ASYNCIO_CANCELLED_ERROR`. `KeyboardInterrupt`, `SystemExit`, or another
non-cancellation `BaseException` is `INTERRUPTED`, is terminalled synchronously
where execution remains possible, and is then propagated rather than converted
into an ordinary measurement result.

Effect certainty and progress availability are independent of the Python
terminal cause. `COMPLETE` requires a returned result which independently
equals durable replay. `EXACT_COMPLETED_PREFIX` means that the locally durable
causal prefix is exact but the requested operation did not complete.
`NO_DURABLE_EFFECT` means the target actor/RAW delta is provably empty; it does
not generalize into a peer-observation claim. An unresolved kernel attempt or a
process-loss window is `UNKNOWN`, never zero. `UNAVAILABLE` requires a bounded
reason and cannot carry a fabricated prefix or returned-progress identity.

The surfaced class is a bounded qualified class name. Exception causality and
context are retained as bounded class and message-digest chains; arbitrary
exception message text is not serialized. A digest is an integrity commitment,
not a confidentiality guarantee for guessable messages.

### 6.2 After coordinates and terminal authority

```text
terminal_raw_ingress_sequence
terminal_raw_ingress_commit_id
terminal_actor_event_count
terminal_actor_tail_event_id
parser_cursor_id_after
runtime_state_after
actor_terminal_state_id_after
actor_terminal_outcome
actor_terminal_cause_code
session_terminal_authority
```

The closed authority enum is:

```text
DURABLE_ACTOR_TERMINAL
VOLATILE_RUNTIME_FAULT_LATCHED
NONTERMINAL_RUNTIME
UNAVAILABLE_AFTER_ORPHAN
```

These values must not be collapsed. A runtime fault latch is not promoted to a
durable actor terminal; a nonterminal runtime is not called clean; restart
recovery does not invent volatile state that was never durably observed. An
orphan terminal retains provable durable RAW/actor coordinates, but its
`runtime_state_after`, observer/boottime/loop end offsets, and
`completed_monotonic_ns` are all null. Those volatile facts cannot be recovered
after process loss.

### 6.3 Prefix, returned progress, terminal time, and identity

```text
recovered_prefix_id
returned_progress_evidence_id
observer_end_offset_nanoseconds
boottime_end_offset_nanoseconds
loop_time_end_offset_nanoseconds
completed_at
completed_monotonic_ns
terminal_id
```

`recovered_prefix_id` commits the exact reconstruction described in Section 7.
`returned_progress_evidence_id` exists only when the legacy ingress call
returned progress. The runner must independently derive progress from the
durable prefix and require exact equality; returned in-memory lists never
override the journal. A mismatch is an error, not PASS.

The terminal identity commits every field above. Same-task terminal end
offsets cannot precede the attempt's corresponding start offsets.
`completed_monotonic_ns` is canonical unsigned uint128 decimal text; relative
offsets remain I-JSON-safe integers. UTC is retained for audit correlation but
does not replace monotonic ordering.

## 7. Exact failed-prefix semantics

### 7.1 Prefix definition

For attempt `a`, let its durable before anchor be `(n0, h0)` and terminal
coordinates be `(n1, h1)`. The exact actor delta is:

```text
actor_events[n0:n1]
```

only after canonical replay proves that `h0` is the tail at `n0`, `h1` is the
tail at `n1`, every event is gap-free and hash-linked, and every event belongs
to the same session, store, writer fence, and attempt boundary.

`CapacityMeasurementOperationPrefixV49F` contains that compact canonical actor
delta, the exact ordered union of every `RawIngressCommitV4` referenced by a
RAW actor event, parser slice, or retained attempt-time witness, and the
contiguous projection-receipt **and canonical-record** span from the attempt
receipt through the terminal receipt. `new_raw_ingress_commits` is a subset of
that complete `raw_dependencies` union; it is not a second dependency root and
must not be hashed twice by artifact aggregation. Actor events alone are
insufficient: their RAW payload commits identities and hashes, not the exact
decrypted RAW bytes. RAW/actor records without receipts are also insufficient:
they cannot prove that the attempt preceded the target records or that the
terminal closed the same global-ledger prefix.

Prefix identity uses two domains to avoid a terminal/self-receipt hash cycle:

```text
recovered_prefix_id = pre-terminal attempt/RAW/actor/receipt/record subject
prefix_id           = final export subject including terminal and terminal receipt
```

The terminal commits `recovered_prefix_id`; the sample and artifact commit the
final `prefix_id`. Treating them as aliases or accepting either under the
other domain rejects.

The loader is a strictly read-only projection operation. It validates process,
thread, event loop, store instance, writer fence, database identity, and bound
session authority. Postmortem loading deliberately does not require the old
socket to remain open, because ordinary error/cancellation cleanup may already
have aborted it. It mints no actor/RAW capability, performs no transport
recovery, and appends no actor event.

Offline replay of the reconstructed prefix must prove all of the following:

1. the attempt receipt follows the declared pre-attempt receipt anchor;
2. RAW records are gap-free from the attempt baseline, including previous-RAW
   links and exact workload bytes;
3. actor events are gap-free and hash-linked from the exact actor baseline;
4. every record retains the exact session, driver, socket, store, writer-fence,
   capacity-policy, and projection-ledger authority;
5. every RAW actor event resolves to exactly one embedded RAW record, with no
   missing, duplicate, or foreign dependency;
6. projection receipts are contiguous from attempt through terminal with no
   unexplained receipt sequence or predecessor hash;
7. every canonical record is strict-decoded through the authoritative
   projection record-kind registry and its bytes, identity, and content hash
   replay exactly;
8. terminal coordinates equal the final reconstructed RAW and actor tails;
9. returned progress, when present, is derived from and exactly equals durable
   replay;
10. effect certainty and progress availability are derived rather than trusted
   as terminal aliases; and
11. an unresolved kernel attempt forces `UNKNOWN`, while a positive local byte
    count never becomes peer delivery.

### 7.2 What “completed prefix” means

The prefix is the exact **locally durable causal prefix**. It does not mean
that all bytes in it reached the peer. For each automatic output obligation,
replay preserves these distinct stages:

```text
PARSER_OUTPUT_COMMITTED
-> WEBSOCKET_WIRE_PREPARED
-> WRITE_PERMIT_CONSUMED
-> TLS_CIPHERTEXT_PREPARED
-> KERNEL_SEND_ATTEMPT_UNRESOLVED
-> KERNEL_SEND_RESOLVED_ZERO
   or KERNEL_SEND_RESOLVED_PARTIAL_POSITIVE
   or KERNEL_SEND_RESOLVED_FULL_WITHOUT_DISPATCH
-> DISPATCH_COMPLETED
```

The stages are evidence classifications over existing actor records, not new
actor events. In particular:

- parser output or prepared wire is an obligation, not a send;
- a consumed permit is authorization, not a syscall result;
- prepared TLS ciphertext is not kernel acceptance;
- an unresolved attempt is unknown and must never be reported as zero;
- a conclusive zero result is distinct from absence of evidence;
- a positive partial result retains the exact locally accepted byte count;
- full local kernel acceptance without dispatch completion is not a completed
  logical dispatch; and
- only `OUTBOUND_DISPATCH_COMPLETED` enters the completed logical-output
  summary.

Thus one completed Pong followed by a parser failure reports exactly one
completed Pong plus the later failed causal suffix. It is neither “output
unavailable” nor an empty output. The protocol never claims peer delivery,
exchange processing, or remote durability.

### 7.3 Availability and uncertainty

The prefix is derived from durable records, not from `actor.events`, mutable
progress arrays, a caught exception's text, or a missing return value. Returned
progress is reconstructed field-by-field from durable evidence: grant offsets,
RAW identity/bytes/batch, parser event IDs and final state, automatic wire and
dispatch lineage, actor counts/tails, retained octets, and whether initial
pending ingress existed. If the required before anchor, actor suffix, RAW
dependency, output lineage, terminal coordinate, or database identity cannot
be established exactly, the operation is not accepted as an exact prefix.
Restart recovery records the uncertainty; it does not substitute an empty
prefix.

## 8. Cancellation and interruption

Python cancellation is cooperative and is delivered by raising
`asyncio.CancelledError` in the task. Raw V7 therefore freezes this order once
an attempt is durable:

```text
catch asyncio.CancelledError explicitly
-> capture the already durable prefix and truthful terminal state
-> synchronously commit CANCELLED terminal and delete open locator
-> perform no await, shielded task, or background finalizer
-> bare re-raise the original cancellation
```

The implementation must not call `Task.uncancel()`, replace cancellation with
an ordinary return, infer an application timeout merely from cancellation, or
allow the transport effect to continue behind `asyncio.shield()`. Repeated
cancellation cannot create a second terminal. A timeout owned by the runtime
must retain its own deadline evidence and must not be inferred from exception
wording.

The A1 context's existing synchronous release runs once as its context exits.
The persisted terminal, propagated task cancellation, exact admission grant,
and final A1 counters must agree. Cancellation before durable attempt commit
remains outside that attempt lifecycle; the deterministic run is a strict
execution prefix ending at its last complete attempt/terminal pair, but it is
not necessarily an admissible artifact under Section 10.

If terminal persistence itself fails, Raw V7 must not pretend cancellation was
successfully recorded. The durable attempt remains open when SQLite rolls back;
the runtime faults closed, the original `BaseException` remains causally
visible where possible, and startup recovery owns later reconciliation. No
best-effort in-memory terminal qualifies as evidence.

## 9. Startup orphan recovery

Before the next runtime command for a session, startup enumerates open-attempt
locators from the retained projection. For each open attempt it must:

1. verify the attempt, canonical receipt, typed row, open locator, campaign,
   session, writer fence, predecessor terminal, and sequence chain;
2. reconstruct any exact durable actor/RAW prefix which remains provable;
3. append exactly one `RECOVERED_ORPHAN` terminal with writer
   `STARTUP_RECOVERY` and cancellation class `PROCESS_LOSS_UNKNOWN`;
4. use `UNAVAILABLE_AFTER_ORPHAN` for volatile session-terminal authority that
   cannot survive process loss;
5. commit the recovery terminal and locator deletion atomically; and
6. fence the old physical session and never retry, resume, or duplicate the
   orphaned effect.

The recovery record means only that a durable attempt lacked its same-task
terminal. It does not prove that cancellation caused the interruption, that no
network effect occurred, or that a peer did not receive bytes after the last
local durable record. Any unresolvable effect remains unknown.

Recovery itself is idempotent only as the same canonical terminal. A different
terminal for the same attempt, a missing locator with no terminal, multiple
open attempts for one session, a locator for a terminalled attempt, or a
non-gap-free predecessor chain is corruption and faults closed.

The recovery terminal closes the retained projection lifecycle; it does not
recreate a lost in-memory campaign capability, one-shot signing authority, or
original manifest bytes. Unless those exact inputs also survive through a
separately accepted retention/publication path, the recovered operation is
locally auditable in the projection but is not eligible for construction of a
new four-member Raw V7 artifact after restart.

## 10. Runner, schedule prefix, and four-member artifact

Raw V7 retains the four-member logical artifact layout:

```text
v4_9f_a2_measurement/<evidence_bundle_id>/
    manifest.json
    samples.jsonl
    correctness.json
    integrity.json
```

The members decode only to these separate V7 classes:

```text
manifest.json     -> CapacityMeasurementManifestV49FV7
samples.jsonl     -> CapacityMeasurementSampleV49FV7
correctness.json  -> CapacityMeasurementCorrectnessV49FV7
integrity.json    -> CapacityMeasurementIntegrityV49FV7
```

The minimum sample composition is:

```text
CapacityMeasurementCommittedLifecycleRecordV49FV7
  record: CapacityMeasurementOperationAttemptV49F
          | CapacityMeasurementOperationTerminalV49F
  projection_receipt

CapacityMeasurementOperationPrefixV49F
  attempt
  terminal
  new_raw_ingress_commits
  raw_dependencies
  actor_events
  projection_receipts
  projection_records
  recovered_prefix_id
  prefix_id

CapacityMeasurementObservationV49FV7
  initial/before/after V6 runtime-boundary components
  before/in-operation/after V6 layer-snapshot components
  returned_ingress_progress: V6 progress component | null
  explicit availability reasons

CapacityMeasurementSampleV49FV7
  committed_attempt
  committed_terminal
  recovered_prefix
  observation
  sample_id
```

V7 may reuse exact V6 component types for runtime boundaries, layer snapshots,
and returned ingress progress, but it must not embed a complete V6 sample. V6's
full-schedule and successful-return parent-chain invariants cannot represent a
failed or cancelled final V7 schedule item safely.

Each Raw V7 sample embeds the exact committed attempt, exact committed
terminal, and exact reconstructed prefix. The sample cross-links the V7
campaign manifest, V7 manifest authority, workload/schedule coordinates,
attempt/terminal receipts, projection-ledger identity, prefix identity, and any
returned-progress identity. Codec replay reconstructs these exact domain
objects before accepting their semantic IDs.

The current admissible artifact rule is deliberately narrower than every
possible runner outcome. A four-member candidate is admissible only when it is:

1. the complete deterministic schedule; or
2. a non-empty contiguous schedule prefix whose **last embedded operation
   terminal is itself run-ending**.

The exact prefix rules are:

- every included schedule item has exactly one attempt and terminal;
- included coordinates start at the first item and are contiguous;
- no later item may appear after the first run-ending terminal;
- `CANCELLED`, `INTERRUPTED`, and `RECOVERED_ORPHAN` are run-ending;
- `RAISED_EXCEPTION` is run-ending only when the V7 manifest predeclares that
  exact bounded error class/code as fatal for the campaign;
- cancellation after attempt commit includes that item with `CANCELLED`;
- an orphan may be included only after its recovery terminal exists and only
  if the exact original manifest/signing context remains retained;
- a short prefix ending in `RETURNED` is inadmissible; and
- missing middle items, reordered items, duplicate operations, an empty sample
  stream, or a claimed complete schedule after an early terminal are rejected.

The signed lifecycle contract carries `fatal_operation_exceptions` as sorted,
unique `(operation_error_code, surfaced_exception_class)` pairs. A short prefix
ending in `RAISED_EXCEPTION` is run-ending only for an exact pair in that set.
An empty set is the fail-closed default: no raised exception can structurally
authorize a short schedule under signed manifest policy merely by matching one
half of the pair or an alias.

Cancellation/interruption before the first attempt, or between already
successful attempts before the next attempt commits, may still be represented
truthfully by task behavior and A1 diagnostics, but it produces **no admissible
Raw V7 artifact**. The last embedded terminal cannot encode or structurally
authorize a pre-attempt stop at the next schedule coordinate. Supporting those
cases requires a separately versioned, authenticated run-level termination
envelope which binds the campaign, exact next schedule coordinate, cause,
clocks, and sample-prefix root. That envelope is not part of this Raw V7 freeze
and must not be improvised as a correctness failure string.

Raw V7 persistence in the integrated projection is not the later artifact-
publisher gate. Until that gate exists, the four members may be constructed as
a bounded canonical in-memory closure only while the exact retained campaign
and signing context remain valid. They are not described as atomically
published or restart-safe filesystem artifacts, and projection recovery alone
cannot reconstruct a lost manifest authority. A publishable candidate must
contain no open selected attempt and must still possess the exact original V7
manifest bytes and admitted external expectation. Atomic temp-file publication,
directory `fsync`, rename/collision rules, external immutability, and
independent anchors remain future work.

Correctness remains provisional and uses a separate V7 class because V7 admits
the strict run-ending prefixes above. Every V7 correctness record must contain
both `CORRECTNESS_FINALIZER_NOT_IMPLEMENTED` and
`POST_RUN_SUFFIX_PROVENANCE_UNATTESTED`. Raw V7 does not derive the six
finalizer-owned claims or allow `passed = true`; it must not reuse V6
correctness by changing the meaning of V6 `observations_complete`. Removing
either mandatory disclosure rejects replay.

## 11. Frozen resource bounds

These are parser/storage safety limits, not measured transport capacity or
production thresholds:

| Surface | Bound |
|---|---:|
| Open measurement attempts per transport session | 1 |
| Terminal records per operation attempt | 1 |
| Exception cause/context chain depth | 8 |
| One exception class name | 256 UTF-8 bytes |
| One error/reason code | 128 UTF-8 bytes |
| Exact input chunks per ingress attempt | 128 |
| Exact input octets per ingress attempt | 65,536 |
| Ingress attempt timeout | 1 to 300 seconds |
| RAW dependencies in one reconstructed prefix | 64 |
| Compact actor events in one reconstructed prefix | 262,144 |
| Canonical reconstructed prefix | 48 MiB |
| Canonical operation attempt | 256 KiB |
| Canonical operation terminal | 256 KiB |
| V7 manifest JSON | 32 MiB |
| One V7 sample JSONL record | 64 MiB |
| V7 samples JSONL | 256 MiB |
| V7 correctness JSON | 4 MiB |
| V7 integrity JSON | 1 MiB |
| V7 four-member closure | 293 MiB |
| V7 trials / sample records | 100,000 |
| Identifier text | 256 UTF-8 bytes |
| Stage text | 128 UTF-8 bytes |
| V7 JSON nesting depth | 64 |
| V7 JSON object members per container | 512 |
| V7 JSON array elements per container | 524,288 |
| Sequence, count, and relative-offset integers | `0 .. 2^53 - 1` where nonnegative |
| Absolute monotonic/loop nanosecond values in lifecycle records | canonical uint128 decimal text |

Input bytes remain bounded by the existing Raw V6 durable-ingress/workload
limits. The numeric outer artifact limits intentionally equal V6's current
ceilings, but V7 applies them to separate V7 record classes and domains. Every
per-record/member/count bound is checked before untrusted parsing or nested-list
materialization.

Before strict JSON decoding, a byte-oriented, string/escape-aware lexical guard
applies those three JSON structure ceilings to each Raw V7 member, each V7
JSONL sample, each embedded predecessor workload manifest, and each base64
lifecycle projection record. It rejects with the stable reason codes
`V7_JSON_DEPTH_LIMIT_EXCEEDED`, `V7_JSON_OBJECT_MEMBER_LIMIT_EXCEEDED`,
`V7_JSON_ARRAY_ELEMENT_LIMIT_EXCEEDED`, or `V7_JSON_MALFORMED_STRUCTURE`.
[RFC 8259 Section 9](https://www.rfc-editor.org/rfc/rfc8259#section-9) permits a
JSON implementation to set limits on nesting depth and object/array size, and
the [Python 3.12 `json` implementation-limitations
documentation](https://docs.python.org/3.12/library/json.html#implementation-limitations)
likewise makes application-side resource limiting explicit. The values 64,
512, and 524,288 are frozen RiskYieldMM project operational ceilings; they are
not research-derived optima or performance claims.

The actor-event bound is deliberately a hard plausibility limit, not a claim
that retaining 262,144 actor events is performant. Later A3 incremental actor
work and measured V7 overhead must establish viable operating limits.

## 12. Designs considered

| Design | Decision | Reason |
|---|---|---|
| Keep Raw V6 “progress unavailable” on any raised ingress | Rejected | It loses already durable RAW/parser/output effects and can misclassify a nonempty prefix as empty or absent |
| Add nullable error fields to Raw V6 | Rejected | It changes accepted Raw V6 semantics without a new version/domain and cannot supply pre-effect lifecycle durability |
| Reuse a V6 signature or point to an external V6 manifest hash | Rejected | V6 did not authorize V7 profiles, and reference-only V7 would not be a self-contained four-member closure |
| Duplicate the complete V6 manifest schema into V7 | Rejected | It creates two drifting definitions of the already hardened observed-authority graph |
| Embed and independently revalidate one exact V6 predecessor under a new V7 outer authority | Frozen | It preserves V6 semantics while making the V7 closure self-contained and domain-separated |
| Return a sample only from the failed coroutine | Rejected | A raised/cancelled coroutine may return nothing while the actor journal already contains a durable prefix |
| Use mutable in-memory actor lists as authority | Rejected | A failed journal transaction can make memory and durable state disagree |
| Embed RAW/actor records without their projection receipts | Rejected | Offline replay could not prove attempt-before-effect order, receipt continuity, or terminal closure |
| Write measurement lifecycle records into the actor chain | Rejected | Measurement would change the causal actor delta it is trying to observe |
| Use a separate measurement SQLite database | Rejected | Cross-database ordering cannot atomically share the existing projection receipt chain or session writer fence |
| Update one mutable attempt row into “complete” | Rejected | It destroys the immutable attempt/terminal distinction and weakens crash diagnosis |
| Two canonical receipt-chained records plus one open locator in the existing projection | Frozen | It gives an immutable pre-effect fact, exactly-one terminal cardinality, and startup discoverability under one transaction authority |
| `asyncio.shield()` or a background finalizer | Rejected | Caller cancellation still occurs while the shielded effect may continue; weak task references and later cancellation make evidence timing ambiguous |
| Suppress cancellation after recording | Rejected | It changes Python task semantics and can make upstream structured-concurrency logic incorrect |
| Treat missing result as zero-byte effect | Rejected | Absence of a result is not evidence of zero kernel acceptance or no peer-visible effect |
| Retry an orphan after restart | Rejected | The earlier effect may have reached kernel or peer; retry can duplicate it |
| Claim atomic external publication now | Deferred | Projection durability is not the filesystem bundle-publisher and external-anchor protocol |

## 13. Acceptance matrix

Raw V7 was accepted only after every following current-tree test and audit
passed without weakening Raw V6 or public-runtime denials.

| Area | Required acceptance evidence |
|---|---|
| V7 source and authority | Fresh current exact-41 V6-schema predecessor in the same collection authority; exact `CRITICAL_MODULE:` and `LOADED_MODULE:` roles; compact V7 inventory record referencing the historical inventory; V7 inventory ID, projection schema/validation/fingerprint/baseline, full actor/parser baseline, profiles, and new one-shot V7 signature; historical exact-40 V6 fixture remains decode-only and byte-exact |
| Manifest composition | Self-contained exact V6 predecessor decodes under V6 and independent expectation; V5, reference-only, mutated predecessor, outer/predecessor key mismatch, and V6-signature replay under V7 domain reject |
| Projection schema | Strict schema/fingerprint bump; pre-V7 DB rejection; attempt and terminal canonical-record/receipt/typed-row consistency; exact locator constraints; denied mutation |
| Transaction faults | Fault injection before/after canonical record, receipt, typed row, locator insert/delete, commit, and rollback; only complete atomic states survive |
| Attempt ordering | Attempt receipt demonstrably commits before target ingress effect; exact grant/policy/before coordinates; no caller-forged operation sequence or predecessor |
| Successful ingress | Durable prefix independently reconstructs returned progress, RAW bytes, parser cursor/state, automatic wire/dispatch lineage, actor coordinates, retained bytes, grant attribution, and terminal runtime state; oracle mismatch is correctness evidence rather than grounds to discard valid physical evidence |
| Failure before RAW | Exact empty actor delta and no RAW dependency, with truthful exception/runtime state; never inferred merely from missing return |
| Failure after RAW | Exact RAW bytes and RAW actor record remain available when parser or later work raises |
| Partial parser/output | First completed Pong retained when a later parser unit fails; prepared-only output remains an obligation; completed-output count is exact |
| Send lifecycle | Unresolved attempt remains unknown; conclusive zero, partial positive, full local acceptance without dispatch, and dispatch completion remain distinct |
| Cancellation | Before-admission and grant-to-orchestration schedule prefixes; after-attempt cancellation at RAW/parser/output/send barriers; synchronous one terminal; bare re-raise; awaited task remains cancelled; A1 releases once |
| Repeated/racing cancellation | No second terminal, no `uncancel`, no shielded continuing effect, no timeout inference from cancellation, deterministic final prefix |
| Interruption | `KeyboardInterrupt`/`SystemExit` terminal where synchronously possible and then propagate; no ordinary PASS/ERROR conversion |
| Postmortem loading | Exact prefix reload succeeds after owner abort without minting capabilities or appending actor events; wrong anchor/store/session/writer fence/database identity rejects |
| Receipt-complete prefix | Attempt-to-terminal projection receipts and canonical records are contiguous and content-valid; every record strict-decodes through the projection registry; two-domain recovered/final prefix identities replay; unexplained/missing/reordered receipts, broken predecessor, wrong ledger, incomplete RAW union, RAW-to-actor mismatch, and foreign record splicing reject |
| Derived classifications | Effect certainty, progress availability, completed-output lifecycle, returned progress, and UNKNOWN are derived from replay; caller-selected aliases or UNKNOWN-to-complete relabelling reject |
| Orphan recovery | Startup enumerates each open attempt before another command, appends one recovery terminal, deletes locator atomically, fences old session, and never retries effect |
| Recovery uncertainty | Process loss after attempt, after RAW, after prepared output, and around terminal commit never becomes false empty/completed/peer-delivered evidence |
| Corruption/adversary | Reordered/dropped actor events, RAW substitution, false prefix ID, false returned progress, duplicate/conflicting terminal, locator contradiction, sequence gap, and foreign authority reject |
| Serialized trust ceiling | One admitted signed manifest can replay with two different internally valid, recomputed unsigned suffixes without another signer call; both remain provisional and the verifier reports self-consistency rather than post-run issuance authenticity |
| Bounds | Exception-chain, class-text, RAW-dependency, actor-event, 48 MiB prefix, 256 KiB attempt/terminal, 64 MiB record, 256 MiB samples, 293 MiB closure, count, integer, and nested JSON limits reject before unbounded work |
| Version separation | V6 rejects V7, V7 rejects V6, V6 signature cannot authorize V7 profiles, and no automatic manifest/sample/DB upgrade exists |
| Artifact closure | Every selected attempt has exactly one embedded terminal/prefix; a complete schedule or non-empty contiguous prefix ending in its own locally committed, runner-bound run-ending terminal; empty/unmarked short prefixes, open attempts, and samples after the run-ending terminal reject |
| Neutrality baseline | Every later V7 campaign arm keeps lifecycle journaling on; only higher probe layers toggle; reports prohibit V6/no-lifecycle versus V7/lifecycle byte/root equivalence claims |
| Public compatibility | Existing public legacy ingress signature, return/exception/cancellation behavior, and public `LIVE_LINUX` construction denial remain unchanged; V7 is measurement-only |
| Regressions | Existing Raw V6 manifest/source/runtime/codec suites, A1 admission, actor/projection, Linux owner, ingress, terminal, and unchanged public `LIVE_LINUX` denial pass |
| Static audits | Targeted Ruff format/lint, Python compilation, `git diff --check`, serialization-surface inventory, exact test-file inventory, and worktree-leftover review pass |

No partial row count or hand-selected happy-path test accepts the gate. Final
acceptance documentation must report disjoint test groups, exact current-tree
counts and timings, failure-injection coverage, and remaining nonclaims.

## 14. Primary-source synthesis and limitations

| Primary source | What it establishes | Limitation | Raw V7 use |
|---|---|---|---|
| [RFC 8032](https://www.rfc-editor.org/rfc/rfc8032) | It specifies Ed25519 signing and verification | A valid signature does not establish who should be trusted, what was observed, or whether a predicate is true | Use a fixed V7 semantic domain and exact subject; require the independently admitted deployment key rather than trusting the embedded key |
| [SLSA 1.2 artifact verification](https://slsa.dev/spec/v1.2/verifying-artifacts) | Verification binds authenticated provenance to a subject and checks the producer against configured expectations | It does not define RiskYieldMM's lifecycle, prefix, cancellation, SQLite, or network semantics | Independently verify the nested V6 predecessor and V7 signer/subject/profile expectations; do not treat a self-consistent closure as external authority |
| [in-toto Statement v1](https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md) | Explicit predicate types and immutable subject digests prevent semantic ambiguity between statement kinds | It does not make a predicate true and Raw V7 does not implement the in-toto envelope | Keep V6 and V7 domains/types distinct and forbid signature/schema relabelling without claiming in-toto conformance |
| [Python 3.12 task cancellation](https://docs.python.org/3.12/library/asyncio-task.html#task-cancellation) | `Task.cancel()` arranges for `CancelledError` to be raised cooperatively; `CancelledError` directly subclasses `BaseException`; cleanup belongs in `try/finally` and cancellation should normally propagate | It defines Python task behavior, not durable trading evidence, SQLite order, or network effect certainty | Catch cancellation explicitly, perform synchronous evidence cleanup, then bare re-raise; never infer that cancellation prevented all effects |
| [Python 3.12 `asyncio.shield`](https://docs.python.org/3.12/library/asyncio-task.html#asyncio.shield) | Shielding prevents caller cancellation from cancelling the inner awaitable while the caller still receives cancellation; tasks need strong references | It is not a durability or finalization protocol | Do not use shield as the primary terminal writer because effects may continue after caller cancellation |
| [Python 3.12 timeouts](https://docs.python.org/3.12/library/asyncio-task.html#timeouts) and [`wait_for`](https://docs.python.org/3.12/library/asyncio-task.html#asyncio.wait_for) | Timeout mechanisms cancel work and may wait beyond the nominal timeout while cancellation completes | They do not identify the project's causal deadline merely from an exception | Bind timeout claims to owned A1/runtime deadline evidence; keep cancellation classification separate |
| [SQLite transactions](https://www.sqlite.org/lang_transaction.html) | A write transaction serializes database changes and `BEGIN IMMEDIATE` starts write ownership immediately | It cannot make a socket effect and database transaction atomic | Put attempt/terminal rows, receipts, and locator mutations in exact local transactions; classify cross-boundary uncertainty honestly |
| [SQLite atomic commit](https://www.sqlite.org/atomiccommit.html) | SQLite documents its rollback-journal commit protocol and storage assumptions | Atomicity depends on OS/filesystem/device behavior and correct configuration | Use the existing retained projection transaction boundary, while explicitly excluding total-storage-loss guarantees |
| [SQLite `synchronous`](https://www.sqlite.org/pragma.html#pragma_synchronous) | `EXTRA` adds directory synchronization for rollback-journal unlink after commit | It is not remote replication, immutable publication, or proof against hostile storage | Retain `DELETE` + `EXTRA`; do not call local commit an external artifact publication |
| [SQLite WAL reset bug](https://sqlite.org/wal.html#the_wal_reset_bug) | SQLite documents a WAL reset corruption bug affecting versions 3.7.0 through 3.51.2 under particular concurrent write/checkpoint conditions | It does not imply rollback journal is infallible | Keep the frozen projection fail-closed against WAL for this gate; do not silently switch journal modes |
| [SQLite busy timeout](https://www.sqlite.org/c3ref/busy_timeout.html) | A busy handler may sleep repeatedly before returning `SQLITE_BUSY` | It does not make synchronous waiting cancellation-safe or latency-bounded | Foreign contention invalidates the campaign; measure blocking separately and do not hide it with async finalizers |
| [SQLite interrupt](https://sqlite.org/c3ref/interrupt.html) | `sqlite3_interrupt()` can cause pending operations on a connection to return `SQLITE_INTERRUPT`, with documented concurrency and transaction effects | It does not identify which transport effect occurred or provide an exactly-once terminal | Do not introduce cross-thread SQLite interruption as cancellation finalization; keep the owner-local synchronous transaction and recover a rolled-back open attempt later |
| [W3C PROV constraints](https://www.w3.org/TR/2013/REC-prov-constraints-20130430/#constraints-on-activities) | Provenance constraints distinguish generation, use, start, end, and ordering relationships | It does not define this evidence schema or prove physical effects | Use the ordering model only: attempt generation precedes target effect; terminal generation follows observation |
| [RFC 5848 signed syslog](https://www.rfc-editor.org/rfc/rfc5848.html) | Sequence and signature groups make missing/reordered records detectable within the stated threat model | It is not a substitute for the project's actor, RAW, or SQLite authority | Apply the limited sequence/predecessor lesson; do not claim RFC 5848 conformance |
| [RFC 9162 Certificate Transparency](https://www.rfc-editor.org/rfc/rfc9162.html#section-2.1.4) | Append-only Merkle trees provide consistency proofs between tree heads | A local tree without external witnesses can still be replaced wholesale | Keep receipt/prefix chains for local consistency; defer independent external anchoring |
| [CloudEvents 1.0.2](https://github.com/cloudevents/spec/blob/ce%40v1.0.2/cloudevents/spec.md) and [OpenTelemetry trace API](https://opentelemetry.io/docs/specs/otel/trace/api/) | They define interoperable event metadata and tracing APIs for observability | Neither format supplies project-specific causal truth, database durability, exactly-once effects, or an admitted trust root | They may mirror V7 status for monitoring later, but never replace canonical attempt/terminal records |
| [POSIX `rename`](https://pubs.opengroup.org/onlinepubs/9799919799/functions/rename.html) and Linux [`fsync`](https://man7.org/linux/man-pages/man2/fsync.2.html) | They define primitives needed for later atomic filesystem publication and durability ordering | Neither is implemented by an in-memory four-member mapping or implied by a SQLite commit | Reserve artifact publication, directory synchronization, and collision handling for the later publisher gate |

The measurement lifecycle remains project-specific canonical evidence, not an
observability event stream.

## 15. Explicit nonclaims

Even after Raw V7 acceptance, this sub-gate will not establish:

- stable bounded in-operation markers or their sampling overhead;
- complete non-ingress operation coverage;
- all A2 CPU, memory, kernel, TLS/BIO, parser, actor, SQLite, lag, and freshness
  target fields;
- measurement neutrality, matched OFF/OFF, ON/ON, and OFF/ON campaigns, or an
  accepted overhead budget;
- equivalence between V6/no-lifecycle and V7/lifecycle receipt roots, record
  identities, timing, or bytes;
- actor scalability or acceptable performance at the frozen parser bounds;
- peer delivery, exchange acknowledgement, remote durability, or exactly-once
  network effects;
- survival of total database/directory/device loss;
- an evidence-derived correctness finalizer or `passed = true`;
- serialized post-run issuance authenticity from the manifest signature alone;
- campaign isolation, atomic filesystem publication, restart-safe artifact
  collision handling, immutable object storage, transparency witnesses, or
  external attestation;
- exercised public `LIVE_LINUX` construction;
- frozen workloads, calibration, independent confirmation, numeric threshold
  selection, signed policy freeze, A2-E enforcement, A3 scaling, or
  multi-session fairness;
- provider conformance, paper/live trading safety, predictive edge,
  profitability, Stage 1 completion, or production readiness.

## 16. Implementation and acceptance sequence

The gate was implemented and reviewed in this order:

1. preserve historical exact-40 V6 decoding, define the compact exact-41 V7
   inventory, collect a fresh current exact-41 V6-schema predecessor under the
   same session/runtime/source authority, then add the self-contained V7
   manifest, domains, independent expectation, projection/actor/parser-baseline
   bindings, and second one-shot V7 signature;
2. extend the existing projection schema/fingerprint with the two canonical
   record kinds, typed tables, open locator, strict transactions, replay, and
   bounds;
3. add the read-only postmortem receipt/actor/RAW prefix loader without actor
   mutation;
4. add a measurement-only runtime entry point which preserves A1 and
   orchestration ordering, writes the attempt before target effect, captures
   exact returned/error/cancelled/interrupted closure, and leaves the existing
   public ingress method unchanged;
5. add startup orphan reconciliation before the next runtime command;
6. add receipt-complete sample/observation/prefix types, separate V7
   correctness/integrity, strict four-member codec, schedule-prefix rules, and
   V6/V7 mutual rejection;
7. run the complete acceptance matrix, focused regression groups, static
   audits, serialization inventory, and explicit leftover/worktree review; and
8. only then reconcile the parent A2-M protocol and roadmap with exact evidence
   and mark this Raw V7 sub-gate accepted.

All eight steps are complete. The acceptance audit records the exact 242-case
direct inventory, frozen 558-case adjacent matrix, post-format execution
results, static checks, and explicit worktree/leftover review.

The next gate after accepted Raw V7 is still not A2-M completion. It is the
separately frozen
[`Raw V8 contract`](v4_9f_a2_marker_operation_target_v8_protocol_freeze_2026-07-22.md):
Section 18 steps 1 and 2 are complete, and active step 3 adds the durable
candidate/attempt/terminal/marker-closure projection and lifecycle before
runtime hooks. The remaining normalization, fixture-oracle, finalization,
isolation, publication, full matched-campaign, calibration, confirmation,
threshold, and enforcement work remains later and separate.
