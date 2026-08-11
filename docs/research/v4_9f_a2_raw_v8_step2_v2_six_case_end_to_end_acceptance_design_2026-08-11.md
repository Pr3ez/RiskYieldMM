# Raw V8 Step-2 V2 six-case end-to-end acceptance design

Date: 2026-08-11  
Status: **A4-P6-E DESIGN FROZEN — FAIL-FIRST REQUIRED — FORMAL STAGE 1 NO-GO**

## 1. Decision being made

`A4-P6-E` is an independent release adjudication over the already accepted
`A4-P6-R` packet. It is not another producer, verifier, or parent-runner
implementation.

The gate answers one narrow question:

> Do the frozen six-case authorities and two-run evidence satisfy their exact
> qualification rule strongly enough to activate `A4-R475`?

The frozen target rule is:

```text
ALL_SIX_CASES_PASS_TWICE_BYTE_IDENTICALLY_UNDER_IMMUTABLE_F2
```

Acceptance releases the next gate for a versioned 475-case implementation and
campaign. It does not claim that the current six-case binaries already support
all 475 cases, that the complete campaign will remain below every F2 limit, or
that any later gate is accepted.

## 2. Confirmed predecessor facts

The parent-runner packet accepted these fixed identities:

| Artifact | Raw octets | SHA-256 |
|---|---:|---|
| runner | 50,461 | `5f1997b4e689a14cbae0a340fce2f320bb058eb9dd04449897ff3dfdf8de7ad7` |
| runner qualification | 17,493 | `431f3ea5f41c87a5635cb2b5b44f24c548ecc4983c8c3acd02a6b5ab2d7a976c` |
| A4-P6-R reviewer | 25,387 | `22565dfb4456823377bcea41790888531f0def2d645c7dd4a2d6f272c0bd26eb` |
| A4-P6-R report | 12,969 | `ae315492c9a7fa24968c3132e5e0f9982693175922db845312a74f3e61e0487a` |
| A4-P6-R acceptance test | 6,676 | `b223ceefc3837e5d7f90827f281f1457038f681d95a0b46585951e6eebfc24a0` |
| A4-P6-R acceptance document | 6,864 | `1d3182dbd6991ce3226b03392ce4d063f68460bff00bb9f8bfb432e9fc427d9d` |

The report semantic ID is:

```text
ee39ba2ee328f20774ed3c678d6bf9edf4790a68a587c591828813c358f0ca9b
```

It records two byte-identical parent transactions, 12 producer and 12 verifier
child runs, candidate immutability, read-only checking, all-or-nothing
publication, injected rollback evidence, and exact reconciliation of all 18
full-run F2 metrics.

## 3. Critical scope finding

The accepted successor producer and verifier deliberately admit only cases:

```text
5, 24, 54, 69, 435, 475
```

The current runner is likewise a six-case pilot. The seed universe contains
474 maximum-publication cases plus the separate local-minimality case 475.
Consequently:

- `A4-P6-E` can release `A4-R475` as the next active implementation gate;
- it cannot release an immediate unmodified 475-case execution;
- `A4-R475` must first freeze a versioned all-case role and campaign contract;
- accepted six-case sources remain immutable predecessor evidence;
- all 475 results and the complete full-run F2 vector must still be measured;
- pilot headroom is not extrapolated into a complete-run guarantee.

This distinction prevents a six-case qualification result from being silently
upgraded into an unsupported all-case capability claim.

## 4. Alternatives considered

### Trust the A4-P6-R acceptance verdict directly

Rejected as circular. `A4-P6-E` must reconstruct the report identity, case
ledger, source bindings, qualification rule, and F2 aggregation rather than
copying `review_decision = ACCEPTED`.

### Import the accepted reviewer or reviewed roles

Rejected because it collapses the independent implementation boundary. The
new reviewer treats predecessor executables as fixed black boxes and invokes
only the A4-P6-R reviewer through an isolated process interface.

### Run only one predecessor replay

Rejected because a single replay cannot independently demonstrate reviewer
output determinism. The selected design performs two isolated complete
reviewer replays and requires both outputs to be byte-identical to each other
and to the frozen predecessor report.

### Start the 475-case campaign immediately

Rejected because 469 non-pilot cases are outside the current role allowlists.
Doing so would either fail closed or require unreviewed in-place mutation of
accepted sources.

### Raise or extrapolate F2 limits from pilot observations

Rejected. F2 is immutable. The pilot values establish only that the pilot fits;
the complete campaign must independently aggregate all 475 results and reject
if any full-run ceiling is exceeded.

## 5. Selected independent-review architecture

The A4-P6-E reviewer is standard-library-only and does not import the runner,
producer, verifier, their tests, or the A4-P6-R reviewer. It performs:

1. exact size/hash checks for every frozen predecessor artifact;
2. strict duplicate-free canonical JSON loading;
3. independent reconstruction of the A4-P6-R report semantic ID;
4. exact source-descriptor reconstruction from repository bytes;
5. exact comparison of the six case positions, kinds, plans, coverage tags,
   candidate/receipt/result identities, closure sizes, and resource vectors
   against the frozen target and producer acceptance ledger;
6. independent SUM/MAXIMUM aggregation of all 18 resource metrics against the
   finalization manifest, including exact aggregation-mode preservation;
7. exact validation of the target qualification rule and runtime evidence;
8. two isolated black-box executions of the frozen A4-P6-R reviewer;
9. byte equality between both replay reports and the stored report; and
10. an explicit release decision that separates pilot acceptance from
    all-475-case readiness.

Static preflight may produce an `UNDER_REVIEW` report but may never release
`A4-R475`.

## 6. Release report contract

The deterministic report contains:

- predecessor artifact descriptors and A4-P6-R semantic identity;
- the exact qualification rule;
- two-replay evidence and effective replayed child-process counts;
- six ordered release-case records;
- 18 independently recomputed F2 reconciliation records;
- seed-universe and current-role-surface counts;
- ordered release criteria with no omitted or optional criterion;
- `release_decision = RELEASED_FOR_A4_R475_VERSIONED_IMPLEMENTATION` only after
  runtime replay;
- `next_subgate = A4-R475` only after runtime replay; and
- `formal_stage1_state = NO-GO` in every mode.

The report identity is SHA-256 over canonical JSON of:

```text
{
  "domain":
    "RiskYieldMMRawV8Step2MaximumProtocolV2SixCaseEndToEndAcceptanceReportV1",
  "payload": <all report members except the report identity>
}
```

## 7. Fail-first and hostile acceptance

Before the reviewer and report exist, the qualification file must produce one
missing-artifact failure and skip dependent checks. After implementation it
must prove:

1. exact reviewer/report bytes and semantic identity;
2. static preflight cannot release the next gate;
3. a fresh full reviewer replay exactly reproduces the frozen report;
4. all release criteria and pilot-only campaign limitations are explicit;
5. the complete 18-metric vector is independently recomputed;
6. re-sealed gate, role-surface, case-ledger, replay-count, or F2 mutations are
   rejected semantically; and
7. reviewer source isolation excludes imports of reviewed roles and tests.

## 8. Gate transition and nonclaims

If all criteria pass, `A4-P6-E` becomes `ACCEPTED` and `A4-R475` becomes
`ACTIVE_FOR_VERSIONED_IMPLEMENTATION`. The first `A4-R475` packet must freeze
the all-case surface and fail-first campaign contract before adding or running
new role versions.

This design does not accept `A4-P6-E`, `A4-R475`, any 475-case implementation
or output, Raw V8 Step 2, Stage 1, Stage 2, paper/live trading, predictive edge,
safety, or profitability. Formal Stage 1 remains `NO-GO`.
