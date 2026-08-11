#!/usr/bin/env python3
"""Independently review the A4-R475-V1-C1 correction contract.

The reviewer never imports the contract generator.  It reconstructs every
case, step, dependency, semantic identity, aggregate, and successor boundary
from the pinned seed, registry, campaign contract, and falsification report.
It also executes the generator twice only through its public check-mode CLI.
"""

from __future__ import annotations

import ast
import hashlib
import json
import pathlib
import subprocess
import sys
from collections import Counter
from typing import Any

REVIEW_DOMAIN = (
    "RiskYieldMMRawV8Step2MaximumProtocolV2"
    "IntrinsicExactnessCorrectionContractAcceptanceReportV1"
)
CONTRACT_DOMAIN = (
    "RiskYieldMMRawV8Step2MaximumProtocolV2"
    "IntrinsicExactnessCorrectionContractV1"
)
CASE_DOMAIN = (
    "RiskYieldMMRawV8Step2MaximumProtocolV2"
    "IntrinsicExactnessCorrectionCaseV1"
)
STEP_DOMAIN = (
    "RiskYieldMMRawV8Step2MaximumProtocolV2"
    "IntrinsicExactnessCorrectionStepV1"
)
LOCAL_DEPENDENCY_DOMAIN = (
    "RiskYieldMMRawV8Step2MaximumProtocolV2"
    "IntrinsicExactnessLocalDependencyV1"
)
IDENTITY_DEPENDENCY_DOMAIN = (
    "RiskYieldMMRawV8Step2MaximumProtocolV2"
    "IntrinsicExactnessIdentityDependencyV1"
)

GENERATOR = (
    "scripts/tests/generate_raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_correction_contract_v49f.py"
)
CONTRACT = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_correction_contract_v49f.json"
)
SEED = "scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json"
REGISTRY = "scripts/tests/raw_v8_step2_external_schema_v2_structural_registry_v49f.json"
CAMPAIGN = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "all_case_campaign_contract_v49f.json"
)
FALSIFICATION = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_template_attainability_acceptance_report_v49f.json"
)

PINNED = {
    "GENERATOR": (
        GENERATOR,
        38_248,
        "b9db5b3b84c26ad20764d7e8bea0fc8aef19209c6d177c15356311068fc2ec8f",
    ),
    "CONTRACT": (
        CONTRACT,
        5_436_266,
        "6245595b759cec6cdecd88292f105dac938f5c69ae92f90ae0365bd032180e14",
    ),
    "SEED": (
        SEED,
        13_419_905,
        "a75a2f352e8513b7ff0043693a0c65ebbf4bc6f06859354789af69e1162b0e4f",
    ),
    "REGISTRY": (
        REGISTRY,
        1_469_663,
        "9160297ff316c5931737c92f8b359f0a1e2ec22f0aa996ef3b09cf830dc96bf3",
    ),
    "CAMPAIGN": (
        CAMPAIGN,
        382_710,
        "3ca4ff4d6e581895b813043e7fdeed24c33cf2c828e362ac81de1725e95a84bb",
    ),
    "FALSIFICATION": (
        FALSIFICATION,
        2_137,
        "a56bd57e795f5c6cda9eed5d8c9512392bff6e0a2637c5fe69fc42508c1ff9ea",
    ),
}

EXPECTED_CONTRADICTIONS = [
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

DEPENDENCY_KIND_ORDER = {
    name: position
    for position, name in enumerate(
        (
            "VALUE_SCHEMA",
            "TEXT_LANGUAGE",
            "ASCII_DFA",
            "UNICODE_IDENTIFIER_PROFILE",
            "UNICODE_SOURCE",
            "INTRINSIC_RULE",
            "TYPE_DESCRIPTOR",
            "IDENTITY_CONTRACT",
            "ARRAY_BATCH",
            "UNION_BRANCH",
            "CODEC_COORDINATE_SET",
        ),
        start=1,
    )
}


class ReviewFailure(ValueError):
    """Fail-closed independent review rejection."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ReviewFailure(message)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


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


def _load_raw(root: pathlib.Path, name: str) -> bytes:
    relative_path, octets, digest = PINNED[name]
    path = root / relative_path
    _require(path.is_file() and not path.is_symlink(), f"{name} absent")
    raw = path.read_bytes()
    _require(len(raw) == octets, f"{name} size drifted")
    _require(_sha256(raw) == digest, f"{name} hash drifted")
    return raw


def _load_json(root: pathlib.Path, name: str) -> dict[str, Any]:
    raw = _load_raw(root, name)
    value = json.loads(raw)
    _require(isinstance(value, dict), f"{name} root differs")
    _require(_pretty_bytes(value) == raw, f"{name} encoding differs")
    return value


def _index(
    records: list[dict[str, Any]], key: str
) -> tuple[dict[str, dict[str, Any]], dict[str, int]]:
    values: dict[str, dict[str, Any]] = {}
    positions: dict[str, int] = {}
    for position, record in enumerate(records, start=1):
        identifier = record[key]
        _require(identifier not in values, f"duplicate authority ID {identifier}")
        values[identifier] = record
        positions[identifier] = position
    return values, positions


def _registry_dependency(
    kind: str,
    identifier: str,
    catalog: str,
    position: int,
    record: dict[str, Any],
) -> dict[str, Any]:
    return {
        "authority_catalog": catalog,
        "authority_position": position,
        "authority_record_sha256": _sha256(_canonical_bytes(record)),
        "dependency_id": identifier,
        "dependency_kind": kind,
    }


def _local_dependency(
    canonicalization_version: str,
    schema_version: str,
    case_position: int,
    step_position: int,
    kind: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    envelope = {
        "case_position": case_position,
        "dependency_kind": kind,
        "payload": payload,
        "step_position": step_position,
    }
    return {
        "authority_catalog": "FROZEN_LOGICAL_PLAN_TEMPLATE_STEP",
        "authority_position": step_position,
        "authority_record_sha256": _sha256(_canonical_bytes(payload)),
        "dependency_id": _semantic_id(
            canonicalization_version,
            schema_version,
            LOCAL_DEPENDENCY_DOMAIN,
            envelope,
        ),
        "dependency_kind": kind,
    }


def _add(
    dependencies: dict[tuple[str, str], dict[str, Any]],
    dependency: dict[str, Any],
) -> dict[str, str]:
    key = (dependency["dependency_kind"], dependency["dependency_id"])
    previous = dependencies.setdefault(key, dependency)
    _require(previous == dependency, f"dependency collision {key!r}")
    return {"dependency_id": key[1], "dependency_kind": key[0]}


def _review_generator_source(root: pathlib.Path) -> None:
    source = _load_raw(root, "GENERATOR").decode("utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported.update(
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    )
    for forbidden in (
        "intrinsic_template_attainability",
        "verify_raw_v8_step2",
        "produce_raw_v8_step2",
        "validate_raw_v8_step2",
    ):
        _require(
            all(forbidden not in name for name in imported),
            f"generator imports {forbidden}",
        )
    for marker in (
        "DEPENDENCY_AND_SUCCESSOR_INTERFACE_ONLY",
        "cross_channel_code_sharing_policy",
        "accepted_predecessor_edit_policy",
        "A4-R475-V1-C2-S",
    ):
        _require(marker in source, f"generator marker absent: {marker}")


def _run_generator_check(root: pathlib.Path) -> tuple[int, bytes, bytes]:
    completed = subprocess.run(
        [
            sys.executable,
            str(root / GENERATOR),
            "--repository-root",
            str(root),
            "--check",
            str(root / CONTRACT),
        ],
        cwd=root,
        check=False,
        capture_output=True,
    )
    return completed.returncode, completed.stdout, completed.stderr


def _reconstruct_cases(
    contract: dict[str, Any],
    seed: dict[str, Any],
    registry: dict[str, Any],
    campaign: dict[str, Any],
    contradiction_positions: list[int],
) -> tuple[list[dict[str, Any]], Counter[str], Counter[str]]:
    canonicalization_version = registry["canonicalization_version"]
    schema_version = registry["measurement_schema_version"]
    recipes = seed["logical_plan_recipe_catalog"]
    templates = recipes["ordered_logical_plan_templates"]
    plans = recipes["ordered_logical_count_plan_records"][:66]
    executions = campaign["case_universe_contract"][
        "ordered_case_execution_records"
    ][:66]
    reviewed_cases = contract["ordered_intrinsic_case_records"]
    _require(len(templates) == len(plans) == len(executions) == 66, "source census differs")
    _require(len(reviewed_cases) == 66, "contract case census differs")

    value_schemas, value_positions = _index(
        registry["value_schema_catalog"], "value_schema_id"
    )
    text_languages, text_positions = _index(
        registry["text_language_catalog"], "text_language_id"
    )
    dfas, dfa_positions = _index(registry["ascii_dfa_catalog"], "ascii_dfa_id")
    profiles, profile_positions = _index(
        registry["identifier_profile_catalog"], "unicode_identifier_profile_id"
    )
    unicode_sources, unicode_positions = _index(
        registry["unicode_source_catalog"], "unicode_source_record_id"
    )
    rules, rule_positions = _index(
        registry["ordered_cross_field_rule_descriptors"], "rule_id"
    )
    types_by_name, type_positions = _index(
        registry["ordered_external_type_descriptors"], "type_name"
    )
    types_by_id, _ = _index(
        registry["ordered_external_type_descriptors"],
        "external_type_descriptor_id",
    )

    reviewed: list[dict[str, Any]] = []
    dependency_counts: Counter[str] = Counter()
    step_counts: Counter[str] = Counter()
    for case_position, (case, template, plan, execution) in enumerate(
        zip(reviewed_cases, templates, plans, executions, strict=True), start=1
    ):
        _require(case["case_position"] == case_position, "case position differs")
        _require(template["template_position"] == case_position, "template position differs")
        _require(plan["case_position"] == case_position, "plan position differs")
        _require(execution["case_position"] == case_position, "execution position differs")
        _require(
            case["logical_plan_template_id"] == template["logical_plan_template_id"]
            and case["logical_count_plan_id"] == plan["logical_count_plan_id"]
            and case["case_execution_record_id"] == execution["case_execution_record_id"]
            and case["root_step_position"] == template["root_step_position"]
            and case["root_type_name"] == template["root_type_name"]
            and case["type_name"] == execution["type_name"]
            and case["alternative_name"] == execution["alternative_name"]
            and case["row_kind"] == execution["row_kind"],
            f"case authority differs: {case_position}",
        )
        expected_status = (
            "FROZEN_P2_ENDPOINT_CONTRADICTED"
            if case_position in contradiction_positions
            else "EXACTNESS_UNRESOLVED_NOT_ACCEPTED"
        )
        _require(case["correction_status"] == expected_status, "case status differs")
        _require(
            case["ordered_relaxation_application_records"]
            == template["ordered_relaxation_application_records"],
            f"case relaxation schedule differs: {case_position}",
        )

        dependencies: dict[tuple[str, str], dict[str, Any]] = {}

        def add_registry(
            kind: str,
            identifier: str,
            catalog: str,
            position: int,
            record: dict[str, Any],
            _dependencies: dict[tuple[str, str], dict[str, Any]] = dependencies,
        ) -> dict[str, str]:
            return _add(
                _dependencies,
                _registry_dependency(kind, identifier, catalog, position, record),
            )

        def add_type(
            type_name: str,
            _dependencies: dict[tuple[str, str], dict[str, Any]] = dependencies,
        ) -> list[dict[str, str]]:
            descriptor = types_by_name[type_name]
            references = [
                add_registry(
                    "TYPE_DESCRIPTOR",
                    descriptor["external_type_descriptor_id"],
                    "ordered_external_type_descriptors",
                    type_positions[type_name],
                    descriptor,
                )
            ]
            if descriptor["identity_field"] is not None:
                payload = {
                    "described_record_domain": descriptor["described_record_domain"],
                    "external_type_descriptor_id": descriptor[
                        "external_type_descriptor_id"
                    ],
                    "identity_field": descriptor["identity_field"],
                    "identity_payload_member_order": descriptor[
                        "identity_payload_member_order"
                    ],
                    "type_name": descriptor["type_name"],
                }
                identity_id = _semantic_id(
                    canonicalization_version,
                    schema_version,
                    IDENTITY_DEPENDENCY_DOMAIN,
                    payload,
                )
                references.append(
                    _add(
                        _dependencies,
                        {
                            "authority_catalog": "DERIVED_IDENTITY_CONTRACT",
                            "authority_position": type_positions[type_name],
                            "authority_record_sha256": _sha256(
                                _canonical_bytes(payload)
                            ),
                            "dependency_id": identity_id,
                            "dependency_kind": "IDENTITY_CONTRACT",
                        },
                    )
                )
            return references

        steps = case["ordered_step_contract_records"]
        source_steps = template["ordered_template_steps"]
        _require(len(steps) == len(source_steps), f"step count differs: {case_position}")
        for step_position, (step, source) in enumerate(
            zip(steps, source_steps, strict=True), start=1
        ):
            references: list[dict[str, str]] = []
            for key in (
                "alternative_name",
                "derivation_kind",
                "logical_derivation_step_id",
                "ordered_child_step_positions",
                "ordered_intrinsic_rule_ids",
                "recurrence_parameters",
                "subject_locator",
                "type_name",
                "value_schema_id",
            ):
                _require(step[key] == source[key], f"step field differs: {case_position}/{step_position}/{key}")
            _require(step["step_position"] == step_position, "step position differs")
            _require(
                all(child < step_position for child in step["ordered_child_step_positions"]),
                "step postorder differs",
            )
            value_schema_id = source["value_schema_id"]
            if value_schema_id is not None:
                references.append(
                    add_registry(
                        "VALUE_SCHEMA",
                        value_schema_id,
                        "value_schema_catalog",
                        value_positions[value_schema_id],
                        value_schemas[value_schema_id],
                    )
                )
            parameters = source["recurrence_parameters"]
            text_id = parameters.get("text_language_id")
            if text_id is not None:
                language = text_languages[text_id]
                _require(
                    parameters["text_language_position"] == text_positions[text_id],
                    "text-language position differs",
                )
                references.append(
                    add_registry(
                        "TEXT_LANGUAGE",
                        text_id,
                        "text_language_catalog",
                        text_positions[text_id],
                        language,
                    )
                )
                dfa_id = language["ascii_dfa_id"]
                if dfa_id is not None:
                    references.append(
                        add_registry(
                            "ASCII_DFA",
                            dfa_id,
                            "ascii_dfa_catalog",
                            dfa_positions[dfa_id],
                            dfas[dfa_id],
                        )
                    )
                profile_id = language["unicode_identifier_profile_id"]
                if profile_id is not None:
                    profile = profiles[profile_id]
                    references.append(
                        add_registry(
                            "UNICODE_IDENTIFIER_PROFILE",
                            profile_id,
                            "identifier_profile_catalog",
                            profile_positions[profile_id],
                            profile,
                        )
                    )
                    for source_id in profile["unicode_source_record_ids"]:
                        references.append(
                            add_registry(
                                "UNICODE_SOURCE",
                                source_id,
                                "unicode_source_catalog",
                                unicode_positions[source_id],
                                unicode_sources[source_id],
                            )
                        )
            for rule_id in source["ordered_intrinsic_rule_ids"]:
                references.append(
                    add_registry(
                        "INTRINSIC_RULE",
                        rule_id,
                        "ordered_cross_field_rule_descriptors",
                        rule_positions[rule_id],
                        rules[rule_id],
                    )
                )
            type_names = []
            for type_name in (
                source["type_name"],
                parameters.get("referenced_type_name"),
                parameters.get("owner_type_name"),
            ):
                if type_name is not None and type_name not in type_names:
                    type_names.append(type_name)
            for type_name in type_names:
                references.extend(add_type(type_name))
            local_kind = {
                "ASSOCIATIVE_HOMOGENEOUS_RUN_BATCH": "ARRAY_BATCH",
                "TAGGED_UNION_BRANCH": "UNION_BRANCH",
                "CODEC_INTERSECTION": "CODEC_COORDINATE_SET",
            }.get(source["derivation_kind"])
            if local_kind is not None:
                references.append(
                    _add(
                        dependencies,
                        _local_dependency(
                            canonicalization_version,
                            schema_version,
                            case_position,
                            step_position,
                            local_kind,
                            {
                                "alternative_name": source["alternative_name"],
                                "recurrence_parameters": parameters,
                                "subject_locator": source["subject_locator"],
                                "type_name": source["type_name"],
                                "value_schema_id": source["value_schema_id"],
                            },
                        ),
                    )
                )
            expected_references = sorted(
                references,
                key=lambda row: (
                    DEPENDENCY_KIND_ORDER[row["dependency_kind"]],
                    row["dependency_id"],
                ),
            )
            _require(
                step["ordered_dependency_references"] == expected_references,
                f"step dependency references differ: {case_position}/{step_position}",
            )
            step_payload = {
                name: value
                for name, value in step.items()
                if name != "correction_step_id"
            }
            _require(
                step["correction_step_id"]
                == _semantic_id(
                    canonicalization_version,
                    schema_version,
                    STEP_DOMAIN,
                    step_payload,
                ),
                f"step identity differs: {case_position}/{step_position}",
            )
            step_counts[source["derivation_kind"]] += 1

        for relaxation in template["ordered_relaxation_application_records"]:
            if relaxation["predicate_kind"] == "PAYLOAD_DERIVED_IDENTITY_EQUALITY":
                descriptor = types_by_id[relaxation["authority_predicate_id"]]
                _require(descriptor["identity_field"] is not None, "identity predicate differs")
                add_type(descriptor["type_name"])

        expected_dependencies = sorted(
            dependencies.values(),
            key=lambda row: (
                DEPENDENCY_KIND_ORDER[row["dependency_kind"]],
                row["dependency_id"],
            ),
        )
        for position, dependency in enumerate(expected_dependencies, start=1):
            dependency["dependency_position"] = position
        _require(
            case["ordered_authority_dependency_records"] == expected_dependencies,
            f"case dependency census differs: {case_position}",
        )
        dependency_counts.update(
            row["dependency_kind"] for row in expected_dependencies
        )
        case_payload = {
            name: value
            for name, value in case.items()
            if name != "intrinsic_correction_case_id"
        }
        _require(
            case["intrinsic_correction_case_id"]
            == _semantic_id(
                canonicalization_version,
                schema_version,
                CASE_DOMAIN,
                case_payload,
            ),
            f"case identity differs: {case_position}",
        )
        reviewed.append(case)
    return reviewed, dependency_counts, step_counts


def review(root: pathlib.Path) -> dict[str, Any]:
    root = pathlib.Path(root).resolve()
    _review_generator_source(root)
    contract = _load_json(root, "CONTRACT")
    seed = _load_json(root, "SEED")
    registry = _load_json(root, "REGISTRY")
    campaign = _load_json(root, "CAMPAIGN")
    falsification = _load_json(root, "FALSIFICATION")
    canonicalization_version = registry["canonicalization_version"]
    schema_version = registry["measurement_schema_version"]

    first_check = _run_generator_check(root)
    second_check = _run_generator_check(root)
    _require(first_check == second_check == (0, b"", b""), "generator check replay differs")

    payload = {
        name: value
        for name, value in contract.items()
        if name != "intrinsic_exactness_correction_contract_id"
    }
    contract_id = _semantic_id(
        canonicalization_version,
        schema_version,
        CONTRACT_DOMAIN,
        payload,
    )
    _require(
        contract["intrinsic_exactness_correction_contract_id"]
        == contract_id
        == "171e9d47a7733f8448f94af5a16da4ba5258f30ee08cb4c835289a05adcb8cb9",
        "contract identity differs",
    )
    _require(
        falsification["contradiction_case_positions"] == EXPECTED_CONTRADICTIONS,
        "accepted contradiction vector differs",
    )
    reviewed, dependency_counts, step_counts = _reconstruct_cases(
        contract,
        seed,
        registry,
        campaign,
        EXPECTED_CONTRADICTIONS,
    )
    case_vector_sha = _sha256(_canonical_bytes(reviewed))
    _require(
        case_vector_sha == contract["ordered_intrinsic_case_records_sha256"],
        "case-vector identity differs",
    )
    aggregate = contract["aggregate_dependency_census"]
    _require(
        aggregate["dependency_kind_counts"] == dict(sorted(dependency_counts.items()))
        and aggregate["step_derivation_kind_counts"] == dict(sorted(step_counts.items()))
        and aggregate["total_case_dependency_records"] == sum(dependency_counts.values())
        and aggregate["total_step_records"] == sum(step_counts.values()),
        "aggregate census differs",
    )
    _require(
        contract["acceptance_contract"]["all_66_exact_maxima_accepted"] is False
        and contract["acceptance_contract"]["all_case_campaign_released"] is False
        and contract["successor_authority_contract"]
        ["verifier_producer_runner_or_campaign_implemented_by_c1"]
        is False
        and contract["successor_authority_contract"][
            "accepted_predecessor_edit_policy"
        ]
        == "FORBIDDEN"
        and contract["dual_channel_contract"]["cross_channel_code_sharing_policy"]
        == "FORBIDDEN"
        and contract["dual_channel_contract"]["pre_execution_source_freeze"]
        == {
            "both_channel_sources_and_output_schemas_frozen_before_execution": True,
            "channel_output_allowed_during_source_freeze": False,
            "mutual_import_read_or_generated_witness_access_policy": "FORBIDDEN",
            "required_packet": "A4-R475-V1-C2-S",
        }
        and contract["dual_channel_contract"]["upper_channel"][
            "source_must_not_read_attainer_output"
        ]
        is True
        and contract["dual_channel_contract"]["attainer_channel"][
            "candidate_source_must_not_read_upper_output"
        ]
        is True
        and contract["next_bounded_packet"] == "A4-R475-V1-C2-S"
        and contract["formal_stage1_state"] == "NO-GO",
        "contract nonclaim or successor boundary differs",
    )
    resources = contract["resource_contract"]
    _require(
        resources["authority_file_count"] == 8
        and resources["authority_file_limit"] == 64
        and resources["pinned_input_octets"] == 15_869_888
        and resources["pinned_input_octet_limit"] == 67_108_864
        and PINNED["CONTRACT"][1] <= resources["contract_raw_octet_limit"],
        "resource boundary differs",
    )

    result: dict[str, Any] = {
        "acceptance_scope": "C1_DEPENDENCY_AND_SUCCESSOR_INTERFACE_ONLY",
        "all_66_exact_maxima_accepted": False,
        "all_case_campaign_released": False,
        "case_vector_sha256": case_vector_sha,
        "contract_id": contract_id,
        "contract_raw_octets": PINNED["CONTRACT"][1],
        "contract_raw_sha256": PINNED["CONTRACT"][2],
        "contradiction_case_count": len(EXPECTED_CONTRADICTIONS),
        "decision": "ACCEPTED_CONTRACT_ONLY",
        "dependency_kind_counts": dict(sorted(dependency_counts.items())),
        "formal_stage1_state": "NO-GO",
        "generator_check_replay_count": 2,
        "generator_check_replays_identical_and_silent": True,
        "generator_raw_octets": PINNED["GENERATOR"][1],
        "generator_raw_sha256": PINNED["GENERATOR"][2],
        "intrinsic_case_count": len(reviewed),
        "next_bounded_packet": "A4-R475-V1-C2-S",
        "not_falsified_nonclaim_case_count": 40,
        "packet": "A4-R475-V1-C1-A",
        "review_version": (
            "riskyieldmm.raw_v8_step2.maximum_protocol_v2."
            "intrinsic_exactness_correction_contract_acceptance.v1"
        ),
        "step_derivation_kind_counts": dict(sorted(step_counts.items())),
        "total_case_dependency_records": sum(dependency_counts.values()),
        "total_step_records": sum(step_counts.values()),
    }
    result["acceptance_report_id"] = _semantic_id(
        canonicalization_version,
        schema_version,
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
    except (ReviewFailure, OSError, ValueError, TypeError, KeyError) as error:
        sys.stderr.write(f"INTRINSIC_CORRECTION_REVIEW_REJECTED: {error}\n")
        return 1
    sys.stdout.buffer.write(_pretty_bytes(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
