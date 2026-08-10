# Raw V8 Step-2 V2 independent verifier acceptance

**Date:** 2026-08-09  
**Gate:** `S1-A4 / A4-V`  
**Decision:** `ACCEPTED — BOUNDED CASE-5 VERIFIER SLICE`  
**Formal Stage 1 state:** `NO-GO`

## 1. What this checkpoint accepts

This checkpoint accepts the first independent constructive verifier at:

```text
scripts/tests/verify_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py
```

The accepted `A4-V` exit is deliberately bounded to the fail-first target that
preceded it. The verifier accepts only case position 5,
`CapacityMeasurementBoolValueV1`, and rejects every other case as
`UNSUPPORTED_CASE`. Coverage for cases 24, 54, 69, 435, and 475 belongs to the
later `A4-P6` gate; complete 475-case coverage belongs to `A4-R475`.

Within that bounded slice, the verifier does not trust a producer assertion.
It independently:

1. loads and identity-checks the constructive boundary, final seed, final F2
   manifest, all 17 seed authorities, the retained V1-rejection authorities,
   and its own source snapshot before opening the candidate;
2. enforces direct regular single-link inputs, strict bounded I-JSON, exact
   candidate-root closure, canonical physical encoding, candidate identity,
   case binding, plan binding, and absence of verifier-owned producer claims;
3. derives the case-5 legal domain from the frozen finite-text, Boolean,
   record-fold, and codec-intersection transfer programs;
4. validates the retained witness `{"kind":"BOOL","value":false}` and proves
   that its 29 compact-canonical octets attain the independently derived upper
   bound of 29;
5. reconstructs the frozen full-case logical-event stream and all 18 semantic
   resource measurements from the seed-bound constructor and metric programs;
6. derives constraint-scope, row-context, certificate, resource-report,
   result, and receipt identities without reading producer code or output; and
7. rechecks candidate, authority, and verifier-source snapshots before
   publishing an absent output root from a private mode-0700 staging root.

The producer and parent pilot runner remain absent.

Frozen implementation identities:

| Artifact | Raw octets | Raw SHA-256 |
|---|---:|---|
| `scripts/tests/verify_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py` | 94,839 | `bd81e47b0c07dc82f28a8d02e536329446267290c4e0e41c6e5fb96fd5c356a7` |
| `tests/test_raw_v8_step2_maximum_protocol_v2_independent_verifier_v49f.py` | 13,851 | `c8b2c3380701b362251af1e4f6d331d9421ac64c6fe4fe635c7e719be6ac0bbe` |

## 2. Exact case-5 result

The legal maximum witness is:

```json
{"kind":"BOOL","value":false}
```

The four postorder cells are:

| Step | Frozen transfer | Lower | Upper |
|---:|---|---:|---:|
| 1 | finite text `"BOOL"` | 6 | 6 |
| 2 | full Boolean domain | 4 | 5 |
| 3 | two-member record fold | 28 | 29 |
| 4 | `LE 3072` codec intersection | 28 | 29 |

The true-valued record is legal but serializes to 28 octets, so it is rejected
as a non-attainer. Integer `0` is not accepted as a Boolean. Wrong tags and
unknown record members also reject.

Exact derived identities and evidence:

| Item | Accepted value |
|---|---|
| Constraint-scope ID | `8026c41df78db04ff509a6f538c5fba49500b4aeec82e2e889cf2b9c00314836` |
| Row-context-closure ID | `9be77803a487774344ce9785f71b5d13258b8d2dfc0d7e982a329921af3e5e2b` |
| Event-stream SHA-256 | `79375d5ecab2af215e9259524c7f16b41a2b5737cda7f5897a3cd6c272c0b314` |
| F2 resource-limit catalog ID | `17a2258cde720b2868e9bb538fbd3d702c299a0db7d8fb5215938578d217d0fe` |
| Certified maximum | `29` octets |
| Codec slack | `3043` octets under `LE 3072` |

The exact ordered 18-metric vector is:

```text
[1, 3, 4, 8, 8, 0, 4, 2684, 8104, 10384, 33573, 0, 0, 0,
 3, 3, 3783, 1359]
```

It byte-equals the case-5 vector already agreed by independent S1-A2
preflights A and B and remains below every frozen per-case F2 limit.

## 3. Implementation isolation and hostile evidence

The verifier is a standalone standard-library process. It imports no project,
test, producer, preflight, or legacy bootstrap implementation and contains the
frozen marker `INDEPENDENT_V2_CONSTRUCTIVE_VERIFIER_V1`. The existing A4-T AST
surface confirms the import allowlist, absence of dynamic code and process
control, and absence of the producer path/marker.

Verifier-owned tests additionally reject:

- a legal but non-maximal true witness;
- integer-as-Boolean, wrong-tag, and extra-member witnesses;
- a correctly bound but not-yet-implemented case;
- candidate hardlinks and symlinks;
- unexpected context objects;
- pre-existing output roots; and
- any execution that would mutate candidate bytes or leave a private staging
  root behind.

Two complete legal runs produce byte-identical result and receipt files.

## 4. Verification evidence

Focused verifier acceptance:

```text
pytest -q tests/test_raw_v8_step2_maximum_protocol_v2_independent_verifier_v49f.py
12 passed
```

The frozen A4-T module now has exactly two intended blockers:

```text
57 passed, 5 skipped, 2 failed
```

The only failures are:

```text
A4_T_SEPARATE_PRODUCER_MISSING
A4_T_PARENT_PILOT_RUNNER_MISSING
```

The verifier legal path, all three hostile candidate classes, source isolation,
and invalid-CLI behavior pass. Static verification is also required to remain
green:

```text
ruff format --check <verifier> <verifier-test>
ruff check <verifier> <verifier-test>
python -m py_compile <verifier> <verifier-test>
```

The complete accepted predecessor through verifier/control matrix passed:

```text
226 passed in 391.93s
```

Exact seed regeneration reproduced `13,419,905` bytes, raw SHA-256
`a75a2f352e8513b7ff0043693a0c65ebbf4bc6f06859354789af69e1162b0e4f`,
and seed ID
`ac22151fa74702ac1488924f01161eaa38574545e6272a290db6b0bbd288ae5f`.
The finalizer's `--check-manifest` mode and the Stage-1 control checker both
returned zero against the accepted finalization manifest.

## 5. Nonclaims

This checkpoint does not accept a producer, parent runner, six-case pilot,
case 24/54/69/435/475 verifier coverage, all-row result run, selected
publication, Raw V8 Step 2, Stage 1, offline Stage 2, paper/live trading,
predictive edge, safety, or profitability.

The verifier's root-last publication uses an absent parent-owned result path;
the later parent runner still must enforce process F0 ceilings, candidate
immutability, no-name-collision isolation, and full-run limits. Those runner
properties are not inferred from this single-process test.

## 6. Next bounded action

Proceed to `A4-P`: implement only the separate case-5 producer at the frozen
path. It must emit the closed legal candidate without importing the verifier,
reading verifier output, or asserting any verifier-owned proof/resource field.
Do not add the parent pilot runner yet.
