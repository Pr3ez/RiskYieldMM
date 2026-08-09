# V4.6 durable outbound-control mediator protocol freeze

**Date:** 2026-07-15  
**Status:** bounded implementation freeze; no provider socket, public-data
authority, H2, order path, or profitability claim  
**Predecessor:**
[`v4_5_governed_deployment_and_outbound_control_protocol_freeze_2026-07-15.md`](v4_5_governed_deployment_and_outbound_control_protocol_freeze_2026-07-15.md)

## Decision

V4.6 inserts an immutable, durable **consumed write permit** between exact
pre-TLS WebSocket-byte preparation and the only admitted writer callback:

```text
durable raw ingress
-> typed RFC trigger or typed parser failure
-> exact logical control intent
-> exact masked pre-TLS WebSocket frame held in owned memory
-> durable one-shot permit consumption
-> at most one local writer invocation
-> signed SENT or UNKNOWN_DELIVERY observation
```

The permit commit is the irrevocable local authorization boundary. A process
restart, cancellation, expired deadline, replaced writer fence, missing result,
or uncertain write never rearms it. This deliberately prefers possible
non-delivery over duplicate stream output.

The permit proves neither that the callback was invoked nor that bytes reached
TLS, the kernel, a NIC, the peer TCP stack, the peer WebSocket parser, or the
provider application. The design provides no distributed transaction and makes
no exactly-once claim.

## Why this design

Three alternatives were compared.

| Alternative | Result |
|---|---|
| Treat `OutboundControlWirePreparedV4` as the spent slot | Safe only if every prepared orphan is abandoned forever, but it conflates byte preparation with write authorization and loses unattempted obligations unnecessarily |
| Add one immutable `OutboundControlWritePermitConsumedV4` | **Selected.** It preserves the append-only projection, identifies the pre-write boundary, distinguishes prepared-only from permit-consumed prefixes, and has deterministic no-retry recovery |
| Add a mutable leased transactional outbox | Rejected for this slice. An expired `INFLIGHT` item cannot safely be retried after a possible stream write; forbidding reclaim reduces the safety boundary to the immutable permit plus redundant mutable state |

SQLite cannot atomically commit a record with a TLS/socket side effect. The
current single-writer `BEGIN IMMEDIATE`, rollback-journal `DELETE`, and
`synchronous=EXTRA` profile remains unchanged. SQLite documents one concurrent
writer, immediate write-transaction acquisition, and the additional directory
sync supplied by `EXTRA` in rollback mode. These properties support the local
permit commit, subject to correct filesystem, VFS, `fsync`, hardware, and
anti-rollback assumptions; they do not make the socket write transactional.

The decision also rejects a conventional retrying outbox because official AWS
guidance explicitly warns that outbox publishers may duplicate messages and
therefore require idempotent consumers. No equivalent provider-side
deduplication contract exists for these WebSocket control bytes.

## Primary-source constraints

- [SQLite transaction control](https://www.sqlite.org/lang_transaction.html)
  permits only one simultaneous writer and documents `BEGIN IMMEDIATE` as an
  immediate write transaction.
- [SQLite `synchronous`](https://www.sqlite.org/pragma.html#pragma_synchronous)
  documents the rollback-journal durability distinction and the extra
  containing-directory synchronization performed by `EXTRA`.
- [SQLite atomic commit](https://www.sqlite.org/atomiccommit.html) explains the
  filesystem, flush, and hardware assumptions beneath crash atomicity.
- [`websockets` 16 Sans-I/O integration](https://websockets.readthedocs.io/en/16.0/howto/sansio.html)
  requires sequential protocol access, serialized network writes, and writing
  every item returned by one drain before beginning another write.
- [`websockets` 16 `Protocol.data_to_send()`](https://github.com/python-websockets/websockets/blob/16.0/src/websockets/protocol.py)
  transfers and clears the protocol's pending write list; the mediator must
  take ownership of those exact bytes before persistence.
- The same pinned source records parser failures in `parser_exc`; a
  `ProtocolError` generates a protocol-error Close rather than normally
  escaping `receive_data()`.
- [RFC 6455 section 7.1.7](https://www.rfc-editor.org/rfc/rfc6455.html#section-7.1.7)
  requires a failed connection to stop processing peer data and permits an
  appropriate Close frame when the connection was established.
- [RFC 6455 status code 1002](https://www.rfc-editor.org/rfc/rfc6455.html#section-7.4.1)
  denotes termination for a protocol error.
- [RFC 9293](https://www.rfc-editor.org/rfc/rfc9293.html) defines TCP as the
  transport byte stream and permits send-side buffering; local submission is
  not evidence of provider application processing.
- [AWS transactional outbox guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html)
  requires duplicate-aware consumers, which this provider control path does
  not expose.

## Frozen invariants

### Permit

1. The exact intent and exact prepared-wire records must already be canonical.
2. Permit consumption occurs after the prepared-wire receipt and strictly
   before both wall-clock and monotonic send deadlines.
3. Current deployment, session, socket lease, OS lease, application writer
   fence, connection generation, monotonic domain, and side-effect-open state
   are checked inside the permit transaction.
4. The canonical permit-record identity is the only `permit_id`; there is no
   caller-chosen second nonce or identifier.
5. Intent ID, prepared-wire ID, permit ID, and attempt ordinal one are unique.
6. A permit loaded during restart is evidence only. Only the exact object
   returned by a successful live commit may reach the in-memory writer path.
7. No SQLite transaction remains open across the writer callback.
8. A permit without a result is never classified as definitely attempted or
   definitely unattempted. It is `PERMIT_CONSUMED_RESULT_MISSING`, fences the
   session, and is never retried.

### Result

1. `dispatch_started_at` and its monotonic counterpart are sampled strictly
   after the durable permit commit returns and immediately before invoking the
   writer; the result binds both those start clocks and the exact earlier
   permit-consumption clocks.
2. `SENT` means only that the reviewed local writer reported full submission of
   the exact pre-TLS batch.
3. Any exception, cancellation, timeout, short submission, TLS failure, or
   other uncertain observation after writer invocation is
   `UNKNOWN_DELIVERY`. An explicit short return may preserve its exact prefix
   length. An exception or cancellation records `bytes_submitted_to_tls=null`;
   it never fabricates zero when a partial prefix may already have crossed the
   call boundary.
4. Result and termination persistence are non-authorizing continuations. They
   may be admitted after the send deadline or original deployment expiry when
   they bind an exact permit that was valid when consumed.
5. Late continuation does not admit a stale/replaced application writer fence.
   If the writer loses ownership, the result remains missing and restart
   recovery handles the orphan conservatively.
6. Recovery never fabricates `SENT`, `UNKNOWN_DELIVERY`, exact start clocks, or
   an exact submitted-byte count.
7. A result first persisted after a session-termination record is admitted only
   when the complete writer observation strictly predates terminal detection
   in wall time and the same monotonic domain. Cross-domain late results fail
   closed. Conversely, termination detection cannot be backdated to precede an
   already durable dispatch outcome.

### Typed protocol failure

The first bounded failure kind is pinned `ProtocolError("incorrect masking")`.
Because V4.6 does not yet persist the Sans-I/O parser cursor or cross-read
source spans, this cause is admitted only for ingress sequence one at byte
offset zero: the first post-handshake WebSocket header. The cause record must
independently bind exact prior raw ingress whose header has the
server-to-client MASK bit set. It commits the pinned parser class and message
digests plus the exact code-1002 Close payload. A caller-selected offset or a
generic hash is not a sufficient cause; MASK-looking payload bytes cannot be
promoted into parser-boundary evidence.
Because the parser must stop at that first failure, no RFC control trigger at
any later offset in the same raw ingress batch may coexist with the failure;
append order and canonical replay both enforce the exclusion.

Other parser failures, UTF-8 failures, payload limits, EOF, internal errors,
and unrepresentable cross-read state are not relabeled as this cause. They
remain fail-closed with zero protocol-error output until a typed contract and
the correct RFC close code are frozen for each case.

## Bounded mediator state machine

```text
COLD
  -> OPEN
  -> RAW_COMMITTED
  -> FAILURE_COMMITTED
  -> INTENT_COMMITTED
  -> WIRE_PREPARED
  -> PERMIT_CONSUMED
  -> DISPATCHING
  -> OPEN | CLOSING | FAULT_LATCHED
```

One actor/lock serializes protocol drain, persistence, and writer access. Stale
socket lease or connection-generation callbacks are rejected before clock
sampling, parser/drain access, journal mutation, or writer access. The writer
port accepts only the exact committed permit and its exact ordered pre-TLS
chunks; it exposes no generic `send()` method.

Caller cancellation after permit consumption does not rearm the obligation.
The owner completes terminalization when possible; otherwise it remains fault
latched for restart reconciliation.

## Deliberately bounded automatic output

Pinned `websockets` 16 can produce multiple ordered outputs from one input
drain. In particular, a coalesced Ping followed by Close yields Pong then Close,
while Close followed by Ping yields only Close. The V4.5 one-frame wire record
cannot truthfully represent the former as one obligation.

V4.6 therefore accepts exactly one nonempty automatic WebSocket frame per
mediation operation. Multiple frames, a mixed `SEND_EOF`, extra bytes, an
unmasked client output, or opcode/payload mismatch fence the session and cause
zero writer calls. Supporting multi-output drains requires a later immutable
ordered-obligation-batch contract; output is never silently dropped,
reordered, combined, or partially permitted.

## Crash-prefix policy

| Durable prefix | Restart interpretation and action |
|---|---|
| Raw/trigger/failure only | Never feed stored bytes into a new live parser; terminate the old session |
| Intent without wire | Do not regenerate masking or output; terminate |
| Wire without permit | No write was authorized; abandon the old socket generation and terminate |
| Permit without result | Write invocation is unknowable; fence, terminate, and never retry |
| `SENT` result | Preserve the signed local observation; terminate the old process generation |
| `UNKNOWN_DELIVERY` result | Preserve terminal uncertainty; terminate and never retry |

Process restart always replaces the old socket/session generation. A prepared
wire is never sent by a restarted process even when no permit exists.
Orphan classification is explicitly session-scoped and reports the durable
session, socket, connection-generation, and writer-fence bindings. A terminal
old session retains its orphan IDs as audit evidence but cannot block a fresh
session; its `has_active_unresolved_control` flag is false and no historical
permit becomes writable again.

## Acceptance tests

- Contract round-trip and mutation rejection for the typed failure and permit.
- Exact first-post-handshake masked-server-header proof for
  `INCORRECT_MASKING`; later ingress, nonzero or payload-selected offset, wrong
  cause, close code, reason, payload, or session/fence binding fails.
- Permit exact-wall and exact-monotonic boundary rejection.
- Unique intent/wire/permit/attempt and exact dispatch linkage.
- Fault injection at canonical append, typed insert, batch finish, and commit
  boundaries.
- Zero writer calls before a committed permit.
- Exactly one writer call for one live returned permit.
- Stale callback, replaced fence, malformed drain, multi-output drain, and
  permit substitution produce zero writer calls.
- Exception or cancellation after writer invocation yields one signed
  `UNKNOWN_DELIVERY` with an unknown submitted-byte count when storage remains
  available and never retries; explicit short returns retain their exact
  count.
- Result persistence failure fault-latches; reopen reports an unresolved
  consumed permit and never writes it.
- Dispatch outcome remains admissible after deadline/deployment expiry as an
  exact non-authorizing continuation.
- A pre-terminal writer outcome may be persisted after termination only with
  strict same-domain proof; a post-terminal outcome, cross-domain late result,
  or retroactively backdated termination is rejected.
- Full canonical replay and typed-table bijection reject missing, extra,
  reordered, tampered, cross-session, or cross-generation records.
- Existing Close, UNKNOWN_DELIVERY, prospective-capture, health, and H1
  fail-closed tests remain green.

## Measured implementation result

The bounded slice is implemented in:

- `riskyieldmm/trading/physical_transport_control_v4.py` for typed failure,
  permit, and dispatch-result contracts;
- `riskyieldmm/trading/physical_projection_v4.py` for durable admission,
  replay, bijection, chronology, and session-scoped orphan classification;
- `riskyieldmm/trading/physical_transport_control_runtime_v4.py` for the
  serialized no-network mediator; and
- the `test_trading_physical_transport_control_v4_6_*` suites plus the control
  runtime suite for contract, corruption, crash-prefix, cancellation, and
  real-store restart adversaries.

Verification on 2026-07-15 produced:

- **50/50** dedicated V4.6 tests passed;
- **90/90** combined V4.5/V4.6 control regression tests passed;
- **302/302** authority, transport, and gate tests passed;
- **394/394** physical tests passed; and
- **1,686** repository tests passed with **32 skipped**.

All touched control files pass Ruff, Ruff format, and `py_compile`; the complete
workspace diff passes `git diff --check`. These are local executable-contract
results. They do not widen the authority or nonclaims below.

## Known prerequisites not solved here

The following remain blockers for a real provider socket:

- a durable runtime-session-to-socket binding created at session commit rather
  than lazily asserted by the first control record;
- a raw-source-span contract for frames and parser failures crossing multiple
  committed TLS reads;
- an ordered multi-obligation drain/batch contract;
- durable heartbeat scheduling, exact/weak/ambiguous response dispositions,
  timeout, and the one-outstanding rule;
- typed WebSocket Close, `SEND_EOF`, TCP half-close/full-close, timeout, and
  abort lifecycle;
- moving the original subscription command behind the same exact pre-TLS
  serialized writer, eliminating its older logical-text sender as an alternate
  path;
- the real pinned Sans-I/O/TLS adapter, measured deployment artifacts, strict
  typed clock/boot adapter whose samples carry and prove the monotonic domain,
  process-kill and storage-power-loss campaigns, provider
  conformance, and no-trading soaks.

Until these are closed, V4.6 is a local ordering and falsification slice only.
It does not authorize a provider connection.

## Explicit nonclaims

V4.6 does not prove socket identity, TLS acceptance, kernel or peer delivery,
provider processing, exactly-once delivery, complete RFC 6455 handling,
deployment reproducibility, host integrity, clock truth, data correctness,
market-data freshness, H1/H2 eligibility, predictive edge, safe execution, or
profitability.
