# Raw V8 Step-2 V2 independent-verifier expansion V2 acceptance

**Date:** 2026-08-10  
**Gate:** `S1-A4 / A4-P6-V2`  
**Decision:** `ACCEPTED`  
**Formal Stage 1 state:** `NO-GO`  
**Next bounded packet:** `A4-P6-V3` — corrected case 435

## 1. Accepted claim

`A4-P6-V2` extends the accepted V0/V1 verifier only for successor-mode exact
profile case 69. The verifier independently resolves the retained local
shutdown operation result and signed operation specification, reconstructs the
one frozen profile application, derives the analytic endpoint, intersects it
with the structural endpoint, executes P1, measures P3, and accepts only when
all three channels agree at exactly **2,581 canonical octets**.

Accepted V2 facts:

| Property | Frozen result |
|---|---|
| Case position | `69` |
| Logical plan | `b991ffb7f0ea927d854228bcc52524e39fee7e88080d9171753b03cc59589fcb` |
| Profile | `92a80f3b2dc5d4b9a6284adfb6819823de7e2546d4141b2b12c5c7c9afff21f4` |
| Conditioning program | `6912414e364c4117822c7ad0d24d1436d46f29e945ed076140785f5c0c9fc442` |
| Signed specification | `f88cf223f28a146b08b5ffbb3b5ce419fb7ce473563edb27900983d6583a2d21` |
| Profile application | `770d99b0001802ceb6bdc044b9b55ce3cfd319754e9b9716c10d0b3d2e214f18` |
| Analytic catalog | `759b3fbd70f3a36c0a6309ec35c4f5cd8efda7cf01d23bcd5e52e290ff29f0e0` |
| Structural endpoint | 524,287 octets |
| Analytic endpoint | 2,581 octets |
| Exact intersection / P3 | 2,581 octets |
| Required physical context objects | none |

The constructive witness is not accepted as its own proof. Exactness follows
only from the independent upper calculation, frozen P1 legality, and measured
P3 attainment under the same identity-bound case, plan, profile, application,
result, and specification authorities.

This is a bounded verifier-packet acceptance. It does not accept cases 435 or
475, the complete verifier, producer expansion, the parent runner, the
six-case pilot, all 475 cases, Raw V8 Step 2, Stage 1, live readiness,
predictive edge, trading safety, or profitability.

## 2. Architecture decision

Three implementation choices were compared:

1. dynamically execute the pinned generic rule runtime;
2. build a generic profile-conditioning engine for all 475 cases now; or
3. extend the verifier-owned static typed subset only for the exact case-69
   dependency closure and retain an out-of-process generic-runtime oracle.

Dynamic execution remains forbidden by the accepted independence and source
isolation contract. A generic profile engine was rejected for V2 because it
would widen the trusted surface before the corrected case-435 and local
case-475 semantics are independently qualified. V2 therefore selects the
third design:

- the generic runtime remains a byte-pinned authority and is never imported or
  executed by the verifier;
- the verifier interprets only the closed result/spec record, tagged-union,
  intrinsic-rule, safe-integer, identifier, and signed-spec operations needed
  by case 69;
- the active tagged-union branch is validated without traversing inactive
  alternatives;
- the exact `OUTER_RESULT_APPLICATION` scope fixes the result reference,
  V4-inventory spec pointer, profile, application schedule, and invocation;
- no physical context file is legal for this fixed-authority scope; and
- cases 435/475 remain explicit `UNSUPPORTED_CASE` rejections.

No external literature search was needed for this packet. Its semantic truth
is repository-defined by the frozen seed, V4 inventory, exact-delta authority,
constructive boundary, and accepted design. External sources cannot establish
the byte identities or opcode semantics of this local protocol and would be a
weaker authority than the executable frozen contracts.

## 3. Exactness evidence

The independent fixture derives the local-shutdown endpoint from the frozen
piecewise-affine decimal-width program:

```text
constant + linear_coefficient * B + decimal_width_coefficient * digits(B)
= 2312 + 268 * 1 + 1 * 1
= 2581
```

Here `B=1` is the signed specification's maximum terminal ingress batch count.
The fixture constructs a legal result of exactly 2,581 compact canonical UTF-8
octets and checks every result counter against its signed maximum. Its stable
identities are:

| Artifact | SHA-256 / semantic ID |
|---|---|
| Canonical witness bytes | `af8bf018a32ac4444cd00cfc6b3cb64c732654398a5904f0295ec77307d718f4` |
| Witness `result_evidence_id` | `912c0d608d394a1d7508f54752d4a0fda0836371f6a1a596934a5910e221c0ff` |
| Maximum attainer | `1a56290000608a5c877bdc9a73ef00600b4dcf261f5b1d85586f5d3339e3723e` |
| Upper-bound certificate | `12f0e8d7559859a815671dd10e0d26d398b2531eef5bb14ef939bb9acc9fc5c9` |
| Proof-resource report | `48bd334db703f92b7341039e186604f620441ae175485f3b5e7a71a36d68e740` |
| Verification receipt | `fb83be220337d47d58da370a266a35df1918ab6d6e79f1e3aeea612300b4327e` |

Two separately published candidate trees produce byte-identical output trees,
and candidate bytes remain unchanged before and after verification.

Hostile coverage directly rejects:

- changed context kind or profile identity;
- exchanged result/spec root inputs;
- a re-sealed but wrong V4 specification pointer;
- wrong application ID, invocation ordinal, or missing invocation;
- a result that violates the signed-spec cross rule;
- intrinsic result or specification failure;
- a legal but nonattaining P3 witness;
- an undeclared physical context object;
- a 2,581-to-2,582 analytic authority mutation in a shadow repository; and
- premature case-435 or case-475 execution.

Every rejected candidate exits through one public fail-closed diagnostic line,
leaves no output root, and never reports an internal failure.

## 4. Deterministic resource evidence

The exact V2 event stream is independently reproduced as:

```text
stream SHA-256
7965e977eca8aa43ce84c97391a1ae4c51dfd2f79fa20e80ea7b6110ea5c808f

18-metric resource vector
[1, 2101890, 157, 829, 4204335, 7, 157, 105752, 673168,
 763519, 1380238, 6, 1, 1, 14, 32, 50016, 36961]
```

Every measured value is at or below the immutable successor F2 ceiling. V2
does not claim case-435 resource requalification; that remains a mandatory V3
result.

## 5. Immutable F0 result

The V2 verifier source is itself pinned. Replacing only the historical V1
verifier bytes with V2 produces this live successor footprint:

| Input surface | Files | Pinned octets | File headroom | Octet headroom |
|---|---:|---:|---:|---:|
| successor authorities before candidate | 38 | 28,825,355 | 26 | 38,283,509 |
| case 69 authorities + candidate | 39 | 28,831,491 | 25 | 38,277,373 |

The 6,136-octet candidate and every authority remain below the immutable F0
ceilings of 64 files, 67,108,864 total pinned octets, and 16,777,216 octets per
individual file. No F0 or F2 ceiling was changed.

## 6. Accepted artifacts and checks

Accepted implementation bytes:

- `scripts/tests/verify_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py`
  - 200,136 octets
  - SHA-256 `ede2a1d01e51fa7fa8687f2f5ae029cdbc8bc98b129d815e5697f4600d42d2ce`
- `tests/test_raw_v8_step2_maximum_protocol_v2_independent_verifier_expansion_v2_v49f.py`
  - 26,421 octets
  - SHA-256 `80d29d39a777c653240c34a0f078ac02a919f6798e3b149e86057fb8e24f7bb5`
- `tests/test_raw_v8_step2_maximum_protocol_v2_v2_runtime_differential_v49f.py`
  - 4,737 octets
  - SHA-256 `520c81cd76d074cfd40298483553d78566abf9da247192db54014f761e8baff9`

Focused and adjacent evidence:

```text
V2 independent acceptance + V2 runtime differential
22 passed in 42.17s

V0 expansion + predecessor verifier
19 passed in 42.25s

V2 + V2 differential + V1 + V1 differential
48 passed

recurrence + profile conditioning + cell transfer + event grammar +
profile-attainability scope + source security + constructive boundary
105 passed in 14.50s

ruff check <V2 implementation, tests, control checker, and control tests>
All checks passed!

python -m py_compile <same Python files>
exit 0

python scripts/tests/generate_raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.py --check
exit 0

python scripts/tests/check_stage1_execution_control.py
STAGE1_CONTROL_OK ... s1_a4_verifier_packet=A4-P6-V2 s1_a4_verifier_next=A4-P6-V3 ...
exit 0

git diff --check
exit 0
```

Final sealing evidence:

```text
29-file accepted Stage 1 core matrix
440 passed

unfiltered A4-T
1 failed, 61 passed, 2 skipped
sole failure: A4_T_PARENT_PILOT_RUNNER_MISSING

unfiltered A4-P6-T
6 failed, 13 passed, 2 skipped
sole failure set: cases 24/54/69/435/475 producer-not-qualified plus parent runner
```

The unfiltered failures are required ordered fail-first evidence. Verifier
acceptance of case 69 does not release its producer path.

## 7. Next action and stop conditions

Proceed only to `A4-P6-V3`: implement corrected exact-profile case 435 against
the accepted exact-delta plan. V3 must reconstruct the complete 67-observation
context and 137 P1 applications, independently establish P2/P3 equality at
257,887 canonical octets, requalify every per-case F2 resource under the
immutable ceilings, and reject old-plan, C2-certificate-trust, context,
schedule, and substitution attacks.

Stop and reopen V2 if case 69 ceases to derive exactly 2,581, the static subset
and pinned runtime disagree, an authority/candidate/context byte can change
without rejection, output becomes nondeterministic, predecessor case 5 or V1
cases 24/54 change, cases 435/475 become executable early, or any F0/F2 ceiling
must be relaxed.
