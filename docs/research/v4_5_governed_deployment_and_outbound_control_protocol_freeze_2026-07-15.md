# V4.5 governed deployment and outbound-control protocol freeze

**Date:** 2026-07-15

**Status:** the V4.5 deployment authority/admission, five immutable
outbound-control records, and canonical SQLite append/replay projection are
implemented. Runtime control mediation, real artifact/clock materializers, and
TCP/TLS/`websockets` Sans-I/O remain unimplemented. This is therefore a
**protocol checkpoint, not deployment approval**.

**Corrects and extends:**
[`v4_4_operational_transport_runtime_protocol_freeze_2026-07-15.md`](v4_4_operational_transport_runtime_protocol_freeze_2026-07-15.md)

## Executive decision

V4.5 keeps the V4.4 fail-closed physical transport model, then makes two
previously deferred boundaries explicit:

1. a runtime may obtain public-market-data capture authority only from an
   out-of-band-pinned deployment root, a threshold-approved DSSE deployment
   bundle, and its exact six-manifest closure; and
2. Bybit application heartbeats and automatically required RFC 6455 Pong/Close
   traffic must pass through a durable, one-shot outbound-control evidence
   chain before any socket write.

These changes remove two important ambiguities. A self-signed root delivered
beside a bundle cannot bootstrap itself, and a WebSocket library cannot emit
unrecorded control bytes merely because it generated them automatically.

The freeze does **not** establish that the hashes declared by a manifest match
real build, dependency, CA, clock, or runtime bytes. The projection persists
and independently replays the five-record control chain, but the runtime does
not yet produce or consume it. It is therefore not a non-bypassable live send
boundary, and connecting a provider socket remains blocked.

The smallest accepted authority path is:

```text
operator-pinned deployment trust-root ID
-> exact DeploymentTrustRootV4
-> threshold-valid DSSE approval over exact deployment-bundle bytes
-> exact six-child content-addressed closure
-> narrow VerifiedDeploymentCapabilityV4
-> current linear deployment approval in the canonical projection
-> OS writer lease + projection writer fence
-> verified runtime startup and orphan reconciliation
-> exact deployment-bound transport policy and session
-> durable outbound-control chain
-> exact one-shot pre-TLS write attempt
-> raw-first inbound evidence and existing V4.4 subscription authority
```

The authority ceiling remains
`PUBLIC_MARKET_DATA_CAPTURE_ONLY`. No V4.5 deployment or control object can
authorize private endpoints, credentials, order entry, `EXECUTION_BAR`, model
promotion, paper/live orders, or capital allocation.

## Evidence vocabulary

This document uses four labels deliberately:

- **External protocol fact**: a property stated by a primary specification or
  official provider/library documentation.
- **Implemented repository fact**: behavior enforced by current source and
  focused tests.
- **Frozen repository design**: behavior required of the next implementation
  even though the complete adapter or persistence layer does not exist.
- **Unestablished claim**: a property for which the repository currently has
  declarations or synthetic fixtures, but not operational evidence.

Content-addressing a declaration proves only that the declaration did not
change. It does not prove that the declared external bytes existed, were built
from the named source, were loaded by the running process, or remained
unmodified.

## Current repository checkpoint

| Area | Implemented repository fact | Present limit |
|---|---|---|
| Operational manifests | Strict V4.5 schemas for collector release, dependency lock, TLS trust store, clock policy, runtime environment, and collector-key authorization | No production materializer or verifier reads and hashes actual deployment artifacts |
| Deployment approval | Exact DSSE payload type and PAE, Ed25519 role keys, signature threshold, mandatory independently supplied expected root ID, validity interval, exact six-child closure, and cross-manifest binding | No production root ceremony, secure key custody, revocation process, or external root distribution |
| Deployment projection | One installed trust root; linear bundle sequence and exact parent; immutable approval storage; current-head assertion; all prior sessions terminal before successor | Root rotation and collector-key rotation intentionally unsupported; local root storage is not the external trust anchor |
| Runtime admission | Startup re-verifies the DSSE approval at governed time, matches the loaded collector signer, checks the projection head, binds the deployment capability, and refuses a mismatched session | The supplied clock, child manifests, and signer are still ports or caller-provided objects; actual host state is not attested |
| Transport authority | V4.5 policy and session records carry exact `deployment_bundle_id`, collector-key authorization, release/runtime, trust-store, and clock-policy identities | No real TLS/WebSocket session has produced these facts |
| Outbound control | Five immutable records—`RawIngressCommitV4`, trigger, intent, prepared wire, and dispatch result—have canonical tables, atomic append rules, typed loading, and full replay | Runtime mediation, real TLS/Sans-I/O production, and OS/socket evidence remain absent |
| Dependency declaration | Optional `transport` extra pins `websockets==16.0` | Core dependencies use broad lower bounds; `requirements-ci.txt` installs only `.[ci]`; no fully hashed transitive lock or wheelhouse exists |
| Verification | 107 dedicated V4.5 tests, 232 authority/transport tests, 344 physical tests, and 1,636 repository tests with 32 skipped passed | Local tests are not artifact, provider, crash-campaign, soak, or deployment evidence |

Two V4.4 identifiers are intentionally stable compatibility surfaces:
`RiskYieldMMTransportCollectorAttestationPublicKeyV4_4` preserves existing
collector-key IDs, and writer-lease JSON remains diagnostic schema `V4.4`.
Neither is stale deployment authority; authoritative physical transport and
control records use the fresh-genesis V4.5 schema.

## Frozen authority graph

### Trust and deployment authority

```text
OUT-OF-BAND OPERATOR DECISION
  expected_trust_root_id
            |
            | exact equality; never inferred from the bundle directory
            v
DeploymentTrustRootV4
  root version
  DEPLOYMENT role -> ordered Ed25519 key IDs + threshold
            |
            | threshold signatures over DSSE PAE(payload_type, payload bytes)
            v
DeploymentBundleApprovalV4
  exact payload type
  exact immutable deployment-bundle bytes
            |
            | verify signatures before parsing; then canonical parse
            v
DeploymentBundleV4
  deployment_bundle_id
  sequence + exact parent
  validity interval + environment
  authority ceiling = PUBLIC_MARKET_DATA_CAPTURE_ONLY
            |
            | exact, unique, one-of-each closure
            +--------------------+-------------------+------------------+
            |                    |                   |                  |
            v                    v                   v                  v
  CollectorRelease      DependencyLock       TLS Trust Store    Clock Policy
            |                    |                   |                  |
            +--------------------+-------------------+------------------+
                                 |
                                 +-------------+----------------------+
                                               |                      |
                                               v                      v
                                   Runtime Environment       Collector Key
                                                             Authorization
                                               |                      |
                                               +----------+-----------+
                                                          |
                                                          v
                                      VerifiedDeploymentCapabilityV4
                                                          |
                               exact current projection deployment head
                                                          |
                                                          v
                           TransportSubscriptionPolicyV4 + signed session
```

The deployment role key approves a bounded composition. It is not the online
transport signer. `CollectorKeyAuthorizationManifestV4` separately limits one
collector key to `TRANSPORT_ATTESTATION_ONLY`, binds it to the collector release,
and requires its validity interval to cover the complete deployment interval.
The runtime must possess the corresponding public key and the bundle must name
the exact current collector-key authorization.

The six-child closure is closed by type and identity:

| Child role | Frozen content | Required cross-binding |
|---|---|---|
| Collector release | release name/version, source-tree hash, build-artifact hash, entry point, parser-policy root | referenced by runtime environment and collector-key authorization |
| Dependency lock | `PIP_REQUIREMENTS_HASHES_V1`, lock hash, wheelhouse root, distribution count, `require_hashes=true`, `only_binary=true`, `fully_pinned=true` | referenced by runtime environment |
| TLS trust store | exact PEM bundle hash/size, certificate count, DER-set root, `SERVER_AUTH` purpose | referenced by runtime environment and session |
| Clock-source policy | chrony version/executable/config/source-set hashes, source minimum, uncertainty/age limits, synchronized/normal-leap requirements, Linux boot-ID monotonic profile | referenced by runtime environment and live clock evidence |
| Runtime environment | Python implementation/version/executable hash, platform, OpenSSL version, installed-distribution root, isolated-mode and user-site controls | exact links to release, dependency, TLS, and clock children |
| Collector-key authorization | derived key ID, exact Ed25519 public key, transport-only use, release binding, validity interval | key interval covers bundle; runtime signer matches |

### Projection authority

The local projection adds history and current-state constraints; it does not
replace the out-of-band root:

```text
stored root (exactly one; immutable)
-> approved genesis bundle: sequence 1, no parent
-> approved successor: prior sequence + 1, exact prior bundle parent
-> same root and environment
-> every prior transport session terminal
-> current deployment head
-> new policy and session may reference only that head
```

The current implementation deliberately rejects trust-root rotation and
collector-key rotation. Safe rotation needs a new protocol with old-and-new
root continuity, key revocation semantics, session drain, and crash recovery;
silently accepting a different key would weaken rather than improve the
authority graph.

### Runtime and socket authority

The runtime capability is narrower than deployment approval:

```text
verified deployment capability
AND held OS writer lease
AND current projection writer-fence generation
AND governed fresh clock evidence in the signed policy
AND current deployment projection head
AND exact transport policy/session bindings
AND one-use socket_lease_id
AND unexpired one-shot outbound permit
= permission for one bounded public-market-data transport side effect
```

No individual hash, signature, manifest, lease, or fence is sufficient by
itself.

The typed one-socket-per-session binding is only a local projection invariant:
it rejects inconsistent `socket_lease_id` substitution across control records.
It does not prove that a kernel socket or descriptor existed, remained
unchanged, had one OS owner, or received the committed bytes.

## Frozen startup order

### Preconditions outside `PhysicalTransportRuntimeV4.start()`

Before calling `start()`, the operational launcher must eventually perform and
prove all of the following:

1. create and validate the private runtime directory and acquire the unchanged
   writer-lease inode;
2. load the out-of-band expected trust-root ID from a channel independent of
   the deployment bundle;
3. load the exact root, DSSE approval, and six children without following
   unsafe links or accepting mutable replacements;
4. load the collector signing key through the restricted key-loading boundary;
5. materialize fresh governed clock evidence from the signed clock policy; and
6. open the canonical projection in the required durability mode.

Of these launcher-side host adapters, only the writer lease and restricted key
loader exist. Deployment manifests, projection admission, and runtime checks
operate on supplied typed objects; production artifact, external-root, clock,
trust-store, and launcher materializers remain absent.

### Exact implemented `start()` sequence

`PhysicalTransportRuntimeV4.start()` currently enforces this order:

```text
COLD
-> STARTING
-> assert the caller-held OS writer lease
-> sample bounded synchronized clock evidence
-> bind its clock_source_manifest_id for this runtime epoch
-> verify expected root == supplied root
-> verify DSSE threshold over exact payload bytes before parsing
-> parse bundle, verify validity and exact six-child closure
-> verify loaded collector signer is bundle-authorized
-> verify clock evidence/configuration is within signed clock policy
-> assert exact deployment bundle/root/sequence is current projection head
-> derive the writer-lease token digest
-> claim a new transactional projection writer-fence generation
-> verify the complete projection
-> take a strictly later sample in the same monotonic domain
-> reconcile every unterminated session as PROCESS_RESTART
-> validate every returned terminal record and reject duplicates
-> take another strictly later same-domain sample
-> READY with deployment/root/sequence/clock/fence identities
```

Any exception before `READY` sets `FAULT_LATCHED`, best-effort releases the
exact application fence if it may have been claimed, then releases the OS
lease. Cleanup failure is retained in the fault cause. The runtime never
continues with a partially verified deployment.

The startup ordering is internally correct but currently proves only the
objects supplied to it. It does not yet prove that a real wheel, installed
distribution graph, CA bundle, chrony process/configuration, Python executable,
OpenSSL library, or source tree matches those objects.

## Frozen outbound-control protocol

### Two heartbeat layers must remain separate

Bybit's documented heartbeat is an **application Text message**:

```json
{"op":"ping","req_id":"<bounded-id>"}
```

It is not an RFC 6455 Ping control frame. The V4.5 outbound opcode set therefore
contains Text, Pong, and Close, but deliberately contains no proactive RFC Ping.
An inbound RFC Ping still requires an RFC Pong; an inbound Close normally
requires a Close response. The two mechanisms have different payloads,
correlation behavior, evidence, and authority consequences.

### Exact durable chain

The accepted chain for every control side effect is:

```text
reactive RFC path only:
  exact decrypted TLS ingress chunks committed as RawIngressCommitV4
  -> zero or more exact InboundRfcControlTriggerV4 records committed

all paths:
  schedule/trigger/typed protocol-failure cause already durable
  -> OutboundControlIntentV4 committed
  -> exact masked pre-TLS chunks drained into memory and validated
  -> OutboundControlWirePreparedV4 committed
  -> current lease/fence/session/deployment/deadline revalidated
  -> one-shot permit consumed
  -> one serialized TLS-stream write attempt
  -> signed OutboundControlDispatchResultV4 committed
  -> when required, session termination and TCP write-half close
```

Every arrow above is a persistence or authority boundary, not a call-stack
comment. The canonical projection makes these associations unique and replays
them independently. One raw commit may support multiple control triggers only
at distinct, non-overlapping frame offsets. The protocol-failure branch remains
blocked until its first-class typed cause is implemented.

#### 1. Raw ingress commitment

`RawIngressCommitV4` binds the policy, session, scope, adapter, capture
partition, socket lease, connection generation, deployment, writer fence, and
monotonic clock domain to an exact ordered batch of decrypted TLS chunks. Its
`ingress_sequence` is gap-free from one within a transport session; chunk
hashes, batch hash, receipt wall time, and receipt monotonic time are immutable.

This proves only a canonical local commitment over supplied decrypted bytes.
It does not prove a kernel read, a TLS-library event, the peer that sent the
bytes, or that the committed chunks came from a real network connection.

#### 2. Durable inbound RFC trigger

`InboundRfcControlTriggerV4` binds:

- policy, session, scope, adapter, capture partition, socket lease, connection
  generation, `deployment_bundle_id`, and writer-fence epoch;
- a durable raw-ingress commit ID and positive ingress sequence;
- the exact ordered decrypted-TLS chunks, each chunk hash, and batch hash;
- the exact frame offset and frame length inside the concatenated chunks;
- the unmasked Close/Ping/Pong opcode, payload bytes and payload hash; and
- wall and same-domain monotonic receipt clocks.

The contract reparses the selected frame from the durable raw bytes and rejects
opcode, length, or payload disagreement. A frame may span ingress chunks.
Inbound server frames must be unmasked. Control payloads are limited to 125
bytes, and Close payloads receive status-code and UTF-8 validation.

#### 3. Logical intent

`OutboundControlIntentV4` binds the same connection/deployment/fence scope, a
strict per-session `control_sequence`, and the exact previous intent. Its four
closed kinds are:

| Kind | Cause | Exact opcode/payload | Session-authority effect |
|---|---|---|---|
| `APPLICATION_JSON_HEARTBEAT` | one durable scheduled-heartbeat identity | one Text frame containing canonical `{"op":"ping","req_id":...}` | does not itself fence |
| `RFC_PONG` | one exact durable inbound RFC Ping | Pong with byte-for-byte echoed Ping payload | does not fence |
| `RFC_CLOSE_REPLY` | one exact durable inbound Close | Close with byte-for-byte echoed valid Close payload | fences immediately |
| `RFC_PROTOCOL_FAILURE_CLOSE` | one durable protocol-failure evidence identity | Close code 1002 | fences immediately |

The heartbeat schedule ID is causal metadata carried by the durable intent,
not a separate authority record. `RFC_PROTOCOL_FAILURE_CLOSE` remains a frozen
contract kind but is not projection-admissible until a first-class typed
protocol-failure cause exists; an arbitrary existing record is not sufficient.

Intent authorization has both governed wall-clock and monotonic deadlines.
Only sequence one may omit a predecessor. The projection enforces that sequence
and predecessor globally for the session, not merely inside one object.

#### 4. Exact pre-TLS wire preparation

`OutboundControlWirePreparedV4` stores the ordered chunks returned by the
Sans-I/O protocol, per-chunk hashes, a batch hash, and total length. It reparses
their concatenation and accepts exactly one complete, final, client-masked
WebSocket frame whose opcode and unmasked payload equal the logical intent.
Text must be valid UTF-8; control payloads and Close status/reason rules are
rechecked.

The committed bytes are the exact WebSocket octets submitted to the TLS stream,
not TLS ciphertext. TLS ciphertext can change with record boundaries, keys,
nonces, and implementation behavior; it is neither the stable application
intent nor available before encryption. Conversely, pre-TLS bytes do not prove
that the peer received or processed them.

#### 5. One-shot dispatch result

`OutboundControlDispatchResultV4` is signed by the deployment-authorized
collector key and binds the intent, prepared wire record, session/socket,
connection generation, deployment, writer fence, wire hash/length, one-shot
permit, clocks/deadline, byte count, and outcome.

Only two outcomes exist:

- `SENT`: all prepared WebSocket octets were submitted to the TLS writer and no
  local error digest exists; or
- `UNKNOWN_DELIVERY`: the write was attempted but local observation cannot
  prove the peer outcome; an error-class digest is mandatory and any submitted
  byte count from zero through the full frame is allowed.

Both outcomes require `permit_consumed=true` and attempt ordinal one. Once a
write begins, timeout, cancellation, short write, TLS failure, connection loss,
or uncertainty consumes the intent. It is never replayed. `SENT` is not a
claim of peer receipt, exchange processing, application Pong, or exactly-once
delivery.

The current projection records the unique permit only in this post-attempt
result; it does not yet persist a distinct pre-write permit-consumption
transition. Therefore the projection alone cannot distinguish “prepared but
never attempted” from “attempted, then crashed before result.” The runtime
slice must conservatively treat every prepared wire as an irrevocable
at-most-once slot, never resend an orphan after restart, and terminate/fence the
session on uncertainty. A dedicated durable pre-write permit is still the
preferred closure.

### Required Sans-I/O receive mediation

`websockets` Sans-I/O responds to Ping, Close, and invalid input automatically
when inbound bytes are processed. Automatic here means that bytes are queued
in memory for `data_to_send()`; it does not require the integration to write
them immediately. The frozen adapter order is:

```text
read decrypted TLS bytes
-> durably append the raw ingress chunk before semantic use
-> feed the same bytes once to ClientProtocol.receive_data()
-> immediately drain every data_to_send() item into owned memory, never socket
-> inspect events and raw bytes; create the exact trigger or protocol-failure cause
-> durably append trigger/cause, intent, and prepared-wire records
-> revalidate deployment, session, socket lease, writer fences, and deadline
-> consume one permit and submit the exact prepared chunks to TLS
-> append signed dispatch result
-> process application data only through the existing raw-first pipeline
```

The protocol object is sequential and has one owner. Reads are serialized;
writes are serialized through one writer. No other library task, keepalive
task, close handler, cancellation callback, or application coroutine may call
the TLS writer.

When `data_to_send()` yields the empty `SEND_EOF` marker, the adapter must record
the close state and half-close the TCP write side after all prior durable
records and permitted bytes. It must not treat `b""` as a zero-length frame or
silently discard it.

### Application heartbeat scheduling and observation

The first implementation profile is intentionally narrow:

1. schedule one heartbeat approximately every 20 seconds only while the
   current session remains open and authority-eligible;
2. permit at most one unresolved application heartbeat per session;
3. generate one bounded, unique request ID and canonical Text payload;
4. commit schedule, intent, prepared frame, and dispatch result in order;
5. raw-capture the provider response as an ordinary Text message;
6. classify exact request-ID echo separately from a weak provider Pong with an
   empty or omitted `req_id`; and
7. use either observation only for connection-health diagnostics, never as a
   subscription ACK or H1 market-data authority.

Bybit documents `req_id` as optional and shows an empty `req_id` on the public
Linear channel. Exact correlation therefore cannot be claimed as a provider
guarantee. Requiring exact echo may be a testnet/mainnet conformance policy;
missing echo must not be repaired by arrival order, inferred connection ID, or
the most recent outstanding request.

### Close and failure precedence

- An inbound Close fences session authority before its response is written.
- No application data frame may be authorized after a Close intent.
- A protocol failure fences authority and permits only one code-1002 Close
  attempt when the Sans-I/O state allows it.
- If a Close was already received, no Pong obligation is created for a later
  Ping in the same batch.
- If Ping and Close obligations were queued in protocol order before closing,
  prepared chunks must retain the exact library order; the adapter may not
  reorder or combine them.
- The bounded V4.5 projection slice does not yet persist a typed multi-obligation
  Sans-I/O queue. It therefore fails closed if a prior Ping remains unresolved
  when a Close trigger becomes durable: general authority and the older Pong
  path are blocked, and only the exact Close-reply continuation is admissible.
  Supporting both ordered obligations requires a later first-class queue
  contract; they must never be silently reordered.
- Any storage uncertainty before a write prevents the write. Any uncertainty
  after a write begins produces `UNKNOWN_DELIVERY`, terminates the session, and
  requires a new connection generation subject to backoff.

RFC 6455 requires Pong and Close responses as soon as practical but defines no
numeric deadline. The repository must select, measure, and freeze a conservative
local control deadline; it must not mislabel that local value as an RFC rule.

## Research basis and limits

| Primary source | What the source establishes | Limitation and repository use |
|---|---|---|
| Secure Systems Lab, [DSSE protocol at audited revision](https://github.com/secure-systems-lab/dsse/blob/8fca562ae08478e4f8d94680040b6456697fa41a/protocol.md) and [project scope](https://github.com/secure-systems-lab/dsse) | PAE authenticates payload type and exact payload bytes and avoids JSON-canonicalization dependence | DSSE explicitly leaves key management/PKI out of scope. V4.5 adds an out-of-band root ID and role threshold, but does not call this a complete PKI or software-update framework |
| SLSA, [Build provenance v1.2](https://slsa.dev/spec/v1.2/build-provenance) and [artifact verification](https://slsa.dev/spec/v1.2/verifying-artifacts) | Build provenance describes where, when, and how an artifact was produced; verification must compare provenance and artifact against expectations | A signed RiskYieldMM deployment bundle is not build provenance. Actual builder identity, invocation, materials, artifact subject digest, and consumer verification remain absent |
| pip, [Secure installs](https://pip.pypa.io/en/stable/topics/secure-installs/) and [Repeatable installs](https://pip.pypa.io/en/stable/topics/repeatable-installs/) | `--require-hashes` is all-or-nothing, transitive dependencies must be named and hashed, pinned requirements are required, and `--only-binary :all:` plus a wheelhouse can narrow installation inputs | Broad `>=` dependencies and an unhashed optional extra do not satisfy this. The manifest booleans are requirements for a future real lock/wheelhouse verifier, not proof today |
| The Update Framework, [specification](https://theupdateframework.github.io/specification/latest/) | A complete update system addresses root continuity, thresholds, expiry, rollback, freeze, mix-and-match, and key rotation | V4.5 makes no TUF-compliance claim; it borrows only selected role-separation, threshold, expiry, and anti-rollback ideas. Its single pinned root and linear local bundle chain are narrower and currently lack a root-update/revocation protocol |
| Python, [`-I` isolated mode](https://docs.python.org/3/using/cmdline.html#cmdoption-I) | Isolated mode implies `-E`, `-P`, and `-s`, excludes script and user-site paths, and ignores `PYTHON*` environment variables | A manifest field saying isolated mode is true does not prove the production interpreter started with those semantics; launcher and runtime verification are required |
| chrony, [`chronyc tracking`, `sources`, and monitoring commands](https://chrony-project.org/doc/4.8/chronyc.html) | `tracking` and `sources` expose synchronization and source state without changing chronyd behavior | A parser must bind exact executable/config/source-set identities, reject unsynchronized or abnormal-leap state, bound sample age/uncertainty, and be adversarially tested. No such adapter exists |
| Linux man-pages, [`clock_gettime(2)`](https://man7.org/linux/man-pages/man2/clock_gettime.2.html) | `CLOCK_MONOTONIC` cannot be set, does not jump with `CLOCK_REALTIME`, and on Linux is relative to boot | Monotonic values alone are not cross-boot identities. V4.5 freezes a boot-ID plus monotonic-domain profile, but the real boot-ID reader/attestor is missing |
| Python, [`ssl` module](https://docs.python.org/3/library/ssl.html) | `SSLContext` exposes certificate/hostname validation, trust loading, TLS version policy, and negotiated session facts | Declared CA hashes and booleans do not prove the exact bytes were loaded into the actual context or used for the session |
| IETF, RFC 6455 [Section 5.3](https://www.rfc-editor.org/rfc/rfc6455.html#section-5.3) and [Section 5.5](https://www.rfc-editor.org/rfc/rfc6455.html#section-5.5) | Client frames are masked; control frames are unfragmented and at most 125 bytes; Ping requires matching Pong unless Close was received; inbound Close normally requires a Close response; data is forbidden after sending Close | The RFC does not provide a numeric response deadline, delivery acknowledgement, application-heartbeat format, or exactly-once guarantee |
| `websockets` 16.0, [Sans-I/O integration guide](https://websockets.readthedocs.io/en/16.0/howto/sansio.html), [client API](https://websockets.readthedocs.io/en/16.0/reference/sansio/client.html), and [tagged protocol source](https://github.com/python-websockets/websockets/blob/16.0/src/websockets/protocol.py) | The integration owns network I/O; after `receive_data()` it drains `data_to_send()`; Ping, Close, and invalid-input responses are queued automatically; `SEND_EOF` means half-close | The library does not provide the repository's durable ordering. V4.5 must interpose persistence and authorization between queueing bytes and writing them |
| Bybit, [V5 WebSocket connection documentation](https://bybit-exchange.github.io/docs/v5/ws/connect) | Public Linear endpoint, JSON ping shape, recommended 20-second heartbeat, optional request ID, example empty request ID, and connection-rate guidance | Documentation is provider behavior, not a durable local transaction. Request-ID echo and timing require non-authoritative conformance measurement; heartbeat response cannot establish subscription authority |

### Local source confirmation

An exploratory, non-recorded local probe against an installed `websockets` 16
Sans-I/O implementation observed a masked Pong after inbound Ping, a masked
Close echo after inbound Close, preserved Ping/Close output order, and a queued
protocol-error Close for malformed masked server input. It is not repository
verification, reproducible evidence, production conformance, or a
dependency-provenance result; the real adapter must turn these observations
into pinned deterministic tests.

## Alternatives considered and rejected

| Alternative | Why it appears attractive | Decision |
|---|---|---|
| Trust a root file stored beside its self-signed bundle | Simple packaging | Rejected: the bundle can choose its own authority. The expected root ID must arrive independently |
| Treat a valid DSSE signature as build provenance | Compact signed evidence | Rejected: it authenticates bytes under a key but does not establish builder, source/materials, invocation, or actual artifact correspondence |
| Treat `pyproject.toml` bounds as a dependency lock | Existing packaging already installs | Rejected: broad lower bounds allow a changing transitive graph and carry no local artifact hashes |
| Implement complete TUF before continuing | Strong update-security model | Postponed, not dismissed: V4.5 needs a bounded offline local deployment gate first. It must state explicitly that root rotation, online update metadata, rollback/freeze defense, and TUF compliance are absent |
| Use high-level `websockets.connect()` or official `pybit` as the authority driver | Convenient reconnect, ping, parsing, and callbacks | Rejected for the authority path: those conveniences can perform hidden control writes, auto-reconnect/resubscribe, or parse before raw persistence. They may remain non-authoritative diagnostics |
| Fork or reimplement RFC 6455 merely to suppress automatic Pong/Close | Maximum apparent control | Rejected: a mature pinned Sans-I/O parser is safer. Its generated bytes can be drained into memory, validated, persisted, and authorized before network I/O |
| Allow the library to write mandatory Pong/Close before journaling | Lowest response latency | Rejected: it creates unaccounted external side effects. Raw ingress is persisted first and queued output stays in memory until durable authorization |
| Send proactive RFC Ping instead of Bybit JSON ping | Common WebSocket keepalive pattern | Rejected for the minimal profile: Bybit documents an application JSON heartbeat. Proactive RFC Ping would add another scheduler/correlation protocol without demonstrated need |
| Retry the same control intent after timeout or partial write | Might improve liveness | Rejected: remote delivery is unknowable after write start. Retry could duplicate side effects or cross a connection generation |
| Commit TLS ciphertext as the canonical intent | Closest bytes to the wire | Rejected as the primary commitment: ciphertext is session/record-bound and generated after the authorization boundary. Exact masked pre-TLS WebSocket octets are the stable object submitted to TLS |
| Accept weak/empty heartbeat Pong as subscription ACK | Avoids idle disconnects and simplifies correlation | Rejected: heartbeat and subscription authority are distinct protocols, and Bybit does not guarantee request-ID echo in the documented Linear examples |
| Treat synthetic contract fixtures as deployment evidence | Tests are deterministic and comprehensive at the object layer | Rejected: fixtures can prove validation logic but cannot prove actual build, CA, clock, host, network, or provider state |

## Deployment-readiness gap analysis

| Gap | Current evidence | Why it blocks provider authority | Required closure |
|---|---|---|---|
| Broad and unhashed dependency graph | Core and most optional dependencies use lower bounds; `requirements-ci.txt` is only `-e .[ci]`; no Python lock/wheelhouse was found; only `websockets==16.0` is directly pinned | The same source can execute different transitive code, and a manifest can name fictional hashes | Generate platform-specific fully pinned, fully hashed transitive locks; build a sealed wheelhouse; install offline with `--require-hashes --only-binary :all: --no-deps`; verify every installed distribution/file root |
| No built collector artifact | No release wheel/OCI artifact or production release-manifest materializer was found | `build_artifact_sha256` and `source_tree_sha256` are caller declarations | Build from a clean immutable revision; record artifact subject digest, source revision, parser-policy root, entry point, build logs, and reproducibility result |
| No build provenance | No SLSA/in-toto provenance or trusted builder policy is consumed | A deployment signature cannot show how the artifact was produced | Produce and verify provenance with explicit builder identity, invocation, materials, and artifact subject; define accepted signer-builder pairs and fallback policy |
| No production trust-root evidence | Tests construct keys; projection stores one root but says storage is not its external anchor | A colocated root or compromised single operator could approve arbitrary bundles | Perform an operator root ceremony, use threshold/offline key custody, pin the initial root independently, audit approvals, and design revocation/root rotation before first rotation |
| No real TLS trust-store evidence | Contract has bundle and DER-set hashes, count, and purpose only | The process may load different ambient CAs or a different SSL context | Materialize the exact CA bundle, parse and hash sorted DER certificates, create one context from only those bytes, verify hostname and purpose, and retain negotiated/certificate evidence |
| No real clock evidence | Clock source is an injected port with synthetic tests; no chrony or boot-ID reader was found | Validity, deadlines, and cross-restart causality can be forged or stale | Implement strict chronyc machine-readable parsing plus executable/config/source-set verification, synchronized/leap/source checks, bounded uncertainty/age, boot-ID domain binding, and failure injection |
| Runtime manifest does not prove running host | Python/OpenSSL/distribution fields are immutable declarations | Caller can claim the approved environment while running another | At startup hash the actual executable, query exact interpreter/OpenSSL/platform state in isolated mode, enumerate installed distributions/files, and compare all roots before authority |
| No real Sans-I/O/TLS adapter | `websockets==16.0` is only in an optional extra; production code does not import `ClientProtocol`, `receive_data`, or `data_to_send` | Exact handshake, masking, automatic control, partial writes, cancellation, and half-close behavior remain unobserved | Implement one owned direct TLS stream and one sequential Sans-I/O protocol with no proxy, compression, subprotocol, or ambient keepalive; instrument exact pre-TLS chunks and all stream outcomes |
| Control projection is not runtime-mediated | Five records and independent replay exist locally; permit identity appears only in the post-attempt result | Records alone cannot prove runtime-before-write ordering, durable pre-write consumption, or prevent a bypassing writer | Integrate scheduling, receive mediation, a durable pre-write permit, dispatch outcomes, fencing, terminal/half-close transitions, orphan-prepared-wire rejection, and stale-callback rejection into the runtime |
| No durable heartbeat observation model | Contract creates heartbeat intent but no response/correlation record or outstanding-heartbeat projection | Health can become ambiguous and weak responses may be overinterpreted | Add exact/weak/ambiguous response dispositions, one-outstanding rule, timeout, connection-generation binding, and explicit non-authority semantics |
| No close/TCP lifecycle evidence | V4.5 control contract stops at dispatch result | A Close frame, peer EOF, local half-close, TLS shutdown, and socket abort can be conflated | Freeze and persist WebSocket close state, `SEND_EOF`, TCP half-close/full-close, timeout/abort, and causal terminal reason without claiming peer agreement |
| No provider conformance or reconnect controller | Only official documentation and local protocol probes exist | Request-ID echo, heartbeat behavior, server Close/Ping patterns, rate limits, and endpoint drift are unmeasured | Run read-only testnet then mainnet captures; implement bounded exponential backoff with jitter and the documented connection ceiling; detect behavior drift and fail closed |
| No process/storage crash campaign | Focused object/runtime tests are deterministic unit tests | SQLite commit uncertainty and kill timing may violate intended ordering | Inject process kill, cancellation, fsync/SQLite faults, lease loss, and restart after every durable and write boundary; verify one canonical replay result and no duplicate write authorization |

## Explicit nonclaims

This freeze does not claim any of the following:

- the available data or models contain stable predictive edge;
- profitability before or after fees, spread, slippage, latency, or impact;
- that a particular heartbeat or control policy improves trading performance;
- build reproducibility, SLSA level, in-toto verification, TUF compliance, SBOM
  completeness, vulnerability freedom, or dependency non-compromise;
- that a signed manifest corresponds to the bytes currently running;
- remote attestation, measured boot, host integrity, kernel integrity, hardware
  key protection, or protection against a malicious same-user process;
- that the locally stored trust root is independently trustworthy;
- safe root or collector-key rotation;
- that the named CA bundle or chrony state was actually loaded or observed;
- mask-key unpredictability merely because a frame is syntactically masked;
- exact TLS record boundaries or ciphertext;
- peer receipt, peer processing, exactly-once delivery, or distributed atomicity;
- request-ID echo on Bybit Linear, heartbeat response timing, or permanent
  provider behavior;
- that a heartbeat proves subscription success, market-data freshness, bar
  completeness, H1 eligibility, or H2 execution authority;
- real socket/TLS/WebSocket handling, real-socket raw-first persistence,
  partial-write behavior, reconnect safety, or storage-crash safety;
- private-stream authentication, order entry, paper trading, live trading, or
  permission to use exchange credentials.

## Acceptance criteria before a real provider socket

### A. Reproducible deployment evidence

- [ ] Build from a clean immutable revision; record the revision and reject a
  dirty source tree.
- [ ] Produce the exact collector artifact and verify its hash before launch.
- [ ] Produce a fully pinned transitive lock with local SHA-256 hashes for every
  accepted platform artifact, including `websockets==16.0` and its complete
  dependency closure.
- [ ] Build a content-addressed wheelhouse and prove an offline installation
  admits no undeclared distribution or source build.
- [ ] Generate the six child manifests from measured bytes, not free-form CLI
  arguments; independently re-read and verify them at startup.
- [ ] Generate and verify build provenance against frozen builder/source/build
  expectations. If provenance is unavailable, the deployment remains explicitly
  non-production rather than silently downgraded.
- [ ] Verify actual Python executable, isolated-mode state, user-site exclusion,
  OpenSSL identity, platform, and complete installed-distribution root.

### B. Root, signing-key, TLS, and clock governance

- [ ] Complete a documented out-of-band root ceremony with more than one role
  key and a threshold that tolerates one key compromise.
- [ ] Keep root private keys offline; record approval participants and audit
  bundle sequence/expiry.
- [ ] Define root compromise, revocation, rollback/freeze, emergency expiry,
  and dual-threshold rotation procedures before rotation is needed.
- [ ] Load the collector key from a mode/owner/link-checked secret path or
  hardware-backed equivalent and prove it matches the key authorization.
- [ ] Hash and parse the exact CA bundle and sorted DER set, load only it into
  the production `SSLContext`, require certificate and hostname verification,
  and capture negotiated evidence.
- [ ] Implement the signed chrony/boot-ID clock adapter and prove fail-closed
  behavior for stale sample, excess uncertainty, unsynchronized state,
  abnormal leap, too few acceptable sources, config/executable drift, reboot,
  and monotonic non-advance.

### C. Canonical outbound-control persistence

- [x] Add all five V4.5 records to the canonical ledger/projection and typed
  replay.
- [x] Enforce exact per-session raw/control sequence, predecessor, deployment,
  fence, socket, generation, clock-domain, and deadline continuity.
- [x] Enforce one supported heartbeat/trigger cause per intent, one wire
  preparation per intent, one unique result permit, and one dispatch result.
  Protocol-failure Close remains categorically rejected until its typed cause
  exists.
- [x] Reject orphan, duplicate, conflicting, reordered, cross-session,
  cross-generation, cross-deployment, stale-fence, expired, or post-Close
  records both at append time and full replay.
- [ ] Add a durable pre-write permit-consumption transition. Until then, any
  prepared wire must be an irrevocable at-most-once slot that a restarted
  runtime never resends.
- [ ] Add one-outstanding application-heartbeat state and exact/weak/ambiguous
  response dispositions with no subscription-authority implication.
- [ ] Persist session fencing and close/half-close lifecycle in causal order.

### D. Real adapter and adversarial tests

- [ ] Use the exact hashed `websockets` 16 artifact through its public Sans-I/O
  API; disable extensions, subprotocols, ambient proxy discovery, and autonomous
  keepalive/reconnect.
- [ ] Prove raw ingress is durable before `receive_data()` and prove every
  `data_to_send()` octet is held in memory until its durable intent/wire records
  and permit exist.
- [ ] Prove a single owner and serialized writer are the only paths to TLS.
- [ ] Verify exact client masking, payload echo, protocol-error code 1002,
  Ping/Close ordering, no data after Close, and `SEND_EOF` half-close.
- [ ] Test split and coalesced frames, frame boundaries across TLS reads,
  multiple controls in one read, malformed frames, invalid UTF-8/status codes,
  partial TLS writes, cancellation, timeout, peer EOF, stale callbacks, queue
  saturation, storage faults, lease replacement, reboot, and deployment expiry.
- [ ] Kill the process after every durable append, permit transition, byte-count
  transition, and socket outcome; restart must produce one deterministic
  terminal state and never reauthorize the consumed intent.
- [ ] Instrument the adapter so a test can prove zero outbound WebSocket octets
  bypassed the canonical mediator.

### E. Provider conformance and no-trading soak

- [ ] Complete deterministic fake-server tests before Internet access.
- [ ] Run read-only Bybit testnet conformance for endpoint/TLS, application
  heartbeat response variants, RFC Ping/Close behavior, request-ID behavior,
  disconnects, backoff, and rate-limit safety.
- [ ] Run a separately approved, credential-free mainnet public-data
  conformance capture; never infer exact request-ID echo from documentation.
- [ ] Complete at least a 24-hour testnet and 7-day no-trading mainnet soak with
  zero unjournaled outbound frames, zero silent evidence drops, zero duplicate
  intent attempts, zero stale-generation admissions, and complete restart
  reconciliation. Longer 30-day/capacity soaks remain required before any
  production-readiness claim.
- [ ] Freeze measured deadlines, queue bounds, reconnect backoff, and resource
  budgets only after observed latency and failure distributions are recorded.

### F. Go/no-go rule

Any missing artifact, mismatched hash, invalid signature, expired bundle,
noncurrent deployment, uncertain/stale clock, changed CA/runtime/dependency
state, stale writer fence, storage uncertainty, malformed control chain,
provider drift, or unknown write outcome disables authority and requires a
fresh governed generation. No test exception, debug mode, or high-level client
fallback may bypass this rule.

## Verification recorded at freeze time

The final checkpoint verification ran the dedicated V4.5 suites for operational
manifests, deployment projection, restricted key loading, control contracts,
and control projection:

```text
tests/test_trading_operational_manifests_v4.py
tests/test_trading_operational_manifests_v4_projection.py
tests/test_trading_transport_key_loading_v4.py
tests/test_trading_physical_transport_control_v4_contracts.py
tests/test_trading_physical_transport_control_v4_projection.py

107 passed
```

The wider authority/transport sweep passed **232 tests**, the complete physical
surface passed **344 tests**, and the complete repository passed **1,636 tests
with 32 skipped**. These results cover strict contracts, SQLite append/replay,
typed/canonical bijection, runtime admission, cross-path fencing, health/gate
fail-closed behavior, reopen verification, and existing integration behavior
under local synthetic fixtures. They are not build, host, clock, TLS, provider,
process-crash, soak, or deployment evidence and do not reduce the operational
gaps above.

## Next implementation slice

The next bounded slice is **V4.5 runtime control mediation, still without a
provider socket**:

1. consume the existing five-record projection from one serialized runtime
   owner with no alternate control-output path;
2. extend the runtime with one-outstanding heartbeat scheduling, durable inbound
   trigger admission, a first-class protocol-failure cause, durable pre-write
   permit consumption, signed dispatch outcomes, Close/failure fencing, and
   stale callback rejection;
3. use a deterministic in-memory protocol-output fixture to exercise the
   mediation boundary without network I/O;
4. inject failure after every append/permit/outcome boundary and prove restart
   never retries an attempted intent; and
5. prove every runtime-produced control output passes through the mediator,
   then rerun the focused and complete physical-authority suites with a clean
   diff check.

This slice is the best next dependency because the real Sans-I/O/TLS adapter
must have a crash-safe place to put automatically generated bytes before it can
be connected. In parallel, a separate operational-evidence slice must replace
synthetic dependency/release/TLS/runtime/clock manifests with measured artifact
builders and verifiers. **Both slices are prerequisites for any real provider
connection.**

After those prerequisites, the order is:

```text
real chrony + boot-ID adapter
-> exact artifact/lock/wheelhouse/trust-store/runtime verifier
-> direct TLS + pinned Sans-I/O adapter behind the control mediator
-> deterministic fake-server crash campaign
-> read-only testnet conformance
-> credential-free mainnet no-trading conformance and soaks
-> only then reconsider public-data authority readiness
```

Nothing in that sequence licenses H2 execution or supports a profitability
claim. It makes the data and operational boundary more falsifiable, which is a
necessary input to later leakage-free model and trading evaluation.
