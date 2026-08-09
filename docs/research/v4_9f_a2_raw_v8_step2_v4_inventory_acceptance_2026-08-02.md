# V4.9F-A2-M Raw V8 Step-2 V4 inventory acceptance

Date: 2026-08-02  
Decision: **narrow GO — `V4_INVENTORY_ONLY_V2_PREFLIGHT_PENDING`**

This report accepts the canonical Raw V8 Step-2 V4 inventory as the exact
authority successor required by the accepted compact maximum-proof V2
correction. It accepts only the inventory migration and its runtime-contract
consumer. It does not accept a V2 proof protocol, either counting preflight, a
pilot, a constructive maximum, the local-shutdown result, runtime-work
accounting, production adapters, Raw V8 Step 2, A2-M, A2-E, or Stage 1.

## 1. Accepted boundary

V4 is an additive, exact-delta migration from the accepted V3 golden. It:

- changes the schema literal to `riskyieldmm.raw_v8_step2_inventory.v4`;
- inserts the accepted compact maximum-proof correction as normative input
  four of five under role `STEP2_COMPACT_MAXIMUM_PROOF_V2_CORRECTION`;
- changes only the corresponding schema, input-count, and authority-hash
  mirrors;
- adds the exact `compact_maximum_proof_v2_contract` object;
- recomputes the root inventory identity; and
- preserves every other recursively reachable value.

The accepted V3 golden, V3 generator/validator, historical V3 harness, and
rejected maximum-protocol V1 artifacts remain unchanged. V1 remains pinned to
V3 and rejected. It is not migrated, relabelled, or made accepting.

## 2. Frozen identities

| Artifact | Bytes | SHA-256 / semantic identity |
|---|---:|---|
| Accepted compact-proof V2 correction | 49,849 | physical `f4d35405ef1e66a8ba1c59027fc2097a56563d50408eb72cc48895d2127b71b4` |
| Accepted V3 inventory | 5,264,966 | physical `f33c1019afa7f49a316aac1bfbef7498e240f391e4fee00dfd95fdcda658669f`; semantic `128d07a45dc2300c140f333cc3a45e2497aaa4089684f6e44da048ab403bbf9d` |
| External Schema V2 registry | 1,469,663 | physical `9160297ff316c5931737c92f8b359f0a1e2ec22f0aa996ef3b09cf830dc96bf3`; semantic `5dc95a3e99c5646e912b6a7e9c3970cf2489d560ea890b0a19d38af4c51c2140` |
| `scripts/tests/generate_raw_v8_step2_inventory_v4_v49f.py` | 41,745 | `0ea8470bfe0942d92daf9aaf4d53b051264a7325f9dfe8a32f4cecdf1b39649e` |
| `scripts/tests/validate_raw_v8_step2_inventory_v4_v49f.py` | 44,131 | `eac22b7828cb65abc85e282ee4b6386e2bcf71b58473282d1610ba109e0b0124` |
| `tests/raw_v8_step2_inventory_v4_v49f.json` | 5,265,855 | physical `de91eac92d1c36cf1670b2484392fbf1c633d75f928c8e70fcd5e71ae798db2b`; semantic `d1435d11a6c9e110b5afb6dacb312f7cd92be71868b2ebe1c8f69ba7f1def3fd` |
| `tests/test_raw_v8_step2_inventory_v4_v49f.py` | 37,504 | `650f4d6879dcd1f82b06e97102a386fd74f4834d180c73ffd3cc240c724cfca3` |
| Accepted V3 contract harness | 129,364 | `6bbc1038f41bb5d78f921e68216951bbfa6c1cbc31c2fe96dd3172b545b7dcac` |
| `tests/_raw_v8_step2_contract_harness_v4_v49f.py` | 10,929 | `bc3d286a306344b40fed8c4de75efacd8731d8a6bfa5527ff0d7ae2169b95a28` |
| `tests/test_trading_physical_transport_capacity_contracts_v49f_v8_v4_isolated.py` | 3,273 | `777ba9c36b1d6f1f1a7c6287a0b57296272194f84836d398efc32e55704937cd` |

The 408 ordered maximum-scope profile IDs retain canonical-list SHA-256
`b50b97b682d5707062867f2789a204e0488bdc95be7977f9ddc408959d1c9e0e`.
The independently derived 474-row universe has canonical JSON SHA-256
`836db59c1111080882dea078a27847b130d18eed474a8982ebad2e062d532d1c`.

## 3. Exact migration proof

The migrator starts from the physically and semantically pinned V3 golden,
deep-copies it, applies the authorized patch, then reverses exactly that patch
and requires full recursive equality with V3. The reversible coordinate
classes are:

```text
/schema_version
/normative_document_inputs             # exact insertion at index 3
/invariants/inventory_schema_version
/invariants/counts/normative_document_input_count
/invariants/normative_document_sha256_by_role
/invariants/compact_maximum_proof_v2_contract
/inventory_sha256
```

The inserted input has exact position, role, path, byte count, and SHA-256.
The previous Step-3 record moves from array position four to five without any
member change. Reverting the seven coordinate classes above reproduces the
complete V3 object, not merely selected counts or hashes.

Explicit equality checks additionally prove that these remain unchanged:

- the complete standalone and embedded External Schema V2 registry;
- the target-field registry, counter schema, marker contract, selectors,
  logical-oracle catalog, operation contracts, and fixture records;
- all 408 complete maximum-constraint profile objects and IDs;
- all profile authority pointers and their ordered ID-list digest;
- the 66 intrinsic rows plus 408 profile-owned rows and their exact order; and
- every unrelated invariant.

The exact V4 compact contract is:

```text
mathematical_acceptance_rule = SOUND_UPPER_BOUND_PLUS_LEGAL_ATTAINMENT_V1
global_least_attainer_required = false
ordered_component_choice_evidence_required = false
proof_resource_report_is_separate = true
publication_selection_policy = PINNED_ACCEPTED_ATTAINER_V1
maximum_publication_row_count = 474
verifier_owned_scope_case_count = 475
```

Boolean members must be booleans rather than integer aliases. The 475 cases
are exactly 474 maximum scopes plus the separate local-shutdown problem.

## 4. Independent generation and validation

The V4 migrator and validator use only the Python standard library and do not
import each other, either V3 generator/validator, or production `riskyieldmm`
code. Both independently pin the final V4 byte count, physical SHA-256, and
semantic root identity.

The validator independently:

1. securely reads the V3 golden, standalone registry, five normative
   documents, and V4 candidate through no-follow, nonblocking descriptors;
2. rejects nonregular, multiple-link, inode-aliased, unstable, outside-root,
   oversized, duplicate-key, non-finite, float, noncanonical, or over-depth
   inputs before authority use;
3. rechecks every source after semantic validation;
4. reconstructs the expected V4 object directly from pinned V3 plus the exact
   amendment rather than importing the migrator;
5. recomputes the registry, target-field registry, all 408 profile IDs, their
   ordered digest, the complete 474-row universe, and the V4 root identity;
6. checks the exact five-input order and every compact-contract member/type;
   and
7. requires the candidate bytes to equal the complete independently rebuilt
   canonical object.

The migrator performs two complete source snapshots before construction and
another before and after check/publication. Its write path uses an exclusive
same-directory temporary, complete write, file and directory fsync, readback,
target/parent identity checks, atomic replacement, final inode/byte
verification, and temporary cleanup. It forbids V3, registry, or normative
authority paths and their inode aliases as outputs.

## 5. Runtime-consumer migration

The accepted V3 contract harness remains byte-identical. A separate V4 wrapper
first runs the pinned independent validator, reads the exact V4 authority, and
then executes the historical contract matrix with only its golden path and
inventory-schema expectation changed to V4. This proves that the byte-identical
registry and fixtures still drive the unchanged production contracts.

The first independent consumer review returned `NO-GO`: the wrapper executed
the V3 harness without authenticating that executable, so a modified or no-op
harness could masquerade as unchanged evidence. Before acceptance, the wrapper
was changed to pin and recheck both:

- the accepted V3 harness at 129,364 bytes / `6bbc1038…`; and
- the independent V4 validator at 44,131 bytes / `eac22b78…`.

It captures exact raw bytes and file identity before each execution and
requires identical after-execution snapshots. The independent re-review then
returned `GO`. The V3 harness and V3 golden remained at their accepted physical
hashes throughout.

## 6. Test evidence

The final V4 inventory/adversarial suite passes **33 tests in 21.72 seconds**.
It covers:

- deterministic write/check/second-write and exact final pins;
- exact recursive migration equality and all 408/474/475 invariants;
- fourteen independently re-signed schema, authority, profile, registry,
  pointer, fixture, and compact-contract attacks;
- relabelled V3, missing/duplicate/reordered/wrong-role amendment, wrong count
  or hash mirror, wrong root identity, and boolean/integer confusion;
- duplicate, non-finite, noncanonical, over-depth, and oversized JSON;
- outside paths, traversal, symlink, FIFO, hard-link, unsafe output, atomic
  failure/cleanup, and source-mutation attacks;
- relative repository-root/default-inventory behavior; and
- standard-library-only generator plus validator independence.

The final combined V3 predecessor, V3 adversarial, historical consumer, V4
inventory/security, and V4 consumer matrix passes **134 tests in 116.32
seconds**. The separate final V4 consumer run passes three tests in 27.20
seconds, and its independent read-only review is `GO` after the executable
trust-closure repair. Ruff format/check, `py_compile`, deterministic direct
generation/validation, documentation-link checks, and `git diff --check` are
also clean within this scope.

## 7. Nonclaims and next gate

This acceptance establishes an authority migration, not feasibility of the
proof implementation. The next gate is the separate V2 seed-protocol
candidate. It must freeze the complete grammar, recurrence/state semantics,
cache keys, meter catalog, deterministic strategy, validation/recipe schemas,
and F0 ceilings before any full-row result exists.

Two independent counting-only implementations must then agree on every metric
for all 475 verifier-owned cases. Only if all counts fit the immutable F0
ceilings may F2 limits be derived and the final V2 protocol frozen without
changing strategy or proof semantics. Both preflights must repeat against the
final protocol bytes before the independent verifier, separate generator, or
six-case pilot is authorized.

No constructive maximum, local-shutdown minimality result, runtime bound,
production compatibility, predictive edge, trading safety, live readiness, or
profitability claim follows from V4 inventory acceptance. Raw V8 Step 2,
A2-M, A2-E, and Stage 1 remain incomplete and NO-GO.

## 8. Gate state

```text
V1 feasibility rejection                 ACCEPTED
V2 compact-proof correction              ACCEPTED
V4 successor inventory                   ACCEPTED
V2 seed protocol                         NOT STARTED
two independent 475-case preflights      NOT STARTED
V2 immutable protocol freeze             NOT STARTED
independent V2 verifier                   NOT STARTED
V2 generator / six-case pilot            NOT AUTHORIZED
474 constructive maxima                  NOT STARTED
local-shutdown V2 result                 NOT STARTED
runtime-work accounting                  INCOMPLETE
production adapters / compatibility      INCOMPLETE
Raw V8 Step-2 acceptance                 NO-GO
A2-M / A2-E / Stage 1                    INCOMPLETE
```
