# V3.4 bounded physical-evidence architecture

> **Superseded architecture candidate (2026-07-14).** This document preserves
> the exploratory fixed-epoch design and its failure-mode analysis, but it is
> not the V4 implementation specification. Primary-source review found no
> demonstrated advantage over a single continuous RFC 9162 tree and exposed
> additional rollover, partial-seal, and identity risks. The frozen baseline is
> now [`v4_physical_evidence_protocol_freeze_2026-07-14.md`](v4_physical_evidence_protocol_freeze_2026-07-14.md):
> one continuous per-scope RFC9162 tree with incremental stored hashes. Fixed
> 4,096-leaf epochs remain a benchmark challenger only.

**Date:** 2026-07-14  
**Status:** Superseded exploratory proposal; retained for alternatives and
failure-mode history  
**Scope:** Bounded physical-market-data evidence, causal selection, typed
storage, restart verification, and scale acceptance  
**Predecessor:** The fixture-backed V3.3 physical-evidence reference slice

> This document is not a frozen protocol, implementation-complete claim,
> deployment certification, trading authorization, or evidence of predictive
> edge or profitability. Every identifier, record shape, limit, query rule,
> performance threshold, and trust assumption below remains provisional until
> it is explicitly frozen, implemented, independently tested, and accepted by
> the required soak gates.

## Executive recommendation

The provisional recommendation is a two-level bounded transparency-log
structure:

```text
exact raw capture
→ one immutable disposition for every provider-message occurrence
→ deterministic typed SQLite projection
→ fixed, 4,096-leaf per-scope RFC9162_SHA256 evidence epoch
→ immutable epoch seal
→ outer RFC9162_SHA256 log of epoch seals
→ constant-size evidence cutoff
→ causal indexed selection
→ chunked ordered selection-result commitment
```

This is preferred over a single Merkle Mountain Range (MMR) or a receipt hash
chain alone because it combines bounded live state, well-specified inclusion
and consistency algorithms, predictable proof sizes, and a simple rollover
boundary. The choice remains provisional until the hashing rules, scope order,
epoch boundary, disposition vocabulary, selector semantics, persistence model,
and acceptance hardware are frozen.

The initial implementation must not claim that ordinary Merkle inclusion
proves range completeness or non-inclusion. The proposed live selector is an
exact deterministic query over a verified typed projection of canonical
ledger objects. A later independently portable range/non-inclusion proof would
require a reviewed authenticated ordered-map design; it must not be improvised
inside the first implementation.

## Why V3.3 cannot be the live structure

The V3.3 reference slice materially improves causal correctness, but its
storage and verification structure is deliberately not production-scalable.
Confirmed implementation properties are:

- `EvidencePrefixV3` carries cumulative capture-segment, message-disposition,
  unresolved-disposition, observation-revision, active-revision, and
  status-revision ID arrays;
- its raw and normalized roots hash complete arrays rather than a
  proof-capable tree;
- parent-prefix validation requires cumulative set containment;
- `_physical_registry()` loads and reparses all prior physical objects;
- `_validate_record_links()` reconstructs manifest, evidence, and physical
  registries on each append;
- full verification repeats graph validation for every stored object.

The consequences are structural rather than tuning problems:

1. Prefix serialization grows linearly and necessarily exceeds the ledger
   object budget after only a small portion of a live history.
2. Repeated full-history registry reconstruction turns append and verification
   toward quadratic work.
3. Selection reparses canonical JSON instead of using causal typed indexes.
4. The new V3.3 disposition layer now represents duplicates, controls,
   malformed/provider errors, accepted no-output messages, and deterministic
   recovery without manufacturing observations, but its IDs add another
   cumulative prefix array and therefore do not solve bounded storage.
5. A local full replay is required to establish completeness; there is no
   bounded commitment or trusted suffix-verification anchor.

V3.4 therefore requires a new schema and validation lineage. It must not
silently change the meaning or identity of V3.3 records.

## Research basis and maturity

### RFC 9162

[RFC 9162, Certificate Transparency Version 2.0](https://www.rfc-editor.org/rfc/rfc9162.html)
is an **IETF Experimental RFC**, not an IETF Standards Track RFC. It specifies
the ordered binary Merkle Tree Hash construction, domain-separated leaf and
node hashing, inclusion proofs, and append-only consistency proofs. Its
consistency proof has logarithmic size, bounded above by approximately
`ceil(log2(n)) + 1` nodes.

### RFC 9942

[RFC 9942, COSE Receipts](https://www.rfc-editor.org/info/rfc9942/)
is an **IETF Standards Track RFC**. It registers `RFC9162_SHA256` as a
verifiable data structure and specifies COSE representations for signed
inclusion and consistency receipts. Its status strengthens the case for using
the RFC 9162 tree algorithms and proof vocabulary, but it does not by itself
certify this repository's implementation or operational trust model.

### Merkle Mountain Range

The reviewed
[Merkle Mountain Range IETF draft](https://datatracker.ietf.org/doc/html/draft-bryce-cose-merkle-mountain-range-proofs)
is an expired individual Internet-Draft with Experimental intent. The
Datatracker explicitly states that it has no formal IETF standing, and its
implementation maturity section describes reference/prototype implementations.
MMRs remain a credible experimental option, but this maturity is insufficient
for selecting one as the first consensus-critical evidence structure without
additional formal review and test-vector work.

### Incremental hash storage

The official Go
[transparency-log `tlog` package](https://pkg.go.dev/golang.org/x/mod/sumdb/tlog)
documents an incremental RFC 6962/9162-style stored-hash layout in which an
append stores at most `1 + log2(n)` hashes and averages fewer than two hashes
per sequential record. It is useful implementation evidence, not a substitute
for our own independently verified implementation and test vectors.

### SQLite

Relevant primary SQLite documentation includes:

- [Atomic Commit in SQLite](https://www.sqlite.org/atomiccommit.html);
- [Transactions](https://www.sqlite.org/lang_transaction.html);
- [STRICT tables](https://www.sqlite.org/stricttables.html);
- [Partial indexes](https://www.sqlite.org/partialindex.html);
- [WITHOUT ROWID](https://www.sqlite.org/withoutrowid.html);
- [Query planning](https://www.sqlite.org/queryplanner.html).

SQLite documents atomic commit and crash recovery under explicit filesystem,
locking, journaling, and synchronization assumptions. Those assumptions must
remain part of the deployment gate. A correct SQLite transaction does not
protect against a broken filesystem, deleted sidecars, malicious direct file
rewrites, or a stale database rollback without an externally retained
checkpoint.

## Commitment-structure comparison

| Candidate | Append | Random inclusion / append-only proof | Live state | Main advantage | Main limitation | Provisional decision |
|---|---:|---:|---:|---|---|---|
| Fixed 4,096-leaf RFC 9162 epochs plus outer epoch tree | Amortized O(1), worst O(log 4096) | O(log 4096) within an epoch and O(log epochs) across seals | Bounded frontier and bounded open epoch | Published algorithms, predictable limits, simple rollover | Two levels and an explicit open-epoch rule | **Preferred** |
| Single MMR | O(log N) | O(log N) | Small peak accumulator; node store remains O(N) | No periodic tree reset; natural append layout | Reviewed IETF draft is expired/experimental; proof conventions less mature here | Postpone |
| Hash chain or chained range digest | O(1) | O(N) random inclusion/range unless another tree is added | Constant head | Simple; resembles existing receipt chain | No compact random inclusion or complete-range proof | Retain only as complementary ledger ordering |

The fixed-epoch design does not replace the global receipt chain. The receipt
chain orders all ledger operations, signed checkpoints anchor advertised
states, and evidence epochs provide bounded content commitments and compact
proofs.

## Provisional trust and threat model

The first implementation is intended to detect and reject:

- omitted or double-classified raw provider messages;
- reordered scope messages or epoch leaves;
- altered canonical objects, dispositions, revisions, epoch nodes, or roots;
- future or backdated information entering an as-of selection;
- stale, incomplete, provisional, status-blocked, or gap-contaminated inputs;
- inconsistent restart state after an interrupted transaction;
- local database rollback when a newer externally retained checkpoint exists;
- selector-result substitution after the decision cutoff;
- cumulative-object and full-history-registry scale regressions.

It does not establish that the upstream provider was truthful, that the
collector host clock was correct beyond its declared uncertainty, that an
execution venue would fill an order, or that an optimized index is immune to
a malicious process with unrestricted database-file access. A stronger
malicious-index threat model would require authenticated ordered-map or range
proofs at decision time and must be frozen separately.

## Proposed record graph

```text
PhysicalScopeManifestV4
  ├─ ProviderAdapterPolicyV3/V4 references
  ├─ concrete InstrumentMapping reference
  ├─ source member and protocol lineage
  └─ disposition, epoch, selector, health, and retention rules

CaptureSegmentV3/V4
  └─ exact ProviderMessageEnvelope occurrences
       └─ MessageDispositionV4 (exactly one per occurrence)
            ├─ zero or more ObservationDerivation records
            └─ zero or more ObservationRevision records

ordered MessageDispositionV4 identities
  → EvidenceEpochHeadV4 transitions
  → EvidenceEpochSealV4
  → EpochLogTransitionV4

latest sealed-epoch log + current open-epoch head
  → EvidenceCutoffV4
  → DependencySelectionProofV4
  → SelectionResultChunkV4/result root
  → InformationSet/feature derivation equality
  → PhysicalEvidenceGate PASS or typed ABSTAIN
```

Names and version numbers in this document are provisional. The implemented
names must be frozen together with exact canonical schemas.

## `PhysicalScopeManifestV4`

The scope manifest defines one ordered physical-evidence stream. Proposed
fields are:

```text
physical_scope_manifest_id
source_member_key
instrument_mapping_id
provider_id / venue_id / environment_id
asset_id / concrete_contract_id / timeframe_id
primary_adapter_policy_id
ordered supporting adapter policy IDs and roles
calendar_manifest_id
protocol_lineage_id
scope_ordering_policy_id
disposition_policy_id
health_policy_id
selection_query_spec_id
hash_algorithm_id = RFC9162_SHA256
epoch_leaf_capacity = 4096
live_selection_retention_seconds
frozen_at
```

The exact scope key remains unresolved. The preferred direction is to bind the
concrete instrument, source member, primary policy, supporting-policy set,
calendar, and protocol lineage without binding an ephemeral collector boot.
Collector boots and connections remain observations inside the stable scope.

The authoritative ledger writer assigns a single monotonic
`scope_message_sequence`. Provider sequence, collector-local sequence,
connection generation, boot ID, receipt wall time, and monotonic time are
preserved rather than substituted for that ledger order.

## `MessageDispositionV4`

Every captured provider-message occurrence must have exactly one immutable
disposition in the same physical scope. Proposed fields are:

```text
message_disposition_id
physical_scope_manifest_id
scope_message_sequence
message_receipt_id
capture_segment_id
raw_capture_receipt_sequence
raw_capture_receipt_hash
adapter_policy_id
parser_release_id
outcome
reason_code
health_severity
duplicate_of_message_receipt_id? 
ordered observation_derivation_ids
ordered observation_revision_ids
output_count
output_root
classified_at
```

The initial outcome vocabulary proposed for freezing is:

- `EMITTED_OBSERVATION`;
- `DUPLICATE_NO_CHANGE`;
- `CONTROL_NO_OBSERVATION`;
- `MALFORMED_REJECTED`;
- `POLICY_REJECTED`;
- `STALE_REJECTED`;
- `CONFLICTING_DUPLICATE_REJECTED`.

Provisional messages are observations rather than ignored messages. A
provisional kline push emits a provisional revision; a later confirmed message
emits a completed successor. An exact equivalent duplicate may produce
`DUPLICATE_NO_CHANGE`, but it must bind the earlier occurrence and an exact
equivalence rule. A conflicting duplicate is not silently deduplicated.

Disposition records are immutable. Reinterpreting an old message with new
parser behavior must create a new adapter/parser policy lineage. It must not
rewrite the historical classification and must not manufacture prospective
availability.

Each disposition becomes one evidence leaf. The provisional leaf construction
is:

```text
leaf_input = canonical_json({
  "domain": "RiskYieldMMPhysicalDispositionLeafV1",
  "physical_scope_manifest_id": scope_id,
  "scope_message_sequence": sequence,
  "message_disposition_id": disposition_id
})

leaf_hash = SHA256(0x00 || leaf_input)
node_hash = SHA256(0x01 || left_hash || right_hash)
```

The domain string, byte encoding, integer representation, empty-tree hash, and
test vectors must be frozen before implementation.

## `EvidenceEpochHeadV4`

An open epoch is a bounded sequence of at most 4,096 disposition leaves.
Proposed head fields are:

```text
evidence_epoch_head_id
physical_scope_manifest_id
epoch_sequence
epoch_id
first_scope_message_sequence
tree_size
tree_root
processed_through_scope_message_sequence
cutoff_global_sequence
cutoff_receipt_hash
parent_evidence_epoch_head_id?
assembled_at
```

Heads are append-only transitions under semantic compare-and-swap. The current
head is found through an indexed transition rather than an updated mutable row.
The canonical object remains constant-size because it stores a root and count,
not leaf IDs or a frontier array that grows with history.

The epoch identity and boundary remain unresolved. The preferred candidate is
a maximum of 4,096 leaves because it is a power of two and gives a short,
predictable proof. Full epochs close deterministically at capacity. Partial
seals should be permitted only for frozen reasons such as policy rotation,
controlled shutdown, migration, or permanent source retirement.

## `EvidenceEpochSealV4`

The seal finalizes one epoch without changing prior heads:

```text
evidence_epoch_seal_id
physical_scope_manifest_id
epoch_sequence
epoch_id
final_epoch_head_id
first_scope_message_sequence
last_scope_message_sequence
tree_size
tree_root
parent_evidence_epoch_seal_id?
close_reason
sealed_at
```

The seal transaction must prove:

- exact sequence continuity;
- no duplicate leaf index or disposition;
- the final root recomputes from immutable stored hashes;
- every raw message through the seal boundary has one disposition;
- every disposition output references registered canonical records;
- the predecessor seal is the active scope seal;
- the partial-seal reason is allowed when `tree_size < 4096`.

## `EpochLogTransitionV4`

Sealed epoch identities become leaves in a second per-scope RFC9162_SHA256
tree. Proposed transition fields are:

```text
epoch_log_transition_id
physical_scope_manifest_id
appended_epoch_sequence
appended_evidence_epoch_seal_id
previous_epoch_log_size
previous_epoch_log_root
new_epoch_log_size
new_epoch_log_root
consistency_path
parent_epoch_log_transition_id?
cutoff_global_sequence
cutoff_receipt_hash
built_at
```

The seal identity is known before it is appended to the outer tree, avoiding a
circular identity. The transition proves the new outer root is an append-only
extension of the previous advertised root.

Epoch sealing, the outer transition, and rollover authorization should be one
specialized SQLite transaction. If the first implementation cannot issue all
corresponding ledger receipts atomically, ingestion must stop until an
idempotent recovery completes the exact transition; it must never skip a
half-sealed epoch.

## `EvidenceCutoffV4`

`EvidenceCutoffV4` is the constant-size replacement for the cumulative V3.3
prefix. Proposed fields are:

```text
evidence_cutoff_id
physical_scope_manifest_id
adapter and supporting policy IDs
source_member_key
instrument_mapping_id
ledger_id
cutoff_global_sequence
cutoff_receipt_hash
knowledge_cutoff_ts
latest_epoch_log_transition_id?
sealed_epoch_log_size
sealed_epoch_log_root
open_epoch_head_id?
open_epoch_sequence?
open_epoch_tree_size
open_epoch_tree_root
raw_message_high_water_sequence
processed_disposition_high_water_sequence
current_required_status_revision_id?
vintage
health
health_reason_codes
event_time_watermark
health_valid_until
assembled_at
parent_evidence_cutoff_id?
```

A healthy cutoff must establish at least:

```text
raw_message_high_water_sequence
  == processed_disposition_high_water_sequence

no missing raw scope sequence
no duplicate disposition scope sequence
no unresolved disposition with halt severity
required current status is trading-eligible and fresh
all selected observations are complete and available by the cutoff
cutoff receipt was registered before the cutoff knowledge clock
health_valid_until has not expired
```

The target canonical size is no more than 16 KiB and must remain invariant
with elapsed history. This threshold is provisional until an exact schema and
object-budget test are frozen.

## `DependencySelectionProofV4` and result chunks

The selector proof must bind the algorithm, not merely selected IDs:

```text
dependency_selection_proof_id
observation_selection_policy_id
selection_query_spec_id
evidence_cutoff_id
decision_cutoff_ts
anchor_ts
searched_lower_bound_ts
searched_upper_bound_ts
requested_count
selected_result_count
selected_result_root
ordered selection_result_chunk_ids
abstained
reason_codes
computed_at
valid_until
```

`ObservationSelectionPolicyV4` must be directly referenced by the protocol or
dependency slot so a portable record cannot substitute a different selector
that happens to pass local compare-and-swap checks.

Large results must not recreate the cumulative-object problem.
`SelectionResultChunkV4` should contain a fixed maximum, provisionally 256,
ordered revision IDs plus its ordinal and chunk hash. The selection result root
commits the ordered chunk sequence. InformationSet and feature-derivation
records bind the same result count and root rather than embedding tens of
thousands of raw IDs.

The chunk size, tree construction, and equality rules remain unresolved and
must be included in object-budget tests.

## Causal selector specification

Every candidate row must satisfy both semantic and ledger cutoffs:

```text
revision_receipt_sequence <= cutoff_global_sequence
available_at_us <= knowledge_cutoff_us
```

The second predicate alone is insufficient because a late-appended record
could claim an earlier availability timestamp. The first predicate alone is
insufficient because a registered record could represent information not yet
semantically available at the decision cutoff.

The selector must then apply the frozen:

- source member and concrete market scope;
- observation kind and name;
- completed-state requirement;
- exact/latest/trailing anchor semantics;
- interval and anchor lag;
- maximum age;
- requested count and continuity;
- active revision head as of both cutoffs;
- current status eligibility;
- tie-break order.

The current preferred active-head rule is: a revision remains active at cutoff
only when no registered successor satisfies both cutoff predicates. The exact
SQL and tie-break comparator must be hashed into `selection_query_spec_id`.

An ordinary RFC 9162 inclusion proof demonstrates that a committed leaf is in
a tree. It does not prove that no lexicographically or temporally preferable
candidate was omitted. In the initial design, exact selection is established
by deterministic typed SQL plus replay verification over canonical records.
The proof commits the exact ordered result and query specification for later
recomputation.

If the threat model requires a standalone third party to verify range
completeness without the ledger/index, implementation must pause until a
reviewed authenticated ordered map or range-commitment scheme is selected.

## Typed SQLite projection

Canonical ledger objects remain the semantic source of truth. Typed tables are
deterministic, append-only projections used for indexed validation and
selection. Each projection row must bind its source object identity/content
hash and receipt sequence so a streaming verifier can prove a bijection.

Proposed core tables are:

```text
physical_scopes_v4
capture_segments_v4
physical_messages_v4
message_dispositions_v4
disposition_outputs_v4
observation_revisions_v4
epoch_leaves_v4
epoch_hashes_v4
epoch_head_transitions_v4
epoch_seals_v4
epoch_log_hashes_v4
physical_verification_anchors_v4
```

Storage conventions proposed for freezing:

- SQLite `STRICT` tables;
- 32-byte BLOB identities and digests in projections;
- exact reversible conversion between canonical lowercase hex and BLOB;
- signed 64-bit integer UTC microseconds for searchable wall clocks;
- signed 64-bit integer nanoseconds only for collector monotonic clocks;
- enum encodings frozen by schema version;
- append-only `UPDATE` and `DELETE` rejection triggers;
- foreign keys enabled;
- application schema fingerprint checked on every open;
- no floating-point timestamps or prices in the evidence projection.

`WITHOUT ROWID` may reduce space for composite primary keys, but SQLite
documents it as an optimization rather than a semantic feature. Each proposed
use must be justified by benchmark and query plan before freezing.

### Proposed message and disposition keys

```sql
PRIMARY KEY (physical_scope_manifest_id, scope_message_sequence)

UNIQUE (
    physical_scope_manifest_id,
    message_receipt_id
)
```

The same composite primary key on message and disposition tables establishes
the exact-one correspondence. The verifier additionally proves contiguous
scope sequences and matching message identities.

### Proposed observation indexes

```sql
CREATE INDEX observation_parent_asof_v4
ON observation_revisions_v4(
    parent_observation_revision_id,
    available_at_us,
    receipt_sequence
)
WHERE parent_observation_revision_id IS NOT NULL;

CREATE INDEX observation_exact_asof_v4
ON observation_revisions_v4(
    source_member_key,
    observation_key,
    available_at_us,
    receipt_sequence
);

CREATE INDEX observation_completed_bar_selection_v4
ON observation_revisions_v4(
    source_member_key,
    bar_close_us DESC,
    available_at_us DESC,
    observation_revision_id DESC,
    receipt_sequence
)
WHERE observation_kind = 'BAR'
  AND completion_state = 'COMPLETE';

CREATE INDEX observation_status_asof_v4
ON observation_revisions_v4(
    physical_scope_manifest_id,
    observation_name,
    available_at_us DESC,
    receipt_sequence DESC
)
WHERE observation_kind = 'MARKET_STATUS';
```

The final column order depends on actual selector predicates and must be
accepted using `EXPLAIN QUERY PLAN` plus measured workloads. SQLite partial
indexes reduce storage and write work only when the query predicate matches
the index predicate closely; they must not be assumed effective without plan
evidence.

### Proposed epoch keys

```sql
PRIMARY KEY (
    physical_scope_manifest_id,
    epoch_sequence,
    leaf_index
)

PRIMARY KEY (
    physical_scope_manifest_id,
    epoch_sequence,
    stored_hash_index
)
```

Only finalized subtree hashes should be stored. The current open-tree root is
reconstructed from the stored hash frontier and compared with the latest
epoch-head transition. A transition should be recorded per committed
normalization batch, not per leaf, unless performance evidence justifies the
extra receipts.

## Write transactions

The proposed writer API separates raw durability from normalization while
keeping each logical batch atomic:

```text
append_capture_segment()
append_normalization_batch()
seal_epoch_and_advance_outer_log()
append_evidence_cutoff()
```

### `append_capture_segment()`

In one `BEGIN IMMEDIATE` transaction:

1. validate the capture object and partition/connection lineage;
2. append its canonical object and receipt;
3. assign contiguous scope message sequences in envelope order;
4. insert typed segment and message rows;
5. commit using the certified journal/synchronous mode.

No disposition or normalized observation is claimed inside the raw transaction.
This preserves the meaning of durable raw receipt.

### `append_normalization_batch()`

After raw durability, one transaction:

1. loads undisposed messages through indexed keys;
2. runs the frozen parser/normalizer;
3. validates derivations and immutable revisions;
4. registers their canonical objects and sequential receipts;
5. registers exactly one disposition for each input message;
6. inserts typed projection rows and disposition outputs;
7. appends ordered disposition leaves and stored Merkle hashes;
8. registers the new constant-size epoch head;
9. commits atomically under one batch idempotency identity.

A failed transaction exposes none of these rows. A retry must reproduce the
same identities and root.

### `seal_epoch_and_advance_outer_log()`

One transaction validates the final open head, registers the seal, appends the
seal leaf and stored outer-tree hashes, verifies the consistency proof, and
registers the new outer-log transition. The next epoch cannot become
authoritative until this commits.

### `append_evidence_cutoff()`

Under the writer lock, this operation reads the typed high-water marks and
active status, freezes the global receipt cutoff, proves exact raw/disposition
coverage, computes health and validity, and appends one constant-size cutoff.
Any raw capture committed before that cutoff but lacking a disposition forces
abstention.

## Crash and restart semantics

The required transactional outcomes are:

| Failure point | Required visible state after restart |
|---|---|
| Before transaction commit | None of the batch is visible |
| After successful commit | Object, receipt, typed rows, Merkle hashes, and head transition are all visible |
| Raw capture committed but normalization absent | Raw rows remain durable; health fails closed until deterministic recovery classifies them |
| During epoch seal transaction | Either the prior open epoch remains active or the seal and outer transition are both complete |
| Retry after uncertain acknowledgement | Idempotency returns/reconstructs the exact committed result; it never creates a duplicate scope sequence |

Restart procedure:

1. preserve and allow SQLite to recover its journal/WAL sidecars;
2. validate filesystem type, owner, mode, lock behavior, journal mode,
   synchronous setting, schema fingerprint, foreign keys, and `STRICT`
   integrity checks;
3. load the newest externally retained signed verification checkpoint;
4. reject a local ledger older than that checkpoint;
5. verify the checkpoint signature and bound physical-state root;
6. stream-verify only the suffix after the checkpoint;
7. reconstruct affected per-scope Merkle frontiers and compare heads;
8. resume undisposed messages in scope order;
9. keep trading/paper promotion disabled until health and verification pass.

A locally stored verification cursor is not a trust anchor. The external
checkpoint must bind at least:

```text
ledger ID and global sequence/root
channel roots
physical projection schema fingerprint
validator release hash
per-scope epoch/log state root
checkpoint time and signing key ID
```

If no trusted checkpoint is available, the writer must either perform a full
genesis verification or remain non-authoritative. A periodic offline full scrub
is still required because suffix verification trusts the externally anchored
prefix.

Application fault injection and `SIGKILL` tests do not simulate every power,
filesystem, controller, or hostile-file-write failure. Deployment remains
conditional on a certified local filesystem and conservative SQLite durability
settings.

## Streaming verification

The verifier must not materialize a full Python registry. It should process
receipts and typed rows in order while retaining only:

- the current global and per-channel receipt heads;
- active semantic-head identifiers required for the suffix;
- one bounded Merkle frontier per active scope/epoch;
- the current outer epoch-log frontier per scope;
- raw/disposition coverage high-water marks;
- the active status and revision heads needed by the suffix;
- verification counters and the latest trusted anchor.

Per-object graph validation should use primary-key/index lookups. Full canonical
objects are parsed once in the stream, their typed projection is compared, and
then they are discarded from memory.

Provisional complexity targets are:

```text
append B dispositions: O(B log 4096) worst-case, amortized O(B)
open epoch frontier:   no more than approximately 13 hashes
epoch inclusion proof: O(log 4096)
outer consistency:     O(log sealed_epoch_count)
evidence cutoff:       O(1) identity/root fields, <= 16 KiB target
selection:             O(log N + k + correction checks)
suffix verification:  O(delta)
full verification:    O(N) time, O(active scopes * log 4096) memory
```

These are algorithmic acceptance properties, not measured results. Instrumented
operation counters and elapsed-time scaling must verify them.

## Selection retention

The provisional initial live-selection horizon is 35 calendar days: 30 days of
intended context plus five days of correction and operational margin. This
value has not been frozen against the final feature lookbacks and may change.

Canonical raw messages, dispositions, revisions, epoch seals, and checkpoints
remain in the immutable audit ledger or an independently verified archive.
The live horizon limits decision queries; it is not permission to delete audit
history.

A selection policy must abstain when:

```text
anchor lag
+ requested interval span
+ allowed observation age
+ required correction/status margin
```

exceeds its frozen live retention. Longer-horizon model state should be emitted
as a separately proved causal derived observation rather than silently reading
an unbounded raw prefix.

Archive rotation, retention duration, and whether old typed indexes remain in
the live SQLite file are unresolved. Any archive/prune design must first prove
the archived bytes, roots, signed checkpoints, and retrieval path.

## Migration from V3.3

Migration must be an append-only cross-lineage replay, not an in-place schema
rewrite.

1. Stop V3.3 prospective writes at a declared cutover.
2. Run complete V3.3 structural verification.
3. Create and externally retain a final signed V3.3 checkpoint.
4. Start a new V3.4 ledger schema and validation lineage.
5. Register `V33BoundedEpochMigrationManifestV4`, binding:
   - old ledger ID, schema, validation version, checkpoint ID, sequence, and
     global/channel roots;
   - new ledger ID and genesis;
   - migration code/release hash;
   - scope mapping and expected object/message/revision counts;
   - migration start/completion clocks.
6. Replay canonical capture segments in old receipt and envelope order.
7. Assign new scope sequences deterministically.
8. Replay the existing exact raw-message/disposition relation into the V4
   vocabulary and verify every referenced derivation/revision. A pre-disposition,
   unsupported, or ambiguous old record causes migration failure, not guessed
   output.
9. Rebuild typed projections, evidence epochs, seals, and result roots.
10. Compare old and new exact/latest/trailing selections at deterministic
    sampled cutoffs.
11. Sign and externally retain the new migrated checkpoint.
12. Begin prospective capture with a new collector boot and new live epoch.

Historical migration preserves the original vintage and clocks. It can never
create `PROSPECTIVE_LIVE`, prove first-seen availability, or authorize live
trading. V3.3 files remain immutable read-only evidence for their original
verifier.

## Acceptance gates

No stage is accepted merely because unit tests pass. The exact workload seed,
message mix, batch sizes, filesystem, SQLite build, journal mode, synchronous
mode, CPU, RAM, storage device, Python version, and package lock must be
recorded with every performance artifact.

### 10,000-event deterministic correctness gate

Purpose: prove content identity, causal selection, boundary behavior, and
tamper rejection before performance optimization.

Required workload:

- multiple physical scopes and both primary/status messages;
- at least two complete epoch boundaries;
- provisional updates followed by completion;
- exact equivalent duplicates and conflicting duplicates;
- malformed, unsupported, stale, and policy-rejected messages;
- status transitions to and from trading halt;
- reconnects and collector boot transitions;
- late corrections with revision successors;
- selection modes exact/latest/trailing;
- batch sizes 1, 17, and 256 over identical ordered input.

Acceptance:

- identical canonical IDs, epoch roots, outer roots, cutoffs, and selection
  result roots across batching strategies;
- published/frozen Merkle vectors pass at sizes 0, 1, 2, 3, 4,095, and 4,096;
- every decision cutoff agrees with an independent slow canonical replay
  selector;
- zero raw messages without exactly one disposition;
- zero duplicate scope sequences or leaf indexes;
- every healthy/unhealthy result matches the frozen severity policy;
- every cutoff remains below the frozen constant object budget;
- mutation/deletion/reorder/substitution tests for messages, dispositions,
  outputs, revisions, leaves, internal nodes, heads, seals, outer transitions,
  cutoffs, chunks, and consistency paths fail closed;
- timestamp-shift and receipt-sequence-shift leakage controls fail closed.

### 100,000-event restart and scaling gate

Purpose: reject quadratic append/reopen behavior and prove transactional
recovery.

Required workload:

- multiple scopes and at least 24 epoch rollovers;
- deterministic crashes after every writer fault-injection stage;
- repeated subprocess `SIGKILL` at randomized transaction points;
- retry after uncertain commit acknowledgement;
- reconnect, correction, duplicate, malformed, and status-halt events;
- signed checkpoints leaving suffixes of different lengths;
- clean and crash/retry runs from the same seed.

Provisional acceptance:

- clean and crash/retry runs end with identical ledger, epoch, outer-log,
  cutoff, and selection roots;
- no half-visible capture, normalization, or epoch-seal transaction;
- suffix verification and full verification end at identical trusted roots;
- query-plan artifacts show indexed search for every selector and status query,
  with no unapproved full scan;
- last-decile per-message append cost is no more than 25% above first-decile
  cost after removing fixed warm-up;
- the 100,000/10,000 full-verification time ratio is at most 15 on the frozen
  host, rejecting obvious quadratic scaling;
- p99 selection is provisionally below 25 ms;
- p99 cutoff construction is provisionally below 50 ms;
- restart verification of a 10,000-receipt suffix is provisionally below
  30 seconds;
- resident memory does not grow linearly with processed history;
- no canonical object exceeds its frozen budget.

Absolute latency thresholds must be re-frozen if the declared reference
hardware shows they are unrealistic, but they may not be relaxed merely to
hide a full scan or unbounded algorithm.

### Accelerated 30-day release soak

The first mandatory pilot workload is two assets at one provider-message
occurrence per second for 30 calendar days:

```text
2 assets * 2,592,000 seconds = 5,184,000 primary occurrences
```

Status, reconnect, correction, and fault records are additional. The workload
must use realistic canonical raw-message sizes rather than tiny placeholder
objects. Its deterministic adversarial mix must include:

- per-second provisional bar updates and provider confirmation;
- exact duplicate occurrences;
- conflicting duplicates;
- malformed and rejected messages;
- late corrections;
- periodic instrument status observations;
- bounded trading-halt intervals;
- network disconnect/reconnect and resubscription;
- collector process restart and boot change;
- transaction faults and process termination;
- periodic signed external checkpoints;
- selection decisions across the full configured horizon.

Provisional acceptance:

- zero selection mismatch over at least 10,000 deterministic sampled cutoffs
  against the independent slow replay;
- zero unclassified or double-classified raw occurrences;
- zero sequence, epoch, revision-head, or status-state divergence;
- clean and crash/retry final roots are identical;
- no object exceeds the canonical budget;
- cutoff size remains constant with elapsed history;
- p99 selector remains below 25 ms on the frozen reference host;
- p99 raw-capture-to-disposition commit remains below 500 ms at four times the
  declared live aggregate rate;
- recovery from a 10,000-receipt suffix remains below 30 seconds;
- a complete 5.184-million-event scrub remains below 30 minutes;
- peak RSS remains below the frozen cap, provisionally 1 GiB, and shows no
  material first-to-last-decile slope after cache warm-up;
- typed projection plus Merkle overhead is provisionally below 3 KiB per raw
  occurrence, reported separately from canonical raw and observation blobs;
- database size, bytes per message, write amplification, checkpoint size, and
  proof size are reported rather than hidden in a pass/fail total.

A separate accelerated 100-scope capacity burst is required. A two-asset
30-day soak establishes duration for the pilot, not broad multi-asset capacity.
Its provisional target is sustained processing at least four times the
configured 100-scope live peak without violating the same decision and health
latency gates.

No soak result authorizes trading. It only establishes that the evidence and
selection machinery behaved as specified under the tested workload.

## Implementation sequence

The provisional safest order is:

1. freeze physical scope ordering, disposition vocabulary, and selector query;
2. implement typed message/disposition/revision projections and independent
   slow-reference comparisons;
3. implement pure RFC9162_SHA256 leaf/node/root/inclusion/consistency functions
   against frozen vectors;
4. add incremental stored hashes and fixed evidence epochs;
5. add epoch seals and the outer epoch log;
6. replace cumulative prefixes with constant-size cutoffs;
7. add chunked selection-result commitments and InformationSet equality;
8. remove full-registry reconstruction from the physical append path;
9. add signed physical-state checkpoints and suffix verification;
10. implement crash/retry recovery and migration tooling;
11. pass 10,000-event correctness before optimization;
12. pass 100,000-event restart/scaling before live capture integration;
13. pass the accelerated 30-day and 100-scope gates before paper/live promotion
    is considered.

Each step must retain a slow, independently structured reference path for
falsification. Removing the reference implementation to improve benchmark
numbers would invalidate the acceptance design.

## Decisions that must be frozen before code

1. **Physical scope key:** exact policy, mapping, source-member, calendar, and
   protocol fields; behavior when supporting status policies rotate.
2. **Authoritative total order:** how the ledger writer arbitrates concurrent
   collectors and proves one active collector/lease per scope.
3. **Hash specification:** SHA-256 domains, canonical leaf bytes, integer
   encoding, empty root, stored-hash layout, inclusion and consistency vectors.
4. **Epoch boundary:** 4,096-leaf capacity, epoch identity, and allowed partial
   close reasons.
5. **Disposition contract:** enum, reason codes, severity, duplicate
   equivalence, maximum outputs, and whether any classification can be revised.
6. **Provisional semantics:** exact revision chain and health behavior for
   multiple in-progress pushes before confirmation.
7. **Selector contract:** both cutoffs, anchor, continuity, active-head rule,
   tie break, correction semantics, status dependency, and query-spec identity.
8. **Portable proof requirement:** whether local deterministic audit is enough
   for V3.4 or an authenticated ordered range/non-inclusion proof blocks code.
9. **Protocol binding:** direct selector-policy ID and result-root equality in
   dependency slots, InformationSets, feature derivations, and gates.
10. **Chunking:** selection result ordering, chunk size, chunk tree, object
    limits, and partial retrieval.
11. **Retention:** validate or replace the provisional 35-day live horizon;
    define immutable archive retention and retrieval.
12. **SQLite representation:** BLOB IDs, timestamp precision, enum encoding,
    table keys, indexes, `WITHOUT ROWID` choices, and schema fingerprint.
13. **Transaction boundaries:** raw versus normalization durability, multi-object
    batch receipts, epoch sealing, idempotency, and backpressure.
14. **Checkpoint trust:** signed physical-state payload, frequency, external
    storage, key rotation, rollback detection, and maximum suffix length.
15. **Migration:** exact old checkpoint, ambiguity policy, replay ordering,
    comparison sample, and prospective cutover boot.
16. **Derived higher timeframes:** whether deterministic HTF revisions enter
    the same evidence-atom log or a separately specified derived stream.
17. **Acceptance environment:** hardware, filesystem, SQLite/Python builds,
    durability mode, message mix, seeds, and absolute/relative thresholds.

## Explicit non-guarantees and exit boundary

Even after this proposal is frozen and all acceptance gates pass, it would
establish only a bounded, causal, append-auditable market-data evidence path
under the tested assumptions. It would not establish:

- that the provider's market data is correct;
- that provider timestamps are trustworthy beyond measured uncertainty;
- that a model has stable predictive information;
- that probability scores are calibrated;
- that an order will fill at the assumed price;
- that fees, spread, slippage, latency, impact, and adverse selection permit
  positive net PnL;
- that future regimes resemble the soak or backtest periods;
- that a strategy is profitable or safe for live capital.

V3.4 can leave provisional status only after the schemas and decisions above
are frozen, the implementation and migration are complete, independent review
finds no open P0/P1 causal or integrity issue, all three soak tiers pass on a
declared environment, the paper/live outer gate forbids every legacy bypass,
and the resulting evidence is captured prospectively. Until then, this is an
architecture proposal and research artifact only.
