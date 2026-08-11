# V4.7 eager socket-owner and governed-clock protocol freeze

**Date:** 2026-07-15
**Status:** V4.7A and the bounded V4.7B Linux clock/socket authority slice are
implemented and locally verified; provider TLS/Sans-I/O integration, loaded
chronyd provenance, deployment measurement, and live promotion remain P0
**Predecessor:**
[`v4_6_durable_control_mediator_protocol_freeze_2026-07-15.md`](v4_6_durable_control_mediator_protocol_freeze_2026-07-15.md)

## Decision

V4.7 removes the remaining interval in which a signed transport session can
exist without a durable socket-owner and application-writer binding.

```text
connected private socket
-> completed TLS/WebSocket handshake evidence
-> governed clock bracket plus socket-owner snapshot
-> one SQLite transaction:
     signed TransportSessionAttestationV4
     signed TransportSocketOwnerBindingV4
     typed session and binding rows
     one operation batch spanning both receipts
-> revalidate the same live owner
-> subscription/control authority may begin
```

The owner binding is a separate canonical record. It does not change or
re-identify the V4.5 handshake attestation. Every V4.7 subscription intent,
raw ingress record, control intent, prepared wire, consumed permit, dispatch
result, capture continuation, and orphan classification must resolve the one
binding that preceded it.

The implementation is split at a deliberate verification boundary:

- **V4.7A** implements the signed record, atomic projection operation, eager
  replay, and rejection of first-record/lazy binding.
- **V4.7B** supplies the only promotion-eligible Linux adapter for
  `CLOCK_BOOTTIME`, boot/time/network namespace identity, `SO_COOKIE`, and
  strict chrony evidence. Synthetic ports remain useful only for tests.

Freezing both field sets now avoids a second projection-genesis change when the
OS adapter arrives. The two slices remain separate because SQLite invariants
and OS/subprocess/time-discipline failures require different fault campaigns.

## Alternatives considered

| Alternative | Decision |
|---|---|
| Add owner fields to `TransportSessionAttestationV4` | Rejected. It conflates remote-handshake observation with local writer ownership and changes every existing V4.5 session identity. |
| Keep the SQL row derived from the first raw/control record | Rejected. A quiet or crash-interrupted session remains unbound, and the first later record selects its own authority. |
| Append a separate binding after the session transaction | Rejected. A crash can preserve the session while losing the binding. |
| Keep only an in-memory owner capability | Rejected. Restart and canonical replay cannot establish which socket/writer epoch owned the session. |
| Atomically append a separate signed canonical binding with the session | **Selected.** It preserves the handshake identity, closes the crash prefix, and gives canonical replay an independent record. |

## Primary-source constraints

- [SQLite transactions](https://www.sqlite.org/lang_transaction.html) document
  that `BEGIN IMMEDIATE` starts the write transaction immediately. The existing
  single-writer rollback-journal profile is retained.
- [SQLite atomic commit](https://www.sqlite.org/atomiccommit.html) explains the
  filesystem, VFS, flush, and hardware assumptions beneath local crash
  atomicity. The operation cannot make a network side effect transactional.
- [Linux `clock_gettime(2)`](https://man7.org/linux/man-pages/man2/clock_gettime.2.html)
  states that `CLOCK_MONOTONIC` excludes suspend while `CLOCK_BOOTTIME` includes
  it. V4.7 uses BOOTTIME for deadlines and ordering.
- [Linux time namespaces](https://man7.org/linux/man-pages/man7/time_namespaces.7.html)
  virtualize MONOTONIC and BOOTTIME offsets. A kernel boot ID alone is not a
  complete monotonic domain.
- [Linux namespace identity](https://man7.org/linux/man-pages/man7/namespaces.7.html)
  is compared through namespace-file device/inode identity; an open namespace
  descriptor also pins the namespace. The production adapter opens
  `/proc/thread-self/ns/time` and `/proc/thread-self/ns/net`, verifies their
  namespace types with `NS_GET_NSTYPE`, retains the descriptors, and compares
  them with freshly opened current-thread descriptors before use.
- [Linux boot ID](https://www.kernel.org/doc/html/v6.9/admin-guide/sysctl/kernel.html)
  is stable for one running kernel instance. It is scope evidence, not a
  cryptographic machine attestation.
- Linux exposes the socket-lifetime cookie as `SO_COOKIE` in the
  [UAPI socket constants](https://github.com/torvalds/linux/blob/master/include/uapi/asm-generic/socket.h)
  and [kernel socket implementation](https://code.googlesource.com/linux/torvalds/linux/+/21e4675d9305f6ccd20b95d943882d607c8ae288/net/core/sock.c).
  File-descriptor numbers are not identities: [`dup(2)`](https://man7.org/linux/man-pages/man2/dup.2.html)
  shares an open file description and [`close(2)`](https://man7.org/linux/man-pages/man2/close.2.html)
  permits descriptor-number reuse.
- Linux also exposes `SO_NETNS_COOKIE` in the UAPI socket constants. V4.7B
  compares the connected socket's value with a fresh probe in the retained
  current network namespace; this complements, rather than replaces, the
  retained namespace descriptor identity.
- [chronyc 4.8](https://chrony-project.org/doc/4.8/chronyc.html)
  exposes system offset, root delay, root dispersion, leap state, and a
  conservative clock-error bound through machine-readable `tracking` and
  `sources` output. V4.7B uses a single explicit command endpoint and parses
  the exact admitted CSV layouts, rejecting unsynchronized, stale, malformed,
  ambiguous, or policy-excessive observations.

## Frozen identity and clock profiles

```text
clock_profile = LINUX_BOOT_ID_TIME_NAMESPACE_CLOCK_BOOTTIME_V1

monotonic_clock_domain_id = SHA256(canonical({
  profile,
  kernel_boot_id,
  time_namespace_id
}))

socket_identity_profile = LINUX_SO_COOKIE_BOOT_NETNS_V1

kernel_socket_identity = SHA256(canonical({
  profile,
  kernel_boot_id,
  network_namespace_id,
  socket_cookie_u64_hex
}))
```

The 64-bit cookie is represented as exactly 16 lowercase hexadecimal digits,
not an I-JSON number. Namespace IDs commit the namespace-file device/inode
pair. Production keeps close-on-exec time/network namespace descriptors open
for the lifetime of the runtime, fences use to the creating process and
thread, and invalidates inherited authority after `fork()`.

A wall-time read and a BOOTTIME read are not simultaneous. Every governed
sample therefore persists a bracket:

```text
boottime_before_ns
wall time plus discipline observation
boottime_after_ns
```

Event A is strictly earlier than event B only when
`A.boottime_after_ns < B.boottime_before_ns`. Overlap is ambiguous and cannot
authorize a transition. UTC rollback cannot reverse BOOTTIME chronology.

## V4.7A atomic owner-binding invariants

1. A V4.7 transport session and exactly one owner binding are appended in the
   same transaction and operation batch. Neither record may survive alone.
2. The binding canonical receipt immediately follows its session receipt.
3. The binding's exact signed `transport_session_id` transitively commits every
   session field, including collector instance. Directly duplicated deployment,
   policy, scope, adapter, partition, collector key, connection generation,
   clock source, and monotonic-domain fields are exact; binding kernel boot is
   exact with session collector boot.
4. The binding names the active application writer-fence token digest and
   generation observed inside the transaction.
5. Binding wall time is not before handshake completion; the BOOTTIME bracket
   begins strictly after handshake completion and does not regress internally.
6. Deployment validity and uncertainty bounds hold at the binding observation.
7. `socket_lease_id` and kernel socket identity are globally single-use in a
   fresh V4.7 ledger.
8. Subscription authorization and all raw/control paths require the prior
   binding. No heartbeat or raw record may create or alter it.
9. A successor writer fence may terminate/reconcile an old bound session but
   may never adopt it. A successor session requires a new binding.
10. Canonical replay independently reconstructs the binding set and compares it
    bijectively with typed rows. Missing, extra, substituted, reordered, or
    corrupted binding state fails verification.
11. A V4.6 database is archived read-only. V4.7 starts a fresh genesis because
    backfilling would manufacture ownership evidence that was never observed at
    session commit.

## V4.7B concrete evidence requirements

The production adapter must:

- use fixed, reviewed executable/config paths, fixed argv, no shell, bounded
  output, strict UTF-8, bounded runtime, and fail-closed chrony parsing;
- verify the executable, configuration, and configured-source artifacts named
  by the signed clock manifest;
- read boot ID before and after evidence collection and reject a mismatch;
- derive the domain from boot plus the pinned time namespace;
- use `CLOCK_BOOTTIME` and persist the full sample bracket/resolution;
- reject abnormal leap state, unsynchronized state, insufficient selectable
  sources, stale samples, non-finite values, and uncertainty above policy;
- obtain and re-read `SO_COOKIE` and `SO_NETNS_COOKIE` on the same private
  close-on-exec socket;
- bind cookie identity to boot plus the pinned network namespace and reject a
  mismatch with the current-network-namespace probe; and
- feed the same governed evidence type to both the subscription runtime and
  the durable control mediator.

There is no silent portable fallback. A platform without the frozen Linux
capabilities has no live transport authority.

## Acceptance tests

### V4.7A

- signed contract round-trip and mutation rejection;
- session-plus-binding append/replay with exactly two adjacent receipts;
- fault injection after each canonical insert, typed insert, batch insert, and
  before commit, proving zero partial session/binding state;
- idempotency conflict on socket, fence, generation, namespace, clock, or
  bracket substitution;
- global socket reuse rejection before a second session becomes durable;
- raw ingress, heartbeat, and subscription authorization rejected when the
  eager binding is absent or mismatched;
- first raw/control records cannot create or change a binding;
- writer-fence replacement cannot adopt or append through the old binding;
- quiet-session orphan classification returns its already durable owner;
- startup reconciliation terminates old authority and requires a fresh owner;
- deletion, typed/canonical corruption, receipt reordering, and cross-session
  substitution fail full replay; and
- existing stale-callback, permit, cancellation, restart, and full physical
  suites remain green.

### V4.7B

- deterministic domain/socket derivation and change on boot/namespace/cookie;
- boot mismatch, time/network namespace change, cookie change/zero/malformed
  value, descriptor reuse, and inherited/forked misuse fail closed;
- malformed/truncated/oversized/non-finite chrony output, timeout, nonzero exit,
  wrong artifact hashes, abnormal leap, stale source, insufficient sources, and
  excessive uncertainty fail closed;
- suspend-like BOOTTIME advancement expires authority; wall rollback does not
  reverse ordering; overlapping brackets cannot prove order;
- mid-runtime boot/domain/source-policy change latches authority before a permit
  or writer invocation; and
- real-host probes remain optional diagnostics and never substitute for signed
  deployment-artifact acceptance.

## V4.7A implementation result

The accepted local slice now consists of:

- `physical_transport_owner_v4.py`: strict signed owner-binding contracts,
  deterministic BOOTTIME-domain/kernel-socket/lease derivation, and the
  noncanonical live owner snapshot;
- `physical_projection_v4.py`: a fresh V4.7 schema, one atomic
  `APPEND_BOUND_TRANSPORT_SESSION_V4_7` operation, adjacent canonical receipts,
  typed owner projection, writer-fence validation, single-use lease/kernel
  identity, full canonical replay, and typed/canonical bijection;
- `physical_transport_runtime_v4.py`: caller-selected socket strings removed
  from session commit, runtime-generated lease capability entropy, pre/post
  commit owner revalidation, retained exact owner-as-writer identity, and
  fail-closed owner abort plus fence cleanup; and
- adversarial contract, transaction-fault, tamper, lazy-bypass, runtime owner
  loss, alternate-writer, reconnect, and real SQLite/lease integration tests.

Measured local verification on 2026-07-15:

- 27 owner contract tests passed;
- 14 dedicated owner-projection tests passed;
- 58 subscription-runtime unit tests passed;
- 4 real projection/OS-lease runtime integration tests passed; and
- 510 combined physical, operational-manifest, and transport-key tests passed;
  the full repository then passed 1,735 tests with 32 skipped.

The generic `ClockEvidenceV4` test port can still supply a point sample; V4.7A
records that point as a zero-width test bracket. Production construction does
not accept that seam: the V4.7B factory creates the Linux owner and clock as
one authority and requires nonzero real BOOTTIME evidence before it can derive
the durable control mediator.

## V4.7B implementation result

The bounded concrete slice now adds:

- `operational_artifact_loading_v4.py`: retained, no-follow, close-on-exec
  regular-file pins for the chronyc executable, chrony configuration, and
  configured-source artifacts, with exact type/mode/size/digest checks and
  replacement or in-place mutation detection;
- `operational_manifests_v4.py`: a fresh V4.7 manifest schema that signs the
  chronyc executable/configuration paths, one explicit command endpoint,
  external command deadline, and output cap;
- `physical_transport_linux_v4.py`: a shell-free, process-group-bounded
  command runner; strict chronyc 4.8 CSV tracking/source parsing; real
  BOOTTIME/wall brackets and resolution; boot, time-namespace, network-
  namespace, process, thread, and fork fencing; `SO_COOKIE` plus
  `SO_NETNS_COOKIE` socket identity; a sealed live factory that constructs its
  own real clock and owner while rejecting deterministic seams; and one shared
  asynchronous send lock for subscription and control frames; and
- `physical_transport_runtime_v4.py` plus
  `physical_transport_control_runtime_v4.py`: uncertainty-adjusted wall and
  BOOTTIME permit deadlines, bracket ordering, exact bound-owner control
  construction, owner abort on a bound control fault, and a final owner/fence/
  clock/deadline guard inside the shared I/O lock immediately before each
  driver invocation. Bound control construction additionally derives its
  signer and writer-fence authority from the committed binding and rejects
  cross-session/deployment/fence/domain wire substitution before permit use.

The chrony error admission bound is:

```text
abs(system_time_offset)
+ root_dispersion
+ 0.5 * root_delay
+ BOOTTIME/wall observation bracket width
+ clock resolution
```

The adapter requires exactly one selected `*` source, a matching configured
source name, policy-sufficient selectable sources, acceptable source age,
normal leap state, finite nonnegative values, and a bound below the signed
policy ceiling. Its external timeout is deliberately longer than chronyc's
internal request timeout so process teardown remains bounded.

Focused local verification on 2026-07-15 passed 198 tests covering the legacy
V4.7 authority, artifact pins, adversarial chrony output and runner behavior,
real Linux clock/namespace/cookie probes, one-owner send serialization,
process/thread/fork misuse, sealed-construction bypasses, queued-send deadline
and fence supersession, wrong-signer/cross-binding attacks, child-process
cleanup, and bound control construction. The combined
physical/operational-manifest/artifact/key surface passed 584 tests, and the
full repository passed 1,809 tests with 32 skipped.

The diagnostic host has Linux BOOTTIME and the required socket/namespace
capabilities, and its `chronyc` reports version 4.8. The invoking desktop user
cannot access the configured chronyd command socket. That host therefore fails
the strict production profile closed; localhost fallback output is diagnostic
only and does not authorize promotion.

This is still a bounded authority slice. A production TLS/pinned-Sans-I/O
driver must implement the exact driver protocol, and projection runtime clock
use must be bound before any live provider promotion. No real provider
connection is authorized by this local result.

## Explicit nonclaims

V4.7 can establish a canonical binding between one observed kernel socket
identity, one cooperating application writer fence, one session, and one
clock/namespace domain. It does **not** prove:

- that no duplicated descriptor exists in another process;
- physical-host identity or integrity of a compromised kernel/chronyd/VM;
- which configuration and executable the already-running chronyd process
  actually loaded, including launcher, dynamic source-directory, and
  authenticated status provenance;
- true UTC accuracy beyond the admitted discipline evidence and error bound;
- peer receipt, provider processing, exactly-once network delivery, or fills;
- provider conformance, order safety, trading edge, or profitability.

The exact claim is one cooperating application writer behind the current
fence—not absolute OS-level uniqueness.
