#!/usr/bin/env python3
"""Join the frozen case-435 C1 upper and C2 attainment channels."""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys
from typing import Any

SEED_PATH = "scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json"
INVENTORY_PATH = "tests/raw_v8_step2_inventory_v4_v49f.json"
REGISTRY_PATH = (
    "scripts/tests/raw_v8_step2_external_schema_v2_structural_registry_v49f.json"
)
LITERAL_PATH = (
    "scripts/tests/raw_v8_step2_external_schema_v2_rule_literal_authority_v49f.json"
)
LEDGER_PATH = (
    "scripts/tests/raw_v8_step2_external_schema_v2_rule_application_ledger_v49f.json"
)
RUNTIME_PATH = (
    "scripts/tests/validate_raw_v8_step2_external_schema_v2_rule_runtime_v49f.py"
)
DEPENDENCY_PATH = (
    "scripts/tests/check_raw_v8_step2_maximum_protocol_v2_"
    "case435_dependency_closure_v49f.py"
)
UPPER_SOLVER_PATH = (
    "scripts/tests/solve_raw_v8_step2_maximum_protocol_v2_case435_upper_v49f.py"
)
UPPER_CHECKER_PATH = (
    "scripts/tests/check_raw_v8_step2_maximum_protocol_v2_"
    "case435_upper_certificate_v49f.py"
)
ATTAINER_CONSTRUCTOR_PATH = (
    "scripts/tests/construct_raw_v8_step2_maximum_protocol_v2_case435_attainer_v49f.py"
)
ATTAINER_CHECKER_PATH = (
    "scripts/tests/check_raw_v8_step2_maximum_protocol_v2_"
    "case435_attainer_certificate_v49f.py"
)

RAW_AUTHORITY_SHA256 = {
    SEED_PATH: "a75a2f352e8513b7ff0043693a0c65ebbf4bc6f06859354789af69e1162b0e4f",
    INVENTORY_PATH: "de91eac92d1c36cf1670b2484392fbf1c633d75f928c8e70fcd5e71ae798db2b",
    REGISTRY_PATH: "9160297ff316c5931737c92f8b359f0a1e2ec22f0aa996ef3b09cf830dc96bf3",
    LITERAL_PATH: "aba3461059367904734e2eb9ae404787b9aab5ed4c3fbcd292925a364926cce2",
    LEDGER_PATH: "979d7affe2d745d46f5977d9d69a4d1efa473f95c1a374737bf34181d9dac282",
    RUNTIME_PATH: "47aa90d897e8dbae5e244b7c04cbd82dfe036b0292d36ef0f5552c868627ab22",
    DEPENDENCY_PATH: "f882042d0bd519ced260734a43a9ee2c9b390ffac965ebe7c04ac261c2932f30",
}
CHANNEL_SOURCE_SHA256 = {
    UPPER_SOLVER_PATH: "fd151f412d8c51eec3de454b91bf34ab1c705d2d81dbb1a37504ac06efa74f6c",
    UPPER_CHECKER_PATH: "e19a00db0f989f3f3740e3314f179307362246efd5a69cea78d50e122fb6877d",
    ATTAINER_CONSTRUCTOR_PATH: (
        "ff0ca26e259f7ecbec8e2dde76eb6a4c6ec5974629ab5fc536f2d05b74e73f11"
    ),
    ATTAINER_CHECKER_PATH: (
        "fb89bd4d242f38e49d43ac06648b67415f7ed6c16007107d8454a6f7dfad4058"
    ),
}

CASE_POSITION = 435
PROFILE_POSITION = 369
MEASURED_SEQUENCE_ORDINAL = 64
PROFILE_ID = "505dac244288e6fb666919c99567f883c28ed573a898ce2a5dd680744dd57540"
PLAN_ID = "9f8cd8303e3a9360986f0294210dda931e827af6eed4ec76b0c084e54f722c4a"
PROGRAM_ID = "0e4a94fb5b99c464e7db1ef0fc0525b9408683a004a5ea034fcfbf5c427eb4e8"
DEPENDENCY_MANIFEST_ID = (
    "d80797d6d34486ed15f73d19a201c7b5ff0ac19593e25302bcba081c2e7b5c3c"
)
UPPER_CERTIFICATE_ID = (
    "c01bba7c5f5f19c12957493c7a0989dc3ddbc42306c0f059ee922c18341e62b4"
)
ATTAINER_CERTIFICATE_ID = (
    "1d801ba5b81a5e5ed27adfba2ff718fa24a7bd27e3cbf87ce5b603f653502dba"
)
UPPER_CERTIFICATE_DOMAIN = (
    "RiskYieldMMStep2MaximumProtocolV2Case435UpperCertificateV1V4_9F_RawV8"
)
ATTAINER_CERTIFICATE_DOMAIN = (
    "RiskYieldMMStep2MaximumProtocolV2Case435AttainerCertificateV1V4_9F_RawV8"
)
JOIN_VERSION = "riskyieldmm.raw_v8_step2.maximum_protocol_v2.case435_exactness_join.v1"
JOIN_DOMAIN = "RiskYieldMMStep2MaximumProtocolV2Case435ExactnessJoinV1V4_9F_RawV8"

UPPER_MEMBERS = {
    "a1_component_certificate",
    "acceptance_state",
    "authority_sha256_by_path",
    "canonical_composition",
    "case435_dependency_manifest_id",
    "case435_upper_certificate_id",
    "case_binding",
    "certificate_version",
    "correction_subgate",
    "exact_upper_bound_octets",
    "exact_upper_bound_proved",
    "finite_domain_reduction",
    "independent_attainer_accepted",
    "next_subgate",
    "ordered_field_maximum_records",
    "ordered_separator_branch_bound_records",
    "separator_feasibility_certificate",
}
ATTAINER_MEMBERS = {
    "acceptance_state",
    "attainer_certificate_version",
    "authority_sha256_by_path",
    "case435_attainer_certificate_id",
    "case435_dependency_manifest_id",
    "case_binding",
    "construction_protocol",
    "correction_subgate",
    "exactness_claimed",
    "legal_attainer_constructed",
    "measured_attainer",
    "next_subgate",
    "ordered_selected_field_witness_records",
    "p1_execution_certificate",
    "p1_legal",
    "retained_witness_context",
    "schedule_authority",
}


class JoinError(RuntimeError):
    """Raised when the two proof channels cannot be joined exactly."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise JoinError(message)


def _reject_number(value: str) -> Any:
    raise JoinError(f"non-integer JSON number is forbidden: {value}")


def _duplicate_guard(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _strict_load(raw: bytes, label: str) -> dict[str, Any]:
    _require(bool(raw) and len(raw) < 20_000_000, f"{label} byte extent is invalid")
    value = json.loads(
        raw,
        object_pairs_hook=_duplicate_guard,
        parse_float=_reject_number,
        parse_constant=_reject_number,
    )
    _require(type(value) is dict, f"{label} root is not an object")
    return value


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _certificate_id(certificate: dict[str, Any], identity: str, domain: str) -> str:
    return _sha256(
        _canonical_bytes(
            {
                "domain": domain,
                "payload": {
                    key: value for key, value in certificate.items() if key != identity
                },
            }
        )
    )


def _load_authorities(root: pathlib.Path) -> tuple[dict[str, Any], dict[str, Any]]:
    loaded: dict[str, dict[str, Any]] = {}
    for relative, expected in {**RAW_AUTHORITY_SHA256, **CHANNEL_SOURCE_SHA256}.items():
        path = root / relative
        _require(path.is_file() and not path.is_symlink(), f"source absent: {relative}")
        raw = path.read_bytes()
        _require(_sha256(raw) == expected, f"source drift: {relative}")
        if relative in {SEED_PATH, REGISTRY_PATH}:
            loaded[relative] = _strict_load(raw, relative)
    return loaded[SEED_PATH], loaded[REGISTRY_PATH]


def _case_binding() -> dict[str, Any]:
    return {
        "case_position": CASE_POSITION,
        "constraint_scope_profile_id": PROFILE_ID,
        "logical_count_plan_id": PLAN_ID,
        "measured_sequence_ordinal": MEASURED_SEQUENCE_ORDINAL,
        "profile_conditioning_program_id": PROGRAM_ID,
        "profile_position": PROFILE_POSITION,
        "target_type_name": "TargetObservationV2",
    }


def _schedule_authority(seed: dict[str, Any]) -> dict[str, Any]:
    recipe = seed["logical_plan_recipe_catalog"]
    plan = recipe["ordered_logical_count_plan_records"][CASE_POSITION - 1]
    program = next(
        row
        for row in recipe["ordered_profile_conditioning_program_records"]
        if row["profile_conditioning_program_id"] == PROGRAM_ID
    )
    _require(
        plan["logical_count_plan_id"] == PLAN_ID
        and plan["profile_conditioning_program_id"] == PROGRAM_ID
        and program["profile_position"] == PROFILE_POSITION
        and program["maximum_constraint_scope_profile_id"] == PROFILE_ID,
        "seed case/program binding differs",
    )
    schedule = program["application_schedule_operation"]
    instructions = schedule["ordered_schedule_segment_records"][0][
        "ordered_application_instruction_records"
    ]
    return {
        "application_invocation_count": schedule["application_invocation_count"],
        "application_schedule_operation_position": schedule["operation_position"],
        "cross_rule_evaluation_count": schedule["cross_rule_evaluation_count"],
        "direct_cross_expression_node_count": schedule[
            "direct_cross_expression_node_count"
        ],
        "ordered_application_instruction_sha256": _sha256(
            _canonical_bytes(instructions)
        ),
    }


def join(
    repository_root: pathlib.Path | str,
    upper: dict[str, Any],
    attainer: dict[str, Any],
) -> dict[str, Any]:
    root = pathlib.Path(repository_root)
    seed, registry = _load_authorities(root)
    _require(set(upper) == UPPER_MEMBERS, "upper certificate members differ")
    _require(set(attainer) == ATTAINER_MEMBERS, "attainer certificate members differ")
    _require(
        upper["case435_upper_certificate_id"]
        == _certificate_id(
            upper, "case435_upper_certificate_id", UPPER_CERTIFICATE_DOMAIN
        )
        == UPPER_CERTIFICATE_ID,
        "upper certificate identity differs",
    )
    _require(
        attainer["case435_attainer_certificate_id"]
        == _certificate_id(
            attainer, "case435_attainer_certificate_id", ATTAINER_CERTIFICATE_DOMAIN
        )
        == ATTAINER_CERTIFICATE_ID,
        "attainer certificate identity differs",
    )
    expected_case = _case_binding()
    _require(
        upper["case_binding"] == attainer["case_binding"] == expected_case,
        "case binding join differs",
    )
    expected_raw = dict(sorted(RAW_AUTHORITY_SHA256.items()))
    _require(
        upper["authority_sha256_by_path"]
        == attainer["authority_sha256_by_path"]
        == expected_raw,
        "raw authority join differs",
    )
    _require(
        upper["case435_dependency_manifest_id"]
        == attainer["case435_dependency_manifest_id"]
        == DEPENDENCY_MANIFEST_ID,
        "dependency manifest join differs",
    )
    _require(
        upper["certificate_version"]
        == "riskyieldmm.raw_v8_step2.maximum_protocol_v2.case435_upper_certificate.v1"
        and upper["exact_upper_bound_proved"] is True
        and upper["independent_attainer_accepted"] is False
        and upper["acceptance_state"]
        == "EXACT_UPPER_BOUND_PROVED_INDEPENDENT_ATTAINER_PENDING"
        and upper["correction_subgate"] == "A4-P6-C435-C1"
        and upper["next_subgate"] == "A4-P6-C435-C2",
        "upper channel disposition differs",
    )
    upper_octets = upper["exact_upper_bound_octets"]
    composition = upper["canonical_composition"]
    _require(
        type(upper_octets) is int
        and upper_octets > 0
        and composition["exact_upper_bound_octets"] == upper_octets
        and composition["codec_constraint_satisfied"] is True
        and composition["codec_relation"] == "LT"
        and upper_octets < composition["codec_octet_limit"],
        "upper channel result differs",
    )
    expected_schedule = _schedule_authority(seed)
    execution = attainer["p1_execution_certificate"]
    _require(
        attainer["attainer_certificate_version"]
        == "riskyieldmm.raw_v8_step2.maximum_protocol_v2.case435_attainer_certificate.v1"
        and attainer["schedule_authority"] == expected_schedule
        and attainer["p1_legal"] is True
        and attainer["legal_attainer_constructed"] is True
        and attainer["exactness_claimed"] is False
        and attainer["acceptance_state"]
        == "LEGAL_ATTAINER_CONSTRUCTED_EXACTNESS_JOIN_PENDING"
        and attainer["correction_subgate"] == "A4-P6-C435-C2"
        and attainer["next_subgate"] == "A4-P6-C435-C3"
        and execution["all_applications_accepted"] is True
        and execution["application_invocation_count"]
        == expected_schedule["application_invocation_count"]
        and execution["charged_rule_evaluation_count"]
        == expected_schedule["cross_rule_evaluation_count"]
        and execution["completed_rule_evaluation_count"]
        == expected_schedule["cross_rule_evaluation_count"]
        and execution["direct_expression_node_count"]
        == expected_schedule["direct_cross_expression_node_count"],
        "attainer channel disposition differs",
    )
    measured = attainer["measured_attainer"]
    attainer_octets = measured["canonical_octets"]
    _require(
        type(attainer_octets) is int
        and attainer_octets > 0
        and measured["measured_sequence_ordinal"] == MEASURED_SEQUENCE_ORDINAL,
        "attainer measurement differs",
    )
    _require(
        upper_octets == attainer_octets,
        "upper/attainer canonical-octet equality fails",
    )
    certificate: dict[str, Any] = {
        "exactness_join_version": JOIN_VERSION,
        "channel_source_sha256_by_path": dict(sorted(CHANNEL_SOURCE_SHA256.items())),
        "shared_raw_authority_sha256_by_path": expected_raw,
        "case435_dependency_manifest_id": DEPENDENCY_MANIFEST_ID,
        "case_binding": expected_case,
        "canonicalization_binding": {
            "canonicalization_version": registry["canonicalization_version"],
            "measurement_schema_version": registry["measurement_schema_version"],
        },
        "schedule_authority": expected_schedule,
        "upper_channel": {
            "certificate_id": UPPER_CERTIFICATE_ID,
            "certificate_version": upper["certificate_version"],
            "exact_upper_bound_octets": upper_octets,
            "exact_upper_bound_proved": True,
            "independent_attainer_accepted": False,
        },
        "attainer_channel": {
            "certificate_id": ATTAINER_CERTIFICATE_ID,
            "certificate_version": attainer["attainer_certificate_version"],
            "measured_attainer_canonical_octets": attainer_octets,
            "measured_attainer_canonical_sha256": measured["canonical_sha256"],
            "measured_attainer_observation_id": measured["observation_id"],
            "p1_legal": True,
            "legal_attainer_constructed": True,
            "prior_exactness_claimed": False,
        },
        "ordered_required_join_predicates": [
            "ACCEPTED_CHANNEL_IDENTITIES_MATCH",
            "CASE_PROFILE_SCOPE_AND_TARGET_BINDING_EQUAL",
            "RAW_AUTHORITY_SETS_EQUAL",
            "DEPENDENCY_MANIFEST_EQUAL",
            "APPLICATION_SCHEDULE_BOUND_TO_SHARED_PROGRAM",
            "UPPER_CHANNEL_PROVED",
            "ATTAINER_CHANNEL_P1_LEGAL",
            "EXACT_UPPER_EQUALS_MEASURED_LEGAL_ATTAINER_OCTETS",
        ],
        "exact_maximum_octets": upper_octets,
        "exact_maximum_proved": True,
        "exactness_claimed": True,
        "acceptance_state": "EXACT_MAXIMUM_PROVED_BY_BOUND_AND_LEGAL_ATTAINMENT",
        "correction_subgate": "A4-P6-C435-C3",
        "next_subgate": "A4-P6-C435-D",
        "verifier_expansion_state": "HOLD",
    }
    certificate["case435_exactness_join_certificate_id"] = _sha256(
        _canonical_bytes({"domain": JOIN_DOMAIN, "payload": certificate})
    )
    return certificate


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) not in {2, 3}:
        raise SystemExit("usage: join...py [repository-root] upper.json attainer.json")
    root = pathlib.Path(argv[0]).resolve() if len(argv) == 3 else pathlib.Path.cwd()
    offset = 1 if len(argv) == 3 else 0
    try:
        upper = _strict_load(
            pathlib.Path(argv[offset]).read_bytes(), "upper certificate"
        )
        attainer = _strict_load(
            pathlib.Path(argv[offset + 1]).read_bytes(), "attainer certificate"
        )
        certificate = join(root, upper, attainer)
    except (JoinError, OSError, KeyError, TypeError, ValueError) as error:
        sys.stderr.write(f"CASE435_EXACTNESS_JOIN_REJECT: {error}\n")
        return 1
    sys.stdout.buffer.write(_canonical_bytes(certificate) + b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
