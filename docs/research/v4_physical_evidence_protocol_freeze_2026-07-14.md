# V4 physical-evidence protocol freeze

**Date:** 2026-07-14

**Status:** Frozen for the first functional vertical slice

**Tracking:** RIS-271

**Predecessor:** fixture-backed V3.3 physical-evidence reference

## V4.1 supersession checkpoint

This document remains the V4.0 storage-and-commitment decision record. New
selector ledgers use the fresh-genesis
[V4.1 causal-selector protocol](v4_1_causal_selector_protocol_freeze_2026-07-14.md),
whose schema/profile/query identities supersede the V4.0 identifiers for new
ledgers. Health-transition and physical-gate authority remain later subgates.

## Decision

V4 uses one continuous, ordered, per-scope `RFC9162_SHA256` transparency
tree. It does not use fixed inner epochs or an outer epoch-seal tree.

```text
exact raw capture
-> exactly one immutable V3-compatible disposition per occurrence
-> canonical V4 ledger record and typed SQLite projection in one transaction
-> continuous per-scope RFC9162 disposition tree
-> constant-size tree head and evidence cutoff
-> indexed dual-cutoff selection
-> independent V3 slow-replay comparison
```

The continuous tree and the global ledger receipt chain have different jobs.
The tree commits the ordered disposition stream for one immutable physical
scope. The receipt chain orders all ledger operations across scopes. Neither
one proves that an SQL range query is complete. V4.0 establishes selection
completeness through deterministic typed queries plus independent canonical
replay; it makes no standalone authenticated-range or malicious-index claim.

## Implementation checkpoint

The first storage-and-commitment slice is implemented in parallel with, and
without mutating, the V3.3 reference oracle:

- `riskyieldmm/trading/transparency_log.py`: exact RFC 9162 empty, leaf, node,
  root, inclusion, consistency, incremental-frontier, and stored-hash logic;
- `riskyieldmm/trading/physical_evidence_v4.py`: immutable scope, physical
  message, deterministic disposition, tree-head, and cutoff contracts;
- `riskyieldmm/trading/physical_projection_v4.py`: one-database `STRICT`
  canonical ledger plus typed projections, `BEGIN IMMEDIATE` transactions,
  deterministic idempotency, immutable triggers, receipt chain, schema
  fingerprint, exact-coverage cutoff construction, and full-genesis replay;
- `tests/test_trading_transparency_log.py`,
  `tests/test_trading_physical_evidence_v4.py`, and
  `tests/test_trading_physical_projection_v4.py`: 51 focused tests, including
  batch sizes 1/17/256 over 257 messages, fault rollback, reopen, strict type
  rejection, immutable-row rejection, duplicate/release attacks, future
  watermark rejection, query-index use, and canonical/typed/tree replay.
- repository-wide compatibility gate: `1297 passed, 32 skipped`; the V3.3
  reference and all prior contract tests remain green.

Frozen implementation identifiers:

```text
protocol_profile_id = 77225c941ac5fd9a1e955bf8c062d6bbfe22f7110034f85a159164aa02da9cee
schema_fingerprint  = 0379b4cf1e5711fa4de60e5fe49fb828218ec470fb145da97b1725a314a5554c
```

This checkpoint is a correctness store, not the live capture/normalization
writer. It has no causal observation selector, status/feed-health transition
reducer, V4 physical gate, signed external anchor, migration authority, or
paper/live execution path.

## Why the provisional epoch design was rejected

The two-level 4,096-leaf proposal was useful for exposing the scale problem,
but primary-source review did not establish an advantage over one continuous
RFC9162 tree:

- both designs have an `O(log N)` frontier and membership proof;
- both have a constant-size `(tree_size, tree_root)` advertised head;
- at about 5.2 million leaves, both need about 23 proof hashes;
- stored hashes can be partitioned into authenticated fixed-size tiles without
  resetting the tree;
- epochs add partial-seal policy, rollover atomicity, open-versus-sealed state,
  a second consistency layer, and recovery from half-completed transitions.

Fixed epochs remain a benchmark challenger. They may be reconsidered only if
measured repair, archive, or latency evidence outweighs their extra protocol
state. MMR remains postponed because the reviewed IETF document is an expired
individual draft. A hash chain remains complementary ordering, not a compact
membership structure.

## Frozen decisions

### 1. Scope identity

One immutable `PhysicalScopeManifestV4` binds:

- provider, venue, environment, asset, concrete contract, and timeframe;
- one exact primary adapter policy and its classifier-release hash;
- zero or one required instrument-status policy, paired with its classifier
  release;
- source-member, instrument-mapping, calendar, protocol-lineage, disposition,
  health, selector, and hash-specification IDs.

Collector boot and connection IDs are observations, not scope identity.
Rotating any bound policy, mapping, calendar, or protocol creates a new scope;
it never changes the meaning of an existing tree.

### 2. Total order and writer authority

V4.0 supports one serialized SQLite writer per ledger. Within a scope it
assigns `scope_message_sequence` by canonical capture receipt order and then
envelope ordinal. The sequence starts at one and has no gaps. Multi-host
consensus is out of scope. A later live writer must add a fenced collector
lease and reject overlapping authority.

### 3. Hash specification

The hash algorithm is SHA-256 with the RFC9162 construction:

```text
empty_root      = SHA256("")
leaf_hash(d)    = SHA256(0x00 || d)
node_hash(l, r) = SHA256(0x01 || l || r)
```

Trees are never padded and the last leaf is never duplicated. Application
leaf input is canonical UTF-8 JSON containing the frozen domain
`RiskYieldMMPhysicalDispositionLeafV4`, scope ID, scope sequence, and
disposition ID. Callers pass leaf input bytes, never a prehashed value, to the
public leaf API. Tree size is always authenticated with the root.

Wrapper semantics are:

- `(0, n)` consistency uses the exact empty root and an empty path;
- `(n, n)` requires equal roots and an empty path;
- reversed sizes are invalid;
- all hashes are exactly 32 bytes.

### 4. Continuous tree and stored hashes

Every accepted disposition adds exactly one leaf to one continuous per-scope
tree. Tree size equals the contiguous disposition high-water sequence. The
incremental frontier contains at most 53 hashes because V4 caps tree size at
`2^53 - 1`, the largest integer admitted by the existing canonical I-JSON
profile. This is stricter than SQLite's signed-integer limit and prevents a
second integer encoding from entering identity-bearing records.

Finalized subtree hashes are addressed by `(scope_id, level, subtree_index)`.
The initial database stores these hashes directly. The archive/export format
uses authenticated tiles with storage height four; serving height is a later
operational choice and does not alter tree identity.

### 5. Disposition contract

V4 retains all twelve implemented V3 outcomes without collapsing them:

```text
NORMALIZED_OBSERVATION
EXACT_DUPLICATE
CONTROL_SUBSCRIPTION_ACK
CONTROL_PONG
PROVIDER_ERROR
EXPECTED_INSTRUMENT_STATUS_ABSENT
MALFORMED_PAYLOAD
UNSUPPORTED_SCHEMA
OUT_OF_SCOPE
RECEIPT_LAG_REJECTED
CLOCK_ORDERING_REJECTED
CONTENT_CONFLICT
```

`NORMALIZED_OBSERVATION` has exactly one derivation and revision in V4.0.
Every other outcome has zero outputs. Exact duplicates bind the earliest exact
normalized occurrence in the same scope and adapter policy. Dispositions are
immutable and can never be reclassified in place. The classifier-result ID is
derived from the normalized semantic fields; callers cannot supply an opaque
identity. Projection admission rechecks the scope-bound classifier release,
rejects repeated normalized raw content, and independently verifies duplicate
lineage.

### 6. Provisional observations

Every distinct valid provisional push creates a provisional revision. Exact
raw duplicates create no revision. A completed revision may never regress to
provisional. Selection excludes provisional rows. Deterministic HTF
derivations belong to a separately versioned derived-evidence stream and do
not become provider-message leaves.

### 7. Selector contract

The initial selector supports completed 1-minute `EXACT_EVENT`,
`LATEST_AVAILABLE_ASOF`, and strict-grid trailing selection. Every selected
revision must satisfy both:

```text
receipt_sequence <= cutoff_global_sequence
available_at_us <= knowledge_cutoff_us
```

The active head is a revision with no successor satisfying both predicates.
The frozen tie break is bar close, availability, receipt sequence, and raw
32-byte revision ID. Initial result cardinality is at most 256.

### 8. Portable proof boundary

Local deterministic audit plus independent replay is sufficient for V4.0.
Ordinary Merkle membership does not prove non-inclusion or preferred-row
completeness. If a portable malicious-index threat model becomes mandatory,
implementation stops until an authenticated ordered-map or range-proof design
is separately reviewed and frozen.

### 9. Protocol binding

A post-manifest `PhysicalProtocolBindingV4` binds the exact protocol manifest,
feature schema, dependency slot, selector policy, and semantic query-spec ID.
V4 proof and gate records require exact cutoff, result-count, result-root, and
policy equality. V3 and legacy evidence cannot satisfy a V4 gate.

### 10. Result commitment

V4.0 permits one result chunk containing at most 256 ordered revision IDs.
Each result leaf binds its ordinal and revision ID under a separate application
domain. The proof binds one chunk ID, count, and result root. Abstention uses
count zero, no chunk, and the RFC9162 empty root. Larger results require a V4.1
protocol decision rather than another cumulative list.

### 11. Retention

The first slice performs no pruning. Canonical and projected history is kept
in full. A 35-day live query horizon remains provisional until Stage 3 freezes
accepted feature lookbacks plus correction and status margins. Archive and
deletion-proof design is required before Stage 7.

### 12. SQLite representation

- `STRICT` tables;
- 32-byte `BLOB` identities and digests with `typeof` and length checks;
- signed integer UTC microseconds and collector monotonic nanoseconds;
- textual enums with exact `CHECK` constraints;
- canonical decimal text, never floating-point evidence values;
- foreign keys enabled and verified on every connection;
- immutable `UPDATE` and `DELETE` rejection triggers;
- schema fingerprint verified on every open;
- ordinary rowid tables initially; `WITHOUT ROWID` is benchmark-only;
- local-filesystem WAL with `synchronous=FULL` only after runtime safety
  checks; rollback journaling remains the portable test default.

### 13. Transactions and idempotency

Raw capture and normalization are separate atomic transactions. Canonical V4
objects, receipts, typed projection rows, stored hashes, and the new tree head
must commit in the same V4 database transaction. Normalization has a
deterministic batch idempotency key. Operational processing timestamps remain
receipt metadata and cannot change semantic disposition leaves or final roots
across batching, retry, or restart.

### 14. Checkpoint trust

The first functional slice verifies from genesis. Before the 100,000-event
gate, a signed V4 anchor must bind the ledger root, schema fingerprint,
validator release, per-scope tree size/root, exact coverage high-waters, and
health-state root. The anchor is published only after database commit and is
retained outside the database. A local cursor is never a trust anchor.

### 15. Migration

The first slice starts from fresh V4 genesis. Later migration is append-only
replay from a fully verified, externally anchored final V3.3 checkpoint into a
new V4 ledger identity. Ambiguous or pre-disposition history fails migration.
Historical replay preserves its original vintage and can never create
prospective first-seen authority.

### 16. Higher timeframes

Provider-message dispositions and deterministic derived timeframes are
separate streams. A future HTF record binds the exact completed 1-minute input
root, child interval, correction policy, and derivation release. Missing,
provisional, or corrected children must fail or produce a new derived revision;
they are never silently forward-filled.

### 17. Acceptance environment

Functional vectors, seeds, canonicalization version, and dependency lock are
frozen with the first implementation. Hardware, filesystem, SQLite build,
journal mode, synchronization mode, and performance thresholds are frozen
before the 100,000-event gate. Thresholds may change only through a recorded
protocol revision, never merely because a run failed.

## Additional invariants

- Exact-one coverage is proved through count, minimum, maximum, contiguous-gap,
  shared-key, and message-identity checks. Matching high-water values alone are
  insufficient.
- A cutoff proves projection coverage and current health. A later selector
  proves that selected revisions are complete and eligible.
- V4.0 supports at most one required `INSTRUMENT_STATUS` authority.
- The event-time watermark is the greatest completed primary-bar close proven
  at cutoff, not a provider control, provisional timestamp, or rejected event.
- Cutoff receipt fields always refer to an already registered predecessor
  receipt, never to the cutoff's own future receipt.
- Semantic IDs exclude unconstrained assembly and processing wall clocks.
- Classifier releases are explicit immutable scope commitments, and classifier
  result IDs are recomputed rather than trusted as caller-selected hashes.
- Typed projection rows bind the canonical object identity, canonical content
  hash, and source receipt sequence.

## Research basis and evidence grade

- [RFC 9162, Certificate Transparency Version 2.0](https://www.rfc-editor.org/rfc/rfc9162.html)
  is the primary definition of the empty root, leaf/node domain separation,
  tree shape, inclusion proofs, and consistency proofs. It is an Experimental
  RFC: its algorithms are the frozen commitment baseline, not an endorsement
  of this repository's application protocol.
- [RFC 9942, COSE Receipts for RFC 9162](https://www.rfc-editor.org/rfc/rfc9942.html)
  is the Standards Track representation for signed RFC9162 receipts. V4 does
  not claim RFC 9942 conformance until its future COSE serialization and
  trivial-proof edge cases are implemented and tested.
- The official Go
  [`golang.org/x/mod/sumdb/tlog`](https://pkg.go.dev/golang.org/x/mod/sumdb/tlog)
  package and the
  [Go checksum-database design](https://go.googlesource.com/proposal/+/master/design/25530-sumdb.md)
  establish that a continuous RFC6962/9162-style tree can append with at most
  `1 + log2(N)` stored-hash work and can use authenticated tiles. This supports
  the continuous-tree baseline; it does not prove that this Python/SQLite
  implementation meets its latency or durability goals.
- SQLite's primary documentation for
  [STRICT tables](https://www.sqlite.org/stricttables.html),
  [transactions](https://www.sqlite.org/lang_transaction.html),
  [atomic commit](https://www.sqlite.org/atomiccommit.html), and
  [partial indexes](https://www.sqlite.org/partialindex.html) defines the
  implemented storage constraints and the tests still required. SQLite
  provides one-writer atomicity inside one database; it does not authenticate
  a malicious database or make external files part of the transaction.

These are established protocol and database mechanisms. Their composition,
leaf schema, health policy, selector, and trading use are repository-specific
engineering decisions that require the acceptance tests below. Fixed epochs,
MMR, portable authenticated range proofs, and COSE receipts remain unselected
or unimplemented alternatives—not hidden claims of equivalence.

## First-slice acceptance

The first functional slice must establish:

1. hard-coded RFC9162 vectors and independent slow/incremental equality;
2. inclusion and consistency rejection for mutated, missing, extra, reordered,
   wrong-sized, or cross-scope inputs;
3. batch invariance across batch sizes 1, 17, and 256;
4. exact raw-message/disposition coverage and contiguous scope sequences;
5. deterministic projection rebuild and canonical-to-typed bijection;
6. constant-size tree heads and cutoffs as history grows;
7. unchanged V3.3 tests as a compatibility gate;
8. no claim of range completeness from Merkle membership alone.

The causal SQL selector, health transitions, V4 physical gate, live
capture/normalization writer, non-semantic V3-disposition provenance
projection, signed anchors, migration, and 10k/100k/soak gates remain
subsequent RIS-271 milestones. None of these artifacts establishes live
readiness, predictive edge, execution quality, profitability, or safety for
capital.
