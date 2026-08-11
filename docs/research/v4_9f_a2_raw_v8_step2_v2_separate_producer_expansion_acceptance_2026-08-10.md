# Raw V8 Step-2 V2 separate-producer expansion acceptance

**Date:** 2026-08-10  
**Gate:** `S1-A4 / A4-P6-P`  
**Decision:** `ACCEPTED`  
**Formal Stage 1 state:** `NO-GO`  
**Next bounded packet:** `A4-P6-R` — parent pilot runner  
**Parent runner at acceptance:** `ABSENT_AND_HELD`

## 1. Accepted outcome

The single frozen `SEPARATE_PRODUCER` role now constructs deterministic,
closed candidates for pilot cases `5`, `24`, `54`, `69`, `435`, and `475`
under the packed successor authority. It also preserves the exact predecessor
case-5 candidate and rejects the five successor-only cases when invoked with
the predecessor boundary.

The accepted verifier remains unchanged and independently derives legality,
maximum/minimality, result identities, receipts, and all 18 F2 resource
measurements. The producer imports no verifier, proof checker, attainer,
runner, or pytest fixture and contains no accepted result, receipt, or
resource-report identity literal.

This acceptance does not release the parent runner, execute the six cases as
one parent-owned transaction, complete the 475-case campaign, close Raw V8
Step 2 or Stage 1, or establish predictive or trading edge.

## 2. Authority-mode resolution

The implementation uses one role source with two fail-closed modes:

| Boundary mode | Accepted cases | Purpose |
|---|---:|---|
| `PREDECESSOR_CONSTRUCTIVE_BOUNDARY_V1` | `5` | Exact compatibility with accepted `A4-P` |
| `SUCCESSOR_CASE435_PACKED_CONTEXT_BOUNDARY_V1` | `5,24,54,69,435,475` | Corrected six-case producer qualification |

The intermediate exact-delta boundary is deliberately not a production mode.
Unknown paths, aliases, noncanonical case positions, unbound identities,
changed F0/F2 limits, and drifted source or authority bytes reject before
publication.

## 3. Historical checkpoint handling

The former `A4-P` producer source and `A4-P6-V-A` test are preserved byte for
byte under non-collected `Archive` paths:

- `scripts/tests/Archive/a4_p_predecessor_accepted/produce_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py`
  - 38,318 bytes
  - SHA-256 `9a0f2078419920dfaf89b3d2161381881abb07f375aaba94a960fc77576573ed`
- `tests/Archive/a4_p6_v_a_historical/test_raw_v8_step2_maximum_protocol_v2_independent_verifier_acceptance_v49f.py`
  - 9,703 bytes
  - SHA-256 `d167ce6c98a6d48960cccbb95b94fddb7f5991adf5481408f3ed125aff2c75c7`

The accepted V-A report remains unchanged:

- semantic ID `1e20c2c1312abe6b3924c96e6979f046325a87d635f728007a157831381b1da1`
- raw SHA-256 `1adbc0b1ac3ca2e9c2ad805de6ba79f6ce1b8ea244d6a11e50c086f438c7c45c`

This is intentionally a versioned transition. Re-executing the old
case-5-only reviewer against the expanded producer would be a category error;
rewriting its report would falsely claim it observed bytes that did not yet
exist. Current control validates those historical bytes at their archive
locations and validates the expanded source through the new acceptance.

## 4. Accepted artifacts

| Artifact | Bytes | SHA-256 / semantic ID |
|---|---:|---|
| Expanded producer | 129,026 | `46c67738905488a467cbb66a6de719f4cd4804e7ac68143cb301dc1e9c46d7da` |
| Frozen verifier | 373,327 | `b1bfb5778b1408c4b2dc45dd008f1089e2405b503b7eee9686820535d5631d25` |
| Successor qualification test | 13,119 | `592780dbb9b211d5b7976be4895e2eb0fc1a0686fa0d81730f9d12a06b2ed7c1` |
| Independent acceptance reviewer | 32,070 | `7067aeae07056e09b6ee5bfb1c059744fab55453c3e41431313e6073e345cdb5` |
| Acceptance test | 6,863 | `d61d515f48fc91d68a3d0864729d7bd803da38709dc6af437e320811a7b963f4` |
| Acceptance report | 12,583 | raw SHA-256 `2ef2a621df51f5193108a61ed5b639ab48378b9e5fd87daf4cfbd619a9fb20c8` |
| Acceptance report semantic ID | — | `defe27a1fafa0c1b37f9e1cf5498b14bb662cc2724dec9660abdb86f78ef9ed6` |

## 5. Independent result ledger

The acceptance reviewer starts both roles as isolated child processes and
never imports them. Each packed-successor pipeline runs twice. Candidate
closures must be byte-identical between passes and unchanged by verification.

| Case | Constructed maximum/minimum octets | Result ID | Receipt ID | Resource-report ID |
|---:|---:|---|---|---|
| 5 | 29 | `f3b8f9da535e87f242c7b26cfbc525b1c71521d2dc1aaade648624206e30845f` | `de9de4223d2a40d13a6c5ad903c4dc259f6d6e84feda3664c0968c7f6b52ceba` | `375939bb2e876af1460adffeacf1fb5c12393c2c45dc7926e8f083e3e5983cee` |
| 24 | 523,738 | `55b5ecc89c5954d891be187220d649a510a136957d1a1a2f41d98a4766d3555d` | `65066d0c7c5b45400a79fbc7caae90c79f98a00ba3125f4f890482a127a23096` | `940cb2ddf33aafc5e87b2e1abc482c88db97d1b6e2750957629fba3c4f8c8107` |
| 54 | 3,145,728 | `3fbbe19b69419aaedcfd0eed07e56422a99b07e6f14ec1252f3c46e275688ce1` | `2e516b7417a28f3330c1938c10451d347b33b5a8a11247656a8fa5f8d6106c81` | `bce3c4cc8a75d8127cd2ce444a694e2f87baf411d8eb3a852826b8ef92ecc451` |
| 69 | 2,581 | `1a56290000608a5c877bdc9a73ef00600b4dcf261f5b1d85586f5d3339e3723e` | `fb83be220337d47d58da370a266a35df1918ab6d6e79f1e3aeea612300b4327e` | `48bd334db703f92b7341039e186604f620441ae175485f3b5e7a71a36d68e740` |
| 435 | 257,887 | `0ac5c1cb7e663b2259264144b4b45e61a0b163e1861d07ec7054072e3829866f` | `fd2d341d8bb8c79f72a97926599e8535c5bcb4694d839120f7852030bbfbc7dd` | `3a38d19959e0944c8353fde865fb2ae63119d4f289869fcfd601fd239b8b7be9` |
| 475 | 524,380 | `937e7a163426dc7015117004c03b8f8fc3fb3c9ad040c423f97b549974f20e73` | `eb6fdf156bb1b855a8fb4fadd8ebb10434c053493f91ce8fbcd5c2539ed10f0f` | `ffbb512dbe46fcc6cb9c94bfff2f21a246a0b4b00a118b60284c82f034b136d8` |

The full candidate/result raw hashes, closure hashes, and 18-component
resource vectors are sealed in
`scripts/tests/raw_v8_step2_maximum_protocol_v2_separate_producer_expansion_acceptance_report_v49f.json`.

## 6. Acceptance evidence

The independent reviewer observed:

- direct packed-successor replay: 12 producer runs and 12 verifier runs;
- exact byte determinism: verified for all six cases;
- candidate immutability under verifier execution: verified;
- successor qualification: `17 passed`;
- frozen A4-T boundary: `61 passed, 2 skipped, 1 failed`, with only
  `A4_T_PARENT_PILOT_RUNNER_MISSING`;
- frozen predecessor A4-P6 target: `13 passed, 2 skipped, 6 failed`, with only
  the five successor-only producer codes plus the absent-runner code; and
- exact predecessor case-5 bytes and semantic ID unchanged.

The producer publication tests also cover authority/path drift, predecessor
rejections, intermediate-boundary rejection, static imports, dynamic-code
prohibition, forbidden candidate claims, output permissions, atomic
publication, candidate immutability, deterministic double runs, and private
staging leftovers.

Final checkpoint regression on the accepted tree:

- independent A4-P6-P acceptance: `10 passed in 168.55s`;
- predecessor plus expanded producer suites: `37 passed in 78.97s`;
- complete pinned V0–V4 verifier replay: `128 passed in 812.87s`;
- Stage 1 execution-control and drift-rejection suite:
  `46 passed in 400.36s`;
- A4-T expected-red boundary: `61 passed, 2 skipped, 1 failed`, solely for
  the absent parent runner; and
- predecessor A4-P6 expected-red boundary: `13 passed, 2 skipped, 6 failed`,
  solely for the five predecessor-mode producer rejections and absent runner.

## 7. Gate transition

`A4-P6-P` is accepted. The only permitted next implementation packet is
`A4-P6-R`, the parent-owned six-case pilot runner. That packet must preserve
role separation, invoke the producer and verifier through their frozen CLIs,
publish one all-or-nothing parent result, reconcile whole-run F2 accounting,
and keep candidate/result closures immutable.

Formal Stage 1 remains `NO-GO`. `A4-P6-E`, the complete 475-case campaign,
Stage 1 closure, Stage 2, live trading, and profitability claims remain held.
