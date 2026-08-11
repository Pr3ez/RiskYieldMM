#!/usr/bin/env python3
"""Independent acceptance review for A4-R475-V1-F.

The review never imports the attainability analyzer.  It executes that source
twice in isolated child interpreters, verifies the complete semantic envelope,
and independently closes the decisive case-8 contradiction from the pinned
schema and typed runtime.  The broader 26-case census is accepted as a frozen
falsification surface; only one proven contradiction is logically required to
block the all-66 V1 acceptance claim.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import subprocess
import sys
from typing import Any

ANALYZER_RELATIVE_PATH = (
    "scripts/tests/check_raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_template_attainability_v49f.py"
)
ANALYZER_RAW_OCTETS = 34_534
ANALYZER_RAW_SHA256 = "5af98367704e9ef695af050637ebb5027aeb516b5f74c971d6781ab7b232f4ff"
SEED_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json"
)
SEED_RAW_OCTETS = 13_419_905
SEED_RAW_SHA256 = "a75a2f352e8513b7ff0043693a0c65ebbf4bc6f06859354789af69e1162b0e4f"
REGISTRY_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_external_schema_v2_structural_registry_v49f.json"
)
REGISTRY_RAW_OCTETS = 1_469_663
REGISTRY_RAW_SHA256 = "9160297ff316c5931737c92f8b359f0a1e2ec22f0aa996ef3b09cf830dc96bf3"
CONTRACT_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "all_case_campaign_contract_v49f.json"
)
CONTRACT_RAW_OCTETS = 382_710
CONTRACT_RAW_SHA256 = "3ca4ff4d6e581895b813043e7fdeed24c33cf2c828e362ac81de1725e95a84bb"
RUNTIME_RELATIVE_PATH = (
    "scripts/tests/validate_raw_v8_step2_external_schema_v2_rule_runtime_v49f.py"
)
RUNTIME_RAW_OCTETS = 249_268
RUNTIME_RAW_SHA256 = "47aa90d897e8dbae5e244b7c04cbd82dfe036b0292d36ef0f5552c868627ab22"

EXPECTED_ANALYSIS_ID = (
    "0b53bd2d79c5f923f1887f7e33f167625fd43753c22345074ae2768dec0d58ad"
)
EXPECTED_VECTOR_SHA256 = (
    "3d1c35477e174cde53ab163c516dea9d7132a468bfa7c7954f1ca538317f8e5d"
)
EXPECTED_CASE8_SHA256 = (
    "9156a97a005f9d2264e34054f071a6b15169f88b23be54cb59bc254362888665"
)
EXPECTED_POSITIONS = [
    1,
    2,
    7,
    8,
    9,
    12,
    18,
    19,
    21,
    22,
    25,
    28,
    30,
    31,
    32,
    34,
    36,
    37,
    42,
    44,
    45,
    48,
    49,
    52,
    59,
    60,
]
CASE8_POSITION = 8
CASE8_TYPE = "CapacityMeasurementDispatchWindowEvidenceV1"
U128_MAXIMUM = (1 << 128) - 1
REVIEW_DOMAIN = (
    "RiskYieldMMRawV8Step2MaximumProtocolV2IntrinsicTemplate"
    "AttainabilityFalsificationAcceptanceV1"
)


class IntrinsicAttainabilityReviewError(RuntimeError):
    """Raised when reviewed evidence or a frozen authority differs."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise IntrinsicAttainabilityReviewError(message)


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as error:
        raise IntrinsicAttainabilityReviewError(
            f"canonical JSON encoding rejected: {error}"
        ) from error


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


def _semantic_id(
    canonicalization_version: str,
    schema_version: str,
    domain: str,
    payload: Any,
) -> str:
    return _sha256(
        _canonical_bytes(
            {
                "canonicalization_version": canonicalization_version,
                "domain": domain,
                "payload": payload,
                "schema_version": schema_version,
            }
        )
    )


def _load_raw(
    root: pathlib.Path,
    relative_path: str,
    expected_octets: int,
    expected_sha256: str,
) -> bytes:
    path = root / relative_path
    _require(
        path.is_file() and not path.is_symlink(),
        f"review path differs: {relative_path}",
    )
    raw = path.read_bytes()
    _require(len(raw) == expected_octets, f"review size differs: {relative_path}")
    _require(_sha256(raw) == expected_sha256, f"review hash differs: {relative_path}")
    return raw


def _load_json(
    root: pathlib.Path,
    relative_path: str,
    expected_octets: int,
    expected_sha256: str,
) -> dict[str, Any]:
    raw = _load_raw(root, relative_path, expected_octets, expected_sha256)
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, UnicodeError) as error:
        raise IntrinsicAttainabilityReviewError(
            f"review JSON differs: {relative_path}: {error}"
        ) from error
    _require(type(value) is dict, f"review root differs: {relative_path}")
    return value


def _index(rows: Any, key_name: str, expected_count: int, label: str) -> dict[Any, Any]:
    _require(
        type(rows) is list and len(rows) == expected_count, f"{label} count differs"
    )
    result = {}
    for row in rows:
        _require(type(row) is dict and key_name in row, f"{label} row differs")
        key = row[key_name]
        _require(key not in result, f"{label} key is duplicated")
        result[key] = row
    return result


def _run_analyzer(root: pathlib.Path) -> tuple[bytes, dict[str, Any]]:
    analyzer = root / ANALYZER_RELATIVE_PATH
    completed = subprocess.run(
        [sys.executable, "-I", "-S", "-B", str(analyzer), str(root)],
        cwd=root,
        check=False,
        capture_output=True,
        timeout=30,
    )
    _require(completed.returncode == 0, "analyzer child rejected")
    _require(completed.stderr == b"", "analyzer child wrote stderr")
    try:
        value = json.loads(completed.stdout)
    except (json.JSONDecodeError, UnicodeError) as error:
        raise IntrinsicAttainabilityReviewError(
            f"analyzer output differs: {error}"
        ) from error
    _require(type(value) is dict, "analyzer output root differs")
    _require(
        completed.stdout == _pretty_bytes(value),
        "analyzer output is not canonical pretty JSON",
    )
    return completed.stdout, value


def _validate_analysis_envelope(
    analysis: dict[str, Any], registry: dict[str, Any]
) -> None:
    identity = analysis["attainability_falsification_id"]
    payload = {
        key: value
        for key, value in analysis.items()
        if key != "attainability_falsification_id"
    }
    _require(
        identity
        == _semantic_id(
            registry["canonicalization_version"],
            registry["measurement_schema_version"],
            (
                "RiskYieldMMRawV8Step2MaximumProtocolV2IntrinsicTemplate"
                "AttainabilityFalsificationV1"
            ),
            payload,
        )
        == EXPECTED_ANALYSIS_ID,
        "analysis semantic identity differs",
    )
    _require(
        analysis["packet"] == "A4-R475-V1-F"
        and analysis["decision"] == "NO_GO_FROZEN_INTRINSIC_P2_ENDPOINTS_UNATTAINABLE"
        and analysis["formal_stage1_state"] == "NO-GO"
        and analysis["intrinsic_case_count"] == 66
        and analysis["contradiction_case_count"] == 26
        and analysis["not_falsified_by_text_ceiling_case_count"] == 40
        and analysis["contradiction_case_positions"] == EXPECTED_POSITIONS
        and analysis["contradiction_vector_sha256"] == EXPECTED_VECTOR_SHA256
        and analysis["all_66_p3_equality_possible"] is False
        and analysis["next_bounded_packet"] == "A4-R475-V1-C",
        "analysis decision envelope differs",
    )
    records = analysis["ordered_contradiction_records"]
    _require(
        _sha256(_canonical_bytes(records)) == EXPECTED_VECTOR_SHA256,
        "contradiction vector differs",
    )
    for row in records:
        _require(
            row["p3_equality_possible"] is False
            and row["language_aware_legal_superset_upper_bound_octets"]
            < row["published_p2_upper_bound_octets"]
            and row["language_aware_legal_superset_upper_bound_octets"]
            + row["unattainable_gap_octets"]
            == row["published_p2_upper_bound_octets"],
            f"contradiction arithmetic differs: {row['case_position']}",
        )


def _case8_scalar_maximum(
    schema: dict[str, Any], languages: dict[str, dict[str, Any]]
) -> int:
    _require(schema["schema_kind"] == "TEXT", "case 8 member is not text")
    language = languages[schema["text_language_id"]]
    kind = language["language_kind"]
    if kind in {"LITERAL", "ENUM"}:
        return max(
            len(_canonical_bytes(value)) for value in language["ordered_literals"]
        )
    _require(kind == "BUILTIN", "case 8 text language is not closed")
    built_in = language["built_in_language_kind"]
    if built_in == "LOWERCASE_SHA256":
        return 66
    if built_in == "RFC3339_UTC":
        return 29
    if built_in == "UINT128_DECIMAL":
        _require(
            language["decimal_maximum"] == str(U128_MAXIMUM), "uint128 maximum differs"
        )
        return 41
    raise IntrinsicAttainabilityReviewError(
        f"case 8 built-in language is unresolved: {built_in}"
    )


def _load_runtime(root: pathlib.Path, runtime_raw: bytes):
    path = root / RUNTIME_RELATIVE_PATH
    specification = importlib.util.spec_from_file_location(
        "_a4_r475_v1_f_independent_runtime", path
    )
    _require(
        specification is not None and specification.loader is not None,
        "runtime import specification differs",
    )
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    code = compile(runtime_raw, str(path), "exec", dont_inherit=True)
    exec(code, module.__dict__)
    return module, module.ExternalSchemaV2Runtime.load(root)


def _review_case8(
    root: pathlib.Path,
    analysis: dict[str, Any],
    seed: dict[str, Any],
    registry: dict[str, Any],
    runtime_raw: bytes,
) -> dict[str, Any]:
    descriptors = _index(
        registry["ordered_external_type_descriptors"],
        "type_name",
        52,
        "external type descriptors",
    )
    schemas = _index(
        registry["value_schema_catalog"],
        "value_schema_id",
        236,
        "value schemas",
    )
    languages = _index(
        registry["text_language_catalog"],
        "text_language_id",
        103,
        "text languages",
    )
    descriptor = descriptors[CASE8_TYPE]
    _require(descriptor["type_form"] == "RECORD", "case 8 descriptor form differs")
    members = descriptor["record_member_descriptors"]
    syntax = 2 + max(0, len(members) - 1)
    scalar_upper_sum = 0
    for member_position, member in enumerate(members, 1):
        _require(
            member["member_position"] == member_position, "case 8 member order differs"
        )
        syntax += len(_canonical_bytes(member["member_name"])) + 1
        scalar_upper_sum += _case8_scalar_maximum(
            schemas[member["value_schema_id"]], languages
        )
    exact_upper = syntax + scalar_upper_sum

    plan = seed["logical_plan_recipe_catalog"]["ordered_logical_count_plan_records"][
        CASE8_POSITION - 1
    ]
    _require(
        plan["case_position"] == CASE8_POSITION
        and plan["case_binding"]["type_name"] == CASE8_TYPE,
        "case 8 plan binding differs",
    )
    templates = _index(
        seed["logical_plan_recipe_catalog"]["ordered_logical_plan_templates"],
        "logical_plan_template_id",
        66,
        "logical templates",
    )
    template = templates[plan["logical_plan_template_id"]]
    root_step = template["ordered_template_steps"][template["root_step_position"] - 1]
    kernels = _index(
        seed["recurrence_catalog"]["ordered_derivation_kernel_records"],
        "derivation_kind",
        18,
        "derivation kernels",
    )
    _require(
        kernels[root_step["derivation_kind"]]["transfer_program"]["opcode"]
        == "CELL_CODEC_INTERSECTION_V1",
        "case 8 root transfer differs",
    )
    coordinate = root_step["recurrence_parameters"]["ordered_codec_coordinate_records"][
        0
    ]
    published_p2 = coordinate["derived_payload_octet_ceiling"]
    _require(
        coordinate["coordinate_scope"] == "SELF_TYPE"
        and coordinate["codec_owner_type_name"] == CASE8_TYPE
        and published_p2 == 524_288,
        "case 8 P2 coordinate differs",
    )

    evidence = analysis["case8_exactness_witness"]
    witness = evidence["witness_record"]
    witness_raw = _canonical_bytes(witness)
    _require(
        exact_upper == len(witness_raw) == evidence["exact_legal_maximum_octets"] == 928
        and _sha256(witness_raw)
        == evidence["exact_legal_maximum_sha256"]
        == EXPECTED_CASE8_SHA256,
        "case 8 exact bound/attainer join differs",
    )
    identity_payload = {
        name: witness[name] for name in descriptor["identity_payload_member_order"]
    }
    recomputed_identity = _semantic_id(
        registry["canonicalization_version"],
        registry["measurement_schema_version"],
        descriptor["described_record_domain"],
        identity_payload,
    )
    _require(
        witness[descriptor["identity_field"]] == recomputed_identity,
        "case 8 standalone identity differs",
    )
    runtime_module, runtime = _load_runtime(root, runtime_raw)
    try:
        declared = runtime.validate_type(CASE8_TYPE, witness)
        evaluation = runtime.evaluate_rule(
            descriptor["ordered_intrinsic_rule_ids"][0], {"self": witness}
        )
    except runtime_module.RuntimeFailure as error:
        raise IntrinsicAttainabilityReviewError(
            f"case 8 typed runtime rejected: {error}"
        ) from error
    _require(
        declared.type_name == CASE8_TYPE and evaluation.root_value is True,
        "case 8 typed runtime evidence differs",
    )
    _require(exact_upper < published_p2, "case 8 contradiction disappeared")
    return {
        "case_position": CASE8_POSITION,
        "type_name": CASE8_TYPE,
        "published_p2_upper_bound_octets": published_p2,
        "independently_derived_exact_legal_maximum_octets": exact_upper,
        "independent_legal_attainer_octets": len(witness_raw),
        "independent_legal_attainer_sha256": _sha256(witness_raw),
        "unattainable_gap_octets": published_p2 - exact_upper,
        "typed_runtime_sha256": RUNTIME_RAW_SHA256,
        "typed_runtime_accepted": True,
        "intrinsic_rule_root": True,
        "standalone_identity_recomputed": True,
        "p3_equality_possible": False,
    }


def review(root: pathlib.Path) -> dict[str, Any]:
    root = pathlib.Path(root).resolve()
    _load_raw(root, ANALYZER_RELATIVE_PATH, ANALYZER_RAW_OCTETS, ANALYZER_RAW_SHA256)
    seed = _load_json(root, SEED_RELATIVE_PATH, SEED_RAW_OCTETS, SEED_RAW_SHA256)
    registry = _load_json(
        root, REGISTRY_RELATIVE_PATH, REGISTRY_RAW_OCTETS, REGISTRY_RAW_SHA256
    )
    contract = _load_json(
        root, CONTRACT_RELATIVE_PATH, CONTRACT_RAW_OCTETS, CONTRACT_RAW_SHA256
    )
    runtime_raw = _load_raw(
        root, RUNTIME_RELATIVE_PATH, RUNTIME_RAW_OCTETS, RUNTIME_RAW_SHA256
    )
    _require(
        contract["candidate_and_result_contract"][
            "unattained_or_unresolved_case_policy"
        ]
        == "COMPLETE_CAMPAIGN_NO_GO_WITHOUT_LIMIT_OR_AUTHORITY_REPAIR",
        "campaign unattained-case policy differs",
    )
    v1_packet = contract["implementation_sequence_contract"]["ordered_packet_records"][
        1
    ]
    _require(
        v1_packet
        == {
            "packet": "A4-R475-V1",
            "packet_position": 2,
            "scope": "ALL_66_INTRINSIC_TEMPLATE_CASES_PLUS_SIX_CASE_REGRESSION",
        },
        "campaign V1 scope differs",
    )

    first_raw, first = _run_analyzer(root)
    second_raw, second = _run_analyzer(root)
    _require(first_raw == second_raw and first == second, "analyzer replay differs")
    _validate_analysis_envelope(first, registry)
    case8_review = _review_case8(root, first, seed, registry, runtime_raw)

    result = {
        "review_version": (
            "riskyieldmm.raw_v8_step2.maximum_protocol_v2."
            "intrinsic_template_attainability_falsification_acceptance.v1"
        ),
        "packet": "A4-R475-V1-F-A",
        "decision": "ACCEPTED_FALSIFICATION_AUTHORITY_REPAIR_REQUIRED",
        "accepted_scope": "FALSIFICATION_ONLY_NO_AUTHORITY_REPAIR",
        "formal_stage1_state": "NO-GO",
        "analyzer_raw_octets": ANALYZER_RAW_OCTETS,
        "analyzer_raw_sha256": ANALYZER_RAW_SHA256,
        "analyzer_output_raw_octets": len(first_raw),
        "analyzer_output_raw_sha256": _sha256(first_raw),
        "analyzer_two_run_byte_identical": True,
        "attainability_falsification_id": first["attainability_falsification_id"],
        "contradiction_case_count": first["contradiction_case_count"],
        "contradiction_case_positions": first["contradiction_case_positions"],
        "contradiction_vector_sha256": first["contradiction_vector_sha256"],
        "case8_independent_review": case8_review,
        "campaign_unattained_case_policy_enforced": True,
        "all_case_v1_acceptance_possible_under_frozen_authority": False,
        "accepted_six_case_verifier_unchanged": True,
        "producer_runner_or_campaign_implemented": False,
        "next_bounded_packet": "A4-R475-V1-C",
    }
    result["acceptance_report_id"] = _semantic_id(
        registry["canonicalization_version"],
        registry["measurement_schema_version"],
        REVIEW_DOMAIN,
        result,
    )
    return result


def _main(argv: list[str]) -> int:
    if len(argv) != 1:
        sys.stderr.write("usage: reviewer REPOSITORY_ROOT\n")
        return 2
    try:
        result = review(pathlib.Path(argv[0]))
    except (
        IntrinsicAttainabilityReviewError,
        OSError,
        subprocess.SubprocessError,
    ) as error:
        sys.stderr.write(f"intrinsic-attainability review failed: {error}\n")
        return 1
    sys.stdout.buffer.write(_pretty_bytes(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
