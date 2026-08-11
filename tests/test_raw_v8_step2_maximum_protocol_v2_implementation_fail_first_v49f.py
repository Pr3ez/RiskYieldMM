"""Independent fail-first contract for S1-A4 constructive implementations.

This A4-T suite freezes the source, CLI, candidate, verified-result, and pilot
surfaces before the verifier, producer, or parent runner exists.  It imports
none of those future implementations.  The intended baseline has exactly
three conformance failures: one for each absent frozen implementation path.
All authority, schema, hostile-fixture, and source-isolation tests must pass;
implementation-dependent tests skip until their corresponding path exists.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
BOUNDARY_PATH = (
    ROOT
    / "scripts/tests/raw_v8_step2_maximum_protocol_v2_constructive_boundary_v49f.json"
)
SEED_PATH = (
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json"
)
MANIFEST_PATH = (
    ROOT
    / "scripts/tests/raw_v8_step2_maximum_protocol_v2_finalization_manifest_v49f.json"
)
BOUNDARY_ID = "bdc7363ae28dfe9a1c1dc132808cb1bd4a06c409201cd49b31e394893142a7ed"
SEED_ID = "ac22151fa74702ac1488924f01161eaa38574545e6272a290db6b0bbd288ae5f"
MANIFEST_ID = "edde204e98ed1caeeb8ae270487d85e39a2168e0a3692ce1d8748d2d8e7fd858"
MANIFEST_SHA256 = "0136fba014287605336193f782b4885f16e0163000d36429ceb0dfaf0cea52e0"
BOUNDARY_DOMAIN = "RiskYieldMMStep2ConstructiveExecutionBoundaryV1V4_9F_RawV8"

ROLE_ORDER = (
    "INDEPENDENT_VERIFIER",
    "SEPARATE_PRODUCER",
    "PARENT_PILOT_RUNNER",
)
ROLE_PATHS = {
    "INDEPENDENT_VERIFIER": (
        ROOT / "scripts/tests/verify_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py"
    ),
    "SEPARATE_PRODUCER": (
        ROOT
        / "scripts/tests/produce_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py"
    ),
    "PARENT_PILOT_RUNNER": (
        ROOT / "scripts/tests/run_raw_v8_step2_maximum_protocol_v2_pilot_v49f.py"
    ),
}
ROLE_MARKERS = {
    "INDEPENDENT_VERIFIER": "INDEPENDENT_V2_CONSTRUCTIVE_VERIFIER_V1",
    "SEPARATE_PRODUCER": "SEPARATE_V2_CONSTRUCTIVE_PRODUCER_V1",
    "PARENT_PILOT_RUNNER": "PARENT_OWNED_V2_CONSTRUCTIVE_PILOT_RUNNER_V1",
}
ROLE_FAILURE_CODES = {
    "INDEPENDENT_VERIFIER": "A4_T_INDEPENDENT_VERIFIER_MISSING",
    "SEPARATE_PRODUCER": "A4_T_SEPARATE_PRODUCER_MISSING",
    "PARENT_PILOT_RUNNER": "A4_T_PARENT_PILOT_RUNNER_MISSING",
}
ROLE_ERROR_PREFIXES = {
    "INDEPENDENT_VERIFIER": (
        "RAW_V8_STEP2_MAXIMUM_PROTOCOL_V2_VERIFIER_INVOCATION_INVALID: "
    ),
    "SEPARATE_PRODUCER": (
        "RAW_V8_STEP2_MAXIMUM_PROTOCOL_V2_PRODUCER_INVOCATION_INVALID: "
    ),
    "PARENT_PILOT_RUNNER": (
        "RAW_V8_STEP2_MAXIMUM_PROTOCOL_V2_PILOT_RUNNER_INVOCATION_INVALID: "
    ),
}


class ContractReject(ValueError):
    """Independent A4-T contract rejection."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractReject(message)


def _duplicate_key_guard(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        _require(key not in value, f"duplicate key {key}")
        value[key] = item
    return value


def _reject_float(value: str) -> Any:
    raise ContractReject(f"floating or non-finite number {value}")


def _strict_loads(raw: bytes) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8", errors="strict")
        _require(not text.startswith("\ufeff"), "BOM")
        value = json.loads(
            text,
            object_pairs_hook=_duplicate_key_guard,
            parse_float=_reject_float,
            parse_constant=_reject_float,
        )
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ContractReject("strict JSON") from error
    _require(type(value) is dict, "root object")
    return value


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _pretty_bytes(value: Any) -> bytes:
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


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _semantic_id(domain: str, payload: Any) -> str:
    return _sha256(_canonical_bytes({"domain": domain, "payload": payload}))


def _closed(value: Any, names: list[str], label: str) -> dict[str, Any]:
    _require(type(value) is dict, f"{label} object")
    _require(set(value) == set(names), f"{label} closed members")
    return value


def _sha(value: Any, label: str) -> str:
    _require(
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value),
        f"{label} SHA-256",
    )
    return value


def _load_authorities() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    boundary_raw = BOUNDARY_PATH.read_bytes()
    seed_raw = SEED_PATH.read_bytes()
    manifest_raw = MANIFEST_PATH.read_bytes()
    boundary = _strict_loads(boundary_raw)
    seed = _strict_loads(seed_raw)
    manifest = _strict_loads(manifest_raw)

    _require(
        boundary["constructive_boundary_id"] == BOUNDARY_ID,
        "boundary identity",
    )
    boundary_payload = {
        name: value
        for name, value in boundary.items()
        if name != "constructive_boundary_id"
    }
    _require(
        _semantic_id(BOUNDARY_DOMAIN, boundary_payload) == BOUNDARY_ID,
        "recomputed boundary identity",
    )
    _require(seed["seed_catalog_id"] == SEED_ID, "seed identity")
    _require(manifest["finalization_manifest_id"] == MANIFEST_ID, "manifest identity")
    _require(_sha256(manifest_raw) == MANIFEST_SHA256, "manifest physical identity")

    authority = boundary["authority_contract"]
    _require(
        authority["seed_authority"]["raw_sha256"] == _sha256(seed_raw),
        "boundary seed hash",
    )
    _require(
        authority["finalization_manifest_authority"]["raw_sha256"] == MANIFEST_SHA256,
        "boundary manifest hash",
    )
    _require(
        authority["downstream_field_binding_rules"]["maximum_protocol_sha256"]
        == "FINALIZATION_MANIFEST_AUTHORITY_RAW_SHA256",
        "downstream two-component mapping",
    )

    roles = boundary["implementation_role_contract"]["ordered_role_records"]
    _require(
        tuple(row["role_name"] for row in roles) == ROLE_ORDER,
        "role order",
    )
    for row in roles:
        name = row["role_name"]
        _require(
            ROOT / row["repository_relative_path"] == ROLE_PATHS[name],
            f"{name} path",
        )
        _require(row["source_marker"] == ROLE_MARKERS[name], f"{name} marker")
    return boundary, seed, manifest


def _seed_maps(seed: dict[str, Any]) -> tuple[dict[int, Any], dict[int, Any]]:
    cases = {
        row["case_position"]: row
        for row in seed["case_universe_catalog"]["ordered_case_bindings"]
    }
    plans = {
        row["case_position"]: row
        for row in seed["logical_plan_recipe_catalog"][
            "ordered_logical_count_plan_records"
        ]
    }
    return cases, plans


def _contains_forbidden_member(value: Any, forbidden: set[str]) -> bool:
    if type(value) is dict:
        return any(
            key in forbidden or _contains_forbidden_member(item, forbidden)
            for key, item in value.items()
        )
    if type(value) is list:
        return any(_contains_forbidden_member(item, forbidden) for item in value)
    return False


def _fixture_candidate(case_position: int) -> dict[str, Any]:
    boundary, seed, manifest = _load_authorities()
    cases, plans = _seed_maps(seed)
    case = cases[case_position]
    if case["case_kind"] == "MAXIMUM_PUBLICATION_ROW":
        payload = {
            "candidate_kind": "MAXIMUM_WITNESS_CONTEXT",
            "witness_record": (
                {"kind": "BOOL", "value": False} if case_position == 5 else {}
            ),
            "scope_witness_context": None,
            "ordered_context_object_entries": [],
        }
    else:
        payload = {
            "candidate_kind": "LOCAL_SHUTDOWN_MUTATION",
            "mutated_spec": {},
            "prospective_result": {},
        }
    candidate = {
        "candidate_version": boundary["candidate_bundle_contract"][
            "candidate_envelope_schema"
        ]["version_literal"],
        "canonicalization_version": boundary["canonicalization_version"],
        "measurement_schema_version": boundary["measurement_schema_version"],
        "protocol_version": boundary["protocol_version"],
        "seed_catalog_id": seed["seed_catalog_id"],
        "finalization_manifest_id": manifest["finalization_manifest_id"],
        "case_position": case_position,
        "case_kind": case["case_kind"],
        "case_binding": copy.deepcopy(case["case_binding"]),
        "logical_count_plan_id": plans[case_position]["logical_count_plan_id"],
        "candidate_payload": payload,
    }
    schema = boundary["candidate_bundle_contract"]["candidate_envelope_schema"]
    candidate["constructive_candidate_id"] = _semantic_id(
        schema["identity_domain"], candidate
    )
    return candidate


def _validate_candidate(candidate: dict[str, Any]) -> None:
    boundary, seed, manifest = _load_authorities()
    contract = boundary["candidate_bundle_contract"]
    schema = contract["candidate_envelope_schema"]
    _closed(candidate, schema["ordered_member_names"], "candidate")
    _require(candidate["candidate_version"] == schema["version_literal"], "version")
    _require(
        candidate["canonicalization_version"] == boundary["canonicalization_version"],
        "canonicalization",
    )
    _require(candidate["protocol_version"] == boundary["protocol_version"], "protocol")
    _require(candidate["seed_catalog_id"] == seed["seed_catalog_id"], "seed")
    _require(
        candidate["finalization_manifest_id"] == manifest["finalization_manifest_id"],
        "manifest",
    )
    cases, plans = _seed_maps(seed)
    position = candidate["case_position"]
    _require(type(position) is int and position in cases, "case position")
    case = cases[position]
    _require(candidate["case_kind"] == case["case_kind"], "case kind")
    _require(candidate["case_binding"] == case["case_binding"], "case binding")
    _require(
        candidate["logical_count_plan_id"] == plans[position]["logical_count_plan_id"],
        "logical plan",
    )

    payload = candidate["candidate_payload"]
    alternatives = contract["candidate_payload_tagged_union"][
        "ordered_alternative_records"
    ]
    by_kind = {row["candidate_kind"]: row for row in alternatives}
    _require(type(payload) is dict, "payload object")
    kind = payload.get("candidate_kind")
    _require(kind in by_kind, "candidate tag")
    alternative = by_kind[kind]
    _closed(payload, alternative["ordered_member_names"], "candidate payload")
    _require(case["case_kind"] == alternative["required_case_kind"], "tag case kind")
    forbidden = set(contract["forbidden_producer_claim_member_names"])
    _require(not _contains_forbidden_member(candidate, forbidden), "producer claim")

    if kind == "MAXIMUM_WITNESS_CONTEXT":
        _require(type(payload["witness_record"]) is dict, "witness record")
        _require(
            payload["scope_witness_context"] is None
            or type(payload["scope_witness_context"]) is dict,
            "scope context",
        )
        context_schema = contract["context_object_entry_schema"]
        entries = payload["ordered_context_object_entries"]
        _require(type(entries) is list, "context entries")
        previous_id: str | None = None
        for expected_position, row in enumerate(entries, 1):
            _closed(row, context_schema["ordered_member_names"], "context entry")
            _require(
                row["context_object_position"] == expected_position,
                "context position",
            )
            object_id = _sha(row["claimed_maximum_context_object_id"], "context ID")
            _require(previous_id is None or previous_id < object_id, "context order")
            expected_path = f"context_objects/{object_id[:2]}/{object_id}.json"
            _require(row["repository_relative_path"] == expected_path, "context path")
            _require(
                type(row["raw_octet_count"]) is int and row["raw_octet_count"] >= 0,
                "context size",
            )
            _sha(row["raw_sha256"], "context hash")
            previous_id = object_id
    else:
        _require(type(payload["mutated_spec"]) is dict, "mutated spec")
        _require(type(payload["prospective_result"]) is dict, "prospective result")

    identity_payload = {
        name: candidate[name] for name in schema["ordered_member_names"][:-1]
    }
    _require(
        candidate["constructive_candidate_id"]
        == _semantic_id(schema["identity_domain"], identity_payload),
        "candidate identity",
    )


def _certificate(boundary: dict[str, Any]) -> dict[str, Any]:
    schema = boundary["verifier_output_contract"]["upper_bound_certificate_schema"]
    value = {
        "certificate_version": schema["version_literal"],
        "maximum_protocol_sha256": MANIFEST_SHA256,
        "derivation_scope_id": "1" * 64,
        "upper_bound_mode": "EXACT_TYPED_FRONTIER",
        "derivation_catalog_id": "2" * 64,
        "derivation_plan_id": "3" * 64,
        "ordered_safe_relaxation_rule_ids": [],
        "certified_upper_bound_octets": 1,
        "streamed_derivation_result_sha256": "4" * 64,
    }
    value["upper_bound_certificate_id"] = _semantic_id(schema["identity_domain"], value)
    return value


def _resource_report(boundary: dict[str, Any], certificate_id: str) -> dict[str, Any]:
    schema = boundary["verifier_output_contract"]["proof_resource_report_schema"]
    manifest = _strict_loads(MANIFEST_PATH.read_bytes())
    value = {
        "resource_report_version": schema["version_literal"],
        "maximum_protocol_sha256": MANIFEST_SHA256,
        "derivation_scope_id": "1" * 64,
        "derivation_plan_id": "3" * 64,
        "derivation_certificate_id": certificate_id,
        "resource_limit_catalog_id": boundary["authority_contract"][
            "f2_resource_limit_catalog"
        ]["f2_resource_limit_catalog_id"],
        "ordered_resource_measurements": [
            {
                "metric_position": row["metric_position"],
                "metric_name": row["metric_name"],
                "measured_value": 0,
            }
            for row in manifest["ordered_f2_limit_records"]
        ],
    }
    value["proof_resource_report_id"] = _semantic_id(schema["identity_domain"], value)
    return value


def _fixture_result(kind: str) -> dict[str, Any]:
    boundary, _seed, _manifest = _load_authorities()
    output = boundary["verifier_output_contract"]
    if kind == "maximum":
        schema = output["maximum_attainer_schema"]
        certificate = _certificate(boundary)
        report = _resource_report(boundary, certificate["upper_bound_certificate_id"])
        value = dict.fromkeys(schema["ordered_member_names"][:-1])
        value.update(
            {
                "artifact_version": schema["version_literal"],
                "canonicalization_version": boundary["canonicalization_version"],
                "measurement_schema_version": boundary["measurement_schema_version"],
                "maximum_protocol_sha256": MANIFEST_SHA256,
                "source_inventory_sha256": "5" * 64,
                "external_schema_registry_id": "6" * 64,
                "rule_literal_authority_sha256": "7" * 64,
                "witness_kind": schema["witness_kind"],
                "canonical_byte_length": 1,
                "certified_analytic_maximum_octets": 1,
                "codec_slack_octets": 0,
                "canonical_sha256": "8" * 64,
                "witness_record": {},
                "scope_witness_context": None,
                "required_context_object_count": 0,
                "ordered_required_context_object_ids": [],
                "upper_bound_certificate": certificate,
                "proof_resource_report": report,
            }
        )
        value["maximum_attainer_id"] = _semantic_id(schema["identity_domain"], value)
        return value

    _require(kind == "local", "result fixture kind")
    schema = output["local_shutdown_result_schema"]
    report = _resource_report(boundary, "9" * 64)
    value = dict.fromkeys(schema["ordered_member_names"][:-1])
    value.update(
        {
            "artifact_version": schema["version_literal"],
            "canonicalization_version": boundary["canonicalization_version"],
            "measurement_schema_version": boundary["measurement_schema_version"],
            "maximum_protocol_sha256": MANIFEST_SHA256,
            "source_inventory_sha256": "5" * 64,
            "external_schema_registry_id": "6" * 64,
            "rule_literal_authority_sha256": "7" * 64,
            "mutated_limit_members": [],
            "mutated_spec": {},
            "changed_limit_field_count": 1,
            "sum_absolute_integer_deltas": 1,
            "prospective_result": {},
            "prospective_result_canonical_byte_length": 1,
            "expected_rejection_coordinate": {},
            "minimality_certificate": {},
            "proof_resource_report": report,
        }
    )
    value["local_shutdown_unrepresentable_id"] = _semantic_id(
        schema["identity_domain"], value
    )
    return value


def _validate_result(kind: str, value: dict[str, Any]) -> None:
    boundary, _seed, manifest = _load_authorities()
    output = boundary["verifier_output_contract"]
    if kind == "maximum":
        schema = output["maximum_attainer_schema"]
        id_name = "maximum_attainer_id"
        _require(value.get("witness_kind") == schema["witness_kind"], "witness kind")
        certificate = _closed(
            value.get("upper_bound_certificate"),
            output["upper_bound_certificate_schema"]["ordered_member_names"],
            "upper-bound certificate",
        )
        forbidden = set(
            output["upper_bound_certificate_schema"]["forbidden_member_names"]
        )
        _require(
            not forbidden.intersection(certificate), "forbidden certificate member"
        )
        certificate_payload = {
            name: certificate[name]
            for name in output["upper_bound_certificate_schema"][
                "ordered_member_names"
            ][:-1]
        }
        _require(
            certificate["upper_bound_certificate_id"]
            == _semantic_id(
                output["upper_bound_certificate_schema"]["identity_domain"],
                certificate_payload,
            ),
            "certificate identity",
        )
    else:
        _require(kind == "local", "result kind")
        schema = output["local_shutdown_result_schema"]
        id_name = "local_shutdown_unrepresentable_id"

    _closed(value, schema["ordered_member_names"], f"{kind} result")
    _require(value["artifact_version"] == schema["version_literal"], "result version")
    _require(value["maximum_protocol_sha256"] == MANIFEST_SHA256, "protocol hash")
    report_schema = output["proof_resource_report_schema"]
    report = _closed(
        value["proof_resource_report"],
        report_schema["ordered_member_names"],
        "resource report",
    )
    report_payload = {
        name: report[name] for name in report_schema["ordered_member_names"][:-1]
    }
    _require(
        report["proof_resource_report_id"]
        == _semantic_id(report_schema["identity_domain"], report_payload),
        "resource report identity",
    )
    measurements = report["ordered_resource_measurements"]
    limit_rows = manifest["ordered_f2_limit_records"]
    _require(
        type(measurements) is list and len(measurements) == len(limit_rows) == 18,
        "resource measurement count",
    )
    for measurement, limit in zip(measurements, limit_rows, strict=True):
        _closed(
            measurement,
            ["metric_position", "metric_name", "measured_value"],
            "resource measurement",
        )
        _require(
            measurement["metric_position"] == limit["metric_position"],
            "resource metric position",
        )
        _require(
            measurement["metric_name"] == limit["metric_name"],
            "resource metric name",
        )
        measured = measurement["measured_value"]
        _require(
            type(measured) is int and 0 <= measured <= limit["f2_per_case"],
            "resource metric F2 limit",
        )
    payload = {name: value[name] for name in schema["ordered_member_names"][:-1]}
    _require(
        value[id_name] == _semantic_id(schema["identity_domain"], payload),
        "result identity",
    )


def _fixture_receipt(kind: str) -> tuple[dict[str, Any], bytes, dict[str, Any], bytes]:
    boundary, seed, manifest = _load_authorities()
    case_position = 5 if kind == "maximum" else 475
    candidate = _fixture_candidate(case_position)
    candidate_raw = _pretty_bytes(candidate)
    result = _fixture_result(kind)
    result_raw = _pretty_bytes(result)
    cases, plans = _seed_maps(seed)
    schema = boundary["verifier_output_contract"]["verification_receipt_schema"]
    result_id_name = (
        "maximum_attainer_id"
        if kind == "maximum"
        else "local_shutdown_unrepresentable_id"
    )
    result_path = (
        boundary["verifier_output_contract"]["verified_bundle_paths"]["maximum_result"]
        if kind == "maximum"
        else boundary["verifier_output_contract"]["verified_bundle_paths"][
            "local_result"
        ]
    )
    receipt = {
        "receipt_version": schema["version_literal"],
        "canonicalization_version": boundary["canonicalization_version"],
        "protocol_version": boundary["protocol_version"],
        "seed_catalog_id": seed["seed_catalog_id"],
        "finalization_manifest_id": manifest["finalization_manifest_id"],
        "case_position": case_position,
        "case_kind": cases[case_position]["case_kind"],
        "case_binding": copy.deepcopy(cases[case_position]["case_binding"]),
        "logical_count_plan_id": plans[case_position]["logical_count_plan_id"],
        "constructive_candidate_id": candidate["constructive_candidate_id"],
        "candidate_raw_octets": len(candidate_raw),
        "candidate_raw_sha256": _sha256(candidate_raw),
        "verification_status": (
            schema["maximum_status"] if kind == "maximum" else schema["local_status"]
        ),
        "result_artifact_kind": (
            "MAXIMUM_ATTAINER" if kind == "maximum" else "LOCAL_SHUTDOWN_RESULT"
        ),
        "result_artifact_id": result[result_id_name],
        "result_repository_relative_path": result_path,
        "result_raw_octets": len(result_raw),
        "result_raw_sha256": _sha256(result_raw),
        "ordered_verified_context_object_entries": [],
    }
    receipt["verification_receipt_id"] = _semantic_id(
        schema["identity_domain"], receipt
    )
    return receipt, candidate_raw, result, result_raw


def _validate_receipt(
    kind: str,
    receipt: dict[str, Any],
    candidate_raw: bytes,
    result: dict[str, Any],
    result_raw: bytes,
) -> None:
    boundary, seed, manifest = _load_authorities()
    output = boundary["verifier_output_contract"]
    schema = output["verification_receipt_schema"]
    _closed(receipt, schema["ordered_member_names"], "verification receipt")
    _require(receipt["receipt_version"] == schema["version_literal"], "receipt version")
    _require(
        receipt["protocol_version"] == boundary["protocol_version"], "receipt protocol"
    )
    _require(receipt["seed_catalog_id"] == seed["seed_catalog_id"], "receipt seed")
    _require(
        receipt["finalization_manifest_id"] == manifest["finalization_manifest_id"],
        "receipt manifest",
    )
    expected_position = 5 if kind == "maximum" else 475
    cases, plans = _seed_maps(seed)
    _require(receipt["case_position"] == expected_position, "receipt case position")
    _require(
        receipt["case_kind"] == cases[expected_position]["case_kind"],
        "receipt case kind",
    )
    _require(
        receipt["case_binding"] == cases[expected_position]["case_binding"],
        "receipt case binding",
    )
    _require(
        receipt["logical_count_plan_id"]
        == plans[expected_position]["logical_count_plan_id"],
        "receipt plan",
    )
    candidate = _strict_loads(candidate_raw)
    _validate_candidate(candidate)
    _require(
        receipt["constructive_candidate_id"] == candidate["constructive_candidate_id"],
        "receipt candidate ID",
    )
    _require(receipt["candidate_raw_octets"] == len(candidate_raw), "candidate size")
    _require(
        receipt["candidate_raw_sha256"] == _sha256(candidate_raw), "candidate hash"
    )
    _validate_result(kind, result)
    result_id_name = (
        "maximum_attainer_id"
        if kind == "maximum"
        else "local_shutdown_unrepresentable_id"
    )
    expected_status = (
        schema["maximum_status"] if kind == "maximum" else schema["local_status"]
    )
    expected_path = (
        output["verified_bundle_paths"]["maximum_result"]
        if kind == "maximum"
        else output["verified_bundle_paths"]["local_result"]
    )
    _require(receipt["verification_status"] == expected_status, "receipt status")
    _require(
        receipt["result_artifact_id"] == result[result_id_name], "receipt result ID"
    )
    _require(
        receipt["result_repository_relative_path"] == expected_path,
        "receipt result path",
    )
    _require(receipt["result_raw_octets"] == len(result_raw), "result size")
    _require(receipt["result_raw_sha256"] == _sha256(result_raw), "result hash")
    _require(
        receipt["ordered_verified_context_object_entries"] == [], "receipt contexts"
    )
    payload = {name: receipt[name] for name in schema["ordered_member_names"][:-1]}
    _require(
        receipt["verification_receipt_id"]
        == _semantic_id(schema["identity_domain"], payload),
        "receipt identity",
    )


def _fixture_pilot_manifest() -> dict[str, Any]:
    boundary, seed, manifest = _load_authorities()
    pilot = boundary["pilot_contract"]
    schema = pilot["pilot_manifest_schema"]
    role_rows = boundary["implementation_role_contract"]["ordered_role_records"]

    def authority(row: dict[str, Any]) -> dict[str, Any]:
        raw = _source_fixture(row["role_name"])
        return {
            "repository_relative_path": row["repository_relative_path"],
            "raw_octets": len(raw),
            "raw_sha256": _sha256(raw),
            "source_marker": row["source_marker"],
        }

    entries = []
    for row in pilot["ordered_pilot_case_records"]:
        position = row["pilot_position"]
        entries.append(
            {
                "pilot_position": position,
                "case_position": row["case_position"],
                "case_kind": row["case_kind"],
                "logical_count_plan_id": row["logical_count_plan_id"],
                "constructive_candidate_id": f"{position:064x}",
                "candidate_root_raw_octets": position,
                "candidate_root_sha256": f"{position + 10:064x}",
                "verification_receipt_id": f"{position + 20:064x}",
                "verified_result_artifact_id": f"{position + 30:064x}",
                "verified_result_root_raw_octets": position + 100,
                "verified_result_root_sha256": f"{position + 40:064x}",
            }
        )
    value = {
        "pilot_version": pilot["pilot_version"],
        "canonicalization_version": boundary["canonicalization_version"],
        "protocol_version": boundary["protocol_version"],
        "seed_catalog_id": seed["seed_catalog_id"],
        "finalization_manifest_id": manifest["finalization_manifest_id"],
        "producer_authority": authority(role_rows[1]),
        "verifier_authority": authority(role_rows[0]),
        "runner_authority": authority(role_rows[2]),
        "ordered_case_result_entries": entries,
        "pilot_status": pilot["pilot_status"],
    }
    value["constructive_pilot_manifest_id"] = _semantic_id(
        schema["identity_domain"], value
    )
    return value


def _validate_pilot_manifest(value: dict[str, Any]) -> None:
    boundary, seed, manifest = _load_authorities()
    pilot = boundary["pilot_contract"]
    schema = pilot["pilot_manifest_schema"]
    _closed(value, schema["ordered_member_names"], "pilot manifest")
    _require(value["pilot_version"] == pilot["pilot_version"], "pilot version")
    _require(
        value["protocol_version"] == boundary["protocol_version"], "pilot protocol"
    )
    _require(value["seed_catalog_id"] == seed["seed_catalog_id"], "pilot seed")
    _require(
        value["finalization_manifest_id"] == manifest["finalization_manifest_id"],
        "pilot manifest authority",
    )
    _require(value["pilot_status"] == pilot["pilot_status"], "pilot status")

    roles = {
        row["role_name"]: row
        for row in boundary["implementation_role_contract"]["ordered_role_records"]
    }
    authorities = (
        ("producer_authority", roles["SEPARATE_PRODUCER"]),
        ("verifier_authority", roles["INDEPENDENT_VERIFIER"]),
        ("runner_authority", roles["PARENT_PILOT_RUNNER"]),
    )
    seen_paths: set[str] = set()
    seen_hashes: set[str] = set()
    for member, expected in authorities:
        authority = _closed(
            value[member],
            schema["implementation_authority_ordered_member_names"],
            member,
        )
        _require(
            authority["repository_relative_path"]
            == expected["repository_relative_path"],
            f"{member} path",
        )
        _require(
            authority["source_marker"] == expected["source_marker"], f"{member} marker"
        )
        _require(
            type(authority["raw_octets"]) is int and authority["raw_octets"] > 0,
            f"{member} size",
        )
        source_hash = _sha(authority["raw_sha256"], f"{member} hash")
        _require(
            authority["repository_relative_path"] not in seen_paths,
            "role path collision",
        )
        _require(source_hash not in seen_hashes, "role hash collision")
        seen_paths.add(authority["repository_relative_path"])
        seen_hashes.add(source_hash)

    expected_rows = pilot["ordered_pilot_case_records"]
    rows = value["ordered_case_result_entries"]
    _require(
        type(rows) is list and len(rows) == len(expected_rows) == 6, "pilot row count"
    )
    for expected, row in zip(expected_rows, rows, strict=True):
        _closed(
            row, schema["case_result_entry_ordered_member_names"], "pilot case result"
        )
        for name in (
            "pilot_position",
            "case_position",
            "case_kind",
            "logical_count_plan_id",
        ):
            _require(row[name] == expected[name], f"pilot {name}")
        for name in (
            "constructive_candidate_id",
            "candidate_root_sha256",
            "verification_receipt_id",
            "verified_result_artifact_id",
            "verified_result_root_sha256",
        ):
            _sha(row[name], f"pilot {name}")
        for name in ("candidate_root_raw_octets", "verified_result_root_raw_octets"):
            _require(type(row[name]) is int and row[name] > 0, f"pilot {name}")

    payload = {name: value[name] for name in schema["ordered_member_names"][:-1]}
    _require(
        value["constructive_pilot_manifest_id"]
        == _semantic_id(schema["identity_domain"], payload),
        "pilot identity",
    )


def _source_fixture(role_name: str) -> bytes:
    marker = ROLE_MARKERS[role_name]
    if role_name == "PARENT_PILOT_RUNNER":
        body = (
            "import os\nimport resource\n"
            f"SOURCE_MARKER = {marker!r}\n"
            "def _launch(path, argv, env):\n"
            "    pid = os.fork()\n"
            "    if pid == 0:\n"
            "        resource.setrlimit(resource.RLIMIT_CPU, (1, 1))\n"
            "        os.execve(path, argv, env)\n"
            "    return os.wait4(pid, 0)\n"
        )
    else:
        body = (
            "import hashlib\nimport json\nimport os\nimport pathlib\nimport sys\n"
            f"SOURCE_MARKER = {marker!r}\n"
            "def _main():\n    return 2\n"
        )
    return body.encode("utf-8")


def _source_surface(role_name: str, raw: bytes) -> None:
    boundary, _seed, manifest = _load_authorities()
    try:
        source = raw.decode("utf-8", errors="strict")
        tree = ast.parse(source)
    except (UnicodeError, SyntaxError) as error:
        raise ContractReject("source syntax") from error

    marker = ROLE_MARKERS[role_name]
    string_constants = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and type(node.value) is str
    }
    _require(marker in string_constants, "source marker")
    for other_name, other_marker in ROLE_MARKERS.items():
        if other_name != role_name:
            _require(other_marker not in source, "other role marker")

    imports: set[str] = set()
    calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            _require(node.level == 0 and node.module is not None, "relative import")
            imports.add(node.module.split(".", 1)[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)

    independence = boundary["independence_contract"]
    allowed = set(independence["allowed_standard_library_import_roots"])
    forbidden = set(independence["forbidden_import_roots"])
    _require(imports <= allowed, "non-allowlisted import")
    _require(imports.isdisjoint(forbidden), "forbidden import")
    _require(
        calls.isdisjoint({"__import__", "compile", "eval", "exec"}),
        "dynamic code",
    )
    _require(calls.isdisjoint({"system", "popen", "spawnl", "spawnv"}), "shell")

    verifier_path = str(ROLE_PATHS["INDEPENDENT_VERIFIER"].relative_to(ROOT))
    producer_path = str(ROLE_PATHS["SEPARATE_PRODUCER"].relative_to(ROOT))
    if role_name == "INDEPENDENT_VERIFIER":
        _require(producer_path not in source, "verifier reads producer")
        _require(
            calls.isdisjoint({"fork", "execve", "wait4", "setrlimit"}),
            "verifier process control",
        )
    elif role_name == "SEPARATE_PRODUCER":
        _require(verifier_path not in source, "producer reads verifier")
        _require(
            calls.isdisjoint({"fork", "execve", "wait4", "setrlimit"}),
            "producer process control",
        )
        forbidden_claims = set(
            boundary["candidate_bundle_contract"][
                "forbidden_producer_claim_member_names"
            ]
        )
        _require(string_constants.isdisjoint(forbidden_claims), "producer proof claim")
        f2_values = {
            row[name]
            for row in manifest["ordered_f2_limit_records"]
            for name in ("f2_per_case", "f2_full_run")
            if row[name] > 65_536
        }
        integers = {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and type(node.value) is int
        }
        _require(integers.isdisjoint(f2_values), "producer hard-coded F2 answer")
    else:
        _require(
            {"fork", "execve", "wait4", "setrlimit"} <= calls,
            "runner fixed process primitives",
        )


def _publish_candidate_fixture(root: Path, candidate: dict[str, Any]) -> bytes:
    _require(not root.exists(), "candidate fixture root already exists")
    root.mkdir(mode=0o700)
    (root / "context_objects").mkdir(mode=0o700)
    raw = _pretty_bytes(candidate)
    (root / "candidate.json").write_bytes(raw)
    return raw


def _isolated_environment() -> dict[str, str]:
    return {
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
    }


def _run_verifier(
    candidate_root: Path, output_root: Path
) -> subprocess.CompletedProcess[bytes]:
    path = _implemented_path_or_skip("INDEPENDENT_VERIFIER")
    return subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            str(path),
            "--repository-root",
            str(ROOT),
            "--boundary",
            str(BOUNDARY_PATH),
            "--candidate-root",
            str(candidate_root),
            "--output-root",
            str(output_root),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        env=_isolated_environment(),
    )


def _reseal_candidate(value: dict[str, Any]) -> None:
    boundary, _seed, _manifest = _load_authorities()
    schema = boundary["candidate_bundle_contract"]["candidate_envelope_schema"]
    payload = {name: value[name] for name in schema["ordered_member_names"][:-1]}
    value["constructive_candidate_id"] = _semantic_id(
        schema["identity_domain"], payload
    )


def _mutate_candidate_extra(value: dict[str, Any]) -> None:
    value["accepted"] = True


def _mutate_candidate_id(value: dict[str, Any]) -> None:
    value["constructive_candidate_id"] = "0" * 64


def _mutate_candidate_plan(value: dict[str, Any]) -> None:
    value["logical_count_plan_id"] = "0" * 64


def _mutate_candidate_binding(value: dict[str, Any]) -> None:
    value["case_binding"] = {}


def _mutate_candidate_tag(value: dict[str, Any]) -> None:
    value["candidate_payload"]["candidate_kind"] = "PRODUCER_CERTIFIED_MAXIMUM"


def _mutate_candidate_claim(value: dict[str, Any]) -> None:
    value["candidate_payload"]["upper_bound_certificate"] = {}


def _mutate_candidate_authority(value: dict[str, Any]) -> None:
    value["finalization_manifest_id"] = "0" * 64


def _mutate_result_missing_report(value: dict[str, Any]) -> None:
    del value["proof_resource_report"]


def _mutate_result_protocol(value: dict[str, Any]) -> None:
    value["maximum_protocol_sha256"] = "0" * 64


def _mutate_result_id(value: dict[str, Any]) -> None:
    id_name = (
        "maximum_attainer_id"
        if "maximum_attainer_id" in value
        else "local_shutdown_unrepresentable_id"
    )
    value[id_name] = "0" * 64


def _mutate_receipt_candidate_hash(value: dict[str, Any]) -> None:
    value["candidate_raw_sha256"] = "0" * 64


def _mutate_receipt_status(value: dict[str, Any]) -> None:
    value["verification_status"] = "PRODUCER_ASSERTED_PASS"


def _mutate_receipt_result_path(value: dict[str, Any]) -> None:
    value["result_repository_relative_path"] = "../escape.json"


def _mutate_receipt_extra(value: dict[str, Any]) -> None:
    value["producer_diagnostic"] = "accepted"


def _mutate_receipt_id(value: dict[str, Any]) -> None:
    value["verification_receipt_id"] = "0" * 64


def _mutate_pilot_duplicate_case(value: dict[str, Any]) -> None:
    value["ordered_case_result_entries"][5]["case_position"] = value[
        "ordered_case_result_entries"
    ][4]["case_position"]


def _mutate_pilot_plan(value: dict[str, Any]) -> None:
    value["ordered_case_result_entries"][0]["logical_count_plan_id"] = "0" * 64


def _mutate_pilot_role_collision(value: dict[str, Any]) -> None:
    value["producer_authority"] = copy.deepcopy(value["verifier_authority"])


def _mutate_pilot_status(value: dict[str, Any]) -> None:
    value["pilot_status"] = "PUBLICATION_AUTHORIZED"


def _mutate_pilot_extra(value: dict[str, Any]) -> None:
    value["accepted_maxima"] = 6


def _mutate_pilot_id(value: dict[str, Any]) -> None:
    value["constructive_pilot_manifest_id"] = "0" * 64


def _hostile_candidate_bad_identity(value: dict[str, Any]) -> None:
    value["constructive_candidate_id"] = "0" * 64


def _hostile_candidate_resealed_claim(value: dict[str, Any]) -> None:
    value["candidate_payload"]["upper_bound_certificate"] = {}
    _reseal_candidate(value)


def _hostile_candidate_resealed_binding(value: dict[str, Any]) -> None:
    value["case_binding"]["row_position"] = 6
    _reseal_candidate(value)


def test_a4_t_authority_and_role_contract_is_exact() -> None:
    boundary, seed, manifest = _load_authorities()
    assert seed["seed_catalog_id"] == SEED_ID
    assert manifest["finalization_manifest_id"] == MANIFEST_ID
    assert boundary["constructive_boundary_id"] == BOUNDARY_ID


@pytest.mark.parametrize("case_position", [5, 475])
def test_candidate_shape_fixtures_are_closed(case_position: int) -> None:
    _validate_candidate(_fixture_candidate(case_position))


@pytest.mark.parametrize(
    "mutation",
    [
        _mutate_candidate_extra,
        _mutate_candidate_id,
        _mutate_candidate_plan,
        _mutate_candidate_binding,
        _mutate_candidate_tag,
        _mutate_candidate_claim,
        _mutate_candidate_authority,
    ],
    ids=lambda function: function.__name__.removeprefix("_mutate_candidate_"),
)
def test_candidate_oracle_rejects_hostile_mutations(
    mutation: Callable[[dict[str, Any]], None],
) -> None:
    value = _fixture_candidate(5)
    mutation(value)
    with pytest.raises(ContractReject):
        _validate_candidate(value)


@pytest.mark.parametrize("kind", ["maximum", "local"])
def test_verifier_result_shape_fixtures_are_closed(kind: str) -> None:
    _validate_result(kind, _fixture_result(kind))


@pytest.mark.parametrize(
    ("kind", "mutation"),
    [
        ("maximum", _mutate_result_missing_report),
        ("maximum", _mutate_result_protocol),
        ("maximum", _mutate_result_id),
        ("local", _mutate_result_missing_report),
        ("local", _mutate_result_protocol),
        ("local", _mutate_result_id),
    ],
    ids=lambda value: getattr(value, "__name__", value).removeprefix("_mutate_result_"),
)
def test_result_oracle_rejects_hostile_mutations(
    kind: str, mutation: Callable[[dict[str, Any]], None]
) -> None:
    value = _fixture_result(kind)
    mutation(value)
    with pytest.raises(ContractReject):
        _validate_result(kind, value)


@pytest.mark.parametrize("kind", ["maximum", "local"])
def test_verification_receipt_shape_fixtures_are_closed(kind: str) -> None:
    receipt, candidate_raw, result, result_raw = _fixture_receipt(kind)
    _validate_receipt(kind, receipt, candidate_raw, result, result_raw)


@pytest.mark.parametrize(
    "mutation",
    [
        _mutate_receipt_candidate_hash,
        _mutate_receipt_status,
        _mutate_receipt_result_path,
        _mutate_receipt_extra,
        _mutate_receipt_id,
    ],
    ids=lambda function: function.__name__.removeprefix("_mutate_receipt_"),
)
def test_receipt_oracle_rejects_hostile_mutations(
    mutation: Callable[[dict[str, Any]], None],
) -> None:
    receipt, candidate_raw, result, result_raw = _fixture_receipt("maximum")
    mutation(receipt)
    with pytest.raises(ContractReject):
        _validate_receipt("maximum", receipt, candidate_raw, result, result_raw)


def test_six_case_pilot_manifest_shape_fixture_is_closed() -> None:
    _validate_pilot_manifest(_fixture_pilot_manifest())


@pytest.mark.parametrize(
    "mutation",
    [
        _mutate_pilot_duplicate_case,
        _mutate_pilot_plan,
        _mutate_pilot_role_collision,
        _mutate_pilot_status,
        _mutate_pilot_extra,
        _mutate_pilot_id,
    ],
    ids=lambda function: function.__name__.removeprefix("_mutate_pilot_"),
)
def test_pilot_manifest_oracle_rejects_hostile_mutations(
    mutation: Callable[[dict[str, Any]], None],
) -> None:
    value = _fixture_pilot_manifest()
    mutation(value)
    with pytest.raises(ContractReject):
        _validate_pilot_manifest(value)


def test_verifier_accepts_independent_legal_case5_attainer(tmp_path: Path) -> None:
    candidate = _fixture_candidate(5)
    candidate_root = tmp_path / "candidate"
    candidate_raw = _publish_candidate_fixture(candidate_root, candidate)
    output_root = tmp_path / "verified"
    completed = _run_verifier(candidate_root, output_root)
    assert completed.returncode == 0, completed.stderr.decode("utf-8", errors="replace")
    assert completed.stdout == completed.stderr == b""
    assert {path.name for path in output_root.iterdir()} == {
        "context_objects",
        "maximum_attainer.json",
        "verification_receipt.json",
    }
    assert (output_root / "context_objects").is_dir()
    assert not any((output_root / "context_objects").iterdir())

    result_raw = (output_root / "maximum_attainer.json").read_bytes()
    receipt_raw = (output_root / "verification_receipt.json").read_bytes()
    result = _strict_loads(result_raw)
    receipt = _strict_loads(receipt_raw)
    assert result_raw == _pretty_bytes(result)
    assert receipt_raw == _pretty_bytes(receipt)
    _validate_result("maximum", result)
    _validate_receipt("maximum", receipt, candidate_raw, result, result_raw)

    witness = {"kind": "BOOL", "value": False}
    witness_raw = _canonical_bytes(witness)
    assert result["type_name"] == "CapacityMeasurementBoolValueV1"
    assert result["alternative_name"] is None
    assert result["witness_record"] == witness
    assert result["scope_witness_context"] is None
    assert result["canonical_byte_length"] == len(witness_raw)
    assert result["certified_analytic_maximum_octets"] == len(witness_raw)
    assert result["canonical_sha256"] == _sha256(witness_raw)
    assert result["upper_bound_certificate"]["certified_upper_bound_octets"] == len(
        witness_raw
    )
    assert (
        result["upper_bound_certificate"]["derivation_plan_id"]
        == candidate["logical_count_plan_id"]
    )


@pytest.mark.parametrize(
    "mutation",
    [
        _hostile_candidate_bad_identity,
        _hostile_candidate_resealed_claim,
        _hostile_candidate_resealed_binding,
    ],
    ids=lambda function: function.__name__.removeprefix("_hostile_candidate_"),
)
def test_verifier_rejects_hostile_candidate_without_output(
    tmp_path: Path, mutation: Callable[[dict[str, Any]], None]
) -> None:
    candidate = _fixture_candidate(5)
    mutation(candidate)
    candidate_root = tmp_path / "candidate"
    _publish_candidate_fixture(candidate_root, candidate)
    output_root = tmp_path / "verified"
    completed = _run_verifier(candidate_root, output_root)
    assert completed.returncode != 0
    assert completed.stdout == b""
    assert completed.stderr.startswith(b"RAW_V8_STEP2_MAXIMUM_PROTOCOL_V2_VERIFIER_")
    assert completed.stderr.count(b"\n") == 1
    assert not output_root.exists()


def test_producer_emits_only_the_legal_case5_candidate(tmp_path: Path) -> None:
    path = _implemented_path_or_skip("SEPARATE_PRODUCER")
    output_root = tmp_path / "candidate"
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            str(path),
            "--repository-root",
            str(ROOT),
            "--boundary",
            str(BOUNDARY_PATH),
            "--case-position",
            "5",
            "--output-root",
            str(output_root),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        env=_isolated_environment(),
    )
    assert completed.returncode == 0, completed.stderr.decode("utf-8", errors="replace")
    assert completed.stdout == completed.stderr == b""
    assert {path.name for path in output_root.iterdir()} == {
        "candidate.json",
        "context_objects",
    }
    assert not any((output_root / "context_objects").iterdir())
    raw = (output_root / "candidate.json").read_bytes()
    candidate = _strict_loads(raw)
    assert raw == _pretty_bytes(candidate)
    _validate_candidate(candidate)
    assert candidate["case_position"] == 5
    assert candidate["candidate_payload"] == {
        "candidate_kind": "MAXIMUM_WITNESS_CONTEXT",
        "witness_record": {"kind": "BOOL", "value": False},
        "scope_witness_context": None,
        "ordered_context_object_entries": [],
    }


@pytest.mark.parametrize("role_name", ROLE_ORDER)
def test_source_surface_fixture_is_role_separated(role_name: str) -> None:
    _source_surface(role_name, _source_fixture(role_name))


@pytest.mark.parametrize(
    ("role_name", "suffix"),
    [
        ("INDEPENDENT_VERIFIER", "\nimport subprocess\n"),
        ("INDEPENDENT_VERIFIER", "\neval('1')\n"),
        (
            "INDEPENDENT_VERIFIER",
            "\nOTHER = 'scripts/tests/produce_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py'\n",
        ),
        ("SEPARATE_PRODUCER", "\nimport riskyieldmm\n"),
        ("SEPARATE_PRODUCER", "\nos.fork()\n"),
        ("SEPARATE_PRODUCER", "\nCLAIM = 'upper_bound_certificate'\n"),
        ("PARENT_PILOT_RUNNER", "\nimport subprocess\n"),
        ("PARENT_PILOT_RUNNER", "\nexec('pass')\n"),
    ],
)
def test_source_surface_rejects_hostile_mutations(role_name: str, suffix: str) -> None:
    with pytest.raises(ContractReject):
        _source_surface(role_name, _source_fixture(role_name) + suffix.encode())


@pytest.mark.parametrize(
    "raw",
    [
        b'{"a":1,"a":2}',
        b'{"a":1.5}',
        b'{"a":NaN}',
        b'\xef\xbb\xbf{"a":1}',
        b"\xff",
    ],
)
def test_strict_parser_rejects_noncanonical_json_domains(raw: bytes) -> None:
    with pytest.raises(ContractReject):
        _strict_loads(raw)


@pytest.mark.parametrize("role_name", ROLE_ORDER)
def test_a4_t_requires_frozen_role_implementation(role_name: str) -> None:
    path = ROLE_PATHS[role_name]
    assert path.is_file() and not path.is_symlink(), (
        f"{ROLE_FAILURE_CODES[role_name]}: implement {path.relative_to(ROOT)} only "
        "after this independent authority/schema/hostile matrix is frozen"
    )


def _implemented_path_or_skip(role_name: str) -> Path:
    path = ROLE_PATHS[role_name]
    if not path.is_file():
        pytest.skip(f"A4-T expected blocker: {role_name} is not implemented")
    return path


@pytest.mark.parametrize("role_name", ROLE_ORDER)
def test_implemented_source_obeys_frozen_isolation_surface(role_name: str) -> None:
    path = _implemented_path_or_skip(role_name)
    _source_surface(role_name, path.read_bytes())


@pytest.mark.parametrize("role_name", ROLE_ORDER)
def test_implemented_role_has_silent_bounded_invalid_cli(role_name: str) -> None:
    path = _implemented_path_or_skip(role_name)
    completed = subprocess.run(
        [sys.executable, "-I", "-S", "-B", str(path), "--invalid"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        env={
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
        },
    )
    assert completed.returncode == 2
    assert completed.stdout == b""
    assert completed.stderr.decode("utf-8", errors="strict").startswith(
        ROLE_ERROR_PREFIXES[role_name]
    )
    assert completed.stderr.count(b"\n") == 1


def test_fail_first_module_does_not_import_future_or_predecessor_implementations() -> (
    None
):
    source = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    roots: set[str] = set()
    calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0 and node.module is not None
            roots.add(node.module.split(".", 1)[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)
    assert roots.isdisjoint({"riskyieldmm", "scripts", "tests"})
    assert "importlib" not in roots
    assert "spec_from_file_location" not in calls


def test_shape_fixtures_are_explicitly_not_semantic_attainers() -> None:
    maximum = _fixture_result("maximum")
    local = _fixture_result("local")
    assert maximum["type_name"] is None
    assert maximum["constraint_scope"] is None
    assert local["constraint_scope_profile_id"] is None
    assert local["minimality_certificate"] == {}
    assert _pretty_bytes(_fixture_candidate(5)).endswith(b"\n")
