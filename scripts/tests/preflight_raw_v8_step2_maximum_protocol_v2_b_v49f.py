#!/usr/bin/env python3
"""Independent flat-ledger execution of the frozen Raw V8 Step-2 V2 seed.

Algorithm marker: FLAT_LEDGER_PREFIX_SUM_V1

This program deliberately shares no executable helper with preflight A.  It
reads only the identity-pinned seed, evaluates the linked transfer-rule ASTs,
exports exact subject bytes to a flat per-case ledger, and obtains M1--M18 in
one ordered prefix reduction over that ledger.
"""

import hashlib
import json
import os
import pathlib
import sys

U128_MAX = (1 << 128) - 1
SAFE_INTEGER_MAX = (1 << 53) - 1
PUBLISHED_MAXIMUM = 9007199254740991
SEED_OCTETS = 13419905
SEED_SHA256 = "a75a2f352e8513b7ff0043693a0c65ebbf4bc6f06859354789af69e1162b0e4f"
SEED_ID = "ac22151fa74702ac1488924f01161eaa38574545e6272a290db6b0bbd288ae5f"
CONTRACT_ID = "6609ad7b9abf21432136e49af178e20c17cb7bc27d3b444a4b6f01a17073fc76"
PROTOCOL_SEMANTICS_ID = (
    "34f6c285e1ce5c2b0496a63f6eda3ee15f72d6268f5ba9dbb0748e01e61d38fb"
)
ROOT_IDENTITIES = {
    "case_universe_catalog": "65376f9ceb08f91f0476b6f97ffa3fe3896a140a99b289388ccc3e453cc4c652",
    "logical_plan_recipe_catalog": "727f4008c6cd469fe2a9c7f833b0bb6a56ba18a17009871e7fb4ceaa2c0aede8",
    "recurrence_catalog": "743ab1fdf8f15da1b38331dc23fcf79dd4a89c2767013afba421107deeeecbcd",
    "resource_metric_catalog": "1d15e95819fa32d37e7b6eaadc1a9ae410db56f347bf8ead583d0d31f9493652",
    "logical_event_catalog": "072733938c00a6617fd59375a76ec9824590a0c140e32430efd7009ce1d77c4b",
    "f0_seed_ceiling_catalog": "89a8803593c1225b237a4646de06a2b2f6cf495859199048fdabfa6e97e083b4",
}
ROOT_ID_MEMBERS = {
    "case_universe_catalog": "case_universe_catalog_id",
    "logical_plan_recipe_catalog": "logical_plan_recipe_catalog_id",
    "recurrence_catalog": "recurrence_catalog_id",
    "resource_metric_catalog": "resource_metric_catalog_id",
    "logical_event_catalog": "logical_event_catalog_id",
    "f0_seed_ceiling_catalog": "f0_seed_ceiling_catalog_id",
}
F0_VALUES = [
    16777216,
    67108864,
    64,
    96,
    2097152,
    1048576,
    1048576,
    14400,
    28800,
    2147483648,
    4294967296,
    8589934592,
]
EXPECTED_TOP_KEYS = {
    "canonicalization_version",
    "case_universe_catalog",
    "catalog_version",
    "f0_seed_ceiling_catalog",
    "identity_envelope_version",
    "logical_event_catalog",
    "logical_plan_recipe_catalog",
    "measurement_schema_version",
    "ordered_authority_binding_records",
    "ordered_identity_domain_records",
    "protocol_counting_semantics_id",
    "protocol_version",
    "recurrence_catalog",
    "resource_metric_catalog",
    "seed_catalog_id",
    "unicode_authority_manifest",
}
ERROR_EXIT = {
    "INVOCATION_INVALID": 2,
    "INPUT_AUTHORITY_INVALID": 3,
    "INPUT_RACE_DETECTED": 3,
    "INPUT_LIMIT_EXCEEDED": 3,
    "INPUT_CANONICALIZATION_INVALID": 4,
    "INPUT_SCHEMA_INVALID": 4,
    "INPUT_IDENTITY_INVALID": 4,
    "CHECKED_ARITHMETIC_REJECT": 5,
    "CASE_SEMANTIC_REJECT": 5,
    "RESOURCE_LIMIT_EXCEEDED": 6,
    "FORBIDDEN_DEPENDENCY": 7,
    "OUTPUT_ATOMICITY_INVALID": 8,
    "OUTPUT_SCHEMA_INVALID": 8,
    "INTERNAL_FAIL_CLOSED": 9,
}


class Failure(Exception):
    __slots__ = ("code", "message")

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


class Cell:
    __slots__ = ("status", "lower", "upper", "state")

    def __init__(self, status, lower, upper, state):
        self.status = status
        self.lower = lower
        self.upper = upper
        self.state = tuple(state)


class Capped:
    __slots__ = ("value", "exceeded")

    def __init__(self, value, exceeded):
        self.value = value
        self.exceeded = exceeded


def fail(code, message):
    raise Failure(code, message)


def canonical(value):
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        fail("INPUT_CANONICALIZATION_INVALID", str(exc))


def pretty(value):
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                indent=2,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        fail("OUTPUT_SCHEMA_INVALID", str(exc))


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def report_identity(domain, payload):
    return sha(canonical({"domain": domain, "payload": payload}))


def semantic_identity(seed, identity_name, payload):
    identities = seed["ordered_identity_domain_records"]
    row = next(
        (item for item in identities if item["identity_name"] == identity_name), None
    )
    if row is None:
        fail("INPUT_IDENTITY_INVALID", "identity domain is absent")
    names = row["ordered_payload_member_names"]
    if not isinstance(payload, dict) or any(name not in payload for name in names):
        fail("INPUT_IDENTITY_INVALID", "identity payload member is absent")
    projected = {name: payload[name] for name in names}
    envelope = {
        "canonicalization_version": seed["canonicalization_version"],
        "domain": row["domain_literal"],
        "payload": projected,
        "schema_version": seed["measurement_schema_version"],
    }
    return sha(canonical(envelope)), canonical(envelope)


def plain_integer(value):
    return type(value) is int


def u128(value, label="value"):
    if not plain_integer(value) or value < 0 or value > U128_MAX:
        fail("CHECKED_ARITHMETIC_REJECT", label + " is not UInt128")
    return value


def safe_integer(value, label="value"):
    if not plain_integer(value) or not -SAFE_INTEGER_MAX <= value <= SAFE_INTEGER_MAX:
        fail("CASE_SEMANTIC_REJECT", label + " is not a signed safe integer")
    return value


def add_checked(values):
    total = 0
    for value in values:
        value = u128(value)
        if value > U128_MAX - total:
            fail("CHECKED_ARITHMETIC_REJECT", "UInt128 addition overflow")
        total += value
    return total


def subtract_checked(left, right):
    left = u128(left)
    right = u128(right)
    if right > left:
        fail("CHECKED_ARITHMETIC_REJECT", "UInt128 subtraction underflow")
    return left - right


def multiply_checked(left, right):
    left = u128(left)
    right = u128(right)
    if left and right > U128_MAX // left:
        fail("CHECKED_ARITHMETIC_REJECT", "UInt128 multiplication overflow")
    return left * right


def capped_add(ceiling, values):
    ceiling = u128(ceiling)
    total = 0
    for value in values:
        value = u128(value)
        if total > ceiling or value > ceiling - total:
            return Capped(ceiling, True)
        total += value
    return Capped(total, False)


def capped_multiply(ceiling, left, right):
    ceiling = u128(ceiling)
    left = u128(left)
    right = u128(right)
    if left > ceiling or (left and right > ceiling // left):
        return Capped(ceiling, True)
    return Capped(left * right, False)


def empty_cell(state):
    return Cell("PROVABLY_EMPTY", 0, 0, state)


def bounded_cell(lower, upper, ceiling, state):
    lower = u128(lower)
    upper = u128(upper)
    ceiling = u128(ceiling)
    if lower > upper:
        fail("CASE_SEMANTIC_REJECT", "cell lower exceeds upper")
    if lower > ceiling:
        return empty_cell(state)
    return Cell("MAY_BE_NONEMPTY", lower, min(upper, ceiling), state)


def validate_cell(cell, ceiling=PUBLISHED_MAXIMUM):
    if not isinstance(cell, Cell):
        fail("CASE_SEMANTIC_REJECT", "transfer result is not a cell")
    if cell.status == "PROVABLY_EMPTY":
        if cell.lower != 0 or cell.upper != 0:
            fail("CASE_SEMANTIC_REJECT", "empty cell is not normalized")
        return cell
    if cell.status != "MAY_BE_NONEMPTY":
        fail("CASE_SEMANTIC_REJECT", "unknown cell status")
    if not 0 <= cell.lower <= cell.upper <= u128(ceiling):
        fail("CASE_SEMANTIC_REJECT", "cell invariant failed")
    return cell


def clip_cell(cell, ceiling):
    cell = validate_cell(cell, U128_MAX)
    if cell.status == "PROVABLY_EMPTY":
        return cell
    return bounded_cell(cell.lower, cell.upper, ceiling, cell.state)


def cell_payload(cell):
    cell = validate_cell(cell)
    return {
        "cell_status": cell.status,
        "certified_lower_bound_octets": cell.lower,
        "certified_upper_bound_octets": cell.upper,
        "ordered_state_components": list(cell.state),
    }


def strict_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            fail("INPUT_CANONICALIZATION_INVALID", "duplicate JSON member")
        result[key] = value
    return result


def reject_constant(value):
    fail("INPUT_CANONICALIZATION_INVALID", "non-finite JSON number " + value)


def read_seed(argument):
    root = pathlib.Path(__file__).resolve().parents[2]
    expected = (
        root / "scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json"
    )
    supplied = pathlib.Path(argument)
    try:
        if supplied.resolve(strict=True) != expected.resolve(strict=True):
            fail("INPUT_AUTHORITY_INVALID", "seed path is not the sole authority")
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(supplied, flags)
    except Failure:
        raise
    except OSError as exc:
        fail("INPUT_AUTHORITY_INVALID", str(exc))
    try:
        before = os.fstat(descriptor)
        if not (before.st_mode & 0o170000) == 0o100000:
            fail("INPUT_AUTHORITY_INVALID", "seed is not a regular file")
        if before.st_size != SEED_OCTETS:
            fail("INPUT_LIMIT_EXCEEDED", "seed octet count differs")
        chunks = []
        remaining = SEED_OCTETS
        while remaining:
            block = os.read(descriptor, min(1048576, remaining))
            if not block:
                fail("INPUT_RACE_DETECTED", "seed ended before accepted length")
            chunks.append(block)
            remaining -= len(block)
        if os.read(descriptor, 1):
            fail("INPUT_LIMIT_EXCEEDED", "seed exceeds accepted length")
        after = os.fstat(descriptor)
        stable = (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) == (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if not stable:
            fail("INPUT_RACE_DETECTED", "seed metadata changed during read")
    finally:
        os.close(descriptor)
    raw = b"".join(chunks)
    if sha(raw) != SEED_SHA256:
        fail("INPUT_AUTHORITY_INVALID", "seed raw SHA-256 differs")
    try:
        seed = json.loads(
            raw,
            object_pairs_hook=strict_pairs,
            parse_constant=reject_constant,
        )
    except Failure:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail("INPUT_CANONICALIZATION_INVALID", str(exc))
    if pretty(seed) != raw:
        fail("INPUT_CANONICALIZATION_INVALID", "seed pretty canonical bytes differ")
    validate_json_limits(seed)
    validate_seed_boundary(seed)
    return seed, raw


def validate_json_limits(seed):
    ceilings = seed["f0_seed_ceiling_catalog"]["ordered_platform_ceiling_records"]
    values = [row["ceiling_value"] for row in ceilings]
    if values != F0_VALUES:
        fail("INPUT_SCHEMA_INVALID", "F0 platform ceilings differ")
    node_count = 0
    array_entries = 0
    object_members = 0
    maximum_depth = 0
    work = [(seed, 1)]
    while work:
        value, depth = work.pop()
        node_count += 1
        maximum_depth = max(maximum_depth, depth)
        if isinstance(value, dict):
            object_members += len(value)
            work.extend((child, depth + 1) for child in value.values())
        elif isinstance(value, list):
            array_entries += len(value)
            work.extend((child, depth + 1) for child in value)
    if maximum_depth > F0_VALUES[3]:
        fail("INPUT_LIMIT_EXCEEDED", "JSON nesting depth exceeds F0")
    if node_count > F0_VALUES[4]:
        fail("INPUT_LIMIT_EXCEEDED", "JSON node count exceeds F0")
    if array_entries > F0_VALUES[5] or object_members > F0_VALUES[6]:
        fail("INPUT_LIMIT_EXCEEDED", "JSON collection count exceeds F0")


def validate_seed_boundary(seed):
    if set(seed) != EXPECTED_TOP_KEYS:
        fail("INPUT_SCHEMA_INVALID", "seed root members differ")
    if seed["seed_catalog_id"] != SEED_ID:
        fail("INPUT_IDENTITY_INVALID", "seed identity differs")
    if seed["protocol_counting_semantics_id"] != PROTOCOL_SEMANTICS_ID:
        fail("INPUT_IDENTITY_INVALID", "protocol semantics identity differs")
    if seed["catalog_version"] != (
        "riskyieldmm.raw_v8_step2_external_schema_v2.maximum_protocol_v2_seed_catalog.v1"
    ):
        fail("INPUT_SCHEMA_INVALID", "seed version differs")
    for root_name, expected in ROOT_IDENTITIES.items():
        root = seed[root_name]
        if root.get(ROOT_ID_MEMBERS[root_name]) != expected:
            fail("INPUT_IDENTITY_INVALID", root_name + " identity differs")
    cases = seed["case_universe_catalog"]["ordered_case_bindings"]
    plans = seed["logical_plan_recipe_catalog"]["ordered_logical_count_plan_records"]
    metrics = seed["resource_metric_catalog"]["ordered_metric_records"]
    if len(cases) != 475 or len(plans) != 475 or len(metrics) != 18:
        fail("INPUT_SCHEMA_INVALID", "case, plan, or metric cardinality differs")
    for position, (case, plan) in enumerate(zip(cases, plans), 1):
        if case["case_position"] != position or plan["case_position"] != position:
            fail("INPUT_SCHEMA_INVALID", "case or plan order differs")
        if case != {
            key: plan[key] for key in ("case_binding", "case_kind", "case_position")
        }:
            fail("INPUT_SCHEMA_INVALID", "case binding does not match plan")
    for position, metric in enumerate(metrics, 1):
        if metric["metric_position"] != position:
            fail("INPUT_SCHEMA_INVALID", "metric order differs")


def expression_members(seed):
    records = seed["recurrence_catalog"]["transfer_rule_catalog"][
        "ordered_primitive_opcode_records"
    ]
    if len(records) != 55:
        fail("INPUT_SCHEMA_INVALID", "primitive opcode cardinality differs")
    result = {}
    for position, row in enumerate(records, 1):
        if row["opcode_position"] != position or row["opcode"] in result:
            fail("INPUT_SCHEMA_INVALID", "primitive opcode order differs")
        result[row["opcode"]] = tuple(row["ordered_required_member_names_after_opcode"])
    return result


def eager_operands(opcode, node):
    table = {
        "EQ_V1": ("left", "right"),
        "LE_V1": ("left", "right"),
        "LT_V1": ("left", "right"),
        "NOT_V1": ("operand",),
        "IS_NULL_V1": ("operand",),
        "IS_BOOLEAN_V1": ("operand",),
        "IS_TEXT_V1": ("operand",),
        "IS_U128_V1": ("operand",),
        "IS_SIGNED_SAFE_INTEGER_V1": ("operand",),
        "IS_LIST_V1": ("operand",),
        "IS_MAPPING_V1": ("operand",),
        "IS_CELL_EMPTY_V1": ("cell",),
        "HAS_EXACT_KEYS_V1": ("mapping",),
        "FIELD_V1": ("mapping",),
        "INDEX_V1": ("sequence", "zero_based_index"),
        "LIST_LENGTH_V1": ("sequence",),
        "FOLD_MIN_U128_V1": ("sequence",),
        "FOLD_MAX_U128_V1": ("sequence",),
        "CHECKED_ADD_LIST_U128_V1": ("sequence",),
        "CHECKED_SUB_U128_V1": ("left", "right"),
        "CHECKED_MUL_U128_V1": ("left", "right"),
        "CAPPED_ADD_LIST_U128_V1": ("ceiling", "sequence"),
        "CAPPED_MUL_U128_V1": ("ceiling", "left", "right"),
        "CAPPED_VALUE_V1": ("capped_value",),
        "CAPPED_EXCEEDED_V1": ("capped_value",),
        "DECIMAL_OCTETS_V1": ("signed_integer",),
        "CANONICAL_STRING_OCTETS_V1": ("text",),
        "CELL_EMPTY_V1": ("state_expression",),
        "CELL_BUILD_CLIPPED_V1": ("lower", "upper", "ceiling", "state_expression"),
        "CELL_BUILD_FROM_CAPPED_V1": (
            "lower_capped",
            "upper_capped",
            "ceiling",
            "state_expression",
        ),
        "CELL_CLIP_V1": ("cell", "ceiling"),
        "CELL_LOWER_V1": ("cell",),
        "CELL_UPPER_V1": ("cell",),
        "CELL_STATE_V1": ("cell",),
        "RESOLVE_LOCAL_CATALOG_V1": ("catalog_id",),
    }
    if opcode in ("AND_V1", "OR_V1"):
        return list(node["ordered_operands"])
    if opcode == "LIST_V1":
        return list(node["ordered_items"])
    if opcode == "CONCAT_V1":
        return list(node["ordered_sequences"])
    return [node[name] for name in table.get(opcode, ())]


def evaluate_ast(root, context, variables, members):
    values = []
    tasks = [("EVAL", root, dict(variables), context)]
    while tasks:
        frame = tasks.pop()
        action = frame[0]
        if action == "EVAL":
            node, scope, active = frame[1], frame[2], frame[3]
            if not isinstance(node, dict) or "opcode" not in node:
                fail("CASE_SEMANTIC_REJECT", "transfer AST node is not an opcode")
            opcode = node["opcode"]
            if opcode not in members or set(node) != {"opcode", *members[opcode]}:
                fail("CASE_SEMANTIC_REJECT", "transfer AST members differ")
            if opcode == "CONST_V1":
                values.append(node["value"])
            elif opcode == "PARAM_V1":
                name = node["parameter_name"]
                if name not in active["parameters"]:
                    fail("CASE_SEMANTIC_REJECT", "transfer parameter is absent")
                values.append(active["parameters"][name])
            elif opcode == "CHILD_V1":
                index = u128(node["zero_based_index"])
                if index >= len(active["children"]):
                    fail("CASE_SEMANTIC_REJECT", "child index is out of range")
                values.append(validate_cell(active["children"][index], U128_MAX))
            elif opcode == "CHILDREN_V1":
                values.append(
                    [validate_cell(item, U128_MAX) for item in active["children"]]
                )
            elif opcode == "CEILING_V1":
                values.append(u128(active["ceiling"]))
            elif opcode == "VAR_V1":
                name = node["variable_name"]
                if name not in scope:
                    fail("CASE_SEMANTIC_REJECT", "unbound transfer variable")
                values.append(scope[name])
            elif opcode == "LET_V1":
                tasks.append(("LET_NEXT", node, dict(scope), active, 0))
            elif opcode == "IF_V1":
                tasks.append(("IF_BRANCH", node, scope, active))
                tasks.append(("EVAL", node["condition"], scope, active))
            elif opcode == "VALIDATE_V1":
                tasks.append(("VALIDATE_RESULT", node, scope, active))
                tasks.append(("EVAL", node["condition"], scope, active))
            elif opcode in (
                "MAP_V1",
                "FILTER_V1",
                "ANY_V1",
                "ALL_V1",
                "ALL_INDEXED_V1",
            ):
                tasks.append(("ITER_START", node, scope, active))
                tasks.append(("EVAL", node["sequence"], scope, active))
            elif opcode == "CALL_RULE_V1":
                tasks.append(("CALL_NEXT", node, scope, active, 0, {}))
            elif opcode == "IN_SET_V1":
                tasks.append(("APPLY", node, scope, active, opcode, 1))
                tasks.append(("EVAL", node["operand"], scope, active))
            elif opcode in ("HAS_EXACT_KEYS_V1", "FIELD_V1"):
                tasks.append(("APPLY", node, scope, active, opcode, 1))
                tasks.append(("EVAL", node["mapping"], scope, active))
            else:
                operands = eager_operands(opcode, node)
                tasks.append(("APPLY", node, scope, active, opcode, len(operands)))
                for operand in reversed(operands):
                    tasks.append(("EVAL", operand, scope, active))
        elif action == "LET_NEXT":
            node, scope, active, index = frame[1], frame[2], frame[3], frame[4]
            bindings = node["ordered_bindings"]
            if index == len(bindings):
                tasks.append(("EVAL", node["result_expression"], scope, active))
            else:
                binding = bindings[index]
                if set(binding) != {"binding_name", "value_expression"}:
                    fail("CASE_SEMANTIC_REJECT", "LET binding members differ")
                name = binding["binding_name"]
                if not isinstance(name, str) or not name:
                    fail("CASE_SEMANTIC_REJECT", "LET binding name differs")
                tasks.append(("LET_STORE", node, scope, active, index, name))
                tasks.append(("EVAL", binding["value_expression"], scope, active))
        elif action == "LET_STORE":
            node, scope, active, index, name = frame[1:]
            if name in scope:
                fail("CASE_SEMANTIC_REJECT", "LET binding is duplicate")
            scope[name] = values.pop()
            tasks.append(("LET_NEXT", node, scope, active, index + 1))
        elif action == "IF_BRANCH":
            node, scope, active = frame[1:]
            condition = values.pop()
            if type(condition) is not bool:
                fail("CASE_SEMANTIC_REJECT", "IF condition is not boolean")
            branch = node["then_expression"] if condition else node["else_expression"]
            tasks.append(("EVAL", branch, scope, active))
        elif action == "VALIDATE_RESULT":
            node, scope, active = frame[1:]
            condition = values.pop()
            if type(condition) is not bool or not condition:
                fail("CASE_SEMANTIC_REJECT", "transfer validation rejected")
            tasks.append(("EVAL", node["result_expression"], scope, active))
        elif action == "ITER_START":
            node, scope, active = frame[1:]
            sequence = values.pop()
            if not isinstance(sequence, (list, tuple)):
                fail("CASE_SEMANTIC_REJECT", "transfer iterator source differs")
            tasks.append(("ITER_NEXT", node, scope, active, list(sequence), 0, []))
        elif action == "ITER_NEXT":
            node, scope, active, sequence, index, results = frame[1:]
            if index == len(sequence):
                opcode = node["opcode"]
                if opcode == "MAP_V1":
                    values.append(results)
                elif opcode == "FILTER_V1":
                    if any(type(item) is not bool for item in results):
                        fail("CASE_SEMANTIC_REJECT", "FILTER predicate differs")
                    values.append(
                        [item for item, keep in zip(sequence, results) if keep]
                    )
                elif opcode == "ANY_V1":
                    if any(type(item) is not bool for item in results):
                        fail("CASE_SEMANTIC_REJECT", "ANY predicate differs")
                    values.append(any(results))
                else:
                    if any(type(item) is not bool for item in results):
                        fail("CASE_SEMANTIC_REJECT", "ALL predicate differs")
                    values.append(all(results))
            else:
                scoped = dict(scope)
                scoped[node["item_variable"]] = sequence[index]
                if node["opcode"] == "ALL_INDEXED_V1":
                    scoped[node["index_variable"]] = index
                    expression = node["predicate"]
                else:
                    expression = node[
                        "map_expression" if node["opcode"] == "MAP_V1" else "predicate"
                    ]
                tasks.append(
                    ("ITER_STORE", node, scope, active, sequence, index, results)
                )
                tasks.append(("EVAL", expression, scoped, active))
        elif action == "ITER_STORE":
            node, scope, active, sequence, index, results = frame[1:]
            results.append(values.pop())
            tasks.append(
                ("ITER_NEXT", node, scope, active, sequence, index + 1, results)
            )
        elif action == "CALL_NEXT":
            node, scope, active, index, arguments = frame[1:]
            bindings = node["ordered_argument_bindings"]
            if index == len(bindings):
                rule_id = node["transfer_rule_id"]
                if rule_id not in active["rules"]:
                    fail("CASE_SEMANTIC_REJECT", "called transfer rule is absent")
                rule = active["rules"][rule_id]
                if set(arguments) != set(rule["ordered_parameter_names"]):
                    fail("CASE_SEMANTIC_REJECT", "called transfer parameters differ")
                ordered = {
                    name: arguments[name] for name in rule["ordered_parameter_names"]
                }
                nested = dict(active)
                nested["parameters"] = ordered
                tasks.append(("EVAL", rule["program"], {}, nested))
            else:
                binding = bindings[index]
                if set(binding) != {"parameter_name", "value_expression"}:
                    fail("CASE_SEMANTIC_REJECT", "CALL binding members differ")
                name = binding["parameter_name"]
                if name in arguments:
                    fail("CASE_SEMANTIC_REJECT", "CALL binding is duplicate")
                tasks.append(
                    ("CALL_STORE", node, scope, active, index, arguments, name)
                )
                tasks.append(("EVAL", binding["value_expression"], scope, active))
        elif action == "CALL_STORE":
            node, scope, active, index, arguments, name = frame[1:]
            arguments[name] = values.pop()
            tasks.append(("CALL_NEXT", node, scope, active, index + 1, arguments))
        elif action == "APPLY":
            node, scope, active, opcode, count = frame[1:]
            operands = values[-count:] if count else []
            if count:
                del values[-count:]
            values.append(apply_primitive(opcode, node, operands, active))
        else:
            fail("INTERNAL_FAIL_CLOSED", "unknown work-stack action")
    if len(values) != 1:
        fail("INTERNAL_FAIL_CLOSED", "transfer work stack did not close")
    return values[0]


def apply_primitive(opcode, node, values, context):
    if opcode == "EQ_V1":
        return values[0] == values[1]
    if opcode == "LE_V1":
        return values[0] <= values[1]
    if opcode == "LT_V1":
        return values[0] < values[1]
    if opcode in ("AND_V1", "OR_V1"):
        if any(type(value) is not bool for value in values):
            fail("CASE_SEMANTIC_REJECT", "boolean operand differs")
        return all(values) if opcode == "AND_V1" else any(values)
    if opcode == "NOT_V1":
        if type(values[0]) is not bool:
            fail("CASE_SEMANTIC_REJECT", "NOT operand differs")
        return not values[0]
    if opcode == "IN_SET_V1":
        if not isinstance(node["ordered_values"], list):
            fail("CASE_SEMANTIC_REJECT", "IN_SET literal array differs")
        return values[0] in node["ordered_values"]
    if opcode == "IS_NULL_V1":
        return values[0] is None
    if opcode == "IS_BOOLEAN_V1":
        return type(values[0]) is bool
    if opcode == "IS_TEXT_V1":
        return isinstance(values[0], str)
    if opcode == "IS_U128_V1":
        return plain_integer(values[0]) and 0 <= values[0] <= U128_MAX
    if opcode == "IS_SIGNED_SAFE_INTEGER_V1":
        return (
            plain_integer(values[0])
            and -SAFE_INTEGER_MAX <= values[0] <= SAFE_INTEGER_MAX
        )
    if opcode == "IS_LIST_V1":
        return isinstance(values[0], list)
    if opcode == "IS_MAPPING_V1":
        return isinstance(values[0], dict)
    if opcode == "IS_CELL_EMPTY_V1":
        return validate_cell(values[0], U128_MAX).status == "PROVABLY_EMPTY"
    if opcode == "HAS_EXACT_KEYS_V1":
        return isinstance(values[0], dict) and list(values[0]) == node["ordered_keys"]
    if opcode == "FIELD_V1":
        if not isinstance(values[0], dict) or node["field_name"] not in values[0]:
            fail("CASE_SEMANTIC_REJECT", "mapping field is absent")
        return values[0][node["field_name"]]
    if opcode == "INDEX_V1":
        index = u128(values[1])
        if not isinstance(values[0], (list, tuple)) or index >= len(values[0]):
            fail("CASE_SEMANTIC_REJECT", "sequence index is out of range")
        return values[0][index]
    if opcode == "LIST_V1":
        return list(values)
    if opcode == "CONCAT_V1":
        result = []
        for sequence in values:
            if not isinstance(sequence, list):
                fail("CASE_SEMANTIC_REJECT", "CONCAT operand differs")
            result.extend(sequence)
        return result
    if opcode == "LIST_LENGTH_V1":
        if not isinstance(values[0], (list, tuple)):
            fail("CASE_SEMANTIC_REJECT", "LIST_LENGTH operand differs")
        return u128(len(values[0]))
    if opcode in ("FOLD_MIN_U128_V1", "FOLD_MAX_U128_V1"):
        sequence = values[0]
        if not isinstance(sequence, list) or not sequence:
            fail("CASE_SEMANTIC_REJECT", "U128 extrema source differs")
        checked = [u128(item) for item in sequence]
        return min(checked) if opcode == "FOLD_MIN_U128_V1" else max(checked)
    if opcode == "CHECKED_ADD_LIST_U128_V1":
        if not isinstance(values[0], list):
            fail("CASE_SEMANTIC_REJECT", "checked-add source differs")
        return add_checked(values[0])
    if opcode == "CHECKED_SUB_U128_V1":
        return subtract_checked(values[0], values[1])
    if opcode == "CHECKED_MUL_U128_V1":
        return multiply_checked(values[0], values[1])
    if opcode == "CAPPED_ADD_LIST_U128_V1":
        if not isinstance(values[1], list):
            fail("CASE_SEMANTIC_REJECT", "capped-add source differs")
        return capped_add(values[0], values[1])
    if opcode == "CAPPED_MUL_U128_V1":
        return capped_multiply(values[0], values[1], values[2])
    if opcode == "CAPPED_VALUE_V1":
        if not isinstance(values[0], Capped):
            fail("CASE_SEMANTIC_REJECT", "capped projection differs")
        return values[0].value
    if opcode == "CAPPED_EXCEEDED_V1":
        if not isinstance(values[0], Capped):
            fail("CASE_SEMANTIC_REJECT", "capped projection differs")
        return values[0].exceeded
    if opcode == "DECIMAL_OCTETS_V1":
        return len(str(safe_integer(values[0])).encode("ascii"))
    if opcode == "CANONICAL_STRING_OCTETS_V1":
        if not isinstance(values[0], str):
            fail("CASE_SEMANTIC_REJECT", "canonical string operand differs")
        return len(canonical(values[0]))
    if opcode == "CELL_EMPTY_V1":
        if not isinstance(values[0], list):
            fail("CASE_SEMANTIC_REJECT", "empty cell state differs")
        return empty_cell(values[0])
    if opcode == "CELL_BUILD_CLIPPED_V1":
        if not isinstance(values[3], list):
            fail("CASE_SEMANTIC_REJECT", "cell state differs")
        return bounded_cell(values[0], values[1], values[2], values[3])
    if opcode == "CELL_BUILD_FROM_CAPPED_V1":
        lower, upper, ceiling, state = values
        if (
            not isinstance(lower, Capped)
            or not isinstance(upper, Capped)
            or not isinstance(state, list)
        ):
            fail("CASE_SEMANTIC_REJECT", "bounded cell operands differ")
        return (
            empty_cell(state)
            if lower.exceeded
            else bounded_cell(lower.value, upper.value, ceiling, state)
        )
    if opcode == "CELL_CLIP_V1":
        return clip_cell(values[0], values[1])
    if opcode == "CELL_LOWER_V1":
        return validate_cell(values[0], U128_MAX).lower
    if opcode == "CELL_UPPER_V1":
        return validate_cell(values[0], U128_MAX).upper
    if opcode == "CELL_STATE_V1":
        return list(validate_cell(values[0], U128_MAX).state)
    if opcode == "RESOLVE_LOCAL_CATALOG_V1":
        catalog_id = values[0]
        if catalog_id not in context["local_catalogs"]:
            fail("CASE_SEMANTIC_REJECT", "local catalog identity did not resolve")
        return context["local_catalogs"][catalog_id]
    fail("CASE_SEMANTIC_REJECT", "unimplemented primitive opcode")


def compile_catalog(seed):
    recurrence = seed["recurrence_catalog"]
    members = expression_members(seed)
    rule_rows = recurrence["transfer_rule_catalog"]["ordered_transfer_rule_records"]
    rules = {}
    for position, row in enumerate(rule_rows, 1):
        if row["rule_position"] != position or row["transfer_rule_id"] in rules:
            fail("INPUT_SCHEMA_INVALID", "transfer rule order differs")
        if set(row["ordered_parameter_names"]) != {
            item["parameter_name"] for item in row["ordered_parameter_type_records"]
        }:
            fail("INPUT_SCHEMA_INVALID", "transfer parameter schema differs")
        rules[row["transfer_rule_id"]] = row
    transfer_rows = recurrence["instruction_set"]["transfer_program_schema"][
        "ordered_transfer_opcode_records"
    ]
    instructions = {}
    for position, row in enumerate(transfer_rows, 1):
        if row["opcode_position"] != position or row["opcode"] in instructions:
            fail("INPUT_SCHEMA_INVALID", "cell instruction order differs")
        if row["transfer_rule_id"] not in rules:
            fail("INPUT_SCHEMA_INVALID", "cell instruction rule is absent")
        instructions[row["opcode"]] = row
    kernels = {}
    for position, row in enumerate(recurrence["ordered_derivation_kernel_records"], 1):
        if row["kernel_position"] != position or row["derivation_kind"] in kernels:
            fail("INPUT_SCHEMA_INVALID", "derivation kernel order differs")
        kernels[row["derivation_kind"]] = row
    local = recurrence["local_shutdown_analytic_catalog"]
    local_catalogs = {local["local_shutdown_analytic_catalog_id"]: local}
    return {
        "members": members,
        "rules": rules,
        "instructions": instructions,
        "kernels": kernels,
        "local_catalogs": local_catalogs,
    }


def evaluate_u128_expression(node, step):
    if not isinstance(node, dict) or "opcode" not in node:
        fail("CASE_SEMANTIC_REJECT", "meter expression differs")
    opcode = node["opcode"]
    if opcode == "CONST_U128":
        return u128(node["value"])
    if opcode == "STEP_LOGICAL_TRANSFER_MULTIPLICITY":
        return u128(step["logical_transfer_multiplicity"])
    if opcode == "PARAM_U128":
        return u128(step["recurrence_parameters"][node["parameter_name"]])
    if opcode == "PARAM_LIST_COUNT":
        value = step["recurrence_parameters"][node["parameter_name"]]
        if not isinstance(value, list):
            fail("CASE_SEMANTIC_REJECT", "meter list parameter differs")
        return u128(len(value))
    if opcode == "INDICATOR_PARAM_NONZERO":
        return int(u128(step["recurrence_parameters"][node["parameter_name"]]) != 0)
    if opcode == "INDICATOR_PARAM_IS_NULL":
        return int(step["recurrence_parameters"][node["parameter_name"]] is None)
    if opcode == "CHECKED_ADD":
        return add_checked(
            [evaluate_u128_expression(item, step) for item in node["ordered_operands"]]
        )
    if opcode == "CHECKED_MUL":
        result = 1
        for item in node["ordered_operands"]:
            result = multiply_checked(result, evaluate_u128_expression(item, step))
        return result
    fail("CASE_SEMANTIC_REJECT", "unknown meter opcode")


def binary_lift_depth(maximum_items):
    maximum_items = u128(maximum_items)
    if maximum_items <= 1:
        return 0
    return (maximum_items - 1).bit_length()


def step_iteration_depth(step):
    kind = step["derivation_kind"]
    parameters = step["recurrence_parameters"]
    if kind == "ASSOCIATIVE_HOMOGENEOUS_RUN_BATCH":
        return binary_lift_depth(parameters["maximum_items"])
    if kind == "ARRAY_STREAM_FOLD":
        return u128(parameters["maximum_items"])
    if kind == "APPLICATION_SCHEDULE_COUNT":
        value = parameters["ordered_application_invocation_records"]
        if not isinstance(value, list):
            fail("CASE_SEMANTIC_REJECT", "application schedule differs")
        return u128(len(value))
    return u128(step["physical_transition_count"])


def compile_templates(seed, catalog):
    recipe = seed["logical_plan_recipe_catalog"]
    compiled = {}
    for template in recipe["ordered_logical_plan_templates"]:
        template_id = template["logical_plan_template_id"]
        if template_id in compiled:
            fail("INPUT_SCHEMA_INVALID", "logical template identity is duplicate")
        cells = {}
        depths = {}
        step_rows = template["ordered_template_steps"]
        for position, step in enumerate(step_rows, 1):
            if step["template_step_position"] != position:
                fail("INPUT_SCHEMA_INVALID", "template is not strict postorder")
            children = step["ordered_child_step_positions"]
            if any(
                not plain_integer(item) or not 1 <= item < position for item in children
            ):
                fail("INPUT_SCHEMA_INVALID", "template child is not earlier")
            if step["derivation_kind"] not in catalog["kernels"]:
                fail("INPUT_SCHEMA_INVALID", "step kernel is absent")
            kernel = catalog["kernels"][step["derivation_kind"]]
            if kernel["kernel_record_sha256"] != step["kernel_record_sha256"]:
                fail("INPUT_IDENTITY_INVALID", "step kernel identity differs")
            program_opcode = kernel["transfer_program"]["opcode"]
            instruction = catalog["instructions"].get(program_opcode)
            if instruction is None:
                fail("INPUT_SCHEMA_INVALID", "cell transfer opcode is absent")
            rule = catalog["rules"][instruction["transfer_rule_id"]]
            parameter_names = rule["ordered_parameter_names"]
            parameters = step["recurrence_parameters"]
            if set(parameters) != set(parameter_names):
                fail("INPUT_SCHEMA_INVALID", "step recurrence parameters differ")
            ordered_parameters = {name: parameters[name] for name in parameter_names}
            context = {
                "parameters": ordered_parameters,
                "children": [cells[item] for item in children],
                "ceiling": PUBLISHED_MAXIMUM,
                "rules": catalog["rules"],
                "local_catalogs": catalog["local_catalogs"],
            }
            result = evaluate_ast(rule["program"], context, {}, catalog["members"])
            cells[position] = validate_cell(result)
            depths[position] = 1 + max((depths[item] for item in children), default=0)
            meter = kernel["meter_program"]
            physical = evaluate_u128_expression(
                meter["transition_attempt_count_expression"], step
            )
            logical = evaluate_u128_expression(
                meter["logical_unbatched_transition_equivalent_count_expression"], step
            )
            batches = evaluate_u128_expression(
                meter["batch_application_count_expression"], step
            )
            if (
                physical != step["physical_transition_count"]
                or logical != step["logical_unbatched_transition_equivalent_count"]
                or batches != step["physical_batch_application_count"]
            ):
                fail("CASE_SEMANTIC_REJECT", "kernel meter does not reconcile")
        root_position = template["root_step_position"]
        if (
            root_position not in cells
            or recipe["logical_plan_instantiation_rule"] is None
        ):
            fail("INPUT_SCHEMA_INVALID", "template root is absent")
        last_parent = {position: position for position in cells}
        for parent in step_rows:
            parent_position = parent["template_step_position"]
            for child_position in parent["ordered_child_step_positions"]:
                last_parent[child_position] = max(
                    last_parent[child_position], parent_position
                )
        compiled[template_id] = {
            "template": template,
            "cells": cells,
            "depth": max(depths.values()),
            "iteration_depth": max(step_iteration_depth(step) for step in step_rows),
            "last_parent": last_parent,
        }
    return compiled


def derive_local_baseline_maximum(local):
    records = local["ordered_mutable_limit_records"]
    baseline = {row["member_name"]: row["baseline_value"] for row in records}
    batch = u128(baseline["maximum_terminal_ingress_batches"])
    program = local["batch_unsaturated_program"]
    if program["opcode"] != "PIECEWISE_AFFINE_DECIMAL_WIDTH_V1":
        fail("INPUT_SCHEMA_INVALID", "local baseline formula differs")
    derived = add_checked(
        [
            program["constant_octets"],
            multiply_checked(program["linear_coefficient"], batch),
            multiply_checked(program["decimal_width_coefficient"], len(str(batch))),
        ]
    )
    if derived != local["baseline_attainable_maximum_octets"]:
        fail("CASE_SEMANTIC_REJECT", "local baseline maximum does not reconcile")
    return derived


def conditioned_root_cell(plan, compiled, profiles, local):
    root = compiled["template"]["root_step_position"]
    base = compiled["cells"][root]
    program_id = plan["profile_conditioning_program_id"]
    if program_id is None:
        return base
    if program_id not in profiles:
        fail("INPUT_SCHEMA_INVALID", "profile program identity is absent")
    profile = profiles[program_id]
    if profile["case_position"] != plan["case_position"]:
        fail("INPUT_SCHEMA_INVALID", "profile program case differs")
    transfer = profile["conditioning_transfer_program"]
    p2 = transfer["p2_upper_bound_program"]
    if transfer["cell_contract_id"] != (
        "22b08631a90cfcda5461171f4287c359f78de037cd3aa7cfe76c81331338cbb2"
    ):
        fail("INPUT_IDENTITY_INVALID", "profile cell contract differs")
    if profile["conditioning_strategy"] == (
        "STRUCTURAL_TEMPLATE_SUPERSET_WITH_EXACT_RETAINED_ATTAINMENT_V1"
    ):
        instructions = p2["ordered_instruction_records"]
        if len(instructions) != 1 or instructions[0]["opcode"] != (
            "LOAD_STRUCTURAL_TEMPLATE_SUPERSET_CELL_V1"
        ):
            fail("CASE_SEMANTIC_REJECT", "generic profile P2 differs")
        return base
    if profile["conditioning_strategy"] != "LOCAL_SHUTDOWN_BASELINE_ANALYTIC_EXACT_V1":
        fail("CASE_SEMANTIC_REJECT", "unknown profile conditioning strategy")
    opcodes = [row["opcode"] for row in p2["ordered_instruction_records"]]
    if opcodes != [
        "LOAD_STRUCTURAL_TEMPLATE_SUPERSET_CELL_V1",
        "LOAD_FIXED_AUTHORITY_SET_V1",
        "EXECUTE_LOCAL_SHUTDOWN_BASELINE_ANALYTIC_EXACT_V1",
        "INTERSECT_EXACT_ANALYTIC_WITH_STRUCTURAL_CELL_V1",
    ]:
        fail("CASE_SEMANTIC_REJECT", "exact profile P2 differs")
    exact = derive_local_baseline_maximum(local)
    if base.status == "PROVABLY_EMPTY" or exact > base.upper:
        fail("CASE_SEMANTIC_REJECT", "exact profile exceeds structural cell")
    return Cell("MAY_BE_NONEMPTY", exact, exact, base.state)


def owner_profile_position(plan, profiles):
    program_id = plan["profile_conditioning_program_id"]
    return None if program_id is None else profiles[program_id]["profile_position"]


def event_authority(seed):
    logical = seed["logical_event_catalog"]
    definitions = {}
    for position, row in enumerate(logical["ordered_event_kind_records"], 1):
        if row["event_kind_position"] != position or row["event_kind"] in definitions:
            fail("INPUT_SCHEMA_INVALID", "event kind order differs")
        definitions[row["event_kind"]] = row
    subjects = {}
    grammar = logical["case_level_event_grammar"]
    for position, row in enumerate(grammar["ordered_subject_schema_records"], 1):
        if row["subject_schema_position"] != position:
            fail("INPUT_SCHEMA_INVALID", "subject schema order differs")
        event_kind = row["event_kind"]
        if event_kind in subjects or event_kind not in definitions:
            fail("INPUT_SCHEMA_INVALID", "subject event binding differs")
        if (
            row["subject_schema_version"]
            != definitions[event_kind]["subject_schema_version"]
        ):
            fail("INPUT_SCHEMA_INVALID", "subject schema version differs")
        subjects[event_kind] = row
    return definitions, subjects


def ledger_event(
    ledger,
    event_kind,
    phase,
    step_position,
    role,
    subject,
    aggregation=1,
    logical_count=0,
    observed=None,
    subject_ordinal=None,
):
    raw = subject if isinstance(subject, bytes) else canonical(subject)
    ledger.append(
        {
            "event_kind": event_kind,
            "execution_phase": phase,
            "logical_derivation_step_position": step_position,
            "subject_role": role,
            "subject_raw": raw,
            "aggregation_multiplicity": u128(aggregation),
            "logical_unbatched_equivalent_count": u128(logical_count),
            "observed_value": None if observed is None else u128(observed),
            "subject_ordinal": subject_ordinal,
        }
    )


def live_entries(active_positions, unit_data, commitment_hashes):
    entries = []
    ordered_positions = sorted(
        active_positions, key=lambda item: unit_data[item]["cache_raw"]
    )
    for position in ordered_positions:
        unit = unit_data[position]
        entries.append(
            {
                "canonical_octets": len(unit["cache_raw"]),
                "entry_id": unit["cache_sha"],
                "entry_kind": "RECURRENCE_CACHE_KEY_V2",
            }
        )
        entries.append(
            {
                "canonical_octets": len(unit["cell_raw"]),
                "entry_id": unit["cell_sha"],
                "entry_kind": "RECURRENCE_RESULT_CELL_V2",
            }
        )
    for digest in commitment_hashes:
        entries.append(
            {
                "canonical_octets": 32,
                "entry_id": digest,
                "entry_kind": "STEP_COMMITMENT_DIGEST_V1",
            }
        )
    return entries


def append_retention(
    ledger,
    position,
    label,
    entries,
    phase="UPPER_BOUND_DERIVATION",
    step_position=None,
):
    observed = add_checked([row["canonical_octets"] for row in entries])
    subject = {
        "snapshot_version": "riskyieldmm.raw_v8_step2_external_schema_v2.live_set_snapshot.v1",
        "snapshot_position": position,
        "observation_label": label,
        "ordered_live_entry_records": entries,
        "observed_value": observed,
    }
    ledger_event(
        ledger,
        "RETENTION_OBSERVATION",
        phase,
        step_position,
        label,
        subject,
        observed=observed,
        subject_ordinal="EVENT_KIND",
    )


def ordinary_result_cell(seed, plan, step, cell):
    schema = seed["recurrence_catalog"]["result_cell_schema"]
    return {
        "result_cell_version": schema["result_cell_version"],
        "subject_variant": "ORDINARY_STEP",
        "logical_count_plan_id": plan["logical_count_plan_id"],
        "state_signature_id": step["state_signature_id"],
        "ordered_state_components": list(cell.state),
        "cell_status": cell.status,
        "certified_lower_bound_octets": cell.lower,
        "certified_upper_bound_octets": cell.upper,
        "logical_derivation_step_position": step["template_step_position"],
        "result_cell_ordinal": 1,
        "local_controller_state_position": None,
        "local_controller_state_id": None,
    }


def ordinary_cache_key(seed, plan, step, cell, profile_position):
    schema = seed["recurrence_catalog"]["cache_key_schema"]
    return {
        "cache_key_version": schema["cache_key_version"],
        "subject_variant": "ORDINARY_STEP",
        "logical_count_plan_id": plan["logical_count_plan_id"],
        "effective_canonical_octet_ceiling": PUBLISHED_MAXIMUM,
        "state_signature_id": step["state_signature_id"],
        "ordered_state_components": list(cell.state),
        "logical_derivation_step_position": step["template_step_position"],
        "derivation_kind": step["derivation_kind"],
        "occurrence_ordinal": 1,
        "array_ordinal": None,
        "owner_profile_position": profile_position,
        "application_invocation_ordinal": None,
        "observation_ordinal": None,
        "local_controller_state_position": None,
        "local_controller_state_id": None,
    }


def ordinary_transition_token(seed, plan, step, cell, ordinal, logical_count):
    schema = seed["recurrence_catalog"]["transition_token_schema"]
    input_symbol = {
        "derivation_kind": step["derivation_kind"],
        "physical_transition_ordinal": ordinal,
    }
    return {
        "transition_token_version": schema["transition_token_version"],
        "subject_variant": "ORDINARY_STEP",
        "logical_count_plan_id": plan["logical_count_plan_id"],
        "transition_ordinal": ordinal,
        "transition_kind": "ORDINARY_KERNEL_TRANSITION",
        "source_state_components": list(cell.state),
        "input_symbol": input_symbol,
        "candidate_state_components": list(cell.state),
        "candidate_certified_upper_bound_octets": cell.upper,
        "logical_derivation_step_position": step["template_step_position"],
        "local_controller_transition_position": None,
        "local_controller_transition_id": None,
        "source_controller_state_id": None,
        "target_controller_state_id": None,
    }


def ordinary_commitment(seed, plan, step, cell_sha, cell):
    schema = seed["recurrence_catalog"]["step_commitment_schema"]
    return {
        "step_commitment_version": schema["step_commitment_version"],
        "subject_variant": "ORDINARY_STEP",
        "logical_count_plan_id": plan["logical_count_plan_id"],
        "state_count": 1,
        "certified_upper_bound_octets": cell.upper,
        "ordered_result_cell_sha256": [cell_sha],
        "logical_derivation_step_position": step["template_step_position"],
        "local_shutdown_analytic_catalog_id": None,
        "initial_controller_state_id": None,
        "terminal_controller_state_id": None,
    }


def descriptor_subject(plan, variant, position, step_id, derivation_kind):
    return {
        "logical_step_reference_version": (
            "riskyieldmm.raw_v8_step2_external_schema_v2.logical_step_reference.v1"
        ),
        "logical_count_plan_id": plan["logical_count_plan_id"],
        "subject_variant": variant,
        "logical_derivation_step_position": position,
        "logical_derivation_step_id": step_id,
        "derivation_kind": derivation_kind,
    }


def intrinsic_subject(plan, rule_ids):
    return {
        "evaluation_version": (
            "riskyieldmm.raw_v8_step2_external_schema_v2.intrinsic_rule_evaluation_record.v1"
        ),
        "logical_count_plan_id": plan["logical_count_plan_id"],
        "ordered_intrinsic_rule_ids": list(rule_ids),
        "aggregation_multiplicity": len(rule_ids),
    }


def ordinary_case_ledger(seed, plan, compiled, profiles):
    ledger = []
    steps = compiled["template"]["ordered_template_steps"]
    cells = dict(compiled["cells"])
    root_position = compiled["template"]["root_step_position"]
    cells[root_position] = conditioned_root_cell(
        plan,
        compiled,
        profiles,
        seed["recurrence_catalog"]["local_shutdown_analytic_catalog"],
    )
    profile_position = owner_profile_position(plan, profiles)
    unit_data = {}
    for step in steps:
        position = step["template_step_position"]
        cell = cells[position]
        cell_raw = canonical(ordinary_result_cell(seed, plan, step, cell))
        cache_raw = canonical(
            ordinary_cache_key(seed, plan, step, cell, profile_position)
        )
        unit_data[position] = {
            "cell": cell,
            "cell_raw": cell_raw,
            "cell_sha": sha(cell_raw),
            "cache_raw": cache_raw,
            "cache_sha": sha(cache_raw),
        }
    active = set()
    commitment_hashes = []
    commitment_records = []
    retention_position = 0
    for step in steps:
        position = step["template_step_position"]
        unit = unit_data[position]
        cell = unit["cell"]
        ledger_event(
            ledger,
            "LOGICAL_DESCRIPTOR_VISIT",
            "UPPER_BOUND_DERIVATION",
            position,
            "LOGICAL_STEP_REFERENCE",
            descriptor_subject(
                plan,
                "ORDINARY_STEP",
                position,
                step["logical_derivation_step_id"],
                step["derivation_kind"],
            ),
            aggregation=step["logical_descriptor_occurrence_count"],
        )
        physical = u128(step["physical_transition_count"])
        logical = u128(step["logical_unbatched_transition_equivalent_count"])
        if physical == 0:
            if logical != 0:
                fail("CASE_SEMANTIC_REJECT", "zero transition run has logical work")
        else:
            quotient, remainder = divmod(logical, physical)
            if quotient == 0:
                fail("CASE_SEMANTIC_REJECT", "transition logical distribution is zero")
            distributed = 0
            for ordinal in range(1, physical + 1):
                logical_count = quotient + int(ordinal <= remainder)
                distributed = add_checked([distributed, logical_count])
                ledger_event(
                    ledger,
                    "TRANSITION_ATTEMPT",
                    "UPPER_BOUND_DERIVATION",
                    position,
                    "ORDINARY_TRANSITION",
                    ordinary_transition_token(
                        seed, plan, step, cell, ordinal, logical_count
                    ),
                    logical_count=logical_count,
                    subject_ordinal=ordinal,
                )
            if distributed != logical:
                fail("CASE_SEMANTIC_REJECT", "transition distribution does not close")
        batches = u128(step["physical_batch_application_count"])
        for ordinal in range(1, batches + 1):
            subject = {
                "batch_application_version": (
                    "riskyieldmm.raw_v8_step2_external_schema_v2.batch_application_record.v1"
                ),
                "logical_count_plan_id": plan["logical_count_plan_id"],
                "logical_derivation_step_position": position,
                "physical_batch_ordinal": ordinal,
                "derivation_kind": step["derivation_kind"],
                "logical_transfer_multiplicity": step["logical_transfer_multiplicity"],
            }
            ledger_event(
                ledger,
                "BATCH_APPLICATION",
                "UPPER_BOUND_DERIVATION",
                position,
                "HOMOGENEOUS_RUN_BATCH",
                subject,
                subject_ordinal=ordinal,
            )
        ledger_event(
            ledger,
            "RESULT_CELL_EMIT",
            "UPPER_BOUND_DERIVATION",
            position,
            "ORDINARY_RESULT_CELL",
            unit["cell_raw"],
            subject_ordinal=1,
        )
        ledger_event(
            ledger,
            "CACHE_INSERT",
            "UPPER_BOUND_DERIVATION",
            position,
            "ORDINARY_CACHE_KEY",
            unit["cache_raw"],
            subject_ordinal=1,
        )
        active.add(position)
        retention_position += 1
        append_retention(
            ledger,
            retention_position,
            "LIVE_CHILDREN_PLUS_PROSPECTIVE_PARENT",
            live_entries(active, unit_data, commitment_hashes),
            step_position=position,
        )
        ledger_event(
            ledger,
            "HASH_PREIMAGE",
            "UPPER_BOUND_DERIVATION",
            position,
            "RETAINED_RESULT_CELL_PREIMAGE",
            unit["cell_raw"],
            subject_ordinal="EVENT_KIND",
        )
        commitment_raw = canonical(
            ordinary_commitment(seed, plan, step, unit["cell_sha"], cell)
        )
        commitment_sha = sha(commitment_raw)
        ledger_event(
            ledger,
            "STEP_COMMITMENT_EMIT",
            "UPPER_BOUND_DERIVATION",
            position,
            "ORDINARY_STEP_COMMITMENT",
            commitment_raw,
            subject_ordinal=position,
        )
        ledger_event(
            ledger,
            "HASH_PREIMAGE",
            "UPPER_BOUND_DERIVATION",
            position,
            "STEP_COMMITMENT_PREIMAGE",
            commitment_raw,
            subject_ordinal="EVENT_KIND",
        )
        commitment_hashes.append(commitment_sha)
        commitment_records.append(
            {
                "derivation_unit_ordinal": position,
                "subject_variant": "ORDINARY_STEP",
                "logical_derivation_step_position": position,
                "local_controller_unit_ordinal": None,
                "step_commitment_sha256": commitment_sha,
            }
        )
        active = {item for item in active if compiled["last_parent"][item] > position}
        retention_position += 1
        append_retention(
            ledger,
            retention_position,
            "AFTER_PARENT_COMMITMENT_HASH_AND_RELEASE",
            live_entries(active, unit_data, commitment_hashes),
            step_position=position,
        )
    intrinsic_ids = []
    for step in steps:
        intrinsic_ids.extend(step["ordered_intrinsic_rule_ids"])
    return {
        "ledger": ledger,
        "unit_data": unit_data,
        "commitment_hashes": commitment_hashes,
        "commitment_records": commitment_records,
        "intrinsic_ids": intrinsic_ids,
        "depth": compiled["depth"],
        "iteration_depth": max(
            compiled["iteration_depth"],
            u128(plan["scope_summary"]["application_invocation_count"]),
        ),
        "retention_position": retention_position,
        "root_positions": [root_position],
    }


def local_cell_upper(local, state):
    kind = state["state_kind"]
    components = state["ordered_state_components"]
    if kind == "INITIAL":
        return u128(local["baseline_attainable_maximum_octets"])
    if kind == "TERMINAL":
        return u128(components[7])
    if kind == "INTERMEDIATE":
        return u128(components[3])
    fail("CASE_SEMANTIC_REJECT", "local controller state kind differs")


def local_result_cell(seed, plan, local, state):
    schema = seed["recurrence_catalog"]["result_cell_schema"]
    return {
        "result_cell_version": schema["result_cell_version"],
        "subject_variant": "LOCAL_CONTROLLER",
        "logical_count_plan_id": plan["logical_count_plan_id"],
        "state_signature_id": local["state_signature_id"],
        "ordered_state_components": state["ordered_state_components"],
        "cell_status": "MAY_BE_NONEMPTY",
        "certified_lower_bound_octets": 0,
        "certified_upper_bound_octets": local_cell_upper(local, state),
        "logical_derivation_step_position": None,
        "result_cell_ordinal": None,
        "local_controller_state_position": state["controller_state_position"],
        "local_controller_state_id": state["controller_state_id"],
    }


def local_cache_key(seed, plan, local, state):
    schema = seed["recurrence_catalog"]["cache_key_schema"]
    return {
        "cache_key_version": schema["cache_key_version"],
        "subject_variant": "LOCAL_CONTROLLER",
        "logical_count_plan_id": plan["logical_count_plan_id"],
        "effective_canonical_octet_ceiling": PUBLISHED_MAXIMUM,
        "state_signature_id": local["state_signature_id"],
        "ordered_state_components": state["ordered_state_components"],
        "logical_derivation_step_position": None,
        "derivation_kind": None,
        "occurrence_ordinal": None,
        "array_ordinal": None,
        "owner_profile_position": None,
        "application_invocation_ordinal": None,
        "observation_ordinal": None,
        "local_controller_state_position": state["controller_state_position"],
        "local_controller_state_id": state["controller_state_id"],
    }


def local_transition_token(
    seed, plan, transition, source_state, target_state, target_upper
):
    schema = seed["recurrence_catalog"]["transition_token_schema"]
    position = transition["controller_transition_position"]
    return {
        "transition_token_version": schema["transition_token_version"],
        "subject_variant": "LOCAL_CONTROLLER",
        "logical_count_plan_id": plan["logical_count_plan_id"],
        "transition_ordinal": position,
        "transition_kind": "LOCAL_CONTROLLER_TRANSITION",
        "source_state_components": source_state["ordered_state_components"],
        "input_symbol": transition["input_mutable_limit_lexical_position"],
        "candidate_state_components": target_state["ordered_state_components"],
        "candidate_certified_upper_bound_octets": target_upper,
        "logical_derivation_step_position": None,
        "local_controller_transition_position": position,
        "local_controller_transition_id": transition["controller_transition_id"],
        "source_controller_state_id": transition["source_controller_state_id"],
        "target_controller_state_id": transition["target_controller_state_id"],
    }


def local_case_ledger(seed, plan):
    local = seed["recurrence_catalog"]["local_shutdown_analytic_catalog"]
    states = local["ordered_controller_state_records"]
    transitions = local["ordered_controller_transition_records"]
    if len(states) != 12 or len(transitions) != 11:
        fail("INPUT_SCHEMA_INVALID", "local controller cardinality differs")
    ledger = []
    unit_data = {}
    for position, state in enumerate(states, 1):
        if state["controller_state_position"] != position:
            fail("INPUT_SCHEMA_INVALID", "local state order differs")
        cell_raw = canonical(local_result_cell(seed, plan, local, state))
        cache_raw = canonical(local_cache_key(seed, plan, local, state))
        unit_data[position] = {
            "cell_raw": cell_raw,
            "cell_sha": sha(cell_raw),
            "cache_raw": cache_raw,
            "cache_sha": sha(cache_raw),
            "upper": local_cell_upper(local, state),
        }
    ledger_event(
        ledger,
        "LOGICAL_DESCRIPTOR_VISIT",
        "UPPER_BOUND_DERIVATION",
        None,
        "LOCAL_CONTROLLER_REFERENCE",
        descriptor_subject(
            plan,
            "LOCAL_CONTROLLER",
            None,
            plan["local_analytic_catalog_id"],
            "LOCAL_SHUTDOWN_ANALYTIC_CONTROLLER",
        ),
        aggregation=local["fixed_controller_transition_count"],
    )
    for position, transition in enumerate(transitions, 1):
        if transition["controller_transition_position"] != position:
            fail("INPUT_SCHEMA_INVALID", "local transition order differs")
        source = states[position - 1]
        target = states[position]
        if (
            transition["source_controller_state_id"] != source["controller_state_id"]
            or transition["target_controller_state_id"] != target["controller_state_id"]
            or transition["expected_target_state_components"]
            != target["ordered_state_components"]
        ):
            fail("CASE_SEMANTIC_REJECT", "local transition adjacency differs")
        ledger_event(
            ledger,
            "TRANSITION_ATTEMPT",
            "UPPER_BOUND_DERIVATION",
            None,
            "LOCAL_CONTROLLER_TRANSITION",
            local_transition_token(
                seed, plan, transition, source, target, unit_data[position + 1]["upper"]
            ),
            logical_count=1,
            subject_ordinal=position,
        )
    metric_program = local["controller_metric_count_program"]
    intrinsic_row = next(
        row
        for row in metric_program["ordered_exact_non_byte_metric_records"]
        if row["metric_position"] == 12
    )
    intrinsic_ids = intrinsic_row["ordered_authority_values"]
    ledger_event(
        ledger,
        "INTRINSIC_RULE_EVALUATION",
        "UPPER_BOUND_DERIVATION",
        None,
        "LOCAL_CONTROLLER_INTRINSIC_RELATIONS",
        intrinsic_subject(plan, intrinsic_ids),
        aggregation=len(intrinsic_ids),
    )
    for position in range(1, 13):
        ledger_event(
            ledger,
            "RESULT_CELL_EMIT",
            "UPPER_BOUND_DERIVATION",
            None,
            "LOCAL_CONTROLLER_STATE_RESULT_CELL",
            unit_data[position]["cell_raw"],
            subject_ordinal=position,
        )
    for position in range(1, 13):
        ledger_event(
            ledger,
            "CACHE_INSERT",
            "UPPER_BOUND_DERIVATION",
            None,
            "LOCAL_CONTROLLER_STATE_CACHE_KEY",
            unit_data[position]["cache_raw"],
            subject_ordinal=position,
        )
    retention_position = 1
    append_retention(
        ledger,
        retention_position,
        "LIVE_CHILDREN_PLUS_PROSPECTIVE_PARENT",
        live_entries(set(range(1, 13)), unit_data, []),
    )
    hash_positions = sorted(range(1, 13), key=lambda item: unit_data[item]["cache_raw"])
    for position in hash_positions:
        ledger_event(
            ledger,
            "HASH_PREIMAGE",
            "UPPER_BOUND_DERIVATION",
            None,
            "RETAINED_RESULT_CELL_PREIMAGE",
            unit_data[position]["cell_raw"],
            subject_ordinal="EVENT_KIND",
        )
    schema = seed["recurrence_catalog"]["step_commitment_schema"]
    commitment = {
        "step_commitment_version": schema["step_commitment_version"],
        "subject_variant": "LOCAL_CONTROLLER",
        "logical_count_plan_id": plan["logical_count_plan_id"],
        "state_count": len(states),
        "certified_upper_bound_octets": max(row["upper"] for row in unit_data.values()),
        "ordered_result_cell_sha256": [
            unit_data[item]["cell_sha"] for item in range(1, 13)
        ],
        "logical_derivation_step_position": None,
        "local_shutdown_analytic_catalog_id": plan["local_analytic_catalog_id"],
        "initial_controller_state_id": states[0]["controller_state_id"],
        "terminal_controller_state_id": states[-1]["controller_state_id"],
    }
    commitment_raw = canonical(commitment)
    commitment_sha = sha(commitment_raw)
    ledger_event(
        ledger,
        "STEP_COMMITMENT_EMIT",
        "UPPER_BOUND_DERIVATION",
        None,
        "LOCAL_CONTROLLER_COMMITMENT",
        commitment_raw,
        subject_ordinal=1,
    )
    ledger_event(
        ledger,
        "HASH_PREIMAGE",
        "UPPER_BOUND_DERIVATION",
        None,
        "STEP_COMMITMENT_PREIMAGE",
        commitment_raw,
        subject_ordinal="EVENT_KIND",
    )
    retention_position += 1
    append_retention(
        ledger,
        retention_position,
        "AFTER_PARENT_COMMITMENT_HASH_AND_RELEASE",
        live_entries(set(), unit_data, [commitment_sha]),
    )
    return {
        "ledger": ledger,
        "unit_data": unit_data,
        "commitment_hashes": [commitment_sha],
        "commitment_records": [
            {
                "derivation_unit_ordinal": 1,
                "subject_variant": "LOCAL_CONTROLLER",
                "logical_derivation_step_position": None,
                "local_controller_unit_ordinal": 1,
                "step_commitment_sha256": commitment_sha,
            }
        ],
        "intrinsic_ids": intrinsic_ids,
        "depth": 1,
        "iteration_depth": local["fixed_controller_transition_count"],
        "retention_position": retention_position,
        "root_positions": [local["terminal_controller_state_position"]],
    }


def profile_catalog(seed):
    rows = seed["logical_plan_recipe_catalog"][
        "ordered_profile_conditioning_program_records"
    ]
    result = {}
    expected_attainment_opcodes = [
        "IMPORT_P2_BOUND_CELL_V1",
        "LOAD_RETAINED_WITNESS_CONTEXT_V1",
        "LOAD_FIXED_AUTHORITY_SET_V1",
        "MATCH_EXACT_PROFILE_SCOPE_CASE_V1",
        "RECONSTRUCT_EXACT_APPLICATION_SCHEDULE_V1",
        "EXECUTE_PINNED_APPLICATION_RULE_AST_ON_RETAINED_BYTES_V1",
        "MEASURE_RETAINED_WITNESS_CANONICAL_OCTETS_V1",
        "REQUIRE_P1_AND_P3_EQUALITY_V1",
    ]
    for position, row in enumerate(rows, 1):
        program_id = row["profile_conditioning_program_id"]
        if row["program_position"] != position or program_id in result:
            fail("INPUT_SCHEMA_INVALID", "profile program order differs")
        computed, unused = semantic_identity(seed, "PROFILE_CONDITIONING_PROGRAM", row)
        if computed != program_id or not unused:
            fail("INPUT_IDENTITY_INVALID", "profile program identity differs")
        attainment = row["conditioning_transfer_program"]["p1_p3_attainment_program"]
        opcodes = [item["opcode"] for item in attainment["ordered_instruction_records"]]
        if (
            opcodes != expected_attainment_opcodes
            or attainment["root_instruction_position"] != 8
        ):
            fail("INPUT_SCHEMA_INVALID", "profile P1/P3 program differs")
        result[program_id] = row
    if len(result) != 408:
        fail("INPUT_SCHEMA_INVALID", "profile program cardinality differs")
    return result


def metric_source_value(source, event):
    if source == "ONE":
        return 1
    if source == "SUBJECT_CANONICAL_OCTETS":
        return len(event["subject_raw"])
    if source == "AGGREGATION_MULTIPLICITY":
        return event["aggregation_multiplicity"]
    if source == "LOGICAL_UNBATCHED_EQUIVALENT_COUNT":
        return event["logical_unbatched_equivalent_count"]
    if source == "OBSERVED_VALUE":
        if event["observed_value"] is None:
            fail("CASE_SEMANTIC_REJECT", "metric observed value is absent")
        return event["observed_value"]
    fail("INPUT_SCHEMA_INVALID", "unknown metric value source")


def reduce_ledger_prefix(ledger, state, definitions, subjects):
    while state["cursor"] < len(ledger):
        event = ledger[state["cursor"]]
        state["cursor"] += 1
        kind = event["event_kind"]
        if kind not in definitions or kind not in subjects:
            fail("CASE_SEMANTIC_REJECT", "event kind is not bound")
        definition = definitions[kind]
        if (
            event["execution_phase"]
            not in definition["ordered_allowed_execution_phases"]
        ):
            fail("CASE_SEMANTIC_REJECT", "event phase is not allowed")
        state["ordinals"][kind] = state["ordinals"].get(kind, 0) + 1
        ordinal = state["ordinals"][kind]
        subject_ordinal = event["subject_ordinal"]
        if subject_ordinal == "EVENT_KIND":
            subject_ordinal = ordinal
        elif subject_ordinal is not None:
            subject_ordinal = u128(subject_ordinal)
        raw = event["subject_raw"]
        token = {
            "event_position": state["cursor"],
            "execution_phase": event["execution_phase"],
            "logical_derivation_step_position": event[
                "logical_derivation_step_position"
            ],
            "event_kind": kind,
            "event_ordinal": ordinal,
            "subject_schema_version": subjects[kind]["subject_schema_version"],
            "subject_kind": subjects[kind]["subject_kind"],
            "subject_role": event["subject_role"],
            "subject_ordinal": subject_ordinal,
            "subject_canonical_octets": len(raw),
            "subject_sha256": sha(raw),
            "aggregation_multiplicity": event["aggregation_multiplicity"],
            "logical_unbatched_equivalent_count": event[
                "logical_unbatched_equivalent_count"
            ],
            "observed_value": event["observed_value"],
        }
        state["tokens"].append(token)
        for update in definition["ordered_metric_update_program"]:
            position = update["metric_position"] - 1
            value = u128(metric_source_value(update["value_source"], event))
            if update["update_kind"] == "ADD":
                state["metrics"][position] = add_checked(
                    [state["metrics"][position], value]
                )
            elif update["update_kind"] == "MAX":
                state["metrics"][position] = max(state["metrics"][position], value)
            else:
                fail("INPUT_SCHEMA_INVALID", "metric update kind differs")


def new_reduction_state():
    return {
        "cursor": 0,
        "ordinals": {},
        "metrics": [0] * 18,
        "tokens": [],
    }


def case_open_subject(plan):
    return {
        "case_open_version": (
            "riskyieldmm.raw_v8_step2_external_schema_v2.case_open_record.v1"
        ),
        "case_position": plan["case_position"],
        "case_kind": plan["case_kind"],
        "logical_count_plan_id": plan["logical_count_plan_id"],
    }


def append_post_derivation_events(seed, plan, execution):
    ledger = execution["ledger"]
    intrinsic_ids = execution["intrinsic_ids"]
    if intrinsic_ids:
        ledger_event(
            ledger,
            "INTRINSIC_RULE_EVALUATION",
            "LEGAL_ATTAINMENT_VALIDATION",
            None,
            "EXACT_RETAINED_ATTAINER_INTRINSIC_RULES",
            intrinsic_subject(plan, intrinsic_ids),
            aggregation=len(intrinsic_ids),
        )
    application_count = u128(plan["scope_summary"]["application_invocation_count"])
    if application_count:
        subject = {
            "evaluation_version": (
                "riskyieldmm.raw_v8_step2_external_schema_v2.application_evaluation_record.v1"
            ),
            "logical_count_plan_id": plan["logical_count_plan_id"],
            "schedule_authority_id": plan["scope_summary"]["schedule_authority_id"],
            "aggregation_multiplicity": application_count,
        }
        ledger_event(
            ledger,
            "APPLICATION_EVALUATION",
            "SCOPE_APPLICATION_VALIDATION",
            None,
            "EXACT_SCOPE_APPLICATION_INVOCATIONS",
            subject,
            aggregation=application_count,
            subject_ordinal=1,
        )
    cross_count = u128(plan["scope_summary"]["cross_rule_evaluation_count"])
    if cross_count:
        subject = {
            "evaluation_version": (
                "riskyieldmm.raw_v8_step2_external_schema_v2.cross_rule_evaluation_record.v1"
            ),
            "logical_count_plan_id": plan["logical_count_plan_id"],
            "schedule_authority_id": plan["scope_summary"]["schedule_authority_id"],
            "aggregation_multiplicity": cross_count,
        }
        ledger_event(
            ledger,
            "CROSS_RULE_EVALUATION",
            "SCOPE_APPLICATION_VALIDATION",
            None,
            "EXACT_SCOPE_CROSS_RULE_ROOTS",
            subject,
            aggregation=cross_count,
            subject_ordinal=1,
        )
    depth = u128(execution["depth"])
    ledger_event(
        ledger,
        "DERIVATION_DEPTH_OBSERVATION",
        "DEPTH_AND_RETENTION_FINALIZATION",
        None,
        "DERIVATION_DAG_DEPTH",
        {
            "depth_record_version": (
                "riskyieldmm.raw_v8_step2_external_schema_v2.derivation_depth_record.v1"
            ),
            "logical_count_plan_id": plan["logical_count_plan_id"],
            "derived_depth": depth,
        },
        observed=depth,
    )
    iteration = u128(execution["iteration_depth"])
    ledger_event(
        ledger,
        "ITERATION_DEPTH_OBSERVATION",
        "DEPTH_AND_RETENTION_FINALIZATION",
        None,
        "ITERATION_DEPTH",
        {
            "depth_record_version": (
                "riskyieldmm.raw_v8_step2_external_schema_v2.iteration_depth_record.v1"
            ),
            "logical_count_plan_id": plan["logical_count_plan_id"],
            "iteration_depth": iteration,
        },
        observed=iteration,
    )
    execution["retention_position"] += 1
    append_retention(
        ledger,
        execution["retention_position"],
        "ROOT_COMMITMENT_DIGEST_THROUGH_FINAL_RESULT_HASH",
        live_entries(set(), execution["unit_data"], execution["commitment_hashes"]),
        phase="DEPTH_AND_RETENTION_FINALIZATION",
    )
    root_positions = sorted(
        execution["root_positions"],
        key=lambda item: execution["unit_data"][item]["cache_raw"],
    )
    root_records = [
        {
            "result_cell_ordinal": ordinal,
            "result_cell_sha256": execution["unit_data"][position]["cell_sha"],
        }
        for ordinal, position in enumerate(root_positions, 1)
    ]
    final = {
        "logical_case_derivation_result_version": (
            "riskyieldmm.raw_v8_step2_external_schema_v2.logical_case_derivation_result.v1"
        ),
        "logical_count_plan_id": plan["logical_count_plan_id"],
        "result_status": "ACCEPT",
        "ordered_root_result_cell_digest_records": root_records,
        "ordered_step_commitment_digest_records": execution["commitment_records"],
    }
    final_raw = canonical(final)
    ledger_event(
        ledger,
        "FINAL_RESULT_EMIT",
        "FINAL_RESULT_SERIALIZATION",
        None,
        "COMPLETE_LOGICAL_CASE_DERIVATION_RESULT",
        final_raw,
    )
    ledger_event(
        ledger,
        "HASH_PREIMAGE",
        "FINAL_RESULT_SERIALIZATION",
        None,
        "FINAL_RESULT_IDENTITY_PREIMAGE",
        final_raw,
        subject_ordinal="EVENT_KIND",
    )


def build_case(seed, plan, templates, profiles, definitions, subjects):
    plan_sha, plan_raw = semantic_identity(seed, "LOGICAL_COUNT_PLAN", plan)
    if plan_sha != plan["logical_count_plan_id"]:
        fail("INPUT_IDENTITY_INVALID", "logical count plan identity differs")
    base_ledger = []
    ledger_event(
        base_ledger,
        "CASE_OPEN",
        "CASE_OPEN",
        None,
        "CASE_OPEN_RECORD",
        case_open_subject(plan),
    )
    ledger_event(
        base_ledger,
        "HASH_PREIMAGE",
        "PLAN_IDENTITY_BINDING",
        None,
        "BOUND_PLAN_IDENTITY_ENVELOPE",
        plan_raw,
        subject_ordinal="EVENT_KIND",
    )
    template_id = plan["logical_plan_template_id"]
    if template_id is None:
        if plan["local_analytic_catalog_id"] is None:
            fail("INPUT_SCHEMA_INVALID", "plan has no executable root")
        execution = local_case_ledger(seed, plan)
    else:
        if (
            template_id not in templates
            or plan["local_analytic_catalog_id"] is not None
        ):
            fail("INPUT_SCHEMA_INVALID", "ordinary plan template binding differs")
        execution = ordinary_case_ledger(seed, plan, templates[template_id], profiles)
    execution["ledger"] = [*base_ledger, *execution["ledger"]]
    append_post_derivation_events(seed, plan, execution)
    state = new_reduction_state()
    reduce_ledger_prefix(execution["ledger"], state, definitions, subjects)
    stream_version = next(
        row["version_literal"]
        for row in seed["ordered_identity_domain_records"]
        if row["identity_name"] == "LOGICAL_EVENT_STREAM"
    )
    preimage = canonical(
        {
            "logical_event_stream_version": stream_version,
            "logical_count_plan_id": plan["logical_count_plan_id"],
            "ordered_pre_close_logical_event_tokens": state["tokens"],
        }
    )
    preimage_sha = sha(preimage)
    ledger_event(
        execution["ledger"],
        "EVENT_STREAM_CLOSE",
        "EVENT_STREAM_FINALIZATION",
        None,
        "EVENT_STREAM_PREIMAGE_DESCRIPTOR",
        {
            "descriptor_version": (
                "riskyieldmm.raw_v8_step2_external_schema_v2.event_stream_preimage_descriptor.v1"
            ),
            "logical_count_plan_id": plan["logical_count_plan_id"],
            "preimage_canonical_octets": len(preimage),
            "preimage_sha256": preimage_sha,
        },
    )
    ledger_event(
        execution["ledger"],
        "HASH_PREIMAGE",
        "EVENT_STREAM_FINALIZATION",
        None,
        "EVENT_STREAM_PREIMAGE",
        preimage,
        subject_ordinal="EVENT_KIND",
    )
    reduce_ledger_prefix(execution["ledger"], state, definitions, subjects)
    if state["cursor"] != len(execution["ledger"]):
        fail("INTERNAL_FAIL_CLOSED", "flat ledger prefix did not close")
    if state["tokens"][-2]["event_kind"] != "EVENT_STREAM_CLOSE" or (
        state["tokens"][-1]["event_kind"] != "HASH_PREIMAGE"
        or state["tokens"][-1]["subject_role"] != "EVENT_STREAM_PREIMAGE"
    ):
        fail("CASE_SEMANTIC_REJECT", "event stream terminal order differs")
    return state["metrics"], preimage_sha


def build_payload(seed, seed_raw):
    catalog = compile_catalog(seed)
    templates = compile_templates(seed, catalog)
    profiles = profile_catalog(seed)
    definitions, subjects = event_authority(seed)
    plans = seed["logical_plan_recipe_catalog"]["ordered_logical_count_plan_records"]
    metrics = seed["resource_metric_catalog"]["ordered_metric_records"]
    case_records = []
    columns = [[] for unused in range(18)]
    for plan in plans:
        measured, event_stream_sha = build_case(
            seed, plan, templates, profiles, definitions, subjects
        )
        measurements = []
        for metric, value in zip(metrics, measured):
            value = u128(value)
            if value > metric["per_case_f0_ceiling"]:
                fail("RESOURCE_LIMIT_EXCEEDED", "per-case F0 metric ceiling exceeded")
            measurements.append(
                {
                    "metric_position": metric["metric_position"],
                    "metric_name": metric["metric_name"],
                    "measured_value": value,
                }
            )
            columns[metric["metric_position"] - 1].append(value)
        without_id = {
            "case_position": plan["case_position"],
            "case_kind": plan["case_kind"],
            "case_binding": plan["case_binding"],
            "logical_count_plan_id": plan["logical_count_plan_id"],
            "result_status": "ACCEPT",
            "ordered_resource_measurements": measurements,
            "derivation_event_stream_sha256": event_stream_sha,
        }
        record = dict(without_id)
        record["case_result_record_id"] = report_identity(
            "RiskYieldMMStep2PreflightCaseResultV1V4_9F_RawV8", without_id
        )
        case_records.append(record)
    summaries = []
    for metric, values in zip(metrics, columns):
        maximum = max(values)
        full_value = (
            add_checked(values) if metric["full_run_aggregation"] == "SUM" else maximum
        )
        if full_value > metric["full_run_f0_ceiling"]:
            fail("RESOURCE_LIMIT_EXCEEDED", "full-run F0 metric ceiling exceeded")
        summaries.append(
            {
                "metric_position": metric["metric_position"],
                "metric_name": metric["metric_name"],
                "full_run_aggregation": metric["full_run_aggregation"],
                "full_run_value": full_value,
                "maximum_case_value": maximum,
                "ordered_maximum_case_positions": [
                    position
                    for position, value in enumerate(values, 1)
                    if value == maximum
                ],
            }
        )
    case_projection = [
        {key: value for key, value in row.items() if key != "case_result_record_id"}
        for row in case_records
    ]
    count_sha = report_identity(
        "RiskYieldMMStep2PreflightCountVectorV1V4_9F_RawV8",
        [*case_projection, *summaries],
    )
    payload = {
        "preflight_semantic_payload_version": (
            "riskyieldmm.raw_v8_step2_external_schema_v2.preflight_semantic_payload.v1"
        ),
        "canonicalization_version": seed["canonicalization_version"],
        "measurement_schema_version": seed["measurement_schema_version"],
        "contract_id": CONTRACT_ID,
        "protocol_version": seed["protocol_version"],
        "protocol_counting_semantics_id": seed["protocol_counting_semantics_id"],
        "seed_catalog_raw_octets": len(seed_raw),
        "seed_catalog_raw_sha256": sha(seed_raw),
        "seed_catalog_id": seed["seed_catalog_id"],
        "case_universe_catalog_id": ROOT_IDENTITIES["case_universe_catalog"],
        "logical_plan_recipe_catalog_id": ROOT_IDENTITIES[
            "logical_plan_recipe_catalog"
        ],
        "recurrence_catalog_id": ROOT_IDENTITIES["recurrence_catalog"],
        "resource_metric_catalog_id": ROOT_IDENTITIES["resource_metric_catalog"],
        "logical_event_catalog_id": ROOT_IDENTITIES["logical_event_catalog"],
        "f0_seed_ceiling_catalog_id": ROOT_IDENTITIES["f0_seed_ceiling_catalog"],
        "verifier_owned_scope_case_count": len(case_records),
        "ordered_case_result_records": case_records,
        "ordered_metric_summary_records": summaries,
        "semantic_count_vector_sha256": count_sha,
    }
    payload["semantic_payload_id"] = report_identity(
        "RiskYieldMMStep2PreflightSemanticPayloadV1V4_9F_RawV8", payload
    )
    return payload


def publish_atomic(target_argument, raw):
    target = pathlib.Path(target_argument)
    temporary = None
    try:
        if not target.is_absolute():
            fail("OUTPUT_ATOMICITY_INVALID", "output path is not absolute")
        parent = target.parent
        if parent.resolve(strict=True) != parent:
            fail("OUTPUT_ATOMICITY_INVALID", "output parent contains a symlink")
        parent_stat = parent.stat()
        if parent_stat.st_mode & 0o077:
            fail("OUTPUT_ATOMICITY_INVALID", "output parent is not private")
        if target.exists() or target.is_symlink():
            fail("OUTPUT_ATOMICITY_INVALID", "output target already exists")
        if any(parent.iterdir()):
            fail("OUTPUT_ATOMICITY_INVALID", "output parent is not empty")
        temporary = parent / ".raw-v8-step2-preflight-b.tmp"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(temporary, flags, 0o600)
        try:
            offset = 0
            while offset < len(raw):
                written = os.write(descriptor, raw[offset:])
                if written <= 0:
                    fail("OUTPUT_ATOMICITY_INVALID", "output write made no progress")
                offset += written
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.link(temporary, target, follow_symlinks=False)
        os.unlink(temporary)
        temporary = None
        directory_flags = os.O_RDONLY
        if hasattr(os, "O_DIRECTORY"):
            directory_flags |= os.O_DIRECTORY
        directory = os.open(parent, directory_flags)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        if target.stat().st_mode & 0o777 != 0o600 or target.read_bytes() != raw:
            fail("OUTPUT_ATOMICITY_INVALID", "published output differs")
    except Failure:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        raise
    except OSError as exc:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        fail("OUTPUT_ATOMICITY_INVALID", str(exc))


def execute(arguments):
    if (
        len(arguments) != 5
        or arguments[1] != "--seed"
        or arguments[3] != ("--semantic-output")
    ):
        fail("INVOCATION_INVALID", "expected --seed PATH --semantic-output PATH")
    seed, raw = read_seed(arguments[2])
    payload = build_payload(seed, raw)
    publish_atomic(arguments[4], pretty(payload))


def main():
    try:
        execute(sys.argv)
        return 0
    except Failure as exc:
        message = " ".join(str(exc.message).split())[:512]
        sys.stderr.write(
            "RAW_V8_STEP2_MAXIMUM_PROTOCOL_V2_PREFLIGHT_B_"
            + exc.code
            + ": "
            + message
            + "\n"
        )
        return ERROR_EXIT.get(exc.code, ERROR_EXIT["INTERNAL_FAIL_CLOSED"])
    except BaseException as exc:
        message = " ".join(str(exc).split())[:512]
        sys.stderr.write(
            "RAW_V8_STEP2_MAXIMUM_PROTOCOL_V2_PREFLIGHT_B_INTERNAL_FAIL_CLOSED: "
            + message
            + "\n"
        )
        return ERROR_EXIT["INTERNAL_FAIL_CLOSED"]


if __name__ == "__main__":
    raise SystemExit(main())
