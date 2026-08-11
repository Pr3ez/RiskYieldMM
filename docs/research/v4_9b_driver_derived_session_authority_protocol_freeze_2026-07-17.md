# V4.9B measured-driver and driver-derived session-authority freeze

**Date:** 2026-07-17

**Status:** bounded local measured-driver and initial-session authority
implemented; public live construction remains deny-gated

**Roadmap position:** Stage 1 critical corrections, after the V4.9A exact local
TLS/WebSocket engine and before the V4.9C ingress/output/send/close actor

## 1. Decision

V4.9B closes one specific V4.9A authority gap: a caller can no longer describe
the live TLS/WebSocket handshake and ask the runtime to treat that description
as transport authority. The admitted deployment now signs an exact driver-file
policy; the retained Linux owner brackets the real driver transition; the
runtime alone constructs and signs the initial session; and the projection
atomically persists that session with its exact socket-owner binding.

The existing deployment closure remains exactly six child manifests. The full
`TlsWebSocketDriverPolicyV49B` is nested inside the signed
`RuntimeEnvironmentManifestV4`, so its member-by-member identity changes the
runtime-environment manifest ID and is transitively covered by deployment
approval. A pre-V4.9 compatibility manifest may omit the nested policy, but the
V4.9B runtime explicitly requires its policy ID and fails closed when it is
absent.

```text
six-child signed deployment closure
  -> RuntimeEnvironmentManifestV4
       -> exact nested TlsWebSocketDriverPolicyV49B
            -> seven role-exact runtime members
            -> three associated Python bytecode-cache members
            -> every recorded websockets distribution file
            -> every recorded cryptography distribution file
  -> retained, revalidated file descriptors and loaded-origin observation
  -> exact measured V4.9A driver
  -> exact retained Linux socket/clock/driver owner
  -> governed pre-sample + owner snapshot
  -> actual TLS/WebSocket handshake under the owner's I/O lock
  -> governed post-sample + unchanged owner snapshot
  -> runtime-only TransportSessionAttestationV4 construction
  -> one SQLite transaction: signed session + signed socket-owner binding
  -> post-commit owner/lease/fence/clock revalidation
  -> exact retained driver-evidence bind
  -> and only then SESSION_COMMITTED send authority
```

The public live factory remains closed. V4.9B establishes the bounded internal
authority path and its fail-stop rules; it does not activate an incomplete
collector before V4.9C and the remaining deployment campaigns.

## 2. Selected and rejected designs

| Candidate | Assessment | Decision |
|---|---|---|
| Add a seventh top-level deployment child | Would version and widen the already frozen six-role deployment graph for a policy that is part of the runtime environment | Rejected; retain six children and sign the complete policy inside the runtime-environment child |
| Sign only package names and versions | Establishes declarations, not the bytes actually importable or mapped in the admitted process | Rejected |
| Trust wheel `RECORD` hashes or one metadata-derived aggregate | `RECORD` hashes and sizes may be empty, metadata may be absent, and installation metadata is discovery input rather than an independent runtime measurement | Rejected as authority |
| Sign an exact member policy and remeasure every member | Binds paths, sizes, digests, executable requirement, import origins, and the loaded OpenSSL objects to one reviewed deployment | **Selected for this bounded driver closure** |
| Let a caller create a signed-looking session from copied evidence | Leaves timestamps, generation, parent, nonce, endpoint, certificate, and transcript facts substitutable outside the exact owner transition | Rejected for live authority |
| Make the network handshake and database one transaction | A remote network transition cannot be rolled back atomically with local SQLite state | Rejected as an impossible guarantee |
| Persist the durable pair, then fail-stop until exact post-commit bind succeeds | Preserves durable evidence without converting a failed revalidation into send authority | **Selected** |

This is the strongest fit for the existing V4.5 deployment graph, V4.7 eager
owner record, V4.8 governed clock, and V4.9A engine. It is not a claim that a
Python-process file closure is equivalent to host or in-memory attestation.

## 3. Signed measured-driver policy

### 3.1 Exact seven primary roles plus three bytecode caches

The policy contains exactly one member for each of these roles:

1. `PYTHON_EXECUTABLE`
2. `PYTHON_SSL_EXTENSION`
3. `PYTHON_STDLIB_SSL`
4. `OPENSSL_LIBCRYPTO`
5. `OPENSSL_LIBSSL`
6. `RISKYIELDMM_TLS_DRIVER`
7. `RISKYIELDMM_TLS_TRUST_STORE`

It also contains an exact, separately named bytecode-cache member for each
source-backed Python role that may execute from a cache in this boundary:

1. `PYTHON_STDLIB_SSL_BYTECODE_CACHE`
2. `RISKYIELDMM_TLS_DRIVER_BYTECODE_CACHE`
3. `RISKYIELDMM_TLS_TRUST_STORE_BYTECODE_CACHE`

For each of those modules, the imported `__cached__` path must equal
`importlib.util.cache_from_source(__spec__.origin)`. The cache is then signed,
opened, retained, rehashed, and path-revalidated in the same way as the seven
primary members. This is required because `-B` prevents Python from writing
bytecode but does not prevent it from loading an existing valid `.pyc` file.

Each member signs its normalized absolute path, byte size, SHA-256 digest, and
whether execution permission is required. The Python executable must require
execute access. The policy also binds the exact Python implementation and
version, OpenSSL version, driver profile, and two complete installed-file
closures: `websockets` and `cryptography`. Each distribution closure signs its
normalized name, version, installation origin, actual top-level module origin,
and every file returned by its installation database, sorted by absolute path.
The actual module origin must itself be one of those signed members.

`importlib.metadata` is used only to enumerate the installed distributions and
their file lists. V4.9B rejects a distribution whose file list is unavailable,
then opens and SHA-256 hashes each listed file itself. It does not accept the
metadata's optional hash or size as runtime integrity evidence. “Complete” in
this slice therefore means every file recorded for those two installed
distributions, not every possible file, library, import hook, or executable in
the process or host.

The runtime additionally resolves the actual `__file__` and import-spec origin
for the Python modules and reads the loaded `libssl` and `libcrypto` paths from
bounded `/proc/self/maps`. It rejects ambiguous or missing OpenSSL mappings.
Every signed member is opened as a regular file with a non-inheritable,
`O_NOFOLLOW` descriptor; the promotion profile rejects group- or
world-writable files. Admission hashes stable pre/post descriptor state, and
later currentness checks rehash the retained descriptor and require the signed
path to reopen to the same admitted file state.

The offline capture helper is deliberately non-authoritative and permits a
writable development tree. Only `open_verified()` against the signed nested
policy can create the promotion profile. The deterministic test constructor is
marked non-promotion.

### 3.2 Exact Python launch profile

Promotion requires Python to have been launched with the effective
`-I -S -B` profile and for the signed runtime manifest to declare isolated mode
with the user site disabled.

- `-I` supplies isolated mode and implies `-E`, `-P`, and `-s`: Python ignores
  `PYTHON*` environment variables, does not prepend an unsafe path, and omits
  the user site directory.
- `-S` disables automatic `site` import and its path manipulations, including
  when `site` is later imported without an explicit `site.main()` call.
- `-B` prevents import-time `.pyc` writes. It reduces runtime filesystem
  mutation; it is not an integrity or provenance mechanism.

The verifier checks the corresponding immutable `sys.flags` fields:
`isolated`, `ignore_environment`, `safe_path`, `no_user_site`, `no_site`, and
`dont_write_bytecode`, and also requires `optimize == 0`; `-O` and `-OO` are
rejected because they can select optimized caches and remove assertions. There
is one important `-S` nuance: after an explicit
`import site`, `site.ENABLE_USER_SITE` remains `None`, not `False`, because
normal site initialization did not run. V4.9B therefore requires
`ENABLE_USER_SITE is not True` **and** `site.check_enableusersite() is False`,
rather than incorrectly requiring the sentinel to equal `False`.

The ordinary developer interpreter does not satisfy this promotion profile and
must remain ineligible. A measured launcher or immutable deployment image must
also provide the admitted import path under `-I -S`; V4.9B does not infer or
mutate that launch configuration. The bounded profile also requires
`Py_ENABLE_SHARED == 0` and rejects any separately mapped `libpython`; this
ensures that the signed Python executable contains the interpreter core for
this profile. It remains a bounded guard, not complete ELF or host attestation.

## 4. Exact owner handshake bracket

`LinuxSocketOwnerV4` now has an exact V4.9B candidate that retains the measured
driver, governed clock, connected socket, namespace and socket-cookie identity,
and one shared I/O lock. Production eligibility additionally requires the real
V4.8B clock authority and the promotion-eligible measured driver; deterministic
clock or artifact seams remain test-only.

One handshake attempt is permitted. Under the owner lock it:

1. snapshots the exact socket/clock/namespace owner;
2. takes a governed pre-sample;
3. revalidates the owner and measured driver;
4. records an inner `CLOCK_BOOTTIME` start;
5. awaits the exact V4.9A TLS/WebSocket handshake on the retained socket;
6. records an inner `CLOCK_BOOTTIME` completion;
7. takes a governed post-sample; and
8. requires the second owner snapshot and all clock/chronyd provenance to be
   unchanged.

The restricted `DriverHandshakeTransitionV49B` retains the exact evidence and
requires strict causal containment:

```text
pre.boottime_after
  < actual handshake start
  < actual handshake completion
  < post.boottime_before
```

It also requires a positive wall interval from `pre.wall_after` to
`post.wall_before`. The signed session deliberately uses these conservative
outer wall and BOOTTIME endpoints, not the narrower inner probes, and uses the
maximum uncertainty of the two governed samples. This prevents the session
from asserting more precise authoritative timing than the clock evidence can
support.

Any exception or cancellation aborts the owner and measured driver. Fork,
process, thread, socket, namespace, clock, chronyd, driver-policy, or loaded
runtime-observation change invalidates the transition.

## 5. Runtime-only session construction and durable bind

The new async runtime operation accepts only the already governed scope,
adapter, partition, collector-instance, and idempotency identifiers. It accepts
no session object, socket owner, socket, handshake evidence, timestamps,
generation, parent session, signer, clock, or entropy seam.

For the bounded initial connection it fixes generation to `1` and parent to
`None`, performs the exact owner handshake, takes another governed binding
sample strictly after the post-handshake bracket, and constructs
`TransportSessionAttestationV4` from:

- the admitted deployment and collector key;
- the signed transport policy and nested runtime-environment identity;
- the exact retained socket/clock owner;
- the exact TLS, HTTP, certificate, endpoint, and nonce evidence; and
- the conservative clock bracket described above.

The runtime verifies this mapping against the retained transition before
commit. The live projection's public append continues to reject
caller-authored session facts. One private path admits only the projection's
exact retained live `LinuxSocketOwnerV4`, rechecks the same driver-derived
mapping, and delegates to the existing shared transaction core.

That SQLite transaction writes the signed session and signed socket-owner
binding as one atomic pair. Transaction fault points cannot expose only one
half. SQLite atomicity applies only to those local database changes; it does
not make the preceding network handshake transactional.

After commit, the runtime revalidates the exact owner, writer lease,
application fence, and a strictly later governed clock sample. It then binds
the exact retained handshake evidence inside the driver, revalidates the owner
again, and only afterward publishes `SESSION_COMMITTED`. Subscription and
control sends remain denied until that evidence bind exists.

If any post-commit check or evidence bind fails, the owner is aborted and the
runtime is permanently fault-latched. The durable session/binding pair may
remain as evidence of the attempted connection, but it does not become send
authority and cannot be retried as a new handshake fact.

## 6. Implemented surface

| Concern | File |
|---|---|
| Nested signed driver policy and deployment capability binding | `riskyieldmm/trading/operational_manifests_v4.py` |
| Offline capture, retained exact member verification, process-profile gate | `riskyieldmm/trading/operational_runtime_artifacts_v49b.py` |
| Measured-driver construction and artifact currentness propagation | `riskyieldmm/trading/physical_transport_tls_v49.py` |
| Exact owner candidate, causal handshake transition, post-commit evidence bind | `riskyieldmm/trading/physical_transport_linux_v4.py` |
| Runtime-only session construction and post-commit fail-stop | `riskyieldmm/trading/physical_transport_runtime_v4.py` |
| Public live rejection and private atomic driver-derived append | `riskyieldmm/trading/physical_projection_v4.py` |
| Manifest and measured-file adversaries | `tests/test_trading_operational_manifests_v4.py`, `tests/test_trading_operational_runtime_artifacts_v49b.py` |
| Owner, runtime, projection, cancellation, and local TLS integration adversaries | `tests/test_trading_physical_transport_linux_owner_v4.py`, `tests/test_trading_physical_transport_runtime_v49b.py`, `tests/test_trading_physical_transport_runtime_v4.py`, `tests/test_trading_physical_projection_v4.py`, `tests/test_trading_physical_transport_tls_v49.py` |

## 7. Acceptance evidence

Final integrated verification completed on 2026-07-17:

- **29 dedicated V4.9B tests passed**;
- **700 adjacent physical/operational/transport tests passed**;
- **1,971 repository tests passed with 32 skipped**;
- focused Ruff lint/format, `py_compile`, and `git diff --check` **passed**.

The acceptance suite must cover at least policy canonicalization, missing or
extra roles, bytecode-cache origin/content substitution, actual `-B` cache
loading, distribution-member omission and substitution, import-origin and
loaded-library mismatch, shared-libpython and optimized-interpreter rejection,
path replacement/mutation, symlink and writable-file rejection, non-isolated
production denial, fork/thread/close invalidation,
caller-authored live-session rejection, one-shot owner evidence identity,
strict pre/handshake/post ordering, cancellation, every session/binding
transaction fault, and every post-commit owner/lease/fence/clock/bind failure.

These are local correctness and falsification results. They are not privileged
deployment, Internet/provider, crash-recovery, long-soak, data-authority, or
trading evidence.

## 8. Primary-source basis and limits

- Python's [command-line documentation](https://docs.python.org/3.12/using/cmdline.html)
  defines `-I`, its implied `-E`/`-P`/`-s` behavior, `-S`, and `-B`; the
  [`sys.flags` reference](https://docs.python.org/3.12/library/sys.html#sys.flags)
  exposes the effective launch state checked by V4.9B. These flags reduce
  ambient import influence but do not attest the launcher, files, or memory.
  The [import-system reference](https://docs.python.org/3.12/reference/import.html#cached-bytecode-invalidation)
  explains cached-bytecode validation; V4.9B signs the three cache candidates
  because `-B` is a write-control flag, not a cache-read prohibition.
- CPython's [build configuration](https://docs.python.org/3.12/using/configure.html#linker-options)
  documents shared-library builds. V4.9B rejects that profile rather than
  claiming the executable hash covers a separately mapped interpreter core.
- [`importlib.metadata`](https://docs.python.org/3.12/library/importlib.metadata.html#distribution-files)
  exposes an installed distribution's recorded files and reports `None` when
  the file list is unavailable. The [PyPA installed-project
  specification](https://packaging.python.org/en/latest/specifications/recording-installed-packages/#the-record-file)
  permits empty `RECORD` hashes and sizes. This supports enumeration plus
  independent remeasurement, not trust in metadata values.
- [SLSA artifact verification](https://slsa.dev/spec/v1.2/verifying-artifacts)
  separates an artifact's digest from trusted provenance expectations. V4.9B
  measures admitted installed bytes but does not claim SLSA provenance or a
  trusted build platform.
- Linux [`/proc` mapping documentation](https://www.kernel.org/doc/html/latest/filesystems/proc.html)
  describes process mappings; V4.9B uses `/proc/self/maps` to identify loaded
  OpenSSL files. This doesn't attest all mappings or detect arbitrary mutation
  of already loaded memory. Linux
  [`fs-verity`](https://www.kernel.org/doc/html/latest/filesystems/fsverity.html)
  can provide kernel-enforced read-only file integrity on supported
  filesystems, but it is a future deployment option and is not implemented by
  this slice.
- Python's [`SSLObject`/`MemoryBIO` documentation](https://docs.python.org/3.12/library/ssl.html#memory-bio-support)
  supports the V4.9A separation of TLS state from caller-owned network I/O.
  The [`asyncio` socket API](https://docs.python.org/3.12/library/asyncio-eventloop.html#working-with-socket-objects-directly)
  confirms that `sock_sendall()` reports success or exception without exact
  partial-send accounting; that evidence gap remains for V4.9C.
- SQLite's [atomic-commit documentation](https://www.sqlite.org/atomiccommit.html)
  supports all-or-nothing changes within the local transaction. It does not
  make a network action and a database transaction one distributed commit.

## 9. Remaining gates and exact next slice

V4.9B is a measured **driver** closure, not full-process or in-memory
attestation. It doesn't measure every collector module, import hook, loader,
transitive system library, interpreter data/code page, kernel, or host state.
It also cannot prove that already mapped code still equals the retained file.
Promotion therefore still requires either an external measured launcher and
immutable image or an expanded full collector-runtime closure with an
independently reviewed trust model.

Supply-chain provenance also remains open: the exact signed dependency lock,
hashed offline wheelhouse or immutable image, wheel/source provenance, build
reproducibility, and controlled installation ceremony must agree with the
measured runtime. Measuring the installed result doesn't establish who built
it or why it should be trusted.

V4.9C remains next and must add:

1. non-substitutable raw append plus parser transition and durable
   cross-ingress source spans;
2. an ordered automatic-output obligation queue;
3. exact prepared-wire subscription and application sends;
4. positive partial-kernel-send accounting; and
5. distinct WebSocket Close, TLS `close_notify`, clean/unclean EOF,
   truncation, timeout, and TCP terminal evidence.

The public factory must remain closed through V4.9C. After that, the project
still requires the outstanding privileged V4.8B/systemd/chronyd gates, signed
lock/wheelhouse deployment, provider and certificate-rollover conformance,
crash/restart campaigns, long no-trading soaks, drift monitoring, and
independent review before reconsidering provider authority.

V4.9B does not establish live readiness, provider correctness, completed-bar
authority, predictive edge, order correctness, trading safety, or
profitability. Its bounded contribution is to make the initial transport
session an internal consequence of one signed measured-driver transition and
one exact durable owner pair, while preserving fail-stop behavior everywhere
outside that proof.
