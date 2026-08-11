# V4.3 transport-session and subscription-authority protocol freeze

> **Corrective successor (2026-07-15):** V4.3 remains the historical local
> projection checkpoint, but it is not eligible for operational collector use.
> The V4.4 correction defines exact handshake-hash input, explicit monotonic
> clock domains, empty-session reconnect lineage, startup reconciliation, and
> two-layer writer fencing. See
> [`v4_4_operational_transport_runtime_protocol_freeze_2026-07-15.md`](v4_4_operational_transport_runtime_protocol_freeze_2026-07-15.md).

**Date:** 2026-07-14

**Status:** protocol frozen and focused-accepted as a local, non-activating
projection over deterministic records and fixtures. This checkpoint does not
prove a production collector performed the real TLS/socket/send/receive
sequence, does not establish operational transport authority, does not activate
live trading, and does not change the V4.2 rule that `EXECUTION_BAR` is
`ABSTAIN`-only.

**Predecessor:**
[`v4_2_physical_health_and_gate_protocol_freeze_2026-07-14.md`](v4_2_physical_health_and_gate_protocol_freeze_2026-07-14.md)

**Scope:** prospective Bybit mainnet public Linear WebSocket kline transport
for the reviewed completed-provider-final one-minute source profiles. The
first implementation remains deliberately narrow; a multiplexed all-asset,
all-timeframe transport is a later protocol.

## Decision

V4.3 closes the local canonical transport-correlation gap left explicit by
V4.2. It does not close the operational proof gap for a deployed collector. A captured
Bybit-shaped `success=true` message, a caller-supplied connection label, or a
`subscription_manifest_hash` is not proof that this collector durably intended
the exact topic, sent that request on the current authenticated transport, and
received the acknowledgement on the same session.

The frozen architecture introduces five immutable canonical records:

1. `TransportSubscriptionPolicyV4`;
2. `TransportSessionAttestationV4`;
3. `OutboundSubscriptionIntentV4`;
4. `SubscriptionAckBindingV4`;
5. `TransportSessionTerminationV4`.

The records form this authority graph:

```text
registered transport policy
           |
           v
verified WSS/TLS session attestation --------------------+
           |                                             |
           v                                             v
durably committed exact one-topic outbound intent   session termination
           |                                             |
           v                                             |
network send [outside SQLite; outcome can be uncertain]  |
           |                                             |
           v                                             |
raw ACK durably captured on the same session              |
           |                                             |
           v                                             |
deterministic ACK binding --------------------------------+
           |
           v
two provider-final completed bars admitted after the binding
           |
           v
V4.3 physical-health integration retaining V4.2 reducer semantics
           |
           v
clock-owned DECISION_INPUT gate only
           |
           v
EXECUTION_BAR remains ABSTAIN
```

The selected design has two distinct durable layers:

- a registered, locally reviewed desired transport policy exists before a
  connection is opened;
- a session-specific exact outbound intent is committed before its WebSocket
  send.

The policy commits what the local projection recognizes as reviewed; it is not
yet a governance approval. The intent proves what the trusted collector record
was prepared to send on one attested session. The acknowledgement binding
proves that one later captured provider response matched that intent on the
same recorded session. No one layer substitutes for the others. Actual
intent-before-network-send enforcement remains unproved until the production
collector exists and passes crash and live-provider acceptance.

The local database and a remote exchange cannot participate in one atomic
transaction. V4.3 therefore represents uncertain outcomes explicitly and
prefers a fresh fenced session over ambiguous retry. It does not claim
exactly-once remote delivery.

## Evidence grade and non-claims

The following distinctions are binding:

- **Confirmed V4.2 implementation fact:** the local health reducer already
  requires a current-connection subscription-ACK disposition and two clean
  completed bars, but the ACK is associated through capture metadata rather
  than a persisted outbound request and authenticated session record.
- **Confirmed provider documentation:** Bybit documents the public subscribe
  request shape, optional `req_id`, several product-specific response examples,
  heartbeat guidance, connection/argument limits, and kline `confirm`
  finality. It does not document the stronger correlation and durability
  guarantees required here.
- **Frozen V4.3 repository contract:** only the five canonical records and
  their deterministic replay may promote a raw subscription response into
  transport authority. The record field manifest, names, types, semantic
  inventory, and invariants are frozen with the V4.3 contract module and may
  not be weakened without a new protocol version.
- **Confirmed V4.3 local implementation fact:** the immutable five-record
  contract module, exact-key parsers, signature checks, projection-generated
  intent builder, public exports, fresh-genesis typed schema, append APIs,
  immutable uniqueness and idempotency rules, canonical-versus-typed replay,
  health/gate integration, termination fencing, and focused adversarial tests
  have landed. Collector/runtime integration, governance approval, actual
  socket ordering, provider conformance, and live soaks remain absent.
- **External established mechanisms:** RFC 6455 defines a WebSocket connection,
  secure opening handshake, ordered message transport, control frames, and
  closure; RFC 9266 defines a stronger TLS exporter channel-binding value for
  TLS 1.3 that this first record profile does not claim to retain; SQLite
  documents local transaction and durability behavior; official
  transactional-outbox guidance places durable intent before publication and
  still requires duplicate-safe processing; RFC 9162 specifies append-only
  Merkle commitments and consistency proofs.
- **Repository-specific design decisions:** one topic per session, one
  in-flight subscription operation, canonical locally generated request IDs,
  no ambiguous send retry, and two post-binding completed bars are conservative
  fail-closed choices. No external source proves that these exact choices
  optimize latency, availability, or trading performance.

V4.3 does **not** prove:

- that Bybit generated every expected market event or that its data is
  economically correct;
- application-layer provider signatures on public messages—Bybit public
  topics require no API authentication;
- that `conn_id` is globally unique, cryptographically authenticated, or
  durable across reconnects;
- exactly-once request delivery, exactly-once provider processing, or exactly
  one ACK;
- that a successful socket `send()` means the provider parsed or accepted the
  request;
- that a Ping/Pong proves the requested kline topic is active or usable;
- protection from a compromised collector process, operating system, trusted
  certificate authority, exchange, or storage device that lies about durable
  flushes;
- live scale, failover, outage-soak, or production readiness;
- model correctness, predictive edge, execution quality, or profitability;
- H2 execution authority, order construction, order submission, or fills.

## Threat model

### Protected authority

The protected decision is narrow:

```text
May this completed physical observation participate in the V4.3-integrated
HEALTHY transition as data from the currently approved and bound subscription?
```

V4.3 protects that decision from:

- a caller inventing an approved topic, request ID, connection generation, or
  subscription-manifest hash;
- a generic ACK from one topic laundering another topic;
- an ACK from an earlier socket, collector boot, connection generation,
  endpoint, environment, or policy;
- an ACK captured before the exact outbound intent was durably committed;
- a response with missing, empty, mismatched, reused, or conflicting `req_id`;
- a response with a missing or changing provider `conn_id`;
- data arriving before ACK being retroactively treated as bound;
- two concurrent subscription requests making a generic response ambiguous;
- a process crash after send being reported as confirmed success;
- replaying a session-bound command on a replacement connection;
- a disconnected or terminated session remaining apparently healthy;
- direct SQL rows or mutable outbox status being treated as canonical evidence;
- omission, reordering, mutation, or cross-session reassignment during full
  replay.

### Trusted computing boundary

The reviewed collector, local TLS/WebSocket library, canonical record builder,
single-writer projection, local filesystem, and SQLite VFS are inside the
trusted computing boundary. The collector must validate the configured WSS
hostname and certificate. RFC 6455 requires a secure WebSocket client to
perform TLS before the WebSocket handshake and to fail the connection when the
server certificate cannot be verified ([RFC 6455, Section
4.1](https://www.rfc-editor.org/rfc/rfc6455.html#section-4.1)).

RFC 9266 defines a 32-byte `tls-exporter` channel binding for TLS 1.3 ([RFC
9266, Section 2](https://www.rfc-editor.org/rfc/rfc9266.html#section-2)). The
first V4.3 record profile does **not** commit that exporter and therefore does
not claim RFC 9266 channel binding. It instead commits a fresh session nonce,
verified certificate and SPKI digests, trust-store identity, TLS/WebSocket
handshake transcript digests, the exact collector boot/generation, and a
signature by the policy-registered collector-attestation key. The mediated
collector must bind all callbacks to that exact live socket. This proves what
the trusted collector attested; it is not an exchange signature over Bybit
JSON and is weaker than a mutually verified application-layer channel binding.
Adding a TLS exporter later changes the canonical session contract and requires
a new identity/fresh-genesis review.

TLS termination by an unregistered proxy, disabled hostname verification,
certificate-verification failure, an insecure `ws://` endpoint, an
unregistered negotiated TLS/WebSocket mode, or a mismatch between the
attested endpoint and policy fails closed.

### Out-of-scope adversaries

A process with authority to forge both raw capture and every canonical record,
or an administrator able to rewrite the database and all locally stored roots,
can defeat a purely local proof. RFC 9162 roots make ordered history
tamper-evident relative to a retained earlier root; they do not independently
witness that root. Signed or externally witnessed checkpoints remain deferred.

## Official provider observations and limitations

The current official Bybit documentation establishes the following narrow
facts:

| Provider observation | Officially documented | V4.3 consequence |
|---|---|---|
| Public topics | Public topics do not require authentication | WSS hostname/certificate validation plus local session attestation and callback binding are required; JSON `conn_id` is not authentication |
| Subscribe request | `op="subscribe"`, `args=[...]`, optional customized `req_id`; multiple topics are supported | V4.3 nevertheless requires exactly one topic and a non-empty local request ID |
| Linear/Inverse success example | `success=true`, `ret_msg=""`, `op="subscribe"`, non-empty `conn_id`, and an optional/empty `req_id` field in examples | The reviewed profile accepts only the exact registered adapter/classifier schema and exact request-ID echo |
| Spot success example | Uses `ret_msg="subscribe"` | Spot cannot silently reuse the Linear response policy |
| Option/Spread response | Shows `successTopics` and `failTopics` | Those per-topic fields do not exist in the documented generic Linear response and cannot be assumed there |
| Disconnect | Bybit warns a client can be disconnected at any time and should reconnect promptly | Every replacement socket is a new fenced session requiring a new intent, ACK binding, and recovery suffix |
| Heartbeat | Bybit recommends an application Ping every 20 seconds; response shapes vary by product | Pongs are retained as liveness evidence only and cannot create subscription authority |
| Kline | Topic is `kline.{interval}.{symbol}`; push frequency is 1–60 seconds; `confirm=true` means closed | Only exact-topic, provider-final completed records are eligible; provider timestamps never replace local receipt time |
| Connection limits | At most 500 connection attempts per five minutes per WebSocket domain and 1,000 market-data connections per IP, separately by category | Reconnect uses bounded jitter/backoff and the narrow one-session profile must be capacity-tested before expansion |
| Argument limits | Public `args` text at most 21,000 characters; Spot at most ten args per request; Options at most 2,000 args per connection; no current futures/spread arg-count limit | Provider maxima are ceilings, not permission to multiplex this protocol version |

Sources: [Bybit V5 Connect](https://bybit-exchange.github.io/docs/v5/ws/connect),
[Bybit public kline](https://bybit-exchange.github.io/docs/v5/websocket/public/kline),
and [Bybit rate limits](https://bybit-exchange.github.io/docs/v5/rate-limit).

The public-stream documentation does **not** specify:

- request-ID uniqueness, maximum length, or duplicate-request behavior;
- a normative echo guarantee for every public product and failure mode;
- partial-success behavior for a multi-topic Linear/Inverse request;
- duplicate-topic subscription behavior;
- an ACK deadline or public subscription-command rate limit;
- session resumption, subscription persistence after reconnect, or a
  query-current-subscriptions operation;
- public `conn_id` uniqueness, lifetime, or cryptographic meaning;
- gap-free, duplicate-free, or sequence-numbered kline delivery.

Bybit documents a 36-character uniqueness convention and duplicate error
`20006` for camel-case order-entry `reqId`, not public-stream snake-case
`req_id`. V4.3 must not import that as a provider guarantee. See the distinct
[WebSocket order-entry guideline](https://bybit-exchange.github.io/docs/v5/websocket/trade/guideline).

The official Pybit connector generates UUID4 request IDs, holds subscriptions
in memory, and re-sends them after reconnect. That is useful evidence of one
client implementation, not a durable public-protocol guarantee and not an
audit-grade outbox ([official `_websocket_stream.py`](https://github.com/bybit-exchange/pybit/blob/master/pybit/_websocket_stream.py)).

## Alternatives evaluated and rejected

| Alternative | Useful property | Decision |
|---|---|---|
| Persist desired intent before connect only | Survives restart and tells a supervisor what should be subscribed | Rejected as sufficient authority: it proves desire, not exact session bytes, send chronology, provider response, or current-session binding |
| Mutate V3 capture or disposition records in place | Fewer new record classes | Rejected: it changes established identities, mixes transport intent with inbound capture, cannot repair already trusted caller metadata, and obscures the fresh authority boundary |
| SQL-only sidecar tables | Fast lookup and minimal canonical changes | Rejected as authority: rows outside canonical receipt order, roots, typed/canonical replay, and schema identity cannot satisfy V4 evidence cutoffs |
| Generic mutable outbox row with `PENDING/SENT/ACKED` updates | Familiar operational queue | Rejected as canonical authority: mutation erases transition history, `SENT` does not prove remote acceptance, and a generic row does not enforce policy/session/topic/request binding |
| Post-send journal | Records attempts during ordinary operation | Rejected: a crash after network send and before durable append leaves an unrecorded, potentially accepted command |
| Retry the same ambiguous command | Improves apparent availability | Rejected because public duplicate behavior is undocumented; terminate/fence the session and derive a fresh request on a new session |
| Accept multi-topic generic Linear ACK | Fewer sockets and requests | Rejected: the documented response does not identify which requested topic succeeded |
| Treat first data as implicit ACK | Avoids dependence on command response | Rejected: it loses exact request chronology and makes unsolicited or stale-session data capable of creating authority |
| Require ACK but allow pre-ACK bars to recover health | Reduces bootstrap latency | Rejected: a later ACK would retroactively authorize data observed before the binding existed |
| Distributed transaction with the exchange | Would remove local/remote uncertainty | Not available: Bybit is not a participant in the local SQLite transaction |

The transactional-outbox pattern is retained in a constrained form. Official
[AWS guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html)
places the outbox event in the same local transaction as the originating state,
then relays only committed rows, while warning that duplicate publication can
occur and ordering/idempotency remain application responsibilities. Official
[Microsoft guidance](https://learn.microsoft.com/en-us/azure/architecture/databases/guide/transactional-out-box-cosmos)
likewise persists before publication and accounts for reprocessing. Their
message-broker examples do not establish Bybit WebSocket idempotency. V4.3's
session fencing and no-ambiguous-retry rule are repository-specific adaptations.

## Fresh-genesis lineage and version boundary

V4.3 is a **fresh-genesis authority and projection lineage**. It is not an
`ALTER TABLE` migration of a V4.2 database and not a reinterpretation of old
raw subscription ACKs.

The following names are frozen semantically:

```text
authority lineage     = riskyieldmm_physical_authority_v4_3
transport schema      = riskyieldmm_physical_transport_v4_3
projection lineage    = riskyieldmm_physical_projection_v4_3
validation lineage    = riskyieldmm_physical_projection_validation_v4_3
canonical record set  = five transport/subscription records in this document
```

The focused-accepted local identities are:

```text
projection schema fingerprint = 353152587486575202fdd1681f3390a54947f728840d507cf41d54fb396269ab
reviewed health policy ID      = 341c453e010e17f51fdaf23d3a4c76ee14ef7fee299d856084475cfe356596a7
physical gate policy ID        = e629e3a55d8680f0db5c6af26841136ceab4e439f3de8eff3b3d13185c764a0f
```

The transport-subscription policy identity includes its reviewed collector
public key and is therefore deployment-specific, not a universal protocol
constant. The generated ledger ID is likewise genesis-instance-specific.
Changing a normative record field, key, state rule, root domain, or invariant
requires a new identity and another fresh-genesis decision.

A V4.2 database can remain a reference fixture. It cannot enter the V4.3
authority lineage by copying rows or treating an old ACK disposition as bound.
Only records admitted from the new genesis under the V4.3 schemas may satisfy
the new transport predicate.

## Five-record canonical profile

The contract-module field names and types are normative and exact. Omitting,
renaming, or weakening a semantic commitment requires a new protocol identity.
For every record, the projection also commits its canonical identity/content
to one unique ordered source receipt; that projection metadata is not a
payload field that could create a circular identity.

Each serialized record envelope also contains the frozen canonicalization and
transport schema versions plus its record-specific identity ID. Exact-key
parsing rejects missing and unknown fields.

| Record | Exact identity-envelope field |
|---|---|
| `TransportSubscriptionPolicyV4` | `transport_subscription_policy_id` |
| `TransportSessionAttestationV4` | `transport_session_id` |
| `OutboundSubscriptionIntentV4` | `outbound_subscription_intent_id` |
| `SubscriptionAckBindingV4` | `subscription_ack_binding_id` |
| `TransportSessionTerminationV4` | `transport_session_termination_id` |

### 1. `TransportSubscriptionPolicyV4`

The policy is the locally reviewed, self-hashed description of one transport
profile; external governance approval remains pending. Its exact payload
manifest is:

```text
policy_name: str
provider_id: str
venue_id: str
environment_id: str
authoritative_endpoint: str
tls_server_name: str
port: int
websocket_path: str
direct_connection_only: bool
minimum_tls_version: str
certificate_verification_required: bool
hostname_verification_required: bool
websocket_http_status_required: int
websocket_accept_validation_required: bool
allowed_websocket_extensions: tuple[str, ...]
allowed_subprotocols: tuple[str, ...]
single_topic_per_session: bool
maximum_inflight_subscriptions: int
require_nonempty_echoed_request_id: bool
maximum_request_id_length: int
send_deadline_seconds: int
ack_deadline_seconds: int
collector_attestation_key_id: canonical hash
collector_attestation_public_key_hex: lowercase Ed25519 key hex
frozen_at: UTC datetime
```

The reviewed profile freezes these non-governance values:

```text
provider_id = BYBIT
venue_id = BYBIT
environment_id = MAINNET
authoritative_endpoint = wss://stream.bybit.com/v5/public/linear
tls_server_name = stream.bybit.com
port = 443
websocket_path = /v5/public/linear
direct_connection_only = true
minimum_tls_version = TLSv1.3
certificate_verification_required = true
hostname_verification_required = true
websocket_http_status_required = 101
websocket_accept_validation_required = true
allowed_websocket_extensions = ()
allowed_subprotocols = ()
single_topic_per_session = true
maximum_inflight_subscriptions = 1
require_nonempty_echoed_request_id = true
maximum_request_id_length = 36
send_deadline_seconds = 5
ack_deadline_seconds = 10
```

The projection freezes the absolute deadline formulas:

```text
send_not_after = authorized_at + 5 seconds
ack_not_after  = authorized_at + 10 seconds
```

**V4.9C timing amendment (2026-07-17):** the send budget was increased from
one to five seconds after the causal actor demonstrated that the earlier budget
could expire inside the durable intent/pre-send journal path before any socket
call.  Bybit's official public-stream subscription contract specifies request
shape and responses but no one-second subscription-send rule; it separately
recommends a 20-second heartbeat interval.  Five seconds remains an absolute,
fail-closed bound below the ten-second ACK deadline, not permission to send a
stale command.  Promotion still requires latency distributions from the target
filesystem/host and must reject a deployment whose high-quantile durable
pre-send latency cannot preserve adequate margin.  See the official
[Bybit V5 WebSocket connection and subscription contract](https://bybit-exchange.github.io/docs/v5/ws/connect).
Because this field participates in policy identity, any pre-checkpoint signed
manifest that still commits the one-second profile is rejected and must be
regenerated; there is no silent reinterpretation or in-place migration.

The ACK deadline is authorization-relative, not dispatch-relative. The intent
is durably recorded before dispatch; a later binding must prove that dispatch
started by the send deadline and that the captured ACK arrived by the absolute
ACK deadline.

Its identity commits:

- schema/canonicalization version and a stable policy name;
- provider, venue, environment, authoritative endpoint, TCP port, TLS server
  name, and WebSocket resource path;
- direct-connection requirement, minimum TLS version, certificate and hostname
  verification requirements;
- required WebSocket HTTP status and `Sec-WebSocket-Accept` validation;
- exact allowed WebSocket extension and subprotocol sets;
- single-topic and maximum-in-flight subscription limits;
- non-empty echoed-request-ID requirement and maximum request-ID length;
- send and ACK deadline durations;
- the exact collector-attestation Ed25519 key identity and public key;
- freeze time.

Only a registered policy can authorize a session. Endpoint aliases, testnet,
Spot, inverse, options, a different path, a relaxed verification flag, another
extension/subprotocol set, another deadline, or a different collector key
requires a different policy identity. The physical scope, adapter, capture
partition, and exact topic are committed by the child session and intent; they
are deliberately not mutable fields in this transport-level policy.

### 2. `TransportSessionAttestationV4`

The attestation is an immutable statement that the reviewed collector opened
one concrete secure WebSocket session under one registered policy. Its
exact payload manifest is:

```text
transport_subscription_policy_id: canonical hash
physical_scope_manifest_id: canonical hash
adapter_policy_id: canonical hash
capture_partition_id: canonical hash
collector_instance_id: str
collector_boot_id: str
connection_generation: int
session_nonce: canonical 32-byte hash encoding
parent_transport_session_id: canonical hash | None
authoritative_endpoint: str
tls_server_name: str
remote_address: str
tls_version: str
tls_cipher: str
alpn_protocol: str | None
websocket_extensions: tuple[str, ...]
peer_certificate_sha256: canonical hash
peer_spki_sha256: canonical hash
trust_store_manifest_id: canonical hash
certificate_verified: bool
hostname_verified: bool
websocket_http_status: int
websocket_accept_verified: bool
handshake_request_sha256: canonical hash
handshake_response_sha256: canonical hash
handshake_started_at: UTC datetime
handshake_completed_at: UTC datetime
handshake_started_monotonic_ns: int
handshake_completed_monotonic_ns: int
clock_uncertainty_milliseconds: int
collector_release_hash: canonical hash
collector_runtime_id: canonical hash
collector_attestation_key_id: canonical hash
collector_attestation_public_key_hex: lowercase Ed25519 key hex
signature_hex: lowercase Ed25519 signature hex
```

The attested session must repeat the frozen endpoint/server name, negotiate
exactly `TLSv1.3`, report successful certificate/hostname/HTTP-101/accept
verification, and have `websocket_extensions=()` and `alpn_protocol=None`.
The cipher, peer/trust commitments, remote address, transcript commitments,
times, and collector identities remain session-specific evidence.

Its identity commits every field except `signature_hex`; the signature covers
the unsigned canonical identity payload. Required semantics are:

- policy, adapter policy, physical scope, capture partition, and collector
  instance/boot identity;
- a fresh 32-byte session nonce, exact optional parent-session identity, and
  strictly increasing connection generation;
- exact authoritative endpoint, TLS server name, remote address, negotiated
  TLS version/cipher, and ALPN protocol;
- verified peer-certificate and SPKI SHA-256 digests plus the exact trust-store
  manifest identity;
- certificate- and hostname-verification results;
- negotiated WebSocket extensions, required HTTP status and verified
  `Sec-WebSocket-Accept` result;
- WebSocket opening-handshake request/response SHA-256 commitments;
- handshake start/completion wall times and monotonic readings plus clock
  uncertainty;
- collector release and runtime identities;
- policy-registered collector-attestation key identity/public key and an
  Ed25519 signature over the canonical attestation.

The attestation is created only after TLS certificate validation and a valid
WebSocket opening handshake. It cannot be copied to another socket. The local
collector's socket-to-session association is mediated and one-to-one for the
session lifetime.

### 3. `OutboundSubscriptionIntentV4`

The intent is both the immutable command commitment and the narrow outbox
entry. Its exact payload manifest is:

```text
transport_subscription_policy_id: canonical hash
transport_session_id: canonical hash
physical_scope_manifest_id: canonical hash
adapter_policy_id: canonical hash
capture_partition_id: canonical hash
connection_generation: int
intent_nonce: canonical 32-byte hash encoding
request_id: str
operation: str
topics: tuple[str, ...]
subscription_manifest_hash: canonical hash
websocket_opcode: str
command_base64: canonical base64
command_sha256: canonical hash
authorized_at: UTC datetime
send_not_after: UTC datetime
ack_not_after: UTC datetime
```

Its identity commits:

- policy, session attestation, adapter policy, physical scope, capture
  partition, and connection generation;
- a fresh 32-byte intent nonce, one `subscribe` operation, exactly one
  canonical topic, and one non-empty canonical local request ID;
- exact `TEXT` WebSocket opcode, base64-encoded emitted command bytes, and
  command SHA-256;
- exact subscription-manifest commitment derived from the ordered one-topic
  list;
- authorization wall time and strictly ordered
  `authorized_at < send_not_after < ack_not_after` deadlines.

The command bytes are exactly canonical JSON for `args`, `op`, and `req_id`;
caller-supplied alternative serialization is rejected. The canonical intent
must commit successfully before any byte of that command is offered to the
WebSocket library. A send-return flag is not authority and does not belong in
the immutable identity. The intent may be sent at most once on its exact
attested session. It may never be replayed on a replacement session.

### Local `req_id` convention

The reviewed V4.3 convention is:

```text
non-empty ASCII string matching [A-Za-z0-9_-]+
no more than 36 characters under the frozen policy
unique across all V4.3 outbound subscription intents in one ledger lineage
generated internally before intent construction and durable commit
never reused after timeout, disconnect, termination, or reconnect
```

This is a **local RiskYieldMM invariant**, chosen for unambiguous correlation
and compatible with, but not restricted to, the official client's UUID4
practice. The authoritative projection/collector path owns allocation;
external caller input is not authority for request-ID allocation. This is not
a Bybit public-stream uniqueness or length guarantee.

### 4. `SubscriptionAckBindingV4`

The binding is the only canonical promotion of a raw ACK disposition into
subscription authority. Its exact payload manifest is:

```text
transport_subscription_policy_id: canonical hash
transport_session_id: canonical hash
outbound_subscription_intent_id: canonical hash
physical_scope_manifest_id: canonical hash
adapter_policy_id: canonical hash
capture_partition_id: canonical hash
connection_generation: int
capture_segment_id: canonical hash
physical_message_id: canonical hash
message_receipt_id: canonical hash
scope_message_sequence: int
provider_message_disposition_id: canonical hash
message_disposition_id: canonical hash
raw_ack_sha256: canonical hash
echoed_request_id: str
provider_connection_id: str
request_command_sha256: canonical hash
dispatch_started_at: UTC datetime
dispatch_completed_at: UTC datetime
dispatch_started_monotonic_ns: int
dispatch_completed_monotonic_ns: int
ack_received_at: UTC datetime
ack_received_monotonic_ns: int
bound_at: UTC datetime
collector_attestation_key_id: canonical hash
collector_attestation_public_key_hex: lowercase Ed25519 key hex
dispatch_attestation_signature_hex: lowercase Ed25519 signature hex
```

Its identity commits every field except
`dispatch_attestation_signature_hex`; that signature covers the unsigned
canonical identity payload. Required semantics are:

- policy, session attestation, outbound intent, adapter policy, physical scope,
  capture partition, and connection generation;
- exact capture segment, physical message, message receipt, scope-message
  sequence, provider-disposition provenance, and message disposition;
- raw ACK SHA-256, exact echoed request ID, non-empty provider `conn_id`, and
  the request-command SHA-256 copied from the bound intent;
- dispatch start/completion wall and monotonic times, ACK receive wall and
  monotonic times, and binding time;
- the policy-registered collector-attestation key identity/public key and an
  Ed25519 dispatch-attestation signature binding the command to the send
  chronology.

Admission re-runs the registered adapter/classifier over the raw capture,
parses the exact product response, and requires:

```text
same local socket/session
same policy, scope, boot, connection generation, and capture partition
intent durable receipt < raw ACK receipt < binding receipt
authorized_at <= dispatch start <= dispatch completion < ACK receive <= binding
dispatch start <= send_not_after and ACK receive <= ack_not_after
op == "subscribe"
success is true
ret_msg exactly matches the registered adapter/classifier product profile
req_id exactly equals the intent req_id
provider conn_id is non-empty and consistent for the session
intent contains exactly one approved topic
session is not terminated
no earlier binding or conflicting ACK exists
```

The response need not repeat the topic because the one-topic intent and exact
request-ID match make the relation unambiguous. If the provider does not echo
the request ID in the live reviewed profile, V4.3 fails closed; it does not
fall back to arrival order or the last request sent.

### 5. `TransportSessionTerminationV4`

The termination permanently fences one session. Its exact payload manifest
is:

```text
transport_subscription_policy_id: canonical hash
transport_session_id: canonical hash
physical_scope_manifest_id: canonical hash
capture_partition_id: canonical hash
connection_generation: int
reason: LOCAL_CLOSE | REMOTE_CLOSE | TRANSPORT_ERROR | ACK_TIMEOUT |
        PROCESS_RESTART | SUPERSEDED
close_code: int | None
close_reason_digest: canonical hash | None
detected_at: UTC datetime
detected_monotonic_ns: int
recorded_at: UTC datetime
collector_attestation_key_id: canonical hash
collector_attestation_public_key_hex: lowercase Ed25519 key hex
signature_hex: lowercase Ed25519 signature hex
```

`signature_hex` is excluded from identity and signs the unsigned canonical
identity payload. Required semantics are:

- policy, session, physical scope, capture partition, and connection
  generation;
- exact canonical reason plus optional locally observed Close code and a digest
  of the Close reason;
- detection wall/monotonic times and later-or-equal recording time;
- the policy-registered collector-attestation key identity/public key and an
  Ed25519 signature over the canonical termination.

RFC 6455 distinguishes clean closure after the closing handshake from an
underlying transport loss and reserves abnormal closure semantics when no
Close frame was received ([RFC 6455, Sections 7.1.4–7.1.5](https://www.rfc-editor.org/rfc/rfc6455.html#section-7.1.4)).
V4.3 preserves that diagnostic distinction, but both outcomes remove current
authority.

A Close-reason digest is legal only with a Close code. A termination is final.
No later intent, binding, capture authority, or health recovery may attach to
the session. If a crash prevents appending termination at the time of loss,
restart reconciliation appends a signed `PROCESS_RESTART` or `SUPERSEDED`
termination, as applicable, when the store is writable; the collector
boot/generation fence already prevents old evidence from authorizing the new
session.

## Derived session state and uniqueness rules

No mutable session head is authoritative. Replay of the five records derives:

```text
ATTESTED
  -> INTENT_COMMITTED
  -> ACK_BOUND
  -> RECOVERING
  -> TRANSPORT_ELIGIBLE

Any nonterminal state -> TERMINATED
```

`ACK_BOUND` may move to `RECOVERING` only through exact-topic evidence after
the binding. `TRANSPORT_ELIGIBLE` is a transport predicate consumed by the
V4.3 physical-health integration, which retains the predecessor V4.2 reducer
semantics. It is not itself `HEALTHY` and never bypasses status, freshness,
continuity, blocker, vintage, or clock rules.

The following uniqueness constraints are normative:

- one registered policy per policy identity;
- one session attestation per session identity, a globally unique session
  nonce, and one `(physical scope, capture partition, generation)` tuple;
- a parent session cannot be its own child and can have at most one direct
  successor in the frozen non-branching reconnect lineage;
- exactly one authority topic in every reviewed intent and at most one
  unresolved/in-flight subscription operation per reviewed session;
- a globally unique intent nonce and request ID;
- at most one non-conflicting ACK binding for each intent, bound within that
  intent's same session, and no reuse of its physical message,
  provider-disposition provenance, or message disposition in another binding;
- at most one terminal record per session;
- one provider `conn_id` value once bound within a session;
- no record may change scope, policy, adapter, boot, generation,
  endpoint, or topic along an identity edge;
- every session/binding/termination signature key must equal the key frozen by
  its registered transport policy;
- all canonical receipts and local authority clocks are non-decreasing;
- every typed relation is reconstructed from canonical records during full
  replay and compared exactly.

A duplicate raw ACK can remain an exhaustively classified capture occurrence.
It cannot produce a second binding. A byte-identical idempotent append request
returns the already stored binding; a different ACK for the same intent or a
reused request ID is an integrity conflict and terminates/fences the session.

## Data-before-ACK and recovery semantics

Provider data can be observed before the subscription command response. V4.3
does not drop or rewrite it:

1. raw bytes are durably captured and exhaustively classified;
2. the observations remain pre-binding evidence and cannot satisfy transport
   eligibility, recovery counts, decision inputs, or gates;
3. a later valid ACK binding does not retroactively authorize them;
4. only completed provider-final bars whose raw/admission receipts are
   strictly later than the binding receipt may enter the recovery suffix;
5. exactly two clean, contiguous one-minute bars on the same session,
   connection generation, capture partition, policy, and exact topic are
   required before the transport predicate can be eligible.

The two bars must both have `confirm=true`, exact expected symbol/interval/topic,
non-regressing provider chronology, no gap or conflicting revision, and all
retained causal-cutoff and vintage conditions. A provisional
`confirm=false` update may be captured but never counts. One post-binding bar
leaves the session in recovery.

The two-bar suffix is a conservative RiskYieldMM rule, not a Bybit guarantee.
It prevents an ACK or a single coincidentally clean event from instantly
restoring authority and preserves the predecessor two-bar recovery semantics.

## One-topic and one-in-flight rule

Every reviewed V4.3 subscription intent carries exactly one authority topic,
and a session may have at most one unresolved/in-flight subscription
operation. The outbound `args` array therefore has length one. The first narrow
collector issues one subscribe operation for the session. It never retries an
ambiguous command, and it fences the session before any replacement subscribe;
unsubscribe and multiplexed command lifecycles remain outside this profile.

This rule is stricter than Bybit's documented capacity. It is required because
the Linear generic ACK does not enumerate successful topics, duplicate behavior
is undocumented, and a post-crash retry cannot be distinguished safely from an
already processed request. It also makes request-to-topic, ACK-to-request, and
capture-to-session completeness independently replayable.

Supporting many topics on one socket is a future fresh policy/profile with
per-command ordering, partial-success semantics, capacity limits, and soak
evidence. The current one-topic rule must not be silently relaxed to solve
scale pressure.

## Session fencing, reconnect, and crash ambiguity

Every WebSocket opening handshake produces a new local session identity. A
new collector boot or connection generation cannot inherit an earlier
attestation, request ID, intent, ACK binding, provider `conn_id`, recovery bar,
or healthy transition. Bybit's instruction to reconnect promptly is an
availability instruction, not a session-resumption guarantee.

RFC 6455 defines WebSocket messages only after a successful opening handshake
and treats closure of the underlying connection as closure of that WebSocket
connection. A reconnect is therefore represented as a new session, even when
it uses the same endpoint and topic. Abnormal closures use randomized initial
delay and increasing backoff as recommended by [RFC 6455, Section
7.2.3](https://www.rfc-editor.org/rfc/rfc6455.html#section-7.2.3), while also
staying below Bybit's connection limits.

The authoritative crash rules are:

- no durable session attestation: do not send;
- attestation without an intent: no subscription authority exists;
- durable intent whose send has not begun: it may be sent once only while its
  exact attested socket is still continuously owned by the same collector;
- any exception or crash during/after send and before a durable valid binding:
  outcome is `UNKNOWN`, not success or failure;
- an unknown intent is never retried on that session and never replayed on a
  new session; fence/terminate and create a new session plus a new request ID;
- raw ACK durably captured before a process crash may be bound later for
  historical audit by deterministic replay, but the dead session cannot become
  current transport authority;
- a crash after binding or after health still forces fresh session binding and
  two fresh post-binding bars before new current authority;
- inability to append or verify the canonical journal denies all gates. The
  service records the incident after storage recovers; it does not synthesize
  a healthy record while the journal is unavailable.

This trades availability for unambiguous local evidence. A later protocol may
introduce a provider-supported idempotency/query mechanism if one becomes
officially documented and empirically verified.

## Failure matrix

| Failure point or observation | Durable fact after recovery | Required disposition | May authorize current health? |
|---|---|---|---|
| Before session-attestation commit | No session | Do not send; create a fresh attested session | No |
| After attestation, before intent commit | Session only | No send; terminate or create the one intent | No |
| After intent commit, before send in the same live process | Exact pending command exists | One send is permitted only on that continuously owned socket | No |
| Crash after intent commit, send status unknowable | Intent exists; remote outcome unknown | Append `PROCESS_RESTART` after recovery; new session and request ID | No |
| Socket send returns successfully | Local call returned | Diagnostic only; await exact raw ACK | No |
| Definite or ambiguous send exception | Exact extent of remote receipt is not provable | Append `TRANSPORT_ERROR`; fence session; no same-command retry | No |
| Data arrives before ACK | Raw data exists without binding | Capture/classify; exclude from recovery and authority | No |
| ACK missing at deadline | Intent has no valid binding | Append `ACK_TIMEOUT`; back off; fresh session | No |
| ACK has missing/empty/mismatched `req_id` | Raw response conflicts with local convention | Reject binding; integrity failure; terminate | No |
| ACK has wrong `op`, `success`, `ret_msg`, or schema | Provider response does not satisfy policy | Reject or provider/schema blocker; terminate as policy requires | No |
| ACK `conn_id` missing or changes | Remote label is absent/inconsistent | Reject binding or later control evidence; terminate | No |
| ACK from old boot/generation/socket | Cross-session response | Reject as out-of-scope/integrity conflict | No |
| Valid ACK after pre-ACK bars | Binding exists | Start recovery count at zero after binding | No |
| One clean completed post-binding bar | Binding plus one recovery bar | `RECOVERING` | No |
| Two clean contiguous completed post-binding bars | Transport predicate can be eligible | Run full V4.3-integrated health reducer; no automatic health claim | Only if every retained health predicate passes |
| Gap, malformed payload, conflict, stale status, or excessive clock uncertainty | Retained health blocker | Apply the frozen blocker/recovery policy | No |
| Ping/Pong healthy but no current kline data | Transport heartbeat only | Price feed becomes stale under the health policy | No |
| Graceful or abnormal close | Termination/fence | Append `LOCAL_CLOSE`, `REMOTE_CLOSE`, or `TRANSPORT_ERROR`; authority ends immediately | No |
| Disk full, I/O error, failed commit, or failed replay | Canonical durability unavailable | Operational journal failure; deny gates | No |
| Duplicate byte-identical append request | Existing canonical record | Return exact stored result idempotently | No new authority |
| Conflicting duplicate intent/binding/termination | Competing history | Roll back, quarantine, deny | No |

## V4.3 health and gate integration

V4.3 replaces the old transport predicate; it does not replace the physical
health reducer.

For an authoritative primary scope, V4.3 replaces the predecessor subscription
condition with:

```text
registered V4.3 transport policy
+ current unterminated attested session
+ exact durable one-topic outbound intent
+ exact valid ACK binding on that session
+ two clean completed bars admitted strictly after the binding
```

A raw `CONTROL_SUBSCRIPTION_ACK` disposition remains evidence used to build the
binding. By itself it has no transport authority. The capture
`subscription_manifest_hash` must equal the ordered one-topic manifest
committed by the exact intent, while policy/scope/session consistency is
verified through separate identity edges; a caller-provided matching digest
is not sufficient.

The typed SQL path and independent canonical replay must reconstruct the exact
policy/session/intent/binding/termination tuple visible at each health cutoff
and require equality. Full-store verification replays every raw ACK under its
registered classifier, recomputes every binding, checks all uniqueness and
chronology rules, verifies termination fences, and re-derives each health
transition and gate.

Both health checks retain their V4.2 semantics:

- decision-cutoff health proves the selected physical input was already bound
  and healthy when assembled;
- current health proves the same scope remains bound, un-terminated, fresh,
  and blocker-free at the transaction-owned gate clock.

`DECISION_INPUT` remains the only locally pass-capable stage. V4.3 does not
implement the atomic H1/H2/order-intent bridge and does not change
`V4_EXECUTION_BAR_PASS_ENABLED = False`. H2/`EXECUTION_BAR` remains
`ABSTAIN`-only with the bridge-not-implemented reason.

## SQLite transaction and durability profile

The first implementation retains the existing conservative local profile:

```text
single serialized authoritative writer
BEGIN IMMEDIATE for canonical append/evaluation
PRAGMA journal_mode = DELETE
PRAGMA synchronous = EXTRA
local filesystem only
intent COMMIT completes before WebSocket send
```

SQLite permits only one simultaneous writer and `BEGIN IMMEDIATE` acquires the
write transaction at the beginning, avoiding a later read-to-write upgrade
race ([SQLite transactions](https://www.sqlite.org/lang_transaction.html),
[SQLite isolation](https://www.sqlite.org/isolation.html)). In rollback-journal
mode, `synchronous=EXTRA` additionally syncs the directory after the journal is
unlinked and is SQLite's strongest documented rollback-mode durability choice
for a commit immediately followed by power loss ([SQLite synchronous
pragma](https://www.sqlite.org/pragma.html#pragma_synchronous)).

The current Python runtime reports SQLite **3.51.1**. SQLite documents a rare
WAL-reset corruption race in versions 3.7.0 through 3.51.2 when multiple
connections in separate threads/processes write or checkpoint concurrently;
the fix is in 3.51.3 and selected backports ([SQLite WAL-reset
bug](https://sqlite.org/wal.html#the_wal_reset_bug)). The frozen
`DELETE + EXTRA` profile is outside the documented WAL-only condition. V4.3
must not switch to concurrent WAL for collector/UI convenience without a
fixed runtime, a new reviewed storage profile, and adversarial concurrency and
crash evidence.

The database must remain on a local filesystem. SQLite warns that network
filesystem locking and synchronization can violate its assumptions and lead
to corruption ([SQLite over a
network](https://sqlite.org/useovernet.html)).

At startup and before authority, the implementation verifies the active
journal/synchronous profile, foreign-key behavior, schema fingerprint,
canonical roots, typed/canonical replay equality, and orphan-session fences.
A mutable operational queue or dashboard may be rebuilt from canonical
records, but it may not be an authority input.

## Canonical audit commitments

All five record kinds participate in the same ordered V4.3 receipt history and
scope/record commitments. Link roots commit ordinal plus record identity, not
an unordered set. Typed indexes retain full relations so replay can prove
completeness rather than accepting a root supplied by a caller.

RFC 9162 defines inclusion and consistency proofs for an append-only Merkle
tree ([RFC 9162, Section
2.1](https://www.rfc-editor.org/rfc/rfc9162.html#section-2.1)). V4.3 uses that
construction as an ordered commitment primitive; it does not claim to operate
a Certificate Transparency log. Roots are meaningful only together with
canonical leaves, tree size, prior roots, inclusion/consistency verification,
and independent replay.

## Acceptance tests

Acceptance is split by evidence level. The local contract/projection slice is
focused-accepted: deterministic contract, projection, health, gate,
adversarial-correlation, and injected transaction-rollback tests pass. This is
not acceptance of the production collector or the complete campaign below.
Golden deployment identities, broader property/tamper campaigns, real-socket
ordering, process/storage crash testing, and provider soaks remain pending.
The verified checkpoint is **119 focused V4.3 tests passed**, **201 physical
tests passed**, and **1,426 repository tests passed with 32 skipped**.

### Contract and canonicalization — focused core accepted

- exact construction, round-trip, identity, canonical bytes, maximum size,
  and unknown-key rejection for all five records;
- golden IDs for the registered reviewed policy and representative record
  chain;
- frozen request-ID alphabet/length validation and ledger-wide uniqueness;
- exactly one topic per intent, no more than one in-flight operation, unique
  binding/termination relations, and no cross-edge scope mutation;
- TLS/session-evidence and WebSocket-transcript commitment validation,
  including rejection of any false RFC 9266 exporter-binding claim;
- exact product-specific ACK schema and provider `conn_id` constraints;
- property tests proving deterministic identities and rejection of reordered,
  omitted, duplicated, or conflicting links.

### Projection and full replay — focused core accepted

- fresh-genesis schema creation and old-schema rejection;
- append each record only through registered parent/policy chronology;
- exact typed SQL versus canonical replay reconstruction at every cutoff;
- raw ACK classifier replay and exact binding re-derivation;
- request/session/topic/boot/generation/capture-partition bijections;
- termination fencing and startup orphan-session reconciliation;
- full replay from genesis reproducing all typed rows, roots, health
  transitions, and gates;
- database tamper, deleted row, changed ordinal, wrong root, wrong canonical
  bytes, and cross-scope laundering rejection.

### Transport state machine — local subset accepted; runtime subset pending

- no network send before a committed attestation and committed intent;
- exactly one send attempt on the exact continuously owned session;
- no fallback correlation when `req_id` is absent;
- data-before-ACK capture without retroactive authority;
- valid binding followed by zero, one, and two post-binding completed bars;
- provisional, wrong-topic, gapped, duplicated, conflicting, stale, and
  post-termination observations;
- reconnect always creates a new session, intent, request ID, ACK binding, and
  two-bar recovery suffix;
- Ping/Pong cannot substitute for a topic ACK or completed bar;
- capacity-aware randomized backoff and a bounded collector queue that fails
  closed rather than dropping authoritative events silently.

### Crash and storage campaign — pending beyond injected transaction rollback

Inject process termination and errors:

- before/after session-attestation commit;
- before/after intent commit;
- immediately before, during, and immediately after socket send;
- after raw ACK receipt but before capture commit;
- after capture commit but before binding append;
- after binding append and after each recovery bar;
- during termination and restart reconciliation;
- on `SQLITE_FULL`, `SQLITE_IOERR`, `SQLITE_BUSY`, failed fsync/commit,
  corrupted canonical bytes, and clock regression.

Each restart must yield either the exact committed prefix or a fail-closed
verification error. No crash point may create a binding, transport eligibility,
`HEALTHY`, or `PASS` without all required earlier records.

### Provider conformance and soak — pending

Before any activation claim, testnet and then controlled mainnet capture must
measure and retain raw evidence for:

- request-ID echo on success and failure;
- exact Linear ACK fields and return-message values;
- provider `conn_id` stability within and change across sessions;
- data-before-ACK occurrence;
- duplicate/late/unsolicited ACK behavior without depending on it;
- kline finality, timing, duplicates, gaps, and reconnect recovery;
- heartbeat and abnormal-close behavior;
- connection-rate/backoff behavior;
- 24-hour, 7-day, and longer outage/restart soaks under the frozen runtime.

An undocumented behavior observed in a soak is evidence for compatibility,
not a provider guarantee. If it is needed for authority, it must be frozen as
a conservative policy predicate and monitored for drift.

## Implemented-versus-deferred boundary

### Focused local acceptance

- five-record immutable contract module, exact field manifests, transport-key
  signatures, projection-generated intent builder, and public exports;
- five-record canonical profile and identity graph;
- fresh-genesis `STRICT` typed schema, append-only receipts, immutable indexes,
  transactional idempotency batches, and canonical-versus-typed full replay;
- registered-policy/session/intent chronology inside the local record graph;
- canonical local request-ID convention;
- one topic and one in-flight subscription operation;
- exact same-session ACK correlation with opaque provider `conn_id` kept
  separate from the local session identity;
- data-before-ACK exclusion and two post-binding completed bars;
- signed termination fencing and reconnect-lineage rules;
- V4.3 health/gate integration with raw ACKs unable to authorize health,
  projection-clock-owned H1, and ABSTAIN-only H2;
- rollback-journal SQLite profile and focused injected rollback/adversarial
  acceptance.

These facts prove deterministic local consistency over the admitted signed
records and fixtures. They do not prove that those facts came from an actual
continuously owned network socket.

### Required for operational transport authority

- reviewed, fenced transport collector/driver that mediates every callback and
  demonstrably cannot send before the durable intent commit;
- TLS/WebSocket session attestation on the actual runtime;
- actual send-attempt, ACK, disconnect, termination, restart, and orphan
  reconciliation wiring;
- governance approval of the collector key, release, runtime, trust store, and
  deployment policy;
- authenticated status-source provenance and live provider-conformance
  capture;
- systematic process/storage crash campaign, bounded-queue/capacity tests, and
  24-hour, 7-day, and longer soaks.

### Deferred trading activation

- multiplexed many-topic sessions and all-asset/all-timeframe scale profile;
- automated live supervisor deployment and production credentials/process
  management;
- externally witnessed or signed ledger checkpoints;
- multi-node failover/consensus;
- automatic governance/Analyst activation and removal of legacy bypass paths;
- atomic H1/H2 plus exact trading order-intent/outbox bridge;
- order submission, execution reconciliation, fills, portfolio controls, and
  broker/exchange recovery;
- profitability or out-of-sample edge claims.

## Final protocol recommendation

Use the focused-accepted V4.3 local projection as the append-only transport
authority layer in front of the V4.3 physical-health integration with retained
V4.2 reducer semantics. Keep the policy and session attestation separate from
the exact outbound intent; make the intent durable before send; correlate one
exact ACK by local request ID and socket session; exclude all pre-binding data;
require two later completed bars; and fence the entire session on any ambiguous
send, reconnect, or termination.

This design contributes a missing causal link:

```text
approved transport
-> attested session
-> durable exact request
-> same-session provider response
-> post-binding completed market data
-> deterministic health
-> non-executing local decision gate
```

It is the focused-accepted local projection under the documented public Bybit
protocol. It is not production transport authority, live activation, or
evidence of profitable trading.
