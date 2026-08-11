#!/usr/bin/env python3
"""Fail-closed record of the rejected Raw-V8 Step-2 V1 pilot bootstrap.

The canonical V1 pilot is permanently unavailable because verifier-owned
pre-search analysis proved that its mandatory coordinate/prefix catalog exceeds
its immutable seed caps.  This module therefore refuses canonical ``--check``
and ``--write`` requests.  Its only executable producer path is the retained,
explicitly reduced structural self-test under ``test_output``.  That self-test
is historical engineering evidence; it neither executes local transfers nor
claims a frozen-scope maximum, feasible pilot, or accepted cap.

Only Python's standard library and immutable repository authorities are used.
In particular, this file imports neither the independent verifier nor
``riskyieldmm``, a solver, or any sibling rule/application runtime.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, Final

CANONICALIZATION_VERSION: Final = "riskyieldmm_canonical_json_v1"
MEASUREMENT_SCHEMA_VERSION: Final = "riskyieldmm_physical_transport_a2m_raw_v49f_v8"
STRUCTURAL_ARTIFACT_VERSION: Final = (
    "riskyieldmm.raw_v8_step2_external_schema_v2."
    "maximum_protocol_structural_self_test.v1"
)
STRUCTURAL_STATUS: Final = "NON_AUTHORITATIVE_REDUCED_STRUCTURAL_TEST_ONLY"
STRUCTURAL_DOMAIN_KIND: Final = "REDUCED_STRUCTURAL_TEST_DOMAIN"

PROTOCOL_RELATIVE_PATH: Final = (
    "docs/research/"
    "v4_9f_a2_raw_v8_step2_constructive_maximum_protocol_freeze_2026-08-01.md"
)
INVENTORY_RELATIVE_PATH: Final = "tests/raw_v8_step2_inventory_v49f.json"
REGISTRY_RELATIVE_PATH: Final = (
    "scripts/tests/raw_v8_step2_external_schema_v2_structural_registry_v49f.json"
)
LITERAL_AUTHORITY_RELATIVE_PATH: Final = (
    "scripts/tests/raw_v8_step2_external_schema_v2_rule_literal_authority_v49f.json"
)
APPLICATION_WITNESS_RELATIVE_PATH: Final = (
    "scripts/tests/raw_v8_step2_external_schema_v2_application_witness_v49f.json"
)
CANONICAL_OUTPUT_RELATIVE_PATH: Final = (
    "scripts/tests/raw_v8_step2_external_schema_v2_maximum_protocol_pilot_v49f.json"
)
CANONICAL_SEED_OUTPUT_RELATIVE_PATH: Final = (
    "scripts/tests/"
    "raw_v8_step2_external_schema_v2_maximum_protocol_pilot_seed_v49f.json"
)
CANONICAL_SEED_PROTOCOL_RELATIVE_PATH: Final = (
    "scripts/tests/"
    "raw_v8_step2_external_schema_v2_maximum_protocol_pilot_seed_protocol_v49f.md"
)
STRUCTURAL_OUTPUT_RELATIVE_PATH: Final = (
    "test_output/"
    "raw_v8_step2_external_schema_v2_maximum_protocol_structural_self_test_v49f.json"
)

EXPECTED_REJECTED_PROTOCOL_OCTETS: Final = 246_093
EXPECTED_REJECTED_PROTOCOL_SHA256: Final = (
    "b3b39b3cb15caa450d9974925db9b5f0b91dd5832a462d2a8687dc19a50c4409"
)
EXPECTED_INVENTORY_PHYSICAL_SHA256: Final = (
    "f33c1019afa7f49a316aac1bfbef7498e240f391e4fee00dfd95fdcda658669f"
)
EXPECTED_INVENTORY_SEMANTIC_ID: Final = (
    "128d07a45dc2300c140f333cc3a45e2497aaa4089684f6e44da048ab403bbf9d"
)
EXPECTED_REGISTRY_PHYSICAL_SHA256: Final = (
    "9160297ff316c5931737c92f8b359f0a1e2ec22f0aa996ef3b09cf830dc96bf3"
)
EXPECTED_REGISTRY_SEMANTIC_ID: Final = (
    "5dc95a3e99c5646e912b6a7e9c3970cf2489d560ea890b0a19d38af4c51c2140"
)
EXPECTED_LITERAL_AUTHORITY_SHA256: Final = (
    "aba3461059367904734e2eb9ae404787b9aab5ed4c3fbcd292925a364926cce2"
)
EXPECTED_APPLICATION_WITNESS_SHA256: Final = (
    "d2f40badc85c58965a72e52fd98bfebbd4caf3335ec5a0415a89294cc3fb3415"
)

SAFE_INTEGER_MAXIMUM: Final = 9_007_199_254_740_991
MAXIMUM_INPUT_OCTETS: Final = 16_777_216
BITMAP_HEX_WIDTH: Final = 64

OBSERVABLE_DESCRIPTOR_ID_DOMAIN: Final = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumObservableDescriptorV1V4_9F_RawV8"
)
STATE_SIGNATURE_ID_DOMAIN: Final = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumStateSignatureV1V4_9F_RawV8"
)
STATE_CELL_ID_DOMAIN: Final = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumStateCellV1V4_9F_RawV8"
)
FRONTIER_COMMITMENT_ID_DOMAIN: Final = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumFrontierCommitmentV1V4_9F_RawV8"
)
CHOICE_PLAN_ID_DOMAIN: Final = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumChoiceCoordinatePlanV1V4_9F_RawV8"
)
STRUCTURAL_SCOPE_ID_DOMAIN: Final = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumStructuralScopeV1V4_9F_RawV8"
)
STRUCTURAL_CONTEXT_ID_DOMAIN: Final = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumStructuralContextV1V4_9F_RawV8"
)
STRUCTURAL_NODE_ID_DOMAIN: Final = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumStructuralProofNodeV1V4_9F_RawV8"
)
STRUCTURAL_CERTIFICATE_ID_DOMAIN: Final = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumStructuralCertificateV1V4_9F_RawV8"
)
STRUCTURAL_CASE_ID_DOMAIN: Final = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumStructuralCaseV1V4_9F_RawV8"
)
STRUCTURAL_OUTCOME_ID_DOMAIN: Final = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumStructuralOutcomeV1V4_9F_RawV8"
)
STRUCTURAL_ARTIFACT_ID_DOMAIN: Final = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumStructuralSelfTestV1V4_9F_RawV8"
)

NODE_KINDS: Final = (
    "FIXED_VALUE",
    "BOOLEAN_VALUE_FRONTIER",
    "SAFE_UINT_DIGIT_FRONTIER",
    "TEXT_LANGUAGE_FRONTIER",
    "NULLABLE_CASE_FRONTIER",
    "ARRAY_FRONTIER",
    "RECORD_FRONTIER",
    "TAGGED_UNION_FRONTIER",
    "CONSTRAINT_FRONTIER",
    "SCOPE_FRONTIER",
    "MAXIMUM_SLICE_EXACT_FRONTIER",
    "LEXICOGRAPHIC_PREFIX_EXCLUSION",
    "LOCAL_SHUTDOWN_MINIMALITY_FRONTIER",
    "CODEC_INTERSECTION_ATTAINMENT",
)

RESOURCE_CLAIM_FIELDS: Final = (
    "proof_node_count",
    "proof_edge_count",
    "maximum_proof_depth",
    "maximum_child_count",
    "state_signature_dimension_count",
    "maximum_state_signature_dimension_count",
    "state_catalog_entry_count",
    "state_catalog_canonicalized_octets",
    "peak_retained_state_catalog_octets",
    "frontier_state_entry_count",
    "frontier_bitmap_run_count",
    "frontier_expanded_point_count",
    "maximum_frontier_width",
    "peak_retained_frontier_octets",
    "frontier_transition_count",
    "frontier_canonicalized_octets",
    "hash_preimage_octets",
    "component_choice_coordinate_count",
    "certificate_canonical_octets",
)

METRIC_NAMES: Final = (
    "PROOF_NODE_COUNT_PER_CERTIFICATE",
    "PROOF_EDGE_COUNT_PER_CERTIFICATE",
    "MAXIMUM_PROOF_DEPTH_PER_CERTIFICATE",
    "MAXIMUM_CHILD_COUNT_PER_NODE",
    "MAXIMUM_STATE_SIGNATURE_DIMENSION_COUNT_PER_NODE",
    "STATE_CATALOG_ENTRY_COUNT_PER_CERTIFICATE",
    "STATE_CATALOG_CANONICALIZED_OCTETS_PER_CERTIFICATE",
    "PEAK_RETAINED_STATE_CATALOG_OCTETS_PER_CERTIFICATE",
    "FRONTIER_STATE_ENTRY_COUNT_PER_CERTIFICATE",
    "FRONTIER_BITMAP_RUN_COUNT_PER_CERTIFICATE",
    "EXPANDED_FRONTIER_POINT_COUNT_PER_CERTIFICATE",
    "MAXIMUM_LIVE_FRONTIER_WIDTH",
    "PEAK_RETAINED_FRONTIER_OCTETS_PER_CERTIFICATE",
    "FRONTIER_TRANSITION_COUNT_PER_CERTIFICATE",
    "FRONTIER_CANONICALIZED_OCTETS_PER_CERTIFICATE",
    "HASH_PREIMAGE_OCTETS_PER_CERTIFICATE",
    "COMPONENT_CHOICE_COORDINATE_COUNT_PER_ROW",
    "CERTIFICATE_CANONICAL_OCTETS",
    "MAXIMUM_ROW_RAW_OCTETS",
    "AGGREGATE_CONTEXT_OBJECT_COMPACT_OCTETS",
    "AGGREGATE_ROW_RAW_OCTETS",
    "AGGREGATE_COMPLETE_ARTIFACT_RAW_OCTETS",
)

PROFILE_BINDINGS: Final = {
    3: "92a80f3b2dc5d4b9a6284adfb6819823de7e2546d4141b2b12c5c7c9afff21f4",
    369: "505dac244288e6fb666919c99567f883c28ed573a898ce2a5dd680744dd57540",
    370: "b764c8c83c39681fe5de8c4064dd8dd25a97dd48c170f1206ce4e1904be74146",
    371: "323d26f06e1ac00198f8dfe9627b9d1759fcbe856ae4e2b68636c14e15785532",
    372: "46c0032e1f747c59b6e60e1bee4edf92c24d2894e9755c4c27d6362810066a47",
    373: "ab3d22d821ab9f68654e3f4c692db7021caeaab517cf0271078a38a3397b0cb1",
}
CHECKPOINT_OUTCOMES: Final = {
    369: "EXACT_MARKER",
    370: "ARTIFACT_BOUND_EXCEEDED",
    371: "OBSERVER_INTERNAL_ERROR",
    372: "SOURCE_CLOCK_UNAVAILABLE",
    373: "TARGET_BOUNDARY_NOT_REACHED",
}
EXPECTED_LOCAL_SHUTDOWN_BASELINE_SPEC_ID: Final = (
    "f88cf223f28a146b08b5ffbb3b5ce419fb7ce473563edb27900983d6583a2d21"
)
LOCAL_SHUTDOWN_INTRINSIC_RELATION_IDS: Final = (
    "maximum_terminal_ingress_plaintext_octets<=16384*maximum_terminal_ingress_batches",
    "2*maximum_terminal_ingress_parser_units<=maximum_terminal_ingress_plaintext_octets",
    "maximum_terminal_tls_records<=maximum_terminal_ingress_batches",
    "maximum_terminal_ingress_automatic_outputs<=maximum_terminal_ingress_parser_units",
    "maximum_websocket_send_attempts<=256*(1+maximum_terminal_ingress_automatic_outputs)",
)


class PilotError(ValueError):
    """Raised for an authority, structural, or publication-guard failure."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PilotError(message)


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise PilotError(f"canonical JSON failure: {exc}") from exc


def _pretty_bytes(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                value,
                allow_nan=False,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise PilotError(f"pretty JSON failure: {exc}") from exc


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _semantic_preimage(domain: str, payload: Any) -> bytes:
    return _canonical_bytes(
        {
            "canonicalization_version": CANONICALIZATION_VERSION,
            "domain": domain,
            "payload": payload,
            "schema_version": MEASUREMENT_SCHEMA_VERSION,
        }
    )


def _semantic_id(domain: str, payload: Any) -> str:
    return _sha256(_semantic_preimage(domain, payload))


def _duplicate_key_guard(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_float(_: str) -> Any:
    raise PilotError("floating-point JSON value rejected")


def _read_bytes(path: Path, expected_sha256: str | None = None) -> bytes:
    data = path.read_bytes()
    _require(len(data) < MAXIMUM_INPUT_OCTETS, f"input exceeds bound: {path}")
    if expected_sha256 is not None:
        _require(_sha256(data) == expected_sha256, f"authority hash drift: {path}")
    return data


def _read_json(path: Path, expected_sha256: str | None = None) -> dict[str, Any]:
    data = _read_bytes(path, expected_sha256)
    try:
        value = json.loads(
            data,
            object_pairs_hook=_duplicate_key_guard,
            parse_float=_reject_float,
            parse_constant=_reject_float,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PilotError(f"invalid JSON authority {path}: {exc}") from exc
    _require(type(value) is dict, f"JSON root is not an object: {path}")
    return value


def _safe_integer(value: Any, label: str) -> int:
    _require(
        type(value) is int and 0 <= value <= SAFE_INTEGER_MAXIMUM,
        f"unsafe integer for {label}",
    )
    return value


def _load_authorities(repository_root: Path) -> dict[str, Any]:
    protocol_path = repository_root / PROTOCOL_RELATIVE_PATH
    protocol_bytes = _read_bytes(protocol_path)
    _require(
        len(protocol_bytes) == EXPECTED_REJECTED_PROTOCOL_OCTETS
        and _sha256(protocol_bytes) == EXPECTED_REJECTED_PROTOCOL_SHA256,
        "rejected V1 protocol physical pin drift",
    )
    try:
        protocol_text = protocol_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PilotError("protocol is not UTF-8") from exc

    inventory = _read_json(
        repository_root / INVENTORY_RELATIVE_PATH,
        EXPECTED_INVENTORY_PHYSICAL_SHA256,
    )
    registry = _read_json(
        repository_root / REGISTRY_RELATIVE_PATH,
        EXPECTED_REGISTRY_PHYSICAL_SHA256,
    )
    _read_json(
        repository_root / LITERAL_AUTHORITY_RELATIVE_PATH,
        EXPECTED_LITERAL_AUTHORITY_SHA256,
    )
    application_witness = _read_json(
        repository_root / APPLICATION_WITNESS_RELATIVE_PATH,
        EXPECTED_APPLICATION_WITNESS_SHA256,
    )

    _require(
        inventory["inventory_sha256"] == EXPECTED_INVENTORY_SEMANTIC_ID,
        "inventory semantic identity drift",
    )
    _require(
        registry["external_schema_registry_id"] == EXPECTED_REGISTRY_SEMANTIC_ID,
        "registry semantic identity drift",
    )
    _require(
        inventory["external_schema_registry_v2"] == registry,
        "embedded and standalone registry differ",
    )
    _require(
        "Status: **REJECTED — PRE-SEARCH PLAN EXCEEDS IMMUTABLE SEED CAPS**"
        in protocol_text,
        "publication guard expected the rejected V1 protocol",
    )
    _require(
        protocol_text.count("`PILOT_PENDING`") >= len(METRIC_NAMES),
        "publication guard expected all resource ceilings to remain pending",
    )
    _require(
        tuple(METRIC_NAMES)
        == tuple(
            line.split("`")[1]
            for line in protocol_text.splitlines()
            if line.startswith("| ") and "PILOT_PENDING" in line and "`" in line
        )[-len(METRIC_NAMES) :],
        "protocol metric order drift",
    )
    return {
        "protocol_bytes": protocol_bytes,
        "protocol_text": protocol_text,
        "candidate_protocol_sha256": _sha256(protocol_bytes),
        "inventory": inventory,
        "registry": registry,
        "application_witness": application_witness,
    }


def _path_step(
    position: int,
    kind: str,
    *,
    member_name: str | None = None,
    member_position: int | None = None,
    array_ordinal: int | None = None,
    sequence_name: str | None = None,
    union_alternative_position: int | None = None,
    nullable_branch: str | None = None,
) -> dict[str, Any]:
    return {
        "step_position": position,
        "step_kind": kind,
        "member_name": member_name,
        "member_position": member_position,
        "array_ordinal": array_ordinal,
        "sequence_name": sequence_name,
        "union_alternative_position": union_alternative_position,
        "nullable_branch": nullable_branch,
    }


def _schema_locator(root_type_name: str, root_value_schema_id: str) -> dict[str, Any]:
    return {
        "locator_kind": "SCHEMA_DOMAIN",
        "record_reference_id": None,
        "root_type_name": root_type_name,
        "root_value_schema_id": root_value_schema_id,
        "ordered_path_steps": [],
        "transient_state_key": None,
        "transient_source_child_position": None,
        "transient_source_child_proof_node_id": None,
    }


def _inventory_locator(reference: str, root_type_name: str) -> dict[str, Any]:
    return {
        "locator_kind": "V3_INVENTORY_POINTER",
        "record_reference_id": reference,
        "root_type_name": root_type_name,
        "root_value_schema_id": None,
        "ordered_path_steps": [],
        "transient_state_key": None,
        "transient_source_child_position": None,
        "transient_source_child_proof_node_id": None,
    }


def _atom(kind: str, value: Any = None) -> dict[str, Any]:
    atom = {
        "atom_kind": kind,
        "boolean_value": None,
        "integer_value": None,
        "text_value": None,
        "position_value": None,
        "canonical_bytes_hex_value": None,
    }
    if kind in {"INACTIVE", "NULL"}:
        _require(value is None, f"{kind} atom carries a value")
    elif kind == "BOOLEAN":
        _require(type(value) is bool, "BOOLEAN atom value is invalid")
        atom["boolean_value"] = value
    elif kind == "SAFE_INTEGER":
        _require(type(value) is int and type(value) is not bool, "integer atom invalid")
        atom["integer_value"] = _safe_integer(value, "atom")
    elif kind == "TEXT":
        _require(type(value) is str, "TEXT atom value is invalid")
        atom["text_value"] = value
    elif kind == "POSITION":
        atom["position_value"] = _safe_integer(value, "position atom")
    elif kind == "CANONICAL_BYTES":
        _require(
            type(value) is str
            and len(value) % 2 == 0
            and value == value.lower()
            and all(character in "0123456789abcdef" for character in value),
            "CANONICAL_BYTES atom value is invalid",
        )
        atom["canonical_bytes_hex_value"] = value
    else:
        raise PilotError(f"unknown atom kind: {kind}")
    return atom


def _state_cell(
    *,
    cell_kind: str,
    exact_atom: dict[str, Any] | None,
    integer_interval: dict[str, Any] | None,
    catalog_id: str | None,
    catalog_position: int | None,
) -> dict[str, Any]:
    payload = {
        "cell_kind": cell_kind,
        "exact_atom": exact_atom,
        "integer_interval": integer_interval,
        "catalog_id": catalog_id,
        "catalog_position": catalog_position,
    }
    return {**payload, "state_cell_id": _semantic_id(STATE_CELL_ID_DOMAIN, payload)}


def _exact_cell(atom: dict[str, Any]) -> dict[str, Any]:
    return _state_cell(
        cell_kind="EXACT_ATOM",
        exact_atom=atom,
        integer_interval=None,
        catalog_id=None,
        catalog_position=None,
    )


def _integer_interval_cell(
    minimum: int, maximum: int, digit_count: int
) -> dict[str, Any]:
    return _state_cell(
        cell_kind="SAFE_INTEGER_INTERVAL",
        exact_atom=None,
        integer_interval={
            "inclusive_minimum": minimum,
            "inclusive_maximum": maximum,
            "decimal_digit_count": digit_count,
            "ordered_constant_affine_region_ids": [],
        },
        catalog_id=None,
        catalog_position=None,
    )


def _state_key(vector: Sequence[dict[str, Any]]) -> tuple[bytes, ...]:
    return tuple(_canonical_bytes(cell) for cell in vector)


def _bitmap_runs(lengths: Iterable[int]) -> list[dict[str, Any]]:
    blocks: dict[int, int] = {}
    for length in sorted(set(lengths)):
        _safe_integer(length, "frontier length")
        block_index, bit_index = divmod(length, 256)
        blocks[block_index] = blocks.get(block_index, 0) | (1 << bit_index)

    runs: list[dict[str, Any]] = []
    for block_index, bitmap in sorted(blocks.items()):
        bitmap_hex = f"{bitmap:0{BITMAP_HEX_WIDTH}x}"
        _require(
            len(bitmap_hex) == BITMAP_HEX_WIDTH
            and bitmap_hex != "0" * BITMAP_HEX_WIDTH,
            "invalid bitmap spelling",
        )
        if (
            runs
            and runs[-1]["last_block_index"] + 1 == block_index
            and runs[-1]["attainable_length_bitmap_hex"] == bitmap_hex
        ):
            runs[-1]["last_block_index"] = block_index
        else:
            runs.append(
                {
                    "first_block_index": block_index,
                    "last_block_index": block_index,
                    "attainable_length_bitmap_hex": bitmap_hex,
                }
            )
    return runs


def _dimension(
    position: int,
    kind: str,
    comparison: str,
    subject_locator: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    payload = {
        "dimension_position": position,
        "dimension_kind": kind,
        "subject_locator": subject_locator,
        "value_schema_id": None,
        "comparison_semantics": comparison,
        "ordered_activation_guard_clauses": [],
    }
    preimage = _semantic_preimage(OBSERVABLE_DESCRIPTOR_ID_DOMAIN, payload)
    return (
        {**payload, "observable_descriptor_id": _sha256(preimage)},
        len(preimage),
    )


def _frontier_points(
    kind: str, witness_octets: int
) -> tuple[list[dict[str, Any]], list[tuple[list[dict[str, Any]], int]]]:
    if kind == "BOOLEAN_VALUE_FRONTIER":
        dimensions = [("BOOLEAN_VALUE", "FALSE_BEFORE_TRUE")]
        points = [
            ([_exact_cell(_atom("BOOLEAN", False))], 5),
            ([_exact_cell(_atom("BOOLEAN", True))], 4),
        ]
    elif kind == "SAFE_UINT_DIGIT_FRONTIER":
        dimensions = [("SAFE_INTEGER_VALUE", "MATHEMATICAL_INTEGER")]
        points = [
            ([_integer_interval_cell(0, 9, 1)], 1),
            ([_integer_interval_cell(10, 99, 2)], 2),
        ]
    elif kind == "TEXT_LANGUAGE_FRONTIER":
        dimensions = [("CATALOG_POSITION", "FROZEN_CATALOG_POSITION")]
        points = [
            ([_exact_cell(_atom("POSITION", 0))], 3),
            ([_exact_cell(_atom("POSITION", 1))], 3),
        ]
    elif kind == "NULLABLE_CASE_FRONTIER":
        dimensions = [("NULLABILITY_BRANCH", "NULL_BEFORE_NON_NULL")]
        points = [
            ([_exact_cell(_atom("POSITION", 0))], 4),
            ([_exact_cell(_atom("POSITION", 1))], 5),
        ]
    elif kind == "ARRAY_FRONTIER":
        dimensions = [("CATALOG_POSITION", "FROZEN_CATALOG_POSITION")]
        points = [
            ([_exact_cell(_atom("POSITION", 0))], 2),
            ([_exact_cell(_atom("POSITION", 1))], 5),
            ([_exact_cell(_atom("POSITION", 2))], 9),
        ]
    elif kind == "TAGGED_UNION_FRONTIER":
        dimensions = [("UNION_ALTERNATIVE_POSITION", "FROZEN_CATALOG_POSITION")]
        points = [
            ([_exact_cell(_atom("POSITION", 0))], 37),
            ([_exact_cell(_atom("POSITION", 1))], 37),
        ]
    elif kind == "SCOPE_FRONTIER":
        dimensions = [("ROOT_FAMILY_POSITION", "FROZEN_CATALOG_POSITION")]
        points = [([_exact_cell(_atom("POSITION", 1))], witness_octets)]
    else:
        dimensions = []
        if kind == "FIXED_VALUE":
            points = [([], 7)]
        elif kind == "RECORD_FRONTIER":
            # Identical bit positions in adjacent blocks exercise mandatory
            # canonical run merging without pretending to be a transfer result.
            points = [([], 31), ([], 287)]
        elif kind == "CONSTRAINT_FRONTIER":
            points = [
                ([], length) for length in sorted({31, 33, 257, 259, witness_octets})
            ]
        elif kind == "MAXIMUM_SLICE_EXACT_FRONTIER":
            points = [([], witness_octets)]
        elif kind == "LEXICOGRAPHIC_PREFIX_EXCLUSION":
            points = [([], witness_octets)]
        elif kind == "LOCAL_SHUTDOWN_MINIMALITY_FRONTIER":
            points = [([], witness_octets)]
        else:
            points = [([], witness_octets)]
    return [
        {"dimension_kind": dimension_kind, "comparison_semantics": comparison}
        for dimension_kind, comparison in dimensions
    ], points


def _build_frontier(
    *,
    kind: str,
    subject_locator: dict[str, Any],
    witness_octets: int,
    measured_winner: list[dict[str, Any]] | None,
    context_winner: list[dict[str, Any]] | None,
) -> tuple[
    list[dict[str, Any]],
    dict[str, Any],
    dict[str, Any],
    dict[str, int],
]:
    dimension_specs, raw_points = _frontier_points(kind, witness_octets)
    dimensions: list[dict[str, Any]] = []
    identity_octets = 0
    for state, _ in raw_points:
        for cell in state:
            cell_payload = {
                key: value for key, value in cell.items() if key != "state_cell_id"
            }
            cell_preimage = _semantic_preimage(STATE_CELL_ID_DOMAIN, cell_payload)
            _require(
                cell["state_cell_id"] == _sha256(cell_preimage),
                "state-cell identity drift",
            )
            identity_octets += len(cell_preimage)
    for position, spec in enumerate(dimension_specs, start=1):
        dimension, preimage_octets = _dimension(
            position,
            spec["dimension_kind"],
            spec["comparison_semantics"],
            subject_locator,
        )
        dimensions.append(dimension)
        identity_octets += preimage_octets

    signature_payload = {"ordered_state_dimensions": dimensions}
    signature_preimage = _semantic_preimage(
        STATE_SIGNATURE_ID_DOMAIN, signature_payload
    )
    signature_id = _sha256(signature_preimage)
    identity_octets += len(signature_preimage)

    unique_points = sorted(
        {
            (_canonical_bytes(state), length): state for state, length in raw_points
        }.items(),
        key=lambda item: (_state_key(item[1]), item[0][1]),
    )
    expanded = [
        {"state_key": state, "canonical_byte_length": key[1]}
        for key, state in unique_points
    ]
    grouped: dict[bytes, tuple[list[dict[str, Any]], list[int]]] = {}
    for point in expanded:
        encoded_state = _canonical_bytes(point["state_key"])
        grouped.setdefault(encoded_state, (point["state_key"], []))[1].append(
            point["canonical_byte_length"]
        )
    state_frontiers = [
        {
            "state_key": state,
            "ordered_length_bitmap_runs": _bitmap_runs(lengths),
        }
        for state, lengths in sorted(
            grouped.values(), key=lambda item: _state_key(item[0])
        )
    ]
    expanded_bytes = _canonical_bytes(expanded)
    bitmap_bytes = _canonical_bytes(state_frontiers)
    output_frontier = {
        "frontier_soundness": "EXACT_ATTAINABLE",
        "state_signature_id": signature_id,
        "ordered_observable_descriptor_ids": [
            dimension["observable_descriptor_id"] for dimension in dimensions
        ],
        "ordered_state_frontiers": state_frontiers,
    }
    maximum = max(point["canonical_byte_length"] for point in expanded)
    commitment_payload = {
        "frontier_version": (
            "riskyieldmm.raw_v8_step2_external_schema_v2.attainable_frontier.v1"
        ),
        "state_signature_id": signature_id,
        "state_entry_count": len(state_frontiers),
        "bitmap_run_count": sum(
            len(entry["ordered_length_bitmap_runs"]) for entry in state_frontiers
        ),
        "expanded_attainable_point_count": len(expanded),
        "minimum_attainable_octets": min(
            point["canonical_byte_length"] for point in expanded
        ),
        "maximum_attainable_octets": maximum,
        "expanded_frontier_sha256": _sha256(expanded_bytes),
        "canonical_bitmap_run_frontier_sha256": _sha256(bitmap_bytes),
        "least_measured_choice_vector_sha256_at_maximum": (
            None
            if measured_winner is None
            else _sha256(_canonical_bytes(measured_winner))
        ),
        "least_context_choice_vector_sha256_at_maximum": (
            None
            if context_winner is None
            else _sha256(_canonical_bytes(context_winner))
        ),
    }
    commitment_preimage = _semantic_preimage(
        FRONTIER_COMMITMENT_ID_DOMAIN, commitment_payload
    )
    commitment = {
        **commitment_payload,
        "frontier_commitment_id": _sha256(commitment_preimage),
    }
    metrics = {
        "frontier_canonicalized_octets": len(expanded_bytes) + len(bitmap_bytes),
        "frontier_compact_octets": len(_canonical_bytes(output_frontier)),
        "hash_preimage_octets": (
            identity_octets
            + len(expanded_bytes)
            + len(bitmap_bytes)
            + len(commitment_preimage)
        ),
    }
    return dimensions, output_frontier, commitment, metrics


def _measurement_binding(
    binding_kind: str,
    validation_root_type_name: str,
    measured_path: list[str],
    sequence_name: str | None = None,
    sequence_ordinal: int | None = None,
) -> dict[str, Any]:
    return {
        "binding_kind": binding_kind,
        "validation_root_type_name": validation_root_type_name,
        "measured_value_typed_member_path": measured_path,
        "sequence_binding_name": sequence_name,
        "sequence_ordinal": sequence_ordinal,
    }


def _case_binding(
    *,
    type_name: str,
    alternative_name: str | None,
    constraint_scope: str,
    profile_id: str | None,
    profile_position: int | None,
    measurement_binding: dict[str, Any],
) -> dict[str, Any]:
    return {
        "type_name": type_name,
        "alternative_name": alternative_name,
        "constraint_scope": constraint_scope,
        "constraint_scope_profile_id": profile_id,
        "profile_position": profile_position,
        "measurement_binding": measurement_binding,
        "pilot_domain_kind": STRUCTURAL_DOMAIN_KIND,
    }


def _codec_coordinate() -> dict[str, Any]:
    return {
        "validation_root_type_name": "CapacityMeasurementOperationResultEvidence",
        "codec_owner_type_name": "CapacityMeasurementOperationResultEvidence",
        "codec_owner_typed_member_path": [],
        "codec_byte_bound_relation": "LT",
        "codec_octet_limit": 524_288,
    }


def _choice_plan(subject_locator: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "coordinate_plan_position": 1,
        "coordinate_scope": "MEASURED_RECORD",
        "coordinate_kind": "BOOLEAN_VALUE",
        "subject_locator": subject_locator,
        "value_schema_id": None,
        "ordered_activation_guard_clauses": [],
    }
    return {
        **payload,
        "choice_coordinate_plan_id": _semantic_id(CHOICE_PLAN_ID_DOMAIN, payload),
    }


def _derivation(
    *,
    kind: str,
    children: list[int],
    binding: dict[str, Any],
    scope_id: str,
    witness_bytes: bytes,
    subject_locator: dict[str, Any],
    choice_plan_id: str,
    registry: dict[str, Any],
    baseline_result_canonical_byte_length: int,
) -> dict[str, Any]:
    if kind == "FIXED_VALUE":
        fixed = _canonical_bytes("BOOL")
        return {
            "derivation_kind": kind,
            "fixed_source_kind": "SCHEMA_LITERAL",
            "fixed_source_locator": subject_locator,
            "fixed_transfer_kind": "EXACT_FIXED_VALUE",
            "fixed_canonical_byte_length": len(fixed),
            "fixed_canonical_sha256": _sha256(fixed),
            "derived_identity_mapping_catalog_id": None,
            "ordered_identity_payload_child_positions": [],
        }
    if kind == "BOOLEAN_VALUE_FRONTIER":
        return {"derivation_kind": kind, "ordered_boolean_values": [False, True]}
    if kind == "SAFE_UINT_DIGIT_FRONTIER":
        return {
            "derivation_kind": kind,
            "integer_minimum": 0,
            "integer_maximum": 99,
            "ordered_decimal_digit_bands": [
                {"digit_count": 1, "inclusive_minimum": 0, "inclusive_maximum": 9},
                {"digit_count": 2, "inclusive_minimum": 10, "inclusive_maximum": 99},
            ],
        }
    if kind == "TEXT_LANGUAGE_FRONTIER":
        language = next(
            item
            for item in registry["text_language_catalog"]
            if item["language_kind"] in {"LITERAL", "ENUM"}
        )
        return {
            "derivation_kind": kind,
            "text_language_id": language["text_language_id"],
            "language_kind": language["language_kind"],
            "text_solver_kind": "FINITE_LITERAL_ENUMERATION",
            "unicode_version": None,
        }
    if kind == "NULLABLE_CASE_FRONTIER":
        return {
            "derivation_kind": kind,
            "null_branch_enabled": True,
            "non_null_child_position": children[0],
        }
    if kind == "ARRAY_FRONTIER":
        return {
            "derivation_kind": kind,
            "array_minimum_items": 0,
            "array_maximum_items": 2,
            "item_child_position": children[0],
            "array_semantics": "POSITIONAL",
            "array_transfer_kind": "EXACT_ARRAY_FRONTIER",
        }
    if kind == "RECORD_FRONTIER":
        return {
            "derivation_kind": kind,
            "record_type_name": "CapacityMeasurementAckDeadlineExpirySpecV1",
            "ordered_member_child_positions": children,
            "derived_identity_member_name": None,
        }
    if kind == "TAGGED_UNION_FRONTIER":
        descriptor = next(
            item
            for item in registry["ordered_external_type_descriptors"]
            if item["type_name"] == "CapacityMeasurementOperationResultBody"
        )
        return {
            "derivation_kind": kind,
            "union_type_name": descriptor["type_name"],
            "ordered_alternative_child_positions": children,
            "ordered_alternative_names": [
                item["alternative_name"]
                for item in descriptor["tagged_union_descriptor"][
                    "ordered_alternatives"
                ]
            ],
            "owner_constraint_present": True,
        }
    if kind == "CONSTRAINT_FRONTIER":
        constraint_id = registry["ordered_cross_field_rule_descriptors"][0]["rule_id"]
        return {
            "derivation_kind": kind,
            "constraint_source_kind": "INTRINSIC_RULE",
            "ordered_constraint_ids": [constraint_id],
            "application_invocation": None,
            "ordered_applicable_scope_case_positions": [],
            "constraint_transfer_kind": "EXACT_RULE_EVALUATION",
            "relaxation_direction": None,
            "input_frontier_child_position": children[0],
        }
    if kind == "SCOPE_FRONTIER":
        binding_kind = binding["measurement_binding"]["binding_kind"]
        transfer = {
            "SELF_RECORD": "INTRINSIC_SELF",
            "OWNER_MEMBER_UNION_VALUE": "OWNER_MEMBER",
            "OUTER_RESULT_RECORD": "OUTER_RESULT_APPLICATION",
            "ROOT_EXACT_CHECKPOINT_OBSERVATION": "ROOT_APPLICATION",
        }[binding_kind]
        return {
            "derivation_kind": kind,
            "constraint_scope": binding["constraint_scope"],
            "constraint_scope_id": scope_id,
            "constraint_scope_profile_id": binding["constraint_scope_profile_id"],
            "measurement_binding": binding["measurement_binding"],
            "ordered_scope_cases": [
                {
                    "scope_case_position": 1,
                    "root_family_position": 1
                    if transfer == "ROOT_APPLICATION"
                    else None,
                    "mode_attempt_pair_position": None,
                    "observation_role_position": None,
                    "measured_sequence_ordinal": binding["measurement_binding"][
                        "sequence_ordinal"
                    ],
                    "ordered_application_invocations": [],
                    "scope_case_child_position": children[0],
                }
            ],
            "scope_transfer_kind": transfer,
        }
    if kind == "MAXIMUM_SLICE_EXACT_FRONTIER":
        return {
            "derivation_kind": kind,
            "target_canonical_byte_length": len(witness_bytes),
            "ordered_exact_constraint_bindings": [],
            "ordered_exact_domain_reinstatement_node_positions": [],
            "ordered_choice_coordinate_plan_ids": [choice_plan_id],
            "upper_frontier_child_position": children[0],
        }
    if kind == "LEXICOGRAPHIC_PREFIX_EXCLUSION":
        return {
            "derivation_kind": kind,
            "target_canonical_byte_length": len(witness_bytes),
            "choice_scope": "MEASURED_RECORD",
            "choice_coordinate_plan_id": choice_plan_id,
            "fixed_prefix_coordinate_count": 1,
            "selected_atom": _atom("BOOLEAN", False),
            "input_prefix_frontier_child_position": children[0],
        }
    if kind == "LOCAL_SHUTDOWN_MINIMALITY_FRONTIER":
        return {
            "derivation_kind": kind,
            "baseline_spec_record_reference": (
                "/fixture_records/operation_specs/LOCAL_SHUTDOWN"
            ),
            "ordered_mutable_limit_member_names": [
                "maximum_terminal_ingress_automatic_outputs",
                "maximum_terminal_ingress_batches",
                "maximum_terminal_ingress_ciphertext_octets",
                "maximum_terminal_ingress_parser_units",
                "maximum_terminal_ingress_plaintext_octets",
                "maximum_terminal_socket_receive_calls",
                "maximum_terminal_tls_records",
                "maximum_terminal_tls_unwrap_iterations",
                "maximum_terminal_zero_progress_iterations",
                "maximum_tls_control_send_attempts",
                "maximum_websocket_send_attempts",
            ],
            "ordered_intrinsic_relation_ids": list(
                LOCAL_SHUTDOWN_INTRINSIC_RELATION_IDS
            ),
            "prospective_result_attainment_mode": (
                "PROSPECTIVE_BYTE_MAXIMUM_WITH_ONE_MASKED_OUTER_CODEC"
            ),
            "masked_outer_codec_coordinate": _codec_coordinate(),
            "baseline_result_inventory_json_pointer": (
                "/fixture_records/operation_results/LOCAL_SHUTDOWN"
            ),
            "baseline_result_canonical_byte_length": (
                baseline_result_canonical_byte_length
            ),
            "outer_codec_byte_bound_relation": "LT",
            "outer_codec_octet_limit": 524_288,
            "winning_objective": {
                "changed_limit_field_count": 0,
                "sum_of_absolute_integer_deltas": "0",
                "changed_member_names_in_lexical_order": [],
                "resulting_changed_values_in_that_same_order": [],
            },
            "prospective_result_canonical_byte_length": len(witness_bytes),
            "prospective_result_canonical_sha256": _sha256(witness_bytes),
            "baseline_spec_fixed_child_position": children[0],
            "ordered_boundary_candidate_root_positions": [],
            "ordered_breakpoint_records": [],
            "ordered_interval_exclusion_records": [],
            "ordered_recurrence_state_records": [],
            "ordered_recurrence_transition_records": [],
            "ordered_dominance_deletion_records": [],
            "recurrence_version": (
                "LEXICAL_SUBSET_UINT128_DELTA_AND_PROSPECTIVE_BYTE_FRONTIER_V1"
            ),
        }
    _require(kind == "CODEC_INTERSECTION_ATTAINMENT", "unknown node kind")
    return {
        "derivation_kind": kind,
        "attainment_mode": "BYTE_MAXIMUM",
        "codec_byte_bound_relation": "LE",
        "codec_octet_limit": max(545, len(witness_bytes)),
        "owner_codec_byte_bound_relation": None,
        "owner_codec_octet_limit": None,
        "masked_codec_coordinate": None,
        "certified_upper_bound_octets": len(witness_bytes),
        "attaining_witness_canonical_byte_length": len(witness_bytes),
        "attaining_witness_canonical_sha256": _sha256(witness_bytes),
        "attaining_scope_case_position": 1,
        "upper_frontier_child_position": children[0],
        "winner_frontier_child_position": children[1],
    }


def _proof_depths(nodes: list[dict[str, Any]]) -> list[int]:
    depths: list[int] = []
    for node in nodes:
        children = node["ordered_child_positions"]
        _require(
            all(1 <= child < node["proof_node_position"] for child in children),
            "proof edge is not strictly backward",
        )
        depths.append(
            1 if not children else 1 + max(depths[child - 1] for child in children)
        )
    return depths


def _assert_reachable(nodes: list[dict[str, Any]]) -> None:
    reachable: set[int] = set()
    pending = [len(nodes)]
    while pending:
        position = pending.pop()
        if position in reachable:
            continue
        reachable.add(position)
        pending.extend(nodes[position - 1]["ordered_child_positions"])
    _require(
        reachable == set(range(1, len(nodes) + 1)), "proof DAG has unreachable nodes"
    )


def _structural_certificate(
    *,
    case_id: str,
    binding: dict[str, Any],
    witness: Any,
    candidate_protocol_sha256: str,
    registry: dict[str, Any],
    baseline_result_canonical_byte_length: int,
) -> dict[str, Any]:
    witness_bytes = _canonical_bytes(witness)
    structural_value_schema_id = registry["value_schema_catalog"][0]["value_schema_id"]
    subject_locator = _schema_locator(binding["type_name"], structural_value_schema_id)
    scope_payload = {
        "case_id": case_id,
        "binding": binding,
        "candidate_protocol_sha256": candidate_protocol_sha256,
        "domain_kind": STRUCTURAL_DOMAIN_KIND,
    }
    scope_id = _semantic_id(STRUCTURAL_SCOPE_ID_DOMAIN, scope_payload)
    context_id = _semantic_id(
        STRUCTURAL_CONTEXT_ID_DOMAIN,
        {"case_id": case_id, "candidate_protocol_sha256": candidate_protocol_sha256},
    )
    choice_plan = _choice_plan(subject_locator)

    plan: list[tuple[str, list[int]]] = [
        ("FIXED_VALUE", []),
        ("BOOLEAN_VALUE_FRONTIER", []),
        ("SAFE_UINT_DIGIT_FRONTIER", []),
        ("TEXT_LANGUAGE_FRONTIER", []),
        ("NULLABLE_CASE_FRONTIER", [2]),
        ("ARRAY_FRONTIER", [3]),
        ("RECORD_FRONTIER", [1, 4, 5, 6]),
        ("TAGGED_UNION_FRONTIER", [1, 5, 6, 7]),
        ("CONSTRAINT_FRONTIER", [8]),
        ("SCOPE_FRONTIER", [9]),
        ("MAXIMUM_SLICE_EXACT_FRONTIER", [10]),
        ("LEXICOGRAPHIC_PREFIX_EXCLUSION", [11]),
        ("LOCAL_SHUTDOWN_MINIMALITY_FRONTIER", [12]),
        ("CODEC_INTERSECTION_ATTAINMENT", [13, 12]),
    ]
    _require(tuple(kind for kind, _ in plan) == NODE_KINDS, "node kind order drift")

    winner_measured = [_atom("BOOLEAN", False)]
    winner_context: list[dict[str, Any]] = []
    nodes: list[dict[str, Any]] = []
    frontier_metrics: list[dict[str, int]] = []
    hash_preimage_octets = len(
        _semantic_preimage(STRUCTURAL_SCOPE_ID_DOMAIN, scope_payload)
    )
    hash_preimage_octets += len(
        _semantic_preimage(
            STRUCTURAL_CONTEXT_ID_DOMAIN,
            {
                "case_id": case_id,
                "candidate_protocol_sha256": candidate_protocol_sha256,
            },
        )
    )
    hash_preimage_octets += len(
        _semantic_preimage(
            CHOICE_PLAN_ID_DOMAIN,
            {
                key: value
                for key, value in choice_plan.items()
                if key != "choice_coordinate_plan_id"
            },
        )
    )

    ceiling = max(545, len(witness_bytes))
    for position, (kind, children) in enumerate(plan, start=1):
        measured_digest_vector = winner_measured if position >= 12 else None
        context_digest_vector = winner_context if position >= 13 else None
        dimensions, output, commitment, metrics = _build_frontier(
            kind=kind,
            subject_locator=subject_locator,
            witness_octets=len(witness_bytes),
            measured_winner=measured_digest_vector,
            context_winner=context_digest_vector,
        )
        frontier_metrics.append(metrics)
        hash_preimage_octets += metrics["hash_preimage_octets"]
        derivation = _derivation(
            kind=kind,
            children=children,
            binding=binding,
            scope_id=scope_id,
            witness_bytes=witness_bytes,
            subject_locator=subject_locator,
            choice_plan_id=choice_plan["choice_coordinate_plan_id"],
            registry=registry,
            baseline_result_canonical_byte_length=(
                baseline_result_canonical_byte_length
            ),
        )
        node_without_id = {
            "proof_node_position": position,
            "proof_node_kind": kind,
            "subject_locator": subject_locator,
            "value_schema_id": None,
            "type_name": binding["type_name"]
            if kind in {"RECORD_FRONTIER", "SCOPE_FRONTIER"}
            else None,
            "alternative_name": binding["alternative_name"]
            if kind == "TAGGED_UNION_FRONTIER"
            else None,
            "effective_canonical_octet_ceiling": ceiling,
            "ordered_child_positions": children,
            "ordered_child_proof_node_ids": [
                nodes[child - 1]["proof_node_id"] for child in children
            ],
            "ordered_ancestor_observable_dimensions": dimensions,
            "output_frontier": output,
            "frontier_commitment": commitment,
            "derivation": derivation,
        }
        wrapper = {
            "maximum_protocol_sha256": candidate_protocol_sha256,
            "proof_scope_authority_id": scope_id,
            "proof_context_authority_id": context_id,
            "node": node_without_id,
        }
        node_preimage = _semantic_preimage(STRUCTURAL_NODE_ID_DOMAIN, wrapper)
        hash_preimage_octets += len(node_preimage)
        nodes.append({**node_without_id, "proof_node_id": _sha256(node_preimage)})

    _assert_reachable(nodes)
    depths = _proof_depths(nodes)
    frontier_octets = [metric["frontier_compact_octets"] for metric in frontier_metrics]
    peak_retained = max(
        frontier_octets[position - 1]
        + sum(frontier_octets[child - 1] for child in node["ordered_child_positions"])
        for position, node in enumerate(nodes, start=1)
    )
    claim = {
        "proof_node_count": len(nodes),
        "proof_edge_count": sum(len(node["ordered_child_positions"]) for node in nodes),
        "maximum_proof_depth": max(depths),
        "maximum_child_count": max(
            len(node["ordered_child_positions"]) for node in nodes
        ),
        "state_signature_dimension_count": sum(
            len(node["ordered_ancestor_observable_dimensions"]) for node in nodes
        ),
        "maximum_state_signature_dimension_count": max(
            len(node["ordered_ancestor_observable_dimensions"]) for node in nodes
        ),
        "state_catalog_entry_count": 0,
        "state_catalog_canonicalized_octets": 0,
        "peak_retained_state_catalog_octets": 0,
        "frontier_state_entry_count": sum(
            node["frontier_commitment"]["state_entry_count"] for node in nodes
        ),
        "frontier_bitmap_run_count": sum(
            node["frontier_commitment"]["bitmap_run_count"] for node in nodes
        ),
        "frontier_expanded_point_count": sum(
            node["frontier_commitment"]["expanded_attainable_point_count"]
            for node in nodes
        ),
        "maximum_frontier_width": max(
            node["frontier_commitment"]["expanded_attainable_point_count"]
            for node in nodes
        ),
        "peak_retained_frontier_octets": peak_retained,
        "frontier_transition_count": sum(
            node["frontier_commitment"]["expanded_attainable_point_count"]
            * max(1, len(node["ordered_child_positions"]))
            for node in nodes
        ),
        "frontier_canonicalized_octets": sum(
            metric["frontier_canonicalized_octets"] for metric in frontier_metrics
        ),
        "hash_preimage_octets": 0,
        "component_choice_coordinate_count": 1,
        "certificate_canonical_octets": 0,
    }
    _require(tuple(claim) == RESOURCE_CLAIM_FIELDS, "resource claim order drift")
    certificate_without_id = {
        "certificate_version": (
            "riskyieldmm.raw_v8_step2_external_schema_v2."
            "structural_upper_bound_certificate.v1"
        ),
        "certificate_status": STRUCTURAL_STATUS,
        "topology_status": "NONCANONICAL_ALL_KIND_TAG_CONNECTIVITY_ONLY",
        "candidate_protocol_sha256": candidate_protocol_sha256,
        "constraint_scope_id": scope_id,
        "structural_context_id": context_id,
        "measured_type_name": binding["type_name"],
        "alternative_name": binding["alternative_name"],
        "structural_choice_coordinate_plan": choice_plan,
        "ordered_proof_nodes": nodes,
        "root_proof_node_position": len(nodes),
        "proof_resource_claim": claim,
        "observed_retained_value_canonical_octets": len(witness_bytes),
        "observed_retained_value_canonical_sha256": _sha256(witness_bytes),
        "nonclaim": (
            "No frontier in this certificate denotes the full frozen scope; "
            "the connected all-kind tag DAG is neither the canonical ordinary "
            "topology nor the separate local-root topology, and no numeric "
            "maximum or cap is asserted."
        ),
    }
    fixed_hash_octets = hash_preimage_octets + len(witness_bytes)
    certificate: dict[str, Any] = {}
    for _ in range(32):
        preimage = _semantic_preimage(
            STRUCTURAL_CERTIFICATE_ID_DOMAIN, certificate_without_id
        )
        desired_hash_octets = fixed_hash_octets + len(preimage)
        if claim["hash_preimage_octets"] != desired_hash_octets:
            claim["hash_preimage_octets"] = desired_hash_octets
            continue
        certificate = {
            **certificate_without_id,
            "structural_certificate_id": _sha256(preimage),
        }
        desired_length = len(_canonical_bytes(certificate))
        if claim["certificate_canonical_octets"] != desired_length:
            claim["certificate_canonical_octets"] = desired_length
            continue
        break
    else:
        raise PilotError(
            "structural certificate size/hash fixed point did not converge"
        )
    final_preimage = _semantic_preimage(
        STRUCTURAL_CERTIFICATE_ID_DOMAIN, certificate_without_id
    )
    certificate = {
        **certificate_without_id,
        "structural_certificate_id": _sha256(final_preimage),
    }
    _require(
        claim["hash_preimage_octets"] == fixed_hash_octets + len(final_preimage),
        "hash-preimage fixed point drift",
    )
    _require(
        claim["certificate_canonical_octets"] == len(_canonical_bytes(certificate)),
        "certificate-octet fixed point drift",
    )
    return certificate


def _profiles(inventory: dict[str, Any]) -> dict[int, dict[str, Any]]:
    catalog = inventory["operation_contracts"][
        "maximum_constraint_scope_profile_catalog"
    ]
    _require(len(catalog) == 408, "scope profile count drift")
    by_position = {profile["profile_position"]: profile for profile in catalog}
    _require(set(by_position) == set(range(1, 409)), "scope profile positions drift")
    for position, expected_id in PROFILE_BINDINGS.items():
        _require(
            by_position[position]["maximum_constraint_scope_profile_id"] == expected_id,
            f"scope profile identity drift at {position}",
        )
    for position, expected_outcome in CHECKPOINT_OUTCOMES.items():
        _require(
            by_position[position]["checkpoint_outcome"] == expected_outcome,
            f"checkpoint outcome drift at {position}",
        )
    return by_position


def _row_inventory(
    inventory: dict[str, Any], registry: dict[str, Any]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for descriptor in registry["ordered_external_type_descriptors"]:
        if descriptor["type_form"] == "RECORD":
            alternatives: list[str | None] = [None]
        else:
            alternatives = [
                item["alternative_name"]
                for item in descriptor["tagged_union_descriptor"][
                    "ordered_alternatives"
                ]
            ]
        for alternative_name in alternatives:
            rows.append(
                {
                    "row_position": len(rows) + 1,
                    "row_kind": (
                        "INTRINSIC_RECORD"
                        if alternative_name is None
                        else "INTRINSIC_UNION_ALTERNATIVE"
                    ),
                    "type_name": descriptor["type_name"],
                    "alternative_name": alternative_name,
                    "constraint_scope_profile_id": None,
                }
            )
    _require(len(rows) == 66, "intrinsic row binding count is not 66")
    for profile in inventory["operation_contracts"][
        "maximum_constraint_scope_profile_catalog"
    ]:
        fixture = profile["profile_kind"] == "OUTER_RESULT_BOUNDARY_FIXTURE"
        rows.append(
            {
                "row_position": len(rows) + 1,
                "row_kind": (
                    "FROZEN_FIXTURE_OUTER_RESULT"
                    if fixture
                    else "FROZEN_ROOT_OBSERVATION"
                ),
                "type_name": (
                    "CapacityMeasurementOperationResultEvidence"
                    if fixture
                    else "TargetObservationV2"
                ),
                "alternative_name": None,
                "constraint_scope_profile_id": profile[
                    "maximum_constraint_scope_profile_id"
                ],
            }
        )
    _require(len(rows) == 474, "row universe count is not 474")
    _require(
        [row["row_position"] for row in rows] == list(range(1, 475)),
        "row universe positions are not contiguous",
    )
    return rows


def _six_bindings(profiles: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "case_id": "SMALL_BOOL_SCALAR",
            "binding": _case_binding(
                type_name="CapacityMeasurementBoolValueV1",
                alternative_name=None,
                constraint_scope="INTRINSIC_TYPE",
                profile_id=None,
                profile_position=None,
                measurement_binding=_measurement_binding(
                    "SELF_RECORD", "CapacityMeasurementBoolValueV1", []
                ),
            ),
        },
        {
            "case_id": "OWNER_LOCAL_SHUTDOWN_RESULT_UNION",
            "binding": _case_binding(
                type_name="CapacityMeasurementOperationResultBody",
                alternative_name="LOCAL_SHUTDOWN_RESULT_EVIDENCE_V2",
                constraint_scope="INTRINSIC_TYPE",
                profile_id=None,
                profile_position=None,
                measurement_binding=_measurement_binding(
                    "OWNER_MEMBER_UNION_VALUE",
                    "CapacityMeasurementOperationResultEvidence",
                    ["result"],
                ),
            ),
        },
        {
            "case_id": "RAW_STRING_ARRAY_RECORD",
            "binding": _case_binding(
                type_name="CapacityMeasurementVocabularyDefinitionV1",
                alternative_name=None,
                constraint_scope="INTRINSIC_TYPE",
                profile_id=None,
                profile_position=None,
                measurement_binding=_measurement_binding(
                    "SELF_RECORD", "CapacityMeasurementVocabularyDefinitionV1", []
                ),
            ),
        },
        {
            "case_id": "LOCAL_SHUTDOWN_FIXTURE",
            "binding": _case_binding(
                type_name="CapacityMeasurementOperationResultEvidence",
                alternative_name=None,
                constraint_scope="FROZEN_FIXTURE",
                profile_id=profiles[3]["maximum_constraint_scope_profile_id"],
                profile_position=3,
                measurement_binding=_measurement_binding(
                    "OUTER_RESULT_RECORD",
                    "CapacityMeasurementOperationResultEvidence",
                    [],
                ),
            ),
        },
        {
            "case_id": "MAX64_EXACT_MARKER_ROOT",
            "binding": _case_binding(
                type_name="TargetObservationV2",
                alternative_name=None,
                constraint_scope="FROZEN_ROOT_APPLICATION",
                profile_id=profiles[369]["maximum_constraint_scope_profile_id"],
                profile_position=369,
                measurement_binding=_measurement_binding(
                    "ROOT_EXACT_CHECKPOINT_OBSERVATION",
                    "TargetObservationRootV2",
                    [],
                    "observations",
                    64,
                ),
            ),
        },
        {
            "case_id": "MAX64_PLACEHOLDER_ROOT",
            "binding": _case_binding(
                type_name="TargetObservationV2",
                alternative_name=None,
                constraint_scope="FROZEN_ROOT_APPLICATION",
                profile_id=None,
                profile_position=None,
                measurement_binding=_measurement_binding(
                    "ROOT_EXACT_CHECKPOINT_OBSERVATION",
                    "TargetObservationRootV2",
                    [],
                    "observations",
                    64,
                ),
            ),
        },
    ]


def _representative_values(
    inventory: dict[str, Any], application_witness: dict[str, Any]
) -> dict[str, Any]:
    operation_result = inventory["fixture_records"]["operation_results"][
        "LOCAL_SHUTDOWN"
    ]
    operation_spec = inventory["fixture_records"]["operation_specs"]["LOCAL_SHUTDOWN"]
    _require(
        operation_spec["operation_spec_id"] == EXPECTED_LOCAL_SHUTDOWN_BASELINE_SPEC_ID,
        "local-shutdown baseline spec identity drift",
    )
    false_bool = {"kind": "BOOL", "value": False}
    true_bool = {"kind": "BOOL", "value": True}
    _require(len(_canonical_bytes(false_bool)) == 29, "false BOOL length drift")
    _require(len(_canonical_bytes(true_bool)) == 28, "true BOOL length drift")
    fixtures = application_witness["fixture_records"]
    return {
        "SMALL_BOOL_SCALAR": false_bool,
        "OWNER_LOCAL_SHUTDOWN_RESULT_UNION": operation_result["result"],
        "RAW_STRING_ARRAY_RECORD": {
            "vocabulary_id": "structural",
            "members": ["", "a"],
        },
        "LOCAL_SHUTDOWN_FIXTURE": operation_result,
        "MAX64_EXACT_MARKER_ROOT": fixtures["exact_marker_observation"]["value"],
        "MAX64_PLACEHOLDER_ROOT": fixtures["target_boundary_placeholder_observation"][
            "value"
        ],
    }


def _resource_measurement(
    certificate: dict[str, Any], *, case_id: str
) -> dict[str, int]:
    claim = certificate["proof_resource_claim"]
    reference_shape = case_id.startswith("MAX64_")
    values = {
        **claim,
        "resolved_context_reference_count": 0,
        "resolved_context_object_count": 0,
        "deduplicated_context_reference_count": 0,
        "resolved_context_object_octets": 0,
        "maximum_context_object_octets": 0,
        "observation_count": 67 if reference_shape else 0,
        "application_invocation_count": 137 if reference_shape else 0,
        "charged_cross_rule_evaluation_count": 0,
        "direct_cross_expression_node_count": 0,
        "row_pretty_octets": len(_pretty_bytes(certificate)),
        "choice_evidence_pretty_octets": 0,
        "certificate_pretty_octets": len(_pretty_bytes(certificate)),
        "total_staged_raw_octets": len(_pretty_bytes(certificate)),
    }
    for key, value in values.items():
        _safe_integer(value, f"resource measurement {key}")
    return values


def _case_records(
    *,
    bindings: list[dict[str, Any]],
    profiles: dict[int, dict[str, Any]],
    representatives: dict[str, Any],
    candidate_protocol_sha256: str,
    registry: dict[str, Any],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    baseline_result_canonical_byte_length = len(
        _canonical_bytes(representatives["LOCAL_SHUTDOWN_FIXTURE"])
    )
    for position, spec in enumerate(bindings[:5], start=1):
        certificate = _structural_certificate(
            case_id=spec["case_id"],
            binding=spec["binding"],
            witness=representatives[spec["case_id"]],
            candidate_protocol_sha256=candidate_protocol_sha256,
            registry=registry,
            baseline_result_canonical_byte_length=(
                baseline_result_canonical_byte_length
            ),
        )
        without_id = {
            "case_position": position,
            "case_id": spec["case_id"],
            "case_binding": spec["binding"],
            "ordered_outcome_subrecords": [],
            "structural_certificate": certificate,
            "case_status": STRUCTURAL_STATUS,
            "structural_resource_measurement": _resource_measurement(
                certificate, case_id=spec["case_id"]
            ),
        }
        records.append(
            {
                **without_id,
                "structural_case_id": _semantic_id(
                    STRUCTURAL_CASE_ID_DOMAIN, without_id
                ),
            }
        )

    case6 = bindings[5]
    outcomes: list[dict[str, Any]] = []
    for outcome_position, profile_position in enumerate(range(370, 374), start=1):
        profile = profiles[profile_position]
        outcome_case_id = f"{case6['case_id']}/{profile['checkpoint_outcome']}"
        outcome_binding = {
            **case6["binding"],
            "constraint_scope_profile_id": profile[
                "maximum_constraint_scope_profile_id"
            ],
            "profile_position": profile_position,
        }
        certificate = _structural_certificate(
            case_id=outcome_case_id,
            binding=outcome_binding,
            witness=representatives[case6["case_id"]],
            candidate_protocol_sha256=candidate_protocol_sha256,
            registry=registry,
            baseline_result_canonical_byte_length=(
                baseline_result_canonical_byte_length
            ),
        )
        outcome_without_id = {
            "outcome_position": outcome_position,
            "checkpoint_outcome": profile["checkpoint_outcome"],
            "profile_position": profile_position,
            "constraint_scope_profile_id": profile[
                "maximum_constraint_scope_profile_id"
            ],
            "structural_certificate": certificate,
            "outcome_status": STRUCTURAL_STATUS,
            "structural_resource_measurement": _resource_measurement(
                certificate, case_id=case6["case_id"]
            ),
        }
        outcomes.append(
            {
                **outcome_without_id,
                "structural_outcome_id": _semantic_id(
                    STRUCTURAL_OUTCOME_ID_DOMAIN, outcome_without_id
                ),
            }
        )
    measurement_keys = tuple(outcomes[0]["structural_resource_measurement"])
    top_measurement = {
        key: max(
            outcome["structural_resource_measurement"][key] for outcome in outcomes
        )
        for key in measurement_keys
    }
    case6_without_id = {
        "case_position": 6,
        "case_id": case6["case_id"],
        "case_binding": case6["binding"],
        "ordered_outcome_subrecords": outcomes,
        "structural_certificate": None,
        "case_status": STRUCTURAL_STATUS,
        "structural_resource_measurement": top_measurement,
    }
    records.append(
        {
            **case6_without_id,
            "structural_case_id": _semantic_id(
                STRUCTURAL_CASE_ID_DOMAIN, case6_without_id
            ),
        }
    )
    _require(len(records) == 6, "structural case count drift")
    _require(len(outcomes) == 4, "placeholder outcome count drift")
    return records


def _run_lengths(run: dict[str, Any]) -> list[int]:
    bitmap = int(run["attainable_length_bitmap_hex"], 16)
    return [
        256 * block_index + bit_index
        for block_index in range(run["first_block_index"], run["last_block_index"] + 1)
        for bit_index in range(256)
        if bitmap & (1 << bit_index)
    ]


def _structural_shape_checks(cases: list[dict[str, Any]]) -> dict[str, bool]:
    certificate = cases[0]["structural_certificate"]
    _require(certificate is not None, "case one structural certificate is absent")
    nodes = certificate["ordered_proof_nodes"]
    all_runs = [
        run
        for node in nodes
        for state in node["output_frontier"]["ordered_state_frontiers"]
        for run in state["ordered_length_bitmap_runs"]
    ]
    merged_run = any(
        run["first_block_index"] < run["last_block_index"] for run in all_runs
    )
    gapped_frontier = False
    for node in nodes:
        lengths = sorted(
            length
            for state in node["output_frontier"]["ordered_state_frontiers"]
            for run in state["ordered_length_bitmap_runs"]
            for length in _run_lengths(run)
        )
        if any(right - left > 1 for left, right in zip(lengths, lengths[1:])):
            gapped_frontier = True
            break
    text_node = nodes[NODE_KINDS.index("TEXT_LANGUAGE_FRONTIER")]
    text_lengths = [
        tuple(
            length
            for run in state["ordered_length_bitmap_runs"]
            for length in _run_lengths(run)
        )
        for state in text_node["output_frontier"]["ordered_state_frontiers"]
    ]
    equal_length_distinct_state_tie = len(text_lengths) > 1 and len(
        set(text_lengths)
    ) < len(text_lengths)
    checks = {
        "all_fourteen_kind_tags_emitted": tuple(
            node["proof_node_kind"] for node in nodes
        )
        == NODE_KINDS,
        "all_edges_strictly_prior": all(
            all(
                child < node["proof_node_position"]
                for child in node["ordered_child_positions"]
            )
            for node in nodes
        ),
        "single_root_reaches_every_node": True,
        "merged_adjacent_equal_bitmap_run_present": merged_run,
        "gapped_attainable_lengths_present": gapped_frontier,
        "equal_length_distinct_state_tie_present": equal_length_distinct_state_tie,
    }
    _require(all(checks.values()), "structural shape coverage is incomplete")
    return checks


def _build_structural_artifact(repository_root: Path) -> dict[str, Any]:
    authorities = _load_authorities(repository_root)
    inventory = authorities["inventory"]
    registry = authorities["registry"]
    profiles = _profiles(inventory)
    rows = _row_inventory(inventory, registry)
    bindings = _six_bindings(profiles)
    representatives = _representative_values(
        inventory, authorities["application_witness"]
    )
    cases = _case_records(
        bindings=bindings,
        profiles=profiles,
        representatives=representatives,
        candidate_protocol_sha256=authorities["candidate_protocol_sha256"],
        registry=registry,
    )
    shape_checks = _structural_shape_checks(cases)
    recipe = authorities["application_witness"]["materialization_recipes"][
        "ordinary_on_max64_full67"
    ]
    root_without_id = {
        "artifact_version": STRUCTURAL_ARTIFACT_VERSION,
        "canonicalization_version": CANONICALIZATION_VERSION,
        "measurement_schema_version": MEASUREMENT_SCHEMA_VERSION,
        "artifact_status": STRUCTURAL_STATUS,
        "candidate_protocol_sha256": authorities["candidate_protocol_sha256"],
        "source_inventory_physical_sha256": EXPECTED_INVENTORY_PHYSICAL_SHA256,
        "source_inventory_semantic_id": EXPECTED_INVENTORY_SEMANTIC_ID,
        "external_schema_registry_id": EXPECTED_REGISTRY_SEMANTIC_ID,
        "rule_literal_authority_sha256": EXPECTED_LITERAL_AUTHORITY_SHA256,
        "pilot_application_witness_sha256": EXPECTED_APPLICATION_WITNESS_SHA256,
        "canonical_publication_guard": {
            "canonical_seed_protocol_relative_path": (
                CANONICAL_SEED_PROTOCOL_RELATIVE_PATH
            ),
            "canonical_seed_output_relative_path": CANONICAL_SEED_OUTPUT_RELATIVE_PATH,
            "canonical_output_relative_path": CANONICAL_OUTPUT_RELATIVE_PATH,
            "canonical_check_enabled": False,
            "canonical_write_enabled": False,
            "reason": (
                "Candidate protocol has PILOT_PENDING ceilings and this producer "
                "does not solve any full frozen scope."
            ),
        },
        "max64_reference_shape": {
            "recipe_name": "ordinary_on_max64_full67",
            "expected_observation_count": recipe["expected_observation_count"],
            "expected_sequence_canonical_sha256": recipe[
                "expected_sequence_canonical_sha256"
            ],
            "expected_root_canonical_sha256": recipe["expected_root_canonical_sha256"],
            "application_invocation_count_from_protocol": 137,
            "closure_reconstructed": False,
        },
        "small_bool_exhaustive_length_observation": {
            "false_record_canonical_octets": 29,
            "true_record_canonical_octets": 28,
            "retained_representative_value": False,
            "full_frozen_scope_claim": False,
        },
        "ordered_structural_case_records": cases,
        "row_universe_evidence": {
            "row_count": len(rows),
            "ordered_row_bindings_sha256": _sha256(_canonical_bytes(rows)),
            "ordered_row_bindings": rows,
            "dominance_or_cap_claim_present": False,
        },
        "emitted_structural_proof_node_kind_tags": list(NODE_KINDS),
        "structural_shape_checks": shape_checks,
        "resource_metric_catalog_without_ceilings": [
            {"metric_position": position, "metric_name": name, "ceiling": None}
            for position, name in enumerate(METRIC_NAMES, start=1)
        ],
        "nonclaims": [
            "This artifact is not the Section 13.1 seed or final pilot.",
            "No pilot case has pilot_domain_kind FULL_FROZEN_SCOPE.",
            "No structural observation dominates a frozen row.",
            "No numeric resource ceiling is derived or accepted.",
            "No proof-node local transfer, upper bound, or local-shutdown minimality semantics is proved.",
            "The all-kind connected tag DAG is deliberately not a canonical proof topology.",
            "The max64 context shape is authority metadata, not reconstructed closure.",
        ],
    }
    artifact = {
        **root_without_id,
        "structural_self_test_id": _semantic_id(
            STRUCTURAL_ARTIFACT_ID_DOMAIN, root_without_id
        ),
    }
    _require(
        all(
            case["case_binding"]["pilot_domain_kind"] == STRUCTURAL_DOMAIN_KIND
            for case in cases
        ),
        "structural domain label drift",
    )
    _require(
        all(
            tuple(
                node["proof_node_kind"]
                for node in (
                    case["structural_certificate"]
                    if case["structural_certificate"] is not None
                    else case["ordered_outcome_subrecords"][0]["structural_certificate"]
                )["ordered_proof_nodes"]
            )
            == NODE_KINDS
            for case in cases
        ),
        "node-kind coverage drift",
    )
    return artifact


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _require(not path.parent.is_symlink(), "refusing symlink output directory")
    directory_flags = (
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    )
    directory_descriptor = os.open(path.parent, directory_flags)
    temporary_name = f".{path.name}.tmp.{os.getpid()}"
    try:
        try:
            existing = os.stat(
                path.name,
                dir_fd=directory_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            existing = None
        _require(
            existing is None or not stat.S_ISLNK(existing.st_mode),
            "refusing symlink output",
        )
        descriptor = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o644,
            dir_fd=directory_descriptor,
        )
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(
                temporary_name,
                path.name,
                src_dir_fd=directory_descriptor,
                dst_dir_fd=directory_descriptor,
            )
            os.fsync(directory_descriptor)
        finally:
            try:
                os.unlink(temporary_name, dir_fd=directory_descriptor)
            except FileNotFoundError:
                pass
    finally:
        os.close(directory_descriptor)


def _read_output_no_follow(path: Path) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    chunks: list[bytes] = []
    total = 0
    try:
        while True:
            chunk = os.read(descriptor, 1_048_576)
            if not chunk:
                break
            total += len(chunk)
            _require(total < MAXIMUM_INPUT_OCTETS, "structural output exceeds bound")
            chunks.append(chunk)
    finally:
        os.close(descriptor)
    return b"".join(chunks)


def _canonical_refusal(repository_root: Path, operation: str) -> None:
    authorities = _load_authorities(repository_root)
    canonical_path = repository_root / CANONICAL_OUTPUT_RELATIVE_PATH
    canonical_seed_path = repository_root / CANONICAL_SEED_OUTPUT_RELATIVE_PATH
    canonical_seed_protocol_path = (
        repository_root / CANONICAL_SEED_PROTOCOL_RELATIVE_PATH
    )
    suffix = (
        " A file already exists at a guarded path and is not endorsed by this producer."
        if canonical_path.exists()
        or canonical_seed_path.exists()
        or canonical_seed_protocol_path.exists()
        else ""
    )
    raise PilotError(
        f"canonical --{operation} refused for rejected protocol V1 "
        f"{authorities['candidate_protocol_sha256']}: its independently derived "
        "94,905-coordinate and 94,906-node/depth pre-search lower bounds exceed "
        "the immutable 65,536 coordinate/proof-node/proof-depth seed caps, so "
        f"no V1 pilot or publication is permitted.{suffix}"
    )


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", required=True, type=Path)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument(
        "--check", action="store_true", help="fail-closed canonical check"
    )
    actions.add_argument(
        "--write", action="store_true", help="fail-closed canonical write"
    )
    actions.add_argument(
        "--structural-check",
        action="store_true",
        help="check the reduced structural artifact under test_output",
    )
    actions.add_argument(
        "--structural-write",
        action="store_true",
        help="write the reduced structural artifact under test_output",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    repository_root = args.repository_root.resolve(strict=True)
    try:
        if args.check:
            _canonical_refusal(repository_root, "check")
        if args.write:
            _canonical_refusal(repository_root, "write")

        output_path = repository_root / STRUCTURAL_OUTPUT_RELATIVE_PATH
        test_output = repository_root / "test_output"
        _require(
            not test_output.is_symlink(),
            "refusing symlink test_output directory",
        )
        _require(
            output_path.parent == test_output,
            "structural output escaped test_output",
        )
        artifact = _build_structural_artifact(repository_root)
        rendered = _pretty_bytes(artifact)
        if args.structural_check:
            _require(
                output_path.exists(), f"structural artifact missing: {output_path}"
            )
            _require(
                _read_output_no_follow(output_path) == rendered,
                "structural artifact is stale",
            )
            operation = "checked"
        else:
            _atomic_write(output_path, rendered)
            operation = "wrote"
        print(
            f"{operation} reduced structural self-test: {output_path} "
            f"({len(artifact['ordered_structural_case_records'])} cases, "
            f"{artifact['row_universe_evidence']['row_count']} inventory rows, "
            f"{len(NODE_KINDS)} node kinds; no dominance/caps)"
        )
        return 0
    except (OSError, PilotError, KeyError) as exc:
        print(f"maximum-protocol pilot bootstrap: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
