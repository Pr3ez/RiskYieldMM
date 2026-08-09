# V4.9C Causal Transport Actor Protocol Freeze

**Date:** 2026-07-17  
**Status:** Bounded local egress checkpoint implemented; non-promotion  
**Roadmap position:** Stage 1 critical corrections, after the V4.9B
driver-derived session authority and before privileged/provider campaigns

## 1. Decision

V4.9C uses one owner-bound session actor and one total durable event order for
all post-handshake transport work. Subscription Text frames, application
heartbeats, automatic RFC Pong and Close output, TLS ciphertext, kernel send
attempts, send results, and layered terminal evidence must not use independent
writers or independent sequence spaces.

The public live factory remains closed. This slice is a local-correctness
candidate only and cannot establish provider authority, live readiness,
completed-bar authority, trading safety, predictive edge, or profitability.

### 1.1 Implemented checkpoint boundary

The bounded implementation now connects one exact V4.9B driver-derived
session to a private runtime-owned actor. The only public subscription entry is
`dispatch_subscription_v49c(idempotency_key=...)`; it accepts no caller sender,
socket, permit, callback, prepared artifact, or wire bytes. Actor activation
fences the legacy subscription and control writers.

The implemented application-egress order is:

```text
durable one-topic intent
→ owner prepares one exact masked WebSocket Text frame (no TLS/socket I/O)
→ actor atomically persists exact wire + deterministic one-shot permit
→ exact owner advances that same artifact through SSLObject/MemoryBIO
→ actor persists the exact TLS ciphertext artifact
→ actor atomically persists kernel attempt + SEND_STARTED
→ owner performs one bounded positive socket.send operation
→ actor atomically persists exact result + SEND_RESOLVED
→ actor persists complete local submission
```

The actor independently decodes the persisted client frame rather than trusting
driver metadata. It requires one final masked frame, canonical payload-length
encoding, no RSV bits or trailing/concatenated frame, and an exact unmasked
opcode/payload hash/length match. Application events are also cross-linked to
the actual durable `OutboundSubscriptionIntentV4`, including authority,
operation ID, Text opcode, command bytes, wall deadline, and preparation time.

SQLite actor batches are bounded to two through eight consecutive events and
use one projection operation clock. Replays must return the exact ordered
records; an insert fault rolls the whole batch and its operation metadata back.
The deterministic actor permit commits the operation, exact wire event, socket
lease, writer-fence token, and writer-fence generation, so a syntactically
valid self-asserted permit fails full-chain validation.

Runtime orchestration serializes the application path, rejects retained
post-upgrade plaintext or pending automatic protocol output, and revalidates
the owner, lease, application fence, actor, intent, permit, and runtime state
after every effectful boundary. An expired preflight is durably terminated
without a kernel attempt. Concurrent backpressure and synchronous close cannot
be overwritten by a late dispatch completion. A positive local send whose
result cannot be persisted aborts the owner and is never replayed.

This is not a complete causal live stream. Runtime ingress-to-parser adoption,
automatic Pong/Close dispatch, actor-ordered ACK and legacy terminal
integration, positive TLS/TCP shutdown, multi-obligation parser output,
queue-depth policy, process-crash/provider/privileged campaigns, and live
factory admission remain open. The current loopback egress test is valid only
when the opening-handshake response contains no retained post-upgrade frame.

## 2. Why the previous seams are insufficient

V4.9A/B deliberately stopped before claiming a complete stream actor. The
remaining gaps are material:

1. A caller-presented `RawIngressCommitV4` can match pending plaintext bytes
   without proving that it is the projection's exact canonical receipt.
2. Parsing a whole ingress batch does not preserve a durable parser cursor or
   prove a frame that spans several durable ingress receipts.
3. Automatic protocol output is retained in memory but is not yet an ordered
   durable obligation.
4. Subscription and control mediation use different permit and sequence
   systems, so their relative stream order isn't proven.
5. `sock_sendall()` success or failure doesn't expose exact positive partial
   progress.
6. WebSocket Close, TLS `close_notify`, TCP half-close/EOF, truncation,
   timeout, and local abort aren't distinct terminal facts.
7. A SQLite commit and a network write cannot form one atomic distributed
   transaction.

## 3. Alternatives considered

### Keep the existing subscription and control writers

Rejected for the V4.9C candidate. Per-writer locks prevent overlap within one
path but cannot prove a total order across subscription, heartbeat, and
automatic protocol output.

### Persist only logical messages and regenerate masked frames after restart

Rejected. Client WebSocket masking changes the exact wire bytes. Regeneration
would make retry and audit evidence ambiguous.

### Treat a consumed permit as proof that no bytes were sent after a crash

Rejected. The process may fail after a positive kernel acceptance and before
recording the result.

### Treat local kernel acceptance as peer delivery

Rejected. A successful `socket.send()` proves only the positive byte count
accepted by the local kernel for that call. It does not prove remote receipt,
TLS processing, WebSocket processing, or exchange acknowledgement.

### One exact owner-bound actor with write-ahead attempts

Selected. The actor serializes all transitions, persists exact prepared bytes,
persists an attempt before invoking the kernel, records every positive partial
result, and treats any attempt without a conclusive result as terminal unknown
delivery. This is conservative and compatible with the previous V4.9B owner
and the next crash/restart and provider-conformance campaigns.

## 4. Frozen event order

Each session event has a gap-free `actor_sequence` beginning at one and the
exact predecessor event ID. The closed event vocabulary is:

```text
RAW_INGRESS_COMMITTED
PARSER_TRANSITION
OUTBOUND_WIRE_PREPARED
WRITE_PERMIT_CONSUMED
TLS_CIPHERTEXT_PREPARED
KERNEL_SEND_ATTEMPT
KERNEL_SEND_RESULT
OUTBOUND_DISPATCH_COMPLETED
TERMINAL_TRANSITION
```

Every event is bound to the exact transport session, socket lease, connection
generation, deployment, application-writer fence, and monotonic clock domain.
Unknown top-level fields, unknown payload fields, substituted payload classes,
sequence gaps, predecessor forks, cross-session causes, and byte/hash
mismatches fail closed.

## 5. Ingress and parser rule

The contract, projection, and session-actor substrate implements the following
rule, but the live runtime read/parser loop is not yet connected. One owner read
produces bounded non-empty plaintext chunks. The projection
commits the exact chunk order before the WebSocket parser sees any byte. The
actor accepts only the store-minted receipt proof returned by that append; an
equal reconstructed object isn't authority.

The parser transition records:

- the absolute byte cursor before and after the transition;
- the exact source receipt slices for every completed frame;
- the retained incomplete tail and its exact source slices;
- emitted frame facts;
- all automatic protocol-output obligations in their original order; and
- parser failure or WebSocket closing state when applicable.

A frame spanning two or more ingress receipts therefore remains attributable
to every exact source byte. A payload substring that resembles a Ping or Close
frame cannot be promoted merely by presenting a local offset.

## 6. Output and send rule

Every logical output kind uses the same actor queue. For application output,
the exact masked WebSocket wire and its deterministic one-shot permit are
persisted atomically before TLS state may advance. TLS accepts only the same
owner-retained wire object, and its resulting ciphertext is persisted as a
separate exact artifact before kernel dispatch. The automatic-output contracts
use the same FIFO, but their runtime dispatch bridge remains open work.

For each ciphertext batch:

1. atomically persist `KERNEL_SEND_ATTEMPT` with its `SEND_STARTED` terminal
   transition and the exact remaining suffix;
2. call non-blocking `socket.send()` once;
3. require a positive integer not exceeding the suffix length;
4. atomically persist `KERNEL_SEND_RESULT` with `SEND_RESOLVED` and that exact
   accepted count; and
5. continue from the unaccepted suffix until complete.

`BlockingIOError`/`EAGAIN` waits for writer readiness within the same absolute
deadline and doesn't fabricate progress. Zero, negative, Boolean, or
over-length results are protocol failures. Cancellation or process loss after
a durable attempt and before its result leaves terminal unknown delivery and
forbids replay.

The reviewed local send budget is now five seconds from durable authorization,
with the ACK budget still ten seconds from that same timestamp. The former
one-second value could expire inside its own intent and pre-send journal path
before a socket call. Five seconds is a provisional fail-closed engineering
bound, not an exchange guarantee; promotion requires target-host latency
distributions and regeneration of any signed manifest that still commits the
rejected one-second profile.

## 7. Layered terminal rule

The pure terminal reducer and actor contracts distinguish at least:

- local or peer WebSocket Close observed/sent;
- local TLS `close_notify` prepared/sent;
- peer TLS `close_notify` observed;
- TCP write-half closed;
- TCP EOF observed;
- abrupt EOF / TLS truncation;
- timeout;
- storage failure;
- transport failure;
- cancellation;
- unknown delivery; and
- clean completion across WebSocket, TLS, and TCP.

After sending a WebSocket Close, application data is forbidden. A raw TCP
half-close cannot substitute for TLS shutdown. Clean completion requires the
applicable WebSocket close exchange, local `close_notify`, peer
`close_notify`, and TCP terminal evidence; EOF before authenticated peer
`close_notify` is truncation, not clean shutdown.

The current runtime has not yet driven that positive TLS/TCP terminal sequence.
Its ACK, timeout, backpressure, and legacy session-termination writes also
remain outside the actor sequence, so the reducer is a validated specification
surface rather than a completed live lifecycle.

## 8. Crash and recovery semantics

SQLite can make projection records atomic with each other, but not with a
network side effect. Recovery therefore replays the actor chain:

- an application wire and permit are one atomic batch, so one cannot survive
  without the other;
- permit without durable TLS ciphertext: no send proven, but the one-shot
  authority isn't silently recreated;
- durable TLS ciphertext without a kernel attempt: no send proven and no
  replay authority is inferred;
- kernel attempt without a result: unknown delivery, terminal fence;
- positive partial result without complete dispatch: unknown remainder,
  terminal fence;
- complete local acceptance without higher-layer acknowledgement: locally
  dispatched only, never peer-delivered;
- incomplete terminal exchange: unclean terminal state.

## 9. Primary-source basis

- [RFC 6455](https://www.rfc-editor.org/rfc/rfc6455.html) defines WebSocket
  framing, control-frame constraints, Ping/Pong behavior, and the closing
  handshake. It doesn't define repository durability or crash recovery.
- [RFC 9846](https://www.rfc-editor.org/rfc/rfc9846.html) is the current TLS 1.3
  specification. Its closure rules require `close_notify` for an orderly
  write-side close; transport EOF without the peer alert cannot prove a
  complete authenticated stream.
- Python's [`socket.send()` documentation](https://docs.python.org/3.12/library/socket.html#socket.socket.send)
  defines the returned local byte count. It doesn't prove peer receipt.
- Python's [`ssl` Memory BIO documentation](https://docs.python.org/3.12/library/ssl.html#memory-bio-support)
  keeps TLS state separate from network I/O and distinguishes clean TLS close
  from abrupt EOF.
- [`websockets` 16 Sans-I/O integration](https://websockets.readthedocs.io/en/16.0/howto/sansio.html)
  requires integrations to feed received bytes, drain generated outputs, and
  serialize operations. It supplies protocol mechanics, not durable authority.
- [SQLite atomic commit](https://www.sqlite.org/atomiccommit.html) supports
  local transaction atomicity only; it doesn't create an atomic commit with a
  remote network action.
- [Bybit V5 WebSocket connection guidance](https://bybit-exchange.github.io/docs/v5/ws/connect)
  specifies the public subscription request/response contract and recommends a
  20-second heartbeat. It does not impose the former one-second local
  authorization-to-send budget.

## 10. Acceptance boundary

Final bounded-checkpoint verification is **156 focused V4.9C and adjacent
staged-transport tests passed** and **612 broad transport/operational tests
passed**. The full repository then passed **2,114 tests with 32 skipped**; its
two warnings are the known Python 3.12 multi-threaded-`fork()` deprecations in
the V4.8B/driver-artifact fork adversaries. The focused set covers contracts,
projection replay and atomic
rollback, actor recovery, partial send, terminal reduction, cancellation,
storage failures, deterministic-permit forgery, exact masked-frame adversaries,
thread/loop/process ownership, real local TLS 1.3 egress, pre-TLS journal
ordering, deadline fencing, concurrent backpressure, close overlap, activation
failure, and positive-result uncertainty. These are local deterministic and
loopback results, not provider or process-crash evidence.
Focused Ruff lint/format, `py_compile`, `git diff --check`, and generated-file
leftover checks are clean for the checkpoint surface.

Even after those tests pass, promotion remains denied pending signed exact
deployment inputs, full-process or immutable-image measurement, privileged
systemd/chronyd validation, provider and certificate-rollover conformance,
crash/restart campaigns, long no-trading soaks, and independent review.
