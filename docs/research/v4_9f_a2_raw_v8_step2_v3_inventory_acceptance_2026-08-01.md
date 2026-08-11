# V4.9F-A2-M Raw V8 Step-2 V3 inventory acceptance

Date: 2026-08-01  
Decision: **narrow GO — `V3_INVENTORY_ONLY_MAXIMA_PENDING`**

This report accepts the canonical Raw V8 Step-2 V3 inventory and its exact
maximum-constraint scope universe, including the single 2026-08-01 re-freeze
after the bounded constructive-maximum context contract was closed. It does not
accept constructive maxima, runtime-work maxima, production adapters, all of
Step 2, Raw V8, A2-M, or Stage 1.

## 1. Accepted boundary

The accepted inventory contains:

- the exact 49 concrete-record plus three finite-union external schema graph;
- the pinned External Schema V2 registry under semantic registry ID
  `5dc95a3e99c5646e912b6a7e9c3970cf2489d560ea890b0a19d38af4c51c2140`;
- four ordered normative-document records with physical byte identities;
- exact fixtures, target-field registry, counter schema, marker contract,
  selectors, and operation contracts;
- 408 pre-frozen maximum-constraint scope profiles:
  - four outer-result fixture profiles;
  - four non-checkpoint root-family profiles;
  - 400 checkpoint selector-position/outcome profiles;
- nine selectors containing 80 entries in aggregate; and
- explicit nonclaims that the 474 constructive byte-maximum rows and the
  local-shutdown unrepresentable counterexample are external and pending.

The profile catalog closes the constraint universe before maximum search. It
does not embed the V3 inventory identity in profile IDs, so inventory identity
is acyclic. Later non-intrinsic maximum-scope IDs must commit the accepted V3
semantic inventory identity.

## 2. Frozen identities

| Artifact | Bytes | SHA-256 / semantic identity |
|---|---:|---|
| `docs/research/v4_9f_a2_raw_v8_step2_external_schema_v2_correction_2026-07-28.md` | 217,135 | `29ec141e53adeb1c0afd51f205f5b57eb784b8859b5ba40958299abd1b713b55` |
| `scripts/tests/raw_v8_step2_external_schema_v2_structural_registry_v49f.json` | 1,469,663 | physical `9160297ff316c5931737c92f8b359f0a1e2ec22f0aa996ef3b09cf830dc96bf3`; semantic registry ID `5dc95a3e99c5646e912b6a7e9c3970cf2489d560ea890b0a19d38af4c51c2140` |
| `scripts/tests/generate_raw_v8_step2_inventory_v49f.py` | 225,129 | `f2ec89ef8e2d835ec4805e0f2890eb9d2b5c60f1de1fccd5e58cb0e69b9e0798` |
| `scripts/tests/validate_raw_v8_step2_external_schema_v2_v49f.py` | 77,117 | `1ec74910c5c4887467bfcaeef6608a44c161f95e8be00bef28b10c615ef43914` |
| `tests/raw_v8_step2_inventory_v49f.json` | 5,264,966 | physical `f33c1019afa7f49a316aac1bfbef7498e240f391e4fee00dfd95fdcda658669f`; semantic inventory ID `128d07a45dc2300c140f333cc3a45e2497aaa4089684f6e44da048ab403bbf9d` |
| `tests/test_raw_v8_step2_external_schema_v2_inventory_v3_v49f.py` | 54,643 | `9ababb8150080b38b5d0087a7c92941b66a1820e6698d4a6104d4bee550c358c` |
| `tests/_raw_v8_step2_contract_harness_v49f.py` | 129,364 | `6bbc1038f41bb5d78f921e68216951bbfa6c1cbc31c2fe96dd3172b545b7dcac` |
| `tests/test_trading_physical_transport_capacity_contracts_v49f_v8_isolated.py` | 13,224 | `2b8fbc55ea5210c7a54bc7f53e674b2ee5d0d01b348f2429108c126bf8037dd5` |
| `tests/test_raw_v8_step2_external_schema_v2_adversarial_v49f.py` | 20,318 | `d4dbd63f59f64d4c0056073563c312884773a278e502ac21a06fc159cd4fb29a` |

The former `test_output/raw_v8_step2_inventory_v3_candidate.json` was
byte-identical during pre-promotion comparison and was then removed. It is not
an accepted or live consumer surface; the canonical file under `tests/` is the
sole authority.

### 2.1 Re-freeze confinement proof

The pre-amendment golden was retained outside the repository during
regeneration. A recursive object comparison proves that the new inventory
differs at exactly four JSON coordinates:

```text
/normative_document_inputs/2/raw_octet_count
/normative_document_inputs/2/raw_sha256
/invariants/normative_document_sha256_by_role/STEP2_EXTERNAL_SCHEMA_V2_CORRECTION
/inventory_sha256
```

All 408 complete scope-profile objects are byte-for-byte equal before and after
the re-freeze. Their ordered ID-list canonical SHA-256 remains
`b50b97b682d5707062867f2789a204e0488bdc95be7977f9ddc408959d1c9e0e`,
and the 408 IDs remain unique. The structural registry ID, literal authority,
generator bytes, schemas, rules, applications, fixtures, and every other
inventory coordinate are unchanged. This is a documentation-authority
re-freeze, not a scope-universe redesign.

## 3. Independent validation

The validator uses only the Python standard library. It does not import
`riskyieldmm` or the generator. It independently:

1. applies the exclusive 16,777,216-byte input bound before decode;
2. performs bounded structural scanning and strict canonical I-JSON decode;
3. rejects duplicate keys, floats, non-finite values, invalid scalar types,
   noncanonical bytes, nonregular files, symlinks, and repository escapes;
4. verifies the exact V3 root and four ordered document authorities;
5. verifies object identity with the pinned structural registry;
6. recomputes the registry and inventory semantic identities;
7. reconstructs all 408 scope profiles independently;
8. resolves all source-authority pointers and recomputes pointed identities;
9. verifies exact 4 + 4 + 400 profile order and all 80 selector coordinates;
10. verifies checkpoint reason mappings and the split local-shutdown scalar,
    intrinsic, and operational contract arrays; and
11. derives the selector-bound schedule maximum of 137 application calls,
    12,531 charged rule evaluations, and 125,431 direct expression nodes for
    the 67-observation root.

The validator reports maxima as pending. It does not infer or accept a maximum
from a Boolean assertion or from the removed historical sizing heuristics.

## 4. Test evidence

The focused V3 inventory/security suite passes 45 tests in 49.24 seconds.
Coverage includes:

- deterministic write/check regeneration;
- exact root, document, registry, profile, pointer, and schedule reconstruction;
- 23 independently re-signed semantic mutations;
- malformed JSON, depth, raw-size, path, symlink, FIFO, directory, and stale-
  authority rejection;
- all five source-authority rechecks;
- partial-write and failed-replace preservation of the previous target;
- atomic publication, final byte/inode verification, and temporary cleanup;
- concurrent leaf changes and observed input/output ancestor swaps;
- denial of authority-document paths as generator output; and
- controlled symlink-loop rejection without a traceback.

The migrated V3 inventory, historical foundation adversaries, and isolated
production-contract consumer matrix passes 98 tests in 69.76 seconds. The
previously accepted 375-test schema/rule/application component matrix remains
predecessor evidence; it is not added to 98 as though the suites were
necessarily disjoint.

## 5. Generator hardening and cleanup

The accepted generator:

- uses directory-descriptor, no-follow traversal for repository inputs;
- performs bounded stable reads and revalidates source snapshots;
- uses a same-directory exclusive temporary, complete write loop, file fsync,
  readback, target/parent identity rechecks, atomic replacement, directory
  fsync, and final path/inode/byte verification;
- permits output only at the canonical golden path or below `test_output/`;
- rejects authority self-overwrite; and
- contains no unreachable top-level function and no active 27-type,
  member-name-inference, or heuristic-maximum implementation.

Write mode has an explicit offline single-writer contract. It detects observed
namespace drift but does not claim to defeat an uncooperative process that can
rename or replace entries concurrently in the same writable directory. Such a
workspace is inadmissible for canonical publication. Linux `O_NOFOLLOW` and
`O_DIRECTORY` behavior is part of the currently accepted platform boundary;
this report makes no cross-platform race-freedom claim.

## 6. Closed defects

Independent review closed these promotion blockers before acceptance:

- circular maximum-scope identity through generated fixture IDs;
- mixed byte-maximum and runtime-work claims;
- incomplete local-shutdown scalar/intrinsic/operational separation;
- unstated ordering of the three local-shutdown operation-contract arrays;
- direct-truncation publication and leaf-symlink replacement risk;
- ancestor-component and foundation-ledger read weakness;
- detached-parent false-success detection;
- unrestricted explicit output overwriting authority inputs;
- symlink-loop traceback leakage;
- validator acceptance of an inventory outside the repository;
- selector-ID reconstruction over the wrong payload;
- stale V1/V2 canonical consumers;
- unreachable member-name-inferred 27-type and heuristic sizing code in the
  active generator;
- a deterministic tie-break that accidentally required optimization over
  derived SHA-256/proof bytes;
- an inline 67-observation root context whose understated row skeleton was
  17,459,925 bytes, contradicting the exclusive 16 MiB row cap;
- a monolithic 27,076-entry context catalog that could itself exceed 16 MiB;
- unbounded hash-prefix catalog partitioning, replaced by deterministic
  ordinal pages; and
- omission of the normative-document invariant mirror from the first
  re-freeze delta assertion.

## 7. Explicit nonclaims and next gate

This decision does **not** establish:

- any of the 474 constructive byte maxima;
- the local-shutdown unrepresentable counterexample or its minimality proof;
- completeness of runtime-work accounting or any work maximum;
- production-schema adapter equivalence;
- final Raw V7 compatibility on the eventual Step-2 tree;
- complete Raw V8 Step-2 or Step-3 acceptance;
- A2-M, A2-E, public-live, paper-trading, Stage 1, predictive-edge, trading-
  safety, or profitability acceptance.

The next gate is to freeze the separate closed constructive-maximum proof
protocol and its independent certificate verifier. Only then may the 474 byte-
maximum rows and the separate local-shutdown counterexample be generated.
Runtime-work accounting remains a distinct later gate.
