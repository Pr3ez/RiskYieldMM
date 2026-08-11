# Raw V8 Step-2 V2 all-case verifier foundation design

Date: 2026-08-11  
Packet: `A4-R475-V0`  
Status: **DESIGN FROZEN — FOUNDATION ONLY**  
Formal Stage 1 state: **NO-GO**

## 1. Decision

`A4-R475-V0` creates the new versioned verifier authority required by the
accepted `A4-R475-T` campaign contract. V0 implements only:

1. an exact all-case contract and authority resolver;
2. independent reconstruction of all 475 effective case/plan bindings;
3. the unique base-seed versus corrected case-435 successor dispatch;
4. a securely pinned complete External Schema V2 typed-value and rule-AST
   runtime; and
5. the fixed single-case CLI with a mandatory rejection after the complete
   authority barrier and before candidate or output access.

V0 accepts zero constructive cases. `A4-R475-V1`, not V0, is responsible for
the 66 intrinsic-template cases and six-case regression.

## 2. Alternatives evaluated

| Architecture | Benefit | Decisive problem | Decision |
|---|---|---|---|
| Widen the accepted pilot verifier in place | Small apparent change | Forbidden by `A4-R475-T`; destroys the byte-frozen six-case regression authority | Rejected |
| Copy the complete 373,327-octet pilot verifier | Immediate access to six special algorithms | Imports pilot dispatch assumptions, duplicates a large surface, and makes accidental V0 case acceptance likely | Rejected |
| Wrap or import the pilot verifier | Minimal source | Violates the new role’s no-other-role execution and source-independence contract | Rejected |
| Implement a second unpinned typed interpreter | Verifier-owned code | Duplicates the accepted 249,268-octet runtime and creates a new semantic implementation that would require a full independent operator/application qualification | Rejected |
| Fresh resolver plus exact pinned accepted runtime, with a candidate-access barrier | Small auditable V0, complete typed foundation, preserves later extension points | Requires strict pinning, race rechecks, and explicit distinction between runtime capability and constructive acceptance | **Selected** |

The selected design minimizes semantic duplication while keeping the verifier,
producer, runner, and pilot roles separate.

## 3. Authority barrier

The verifier accepts exactly the repository-local all-case campaign contract:

```text
contract ID  9be94bf6b53b612d62ac26bc74133f25c1101a0962987a855e65cdcd06418583
raw SHA-256  3ca4ff4d6e581895b813043e7fdeed24c33cf2c828e362ac81de1725e95a84bb
raw octets   382710
```

It then opens, snapshots, hashes, parses, and later rechecks the contract’s 13
ordered authorities. It additionally pins:

- its own versioned source path;
- the accepted typed-rule runtime source;
- the structural registry; and
- the rule-literal authority.

Every input must be a direct, single-link regular file under a lexically
canonical, symlink-free repository path. Duplicate inodes, changed metadata,
changed bytes, unknown records, unsafe JSON numbers, duplicate keys, excess
JSON structure, or F0 excess reject.

The resulting V0 footprint is 18 authority files and 16,717,988 pinned octets,
leaving 46 file slots and 50,390,876 octets under immutable F0. No limit is
raised or repaired from observations.

## 4. Exact case resolution

The resolver independently reconstructs positions 1 through 475 from the
base seed, logical-plan catalog, case-plan bindings, and accepted case-435
successor delta. It does not trust the contract’s copied case rows alone.

- case 435 alone resolves to successor plan
  `343259e38b6050fac5905fdc7ed6dca6d345d32c07b8370085bdf865793e7ad8`;
- all other 474 positions resolve to the byte-exact base-seed plan at the same
  one-based position;
- every case-execution record ID, the ordered-ledger hash, and the ledger ID
  are recomputed; and
- the independently derived family census must be exactly 66 intrinsic, 406
  generic profile, and one each signed analytic, corrected application, and
  local minimality.

## 5. Typed runtime boundary

The accepted External Schema V2 runtime is loaded only from its exact pinned
source bytes. V0 verifies its registry and literal authorities and requires
the complete capability surface:

- 236 value schemas;
- 52 external types;
- 42/42 executable rules, comprising 33 generic and 9 complex rules;
- 41 generic and 11 complex operators;
- 8 executable applications; and
- 2 fixed-position resolvers.

The runtime executes a structured rule AST. It does not call Python `eval`,
load producer output as proof, solve a constructive maximum, or authorize a
case. V0 exposes typed-value and rule-AST functions for later verifier packets,
with complete authority rechecks before execution.

## 6. Candidate-access barrier

The CLI inherits the exact four fixed-order A4-B0 options:

```text
--repository-root --boundary --candidate-root --output-root
```

V0 lexically parses all four values, loads and rechecks the complete authority
foundation, deletes the candidate/output arguments from the executable V0
path, and returns the stable `FOUNDATION_ONLY` rejection. It never requires,
opens, creates, deletes, repairs, or normalizes either candidate or output.

This makes premature case acceptance impossible through the CLI while leaving
the interface stable for V1 through V3.

## 7. Independent acceptance design

The independent reviewer must not import the verifier. It instead:

1. reconstructs all 475 case rows from the seed and delta;
2. inspects the verifier AST and fixed call order;
3. rejects pilot-role imports and forbidden execution helpers;
4. runs two isolated verifier CLI replays with absent candidate/output paths;
5. runs two isolated typed-runtime replays;
6. proves both replay pairs byte-identical;
7. independently reconstructs F0 use; and
8. seals a deterministic foundation-only report.

Hostile tests coherently reseal case-ledger, role-state, acceptance-count,
next-packet, and resource overclaims. Byte resealing is never sufficient when
the independently reconstructed authority or scope differs.

## 8. Research boundary and nonclaims

No external web research is required for this packet. The decision is governed
by repository-specific byte authorities, fixed schemas, and an already
qualified local typed runtime; external literature cannot redefine them.

V0 does not accept a witness, prove a maximum, qualify any of the 66 intrinsic
cases, qualify generic profiles, reproduce six pilot results, implement the
producer or runner, start the campaign, accept Raw V8 Step 2, exit Stage 1, or
claim trading safety, predictive edge, live readiness, or profitability.

After independent V0 acceptance, the sole next packet is `A4-R475-V1`.
