#!/usr/bin/env python3
"""Build the exact-delta case-435 authority successor chain.

The accepted V1 seed, finalization manifest, constructive boundary, and
six-case fail-first target are immutable predecessor evidence.  This migrator
publishes four compact, ordered delta authorities instead of rewriting those
files or duplicating the 13 MiB seed:

    seed delta -> manifest delta -> boundary delta -> target delta

Only case 435 is overridden.  Every other case and profile resolves directly
to its byte-pinned predecessor record.  The manifest deliberately preserves
the predecessor F2 limits as immutable ceilings while requiring the expanded
verifier to requalify its case-435 resource use; it does not mislabel the old
preflight comparison as evidence about the new exact proof program.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import pathlib
import secrets
import sys
from typing import Any, Final


class AuthorityMigrationError(ValueError):
    """Raised when the case-435 authority migration cannot be proved."""


CANONICALIZATION_VERSION: Final = "riskyieldmm_canonical_json_v1"
MEASUREMENT_SCHEMA_VERSION: Final = (
    "riskyieldmm.raw_v8_step2_external_schema_v2.measurement_schema.v1"
)
PROTOCOL_VERSION: Final = (
    "riskyieldmm.raw_v8_step2_external_schema_v2.constructive_maximum_protocol.v2"
)
CASE_POSITION: Final = 435
PROFILE_POSITION: Final = 369
PROFILE_ID: Final = (
    "505dac244288e6fb666919c99567f883c28ed573a898ce2a5dd680744dd57540"
)
PREDECESSOR_PROGRAM_ID: Final = (
    "0e4a94fb5b99c464e7db1ef0fc0525b9408683a004a5ea034fcfbf5c427eb4e8"
)
PREDECESSOR_PLAN_ID: Final = (
    "9f8cd8303e3a9360986f0294210dda931e827af6eed4ec76b0c084e54f722c4a"
)
PREDECESSOR_STRUCTURAL_UPPER_OCTETS: Final = 262_143
EXACT_MAXIMUM_OCTETS: Final = 257_887
UPPER_CERTIFICATE_ID: Final = (
    "c01bba7c5f5f19c12957493c7a0989dc3ddbc42306c0f059ee922c18341e62b4"
)
ATTAINER_CERTIFICATE_ID: Final = (
    "1d801ba5b81a5e5ed27adfba2ff718fa24a7bd27e3cbf87ce5b603f653502dba"
)
EXACTNESS_JOIN_CERTIFICATE_ID: Final = (
    "2abf00603826f93bb6a538511bbd49ee45096901edbf9bc63c7d0cefb9e7fc3f"
)
CORRECTION_CONTRACT_ID: Final = (
    "e95d6f101942c0f1171616f0b05cf8978991fda639fc63a355765dd73b18c37b"
)

SEED_PATH: Final = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json"
)
MANIFEST_PATH: Final = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_finalization_manifest_v49f.json"
)
BOUNDARY_PATH: Final = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_constructive_boundary_v49f.json"
)
TARGET_PATH: Final = (
    "tests/test_raw_v8_step2_maximum_protocol_v2_six_case_qualification_fail_first_v49f.py"
)

SEED_OCTETS: Final = 13_419_905
SEED_RAW_SHA256: Final = (
    "a75a2f352e8513b7ff0043693a0c65ebbf4bc6f06859354789af69e1162b0e4f"
)
SEED_ID: Final = (
    "ac22151fa74702ac1488924f01161eaa38574545e6272a290db6b0bbd288ae5f"
)
MANIFEST_OCTETS: Final = 15_560
MANIFEST_RAW_SHA256: Final = (
    "0136fba014287605336193f782b4885f16e0163000d36429ceb0dfaf0cea52e0"
)
MANIFEST_ID: Final = (
    "edde204e98ed1caeeb8ae270487d85e39a2168e0a3692ce1d8748d2d8e7fd858"
)
BOUNDARY_OCTETS: Final = 27_334
BOUNDARY_RAW_SHA256: Final = (
    "05468ec3411869fc5b4b5c60d2820e58f8ebf0af96dea978f06d92705fe3bb2b"
)
BOUNDARY_ID: Final = (
    "bdc7363ae28dfe9a1c1dc132808cb1bd4a06c409201cd49b31e394893142a7ed"
)
TARGET_OCTETS: Final = 60_279
TARGET_RAW_SHA256: Final = (
    "12c1ff23ca6a7b58ddcda205ae017af15d7eef5be799ca7385231777c443a886"
)

SEED_DELTA_OUTPUT: Final = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_seed_delta_v49f.json"
)
MANIFEST_DELTA_OUTPUT: Final = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_manifest_delta_v49f.json"
)
BOUNDARY_DELTA_OUTPUT: Final = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_boundary_delta_v49f.json"
)
TARGET_DELTA_OUTPUT: Final = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_six_case_target_delta_v49f.json"
)
OUTPUT_PATHS: Final = (
    SEED_DELTA_OUTPUT,
    MANIFEST_DELTA_OUTPUT,
    BOUNDARY_DELTA_OUTPUT,
    TARGET_DELTA_OUTPUT,
)

SEED_DELTA_DOMAIN: Final = (
    "RiskYieldMMStep2Case435ExactSeedDeltaV1V4_9F_RawV8"
)
PROGRAM_DOMAIN: Final = (
    "RiskYieldMMStep2Case435ExactProfileConditioningProgramV2V4_9F_RawV8"
)
PLAN_DOMAIN: Final = (
    "RiskYieldMMStep2Case435ExactLogicalCountPlanV4V4_9F_RawV8"
)
MANIFEST_DELTA_DOMAIN: Final = (
    "RiskYieldMMStep2Case435ExactManifestDeltaV1V4_9F_RawV8"
)
BOUNDARY_DELTA_DOMAIN: Final = (
    "RiskYieldMMStep2Case435ExactBoundaryDeltaV1V4_9F_RawV8"
)
F2_CATALOG_DOMAIN: Final = (
    "RiskYieldMMStep2Case435ExactF2ResourceLimitCatalogV2V4_9F_RawV8"
)
TARGET_DELTA_DOMAIN: Final = (
    "RiskYieldMMStep2Case435ExactSixCaseTargetDeltaV1V4_9F_RawV8"
)

SEED_DELTA_VERSION: Final = (
    "riskyieldmm.raw_v8_step2_external_schema_v2.case435_exact_seed_delta.v1"
)
MANIFEST_DELTA_VERSION: Final = (
    "riskyieldmm.raw_v8_step2_external_schema_v2.case435_exact_manifest_delta.v1"
)
BOUNDARY_DELTA_VERSION: Final = (
    "riskyieldmm.raw_v8_step2_external_schema_v2.case435_exact_boundary_delta.v1"
)
TARGET_DELTA_VERSION: Final = (
    "riskyieldmm.raw_v8_step2_external_schema_v2.case435_exact_six_case_target_delta.v1"
)

EXACTNESS_SOURCE_SPECS: Final = (
    (
        "CASE435_UPPER_SOLVER",
        "scripts/tests/solve_raw_v8_step2_maximum_protocol_v2_case435_upper_v49f.py",
        63_596,
        "fd151f412d8c51eec3de454b91bf34ab1c705d2d81dbb1a37504ac06efa74f6c",
    ),
    (
        "CASE435_UPPER_CHECKER",
        "scripts/tests/check_raw_v8_step2_maximum_protocol_v2_case435_upper_certificate_v49f.py",
        46_246,
        "e19a00db0f989f3f3740e3314f179307362246efd5a69cea78d50e122fb6877d",
    ),
    (
        "CASE435_ATTAINER_CONSTRUCTOR",
        "scripts/tests/construct_raw_v8_step2_maximum_protocol_v2_case435_attainer_v49f.py",
        55_880,
        "ff0ca26e259f7ecbec8e2dde76eb6a4c6ec5974629ab5fc536f2d05b74e73f11",
    ),
    (
        "CASE435_ATTAINER_CHECKER",
        "scripts/tests/check_raw_v8_step2_maximum_protocol_v2_case435_attainer_certificate_v49f.py",
        31_130,
        "fb89bd4d242f38e49d43ac06648b67415f7ed6c16007107d8454a6f7dfad4058",
    ),
    (
        "CASE435_EXACTNESS_JOIN",
        "scripts/tests/join_raw_v8_step2_maximum_protocol_v2_case435_exactness_v49f.py",
        16_018,
        "236adccb8d80adcf16f834e6766e5b1085ed2664fa777a46e049f920eb1110e4",
    ),
    (
        "CASE435_EXACTNESS_CHECKER",
        "scripts/tests/check_raw_v8_step2_maximum_protocol_v2_case435_exactness_certificate_v49f.py",
        16_594,
        "18cbe51ed71f3ef7b06f251f0e83178d9529af5e4360559b91363a4b76996226",
    ),
    (
        "CASE435_EXACTNESS_TEST",
        "tests/test_raw_v8_step2_maximum_protocol_v2_case435_exactness_join_v49f.py",
        11_081,
        "fdda11a22e29797e8878c8321d7d724a30e44cd73d1ffde2ab6857efbef17cc2",
    ),
    (
        "CASE435_EXACTNESS_ACCEPTANCE",
        "docs/research/v4_9f_a2_raw_v8_step2_v2_case435_exactness_join_acceptance_2026-08-10.md",
        8_576,
        "ce2e5afd4b3627a8012f659f331e4688f6b81131032da4fdf131e3ad63e57af2",
    ),
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AuthorityMigrationError(message)


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


def _domain_id(domain: str, payload: Any) -> str:
    return _sha256(_canonical_bytes({"domain": domain, "payload": payload}))


def _seed_domain_id(seed: dict[str, Any], domain: str, payload: Any) -> str:
    return _sha256(
        _canonical_bytes(
            {
                "canonicalization_version": seed["canonicalization_version"],
                "domain": domain,
                "payload": payload,
                "schema_version": seed["measurement_schema_version"],
            }
        )
    )


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AuthorityMigrationError(f"duplicate JSON member {key!r}")
        result[key] = value
    return result


def _reject_number(value: str) -> Any:
    raise AuthorityMigrationError(f"non-integer JSON number {value!r}")


def _strict_load(raw: bytes, *, label: str) -> dict[str, Any]:
    _require(not raw.startswith(b"\xef\xbb\xbf"), f"{label} has a BOM")
    try:
        text = raw.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_float=_reject_number,
            parse_constant=_reject_number,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AuthorityMigrationError(f"{label} is not strict JSON") from error
    _require(type(value) is dict, f"{label} root is not an object")
    return value


def _read_pinned(
    root: pathlib.Path,
    relative_path: str,
    octets: int,
    digest: str,
    *,
    label: str,
) -> bytes:
    path = root / relative_path
    raw = path.read_bytes()
    _require(len(raw) == octets, f"{label} octet count drifted")
    _require(_sha256(raw) == digest, f"{label} SHA-256 drifted")
    return raw


def _file_authority(
    relative_path: str,
    raw: bytes,
    *,
    semantic_member_name: str | None = None,
    semantic_id: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "repository_relative_path": relative_path,
        "raw_octets": len(raw),
        "raw_sha256": _sha256(raw),
    }
    if semantic_member_name is not None:
        _require(semantic_id is not None, "semantic authority ID is absent")
        result[semantic_member_name] = semantic_id
    return result


def _find_one(rows: list[dict[str, Any]], *, key: str, value: Any) -> dict[str, Any]:
    matches = [row for row in rows if row.get(key) == value]
    _require(len(matches) == 1, f"expected one {key}={value!r} record")
    return matches[0]


def _validate_predecessors(
    seed: dict[str, Any], manifest: dict[str, Any], boundary: dict[str, Any]
) -> None:
    identity = _find_one(
        seed["ordered_identity_domain_records"],
        key="identity_name",
        value="SEED_CATALOG",
    )
    seed_payload = {
        name: seed[name] for name in identity["ordered_payload_member_names"]
    }
    _require(seed["seed_catalog_id"] == SEED_ID, "predecessor seed ID drifted")
    _require(
        _seed_domain_id(seed, identity["domain_literal"], seed_payload) == SEED_ID,
        "predecessor seed identity preimage drifted",
    )
    manifest_payload = {
        key: value
        for key, value in manifest.items()
        if key != "finalization_manifest_id"
    }
    _require(
        manifest["finalization_manifest_id"] == MANIFEST_ID,
        "predecessor manifest ID drifted",
    )
    _require(
        _domain_id(
            "RiskYieldMMStep2FinalizationManifestV1V4_9F_RawV8",
            manifest_payload,
        )
        == MANIFEST_ID,
        "predecessor manifest identity preimage drifted",
    )
    boundary_payload = {
        key: value
        for key, value in boundary.items()
        if key != "constructive_boundary_id"
    }
    _require(
        boundary["constructive_boundary_id"] == BOUNDARY_ID,
        "predecessor boundary ID drifted",
    )
    _require(
        _domain_id(
            "RiskYieldMMStep2ConstructiveExecutionBoundaryV1V4_9F_RawV8",
            boundary_payload,
        )
        == BOUNDARY_ID,
        "predecessor boundary identity preimage drifted",
    )


def _exactness_theorem_authority(root: pathlib.Path) -> dict[str, Any]:
    source_records = []
    for position, (role, path, octets, digest) in enumerate(
        EXACTNESS_SOURCE_SPECS, 1
    ):
        raw = _read_pinned(root, path, octets, digest, label=role)
        source_records.append(
            {
                "source_position": position,
                "source_role": role,
                **_file_authority(path, raw),
            }
        )
    return {
        "correction_subgate": "A4-P6-C435-C3",
        "correction_contract_id": CORRECTION_CONTRACT_ID,
        "case_position": CASE_POSITION,
        "profile_position": PROFILE_POSITION,
        "maximum_constraint_scope_profile_id": PROFILE_ID,
        "predecessor_profile_conditioning_program_id": PREDECESSOR_PROGRAM_ID,
        "predecessor_logical_count_plan_id": PREDECESSOR_PLAN_ID,
        "upper_certificate_id": UPPER_CERTIFICATE_ID,
        "attainer_certificate_id": ATTAINER_CERTIFICATE_ID,
        "exactness_join_certificate_id": EXACTNESS_JOIN_CERTIFICATE_ID,
        "proved_legal_upper_bound_octets": EXACT_MAXIMUM_OCTETS,
        "independently_measured_legal_attainer_octets": EXACT_MAXIMUM_OCTETS,
        "exact_maximum_octets": EXACT_MAXIMUM_OCTETS,
        "exact_cell_kind": "EXACT_ATTAINED_MAXIMUM",
        "ordered_source_authority_records": source_records,
    }


def _successor_program(
    predecessor: dict[str, Any], theorem: dict[str, Any]
) -> dict[str, Any]:
    program = copy.deepcopy(predecessor)
    _require(
        program.pop("profile_conditioning_program_id") == PREDECESSOR_PROGRAM_ID,
        "case-435 predecessor program ID drifted",
    )
    _require(program["case_position"] == CASE_POSITION, "case-435 program position")
    _require(
        program["profile_position"] == PROFILE_POSITION, "case-435 profile position"
    )
    _require(
        program["maximum_constraint_scope_profile_id"] == PROFILE_ID,
        "case-435 profile ID drifted",
    )
    transfer = program["conditioning_transfer_program"]
    old_p2 = transfer["p2_upper_bound_program"]
    _require(
        old_p2["upper_bound_source"] == "STRUCTURAL_TEMPLATE_SUPERSET_V1",
        "case-435 predecessor is not the falsified structural source",
    )
    template_id = program["logical_plan_template_id"]
    root_position = program["template_root_step_position"]
    exact_cell = {
        "cell_kind": "EXACT_ATTAINED_MAXIMUM",
        "cell_status": "C3_EXACTNESS_JOIN_ACCEPTED",
        "certified_lower_bound_octets": EXACT_MAXIMUM_OCTETS,
        "certified_upper_bound_octets": EXACT_MAXIMUM_OCTETS,
        "attaining_witness_canonical_octets": EXACT_MAXIMUM_OCTETS,
        "proof_source_id": theorem["exactness_join_certificate_id"],
    }
    transfer["program_version"] = (
        "riskyieldmm.raw_v8_step2_external_schema_v2."
        "profile_conditioning_dual_channel_program.v2"
    )
    transfer["p2_upper_bound_program"] = {
        "program_version": (
            "riskyieldmm.raw_v8_step2_external_schema_v2."
            "case_exactness_join_p2_program.v1"
        ),
        "upper_bound_source": "ACCEPTED_CASE_EXACTNESS_JOIN_V1",
        "ordered_instruction_records": [
            {
                "instruction_position": 1,
                "opcode": "IMPORT_ACCEPTED_CASE_EXACTNESS_JOIN_CELL_V1",
                "ordered_input_instruction_positions": [],
                "output_type": "P2_EXACT_ATTAINED_CELL",
                "parameters": {
                    "case_position": CASE_POSITION,
                    "maximum_constraint_scope_profile_id": PROFILE_ID,
                    "exactness_join_certificate_id": EXACTNESS_JOIN_CERTIFICATE_ID,
                    "exact_maximum_octets": EXACT_MAXIMUM_OCTETS,
                    "exact_cell": exact_cell,
                },
            },
            {
                "instruction_position": 2,
                "opcode": "LOAD_STRUCTURAL_TEMPLATE_SUPERSET_CELL_V1",
                "ordered_input_instruction_positions": [],
                "output_type": "P2_SUPERSET_BOUND_CELL",
                "parameters": {
                    "logical_plan_template_id": template_id,
                    "template_root_step_position": root_position,
                    "predecessor_structural_upper_bound_octets": (
                        PREDECESSOR_STRUCTURAL_UPPER_OCTETS
                    ),
                },
            },
            {
                "instruction_position": 3,
                "opcode": "REQUIRE_EXACT_CELL_WITHIN_STRUCTURAL_CEILING_V1",
                "ordered_input_instruction_positions": [1, 2],
                "output_type": "P2_EXACT_ATTAINED_CELL",
                "parameters": {
                    "acceptance_rule": (
                        "EXACT_CELL_LOWER_EQUALS_UPPER_EQUALS_ATTAINER_AND_"
                        "EXACT_UPPER_LE_STRUCTURAL_CEILING"
                    )
                },
            },
        ],
        "root_instruction_position": 3,
        "failure_policy": "UNRESOLVED_EMPTY_INVALID_OR_LIMIT_EXCEEDED_NO_GO",
        "exact_attainability_claimed": True,
        "safe_relaxation_applied": False,
        "cross_application_deletion_applied": False,
    }
    p1_p3 = transfer["p1_p3_attainment_program"]
    import_p2 = _find_one(
        p1_p3["ordered_instruction_records"],
        key="opcode",
        value="IMPORT_P2_BOUND_CELL_V1",
    )
    import_p2["parameters"]["p2_root_instruction_position"] = 3
    program["profile_conditioning_program_version"] = (
        "riskyieldmm.raw_v8_step2_external_schema_v2."
        "profile_conditioning_program.v2"
    )
    program["conditioning_strategy"] = (
        "APPLICATION_AWARE_EXACT_UPPER_ATTAINMENT_JOIN_V1"
    )
    program["profile_conditioning_program_id"] = _domain_id(
        PROGRAM_DOMAIN, program
    )
    return program


def _successor_plan(
    predecessor: dict[str, Any], successor_program_id: str
) -> dict[str, Any]:
    plan = copy.deepcopy(predecessor)
    _require(
        plan.pop("logical_count_plan_id") == PREDECESSOR_PLAN_ID,
        "case-435 predecessor plan ID drifted",
    )
    _require(
        plan["upper_bound_mode"]
        == "LEGAL_DOMAIN_SUPERSET_WITH_LEGAL_ATTAINMENT",
        "case-435 predecessor plan mode drifted",
    )
    plan["logical_count_plan_version"] = (
        "riskyieldmm.raw_v8_step2_external_schema_v2.logical_count_plan.v4"
    )
    plan["upper_bound_mode"] = "EXACT_LEGAL_DOMAIN"
    plan["ordered_safe_relaxation_rule_ids"] = []
    plan["profile_conditioning_program_id"] = successor_program_id
    plan["logical_root_reference"] = {
        "root_kind": "PROFILE_CONDITIONING_PROGRAM",
        "root_id": successor_program_id,
    }
    plan["scope_summary"]["schedule_authority_id"] = successor_program_id
    plan["scope_summary"]["p2_cross_application_deletion_policy_id"] = None
    plan["logical_count_plan_id"] = _domain_id(PLAN_DOMAIN, plan)
    return plan


def _record_digest(rows: Any) -> str:
    return _sha256(_canonical_bytes(rows))


def _build_seed_delta(
    seed: dict[str, Any], seed_raw: bytes, theorem: dict[str, Any]
) -> dict[str, Any]:
    recipe = seed["logical_plan_recipe_catalog"]
    programs = recipe["ordered_profile_conditioning_program_records"]
    plans = recipe["ordered_logical_count_plan_records"]
    bindings = recipe["ordered_case_plan_bindings"]
    predecessor_program = _find_one(programs, key="case_position", value=CASE_POSITION)
    predecessor_plan = _find_one(plans, key="case_position", value=CASE_POSITION)
    predecessor_binding = _find_one(bindings, key="case_position", value=CASE_POSITION)
    successor_program = _successor_program(predecessor_program, theorem)
    successor_plan = _successor_plan(
        predecessor_plan, successor_program["profile_conditioning_program_id"]
    )
    successor_binding = copy.deepcopy(predecessor_binding)
    successor_binding["logical_count_plan_id"] = successor_plan[
        "logical_count_plan_id"
    ]

    unaffected_programs = [
        row for row in programs if row["case_position"] != CASE_POSITION
    ]
    unaffected_plans = [row for row in plans if row["case_position"] != CASE_POSITION]
    unaffected_bindings = [
        row for row in bindings if row["case_position"] != CASE_POSITION
    ]
    inherited_recipe_members = {
        key: value
        for key, value in recipe.items()
        if key
        not in {
            "logical_plan_recipe_catalog_id",
            "ordered_profile_conditioning_program_records",
            "ordered_logical_count_plan_records",
            "ordered_case_plan_bindings",
        }
    }
    payload: dict[str, Any] = {
        "seed_delta_version": SEED_DELTA_VERSION,
        "canonicalization_version": seed["canonicalization_version"],
        "measurement_schema_version": seed["measurement_schema_version"],
        "protocol_version": seed["protocol_version"],
        "predecessor_seed_authority": _file_authority(
            SEED_PATH,
            seed_raw,
            semantic_member_name="seed_catalog_id",
            semantic_id=seed["seed_catalog_id"],
        ),
        "exactness_theorem_authority": theorem,
        "resolution_contract": {
            "resolution_version": (
                "riskyieldmm.raw_v8_step2_external_schema_v2."
                "single_case_exact_delta_resolution.v1"
            ),
            "ordered_override_case_positions": [CASE_POSITION],
            "override_cardinality": 1,
            "base_fallback_case_count": 474,
            "resolution_rule": (
                "CASE_435_MUST_RESOLVE_TO_SUCCESSOR_RECORDS_OTHER_CASES_MUST_"
                "RESOLVE_BYTE_EXACTLY_TO_PREDECESSOR"
            ),
            "shadowed_predecessor_case435_use_policy": "REJECT",
            "unknown_duplicate_or_extra_override_policy": "REJECT",
            "structural_superset_as_exact_maximum_policy": "REJECT",
        },
        "successor_program_schema_contract": {
            "profile_conditioning_program_version": (
                "riskyieldmm.raw_v8_step2_external_schema_v2."
                "profile_conditioning_program.v2"
            ),
            "conditioning_transfer_program_version": (
                "riskyieldmm.raw_v8_step2_external_schema_v2."
                "profile_conditioning_dual_channel_program.v2"
            ),
            "p2_program_version": (
                "riskyieldmm.raw_v8_step2_external_schema_v2."
                "case_exactness_join_p2_program.v1"
            ),
            "ordered_p2_opcode_records": [
                {
                    "opcode_position": 1,
                    "opcode": "IMPORT_ACCEPTED_CASE_EXACTNESS_JOIN_CELL_V1",
                    "output_type": "P2_EXACT_ATTAINED_CELL",
                },
                {
                    "opcode_position": 2,
                    "opcode": "LOAD_STRUCTURAL_TEMPLATE_SUPERSET_CELL_V1",
                    "output_type": "P2_SUPERSET_BOUND_CELL",
                },
                {
                    "opcode_position": 3,
                    "opcode": "REQUIRE_EXACT_CELL_WITHIN_STRUCTURAL_CEILING_V1",
                    "output_type": "P2_EXACT_ATTAINED_CELL",
                },
            ],
            "exact_cell_invariant": (
                "LOWER_EQUALS_UPPER_EQUALS_ATTAINING_WITNESS_AND_EXACT_UPPER_"
                "DOES_NOT_EXCEED_STRUCTURAL_CEILING"
            ),
            "p1_p3_program_policy": (
                "PRESERVE_PREDECESSOR_EXACT_APPLICATION_REPLAY_AND_BIND_TO_"
                "SUCCESSOR_P2_ROOT"
            ),
        },
        "successor_case435_profile_conditioning_program": successor_program,
        "successor_case435_logical_count_plan": successor_plan,
        "successor_case435_case_plan_binding": successor_binding,
        "no_unrelated_drift_proof": {
            "case_universe_record_count": len(
                seed["case_universe_catalog"]["ordered_case_bindings"]
            ),
            "case_universe_records_sha256": _record_digest(
                seed["case_universe_catalog"]["ordered_case_bindings"]
            ),
            "unaffected_profile_program_count": len(unaffected_programs),
            "unaffected_profile_program_records_sha256": _record_digest(
                unaffected_programs
            ),
            "unaffected_case_plan_count": len(unaffected_plans),
            "unaffected_case_plan_records_sha256": _record_digest(unaffected_plans),
            "unaffected_case_plan_binding_count": len(unaffected_bindings),
            "unaffected_case_plan_binding_records_sha256": _record_digest(
                unaffected_bindings
            ),
            "inherited_recipe_member_names": sorted(inherited_recipe_members),
            "inherited_recipe_members_sha256": _record_digest(
                inherited_recipe_members
            ),
            "authorized_override_json_pointers": [
                "/logical_plan_recipe_catalog/ordered_profile_conditioning_program_records/368",
                "/logical_plan_recipe_catalog/ordered_logical_count_plan_records/434",
                "/logical_plan_recipe_catalog/ordered_case_plan_bindings/434",
            ],
        },
    }
    return {
        **payload,
        "successor_seed_catalog_id": _domain_id(SEED_DELTA_DOMAIN, payload),
    }


def _build_manifest_delta(
    manifest: dict[str, Any],
    manifest_raw: bytes,
    seed_delta: dict[str, Any],
    seed_delta_raw: bytes,
) -> dict[str, Any]:
    f2_records = manifest["ordered_f2_limit_records"]
    payload: dict[str, Any] = {
        "manifest_delta_version": MANIFEST_DELTA_VERSION,
        "canonicalization_version": manifest["canonicalization_version"],
        "protocol_version": manifest["protocol_version"],
        "predecessor_finalization_manifest_authority": _file_authority(
            MANIFEST_PATH,
            manifest_raw,
            semantic_member_name="finalization_manifest_id",
            semantic_id=manifest["finalization_manifest_id"],
        ),
        "successor_seed_delta_authority": _file_authority(
            SEED_DELTA_OUTPUT,
            seed_delta_raw,
            semantic_member_name="successor_seed_catalog_id",
            semantic_id=seed_delta["successor_seed_catalog_id"],
        ),
        "exactness_join_certificate_id": EXACTNESS_JOIN_CERTIFICATE_ID,
        "case435_exact_maximum_octets": EXACT_MAXIMUM_OCTETS,
        "predecessor_evidence_scope": {
            "comparison_payload_id": manifest["comparison_evidence"][
                "comparison_payload_id"
            ],
            "semantic_payload_id": manifest["semantic_evidence"][
                "semantic_payload_id"
            ],
            "comparison_applies_to_predecessor_seed_only": True,
            "comparison_reuse_as_successor_preflight_forbidden": True,
        },
        "f2_limit_authority": {
            "limit_record_count": len(f2_records),
            "ordered_f2_limit_records_sha256": _record_digest(f2_records),
            "limits_are_byte_exact_predecessor_ceilings": True,
            "limits_may_not_be_raised_or_repaired_by_case435": True,
            "case435_successor_resource_requalification": (
                "REQUIRED_DURING_A4_P6_V_BEFORE_CASE_ACCEPTANCE"
            ),
            "excess_policy": "CONTROLLED_NO_GO_WITH_NO_LIMIT_CHANGE",
        },
        "manifest_status": (
            "CASE435_EXACT_DELTA_BOUND_VERIFIER_RESOURCE_REQUALIFICATION_REQUIRED"
        ),
        "next_subgate": "A4-P6-C435-D-BOUNDARY",
    }
    return {
        **payload,
        "successor_manifest_id": _domain_id(MANIFEST_DELTA_DOMAIN, payload),
    }


def _build_boundary_delta(
    boundary: dict[str, Any],
    boundary_raw: bytes,
    manifest: dict[str, Any],
    seed_delta: dict[str, Any],
    seed_delta_raw: bytes,
    manifest_delta: dict[str, Any],
    manifest_delta_raw: bytes,
) -> dict[str, Any]:
    successor_plan = seed_delta["successor_case435_logical_count_plan"]
    predecessor_pilot = _find_one(
        boundary["pilot_contract"]["ordered_pilot_case_records"],
        key="case_position",
        value=CASE_POSITION,
    )
    successor_pilot = copy.deepcopy(predecessor_pilot)
    successor_pilot["logical_count_plan_id"] = successor_plan[
        "logical_count_plan_id"
    ]
    successor_pilot["coverage_tag"] = (
        "MAX64_ROOT_FULL67_CONTEXT_137_APPLICATIONS_EXACT_257887"
    )
    f2_payload = {
        "catalog_version": (
            "riskyieldmm.raw_v8_step2_external_schema_v2."
            "case435_exact_f2_resource_limit_catalog.v2"
        ),
        "protocol_version": boundary["protocol_version"],
        "successor_seed_catalog_id": seed_delta["successor_seed_catalog_id"],
        "successor_manifest_id": manifest_delta["successor_manifest_id"],
        "predecessor_ordered_f2_limit_records_sha256": _record_digest(
            manifest["ordered_f2_limit_records"]
        ),
    }
    f2_catalog_id = _domain_id(F2_CATALOG_DOMAIN, f2_payload)
    payload: dict[str, Any] = {
        "boundary_delta_version": BOUNDARY_DELTA_VERSION,
        "canonicalization_version": boundary["canonicalization_version"],
        "measurement_schema_version": boundary["measurement_schema_version"],
        "protocol_version": boundary["protocol_version"],
        "predecessor_constructive_boundary_authority": _file_authority(
            BOUNDARY_PATH,
            boundary_raw,
            semantic_member_name="constructive_boundary_id",
            semantic_id=boundary["constructive_boundary_id"],
        ),
        "successor_seed_delta_authority": _file_authority(
            SEED_DELTA_OUTPUT,
            seed_delta_raw,
            semantic_member_name="successor_seed_catalog_id",
            semantic_id=seed_delta["successor_seed_catalog_id"],
        ),
        "successor_manifest_delta_authority": _file_authority(
            MANIFEST_DELTA_OUTPUT,
            manifest_delta_raw,
            semantic_member_name="successor_manifest_id",
            semantic_id=manifest_delta["successor_manifest_id"],
        ),
        "effective_authority_resolution": {
            "load_order": [
                "PREDECESSOR_BOUNDARY",
                "PREDECESSOR_SEED_AND_MANIFEST",
                "SUCCESSOR_SEED_DELTA",
                "SUCCESSOR_MANIFEST_DELTA",
            ],
            "candidate_read_barrier": (
                "ALL_PREDECESSOR_AND_DELTA_AUTHORITIES_ACCEPTED_BEFORE_"
                "OPENING_CANDIDATE_BYTES"
            ),
            "case435_resolution": "SUCCESSOR_EXACT_RECORDS_ONLY",
            "all_other_case_resolution": "BYTE_EXACT_PREDECESSOR_RECORDS_ONLY",
            "ambiguous_missing_duplicate_or_extra_resolution_policy": "REJECT",
            "downstream_field_binding_overrides": {
                "seed_catalog_id": "SUCCESSOR_SEED_CATALOG_ID",
                "finalization_manifest_id": "SUCCESSOR_MANIFEST_ID",
                "maximum_protocol_sha256": "SUCCESSOR_MANIFEST_DELTA_RAW_SHA256",
                "derivation_plan_id_for_case435": (
                    "SUCCESSOR_CASE435_LOGICAL_COUNT_PLAN_ID"
                ),
                "upper_bound_mode_for_case435": "EXACT_LEGAL_DOMAIN",
                "ordered_safe_relaxation_rule_ids_for_case435": [],
                "resource_limit_catalog_id": "SUCCESSOR_F2_RESOURCE_LIMIT_CATALOG_ID",
            },
        },
        "successor_f2_resource_limit_catalog": {
            **f2_payload,
            "f2_resource_limit_catalog_id": f2_catalog_id,
            "limit_records_source": (
                "PREDECESSOR_FINALIZATION_MANIFEST_ORDERED_F2_LIMIT_RECORDS"
            ),
            "resource_requalification_rule": (
                "CASE435_EXPANDED_VERIFIER_MUST_FIT_EVERY_IMMUTABLE_PER_CASE_"
                "AND_FULL_RUN_LIMIT_OR_REJECT"
            ),
        },
        "case435_pilot_record_override": successor_pilot,
        "preserved_boundary_contract": {
            "inherited_member_names": sorted(
                key
                for key in boundary
                if key
                not in {
                    "constructive_boundary_id",
                    "authority_contract",
                    "pilot_contract",
                    "resource_enforcement_contract",
                }
            ),
            "inherited_members_sha256": _record_digest(
                {
                    key: value
                    for key, value in boundary.items()
                    if key
                    not in {
                        "constructive_boundary_id",
                        "authority_contract",
                        "pilot_contract",
                        "resource_enforcement_contract",
                    }
                }
            ),
            "candidate_and_result_schemas_unchanged": True,
            "implementation_role_records_unchanged": True,
            "filesystem_and_independence_contracts_unchanged": True,
        },
        "boundary_status": (
            "CASE435_EXACT_DELTA_ACCEPTED_FOR_INDEPENDENT_VERIFIER_EXPANSION"
        ),
        "verifier_expansion_state": "RELEASED_FOR_A4_P6_V_IMPLEMENTATION",
        "producer_expansion_state": "HOLD_UNTIL_A4_P6_V_ACCEPTED",
        "runner_state": "HOLD_UNTIL_VERIFIER_AND_PRODUCER_EXPANSIONS_ACCEPTED",
    }
    return {
        **payload,
        "successor_constructive_boundary_id": _domain_id(
            BOUNDARY_DELTA_DOMAIN, payload
        ),
    }


def _build_target_delta(
    root: pathlib.Path,
    target_raw: bytes,
    boundary: dict[str, Any],
    seed_delta: dict[str, Any],
    seed_delta_raw: bytes,
    manifest_delta: dict[str, Any],
    manifest_delta_raw: bytes,
    boundary_delta: dict[str, Any],
    boundary_delta_raw: bytes,
) -> dict[str, Any]:
    del root
    case_rows = copy.deepcopy(
        boundary["pilot_contract"]["ordered_pilot_case_records"]
    )
    case435_row = _find_one(case_rows, key="case_position", value=CASE_POSITION)
    replacement = boundary_delta["case435_pilot_record_override"]
    case435_row.clear()
    case435_row.update(copy.deepcopy(replacement))
    payload: dict[str, Any] = {
        "target_delta_version": TARGET_DELTA_VERSION,
        "canonicalization_version": CANONICALIZATION_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "predecessor_six_case_target_authority": _file_authority(
            TARGET_PATH, target_raw
        ),
        "successor_seed_delta_authority": _file_authority(
            SEED_DELTA_OUTPUT,
            seed_delta_raw,
            semantic_member_name="successor_seed_catalog_id",
            semantic_id=seed_delta["successor_seed_catalog_id"],
        ),
        "successor_manifest_delta_authority": _file_authority(
            MANIFEST_DELTA_OUTPUT,
            manifest_delta_raw,
            semantic_member_name="successor_manifest_id",
            semantic_id=manifest_delta["successor_manifest_id"],
        ),
        "successor_boundary_delta_authority": _file_authority(
            BOUNDARY_DELTA_OUTPUT,
            boundary_delta_raw,
            semantic_member_name="successor_constructive_boundary_id",
            semantic_id=boundary_delta["successor_constructive_boundary_id"],
        ),
        "ordered_pilot_case_records": case_rows,
        "case435_exact_expectation": {
            "case_position": CASE_POSITION,
            "profile_position": PROFILE_POSITION,
            "maximum_constraint_scope_profile_id": PROFILE_ID,
            "successor_profile_conditioning_program_id": seed_delta[
                "successor_case435_profile_conditioning_program"
            ]["profile_conditioning_program_id"],
            "successor_logical_count_plan_id": seed_delta[
                "successor_case435_logical_count_plan"
            ]["logical_count_plan_id"],
            "upper_bound_mode": "EXACT_LEGAL_DOMAIN",
            "ordered_safe_relaxation_rule_ids": [],
            "exactness_join_certificate_id": EXACTNESS_JOIN_CERTIFICATE_ID,
            "certified_upper_bound_octets": EXACT_MAXIMUM_OCTETS,
            "required_legal_attainer_octets": EXACT_MAXIMUM_OCTETS,
            "acceptance_rule": (
                "P1_LEGAL_AND_C3_SOUND_EXACT_UPPER_AND_P3_EXACT_ATTAINMENT"
            ),
        },
        "qualification_contract": {
            "target_status": (
                "CORRECTED_AUTHORITY_FROZEN_IMPLEMENTATIONS_NOT_YET_QUALIFIED"
            ),
            "verifier_expansion_state": "NEXT",
            "producer_expansion_state": "WAITING",
            "runner_state": "WAITING",
            "all_six_case_acceptance_rule": (
                "ALL_SIX_CASES_PASS_TWICE_BYTE_IDENTICALLY_UNDER_IMMUTABLE_F2"
            ),
            "no_case_result_or_profitability_claimed": True,
            "next_subgate": "A4-P6-V",
        },
    }
    return {
        **payload,
        "successor_six_case_target_id": _domain_id(TARGET_DELTA_DOMAIN, payload),
    }


def build_authorities(root: pathlib.Path) -> dict[str, dict[str, Any]]:
    root = root.resolve(strict=True)
    seed_raw = _read_pinned(
        root, SEED_PATH, SEED_OCTETS, SEED_RAW_SHA256, label="predecessor seed"
    )
    manifest_raw = _read_pinned(
        root,
        MANIFEST_PATH,
        MANIFEST_OCTETS,
        MANIFEST_RAW_SHA256,
        label="predecessor manifest",
    )
    boundary_raw = _read_pinned(
        root,
        BOUNDARY_PATH,
        BOUNDARY_OCTETS,
        BOUNDARY_RAW_SHA256,
        label="predecessor boundary",
    )
    target_raw = _read_pinned(
        root,
        TARGET_PATH,
        TARGET_OCTETS,
        TARGET_RAW_SHA256,
        label="predecessor target",
    )
    seed = _strict_load(seed_raw, label="predecessor seed")
    manifest = _strict_load(manifest_raw, label="predecessor manifest")
    boundary = _strict_load(boundary_raw, label="predecessor boundary")
    _validate_predecessors(seed, manifest, boundary)
    theorem = _exactness_theorem_authority(root)

    seed_delta = _build_seed_delta(seed, seed_raw, theorem)
    seed_delta_raw = _pretty_bytes(seed_delta)
    manifest_delta = _build_manifest_delta(
        manifest, manifest_raw, seed_delta, seed_delta_raw
    )
    manifest_delta_raw = _pretty_bytes(manifest_delta)
    boundary_delta = _build_boundary_delta(
        boundary,
        boundary_raw,
        manifest,
        seed_delta,
        seed_delta_raw,
        manifest_delta,
        manifest_delta_raw,
    )
    boundary_delta_raw = _pretty_bytes(boundary_delta)
    target_delta = _build_target_delta(
        root,
        target_raw,
        boundary,
        seed_delta,
        seed_delta_raw,
        manifest_delta,
        manifest_delta_raw,
        boundary_delta,
        boundary_delta_raw,
    )
    return {
        SEED_DELTA_OUTPUT: seed_delta,
        MANIFEST_DELTA_OUTPUT: manifest_delta,
        BOUNDARY_DELTA_OUTPUT: boundary_delta,
        TARGET_DELTA_OUTPUT: target_delta,
    }


def _publish(path: pathlib.Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        _require(path.read_bytes() == raw, f"refusing to replace drifted {path}")
        return
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
        0o644,
    )
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
        os.unlink(temporary)
    except Exception:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def _check(root: pathlib.Path, artifacts: dict[str, dict[str, Any]]) -> None:
    for relative_path, value in artifacts.items():
        expected = _pretty_bytes(value)
        actual = (root / relative_path).read_bytes()
        _require(actual == expected, f"generated authority differs: {relative_path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repository_root", nargs="?", default=".")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    arguments = parser.parse_args(argv)
    root = pathlib.Path(arguments.repository_root).resolve(strict=True)
    try:
        artifacts = build_authorities(root)
        if arguments.write:
            for relative_path, value in artifacts.items():
                _publish(root / relative_path, _pretty_bytes(value))
        else:
            _check(root, artifacts)
    except (AuthorityMigrationError, OSError, KeyError, TypeError, ValueError) as error:
        sys.stderr.write(f"CASE435_AUTHORITY_MIGRATION_REJECT: {error}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
