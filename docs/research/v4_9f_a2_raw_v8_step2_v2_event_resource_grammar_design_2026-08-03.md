# Raw V8 Step-2 V2 case-level event and resource-meter grammar

Date: 2026-08-03
Status: **OWNER DECISIONS CLOSED; INTEGRATED IN THE ACCEPTED `S1-A1` SEED**

## 1. Decision boundary

This design closes the case-level event stream needed by two independent F1
implementations. It does not authorize F1. The accepted seed contains the
closed grammar and complete bounded hand oracles described here.

The final event catalog must make the following function total and
deterministic:

```text
(seed catalog, logical count plan, recurrence outputs, exact attainer,
 scope schedule) -> (ordered event tokens, 18 resource measurements,
 event-stream digest)
```

No implementation may infer an ordering, subject, multiplicity, retained-live
set, or byte-accounting rule from prose.

## 2. Event token

Every event token has exactly these members:

```text
event_position
execution_phase
logical_derivation_step_position | null
event_kind
event_ordinal
subject_schema_version
subject_kind
subject_role
subject_ordinal | null
subject_canonical_octets
subject_sha256
aggregation_multiplicity
logical_unbatched_equivalent_count
observed_value | null
```

Rules:

- `event_position` is contiguous one-based across the complete case stream.
- `event_ordinal` is contiguous one-based per `event_kind` across the case.
- `subject_ordinal` comes from the subject collection, not from event position.
- `subject_role` binds the exact semantic purpose of the subject. It is
  especially mandatory for hash preimages, where byte-equal preimages used by
  two semantic identities are two operations.
- `subject_canonical_octets` and `subject_sha256` are recomputed from the exact
  subject bytes. Length alone is never semantic authority.
- `aggregation_multiplicity` is a checked UInt128. Only descriptor, intrinsic
  rule, cross-rule, and application events may use a value greater than one.
  Every byte-bearing event binds exactly one physical subject and therefore
  has aggregation multiplicity one.
- `logical_unbatched_equivalent_count` is separate from aggregation. It is
  nonzero only for `TRANSITION_ATTEMPT` and is derived by the transition
  program. M4 counts the one physical transition token; M5 adds this explicit
  unbatched-equivalent count. A batched transition may therefore represent
  many logical transfers without pretending that many byte-bearing tokens
  were emitted.
- the running resource vector is not serialized in a token and therefore
  cannot feed its own event-stream digest.

The permitted phases, in order, are:

```text
CASE_OPEN
PLAN_IDENTITY_BINDING
UPPER_BOUND_DERIVATION
LEGAL_ATTAINMENT_VALIDATION
SCOPE_APPLICATION_VALIDATION
DEPTH_AND_RETENTION_FINALIZATION
FINAL_RESULT_SERIALIZATION
EVENT_STREAM_FINALIZATION
```

## 3. Exact subject contract

| Event kind | Exact subject kind | Step | Subject ordinal | Aggregation / unbatched count | Observed value |
|---|---|---|---|---|---|
| `CASE_OPEN` | `CASE_OPEN_RECORD_V1` | null | null | one | null |
| `LOGICAL_DESCRIPTOR_VISIT` | `LOGICAL_DERIVATION_STEP_REFERENCE_V1` | required for ordinary steps; null for local controller | null | descriptor occurrence count / zero | null |
| `TRANSITION_ATTEMPT` | `RECURRENCE_TRANSITION_TOKEN_V2` | required for ordinary steps; null for local controller | physical transition ordinal | one / explicit transition unbatched equivalent | null |
| `BATCH_APPLICATION` | `BATCH_APPLICATION_RECORD_V1` | required | physical batch ordinal | one | null |
| `INTRINSIC_RULE_EVALUATION` | `INTRINSIC_RULE_EVALUATION_RECORD_V1` | source step when applicable | rule position | charged evaluation count / zero | null |
| `RESULT_CELL_EMIT` | `RECURRENCE_RESULT_CELL_V2` | required for ordinary steps; null for local controller | pre-merge result-cell ordinal | one | null |
| `CACHE_INSERT` | `RECURRENCE_CACHE_KEY_V2` | required for ordinary steps; null for local controller | first-insertion ordinal | one | null |
| `STEP_COMMITMENT_EMIT` | `RECURRENCE_STEP_COMMITMENT_V2` | required for ordinary steps; null for local controller | commitment ordinal | one | null |
| `APPLICATION_EVALUATION` | `APPLICATION_EVALUATION_RECORD_V1` | null | application invocation ordinal | charged invocation count / zero | null |
| `CROSS_RULE_EVALUATION` | `CROSS_RULE_EVALUATION_RECORD_V1` | null | application schedule position | charged rule-root count / zero | null |
| `HASH_PREIMAGE` | `HASH_PREIMAGE_BYTES_V1` | source step or null | hash-purpose ordinal | one | null |
| `RETENTION_OBSERVATION` | `LIVE_SET_SNAPSHOT_V1` | observation step or null | observation ordinal | one | retained octets |
| `DERIVATION_DEPTH_OBSERVATION` | `DERIVATION_DEPTH_RECORD_V1` | root or null | null | one | derived depth |
| `ITERATION_DEPTH_OBSERVATION` | `ITERATION_DEPTH_RECORD_V1` | root or null | null | one | derived depth |
| `FINAL_RESULT_EMIT` | `LOGICAL_CASE_DERIVATION_RESULT_V1` | null | null | one | null |
| `EVENT_STREAM_CLOSE` | `EVENT_STREAM_PREIMAGE_DESCRIPTOR_V1` | null | null | one | null |

Each subject kind needs a closed member schema and a canonical-byte source.
The token's `subject_role` uses a closed hash-purpose enum. The hash event's
subject bytes are the exact bytes passed to SHA-256, its
`subject_canonical_octets` is the exact preimage length, and its
`subject_sha256` is the resulting digest. It never measures the size of a
metadata descriptor in place of the real preimage.

## 4. Transition expansion and case program

The existing per-step aggregate fields do not determine an event stream. Each
ordinary recurrence kernel therefore needs a closed transition-expansion
program. Its ordered run records have exactly:

```text
transition_run_position
transition_source_kind
first_physical_transition_ordinal
physical_transition_count
logical_unbatched_equivalent_count
token_subject_expansion_program
logical_count_distribution_program
canonical_octet_sum_program
```

Run ordinal ranges are contiguous and non-overlapping. A run expands to
exactly `physical_transition_count` distinct physical `TRANSITION_ATTEMPT`
tokens, each with aggregation multiplicity one. Its positive per-token logical
counts sum to the run's `logical_unbatched_equivalent_count`. Across one step,
the run physical-count sum and logical-count sum must equal the existing
kernel meter expressions for physical transitions and logical
unbatched-equivalent transitions respectively. This is where descriptor,
array, and application transfer multipliers are applied; they never resize a
physical event token.

Every transition subject is constructed for its exact physical ordinal. M9
and M10 sum the resulting per-token canonical lengths. A run with
ordinal-dependent token bytes must provide an exact canonical-octet sum
program; multiplying one selected token length is forbidden. Case 475 maps
its eleven controller-transition records one-to-one to eleven physical and
eleven logical transitions.

The catalog stores one ordered AST with these nine program nodes:

1. `EMIT_CASE_OPEN_ONCE_V1`.
2. `EMIT_BOUND_PLAN_IDENTITY_HASH_V1` exactly once.
3. `EXECUTE_ORDINARY_STEPS_POSTORDER_V1`, selected only when a template is
   present.
4. `EXECUTE_LOCAL_CONTROLLER_ORDER_V1`, selected only for case 475.
5. `EXECUTE_EXACT_ATTAINER_VALIDATION_V1`.
6. `EXECUTE_SCOPE_SCHEDULE_LEXICAL_V1`.
7. `EMIT_DEPTH_AND_LIVE_SET_MAXIMA_V1`.
8. `EMIT_FINAL_RESULT_ONCE_V1` followed by its identity hash preimage.
9. `CLOSE_THEN_HASH_EXCLUDED_CONTROL_EVENTS_V1`.

For an ordinary step, the exact per-step order is:

```text
LOGICAL_DESCRIPTOR_VISIT, when multiplicity is positive
TRANSITION_ATTEMPT, increasing physical transition ordinal
BATCH_APPLICATION, increasing physical batch ordinal
RESULT_CELL_EMIT, complete-key byte order before merge
CACHE_INSERT, only for the first complete-key insertion
RETENTION_OBSERVATION at the prospective insertion boundary
HASH_PREIMAGE for each retained result cell, in complete-key byte order after
all candidate merges
STEP_COMMITMENT_EMIT, exactly once
HASH_PREIMAGE for that complete step commitment, exactly once
RETENTION_OBSERVATION at each frozen live-set boundary
```

`RESULT_CELL_EMIT` counts a complete pre-merge candidate cell. A duplicate
full key selects the byte-identical-key cell with maximum upper bound without
constructing a second merged cell. After all candidates are processed, the
retained winning cells are hashed in full-key byte order for the commitment.
The commitment is constructed after those cell digests exist and is hashed
immediately in the same step. Strict step postorder therefore produces
`cells(step 1), commitment(step 1), cells(step 2), commitment(step 2), ...`.
This makes child digests available before parent construction and allows each
full commitment preimage to be released after its hash instead of retaining
all commitment preimages until the end of the case.

Complete intrinsic rules relaxed during P2 are not silently charged as if
executed. Their exact P1/P3 evaluation occurs in
`LEGAL_ATTAINMENT_VALIDATION`, in descriptor postorder and rule authority
order. One aggregated rule token may carry the checked evaluation count in
`aggregation_multiplicity`; the subject binds the exact rule and occurrence
range. This aggregation is never used by a byte-bearing subject.

The scope program visits application schedule records in lexical application
name order, then invocation ordinal. It emits one aggregated
`APPLICATION_EVALUATION` token and one aggregated `CROSS_RULE_EVALUATION`
token per schedule record. The two multiplicities must equal the independently
rederived invocation and rule-root counts.

The local program uses controller state/transition order. Its event expansion,
including rule/application multiplicities, must be stored as a closed local
program rather than inferred from the provisional non-byte vector.

Every program node stores structured `iteration_source`, `ordinal_source`, and
one ordered emission record per event kind occurrence. Each emission record
contains a closed condition expression, checked cardinality expression, exact
subject-collection locator, subject-order enum, subject-ordinal source, and
separate aggregation-multiplicity and logical-unbatched-equivalent-count
expressions. A list of event-kind labels is not a program.

## 5. Per-case hash-preimage order

M11 admits exactly this nested program order:

1. the bound logical-count-plan identity envelope, once;
2. for each derivation unit in strict postorder:
   1. all retained result-cell preimages in complete canonical cell-key byte
      order; then
   2. that unit's single step-commitment preimage immediately;
3. the complete final-result identity preimage, once; and
4. the event-stream preimage, once and last.

The ordinary case units are its logical steps. Case 475 contributes one closed
local-controller derivation unit; it does not acquire a fabricated ordinary
step position.

Catalog, state-signature, kernel, source-authority, generator, manifest, and
other global validation hashes are F0/preflight work. They are not per-case
M11 terms. The per-unit result-cell-before-commitment order creates no conflict
with postorder or last-parent release: each cell is hashed before its unit
commitment is constructed and the complete commitment preimage is released
immediately after that unit's commitment hash.

## 6. Byte-accounting partition

The catalog stores these exact equations. Every term has coefficient one and
uses the event subject bytes once:

```text
M8  = sum_octets(CACHE_INSERT:RECURRENCE_CACHE_KEY_V2)

M9  = sum_octets(CACHE_INSERT:RECURRENCE_CACHE_KEY_V2)
    + sum_octets(TRANSITION_ATTEMPT:RECURRENCE_TRANSITION_TOKEN_V2)

M10 = sum_octets(CACHE_INSERT:RECURRENCE_CACHE_KEY_V2)
    + sum_octets(TRANSITION_ATTEMPT:RECURRENCE_TRANSITION_TOKEN_V2)
    + sum_octets(RESULT_CELL_EMIT:RECURRENCE_RESULT_CELL_V2)

M11 = sum_octets(HASH_PREIMAGE:HASH_PREIMAGE_BYTES_V1)

M18 = sum_octets(FINAL_RESULT_EMIT:LOGICAL_CASE_DERIVATION_RESULT_V1)
```

Consequences:

- step commitments and event-control tokens are not M9/M10 terms;
- result cells are M10 terms, not M9 terms;
- M18 has exactly one term and exactly one physical event per case: the
  complete final compact-canonical result. Result cells, commitments, framing
  fragments, nested results, prefixes, suffixes, and event-control records are
  forbidden M18 terms;
- event-token serialization is outside M8, M9, M10, and M18;
- M11 counts each actual hash invocation, even when its source bytes were also
  counted by another metric;
- a term is unique by `(metric_position, event_position)`, not by byte digest.

Any alternative accounting model requires an explicit protocol decision and
new metric names. It must not be smuggled in through an `emission_order`
label.

## 7. Peak retained live set

The live-set program tracks distinct entries of these kinds:

```text
RECURRENCE_CACHE_KEY_V2
RECURRENCE_RESULT_CELL_V2
RECURRENCE_STEP_COMMITMENT_V2
```

Equal bytes in distinct live entries count separately. The program derives
each child's last parent from the postorder DAG. At every parent it observes:

1. the complete live child set before parent materialization;
2. that set plus the prospective parent key/cell/commitment;
3. the live set after the current parent commitment hash and release consume
   the complete commitment preimage and the last-used children;
4. release in reverse child-step position immediately after last use.

Only a commitment digest may remain after the immediate per-unit commitment
hash, and only when a later parent or the final-result serializer requires it.
The final result binds the ordered commitment **digest records**, never the
complete commitment preimages. Each digest record is a distinct retained
entry for M17 until its last parent/final-result use, even when two digest byte
strings are equal. A complete commitment preimage is never retained after its
hash and is never reconstructed after release.

The complete 18-value resource measurement vector belongs to the separate
normative resource report and comparator output; it is not a member of
`LOGICAL_CASE_DERIVATION_RESULT_V1`. Embedding M18 in the object whose
canonical length defines M18, or embedding M11 before the final-result and
stream preimages have been hashed, would create a self-reference. The hand
oracle therefore binds the final-result bytes and the complete resource vector
as separate sibling evidence.

Transition-token buffers, canonicalizer scratch space, source-authority bytes,
event-token bytes, final-result serializer buffers, and the final event-stream
preimage are excluded from M17; their platform memory belongs to the separate
F0 RSS ceiling. The root commitment digest remains live through final-result
serialization and its hash, then releases.

Each `LIVE_SET_SNAPSHOT_V1` subject contains the ordered live-entry identity,
kind, canonical octets, acquisition position, last-parent position, and release
state. M17 is the maximum `observed_value` over all such events.

## 8. Cycle-free event-stream finalization

The exact order is:

1. freeze all events before `EVENT_STREAM_CLOSE`;
2. construct compact-canonical preimage
   `{logical_event_stream_version, logical_count_plan_id,
   ordered_pre_close_logical_event_tokens}`;
3. emit one `EVENT_STREAM_CLOSE` token containing the preimage descriptor; the
   close token is excluded from the preimage;
4. emit one `HASH_PREIMAGE` token for `EVENT_STREAM_PREIMAGE`; that token is
   also excluded from the preimage;
5. publish SHA-256 of the frozen preimage; no event follows the hash event.

The comparator recomputes and validates both excluded control tokens. Neither
token can contribute to M9, M10, or M18. The hash preimage contributes once to
M11. This breaks the token/hash self-reference without leaving the control
events unchecked.

## 9. Required hand oracles and negative controls

Every hand oracle is a complete bounded fixture, not merely a schema promise.
It includes:

```text
complete logical count plan
exact source objects or fixture locators
ordered event tokens
event-stream preimage octets encoded as lowercase hex and SHA-256
complete 18-value resource vector
final-result canonical octets encoded as lowercase hex and SHA-256
ordered live-set snapshots and peak
expected status
```

The oracle set covers unrestricted Boolean, nullable, finite text, relaxed
text, safe integer, batched array, stream-fallback array, record, self-value
union, owner-payload union, codec intersection, contextual application
schedule, and case 475.

These are minimum discriminating microfixtures, with transition cardinalities
through 16 where a batched/unbatched distinction is required. Full-scale
maximum-case token arrays are not hand oracles: F1/F2 stream them and compare
reconciled counts, exact byte sums, and the final digest. This keeps the oracle
surface reviewable without weakening the production stream contract.

The prospective catalog now carries three complete bounded oracle token
streams with exact canonical preimages, final-result bytes, live-set
snapshots, and independently recomputed 18-vectors. Together they cover all
thirteen required transfer/profile/local tags. The validator also rejects all
fourteen frozen mutation classes; a schema-only or empty-oracle catalog still
fails closed.

The validator must reject, independently, one event omitted, duplicated,
reordered, resized, assigned another subject digest, assigned another ordinal
or multiplicity, released early/late, moved to another byte metric, included
in the stream preimage incorrectly, or followed by an event after the final
hash.

## 10. Closed owner decisions

The owner approved M18 once-only ownership, the M9/M10 equations, inclusion of
P2 plus P1/P3 work, aggregation only for descriptor/rule/application work, and
the M17 object set. Section 5 freezes the corrected per-unit M11 order.

Case 475 must not acquire a fabricated ordinary logical-step position. The
cache key, result cell, step commitment, and transition token are closed
tagged unions. Each has an `ORDINARY_STEP` variant and a `LOCAL_CONTROLLER`
variant with an exact discriminant and mutually exclusive required/null
members. The local transition-token variant binds the controller-transition
position and identity, source and target state identities, and exact state
components. The ordinary variant binds the logical derivation step and
physical-transition fields. Unknown variants, mixed members, missing members,
zero sentinels, and invented ordinary positions reject.

The final derivation result binds ordered commitment digest records. Complete
commitment preimages are hashed once in the per-unit M11 order and released
immediately afterward. Only the digest record remains through its last parent
or final-result use. Reconstructing a released preimage, retaining every full
preimage until the end, or streaming copies of full preimages into the final
result is forbidden. M18 still charges only the one complete final canonical
result; serializer fragments are never M18 terms.

No owner choice remains open in this design note. The tagged schemas,
digest-owned final-result contract, complete event grammar, and nonempty hand
oracles are green in the accepted serialized catalog. The deterministic
regeneration and focused evidence are recorded in
[`v4_9f_a2_raw_v8_step2_maximum_protocol_v2_seed_acceptance_2026-08-09.md`](v4_9f_a2_raw_v8_step2_maximum_protocol_v2_seed_acceptance_2026-08-09.md).
