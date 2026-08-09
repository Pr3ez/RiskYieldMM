# Raw V8 Step-2 V2 preflight B acceptance

Date: 2026-08-09  
Status: **ACCEPTED A2-B ONLY — PARENT-OWNED COMPARATOR AND A2-E PENDING**

## 1. Decision

The second S1-A2 implementation is accepted as the frozen independent
flat-ledger candidate. It consumes the same identity-pinned V2 seed as A, but
uses an explicitly different execution shape:

```text
typed work-stack transfer evaluator
  -> independently compiled templates and profile programs
  -> flat ordered event ledger
  -> one prefix reduction over ledger events
  -> M1 through M18 case records and full-run summaries
```

The source marker is `FLAT_LEDGER_PREFIX_SUM_V1`. B does not import A, the
seed generator, repository modules, test helpers, or an expected result
vector. Its semantic payload is byte-for-byte identical to A's independently
emitted payload across all 475 case records and all 18 metric summaries.

This closes `A2-B`. It does not close `A2-C`, `A2-E`, or `S1-A2`: the two
programs still require parent-owned isolated execution, source-separation
enforcement, immutable resource measurements, and final read-only acceptance.

## 2. Frozen artifacts

| Artifact | Raw octets | Raw SHA-256 |
|---|---:|---|
| `scripts/tests/preflight_raw_v8_step2_maximum_protocol_v2_b_v49f.py` | 89,474 | `de618350fc5c5c48d998de7ae49449f9edca0eff25161bde07cf271c22e47954` |
| `tests/test_raw_v8_step2_maximum_protocol_v2_preflight_b_v49f.py` | 10,963 | `ec31059b396872405963b96537ec73ef86d221a6525ab6ff4073cefc6e7fa7b0` |

The implementation imports only `hashlib`, `json`, `os`, `pathlib`, and
`sys`, all from the frozen standard-library allowlist. Static tests reject
local imports, dynamic execution, forbidden dependencies, source reads of A,
and a missing or altered algorithm marker.

## 3. Exact independent agreement

Fresh A and B invocations using Python `-I -S -B` produced these common
semantic bytes:

| Observation | Common value |
|---|---:|
| Ordered case records | 475 |
| Measurements per case | 18 |
| Semantic payload raw octets | 1,702,217 |
| Semantic payload raw SHA-256 | `27d583074ed3b684d969644222ce025791e85fd7f28578b1ef9ca6fd6e573081` |
| Semantic payload ID | `d51f81fe078309ee817a4f7ab93be3891ef4fbb5aab45e41b8e0d60ce3103c1b` |
| Semantic count-vector SHA-256 | `a9d7cd1ce1cb0aa6dccb175a5a1c49e69f1e672e18a9b4419ccbcdfedc1f79a8` |

The equality check compared the complete canonical-pretty byte sequences. It
did not normalize, merge, repair, round, reorder, or selectively compare
fields.

## 4. Common full-run measurement vector

| M | Metric | Aggregation | Full-run value | Maximum case value |
|---:|---|---|---:|---:|
| 1 | `SCOPE_CASE_COUNT` | sum | 475 | 1 |
| 2 | `LOGICAL_DESCRIPTOR_OCCURRENCE_COUNT` | sum | 29,189,597 | 2,101,890 |
| 3 | `RECURRENCE_STATE_ENTRY_COUNT` | sum | 66,119 | 158 |
| 4 | `RECURRENCE_TRANSITION_ATTEMPT_COUNT` | sum | 417,528 | 1,002 |
| 5 | `LOGICAL_UNBATCHED_TRANSITION_EQUIVALENT_COUNT` | sum | 170,915,620 | 4,204,335 |
| 6 | `RECURRENCE_BATCH_APPLICATION_COUNT` | sum | 1,735 | 20 |
| 7 | `CACHE_ENTRY_COUNT` | sum | 66,119 | 158 |
| 8 | `CACHE_KEY_CANONICAL_OCTETS` | sum | 44,461,267 | 106,427 |
| 9 | `DERIVATION_CANONICALIZATION_INPUT_OCTETS` | sum | 329,067,149 | 789,383 |
| 10 | `DERIVATION_CANONICALIZATION_OUTPUT_OCTETS` | sum | 367,039,374 | 880,113 |
| 11 | `DERIVATION_HASH_PREIMAGE_OCTETS` | sum | 619,175,993 | 1,481,221 |
| 12 | `INTRINSIC_RULE_EVALUATION_COUNT` | sum | 4,160 | 10 |
| 13 | `CROSS_RULE_EVALUATION_COUNT` | sum | 4,198,492 | 48,649 |
| 14 | `APPLICATION_EVALUATION_COUNT` | sum | 46,268 | 569 |
| 15 | `MAXIMUM_DERIVATION_DEPTH` | maximum | 17 | 17 |
| 16 | `MAXIMUM_ITERATION_DEPTH` | maximum | 569 | 569 |
| 17 | `PEAK_RETAINED_DERIVATION_OCTETS` | maximum | 54,297 | 54,297 |
| 18 | `DERIVATION_RESULT_CANONICAL_OCTETS` | sum | 15,585,644 | 37,195 |

Every per-case and full-run value remains within the immutable F0 ceilings.
No ceiling or semantic rule was changed to obtain agreement.

## 5. Acceptance evidence

```bash
ruff format \
  scripts/tests/preflight_raw_v8_step2_maximum_protocol_v2_b_v49f.py \
  tests/test_raw_v8_step2_maximum_protocol_v2_preflight_b_v49f.py

ruff check \
  scripts/tests/preflight_raw_v8_step2_maximum_protocol_v2_b_v49f.py \
  tests/test_raw_v8_step2_maximum_protocol_v2_preflight_b_v49f.py

ruff format --check \
  scripts/tests/preflight_raw_v8_step2_maximum_protocol_v2_b_v49f.py \
  tests/test_raw_v8_step2_maximum_protocol_v2_preflight_b_v49f.py

python -m py_compile \
  scripts/tests/preflight_raw_v8_step2_maximum_protocol_v2_b_v49f.py \
  tests/test_raw_v8_step2_maximum_protocol_v2_preflight_b_v49f.py

pytest -q \
  tests/test_raw_v8_step2_maximum_protocol_v2_preflight_b_v49f.py
```

Observed result:

```text
ruff check: All checks passed
ruff format --check: 2 files already formatted
py_compile: PASS
pytest: 6 passed in 125.69s
exact manual A/B comparison: EXACT_BYTES_EQUAL
```

The focused suite proves source separation, strict input authority, complete
475-case and 18-metric schema/identity closure, deterministic output,
no-overwrite behavior, and independent reconciliation against seed-bound
plans and metric programs.

## 6. Differential falsifications resolved

The first whole-payload comparison exposed four defects in B. Each was fixed
in B without modifying A, the seed, the contract, or any F0 ceiling:

1. B incorrectly required an absolute seed argument even though the frozen
   policy requires any argument that resolves without symlinks to the sole
   authorized path.
2. Ordinary per-step retention events carried a null step position instead of
   the current logical step position.
3. Root-retention events used an obsolete hand-oracle phase name rather than
   the frozen full-case `DEPTH_AND_RETENTION_FINALIZATION` phase.
4. The local controller's 12 result-cell hash preimages followed state order
   instead of canonical cache-key order.

After those corrections, every case and metric matched exactly. These
failures are useful evidence that the implementations exercised different
paths rather than merely duplicating one report.

## 7. Remaining limitations and nonclaims

- Exact agreement is strong evidence against implementation-specific counting
  errors, but two programs can still share a mistaken interpretation of the
  same frozen authority.
- The manual equality run did not provide the frozen parent-owned `wait4`
  CPU/RSS/wall/storage envelopes. That belongs to `A2-C`.
- Generic P2 cells remain structural superset bounds; neither implementation
  invents a generic retained-witness attainment proof.
- This record does not accept `A2-C`, `A2-E`, `S1-A2`, `S1-A3`, a constructive
  maximum, Raw V8 Step 2/3, Stage 1, Stage 2, paper/live readiness, trading
  safety, predictive edge, or profitability.

## 8. Next bounded action

Implement the fixed-path `A2-C` comparator. It must statically prove source
separation, launch A and B through `fork -> setrlimit -> execve` with Python
`-I -S -B`, measure resources through parent-owned `wait4`, validate each
closed semantic payload and execution envelope independently, require exact
payload bytes, and atomically publish only `EXACT_AGREEMENT` or fail closed.
