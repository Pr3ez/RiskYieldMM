# Raw V8 Step-2 V2 independent-verifier expansion V1 acceptance

**Date:** 2026-08-10  
**Gate:** `S1-A4 / A4-P6-V1`  
**Decision:** `ACCEPTED`  
**Formal Stage 1 state:** `NO-GO`  
**Next bounded packet:** `A4-P6-V2` — exact-profile case 69

## 1. Accepted claim

`A4-P6-V1` extends the accepted V0 verifier only for successor-mode intrinsic
cases 24 and 54. It preserves predecessor and successor case 5 byte-exactly,
accepts independently constructed exact attainers for cases 24/54, and keeps
cases 69, 435, and 475 as stable `UNSUPPORTED_CASE` rejections. Producer and
parent-runner expansion remain held.

The accepted maxima are:

| Case | Frozen binding | Exact maximum | Retained context |
|---:|---|---:|---:|
| 24 | `CapacityMeasurementOperationResultBody / LOCAL_SHUTDOWN_RESULT_EVIDENCE_V2` | 523,738 canonical octets | one byte-exact 524,287-octet owner record |
| 54 | `CapacityMeasurementVocabularyDefinitionV1` | 3,145,728 canonical octets | none |

For each case, the verifier independently resolves the frozen case and logical
plan, executes the applicable recurrence transfer program, proves the analytic
upper endpoint, validates the candidate against the frozen typed and intrinsic
rules, and requires the legal witness length to equal that endpoint. Equality
of the proved upper bound and constructive legal attainer is the accepted
exactness argument; the candidate is never treated as its own proof.

This is a narrow verifier-packet acceptance. It is not acceptance of case 69,
case 435, case 475, the complete verifier, any producer or runner expansion,
the six-case pilot, all 475 results, live readiness, predictive edge, trading
safety, or profitability.

## 2. Architecture decision

Two viable execution designs were evaluated:

1. dynamically import or execute the already pinned generic typed-rule
   runtime inside the verifier; or
2. keep the verifier standard-library-only and implement the minimum closed
   typed/rule subset needed by cases 24/54, then compare it against the pinned
   generic runtime in a separate differential suite.

The first design was rejected because the frozen independent-verifier role
forbids dynamic code loading and execution. It would make authority data
executable inside the security boundary and would fail the accepted source
isolation contract. V1 therefore uses the second design:

- the generic runtime source is still loaded and pinned before candidate
  access as an authority byte string;
- the verifier never calls `__import__`, `compile`, `eval`, or `exec`;
- a verifier-owned static subset validates the required record/tagged-union,
  text/literal/ASCII-DFA, safe-integer, array, object-reference, semantic-ID,
  codec, and intrinsic-rule forms; and
- a separate test-only differential oracle checks both positive attainers and
  six representative rejection samples against the exact pinned generic
  runtime.

This preserves V0's authority barrier and V1's independent runtime role while
leaving V2 free to add the different profile-conditioned semantics required
by case 69. No producer, preflight validator, maximum-protocol validator,
certificate result, or stored V1 answer is imported into the verifier.

## 3. Case-specific evidence

### Case 24 — retained owner-member union

The positive fixture builds the complete local-shutdown owner record from the
frozen V4 inventory, replaces only its `result` with the independently
constructed legal attainer, recomputes the owner semantic ID, and publishes
the compact canonical owner as one identity-bound context object. The verifier:

- closes the candidate/context directory tree and rejects symlinks,
  non-regular files, path/inode aliases, undeclared files, missing files, and
  physical or semantic-ID drift;
- resolves the exact owner reference and requires byte equality between its
  `result` member and the inline measured witness;
- validates the complete owner record, owner semantic identity, operation and
  result discriminators, selected union alternative, concrete result body,
  intrinsic cross-field counts/uniqueness, and both body and owner codecs;
- derives an exact 523,738-octet body endpoint while the complete retained
  owner occupies 524,287 octets; and
- rechecks every authority and all candidate/context bytes before atomic
  output publication.

Hostile coverage includes duplicate array members, count mismatch,
nonattainment, owner/witness divergence, context-byte tamper, missing/extra
context closure, wrong discriminator, wrong owner identity, owner-codec
overflow, and malformed UTF-8. Re-sealed illegal candidates reject without an
internal verifier failure or partial output.

### Case 54 — ordered raw-string vocabulary

The positive fixture independently constructs exactly 512 strictly ascending
members and expands the final member to attain the frozen 3,145,728-octet
endpoint. The verifier validates the closed record schema, ASCII-DFA
vocabulary ID, raw canonical JSON-string language, array cardinality,
uniqueness, strict lexical ordering, recurrence bound, and record codec.

Hostile coverage includes duplicate/reordered members, nonattainment,
self-codec overflow, and malformed UTF-8. Cases 69/435/475 remain explicitly
rejected, proving that V1 does not silently consume a later packet.

## 4. Deterministic result and resource evidence

Both positive cases were executed twice from independently republished input
trees. Candidate and context bytes remained unchanged and every emitted file
was byte-identical across runs. The verifier reproduced the frozen event
streams and all 18 F2-metered measurements:

| Case | Logical plan | Event-stream SHA-256 | 18-metric resource vector |
|---:|---|---|---|
| 24 | `428ff735837b841e66103d64cbcd4af7ceaf88d009c38229ad5e4cde0ab30d67` | `bf6a4886b3bc7110a61a5170e2b03f5de402a08e5bd78eccafb54b719d99cbcd` | `[1, 2101277, 39, 459, 4202945, 5, 39, 26493, 340068, 362505, 488331, 1, 0, 0, 6, 32, 36304, 9469]` |
| 54 | `4eeedde2c223693e62a2b89a2016b43f9954496771189616ad68ac8cf21e6da1` | `9a9b153f3fee7073849416c8ccc3f419bda471b1c541165b20f49989cb6b379f` | `[1, 515, 5, 9, 1031, 1, 5, 3415, 9775, 12712, 41372, 1, 0, 0, 4, 9, 3937, 1589]` |

Every measured value is at or below its immutable successor F2 ceiling. V1
does not claim case-435 F2 requalification; that remains an explicit V3
obligation.

## 5. Immutable F0 result

The verifier source is itself a pinned input. Its V1 growth changes the live
successor authority footprint without rewriting the historical V0 result:

| Input surface | Files | Pinned octets | File headroom | Octet headroom |
|---|---:|---:|---:|---:|
| successor authorities before candidate | 38 | 28,791,339 | 26 | 38,317,525 |
| case 24 authorities + candidate + context | 40 | 29,912,348 | 24 | 37,196,516 |
| case 54 authorities + candidate | 39 | 31,942,999 | 25 | 35,165,865 |

These totals remain below the immutable F0 ceilings of 64 input files and
67,108,864 pinned input octets. The largest individual V1 input is the
3,151,660-octet case-54 candidate, below the frozen 16,777,216-octet strict
individual-file upper bound. No F0 or F2 ceiling was raised.

## 6. Accepted artifacts and checks

Accepted implementation bytes:

- `scripts/tests/verify_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py`
  - 166,120 octets
  - SHA-256 `3a4cbab8ef3263d39ccf7caa174f82ffd8747f4c0e3229fef57cfae2507be333`
- `tests/test_raw_v8_step2_maximum_protocol_v2_independent_verifier_expansion_v1_v49f.py`
  - 25,633 octets
  - SHA-256 `94d25b649310d4eef96f76e125e468e4028fc334b445fcc6bb47970d8c3b9bff`
- `tests/test_raw_v8_step2_maximum_protocol_v2_v1_runtime_differential_v49f.py`
  - 4,357 octets
  - SHA-256 `44a8935a1760cb3eb5ca0697c2642e011b66f986bcb6b321d3e4b91102c6deb1`

Focused and adjacent evidence:

```text
pytest -q tests/test_raw_v8_step2_maximum_protocol_v2_independent_verifier_expansion_v1_v49f.py
19 passed in 55.72s

pytest -q tests/test_raw_v8_step2_maximum_protocol_v2_v1_runtime_differential_v49f.py
7 passed in 3.11s

pytest -q tests/test_raw_v8_step2_maximum_protocol_v2_independent_verifier_expansion_v49f.py
7 passed in 16.18s

pytest -q tests/test_raw_v8_step2_maximum_protocol_v2_independent_verifier_v49f.py
12 passed in 27.75s

pytest -q tests/test_raw_v8_step2_maximum_protocol_v2_implementation_fail_first_v49f.py \
  -k 'not test_a4_t_requires_frozen_role_implementation'
59 passed, 2 skipped, 3 deselected in 22.47s

pytest -q tests/test_raw_v8_step2_maximum_protocol_v2_six_case_qualification_fail_first_v49f.py \
  -k 'not test_remaining_pilot_pipeline_is_exact_deterministic_and_candidate_immutable and not test_parent_runner_exists_and_obeys_frozen_isolation_surface'
13 passed, 2 skipped, 6 deselected in 12.37s

ruff check <V1 implementation, tests, control checker, and control tests>
All checks passed!

python -m py_compile <same Python files>
exit 0

python scripts/tests/generate_raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.py --check
exit 0

python scripts/tests/check_stage1_execution_control.py
STAGE1_CONTROL_OK ... s1_a4_verifier_packet=A4-P6-V1 s1_a4_verifier_next=A4-P6-V2 ...
exit 0

git diff --check
exit 0
```

Final sealing evidence:

```text
27-file accepted Stage 1 core matrix
414 passed

unfiltered A4-T
1 failed, 61 passed, 2 skipped in 23.25s
sole failure: A4_T_PARENT_PILOT_RUNNER_MISSING

unfiltered A4-P6-T
6 failed, 13 passed, 2 skipped in 14.70s
sole failure set: cases 24/54/69/435/475 producer-not-qualified plus parent runner
```

The unfiltered failures are required ordered fail-first evidence, not
regressions: A4-T may fail only for the absent parent runner; A4-P6-T may fail
only for cases 24/54/69/435/475 producer qualification plus the absent parent
runner. Verifier acceptance of cases 24/54 deliberately does not release their
producer path.

## 7. Next action and stop conditions

Proceed only to `A4-P6-V2`: independently implement exact-profile case 69.
V2 must derive the 2,581-octet structural/analytic intersection, validate the
retained result/spec and exact profile application, preserve both V0 authority
modes and all V1 cases, remain within immutable F0/F2 ceilings, and leave cases
435/475, producer expansion, and the runner fail-closed.

Stop and reopen V1 if any accepted V0/V1 authority or artifact byte changes,
the generic runtime and static subset disagree, a candidate/context byte can
change without rejection, a hostile input reaches internal failure or partial
publication, case 5 changes, a later case becomes executable, or any resource
ceiling must be relaxed.
