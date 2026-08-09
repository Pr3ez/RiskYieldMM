# V4.9A exact TLS 1.3 and WebSocket Sans-I/O engine freeze

**Date:** 2026-07-15  
**Status:** bounded local engine and trust-store closure implemented and
fake-server accepted; live construction remains deny-gated  
**Roadmap position:** Stage 1 critical corrections, after V4.8B loaded-chronyd
provenance and before driver-derived live session admission

## 1. Decision

V4.9 is split at the first boundary that can be falsified without silently
activating an incomplete provider transport.

V4.9A selects:

- one fresh `ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)` per connection;
- `minimum_version == maximum_version == TLSv1_3`;
- `ssl.SSLObject` over paired `ssl.MemoryBIO` objects and an already-owned
  nonblocking raw socket;
- exact `websockets==16.0` `ClientProtocol` Sans-I/O;
- an exact retained CA artifact loaded without ambient platform roots;
- a one-owner serialized state machine;
- exact HTTP request/response transcript hashes;
- separation of an HTTP `101` response from any coalesced first WebSocket
  bytes;
- a hard raw-before-WebSocket-parse transition; and
- automatic Pong/Close output drained into owned memory with zero receive-path
  socket writes.

It does **not** remove the V4.8B live factory gate. This is intentional. The
existing runtime and projection still reject caller-authored live session
facts, and V4.9A doesn't yet connect its driver observation to their atomic
session/socket-owner commit.

```text
signed TLS trust manifest + operational CA path
  -> retained O_NOFOLLOW regular-file descriptor
  -> exact bundle digest and size
  -> strict certificate-only PEM parse
  -> unique canonical DER certificate set
  -> fresh OpenSSL client trust store with the same DER set
  -> private TLS 1.3-only SSLContext / SSLObject / MemoryBIO pair
  -> exact websockets 16.0 ClientProtocol
  -> TLS handshake and HTTP upgrade
  -> sealed noncanonical driver observation
  -> [V4.9B atomic session/owner commit -- still pending]
  -> coalesced or later TLS plaintext held as PendingRawIngressV49
  -> exact RawIngressCommitV4 presented
  -> and only then ClientProtocol.receive_data()
  -> automatic output held in memory
  -> [durable ordered output mediation -- still pending]
```

## 2. Why this architecture

| Candidate | Assessment | Decision |
|---|---|---|
| High-level `websockets.connect()` | Convenient, but it owns network I/O, reconnect, keepalive, and automatic control behavior outside the existing durable authority boundary | Rejected for the authority path |
| `SSLObject` + `MemoryBIO` + `websockets` Sans-I/O | Makes TLS and WebSocket network I/O caller-owned, preserves the already pinned parser and V4.6 failure contracts, and permits output to be held before a durable permit | **Selected** |
| `wsproto` | Its explicit events are attractive, but it adds `h11`, isn't installed, and would invalidate the current `websockets==16.0` behavior and exception commitments | Postponed to a separately versioned redesign only if V4.9 falsification fails |
| New in-repository RFC 6455 implementation | Maximum local control, but creates a large security-critical parser/serializer surface for fragmentation, UTF-8, masking, lengths, controls, and closing | Rejected |
| `SSLSocket` wrapping the retained socket | Simpler, but obscures the exact TLS input/output boundary and makes one retained raw owner harder to preserve | Rejected |

This is the strongest fit for the existing record graph, not a universal claim
that the chosen libraries are superior for every WebSocket client.

## 3. Exact trust-store closure

`PinnedTlsTrustStoreV49` converts the signed manifest from metadata into a
runtime-checked trust input:

1. open the operational path through `PinnedRuntimeArtifactV4` without
   following a final symlink;
2. retain a non-inheritable descriptor and verify the signed SHA-256 and exact
   byte size;
3. permit only PEM `CERTIFICATE` blocks separated by ASCII whitespace;
4. reject comments, other PEM block types, trailing text, malformed blocks,
   duplicates, and an empty bundle;
5. parse each certificate to DER with `cryptography`;
6. derive a domain-separated root from sorted certificate-DER SHA-256 values;
7. compare exact certificate count and DER-set root with
   `TlsTrustStoreManifestV4`;
8. create a new raw client `SSLContext`, never `create_default_context()`;
9. load only the admitted blocks through `cadata`;
10. compare `get_ca_certs(binary_form=True)` back to the signed unique DER set;
    and
11. repeat artifact and OpenSSL-view validation on every context build and
    currentness check.

The context has TLS 1.3 minimum and maximum, `CERT_REQUIRED`, hostname checks,
`OP_NO_COMPRESSION`, `OP_NO_TICKET` where exposed, and no key-log file. No
system default CA, `SSL_CERT_FILE`, `SSL_CERT_DIR`, or `SSLKEYLOGFILE` path is
loaded by this implementation.

`VERIFY_X509_STRICT` is not enabled in V4.9A. It disables compatibility
workarounds, but must first be falsified against the measured provider chain
and exact deployment CA bundle. This is a documented compatibility/security
decision, not an accidental default.

## 4. Exact engine invariants

### 4.1 Private construction and currentness

The exact engine constructs and retains its own context, BIOs, `SSLObject`,
request, and `ClientProtocol`. It accepts none of them from a caller and exposes
none of them through a supported property.

It records its creation process, thread, event loop, socket object, descriptor
stat, peer address, and nonblocking mode. Every operation revalidates those
facts, the exact `websockets` distribution version, the pinned trust artifact,
the context options, verification flags, cipher profile, and effective CA DER
set. A failed or cancelled transition latches the engine; it cannot resume the
connection.

Python object privacy is not a security boundary against arbitrary malicious
code in the same process. Process isolation and measured runtime artifacts
remain deployment gates.

### 4.2 TLS profile

The client:

- sends exact SNI `stream.bybit.com`;
- uses `CERT_REQUIRED` plus hostname verification with common-name fallback
  disabled;
- negotiates exactly TLS 1.3;
- rejects session reuse, TLS compression, or negotiated ALPN;
- records the negotiated cipher name;
- records the exact leaf-certificate and leaf-SPKI SHA-256 values; and
- uses no 0-RTT application API or session supplied by a caller.

Python's public `ssl` API does not expose TLS 1.3 cipher-suite configuration
through `set_ciphers()`. V4.9A therefore records the negotiated suite but does
not claim a signed cipher allowlist. A later policy must define and validate
such an allowlist from observed provider compatibility before promotion.

Python 3.12 also lacks a public `SSLObject.get_verified_chain()` contract.
V4.9A records the leaf only and makes no complete presented/verified-chain,
selected-anchor, OCSP, CRL, Certificate Transparency, or revocation claim.
Full portable chain evidence requires an explicitly approved Python/OpenSSL
profile and a versioned record extension; private `_sslobj` methods are not
used.

### 4.3 HTTP opening handshake

`ClientProtocol` generates one exact request with the signed Host and path,
Upgrade/Connection, a fresh WebSocket key, and version 13. No origin,
extension, subprotocol, proxy, redirect, reconnect, or keepalive layer exists.

The engine buffers bounded decrypted response bytes until the first exact
`\r\n\r\n`. It preserves and hashes the original bytes, rejects NUL, bare LF,
obsolete folding, excessive headers, duplicate critical headers, body-framing
headers, extensions, and subprotocols, and requires one successful empty HTTP
101 response event with no generated protocol output.

Critically, bytes after the delimiter are not passed to `ClientProtocol`.
They remain a private coalesced suffix until the exact handshake evidence is
consumed by the later session-binding boundary.

### 4.4 Raw-before-parse and automatic output

After binding the one exact handshake observation, any coalesced suffix becomes
`PendingRawIngressV49`. Later TLS reads produce the same type. While a raw batch
is pending, no additional read, application send, or parser transition is
admitted.

`parse_durable_ingress()` requires an exact `RawIngressCommitV4` with the same
gap-free ingress sequence, chunk count, chunk boundaries, and bytes. It then
feeds each committed chunk once to `ClientProtocol`, captures frame events,
and drains every `data_to_send()` item exactly once. The receive path never
writes those bytes.

V4.9A proves this state-machine ordering locally. It does not yet prove that a
caller-presented `RawIngressCommitV4` has a canonical SQLite receipt. V4.9C
must make the exact projection append and parser call one internal owner
operation, with the projection result unavailable to public substitution.

Multiple automatic outputs are preserved in library order. The current V4.6
control mediator intentionally accepts exactly one drain item, so a multi-item
batch remains unsendable and fails closed. V4.9C must introduce a first-class
ordered obligation queue; it may not select, merge, reorder, or drop outputs.

### 4.5 Writes and limits

The compatibility subscription method proves that the retained protocol
generated one masked Text frame whose decoded payload equals the authorized
logical bytes before submitting it to TLS. This closes opcode/framing behavior
but does not yet persist the random mask and exact frame bytes.

Automatic control submission requires the exact pending output tuple and an
exact `OutboundControlWritePermitConsumedV4` whose length and ordered-batch
hash agree. Exceptions or cancellation latch the engine.

The implementation still uses `loop.sock_sendall()` below the TLS BIO. It can
therefore prove complete return or uncertainty, not each positive partial
kernel send. Existing mediator semantics correctly record an exception after
the call boundary as unknown delivery with no fabricated zero count. Exact
partial-send accounting remains a V4.9C gate.

## 5. Implemented files

| Concern | File |
|---|---|
| Strict PEM/DER set, pinned artifact, exact OpenSSL store | `riskyieldmm/trading/tls_trust_store_v49.py` |
| TLS 1.3 MemoryBIO engine, HTTP split, handshake observation, raw-first parser gate, held output | `riskyieldmm/trading/physical_transport_tls_v49.py` |
| Trust-store adversaries | `tests/test_trading_tls_trust_store_v49.py` |
| Real local TLS/WebSocket fake-server adversaries | `tests/test_trading_physical_transport_tls_v49.py` |
| Exact test/development transport dependency | `pyproject.toml` |

The modules aren't exported from the package-wide `trading.__init__` because
`websockets` remains an optional transport dependency. Tests and the future
sealed factory import the module explicitly.

## 6. V4.9A acceptance evidence

The deterministic trust tests cover:

- domain separation, set ordering, and duplicate rejection;
- fresh contexts and exact effective OpenSSL roots;
- digest, size, count, and DER-root mismatch;
- comments, other PEM blocks, trailing text, malformed certificates, and
  duplicate DER;
- path replacement after admission; and
- idempotent close with fail-closed reuse.

The local fake server uses real TLS 1.3 with a generated test CA and hostname
certificate. It covers:

- exact response-boundary splitting;
- verified TLS 1.3, no ALPN, exact transcript/certificate evidence;
- a response and Ping coalesced into one server write;
- no Ping visibility or Pong output before the raw record is presented;
- exact masked matching Pong held after parsing;
- two automatic Pongs preserved in order with zero socket output;
- one-shot handshake evidence;
- wrong raw sequence/bytes fault latching;
- exact masked Text subscription framing;
- invalid `Sec-WebSocket-Accept`;
- wrong hostname, untrusted CA, and a TLS-1.2-only peer; and
- cancellation after the request with no resumable state.

Final verification is:

- **24 dedicated V4.9A tests passed**: 13 trust-store and 11 real local
  TLS/WebSocket engine tests;
- **712 broad physical, operational-manifest, artifact, chronyd, transport,
  trust, and engine tests passed**;
- **1,937 repository tests passed with 32 skipped** in 151.23 seconds;
- the full run emitted one Python 3.12 deprecation warning for the pre-existing
  V4.8B multi-threaded `fork()` adversary;
- Ruff lint passed on both new modules and both new test files;
- Ruff format, `py_compile`, and `git diff --check` passed for the V4.9A
  implementation scope.

These are deterministic local correctness results. They are not Internet,
Bybit, certificate-rollover, kernel partial-write, process-crash, privileged
host, or soak evidence.

## 7. Remaining gates and exact next slices

### V4.9B — driver-derived session authority

1. Add a signed nested driver-policy profile without changing the exact
   six-child deployment closure; the runtime-environment manifest should bind
   its identity.
2. Verify the installed Python/OpenSSL/`websockets`/`cryptography` artifact
   roots rather than relying on version declarations.
3. Make `LinuxSocketOwnerV4` require the exact engine while retaining
   `is_live_profile == false` until all of this slice is complete.
4. Add one locked owner handshake that samples the exact V4.8B governed clock
   before and after the driver transition.
5. Add an async live-only runtime method that takes no session object and no
   owner argument, constructs and signs `TransportSessionAttestationV4` from
   the exact driver observation, and reuses the current owner-binding checks.
6. Refactor the projection's large bound-session append into one private core;
   retain public live rejection and admit the internal exact authority path
   only.
7. Fault-inject every session/binding insert and post-commit owner/clock check.

The factory remains closed until this slice cannot accept a caller-authored or
structural-driver fact.

### V4.9C — complete ingress, output, send, and close actor

1. Add durable parser cursors and cross-ingress source spans.
2. Bind projection raw append and parser transition in one non-substitutable
   actor operation.
3. Add an ordered automatic-output obligation/batch contract.
4. Move subscription and application heartbeat frames to the same exact
   prepared-wire, durable-permit, dispatch-result chain.
5. Replace opaque `sock_sendall()` evidence with explicit positive partial-send
   accounting.
6. Add WebSocket Close, TLS `close_notify`, clean/unclean EOF, truncation,
   timeout, and TCP terminal evidence as distinct states.
7. Inject cancellation, storage failure, crash, fork, thread/loop migration,
   and descriptor replacement at every boundary.

Only after V4.9B/C, measured deployment artifacts, privileged V4.8B tests, and
complete local fault campaigns should the factory gate be reconsidered.

### Provider and operational campaigns

The later order remains:

```text
complete local V4.9B/C
-> disposable privileged host integration
-> read-only testnet conformance
-> separately approved credential-free mainnet public-data conformance
-> drift/rollover policy
-> crash/restart campaigns
-> long no-trading soaks
-> independent review
```

No order route or trading activation is part of these transport slices.

## 8. Primary-source basis and limitations

- Python's [`ssl` Memory BIO support](https://docs.python.org/3.12/library/ssl.html#memory-bio-support)
  defines `SSLObject` as TLS over incoming/outgoing memory buffers, leaving
  network I/O to the integration. The same documentation defines
  `CERT_REQUIRED`, hostname checking, version bounds, trust loading, clean
  `SSLZeroReturnError`, and abrupt `SSLEOFError`. Platform/OpenSSL variation
  remains possible.
- [`websockets` 16 Sans-I/O integration](https://websockets.readthedocs.io/en/16.0/howto/sansio.html)
  makes the integration call `receive_data()`, drain `data_to_send()`, and
  process `events_received()`. It automatically responds to Ping and Close,
  but it provides no repository-specific durability or authorization.
- [`websockets` 16 client API](https://websockets.readthedocs.io/en/16.0/reference/sansio/client.html)
  supplies the opening request/response state machine and exact frame
  serializer/parser used here. Version 16.0 remains pinned because existing
  evidence contracts depend on its behavior.
- [RFC 6455](https://www.rfc-editor.org/info/rfc6455/) requires client masking,
  unmasked server frames, matching Pong behavior, Close response behavior,
  and no data frames after sending Close. It doesn't define the repository's
  journal, deadlines, delivery claims, or crash semantics.
- [RFC 9846](https://www.rfc-editor.org/info/rfc9846/) is the current TLS 1.3
  specification and obsoletes RFC 8446. It defines TLS mechanisms, not the
  application's hostname, PKI, persistence, or trading-authority policy.

## 9. Explicit nonclaims

V4.9A does not establish:

- a live or provider-authoritative collector;
- complete certificate-chain, revocation, CT, or provider-ownership evidence;
- DNS, route, proxy-bypass, remote-IP ownership, kernel-read, TLS-record, or
  peer-message provenance;
- exact kernel partial-send counts or peer receipt;
- crash-safe ordered multi-control delivery;
- a clean WebSocket/TLS/TCP shutdown lifecycle;
- provider compatibility, certificate-rollover safety, or future behavior;
- data correctness, completed-bar availability, predictive signal, order
  correctness, trading safety, or profitability.

The value of V4.9A is narrower and necessary: it replaces a hypothetical
driver with a concrete, testable protocol engine while preserving the deny
gate that prevents incomplete local correctness from becoming market-data or
trading authority.
