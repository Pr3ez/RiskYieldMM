#!/usr/bin/env python3
"""Independently verify the case-435 C2 retained-witness certificate."""

from __future__ import annotations

import dataclasses
import hashlib
import importlib.util
import json
import pathlib
import sys
from types import ModuleType
from typing import Any

SEED_PATH = "scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json"
INVENTORY_PATH = "tests/raw_v8_step2_inventory_v4_v49f.json"
REGISTRY_PATH = (
    "scripts/tests/raw_v8_step2_external_schema_v2_structural_registry_v49f.json"
)
LITERAL_PATH = (
    "scripts/tests/raw_v8_step2_external_schema_v2_rule_literal_authority_v49f.json"
)
APPLICATION_LEDGER_PATH = (
    "scripts/tests/raw_v8_step2_external_schema_v2_rule_application_ledger_v49f.json"
)
RUNTIME_PATH = (
    "scripts/tests/validate_raw_v8_step2_external_schema_v2_rule_runtime_v49f.py"
)
DEPENDENCY_ANALYZER_PATH = (
    "scripts/tests/check_raw_v8_step2_maximum_protocol_v2_"
    "case435_dependency_closure_v49f.py"
)

PINNED_SHA256 = {
    SEED_PATH: "a75a2f352e8513b7ff0043693a0c65ebbf4bc6f06859354789af69e1162b0e4f",
    INVENTORY_PATH: "de91eac92d1c36cf1670b2484392fbf1c633d75f928c8e70fcd5e71ae798db2b",
    REGISTRY_PATH: "9160297ff316c5931737c92f8b359f0a1e2ec22f0aa996ef3b09cf830dc96bf3",
    LITERAL_PATH: "aba3461059367904734e2eb9ae404787b9aab5ed4c3fbcd292925a364926cce2",
    APPLICATION_LEDGER_PATH: (
        "979d7affe2d745d46f5977d9d69a4d1efa473f95c1a374737bf34181d9dac282"
    ),
    RUNTIME_PATH: "47aa90d897e8dbae5e244b7c04cbd82dfe036b0292d36ef0f5552c868627ab22",
    DEPENDENCY_ANALYZER_PATH: (
        "f882042d0bd519ced260734a43a9ee2c9b390ffac965ebe7c04ac261c2932f30"
    ),
}

CASE_POSITION = 435
PROFILE_POSITION = 369
MEASURED_SEQUENCE_ORDINAL = 64
FIELD_COUNT = 185
OBSERVATION_COUNT = 67
PROFILE_ID = "505dac244288e6fb666919c99567f883c28ed573a898ce2a5dd680744dd57540"
PLAN_ID = "9f8cd8303e3a9360986f0294210dda931e827af6eed4ec76b0c084e54f722c4a"
PROGRAM_ID = "0e4a94fb5b99c464e7db1ef0fc0525b9408683a004a5ea034fcfbf5c427eb4e8"
DEPENDENCY_MANIFEST_ID = (
    "d80797d6d34486ed15f73d19a201c7b5ff0ac19593e25302bcba081c2e7b5c3c"
)
CERTIFICATE_VERSION = (
    "riskyieldmm.raw_v8_step2.maximum_protocol_v2.case435_attainer_certificate.v1"
)
CERTIFICATE_DOMAIN = (
    "RiskYieldMMStep2MaximumProtocolV2Case435AttainerCertificateV1V4_9F_RawV8"
)
CONSTRUCTION_VERSION = (
    "riskyieldmm.raw_v8_step2.maximum_protocol_v2."
    "case435_independent_longest_first_attainer.v1"
)
APPLICATION_ORDER = (
    "APPLY/SELECTOR_MARKER_CONTRACT_V1",
    "APPLY/V2_OBSERVATION_AGGREGATE_REGISTRY_V1",
    "APPLY/V2_OBSERVATION_FIELDS_REGISTRY_V1",
    "APPLY/V2_ROOT_OBSERVATION_MEMBERSHIP_V1",
    "APPLY/V2_ROOT_SELECTOR_LIFECYCLE_V1",
)
CHECKPOINT_MEMBERS = (
    "checkpoint_binding_status",
    "checkpoint_binding_unavailable_reason",
    "checkpoint_marker_kind",
    "checkpoint_selector_entry_id",
    "checkpoint_selector_position",
    "expected_checkpoint_marker_kind",
    "expected_occurrence_index_within_kind",
    "full_checkpoint_selector_id",
    "marker_ordinal",
)
TOP_LEVEL_MEMBERS = {
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


class CertificateError(RuntimeError):
    """Raised when the purported retained witness fails closed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CertificateError(message)


def _reject_number(value: str) -> Any:
    raise CertificateError(f"non-integer JSON number is forbidden: {value}")


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


def _read_authorities(root: pathlib.Path) -> tuple[dict[str, Any], ...]:
    loaded: dict[str, dict[str, Any]] = {}
    for relative, expected in PINNED_SHA256.items():
        path = root / relative
        _require(
            path.is_file() and not path.is_symlink(), f"authority absent: {relative}"
        )
        raw = path.read_bytes()
        _require(_sha256(raw) == expected, f"authority drift: {relative}")
        if relative.endswith(".json"):
            loaded[relative] = _strict_load(raw, relative)
    return (
        loaded[SEED_PATH],
        loaded[INVENTORY_PATH],
        loaded[REGISTRY_PATH],
        loaded[LITERAL_PATH],
        loaded[APPLICATION_LEDGER_PATH],
    )


def _load_runtime(root: pathlib.Path) -> ModuleType:
    path = root / RUNTIME_PATH
    name = "raw_v8_case435_attainer_certificate_runtime_v49f"
    spec = importlib.util.spec_from_file_location(name, path)
    _require(spec is not None and spec.loader is not None, "runtime loader unresolved")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _semantic_id(
    canonicalization: str,
    schema_version: str,
    domain: str,
    payload: dict[str, Any],
) -> str:
    return _sha256(
        _canonical_bytes(
            {
                "canonicalization_version": canonicalization,
                "domain": domain,
                "payload": payload,
                "schema_version": schema_version,
            }
        )
    )


def _record_identity(
    value: dict[str, Any],
    descriptor: dict[str, Any],
    canonicalization: str,
    schema_version: str,
) -> str:
    return _semantic_id(
        canonicalization,
        schema_version,
        descriptor["described_record_domain"],
        {
            member: value[member]
            for member in descriptor["identity_payload_member_order"]
        },
    )


def _record_input(
    runtime_module: ModuleType,
    binding_name: str,
    type_name: str,
    value: dict[str, Any],
) -> Any:
    return runtime_module.ApplicationRecordInput(
        binding_name=binding_name,
        declared=runtime_module.TypedValue(value=value, type_name=type_name),
    )


def _sequence_input(
    runtime_module: ModuleType,
    binding_name: str,
    type_name: str,
    values: list[dict[str, Any]],
) -> Any:
    return runtime_module.ApplicationSequenceInput(
        binding_name=binding_name,
        ordered_records=tuple(
            runtime_module.TypedValue(value=value, type_name=type_name)
            for value in values
        ),
    )


def _receipt(
    evidence: Any, schedule_position: int, invocation_ordinal: int | None
) -> dict[str, Any]:
    payload = dataclasses.asdict(evidence)
    _require(
        payload["accepted"] is True,
        (
            "retained witness fails P1: "
            f"position={schedule_position}, ordinal={invocation_ordinal}, "
            f"coordinate={payload['result_coordinate']}"
        ),
    )
    return {
        "application_schedule_position": schedule_position,
        "invocation_ordinal": invocation_ordinal,
        "application_name": payload["application_name"],
        "rule_application_id": payload["rule_application_id"],
        "rule_id": payload["rule_id"],
        "charged_rule_evaluations": payload["charged_rule_evaluations"],
        "completed_rule_evaluations": payload["completed_rule_evaluations"],
        "total_expression_nodes": payload["total_expression_nodes"],
        "direct_expression_nodes": sum(
            row["direct_expression_nodes"]
            for row in payload["ordered_rule_step_evidence"]
        ),
        "evidence_canonical_sha256": _sha256(_canonical_bytes(payload)),
    }


def _execute_p1(
    runtime_module: ModuleType,
    runtime: Any,
    root: dict[str, Any],
    observations: list[dict[str, Any]],
    selector: dict[str, Any],
    marker_contract: dict[str, Any],
    target_registry: dict[str, Any],
) -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    evidence = runtime.evaluate_application(
        APPLICATION_ORDER[0],
        (
            _record_input(runtime_module, "selector", "CheckpointSelectorV1", selector),
            _record_input(
                runtime_module,
                "marker_contract",
                "MarkerContractV1",
                marker_contract,
            ),
        ),
    )
    receipts.append(_receipt(evidence, 1, None))
    for ordinal, observation in enumerate(observations):
        evidence = runtime.evaluate_application(
            APPLICATION_ORDER[1],
            (
                _record_input(
                    runtime_module,
                    "observation",
                    "TargetObservationV2",
                    observation,
                ),
                _record_input(
                    runtime_module,
                    "target_registry",
                    "TargetFieldRegistryV1",
                    target_registry,
                ),
            ),
        )
        receipts.append(_receipt(evidence, 2, ordinal))
    for ordinal, observation in enumerate(observations):
        evidence = runtime.evaluate_application(
            APPLICATION_ORDER[2],
            (
                _record_input(
                    runtime_module,
                    "observation",
                    "TargetObservationV2",
                    observation,
                ),
                _record_input(
                    runtime_module,
                    "target_registry",
                    "TargetFieldRegistryV1",
                    target_registry,
                ),
            ),
        )
        receipts.append(_receipt(evidence, 3, ordinal))
    evidence = runtime.evaluate_application(
        APPLICATION_ORDER[3],
        (_record_input(runtime_module, "root", "TargetObservationRootV2", root),),
        (
            _sequence_input(
                runtime_module,
                "observation",
                "TargetObservationV2",
                observations,
            ),
        ),
    )
    receipts.append(_receipt(evidence, 4, None))
    evidence = runtime.evaluate_application(
        APPLICATION_ORDER[4],
        (_record_input(runtime_module, "root", "TargetObservationRootV2", root),),
        (
            _sequence_input(
                runtime_module,
                "observations",
                "TargetObservationV2",
                observations,
            ),
            _sequence_input(
                runtime_module,
                "selector",
                "CheckpointSelectorV1",
                [selector],
            ),
        ),
    )
    receipts.append(_receipt(evidence, 5, None))
    return receipts


def _verify_record_identities(
    registry: dict[str, Any],
    selector: dict[str, Any],
    root: dict[str, Any],
    observations: list[dict[str, Any]],
) -> None:
    canonicalization = registry["canonicalization_version"]
    schema_version = registry["measurement_schema_version"]
    types = {
        row["type_name"]: row for row in registry["ordered_external_type_descriptors"]
    }
    records: list[tuple[dict[str, Any], str, str]] = [
        (selector, "CheckpointSelectorV1", "checkpoint_selector_id"),
        (root, "TargetObservationRootV2", "target_observation_root_sha256"),
    ]
    for observation in observations:
        records.extend(
            (
                (
                    observation["observation_context"],
                    "TargetObservationContextV2",
                    "observation_context_id",
                ),
                (observation, "TargetObservationV2", "observation_id"),
            )
        )
        records.extend(
            (field, "TargetFieldObservationV1", "field_observation_id")
            for field in observation["field_observations"]
        )
    for value, type_name, identity_member in records:
        _require(
            value[identity_member]
            == _record_identity(
                value, types[type_name], canonicalization, schema_version
            ),
            f"semantic identity differs: {type_name}",
        )


def _verify_lifecycle(
    selector: dict[str, Any],
    root: dict[str, Any],
    observations: list[dict[str, Any]],
) -> None:
    _require(
        len(observations) == OBSERVATION_COUNT
        and root["observation_count"] == OBSERVATION_COUNT,
        "retained observation count differs",
    )
    _require(
        root["ordered_observation_ids"]
        == [row["observation_id"] for row in observations],
        "root observation membership vector differs",
    )
    _require(
        selector["selector_length"] == MEASURED_SEQUENCE_ORDINAL
        and root["full_checkpoint_selector_id"] == selector["checkpoint_selector_id"],
        "selector/root binding differs",
    )
    roles = [row["observation_context"]["observation_role"] for row in observations]
    _require(
        roles
        == ["BEFORE_OPERATION"]
        + ["STABLE_CHECKPOINT"] * MEASURED_SEQUENCE_ORDINAL
        + ["AFTER_OPERATION", "OPERATION_AGGREGATE"],
        "observation role sequence differs",
    )
    root_join_members = (
        "attempt_id",
        "candidate_id",
        "instrumentation_mode",
        "operation_kind",
        "target_field_registry_id",
    )
    for observation in observations:
        context = observation["observation_context"]
        _require(
            all(context[member] == root[member] for member in root_join_members),
            "observation/root context join differs",
        )
        _require(
            observation["observation_context_id"] == context["observation_context_id"]
            and len(observation["field_observations"]) == FIELD_COUNT,
            "observation context or field cardinality differs",
        )
        _require(
            all(
                field["observation_context_id"] == context["observation_context_id"]
                and field["target_field_registry_id"]
                == root["target_field_registry_id"]
                for field in observation["field_observations"]
            ),
            "field/context join differs",
        )
    for observation in (observations[0], observations[-2], observations[-1]):
        context = observation["observation_context"]
        _require(
            all(context[member] is None for member in CHECKPOINT_MEMBERS),
            "outer observation carries checkpoint state",
        )
    for position, (entry, observation) in enumerate(
        zip(
            selector["ordered_entries"],
            observations[1 : MEASURED_SEQUENCE_ORDINAL + 1],
            strict=True,
        ),
        1,
    ):
        context = observation["observation_context"]
        _require(
            context["checkpoint_selector_position"] == position
            and context["checkpoint_selector_entry_id"]
            == entry["checkpoint_selector_entry_id"]
            and context["expected_checkpoint_marker_kind"]
            == entry["checkpoint_marker_kind"]
            and context["expected_occurrence_index_within_kind"]
            == entry["occurrence_index_within_kind"]
            and context["full_checkpoint_selector_id"]
            == selector["checkpoint_selector_id"],
            "checkpoint selector coordinate differs",
        )
        if position < MEASURED_SEQUENCE_ORDINAL:
            _require(
                context["checkpoint_binding_status"]
                == "UNAVAILABLE_TARGET_BOUNDARY_NOT_REACHED"
                and context["checkpoint_binding_unavailable_reason"]
                == "TARGET_BOUNDARY_NOT_REACHED"
                and context["checkpoint_marker_kind"] is None
                and context["marker_ordinal"] is None,
                "preceding checkpoint is not a boundary placeholder",
            )
        else:
            _require(
                context["checkpoint_binding_status"] == "EXACT_MARKER"
                and context["checkpoint_binding_unavailable_reason"] is None
                and context["checkpoint_marker_kind"] == entry["checkpoint_marker_kind"]
                and type(context["marker_ordinal"]) is int,
                "measured checkpoint is not exact",
            )


def _verify_selected_fields(
    certificate: dict[str, Any], measured: dict[str, Any]
) -> None:
    fields = measured["field_observations"]
    records = certificate["ordered_selected_field_witness_records"]
    _require(
        type(records) is list and len(records) == FIELD_COUNT,
        "selected field witness vector differs",
    )
    required = {
        "field_id",
        "field_position",
        "proposal_count",
        "selected_branch",
        "selected_canonical_octets",
        "selected_canonical_sha256",
        "selected_field_observation_id",
    }
    for position, (record, field) in enumerate(zip(records, fields, strict=True), 1):
        raw = _canonical_bytes(field)
        _require(set(record) == required, "selected field record members differ")
        _require(
            record["field_position"] == position
            and record["field_id"] == field["field_id"]
            and type(record["proposal_count"]) is int
            and record["proposal_count"] > 0
            and type(record["selected_branch"]) is dict
            and record["selected_canonical_octets"] == len(raw)
            and record["selected_canonical_sha256"] == _sha256(raw)
            and record["selected_field_observation_id"]
            == field["field_observation_id"],
            "selected field witness record differs",
        )


def _verify_declared_execution(
    execution: dict[str, Any], schedule: dict[str, Any]
) -> None:
    _require(
        set(execution)
        == {
            "all_applications_accepted",
            "application_invocation_count",
            "charged_rule_evaluation_count",
            "completed_rule_evaluation_count",
            "direct_expression_node_count",
            "ordered_application_execution_receipts",
            "receipt_vector_sha256",
        },
        "declared P1 execution members differ",
    )
    receipts = execution["ordered_application_execution_receipts"]
    _require(
        type(receipts) is list
        and len(receipts) == schedule["application_invocation_count"]
        and execution["application_invocation_count"] == len(receipts)
        and execution["all_applications_accepted"] is True
        and execution["charged_rule_evaluation_count"]
        == schedule["cross_rule_evaluation_count"]
        and execution["completed_rule_evaluation_count"]
        == schedule["cross_rule_evaluation_count"]
        and execution["direct_expression_node_count"]
        == schedule["direct_cross_expression_node_count"]
        and execution["receipt_vector_sha256"] == _sha256(_canonical_bytes(receipts)),
        "declared P1 execution accounting differs",
    )
    required_members = {
        "application_name",
        "application_schedule_position",
        "charged_rule_evaluations",
        "completed_rule_evaluations",
        "direct_expression_nodes",
        "evidence_canonical_sha256",
        "invocation_ordinal",
        "rule_application_id",
        "rule_id",
        "total_expression_nodes",
    }
    positions = [1] + [2] * OBSERVATION_COUNT + [3] * OBSERVATION_COUNT + [4, 5]
    ordinals = (
        [None]
        + list(range(OBSERVATION_COUNT))
        + list(range(OBSERVATION_COUNT))
        + [None, None]
    )
    for receipt, position, ordinal in zip(receipts, positions, ordinals, strict=True):
        _require(
            set(receipt) == required_members
            and receipt["application_schedule_position"] == position
            and receipt["invocation_ordinal"] == ordinal
            and receipt["application_name"] == APPLICATION_ORDER[position - 1]
            and type(receipt["charged_rule_evaluations"]) is int
            and receipt["charged_rule_evaluations"] > 0
            and receipt["completed_rule_evaluations"]
            == receipt["charged_rule_evaluations"],
            "declared P1 receipt vector differs",
        )


def verify(
    repository_root: pathlib.Path | str, certificate: dict[str, Any]
) -> dict[str, Any]:
    root_path = pathlib.Path(repository_root)
    _require(set(certificate) == TOP_LEVEL_MEMBERS, "certificate members differ")
    supplied_id = certificate["case435_attainer_certificate_id"]
    payload = {
        key: value
        for key, value in certificate.items()
        if key != "case435_attainer_certificate_id"
    }
    expected_id = _sha256(
        _canonical_bytes({"domain": CERTIFICATE_DOMAIN, "payload": payload})
    )
    _require(supplied_id == expected_id, "certificate identity differs")
    seed, inventory, registry, literal, ledger = _read_authorities(root_path)
    _require(
        certificate["attainer_certificate_version"] == CERTIFICATE_VERSION
        and certificate["authority_sha256_by_path"]
        == dict(sorted(PINNED_SHA256.items()))
        and certificate["case435_dependency_manifest_id"] == DEPENDENCY_MANIFEST_ID,
        "certificate authority binding differs",
    )
    _require(
        inventory["external_schema_registry_v2"] == registry
        and literal["target_field_registry"] == inventory["target_field_registry"],
        "raw authority join differs",
    )
    _require(
        certificate["case_binding"]
        == {
            "case_position": CASE_POSITION,
            "constraint_scope_profile_id": PROFILE_ID,
            "logical_count_plan_id": PLAN_ID,
            "measured_sequence_ordinal": MEASURED_SEQUENCE_ORDINAL,
            "profile_conditioning_program_id": PROGRAM_ID,
            "profile_position": PROFILE_POSITION,
            "target_type_name": "TargetObservationV2",
        },
        "case binding differs",
    )
    protocol = certificate["construction_protocol"]
    _require(
        set(protocol)
        == {
            "a1_cartesian_tuple_count",
            "a1_legal_tuple_count",
            "a1_policy",
            "candidate_policy",
            "construction_protocol_version",
            "external_upper_channel_imported",
            "outer_role_total_field_proposal_count",
            "precomputed_witness_imported",
            "runtime_role",
            "total_field_proposal_count",
        }
        and protocol["construction_protocol_version"] == CONSTRUCTION_VERSION
        and protocol["external_upper_channel_imported"] is False
        and protocol["precomputed_witness_imported"] is False
        and protocol["runtime_role"]
        == "PINNED_P1_EXECUTION_AUTHORITY_NOT_OPTIMIZATION_SOURCE"
        and type(protocol["total_field_proposal_count"]) is int
        and protocol["total_field_proposal_count"] >= FIELD_COUNT
        and type(protocol["a1_cartesian_tuple_count"]) is int
        and type(protocol["a1_legal_tuple_count"]) is int
        and 0
        < protocol["a1_legal_tuple_count"]
        <= protocol["a1_cartesian_tuple_count"],
        "construction protocol differs",
    )

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
        "case/plan/program authority join differs",
    )
    schedule = program["application_schedule_operation"]
    instructions = schedule["ordered_schedule_segment_records"][0][
        "ordered_application_instruction_records"
    ]
    ledger_by_name = {
        row["application_name"]: row
        for row in ledger["ordered_rule_application_descriptors"]
    }
    _require(
        [row["application_name"] for row in instructions] == list(APPLICATION_ORDER)
        and all(
            ledger_by_name[row["application_name"]]["rule_application_id"]
            == row["rule_application_id"]
            for row in instructions
        ),
        "application schedule authority differs",
    )
    expected_schedule = {
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
    _require(
        certificate["schedule_authority"] == expected_schedule,
        "schedule certificate differs",
    )

    retained = certificate["retained_witness_context"]
    _require(
        set(retained)
        == {
            "checkpoint_selector",
            "ordered_observations",
            "target_observation_root",
        },
        "retained witness members differ",
    )
    selector = retained["checkpoint_selector"]
    observations = retained["ordered_observations"]
    root = retained["target_observation_root"]
    _require(
        type(selector) is dict and type(root) is dict and type(observations) is list,
        "retained witness shape differs",
    )
    _verify_record_identities(registry, selector, root, observations)
    _verify_lifecycle(selector, root, observations)
    measured = observations[MEASURED_SEQUENCE_ORDINAL]
    _verify_selected_fields(certificate, measured)
    measured_raw = _canonical_bytes(measured)
    root_raw = _canonical_bytes(root)
    expected_measurement = {
        "canonical_octets": len(measured_raw),
        "canonical_sha256": _sha256(measured_raw),
        "measured_sequence_ordinal": MEASURED_SEQUENCE_ORDINAL,
        "observation_id": measured["observation_id"],
        "observation_sequence_position": MEASURED_SEQUENCE_ORDINAL + 1,
        "ordered_observation_id_vector_sha256": _sha256(
            _canonical_bytes(root["ordered_observation_ids"])
        ),
        "root_canonical_sha256": _sha256(root_raw),
        "root_id": root["target_observation_root_sha256"],
    }
    _require(
        certificate["measured_attainer"] == expected_measurement,
        "measured attainer projection differs",
    )
    _require(
        certificate["p1_legal"] is True
        and certificate["legal_attainer_constructed"] is True
        and certificate["exactness_claimed"] is False
        and certificate["acceptance_state"]
        == "LEGAL_ATTAINER_CONSTRUCTED_EXACTNESS_JOIN_PENDING"
        and certificate["correction_subgate"] == "A4-P6-C435-C2"
        and certificate["next_subgate"] == "A4-P6-C435-C3",
        "C2 acceptance/nonclaim state differs",
    )
    _verify_declared_execution(certificate["p1_execution_certificate"], schedule)

    runtime_module = _load_runtime(root_path)
    runtime = runtime_module.ExternalSchemaV2Runtime.load(root_path)
    receipts = _execute_p1(
        runtime_module,
        runtime,
        root,
        observations,
        selector,
        inventory["marker_contract"],
        inventory["target_field_registry"],
    )
    execution = certificate["p1_execution_certificate"]
    expected_execution = {
        "all_applications_accepted": True,
        "application_invocation_count": len(receipts),
        "charged_rule_evaluation_count": sum(
            row["charged_rule_evaluations"] for row in receipts
        ),
        "completed_rule_evaluation_count": sum(
            row["completed_rule_evaluations"] for row in receipts
        ),
        "direct_expression_node_count": sum(
            row["direct_expression_nodes"] for row in receipts
        ),
        "ordered_application_execution_receipts": receipts,
        "receipt_vector_sha256": _sha256(_canonical_bytes(receipts)),
    }
    _require(execution == expected_execution, "P1 execution certificate differs")
    _require(
        execution["application_invocation_count"]
        == schedule["application_invocation_count"]
        and execution["charged_rule_evaluation_count"]
        == schedule["cross_rule_evaluation_count"]
        and execution["completed_rule_evaluation_count"]
        == schedule["cross_rule_evaluation_count"]
        and execution["direct_expression_node_count"]
        == schedule["direct_cross_expression_node_count"],
        "P1 work accounting differs",
    )
    return {
        "case435_attainer_certificate_id": supplied_id,
        "measured_attainer_canonical_octets": len(measured_raw),
        "measured_attainer_canonical_sha256": _sha256(measured_raw),
        "p1_application_invocation_count": len(receipts),
        "p1_rule_evaluation_count": execution["charged_rule_evaluation_count"],
        "p1_direct_expression_node_count": execution["direct_expression_node_count"],
        "p1_legal": True,
        "exactness_claimed": False,
        "acceptance_state": certificate["acceptance_state"],
        "next_subgate": certificate["next_subgate"],
    }


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) > 2:
        raise SystemExit("usage: check...py [repository-root] [certificate.json]")
    root = (
        pathlib.Path(argv[0]).resolve()
        if argv
        else pathlib.Path(__file__).resolve().parents[2]
    )
    try:
        raw = (
            pathlib.Path(argv[1]).read_bytes()
            if len(argv) == 2
            else sys.stdin.buffer.read()
        )
        certificate = _strict_load(raw, "case-435 attainer certificate")
        report = verify(root, certificate)
    except (
        CertificateError,
        OSError,
        KeyError,
        TypeError,
        ValueError,
    ) as error:
        sys.stderr.write(f"CASE435_ATTAINER_CERTIFICATE_REJECT: {error}\n")
        return 1
    sys.stdout.buffer.write(_canonical_bytes(report) + b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
