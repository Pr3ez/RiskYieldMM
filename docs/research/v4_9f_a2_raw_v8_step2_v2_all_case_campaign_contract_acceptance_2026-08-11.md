# Raw V8 Step-2 V2 all-case campaign contract acceptance

Date: 2026-08-11  
Status: **A4-R475-T ACCEPTED — A4-R475-V0 NEXT — ALL-CASE ROLES FAIL-FIRST — FORMAL STAGE 1 NO-GO**

## 1. Decision

`A4-R475-T` is accepted as a contract-only packet. A separately authored
reviewer reconstructed the effective 475-case ledger directly from the frozen
seed and case-435 successor delta, matched all 12 F0 and 18 F2 records, and
validated the versioned role, checkpoint, resume, rollback, and root-last
publication boundary.

The accepted six-case sources were not modified. The three new all-case role
paths remain intentionally absent, producing exactly three fail-first
implementation failures.

## 2. Accepted artifacts

| Artifact | Raw octets | SHA-256 |
|---|---:|---|
| contract generator | 35,282 | `46a350c15cfffae80644e55132a4bbeb3a257b2b76261545f7ee4235835e7bd9` |
| all-case contract | 382,710 | `3ca4ff4d6e581895b813043e7fdeed24c33cf2c828e362ac81de1725e95a84bb` |
| independent reviewer | 25,668 | `9c5c30d7d00da2ca73d1e8f98edbc089b80e366b39bedcb426752fb4d0a86beb` |
| acceptance report | 3,607 | `c6703ae1a6b8262139bba63d5959054b999c43e2ffc7fef0fd854670e303384c` |
| acceptance test | 11,312 | `ebe423ef1167a7dc146bb65c5dd815161b5f0b870a6493e40f3231f5e8365a4a` |
| implementation fail-first test | 870 | `201ef30354c61cd87dcb26638d3194209b7cd34cad444ce18b1dd789010a3cfa` |

Contract semantic ID:

```text
9be94bf6b53b612d62ac26bc74133f25c1101a0962987a855e65cdcd06418583
```

Acceptance-report semantic ID:

```text
16035e8342cbe5713aa9d619638da13b34d5e7e56707433e66dfb3aa1078f1cd
```

## 3. Independently reconstructed case surface

The reviewer derived:

```text
case count:                         475
maximum-publication cases:          474
local-minimality cases:               1
intrinsic-template cases:            66
generic-profile cases:              406
signed-analytic exact profiles:       1
corrected application-exact profiles: 1
```

Ordered case-ledger SHA-256:

```text
d3ddf4d97353bde65295764eeed8d0f347c1930d8089dc25f20e91c946578e72
```

Case-ledger semantic ID:

```text
67ec002e95bf30764aa1d7e0175ab082d4b4f987a7d96981be75ece794e62566
```

Case 435 alone resolves through the accepted successor plan and packed-context
transport. Every other case resolves from the base seed at its exact one-based
position.

## 4. Lifecycle guarantees frozen

The accepted contract requires:

- one exclusive mutating owner and one case attempt at a time;
- strict completion order from case 1 through 475;
- a durable immutable anchor before the first attempt;
- a parent-authored case commit written last and atomically renamed;
- complete revalidation before any checkpoint reuse;
- rejection, not repair or skip, for corrupt or ambiguous committed state;
- rollback of recognized uncommitted attempts only;
- exact 475-case F2 reconciliation; and
- one final rename of the complete private work root to an absent accepted
  root.

No case checkpoint is independently accepted and no partial campaign may be
published.

## 5. Test evidence

The initial combined fail-first observation was:

```text
4 failed, 6 skipped
```

One failure was the absent contract packet; three were the absent versioned
producer, verifier, and runner. After implementing the contract packet:

```text
contract acceptance: 9 passed
intentional role fail-first: 3 failed
```

The green suite includes exact artifact identities, generator and independent
reviewer check modes, complete case/F0/F2 reconstruction, lifecycle checks,
four coherently re-sealed hostile mutations, and a real subprocess proof that
the accepted six-case producer rejects non-pilot case 1 without output.

## 6. Acceptance criteria

All eight contract criteria pass:

1. pinned predecessor and successor authority chain;
2. independently reconstructed effective 475-case ledger;
3. explicit complete five-family decomposition;
4. immutable F0 and F2 resource ledgers;
5. distinct versioned role paths and independence boundary;
6. fail-closed checkpoint, resume, and rollback semantics;
7. root-last atomic complete-campaign publication; and
8. explicit implementation fail-first state and Stage-1 nonclaims.

## 7. Next bounded packet

`A4-R475-V0` is next. It must implement only the versioned verifier foundation:

- exact all-case authority resolution, including case 435’s successor path;
- a generic typed-value legality interpreter over the frozen structural
  registry;
- a generic pinned intrinsic/cross-rule AST executor;
- preservation of the accepted six-case verifier as an immutable regression
  authority; and
- fail-closed tests before any new case is accepted.

It must not implement the producer or runner, start the campaign, or claim
all-case verifier acceptance.

## 8. Nonclaims

This checkpoint accepts only `A4-R475-T`. The future role paths remain absent.
It does not accept `A4-R475-V0`, any newly supported case, a 475-case result,
Raw V8 Step 2, Stage 1, Stage 2, paper/live trading, predictive edge, safety, or
profitability. Formal Stage 1 remains `NO-GO`.
