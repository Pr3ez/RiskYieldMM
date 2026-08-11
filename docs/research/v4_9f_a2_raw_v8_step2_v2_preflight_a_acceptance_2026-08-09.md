# Raw V8 Step-2 V2 preflight A acceptance

Date: 2026-08-09  
Status: **ACCEPTED A2-A ONLY — A2-B AND DUAL AGREEMENT PENDING**

## 1. Decision

The first S1-A2 implementation is accepted as the frozen iterative counter
candidate. It consumes only the identity-pinned V2 seed, independently
interprets the catalog-carried cell-transfer AST, constructs the complete
event stream for every one of the 475 plans, enforces all 18 immutable F0
per-case and full-run ceilings, and publishes one fail-closed semantic payload.

This acceptance closes `A2-A`. It does not accept the metric vector as true by
itself. Truth still requires a separately authored `A2-B`, isolated execution,
and exact A/B comparison under `A2-C` and `A2-E`.

## 2. Frozen artifacts

| Artifact | Raw octets | Raw SHA-256 |
|---|---:|---|
| `scripts/tests/preflight_raw_v8_step2_maximum_protocol_v2_a_v49f.py` | 97,098 | `beaf9405b7281508c046ad4d0735a70971ea4121c27fadb92d6b6401ccfe9d25` |
| `tests/test_raw_v8_step2_maximum_protocol_v2_preflight_a_v49f.py` | 14,311 | `54e73acc5486d09dff9e56bb8456a85d40c96f18cb21ca2a6d7bb2d86a1dedfd` |

The source marker is `ITERATIVE_CATALOG_INTERPRETER_V1`. The implementation
imports only `hashlib`, `json`, `os`, `pathlib`, and `sys`; it does not import
the seed generator, repository modules, the future B implementation, or test
helpers.

## 3. Deterministic result

Two isolated-style invocations using Python `-I -S -B` produced identical
canonical-pretty bytes:

| Observation | Value |
|---|---:|
| Cases | 475 |
| Metrics per case | 18 |
| Semantic result raw octets | 1,702,217 |
| Semantic result raw SHA-256 | `27d583074ed3b684d969644222ce025791e85fd7f28578b1ef9ca6fd6e573081` |
| Semantic payload ID | `d51f81fe078309ee817a4f7ab93be3891ef4fbb5aab45e41b8e0d60ce3103c1b` |
| Semantic count-vector SHA-256 | `a9d7cd1ce1cb0aa6dccb175a5a1c49e69f1e672e18a9b4419ccbcdfedc1f79a8` |

The result is deliberately not checked into the repository. The future
comparator owns private result directories, execution envelopes, and final
comparison publication.

## 4. Full-run measurements reported by A

These values are candidate results awaiting independent B agreement:

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

Every reported per-case and full-run value is at or below its frozen seed F0
ceiling. No ceiling was changed or tuned.

## 5. Acceptance evidence

```bash
python -m py_compile \
  scripts/tests/preflight_raw_v8_step2_maximum_protocol_v2_a_v49f.py

ruff check \
  scripts/tests/preflight_raw_v8_step2_maximum_protocol_v2_a_v49f.py \
  tests/test_raw_v8_step2_maximum_protocol_v2_preflight_a_v49f.py

pytest -q \
  tests/test_raw_v8_step2_maximum_protocol_v2_preflight_a_v49f.py
```

Observed result:

```text
py_compile: PASS
ruff: All checks passed
pytest: 6 passed in 111.65s
```

The tests independently prove source/import separation, closed payload and
case identities, the count-vector seal, plan-derived M1-M7 and M12-M16
reconciliation, 18 full-run summaries, deterministic bytes, and no-overwrite
failure without a partial output.

The three seed hand oracles are not expected to equal these full-scale case
results. They are the bounded discriminating microfixtures required by the
event-grammar design; the design assigns complete 475-case stream comparison
to A and B.

## 6. Falsifications resolved during implementation

1. The frozen transfer catalog contains 55 primitive opcodes, not the earlier
   provisional count of 54. A now requires exactly 55.
2. JSON object key order cannot represent semantic parameter order because
   canonical serialization sorts keys. A checks exact parameter membership
   and reconstructs the catalog-declared order before rule execution.
3. Constructor value-source literal `null` is a typed null value, not an
   unresolved context locator.
4. The amended full local program emits 12 state cells and 12 cache keys, uses
   11 one-to-one transitions, aggregates 11 descriptor occurrences, and has
   maximum iteration depth 11. The terminal-only hand microfixture must not be
   substituted for this full case.

## 7. Remaining limitations and nonclaims

- Generic profile P2 cells are structural superset bounds. The seed explicitly
  makes no generic P2 attainability claim.
- A validates the closed P1/P3 program and its plan/schedule bindings, but the
  seed does not contain retained witness bytes. A therefore does not claim an
  independent generic witness proof.
- A is one implementation. Its candidate vector may still contain a common
  interpretation error and is not accepted until B agrees exactly.
- Parent-owned `wait4` CPU/RSS/wall/storage enforcement belongs to the future
  comparator and has not been accepted here.
- This record does not accept A2-B, A2-C, A2-E, S1-A2, S1-A3, a constructive
  maximum, Raw V8 Step 2, Stage 1, Stage 2, paper/live trading, safety,
  predictive edge, or profitability.

## 8. Next bounded action

Author `A2-B` from the frozen seed and boundary contract using the distinct
`FLAT_LEDGER_PREFIX_SUM_V1` architecture. It must not import, copy, translate,
or inspect A's result vector. Only after B independently emits its payload may
the comparator test exact equality.
