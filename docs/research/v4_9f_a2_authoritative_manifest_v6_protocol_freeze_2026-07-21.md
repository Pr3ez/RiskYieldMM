# V4.9F-A2 Authoritative Local Manifest Raw V6 Protocol Freeze

**Date:** 2026-07-21  
**Implementation reconciliation:** 2026-07-21  
**Trust-ceiling clarification:** 2026-07-22

**Status:** Implemented and locally accepted as the observed-local Raw V6
authoritative-manifest sub-gate. This acceptance is EXPLORATORY and
non-promotional. It is not A2-M completion, Stage 1 exit, public live-path
qualification, external attestation, or trading evidence.

**Roadmap position:** Stage 1 critical corrections, inside V4.9F-A2-M Step 2,
after the historical caller-declared Raw V5 checkpoint and before Raw V7
failed-prefix/cancellation evidence, stable in-operation markers, non-ingress
operations, complete target fields, normalization, finalization, isolation,
publication, calibration, or enforcement.

**Parent protocol:**
[`v4_9f_a2_measurement_and_enforcement_protocol_freeze_2026-07-20.md`](v4_9f_a2_measurement_and_enforcement_protocol_freeze_2026-07-20.md)

## 1. Decision and authority ceiling

The implemented measurement schema is:

```text
riskyieldmm_physical_transport_a2m_raw_v49f_v6
```

Raw V6 makes the smallest implemented change which closes the Raw V5 manifest
substitution seam:

1. The caller supplies only a campaign label, exact workload tuple, and exact
   measurement design.
2. Source, deployment/runtime, process environment, storage, session, policy,
   and clock-origin facts are obtained from local observers and retained
   runtime authorities.
3. A one-shot runtime-owned Ed25519 signer binds the resulting authority
   subject through a fixed domain-separated payload.
4. Public sampling and bundle construction require the retained collected
   campaign capability. Replaying `manifest.json` does not recreate runtime
   authority.
5. Each sample binds `manifest_authority_id`.
6. The artifact remains exactly four members: `manifest.json`,
   `samples.jsonl`, `correctness.json`, and `integrity.json`.
7. Raw V5 is rejected. There is no hydration, semantic conversion, or automatic
   upgrade into Raw V6.

The evidence class is:

```text
OBSERVED_LOCAL_SIGNED_DEPLOYMENT_BOUND_V49F_V6
```

The serialized authority also states:

```text
external_attestation_status = NOT_EXTERNALLY_ATTESTED
promotion_eligible = false
signature_algorithm = ED25519
```

This is observed-local integrity evidence. It is not SLSA provenance, an
in-toto attestation, DSSE, verified boot, IMA, fs-verity, TPM evidence, remote
attestation, or proof that the observing host was uncompromised.

## 2. Implemented ownership boundary

The implementation is divided across these authority seams:

| Surface | Implemented owner |
|---|---|
| Source observation and retained source descriptors | `physical_transport_capacity_source_observation_v49f.py` |
| Manifest request, runtime/process observations, signature, admitted expectation, and retained campaign | `physical_transport_capacity_manifest_authority_v49f.py` |
| Raw V6 manifest/sample/correctness/integrity codec | `physical_transport_capacity_measurement_v49f.py` |
| Public retained-campaign runner and bundle boundary | `physical_transport_capacity_sampler_v49f.py` |
| Runtime-owned deployment/session/driver/clock capture and signing | `physical_transport_runtime_v4.py` |
| Runtime-owned SQLite identity and pragma observation | `physical_projection_v4.py` and `physical_transport_actor_journal_v49c.py` |
| Linux runtime authority projection | `physical_transport_linux_v4.py` |

No caller-facing collector argument accepts a source hash, runtime identity,
environment record, deployment record, session ID, socket identity, clock
origin, public key, or signature.

## 3. Exact serialized graph

### 3.1 Manifest request

`CapacityMeasurementManifestRequestV49F` is intent, not provenance. Its exact
semantic fields are:

```text
campaign_label
phase
measurement_design_id
workload_corpus_sha256
workload_ids
workload_sha256s
manifest_request_id
```

`phase` is exactly `EXPLORATORY`. Workload IDs are sorted and unique; IDs and
hashes are non-empty and aligned. The request is reconstructed from the
executable design and workload tuple.

### 3.2 Source observation

`SourceObservationSnapshotV49F` contains:

```text
repository_root
git_state
members
member_count
total_bytes
source_tree_sha256
deployment_source_tree_sha256
deployment_source_tree_matches
source_observation_id
schema_version
```

The nested Git record contains the object format, HEAD commit, HEAD tree,
optional full branch ref, exact porcelain-v2 `-z` status bytes as canonical
base64, the derived clean flag, and `git_state_id`.

Each `SourceMemberObservationV49F` contains a repository-relative path, sorted
module roles, size, SHA-256, device, inode, mode, modification/change times,
and `member_id`. Device, inode, mode, and nanosecond text are canonical unsigned
decimal with at most 39 digits.

The deployment source-tree identity is portable: it commits ordered relative
paths, sizes, and content hashes. The full observation identity additionally
commits Git state and local file identities. A matching deployment tree is
mandatory for manifest construction.

### 3.3 Runtime observation

`CapacityMeasurementRuntimeObservationV49F` is projected from the runtime-owned
manifest-authority snapshot. It binds:

- authority profile and runtime schema;
- deployment bundle, sequence, trust root, and environment;
- collector release, key authorization, key ID, release name/version/entrypoint,
  declared source tree, and build artifact;
- runtime-environment and TLS/WebSocket driver policy;
- retained driver-runtime observation;
- transport-capacity policy, session, driver nonce, and kernel socket;
- boot ID, time/network namespaces, monotonic clock domain, and clock-source
  manifest; and
- paired chronyd launch/runtime identities when chronyd authority is present.

The resulting `runtime_observation_id` commits the exact record. It does not
replace the underlying verified deployment, driver, owner, and clock
capabilities retained by the runtime.

### 3.4 Process/environment observation

`CapacityMeasurementProcessEnvironmentObservationV49F` observes bounded facts
from the current process and runtime-owned SQLite projection:

- capture time and monotonic bracket;
- kernel, machine, CPU model/count/affinity;
- Python implementation/version/full version/cache tag/ABI, executable path
  and SHA-256, platform tag, `sys.flags`, ordered `sys.path` digest, and import
  meta-path type digest;
- event-loop and event-loop-policy implementation;
- OpenSSL, websockets, and SQLite versions;
- filesystem type/mount identity, database path/device/inode, storage identity,
  exact SQLite pragmas, and pragma digest;
- boot ID, time/network/mount/PID/cgroup namespaces, and cgroup-membership
  digest; and
- reviewed safe environment values, sorted sensitive-variable names, one
  aggregate digest of the complete sensitive name/value pairs,
  `environment_sha256`, and loader-injection presence.

Sensitive plaintext values are not serialized. Their aggregate digest binds
changes across currentness checks. It is an integrity commitment, not a secret
store or a confidentiality guarantee against guessing low-entropy values.

`/proc/self/exe` and the resolved `sys.executable` path are opened separately,
hashed through retained descriptors with pre/post `fstat`, and required to have
the same file identity and digest during each observation.

### 3.5 Signed manifest authority

`CapacityMeasurementManifestAuthorityV49F` contains the exact subject fields:

```text
authority_profile
external_attestation_status
manifest_request_id
source_observation_id
runtime_observation_id
environment_observation_id
deployment_bundle_id
deployment_trust_root_id
collector_release_manifest_id
runtime_environment_manifest_id
transport_session_id
driver_evidence_nonce_sha256
kernel_socket_identity
transport_capacity_policy_id
started_at_utc
monotonic_origin_nanoseconds
boottime_origin_nanoseconds
loop_time_origin_nanoseconds
promotion_eligible
```

`authority_subject_id` is the Raw V6 semantic identity of those fields. The
runtime signs canonical JSON with this exact shape:

```text
canonicalization_version
domain = RiskYieldMMA2MManifestAuthoritySubjectV4_9F_RawV6
payload:
  authority_subject_id
  collector_attestation_key_id
  deployment_bundle_id
  transport_session_id
schema_version = riskyieldmm_physical_transport_a2m_raw_v49f_v6
```

The authority record embeds the Ed25519 public key, derived key ID, lowercase
128-hex-character signature, signature algorithm, and
`manifest_authority_id`. This is direct domain-separated Ed25519. There is no
DSSE envelope, payload type, observation statement, approval record, or
serializable sealed-context record.

### 3.6 Manifest and derived compatibility projections

`CapacityMeasurementManifestV49F` embeds the request, source observation,
runtime observation, process/environment observation, and signed authority in
full. It also retains the established top-level source, runtime, environment,
session, policy, workload, design, and three-clock fields.

Those top-level fields are compatibility projections, not caller authority.
Manifest construction requires exact equality with the corresponding nested
observation. The authority must cross-link every nested identity and the same
deployment, release, session, nonce, socket, policy, start time, and clock
origins. Any rehashed alias or cross-link substitution is rejected.

`campaign_manifest_id` commits the complete manifest. It is distinct from the
later evidence-bundle identity because samples are execution results, not part
of the preregistered campaign identity.

## 4. Source collection and currentness

The release-source inventory is exactly the 40 names in
`CRITICAL_SOURCE_MODULES_V49F`. The same deterministic producer,
`measure_current_release_source_tree_v49f()`, is used to create the source-tree
hash that a deployment release must sign.

Collection enforces all of the following:

- every inventory member resolves to the exact object in `sys.modules`;
- every loaded `riskyieldmm` module is in the frozen inventory, including
  fileless modules; an extra module fails closed;
- `module.__name__`, `module.__file__`, `module.__spec__.name`, and
  `module.__spec__.origin` agree;
- the loader is a matching `SourceFileLoader`, and the origin is a `.py` file
  inside the retained repository root;
- every directory component and final file is opened with `openat`-style
  no-symlink traversal, close-on-exec, and non-inheritable descriptors;
- every bounded file hash uses positioned reads bracketed by identical
  `fstat` identity;
- Git object format, HEAD, tree, a separately queried branch ref, and exact
  `--no-optional-locks -c core.fsmonitor=false -c core.untrackedCache=false
  status --porcelain=v2 -z --untracked-files=all` bytes are captured before and
  after member collection; and
- the loaded-module mapping, root path, Git state, retained inode, reopened
  path identity, digest, and file metadata remain unchanged at each governed
  currentness check.

`source_tree_clean` is derived from whether the exact status payload is empty.
Raw V6 remains EXPLORATORY and non-promotion even when clean. Dirty status is
committed, but modification of a frozen source member also changes the source
tree and therefore fails the signed-release comparison.

## 5. Collection, signing, and retained capability

Collection uses this order:

```text
capture distinct MONOTONIC, CLOCK_BOOTTIME, and event-loop origins
  -> capture runtime and SQLite authority
  -> observe and retain the source closure
  -> recapture runtime and SQLite authority
  -> observe process/environment facts
  -> recheck source currentness
  -> derive request and complete authority subject
  -> create one-shot signing authorization
  -> runtime recaptures authority under its orchestration boundary
  -> consume authorization and sign the fixed payload
  -> reconstruct manifest and retained campaign
  -> perform final pre-return currentness check
```

The signing authorization is exact-type, one-shot, PID-, thread-, event-loop-,
and fork-bound. It retains the observed source, runtime, SQLite, process, and
clock subject. Before signing it rechecks source, runtime, SQLite, stable
process fields, the 120-second maximum collection age, and at most one second
of MONOTONIC/event-loop elapsed disagreement. Opaque caller-selected strings
cannot be signed through this seam.

`CollectedCapacityMeasurementCampaignV49F` is the live non-serializable
capability. It retains the runtime, source descriptors, runtime snapshot,
SQLite observation, observed records, creator PID/thread/event loop, and
close/fork state. JSON cannot recreate it.

The production runner checks campaign currentness before boundary collection,
again immediately before the underlying operation, and after the post-operation
boundary. Post-operation authority failure preserves the truthful operation
evidence but sets measurement outcome to `ERROR` with
`MANIFEST_AUTHORITY_CHANGED_AFTER_OPERATION`. Public bundle construction checks
the campaign before and after creating the provisional four-member bundle.

Collection is all-or-nothing. A `BaseException`, including cancellation, closes
the partially retained source authority and returns no collected campaign.
Closing a returned campaign is irreversible.

## 6. Independent offline trust expectation

Canonical replay plus the embedded key proves only that a candidate is
self-consistent. A hostile writer can replace the whole local closure, insert a
foreign key and deployment claim, sign it, and recompute every identity.

Offline authenticity therefore requires an independently admitted static
`AdmittedCapacityMeasurementAuthorityExpectationV49F`. Its exact comparison
surface includes:

- authority profile and runtime schema;
- deployment bundle, sequence, trust root, and environment;
- collector release identity, name, version, entrypoint, key authorization,
  key ID, and public key;
- runtime-environment manifest;
- source-tree and build-artifact hashes;
- TLS/WebSocket driver policy;
- transport-capacity policy; and
- clock-source manifest.

`from_verified_deployment()` derives this expectation only from an exact
`VerifiedDeploymentCapabilityV4` and its exact matching
`CollectorReleaseManifestV4`. The verifier reconstructs Raw V6 and then requires
the manifest's complete static authority surface to equal that independently
admitted expectation.

That comparison authenticates the signed manifest authority subject and its
starting deployment/runtime claims only. The signature does not cover the
later `samples.jsonl`, provisional correctness, integrity member, or a final
sample/receipt root. Those members are canonical and hash-closed, but a local
offline editor can replace a complete suffix and recompute its unsigned roots
without the signing key. Raw V6 therefore makes no post-run issuance-
authenticity claim; the later independent finalizer, publisher, and external
anchor gates must close that boundary.

This verifier does not make an untrusted expectation trustworthy. The caller
must obtain the verified deployment capability and release through the existing
deployment trust path, outside the candidate Raw V6 artifact.

## 7. Public/live boundary

`collect_capacity_measurement_campaign_v49f()` accepts only an exact
`LIVE_LINUX` runtime profile. The public live runtime factory remains
fail-closed, so that path is currently unreachable and has not been exercised
end to end.

The successful end-to-end collector test uses only the private explicit
`EXACT_TEST` collector. It covers the same internal collection path but does not
prove privileged host integration, real provider behavior, or public live
construction. Raw V6 acceptance must not be described as a live campaign.

## 8. Codec and artifact closure

The only artifact layout is:

```text
v4_9f_a2_measurement/<evidence_bundle_id>/
    manifest.json
    samples.jsonl
    correctness.json
    integrity.json
```

JSON records are canonical, non-empty, exactly LF-terminated, bounded by record
type, and replayed byte-for-byte. Sample JSONL is non-empty, LF-only, contains
no blank record, bounds each record before parsing, bounds total record count
and bytes, and reconstructs the frozen deterministic schedule.

`integrity.json` commits the exact media type, byte count, record count, and
SHA-256 of the other three members. The artifact mapping admits exactly the
four names. Member and total bounds are checked before nested parsing.

Correctness remains deliberately provisional. Every Raw V6 correctness record
must contain `CORRECTNESS_FINALIZER_NOT_IMPLEMENTED`; the six finalizer-owned
claims remain false and `passed` remains false. The manifest-authority gate does
not implement the independent correctness finalizer or make a bundle
publishable.

Raw V5 schema bytes are rejected by Raw V6 JSON, JSONL, and bundle replay.
Historical V5 artifacts may be retained as historical bytes, but they cannot
enter a V6 runner, finalizer, publisher, calibration, or enforcement path.

## 9. Frozen parser and collection bounds

These limits are resource-safety bounds, not measured transport capacity or
production thresholds:

| Surface | Bound |
|---|---:|
| Manifest-request workloads / manifest workloads | 256 |
| One canonical workload manifest | 1 MiB |
| Aggregate workload corpus | 16 MiB |
| Warm-up repetitions per workload | 10,000 |
| Measured repetitions per workload | 100,000 |
| Total trials / samples | 100,000 |
| Manifest JSON | 32 MiB |
| One sample JSONL record | 64 MiB |
| Samples JSONL | 256 MiB |
| Correctness JSON | 4 MiB |
| Integrity JSON | 1 MiB |
| Four-member closure | 293 MiB |
| Source members | 512 |
| One source member | 8 MiB |
| Aggregate source bytes | 64 MiB |
| Raw Git status bytes | 2 MiB |
| Git stderr | 64 KiB |
| One Git subprocess | 10 seconds |
| Source hash read chunk | 128 KiB |
| Normalized source path | 4,096 text characters |
| Source and clock unsigned decimal text | 39 digits |
| Process environment variables | 4,096 |
| Canonical environment observation payload | 1 MiB |
| Process executable | 1 GiB |
| Signing-authorization collection age | 120 seconds |
| MONOTONIC/event-loop elapsed disagreement | 1 second |
| Ed25519 signatures | exactly one 64-byte signature |

The existing physical-output bounds remain the Raw V6 continuation of the
accepted exact-output representation. They are schema plausibility limits, not
evidence that the live system can sustain those values.

## 10. Adversarial verification and acceptance evidence

The accepted verification covers:

- deterministic release-source production and signed-release comparison;
- clean and dirty Git byte capture, two-pass Git races, source mutation,
  truncation, symlinked path components, root/path replacement, and descriptor
  cleanup;
- exact 40-module inventory, fileless/extra module rejection, module/spec/loader
  disagreement, outside-root origins, and thread/fork/close currentness;
- runtime/store recapture, orchestration/A1 quiescence, SQLite pragma/path/inode
  replacement, driver-currentness failure, and unchanged public-factory denial;
- distinct MONOTONIC, BOOTTIME, and event-loop origins;
- one-shot non-opaque signing authorization;
- nested request/source/runtime/environment substitution with recomputed outer
  identities;
- foreign signature, key, authority cross-link, top-level alias, and sample
  authority substitution;
- whole-closure foreign replacement accepted only as self-consistent local
  bytes and rejected against the independent admitted expectation;
- sensitive-environment aggregate digest drift;
- workload count, corpus, repetition, total-trial, uint-text, JSON/JSONL member,
  and whole-closure limits before unbounded parsing/allocation;
- exact manifest and four-member byte round-trip; and
- strict Raw V5 rejection without upgrade.

The final current-tree runs are disjoint by test file and therefore total **228
tests**:

| Verification group | Result |
|---|---:|
| Source observation plus manifest/codec/adversarial contracts | 132 passed in 10.48 s |
| End-to-end collector, environment drift, trusted-expectation, and one-shot signing | 4 passed in 39.39 s |
| Runtime-owned manifest-authority seam | 5 passed in 73.98 s |
| Public retained-campaign sampler regression | 25 passed in 417.59 s |
| Adjacent projection, journal, A1-capacity, Linux-owner, and runtime regression | 62 passed in 237.39 s |

Targeted Ruff formatting/lint and Python compilation passed. The final
serialization-surface and worktree checks are recorded in the parent protocol;
historical repository-wide counts are not added to these current focused
results.

The 2026-07-22 trust-ceiling clarification added one disjoint regression,
`test_trading_physical_transport_capacity_v6_trust_ceiling.py`, which passed
1 test in 1.36 s. It demonstrates that two different unsigned sample suffixes
can share the same signed Raw V6 manifest and both replay after their unsigned
roots are recomputed. This test narrows the documented claim to manifest-
authority authenticity; it is not added retroactively to the historical 228-
test acceptance count and does not promote either suffix.

## 11. Designs considered

| Design | Decision | Reason |
|---|---|---|
| Keep caller-declared Raw V5 provenance | Rejected | Hashing a declaration does not show that it described the executing process |
| Auto-upgrade V5 by inventing observations | Rejected | The observation never occurred and cannot be reconstructed historically |
| Add a fifth provenance member | Rejected for V6 | Nested records preserve the exact four-member artifact closure |
| Deterministic source observation, runtime-owned authority capture, retained campaign, and direct domain-separated Ed25519 | Implemented | It closes local caller substitution with the smallest compatible graph |
| DSSE/in-toto statement | Deferred | Useful for interoperable external attestations, but not required for this embedded local record and not implemented here |
| SLSA provenance/VSA | Deferred | Requires an independent build/verifier pipeline and externally supplied expectations |
| OCI descriptors and TUF metadata | Deferred | Useful for distribution and rollback protection, not proof of the running host |
| fs-verity, IMA, measured boot, or remote attestation | Deferred | Requires privileged provisioning and an independent host trust root |

## 12. Primary-source basis

- Git defines its stable machine-readable status surface in
  [`git status --porcelain=v2 -z`](https://git-scm.com/docs/git-status#_porcelain_format_version_2).
  [`git hash-object`](https://git-scm.com/docs/git-hash-object) and
  [`racy-git`](https://git-scm.com/docs/racy-git) explain why commit/index/stat
  metadata alone is not an identity for running mutable bytes.
- Python's [import system](https://docs.python.org/3/reference/import.html) and
  [`ModuleSpec` and loader contracts](https://docs.python.org/3/library/importlib.html#importlib.machinery.ModuleSpec)
  motivate checking module, spec, loader, origin, and file together. They do not
  prove that in-memory code objects still correspond to a source file.
- Linux documents [`open`/`openat`](https://man7.org/linux/man-pages/man2/open.2.html),
  [`pread`](https://man7.org/linux/man-pages/man2/pread.2.html),
  [`/proc/pid/exe`](https://man7.org/linux/man-pages/man5/proc_pid_exe.5.html),
  [`/proc/pid/ns`](https://man7.org/linux/man-pages/man5/proc_pid_ns.5.html), and
  [`/proc/pid/cgroup`](https://man7.org/linux/man-pages/man5/proc_pid_cgroup.5.html).
  Retained descriptors plus reopen/re-observation are local race controls, not
  filesystem immutability.
- SQLite's official [PRAGMA reference](https://www.sqlite.org/pragma.html)
  defines the live settings captured from the runtime-owned connection. Those
  settings and an inode do not prove database logical contents or durability.
- [RFC 8032](https://www.rfc-editor.org/rfc/rfc8032) specifies Ed25519. Raw V6
  additionally supplies its own fixed semantic domain and exact signed payload;
  it makes no generic attestation-format claim.
- [SLSA provenance](https://slsa.dev/spec/v1.2/provenance),
  [SLSA artifact verification](https://slsa.dev/spec/v1.2/verifying-artifacts),
  [in-toto Statement v1](https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md),
  and [DSSE](https://github.com/secure-systems-lab/dsse/blob/master/protocol.md)
  define stronger interoperable supply-chain relationships. They support the
  need for an independent expectation; Raw V6 does not implement them.
- [OCI descriptors](https://github.com/opencontainers/image-spec/blob/main/descriptor.md),
  [The Update Framework](https://theupdateframework.github.io/specification/latest/),
  [fs-verity](https://docs.kernel.org/filesystems/fsverity.html), and
  [Linux IMA/EVM](https://docs.kernel.org/security/integrity.html) inform later
  distribution and host-integrity work and are explicit nonclaims here.

## 13. Limitations and nonclaims

Raw V6 does not establish:

- independent build provenance, reproducible builds, or dependency resolution;
- that a locally observed Git object is authentic merely because it hashes;
- bytecode, code-object, interpreter-memory, native-extension, shared-library,
  or complete installed-distribution identity; the frozen source profile admits
  only exact `.py` `SourceFileLoader` origins;
- prevention of dynamic imports; any loaded RiskYieldMM module outside the
  exact inventory instead invalidates currentness;
- prevention of mutation between checks;
- resistance to root/kernel compromise, signer-key compromise, ptrace/process
  injection, verified-boot failure, or hostile storage below the process;
- external authenticity without an independently admitted deployment
  expectation;
- post-run sample/correctness/integrity issuance authenticity from the signed
  manifest or its admitted expectation;
- an exercised public `LIVE_LINUX` collector path;
- stable in-operation markers, failed-prefix recovery, a persisted cancellation
  terminal record, non-ingress operations, or complete A2 target fields;
- physical alpha-normalization or matched OFF/OFF, ON/ON, and OFF/ON neutrality
  campaigns;
- an evidence-derived correctness finalizer;
- campaign isolation, an atomic durable publisher, restart-safe collision
  handling, or immutable external publication;
- calibration, independent confirmation, threshold freeze, A2-E enforcement,
  A3 scaling, or multi-session fairness;
- provider conformance, paper/live trading safety, predictive edge,
  profitability, Stage 1 exit, or production readiness.

## 14. Next gate

Following this accepted Raw V6 sub-gate, the next sequential A2-M gate is
**Raw V7 failed-prefix and cancellation terminal evidence**. It must persist
exact completed RAW/parser/output/actor progress and
truthful terminal state when ingress fails or is cancelled after partial
effects. Because that changes sample semantics, it requires a versioned Raw V7
contract; it must not be retrofitted into accepted Raw V6 identities.

Raw V7 still will not complete A2-M or Stage 1. Stable markers, non-ingress
operations, target coverage, normalization, finalization, isolation,
publication, frozen campaigns, calibration, enforcement, and the remaining
program-wide Stage 1 gates continue afterward.
