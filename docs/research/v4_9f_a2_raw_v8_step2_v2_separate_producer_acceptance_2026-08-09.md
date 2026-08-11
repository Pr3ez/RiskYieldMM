# Raw V8 Step-2 V2 separate producer acceptance

**Date:** 2026-08-09  
**Gate:** `S1-A4 / A4-P`  
**Decision:** `ACCEPTED` for frozen case position 5 only  
**Next:** `A4-P6`, beginning with an independent fail-first six-case target  
**Formal Stage 1 state:** `NO-GO`

## 1. Accepted boundary

The accepted producer is:

```text
scripts/tests/produce_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py
```

It is a standalone, non-authoritative candidate generator. It does not import,
read, execute, or reproduce the independent verifier. It accepts only the
fixed case-5 CLI and emits only one closed candidate bundle containing:

```json
{
  "candidate_kind": "MAXIMUM_WITNESS_CONTEXT",
  "ordered_context_object_entries": [],
  "scope_witness_context": null,
  "witness_record": {"kind": "BOOL", "value": false}
}
```

The producer derives the two legal Boolean alternatives from the pinned
`CapacityMeasurementBoolValueV1` structural-registry descriptor and selects
the longest compact canonical witness. It does not receive or assert an upper
bound, verification result, resource vector, or proof certificate.

Before publication it validates and later rechecks:

1. its own direct, single-link source file and source marker;
2. the exact physical and semantic A4-B0 boundary;
3. the final S1-A3 seed and finalization manifest;
4. all 17 seed-pinned authority files, including unique device/inode and exact
   byte identities;
5. F0 input-file, total-input, JSON-domain, and output-file limits;
6. the exact case-5 case binding and logical-plan ID; and
7. the complete candidate bytes staged for publication.

The output root must be absent. The producer builds a private mode-0700
sibling root, writes a mode-0600 single-link `candidate.json`, fsyncs the file
and directories, rechecks every input, and publishes the closed root last. It
does not overwrite or repair an existing file, directory, or symlink.

## 2. Frozen implementation identities

| Artifact | Raw octets | Raw SHA-256 |
|---|---:|---|
| `scripts/tests/produce_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py` | 38,318 | `9a0f2078419920dfaf89b3d2161381881abb07f375aaba94a960fc77576573ed` |
| `tests/test_raw_v8_step2_maximum_protocol_v2_separate_producer_v49f.py` | 15,565 | `c3f47d0a2ef9f5026c953699165e98985c09a143058a0e85dd7a680675baaa28` |

The frozen producer source marker is:

```text
SEPARATE_V2_CONSTRUCTIVE_PRODUCER_V1
```

The verifier and producer remain distinct paths, files, source markers, and
semantic roles. The parent runner remains absent.

## 3. Exact case-5 candidate

The produced candidate has:

| Field | Value |
|---|---|
| case position | `5` |
| case kind | `MAXIMUM_PUBLICATION_ROW` |
| type | `CapacityMeasurementBoolValueV1` |
| witness | `{"kind":"BOOL","value":false}` |
| candidate envelope raw octets | `1,333` |
| candidate envelope raw SHA-256 | `6dfba23c6d18e96eaf826de408f66d4c69980acbd604d3d7c66f29661f74f9f1` |
| constructive candidate ID | `048df6d26b0d60f217864c32a1b420a34b8427a513a120185de43d822e73b120` |
| context objects | `0` |

Two independent producer runs emit byte-identical candidate envelopes. The
accepted A4-V verifier accepts these bytes as the exact 29-octet attainer and
does not mutate the candidate closure.

## 4. Acceptance and falsification evidence

The dedicated producer suite reports:

```text
20 passed
```

It covers:

- exact envelope bytes, identity, binding, plan, witness, modes, and links;
- byte determinism across independent runs;
- black-box verifier interoperability and candidate immutability;
- noncanonical and unsupported case positions;
- missing, reordered, and extra CLI arguments;
- existing output files, directories, and symlinks;
- boundary-byte substitution;
- seed-byte substitution;
- structural-authority byte substitution, hardlinking, and symlinking;
- hardlinked producer-source rejection; and
- private-staging cleanup on success and failure.

The unfiltered frozen A4-T module now reports exactly:

```text
61 passed, 2 skipped, 1 failed
```

The only failure is the deliberate next-gate sentinel:

```text
A4_T_PARENT_PILOT_RUNNER_MISSING
```

The accepted filtered selection reports:

```text
59 passed, 2 skipped, 3 deselected
```

The unchanged independent verifier suite reports `12 passed`. The complete
predecessor-through-producer/control matrix reports:

```text
306 passed, 2 skipped, 3 deselected in 423.76s
```

The Stage-1 control checker and its seven drift tests pass. The exact seed and
finalization authorities remain frozen; no F2 limit changed.

## 5. Nonclaims

This acceptance proves only that the bounded case-5 producer creates the exact
candidate data expected by the independent verifier under the frozen local
authority and filesystem contract.

It does **not** accept or claim:

- the parent pilot runner;
- producer or verifier support for cases 24, 54, 69, 435, or 475;
- a passing six-case pilot;
- all-475 constructive closure;
- publication of the 474 maximum rows;
- offline Stage 2 readiness;
- paper- or live-trading readiness;
- predictive edge; or
- profitability.

Stage 1 therefore remains formal `NO-GO`.

## 6. Next bounded action

Proceed to `A4-P6`. Its first action is an independent fail-first target that
freezes exact legal candidates, verified results, resource evidence, runner
isolation, immutable F2 limits, two-run determinism, and all-or-nothing
qualification for positions `5`, `24`, `54`, `69`, `435`, and `475`.

Only after that target is accepted may the existing producer and verifier be
extended to the remaining five cases and the parent-owned runner be added. A
case-5-only runner, structural-only acceptance, copied producer/verifier
logic, limit tuning, or partial pilot PASS must remain rejected.
