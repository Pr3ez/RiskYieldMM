# V4.9F-A2 Raw V7 Acceptance-Coverage Audit

**Audit date:** 2026-07-22
**Audited protocol:**
[`v4_9f_a2_failed_prefix_cancellation_v7_protocol_freeze_2026-07-21.md`](v4_9f_a2_failed_prefix_cancellation_v7_protocol_freeze_2026-07-21.md)
**Result:** **Raw V7 is locally accepted within its frozen trust ceiling.**

## 1. Executive result

This is an independent requirements-to-tests traceability review of every one
of the 27 rows in the frozen Section 13 acceptance matrix. The final post-format
tree supplies complete direct lifecycle, projection, offline-replay, runtime,
production-collector, inherited Raw V6/A1, adjacent-regression, static, and
leftover evidence for every row.

The row-level result is:

| Audit classification | Rows | Meaning |
|---|---:|---|
| Direct evidence | 27 | Every material clause in that row has directly relevant final-tree evidence |
| Partial evidence | 0 | At least one material clause is covered and at least one required clause lacks direct V7 evidence |
| Blocked by a contract/trust issue | 0 | No current matrix row depends on post-run issuance authenticity |
| Open | 0 | No acceptance row remains open |
| **Total** | **27** | All rows close directly; no partial count was used to accept Raw V7 |

The highest-severity finding is a provenance boundary, not a SHA-256 or
canonicalization failure. The V7 Ed25519 signature covers the manifest and
starting baseline only. It does not cover attempts, terminals, samples,
`correctness.json`, `integrity.json`, or a final receipt/sample root. Therefore
an offline editor needs no signing secret to construct a different internally
valid suffix from the public baseline and recompute every downstream receipt,
identity, root, and integrity digest. The codec establishes canonical internal
consistency of the claimed suffix; it does not certify that the suffix is the
one produced by the measured runtime.

The focused regression
[`test_trading_physical_transport_capacity_v7_trust_ceiling.py`](../../tests/test_trading_physical_transport_capacity_v7_trust_ceiling.py)
demonstrates this boundary harmlessly: two bundles have the same signed
`manifest.json`, different `samples.jsonl`, projection roots, and bundle IDs,
and both replay under the same admitted manifest expectation. Both remain
provisional with `passed is False`.

## 2. Scope and method

The audit inspected:

- the complete Section 13 matrix and Sections 2 through 10 of the Raw V7
  freeze;
- V7 lifecycle, artifact, adversarial, runtime, and production tests;
- inherited Raw V6 source, manifest, codec, collector, authority, and sampler
  suites;
- inherited A1 admission, actor/projection, Linux-owner, and ingress/runtime
  tests relevant to the claimed lower-layer invariants; and
- the V7 projection/lifecycle/artifact validation surfaces used by those
  tests.

Collector and runner behavior remained owned by the concurrent production
agent and was not changed by this audit. In addition to this document and the
isolated integrity-boundary regression, the audit added a focused acceptance-
edge suite and narrow lifecycle/codec hardening for UTF-8 byte ceilings,
bounded Raw V7 JSON structure, and artifact-length arithmetic.

### 2.1 Direct V7 test inventory

Pytest collection reports this exact file-disjoint V7 inventory:

| File | Collected cases |
|---|---:|
| `test_trading_physical_transport_capacity_lifecycle_v49f.py` | 6 |
| `test_trading_physical_transport_capacity_measurement_v7_v49f.py` | 42 |
| `test_trading_physical_transport_capacity_v7_adversarial.py` | 28 |
| `test_trading_physical_transport_runtime_v49f_lifecycle.py` | 13 |
| `test_trading_physical_transport_capacity_v7_production.py` | 1 |
| `test_trading_physical_transport_capacity_v7_runner_firewall.py` | 12 |
| `test_trading_physical_transport_capacity_v7_trust_ceiling.py` | 1 |
| `test_trading_physical_transport_capacity_v7_acceptance_edges.py` | 74 |
| `test_trading_physical_transport_capacity_v7_effect_acceptance.py` | 34 |
| `test_trading_physical_transport_capacity_v7_neutrality_baseline.py` | 21 |
| `test_trading_physical_transport_capacity_v7_static_surface.py` | 6 |
| `test_trading_physical_transport_capacity_v7_source_closure.py` | 4 |
| **Total** | **242** |

The 12 runner-firewall cases are the expanded pytest cases, not five source
function names: four post-terminal assembly failure points, four primary
exception classes, one closed-context latch failure, and two post-terminal
states, plus campaign finalization of an already-recorded run-ending prefix.
They are counted once as a disjoint file group. The 74 acceptance-edge cases
are likewise expanded pytest cases: source/manifest/schema/transaction,
receipt/classification, exact resource-bound arithmetic and JSON structure,
version-separation, and artifact-closure cases are each counted once.
The four source-closure cases are three fresh `python -I` production-observer
processes plus one frozen historical Raw V6 four-member fixture replay.

Two additional V7 source-successor cases live in the inherited source file:

- `test_raw_v7_source_inventory_is_an_explicit_historical_successor`; and
- `test_historical_raw_v6_source_snapshot_replays_after_inventory_revision`.

### 2.2 Inherited test inventory inspected

The current file-level Raw V6 inventory collects as follows:

| Group | Files | Current cases |
|---|---|---:|
| Source plus manifest/codec/adversarial | source observation (25), Raw V6 measurement/codec (78), Raw V6 manifest adversarial (31) | 134 |
| Retained Raw V6 collector | manifest collector | 4 |
| Runtime-owned manifest authority | manifest-authority runtime | 5 |
| Retained Raw V6 sampler | capacity sampler | 25 |
| Serialized trust-ceiling nonclaim | Raw V6 trust ceiling | 1 |
| **Current file-level total** | seven files | **169** |

The source file's 25 cases include the two V7 successor cases above. Removing
those two gives the same 166 Raw V6 source/manifest/collector/authority/sampler
cases recorded by the accepted predecessor; the additional trust-ceiling case
is a later nonclaim regression. The predecessor freeze also
records 62 adjacent projection/journal/A1/Linux-owner/runtime cases, for 228
historical current-tree cases at that checkpoint. It does not preserve the
exact file command for those 62 cases, which is itself a gap against Raw V7's
“exact test-file inventory” requirement. The frozen 39-file manifest below
closes that requirement for current Raw V7 acceptance without retroactively
rewriting the predecessor checkpoint.

The audit additionally inspected the current A1 and lower-layer inventories
most relevant to V7: A1 capacity contracts (22), V4.9F capacity runtime (3),
actor journal (2), actor contracts (62), actor projection (6), session actor
(34), V4.9D ingress runtime (12), Linux owner (8), V4.9D Linux ingress (3),
V4.9B runtime (15), and runtime integration (4). Lower-layer evidence is
credited only for the invariant it actually tests; it is not treated as a V7
sample, terminal, or artifact test.

### 2.3 Frozen adjacent-regression and audit inventories

[`raw_v7_regression_inventory_v49f.json`](../../tests/raw_v7_regression_inventory_v49f.json)
now freezes one file-disjoint, eight-group current-tree inventory:

| Group | Files | Collected cases |
|---|---:|---:|
| Raw V6 | 7 | 169 |
| A1 | 2 | 25 |
| Actor | 4 | 104 |
| Projection | 4 | 45 |
| Linux owner | 4 | 19 |
| Ingress | 5 | 42 |
| Terminal | 11 | 128 |
| Public denial | 2 | 26 |
| **Total** | **39** | **558** |

The verifier
[`verify_raw_v7_regression_inventory_v49f.py`](../../scripts/tests/verify_raw_v7_regression_inventory_v49f.py)
checks strict duplicate-free/finite JSON, exact scope and group order, disjoint
repository-contained paths after symlink resolution, every file digest, every
group/total count, and optionally exact pytest collection. Its digest
`3388b0af8b7a5d581f44abc8c6bd86ba4ca70c5f9b3ceb01182c5b51a3eee28d`
detects accidental inventory drift; it is neither a signature nor an external
authority. Collection passed at **39 files / 558 cases in 2.16 seconds**. The
final stable tree then executed all 558 cases in three file-disjoint manifest
partitions: Raw V6 plus A1 passed **194/194 in 653.97 seconds** (**654.25
seconds wall**); actor plus projection plus Linux owner passed **168/168 in
576.69 seconds** (**576.97 seconds wall**); and ingress plus terminal plus
public denial passed **196/196 in 1430.38 seconds**. The inventory verifier
reported the same
`3388b0af8b7a5d581f44abc8c6bd86ba4ca70c5f9b3ceb01182c5b51a3eee28d`
digest before the partitioned campaign and after its final adjacent partition.
These direct executions, not collection alone, close regression row 26.

The neutrality trace boundary also has four provisional structural safety
bounds: 16 MiB per literal prefix field, 4,096 items per sequence, 256 UTF-8
octets per identifier, and 65,536 total causal links. These prevent unbounded
test/oracle inputs; they are not measured neutrality, capacity, latency, or
production-acceptance thresholds.

## 3. Row-by-row traceability

Status legend: **Direct** means directly exercised; **Partial** means at least
one required clause remains unexercised; **Blocked** means current semantics
cannot support the frozen wording; **Open** means the required current audit is
absent. The matrix now explicitly makes post-run provenance a trust-ceiling
nonclaim, so no row is classified as blocked merely because V7 has no signed
final result.

| # | Acceptance area | Status | Current evidence | Remaining gap |
|---:|---|---|---|---|
| 1 | V7 source and authority | Direct | V7 manifest round-trip/independent expectation; exact-41 successor and production collection; direct role mutations reject missing critical/loaded roles, a renamed module, an unknown role, and a cross-member duplicate. Three fresh `python -I` processes prove the production observer rejects a file-backed extra module, an alias-loaded lifecycle module, and the canonical lifecycle name replaced by a fileless module. The frozen exact-40 Raw V6 fixture matches all four historical member lengths/SHA-256 values, V6 round-trips byte-identically, and V7 rejects it as a predecessor | None within the bounded Raw V7 row |
| 2 | Manifest composition | Direct | V7 round-trip/independent authority replay, nested V6 replay, and direct embedded-V5, reference-only, mutated-predecessor, outer-key-mismatch, V6-signature-replay, and V6/V7 mutual-manifest rejection cases exercise every frozen clause | None within the bounded Raw V7 row |
| 3 | Projection schema | Direct | Schema/validation/fingerprint bindings, canonical record/receipt/typed-row consistency, exact locator closure, a constructed pre-V7 database no-upgrade rejection, and five direct attempt/terminal/locator SQL mutation cases fault closed | None within the bounded Raw V7 row |
| 4 | Transaction faults | Direct | Attempt and terminal matrices cover canonical append, receipt, typed row, locator insert/delete, batch finish, commit, post-commit, and rollback boundaries; the 11-case startup-recovery matrix exercises the same atomic terminal/locator transaction and rollback-fault propagation | None within the bounded Raw V7 row |
| 5 | Attempt ordering | Direct | The success case observes the durable attempt before target read. A four-case production-path matrix then forges operation sequence, predecessor terminal, grant coordinates, or signed-policy coordinates after issuance and proves the exact validation error occurs before the target-effect counter can increment, with no attempt row left behind | None within the bounded Raw V7 row |
| 6 | Successful ingress | Direct | One successful Ping operation independently replays exact RAW bytes, parser state, Pong payload, automatic source/dispatch lineage, actor before/after coordinates, retained bytes, A1 grant coordinates, terminal runtime state, and `COMPLETE`. Its declaration intentionally predicts zero output while the observed Pong remains retained as correctness evidence | None within the bounded Raw V7 row |
| 7 | Failure before RAW | Direct | The exception-before-RAW case preserves the exact primary cause and directly asserts no RAW commit, no RAW dependency, an empty actor delta, baseline RAW/actor coordinates, derived `NO_DURABLE_EFFECT` plus `EXACT_DURABLE_PREFIX`, and truthful `FAULT_LATCHED` runtime state | None within the bounded Raw V7 row |
| 8 | Failure after RAW | Direct | `test_failure_after_raw_or_completed_output_retains_exact_durable_prefix[False]` injects the parser failure after durable RAW and asserts retained RAW record, dependency, RAW actor event, terminal, and exact-prefix classification | None within the bounded Raw V7 row |
| 9 | Partial parser/output | Direct | A five-case V7 matrix covers zero output, prepared-only output, one completion, one completion plus later failure, and two completions. It derives the completed-output count solely from durable `OUTBOUND_DISPATCH_COMPLETED` events, while the prepared-only case retains its unsent obligation | None within the bounded Raw V7 row |
| 10 | Send lifecycle | Direct | One integrated V7 matrix preserves five distinct prefixes and terminal meanings: unresolved attempt/`UNKNOWN`, conclusive zero via durable send failure, partial positive result, full local acceptance without dispatch completion, and fully completed dispatch/`COMPLETE` | None identified within this row; local kernel acceptance remains explicitly distinct from peer receipt |
| 11 | Cancellation | Direct | Nine integrated barriers cover before admission, grant-to-orchestration, after operation attempt, RAW commit, parser transition, prepared output, durable kernel attempt, kernel result, and dispatch completion. Each post-attempt case asserts the exact actor-kind sequence, RAW/dependency count, independently derived effect/progress classification, one synchronous cancellation terminal, bare cancellation identity, cancelled task state, no timeout relabel, and one A1 release | None within the bounded Raw V7 row |
| 12 | Repeated/racing cancellation | Direct | A triple-cancel case runs in three isolated harnesses and compares one normalized actor-kind/RAW/effect/progress/terminal oracle across all runs. Each run retains one terminal, `UNKNOWN` unresolved-send evidence, the exact `CancelledError`, at least three cancellation requests, no open attempt, and no `uncancel` or `shield` source path | None within the bounded Raw V7 row |
| 13 | Interruption | Direct | Parameterized `KeyboardInterrupt` and `SystemExit` cases persist `INTERRUPTED`, retain the exact class, and propagate the exact object without PASS/ERROR conversion; the runner firewall proves post-terminal assembly failure cannot mask either primary interruption | None within the bounded Raw V7 row |
| 14 | Postmortem loading | Direct | Owner-abort reload succeeds twice with exactly equal prefix evidence; the projection verification report and SQLite `total_changes` remain unchanged, the lifecycle-capability map remains empty, and the owner remains closed. Every retained store-identity coordinate is mutated independently, while session and writer-fence substitutions reject | None within the bounded Raw V7 row |
| 15 | Receipt-complete prefix | Direct | Prefix replay verifies contiguous receipts, strict registry decoding, recovered/final identities, RAW union and actor mappings; the existing mutation matrix plus a valid-but-unexplained foreign attempt-record splice reject missing/reordered/content-invalid/foreign receipt chains | None within the frozen structural claim; whole-suffix replacement is intentionally isolated in the serialized-trust-ceiling row |
| 16 | Derived classifications | Direct | Replay derives `COMPLETE`, `NO_DURABLE_EFFECT`, `EXACT_COMPLETED_PREFIX`, `UNKNOWN`, progress availability, completed-output lifecycle, and returned progress. V7 sample replay now independently rederives terminal effect/progress aliases from serialized actor/RAW facts; even a caller-recomputed unsigned terminal record and receipt cannot relabel unresolved-send `UNKNOWN` or claim unavailable progress | None within the bounded Raw V7 row |
| 17 | Orphan recovery | Direct | Startup snapshot is claimed before session reconciliation; one terminal is appended, locator removed, old session fenced, no network effect retried, and the next mutation is barred until completion | The one-open-attempt-per-session bound limits the exercised case to one session, but the required per-attempt behavior is directly covered |
| 18 | Recovery uncertainty | Direct | Process-loss cases after attempt, RAW, prepared output, completed dispatch, and around terminal commit retain the durable prefix and produce conservative recovery evidence without retry. The integrated send-state matrix additionally proves that an unresolved durable attempt remains `UNKNOWN`, while conclusive zero/result/dispatch evidence is not downgraded or promoted across those boundaries | None within the bounded Raw V7 row |
| 19 | Corruption/adversary | Direct | Reordered/dropped events, receipt gaps/predecessors, wrong ledger, RAW substitution, false prefix, duplicate terminal/locator contradictions, returned-progress mutations, a valid-but-unexplained foreign record splice, and direct classification-field relabelling all reject | None within the frozen corruption claim; whole-suffix replacement is intentionally addressed by the separate trust-ceiling row rather than misclassified as corruption detection |
| 20 | Serialized trust ceiling | Direct | `test_signed_manifest_provenance_does_not_certify_unsigned_sample_suffix` reuses one admitted signed manifest, constructs two different internally valid suffixes without another signer call, and proves both remain provisional and self-consistent under the same independent expectation | None within the frozen V7 claim; final-result provenance and anti-equivocation require a separately versioned signed/external anchor |
| 21 | Bounds | Direct | Direct exact/one-over cases cover the 48 MiB prefix, 256 KiB attempt/terminal, 32/64/4/1 MiB JSON members, 256 MiB samples aggregate, 293 MiB closure arithmetic, 100,000 records, representative safe integers, and 256-byte UTF-8 exception classes. Preparse cases cover exception/RAW/actor arrays and string/escape-aware JSON depth 64, object-member 512, and array-element 524,288 ceilings with stable rejection reasons | None identified within this row; the 256 MiB and 293 MiB edges are validated as integer lengths derived from actual bytes in production paths, without unsafe test allocations |
| 22 | Version separation | Direct | V6/V7 manifests, samples, and whole bundles mutually reject; embedded V5 and V6-signature-as-V7 replay reject; a pre-V7 database is rejected without upgrade; historical V6 source bytes still replay | None within the bounded Raw V7 row |
| 23 | Artifact closure | Direct | Sample construction requires one embedded attempt/terminal/prefix; five direct structural cases reject empty, missing-first, reordered, post-run-ending, and short-nonterminal streams; complete coverage after an early terminal rejects; production and the 12 runner-firewall cases cover complete and retained run-ending-prefix finalization | None within the frozen structural claim; replay intentionally proves structural integrity and retained-runner binding, not external issuance provenance |
| 24 | Neutrality baseline | Direct | An exact two-arm Raw V7 type makes V6/no-lifecycle input unrepresentable, keeps lifecycle journaling on while only resource probes toggle, and scopes literal reports to the same V7 baseline; physical reports explicitly disclaim byte/root equivalence. All ordered arm pairs, caller-forged reports, wrong types, one-over bounds, and changed-prefix cases are direct | This is a lifecycle-on baseline contract and bounded oracle, not executed matched campaigns, physical normalization, acceptable-overhead evidence, or a full neutrality claim |
| 25 | Public compatibility | Direct | Direct effect-path cases preserve the exact legacy method signature and return/error/cancellation behavior, including primary exception/cancellation identity and zero V7 lifecycle rows. Test-runtime use of the `LIVE_LINUX` collector still denies, three legacy terminal-bypass routes deny, and the exported V7 authorization/error surface remains measurement-only | None identified within this row; production-route promotion and public-live qualification remain later explicit gates |
| 26 | Regressions | Direct | A reproducible hash-checked manifest freezes 39 disjoint current files and 558 cases across Raw V6, A1, actor, projection, Linux owner, ingress, terminal, and public denial. Three file-disjoint final-tree partitions passed 194/194 in 653.97 seconds (654.25 seconds wall), 168/168 in 576.69 seconds (576.97 seconds wall), and 196/196 in 1430.38 seconds. The verifier retained the exact `3388b0af8b7a5d581f44abc8c6bd86ba4ca70c5f9b3ceb01182c5b51a3eee28d` digest before the partitioned campaign and after its final adjacent partition | None within this bounded regression row; the three commands partition the exact frozen inventory by whole manifest groups without file or case overlap |
| 27 | Static audits | Direct | Final root checks report 25/25 scoped Python files Ruff-formatted and lint-clean, successful Python compilation, 20/20 static-surface and inventory-verifier tests, exact 242-case direct collection in 0.84 seconds, exact 39-file/558-case inventory collection, and clean `git diff --check`. The scoped leftover review found no production placeholder/debugger marker or temporary/backup/reject artifact; the only trailing whitespace match is an existing README Markdown hard break outside the changed checkpoint. The extensive unrelated tracked/untracked shared worktree was categorized and preserved without cleanup | None within this bounded static row; a dirty shared worktree is not represented as a clean checkout |

## 4. Integrity and provenance boundary

### 4.1 What V7 currently proves

Given an independently admitted deployment expectation, V7 can verify the
signature and exact contents of the manifest subject and its starting
projection/actor/parser baseline. Given a candidate suffix, it can then verify
that the candidate is canonical and internally self-consistent: record kinds,
receipt links, actor/RAW relationships, terminal closure, schedule structure,
roots, and member digests all recompute.

### 4.2 Explicit V7 nonclaim

V7 does not provide cryptographic provenance for the post-baseline suffix. A
receipt hash chain without a signed or independently anchored final head does
not detect whole-suffix replacement: every next receipt hash is computable from
public inputs. `integrity.json` is also unsigned and therefore closes bytes but
does not establish their producer.

During this audit, the freeze was corrected to say that the receipt chain
detects omission, reordering, or replacement only when a separately trusted
final root exists, and that the artifact codec establishes suffix
self-consistency rather than issuance authenticity. The runtime short-prefix
diagnostic now says “structurally valid run-ending terminal”. V7 correctness
also rejects replay unless both
`CORRECTNESS_FINALIZER_NOT_IMPLEMENTED` and
`POST_RUN_SUFFIX_PROVENANCE_UNATTESTED` are present; the production and
alternate-suffix regressions assert that disclosure.

Those changes resolve the audit's terminology/disclosure defect without
changing the cryptographic design. The fatal-exception rule now says
“structurally authorize a short schedule under signed manifest policy”, and
the pre-attempt-stop rule says an earlier terminal cannot encode or
structurally authorize that later stop. No schedule-structure sentence now
uses “authenticate” as a synonym for post-run producer provenance.

### 4.3 Boundary that remains open by design

The four-member V7 artifact remains a local-only candidate with no signed or
externally anchored final result. This is now an explicit serialized-trust-
ceiling acceptance row and a future-publication nonclaim, not a hidden V7
acceptance promise. It cannot be closed by stronger SHA-256 checks, more
receipt links, or wording changes. The V7 manifest verifier authenticates the
manifest and independently revalidates its embedded predecessor; it does not
authenticate sample or final-root provenance.

### 4.4 Later-version signed-final-root alternative

If cryptographic post-run provenance is required, it changes the evidence
contract and belongs in a separately versioned gate. A second one-shot,
domain-separated finalization attestation should bind at least:

- V7 manifest ID and manifest-authority ID;
- projection ledger ID and signed baseline sequence/hash;
- final projection receipt sequence/hash;
- sample-stream digest, count, first/last sample IDs;
- schedule coverage, expected count, final operation sequence, and terminal ID;
- RAW, actor, and projection roots;
- exact correctness predicate/failure-code payload;
- finalization policy/version, signer key ID, retained session/writer fence,
  and finalization time/sequence; and
- a new one-shot finalizer authorization distinct from manifest signing.

The verifier must check that signature against an independently admitted key
and reject signature replay across any manifest, baseline, suffix, correctness
payload, or schedule. A signed final root blocks an arbitrary offline editor,
but by itself does not prevent an authorized signer from issuing two different
roots or rolling back to an older signed root. Uniqueness and anti-rollback
still require a durable monotonic publication record or an independently
witnessed external anchor.

## 5. Focused execution evidence

The final report must preserve both the clean result and the one environmental
rerun:

- the four core V7 files passed **89/89 in 432.36 seconds** with a short
  `--basetemp`;
- the production and trust-ceiling files passed **1/1 in 77.46 seconds** and
  **1/1 in 3.73 seconds**, respectively, so the six-file direct V7 group is
  **91/91** across file-disjoint commands on the then-current intermediate tree;
- the disjoint runner-firewall command collected and passed **12/12 in 0.36
  seconds**, producing **103 distinct V7-focused cases** without double-counting
  parameterized source functions;
- an earlier four-file run executed 89 cases as 88 passed plus one setup
  failure caused by the generated AF_UNIX/chronyd test path exceeding its
  108-byte bound;
- that exact failed node passed as 1/1 with a short explicit `--basetemp`;
- the production plus integrity-boundary pair also passed 2/2 in an earlier
  combined diagnostic run;
- the row-1 source-closure file passed **4/4 in 2.58 seconds**; the expanded
  source-focused command passed **35/35 in 4.31 seconds**, and exact direct V7
  intermediate collection reported **241 cases in 0.72 seconds**; and
- every long-path-sensitive run used a short explicit `--basetemp` so the test
  infrastructure remained inside the frozen Unix-socket path bound.

The setup-path failure occurred before the V7 test scenario and is not evidence
of a lifecycle contract failure. It must nevertheless remain visible rather
than being silently counted as a first-run pass.

### 5.1 Neutrality, compatibility, inventory, and static evidence

The rows 24 through 27 audit first produced these exact intermediate results:

- the combined neutrality, serialization, public/static-surface, inventory-
  verifier, and inherited sampler-neutrality command passed **49 cases with 17
  deselected in 1.13 seconds** (**1.41 seconds wall**);
- the exact public-compatibility command passed **7/7 in 105.50 seconds** under
  short `--basetemp=/tmp/pc7`: three legacy return/error/cancellation cases,
  one public signature/live-collector denial, and three legacy terminal-bypass
  denials;
- its preceding long-basetemp diagnostic reported **4 failed, 3 passed in
  45.31 seconds**, with all four failures occurring during fixture creation at
  the intentional 108-byte AF_UNIX query-socket headroom check. The identical
  short-path rerun above classifies these as test-path setup failures, not
  product regressions;
- the inventory verifier's own **14/14** focused tests cover successful collect
  and skip-collect plus digest, file hash, count, group, parent-path, symlink-
  escape, duplicate-key, non-finite-JSON, and scope rejection;
- intermediate inventory verification passed both skip-collection in **0.055 seconds**
  and exact **39-file / 558-case** collection in **2.148 seconds**. The 558
  cases were still pending execution at that intermediate checkpoint;
- intermediate scoped Ruff lint, Ruff format check, Python compilation, and
  `git diff --check` passed in **0.123 seconds**; and
- intermediate direct V7 collection, including the effect, neutrality, static-
  surface, and row-1 source-closure files, reported **241 cases in 0.72
  seconds**.

One early combined whole-sampler diagnostic printed nine passing progress
markers but was intentionally terminated after about 2 minutes 40 seconds
because that file includes expensive integrations. It is counted as neither a
pass nor a failure; only the later exact 49-case focused command is evidence.

The leftover review found no scoped production `TODO`, `FIXME`, `HACK`, `XXX`,
`NotImplementedError`, debugger call, temporary, backup, reject, SQLite sidecar,
or generated artifact file. The newly owned no-op sites are intentional:
Ping/Pong parsing changes no fragmentation state, and a secondary artifact-
failure latch must not mask the primary exception. Inherited no-op cleanup
handlers cover bounded descriptor/socket/process/fork cleanup and parser
non-matches; their behavior remains exercised by the adjacent matrix. The
`CORRECTNESS_FINALIZER_NOT_IMPLEMENTED` and
`POST_RUN_SUFFIX_PROVENANCE_UNATTESTED` strings are mandatory serialized
nonclaims, not forgotten implementation placeholders. The repository still
contains extensive unrelated concurrent tracked and untracked work; nothing
was deleted or cleaned from that shared worktree, and row 27 closes from the
explicit categorized final audit rather than a false clean-worktree claim.

### 5.2 Final stable-tree closure

After all implementation repairs, formatting, and audit reconciliation, the
final stable tree supplied the evidence that closes the direct and adjacent
inventories:

- the exact 12-file direct V7 inventory passed **242/242 in 1221.45 seconds**
  (**1221.75 seconds wall**);
- the exact adjacent inventory ran as three file-disjoint manifest partitions:
  Raw V6 plus A1 passed **194/194 in 653.97 seconds** (**654.25 seconds wall**),
  actor plus projection plus Linux owner passed **168/168 in 576.69 seconds**
  (**576.97 seconds wall**), and ingress plus terminal plus public denial
  passed **196/196 in 1430.38 seconds**;
- skip-collection verification before the partitioned campaign and after its
  final adjacent partition returned the invariant inventory digest
  `3388b0af8b7a5d581f44abc8c6bd86ba4ca70c5f9b3ceb01182c5b51a3eee28d`
  and the same **39 files / 558 cases**;
- all **25/25** scoped Python files passed Ruff formatting/lint checks and
  Python compilation; the combined static-surface plus inventory-verifier
  command passed **20/20 in 0.96 seconds**; direct collection returned the
  exact **242 cases in 0.84 seconds**; and exact inventory collection returned
  **39 files / 558 cases in 2.16 seconds**; and
- final `git diff --check` passed. The scoped leftover audit found no production
  placeholder/debugger marker or temporary, backup, reject, SQLite-sidecar, or
  generated-artifact residue; unrelated shared-worktree changes remained
  categorized and untouched rather than being represented as a clean checkout.

The earlier collection-only checkpoints, long-basetemp setup failures,
targeted reruns, partial commands, and terminated sampler diagnostic remain
recorded in Sections 5 and 5.1 as intermediate diagnostics. They are neither
deleted nor retroactively counted as final passes; the stable-tree results
above are the acceptance evidence.

## 6. Acceptance conclusion

Raw V7 is **locally accepted within its frozen trust ceiling**. All 27 matrix
rows now have direct final-tree evidence: the exact 242-case V7 inventory, the
complete 558-case adjacent inventory, and the stable-tree static, collection,
diff, and leftover audits all close successfully.

This is deliberately bounded local acceptance, not an expansion of the
protocol's trust claims.

The neutrality row closes only the lifecycle-on comparison baseline, not
matched physical campaigns, normalization, overhead acceptance, or full
measurement neutrality. Separately, the unsigned suffix means V7 can claim
canonical local data integrity only, not cryptographic provenance for what
happened after the signed baseline.

No A2-M completion, durable external artifact, public-live qualification,
Stage 1 exit, production readiness, or profitability claim follows from this
audit.
