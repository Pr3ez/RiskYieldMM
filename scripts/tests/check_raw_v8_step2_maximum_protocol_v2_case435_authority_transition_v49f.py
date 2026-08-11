#!/usr/bin/env python3
"""Independently verify the case-435 exact-delta authority transition.

This source imports neither the migration program nor any producer/verifier.
It starts from the physically pinned predecessor authorities, reverses the
authorized case-435 edits, reconstructs all semantic identities and physical
links, and proves that the effective resolver changes exactly one program,
one logical plan, and one case-plan binding.
"""

from __future__ import annotations

import copy
import hashlib
import json
import pathlib
import sys
from typing import Any, Final


class AuthorityTransitionReject(ValueError):
    """Raised when an authority transition is incomplete or ambiguous."""


CANONICALIZATION_VERSION: Final = "riskyieldmm_canonical_json_v1"
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
SEED_DELTA_PATH: Final = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_seed_delta_v49f.json"
)
MANIFEST_DELTA_PATH: Final = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_manifest_delta_v49f.json"
)
BOUNDARY_DELTA_PATH: Final = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_boundary_delta_v49f.json"
)
TARGET_DELTA_PATH: Final = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_six_case_target_delta_v49f.json"
)

PREDECESSOR_PINS: Final = {
    SEED_PATH: (
        13_419_905,
        "a75a2f352e8513b7ff0043693a0c65ebbf4bc6f06859354789af69e1162b0e4f",
        "ac22151fa74702ac1488924f01161eaa38574545e6272a290db6b0bbd288ae5f",
    ),
    MANIFEST_PATH: (
        15_560,
        "0136fba014287605336193f782b4885f16e0163000d36429ceb0dfaf0cea52e0",
        "edde204e98ed1caeeb8ae270487d85e39a2168e0a3692ce1d8748d2d8e7fd858",
    ),
    BOUNDARY_PATH: (
        27_334,
        "05468ec3411869fc5b4b5c60d2820e58f8ebf0af96dea978f06d92705fe3bb2b",
        "bdc7363ae28dfe9a1c1dc132808cb1bd4a06c409201cd49b31e394893142a7ed",
    ),
    TARGET_PATH: (
        60_279,
        "12c1ff23ca6a7b58ddcda205ae017af15d7eef5be799ca7385231777c443a886",
        None,
    ),
}

EXACTNESS_SOURCE_PINS: Final = (
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

SEED_DELTA_DOMAIN: Final = "RiskYieldMMStep2Case435ExactSeedDeltaV1V4_9F_RawV8"
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

SEED_KEYS: Final = frozenset(
    {
        "seed_delta_version",
        "canonicalization_version",
        "measurement_schema_version",
        "protocol_version",
        "predecessor_seed_authority",
        "exactness_theorem_authority",
        "resolution_contract",
        "successor_program_schema_contract",
        "successor_case435_profile_conditioning_program",
        "successor_case435_logical_count_plan",
        "successor_case435_case_plan_binding",
        "no_unrelated_drift_proof",
        "successor_seed_catalog_id",
    }
)
MANIFEST_KEYS: Final = frozenset(
    {
        "manifest_delta_version",
        "canonicalization_version",
        "protocol_version",
        "predecessor_finalization_manifest_authority",
        "successor_seed_delta_authority",
        "exactness_join_certificate_id",
        "case435_exact_maximum_octets",
        "predecessor_evidence_scope",
        "f2_limit_authority",
        "manifest_status",
        "next_subgate",
        "successor_manifest_id",
    }
)
BOUNDARY_KEYS: Final = frozenset(
    {
        "boundary_delta_version",
        "canonicalization_version",
        "measurement_schema_version",
        "protocol_version",
        "predecessor_constructive_boundary_authority",
        "successor_seed_delta_authority",
        "successor_manifest_delta_authority",
        "effective_authority_resolution",
        "successor_f2_resource_limit_catalog",
        "case435_pilot_record_override",
        "preserved_boundary_contract",
        "boundary_status",
        "verifier_expansion_state",
        "producer_expansion_state",
        "runner_state",
        "successor_constructive_boundary_id",
    }
)
TARGET_KEYS: Final = frozenset(
    {
        "target_delta_version",
        "canonicalization_version",
        "protocol_version",
        "predecessor_six_case_target_authority",
        "successor_seed_delta_authority",
        "successor_manifest_delta_authority",
        "successor_boundary_delta_authority",
        "ordered_pilot_case_records",
        "case435_exact_expectation",
        "qualification_contract",
        "successor_six_case_target_id",
    }
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AuthorityTransitionReject(message)


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


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result, f"duplicate JSON member {key!r}")
        result[key] = value
    return result


def _bad_number(value: str) -> Any:
    raise AuthorityTransitionReject(f"non-integer JSON number {value!r}")


def _strict_json(raw: bytes, *, label: str) -> dict[str, Any]:
    _require(not raw.startswith(b"\xef\xbb\xbf"), f"{label} BOM")
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs,
            parse_float=_bad_number,
            parse_constant=_bad_number,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AuthorityTransitionReject(f"{label} strict JSON") from error
    _require(type(value) is dict, f"{label} root type")
    return value


def _closed(value: Any, keys: frozenset[str], label: str) -> dict[str, Any]:
    _require(type(value) is dict and frozenset(value) == keys, f"{label} keys")
    return value


def _one(rows: list[dict[str, Any]], key: str, expected: Any) -> dict[str, Any]:
    matches = [row for row in rows if row.get(key) == expected]
    _require(len(matches) == 1, f"one {key}={expected!r}")
    return matches[0]


def _authority(path: str, raw: bytes, id_name: str | None, identity: str | None):
    value: dict[str, Any] = {
        "repository_relative_path": path,
        "raw_octets": len(raw),
        "raw_sha256": _sha256(raw),
    }
    if id_name is not None:
        value[id_name] = identity
    return value


def _payload_identity(value: dict[str, Any], id_name: str, domain: str) -> None:
    claimed = value[id_name]
    payload = {key: item for key, item in value.items() if key != id_name}
    _require(claimed == _domain_id(domain, payload), f"{id_name} identity")


def _load_predecessors(root: pathlib.Path):
    raws: dict[str, bytes] = {}
    for path, (octets, digest, _identity) in PREDECESSOR_PINS.items():
        raw = (root / path).read_bytes()
        _require(len(raw) == octets, f"predecessor {path} octets")
        _require(_sha256(raw) == digest, f"predecessor {path} digest")
        raws[path] = raw
    seed = _strict_json(raws[SEED_PATH], label="predecessor seed")
    manifest = _strict_json(raws[MANIFEST_PATH], label="predecessor manifest")
    boundary = _strict_json(raws[BOUNDARY_PATH], label="predecessor boundary")
    _require(seed["seed_catalog_id"] == PREDECESSOR_PINS[SEED_PATH][2], "seed ID")
    _require(
        manifest["finalization_manifest_id"] == PREDECESSOR_PINS[MANIFEST_PATH][2],
        "manifest ID",
    )
    _require(
        boundary["constructive_boundary_id"] == PREDECESSOR_PINS[BOUNDARY_PATH][2],
        "boundary ID",
    )
    return raws, seed, manifest, boundary


def _load_successors(root: pathlib.Path):
    objects: dict[str, dict[str, Any]] = {}
    raws: dict[str, bytes] = {}
    for path in (
        SEED_DELTA_PATH,
        MANIFEST_DELTA_PATH,
        BOUNDARY_DELTA_PATH,
        TARGET_DELTA_PATH,
    ):
        raw = (root / path).read_bytes()
        value = _strict_json(raw, label=path)
        _require(raw == _pretty_bytes(value), f"{path} physical encoding")
        objects[path] = value
        raws[path] = raw
    return raws, objects


def _verify_theorem(root: pathlib.Path, theorem: Any) -> None:
    _require(type(theorem) is dict, "theorem authority type")
    expected_sources = []
    for position, (role, path, octets, digest) in enumerate(EXACTNESS_SOURCE_PINS, 1):
        raw = (root / path).read_bytes()
        _require(len(raw) == octets and _sha256(raw) == digest, f"{role} drift")
        expected_sources.append(
            {
                "source_position": position,
                "source_role": role,
                **_authority(path, raw, None, None),
            }
        )
    expected = {
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
        "ordered_source_authority_records": expected_sources,
    }
    _require(theorem == expected, "exactness theorem projection")


def _verify_program_and_reverse(
    successor: Any, predecessor: dict[str, Any]
) -> str:
    _require(type(successor) is dict, "successor program type")
    program_id = successor.get("profile_conditioning_program_id")
    unsigned = {
        key: value
        for key, value in successor.items()
        if key != "profile_conditioning_program_id"
    }
    _require(program_id == _domain_id(PROGRAM_DOMAIN, unsigned), "program ID")
    _require(successor["case_position"] == CASE_POSITION, "program case")
    _require(successor["profile_position"] == PROFILE_POSITION, "program profile")
    _require(
        successor["conditioning_strategy"]
        == "APPLICATION_AWARE_EXACT_UPPER_ATTAINMENT_JOIN_V1",
        "program strategy",
    )
    transfer = successor["conditioning_transfer_program"]
    p2 = transfer["p2_upper_bound_program"]
    _require(p2["upper_bound_source"] == "ACCEPTED_CASE_EXACTNESS_JOIN_V1", "P2 source")
    _require(p2["root_instruction_position"] == 3, "P2 root")
    _require(p2["exact_attainability_claimed"] is True, "P2 exact claim")
    _require(p2["safe_relaxation_applied"] is False, "P2 safe relaxation")
    _require(
        p2["cross_application_deletion_applied"] is False, "P2 cross deletion"
    )
    instructions = p2["ordered_instruction_records"]
    _require(
        [row["instruction_position"] for row in instructions] == [1, 2, 3],
        "P2 instruction positions",
    )
    _require(
        [row["opcode"] for row in instructions]
        == [
            "IMPORT_ACCEPTED_CASE_EXACTNESS_JOIN_CELL_V1",
            "LOAD_STRUCTURAL_TEMPLATE_SUPERSET_CELL_V1",
            "REQUIRE_EXACT_CELL_WITHIN_STRUCTURAL_CEILING_V1",
        ],
        "P2 opcode sequence",
    )
    exact_parameters = instructions[0]["parameters"]
    cell = exact_parameters["exact_cell"]
    _require(exact_parameters["case_position"] == CASE_POSITION, "cell case")
    _require(
        exact_parameters["exactness_join_certificate_id"]
        == EXACTNESS_JOIN_CERTIFICATE_ID,
        "cell proof ID",
    )
    _require(cell["cell_kind"] == "EXACT_ATTAINED_MAXIMUM", "cell kind")
    _require(
        cell["certified_lower_bound_octets"]
        == cell["certified_upper_bound_octets"]
        == cell["attaining_witness_canonical_octets"]
        == EXACT_MAXIMUM_OCTETS,
        "exact cell equality",
    )
    _require(cell["proof_source_id"] == EXACTNESS_JOIN_CERTIFICATE_ID, "cell source")
    _require(
        instructions[1]["parameters"]["predecessor_structural_upper_bound_octets"]
        == PREDECESSOR_STRUCTURAL_UPPER_OCTETS,
        "structural ceiling",
    )
    _require(
        EXACT_MAXIMUM_OCTETS <= PREDECESSOR_STRUCTURAL_UPPER_OCTETS,
        "exact cell exceeds structural ceiling",
    )
    import_p2 = _one(
        transfer["p1_p3_attainment_program"]["ordered_instruction_records"],
        "opcode",
        "IMPORT_P2_BOUND_CELL_V1",
    )
    _require(import_p2["parameters"]["p2_root_instruction_position"] == 3, "P1/P3 P2 root")

    reverted = copy.deepcopy(successor)
    reverted["profile_conditioning_program_version"] = predecessor[
        "profile_conditioning_program_version"
    ]
    reverted["conditioning_strategy"] = predecessor["conditioning_strategy"]
    reverted_transfer = reverted["conditioning_transfer_program"]
    predecessor_transfer = predecessor["conditioning_transfer_program"]
    reverted_transfer["program_version"] = predecessor_transfer["program_version"]
    reverted_transfer["p2_upper_bound_program"] = copy.deepcopy(
        predecessor_transfer["p2_upper_bound_program"]
    )
    reverted_import = _one(
        reverted_transfer["p1_p3_attainment_program"]["ordered_instruction_records"],
        "opcode",
        "IMPORT_P2_BOUND_CELL_V1",
    )
    reverted_import["parameters"]["p2_root_instruction_position"] = 1
    reverted["profile_conditioning_program_id"] = PREDECESSOR_PROGRAM_ID
    _require(reverted == predecessor, "program contains unauthorized drift")
    return program_id


def _verify_plan_and_reverse(
    successor: Any, predecessor: dict[str, Any], program_id: str
) -> str:
    _require(type(successor) is dict, "successor plan type")
    plan_id = successor.get("logical_count_plan_id")
    unsigned = {
        key: value for key, value in successor.items() if key != "logical_count_plan_id"
    }
    _require(plan_id == _domain_id(PLAN_DOMAIN, unsigned), "plan ID")
    _require(successor["case_position"] == CASE_POSITION, "plan case")
    _require(successor["upper_bound_mode"] == "EXACT_LEGAL_DOMAIN", "plan mode")
    _require(successor["ordered_safe_relaxation_rule_ids"] == [], "plan relaxations")
    _require(successor["profile_conditioning_program_id"] == program_id, "plan program")
    _require(
        successor["logical_root_reference"]
        == {"root_kind": "PROFILE_CONDITIONING_PROGRAM", "root_id": program_id},
        "plan root",
    )
    _require(successor["scope_summary"]["schedule_authority_id"] == program_id, "schedule ID")
    _require(
        successor["scope_summary"]["p2_cross_application_deletion_policy_id"]
        is None,
        "plan exact deletion policy",
    )
    reverted = copy.deepcopy(successor)
    reverted["logical_count_plan_version"] = predecessor["logical_count_plan_version"]
    reverted["upper_bound_mode"] = predecessor["upper_bound_mode"]
    reverted["ordered_safe_relaxation_rule_ids"] = copy.deepcopy(
        predecessor["ordered_safe_relaxation_rule_ids"]
    )
    reverted["profile_conditioning_program_id"] = PREDECESSOR_PROGRAM_ID
    reverted["logical_root_reference"] = copy.deepcopy(
        predecessor["logical_root_reference"]
    )
    reverted["scope_summary"]["schedule_authority_id"] = PREDECESSOR_PROGRAM_ID
    reverted["scope_summary"]["p2_cross_application_deletion_policy_id"] = (
        predecessor["scope_summary"]["p2_cross_application_deletion_policy_id"]
    )
    reverted["logical_count_plan_id"] = PREDECESSOR_PLAN_ID
    _require(reverted == predecessor, "plan contains unauthorized drift")
    return plan_id


def _verify_seed(
    root: pathlib.Path,
    seed_delta: dict[str, Any],
    seed_raw: bytes,
    seed: dict[str, Any],
) -> tuple[str, str, str]:
    _closed(seed_delta, SEED_KEYS, "seed delta")
    _payload_identity(seed_delta, "successor_seed_catalog_id", SEED_DELTA_DOMAIN)
    _require(
        seed_delta["predecessor_seed_authority"]
        == _authority(SEED_PATH, seed_raw, "seed_catalog_id", seed["seed_catalog_id"]),
        "seed predecessor authority",
    )
    _verify_theorem(root, seed_delta["exactness_theorem_authority"])
    resolution = seed_delta["resolution_contract"]
    _require(resolution["ordered_override_case_positions"] == [CASE_POSITION], "override set")
    _require(resolution["override_cardinality"] == 1, "override count")
    _require(resolution["base_fallback_case_count"] == 474, "fallback count")
    _require(resolution["shadowed_predecessor_case435_use_policy"] == "REJECT", "shadow policy")

    recipe = seed["logical_plan_recipe_catalog"]
    predecessor_program = _one(
        recipe["ordered_profile_conditioning_program_records"],
        "case_position",
        CASE_POSITION,
    )
    predecessor_plan = _one(
        recipe["ordered_logical_count_plan_records"], "case_position", CASE_POSITION
    )
    predecessor_binding = _one(
        recipe["ordered_case_plan_bindings"], "case_position", CASE_POSITION
    )
    program_id = _verify_program_and_reverse(
        seed_delta["successor_case435_profile_conditioning_program"],
        predecessor_program,
    )
    plan_id = _verify_plan_and_reverse(
        seed_delta["successor_case435_logical_count_plan"],
        predecessor_plan,
        program_id,
    )
    binding = seed_delta["successor_case435_case_plan_binding"]
    expected_binding = copy.deepcopy(predecessor_binding)
    expected_binding["logical_count_plan_id"] = plan_id
    _require(binding == expected_binding, "case-plan binding override")

    programs = [
        row
        for row in recipe["ordered_profile_conditioning_program_records"]
        if row["case_position"] != CASE_POSITION
    ]
    plans = [
        row
        for row in recipe["ordered_logical_count_plan_records"]
        if row["case_position"] != CASE_POSITION
    ]
    bindings = [
        row
        for row in recipe["ordered_case_plan_bindings"]
        if row["case_position"] != CASE_POSITION
    ]
    inherited = {
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
    proof = seed_delta["no_unrelated_drift_proof"]
    expected_proof = {
        "case_universe_record_count": 475,
        "case_universe_records_sha256": _sha256(
            _canonical_bytes(seed["case_universe_catalog"]["ordered_case_bindings"])
        ),
        "unaffected_profile_program_count": 407,
        "unaffected_profile_program_records_sha256": _sha256(
            _canonical_bytes(programs)
        ),
        "unaffected_case_plan_count": 474,
        "unaffected_case_plan_records_sha256": _sha256(_canonical_bytes(plans)),
        "unaffected_case_plan_binding_count": 474,
        "unaffected_case_plan_binding_records_sha256": _sha256(
            _canonical_bytes(bindings)
        ),
        "inherited_recipe_member_names": sorted(inherited),
        "inherited_recipe_members_sha256": _sha256(_canonical_bytes(inherited)),
        "authorized_override_json_pointers": [
            "/logical_plan_recipe_catalog/ordered_profile_conditioning_program_records/368",
            "/logical_plan_recipe_catalog/ordered_logical_count_plan_records/434",
            "/logical_plan_recipe_catalog/ordered_case_plan_bindings/434",
        ],
    }
    _require(proof == expected_proof, "no-unrelated-drift proof")
    return seed_delta["successor_seed_catalog_id"], program_id, plan_id


def _verify_manifest(
    manifest_delta: dict[str, Any],
    manifest_raw: bytes,
    manifest: dict[str, Any],
    seed_delta_raw: bytes,
    seed_id: str,
) -> str:
    _closed(manifest_delta, MANIFEST_KEYS, "manifest delta")
    _payload_identity(manifest_delta, "successor_manifest_id", MANIFEST_DELTA_DOMAIN)
    _require(
        manifest_delta["predecessor_finalization_manifest_authority"]
        == _authority(
            MANIFEST_PATH,
            manifest_raw,
            "finalization_manifest_id",
            manifest["finalization_manifest_id"],
        ),
        "manifest predecessor authority",
    )
    _require(
        manifest_delta["successor_seed_delta_authority"]
        == _authority(SEED_DELTA_PATH, seed_delta_raw, "successor_seed_catalog_id", seed_id),
        "manifest seed authority",
    )
    _require(
        manifest_delta["exactness_join_certificate_id"]
        == EXACTNESS_JOIN_CERTIFICATE_ID,
        "manifest theorem ID",
    )
    evidence = manifest_delta["predecessor_evidence_scope"]
    _require(
        evidence
        == {
            "comparison_payload_id": manifest["comparison_evidence"][
                "comparison_payload_id"
            ],
            "semantic_payload_id": manifest["semantic_evidence"][
                "semantic_payload_id"
            ],
            "comparison_applies_to_predecessor_seed_only": True,
            "comparison_reuse_as_successor_preflight_forbidden": True,
        },
        "manifest evidence scope",
    )
    f2 = manifest_delta["f2_limit_authority"]
    _require(f2["limit_record_count"] == 18, "F2 count")
    _require(
        f2["ordered_f2_limit_records_sha256"]
        == _sha256(_canonical_bytes(manifest["ordered_f2_limit_records"])),
        "F2 digest",
    )
    _require(f2["limits_are_byte_exact_predecessor_ceilings"] is True, "F2 inheritance")
    _require(
        f2["case435_successor_resource_requalification"]
        == "REQUIRED_DURING_A4_P6_V_BEFORE_CASE_ACCEPTANCE",
        "F2 requalification",
    )
    _require(
        manifest_delta["manifest_status"]
        == "CASE435_EXACT_DELTA_BOUND_VERIFIER_RESOURCE_REQUALIFICATION_REQUIRED",
        "manifest status",
    )
    return manifest_delta["successor_manifest_id"]


def _verify_boundary(
    boundary_delta: dict[str, Any],
    boundary_raw: bytes,
    boundary: dict[str, Any],
    manifest: dict[str, Any],
    seed_delta_raw: bytes,
    seed_id: str,
    manifest_delta_raw: bytes,
    manifest_id: str,
    plan_id: str,
) -> tuple[str, str]:
    _closed(boundary_delta, BOUNDARY_KEYS, "boundary delta")
    _payload_identity(
        boundary_delta, "successor_constructive_boundary_id", BOUNDARY_DELTA_DOMAIN
    )
    _require(
        boundary_delta["predecessor_constructive_boundary_authority"]
        == _authority(
            BOUNDARY_PATH,
            boundary_raw,
            "constructive_boundary_id",
            boundary["constructive_boundary_id"],
        ),
        "boundary predecessor authority",
    )
    _require(
        boundary_delta["successor_seed_delta_authority"]
        == _authority(SEED_DELTA_PATH, seed_delta_raw, "successor_seed_catalog_id", seed_id),
        "boundary seed authority",
    )
    _require(
        boundary_delta["successor_manifest_delta_authority"]
        == _authority(
            MANIFEST_DELTA_PATH,
            manifest_delta_raw,
            "successor_manifest_id",
            manifest_id,
        ),
        "boundary manifest authority",
    )
    resolution = boundary_delta["effective_authority_resolution"]
    _require(resolution["case435_resolution"] == "SUCCESSOR_EXACT_RECORDS_ONLY", "case resolution")
    _require(
        resolution["all_other_case_resolution"]
        == "BYTE_EXACT_PREDECESSOR_RECORDS_ONLY",
        "base resolution",
    )
    overrides = resolution["downstream_field_binding_overrides"]
    _require(overrides["upper_bound_mode_for_case435"] == "EXACT_LEGAL_DOMAIN", "boundary mode")
    _require(overrides["ordered_safe_relaxation_rule_ids_for_case435"] == [], "boundary relaxations")

    f2 = boundary_delta["successor_f2_resource_limit_catalog"]
    f2_id = f2["f2_resource_limit_catalog_id"]
    f2_payload = {
        key: value
        for key, value in f2.items()
        if key
        not in {
            "f2_resource_limit_catalog_id",
            "limit_records_source",
            "resource_requalification_rule",
        }
    }
    _require(f2_id == _domain_id(F2_CATALOG_DOMAIN, f2_payload), "successor F2 ID")
    _require(
        f2["predecessor_ordered_f2_limit_records_sha256"]
        == _sha256(_canonical_bytes(manifest["ordered_f2_limit_records"])),
        "boundary F2 digest",
    )
    predecessor_pilot = _one(
        boundary["pilot_contract"]["ordered_pilot_case_records"],
        "case_position",
        CASE_POSITION,
    )
    expected_pilot = copy.deepcopy(predecessor_pilot)
    expected_pilot["logical_count_plan_id"] = plan_id
    expected_pilot["coverage_tag"] = (
        "MAX64_ROOT_FULL67_CONTEXT_137_APPLICATIONS_EXACT_257887"
    )
    _require(
        boundary_delta["case435_pilot_record_override"] == expected_pilot,
        "boundary pilot override",
    )
    inherited = {
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
    preserved = boundary_delta["preserved_boundary_contract"]
    _require(preserved["inherited_member_names"] == sorted(inherited), "boundary inherited names")
    _require(
        preserved["inherited_members_sha256"] == _sha256(_canonical_bytes(inherited)),
        "boundary inherited digest",
    )
    _require(
        boundary_delta["verifier_expansion_state"]
        == "RELEASED_FOR_A4_P6_V_IMPLEMENTATION",
        "verifier release",
    )
    _require(
        boundary_delta["producer_expansion_state"]
        == "HOLD_UNTIL_A4_P6_V_ACCEPTED",
        "producer hold",
    )
    return boundary_delta["successor_constructive_boundary_id"], f2_id


def _verify_target(
    target_delta: dict[str, Any],
    target_raw: bytes,
    boundary: dict[str, Any],
    seed_delta_raw: bytes,
    seed_id: str,
    manifest_delta_raw: bytes,
    manifest_id: str,
    boundary_delta_raw: bytes,
    boundary_id: str,
    program_id: str,
    plan_id: str,
) -> str:
    _closed(target_delta, TARGET_KEYS, "target delta")
    _payload_identity(target_delta, "successor_six_case_target_id", TARGET_DELTA_DOMAIN)
    _require(
        target_delta["predecessor_six_case_target_authority"]
        == _authority(TARGET_PATH, target_raw, None, None),
        "target predecessor authority",
    )
    _require(
        target_delta["successor_seed_delta_authority"]
        == _authority(SEED_DELTA_PATH, seed_delta_raw, "successor_seed_catalog_id", seed_id),
        "target seed authority",
    )
    _require(
        target_delta["successor_manifest_delta_authority"]
        == _authority(
            MANIFEST_DELTA_PATH,
            manifest_delta_raw,
            "successor_manifest_id",
            manifest_id,
        ),
        "target manifest authority",
    )
    _require(
        target_delta["successor_boundary_delta_authority"]
        == _authority(
            BOUNDARY_DELTA_PATH,
            boundary_delta_raw,
            "successor_constructive_boundary_id",
            boundary_id,
        ),
        "target boundary authority",
    )
    expected_rows = copy.deepcopy(
        boundary["pilot_contract"]["ordered_pilot_case_records"]
    )
    row = _one(expected_rows, "case_position", CASE_POSITION)
    row["logical_count_plan_id"] = plan_id
    row["coverage_tag"] = "MAX64_ROOT_FULL67_CONTEXT_137_APPLICATIONS_EXACT_257887"
    _require(target_delta["ordered_pilot_case_records"] == expected_rows, "target case rows")
    expectation = target_delta["case435_exact_expectation"]
    _require(expectation["case_position"] == CASE_POSITION, "target case")
    _require(expectation["successor_profile_conditioning_program_id"] == program_id, "target program")
    _require(expectation["successor_logical_count_plan_id"] == plan_id, "target plan")
    _require(expectation["upper_bound_mode"] == "EXACT_LEGAL_DOMAIN", "target mode")
    _require(expectation["ordered_safe_relaxation_rule_ids"] == [], "target relaxations")
    _require(
        expectation["certified_upper_bound_octets"]
        == expectation["required_legal_attainer_octets"]
        == EXACT_MAXIMUM_OCTETS,
        "target exact equality",
    )
    qualification = target_delta["qualification_contract"]
    _require(qualification["verifier_expansion_state"] == "NEXT", "target verifier next")
    _require(qualification["producer_expansion_state"] == "WAITING", "target producer wait")
    _require(qualification["runner_state"] == "WAITING", "target runner wait")
    _require(qualification["next_subgate"] == "A4-P6-V", "target next subgate")
    _require(qualification["no_case_result_or_profitability_claimed"] is True, "target nonclaim")
    return target_delta["successor_six_case_target_id"]


def validate_objects(
    root: pathlib.Path,
    *,
    successor_raws: dict[str, bytes],
    successor_objects: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    root = root.resolve(strict=True)
    predecessor_raws, seed, manifest, boundary = _load_predecessors(root)
    seed_delta = successor_objects[SEED_DELTA_PATH]
    manifest_delta = successor_objects[MANIFEST_DELTA_PATH]
    boundary_delta = successor_objects[BOUNDARY_DELTA_PATH]
    target_delta = successor_objects[TARGET_DELTA_PATH]
    seed_id, program_id, plan_id = _verify_seed(
        root, seed_delta, predecessor_raws[SEED_PATH], seed
    )
    manifest_id = _verify_manifest(
        manifest_delta,
        predecessor_raws[MANIFEST_PATH],
        manifest,
        successor_raws[SEED_DELTA_PATH],
        seed_id,
    )
    boundary_id, f2_id = _verify_boundary(
        boundary_delta,
        predecessor_raws[BOUNDARY_PATH],
        boundary,
        manifest,
        successor_raws[SEED_DELTA_PATH],
        seed_id,
        successor_raws[MANIFEST_DELTA_PATH],
        manifest_id,
        plan_id,
    )
    target_id = _verify_target(
        target_delta,
        predecessor_raws[TARGET_PATH],
        boundary,
        successor_raws[SEED_DELTA_PATH],
        seed_id,
        successor_raws[MANIFEST_DELTA_PATH],
        manifest_id,
        successor_raws[BOUNDARY_DELTA_PATH],
        boundary_id,
        program_id,
        plan_id,
    )
    return {
        "verification_version": (
            "riskyieldmm.raw_v8_step2_external_schema_v2."
            "case435_exact_authority_transition_verification.v1"
        ),
        "verification_status": "ACCEPTED",
        "authorized_case_change_count": 1,
        "authorized_profile_program_change_count": 1,
        "authorized_logical_plan_change_count": 1,
        "authorized_case_plan_binding_change_count": 1,
        "unaffected_case_count": 474,
        "unaffected_profile_program_count": 407,
        "successor_seed_catalog_id": seed_id,
        "successor_case435_profile_conditioning_program_id": program_id,
        "successor_case435_logical_count_plan_id": plan_id,
        "successor_manifest_id": manifest_id,
        "successor_constructive_boundary_id": boundary_id,
        "successor_f2_resource_limit_catalog_id": f2_id,
        "successor_six_case_target_id": target_id,
        "case435_exact_maximum_octets": EXACT_MAXIMUM_OCTETS,
        "f2_resource_requalification_state": "REQUIRED_IN_A4_P6_V",
        "verifier_expansion_state": "RELEASED_FOR_A4_P6_V_IMPLEMENTATION",
        "next_subgate": "A4-P6-V",
    }


def verify(root: pathlib.Path) -> dict[str, Any]:
    raws, objects = _load_successors(root.resolve(strict=True))
    return validate_objects(root, successor_raws=raws, successor_objects=objects)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) > 1:
        raise SystemExit("usage: check...py [repository-root]")
    root = pathlib.Path(argv[0] if argv else ".")
    try:
        report = verify(root)
    except (AuthorityTransitionReject, OSError, KeyError, TypeError, ValueError) as error:
        sys.stderr.write(f"CASE435_AUTHORITY_TRANSITION_REJECT: {error}\n")
        return 1
    sys.stdout.buffer.write(_canonical_bytes(report) + b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
