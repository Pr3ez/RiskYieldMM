# V4.4 operational transport-runtime protocol freeze

**Date:** 2026-07-15

**Status:** corrective contracts and the first crash-aware, fail-closed local
operational boundary are implemented and adversarially tested. No real exchange
socket is connected by this checkpoint, and no process/storage crash campaign
has been accepted. It is not production transport authority, does not enable
`EXECUTION_BAR`, does not submit orders, and provides no evidence of predictive
edge or profitability.

**Corrects:**
[`v4_3_transport_subscription_authority_protocol_freeze_2026-07-14.md`](v4_3_transport_subscription_authority_protocol_freeze_2026-07-14.md)

## Executive decision

Do not connect a live WebSocket directly to the V4.3 projection. The operational
audit found four correctness gaps that deterministic fixture tests could not
expose:

1. the handshake digest fields did not freeze whether they committed wire
   octets or a library's parsed/re-serialized objects;
2. monotonic timestamps had no clock-domain identity, so an OS reboot could
   make honest restart termination impossible or incomparable;
3. a session that received no messages left no capture segment, which could
   incorrectly prevent a later valid capture generation from extending the
   partition lineage;
4. a class described as single-writer had SQLite serialization but no process
   lease or application fencing epoch.

V4.4 is a fresh-genesis correction, not an in-place interpretation of accepted
V4.3 records. Class names retain the broad `V4` API family, while canonical
schema, signing, identity, key, manifest, and projection domains are versioned
`V4_4`.

The smallest defensible implementation sequence is:

```text
private runtime directory (0700)
-> nonblocking kernel writer lease on one unchanged inode
-> transactional projection fence epoch
-> full projection verification
-> PROCESS_RESTART reconciliation of every old open session
-> READY (still no network authority)
-> exact TLS/WebSocket handshake evidence committed
-> exact one-topic subscription intent durably committed
-> one-shot permit bound to writer epoch + socket + session + command
-> exact Text-frame dispatch attempt
-> raw-first bounded capture
-> exact ACK binding
-> two completed post-binding bars
-> deterministic health and H1 decision gate
-> H2 remains ABSTAIN
```

## Why the implementation changed before adding a socket

Adding a network library first would have made code appear live while leaving
its evidence semantics ambiguous. The V4.4 correction instead makes each
authority-relevant application subscription send depend on an already
committed local fact. Opening-handshake traffic and WebSocket control frames
remain outside this mediator and require their own driver/control boundary.
This does not create a distributed transaction with Bybit. Once a write begins,
a timeout, exception, or cancellation still has **unknown delivery** and the
intent is never retried. Safety means preventing a false local authority claim,
not claiming exactly-once remote delivery.

## Frozen corrections

### Exact opening-handshake commitment

`TransportSessionAttestationV4` now requires:

```text
handshake_commitment_profile =
  EXACT_DECRYPTED_HTTP1_OPENING_HANDSHAKE_OCTETS_V1

handshake_request_sha256 =
  SHA256(exact decrypted HTTP/1.1 request octets through CRLFCRLF)

handshake_response_sha256 =
  SHA256(exact decrypted HTTP/1.1 response octets through CRLFCRLF)
```

The profile commits bytes, not semantic equivalence and not reconstructed
headers. A future structured commitment requires a new profile and explicit
canonicalization. Certificate validation, hostname validation, status `101`,
`Sec-WebSocket-Accept`, TLS version/cipher, ALPN, extensions, peer certificate,
SPKI, trust-store manifest, collector release, and runtime identity remain
separate signed fields; a transcript hash does not replace those checks.

### Clock-domain comparability

Sessions now carry `monotonic_clock_domain_id`; terminations carry
`detected_monotonic_clock_domain_id`.

- Inside one domain, monotonic values must strictly advance.
- A same-boot successor must retain its parent's domain.
- A cross-domain terminal event is admitted only as `PROCESS_RESTART`, with
  causal wall-clock ordering still required.
- The runtime accepts `ClockEvidenceV4` only from an injected governed source,
  within bounded validity and uncertainty. It never substitutes zero when
  discipline evidence is missing.

Linux documents `CLOCK_MONOTONIC` as time since an unspecified point and notes
that it is unaffected by discontinuous wall-clock changes. The operational
domain ID must therefore commit the current boot/monotonic epoch rather than
pretend values are comparable across reboots.

The repository currently defines and tests the clock-evidence port and
fail-closed admission. The runtime pins one source-manifest identity for its
epoch, but this identity currently appears only in the volatile start report;
it is not yet bound into a signed session or deployment manifest. A governed
chrony/timesync implementation and signed manifest binding are still required
before a provider run can be authority-eligible.

### Empty-session reconnect lineage

The first persisted `CaptureSegmentV3` for a partition may begin at any
positive connection generation, because earlier attested sessions can end
without receiving an application message. Once capture has begun, a later
segment may also skip empty generations only when the projection can traverse
the exact signed transport parent chain and prove that every intermediate
session has the same policy/scope/adapter/partition, collector instance and
boot, and monotonic domain; is terminal; and has zero captured segments. Every
admitted segment must still:

- begin at collector sequence one;
- be the partition's only parentless root;
- use the exact derived partition identity;
- satisfy all existing segment, message, and transport binding invariants.

A second parentless segment remains a fork and is rejected. Missing,
nonterminal, differently bound, or nonempty intermediate sessions make a gap
inadmissible. Full replay independently repeats the same proof.

### Terminal reasons

`BACKPRESSURE` and `STORAGE_FAILURE` are explicit terminal reasons. A bounded
capture queue must never silently drop, overwrite, sample, or coalesce evidence.
Queue saturation fences the session. Storage uncertainty latches authority off
even when the terminal record itself cannot be persisted; the next startup must
reconcile the orphan before becoming ready.

## Two-layer writer fencing

### Kernel lease

`PhysicalTransportWriterLeaseV4` uses a nonblocking exclusive Linux `flock` on
a mode-0600, current-user-owned, single-link regular file beneath a
current-user-owned mode-0700 directory without symlink ancestry. It uses
`O_CLOEXEC`, `O_NOFOLLOW` where available, verifies pathname/inode continuity,
persists only a hash of its random 256-bit token, and fsyncs file and parent
metadata. PID and JSON contents are diagnostic only; neither establishes
ownership.

This remains a local-filesystem, cooperative-process mechanism. Linux `flock`
protects an open-file description/inode, not a logical pathname, and semantics
on NFS or other network/distributed filesystems are outside the accepted
profile.

### Transactional projection fence

The projection adds a mutable, explicitly noncanonical singleton fence with an
active token hash and monotonically increasing generation. After acquiring the
kernel lease, a runtime transactionally claims a new projection epoch. Each
canonical mutation transaction and full verification on that bound store
instance validates the same active token and generation. If a lock pathname is
replaced and another cooperative runtime claims a new epoch, the old bound
connection's next canonical mutation or full verification fails before
appending a receipt. This does not claim that every ordinary read API is
fenced.

The mediator also checks that epoch before permit issuance, immediately before
dispatch, after dispatch completion, and around ACK binding. This is defense in
depth, not a distributed fencing token understood by Bybit: each check
transaction ends before the socket operation. External-side-effect exclusion
still depends on one trusted host, the continuously held local OS lease, and the
private runtime directory. Cross-host writers, hostile same-user path mutation,
an atomic check-plus-remote-write guarantee, and remote enforcement are not
claimed.

The operational fence is deliberately absent from the immutable evidence
ledger: it coordinates which local writer may append; it is not market-data or
trading evidence. A stale active row after process death is expected. Runtime
policy orders projection-fence claim only after `assert_held()` on the kernel
lease, then startup reconciliation terminates prior open transport sessions.
The projection claim API itself cannot prove possession of `flock`; it is a
trusted cooperative boundary, not independent kernel-lease evidence.

## Fenced mediator

`PhysicalTransportRuntimeV4` is dependency-injected and owns the following
ordering:

```text
COLD
  -> STARTING
  -> READY
  -> SESSION_COMMITTED
  -> INTENT_COMMITTED
  -> DISPATCHING
  -> AWAITING_ACK
  -> ACK_BOUND

any active state -> FENCED -> READY (fresh reconnect only)
journal/clock/fence uncertainty -> FAULT_LATCHED
any non-dispatch state -> CLOSED
```

Important properties:

- startup claims the application fence, verifies the full projection, and
  resamples bounded clock evidence before reconciliation and again before
  `READY`, so a slow verification cannot reuse expired startup evidence;
- startup failure best-effort releases the exact application epoch and then the
  kernel lease; a later runtime still verifies and reconciles any uncertain
  committed prefix;
- a send permit exists only after `authorize_outbound_subscription_intent`
  returns from its durable commit, fresh post-commit clock evidence remains
  before the send deadline, and both writer fences are rechecked;
- the permit commits the writer-token hash, socket lease, session, generation,
  intent, command hash, exact command bytes, and deadline;
- a permit is accepted once and cannot cross a reconnect;
- reconciliation, ACK, and terminal idempotency keys retain the complete
  256-bit canonical record/session identities rather than truncated prefixes;
- a caller supplies the socket-lease identity when committing a reviewed
  session and must return the runtime-issued permit/callback identity exactly;
  it cannot originate or alter permit contents. Reuse within one runtime epoch
  is rejected, but no real OS socket is tied to that identity yet;
- dispatch/ACK/backpressure callbacks from an old socket-lease identity are
  rejected without mutating a new session;
- the explicit `send_exact_text_frame(bytes)` port requires one complete
  WebSocket **Text** frame; a generic `send(bytes)` adapter is forbidden because
  many high-level clients choose the Binary opcode. Current synthetic senders
  prove only the port contract, not actual opcode, framing, partial-write, or
  kernel-write semantics;
- any failure after `send_exact_text_frame(command_bytes)` begins is unknown delivery,
  terminates/fault-latches, and never retries the intent;
- an ACK captured before the send-completion callback is buffered, but cannot
  bind until runtime-owned dispatch completion exists and both fences have
  been rechecked;
- only captured WebSocket **Text** messages can become Bybit JSON or ACK
  authority; Binary and Unknown frames remain raw evidence and classify as
  unsupported before JSON decoding;
- ACK timeout is currently poll-driven. Multiple conflicting ACK candidates,
  backpressure, storage failure, explicit termination, and local close remove
  current authority; a real event loop still must wire remote close and socket
  failure callbacks;
- a durable terminal event is required before the mediator can prepare a fresh
  reconnect;
- an untrusted callback cannot originate or control dispatch clocks, signer,
  permit contents, or a projection fence epoch; it returns only runtime-issued
  identity/capability values plus the durable disposition identity.

The current runtime takes a reviewed signed session record from the future
driver boundary. The driver and the helper that hashes exact decrypted opening
handshake octets are not yet implemented; therefore real handshake
observations, Text framing, and raw socket bytes are still unproved.

## Transport-library decision

### Rejected as the authority driver: official `pybit`

The official SDK is useful for ordinary application integration but its
WebSocket implementation does not match this evidence boundary. The reviewed
source parses messages before callbacks, automatically resubscribes stored
commands after reconnect, generates/sends its own request before storing local
subscription state, and contains fallback correlation when a request ID is
absent. Those behaviors conflict with raw-first capture, projection-generated
exact bytes, durable intent-before-send, fresh authorization on reconnect, and
fail-closed exact ACK binding.

### Deferred operational adapter: pinned `websockets` Sans-I/O

The selected future adapter is a pinned `websockets==16.0` Sans-I/O protocol
driven by owned `asyncio` TLS streams. The official integration guide makes
network I/O and asynchronous control flow the integration layer's
responsibility and exposes `data_to_send()` / `receive_data()` boundaries. This
allows the collector to retain exact decrypted opening-handshake bytes, turn
off extensions, avoid environment proxy discovery, own write-completion
timing, and raw-capture application messages before classification.

The dependency is not added by this checkpoint because no operational adapter
is accepted yet. Ambient environment availability is not a reproducible
dependency.

## Provider-specific constraints and conformance gate

Official Bybit documentation currently establishes:

- the Linear public endpoint is
  `wss://stream.bybit.com/v5/public/linear`;
- subscription requests use `op="subscribe"` and `args`, while `req_id` is
  optional in the documented protocol;
- response examples vary by product and include an empty `req_id` example;
- heartbeat guidance recommends a JSON ping every 20 seconds;
- clients should avoid frequent reconnects and stay below 500 connections per
  five minutes per WebSocket domain;
- a kline is closed only when `confirm=true`; supported intervals and
  `kline.{interval}.{symbol}` topics are documented.

V4.4 deliberately requires a non-empty exact echoed request ID even though the
provider does not promise it for every response. That is a **conformance test**,
not a provider guarantee. Testnet and then mainnet must prove the reviewed
Linear endpoint echoes the chosen request ID. Missing or changed behavior
blocks authority; the collector must never guess a topic or bind by arrival
order.

Heartbeats are liveness traffic but still outbound side effects. V4.4 permits
**no outbound heartbeat yet**. A separate durable outbound-control intent,
correlation, deadline, and replay profile must be implemented before the driver
may send JSON ping traffic; until then a session cannot remain
authority-eligible long enough to depend on heartbeats. Inbound Pong/control
evidence may be raw captured, but it cannot be confused with subscription
authority. Automatic Pong/Close behavior must be mediated and tested by the
future driver.

## Crash and adversarial semantics

| Failure boundary | Required result |
|---|---|
| before application-fence claim | no journal or send authority |
| after claim, before verify | `FAULT_LATCHED`; no send |
| open prior session at startup | `PROCESS_RESTART` before `READY` |
| after session commit, before intent | terminal/fresh reconnect; no send |
| after intent commit, before permit construction | intent remains durable; session fenced; never authorize a second intent |
| expired/forged/stale permit | no send; current session fenced where applicable |
| exception/cancellation after send begins | unknown delivery; terminal/fault latch; never retry |
| ACK before send completion | buffer only; bind after causal completion or reject |
| ACK mismatch/ambiguity | terminal; no transport eligibility |
| bounded queue full | `BACKPRESSURE`; no dropped evidence |
| SQLite/storage failure | `STORAGE_FAILURE` if recordable, otherwise `FAULT_LATCHED` |
| lock pathname replacement | a cooperative successor claims a new application generation; the old bound store's next canonical mutation/full verify fails, while the remote-send check-to-send gap remains explicit |
| process kill | stale fence/session expected; next kernel-lease holder reconciles |
| reboot | new monotonic domain; cross-domain `PROCESS_RESTART` only |

## Implemented files

- `riskyieldmm/trading/physical_transport_v4.py`
- `riskyieldmm/trading/physical_market_data.py`
- `riskyieldmm/trading/physical_projection_v4.py`
- `riskyieldmm/trading/physical_transport_lease_v4.py`
- `riskyieldmm/trading/physical_transport_runtime_v4.py`
- focused contract, projection, lease, capture-lineage, and runtime adversarial
  tests under `tests/`

## Acceptance and remaining blockers

Final local verification:

```text
focused V4.4 transport/capture/runtime selection: 183 passed
all physical-authority tests:                      298 passed
full repository:                                 1,523 passed, 32 skipped
```

The focused selection covers strict inbound frame type, classifier replay,
capture lineage and proven empty-generation gaps, transport contracts and
projection, kernel/application fencing, faulty runtime ports, real
SQLite/`flock` ACK binding and lease-loss reconciliation. The full repository
run completed in 84.02 seconds on this workspace. These are local software
tests, not provider conformance, crash-campaign, soak, trading-performance, or
profitability evidence.

This checkpoint accepts only:

- corrected V4.4 immutable record semantics;
- deterministic projection/replay with clock-domain rules;
- first capture after empty prior sessions and capture-lineage gaps proven to
  contain only exact-bound, terminal, zero-capture intermediate sessions;
- kernel and transactional writer fences;
- idempotent startup orphan reconciliation;
- one-shot exact-command permit and fail-closed lifecycle behavior under
  synthetic driver, faulty-journal, lease-loss, deadline, reconnect, and raw
  frame-type adversaries.

It does **not** accept:

- a real TCP/TLS/WebSocket driver or exact handshake-octet capture;
- a governed clock-discipline implementation;
- governed trust-store, release, runtime, deployment, or signing-key manifests;
- live Bybit request-ID conformance;
- raw-first bounded persistence on a real socket;
- an outbound heartbeat/control-intent protocol and mediated automatic
  Pong/Close behavior;
- reconnect-rate/backoff implementation and provider drift monitoring;
- 24-hour, 7-day, 30-day, crash, restart, capacity, or multi-asset soaks;
- H2 execution, order construction, broker/exchange credentials, paper/live
  activation, or profitable trading.

## Next implementation slice

1. freeze the release/runtime/trust-store/clock manifests and key-loading
   boundary;
2. freeze a durable outbound-control/heartbeat profile, including mediation of
   automatic Pong/Close behavior;
3. add the pinned Sans-I/O dependency in an isolated optional transport extra;
4. implement a direct TLS 1.3 client with hostname/certificate validation,
   exact request/response transcript retention, no proxy, no compression, no
   subprotocol, and bounded timeouts;
5. connect the driver to the mediator with one reader, bounded immutable queue,
   raw-before-classification persistence, and socket abort on any ambiguity;
6. run deterministic fake-server tests for split/coalesced handshake reads,
   frames arriving with the final handshake read, partial writes,
   cancellation, stale callbacks, malformed frames, and queue/storage faults;
7. run non-authoritative Bybit testnet/mainnet conformance captures; promote
   nothing if exact request-ID echo or reviewed TLS facts do not hold;
8. only then begin long no-trading soaks and capacity measurements.

## Primary sources

- Bybit, [WebSocket connection, subscription, heartbeat, and connection-limit documentation](https://bybit-exchange.github.io/docs/v5/ws/connect)
- Bybit, [public kline stream and `confirm` finality](https://bybit-exchange.github.io/docs/v5/websocket/public/kline)
- Bybit, [official `pybit` WebSocket stream source at 5.16.0](https://github.com/bybit-exchange/pybit/blob/5.16.0/pybit/_websocket_stream.py)
- websockets 16.0, [Sans-I/O integration guide](https://websockets.readthedocs.io/en/16.0/howto/sansio.html)
- websockets 16.0, [Sans-I/O client reference](https://websockets.readthedocs.io/en/16.0/reference/sansio/client.html)
- IETF, [RFC 6455: The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455.html)
- Python, [`ssl` TLS validation APIs](https://docs.python.org/3/library/ssl.html)
- Python, [`fcntl` / `flock` APIs](https://docs.python.org/3/library/fcntl.html)
- Linux man-pages, [`flock(2)` semantics and network-filesystem qualifications](https://man7.org/linux/man-pages/man2/flock.2.html)
- Linux man-pages, [`clock_gettime(2)` clock semantics](https://man7.org/linux/man-pages/man2/clock_gettime.2.html)
- SQLite, [transaction semantics](https://www.sqlite.org/lang_transaction.html)
- SQLite, [`PRAGMA synchronous`](https://www.sqlite.org/pragma.html#pragma_synchronous)
