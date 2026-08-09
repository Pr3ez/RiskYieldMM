# Raw V8 Step-2 V2 event-metadata amendment

Date: 2026-08-09  
Status: **ACCEPTED S1-A1 AMENDMENT; S1-A2 BOUNDARY REFROZEN**

## 1. Decision

The first S1-A2-A dry run falsified one remaining ambiguity in the accepted
seed. The case-event grammar defined event kinds, emission order, subject
constructors, and cardinalities, but it did not bind four token metadata
values at each emission position:

- `subject_role`;
- `subject_ordinal` source;
- `observed_value` source; and
- ordinary-step versus null `logical_derivation_step_position` source.

Those values affect canonical event-token bytes and therefore every complete
case's event-stream digest. Letting preflights A and B independently invent
them would make agreement depend on an unstated shared assumption. S1-A2 was
therefore paused before either result vector existed, the missing authority
was added to S1-A1, and the dependent data-only preflight boundary was
refrozen.

This is a bounded correction, not a new maximum-proof design. It does not add
an expected 475-case vector, an executable preflight helper, or a witness.

## 2. Corrected authority

The case-event grammar now publishes exactly one
`event_metadata_program` with version
`riskyieldmm.raw_v8_step2_external_schema_v2.event_metadata_program.v1`.
Its binding rule is:

```text
ZIP_PROGRAM_POSITION_THEN_EMISSION_POSITION_AND_MATERIALIZE_METADATA_ON_EMISSION_RECORD_BEFORE_TOKENIZATION_V1
```

The program has one metadata record for each of the nine ordered case
programs and one aligned entry for every emission. It freezes:

- exact uppercase subject-role literals;
- subject-ordinal sources from the closed enum `NULL`,
  `EMISSION_SUBJECT_COLLECTION_ORDINAL`, `EVENT_KIND_ORDINAL`, and
  `DERIVATION_UNIT_ORDINAL`;
- observed-value sources from the closed enum `NULL` and
  `SUBJECT_OBSERVED_VALUE`; and
- logical-step sources from the closed enum `NULL` and
  `CURRENT_ORDINARY_TEMPLATE_STEP_POSITION`.

Only the ordinary postorder program may use the current ordinary template
step. Observed values are present exactly on retention, derivation-depth, and
iteration-depth observations. Unknown members, missing rows, duplicate rows,
misaligned array lengths, unknown sources, and role substitutions are
rejected.

The local controller deliberately binds all twelve state emissions, not only
the terminal state. Its exact state roles are:

```text
LOCAL_CONTROLLER_STATE_RESULT_CELL
LOCAL_CONTROLLER_STATE_CACHE_KEY
```

This prevents the earlier terminal-only microfixture vocabulary from being
silently applied to the full local-controller case.

## 3. Boundary refreeze

Because the accepted seed bytes and semantic roots changed, the S1-A2 shared
contract was regenerated against the amended seed. The refreeze also closes
three version literals that the first boundary encoded in schemas but did not
pin as values:

| Payload | Frozen version |
|---|---|
| Semantic payload | `riskyieldmm.raw_v8_step2_external_schema_v2.preflight_semantic_payload.v1` |
| Execution envelope | `riskyieldmm.raw_v8_step2_external_schema_v2.preflight_execution_envelope.v1` |
| Comparison payload | `riskyieldmm.raw_v8_step2_external_schema_v2.preflight_comparison_payload.v1` |

No expected case, metric, or event-stream result was added to the boundary.

## 4. Current identities

| Artifact or identity | Accepted value |
|---|---:|
| Event grammar bytes | 131,015 |
| Event grammar raw SHA-256 | `72bfd44ff159eb6904936ae32d0d25ab9b0c8536b87f5e93d055b521679401c8` |
| Generator raw SHA-256 | `47b4ecada8c661185e4087787b99e113b2366ff87ee06e951a21a85b9a4cab4f` |
| Seed catalog bytes | 13,419,905 |
| Seed catalog raw SHA-256 | `a75a2f352e8513b7ff0043693a0c65ebbf4bc6f06859354789af69e1162b0e4f` |
| Seed semantic catalog ID | `ac22151fa74702ac1488924f01161eaa38574545e6272a290db6b0bbd288ae5f` |
| Protocol-counting-semantics ID | `34f6c285e1ce5c2b0496a63f6eda3ee15f72d6268f5ba9dbb0748e01e61d38fb` |
| Logical-event-catalog ID | `072733938c00a6617fd59375a76ec9824590a0c140e32430efd7009ce1d77c4b` |
| Preflight contract bytes | 16,919 |
| Preflight contract raw SHA-256 | `007ed9a8d06b91f73708129b66a33eaf525e203d306426d05b8cd8bba9c7294b` |
| Preflight contract semantic ID | `6609ad7b9abf21432136e49af178e20c17cb7bc27d3b444a4b6f01a17073fc76` |

The case-universe, logical-plan-recipe, recurrence, resource-metric, and F0
semantic roots are unchanged:

```text
case universe:       65376f9ceb08f91f0476b6f97ffa3fe3896a140a99b289388ccc3e453cc4c652
logical plan recipe: 727f4008c6cd469fe2a9c7f833b0bb6a56ba18a17009871e7fb4ceaa2c0aede8
recurrence:          743ab1fdf8f15da1b38331dc23fcf79dd4a89c2767013afba421107deeeecbcd
resource metrics:    1d15e95819fa32d37e7b6eaadc1a9ae410db56f347bf8ead583d0d31f9493652
F0 ceilings:         89a8803593c1225b237a4646de06a2b2f6cf495859199048fdabfa6e97e083b4
```

The seed retains 2,308,735 bytes of headroom below the 15,728,640-byte
operational target and 3,357,311 bytes below the 16,777,216-byte strict
individual-file ceiling.

## 5. Acceptance evidence

The full seed/security matrix now contains 108 tests. Seven new hostile tests
reject a dropped metadata row, wrong binding rule, missing role, obsolete local
role, invalid observed-value source, invalid ordinal source, and invalid step
source. The refrozen boundary has 13 tests, including a version-literal
mutation.

```bash
python scripts/tests/generate_raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.py --write
python scripts/tests/generate_raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.py --check
python scripts/tests/generate_raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.py --write
python scripts/tests/generate_raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.py --check

pytest -q \
  tests/test_raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.py \
  tests/test_raw_v8_step2_maximum_protocol_v2_local_state_v49f.py \
  tests/test_raw_v8_step2_maximum_protocol_v2_recurrence_v49f.py \
  tests/test_raw_v8_step2_maximum_protocol_v2_profile_conditioning_v49f.py \
  tests/test_raw_v8_step2_maximum_protocol_v2_cell_transfer_v49f.py \
  tests/test_raw_v8_step2_maximum_protocol_v2_event_grammar_v49f.py \
  tests/test_raw_v8_step2_maximum_protocol_v2_full_case_execution_closure_v49f.py \
  tests/test_raw_v8_step2_maximum_protocol_v2_preflight_contract_v49f.py \
  tests/test_raw_v8_step2_maximum_protocol_v2_source_security_v49f.py
```

Observed result: **121 passed, 0 failed**. The first eight seed/security suites
account for 108 tests and the boundary suite accounts for 13. Generator
write/check/write/check reproduced the same seed bytes, raw hash, and semantic
ID. Targeted Ruff format and lint checks passed.

## 6. Gate effect

`S1-A1` remains `ACCEPTED`, now under this amendment. `S1-A2` remains the sole
active mutable gate. Its `A2-B0` shared data boundary is frozen under the new
contract identity, and `A2-A` is the next bounded implementation.

The dry run did not produce a valid preflight-A result, so it is not counted
as partial S1-A2 acceptance. Preflight A must derive all metadata through the
new program; hard-coded role or ordinal tables are prohibited.

## 7. Nonclaims

This amendment does not accept preflight A or B, their comparator or
agreement, final V2 limits, a constructive maximum, Raw V8 Step 2/3, A2-M,
A2-E, Stage 1, offline Stage 2, paper/live activation, predictive edge,
trading safety, or profitability.
