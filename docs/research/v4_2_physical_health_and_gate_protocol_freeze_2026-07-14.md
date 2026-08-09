# V4.2 physical-health reducer and local-gate protocol freeze

**Date:** 2026-07-14

**Status:** Implemented and focused-accepted as a local, non-activating
projection with a clock-owned `DECISION_INPUT` gate; `EXECUTION_BAR` is
deliberately `ABSTAIN`-only until the atomic H1/H2/order-intent bridge.
Live-adapter, scale/soak, governance, execution-bridge, and Stage 1 acceptance
remain open

**Predecessor:**
[`v4_1_causal_selector_protocol_freeze_2026-07-14.md`](v4_1_causal_selector_protocol_freeze_2026-07-14.md)

**Scope:** prospective Bybit mainnet linear-perpetual evidence for the reviewed
`BTCUSDT` and `ETHUSDT` completed-provider-final 1-minute source profiles

## Decision

V4.2 closes one narrowly defined correctness gap: a caller may no longer turn
a V4.1 selection proof into physical trading authority by supplying a
`HEALTHY` value. Health is instead the deterministic result of canonical
physical evidence under one frozen policy.

The selected architecture is a hybrid:

```text
immutable physical messages and exhaustive dispositions
              |                                  |
              v                                  v
typed indexed dual-cutoff extraction     canonical-record replay extraction
              |                                  |
              +-------- exact tuple equality ----+
                                  |
                                  v
                   pure deterministic health reducer
                                  |
                                  v
              EvidenceCutoffV4 + PhysicalHealthTransitionV4
                                  |
                                  v
exact InformationSet + V4.1 proofs + decision/current health checks
                                  |
                                  v
                transaction-owned projection-clock sample
                                  |
                                  v
              DECISION_INPUT local PASS or ABSTAIN
                                  |
                                  v
            EXECUTION_BAR local ABSTAIN only in V4.2
                                  |
                                  v
 future atomic governed H1/H2/order-intent bridge [not V4.2]
```

The canonical event log and derived transition chain are authoritative. A
mutable health head, dashboard value, process-local object, or caller field is
only a rebuildable cache. V4.2 independently constructs the reducer's evidence
tuple through typed SQL and canonical-record replay, requires exact equality,
then applies the same frozen pure reducer to both tuples. This differential
boundary catches typed-projection/extraction divergence; it is not a second,
independently coded health-transition algorithm.

V4.2 remains **non-activating**. A local `DECISION_INPUT PASS` record proves
that the frozen physical predicates held at one local ledger snapshot and one
projection-clock sample; it does not submit an order, grant an Analyst model
trading authority, prove execution quality, establish live readiness, or
demonstrate predictive edge or profitability.

## Evidence grade and current boundary

The following distinctions are binding:

- **Confirmed V4.1 implementation fact:** the selector already binds one exact
  evidence cutoff, applies both receipt and knowledge cutoffs, compares indexed
  SQL with canonical replay, and persists its result in a `BEGIN IMMEDIATE`
  transaction.
- **Confirmed V4.1 limitation:** a selection proof explicitly does not prove
  feed health or economic eligibility. The compatibility cutoff surface carried
  health-shaped fields without a frozen authoritative transition reducer.
- **Implemented V4.2 contract and projection surface:**
  `physical_health_v4.py` defines the reviewed policy, pure reduction result,
  health transition, blocker commitment, and transition-chain rules;
  `physical_gate_v4.py` defines the constant-size local gate and ordered proof
  and health-link commitments. `physical_projection_v4.py` now registers the
  reviewed policy; atomically derives a cutoff and transition; compares typed
  SQL evidence with canonical replay; persists exact `InformationSet`, gate,
  and ordered link rows; derives `PASS`/`ABSTAIN`; and re-verifies all of those
  records from genesis. Authoritative scopes require exact registered primary
  and status adapter-policy roles; public admission and full replay independently
  enforce capture membership/lineage, raw classification/normalization replay,
  and receipt/classifier clock ordering.
- **Focused measured evidence:** `tests/test_trading_physical*.py` passes
  **165 tests** in the current workspace. The end-to-end authority fixture
  proves a derived healthy transition and clock-current local
  `DECISION_INPUT PASS`, caller-selected-health rejection, several adversarial
  `ABSTAIN` outcomes, expiry to `STALE`, idempotency, and full-store
  verification. The complete repository suite passes **1,390 tests** with
  **32 skipped**.
- **Not accepted by this checkpoint:** a separately coded transition algorithm,
  live collector, process/journal fault campaign, frozen-environment scale and
  soak evidence, automatic H1-to-H2 workflow, local order intent/outbox,
  Analyst integration, governance activation, or remote execution.
- **External established mechanisms:** event replay and deterministic state
  machines, mediated/fail-closed policy enforcement, SQLite local transaction
  isolation, and RFC 9162 ordered Merkle commitments.
- **Repository-specific decisions requiring continued adversarial evidence:**
  all exact time limits, recovery counts, state precedence, reason mapping,
  gate-link order, and the two-check workflow below. The focused suite is a
  checkpoint; no cited source proves these values are optimal for trading.

## Confirmed gaps this revision addresses

| Gap at the V4.1 boundary | Why it matters | V4.2 disposition |
|---|---|---|
| Caller-shaped cutoff health | A caller could present a health label that was not reproduced from the ledger | Compatibility cutoffs have no health authority; only a verified `PhysicalHealthTransitionV4` may satisfy a gate |
| No complete transition/recovery matrix | One clean event could otherwise clear a serious historical blocker | Freeze every blocking disposition and its recovery mode; require the common two-bar recovery suffix |
| No explicit no-message time tick | A feed could remain apparently healthy forever if nothing appended | A later evaluation creates a later knowledge cutoff even when the disposition tree is unchanged; freshness then expires deterministically |
| One projection path could certify its own bug | Persisting typed-query output alone cannot reveal projection/extraction mistakes | Implement typed SQL and canonical replay evidence reconstruction, require exact evidence/result equality, and replay it again during full-store verification |
| Selection proof not bound to current health | Correct selected rows can still be stale, disconnected, status-blocked, or from non-prospective evidence | Gate links the exact selection proofs, exact current health transitions, exact `InformationSet`, and evaluation receipt |
| Decision-time-only check | Health may change between model evaluation and order construction | `DECISION_INPUT` is pass-capable; `EXECUTION_BAR` is represented but forced to `ABSTAIN` until the atomic execution bridge exists |
| TOCTOU between check and local intent | A new blocker could arrive after a check but before a local order is admitted | A future policy/version must enable H2 only through one transaction that refreshes health and persists `EXECUTION_BAR PASS`, the exact local intent, and its outbox entry atomically |
| Local/exchange atomicity assumed | SQLite cannot commit atomically with a remote exchange that is not a transaction participant | V4.2 stops at a local proof; later bridge needs durable idempotent intent, pre-send revalidation, and reconciliation |

The following gaps are deliberately **not** closed here:

- no durable live WebSocket/REST collector, restart supervisor, or outage soak;
- no dedicated PONG-age or system-status authority in the reviewed health
  policy; a PONG is transport evidence, not proof that price/status data is
  usable;
- no signed build/runtime identity or externally witnessed V4 ledger anchor;
- no deterministic higher-timeframe physical derivation;
- no persisted outbound subscription intent binding `req_id`, topic, provider
  connection ID, and authenticated transport evidence to the observed ACK;
- no actual V4 manifest/governance-record validation or non-bypassable Analyst
  activation bridge; the legacy V3 activation path remains outside this gate;
- no atomic H1/H2 plus exact order-intent/outbox operation, model, threshold,
  risk, portfolio, order, fill, or reconciliation bridge;
- no evidence that the system has a profitable out-of-sample trade policy.

## Alternatives evaluated

| Alternative | Useful property | Decision and reason |
|---|---|---|
| Caller-maintained state plus periodic checks | Simple and fast | Rejected as authority: mutable state can be skipped, overwritten, or restored inconsistently and does not by itself reproduce history |
| Pure reducer over the canonical event history | Deterministic, replayable, easy to property-test | Selected as the authoritative calculation, with persisted transitions as audit records |
| Query-only health view | Recomputes from stored facts and can avoid a mutable state machine | Retained as the indexed typed extraction side of the differential check, not as a mutable authority |
| Fully separate second transition reducer | Stronger protection against a defect in the reducer itself | Not implemented in this slice. V4.2 instead separates evidence extraction while sharing the small pure reducer; golden, adversarial, and property tests cover reducer semantics |
| SQL and replay sharing projected candidate rows | Less code | Rejected: canonical replay parses canonical ledger records independently and must exactly equal the typed SQL evidence tuple |
| Mutable materialized health head | Constant-time read | Allowed only as a verified, disposable cache rebuilt from transitions; never a gate authority |
| Probabilistic/HMM health regime | Can describe latent market or feed regimes | Rejected for safety admission: a probability is not an exhaustive operational integrity state and cannot replace deterministic blockers |
| Kubernetes/Prometheus readiness alone | Good operations and alerting primitives | Retained for monitoring only; periodic probes and alerts are not transaction-bound order authorization |
| Distributed consensus/transaction protocol | Stronger multi-node coordination | Not justified for this single-writer local correctness slice; Raft/2PC concepts do not make an exchange an SQLite participant |

## Frozen lineage and identities

V4.2 is a **fresh-genesis projection lineage**, not an in-place V4.1 database
upgrade. The new typed tables and record kinds change the schema fingerprint
and verification boundary. A V4.1 database remains a reference fixture and may
enter V4.2 only through a separately approved, full-replay migration gate.

The frozen names are:

```text
authority schema     = riskyieldmm_physical_authority_v4_2
projection schema    = riskyieldmm_physical_projection_v4_2
projection validator = riskyieldmm_physical_projection_validation_v4_2
schema fingerprint   = cfad18b8b96cb45a3dcc1ea67eea114e1fe4d3d7ff345889cabce2931ec25d3d
health policy name   = RiskYieldMMPhysicalHealthPolicyV4_2
health policy id     = fdc8d462d38c9fc87071c0fffec740ae79cb47ca86582e15997621b809c9a2f0
gate policy id       = f487ae92b42c8e6b11ebc72d0c6d54e4f75f93c57fe42b41ff062f412222a4d5
```

Those IDs are canonical hashes of the present contracts. If a normative field
changes, the policy identity, schema fingerprint, acceptance fixture, and
fresh-genesis decision must be reconsidered; an implementation must not keep
the displayed ID while changing its payload.

The new canonical record kinds are:

- `PHYSICAL_HEALTH_POLICY_V4`;
- `PHYSICAL_HEALTH_TRANSITION_V4`;
- `PHYSICAL_EVIDENCE_GATE_V4`.

The full ordered gate links are stored in typed link rows while the canonical
gate carries only their counts and RFC 9162 roots. A root is a compact
commitment, not proof that the chosen link set was complete; completeness is
established by exact `InformationSet` group/revision equality and deterministic
gate re-derivation at the frozen receipt.

## Exact time and cutoff semantics

### Dual cutoff

Every fact consumed by health must satisfy both boundaries of the bound
`EvidenceCutoffV4`:

```text
fact admission/disposition receipt sequence <= cutoff_global_sequence
fact classified/available timestamp          <= knowledge_cutoff_ts
```

Both predicates are inclusive. The first prevents later ledger admissions
from leaking through a backdated semantic time. The second prevents an already
admitted record from being used before it was observable. A transition binds
the cutoff ID, sequence, receipt hash, knowledge cutoff, scope tree size, and
scope tree root as one object; detached integers or a caller-assembled tuple
are invalid.

Normalized observations additionally retain their own observation-admission
sequence and `available_at`. Both implemented evidence-extraction paths enforce
those boundaries rather than relying only on the disposition row.

### Health evaluation time is the knowledge cutoff

For authoritative health:

```text
evaluation_time == knowledge_cutoff_ts == transition.evaluated_at
```

This is stricter than allowing a caller to evaluate an old knowledge snapshot
at a later time. If wall time advances, the caller must request a new cutoff
whose knowledge cutoff advances too. This prevents facts arriving between an
old cutoff and a later evaluation from being deliberately excluded.

A no-message watchdog tick is still meaningful: it appends a later cutoff and
transition with a later knowledge/evaluation time while the scope disposition
tree size/root may remain unchanged. Bar or status freshness then becomes
`STALE` without inventing a provider message.

The health reducer, typed extraction, canonical replay, and transition
constructor receive an explicit UTC knowledge/evaluation timestamp. They may
not call wall-clock functions, SQLite `CURRENT_TIMESTAMP`, or a process clock
internally. Python's monotonic clock may schedule a retry or watchdog, but its
origin is process-local and it cannot be persisted as a causal market-data
time.

### Gate evaluation time belongs to the projection

For a newly derived gate:

```text
gate.evaluated_at = one projection-clock sample taken inside the same
                    BEGIN IMMEDIATE transaction that freezes
                    evaluation_receipt_sequence and evaluation_receipt_hash
```

The public gate API accepts the information-set ID, stage, and idempotency key;
it does not accept `evaluated_at`. The caller therefore cannot select or
backdate the authority clock. Current-health, proof chronology, and expiry
checks all use that one transaction-owned sample. The gate receipt has its own
later-or-equal projection-clock sample and a rollback is rejected. An
idempotent retry resolves the stored operation batch before sampling again and
returns the original gate without changing its evaluation time or identity.

For a same-scope successor transition:

- parent identity and `prior_health == parent.current_health` are exact;
- cutoff receipt sequence, knowledge cutoff, tree size, and event-time
  watermark cannot regress;
- evaluation time strictly advances;
- if a transition names the same cutoff sequence, its cutoff ID, receipt hash,
  tree size, and root must also be identical.

## Exact reviewed health policy

| Field | Frozen value | Meaning |
|---|---:|---|
| Base interval | `60` seconds | Provider-final one-minute bars only |
| Primary-bar freshness | `90` seconds | Stale when `evaluation_time >= latest_bar_close + 90s` |
| Instrument-status freshness | `90` seconds | Stale when `evaluation_time >= status_source_publish + 90s` |
| Maximum clock uncertainty | `250` milliseconds | Current primary capture segment must not exceed this bound |
| Recovery suffix | `2` consecutive completed bars | Both must be clean, contiguous, current-connection, provider-final 1m bars after the recovery anchor |
| Required vintage | `PROSPECTIVE_LIVE` | Historical import, replay, nominal-current, or mixed primary **or required-status authority** evidence cannot be healthy |
| Subscription ACK | required | Must match the latest bar's boot ID, connection ID, generation, subscription-manifest hash, and `capture_partition_id` |
| Instrument status | `Trading` | Exact case-sensitive reviewed provider value |
| Contract type | `LinearPerpetual` | Exact reviewed contract class |
| Adapter receipt-lag ceiling | `2,000` milliseconds | Existing reviewed Bybit adapter/classifier bound; a rejected occurrence becomes a health blocker |
| Maximum blocker links | `4,096` | `4,097` is rejected, never truncated |
| Maximum gate proof links | `4,096` | `4,097` is rejected, never truncated |
| Maximum gate health links | `4,096` | `4,097` is rejected, never truncated |

These values match the narrow reviewed Bybit adapter family where applicable.
They are conservative repository decisions, not estimates of an optimal
trading latency or recovery duration. The 90-second thresholds allow one
completed 60-second bar plus 30 seconds of tolerance; they do not guarantee
that a venue or network is healthy during that period.

The reviewed scope must resolve both adapter policies as registered canonical
records before the scope is admitted. The primary role is exactly a
`BYBIT_V5_PUBLIC_KLINE` policy with `TRADING_AUTHORITY`, a 60-second base
interval, required instrument status, and the scope's primary classifier
release. The status role is exactly `BYBIT_V5_INSTRUMENT_INFO` with
`RECONCILIATION_ONLY`, no recursive status requirement, and the scope's status
classifier release. Both policies must match the scope coordinates, calendar,
provider-native instrument, and freeze chronology; they cannot be substituted
or silently reused across authoritative scopes.

For a `HEALTHY` result:

```text
health_valid_until = min(
    latest_completed_primary_bar_close + 90 seconds,
    current_required_status_source_publish + 90 seconds
)
evaluation_time < health_valid_until
```

No extra caller-selected grace period is permitted. A non-healthy transition
uses `evaluation_time + 1 microsecond` only to satisfy immutable interval shape;
that diagnostic validity does not make it gate-eligible. A `PASS` gate's
`valid_until` is the minimum of all linked healthy-transition expiries and may
never extend one.

### State precedence

When more than one condition applies, the frozen severity order is:

```text
JOURNAL_FAILURE
> INTEGRITY_CONFLICT
> SCHEMA_UNSUPPORTED
> CLOCK_UNCERTAIN
> GAP
> DISCONNECTED
> STATUS_BLOCKED
> STALE
> RECOVERING
> BOOTSTRAPPING
> HEALTHY
```

`HEALTHY` means that no reason code remains. It is not a majority vote or the
absence of a recently observed provider error alone. Unknown states, unknown
dispositions, incomplete classification, malformed canonical rows, and
evaluation exceptions fail closed.

`JOURNAL_FAILURE` is a fail-closed operational condition. A failed journal
cannot reliably append a record claiming its own failure; the gate service must
deny all requests while projection verification or durable append is failing,
and record the incident after recovery. It cannot synthesize a healthy
transition during the outage.

## Frozen blocker and recovery matrix

A blocking disposition takes effect on its first causally visible occurrence.
There is no `N`-failure debounce for safety blockers.

| Blocking disposition | Health while unresolved | Exact blocker-specific recovery |
|---|---|---|
| `PROVIDER_ERROR` | `DISCONNECTED` | A completed authoritative observation on a later connection generation or a new collector boot, for the same adapter |
| `EXPECTED_INSTRUMENT_STATUS_ABSENT` | `STATUS_BLOCKED` | A completed provider-final instrument-status observation; the active status must then pass `Trading`, `LinearPerpetual`, clock, and freshness checks |
| `MALFORMED_PAYLOAD` | `INTEGRITY_CONFLICT` | A completed authoritative observation after a later connection generation or new collector boot, for the same adapter |
| `UNSUPPORTED_SCHEMA` | `SCHEMA_UNSUPPORTED` | `SCOPE_ROTATION_ONLY`; the affected scope cannot auto-recover under the same frozen parser/profile |
| `OUT_OF_SCOPE` | `INTEGRITY_CONFLICT` | A completed authoritative observation after a later connection generation or new collector boot, for the same adapter |
| `RECEIPT_LAG_REJECTED` | `STALE` | A later completed bar or instrument-status observation for the same adapter; common recovery conditions still apply |
| `CLOCK_ORDERING_REJECTED` | `CLOCK_UNCERTAIN` | A completed authoritative observation after a new collector boot, for the same adapter; a generation change alone is insufficient |
| `CONTENT_CONFLICT` | `INTEGRITY_CONFLICT` | `SCOPE_ROTATION_ONLY`; the affected scope remains permanently blocked |

Blocker-specific recovery only removes that blocker. It does **not** directly
produce `HEALTHY`. All of these common conditions must also hold:

1. complete causal classification covers scope message sequences `1..N` with
   no omission;
2. every primary capture and every required-status authority capture belongs to
   the single required `PROSPECTIVE_LIVE` vintage;
3. there is no active revision fork;
4. no unresolved blocker remains;
5. the current primary segment is within the 250 ms uncertainty bound;
6. the current connection has its exact subscription ACK on the same
   `capture_partition_id`;
7. the active instrument-status revision is unique, provider-final,
   `Trading`, `LinearPerpetual`, and fresh;
8. the latest completed provider-final primary bar is fresh;
9. two clean primary bars form a strict contiguous 1-minute suffix on the
   current connection and same `capture_partition_id` as the ACK;
10. both bars were admitted after
    `max(current_connection_ACK_receipt, latest_blocking_disposition_receipt)`.

Consequently, one clean message cannot restore health. There is no additional
wall-clock cooldown in V4.2 beyond the two completed-bar suffix. A longer
cooldown is a possible later policy revision and would change the policy ID;
it must not be silently added to this lineage.

Scope rotation is not an in-place reset. It requires a new governed scope and
policy/parser binding and therefore cannot erase the old scope's immutable
conflict history.

## Pure reducer and SQL-versus-canonical replay

### Authoritative reducer

The pure reducer receives only:

- the reviewed, self-hashed health policy;
- the exact physical-scope manifest;
- canonically ordered health evidence visible through both cutoffs;
- the exact covered message count;
- the explicit knowledge/evaluation time.

It performs no I/O, uses no implicit current time, sends no network request,
and reads no mutable health head. Its complete output tuple is:

```text
current health
canonical ordered reason codes
ordered unresolved disposition IDs and RFC9162 root
clean recovery-bar count
current required-status revision ID
event-time watermark
health-valid-until
derived vintage
```

Blocker IDs are ordered by scope-message sequence and then raw identity. Their
leaf commits the ordinal and disposition ID under the
`RiskYieldMMPhysicalHealthBlockerLeafV4_2` domain. Empty, one, and 4,096-link
roots are valid; duplicate IDs or 4,097 links fail closed.

### Implemented differential boundary

Before health extraction, both the public append path and full-genesis
`verify()` enforce capture membership and lineage. Every capture envelope must
map to exactly one physical message, every physical message must map back to
its exact capture receipt and ordinal, segment parentage must be valid, and a
capture occurrence, partition, or authoritative adapter stream cannot be
silently duplicated, omitted, split across scopes, or reassigned. The same
verification reconstructs every raw classifier result under its registered
adapter policy and requires exact equality of the disposition, raw-normalized
derivation, and observation revision. Classifier provenance and normalized
outputs must remain bijective.

Projection receipt clocks are non-decreasing. A normalized observation's
durable timestamp must equal its capture receipt, and every classifier receipt
must be at or after its declared `classified_at`. Admission and full replay
enforce these chronology rules; a self-consistent typed row cannot bypass them.

`_health_evidence_sql` reconstructs the canonical reducer input from typed,
indexed disposition/provenance/message/revision rows. In parallel,
`_health_evidence_replay` scans canonical records through the exact receipt
cutoff, reparses physical messages, capture segments, classifier provenance,
dispositions, and revisions, and reconstructs the tuple without consuming the
typed health query's rows.

The two ordered `HealthEvidenceItemV4` tuples must be exactly equal. The store
then invokes the same frozen `reduce_physical_health_v4` function on each tuple
and requires exact `HealthReductionResultV4` equality. A mismatch raises
`PhysicalProjectionV4VerificationError` and rolls back the authoritative
health append; no SQL answer is preferred merely because it is faster.

Neither path may read a persisted transition's claimed health, reasons,
counters, or roots as reducer inputs, consume a mutable health-head cache, omit
either cutoff, or use implicit current time. The typed path retains explicit
predicates for:

```text
disposition_receipt_sequence <= cutoff_global_sequence
classified_at                 <= knowledge_cutoff_ts
observation_admission_sequence <= cutoff_global_sequence
observation_available_at       <= knowledge_cutoff_ts
```

The implementation also independently derives the causal event-time watermark
from indexed active heads and compares it with the reducer result before
admission.

Full-store `verify()` repeats typed-versus-canonical evidence construction and
reduction for every health transition, compares each derived cutoff and
transition field, checks parent lineage, and rejects any `HEALTHY` cutoff with
no deterministic transition. It then re-derives every persisted gate at its
frozen evaluation receipt and compares the gate plus ordered link rows exactly.

This is a strong projection/replay check, but the pure transition logic itself
is shared. It can therefore catch typed/canonical extraction divergence and
stored-result tampering, not every possible defect repeated inside the common
reducer. The reducer's exact-value, deterministic, blocker, recovery, fork,
freshness, and time-tick tests are the compensating evidence in this slice. A
second independently coded transition algorithm remains a possible later
assurance upgrade.

`EXPLAIN QUERY PLAN` is an acceptance diagnostic for intended scope/receipt,
revision-parent, adapter/kind, and time indexes. It is not performance proof.
The frozen benchmark must compare full replay, typed extraction, and the
incremental reducer on identical correctness-approved databases.

Any `health_heads` or equivalent current-state table is optional. If added, it
must be derivable from the immutable transition chain, protected from direct
`UPDATE`/`DELETE`, checked against replay at startup, and discarded/rebuilt on
disagreement.

## Immutable health transition

`PhysicalHealthTransitionV4` binds:

- scope, ledger, reviewed policy, and exact evidence cutoff;
- cutoff sequence/hash, knowledge cutoff, tree size, and tree root;
- parent transition and prior/current state;
- canonical reasons;
- unresolved-blocker count/root;
- recovery count;
- active required-status revision;
- event-time watermark;
- validity and evaluation time.

`append_derived_health_cutoff()` now performs authoritative admission. Within
one `BEGIN IMMEDIATE` transaction it verifies gap-free exact-one message,
disposition, and tree coverage; freezes the receipt/tree/knowledge cutoff;
compares typed SQL evidence with canonical replay; runs the pure reducer on
both; independently checks the indexed watermark; appends the derived cutoff
and transition; and records one idempotent operation batch. The caller chooses
only the scope, knowledge/evaluation time, and idempotency key. It cannot
submit `current_health`, reasons, blocker root, recovery count, status ID,
watermark, or validity.

The reviewed policy itself is a canonical ledger record. A transition under an
unregistered policy, a policy with one altered threshold, a detached cutoff,
wrong tree root, wrong prior state, forked parent, regressing clock, or a
caller-supplied healthy compatibility cutoff is rejected.

The transition chain is one linear chain per physical scope. A new transition
may reuse unchanged evidence content on a later no-message time tick, but it
still binds the later cutoff/evaluation snapshot and exact parent. The
compatibility `append_cutoff()` path explicitly rejects caller-selected
`HEALTHY`; non-healthy research cutoffs cannot satisfy a physical gate.

## Constant-size local gate proof

`PhysicalEvidenceGateV4` binds the following values in its canonical identity:

- reviewed physical-gate policy ID and stage;
- ledger ID;
- exact `InformationSetV3` ID and canonical record hash;
- observation cutoff;
- evaluation receipt sequence and hash;
- ordered V4.1 selection-proof link count/root;
- ordered V4.2 health-transition link count/root;
- `PASS` or `ABSTAIN`, canonical reasons, evaluation time, and validity.

The gate policy requires an exact persisted `InformationSet`, V4.1 selection
proofs, decision-cutoff health, and current derived health. The implemented
`evaluate_physical_gate()` samples the projection clock once after entering its
`BEGIN IMMEDIATE` transaction, freezes the current ledger receipt, derives the
verdict at that sample, and atomically appends the gate and its ordered
proof/health link rows. The caller supplies no evaluation timestamp, and an
idempotent replay returns the stored gate. Constructing a Python object whose
fields spell `PASS` is representation only; only this projection evaluator can
admit a local `DECISION_INPUT PASS`. `EXECUTION_BAR PASS` is rejected by the
contract in this policy version.

### Canonical link order and completeness

Proof IDs are ordered by the implemented total key:

```text
dependency_slot_id,
source_member_id,
observation_selection_proof_id
```

`InformationSetV3` dependencies are identity-sorted by their own contract, but
the gate does not pretend that this is the proof-link order. It groups both
dependencies and proofs by `(dependency_slot_id, source_member_id)`, requires
exact group-set equality and one proof per group, and requires exact selected
revision-set equality within each group. Every dependency is also checked
against its physical revision value and scope.

Health IDs are ordered in two parts: exact decision-cutoff transitions sorted
by physical-scope ID, followed by distinct latest/current transitions sorted by
physical-scope ID. A latest transition identical to its decision transition is
not repeated. A second decision cutoff for one scope, an omitted or extra proof
group, an ambiguous proof group, a reordered stored link, or a foreign ledger
changes the derived artifact or produces `ABSTAIN`.

The proof leaf domain is
`RiskYieldMMPhysicalGateProofLinkLeafV4_2`; the health leaf domain is
`RiskYieldMMPhysicalGateHealthLinkLeafV4_2`. Each leaf binds its ordinal and
linked ID. The full ordered links remain in typed tables so verification can
recompute the roots and reconstruct completeness from the `InformationSet`.

A `DECISION_INPUT PASS` requires non-empty proof and health links and no reason
codes. An `ABSTAIN` requires at least one canonical reason; empty link roots are
allowed only when their counts are zero. `verify()` reads typed link rows by
ordinal, re-derives the historical gate at its frozen evaluation receipt, and
requires exact gate/proof-link/health-link equality.

## Two health checks inside every local gate

The implemented evaluator separates decision-time health from current health.
Both checks are evaluated for either identity-bearing stage; `EXECUTION_BAR`
additionally carries a mandatory bridge-not-implemented abstention.

### Check A — exact decision-cutoff health

For each selection-proof scope, the evaluator resolves the unique transition
whose `evidence_cutoff_id` is the proof's exact cutoff. It requires:

- the transition scope to equal the proof scope;
- `current_health == HEALTHY`;
- `transition.knowledge_cutoff_ts == InformationSet.observation_cutoff_ts`;
- validity strictly beyond
  `max(InformationSet.assembled_at, selection_proof.computed_at)`;
- one unambiguous decision cutoff per physical scope.

This proves that the selected physical input was healthy when it became the
persisted decision input. It prevents a later healthy transition from
retroactively healing an unhealthy decision cutoff.

### Check B — latest health at the frozen gate boundary

For each required proof scope, the evaluator independently resolves the latest
health transition whose receipt is visible at the gate's frozen evaluation
receipt. It requires:

- `current_health == HEALTHY`;
- transition evaluation no later than the transaction-owned projection-clock
  sample;
- validity strictly beyond that gate sample;
- no physical-message or disposition receipt visible at the gate boundary with
  a sequence later than the transition's evidence cutoff.

The last predicate is the implemented currentness check. Even a newly captured
and classified control PONG after the health cutoff makes the transition lag
provider evidence and produces `CURRENT_HEALTH_LAGS_PROVIDER_EVIDENCE` until a
new derived-health cutoff/transition incorporates it.

## Two represented gate stages; only H1 is pass-capable

`evaluate_physical_gate()` accepts both identity-bearing stages and applies the
same proof-completeness and two-health-check logic, but the frozen policy gives
them different authority:

- `DECISION_INPUT` is the H1 boundary before a model/rule output is treated as
  physically eligible. The focused end-to-end projection test exercises a
  local `PASS` and adversarial `ABSTAIN` outcomes at this stage.
- `EXECUTION_BAR` is the H2 boundary intended for a new evaluation immediately
  before local order-intent admission. In V4.2 the evaluator always persists
  `ABSTAIN` with `EXECUTION_GATE_BRIDGE_NOT_IMPLEMENTED`, and the contract
  rejects any `EXECUTION_BAR PASS`. Substituting the stage still changes the
  gate identity, but cannot create execution authority.

The local evaluator does not enforce an H1-parent link, create a fresh H2
health tick automatically, or persist an order intent/outbox. A later reviewed
policy/version may enable H2 only after one atomic bridge can bind H1, refresh
or resolve H2 health, derive `EXECUTION_BAR PASS`, and persist the exact local
intent and outbox entry before commit. Calling H2 now and appending an intent
later is forbidden. Reusing H1 alone is also forbidden. There is no executable
order after this checkpoint.

## Transaction and TOCTOU boundary

For each derived-health or gate operation, cutoff/boundary resolution, typed
query, canonical replay where applicable, reducer comparison, link
construction, root calculation, and canonical/typed inserts occur under one
single-writer
`BEGIN IMMEDIATE` transaction. An exception at any point rolls back the whole
operation.

For the future H2 bridge, this local atomic unit is required:

```text
resolve current ledger head
-> append/resolve H2 cutoff and health transitions
-> typed-SQL/canonical-replay health verification
-> verify execution InformationSet and selection proofs
-> derive EXECUTION_BAR PASS under a later reviewed policy
-> persist H1 link + EXECUTION_BAR PASS + exact local intent + outbox entry
-> commit
```

No network call belongs inside this SQLite transaction. The exchange is not a
SQLite transaction participant. After commit, a sender must claim the outbox
idempotently, revalidate that the gate has not expired and that no newer
blocking evidence exists, submit with an idempotency/client-order key where
supported, and reconcile acknowledgement, fill, reject, timeout, duplicate,
and unknown outcomes. Those semantics are a later gate, not implied by a local
`PASS`.

## Fail-closed behavior

Normal, canonically expressible ineligibility produces a persisted `ABSTAIN`
with ordered reasons. Structural/canonical/database failures raise, roll back,
and produce no gate record. Both outcomes deny local authority.

`ABSTAIN` conditions include:

- missing, duplicate, foreign, unregistered, reordered, or expired proof or
  health link;
- caller-selected `HEALTHY`, caller-selected validity, or compatibility-cutoff
  health used as authority;
- policy, scope, source member, adapter, classifier, parser, mapping, contract,
  environment, ledger, cutoff, receipt, tree, or `InformationSet` substitution;
- historical/replay/mixed vintage;
- missing or ambiguous status, non-`Trading` status, wrong contract type, or
  stale status;
- no current matching subscription ACK;
- stale/missing primary bar, strict-grid gap, incomplete causal classification,
  active revision fork, or excessive clock uncertainty;
- any unresolved disposition blocker or incomplete two-bar recovery suffix;
- the current transition lagging any provider message or disposition visible at
  the frozen gate receipt;
- every current `EXECUTION_BAR` request, with
  `EXECUTION_GATE_BRIDGE_NOT_IMPLEMENTED`;
- any legacy call path attempting to bypass H1 or the future atomic H2/intent
  bridge.

Typed-SQL/canonical-replay disagreement, invalid canonical identity, RFC 9162
count/root disagreement, schema drift, database verification error,
transaction error, journal error, timeout, cancellation, or an unhandled
exception aborts the operation instead of minting `ABSTAIN` or `PASS`.

No emergency override may manufacture `PASS`. An operational kill switch may
only turn trading off. A recovery operator may rotate a scope or approve a new
policy/schema through governance, but may not rewrite old evidence or clear a
latched blocker in place.

## Focused acceptance evidence and remaining tests

The confirmed focused command covers:

```text
pytest -q tests/test_trading_physical*.py
```

It passes **165 tests**. The full repository suite passes **1,390 tests** with
**32 skipped** in **61.53 seconds**. The covered physical evidence includes:

- exact policy identity/parameter rejection and blocker-recovery matrix shape;
- empty/one/4,096/4,097, duplicate, and reorder commitment boundaries;
- deterministic reducer replay, empty/replay prefix handling, current ACK,
  two-bar recovery, time-tick expiry, required status, transient and latched
  blockers, required-status replay-vintage rejection, and
  active-revision-fork rejection;
- transition shape, identity, parent, prior-state, and monotonicity attacks;
- exact registered primary/status adapter-policy roles, capture membership and
  lineage on public admission and full replay, raw classifier/normalization
  replay, and monotone receipt/classifier chronology;
- same-`capture_partition_id` ACK and two-bar recovery enforcement;
- atomic idempotent policy and derived cutoff/transition append;
- rejection of caller-selected `HEALTHY`;
- exact V4.1 selection, persisted live-certified `InformationSet`, and a local
  clock-current `DECISION_INPUT PASS` with no caller evaluation timestamp;
- idempotent gate replay preserving the original evaluation sample, rejection
  of a regressing gate-receipt clock, evaluator-level `EXECUTION_BAR ABSTAIN`,
  and contract-level rejection of `EXECUTION_BAR PASS`;
- `ABSTAIN` for unproved state dependencies, selected dependency mismatch,
  current health lagging a newer provider PONG, and a stale latest transition;
- full-genesis verification of policy, cutoffs, transition lineage,
  `InformationSet`, gates, links, operation batches, and existing V4.1
  selection/projection state.

Focused acceptance is not exhaustive. Before Stage 1 exit the suite still
needs every blocker/recovery edge and exact freshness boundary, required-status
mixed-vintage combinations beyond the focused replay case, a dedicated atomic
H1/H2/order-intent/outbox end-to-end bridge,
health/gate-specific injected-fault and concurrent-writer matrices, legacy
order-path bypass tests, frozen query plans, and correctness-first 10,000-event,
100,000-event, restart, two-asset 30-day, and 100-scope capacity/soak gates.

## Acceptance matrix

| Area | Required evidence | Acceptance rule | Freeze status |
|---|---|---|---|
| Fresh genesis | V4.1 open/reuse and partial-upgrade attacks | V4.1 database cannot claim V4.2 schema/authority; V4.2 starts from its own genesis | Implemented schema/fingerprint; broader migration attacks pending |
| Policy identity | Round trip plus one-field mutations for all exact values and recovery rules | Only the displayed reviewed ID is accepted | Implemented; focused suite passed |
| Dual cutoff | Both crossed-clock adversaries and inclusive boundaries | A fact enters only when both predicates pass | Implemented in typed and canonical extraction; focused suite passed |
| Health evaluation tick | No-message later cutoff and intervening-fact adversary | `evaluated_at == knowledge_cutoff`; old knowledge cannot be evaluated as current | Implemented; reducer and projection expiry fixtures passed |
| Gate evaluation clock | Backdating, expiry, receipt-clock rollback, and idempotent-retry attacks | One internal projection-clock sample under the frozen transaction; caller supplies no authority time; retry preserves the stored sample | Implemented; focused current-time, rollback, and replay cases passed |
| Pure reducer | Golden and randomized histories for every state/reason/recovery edge | Same explicit input always returns byte-identical tuple | Implemented; focused cases passed; exhaustive matrix pending |
| Typed SQL versus canonical replay | Independent evidence construction through both cutoffs | Exact evidence/result equality; disagreement rolls back | Implemented and repeated by full verification; common-reducer limitation documented |
| State precedence | Simultaneous blocker/freshness/gap/status/clock faults | Highest frozen state wins with complete canonical reasons | Policy fixed; broader adversarial matrix pending |
| Recovery | All eight blocker modes, current ACK, status, two-bar suffix | One event cannot heal; scope-only blockers never heal in-place | Core focused cases passed; every-edge matrix pending |
| Validity | Bar/status boundary and min-expiry tests | Healthy and gate validity never extends observed evidence | Implemented; focused expiry passed; exact boundary matrix pending |
| Transition chain | Parent/fork/substitution/regression/reopen fixtures | One same-scope monotone replayable chain | Implemented and full-genesis verified; broader attacks pending |
| Blocker commitment | 0/1/4,096/4,097, duplicate/reorder attacks | Exact ordered RFC 9162 root; never truncate | Implemented; focused boundaries passed |
| Gate commitments | Proof/health 0/1/4,096/4,097 and completeness attacks | Roots, typed links, `InformationSet`, and implemented canonical order agree | Implemented; focused contract/E2E/full-verify cases passed |
| H1 decision check | Selection/health/info-set/receipt/policy substitutions | Clock-current `PASS` only for exact healthy prospective decision and current inputs | Implemented; PASS plus adversarial ABSTAIN cases passed |
| H2 execution check | Pre-bridge PASS construction/evaluation, new evidence, expiry, reconnect, and H1-reuse attacks | V4.2 always persists `EXECUTION_BAR ABSTAIN`; only a later atomic H1/H2/intent policy may enable PASS | ABSTAIN-only contract and evaluator implemented; atomic bridge deliberately absent |
| Transaction/crash | Injected failure at every write boundary; concurrent writer; retry | All-or-nothing transition/gate/link records under one snapshot; future H2 PASS and exact intent/outbox share one transaction | Current transactional/idempotent path implemented; atomic execution bridge and broader fault matrix pending |
| Query plan/scale | Frozen environment, plan facts, reducer/replay benchmarks and soaks | Correctness first; predeclared resource/latency limits pass | Pending |
| Journal failure | Append/verify/fsync/storage-full/corruption faults | No gate can pass while journal authority is unavailable | Required; operational test pending |
| External execution boundary | Outbox/idempotency/revalidation/reconciliation fixtures | Local gate never claims atomic remote execution | Next subgate, deliberately absent |
| Analyst/governance bridge | Explicit activation grant, model lineage, risk/order binding, kill switch, paper shadow | No existing Analyst or order path can consume V4.2 `PASS` as live authority | Next subgate, deliberately absent |

No row in this matrix is an economic edge test. Completing it would establish a
stronger causal and operational evidence boundary, not a profitable strategy.

## Non-activating boundary and next bridge

Until the matrix is accepted:

- V4.2 gates are local correctness/audit artifacts only;
- paper and live order submission remain disabled;
- V4.1 selection proofs remain usable for research, but not as physical trading
  authority;
- legacy cutoff health, UI health badges, alerts, and process liveness cannot
  substitute for a transition or gate;
- no model artifact may self-declare compatibility with V4.2.

The next governance/Analyst execution subgate must add an immutable activation
grant binding, at minimum:

```text
approved V4.2 schema/fingerprint and ledger
approved health and gate policy IDs
approved physical scopes, assets, contracts, venue, and environment
approved InformationSet/feature/label/model lineage
approved decision policy, risk policy, and order policy
required DECISION_INPUT gate ID
required EXECUTION_BAR gate ID
exact order-intent digest and validity
paper-only/live mode, capital limits, kill switch, and approver identities
```

It must start disabled and paper-only, prove offline/live feature and decision
parity, use a durable idempotent outbox, and reconcile every order state before
any separately governed live-capital review. A model may rank or abstain only
after H1. No order becomes sendable while V4.2 forces H2 to `ABSTAIN`; a later
reviewed policy may enable `EXECUTION_BAR PASS` only when that PASS, the exact
intent/outbox entry, and the activation grant are bound by the atomic bridge.

## Primary-source basis and limitations

- NIST SP 800-160 Vol. 1 Rev. 1 describes mediated access, separation of policy
  decision and enforcement, protective defaults, and non-bypassable reference
  monitoring: [Systems Security Engineering](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-160v1r1.pdf).
  It supports the fail-closed gate shape; it does not define market-data health
  states, the 90-second limits, or a profitable trading policy.
- SQLite documents explicit transactions, the one-writer model, and snapshot
  isolation in [Transaction](https://www.sqlite.org/lang_transaction.html) and
  [Isolation In SQLite](https://www.sqlite.org/isolation.html). These sources
  support the local `BEGIN IMMEDIATE` boundary, not remote-exchange atomicity or
  business correctness.
- Microsoft's [Durable Task orchestration](https://learn.microsoft.com/en-us/azure/durable-task/common/durable-task-orchestrations)
  and [deterministic-code constraints](https://learn.microsoft.com/en-us/azure/durable-task/common/durable-task-code-constraints)
  explain replay from append-only history and why deterministic logic must not
  call implicit current time or external I/O. This is vendor guidance, not a
  proof of this implementation.
- The Microsoft [Event Sourcing pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/event-sourcing)
  supports append-only events, replay, projections, snapshots as optimizations,
  ordering, idempotency, and versioning. It also warns that projections may be
  eventually consistent; V4.2 therefore verifies its local projection before
  admission.
- W3C [SCXML](https://www.w3.org/TR/scxml/) formalizes deterministic event
  processing and run-to-completion behavior. It does not supply persistence,
  provider semantics, or trading thresholds.
- Ongaro and Ousterhout's [Raft paper](https://raft.github.io/raft.pdf) explains
  why deterministic state machines receiving the same ordered log reach the
  same state. V4.2 borrows that reasoning; it does not propose deploying Raft.
- Kubernetes distinguishes
  [liveness, readiness, and startup probes](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#types-of-probe).
  This supports keeping process health separate from data eligibility. Its
  defaults are not adopted as market-data thresholds.
- Prometheus documents [staleness](https://prometheus.io/docs/prometheus/latest/querying/basics/)
  and alert persistence via [`for`](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/).
  These are useful monitoring mechanisms, not transaction-bound gate proofs.
- Bybit documents that kline `confirm=true` means a candle is closed in
  [V5 WebSocket Kline](https://bybit-exchange.github.io/docs/v5/websocket/public/kline),
  and recommends periodic ping while acknowledging disconnects in
  [V5 WebSocket Connect](https://bybit-exchange.github.io/docs/v5/ws/connect).
  Its [system-status documentation](https://bybit-exchange.github.io/docs/v5/system-status)
  notes that short interruptions may be absent. Therefore a PONG or empty
  maintenance response cannot independently prove usable market data.
- Python documents that [`time.monotonic()`](https://docs.python.org/3/library/time.html#time.monotonic)
  cannot go backward but has an undefined origin; only differences are valid.
  This supports scheduler use, not persisted causal timestamps.
- MITRE [CWE-367](https://cwe.mitre.org/data/definitions/367.html) describes
  time-of-check/time-of-use races and recommends locking or atomic operations
  where possible. This supports H2 plus a same-transaction local intent; it
  does not make a remote exchange atomic.
- Gray and Lamport's [Consensus on Transaction Commit](https://www.microsoft.com/en-us/research/publication/consensus-on-transaction-commit/)
  describes the participant/agreement requirements of distributed commit. A
  venue API is not a participant in the local SQLite commit protocol.
- [RFC 9162](https://www.rfc-editor.org/rfc/rfc9162.html#section-2.1) defines
  ordered Merkle Tree Hash construction. It supports the blocker and link
  commitments, but does not prove SQL completeness, feed health, or the honesty
  of a compromised local store.

The external sources justify mechanisms and safety boundaries. The exact
repository policy remains conditional engineering. It must be falsified with
adversarial tests, live-compatible shadow evidence, cost-aware downstream
experiments, and later untouched out-of-sample data. Even a completely accepted
V4.2 protocol may reveal that the available trading features contain no stable
economic edge.
