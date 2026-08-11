# Raw V8 Step-2 V2 case-435 packed-context boundary acceptance

**Date:** 2026-08-10  
**Formal parent gate:** `A4-P6-V`  
**Bounded prerequisite:** `A4-P6-V3-T`  
**Decision:** `ACCEPTED`  
**Stage 1:** `NO-GO`

## 1. Outcome

The case-435 V3 implementation audit found and closed a physical transport
contradiction before verifier code was allowed to accept the case.

The accepted successor verifier pins 38 authority files before reading a
candidate. The immutable F0 ceiling permits 64 input files. The inherited
flat context transport requires one file per non-inline context object, but
case 435 requires:

```text
1 root context object
+ 67 observations
- 1 inline measured witness
= 67 context-object files
```

Therefore the inherited minimum is:

```text
38 authorities + 1 candidate + 67 context objects = 106 input files
106 > F0 INPUT_FILE_COUNT 64
```

This is a protocol-level incompatibility, not a performance problem and not a
reason to raise F0. The additive correction accepted here transports the 67
complete logical context objects in one compact canonical context-pack file:

```text
38 predecessor/successor authorities
+ 1 packed-context boundary authority
+ 1 candidate
+ 1 context pack
= 41 input files
```

The corrected path has 23 file slots of headroom. It changes only case 435's
candidate-side physical transport. Logical context-object IDs, record
references, complete typed records, output context-object files, and receipt
entries remain unchanged.

## 2. Evidence that packing fits the existing byte ceiling

An out-of-process reconstruction of the accepted C2 retained context executed
the complete frozen 137-application schedule and measured:

| Measurement | Result |
|---|---:|
| observations | 67 |
| unique observation IDs | 67 |
| root plus observation logical records | 68 |
| sum of compact logical-record octets | 12,873,935 |
| largest record / inline witness | 257,887 |
| conservative single-pack diagnostic including the inline witness | 12,877,592 |
| immutable individual-file strict upper bound | 16,777,216 |
| P1 application invocations | 137 |
| charged rule evaluations | 12,531 |
| direct expression nodes | 125,431 |

The contracted pack excludes the inline witness, so the conservative
12,877,592-octet diagnostic is an upper measurement for the eventual V3
fixture. V3 must still reconstruct and measure its independent pack under F0;
this transport acceptance is not a witness or a case-435 verifier acceptance.

The diagnostic used C2 only to falsify/measure transport. Neither the new
authority nor the verifier may consume the C2 certificate, constructor output,
or a stored witness as acceptance input.

## 3. Alternatives evaluated

| Alternative | Assessment | Decision |
|---|---|---|
| Raise `INPUT_FILE_COUNT` above 64 | Makes the fixture fit by changing an immutable safety ceiling | Rejected |
| Exempt context objects from F0 | Misstates the actual pinned input surface | Rejected |
| Stop pinning accepted authorities | Breaks source isolation and the predecessor/successor read barrier | Rejected |
| Embed summary hashes instead of complete records | Cannot replay P1 on retained bytes and permits substitution | Rejected |
| Reconstruct missing context inside the verifier | Makes the verifier partly act as producer and removes hostile record mutation coverage | Rejected |
| Rewrite the accepted D boundary in place | Invalidates an accepted authority and its transitive identities | Rejected |
| Add one versioned compact context pack | Preserves complete records and all logical identities while satisfying unchanged F0 | **Selected** |

Packing is preferable to inline derivation because it retains the producer's
complete bytes as untrusted data. The verifier must still independently parse,
type-check, identify, hash, and execute those records.

## 4. Accepted transport contract

The additive authority is selected by a distinct boundary path. The old
successor boundary remains valid for V0/V1/V2 and must continue to reject case
435.

For case 435 only, the corrected candidate uses:

```text
candidate_kind = MAXIMUM_WITNESS_PACKED_CONTEXT

candidate payload:
  candidate_kind
  witness_record
  scope_witness_context
  ordered_context_pack_entries
```

The single pack contains exactly 67 logical context-object records, strictly
ordered by `maximum_context_object_id`. Every record entry carries:

```text
context_object_position
maximum_context_object_id
record_type_name
record_identity_field
record_identity
record_canonical_byte_length
record_canonical_sha256
record
```

The pack itself is exact compact canonical UTF-8 JSON with no trailing byte.
Its ID covers the full ordered record set. The candidate's pack entry binds
the pack ID, first/last object IDs, count, path, byte length, and raw SHA-256.

The verifier must reject unknown, duplicate, missing, extra, overlapping,
misordered, noncanonical, oversized, path-aliased, symlinked, hardlinked, or
replaced packs/records. It must prove that every and only `CONTEXT_OBJECT`
reference recursively reachable from `scope_witness_context` resolves exactly
once. The inline witness must not also appear in the pack.

After verification, the pack is not published as a mathematical shortcut.
The verifier unpacks the accepted complete records into the inherited compact
context-object files and emits the inherited logical receipt entries.

## 5. Non-drift boundary

The correction leaves these accepted values unchanged:

| Authority | Unchanged value |
|---|---|
| successor seed | `7fad47e881624d0f39809e72ce2d3d3fd81fb8c85f854fe8332faf543cd1120b` |
| successor manifest | `6aed1139c158f8685bcb226697a2efe57af3c42f57831173bd7b3ea169025d9c` |
| maximum-protocol SHA-256 | `daa55d18aa8adfcef9b8a6ea2c6fa734f7922888a902eb863c6307c0fc13bacf` |
| F2 catalog | `5b2171f64c082ddaa5ecbeb19e2e2f5b952c07336a097364f23fd1658c3d944f` |
| case-435 program | `160486e8c6023b4cfb7ac430065a1dd8c8c422342535fbd5b9b0bceb2ca2e820` |
| case-435 plan | `343259e38b6050fac5905fdc7ed6dca6d345d32c07b8370085bdf865793e7ad8` |
| exactness join | `2abf00603826f93bb6a538511bbd49ee45096901edbf9bc63c7d0cefb9e7fc3f` |
| exact maximum | 257,887 canonical octets |

No F0 or F2 value was changed. Candidate transport for cases 5, 24, 54, and
69 is unchanged. Case 475 remains unsupported during V3.

## 6. Accepted artifacts and checks

| Artifact | Bytes | SHA-256 / semantic ID |
|---|---:|---|
| `scripts/tests/generate_raw_v8_step2_maximum_protocol_v2_case435_context_pack_boundary_v49f.py` | 14,831 | `78f33ab0c7d4e5c3df57ae8ee2b467a77de216039ffe6d5cb16e9e64de8549df` |
| `scripts/tests/check_raw_v8_step2_maximum_protocol_v2_case435_context_pack_boundary_v49f.py` | 18,464 | `6eae49c048f06eae352269ea277a1e450cbaac6bf29811c65742c4fe36e6c408` |
| `scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_context_pack_boundary_delta_v49f.json` | 6,049 | raw `985f0d67a545d036f1777a627f01b609d396a39c690ac81c1bacfc4f7563f56b`; ID `c8448f57dcdc3e4f1f3239043ed4977013efbd99c750cb2e2e857025f5ac0acd` |
| `tests/test_raw_v8_step2_maximum_protocol_v2_case435_context_pack_boundary_v49f.py` | 9,658 | `a81db42f06bb592d47b67513a8bf9b8e99cddb00cc90ead7d7cabe398d46daf4` |

Focused result:

```text
17 passed in 5.27s
```

The suite independently recomputes the F0 contradiction, correction identity,
exact schemas, predecessor binding, unchanged mathematical authority IDs, and
corrected file count. Eleven re-sealed mutations reject, including limit,
F2, count, payload-schema, C2-trust, flat-transport, publication, path, and
extra-claim mutations. Generator/checker separation and deterministic CLI
output are also enforced.

## 7. Next action and stop conditions

Resume `A4-P6-V3` against the new packed-context boundary. V3 must:

1. independently construct a packed case-435 fixture without importing the
   verifier or a stored C2 certificate;
2. resolve/unpack all 67 logical context objects and the one inline ordinal-64
   witness;
3. execute the complete 137-invocation P1 schedule;
4. prove P2/P3 equality at 257,887 octets;
5. enforce every immutable F2 metric; and
6. preserve V0/V1/V2 and predecessor case-5 behavior while case 475, producer,
   and runner remain fail-closed.

Stop and reopen this transport correction if one pack cannot satisfy the
immutable per-file/total-octet/node/depth ceilings, any logical context or
record-reference identity must change, accepted D bytes drift, output cannot
be reproduced in the inherited logical format, or a limit must be raised.

This acceptance does not accept case 435, the expanded verifier, the producer,
the runner, the six-case pilot, Stage 1, Stage 2, predictive edge, or
profitability.
