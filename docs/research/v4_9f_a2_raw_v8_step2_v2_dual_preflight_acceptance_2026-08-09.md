# Raw V8 Step-2 V2 dual-preflight acceptance

Date: 2026-08-09  
Decision: **GO FOR S1-A2 ONLY — ACTIVATE S1-A3 FINAL V2 FREEZE**

## 1. Accepted boundary

S1-A2 is accepted. Two separately authored counting-only implementations
consume the same identity-pinned 13,419,905-byte V2 seed, independently derive
all 475 ordered case records and all 18 resource metrics, and emit the same
1,702,217-byte semantic payload. A parent-owned comparator proves source
separation, executes both programs under immutable process/resource controls,
validates each report without repair, and atomically publishes
`EXACT_AGREEMENT`.

This is the packet-local final acceptance formerly abbreviated `A2-E` in the
S1-A2 work list. It is not the transport-wide A2-E enforcement milestone under
`S1-A8`; that later milestone remains unimplemented and unaccepted.

The accepted claim is deliberately narrow:

```text
for the frozen S1-A1 seed and S1-A2 contract,
independent A and B counting architectures produce exactly the same
475-case / 18-metric semantic result within every immutable F0 ceiling
under the parent-owned isolated execution boundary
```

## 2. Frozen authority and executable bytes

| Artifact | Raw octets | Raw SHA-256 |
|---|---:|---|
| V2 seed catalog | 13,419,905 | `a75a2f352e8513b7ff0043693a0c65ebbf4bc6f06859354789af69e1162b0e4f` |
| S1-A2 data contract | 16,919 | `007ed9a8d06b91f73708129b66a33eaf525e203d306426d05b8cd8bba9c7294b` |
| Preflight A | 97,098 | `beaf9405b7281508c046ad4d0735a70971ea4121c27fadb92d6b6401ccfe9d25` |
| Preflight A tests | 14,311 | `54e73acc5486d09dff9e56bb8456a85d40c96f18cb21ca2a6d7bb2d86a1dedfd` |
| Preflight B | 89,474 | `de618350fc5c5c48d998de7ae49449f9edca0eff25161bde07cf271c22e47954` |
| Preflight B tests | 10,963 | `ec31059b396872405963b96537ec73ef86d221a6525ab6ff4073cefc6e7fa7b0` |
| Parent comparator | 52,732 | `e0527f10a4ccb18891d18b8910101066bbc01ab57eebc2e3b18338d7c6f4f793` |
| Comparator tests | 10,113 | `3ed939f99c84e951dab94d265999a41e892370308c5e9f501ade489313edd029` |

Semantic authority identities remain:

| Authority | Identity |
|---|---|
| Seed catalog | `ac22151fa74702ac1488924f01161eaa38574545e6272a290db6b0bbd288ae5f` |
| Preflight contract | `6609ad7b9abf21432136e49af178e20c17cb7bc27d3b444a4b6f01a17073fc76` |
| Protocol counting semantics | `34f6c285e1ce5c2b0496a63f6eda3ee15f72d6268f5ba9dbb0748e01e61d38fb` |

## 3. Independence decision

The implementations are separate in both physical source and algorithm:

| Property | A | B |
|---|---|---|
| Marker | `ITERATIVE_CATALOG_INTERPRETER_V1` | `FLAT_LEDGER_PREFIX_SUM_V1` |
| Principal execution shape | iterative catalog interpreter and per-case event construction | typed work stack, flat event ledger, ordered prefix reduction |
| Source SHA-256 | `beaf9405...` | `de618350...` |
| Shared executable helper | none | none |
| Shared material | frozen seed and data-only contract | frozen seed and data-only contract |

The comparator proves distinct device/inode pairs and hashes, closed
standard-library imports, no local/dynamic/network/process helper imports, no
other repository source path in either child, exact marker presence, and
pre/post-execution source stability.

Review independence in this packet is executable rather than organizational:
the two algorithms, their focused reconciliation tests, and the parent
comparator challenge one another on frozen bytes. This record does not claim a
third-party or external certification.

## 4. Exact semantic result

| Observation | Accepted value |
|---|---|
| Ordered cases | 475 |
| Measurements per case | 18 |
| Semantic raw octets | 1,702,217 |
| Semantic raw SHA-256 | `27d583074ed3b684d969644222ce025791e85fd7f28578b1ef9ca6fd6e573081` |
| Semantic payload ID | `d51f81fe078309ee817a4f7ab93be3891ef4fbb5aab45e41b8e0d60ce3103c1b` |
| Count-vector SHA-256 | `a9d7cd1ce1cb0aa6dccb175a5a1c49e69f1e672e18a9b4419ccbcdfedc1f79a8` |
| Complete semantic bytes equal | true |
| All 475 case records equal | true |
| All 18 summaries equal | true |

The accepted full-run measurement vector is:

| M | Full-run value | Maximum case value |
|---:|---:|---:|
| 1 | 475 | 1 |
| 2 | 29,189,597 | 2,101,890 |
| 3 | 66,119 | 158 |
| 4 | 417,528 | 1,002 |
| 5 | 170,915,620 | 4,204,335 |
| 6 | 1,735 | 20 |
| 7 | 66,119 | 158 |
| 8 | 44,461,267 | 106,427 |
| 9 | 329,067,149 | 789,383 |
| 10 | 367,039,374 | 880,113 |
| 11 | 619,175,993 | 1,481,221 |
| 12 | 4,160 | 10 |
| 13 | 4,198,492 | 48,649 |
| 14 | 46,268 | 569 |
| 15 | 17 | 17 |
| 16 | 569 | 569 |
| 17 | 54,297 | 54,297 |
| 18 | 15,585,644 | 37,195 |

No expected per-case vector was added to the seed or shared contract, and no
F0 ceiling was changed after observing these results.

## 5. Comparator and resource result

The final canonical comparison payload is stable across repeated final-source
CLI runs:

| Observation | Accepted value |
|---|---|
| Status | `EXACT_AGREEMENT` |
| Raw octets | 1,206 |
| Raw SHA-256 | `1c09d456294f4c7271f9513c2ebac5de02324e60365ff29f26609482bdd6a8b0` |
| Comparison payload ID | `e5c8d49f7434f1f295c77dc7c625508d798f7ac872eacf0ff4c0ce0e18768c8d` |
| All resource limits satisfied | true |

One final telemetry capture observed:

| Observation | A | B | F0 ceiling |
|---|---:|---:|---:|
| Wall ns | 55,499,309,063 | 42,677,045,446 | 14,400,000,000,000 |
| CPU ns | 55,475,453,000 | 42,662,703,999 | 28,800,000,000,000 |
| Peak RSS octets | 107,794,432 | 121,065,472 | 2,147,483,648 |
| Temporary storage octets | 1,703,936 | 1,703,936 | 4,294,967,296 |
| Semantic output octets | 1,702,217 | 1,702,217 | `< 16,777,216` |
| Stdout / stderr octets | 0 / 0 | 0 / 0 | 1,048,576 each |
| Exit code | 0 | 0 | 0 |

Execution telemetry is explicitly nonsemantic and may vary on later runs.

## 6. Fresh acceptance matrix

| Check | Result |
|---|---|
| Stage 1 control script | PASS |
| Stage 1 control pytest | 1 passed in 3.58 s |
| Seed generator `--check` | exact 13,419,905-byte reproduction |
| S1-A1 plus boundary/security matrix | 121 passed in 16.54 s |
| Preflight A focused suite | 6 passed in 112.99 s |
| Preflight B focused suite | 6 passed in 125.69 s |
| Comparator focused/real-child suite | 8 passed in 100.59 s |
| Comparator final CLI | exit 0; empty stdout/stderr; one mode-0600 output |
| Repeated comparison bytes | exact |
| Ruff check and format check | PASS |
| Python compile | PASS |
| Scoped `git diff --check` | PASS |

The 121-test predecessor command contains the originally accepted 108 seed
tests plus 13 later preflight-boundary/security tests. The historical 108-test
S1-A1 acceptance value therefore remains true; the current combined matrix is
strictly larger.

## 7. Falsifications retained as evidence

The work did not proceed by first-pass confirmation. Differential execution
found and corrected four B-only defects without changing A or the authority:

1. an overstrict absolute-path requirement;
2. null ordinary retention-step metadata;
3. an obsolete root-retention phase name; and
4. local result-cell hashes in state rather than canonical cache-key order.

Comparator review additionally closed source drift around execution,
kill-and-reap cleanup after parent observation failure, and rollback after a
post-link publication failure. These corrections were followed by fresh
final-byte tests.

## 8. Scoped leftovers and state transition

No semantic output, execution envelope, or staging directory is checked into
the repository. Temporary acceptance outputs are external `/tmp` evidence and
are removed after recording their hashes. The repository still contains a
large mixed set of earlier Stage 1 and unrelated user changes; this acceptance
does not classify, stage, commit, discard, or clean them.

The canonical transition is:

```text
S1-A2  ACTIVE -> ACCEPTED
S1-A3  WAITING -> ACTIVE
Stage 1 remains NO-GO
offline Stage 2 remains BLOCKED on S1-R0
paper/live remains BLOCKED on S1-X
```

## 9. Nonclaims

This acceptance does not freeze final V2/F1/F2 authority, prove a constructive
maximum, generate any maximum witness, accept Raw V8 Step 2 or Step 3, accept
the transport-wide A2-M/A2-E milestones, complete Stage 1, unlock offline
Stage 2, authorize paper/live trading, establish provider behavior, prove
predictive edge, ensure trading safety, or demonstrate profitability.

## 10. Next bounded action

Execute `S1-A3`: produce one final identity-bound V2 protocol/F1/F2 freeze from
the accepted S1-A1/S1-A2 bytes, prove that no semantic or limit drift was
introduced, and repeat both independent preflights plus the comparator against
that final authority. No verifier, producer, pilot, or constructive maximum is
authorized until S1-A3 closes.
