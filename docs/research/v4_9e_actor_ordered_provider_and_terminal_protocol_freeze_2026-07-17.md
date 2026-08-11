# V4.9E Actor-Ordered Provider and Terminal Protocol Freeze

**Date:** 2026-07-17; bounded local acceptance and post-edit revalidation
recorded 2026-07-18

**Status:** Accepted as a bounded local implementation checkpoint; public live
factory and all operational promotion gates remain closed

**Roadmap position:** Stage 1 critical corrections, after the accepted bounded
V4.9D causal-ingress checkpoint and before privileged deployment,
provider/certificate conformance, process-crash campaigns, and long no-trading
soaks

## 1. Decision

V4.9E is one checkpoint implemented in three ordered internal
slices:

```text
E1: completed application message -> deterministic provider classification
    -> exact subscription ACK binding/completion or ordered ACK timeout

E2: WebSocket Close -> local/peer TLS close_notify
    -> local TCP write-half-close/peer TCP EOF -> layered terminal outcome

E3: projection convergence, legacy-termination bridge, recovery, API sealing,
    and integrated adversarial acceptance
```

E1, E2, and E3 are implementation boundaries, not independently promotable
protocol versions. The bounded local acceptance recorded here covers the
complete E1-to-E3 actor order, full replay, focused and repository-wide
verification, and an explicit final review of the claims in this document.
It is not operational promotion.

The public live factory remains closed throughout V4.9E. This document freezes
a local protocol candidate. It does not establish provider authority, live
readiness, process-crash recovery of an active TLS object, production overload
safety, completed-bar authority, trading safety, predictive edge, or
profitability.

## 2. Confirmed starting point

V4.9D provides durable RAW plaintext adoption, exact cross-RAW frame source
attribution, one-frame-at-a-time WebSocket parsing, and automatic Pong/Close
output through the actor send path. The following gaps are confirmed in the
current implementation and motivate this freeze:

| Current surface | Confirmed limitation | V4.9E requirement |
|---|---|---|
| `physical_transport_runtime_v4.py` parser cursor | A final unfragmented data frame or final Continuation clears retained message bytes before application classification is exposed | Reconstruct one complete message from canonical RAW bytes and ordered parser events, then append exactly one message event |
| V4 runtime ACK callback | `observe_captured_ack()` accepts caller-presented disposition and socket-lease identities | Remove that authority seam; binding must derive from the exact actor-ordered message and deterministic classifier |
| Runtime timeout and termination methods | ACK expiry, generic termination, backpressure fencing, and synchronous close can write outside the actor order | Actor-route or reject every path while the V4.9E actor is active |
| V4.9C actor validator | Positive TLS notify, TCP half-close/EOF, and clean terminal facts are rejected because physical evidence is not integrated | Admit only typed facts derived from the retained TLS driver and Linux socket owner |
| Retained TLS driver | No actor-ordered `SSLObject.unwrap()`/shutdown path exists; unexplained outgoing BIO bytes fail closed | Add write-ahead shutdown authority and exact driver-produced TLS output artifacts |
| Automatic Close marker | `send_eof_after_output` currently reaches WebSocket closing state but does not perform TLS or TCP shutdown | Drive the complete layered terminal state machine |
| V4 projection ACK verifier | Exact schema, request ID, session, generation, partition, manifest, ordering, and deadline checks are already strong once a disposition is supplied | Retain those checks and replace the untrusted bridge into them |

These were the implementation gaps at the start of V4.9E. Sections 11, 12,
and 14 now record the code and local falsification evidence that close this
bounded checkpoint. The deferred operational evidence in Sections 3.4 and 14
is still absent.

## 3. Exact scope and ordered implementation slices

### 3.1 E1 — actor-ordered provider message and ACK

E1 includes:

- exactly one completed application-message identity for every complete
  WebSocket Text or Binary message;
- ordered reconstruction of fragmented messages from canonical RAW receipts
  and parser events, including legal interleaved control frames;
- a bounded aggregate message size and strict incremental UTF-8 validation for
  Text messages;
- deterministic provider classification from exact reconstructed bytes,
  opcode, registered provider profile, and session authority;
- an explicit disposition for every completed application message, including
  malformed, unsupported, non-ACK, heartbeat, and market-data messages;
- exact one-topic Bybit Linear/Inverse subscription-ACK binding;
- atomic ACK binding and subscription-operation completion;
- actor-ordered ACK deadline evaluation and timeout;
- exclusion of pre-binding data from later recovery authority; and
- removal or fencing of caller-presented ACK identities.

E1 does not treat a ranking score, heartbeat Pong, first market-data message,
JSON resemblance, caller callback, or provider `conn_id` as subscription
authority.

### 3.2 E2 — positive layered shutdown

E2 includes:

- exact WebSocket Close receive and send evidence;
- prohibition of later application output after closing starts;
- a write-ahead, owner-bound TLS shutdown operation;
- local TLS `close_notify` generation by the retained `SSLObject`, with exact
  outgoing `MemoryBIO` ciphertext persisted before a kernel send attempt;
- peer TLS `close_notify` observation by the retained TLS driver;
- supported, typed TLS 1.3 post-handshake control output through the same actor
  artifact and send path;
- local Linux `shutdown(SHUT_WR)` through the retained socket owner only after
  full local kernel acceptance of `close_notify` ciphertext;
- peer TCP EOF from a retained-owner `recv()` result of zero;
- clean, truncated, timeout, fatal, storage-failure, and unknown-effect
  outcomes without collapsing their meanings; and
- local-initiated, peer-initiated, and simultaneous Close sequences.

The existing V4.9C names `TLS_CLOSE_NOTIFY_SENT` and `TCP_FIN_SENT` are too
strong if read literally. For V4.9E evidence:

- TLS-engine production of an exact notify artifact is
  `TLS_CLOSE_NOTIFY_PREPARED`; it is not a peer receipt claim;
- full positive `socket.send()` results prove only local kernel acceptance of
  the exact ciphertext;
- successful `shutdown(SHUT_WR)` is `TCP_WRITE_HALF_CLOSED`; it proves the
  local kernel accepted the write-half-close request, not that a FIN was
  observed on the wire or by the peer; and
- only a later retained-owner `recv()` result of zero is `TCP_EOF_RECEIVED`.

V4.9E may implement those meanings with new versioned transition kinds or a
versioned payload phase. It must not silently reinterpret historical V4.9C
rows or promote the old names into stronger physical claims.

### 3.3 E3 — convergence, recovery, and acceptance

E3 includes:

- one gap-free actor order spanning RAW, parser, completed message,
  classification, ACK/deadline, outbound, TLS, kernel, and terminal facts;
- one canonical projection transaction boundary for every atomic group frozen
  below;
- full-store reconstruction from canonical predecessors rather than trusting
  stored hashes or caller identities;
- a one-to-one bridge between the final actor terminal outcome and the legacy
  `TransportSessionTerminationV4` row;
- deterministic restart reconciliation and idempotent replay;
- rejection or actor routing of every legacy ACK, timeout, backpressure,
  generic termination, and close bypass;
- removal of callback/socket/raw-fact injection seams from the public runtime;
- the complete adversarial matrix in Section 11; and
- a final documentation and nonclaim review before acceptance.

### 3.4 Deferred beyond V4.9E

Unless a later amendment explicitly expands this freeze, V4.9E does not
include:

- serializing or resuming a live Python `SSLObject` or WebSocket parser after
  process loss;
- retrying an operation whose TLS, socket-send, or half-close result is
  unknown;
- a production queue-depth, fairness, or overload policy;
- multi-topic subscription authority or partial-success policy;
- a provider guarantee of request-ID echo, `conn_id` uniqueness, duplicate
  behavior, or ACK latency;
- privileged systemd/chronyd/certificate-rollover/provider campaigns;
- process-kill or power-loss campaigns beyond deterministic crash-prefix and
  storage-fault tests;
- long-running no-trading or paper-trading soaks;
- public live-factory admission; or
- any trading, predictive-edge, or profitability conclusion.

After process loss, an open V4.9E session is reconciled conservatively as
`PROCESS_RESTART` or a more specific already durable terminal outcome, the
old owner is never resumed, and a fresh session is required. This is
fail-stop/reconnect recovery, not live TLS-object recovery.

## 4. Frozen actor vocabulary and authority

### 4.0 Narrow E2 vocabulary amendment (2026-07-17)

Implementation review found that the prospective list below did not name a
durable TLS-control kernel-attempt/result pair or a durable peer TLS/TCP
observation. A terminal transition alone cannot safely fill either role: it
would place a positive claim after an unjournaled effect and would not retain
the exact driver/owner predecessor required by Section 4.4. The freeze was
therefore amended before E2 implementation with the following additive V4.9E
event meanings:

```text
TLS_PROTOCOL_OPERATION_STARTED
TLS_PROTOCOL_OPERATION_FAILED
TLS_CONTROL_CIPHERTEXT_PREPARED
TLS_CONTROL_KERNEL_SEND_ATTEMPT
TLS_CONTROL_KERNEL_SEND_RESULT
TLS_SHUTDOWN_OBSERVED
TCP_HALF_CLOSE_ATTEMPT
TCP_HALF_CLOSE_RESULT
```

`TLS_SHUTDOWN_OBSERVED` has a closed observation kind distinguishing an
authenticated peer TLS `close_notify` from a retained-owner zero-length TCP
`recv()`. The TLS-control attempt and result events retain the exact suffix,
ordinal, accepted count, and resulting offset; a positive full-acceptance fact
is derived only from gap-free results covering the complete prepared artifact.
This amendment was additive during implementation. It does not reinterpret an
existing V4.9C event; its acceptance evidence is recorded in Section 11.

The V4.9E actor retains the V4.9D events and adds closed, versioned meanings
equivalent to:

```text
RAW_INGRESS_COMMITTED
PARSER_TRANSITION
OUTBOUND_WIRE_PREPARED
WRITE_PERMIT_CONSUMED
TLS_CIPHERTEXT_PREPARED
KERNEL_SEND_ATTEMPT
KERNEL_SEND_RESULT
KERNEL_SEND_FAILURE
OUTBOUND_DISPATCH_COMPLETED
APPLICATION_MESSAGE_COMMITTED
SUBSCRIPTION_ACK_BOUND
ACK_DEADLINE_EXPIRED
LOCAL_SHUTDOWN_COMMAND_STARTED
LOCAL_SHUTDOWN_DEADLINE_EVIDENCE
TERMINAL_INGRESS_FAILURE
TLS_PROTOCOL_OPERATION_STARTED
TLS_PROTOCOL_OPERATION_FAILED
TLS_CONTROL_CIPHERTEXT_PREPARED
TLS_CONTROL_KERNEL_SEND_ATTEMPT
TLS_CONTROL_KERNEL_SEND_RESULT
TLS_CONTROL_KERNEL_SEND_FAILURE
TLS_SHUTDOWN_OBSERVED
TCP_HALF_CLOSE_ATTEMPT
TCP_HALF_CLOSE_RESULT
TERMINAL_TRANSITION
```

These event meanings and semantic names are frozen for V4.9E. A versioned
payload phase may represent one listed distinction instead of a standalone
event only when the mapping is explicit and one-to-one. Any other name or
semantic change requires an amendment before acceptance. Unknown event kinds,
unknown payload fields, sequence gaps, predecessor forks, cross-session
causes, or identity substitutions fail closed.

For compatibility with the existing pure terminal reducer,
`TLS_CLOSE_NOTIFY_SENT` may be emitted only after an exact
`LOCAL_CLOSE_NOTIFY` artifact has been fully accepted by the local kernel. In
V4.9E it is a compatibility state marker, not proof of wire transmission,
peer receipt, or peer processing. Likewise, `TCP_FIN_SENT` may be emitted only
after the exact successful `shutdown(SHUT_WR)` result and means local TCP write
half-closure, not observation of a FIN on the wire. Unbound historical or
caller-created uses of either marker remain invalid. An
`OPAQUE_POST_HANDSHAKE_RESPONSE` may use the TLS-control prepare/attempt/result
path, but it can never create local-close, TCP-half-close, or clean-terminal
authority.

`APPLICATION_MESSAGE_COMMITTED` combines exact message completion and
deterministic provider classification in one event. `SUBSCRIPTION_ACK_BOUND`
is the exact successful subscription-operation completion fact. Separate
events carrying the same authority are deliberately not added.

### 4.0.1 Prepared-obligation and negative-prefix amendment (2026-07-17)

Adversarial implementation review found three further places where the
positive vocabulary above was not closed under its own durable prefixes:

1. TLS-control ciphertext could exist durably before the compatibility
   `TLS_CLOSE_NOTIFY_SENT` marker, while the generic send-attempt reducer had
   no obligation capable of referring to that prepared artifact;
2. a retained TLS operation could fail, exhaust its absolute deadline without
   a terminal observation, or produce unsendable post-handshake output after
   `SHUT_WR` without one typed actor event; and
3. a half-close syscall error or unresolved outcome could otherwise end at an
   attempt record with no deterministic final successor.

V4.9E therefore freezes these additional meanings before E2 acceptance:

- `TLS_CLOSE_NOTIFY_PREPARED` is a terminal-state compatibility transition
  created only after the exact `LOCAL_CLOSE_NOTIFY` artifact is durable. It is
  preparation authority, not a sent, accepted, peer-observed, or clean fact.
- `TLS_OPAQUE_CONTROL` is an obligation layer used only to close the
  attempt/result/unknown-send grammar for a typed supported non-notify TLS
  control artifact. It can never create Close, half-close, or clean authority.
- Every `TLS_CONTROL_KERNEL_SEND_ATTEMPT` is immediately paired in the same
  actor batch with `SEND_ATTEMPT_STARTED` for the exact prepared obligation.
  Every conclusive positive result is immediately paired with
  `SEND_ATTEMPT_RESOLVED`. An unresolved effect terminates with fixed cause
  `TLS_CONTROL_SEND_OUTCOME_UNKNOWN`; it is never retried or reclassified as
  accepted.
- `TLS_PROTOCOL_OPERATION_FAILED` has four physical failure kinds:
  `DRIVER_ERROR`, `DEADLINE_EXPIRED_NO_OBSERVATION`,
  `DEADLINE_EXPIRED_AFTER_PROGRESS`, and
  `UNSENDABLE_POST_HANDSHAKE_OUTPUT_AFTER_SHUT_WR`. Physical evidence and
  deadline interpretation are intentionally separate. Its independent
  `deadline_classification` is one of `BOTH_DUE`, `CLOCK_DISAGREEMENT`, or
  `OWNER_EVIDENCE_BEFORE_BOTH_CLOCKS` when applicable. Consequently,
  `CLOCK_DISAGREEMENT` is not a TLS physical failure kind. Projection maps the
  two dimensions to the fixed timeout, clock-integrity fatal,
  after-progress-timeout, driver-error, or unsendable-output terminal cause.
  Unsendable output retains the exact nested driver/owner/socket evidence and
  ciphertext digest/octet summary, is always non-clean, and must not enter a
  kernel-send path after write-half closure.
- A negative `TCP_HALF_CLOSE_RESULT` maps to fixed cause
  `TCP_HALF_CLOSE_ERROR`. A started half-close without a conclusive result
  maps to `TCP_HALF_CLOSE_OUTCOME_UNKNOWN`. Neither permits `TCP_FIN_SENT`, a
  repeated syscall on replacement authority, or clean convergence.
- Failure to mint or validate the pure owner-local one-shot token before a
  half-close attempt creates no syscall claim and converges with fixed cause
  `TCP_HALF_CLOSE_TOKEN_PREPARATION_ERROR`. It must not fabricate an attempt,
  result, ambiguity, or retry authority.

The actor verifier recomputes, rather than merely compares, sealed owner
identities. The half-close token is derived from the session, TLS-control
sequence, exact notify artifact hash, and octet count. Its result identity is
derived from that token, the fixed Linux `SHUT_WR` ABI value, acceptance flag,
and closed error code. A TCP-EOF observation additionally binds the retained
kernel-socket identity and recomputes the owner observation identity from the
exact driver observation. Same-shape caller values are not authority.

The local WebSocket Close owner capability is deliberately no-argument and
fixed to status code 1000 with an empty reason. It returns the exact prepared
wire object already admitted to the staged FIFO and performs no TLS or socket
I/O. Caller-selected close payloads remain outside V4.9E.

### 4.0.2 Command authority and deadline-evidence amendment (2026-07-17)

Integrated runtime review found that deriving a shutdown deadline immediately
before each layer was insufficient. It left no durable authority before the
first owner mutation and could let WebSocket, TLS, and TCP operations refer to
different clock observations. V4.9E therefore adds exactly one
`LOCAL_SHUTDOWN_COMMAND_STARTED` event before any local-command owner mutation.
Its deterministic, predecessor-bound identity commits:

- the fixed local WebSocket Close code 1000 and empty reason commitment;
- one bounded caller timeout;
- one actor-sampled governed wall/BOOTTIME start observation; and
- the corresponding absolute wall and BOOTTIME shutdown deadlines.

The command is admitted only for a quiescent OPEN WebSocket state or after a
complete peer-first WebSocket closing handshake. A session admits at most one
such command. Every subsequent local Close wire, retained TLS operation,
TLS-control artifact and send, TCP half-close token/attempt, and bounded peer
shutdown poll must bind the exact command event and its unchanged BOOTTIME
deadline. Runtime code may consume these committed values but may not inject,
resample, extend, or translate the deadline. Expiry while any required layer
is still missing maps to one command-level `TIMEOUT`; it does not become clean
because some earlier layers completed. Both the governed wall and BOOTTIME
observations must be due for that classification. If exactly one is due, the
actor records a distinct clock-integrity `FATAL` outcome using the original
disagreeing observation; it must not choose whichever clock is favorable.

Deadline evidence is closed by the last effect that can be proved:

- an exact owner pre-syscall check with no driver or kernel progress is sealed
  as operation-specific `DEADLINE_EXPIRED_NO_OBSERVATION` and maps to
  `TIMEOUT`;
- a send deadline reached after one or more conclusive would-block results and
  no positive kernel acceptance is sealed with the exact ciphertext suffix,
  offset, deadline, and would-block count as
  `DEADLINE_EXPIRED_NO_KERNEL_ACCEPTANCE`; it maps to `TIMEOUT` and grants no
  retry authority;
- terminal WebSocket-close ingress or a TLS shutdown poll that accepted
  positive ciphertext before its deadline expired is sealed with the exact
  operation, received digest/octet count, and owner plus driver evidence
  identities; it maps to a distinct typed shutdown `TIMEOUT` and the
  capability is consumable exactly once;
- a final pre-syscall BOOTTIME check that prevents `shutdown(SHUT_WR)` produces
  a conclusive negative half-close result and command `TIMEOUT`, never
  `TCP_FIN_SENT` or a generic socket error.

When the actor has durably written a kernel attempt but can prove that its
effect callback was not invoked, replay must retain a typed no-effect outcome;
it must not claim `UNKNOWN_SEND`. Cancellation or failure after callback
invocation, an invalid or ambiguous return, and any unsealed generic
`TimeoutError` remain conservative unknown/fatal paths. Python exception class
or message text alone is never physical evidence.

Finally, after a durable peer Close, an owner failure while preparing or
sending the mandatory automatic Close response may projection-latch terminal
I/O only long enough for the actor and legacy projection to commit their one
signed non-clean pair. The owner is then aborted. This narrow rule does not
weaken the pre-V4.9E fail-closed behavior for Pong, application output, or an
invalid automatic-output candidate. Sealed send evidence also distinguishes a
parser-derived automatic Close response from a local-command Close; neither
origin may be substituted for the other during replay.

### 4.0.3 Implemented terminal-owner authority closure (2026-07-18)

Final adversarial review exposed one additional authority requirement: after
a real retained-driver or retained-owner mutation, the journal still needs an
exact clock observation to classify and persist the outcome. Granting that
clock from hashes, generic actor state, or a special-case failure enum would
reintroduce a caller-controlled terminal seam. The accepted implementation
therefore uses the following closed mechanism:

- the terminal owner clock/provider/authorizer/restore capabilities are an
  all-or-none set available only to the exact retained session owner;
- the owner consumes an exact one-shot post-mutation handoff and validates the
  nested driver -> owner -> socket evidence chain before authorizing a journal
  clock observation;
- same-process actor reconstruction with the same retained live owner selects
  the latest durable exact owner evidence across TLS observation, deadline
  evidence, terminal ingress, TCP half-close, and unsendable-output families,
  then recomputes the full predecessor chain and proves that owner had already
  been authorized;
- restored authority can never change from false to true merely because a
  stored row has matching fields or hashes;
- if the retained driver has already entered `TLS_SHUTDOWN_V49E`, that state is
  preserved so peer `close_notify` and TCP EOF can still be observed;
- otherwise, a private pre-shutdown terminal-journal fault latch may move the
  bound driver to `FAULT_LATCHED` solely to retain identity authority. It
  grants no TLS, socket, read, write, retry, or replacement-owner I/O; and
- every affected payload recomputes nested driver and owner identities, and
  unsendable-output replay additionally binds the exact kernel-socket
  identity and ciphertext evidence;
- peer `close_notify` and later TCP EOF observations must retain one identical
  owner kernel-socket identity even when each row is independently
  self-consistent; and
- same-process recovery of a durable observation or marker obtains fresh
  governed terminal clock samples. It never fabricates a later timestamp by
  adding one to a previously stored monotonic value.

This closure is why physical TLS failure kind and dual-clock classification
remain two independent dimensions. Owner evidence observed before both clocks
are due is preserved as physical evidence and classified explicitly; it is
not rewritten into a more convenient timeout or clock-disagreement fact.
Disconnected-owner restoration before strict retained-owner validation and
true process-loss recovery without the in-memory owner remain denied. They
require the later durable supervisor/process-restart contract; V4.9E neither
falls back on `ENOTCONN` nor promotes a stored hash into clock authority.

### 4.1 Committed-message identity

One `APPLICATION_MESSAGE_COMMITTED` event, its actor envelope, and its exact
store-minted predecessors must commit directly or transitively at least:

- the exact session, lease, connection generation, capture partition, physical
  scope, and monotonic clock domain;
- Text or Binary opcode;
- ordered contributing parser-event IDs;
- ordered canonical RAW source slices for every payload byte;
- exact payload length and SHA-256 digest;
- `received_at` and `received_monotonic_ns`, equal to the last contributing
  byte's canonical RAW observation in the same clock domain; the first-byte
  observation remains derivable from the ordered sources;
- a store-minted message identity.

Full replay must reconstruct the payload from canonical RAW bytes, traverse
the exact parser-event chain, remove frame headers/masking as appropriate,
respect fragmentation order, and verify length and digest. Matching caller
bytes, offsets, or hashes are never authority.

A control frame may appear between data fragments and retain its own parser
and automatic-output obligations. It never contributes bytes or identity to
the fragmented application message. No completed-message event exists before
the final fragment.

### 4.2 Classification within the message commit

The same `APPLICATION_MESSAGE_COMMITTED` event references one exact canonical
classifier result. Its payload commits:

- registered provider-adapter and classifier-profile identities;
- message identity, opcode, length, and digest;
- exhaustive disposition kind;
- normalized provider-message identity when applicable;
- classifier version and deterministic schema identity; and
- the exact canonical capture/message/disposition records produced by that
  classification.

Classification is a pure function of canonical message evidence and the
registered profile. Current intent state may decide whether an ACK can bind,
but it must not change what the message is classified as.

### 4.3 ACK and deadline identity

An ACK binding must reference:

- the exact one-topic outbound intent and dispatch completion;
- exact request ID and ordered one-topic manifest committed by that intent;
- exact completed Text message and classifier disposition;
- exact echoed non-empty request ID;
- an exact five-key JSON object with no extra fields: `success` is Boolean
  `true`, `ret_msg` is `""`, `op` is `"subscribe"`, `conn_id` is a non-empty
  string, and `req_id` is the exact echoed request ID;
- session, lease, generation, partition, scope, deployment, and policy;
- the intent's governed monotonic deadline; and
- the completed message's last-byte local observation time.

The first valid canonical binding row and `SUBSCRIPTION_ACK_BOUND` event commit
in the same transaction as the application-message commit. That actor event is
the subscription-operation completion fact. A duplicate byte-identical append
is idempotent. A second message, reused request ID, conflicting `conn_id`,
copied disposition, wrong session, missing/empty/mismatched request ID, wrong
opcode, wrong schema, or failed success response cannot bind.

Bybit documents `req_id` as optional and its Linear/Inverse example contains
an empty value. V4.9E deliberately imposes a stricter local profile: the
outbound request uses one non-empty request ID and only an exact echo binds.
This is a RiskYieldMM correlation rule, not a provider-wide guarantee.

While one subscription is pending, an ACK-shaped `op="subscribe"` response
with failed success, wrong/missing request ID, conflicting connection ID, or a
schema near-miss commits its exhaustive disposition and an actor-ordered
provider/integrity failure in the same E1-B transaction. It does not remain
silently pending until a more favorable response or timeout. An unrelated
well-formed market-data or heartbeat message is classified normally and does
not terminate the pending operation.

### 4.4 Terminal observation identity

Every positive terminal fact must carry a typed, store-minted predecessor:

- WebSocket Close received -> exact Close parser event and source slices;
- WebSocket Close prepared/sent -> exact Close wire, permit, ciphertext,
  attempts, results, and completed local dispatch;
- local TLS notify prepared -> exact owner-bound TLS shutdown attempt and exact
  ciphertext artifact drained from its outgoing BIO;
- local TLS notify fully accepted -> exact positive kernel result chain for
  the full artifact;
- peer TLS notify received -> exact driver-owned TLS input operation and
  authenticated TLS end-of-data observation;
- TCP write-half closed -> exact owner-bound half-close attempt and successful
  `shutdown(SHUT_WR)` result;
- TCP EOF received -> exact owner-bound positive `recv()`-zero observation;
  and
- clean terminal -> every required WebSocket, TLS, and TCP predecessor.

Caller-selected terminal enums, timestamps, socket descriptors, TLS bytes,
source events, or success flags are never accepted as physical evidence.

## 5. E1 frozen information flow

The only admitted positive provider-message flow is:

```text
canonical RAW receipts already durable
-> exact frame parser events in actor order
-> final Text/Binary parser event durably creates one pending message obligation
-> reconstruct exact message bytes from canonical RAW/parser predecessors
-> deterministically classify under the registered provider profile
-> atomically append canonical message/classification + application actor event
-> if and only if it is the exact current in-deadline ACK:
     atomically append binding + subscription completion in that same commit
-> otherwise retain the exhaustive classification without authority
```

### 5.1 Fragmentation and message bounds

The aggregate message bound is exactly 1,048,576 payload octets and 4,096 data
frames. It applies across all fragments, not separately to each frame. The
parser must reject a fragment that would cross either bound before allocating
or appending an unbounded aggregate. UTF-8 state advances incrementally across
Text continuations. Binary messages are exhaustively classified but cannot
satisfy the JSON subscription-ACK profile.

An ordinary complete market-data message, malformed JSON, JSON array, JSON
scalar, unknown object, heartbeat, provider error, duplicate ACK, or schema
near-miss must still produce one deterministic disposition. “Ignored” means a
recorded disposition, never silent discard.

### 5.2 No retroactive ACK authority

An ACK observed before its exact intent or before that intent's dispatch
completion may be captured and classified but can never bind retroactively.
Data observed before a valid binding likewise remains pre-binding evidence;
later binding does not make it eligible for recovery or trading inputs.

### 5.3 Deadline race rule

The governed monotonic deadline is the actor-ordering authority. The committed
wall receipt must also be at or before the wall deadline; disagreement between
the two clock representations fails closed rather than choosing the favorable
one. A message is in time only if its last contributing RAW byte was durably
observed in the intent's monotonic domain at or before the committed deadline.

The actor must not let a deadline command overtake an earlier admitted RAW
receipt whose bytes could complete the current message. Before committing
`ACK_DEADLINE_EXPIRED`, it drains all causally earlier admitted ingress through
message finalization. A message whose final contributing byte is after the
deadline is late even when its first fragment arrived earlier. Once timeout is
committed, no later replay or callback can revive the session.

This rule is intentionally local and conservative. The receipt timestamp is
when the retained process durably observed bytes, not a claim about exchange
send time, network arrival time, or kernel-buffer arrival time.

## 6. Frozen atomic transaction and effect boundaries

SQLite transactions can make local records atomic with each other. They
cannot be atomic with TLS state mutation or a Linux socket syscall. V4.9E
therefore freezes the following boundaries:

| Boundary | Records that commit together | External/in-memory effect between commits | Failure or crash interpretation |
|---|---|---|---|
| E1-A parser transition | one parser event plus resulting cursor/source attribution; a final Text/Binary transition also creates one replayable pending-message obligation in actor state | one bounded parser mutation | persistence uncertainty fault-latches the session; a durable final parser event without E1-B remains a pure local pending obligation, not a silent message |
| E1-B message finalization | application-message event plus canonical message/capture/classification records and—only for one valid current ACK—canonical binding plus `SUBSCRIPTION_ACK_BOUND` | deterministic reconstruction/classification only; no network effect | none of the E1-B records may survive alone; commit uncertainty fault-latches; exact committed replay is idempotent |
| E1-C timeout | deadline event, subscription failure state, terminal transition, and legacy termination bridge when E3 is present | no network effect | may commit only after all earlier admitted ingress is finalized; once committed it is final |
| E2-A Close receive | Close parser event, cursor-to-closing state, `WS_CLOSE_RECEIVED`, and any deterministic Close-response obligation | parser mutation | rollback or uncertainty fault-latches; no TLS/TCP shutdown inferred |
| E2-B Close send authorization | exact masked Close wire, one-shot permit, and `WS_CLOSE_PREPARED`/equivalent obligation | no TLS/socket effect | all-or-nothing; absence of the batch forbids TLS advance |
| E2-C TLS operation start | unique owner-bound TLS operation attempt, purpose, cause, and precondition identities | subsequent `SSLObject.read()`/`unwrap()` may mutate TLS state | missing result after restart is unknown TLS state; terminate/fence, never replay on a replacement object |
| E2-D TLS operation result | exact outgoing BIO artifact(s), operation result, and `TLS_CLOSE_NOTIFY_PREPARED`, typed supported-control cause, or `TLS_PROTOCOL_OPERATION_FAILED` | TLS state has already mutated | persistence failure is storage uncertainty; driver error/deadline/unsendable-after-`SHUT_WR` remain typed non-clean outcomes; no socket send and no positive sent claim |
| E2-E kernel send start | exact ciphertext suffix, attempt, and `SEND_ATTEMPT_STARTED` | one bounded `socket.send()` | attempt without result is unknown delivery; never retry |
| E2-F kernel send result | exact positive accepted count, result, and `SEND_ATTEMPT_RESOLVED`; full-obligation marker when complete | kernel may have accepted bytes | commit failure after a positive result is unknown delivery; abort owner |
| E2-G TCP half-close start | unique owner/lease-bound `TCP_HALF_CLOSE_ATTEMPT` and prerequisite accepted notify identity | one `shutdown(SHUT_WR)` | attempt without result is ambiguous local half-close; never claim clean or repeat on a replacement owner |
| E2-H TCP half-close result | exact syscall success/failure and, only on success, `TCP_WRITE_HALF_CLOSED`; negative/unknown outcomes carry their fixed terminal cause | kernel has processed or may have processed the syscall | persistence failure after success is ambiguous; fail-stop, no synthesized success; negative or unproved identity never creates `TCP_FIN_SENT` |
| E2-I peer TLS end | driver observation, source TLS-input operation, observation time, and `TLS_CLOSE_NOTIFY_RECEIVED` | TLS state has already processed peer bytes | persistence failure fault-latches; TCP EOF alone cannot replace this fact |
| E2-J peer TCP end | owner observation, zero-length stream `recv()` result, observation time, and `TCP_EOF_RECEIVED` | kernel has returned EOF | persistence failure fault-latches; no clean outcome inferred |
| E3-A final convergence | final terminal actor event and exactly one legacy `TransportSessionTerminationV4` row | no new network effect | neither may survive alone; replay returns the exact pair or rejects corruption |

The E1-A/E1-B split is intentional. The final parser event is already a
canonical, replayable predecessor and therefore may survive as one pending
pure-local message obligation. E1-B is broad but bounded to one complete
application message; it prevents durable classification without its actor
cause and prevents an ACK binding from surviving without exact message and
classification evidence. Splitting E1-B further requires amending this freeze
with an equally strong replayable intermediate state before code is accepted.

Cancellation never converts an uncertain effect into permission to retry.
After an effect may have occurred, cleanup is shielded only long enough to
record the strongest available outcome; failed persistence remains a terminal
uncertainty.

## 7. E2 layered close and shutdown order

### 7.1 WebSocket layer

[RFC 6455 Section
5.5.1](https://www.rfc-editor.org/rfc/rfc6455.html#section-5.5.1) defines Close
as a control frame, while [Section
7.1](https://www.rfc-editor.org/rfc/rfc6455.html#section-7.1) defines the
closing handshake and permits simultaneous closing. Sending or receiving
Close starts the closing handshake; after both sides have sent and received
Close, the underlying connection is closed. V4.9E therefore requires both
exact Close facts before a clean local TLS shutdown can be completed.

The local branch is:

```text
exact local Close obligation
-> exact Close ciphertext
-> every kernel attempt resolved
-> full local kernel acceptance of the Close ciphertext
```

The peer branch is:

```text
exact peer Close parser event
-> exact Close code/reason digest retained when present
```

Once either branch starts closing, new application Text/Binary output and new
subscription operations are forbidden. Mandatory Close completion and already
authorized protocol output retain actor priority.

### 7.2 TLS layer

[RFC 8446 Section 6.1](https://www.rfc-editor.org/rfc/rfc8446.html#section-6.1)
defines `close_notify` as orderly closure of one TLS direction and requires it
before closing that write side unless an error alert was already sent. A
transport close before peer `close_notify` cannot prove all sent data was
received.

The local TLS branch is:

```text
both WebSocket Close facts + local Close fully kernel accepted
-> durable owner-bound TLS shutdown attempt
-> retained SSLObject.unwrap() / shutdown state progression
-> exact outgoing MemoryBIO close_notify ciphertext
-> durable ciphertext artifact
-> write-ahead send attempt(s) and exact result(s)
-> full local kernel acceptance of the notify artifact
```

The peer TLS branch remains readable after the local write side starts
closing. `SSLObject.read()`/`unwrap()` may require more input or output. Peer
TLS end-of-data is positive only when the retained TLS engine authenticates
and processes `close_notify`. A raw socket EOF or Python `SSLEOFError` without
that alert is truncation.

Python's `SSLObject` performs no network I/O; it exchanges bytes through
`MemoryBIO`, all operations are nonblocking, and `unwrap()` does not return a
socket. `SSLWantReadError` and `SSLWantWriteError` are state-machine outcomes,
not permission for an unjournaled socket read or write.

OpenSSL documents shutdown as two steps—send local `close_notify`, receive peer
`close_notify`—which may occur in either order. Its return/state semantics do
not replace V4.9E evidence: actor facts still require exact BIO artifacts,
kernel results, input causes, and owner observations.

### 7.3 Supported TLS 1.3 post-handshake output

No receive path may opportunistically drain the outgoing BIO to the socket.
Every positive TLS-control output must have:

- one retained-driver operation with a typed purpose;
- an exact actor predecessor, such as a TLS input receipt or shutdown attempt;
- exact outgoing BIO bytes and digest;
- a registered supported-output policy;
- durable ciphertext before a kernel attempt; and
- the same partial-send, deadline, cancellation, and uncertainty rules as all
  other ciphertext.

Shutdown-generated `close_notify` is mandatory. Any other post-handshake
output is admitted only when its OpenSSL/Python behavior has a deterministic
local harness and a typed actor cause. Unknown or unexplained BIO output keeps
the V4.9D fail-closed behavior; V4.9E must not weaken that check into “send any
pending TLS bytes.”

After a successful `shutdown(SHUT_WR)`, no TLS output is sendable regardless
of whether OpenSSL can still produce it while processing peer input. Such an
artifact is retained only as the typed
`UNSENDABLE_POST_HANDSHAKE_OUTPUT_AFTER_SHUT_WR` failure evidence described in
Section 4.0.1. It must not enter the kernel-send path and can never be treated
as completion of an earlier control obligation.

### 7.4 TCP layer

Linux `shutdown(SHUT_WR)` disallows further transmissions on the retained
full-duplex socket. It does not close the read direction and does not prove
peer receipt. V4.9E calls it exactly once, through the sealed owner, only after
full local kernel acceptance of the TLS notify artifact.

The owner continues bounded reads. Linux stream `recv()` returning zero after
a nonzero requested length is the peer orderly transport EOF observation. It
does not by itself prove TLS `close_notify`; the TLS fact must already exist
for a clean result.

### 7.5 Clean and non-clean outcomes

`CLEAN_ALL_LAYERS` requires all of:

```text
local WebSocket Close prepared and fully kernel accepted
+ peer WebSocket Close parsed
+ local TLS close_notify prepared and fully kernel accepted
+ peer TLS close_notify authenticated and observed
+ local TCP write half closed successfully
+ peer TCP EOF observed
+ no unresolved send/TLS/half-close attempt
+ no prior final failure outcome
```

Peer TLS `close_notify` before peer WebSocket Close is WebSocket truncation.
TCP EOF before peer TLS `close_notify` is TLS truncation. A timeout while
waiting for any missing layer is timeout, not clean. Storage failure, fatal
TLS/protocol error, unknown send, and ambiguous half-close remain distinct
terminal causes even when later cleanup produces additional observations.

## 8. E3 projection convergence and legacy bridge

### 8.1 One final writer

While the actor is active, these legacy runtime calls must either enqueue an
actor command or reject invocation:

```text
observe_captured_ack(...)
expire_ack_if_due()
terminate_current(...)
fence_backpressure(...)
close()
```

No synchronous `close()` may claim a clean WebSocket/TLS/TCP exchange. A new
async actor-owned shutdown operation is required for the positive path. A
forced synchronous teardown may abort/fence locally, but it must record a
non-clean reason.

### 8.2 Final outcome mapping

The final actor outcome and legacy termination row commit together. The
implemented mapping is frozen as:

| Actor outcome/cause | Legacy reason |
|---|---|
| clean, local Close first | `LOCAL_CLOSE` |
| clean, peer Close first | `REMOTE_CLOSE` |
| clean, simultaneous Close | origin of the first durable Close actor event; actor sequence breaks the tie |
| ACK deadline | `ACK_TIMEOUT` |
| storage failure | `STORAGE_FAILURE` |
| backpressure policy fence | `BACKPRESSURE` |
| process restart reconciliation | `PROCESS_RESTART` |
| explicit replacement | `SUPERSEDED` |
| truncation, fatal protocol/TLS/socket error, unknown send, or ambiguous half-close | `TRANSPORT_ERROR` |

For clean Close, `close_code` and `close_reason_digest` come from the initiating
Close event; both Close events remain available in actor history when their
payloads differ. `detected_at` and monotonic detection fields come from the
decisive physical or deadline observation, not from the later recording time.

There must be exactly one pair. A legacy row without the exact final actor
event, two legacy rows, a reason mismatch, a close-code/digest mismatch, or a
cross-session timestamp source fails full verification.

### 8.3 Recovery

On reopen, projection verification reconstructs:

1. canonical RAW and parser chains;
2. every complete application message from source bytes;
3. deterministic classification;
4. exact ACK/deadline state;
5. every outbound artifact and kernel result;
6. every typed TLS/TCP terminal predecessor; and
7. the one final actor/legacy termination pair.

Committed pure-local steps may be returned idempotently. No TLS or socket
effect is repeated. An attempt without a conclusive result remains unknown and
forces a fresh session. A dead session never becomes current authority merely
because replay later reconstructs a historical ACK.

## 9. Critical crash-prefix interpretations

| Last durable/effect boundary | Required recovery interpretation |
|---|---|
| RAW durable, parser event absent | RAW remains evidence; continue only in the same proven live actor/driver, otherwise process-restart fence |
| final parser mutation, E1-A commit absent/uncertain | parser state unproved; fault-latch, no classification or output |
| final parser event durable, E1-B absent | one pending pure-local message obligation; reconstruct/classify idempotently; after process loss any historical binding cannot revive the terminated session |
| E1-B commit durable, reply to caller lost | replay returns exact message/classification/binding result without duplicate events |
| pre-deadline RAW queued, deadline requested | finalize the earlier RAW before deciding timeout |
| timeout durable | final; later data or callback cannot revive |
| Close parser durable, response obligation absent | recover pure local authorization only if actor rules prove it; no inferred send/TLS fact |
| TLS operation attempt durable, result absent | TLS state unknown after process loss; no replay on a replacement SSLObject |
| TLS engine produced notify, artifact commit fails | storage uncertainty; no socket write and no sent claim |
| ciphertext artifact durable, kernel attempt absent | no send proven; no inferred retry authority |
| kernel attempt without result | unknown delivery; terminal fence |
| positive kernel result cannot commit | unknown delivery; abort owner |
| half-close attempt durable, syscall result absent | ambiguous local half-close; no repeat and no clean result |
| peer notify observed, journal fails | fault-latched storage uncertainty; EOF cannot repair it |
| TCP EOF observed, journal fails | fault-latched storage uncertainty; no clean result |
| final actor event/legacy pair transaction uncertain | reopen must find the exact pair or reject/quarantine; never append a competing pair blindly |

Deterministic injected failures must cover every prefix above. Full process
kill, host reboot, filesystem fault, and power-loss campaigns remain a later
promotion gate and must not be implied by unit-test crash prefixes.

## 10. Rejected alternatives

### Classify only the final frame payload

Rejected. A fragmented message spans multiple parser events and RAW receipts;
the final frame alone is not the application message.

### Let a callback provide the disposition to bind

Rejected. Correct-looking IDs do not prove that exact actor-ordered bytes
produced that disposition on this session.

### Bind an ACK captured before its intent once the intent appears

Rejected. That would reverse causality and permit stale or injected control
traffic to authorize a later command.

### Timeout solely by callback processing time

Rejected. Backlog could make a durably observed in-time ACK appear late, or a
partially received message appear complete. The last contributing byte's
governed monotonic observation and actor queue order are required.

### Call `unwrap()` and write its BIO output directly

Rejected. TLS mutation and ciphertext would bypass the write-ahead actor send
protocol and could not be reconciled after failure.

### Interpret pending outgoing BIO bytes as automatically safe

Rejected. Their mere existence does not identify cause, policy, order, or send
authority. Unsupported output remains fail closed.

### Close the raw socket immediately after WebSocket Close

Rejected. It omits TLS `close_notify`, can create truncation ambiguity, and
collapses local close request, peer TLS closure, and peer TCP EOF.

### Treat `shutdown(SHUT_WR)` as observed FIN or peer receipt

Rejected. The syscall changes the local socket direction. It supplies neither
packet-level evidence nor remote observation.

### Reuse synchronous generic termination for a clean close

Rejected. A clean outcome requires asynchronous observations across three
layers and cannot be minted by a caller-provided reason.

### Mark E1 or E2 accepted independently

Rejected. ACK authority without ordered terminal handling, or terminal
handling without converged replay/API sealing, leaves a materially incomplete
live protocol.

## 11. Required acceptance matrix

Every row below has bounded local evidence on the accepted 2026-07-18
worktree. “Passed” here means deterministic in-process/unit/integration
falsification only. It does not satisfy any deferred process-kill, privileged
host, real-provider, capacity, soak, paper-trading, or production gate.

| Area | Required proof | Primary harness placement |
|---|---|---|
| Complete message | Exactly one message event after the final Text/Binary fragment; exact cross-RAW reconstruction; interleaved control frame excluded; incomplete/oversize/invalid UTF-8 rejected | V4.9D ingress/parser-byte suites plus `test_trading_physical_projection_v49e_provider_commit.py` |
| Deterministic classification | Every complete message has one exact disposition; same-length byte/hash/source/fragment substitutions fail replay | provider-commit projection and runtime provider-integrity suites |
| Exact ACK | real local TLS subscription -> exact provider ACK -> message/classification/binding/completion order; malformed, binary, absent/empty/wrong request ID, extra field, false success, duplicate, copied, and foreign-session ACK do not bind | provider-commit/provider-integrity suites plus retained V4 ACK projection adversaries |
| Deadline race | earlier in-time RAW cannot be overtaken; final byte after deadline is late; committed timeout cannot revive; ACK before intent never binds later | V4.9E runtime command/timeout and actor-contract suites |
| Shutdown command authority | exactly one predecessor-bound command precedes local owner mutation; all WS/TLS/TCP artifacts retain its identical deadline; both-dual-clock due, either disagreement direction, no-observation, would-block-only, partial-progress, and pre-`SHUT_WR` expiry remain distinct and replayable | terminal actor/session, owner-capability, runtime-timeout, and terminal-projection suites |
| API sealing | no public socket, callback, disposition, terminal enum, TLS bytes, syscall result, or source-fact injection; legacy bypasses reject/actor-route | extend actor/runtime contract suites |
| WebSocket Close | local-, peer-, and simultaneous-close order; exact Close payload; no later application output; Close dispatch fully accepted before local TLS shutdown | V4.9D Close/session plus V4.9E terminal-runtime suites |
| Local TLS notify | real `SSLObject`/`MemoryBIO` shutdown; WantRead/WantWrite; exact artifact; arbitrary BIO output remains rejected; notify never starts before WS prerequisites | `test_trading_physical_transport_tls_v49e_shutdown.py` |
| Peer TLS notify | driver-derived observation only; notify before peer WS Close truncates; forged callback/source rejected | TLS shutdown and terminal runtime suites |
| TLS post-handshake output | supported typed control follows artifact/attempt/result order; unexplained output remains fail closed | TLS shutdown suite |
| TCP half-close | sealed owner, exact one `SHUT_WR`, only after notify acceptance; descriptor/lease/thread/loop/deadline/cancel/error adversaries; failure has no positive result | `test_trading_physical_transport_linux_owner_v49e_shutdown.py` |
| TCP EOF | owner-derived stream `recv()` zero only; EOF without TLS notify truncates; half-close success does not synthesize EOF | owner and terminal runtime suites |
| Clean convergence | every required layer present, no unresolved attempt, one final actor/legacy pair; each missing-layer permutation fails | terminal reducer plus `test_trading_physical_transport_runtime_v49e_terminal.py` |
| Negative terminal outcomes | timeout, fatal, storage, truncation, unknown send, ambiguous half-close, backpressure, restart, and supersession remain distinguishable | terminal reducer/runtime/projection suites |
| Atomicity | insert fault at every row of E1-B, Close authorization, attempts/results, and final pair leaves no half-batch | extend session-actor and actor-projection suites |
| Crash prefixes | every Section 9 prefix reopens deterministically without repeated TLS/socket effects or positive fact synthesis | all new V4.9E suites; full process-kill campaign remains later |
| Full replay | reconstruct messages and terminal predecessors from canonical bytes/results; reorder, omit, duplicate, cross-link, same-shape forge, and direct DB mutation fail | provider-commit projection plus `test_trading_physical_transport_projection_v49e_terminal.py` |
| Regression/nonclaim | all V4.9A-D and V4 authority tests remain green; public factory closed; no live/trading claim appears | focused plus full repository suite and documentation audit |

The final evidence groups were run serially where retained Linux-owner/live
TLS harnesses could otherwise compete for local resources:

| Evidence group | Result | Matrix coverage |
|---|---:|---|
| Full repository regression after post-edit revalidation | 2,335 passed, 32 skipped, 3 explained warnings in 2,283.06 s | all rows, five added adversaries, and prior-gate regression |
| Final 20-file protocol/owner/TLS/session matrix | 287 passed in 500.61 s | command, API sealing, WebSocket/TLS/TCP order, deadline classification, nested evidence, owner recovery, unsendable output, legacy bypass |
| Projection/provider plus authority-adversarial matrix | 146 passed in 426.67 s | message/classification/ACK, atomicity, replay mutation, clock transaction rollback, prior projection gates |
| Terminal projection suite | 23 passed in 309.88 s | final convergence, legacy pair, negative outcomes, replay and corruption |
| Runtime shutdown-command suite | 11 passed in 187.59 s | durable command identity, fixed deadline, local/peer ordering, no bypass |
| Live terminal/negative-pair/terminal-ingress group | 8 passed in 214.07 s | real retained owner/driver terminal paths and non-clean pairing |
| Focused actor/session post-edit amendment | 39 passed in 1.23 s | same-socket shutdown observations, governed recovery clocks, unavailable-clock fail closure, append-only prefix adoption |
| Actor contract suite | 62 passed in 0.46 s | event grammar, reordering, fragmentation, duplicate command, structural forgeries |
| Exact peer-first plus local-deadline regression pair | 2 passed in 52.36 s | peer-first TLS state preservation and durable no-observation deadline evidence |
| Authority adversarial suite | 6 passed in 6.84 s | transaction-clock/receipt rollback and authority substitutions |
| Public-factory denial suite | 5 passed in 0.63 s | gate precedence and close-before-reject behavior |

The three full-suite warnings are expected Python 3.12 multi-threaded
`fork()` deprecation warnings in the chronyd-provenance,
operational-runtime-artifact, and deadline-capability harnesses. They are not
test failures, but replacing fork-based test setup remains later hygiene.

The existing
`test_actor_chain_rejects_unbound_positive_tls_terminal_fact` contract remains
valid: unbound positive facts must still fail. V4.9E adds acceptance only for
facts whose exact driver/owner predecessors survive full verification.

## 12. Implemented code and test surfaces

The V4.9E implementation is concentrated primarily in:

- `riskyieldmm/trading/physical_transport_actor_v49c.py`;
- `riskyieldmm/trading/physical_transport_session_actor_v49c.py`;
- `riskyieldmm/trading/physical_transport_runtime_v4.py`;
- `riskyieldmm/trading/physical_transport_tls_v49.py`;
- `riskyieldmm/trading/physical_transport_linux_v4.py`;
- `riskyieldmm/trading/physical_transport_terminal_v49c.py`;
- `riskyieldmm/trading/physical_projection_v4.py`; and
- `riskyieldmm/trading/__init__.py` only for private/internal exports required
  by tests; no public live-factory admission is granted.

The dedicated implementation evidence includes:

- `tests/test_trading_physical_projection_v49e_provider_commit.py`;
- `tests/test_trading_physical_transport_runtime_v49e_provider_integrity.py`;
- `tests/test_trading_physical_transport_runtime_v49e_command.py`;
- `tests/test_trading_physical_transport_runtime_v49e_timeout.py`;
- `tests/test_trading_physical_transport_runtime_v49e_terminal.py`;
- `tests/test_trading_physical_transport_runtime_v49e_negative_pair.py`;
- `tests/test_trading_physical_transport_runtime_v49e_terminal_ingress.py`;
- `tests/test_trading_physical_transport_projection_v49e_terminal.py`;
- `tests/test_trading_physical_transport_actor_v49e_terminal_contract.py`;
- `tests/test_trading_physical_transport_actor_v49e_two_dimensional_failure.py`;
- `tests/test_trading_physical_transport_actor_v49c_contracts.py`;
- `tests/test_trading_physical_transport_session_actor_v49e_terminal.py`;
- `tests/test_trading_physical_transport_tls_v49e_shutdown.py`;
- `tests/test_trading_physical_transport_linux_owner_v49e_shutdown.py`;
- `tests/test_trading_physical_transport_v49e_deadline_capabilities.py`;
- `tests/test_trading_physical_transport_v49e_nested_send_evidence.py`;
- `tests/test_trading_physical_transport_v49e_owner_capabilities.py`;
- `tests/test_trading_physical_transport_v49e_unsendable_output.py`; and
- `tests/test_trading_physical_transport_runtime_v49e_legacy_bypass.py`.

Existing V4.9C/D reducer, actor, session, projection, TLS, owner, runtime, and
ACK tests remain mandatory regression evidence and were included in the
full-repository and focused matrices in Section 11.

## 13. Primary-source basis and limits

- [RFC 6455 Section
  5.5.1](https://www.rfc-editor.org/rfc/rfc6455.html#section-5.5.1) and
  [Section 7.1](https://www.rfc-editor.org/rfc/rfc6455.html#section-7.1) define
  the WebSocket Close frame, closing handshake, simultaneous Close behavior,
  and underlying-connection transition. They do not define local actor
  records, transactions, or crash recovery.
- [RFC 8446 Section
  6.1](https://www.rfc-editor.org/rfc/rfc8446.html#section-6.1) defines TLS 1.3
  closure alerts, independent write-side closure, and the truncation ambiguity
  when transport closure precedes `close_notify`. It does not prescribe this
  repository's TCP lifecycle or evidence schema.
- Python 3.12's [`SSLObject` and Memory BIO
  documentation](https://docs.python.org/3.12/library/ssl.html#memory-bio-support)
  documents socket-free TLS state progression, nonblocking WantRead/WantWrite
  behavior, `MemoryBIO`, `unwrap()`, and strict unexpected-EOF reporting. It
  does not make a TLS operation atomic with SQLite or a socket syscall.
- OpenSSL's [`SSL_shutdown()`
  documentation](https://docs.openssl.org/3.1/man3/SSL_shutdown/) describes
  local and peer `close_notify` as two steps that may occur in either order,
  including nonblocking/incomplete shutdown. OpenSSL state flags are trusted
  library observations, not evidence of kernel or peer receipt.
- Bybit's [V5 WebSocket connection
  documentation](https://bybit-exchange.github.io/docs/v5/ws/connect) documents
  public endpoints, subscription request/response examples, optional
  `req_id`, `conn_id`, heartbeat examples, and disconnect guidance. It does
  not guarantee exact request-ID echo for every Linear response, ACK latency,
  duplicate semantics, or `conn_id` uniqueness.
- Linux [`shutdown(2)`](https://man7.org/linux/man-pages/man2/shutdown.2.html)
  defines `SHUT_WR` as disabling further transmissions on the local socket
  direction. Linux
  [`recv(2)`](https://man7.org/linux/man-pages/man2/recvmsg.2.html) documents a
  zero return on a stream socket after peer orderly shutdown. Neither syscall
  proves application- or TLS-layer peer processing.
- SQLite's [atomic commit
  documentation](https://www.sqlite.org/atomiccommit.html) supports local
  transaction atomicity. It does not create a distributed transaction with
  OpenSSL, the kernel, the network, or Bybit.

These primary sources support protocol and platform mechanics. The actor
vocabulary, broad E1-B transaction, one-topic exact-echo profile, last-byte
deadline rule, no-ambiguous-retry policy, legacy bridge, and fail-stop crash
interpretations are RiskYieldMM engineering decisions. They require local
falsification and later operational evidence; the sources do not prove them
correct or profitable.

## 14. Acceptance boundary and exact nonclaims

V4.9E is accepted only as the bounded local implementation checkpoint defined
by this freeze. The acceptance review found:

1. E1, E2, and E3 are implemented as one actor-ordered checkpoint without an
   interim promotion claim;
2. the Section 6 effect boundaries and Section 9 prefixes have deterministic
   local fault/replay coverage;
3. the Section 11 matrix has named passing evidence;
4. projection replay rejects mutation, reordering, omission, direct-row
   corruption, and cross-authority substitution;
5. `ruff check riskyieldmm/trading tests/test_trading*.py`,
   `ruff format --check riskyieldmm/trading tests/test_trading*.py` (115 files),
   `python -m compileall -q riskyieldmm/trading tests`, and
   `git diff --check` pass;
6. the full repository suite passes with 2,335 passed, 32 intentional skips,
   and the three explained Python 3.12 fork warnings in Section 11;
7. the final actor/legacy termination bridge has one validated writer;
8. legacy ACK, terminal, close, and source-evidence bypasses reject or remain
   actor-routed;
9. the two-dimensional TLS physical/deadline contract, generalized exact
   owner-evidence clock restoration, and nested driver/owner/socket evidence
   survive their adversarial matrices; and
10. the public live factory still closes any structurally admitted socket and
    raises before launch, pending all later promotion gates.

This evidence does not include a process-kill, host, provider, overload, soak,
or trading campaign. A broader lint command over unrelated non-V4.9E test
families still reports pre-existing HTF/RPF/TA findings; the scoped V4.9E
trading lint and the full behavioral repository suite are green. Those
unrelated findings were not silently rewritten as part of this checkpoint.

Even successful V4.9E local acceptance would not establish:

- provider request-ID behavior or certificate rollover on the target service;
- resilience to real process kill, host reboot, disk/power failure, packet
  loss, proxy behavior, or network partitions;
- adequate queue capacity, fairness, latency, or long-run stability;
- correct completed-bar authority or decision-time feature availability;
- safe order execution, paper-trading fidelity, or portfolio risk control;
- predictive signal, out-of-sample edge, profitability, or suitability for
  live capital; or
- public live-factory admission.

## 15. DONE repository worklog handoff

This section is the repository fallback worklog row for the bounded V4.9E
checkpoint.

- **Name:** V4.9E actor-ordered provider and terminal protocol
- **Status:** DONE and revalidated for bounded local acceptance; operational
  promotion remains closed
- **Scope:** Stage 1 critical corrections; E1 completed-message/classification/
  ACK/deadline order, E2 WebSocket/TLS/TCP layered shutdown, and E3 replay,
  termination convergence, recovery, and API sealing
- **Linear Issue:** RIS-274 fallback thread. Dedicated issue creation was
  blocked by the Linear workspace's free-plan issue limit. START/RESUME was
  recorded in comment `cb85b439-0efe-48ad-80fb-98e20cc0dece`; DONE with the
  technical summary, artifacts, metrics, nonclaims, and remaining gates was
  recorded in comment `2e3476d1-7f46-4b54-9333-0236cac45f54`. The post-edit
  revalidation START and final 2,335-test DONE evidence are comments
  `69df0be4-f5e0-4c4b-a8fd-37df56a74a6c` and
  `b0feb64a-03d4-482d-99ff-a2302f4a9153`.
- **Summary:** The full E1-to-E3 V4.9E protocol is implemented and accepted
  against the bounded local matrix in Sections 11 and 14. Physical TLS failure
  evidence remains independent from dual-clock classification; exact nested
  driver/owner/socket identities and generalized latest-owner-evidence clock
  restoration close the final terminal journal seam. Post-edit revalidation
  additionally requires one owner socket across every shutdown observation,
  fresh governed terminal clocks for recovered marker/convergence rows, and
  append-only prefix adoption. The public live factory remains closed.
- **Artifacts:**
  `docs/research/v4_9e_actor_ordered_provider_and_terminal_protocol_freeze_2026-07-17.md`,
  `docs/research/trading_prediction_system_diagnosis_and_redesign_2026-07-14.md`,
  `docs/research/README.md`, and `README.md`
- **Key Metrics:** 2,335 passed, 32 skipped, 3 explained warnings in the full
  repository; 287 final protocol/owner/TLS/session tests; 146
  projection/provider/authority tests; scoped lint, format, compilation,
  whitespace, and public-factory denial gates passed
- **Next Actions:** keep the live factory closed; complete privileged
  systemd/chronyd and provider/certificate campaigns, real process-crash and
  power-loss testing, queue/capacity/latency validation, long no-trading and
  paper-trading soaks, then separately validate completed-bar authority and the
  trading decision pipeline before any promotion decision
- **Date:** 2026-07-18

No external Notion write is claimed. The Notion connector was unavailable in
this session, so this durable repository row is the explicit fallback rather
than an invented external synchronization claim.
