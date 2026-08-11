# V4.9F-A2 Raw V8 Step-2 Acceptance-Coverage Audit

**Audit date:** 2026-07-25  
**Audited protocol:**
[`v4_9f_a2_marker_operation_target_v8_protocol_freeze_2026-07-22.md`](v4_9f_a2_marker_operation_target_v8_protocol_freeze_2026-07-22.md)  
**Historical result:** **Section 18 Step 2 was locally accepted for the
2026-07-25 surface. Raw V8 was not accepted.**

**Current disposition:** A breaking Step-3 audit found causally unsound V1
ingress/subscription/shutdown shapes and checkpoint/lifecycle drift. This
audit remains immutable evidence of the historical checkpoint, but it is not
current acceptance authority. The corrected Step-3 layer remains governed by:
[`v4_9f_a2_raw_v8_step3_target_and_lifecycle_correction_2026-07-26.md`](v4_9f_a2_raw_v8_step3_target_and_lifecycle_correction_2026-07-26.md).
The 2026-07-28 schema audit further rejected the lossy 27-record V1 external
registry. The exact 49-record plus three-union design is governed by
[`v4_9f_a2_raw_v8_step2_external_schema_v2_correction_2026-07-28.md`](v4_9f_a2_raw_v8_step2_external_schema_v2_correction_2026-07-28.md)
and its canonical V3 inventory is now a narrowly accepted component under
[`v4_9f_a2_raw_v8_step2_v3_inventory_acceptance_2026-08-01.md`](v4_9f_a2_raw_v8_step2_v3_inventory_acceptance_2026-08-01.md).
Full Step-2 acceptance remains NO-GO pending constructive maxima, separate
work accounting/certification, production adapters, and final compatibility.

## 1. Executive result

At the historical checkpoint, the isolated Raw V8 contract layer supplied an exact four-operation tagged
union, strict spec/result records, a reproducible 185-field typed target
registry, a 66-field operation-counter schema, typed observation envelopes,
explicit availability/censoring rules, and generated worst-case byte evidence.
It is deliberately private to its module and does not alter or export the
accepted Raw V7 implementation.

Acceptance followed a real independent NO-GO. The first adversarial review
showed that a fully rehashed `ON`/`OFF` relabel, null-attempt observations with
operation accumulators, and an operation-inapplicable stable checkpoint could
be accepted, and that the public root semantic validator lacked direct
coverage. The protocol was amended before acceptance. The final contract now
freezes and enforces:

- an exact sorted 85-field null-attempt set, including the explicit target-
  effect duration field;
- operation applicability before null-attempt and instrumentation-mode
  fallbacks;
- a complete and disjoint 58 operation-local plus 8 point/current partition
  of the 66 counter fields;
- exactly three statically available fields in `OFF`, with stable checkpoints
  forbidden and startup-recovery observations permitted;
- an exact 13-entry stable-checkpoint-to-operation map; and
- direct root-semantic validation plus exhaustive one-field-at-a-time
  null-attempt falsification.

This is a narrow design-and-contract acceptance. It does not implement the V8
projection, lifecycle, marker capability, live observers, runtime hooks,
collector, artifact, replay, campaign, calibration, or enforcement path.

## 2. Accepted artifacts and identities

The hashes below identify the exact historical 2026-07-25 snapshot. The
relative links identify repository paths whose current contents may be newer;
they are navigational only and must not be used to verify those historical
hashes. Current Step-2 status is maintained in the implementation roadmap.

| Artifact | Role | Final evidence |
|---|---|---|
| [`physical_transport_capacity_contracts_v49f_v8.py`](../../riskyieldmm/trading/physical_transport_capacity_contracts_v49f_v8.py) | Private production contract module | SHA-256 `7e46271c36bbce19ec9e5a6d413f917cfb1384c895e6f4c7bc916eb90b878632` |
| [`generate_raw_v8_step2_inventory_v49f.py`](../../scripts/tests/generate_raw_v8_step2_inventory_v49f.py) | Standard-library-only independent inventory generator | SHA-256 `db5ab299ae34d12eaf2fa19e2e825d2d3ccae3dc2f553122a600588053e52946`; never imports `riskyieldmm` |
| [`raw_v8_step2_inventory_v49f.json`](../../tests/raw_v8_step2_inventory_v49f.json) | Golden exact inventory and generated boundary evidence | File SHA-256 `218ff5dc580439c1ba57473bbcdbb2b8ceed966f6bce8b6a74918551b86acaeb`; semantic inventory SHA-256 `c8a67ca66b02d9742169205060ecb5846821eb6c95dcc9d7034eeb6280bde6a5` |
| [`_raw_v8_step2_contract_harness_v49f.py`](../../tests/_raw_v8_step2_contract_harness_v49f.py) | Isolated adversarial child harness | SHA-256 `f17b99d9d68e249db79e05543373a87add0e64d8084b2956d483a643bbeb17ba` |
| [`test_trading_physical_transport_capacity_contracts_v49f_v8_isolated.py`](../../tests/test_trading_physical_transport_capacity_contracts_v49f_v8_isolated.py) | Parent import-isolation and process-boundary tests | SHA-256 `b7dd3600ae8d274c22b36c60d72ae276971db9135e6784bc37fbf59a711c780b` |

The exact target-field registry ID is
`d09226eddb8b5f10345267132b42706dfd54dd356b434315e39aeebecc135235`.
The exact operation-counter schema ID is
`5181eb89788d511ffeb2ccc65264b81e9e0d3ae977043820524f8b08dfa58fc3`.
The registry canonical JSON is 292,259 bytes.

The generated inventory freezes:

| Quantity | Exact result |
|---|---:|
| Target fields | 185 |
| Vocabulary definitions | 25 |
| Value-constraint definitions | 17 |
| Cross-field constraint definitions | 1 |
| Value-shape definitions | 6 |
| Operation counters | 66 |
| Monotone counters | 57 |
| Nonmonotone counters | 9 |
| Null-attempt fields | 85 |
| Compact operation-local fields | 58 |
| Compact point/current fields | 8 |
| Stable checkpoint mappings | 13 |
| Statically available `OFF` fields | 3 |

The ordered 85-field null-attempt tuple has SHA-256
`dc88dcd26bc773aa48a35a47b36d352a158a84a05f6e963aaecbe057ef34193d`.
Its full 185-field `OFF` observation is 184,324 canonical bytes with SHA-256
`05bcbfeb19d71a3a0c8c74f32844c7a97c8af4fc7c7dfb0d2627ca98b7329787`.

## 3. Boundary proof

The independent generator enumerated every legal per-field representation for
each operation and selected the canonical worst case without importing the
production module:

| Operation | Legal representations | Maximum bytes | Margin below 262,144 |
|---|---:|---:|---:|
| `ACK_DEADLINE_EXPIRY` | 2,815 | 259,090 | 3,054 |
| `INGRESS` | 2,803 | 258,680 | 3,464 |
| `LOCAL_SHUTDOWN` | 2,815 | 259,085 | 3,059 |
| `SUBSCRIPTION_DISPATCH` | 2,803 | 258,694 | 3,450 |

The overall maximum is the ACK observation with SHA-256
`e856f15d9e9ce22e37ef2b24c20111d17872a7464c2330e8888fd6a0ce084c0b`.
The nested maxima are 2,548/4,096 bytes for one field observation,
1,565/3,072 for the strict value union, 183/512 for a clock span,
1,209/2,048 for an observation-context semantic preimage, and 766/2,048 for a
source-error-detail semantic preimage. No undefined generic node ceiling is
used.

## 4. Acceptance evidence

| Check | Final result |
|---|---|
| Independent inventory replay | `generate_raw_v8_step2_inventory_v49f.py --check` passed |
| Direct isolated child contract | `PASS raw-v8-step2-contracts` |
| Process-isolated pytest | 4 passed in 18.95 seconds on the root rerun; an independent final-byte rerun also passed all four |
| Lint | Ruff check passed for production, generator, harness, and isolated parent |
| Formatting | Ruff format check passed for the same four files |
| Compilation | `py_compile` passed |
| Scoped whitespace/error audit | `git diff --check` passed |
| Targeted Raw V7 compatibility | 11 non-network cases passed; the one loopback production case passed separately outside the restricted sandbox in 74.40 seconds |

The restricted-sandbox run of the production regression failed only because
the sandbox denied binding `127.0.0.1`. Re-execution with loopback permission
passed; it is recorded as an environment diagnostic, not hidden as a code
failure.

## 5. Step-2 traceability

| Acceptance area | Status | Direct evidence |
|---|---|---|
| New-domain version separation | Direct | Exact V8 domains and schema literals; V6/V7 relabels and nested substitutions reject |
| Exact operation union | Direct | Four distinct tags, four exact spec types, four exact result types, and cross-tag/spec/result mutation matrices |
| Exact scalar typing | Direct | Boolean-as-integer, integer subclasses, float/nonfinite values, unknown members, and forged dataclasses reject |
| Registry identity and replay | Direct | Independent literal parser/generator reproduces all 185 ordered descriptors and the registry semantic ID |
| Value, error, and context unions | Direct | Every strict value shape, source-error form, clock span, context member, byte ceiling, and semantic-ID preimage is exercised |
| Mode semantics | Direct | Rehashed `ON`/`OFF` relabels reject; `OFF` and `ON` availability rules are exact |
| Null-attempt semantics | Direct | Exact 85-field tuple; full valid control; every field restored to an attempted donor one at a time rejects |
| Checkpoint applicability | Direct | All 13 checkpoints are tested against all four operations; ingress-only markers cannot be attached to ACK or another tag |
| Root semantic validation | Direct | The public-in-module root validator is invoked on valid and forged nested observations |
| Counter schema | Direct | Exact 66-field identity, 57/9 monotonic partition, and complete 58/8 compact-coordinate partition |
| Canonical byte bounds | Direct | Independent exhaustive legal-representation generator proves every per-operation and nested maximum |
| Import/public isolation | Direct | Fresh `python -I -B` child, AST import audit, package export audit, and public-name disjointness |
| Raw V7 compatibility | Direct | V7 production module remains unchanged; all 12 selected compatibility cases pass |

## 6. Nonclaims and next gate

Step 2 does not establish:

- durable candidate, attempt, terminal, marker-closure, locator, or receipt
  semantics;
- transaction atomicity, commit-acknowledgement resolution, startup orphan
  recovery, or no-retry process-loss behavior;
- marker-ring, probe, extrema, observer-firewall, A1, TLS, kernel, parser,
  actor, SQLite, process, GC, freshness, or control runtime evidence;
- a V8 collector, four-member artifact, independent replay, correctness
  finalizer, isolated campaign, or atomic publisher;
- neutrality, acceptable overhead, calibrated thresholds, A2-E enforcement,
  public-live authority, Stage 1 exit, production readiness, edge, or
  profitability.

The active gate is Section 18 Step 3: introduce V8 candidate, attempt, terminal,
and marker-closure projection records and typed tables; bind their receipts and
relations; atomically commit candidate plus open locator and terminal plus
closure plus locator deletion; replay candidate-to-attempt state; and recover
every startup orphan conservatively without retrying the target effect. Raw V7
tables, codecs, and accepted semantics must remain unchanged.
