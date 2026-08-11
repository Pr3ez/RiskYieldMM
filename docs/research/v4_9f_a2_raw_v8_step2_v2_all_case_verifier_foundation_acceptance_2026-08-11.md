# Raw V8 Step-2 V2 all-case verifier foundation acceptance

Date: 2026-08-11  
Gate: `S1-A4 / A4-R475-V0`  
Decision: **A4-R475-V0 ACCEPTED — FOUNDATION ONLY**  
Formal Stage 1 state: **NO-GO**  
Next bounded packet: **A4-R475-V1**

## 1. Accepted claim

The new versioned verifier path now implements the authority, case-resolution,
typed-legality, and rule-AST foundation frozen by `A4-R475-T`.

It independently reconstructs all 475 effective case/plan records and resolves
only case 435 through the accepted successor delta. It pins and qualifies the
complete accepted typed runtime. Its fixed CLI performs the full authority
barrier and then rejects as `FOUNDATION_ONLY` before candidate or output
access.

The accepted constructive case count remains zero.

## 2. Artifact identities

| Artifact | Raw octets | SHA-256 |
|---|---:|---|
| versioned verifier foundation | 42,659 | `15adb9fd5c427c1e1e96ff630e13b36d3f385f12eaf68a388a5da7be48dbf5aa` |
| independent reviewer | 24,299 | `b835f426b9e15cbb4f2dadb7af8bb4a159356275a2f4c30557da1da00b080544` |
| acceptance report | 3,776 | `1a8a5e8500e29d68d45a87aba4955c8041248b42509cf4d675f3ab02a64f8e59` |
| historical fail-first test | 416 | `2d3185a046473b0237d6ea797bf94c01230ae73066f980ba71c2f82fb1de77c7` |
| semantic foundation test | 13,230 | `caec936701273cdf603f56c66b3905fbf63f27dec746cafcfdb796d9a48d8025` |
| independent acceptance test | 7,503 | `c87ecaaa5b2771560807b165b45c5eb470142dd6c8f654f0c46ee2071c164fb2` |

Acceptance report ID:

```text
127784d23829d3b92179596d5d058d5305c0075208b8a809109e4de49663973f
```

The predecessor six-case verifier remains byte-exact at SHA-256
`b1bfb5778b1408c4b2dc45dd008f1089e2405b503b7eee9686820535d5631d25`.

## 3. Independent evidence

The independent reviewer imports neither the versioned verifier nor the pilot
roles. It independently obtained:

- 475 ordered case records;
- execution-family census `66 + 406 + 1 + 1 + 1`;
- successor dispatch positions exactly `[435]`;
- case-ledger ID
  `67ec002e95bf30764aa1d7e0175ab082d4b4f987a7d96981be75ece794e62566`;
- two byte-identical verifier replays, both returning the exact
  `FOUNDATION_ONLY` rejection;
- zero candidate paths opened and zero output paths created;
- two byte-identical typed-runtime reports covering 42 rules, 8 applications,
  and 2 resolvers; and
- an 18-file, 16,717,988-octet authority footprint under unchanged F0.

Four independently checked, coherently resealed acceptance-report mutations
were rejected: constructive-count overclaim, producer-presence overclaim,
skipped-next-packet claim, and false F0 headroom.

## 4. Test evidence

Historical fail-first before implementation:

```text
1 failed in 0.08s
failure: A4-R475-V0 versioned verifier foundation is missing
```

Final focused matrix:

```text
pytest -q \
  tests/test_raw_v8_step2_maximum_protocol_v2_all_case_verifier_foundation_fail_first_v49f.py \
  tests/test_raw_v8_step2_maximum_protocol_v2_all_case_verifier_foundation_v49f.py \
  tests/test_raw_v8_step2_maximum_protocol_v2_all_case_verifier_foundation_acceptance_v49f.py

22 passed in 48.83s
```

The 22 cases comprise 1 role-presence check, 12 semantic/security checks, and
9 independent acceptance checks.

## 5. Fail-first transition

The original all-case role boundary now has exactly this state:

| Role | State after V0 |
|---|---|
| versioned verifier | present and accepted as foundation-only |
| versioned producer | absent, expected red |
| versioned runner | absent, expected red |

Therefore the three-role fail-first suite must now produce one pass and exactly
two failures. That is the required boundary, not a regression.

## 6. Nonclaims and next action

This packet accepts no constructive case and no maximum. It does not accept the
66 intrinsic cases, generic-profile cases, special cases, producer, runner,
campaign, Raw V8 Step 2, Stage 1, live readiness, trading safety, predictive
edge, or profitability.

Proceed only to `A4-R475-V1`: add the 66 intrinsic-template cases and require
byte-exact regression for all six accepted pilot cases. V1 must retain the V0
authority and candidate-access boundaries and leave generic-profile and special
case expansion for V2/V3.
