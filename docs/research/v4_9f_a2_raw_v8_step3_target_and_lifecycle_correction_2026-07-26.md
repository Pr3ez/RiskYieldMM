# V4.9F-A2 Raw V8 Step-3 Target-Span and Lifecycle Correction

**Correction date:** 2026-07-26  
**Status:** Normative correction candidate; **NO-GO** until the parent, Step-2
inventory, Step-3 freeze, schema, independent bound generator, implementation,
and adversarial acceptance evidence all agree. This document does not accept
Raw V8, A2-M, A2-E, Stage 1, production readiness, trading edge, or
profitability.

**Documents corrected by this amendment:**

- [`v4_9f_a2_marker_operation_target_v8_protocol_freeze_2026-07-22.md`](v4_9f_a2_marker_operation_target_v8_protocol_freeze_2026-07-22.md)
- [`v4_9f_a2_raw_v8_step2_acceptance_audit_2026-07-25.md`](v4_9f_a2_raw_v8_step2_acceptance_audit_2026-07-25.md)
- [`v4_9f_a2_raw_v8_step3_projection_lifecycle_protocol_freeze_2026-07-25.md`](v4_9f_a2_raw_v8_step3_projection_lifecycle_protocol_freeze_2026-07-25.md)

The Step-2 acceptance is a valid historical checkpoint for its then-frozen
surface, but its V1 ingress, subscription, and shutdown shapes are superseded
for Raw V8 implementation. They must not be treated as accepted current
contracts.

**Current Step-2 V2 machine-contract input:**
[`v4_9f_a2_raw_v8_step2_v2_contract_freeze_2026-07-26.md`](v4_9f_a2_raw_v8_step2_v2_contract_freeze_2026-07-26.md).
It freezes the inventory root, corrected tag/body matrices, marker contract,
selector catalog, logical-oracle profile, observation codecs, and external
type-descriptor domain consumed by this correction. A conflict is global
NO-GO until both documents are amended and re-audited; neither silently
overrides the other.

## 1. Executive decision

The narrowest sound design is:

1. exactly one open Raw V8 candidate in the complete projection store;
2. one non-serializable root lifecycle capability bound to the exact store,
   connection, process, thread, event loop, current asyncio task, writer fence,
   candidate, attempt, and operation;
3. one single-use mutation permit for each target transaction;
4. complete target-receipt attribution through the existing
   `operation_batches` partition plus an operation-specific deterministic
   finite automaton;
5. exact count and canonical-byte reservations before each effect that can
   require a projection transaction;
6. a separately reserved finite, state-specific emergency convergence suffix;
7. fixed checkpoint-selector positions with explicit unavailable placeholder
   observations;
8. immutable terminal and closure bytes constructed before the final
   transaction;
9. one exact open-locator recovery snapshot; and
10. generated, operation-specific plan admission rather than assuming all
    independent parser, marker, probe, and prefix maxima can coexist.

This retains one authoritative receipt chain and complete replay. It rejects:

- per-session open locators, because another session can contaminate the
  supposedly contiguous candidate-to-closure span;
- a `ContextVar` as authority, because asyncio copies context into child tasks
  and `asyncio.to_thread()` propagates the current context;
- receipt sidecars, because they create a second attribution truth;
- count-only target bounds, because canonical entry sizes vary materially;
- predeclared subscription IDs generated inside the target;
- an explicit 4,096-frame ingress oracle, because a legal 65,536-byte input
  can contain 32,768 minimal frame units;
- online TLS-ciphertext prediction, because client masking and TLS records are
  effect outputs rather than a logical workload oracle;
- an unbounded shutdown read loop; and
- terminal or closure serialization after `BEGIN IMMEDIATE`.

## 2. Confirmed implementation facts

These are implementation facts, not external-research claims:

| Fact | Current location | Consequence |
|---|---|---|
| The V8 locator is unique only by session | `physical_projection_v49f_v8.py`, `capacity_measurement_open_candidates_v49f_v8` | Two sessions may open candidates and interleave receipts |
| Existing target writes already have exact `operation_batches` ranges | `physical_projection_v4.py`, `_finish_batch()` | V8 can reuse the authoritative partition rather than add a sidecar |
| A composite V4.9E operation suppresses nested batch rows | `physical_projection_v4.py`, `_finish_batch()` | The outer batch is the exact atomic group and must be the DFA symbol |
| Subscription dispatch authorizes a new intent inside the target | `physical_transport_runtime_v4.py`, `_dispatch_subscription_v49c_locked()` and `physical_projection_v4.py`, `authorize_outbound_subscription_intent()` | Request ID, nonce, command, and intent ID cannot be signed as pre-target expected values |
| Authorization generates a random nonce and request ID | `physical_projection_v4.py`, `authorize_outbound_subscription_intent()` | A replayed old intent is not a fresh Raw V8 subscription target |
| ACK not-due returns `False` without a target receipt | `physical_transport_runtime_v4.py`, `expire_ack_if_due_v49e()` | The ACK DFA must admit an empty target span |
| ACK due commits one indivisible three-receipt group | `physical_projection_v4.py`, `_expire_actor_ack_deadline_core_v49e()` | No one- or two-receipt ACK prefix is legal |
| Local shutdown reads terminal ingress in a loop until peer Close | `physical_transport_runtime_v4.py`, `shutdown_current_v49e()` | Timeout alone does not bound batches, plaintext, parser work, or projection growth |
| A terminal-ingress batch parses at most one unit in current `CLOSING` state | `physical_transport_runtime_v4.py`, `_process_next_ingress_v49d_locked()` | Current shutdown parser-unit count is bounded by terminal batch count, but both still need explicit limits |
| The current Step-2 ingress spec serializes every expected logical output | `physical_transport_capacity_contracts_v49f_v8.py` | Its 4,096-frame limit is below the 32,768-unit parser type bound |
| The current subscription spec predicts target-generated identities | `physical_transport_capacity_contracts_v49f_v8.py` | Its accepted V1 shape is causally unsound for the actual runtime |

## 3. Breaking version and supersession rules

The correction uses fresh type tags. Old bytes remain parseable only for
historical audit; they are not admitted into a corrected Raw V8 declaration:

```text
INGRESS_OPERATION_SPEC_V2
SUBSCRIPTION_DISPATCH_SPEC_V2
LOCAL_SHUTDOWN_SPEC_V2

INGRESS_PRECONDITION_V2
SUBSCRIPTION_DISPATCH_PRECONDITION_V2
LOCAL_SHUTDOWN_PRECONDITION_V2

INGRESS_RESULT_EVIDENCE_V2
SUBSCRIPTION_DISPATCH_RESULT_EVIDENCE_V2
LOCAL_SHUTDOWN_RESULT_EVIDENCE_V2
```

The exact ACK V1 spec, precondition, and result **remain V1**. They are
reaccepted without a tag change after their three-receipt/zero-receipt DFA,
due-clock truth, and target-span budgets pass the regenerated inventory.

The parent hash, declaration identities, Step-2 inventory hash, V8 extension
SQL hash, full SQL hash, schema fingerprint, and initializer candidate values
must change. No old accepted hash may be silently relabelled as current.

### 3.1 Canonical identity rules

V2 operation specs retain the outer domain
`RiskYieldMMA2MOperationSpecV4_9F_RawV8`. Their identity payload is exactly:

```text
operation_kind
spec_type                         # exact V1 or V2 tag
spec                              # exact tagged body
```

V2 results retain
`RiskYieldMMA2MOperationResultEvidenceV4_9F_RawV8`; their identity payload is:

```text
candidate_id
attempt_id
operation_kind
result_type                       # exact V1 or V2 tag
result                            # exact tagged body
```

The tag and exact-key nested body provide breaking domain separation without
inventing a parallel outer codec. Every standalone record serializes:

```text
canonicalization_version
measurement_schema_version = riskyieldmm_physical_transport_a2m_raw_v49f_v8
record_domain
<exact identity-payload members>
<identity field>
```

The identity uses the existing Raw V8 semantic-ID algorithm over
`record_domain` and the exact identity payload excluding its identity field.

New identity domains and fields are the explicit pairs below; there is no
positional correspondence between separate lists:

| Literal identity domain | Exact identity field |
|---|---|
| `RiskYieldMMA2MSealedPendingIngressV2V4_9F_RawV8` | `sealed_pending_input_id` |
| `RiskYieldMMA2MIngressOracleBaselineV2V4_9F_RawV8` | `ingress_oracle_baseline_id` |
| `RiskYieldMMA2MIngressOracleExpectationV2V4_9F_RawV8` | `ingress_oracle_expectation_id` |
| `RiskYieldMMA2MCheckpointSelectorEntryV1V4_9F_RawV8` | `checkpoint_selector_entry_id` |
| `RiskYieldMMA2MCheckpointSelectorV1V4_9F_RawV8` | `checkpoint_selector_id` |
| `RiskYieldMMA2MIngressLogicalOracleProfileV1V4_9F_RawV8` | `logical_oracle_profile_id` |
| `RiskYieldMMA2MMarkerContractV1V4_9F_RawV8` | `marker_contract_id` |
| `RiskYieldMMA2MStep2ExternalTypeDescriptorV1V4_9F_RawV8` | `external_type_descriptor_id` |
| `RiskYieldMMA2MTargetObservationContextV2V4_9F_RawV8` | `observation_context_id` |
| `RiskYieldMMA2MTargetObservationV2V4_9F_RawV8` | `observation_id` |
| `RiskYieldMMA2MTargetObservationRootV2V4_9F_RawV8` | `target_observation_root_sha256` |
| `RiskYieldMMA2MShutdownTraceStepV1V4_9F_RawV8` | `shutdown_trace_step_id` |
| `RiskYieldMMA2MTerminalIngressReadEvidenceV2V4_9F_RawV8` | `terminal_ingress_read_evidence_id` |
| `RiskYieldMMTerminalIngressTlsCiphertextStagingStateV1V4_9F_RawV8` | `terminal_tls_staging_state_id` |
| `RiskYieldMMTlsRecordBoundaryLedgerV1V4_9F_RawV8` | `tls_record_boundary_ledger_id` |
| `RiskYieldMMTlsRecordSplitterProfileV1V4_9F_RawV8` | `tls_record_splitter_profile_id` |
| `RiskYieldMMTlsHandshakeTraceProfileV1V4_9F_RawV8` | `tls_handshake_trace_profile_id` |
| `RiskYieldMMTlsHandshakeTraceRecordV1V4_9F_RawV8` | `tls_handshake_trace_record_id` |
| `RiskYieldMMTlsHandshakeTraceStartAnchorV1V4_9F_RawV8` | `tls_handshake_trace_start_anchor_id` |
| `RiskYieldMMTlsHandshakeTraceBracketV1V4_9F_RawV8` | `tls_handshake_trace_bracket_id` |
| `RiskYieldMMTlsPhaseTransitionEvidenceV1V4_9F_RawV8` | `tls_phase_transition_evidence_id` |
| `RiskYieldMMA2MNativeShapeDescriptorV1V4_9F_RawV8` | `native_shape_id` |
| `RiskYieldMMA2MStrictEvidenceShapeDescriptorV1V4_9F_RawV8` | `strict_evidence_shape_id` |
| `RiskYieldMMA2MRecordVariantDescriptorV1V4_9F_RawV8` | `record_variant_id` |
| `RiskYieldMMA2MProjectionEntryVariantDescriptorV1V4_9F_RawV8` | `projection_entry_variant_id` |
| `RiskYieldMMA2MOperationBatchEnvelopeDescriptorV1V4_9F_RawV8` | `operation_batch_envelope_descriptor_id` |
| `RiskYieldMMA2MBoundedStringLanguageV1V4_9F_RawV8` | `bounded_string_language_id` |
| `RiskYieldMMA2MRecordKindContributionV1V4_9F_RawV8` | `record_kind_contribution_id` |
| `RiskYieldMMA2MIndependentParserOracleDescriptorV1V4_9F_RawV8` | `independent_parser_oracle_descriptor_id` |
| `RiskYieldMMA2MIndependentParserOracleConformanceCaseV1V4_9F_RawV8` | `conformance_case_id` |
| `RiskYieldMMA2MRestrictedWasmOracleABIV1V4_9F_RawV8` | `abi_descriptor_id` |
| `RiskYieldMMA2MPureRuleDescriptorV1V4_9F_RawV8` | `pure_rule_id` |
| `RiskYieldMMA2MTargetDFADescriptorV1V4_9F_RawV8` | `target_dfa_id` |
| `RiskYieldMMA2MEmergencyActivationInputV1V4_9F_RawV8` | `emergency_activation_id` |
| `RiskYieldMMA2MTargetSymbolBoundV1V4_9F_RawV8` | `target_symbol_bound_id` |
| `RiskYieldMMA2MTargetBoundUniverseManifestV1V4_9F_RawV8` | `target_bound_universe_manifest_id` |
| `RiskYieldMMA2MLegalPathMaterializationCertificateV1V4_9F_RawV8` | `legal_path_materialization_certificate_id` |
| `RiskYieldMMA2MEmergencySuffixUniversalValidationCertificateV1V4_9F_RawV8` | `emergency_suffix_universal_validation_certificate_id` |
| `RiskYieldMMA2MMetricAbstractDomainDescriptorV1V4_9F_RawV8` | `metric_abstract_domain_descriptor_id` |
| `RiskYieldMMA2MAbstractStateV1V4_9F_RawV8` | `abstract_state_id` |
| `RiskYieldMMA2MMetricAbstractEdgeV1V4_9F_RawV8` | `abstract_edge_id` |
| `RiskYieldMMA2MDFAMetricBoundCertificateV1V4_9F_RawV8` | `dfa_metric_bound_certificate_id` |
| `RiskYieldMMA2MHardCeilingRecordV1V4_9F_RawV8` | `hard_ceiling_record_id` |
| `RiskYieldMMA2MAdmittedPlanRecordV1V4_9F_RawV8` | `admitted_plan_record_id` |
| `RiskYieldMMA2MComponentBoundDerivationDescriptorV1V4_9F_RawV8` | `component_bound_derivation_descriptor_id` |
| `RiskYieldMMA2MComponentBoundRecordV1V4_9F_RawV8` | `component_bound_record_id` |
| `RiskYieldMMA2MFullPrefixBoundRecordV1V4_9F_RawV8` | `full_prefix_bound_record_id` |
| `RiskYieldMMA2MPlanCoordinateDispositionV1V4_9F_RawV8` | `plan_coordinate_disposition_id` |
| `RiskYieldMMA2MEmergencySuffixProfileV1V4_9F_RawV8` | `emergency_suffix_profile_id` |
| `RiskYieldMMA2MWeightedTargetDFABoundProfileV1V4_9F_RawV8` | `weighted_dfa_bound_profile_id` |
| `RiskYieldMMA2MTargetSpanBudgetV1V4_9F_RawV8` | `target_span_budget_id` |
| `RiskYieldMMA2MTargetBoundInventoryV1V4_9F_RawV8` | `target_bound_inventory_id` |

`RiskYieldMMA2MTerminalIngressReadEvidenceV2V4_9F_RawV8` is an embedded
semantic-ID domain inside the `TERMINAL_INGRESS_READ_RESULT` actor payload; it
does not create a separate projection receipt. Inventory descriptor domains
are likewise embedded in the target-bound inventory. A type is serialized as
a standalone envelope only where its contract explicitly declares a
standalone record.

For every Raw-V8 semantic identity in this correction, `semantic_id(domain,
payload)` means exactly:

```text
lowercase_hex(
  SHA-256(
    canonical_json_bytes({
      "canonicalization_version":
        CANONICALIZATION_VERSION,
      "domain":
        domain,
      "payload":
        payload,
      "schema_version":
        "riskyieldmm_physical_transport_a2m_raw_v49f_v8"
    })
  )
)
```

`payload` excludes the identity field being derived. The serialized
standalone record is a separate exact-key object:

```text
canonicalization_version
measurement_schema_version =
  riskyieldmm_physical_transport_a2m_raw_v49f_v8
record_domain
<identity-payload members>
<identity field>
```

`measurement_schema_version` and `record_domain` are serialization members;
they are not renamed substitutes for `schema_version` and `domain` inside
the semantic-ID preimage.

The three ingress digests are also literal:

```text
input_sha256 =
  lowercase_hex(SHA-256(concatenation of decoded input chunks in order))

raw_ingress_batch_sha256 =
  sha256_digest({
    "domain": "RiskYieldMMExactOrderedDecryptedIngressChunksV4_5",
    "ordered_chunks_base64": [canonical base64 chunk strings in order]
  })

logical_output_frames_sha256 =
  sha256_digest({
    "domain": "RiskYieldMMA2MExactLogicalOutputFramesV4_9F",
    "ordered_frames": [
      {
        "opcode": "CLOSE" | "PONG",
        "payload_base64": canonical base64 payload
      }
      in logical production order
    ]
  })
```

Here `sha256_digest(x)` is lowercase hexadecimal SHA-256 of
`canonical_json_bytes(x)`. The streamed logical-output implementation must
produce the identical byte preimage; it does not introduce a second digest
domain.

## 4. Store-wide locator and lifecycle authority

### 4.1 Schema correction

Add to `capacity_measurement_open_candidates_v49f_v8`:

```sql
open_singleton INTEGER NOT NULL UNIQUE CHECK(open_singleton = 1)
```

Candidate creation, inside its transaction, requires zero locator rows and
inserts `open_singleton=1`. More than one locator is corruption even if a
damaged database bypassed the SQL constraint.

While the locator exists:

- no unrelated canonical receipt may be appended;
- before an attempt, only the matching attempt or no-attempt finalizer may
  append;
- after an attempt, only an exact target mutation permit or the matching
  finalizer may append;
- a new candidate is rejected;
- a different session is not an exception; and
- startup under a new writer must recover the locator before any ordinary
  mutation.

The global receipt span is therefore exactly:

```text
no attempt:
  candidate -> terminal -> closure

attempted:
  candidate -> attempt -> ordered zero-to-N target-batch span
            -> terminal -> closure
```

This correction makes a breaking amendment to the parent candidate/attempt
schemas. `CapacityMeasurementOperationCandidateV49FV8` adds, immediately
before `candidate_id` in its exact identity payload:

```text
plan_coordinate_sha256
admitted_plan_record_id
```

`CapacityMeasurementOperationAttemptV49FV8` duplicates the same two fields
immediately before `attempt_id`. Both are non-null lowercase SHA-256 IDs.
Before the atomic candidate-plus-locator insert, the runtime constructs the
complete frozen coordinate request from the candidate's immutable
operation/spec/instrumentation/selector/marker/probe/shutdown inputs, verifies
its hash, resolves exactly one inventory disposition, requires
`ADMITTED_BY_TIER1_BOUND`, and stores the referenced admitted-plan ID. The
attempt must byte-equal both candidate fields and independently re-resolve the
same plan/profile/budget/full-prefix chain before its insert. Candidate,
attempt, locator snapshot, replay codec, projection schema/fingerprint,
strict external type descriptors, terminal/closure replay, and recovery all
include or verify this linkage. A missing column, null/default ID,
cross-coordinate substitution, or an admitted-plan ID not reachable from the
published disposition rejects before target authority; no legacy candidate
or attempt is silently upgraded.

### 4.2 Root capability

The process-local root capability binds:

```text
store object identity
sqlite connection object identity
projection ledger ID
process ID and fork generation
native thread identity
event-loop object identity
current asyncio Task object identity
candidate ID
attempt ID | null
operation kind
writer-fence token SHA-256 and generation
candidate receipt sequence/hash
attempt receipt sequence/hash | null
target-span budget ID
current target DFA state
consumed and reserved target transaction count
consumed and reserved projection-entry count
consumed and reserved projection-entry canonical bytes
consumed and reserved record-body canonical bytes
consumed and reserved operation-batch metadata bytes
consumed and reserved actor-event count
consumed and reserved RAW-commit count
dedicated emergency receipt/entry/body/metadata reserve
sealed/invalidated state
```

A `ContextVar` may locate the root cheaply, but it is never evidence of
authority. Every use compares all bound object identities and coordinates.
Child-task context inheritance, `to_thread()`, another loop, another thread,
post-fork use, another store, another connection, a changed writer fence, and
use after seal all reject before mutation.

The root is not directly consumed by a write. It mints one single-use mutation
permit bound to:

```text
exact outer operation token
exact idempotency key
exact request hash
expected current ledger head
allowed next DFA transition
maximum receipts for this transaction
maximum canonical target-entry bytes for this transaction
maximum canonical target-record-body bytes for this transaction
maximum canonical operation-batch metadata bytes for this transaction
maximum actor events for this transaction
maximum RAW commits for this transaction
whether the dedicated emergency reserve is consumed
```

The root state machine is exactly:

```text
PENDING -> ACTIVE -> SEALED
```

Activation consumes `PENDING` synchronously before the first target await.
Return, raised exception, cancellation, and fatal interruption seal the root
from a `finally` path. No exit can leave it active.

The transaction consumes the permit exactly once. Commit acknowledgement
uncertainty invalidates the live root until a fresh connection proves the
result. A writer-fence change permanently invalidates normal live
finalization; the next writer may only use recovery.

Permit outcomes are exact:

| Outcome | Permit | Root and ledger consequence |
|---|---|---|
| Validation failure before `BEGIN` | `REJECTED` | Root seals; head and counters remain unchanged |
| Conclusive transaction rollback | `ROLLED_BACK` | Head/counters/DFA remain unchanged; root may continue only when the pre-existing target algorithm itself continues, never because V8 retries |
| Normal COMMIT acknowledgement | `COMMITTED` | Advance DFA and all consumed counters exactly once |
| Same-connection exact idempotent replay | `REPLAYED` | Revalidate the already charged group; never charge or advance twice |
| COMMIT/acknowledgement uncertainty | `UNCERTAIN` | Root seals permanently; no target continuation or retry |

A fresh connection may prove the uncertain group present or absent, but it
never revives the connection-bound root. Presence is incorporated by
recovery/idempotent finalization; absence leaves the prior stable prefix for
recovery. In both cases the original target invocation is not retried.

The store revalidates the permit, singleton locator, writer fence, expected
head, exact receipt group, DFA transition, and post-group count/byte totals
both before the first append and immediately before transaction COMMIT.

### 4.3 Operation-batch partition

The finalizer orders target `operation_batches` by
`first_receipt_sequence`. It first distinguishes:

```text
zero target batches:
  current head equals attempt receipt sequence/hash
  the operation DFA admits epsilon for the exact terminal trigger/result

one or more target batches:
  apply the partition proof below
```

For a positive span it proves:

```text
first target batch begins at attempt_receipt_sequence + 1
each next first sequence equals prior last sequence + 1
last target batch ends at the exact pre-terminal ledger head
every target receipt belongs to exactly one outer batch
every outer batch advances the operation-specific DFA
every exact target request payload is independently reconstructed and its
  native production operation token/domain/schema hash equals
  operation_batches.request_hash
every stored result_blob and canonical record replays byte-exactly
```

Existing target methods retain
`RiskYieldMMPhysicalProjectionRequestV4` and their native V4 projection schema
in `_request_hash()`. V8 does not rewrite those hashes, because doing so would
change the target. Only the new candidate/attempt/finalize/recover operations
use `RiskYieldMMPhysicalProjectionRequestV4_9F_RawV8`. V8 may separately hash
its reconstructed target-batch evidence, but that evidence hash is never
substituted into `operation_batches.request_hash`.

An empty target span is legal only in a branch whose DFA permits it. A gap,
overlap, nested duplicate batch, unknown operation token, wrong session,
wrong actor predecessor, wrong fence, incomplete atomic group, unexpected
record, or unconsumed receipt is contamination. Normal finalization writes
nothing and leaves the locator for operator-visible recovery diagnosis.

## 5. Exact target-span accounting and reservation

For target projection entry `e`:

```text
entry_bytes(e) =
  len(canonical_json_bytes({
    "receipt": e.receipt.as_dict(),
    "record": e.record.as_dict()
  }))
```

For `n` target entries:

```text
target_projection_entry_canonical_bytes =
  2
  + sum(entry_bytes(e))
  + max(0, n - 1)
```

The two bytes are the JSON array brackets and the final term counts commas.
This is not a Python object-size estimate.

Record-body accounting is unframed and literal:

```text
record_body_bytes(e) =
  len(canonical_json_bytes(e.record.as_dict()))

maximum_one_target_record_body_canonical_bytes =
  max(record_body_bytes(e) for target entry e, default=0)

aggregate_target_record_body_canonical_bytes =
  sum(record_body_bytes(e) for target entry e)
```

The emergency entry-array equivalent applies the framed `entry_bytes`
function to only the entries in the consumed emergency symbol, including its
one bracket pair and internal commas. Emergency record-body metrics apply the
unframed `record_body_bytes` function to those same entries and therefore
exclude brackets and commas. The receipt count of the consumed emergency
symbol is exactly its emergency projection-entry count; there is no second
independent emergency-entry counter.

The normal and emergency reservations are bookkeeping partitions, not two
serialized arrays. For actual normal count `n`, let `T` be its ordinary
framed entry-array bytes (`2` when empty). For consumed-emergency count `m`,
let `E` be its optional-array-segment contribution: `0` when empty and,
when nonempty, the same bytes as its standalone framed array. The one
target-span array is charged exactly:

```text
if n = 0 and m = 0: combined_entry_array_bytes = 2
if n > 0 and m = 0: combined_entry_array_bytes = T
if n = 0 and m > 0: combined_entry_array_bytes = E
if n > 0 and m > 0: combined_entry_array_bytes = T + E - 1
```

The last case removes one duplicated bracket pair and adds the one
normal/emergency boundary comma. The same four-case formula and zero-empty
emergency-segment convention apply to normal and emergency framed
operation-batch metadata arrays.

Every current committed target symbol creates exactly one outer
`operation_batches` row and at least one receipt. Consequently, at every
stable state:

```text
consumed target transaction count = consumed target operation-batch count
consumed emergency transaction count = consumed emergency operation-batch count
```

Their maxima must also be equal. No zero-receipt semantic failure is counted
as either a transaction or a batch.

Every attempt binds an exact `CapacityMeasurementTargetSpanBudgetV8`:

```text
operation_kind
operation_spec_id
hard_ceiling_record_id
maximum_target_transaction_count
maximum_target_projection_entry_count
maximum_target_projection_entry_canonical_bytes
maximum_one_target_record_body_canonical_bytes
maximum_aggregate_target_record_body_canonical_bytes
maximum_target_operation_batch_count
maximum_one_operation_batch_result_blob_bytes
maximum_aggregate_operation_batch_metadata_bytes
maximum_target_actor_event_count
maximum_target_raw_ingress_commit_count
maximum_emergency_transaction_count
maximum_emergency_operation_batch_count
maximum_emergency_receipt_count
maximum_emergency_entry_canonical_bytes
maximum_emergency_one_record_body_canonical_bytes
maximum_emergency_aggregate_record_body_canonical_bytes
maximum_emergency_one_operation_batch_result_blob_bytes
maximum_emergency_operation_batch_metadata_bytes
maximum_emergency_actor_event_count
maximum_emergency_raw_ingress_commit_count
emergency_suffix_profile_id
weighted_dfa_bound_profile_id
target_span_budget_id
```

Every member before `target_span_budget_id`, in this exact order and with no
additional key, is its identity payload under
`RiskYieldMMA2MTargetSpanBudgetV1V4_9F_RawV8`.
The budget is coordinate-scoped, not attempt-input-scoped. Ingress attempts
bind their independently sealed `ingress_oracle_expectation_id` in the
precondition, but that instance identity is not a budget member. The resolved
INGRESS DFA/profile and budget dominate every expectation value admitted by
the frozen operation-spec and expectation schemas; changing the expectation
cannot select a different budget for the same plan coordinate.

Every `maximum_emergency_*` value is the certified sound componentwise upper
bound recomputed from the resolved operation-specific
`EmergencySuffixProfileV1` and remains canonically conservative. It is never
a cross-operation reserve.
Consequently ACK's epsilon-only profile has zero for every emergency maximum,
subscription's one-event unknown-send suffix has one transaction, one batch,
one receipt, and one actor event, and the ingress/local-shutdown values
dominate every reachable literal suffix.
For every operation:

```text
maximum_emergency_transaction_count
  = maximum_emergency_operation_batch_count

maximum_emergency_receipt_count
  = maximum emergency projection-entry count
```

Global structural ceilings remain:

```text
target projection entry count           <= 65,536
target projection entry canonical bytes <= 48 MiB
one operation-batch result blob          <= 64 KiB
aggregate target batch metadata          <= 8 MiB
retained dependency entries             <= 8 MiB
candidate                               <= 4 MiB
attempt                                 <= 1 MiB
terminal                                <= 1 MiB
closure                                 <= 24 MiB
outer prefix shell                      <= 10 MiB
closed prefix                           <= 96 MiB
sample                                  <= 128 MiB
```

The target-entry ceiling is exactly 50,331,648 octets. Batch metadata is a
storage/replay budget and is not silently charged to the serialized
projection-entry array. Its exact operation token, idempotency key, request
hash, first/last sequence, result blob, and committed-at framing are charged
to the separate 8-MiB aggregate above.

For batch `b`:

```text
batch_metadata_bytes(b) =
  len(canonical_json_bytes({
    "idempotency_key": b.idempotency_key,
    "operation": b.operation,
    "request_hash": lowercase_hex(b.request_hash),
    "first_receipt_sequence": b.first_receipt_sequence,
    "last_receipt_sequence": b.last_receipt_sequence,
    "result": strict_parse_and_recanonicalize(b.result_blob),
    "committed_at": b.committed_at
  }))

aggregate_batch_metadata_bytes =
  2
  + sum(batch_metadata_bytes(b))
  + max(0, batch_count - 1)
```

The stored `result_blob` must equal the canonical bytes of `result`.

The structural ceilings apply to the complete normal-plus-consumed-emergency
span:

```text
n + m <= 65,536
combined_entry_array_bytes <= 50,331,648
combined_batch_metadata_bytes <= 8 MiB
normal aggregate body bytes + emergency aggregate body bytes
  <= the admitted complete-span aggregate-body budget
```

The generator and live permit checker evaluate these combined equations;
separate reserves can never each consume the full global ceiling.

The existing 262,144 actor-prefix/export ceiling remains a broad parent
decoder bound. Raw V8 measured targets use the distinct 65,536-receipt
structural ceiling above. It is still not evidence that 65,536 complete
entries fit: the generator derives an operation-specific bound below both
ceilings, and actual canonical bytes are checked again at runtime.

The coherent Step-3 96-MiB additive closed-prefix model supersedes the
historical parent's conflicting 48-MiB whole-prefix row. The 48-MiB value is
only the complete target projection-entry array.

Before candidate persistence, plan admission reserves candidate, optional
attempt, worst-case target span, terminal, closure, retained dependencies,
outer shell, and sample framing. Before each target effect that can require a
projection write, the live capability reserves that transaction's complete
worst-case atomic group. Normal work may not consume the emergency reserve.

The emergency suffix is state-dependent:

```text
no unresolved send and actor authority live:
  exact target-native operational limit-convergence symbol, but only when
  the signed target operation itself reached that declared limit           # 2

unresolved application/Pong send:
  AE(TERMINAL_TRANSITION, UNKNOWN_SEND, exact obligation anchor) # 1 receipt

ambiguous Close/TLS-control send:
  exact Close/TLS UNKNOWN_SEND convergence symbol                # 2 receipts

conclusive Close/TLS post-write-ahead timeout:
  exact native failure symbol, then required convergence         # 4 receipts

accounted terminal-read deadline:
  exact failure symbol when required, then decisive convergence  # <= 3 receipts

no target mutation yet and no safe actor convergence:
  epsilon; seal measurement and preserve the unchanged target head
```

An observer-only target-span/count/byte invariant breach never authorizes a
new terminal event. Such a breach seals or recovers the measurement. All
terminal limit symbols must be part of the target operation in both OFF and
ON modes.

`emergency_suffix_profile_id` maps every automaton state to exactly one of
these finite suffixes and its literal cause/anchor requirements. The plan
reserves that operation profile's certified componentwise upper-bound
transaction/receipt/byte charge while the live state consumes only its exact
suffix. If the next
ordinary effect does not fit while preserving that state's suffix, the target
does not begin the effect. Lost authority or
acknowledgement uncertainty invalidates the capability and defers to recovery;
it never guesses whether more budget remains.

## 6. Exact target transaction symbols

Every symbol is one complete outer `operation_batches` row. A symbol
descriptor binds its literal name, one native codec below, exact
idempotency-key rule, strict request/result descriptors, ordered record
variant descriptors, and exact receipt count. No parameterized, wildcard, or
optional symbol exists in the generated alphabet.

The native codecs are:

| Codec | Native operation | Exact request | Exact result |
|---|---|---|---|
| `ACTOR_SINGLE` | `APPEND_TRANSPORT_ACTOR_EVENT_V49C` | one exact `event.as_dict()` as the top-level payload | `{"transport_actor_event_id": id}` |
| `ACTOR_BATCH` | `APPEND_TRANSPORT_ACTOR_EVENT_BATCH_V49C` | `{"events": [two through eight exact ordered event bodies]}` | `{"transport_actor_event_ids": [same ordered IDs]}` |
| `RAW2` | `APPEND_ACTOR_RAW_INGRESS_V49C` | `{"driver_policy_id": id, "raw": raw.as_dict()}` | `{"raw_ingress_commit_id": id, "transport_actor_event_id": id}` |
| `TERMINAL_READ` | `COMMIT_ACTOR_TERMINAL_INGRESS_READ_V49F_V8` | exact three-key body below | exact three-key body below |
| `MESSAGE` | `COMMIT_ACTOR_PROVIDER_MESSAGE_V49E` | exact eight-key body below | exact nine-key body below |
| `TERMINAL2` | `CONVERGE_ACTOR_TERMINAL_V49E` | `{"terminal_event": terminal_event.as_dict()}` | `{"terminal_event_id": id, "transport_session_termination_id": id}` |
| `ACK3` | `EXPIRE_ACTOR_ACK_DEADLINE_V49E` | exact four-key body below | exact three-key body below |
| `INTENT1` | `AUTHORIZE_OUTBOUND_SUBSCRIPTION_INTENT_V4_5` | `{"transport_session_id": id}` | `{"outbound_subscription_intent_id": id}` |
| `TERMINATION1` | `APPEND_TRANSPORT_SESSION_TERMINATION_V4_5` | exact seven-key body below | `{"transport_session_termination_id": id}` |

“Exact” requires `set(decoded_object) == set(required_keys)` recursively at
every closed object, before any native replay method is invoked. Raw V8 never
inherits a production `required.issubset(replay)` shortcut. The native ACK,
intent, actor single/batch, RAW, message, terminal, and termination replay
seams must be hardened to the same equality or wrapped by the independent V8
verifier so an extra member cannot enter projection. Acceptance mutates one
extra key at every nesting level for every codec and requires rejection
before sequence/counter/state mutation.

The `MESSAGE` request keys are exactly:

```text
classified_monotonic_ns
collector_received_at
collector_received_monotonic_ns
driver_policy_id
raw_payload_base64
source_parser_event_ids
transport_session_id
websocket_opcode
```

The new `TERMINAL_READ` request is exactly:

```text
driver_policy_id
terminal_ingress_read_result_event
raw | null
```

and its result is exactly:

```text
terminal_ingress_read_result_event_id
raw_ingress_commit_id | null
raw_ingress_actor_event_id | null
```

`TERMINAL_READ_ZERO1`, `TERMINAL_READ_DEADLINE_NOOBS1`,
`TERMINAL_READ_DEADLINE_PROGRESS1`,
`TERMINAL_READ_DRIVER_NOPROGRESS1`, and
`TERMINAL_READ_DRIVER_PROGRESS1`, `TERMINAL_READ_PRE_IO_DUE1`, and
`TERMINAL_READ_PRE_IO_XOR1` require null RAW/result RAW IDs and commit only
their exact `TERMINAL_INGRESS_READ_RESULT` actor event.
`TERMINAL_RAW3` requires `DATA`, a complete RAW record, and commits atomically
in this order: terminal-read result actor event, RAW ingress commit, and
`RAW_INGRESS_COMMITTED` actor event. Nested ordinary RAW batching is
suppressed. All eight result symbols use:

```text
"v49f-v8-terminal-read-result-" +
terminal_ingress_read_attempt_event_id
```

as their exact idempotency key. The attempt event ID is therefore the
one-result key; a second, differently encoded result for the same attempt
rejects.

The `MESSAGE` result keys are exactly:

```text
ack_event_id
application_event_id
capture_segment_id
message_disposition_id
physical_message_id
provider_message_disposition_id
provider_failure_event_id
subscription_ack_binding_id
transport_session_termination_id
```

The six literal message symbols and result null patterns are:

| Symbol | Records | Optional IDs made present |
|---|---:|---|
| `MSG_BASE6` | 6 | none |
| `MSG_NORMALIZED8` | 8 | observation derivation/revision records only |
| `MSG_ACK8` | 8 | ACK binding and ACK actor event |
| `MSG_NORMALIZED_ACK10` | 10 | observation pair plus ACK pair |
| `MSG_FATAL8` | 8 | provider failure event and termination |
| `MSG_NORMALIZED_FATAL10` | 10 | observation pair, provider failure event, and termination |

All other nullable `MESSAGE` result members follow the exact symbol-specific
descriptor. `source_parser_event_ids` has cardinality `1..4,096`.

The `ACK3` request keys are `driver_policy_id`, `observed_at`,
`observed_monotonic_ns`, and `transport_session_id`; result keys are
`deadline_event_id`, `terminal_event_id`, and
`transport_session_termination_id`.

The `TERMINATION1` request keys are `close_code`,
`close_reason_digest`, `detected_at`, `detected_monotonic_ns`,
`detected_monotonic_clock_domain_id`, `reason`, and
`transport_session_id`.

Idempotency keys are reconstructed exactly:

```text
RAW2:
  "v49c-actor-raw-" + raw_ingress_commit_id

ACTOR_SINGLE:
  "v49c-actor-event-" + transport_actor_event_id

ACTOR_BATCH:
  "v49c-actor-batch-" + sha256_digest({
    "domain": "RiskYieldMMActorProjectionBatchV4_9C",
    "transport_actor_event_ids": [ordered IDs]
  })

MESSAGE:
  "v49e-provider-" + sha256_digest({
    "collector_received_at":
      str(utc_datetime(request.collector_received_at)),
    "collector_received_monotonic_ns": exact value,
    "domain": "RiskYieldMMActorProviderMessageV4_9E",
    "raw_payload_sha256": SHA-256(decoded raw_payload_base64),
    "source_parser_event_ids": [ordered IDs],
    "transport_session_id": exact ID,
    "websocket_opcode": exact opcode
  })

TERMINAL2:
  "v49e-terminal-" + terminal_event_id

ACK3:
  "v49e-ack-timeout-" + transport_session_id

INTENT1:
  exact declaration-bound caller key
```

The two subscription `TERMINATION1` keys equal
`runtime_idempotency_prefix + "-term-" + transport_session_id`, where
`runtime_idempotency_prefix` is the exact `canonical_identifier` value of
length `1..96` captured in the V2 precondition. The resulting key must equal
the precondition's `termination_idempotency_key`, must satisfy the native
journal key bound, and is frozen in both symbol descriptors. `SUB_AUTH_TERM1`
is not a separate codec: it is the `TD1_STORAGE_FAILURE` literal
`TERMINATION1` symbol under this exact key and request.

Nested message, ACK, and terminal suboperations do not create nested outer
batches. Every verifier transition checks the native token, idempotency key,
request hash reconstructed in the production V4 request domain, strict result
body/null pattern, exact receipt span, and record bodies. Receipt kinds alone
never establish a symbol. No proper receipt prefix of a symbol is a stable
committed DFA state.

## 7. Operation-specific DFAs

### 7.1 ACK deadline expiry

The exact state is `phase`, where `phase` is `Q0` or
`ACK_DUE_TERMINAL`. The only non-epsilon symbol is:

```text
ACK3
  native operation = EXPIRE_ACTOR_ACK_DEADLINE_V49E
  request exact keys, in canonical-map order:
    driver_policy_id
    observed_at
    observed_monotonic_ns
    transport_session_id
  result exact keys, in canonical-map order:
    deadline_event_id
    terminal_event_id
    transport_session_termination_id
  records, in receipt order:
    AE(ACK_DEADLINE_EXPIRED)
    AE(TERMINAL_TRANSITION, TIMEOUT, ACK_DEADLINE_EXPIRED)
    TRANSPORT_SESSION_TERMINATION(reason=ACK_TIMEOUT)
```

The deterministic transition table is:

| Current phase | Input symbol | Guard | Next phase |
|---|---|---|---|
| `Q0` | `ACK3` | independent due decision is `DUE`; all request/result links replay exactly | `ACK_DUE_TERMINAL` |

All unlisted transitions reject. The independent due decision is exactly:

```text
NOT_DUE =
  wall_before_at < ack_not_after
  OR monotonic_before_ns < derived_ack_deadline_monotonic_ns

DUE =
  wall_before_at >= ack_not_after
  AND monotonic_before_ns >= derived_ack_deadline_monotonic_ns
```

The zero-span finalization branch is legal only for `NOT_DUE` plus returned
`False`. Returned `True` is legal only in `ACK_DUE_TERMINAL`. A target
exception/cancellation/interruption before a committed `ACK3` may finalize
the stable zero span as adverse evidence. Commit acknowledgement uncertainty
seals the live root and is resolved only by recovery. No ACK emergency target
suffix is legal: `emergency_suffix_profile_id` maps both ACK phases to
epsilon, while the normal ACK plan pre-reserves the complete `ACK3`.
An owner-abort failure after durable `ACK3` may surface as a raised target;
raised/cancelled/interrupted and recovery finalization therefore also accept
the complete `ACK_DUE_TERMINAL` state. Returned `False` remains exclusive to
`Q0/NOT_DUE`, and returned `True` remains exclusive to
`ACK_DUE_TERMINAL`.

### 7.2 Fresh subscription dispatch

The exact state is:

```text
SubscriptionStateV2
  phase =
    Q0 | INTENT | WIRED | TLS_READY | SEND_PENDING |
    UNKNOWN_SEND | DONE | DIRECT_TERMINAL
  resolved_send_count                   # 0..256
  submitted_ciphertext_octets           # 0..ciphertext_octets
  ciphertext_octets | null
  pending_kernel_attempt_event_id | null
  ordered_kernel_result_event_ids
  outbound_subscription_intent_id | null
  outbound_wire_prepared_event_id | null
  tls_ciphertext_prepared_event_id | null
  actor_tail_event_id | null
```

The literal symbols used here are:

```text
I_SUB1
  native operation = AUTHORIZE_OUTBOUND_SUBSCRIPTION_INTENT_V4_5
  request = {"transport_session_id": exact session ID}
  result = {"outbound_subscription_intent_id": exact generated ID}
  records = [OUTBOUND_SUBSCRIPTION_INTENT]

W_APP2
  native operation = APPEND_TRANSPORT_ACTOR_EVENT_BATCH_V49C
  request = {"events": [exact W_APP event body, exact permit event body]}
  result = {"transport_actor_event_ids": [wire ID, permit ID]}
  records = [AE(OUTBOUND_WIRE_PREPARED, APPLICATION_INTENT),
             AE(WRITE_PERMIT_CONSUMED)]

TLS_APP1
  native operation = APPEND_TRANSPORT_ACTOR_EVENT_V49C
  request = exact TLS-ciphertext-prepared event body
  result = {"transport_actor_event_id": exact TLS event ID}
  records = [AE(TLS_CIPHERTEXT_PREPARED)]

KA_APP2
  native operation = APPEND_TRANSPORT_ACTOR_EVENT_BATCH_V49C
  request = {"events": [exact kernel-attempt body,
                         exact send-attempt-started body]}
  result = {"transport_actor_event_ids": [attempt ID, started ID]}
  records = [AE(KERNEL_SEND_ATTEMPT),
             AE(TERMINAL_TRANSITION, SEND_ATTEMPT_STARTED)]

KR_APP2
  native operation = APPEND_TRANSPORT_ACTOR_EVENT_BATCH_V49C
  request = {"events": [exact kernel-result body,
                         exact send-attempt-resolved body]}
  result = {"transport_actor_event_ids": [result ID, resolved ID]}
  records = [AE(KERNEL_SEND_RESULT),
             AE(TERMINAL_TRANSITION, SEND_ATTEMPT_RESOLVED)]

UNKNOWN_APP_DEADLINE1
  native operation = APPEND_TRANSPORT_ACTOR_EVENT_V49C
  request = exact UNKNOWN_SEND terminal-transition event body with
    cause SEND_DEADLINE_ELAPSED_AFTER_WRITE_AHEAD
  result = {"transport_actor_event_id": exact terminal event ID}
  records = [AE(TERMINAL_TRANSITION, UNKNOWN_SEND)]

UNKNOWN_APP_EFFECT1
  native operation/result/record count = identical codec to
    UNKNOWN_APP_DEADLINE1
  request cause = SEND_EFFECT_WITHOUT_DURABLE_RESULT

D_APP1
  native operation = APPEND_TRANSPORT_ACTOR_EVENT_V49C
  request = exact outbound-dispatch-completed event body
  result = {"transport_actor_event_id": exact completion event ID}
  records = [AE(OUTBOUND_DISPATCH_COMPLETED)]

TD1_STORAGE_FAILURE
  native operation = APPEND_TRANSPORT_SESSION_TERMINATION_V4_5
  request exact keys:
    close_code
    close_reason_digest
    detected_at
    detected_monotonic_ns
    detected_monotonic_clock_domain_id
    reason = STORAGE_FAILURE
    transport_session_id
  result = {"transport_session_termination_id": exact termination ID}
  records = [TRANSPORT_SESSION_TERMINATION]

TD1_TRANSPORT_ERROR
  native operation = APPEND_TRANSPORT_SESSION_TERMINATION_V4_5
  request/result keys are identical to TD1_STORAGE_FAILURE
  reason = TRANSPORT_ERROR
  records = [TRANSPORT_SESSION_TERMINATION]
```

Both `TD1` symbols require a zero actor-event count. Once any actor event
exists, the current projection rejects legacy standalone termination;
zero-receipt fault latching is then an adverse target outcome, not a
fabricated DFA symbol.

`TD1_STORAGE_FAILURE` requires a conclusive authorization rollback/absence.
Authorization COMMIT-acknowledgement uncertainty is never classified as
storage failure and never continues to `TD1`. The corrected runtime must
propagate the dedicated uncertain-outcome condition past its generic
authorization exception handler so the Raw V8 root seals and startup recovery
resolves whether `I_SUB1` committed. This correction applies in both OFF and
ON modes.

The deterministic transition table is:

| Current phase | Symbol | Guard and linked counter update | Next phase |
|---|---|---|---|
| `Q0` | `I_SUB1` | exact authorization key absent; generated intent is fresh | `INTENT` |
| `Q0` | `TD1_STORAGE_FAILURE` | authorization append failed before `I_SUB1`; actor-event count is zero | `DIRECT_TERMINAL` |
| `INTENT` | `TD1_TRANSPORT_ERROR` | exact generated intent exists; permit/clock/pre-wire failure; actor-event count is zero | `DIRECT_TERMINAL` |
| `INTENT` | `W_APP2` | exact intent/permit/wire links | `WIRED` |
| `WIRED` | `TLS_APP1` | exact wire link; bind positive `ciphertext_octets` | `TLS_READY` |
| `TLS_READY` | `KA_APP2` | count `<256`; submitted octets `<` ciphertext octets; no pending attempt; ordinal is count + 1; start equals submitted octets; requested octets equal ciphertext minus submitted | `SEND_PENDING` |
| `SEND_PENDING` | `KR_APP2` | exact pending attempt; `1 <= accepted <= requested`; submitted octets increase by accepted | `TLS_READY` |
| `SEND_PENDING` | `UNKNOWN_APP_DEADLINE1` | exact pending attempt and application obligation anchor; second deadline gate elapsed | `UNKNOWN_SEND` |
| `SEND_PENDING` | `UNKNOWN_APP_EFFECT1` | exact pending attempt and application obligation anchor; callback/result resolution ambiguous | `UNKNOWN_SEND` |
| `TLS_READY` | `D_APP1` | count `1..256`; submitted octets equal ciphertext octets; result-ID tuple equals all resolved result IDs; disposition is `COMPLETE_LOCAL_SUBMISSION` | `DONE` |

Entering `TLS_READY` after `TLS_APP1` initializes both counters to zero.
Entering it after `KR_APP2` increments `resolved_send_count` once and clears
the pending attempt. All unlisted transitions reject.

Returned success is legal only in `DONE` with exact V2 result replay.
Raised/cancelled/interrupted or startup-recovery finalization is legal from
each stable phase. A proper receipt prefix of one native symbol is never a
stable phase. Successful receipt count is exactly `5 + 4r`, where
`1 <= r <= 256`, hence 9 through 1,029.

Emergency suffix mapping is exact for this DFA:

| Phase | Reserved legal emergency suffix |
|---|---|
| `Q0`, `INTENT` | epsilon; `TD1_STORAGE_FAILURE` and `TD1_TRANSPORT_ERROR` are normal target semantic failures, not quota-emergency suffixes |
| `SEND_PENDING` | exactly one of `UNKNOWN_APP_DEADLINE1` or `UNKNOWN_APP_EFFECT1`, selected by the observed cause |
| `WIRED`, `TLS_READY` | epsilon; seal/recover without inventing a target transition |
| `UNKNOWN_SEND`, `DONE`, `DIRECT_TERMINAL` | epsilon |

Raw V8 does not invent a post-actor standalone termination or an application
`KF` branch that the current target does not commit.

### 7.3 Ingress

The literal ingress alphabet is:

```text
RAW2
P_00_1
P_10_1
P_01_PONG1
P_ERROR_CLOSE1
PC_01_CLOSE2
MSG_BASE6
MSG_NORMALIZED8
MSG_ACK8
MSG_NORMALIZED_ACK10
MSG_FATAL8
MSG_NORMALIZED_FATAL10
W_PONG2
W_CLOSE3
TLS_PONG1
TLS_CLOSE1
KA_PONG2
KA_CLOSE2
KR_PONG_MORE2
KR_PONG_FINAL2
KR_CLOSE_MORE2
KR_CLOSE_FINAL2
UNKNOWN_PONG_DEADLINE1
UNKNOWN_PONG_EFFECT1
KF_CLOSE_TIMEOUT2
KF_CLOSE_FATAL2
D_PONG1
D_CLOSE1
WS_ACCEPTED_CLOSE1
TC_CLOSE_PREATTEMPT_TIMEOUT2
TC_CLOSE_PREATTEMPT_FATAL2
TC_CLOSE_UNKNOWN_EFFECT2
TC_CLOSE_POSTFAIL_TIMEOUT2
TC_CLOSE_POSTFAIL_FATAL2
```

The suffix number is exact receipt count. `RAW2` uses the `RAW2` codec.
`ACTOR_SINGLE` is used by `P_00_1`, `P_10_1`, `P_01_PONG1`,
`P_ERROR_CLOSE1`, `TLS_PONG1`,
`TLS_CLOSE1`, `UNKNOWN_PONG_DEADLINE1`, `UNKNOWN_PONG_EFFECT1`,
`D_PONG1`, `D_CLOSE1`, and `WS_ACCEPTED_CLOSE1`. `ACTOR_BATCH` is used by
`PC_01_CLOSE2`, `W_PONG2`, `W_CLOSE3`, both `KA` symbols, all four
`KR` symbols, and both `KF` symbols. The six literal message symbols use
`MESSAGE`; the five literal Close terminal-convergence symbols use
`TERMINAL2`.

In each non-error `P` or `PC` name, the first numeric bit is the literal
completed-application-message bit and the second is the literal
automatic-output bit. A set second bit has its opcode in the symbol name.
`PC` additionally includes the paired `WS_CLOSE_RECEIVED` terminal
transition. These five parser symbols are the complete reachable cross-product
from the exact OPEN ingress baseline. In pinned `websockets==16.0`, a peer
Close received in OPEN is always echoed, so `PC_00_2` is unreachable here and
belongs only to the local-shutdown CLOSING alphabet. Message-plus-output,
peer-Close message, and peer-Close Pong combinations are rejected as
unreachable rather than reserved as speculative variants.

Ingress replay state is the exact tuple:

```text
phase =
  Q0 | READY | NEED_MSG | NEED_W_PONG | NEED_W_CLOSE |
  NEED_TLS_PONG | NEED_TLS_CLOSE |
  SEND_READY_PONG | SEND_READY_CLOSE |
  SEND_PENDING_PONG | SEND_PENDING_CLOSE |
  NEED_D_PONG | NEED_D_CLOSE | NEED_WS_ACCEPTED |
  NEED_TC_CLOSE_TIMEOUT | NEED_TC_CLOSE_FATAL |
  RETURN_READY_FAILED | RETURN_READY_CLOSING | TERMINAL_ADVERSE
parser_cursor_id
parser_state
parser_sequence
next_stream_octet
fragmented_message_state
fragmented_message_payload_base64 | null
fragmented_message_parser_event_ids
retained_tail_id
retained_tail_base64
retained_tail_octets
retained_tail_sha256
ordered_retained_raw_dependency_ids
pending_message_descriptor | null
pending_output_kind = NONE | PONG | CLOSE
post_output_return_phase = READY | RETURN_READY_FAILED | RETURN_READY_CLOSING
wire_event_id | null
tls_event_id | null
resolved_send_count
submitted_ciphertext_octets
total_ciphertext_octets
ordered_kernel_result_event_ids
pending_kernel_attempt_event_id | null
actor_tail_event_id
target counters from Section 5
```

`resolved_send_count` is `0..256`. Byte offsets are
`0..total_ciphertext_octets`. Every transition also applies the exact parser,
RAW-lineage, actor-predecessor, obligation, fence, and counter update encoded
by its descriptor.

Parser transitions from `READY` are literal:

| Symbol | Required oracle output | Next phase/state |
|---|---|---|
| `P_00_1` | ordinary non-error unit; no message; no output | `READY` |
| `P_10_1` | completed application message; no output | `NEED_MSG`, output `NONE`, post return `READY` |
| `P_01_PONG1` | no message; automatic Pong | `NEED_W_PONG`, post return `READY` |
| `P_ERROR_CLOSE1` | exact parser failure plus one automatic Close | `NEED_W_CLOSE`, post-output return `RETURN_READY_FAILED` |
| `PC_01_CLOSE2` | peer Close plus automatic Close | `NEED_W_CLOSE`, post return `RETURN_READY_CLOSING` |

`Q0 + RAW2 -> READY` is the sole initial transition. In `READY`, returned
success is finalizable only when the independent oracle says no complete
unit remains and the exact final cursor/tail/progress result matches.

Message transitions are:

| Current | Symbol | Guard | Next |
|---|---|---|---|
| `NEED_MSG` | `MSG_BASE6` | exact non-normalized, non-ACK message result | `READY` |
| `NEED_MSG` | `MSG_NORMALIZED8` | exact normalized, non-ACK result | `READY` |
| `NEED_MSG` | `MSG_ACK8` | exact non-normalized ACK result | `READY` |
| `NEED_MSG` | `MSG_NORMALIZED_ACK10` | exact normalized ACK result | `READY` |
| `NEED_MSG` | `MSG_FATAL8` | exact non-normalized ACK-integrity terminal result | `TERMINAL_ADVERSE` |
| `NEED_MSG` | `MSG_NORMALIZED_FATAL10` | exact normalized ACK-integrity terminal result | `TERMINAL_ADVERSE` |

The pinned runtime never combines a completed application message with an
automatic control output, so a successful nonfatal message symbol returns to
`READY`. Every admitted returned workload must prove
before candidate creation that each completed message's exact
`source_parser_event_ids`, including baseline fragment IDs, is at most 4,096.
If live replay nevertheless reaches `NEED_MSG` with a longer lineage, that
stable phase may only adverse-finalize with no fabricated `MSG` symbol.

Automatic-output transitions are:

| Current | Symbol | Exact guard/update | Next |
|---|---|---|---|
| `NEED_W_PONG` | `W_PONG2` | exact automatic Pong wire/permit pair | `NEED_TLS_PONG` |
| `NEED_W_CLOSE` | `W_CLOSE3` | exact automatic Close wire/WS-sent/permit triple | `NEED_TLS_CLOSE` |
| `NEED_TLS_PONG` | `TLS_PONG1` | bind positive ciphertext length and wire link | `SEND_READY_PONG` |
| `NEED_TLS_CLOSE` | `TLS_CLOSE1` | bind positive ciphertext length and wire link | `SEND_READY_CLOSE` |
| `SEND_READY_PONG` | `KA_PONG2` | both deadline brackets allow send; count `<256`; submitted `< total`; exact ordinal/start/request | `SEND_PENDING_PONG` |
| `SEND_READY_CLOSE` | `KA_CLOSE2` | same finite-send guards | `SEND_PENDING_CLOSE` |
| `SEND_READY_CLOSE` | `TC_CLOSE_PREATTEMPT_TIMEOUT2` | both deadline domains due; kind `TIMEOUT`; cause `WEBSOCKET_CLOSE_DEADLINE_EXPIRED` | `TERMINAL_ADVERSE` |
| `SEND_READY_CLOSE` | `TC_CLOSE_PREATTEMPT_FATAL2` | exactly one deadline domain due; kind `FATAL`; cause `LOCAL_SHUTDOWN_CLOCK_DISAGREEMENT` | `TERMINAL_ADVERSE` |
| `SEND_PENDING_PONG` | `KR_PONG_MORE2` | exact attempt; positive accepted bytes; new offset below total | `SEND_READY_PONG` |
| `SEND_PENDING_PONG` | `KR_PONG_FINAL2` | exact attempt; new offset equals total | `NEED_D_PONG` |
| `SEND_PENDING_PONG` | `UNKNOWN_PONG_DEADLINE1` | exact unresolved attempt; cause `SEND_DEADLINE_ELAPSED_AFTER_WRITE_AHEAD` | `TERMINAL_ADVERSE` |
| `SEND_PENDING_PONG` | `UNKNOWN_PONG_EFFECT1` | exact unresolved attempt; cause `SEND_EFFECT_WITHOUT_DURABLE_RESULT` | `TERMINAL_ADVERSE` |
| `SEND_PENDING_CLOSE` | `KR_CLOSE_MORE2` | exact attempt; positive accepted bytes; new offset below total | `SEND_READY_CLOSE` |
| `SEND_PENDING_CLOSE` | `KR_CLOSE_FINAL2` | exact attempt; new offset equals total | `NEED_D_CLOSE` |
| `SEND_PENDING_CLOSE` | `TC_CLOSE_UNKNOWN_EFFECT2` | exact obligation/attempt; `UNKNOWN_SEND`; cause `SEND_EFFECT_WITHOUT_DURABLE_RESULT` | `TERMINAL_ADVERSE` |
| `SEND_PENDING_CLOSE` | `KF_CLOSE_TIMEOUT2` | conclusive no-acceptance timeout failure | `NEED_TC_CLOSE_TIMEOUT` |
| `SEND_PENDING_CLOSE` | `KF_CLOSE_FATAL2` | conclusive no-acceptance clock-disagreement failure | `NEED_TC_CLOSE_FATAL` |
| `NEED_TC_CLOSE_TIMEOUT` | `TC_CLOSE_POSTFAIL_TIMEOUT2` | `TIMEOUT/WEBSOCKET_CLOSE_DEADLINE_EXPIRED` | `TERMINAL_ADVERSE` |
| `NEED_TC_CLOSE_FATAL` | `TC_CLOSE_POSTFAIL_FATAL2` | `FATAL/LOCAL_SHUTDOWN_CLOCK_DISAGREEMENT` | `TERMINAL_ADVERSE` |
| `NEED_D_PONG` | `D_PONG1` | complete local submission and exact result-ID tuple | stored post-output return phase |
| `NEED_D_CLOSE` | `D_CLOSE1` | complete local submission and exact result-ID tuple | `NEED_WS_ACCEPTED` |
| `NEED_WS_ACCEPTED` | `WS_ACCEPTED_CLOSE1` | exact Close obligation fully accepted | stored post-output return phase |

If a Pong deadline gate rejects before `KA_PONG2`, no new target receipt is
committed and `SEND_READY_PONG` adverse-finalizes. All unlisted
state/symbol pairs reject. Returned success is legal only at oracle-empty
`READY`, `RETURN_READY_FAILED`, or `RETURN_READY_CLOSING`, with no unresolved
message/output/send and exact cursor, tail, RAW result, logical-output digest,
obligations, and V2 result. `TERMINAL_ADVERSE` cannot return a success result.
Raised/cancelled/interrupted and startup recovery may finalize any complete
symbol state; a partial native batch is never stable.

A Close deadline discovered after `KA_CLOSE2` is not a direct
unknown-deadline symbol. Conclusive no-acceptance evidence commits
`KF_CLOSE_TIMEOUT2` and then `TC_CLOSE_POSTFAIL_TIMEOUT2`; only a callback or
result whose physical effect cannot be resolved commits
`TC_CLOSE_UNKNOWN_EFFECT2`.

### 7.4 Local shutdown

Local shutdown uses the following additional literal symbols. Shared ingress
parser, message, and automatic-Pong symbols reuse their Section 7.3
descriptors only when explicitly listed below. OPEN-state automatic-Close
symbols are not imported into the CLOSING automaton.

```text
SC1
W_LOCAL_CLOSE3
TLS_LOCAL_WS1
KA_LOCAL_WS2
KR_LOCAL_WS_MORE2
KR_LOCAL_WS_FINAL2
KF_LOCAL_WS_TIMEOUT2
KF_LOCAL_WS_FATAL2
D_LOCAL_WS1
WS_ACCEPTED_LOCAL1
TC_LOCAL_WS_UNKNOWN_EFFECT2

TERMINAL_READ_ATTEMPT1
TERMINAL_RAW3
TERMINAL_READ_ZERO1
TERMINAL_READ_DEADLINE_NOOBS1
TERMINAL_READ_DEADLINE_PROGRESS1
TERMINAL_READ_DRIVER_NOPROGRESS1
TERMINAL_READ_DRIVER_PROGRESS1
TERMINAL_READ_PRE_IO_DUE1
TERMINAL_READ_PRE_IO_XOR1
P_ERROR_NO_OUTPUT1
PC_00_2
TC_FATAL_TERMINAL_READ_UNKNOWN_EFFECT2

DEADLINE_EVIDENCE_BOTH1
DEADLINE_EVIDENCE_XOR1
DEADLINE_EVIDENCE_EARLY1
TERMINAL_INGRESS_FAIL_BOTH1
TERMINAL_INGRESS_FAIL_XOR1

TS_LOCAL1
TCPREP_LOCAL2
TLSFAIL_DRIVER1
TLSFAIL_NOOBS_BOTH1
TLSFAIL_NOOBS_XOR1
TLSFAIL_NOOBS_EARLY1
TLSFAIL_PROGRESS_BOTH1
TLSFAIL_PROGRESS_XOR1
TLSFAIL_PROGRESS_EARLY1
TLSFAIL_UNSENDABLE1
TKA_LOCAL2
TKR_LOCAL_MORE2
TKR_LOCAL_FINAL4
TKF_LOCAL_TIMEOUT2
TKF_LOCAL_FATAL2
TC_TLS_CONTROL_UNKNOWN_OUTCOME2

HATT1
HOK2
HNEG_PRE_SYSCALL1
HNEG_CLOCK1
HNEG_ERROR1

PS1
POBS_NOTIFY2
POBS_EOF_TRUNCATED1
POBS_EOF_CLEAN2

TC_TIMEOUT_LOCAL_COMMAND_DEADLINE2
TC_FATAL_LOCAL_CLOCK_DISAGREEMENT2
TC_TIMEOUT_TERMINAL_INGRESS_PROGRESS2
TC_FATAL_TLS_DRIVER2
TC_TIMEOUT_TLS_SHUTDOWN2
TC_TIMEOUT_TLS_SHUTDOWN_PROGRESS2
TC_FATAL_TLS_POST_HANDSHAKE_OUTPUT2
TC_TIMEOUT_HALF_CLOSE_PRE_SYSCALL2
TC_FATAL_HALF_CLOSE_ERROR2
TC_FATAL_HALF_CLOSE_UNKNOWN2
TC_FATAL_TCP_TOKEN_PREPARATION2
TC_FATAL_SHUTDOWN_EFFECT2
TC_TRUNCATED_NULLCAUSE2
TC_CLEAN_NULLCAUSE2
TC_AUTO_PONG_UNKNOWN_DEADLINE2
TC_AUTO_PONG_UNKNOWN_EFFECT2

TC_FATAL_LIMIT_TERMINAL_INGRESS_BATCH2
TC_FATAL_LIMIT_TERMINAL_INGRESS_CIPHERTEXT2
TC_FATAL_LIMIT_TERMINAL_INGRESS_OCTET2
TC_FATAL_LIMIT_TERMINAL_SOCKET_RECEIVE2
TC_FATAL_LIMIT_TERMINAL_TLS_RECORD2
TC_FATAL_LIMIT_TERMINAL_TLS_UNWRAP2
TC_FATAL_LIMIT_TERMINAL_ZERO_PROGRESS2
TC_FATAL_LIMIT_TERMINAL_INGRESS_PARSER2
TC_FATAL_LIMIT_AUTOMATIC_OUTPUT2
TC_FATAL_LIMIT_WEBSOCKET_SEND2
TC_FATAL_LIMIT_TLS_CONTROL_SEND2
TC_FATAL_LIMIT_PEER_SHUTDOWN_POLL2
```

Decisive terminal kind/cause mappings are literal:

| Symbol | Terminal kind / cause |
|---|---|
| `TC_TIMEOUT_LOCAL_COMMAND_DEADLINE2` | `TIMEOUT / LOCAL_SHUTDOWN_COMMAND_DEADLINE_EXPIRED` |
| `TC_FATAL_LOCAL_CLOCK_DISAGREEMENT2` | `FATAL / LOCAL_SHUTDOWN_CLOCK_DISAGREEMENT` |
| `TC_TIMEOUT_TERMINAL_INGRESS_PROGRESS2` | `TIMEOUT / TERMINAL_CLOSE_INGRESS_DEADLINE_EXPIRED_AFTER_PROGRESS` |
| `TC_FATAL_TLS_DRIVER2` | `FATAL / TLS_OPERATION_DRIVER_ERROR` |
| `TC_TIMEOUT_TLS_SHUTDOWN2` | `TIMEOUT / TLS_SHUTDOWN_DEADLINE_EXPIRED` |
| `TC_TIMEOUT_TLS_SHUTDOWN_PROGRESS2` | `TIMEOUT / TLS_SHUTDOWN_DEADLINE_EXPIRED_AFTER_PROGRESS` |
| `TC_FATAL_TLS_POST_HANDSHAKE_OUTPUT2` | `FATAL / TLS_POST_HANDSHAKE_OUTPUT_AFTER_SHUT_WR` |
| `TC_TIMEOUT_HALF_CLOSE_PRE_SYSCALL2` | `TIMEOUT / TCP_HALF_CLOSE_DEADLINE_EXPIRED_BEFORE_SYSCALL` |
| `TC_FATAL_HALF_CLOSE_ERROR2` | `FATAL / TCP_HALF_CLOSE_ERROR` |
| `TC_FATAL_HALF_CLOSE_UNKNOWN2` | `FATAL / TCP_HALF_CLOSE_OUTCOME_UNKNOWN` |
| `TC_FATAL_TCP_TOKEN_PREPARATION2` | `FATAL / TCP_HALF_CLOSE_TOKEN_PREPARATION_ERROR` |
| `TC_FATAL_SHUTDOWN_EFFECT2` | `FATAL / V49E_SHUTDOWN_EFFECT_FAILURE` |
| `TC_LOCAL_WS_UNKNOWN_EFFECT2` | `UNKNOWN_SEND / SEND_EFFECT_WITHOUT_DURABLE_RESULT` |
| `TC_AUTO_PONG_UNKNOWN_DEADLINE2` | `UNKNOWN_SEND / SEND_DEADLINE_ELAPSED_AFTER_WRITE_AHEAD` |
| `TC_AUTO_PONG_UNKNOWN_EFFECT2` | `UNKNOWN_SEND / SEND_EFFECT_WITHOUT_DURABLE_RESULT` |
| `TC_TLS_CONTROL_UNKNOWN_OUTCOME2` | `UNKNOWN_SEND / TLS_CONTROL_SEND_OUTCOME_UNKNOWN` |
| `TC_FATAL_TERMINAL_READ_UNKNOWN_EFFECT2` | `FATAL / TERMINAL_INGRESS_READ_EFFECT_WITHOUT_DURABLE_RESULT` |
| `TC_TRUNCATED_NULLCAUSE2` | `TCP_EOF_RECEIVED / null` |
| `TC_CLEAN_NULLCAUSE2` | `CLEAN_ALL_LAYERS / null` |

The twelve limit symbols have kind `FATAL` and their position-matched
dimension-specific causes from Section 8.3. `TC_TRUNCATED_NULLCAUSE2` and
`TC_CLEAN_NULLCAUSE2` have the exact kinds and null causes above. No descriptor may
substitute a broader exception class or a differently named cause.

The suffix number is receipt count. `SC1`, `TLS_LOCAL_WS1`,
`D_LOCAL_WS1`, `WS_ACCEPTED_LOCAL1`, `TERMINAL_READ_ATTEMPT1`,
`P_ERROR_NO_OUTPUT1`, the three deadline-evidence symbols,
the two terminal-ingress-failure symbols, `TS_LOCAL1`, all eight
TLS-failure symbols, `HATT1`, and `PS1` use `ACTOR_SINGLE`.
`W_LOCAL_CLOSE3`, `PC_00_2`, both local-WS `KA/KR/KF` groups, `TCPREP_LOCAL2`,
`TKA_LOCAL2`, all local TLS-control `TKR/TKF` groups, `HOK2`, and the
three peer observations with suffix two use `ACTOR_BATCH`. The one-receipt
`HNEG_PRE_SYSCALL1`, `HNEG_CLOCK1`, `HNEG_ERROR1`, and
`POBS_EOF_TRUNCATED1` use `ACTOR_SINGLE`. Every literal symbol beginning
with `TC_` uses `TERMINAL2`. `TERMINAL_RAW3` and the seven
`TERMINAL_READ_*1` result symbols use the `TERMINAL_READ` codec; the former
has three receipts and each latter has one.

The shutdown replay state is:

```text
phase =
  Q0 | NEED_LOCAL_WS | LOCAL_WS_NEED_TLS |
  LOCAL_WS_SEND_READY | LOCAL_WS_SEND_PENDING |
  LOCAL_WS_NEED_D | LOCAL_WS_NEED_ACCEPT |
  WAIT_PEER_CLOSE | TERMINAL_READ_PENDING |
  READ_DEADLINE_ACCOUNTED | TERMINAL_UNIT_READY |
  UNIT_NEED_MSG | UNIT_NEED_W_PONG |
  UNIT_NEED_TLS_PONG |
  UNIT_SEND_READY_PONG |
  UNIT_SEND_PENDING_PONG |
  UNIT_NEED_D_PONG |
  NEED_TLS_LOCAL_OP | TLS_LOCAL_STARTED |
  TLS_CONTROL_SEND_READY | TLS_CONTROL_SEND_PENDING |
  NEED_HALF_CLOSE | HALF_CLOSE_PENDING |
  POLL_READY | POLL_PENDING |
  NEED_DECISIVE_TERMINAL | NEED_CLEAN_TERMINAL | TERMINAL
peer_first_close_converged
terminal_ingress_batch_count
terminal_ingress_ciphertext_octets
terminal_ingress_plaintext_octets
terminal_socket_receive_call_count
terminal_tls_record_count
terminal_tls_unwrap_iteration_count
terminal_zero_progress_iteration_count
terminal_ingress_parser_unit_count
terminal_ingress_automatic_output_count
websocket_send_attempt_count
tls_control_send_attempt_count
peer_shutdown_poll_count
parser_cursor
parser_cursor_id
parser_state
parser_sequence
next_stream_octet
fragmented_message_opcode | null
fragmented_message_payload_base64 | null
fragmented_message_octets
fragmented_message_sha256 | null
fragmented_message_parser_event_ids
retained_tail_id
retained_tail_base64
retained_tail_octets
retained_tail_sha256
ordered_retained_raw_dependency_ids
pending_terminal_ingress_read_attempt_event_id | null
pending_terminal_ingress_read_capability_id | null
previous_terminal_ingress_read_result_event_id | null
terminal_tls_staging_state
terminal_tls_staging_state_id
pending_terminal_read_outcome | null
unit_is_peer_close
unit_message_required
unit_output_kind = NONE | PONG
unit_return_phase =
  WAIT_PEER_CLOSE | TERMINAL_UNIT_READY
current wire/TLS/control/half-close/poll IDs
resolved send count, submitted octets, total octets, ordered result IDs
pending physical-effect tuple | null
required_decisive_terminal_symbol | null
actor_tail_event_id
target counters from Section 5
```

All twelve enforcement counters are safe, nondecreasing, and bounded by the
signed V2 precondition. `terminal_ingress_batch_count` increments at the
durable read attempt before I/O; the six physical-work counters increment
only at its matched durable result. Per-send resolved count is `0..256`.

The initial/local-WebSocket transitions are:

| Current | Symbol | Guard/update | Next |
|---|---|---|---|
| `Q0` | `SC1` | baseline peer-first flag false | `NEED_LOCAL_WS` |
| `Q0` | `SC1` | baseline peer-first flag true | `NEED_TLS_LOCAL_OP` |
| `NEED_LOCAL_WS` | `W_LOCAL_CLOSE3` | exact local Close wire/WS-sent/permit | `LOCAL_WS_NEED_TLS` |
| `NEED_LOCAL_WS` | `TC_FATAL_TLS_DRIVER2` | local WebSocket Close preparation failed with current `TLS_OPERATION_DRIVER_ERROR` cause | `TERMINAL` |
| `LOCAL_WS_NEED_TLS` | `TLS_LOCAL_WS1` | bind positive ciphertext | `LOCAL_WS_SEND_READY` |
| `LOCAL_WS_NEED_TLS` | `TC_FATAL_TLS_DRIVER2` | local WebSocket TLS preparation failed with current `TLS_OPERATION_DRIVER_ERROR` cause | `TERMINAL` |
| `LOCAL_WS_SEND_READY` | `KA_LOCAL_WS2` | both deadline domains allow; send/plan caps allow; exact offset/request | `LOCAL_WS_SEND_PENDING` |
| `LOCAL_WS_SEND_READY` | `TC_TIMEOUT_LOCAL_COMMAND_DEADLINE2` | both deadline domains due | `TERMINAL` |
| `LOCAL_WS_SEND_READY` | `TC_FATAL_LOCAL_CLOCK_DISAGREEMENT2` | exactly one deadline domain due | `TERMINAL` |
| `LOCAL_WS_SEND_PENDING` | `KR_LOCAL_WS_MORE2` | exact positive partial acceptance | `LOCAL_WS_SEND_READY` |
| `LOCAL_WS_SEND_PENDING` | `KR_LOCAL_WS_FINAL2` | exact final acceptance | `LOCAL_WS_NEED_D` |
| `LOCAL_WS_SEND_PENDING` | `KF_LOCAL_WS_TIMEOUT2` | conclusive timeout/no acceptance; record required terminal symbol | `NEED_DECISIVE_TERMINAL` |
| `LOCAL_WS_SEND_PENDING` | `KF_LOCAL_WS_FATAL2` | conclusive clock disagreement/no acceptance; record required terminal symbol | `NEED_DECISIVE_TERMINAL` |
| `LOCAL_WS_SEND_PENDING` | `TC_LOCAL_WS_UNKNOWN_EFFECT2` | callback/result ambiguous; exact attempt/Close anchor | `TERMINAL` |
| `LOCAL_WS_NEED_D` | `D_LOCAL_WS1` | complete submission/result tuple | `LOCAL_WS_NEED_ACCEPT` |
| `LOCAL_WS_NEED_ACCEPT` | `WS_ACCEPTED_LOCAL1` | exact Close obligation accepted | `WAIT_PEER_CLOSE` |

After `KF_LOCAL_WS_TIMEOUT2`, the required next symbol is
`TC_TIMEOUT_LOCAL_COMMAND_DEADLINE2`; after
`KF_LOCAL_WS_FATAL2`, it is `TC_FATAL_LOCAL_CLOCK_DISAGREEMENT2`.
There is no direct local-Close unknown-deadline symbol. A conclusive
post-write-ahead deadline commits `KF_LOCAL_WS_TIMEOUT2` and then its required
timeout convergence. Only an actually ambiguous callback/result uses
`TC_LOCAL_WS_UNKNOWN_EFFECT2`.
`NEED_DECISIVE_TERMINAL` accepts only its stored required literal symbol and
then enters `TERMINAL`.

Terminal ingress begins only in `WAIT_PEER_CLOSE`:

| Current | Symbol | Guard/update | Next |
|---|---|---|---|
| `WAIT_PEER_CLOSE` | `TERMINAL_READ_ATTEMPT1` | attempt count below batch maximum; ciphertext/receive/TLS-record/unwrap/zero-progress allowances positive; plaintext allowance at least 16,384; both authorization clocks strictly before command deadlines; exact next ordinal/capability/command/fence/staging-before ID; increment attempt count once | `TERMINAL_READ_PENDING` |
| `TERMINAL_READ_PENDING` | `TERMINAL_READ_PRE_IO_DUE1` | acknowledged matching attempt; post-ack gate is `BOTH_DUE`; no effect capability and all work deltas zero; store command-timeout convergence | `NEED_DECISIVE_TERMINAL` |
| `TERMINAL_READ_PENDING` | `TERMINAL_READ_PRE_IO_XOR1` | acknowledged matching attempt; post-ack gate is `CLOCK_XOR`; no effect capability and all work deltas zero; store clock-fatal convergence | `NEED_DECISIVE_TERMINAL` |
| `TERMINAL_READ_PENDING` | `TERMINAL_RAW3` | exact matching attempt/authorization/effect capability; pre-I/O, first post-effect, and DATA commit-ready gates are all `BOTH_ALLOW`; all deltas within allowance; oracle exposes one complete parser unit | `TERMINAL_UNIT_READY` |
| `TERMINAL_READ_PENDING` | `TERMINAL_RAW3` | same three `BOTH_ALLOW` gates but oracle exposes no complete parser unit | `WAIT_PEER_CLOSE` |
| `TERMINAL_READ_PENDING` | `TERMINAL_RAW3` | exact DATA commit; first post-effect gate is `BOTH_DUE`, or it is `BOTH_ALLOW` and commit-ready is `BOTH_DUE`; store command-timeout convergence without allowing the second pair to overwrite a decisive first pair | `NEED_DECISIVE_TERMINAL` |
| `TERMINAL_READ_PENDING` | `TERMINAL_RAW3` | exact DATA commit; first post-effect gate is `CLOCK_XOR`, or it is `BOTH_ALLOW` and commit-ready is `CLOCK_XOR`; store clock-fatal convergence without allowing the second pair to overwrite a decisive first pair | `NEED_DECISIVE_TERMINAL` |
| `TERMINAL_READ_PENDING` | `TERMINAL_READ_ZERO1` | exact matching result; zero plaintext, positive bounded physical work, and neither command clock due | `WAIT_PEER_CLOSE` |
| `TERMINAL_READ_PENDING` | `TERMINAL_READ_ZERO1` | exact zero result; both clocks due; store command-timeout convergence | `NEED_DECISIVE_TERMINAL` |
| `TERMINAL_READ_PENDING` | `TERMINAL_READ_ZERO1` | exact zero result; exactly one clock due; store clock-fatal convergence | `NEED_DECISIVE_TERMINAL` |
| `TERMINAL_READ_PENDING` | `TERMINAL_READ_DEADLINE_NOOBS1` | exact no-observation result; both clocks due; store timeout convergence | `NEED_DECISIVE_TERMINAL` |
| `TERMINAL_READ_PENDING` | `TERMINAL_READ_DEADLINE_NOOBS1` | exact no-observation result; exactly one clock due; store clock-fatal convergence | `NEED_DECISIVE_TERMINAL` |
| `TERMINAL_READ_PENDING` | `TERMINAL_READ_DEADLINE_NOOBS1` | result preceded both clocks; store driver-fatal convergence | `NEED_DECISIVE_TERMINAL` |
| `TERMINAL_READ_PENDING` | `TERMINAL_READ_DEADLINE_PROGRESS1` | exact positive-progress deadline result | `READ_DEADLINE_ACCOUNTED` |
| `TERMINAL_READ_PENDING` | `TERMINAL_READ_DRIVER_NOPROGRESS1` | exact driver error/no progress; store `TC_FATAL_TLS_DRIVER2` | `NEED_DECISIVE_TERMINAL` |
| `TERMINAL_READ_PENDING` | `TERMINAL_READ_DRIVER_PROGRESS1` | exact driver error/positive progress; store `TC_FATAL_TLS_DRIVER2` | `NEED_DECISIVE_TERMINAL` |
| `TERMINAL_READ_PENDING` | `TC_FATAL_TERMINAL_READ_UNKNOWN_EFFECT2` | deterministic result key absent; exact result object unavailable; unmatched attempt anchor | `TERMINAL` |
| `READ_DEADLINE_ACCOUNTED` | `TERMINAL_INGRESS_FAIL_BOTH1` | exact matching failure event; both clocks due; store progress-timeout convergence | `NEED_DECISIVE_TERMINAL` |
| `READ_DEADLINE_ACCOUNTED` | `TERMINAL_INGRESS_FAIL_XOR1` | exact matching failure event; exactly one clock due; store clock-fatal convergence | `NEED_DECISIVE_TERMINAL` |
| `READ_DEADLINE_ACCOUNTED` | `TC_FATAL_SHUTDOWN_EFFECT2` | neither actor clock due after sealed positive-progress deadline evidence; semantic evidence contradiction | `TERMINAL` |
| `TERMINAL_UNIT_READY` | one of `P_00_1`, `P_10_1`, `P_01_PONG1`, `P_ERROR_NO_OUTPUT1`, `PC_00_2` | pinned CLOSING oracle matches the next complete durable unit; increment parser-unit count once | deterministic unit phase |

For every non-close parser unit, the independent durable-tail oracle chooses
`unit_return_phase=TERMINAL_UNIT_READY` iff another complete unit already
exists, otherwise `WAIT_PEER_CLOSE`. `P_00_1` enters that stored return
directly; `P_10_1` enters `UNIT_NEED_MSG`; and `P_01_PONG1` enters
`UNIT_NEED_W_PONG`. `PC_00_2` enters `NEED_TLS_LOCAL_OP`.
`P_ERROR_NO_OUTPUT1` persists the parser failure without a second Close
output, then enters `NEED_DECISIVE_TERMINAL` requiring
`TC_FATAL_SHUTDOWN_EFFECT2`.

This five-symbol local parser subset is intentionally different from the five
OPEN-ingress variants in Section 7.3. Under pinned `websockets==16.0`,
`Protocol.fail()` emits a Close only in `OPEN`, and an inbound Close is echoed
only in `OPEN`; therefore `P_ERROR_CLOSE1` and `PC_01_CLOSE2` are unreachable
after the local Close has placed the protocol in `CLOSING`. Fragment
start/middle is `P_00_1`, a final continuation is `P_10_1`, Ping is
`P_01_PONG1`, Pong is `P_00_1`, and invalid sequencing/UTF-8/Close-during-
fragment is `P_ERROR_NO_OUTPUT1`. The current projection accepts successful
CLOSING receipts only for opcode Close; Raw V8 remains disabled until both
OFF and ON projection accept and replay the other four pinned outcomes under
these exact guards.

The current runtime breaks after one CLOSING unit, attempts another owner
read, and the driver refuses it because a complete durable unit remains.
Raw V8 changes both modes to drain
already durable complete units through `TERMINAL_UNIT_READY` before another
read. It neither discards coalesced frames nor performs a second owner read
for them.

The three guarded `TERMINAL_READ_DEADLINE_NOOBS1` rows store, respectively,
`TC_TIMEOUT_LOCAL_COMMAND_DEADLINE2`,
`TC_FATAL_LOCAL_CLOCK_DISAGREEMENT2`, and `TC_FATAL_TLS_DRIVER2`.
The due/XOR `TERMINAL_RAW3` rows store
`TC_TIMEOUT_LOCAL_COMMAND_DEADLINE2` and
`TC_FATAL_LOCAL_CLOCK_DISAGREEMENT2`; the due/XOR
`TERMINAL_READ_ZERO1` rows store `TC_TIMEOUT_LOCAL_COMMAND_DEADLINE2` and
`TC_FATAL_LOCAL_CLOCK_DISAGREEMENT2`.
The pre-I/O due/XOR rows store the same two position-matched decisive
symbols. They are matched results for the acknowledged attempt but prove
that no owner or driver effect began.
The two `READ_DEADLINE_ACCOUNTED` rows store, respectively,
`TC_TIMEOUT_TERMINAL_INGRESS_PROGRESS2` and
`TC_FATAL_LOCAL_CLOCK_DISAGREEMENT2`. Every result clears the pending
attempt/capability, advances the previous-result ID, and increments the exact
six deltas once, including an exact zero increment for either pre-I/O result.
It also validates the complete staging before-state against the DFA state and
replaces both staging members with the exact nested after-state/ID;
pre-I/O and owner-pre-driver results preserve them byte-for-byte. The initial
state is the canonical EMPTY staging object.
`TERMINAL_READ_PENDING` rejects every unrelated actor
mutation. Recovery at that stable phase follows the explicit unknown-effect
rule in Section 8.3.

`UNIT_NEED_MSG` admits exactly the same six message symbols and guards as
Section 7.3. Base/normalized/ACK variants enter the stored automatic phase or
the stored return phase. Fatal variants enter `TERMINAL`. The same 4,096
message-lineage limit applies.

The `UNIT_` automatic-output submachine copies only the Section 7.3 Pong
rows after prefixing each phase. Its literal symbols are `W_PONG2`,
`TLS_PONG1`, `KA_PONG2`, `KR_PONG_MORE2`, `KR_PONG_FINAL2`,
`TC_AUTO_PONG_UNKNOWN_DEADLINE2`,
`TC_AUTO_PONG_UNKNOWN_EFFECT2`, and `D_PONG1`. A completed Pong enters the
stored return phase. Automatic-output and WebSocket-attempt counters increment
before each effect and remain within the signed shutdown limits.

An unresolved automatic Pong uses paired
`TC_AUTO_PONG_UNKNOWN_DEADLINE2` or
`TC_AUTO_PONG_UNKNOWN_EFFECT2`, retaining the exact attempt/obligation
anchor. No `UNIT_*_CLOSE` phase or Close-output symbol exists: the pinned
CLOSING parser can neither emit a parser-failure Close nor echo a peer Close.
Raw V8 thereby changes one current unsafe local-shutdown branch:
The current one-event signer-less Pong terminalization is inadmissible.
Local-shutdown measurement stays disabled until the production actor routes
both OFF and ON through these paired convergence operations.

Deadline evidence is a literal Cartesian expansion, not a phase wildcard:

| Current phase | Evidence symbols admitted | Required decisive symbols in BOTH/XOR/EARLY order |
|---|---|---|
| `NEED_LOCAL_WS` | `DEADLINE_EVIDENCE_BOTH1`, `DEADLINE_EVIDENCE_XOR1`, `DEADLINE_EVIDENCE_EARLY1` | `TC_TIMEOUT_LOCAL_COMMAND_DEADLINE2`, `TC_FATAL_LOCAL_CLOCK_DISAGREEMENT2`, `TC_FATAL_TLS_DRIVER2` |
| `LOCAL_WS_NEED_TLS` | same three | same three |
| `NEED_HALF_CLOSE` | same three | same three |

Each row enters `NEED_DECISIVE_TERMINAL` with exactly the position-matched
symbol. These evidence rows require a qualified owner/driver clock seam to
have returned the corresponding durable evidence before any physical effect.
Their operation field is fixed by phase:

```text
NEED_LOCAL_WS       -> LOCAL_WEBSOCKET_CLOSE_PREPARATION
LOCAL_WS_NEED_TLS   -> LOCAL_WEBSOCKET_CLOSE_TLS_PREPARATION
NEED_HALF_CLOSE     -> TCP_WRITE_SHUTDOWN_TOKEN_PREPARATION
```

No other operation token is accepted. Every positive WebSocket/TLS
preparation and terminal-read result represented by this alphabet is committed
as its ordinary symbol before a later clock gate; a later gate cannot erase
or relabel that work. The private one-shot SHUT_WR token is deliberately not
a durable preparation symbol: `HATT1` is appended only after token preparation
and the second both-clock-allow gate. Token-preparation failure uses
`TC_FATAL_TCP_TOKEN_PREPARATION2`, and no syscall occurs before `HATT1`.
Terminal ingress never uses these legacy generic evidence symbols: it must
first commit `TERMINAL_READ_ATTEMPT1`, then one exact terminal-read result
symbol. The evidence rows are disjoint from the actor's own pre-effect clock
gates. The latter
expand literally as:

| Current phase | Both clocks due | Exactly one clock due |
|---|---|---|
| `NEED_LOCAL_WS` | `TC_TIMEOUT_LOCAL_COMMAND_DEADLINE2 -> TERMINAL` | `TC_FATAL_LOCAL_CLOCK_DISAGREEMENT2 -> TERMINAL` |
| `LOCAL_WS_NEED_TLS` | same | same |
| `WAIT_PEER_CLOSE` | same | same |
| `NEED_TLS_LOCAL_OP` | same | same |
| `POLL_READY` | same | same |

The `READ_DEADLINE_ACCOUNTED` rows are separately enumerated in the terminal
read table. There is no “stable terminal-ingress progress” placeholder in the
generated DFA.

After peer WebSocket Close, TLS close-notify transitions are:

| Current | Symbol | Guard/update | Next |
|---|---|---|---|
| `NEED_TLS_LOCAL_OP` | `TS_LOCAL1` | exact `LOCAL_CLOSE_NOTIFY` operation start | `TLS_LOCAL_STARTED` |
| `TLS_LOCAL_STARTED` | `TCPREP_LOCAL2` | ciphertext prepared plus `TLS_CLOSE_NOTIFY_PREPARED` | `TLS_CONTROL_SEND_READY` |
| `TLS_CONTROL_SEND_READY` | `TKA_LOCAL2` | caps/deadlines allow; exact offset/request | `TLS_CONTROL_SEND_PENDING` |
| `TLS_CONTROL_SEND_READY` | `TC_TIMEOUT_LOCAL_COMMAND_DEADLINE2` | both deadline domains due | `TERMINAL` |
| `TLS_CONTROL_SEND_READY` | `TC_FATAL_LOCAL_CLOCK_DISAGREEMENT2` | exactly one deadline domain due | `TERMINAL` |
| `TLS_CONTROL_SEND_PENDING` | `TKR_LOCAL_MORE2` | exact positive partial acceptance | `TLS_CONTROL_SEND_READY` |
| `TLS_CONTROL_SEND_PENDING` | `TKR_LOCAL_FINAL4` | final result/resolution plus TLS-notify-sent and accepted | `NEED_HALF_CLOSE` |
| `TLS_CONTROL_SEND_PENDING` | `TKF_LOCAL_TIMEOUT2` | conclusive timeout/no acceptance; require timeout convergence | `NEED_DECISIVE_TERMINAL` |
| `TLS_CONTROL_SEND_PENDING` | `TKF_LOCAL_FATAL2` | conclusive clock disagreement/no acceptance; require fatal convergence | `NEED_DECISIVE_TERMINAL` |
| `TLS_CONTROL_SEND_PENDING` | `TC_TLS_CONTROL_UNKNOWN_OUTCOME2` | current owner/driver reports literal `TLS_CONTROL_SEND_OUTCOME_UNKNOWN`; exact TLS obligation/attempt | `TERMINAL` |

The timeout/fatal `TKF` rows require
`TC_TIMEOUT_LOCAL_COMMAND_DEADLINE2` and
`TC_FATAL_LOCAL_CLOCK_DISAGREEMENT2`, respectively.
There is no TLS-control unknown-deadline/effect split. The current
owner/driver exposes exactly one ambiguous outcome,
`TLS_CONTROL_SEND_OUTCOME_UNKNOWN`, mapped to
`TC_TLS_CONTROL_UNKNOWN_OUTCOME2`; conclusive post-write-ahead deadline
evidence follows `TKF_LOCAL_TIMEOUT2` and its required decisive convergence.

TLS-operation failure symbols map exactly:

`TC_FATAL_TLS_DRIVER2` is
`TERMINAL2(FATAL, cause=TLS_OPERATION_DRIVER_ERROR)`; it is distinct from
the outer `V49E_SHUTDOWN_EFFECT_FAILURE` catch.

| Failure symbol | Required decisive symbol |
|---|---|
| `TLSFAIL_DRIVER1` | `TC_FATAL_TLS_DRIVER2` |
| `TLSFAIL_NOOBS_BOTH1` | `TC_TIMEOUT_TLS_SHUTDOWN2` |
| `TLSFAIL_NOOBS_XOR1` | `TC_FATAL_LOCAL_CLOCK_DISAGREEMENT2` |
| `TLSFAIL_NOOBS_EARLY1` | `TC_FATAL_TLS_DRIVER2` |
| `TLSFAIL_PROGRESS_BOTH1` | `TC_TIMEOUT_TLS_SHUTDOWN_PROGRESS2` |
| `TLSFAIL_PROGRESS_XOR1` | `TC_FATAL_LOCAL_CLOCK_DISAGREEMENT2` |
| `TLSFAIL_PROGRESS_EARLY1` | `TC_FATAL_TLS_DRIVER2` |
| `TLSFAIL_UNSENDABLE1` | `TC_FATAL_TLS_POST_HANDSHAKE_OUTPUT2` |

The generated transition rows are exactly:

| Current phase | Legal TLS-failure symbols |
|---|---|
| `TLS_LOCAL_STARTED` | `TLSFAIL_DRIVER1`, `TLSFAIL_NOOBS_BOTH1`, `TLSFAIL_NOOBS_XOR1`, `TLSFAIL_NOOBS_EARLY1` |
| `POLL_PENDING` | all eight table symbols |

Every row enters `NEED_DECISIVE_TERMINAL` and stores the table-matched
decisive symbol. The four progress/unsendable variants are illegal from
`TLS_LOCAL_STARTED`; no generic “TLS preparation/poll phase” row exists.

Half-close transitions are:

| Current | Symbol | Guard/update | Next |
|---|---|---|---|
| `NEED_HALF_CLOSE` | `HATT1` | token preparation and both deadline domains allow before syscall | `HALF_CLOSE_PENDING` |
| `NEED_HALF_CLOSE` | `TC_FATAL_TCP_TOKEN_PREPARATION2` | token preparation failed before syscall | `TERMINAL` |
| `NEED_HALF_CLOSE` | `TC_TIMEOUT_LOCAL_COMMAND_DEADLINE2` | both domains due before attempt | `TERMINAL` |
| `NEED_HALF_CLOSE` | `TC_FATAL_LOCAL_CLOCK_DISAGREEMENT2` | exactly one domain due | `TERMINAL` |
| `HALF_CLOSE_PENDING` | `HOK2` | `KERNEL_ACCEPTED` result plus `TCP_FIN_SENT` | `POLL_READY` |
| `HALF_CLOSE_PENDING` | `HNEG_PRE_SYSCALL1` | owner result `DEADLINE_EXPIRED_BEFORE_SYSCALL`; require exact timeout | `NEED_DECISIVE_TERMINAL` |
| `HALF_CLOSE_PENDING` | `HNEG_CLOCK1` | owner clock-disagreement result; require exact fatal | `NEED_DECISIVE_TERMINAL` |
| `HALF_CLOSE_PENDING` | `HNEG_ERROR1` | generic negative result; require exact fatal | `NEED_DECISIVE_TERMINAL` |
| `HALF_CLOSE_PENDING` | `TC_FATAL_HALF_CLOSE_UNKNOWN2` | syscall outcome ambiguous; no fabricated HNEG | `TERMINAL` |

The three `HNEG` rows require, respectively,
`TC_TIMEOUT_HALF_CLOSE_PRE_SYSCALL2`,
`TC_FATAL_LOCAL_CLOCK_DISAGREEMENT2`, and
`TC_FATAL_HALF_CLOSE_ERROR2`.

Peer-poll transitions are:

| Current | Symbol | Guard/update | Next |
|---|---|---|---|
| `POLL_READY` | `PS1` | poll count `<2`; increment once | `POLL_PENDING` |
| `POLL_PENDING` | `POBS_NOTIFY2` | peer notify true, EOF false, truncated false; includes `TLS_CLOSE_NOTIFY_RECEIVED` | `POLL_READY` |
| `POLL_PENDING` | `POBS_EOF_TRUNCATED1` | EOF true, peer notify false, truncated true | `NEED_DECISIVE_TERMINAL` |
| `POLL_PENDING` | `POBS_EOF_CLEAN2` | EOF true, peer notify true, truncated false; includes null-cause `TCP_EOF_RECEIVED` marker | `NEED_CLEAN_TERMINAL` |
| `NEED_CLEAN_TERMINAL` | `TC_CLEAN_NULLCAUSE2` | reducer proves all eight WS/TLS/TCP terminal facts | `TERMINAL` |

`POBS_EOF_TRUNCATED1` requires
`TC_TRUNCATED_NULLCAUSE2` next. Both
`TC_TRUNCATED_NULLCAUSE2` and `TC_CLEAN_NULLCAUSE2` have null cause code.
A process loss between the one-event truncated observation and its required
terminal convergence is a legal stable recovery prefix. The clean
observation/`TCP_EOF_RECEIVED` pair is one atomic two-record symbol.

The twelve literal limit-convergence symbols declared at the end of the
alphabet correspond one-to-one, in declaration order, with the twelve signed
limit dimensions in Section 8.3. A limit symbol
is legal only from the exact stable state immediately before the forbidden
next effect; the forbidden effect is not performed. `POLL_READY` at poll count
two uses `TC_FATAL_LIMIT_PEER_SHUTDOWN_POLL2` rather than a third `PS1`.

`TC_FATAL_SHUTDOWN_EFFECT2` is exactly
`TERMINAL2(FATAL, cause=V49E_SHUTDOWN_EFFECT_FAILURE)` and preserves the
current source cause token. It is legal only for a semantic target/driver/
parser failure proved by the DFA. Marker, probe, clock-observer,
serialization, or instrumentation failures cannot enter this catch: observer
hooks are total/no-throw and OFF/ON-neutral, and such failures seal/recover
measurement evidence without changing target behavior.

`TC_FATAL_SHUTDOWN_EFFECT2` is legal from these no-pending-effect phases only:

```text
NEED_LOCAL_WS
LOCAL_WS_NEED_TLS
LOCAL_WS_SEND_READY
LOCAL_WS_NEED_D
LOCAL_WS_NEED_ACCEPT
WAIT_PEER_CLOSE
READ_DEADLINE_ACCOUNTED
TERMINAL_UNIT_READY
UNIT_NEED_MSG
UNIT_NEED_W_PONG
UNIT_NEED_TLS_PONG
UNIT_SEND_READY_PONG
UNIT_NEED_D_PONG
NEED_TLS_LOCAL_OP
TLS_LOCAL_STARTED
TLS_CONTROL_SEND_READY
NEED_HALF_CLOSE
POLL_READY
```

The generated descriptor expands this list into one literal transition row
per state; there is no catch-all transition. It is forbidden while a
WebSocket send, TLS-control send, half-close syscall, or poll observation is
physically unresolved.

Every pre-effect decision uses one frozen total priority when multiple facts
are true:

```text
1  lost/uncertain authority, commit uncertainty, or startup recovery
2  both actor clock domains due
3  exactly one actor clock domain due
4  exhausted operational limit, in the twelve-cause declaration order
5  ordinary effect eligibility
```

Priority 1 selects epsilon measurement recovery. Priorities 2 and 3 select
their literal timeout/fatal branches. Priority 4 selects the first exhausted
dimension in declaration order. Every lower-priority eligibility/guard rule
contains explicit negations of all higher-priority conditions; the generated
eligibility-table proof checks this equality over the complete bounded state
domain. Thus simultaneous depleted allowances, or a depleted allowance at a
deadline, cannot yield different OFF/ON causes.

Returned success is legal only in `TERMINAL` with exact actor terminal
convergence, adopted termination, trace root, final counters, and V2 result.
Raised/cancelled/interrupted and recovery may finalize any complete-symbol
state. All unlisted state/symbol pairs reject. Current unbounded shutdown code
is not admitted until the twelve counters and all pre-effect guards above are
implemented in both OFF and ON execution.

### 7.5 Exact emergency-suffix phase map

The generated `EmergencySuffixProfileV1` expands every row below for every
literal phase and trigger. It never invents a transition absent from the
operation DFA.

Every non-epsilon suffix below has an additional exact guard:
same process, same live target writer/root capability, exact live actor
authority, and a conclusive physical-effect state. For every stable phase of
all four DFAs, `LOST_AUTHORITY`, `STARTUP_RECOVERY`, or
`COMMIT_ACKNOWLEDGEMENT_UNCERTAIN` instead maps to epsilon measurement
recovery. Recovery preserves the durable prefix, writes only the prebuilt V8
terminal/closure pair, removes the locator, and performs any later
actor/session convergence outside the measured target. It never appends a
missing failure, TC, or clean-convergence symbol into the target under a new
writer.

The trigger vocabulary is closed:

```text
EmergencyTriggerClassV1
  RETURNED
  TARGET_RAISED
  TARGET_CANCELLED
  TARGET_INTERRUPTED
  MEASUREMENT_OBSERVER_FAILURE
  OPERATIONAL_LIMIT
  POST_WRITE_AHEAD_DEADLINE
  POST_WRITE_AHEAD_CLOCK_DISAGREEMENT
  PHYSICAL_EFFECT_AMBIGUITY
  LOST_AUTHORITY
  COMMIT_ACKNOWLEDGEMENT_UNCERTAIN
  STARTUP_RECOVERY
```

Lifecycle-trigger mapping is literal where the trigger itself states the
target exit:

| Emergency trigger | Terminal trigger |
|---|---|
| `RETURNED` | `RETURNED` |
| `TARGET_RAISED` | `RAISED_EXCEPTION` |
| `TARGET_CANCELLED` | `CANCELLED` |
| `TARGET_INTERRUPTED` | `INTERRUPTED` |
| `MEASUREMENT_OBSERVER_FAILURE`, `LOST_AUTHORITY`, `COMMIT_ACKNOWLEDGEMENT_UNCERTAIN`, `STARTUP_RECOVERY` | `RECOVERED_ORPHAN` |

`OPERATIONAL_LIMIT`, both post-write trigger classes, and
`PHYSICAL_EFFECT_AMBIGUITY` do not have a global lifecycle mapping:
subscription dispatch and ingress may raise after convergence, while local
shutdown may return an adverse termination. Their exact terminal trigger and
path class are therefore explicit in each operation/phase/state/trigger
partition of the required emergency-suffix manifest. A suffix certificate
must use that partition mapping and may not choose another lifecycle class.

For each reachable bounded state, the generated profile evaluates every one
of these twelve classes. Specific rows below apply only through
pairwise-disjoint Boolean guards; one literal fallback row for each remaining
phase/class has an epsilon suffix. Therefore every reachable
`(state, trigger class)` has exactly one suffix record—never a prose wildcard.

ACK:

| Phase | Trigger | Suffix |
|---|---|---|
| `Q0`, `ACK_DUE_TERMINAL` | any measurement/runtime exit | epsilon |

Subscription:

| Phase | Trigger | Suffix |
|---|---|---|
| `SEND_PENDING` | post-write-ahead deadline | `UNKNOWN_APP_DEADLINE1` |
| `SEND_PENDING` | callback/result ambiguity | `UNKNOWN_APP_EFFECT1` |
| `Q0`, `INTENT`, `WIRED`, `TLS_READY`, `UNKNOWN_SEND`, `DONE`, `DIRECT_TERMINAL` | every other exit | epsilon |

Ingress:

| Phase | Trigger | Suffix |
|---|---|---|
| `SEND_PENDING_PONG` | post-write-ahead deadline | `UNKNOWN_PONG_DEADLINE1` |
| `SEND_PENDING_PONG` | callback/result ambiguity | `UNKNOWN_PONG_EFFECT1` |
| `SEND_PENDING_CLOSE` | conclusive post-write-ahead deadline/no acceptance | `KF_CLOSE_TIMEOUT2`, `TC_CLOSE_POSTFAIL_TIMEOUT2` |
| `SEND_PENDING_CLOSE` | conclusive post-write-ahead clock disagreement/no acceptance | `KF_CLOSE_FATAL2`, `TC_CLOSE_POSTFAIL_FATAL2` |
| `SEND_PENDING_CLOSE` | callback/result ambiguity | `TC_CLOSE_UNKNOWN_EFFECT2` |
| `NEED_TC_CLOSE_TIMEOUT` | conclusive timeout failure already committed | `TC_CLOSE_POSTFAIL_TIMEOUT2` |
| `NEED_TC_CLOSE_FATAL` | conclusive clock failure already committed | `TC_CLOSE_POSTFAIL_FATAL2` |
| every other named ingress phase | measurement-only failure, lost authority, or no unresolved effect | epsilon |

The last row is expanded into each remaining literal phase in the profile;
the profile cannot serialize `every other` as a row.

Local shutdown:

| Phase | Trigger | Suffix |
|---|---|---|
| `LOCAL_WS_SEND_PENDING` | conclusive post-write-ahead deadline/no acceptance | `KF_LOCAL_WS_TIMEOUT2`, `TC_TIMEOUT_LOCAL_COMMAND_DEADLINE2` |
| `LOCAL_WS_SEND_PENDING` | conclusive post-write-ahead clock disagreement/no acceptance | `KF_LOCAL_WS_FATAL2`, `TC_FATAL_LOCAL_CLOCK_DISAGREEMENT2` |
| `LOCAL_WS_SEND_PENDING` | callback/result ambiguity | `TC_LOCAL_WS_UNKNOWN_EFFECT2` |
| `UNIT_SEND_PENDING_PONG` | post-write-ahead deadline | `TC_AUTO_PONG_UNKNOWN_DEADLINE2` |
| `UNIT_SEND_PENDING_PONG` | callback/result ambiguity | `TC_AUTO_PONG_UNKNOWN_EFFECT2` |
| `TERMINAL_READ_PENDING` | acknowledged attempt, fresh post-ack pair `BOTH_DUE`, and physical effect provably not started | `TERMINAL_READ_PRE_IO_DUE1`, `TC_TIMEOUT_LOCAL_COMMAND_DEADLINE2` |
| `TERMINAL_READ_PENDING` | acknowledged attempt, fresh post-ack pair `CLOCK_XOR`, and physical effect provably not started | `TERMINAL_READ_PRE_IO_XOR1`, `TC_FATAL_LOCAL_CLOCK_DISAGREEMENT2` |
| `TERMINAL_READ_PENDING` | same-process read callback/result ambiguity after a `BOTH_ALLOW` effect capability was consumed and deterministic result replay fails | `TC_FATAL_TERMINAL_READ_UNKNOWN_EFFECT2` |
| `TERMINAL_READ_PENDING` | process loss, commit uncertainty, or owner-authority loss | epsilon and measurement recovery with `UNKNOWN_PENDING_TERMINAL_READ` |
| `READ_DEADLINE_ACCOUNTED` | both clocks due | `TERMINAL_INGRESS_FAIL_BOTH1`, `TC_TIMEOUT_TERMINAL_INGRESS_PROGRESS2` |
| `READ_DEADLINE_ACCOUNTED` | exactly one clock due | `TERMINAL_INGRESS_FAIL_XOR1`, `TC_FATAL_LOCAL_CLOCK_DISAGREEMENT2` |
| `READ_DEADLINE_ACCOUNTED` | neither clock due | `TC_FATAL_SHUTDOWN_EFFECT2` |
| `TLS_CONTROL_SEND_PENDING` | conclusive post-write-ahead deadline/no acceptance | `TKF_LOCAL_TIMEOUT2`, `TC_TIMEOUT_LOCAL_COMMAND_DEADLINE2` |
| `TLS_CONTROL_SEND_PENDING` | conclusive post-write-ahead clock disagreement/no acceptance | `TKF_LOCAL_FATAL2`, `TC_FATAL_LOCAL_CLOCK_DISAGREEMENT2` |
| `TLS_CONTROL_SEND_PENDING` | owner/driver `TLS_CONTROL_SEND_OUTCOME_UNKNOWN` | `TC_TLS_CONTROL_UNKNOWN_OUTCOME2` |
| `HALF_CLOSE_PENDING` | syscall outcome ambiguous | `TC_FATAL_HALF_CLOSE_UNKNOWN2` |
| `NEED_DECISIVE_TERMINAL` | conclusive prerequisite already committed | the one stored required decisive symbol |
| `NEED_CLEAN_TERMINAL` | clean marker already committed | `TC_CLEAN_NULLCAUSE2` |
| a stable pre-effect phase whose signed operational counter is exhausted | exact one of the twelve literal limit-convergence symbols |
| `POLL_PENDING` | unresolved TLS/owner poll effect | epsilon and recovery |
| `Q0`, `TERMINAL` | any exit | epsilon |
| every remaining named local phase with no unresolved physical effect or committed decisive prerequisite | `RETURNED`, `TARGET_RAISED`, `TARGET_CANCELLED`, `TARGET_INTERRUPTED`, or `MEASUREMENT_OBSERVER_FAILURE` | epsilon; seal/recover |

The descriptor expands the pre-effect limit row into a Cartesian list of
literal eligible phase, dimension, and suffix rows and proves the forbidden
next effect was not performed. An observer-only structural budget breach,
commit uncertainty, or lost actor authority maps to epsilon/recovery for all
four operations and never to a guessed target mutation.

## 8. Corrected operation contracts

### 8.1 Ingress V2 and independent oracle

Public BIO/SSL pending counters cannot prove that OpenSSL has not already
swallowed an incomplete TLS record. Raw V8 therefore requires a driver-owned
record-boundary ledger that is authoritative from the connection's first TLS
receive, including handshake records. Existing connections created without
that seam are ineligible; they cannot be upgraded from pending counters.

`TlsRecordBoundaryLedgerV1` has exactly:

```text
ledger_version = riskyieldmm_tls_record_boundary_ledger_v1
pre_session_connection_authority_id
driver_evidence_nonce_sha256
governed_clock_source_id
monotonic_clock_domain_id
kernel_socket_identity
writer_fence_token_sha256
writer_fence_generation
pre_session_connection_lease_id
transport_session_id | null
session_binding_status = UNBOUND_HANDSHAKE | BOUND_SESSION
socket_lease_id | null
session_lease_binding_id | null
connection_generation
splitter_active_from_first_tls_receive = true
tls_phase = HANDSHAKE | APPLICATION
handshake_subphase =
  EXPECT_SERVER_HELLO | ENCRYPTED_HANDSHAKE | null
compatibility_ccs_records_received
tls_handshake_trace_profile_id
ordered_tls_handshake_trace_records
tls_handshake_trace_root_sha256
tls_handshake_trace_canonical_bytes
tls_handshake_trace_start_anchor
tls_handshake_trace_start_anchor_id
tls_handshake_trace_bracket | null
tls_handshake_trace_bracket_id | null
ordered_tls_phase_transition_evidence_records
tls_phase_transition_evidence_root_sha256
tls_record_splitter_profile_id
ciphertext_stream_received_octets
ciphertext_stream_fed_octets
tls_records_fed_count
fed_tls_record_commitment_root_sha256
driver_staged_ciphertext_base64
driver_staged_ciphertext_octets
driver_staged_ciphertext_sha256
memory_bio_incoming_pending_octets
memory_bio_outgoing_pending_octets
ssl_plaintext_pending_octets
boundary_status =
  STABLE_RECORD_BOUNDARY | DRIVER_PARTIAL_RECORD |
  DRIVER_INVALID_TERMINAL | OPENSSL_ACTIVE
driver_fault_latched
driver_fault_code | null
driver_fault_evidence_id | null
last_stable_record_ordinal
tls_record_boundary_ledger_id
```

The pre-session lease and connection authority are minted at driver
construction, before the first handshake byte. They do not reuse the existing
session-scoped `socket_lease_id`, which cannot exist until a transport session
has been committed:

```text
pre_session_connection_lease_id =
  sha256_digest({
    "domain": "RiskYieldMMPreSessionConnectionLeaseV1V4_9F_RawV8",
    "kernel_socket_identity": exact immutable identity,
    "driver_evidence_nonce_sha256": exact constructor nonce,
    "writer_fence_token_sha256": exact constructor fence,
    "writer_fence_generation": exact constructor generation,
    "connection_generation": exact connection generation
  })
```

Both clock identities and all pre-session lease inputs are complete frozen
authority records available at driver construction and are preserved for the
lifetime of the ledger.
`UNBOUND_HANDSHAKE` requires a null session ID and
null session-scoped lease/binding ID and `tls_phase=HANDSHAKE`. At the existing
handshake-commit boundary one atomic transition sets the binding tag/session
ID/session-scoped lease/binding ID, TLS phase/subphase, and transition-
evidence array/root; it preserves the pre-session connection authority/lease,
cumulative counters, staging bytes, and fed-record root byte-for-byte.
Thereafter
`BOUND_SESSION` requires the exact committed session ID and existing
session-scoped socket lease and cannot revert.

The authority ID is exactly:

```text
sha256_digest({
  "domain": "RiskYieldMMTlsRecordBoundaryPreSessionAuthorityV1V4_9F_RawV8",
  "driver_evidence_nonce_sha256": exact ledger nonce,
  "governed_clock_source_id": exact ledger source,
  "monotonic_clock_domain_id": exact ledger domain,
  "pre_session_connection_lease_id": exact pre-session lease,
  "connection_generation": exact ledger generation,
  "tls_record_splitter_profile_id": exact ledger profile,
  "tls_handshake_trace_profile_id": exact trace profile
})
```

The one-way session binding is:

```text
session_lease_binding_id =
  sha256_digest({
    "domain": "RiskYieldMMPreSessionToSessionLeaseBindingV1V4_9F_RawV8",
    "pre_session_connection_authority_id": exact authority,
    "pre_session_connection_lease_id": exact pre-session lease,
    "kernel_socket_identity": exact immutable identity,
    "transport_session_id": exact committed session,
    "socket_lease_id": exact derived session-scoped lease,
    "connection_generation": exact generation
  })
```

The existing lease is derived only after session commit under its unchanged
session-scoped contract. Binding verifies the same kernel identity,
generation, owner/fence lineage, and cannot substitute a lease from another
pre-session connection.

Handshake starts at `EXPECT_SERVER_HELLO`, with zero compatibility-CCS count,
an empty transition-evidence array, and the exact empty transition root.
The frozen transition-authority rules alone may first enter
`ENCRYPTED_HANDSHAKE` and then atomically enter `APPLICATION` while binding
the committed session. The first transition records accepted
ServerHello/key-activation evidence; it is provisional until the second
record proves verified peer Finished and the committed handshake transcript.
`APPLICATION` requires `handshake_subphase=null`, exactly those two ordered
transition records and their recomputed root, the complete matching
handshake-trace bracket/ID, `BOUND_SESSION`, and a
compatibility-CCS count no greater than the profile maximum. A CCS rule
increments that count exactly once before feed and is illegal after peer
Finished. No rolling hash substitutes for the complete embedded evidence
records or their current guard facts.

One `TlsPhaseTransitionEvidenceRecordV1` has exactly:

```text
transition_ordinal
from_tls_phase
from_handshake_subphase | null
to_tls_phase
to_handshake_subphase | null
transition_event_kind
transition_evidence_shape_id
transition_evidence
transition_evidence_sha256
callback_boottime_ns
tls_handshake_trace_start_anchor_id
tls_handshake_trace_bracket_id | null
tls_phase_transition_evidence_id
```

Ordinals start at one, are contiguous, and the array has at most two records.
Record one is exactly
`HANDSHAKE/EXPECT_SERVER_HELLO ->
HANDSHAKE/ENCRYPTED_HANDSHAKE` with
`SERVER_HELLO_KEY_ACTIVATION_ACCEPTED`; record two is exactly
`HANDSHAKE/ENCRYPTED_HANDSHAKE -> APPLICATION/null` with
`PEER_FINISHED_VERIFIED_HANDSHAKE_COMMITTED`. Each complete evidence body
validates the one frozen `StrictEvidenceShapeDescriptorV1` named by the
matching transition-authority row. The first body embeds the exact accepted
ServerHello/transcript commitment, key-activation outcome, trace-record ID,
fed-record ordinal/root, and connection authority. The second embeds the verified peer
Finished/transcript commitment, prior transition ID, committed session ID,
trace-record ID, fed-record ordinal/root, and connection authority. The second guard proves
that its transcript commits the first event; only then is the provisional
ServerHello evidence authenticated. Both records carry the exact callback
BOOTTIME tick and same pre-handshake start-anchor ID. Record one requires a
null final bracket because it is sealed before handshake completion; record
two requires the complete bracket ID. The final bracket proves both ticks are
strictly ordered and inside it. No governed clock/source call occurs inside
the native TLS callback.

The evidence digest is raw SHA-256 of
`canonical_json_bytes(transition_evidence)`. The evidence ID is
`semantic_id()` under
`RiskYieldMMTlsPhaseTransitionEvidenceV1V4_9F_RawV8` over every preceding
record member. The rolling root is:

```text
transition_root_0 =
  sha256_digest({
    "domain": "RiskYieldMMTlsPhaseTransitionEvidenceRootEmptyV1V4_9F_RawV8",
    "pre_session_connection_authority_id": exact authority,
    "tls_record_splitter_profile_id": exact splitter profile,
    "tls_handshake_trace_profile_id": exact trace profile
  })

transition_root_i =
  sha256_digest({
    "domain": "RiskYieldMMTlsPhaseTransitionEvidenceRootStepV1V4_9F_RawV8",
    "previous_root_sha256": transition_root_(i-1),
    "transition_ordinal": i,
    "tls_phase_transition_evidence_id": exact record ID
  })
```

`EXPECT_SERVER_HELLO` requires the empty array/root;
`ENCRYPTED_HANDSHAKE` requires exactly record one/root one; and
`APPLICATION` requires exactly both records/root two. The array is therefore
self-contained and hermetic; an enum plus an unresolved evidence hash is
forbidden.

The source seam for those bodies is explicit.
`TlsHandshakeTraceProfileV1` has exactly:

```text
profile_version = riskyieldmm_tls_handshake_trace_profile_v1
implementation_kind =
  QUALIFIED_PINNED_OPENSSL_MESSAGE_CALLBACK_ADAPTER
runtime_identity
openssl_identity
installation_phase = BEFORE_MEMORY_BIO_WRAP
connection_role = TLS_CLIENT
ordered_traced_directions = [RECEIVED, SENT]
ordered_traced_content_types
callback_order_clock = LOCAL_CLOCK_BOOTTIME_NO_IO
maximum_trace_record_count = 256
maximum_one_handshake_message_octets = 1,048,576
maximum_aggregate_handshake_message_octets = 1,048,576
callback_failure_disposition = LATCH_CONNECTION_FAULT_AND_REJECT
trace_record_schema
tls_handshake_trace_profile_id
```

The adapter is installed before `wrap_bio`/`SSLObject` construction and before
the first handshake byte. It uses a pinned CPython/OpenSSL message callback
or an equivalently qualified native OpenSSL callback that exposes decrypted
handshake-message type and complete message bytes in causal order. Merely
calling `SSLObject.do_handshake()` and reading negotiated
version/cipher/certificate after success is insufficient.

One `TlsHandshakeTraceRecordV1` has exactly:

```text
trace_ordinal
direction
content_type
handshake_message_type | null
message_base64
message_octets
message_sha256
fed_tls_record_count_at_callback
fed_tls_record_commitment_root_sha256_at_callback
callback_boottime_ns
tls_handshake_trace_record_id
```

Ordinals are contiguous; messages are canonical padded base64, nonempty, and
match their count/digest; the two fed-record anchors equal the current
ledger; callback BOOTTIME ticks are positive, strictly increasing, and read
through a prebound no-I/O local syscall/primitive only. The callback performs
no chronyd query, owner-authority revalidation, filesystem/network operation,
await, allocation beyond its preallocated bound, or reentrant handshake call.
The trace ID is `semantic_id()` under
`RiskYieldMMTlsHandshakeTraceRecordV1V4_9F_RawV8`. Its array is strictly
ordinal-sorted and respects both profile bounds.
`tls_handshake_trace_canonical_bytes` is the exact canonical byte length of
the array. Its rolling root is:

```text
trace_root_0 =
  sha256_digest({
    "domain": "RiskYieldMMTlsHandshakeTraceRootEmptyV1V4_9F_RawV8",
    "pre_session_connection_authority_id": exact authority,
    "tls_handshake_trace_profile_id": exact profile,
    "tls_handshake_trace_start_anchor_id": exact start anchor
  })

trace_root_i =
  sha256_digest({
    "domain": "RiskYieldMMTlsHandshakeTraceRootStepV1V4_9F_RawV8",
    "previous_root_sha256": trace_root_(i-1),
    "trace_ordinal": i,
    "tls_handshake_trace_record_id": exact record ID
  })
```

Before entering `do_handshake`, the owner persists one complete
`TlsHandshakeTraceStartAnchorV1`:

```text
pre_session_connection_authority_id
tls_handshake_trace_profile_id
governed_clock_source_id
monotonic_clock_domain_id
before_observed_at
before_observed_monotonic_ns
before_boottime_ns
tls_handshake_trace_start_anchor_id
```

Its ID is `semantic_id()` under
`RiskYieldMMTlsHandshakeTraceStartAnchorV1V4_9F_RawV8`. It is available before
the first callback and remains byte-identical in every ledger. After
`do_handshake` succeeds, the owner completes one
`TlsHandshakeTraceBracketV1`:

```text
tls_handshake_trace_start_anchor
tls_handshake_trace_start_anchor_id
after_observed_at
after_observed_monotonic_ns
after_boottime_ns
tls_handshake_trace_root_sha256
tls_handshake_trace_bracket_id
```

The before/start and after wall/monotonic samples use the normal qualified
owner clock path; the BOOTTIME values are the position-matched members of
those governed samples. After is no earlier in wall time and strictly later
in both monotonic/BOOTTIME domains. Every callback tick lies in the closed BOOTTIME
interval and trace order agrees with tick order. The bracket ID is
`semantic_id()` under
`RiskYieldMMTlsHandshakeTraceBracketV1V4_9F_RawV8`. Before handshake
completion the start anchor is non-null while bracket members in the ledger
are null; successful transition to `APPLICATION` atomically stores the
complete bracket/ID. A bound session requires all four anchor/bracket members
non-null and mutually resolving.

Transition evidence references the exact trace record IDs/root prefix and
embeds the profile-qualified callback/engine acceptance result. The second
transition is legal only after successful certificate/path/hostname policy,
verified Finished, and successful `do_handshake`; those facts authenticate
the committed trace containing record one. Callback exception, missing or
out-of-order ServerHello/Finished, trace overflow, callback installation
after `wrap_bio`, transcript mismatch, or message bytes unavailable latches
the connection fault and makes it permanently ineligible. Raw V8 remains
NO-GO on a runtime for which this qualified seam cannot be frozen and
validated; it never fabricates transition bodies from post-handshake enums.

The resolved `TlsRecordSplitterProfileV1` is a frozen manifest input, not a
host-SSL default. It has the exact receive-side rows below:

| TLS phase | Outer type | Legacy-version handling | Declared fragment length | Extra rule |
|---|---:|---:|---:|---|
| `HANDSHAKE` | 20 | retain two bytes; ignore for receiver validity | 1 | complete body is exactly `0x01`; compatibility CCS only before peer Finished |
| `HANDSHAKE` | 21 | retain two bytes; ignore for receiver validity | 2 | exactly one plaintext Alert message before encrypted-handshake activation |
| `HANDSHAKE` | 22 | retain two bytes; ignore for receiver validity | `1..16,384` | plaintext handshake |
| `HANDSHAKE` | 23 | retain two bytes; ignore for receiver validity | `1..16,640` | encrypted handshake/application-protected record |
| `APPLICATION` | 23 | retain two bytes; ignore for receiver validity | `1..16,640` | all protected application, alert, and post-handshake content |

`TlsRecordSplitterProfileV1` has exactly:

```text
profile_version = riskyieldmm_tls_record_splitter_profile_v1
connection_role = TLS_CLIENT
tls_protocol_version = TLS_1_3
legacy_record_version_receiver_policy =
  RETAIN_TWO_OCTETS_IGNORE_FOR_VALIDITY_RFC8446
header_octets = 5
maximum_tls_plaintext_fragment_octets = 16,384
maximum_tls_ciphertext_fragment_octets = 16,640
maximum_tls_ciphertext_wire_octets = 16,645
ordered_phase_names = [APPLICATION, HANDSHAKE]
ordered_record_rule_records
ordered_phase_transition_authority_records
maximum_compatibility_ccs_records_before_peer_finished
tls_record_splitter_profile_id
```

Each record rule has exactly
`{tls_phase, outer_content_type, legacy_record_version_receiver_policy,
minimum_declared_fragment_octets, maximum_declared_fragment_octets,
exact_body_base64|null, admissibility_guard_rule_id}` and is strictly sorted
by `(tls_phase, outer_content_type, minimum_declared_fragment_octets,
maximum_declared_fragment_octets, admissibility_guard_rule_id)`. It reproduces
the five table rows exactly. Each phase-transition-authority row has exactly
`{transition_ordinal, from_tls_phase, from_handshake_subphase,
transition_event_kind, transition_evidence_shape_id, to_tls_phase,
to_handshake_subphase}`; rows are unique and strictly sorted by ordinal,
ordinals are exactly one and two, and their remaining values byte-equal the
two transition records specified above. Only exact verified
peer-Finished/handshake-commit evidence may enter `APPLICATION`; each shape ID
resolves one complete frozen `StrictEvidenceShapeDescriptorV1`. No row leaves it. The
compatibility-CCS maximum is a literal positive safe integer
derived from the pinned client handshake policy; its guard consumes one unit
per exact `0x01` body and rejects after the maximum. The profile ID is
`semantic_id()` over every preceding member under the literal profile domain.

The profile also fixes the client role, exact peer-Finished transition
authority, compatibility-CCS counter and transition rules, five-byte header
codec, `TLSPlaintext.length <= 2^14`, and
`TLSCiphertext.length <= 2^14 + 256`. Every row, counter transition, and
phase change is a complete closed descriptor body in the universe manifest;
an implementation-selected TLS phase/subphase is forbidden. The same
milestone splitter/conservation rules apply from the first handshake record.
This intentionally follows RFC 8446 receiver semantics: the two legacy
version octets are committed as evidence but never cause splitter rejection,
and a plaintext Alert record has exactly two fragment octets. Handshake
messages may span protected records, which is why the application-phase
post-handshake boundary rule below remains conservative. See
[RFC 8446 Section 5.1](https://www.rfc-editor.org/rfc/rfc8446.html#section-5.1).
The rolling record root is initialized from the literal empty list and
extends with each exact ordinal/wire-octet/hash tuple, including handshake
records. The ledger ID is
`semantic_id()` over every preceding member. `STABLE_RECORD_BOUNDARY`
requires empty driver staging, received octets equal fed octets, and a
completed owner/driver critical section. Public pending counters are
orthogonal exact observations: candidate admission requires all three zero,
but a terminal fault snapshot retains rather than erases a nonzero value.
`DRIVER_PARTIAL_RECORD` retains exact bounded bytes outside OpenSSL.
`DRIVER_INVALID_TERMINAL` retains the exact minimal invalid proof prefix and
is fault-latched; it cannot enter another read. `OPENSSL_ACTIVE` is never an
admission or durable state.

The record-root equations are:

```text
root_0 =
  sha256_digest({
    "domain": "RiskYieldMMTlsFedRecordRootEmptyV1V4_9F_RawV8",
    "pre_session_connection_authority_id": exact authority,
    "tls_record_splitter_profile_id": exact profile
  })

root_i =
  sha256_digest({
    "domain": "RiskYieldMMTlsFedRecordRootStepV1V4_9F_RawV8",
    "previous_root_sha256": root_(i-1),
    "record_ordinal": i,
    "tls_phase_at_feed": exact phase,
    "wire_octets": exact positive safe integer,
    "record_sha256": SHA256(exact wire bytes)
  })
```

`tls_records_fed_count=i`, ordinals are contiguous safe integers, and another
record is forbidden at the safe-integer maximum. `last_stable_record_ordinal`
is zero before any fed record; thereafter it equals the greatest fed ordinal
at whose completed critical-section exit the framing stage was empty. It
never exceeds `tls_records_fed_count` and changes only on such a framing-
stable exit; public pending state and the fault latch remain separate facts.

Every durable ledger satisfies:

```text
decoded_stage = canonical_base64_decode(driver_staged_ciphertext_base64)
len(decoded_stage) = driver_staged_ciphertext_octets
SHA256(decoded_stage) = driver_staged_ciphertext_sha256
ciphertext_stream_received_octets =
  ciphertext_stream_fed_octets + driver_staged_ciphertext_octets
last_stable_record_ordinal = tls_records_fed_count
```

Status truth is exhaustive:

| Status | Durable truth |
|---|---|
| `STABLE_RECORD_BOUNDARY` | stage empty; received=fed; driver critical section complete; public pending counters retain their exact values |
| `DRIVER_PARTIAL_RECORD` | stage is the exact valid 1..4-byte header prefix or 5..expected-1 header/body prefix under the frozen phase rule; no staged byte has been fed; public pending counters retain their exact values |
| `DRIVER_INVALID_TERMINAL` | stage is exactly the first phase/profile-invalid milestone proof: 1 byte for an inadmissible outer type, 5 bytes for a length/rule mismatch, or 6 bytes for a wrong one-byte CCS body; legacy-version octets never form an invalid proof; fault latch and decode code are set; no later transition |
| `OPENSSL_ACTIVE` | process-local critical-section state only; never serialized, hashed, used for admission, or returned |

Framing status and driver fault are orthogonal. `driver_fault_latched=false`
requires both fault members null. `true` requires one closed
`TerminalIngressDriverErrorCodeV1` whose producer is driver-origin and a
non-null evidence ID:

```text
driver_fault_evidence_id =
  sha256_digest({
    "domain": "RiskYieldMMTlsRecordBoundaryDriverFaultV1V4_9F_RawV8",
    "pre_session_connection_authority_id": exact authority,
    "driver_evidence_nonce_sha256": exact nonce,
    "tls_record_splitter_profile_id": exact profile,
    "driver_fault_code": exact code,
    "ciphertext_stream_received_octets": exact value,
    "ciphertext_stream_fed_octets": exact value,
    "tls_records_fed_count": exact value,
    "fed_tls_record_commitment_root_sha256": exact root,
    "driver_staged_ciphertext_octets": exact value,
    "driver_staged_ciphertext_sha256": exact digest,
    "memory_bio_incoming_pending_octets": exact value,
    "memory_bio_outgoing_pending_octets": exact value,
    "ssl_plaintext_pending_octets": exact value
  })
```

The latch changes only `false -> true`, never clears, and permanently forbids
candidate admission and further driver entry. Splitter invalidity requires
`TLS_RECORD_DECODE_FAILED`; WantWrite/outgoing bytes, nonspecial TLS failure,
partial-stage receive failure, and post-handshake-boundary uncertainty retain
their honest framing/pending state with their exact closed code. A framing
status that looks stable cannot override the fault latch.

For one driver-entered result, received increases by exact positive received
chunks, fed increases by the exact one admitted record or zero, record count
and root extend iff fed, and stage is exactly conservation remainder. The
ledger contains no per-read completion clock: the causally later actor result
owns the first post-effect observation pair. Consequently the complete
after-ledger and driver-core ID are constructible before owner return and
cannot depend on `POST_EFFECT_GATE_SEALED`. Pre-I/O and owner-pre-driver
results retain the complete ledger byte-for-byte. Every
authority/clock/session/lease/generation/profile/subphase/CCS/transition-
evidence member is unchanged except at its one explicitly authorized
handshake transition.

Both ingress and local-shutdown candidate creation bind the complete ledger
and ID and require `session_binding_status=BOUND_SESSION`,
`tls_phase=APPLICATION`, `STABLE_RECORD_BOUNDARY`,
`driver_fault_latched=false`, and all three public pending counters zero. A local-shutdown
candidate derives its first terminal staging state from this stable ledger:
terminal-local cumulative counters start at zero and staging is empty, while
the connection ledger retains its lifetime counters/root. Every subsequent
V8 feed goes through the same splitter. Each durable result embeds the
complete before-ID and after-ledger/ID; connection-ledger staging bytes after
the feed byte-equal terminal staging after the feed, and both transitions use
the same received/fed record deltas. A partial record therefore produces
`DRIVER_PARTIAL_RECORD`, and the next acknowledged read accepts that exact
ledger/staging pair rather than falsely demanding another stable boundary.
`OPENSSL_ACTIVE` is never persisted. A
differential test must split a record across reads until OpenSSL would report
BIO/SSL pending zero plus WantRead and prove admission rejects unless the
driver ledger retains the partial bytes.

The signed spec contains exact workload input and compact commitments:

```text
CapacityMeasurementIngressOperationSpecV2
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

Bounds are:

```text
input chunks                    <= 128
input octets                    <= 65,536
parser units                    <= 32,768
logical output frames           <= 32,768
one control-frame payload       <= 125 octets
aggregate logical payload       <= 65,536 octets
```

For `B <= 65,536` new bytes:

```text
empty retained tail:
  units <= floor(B / 2)

nonempty retained tail:
  units <= 1 + floor((B - 1) / 2)
```

Thus 32,768 is a parser type bound, not a promise that every legal input fits
the 48-MiB target-entry budget.

The candidate/attempt binds one exact
`CapacityMeasurementIngressOracleBaselineV2`:

```text
parser cursor/state/sequence/next-stream-octet identity
fragmented-message state and commitment
retained-tail identity/octet count/SHA-256
ordered retained RAW dependency IDs
expected next ingress sequence
driver and MemoryBIO pending counters
durable ingress buffer counters
automatic output/staged wire/TLS pending counters
flow_snapshot_id
input_source_mode = INITIAL_PENDING | SEALED_OWNER_PENDING
sealed_pending_input_id
sealed_pending_input_chunk_count
sealed_pending_input_octets
sealed_pending_input_batch_sha256
ingress_oracle_baseline_id
```

Baseline truth is literal:

```text
memory_bio_incoming_pending_octets = 0
memory_bio_outgoing_pending_octets = 0
ssl_plaintext_pending_octets = 0
protocol_output_chunks = 0
protocol_output_octets = 0
pending_send_eof = false
staged_websocket_wire_octets = 0
pending_tls_ciphertext_octets = 0
remaining_pending_tls_ciphertext_octets = 0
staged_tls_ciphertext_octets = 0
remaining_staged_tls_ciphertext_octets = 0
staged_tls_control_ciphertext_octets = 0
remaining_staged_tls_control_ciphertext_octets = 0

durable_ingress_buffer_octets = retained_ingress_tail_octets
has_complete_durable_unit = false
```

The durable ingress bytes are exactly the retained-tail bytes: their octet
count, SHA-256, retained-tail ID, and ordered RAW dependency IDs recompute
from the same sealed prefix. `pending_raw_chunks/pending_raw_octets` equal
the exact sealed input only for `SEALED_OWNER_PENDING`, and equal the exact
retained initial capability for `INITIAL_PENDING`; their batch hash and count
must equal the corresponding sealed-input members. No uncommitted third
buffer is permitted.

The two zeroed inbound TLS counters are causal admission guards, not merely
sizes. Raw V8 rejects before candidate persistence when MemoryBIO ciphertext
or already-decrypted SSL plaintext remains hidden outside the exact retained
tail and sealed pending input; counts alone are never treated as a commitment
to unknown bytes.

Before candidate persistence, under the existing runtime orchestration lock
and exact owner authority, the collector claims either the retained initial
pending input or one bounded owner read into a private one-shot
`SealedPendingIngressCapabilityV2`. It binds the session, driver nonce,
expected ingress sequence, exact ordered chunks, chunk count, octets, batch
hash, process/thread/loop/task, and owner identity. It appends no projection
record and is either consumed by the immediately following measured ingress
or forces owner abort; bytes are never silently discarded or returned to an
unmeasured caller.

Candidate admission compares that sealed input to the signed spec, runs the
independent parser oracle, and reserves the complete weighted DFA before the
candidate or target effect. Any input/oracle/budget mismatch rejects before
candidate persistence. The measured target is the private
consume-sealed-pending ingress path; it performs no new socket read and must
consume the exact capability once. This explicitly measures durable adoption,
parsing, application processing, and automatic output, not network receive
latency. A future receive-capacity operation requires its own causal contract.

The sealed record's exact identity payload is:

```text
transport_session_id
driver_evidence_nonce_sha256
socket_lease_id
connection_generation
writer_fence_token_sha256
writer_fence_generation
expected_ingress_sequence
input_source_mode
ordered_input_chunks_base64
input_chunk_count
input_octet_count
input_sha256
raw_ingress_batch_sha256
sealed_capability_nonce_sha256
```

The oracle-baseline identity payload is:

```text
transport_session_id
parser_cursor
parser_cursor_id
parser_state
cursor_sequence
next_stream_octet
fragmented_message_opcode | null
fragmented_message_payload_base64 | null
fragmented_message_octets
fragmented_message_sha256 | null
fragmented_message_parser_event_ids
retained_ingress_tail_id
retained_ingress_tail_base64
retained_ingress_tail_octets
retained_ingress_tail_sha256
ordered_retained_raw_dependency_ids
expected_next_ingress_sequence
input_source_mode
sealed_pending_input_id
tls_record_boundary_ledger
tls_record_boundary_ledger_id
driver_state
memory_bio_incoming_pending_octets
memory_bio_outgoing_pending_octets
ssl_plaintext_pending_octets
pending_raw_chunks
pending_raw_octets
durable_ingress_buffer_octets
has_complete_durable_unit
protocol_output_chunks
protocol_output_octets
pending_send_eof
staged_websocket_wire_octets
pending_tls_ciphertext_octets
remaining_pending_tls_ciphertext_octets
staged_tls_ciphertext_octets
remaining_staged_tls_ciphertext_octets
staged_tls_control_ciphertext_octets
remaining_staged_tls_control_ciphertext_octets
flow_snapshot_id
```

Both baseline byte members are canonical padded RFC-4648 base64.
Decoded `retained_ingress_tail_base64` has exactly the duplicated tail
octet count and digest. `fragmented_message_payload_base64` is null exactly
when its opcode is null; otherwise its decoded octets and digest equal the
fragment fields. Its parser-event tuple is empty exactly when the opcode is
null; otherwise it is receipt-ordered, unique, bounded by 4,096, and every ID
resolves to the already-durable fragment lineage. The same
byte/count/hash/nullability/lineage equations hold for every ingress and
local-shutdown DFA state. State updates may retain the
bytes only through these bounded members; IDs or hashes alone never stand in
for parser input.

Raw V8 ingress admission is restricted to a stable fragmentation boundary:
the baseline opcode and payload are null, octets are zero, digest is null,
and parser-event IDs are empty. Fragmentation may begin inside the measured
target, where every lineage event is then in the target span. Pre-candidate
fragment lineage is not silently looked up or added as an unbounded retained
dependency.

The expectation identity payload is:

```text
operation_spec_id
ingress_oracle_baseline_id
sealed_pending_input_id
expected_parser_unit_count
expected_completed_application_message_count
expected_consumed_new_input_octets
expected_final_parser_cursor_id
expected_final_retained_tail_octets
expected_final_retained_tail_sha256
expected_logical_output_frame_count
expected_logical_output_payload_octets
expected_logical_output_frames_sha256
```

Each ID is appended only after hashing every preceding exact member under its
literal Section 3.1 domain. The candidate and attempt both duplicate the three
IDs. The attempted branch also retains the complete
`SealedPendingIngressV2` record as a dependency, and the attempt embeds that
complete record, the complete baseline, the complete expectation, and the
complete precondition once. A replay verifier can therefore recompute the
sealed-input ID, including the exact chunks and sealed-capability nonce,
without process-local state. Candidate-only recovery does not claim that
ingress was consumed and requires no target replay.

`expected_logical_output_frames_sha256` preserves the existing domain-separated
semantic preimage for the exact ordered logical frames. The independent oracle
feeds opcode and canonical base64 payload members into an incremental
canonical-JSON encoder; it never materializes the frame tuple. Property tests
must prove byte-for-byte equality between this streamed digest and the
materialized canonical preimage at every boundary, including the empty
sequence and 32,768-frame type ceiling.

The V2 result contains:

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

The full target prefix, not these duplicated scalars alone, is authoritative.
Returned-success equality is exhaustive:

| Result member | Required equality |
|---|---|
| `sealed_pending_input_id` | attempt's embedded sealed input ID and expectation's sealed input ID |
| `ingress_oracle_baseline_id` | attempt's embedded baseline ID and expectation's baseline ID |
| `observed_consumed_new_input_octets` | `expected_consumed_new_input_octets` and the exact sealed-input octets consumed by durable RAW replay |
| `observed_parser_unit_count` | `expected_parser_unit_count` and the count of replayed `P/PC` symbols |
| `observed_completed_application_message_count` | `expected_completed_application_message_count` and the count of completed-message descriptors consumed by exact `MESSAGE` symbols |
| `final_parser_cursor_id` | `expected_final_parser_cursor_id` and the ID recomputed from the final durable parser cursor |
| `final_retained_tail_octets` | `expected_final_retained_tail_octets` and exact final tail bytes |
| `final_retained_tail_sha256` | `expected_final_retained_tail_sha256` and SHA-256 of exact final tail bytes |
| `final_retained_tail_id` | semantic ID recomputed from the final tail octets, digest, cursor, and ordered RAW dependencies |
| `observed_logical_output_frame_count` | `expected_logical_output_frame_count` and exact replayed logical Pong/Close frame count |
| `observed_logical_output_payload_octets` | `expected_logical_output_payload_octets` and the sum of exact replayed logical payload octets |
| `observed_logical_output_frames_sha256` | `expected_logical_output_frames_sha256` and the digest independently recomputed from exact ordered replayed frames |
| `ingress_progress_evidence_id` | exact current progress semantic ID recomputed from the complete durable prefix and every result member above |

The durable RAW replay must consume the sealed chunks exactly once in order,
with no hidden MemoryBIO/SSL bytes, and its final cursor/tail must equal the
independent oracle state. Each table row is checked in both OFF and ON modes;
one mismatch rejects returned success. Oracle comparison occurs after the
target path in both modes.
Online TLS-ciphertext comparison is forbidden.

### 8.2 Fresh subscription V2

The signed spec contains only pre-target policy:

```text
CapacityMeasurementSubscriptionDispatchSpecV2
  workload_family
  idempotency_key
  transport_subscription_policy_id
  adapter_policy_id
  expected_topic
  expected_operation = "subscribe"
  expected_logical_opcode = TEXT
  expected_dispatch_disposition
```

It does not contain an expected intent ID, nonce, request ID, command hash,
logical payload hash, logical payload octets, wire ID, or TLS ID.

The V2 precondition proves atomically:

```text
runtime state = SESSION_COMMITTED
intent mode = FRESH_CREATE
runtime intent, permit, dispatch window, and pending ACK all absent
no durable subscription intent for the session
no ACK binding
exact authorization operation-batch key absent
exact authorization idempotency key unused
policy/adapter/topic agree with the signed spec
parser OPEN, retained tail empty, no initial pending input
fragmented-message state empty
actor nonterminal, not fault-latched, not activating
no pending automatic output or outbound wire
application fence and writer fence exact
```

The returned V2 result contains generated facts:

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

Generated facts are replayed from `I` and the target prefix. They are results,
not sampler inputs.

`dispatch_window_evidence` is the complete strict nested current-production
12-member standalone envelope:

```text
canonicalization_version
measurement_schema_version
record_domain
transport_session_id
outbound_subscription_intent_id
socket_lease_id
monotonic_clock_domain_id
dispatch_started_at
dispatch_completed_at
dispatch_started_monotonic_ns
dispatch_completed_monotonic_ns
dispatch_window_evidence_id
```

The four envelope members and eight-field identity payload match the pinned
current type exactly. Both monotonic members are canonical unsigned-uint128
decimal strings, not JSON integers; numeric comparison occurs only after
strict decimal decoding. Its own semantic preimage recomputes exactly to the duplicated
`dispatch_window_evidence_id`; session/intent equal the candidate/result,
lease/domain equal authority, and both clock intervals are ordered and bound
the dispatch target. Wire/TLS IDs, KA/KR tuples, submitted total, completion,
and disposition are outer V2 result fields replayed independently from the
target prefix; they are not falsely injected into the existing nested type.
Neither representation is optional and any actual duplicated fact must agree.

Source-derived replay equalities are explicit:

```text
generated_request_id =
  I_SUB1.outbound_subscription_intent.request_id

generated_request_command_sha256 =
  I_SUB1.outbound_subscription_intent.command_sha256 =
  W_APP2.logical_payload_sha256

generated_logical_opcode = W_APP2.logical_opcode = TEXT
generated_logical_payload_sha256 = W_APP2.logical_payload_sha256
generated_logical_payload_octets = W_APP2.logical_payload_octets

len(canonical decoded subscription command bytes) =
  generated_logical_payload_octets
SHA256(canonical decoded subscription command bytes) =
  generated_request_command_sha256

I_SUB1.operation = "subscribe"
I_SUB1.topics = (signed expected_topic,)
I_SUB1.websocket_opcode = TEXT
canonical decoded subscription command =
  {"args": [signed expected_topic],
   "op": "subscribe",
   "req_id": generated_request_id}

TLS_APP1.plaintext_sha256 = W_APP2.wire_batch_sha256
TLS_APP1.plaintext_octets = W_APP2.wire_octets

D_APP1.outbound_wire_prepared_event_id = W_APP2 event ID
D_APP1.tls_ciphertext_prepared_event_id = TLS_APP1 event ID
D_APP1 ordered attempt/result IDs = exact target KA/KR chain
D_APP1.submitted_ciphertext_octets =
  sum(exact positive accepted octets in that chain)
```

The canonical command bytes are reconstructed from the strict intent/request
codec; no result-supplied byte string is trusted. Each equality is an
embedded semantic-relation rule and is tested by mutating every linked field
independently.

Kernel tuples have equal cardinality `1..256`; position `i` is one `KA/KR`
pair. Every ID is unique, belongs to the exact candidate session/fence, and
appears in target receipt order. Returned evidence requires
`COMPLETE_LOCAL_SUBMISSION`, a final `D`, and no unmatched attempt.

### 8.3 Local shutdown V2

The signed timeout, Close code/reason, and expected terminal outcome remain.
Every physical terminal owner read has a durable write-ahead before owner I/O
and exactly one durable result or an explicit unknown-effect outcome.

`TERMINAL_READ_ATTEMPT1` uses `ACTOR_SINGLE` to append
`TERMINAL_INGRESS_READ_ATTEMPT`. Its payload keys are exactly:

```text
local_shutdown_command_started_event_id
local_shutdown_command_id
read_ordinal
previous_terminal_ingress_read_result_event_id | null
terminal_tls_staging_before_id
tls_record_boundary_ledger_before_id
driver_evidence_nonce_sha256
expected_ingress_sequence
shutdown_deadline_at
shutdown_deadline_monotonic_ns
maximum_ciphertext_octets
maximum_plaintext_octets
maximum_socket_receive_calls
maximum_tls_records
maximum_tls_unwrap_iterations
maximum_zero_progress_iterations
target_span_budget_id
authorized_at
authorized_monotonic_ns
terminal_ingress_read_capability_id
```

The ordinary top-level actor event supplies, without duplication, the exact
subscription policy, session, physical-scope manifest, adapter policy,
capture partition, socket lease, connection generation, deployment bundle,
writer-fence token/generation, monotonic clock domain, driver policy,
sequence, predecessor, and record clocks. Its `recorded_at` is exactly
payload `authorized_at` and its `recorded_monotonic_ns` is exactly payload
`authorized_monotonic_ns`; the two copies cannot select different pre-attempt
branches. The durable authorization-capability ID is:

```text
sha256_digest({
  "domain": "RiskYieldMMTerminalIngressReadCapabilityV1V4_9F",
  "actor_authority": {
    "transport_subscription_policy_id": exact value,
    "transport_session_id": exact value,
    "physical_scope_manifest_id": exact value,
    "adapter_policy_id": exact value,
    "capture_partition_id": exact value,
    "socket_lease_id": exact value,
    "connection_generation": exact value,
    "deployment_bundle_id": exact value,
    "writer_fence_token_sha256": exact value,
    "writer_fence_generation": exact value,
    "monotonic_clock_domain_id": exact value,
    "driver_policy_id": exact value
  },
  "actor_sequence": exact attempt actor sequence,
  "previous_event_id": exact attempt predecessor,
  "local_shutdown_command_started_event_id": exact value,
  "local_shutdown_command_id": exact value,
  "read_ordinal": exact value,
  "previous_terminal_ingress_read_result_event_id": exact nullable value,
  "terminal_tls_staging_before_id": exact value,
  "tls_record_boundary_ledger_before_id":
    exact current connection boundary ledger,
  "driver_evidence_nonce_sha256": exact value,
  "expected_ingress_sequence": exact value,
  "shutdown_deadline_at": utc_iso(exact value),
  "shutdown_deadline_monotonic_ns": exact value,
  "maximum_ciphertext_octets": exact value,
  "maximum_plaintext_octets": exact value,
  "maximum_socket_receive_calls": exact value,
  "maximum_tls_records": exact value,
  "maximum_tls_unwrap_iterations": exact value,
  "maximum_zero_progress_iterations": exact value,
  "target_span_budget_id": exact value,
  "authorized_at": utc_iso(exact value),
  "authorized_monotonic_ns": exact value
})
```

At read ordinal one, the boundary ledger is the candidate's exact stable
application ledger and the terminal staging state is its derived empty
terminal-local state. At every later ordinal, the ledger-before ID equals the
prior acknowledged result's ledger-after ID and the staging-before ID equals
that result's staging-after ID. `STABLE_RECORD_BOUNDARY` and
`DRIVER_PARTIAL_RECORD` are legal read-entry states; the latter requires its
staged bytes/count/hash to byte-equal terminal staging before. `OPENSSL_ACTIVE`
is never legal or durable.

The six maximums are remaining allowances, not original plan ceilings.
Ciphertext/receive/TLS-record/unwrap/zero-progress allowances are positive;
plaintext is at least 16,384. The attempt is legal only when
`terminal_ingress_batch_count < maximum_terminal_ingress_batches`,
`authorized_at <` the exact payload `shutdown_deadline_at`, and
`authorized_monotonic_ns < shutdown_deadline_monotonic_ns`; any due/XOR state
uses the direct pre-read TC rows and no capability is minted. `read_ordinal`
starts at one and is contiguous; its previous-result
member is null exactly at one and otherwise equals the prior result actor
event. This first pair is only the write-ahead authorization gate. An
acknowledged attempt still cannot authorize owner I/O.

After the attempt receipt is durably acknowledged, the same qualified actor
samples one fresh governed wall/monotonic pair and classifies it exactly:

```text
BOTH_ALLOW =
  effect_ready_at < shutdown_deadline_at
  and effect_ready_monotonic_ns < shutdown_deadline_monotonic_ns

BOTH_DUE =
  effect_ready_at >= shutdown_deadline_at
  and effect_ready_monotonic_ns >= shutdown_deadline_monotonic_ns

CLOCK_XOR =
  exactly one of those two comparisons is due
```

For `BOTH_DUE` or `CLOCK_XOR`, it commits the corresponding matched pre-I/O
result below and then the position-matched decisive terminal symbol. It
does not mint an effect capability, call the owner, or mutate the socket/TLS
driver. The fresh wall time must be no earlier than authorization and the
fresh monotonic time must be strictly later; wall reversal or non-increasing
monotonic time rejects and seals measurement without owner I/O. Only
`BOTH_ALLOW` derives:

```text
terminal_ingress_read_effect_capability_id =
  sha256_digest({
    "domain":
      "RiskYieldMMTerminalIngressReadEffectCapabilityV1V4_9F",
    "terminal_ingress_read_attempt_event_id": exact attempt ID,
    "terminal_ingress_read_capability_id":
      exact durable authorization-capability ID,
    "effect_ready_at": utc_iso(exact fresh wall time),
    "effect_ready_monotonic_ns": exact fresh monotonic time
  })
```

and mints one private object-identity, one-shot physical-effect capability
carrying all four bound values. The actor passes that object to the qualified
owner. Its only lifecycle is
`NEW -> OWNER_CLAIMED -> DRIVER_ENTERED -> RETIRED`. At its one permitted
entry and before any await, the owner atomically claims `NEW`, then validates
authority, monotonic deadline, and every remaining signed allowance. An
owner-only negative result retires from `OWNER_CLAIMED` without driver entry.
The qualified driver accepts only that same `OWNER_CLAIMED` object and
atomically enters `DRIVER_ENTERED` immediately before its first driver
operation. A matched result or callback ambiguity retires it permanently.
This remains required when the eventual
deadline/no-observation or error result reports zero mutations. These
defenses cannot replace the actor's dual clock gate. Process-local context,
a copied token value, an event
whose receipt is unacknowledged, or the durable authorization-capability ID
alone cannot authorize I/O. If this post-ack clock sample itself fails, no
effect capability or I/O exists: measurement seals at the unmatched pending
attempt and uses the epsilon recovery rule below. It may not guess a deadline
classification.

Retirement retains one exact history tag:
`OWNER_PRE_DRIVER_RESULT_SEALED`, `DRIVER_CORE_RESULT_SEALED`, or
`DRIVER_ENTERED_WITHOUT_CORE_RESULT`. Re-entry to the first two returns only
the exact sealed core object and deterministic projection key;
`DRIVER_ENTERED_WITHOUT_CORE_RESULT` is physical unknown effect and can never
fabricate an owner-pre-driver result.

The lifecycle/action table is total:

| Current state/tag | Invocation | Exact action |
|---|---|---|
| `NEW` | first owner entry with the identical object | atomically set `OWNER_CLAIMED`; validate authority/deadline/allowances |
| `NEW` real object | copied/wrong object presented | reject that invocation without mutating the real capability |
| `OWNER_CLAIMED` | validation fails before driver | seal owner-pre-driver error, retire as `OWNER_PRE_DRIVER_RESULT_SEALED`; zero driver calls |
| `OWNER_CLAIMED` | first qualified driver entry | atomically set `DRIVER_ENTERED` immediately before the first driver operation |
| `OWNER_CLAIMED` | concurrent/repeated owner entry | reject with no driver or capability mutation |
| `DRIVER_ENTERED` | concurrent/repeated owner or driver entry while core absent | reject with no second physical operation |
| `RETIRED/OWNER_PRE_DRIVER_RESULT_SEALED` | same-process replay | return the exact sealed owner core and deterministic projection key |
| `RETIRED/DRIVER_CORE_RESULT_SEALED` | same-process replay | return the exact sealed driver core and deterministic projection key |
| `RETIRED/DRIVER_ENTERED_WITHOUT_CORE_RESULT` | any replay | return only unknown-effect recovery classification; never synthesize a result |

`OWNER_AUTHORITY_VALIDATION_FAILED` is legal for the identical object that
was claimed but never entered `DRIVER_ENTERED`; a copied/wrong object is a
separate pre-claim rejection and cannot alter the real object. Thus
in-flight re-entry rejects, while post-retirement replay of a sealed result is
idempotent. All owner-pre-driver rows have all six work deltas zero. No
retirement path erases a possibly performed effect.

Actor completion is a second, causally later one-way state machine:

```text
WAITING_FOR_CORE
  -> DRIVER_CORE_RESULT_SEALED | OWNER_PRE_DRIVER_RESULT_SEALED
  -> POST_EFFECT_GATE_SEALED
  -> DATA_COMMIT_GATE_SEALED       # DATA only
  -> ACTOR_RESULT_SEALED
```

Each state retains the complete prior object/pair. A same-process retry
continues from the latest state, never re-enters owner/driver I/O and never
resamples a sealed clock pair. Process loss before the final actor result is
durable uses the unmatched-attempt unknown-effect recovery; it cannot claim a
V2 success from lost process memory. Once `ACTOR_RESULT_SEALED` exists, only
the deterministic projection commit may be retried.

The matching `TERMINAL_INGRESS_READ_RESULT` actor payload is exactly:

```text
terminal_ingress_read_attempt_event_id
terminal_ingress_read_capability_id
local_shutdown_command_started_event_id
local_shutdown_command_id
read_ordinal
previous_terminal_ingress_read_result_event_id | null
terminal_tls_staging_before_id
tls_record_boundary_ledger_before_id
driver_evidence_nonce_sha256
effect_ready_at
effect_ready_monotonic_ns
pre_io_gate_outcome = BOTH_ALLOW | BOTH_DUE | CLOCK_XOR
terminal_ingress_read_effect_capability_id | null
driver_core_result_id | null
owner_pre_driver_result_id | null
pre_io_gate_evidence_id | null
sealed_owner_evidence_type =
  NONE | DEADLINE_NO_OBSERVATION |
  DEADLINE_AFTER_PROGRESS | DRIVER_ERROR | ACTOR_PRE_IO_GATE
operation | null
deadline_ns | null
kernel_socket_identity | null
expected_kernel_socket_identity | null
observed_kernel_socket_identity | null
owner_evidence_id | null
driver_evidence_id | null
driver_error_code | null
driver_error_class | null
error_origin = OWNER_PRE_DRIVER | DRIVER | null
read_outcome =
  DATA | ZERO_PLAINTEXT | DEADLINE_NO_OBSERVATION |
  DEADLINE_AFTER_PROGRESS | DRIVER_ERROR_NO_PROGRESS |
  DRIVER_ERROR_AFTER_PROGRESS | NOT_STARTED_DEADLINE |
  NOT_STARTED_CLOCK_DISAGREEMENT
ciphertext_octets_delta
plaintext_octets_delta
socket_receive_calls_delta
tls_records_delta
tls_unwrap_iterations_delta
zero_progress_iterations_delta
ciphertext_sha256 | null
plaintext_sha256 | null
raw_ingress_batch_sha256 | null
ordered_received_ciphertext_chunks_base64
ordered_received_ciphertext_chunks_sha256
fed_tls_record_ordinal | null
fed_tls_record_wire_octets
fed_tls_record_sha256 | null
terminal_tls_staging_after
terminal_tls_staging_after_id
tls_record_boundary_ledger_after
tls_record_boundary_ledger_after_id
observed_at
observed_monotonic_ns
post_effect_gate_outcome = BOTH_ALLOW | BOTH_DUE | CLOCK_XOR | null
commit_ready_at | null
commit_ready_monotonic_ns | null
commit_ready_gate_outcome = BOTH_ALLOW | BOTH_DUE | CLOCK_XOR | null
decisive_deadline_gate =
  PRE_IO | POST_EFFECT | COMMIT_READY | OUTCOME_SEMANTICS
terminal_ingress_read_evidence_id
```

For every driver-entered outcome, `driver_core_result_id` is sealed before
owner return and recomputes exactly as:

```text
sha256_digest({
  "domain": "RiskYieldMMTerminalIngressDriverCoreResultV1V4_9F",
  "terminal_ingress_read_attempt_event_id": exact ID,
  "terminal_ingress_read_capability_id": exact ID,
  "tls_record_boundary_ledger_before_id": exact value,
  "terminal_ingress_read_effect_capability_id": exact non-null ID,
  "read_outcome": exact tag,
  "sealed_owner_evidence_type": exact tag,
  "operation": exact nullable value,
  "deadline_ns": exact nullable value,
  "kernel_socket_identity": exact nullable value,
  "expected_kernel_socket_identity": exact nullable value,
  "observed_kernel_socket_identity": exact nullable value,
  "driver_evidence_id": exact nullable value,
  "driver_error_code": exact nullable value,
  "driver_error_class": exact nullable value,
  "error_origin": exact nullable tag,
  "ciphertext_octets_delta": exact value,
  "plaintext_octets_delta": exact value,
  "socket_receive_calls_delta": exact value,
  "tls_records_delta": exact value,
  "tls_unwrap_iterations_delta": exact value,
  "zero_progress_iterations_delta": exact value,
  "ciphertext_sha256": exact nullable value,
  "ordered_plaintext_chunks_base64": exact owner-result chunks,
  "ordered_plaintext_chunks_sha256": exact per-chunk digests,
  "plaintext_sha256": exact nullable value,
  "raw_ingress_batch_sha256": exact nullable value,
  "terminal_tls_staging_before_id": exact value,
  "ordered_received_ciphertext_chunks_base64": exact ordered chunks,
  "ordered_received_ciphertext_chunks_sha256": exact ordered digests,
  "fed_tls_record_ordinal": exact nullable ordinal,
  "fed_tls_record_wire_octets": exact value,
  "fed_tls_record_sha256": exact nullable digest,
  "terminal_tls_staging_after_id": exact value,
  "tls_record_boundary_ledger_after_id": exact value
})
```

The driver core deliberately excludes `owner_evidence_id` and all actor clock
pairs. The driver seals the complete physical result and after-ledger before
owner return; the owner then deterministically derives its deadline/error
evidence from that immutable core and the already-bound owner authority.
Finally the actor samples the post-effect pair and binds the core ID, owner
evidence ID, and clocks in `terminal_ingress_read_evidence_id`. A
recomputation test must construct the driver-core ID before the first actor
clock call and prove that changing any later owner/actor member cannot change
it.

An owner-pre-driver error instead has `driver_core_result_id=null` and a
non-null `owner_pre_driver_result_id`:

```text
sha256_digest({
  "domain": "RiskYieldMMTerminalIngressOwnerPreDriverResultV1V4_9F",
  "terminal_ingress_read_attempt_event_id": exact ID,
  "terminal_ingress_read_capability_id": exact ID,
  "terminal_ingress_read_effect_capability_id": exact non-null ID,
  "terminal_tls_staging_before_id": exact unchanged ID,
  "tls_record_boundary_ledger_before_id": exact unchanged ID,
  "driver_error_code": exact owner-origin code,
  "expected_kernel_socket_identity": exact nullable identity,
  "observed_kernel_socket_identity": exact nullable identity,
  "owner_evidence_id": exact owner-pre-driver evidence ID
})
```

For both `NOT_STARTED_*` outcomes, `driver_core_result_id`,
`owner_pre_driver_result_id`, and
`terminal_ingress_read_effect_capability_id` are null, so there is no owner
or driver-core result preimage and no physical-effect authority to replay. Their required
evidence ID is:

```text
pre_io_gate_evidence_id =
  sha256_digest({
    "domain":
      "RiskYieldMMTerminalIngressReadPreIOGateEvidenceV1V4_9F_RawV8",
    "terminal_ingress_read_attempt_event_id": exact attempt ID,
    "terminal_ingress_read_capability_id":
      exact durable authorization-capability ID,
    "local_shutdown_command_started_event_id": exact ID,
    "local_shutdown_command_id": exact ID,
    "read_ordinal": exact value,
    "shutdown_deadline_at": utc_iso(exact attempt value),
    "shutdown_deadline_monotonic_ns": exact attempt value,
    "authorized_at": utc_iso(exact attempt value),
    "authorized_monotonic_ns": exact attempt value,
    "effect_ready_at": utc_iso(exact value),
    "effect_ready_monotonic_ns": exact value,
    "gate_outcome": "BOTH_DUE" | "CLOCK_XOR"
  })
```

Every owner/driver outcome instead requires
`pre_io_gate_evidence_id=null`. The result event
does not retain plaintext chunks twice: for `DATA`, the composite
transaction's RAW record supplies them and projection recomputes the driver
core ID from that exact RAW; every other outcome requires an empty plaintext
chunk tuple. Received-ciphertext chunks remain present for every positive
`ciphertext_octets_delta`, including partial ZERO and error-after-progress,
because staging conservation cannot reconstruct them from RAW.
Both received-ciphertext arrays have the frozen
`maximum_items=16,645`, equal cardinality, and no null element. Every decoded
base64 chunk is canonical and nonempty, its position-matched digest is raw
SHA-256 of those octets, and:

```text
ciphertext_octets_delta = 0
  iff both received-ciphertext arrays are empty

ciphertext_octets_delta > 0
  iff 1 <= len(ordered_received_ciphertext_chunks_base64)
         <= min(socket_receive_calls_delta, 16,645)

sum(decoded chunk octets) = ciphertext_octets_delta <= 16,645
ciphertext_sha256 =
  SHA256(concatenation of decoded chunks in exact array order)
```

Every socket receive requests at most the exact bytes missing from the
current five-byte header milestone or declared record boundary. It therefore
cannot over-read into a second TLS record; one-byte positive returns establish
the hard array-cardinality maximum. The signed
`maximum_terminal_socket_receive_calls` remains an independently enforced
possibly smaller allowance. A positive chunk count greater than either
allowance, an empty chunk element, unequal tuple lengths, digest mismatch, or
aggregate greater than one 16,645-byte wire record rejects.
`terminal_ingress_read_evidence_id` is `semantic_id()` under the
literal Section 3.1 terminal-read-evidence domain over every preceding
result-payload member.

The result payload is one exact tagged union:

| Read outcome | Sealed evidence type and nullable-field truth |
|---|---|
| `DATA`, `ZERO_PLAINTEXT` | pre-I/O gate `BOTH_ALLOW`; effect capability and driver core present; owner-pre-driver result/pre-I/O evidence null; `NONE`; operation, deadline, all three socket-identity members, both owner/driver evidence IDs, error origin, and both driver-error members are null |
| `DEADLINE_NO_OBSERVATION` | gate `BOTH_ALLOW`; effect capability and driver core present; owner-pre-driver result/pre-I/O evidence null; `DEADLINE_NO_OBSERVATION`; operation is exactly `TERMINAL_CLOSE_INGRESS`; deadline/kernel/owner ID present; expected/observed identities, driver ID, origin, and error members null |
| `DEADLINE_AFTER_PROGRESS` | gate `BOTH_ALLOW`; effect capability and driver core present; owner-pre-driver result/pre-I/O evidence null; `DEADLINE_AFTER_PROGRESS`; operation is exactly `TERMINAL_CLOSE_INGRESS`; deadline/kernel/owner/driver IDs present; expected/observed identities, origin, and error members null |
| either `DRIVER_ERROR_*`, owner origin | gate `BOTH_ALLOW`; effect capability and owner-pre-driver result present; driver core/pre-I/O evidence null; `DRIVER_ERROR`; operation is exactly `TERMINAL_CLOSE_INGRESS`; origin `OWNER_PRE_DRIVER`; owner ID and closed code present; driver ID null; class null |
| either `DRIVER_ERROR_*`, driver origin | gate `BOTH_ALLOW`; effect capability and driver core present; owner-pre-driver result/pre-I/O evidence null; `DRIVER_ERROR`; operation is exactly `TERMINAL_CLOSE_INGRESS`; origin `DRIVER`; owner/driver IDs and closed code present; safe class present only for an allowed caught exception |
| `NOT_STARTED_DEADLINE` | pre-I/O gate `BOTH_DUE`; effect capability, driver core, and owner-pre-driver result null; pre-I/O evidence present; `ACTOR_PRE_IO_GATE`; operation is exactly `TERMINAL_CLOSE_INGRESS_PRE_IO_GATE`; deadline is the exact monotonic command deadline; every socket-identity/evidence/error/origin member null |
| `NOT_STARTED_CLOCK_DISAGREEMENT` | pre-I/O gate `CLOCK_XOR`; effect capability, driver core, and owner-pre-driver result null; pre-I/O evidence present; `ACTOR_PRE_IO_GATE`; operation is exactly `TERMINAL_CLOSE_INGRESS_PRE_IO_GATE`; deadline is the exact monotonic command deadline; every socket-identity/evidence/error/origin member null |

Every `BOTH_ALLOW` row requires both effect-ready clocks strictly before
their corresponding command deadlines and a recomputed effect-capability ID.
It also requires `observed_at >= effect_ready_at` and
`observed_monotonic_ns > effect_ready_monotonic_ns`.
Every owner/driver row classifies that first post-effect observation in
`post_effect_gate_outcome`. `DATA` alone has a strictly later commit-ready
pair and non-null commit-ready classification; every other row has all three
commit-ready members null. A pre-I/O row instead has a null post-effect
classification, null commit-ready members, and
`decisive_deadline_gate=PRE_IO`. `ZERO_PLAINTEXT` uses
`decisive_deadline_gate=POST_EFFECT`. Deadline/error rows use
`OUTCOME_SEMANTICS` after retaining their post-effect classification.
Every pre-I/O row requires the evidence ID above,
`observed_at=effect_ready_at`,
`observed_monotonic_ns=effect_ready_monotonic_ns`, all six work deltas zero,
all three byte hashes null, empty plaintext chunks, and the literal one-event
symbol `TERMINAL_READ_PRE_IO_DUE1` or `TERMINAL_READ_PRE_IO_XOR1`. Conversely,
those two symbols accept only their matching tagged-union row. The exact
gate comparisons are replayed from the retained local-shutdown command and
payload clocks.

Pre-I/O and owner-pre-driver rows additionally require staging before ID
equal after ID, an empty received-ciphertext chunk tuple, empty digest tuple,
null fed ordinal/hash, zero fed octets, and no staging-state mutation. Their
complete boundary-ledger after body and ID also byte-equal the before ledger
and ID.

For every driver-entered row, the complete
`tls_record_boundary_ledger_after` validates the frozen splitter profile and
its ID is `semantic_id()` over that exact body. Its connection authority,
session binding, lease, generation, phase, profile, and prior record-root
lineage equal the before ledger. Its stream counters advance by exactly the
same ciphertext/fed-record deltas as terminal staging, its staged bytes
byte-equal terminal staging after, and its record root extends exactly once
iff `tls_records_delta=1`. Empty staging selects
`STABLE_RECORD_BOUNDARY`; a valid incomplete record selects
`DRIVER_PARTIAL_RECORD`; an invalid proof prefix selects
`DRIVER_INVALID_TERMINAL`. Public pending counters are retained independently.
Every driver error that makes later reuse unsafe atomically sets the immutable
fault code/evidence latch, even when framing remains stable. A result cannot
persist `OPENSSL_ACTIVE`.

For no-observation deadline evidence, `owner_evidence_id` recomputes in the
current native domain:

```text
sha256_digest({
  "domain": "RiskYieldMMOwnerDeadlineExpiredNoObservationV4_9E",
  "transport_session_id": exact session,
  "kernel_socket_identity": exact identity,
  "driver_evidence_nonce_sha256": exact nonce,
  "operation": "TERMINAL_CLOSE_INGRESS",
  "deadline_ns": exact deadline
})
```

For positive-ciphertext deadline evidence:

```text
driver_evidence_id =
  sha256_digest({
    "domain": "RiskYieldMMDeadlineExpiredAfterProgressV4_9E",
    "driver_evidence_nonce_sha256": exact nonce,
    "operation": "TERMINAL_CLOSE_INGRESS",
    "deadline_ns": exact deadline,
    "ciphertext_octets_received": ciphertext_octets_delta,
    "ciphertext_sha256": exact digest
  })

owner_evidence_id =
  sha256_digest({
    "domain": "RiskYieldMMOwnerDeadlineExpiredAfterProgressV4_9E",
    "transport_session_id": exact session,
    "kernel_socket_identity": exact identity,
    "driver_evidence_nonce_sha256": exact nonce,
    "operation": "TERMINAL_CLOSE_INGRESS",
    "deadline_ns": exact deadline,
    "ciphertext_octets_received": ciphertext_octets_delta,
    "ciphertext_sha256": exact digest,
    "driver_evidence_id": exact driver_evidence_id
  })
```

Raw V8 introduces closed driver/owner error-evidence domains rather than
classifying an arbitrary exception from process memory:

```text
TerminalIngressDriverErrorCodeV1
  KERNEL_RECEIVE_FAILED
  TLS_RECORD_DECODE_FAILED
  TLS_UNWRAP_FAILED
  TLS_POST_HANDSHAKE_OUTPUT_DETECTED
  TLS_POST_HANDSHAKE_BOUNDARY_UNPROVABLE
  TLS_CLOSE_NOTIFY_BEFORE_WEBSOCKET_CLOSE
  TCP_EOF_BEFORE_TLS_CLOSE_NOTIFY
  SOCKET_IDENTITY_CHANGED
  DRIVER_STATE_INVARIANT_FAILED
  OWNER_AUTHORITY_VALIDATION_FAILED
```

```text
driver_evidence_id =
  sha256_digest({
    "domain": "RiskYieldMMTerminalIngressDriverErrorV1V4_9F",
    "driver_evidence_nonce_sha256": exact nonce,
    "operation": "TERMINAL_CLOSE_INGRESS",
    "deadline_ns": exact deadline,
    "kernel_socket_identity": exact nullable identity,
    "expected_kernel_socket_identity": exact nullable identity,
    "observed_kernel_socket_identity": exact nullable identity,
    "driver_error_code": exact closed code,
    "driver_error_class": exact nullable safe class,
    "error_origin": "DRIVER",
    "ciphertext_octets_delta": exact value,
    "ciphertext_sha256": exact nullable digest,
    "socket_receive_calls_delta": exact value,
    "tls_records_delta": exact value,
    "tls_unwrap_iterations_delta": exact value,
    "zero_progress_iterations_delta": exact value
  })

owner_evidence_id =
  sha256_digest({
    "domain": "RiskYieldMMTerminalIngressOwnerDriverErrorV1V4_9F",
    "transport_session_id": exact session,
    "socket_lease_id": exact lease,
    "connection_generation": exact generation,
    "terminal_ingress_read_effect_capability_id":
      exact physical-effect capability,
    "driver_evidence_id": exact driver_evidence_id
  })

owner-only owner_evidence_id =
  sha256_digest({
    "domain":
      "RiskYieldMMTerminalIngressOwnerPreDriverErrorV1V4_9F",
    "transport_session_id": exact session,
    "socket_lease_id": exact lease,
    "connection_generation": exact generation,
    "terminal_ingress_read_attempt_event_id": exact attempt,
    "terminal_ingress_read_effect_capability_id":
      exact physical-effect capability,
    "driver_error_code": exact owner-origin code,
    "expected_kernel_socket_identity": exact nullable identity,
    "observed_kernel_socket_identity": exact nullable identity,
    "error_origin": "OWNER_PRE_DRIVER"
  })
```

The reachable source-site mapping is literal; production uses typed
sentinels, never exception-message matching:

| Closed code | Exact admitted producer/condition | Origin | Class retention |
|---|---|---|---|
| `OWNER_AUTHORITY_VALIDATION_FAILED` | copied/wrong/unconsumed-invalid effect capability; actor/session/fence/lease mismatch; active outbound artifact; unbound or fault-latched driver before driver entry | `OWNER_PRE_DRIVER`; driver evidence null | null |
| `SOCKET_IDENTITY_CHANGED` | expected and observed owner identities are both available and unequal at the owner snapshot or driver current-socket assertion | owner snapshot -> `OWNER_PRE_DRIVER`; driver assertion -> `DRIVER` | null |
| `KERNEL_RECEIVE_FAILED` | non-timeout caught selector/readiness/`recv` exception; `BlockingIOError` and `InterruptedError` remain retries | `DRIVER` | exact sanitized caught class |
| `TLS_UNWRAP_FAILED` | caught nonspecial `ssl.SSLError` after excluding WantRead, WantWrite, ZeroReturn, and SSLEOF | `DRIVER` | exact sanitized caught class |
| `TLS_RECORD_DECODE_FAILED` | V8 splitter rejects an inadmissible outer type, an over-profile declared length or phase/admissibility guard, a wrong exact one-byte compatibility-CCS body, or an exhausted CCS-count guard before feed; the retained proof is the exact phase-specific 1/5/6-byte milestone | `DRIVER` | null |
| `TLS_POST_HANDSHAKE_OUTPUT_DETECTED` | pending outgoing TLS bytes or `SSLWantWriteError` while terminal ingress reads | `DRIVER` | null |
| `TLS_POST_HANDSHAKE_BOUNDARY_UNPROVABLE` | one complete protected record was fed, `SSLObject.read` produced no application plaintext and no conclusive close/error, and the pinned runtime exposes no authenticated TLS post-handshake message-boundary seam | `DRIVER` | null |
| `TLS_CLOSE_NOTIFY_BEFORE_WEBSOCKET_CLOSE` | `SSLZeroReturnError` or zero plaintext while still awaiting peer WebSocket Close | `DRIVER` | null |
| `TCP_EOF_BEFORE_TLS_CLOSE_NOTIFY` | kernel `recv()` returns EOF or `SSLEOFError` before authenticated close-notify | `DRIVER` | null |
| `DRIVER_STATE_INVARIANT_FAILED` | driver-internal wrong state, complete durable unit at read entry, missing actor lock, impossible allowance/counter, or a nonbytes value detected and sealed inside the typed driver result boundary | `DRIVER` | null |

For `SOCKET_IDENTITY_CHANGED`, the single
`kernel_socket_identity` member is null, both expected/observed members are
present and unequal, and the origin selects the evidence preimage. For every
other error those two members are null; a driver-origin row carries the exact
current `kernel_socket_identity`, while an owner-origin authority row has it
null. `DRIVER_ERROR_AFTER_PROGRESS` is selected iff
`ciphertext_octets_delta > 0`; otherwise it is
`DRIVER_ERROR_NO_PROGRESS`, regardless of other positive work counters.
Every error has zero plaintext and null plaintext/RAW hashes.

`TimeoutError` maps only to one of the two deadline outcomes. Allowance
exhaustion maps to `ZERO_PLAINTEXT` plus the dimension limit convergence, or
to its direct pre-attempt limit; cancellation/interruption is not coerced
into an error code. Any site/class absent from the table uses
unknown-effect/recovery rather than the nearest code.

Step 2 embeds exactly this vocabulary, source-site table, and the existing
safe exception-class sanitizer. The owner holds its exclusive authority,
lease, and socket-identity snapshot across driver entry, result sealing, and
return. All fallible post-return authority checks are moved before I/O; a
defensive post-return assertion failure is unknown effect, not `DATA` or an
owner error. This makes owner-origin errors structurally pre-driver.

`DATA` requires positive plaintext, positive newly received ciphertext, both
hashes, exact RAW batch equality, and `TERMINAL_RAW3`. Local-shutdown/first-
read entry and every acknowledged continuation have no hidden MemoryBIO or
`SSLObject.pending()` plaintext, so buffered unaccounted input is
inadmissible.
The bounded V8 owner read returns `DATA` immediately after the first positive
plaintext chunk becomes available. After that successful `SSLObject.read`
return, it performs no further fallible TLS, receive, drain, or authority
operation before sealing the typed DATA result. Fault injection at every old
would-have-drained site must prove those sites are not called. If a future
implementation needs to carry a condition discovered after positive
plaintext, it must add a closed durable deferred-condition field and a
next-attempt transition first; it may not silently defer an unrecorded
condition. An outer caller that receives an invalid/malformed typed returned
object has possible effect and enters unknown-effect recovery; it cannot
rewrite the event as `DRIVER_STATE_INVARIANT_FAILED`. Therefore every admitted
deadline/driver/pre-I/O result has exactly zero plaintext, and this production
behavior is a mandatory differential test against the independent oracle.
`ZERO_PLAINTEXT` requires zero
plaintext, null plaintext/RAW hashes, at least one bounded physical-work
delta, and `TERMINAL_READ_ZERO1`. Deadline/driver outcomes require zero
plaintext and a null RAW hash. Protocol progress means exactly
`ciphertext_octets_delta > 0`; NO_OBSERVATION/NO_PROGRESS require zero
ciphertext but may have positive socket-call, unwrap, or zero-progress
deltas. They use the corresponding one-receipt result symbol.
`ciphertext_sha256` is present iff ciphertext octets are positive and hashes
the exact ordered ciphertext bytes. `plaintext_sha256` is present iff
plaintext is positive and hashes concatenated ordered plaintext chunks; every
per-chunk digest hashes its exact decoded chunk. The RAW batch digest uses the
existing exact ordered-decrypted-chunks domain. All deltas are nonnegative
safe integers, never
exceed the attempt's remaining allowances, and each cumulative counter is
the exact sum of the acknowledged result chain. `terminal_ingress_batch_count`
is the V8 terminal-read-attempt count and increments once at
`TERMINAL_READ_ATTEMPT1`; the six read-derived counters increment only from
its matched result event.

The result actor event's top-level `recorded_at` and
`recorded_monotonic_ns` equal the payload's `observed_at` and
`observed_monotonic_ns`. For `DATA`, the result event uses the first governed post-effect clock and
the RAW record uses the second, strictly later governed clock, preserving the
current actor-chain and RAW-clock invariants. A read that consumed ciphertext
and then hit a deadline/error commits its result before any failure event and
decisive terminal transition. No process-local
`TerminalIngressReadOutcomeV49E` is replay authority.

Post-read deadline classification is ordered and cannot erase an earlier
decision. For `DATA`, the first post-effect pair is decisive whenever it is
`BOTH_DUE` or `CLOCK_XOR`; the second RAW/commit-ready pair is sampled and
retained to seal the exact DATA transaction but cannot overwrite that first
classification. Only when the first pair is `BOTH_ALLOW` does the commit-ready
pair decide. In that branch `decisive_deadline_gate=COMMIT_READY`; otherwise
it is `POST_EFFECT`. `ZERO_PLAINTEXT` has no second pair and its result-event
pair decides. A decisive `BOTH_ALLOW` permits parser/next-read progress,
`BOTH_DUE` requires `TC_TIMEOUT_LOCAL_COMMAND_DEADLINE2`, and `CLOCK_XOR`
requires `TC_FATAL_LOCAL_CLOCK_DISAGREEMENT2`. This preserves both current
post-read and commit-ready gates without allowing clock lag to turn a first
XOR into a later timeout.

If same-process callback/result ambiguity follows an acknowledged attempt
whose `BOTH_ALLOW` effect capability was consumed,
the actor first replays the deterministic result idempotency key. If absent
and the exact sealed result object remains, it may retry only the projection
commit, never owner I/O. Otherwise it commits
`TC_FATAL_TERMINAL_READ_UNKNOWN_EFFECT2` with kind `FATAL`, cause
`TERMINAL_INGRESS_READ_EFFECT_WITHOUT_DURABLE_RESULT`, and the exact unmatched
attempt anchor. A `BOTH_DUE`, `CLOCK_XOR`, or failed post-ack clock sample
cannot use this physical-effect-unknown branch because no effect capability
or owner I/O existed. At startup, after owner-authority loss, or after that
clock-sample failure,
`TERMINAL_READ_PENDING` has an epsilon measurement-recovery suffix:
finalization records `UNKNOWN_PENDING_TERMINAL_READ`, treats all read-derived
counters as lower bounds, and cannot emit a V2 success result. Only after the
Raw V8 locator is removed may actor/session recovery converge outside the
target with cause `RECOVERY_WITHOUT_TERMINAL_INGRESS_READ_OUTCOME`. Recovery
never fabricates deltas.

The V2 result binds the complete bounded shutdown trace compactly:

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

The attempt tuple has cardinality
`0..maximum_terminal_ingress_batches`. On a successful returned V2 result,
the result tuple has equal cardinality and pairs by position; every attempt
has exactly one result and no unknown-effect branch. The two terminal RAW
tuples have equal cardinality
`0..maximum_terminal_ingress_batches`, form the exact `DATA` subsequence of
the result tuple, and pair by position. Parser-transition IDs have cardinality
`0..maximum_terminal_ingress_parser_units` and occur in receipt order. All
convenience IDs are unique and are derived indexes into the authoritative
target prefix.

`final_terminal_tls_staging_state_id` equals the last acknowledged read
result's after ID, or the canonical initial EMPTY state ID when there were no
reads. A clean returned shutdown requires its resolved state `EMPTY`;
adverse/timeout results may retain one bounded partial or terminal staging
state. The compact ID and complete read events must agree.

For every target outer batch, replay constructs one strict trace step:

```text
ShutdownTraceStepV1
  step_ordinal
  symbol
  native_operation_token
  idempotency_key
  request_hash
  first_receipt_sequence
  last_receipt_sequence
  ordered_record_ids
  counter_snapshot_after
  shutdown_trace_step_id
```

`counter_snapshot_after` is the strict fixed 12-key map matching the twelve
`final_*` counters above. The step ID is `semantic_id()` under the literal
shutdown-step domain over all preceding members. The root is:

```text
shutdown_trace_root_sha256 =
  sha256_digest({
    "domain": "RiskYieldMMA2MShutdownTraceRootV1V4_9F_RawV8",
    "ordered_shutdown_trace_step_ids": [all step IDs in receipt order]
  })
```

The operation result stores only the count, root, final counters, and bounded
convenience IDs; the complete step bodies are deterministically reconstructed
from the retained target `operation_batches` and projection entries. Replay
requires contiguous step ordinals, exact DFA transitions, exact batch
request/result codecs, and a final counter snapshot equal to the result.
This binds local-WS, terminal-message/automatic-output, TLS-control,
half-close, poll, observation, failure, and decisive-terminal events. The
generator materializes the complete V2 result including every convenience
tuple and requires:

```text
len(canonical_json_bytes(complete operation result evidence))
  <= 524,288
```

This is the current breaking-schema operation-result-evidence ceiling. It is
distinct from the 65,536-byte ceiling on each target
`operation_batches.result_blob`. A plan whose selected terminal-read/parser
limits make the complete V2 result exceed 524,288 bytes is rejected before
candidate creation.

The plan declares:

```text
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
maximum_peer_shutdown_polls = 2
```

Required relationships are:

```text
terminal plaintext octets
  <= 16,384 * terminal batches

terminal parser units
  <= floor(terminal plaintext octets / 2)

terminal parser units
  <= 4,096

terminal TLS records
  <= terminal batches

terminal automatic outputs
  <= terminal parser units

websocket send attempts
  <= 256 * (1 + terminal automatic outputs)

TLS-control send attempts <= 256
peer-shutdown polls       <= 2
```

Ciphertext, receive-call, TLS-record, unwrap-iteration, and zero-progress
ceilings are positive values frozen in each preflight/manifest-selected plan
coordinate whose weighted worst case fits the same target count/byte budget.
The bound generator only evaluates those immutable coordinate values; it
neither selects nor changes them. They are not inferred from plaintext.

The batch, octet, parser, automatic-output, WebSocket-send, and TLS-send
limits likewise remain preflight/manifest-selected frozen plan values. A
parser plan may freeze fewer than 4,096 units but never more: this fixed
protocol upper bound prevents one fragmented message from exceeding the existing
`MESSAGE.source_parser_event_ids` cardinality before its final commit. The
earlier candidate value of 64 batches is not frozen; every selected value
still requires weighted-DFA and 48-MiB target-entry proof.

The runtime-to-actor-to-owner-to-driver terminal-read API is extended with
exact remaining ciphertext, plaintext, receive-call, TLS-record,
unwrap-iteration, and zero-progress allowances. It may return at most
`min(16,384, remaining_plaintext)` plaintext octets and reports exact consumed
counters. If the qualified owner/driver cannot enforce those arguments, local
shutdown measurement remains disabled.

The fixed TLS 1.3 staging limit is:

```text
MAXIMUM_TERMINAL_TLS_STAGED_CIPHERTEXT_OCTETS = 16,645
```

This is one five-byte TLSCiphertext header plus the pinned TLS 1.3 maximum
`2^14 + 256` encrypted-record octets. One
`TerminalIngressTlsCiphertextStagingStateV1` is durably nested in every read
result and has exactly:

```text
state_version = riskyieldmm_terminal_ingress_tls_staging_v1
transport_session_id
socket_lease_id
connection_generation
driver_evidence_nonce_sha256
ciphertext_stream_received_octets
ciphertext_stream_fed_octets
tls_records_fed_count
next_tls_record_ordinal
staging_status =
  EMPTY | HEADER_INCOMPLETE | BODY_INCOMPLETE |
  COMPLETE_UNFED | INVALID_TERMINAL
staged_record_stream_start_octet
staged_ciphertext_base64
staged_ciphertext_octets
staged_ciphertext_sha256
declared_encrypted_record_octets | null
expected_record_wire_octets | null
invalid_proof_prefix_octets | null
terminal_tls_staging_state_id
```

Base64 is canonical padded RFC-4648 and the digest is raw SHA-256 of its
decoded bytes, including SHA-256(empty). Exact equations are:

```text
0 <= staged_ciphertext_octets <= 16,645
ciphertext_stream_received_octets =
  ciphertext_stream_fed_octets + staged_ciphertext_octets
staged_record_stream_start_octet = ciphertext_stream_fed_octets
next_tls_record_ordinal = tls_records_fed_count + 1
```

Status truth is:

```text
EMPTY:
  staged length 0; declared/expected/proof null

HEADER_INCOMPLETE:
  length 1..4; declared/expected/proof null;
  length 1 requires outer type 23;
  length 2 requires outer type 23;
  length 3 or 4 requires outer type 23; the two legacy-version octets are
  retained but ignored for receiver validity

BODY_INCOMPLETE:
  length 5..expected-1; decoded outer type 23,
  declared length 1..16,640; declared is header uint16;
  expected = 5 + declared; proof null

COMPLETE_UNFED:
  length = expected with the same valid-header rules; proof null

INVALID_TERMINAL:
  retain every byte actually received through detection; proof is exactly
  1 for wrong outer type or 5 for zero/over-
  16,640 declared length; staged length equals that proof because header
  receives are forced to milestones 1, then 2, then 2 octets
```

No other framing-failure category is admitted. `COMPLETE_UNFED` and
`INVALID_TERMINAL` are legal only on their exact adverse terminal results.
A continuing `DATA` ends `EMPTY`. A continuing `ZERO_PLAINTEXT` has no fed
record and ends `EMPTY`/`HEADER_INCOMPLETE`/`BODY_INCOMPLETE`. The unique initial state is empty with all cumulative
values zero and next ordinal one. Its identity is `semantic_id()` over every
preceding member under the literal staging-state domain. Attempt ordinal one
binds that initial ID; every later attempt's
`terminal_tls_staging_before_id` equals the prior acknowledged result's after
ID. The owner receives the complete resolved state from the durable chain,
never an ambient FIFO.

The V8 driver therefore adds a private bounded ciphertext-staging FIFO and a
literal TLS-record splitter. It delineates each record from the exact
five-byte TLS header and declared body length, rejects an invalid or
over-policy length, and feeds at most one newly admitted complete record to
the incoming `MemoryBIO` at a time. A kernel receive size is the minimum of
the remaining ciphertext allowance and the bytes still needed for the
current semantic milestone: one outer-type byte, two legacy-version bytes,
two length bytes, then the remaining body. Header reads are therefore exactly
`1`, `2`, `2` when starting empty; no read can return bytes beyond the field
whose validation may terminate the record. Body reads use only remaining
body bytes. The current fixed-size receive is not V8-admissible.

Counter boundaries are exact:

```text
socket_receive_calls_delta:
  increment immediately before every actual recv call, including calls that
  return EOF, stale-readiness, BlockingIOError, InterruptedError, or error

ciphertext_octets_delta:
  increment only by positive bytes returned from recv

tls_records_delta:
  increment exactly when one complete syntactically valid staged record is
  admitted and fed to MemoryBIO

tls_unwrap_iterations_delta:
  increment immediately before every SSLObject.read call

zero_progress_iterations_delta:
  increment once for a loop turn with no positive received ciphertext,
  no newly admitted TLS record, and no plaintext; each stale-readiness,
  BlockingIOError, InterruptedError, or bounded readiness timer-slice expiry
  is one such turn
```

The next counter is checked before its corresponding action. A partial staged
record with no plaintext at an exhausted per-attempt allowance returns
`ZERO_PLAINTEXT` with exact deltas and retains the bounded staged bytes for
the next acknowledged attempt. Global dimension exhaustion then commits its
literal limit convergence before another forbidden action. The independent
oracle and OFF/ON driver-call trace must reproduce the same header/body
boundaries, staging bytes, and counter increments.
The current 50-ms readiness slicing is admissible only when every expired
slice consumes one signed zero-progress unit before another wait. A one-shot
replacement wait would require its own frozen bounded-work descriptor.
No-readiness tests run through zero, one, and the exact maximum permitted
timer-slice expiries and prove the next slice is never entered after the cap.

OFF/ON neutrality tests use shared exogenous input rather than unrelated live
runs. Test-only `EffectOracleInputTapeV1` has exact keys:

```text
tape_version = riskyieldmm_effect_oracle_input_tape_v1
operation_kind
initial_cloned_store_and_authority_snapshot
ordered_entropy_events
ordered_governed_clock_events
ordered_local_clock_events
ordered_readiness_and_timer_events
ordered_socket_receive_events
ordered_socket_send_events
ordered_parser_tls_callback_events
ordered_cancellation_and_fault_events
ordered_transaction_commit_rollback_ack_events
effect_oracle_input_tape_id
```

Each event is a strict record
`{event_ordinal, qualified_callsite_id, invocation_ordinal_at_callsite,
outcome_kind, exact_value_or_sanitized_error}`. Arrays are strictly
ordinal-sorted and duplicate-free; values validate callsite-specific closed
schemas. The cloned initial snapshot contains complete projection bytes/head,
owner/driver/session/fence/capability state, parser/TLS state, and every
external authority used by the target. The tape supplies every entropy byte,
clock bracket, readiness ordering, recv/send value or error, cancellation,
fault, and transaction outcome. A missing, extra, out-of-order, unused, or
wrong-callsite event fails the test. Production code cannot accept a tape;
only qualified test adapters consume it.

For each scenario the harness clones the same initial snapshot and replays the
same tape into two OFF runs, two ON runs, and the OFF/ON comparison. It records
the exact ordered semantic target-call trace
`{operation_token, idempotency_key, request_bytes, result_bytes}`,
owner/driver physical-call trace, return value or sanitized raised class,
application/transport after-state, and durable target-prefix projection.
OFF/OFF and ON/ON must be byte-identical. OFF/ON must contain no extra,
missing, or reordered target/physical call and must have identical target
request/result bytes and target-domain record bodies.

Global projection receipt sequences/hashes may differ solely because ON
contains measurement-only candidate/attempt/marker/finalization records. The
harness therefore also proves an exact ledger-difference decomposition:
remove only records whose frozen kind is measurement-only, renumber the
remaining target receipt groups relatively, and recompute their content
hashes; the two target projections must then be byte-identical. Any other
record/body/order difference fails. Raw globally anchored receipt bytes are
not falsely asserted equal across differently instrumented ledgers.

This is an effect-neutrality claim under identical exogenous inputs, not a
claim that independently scheduled live runs have equal wall-clock timing.
Production acceptance means instrumentation adds no target/physical call,
does not reorder one, and does not alter target semantics; measurement-only
records and observer cost remain separately measured.

For every result, let `B` be decoded before-state bytes, `N` the concatenated
positive received chunks, `F` the one fed record or empty, and `A` decoded
after-state bytes. Projection proves:

```text
B || N = F || A
len(N) = ciphertext_octets_delta
SHA256(N) = ciphertext_sha256 iff N is nonempty
len(F) = fed_tls_record_wire_octets
tls_records_delta in {0, 1}
F is present iff tls_records_delta = 1
fed_tls_record_ordinal = before.next_tls_record_ordinal when present
F has one exact valid header/body and SHA256(F) = fed_tls_record_sha256
after.received = before.received + len(N)
after.fed = before.fed + len(F)
after.record_count = before.record_count + tls_records_delta
```

Outcome/staging truth is exact:

| Outcome | TLS staging/fed-record truth |
|---|---|
| `DATA` | positive `N`; `tls_records_delta=1`; fed ordinal/octet/hash all present; after state `EMPTY` |
| `ZERO_PLAINTEXT` | no fed record; after is `EMPTY` or a valid incomplete state |
| either pre-I/O result or owner-pre-driver error | before equals after; `N` empty; no fed record; all six work deltas zero |
| `DEADLINE_NO_OBSERVATION` | ciphertext/plaintext/record deltas zero, no fed record, staging unchanged; socket-call/unwrap/zero-progress deltas may be positive |
| `DRIVER_ERROR_NO_PROGRESS` | no fed record and zero ciphertext; before equals after except a deterministic `INVALID_TERMINAL` owner result is impossible under this tag |
| `DEADLINE_AFTER_PROGRESS` or `DRIVER_ERROR_AFTER_PROGRESS` | positive `N`; may retain one incomplete/terminal state with no feed, or feed exactly one record and end `EMPTY`; exact error/evidence truth decides |

A fed record with zero application plaintext cannot become continuing
`ZERO_PLAINTEXT` under the pinned Python/OpenSSL seam: record boundaries do
not prove that OpenSSL holds no partial post-handshake message. A conclusive
close-notify/EOF/output/deadline/driver condition takes its exact adverse
outcome; otherwise the driver seals
`TLS_POST_HANDSHAKE_BOUNDARY_UNPROVABLE`, fault-latches the connection, and
does not start another read. A future continuing-zero path requires a frozen
native authenticated message-boundary callback plus fragmented
NewSessionTicket/KeyUpdate tests before this rule may change.

Every received-chunk digest matches its decoded chunk; exact chunks are
needed because hashes cannot prove a record assembled from prior partial
bytes. Restored `B` was counted when first received and never increments
socket/ciphertext counters again. Removing `F` and advancing its ordinal
proves it is fed once. No next attempt begins before exact result
acknowledgement; acknowledgement loss replays the same result key/object and
never repeats receive/feed/unwrap.

One attempt receives at most 16,645 positive ciphertext octets. The bound
generator charges the nested staging state, canonical base64 chunks, digests,
and framing to the strict `TERMINAL_READ` request shape, actor/RAW record
bodies, projection entries, target span, and full prefix. The native
operation-batch result blob remains only its three IDs and is checked
separately against 65,536 bytes. The compact V2 operation result carries only
the final staging ID, so its 524,288-byte evidence check charges that ID, not
the already retained nested event bodies. A plan that fails any corresponding
ceiling rejects before a candidate.

A continuing result is legal only at a stable OpenSSL boundary:
incoming `MemoryBIO.pending()==0`, `SSLObject.pending()==0`, no hidden
post-handshake output, and at most one incomplete record in the durable
staging object. One fed record is drained completely, and any application
plaintext from it is returned in the same `DATA` RAW. Before feeding, the
remaining plaintext allowance is at least 16,384. Otherwise the
plaintext-limit convergence occurs before feed. If the signed allowances
cannot reach this stable boundary, an exact closed adverse result is used or
the effect remains unknown; a continuing result is forbidden.

This durable object permits continuation only by the same live TLS owner.
It does not serialize OpenSSL traffic secrets, record sequence numbers, or
`SSLObject` state. Process/owner loss remains epsilon
`UNKNOWN_PENDING_TERMINAL_READ`, prohibits new I/O and V2 success, and never
pretends staging bytes make TLS cross-process resumable.

Enforcement occurs before the next owner read, ciphertext receive, TLS record,
unwrap/zero-progress turn, parser unit, automatic output, and kernel effect.
Exhaustion uses one dimension-specific cause:

```text
LOCAL_SHUTDOWN_TERMINAL_INGRESS_BATCH_LIMIT_REACHED
LOCAL_SHUTDOWN_TERMINAL_INGRESS_CIPHERTEXT_LIMIT_REACHED
LOCAL_SHUTDOWN_TERMINAL_INGRESS_OCTET_LIMIT_REACHED
LOCAL_SHUTDOWN_TERMINAL_SOCKET_RECEIVE_LIMIT_REACHED
LOCAL_SHUTDOWN_TERMINAL_TLS_RECORD_LIMIT_REACHED
LOCAL_SHUTDOWN_TERMINAL_TLS_UNWRAP_LIMIT_REACHED
LOCAL_SHUTDOWN_TERMINAL_ZERO_PROGRESS_LIMIT_REACHED
LOCAL_SHUTDOWN_TERMINAL_INGRESS_PARSER_LIMIT_REACHED
LOCAL_SHUTDOWN_AUTOMATIC_OUTPUT_LIMIT_REACHED
LOCAL_SHUTDOWN_WEBSOCKET_SEND_LIMIT_REACHED
LOCAL_SHUTDOWN_TLS_CONTROL_SEND_LIMIT_REACHED
LOCAL_SHUTDOWN_PEER_SHUTDOWN_POLL_LIMIT_REACHED
```

For the plaintext dimension, “exhausted” at a new read/feed boundary means
remaining allowance is below the effective maximum plaintext of one admitted
record—16,384. This conservative pre-attempt guard closes the otherwise
unrepresentable complete-record/insufficient-drain branch.

Already committed RAW remainder stays durable. The exact reserved literal
FATAL limit-convergence symbol for the exhausted dimension is committed
before owner authority is released. Before every peer-shutdown poll the actor
checks `peer_shutdown_poll_count < maximum_peer_shutdown_polls`; exhaustion
maps exactly to `LOCAL_SHUTDOWN_PEER_SHUTDOWN_POLL_LIMIT_REACHED` and
`TC_FATAL_LIMIT_PEER_SHUTDOWN_POLL2`, without issuing a third poll.

### 8.4 Exact V2 attempt-precondition variants

Every mapping is strict and its tag must equal the operation kind.

```text
IngressPreconditionV2
  runtime_state
  sealed_pending_input
  sealed_pending_input_id
  ingress_oracle_baseline
  ingress_oracle_baseline_id
  ingress_oracle_expectation
  ingress_oracle_expectation_id
  actor_terminal_state_id
  actor_fault_latched
  actor_activation_in_progress
  oldest_outbound_wire_event_id = null
  pending_automatic_protocol_output = false
  application_fence_token_sha256
  application_fence_generation
  target_span_budget_id

SubscriptionDispatchPreconditionV2
  runtime_state
  creation_mode = FRESH_CREATE
  runtime_intent_id = null
  runtime_send_permit_id = null
  runtime_dispatch_window_id = null
  pending_ack_disposition_id = null
  durable_subscription_intent_id = null
  subscription_ack_binding_id = null
  authorization_operation_token
  authorization_idempotency_key
  authorization_batch_present = false
  runtime_idempotency_prefix
  termination_idempotency_key
  transport_subscription_policy_id
  adapter_policy_id
  topic
  parser_cursor_id
  parser_state = OPEN
  retained_ingress_tail_octets = 0
  fragmented_message_octets = 0
  fragmented_message_parser_event_ids = []
  initial_pending_raw_ingress_present = false
  actor_terminal_state_id
  actor_event_count = 0
  actor_tail_event_id = null
  actor_fault_latched = false
  actor_activation_in_progress = false
  oldest_outbound_wire_event_id = null
  pending_automatic_protocol_output = false
  application_fence_token_sha256
  application_fence_generation
  target_span_budget_id

LocalShutdownPreconditionV2
  runtime_state = SESSION_COMMITTED | AWAITING_ACK | ACK_BOUND
  parser_cursor_id
  parser_state
  retained_ingress_tail_octets = 0
  initial_pending_raw_ingress_present = false
  fragmented_message_octets = 0
  fragmented_message_parser_event_ids = []
  tls_record_boundary_ledger
  tls_record_boundary_ledger_id
  memory_bio_incoming_pending_octets = 0
  memory_bio_outgoing_pending_octets = 0
  ssl_plaintext_pending_octets = 0
  actor_terminal_state
  actor_terminal_state_id
  peer_first_close_converged
  actor_fault_latched = false
  actor_activation_in_progress = false
  oldest_outbound_wire_event_id = null
  pending_automatic_protocol_output = false
  last_terminal_convergence_event_id = null
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
  maximum_peer_shutdown_polls = 2
  target_span_budget_id
```

`AckDeadlineExpiryPreconditionV1` remains the exact Step-2 V1 mapping. All
four variants additionally agree with the attempt's duplicated session,
writer-fence, declaration, spec, and durable-baseline authority.

Local-shutdown cross-field guards are strict. `parser_state=CLOSING` iff
`ws_close_sent`, `ws_close_received`, and
`ws_output_fully_kernel_accepted` are all true; all three false requires
`OPEN`, and a mixed triple rejects. Any other parser state rejects. The
baseline requires `tls_close_notify_sent=false`,
`tls_close_notify_received=false`,
`tls_close_notify_fully_kernel_accepted=false`, `tcp_fin_sent=false`,
`tcp_eof_received=false`, all three hidden-input counters exactly zero, and
no prior terminal convergence. If the current production owner has buffered
TLS input/plaintext at shutdown entry, Raw V8 stays disabled until the normal
ingress path drains it to this stable boundary; the measurement never adopts
ambient OpenSSL state. These guards,
the runtime
state enum above, and the null last-convergence member are independently
replayed from the exact actor prefix; V2 does not admit a baseline the current
shutdown entry path cannot reach.

## 9. Fixed checkpoint-selector positions

The selector is a signed, immutable tuple of at most 64 entries:

```text
CheckpointSelectorEntryV1
  selector_position                 # 1..N
  operation_kind
  checkpoint_marker_kind
  occurrence_index_within_kind
  checkpoint_selector_entry_id

CheckpointSelectorV1
  operation_kind
  ordered_entries
  selector_length = N
  checkpoint_selector_id
```

Entries are unique. Their order must be compatible with the operation DFA.
An exact compact marker matches an entry by operation, kind, and
occurrence-within-kind. A matched checkpoint executes immediately after that
truthful compact marker and before the next target mutation.

Each entry ID hashes its first four members under the literal entry domain.
The selector ID hashes:

```text
operation_kind
selector_length
ordered_checkpoint_selector_entry_ids
```

under the literal selector domain. `ordered_entries` must reproduce those
exact IDs and positions `1..N`; substitution or a second entry with the same
kind/occurrence rejects.

Attempted ON closure cardinality is always:

```text
BEFORE
N checkpoint-position observations
AFTER
AGGREGATE
```

An ON candidate always binds one `CheckpointSelectorV1`, including the
canonical empty selector when `N=0`; its non-null ID is carried through an
attempt and its three-or-more-observation root. An OFF candidate and every
no-attempt branch bind no active selector: selector ID is null and the
three-role root has only `BEFORE`, `AFTER`, and `AGGREGATE`. Startup recovery
binds no selector, has exactly one `RECOVERY` observation, and its root order
is that one observation. Selector occurrences are replayed from the expanded
DFA path: occurrence indices start at one per marker kind and advance only
after the corresponding durable symbol transition. A selector entry can bind
only that exact replayed occurrence; ring order or callback timing cannot
invent an occurrence.

The `V1` class suffix is deliberate and matches the V1 identity domains in
Section 3.1. It denotes the first selector schema introduced by Raw V8, not
the measurement schema generation.

Checkpoint positions require a breaking context record; the inherited V1
context cannot encode a placeholder because it requires a marker ordinal.
The exact V2 context domain is the literal Section 3.1 domain, and its exact
keys are:

```text
TargetObservationContextV2
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
  observation_context_id
```

`observation_context_id` is `semantic_id()` of all preceding exact members.
The decoder uses a V2 tag and never accepts the old and new shapes under one
untagged record.

For every non-`STABLE_CHECKPOINT` role, all selector/binding members are null.
For `STABLE_CHECKPOINT`, selector ID, position, entry ID, expected kind, and
expected occurrence are required and exact. The binding enum is:

```text
EXACT_MARKER
UNAVAILABLE_MARKER_OBSERVER_FAILURE
UNAVAILABLE_TARGET_BOUNDARY_NOT_REACHED
```

Its truth table is exhaustive:

| Binding status | Required truth |
|---|---|
| `EXACT_MARKER` | marker ordinal is positive; actual marker kind equals expected kind; unavailable reason is null; all three context spans are `AVAILABLE` |
| `UNAVAILABLE_TARGET_BOUNDARY_NOT_REACHED` | marker ordinal and actual kind are null; unavailable reason is `TARGET_BOUNDARY_NOT_REACHED`; all three spans are unavailable for that reason |
| `UNAVAILABLE_MARKER_OBSERVER_FAILURE` | marker ordinal and actual kind are null; unavailable reason is the exact mapped marker error reason below; all three spans are unavailable for that same reason |

The clock-span record used by this V2 context is a breaking V2 variant that
admits exactly these placeholder reasons in addition to the inherited
available/source/process-loss cases:

```text
TargetObservationClockSpanV2
  clock_domain
  span_status
  started_offset_nanoseconds | null
  completed_offset_nanoseconds | null
  unavailable_reason | null

TARGET_BOUNDARY_NOT_REACHED
SOURCE_CLOCK_UNAVAILABLE
PROCESS_LOSS_VOLATILE_MARKER_STATE
ARTIFACT_BOUND_EXCEEDED
OBSERVER_INTERNAL_ERROR
```

`AVAILABLE` requires two ordered safe offsets and a null reason.
`UNAVAILABLE` requires null offsets and exactly one listed reason. It does
not serialize `MARKER_OBSERVER_FAILURE` as a reason. Marker error mapping is
literal:

| Marker error code | Placeholder reason |
|---|---|
| `CLOCK_READ_FAILED` | `SOURCE_CLOCK_UNAVAILABLE` |
| `SAFE_INTEGER_OR_BOUND_EXCEEDED` | `ARTIFACT_BOUND_EXCEEDED` |
| `CAPABILITY_MISMATCH`, `CLOCK_REGRESSION`, `COUNTER_ACCUMULATOR_FAILED`, `MARKER_SLOT_CONVERSION_FAILED` | `OBSERVER_INTERNAL_ERROR` |

Binding-status precedence is:

```text
1. exact selected marker/checkpoint captured -> EXACT_MARKER
2. durable DFA replay conclusively proves boundary not reached
   -> UNAVAILABLE_TARGET_BOUNDARY_NOT_REACHED
3. sticky marker failure prevents deciding a not-yet-captured boundary
   -> UNAVAILABLE_MARKER_OBSERVER_FAILURE
```

Reached/not reached is derived from durable DFA replay, never ring survival.
Observations serialize by selector position. Exact-marker ordinals are
strictly increasing across exact-marker positions; placeholders do not
participate in ordinal ordering. Ring overwrite may remove a compact marker
after its exact checkpoint has already been captured.

Every placeholder has all 185 fields:

```text
status = UNAVAILABLE
reason = exact field-placeholder reason mapped below
observation_attempt = NOT_ATTEMPTED
observation_method = NOT_ATTEMPTED
adapter_span_status = NOT_APPLICABLE
adapter start/completion offsets = null
```

The context and field layers deliberately use different reasons for the two
marker-level failures whose historical field reason requires an attempted
adapter:

| Context placeholder reason | Field-placeholder reason |
|---|---|
| `TARGET_BOUNDARY_NOT_REACHED` | `CHECKPOINT_PLACEHOLDER_TARGET_BOUNDARY_NOT_REACHED` |
| `SOURCE_CLOCK_UNAVAILABLE` | `CHECKPOINT_PLACEHOLDER_SOURCE_CLOCK_UNAVAILABLE` |
| `ARTIFACT_BOUND_EXCEEDED` | `CHECKPOINT_PLACEHOLDER_ARTIFACT_BOUND_EXCEEDED` |
| `OBSERVER_INTERNAL_ERROR` | `CHECKPOINT_PLACEHOLDER_OBSERVER_INTERNAL_ERROR` |

The four `CHECKPOINT_PLACEHOLDER_*` members are breaking additions to the
current Step-2 status-reason vocabulary. Each admits only
`UNAVAILABLE`/`NOT_ATTEMPTED`/`NOT_ATTEMPTED` method/
`NOT_APPLICABLE` adapter span, null value, `NONE` censoring, `NONE` failure
phase, and no source error metadata. They are legal only in a V2
`STABLE_CHECKPOINT` context whose binding status/reason maps to that row.
The regenerated status-reason policy extends its closed
`context_predicate` vocabulary with exactly:

```text
V2_CHECKPOINT_PLACEHOLDER_TARGET_BOUNDARY_NOT_REACHED
V2_CHECKPOINT_PLACEHOLDER_SOURCE_CLOCK_UNAVAILABLE
V2_CHECKPOINT_PLACEHOLDER_ARTIFACT_BOUND
V2_CHECKPOINT_PLACEHOLDER_OBSERVER_INTERNAL_ERROR
```

The four predicates are required one-to-one by the four field-placeholder
reasons in the same order as the mapping table. A standalone field envelope
validates the represented attempt/error form but cannot discharge a
checkpoint predicate from a context ID alone. `TargetObservationV2` must
resolve the complete V2 context and require `STABLE_CHECKPOINT`, the exact
placeholder binding status, the corresponding context reason, and the exact
dedicated field reason for all 185 entries. Any dedicated reason under a
null, non-checkpoint, exact-marker, wrong placeholder binding, wrong context
reason, or mixed-field observation rejects. The policy record therefore
carries the machine gate; this is not external prose or a decoder exception.

The dedicated reasons are not aliases for the historical
`TARGET_BOUNDARY_NOT_REACHED`, `SOURCE_CLOCK_UNAVAILABLE`,
`ARTIFACT_BOUND_EXCEEDED`, or `OBSERVER_INTERNAL_ERROR` states. Their
historical reason-rule records and descriptor eligibility retain their
existing meaning. Every one of the 185 regenerated descriptors adds all four
dedicated checkpoint-placeholder reasons to `allowed_status_reasons`; this
addition is what makes a complete placeholder representable even for the
four static/policy descriptors that exclude the historical target-boundary
and source-clock reasons. The 185 field IDs, order, value types, units,
methods, roles, operation applicability, and 66-counter schema remain
unchanged. The shared policy/vocabulary, complete descriptor records, and
therefore the target-field registry identity regenerate under Step-2 V2.

Source adapters are not called. Root validation requires positions exactly
`1..N`, exact selector/entry IDs and expected kind/occurrence, plus the three
mandatory non-checkpoint roles.

The V2 context has a V2 serialization home. A
`TARGET_OBSERVATION_V2` record uses the literal V2 observation domain and
exact keys:

```text
TargetObservationV2
  observation_context
  observation_context_id
  field_observations
  observation_id
```

`observation_context` is the one complete flattened
`TargetObservationContextV2` record and must recompute to
`observation_context_id`. `field_observations` is the exact 185-record
registry-ordered tuple; every field binds that context ID.
`observation_id` is `semantic_id()` under the literal V2 observation domain
over the three preceding members. Missing/extra members and a V1 context
reject.

The corresponding V2 root has exact keys:

```text
TargetObservationRootV2
  candidate_id
  attempt_id | null
  operation_kind
  instrumentation_mode
  target_field_registry_id
  full_checkpoint_selector_id | null
  observation_count
  ordered_observation_ids
  target_observation_root_sha256
```

The root ID is `semantic_id()` under the literal V2 root domain over all
preceding members. For attempted ON, root order is exactly `BEFORE`, selector
positions `1..N`, `AFTER`, `AGGREGATE`; it is not marker-ordinal order.
No-attempt/OFF has no checkpoint positions and its inherited three-role order.
The old V1 rule requiring non-null marker ordinal/kind for every
`STABLE_CHECKPOINT` is superseded only for V2: those values are nullable
exactly in the two unavailable binding states above. Non-checkpoint roles
require every selector/binding member null.

## 10. Terminal, delivery, marker, and probe corrections

### 10.1 Terminal preobservation clocks

Add:

```text
TerminalPreobservationClockAvailabilityV8
  EXACT_SAME_PROCESS
  UNAVAILABLE_OBSERVER_FAILURE
  UNAVAILABLE_PROCESS_LOSS

TerminalPreobservationClockErrorCodeV8
  CLOCK_READ_FAILED
  CLOCK_REGRESSION
  SAFE_INTEGER_OR_BOUND_EXCEEDED
```

The terminal adds:

```text
terminal_preobservation_clock_availability
terminal_preobservation_clock_error_code | null
terminal_preobservation_clock_error_class | null
terminal_preobservation_observer_offset_ns | null
terminal_preobservation_boottime_offset_ns | null
terminal_preobservation_loop_offset_ns | null
terminal_preobservation_process_cpu_offset_ns | null
terminal_preobservation_thread_cpu_offset_ns | null
terminal_preobservation_wall_time | null
```

Sampling is all-or-nothing in this order:

```text
observer -> BOOTTIME -> loop -> process CPU -> thread CPU -> wall UTC
```

Any same-process failure discards all temporary clock values, records the
exact error, and continues terminal/closure construction. Recovery records
process loss. No branch invents partial terminal clocks.

| Availability | Six values | Error code/class |
|---|---|---|
| `EXACT_SAME_PROCESS` | all present | both null |
| `UNAVAILABLE_OBSERVER_FAILURE` | all null | exact code; class present iff a caught exception caused it |
| `UNAVAILABLE_PROCESS_LOSS` | all null | both null |

Deterministic regression/bound validation has a null error class.

### 10.2 Delivery uncertainty is orthogonal

Remove `UNKNOWN_DELIVERY_PREFIX` from
`OperationResultUnavailableReasonV8`. Add:

```text
SubscriptionDeliveryStateV8
  NOT_APPLICABLE_NON_SUBSCRIPTION
  NO_UNRESOLVED_LOCAL_SEND
  UNKNOWN_UNMATCHED_LOCAL_SEND

unmatched_local_send_event_id | null
```

Both members are terminal fields. Exact truth is:

| Branch | Delivery state | Anchor/effect truth |
|---|---|---|
| Any non-subscription | `NOT_APPLICABLE_NON_SUBSCRIPTION` | anchor null |
| Subscription with no unmatched local send | `NO_UNRESOLVED_LOCAL_SEND` | anchor null |
| Subscription whose stable prefix ends with an unmatched `KERNEL_SEND_ATTEMPT` | `UNKNOWN_UNMATCHED_LOCAL_SEND` | anchor is that exact final attempt event; `effect_certainty=UNKNOWN` |

The anchor is specifically the first event of the atomic `KA_APP2` group:
the `KERNEL_SEND_ATTEMPT` actor event ID. It is never the paired
`SEND_ATTEMPT_STARTED` terminal-transition ID. Replay requires the two-event
KA group to be complete, then proves that no matching `KR_APP2` result group
exists for that attempt.

The result-unavailable reason remains exact:

```text
returned but over bound       -> RESULT_EVIDENCE_BOUND_EXCEEDED
returned but invalid          -> RESULT_EVIDENCE_VALIDATION_FAILED
raised                        -> TARGET_RAISED_EXCEPTION
cancelled                     -> TARGET_CANCELLED
interrupted                   -> TARGET_INTERRUPTED
attempted recovery            -> PROCESS_LOSS_BEFORE_RESULT
```

A raised subscription may therefore carry both
`TARGET_RAISED_EXCEPTION` and `UNKNOWN_UNMATCHED_LOCAL_SEND`.
A valid returned subscription result is rejected if the prefix still has an
unmatched send.

Local terminal-read uncertainty is independently explicit:

```text
TerminalReadEffectStateV8
  NOT_APPLICABLE_NON_LOCAL_SHUTDOWN
  NO_UNRESOLVED_TERMINAL_READ
  UNKNOWN_PENDING_TERMINAL_READ

TerminalReadCounterCompletenessV8
  NOT_APPLICABLE_NON_LOCAL_SHUTDOWN
  EXACT_ACKNOWLEDGED_RESULTS
  LOWER_BOUND_PENDING_RESULT

unmatched_terminal_ingress_read_attempt_event_id | null
```

For non-local-shutdown operations both enums use their not-applicable value
and the anchor is null. A local-shutdown prefix with no unmatched
`TERMINAL_INGRESS_READ_ATTEMPT` uses `NO_UNRESOLVED_TERMINAL_READ`,
`EXACT_ACKNOWLEDGED_RESULTS`, and a null anchor. Whenever the latest
acknowledged attempt has no matched result—including a prefix at
`TERMINAL_READ_PENDING` and a `TERMINAL` prefix reached through
`TC_FATAL_TERMINAL_READ_UNKNOWN_EFFECT2`—the terminal uses
`UNKNOWN_PENDING_TERMINAL_READ`, `LOWER_BOUND_PENDING_RESULT`, the exact
attempt actor-event ID, and `effect_certainty=UNKNOWN`; no returned V2 result
is legal. The durable attempt count is exact, while the six read-derived
counters are only lower bounds. This read truth is orthogonal to
subscription-delivery truth.

### 10.2.1 Complete corrected terminal schema

This amendment replaces, rather than appends ambiguously to, the parent
terminal member list:

```text
OperationTerminalV8
  candidate_id
  attempt_id | null
  operation_kind
  previous_operation_terminal_id | null
  admission_outcome_evidence | null
  admission_outcome_evidence_id
  target_authorization_outcome
  terminal_writer
  terminal_trigger
  emergency_activation | null
  emergency_activation_id | null
  emergency_suffix_profile_id | null
  selected_emergency_suffix_record_ordinal | null
  finalization_context_guard_rule_id | null
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
  subscription_delivery_state
  unmatched_local_send_event_id | null
  terminal_read_effect_state
  terminal_read_counter_completeness
  unmatched_terminal_ingress_read_attempt_event_id | null
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
  target_writer_fence_token_sha256 | null
  target_writer_fence_generation | null
  finalizer_writer_fence_token_sha256
  finalizer_writer_fence_generation
  finalizer_writer_relationship
  recovered_prefix_id
  terminal_preobservation_clock_availability
  terminal_preobservation_clock_error_code | null
  terminal_preobservation_clock_error_class | null
  terminal_preobservation_observer_offset_ns | null
  terminal_preobservation_boottime_offset_ns | null
  terminal_preobservation_loop_offset_ns | null
  terminal_preobservation_process_cpu_offset_ns | null
  terminal_preobservation_thread_cpu_offset_ns | null
  terminal_preobservation_wall_time | null
  terminal_id
```

`terminal_id` is `semantic_id()` under
`RiskYieldMMA2MOperationTerminalV4_9F_RawV8` over all preceding exact
members. `SAME_TASK` requires `SAME_TARGET_WRITER`; `STARTUP_RECOVERY`
requires `RECOVERY_WRITER`. Attempted paths require both target-writer
members from the attempt. No-attempt paths require both null.
`SAME_TARGET_WRITER` finalizer coordinates equal the attempt pair when
attempted and the candidate pair otherwise. `RECOVERY_WRITER` uses the
current persisted recovery fence and never claims same-process clock truth.
Admission body/ID truth is exact. `attempt_id=null` requires one complete
strict admission-outcome body—including `UNRESOLVED_PROCESS_LOSS` on the
qualified recovery branch—and the non-null ID byte-equals its independently
recomputed identity. `attempt_id!=null` requires
`admission_outcome_evidence=null`; the non-null ID byte-equals the complete
`GRANTED` outcome already embedded in that exact attempt. Any other nullness,
duplicated attempted body, ID-only no-attempt assertion, or unequal ID
rejects.

The five emergency members are all null exactly when no emergency suffix was
selected. Otherwise the complete activation object validates
`EmergencyActivationInputV1`; its ID is `semantic_id()` under
`RiskYieldMMA2MEmergencyActivationInputV1V4_9F_RawV8`; the profile resolves
through the candidate's admitted plan; the ordinal resolves exactly one
suffix row; and the context-guard ID byte-equals that row. Durable replay
re-evaluates the row's pre-state/activation guards against the retained target
prefix, proves the committed target symbols equal its `ordered_symbols`, and
then reconstructs the complete actual `FinalizationContextV1` from the
operation result, no-attempt evidence, or recovery evidence and pre-terminal
receipt anchors already retained in the prefix/terminal. The post-state
context guard and finalizer
must both pass. No terminal/closure ID is an input to that context, preventing
an identity cycle. Omitting the activation body, retaining only its hash, or
selecting a suffix by later context is forbidden.

The delivery coupling is the exhaustive table in Section 10.2 and is derived
from durable replay during recovery. Clock coupling is the all-or-none table
in Section 10.1. All five numeric offsets are safe unsigned integers and wall
time is canonical UTC. A caught `CLOCK_READ_FAILED` requires the safe error
class; deterministic `CLOCK_REGRESSION` and
`SAFE_INTEGER_OR_BOUND_EXCEEDED` require a null class.

### 10.3 Marker failure map

`CLOSURE_SEAL_CLOCKS` is not a marker phase. Closure clocks have independent
error fields.

```text
MarkerObserverFailurePhaseV8
  NONE
  BEFORE_FIRST_TRUTHFUL_MARKER
  AFTER_TRUTHFUL_MARKER_PREFIX
  MARKER_SLOT_CONVERSION

closure_clock_error_code | null
closure_clock_error_class | null
```

| Marker phase | Legal codes |
|---|---|
| `NONE` | code/class null |
| `BEFORE_FIRST_TRUTHFUL_MARKER` | `CAPABILITY_MISMATCH`, `CLOCK_READ_FAILED`, `CLOCK_REGRESSION`, `COUNTER_ACCUMULATOR_FAILED`, `SAFE_INTEGER_OR_BOUND_EXCEEDED` |
| `AFTER_TRUTHFUL_MARKER_PREFIX` | same five codes |
| `MARKER_SLOT_CONVERSION` | exactly `MARKER_SLOT_CONVERSION_FAILED` |

Closure-clock availability is exact same-process, instrumentation-off,
observer-failure, or process-loss. Observer failure permits only clock read,
regression, or safe-bound error.

| Closure-clock availability | Three seal offsets | Code/class |
|---|---|---|
| `EXACT_SAME_PROCESS` | all present | null/null |
| `NOT_OBSERVED_INSTRUMENTATION_OFF` | all null | null/null |
| `UNAVAILABLE_OBSERVER_FAILURE` | all null | `CLOCK_READ_FAILED`, `CLOCK_REGRESSION`, or `SAFE_INTEGER_OR_BOUND_EXCEEDED`; class iff exception |
| `UNAVAILABLE_PROCESS_LOSS` | all null | null/null |

Primary closure reason precedence is:

```text
marker capture or marker-slot conversion error
-> closure-clock error
-> marker overwrite
-> probe observer error
-> probe overwrite
-> due-but-unfired probe
```

Every lower-precedence condition remains visible in its dedicated fields.

### 10.3.1 Complete corrected closure schema

This amendment replaces the parent closure member list with:

```text
MarkerClosureV8
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
  closure_clock_error_code | null
  closure_clock_error_class | null
  closure_completed_observer_offset_ns | null
  closure_completed_boottime_offset_ns | null
  closure_completed_loop_offset_ns | null
  closure_id
```

`closure_id` is `semantic_id()` under
`RiskYieldMMA2MMarkerClosureV4_9F_RawV8` over all preceding members.
`status_reason_counts` is a fixed 26-key map containing every current Step-2
status reason exactly once in UTF-8 lexical order, including the four
`CHECKPOINT_PLACEHOLDER_*` reasons and zero values. It counts every non-null
nested field reason. This explicitly supersedes the inherited 22-key closure,
bound-generator, and acceptance statements; a 22-key map, missing zero key,
or extra historical alias rejects.
Marker-map truth is exhaustive:

| Closure path | Three marker maps |
|---|---|
| ON, same-process, at least one truthful marker | all present as complete marker-kind maps; counts are nonnegative, and first/last are null exactly for a zero count |
| ON, same-process, zero truthful markers with no marker failure | all present as complete zero-count maps; every first/last value is null |
| OFF, startup recovery, failure before the first truthful marker, or marker-slot conversion failure | all three null |
| ON, same-process failure after a truthful marker prefix | all present for the exact truthful prefix |

Mixed null/present map triples reject. When maps are present, the sum of
counts equals `emitted_total`, their first/last ordinals agree with the
retained/all-prefix aggregates, and every marker kind from the contract is
represented even when its count is zero.
Marker error-to-reason mapping is:

```text
CLOCK_READ_FAILED                  -> SOURCE_CLOCK_UNAVAILABLE
SAFE_INTEGER_OR_BOUND_EXCEEDED     -> ARTIFACT_BOUND_EXCEEDED
CAPABILITY_MISMATCH                -> OBSERVER_INTERNAL_ERROR
CLOCK_REGRESSION                   -> OBSERVER_INTERNAL_ERROR
COUNTER_ACCUMULATOR_FAILED         -> OBSERVER_INTERNAL_ERROR
MARKER_SLOT_CONVERSION_FAILED      -> OBSERVER_INTERNAL_ERROR
```

Closure-clock mapping uses the same first two rows and maps
`CLOCK_REGRESSION` to `OBSERVER_INTERNAL_ERROR`. Marker phase `NONE` requires
null marker code/class. Closure availability other than
`UNAVAILABLE_OBSERVER_FAILURE` requires null closure code/class. Observer
failure requires exactly `CLOCK_READ_FAILED`, `CLOCK_REGRESSION`, or
`SAFE_INTEGER_OR_BOUND_EXCEEDED` and all three seal offsets null.

Overall closure status/reason precedence is:

```text
1. OFF -> UNAVAILABLE / INSTRUMENTATION_DISABLED
2. ON process loss
   -> UNAVAILABLE / PROCESS_LOSS_VOLATILE_MARKER_STATE
3. marker failure before first marker or marker-slot conversion
   -> UNAVAILABLE / mapped marker reason
4. later marker failure -> PARTIAL / mapped marker reason
5. closure-clock error -> PARTIAL / mapped clock reason
6. marker overwrite -> PARTIAL / MARKER_RING_OVERWROTE_PREFIX
7. probe observer reason -> PARTIAL / exact probe reason
8. probe overwrite -> PARTIAL / PROBE_RING_OVERWROTE_PREFIX
9. due-but-unfired probe -> PARTIAL / PERIODIC_PROBE_DID_NOT_FIRE
10. otherwise -> COMPLETE / null
```

Every lower-precedence fact remains serialized.
`CLOSURE_SEAL_CLOCKS` is forbidden as a marker failure phase.

### 10.4 Probe failure map

The serialized `CapacityMeasurementLoopProbeSummaryV8` has these exact
members:

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
closure_loop_offset_ns | null
final_unfired_delay_lower_bound_ns | null
callback_observer_span_total_ns | null
callback_observer_span_maximum_ns | null
observer_failure_phase
observer_error_code | null
observer_error_class | null
```

```text
LoopProbeObserverErrorCodeV8
  CLOCK_READ_FAILED
  CLOCK_REGRESSION
  PROBE_ARITHMETIC_FAILED
  PROBE_CALLBACK_FAILED
  PROBE_SCHEDULE_FAILED
  PROBE_CANCEL_FAILED
  PROBE_SLOT_CONVERSION_FAILED
  SAFE_INTEGER_OR_BOUND_EXCEEDED

LoopProbeObserverFailurePhaseV8
  NONE
  INITIAL_CLOCK_OR_ARITHMETIC
  INITIAL_SCHEDULE
  CALLBACK_CAPTURE
  SUCCESSOR_ARITHMETIC
  SUCCESSOR_SCHEDULE
  CLOSURE_CANCEL
  CLOSURE_LOOP_CLOCK
  PROBE_SLOT_CONVERSION
```

The phase/code relation is literal:

| Probe phase | Legal codes |
|---|---|
| `NONE` | code and class null |
| `INITIAL_CLOCK_OR_ARITHMETIC` | `CLOCK_READ_FAILED`, `CLOCK_REGRESSION`, `PROBE_ARITHMETIC_FAILED`, `SAFE_INTEGER_OR_BOUND_EXCEEDED` |
| `INITIAL_SCHEDULE` | `PROBE_SCHEDULE_FAILED` |
| `CALLBACK_CAPTURE` | `CLOCK_READ_FAILED`, `CLOCK_REGRESSION`, `PROBE_CALLBACK_FAILED`, `SAFE_INTEGER_OR_BOUND_EXCEEDED` |
| `SUCCESSOR_ARITHMETIC` | `PROBE_ARITHMETIC_FAILED`, `SAFE_INTEGER_OR_BOUND_EXCEEDED` |
| `SUCCESSOR_SCHEDULE` | `PROBE_SCHEDULE_FAILED` |
| `CLOSURE_CANCEL` | `PROBE_CANCEL_FAILED` |
| `CLOSURE_LOOP_CLOCK` | `CLOCK_READ_FAILED`, `CLOCK_REGRESSION`, `SAFE_INTEGER_OR_BOUND_EXCEEDED` |
| `PROBE_SLOT_CONVERSION` | `PROBE_SLOT_CONVERSION_FAILED` |

Error-to-reason mapping is:

```text
CLOCK_READ_FAILED                  -> SOURCE_CLOCK_UNAVAILABLE
SAFE_INTEGER_OR_BOUND_EXCEEDED     -> ARTIFACT_BOUND_EXCEEDED
every other non-null probe code    -> OBSERVER_INTERNAL_ERROR
```

Error class is present iff a caught exception caused the exact code.
Deterministic regression/arithmetic/bound validation has a null class.

Status/reason precedence is exact:

```text
1. instrumentation OFF
   -> DISABLED / INSTRUMENTATION_DISABLED
2. ON process loss
   -> UNAVAILABLE / PROCESS_LOSS_VOLATILE_MARKER_STATE
3. PROBE_SLOT_CONVERSION
   -> UNAVAILABLE / OBSERVER_INTERNAL_ERROR
4. INITIAL_CLOCK_OR_ARITHMETIC or INITIAL_SCHEDULE before a truthful
   callback/schedule series
   -> UNAVAILABLE / mapped code reason
5. any other non-NONE observer failure
   -> PARTIAL / mapped code reason
6. no observer error and overwritten_count > 0
   -> PARTIAL / PROBE_RING_OVERWROTE_PREFIX
7. no observer error/overwrite and probe_phases_missed > 0
   -> PARTIAL / PERIODIC_PROBE_DID_NOT_FIRE
8. otherwise
   -> COMPLETE / null
```

Lower-precedence overwrite and due facts remain in their dedicated counters.

Let `P=interval_ns`, `s=start_loop_offset_ns`, and
`expected_0=s+P`. The first scheduled phase is zero. A complete truthful
callback for phase `q` at actual loop offset `a` records:

```text
delay = max(0, a - expected_q)

if a < expected_0:
  q_next = q + 1
else:
  q_next = max(q + 1, floor((a - expected_0) / P) + 1)

newly_missed = q_next - q - 1
expected_next = expected_0 + q_next * P
```

All arithmetic is checked in temporaries before mutation.
`probes_fired` and callback ordinal advance only after the entire callback
slot is truthful. `probes_scheduled` advances only after `call_at()` returns
a live handle.

For `F=probes_fired` and capacity `L`:

```text
retained_count = min(F, L)
overwritten_count = max(0, F - L)

if F <= L:
  retained callback ordinals = 1..F
else:
  retained callback ordinals = 1, then F-L+2..F
```

Aggregate delay/span totals and extrema cover all `F` truthful callbacks, not
only retained slots. When `F=0`, totals are zero and extrema plus associated
ordinals are null.

Exact path rows are:

| Phase/path | Schedule/offset state | Counts, pending state, and aggregates |
|---|---|---|
| OFF | start/expected null | scheduled/fired/retained/overwritten/missed/totals zero; retained empty; all timing/ordinal/phase/next/extrema including closure loop offset null; `pending_handle_cancelled=false`; phase `NONE`; errors null |
| Healthy ON after `F` callbacks | start/expected present | `probes_scheduled=F+1`; exact pending phase/expected; `cancel()` called and `handle.cancelled()==true`; `closure_loop_offset_ns` is present and equals the closure's `closure_completed_loop_offset_ns`; `pending_handle_cancelled=true`; closure-due formula applies |
| Recovery ON | interval/capacity retained | retained count zero/empty; every other volatile member, including closure loop offset, null; phase `NONE`; errors null |
| `INITIAL_CLOCK_OR_ARITHMETIC` | failed temporary initial state discarded | scheduled/fired/retained/overwritten/missed/totals zero; start/expected/next null; cancel false |
| `INITIAL_SCHEDULE` | start/expected present | scheduled/fired/retained/overwritten/missed/totals zero; no pending handle/next; cancel false |
| `CALLBACK_CAPTURE` | start/expected present | `probes_scheduled=F+1`; failed callback excluded; exact prefix of `F`; no live successor; next null; cancel false |
| `SUCCESSOR_ARITHMETIC` or `SUCCESSOR_SCHEDULE` | start/expected present | `probes_scheduled=F>0`; exact prefix; no live successor; next null; cancel false; unsuccessfully scheduled computed successor is not serialized |
| `CLOSURE_CANCEL` | start/expected and exact pending phase present | `probes_scheduled=F+1`; cancellation is unproved, so `pending_handle_cancelled=null`; `closure_loop_offset_ns=null`; no closure clock/due increment |
| `CLOSURE_LOOP_CLOCK` | exact pending phase present | cancellation already proved; `probes_scheduled=F+1`; `pending_handle_cancelled=true`; `closure_loop_offset_ns=null` and censored fields unavailable; no closure-due increment |
| `PROBE_SLOT_CONVERSION` | interval/capacity only | retained count zero/empty; every other volatile member null |

For an exact pending phase with serialized `c=closure_loop_offset_ns`, next
expected offset `e`, and interval `P`:

```text
if c < e:
  closure_due_missed = 0
  final_unfired_delay_lower_bound_ns = null
else:
  closure_due_missed = floor((c - e) / P) + 1
  final_unfired_delay_lower_bound_ns = c - e
```

`probe_phases_missed` is successful-callback skipped phases plus
`closure_due_missed`. The censored lower bound never enters fired totals or
extrema.

## 11. Immutable finalization and exact recovery

### 11.1 Construction order

The corrected tail is:

```text
seal marker/probe/observation state
-> derive recovered_prefix_id
-> serialize and identify terminal
-> serialize and identify closure binding terminal_id
-> validate immutable FinalizationPlanV8
-> BEGIN IMMEDIATE
-> revalidate locator, writer fence, ledger head, and complete span
-> append preconstructed terminal and receipt
-> insert typed terminal
-> append preconstructed closure and consecutive receipt
-> insert typed closure
-> delete the singleton locator
-> finish exact two-receipt batch
-> COMMIT
-> create finalization observation
```

Normal finalization records and verifies the same target writer-fence token
and generation carried by the attempt. Recovery instead records both the old
target fence and the current recovery-finalizer fence; it never relabels the
new writer as the target writer.

Terminal writer coordinates are explicit:

```text
target_writer_fence_token_sha256 | null
target_writer_fence_generation | null
finalizer_writer_fence_token_sha256
finalizer_writer_fence_generation
finalizer_writer_relationship:
  SAME_TARGET_WRITER | RECOVERY_WRITER
```

An attempted branch requires the target pair and derives it from the attempt.
A no-attempt branch requires both target members null and derives the
historical pre-admission writer pair from the candidate when checking
finalizer authority. `SAME_TARGET_WRITER` requires the finalizer pair to equal
the attempt pair when attempted, or the candidate pair when not attempted.
`RECOVERY_WRITER` permits a different finalizer pair, requires startup
recovery, and cannot carry same-process target timing.

Startup order is normative:

```text
claim and persist the new writer fence
-> verify the historical V8 receipt chain and singleton locator
-> create the exact recovery snapshot
-> preconstruct and validate RecoveryFinalizationPlanV8
-> recover and remove the locator
-> verify no locator remains
-> only then reconcile actor/session state or permit an ordinary mutation
```

The current Raw-V7-only startup exclusion for a V8 store must be replaced by
this V8-specific branch; it is not permission to invoke the V7 recovery
codec.

`FinalizationPlanV8` contains:

```text
operation_token
idempotency_key
request_payload
request_hash
candidate_id
attempt_id | null
expected_locator_candidate_id
expected_target_writer_fence_token_sha256 | null
expected_target_writer_fence_generation | null
finalizer_writer_fence_token_sha256
finalizer_writer_fence_generation
finalizer_writer_relationship
expected_pre_terminal_receipt_sequence
expected_pre_terminal_receipt_hash
recovered_prefix_id
terminal_record
terminal_id
terminal_content_hash
terminal_canonical_bytes
closure_record
closure_id
closure_content_hash
closure_canonical_bytes
```

The plan's `finalizer_writer_relationship` must equal the terminal member,
and all four writer coordinates must satisfy Section 11.1 before `BEGIN`.
Its operation token is exactly
`FINALIZE_CAPACITY_MEASUREMENT_OPERATION_V49F_V8` and its idempotency key is
`"v49f-v8:finalize:" + candidate_id`.
Each canonical byte member equals `canonical_json_bytes()` of its complete
record, decodes strictly back to that record, and recomputes its semantic ID.
Each content hash is lowercase hexadecimal SHA-256 of the corresponding
canonical bytes with no additional domain envelope.

`RecoveryFinalizationPlanV8` is a separate immutable ephemeral tuple with
exact keys:

```text
operation_token = RECOVER_CAPACITY_MEASUREMENT_OPERATION_V49F_V8
idempotency_key
request_payload
request_hash
recovery_snapshot
candidate_id
attempt_id | null
recovery_writer_fence_token_sha256
recovery_writer_fence_generation
expected_pre_terminal_receipt_sequence
expected_pre_terminal_receipt_hash
recovered_prefix_id
terminal_record
terminal_id
terminal_content_hash
terminal_canonical_bytes
closure_record
closure_id
closure_content_hash
closure_canonical_bytes
```

Its idempotency key is `"v49f-v8:recover:" + candidate_id`. The recovery
writer coordinates equal the snapshot and both prebuilt records. Record/byte
and content-hash truth is identical to `FinalizationPlanV8`. The plan is
constructed and completely validated after the current writer fence and
snapshot are persisted but before recovery `BEGIN`.

No terminal/closure body canonicalization, content hashing, identity hashing,
target observation, closure construction, or source adapter call occurs after
`BEGIN IMMEDIATE`. Bounded receipt construction/hashing and exact batch-result
canonicalization remain necessary after the head and receipt sequences are
revalidated. Lightweight reads of the already bound finalization observer
clock bracket the transaction stages.
Their failure makes the post-commit finalization observation unavailable but
does not change transaction control.

### 11.2 Finalization observation

`FinalizationObservationV8` uses the literal domain
`RiskYieldMMA2MFinalizationObservationV4_9F_RawV8` and has exact keys:

```text
candidate_id
terminal_id
closure_id
availability
terminal_closure_serialization_span | null
terminal_closure_validation_span | null
final_transaction_begin_span | null
final_transaction_body_span | null
final_transaction_commit_span | null
seal_to_commit_return_span | null
finalization_error_code | null
finalization_error_class | null
finalization_observation_id
```

Availability is one of `EXACT_SAME_PROCESS`,
`UNAVAILABLE_OBSERVER_FAILURE`, `UNAVAILABLE_COMMIT_ACKNOWLEDGEMENT`,
`UNAVAILABLE_IDEMPOTENT_REPLAY`, or `UNAVAILABLE_PROCESS_LOSS`.
`finalization_observation_id` is `semantic_id()` under the literal domain
over all preceding exact members.

Availability truth is:

| Circumstance | Availability and members |
|---|---|
| Current process, COMMIT returns, all brackets valid | `EXACT_SAME_PROCESS`; all six spans; error fields null |
| COMMIT returns but a finalization bracket/read/validation observer fails | `UNAVAILABLE_OBSERVER_FAILURE`; spans null; exact code; class iff a caught exception |
| COMMIT raises or acknowledgement is lost and fresh replay proves committed | `UNAVAILABLE_COMMIT_ACKNOWLEDGEMENT`; spans and errors null |
| Same-process later exact replay lacks retained ephemeral spans | `UNAVAILABLE_IDEMPOTENT_REPLAY`; spans and errors null |
| Another process/fork reconstructs the batch | `UNAVAILABLE_PROCESS_LOSS`; spans and errors null |

`FinalizationErrorCodeV8` is exactly
`CLOCK_READ_FAILED`, `CLOCK_REGRESSION`,
`SAFE_INTEGER_OR_BOUND_EXCEEDED`, or `SPAN_VALIDATION_FAILED`.
Only `UNAVAILABLE_OBSERVER_FAILURE` permits an error code. A caught
`CLOCK_READ_FAILED` may carry its safe class; deterministic
`CLOCK_REGRESSION`, `SAFE_INTEGER_OR_BOUND_EXCEEDED`, and
`SPAN_VALIDATION_FAILED` require a null class. Immutable plan/body validation
failure before `BEGIN` is fail-closed and creates no final batch or
observation. `SPAN_VALIDATION_FAILED` refers only to validation of an already
captured observer bracket and cannot mask plan validation.

Exact batch request/result bodies are:

```text
CANDIDATE request:
  complete candidate record

ATTEMPT request:
  complete attempt record

FINALIZE request:
  candidate_id
  attempt_id | null
  expected_pre_terminal_receipt_sequence
  expected_pre_terminal_receipt_hash
  recovered_prefix_id
  terminal_record
  closure_record

RECOVER request:
  recovery_snapshot
  candidate_id
  candidate_position = 0
  expected_pre_terminal_receipt_sequence
  expected_pre_terminal_receipt_hash
  recovered_prefix_id
  terminal_record
  closure_record
```

Lifecycle idempotency keys are exactly:

```text
CANDIDATE  = "v49f-v8:candidate:" + candidate_id
ATTEMPT    = "v49f-v8:attempt:" + candidate_id
FINALIZE   = "v49f-v8:finalize:" + candidate_id
RECOVER    = "v49f-v8:recover:" + candidate_id
```

For new V8 lifecycle operations:

```text
request_hash =
  lowercase_hex(SHA-256(canonical_json_bytes({
    "domain": "RiskYieldMMPhysicalProjectionRequestV4_9F_RawV8",
    "operation": operation_token,
    "payload": request_payload,
    "schema_version": "riskyieldmm_physical_projection_v4_9f_raw_v8"
  })))
```

The complete terminal and closure mappings in both `FINALIZE` and `RECOVER`
must equal their prebuilt plan bytes and IDs; IDs/hashes alone are
insufficient. Recovery never derives writer-dependent record bytes inside
the transaction.

Every result is a strict exact-key mapping:

```text
CandidateBatchResultV8
  candidate_id
  candidate_receipt_sequence
  candidate_receipt_hash
  receipt_count = 1

AttemptBatchResultV8
  candidate_id
  attempt_id
  attempt_receipt_sequence
  attempt_receipt_hash
  receipt_count = 1

FinalBatchResultV8
  candidate_id
  attempt_id | null
  recovered_prefix_id
  terminal_id
  closure_id
  first_receipt_sequence
  first_receipt_hash
  last_receipt_sequence
  last_receipt_hash
  receipt_count = 2

RecoveryBatchResultV8
  candidate_id
  attempt_id | null
  recovered_prefix_id
  terminal_id
  closure_id
  first_receipt_sequence
  first_receipt_hash
  last_receipt_sequence
  last_receipt_hash
  receipt_count = 2
  recovery_snapshot
  recovery_snapshot_id
  open_locator_snapshot_entry_id
  candidate_position = 0
```

IDs/hashes are exact lowercase 64-hex values; sequences are positive safe
integers. The final first receipt is the terminal, the last is its consecutive
closure. No batch result contains `finalization_observation_id` or the outer
`prefix_id`. `RecoveryBatchResultV8.recovery_snapshot` is the complete exact
snapshot from the hashed request; its embedded entry, root, snapshot ID, and
duplicated scalar IDs must recompute. This result blob is the durable replay
home for the random nonce and full snapshot and must remain within the
64-KiB one-batch-result ceiling.

### 11.3 Recovery snapshot

Exact domains are:

```text
RiskYieldMMA2MOpenLocatorSnapshotEntryV4_9F_RawV8
RiskYieldMMA2MOpenLocatorSnapshotRootV4_9F_RawV8
RiskYieldMMA2MStartupRecoverySnapshotV4_9F_RawV8
```

Entry and snapshot identities use exactly the Section 3.1
`semantic_id(domain, payload)` preimage. Their standalone serialization uses
the distinct flattened Section 3.1 record envelope; it never uses a
`measurement_schema` alias or places a `payload` member in that flattened
record.

`OpenLocatorSnapshotEntryV8.payload` has the exact keys:

```text
candidate_id
transport_session_id
campaign_manifest_id
sample_sequence
operation_sequence
operation_kind
candidate_receipt_sequence
candidate_receipt_hash
attempt_id | null
attempt_receipt_sequence | null
attempt_receipt_hash | null
pre_terminal_receipt_sequence
pre_terminal_receipt_hash
open_locator_snapshot_entry_id
```

The attempt ID/sequence/hash are either all present or all null. The entry ID
is `semantic_id()` under
`RiskYieldMMA2MOpenLocatorSnapshotEntryV4_9F_RawV8` with the exact payload
excluding `open_locator_snapshot_entry_id`.

The exact root preimage is:

```text
sha256_digest({
  "domain": "RiskYieldMMA2MOpenLocatorSnapshotRootV4_9F_RawV8",
  "ordered_open_locator_snapshot_entry_ids":
    [open_locator_snapshot_entry_id]
})
```

The snapshot payload has exact keys:

```text
projection_ledger_id
projection_store_observation_id
recovery_writer_fence_token_sha256
recovery_writer_fence_generation
snapshot_head_receipt_sequence
snapshot_head_receipt_hash
recovery_nonce
ordered_open_locator_snapshot_entries   # exact one full entry
open_locator_root_sha256
recovery_snapshot_id
```

`recovery_nonce` is exactly 32 random bytes encoded as 64 lowercase hex
characters. `recovery_snapshot_id` is `semantic_id()` under
`RiskYieldMMA2MStartupRecoverySnapshotV4_9F_RawV8` with the exact snapshot
payload excluding itself. `open_locator_root_sha256` is intentionally not a
semantic ID: it is `sha256_digest()` of the exact root object above. The
embedded entry is recomputed before the root and snapshot IDs are trusted.
The complete snapshot, which embeds the sole complete entry, is supplied in
the hashed `RECOVER` request. No unspecified process-memory or absent durable
snapshot-table lookup is permitted.

The root contains exactly one ordered entry ID. The snapshot contains ledger,
store observation, head sequence/hash, a fresh 32-byte nonce encoded as 64
lowercase hex characters, the exact entry, root, and snapshot ID. Because
unrelated mutation is fenced, the entry pre-terminal anchor equals the
snapshot head.

## 12. Independent bound generator

The generator imports no production module. It consumes literal codecs,
record-kind tables, operation symbols, parser rules, selector plans, registry
inventory, and hard ceilings. It:

1. independently parses each signed ingress input and computes the oracle;
2. computes the canonical finite abstract-state fixed point over every success
   and legal adverse DFA branch;
3. computes conservative schema/path upper bounds and verifies their complete
   derivation coverage;
4. computes exact entry-array and batch-metadata bytes;
5. reserves emergency convergence separately;
6. computes marker/probe/checkpoint/closure cross-products;
7. derives the admissible plan region;
8. emits a canonical JSON inventory and SHA-256; and
9. emits one required admission/conservative-rejection disposition for every
   frozen coordinate; optional concrete witnesses live only in the separate
   diagnostic report.

### 12.1 Self-contained codec and rule descriptors

Every opaque shape/variant/rule name is resolved by a complete embedded
descriptor.

`NativeShapeDescriptorV1` has exact keys:

```text
shape_role = REQUEST | RESULT
symbol
native_operation_token
schema_dialect = RAW_V8_CLOSED_SCHEMA_V1
strict_json_schema
maximum_value
maximum_canonical_octets
native_shape_id
```

`StrictEvidenceShapeDescriptorV1` is separate from a native request/result
shape and has exact keys:

```text
shape_name
evidence_role =
  FINALIZATION | EMERGENCY_ACTIVATION | TLS_PHASE_TRANSITION
operation_kind | null
evidence_kind
schema_dialect = RAW_V8_CLOSED_SCHEMA_V1
strict_json_schema
maximum_value
maximum_canonical_octets
strict_evidence_shape_id
```

Finalization and emergency-activation evidence require a non-null operation
kind; TLS phase-transition evidence requires null. Names/kinds are bounded manifest-frozen strings. The
maximum value/octet rules are identical to the closed-schema constructive
maximum below. The ID is `semantic_id()` under
`RiskYieldMMA2MStrictEvidenceShapeDescriptorV1V4_9F_RawV8` over all preceding
members. Every `finalization_evidence_shape_id` and
`transition_evidence_shape_id` in this document is exactly one resolved
`strict_evidence_shape_id`, never a `NativeShapeDescriptorV1`.

`RAW_V8_CLOSED_SCHEMA_V1` is not an implementation-selected JSON-Schema
dialect. Every schema node has exactly:

```text
type = OBJECT | ARRAY | INTEGER | STRING | BOOLEAN | NULL
nullable
properties | null
required | null
additional_properties | null
items | null
minimum | null
maximum | null
minimum_items | null
maximum_items | null
minimum_length | null
maximum_length | null
enum | null
const_present
const
string_language_id | null
maximum_value
maximum_canonical_octets
```

Every listed key is physically present. `const_present=false` means `const`
is null and inactive; `const_present=true` permits any canonical value,
including JSON null. Absence of a const constraint is therefore distinct from
a const-null constraint.

`nullable=true` denotes exactly the closed union of JSON null and the one
declared non-null `type`. `type=NULL` requires `nullable=false`. No other
implicit or open union is legal. Object nodes have a fixed property map, an
equal UTF-8-sorted required-key tuple, and `additional_properties=false`.
Every object property is present; nullable values use JSON null, never an
omitted property. Array nodes require finite safe `minimum_items` and
`maximum_items` and one item schema. Integer nodes require finite safe
`minimum` and `maximum`. Non-enum, non-const string nodes require finite safe
`minimum_length` and `maximum_length`, measured in ASCII octets, and one
non-null embedded `string_language_id`. Const/enum/non-string nodes require
that member null.

`BoundedStringLanguageDescriptorV1` replaces implementation-selected regex
parsing. It has exactly:

```text
language_name
ordered_ascii_codepoints
state_count
start_state
ordered_accepting_states
ordered_transition_records
minimum_length
maximum_length
maximum_string
maximum_canonical_octets
bounded_string_language_id
```

Codepoints are unique increasing integers in `0..127`; state IDs are
contiguous safe integers `0..state_count-1`; the start and accepting states
belong to that set, and `ordered_accepting_states` is strictly increasing and
duplicate-free. Each transition is exactly
`{from_state, ascii_codepoint, to_state}` and rows are strictly sorted and
unique by that integer triple. For every state/codepoint pair there is
exactly one row, so the automaton is deterministic and complete; a rejecting
sink may be used. A string is accepted iff its octet length is within the
literal finite bounds and its final state is accepting. The descriptor
language is nonempty.

`maximum_string` is the accepted string whose
`canonical_json_bytes(string)` is unsigned-byte lexicographically greatest
among those with the greatest canonical-JSON byte length. Raw unescaped
string-byte order is never used. The
generator recomputes it by dynamic programming over
`(position, automaton_state)` with exact canonical-JSON escape weights and
the same byte tie-break. The octet member equals its canonical JSON length.
The language ID is `semantic_id()` under
`RiskYieldMMA2MBoundedStringLanguageV1V4_9F_RawV8` over all preceding
members. A string schema's length bounds equal those in its resolved
descriptor and its constructive maximum equals the descriptor maximum.

The universe manifest contains exactly one required language declaration
whose `language_name=LOWERCASE_SHA256_HEX_V1`. Its
`ordered_ascii_codepoints` are the increasing ASCII values for `0..9` and
`a..f`; minimum and maximum length are both 64; states `0..63` advance by one
on every listed codepoint, state 64 is the sole accepting state, state 65 is
rejecting, and every listed transition from states 64 or 65 enters/remains in
65. Thus the complete 66-state DFA accepts exactly 64 lowercase hexadecimal
ASCII characters. Its `maximum_string` is 64 `f` characters and
`maximum_canonical_octets=66`. The expected identity of that one manifest
declaration is, by definition, `LOWERCASE_SHA256_HEX_LANGUAGE_ID`; every use
of that symbol must byte-equal this ID. A second declaration with the same
name, a different descriptor under the alias, or an unresolved symbolic
constant rejects.

Constraint modes are mutually exclusive:
`const_present=true` requires `enum=null` and
`string_language_id=null`; `enum!=null` requires `const_present=false` and
`string_language_id=null`; a non-const/non-enum STRING requires its language
ID. Const/enum candidates must also satisfy the declared type and
nullability; const null is legal only for a nullable node or `type=NULL`.
`enum`, when non-null, is nonempty, duplicate-free, and ordered by canonical
bytes. Every inapplicable member is null except the Boolean `const_present`.
Empty schema languages reject. There is no pattern grammar, host regex
engine, locale, Unicode normalization, or implicit default alphabet.

For schema `S`, its unique maximum is:

```text
maximum(S) =
  argmax over x validating against S of
    (len(canonical_json_bytes(x)), canonical_json_bytes(x))
```

The second tuple member is an unsigned-byte lexicographic tie-break. The
generator recomputes this maximum bottom-up: const/enum candidates are
enumerated; null and Boolean candidates are finite; an integer maximum is one
of its finite interval endpoints; a string maximum is obtained by
length-bounded dynamic programming over the embedded finite automaton with
canonical-JSON escape octets as weights; an object combines the independently
recomputed property maxima; an array repeats the item maximum through
`maximum_items`; and a nullable node compares its non-null maximum with
canonical JSON null. Every node's `maximum_value` and
`maximum_canonical_octets` must equal this independently recomputed result.
Thus every schema language is finite and every claimed maximum has a
constructive witness.

The descriptor `maximum_value` must byte-equal the root schema node's
independently recomputed `maximum_value`; its octet field must equal both the
root node's `maximum_canonical_octets` and the recomputed canonical byte
length. Mere schema validation of a claimed maximum is insufficient. The ID
is `semantic_id()` under the literal native-shape domain over all preceding
members.

`RecordVariantDescriptorV1` has exact keys:

```text
record_kind
variant_tag
schema_dialect = RAW_V8_CLOSED_SCHEMA_V1
strict_json_schema
ordered_literal_discriminants
maximum_record
maximum_canonical_octets
actor_event_count
raw_ingress_commit_count
record_variant_id
```

`maximum_record` byte-equals the root schema's constructive maximum, whose
literal discriminants are encoded as const constraints; its octet field
equals both root maximum octets and canonical byte length. The ID is
`semantic_id()` under the literal record-variant domain over all preceding
members.

Each `ordered_literal_discriminants` item is exactly:

```text
json_pointer_tokens
literal_value
```

`json_pointer_tokens` is a nonempty array of bounded property-name strings
that resolves from the record root to one leaf schema with
`const_present=true`; `literal_value` byte-equals that leaf's `const`.
Items are unique and strictly sorted by
`canonical_json_bytes(json_pointer_tokens)`. The array is exhaustive: it
contains every const-constrained leaf and no other leaf.

The generator-input manifest also embeds one
`RecordKindContributionV1` for every admitted record kind:

```text
record_kind
actor_event_count
raw_ingress_commit_count
record_kind_contribution_id
```

Both counts are literal safe integers in `0..1`, fixed by the current
projection receipt codec, and the ID is `semantic_id()` under
`RiskYieldMMA2MRecordKindContributionV1V4_9F_RawV8`. Records are unique and
strictly sorted by `record_kind`. Every variant's two contribution counts
must equal the sole resolved record-kind contribution; no variant can lower
or relabel them.

`ProjectionEntryVariantDescriptorV1` closes the receipt framing and has exact
keys:

```text
symbol
entry_position_within_symbol
record_variant_id
receipt_schema_dialect = RAW_V8_CLOSED_SCHEMA_V1
receipt_strict_json_schema
maximum_receipt
maximum_entry_object
maximum_receipt_canonical_octets
maximum_entry_object_canonical_octets
projection_entry_variant_id
```

The maximum receipt byte-equals the exact receipt schema's constructive
maximum, including its safe sequence/time/text and resolved record-kind/ID
constraints.
`maximum_entry_object` must equal exactly
`{"receipt": maximum_receipt, "record": resolved maximum_record}`.
Both octet fields recompute from canonical bytes. Position is positive and
contiguous inside the symbol. The ID is `semantic_id()` under the literal
projection-entry-variant domain over all preceding members.

`OperationBatchEnvelopeDescriptorV1` closes batch framing and has exact keys:

```text
symbol
native_operation_token
idempotency_key_schema_dialect = RAW_V8_CLOSED_SCHEMA_V1
idempotency_key_schema
maximum_idempotency_key
request_shape_id
result_shape_id
first_receipt_sequence_formula
last_receipt_sequence_formula
committed_at_schema_dialect = RAW_V8_CLOSED_SCHEMA_V1
committed_at_schema
maximum_committed_at
maximum_batch_metadata_object
maximum_result_blob_octets
maximum_batch_metadata_object_octets
operation_batch_envelope_descriptor_id
```

The two sequence formulas are pure-rule IDs resolved by the same inventory.
The idempotency-key and committed-at schemas are complete closed-schema
nodes, resolve every string-language ID through the embedded language
inventory, and independently reproduce their two claimed maxima.
`committed_at_schema` accepts only the canonical UTC serialization used by
the projection store; there is no host datetime formatter choice.
The metadata object is exactly the Section 5 batch object's constructive
maximum with its maximum idempotency key, token, request hash, safe sequences,
strict result, and canonical UTC commit time. Its result blob is the
canonical result bytes. All sizes recompute. The ID is `semantic_id()` under
the literal batch-envelope domain over all preceding members.

Parser-dependent guards do not hide parser execution inside a Boolean AST.
`IndependentParserOracleDescriptorV1` has exactly:

```text
oracle_kind =
  WEBSOCKET_PARSER | TLS_RECORD_SPLITTER |
  METRIC_STATE_SUMMARY_EXTRACTOR
oracle_name
oracle_version
logical_oracle_profile_id | null
execution_abi =
  RAW_V8_RESTRICTED_WASM_ORACLE_ABI_V1
abi_descriptor
abi_descriptor_id
wasm_module_base64
wasm_module_octets
wasm_module_sha256
entrypoint = raw_v8_oracle_eval
input_schema_dialect = RAW_V8_CLOSED_SCHEMA_V1
input_schema
output_schema_dialect = RAW_V8_CLOSED_SCHEMA_V1
output_schema
maximum_instruction_events
maximum_working_memory_octets
ordered_source_file_records
source_root_sha256
ordered_conformance_case_records
conformance_corpus_root_sha256
independent_parser_oracle_descriptor_id
```

`WEBSOCKET_PARSER` requires a non-null `logical_oracle_profile_id` that
resolves the one complete Step-2 ingress logical-oracle profile and byte-equals
the profile selected by every compatible ingress operation spec. Both
`TLS_RECORD_SPLITTER` and `METRIC_STATE_SUMMARY_EXTRACTOR` require this member
null. The profile record is an embedded Step-2 input, not a descriptor-selected
body; unresolved, duplicate, unequal, crossed-operation, or non-WebSocket
profile binding rejects before oracle execution. Because the member precedes
the terminal descriptor ID, it is part of the exact descriptor identity and
the universe/body bijection.

Each source-file record is exactly
`{repository_relative_path, source_utf8, octet_count, raw_file_sha256}` and
is strictly sorted by path. The supplied UTF-8 bytes must equal the count and
hash; source is reviewable from the descriptor without a filesystem lookup.
The root hashes that complete array under
`RiskYieldMMA2MIndependentParserOracleSourceV1V4_9F_RawV8`; the descriptor
ID is `semantic_id()` under the corresponding descriptor domain.

The source root is exactly:

```text
sha256_digest({
  "domain": "RiskYieldMMA2MIndependentParserOracleSourceV1V4_9F_RawV8",
  "ordered_source_file_records": exact complete ordered records
})
```

Source is audit provenance; the embedded WebAssembly module is the sole
executable oracle. Canonical padded RFC-4648 decoding of
`wasm_module_base64` must equal its octet count and raw SHA-256.

`abi_descriptor` has exactly:

```text
abi_version = raw_v8_restricted_wasm_oracle_abi_v1
wasm_binary_version = 1
allowed_value_types = [i32, i64]
allowed_opcode_names
imports = []
required_exports =
  [{name: memory, kind: MEMORY},
   {name: raw_v8_oracle_eval, kind: FUNCTION,
    params: [i32, i32, i32, i32], results: [i32]}]
memory_initial_pages
memory_maximum_pages
input_encoding = CANONICAL_JSON_UTF8
output_encoding = CANONICAL_JSON_UTF8
input_pointer = 0
output_pointer
output_capacity
fuel_accounting = ONE_PER_EXECUTED_ALLOWED_OPCODE
trap_disposition = REJECT
noncanonical_output_disposition = REJECT
abi_descriptor_id
```

The allowed opcode array is nonempty, unique, and strictly UTF-8 sorted. It
contains only deterministic integer, structured-control, direct-call, and
fixed-memory load/store operations required by the frozen modules. Float,
SIMD, threads, atomics, reference types, tables, indirect calls, imports,
bulk memory, `memory.grow`, clocks, randomness, filesystem, environment,
network, host callbacks, and nondeterministic extensions are forbidden.
Initial and maximum pages are equal positive safe integers; their byte size
equals `maximum_working_memory_octets`. Input and output regions are
nonoverlapping and statically fit that memory. `output_capacity` equals the
resolved output schema's independently computed maximum canonical octets;
`output_pointer + output_capacity` is within fixed memory. The verifier writes canonical
input bytes at pointer zero, calls the exact four-argument export with input
pointer/length and fixed output pointer/capacity, interprets the nonnegative
result as output length, and rejects a trap, negative/over-capacity length,
invalid UTF-8, noncanonical JSON, schema mismatch, or trailing bytes.
Instruction fuel is decremented exactly once per executed allowed opcode;
exceeding the positive limit rejects.

Every evaluation creates a fresh module instance: standard data segments are
applied once, all other memory bytes are zero, mutable globals have their
declared initial values, and no instance or output region is reused.
Start-function execution is forbidden unless the exact optional start export
is declared by the ABI; when declared, all of its executed opcodes consume
the same per-evaluation fuel before the entrypoint. The frozen V1 profiles
declare no start function.

The ABI ID is `semantic_id()` under
`RiskYieldMMA2MRestrictedWasmOracleABIV1V4_9F_RawV8` over every preceding ABI
member. Module validation against that exact ABI is deterministic under the
WebAssembly core integer semantics, so independent validators need not share
one executable build. The descriptor embeds and hashes all program/ABI bytes;
a runtime implementation name or host interpreter hash is not an identity
input.

Each conformance case is exactly
`{case_name, case_category, input, expected_output, conformance_case_id}`. Input/output
validate the descriptor schemas; names are unique; cases sort strictly by
case ID. The case ID is `semantic_id()` under
`RiskYieldMMA2MIndependentParserOracleConformanceCaseV1V4_9F_RawV8`.
The corpus root is:

```text
sha256_digest({
  "domain":
    "RiskYieldMMA2MIndependentParserOracleConformanceCorpusV1V4_9F_RawV8",
  "ordered_conformance_case_ids": exact ordered IDs
})
```

Every embedded case is executed and must byte-equal its expected output.
The universe manifest declares required case categories and coverage counts,
including all five OPEN and CLOSING shapes, fragmentation/coalescing,
malformed UTF-8/sequencing, hidden TLS input, and every boundary class; the
descriptor cannot satisfy coverage with a hash-only external corpus.

The oracle implementation imports neither the production parser nor
production projection modules. `WEBSOCKET_PARSER` takes bounded parser
state/tail plus decoded RAW bytes from the strict native symbol and outputs
complete-unit availability, consumed boundary, next parser state/tail,
literal parser outcome, ordered message-lineage IDs, automatic-output facts,
and every Section 8.1/8.3 parser equality field.
`TLS_RECORD_SPLITTER` takes the complete frozen splitter profile, ledger
before, terminal staging before, and exact new ciphertext chunks; it outputs
header milestones, declared/wire lengths, valid/invalid proof class, fed
record facts, after staging/ledger summary, and all counter/conservation
facts. Its corpus includes every 0/1/2/3/4/5-byte header boundary, zero and
maximum valid lengths, each invalid type/length/admissibility proof prefix, partial
body, complete body, hidden-OpenSSL-input rejection, handshake/application
profile row, every phase-specific 1/5/6-byte invalid
type/length/admissibility proof (with no invalid-version category), and
one-byte-over limits. `METRIC_STATE_SUMMARY_EXTRACTOR` takes one complete
concrete DFA state plus its frozen target-DFA ID and returns the
exact closed triple `{pending_effect_class, parser_summary, tls_summary}`; its
corpus covers every phase/tag and every boundary/nullness class. All three
descriptor kinds are required by
the universe manifest.

The pure-rule input below contains
`{oracle_descriptor_id, oracle_facts}`. Before any guard/update evaluation,
the independent verifier recomputes those facts from the strict pre-state and
symbol and requires byte equality. Operations/transitions that do not use a
parser require the exact null descriptor and null/empty oracle-facts value.
Rule ASTs may read recomputed facts but cannot supply, override, or trust
caller-provided parser conclusions.

`RAW2`/`TERMINAL_RAW3` state updates place their canonical decoded bytes into
the bounded retained-tail state before a later `P_*` transition. A `P_*`
symbol therefore recomputes from those pre-state bytes even though its own
actor event contains no RAW payload; after consumption, its update stores the
exact next tail/fragment bytes, counts, hashes, cursor, and dependency IDs.
Ambient projection lookup and hash-to-bytes reconstruction are forbidden.

Transition guards and counter updates are not opaque code strings.
`PureRuleDescriptorV1` has exact keys:

```text
rule_role =
  BOOLEAN_GUARD | SCALAR_EXPRESSION | STATE_UPDATE |
  NATIVE_BATCH_MATERIALIZER | FINALIZATION_CONTEXT_MATERIALIZER |
  INITIAL_SUFFIX_EXECUTION_CONTEXT_MATERIALIZER |
  SUFFIX_EXECUTION_CONTEXT_UPDATE
input_schema_dialect = RAW_V8_CLOSED_SCHEMA_V1
input_schema
ordered_input_assumption_rule_ids
result_schema_dialect = RAW_V8_CLOSED_SCHEMA_V1
result_schema
rule_ast
ast_node_count
pure_rule_id
```

The AST is a closed discriminated union:

```text
CONST   has exactly {op, value}
FIELD   has exactly {op, path}
OBJECT  has exactly {op, field_names, args}
OBJECT_MEMBER has exactly {op, field_name, args}
TYPED_EMPTY_ARRAY has exactly {op, item_schema, maximum_items}
STRING_CONCAT, UTC_DATETIME_STR_V1, UTC_ADD_NANOSECONDS
  have exactly {op, args, result_string_language_id}
every other operator has exactly {op, args}
```

Inactive keys are absent and any extra key rejects. Thus
`{"op":"CONST","value":null}` is an unambiguous constant JSON null. A `path`
is a nonempty array of exact object-member names resolved against
`input_schema`; array indexing is expressed only by `ARRAY_AT`. Legal
operators and truth are:

| `op` | Exact form and result |
|---|---|
| `CONST` | exact value, including null |
| `FIELD` | exact schema-resolved input path |
| `OBJECT_MEMBER` | one statically typed closed-object arg and one exact member name; returns that member's declared type |
| `NOT` | one Boolean arg |
| `AND`, `OR` | one or more Boolean args, evaluated in array order |
| `EQ`, `NE`, `LT`, `LE`, `GT`, `GE` | exactly two same-domain scalar args |
| `ADD`, `SUB`, `MUL`, `MIN`, `MAX` | exactly two safe-uint args; overflow or negative subtraction rejects |
| `LEN` | one bounded string/array/object arg |
| `IS_NULL` | one arg |
| `ARRAY` | one or more same-item-domain args; returns their ordered bounded array |
| `TYPED_EMPTY_ARRAY` | no args; returns the exact empty array with its complete declared item type and maximum cardinality |
| `ARRAY_AT` | bounded array and safe-uint index; out-of-range rejects |
| `ARRAY_APPEND` | bounded array and one item; returns the appended array |
| `ARRAY_CONCAT` | two same-item-domain bounded arrays |
| `ARRAY_EQ` | two same-item-domain bounded arrays; exact ordered equality |
| `ARRAY_CONTAINS` | bounded array and one same-domain item |
| `ALL_UNIQUE` | one bounded array; equality is canonical-value equality |
| `SHA256_CANONICAL` | one canonical value; returns lowercase hex digest |
| `STRING_CONCAT` | one bounded array of bounded strings; returns their concatenation under a statically proved maximum length |
| `CANONICAL_BASE64_DECODE` | one bounded canonical RFC-4648 padded-base64 string; returns bounded internal `BYTES` |
| `BASE64_ARRAY_DECODE` | one bounded array of canonical padded-base64 strings; returns a bounded `BYTES_ARRAY` |
| `BYTES_CONCAT` | one bounded array of internal `BYTES`; returns bounded internal `BYTES` |
| `SHA256_BYTES` | one bounded internal `BYTES`; returns a 64-character lowercase hex digest |
| `SHA256_BYTES_ARRAY` | one bounded `BYTES_ARRAY`; returns the equal-length ordered digest array |
| `BYTES_EQ` | two bounded `BYTES` values; exact octet equality |
| `SEMANTIC_ID` | exactly one literal domain string and one canonical payload; applies Section 3.1 `semantic_id()` |
| `UTC_ISO_VALID` | one string; returns Boolean under `CANONICAL_UTC_ISO_V1` |
| `UTC_DATETIME_STR_V1` | one valid canonical-Z UTC string; returns the exact Python aware-datetime `str()` form below |
| `UTC_LT`, `UTC_LE`, `UTC_GT`, `UTC_GE` | two valid canonical-Z UTC strings; compare parsed UTC instants, not bytes |
| `UTC_ADD_NANOSECONDS` | one valid UTC instant plus one safe-uint duration; returns canonical UTC under statically proved calendar range |
| `UTC_DIFF_NANOSECONDS` | later and earlier valid canonical-Z UTC instants; requires later >= earlier, both microsecond-aligned, and returns the exact safe-uint nanosecond difference |
| `OBJECT` | `field_names` is ordered/unique and args supply corresponding values |

Static validation resolves one exact `RuleValueTypeV1` for every AST node.
That closed type algebra is
`JSON_NULL | JSON_BOOLEAN | JSON_SAFE_UINT |
JSON_LITERAL_STRING(value) | JSON_FINITE_STRING_SET(ordered_values) |
JSON_STRING(language_id) |
JSON_ARRAY(item_type,max_items) | JSON_OBJECT(exact_fields) |
JSON_NULLABLE(non_null_type) |
BYTES(max_octets) | BYTES_ARRAY(max_items,max_item_octets,max_total_octets)`.
`JSON_NULLABLE(T)` maps one exact `nullable=true` schema node, requires `T`
to be a non-null JSON type, and forbids nested nullable and nullable
`JSON_NULL`. `FIELD` and `OBJECT_MEMBER` preserve this type exactly.
`CONST(null)` has `JSON_NULL`; `IS_NULL` accepts any JSON type; and `EQ`/`NE`
accept compatible nullable/non-null/null operands and implement exact JSON
null equality. Every other operator requiring `T` may consume
`JSON_NULLABLE(T)` only when same-input assumptions or the current symbolic
partition prove it definitely non-null before evaluation. Concrete null
consumption rejects; abstract possible-null consumption makes a required
totality claim fail. `OBJECT` accepts a nullable argument exactly where its
declared field schema is nullable.
The root may use only a JSON type and its entire statically derived value set
must be included in the descriptor's `result_schema`; every runtime result
must validate that schema. Internal nodes may use JSON or bounded
`BYTES`/`BYTES_ARRAY` types. Byte types are internal only and therefore do not
pretend to be `RAW_V8_CLOSED_SCHEMA_V1` nodes.
String CONST/enum/FIELD nodes resolve respectively to literal, finite-set, or
frozen-language types. Each special string-producing node resolves its
non-null `result_string_language_id`; the verifier proves by finite-DFA
product construction that every possible output belongs to that language.
The declared language must itself be embedded/frozen and its maximum bounds
must dominate the node's statically computed output bounds. This annotation
is part of the AST identity and prevents host-selected string result types.
`SHA256_CANONICAL`, `SHA256_BYTES`, and `SEMANTIC_ID` always resolve the one
manifest-frozen `LOWERCASE_SHA256_HEX_LANGUAGE_ID`; `SHA256_BYTES_ARRAY`
returns a bounded array whose item type is that same language. The referenced
descriptor accepts exactly 64 lowercase hexadecimal ASCII characters.
Every array operand has finite `maximum_items`; `ARRAY`, `ARRAY_APPEND`, and
`ARRAY_CONCAT` reject unless their worst-case result fits that bound.
`OBJECT_MEMBER` requires exactly one argument, rejects unless its refined
static type is a definitely non-null closed object containing `field_name`,
and projects that exact member
without a default or dynamic key. Its concrete and abstract semantics are
the pointwise projection of that member's value domain and must relations;
it is the only way to consume a member of an object returned by `ARRAY_AT`.
`TYPED_EMPTY_ARRAY.item_schema` is one complete canonical
`RAW_V8_CLOSED_SCHEMA_V1` JSON item schema; the validator derives its
`RuleValueTypeV1` using the same schema-to-type mapping as `FIELD`.
`maximum_items` is a safe uint equal to the resolved result array schema's
maximum; zero is permitted for an epsilon-only operation. It has no `args`
member and is the sole empty-array constructor, so static type derivation
never depends on an enclosing `OBJECT` context or an undefined serialization
of the mathematical type algebra.
`ARRAY_AT`, arithmetic, and every other partial operation must be total over
the descriptor's finite `input_schema` restricted by all resolved input
assumption rules; a possible out-of-range, overflow, negative subtraction, or
invalid temporal order inside that admitted subset invalidates the
descriptor. Assumption rule IDs are strictly increasing, resolve only earlier
Boolean rules, and form an acyclic graph. They are frozen in the universe
manifest with the consuming rule, are evaluated first at runtime, and all
must be true. Every direct or transitive assumption descriptor has
`input_schema_dialect` and complete `input_schema` byte-equal to the consuming
descriptor, has the exact closed Boolean result schema, and is evaluated on
the same immutable complete input object; no projection, field default,
role-specific reinterpretation, or ambient binding is legal. A schema
mismatch invalidates the consuming descriptor. Assumptions cannot be
generator-selected to shrink a native schema or an abstract edge partition.
A rule with no assumptions uses the empty array.
No unbounded iteration,
callback, map, filter, or reduce operator exists.

`BYTES` and `BYTES_ARRAY` are statically bounded internal rule types and can
never occur in a serialized input, output, state, record, or rule-root result. Base64 decoding
rejects noncanonical padding/alphabet. `CANONICAL_UTC_ISO_V1` accepts exactly
`YYYY-MM-DDTHH:MM:SSZ` or
`YYYY-MM-DDTHH:MM:SS.ffffffZ`, with Gregorian-valid dates, year
`0001..9999`, time fields in range, no leap second or offset, and a nonzero
six-digit fractional part when present. Its unique constructive maximum is
`9999-12-31T23:59:59.999999Z`.

`UTC_DATETIME_STR_V1` replaces `T` with one ASCII space and terminal `Z` with
`+00:00`, preserving the absent or exact six-digit fractional part:

```text
YYYY-MM-DDTHH:MM:SSZ
  -> YYYY-MM-DD HH:MM:SS+00:00

YYYY-MM-DDTHH:MM:SS.ffffffZ
  -> YYYY-MM-DD HH:MM:SS.ffffff+00:00
```

This total transform is used inside the `MESSAGE` idempotency-key relation;
the persisted canonical UTC value and journal datetime-string preimage are
not treated as the same bytes.

`UTC_ADD_NANOSECONDS` rejects unless the duration is a multiple of 1,000
nanoseconds and the entire statically possible date range remains in
`0001..9999`; it emits the unique canonical-Z representation.
`UTC_DIFF_NANOSECONDS` parses both operands under the same codec, subtracts
UTC instants as signed integer microseconds, rejects a negative difference,
and multiplies by 1,000 with safe-uint overflow proof. This is the only ACK
wall-duration-to-monotonic-duration bridge; the exact relation is:

```text
derived_ack_deadline_monotonic_ns =
  dispatch_completed_monotonic_ns
  + UTC_DIFF_NANOSECONDS(
      ack_not_after,
      dispatch_completed_at
    )
```

For `BOOLEAN_GUARD`, `SCALAR_EXPRESSION`, and `STATE_UPDATE`, the rule input
is the strict object `{state, symbol, trigger,
emergency_activation, finalization_context, sequence_context,
oracle_descriptor_id, oracle_facts}`.
`state` is the complete DFA state. `symbol` is the exact closed
`RuleSymbolValueV1={symbol_kind=NOT_APPLICABLE|NATIVE_BATCH,
native_batch|null}`. `NOT_APPLICABLE` requires null; `NATIVE_BATCH` requires
the strict decoded native batch
`{name, native_operation_token, idempotency_key, request, result,
ordered_records, first_receipt_sequence, last_receipt_sequence}`;
`trigger` is the exact emergency-trigger class;
`emergency_activation` is the closed pre-suffix evidence union below;
`finalization_context` is the closed lifecycle/result union below; and
`sequence_context` is exactly:

```text
base_first_receipt_sequence
committed_receipt_count
last_receipt_sequence | null
next_receipt_sequence
committed_operation_batch_count
next_operation_batch_ordinal
```

All non-null members are safe uints in
`0..9007199254740991`. Zero receipt count requires null last and
`next=base`; positive count requires
`last=base+count-1` and `next=last+1`.
`next_operation_batch_ordinal=committed_operation_batch_count+1`.
All arithmetic is safe-uint checked.

The constructor has exactly two lifecycle branches. For an attempted
operation,
`base_first_receipt_sequence=attempt_receipt_sequence+1`,
`committed_receipt_count=current_head_sequence-attempt_receipt_sequence`,
the last/null and next members follow the equations above, and committed
batch count is the exact contiguous target/emergency batch count. For a
candidate-only/no-attempt finalization,
`base_first_receipt_sequence=next_receipt_sequence=
candidate_receipt_sequence+1`, `committed_receipt_count=0`,
`last_receipt_sequence=null`, `committed_operation_batch_count=0`, and
`next_operation_batch_ordinal=1`. The current head must then be the candidate
receipt. Every finalizer and materializer receives this same constructed
value; neither an empty/default context nor a third branch is legal.

Before candidate creation, after resolving the admitted plan but before
persistence, the sealed journal context must satisfy:

```text
pre_candidate_receipt_sequence <=
  9007199254740991 - maximum_remaining_ledger_receipt_count

if maximum_combined_target_emergency_batch_count > 0:
  1 + maximum_combined_target_emergency_batch_count - 1
    <= 9007199254740991
```

`maximum_remaining_ledger_receipt_count` is the full-prefix component below
covering the candidate, optional attempt, target plus emergency receipts,
terminal, and closure—the complete frozen receipt layout of Section 4.1.
Observations nested in the artifact are not invented as extra ledger
receipts. Its exact value is re-resolved
through `admitted_plan_record_id -> full_prefix_bound_record_id` before each
headroom check. Define

```text
receipt_reservation_end_sequence =
  candidate.pre_candidate_receipt_sequence
  + maximum_remaining_ledger_receipt_count
```

with safe-uint arithmetic. This value is derived evidence, not a new
candidate/attempt identity field: candidate and attempt already retain the
admitted-plan ID and authoritative pre-write receipt sequence/hash needed to
recompute it byte-exactly.
The operation-batch reserve remains the combined target/emergency hard
ceiling and operation batch ordinals begin at one; no per-operation
`SequenceContextV1` is presumed to exist before candidate creation. Before an
attempt or emergency activation, the verifier re-resolves
the same plan and full-prefix component, requires the candidate's retained
pre-candidate sequence/hash to match the exact ancestor/expected head used by
the atomic candidate insert, and separately requires the authoritative
current head sequence/hash to byte-equal the last candidate/attempt/target
prefix receipt reconstructed by contiguous replay. It computes
`already_committed_receipt_span =
current_head_sequence - pre_candidate_receipt_sequence`, subtracts that exact
span from the reservation, and proves that
the remaining target/suffix/terminal/closure receipt layout ends no later
than `receipt_reservation_end_sequence`. Thus every canonical sequence
formula is total. Failure rejects before candidate persistence or, after
persistence, seals the operation for recovery; it is never wrapped,
saturated, or deferred to an unchecked suffix.
Members irrelevant to one of these three roles are still present as their schema
null/empty values, so no ambient data lookup is possible.

`RuleTriggerV1 = NOT_APPLICABLE | <one exact EmergencyTriggerClassV1 value>`.
Transition and finalization rules require `NOT_APPLICABLE`; emergency
state/trigger rules require one non-`NOT_APPLICABLE` class. This scalar is
the only trigger type in rule input and removes any implicit null or
out-of-vocabulary sentinel.

Emergency suffix selection receives one immutable
`EmergencyActivationInputV1` with exact keys:

```text
emergency_trigger_class
activation_evidence_shape_id
activation_evidence
activation_evidence_sha256
sealed_sequence_context
pre_candidate_receipt_sequence
receipt_reservation_end_sequence
emergency_activation_id
```

`EmergencyActivationValueV1` is the exact closed object
`{activation_kind=NOT_APPLICABLE|ACTIVE, active_input|null}`.
`NOT_APPLICABLE` requires `active_input=null`; `ACTIVE` requires the complete
`EmergencyActivationInputV1` object above. This tagged-object encoding is
valid `RAW_V8_CLOSED_SCHEMA_V1`; no string/object union, partial object, or
implicit default is legal. The `emergency_activation` rule-input member uses
this object.
The class is one exact non-`NOT_APPLICABLE` `RuleTriggerV1` value.
For emergency guard evaluation the scalar `trigger` is derived from, and must
byte-equal, `emergency_activation.active_input.emergency_trigger_class`; it is never an
independently supplied value. A mismatch rejects before any guard runs.
The shape ID resolves the operation/class-specific frozen
`EMERGENCY_ACTIVATION` strict evidence shape; the complete body validates it
and the digest is raw SHA-256 of its canonical bytes. It contains only facts
available before suffix selection: the current lifecycle/attempt/capability
anchors, limit or ambiguity observation, and any already-existing target
exception/cancellation/interruption evidence. It never claims a result,
terminal, closure, or receipt that the suffix has not produced.
`sealed_sequence_context` is the exact complete `SequenceContextV1` available
at activation; its relative counts byte-equal
`pre_state.relative_sequence_state`. It is retained in the activation
identity and is the sole absolute sequence source for suffix materialization.
Both receipt-sequence anchors are safe uints. Universally,
`receipt_reservation_end_sequence` equals

```text
pre_candidate_receipt_sequence
+ target_full_path_projection_entry_count
+ maximum_emergency_receipt_count
+ 4
```

where the target count is the resolved prerequisite six-class target
certificate's `projection_entry_count` root, the emergency count is
mechanically derived from manifest suffix rows plus conservative symbol
bounds, and four is candidate + maximum present attempt + terminal + closure.
This algebra uses only pre-universal inputs. At runtime, activation
construction additionally requires these two scalars to byte-equal the
candidate's retained pre-head and the independently re-resolved admitted-plan
full-prefix receipt component; that later equality is a runtime/postconstruction
check and is not an input or identity dependency of the universal
certificate.
`emergency_activation_id` is `semantic_id()` under the literal activation
domain over every preceding member.

The activation input is created before suffix selection, is not synthesized
by a pure rule, and is carried byte-for-byte unchanged while normal DFA
symbols execute.
Each normal transition still evaluates with its required
`trigger=NOT_APPLICABLE`, `emergency_activation=NOT_APPLICABLE`, and
`finalization_context=NOT_APPLICABLE`. After the suffix executes, the runtime
builds the complete actual `FinalizationContextV1` from the now-durable
operation result or recovery evidence and supplies it to the context guard
and matching finalizer. Its `terminal_trigger_class` equals the selected
suffix record's `terminal_trigger_class`, not the differently named emergency
class. For an epsilon suffix the evidence already exists; for a non-epsilon
suffix it includes the exact newly produced result/receipt anchors.
This separates normal transition semantics from terminal evidence without
losing the latter.

A `BOOLEAN_GUARD` has the exact non-null Boolean result schema. A
`SCALAR_EXPRESSION` has an exact null/Boolean/integer/string result schema;
both batch sequence-formula IDs resolve to this role with a non-null safe
integer result. A `STATE_UPDATE` is one root `OBJECT` whose result schema is
byte-equal to the complete DFA state schema. `ast_node_count` is independently
recomputed. The ID is `semantic_id()` under the literal pure-rule domain over
all preceding members. Evaluation has no I/O, clock, randomness, production
import, or user callback.

For one operation, `CommittedSuffixBatchValueV1` is one closed homogeneous
array-item schema:

```text
symbol
native_batch_by_symbol
```

`symbol` is the operation DFA's complete nonempty
`ordered_symbol_names` enum, including operations whose emergency suffixes
are all epsilon. `native_batch_by_symbol` is a closed object with exactly one
property named by each DFA symbol, sorted by UTF-8 bytes; each property is
nullable over that symbol's complete strict native-batch schema. Exactly the
property matching `symbol` is non-null and every other property is null. The
operation-specific maximum array cardinality is the manifest-derived
`maximum_emergency_policy_steps`; a shorter selected suffix requires the
array length to equal its already committed prefix length and its symbol tags
to byte-equal that suffix prefix in order.

A `NATIVE_BATCH_MATERIALIZER` is one root `OBJECT` over the exact input
`{emergency_activation, current_state, sequence_context,
ordered_prior_suffix_results}` and its result schema byte-equals the complete
native-batch schema for its one declared operation symbol. A
`FINALIZATION_CONTEXT_MATERIALIZER` is one root `OBJECT` over
`{emergency_activation, current_state, sequence_context,
ordered_prior_suffix_results}` and its result schema byte-equals the exact tagged
`FinalizationContextV1` schema for the suffix terminal class. These roles may
use the same closed AST operators and must be total over their declared input
schema; they do not broaden `SCALAR_EXPRESSION` or permit ambient values.

`INITIAL_SUFFIX_EXECUTION_CONTEXT_MATERIALIZER` is one root `OBJECT` over
`{emergency_activation,current_state}` and returns the
exact closed object
`{sequence_context,ordered_prior_suffix_results=[]}`; that empty array is
constructed by `TYPED_EMPTY_ARRAY` with the exact
`CommittedSuffixBatchValueV1` item type and operation-specific maximum.
Its `sequence_context` is exactly
`emergency_activation.active_input.sealed_sequence_context` after proving the relative
counts equal `current_state.relative_sequence_state`.
`SUFFIX_EXECUTION_CONTEXT_UPDATE` is one root `OBJECT` over
`{emergency_activation,pre_state,post_state,sequence_context,
ordered_prior_suffix_results,committed_native_batch}` and returns the same
closed object with exact receipt/batch sequence advancement and exactly one
new `CommittedSuffixBatchValueV1` wrapper appended. The wrapper's symbol is
the update descriptor's one frozen suffix-position symbol; its matching
variant contains the byte-identical committed native batch (including its
complete request, result, records, and receipt anchors) and all other
variants are null. Both schemas are operation-specific, statically bounded,
total, and unable to read future or ambient state. The same
`ordered_prior_suffix_results` field name and item schema is used by every
later materializer and by finalization; `ordered_suffix_results` is not a
second representation.

### 12.2 Exact deterministic bounded automaton descriptor

The four state machines in Section 7 are deterministic bounded extended
automata: phase transitions are finite and literal; bounded counters/anchors
are state members evaluated by pure rules. The only lifecycle vocabularies
are:

```text
TerminalTriggerClassV1 =
  RETURNED | RAISED_EXCEPTION | CANCELLED |
  INTERRUPTED | RECOVERED_ORPHAN

PathClassV1 =
  RETURN_SUCCESS | RETURN_INVALID_ADVERSE | RAISED_ADVERSE |
  CANCELLED_ADVERSE | INTERRUPTED_ADVERSE | RECOVERY
```

`FinalizationContextV1` is the exact tagged union:

```text
finalization_context_kind =
  NOT_APPLICABLE | RETURNED | RAISED_EXCEPTION |
  CANCELLED | INTERRUPTED | RECOVERED_ORPHAN
terminal_trigger_class | null
finalization_evidence_shape_id | null
finalization_evidence | null
finalization_evidence_sha256 | null
```

`NOT_APPLICABLE` requires all remaining members null. Every other tag requires
the equal non-null terminal-trigger class, the one operation/tag-specific
strict `StrictEvidenceShapeDescriptorV1` frozen in the universe manifest, a complete
evidence body validating that shape, and raw SHA-256 of its canonical bytes.
For an attempted operation, `RETURNED` embeds the complete exact
operation-specific V1/V2 result required by that finalizer (including ACK's
Boolean/V1 branches), not only a success Boolean.
`RAISED_EXCEPTION` embeds only the closed sanitized exception class/code and
exact durable cause anchors. Attempt-present `CANCELLED` and `INTERRUPTED`
embed their exact acknowledged lifecycle/attempt anchors.
`RECOVERED_ORPHAN` embeds the exact candidate/attempt/terminal recovery
disposition and uncertainty anchors. No traceback, exception message,
process-local object, or host-selected schema is legal.

Candidate-only/no-attempt finalization uses the dedicated strict
`NoAttemptFinalizationEvidenceV1` shape with exact keys:

```text
candidate_id
admitted_plan_record_id
admission_outcome_evidence
admission_outcome_evidence_id
target_authorization_outcome
terminal_trigger
cancellation_classification
operation_error_code | null
surfaced_exception_class | null
exception_class_chain
exception_message_sha256_chain
candidate_receipt_sequence
candidate_receipt_hash
pre_terminal_receipt_sequence
pre_terminal_receipt_hash
target_dfa_id
initial_target_dfa_state
target_transaction_count = 0
target_projection_entry_count = 0
target_projection_entry_canonical_bytes = 2
maximum_one_target_record_body_canonical_bytes = 0
aggregate_target_record_body_canonical_bytes = 0
target_operation_batch_count = 0
aggregate_operation_batch_metadata_bytes = 2
target_actor_event_count = 0
target_raw_ingress_commit_count = 0
operation_result_evidence = null
result_evidence_id = null
```

The pre-terminal sequence/hash byte-equal the candidate receipt sequence/hash;
contiguous replay proves no attempt or target receipt exists. The DFA
ID/state equal the operation descriptor and its exact initial state, and the
standard no-attempt `SequenceContextV1` above is used. The evidence's
candidate/admission/authorization members byte-equal the terminal and
published plan chain.
The trigger/error/exception members also byte-equal the terminal. Raised
branches require the bounded safe exception evidence fixed by Step 3;
cancellation has the exact `asyncio.CancelledError` head; interruption uses
the bounded non-cancellation `BaseException` chain; recovery uses its explicit
process-loss classification.

The no-attempt mapping is exhaustive and exclusive:

| Admission outcome | Required target-authorization outcome | Terminal trigger | Path class |
|---|---|---|---|
| `REJECTED`, `TIMED_OUT`, `CLOSED_BEFORE_ENTRY`, `FAILED_BEFORE_ENTRY` | `NOT_REACHED_NON_GRANT` | `RAISED_EXCEPTION` | `RAISED_ADVERSE` |
| `CANCELLED_BEFORE_ENTRY` | `NOT_REACHED_NON_GRANT` | `CANCELLED` | `CANCELLED_ADVERSE` |
| `INTERRUPTED_BEFORE_ENTRY` | `NOT_REACHED_NON_GRANT` | `INTERRUPTED` | `INTERRUPTED_ADVERSE` |
| `GRANTED`, attempt persistence exited by ordinary `Exception` | `ATTEMPT_PERSISTENCE_FAILED` | `RAISED_EXCEPTION` | `RAISED_ADVERSE` |
| `GRANTED`, attempt persistence exited by `asyncio.CancelledError` | `ATTEMPT_PERSISTENCE_FAILED` | `CANCELLED` | `CANCELLED_ADVERSE` |
| `GRANTED`, attempt persistence exited by non-cancellation `BaseException` | `ATTEMPT_PERSISTENCE_FAILED` | `INTERRUPTED` | `INTERRUPTED_ADVERSE` |
| `UNRESOLVED_PROCESS_LOSS` | `UNRESOLVED_PROCESS_LOSS` | `RECOVERED_ORPHAN` | `RECOVERY` |

For these rows, the tag-specific strict shape wraps the complete
`NoAttemptFinalizationEvidenceV1`; `RAISED_EXCEPTION`, `CANCELLED`, and
`INTERRUPTED` do not require an attempt. Every
attempt-present finalizer rejects this no-attempt shape, and every
attempt-absent finalizer rejects an attempted result/anchor shape. No other
outcome/authorization/trigger/path product is legal.

`TargetDFADescriptorV1` has exact keys:

```text
operation_kind
state_schema_dialect = RAW_V8_CLOSED_SCHEMA_V1
state_schema
initial_state
path_length_ranking_descriptor
ordered_symbol_names
ordered_pure_rule_descriptors
ordered_transition_records
ordered_return_finalization_records
ordered_adverse_finalization_records
ordered_recovery_finalization_records
semantic_conformance_proof
target_dfa_id
```

Each transition record has exactly:

```text
current_phase
execution_scope = NORMAL | EMERGENCY
symbol
eligibility_rule_id
guard_rule_id
state_update_rule_id
next_phase
```

`path_length_ranking_descriptor` is exactly:

```text
scope_field_path = /execution_scope
normal_scope_value = NORMAL
field_path = /target_symbol_step_count
initial_value = 0
increment_per_symbol = 1
maximum_symbol_steps
ordered_transition_ranking_obligation_records
```

The scope field resolves to the exact enum `[EMERGENCY, NORMAL]` and
`initial_state` sets it to `NORMAL`. The counter field resolves to a required
non-null safe-uint member of `state_schema`
with minimum zero and maximum exactly `maximum_symbol_steps`; `initial_state`
sets it to zero. The maximum is one operation-global manifest literal in
`1..65,536`, shared by every spec for that operation and embedded in the DFA
identity. It is an intentional protocol limit, not a bound-generator choice:
the preflight freezes it before generation, conformance tests exercise the
exact and blocked-plus-one boundaries, and Stage-1 acceptance requires at
least the manifest's exact required operation-viability fixture and named
coordinate to replay and be admitted under it. It does not
depend on a later plan, profile, budget, or generated result.
There is exactly one obligation record for every `NORMAL` transition row, in
the relative order of those rows:

```text
current_phase
execution_scope = NORMAL
symbol
eligibility_rule_id
guard_rule_id
state_update_rule_id
counter_update_expression_json_pointer
eligibility_limit_expression_json_pointer
```

There is none for an `EMERGENCY` transition. Each normal row's guard AST contains the exact
`EQ(FIELD(/execution_scope), CONST(NORMAL))` comparison at its root or only
below `AND` nodes. The counter-update pointer resolves exactly one output expression in the
closed state-update `OBJECT` tree, byte-equal to
`ADD(FIELD(/target_symbol_step_count), CONST(1))`; no other normal expression writes
that field. The eligibility-limit pointer resolves the exact
`LT(FIELD(/target_symbol_step_count), CONST(maximum_symbol_steps))`
subexpression. That subexpression is either the eligibility AST root or lies
only below one or more `AND` nodes—never below `OR`, `NOT`, or another
operator—so eligibility true implies the strict limit. The verifier checks
these AST shapes, paths, static safe-uint totality, and one-to-one transition
coverage directly; a claimed semantic implication or sampled execution is
insufficient. Every `EMERGENCY` row instead contains the dominating exact
scope comparison to `EMERGENCY`, leaves `target_symbol_step_count`
byte-equal to its pre-state value, and is governed by the separate emergency
policy counter/rank below. Thus every legal normal target symbol increments
the target counter exactly once, no legal `(K+1)`st normal symbol exists, and
no reset or hidden write can extend a target path. A frozen activation-state
update changes scope from `NORMAL` to `EMERGENCY` without emitting a target
symbol. The one-shot policy controller separately initializes its external
suffix ordinal, position, and rank from the uniquely selected manifest row;
none is written into the DFA state. No transition can be legal in both
scopes.

Each finalization record has exactly:

```text
phase
terminal_trigger_class
finalization_evidence_shape_id
path_class
result_guard_rule_id
```

Every rule ID resolves inside the descriptor. Every symbol resolves in the
embedded symbol-bound inventory. `phase` is one required enum member of
`state_schema`. `initial_state` validates against that schema and has the
literal operation initial phase. `ordered_symbol_names` is strictly
UTF-8-increasing and unique and equals the symbols used by all declared
transition rows; an unreferenced alphabet symbol is forbidden.
`ordered_pure_rule_descriptors` is strictly
increasing by `pure_rule_id` UTF-8 bytes and contains exactly the rules
referenced by this DFA.

The state schema also has one required non-null
`/relative_sequence_state` object:

```text
committed_receipt_count
committed_operation_batch_count
```

Both are safe uints and `initial_state` sets them to zero. Absolute journal
sequence numbers are invocation-specific and therefore never embedded in the
DFA identity. `SequenceContextV1` instead carries the sealed absolute base,
the same two relative counts, and their derived next/last values. Every normal
or emergency transition's state update constructs
`/relative_sequence_state` from the exact committed native-batch append and
the output counts byte-equal the context passed to the next transition. The
emergency activation update preserves it.

Transition rows sort strictly by
`(current_phase, execution_scope, symbol, eligibility_rule_id, guard_rule_id,
state_update_rule_id, next_phase)`; keys
`(current_phase, execution_scope, symbol, guard_rule_id)` are unique. Every row in one
`(current_phase, execution_scope, symbol)` group has the same embedded Boolean
`eligibility_rule_id`. For one strict
decoded symbol, evaluation is exactly:

1. validate the complete pre-state and require
   `pre_state.phase == current_phase` and
   `pre_state.execution_scope == execution_scope`, and require
   `pre_state.relative_sequence_state` byte-equal the two relative count
   members of `sequence_context`;
2. validate/decode the complete symbol input;
3. evaluate the eligibility rule and every candidate Boolean guard on the
   same immutable
   `(pre_state, symbol, trigger, sequence_context)`;
4. require `OR(all group guards) == eligibility`, plus exactly one true guard
   when eligibility is true and zero when false;
5. evaluate that row's state-update rule once on that same immutable input;
6. require the complete result to validate `state_schema` and
   `updated_state.phase == next_phase` and
   `updated_state.execution_scope == execution_scope`; the state-update AST
   must construct `/execution_scope` exactly as
   `FIELD(pre_state.execution_scope)` and must construct
   `/relative_sequence_state` as the two exact count members of the committed
   native-batch sequence append result; and
7. only then accept the transition.

Transition-rule input uses `symbol_kind=NATIVE_BATCH` and fixes `trigger` and `finalization_context` to their
literal `NOT_APPLICABLE` values, and its ASTs may not read either path; replay
of an already committed target prefix cannot depend on how the target later
exits. Finalization-rule input instead fixes
`symbol={symbol_kind=NOT_APPLICABLE,native_batch=null}`,
fixes `trigger=NOT_APPLICABLE`, and may read the complete
strict `finalization_context`.

`semantic_conformance_proof` is exactly:

```text
abstract_partition_rule =
  RULE_RELEVANT_ENDPOINTS_RELATIONS_AND_SCHEMA_TOP_V1
symbolic_proof_rule =
  RAW_V8_PURE_RULE_SUBSTITUTION_INTERVAL_RELATION_V1
ordered_normal_guard_partition_records
ordered_finalizer_partition_records
ordered_emergency_row_deferred_records
semantic_conformance_trace_root_sha256
```

It uses the exact `RuleAbstractValueV1`, canonical symbolic inference, and
verifier-generated trace construction defined in Section 12.3. One normal
guard-partition record is exactly:

```text
current_phase
execution_scope = NORMAL
symbol
eligibility_rule_id
ordered_transition_keys
ordered_input_partition_records
coverage_result = DEFINITELY_TRUE
pairwise_disjoint_result = DEFINITELY_TRUE
```

One input partition is exactly
`{abstract_rule_input_value, eligibility_result,
selected_guard_rule_id|null, ordered_guard_result_records}`. A guard result is
exactly `{guard_rule_id,state_update_rule_id,next_phase,result}` sorted by the
three-key transition tail. Eligibility true requires one selected true guard
and every other result false; eligibility false requires null selected ID and
all false. Group records sort by
`(current_phase,execution_scope,symbol,eligibility_rule_id)`, transition keys
sort by the full transition tuple, and input partitions sort by canonical
abstract-value bytes. Their exact union is the complete group rule-input
domain and intersections are empty.

One finalizer-partition record is exactly
`{phase,terminal_trigger_class,
ordered_finalizer_keys,ordered_input_partition_records,
coverage_result=DEFINITELY_TRUE,
pairwise_disjoint_result=DEFINITELY_TRUE}`. Its input partition is exactly
`{abstract_rule_input_value,selected_finalizer_key,
ordered_finalizer_result_records}`; one finalizer result is the complete
five-field finalizer key plus `result`, sorted by that key. Exactly one result
is true and all others false. Finalizer group records sort by
`(phase,terminal_trigger_class)` and partitions by canonical abstract-value
bytes. A group contains every complete five-field finalizer key for that
phase/trigger across all path classes; the uniquely selected key determines
`path_class`. The output classification is never used to split the input
domain into multiple simultaneously true groups.

The trace-root preimage is exactly
`{domain,descriptor_body_before_semantic_conformance_proof,
semantic_conformance_proof_without_trace_root,
ordered_recomputed_proof_steps}` where `domain` is
`RiskYieldMMA2MTargetDFASemanticConformanceTraceV1V4_9F_RawV8`, the proof
descriptor body contains every `TargetDFADescriptorV1` member preceding
`semantic_conformance_proof` in declared order, the proof body contains in
its declared order the five members preceding
`semantic_conformance_trace_root_sha256`, and proof steps are constructed by
the deterministic symbolic algorithm in Section 12.3. Neither the supplied
trace root nor `target_dfa_id` is in that preimage. `UNKNOWN`, uncovered
input, overlap, wrong key set, or trace mismatch rejects.

Each emergency-row deferred record is exactly
`{complete_transition_tuple,
closure_kind=DEFERRED_TO_EMERGENCY_UNIVERSAL_CERTIFICATE}`. Emergency rows are
not claimed reachable from the normal initial state. The array is the
duplicate-free complete set of all declared `EMERGENCY` transition rows,
strictly sorted by the canonical bytes of the complete transition tuple. For
one operation spec, the universal certificate contains as definitely-true
transition branches exactly the deferred rows referenced by at least one
position of that spec's manifest-required suffix rows. A deferred row not
referenced by any such suffix may remain syntactically dead and is not in
that certificate closure. Thus the external
non-symbol activation update is the only NORMAL-to-EMERGENCY bridge, without
inventing a symbol edge or concrete canonical witness.

When one phase/symbol has multiple rows, their guards are pairwise disjoint.
Across all bounded reachable states, the embedded eligibility equality above
is exhaustive under this proof. Concrete reachability of every declared
normal row is not a safety premise: a syntactically valid dead row is allowed
and only makes the conservative analysis no tighter. Every emergency row
referenced by a required suffix must be in the exact applicable universal
proof closure above; absence or an extra branch row invalidates the
descriptor.

Each finalization array sorts strictly by
`(phase, terminal_trigger_class, finalization_evidence_shape_id, path_class,
result_guard_rule_id)` and has unique rows.
Within and across the three arrays, guards for the same reachable
state/trigger are pairwise disjoint. Over every reachable complete-symbol
state and strict finalization-context input, exactly one finalization row
is true:

```text
ordered_return_finalization_records:
  RETURNED + RETURN_SUCCESS only; valid operation success/normal-return phases

ordered_adverse_finalization_records:
  RETURNED + RETURN_INVALID_ADVERSE,
  RAISED_EXCEPTION + RAISED_ADVERSE,
  CANCELLED + CANCELLED_ADVERSE, or
  INTERRUPTED + INTERRUPTED_ADVERSE

ordered_recovery_finalization_records:
  RECOVERED_ORPHAN + RECOVERY only
```

This trigger/path table is exact; the containing array and row path class
must agree. Recovery covers every stable complete-symbol reachable state and no partial
native batch. No row can classify one state/trigger/result into two
categories, and every legal finalization is covered.
No wildcard, regex, optional symbol, catch-all state, ellipsis, or unresolved
predicate is legal. `target_dfa_id` is `semantic_id()` under the literal DFA
domain over all preceding members.

### 12.2.1 Canonical generator universe and completeness root

The generator does not discover or emit its own required universe. After the
correction and generator source freeze, an independent preflight freezes one
canonical pre-generator input
`tests/raw_v8_target_bound_universe_manifest_v1.json`; two independent
implementations reproduce its identities/hashes before the bound generator
may run. The generator consumes that exact body read-only and embeds it
unchanged as `TargetBoundUniverseManifestV1`, with exactly:

```text
manifest_version =
  riskyieldmm_raw_v8_target_bound_universe_v1
universe_manifest_path =
  tests/raw_v8_target_bound_universe_manifest_v1.json
correction_document_path
correction_document_sha256
parent_protocol_path
parent_protocol_sha256
step2_inventory_input_sha256
generator_source_root
generator_source_manifest
generator_source_sha256
generator_version =
  riskyieldmm_raw_v8_bound_generator_v1
ordered_record_kind_count_records
ordered_required_bounded_string_language_records
ordered_required_tls_handshake_trace_profile_records
ordered_required_tls_record_splitter_profile_records
ordered_required_parser_oracle_records
ordered_required_oracle_conformance_categories
ordered_required_pure_rule_records
ordered_required_native_shape_records
ordered_required_strict_evidence_shape_records
ordered_required_record_variant_records
ordered_required_projection_entry_variant_records
ordered_required_operation_batch_envelope_records
ordered_required_target_dfa_records
ordered_required_metric_abstract_domain_records
ordered_required_component_bound_derivation_records
ordered_required_operation_symbol_records
ordered_required_transition_records
ordered_required_finalization_records
ordered_required_emergency_suffix_records
ordered_required_operation_viability_records
ordered_required_emergency_trigger_class_names
ordered_terminal_trigger_class_names
maximum_abstract_fixed_point_rounds = 1,000,000
maximum_abstract_state_count = 1,000,000
maximum_abstract_edge_count = 4,000,000
maximum_raw_successors_per_round = 8,000,000
maximum_rule_abstract_array_slots_per_value = 1,000,000
maximum_rule_abstract_array_transfer_candidates_per_ast_node = 8,000,000
maximum_universal_selection_partition_records = 1,000,000
maximum_universal_execution_value_occurrences = 4,000,000
maximum_universal_obligation_record_occurrences = 8,000,000
maximum_universal_recomputed_proof_trace_nodes = 16,000,000
maximum_restricted_wasm_instruction_events_per_evaluation = 10,000,000
maximum_total_abstract_successor_evaluations = 100,000,000
maximum_total_abstract_cell_product_candidates = 100,000,000
maximum_total_raw_successor_occurrences = 100,000,000
maximum_total_abstract_state_occurrences = 100,000,000
maximum_total_bellman_value_record_evaluations = 100,000,000
maximum_total_bellman_option_candidate_evaluations = 500,000,000
maximum_total_finite_automaton_state_visits = 100,000,000
maximum_total_finite_automaton_transition_candidates = 500,000,000
maximum_total_closed_schema_node_visits = 500,000,000
maximum_total_rule_ast_node_evaluations = 500,000,000
maximum_total_rule_abstract_array_slot_occurrences = 100,000,000
maximum_total_rule_abstract_array_transfer_candidates = 100,000,000
maximum_total_restricted_wasm_instruction_events = 500,000,000
maximum_total_rule_byte_octets_processed = 68,719,476,736
maximum_total_canonical_table_byte_occurrences = 68,719,476,736
maximum_generator_source_filesystem_nodes = 10,000
maximum_generator_source_file_count = 1,000
maximum_generator_source_one_file_octets = 67,108,864
maximum_generator_source_total_octets = 268,435,456
maximum_peak_canonical_table_bytes = 536,870,912
maximum_target_bound_universe_manifest_canonical_bytes = 536,870,912
maximum_target_bound_inventory_canonical_bytes = 1,073,741,824
ordered_plan_coordinate_requests
ordered_ceiling_descriptor_records
ordered_rejection_precedence_records
target_bound_universe_manifest_id
```

The manifest file's complete top-level object is exactly this
`TargetBoundUniverseManifestV1` including its terminal ID, with no wrapper or
extra key, and its raw bytes are
`canonical_json_bytes(complete_object) + b"\n"`. The independent construction
command is:

```text
python scripts/tests/generate_raw_v8_target_bound_universe_v49f.py \
  --step2 tests/raw_v8_step2_inventory_v49f.json \
  --output tests/raw_v8_target_bound_universe_manifest_v1.json

python scripts/tests/verify_raw_v8_target_bound_universe_v49f.py \
  --step2 tests/raw_v8_step2_inventory_v49f.json \
  --universe tests/raw_v8_target_bound_universe_manifest_v1.json
```

It uses the same nonsymlink same-directory atomic-write/fsync protocol later
specified for the inventory. It is outside `generator_source_root` and the
bound generator never imports it. The independent inventory verifier
reconstructs every required manifest declaration from separately encoded
normative constants and the Step-2 input, then requires raw-byte equality to
this file before verifying generator output; merely rehashing caller-supplied
manifest rows is insufficient.
The universe-only verifier likewise shares/imports neither the construction
script nor bound-generator source, independently reconstructs the complete
body and raw bytes, and must pass before either sealed generator invocation.

The literal paths are:

```text
correction_document_path =
  docs/research/v4_9f_a2_raw_v8_step3_target_and_lifecycle_correction_2026-07-26.md
parent_protocol_path =
  docs/research/v4_9f_a2_marker_operation_target_v8_protocol_freeze_2026-07-22.md
generator_source_root =
  tools/raw_v8_bound_generator
```

Both document hashes are lowercase SHA-256 of exact raw file bytes with no
newline normalization. The source manifest is exactly
`{root, ordered_entries}`; each entry is exactly
`{relative_path, octet_count, raw_sha256}`. It contains every regular
nonsymlink file recursively below the root and no other file; outputs live
outside the root. Every reachable filesystem node below the root must be
either a real directory or a regular nonsymlink file. A symlink, socket,
FIFO, device, mount traversal, or other special node rejects the source
closure. Repository-relative POSIX paths are ASCII, contain no empty, `.`,
or `..` segment, and sort strictly by UTF-8 bytes. The generator is executed
and independently reproduced only from a sealed copy constructed from these
manifested bytes. Importing a repository-local, site-package, user-site,
plugin, or dynamically loaded module outside that copy is forbidden. The
qualified CPython interpreter and standard-library primitives used only for
CLI parsing, file I/O, SHA-256, strict JSON parsing, and exact integer arithmetic are
permitted execution substrate rather than generator source; their output
remains subject to independent byte-for-byte reproduction. No host
stdlib parser/regex result is accepted where this contract requires an
embedded DFA or restricted-WASM oracle. The source hash is:

Source traversal itself is finitely bounded. Increment the filesystem-node
counter before classifying each root descendant and reject before node
`10,001`; increment the file counter before accepting a regular file and
reject before file `1,001`. Before opening or reading a file, `lstat` size
must be at most `maximum_generator_source_one_file_octets`; after the
descriptor is opened with the frozen no-follow/race checks, the exact bytes
read must equal that size. Add the size to a checked run-total source-octet
counter before hashing or copying and reject if it would exceed
`maximum_generator_source_total_octets`. Directory entries, files, and bytes
are processed in the exact path order above. The preflight, sealed launcher,
and verifier enforce the same four manifest caps independently; a streamed
copy or hash is not an exemption.

```text
sha256_digest({
  "domain":
    "RiskYieldMMA2MRawV8BoundGeneratorSourceManifestV1V4_9F",
  "root": "tools/raw_v8_bound_generator",
  "ordered_entries": exact complete entries
})
```

The manifest ID is `semantic_id()` under the literal universe-manifest
domain over every preceding member. Record-kind count records are those in
Section 12.1. Required native shapes, symbols, transitions, finalizers,
trigger classes, parser/language descriptors, plan coordinates, ceilings,
and rejection rules are complete machine-readable declarations, not hashes
of self-selected output arrays.

Each required descriptor record is exactly:

```text
descriptor_kind =
  BOUNDED_STRING_LANGUAGE | TLS_HANDSHAKE_TRACE_PROFILE |
  TLS_RECORD_SPLITTER_PROFILE |
  PARSER_ORACLE | PURE_RULE | NATIVE_SHAPE | STRICT_EVIDENCE_SHAPE |
  RECORD_VARIANT | PROJECTION_ENTRY_VARIANT | OPERATION_BATCH_ENVELOPE |
  TARGET_DFA | METRIC_ABSTRACT_DOMAIN | COMPONENT_BOUND_DERIVATION
scope_kind = SHARED | OPERATION
ordered_dependent_operation_kinds
operation_kind | null
declaration_name
descriptor_body_without_identity
expected_identity_field
expected_identity
```

`expected_identity_field` is the one literal field for its kind. The
preflight recomputes `expected_identity` from the complete supplied body and
rejects mismatch. Records are unique by `(descriptor_kind, operation_kind,
declaration_name)`, strictly sorted by
`canonical_json_bytes([descriptor_kind, operation_kind, declaration_name])`,
and each lives only in its correspondingly named manifest array. The pair
`(expected_identity_field,expected_identity)` is globally unique across all
required descriptor arrays; a shared body has one declaration with the
complete dependent-operation set, not one alias per operation. Null operation kind is legal
only when `scope_kind=SHARED`; `OPERATION` requires a non-null operation kind.
There is no descriptor-kind or evidence-role exception.

Scoping is derived by
`DESCRIPTOR_OPERATION_DEPENDENCY_CLOSURE_V1`. Its roots are every
operation-keyed required symbol, transition, finalizer, emergency suffix,
viability, metric-domain, component-derivation, and plan validation
declaration. Add that root's operation to every directly referenced
descriptor; then, in descriptor-ID and JSON-pointer order, propagate the
complete operation set through every schema-language, shape, variant,
envelope, rule/assumption, oracle/ABI/corpus, DFA, metric-domain, and
derivation reference until the first unchanged set map. An empty set is an
orphan and rejects. The sorted set byte-equals
`ordered_dependent_operation_kinds`. A singleton set requires
`scope_kind=OPERATION` and its sole value byte-equal `operation_kind`; a set
of two or more requires `scope_kind=SHARED` and
`operation_kind=null`. This same body-equality/reference-closure test applies
to `STRICT_EVIDENCE_SHAPE` TLS-phase, finalization, and activation roles and
to every parser/rule/language kind; prose labels cannot override it. Thus two
independent preflights cannot choose whether an identical referenced body is
shared or copied per operation. This freezes
complete schemas, ASTs, codecs, oracle program/corpus bodies, record variants,
envelope bodies, and each complete DFA body—including state schema, initial
state, embedded rule set, transitions, finalizers, and expected
`target_dfa_id`—before generator output exists.

Each required operation-symbol record is exactly:

```text
operation_kind
symbol
native_operation_token
native_request_shape_id
native_result_shape_id
ordered_record_variant_ids
ordered_projection_entry_variant_ids
operation_batch_envelope_descriptor_id
ordered_semantic_relation_rule_ids
```

Rows are unique and sorted by `(operation_kind, symbol)`. Each required
transition record is exactly:

```text
operation_kind
current_phase
execution_scope
symbol
eligibility_rule_id
guard_rule_id
state_update_rule_id
next_phase
```

and each required finalization record is exactly:

```text
operation_kind
path_class
phase
terminal_trigger_class
finalization_evidence_shape_id
result_guard_rule_id
```

Transition rows sort by the complete Section 12.2 tuple; finalizers sort by
`(operation_kind, path_class, phase, terminal_trigger_class,
finalization_evidence_shape_id, result_guard_rule_id)`. The emitted
descriptors must reproduce these IDs and
rows exactly; names without complete bodies or rule IDs are insufficient.

Coverage is bijective. Each required declaration occurs in exactly one
resolved emitted descriptor/bound/profile and every emitted item resolves to
exactly one required declaration. DFA rows, finalization rows, symbol
alphabets, record-kind contribution records, trigger vocabularies, and
selector/plan coordinates are compared as canonical multisets with
multiplicity one. A missing or extra declaration rejects before any bound is
trusted.

The six universal/symbolic caps above have exact work-unit mappings. Array
slots count the `ordered_array_item_presence_records` in one
`RuleAbstractValueV1`; transfer candidates count pre-dedup
`(input-length tuple,item-index)` candidates produced by one array AST node;
selection records count the serialized selection array; execution-value
occurrences count every value occurrence across activation, step-pre,
materialized-batch, step-post, terminal-pre, and materialized-context arrays;
obligation occurrences count every serialized step, transition-branch,
terminal, other-row, and other-finalizer record; proof nodes count the
verifier-recomputed maximally shared trace DAG before topological
serialization. Each counter is incremented in the canonical enumeration
order defined below and checked before accepting the next unit. Exceeding a
cap produces no certificate and leaves Raw V8 NO-GO; no truncation, spill,
sampling, alternative sharing, or host memory-dependent limit is permitted.

The fifteen computation aggregate caps are inventory-run totals, not
per-round loopholes. The sealed generator and independent verifier each start
all fifteen counters at zero and independently enforce the same limits over
their complete run; generator success never supplies or reduces a verifier
counter.
One abstract-successor evaluation is one attempted abstract transfer for one
canonically enumerated `(certificate,round-or-final-edge,state,transition
row)` before guard pruning; repeated evaluation in a later round counts
again. Before Bellman execution, each certificate computes exactly
`(maximum_symbol_steps + 1) * final_node_count * 10`; safe-uint failure or a
sum above the total Bellman cap rejects before `V_0`. Successor totals are
incremented in certificate-ID, round, state-ID, transition-tuple order and
reject before the first over-cap evaluation.

One Bellman-option candidate evaluation is one finalization or outgoing-edge
option inspected for one `(certificate,iteration,node,metric)` value record.
It increments before eligibility, successor-reachability, overflow, score,
tie-break, or duplicate handling, in certificate-ID, iteration, node-ID,
metric, option-kind, and canonical option-key order. `V_0` counts every
finalization option; each `V_k` counts those same finalization options plus
every outgoing edge, including an edge later discarded because its successor
is unreachable. The value-record precheck does not substitute for this
option-candidate counter.

One raw-successor occurrence is one Cartesian-expanded successor before
deduplication, including a successor later discarded as a duplicate or
absorbed by a join. The generator increments the run-total raw-successor
counter immediately before appending each occurrence in certificate-ID,
round-or-final-edge, source-state-ID, transition-tuple, pending-effect-class,
and ranking-cell-product order. The local per-round cap and the run-total cap
must both admit that occurrence. Thus a legal local maximum cannot repeat
across many fixed-point rounds without consuming the finite run-total budget.

One abstract-cell-product candidate is one tuple considered before an
empty-cell, inconsistent-fact, unreachable-branch, or duplicate filter while
projecting or splitting any abstract value. This run-total counter covers
every Cartesian enumeration in both generator and verifier, including
emergency root-seed projection, fixed-point and final-edge raw-successor
expansion, metric-node-to-rule-value lifting, and universal-selection
partition construction. It increments before inspecting the candidate in the
literal descriptor/claim, source-value, pending-effect-class, field, and
cell-product order prescribed by the applicable algorithm. A rejected,
empty, inconsistent, or later-deduplicated candidate still consumes one unit.
No equivalent unnamed Cartesian enumeration is exempt.

One abstract-state occurrence is one node placed in a complete root-seed or
fixed-point `N_r` table, including a byte-identical node repeated in a later
round, plus one final-node occurrence visited during final-edge derivation.
Occurrences are counted in certificate-ID, table-round, then state-ID order
before the table is accepted. The cap applies to the complete inventory run,
not to the number of distinct semantic state IDs.

One rule-AST-node evaluation is one visit to one concrete or abstract AST
node during descriptor validation, transition/finalizer execution, selection,
materialization/context update, semantic-conformance checking, or
verifier-generated proof recomputation, including every plan-coordinate
validation-rule visit and every per-coordinate component-derivation rule
visit; shared cached results still count once at each normative call site.
One array-transfer candidate is one pre-dedup
`(input-length tuple,item-index)` candidate already defined above. Both totals
accumulate across the complete inventory run in certificate/descriptor or
coordinate ID, claim locator, AST JSON-pointer, and local enumeration order.
The per-node candidate cap remains a local fail-fast bound; every candidate
also increments the aggregate counter. Exceeding either total rejects before
the next visit/candidate.

One finite-automaton state visit is one entry into a
`(position,state)`, `(language_state,emitted_length)`, or finite-product state
before accepting-state, reachability, maximum, or outgoing-transition
handling. It increments in descriptor/component ID, algorithm phase,
position/length, then state/product-tuple order. This counter advances even
when the alphabet or outgoing-transition set is empty.

One finite-automaton transition candidate is one transition inspected before
pruning, reachability, equality, maximum, or deduplication handling during
bounded-string `(position,state)` dynamic programming, special-string
finite-DFA product construction, or component compilation over
`(language_state,emitted_length)`. The counter increments in descriptor/
component ID, algorithm phase, position or emitted length, state/product
tuple, then ASCII-codepoint order. Every generator and verifier automaton
enumeration is covered; a rejecting, unreachable, or duplicate candidate
still consumes one unit.

One closed-schema-node visit is one entry into one schema node during schema
validation, constructive-maximum computation, native/evidence/variant/
envelope compatibility, descriptor coverage, component compilation, plan
validation, or independent verifier replay. It increments before type,
const/enum, reachability, compatibility, or cache handling in descriptor ID,
claim locator, and schema JSON-pointer order. Reusing a schema or cached
maximum at another normative call site counts again.

One abstract-array-slot occurrence is one slot-presence record constructed,
copied, intersected, unioned, validated, visited, or serialized before
deduplication in any `RuleAbstractValueV1` operation. It increments in
descriptor/claim ID, AST or schema JSON-pointer, array path, input-length
tuple, and item-index order. The per-value slot cap remains a local bound;
the run-total slot cap covers repeated transient values even when their final
records are empty, equal, cached, or discarded.

Every restricted-WASM descriptor's own
`maximum_instruction_events` is positive and no greater than the manifest
per-evaluation cap. One instruction event is one opcode dispatch under the
frozen restricted interpreter, including control, load/store, and terminal
opcodes; a trapped or rejected dispatch still counts. The run-total counter
includes manifest oracle conformance, metric-summary extraction,
fixed-point/singleton transfer, universal proof, and independent verifier
replay in canonical call-site order, and rejects before dispatching the first
over-cap opcode. A cache never erases the normative count of a required
evaluation.

`maximum_total_rule_byte_octets_processed` counts byte work performed by
rule/operator evaluation and proof replay. Before each canonical
serialization, semantic-ID or raw SHA-256 input, base64 decode/encode,
byte-array concatenation, or byte-equality comparison, add every input octet
read and every output octet materialized; repeated reads and byte-identical
cached values count again at each normative call site. It covers concrete,
abstract, selection, materialization, context, validation, component, and
verifier executions. The counter rejects before the first operation whose
checked addition would exceed the cap; an iterator, streaming hash, or
zero-copy view does not erase logically processed octets.

`maximum_peak_canonical_table_bytes` bounds the greatest canonical byte
length of any one complete root/node/raw-successor/final-edge/Bellman-value/
selection/execution-value/obligation/proof-node table before it is hashed or
discarded. The generator may stream canonical bytes but has no alternate
disk-spill representation. In addition, every such completed table contributes
its exact canonical byte length to
`maximum_total_canonical_table_byte_occurrences`, even when an equal table was
already produced in another round or certificate. The counter advances in
certificate-ID, phase, round, and table-kind order and rejects before hashing
or consuming the first table whose addition would exceed the cap. A cache,
streamed hash, unchanged round, or discarded transient table cannot erase
that occurrence. The two artifact-byte caps apply to the exact raw bytes
including their one terminal newline and are checked before atomic replace.
All products/sums use checked safe uint arithmetic. These checks, including
the cap member that failed, are deterministic global NO-GO reasons, never
coordinate dispositions.

Each required oracle-conformance category record is exactly
`{independent_parser_oracle_descriptor_id, case_category,
minimum_case_count}`. Counts are positive safe integers; rows are unique and
strictly sorted by descriptor ID/category UTF-8 bytes. Embedded corpus cases
must meet every minimum and may use no undeclared category.

Each required emergency-suffix declaration is exactly:

```text
operation_kind
phase
state_guard_rule_id
emergency_trigger_class
activation_evidence_shape_id
trigger_guard_rule_id
activation_state_update_rule_id
initial_suffix_execution_context_materializer_rule_id
ordered_symbols
ordered_symbol_materializer_rule_ids
ordered_suffix_execution_context_update_rule_ids
finalization_context_materializer_rule_id
terminal_kind | null
cause_code | null
anchor_role | null
terminal_trigger_class
finalization_evidence_shape_id
finalization_context_guard_rule_id
required_path_class
```

Rows sort strictly by the complete canonical record bytes and are unique.
The tuple `(operation_kind, phase, emergency_trigger_class,
activation_evidence_shape_id, state_guard_rule_id, trigger_guard_rule_id)` is
also unique. Exactly one row is selected for every pre-admission executable
selection-domain state/activation pair using only those pre-suffix fields; the later context
guard cannot choose which symbols execute. They are the literal machine-readable
expansion of Section 7.5, including every fallback partition. The emitted
suffix records are bijective with these declarations and must byte-equal all
policy fields; the finalization fields resolve the exact finalizer evidence
shape and a frozen pure Boolean context guard that validates the complete,
independently supplied `FinalizationContextV1` against the final suffix state,
trigger class, evidence/hash, and durable anchors. A generator cannot
replace a required conclusive suffix with
epsilon while preserving mere coverage.

The activation update is a frozen `STATE_UPDATE` rule over the selected
pre-state and activation. It changes only `execution_scope` from `NORMAL` to
`EMERGENCY` and preserves every other DFA-state member, including the normal
target-step counter and relative sequence state. The suffix row ordinal,
position, and remaining rank are external one-shot policy-controller fields
attached by the universal verifier/runtime and are not invented as DFA-state
members. The
native-batch materializer and execution-context-update arrays each have
exactly the same length as `ordered_symbols`; each materializer
entry is a frozen pure rule that constructs the complete native batch for
that position solely from the activation, current durable DFA state, and
earlier committed suffix results. No suffix rule may call or sample an owner,
driver, network, clock, randomness source, or not-yet-durable effect outcome.
The finalization-context materializer has the dedicated role above and
constructs the complete strict context solely from the final durable state,
activation, sequence context, and committed suffix results.
The initial-context materializer binds the target sequence anchor already
available at activation. For an attempted operation,
`base_first_receipt_sequence=attempt_receipt_sequence+1`;
`committed_receipt_count=current_ledger_head_sequence-
attempt_receipt_sequence`; zero count therefore means the head is still the
attempt receipt, while a positive count makes
`last_receipt_sequence=current_ledger_head_sequence`.
`next_receipt_sequence=current_ledger_head_sequence+1`.
The committed operation-batch count is the exact number of already committed
target/emergency batches reconstructed from the contiguous receipt span.
The activation constructor requires the authoritative current head
sequence/hash, candidate/attempt retained sequence/hash, and reconstructed
span root to match the live root and singleton locator before selection. Each
update rule then advances the exact receipt/batch counts and appends exactly
the one committed suffix result. There is no certificate-selected sequence
context, absolute base, ledger head, or result history.
If a conclusive policy needs a future nondeterministic result, a linear suffix
is invalid and Raw V8 remains NO-GO until a separately frozen branching
policy-automaton protocol replaces it. The current Raw V8 declarations are
accepted only when the universal certificate below proves this determinism
and total executability.

`ordered_required_emergency_trigger_class_names` is the unique strict
UTF-8-sorted set of every non-`NOT_APPLICABLE` trigger class occurring in the
complete required emergency-suffix array and byte-equals the closed
`EmergencyTriggerClassV1` vocabulary. `ordered_terminal_trigger_class_names`
is exactly the strict UTF-8-sorted unique array
`[CANCELLED, INTERRUPTED, RAISED_EXCEPTION, RECOVERED_ORPHAN, RETURNED]` and
byte-equals `TerminalTriggerClassV1`. Neither array is a multiset,
declaration order, or generator-selected subset.

One required operation-viability record is exactly:

```text
operation_kind
operation_spec_id
target_dfa_id
required_plan_coordinate_sha256
ordered_native_batches
ordered_sequence_contexts
finalization_context
expected_path_class = RETURN_SUCCESS
expected_final_state
expected_normal_symbol_count
maximum_symbol_steps
```

There is exactly one record for each of the four operation kinds, sorted by
`operation_kind`, and no extra record. It resolves one required DFA, spec,
and frozen coordinate from this same manifest. Native batches and sequence
contexts are complete strict values, their arrays have equal positive length,
and `expected_normal_symbol_count` equals that length and lies in
`1..maximum_symbol_steps`. Preflight and both generator verifiers replay the
fixture from the exact DFA initial state, require every transition to be
`NORMAL`, require the supplied sequence contexts to chain exactly, and
require the complete supplied finalization context to select exactly
`RETURN_SUCCESS` with the byte-equal expected final state. They also execute
the structural boundary check on an otherwise schema-valid normal transition
input with `/target_symbol_step_count=maximum_symbol_steps` and require
eligibility definitely false, proving the blocked plus-one case. The
coordinate's final disposition must be `ADMITTED_BY_TIER1_BOUND`; a
cross-product or bound rejection leaves Stage 1 NO-GO. This pre-generation
fixture is a functional conformance obligation, not a generator-selected
concrete maximizing path or canonical metric witness.

Each plan-coordinate request is exactly:

```text
operation_spec_id
instrumentation_mode = OFF | ON
checkpoint_selector_id | null
checkpoint_selector_entry_count
marker_capacity
loop_probe_capacity
local_shutdown_limit_vector | null
plan_coordinate_sha256
```

The coordinate hash is exactly:

```text
sha256_digest({
  "domain": "RiskYieldMMA2MPlanCoordinateV1V4_9F_RawV8",
  "coordinate": exact complete preceding coordinate members
})
```

Coordinates are unique by that hash and strictly sorted by its UTF-8 bytes;
equal hashes with unequal coordinate bytes reject.
`OFF` requires a null selector; `ON` requires one exactly resolved embedded
selector, including the canonical empty selector.
`checkpoint_selector_entry_count` is a safe uint set by independent preflight
to zero for `OFF` and to the exact length of the resolved selector's canonical
entry array for `ON`; the coordinate is rejected before hashing if the value
does not match. Component formulas bind this total scalar from
`PLAN_COORDINATE_REQUEST` and never conditionally dereference a null
`CHECKPOINT_SELECTOR`. Marker/probe capacities are literal, never generator
defaults. `local_shutdown_limit_vector` is null
iff the operation is not `LOCAL_SHUTDOWN`; otherwise it is this exact
positive-safe-integer 12-key object in this canonical property order:

```text
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

The poll value is exactly two, the parser value is at most 4,096, all Section
8.3 relationships hold, and the object byte-equals spec/precondition values.
The inventory has exactly one explicit disposition record for every
coordinate and none for an undeclared coordinate. Admission, conservative
bound rejection, and non-ceiling cross-product rejection are disjoint cases
defined in Section 12.4. An analysis failure produces no conforming inventory
and leaves Raw V8 globally NO-GO; it is not disguised as a coordinate
disposition.

Dependency order is acyclic:

```text
correction, parent, Step-2, and generator source bytes
-> schema, record, rule, parser-oracle, DFA, metric-domain, and
   component-derivation descriptors plus viability fixtures
-> TargetBoundUniverseManifestV1
-> conservative symbol bounds
-> six-class target full-path metric-bound certificates
   (exactly one per operation-spec/DFA tuple)
-> emergency universal-validation certificates
-> emergency metric-bound certificates
-> emergency suffix profiles
-> weighted target profiles
-> target-span budgets
-> component records and coordinate-level full-prefix bounds
-> coordinate dispositions and admitted plans
-> TargetBoundInventoryV1
```

No identity payload may reference an object in a later row.

### 12.3 Sound symbol and componentwise path bounds

Each `TargetSymbolBoundV1` has exact keys:

```text
operation_kind
symbol
native_operation_token
native_request_shape_id
native_result_shape_id
ordered_record_variant_ids
ordered_projection_entry_variant_ids
operation_batch_envelope_descriptor_id
projection_entry_count
projection_entry_element_octets
maximum_one_record_body_octets
aggregate_record_body_octets
operation_batch_result_blob_octets
operation_batch_metadata_object_octets
actor_event_count
raw_ingress_commit_count
ordered_semantic_relation_rule_ids
bound_kind = CONSERVATIVE_SCHEMA_UPPER_BOUND
target_symbol_bound_id
```

`operation_kind` is one of the four exact operation kinds and every symbol
resolution is keyed by `(operation_kind,symbol)`, never by symbol alone.
Every referenced descriptor is embedded and recomputed. Semantic relation
rules are strictly increasing by rule ID and all must return true for a legal
native symbol. Cross-links are exact:

```text
symbol =
  request.symbol =
  result.symbol =
  envelope.symbol =
  every projection-entry symbol

operation_kind =
  required operation-symbol row operation_kind =
  owning target-DFA operation_kind =
  every transition/edge resolver operation_kind

native_operation_token =
  request.native_operation_token =
  result.native_operation_token =
  envelope.native_operation_token

native_request_shape_id = envelope.request_shape_id
native_result_shape_id  = envelope.result_shape_id

len(ordered_record_variant_ids) =
  len(ordered_projection_entry_variant_ids) =
  projection_entry_count

for one-based position i:
  projection[i].entry_position_within_symbol = i
  projection[i].record_variant_id =
    ordered_record_variant_ids[i]
```

Entry positions are exactly `1..count`.
`projection_entry_element_octets` is the sum of resolved maximum entry-object
lengths with no array brackets or commas.
`operation_batch_metadata_object_octets` equals the resolved batch-envelope
object length with no array framing. All other metrics are:

```text
maximum_one_record_body_octets =
  max(resolved record maximum octets, default 0)

aggregate_record_body_octets =
  sum(resolved record maximum octets)

operation_batch_result_blob_octets =
  envelope.maximum_result_blob_octets

actor_event_count =
  sum(resolved record-kind actor-event contributions)

raw_ingress_commit_count =
  sum(resolved record-kind RAW-ingress contributions)
```

Every value is a closed-schema upper bound and is deliberately labelled
conservative even when a concrete native batch can attain it. This removes
arbitrary concrete filler/ID/timestamp choices from canonical identities.
Conservative bounds remain valid for safety admission when their values fit
the ceilings; the label does not itself cause rejection. The bound ID is
`semantic_id()` under the literal symbol-bound domain over all preceding
members.

For an ordered path with complete symbol-count map `c_s`:

```text
entry_count = sum(c_s * symbol_s.projection_entry_count)

target_projection_entry_canonical_bytes =
  2
  + sum(c_s * symbol_s.projection_entry_element_octets)
  + max(0, entry_count - 1)

batch_count = sum(c_s)

aggregate_operation_batch_metadata_bytes =
  2
  + sum(c_s * symbol_s.operation_batch_metadata_object_octets)
  + max(0, batch_count - 1)
```

Thus one array wrapper and the exact global comma count are charged; repeated
symbols never duplicate brackets.

`LegalPathMaterializationCertificateV1` is a noncanonical diagnostic record
with exact keys:

```text
certificate_purpose =
  STATE_REACHABILITY | SYMBOL_BOUND_MAXIMUM | DFA_METRIC_MAXIMUM |
  REJECTED_BOUNDARY
operation_kind
operation_spec_id
target_dfa_id
bound_symbol | null
path_class | null
terminal_trigger_class | null
emergency_activation
required_emergency_suffix_record_ordinal | null
finalization_context
start_state
start_state_reachability_certificate_id | null
ordered_step_records
final_state
finalization_context_guard_rule_id | null
finalization_guard_rule_id | null
metric_member | null
computed_metric_value | null
boundary_materialization_kind =
  TARGET_PATH | TARGET_SPAN
boundary_materialization
boundary_materialization_sha256
legal_path_materialization_certificate_id
```

Each step is exactly:

```text
step_ordinal
pre_state
current_phase
execution_scope
symbol
eligibility_rule_id
guard_rule_id
state_update_rule_id
next_phase
native_batch
sequence_context
ordered_projection_entries
operation_batch_metadata_object
post_state
```

`SYMBOL_BOUND_MAXIMUM` requires `bound_symbol` non-null, exactly one step
with that symbol, and no finalization requirement; every other purpose
requires `bound_symbol=null`. A diagnostic report may associate the
certificate with a symbol bound by an explicitly noncanonical report field;
there is no canonical proof map or identity edge.
`STATE_REACHABILITY` starts at the DFA initial state, has null path
class/trigger/finalization/metric members, has
`emergency_activation=NOT_APPLICABLE`, contains an arbitrary legal prefix,
and proves only its exact final state. Only this purpose may satisfy another
certificate's `start_state_reachability_certificate_id`.

Purpose-tag truth is exhaustive:

| Purpose | Bound symbol | Lifecycle/path/finalizer | Metric/value | Allowed materialization |
|---|---|---|---|---|
| `STATE_REACHABILITY` | null | nullable fields null; activation/context `NOT_APPLICABLE` | both null | `TARGET_PATH` |
| `SYMBOL_BOUND_MAXIMUM` | present | nullable fields null; activation/context `NOT_APPLICABLE` | both null | `TARGET_PATH` |
| `DFA_METRIC_MAXIMUM` | null | trigger class/path/finalizer and matching complete context all present; activation/suffix/context-guard members not applicable/null | both present | `TARGET_PATH` |
| `REJECTED_BOUNDARY` | null | activation/suffix/context-guard not applicable/null; exact terminal values and matching context required only when its body includes a finalized target path | both present | `TARGET_PATH` or `TARGET_SPAN` |

Every inactive nullable field is null; active fields are non-null. A
noninitial start requires a reachability-certificate ID; the initial state
requires it null.

Ordinals start at one and are contiguous; states chain byte-for-byte. Every
step passes Section 12.2 transition evaluation using its complete
`SequenceContextV1`, both native schemas, every
semantic relation rule, positional record/receipt links, sequence
contiguity, the canonical UTC codec, and exact operation-batch
reconstruction. Its target-span component is derived as:

```text
{
  "ordered_projection_entries":
    concatenation of all step projection entries,
  "ordered_operation_batch_metadata_objects":
    one step metadata object per step
}
```

For `TARGET_PATH`, `boundary_materialization` is exactly
`{ordered_steps, target_span}`; for `TARGET_SPAN`, it is the derived span
above. This certificate never claims a full-prefix or sample materialization.
Those bounds use the deterministic component records below, and a
conservative composition is never relabelled as a reachable witness. Every
component body and identity resolves through the embedded Step-2 input and
inventory; a hash-only component is forbidden.

The materialization hash is `sha256_digest()` of
`{"domain":"RiskYieldMMLegalBoundaryMaterializationV1V4_9F_RawV8",
"materialization_kind": exact kind,
"materialization": exact complete body}`. A complete path whose purpose
requires finalization satisfies exactly one finalization guard evaluated
against its complete matching `finalization_context`. A noninitial start
requires a reachability
certificate whose final state equals this start; certificate-reference
graphs are acyclic. The certificate identity covers every preceding member.

These diagnostic certificates are excluded from
`TargetBoundUniverseManifestV1`, `TargetBoundInventoryV1`, every canonical
profile/budget/component/disposition identity, and the Raw V8 GO decision.
They may be emitted into a separately hashed diagnostic report for
falsification and human inspection, but their presence, absence, order, or
choice among multiple legal materializations cannot change admission.

Required Stage-1 componentwise path bounds use a finite metric-relevant
abstract-state quotient. Exhaustive concrete-state enumeration is explicitly
not required: concrete 256-bit IDs, timestamp values, payload bytes, and
arrays would make that artifact finite but non-materializable.

`MetricAbstractDomainDescriptorV1` has exact keys:

```text
abstract_domain_version =
  riskyieldmm_raw_v8_metric_abstract_domain_v1
target_dfa_id
ordered_phase_names
ordered_counter_domain_records
ordered_enum_domain_records
ordered_length_domain_records
ordered_nullness_domain_records
ordered_identity_field_paths
ordered_timestamp_field_paths
ordered_pending_effect_class_names
ordered_ranking_counter_field_paths
ordered_ranking_transfer_obligation_records
ordered_primitive_metric_descriptor_records
parser_summary_schema
tls_summary_schema
metric_state_summary_extractor_oracle_descriptor_id
threshold_derivation_rule =
  SCHEMA_ENDPOINTS_AND_RULE_CONSTANTS_PLUS_MINUS_ONE_V1
join_rule = PHASE_LOCAL_THRESHOLD_HULL_AND_MUST_RELATIONS_V1
widening_rule = CANONICAL_THRESHOLD_ROUNDING_V1
transfer_rule =
  SINGLETON_EXACT_ELSE_RANKING_INTERVAL_AND_SCHEMA_TOP_V1
oracle_abstract_rule =
  SINGLETON_EXECUTE_ELSE_OUTPUT_SCHEMA_TOP_V1
summary_extractor_abstract_rule =
  SINGLETON_EXECUTE_ELSE_OUTPUT_SCHEMA_TOP_V1
metric_abstract_domain_descriptor_id
```

Every state-member reference in this descriptor is one canonical RFC-6901
JSON Pointer from the complete DFA state root; the empty pointer is forbidden
and `~`/`/` escaping is canonical. Repeated leaf names in different objects
therefore cannot alias.

Each counter record is exactly
`{field_path, minimum, maximum, ordered_thresholds}`. Thresholds are the
strictly increasing unique clipped set containing the field's schema
endpoints, zero/one, every integer constant that can reach that field through
a frozen guard/update/assumption AST, and each such value minus/plus one when
inside the field interval. Each enum record is exactly
`{field_path, ordered_values}` and contains the exact finite value set. Each
length record is exactly
`{field_path, minimum_length, maximum_length, ordered_thresholds}` for a
bounded string/bytes/array field. Its thresholds use the same endpoint,
zero/one, constant, and clipped plus/minus-one construction, where constants
are every `LEN` comparison/update constant reachable from that path. Each nullness-domain record is exactly
`{field_path}`.

The four record arrays are duplicate-free and strictly increasing by
`field_path`. They are exhaustive respectively over every safe-uint state
path that a guard/update/metric can read or write, every finite-enum/Boolean/
nullable-tag path such a rule can read or write, and every bounded
string/bytes/array path whose length can affect a guard, update, oracle input,
or metric, plus every nullable state path read by any rule, summary, or
identity relation. No unrelated state path may be added to alter joining. Identity
and timestamp arrays likewise contain canonical JSON Pointer paths, are
unique and strictly UTF-8 sorted, and exhaust every equality/hash/ID or UTC
path referenced by a frozen rule.

`ordered_ranking_counter_field_paths` is the strictly UTF-8-sorted exact
subset of counter-domain paths whose value can affect eligibility, a loop
limit, an emergency limit, or covered-path termination. It is not
generator-selected. There is exactly one ranking-transfer obligation for
every `(current_phase, execution_scope, symbol, guard_rule_id,
state_update_rule_id, field_path)` transition/ranking-path product, sorted by
that tuple:

```text
current_phase
execution_scope
symbol
guard_rule_id
state_update_rule_id
field_path
update_expression_json_pointer
required_abstract_update =
  SUPPORTED_RANKING_AST
claimed_enabled_relation =
  EQ | LE | LT | GE | GT | UNCONSTRAINED
```

The JSON pointer resolves the unique expression that constructs that output
path inside the state-update rule's closed `OBJECT` AST. Every ranking path
must be explicitly constructed on every transition; omission, duplicate
construction, schema-default insertion, or an unsupported expression
invalidates the required descriptor. The verifier independently proves any
non-`UNCONSTRAINED` relation between pre/post values for every abstract input
where all assumptions, eligibility, and the selected guard can hold.
`UNCONSTRAINED` permits resets between phases but still requires the exact
supported expression transformer; it never means schema top. These
obligations preserve the bounded counters needed to prove loop convergence
without claiming precision for payloads, IDs, or timestamps.

`ordered_phase_names` byte-equals the strictly UTF-8-sorted phase enum in the
resolved DFA state schema. `ordered_pending_effect_class_names` byte-equals
the strictly sorted closed pending-effect vocabulary derived from the DFA
state and emergency declarations; neither array is generator-selected.
Parser and TLS summaries are complete closed schemas over phase/status,
bounded length intervals, fragment/record completeness, required hash
nullness, counter intervals, and exact finite outcome classes; they never
carry payload bytes or hash values.
The summary-extractor ID resolves exactly one embedded
`METRIC_STATE_SUMMARY_EXTRACTOR` restricted-WASM descriptor whose input schema
byte-equals the target DFA state schema plus constant DFA ID and whose output
schema byte-equals the pending-effect enum plus the two summary schemas.
Concrete abstraction executes it and requires exact output. A singleton
abstract input executes it; a nonsingleton uses the unique output-schema top.
No generator-written projection table or host state inspector is legal.

For every counter or length domain record, cells are the unique increasing
partition obtained by emitting each threshold as a singleton cell and each
nonempty integer gap between adjacent thresholds as one closed interval.
Cells sort by `(lower_inclusive, upper_inclusive)` and receive contiguous
zero-based ordinals. A concrete value has exactly one cell. An abstract
interval is the smallest contiguous cell range covering its values; join is
the smallest cell-range hull covering both operands; threshold rounding maps
raw endpoints to the unique containing cells. These formulas, including
endpoint clipping, define `threshold_cell_ordinal`, hull, and widening
without an implementation-selected partition.

The primitive metric array contains exactly one record for each member below,
strictly sorted by `metric_member`, with no extra member:

```text
actor_event_count
aggregate_record_body_octets
maximum_one_operation_batch_result_blob_octets
maximum_one_record_body_octets
operation_batch_array_element_score
operation_batch_count
projection_entry_array_element_score
projection_entry_count
raw_ingress_commit_count
transaction_count
```

Each record is exactly
`{metric_member, path_accumulator, target_root_accumulator,
emergency_root_accumulator}`. Count and aggregate members use `SUM` in all
three accumulator fields. Both maximum-one members use `MAX` in all three.
The two array-element scores use `SUM` along edges,
`TARGET_ARRAY_FRAMING` at a target root, and
`OPTIONAL_ARRAY_SEGMENT_FRAMING` at an emergency root. This exact array is a
required manifest declaration and byte-equals every emitted abstract-domain
descriptor; a certificate cannot choose its metric vocabulary or
accumulator.

One `AbstractStateV1` has exactly:

```text
phase
execution_scope
ranking_counter_cell_key
ordered_counter_intervals
ordered_enum_value_sets
ordered_length_intervals
ordered_nullness_records
ordered_must_equal_identity_partitions
ordered_must_not_equal_identity_pairs
ordered_timestamp_order_records
pending_effect_class
parser_summary
tls_summary
emergency_suffix_cursor | null
abstract_state_id
```

Intervals use only declared thresholds. One must-equality partition is
exactly `{representative_field_path, ordered_member_field_paths}`. Members are
strictly sorted, nonempty, the representative is their UTF-8-smallest path,
and the partitions cover every identity-domain path exactly once; a singleton
represents no known equality to another field. One must-not-equal pair is
exactly `{lower_field_path, upper_field_path}` with
`lower_field_path < upper_field_path` by UTF-8 bytes; both paths exist, are in
different equality partitions, and the sorted pair array contains exactly
the inequalities true for every represented concrete state.

One timestamp-order record is exactly
`{lower_field_path, upper_field_path, relation}` with the same canonical path
orientation. Relations are only `LT|LE|EQ|GE|GT`; swapping a source
orientation requires the exact inverse (`LT<->GT`, `LE<->GE`, `EQ->EQ`).
The sorted array contains exactly the relations true for every represented
concrete state; absent means unknown, including nullable cases. A timestamp
relation may be present only when both paths are definitely non-null under the
nullness records. Pairs/records are duplicate-free and strictly sorted by
their complete tuples. Abstraction of one concrete state is therefore unique.
Counter and length interval records are exactly
`{field_path, lower_inclusive, upper_inclusive}`; enum records are
`{field_path, ordered_possible_values}`; nullness records are
`{field_path, possible_null, possible_non_null}`. Each array has exactly one
record for every corresponding abstract-domain record, in identical
field-path order; at least one nullness Boolean is true and a singleton
concrete state sets exactly one. Identity partitions/pairs and timestamp-order records use
only paths from their exhaustive domain arrays and have canonical
unsigned-byte ordering. Parser/TLS summaries validate the exact summary
schemas and include every declared field.
The exhaustive enum records for `/phase` and `/execution_scope` are always
the singletons `ordered_possible_values=[phase]` and
`ordered_possible_values=[execution_scope]`; duplicated scalars and abstract
fields cannot disagree.
`ranking_counter_cell_key` is the exact array of
`{field_path, threshold_cell_ordinal}` for every monotone counter/offset that
appears in an eligibility, limit, or termination rule, in the corresponding
counter-domain array order. The ordinal is the unique interval cell induced
by that record's ordered thresholds and is independently recomputed; no
field may be omitted or repeated. Join is
per-phase/per-scope/per-cursor/per-ranking-cell: threshold hull for intervals, set union for may-enums
and nullness, and intersection for must-equality, must-inequality, and time
facts. Widening rounds outward to the next declared thresholds. Different
phase, execution scope, pending-effect class, ranking-counter cell, or emergency cursor values
are never joined.
For each parser or TLS summary independently, byte-identical summary values
join to that value; two unequal summary values join to the one complete
closed output-schema top, and top joined with anything remains top. Widening
uses the same rule. No fieldwise implementation-selected summary merge is
permitted. Thus summaries may be absent from the join key without leaving
their joined value or state identity ambiguous.
These finite rules make every abstract identity independently reproducible.
`abstract_state_id` is `semantic_id()` under
`RiskYieldMMA2MAbstractStateV1V4_9F_RawV8` over every preceding abstract-state
member. For an oracle input whose complete abstract value is singleton, the
verifier executes the frozen restricted-WASM oracle and abstracts its exact
output. Otherwise it uses the unique full top element of the oracle's closed
output schema. No generator-supplied oracle summary can remove behavior.

`DFAMetricBoundCertificateV1` has exact keys:

```text
operation_kind
operation_spec_id
target_dfa_id
certificate_scope = TARGET_FULL_PATH | EMERGENCY_SUFFIX
emergency_suffix_universal_validation_certificate_id | null
metric_abstract_domain_descriptor
metric_abstract_domain_descriptor_id
ordered_required_emergency_suffix_records | null
covered_path_classes
maximum_symbol_steps
ordered_start_partition_records
ordered_abstract_node_records
ordered_abstract_edge_records
abstract_reachability_fixed_point_rounds
abstract_reachability_trace_root_sha256
bellman_iteration_count
path_length_ranking_verified = true
bellman_trace_root_sha256
ordered_root_metric_bound_records
dfa_metric_bound_certificate_id
```

Covered path classes are a nonempty strictly UTF-8-sorted subset of
`PathClassV1`. Target scope sets `maximum_symbol_steps` to the operation-global
literal embedded in its DFA rank descriptor. It never depends on an
operation-spec, later target budget, or admitted plan. Emergency scope sets it to
the maximum number of policy actions proved by the emergency universal-policy
rank. Let that scope-specific bound be `K`; `bellman_iteration_count=K`.
Target scope sets `path_length_ranking_verified=true` only after independently
checking every exact DFA AST obligation above. Emergency scope sets it true
only after the complete universal-policy rank/branch proof below passes.
This concrete well-founded proof—not stabilization of a deliberately
coarse abstract quotient—establishes that no covered legal path has more than
K symbols. Arithmetic overflow or inability to prove the relevant rank makes
the entire generated inventory invalid and leaves Raw V8 NO-GO; it cannot be
encoded as a cross-product or numeric bound rejection.
The embedded metric-domain descriptor and ID byte-equal the one required by
the universe manifest and emitted once in the inventory for this target DFA;
the bound generator cannot derive a different partition.
`TARGET_FULL_PATH` requires
`emergency_suffix_universal_validation_certificate_id=null` and
`ordered_required_emergency_suffix_records=null`.
`EMERGENCY_SUFFIX` requires a non-null array byte-equal the complete
manifest-required suffix declarations for this operation/spec after adding
no extra field, and requires a non-null universal-validation certificate ID.
No target certificate may carry emergency baggage, and no emergency
certificate may omit, add, or reorder a suffix row.
For emergency scope the resolved universal certificate has the same
operation/spec/DFA/domain and suffix bytes,
`maximum_symbol_steps=maximum_emergency_policy_steps`. Emergency seeds are
recomputed by `RULE_ABSTRACT_EXECUTION_TO_METRIC_ROOT_V1`:

1. for every suffix proof and every one of its
   `ordered_activation_image_execution_values`, take the abstract `state`
   member and selected required-row ordinal;
2. project every state path present in the metric-domain descriptor from its
   `RuleAbstractValueV1` interval/set/nullness/relation facts, using the
   descriptor's schema top for a metric path intentionally absent from the
   rule-relevant domain, then round/split numeric ranges by the exact metric
   threshold cells; every pre-filter cell tuple consumes one run-total
   abstract-cell-product candidate before an empty, inconsistent, or duplicate
   tuple can be removed;
3. apply the descriptor's frozen summary extractor abstract rule—execute a
   complete singleton, otherwise use its one closed output-schema top—and
   split every possible pending-effect class and ranking cell in declared
   order;
4. force `/execution_scope=EMERGENCY`, preserve the projected phase, and
   attach cursor
   `{required_record_ordinal=row_ordinal,next_symbol_position=1}` (also the
   sentinel for an epsilon row), plus the row's exact state/trigger/activation
   shape/finalization/context/path metadata; and
5. construct canonical start bodies, sort by complete canonical JSON bytes,
   and deduplicate before assigning root ordinals.

The verifier-generated projection map proves every universal activation image
maps to at least one retained seed and every retained seed has at least one
source image. The canonical deduplicated set of projected bodies byte-equals
the canonical deduplicated set of emergency start bodies; multiplicity is
deliberately not preserved after this lossy projection. A caller-selected,
merely may-reachable, missing, or extra emergency root is illegal.

One start record is exactly
`{root_ordinal, root_seed_abstract_state,
root_seed_abstract_state_id, fixed_point_abstract_state_id,
state_guard_rule_id|null,
emergency_trigger_class|null, trigger_guard_rule_id|null,
activation_evidence_shape_id|null,
finalization_evidence_shape_id|null,
finalization_context_guard_rule_id|null,
required_path_class|null,
required_emergency_suffix_record_ordinal|null}`. Target scope has one abstract
initial-state root and null emergency members. Emergency roots are the
canonical abstraction of every manifest-required state/trigger partition,
with non-null guards/trigger/context/finalizer bindings and ordinal. To assign
ordinals, construct every complete start-record body without `root_ordinal`
or the not-yet-known `fixed_point_abstract_state_id`,
sort those bodies by canonical JSON bytes, reject duplicates, and assign
contiguous one-based ordinals in that order. The seed body independently
recomputes its seed ID. During fixed point the verifier tracks the unique join
group containing each seed and updates its representative after every round;
the terminal representative is `fixed_point_abstract_state_id` and resolves
in the final node array. Final start records retain root-ordinal order; a
traversal-selected ordinal or unresolved/superseded Bellman root rejects.
They are soundly exhaustive over complete
`EmergencyActivationInputV1` values and their permitted post-suffix
finalization-shape classes; overlapping concrete partitions
reject.

One node is exactly:

```text
abstract_state_id
abstract_state
ordered_possibly_eligible_finalization_keys
```

Each finalization key is exactly
`{phase, terminal_trigger_class, finalization_evidence_shape_id,
result_guard_rule_id, path_class}` and sorts by that tuple.
For every node, `ordered_possibly_eligible_finalization_keys` is the exact
strictly sorted duplicate-free set independently recomputed as follows:
enumerate every resolved DFA finalization row in `covered_path_classes` whose
phase matches the node; restrict emergency scope to the selected suffix
cursor/row, activation shape, terminal class, context guard, and required path
class; abstract-evaluate the complete context guard and finalizer over the
frozen strict finalization-context schema/domain; and include the key iff the
result is true or unknown, never when definitely false. Omissions, extras, or
a caller-supplied context partition reject before Bellman initialization.
One edge is exactly:

```text
from_abstract_state_id
current_phase
execution_scope
symbol
eligibility_rule_id
guard_rule_id
state_update_rule_id
next_phase
emergency_suffix_cursor_before | null
emergency_suffix_cursor_after | null
ordered_semantic_relation_rule_ids
ordered_input_assumption_rule_ids
to_abstract_state_id
ordered_metric_upper_bound_records
abstract_edge_id
```

Before edge hashing, the resolved from-state must have
`phase=current_phase`, `/execution_scope=execution_scope`, and cursor equal
`emergency_suffix_cursor_before`; the resolved to-state must have
`phase=next_phase`, `/execution_scope=execution_scope`, and cursor equal
`emergency_suffix_cursor_after`. In target scope, both endpoint states'
embedded cursors and both edge cursor members are null; endpoint IDs and
states remain non-null. Any endpoint or duplicate-field mismatch rejects.

The semantic-relation list byte-equals the resolved
`TargetSymbolBoundV1.ordered_semantic_relation_rule_ids`; the assumption list
is the strictly sorted union of the exact assumptions frozen on the three
transition rules and those semantic relations. Neither list is
generator-selected. Abstract transfer is total but preserves only the small
termination-relevant numeric fragment frozen by the descriptor. If the
complete rule input—including state, native batch, sequence, oracle, and all
applicable terminal members—is singleton, execute every assumption,
relation, eligibility, guard, and update exactly. Otherwise use
`RANKING_INTERVAL_ABSTRACT_EVAL_V1`:

- `CONST` yields its singleton; a numeric `FIELD` yields the current ranking
  interval when it names a ranking state path and otherwise the exact closed-
  schema numeric interval; finite enum/Boolean fields yield their declared
  possible set;
- safe-uint `ADD`, `SUB`, `MIN`, and `MAX` yield the interval hull of every
  mathematically defined operand pair admitted by the operand intervals,
  clipped to the statically validated result schema; an empty set, a concrete
  overflow, or a concrete negative subtraction invalidates the certificate;
- `EQ`, `NE`, `LT`, `LE`, `GT`, and `GE` return definitely true when the
  relation holds for every represented operand pair, definitely false when it
  holds for none, and unknown otherwise;
- `NOT`, `AND`, and `OR` use strong Kleene three-valued truth in AST argument
  order; and
- every other operator, and any supported operator with an unsupported
  descendant, yields the unique top of its statically declared result type.

For an enabled nonsingleton `STATE_UPDATE`, the verifier follows each frozen
`update_expression_json_pointer` and applies that transformer to every
ranking counter. It uses the row's exact `next_phase` and cursor update.
It also fixes post `/execution_scope` to the row's unchanged exact
`execution_scope`. Every other non-ranking state field, including
payload/string/hash/ID/UTC facts, uses its declared schema top;
pending/parser/TLS summaries likewise use their
declared top unless their complete extractor input is singleton. The
abstractly transformed ranking interval is intersected with its declared
counter domain and then split by the canonical threshold cells. The claimed
per-transition relation is checked over the same enabled input abstraction.

Assumption, semantic-relation, eligibility, and guard ASTs are evaluated with
the same semantics: definitely false yields no edge; true or unknown yields a
sound edge. Unsupported payload predicates therefore add behavior but never
remove it, while counter guards and increments retain the facts needed to
close bounded send/read/poll loops. No string, array, hash/ID, UTC, or
cross-field relational refinement is inferred beyond a singleton exact
execution. Every possible concrete post-state must be represented by
`to_abstract_state_id`; an unknown fact can add paths or widen metrics but can
never remove a concrete path.

Before join, each nonsingleton raw successor is expanded canonically into the
Cartesian product of every possible pending-effect class and every
intersected threshold cell of each ranking counter, in the exact declared
field/class order. Every tuple consumes the run-total abstract-cell-product
candidate budget before its cells are inspected. Ranking intervals are
clipped to the selected cells; empty products are discarded; results are
sorted by complete canonical bytes and deduplicated. Parser/TLS summaries may
remain their schema top, but no multi-class pending-effect value or interval
spanning two ranking cells may inhabit one `AbstractStateV1`. In each round,
the raw-successor cap is checked for each surviving Cartesian-expanded
occurrence before deduplication, and that same occurrence consumes the
run-total raw-successor budget; the state and edge caps are checked on the
final deduplicated arrays after join/rederivation, while every retained table
node consumes the run-total state-occurrence budget. Exceeding
`maximum_total_abstract_cell_product_candidates`,
`maximum_raw_successors_per_round`,
`maximum_total_raw_successor_occurrences`,
`maximum_total_abstract_state_occurrences`,
`maximum_abstract_state_count`, or `maximum_abstract_edge_count` produces no
certificate rather than truncation, sampling, spilling into an
implementation-dependent representation, or continuing under a different
limit.

Each edge metric record is exactly:

```text
metric_member
upper_bound_value
bound_kind = CONSERVATIVE_GLOBAL_SYMBOL_UPPER_BOUND
```

`ordered_metric_upper_bound_records` contains exactly the ten primitive
metrics declared by the abstract-domain descriptor, once each, strictly
sorted by `metric_member`; omission, duplication, reordering, or an extra
metric rejects.
The value is not solved afresh under an implementation-selected correlated
schema optimizer. It byte-equals the resolved global `TargetSymbolBoundV1`
for this literal symbol under the fixed mapping:

```text
transaction_count = 1
projection_entry_count = projection_entry_count
projection_entry_array_element_score =
  projection_entry_element_octets + projection_entry_count
maximum_one_record_body_octets = maximum_one_record_body_octets
aggregate_record_body_octets = aggregate_record_body_octets
operation_batch_count = 1
operation_batch_array_element_score =
  operation_batch_metadata_object_octets + 1
maximum_one_operation_batch_result_blob_octets =
  operation_batch_result_blob_octets
actor_event_count = actor_event_count
raw_ingress_commit_count = raw_ingress_commit_count
```

Safe-integer overflow rejects. Every edge is deliberately labelled
conservative even when a separate diagnostic materialization attains the
global symbol bound,
because one global witness need not be reachable from every abstract
from-state. Root metrics likewise remain conservative regardless of
diagnostic materializations. This deliberately trades
precision for reproducibility and soundness. Any future state-conditioned
tightening requires a separately frozen solver/objective/certificate protocol
and cannot affect Raw V8 Stage-1 admission.
`abstract_edge_id` is `semantic_id()` under the literal abstract-edge domain
over every preceding edge member.

Starting from the ordered roots, the verifier runs canonical synchronous
fixed-point rounds; no mutable worklist schedule is permitted:

1. round zero is the strictly ID-sorted unique root-seed node set plus the
   root-ordinal-to-current-representative map;
2. to compute `N_(r+1)`, freeze the complete `N_r` node array and enumerate
   every `(abstract_state_id, execution_scope, symbol, guard_rule_id)` from
   that snapshot in unsigned-byte lexicographic order, computing all sound
   raw successors;
3. union those raw successors with `N_r`, group by the exact
   `(phase, execution_scope, pending_effect_class, ranking_counter_cell_key,
   emergency_suffix_cursor)` join key, and compute each group once from the
   canonically sorted complete member set using the frozen hull/intersection
   join;
4. apply `CANONICAL_THRESHOLD_ROUNDING_V1` once to every joined group, mint
   the `N_(r+1)` canonical state IDs, discard superseded IDs, and update each
   root-map entry to the unique new group containing its prior
   representative; and
5. stop at the first positive round `q` for which the complete `N_q` node
   array and root map byte-equal `N_(q-1)` and its map.

Every changed join key is automatically reconsidered in the next full round;
there is no edge invalidation/requeue choice. The manifest freezes
`maximum_abstract_fixed_point_rounds=1,000,000`; nonconvergence within that
limit produces no certificate.

Only after node convergence, derive the final edge set `E*` from `N_q`.
Enumerate every enabled transition from every final node in the same order,
compute and cell-split its raw successors, and map each successor to the
unique final join-key state that contains it under the exact
interval/set/nullness/must-fact partial order. Fixed-point closure requires
that state to exist; missing or multiple containing endpoints reject. Create
the complete exact edge for each mapping, then canonical-sort and deduplicate.
The local and run-total raw-successor caps are checked again on this final
enumeration, every final source-node visit consumes the run-total state budget,
and the edge cap is checked on the resulting `E*`; intermediate rounds never
claim an edge whose destination is not yet in their node set. Every completed
transient and final table also consumes the cumulative canonical-table-byte
budget. The supplied round count/root and final strictly ID-sorted
duplicate-free `N_q`/`E*` arrays must byte-equal independent recomputation.
No caller-chosen initialization, round boundary, partitioning, widening
schedule, endpoint remap, or conservative value is permitted.

Trace hashing is exact. For reachability round `r`, the table hash is:

```text
H_reach_table(r) =
  sha256_digest({
    "domain": "RiskYieldMMA2MAbstractReachabilityRoundTableV1V4_9F_RawV8",
    "round": r,
    "ordered_abstract_state_ids": exact sorted IDs after the round,
    "ordered_root_representative_records":
      exact root-ordinal/current-state-ID records after the round
  })

R_0 =
  sha256_digest({
    "domain": "RiskYieldMMA2MAbstractReachabilityTraceEmptyV1V4_9F_RawV8",
    "metric_abstract_domain_descriptor_id": exact ID
  })

R_r =
  sha256_digest({
    "domain": "RiskYieldMMA2MAbstractReachabilityTraceStepV1V4_9F_RawV8",
    "previous_root_sha256": R_(r-1),
    "round": r,
    "round_table_sha256": H_reach_table(r)
  })

R_final =
  sha256_digest({
    "domain": "RiskYieldMMA2MAbstractReachabilityFinalV1V4_9F_RawV8",
    "node_round_trace_root_sha256": R_q,
    "ordered_final_abstract_state_ids": exact sorted N_q IDs,
    "ordered_final_abstract_edge_ids": exact sorted E* IDs,
    "ordered_final_root_representative_records":
      exact root-ordinal/final-state-ID records
  })
```

Rounds start at one and are contiguous; round `q` is the first unchanged
node/root-map round. The supplied reachability trace root is `R_final`, not an
intermediate edge table hash.

An emergency cursor is exactly
`{required_record_ordinal, next_symbol_position}`. For a suffix with `L`
ordered symbols, `next_symbol_position` is in `1..L+1`; `L+1` is the terminal
sentinel. A nonterminal edge consumes exactly the symbol at the current
one-based position and advances by exactly one. Only the sentinel may evaluate
the suffix row's post-suffix context guard and matching finalizer/path class
using the actual complete `FinalizationContextV1`. An epsilon suffix starts at
the sentinel and emits no edge. Target scope requires every cursor null.

Primitive metrics are transaction count, projection-entry count, entry-array
score (`entry object octets + entry count`), maximum one record body,
aggregate record bodies, operation-batch count, batch-array score
(`metadata object octets + 1`), maximum one result blob, actor-event count,
and RAW-ingress count. For a target-array root, empty framing is two bytes and
nonempty framing is `1 + score`. For an emergency optional segment, empty is
zero and nonempty is `1 + score`.

Each root metric record is exactly:

```text
metric_member
accumulator =
  SUM | MAX | TARGET_ARRAY_FRAMING |
  OPTIONAL_ARRAY_SEGMENT_FRAMING
upper_bound_value
bound_kind = CONSERVATIVE_ABSTRACT_PATH_UPPER_BOUND
```

`ordered_root_metric_bound_records` contains exactly the same ten metrics,
once each and strictly sorted. Its `accumulator` byte-equals the resolved
primitive metric descriptor's target or emergency accumulator according to
certificate scope. `TARGET_ARRAY_FRAMING` performs the specified empty-two/
nonempty-one-plus-score transformation after the deterministic SUM;
`OPTIONAL_ARRAY_SEGMENT_FRAMING` performs empty-zero/nonempty-one-plus-score.
The canonical label is always conservative; no concrete maximizing-path ID
is an identity member. A caller cannot relabel SUM as MAX, claim concrete
attainment, or omit a costly metric.

For every node/metric, Bellman iteration is deterministic. A
`BellmanOptionKeyV1` is the following exact tagged union:

```text
FINALIZATION:
  {option_kind = FINALIZATION, finalization_key}

EDGE:
  {option_kind = EDGE, abstract_edge_id}
```

`finalization_key` is one complete key from the node's frozen eligible set.
An edge option resolves the one complete edge. Option keys compare by the
unsigned-byte lexicographic order of their canonical JSON bytes. Define the
candidate multiset and recurrence exactly:

```text
C_0(node, metric) =
  one (score=0, FINALIZATION key) candidate for every possibly eligible
  covered finalization key

C_k(node, SUM metric) =
  C_0(node, metric)
  union one (score=edge.weight + V_(k-1)(edge.to), EDGE key) candidate
        for every outgoing edge whose successor value is reachable

C_k(node, MAX metric) =
  C_0(node, metric)
  union one (score=max(edge.weight, V_(k-1)(edge.to)), EDGE key) candidate
        for every outgoing edge whose successor value is reachable

V_k(node, metric) =
  unreachable, when C_k is empty;
  otherwise the greatest candidate score, selecting the byte-smallest
  option key among candidates with that score
```

An edge whose successor is unreachable contributes no candidate under either
accumulator; its weight alone can never make a dead end reachable. Every
addition/max uses safe unsigned integers and overflow produces no certificate.
Before any finalization or edge is tested for membership in `C_k`, it consumes
one run-total Bellman-option candidate in the exact order defined with the
aggregate caps; an ineligible, unreachable, overflowing, losing, or
tie-broken option still counts.
Array framing is applied once to the final SUM score using the target or
emergency convention. The verifier streams every iteration's sorted table
hash into `bellman_trace_root_sha256`; supplied roots/values must equal
recomputation through exactly
`bellman_iteration_count`. Root bounds are the componentwise maximum over
the start records' `fixed_point_abstract_state_id` values. Root records remain
`CONSERVATIVE_ABSTRACT_PATH_UPPER_BOUND` even when a separate diagnostic path
attains the value; diagnostics never change the deterministic numeric bound
or canonical identity.

Each value record is exactly
`{abstract_state_id, metric_member, reachable, value|null,
selected_option_key|null}`. There is exactly one record for every
node/primitive-metric pair, sorted by
`(abstract_state_id, metric_member)`. `reachable=false` is the sole encoding
of minus-infinity and requires both nullable members null. `reachable=true`
requires a safe-uint value and a non-null valid option key that realizes that
value under the recurrence; no other nullability combination is legal.
Iteration hashes and the trace are:

```text
H_bellman_table(k) =
  sha256_digest({
    "domain": "RiskYieldMMA2MBellmanValueTableV1V4_9F_RawV8",
    "ordered_value_records": exact complete V_k table
  })

Q_minus_1 =
  sha256_digest({
    "domain": "RiskYieldMMA2MBellmanTraceEmptyV1V4_9F_RawV8",
    "certificate_scope": exact scope,
    "metric_abstract_domain_descriptor_id": exact ID,
    "maximum_symbol_steps": K
  })

Q_k =
  sha256_digest({
    "domain": "RiskYieldMMA2MBellmanTraceStepV1V4_9F_RawV8",
    "previous_root_sha256": Q_(k-1),
    "iteration": k,
    "iteration_table_sha256": H_bellman_table(k)
  })
```

The trace includes contiguous tables `V_0..V_K` and ends at `Q_K`;
`bellman_iteration_count=K` and `bellman_trace_root_sha256=Q_K`. The
independently verified concrete path-length/policy rank makes this finite
horizon complete even when the conservative quotient contains a spurious
cycle. No K+1 stabilization claim is made. Every preimage has the exact keys
shown and no other member.

This required Tier-1 analysis is conservative and reproducible. Optional
Tier-2 CEGAR is diagnostic-only in Raw V8 Stage 1: it may suggest a tighter
bound or produce a legal counterexample, but it is outside the canonical
inventory, cannot change a disposition, cannot mint an admitted plan, and
cannot affect any identity. Admitting a coordinate through refinement
requires a later protocol version with a frozen refinement domain,
certificate schema, resolver/inventory array, and independent reproduction.
Timeout/unknown remains rejected.
Exhaustive concrete-state DP and global least-legal-frontier proofs are
postponed Tier 3 and are not Stage-1 acceptance dependencies.
Stage-1 acceptance additionally requires the one frozen
`RequiredOperationViabilityRecordV1` for each of the four operations to replay
exactly, its named coordinate to be admitted by Tier 1, and its plus-one
boundary check to fail eligibility exactly as specified above; optional CEGAR
cannot be the only route to a usable plan.

Each `WeightedTargetDFABoundProfileV1` identity payload is:

```text
operation_kind
operation_spec_id
target_dfa_id
covered_path_classes
dfa_metric_bound_certificate_id
ordered_metric_bound_records
target_transaction_count
target_projection_entry_count
target_projection_entry_canonical_bytes
maximum_one_target_record_body_canonical_bytes
aggregate_target_record_body_canonical_bytes
target_operation_batch_count
maximum_one_operation_batch_result_blob_bytes
aggregate_operation_batch_metadata_bytes
target_actor_event_count
target_raw_ingress_commit_count
emergency_suffix_profile_id
```

The profile ID is appended as
`weighted_dfa_bound_profile_id=semantic_id()` under the literal weighted
profile domain. Covered classes are exactly
`[CANCELLED_ADVERSE, INTERRUPTED_ADVERSE, RAISED_ADVERSE, RECOVERY,
RETURN_INVALID_ADVERSE, RETURN_SUCCESS]` in UTF-8 order. Every duplicated
metric equals its componentwise root record in the resolved certificate.
That certificate has the same `operation_kind`, `operation_spec_id`, and
`target_dfa_id`, sets `certificate_scope=TARGET_FULL_PATH`, and has
`covered_path_classes` byte-equal the six classes above. Substitution of a
cross-operation, cross-spec, emergency-scope, or under-covered certificate
rejects even when its numeric metric records happen to match.
The resolved emergency profile's universal certificate has
`target_full_path_dfa_metric_bound_certificate_id` equal this same certificate
ID.
The profile therefore dominates every reachable return, adverse, and
recovery path even when no single path maximizes all metrics.

`EmergencySuffixProfileV1` has exact keys:

```text
operation_kind
operation_spec_id
target_dfa_id
ordered_state_suffix_records
emergency_suffix_universal_validation_certificate_id
dfa_metric_bound_certificate_id
ordered_metric_bound_records
maximum_emergency_transaction_count
maximum_emergency_operation_batch_count
maximum_emergency_receipt_count
maximum_emergency_entry_canonical_bytes
maximum_emergency_one_record_body_canonical_bytes
maximum_emergency_aggregate_record_body_canonical_bytes
maximum_emergency_one_operation_batch_result_blob_bytes
maximum_emergency_operation_batch_metadata_bytes
maximum_emergency_actor_event_count
maximum_emergency_raw_ingress_commit_count
emergency_suffix_profile_id
```

Each suffix record has exactly:

```text
phase
state_guard_rule_id
emergency_trigger_class
activation_evidence_shape_id
trigger_guard_rule_id
activation_state_update_rule_id
initial_suffix_execution_context_materializer_rule_id
ordered_symbols
ordered_symbol_materializer_rule_ids
ordered_suffix_execution_context_update_rule_ids
finalization_context_materializer_rule_id
terminal_kind | null
cause_code | null
anchor_role | null
terminal_trigger_class
finalization_evidence_shape_id
finalization_context_guard_rule_id
required_path_class
```

`ordered_state_suffix_records` is duplicate-free and strictly increasing by
the canonical bytes of the complete record above. It byte-equals the required
manifest declarations after removing only their duplicated
`operation_kind`; no emitter-selected ordering or extra row is legal.

All three guard IDs resolve to embedded pure Boolean rules. The state and
trigger guards select against the immutable pre-suffix state and exact
`EmergencyActivationInputV1`. The context guard evaluates against the
complete post-suffix state, the byte-identical activation input, and the
newly supplied complete
`FinalizationContextV1`; it validates the suffix-record terminal class,
evidence shape/body/hash, and
every operation-specific durable anchor rather than constructing an object.
Across every bounded pre-admission executable selection-domain
state/activation pair, records
for that phase are exhaustive and mutually exclusive. `ordered_symbols` is
an exact legal DFA path from every pair selected by those rules to the
matching adverse or recovery finalization guard selected by the trigger
class. The context guard and exactly one matching finalizer guard must be
true over the same post-state and actual context. Epsilon is the empty array and is legal only when the current state
already satisfies that matching guard. The canonical universal-validation
certificate proves these universal claims; a concrete example path is neither
necessary nor sufficient. The embedded
metric-bound certificate covers every bounded reachable
state/trigger-class suffix partition and its componentwise root records
equal all duplicated emergency maxima. The profile ID is
`semantic_id()` under the literal emergency domain over all preceding
members. Commit uncertainty and lost authority are recovery triggers and
therefore have empty target suffixes.

The resolved emergency certificate has the same `operation_kind`,
`operation_spec_id`, and `target_dfa_id`, sets
`certificate_scope=EMERGENCY_SUFFIX`, and byte-equals the complete required
suffix declarations.
Its `covered_path_classes` is exactly the strictly UTF-8-sorted unique set of
`required_path_class` values in those rows. Its root metric records byte-equal
the profile metric records and duplicated maxima. The enclosing weighted
profile's `emergency_suffix_profile_id` resolves this same operation/spec/DFA
triple; cross-spec or partial-suffix substitution rejects.

`EmergencySuffixUniversalValidationCertificateV1` has exact keys:

```text
operation_kind
operation_spec_id
target_dfa_id
target_full_path_dfa_metric_bound_certificate_id
metric_abstract_domain_descriptor_id
ordered_required_emergency_suffix_records
abstract_partition_rule =
  RULE_RELEVANT_ENDPOINTS_RELATIONS_AND_SCHEMA_TOP_V1
symbolic_proof_rule =
  RAW_V8_PURE_RULE_SUBSTITUTION_INTERVAL_RELATION_V1
ordered_selection_partition_records
selection_exhaustive_result = DEFINITELY_TRUE
selection_pairwise_disjoint_result = DEFINITELY_TRUE
ordered_suffix_universal_proof_records
maximum_emergency_policy_steps
universal_validation_trace_root_sha256
emergency_suffix_universal_validation_certificate_id
```

The suffix array byte-equals the operation's complete manifest declarations.
`maximum_emergency_policy_steps` is mechanically
`max(len(ordered_symbols), default=0)`; for a selected row of length `L`, the
rank before one-based position `p` is exactly `L-p+1` and the sentinel rank is
zero. No solver-selected ranking function exists.

`RuleAbstractValueV1` is the exact nonempty-set representation:

```text
value_schema_sha256
ordered_safe_uint_interval_records
ordered_finite_value_set_records
ordered_length_interval_records
ordered_array_item_presence_records
ordered_nullness_records
ordered_must_equal_path_partitions
ordered_must_not_equal_path_pairs
ordered_timestamp_relation_records
```

`value_schema_sha256` is lowercase raw
`sha256(canonical_json_bytes(complete_resolved_RAW_V8_CLOSED_SCHEMA_V1_schema))`.
The complete schema is fixed by the serialized value's parent location:
selection values use the exact
`EmergencySuffixSelectionInputV1={pre_state,emergency_activation}` schema;
execution values use the exact four-field execution-value schema; native
batch/context images use the referenced materializer's complete
`result_schema`; and a guard/update abstract input uses that resolved
`PureRuleDescriptorV1.input_schema`. A projected state subtree uses the exact
state-schema node at that canonical parent path, never the enclosing schema or
an implementation-built subset. The verifier recomputes the hash before
reading any abstract records. Union, intersection, comparison, or image
construction between unequal schema hashes rejects.

Field paths are canonical RFC-6901 paths from the stated value root. The
interval, finite-set, nullness, identity, and timestamp records use the exact
schemas, orientation, sort, and consistency rules of `AbstractStateV1` and
cover every rule-relevant leaf exactly once. Arrays of abstract values are
strictly increasing by canonical bytes and duplicate-free. Intersection and
cell union are the exact componentwise finite operations; an inconsistent
interval/set/nullness/equality/time conjunction is the unique empty result
and is never serialized as a value.

For every rule-relevant bounded array at path `a` with schema maximum `M`,
the presence array contains exactly one record
`{array_field_path=a,item_index=i,possible_absent,possible_present}` for each
zero-based `i` in `0..M-1`, ordered by `(array_field_path,item_index)`.
At least one Boolean is true. Presence is prefix-closed: definite presence at
`i` implies definite presence below `i`, and possible presence at `i`
forbids definite absence below `i`. The array's length interval is exactly
consistent with these records; a fixed length makes lower slots definitely
present and the rest definitely absent. Every rule-relevant item leaf is
unrolled under the canonical pointer `a/<i>/...` and appears in the
corresponding interval/set/nullness/relation domains exactly when slot `i`
can be present.

Abstract array operators are finite and fixed. `ARRAY` constructs its exact
length, slot presences, and item values. `ARRAY_AT(a,j)` unions the item value
at every index represented by `j` and is definitely total only when every
represented array has every represented index present; otherwise a required
totality claim fails. `ARRAY_APPEND` enumerates each input length admitted by
the length cells, copies prior slots, writes the appended value at that
length, unions the resulting slot/value records, and adds one to length.
`ARRAY_CONCAT` does the same canonical enumeration over every admitted
left/right length pair and shifts right slots by the left length. Operators
reject if any result exceeds the frozen schema maximum. Enumeration order is
array path, input-length tuple, then slot index; results are cell-normalized,
sorted, and deduplicated. These rules also govern `ARRAY_CONTAINS`,
`ARRAY_EQ`, and `ALL_UNIQUE` through the exact possible present slots; an
unsupported correlation yields `UNKNOWN`, never a false must claim.

Selection partitions are derived only over the complete closed
`EmergencySuffixSelectionInputV1={pre_state, emergency_activation}`. The
resolved target-full-path certificate has the same operation/spec/DFA/domain,
sets `certificate_scope=TARGET_FULL_PATH`, and is already independent of this
universal certificate. Its covered classes are exactly the six-class
all-path set required by the weighted profile, and the inventory permits
exactly one such target certificate for this operation-spec/DFA tuple. The
pre-state domain is the nonempty conservative set
of all its final fixed-point normal-scope abstract nodes; there is no
generator-selected “stable” subset. The activation domain is the
complete union of every operation-valid manifest strict activation shape and
body schema. The selection domain is their Cartesian product intersected with
all activation-shape anchor relations, including byte-equality between the
sealed sequence context's two relative counts and
`pre_state.relative_sequence_state`; mismatched impossible pairs are not
members. Every pre-state/activation/cell tuple consumes one run-total
abstract-cell-product candidate before relation, emptiness, inconsistency, or
deduplication filtering. For each activation, independently set
`maximum_remaining_suffix_receipt_count =
maximum_emergency_receipt_count + 2`, where the two fixed receipts are
terminal and closure. Both emergency maxima are mechanically recomputed from
the manifest suffix rows and resolved conservative symbol bounds (and are
only later duplicated by the emergency profile); they are not read from a
later profile. Use the two reservation scalars carried by the activation and
require their exact pre-universal algebra above. The domain requires

```text
next_receipt_sequence
  + maximum_remaining_suffix_receipt_count - 1
  <= min(9007199254740991, receipt_reservation_end_sequence)
```

and, when `maximum_emergency_operation_batch_count>0`, requires

```text
next_operation_batch_ordinal
  + maximum_emergency_operation_batch_count - 1
  <= 9007199254740991
```

with safe-uint arithmetic; the zero-batch case performs no subtract-one
expression. The same two relations are explicit assumptions for every suffix
materializer/context-update totality proof. A stale ledger anchor, unequal
runtime plan/profile chain, or failed relation is outside executable
activation and seals for recovery; no downstream admitted-plan identity is
resolved while constructing or verifying this certificate.
Neither
`finalization_context`, future suffix result, nor generated profile is a
selection input. To evaluate a selection guard, the verifier lifts the pair
into the shared guard-input schema with `state=pre_state`,
`trigger=emergency_activation.active_input.emergency_trigger_class`,
`emergency_activation` byte-equal, and exact `NOT_APPLICABLE`/null-empty
values for symbol and finalization context. Oracle facts are independently
recomputed from permitted state/activation fields. Selection guard ASTs and
assumptions are statically forbidden to read sequence context, symbol/result,
finalization context, or another future field. The derivation uses every
schema endpoint, enum/tag value,
rule integer/length constant and clipped plus/minus one, nullable case,
identity relation, and timestamp relation referenced by selection rules.
Unreferenced payload bytes/strings remain schema top.

The metric-node-to-rule-domain lift is
`METRIC_ABSTRACT_STATE_TO_RULE_ABSTRACT_VALUE_V1` and is verifier-owned. For
each final target node it:

1. copies exact phase/scope finite values and intersects every shared
   counter, enum, length, and nullness path with the node's interval/set;
2. copies must-equality, must-inequality, and timestamp relations only when
   both canonical paths occur in the rule-input state subtree;
3. assigns the declared closed-schema top to every rule-relevant raw-state
   leaf absent from the metric domain, including payload/ID/time leaves for
   which no must fact was copied;
4. deliberately discards parser/TLS summary values as inverse constraints on
   raw state—there is no invented inverse extractor—and recomputes any
   selection-rule oracle facts from the lifted state using the ordinary
   singleton-else-output-top rule; and
5. refines the result by every rule-domain endpoint/constant cell, enumerates
   in metric-node ID then canonical cell-product order, increments the
   run-total abstract-cell-product counter before inspecting every tuple,
   removes empty cells, and canonical-sort/deduplicates the resulting
   `RuleAbstractValueV1` set.

The union of those lifted values, not an implementation-selected inverse, is
the exact pre-state input to selection partitioning. This lift is
conservative: discarding a summary constraint may add states and make a must
proof fail, but can never remove a concrete target state.

One selection record is exactly
`{partition_ordinal, selection_abstract_value,
selected_suffix_record_ordinal, selected_state_guard_result,
selected_trigger_guard_result, ordered_other_row_result_records}`.
Other-row records are exactly
`{required_suffix_record_ordinal, state_guard_result,
trigger_guard_result, combined_result}`. Records sort by canonical selection
value and receive contiguous one-based ordinals. The selected results are
`DEFINITELY_TRUE`; every other combined result is `DEFINITELY_FALSE`. Exact
symbolic union equals the complete selection domain defined immediately above
and every
pairwise symbolic intersection is empty. `UNKNOWN` proves none of selection,
coverage, or disjointness.

One suffix proof is exactly:

```text
required_suffix_record_ordinal
ordered_start_partition_ordinals
activation_state_update_rule_id
activation_update_result = DEFINITELY_TOTAL
initial_suffix_execution_context_materializer_rule_id
initial_execution_context_result = DEFINITELY_TOTAL
ordered_activation_image_execution_values
ordered_step_obligation_records
ordered_terminal_obligation_records
```

One step obligation is exactly:

```text
symbol_position
rank_before
symbol
symbol_materializer_rule_id
suffix_execution_context_update_rule_id
ordered_pre_abstract_execution_values
materializer_result = DEFINITELY_TOTAL
ordered_materialized_native_batch_abstract_values
ordered_transition_branch_obligation_records
execution_context_update_result = DEFINITELY_TOTAL
ordered_post_abstract_execution_values
rank_after
```

An execution value has exact schema
`{state, emergency_activation, sequence_context,
ordered_prior_suffix_results}`. The activation image derives all four members
without future data and preserves the immutable activation byte-for-byte
across every transition image; its exact value set
equals step one's pre-value set, or the terminal pre-value set for epsilon.
Every later step's pre-value set byte-equals the preceding step's post-value
set. The materializer result covers only complete native batches for the
declared symbol.

One transition-branch obligation is exactly:

```text
current_phase
execution_scope = EMERGENCY
eligibility_rule_id
guard_rule_id
state_update_rule_id
next_phase
ordered_pre_execution_subset
ordered_native_batch_subset
assumptions_result = DEFINITELY_TRUE
semantic_relations_result = DEFINITELY_TRUE
eligibility_result = DEFINITELY_TRUE
selected_guard_result = DEFINITELY_TRUE
ordered_other_guard_result_records
ordered_post_execution_image
```

The row tuple resolves exactly one DFA transition. Other-guard records cover
every other row in the same `(phase, scope, symbol)` group. One is exactly
`{eligibility_rule_id,guard_rule_id,state_update_rule_id,next_phase,
result=DEFINITELY_FALSE}` and records sort by the complete transition tail.
Branch pre/batch products are pairwise disjoint and their
union equals the complete step pre/materializer image; branch post images
union exactly to the step post set. Every post-state preserves emergency scope
and the normal target-step counter, and its sequence context/ordered prior
results are the exact transition/append image. For every pre value,
the sequence-context relative counts equal
`state.relative_sequence_state`; for every post value, the
execution-context update's sequence context and branch transition append
result are byte-equal, and their two relative counts equal
`post_state.relative_sequence_state`.
`rank_after=rank_before-1`, cursor positions advance exactly, and the
canonical successor set is the sound symbolic image of every pre-state/batch
combination.

One terminal obligation is exactly:

```text
terminal_obligation_ordinal
ordered_pre_abstract_execution_values
finalization_context_materializer_rule_id
context_materializer_result = DEFINITELY_TOTAL
ordered_materialized_finalization_context_values
finalization_context_guard_rule_id
context_guard_result = DEFINITELY_TRUE
selected_finalizer_key
selected_finalizer_result = DEFINITELY_TRUE
ordered_other_finalizer_result_records
```

The activation and initial-context IDs byte-equal the suffix row. At position
`p`, the native materializer and execution-context update IDs byte-equal
their position-`p` row arrays. The activation state-update image and initial-
context materializer image are combined over the same selection value; this
joint image is exactly `ordered_activation_image_execution_values`.
The context update's image—not a prose append assumption—provides the
post-step sequence/prior-result members.

The materializer ID byte-equals the suffix row and its exact output image is
the listed complete strict contexts. Other-finalizer records contain every
other resolved finalizer for the reachable phase/trigger. One is exactly
`{phase,terminal_trigger_class,finalization_evidence_shape_id,path_class,
result_guard_rule_id,result=DEFINITELY_FALSE}` and records sort by the
complete finalizer key. Terminal pre-value arrays partition exactly the final step
post set (or epsilon activation image), with no omission or extra. Malformed
external contexts are outside the materializer image and cannot select a
suffix. Epsilon rows have no step obligations and prove these terminal
obligations directly.

Every selection ordinal occurs once in exactly one suffix proof; each proof's
start ordinal set is exactly the set selecting its row. For row length `L`,
step positions are exactly `1..L`, ranks are exactly `L..1` followed by zero,
and all arrays above are duplicate-free. Suffix proofs sort by required row
ordinal, start/position/terminal ordinals increase numerically, steps sort by
symbol position, transition branches by the full transition tuple, and every
remaining heterogeneous value/record array sorts by canonical JSON bytes.
These set and chain
equalities are independently recomputed before any logical claim is checked.

The symbolic proof trace is verifier-generated, not supplied or identity-
selected. The closed inference tags are
`SCHEMA_DOMAIN, CONST, FIELD, AST_SUBSTITUTION, INTERVAL_ARITHMETIC,
FINITE_SET_RELATION, IDENTITY_RELATION, TIMESTAMP_RELATION,
STRONG_KLEENE_BOOLEAN, OBJECT_POINTWISE, UNION_COVERAGE,
INTERSECTION_EMPTY, AND TOTAL_FUNCTION`. Their subjects are fixed by the
claim's canonical JSON locator, resolved rule/AST pointer, exact abstract-
value collection hash, field paths, and (for coverage) domain/partition
collection hashes. They compute the tagged conclusions
`TRUTH`, `ABSTRACT_VALUE`, `ABSTRACT_VALUE_SET`, `COVERAGE`, `DISJOINT`, and
`TOTAL_FUNCTION` under the exact abstract operations above.

Trace construction is canonical:

1. enumerate every serialized truth/totality/image claim plus the checker
   invariants `SELECTION_COVERAGE`, `SELECTION_DISJOINTNESS`,
   `START_SET_EQUALITY`, `ACTIVATION_IMAGE_EQUALITY`,
   `STEP_CHAIN_EQUALITY`, `BRANCH_COVERAGE`, `BRANCH_DISJOINTNESS`,
   `TERMINAL_COVERAGE`, and `RANK_SEQUENCE`, sorted by locator;
2. recursively expand the unique inference dictated by the resolved AST node
   or set operation; there is no alternative inference choice;
3. normalize AST substitution capture-free, order operands/premises by
   canonical subject bytes, and maximally share byte-identical
   `{inference_tag, subject, ordered_premise_keys, conclusion}` nodes;
4. topologically sort nodes by `(dependency_depth, canonical node bytes)` and
   assign contiguous one-based ordinals; and
5. require every derived truth/totality literal and value set to byte-equal
   its serialized certificate field. Any `UNKNOWN` required as true/false,
   unsupported AST operation, unequal image, missing/extra partition,
   arithmetic failure, or resource-cap overflow leaves Raw V8 NO-GO.

The standard strong-Kleene tables, interval/finite-set relations,
identity/timestamp must facts, pointwise object construction, normalized cell
union/intersection, and static partial-operator totality are exactly those
already frozen in this correction. Because the trace is recomputed from
claims and not serialized, alternative DAG decomposition cannot change a
certificate identity.

The trace root is `sha256_digest()` of
`{"domain":"RiskYieldMMA2MEmergencySuffixUniversalValidationTraceV1V4_9F_RawV8",
"certificate_body": exact every preceding certificate member,
"ordered_recomputed_proof_steps": exact canonical trace above}`. The
certificate ID is `semantic_id()` under its literal domain over every
preceding member. The profile resolves exactly one such certificate with the
same operation/spec/DFA/domain/suffix bytes. This must/universal proof is
separate from the may/upper-bound DFA metric certificate; a may edge or
`UNKNOWN` result never proves emergency executability.

For each suffix record, transaction/batch count is
`len(ordered_symbols)`, receipt/entry/actor/RAW counts and record-body bytes
are bounded by the resolved symbol records, and framed entry/batch bytes use
the Section 5 four-case/comma rules. Every `maximum_emergency_*` member is
the conservative certified componentwise upper bound over all suffix records.
It is never relabelled exact by a diagnostic path. An epsilon-only profile has
all-zero maxima; unrelated cross-operation constants are forbidden.

### 12.4 Ceilings, budgets, plans, and witnesses

`HardCeilingRecordV1` has exact keys and values:

```text
maximum_target_transaction_count = 65,536
maximum_target_projection_entry_count = 65,536
maximum_target_projection_entry_canonical_bytes = 50,331,648
maximum_one_target_record_body_canonical_bytes = 1,048,576
maximum_aggregate_target_record_body_canonical_bytes = 50,331,648
maximum_target_operation_batch_count = 65,536
maximum_one_operation_batch_result_blob_bytes = 65,536
maximum_aggregate_operation_batch_metadata_bytes = 8,388,608
maximum_target_actor_event_count = 65,536
maximum_target_raw_ingress_commit_count = 65,536
maximum_retained_dependency_canonical_bytes = 8,388,608
maximum_operation_result_evidence_canonical_bytes = 524,288
maximum_candidate_canonical_bytes = 4,194,304
maximum_attempt_canonical_bytes = 1,048,576
maximum_terminal_canonical_bytes = 1,048,576
maximum_closure_canonical_bytes = 25,165,824
maximum_outer_prefix_shell_canonical_bytes = 10,485,760
maximum_closed_prefix_canonical_bytes = 100,663,296
maximum_sample_canonical_bytes = 134,217,728
hard_ceiling_record_id
```

The ID is `semantic_id()` under the literal hard-ceiling domain over all
preceding members. A `TargetSpanBudgetV1` is exactly the Section 5 record,
including this hard-ceiling ID, and its identity is the Section 5
`target_span_budget_id`. It is a certified proposed bound and remains
representable even when one or more combined normal-plus-reserved-emergency
metrics exceed a hard ceiling. Every combined value is recomputed by the
Section 5 equations without clipping. Only an admitted disposition requires
every applicable value to be no greater than its ceiling; an over-ceiling
budget can occur only in a bound-rejected chain and can never be attached to
a candidate or attempt.

The universe manifest contains exactly one `CeilingDescriptorV1` for every
numeric hard-ceiling member:

```text
priority
ceiling_member
metric_member
metric_kind = COUNT | BYTE
ceiling_value
rejection_code = CONSERVATIVE_BOUND_EXCEEDS_CEILING
```

Priorities are contiguous from one and descriptors are strictly sorted by
priority; every rejection code is the literal above and values byte-equal the hard-ceiling record, including the
operation-result-evidence ceiling. Non-ceiling rejection-precedence records
are separately exactly
`{priority, rejection_code, validation_rule_id}` with contiguous priorities
from one. The array is strictly increasing by unique `priority`, has no
duplicate rejection code/rule pair, and the first false rule is the only
cross-product rejection code.

Every `validation_rule_id` resolves an earlier `BOOLEAN_GUARD`
`PureRuleDescriptorV1` whose input schema byte-equals the closed
`PlanCoordinateValidationInputV1` schema. Its exact runtime input is:

```text
plan_coordinate_request
operation_spec
checkpoint_selector | null
target_field_registry
operation_counter_schema
marker_contract
target_observation_context_descriptor
target_observation_descriptor
target_observation_root_descriptor
hard_ceiling_record
```

The coordinate request is the complete manifest row. Every other member is
the complete unique record resolved from the embedded Step-2 input or the
hard-ceiling record; `checkpoint_selector` is null exactly in instrumentation
mode `OFF`. The rule's input schema, assumptions, AST, and result schema are
frozen in the universe manifest. The verifier constructs this same input for
each coordinate, evaluates rules in precedence order, and accepts only a
literal Boolean result. The first `false` yields
`CROSS_PRODUCT_REJECTED`; `true` continues. A schema failure, unresolved
identity, unequal duplicate body, rule exception, non-Boolean result, or
indeterminate host lookup invalidates the inventory rather than becoming a
coordinate rejection. No profile, generated bound, caller field, or ambient
registry is an input to this pre-bound cross-product decision.

`ComponentBoundDerivationDescriptorV1` freezes every coordinate-level scalar
formula before generation. It has exact keys:

```text
operation_kind
derivation_priority
bound_member
ceiling_member | null
metric_member
input_schema_dialect = RAW_V8_CLOSED_SCHEMA_V1
input_schema
ordered_support_bindings
derivation_ast
ast_node_count
derivation_soundness_rule =
  EXHAUSTIVE_CANONICAL_SERIALIZATION_COVERAGE_V1
ordered_coverage_obligation_records
result_schema_dialect = RAW_V8_CLOSED_SCHEMA_V1
result_schema
component_bound_derivation_descriptor_id
```

`operation_kind` is non-null. Priorities are contiguous from one within each
operation. A support binding is exactly:

```text
input_field_name
source_kind =
  PLAN_COORDINATE | WEIGHTED_PROFILE | EMERGENCY_PROFILE |
  TARGET_BUDGET | HARD_CEILING | STEP2_EMBEDDED_RECORD |
  EARLIER_COMPONENT
source_record_role
source_json_pointer
source_bound_member | null
```

`source_record_role` is one of
`PLAN_COORDINATE_REQUEST, WEIGHTED_DFA_BOUND_PROFILE,
EMERGENCY_SUFFIX_PROFILE, TARGET_SPAN_BUDGET, HARD_CEILING_RECORD,
OPERATION_SPEC, TARGET_FIELD_REGISTRY, OPERATION_COUNTER_SCHEMA,
MARKER_CONTRACT, CHECKPOINT_SELECTOR, TARGET_OBSERVATION_CONTEXT_DESCRIPTOR,
TARGET_OBSERVATION_DESCRIPTOR, TARGET_OBSERVATION_ROOT_DESCRIPTOR,
COMPONENT_BOUND_RECORD`. `source_bound_member` is non-null exactly for
`EARLIER_COMPONENT`, names a lower-priority descriptor in the same operation,
and the role is then `COMPONENT_BOUND_RECORD`; otherwise it is null. Every
other source resolves uniquely through the coordinate's already-fixed chain.
The JSON pointer is canonical RFC-6901 and resolves a value that validates the
binding field's exact closed input-schema node; null, Boolean, finite enum,
bounded string, safe uint, array, and closed object values are permitted only
when that node declares them. This permits formulas to distinguish OFF/ON and
the null/non-null selector without an untyped sentinel.

Bindings are in exact `input_schema` property order, have unique field names,
and cover every input property exactly once; no unused binding, hidden
constant source, ambient lookup, or generator-selected support is legal. The
derivation AST uses the exact PureRule AST/type semantics, plus one additional
total operator `IF` with exactly
`{op=IF,args=[Boolean, same-type then, same-type else]}`. It has no input
assumptions and its root is a non-null safe uint validating `result_schema`.
All branches are statically total and every arithmetic intermediate is a
safe uint. `ast_node_count` and the semantic ID are independently recomputed.

Freezing an AST is not by itself evidence that it is an upper bound.
One coverage obligation is exactly
`{destination_record_role, destination_json_pointer,
contribution_kind, cardinality_ast_pointer|null, octet_ast_pointer|null}`.
`destination_record_role` is one of
`TARGET_TRANSACTION_STREAM, TARGET_PROJECTION_ARRAY,
EMERGENCY_PROJECTION_SEGMENT, TARGET_OPERATION_BATCH_ARRAY,
EMERGENCY_OPERATION_BATCH_SEGMENT, TARGET_OBSERVATION_ARRAY,
CANDIDATE, ATTEMPT_PRESENT, ATTEMPT_ABSENT,
OPERATION_RESULT_EVIDENCE, TERMINAL, CLOSURE, RETAINED_DEPENDENCIES,
OUTER_PREFIX_SHELL, CLOSED_PREFIX, SAMPLE`. `contribution_kind` is one of
`SCALAR_VALUE, OBJECT_KEY_COLON, OBJECT_COMMA, OBJECT_BRACES,
ARRAY_ELEMENT, ARRAY_COMMA, ARRAY_BRACKETS, NULL_LITERAL,
STRING_QUOTES_OR_ESCAPING, SEMANTIC_COUNT`. `SEMANTIC_COUNT` requires a
non-null cardinality pointer and null octet pointer. Every other kind requires
a non-null octet pointer; array element/comma contributions also require the
cardinality pointer, while fixed scalar/object/bracket/string contributions
require it null. Pointers are canonical JSON pointers into
`derivation_ast` and resolve a safe-uint node that contributes exactly that
factor/value. Records sort strictly by complete canonical JSON bytes and are
duplicate-free.

The verifier maps each destination role to the one resolved complete closed
schema/envelope named by the coordinate/profile/Step-2 chain and derives the
complete canonical-serialization contribution multiset recursively from the
resolved closed output schemas and exact envelope/composition roles. The
recursion is exact:

```text
NULL              -> 4
BOOLEAN           -> exact const length, else max(4,5)
SAFE_UINT         -> decimal ASCII length of its maximum
CONST/ENUM        -> maximum canonical JSON octets of its finite values
STRING            -> 2 + maximum JSON-escaped ASCII octets
NULLABLE(T)       -> MAX(4, B(T))
ARRAY(T,n)        -> 2 if n=0, else 2 + n*B(T) + (n-1)
OBJECT(fields)    -> 2 + sum(quoted-key bytes + 1 + B(value))
                     + max(0, field_count-1)
```

Object fields use the schema's canonical UTF-8 key order. String escaped
weight is two for quote, backslash, backspace, tab, newline, form feed, and
carriage return; six for every other codepoint in `0x00..0x1f`; and one for
every remaining ASCII codepoint, including `0x7f`. These are exactly the
canonical serializer's JSON escape lengths. The maximum is the unique
weighted-DFA dynamic program
over `(language_state, emitted_length)` with state/length ascending
iteration. This component compiler retains only the numeric maximum weight
and emits no predecessor or witness; the result must equal the resolved
language descriptor's `maximum_canonical_octets`. Any separate constructive
maximum uses that descriptor's lexicographically greatest canonical-JSON
tie-break. Fixed-cardinality arrays use
their exact count; bounded variable arrays use their maximum unless a bound
input fixes a smaller count. Optional attempted/no-attempt branches compile
to `MAX` unless a frozen coordinate value selects one. The Section 5 target/
emergency pair compiles to its exact four `IF` cases and never adds two
bracket pairs.

Every
derived contribution occurs exactly once in the sorted obligation array and
no extra contribution exists. For counts, the same checker derives every
semantic event/entry/batch relation from the frozen profile/budget rules.
It then compiles those obligations with
`CANONICAL_BOUND_EXPRESSION_COMPILER_V1`, normalizes commutative operand order
by flattening associative `ADD/MUL/MIN/MAX`, constant-folding, sorting
remaining operands by canonical AST bytes, and rebuilding a left-associated
tree; noncommutative operands retain source order. The result must byte-equal
`derivation_ast`. A `CONST(0)`, omitted separator/key/null branch,
double-counted nested evidence, or unbound array cardinality therefore
rejects even when two evaluators would agree on it.

For each operation the manifest requires exactly one descriptor for every
numeric hard-ceiling member, with the same non-null `ceiling_member` and
metric, plus exactly these four support-only descriptors with
`ceiling_member=null`:

```text
maximum_target_observation_count
target_projection_entry_canonical_bytes
emergency_projection_entry_canonical_bytes
maximum_remaining_ledger_receipt_count
```

There is no other descriptor. The per-operation required set and priority
order are byte-equal between the universe manifest and emitted inventory.
This makes the complete ceiling-to-metric-to-support-to-formula mapping
exhaustive; names such as “canonical composition” are explanatory only and
cannot substitute for the frozen AST. In particular, the target/emergency
array formula is expressed by `IF` over the exact zero/nonzero counts and
implements the four Section 5 cases, while candidate, attempt, terminal,
closure, retained-dependency, outer-shell, closed-prefix, and sample formulas
bind every canonical JSON key/separator/null/array contribution as literal
AST constants or resolved schema maxima. Two independent evaluators must
reproduce every scalar and descriptor identity before any disposition is
accepted.

`FullPrefixBoundRecordV1` proves that target admission composes with the
retained schemas for one declared coordinate before any admission decision.
It has exact keys:

```text
plan_coordinate_sha256
operation_spec_id
instrumentation_mode
checkpoint_selector_id | null
checkpoint_selector_entry_count
marker_capacity
loop_probe_capacity
local_shutdown_limit_vector | null
weighted_dfa_bound_profile_id
target_span_budget_id
hard_ceiling_record_id
target_field_registry_id
operation_counter_schema_id
marker_contract_id
target_observation_context_type
target_observation_type
target_observation_root_type
ordered_component_bound_records
maximum_target_observation_count
maximum_remaining_ledger_receipt_count
candidate_canonical_bytes
attempt_canonical_bytes
operation_result_evidence_canonical_bytes
target_projection_entry_canonical_bytes
emergency_projection_entry_canonical_bytes
terminal_canonical_bytes
closure_canonical_bytes
retained_dependency_canonical_bytes
outer_prefix_shell_canonical_bytes
closed_prefix_canonical_bytes
sample_canonical_bytes
full_prefix_bound_record_id
```

Every duplicated coordinate member byte-equals the manifest request resolved
through `plan_coordinate_sha256`; profile and budget are the unique
deterministic outputs for that coordinate. The ceiling ID equals the one
resolved through its target-span budget. Every
type/contract/registry/selector resolves to one complete embedded Step-2 input
record.

One `ComponentBoundRecordV1` has exactly:

```text
bound_member
ceiling_member | null
metric_member
component_bound_derivation_descriptor_id
ordered_resolved_support_records
upper_bound_value
bound_kind = CANONICAL_CONSERVATIVE_UPPER_BOUND
component_bound_record_id
```

Each resolved support record is exactly
`{input_field_name, source_identity_field|null, source_identity|null,
source_json_pointer, resolved_value}` in descriptor binding order.
It must resolve the binding's exact role/object/pointer; an earlier-component
source has lower derivation priority and the referenced component ID/value
must match. The descriptor ID resolves the same operation, bound, ceiling,
metric, schema, bindings, and priority. Evaluating its frozen AST over the
resolved input object must produce `upper_bound_value`; dependencies are
acyclic by priority.

The two source-identity members are null together only for a null
`CHECKPOINT_SELECTOR` source in instrumentation mode `OFF`; that null source
is anchored by the non-null plan-coordinate identity and
`resolved_value=null`. Every other support has both identity members non-null.

`ordered_component_bound_records` contains exactly one record for every
required per-operation derivation descriptor, including the four support
records, in identical priority order. A record with non-null
`ceiling_member` byte-equals that ceiling descriptor's metric; a support
record has null ceiling and is never independently compared to a hard
ceiling. Every record remains conservatively labelled even when a diagnostic
full materialization happens to attain the value. No concrete path/span
certificate can prove a full-prefix or sample body and no such certificate
is a canonical member.

Every full-prefix scalar that directly represents one hard-ceiling member
equals its corresponding component record. `maximum_target_observation_count`,
`maximum_remaining_ledger_receipt_count`, and the separately listed
normal/emergency entry-array byte values are exact
support values used by downstream component formulas; the ceiling component
for target projection bytes is their four-case combined array composition,
not either support alone. These support values are not mislabeled as
independent hard ceilings. Bounds are not sums of unrelated ceilings.
The receipt support descriptor's normalized AST is exactly equivalent to:

```text
1  # candidate
+ 1  # maximum ATTEMPT_PRESENT branch
+ target_projection_entry_count
+ maximum_emergency_receipt_count
+ 1  # terminal
+ 1  # closure
```

Both variable counts resolve from the target budget/profile chain. Its
coverage obligations contain exactly one `SEMANTIC_COUNT` contribution for
`CANDIDATE`, `ATTEMPT_PRESENT`, `TARGET_PROJECTION_ARRAY`,
`EMERGENCY_PROJECTION_SEGMENT`, `TERMINAL`, and `CLOSURE`; the
`ATTEMPT_ABSENT` contribution is zero. There is no observation,
batch-envelope, or artifact-shell receipt contribution. The compiler proves
safe-uint totality and byte-equality to this frozen ledger layout. The
`maximum_target_observation_count` descriptor binds
`checkpoint_selector_entry_count` from `PLAN_COORDINATE_REQUEST`; it never
dereferences a null selector or supplies an implementation-chosen fallback.
Target and emergency entry arrays compose by
the four-case Section 5 formula, never by adding two independently framed
arrays. `closed_prefix_canonical_bytes` equals exact canonical composition
of candidate, attempted/no-attempt branch, target plus emergency, terminal,
closure, retained dependencies, and shell. Sample bytes add only the exact
sample framing. The record ID is `semantic_id()` under the literal
full-prefix-bound domain over all preceding members.

`operation_result_evidence_canonical_bytes` is the certified nested result
evidence upper bound used to prove its 524,288-byte ceiling and the terminal maximum;
because those bytes are inside the terminal, closed-prefix composition does
not add them a second time.

Each admitted plan record is created only after its full-prefix bound passes
and has exact keys:

```text
plan_coordinate_sha256
operation_spec_id
instrumentation_mode
checkpoint_selector_id | null
checkpoint_selector_entry_count
marker_capacity
loop_probe_capacity
local_shutdown_limit_vector | null
weighted_dfa_bound_profile_id
target_span_budget_id
full_prefix_bound_record_id
admitted = true
admitted_plan_record_id
```

Every duplicate byte-equals the coordinate/full-prefix record. Its ID is
`semantic_id()` under the literal admitted-plan domain over all preceding
members. Dependency order is coordinate, profile/budget, full-prefix bound,
then admitted plan; there is no reciprocal identity cycle.

`PlanCoordinateDispositionV1` has exact keys:

```text
plan_coordinate_sha256
disposition =
  ADMITTED_BY_TIER1_BOUND | BOUND_REJECTED | CROSS_PRODUCT_REJECTED
weighted_dfa_bound_profile_id | null
target_span_budget_id | null
full_prefix_bound_record_id | null
admitted_plan_record_id | null
rejection_code | null
ordered_failed_ceiling_members
failing_ceiling_member | null
failing_metric_member | null
computed_upper_bound | null
ceiling_value | null
bound_kind | null
plan_coordinate_disposition_id
```

First, every non-ceiling validation rule is evaluated in manifest precedence.
If one fails, the disposition is `CROSS_PRODUCT_REJECTED`: all profile,
budget, bound, plan, and metric members are null, the failed-ceiling array is
empty, and `rejection_code` is the first false rule's code. If all pass, the unique profile, budget,
and complete full-prefix bound are non-null and every ceiling descriptor is
evaluated in priority order.

If no component upper bound exceeds its ceiling, the disposition is
`ADMITTED_BY_TIER1_BOUND`: the exact admitted plan is non-null; rejection,
failure, value, and bound-kind members are null/empty. If one or
more exceed, the disposition is `BOUND_REJECTED`: the admitted plan is null;
the failed-ceiling array contains exact `ceiling_member` strings only and is
the complete nonempty descriptor-priority-ordered set with no duplicate. The
four primary failure members name the first element and its exact bound and
ceiling: `failing_ceiling_member` equals the first string, while
`failing_metric_member`, `computed_upper_bound`, and `ceiling_value` equal
the corresponding descriptor/component values. `bound_kind` byte-equals the component's required
`CANONICAL_CONSERVATIVE_UPPER_BOUND`. Exact attainment is not a Raw V8
canonical case. Every primary uses the literal
`CONSERVATIVE_BOUND_EXCEEDS_CEILING`: it is safe rejection, not evidence that
the ceiling is reachable. The disposition ID is
`semantic_id()` under
`RiskYieldMMA2MPlanCoordinateDispositionV1V4_9F_RawV8` over every preceding
member.

The Raw V8 candidate and attempt both carry `admitted_plan_record_id`. The
verifier derives the exact coordinate hash from their immutable request,
resolves exactly one disposition, requires `ADMITTED_BY_TIER1_BOUND`, and
then byte-compares the plan/profile/budget/full-prefix chain before candidate
persistence. A bound-rejected or cross-product-rejected coordinate cannot be
overridden by a caller-supplied plan ID.

Raw V8 has no canonical rejected-boundary witness record. A conservative
upper bound above a ceiling proves only that admission is unsafe under the
frozen analysis; it does not prove an attainable over-ceiling materialization.
A cross-product rejection is already completely and deterministically
represented by its coordinate disposition and first failed rule. Optional
concrete plus-one or counterexample materializations belong only to the
separately hashed diagnostic report and cannot affect an identity,
disposition, or GO decision.

### 12.5 Canonical inventory

The literal codec inventory hash is:

```text
literal_codec_inventory_sha256 =
  sha256_digest({
    "domain": "RiskYieldMMA2MLiteralCodecInventoryV1V4_9F_RawV8",
    "ordered_native_shape_ids": [strictly increasing IDs],
    "ordered_strict_evidence_shape_ids": [strictly increasing IDs],
    "ordered_record_variant_ids": [strictly increasing IDs],
    "ordered_projection_entry_variant_ids": [strictly increasing IDs],
    "ordered_operation_batch_envelope_descriptor_ids":
      [strictly increasing IDs],
    "ordered_bounded_string_language_descriptor_ids":
      [strictly increasing IDs],
    "ordered_tls_handshake_trace_profile_ids":
      [strictly increasing IDs],
    "ordered_tls_record_splitter_profile_ids":
      [strictly increasing IDs],
    "ordered_record_kind_contribution_ids":
      [strictly increasing IDs],
    "ordered_independent_parser_oracle_descriptor_ids":
      [strictly increasing IDs],
    "ordered_pure_rule_ids": [strictly increasing IDs],
    "ordered_metric_abstract_domain_descriptor_ids":
      [strictly increasing IDs],
    "ordered_component_bound_derivation_descriptor_ids":
      [strictly increasing IDs]
  })
```

The canonical `TargetBoundInventoryV1` identity payload is:

```text
correction_document_sha256
parent_protocol_sha256
step2_inventory_input
step2_inventory_input_sha256
generator_source_sha256
generator_version
target_bound_universe_manifest
target_bound_universe_manifest_id
literal_codec_inventory_sha256
ordered_bounded_string_language_descriptors
ordered_tls_handshake_trace_profiles
ordered_tls_record_splitter_profiles
ordered_record_kind_contribution_records
ordered_independent_parser_oracle_descriptors
ordered_native_shape_descriptors
ordered_strict_evidence_shape_descriptors
ordered_record_variant_descriptors
ordered_projection_entry_variant_descriptors
ordered_operation_batch_envelope_descriptors
ordered_pure_rule_descriptors
ordered_target_dfa_descriptors
ordered_metric_abstract_domain_descriptors
ordered_component_bound_derivation_descriptors
target_dfa_id_by_operation
hard_ceiling_record
ordered_symbol_bounds
ordered_emergency_suffix_universal_validation_certificates
ordered_dfa_metric_bound_certificates
ordered_emergency_suffix_profiles
ordered_weighted_dfa_bound_profiles
ordered_target_span_budgets
ordered_full_prefix_bound_records
full_prefix_bound_record_id_by_plan_coordinate_sha256
ordered_admitted_plan_records
ordered_plan_coordinate_dispositions
plan_coordinate_disposition_id_by_coordinate_sha256
```

Every embedded descriptor/record ID is recomputed. Arrays are strictly
increasing by their terminal identity field's UTF-8 bytes. The operation map
has exactly `ACK_DEADLINE_EXPIRY`, `INGRESS`, `LOCAL_SHUTDOWN`, and
`SUBSCRIPTION_DISPATCH`; each value resolves the unique target-DFA descriptor
whose embedded `operation_kind` equals that key, and the map's value set
byte-equals the complete `ordered_target_dfa_descriptors` ID set. A
cross-operation permutation, duplicate value, missing descriptor, or orphan
descriptor rejects. `target_bound_inventory_id` is `semantic_id()` under
the literal inventory domain over this exact payload.

The one canonical output path is
`tests/raw_v8_target_bound_inventory_v1.json`. Its complete top-level object
is exactly the payload above followed by
`target_bound_inventory_id`; there is no wrapper, locator, timestamp, run ID,
or extra key. Raw file bytes are exactly
`canonical_json_bytes(complete_object) + b"\n"`. Generation writes those
bytes to a nonsymlink temporary regular file in the same directory, flushes
and `fsync()`s it, atomically replaces the output, and `fsync()`s the parent
directory; a pre-existing symlink or non-regular output rejects.

The required commands, run from repository root with the project Python, are:

```text
python scripts/tests/verify_raw_v8_target_bound_universe_v49f.py \
  --step2 tests/raw_v8_step2_inventory_v49f.json \
  --universe tests/raw_v8_target_bound_universe_manifest_v1.json

python scripts/tests/run_raw_v8_bound_generator_sealed_v49f.py \
  --universe tests/raw_v8_target_bound_universe_manifest_v1.json \
  --step2 tests/raw_v8_step2_inventory_v49f.json \
  --output tests/raw_v8_target_bound_inventory_v1.json

python scripts/tests/run_raw_v8_bound_generator_sealed_v49f.py \
  --universe tests/raw_v8_target_bound_universe_manifest_v1.json \
  --step2 tests/raw_v8_step2_inventory_v49f.json \
  --output tests/.raw_v8_target_bound_inventory_v1.reproduction.json

cmp --silent \
  tests/raw_v8_target_bound_inventory_v1.json \
  tests/.raw_v8_target_bound_inventory_v1.reproduction.json

python scripts/tests/verify_raw_v8_target_bound_inventory_v49f.py \
  --universe tests/raw_v8_target_bound_universe_manifest_v1.json \
  --step2 tests/raw_v8_step2_inventory_v49f.json \
  --inventory tests/raw_v8_target_bound_inventory_v1.json

rm -f tests/.raw_v8_target_bound_inventory_v1.reproduction.json
test ! -e tests/.raw_v8_target_bound_inventory_v1.reproduction.json
```

The sealed launcher first rejects a pre-existing reproduction output and any
symlink/special output. For each invocation it verifies the live source tree
against the universe source manifest, creates a fresh private temporary
directory outside the repository, copies exactly the manifested regular-file
bytes, makes files/directories read-only, rehashes the copy, and invokes only
that copy under the qualified interpreter with `sys.path` limited to the
sealed root plus qualified standard-library paths. It rejects a loaded
repository/site/user/plugin module, cleans the private copy in `finally`, and
never imports generator code into the launcher process. The live
`tools/raw_v8_bound_generator/generate.py` command is not normative.

The verifier is outside `generator_source_root`, shares no generator module,
parses all three exact files independently, recomputes every schema/semantic
ID, certificate, bound, disposition, map, closure, source/document hash, and
canonical raw output byte, and exits nonzero at the first mismatch. A second
generator run to a fresh regular temporary path followed by byte-for-byte
comparison with the canonical output is the required reproducibility check;
the fixed dot-file is noncanonical and must be absent after the exact cleanup
commands above.
Success from the generator alone is never acceptance evidence.

The duplicated correction, parent, Step-2, source, and version members
byte-equal the resolved universe manifest. Language, TLS handshake/splitter,
parser-oracle, metric-abstract-domain, and component-derivation arrays contain
complete descriptor bodies, not locators; their identities are bijective with
the corresponding required manifest arrays and codec inventory. After the
inventory is loaded, no ambient filesystem, regex/parser engine, production
module, schema registry, or process state is a permitted resolution source;
the only executable oracle seam is the descriptor-supplied restricted-WASM
module under its complete embedded ABI and deterministic fuel/memory limits.

Canonical proof closure is set-based and exact. Starting from every weighted
profile, follow its target metric certificate and emergency profile; from the
emergency profile follow its emergency metric certificate and universal
validation certificate; from every full-prefix record follow every component
derivation descriptor and lower-priority component dependency. The reached
sets must equal, respectively,
`ordered_dfa_metric_bound_certificates`,
`ordered_emergency_suffix_universal_validation_certificates`, and
`ordered_component_bound_derivation_descriptors`; the exact set of emergency
profiles reached directly from weighted profiles must also byte-equal
`ordered_emergency_suffix_profiles`. Shared DAG nodes may be
reached more than once, but an orphan, unresolved reference, unequal bytes
under one ID, cycle, or extra array member rejects. Diagnostic concrete path
certificates have no canonical array or proof map and are invisible to this
closure.

For every required `(operation_kind,operation_spec_id,target_dfa_id)` tuple,
the closure contains exactly one `TARGET_FULL_PATH` metric certificate with
the six-class set, exactly one emergency universal-validation certificate,
exactly one `EMERGENCY_SUFFIX` metric certificate pointing to that universal
certificate, exactly one emergency profile pointing to both emergency
objects, and exactly one weighted profile pointing to the target certificate
and emergency profile. Duplicate equivalent IDs, a second certificate for
the same tuple/scope, or any crossed link rejects.

`step2_inventory_input` is the complete canonical JSON value of the
regenerated Step-2 inventory, not a path, locator, or hash-only assertion.
`step2_inventory_input_sha256` equals
`sha256(canonical_json_bytes(step2_inventory_input))`; the input's own
inventory hash and every embedded record identity are independently
recomputed. Every registry, counter schema, marker contract, checkpoint
selector, observation codec, operation spec, and external type referenced
here resolves to exactly one complete record in that embedded input. Missing
resolution, duplicate identity, unequal bytes under one identity, or ambient
file/process lookup rejects.

Dependency order is acyclic:

```text
final correction and parent bytes
-> regenerated Step-2 inventory input
-> target-bound inventory
-> Step-3 freeze, schema candidates, and initializer values
```

The Step-2 input may bind correction/parent hashes, but it cannot contain
`target_bound_inventory_id`, a target-bound artifact hash, or any
descriptor/profile/budget/plan/full-prefix identity whose preimage
depends on this inventory. This document likewise never embeds the resulting
inventory ID or file hash.

`full_prefix_bound_record_id_by_plan_coordinate_sha256` has exactly one key
for every coordinate whose non-ceiling validations pass and no other key.
Each value resolves exactly one full-prefix record with that coordinate; each
full-prefix record occurs once. Cross-product-rejected coordinates have no
full-prefix map entry.

`plan_coordinate_disposition_id_by_coordinate_sha256` has exactly one key for
every manifest coordinate and no other key. Each value resolves one complete
disposition with the same coordinate; every disposition occurs once. The
admitted-plan array is exactly the set referenced by admitted dispositions.
Arrays sort by their terminal IDs; both maps sort by coordinate hash.
Every emitted weighted profile and target budget is reached by at least one
non-cross-product disposition/full-prefix chain, and every full-prefix,
admitted-plan, and disposition record is reached by the maps above.
Unreferenced alternative plans, profiles, budgets, or bounds are forbidden.

For every coordinate, independent recomputation therefore reaches exactly
one terminal decision:

```text
first non-ceiling validation false -> CROSS_PRODUCT_REJECTED
else first canonical component bound over ceiling -> BOUND_REJECTED
else -> ADMITTED_BY_TIER1_BOUND
```

No global least-over-ceiling/dominated-ceiling dichotomy is required. A
conservative bound above a ceiling remains a truthful, explicit per-coordinate
rejection and can be revisited only under a later frozen refinement protocol.

`correction_document_sha256` is raw SHA-256 of the final frozen correction
document bytes. This document must never embed the resulting inventory ID or
inventory-file hash; doing so would create a hash cycle. Any later document
edit requires a fresh inventory.

Representative count equations are:

```text
subscription success = 5 + 4 * send_results
subscription success batches = 4 + 2 * send_results
ACK not due          = 0
ACK due              = 3

ingress:
  RAW                         = 2
  parser contribution         = parser units + close transitions
  message contribution        <= 10 * completed application messages
  Pong output                 = 4 + 4 * send results
  Close output                = 6 + 4 * send results

clean local shutdown excluding terminal ingress:
  local WS Close              = 6 + 4 * WS send results
  TLS close-notify            = 5 + 4 * TLS send results
  command start               = 1
  half-close success          = 3
  notify-then-clean polls     = 8

terminal ingress:
  durable read attempt        = 1
  DATA result + RAW adoption  = 3
  non-DATA read result        = 1
  parser contribution         = parser units + peer-Close transitions
```

The generator must demonstrate the 48-MiB target-entry cap and 96-MiB closed
prefix independently. It must not multiply a guessed average record size by a
count. For example, 32,768 current no-output parser events already exceed 48
MiB before receipt framing, so such a legal parser input is rejected before a
candidate rather than truncated or compacted after observation.

No shutdown plan value, checkpoint/marker/probe capacity tuple, schema
fingerprint, admitted-plan identity, or Step-3 GO is frozen by this prose.
Raw V8 remains NO-GO until a conforming inventory containing every descriptor,
binding, required coordinate disposition, and required bound proof above has actually been
emitted, independently reproduced byte-for-byte and identity-for-identity,
and consumed by the regenerated Step-2/Step-3/schema/initializer chain.

## 13. Implementation and acceptance order

1. Reconcile this correction with the parent and Step-3 freeze.
2. Add V2 Step-2 types and regenerate the independent inventory.
3. Add the singleton locator and regenerate schema candidates.
4. Re-run initializer and complete Raw V7/final-tree regression acceptance.
5. Implement mutation guards, root capability, one-shot permits, span
   accounting, operation-batch partition replay, and the four DFAs.
6. Implement independent ingress oracle and V2 operation result replay.
7. Implement finite shutdown budgets and emergency convergence.
8. Implement marker/probe/terminal/finalization/recovery corrections.
9. Generate plan bounds and accept only its published admissible region.
10. Run fault injection at every transaction, I/O, marker, probe, clock,
    serialization, commit, acknowledgement, and recovery boundary.
11. Run OFF/OFF, ON/ON, and OFF/ON paired effect-oracle tests.
12. Publish a Step-3 acceptance audit only after all exact hashes and full
    final-tree regressions pass.

Mandatory adversarial cases include:

- two simultaneous candidate creators;
- unrelated same-session and other-session appends while open;
- child task, `to_thread`, other loop/thread/store/connection, post-fork, and
  stale-fence capability use;
- every valid and invalid DFA transition;
- operation-batch gap, overlap, duplicate, unknown token, and wrong request;
- exact-byte/count limit; optional diagnostic exact plus-one only where
  reachable, plus the required canonical disposition for every frozen
  coordinate;
- input mismatch after owner read;
- subscription replayed authorization;
- ACK zero/three-receipt branches and forbidden partial group;
- shutdown exhaustion at every dimension;
- a blocked attempt commit proving zero owner calls before exact ACK;
- attempt rollback, wrong ACK, acknowledgement uncertainty, and
  pre-ACK cancellation each proving zero owner/driver calls;
- commit latency crossing to `BOTH_DUE` and each `CLOCK_XOR` polarity,
  including equality-at-deadline, proving the exact pre-I/O result, zero work
  deltas, zero owner/driver calls, and position-matched decisive terminal;
- `BOTH_ALLOW` proving one owner call and strict clock ordering; copied/wrong
  or unconsumed-invalid capability rejects before driver entry, a
  `DRIVER_CORE_RESULT_SEALED` reuse returns the exact same core/key, and
  `DRIVER_ENTERED_WITHOUT_CORE_RESULT` enters unknown-effect recovery without
  synthesizing a result;
- fault injection after attempt commit, after ACK, after the post-ACK gate,
  during owner I/O, after driver-core seal, after the first post-effect pair,
  after the second DATA pair, and before/after actor-result projection commit,
  proving no repeated I/O, no resampled sealed clock, and exact
  attempt/result/previous-result chains;
- fault injection at every old post-positive receive/feed/unwrap/drain/
  authority-check site, proving no fallible TLS/read/output call occurs after
  the first positive plaintext and before the driver core is sealed;
- marker/probe phase-code cross-products;
- terminal clock failure at every read;
- head change between finalization-plan construction and `BEGIN`;
- fault after every terminal/closure write boundary;
- candidate-only and attempted recovery;
- commit acknowledgement loss and idempotent replay; and
- forged second locator/corrupt snapshot.

## 14. Primary-source support and limits

The concurrency design follows documented Python behavior:

- [`contextvars`](https://docs.python.org/3.12/library/contextvars.html):
  asyncio supports context propagation, which is why context identity alone
  cannot authorize a mutation.
- [`asyncio` tasks](https://docs.python.org/3.12/library/asyncio-task.html):
  task creation copies the current context and `current_task()` exposes the
  exact executing task used by the additional object-identity check.
- [`sqlite3`](https://docs.python.org/3.12/library/sqlite3.html) and
  [SQLite transactions](https://www.sqlite.org/lang_transaction.html):
  transaction state and commit acknowledgement must be resolved explicitly;
  SQLite serializes writes but does not prove application-level receipt
  attribution.
- [SQLite atomic commit](https://www.sqlite.org/atomiccommit.html) and
  [locking](https://www.sqlite.org/lockingv3.html): support the atomic
  terminal-plus-closure and crash-replay design within the qualified local
  filesystem profile.

These sources support mechanisms, not the trading value of Raw V8. The DFAs,
budgets, causal specs, and acceptance thresholds are project-specific and
must be falsified empirically. Complete protocol correctness does not imply
predictive edge or profitability.
