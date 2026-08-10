# Raw V8 Step-2 V2 implementation fail-first acceptance

Date: 2026-08-09  
Gate: `S1-A4/A4-T`  
Decision: **FAIL-FIRST TARGET ACCEPTED — `A4-V` NEXT**

## 1. Decision

`A4-T` is accepted. The independent test authority is
[`test_raw_v8_step2_maximum_protocol_v2_implementation_fail_first_v49f.py`](../../tests/test_raw_v8_step2_maximum_protocol_v2_implementation_fail_first_v49f.py).
It was frozen before any of the three implementation paths existed and imports
none of them.

The observed full fail-first result is exactly:

```text
50 passed, 11 skipped, 3 failed
```

The three failures are exclusively:

```text
A4_T_INDEPENDENT_VERIFIER_MISSING
A4_T_SEPARATE_PRODUCER_MISSING
A4_T_PARENT_PILOT_RUNNER_MISSING
```

The passing-only selection is:

```text
50 passed, 11 skipped, 3 deselected
```

No implementation was added to obtain this state. `A4-V` may now implement
only the independent verifier against the frozen target. The producer and
runner remain absent.

## 2. Why this gate is necessary

Implementing a verifier and then writing tests around its output would let the
implementation define its own acceptance target. A source-only test would be
too weak because a correctly named stub could satisfy path, import, marker,
and invalid-CLI assertions without proving P1, P2, or P3.

The accepted test therefore freezes three layers before implementation:

1. closed data and identity contracts;
2. source, import, process, and CLI isolation; and
3. externally observable positive and negative behavior.

This does not prove the future verifier correct. It prevents several circular
or under-specified implementation paths and supplies a stable first target for
independent-verifier development.

## 3. Frozen authority and schema oracles

The suite independently binds:

- constructive boundary ID
  `bdc7363ae28dfe9a1c1dc132808cb1bd4a06c409201cd49b31e394893142a7ed`;
- seed ID
  `ac22151fa74702ac1488924f01161eaa38574545e6272a290db6b0bbd288ae5f`;
- finalization-manifest ID
  `edde204e98ed1caeeb8ae270487d85e39a2168e0a3692ce1d8748d2d8e7fd858`;
- downstream physical protocol hash
  `0136fba014287605336193f782b4885f16e0163000d36429ceb0dfaf0cea52e0`;
- exact verifier, producer, and runner paths and source markers; and
- the six fixed pilot case/plan bindings.

Independent schema oracles cover both candidate alternatives, maximum and
local result artifacts, upper-bound certificates, all 18 resource
measurements, verification receipts, role authorities, and the complete
six-case pilot manifest. Every identity is recomputed from its frozen domain
and preceding payload.

The in-memory maximum/local result objects are explicitly shape fixtures, not
claimed semantic attainers. They cannot be published as evidence.

## 4. Hostile coverage

Passing hostile tests reject:

- duplicate, floating, non-finite, BOM, or invalid-UTF-8 JSON;
- changed boundary, seed, manifest, case, plan, binding, or semantic identity;
- unknown candidate tags and producer proof/resource claims;
- missing resource reports, wrong protocol hashes, and changed result IDs;
- changed candidate/result receipt hashes, producer-asserted PASS, path escape,
  unknown receipt members, and changed receipt identity;
- duplicate/wrong pilot cases, plan drift, role collision, publication status,
  unknown pilot members, and changed pilot identity;
- forbidden imports, dynamic code, shell/process bypass, producer/verifier
  cross-reading, hard-coded producer F2 answers, and role-marker collision; and
- accepted output after a hostile verifier candidate.

All source fixtures are static AST inputs. They are not executable substitute
implementations.

## 5. Frozen functional target

The independent positive control is case position 5,
`CapacityMeasurementBoolValueV1`. From the accepted external schema, its legal
maximum witness is fixed before implementation as:

```json
{"kind":"BOOL","value":false}
```

`false` is one canonical byte longer than `true`. The verifier target must:

1. accept the closed candidate through the exact isolated CLI;
2. emit only the closed maximum-result, receipt, and empty context root;
3. independently derive the type/case/plan and all identities;
4. prove that canonical witness length equals its certified upper bound;
5. bind the exact witness SHA-256;
6. emit all 18 ordered, name-correct, F2-bounded resource measurements; and
7. leave candidate bytes unchanged.

Three separately resealed hostile candidate classes must fail with no accepted
output root: invalid candidate identity, forbidden producer certificate claim,
and changed case binding.

The separately frozen producer target must emit exactly the same legal case-5
candidate without a proof, resource, bound, PASS, or verifier-derived claim.
Its implementation remains prohibited until `A4-V` is accepted and `A4-P`
becomes next.

## 6. Source and CLI boundary

Verifier and producer sources must use only the boundary allowlist, contain
their distinct source marker, avoid every forbidden import/dynamic-code root,
avoid process-launch primitives, avoid the other role path/marker, and remain
standalone. The producer additionally cannot contain forbidden proof-field
constants or hard-coded large F2 values.

Only the runner may use the fixed `fork`, `setrlimit`, `execve`, and `wait4`
surface. `subprocess`, shell calls, network imports, production `riskyieldmm`,
predecessor `scripts`/`tests`, reflection, serialization shortcuts, and host
Unicode authority remain prohibited.

Each role has one exact invalid-invocation diagnostic prefix, exit code 2,
empty stdout, and one bounded stderr line. Success remains silent.

## 7. Exact artifact identity

| Artifact | Exact value |
|---|---:|
| Fail-first test raw octets | 52,970 |
| Fail-first test raw SHA-256 | `10058dabf6b868969a5cad8387ecedbfa42a0e59f6e5a922adffd9cf99c24080` |
| Passing contract/hostile cases | 50 |
| Implementation-dependent skips | 11 |
| Intended missing-path failures | 3 |
| Unexpected failures | 0 |
| Full predecessor/boundary/control matrix | 213 passed in 378.12 seconds |
| Seed exact regeneration | passed; 13,419,905 byte-identical bytes |
| Finalization-manifest exact regeneration | passed; exit 0 |
| Ruff format/check, compilation, diff check | passed |
| Changed-document relative links | 242 checked across 10 files; all resolved |
| Temporary/partial/backup protocol leftovers | none |

## 8. State transition

```text
A4-B0  remains ACCEPTED
A4-T   NEXT -> ACCEPTED
A4-V   WAITING -> NEXT
S1-A4  remains ACTIVE
Stage 1 remains NO-GO
offline Stage 2 remains BLOCKED on S1-R0
paper/live remains BLOCKED on S1-X
```

`A4-V` must implement only
`scripts/tests/verify_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py`.
It must turn the verifier-specific missing-path failure and verifier-dependent
skips into passes without changing this test, the boundary, S1-A3 authority,
F2, producer path, or runner path. A stub that only passes the source/invalid-
CLI tests does not close `A4-V`; the legal case-5 and resealed-hostile
functional tests must also pass.

## 9. Nonclaims

This checkpoint does not implement or accept the verifier, producer, or
runner; run the pilot; prove any published maximum; accept local case 475;
complete all 475 results, Raw V8 Step 2/3, A2-M/A2-E, or Stage 1; unlock
offline Stage 2 or paper/live trading; establish predictive edge, trading
safety, or profitability.
