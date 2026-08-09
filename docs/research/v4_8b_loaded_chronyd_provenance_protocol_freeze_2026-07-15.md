# V4.8B prospective loaded-chronyd provenance protocol freeze

Date: 2026-07-15

Status: implemented and locally verified as a prospective, fail-closed
authority; not deployed, integration-certified, or promotion-ready

Roadmap position: Stage 1 critical corrections, after the V4.8A governed
projection clock and before the V4.9 exact TLS 1.3/WebSocket Sans-I/O driver

## 1. Outcome

V4.8B replaces retrospective trust in an unrelated distribution `chronyd`
with a dedicated launch capability. The capability is prepared from retained,
hash-pinned inputs, admits only a finite static configuration, passes those
exact bytes to the retained `chronyd` executable through a sealed `memfd`, and
binds later clock samples to one retained process, pidfd, command-socket inode,
runtime topology, launch identity, and authenticated read-only protocol
transcript.

The distribution daemon is deliberately not attachable. This is a prospective
design: the reviewed supervisor must own the exact launch from preparation to
teardown. A path hash taken after an arbitrary daemon started is not treated as
evidence of what that daemon parsed or retained.

V4.8B also carries the pair
`(chronyd_launch_id, chronyd_runtime_observation_sha256)` through clock
evidence, the retained Linux owner, the operational runtime, the governed
projection, control mediation, and session-commit admission. A missing or
changed pair fails closed in the live profile.

This result is intentionally narrower than “the host time service is trusted.”
It does not attest systemd's complete in-memory effective unit, prove that no
other privileged process can discipline the kernel clock, implement the
reserved durable read-only supervisor API, establish a real provider
connection, or demonstrate predictive edge, trading safety, or profitability.

## 2. Why a prospective launch is required

The V4.7B clock adapter pinned `chronyc`, the configuration files, configured
source artifacts, Linux namespaces, and causal `CLOCK_BOOTTIME` brackets.
V4.8A then made that clock authority the only source of durable operational
timestamps. Neither slice could establish which executable and configuration
an already-running daemon actually loaded.

The alternatives were evaluated against that gap:

| Alternative | Decision | Reason |
|---|---|---|
| Attach to the distribution daemon and hash current paths | Rejected | Path bytes can be replaced after `exec`, includes can change, the launcher can inject different arguments or environment, and the querying process does not own the daemon lifecycle. |
| Read `/proc/<pid>/cmdline` and `/proc/<pid>/exe` after startup | Insufficient alone | These observations improve process identity but do not prove the complete parsed configuration or retain the exact input descriptors. |
| Allow `include`, `confdir`, `sourcedir`, DNS names, pools, or refclocks | Rejected for this profile | They introduce configuration or resolution state outside the sealed byte closure and require separate causal provenance. |
| Copy approved files to a temporary path before launch | Rejected | A mutable pathname reintroduces replacement and namespace ambiguity between validation and parsing. |
| Assemble one static configuration, seal it, validate the pinned parser's output, then launch the same retained executable and config descriptors | Selected | The supervisor retains the artifacts and gives the child only the exact executable/configuration instances it validated. |

The resulting order is:

```text
V4.7B pinned clock/socket authority
  -> V4.8A governed projection-clock binding
  -> V4.8B prospective loaded-chronyd authority
  -> V4.9 exact TLS 1.3 + WebSocket Sans-I/O driver
  -> provider conformance, crash campaigns, and no-trading soaks
```

## 3. Signed closure and preparation

### 3.1 Nested launch policy

`ClockSourcePolicyManifestV4` now contains an exact
`ChronydLaunchPolicyV48B`. Its identity commits to:

- the reviewed launch, supervisor, and command-proxy profiles;
- systemd unit name, path, and file digest;
- `chronyd` executable path and digest;
- assembled and `chronyd -p` printed configuration digests;
- the fixed child-environment digest;
- distinct root, daemon, and supervisor runtime directories;
- real command, lifecycle-notify, and reserved read-only API socket paths;
- the dedicated post-drop account name, UID, GID, and LSM profile;
- readiness and maximum-datagram bounds.

The operational deployment remains the existing exact six-child manifest
graph. Nesting the launch policy in its clock child means a deployment that
changes any launch property necessarily changes the clock manifest and the
approved deployment closure.

### 3.2 Static configuration profile

Preparation opens and retains the signed unit, `chronyd`, base configuration,
and source-fragment artifacts. Inputs must be bounded, strict ASCII,
NUL-free, LF-terminated bytes with normalized unique absolute paths. Fragment
order is canonical by path.

Only the reviewed finite directive set is accepted. The profile requires
exact singleton values for:

```text
bindcmdaddress <signed real command socket>
cmdport 0
driftfile /
minsources <signed minimum>
pidfile /
port 0
```

Every `server` or `peer` endpoint must be a canonical literal IPv4 or IPv6
address. Endpoint names must be unique and the total source count is bounded
to 64. Dynamic or externally resolved state, including `include`, `confdir`,
`sourcedir`, `pool`, `refclock`, DNS endpoint names, NTS key/certificate
options, and local/manual service modes, is rejected rather than approximated.

The assembled bytes include input digests, are checked against the signed
effective digest, and are written to a `memfd` carrying all four required
seals: write, grow, shrink, and further-seal prevention. Preparation invokes
the retained executable by `/proc/self/fd/<fd>` for exact version `4.8` and
for `-p -f /proc/self/fd/<sealed-config-fd>`. The bounded printed output must
match the independently signed printed-configuration digest.

The public production preparation path has no injectable command runner. A
private deterministic test path creates an explicitly non-live capability,
which the live launch boundary refuses.

## 4. Supervised lifecycle and retained authority

### 4.1 Pre-launch admission

The exact launch requires:

- root supervisor credentials;
- a valid systemd `INVOCATION_ID` that matches the named unit invocation link;
- supervisor membership in a cgroup path containing the signed unit name;
- the signed post-drop account mapping;
- no existing process with the dedicated effective UID;
- fresh socket paths;
- three retained, non-symlink runtime directories with exact ownership, mode,
  device, and inode identity.

The runtime topology separates the daemon-created command socket from
supervisor-owned sockets:

```text
root-owned runtime directory (0711)
├── daemon socket directory (post-drop UID/GID, 0700 before launch)
│   └── real chronyd command socket
└── supervisor socket directory (root:post-drop GID, 0710)
    ├── lifecycle-notify socket
    ├── reserved read-only API pathname (not served in V4.8B)
    └── one fresh private proxy directory per internal query
```

The child is launched only from the retained executable and sealed-config
descriptors with exact reviewed arguments and environment. The supervisor
immediately opens and retains a pidfd.

### 4.2 Lifecycle readiness is not source readiness

The private notify socket enables `SO_PASSCRED`. Launch admission accepts one
complete datagram only when kernel-provided credentials equal the child PID
and signed post-drop UID/GID and the payload is exactly `READY=1`. Extra queued
datagrams are rejected.

`READY=1` proves only that the admitted child reached its lifecycle-ready
point. It is not reinterpreted as synchronization, upstream-source, or UTC
truth evidence. Initial source loading is checked separately by the bounded
read-only query state machine. Only a temporarily smaller source count is
retryable, within one `CLOCK_BOOTTIME` deadline; excess sources, malformed
traffic, process changes, and all other protocol failures are fatal and
fault-latch the authority.

### 4.3 Process and command-socket identity

After lifecycle readiness, the supervisor binds:

- PID plus retained pidfd and `/proc/<pid>/stat` start ticks;
- direct parent PID;
- retained executable device/inode;
- real/effective/saved/filesystem UID and GID agreement;
- no supplementary groups;
- exact permitted, effective, and bounding capabilities for
  `CAP_NET_BIND_SERVICE | CAP_SYS_TIME`, with inheritable and ambient sets
  empty;
- `NoNewPrivs=1`, seccomp filter mode with at least one filter, and
  `CoreDumping=0`;
- a non-group/world-writable umask;
- kernel boot ID, cgroup record digest, signed LSM profile, and mount, network,
  PID, time, and user namespace identities;
- exclusive use of the dedicated effective UID within the visible `/proc`
  namespace.

The daemon initially creates its command socket as the post-drop UID/GID with
mode `0660`. The supervisor freezes its directory, verifies the socket inode,
changes directory ownership to root and mode to `0700`, takes root ownership
of the same socket inode, changes it to `0600`, and revalidates both retained
and pathname identities. This prevents new pathname clients in the ordinary
DAC model and prevents the daemon from replacing the socket after admission.

The launch identity commits to the boot, invocation, executable/configuration
digests, PID, and start ticks. The runtime-observation digest additionally
commits to the process-security, cgroup, namespace, runtime-directory, LSM,
and sealed command-socket observations. Each authority check revalidates the
retained process, pidfd, socket, preparation artifacts, systemd invocation,
dedicated UID, directories, and complete process snapshot. A mismatch
fault-latches the capability.

Teardown signals the owned daemon through the retained pidfd, unlinks only
the exact retained socket inodes, restores the controlled daemon directory for
a future supervised launch, and closes retained descriptors. A forked child
may close its inherited Python objects but cannot signal or unlink the parent
daemon.

## 5. Frozen read-only Chrony protocol

The production query invokes the separately retained, signed `chronyc 4.8`
artifact with exact non-resolving, CSV, dot-terminated response settings and
zero retries. A fresh pathname is allocated under the sealed supervisor directory
for every query. The internal proxy owns two `AF_UNIX/SOCK_DGRAM` sockets and
requires exactly one `SCM_CREDENTIALS` record on every datagram:

- downstream request credentials must equal the exact spawned `chronyc`
  PID and supervisor UID/GID;
- upstream reply credentials must equal the retained daemon PID and signed
  post-drop UID/GID.

`SO_PEERCRED` is not substituted for per-message credentials on pathname
datagram sockets.

The admitted Chrony command protocol is version 6 only:

| Phase | Request command | Reply type | Exact datagram bytes | Cardinality |
|---|---:|---:|---:|---:|
| Tracking | 33 | 5 | 104 | 1 |
| Number of sources | 14 | 2 | 32 | 1 |
| Source data | 15 | 3 | 76 | exactly one for each index `0..N-1` |

The complete exchange therefore contains exactly `N + 2` request/reply
cycles, bounded to 66 cycles for 64 configured sources. Every packet must have
the frozen header, length, command/reply type, successful status, sequence,
index, and zero-padding shape. The runtime source count must equal the sealed
static endpoint count. The transcript digest commits to every request and
reply digest, sequence, order, and source count.

One shared `CLOCK_BOOTTIME` deadline bounds the child process, proxy relay,
datagram receives and sends, output collection, and thread completion. Stdout
and stderr are incrementally bounded; there is no later unbounded
`communicate()` fallback. Queries are serialized per authority, and a failure
fault-latches it.

The authenticated query supplies `chronyc` CSV bytes only after the state
machine, credentials, retained provenance, source count, process exit, bounded
output, and artifact revalidation all succeed. The existing strict V4.7B
tracking/source parser then applies synchronization, normal-leap, source,
freshness, finite-value, uncertainty, configured-endpoint, and
wall/`CLOCK_BOOTTIME` policies.

## 6. End-to-end identity propagation

`LinuxChronyClockSourceV4` requires the exact live
`ChronydLaunchAuthorityV48B`. Each accepted sample contains:

```text
chronyd_launch_id
chronyd_runtime_observation_sha256
query_observation_sha256
```

The first two fields are retained by `ClockEvidenceV4` and
`TransportSocketOwnerSnapshotV4`. Live admission requires both or neither at
the general data-contract level, and requires both in the live profile.
Continuity checks reject a pair that changes across:

- repeated runtime clock samples;
- governed projection mutations;
- control-runtime sampling against the exact retained owner snapshot;
- owner-level currentness checks.

The session-commit path contains the same owner/pair comparison, but current
live admission intentionally stops at the V4.9 exact-driver gate before it can
consume a caller-supplied session or owner snapshot. V4.8B tests therefore
prove that the gate aborts before pair consumption; a stable live commit cannot
be accepted until V4.9 supplies driver-derived session evidence.

The query-observation digest remains sample-specific and is incorporated in
the clock observation evidence; it is not treated as the stable launch
identity.

The sealed Linux live factory still stops at the V4.9 driver gate before
preparing artifacts, launching `chronyd`, constructing a clock, or transferring
a socket. V4.8B therefore does not silently activate a partial live stack.

## 7. Implementation map

| Concern | Implementation |
|---|---|
| Signed nested launch policy and six-child closure | `riskyieldmm/trading/operational_manifests_v4.py` |
| Static configuration, sealed preparation, launch, process/socket authority, and authenticated protocol | `riskyieldmm/trading/chronyd_provenance_v48b.py` |
| Strict clock parsing, authority binding, evidence production, and V4.9 deny gate | `riskyieldmm/trading/physical_transport_linux_v4.py` |
| Clock evidence and runtime continuity | `riskyieldmm/trading/physical_transport_runtime_v4.py` |
| Owner snapshot continuity | `riskyieldmm/trading/physical_transport_owner_v4.py` |
| Projection continuity | `riskyieldmm/trading/physical_projection_v4.py` |
| Control-runtime owner matching | `riskyieldmm/trading/physical_transport_control_runtime_v4.py` |
| Manifest, protocol, lifecycle, propagation, and factory adversaries | `tests/test_trading_operational_manifests_v4.py`, `tests/test_trading_chronyd_provenance_v48b.py`, and the physical transport/projection/control suites |

## 8. Threat model and explicit nonclaims

V4.8B assumes a trusted Linux kernel, trusted systemd/supervisor process, an
uncompromised retained `chronyd`/`chronyc`, and correct signed policy inputs.
Within that boundary it is designed to detect configuration ambiguity,
artifact replacement, PID reuse, process/socket/runtime-topology changes,
protocol substitution, credential mismatch, source-set mismatch, query
concurrency, timeouts, fork misuse, and partial cleanup.

The following remain explicit nonclaims and Stage 1 gates:

1. **Complete effective systemd state is not attested.** The signed unit file,
   invocation identity, and cgroup membership are bound, but manager-loaded
   fragment identity, drop-ins, transient properties, expanded `ExecStart`,
   environment, capability directives, namespaces, sandboxing, and `KillMode`
   are not read back and committed from systemd's in-memory effective state.

2. **DAC sealing cannot revoke a client that connected before the seal.** A
   same-UID datagram client with a pre-existing connection can retain it.
   Requiring an otherwise unused dedicated UID and checking the visible
   `/proc` set materially narrows this risk, but does not prove peer
   exclusivity across hidden PID namespaces or replace an enforced LSM peer
   policy.

3. **Exclusive host clock discipline is not proven.** An authenticated reply
   from the retained daemon does not establish that another service or process
   with `CAP_SYS_TIME` is absent or unable to modify `CLOCK_REALTIME`.

4. **The signed durable read-only API path is reserved but unserved.** V4.8B
   uses one private in-process credential proxy per query. It does not expose
   a reusable external supervisor API or authorize another process to query
   through that reserved pathname.

5. **No real privileged deployment has been certified.** Unit tests use
   deterministic process/socket/protocol seams. A disposable systemd host or
   pinned VM/container must still run the exact root launch, READY lifecycle,
   socket seal, real `chronyd 4.8` protocol, query, fault, teardown, and restart
   campaigns.

6. **UTC truth and upstream-source honesty are not proven.** Chrony state is
   evidence about the retained local daemon's observations and calculations,
   not remote attestation of upstream clocks.

7. **No transport, trading, or alpha claim follows.** V4.8B does not implement
   TLS/WebSocket framing, provider conformance, completed-bar correctness,
   execution, fills, strategy evaluation, predictive edge, safety, or
   profitability.

## 9. Verification and falsification

The focused V4.8B tests cover:

- exact manifest round-trip, path topology, fixed profile, timeout, datagram,
  and Unix-socket headroom bounds;
- configuration order, digest, endpoint count, duplicate, dynamic directive,
  external-state, encoding, newline, line-size, and total-size adversaries;
- complete `memfd` seals and post-seal mutation failure;
- retained artifact replacement and preparation cleanup;
- exact version and printed-config output admission;
- protocol versions, types, commands, status, sizes, sequences, source indices,
  padding, counts, truncation, extra data, and 1/64-source boundaries;
- per-datagram credential presence and PID/UID/GID equality;
- one shared deadline, bounded output, zero retries, relay termination, and
  query cleanup/fault-latching;
- pidfd-only owned-process signaling and fork-safe teardown;
- process start, parent, executable, UID/GID, supplementary group,
  capabilities, `NoNewPrivs`, seccomp, coredump, LSM, cgroup, namespace, and
  dedicated-UID adversaries;
- runtime-directory and command-socket owner/mode/inode sealing and
  replacement attacks;
- rejection of unsigned `chronyc`, non-production preparation, and the
  pre-V4.9 live factory before launch side effects;
- stable launch/runtime pair acceptance and changed or missing pair rejection
  at the live runtime, owner, projection, and control boundaries, plus
  commit-session rejection at the earlier V4.9 driver gate before pair
  consumption.

These are local falsification tests, not privileged integration evidence.
Final verification on 2026-07-15 is:

- **46 dedicated chronyd-provenance tests passed**;
- **10 pair-focused tests passed**, including one pre-existing pair-constructor
  contract and nine new runtime/projection/control/commit-gate cases;
- **308 adjacent operational-manifest, provenance, Linux clock/owner,
  runtime, projection, control, and sealing tests passed**;
- **1,913 repository tests passed with 32 skipped**;
- Ruff lint passed across `riskyieldmm/trading` and every trading test; Ruff
  format passed for all 19 V4.8B-touched implementation/test files;
- `py_compile` passed for the six affected implementation modules.

The repository-wide Ruff format command is not a clean baseline: it rejects a
pre-existing notebook schema and reports 246 older files outside this slice as
not formatted. V4.8B did not rewrite those user-owned areas. This limitation
is recorded rather than hidden or fixed by an unrelated bulk rewrite.

## 10. Primary-source basis

The static parser and lifecycle constraints are grounded in the official
Chrony 4.8 documentation for
[`chronyd`](https://chrony-project.org/doc/4.8/chronyd.html),
[`chrony.conf`](https://chrony-project.org/doc/4.8/chrony.conf.html), and
[`chronyc`](https://chrony-project.org/doc/4.8/chronyc.html). Exact command and
wire constants were cross-checked against the tagged Chrony 4.8 source,
including
[`client.c`](https://gitlab.com/chrony/chrony/-/blob/4.8/client.c),
[`cmdmon.c`](https://gitlab.com/chrony/chrony/-/blob/4.8/cmdmon.c), and
[`candm.h`](https://gitlab.com/chrony/chrony/-/blob/4.8/candm.h). The source
justifies the frozen implementation-specific protocol for this exact version;
it is not a promise that future Chrony releases preserve it.

The Linux mechanisms and their limits follow the primary Linux manual pages
for [`memfd_create(2)`](https://man7.org/linux/man-pages/man2/memfd_create.2.html),
[`pidfd_open(2)`](https://man7.org/linux/man-pages/man2/pidfd_open.2.html),
[`unix(7)`](https://man7.org/linux/man-pages/man7/unix.7.html),
[`proc_pid_status(5)`](https://man7.org/linux/man-pages/man5/proc_pid_status.5.html),
and [`capabilities(7)`](https://man7.org/linux/man-pages/man7/capabilities.7.html).
In particular, `SCM_CREDENTIALS` is per-message ancillary evidence and Unix
pathname permissions do not retroactively revoke already-connected peers.

The lifecycle distinction follows systemd's official
[`sd_notify(3)`](https://www.freedesktop.org/software/systemd/man/latest/sd_notify.html)
semantics: `READY=1` communicates service startup completion, not application-
specific time-source synchronization. Effective-manager-state attestation is
deferred because the current code does not yet bind the properties exposed by
systemd's official
[`org.freedesktop.systemd1`](https://www.freedesktop.org/software/systemd/man/latest/org.freedesktop.systemd1.html)
interface.

These sources support mechanism selection and protocol interpretation. They
do not demonstrate market predictability or profitable trading.

## 11. Diagnostic-host result and remaining gates

The current workstation's distribution `chronyd` remains outside the admitted
profile. It uses distribution-owned launch/configuration conventions and an
existing service account rather than this dedicated signed static closure.
No host time service was stopped, restarted, reconfigured, or otherwise
mutated while implementing V4.8B.

Before V4.8B can become deployment evidence, Stage 1 still requires:

- read-back and commitment of systemd's effective loaded unit/drop-ins and
  security properties;
- a defensible exclusive clock-disciplinarian policy and coexistence tests;
- an LSM or equivalent peer-containment design for the command endpoint, or a
  redesign that removes the preconnected-client ambiguity;
- implementation or removal/renaming of the reserved durable supervisor API;
- real `chronyd 4.8` interoperability plus disposable-systemd/root and pinned
  VM/container launch, replacement, crash, restart, and cleanup campaigns;
- the V4.9 exact TLS 1.3/WebSocket Sans-I/O driver and driver-derived session
  evidence;
- provider conformance, drift monitoring, crash campaigns, and long
  no-trading soaks.

Independent-label, interval-aware split, feature-availability, execution, and
model-baseline gates elsewhere in Stage 1 remain unchanged. No model training
or profitability optimization should use V4.8B's local correctness result as a
substitute for those controls.
