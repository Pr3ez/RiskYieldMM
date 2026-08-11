#!/usr/bin/env python3
"""Build the A4-R475-V1-C1 intrinsic exactness-correction contract.

The generator is data-only.  It imports no analyzer, verifier, producer,
runner, runtime, or seed generator.  It reconstructs the complete dependency
surface of the 66 frozen intrinsic templates from byte-pinned authorities and
freezes the interfaces required by independent upper, attainer, and exactness
join packets.  It does not claim that any unresolved maximum is exact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import sys
from collections import Counter
from typing import Any

SOURCE_MARKER = "A4_R475_V1_C1_INTRINSIC_CORRECTION_CONTRACT_GENERATOR_V1"
ERROR_PREFIX = "RAW_V8_STEP2_MAXIMUM_PROTOCOL_V2_INTRINSIC_CORRECTION_"
CONTRACT_VERSION = (
    "riskyieldmm.raw_v8_step2.maximum_protocol_v2."
    "intrinsic_exactness_correction_contract.v1"
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

INTRINSIC_CASE_COUNT = 66
CONTRADICTION_CASE_COUNT = 26
NOT_FALSIFIED_CASE_COUNT = 40
EXPECTED_CONTRADICTION_POSITIONS = [
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

AUTHORITIES: dict[str, tuple[str, int, str]] = {
    "SEED": (
        "scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json",
        13_419_905,
        "a75a2f352e8513b7ff0043693a0c65ebbf4bc6f06859354789af69e1162b0e4f",
    ),
    "REGISTRY": (
        "scripts/tests/raw_v8_step2_external_schema_v2_structural_registry_v49f.json",
        1_469_663,
        "9160297ff316c5931737c92f8b359f0a1e2ec22f0aa996ef3b09cf830dc96bf3",
    ),
    "ALL_CASE_CONTRACT": (
        "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
        "all_case_campaign_contract_v49f.json",
        382_710,
        "3ca4ff4d6e581895b813043e7fdeed24c33cf2c828e362ac81de1725e95a84bb",
    ),
    "FALSIFICATION_ACCEPTANCE_REPORT": (
        "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
        "intrinsic_template_attainability_acceptance_report_v49f.json",
        2_137,
        "a56bd57e795f5c6cda9eed5d8c9512392bff6e0a2637c5fe69fc42508c1ff9ea",
    ),
    "ALL_CASE_V0_VERIFIER": (
        "scripts/tests/verify_raw_v8_step2_maximum_protocol_v2_"
        "all_case_candidate_v49f.py",
        42_659,
        "15adb9fd5c427c1e1e96ff630e13b36d3f385f12eaf68a388a5da7be48dbf5aa",
    ),
    "PILOT_PRODUCER": (
        "scripts/tests/produce_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py",
        129_026,
        "46c67738905488a467cbb66a6de719f4cd4804e7ac68143cb301dc1e9c46d7da",
    ),
    "PILOT_VERIFIER": (
        "scripts/tests/verify_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py",
        373_327,
        "b1bfb5778b1408c4b2dc45dd008f1089e2405b503b7eee9686820535d5631d25",
    ),
    "PILOT_RUNNER": (
        "scripts/tests/run_raw_v8_step2_maximum_protocol_v2_pilot_v49f.py",
        50_461,
        "5f1997b4e689a14cbae0a340fce2f320bb058eb9dd04449897ff3dfdf8de7ad7",
    ),
}

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


class ContractFailure(ValueError):
    """Fail-closed correction-contract construction rejection."""


def _require(condition: bool, code: str, detail: str = "") -> None:
    if not condition:
        raise ContractFailure(f"{code}: {detail}" if detail else code)


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


def _duplicate_guard(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, value in pairs:
        _require(name not in result, "DUPLICATE_JSON_KEY", name)
        result[name] = value
    return result


def _reject_number(value: str) -> Any:
    raise ContractFailure(f"JSON_NUMBER_INVALID: {value}")


def _strict_json(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_duplicate_guard,
            parse_constant=_reject_number,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ContractFailure(f"{label}_JSON_INVALID: {error}") from error
    _require(isinstance(value, dict), f"{label}_ROOT_INVALID")
    _require(_pretty_bytes(value) == raw, f"{label}_ENCODING_INVALID")
    return value


def _load_authorities(root: pathlib.Path) -> tuple[dict[str, bytes], dict[str, Any]]:
    raw_by_name: dict[str, bytes] = {}
    json_by_name: dict[str, Any] = {}
    for name, (relative_path, octets, digest) in AUTHORITIES.items():
        path = root / relative_path
        _require(path.is_file() and not path.is_symlink(), "AUTHORITY_ABSENT", name)
        raw = path.read_bytes()
        _require(len(raw) == octets, "AUTHORITY_SIZE_DRIFT", name)
        _require(_sha256(raw) == digest, "AUTHORITY_HASH_DRIFT", name)
        raw_by_name[name] = raw
        if relative_path.endswith(".json"):
            json_by_name[name] = _strict_json(raw, name)
    return raw_by_name, json_by_name


def _index(
    records: list[dict[str, Any]],
    key: str,
    label: str,
) -> tuple[dict[Any, dict[str, Any]], dict[Any, int]]:
    by_id: dict[Any, dict[str, Any]] = {}
    positions: dict[Any, int] = {}
    for position, record in enumerate(records, start=1):
        identifier = record.get(key)
        _require(identifier is not None, f"{label}_ID_ABSENT", str(position))
        _require(identifier not in by_id, f"{label}_ID_DUPLICATE", str(identifier))
        by_id[identifier] = record
        positions[identifier] = position
    return by_id, positions


def _registry_dependency(
    *,
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
    identifier = _semantic_id(
        canonicalization_version,
        schema_version,
        LOCAL_DEPENDENCY_DOMAIN,
        envelope,
    )
    return {
        "authority_catalog": "FROZEN_LOGICAL_PLAN_TEMPLATE_STEP",
        "authority_position": step_position,
        "authority_record_sha256": _sha256(_canonical_bytes(payload)),
        "dependency_id": identifier,
        "dependency_kind": kind,
    }


def _add_dependency(
    dependencies: dict[tuple[str, str], dict[str, Any]],
    dependency: dict[str, Any],
) -> dict[str, str]:
    key = (dependency["dependency_kind"], dependency["dependency_id"])
    previous = dependencies.setdefault(key, dependency)
    _require(previous == dependency, "DEPENDENCY_COLLISION", repr(key))
    return {"dependency_id": key[1], "dependency_kind": key[0]}


def _build_case(
    *,
    canonicalization_version: str,
    schema_version: str,
    template: dict[str, Any],
    plan: dict[str, Any],
    execution: dict[str, Any],
    contradiction_positions: set[int],
    value_schemas: dict[str, dict[str, Any]],
    value_positions: dict[str, int],
    text_languages: dict[str, dict[str, Any]],
    text_positions: dict[str, int],
    dfas: dict[str, dict[str, Any]],
    dfa_positions: dict[str, int],
    profiles: dict[str, dict[str, Any]],
    profile_positions: dict[str, int],
    unicode_sources: dict[str, dict[str, Any]],
    unicode_positions: dict[str, int],
    rules: dict[str, dict[str, Any]],
    rule_positions: dict[str, int],
    types_by_name: dict[str, dict[str, Any]],
    type_name_positions: dict[str, int],
    types_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    case_position = plan["case_position"]
    _require(case_position == template["template_position"], "TEMPLATE_POSITION_DRIFT")
    _require(case_position == execution["case_position"], "EXECUTION_POSITION_DRIFT")
    _require(
        plan["logical_plan_template_id"] == template["logical_plan_template_id"],
        "PLAN_TEMPLATE_ID_DRIFT",
        str(case_position),
    )
    _require(
        execution["effective_logical_count_plan_id"]
        == plan["logical_count_plan_id"],
        "EXECUTION_PLAN_ID_DRIFT",
        str(case_position),
    )
    _require(
        execution["execution_family"] == "INTRINSIC_TEMPLATE_ATTAINMENT",
        "EXECUTION_FAMILY_INVALID",
        str(case_position),
    )

    dependencies: dict[tuple[str, str], dict[str, Any]] = {}
    steps: list[dict[str, Any]] = []

    def add_registry(
        kind: str,
        identifier: str,
        catalog: str,
        position: int,
        record: dict[str, Any],
    ) -> dict[str, str]:
        return _add_dependency(
            dependencies,
            _registry_dependency(
                kind=kind,
                identifier=identifier,
                catalog=catalog,
                position=position,
                record=record,
            ),
        )

    def add_type(type_name: str) -> list[dict[str, str]]:
        descriptor = types_by_name.get(type_name)
        _require(descriptor is not None, "TYPE_DESCRIPTOR_UNRESOLVED", type_name)
        references = [
            add_registry(
                "TYPE_DESCRIPTOR",
                descriptor["external_type_descriptor_id"],
                "ordered_external_type_descriptors",
                type_name_positions[type_name],
                descriptor,
            )
        ]
        if descriptor["identity_field"] is not None:
            identity_payload = {
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
                identity_payload,
            )
            references.append(
                _add_dependency(
                    dependencies,
                    {
                        "authority_catalog": "DERIVED_IDENTITY_CONTRACT",
                        "authority_position": type_name_positions[type_name],
                        "authority_record_sha256": _sha256(
                            _canonical_bytes(identity_payload)
                        ),
                        "dependency_id": identity_id,
                        "dependency_kind": "IDENTITY_CONTRACT",
                    },
                )
            )
        return references

    for expected_position, source_step in enumerate(
        template["ordered_template_steps"], start=1
    ):
        _require(
            source_step["template_step_position"] == expected_position,
            "STEP_POSITION_DRIFT",
            f"{case_position}/{expected_position}",
        )
        references: list[dict[str, str]] = []
        value_schema_id = source_step["value_schema_id"]
        if value_schema_id is not None:
            schema = value_schemas.get(value_schema_id)
            _require(schema is not None, "VALUE_SCHEMA_UNRESOLVED", value_schema_id)
            references.append(
                add_registry(
                    "VALUE_SCHEMA",
                    value_schema_id,
                    "value_schema_catalog",
                    value_positions[value_schema_id],
                    schema,
                )
            )

        parameters = source_step["recurrence_parameters"]
        text_language_id = parameters.get("text_language_id")
        if text_language_id is not None:
            language = text_languages.get(text_language_id)
            _require(
                language is not None,
                "TEXT_LANGUAGE_UNRESOLVED",
                text_language_id,
            )
            _require(
                parameters.get("text_language_position")
                == text_positions[text_language_id],
                "TEXT_LANGUAGE_POSITION_DRIFT",
                text_language_id,
            )
            references.append(
                add_registry(
                    "TEXT_LANGUAGE",
                    text_language_id,
                    "text_language_catalog",
                    text_positions[text_language_id],
                    language,
                )
            )
            dfa_id = language["ascii_dfa_id"]
            if dfa_id is not None:
                _require(dfa_id in dfas, "ASCII_DFA_UNRESOLVED", dfa_id)
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
                _require(
                    profile_id in profiles,
                    "UNICODE_PROFILE_UNRESOLVED",
                    profile_id,
                )
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
                    _require(
                        source_id in unicode_sources,
                        "UNICODE_SOURCE_UNRESOLVED",
                        source_id,
                    )
                    references.append(
                        add_registry(
                            "UNICODE_SOURCE",
                            source_id,
                            "unicode_source_catalog",
                            unicode_positions[source_id],
                            unicode_sources[source_id],
                        )
                    )

        for rule_id in source_step["ordered_intrinsic_rule_ids"]:
            _require(rule_id in rules, "INTRINSIC_RULE_UNRESOLVED", rule_id)
            references.append(
                add_registry(
                    "INTRINSIC_RULE",
                    rule_id,
                    "ordered_cross_field_rule_descriptors",
                    rule_positions[rule_id],
                    rules[rule_id],
                )
            )

        type_names: list[str] = []
        if source_step["type_name"] is not None:
            type_names.append(source_step["type_name"])
        referenced_type = parameters.get("referenced_type_name")
        if referenced_type is not None and referenced_type not in type_names:
            type_names.append(referenced_type)
        owner_type = parameters.get("owner_type_name")
        if owner_type is not None and owner_type not in type_names:
            type_names.append(owner_type)
        for type_name in type_names:
            references.extend(add_type(type_name))

        local_kind = {
            "ASSOCIATIVE_HOMOGENEOUS_RUN_BATCH": "ARRAY_BATCH",
            "TAGGED_UNION_BRANCH": "UNION_BRANCH",
            "CODEC_INTERSECTION": "CODEC_COORDINATE_SET",
        }.get(source_step["derivation_kind"])
        if local_kind is not None:
            references.append(
                _add_dependency(
                    dependencies,
                    _local_dependency(
                        canonicalization_version,
                        schema_version,
                        case_position,
                        expected_position,
                        local_kind,
                        {
                            "alternative_name": source_step["alternative_name"],
                            "recurrence_parameters": parameters,
                            "subject_locator": source_step["subject_locator"],
                            "type_name": source_step["type_name"],
                            "value_schema_id": source_step["value_schema_id"],
                        },
                    ),
                )
            )

        step_payload = {
            "alternative_name": source_step["alternative_name"],
            "derivation_kind": source_step["derivation_kind"],
            "logical_derivation_step_id": source_step["logical_derivation_step_id"],
            "ordered_child_step_positions": source_step[
                "ordered_child_step_positions"
            ],
            "ordered_dependency_references": sorted(
                references,
                key=lambda row: (
                    DEPENDENCY_KIND_ORDER[row["dependency_kind"]],
                    row["dependency_id"],
                ),
            ),
            "ordered_intrinsic_rule_ids": source_step["ordered_intrinsic_rule_ids"],
            "recurrence_parameters": parameters,
            "step_position": expected_position,
            "subject_locator": source_step["subject_locator"],
            "type_name": source_step["type_name"],
            "value_schema_id": source_step["value_schema_id"],
        }
        step_payload["correction_step_id"] = _semantic_id(
            canonicalization_version,
            schema_version,
            STEP_DOMAIN,
            step_payload,
        )
        steps.append(step_payload)

    # Every relaxed predicate is explicitly resolved to the frozen dependency
    # surface.  This prevents C2 from silently dropping a predicate class.
    for relaxation in template["ordered_relaxation_application_records"]:
        predicate_kind = relaxation["predicate_kind"]
        predicate_id = relaxation["authority_predicate_id"]
        if predicate_kind == "TEXT_LANGUAGE":
            expected_key = ("TEXT_LANGUAGE", predicate_id)
        elif predicate_kind == "INTRINSIC_RULE":
            expected_key = ("INTRINSIC_RULE", predicate_id)
        elif predicate_kind == "PAYLOAD_DERIVED_IDENTITY_EQUALITY":
            descriptor = types_by_id.get(predicate_id)
            _require(
                descriptor is not None,
                "IDENTITY_DESCRIPTOR_UNRESOLVED",
                predicate_id,
            )
            _require(
                descriptor["identity_field"] is not None,
                "IDENTITY_CONTRACT_ABSENT",
                predicate_id,
            )
            add_type(descriptor["type_name"])
            identity_payload = {
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
            expected_key = (
                "IDENTITY_CONTRACT",
                _semantic_id(
                    canonicalization_version,
                    schema_version,
                    IDENTITY_DEPENDENCY_DOMAIN,
                    identity_payload,
                ),
            )
        elif predicate_kind == "ARRAY_ORDER_AND_UNIQUENESS":
            expected_key = ("VALUE_SCHEMA", predicate_id)
        else:
            raise ContractFailure(f"RELAXATION_PREDICATE_KIND_UNKNOWN: {predicate_kind}")
        _require(
            expected_key in dependencies,
            "RELAXATION_DEPENDENCY_UNRESOLVED",
            f"{case_position}/{relaxation['application_position']}",
        )

    ordered_dependencies = sorted(
        dependencies.values(),
        key=lambda row: (
            DEPENDENCY_KIND_ORDER[row["dependency_kind"]],
            row["dependency_id"],
        ),
    )
    for position, dependency in enumerate(ordered_dependencies, start=1):
        dependency["dependency_position"] = position

    status = (
        "FROZEN_P2_ENDPOINT_CONTRADICTED"
        if case_position in contradiction_positions
        else "EXACTNESS_UNRESOLVED_NOT_ACCEPTED"
    )
    case_payload = {
        "alternative_name": execution["alternative_name"],
        "case_execution_record_id": execution["case_execution_record_id"],
        "case_position": case_position,
        "correction_status": status,
        "logical_count_plan_id": plan["logical_count_plan_id"],
        "logical_plan_template_id": template["logical_plan_template_id"],
        "ordered_authority_dependency_records": ordered_dependencies,
        "ordered_relaxation_application_records": template[
            "ordered_relaxation_application_records"
        ],
        "ordered_step_contract_records": steps,
        "root_step_position": template["root_step_position"],
        "root_type_name": template["root_type_name"],
        "row_kind": execution["row_kind"],
        "type_name": execution["type_name"],
    }
    case_payload["intrinsic_correction_case_id"] = _semantic_id(
        canonicalization_version,
        schema_version,
        CASE_DOMAIN,
        case_payload,
    )
    return case_payload


def build_contract(root: pathlib.Path) -> dict[str, Any]:
    root = root.resolve()
    raw, parsed = _load_authorities(root)
    seed = parsed["SEED"]
    registry = parsed["REGISTRY"]
    campaign = parsed["ALL_CASE_CONTRACT"]
    falsification = parsed["FALSIFICATION_ACCEPTANCE_REPORT"]
    canonicalization_version = registry["canonicalization_version"]
    schema_version = registry["measurement_schema_version"]
    _require(
        seed["canonicalization_version"] == canonicalization_version
        and seed["measurement_schema_version"] == schema_version,
        "SEED_REGISTRY_VERSION_DRIFT",
    )
    _require(
        seed["seed_catalog_id"]
        == "ac22151fa74702ac1488924f01161eaa38574545e6272a290db6b0bbd288ae5f",
        "SEED_ID_DRIFT",
    )
    _require(
        registry["external_schema_registry_id"]
        == "5dc95a3e99c5646e912b6a7e9c3970cf2489d560ea890b0a19d38af4c51c2140",
        "REGISTRY_ID_DRIFT",
    )
    _require(
        campaign["all_case_campaign_contract_id"]
        == "9be94bf6b53b612d62ac26bc74133f25c1101a0962987a855e65cdcd06418583",
        "CAMPAIGN_CONTRACT_ID_DRIFT",
    )
    _require(
        falsification["acceptance_report_id"]
        == "7dfd4073f40f1825356b32c3ed0ca7f291a4a179827882fbbedbdeb96030102e"
        and falsification["decision"]
        == "ACCEPTED_FALSIFICATION_AUTHORITY_REPAIR_REQUIRED"
        and falsification["next_bounded_packet"] == "A4-R475-V1-C",
        "FALSIFICATION_ACCEPTANCE_DRIFT",
    )
    contradiction_positions = falsification["contradiction_case_positions"]
    _require(
        contradiction_positions == EXPECTED_CONTRADICTION_POSITIONS,
        "CONTRADICTION_VECTOR_DRIFT",
    )

    recipes = seed["logical_plan_recipe_catalog"]
    templates = recipes["ordered_logical_plan_templates"]
    plans = recipes["ordered_logical_count_plan_records"][:INTRINSIC_CASE_COUNT]
    executions = campaign["case_universe_contract"][
        "ordered_case_execution_records"
    ][:INTRINSIC_CASE_COUNT]
    _require(len(templates) == INTRINSIC_CASE_COUNT, "TEMPLATE_COUNT_DRIFT")
    _require(len(plans) == INTRINSIC_CASE_COUNT, "PLAN_COUNT_DRIFT")
    _require(len(executions) == INTRINSIC_CASE_COUNT, "EXECUTION_COUNT_DRIFT")

    value_schemas, value_positions = _index(
        registry["value_schema_catalog"], "value_schema_id", "VALUE_SCHEMA"
    )
    text_languages, text_positions = _index(
        registry["text_language_catalog"], "text_language_id", "TEXT_LANGUAGE"
    )
    dfas, dfa_positions = _index(
        registry["ascii_dfa_catalog"], "ascii_dfa_id", "ASCII_DFA"
    )
    profiles, profile_positions = _index(
        registry["identifier_profile_catalog"],
        "unicode_identifier_profile_id",
        "UNICODE_PROFILE",
    )
    unicode_sources, unicode_positions = _index(
        registry["unicode_source_catalog"],
        "unicode_source_record_id",
        "UNICODE_SOURCE",
    )
    rules, rule_positions = _index(
        registry["ordered_cross_field_rule_descriptors"],
        "rule_id",
        "INTRINSIC_RULE",
    )
    types_by_name, type_name_positions = _index(
        registry["ordered_external_type_descriptors"],
        "type_name",
        "TYPE_DESCRIPTOR",
    )
    types_by_id, _ = _index(
        registry["ordered_external_type_descriptors"],
        "external_type_descriptor_id",
        "TYPE_DESCRIPTOR",
    )

    ordered_cases = [
        _build_case(
            canonicalization_version=canonicalization_version,
            schema_version=schema_version,
            template=template,
            plan=plan,
            execution=execution,
            contradiction_positions=set(contradiction_positions),
            value_schemas=value_schemas,
            value_positions=value_positions,
            text_languages=text_languages,
            text_positions=text_positions,
            dfas=dfas,
            dfa_positions=dfa_positions,
            profiles=profiles,
            profile_positions=profile_positions,
            unicode_sources=unicode_sources,
            unicode_positions=unicode_positions,
            rules=rules,
            rule_positions=rule_positions,
            types_by_name=types_by_name,
            type_name_positions=type_name_positions,
            types_by_id=types_by_id,
        )
        for template, plan, execution in zip(templates, plans, executions, strict=True)
    ]
    status_counts = Counter(row["correction_status"] for row in ordered_cases)
    _require(
        status_counts
        == {
            "FROZEN_P2_ENDPOINT_CONTRADICTED": CONTRADICTION_CASE_COUNT,
            "EXACTNESS_UNRESOLVED_NOT_ACCEPTED": NOT_FALSIFIED_CASE_COUNT,
        },
        "CORRECTION_STATUS_CENSUS_DRIFT",
    )
    dependency_occurrences = Counter(
        dependency["dependency_kind"]
        for case in ordered_cases
        for dependency in case["ordered_authority_dependency_records"]
    )
    step_kind_counts = Counter(
        step["derivation_kind"]
        for case in ordered_cases
        for step in case["ordered_step_contract_records"]
    )
    authority_records = [
        {
            "authority_name": name,
            "raw_octets": AUTHORITIES[name][1],
            "raw_sha256": AUTHORITIES[name][2],
            "relative_path": AUTHORITIES[name][0],
        }
        for name in AUTHORITIES
    ]
    pinned_octets = sum(len(value) for value in raw.values())
    _require(pinned_octets < 67_108_864, "PINNED_INPUT_F0_EXCEEDED")

    contract: dict[str, Any] = {
        "acceptance_contract": {
            "acceptance_claim": "DEPENDENCY_AND_SUCCESSOR_INTERFACE_ONLY",
            "all_66_exact_maxima_accepted": False,
            "all_case_campaign_released": False,
            "required_case_count": INTRINSIC_CASE_COUNT,
            "required_contradiction_case_count": CONTRADICTION_CASE_COUNT,
            "required_not_falsified_nonclaim_case_count": NOT_FALSIFIED_CASE_COUNT,
            "required_review": "INDEPENDENT_FULL_RECONSTRUCTION_WITHOUT_GENERATOR_IMPORT",
        },
        "aggregate_dependency_census": {
            "dependency_kind_counts": dict(sorted(dependency_occurrences.items())),
            "step_derivation_kind_counts": dict(sorted(step_kind_counts.items())),
            "total_case_dependency_records": sum(dependency_occurrences.values()),
            "total_step_records": sum(step_kind_counts.values()),
        },
        "canonicalization_version": canonicalization_version,
        "contract_version": CONTRACT_VERSION,
        "correction_scope_contract": {
            "contradiction_case_count": CONTRADICTION_CASE_COUNT,
            "intrinsic_case_count": INTRINSIC_CASE_COUNT,
            "not_falsified_case_count": NOT_FALSIFIED_CASE_COUNT,
            "ordered_contradiction_case_positions": contradiction_positions,
            "scope_rule": "ALL_66_INTRINSIC_TEMPLATES_WITHOUT_SAMPLING_OR_PROMOTION_OF_UNRESOLVED_CASES",
        },
        "dual_channel_contract": {
            "attainer_channel": {
                "candidate_source_must_not_read_upper_output": True,
                "must_execute_complete_p1": True,
                "required_packet": "A4-R475-V1-C2-A",
                "required_result": "ONE_CANONICAL_P1_LEGAL_ATTAINER_PER_CASE",
            },
            "cross_channel_code_sharing_policy": "FORBIDDEN",
            "pre_execution_source_freeze": {
                "both_channel_sources_and_output_schemas_frozen_before_execution": True,
                "channel_output_allowed_during_source_freeze": False,
                "mutual_import_read_or_generated_witness_access_policy": "FORBIDDEN",
                "required_packet": "A4-R475-V1-C2-S",
            },
            "exactness_join": {
                "equality_rule": "UPPER_OCTETS_EQUALS_MEASURED_ATTAINER_OCTETS",
                "problem_authority_identity_rule": "EXACT_MATCH",
                "required_packet": "A4-R475-V1-C3",
                "unresolved_or_unequal_policy": "NO_GO",
            },
            "upper_channel": {
                "ambient_relaxed_text_cell_allowed": False,
                "source_must_not_read_attainer_output": True,
                "must_prove_legal_domain_superset": True,
                "required_methods": [
                    "FINITE_ENUMERATION",
                    "CLOSED_BUILTIN_FORMULA",
                    "ASCII_DFA_DYNAMIC_PROGRAMMING",
                    "PINNED_UNICODE_PROFILE_PROGRAM",
                    "RULE_AWARE_COMPOSITION",
                    "CODEC_INTERSECTION",
                ],
                "required_packet": "A4-R475-V1-C2-U",
                "required_result": "ONE_PROOF_CARRYING_LEGAL_UPPER_PER_CASE",
            },
        },
        "formal_stage1_state": "NO-GO",
        "measurement_schema_version": schema_version,
        "next_bounded_packet": "A4-R475-V1-C2-S",
        "ordered_authority_records": authority_records,
        "ordered_intrinsic_case_records": ordered_cases,
        "ordered_intrinsic_case_records_sha256": _sha256(
            _canonical_bytes(ordered_cases)
        ),
        "ordered_successor_packet_records": [
            {
                "packet": "A4-R475-V1-C2-S",
                "packet_position": 1,
                "scope": "PRE_EXECUTION_DUAL_CHANNEL_SOURCE_AND_SCHEMA_FREEZE",
            },
            {
                "packet": "A4-R475-V1-C2-U",
                "packet_position": 2,
                "scope": "INDEPENDENT_LEGAL_UPPER_CHANNEL_ALL_66_CASES",
            },
            {
                "packet": "A4-R475-V1-C2-A",
                "packet_position": 3,
                "scope": "INDEPENDENT_P1_LEGAL_ATTAINER_CHANNEL_ALL_66_CASES",
            },
            {
                "packet": "A4-R475-V1-C3",
                "packet_position": 4,
                "scope": "EXACTNESS_JOIN_AND_VERSIONED_AUTHORITY_DELTA",
            },
            {
                "packet": "A4-R475-V1",
                "packet_position": 5,
                "scope": "CORRECTED_INTRINSIC_TEMPLATE_VERIFIER_COVERAGE",
            },
        ],
        "packet": "A4-R475-V1-C1",
        "predecessor_authority_contract": {
            "all_case_campaign_contract_id": campaign[
                "all_case_campaign_contract_id"
            ],
            "all_case_v0_verifier_raw_sha256": AUTHORITIES[
                "ALL_CASE_V0_VERIFIER"
            ][2],
            "falsification_acceptance_report_id": falsification[
                "acceptance_report_id"
            ],
            "pilot_role_bytes_must_remain_exact": True,
            "seed_catalog_id": seed["seed_catalog_id"],
            "structural_registry_id": registry["external_schema_registry_id"],
        },
        "resource_contract": {
            "authority_file_count": len(AUTHORITIES),
            "authority_file_limit": 64,
            "contract_raw_octet_limit": 16_777_216,
            "limit_tuning_from_observed_answer_allowed": False,
            "pinned_input_octet_limit": 67_108_864,
            "pinned_input_octets": pinned_octets,
        },
        "source_marker": SOURCE_MARKER,
        "successor_authority_contract": {
            "accepted_predecessor_edit_policy": "FORBIDDEN",
            "allowed_new_authority": "VERSIONED_INTRINSIC_EXACTNESS_DELTA_ONLY",
            "all_case_v0_candidate_access_barrier_must_remain": True,
            "correction_endpoint_source": "C3_ACCEPTED_EQUAL_UPPER_AND_ATTAINER_LENGTH",
            "unknown_missing_duplicate_extra_or_resealed_dependency_policy": "NO_GO",
            "verifier_producer_runner_or_campaign_implemented_by_c1": False,
        },
    }
    contract["intrinsic_exactness_correction_contract_id"] = _semantic_id(
        canonicalization_version,
        schema_version,
        CONTRACT_DOMAIN,
        contract,
    )
    _require(
        len(_pretty_bytes(contract)) <= 16_777_216,
        "CONTRACT_OUTPUT_F0_EXCEEDED",
    )
    return contract


def _atomic_write(path: pathlib.Path, raw: bytes) -> None:
    _require(path.is_absolute(), "OUTPUT_PATH_INVALID")
    _require(path.parent.is_dir() and not path.parent.is_symlink(), "OUTPUT_PARENT_INVALID")
    _require(not path.exists() and not path.is_symlink(), "OUTPUT_EXISTS")
    temporary = path.parent / f".{path.name}.tmp"
    descriptor: int | None = None
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
            0o600,
        )
        offset = 0
        while offset < len(raw):
            written = os.write(descriptor, raw[offset:])
            _require(written > 0, "OUTPUT_WRITE_STALLED")
            offset += written
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.link(temporary, path, follow_symlinks=False)
        os.unlink(temporary)
        parent = os.open(path.parent, os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _arguments(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--repository-root", required=True)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--write")
    modes.add_argument("--check")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        arguments = _arguments(sys.argv[1:] if argv is None else argv)
        root = pathlib.Path(arguments.repository_root)
        _require(
            root.is_absolute() and pathlib.Path(os.path.realpath(root)) == root,
            "REPOSITORY_ROOT_INVALID",
        )
        contract = build_contract(root)
        raw = _pretty_bytes(contract)
        selected = arguments.write if arguments.write is not None else arguments.check
        output = pathlib.Path(selected)
        _require(output.is_absolute(), "OUTPUT_PATH_INVALID")
        if arguments.write is not None:
            _atomic_write(output, raw)
        else:
            _require(output.is_file() and not output.is_symlink(), "CHECK_TARGET_INVALID")
            _require(output.read_bytes() == raw, "CONTRACT_STALE")
    except (ContractFailure, OSError, ValueError, TypeError, KeyError) as error:
        sys.stderr.write(f"{ERROR_PREFIX}REJECTED: {type(error).__name__}: {error}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
