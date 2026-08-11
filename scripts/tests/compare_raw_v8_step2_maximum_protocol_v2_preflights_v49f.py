#!/usr/bin/env python3
"""Parent-owned isolated comparator for the two S1-A2 counting preflights."""

import ast
import hashlib
import json
import os
import pathlib
import resource
import signal
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONTRACT_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_preflight_contract_v49f.json"
)
CONTRACT_OCTETS = 16919
CONTRACT_SHA256 = "007ed9a8d06b91f73708129b66a33eaf525e203d306426d05b8cd8bba9c7294b"
CONTRACT_ID = "6609ad7b9abf21432136e49af178e20c17cb7bc27d3b444a4b6f01a17073fc76"
CONTRACT_DOMAIN = "RiskYieldMMStep2PreflightExecutionContractV1V4_9F_RawV8"
COMPARISON_DOMAIN = "RiskYieldMMStep2PreflightComparisonV1V4_9F_RawV8"
CASE_RESULT_DOMAIN = "RiskYieldMMStep2PreflightCaseResultV1V4_9F_RawV8"
COUNT_VECTOR_DOMAIN = "RiskYieldMMStep2PreflightCountVectorV1V4_9F_RawV8"
SEMANTIC_PAYLOAD_DOMAIN = "RiskYieldMMStep2PreflightSemanticPayloadV1V4_9F_RawV8"
ERROR_PREFIX = "RAW_V8_STEP2_MAXIMUM_PROTOCOL_V2_PREFLIGHT_COMPARATOR"
U128_MAX = (1 << 128) - 1

EXIT_CODES = {
    "INVOCATION_INVALID": 2,
    "OUTPUT_ATOMICITY_INVALID": 8,
    "INTERNAL_FAIL_CLOSED": 9,
    "COMPARATOR_REPORT_INVALID": 20,
    "COMPARATOR_IMPLEMENTATION_NOT_SEPARATE": 21,
    "COMPARATOR_RESULT_MISMATCH": 22,
    "COMPARATOR_RESOURCE_EVIDENCE_INVALID": 23,
}


class Reject(Exception):
    """Stable fail-closed comparator rejection."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = " ".join(str(message).split())[:768]


def _reject(code, message):
    raise Reject(code, message)


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _sha256(raw):
    return hashlib.sha256(raw).hexdigest()


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
        _reject("COMPARATOR_REPORT_INVALID", f"canonical JSON rejected: {error}")


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
        _reject("COMPARATOR_REPORT_INVALID", f"pretty JSON rejected: {error}")


def _domain_id(domain, payload):
    return _sha256(_canonical_bytes({"domain": domain, "payload": payload}))


def _duplicate_closed_object(pairs):
    value = {}
    for key, child in pairs:
        if key in value:
            _reject("COMPARATOR_REPORT_INVALID", f"duplicate JSON key: {key}")
        value[key] = child
    return value


def _reject_float(_value):
    _reject("COMPARATOR_REPORT_INVALID", "floating-point JSON is forbidden")


def _reject_constant(_value):
    _reject("COMPARATOR_REPORT_INVALID", "non-finite JSON is forbidden")


def _parse_integer(text):
    if len(text.lstrip("-")) > 39:
        _reject("COMPARATOR_REPORT_INVALID", "JSON integer exceeds UInt128 width")
    return int(text)


def _parse_json(raw):
    try:
        text = raw.decode("utf-8")
        return json.loads(
            text,
            object_pairs_hook=_duplicate_closed_object,
            parse_float=_reject_float,
            parse_int=_parse_integer,
            parse_constant=_reject_constant,
        )
    except Reject:
        raise
    except (UnicodeError, json.JSONDecodeError, ValueError) as error:
        _reject("COMPARATOR_REPORT_INVALID", f"strict JSON rejected: {error}")


def _closed_object(value, names, label):
    if not isinstance(value, dict) or set(value) != set(names):
        _reject("COMPARATOR_REPORT_INVALID", f"{label} has wrong members")


def _hex_digest(value, label):
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        _reject("COMPARATOR_REPORT_INVALID", f"{label} is not a SHA-256 digest")


def _secure_read(path, maximum_octets, expected_octets=None, expected_sha256=None):
    path = pathlib.Path(path)
    if not path.is_absolute() or os.path.realpath(path) != str(path):
        _reject("COMPARATOR_REPORT_INVALID", f"noncanonical or symlinked path: {path}")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = None
    try:
        descriptor = os.open(path, flags)
        before = os.fstat(descriptor)
        if before.st_mode & 0o170000 != 0o100000:
            _reject("COMPARATOR_REPORT_INVALID", f"not a regular file: {path}")
        if before.st_size < 0 or before.st_size > maximum_octets:
            _reject("COMPARATOR_REPORT_INVALID", f"file size exceeds limit: {path}")
        if expected_octets is not None and before.st_size != expected_octets:
            _reject("COMPARATOR_REPORT_INVALID", f"file length differs: {path}")
        chunks = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(1 << 20, maximum_octets + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > maximum_octets:
                _reject("COMPARATOR_REPORT_INVALID", f"file read exceeds limit: {path}")
        after = os.fstat(descriptor)
        stable_before = (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        stable_after = (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if stable_before != stable_after or total != before.st_size:
            _reject("COMPARATOR_REPORT_INVALID", f"file changed during read: {path}")
        raw = b"".join(chunks)
        if expected_octets is not None and len(raw) != expected_octets:
            _reject("COMPARATOR_REPORT_INVALID", f"file length differs: {path}")
        if expected_sha256 is not None and _sha256(raw) != expected_sha256:
            _reject("COMPARATOR_REPORT_INVALID", f"file hash differs: {path}")
        return raw, before
    except Reject:
        raise
    except OSError as error:
        _reject("COMPARATOR_REPORT_INVALID", f"secure read failed for {path}: {error}")
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass


def _authorized_argument(argument, relative_path, code="COMPARATOR_REPORT_INVALID"):
    expected = ROOT / relative_path
    candidate = pathlib.Path(os.path.abspath(argument))
    if os.path.realpath(candidate) != str(candidate) or candidate != expected:
        _reject(code, f"argument does not resolve to {relative_path}")
    return expected


def _json_shape(value, limits):
    maximum_depth = limits["JSON_NESTING_DEPTH"]
    maximum_nodes = limits["DECODED_JSON_NODE_COUNT"]
    maximum_arrays = limits["DECODED_JSON_ARRAY_ENTRY_COUNT"]
    maximum_members = limits["DECODED_JSON_OBJECT_MEMBER_COUNT"]
    nodes = 0
    array_entries = 0
    object_members = 0
    stack = [(value, 1)]
    while stack:
        child, depth = stack.pop()
        nodes += 1
        if nodes > maximum_nodes or depth > maximum_depth:
            _reject("COMPARATOR_REPORT_INVALID", "JSON shape exceeds frozen limits")
        if isinstance(child, dict):
            object_members += len(child)
            if object_members > maximum_members:
                _reject("COMPARATOR_REPORT_INVALID", "JSON object members exceed limit")
            stack.extend((item, depth + 1) for item in child.values())
        elif isinstance(child, list):
            array_entries += len(child)
            if array_entries > maximum_arrays:
                _reject("COMPARATOR_REPORT_INVALID", "JSON array entries exceed limit")
            stack.extend((item, depth + 1) for item in child)


def _limit_map(contract):
    rows = contract["resource_enforcement_contract"]["ordered_f0_limit_records"]
    return {row["resource_name"]: row["expected_value"] for row in rows}


def _load_contract(argument):
    path = _authorized_argument(argument, CONTRACT_RELATIVE_PATH)
    raw, _status = _secure_read(
        path,
        CONTRACT_OCTETS,
        expected_octets=CONTRACT_OCTETS,
        expected_sha256=CONTRACT_SHA256,
    )
    contract = _parse_json(raw)
    if raw != _pretty_bytes(contract):
        _reject("COMPARATOR_REPORT_INVALID", "contract is not canonical-pretty JSON")
    expected_top = {
        "contract_id",
        "contract_version",
        "error_taxonomy",
        "implementation_separation_policy",
        "input_authority",
        "report_contract",
        "resource_enforcement_contract",
        "unknown_or_extra_member_policy",
    }
    if not isinstance(contract, dict) or set(contract) != expected_top:
        _reject("COMPARATOR_REPORT_INVALID", "contract root is not closed")
    identity_payload = {
        name: value for name, value in contract.items() if name != "contract_id"
    }
    if contract["contract_id"] != CONTRACT_ID or contract["contract_id"] != _domain_id(
        CONTRACT_DOMAIN, identity_payload
    ):
        _reject("COMPARATOR_REPORT_INVALID", "contract identity differs")
    if contract["unknown_or_extra_member_policy"] != "REJECT":
        _reject("COMPARATOR_REPORT_INVALID", "contract is not fail closed")
    return contract, raw


def _source_import_roots(tree):
    roots = set()
    calls = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level != 0 or node.module is None:
                _reject(
                    "COMPARATOR_IMPLEMENTATION_NOT_SEPARATE",
                    "relative source import is forbidden",
                )
            roots.add(node.module.split(".", 1)[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)
    return roots, calls


def _validate_source(source, contract, label, comparator=False):
    try:
        text = source["raw"].decode("utf-8")
        tree = ast.parse(text, filename=source["relative_path"])
    except (UnicodeError, SyntaxError) as error:
        _reject(
            "COMPARATOR_IMPLEMENTATION_NOT_SEPARATE", f"source parse failed: {error}"
        )
    policy = contract["implementation_separation_policy"]
    allowed_name = (
        "allowed_comparator_standard_library_import_roots"
        if comparator
        else "allowed_preflight_standard_library_import_roots"
    )
    allowed = set(policy[allowed_name])
    forbidden = set(policy["forbidden_import_roots"])
    roots, calls = _source_import_roots(tree)
    if not roots <= allowed or roots & forbidden:
        _reject(
            "COMPARATOR_IMPLEMENTATION_NOT_SEPARATE",
            f"{label} imports a forbidden or unknown root",
        )
    if calls & set(policy["forbidden_ast_call_names"]):
        _reject(
            "COMPARATOR_IMPLEMENTATION_NOT_SEPARATE",
            f"{label} uses dynamic execution",
        )
    if comparator:
        return
    marker = policy["algorithm_markers"][label]
    if text.count(marker) != 1:
        _reject(
            "COMPARATOR_IMPLEMENTATION_NOT_SEPARATE",
            f"{label} algorithm marker is absent or duplicated",
        )
    seed_path = contract["input_authority"]["sole_authorized_repository_relative_path"]
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        literal = node.value
        if (
            ("/" in literal or "\\" in literal)
            and (".json" in literal or ".py" in literal)
            and literal != seed_path
        ):
            _reject(
                "COMPARATOR_IMPLEMENTATION_NOT_SEPARATE",
                f"{label} contains another repository source path",
            )


def _validate_source_separation(sources, contract):
    source_a = sources["A"]
    source_b = sources["B"]
    if (source_a["device"], source_a["inode"]) == (
        source_b["device"],
        source_b["inode"],
    ) or source_a["raw_sha256"] == source_b["raw_sha256"]:
        _reject(
            "COMPARATOR_IMPLEMENTATION_NOT_SEPARATE",
            "A and B are not distinct source files",
        )
    policy = contract["implementation_separation_policy"]
    for label in ("A", "B"):
        if (
            sources[label]["relative_path"]
            != policy[f"implementation_{label.lower()}_repository_relative_path"]
        ):
            _reject(
                "COMPARATOR_IMPLEMENTATION_NOT_SEPARATE",
                f"{label} source path differs",
            )
        _validate_source(sources[label], contract, label)


def _verify_source_unchanged(source, contract):
    maximum = _limit_map(contract)["INDIVIDUAL_FILE_STRICT_UPPER_OCTETS"] - 1
    raw, status = _secure_read(source["path"], maximum)
    if (
        status.st_dev != source["device"]
        or status.st_ino != source["inode"]
        or len(raw) != source["raw_octets"]
        or _sha256(raw) != source["raw_sha256"]
    ):
        _reject(
            "COMPARATOR_IMPLEMENTATION_NOT_SEPARATE",
            "implementation source changed around child execution",
        )


def _validate_seed(seed, seed_raw, contract):
    authority = contract["input_authority"]
    if seed_raw != _pretty_bytes(seed):
        _reject("COMPARATOR_REPORT_INVALID", "seed is not canonical-pretty JSON")
    if not isinstance(seed, dict):
        _reject("COMPARATOR_REPORT_INVALID", "seed root is not an object")
    required = {
        "catalog_version": authority["accepted_catalog_version"],
        "seed_catalog_id": authority["accepted_catalog_id"],
        "protocol_counting_semantics_id": authority[
            "accepted_protocol_counting_semantics_id"
        ],
        "canonicalization_version": authority["canonicalization_version"],
        "measurement_schema_version": authority["measurement_schema_version"],
    }
    for name, expected in required.items():
        if seed.get(name) != expected:
            _reject("COMPARATOR_REPORT_INVALID", f"seed {name} differs")
    for row in authority["ordered_required_semantic_root_records"]:
        root_name = row["root_name"]
        id_name = f"{root_name}_id"
        if (
            not isinstance(seed.get(root_name), dict)
            or seed[root_name].get(id_name) != row["expected_id"]
        ):
            _reject("COMPARATOR_REPORT_INVALID", f"seed {root_name} identity differs")
    cases = seed["case_universe_catalog"]["ordered_case_bindings"]
    plans = seed["logical_plan_recipe_catalog"]["ordered_case_plan_bindings"]
    metrics = seed["resource_metric_catalog"]["ordered_metric_records"]
    if (
        len(cases) != authority["expected_verifier_owned_case_count"]
        or [row.get("case_position") for row in cases] != list(range(1, 476))
        or [row.get("case_position") for row in plans] != list(range(1, 476))
        or [row.get("metric_position") for row in metrics] != list(range(1, 19))
    ):
        _reject("COMPARATOR_REPORT_INVALID", "seed case, plan, or metric order differs")
    contract_limits = contract["resource_enforcement_contract"][
        "ordered_f0_limit_records"
    ]
    seed_limits = seed["f0_seed_ceiling_catalog"]["ordered_platform_ceiling_records"]
    if len(contract_limits) != len(seed_limits) or len(seed_limits) != 12:
        _reject("COMPARATOR_REPORT_INVALID", "F0 limit record count differs")
    for contract_row, seed_row in zip(contract_limits, seed_limits, strict=True):
        if (
            contract_row["resource_name"] != seed_row["resource_name"]
            or contract_row["expected_value"] != seed_row["ceiling_value"]
        ):
            _reject("COMPARATOR_REPORT_INVALID", "contract and seed F0 limits differ")
    _json_shape(seed, _limit_map(contract))


def _load_authorities(contract):
    limits = _limit_map(contract)
    file_limit = limits["INDIVIDUAL_FILE_STRICT_UPPER_OCTETS"]
    authority = contract["input_authority"]
    seed_path = ROOT / authority["sole_authorized_repository_relative_path"]
    seed_raw, _seed_status = _secure_read(
        seed_path,
        file_limit - 1,
        expected_octets=authority["accepted_catalog_raw_octets"],
        expected_sha256=authority["accepted_catalog_raw_sha256"],
    )
    seed = _parse_json(seed_raw)
    _validate_seed(seed, seed_raw, contract)
    policy = contract["implementation_separation_policy"]
    sources = {}
    for label in ("A", "B"):
        relative = policy[f"implementation_{label.lower()}_repository_relative_path"]
        raw, status = _secure_read(ROOT / relative, file_limit - 1)
        sources[label] = {
            "device": status.st_dev,
            "inode": status.st_ino,
            "path": ROOT / relative,
            "raw": raw,
            "raw_octets": len(raw),
            "raw_sha256": _sha256(raw),
            "relative_path": relative,
        }
    self_relative = policy["comparator_repository_relative_path"]
    self_raw, self_status = _secure_read(ROOT / self_relative, file_limit - 1)
    self_source = {
        "device": self_status.st_dev,
        "inode": self_status.st_ino,
        "path": ROOT / self_relative,
        "raw": self_raw,
        "raw_octets": len(self_raw),
        "raw_sha256": _sha256(self_raw),
        "relative_path": self_relative,
    }
    _validate_source(self_source, contract, "COMPARATOR", comparator=True)
    _validate_source_separation(sources, contract)
    total_input = (
        len(seed_raw)
        + CONTRACT_OCTETS
        + sum(source["raw_octets"] for source in sources.values())
    )
    if total_input > limits["TOTAL_PINNED_INPUT_OCTETS"]:
        _reject("COMPARATOR_RESOURCE_EVIDENCE_INVALID", "pinned input exceeds F0")
    return seed, seed_raw, sources


def _validate_semantic_payload(raw, contract, seed):
    limits = _limit_map(contract)
    if len(raw) >= limits["INDIVIDUAL_FILE_STRICT_UPPER_OCTETS"]:
        _reject("COMPARATOR_REPORT_INVALID", "semantic payload exceeds strict file cap")
    payload = _parse_json(raw)
    if raw != _pretty_bytes(payload):
        _reject(
            "COMPARATOR_REPORT_INVALID",
            "semantic payload is not canonical-pretty JSON",
        )
    _json_shape(payload, limits)
    report = contract["report_contract"]
    semantic_names = report["preflight_semantic_payload_schema"]["ordered_member_names"]
    _closed_object(payload, semantic_names, "semantic payload")
    authority = contract["input_authority"]
    versions = report["version_literals"]
    expected_scalars = {
        "preflight_semantic_payload_version": versions[
            "preflight_semantic_payload_version"
        ],
        "canonicalization_version": authority["canonicalization_version"],
        "measurement_schema_version": authority["measurement_schema_version"],
        "contract_id": contract["contract_id"],
        "protocol_version": seed["protocol_version"],
        "protocol_counting_semantics_id": authority[
            "accepted_protocol_counting_semantics_id"
        ],
        "seed_catalog_raw_octets": authority["accepted_catalog_raw_octets"],
        "seed_catalog_raw_sha256": authority["accepted_catalog_raw_sha256"],
        "seed_catalog_id": authority["accepted_catalog_id"],
        "verifier_owned_scope_case_count": authority[
            "expected_verifier_owned_case_count"
        ],
    }
    root_id_members = {
        "case_universe_catalog": "case_universe_catalog_id",
        "logical_plan_recipe_catalog": "logical_plan_recipe_catalog_id",
        "recurrence_catalog": "recurrence_catalog_id",
        "resource_metric_catalog": "resource_metric_catalog_id",
        "logical_event_catalog": "logical_event_catalog_id",
        "f0_seed_ceiling_catalog": "f0_seed_ceiling_catalog_id",
    }
    for row in authority["ordered_required_semantic_root_records"]:
        expected_scalars[root_id_members[row["root_name"]]] = row["expected_id"]
    for name, expected in expected_scalars.items():
        if payload[name] != expected:
            _reject("COMPARATOR_REPORT_INVALID", f"semantic {name} differs")
    case_rows = payload["ordered_case_result_records"]
    summary_rows = payload["ordered_metric_summary_records"]
    if not isinstance(case_rows, list) or len(case_rows) != 475:
        _reject("COMPARATOR_REPORT_INVALID", "semantic case count differs")
    if not isinstance(summary_rows, list) or len(summary_rows) != 18:
        _reject("COMPARATOR_REPORT_INVALID", "semantic summary count differs")
    seed_cases = seed["case_universe_catalog"]["ordered_case_bindings"]
    seed_plans = seed["logical_plan_recipe_catalog"]["ordered_case_plan_bindings"]
    metrics = seed["resource_metric_catalog"]["ordered_metric_records"]
    columns = [[] for _metric in metrics]
    case_names = report["case_result_record_schema"]["ordered_member_names"]
    measurement_names = report["resource_measurement_record_schema"][
        "ordered_member_names"
    ]
    for position, (row, seed_case, seed_plan) in enumerate(
        zip(case_rows, seed_cases, seed_plans, strict=True), 1
    ):
        _closed_object(row, case_names, f"case {position}")
        if (
            row["case_position"] != position
            or row["case_kind"] != seed_case["case_kind"]
            or row["case_binding"] != seed_case["case_binding"]
            or row["logical_count_plan_id"] != seed_plan["logical_count_plan_id"]
            or row["result_status"]
            != report["case_result_record_schema"]["expected_result_status"]
        ):
            _reject("COMPARATOR_REPORT_INVALID", f"case {position} binding differs")
        measurements = row["ordered_resource_measurements"]
        if not isinstance(measurements, list) or len(measurements) != 18:
            _reject("COMPARATOR_REPORT_INVALID", f"case {position} metrics differ")
        for metric_index, (measurement, metric) in enumerate(
            zip(measurements, metrics, strict=True)
        ):
            _closed_object(
                measurement,
                measurement_names,
                f"case {position} measurement {metric_index + 1}",
            )
            value = measurement["measured_value"]
            if (
                measurement["metric_position"] != metric["metric_position"]
                or measurement["metric_name"] != metric["metric_name"]
                or not _is_int(value)
                or not 0 <= value <= U128_MAX
                or value > metric["per_case_f0_ceiling"]
            ):
                _reject(
                    "COMPARATOR_REPORT_INVALID",
                    f"case {position} measurement {metric_index + 1} differs",
                )
            columns[metric_index].append(value)
        _hex_digest(row["derivation_event_stream_sha256"], "event stream digest")
        case_payload = {
            name: value
            for name, value in row.items()
            if name != "case_result_record_id"
        }
        if row["case_result_record_id"] != _domain_id(CASE_RESULT_DOMAIN, case_payload):
            _reject("COMPARATOR_REPORT_INVALID", f"case {position} identity differs")
    summary_names = report["metric_summary_record_schema"]["ordered_member_names"]
    for metric_index, (summary, metric, values) in enumerate(
        zip(summary_rows, metrics, columns, strict=True), 1
    ):
        _closed_object(summary, summary_names, f"metric summary {metric_index}")
        maximum = max(values)
        full_value = sum(values) if metric["full_run_aggregation"] == "SUM" else maximum
        maximum_positions = [
            position for position, value in enumerate(values, 1) if value == maximum
        ]
        if full_value > U128_MAX or full_value > metric["full_run_f0_ceiling"]:
            _reject("COMPARATOR_REPORT_INVALID", f"metric {metric_index} exceeds F0")
        expected_summary = {
            "metric_position": metric["metric_position"],
            "metric_name": metric["metric_name"],
            "full_run_aggregation": metric["full_run_aggregation"],
            "full_run_value": full_value,
            "maximum_case_value": maximum,
            "ordered_maximum_case_positions": maximum_positions,
        }
        if summary != expected_summary:
            _reject(
                "COMPARATOR_REPORT_INVALID",
                f"metric summary {metric_index} differs",
            )
    case_vector = [
        {name: value for name, value in row.items() if name != "case_result_record_id"}
        for row in case_rows
    ]
    count_vector = _domain_id(COUNT_VECTOR_DOMAIN, [*case_vector, *summary_rows])
    if payload["semantic_count_vector_sha256"] != count_vector:
        _reject("COMPARATOR_REPORT_INVALID", "semantic count-vector identity differs")
    semantic_identity_payload = {
        name: value for name, value in payload.items() if name != "semantic_payload_id"
    }
    if payload["semantic_payload_id"] != _domain_id(
        SEMANTIC_PAYLOAD_DOMAIN, semantic_identity_payload
    ):
        _reject("COMPARATOR_REPORT_INVALID", "semantic payload identity differs")
    return payload


def _allocated_octets(path):
    total = 0
    stack = [pathlib.Path(path)]
    while stack:
        current = stack.pop()
        try:
            status = os.lstat(current)
        except FileNotFoundError:
            continue
        except OSError as error:
            _reject(
                "COMPARATOR_RESOURCE_EVIDENCE_INVALID",
                f"storage observation failed: {error}",
            )
        total += status.st_blocks * 512
        kind = status.st_mode & 0o170000
        if kind == 0o120000:
            _reject(
                "COMPARATOR_RESOURCE_EVIDENCE_INVALID",
                "symlink appeared in private output directory",
            )
        if kind == 0o040000:
            try:
                with os.scandir(current) as entries:
                    stack.extend(pathlib.Path(entry.path) for entry in entries)
            except OSError as error:
                _reject(
                    "COMPARATOR_RESOURCE_EVIDENCE_INVALID",
                    f"storage scan failed: {error}",
                )
    return total


def _set_child_limits(limits):
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    cpu = limits["F1_CPU_SECONDS"]
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
    file_size = limits["INDIVIDUAL_FILE_STRICT_UPPER_OCTETS"] - 1
    resource.setrlimit(resource.RLIMIT_FSIZE, (file_size, file_size))
    address_space = limits["F1_PEAK_RSS_OCTETS"]
    resource.setrlimit(resource.RLIMIT_AS, (address_space, address_space))
    nofile = limits["INPUT_FILE_COUNT"]
    resource.setrlimit(resource.RLIMIT_NOFILE, (nofile, nofile))


def _drain_pipe(descriptor, state, capture_limit):
    while True:
        try:
            raw = os.read(descriptor, 65536)
        except BlockingIOError:
            return False
        except OSError as error:
            _reject(
                "COMPARATOR_RESOURCE_EVIDENCE_INVALID",
                f"diagnostic pipe read failed: {error}",
            )
        if not raw:
            try:
                os.close(descriptor)
            except OSError:
                pass
            return True
        state["octets"] += len(raw)
        state["hash"].update(raw)
        remaining = max(0, capture_limit + 1 - len(state["captured"]))
        if remaining:
            state["captured"].extend(raw[:remaining])


def _signal_child(pid, selected_signal):
    try:
        os.kill(pid, selected_signal)
    except ProcessLookupError:
        pass
    except OSError as error:
        _reject(
            "COMPARATOR_RESOURCE_EVIDENCE_INVALID",
            f"watchdog signal failed: {error}",
        )


def _enforce_execution_envelope(envelope, contract):
    schema = contract["report_contract"]["execution_envelope_schema"]
    _closed_object(envelope, schema["ordered_member_names"], "execution envelope")
    limits = _limit_map(contract)
    integer_names = (
        "implementation_raw_octets",
        "observed_wall_nanoseconds",
        "observed_cpu_nanoseconds",
        "observed_peak_rss_octets",
        "observed_temporary_storage_octets",
        "semantic_payload_raw_octets",
        "exit_code",
        "stdout_octets",
        "stderr_octets",
    )
    if any(not _is_int(envelope[name]) or envelope[name] < 0 for name in integer_names):
        _reject(
            "COMPARATOR_RESOURCE_EVIDENCE_INVALID",
            "execution envelope has a noninteger observation",
        )
    for name in (
        "implementation_raw_sha256",
        "semantic_payload_raw_sha256",
        "stdout_sha256",
        "stderr_sha256",
    ):
        _hex_digest(envelope[name], name)
    versions = contract["report_contract"]["version_literals"]
    if envelope["execution_envelope_version"] != versions["execution_envelope_version"]:
        _reject(
            "COMPARATOR_RESOURCE_EVIDENCE_INVALID",
            "execution envelope version differs",
        )
    if (
        envelope["exit_code"] != 0
        or envelope["stdout_octets"] != 0
        or envelope["stderr_octets"] != 0
        or envelope["stdout_sha256"] != _sha256(b"")
        or envelope["stderr_sha256"] != _sha256(b"")
    ):
        _reject(
            "COMPARATOR_RESOURCE_EVIDENCE_INVALID",
            "child did not complete silently and successfully",
        )
    if (
        envelope["semantic_payload_raw_octets"]
        >= limits["INDIVIDUAL_FILE_STRICT_UPPER_OCTETS"]
    ):
        _reject(
            "COMPARATOR_RESOURCE_EVIDENCE_INVALID",
            "semantic output exceeds file F0",
        )
    comparisons = (
        (
            envelope["observed_wall_nanoseconds"],
            limits["F1_WALL_CLOCK_SECONDS"] * 1_000_000_000,
            "wall",
        ),
        (
            envelope["observed_cpu_nanoseconds"],
            limits["F1_CPU_SECONDS"] * 1_000_000_000,
            "CPU",
        ),
        (
            envelope["observed_peak_rss_octets"],
            limits["F1_PEAK_RSS_OCTETS"],
            "RSS",
        ),
        (
            envelope["observed_temporary_storage_octets"],
            limits["F1_TEMPORARY_STORAGE_OCTETS"],
            "temporary storage",
        ),
    )
    for observed, ceiling, label in comparisons:
        if observed > ceiling:
            _reject(
                "COMPARATOR_RESOURCE_EVIDENCE_INVALID",
                f"child {label} exceeds F0",
            )
    capture_limit = contract["resource_enforcement_contract"][
        "child_execution_program"
    ]["stdout_stderr_capture_limit_octets_each"]
    if (
        envelope["stdout_octets"] > capture_limit
        or envelope["stderr_octets"] > capture_limit
    ):
        _reject(
            "COMPARATOR_RESOURCE_EVIDENCE_INVALID",
            "diagnostic capture exceeds limit",
        )


def _run_child(
    label,
    contract,
    seed,
    source,
    output_directory,
    staging,
    staging_state,
):
    limits = _limit_map(contract)
    _verify_source_unchanged(source, contract)
    execution = contract["resource_enforcement_contract"]["child_execution_program"]
    capture_limit = execution["stdout_stderr_capture_limit_octets_each"]
    semantic_path = output_directory / "semantic.json"
    seed_path = (
        ROOT / contract["input_authority"]["sole_authorized_repository_relative_path"]
    )
    arguments = [
        sys.executable,
        "-I",
        "-S",
        "-B",
        str(source["path"]),
        "--seed",
        str(seed_path),
        "--semantic-output",
        str(semantic_path),
    ]
    environment = dict(execution["frozen_environment"])
    stdout_read, stdout_write = os.pipe()
    stderr_read, stderr_write = os.pipe()
    start_ns = time.monotonic_ns()
    try:
        pid = os.fork()
    except OSError as error:
        for descriptor in (
            stdout_read,
            stdout_write,
            stderr_read,
            stderr_write,
        ):
            os.close(descriptor)
        _reject("COMPARATOR_RESOURCE_EVIDENCE_INVALID", f"fork failed: {error}")
    if pid == 0:
        try:
            os.close(stdout_read)
            os.close(stderr_read)
            os.chdir(ROOT)
            os.umask(0o077)
            _set_child_limits(limits)
            os.dup2(stdout_write, 1)
            os.dup2(stderr_write, 2)
            os.close(stdout_write)
            os.close(stderr_write)
            os.closerange(3, limits["INPUT_FILE_COUNT"])
            os.execve(sys.executable, arguments, environment)
        except BaseException:
            try:
                os.write(2, b"COMPARATOR_CHILD_LAUNCH_FAILED\n")
            except OSError:
                pass
            os._exit(127)
    os.close(stdout_write)
    os.close(stderr_write)
    os.set_blocking(stdout_read, False)
    os.set_blocking(stderr_read, False)
    pipe_states = {
        stdout_read: {
            "octets": 0,
            "hash": hashlib.sha256(),
            "captured": bytearray(),
        },
        stderr_read: {
            "octets": 0,
            "hash": hashlib.sha256(),
            "captured": bytearray(),
        },
    }
    open_descriptors = {stdout_read, stderr_read}
    status = None
    usage = None
    wait_return_ns = None
    resource_reason = None
    term_sent_ns = None
    wall_limit_ns = limits["F1_WALL_CLOCK_SECONDS"] * 1_000_000_000
    grace_ns = (
        contract["resource_enforcement_contract"]["watchdog_grace_seconds"]
        * 1_000_000_000
    )
    maximum_temporary = _allocated_octets(output_directory)
    try:
        while status is None or open_descriptors:
            for descriptor in tuple(open_descriptors):
                if _drain_pipe(descriptor, pipe_states[descriptor], capture_limit):
                    open_descriptors.remove(descriptor)
            now = time.monotonic_ns()
            temporary = _allocated_octets(output_directory)
            maximum_temporary = max(maximum_temporary, temporary)
            staging_state["maximum"] = max(
                staging_state["maximum"], _allocated_octets(staging)
            )
            if resource_reason is None:
                if any(
                    state["octets"] > capture_limit for state in pipe_states.values()
                ):
                    resource_reason = "diagnostic capture limit exceeded"
                elif maximum_temporary > limits["F1_TEMPORARY_STORAGE_OCTETS"]:
                    resource_reason = "temporary storage limit exceeded"
                elif (
                    staging_state["maximum"]
                    > limits["PUBLICATION_STAGING_STORAGE_OCTETS"]
                ):
                    resource_reason = "publication staging limit exceeded"
                elif now - start_ns > wall_limit_ns:
                    resource_reason = "wall watchdog expired"
            if resource_reason is not None and status is None:
                if term_sent_ns is None:
                    _signal_child(pid, signal.SIGTERM)
                    term_sent_ns = now
                elif now - term_sent_ns >= grace_ns:
                    _signal_child(pid, signal.SIGKILL)
            if status is None:
                try:
                    waited_pid, waited_status, waited_usage = os.wait4(pid, os.WNOHANG)
                except OSError as error:
                    _reject(
                        "COMPARATOR_RESOURCE_EVIDENCE_INVALID",
                        f"wait4 failed: {error}",
                    )
                if waited_pid == pid:
                    status = waited_status
                    usage = waited_usage
                    wait_return_ns = time.monotonic_ns()
            if status is None or open_descriptors:
                time.sleep(0.01)
    except BaseException:
        if status is None:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
            try:
                os.wait4(pid, 0)
            except OSError:
                pass
        for descriptor in tuple(open_descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise
    if usage is None or wait_return_ns is None or status is None:
        _reject(
            "COMPARATOR_RESOURCE_EVIDENCE_INVALID",
            "wait4 evidence is incomplete",
        )
    if sys.platform != "linux":
        _reject(
            "COMPARATOR_RESOURCE_EVIDENCE_INVALID",
            "Linux wait4 RSS is required",
        )
    exit_code = os.waitstatus_to_exitcode(status)
    _verify_source_unchanged(source, contract)
    stdout_state = pipe_states[stdout_read]
    stderr_state = pipe_states[stderr_read]
    if resource_reason is not None:
        _reject("COMPARATOR_RESOURCE_EVIDENCE_INVALID", resource_reason)
    if exit_code != 0:
        _reject(
            "COMPARATOR_REPORT_INVALID",
            f"implementation {label} exited {exit_code}",
        )
    if stdout_state["octets"] or stderr_state["octets"]:
        _reject(
            "COMPARATOR_RESOURCE_EVIDENCE_INVALID",
            f"implementation {label} was noisy",
        )
    try:
        entries = list(os.scandir(output_directory))
    except OSError as error:
        _reject(
            "COMPARATOR_REPORT_INVALID",
            f"child output listing failed: {error}",
        )
    if len(entries) != 1 or entries[0].name != semantic_path.name:
        _reject(
            "COMPARATOR_REPORT_INVALID",
            f"implementation {label} output differs",
        )
    semantic_raw, semantic_status = _secure_read(
        semantic_path,
        limits["INDIVIDUAL_FILE_STRICT_UPPER_OCTETS"] - 1,
    )
    if semantic_status.st_mode & 0o777 != 0o600:
        _reject(
            "COMPARATOR_REPORT_INVALID",
            f"implementation {label} output mode differs",
        )
    semantic_payload = _validate_semantic_payload(semantic_raw, contract, seed)
    maximum_temporary = max(maximum_temporary, _allocated_octets(output_directory))
    staging_state["maximum"] = max(staging_state["maximum"], _allocated_octets(staging))
    envelope_names = contract["report_contract"]["execution_envelope_schema"][
        "ordered_member_names"
    ]
    values = {
        "execution_envelope_version": contract["report_contract"]["version_literals"][
            "execution_envelope_version"
        ],
        "implementation_label": label,
        "implementation_repository_relative_path": source["relative_path"],
        "implementation_raw_octets": source["raw_octets"],
        "implementation_raw_sha256": source["raw_sha256"],
        "python_implementation": sys.implementation.name,
        "python_version": (
            f"{sys.version_info.major}.{sys.version_info.minor}."
            f"{sys.version_info.micro}"
        ),
        "observed_wall_nanoseconds": wait_return_ns - start_ns,
        "observed_cpu_nanoseconds": (
            int(usage.ru_utime * 1_000_000_000) + int(usage.ru_stime * 1_000_000_000)
        ),
        "observed_peak_rss_octets": int(usage.ru_maxrss) * 1024,
        "observed_temporary_storage_octets": maximum_temporary,
        "semantic_payload_raw_octets": len(semantic_raw),
        "semantic_payload_raw_sha256": _sha256(semantic_raw),
        "exit_code": exit_code,
        "stdout_octets": stdout_state["octets"],
        "stdout_sha256": stdout_state["hash"].hexdigest(),
        "stderr_octets": stderr_state["octets"],
        "stderr_sha256": stderr_state["hash"].hexdigest(),
    }
    envelope = {name: values[name] for name in envelope_names}
    _enforce_execution_envelope(envelope, contract)
    report_names = contract["report_contract"][
        "wrapped_report_root_ordered_member_names"
    ]
    report_values = {
        "semantic_payload": semantic_payload,
        "execution_envelope": envelope,
    }
    wrapped = {name: report_values[name] for name in report_names}
    return wrapped, semantic_raw


def _comparison_payload(
    contract,
    seed,
    sources,
    report_a,
    report_b,
    semantic_raw_a,
    semantic_raw_b,
):
    _enforce_execution_envelope(report_a["execution_envelope"], contract)
    _enforce_execution_envelope(report_b["execution_envelope"], contract)
    payload_a = report_a["semantic_payload"]
    payload_b = report_b["semantic_payload"]
    bytes_equal = semantic_raw_a == semantic_raw_b
    cases_equal = (
        payload_a["ordered_case_result_records"]
        == payload_b["ordered_case_result_records"]
    )
    metrics_equal = (
        payload_a["ordered_metric_summary_records"]
        == payload_b["ordered_metric_summary_records"]
    )
    identities_equal = (
        payload_a["semantic_payload_id"] == payload_b["semantic_payload_id"]
        and payload_a["semantic_count_vector_sha256"]
        == payload_b["semantic_count_vector_sha256"]
    )
    if not (bytes_equal and cases_equal and metrics_equal and identities_equal):
        _reject("COMPARATOR_RESULT_MISMATCH", "A and B semantic results differ")
    names = contract["report_contract"]["comparison_payload_schema"][
        "ordered_member_names"
    ]
    values = {
        "comparison_payload_version": contract["report_contract"]["version_literals"][
            "comparison_payload_version"
        ],
        "contract_id": contract["contract_id"],
        "seed_catalog_raw_sha256": contract["input_authority"][
            "accepted_catalog_raw_sha256"
        ],
        "seed_catalog_id": seed["seed_catalog_id"],
        "implementation_a_raw_sha256": sources["A"]["raw_sha256"],
        "implementation_b_raw_sha256": sources["B"]["raw_sha256"],
        "implementation_a_semantic_payload_id": payload_a["semantic_payload_id"],
        "implementation_b_semantic_payload_id": payload_b["semantic_payload_id"],
        "semantic_count_vector_sha256": payload_a["semantic_count_vector_sha256"],
        "semantic_payload_bytes_equal": True,
        "all_475_case_records_equal": True,
        "all_18_metric_summaries_equal": True,
        "all_resource_limits_satisfied": True,
        "comparison_status": contract["report_contract"]["comparison_payload_schema"][
            "success_status"
        ],
    }
    identity_payload = {
        name: values[name] for name in names if name != "comparison_payload_id"
    }
    values["comparison_payload_id"] = _domain_id(COMPARISON_DOMAIN, identity_payload)
    comparison = {name: values[name] for name in names}
    _validate_comparison_payload(comparison, contract)
    return comparison


def _validate_comparison_payload(comparison, contract):
    schema = contract["report_contract"]["comparison_payload_schema"]
    names = schema["ordered_member_names"]
    _closed_object(comparison, names, "comparison payload")
    if comparison["comparison_status"] != schema["success_status"]:
        _reject("COMPARATOR_RESULT_MISMATCH", "comparison status differs")
    for name in (
        "semantic_payload_bytes_equal",
        "all_475_case_records_equal",
        "all_18_metric_summaries_equal",
        "all_resource_limits_satisfied",
    ):
        if comparison[name] is not True:
            _reject(
                "COMPARATOR_RESULT_MISMATCH",
                f"comparison flag {name} is false",
            )
    for name in (
        "contract_id",
        "seed_catalog_raw_sha256",
        "seed_catalog_id",
        "implementation_a_raw_sha256",
        "implementation_b_raw_sha256",
        "implementation_a_semantic_payload_id",
        "implementation_b_semantic_payload_id",
        "semantic_count_vector_sha256",
        "comparison_payload_id",
    ):
        _hex_digest(comparison[name], name)
    identity_payload = {
        name: comparison[name] for name in names if name != "comparison_payload_id"
    }
    if comparison["comparison_payload_id"] != _domain_id(
        COMPARISON_DOMAIN, identity_payload
    ):
        _reject("COMPARATOR_RESULT_MISMATCH", "comparison identity differs")


def _validate_private_empty_directory(path):
    path = pathlib.Path(path)
    if not path.is_absolute() or os.path.realpath(path) != str(path):
        _reject(
            "OUTPUT_ATOMICITY_INVALID",
            "private directory path is not canonical",
        )
    try:
        status = os.lstat(path)
        entries = list(os.scandir(path))
    except OSError as error:
        _reject(
            "OUTPUT_ATOMICITY_INVALID",
            f"private directory check failed: {error}",
        )
    if (
        status.st_mode & 0o170000 != 0o040000
        or status.st_uid != os.getuid()
        or status.st_mode & 0o077
        or entries
    ):
        _reject(
            "OUTPUT_ATOMICITY_INVALID",
            "directory is not private and empty",
        )


def _run_comparison(contract, seed, seed_raw, sources, staging):
    del seed_raw
    _validate_private_empty_directory(staging)
    _validate_source_separation(sources, contract)
    directories = {}
    try:
        for label in ("A", "B"):
            child = staging / label.lower()
            os.mkdir(child, 0o700)
            directories[label] = child
    except OSError as error:
        _reject(
            "OUTPUT_ATOMICITY_INVALID",
            f"child directory creation failed: {error}",
        )
    staging_state = {"maximum": _allocated_octets(staging)}
    report_a, raw_a = _run_child(
        "A",
        contract,
        seed,
        sources["A"],
        directories["A"],
        staging,
        staging_state,
    )
    report_b, raw_b = _run_child(
        "B",
        contract,
        seed,
        sources["B"],
        directories["B"],
        staging,
        staging_state,
    )
    if (
        staging_state["maximum"]
        > _limit_map(contract)["PUBLICATION_STAGING_STORAGE_OCTETS"]
    ):
        _reject(
            "COMPARATOR_RESOURCE_EVIDENCE_INVALID",
            "publication staging exceeds F0",
        )
    reports = {"A": report_a, "B": report_b}
    comparison = _comparison_payload(
        contract, seed, sources, report_a, report_b, raw_a, raw_b
    )
    return comparison, reports


def _remove_tree(path):
    path = pathlib.Path(path)
    try:
        status = os.lstat(path)
    except FileNotFoundError:
        return
    except OSError as error:
        _reject("OUTPUT_ATOMICITY_INVALID", f"cleanup stat failed: {error}")
    if status.st_mode & 0o170000 != 0o040000:
        try:
            os.unlink(path)
        except OSError as error:
            _reject(
                "OUTPUT_ATOMICITY_INVALID",
                f"cleanup unlink failed: {error}",
            )
        return
    try:
        with os.scandir(path) as entries:
            children = [pathlib.Path(entry.path) for entry in entries]
        for child in children:
            _remove_tree(child)
        os.rmdir(path)
    except OSError as error:
        _reject("OUTPUT_ATOMICITY_INVALID", f"cleanup failed: {error}")


def _publish_atomic(target, raw):
    target = pathlib.Path(target)
    parent = target.parent
    temporary = parent / f".{target.name}.comparator.tmp"
    descriptor = None
    created = False
    published = False
    if target.exists() or target.is_symlink():
        _reject(
            "OUTPUT_ATOMICITY_INVALID",
            "comparison output already exists",
        )
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(temporary, flags, 0o600)
        created = True
        offset = 0
        while offset < len(raw):
            written = os.write(descriptor, raw[offset:])
            if written <= 0:
                _reject(
                    "OUTPUT_ATOMICITY_INVALID",
                    "comparison write made no progress",
                )
            offset += written
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.link(temporary, target, follow_symlinks=False)
        published = True
        os.unlink(temporary)
        created = False
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        directory = os.open(parent, directory_flags)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        status = os.lstat(target)
        if (
            status.st_mode & 0o170000 != 0o100000
            or status.st_mode & 0o777 != 0o600
            or status.st_size != len(raw)
        ):
            _reject(
                "OUTPUT_ATOMICITY_INVALID",
                "published comparison metadata differs",
            )
    except Reject:
        raise
    except OSError as error:
        _reject(
            "OUTPUT_ATOMICITY_INVALID",
            f"atomic comparison publication failed: {error}",
        )
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
        if published and sys.exc_info()[0] is not None:
            try:
                os.unlink(target)
                directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                directory = os.open(parent, directory_flags)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            except OSError:
                pass


def _arguments(argv):
    if len(argv) != 4 or argv[0] != "--contract" or argv[2] != "--comparison-output":
        _reject(
            "INVOCATION_INVALID",
            "expected --contract PATH --comparison-output PATH",
        )
    return argv[1], argv[3]


def _output_path(argument):
    target = pathlib.Path(argument)
    if not target.is_absolute() or target.name in {"", ".", ".."}:
        _reject(
            "OUTPUT_ATOMICITY_INVALID",
            "comparison output path is invalid",
        )
    parent = target.parent
    _validate_private_empty_directory(parent)
    if target.exists() or target.is_symlink():
        _reject(
            "OUTPUT_ATOMICITY_INVALID",
            "comparison output already exists",
        )
    return target


def _main(argv):
    contract_argument, output_argument = _arguments(argv)
    output = _output_path(output_argument)
    contract, contract_raw = _load_contract(contract_argument)
    seed, seed_raw, sources = _load_authorities(contract)
    stage = output.parent / f".{output.name}.comparator-stage-{os.getpid()}"
    try:
        os.mkdir(stage, 0o700)
    except OSError as error:
        _reject("OUTPUT_ATOMICITY_INVALID", f"staging creation failed: {error}")
    try:
        comparison, _reports = _run_comparison(contract, seed, seed_raw, sources, stage)
        del contract_raw
        raw = _pretty_bytes(comparison)
        _remove_tree(stage)
        if list(os.scandir(output.parent)):
            _reject(
                "OUTPUT_ATOMICITY_INVALID",
                "unexpected entry before publication",
            )
        _publish_atomic(output, raw)
    finally:
        if stage.exists() or stage.is_symlink():
            _remove_tree(stage)


def _entrypoint():
    try:
        _main(sys.argv[1:])
        return 0
    except Reject as error:
        line = f"{ERROR_PREFIX}_{error.code}: {error.message}\n".encode(
            "utf-8", "replace"
        )
        try:
            os.write(2, line)
        except OSError:
            pass
        return EXIT_CODES.get(error.code, EXIT_CODES["INTERNAL_FAIL_CLOSED"])
    except BaseException as error:
        line = (
            f"{ERROR_PREFIX}_INTERNAL_FAIL_CLOSED: {type(error).__name__}\n"
        ).encode("ascii", "replace")
        try:
            os.write(2, line)
        except OSError:
            pass
        return EXIT_CODES["INTERNAL_FAIL_CLOSED"]


if __name__ == "__main__":
    raise SystemExit(_entrypoint())
