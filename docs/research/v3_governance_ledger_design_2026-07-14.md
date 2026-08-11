# V3 governance ledger: implemented design and remaining certification gates

- **Design reconciliation date:** 2026-07-14
- **Status:** latest documented hardening is implemented and the complete
  repository suite passes; not deployment certified
- **Implementation:** `riskyieldmm/trading/ledger.py`,
  `riskyieldmm/trading/ledger_signing.py`, and
  `riskyieldmm/trading/ledger_cli.py`
- **Applies to:** the V3 event contracts and experiment manifests exported by
  `riskyieldmm.trading`

The local governance-ledger API, SQLite schema, receipt chains, Ed25519 adapter,
checkpoint registration, two-checkpoint holdout authorization/seal protocol,
single-snapshot verifier, backup method, and read-only verification CLI now
exist. This document records what the code actually implements and separates it
from later production work.

It does **not** certify live deployment, historical first-seen truth, physical
holdout secrecy, external timestamping, crash/power-loss behavior on every
target filesystem, or predictive edge. The ledger is not yet connected to the
legacy Analyst or RPF execution pipelines.

## 1. Evidence labels

- **IMPLEMENTED** — behavior present in the current code and schema. Test status
  is stated separately; deployment certification remains a separate claim.
- **ESTABLISHED** — behavior documented by an official standard or primary
  product documentation.
- **CONDITIONAL** — a supported mode or future recommendation whose claim
  depends on stated operating conditions and acceptance tests.
- **LIMITATION** — something the current implementation does not establish or
  prevent.

These labels describe engineering evidence. They do not measure trading
quality or profitability.

## 2. Implementation summary

| Area | Current state | Evidence label |
|---|---|---|
| Authoritative store | One local SQLite database with `STRICT` tables and one process-held writer lock | **IMPLEMENTED** |
| Default durability | Rollback-journal `DELETE` mode with `synchronous=EXTRA` | **IMPLEMENTED** |
| Current WAL policy | Explicit WAL requests are rejected on the installed SQLite 3.51.1 runtime | **IMPLEMENTED / ESTABLISHED** |
| Ledger identity | Random 32-byte nonce plus creation time, schema/canonicalization/validation versions, journal mode, and object-size policy derive `ledger_id` | **IMPLEMENTED** |
| Atomic mutation | Explicit `BEGIN IMMEDIATE`; object/governance payload, receipt, and head transition commit together | **IMPLEMENTED** |
| Object bytes | Exact canonical UTF-8 JSON BLOB plus raw SHA-256 `content_hash`; native V3 identity and `record_hash` retained | **IMPLEMENTED** |
| Receipt ordering | One global chain and four channel chains: `MANIFEST`, `EVENT`, `LABEL`, `GOVERNANCE` | **IMPLEMENTED** |
| Heads | Latest immutable transition per `(head_type, semantic_key)`; no mutable active-head row | **IMPLEMENTED** |
| Staged source members | Immutable `SOURCE_BUNDLE_MEMBER_OBJECT` alternatives may coexist; bundle-lineage CAS selects the authoritative complete member set | **IMPLEMENTED** |
| Cross-record causal claims | Stable-member observation revisions and candidate-neutral vector positions remain immutable across otherwise distinct records | **IMPLEMENTED** |
| Idempotency | Caller key + canonical request hash; exact same-key replay returns the original receipt | **IMPLEMENTED** |
| Checkpoints | Ed25519 signature over a committed receipt prefix and all channel roots; checkpoint itself receives a governance receipt | **IMPLEMENTED** |
| External rollback evidence | Requires an externally retained checkpoint and its trusted public key | **CONDITIONAL / LIMITATION** |
| Verification coherence | One pinned SQLite read snapshot; exact application-schema fingerprint; receipt/operation-child bijections | **IMPLEMENTED** |
| Signature verification | A supplied trusted verifier checks every stored checkpoint; a detached external checkpoint additionally anchors a trusted prefix | **IMPLEMENTED / CONDITIONAL** |
| Trust report | Reports trusted checkpoint ID/sequence and the exact count of receipts after the trusted signed prefix | **IMPLEMENTED** |
| Holdout control | Effective holdout source/bundle/non-anchor-member receipts must follow the protocol receipt; latest pre-grant checkpoint authorizes one immutable exact protocol/split grant; only a registered, externally retained post-grant checkpoint seals it | **IMPLEMENTED** |
| Holdout blindness | No physical read prevention, partition fingerprint, read counter, or blind evaluator | **LIMITATION** |
| Verification CLI | `riskyieldmm-ledger verify`, optionally with external checkpoint JSON and public key | **IMPLEMENTED** |
| Automated test status | Complete repository `pytest -q`: `1151 passed, 32 skipped in 45.30s`; hardened ledger/CLI coverage included | **IMPLEMENTED** |
| Production certification | Fault, operational, external-anchor, key-lifecycle, and pipeline-integration gates remain | **CONDITIONAL** |

## 3. Storage profile and current SQLite decision

### 3.1 Runtime and journal mode

The active environment currently reports:

```text
Python 3.12.12
sqlite3.sqlite_version = 3.51.1
sqlite3.threadsafety = 3
```

**ESTABLISHED:** SQLite documents a rare WAL-reset corruption race in versions
3.7.0 through 3.51.2. It is fixed in 3.51.3 and later, with documented fixed
backports 3.44.6 and 3.50.7. The race requires WAL mode, multiple connections
in different threads/processes, and concurrent writing/checkpointing. See
[SQLite's WAL-reset notice](https://sqlite.org/wal.html#the_wal_reset_bug).

**IMPLEMENTED:** `V3GovernanceLedger` therefore defaults to:

```sql
PRAGMA journal_mode = DELETE;
PRAGMA synchronous = EXTRA;
PRAGMA foreign_keys = ON;
PRAGMA trusted_schema = OFF;
PRAGMA cell_size_check = ON;
PRAGMA mmap_size = 0;
PRAGMA busy_timeout = 5000;
```

Extension loading is disabled. Where Python/SQLite exposes defensive database
configuration, defensive mode is enabled and trusted-schema mode is disabled.

SQLite documents that `DELETE` mode commits by deleting the rollback journal,
and that `EXTRA` adds a directory sync after that unlink. This is why `EXTRA`,
not merely `FULL`, is used for the rollback-journal default. See the official
[journal and synchronous pragma documentation](https://sqlite.org/pragma.html#pragma_synchronous)
and [atomic-commit description](https://sqlite.org/atomiccommit.html).

**IMPLEMENTED:** WAL can be requested only when
`sqlite_wal_runtime_is_safe()` recognizes a fixed release. A WAL ledger uses
`synchronous=FULL`. Journal mode is persisted in immutable ledger metadata; a
later open must request the same mode.

**CONDITIONAL:** a fixed SQLite version is necessary but not sufficient to make
WAL the certified production mode. Switching the default still requires
checkpoint, long-reader, backup, concurrency, and crash tests.

### 3.2 Local writer and transaction boundary

**IMPLEMENTED:** a writable ledger:

- owns one SQLite connection opened with `isolation_level=None`;
- acquires a nonblocking `fcntl.flock()` on a private writer-lock file;
- before every mutation, revalidates the metadata-bound journal mode,
  `synchronous` level (`EXTRA` for `DELETE`, `FULL` for WAL), foreign-key
  enforcement, disabled trusted schema, and zero memory mapping;
- wraps every mutation in literal `BEGIN IMMEDIATE`, commit, and rollback;
- uses SQLite's five-second busy handler as the database-lock backstop;
- refuses to return a writable reopen until full local structural verification
  succeeds;
- validates rollback-journal/WAL sidecar ownership and permissions before the
  transaction and again immediately before commit.

SQLite documents that `BEGIN IMMEDIATE` starts a write transaction immediately
and may return `SQLITE_BUSY` if another writer is active. See
[SQLite transaction control](https://sqlite.org/lang_transaction.html).

There is no writer-queue service, batch append API, application retry loop, or
multi-host coordinator in the current implementation. “Single writer” means
one process holding the advisory lock and one owning connection. SQLite remains
the final transactional lock; the advisory lock coordinates compliant local
processes only.

## 4. Public API and persisted types

### 4.1 Main API

The implemented mutation and verification surface is:

```python
with V3GovernanceLedger(database_path) as ledger:
    receipt = ledger.append(record, idempotency_key="...")

    pre_grant_checkpoint = ledger.create_checkpoint(
        signer,
        idempotency_key="pre-grant-checkpoint",
    )

    grant = ledger.grant_final_holdout_evaluation(
        protocol_manifest_id=...,
        split_manifest_id=...,
        checkpoint_id=pre_grant_checkpoint.checkpoint_id,
        approval_hash=...,
        evidence_gate_hash=...,
        frozen_artifact_hash=...,
        external_anchor_hash=...,
        idempotency_key="...",
    )

    post_grant_checkpoint = ledger.create_checkpoint(
        signer,
        idempotency_key="post-grant-checkpoint",
    )
    # Retain this exact checkpoint JSON and its trusted key outside the DB.
    seal = ledger.verify_holdout_evaluation_seal(
        grant.grant_id,
        trusted_checkpoint=post_grant_checkpoint,
        verifier=trusted_public_key,
    )

    report = ledger.verify(
        trusted_checkpoint=post_grant_checkpoint,  # optional external copy
        verifier=trusted_public_key,                # required with checkpoint
    )

    backup_report = ledger.backup_to(new_database_path)
```

Read methods include `open_read_only()`, `get_record()`, `get_receipt()`,
`receipt_for_idempotency_key()`, and `active_head()`.

The exported evidence types are:

- `LedgerReceipt`;
- `LedgerChannelRoot`;
- `SignedLedgerCheckpoint`;
- `HoldoutEvaluationGrant`;
- `LedgerVerificationReport`;
- `HoldoutEvaluationSealReport`.

The signing module provides `Ed25519CheckpointSigner` and
`Ed25519CheckpointVerifier`. They implement the structural `CheckpointSigner`
and `CheckpointVerifier` protocols used by the ledger.

### 4.2 Accepted top-level V3 records

`append()` accepts exact instances of:

```text
SourceBundleMemberV3
SourceBundleV3
FeatureDependencySlotV3
FeatureDefinitionV3
FeatureSchemaV3
ImmutableManifestV3
InformationSetV3
PrimarySignalCandidateV3
CandidateFeatureMaterializationV3
EligibilityDecisionV3
DecisionEventV3
BarrierActivationV3
LabelOutcomeV3
EventDependenceAssignmentV3
```

`InformationDependencyV3` and `CostComponentV3` remain nested data inside their
owning canonical records; they are not independent ledger object kinds.

## 5. Implemented channels and semantic heads

### 5.1 Channel routing

| Channel | Content |
|---|---|
| `MANIFEST` | Typed source/feature evidence plus every `ImmutableManifestV3` kind |
| `EVENT` | information sets, primary candidates, candidate feature materializations, eligibility decisions, decision events, and barrier activations |
| `LABEL` | label outcomes and event-dependence assignments |
| `GOVERNANCE` | signed checkpoints and final-holdout evaluation grants |

Routing is derived from the exact record class. A caller cannot select a
channel.

A split manifest is checked against the current `EVENT` and `LABEL` receipt
roots before it is appended. This binds its `event_ledger_root` and
`label_ledger_root` to the registered prefixes rather than caller-selected
history.

### 5.2 Head derivation

Each accepted operation inserts one immutable `head_transitions` row containing:

```text
receipt_sequence
head_type
semantic_key
previous_identity_id
new_identity_id
receipt_hash
```

`active_head(head_type, semantic_key)` returns the latest transition by receipt
sequence. There is no mutable `active_heads` table and no separately hashed
transition object. The authoritative cryptographic binding is the associated
`LedgerReceipt`, whose signed identity payload includes `head_type`,
`semantic_key`, `expected_head`, `new_head`, and both previous receipt hashes.

The implemented record mapping is:

| Record | `head_type` and key | Expected predecessor |
|---|---|---|
| Source manifest | `SOURCE_LINEAGE`; key hashes source contract + dataset | `parent_source_manifest_id` |
| Source member object | `SOURCE_BUNDLE_MEMBER_OBJECT`; key is member ID | none; staged, not authoritative lineage CAS |
| Source bundle | `SOURCE_BUNDLE_LINEAGE`; key hashes source contract + dataset | `parent_source_bundle_id` |
| Slot/definition/schema | identity-specific evidence head; key is its content ID | none |
| Other manifest | `MANIFEST_<TYPE>`; key is its manifest ID | none |
| Information set | `INFORMATION_SET`; key is information-set ID | none |
| Primary candidate | `PRIMARY_SIGNAL_CANDIDATE`; key is candidate semantic key | none |
| Candidate materialization | `CANDIDATE_FEATURE_MATERIALIZATION`; key binds exact information/candidate/schema/encoding | none |
| Eligibility | `ELIGIBILITY_DECISION`; key is `eligibility_key` | none |
| Decision event | `DECISION_EVENT`; key binds the exact eligibility ID and record hash | none |
| Barrier activation | `BARRIER_ACTIVATION`; key is decision-event ID | none |
| Label outcome | `LABEL_OUTCOME`; key is decision-event ID | `supersedes_label_outcome_id` |
| Dependence assignment | `EVENT_DEPENDENCE_ASSIGNMENT`; key hashes event + dependence policy | `supersedes_assignment_id` |
| Checkpoint | `SIGNED_LEDGER_CHECKPOINT`; key is ledger ID | previous checkpoint ID |
| Holdout grant | `HOLDOUT_EVALUATION_GRANT`; key is protocol ID | none |

Before insertion, the current derived head must equal the expected predecessor.
This is the semantic compare-and-swap rule. Source-member objects are the
deliberate exception: alternatives are staged without claiming a stable-key
head, and the source-bundle transition is the authoritative selection. A member
successor may be staged only from a parent in the active bundle and only after
that bundle's cutoff. Corrected label and dependence records must also have
nondecreasing known-at clocks.

## 6. Exact object bytes and hashes

### 6.1 Canonical BLOB

`append()` serializes `record.as_dict()` with
`riskyieldmm.trading.canonical_json_bytes`, parses it through the exact V3
`from_mapping()` implementation, and requires byte-identical canonical
round-trip output.

**IMPLEMENTED:** the object `content_hash` is deliberately simple:

```text
content_hash = SHA256(exact_canonical_blob).hexdigest()
```

It is the raw SHA-256 of the exact persisted BLOB. It is not the earlier
domain-wrapped stored-object digest proposed during design.

Native identities remain separate:

- `identity_id` is the record's V3 ID (`manifest_id`, `information_set_id`,
  `decision_event_id`, and so on);
- `record_hash` remains the object's native `record_hash` where the V3 type has
  one;
- for types without a separate native `record_hash`, the ledger uses
  `content_hash` in the receipt's `record_hash` field.

The object table rejects duplicate content hashes, duplicate `(record_kind,
identity_id)`, and duplicate `(record_kind, record_hash)`.

**ESTABLISHED:** SHA-256 is specified by
[NIST FIPS 180-4](https://csrc.nist.gov/pubs/fips/180-4/upd1/final). The existing
RiskYieldMM canonical subset is inspired by
[RFC 8785](https://www.rfc-editor.org/rfc/rfc8785.html), while intentionally
prohibiting binary floats and using canonical decimal strings.

### 6.2 Graph validation

Before commit and again during full verification, the ledger resolves earlier
objects and calls the appropriate V3 validators:

- full manifest graph validation;
- information-set/protocol validation;
- eligibility/information/protocol validation;
- decision-event record/protocol validation;
- barrier/event validation;
- label/event/activation validation;
- dependence assignment/event/active-label validation.

Domain references are enforced by these typed validators and historical
as-of-sequence lookups. They are not materialized as a separate SQL
`object_references` table in the implemented schema.

### 6.3 First-seen evidence boundary

`LIVE_FIRST_SEEN_CERTIFIED` is a record/manifest classification whose internal
clock and lineage rules are validated. It is not retroactive proof that the
bytes were observed in real time. The ledger proves its own registration order
and enforces `receipt_ts >=` the record's terminal availability clock, but it
does not require a record to be registered before its historical decision
timestamp and it does not independently attest the source or local clock.

**LIMITATION:** backfilling a historical record with
`vintage_class=LIVE_FIRST_SEEN_CERTIFIED` proves only that those exact bytes were
accepted at the later ledger receipt. It does **not** prove that the observation
was available before the historical trading decision. A defensible prospective
claim requires real-time ingestion and causal linkage before the decision
cutoff, plus independent observation/retention before that cutoff of a
checkpoint whose signed prefix already covers the receipt. Even then, the claim
is ledger-relative; source authenticity needs separate evidence.

## 7. Actual SQLite schema

The database has six `STRICT` tables:

| Table | Implemented responsibility |
|---|---|
| `ledger_meta` | random identity nonce, derived ledger ID, schema/canonicalization/validation versions, creation time, journal mode, and maximum object size |
| `objects` | exact canonical BLOB, raw content hash, V3 identity/native hash, semantic key, and first receipt sequence |
| `receipts` | global/channel sequences, receipt hash, operation, object/governance binding, head type/key/predecessor/successor, idempotency/request hashes, previous hashes, and canonical receipt BLOB |
| `head_transitions` | one immutable derived transition for every receipt |
| `checkpoints` | signed checkpoint BLOB, content hash, key/algorithm, signed prefix, predecessor, and governance receipt |
| `holdout_grants` | immutable grant BLOB and its exact protocol, split, checkpoint, and governance receipt bindings |

Every table has `BEFORE UPDATE` and `BEFORE DELETE` abort triggers. Deferred
foreign keys bind objects, checkpoints, grants, and transitions to the receipt
created in the same transaction. Unique constraints enforce identity,
idempotency, sequence, protocol, split, and checkpoint slots.

Full verification also hashes the exact definitions of every application-owned
table, index, and trigger in `sqlite_schema`, ordered by type/name/table, and
compares that fingerprint with one generated from the compiled `_SCHEMA_SQL`.
Checking only object names is insufficient: a same-named trigger rewritten as
a no-op fails this exact-schema check.

At creation, a random 32-byte `ledger_identity_nonce` is stored and `ledger_id`
is derived from that nonce plus `created_at`, schema/canonicalization/validation
versions, journal mode, and `max_object_bytes`. Every open and verification
recomputes the identity. Thus an in-range policy change (for example increasing
the object-size limit from 1 MiB to 2 MiB) is detected rather than passing only
range validation. Receipts and checkpoints bind the derived `ledger_id`; an
externally retained trusted checkpoint therefore also commits to those metadata
values through the ledger identity.

There are no implemented tables for append requests, object-reference edges,
external-anchor proofs, partition fingerprints, mutable heads, or key custody.
Those concepts must not be described as current schema behavior.

## 8. Atomic append and idempotency behavior

### 8.1 `append()` sequence

1. Require an exact supported V3 class.
2. Canonicalize, enforce `max_object_bytes`, parse, and require exact round trip.
3. Derive identity, native hash, raw content hash, channel, head type, semantic
   key, expected predecessor, successor, and canonical request hash.
4. Enter `BEGIN IMMEDIATE`.
5. Resolve caller idempotency key behavior.
6. Reject a duplicate object registered under another idempotency key.
7. Require current head == expected predecessor.
8. Resolve and validate the complete required V3 graph, supersession clocks,
   and split roots.
9. Insert object, receipt, and head transition.
10. Commit through the transaction context before returning success.

The receipt timestamp must not precede the record's terminal availability
clock, and receipt timestamps may not move backward relative to the previous
global receipt.

Full verification proves an exact operation-child bijection: each append
receipt has one and only one object row, each checkpoint receipt one and only
one checkpoint row, and each holdout-grant receipt one and only one grant row.
The receipt must have the correct channel, record kind, identity, and governance
payload presence for that operation, while the separate transition verifier
requires exactly one head transition for every receipt.

### 8.2 Caller idempotency keys

The idempotency key is caller-supplied, normalized as a bounded identifier, and
unique in `receipts`. The ledger separately derives `request_hash` from the
operation's identity-bearing inputs.

| Situation | Implemented result |
|---|---|
| Same idempotency key and same request hash | return original receipt/object |
| Same idempotency key and different request hash | `LedgerIdempotencyConflictError` |
| Same object/content submitted under a different key | `LedgerAlreadyRegisteredError` with the first receipt sequence |
| New object, stale or missing expected predecessor | `LedgerConflictError` |
| Valid explicit label/assignment/source successor | append one receipt and transition |
| Duplicate protocol/split holdout grant | `HoldoutGrantConflictError` |

An old object submitted after it was superseded is not reactivated. It is either
an exact same-key replay or an already-registered conflict.

`create_checkpoint()` and `grant_final_holdout_evaluation()` use the same
caller-key/request-hash rule. A caller must use a new idempotency key when it
intends to create a new checkpoint for a later prefix.

## 9. Global and channel receipt chains

`LedgerReceipt` stores one global sequence and one sequence in its routed
channel. Its identity payload includes:

```text
ledger/schema/canonicalization/validation versions
global_sequence
channel + channel_sequence
receipt_ts
operation
record_kind + identity_id + record_hash + content_hash
semantic_key + head_type + expected_head + new_head
idempotency_key + request_hash
governance_payload_hash
previous_global_receipt_hash
previous_channel_receipt_hash
```

The receipt hash is:

```text
sha256_digest({
  "domain": "RiskYieldMMLedgerReceiptV1",
  "payload": receipt.identity_payload()
})
```

The same receipt hash advances both the global chain and its channel chain.
There is no separate channel-receipt object. An empty chain uses 64 zeroes as
`GENESIS_HASH`.

**IMPLEMENTED:** because `head_type` is inside the hashed receipt identity, a
transition cannot be reclassified from, for example, `LABEL_OUTCOME` to another
head family without breaking receipt verification. Full verification also
requires every receipt to have exactly one matching immutable transition.

The global chain gives one total local order. Channel roots provide focused
prefix commitments for manifests, events, labels, and governance. A linear
chain detects mutation, insertion, reordering, or a broken predecessor within
the verified copy.

**LIMITATION:** an unanchored linear chain does not detect deletion of its tail
or replacement of the complete database with an internally consistent older
copy. That is the checkpoint/public-key problem in the next section.

## 10. Ed25519 checkpoints and rollback evidence

### 10.1 Implemented checkpoint

`create_checkpoint(signer, idempotency_key=...)` signs the current committed
receipt prefix. `SignedLedgerCheckpoint.signing_payload()` contains:

```text
ledger/schema/canonicalization/checkpoint versions
signed_at
global_sequence + global_receipt_root
exactly one root for each of MANIFEST, EVENT, LABEL, GOVERNANCE
previous_checkpoint_id
signature_algorithm = ED25519
key_id
```

The signer returns a detached 64-byte signature and verifies it before the
checkpoint is accepted. The checkpoint ID hashes the signing payload,
signature, and signature encoding. The exact checkpoint BLOB also receives a
raw SHA-256 content hash.

The checkpoint signs the prefix ending immediately before its own registration
receipt. The checkpoint row and `GOVERNANCE` receipt are then committed
atomically, and the receipt's sequence must be `signed_global_sequence + 1`.
Later checkpoints link the previous checkpoint ID. Silent key/algorithm changes
are rejected; a rotation protocol is not yet implemented.

The Ed25519 adapter uses the optional `cryptography` dependency declared by the
`governance` extra. `derive_ed25519_key_id()` binds the key ID to the exact raw
public key. Private-key persistence is intentionally caller-owned; the ledger
stores no private key.

Adversarial testing found that the active OpenSSL/`cryptography` provider
accepted an all-zero Ed25519 public key and all-zero signature for the actual
checkpoint payload. Provider verification is therefore only the final step.
The adapter first canonically decodes the public key and signature `R`, rejects
the identity and points outside the prime-order main subgroup, and requires the
signature scalar `S` to be canonical (`S < L`). This matches the point-validity
properties documented for libsodium—canonical encoding, main-subgroup
membership, and rejection of small-order points—without claiming that this
implementation is libsodium-backed. See [libsodium point validation](https://doc.libsodium.org/advanced/point-arithmetic).

**ESTABLISHED:** Ed25519 is specified by
[RFC 8032](https://www.rfc-editor.org/rfc/rfc8032.html).

### 10.2 What must be retained externally

**LIMITATION:** checkpoint rows and signatures stored only inside the same
SQLite database are not rollback evidence. An attacker able to replace the DB
can replace those rows as well.

For rollback evidence, retain outside the ledger's mutable trust domain:

1. the canonical `SignedLedgerCheckpoint` JSON; and
2. the trusted 32-byte Ed25519 public key (or a separately trusted binding to
   its derived key ID).

`verify(trusted_checkpoint=..., verifier=...)` verifies that external signature,
ledger ID, global root, and all channel roots against database state at the
checkpoint's signed sequence. It prevents an older or altered copy from passing
for that anchored prefix. It cannot authenticate receipts appended after that
checkpoint.

When any `verifier` is supplied, full verification also verifies the detached
signature of **every checkpoint stored in the database** with that verifier.
This is valid under the current invariant that silent checkpoint key/algorithm
rotation is prohibited. The externally supplied checkpoint is verified again as
a distinct trust input. Supplying a verifier without an external checkpoint can
authenticate the stored signatures, but it does not make database-resident
checkpoint copies independent rollback anchors.

`LedgerVerificationReport` makes the trust boundary explicit:

- `trusted_checkpoint_id` identifies the supplied external checkpoint, or is
  null when none was supplied;
- `trusted_global_sequence` is the signed global prefix sequence, or null;
- `unanchored_receipt_count` is `receipt_count - trusted_global_sequence`, or
  all receipts when no external checkpoint was supplied.

A checkpoint signs the prefix before its own registration receipt. Therefore
even verification against the newest checkpoint normally reports at least that
registration receipt as an unanchored suffix. Operators must not describe the
current ledger tail as externally anchored when this count is nonzero.

The CLI exposes the same boundary:

```text
riskyieldmm-ledger verify DATABASE \
  --checkpoint TRUSTED_CHECKPOINT.json \
  --public-key-hex 32_BYTE_PUBLIC_KEY_HEX
```

Without a verifier, `verify()` checks stored checkpoint canonical form,
chain/root/receipt consistency, but does not authenticate the signatures. With
a verifier but without independently retained checkpoint bytes, signature
authentication still does not establish database rollback freshness.

**CONDITIONAL / FUTURE:** an RFC 3161 timestamp authority or independently
administered append-only store can add evidence that the externally retained
checkpoint existed before an external time. RFC 3161 anchoring is not currently
implemented. See [RFC 3161](https://www.rfc-editor.org/rfc/rfc3161.html).

**LIMITATION:** a signature or timestamp proves commitment to bytes, not that
the source data, receipt clock, model claim, or economic result was truthful.

## 11. Two-checkpoint final-holdout protocol

### 11.1 Pre-grant checkpoint and authorization grant

`HoldoutEvaluationGrant` binds exactly:

```text
ledger_id
protocol_manifest_id
split_manifest_id
checkpoint_id
approval_hash
evidence_gate_hash
frozen_artifact_hash
external_anchor_hash
granted_at
grant_id
```

The grant's `checkpoint_id` is the **pre-grant authorization checkpoint**. The
four evidence fields are canonical 64-hex commitments supplied by the caller.
The ledger records their exact values; it does not open, interpret, or
independently validate the approval document, evidence gate, frozen artifact,
or external anchor behind those hashes.

The grant method verifies that:

- the registered protocol is a `PROTOCOL` manifest;
- the registered split is a `FINAL_HOLDOUT` split for that protocol;
- the effective holdout SOURCE descendant, each descendant bundle, and every
  non-anchor member were first registered after the protocol receipt;
- protocol and split bind the same holdout policy;
- neither that exact protocol nor that exact split already has a grant;
- the supplied authorization checkpoint is the latest registered checkpoint;
- no receipt follows that checkpoint's registration receipt;
- its signed prefix covers the holdout split;
- grant time is not before checkpoint signing;
- the grant becomes the immediately following governance receipt.

The protocol and split unique constraints make the grant irreversible inside
the append-only schema. Exact same-key retry returns the existing grant. The
authorization checkpoint necessarily predates the grant receipt, so it cannot
by itself prove that the grant survived a later rollback.

Vintage class is immutable within source lineage. Accordingly, the protocol is
anchored to a prospective `LIVE_FIRST_SEEN_CERTIFIED` root and the holdout
accrues through later same-vintage descendants. Binding a model developed on a
separate historical or nominal lineage into that live protocol still requires
a future explicit model-promotion artifact. The current grant's caller-supplied
`frozen_artifact_hash` records a commitment but does not prove that
cross-lineage promotion workflow by itself.

### 11.2 Post-grant checkpoint and evaluation seal

After the grant, create another checkpoint whose signed global sequence covers
the grant receipt, then retain that checkpoint and its trusted public key
outside the database. The post-grant checkpoint may follow other receipts, but
its signed sequence must be at least the grant receipt sequence.

```python
post_grant_checkpoint = ledger.create_checkpoint(
    signer,
    idempotency_key="post-grant-checkpoint",
)

seal = ledger.verify_holdout_evaluation_seal(
    grant.grant_id,
    trusted_checkpoint=post_grant_checkpoint,
    verifier=signer.verifier(),
)
```

`verify_holdout_evaluation_seal()` runs full verification in one read snapshot,
authenticates the supplied checkpoint and stored checkpoint chain, confirms the
grant exists, requires the trusted signed sequence to cover its receipt, and
requires that exact trusted checkpoint to be registered in the ledger. A
detached but unregistered checkpoint is insufficient. Passing the pre-grant
checkpoint fails because its signed prefix ends before the grant.

`HoldoutEvaluationSealReport` returns the grant/protocol/split IDs, grant
receipt sequence, trusted checkpoint ID and signed sequence, and the remaining
`unanchored_receipt_count`. The post-grant checkpoint's own registration receipt
is outside its signed prefix, so a successful seal does not imply that the
entire current tail is anchored.

### 11.3 Honest claim boundary

After the post-grant checkpoint has genuinely been retained outside the
database, the accurate claim is:

> The ledger issued one immutable authorization grant for this exact protocol
> and registered final split, bound the supplied approval/evidence/artifact/
> anchor commitments, and a later externally retained registered checkpoint
> signs a prefix that includes that grant receipt.

It does not support these stronger claims:

- **LIMITATION:** it does not prevent direct filesystem reads or copies;
- **LIMITATION:** it does not count file reads or evaluator invocations;
- **LIMITATION:** it does not bind a `trial_spec_manifest_id` or run-attempt ID;
- **LIMITATION:** it does not fingerprint equivalent row partitions across
  different protocol/split IDs;
- **LIMITATION:** `external_anchor_hash` is a commitment, not locally validated
  proof that an external service accepted either checkpoint;
- **LIMITATION:** the API cannot prove the operator actually retained the
  post-grant checkpoint outside the database; that is an operational fact;
- **LIMITATION:** it does not automatically start, isolate, or constrain an
  evaluator.

A stronger untouched-holdout claim requires the blind-evaluator gate in
Section 16.

## 12. Verification and backup behavior

### 12.1 Full verifier

`V3GovernanceLedger.verify()` currently checks:

- state-directory, database, and sidecar ownership and modes; an existing writer
  lock file is also validated, while its absence is valid for read-only use;
- recomputed ledger identity over the stored nonce and immutable metadata,
  runtime journal mode, schema versions, and WAL safety;
- SQLite `integrity_check`, `foreign_key_check`, and the exact fingerprint of
  every application-owned table, index, and trigger definition;
- canonical receipt BLOBs against relational columns;
- contiguous global/channel sequences, previous hashes, and nondecreasing
  receipt clocks;
- exact object BLOB content hashes, V3 identities/native hashes, request hashes,
  terminal availability clocks, and as-of-receipt graph validation;
- one matching head transition for every receipt, valid predecessor replay, and
  an exact receipt-to-operation-child bijection;
- checkpoint BLOB/receipt/root/predecessor/key consistency and, whenever a
  verifier is supplied, every stored checkpoint signature;
- holdout grant BLOB/manifest/checkpoint/receipt consistency;
- an optional external checkpoint signature and public-key binding.

All database reads above occur inside one explicitly established SQLite read
transaction. The verifier forces the deferred transaction to acquire its
snapshot before the first validation phase, so a concurrent legitimate commit
cannot mix receipt state from one point with objects or governance rows from
another.

The returned report contains counts, current global and channel roots, ledger
ID, the trusted external checkpoint ID and signed sequence when supplied, and
the exact number of receipts after that trusted prefix. With no external
checkpoint, every receipt is reported as unanchored.

### 12.2 Read-only CLI

`riskyieldmm-ledger verify` opens the database with SQLite `mode=ro` and
`query_only=ON`. Current CLI tests cover clean read-only verification, externally
supplied checkpoint/public-key verification, wrong/missing key handling,
malformed checkpoint rejection, unsafe database mode rejection, and missing DB
rejection. Late SQLite read/corruption errors are normalized to a controlled
exit status rather than escaping as a traceback.

The adversarial ledger tests exercise journal/durability defaults, global and
channel chains, replay/conflicts, manifest graphs, lineage/supersession,
global observation claims, candidate-neutral projections, executable missing-
input policies, null-publication clock poisoning, candidate-field declarations,
writer exclusion, transactional rollback and abrupt process death, canonical
BLOB tampering, exact receipt-child bijections, schema substitution, one-snapshot
verification, stored/external checkpoint signatures, rollback detection,
trusted-sequence reporting, two-checkpoint holdout sealing, private backup,
no-repair storage behavior, connection-durability downgrade rejection, and
immutable object-size limits. Writable-reopen refusal, broken-sidecar-symlink
rejection, and the second pre-commit sidecar check are exercised directly. Test
coverage is not a substitute for the
operational certification gates below.

On 2026-07-14 the final complete-repository command `pytest -q` finished with
`1151 passed, 32 skipped in 45.30s`.

### 12.3 Backup

`backup_to(destination)`:

1. requires a nonexistent, non-symlink destination in an existing non-symlink,
   current-UID, mode-`0700` directory on an accepted filesystem;
2. exclusively creates a regular mode-`0600` file with `O_EXCL` and
   `O_NOFOLLOW` where available, then validates descriptor/path identity;
3. uses SQLite's online backup API without overwriting an existing path;
4. fsyncs the completed file and its parent directory;
5. opens the copy read-only and runs structural `verify()` before returning;
6. removes the newly created database and known sidecars if backup or
   verification fails.

Python exposes the SQLite backup API in the official
[`sqlite3` documentation](https://docs.python.org/3/library/sqlite3.html).

**LIMITATION:** `backup_to()` does not copy or verify an externally retained
checkpoint/public key and does not itself establish rollback freshness. The
operator must retain and verify those artifacts separately.

## 13. Security and resource boundaries

### 13.1 Implemented local controls

- Minimum SQLite version is 3.37 because the schema uses `STRICT` tables.
- Parent directory must be owned by the current UID, not be a symlink, and have
  exact mode `0700`.
- DB, writer lock, and detected journal/WAL/SHM files must be regular,
  single-link, current-UID files with exact mode `0600`.
- Known network/distributed filesystem types are rejected using Linux mount
  information when available.
- New database and backup files use exclusive creation and `O_NOFOLLOW` where
  supported, are validated against the opened descriptor, and are fsynced.
- A new writer-lock file is also created exclusively with `O_NOFOLLOW` where
  supported and validated against its opened descriptor.
- Existing files are validated and rejected if unsafe; the ledger does not
  silently `chmod` or otherwise repair them. Failed new-ledger initialization
  removes the newly created database/sidecars instead of leaving a poisoned
  path.
- The writer-lock file is protected by nonblocking `flock()`.
- SQLite extension loading and memory mapping are disabled; trusted schema is
  disabled; defensive mode is requested where exposed.
- Read-only opens use SQLite URI `mode=ro` plus `query_only=ON`.
- Default canonical object limit is 1 MiB. A new ledger may configure a value
  up to 64 MiB; the chosen value becomes immutable metadata.

SQLite documents that foreign-key enforcement must be explicitly enabled on
each connection; see [SQLite foreign keys](https://sqlite.org/foreignkeys.html).
`STRICT` typing is documented in
[SQLite STRICT tables](https://sqlite.org/stricttables.html). Python's Unix
advisory lock interface is documented under
[`fcntl.flock`](https://docs.python.org/3/library/fcntl.html#fcntl.flock).

### 13.2 Current limitations

- The implementation is Unix/Linux-specific because it imports `fcntl` and
  consults `/proc/self/mountinfo` when available.
- File modes and advisory locks do not defend against the owning account or
  root.
- Standard SQLite storage is not encrypted at rest by this implementation.
- There is no free-space floor, writer-queue bound, statement deadline,
  pagination service, ledger-size cap, archive rotation, or rate limiter.
- The five-second SQLite busy timeout has no additional bounded application
  retry policy.
- Signer key persistence, hardware custody, revocation, and rotation are outside
  the implemented ledger.
- The external evidence artifacts named by holdout hashes are not fetched or
  validated.

These are certification gates, not hidden properties of the current code.

## 14. Threat model

| Threat | Current response | Residual limitation |
|---|---|---|
| Process exception mid-mutation | SQLite transaction rollback; object/receipt/transition/grant use one transaction | Power loss and faulty filesystem behavior still require target-environment fault tests |
| Two compliant local writers | nonblocking process lock; `BEGIN IMMEDIATE` and unique constraints as backstops | same-UID code can bypass the service and edit/open the DB directly |
| Duplicate delivery | same caller key/request hash returns original evidence | same object under a different key is a hard error, not an automatic dedupe response |
| Conflicting or stale successor | semantic compare-and-swap, unique identity, graph validation, monotone correction clocks | compromised writer/source logic can still submit semantically misleading but valid data |
| Metadata/receipt/schema mutation or orphaning | recomputed metadata-bound ledger identity, canonical BLOB/hash chains, exact schema fingerprint, transition cardinality, and receipt-child bijections | an internally consistent unanchored replacement DB can evade local-only verification |
| Mixed-state verification during append | all relational verification runs in one pinned SQLite read snapshot | filesystem metadata checks surround, but are not part of, the SQLite snapshot |
| Database rollback | externally retained signed checkpoint + independently trusted public key; report exposes trusted sequence and unanchored suffix | protects only through the trusted signed sequence; later tail remains unanchored |
| Stored-signature forgery/replacement | supplied verifier checks every stored checkpoint and the external trust anchor | signatures and checkpoint copies stored only in the replaced DB are still not independent trust roots |
| Local clock rollback | receipt time must be monotone and after record terminal time | local clock is not trusted objective time; false but monotone time remains possible |
| Signing-key theft | key ID binds the public key; signature verification detects other keys | stolen private key can issue valid signatures; rotation/revocation are not implemented |
| Historical `LIVE_FIRST_SEEN` backfill | receipt records the later registration order and exact bytes | does not prove the observation existed before the historical decision |
| Holdout grant rollback/reuse | unique exact protocol/split grant plus externally retained registered post-grant checkpoint seal | equivalent data under different IDs, failure to retain the seal, and direct filesystem access are not prevented |
| Unsafe pre-existing storage | exact owner/type/link/mode checks (including broken sidecar symlinks) fail closed without permission repair; new DB/backup uses exclusive no-follow creation | same-UID or root code can still replace paths outside the compliant API |
| Invalid/flood input | exact parser and 1 MiB default object cap | no rate limiter, free-space guard, or service authentication exists |
| Disk/database corruption | SQLite integrity/FK checks, canonical reconstruction, verified backup | no automatic recovery orchestration or externally freshness-checked restore exists |

**LIMITATION:** none of these controls proves that market data were genuine,
features causal, labels economically correct, execution realistic, or a model
profitable.

## 15. Remaining acceptance gates

The documented hardening is implemented and the complete repository suite is
green. Deployment certification still requires these gates and retained
evidence:

1. independent golden vectors for every accepted object, semantic head,
   receipt, checkpoint, grant, signature, and raw BLOB hash;
2. stronger multi-process database-contention tests beyond the implemented
   authoritative-writer exclusion, including readers during writes,
   checkpointing, grants, verification, and backup;
3. commit/acknowledgement-boundary fault injection plus disk-full, I/O-error,
   corruption, truncation, and restore tests;
4. real power-loss testing on each certified storage/filesystem profile,
   explicitly separated from the covered process-death simulation;
5. complete unsafe owner/mode/symlink/hard-link/filesystem and read-only
   mutation matrices;
6. external pre/post-grant checkpoint publication, independent retention,
   trusted-sequence/unanchored-tail monitoring, and a documented recovery
   drill;
7. a reviewed signing-key custody, rotation, revocation, and compromise
   procedure;
8. retained and independently validated approval, evidence, frozen-artifact,
   and external-anchor commitments plus blind-evaluator integration;
9. measured object/receipt growth, contention latency, verification time,
   backup time, recovery time, and disk-capacity alarms under representative
   load;
10. legacy Analyst/RPF append integration, historical/live parity, and complete
    trading-pipeline acceptance tests.

Passing this list establishes governance mechanics, not trading edge.

## 16. Later architecture gates

### 16.1 Blind evaluator

A physical untouched-holdout claim requires a separate account/host or service
that exclusively holds the final data and:

- accepts only a frozen artifact and a grant covered by an externally retained
  registered post-grant checkpoint seal;
- has no interactive researcher access or unrestricted output/egress;
- enforces the predeclared evaluation and attempt budget;
- returns a signed, bounded result rather than raw holdout rows;
- retains its own access log and external checkpoint.

**CONDITIONAL:** this is future work. The local grant is deliberately an honest
authorization receipt, not a data-access control system.

### 16.2 PostgreSQL or single-writer service

SQLite remains appropriate while one local writer owns the database and the
measured lock/durability objectives pass. PostgreSQL becomes justified when:

- writers or trusted clients span hosts;
- database authorization, central operations, HA, or point-in-time recovery are
  required;
- sustained read/write contention violates the local service objective;
- the blind evaluator needs a separately administered persistence boundary.

**ESTABLISHED:** PostgreSQL transactions provide all-or-nothing changes, MVCC
supports concurrent readers/writers, and serializable transactions can require
application retries. Official references:

- [PostgreSQL transactions](https://www.postgresql.org/docs/current/tutorial-transactions.html)
- [PostgreSQL MVCC](https://www.postgresql.org/docs/current/mvcc-intro.html)
- [PostgreSQL serializable isolation](https://www.postgresql.org/docs/current/transaction-iso.html#XACT-SERIALIZABLE)
- [PostgreSQL WAL durability settings](https://www.postgresql.org/docs/current/runtime-config-wal.html)

Migration must stop SQLite writes, retain an externally trusted terminal
checkpoint/public key, export exact canonical BLOBs and receipts, import without
changing hashes, verify both copies, and start exactly one new authority. Dual
authoritative writers are prohibited.

### 16.3 Optional transparency tree and timestamp authority

The current linear chains are adequate for a low-volume local ledger. An
RFC 9162-style Merkle tree is useful only if compact inclusion/consistency
proofs or multiple independent auditors become requirements. It does not remove
the need for independent observation. See
[RFC 9162](https://www.rfc-editor.org/rfc/rfc9162.html).

An RFC 3161 timestamp authority can independently time-anchor a checkpoint
hash. Neither feature is currently implemented.

## 17. Readiness statement

The documented ledger scope is implemented and its complete repository suite
passes. It is not deployment certified. The following wording is accurate
today:

> RiskYieldMM has an implemented local V3 governance-ledger foundation with
> atomic SQLite registration, immutable canonical objects, globally and
> per-channel chained receipts, derived semantic heads, Ed25519 checkpoint
> support, an exact protocol/split authorization grant with separately verified
> post-grant checkpoint sealing, single-snapshot structural/cryptographic
> verification, explicit unanchored-tail reporting, and verified-copy backup
> support.

The following wording is not yet justified:

> The production trading pipeline is prospectively sealed, the final holdout was
> physically inaccessible, every stored checkpoint is externally anchored, or
> the ledger is deployment certified.

Those claims require the remaining gates above.

## 18. Primary and official references

- SQLite, [Transactions](https://sqlite.org/lang_transaction.html)
- SQLite, [Atomic Commit](https://sqlite.org/atomiccommit.html)
- SQLite, [Journal and synchronous pragmas](https://sqlite.org/pragma.html#pragma_synchronous)
- SQLite, [Write-Ahead Logging and WAL-reset bug](https://sqlite.org/wal.html#the_wal_reset_bug)
- SQLite, [STRICT tables](https://sqlite.org/stricttables.html)
- SQLite, [Foreign-key support](https://sqlite.org/foreignkeys.html)
- Python, [`sqlite3` standard-library documentation](https://docs.python.org/3/library/sqlite3.html)
- Python, [`fcntl.flock`](https://docs.python.org/3/library/fcntl.html#fcntl.flock)
- IETF, [RFC 8785: JSON Canonicalization Scheme](https://www.rfc-editor.org/rfc/rfc8785.html)
- NIST, [FIPS 180-4: Secure Hash Standard](https://csrc.nist.gov/pubs/fips/180-4/upd1/final)
- IETF, [RFC 8032: Edwards-Curve Digital Signature Algorithm](https://www.rfc-editor.org/rfc/rfc8032.html)
- Libsodium, [Edwards25519 point validation](https://doc.libsodium.org/advanced/point-arithmetic)
- IETF, [RFC 3161: Time-Stamp Protocol](https://www.rfc-editor.org/rfc/rfc3161.html)
- IETF, [RFC 9162: Certificate Transparency Version 2.0](https://www.rfc-editor.org/rfc/rfc9162.html)
- PostgreSQL, [Transactions](https://www.postgresql.org/docs/current/tutorial-transactions.html)
- PostgreSQL, [MVCC](https://www.postgresql.org/docs/current/mvcc-intro.html)
- PostgreSQL, [Serializable isolation](https://www.postgresql.org/docs/current/transaction-iso.html#XACT-SERIALIZABLE)
- PostgreSQL, [WAL durability settings](https://www.postgresql.org/docs/current/runtime-config-wal.html)
