# Raw V8 Step-2 V2 S1-A2 source-identity amendment

Date: 2026-08-09  
Gate: predecessor reconciliation before `S1-A3/A3-T`  
Decision: **ACCEPT CURRENT EXACT BYTES; SEMANTIC AUTHORITY UNCHANGED**

## 1. Why this amendment exists

The S1-A3 entry audit compared the committed repository files with the exact
bytes recorded by the original S1-A2 acceptance. The current preflight-A
source and its focused test did not match that record:

| Artifact | Original accepted bytes | Current bytes |
|---|---:|---:|
| Preflight A | 97,098 | 97,254 |
| Preflight A test | 14,311 | 14,159 |

The original accepted blobs are not present in repository history, so the
reason for the byte difference is not inferred. The mismatch is treated as
real source drift. It cannot be silently absorbed into the final V2 manifest.

## 2. Reconciliation method

No predecessor source, seed, contract, counting rule, F0 ceiling, rounding
unit, or expected answer vector was edited. The current committed files were
challenged as a new exact-source tuple:

1. regenerate and identity-check the accepted seed;
2. rerun the 121-test seed/boundary/security matrix;
3. rerun preflight A and its hostile checks;
4. rerun independently authored preflight B;
5. rerun the parent-owned isolated comparator; and
6. emit a fresh private comparison payload, record its identities, and remove
   the private output.

The acceptable outcome was exact semantic invariance plus a new
source-dependent comparison identity. Any changed case, metric, semantic ID,
count-vector digest, or resource rejection would have returned S1-A2 to a
versioned semantic correction.

## 3. Current exact authority tuple

| Position | Role | Raw octets | Raw SHA-256 |
|---:|---|---:|---|
| 1 | Preflight contract | 16,919 | `007ed9a8d06b91f73708129b66a33eaf525e203d306426d05b8cd8bba9c7294b` |
| 2 | Preflight A | 97,254 | `fa02fcfce55e6e7b16ef90422ac079b8e34cbc1cf2c0d8422dd8b28639ec76e7` |
| 3 | Preflight A test | 14,159 | `18c9567f8325834761d05c4d29cab605e89c75d8298e3340802989d7cc582063` |
| 4 | Preflight B | 89,474 | `de618350fc5c5c48d998de7ae49449f9edca0eff25161bde07cf271c22e47954` |
| 5 | Preflight B test | 10,963 | `ec31059b396872405963b96537ec73ef86d221a6525ab6ff4073cefc6e7fa7b0` |
| 6 | Parent comparator | 52,732 | `e0527f10a4ccb18891d18b8910101066bbc01ab57eebc2e3b18338d7c6f4f793` |
| 7 | Comparator test | 10,113 | `3ed939f99c84e951dab94d265999a41e892370308c5e9f501ade489313edd029` |

These records are now duplicated in the machine-checked
`s1_a2_snapshot` inside
[`stage1_execution_control_2026-08-08.md`](stage1_execution_control_2026-08-08.md).
The control checker rejects missing, reordered, resized, rehashed, duplicated,
or path-substituted authority files before S1-A3 work can continue.

## 4. Semantic invariance result

| Observation | Result |
|---|---|
| Ordered cases | 475, unchanged |
| Metrics per case | 18, unchanged |
| Semantic raw octets | 1,702,217, unchanged |
| Semantic raw SHA-256 | `27d583074ed3b684d969644222ce025791e85fd7f28578b1ef9ca6fd6e573081`, unchanged |
| Semantic payload ID | `d51f81fe078309ee817a4f7ab93be3891ef4fbb5aab45e41b8e0d60ce3103c1b`, unchanged |
| Count-vector SHA-256 | `a9d7cd1ce1cb0aa6dccb175a5a1c49e69f1e672e18a9b4419ccbcdfedc1f79a8`, unchanged |
| Case bytes equal | true |
| Metric summaries equal | true |
| Resource limits satisfied | true |
| Comparison status | `EXACT_AGREEMENT` |

Because the comparison payload binds the implementation source hashes, its
seal changes mechanically:

| Observation | Current value |
|---|---|
| Comparison raw octets | 1,206 |
| Comparison raw SHA-256 | `44e1572ea8a9bfd19a876e80dcb027a503f9e720389a2671d02c37bc740f9b43` |
| Comparison payload ID | `8fca05661cbf728468b442466f613b7840b9c462cb2fd55302d34569fe243256` |

## 5. Fresh verification

| Check | Result |
|---|---|
| Stage 1 control plus seed regeneration | PASS |
| Seed/boundary/security predecessor matrix | 121 passed in 15.65 s |
| Preflight A focused suite | 6 passed in 111.36 s |
| Preflight B focused suite | 6 passed in 125.95 s |
| Comparator focused/real-child suite | 8 passed in 98.23 s |
| Fresh private comparator CLI | exit 0; 1,206-byte `EXACT_AGREEMENT`; private output removed |

## 6. Decision and nonclaims

S1-A2 remains accepted for the exact current tuple above. This amendment
supersedes only the preflight-A source/test hashes and the mechanically
dependent comparison hash/ID in the original dated records. It does not alter
or reaccept any semantic rule, case result, metric, ceiling, or rounding unit.

S1-A3 remains active and `A3-T` remains next. This amendment does not accept a
final manifest, F2 authority, finalizer, constructive maximum, verifier,
producer, pilot, Raw V8 Step 2/3, Stage 1, offline Stage 2, paper/live trading,
safety, predictive edge, or profitability.
