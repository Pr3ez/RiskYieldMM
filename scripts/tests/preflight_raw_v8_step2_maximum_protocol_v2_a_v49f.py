#!/usr/bin/env python3
"""S1-A2 preflight A: standalone iterative catalog interpreter.

This process reads only the identity-pinned seed catalog, executes its linked
cell-transfer rule AST, constructs every case event in program order, and
publishes one semantic report.  It deliberately shares no executable code
with preflight B or the seed producer.
"""

import hashlib
import json
import os
import pathlib
import sys

ALGORITHM_MARKER = "ITERATIVE_CATALOG_INTERPRETER_V1"
ROOT = pathlib.Path(__file__).resolve().parents[2]
SEED_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json"
)
SEED_OCTETS = 13_419_905
SEED_SHA256 = "a75a2f352e8513b7ff0043693a0c65ebbf4bc6f06859354789af69e1162b0e4f"
SEED_ID = "ac22151fa74702ac1488924f01161eaa38574545e6272a290db6b0bbd288ae5f"
CONTRACT_ID = "6609ad7b9abf21432136e49af178e20c17cb7bc27d3b444a4b6f01a17073fc76"
SEMANTIC_PAYLOAD_VERSION = (
    "riskyieldmm.raw_v8_step2_external_schema_v2.preflight_semantic_payload.v1"
)
U128_MAX = (1 << 128) - 1
SAFE_INTEGER_MAX = 9_007_199_254_740_991
MAY_BE_NONEMPTY = "MAY_BE_NONEMPTY"
PROVABLY_EMPTY = "PROVABLY_EMPTY"
ERROR_PREFIX = "RAW_V8_STEP2_MAXIMUM_PROTOCOL_V2_PREFLIGHT_A"

EXIT_CODES = {
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

CASE_RESULT_DOMAIN = "RiskYieldMMStep2PreflightCaseResultV1V4_9F_RawV8"
COUNT_VECTOR_DOMAIN = "RiskYieldMMStep2PreflightCountVectorV1V4_9F_RawV8"
SEMANTIC_PAYLOAD_DOMAIN = "RiskYieldMMStep2PreflightSemanticPayloadV1V4_9F_RawV8"


class Reject(Exception):
    """A stable fail-closed rejection."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = str(message).replace("\n", " ")[:768]


def _reject(code, message):
    raise Reject(code, message)


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _u128(value, label="value"):
    if not _is_int(value) or not 0 <= value <= U128_MAX:
        _reject("CHECKED_ARITHMETIC_REJECT", f"{label} is not UInt128")
    return value


def _checked_add(*values):
    total = 0
    for value in values:
        value = _u128(value, "addend")
        if value > U128_MAX - total:
            _reject("CHECKED_ARITHMETIC_REJECT", "UInt128 addition overflow")
        total += value
    return total


def _checked_sub(left, right):
    left = _u128(left, "minuend")
    right = _u128(right, "subtrahend")
    if right > left:
        _reject("CHECKED_ARITHMETIC_REJECT", "UInt128 subtraction underflow")
    return left - right


def _checked_mul(left, right):
    left = _u128(left, "multiplicand")
    right = _u128(right, "multiplier")
    if left and right > U128_MAX // left:
        _reject("CHECKED_ARITHMETIC_REJECT", "UInt128 multiplication overflow")
    return left * right


def _capped_add(ceiling, values):
    ceiling = _u128(ceiling, "ceiling")
    total = 0
    for value in values:
        value = _u128(value, "capped addend")
        if total > ceiling or value > ceiling - total:
            return (ceiling, True)
        total += value
    return (total, False)


def _capped_mul(ceiling, left, right):
    ceiling = _u128(ceiling, "ceiling")
    left = _u128(left, "capped multiplicand")
    right = _u128(right, "capped multiplier")
    if left > ceiling or (left and right > ceiling // left):
        return (ceiling, True)
    return (left * right, False)


def _canonical_bytes(value):
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as error:
        _reject("OUTPUT_SCHEMA_INVALID", f"canonical JSON rejected: {error}")


def _pretty_bytes(value):
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
    except (TypeError, ValueError, UnicodeError) as error:
        _reject("OUTPUT_SCHEMA_INVALID", f"pretty JSON rejected: {error}")


def _sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _domain_id(domain, payload):
    return _sha256(_canonical_bytes({"domain": domain, "payload": payload}))


def _duplicate_closed_object(pairs):
    value = {}
    for key, child in pairs:
        if key in value:
            _reject("INPUT_CANONICALIZATION_INVALID", f"duplicate JSON key: {key}")
        value[key] = child
    return value


def _reject_float(_value):
    _reject("INPUT_CANONICALIZATION_INVALID", "floating-point JSON is forbidden")


def _reject_constant(_value):
    _reject("INPUT_CANONICALIZATION_INVALID", "non-finite JSON is forbidden")


def _parse_json(raw):
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_duplicate_closed_object,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except Reject:
        raise
    except (json.JSONDecodeError, UnicodeError, ValueError) as error:
        _reject("INPUT_CANONICALIZATION_INVALID", f"JSON decode failed: {error}")
    if type(value) is not dict:
        _reject("INPUT_SCHEMA_INVALID", "seed root is not an object")
    if raw != _pretty_bytes(value):
        _reject("INPUT_CANONICALIZATION_INVALID", "seed is not canonical pretty JSON")
    return value


def _validate_json_resources(value, ceilings):
    maximum_depth = ceilings["JSON_NESTING_DEPTH"]
    maximum_nodes = ceilings["DECODED_JSON_NODE_COUNT"]
    maximum_arrays = ceilings["DECODED_JSON_ARRAY_ENTRY_COUNT"]
    maximum_members = ceilings["DECODED_JSON_OBJECT_MEMBER_COUNT"]
    nodes = 0
    arrays = 0
    members = 0
    stack = [(value, 1)]
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > maximum_nodes or depth > maximum_depth:
            _reject("INPUT_LIMIT_EXCEEDED", "decoded JSON node/depth cap exceeded")
        if type(item) is dict:
            members += len(item)
            if members > maximum_members:
                _reject("INPUT_LIMIT_EXCEEDED", "decoded JSON member cap exceeded")
            stack.extend((child, depth + 1) for child in item.values())
        elif type(item) is list:
            arrays += len(item)
            if arrays > maximum_arrays:
                _reject("INPUT_LIMIT_EXCEEDED", "decoded JSON array cap exceeded")
            stack.extend((child, depth + 1) for child in item)


def _read_seed(argument):
    authorized = (ROOT / SEED_RELATIVE_PATH).absolute()
    candidate = pathlib.Path(argument)
    if not candidate.is_absolute():
        candidate = (ROOT / candidate).absolute()
    else:
        candidate = candidate.absolute()
    if candidate != authorized:
        _reject("INPUT_AUTHORITY_INVALID", "seed path is not the sole authority")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(str(authorized), flags)
    except OSError as error:
        _reject("INPUT_AUTHORITY_INVALID", f"seed open failed: {error}")
    try:
        before = os.fstat(descriptor)
        if (before.st_mode & 0o170000) != 0o100000 or before.st_nlink != 1:
            _reject("INPUT_AUTHORITY_INVALID", "seed is not a regular single-link file")
        if before.st_size != SEED_OCTETS:
            _reject("INPUT_LIMIT_EXCEEDED", "seed byte count differs")
        chunks = []
        remaining = SEED_OCTETS + 1
        while remaining:
            chunk = os.read(descriptor, min(1_048_576, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        after = os.fstat(descriptor)
    except OSError as error:
        _reject("INPUT_AUTHORITY_INVALID", f"seed read failed: {error}")
    finally:
        os.close(descriptor)
    stable_fields = (
        "st_dev",
        "st_ino",
        "st_mode",
        "st_nlink",
        "st_size",
        "st_mtime_ns",
        "st_ctime_ns",
    )
    if any(getattr(before, name) != getattr(after, name) for name in stable_fields):
        _reject("INPUT_RACE_DETECTED", "seed metadata changed during read")
    if len(raw) != SEED_OCTETS or _sha256(raw) != SEED_SHA256:
        _reject("INPUT_AUTHORITY_INVALID", "seed physical identity differs")
    return raw


def _cell(status, lower, upper, state):
    return {
        "status": status,
        "lower": lower,
        "upper": upper,
        "state": list(state),
    }


def _empty(state=()):
    return _cell(PROVABLY_EMPTY, 0, 0, state)


def _nonempty(lower, upper, ceiling, state=()):
    lower = _u128(lower, "cell lower")
    upper = _u128(upper, "cell upper")
    ceiling = _u128(ceiling, "cell ceiling")
    if not lower <= upper <= ceiling:
        _reject("CASE_SEMANTIC_REJECT", "nonempty cell violates its interval")
    return _cell(MAY_BE_NONEMPTY, lower, upper, state)


def _validate_cell(value, ceiling):
    if type(value) is not dict or set(value) != {"status", "lower", "upper", "state"}:
        _reject("CASE_SEMANTIC_REJECT", "value is not a closed cell")
    if type(value["state"]) is not list:
        _reject("CASE_SEMANTIC_REJECT", "cell state is not a list")
    if value["status"] == PROVABLY_EMPTY:
        if value["lower"] != 0 or value["upper"] != 0:
            _reject("CASE_SEMANTIC_REJECT", "empty cell is not normalized")
        return value
    if value["status"] != MAY_BE_NONEMPTY:
        _reject("CASE_SEMANTIC_REJECT", "cell status is unknown")
    _nonempty(value["lower"], value["upper"], ceiling, value["state"])
    return value


def _clip_bounds(lower, upper, ceiling, state=()):
    lower = _u128(lower, "raw lower")
    upper = _u128(upper, "raw upper")
    ceiling = _u128(ceiling, "effective ceiling")
    if lower > upper:
        _reject("CASE_SEMANTIC_REJECT", "raw cell interval is inverted")
    if lower > ceiling:
        return _empty(state)
    return _nonempty(lower, min(upper, ceiling), ceiling, state)


def _clip_cell(value, ceiling):
    value = _validate_cell(value, U128_MAX)
    if value["status"] == PROVABLY_EMPTY:
        return value
    return _clip_bounds(value["lower"], value["upper"], ceiling, value["state"])


def _canonical_string_octets(value):
    if not isinstance(value, str):
        _reject("CASE_SEMANTIC_REJECT", "text transfer operand is not text")
    try:
        return len(
            json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        )
    except (ValueError, UnicodeError) as error:
        _reject("CASE_SEMANTIC_REJECT", f"text transfer rejected: {error}")


def _require_bool(value, label):
    if type(value) is not bool:
        _reject("CASE_SEMANTIC_REJECT", f"{label} is not boolean")
    return value


def _eval_ast(expression, parameters, children, ceiling, variables, runtime):
    if type(expression) is not dict or "opcode" not in expression:
        _reject("CASE_SEMANTIC_REJECT", "transfer AST node is not an object")
    opcode = expression["opcode"]
    signature = runtime["primitive_signatures"].get(opcode)
    if signature is None or set(expression) != {"opcode", *signature}:
        _reject("CASE_SEMANTIC_REJECT", f"transfer AST schema differs: {opcode}")

    def evaluate(child):
        return _eval_ast(child, parameters, children, ceiling, variables, runtime)

    if opcode == "CONST_V1":
        return expression["value"]
    if opcode == "PARAM_V1":
        name = expression["parameter_name"]
        if name not in parameters:
            _reject("CASE_SEMANTIC_REJECT", f"transfer parameter is absent: {name}")
        return parameters[name]
    if opcode == "CHILD_V1":
        index = _u128(expression["zero_based_index"], "child index")
        if index >= len(children):
            _reject("CASE_SEMANTIC_REJECT", "child index is out of range")
        return _validate_cell(children[index], U128_MAX)
    if opcode == "CHILDREN_V1":
        return [_validate_cell(child, U128_MAX) for child in children]
    if opcode == "CEILING_V1":
        return _u128(ceiling, "effective ceiling")
    if opcode == "VAR_V1":
        name = expression["variable_name"]
        if name not in variables:
            _reject("CASE_SEMANTIC_REJECT", f"transfer variable is absent: {name}")
        return variables[name]
    if opcode == "LET_V1":
        scoped = dict(variables)
        seen = set()
        for binding in expression["ordered_bindings"]:
            if list(binding) != ["binding_name", "value_expression"]:
                _reject("CASE_SEMANTIC_REJECT", "LET binding schema differs")
            name = binding["binding_name"]
            if not isinstance(name, str) or not name or name in seen:
                _reject("CASE_SEMANTIC_REJECT", "LET binding name differs")
            scoped[name] = _eval_ast(
                binding["value_expression"],
                parameters,
                children,
                ceiling,
                scoped,
                runtime,
            )
            seen.add(name)
        return _eval_ast(
            expression["result_expression"],
            parameters,
            children,
            ceiling,
            scoped,
            runtime,
        )
    if opcode == "IF_V1":
        branch = (
            expression["then_expression"]
            if _require_bool(evaluate(expression["condition"]), "IF condition")
            else expression["else_expression"]
        )
        return evaluate(branch)
    if opcode == "VALIDATE_V1":
        if not _require_bool(evaluate(expression["condition"]), "VALIDATE condition"):
            _reject(
                "CASE_SEMANTIC_REJECT",
                f"transfer validation failed: {expression['error_code']}",
            )
        return evaluate(expression["result_expression"])
    if opcode in {"EQ_V1", "LE_V1", "LT_V1"}:
        left = evaluate(expression["left"])
        right = evaluate(expression["right"])
        if opcode == "EQ_V1":
            return left == right
        if opcode == "LE_V1":
            return left <= right
        return left < right
    if opcode in {"AND_V1", "OR_V1"}:
        values = [
            _require_bool(evaluate(item), f"{opcode} operand")
            for item in expression["ordered_operands"]
        ]
        return all(values) if opcode == "AND_V1" else any(values)
    if opcode == "NOT_V1":
        return not _require_bool(evaluate(expression["operand"]), "NOT operand")
    if opcode == "IN_SET_V1":
        if type(expression["ordered_values"]) is not list:
            _reject("CASE_SEMANTIC_REJECT", "IN_SET values are not a list")
        return evaluate(expression["operand"]) in expression["ordered_values"]
    if opcode.startswith("IS_"):
        operand = evaluate(expression.get("operand", expression.get("cell")))
        if opcode == "IS_NULL_V1":
            return operand is None
        if opcode == "IS_BOOLEAN_V1":
            return type(operand) is bool
        if opcode == "IS_TEXT_V1":
            return isinstance(operand, str)
        if opcode == "IS_U128_V1":
            return _is_int(operand) and 0 <= operand <= U128_MAX
        if opcode == "IS_SIGNED_SAFE_INTEGER_V1":
            return _is_int(operand) and -SAFE_INTEGER_MAX <= operand <= SAFE_INTEGER_MAX
        if opcode == "IS_LIST_V1":
            return type(operand) is list
        if opcode == "IS_MAPPING_V1":
            return type(operand) is dict
        if opcode == "IS_CELL_EMPTY_V1":
            return _validate_cell(operand, U128_MAX)["status"] == PROVABLY_EMPTY
    if opcode == "HAS_EXACT_KEYS_V1":
        mapping = evaluate(expression["mapping"])
        keys = expression["ordered_keys"]
        return type(mapping) is dict and type(keys) is list and list(mapping) == keys
    if opcode == "FIELD_V1":
        mapping = evaluate(expression["mapping"])
        name = expression["field_name"]
        if type(mapping) is not dict or name not in mapping:
            _reject("CASE_SEMANTIC_REJECT", f"mapping field is absent: {name}")
        return mapping[name]
    if opcode == "INDEX_V1":
        sequence = evaluate(expression["sequence"])
        index = _u128(evaluate(expression["zero_based_index"]), "sequence index")
        if type(sequence) not in {list, tuple} or index >= len(sequence):
            _reject("CASE_SEMANTIC_REJECT", "sequence index is out of range")
        return sequence[index]
    if opcode == "LIST_V1":
        return [evaluate(item) for item in expression["ordered_items"]]
    if opcode == "CONCAT_V1":
        output = []
        for child in expression["ordered_sequences"]:
            sequence = evaluate(child)
            if type(sequence) is not list:
                _reject("CASE_SEMANTIC_REJECT", "CONCAT operand is not a list")
            output.extend(sequence)
        return output
    if opcode == "LIST_LENGTH_V1":
        sequence = evaluate(expression["sequence"])
        if type(sequence) not in {list, tuple}:
            _reject("CASE_SEMANTIC_REJECT", "LIST_LENGTH operand is not a sequence")
        return _u128(len(sequence), "sequence length")
    if opcode in {"MAP_V1", "FILTER_V1", "ANY_V1", "ALL_V1"}:
        sequence = evaluate(expression["sequence"])
        if type(sequence) not in {list, tuple}:
            _reject("CASE_SEMANTIC_REJECT", f"{opcode} sequence differs")
        variable = expression["item_variable"]
        expression_name = "map_expression" if opcode == "MAP_V1" else "predicate"
        results = [
            _eval_ast(
                expression[expression_name],
                parameters,
                children,
                ceiling,
                {**variables, variable: item},
                runtime,
            )
            for item in sequence
        ]
        if opcode == "MAP_V1":
            return results
        admitted = [_require_bool(item, f"{opcode} predicate") for item in results]
        if opcode == "FILTER_V1":
            return [item for item, keep in zip(sequence, admitted) if keep]
        return any(admitted) if opcode == "ANY_V1" else all(admitted)
    if opcode == "ALL_INDEXED_V1":
        sequence = evaluate(expression["sequence"])
        if type(sequence) not in {list, tuple}:
            _reject("CASE_SEMANTIC_REJECT", "ALL_INDEXED sequence differs")
        results = []
        for index, item in enumerate(sequence):
            scoped = {
                **variables,
                expression["index_variable"]: index,
                expression["item_variable"]: item,
            }
            results.append(
                _require_bool(
                    _eval_ast(
                        expression["predicate"],
                        parameters,
                        children,
                        ceiling,
                        scoped,
                        runtime,
                    ),
                    "ALL_INDEXED predicate",
                )
            )
        return all(results)
    if opcode in {"FOLD_MIN_U128_V1", "FOLD_MAX_U128_V1"}:
        sequence = evaluate(expression["sequence"])
        if type(sequence) is not list or not sequence:
            _reject("CASE_SEMANTIC_REJECT", "integer extrema sequence is empty")
        values = [_u128(item, "extrema operand") for item in sequence]
        return min(values) if opcode == "FOLD_MIN_U128_V1" else max(values)
    if opcode == "CHECKED_ADD_LIST_U128_V1":
        sequence = evaluate(expression["sequence"])
        if type(sequence) is not list:
            _reject("CASE_SEMANTIC_REJECT", "checked-add operand is not a list")
        return _checked_add(*sequence)
    if opcode == "CHECKED_SUB_U128_V1":
        return _checked_sub(evaluate(expression["left"]), evaluate(expression["right"]))
    if opcode == "CHECKED_MUL_U128_V1":
        return _checked_mul(evaluate(expression["left"]), evaluate(expression["right"]))
    if opcode == "CAPPED_ADD_LIST_U128_V1":
        sequence = evaluate(expression["sequence"])
        if type(sequence) is not list:
            _reject("CASE_SEMANTIC_REJECT", "capped-add operand is not a list")
        return _capped_add(evaluate(expression["ceiling"]), sequence)
    if opcode == "CAPPED_MUL_U128_V1":
        return _capped_mul(
            evaluate(expression["ceiling"]),
            evaluate(expression["left"]),
            evaluate(expression["right"]),
        )
    if opcode in {"CAPPED_VALUE_V1", "CAPPED_EXCEEDED_V1"}:
        capped = evaluate(expression["capped_value"])
        if type(capped) is not tuple or len(capped) != 2 or type(capped[1]) is not bool:
            _reject("CASE_SEMANTIC_REJECT", "capped projection differs")
        return capped[0] if opcode == "CAPPED_VALUE_V1" else capped[1]
    if opcode == "DECIMAL_OCTETS_V1":
        value = evaluate(expression["signed_integer"])
        if not _is_int(value) or not -SAFE_INTEGER_MAX <= value <= SAFE_INTEGER_MAX:
            _reject("CASE_SEMANTIC_REJECT", "decimal operand is not a safe integer")
        return len(str(value).encode("ascii"))
    if opcode == "CANONICAL_STRING_OCTETS_V1":
        return _canonical_string_octets(evaluate(expression["text"]))
    if opcode == "CELL_EMPTY_V1":
        state = evaluate(expression["state_expression"])
        if type(state) is not list:
            _reject("CASE_SEMANTIC_REJECT", "empty cell state is not a list")
        return _empty(state)
    if opcode == "CELL_BUILD_CLIPPED_V1":
        state = evaluate(expression["state_expression"])
        if type(state) is not list:
            _reject("CASE_SEMANTIC_REJECT", "cell state is not a list")
        return _clip_bounds(
            evaluate(expression["lower"]),
            evaluate(expression["upper"]),
            evaluate(expression["ceiling"]),
            state,
        )
    if opcode == "CELL_BUILD_FROM_CAPPED_V1":
        lower = evaluate(expression["lower_capped"])
        upper = evaluate(expression["upper_capped"])
        state = evaluate(expression["state_expression"])
        target = evaluate(expression["ceiling"])
        if (
            type(lower) is not tuple
            or type(upper) is not tuple
            or type(state) is not list
        ):
            _reject("CASE_SEMANTIC_REJECT", "bounded cell operands differ")
        return (
            _empty(state) if lower[1] else _nonempty(lower[0], upper[0], target, state)
        )
    if opcode == "CELL_CLIP_V1":
        return _clip_cell(evaluate(expression["cell"]), evaluate(expression["ceiling"]))
    if opcode in {"CELL_LOWER_V1", "CELL_UPPER_V1", "CELL_STATE_V1"}:
        value = _validate_cell(evaluate(expression["cell"]), U128_MAX)
        if opcode == "CELL_LOWER_V1":
            return value["lower"]
        if opcode == "CELL_UPPER_V1":
            return value["upper"]
        return list(value["state"])
    if opcode == "CALL_RULE_V1":
        rule = runtime["rules_by_id"].get(expression["transfer_rule_id"])
        if rule is None:
            _reject("CASE_SEMANTIC_REJECT", "called transfer rule is absent")
        arguments = {}
        for binding in expression["ordered_argument_bindings"]:
            if list(binding) != ["parameter_name", "value_expression"]:
                _reject("CASE_SEMANTIC_REJECT", "rule argument schema differs")
            name = binding["parameter_name"]
            if name in arguments:
                _reject("CASE_SEMANTIC_REJECT", "rule argument is duplicate")
            arguments[name] = evaluate(binding["value_expression"])
        return _run_rule(rule, arguments, children, ceiling, runtime)
    if opcode == "RESOLVE_LOCAL_CATALOG_V1":
        catalog_id = evaluate(expression["catalog_id"])
        value = runtime["local_catalogs_by_id"].get(catalog_id)
        if value is None:
            _reject("CASE_SEMANTIC_REJECT", "local catalog identity did not resolve")
        return value
    _reject("CASE_SEMANTIC_REJECT", f"transfer opcode is not implemented: {opcode}")


def _run_rule(rule, parameters, children, ceiling, runtime):
    names = rule["ordered_parameter_names"]
    if type(parameters) is not dict or set(parameters) != set(names):
        _reject("CASE_SEMANTIC_REJECT", "transfer rule parameter order differs")
    parameters = {name: parameters[name] for name in names}
    value = _eval_ast(rule["program"], parameters, children, ceiling, {}, runtime)
    return _validate_cell(value, ceiling)


def _json_pointer(root, pointer):
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        _reject("INPUT_SCHEMA_INVALID", "JSON pointer differs")
    value = root
    for encoded in pointer[1:].split("/"):
        part = encoded.replace("~1", "/").replace("~0", "~")
        if type(value) is list:
            if not part.isdigit() or (len(part) > 1 and part.startswith("0")):
                _reject("INPUT_SCHEMA_INVALID", "JSON pointer array index differs")
            index = int(part)
            if index >= len(value):
                _reject("INPUT_SCHEMA_INVALID", "JSON pointer index is absent")
            value = value[index]
        elif type(value) is dict and part in value:
            value = value[part]
        else:
            _reject("INPUT_SCHEMA_INVALID", "JSON pointer member is absent")
    return value


def _validate_seed(seed, raw):
    if seed.get("seed_catalog_id") != SEED_ID:
        _reject("INPUT_IDENTITY_INVALID", "seed semantic identity differs")
    if seed.get("catalog_version") != (
        "riskyieldmm.raw_v8_step2_external_schema_v2.maximum_protocol_v2_seed_catalog.v1"
    ):
        _reject("INPUT_SCHEMA_INVALID", "seed version differs")
    required_roots = (
        (
            "case_universe_catalog",
            "65376f9ceb08f91f0476b6f97ffa3fe3896a140a99b289388ccc3e453cc4c652",
        ),
        (
            "logical_plan_recipe_catalog",
            "727f4008c6cd469fe2a9c7f833b0bb6a56ba18a17009871e7fb4ceaa2c0aede8",
        ),
        (
            "recurrence_catalog",
            "743ab1fdf8f15da1b38331dc23fcf79dd4a89c2767013afba421107deeeecbcd",
        ),
        (
            "resource_metric_catalog",
            "1d15e95819fa32d37e7b6eaadc1a9ae410db56f347bf8ead583d0d31f9493652",
        ),
        (
            "logical_event_catalog",
            "072733938c00a6617fd59375a76ec9824590a0c140e32430efd7009ce1d77c4b",
        ),
        (
            "f0_seed_ceiling_catalog",
            "89a8803593c1225b237a4646de06a2b2f6cf495859199048fdabfa6e97e083b4",
        ),
    )
    for name, expected in required_roots:
        value = seed.get(name)
        if type(value) is not dict or value.get(f"{name}_id") != expected:
            _reject("INPUT_IDENTITY_INVALID", f"semantic root differs: {name}")
    ceilings = {}
    rows = seed["f0_seed_ceiling_catalog"]["ordered_platform_ceiling_records"]
    if type(rows) is not list or len(rows) != 12:
        _reject("INPUT_SCHEMA_INVALID", "F0 ceiling catalog differs")
    for position, row in enumerate(rows, 1):
        if row.get("ceiling_position") != position:
            _reject("INPUT_SCHEMA_INVALID", "F0 ceiling order differs")
        ceilings[row["resource_name"]] = _u128(row["ceiling_value"], "F0 ceiling")
    if len(raw) >= ceilings["INDIVIDUAL_FILE_STRICT_UPPER_OCTETS"]:
        _reject("INPUT_LIMIT_EXCEEDED", "seed exceeds strict individual-file cap")
    _validate_json_resources(seed, ceilings)
    universe = seed["case_universe_catalog"]
    if (
        universe.get("verifier_owned_case_count") != 475
        or universe.get("maximum_row_count") != 474
    ):
        _reject("INPUT_SCHEMA_INVALID", "case universe cardinality differs")
    return ceilings


def _build_runtime(seed):
    recurrence = seed["recurrence_catalog"]
    rule_catalog = recurrence["transfer_rule_catalog"]
    primitive_signatures = {}
    for position, row in enumerate(rule_catalog["ordered_primitive_opcode_records"], 1):
        if (
            row.get("opcode_position") != position
            or row["opcode"] in primitive_signatures
        ):
            _reject("INPUT_SCHEMA_INVALID", "primitive transfer opcode order differs")
        primitive_signatures[row["opcode"]] = row[
            "ordered_required_member_names_after_opcode"
        ]
    if len(primitive_signatures) != 55:
        _reject("INPUT_SCHEMA_INVALID", "primitive transfer opcode count differs")
    rules_by_id = {}
    for position, rule in enumerate(rule_catalog["ordered_transfer_rule_records"], 1):
        if (
            rule.get("rule_position") != position
            or rule["transfer_rule_id"] in rules_by_id
        ):
            _reject("INPUT_SCHEMA_INVALID", "transfer rule order differs")
        rules_by_id[rule["transfer_rule_id"]] = rule
    if len(rules_by_id) != 19:
        _reject("INPUT_SCHEMA_INVALID", "transfer rule count differs")
    opcode_rows = recurrence["instruction_set"]["transfer_program_schema"][
        "ordered_transfer_opcode_records"
    ]
    opcode_to_rule = {}
    for position, row in enumerate(opcode_rows, 1):
        if row.get("opcode_position") != position or row["opcode"] in opcode_to_rule:
            _reject("INPUT_SCHEMA_INVALID", "cell opcode order differs")
        rule_id = row["transfer_rule_id"]
        if rule_id not in rules_by_id:
            _reject("INPUT_SCHEMA_INVALID", "cell opcode rule identity is absent")
        opcode_to_rule[row["opcode"]] = rule_id
    if len(opcode_to_rule) != 18:
        _reject("INPUT_SCHEMA_INVALID", "cell opcode count differs")
    local = recurrence["local_shutdown_analytic_catalog"]
    return {
        "primitive_signatures": primitive_signatures,
        "rules_by_id": rules_by_id,
        "opcode_to_rule": opcode_to_rule,
        "local_catalogs_by_id": {local["local_shutdown_analytic_catalog_id"]: local},
    }


def _eval_u128_expression(expression, step):
    if type(expression) is not dict or "opcode" not in expression:
        _reject("CASE_SEMANTIC_REJECT", "meter expression differs")
    opcode = expression["opcode"]
    if opcode == "CONST_U128" and set(expression) == {"opcode", "value"}:
        return _u128(expression["value"], "meter constant")
    if opcode == "STEP_LOGICAL_TRANSFER_MULTIPLICITY" and set(expression) == {"opcode"}:
        return _u128(step["logical_transfer_multiplicity"], "transfer multiplicity")
    if opcode == "PARAM_U128" and set(expression) == {"opcode", "parameter_name"}:
        return _u128(
            step["recurrence_parameters"][expression["parameter_name"]],
            "meter parameter",
        )
    if opcode == "PARAM_LIST_COUNT" and set(expression) == {
        "opcode",
        "parameter_name",
    }:
        value = step["recurrence_parameters"][expression["parameter_name"]]
        if type(value) is not list:
            _reject("CASE_SEMANTIC_REJECT", "meter list parameter differs")
        return _u128(len(value), "meter list length")
    if opcode in {"INDICATOR_PARAM_NONZERO", "INDICATOR_PARAM_IS_NULL"} and set(
        expression
    ) == {"opcode", "parameter_name"}:
        value = step["recurrence_parameters"][expression["parameter_name"]]
        return (
            int(value is not None)
            if opcode == "INDICATOR_PARAM_NONZERO"
            else int(value is None)
        )
    if opcode in {"CHECKED_ADD", "CHECKED_MUL"} and set(expression) == {
        "opcode",
        "ordered_operands",
    }:
        values = [
            _eval_u128_expression(item, step) for item in expression["ordered_operands"]
        ]
        if not values:
            _reject("CASE_SEMANTIC_REJECT", "meter arithmetic has no operands")
        if opcode == "CHECKED_ADD":
            return _checked_add(*values)
        product = 1
        for value in values:
            product = _checked_mul(product, value)
        return product
    _reject("CASE_SEMANTIC_REJECT", f"meter opcode differs: {opcode}")


def _execute_template(template, seed, runtime):
    recurrence = seed["recurrence_catalog"]
    ceiling = _u128(
        recurrence["arithmetic_policy"]["published_maximum"], "ambient ceiling"
    )
    kernels = {
        row["derivation_kind"]: row
        for row in recurrence["ordered_derivation_kernel_records"]
    }
    if len(kernels) != 18:
        _reject("INPUT_SCHEMA_INVALID", "derivation-kernel catalog differs")
    cells = []
    steps = template["ordered_template_steps"]
    for position, step in enumerate(steps, 1):
        if step.get("template_step_position") != position:
            _reject("CASE_SEMANTIC_REJECT", "template is not strict postorder")
        kernel = kernels.get(step["derivation_kind"])
        if (
            kernel is None
            or kernel["kernel_record_sha256"] != step["kernel_record_sha256"]
        ):
            _reject("CASE_SEMANTIC_REJECT", "step kernel identity differs")
        child_positions = step["ordered_child_step_positions"]
        if type(child_positions) is not list or any(
            not _is_int(child) or not 1 <= child < position for child in child_positions
        ):
            _reject("CASE_SEMANTIC_REJECT", "step child order is not strict postorder")
        parameters = step["recurrence_parameters"]
        if type(parameters) is not dict or set(parameters) != set(
            kernel["ordered_parameter_member_names"]
        ):
            _reject(
                "CASE_SEMANTIC_REJECT",
                f"step parameter order differs: {template['logical_plan_template_id']}:{position}:{step['derivation_kind']}",
            )
        meter = kernel["meter_program"]
        expected = (
            (
                "physical_transition_count",
                "transition_attempt_count_expression",
            ),
            (
                "logical_unbatched_transition_equivalent_count",
                "logical_unbatched_transition_equivalent_count_expression",
            ),
            (
                "physical_batch_application_count",
                "batch_application_count_expression",
            ),
        )
        for member, expression_member in expected:
            if _eval_u128_expression(meter[expression_member], step) != step[member]:
                _reject("CASE_SEMANTIC_REJECT", f"step meter mismatch: {member}")
        opcode = kernel["transfer_program"]["opcode"]
        rule_id = runtime["opcode_to_rule"].get(opcode)
        if rule_id is None:
            _reject("CASE_SEMANTIC_REJECT", "cell transfer opcode is absent")
        cell = _run_rule(
            runtime["rules_by_id"][rule_id],
            parameters,
            [cells[child - 1] for child in child_positions],
            ceiling,
            runtime,
        )
        cells.append(cell)
    if template.get("root_step_position") != len(steps):
        _reject("CASE_SEMANTIC_REJECT", "template root is not final postorder step")
    return cells


def _condition_profile_root(plan, profile, cells, seed):
    root_index = plan["root_step_position"] - 1
    strategy = profile["conditioning_strategy"]
    if strategy == "STRUCTURAL_TEMPLATE_SUPERSET_WITH_EXACT_RETAINED_ATTAINMENT_V1":
        return cells
    if strategy != "LOCAL_SHUTDOWN_BASELINE_ANALYTIC_EXACT_V1":
        _reject("CASE_SEMANTIC_REJECT", "profile conditioning strategy differs")
    if plan["case_position"] != 69 or profile["profile_position"] != 3:
        _reject("CASE_SEMANTIC_REJECT", "local baseline profile binding differs")
    p2 = profile["conditioning_transfer_program"]["p2_upper_bound_program"]
    opcodes = [row["opcode"] for row in p2["ordered_instruction_records"]]
    if opcodes != [
        "LOAD_STRUCTURAL_TEMPLATE_SUPERSET_CELL_V1",
        "LOAD_FIXED_AUTHORITY_SET_V1",
        "EXECUTE_LOCAL_SHUTDOWN_BASELINE_ANALYTIC_EXACT_V1",
        "INTERSECT_EXACT_ANALYTIC_WITH_STRUCTURAL_CELL_V1",
    ]:
        _reject("CASE_SEMANTIC_REJECT", "local baseline P2 program differs")
    local = seed["recurrence_catalog"]["local_shutdown_analytic_catalog"]
    batch = next(
        (
            row
            for row in local["ordered_mutable_limit_records"]
            if row["member_name"] == "maximum_terminal_ingress_batches"
        ),
        None,
    )
    if batch is None:
        _reject("CASE_SEMANTIC_REJECT", "local baseline batch authority is absent")
    value = _u128(batch["baseline_value"], "local baseline batch limit")
    formula = local["batch_unsaturated_program"]
    derived = _checked_add(
        formula["constant_octets"],
        _checked_mul(formula["linear_coefficient"], value),
        _checked_mul(formula["decimal_width_coefficient"], len(str(value))),
    )
    if derived != local["baseline_attainable_maximum_octets"]:
        _reject("CASE_SEMANTIC_REJECT", "local baseline analytic result differs")
    structural = cells[root_index]
    if structural["status"] != MAY_BE_NONEMPTY or derived > structural["upper"]:
        _reject("CASE_SEMANTIC_REJECT", "local baseline exceeds structural root")
    conditioned = list(cells)
    conditioned[root_index] = _cell(
        MAY_BE_NONEMPTY, derived, derived, structural["state"]
    )
    return conditioned


def _tagged_subject(schema, values):
    members = schema["ordered_member_names"]
    version_member = members[0]
    complete = {version_member: schema[version_member], **values}
    if set(complete) != set(members):
        _reject("CASE_SEMANTIC_REJECT", "tagged subject members differ")
    return {name: complete[name] for name in members}


class _CaseEvents:
    def __init__(self, seed, plan):
        self.seed = seed
        self.plan = plan
        self.recurrence = seed["recurrence_catalog"]
        self.grammar = seed["logical_event_catalog"]["case_level_event_grammar"]
        self.programs = {
            row["program_name"]: row
            for row in self.grammar["ordered_case_program_records"]
        }
        self.metadata = {
            row["program_name"]: row
            for row in self.grammar["event_metadata_program"][
                "ordered_program_metadata_records"
            ]
        }
        self.subject_schemas = {
            row["event_kind"]: row
            for row in self.grammar["ordered_subject_schema_records"]
        }
        execution = self.grammar["full_case_execution_program"]
        self.constructors = {
            row["event_kind"]: row
            for row in execution["ordered_subject_constructor_records"]
        }
        self.metric_programs = {
            row["event_kind"]: row["ordered_metric_update_program"]
            for row in seed["logical_event_catalog"]["ordered_event_kind_records"]
        }
        if not (
            len(self.programs) == len(self.metadata) == 9
            and len(self.subject_schemas) == len(self.constructors) == 16
        ):
            _reject("INPUT_SCHEMA_INVALID", "event-program catalogs differ")
        self.tokens = []
        self.event_ordinals = {}
        self.measurements = dict.fromkeys(range(1, 19), 0)

    def construct(self, event_kind, context):
        constructor = self.constructors[event_kind]
        if constructor["event_kind"] != event_kind:
            _reject("CASE_SEMANTIC_REJECT", "subject constructor binding differs")
        if constructor["constructor_opcode"] == "USE_EXACT_HASH_SOURCE_BYTES_V1":
            raw = context.get("ORDERED_CASE_HASH_PROGRAM_SELECTED_PREIMAGE_BYTES")
            if type(raw) is not bytes:
                _reject("CASE_SEMANTIC_REJECT", "hash preimage bytes are absent")
            return raw
        values = {}
        for position, row in enumerate(constructor["ordered_value_source_records"], 1):
            if row.get("value_source_position") != position:
                _reject("CASE_SEMANTIC_REJECT", "constructor value order differs")
            source = row["value_source"]
            if source.startswith("CONST:"):
                value = source[6:]
            elif source == "null":
                value = None
            elif source in context:
                value = context[source]
            else:
                _reject(
                    "CASE_SEMANTIC_REJECT",
                    f"constructor source is unresolved: {event_kind}:{source}",
                )
            name = row["member_name"]
            if name in values:
                _reject("CASE_SEMANTIC_REJECT", "constructor member is duplicate")
            values[name] = value
        order_source = constructor["subject_member_order_source"]
        if order_source == "CONSTRUCTOR_ORDERED_VALUE_SOURCE_RECORDS":
            members = [
                row["member_name"]
                for row in constructor["ordered_value_source_records"]
            ]
        elif (
            order_source == "/recurrence_catalog/cache_key_schema/ordered_member_names"
        ):
            members = self.recurrence["cache_key_schema"]["ordered_member_names"]
        elif order_source == (
            "/recurrence_catalog/transition_token_schema/ordered_member_names"
        ):
            members = self.recurrence["transition_token_schema"]["ordered_member_names"]
        elif (
            order_source
            == "/recurrence_catalog/result_cell_schema/ordered_member_names"
        ):
            members = self.recurrence["result_cell_schema"]["ordered_member_names"]
        elif order_source == (
            "/recurrence_catalog/step_commitment_schema/ordered_member_names"
        ):
            members = self.recurrence["step_commitment_schema"]["ordered_member_names"]
        elif order_source == (
            "/logical_event_catalog/case_level_event_grammar/"
            "final_result_subject_contract/ordered_member_names"
        ):
            members = self.grammar["final_result_subject_contract"][
                "ordered_member_names"
            ]
        else:
            _reject("CASE_SEMANTIC_REJECT", "subject member-order source differs")
        if set(values) != set(members):
            _reject("CASE_SEMANTIC_REJECT", f"subject members differ: {event_kind}")
        return {name: values[name] for name in members}

    def add(
        self,
        program_name,
        emission_position,
        subject,
        source_record=None,
        collection_ordinal=None,
        derivation_unit_ordinal=None,
        ordinary_step_position=None,
    ):
        program = self.programs[program_name]
        metadata = self.metadata[program_name]
        emissions = program["ordered_event_emission_records"]
        if not 1 <= emission_position <= len(emissions):
            _reject("CASE_SEMANTIC_REJECT", "event emission position differs")
        emission = emissions[emission_position - 1]
        if emission["emission_position"] != emission_position:
            _reject("CASE_SEMANTIC_REJECT", "event emission order differs")
        event_kind = emission["event_kind"]
        source_record = source_record or {}

        def expression_value(expression, field_default=None):
            opcode = expression["opcode"]
            if opcode == "CONST_U128" and set(expression) == {"opcode", "value"}:
                return _u128(expression["value"], "event constant")
            if opcode == "SOURCE_FIELD_U128" and set(expression) == {
                "opcode",
                "field_name",
            }:
                name = expression["field_name"]
                if name not in source_record:
                    if field_default is not None:
                        return field_default
                    _reject(
                        "CASE_SEMANTIC_REJECT", f"event source field is absent: {name}"
                    )
                return _u128(source_record[name], f"event source field {name}")
            _reject("CASE_SEMANTIC_REJECT", "event expression opcode differs")

        if expression_value(emission["condition_expression"]) != 1:
            _reject("CASE_SEMANTIC_REJECT", "selected event condition is false")
        aggregation = expression_value(
            emission["aggregation_multiplicity_expression"], 1
        )
        logical = expression_value(
            emission["logical_unbatched_equivalent_count_expression"], 0
        )
        ordinal = self.event_ordinals.get(event_kind, 0) + 1
        ordinal_source = metadata["subject_ordinal_sources"][emission_position - 1]
        if ordinal_source == "NULL":
            subject_ordinal = None
        elif ordinal_source == "EMISSION_SUBJECT_COLLECTION_ORDINAL":
            subject_ordinal = collection_ordinal
        elif ordinal_source == "EVENT_KIND_ORDINAL":
            subject_ordinal = ordinal
        elif ordinal_source == "DERIVATION_UNIT_ORDINAL":
            subject_ordinal = derivation_unit_ordinal
        else:
            _reject("CASE_SEMANTIC_REJECT", "event subject-ordinal source differs")
        if ordinal_source != "NULL" and subject_ordinal is None:
            _reject("CASE_SEMANTIC_REJECT", "event subject ordinal is unresolved")
        step_source = metadata["logical_derivation_step_position_source"]
        if step_source == "CURRENT_ORDINARY_TEMPLATE_STEP_POSITION":
            step_position = ordinary_step_position
            if step_position is None:
                _reject("CASE_SEMANTIC_REJECT", "ordinary event step is unresolved")
        elif step_source == "NULL":
            step_position = None
        else:
            _reject("CASE_SEMANTIC_REJECT", "event step source differs")
        observed_source = metadata["observed_value_sources"][emission_position - 1]
        if observed_source == "NULL":
            observed = None
        elif observed_source == "SUBJECT_OBSERVED_VALUE":
            if type(subject) is not dict:
                _reject("CASE_SEMANTIC_REJECT", "observed event subject differs")
            observed = subject.get(
                "observed_value",
                subject.get("derived_depth", subject.get("iteration_depth")),
            )
            _u128(observed, "event observed value")
        else:
            _reject("CASE_SEMANTIC_REJECT", "event observed-value source differs")
        raw = subject if type(subject) is bytes else _canonical_bytes(subject)
        schema = self.subject_schemas[event_kind]
        token = {
            "event_position": len(self.tokens) + 1,
            "execution_phase": emission["execution_phase"],
            "logical_derivation_step_position": step_position,
            "event_kind": event_kind,
            "event_ordinal": ordinal,
            "subject_schema_version": schema["subject_schema_version"],
            "subject_kind": schema["subject_kind"],
            "subject_role": metadata["ordered_subject_role_literals"][
                emission_position - 1
            ],
            "subject_ordinal": subject_ordinal,
            "subject_canonical_octets": len(raw),
            "subject_sha256": _sha256(raw),
            "aggregation_multiplicity": aggregation,
            "logical_unbatched_equivalent_count": logical,
            "observed_value": observed,
        }
        self.tokens.append(token)
        self.event_ordinals[event_kind] = ordinal
        for update in self.metric_programs[event_kind]:
            source = update["value_source"]
            if source == "ONE":
                value = 1
            elif source == "SUBJECT_CANONICAL_OCTETS":
                value = len(raw)
            elif source == "AGGREGATION_MULTIPLICITY":
                value = aggregation
            elif source == "LOGICAL_UNBATCHED_EQUIVALENT_COUNT":
                value = logical
            elif source == "OBSERVED_VALUE":
                value = observed
            else:
                _reject("CASE_SEMANTIC_REJECT", "metric event value source differs")
            value = _u128(value, "metric event value")
            position = update["metric_position"]
            if update["update_kind"] == "ADD":
                self.measurements[position] = _checked_add(
                    self.measurements[position], value
                )
            elif update["update_kind"] == "MAX":
                self.measurements[position] = max(self.measurements[position], value)
            else:
                _reject("CASE_SEMANTIC_REJECT", "metric update kind differs")
        return raw


def _plan_identity_preimage(seed, plan):
    identity = next(
        (
            row
            for row in seed["ordered_identity_domain_records"]
            if row["identity_name"] == "LOGICAL_COUNT_PLAN"
        ),
        None,
    )
    if identity is None:
        _reject("INPUT_SCHEMA_INVALID", "logical-plan identity domain is absent")
    payload = {name: plan[name] for name in identity["ordered_payload_member_names"]}
    raw = _canonical_bytes(
        {
            "canonicalization_version": seed["canonicalization_version"],
            "domain": identity["domain_literal"],
            "payload": payload,
            "schema_version": seed["measurement_schema_version"],
        }
    )
    if _sha256(raw) != plan["logical_count_plan_id"]:
        _reject("CASE_SEMANTIC_REJECT", "logical-plan identity does not reproduce")
    return raw


def _base_context(events):
    plan = events.plan
    recurrence = events.recurrence
    return {
        "PLAN.case_position": plan["case_position"],
        "PLAN.case_kind": plan["case_kind"],
        "PLAN.logical_count_plan_id": plan["logical_count_plan_id"],
        "PLAN.local_analytic_catalog_id": plan["local_analytic_catalog_id"],
        "PLAN.scope_summary.schedule_authority_id": plan["scope_summary"][
            "schedule_authority_id"
        ],
        "PLAN.scope_summary.cross_rule_evaluation_count": plan["scope_summary"][
            "cross_rule_evaluation_count"
        ],
        "PLAN.scope_summary.application_invocation_count": plan["scope_summary"][
            "application_invocation_count"
        ],
        "RECURRENCE.cache_key_schema.cache_key_version": recurrence["cache_key_schema"][
            "cache_key_version"
        ],
        "RECURRENCE.transition_token_schema.transition_token_version": recurrence[
            "transition_token_schema"
        ]["transition_token_version"],
        "RECURRENCE.result_cell_schema.result_cell_version": recurrence[
            "result_cell_schema"
        ]["result_cell_version"],
        "RECURRENCE.step_commitment_schema.step_commitment_version": recurrence[
            "step_commitment_schema"
        ]["step_commitment_version"],
    }


def _live_entries(raw_pairs, commitment_digests):
    entries = []
    for pair in sorted(raw_pairs, key=lambda item: item["key_raw"]):
        entries.extend(
            [
                {
                    "entry_kind": "RECURRENCE_CACHE_KEY_V2",
                    "entry_id": pair["key_sha256"],
                    "canonical_octets": len(pair["key_raw"]),
                },
                {
                    "entry_kind": "RECURRENCE_RESULT_CELL_V2",
                    "entry_id": pair["cell_sha256"],
                    "canonical_octets": len(pair["cell_raw"]),
                },
            ]
        )
    entries.extend(
        {
            "entry_kind": "STEP_COMMITMENT_DIGEST_V1",
            "entry_id": digest,
            "canonical_octets": 32,
        }
        for digest in commitment_digests
    )
    return entries


def _retention_subject(events, entries):
    observed = _checked_add(*(row["canonical_octets"] for row in entries))
    context = {
        "CONTIGUOUS_ONE_BASED_RETENTION_OBSERVATION_ORDINAL": events.event_ordinals.get(
            "RETENTION_OBSERVATION", 0
        )
        + 1,
        "RETENTION.observation_label": None,
        "RETENTION.ordered_live_entry_records": entries,
        "SUM:RETENTION.ordered_live_entry_records.canonical_octets": observed,
    }
    return context, observed


def _ordinary_case_units(events, template, cells, owner_profile_position):
    base = _base_context(events)
    plan = events.plan
    recurrence = events.recurrence
    ceiling = recurrence["arithmetic_policy"]["published_maximum"]
    steps = template["ordered_template_steps"]
    last_parent = {position: position for position in range(1, len(steps) + 1)}
    for parent in steps:
        for child in parent["ordered_child_step_positions"]:
            last_parent[child] = max(
                last_parent[child], parent["template_step_position"]
            )
    active_pairs = {}
    commitment_digests = []
    commitment_records = []
    root_pair = None
    depths = []
    iterations = []
    intrinsic_rule_ids = []
    for position, (step, cell) in enumerate(zip(steps, cells), 1):
        child_depths = [
            depths[child - 1] for child in step["ordered_child_step_positions"]
        ]
        depths.append(1 if not child_depths else 1 + max(child_depths))
        kind = step["derivation_kind"]
        if kind == "ASSOCIATIVE_HOMOGENEOUS_RUN_BATCH":
            maximum_items = step["recurrence_parameters"]["maximum_items"]
            iteration = 0 if maximum_items <= 1 else (maximum_items - 1).bit_length()
        elif kind == "ARRAY_STREAM_FOLD":
            iteration = step["recurrence_parameters"]["maximum_items"]
        elif kind == "APPLICATION_SCHEDULE_COUNT":
            iteration = len(
                step["recurrence_parameters"]["ordered_application_invocation_records"]
            )
        else:
            iteration = step["physical_transition_count"]
        iterations.append(_u128(iteration, "ordinary iteration depth"))
        intrinsic_rule_ids.extend(step["ordered_intrinsic_rule_ids"])
        unit = {
            "UNIT.subject_variant": "ORDINARY_STEP",
            "UNIT.logical_derivation_step_position": position,
            "UNIT.logical_derivation_step_id": step["logical_derivation_step_id"],
            "UNIT.derivation_kind": kind,
            "UNIT.effective_canonical_octet_ceiling": ceiling,
            "UNIT.state_signature_id": step["state_signature_id"],
            "UNIT.owner_profile_position": owner_profile_position,
        }
        cell_context = {
            **base,
            **unit,
            "CELL.state_signature_id": step["state_signature_id"],
            "CELL.ordered_state_components": list(cell["state"]),
            "CELL.cell_status": cell["status"],
            "CELL.certified_lower_bound_octets": cell["lower"],
            "CELL.certified_upper_bound_octets": cell["upper"],
            "ORDINARY:STEP.template_step_position|LOCAL:null": position,
            "ORDINARY:CONST_U128_1|LOCAL:null": 1,
            "ORDINARY:null|LOCAL:CONTROLLER_STATE.controller_state_position": None,
            "ORDINARY:null|LOCAL:CONTROLLER_STATE.controller_state_id": None,
        }
        result_cell = events.construct("RESULT_CELL_EMIT", cell_context)
        result_raw = _canonical_bytes(result_cell)
        result_sha = _sha256(result_raw)
        key_context = {
            **base,
            **unit,
            "CELL.ordered_state_components": list(cell["state"]),
            "ORDINARY:STEP.template_step_position|LOCAL:null": position,
            "ORDINARY:STEP.derivation_kind|LOCAL:null": kind,
            "ORDINARY:CONST_U128_1|LOCAL:null": 1,
            "ORDINARY:null|LOCAL:CONTROLLER_STATE.controller_state_position": None,
            "ORDINARY:null|LOCAL:CONTROLLER_STATE.controller_state_id": None,
        }
        cache_key = events.construct("CACHE_INSERT", key_context)
        key_raw = _canonical_bytes(cache_key)
        pair = {
            "position": position,
            "key_raw": key_raw,
            "key_sha256": _sha256(key_raw),
            "cell_raw": result_raw,
            "cell_sha256": result_sha,
        }
        transition_subjects = []
        physical = _u128(step["physical_transition_count"], "physical transitions")
        logical = _u128(
            step["logical_unbatched_transition_equivalent_count"],
            "logical transition count",
        )
        if physical == 0 or logical < physical:
            _reject("CASE_SEMANTIC_REJECT", "ordinary transition run is not positive")
        quotient, remainder = divmod(logical, physical)
        for ordinal in range(1, physical + 1):
            transition_context = {
                **base,
                **unit,
                "TRANSITION.physical_transition_ordinal": ordinal,
                "ORDINARY:ORDINARY_KERNEL_TRANSITION|LOCAL:LOCAL_CONTROLLER_TRANSITION": (
                    "ORDINARY_KERNEL_TRANSITION"
                ),
                "TRANSITION.source_state_components": list(cell["state"]),
                "TRANSITION.input_symbol": {
                    "derivation_kind": kind,
                    "physical_transition_ordinal": ordinal,
                },
                "TRANSITION.candidate_state_components": list(cell["state"]),
                "TRANSITION.candidate_certified_upper_bound_octets": cell["upper"],
                "ORDINARY:STEP.template_step_position|LOCAL:null": position,
                "ORDINARY:null|LOCAL:CONTROLLER_TRANSITION.controller_transition_position": None,
                "ORDINARY:null|LOCAL:CONTROLLER_TRANSITION.controller_transition_id": None,
                "ORDINARY:null|LOCAL:CONTROLLER_TRANSITION.source_controller_state_id": None,
                "ORDINARY:null|LOCAL:CONTROLLER_TRANSITION.target_controller_state_id": None,
            }
            transition_subjects.append(
                (
                    events.construct("TRANSITION_ATTEMPT", transition_context),
                    quotient + int(ordinal <= remainder),
                )
            )
        if sum(row[1] for row in transition_subjects) != logical:
            _reject(
                "CASE_SEMANTIC_REJECT", "transition distribution does not reconcile"
            )
        batch_subjects = []
        for ordinal in range(1, step["physical_batch_application_count"] + 1):
            batch_subjects.append(
                events.construct(
                    "BATCH_APPLICATION",
                    {
                        **base,
                        "STEP.template_step_position": position,
                        "BATCH.physical_batch_ordinal": ordinal,
                        "STEP.derivation_kind": kind,
                        "STEP.logical_transfer_multiplicity": step[
                            "logical_transfer_multiplicity"
                        ],
                    },
                )
            )
        commitment_context = {
            **base,
            **unit,
            "UNIT.ordered_result_cells.LENGTH": 1,
            "MAXIMUM:UNIT.ordered_result_cells.certified_upper_bound_octets": cell[
                "upper"
            ],
            "UNIT.ordered_result_cells.CANONICAL_SHA256": [result_sha],
            "ORDINARY:STEP.template_step_position|LOCAL:null": position,
            "ORDINARY:null|LOCAL:PLAN.local_analytic_catalog_id": None,
            "ORDINARY:null|LOCAL:INITIAL_CONTROLLER_STATE.controller_state_id": None,
            "ORDINARY:null|LOCAL:TERMINAL_CONTROLLER_STATE.controller_state_id": None,
        }
        commitment = events.construct("STEP_COMMITMENT_EMIT", commitment_context)
        commitment_raw = _canonical_bytes(commitment)
        commitment_sha = _sha256(commitment_raw)
        commitment_records.append(
            {
                "derivation_unit_ordinal": position,
                "subject_variant": "ORDINARY_STEP",
                "logical_derivation_step_position": position,
                "local_controller_unit_ordinal": None,
                "step_commitment_sha256": commitment_sha,
            }
        )
        descriptor = events.construct("LOGICAL_DESCRIPTOR_VISIT", {**base, **unit})
        events.add(
            "ORDINARY_POSTORDER_STEPS",
            1,
            descriptor,
            {"aggregation_multiplicity": step["logical_descriptor_occurrence_count"]},
            ordinary_step_position=position,
        )
        for ordinal, (subject, logical_count) in enumerate(transition_subjects, 1):
            events.add(
                "ORDINARY_POSTORDER_STEPS",
                2,
                subject,
                {"logical_unbatched_equivalent_count": logical_count},
                collection_ordinal=ordinal,
                ordinary_step_position=position,
            )
        for ordinal, subject in enumerate(batch_subjects, 1):
            events.add(
                "ORDINARY_POSTORDER_STEPS",
                3,
                subject,
                collection_ordinal=ordinal,
                ordinary_step_position=position,
            )
        events.add(
            "ORDINARY_POSTORDER_STEPS",
            4,
            result_cell,
            collection_ordinal=1,
            ordinary_step_position=position,
        )
        events.add(
            "ORDINARY_POSTORDER_STEPS",
            5,
            cache_key,
            collection_ordinal=1,
            ordinary_step_position=position,
        )
        active_pairs[position] = pair
        entries = _live_entries(list(active_pairs.values()), commitment_digests)
        retention_context, _ = _retention_subject(events, entries)
        retention_context["RETENTION.observation_label"] = (
            "LIVE_CHILDREN_PLUS_PROSPECTIVE_PARENT"
        )
        retention = events.construct("RETENTION_OBSERVATION", retention_context)
        events.add(
            "ORDINARY_POSTORDER_STEPS",
            6,
            retention,
            ordinary_step_position=position,
        )
        events.add(
            "ORDINARY_POSTORDER_STEPS",
            7,
            events.construct(
                "HASH_PREIMAGE",
                {"ORDERED_CASE_HASH_PROGRAM_SELECTED_PREIMAGE_BYTES": result_raw},
            ),
            ordinary_step_position=position,
        )
        events.add(
            "ORDINARY_POSTORDER_STEPS",
            8,
            commitment,
            derivation_unit_ordinal=position,
            ordinary_step_position=position,
        )
        events.add(
            "ORDINARY_POSTORDER_STEPS",
            9,
            events.construct(
                "HASH_PREIMAGE",
                {"ORDERED_CASE_HASH_PROGRAM_SELECTED_PREIMAGE_BYTES": commitment_raw},
            ),
            ordinary_step_position=position,
        )
        commitment_digests.append(commitment_sha)
        for retained_position in list(active_pairs):
            if last_parent[retained_position] <= position:
                del active_pairs[retained_position]
        entries = _live_entries(list(active_pairs.values()), commitment_digests)
        retention_context, _ = _retention_subject(events, entries)
        retention_context["RETENTION.observation_label"] = (
            "AFTER_PARENT_COMMITMENT_HASH_AND_RELEASE"
        )
        retention = events.construct("RETENTION_OBSERVATION", retention_context)
        events.add(
            "ORDINARY_POSTORDER_STEPS",
            10,
            retention,
            ordinary_step_position=position,
        )
        if position == plan["root_step_position"]:
            root_pair = pair
    if root_pair is None or active_pairs:
        _reject("CASE_SEMANTIC_REJECT", "ordinary root/release program did not close")
    return {
        "commitment_digests": commitment_digests,
        "commitment_records": commitment_records,
        "root_pair": root_pair,
        "maximum_derivation_depth": max(depths),
        "maximum_iteration_depth": max(
            max(iterations), plan["scope_summary"]["application_invocation_count"]
        ),
        "intrinsic_rule_ids": intrinsic_rule_ids,
        "local": False,
    }


def _local_case_unit(events):
    base = _base_context(events)
    plan = events.plan
    recurrence = events.recurrence
    local = recurrence["local_shutdown_analytic_catalog"]
    ceiling = recurrence["arithmetic_policy"]["published_maximum"]
    states = local["ordered_controller_state_records"]
    transitions = local["ordered_controller_transition_records"]
    if len(states) != 12 or len(transitions) != 11:
        _reject("CASE_SEMANTIC_REJECT", "local controller cardinality differs")
    cells = []
    pairs = []
    for position, state in enumerate(states, 1):
        if state["controller_state_position"] != position:
            _reject("CASE_SEMANTIC_REJECT", "local state order differs")
        components = state["ordered_state_components"]
        upper = (
            local["baseline_attainable_maximum_octets"]
            if position == 1
            else components[7]
            if position == 12
            else components[3]
        )
        cell = _cell(MAY_BE_NONEMPTY, 0, _u128(upper, "local cell upper"), components)
        unit = {
            "UNIT.subject_variant": "LOCAL_CONTROLLER",
            "UNIT.logical_derivation_step_position": None,
            "UNIT.logical_derivation_step_id": plan["local_analytic_catalog_id"],
            "UNIT.derivation_kind": "LOCAL_SHUTDOWN_ANALYTIC_CONTROLLER",
            "UNIT.effective_canonical_octet_ceiling": ceiling,
            "UNIT.state_signature_id": local["state_signature_id"],
            "UNIT.owner_profile_position": None,
        }
        result = events.construct(
            "RESULT_CELL_EMIT",
            {
                **base,
                **unit,
                "CELL.state_signature_id": local["state_signature_id"],
                "CELL.ordered_state_components": components,
                "CELL.cell_status": cell["status"],
                "CELL.certified_lower_bound_octets": cell["lower"],
                "CELL.certified_upper_bound_octets": cell["upper"],
                "ORDINARY:STEP.template_step_position|LOCAL:null": None,
                "ORDINARY:CONST_U128_1|LOCAL:null": None,
                "ORDINARY:null|LOCAL:CONTROLLER_STATE.controller_state_position": position,
                "ORDINARY:null|LOCAL:CONTROLLER_STATE.controller_state_id": state[
                    "controller_state_id"
                ],
            },
        )
        result_raw = _canonical_bytes(result)
        key = events.construct(
            "CACHE_INSERT",
            {
                **base,
                **unit,
                "CELL.ordered_state_components": components,
                "ORDINARY:STEP.template_step_position|LOCAL:null": None,
                "ORDINARY:STEP.derivation_kind|LOCAL:null": None,
                "ORDINARY:CONST_U128_1|LOCAL:null": None,
                "ORDINARY:null|LOCAL:CONTROLLER_STATE.controller_state_position": position,
                "ORDINARY:null|LOCAL:CONTROLLER_STATE.controller_state_id": state[
                    "controller_state_id"
                ],
            },
        )
        key_raw = _canonical_bytes(key)
        cells.append((state, cell, result))
        pairs.append(
            {
                "position": position,
                "key": key,
                "key_raw": key_raw,
                "key_sha256": _sha256(key_raw),
                "cell": result,
                "cell_raw": result_raw,
                "cell_sha256": _sha256(result_raw),
            }
        )
    transition_subjects = []
    for position, transition in enumerate(transitions, 1):
        source_state = states[position - 1]
        target_state = states[position]
        if (
            transition["controller_transition_position"] != position
            or transition["source_controller_state_id"]
            != source_state["controller_state_id"]
            or transition["target_controller_state_id"]
            != target_state["controller_state_id"]
            or transition["expected_target_state_components"]
            != target_state["ordered_state_components"]
        ):
            _reject("CASE_SEMANTIC_REJECT", "local transition adjacency differs")
        transition_subjects.append(
            events.construct(
                "TRANSITION_ATTEMPT",
                {
                    **base,
                    "UNIT.subject_variant": "LOCAL_CONTROLLER",
                    "TRANSITION.physical_transition_ordinal": position,
                    "ORDINARY:ORDINARY_KERNEL_TRANSITION|LOCAL:LOCAL_CONTROLLER_TRANSITION": (
                        "LOCAL_CONTROLLER_TRANSITION"
                    ),
                    "TRANSITION.source_state_components": source_state[
                        "ordered_state_components"
                    ],
                    "TRANSITION.input_symbol": transition[
                        "input_mutable_limit_lexical_position"
                    ],
                    "TRANSITION.candidate_state_components": transition[
                        "expected_target_state_components"
                    ],
                    "TRANSITION.candidate_certified_upper_bound_octets": cells[
                        position
                    ][1]["upper"],
                    "ORDINARY:STEP.template_step_position|LOCAL:null": None,
                    "ORDINARY:null|LOCAL:CONTROLLER_TRANSITION.controller_transition_position": position,
                    "ORDINARY:null|LOCAL:CONTROLLER_TRANSITION.controller_transition_id": transition[
                        "controller_transition_id"
                    ],
                    "ORDINARY:null|LOCAL:CONTROLLER_TRANSITION.source_controller_state_id": transition[
                        "source_controller_state_id"
                    ],
                    "ORDINARY:null|LOCAL:CONTROLLER_TRANSITION.target_controller_state_id": transition[
                        "target_controller_state_id"
                    ],
                },
            )
        )
    intrinsic_ids = next(
        row["ordered_authority_values"]
        for row in local["controller_metric_count_program"][
            "ordered_exact_non_byte_metric_records"
        ]
        if row["metric_position"] == 12
    )
    unit = {
        "UNIT.subject_variant": "LOCAL_CONTROLLER",
        "UNIT.logical_derivation_step_position": None,
        "UNIT.logical_derivation_step_id": plan["local_analytic_catalog_id"],
        "UNIT.derivation_kind": "LOCAL_SHUTDOWN_ANALYTIC_CONTROLLER",
    }
    descriptor = events.construct("LOGICAL_DESCRIPTOR_VISIT", {**base, **unit})
    events.add(
        "LOCAL_CONTROLLER",
        1,
        descriptor,
        {"aggregation_multiplicity": len(transitions)},
    )
    for ordinal, subject in enumerate(transition_subjects, 1):
        events.add(
            "LOCAL_CONTROLLER",
            2,
            subject,
            {"logical_unbatched_equivalent_count": 1},
            collection_ordinal=ordinal,
        )
    intrinsic = events.construct(
        "INTRINSIC_RULE_EVALUATION",
        {
            **base,
            "ORDINARY:TEMPLATE_STEPS.ordered_intrinsic_rule_ids|LOCAL:LOCAL_METRIC_PROGRAM.metric_12.ordered_authority_values": intrinsic_ids,
            "ORDERED_INTRINSIC_RULE_IDS.LENGTH": len(intrinsic_ids),
        },
    )
    events.add(
        "LOCAL_CONTROLLER",
        3,
        intrinsic,
        {"aggregation_multiplicity": len(intrinsic_ids)},
    )
    for ordinal, pair in enumerate(pairs, 1):
        events.add(
            "LOCAL_CONTROLLER",
            4,
            pair["cell"],
            collection_ordinal=ordinal,
        )
    for ordinal, pair in enumerate(pairs, 1):
        events.add(
            "LOCAL_CONTROLLER",
            5,
            pair["key"],
            collection_ordinal=ordinal,
        )
    entries = _live_entries(pairs, [])
    retention_context, _ = _retention_subject(events, entries)
    retention_context["RETENTION.observation_label"] = (
        "LIVE_CHILDREN_PLUS_PROSPECTIVE_PARENT"
    )
    events.add(
        "LOCAL_CONTROLLER",
        6,
        events.construct("RETENTION_OBSERVATION", retention_context),
    )
    for pair in sorted(pairs, key=lambda item: item["key_raw"]):
        events.add(
            "LOCAL_CONTROLLER",
            7,
            events.construct(
                "HASH_PREIMAGE",
                {"ORDERED_CASE_HASH_PROGRAM_SELECTED_PREIMAGE_BYTES": pair["cell_raw"]},
            ),
        )
    initial = states[local["initial_controller_state_position"] - 1]
    terminal = states[local["terminal_controller_state_position"] - 1]
    commitment = events.construct(
        "STEP_COMMITMENT_EMIT",
        {
            **base,
            "UNIT.subject_variant": "LOCAL_CONTROLLER",
            "UNIT.ordered_result_cells.LENGTH": len(pairs),
            "MAXIMUM:UNIT.ordered_result_cells.certified_upper_bound_octets": max(
                cell[1]["upper"] for cell in cells
            ),
            "UNIT.ordered_result_cells.CANONICAL_SHA256": [
                pair["cell_sha256"] for pair in pairs
            ],
            "ORDINARY:STEP.template_step_position|LOCAL:null": None,
            "ORDINARY:null|LOCAL:PLAN.local_analytic_catalog_id": plan[
                "local_analytic_catalog_id"
            ],
            "ORDINARY:null|LOCAL:INITIAL_CONTROLLER_STATE.controller_state_id": initial[
                "controller_state_id"
            ],
            "ORDINARY:null|LOCAL:TERMINAL_CONTROLLER_STATE.controller_state_id": terminal[
                "controller_state_id"
            ],
        },
    )
    commitment_raw = _canonical_bytes(commitment)
    commitment_sha = _sha256(commitment_raw)
    events.add(
        "LOCAL_CONTROLLER",
        8,
        commitment,
        derivation_unit_ordinal=1,
    )
    events.add(
        "LOCAL_CONTROLLER",
        9,
        events.construct(
            "HASH_PREIMAGE",
            {"ORDERED_CASE_HASH_PROGRAM_SELECTED_PREIMAGE_BYTES": commitment_raw},
        ),
    )
    entries = _live_entries([], [commitment_sha])
    retention_context, _ = _retention_subject(events, entries)
    retention_context["RETENTION.observation_label"] = (
        "AFTER_PARENT_COMMITMENT_HASH_AND_RELEASE"
    )
    events.add(
        "LOCAL_CONTROLLER",
        10,
        events.construct("RETENTION_OBSERVATION", retention_context),
    )
    return {
        "commitment_digests": [commitment_sha],
        "commitment_records": [
            {
                "derivation_unit_ordinal": 1,
                "subject_variant": "LOCAL_CONTROLLER",
                "logical_derivation_step_position": None,
                "local_controller_unit_ordinal": 1,
                "step_commitment_sha256": commitment_sha,
            }
        ],
        "root_pair": pairs[-1],
        "maximum_derivation_depth": 1,
        "maximum_iteration_depth": len(transitions),
        "intrinsic_rule_ids": intrinsic_ids,
        "local": True,
    }


def _validate_profile_binding(plan, profile, template, seed):
    recipe = seed["logical_plan_recipe_catalog"]
    contract = recipe["profile_conditioned_cell_contract"]
    transfer = profile["conditioning_transfer_program"]
    if not (
        profile["case_position"] == plan["case_position"]
        and profile["profile_conditioning_program_id"]
        == plan["profile_conditioning_program_id"]
        and profile["logical_plan_template_id"] == plan["logical_plan_template_id"]
        and profile["template_root_step_position"]
        == plan["root_step_position"]
        == template["root_step_position"]
        and transfer["cell_contract_id"]
        == contract["profile_conditioned_cell_contract_id"]
    ):
        _reject("CASE_SEMANTIC_REJECT", "profile/plan binding differs")
    scope = plan["scope_summary"]
    schedule = profile["application_schedule_operation"]
    if not (
        schedule["application_invocation_count"]
        == scope["application_invocation_count"]
        and schedule["cross_rule_evaluation_count"]
        == scope["cross_rule_evaluation_count"]
        and schedule["direct_cross_expression_node_count"]
        == scope["direct_cross_expression_node_count"]
        and scope["schedule_authority_id"] == profile["profile_conditioning_program_id"]
    ):
        _reject("CASE_SEMANTIC_REJECT", "profile scope schedule differs")
    fixed = profile["ordered_fixed_authority_operations"]
    if any(
        row.get("operation_position") != position
        for position, row in enumerate(fixed, 1)
    ):
        _reject("CASE_SEMANTIC_REJECT", "profile fixed-authority order differs")
    p2 = transfer["p2_upper_bound_program"]
    p2_rows = p2["ordered_instruction_records"]
    for position, row in enumerate(p2_rows, 1):
        if row.get("instruction_position") != position or any(
            not _is_int(child) or not 1 <= child < position
            for child in row["ordered_input_instruction_positions"]
        ):
            _reject("CASE_SEMANTIC_REJECT", "profile P2 program is not postorder")
    strategy = profile["conditioning_strategy"]
    p2_opcodes = [row["opcode"] for row in p2_rows]
    if strategy == "STRUCTURAL_TEMPLATE_SUPERSET_WITH_EXACT_RETAINED_ATTAINMENT_V1":
        if not (
            p2_opcodes == ["LOAD_STRUCTURAL_TEMPLATE_SUPERSET_CELL_V1"]
            and p2["root_instruction_position"] == 1
            and p2["generic_attainability_claimed"] is False
            and p2_rows[0]["parameters"]
            == {
                "logical_plan_template_id": plan["logical_plan_template_id"],
                "template_root_step_position": plan["root_step_position"],
            }
        ):
            _reject("CASE_SEMANTIC_REJECT", "generic profile P2 program differs")
    elif strategy == "LOCAL_SHUTDOWN_BASELINE_ANALYTIC_EXACT_V1":
        if not (
            p2_opcodes
            == [
                "LOAD_STRUCTURAL_TEMPLATE_SUPERSET_CELL_V1",
                "LOAD_FIXED_AUTHORITY_SET_V1",
                "EXECUTE_LOCAL_SHUTDOWN_BASELINE_ANALYTIC_EXACT_V1",
                "INTERSECT_EXACT_ANALYTIC_WITH_STRUCTURAL_CELL_V1",
            ]
            and p2["root_instruction_position"] == 4
            and p2["generic_attainability_claimed"] is None
        ):
            _reject("CASE_SEMANTIC_REJECT", "exact profile P2 program differs")
    else:
        _reject("CASE_SEMANTIC_REJECT", "profile strategy differs")
    attainment = transfer["p1_p3_attainment_program"]
    attainment_rows = attainment["ordered_instruction_records"]
    expected_opcodes = [
        "IMPORT_P2_BOUND_CELL_V1",
        "LOAD_RETAINED_WITNESS_CONTEXT_V1",
        "LOAD_FIXED_AUTHORITY_SET_V1",
        "MATCH_EXACT_PROFILE_SCOPE_CASE_V1",
        "RECONSTRUCT_EXACT_APPLICATION_SCHEDULE_V1",
        "EXECUTE_PINNED_APPLICATION_RULE_AST_ON_RETAINED_BYTES_V1",
        "MEASURE_RETAINED_WITNESS_CANONICAL_OCTETS_V1",
        "REQUIRE_P1_AND_P3_EQUALITY_V1",
    ]
    if [row["opcode"] for row in attainment_rows] != expected_opcodes or attainment[
        "root_instruction_position"
    ] != 8:
        _reject("CASE_SEMANTIC_REJECT", "profile P1/P3 program differs")
    for position, row in enumerate(attainment_rows, 1):
        if row.get("instruction_position") != position or any(
            not _is_int(child) or not 1 <= child < position
            for child in row["ordered_input_instruction_positions"]
        ):
            _reject("CASE_SEMANTIC_REJECT", "profile P1/P3 program is not postorder")


def _event_stream_version(seed):
    record = next(
        (
            row
            for row in seed["ordered_identity_domain_records"]
            if row["identity_name"] == "LOGICAL_EVENT_STREAM"
        ),
        None,
    )
    if record is None:
        _reject("INPUT_SCHEMA_INVALID", "logical event-stream identity is absent")
    return record["version_literal"]


def _finalize_case(events, unit_result, metric_rows, seed):
    base = _base_context(events)
    plan = events.plan
    intrinsic_ids = unit_result["intrinsic_rule_ids"]
    if intrinsic_ids:
        intrinsic = events.construct(
            "INTRINSIC_RULE_EVALUATION",
            {
                **base,
                "ORDINARY:TEMPLATE_STEPS.ordered_intrinsic_rule_ids|LOCAL:LOCAL_METRIC_PROGRAM.metric_12.ordered_authority_values": intrinsic_ids,
                "ORDERED_INTRINSIC_RULE_IDS.LENGTH": len(intrinsic_ids),
            },
        )
        events.add(
            "EXACT_ATTAINER_VALIDATION",
            1,
            intrinsic,
            {"aggregation_multiplicity": len(intrinsic_ids)},
        )
    scope = plan["scope_summary"]
    application_count = _u128(
        scope["application_invocation_count"], "application count"
    )
    cross_count = _u128(scope["cross_rule_evaluation_count"], "cross-rule count")
    if application_count or cross_count:
        if not isinstance(scope["schedule_authority_id"], str):
            _reject("CASE_SEMANTIC_REJECT", "nonempty scope has no authority")
    if application_count:
        application = events.construct("APPLICATION_EVALUATION", base)
        events.add(
            "SCOPE_APPLICATIONS",
            1,
            application,
            {"aggregation_multiplicity": application_count},
            collection_ordinal=1,
        )
    if cross_count:
        cross = events.construct("CROSS_RULE_EVALUATION", base)
        events.add(
            "SCOPE_APPLICATIONS",
            2,
            cross,
            {"aggregation_multiplicity": cross_count},
            collection_ordinal=1,
        )
    maximum_depth = _u128(
        unit_result["maximum_derivation_depth"], "maximum derivation depth"
    )
    maximum_iteration = _u128(
        unit_result["maximum_iteration_depth"], "maximum iteration depth"
    )
    depth = events.construct(
        "DERIVATION_DEPTH_OBSERVATION",
        {**base, "DEPTH.maximum_derivation_depth": maximum_depth},
    )
    events.add("DEPTH_AND_RETENTION", 1, depth)
    iteration = events.construct(
        "ITERATION_DEPTH_OBSERVATION",
        {**base, "DEPTH.maximum_iteration_depth": maximum_iteration},
    )
    events.add("DEPTH_AND_RETENTION", 2, iteration)
    entries = _live_entries([], unit_result["commitment_digests"])
    retention_context, _ = _retention_subject(events, entries)
    retention_context["RETENTION.observation_label"] = (
        "ROOT_COMMITMENT_DIGEST_THROUGH_FINAL_RESULT_HASH"
    )
    retention = events.construct("RETENTION_OBSERVATION", retention_context)
    events.add("DEPTH_AND_RETENTION", 3, retention)
    root_pair = unit_result["root_pair"]
    final_result = events.construct(
        "FINAL_RESULT_EMIT",
        {
            **base,
            "ROOT_RESULT_CELLS.IN_CANONICAL_CELL_KEY_ORDER.DIGEST_RECORDS": [
                {
                    "result_cell_ordinal": 1,
                    "result_cell_sha256": root_pair["cell_sha256"],
                }
            ],
            "DERIVATION_UNITS.IN_POSTORDER.COMMITMENT_DIGEST_RECORDS": unit_result[
                "commitment_records"
            ],
        },
    )
    final_raw = events.add("FINAL_RESULT", 1, final_result)
    events.add(
        "FINAL_RESULT",
        2,
        events.construct(
            "HASH_PREIMAGE",
            {"ORDERED_CASE_HASH_PROGRAM_SELECTED_PREIMAGE_BYTES": final_raw},
        ),
    )
    preimage_members = events.grammar["stream_finalization_program"][
        "preimage_member_names"
    ]
    stream_payload = {
        "logical_event_stream_version": _event_stream_version(seed),
        "logical_count_plan_id": plan["logical_count_plan_id"],
        "ordered_pre_close_logical_event_tokens": list(events.tokens),
    }
    if list(stream_payload) != preimage_members:
        _reject("CASE_SEMANTIC_REJECT", "event-stream preimage order differs")
    stream_raw = _canonical_bytes(stream_payload)
    stream_sha = _sha256(stream_raw)
    close = events.construct(
        "EVENT_STREAM_CLOSE",
        {
            **base,
            "EVENT_STREAM_PREIMAGE.RAW_OCTET_COUNT": len(stream_raw),
            "EVENT_STREAM_PREIMAGE.SHA256": stream_sha,
        },
    )
    events.add("STREAM_FINALIZATION", 1, close)
    events.add(
        "STREAM_FINALIZATION",
        2,
        events.construct(
            "HASH_PREIMAGE",
            {"ORDERED_CASE_HASH_PROGRAM_SELECTED_PREIMAGE_BYTES": stream_raw},
        ),
    )
    if [row["event_position"] for row in events.tokens] != list(
        range(1, len(events.tokens) + 1)
    ):
        _reject("CASE_SEMANTIC_REJECT", "event positions are not contiguous")
    measurements = []
    for position, metric in enumerate(metric_rows, 1):
        if metric.get("metric_position") != position:
            _reject("INPUT_SCHEMA_INVALID", "resource metric order differs")
        measured = _u128(events.measurements[position], "resource measurement")
        if measured > metric["per_case_f0_ceiling"]:
            _reject(
                "RESOURCE_LIMIT_EXCEEDED",
                f"case {plan['case_position']} metric {position} exceeds F0",
            )
        measurements.append(
            {
                "metric_position": position,
                "metric_name": metric["metric_name"],
                "measured_value": measured,
            }
        )
    case_payload = {
        "case_position": plan["case_position"],
        "case_kind": plan["case_kind"],
        "case_binding": plan["case_binding"],
        "logical_count_plan_id": plan["logical_count_plan_id"],
        "result_status": "ACCEPT",
        "ordered_resource_measurements": measurements,
        "derivation_event_stream_sha256": stream_sha,
    }
    return {
        **case_payload,
        "case_result_record_id": _domain_id(CASE_RESULT_DOMAIN, case_payload),
    }


def _run_case(seed, plan, templates, template_cells, profiles, runtime, metrics):
    events = _CaseEvents(seed, plan)
    base = _base_context(events)
    case_open = events.construct("CASE_OPEN", base)
    events.add("CASE_OPEN", 1, case_open)
    plan_raw = _plan_identity_preimage(seed, plan)
    events.add(
        "BOUND_PLAN_HASH_PREIMAGE",
        1,
        events.construct(
            "HASH_PREIMAGE",
            {"ORDERED_CASE_HASH_PROGRAM_SELECTED_PREIMAGE_BYTES": plan_raw},
        ),
    )
    template_id = plan["logical_plan_template_id"]
    if template_id is None:
        local_id = plan["local_analytic_catalog_id"]
        if not (
            plan["case_position"] == 475
            and plan["logical_root_reference"]
            == {"root_kind": "LOCAL_SHUTDOWN_ANALYTIC_CATALOG", "root_id": local_id}
            and local_id in runtime["local_catalogs_by_id"]
        ):
            _reject("CASE_SEMANTIC_REJECT", "local plan binding differs")
        unit_result = _local_case_unit(events)
    else:
        template = templates.get(template_id)
        cells = template_cells.get(template_id)
        if template is None or cells is None:
            _reject("CASE_SEMANTIC_REJECT", "logical template is unresolved")
        if plan["root_step_position"] != template["root_step_position"]:
            _reject("CASE_SEMANTIC_REJECT", "plan/template root differs")
        profile_id = plan["profile_conditioning_program_id"]
        owner_profile_position = None
        if profile_id is None:
            if plan["logical_root_reference"] != {
                "root_kind": "LOGICAL_PLAN_TEMPLATE",
                "root_id": template_id,
            }:
                _reject("CASE_SEMANTIC_REJECT", "template-root binding differs")
            conditioned = cells
        else:
            profile = profiles.get(profile_id)
            if profile is None or plan["logical_root_reference"] != {
                "root_kind": "PROFILE_CONDITIONING_PROGRAM",
                "root_id": profile_id,
            }:
                _reject("CASE_SEMANTIC_REJECT", "profile-root binding differs")
            _validate_profile_binding(plan, profile, template, seed)
            conditioned = _condition_profile_root(plan, profile, cells, seed)
            owner_profile_position = profile["profile_position"]
        unit_result = _ordinary_case_units(
            events, template, conditioned, owner_profile_position
        )
    return _finalize_case(events, unit_result, metrics, seed)


def _metric_summaries(case_records, metric_rows):
    summaries = []
    for position, metric in enumerate(metric_rows, 1):
        values = [
            row["ordered_resource_measurements"][position - 1]["measured_value"]
            for row in case_records
        ]
        maximum = max(values)
        aggregation = metric["full_run_aggregation"]
        if aggregation == "SUM":
            full_value = _checked_add(*values)
        elif aggregation == "MAXIMUM":
            full_value = maximum
        else:
            _reject("INPUT_SCHEMA_INVALID", "metric aggregation differs")
        if full_value > metric["full_run_f0_ceiling"]:
            _reject("RESOURCE_LIMIT_EXCEEDED", f"full-run metric {position} exceeds F0")
        summaries.append(
            {
                "metric_position": position,
                "metric_name": metric["metric_name"],
                "full_run_aggregation": aggregation,
                "full_run_value": full_value,
                "maximum_case_value": maximum,
                "ordered_maximum_case_positions": [
                    case_position
                    for case_position, value in enumerate(values, 1)
                    if value == maximum
                ],
            }
        )
    return summaries


def _build_report(seed, seed_raw):
    runtime = _build_runtime(seed)
    recipe = seed["logical_plan_recipe_catalog"]
    template_rows = recipe["ordered_logical_plan_templates"]
    templates = {row["logical_plan_template_id"]: row for row in template_rows}
    if len(template_rows) != 66 or len(templates) != 66:
        _reject("INPUT_SCHEMA_INVALID", "logical template cardinality differs")
    template_cells = {
        template_id: _execute_template(template, seed, runtime)
        for template_id, template in templates.items()
    }
    profile_rows = recipe["ordered_profile_conditioning_program_records"]
    profiles = {row["profile_conditioning_program_id"]: row for row in profile_rows}
    if len(profile_rows) != 408 or len(profiles) != 408:
        _reject("INPUT_SCHEMA_INVALID", "profile program cardinality differs")
    plans = recipe["ordered_logical_count_plan_records"]
    bindings = seed["case_universe_catalog"]["ordered_case_bindings"]
    metrics = seed["resource_metric_catalog"]["ordered_metric_records"]
    if len(plans) != 475 or len(bindings) != 475 or len(metrics) != 18:
        _reject("INPUT_SCHEMA_INVALID", "report authority cardinality differs")
    case_records = []
    for position, (plan, binding) in enumerate(zip(plans, bindings), 1):
        if not (
            plan["case_position"] == position
            and binding["case_position"] == position
            and binding["case_kind"] == plan["case_kind"]
            and binding["case_binding"] == plan["case_binding"]
            and plan["recurrence_catalog_id"]
            == seed["recurrence_catalog"]["recurrence_catalog_id"]
        ):
            _reject("CASE_SEMANTIC_REJECT", "case-plan binding differs")
        case_records.append(
            _run_case(
                seed,
                plan,
                templates,
                template_cells,
                profiles,
                runtime,
                metrics,
            )
        )
    summaries = _metric_summaries(case_records, metrics)
    case_vector = [
        {name: value for name, value in row.items() if name != "case_result_record_id"}
        for row in case_records
    ]
    count_vector_sha = _domain_id(COUNT_VECTOR_DOMAIN, [*case_vector, *summaries])
    payload = {
        "preflight_semantic_payload_version": SEMANTIC_PAYLOAD_VERSION,
        "canonicalization_version": seed["canonicalization_version"],
        "measurement_schema_version": seed["measurement_schema_version"],
        "contract_id": CONTRACT_ID,
        "protocol_version": seed["protocol_version"],
        "protocol_counting_semantics_id": seed["protocol_counting_semantics_id"],
        "seed_catalog_raw_octets": len(seed_raw),
        "seed_catalog_raw_sha256": _sha256(seed_raw),
        "seed_catalog_id": seed["seed_catalog_id"],
        "case_universe_catalog_id": seed["case_universe_catalog"][
            "case_universe_catalog_id"
        ],
        "logical_plan_recipe_catalog_id": recipe["logical_plan_recipe_catalog_id"],
        "recurrence_catalog_id": seed["recurrence_catalog"]["recurrence_catalog_id"],
        "resource_metric_catalog_id": seed["resource_metric_catalog"][
            "resource_metric_catalog_id"
        ],
        "logical_event_catalog_id": seed["logical_event_catalog"][
            "logical_event_catalog_id"
        ],
        "f0_seed_ceiling_catalog_id": seed["f0_seed_ceiling_catalog"][
            "f0_seed_ceiling_catalog_id"
        ],
        "verifier_owned_scope_case_count": len(case_records),
        "ordered_case_result_records": case_records,
        "ordered_metric_summary_records": summaries,
        "semantic_count_vector_sha256": count_vector_sha,
    }
    return {
        **payload,
        "semantic_payload_id": _domain_id(SEMANTIC_PAYLOAD_DOMAIN, payload),
    }


def _output_path(argument):
    candidate = pathlib.Path(os.path.abspath(argument))
    parent = candidate.parent
    if candidate.name in {"", ".", ".."}:
        _reject("OUTPUT_ATOMICITY_INVALID", "semantic output name differs")
    if os.path.realpath(parent) != str(parent):
        _reject("OUTPUT_ATOMICITY_INVALID", "output parent contains a symlink")
    try:
        status = os.lstat(parent)
    except OSError as error:
        _reject("OUTPUT_ATOMICITY_INVALID", f"output parent stat failed: {error}")
    if (
        (status.st_mode & 0o170000) != 0o040000
        or status.st_uid != os.getuid()
        or status.st_mode & 0o077
    ):
        _reject("OUTPUT_ATOMICITY_INVALID", "output parent is not private")
    try:
        entries = os.listdir(parent)
    except OSError as error:
        _reject("OUTPUT_ATOMICITY_INVALID", f"output parent list failed: {error}")
    if entries:
        _reject("OUTPUT_ATOMICITY_INVALID", "output parent is not empty")
    return candidate


def _publish_atomic(path, raw):
    parent = path.parent
    temporary = parent / f".{path.name}.preflight-a.tmp"
    descriptor = None
    created = False
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(str(temporary), flags, 0o600)
        created = True
        offset = 0
        while offset < len(raw):
            written = os.write(descriptor, raw[offset:])
            if written <= 0:
                _reject("OUTPUT_ATOMICITY_INVALID", "output write made no progress")
            offset += written
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.link(temporary, path, follow_symlinks=False)
        os.unlink(temporary)
        created = False
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        directory = os.open(str(parent), directory_flags)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except Reject:
        raise
    except OSError as error:
        _reject("OUTPUT_ATOMICITY_INVALID", f"atomic publication failed: {error}")
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if created:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def _arguments(argv):
    if len(argv) != 4 or argv[0] != "--seed" or argv[2] != "--semantic-output":
        _reject("INVOCATION_INVALID", "expected --seed PATH --semantic-output PATH")
    return argv[1], argv[3]


def _main(argv):
    seed_argument, output_argument = _arguments(argv)
    output = _output_path(output_argument)
    seed_raw = _read_seed(seed_argument)
    seed = _parse_json(seed_raw)
    _validate_seed(seed, seed_raw)
    report = _build_report(seed, seed_raw)
    _publish_atomic(output, _pretty_bytes(report))


def _entrypoint():
    try:
        _main(sys.argv[1:])
    except Reject as error:
        line = f"{ERROR_PREFIX}_{error.code}: {error.message}\n".encode(
            "utf-8", "replace"
        )
        try:
            os.write(2, line)
        except OSError:
            pass
        return EXIT_CODES.get(error.code, EXIT_CODES["INTERNAL_FAIL_CLOSED"])
    except Exception as error:
        line = f"{ERROR_PREFIX}_INTERNAL_FAIL_CLOSED: {type(error).__name__}\n".encode(
            "ascii", "replace"
        )
        try:
            os.write(2, line)
        except OSError:
            pass
        return EXIT_CODES["INTERNAL_FAIL_CLOSED"]
    return 0


if __name__ == "__main__":
    raise SystemExit(_entrypoint())
