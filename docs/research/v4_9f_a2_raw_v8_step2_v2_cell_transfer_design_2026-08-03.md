# Raw V8 Step-2 V2 ordinary cell-transfer design

Date: 2026-08-03  
Status: **INTEGRATED — ACCEPTED WITH THE `S1-A1` SEED**

## 1. Purpose and authority boundary

This note defines the ordinary recurrence cell transfer required before the V2
seed can return to design review. Its executable oracle is:

```text
tests/test_raw_v8_step2_maximum_protocol_v2_cell_transfer_v49f.py
```

The test imports neither the generator nor `riskyieldmm`. It is challenger
evidence, not accepted protocol authority. The generator and catalog were not
edited while this design was produced.

## 2. Evaluation model

Evaluation is strict postorder and bottom-up. A result cell is exactly:

```text
cell_status
certified_lower_bound_octets
certified_upper_bound_octets
ordered_state_components
```

`PROVABLY_EMPTY` has the unique numeric normal form `(0, 0)`. A
`MAY_BE_NONEMPTY` cell satisfies:

```text
0 <= certified_lower_bound_octets
  <= certified_upper_bound_octets
  <= effective_canonical_octet_ceiling
```

The interval is an abstract enclosure. It does not claim that every integer in
the interval, or a clipped upper endpoint, is attainable. This distinction is
required by the accepted compact correction and the prior seed red-team: a
max-only child summary cannot justify discarding shorter child values needed
under an ancestor codec cap.

Every arithmetic operand and intermediate is checked `UInt128`. Boolean values
are never integers. Addition, multiplication, or subtraction overflow or
underflow rejects before committing a cell, state, cache entry, token, or byte
buffer. Upper-bound folds additionally have typed ceiling-saturating add and
multiply operations. They pre-check `ceiling - accumulator` or
`ceiling // multiplicand` and return `(ceiling, exceeded_ceiling=true)` without
constructing an overflowing intermediate. Exact equality with the ceiling
returns `exceeded_ceiling=false`. This lets an unbounded relaxed-string cell
flow through a record or array until the explicit codec intersection without
unsafe top-down pruning or arithmetic overflow. Parameters whose external
domain is I-JSON `SAFE_INTEGER` are signed and constrained to
`[-9007199254740991, 9007199254740991]`.

## 3. Effective ceiling and owner residuals

Ordinary children are not top-down-pruned using inferred owner residuals. They
are evaluated bottom-up and a subsequent `CELL_CODEC_INTERSECTION_V1` applies
each exact structured coordinate.

For one coordinate:

```text
inclusive = limit              when relation == LE
inclusive = checked_sub(limit, 1) when relation == LT

payload_ceiling = checked_sub(
    inclusive,
    minimum_sibling_and_syntax_octets,
)
```

`SELF_TYPE` requires zero sibling/syntax octets. `OWNER_PAYLOAD_RESIDUAL`
requires the complete owner overhead. The stored
`derived_payload_octet_ceiling` is challenger data only: the evaluator
recomputes it and rejects disagreement. The effective ceiling is the minimum
of the ambient ceiling and all coordinate payload ceilings.

The current seed contains eight explicit residual coordinates. The independent
test reconstructs each owner record's fixed syntax from its plan, reconstructs
each selected discriminator literal and fixed-width sibling from the standalone
registry and plan, and then recomputes all eight residuals:

```text
result alternatives: 523724, 523728, 523738, 523752
spec alternatives:    2096777, 2096781, 2096791, 2096795
```

This resolves the current result/spec owner rows without guessing. If a later
plan expects the owner residual to propagate into descendants before their
postorder cells exist, the evaluation order is ambiguous and must reject; no
such top-down rule is inferred here.

## 4. Closed transfer rules

| Opcode | Bound transfer | State |
|---|---|---|
| `CELL_FIXED_OCTETS_V1` | Exact fixed length or empty above the ceiling | empty signature |
| `CELL_BOOLEAN_LITERAL_V1` | `true=4`, `false=5`; null parameter is the exact full-domain sentinel, therefore `[4,5]` before clipping | empty signature |
| `CELL_SAFE_INTEGER_INTERVAL_V1` | Lower is the decimal length of zero or the endpoint nearest zero; upper is the maximum endpoint decimal length | empty signature |
| `CELL_FINITE_TEXT_V1` | Canonicalize every frozen literal; take exact extrema of admitted literals | empty signature |
| `CELL_BOUNDED_TEXT_OCTETS_V1` | Validate and clip the authority-derived canonical-octet interval | empty signature |
| `CELL_RELAXED_JSON_STRING_V1` | Safe superset is every canonical JSON string under the effective ceiling; empty string proves lower 2 | empty signature |
| `CELL_DERIVED_IDENTITY_V1` | Exact authority-derived canonical width | empty signature |
| `CELL_NULLABLE_V1` | Interval union of canonical `null` length 4 and admitted child | empty signature |
| `CELL_CHILD_BOUNDS_ALIAS_V1` | Clip and preserve the referenced child | child state |
| `CELL_ARRAY_BATCH_V1` | For cardinality `n`, `2 + n*item + max(n-1,0)`; lower at minimum cardinality and upper at maximum cardinality | `(ITEM_COUNT, CAPPED_ITEM_UPPER_OCTET_SUM, COMMA_COUNT)` |
| `CELL_ARRAY_STREAM_V1` | Same semantic interval as batch; physical fold is ordinal | `(ARRAY_ORDINAL, ITEM_COUNT, CAPPED_ITEM_UPPER_OCTET_SUM, COMMA_COUNT)` |
| `CELL_RECORD_V1` | Fixed record syntax plus checked ordered sums of every child lower/upper; any empty required child makes the record empty | empty signature |
| `CELL_UNION_V1` | Minimum lower and maximum upper across admitted alternatives | empty signature |
| `CELL_CODEC_INTERSECTION_V1` | Recompute every coordinate and clip the child to their minimum | child state |
| `CELL_SAFE_RELAXATION_V1` | Bound-preserving alias only after its exact relaxation evidence validates | child state |
| `CELL_SCOPE_ROOT_V1` | Bound-preserving alias only after case and fixed-authority bindings validate | child state |
| `CELL_APPLICATION_WRAPPER_V1` | Bound-preserving alias only after the complete ordered schedule validates | child state |
| `CELL_LOCAL_SHUTDOWN_SWEEP_V2` | Resolve the bound analytic catalog, replay an exact 12-state/11-transition chain, and return the terminal winner length | terminal eight-component state |

Batch and stream use the same semantic bound equation. Batch is admissible only
when its separately validated observer closure says `batch_eligible=true` and
its ordered runs cover the exact maximum cardinality. This transfer design does
not itself prove the observer closure.

## 5. Required catalog surface

Each transfer-opcode record must have only:

```text
opcode_position
opcode
semantic_rule
ordered_required_parameter_names
child_read_mode
state_rule
transfer_rule_id
unknown_or_extra_member_policy
```

The independent test freezes the exact value of those fields for all 18
opcodes. `semantic_rule`, `child_read_mode`, and `state_rule` are diagnostic
enums. They are not executable authority. `transfer_rule_id` must resolve one
complete rule in a separately identity-bound `transfer_rule_catalog`.

That catalog carries:

```text
transfer_rule_catalog_version
evaluation_order
unknown_or_extra_ast_member_policy
ordered_primitive_opcode_records
ordered_transfer_rule_records
transfer_rule_catalog_id
```

Each rule freezes its exact parameter order, `CELL` result type, complete AST,
and semantic identity. Each primitive record freezes exact operands, operand
type rule, result type, and reject-extra policy. The reference design has
low-level typed primitives for constants, parameters, child reads, lexical
bindings, lazy branches, validation, Boolean/order operations, mapping fields,
indexed list maps/filters/folds, checked and ceiling-saturating `UInt128`
arithmetic, decimal/string canonical lengths, cell construction/clipping/state,
identity-bound subrule calls, and local-catalog resolution.

The independent test executes the reference AST for all 18 transfer families
and compares the results with separately authored hand micro-oracles. Once the
seed publishes the catalog, the same test follows each catalog opcode's
`transfer_rule_id`, interprets the catalog-carried AST, and compares those
results with the same hand oracles. A high-level `semantic_rule` label plus a
challenger-only Python dispatcher is explicitly insufficient.

The arithmetic policy must similarly contain closed records for checked add,
subtract, multiply, ceiling-saturating add, ceiling-saturating multiply, and
nonempty minimum. Executable strings such as `saturating_add_formula` and
`saturating_multiply_formula` are forbidden.

The transfer parameter grammar must add `SIGNED_SAFE_INTEGER`; both
`integer_minimum` and `integer_maximum` use it. Probe values remain independently
recomputed metering inputs and do not replace endpoint validation.

## 6. Profile-conditioning interface

The prospective generator now binds all 408 profiles, fixed authorities,
scope cases, exact application-count schedules, and one identity-bound
dual-channel `conditioning_transfer_program` per profile. The old detached
`DERIVE_EXACT_PROFILE_CONDITIONED_UPPER_BOUND_V1` label is no longer the
acceptance mechanism.

The profile layer therefore needs a typed cell pipeline:

```text
template root cell
  -> scope operation with exact fixed-authority and scope-case inputs
  -> application fold with the complete ordered cross-rule schedule
  -> typed P2 derivation program
  -> conditioned-cell intersection
  -> independent P3 witness-length equality check
```

Each operation consumes the preceding operation position and emits a typed
cell or conditioning state. The `p2_upper_bound_program` produces either a
tagged `SUPERSET_UPPER_BOUND` or `EXACT_ATTAINED_MAXIMUM` cell. Generic
profiles retain the structural-template superset as P2 and explicitly make no
generic attainability claim. Their separate `p1_p3_attainment_program` loads
the retained witness and fixed authorities, matches the exact scope case,
reconstructs and executes the pinned application schedule, measures the
retained canonical bytes, and accepts only when P1 is true and the measured
length equals the P2 upper bound. P3 therefore never supplies or silently
tightens P2.

For case 69, the existing local analytic catalog can supply an explicit
intersection only through the typed program frozen by the independent test:

```text
LOCAL_SHUTDOWN_BASELINE_ANALYTIC_INTERSECTION_V1
  input application operation = 3
  fixed spec operation = 1
  fixed member path = spec/maximum_terminal_ingress_batches
  bound local analytic catalog ID
  bound batch_unsaturated_program locator
  independently execute 2312 + 268*b + decimal_width(b)
  compare expected derived upper = 2581
  intersect child upper, preserving lower and state
```

The challenger independently verifies the fixed spec pointer, ID, canonical
octets, SHA-256, local-catalog baseline binding, typed integer, program range,
and checked arithmetic before deriving 2581. Reading the stored 2581 alone is
forbidden. Case 69 now executes that analytic path and intersects the incoming
cell to an `EXACT_ATTAINED_MAXIMUM` cell with lower and upper both 2,581.

## 7. Current independent result

The accepted, serialized seed passes the reference AST micro-oracles,
direct hand micro-oracles, UInt128 rejection paths, strict postorder child
bindings, all eight independently reconstructed owner residuals, all 18 typed
opcode contracts, semantic-ID and earlier-subrule closure, structured
arithmetic, signed-safe-integer validation, and the case-69 analytic
intersection. Unknown opcodes, extra members, wrong semantic identities, and
forward subrule calls reject in the source-security suite.

The controlled regeneration, byte-identical rewrite check, full focused
matrix, and S1-A1 acceptance packet are recorded in
[`v4_9f_a2_raw_v8_step2_maximum_protocol_v2_seed_acceptance_2026-08-09.md`](v4_9f_a2_raw_v8_step2_maximum_protocol_v2_seed_acceptance_2026-08-09.md).
That narrow seed acceptance is not evidence that a V2 maximum, local
minimality result, Raw V8, or Stage 1 has passed.
