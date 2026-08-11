#!/usr/bin/env python3
"""Standalone S1-A3 finalizer for the Raw V8 Step-2 V2 authority bundle.

The program imports no repository code. It executes the accepted comparator
and preflight A as isolated fixed-path children, validates their fresh output,
derives every F1/F2 value, and either atomically creates or exactly checks the
canonical finalization manifest.
"""

import hashlib
import json
import os
import pathlib
import resource
import signal
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
SEED_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json"
)
CONTRACT_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_preflight_contract_v49f.json"
)
A_RELATIVE_PATH = "scripts/tests/preflight_raw_v8_step2_maximum_protocol_v2_a_v49f.py"
B_RELATIVE_PATH = "scripts/tests/preflight_raw_v8_step2_maximum_protocol_v2_b_v49f.py"
COMPARATOR_RELATIVE_PATH = (
    "scripts/tests/compare_raw_v8_step2_maximum_protocol_v2_preflights_v49f.py"
)

SEED_OCTETS = 13_419_905
SEED_SHA256 = "a75a2f352e8513b7ff0043693a0c65ebbf4bc6f06859354789af69e1162b0e4f"
SEED_ID = "ac22151fa74702ac1488924f01161eaa38574545e6272a290db6b0bbd288ae5f"
CONTRACT_OCTETS = 16_919
CONTRACT_SHA256 = "007ed9a8d06b91f73708129b66a33eaf525e203d306426d05b8cd8bba9c7294b"
CONTRACT_ID = "6609ad7b9abf21432136e49af178e20c17cb7bc27d3b444a4b6f01a17073fc76"
A_OCTETS = 97_254
A_SHA256 = "fa02fcfce55e6e7b16ef90422ac079b8e34cbc1cf2c0d8422dd8b28639ec76e7"
B_OCTETS = 89_474
B_SHA256 = "de618350fc5c5c48d998de7ae49449f9edca0eff25161bde07cf271c22e47954"
COMPARATOR_OCTETS = 52_732
COMPARATOR_SHA256 = "e0527f10a4ccb18891d18b8910101066bbc01ab57eebc2e3b18338d7c6f4f793"

MANIFEST_VERSION = (
    "riskyieldmm.raw_v8_step2_external_schema_v2.finalization_manifest.v1"
)
FINALIZATION_STATUS = "FINAL_V2_F2_FROZEN"
CANONICALIZATION_VERSION = "riskyieldmm_canonical_json_v1"
MANIFEST_DOMAIN = "RiskYieldMMStep2FinalizationManifestV1V4_9F_RawV8"
CONTRACT_DOMAIN = "RiskYieldMMStep2PreflightExecutionContractV1V4_9F_RawV8"
COMPARISON_DOMAIN = "RiskYieldMMStep2PreflightComparisonV1V4_9F_RawV8"
CASE_RESULT_DOMAIN = "RiskYieldMMStep2PreflightCaseResultV1V4_9F_RawV8"
COUNT_VECTOR_DOMAIN = "RiskYieldMMStep2PreflightCountVectorV1V4_9F_RawV8"
SEMANTIC_PAYLOAD_DOMAIN = "RiskYieldMMStep2PreflightSemanticPayloadV1V4_9F_RawV8"
ERROR_PREFIX = "RAW_V8_STEP2_MAXIMUM_PROTOCOL_V2_FINALIZER"
U128_MAX = (1 << 128) - 1

ROOT_MEMBERS = (
    "finalization_manifest_version",
    "finalization_status",
    "canonicalization_version",
    "protocol_version",
    "protocol_counting_semantics_id",
    "seed_authority",
    "preflight_contract_authority",
    "ordered_implementation_authorities",
    "semantic_evidence",
    "comparison_evidence",
    "ordered_f2_limit_records",
    "finalization_manifest_id",
)
SEED_AUTHORITY_MEMBERS = (
    "repository_relative_path",
    "raw_octets",
    "raw_sha256",
    "catalog_version",
    "seed_catalog_id",
)
CONTRACT_AUTHORITY_MEMBERS = (
    "repository_relative_path",
    "raw_octets",
    "raw_sha256",
    "contract_version",
    "contract_id",
)
IMPLEMENTATION_AUTHORITY_MEMBERS = (
    "implementation_position",
    "implementation_label",
    "repository_relative_path",
    "raw_octets",
    "raw_sha256",
    "algorithm_marker",
)
SEMANTIC_EVIDENCE_MEMBERS = (
    "preflight_semantic_payload_version",
    "raw_octets",
    "raw_sha256",
    "semantic_payload_id",
    "semantic_count_vector_sha256",
    "ordered_metric_evidence_records",
)
METRIC_EVIDENCE_MEMBERS = (
    "metric_position",
    "metric_name",
    "full_run_aggregation",
    "required_per_case",
    "required_full_run",
)
COMPARISON_EVIDENCE_MEMBERS = (
    "comparison_payload_version",
    "raw_octets",
    "raw_sha256",
    "comparison_payload_id",
    "comparison_status",
    "implementation_a_raw_sha256",
    "implementation_b_raw_sha256",
    "implementation_a_semantic_payload_id",
    "implementation_b_semantic_payload_id",
    "semantic_count_vector_sha256",
    "semantic_payload_bytes_equal",
    "all_475_case_records_equal",
    "all_18_metric_summaries_equal",
    "all_resource_limits_satisfied",
)
F2_MEMBERS = (
    "metric_position",
    "metric_name",
    "full_run_aggregation",
    "required_per_case",
    "per_case_rounding_unit",
    "f2_per_case",
    "per_case_f0_ceiling",
    "required_full_run",
    "full_run_rounding_unit",
    "f2_full_run",
    "full_run_f0_ceiling",
)

EXIT_CODES = {
    "INVOCATION_INVALID": 2,
    "INPUT_AUTHORITY_INVALID": 3,
    "INPUT_RACE_DETECTED": 3,
    "INPUT_CANONICALIZATION_INVALID": 4,
    "INPUT_SCHEMA_INVALID": 4,
    "EVIDENCE_INVALID": 5,
    "RESOURCE_LIMIT_EXCEEDED": 6,
    "FORBIDDEN_DEPENDENCY": 7,
    "OUTPUT_ATOMICITY_INVALID": 8,
    "INTERNAL_FAIL_CLOSED": 9,
}


class Reject(Exception):
    """Stable fail-closed finalizer rejection."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = " ".join(str(message).split())[:768]


def _reject(code, message):
    raise Reject(code, message)


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _u128(value, label="value"):
    if not _is_int(value) or not 0 <= value <= U128_MAX:
        _reject("EVIDENCE_INVALID", f"{label} is not UInt128")
    return value


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
        _reject("INPUT_CANONICALIZATION_INVALID", f"canonical JSON rejected: {error}")


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
        _reject("INPUT_CANONICALIZATION_INVALID", f"pretty JSON rejected: {error}")


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


def _parse_integer(text):
    if len(text.lstrip("-")) > 39:
        _reject("INPUT_CANONICALIZATION_INVALID", "JSON integer exceeds UInt128 width")
    return int(text)


def _parse_json(raw):
    try:
        return json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_duplicate_closed_object,
            parse_float=_reject_float,
            parse_int=_parse_integer,
            parse_constant=_reject_constant,
        )
    except Reject:
        raise
    except (UnicodeError, json.JSONDecodeError, ValueError) as error:
        _reject("INPUT_CANONICALIZATION_INVALID", f"strict JSON rejected: {error}")


def _closed_object(value, names, label):
    if not isinstance(value, dict) or set(value) != set(names):
        _reject("INPUT_SCHEMA_INVALID", f"{label} has wrong members")


def _hex_digest(value, label):
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        _reject("INPUT_SCHEMA_INVALID", f"{label} is not a SHA-256 digest")


def _secure_read(path, maximum_octets, expected_octets=None, expected_sha256=None):
    path = pathlib.Path(path)
    if not path.is_absolute() or os.path.realpath(path) != str(path):
        _reject("INPUT_AUTHORITY_INVALID", f"noncanonical or symlinked path: {path}")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = None
    try:
        descriptor = os.open(path, flags)
        before = os.fstat(descriptor)
        if before.st_mode & 0o170000 != 0o100000:
            _reject("INPUT_AUTHORITY_INVALID", f"not a regular file: {path}")
        if before.st_size < 0 or before.st_size > maximum_octets:
            _reject("INPUT_AUTHORITY_INVALID", f"file size exceeds limit: {path}")
        if expected_octets is not None and before.st_size != expected_octets:
            _reject("INPUT_AUTHORITY_INVALID", f"file length differs: {path}")
        chunks = []
        total = 0
        while True:
            available = maximum_octets + 1 - total
            chunk = os.read(descriptor, min(1_048_576, available))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > maximum_octets:
                _reject("INPUT_AUTHORITY_INVALID", f"file read exceeds limit: {path}")
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
            _reject("INPUT_RACE_DETECTED", f"file changed during read: {path}")
        raw = b"".join(chunks)
        if expected_octets is not None and len(raw) != expected_octets:
            _reject("INPUT_AUTHORITY_INVALID", f"file length differs: {path}")
        if expected_sha256 is not None and _sha256(raw) != expected_sha256:
            _reject("INPUT_AUTHORITY_INVALID", f"file hash differs: {path}")
        return raw, before
    except Reject:
        raise
    except OSError as error:
        _reject("INPUT_AUTHORITY_INVALID", f"secure read failed for {path}: {error}")
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass


def _status_identity(status):
    return (
        status.st_dev,
        status.st_ino,
        status.st_mode,
        status.st_size,
        status.st_mtime_ns,
        status.st_ctime_ns,
    )


def _verify_file_snapshot(snapshot):
    _raw, status = _secure_read(
        snapshot["path"],
        snapshot["raw_octets"],
        expected_octets=snapshot["raw_octets"],
        expected_sha256=snapshot["raw_sha256"],
    )
    if _status_identity(status) != snapshot["status_identity"]:
        _reject("INPUT_RACE_DETECTED", f"authority changed: {snapshot['path']}")


def _limit_map(contract):
    rows = contract["resource_enforcement_contract"]["ordered_f0_limit_records"]
    return {row["resource_name"]: row["expected_value"] for row in rows}


def _json_shape(value, limits):
    maximum_depth = limits["JSON_NESTING_DEPTH"]
    maximum_nodes = limits["DECODED_JSON_NODE_COUNT"]
    maximum_arrays = limits["DECODED_JSON_ARRAY_ENTRY_COUNT"]
    maximum_members = limits["DECODED_JSON_OBJECT_MEMBER_COUNT"]
    nodes = 0
    arrays = 0
    members = 0
    stack = [(value, 1)]
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if depth > maximum_depth or nodes > maximum_nodes:
            _reject("RESOURCE_LIMIT_EXCEEDED", "JSON shape exceeds limit")
        if isinstance(current, list):
            arrays += len(current)
            if arrays > maximum_arrays:
                _reject("RESOURCE_LIMIT_EXCEEDED", "JSON array entries exceed limit")
            stack.extend((child, depth + 1) for child in current)
        elif isinstance(current, dict):
            members += len(current)
            if members > maximum_members:
                _reject("RESOURCE_LIMIT_EXCEEDED", "JSON object members exceed limit")
            stack.extend((child, depth + 1) for child in current.values())


def _validate_contract(contract, raw):
    if raw != _pretty_bytes(contract):
        _reject(
            "INPUT_CANONICALIZATION_INVALID", "contract is not canonical pretty JSON"
        )
    expected = {
        "contract_id",
        "contract_version",
        "error_taxonomy",
        "implementation_separation_policy",
        "input_authority",
        "report_contract",
        "resource_enforcement_contract",
        "unknown_or_extra_member_policy",
    }
    if not isinstance(contract, dict) or set(contract) != expected:
        _reject("INPUT_SCHEMA_INVALID", "contract root differs")
    payload = {name: value for name, value in contract.items() if name != "contract_id"}
    if contract["contract_id"] != CONTRACT_ID or contract["contract_id"] != _domain_id(
        CONTRACT_DOMAIN, payload
    ):
        _reject("INPUT_AUTHORITY_INVALID", "contract identity differs")
    if contract["unknown_or_extra_member_policy"] != "REJECT":
        _reject("INPUT_SCHEMA_INVALID", "contract is not fail closed")


def _validate_seed(seed, raw, contract):
    if raw != _pretty_bytes(seed):
        _reject("INPUT_CANONICALIZATION_INVALID", "seed is not canonical pretty JSON")
    authority = contract["input_authority"]
    expected = {
        "catalog_version": authority["accepted_catalog_version"],
        "canonicalization_version": authority["canonicalization_version"],
        "measurement_schema_version": authority["measurement_schema_version"],
        "protocol_counting_semantics_id": authority[
            "accepted_protocol_counting_semantics_id"
        ],
        "seed_catalog_id": authority["accepted_catalog_id"],
    }
    for name, expected_value in expected.items():
        if seed.get(name) != expected_value:
            _reject("INPUT_AUTHORITY_INVALID", f"seed {name} differs")
    metrics = seed.get("resource_metric_catalog", {}).get("ordered_metric_records")
    if not isinstance(metrics, list) or len(metrics) != 18:
        _reject("INPUT_SCHEMA_INVALID", "seed metric authority differs")
    if [row.get("metric_position") for row in metrics] != list(range(1, 19)):
        _reject("INPUT_SCHEMA_INVALID", "seed metric order differs")
    limits = _limit_map(contract)
    _json_shape(seed, limits)


def _source_specifications():
    return (
        (
            "A",
            A_RELATIVE_PATH,
            A_OCTETS,
            A_SHA256,
            "ITERATIVE_CATALOG_INTERPRETER_V1",
        ),
        (
            "B",
            B_RELATIVE_PATH,
            B_OCTETS,
            B_SHA256,
            "FLAT_LEDGER_PREFIX_SUM_V1",
        ),
        (
            "COMPARATOR",
            COMPARATOR_RELATIVE_PATH,
            COMPARATOR_OCTETS,
            COMPARATOR_SHA256,
            "RiskYieldMMStep2PreflightComparisonV1V4_9F_RawV8",
        ),
    )


def _load_authorities():
    contract_raw, contract_status = _secure_read(
        ROOT / CONTRACT_RELATIVE_PATH,
        CONTRACT_OCTETS,
        expected_octets=CONTRACT_OCTETS,
        expected_sha256=CONTRACT_SHA256,
    )
    contract = _parse_json(contract_raw)
    _validate_contract(contract, contract_raw)
    limits = _limit_map(contract)
    file_limit = limits["INDIVIDUAL_FILE_STRICT_UPPER_OCTETS"] - 1
    seed_raw, seed_status = _secure_read(
        ROOT / SEED_RELATIVE_PATH,
        file_limit,
        expected_octets=SEED_OCTETS,
        expected_sha256=SEED_SHA256,
    )
    seed = _parse_json(seed_raw)
    _validate_seed(seed, seed_raw, contract)

    sources = {}
    snapshots = {
        "SEED": {
            "path": ROOT / SEED_RELATIVE_PATH,
            "raw_octets": len(seed_raw),
            "raw_sha256": SEED_SHA256,
            "status_identity": _status_identity(seed_status),
        },
        "CONTRACT": {
            "path": ROOT / CONTRACT_RELATIVE_PATH,
            "raw_octets": len(contract_raw),
            "raw_sha256": CONTRACT_SHA256,
            "status_identity": _status_identity(contract_status),
        },
    }
    devices = []
    hashes = []
    for label, relative, octets, digest, marker in _source_specifications():
        raw, status = _secure_read(
            ROOT / relative,
            file_limit,
            expected_octets=octets,
            expected_sha256=digest,
        )
        if marker.encode("utf-8") not in raw:
            _reject("FORBIDDEN_DEPENDENCY", f"{label} algorithm marker is absent")
        sources[label] = {
            "path": ROOT / relative,
            "relative_path": relative,
            "raw_octets": len(raw),
            "raw_sha256": digest,
            "algorithm_marker": marker,
        }
        snapshots[label] = {
            "path": ROOT / relative,
            "raw_octets": len(raw),
            "raw_sha256": digest,
            "status_identity": _status_identity(status),
        }
        devices.append((status.st_dev, status.st_ino))
        hashes.append(digest)
    if len(devices) != len(set(devices)) or len(hashes) != len(set(hashes)):
        _reject("FORBIDDEN_DEPENDENCY", "implementation sources are not separate")
    total = (
        len(seed_raw)
        + len(contract_raw)
        + sum(source["raw_octets"] for source in sources.values())
    )
    if total > limits["TOTAL_PINNED_INPUT_OCTETS"]:
        _reject("RESOURCE_LIMIT_EXCEEDED", "pinned inputs exceed F0")
    return seed, seed_raw, contract, contract_raw, sources, snapshots


def _verify_authorities_unchanged(snapshots):
    if set(snapshots) != {"SEED", "CONTRACT", "A", "B", "COMPARATOR"}:
        _reject("INPUT_AUTHORITY_INVALID", "authority snapshot set differs")
    for label in ("SEED", "CONTRACT", "A", "B", "COMPARATOR"):
        _verify_file_snapshot(snapshots[label])


def _validate_semantic_payload(raw, contract, seed):
    limits = _limit_map(contract)
    if len(raw) >= limits["INDIVIDUAL_FILE_STRICT_UPPER_OCTETS"]:
        _reject("RESOURCE_LIMIT_EXCEEDED", "semantic payload exceeds file F0")
    payload = _parse_json(raw)
    if raw != _pretty_bytes(payload):
        _reject("INPUT_CANONICALIZATION_INVALID", "semantic payload is not canonical")
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
            _reject("EVIDENCE_INVALID", f"semantic {name} differs")

    case_rows = payload["ordered_case_result_records"]
    summary_rows = payload["ordered_metric_summary_records"]
    if not isinstance(case_rows, list) or len(case_rows) != 475:
        _reject("EVIDENCE_INVALID", "semantic case count differs")
    if not isinstance(summary_rows, list) or len(summary_rows) != 18:
        _reject("EVIDENCE_INVALID", "semantic summary count differs")
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
            _reject("EVIDENCE_INVALID", f"case {position} binding differs")
        measurements = row["ordered_resource_measurements"]
        if not isinstance(measurements, list) or len(measurements) != 18:
            _reject("EVIDENCE_INVALID", f"case {position} metrics differ")
        for metric_index, (measurement, metric) in enumerate(
            zip(measurements, metrics, strict=True)
        ):
            _closed_object(
                measurement,
                measurement_names,
                f"case {position} measurement {metric_index + 1}",
            )
            measured = measurement["measured_value"]
            if (
                measurement["metric_position"] != metric["metric_position"]
                or measurement["metric_name"] != metric["metric_name"]
                or not _is_int(measured)
                or not 0 <= measured <= U128_MAX
                or measured > metric["per_case_f0_ceiling"]
            ):
                _reject(
                    "EVIDENCE_INVALID",
                    f"case {position} measurement {metric_index + 1} differs",
                )
            columns[metric_index].append(measured)
        _hex_digest(row["derivation_event_stream_sha256"], "event stream digest")
        case_payload = {
            name: value
            for name, value in row.items()
            if name != "case_result_record_id"
        }
        if row["case_result_record_id"] != _domain_id(CASE_RESULT_DOMAIN, case_payload):
            _reject("EVIDENCE_INVALID", f"case {position} identity differs")

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
            _reject("EVIDENCE_INVALID", f"metric {metric_index} exceeds F0")
        expected_summary = {
            "metric_position": metric["metric_position"],
            "metric_name": metric["metric_name"],
            "full_run_aggregation": metric["full_run_aggregation"],
            "full_run_value": full_value,
            "maximum_case_value": maximum,
            "ordered_maximum_case_positions": maximum_positions,
        }
        if summary != expected_summary:
            _reject("EVIDENCE_INVALID", f"metric summary {metric_index} differs")

    case_vector = [
        {name: value for name, value in row.items() if name != "case_result_record_id"}
        for row in case_rows
    ]
    count_vector = _domain_id(COUNT_VECTOR_DOMAIN, [*case_vector, *summary_rows])
    if payload["semantic_count_vector_sha256"] != count_vector:
        _reject("EVIDENCE_INVALID", "semantic count-vector identity differs")
    identity_payload = {
        name: value for name, value in payload.items() if name != "semantic_payload_id"
    }
    if payload["semantic_payload_id"] != _domain_id(
        SEMANTIC_PAYLOAD_DOMAIN, identity_payload
    ):
        _reject("EVIDENCE_INVALID", "semantic payload identity differs")
    return payload


def _validate_comparison_payload(raw, contract, seed, sources, semantic=None):
    limits = _limit_map(contract)
    if len(raw) >= limits["INDIVIDUAL_FILE_STRICT_UPPER_OCTETS"]:
        _reject("RESOURCE_LIMIT_EXCEEDED", "comparison exceeds file F0")
    comparison = _parse_json(raw)
    if raw != _pretty_bytes(comparison):
        _reject("INPUT_CANONICALIZATION_INVALID", "comparison is not canonical")
    schema = contract["report_contract"]["comparison_payload_schema"]
    names = schema["ordered_member_names"]
    _closed_object(comparison, names, "comparison payload")
    expected = {
        "comparison_payload_version": contract["report_contract"]["version_literals"][
            "comparison_payload_version"
        ],
        "contract_id": contract["contract_id"],
        "seed_catalog_raw_sha256": SEED_SHA256,
        "seed_catalog_id": seed["seed_catalog_id"],
        "implementation_a_raw_sha256": sources["A"]["raw_sha256"],
        "implementation_b_raw_sha256": sources["B"]["raw_sha256"],
        "comparison_status": schema["success_status"],
    }
    for name, expected_value in expected.items():
        if comparison[name] != expected_value:
            _reject("EVIDENCE_INVALID", f"comparison {name} differs")
    for name in (
        "semantic_payload_bytes_equal",
        "all_475_case_records_equal",
        "all_18_metric_summaries_equal",
        "all_resource_limits_satisfied",
    ):
        if comparison[name] is not True:
            _reject("EVIDENCE_INVALID", f"comparison flag {name} is false")
    for name in (
        "implementation_a_semantic_payload_id",
        "implementation_b_semantic_payload_id",
        "semantic_count_vector_sha256",
        "comparison_payload_id",
    ):
        _hex_digest(comparison[name], name)
    if (
        comparison["implementation_a_semantic_payload_id"]
        != comparison["implementation_b_semantic_payload_id"]
    ):
        _reject("EVIDENCE_INVALID", "comparison semantic IDs differ")
    identity_payload = {
        name: comparison[name] for name in names if name != "comparison_payload_id"
    }
    if comparison["comparison_payload_id"] != _domain_id(
        COMPARISON_DOMAIN, identity_payload
    ):
        _reject("EVIDENCE_INVALID", "comparison identity differs")
    if semantic is not None and (
        semantic["semantic_payload_id"]
        != comparison["implementation_a_semantic_payload_id"]
        or semantic["semantic_count_vector_sha256"]
        != comparison["semantic_count_vector_sha256"]
    ):
        _reject("EVIDENCE_INVALID", "direct A evidence differs from comparison")
    return comparison


def _round_up(value, unit):
    value = _u128(value, "F1 value")
    unit = _u128(unit, "rounding unit")
    if unit == 0:
        _reject("EVIDENCE_INVALID", "rounding unit is zero")
    increment = (unit - (value % unit)) % unit
    if increment > U128_MAX - value:
        _reject("EVIDENCE_INVALID", "F2 rounding overflow")
    return value + increment


def _derive_metric_records(seed, summaries):
    metrics = seed["resource_metric_catalog"]["ordered_metric_records"]
    if not isinstance(summaries, list) or len(summaries) != 18:
        _reject("EVIDENCE_INVALID", "metric summary count differs")
    names = {
        "metric_position",
        "metric_name",
        "full_run_aggregation",
        "full_run_value",
        "maximum_case_value",
        "ordered_maximum_case_positions",
    }
    evidence = []
    f2_records = []
    for position, (metric, summary) in enumerate(
        zip(metrics, summaries, strict=True), 1
    ):
        if not isinstance(summary, dict) or set(summary) != names:
            _reject("EVIDENCE_INVALID", f"metric summary {position} members differ")
        if (
            summary["metric_position"] != position
            or summary["metric_name"] != metric["metric_name"]
            or summary["full_run_aggregation"] != metric["full_run_aggregation"]
        ):
            _reject("EVIDENCE_INVALID", f"metric summary {position} binding differs")
        per_case = _u128(summary["maximum_case_value"], "required per case")
        full_run = _u128(summary["full_run_value"], "required full run")
        per_unit = _u128(metric["per_case_f2_rounding_unit"], "per-case unit")
        full_unit = _u128(metric["full_run_f2_rounding_unit"], "full-run unit")
        per_f0 = _u128(metric["per_case_f0_ceiling"], "per-case F0")
        full_f0 = _u128(metric["full_run_f0_ceiling"], "full-run F0")
        per_f2 = _round_up(per_case, per_unit)
        full_f2 = _round_up(full_run, full_unit)
        if not per_case <= per_f2 <= per_f0:
            _reject("EVIDENCE_INVALID", f"metric {position} per-case F2 exceeds F0")
        if not full_run <= full_f2 <= full_f0:
            _reject("EVIDENCE_INVALID", f"metric {position} full-run F2 exceeds F0")
        evidence.append(
            {
                "metric_position": position,
                "metric_name": metric["metric_name"],
                "full_run_aggregation": metric["full_run_aggregation"],
                "required_per_case": per_case,
                "required_full_run": full_run,
            }
        )
        f2_records.append(
            {
                "metric_position": position,
                "metric_name": metric["metric_name"],
                "full_run_aggregation": metric["full_run_aggregation"],
                "required_per_case": per_case,
                "per_case_rounding_unit": per_unit,
                "f2_per_case": per_f2,
                "per_case_f0_ceiling": per_f0,
                "required_full_run": full_run,
                "full_run_rounding_unit": full_unit,
                "f2_full_run": full_f2,
                "full_run_f0_ceiling": full_f0,
            }
        )
    return evidence, f2_records


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
            _reject("RESOURCE_LIMIT_EXCEEDED", f"storage observation failed: {error}")
        total += status.st_blocks * 512
        kind = status.st_mode & 0o170000
        if kind == 0o120000:
            _reject("RESOURCE_LIMIT_EXCEEDED", "symlink appeared in staging")
        if kind == 0o040000:
            try:
                with os.scandir(current) as entries:
                    stack.extend(pathlib.Path(entry.path) for entry in entries)
            except OSError as error:
                _reject("RESOURCE_LIMIT_EXCEEDED", f"storage scan failed: {error}")
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
            raw = os.read(descriptor, 65_536)
        except BlockingIOError:
            return False
        except OSError as error:
            _reject("RESOURCE_LIMIT_EXCEEDED", f"diagnostic read failed: {error}")
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
        _reject("RESOURCE_LIMIT_EXCEEDED", f"watchdog signal failed: {error}")


def _run_child(label, arguments, output_directory, output_name, contract, staging):
    limits = _limit_map(contract)
    execution = contract["resource_enforcement_contract"]["child_execution_program"]
    capture_limit = execution["stdout_stderr_capture_limit_octets_each"]
    output_path = output_directory / output_name
    stdout_read, stdout_write = os.pipe()
    stderr_read, stderr_write = os.pipe()
    start_ns = time.monotonic_ns()
    try:
        pid = os.fork()
    except OSError as error:
        for descriptor in (stdout_read, stdout_write, stderr_read, stderr_write):
            os.close(descriptor)
        _reject("RESOURCE_LIMIT_EXCEEDED", f"fork failed: {error}")
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
            os.execve(sys.executable, arguments, dict(execution["frozen_environment"]))
        except BaseException:
            try:
                os.write(2, b"FINALIZER_CHILD_LAUNCH_FAILED\n")
            except OSError:
                pass
            os._exit(127)
    os.close(stdout_write)
    os.close(stderr_write)
    os.set_blocking(stdout_read, False)
    os.set_blocking(stderr_read, False)
    states = {
        stdout_read: {"octets": 0, "hash": hashlib.sha256(), "captured": bytearray()},
        stderr_read: {"octets": 0, "hash": hashlib.sha256(), "captured": bytearray()},
    }
    open_descriptors = {stdout_read, stderr_read}
    status = None
    usage = None
    wait_return_ns = None
    reason = None
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
                if _drain_pipe(descriptor, states[descriptor], capture_limit):
                    open_descriptors.remove(descriptor)
            now = time.monotonic_ns()
            maximum_temporary = max(
                maximum_temporary, _allocated_octets(output_directory)
            )
            staging_octets = _allocated_octets(staging)
            if reason is None:
                if any(state["octets"] > capture_limit for state in states.values()):
                    reason = "diagnostic capture limit exceeded"
                elif maximum_temporary > limits["F1_TEMPORARY_STORAGE_OCTETS"]:
                    reason = "temporary storage limit exceeded"
                elif staging_octets > limits["PUBLICATION_STAGING_STORAGE_OCTETS"]:
                    reason = "publication staging limit exceeded"
                elif now - start_ns > wall_limit_ns:
                    reason = "wall watchdog expired"
            if reason is not None and status is None:
                if term_sent_ns is None:
                    _signal_child(pid, signal.SIGTERM)
                    term_sent_ns = now
                elif now - term_sent_ns >= grace_ns:
                    _signal_child(pid, signal.SIGKILL)
            if status is None:
                try:
                    waited_pid, waited_status, waited_usage = os.wait4(pid, os.WNOHANG)
                except OSError as error:
                    _reject("RESOURCE_LIMIT_EXCEEDED", f"wait4 failed: {error}")
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
        _reject("RESOURCE_LIMIT_EXCEEDED", "wait4 evidence is incomplete")
    if sys.platform != "linux":
        _reject("RESOURCE_LIMIT_EXCEEDED", "Linux wait4 RSS is required")
    exit_code = os.waitstatus_to_exitcode(status)
    if reason is not None:
        _reject("RESOURCE_LIMIT_EXCEEDED", reason)
    if exit_code != 0:
        _reject("EVIDENCE_INVALID", f"{label} exited {exit_code}")
    if states[stdout_read]["octets"] or states[stderr_read]["octets"]:
        _reject("RESOURCE_LIMIT_EXCEEDED", f"{label} was noisy")
    wall = wait_return_ns - start_ns
    cpu = int(usage.ru_utime * 1_000_000_000) + int(usage.ru_stime * 1_000_000_000)
    rss = int(usage.ru_maxrss) * 1_024
    if wall > wall_limit_ns or cpu > limits["F1_CPU_SECONDS"] * 1_000_000_000:
        _reject("RESOURCE_LIMIT_EXCEEDED", f"{label} time exceeds F0")
    if rss > limits["F1_PEAK_RSS_OCTETS"]:
        _reject("RESOURCE_LIMIT_EXCEEDED", f"{label} RSS exceeds F0")
    try:
        entries = list(os.scandir(output_directory))
    except OSError as error:
        _reject("EVIDENCE_INVALID", f"{label} output listing failed: {error}")
    if len(entries) != 1 or entries[0].name != output_name:
        _reject("EVIDENCE_INVALID", f"{label} output differs")
    raw, output_status = _secure_read(
        output_path, limits["INDIVIDUAL_FILE_STRICT_UPPER_OCTETS"] - 1
    )
    if output_status.st_mode & 0o777 != 0o600:
        _reject("EVIDENCE_INVALID", f"{label} output mode differs")
    return raw


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
            _reject("OUTPUT_ATOMICITY_INVALID", f"cleanup unlink failed: {error}")
        return
    try:
        with os.scandir(path) as entries:
            children = [pathlib.Path(entry.path) for entry in entries]
        for child in children:
            _remove_tree(child)
        os.rmdir(path)
    except OSError as error:
        _reject("OUTPUT_ATOMICITY_INVALID", f"cleanup failed: {error}")


def _manifest_id(manifest):
    payload = {name: manifest[name] for name in ROOT_MEMBERS[:-1]}
    return _domain_id(MANIFEST_DOMAIN, payload)


def _build_manifest(
    seed,
    seed_raw,
    contract,
    contract_raw,
    sources,
    semantic,
    semantic_raw,
    comparison,
    comparison_raw,
):
    metric_evidence, f2_records = _derive_metric_records(
        seed, semantic["ordered_metric_summary_records"]
    )
    implementation_rows = []
    for position, label in enumerate(("A", "B", "COMPARATOR"), 1):
        source = sources[label]
        implementation_rows.append(
            {
                "implementation_position": position,
                "implementation_label": label,
                "repository_relative_path": source["relative_path"],
                "raw_octets": source["raw_octets"],
                "raw_sha256": source["raw_sha256"],
                "algorithm_marker": source["algorithm_marker"],
            }
        )
    values = {
        "finalization_manifest_version": MANIFEST_VERSION,
        "finalization_status": FINALIZATION_STATUS,
        "canonicalization_version": CANONICALIZATION_VERSION,
        "protocol_version": seed["protocol_version"],
        "protocol_counting_semantics_id": seed["protocol_counting_semantics_id"],
        "seed_authority": {
            "repository_relative_path": SEED_RELATIVE_PATH,
            "raw_octets": len(seed_raw),
            "raw_sha256": _sha256(seed_raw),
            "catalog_version": seed["catalog_version"],
            "seed_catalog_id": seed["seed_catalog_id"],
        },
        "preflight_contract_authority": {
            "repository_relative_path": CONTRACT_RELATIVE_PATH,
            "raw_octets": len(contract_raw),
            "raw_sha256": _sha256(contract_raw),
            "contract_version": contract["contract_version"],
            "contract_id": contract["contract_id"],
        },
        "ordered_implementation_authorities": implementation_rows,
        "semantic_evidence": {
            "preflight_semantic_payload_version": semantic[
                "preflight_semantic_payload_version"
            ],
            "raw_octets": len(semantic_raw),
            "raw_sha256": _sha256(semantic_raw),
            "semantic_payload_id": semantic["semantic_payload_id"],
            "semantic_count_vector_sha256": semantic["semantic_count_vector_sha256"],
            "ordered_metric_evidence_records": metric_evidence,
        },
        "comparison_evidence": {
            "comparison_payload_version": comparison["comparison_payload_version"],
            "raw_octets": len(comparison_raw),
            "raw_sha256": _sha256(comparison_raw),
            "comparison_payload_id": comparison["comparison_payload_id"],
            "comparison_status": comparison["comparison_status"],
            "implementation_a_raw_sha256": comparison["implementation_a_raw_sha256"],
            "implementation_b_raw_sha256": comparison["implementation_b_raw_sha256"],
            "implementation_a_semantic_payload_id": comparison[
                "implementation_a_semantic_payload_id"
            ],
            "implementation_b_semantic_payload_id": comparison[
                "implementation_b_semantic_payload_id"
            ],
            "semantic_count_vector_sha256": comparison["semantic_count_vector_sha256"],
            "semantic_payload_bytes_equal": comparison["semantic_payload_bytes_equal"],
            "all_475_case_records_equal": comparison["all_475_case_records_equal"],
            "all_18_metric_summaries_equal": comparison[
                "all_18_metric_summaries_equal"
            ],
            "all_resource_limits_satisfied": comparison[
                "all_resource_limits_satisfied"
            ],
        },
        "ordered_f2_limit_records": f2_records,
    }
    manifest = {name: values[name] for name in ROOT_MEMBERS[:-1]}
    manifest["finalization_manifest_id"] = _manifest_id(
        {**manifest, "finalization_manifest_id": ""}
    )
    _validate_manifest_structure(manifest)
    return manifest


def _validate_manifest_structure(manifest):
    _closed_object(manifest, ROOT_MEMBERS, "manifest")
    if (
        manifest["finalization_manifest_version"] != MANIFEST_VERSION
        or manifest["finalization_status"] != FINALIZATION_STATUS
        or manifest["canonicalization_version"] != CANONICALIZATION_VERSION
    ):
        _reject("EVIDENCE_INVALID", "manifest literal differs")
    _closed_object(manifest["seed_authority"], SEED_AUTHORITY_MEMBERS, "seed authority")
    _closed_object(
        manifest["preflight_contract_authority"],
        CONTRACT_AUTHORITY_MEMBERS,
        "contract authority",
    )
    implementations = manifest["ordered_implementation_authorities"]
    if not isinstance(implementations, list) or len(implementations) != 3:
        _reject("EVIDENCE_INVALID", "implementation authority count differs")
    for position, row in enumerate(implementations, 1):
        _closed_object(row, IMPLEMENTATION_AUTHORITY_MEMBERS, f"source {position}")
        if row["implementation_position"] != position:
            _reject("EVIDENCE_INVALID", f"source {position} order differs")
    semantic = manifest["semantic_evidence"]
    _closed_object(semantic, SEMANTIC_EVIDENCE_MEMBERS, "semantic evidence")
    metrics = semantic["ordered_metric_evidence_records"]
    if not isinstance(metrics, list) or len(metrics) != 18:
        _reject("EVIDENCE_INVALID", "metric evidence count differs")
    for position, row in enumerate(metrics, 1):
        _closed_object(row, METRIC_EVIDENCE_MEMBERS, f"metric evidence {position}")
        if row["metric_position"] != position:
            _reject("EVIDENCE_INVALID", f"metric evidence {position} order differs")
    _closed_object(
        manifest["comparison_evidence"],
        COMPARISON_EVIDENCE_MEMBERS,
        "comparison evidence",
    )
    f2_records = manifest["ordered_f2_limit_records"]
    if not isinstance(f2_records, list) or len(f2_records) != 18:
        _reject("EVIDENCE_INVALID", "F2 record count differs")
    for position, row in enumerate(f2_records, 1):
        _closed_object(row, F2_MEMBERS, f"F2 {position}")
        if row["metric_position"] != position:
            _reject("EVIDENCE_INVALID", f"F2 {position} order differs")
        if row["f2_per_case"] != _round_up(
            row["required_per_case"], row["per_case_rounding_unit"]
        ) or row["f2_full_run"] != _round_up(
            row["required_full_run"], row["full_run_rounding_unit"]
        ):
            _reject("EVIDENCE_INVALID", f"F2 {position} derivation differs")
        if (
            not row["required_per_case"]
            <= row["f2_per_case"]
            <= row["per_case_f0_ceiling"]
        ):
            _reject("EVIDENCE_INVALID", f"F2 {position} per-case bound differs")
        if (
            not row["required_full_run"]
            <= row["f2_full_run"]
            <= row["full_run_f0_ceiling"]
        ):
            _reject("EVIDENCE_INVALID", f"F2 {position} full-run bound differs")
    _hex_digest(manifest["finalization_manifest_id"], "manifest ID")
    if manifest["finalization_manifest_id"] != _manifest_id(manifest):
        _reject("EVIDENCE_INVALID", "manifest identity differs")


def _validate_checked_manifest(raw, expected_raw):
    value = _parse_json(raw)
    if raw != _pretty_bytes(value):
        _reject("INPUT_CANONICALIZATION_INVALID", "checked manifest is not canonical")
    _validate_manifest_structure(value)
    if raw != expected_raw:
        _reject("EVIDENCE_INVALID", "checked manifest differs from fresh evidence")
    return value


def _validate_output_parent(parent):
    parent = pathlib.Path(parent)
    if not parent.is_absolute() or os.path.realpath(parent) != str(parent):
        _reject("OUTPUT_ATOMICITY_INVALID", "output parent is noncanonical")
    try:
        status = os.lstat(parent)
    except OSError as error:
        _reject("OUTPUT_ATOMICITY_INVALID", f"output parent check failed: {error}")
    if (
        status.st_mode & 0o170000 != 0o040000
        or status.st_uid != os.getuid()
        or status.st_mode & 0o002
    ):
        _reject("OUTPUT_ATOMICITY_INVALID", "output parent is not owner-controlled")


def _publish_atomic(target, raw):
    target = pathlib.Path(target)
    _validate_output_parent(target.parent)
    temporary = target.parent / f".{target.name}.finalizer.tmp-{os.getpid()}"
    descriptor = None
    created = False
    published = False
    if target.exists() or target.is_symlink():
        _reject("OUTPUT_ATOMICITY_INVALID", "manifest output already exists")
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
                _reject("OUTPUT_ATOMICITY_INVALID", "manifest write made no progress")
            offset += written
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.link(temporary, target, follow_symlinks=False)
        published = True
        os.unlink(temporary)
        created = False
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        directory = os.open(target.parent, directory_flags)
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
            _reject("OUTPUT_ATOMICITY_INVALID", "published manifest metadata differs")
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
        if published and sys.exc_info()[0] is not None:
            try:
                os.unlink(target)
                directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                directory = os.open(target.parent, directory_flags)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            except OSError:
                pass


def _output_path(argument, check):
    target = pathlib.Path(argument)
    if not target.is_absolute() or target.name in {"", ".", ".."}:
        _reject("OUTPUT_ATOMICITY_INVALID", "manifest path is invalid")
    if os.path.realpath(target.parent) != str(target.parent):
        _reject("OUTPUT_ATOMICITY_INVALID", "manifest parent is symlinked")
    _validate_output_parent(target.parent)
    if check:
        if not target.is_file() or target.is_symlink():
            _reject("OUTPUT_ATOMICITY_INVALID", "checked manifest is absent or unsafe")
    elif target.exists() or target.is_symlink():
        _reject("OUTPUT_ATOMICITY_INVALID", "manifest output already exists")
    return target


def _arguments(argv):
    if len(argv) != 2 or argv[0] not in {"--write-manifest", "--check-manifest"}:
        _reject(
            "INVOCATION_INVALID",
            "expected --write-manifest ABSOLUTE_PATH or --check-manifest ABSOLUTE_PATH",
        )
    return argv[0] == "--check-manifest", argv[1]


def _main(argv):
    check, target_argument = _arguments(argv)
    target = _output_path(target_argument, check)
    seed, seed_raw, contract, contract_raw, sources, snapshots = _load_authorities()
    staging = target.parent / f".{target.name}.finalizer-stage-{os.getpid()}"
    try:
        os.mkdir(staging, 0o700)
    except OSError as error:
        _reject("OUTPUT_ATOMICITY_INVALID", f"staging creation failed: {error}")
    try:
        comparator_directory = staging / "comparator"
        a_directory = staging / "a"
        os.mkdir(comparator_directory, 0o700)
        os.mkdir(a_directory, 0o700)
        comparator_arguments = [
            sys.executable,
            "-I",
            "-S",
            "-B",
            str(sources["COMPARATOR"]["path"]),
            "--contract",
            str(ROOT / CONTRACT_RELATIVE_PATH),
            "--comparison-output",
            str(comparator_directory / "comparison.json"),
        ]
        comparison_raw = _run_child(
            "COMPARATOR",
            comparator_arguments,
            comparator_directory,
            "comparison.json",
            contract,
            staging,
        )
        comparison = _validate_comparison_payload(
            comparison_raw, contract, seed, sources
        )
        _verify_authorities_unchanged(snapshots)
        a_arguments = [
            sys.executable,
            "-I",
            "-S",
            "-B",
            str(sources["A"]["path"]),
            "--seed",
            str(ROOT / SEED_RELATIVE_PATH),
            "--semantic-output",
            str(a_directory / "semantic.json"),
        ]
        semantic_raw = _run_child(
            "A",
            a_arguments,
            a_directory,
            "semantic.json",
            contract,
            staging,
        )
        semantic = _validate_semantic_payload(semantic_raw, contract, seed)
        _validate_comparison_payload(
            comparison_raw, contract, seed, sources, semantic=semantic
        )
        manifest = _build_manifest(
            seed,
            seed_raw,
            contract,
            contract_raw,
            sources,
            semantic,
            semantic_raw,
            comparison,
            comparison_raw,
        )
        manifest_raw = _pretty_bytes(manifest)
        if (
            len(manifest_raw)
            >= _limit_map(contract)["INDIVIDUAL_FILE_STRICT_UPPER_OCTETS"]
        ):
            _reject("RESOURCE_LIMIT_EXCEEDED", "manifest exceeds file F0")
        _verify_authorities_unchanged(snapshots)
        _remove_tree(staging)
        if check:
            checked_raw, checked_status = _secure_read(
                target,
                _limit_map(contract)["INDIVIDUAL_FILE_STRICT_UPPER_OCTETS"] - 1,
            )
            if checked_status.st_mode & 0o777 != 0o600:
                _reject("OUTPUT_ATOMICITY_INVALID", "checked manifest mode differs")
            _validate_checked_manifest(checked_raw, manifest_raw)
        else:
            _publish_atomic(target, manifest_raw)
    finally:
        if staging.exists() or staging.is_symlink():
            _remove_tree(staging)


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
    except Exception as error:
        line = f"{ERROR_PREFIX}_INTERNAL_FAIL_CLOSED: {type(error).__name__}\n".encode(
            "ascii", "replace"
        )
        try:
            os.write(2, line)
        except OSError:
            pass
        return EXIT_CODES["INTERNAL_FAIL_CLOSED"]


if __name__ == "__main__":
    raise SystemExit(_entrypoint())
