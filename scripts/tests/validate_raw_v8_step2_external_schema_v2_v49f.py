#!/usr/bin/env python3
"""Independently validate the Raw-V8 Step-2 V3 inventory gate.

This validator is intentionally standard-library-only.  It does not import the
inventory generator, production ``riskyieldmm`` modules, dataclasses, or
production constants.  The frozen correction and accepted standalone
structural registry are physical inputs; the 408 maximum-constraint-scope
profiles are rebuilt here from the frozen authorities and compared exactly.

Constructive maximum witnesses, production adapters, and the final Step-2 GO
decision remain outside this isolated inventory gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any, Final

CANONICALIZATION_VERSION: Final = "riskyieldmm_canonical_json_v1"
MEASUREMENT_SCHEMA_VERSION: Final = "riskyieldmm_physical_transport_a2m_raw_v49f_v8"
INVENTORY_SCHEMA_VERSION: Final = "riskyieldmm.raw_v8_step2_inventory.v3"
COMPONENT_STATUS: Final = "V3_INVENTORY_ONLY_MAXIMA_PENDING"

INVENTORY_RELATIVE_PATH: Final = "tests/raw_v8_step2_inventory_v49f.json"
STRUCTURAL_REGISTRY_RELATIVE_PATH: Final = (
    "scripts/tests/raw_v8_step2_external_schema_v2_structural_registry_v49f.json"
)
STRUCTURAL_REGISTRY_OCTETS: Final = 1_469_663
STRUCTURAL_REGISTRY_SHA256: Final = (
    "9160297ff316c5931737c92f8b359f0a1e2ec22f0aa996ef3b09cf830dc96bf3"
)
STRUCTURAL_REGISTRY_ID: Final = (
    "5dc95a3e99c5646e912b6a7e9c3970cf2489d560ea890b0a19d38af4c51c2140"
)
STRUCTURAL_REGISTRY_DOMAIN: Final = (
    "RiskYieldMMA2MStep2ExternalSchemaRegistryV2V4_9F_RawV8"
)

INVENTORY_EXCLUSIVE_OCTET_LIMIT: Final = 16_777_216
SOURCE_EXCLUSIVE_OCTET_LIMIT: Final = 16_777_216
MAXIMUM_JSON_NESTING_DEPTH: Final = 16
SAFE_INTEGER_MAXIMUM: Final = 9_007_199_254_740_991
SHA256_HEX_LENGTH: Final = 64

CORRECTION_OCTETS: Final = 217_135
CORRECTION_SHA256: Final = (
    "29ec141e53adeb1c0afd51f205f5b57eb784b8859b5ba40958299abd1b713b55"
)

NORMATIVE_DOCUMENTS: Final = (
    (
        "PARENT_MARKER_OPERATION_TARGET_PROTOCOL",
        "docs/research/"
        "v4_9f_a2_marker_operation_target_v8_protocol_freeze_2026-07-22.md",
        212_471,
        "15b42d32afe5fdff74890b2c18f735ff761244548729142c4ff2b1034fee2388",
    ),
    (
        "STEP2_V2_CONTRACT_FREEZE",
        "docs/research/v4_9f_a2_raw_v8_step2_v2_contract_freeze_2026-07-26.md",
        34_591,
        "355548cb3ef323ab45b0289be9891ab578b75d0147639ab37c9f3e5ff251aa1c",
    ),
    (
        "STEP2_EXTERNAL_SCHEMA_V2_CORRECTION",
        "docs/research/"
        "v4_9f_a2_raw_v8_step2_external_schema_v2_correction_2026-07-28.md",
        CORRECTION_OCTETS,
        CORRECTION_SHA256,
    ),
    (
        "STEP3_TARGET_AND_LIFECYCLE_CORRECTION",
        "docs/research/"
        "v4_9f_a2_raw_v8_step3_target_and_lifecycle_correction_2026-07-26.md",
        435_478,
        "635952095b0b20089d5ec2c13104255ebeeff11535c8f94131a4983a1a9fec0a",
    ),
)

INVENTORY_ROOT_KEYS: Final = frozenset(
    {
        "schema_version",
        "normative_document_inputs",
        "invariants",
        "target_field_registry",
        "operation_counter_schema",
        "marker_contract",
        "checkpoint_selector_catalog",
        "ingress_logical_oracle_profile_catalog",
        "external_schema_registry_v2",
        "operation_contracts",
        "fixture_records",
        "inventory_sha256",
    }
)
INVENTORY_LOGICAL_MEMBER_ORDER: Final = (
    "schema_version",
    "normative_document_inputs",
    "invariants",
    "target_field_registry",
    "operation_counter_schema",
    "marker_contract",
    "checkpoint_selector_catalog",
    "ingress_logical_oracle_profile_catalog",
    "external_schema_registry_v2",
    "operation_contracts",
    "fixture_records",
    "inventory_sha256",
)
NORMATIVE_DOCUMENT_KEYS: Final = frozenset(
    {
        "document_role",
        "repository_relative_path",
        "raw_octet_count",
        "raw_sha256",
    }
)

STRUCTURAL_REGISTRY_KEYS: Final = frozenset(
    {
        "canonicalization_version",
        "measurement_schema_version",
        "record_domain",
        "external_schema_profile",
        "unicode_source_catalog",
        "identifier_profile_catalog",
        "ascii_dfa_catalog",
        "text_language_catalog",
        "value_schema_catalog",
        "external_type_descriptor_count",
        "ordered_external_type_descriptors",
        "cross_field_rule_descriptor_count",
        "ordered_cross_field_rule_descriptors",
        "fixed_position_resolver_profile_catalog",
        "rule_application_descriptor_count",
        "ordered_rule_application_descriptors",
        "schema_graph_node_count",
        "ordered_schema_graph_node_names",
        "external_schema_registry_id",
    }
)
STRUCTURAL_REGISTRY_IDENTITY_PAYLOAD_MEMBERS: Final = (
    "external_schema_profile",
    "unicode_source_catalog",
    "identifier_profile_catalog",
    "ascii_dfa_catalog",
    "text_language_catalog",
    "value_schema_catalog",
    "external_type_descriptor_count",
    "ordered_external_type_descriptors",
    "cross_field_rule_descriptor_count",
    "ordered_cross_field_rule_descriptors",
    "fixed_position_resolver_profile_catalog",
    "rule_application_descriptor_count",
    "ordered_rule_application_descriptors",
    "schema_graph_node_count",
    "ordered_schema_graph_node_names",
)

EXPECTED_SEMANTIC_IDS: Final = {
    "target_field_registry_id": (
        "ae01f3a8e53163eefdc77bb4a863710dc851aec22738719639a3c21fe683a618"
    ),
    "operation_counter_schema_id": (
        "5181eb89788d511ffeb2ccc65264b81e9e0d3ae977043820524f8b08dfa58fc3"
    ),
    "marker_contract_id": (
        "1e529cc6ced2f3a67cafca3ec2af5146322c73b89f9cd4385cbd7b72949132b4"
    ),
    "logical_oracle_profile_id": (
        "a85c176a642671a25070d15a4473f3b2c581dbcb6596bd0bb180a447020b1ca0"
    ),
    "external_schema_registry_id": STRUCTURAL_REGISTRY_ID,
}

OPERATION_KINDS: Final = (
    "ACK_DEADLINE_EXPIRY",
    "INGRESS",
    "LOCAL_SHUTDOWN",
    "SUBSCRIPTION_DISPATCH",
)
OPERATION_SPEC_IDS: Final = {
    "ACK_DEADLINE_EXPIRY": (
        "92db29b63b667b0b9734be8d164142bb7446fd58dcd7692de0b1f30a01a838b8"
    ),
    "INGRESS": ("94bee9905327c32ff48990db0af1f9f8c3e6748d4e0fb8900989751e696f7f75"),
    "LOCAL_SHUTDOWN": (
        "f88cf223f28a146b08b5ffbb3b5ce419fb7ce473563edb27900983d6583a2d21"
    ),
    "SUBSCRIPTION_DISPATCH": (
        "8879605af643230fefff6984f5d5682241c3e20ce0a2710ecfd8959d5addc9bd"
    ),
}

# Exact catalog order is semantic.  Pinning each selector semantic identity
# independently pins every nested entry, marker, occurrence, and operation.
SELECTOR_CATALOG: Final = (
    (
        "SUBSCRIPTION_COVERAGE",
        "SUBSCRIPTION_DISPATCH",
        4,
        "01966c701a9ae97972acd0e4d74af4f01a85ec2fe544799e28028c0c4f310f23",
    ),
    (
        "LOCAL_SHUTDOWN_COVERAGE",
        "LOCAL_SHUTDOWN",
        5,
        "194a464d62fcbba442739fbe19639e5381a10cba5b5d5ae764bbe5cd32c73843",
    ),
    (
        "ACK_EMPTY",
        "ACK_DEADLINE_EXPIRY",
        0,
        "688c8d4807d1a48fea80b872345f5d2b05b36c795ff54f400491f86d8004b503",
    ),
    (
        "INGRESS_MAX64_PARSER_UNITS",
        "INGRESS",
        64,
        "6cc3c8c09a08675ecbddddb4131dabbdd24ea3e879bc467fe56e3089834ff2f9",
    ),
    (
        "INGRESS_EMPTY",
        "INGRESS",
        0,
        "97a8c0b20264cf28d92c319e9ec4906543779fcbada59ebf0146175cef106956",
    ),
    (
        "ACK_COVERAGE",
        "ACK_DEADLINE_EXPIRY",
        3,
        "cff4b7f243fa454d18e8085577c77191488517b0c07ef196622edc04f7b99bea",
    ),
    (
        "INGRESS_COVERAGE",
        "INGRESS",
        4,
        "d2c892bc86149c82fb936eeacd3526aa814288e47a6eba20c9697203178ba731",
    ),
    (
        "LOCAL_SHUTDOWN_EMPTY",
        "LOCAL_SHUTDOWN",
        0,
        "f0380277d46bcdeac7c81dc07e402b6b61e2e8e5ce1bab84b54b515aa7c25b6a",
    ),
    (
        "SUBSCRIPTION_EMPTY",
        "SUBSCRIPTION_DISPATCH",
        0,
        "fc886e7b6266bef85e20c93cd0b873a8f5e15aa6e270922ceca45682a7e1f7b5",
    ),
)

MAXIMUM_SCOPE_PROFILE_DOMAIN: Final = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumConstraintScopeProfileV1V4_9F_RawV8"
)
MAXIMUM_SCOPE_PROFILE_COUNT: Final = 408
MAXIMUM_RESULT_SCOPE_PROFILE_COUNT: Final = 4
MAXIMUM_NON_CHECKPOINT_SCOPE_PROFILE_COUNT: Final = 4
MAXIMUM_CHECKPOINT_SCOPE_PROFILE_COUNT: Final = 400
MAXIMUM_CHECKPOINT_OUTCOMES: Final = (
    "EXACT_MARKER",
    "ARTIFACT_BOUND_EXCEEDED",
    "OBSERVER_INTERNAL_ERROR",
    "SOURCE_CLOCK_UNAVAILABLE",
    "TARGET_BOUNDARY_NOT_REACHED",
)
MAXIMUM_CHECKPOINT_OUTCOME_BINDINGS: Final = {
    "EXACT_MARKER": ("EXACT_MARKER", None, None),
    "ARTIFACT_BOUND_EXCEEDED": (
        "UNAVAILABLE_MARKER_OBSERVER_FAILURE",
        "ARTIFACT_BOUND_EXCEEDED",
        "CHECKPOINT_PLACEHOLDER_ARTIFACT_BOUND_EXCEEDED",
    ),
    "OBSERVER_INTERNAL_ERROR": (
        "UNAVAILABLE_MARKER_OBSERVER_FAILURE",
        "OBSERVER_INTERNAL_ERROR",
        "CHECKPOINT_PLACEHOLDER_OBSERVER_INTERNAL_ERROR",
    ),
    "SOURCE_CLOCK_UNAVAILABLE": (
        "UNAVAILABLE_MARKER_OBSERVER_FAILURE",
        "SOURCE_CLOCK_UNAVAILABLE",
        "CHECKPOINT_PLACEHOLDER_SOURCE_CLOCK_UNAVAILABLE",
    ),
    "TARGET_BOUNDARY_NOT_REACHED": (
        "UNAVAILABLE_TARGET_BOUNDARY_NOT_REACHED",
        "TARGET_BOUNDARY_NOT_REACHED",
        "CHECKPOINT_PLACEHOLDER_TARGET_BOUNDARY_NOT_REACHED",
    ),
}

PROFILE_KEYS: Final = frozenset(
    {
        "profile_position",
        "profile_kind",
        "constraint_scope",
        "measured_type_name",
        "operation_kind",
        "ordered_source_authority_pointers",
        "ordered_source_authority_ids",
        "selector_catalog_position",
        "selector_catalog_name",
        "checkpoint_selector_id",
        "checkpoint_selector_entry_id",
        "expected_checkpoint_marker_kind",
        "expected_occurrence_index_within_kind",
        "selector_position",
        "checkpoint_outcome",
        "checkpoint_binding_status",
        "checkpoint_binding_unavailable_reason",
        "checkpoint_field_unavailable_reason",
        "ordered_admissible_root_families",
        "application_schedule_formula",
        "maximum_constraint_scope_profile_id",
    }
)
PROFILE_ID_PAYLOAD_MEMBERS: Final = (
    "profile_position",
    "profile_kind",
    "constraint_scope",
    "measured_type_name",
    "operation_kind",
    "ordered_source_authority_pointers",
    "ordered_source_authority_ids",
    "selector_catalog_position",
    "selector_catalog_name",
    "checkpoint_selector_id",
    "checkpoint_selector_entry_id",
    "expected_checkpoint_marker_kind",
    "expected_occurrence_index_within_kind",
    "selector_position",
    "checkpoint_outcome",
    "checkpoint_binding_status",
    "checkpoint_binding_unavailable_reason",
    "checkpoint_field_unavailable_reason",
    "ordered_admissible_root_families",
    "application_schedule_formula",
)
ROOT_FAMILY_KEYS: Final = frozenset(
    {
        "root_family_kind",
        "ordered_instrumentation_mode_attempt_presence_pairs",
        "selector_catalog_position",
        "selector_catalog_name",
        "checkpoint_selector_id",
        "selector_length",
        "observation_count",
        "role_sequence_formula",
        "ordered_measured_observation_roles",
        "selector_present",
    }
)

OPERATION_CONTRACT_KEYS: Final = frozenset(
    {
        "checkpoint_binding_statuses",
        "checkpoint_context_to_field_reason",
        "checkpoint_placeholder_context_predicate_by_field_reason",
        "checkpoint_placeholder_discharge_rule",
        "clock_span_members",
        "current_result_type_by_operation",
        "current_spec_type_by_operation",
        "local_shutdown_scalar_limit_domains",
        "local_shutdown_intrinsic_limit_relations",
        "local_shutdown_operational_result_relations",
        "maximum_constraint_scope_profile_catalog",
        "operation_result_canonical_byte_ceiling",
        "operation_result_variants",
        "operation_spec_variants",
        "record_types",
        "registry_definition_type_members",
        "removed_v1_tags",
        "semantic_id_preimage_members",
        "semantic_preimage_structural_scan",
        "source_error_detail_fixture",
        "standalone_envelope_prefix_members",
        "target_observation_context_v2_payload_members",
        "target_observation_root_v2_payload_members",
        "target_observation_v2_payload_members",
        "value_union_variants",
    }
)
FIXTURE_RECORD_KEYS: Final = frozenset(
    {
        "operation_specs",
        "operation_declaration",
        "dispatch_window_evidence",
        "due_decision_clock_evidence",
        "operation_results",
        "target_observation_v2_fixtures",
        "counter_snapshot",
        "local_shutdown_boundary_spec",
        "one_field_mutation_metadata",
    }
)

INVARIANT_KEYS: Final = frozenset(
    {
        "canonicalization_version",
        "checkpoint_placeholder_reason_amendment",
        "constructive_maxima_external_artifact_contract",
        "context_semantics",
        "counts",
        "exact_semantic_ids",
        "forbidden_downstream_identity_fields",
        "frozen_byte_maxima",
        "generated_boundary_proofs",
        "inventory_schema_version",
        "maximum_constraint_scope_profile_ids_canonical_json_sha256",
        "measurement_schema_version",
        "monotone_counter_zero_based_positions",
        "normative_document_sha256_by_role",
        "operation_counter_schema_id",
        "protocol_sha256",
        "semantic_preimage_node_count_limit",
        "target_field_ids_canonical_json_sha256",
        "target_field_layer_counts",
        "target_field_registry_canonical_json_bytes",
        "target_field_registry_id",
        "target_field_value_kind_counts",
        "v1_removal_assertions",
    }
)
LEGACY_HEURISTIC_KEYS: Final = frozenset(
    {
        "operation_result_bound_proof",
        "target_observation_v2_bound_proof",
        "per_operation_legal_value_maxima",
        "checkpoint_catalog_position_state_expected_coordinates",
        "checkpoint_catalog_position_state_witnessed_coordinates",
        "checkpoint_catalog_position_state_witnesses",
        "selector_root_witnesses",
    }
)

LOCAL_SHUTDOWN_SCALAR_LIMIT_DOMAINS: Final = (
    ("maximum_terminal_ingress_batches", 1, SAFE_INTEGER_MAXIMUM),
    ("maximum_terminal_ingress_ciphertext_octets", 1, SAFE_INTEGER_MAXIMUM),
    ("maximum_terminal_ingress_plaintext_octets", 1, SAFE_INTEGER_MAXIMUM),
    ("maximum_terminal_socket_receive_calls", 1, SAFE_INTEGER_MAXIMUM),
    ("maximum_terminal_tls_records", 1, SAFE_INTEGER_MAXIMUM),
    ("maximum_terminal_tls_unwrap_iterations", 1, SAFE_INTEGER_MAXIMUM),
    ("maximum_terminal_zero_progress_iterations", 1, SAFE_INTEGER_MAXIMUM),
    ("maximum_terminal_ingress_parser_units", 1, 4_096),
    ("maximum_terminal_ingress_automatic_outputs", 1, 4_096),
    ("maximum_websocket_send_attempts", 1, 1_048_832),
    ("maximum_tls_control_send_attempts", 1, 256),
    ("maximum_peer_shutdown_polls", 2, 2),
)
LOCAL_SHUTDOWN_INTRINSIC_LIMIT_RELATIONS: Final = (
    "maximum_terminal_ingress_plaintext_octets<=16384*maximum_terminal_ingress_batches",
    "2*maximum_terminal_ingress_parser_units"
    "<=maximum_terminal_ingress_plaintext_octets",
    "maximum_terminal_tls_records<=maximum_terminal_ingress_batches",
    "maximum_terminal_ingress_automatic_outputs<=maximum_terminal_ingress_parser_units",
    "maximum_websocket_send_attempts"
    "<=256*(1+maximum_terminal_ingress_automatic_outputs)",
)
LOCAL_SHUTDOWN_OPERATIONAL_RESULT_RELATIONS: Final = (
    "result.terminal_outcome=spec.expected_terminal_outcome",
    "result.final_terminal_ingress_batch_count<=spec.maximum_terminal_ingress_batches",
    "result.final_terminal_ingress_ciphertext_octets"
    "<=spec.maximum_terminal_ingress_ciphertext_octets",
    "result.final_terminal_ingress_plaintext_octets"
    "<=spec.maximum_terminal_ingress_plaintext_octets",
    "result.final_terminal_socket_receive_call_count"
    "<=spec.maximum_terminal_socket_receive_calls",
    "result.final_terminal_tls_record_count<=spec.maximum_terminal_tls_records",
    "result.final_terminal_tls_unwrap_iteration_count"
    "<=spec.maximum_terminal_tls_unwrap_iterations",
    "result.final_terminal_zero_progress_iteration_count"
    "<=spec.maximum_terminal_zero_progress_iterations",
    "result.final_terminal_ingress_parser_unit_count"
    "<=spec.maximum_terminal_ingress_parser_units",
    "result.final_terminal_ingress_automatic_output_count"
    "<=spec.maximum_terminal_ingress_automatic_outputs",
    "result.final_websocket_send_attempt_count<=spec.maximum_websocket_send_attempts",
    "result.final_tls_control_send_attempt_count"
    "<=spec.maximum_tls_control_send_attempts",
    "result.final_peer_shutdown_poll_count<=spec.maximum_peer_shutdown_polls",
    "len(result.ordered_terminal_ingress_read_attempt_event_ids)"
    "<=spec.maximum_terminal_ingress_batches",
    "len(result.ordered_terminal_parser_transition_event_ids)"
    "<=spec.maximum_terminal_ingress_parser_units",
)


class InventoryValidationError(ValueError):
    """Raised when the V3 inventory differs from the frozen authority."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise InventoryValidationError(message)


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


def _semantic_id(domain: str, payload: dict[str, Any]) -> str:
    return _sha256(
        _canonical_bytes(
            {
                "canonicalization_version": CANONICALIZATION_VERSION,
                "domain": domain,
                "payload": payload,
                "schema_version": MEASUREMENT_SCHEMA_VERSION,
            }
        )
    )


def _is_sha256(value: Any) -> bool:
    return (
        type(value) is str
        and len(value) == SHA256_HEX_LENGTH
        and all(character in "0123456789abcdef" for character in value)
    )


def _exact_nonnegative_integer(value: Any, *, field: str) -> int:
    _require(
        type(value) is int and 0 <= value <= SAFE_INTEGER_MAXIMUM,
        f"{field} must be an exact non-negative safe integer",
    )
    return value


def _absolute_lexical_path(path: Path, *, base: Path | None = None) -> Path:
    """Return an absolute path without following or erasing symlink segments."""

    if not path.is_absolute():
        _require(base is not None, "relative path has no secure base")
        path = base / path
    _require(path.is_absolute(), "secure input path is not absolute")
    _require(
        all(part not in {"", ".", ".."} for part in path.parts[1:]),
        f"secure input path is not normalized: {path}",
    )
    return path


def _stat_signature(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_uid,
        value.st_gid,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _secure_bounded_read(
    path: Path,
    *,
    base: Path | None = None,
    maximum_octets: int,
    exclusive: bool,
) -> bytes:
    """Read one regular file through no-follow directory descriptors.

    Every path component is opened relative to its already-open parent using
    ``O_NOFOLLOW``.  File identity is checked before and after the bounded
    read and against the still-bound directory entry before acceptance.
    """

    _require(
        type(maximum_octets) is int and maximum_octets > 0,
        "secure read byte bound is invalid",
    )
    absolute = _absolute_lexical_path(path, base=base)
    hard_limit = maximum_octets - 1 if exclusive else maximum_octets
    directory_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    directory_flags |= getattr(os, "O_DIRECTORY", 0)
    directory_flags |= getattr(os, "O_NOFOLLOW", 0)
    file_flags = os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0)
    file_flags |= getattr(os, "O_NOFOLLOW", 0)

    directory_fd: int | None = None
    file_fd: int | None = None
    try:
        directory_fd = os.open("/", directory_flags)
        parts = absolute.parts[1:]
        _require(bool(parts), "secure input path names no file")
        for part in parts[:-1]:
            next_fd = os.open(
                part,
                directory_flags,
                dir_fd=directory_fd,
            )
            os.close(directory_fd)
            directory_fd = next_fd
        file_name = parts[-1]
        file_fd = os.open(file_name, file_flags, dir_fd=directory_fd)
        before = os.fstat(file_fd)
        _require(
            stat.S_ISREG(before.st_mode),
            f"secure input is not a regular file: {absolute}",
        )
        _require(
            before.st_size <= hard_limit,
            f"secure input exceeds its byte bound: {absolute}",
        )

        chunks: list[bytes] = []
        total = 0
        while True:
            remaining = hard_limit + 1 - total
            _require(remaining > 0, f"secure input exceeds its byte bound: {absolute}")
            chunk = os.read(file_fd, min(65_536, remaining))
            if not chunk:
                break
            total += len(chunk)
            _require(
                total <= hard_limit,
                f"secure input exceeds its byte bound: {absolute}",
            )
            chunks.append(chunk)

        after = os.fstat(file_fd)
        _require(
            _stat_signature(before) == _stat_signature(after),
            f"secure input changed during read: {absolute}",
        )
        bound_entry = os.stat(file_name, dir_fd=directory_fd, follow_symlinks=False)
        _require(
            not stat.S_ISLNK(bound_entry.st_mode)
            and _stat_signature(before) == _stat_signature(bound_entry),
            f"secure input identity changed during read: {absolute}",
        )
    except OSError as exc:
        raise InventoryValidationError(
            f"cannot securely read input without symlink traversal: {absolute}"
        ) from exc
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if directory_fd is not None:
            os.close(directory_fd)

    raw = b"".join(chunks)
    _require(
        len(raw) == before.st_size,
        f"secure input was truncated during read: {absolute}",
    )
    return raw


def _scan_json_structure(raw: bytes, *, maximum_depth: int) -> None:
    """Apply the bounded structural scan before UTF-8/JSON decoding."""

    _require(not raw.startswith(b"\xef\xbb\xbf"), "JSON BOM is forbidden")
    stack: list[int] = []
    closing = {ord("}"): ord("{"), ord("]"): ord("[")}
    in_string = False
    escaped = False
    for octet in raw:
        if in_string:
            if escaped:
                escaped = False
            elif octet == ord("\\"):
                escaped = True
            elif octet == ord('"'):
                in_string = False
            elif octet < 0x20:
                raise InventoryValidationError(
                    "JSON contains an unescaped control octet"
                )
            continue
        if octet == ord('"'):
            in_string = True
        elif octet in (ord("["), ord("{")):
            stack.append(octet)
            _require(
                len(stack) <= maximum_depth,
                "JSON nesting exceeds the frozen structural bound",
            )
        elif octet in closing:
            _require(
                bool(stack) and stack[-1] == closing[octet],
                "JSON structural delimiters are unbalanced",
            )
            stack.pop()
    _require(not in_string and not escaped, "JSON string is unterminated")
    _require(not stack, "JSON container is unterminated")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InventoryValidationError(f"duplicate JSON key is forbidden: {key}")
        result[key] = value
    return result


def _reject_float(value: str) -> Any:
    raise InventoryValidationError(f"JSON float is forbidden: {value}")


def _reject_nonfinite(value: str) -> Any:
    raise InventoryValidationError(f"non-finite JSON value is forbidden: {value}")


def _parse_integer(value: str) -> int:
    parsed = int(value, 10)
    _require(
        -SAFE_INTEGER_MAXIMUM <= parsed <= SAFE_INTEGER_MAXIMUM,
        "JSON integer is outside the exact safe-integer domain",
    )
    return parsed


def _validate_json_scalars(value: Any) -> None:
    stack = [value]
    while stack:
        current = stack.pop()
        if type(current) is dict:
            stack.extend(current.keys())
            stack.extend(current.values())
        elif type(current) is list:
            stack.extend(current)
        elif type(current) is str:
            _require(
                not any(0xD800 <= ord(character) <= 0xDFFF for character in current),
                "JSON string contains a surrogate code point",
            )
        else:
            _require(
                current is None
                or type(current) is bool
                or (
                    type(current) is int
                    and -SAFE_INTEGER_MAXIMUM <= current <= SAFE_INTEGER_MAXIMUM
                ),
                "JSON scalar is outside the exact I-JSON subset",
            )


def _decode_pretty_json(raw: bytes, *, label: str) -> Any:
    _scan_json_structure(raw, maximum_depth=MAXIMUM_JSON_NESTING_DEPTH)
    try:
        text = raw.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_float=_reject_float,
            parse_int=_parse_integer,
            parse_constant=_reject_nonfinite,
        )
    except (
        InventoryValidationError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        RecursionError,
    ) as exc:
        raise InventoryValidationError(f"{label} is not strict canonical JSON") from exc
    _validate_json_scalars(value)
    _require(_pretty_bytes(value) == raw, f"{label} is not canonical pretty JSON")
    return value


def _validate_exact_keys(
    value: Any, expected: frozenset[str], *, label: str
) -> dict[str, Any]:
    _require(type(value) is dict, f"{label} must be an exact object")
    missing = sorted(expected - set(value))
    extra = sorted(set(value) - expected)
    _require(
        not missing and not extra,
        f"{label} keys differ: missing={missing}, extra={extra}",
    )
    return value


def _validate_standalone_identity(
    record: Any,
    *,
    identity_field: str,
    expected_id: str | None = None,
    label: str,
) -> str:
    _require(type(record) is dict, f"{label} must be an exact object")
    _require(
        record.get("canonicalization_version") == CANONICALIZATION_VERSION,
        f"{label} canonicalization_version differs",
    )
    _require(
        record.get("measurement_schema_version") == MEASUREMENT_SCHEMA_VERSION,
        f"{label} measurement_schema_version differs",
    )
    domain = record.get("record_domain")
    _require(type(domain) is str and bool(domain), f"{label} record_domain differs")
    identity = record.get(identity_field)
    _require(_is_sha256(identity), f"{label} {identity_field} is not one SHA-256")
    excluded = {
        "canonicalization_version",
        "measurement_schema_version",
        "record_domain",
        identity_field,
    }
    payload = {key: value for key, value in record.items() if key not in excluded}
    recomputed = _semantic_id(domain, payload)
    _require(recomputed == identity, f"{label} semantic identity differs")
    if expected_id is not None:
        _require(identity == expected_id, f"{label} differs from its frozen identity")
    return identity


def _validate_selector_identity(
    selector: Any, *, expected_id: str | None = None, label: str
) -> str:
    _require(type(selector) is dict, f"{label} must be an exact object")
    _require(
        selector.get("canonicalization_version") == CANONICALIZATION_VERSION
        and selector.get("measurement_schema_version") == MEASUREMENT_SCHEMA_VERSION
        and selector.get("record_domain")
        == "RiskYieldMMA2MCheckpointSelectorV1V4_9F_RawV8",
        f"{label} envelope differs",
    )
    identity = selector.get("checkpoint_selector_id")
    _require(_is_sha256(identity), f"{label} checkpoint_selector_id differs")
    payload = {
        "operation_kind": selector.get("operation_kind"),
        "selector_length": selector.get("selector_length"),
        "ordered_checkpoint_selector_entry_ids": selector.get(
            "ordered_checkpoint_selector_entry_ids"
        ),
    }
    _require(
        _semantic_id(selector["record_domain"], payload) == identity,
        f"{label} semantic identity differs",
    )
    if expected_id is not None:
        _require(identity == expected_id, f"{label} differs from its frozen identity")
    return identity


def _repository_relative_path(value: str) -> Path:
    _require(type(value) is str and bool(value), "repository path must be text")
    _require("\\" not in value, f"repository path uses an alternate separator: {value}")
    parsed = PurePosixPath(value)
    _require(
        not parsed.is_absolute()
        and tuple(parsed.parts)
        and all(part not in {"", ".", ".."} for part in parsed.parts),
        f"repository path is not normalized relative POSIX: {value}",
    )
    _require(parsed.as_posix() == value, f"repository path is not canonical: {value}")
    return Path(*parsed.parts)


def _inventory_path_below_repository(path: Path, *, repository_root: Path) -> Path:
    absolute = _absolute_lexical_path(path, base=repository_root)
    try:
        relative = absolute.relative_to(repository_root)
    except ValueError as exc:
        raise InventoryValidationError(
            "inventory path is outside the repository root"
        ) from exc
    _require(
        tuple(relative.parts)
        and all(part not in {"", ".", ".."} for part in relative.parts),
        "inventory path is not normalized below the repository root",
    )
    return absolute


def _load_normative_documents(
    *, repository_root: Path
) -> tuple[list[dict[str, Any]], dict[str, bytes]]:
    records: list[dict[str, Any]] = []
    source_bytes: dict[str, bytes] = {}
    for role, relative_path, expected_octets, expected_sha256 in NORMATIVE_DOCUMENTS:
        raw = _secure_bounded_read(
            _repository_relative_path(relative_path),
            base=repository_root,
            maximum_octets=SOURCE_EXCLUSIVE_OCTET_LIMIT,
            exclusive=True,
        )
        _require(
            len(raw) == expected_octets,
            f"normative document octet count differs: {relative_path}",
        )
        _require(
            _sha256(raw) == expected_sha256,
            f"normative document SHA-256 differs: {relative_path}",
        )
        records.append(
            {
                "document_role": role,
                "repository_relative_path": relative_path,
                "raw_octet_count": len(raw),
                "raw_sha256": _sha256(raw),
            }
        )
        source_bytes[relative_path] = raw
    return records, source_bytes


def _load_structural_registry(*, repository_root: Path) -> tuple[dict[str, Any], bytes]:
    raw = _secure_bounded_read(
        _repository_relative_path(STRUCTURAL_REGISTRY_RELATIVE_PATH),
        base=repository_root,
        maximum_octets=INVENTORY_EXCLUSIVE_OCTET_LIMIT,
        exclusive=True,
    )
    _require(
        len(raw) == STRUCTURAL_REGISTRY_OCTETS,
        "standalone structural registry octet count differs",
    )
    _require(
        _sha256(raw) == STRUCTURAL_REGISTRY_SHA256,
        "standalone structural registry SHA-256 differs",
    )
    registry = _decode_pretty_json(raw, label="standalone structural registry")
    _validate_exact_keys(
        registry,
        STRUCTURAL_REGISTRY_KEYS,
        label="standalone structural registry",
    )
    _require(
        registry["canonicalization_version"] == CANONICALIZATION_VERSION,
        "standalone structural registry canonicalization differs",
    )
    _require(
        registry["measurement_schema_version"] == MEASUREMENT_SCHEMA_VERSION,
        "standalone structural registry measurement schema differs",
    )
    _require(
        registry["record_domain"] == STRUCTURAL_REGISTRY_DOMAIN,
        "standalone structural registry record domain differs",
    )
    payload = {
        member: registry[member]
        for member in STRUCTURAL_REGISTRY_IDENTITY_PAYLOAD_MEMBERS
    }
    _require(
        _semantic_id(STRUCTURAL_REGISTRY_DOMAIN, payload)
        == registry["external_schema_registry_id"],
        "standalone structural registry semantic identity differs",
    )
    _require(
        registry["external_schema_registry_id"] == STRUCTURAL_REGISTRY_ID,
        "standalone structural registry identity is not the frozen identity",
    )
    _require(
        registry["external_type_descriptor_count"] == 52
        and len(registry["ordered_external_type_descriptors"]) == 52
        and registry["schema_graph_node_count"] == 52
        and len(registry["ordered_schema_graph_node_names"]) == 52,
        "standalone structural registry 52-node counts differ",
    )
    _require(
        registry["cross_field_rule_descriptor_count"] == 42
        and len(registry["ordered_cross_field_rule_descriptors"]) == 42,
        "standalone structural registry 42-rule counts differ",
    )
    _require(
        registry["rule_application_descriptor_count"] == 8
        and len(registry["ordered_rule_application_descriptors"]) == 8,
        "standalone structural registry eight-application counts differ",
    )
    _require(
        len(registry["fixed_position_resolver_profile_catalog"]) == 2,
        "standalone structural registry resolver count differs",
    )
    return registry, raw


def _validate_normative_document_records(
    actual: Any, *, expected: list[dict[str, Any]]
) -> None:
    _require(type(actual) is list, "normative_document_inputs must be an array")
    _require(
        len(actual) == len(NORMATIVE_DOCUMENTS),
        "normative_document_inputs count differs",
    )
    for position, record in enumerate(actual, 1):
        _validate_exact_keys(
            record,
            NORMATIVE_DOCUMENT_KEYS,
            label=f"normative document input {position}",
        )
        _exact_nonnegative_integer(
            record["raw_octet_count"],
            field=f"normative document input {position} raw_octet_count",
        )
        _require(
            _is_sha256(record["raw_sha256"]),
            f"normative document input {position} raw_sha256 differs",
        )
    _require(
        actual == expected,
        "normative_document_inputs bytes, roles, paths, or semantic order differ",
    )


def _validate_embedded_structural_registry(
    actual: Any, *, standalone: dict[str, Any]
) -> None:
    _validate_exact_keys(
        actual,
        STRUCTURAL_REGISTRY_KEYS,
        label="embedded structural registry",
    )
    _require(
        actual == standalone,
        "embedded structural registry differs from the exact pinned raw object",
    )
    payload = {
        member: actual[member]
        for member in STRUCTURAL_REGISTRY_IDENTITY_PAYLOAD_MEMBERS
    }
    _require(
        _semantic_id(STRUCTURAL_REGISTRY_DOMAIN, payload)
        == actual["external_schema_registry_id"]
        == STRUCTURAL_REGISTRY_ID,
        "embedded structural registry semantic identity differs",
    )


def _validate_selector_catalog(actual: Any) -> list[dict[str, Any]]:
    _require(type(actual) is list, "checkpoint_selector_catalog must be an array")
    _require(
        len(actual) == len(SELECTOR_CATALOG),
        "checkpoint selector catalog count differs",
    )
    seen_entry_ids: set[str] = set()
    total_entries = 0
    for catalog_position, (record, frozen) in enumerate(
        zip(actual, SELECTOR_CATALOG, strict=True), 1
    ):
        catalog_name, operation_kind, selector_length, selector_id = frozen
        _validate_exact_keys(
            record,
            frozenset({"catalog_name", "selector"}),
            label=f"selector catalog record {catalog_position}",
        )
        _require(
            record["catalog_name"] == catalog_name,
            f"selector catalog name/order differs at {catalog_position}",
        )
        selector = record["selector"]
        _validate_exact_keys(
            selector,
            frozenset(
                {
                    "canonicalization_version",
                    "measurement_schema_version",
                    "record_domain",
                    "operation_kind",
                    "selector_length",
                    "ordered_checkpoint_selector_entry_ids",
                    "ordered_entries",
                    "checkpoint_selector_id",
                }
            ),
            label=f"selector {catalog_name}",
        )
        _require(
            selector["operation_kind"] == operation_kind,
            f"selector {catalog_name} operation differs",
        )
        _require(
            selector["selector_length"] == selector_length,
            f"selector {catalog_name} length differs",
        )
        entries = selector["ordered_entries"]
        entry_ids = selector["ordered_checkpoint_selector_entry_ids"]
        _require(
            type(entries) is list
            and type(entry_ids) is list
            and len(entries) == len(entry_ids) == selector_length,
            f"selector {catalog_name} entry cardinality differs",
        )
        occurrence_by_marker: dict[str, int] = {}
        for selector_position, entry in enumerate(entries, 1):
            _validate_exact_keys(
                entry,
                frozenset(
                    {
                        "canonicalization_version",
                        "measurement_schema_version",
                        "record_domain",
                        "operation_kind",
                        "selector_position",
                        "checkpoint_marker_kind",
                        "occurrence_index_within_kind",
                        "checkpoint_selector_entry_id",
                    }
                ),
                label=f"selector {catalog_name} entry {selector_position}",
            )
            _require(
                entry["operation_kind"] == operation_kind,
                f"selector {catalog_name} entry operation differs",
            )
            _require(
                entry["selector_position"] == selector_position,
                f"selector {catalog_name} positions are not contiguous one-based",
            )
            marker = entry["checkpoint_marker_kind"]
            occurrence = entry["occurrence_index_within_kind"]
            _require(
                type(marker) is str and type(occurrence) is int and occurrence >= 1,
                f"selector {catalog_name} marker coordinate is invalid",
            )
            previous = occurrence_by_marker.get(marker, 0)
            _require(
                occurrence == previous + 1,
                f"selector {catalog_name} marker occurrences are not contiguous",
            )
            occurrence_by_marker[marker] = occurrence
            entry_id = _validate_standalone_identity(
                entry,
                identity_field="checkpoint_selector_entry_id",
                label=f"selector {catalog_name} entry {selector_position}",
            )
            _require(
                entry_ids[selector_position - 1] == entry_id,
                f"selector {catalog_name} ordered entry identity differs",
            )
            _require(
                entry_id not in seen_entry_ids,
                "checkpoint selector entry identity is duplicated",
            )
            seen_entry_ids.add(entry_id)
        _validate_selector_identity(
            selector,
            expected_id=selector_id,
            label=f"selector {catalog_name}",
        )
        total_entries += selector_length
    _require(total_entries == 80, "checkpoint selector entry count differs from 80")
    _require(len(seen_entry_ids) == 80, "checkpoint selector entry IDs are not unique")
    return actual


def _validate_frozen_authority_records(inventory: dict[str, Any]) -> None:
    _validate_standalone_identity(
        inventory["target_field_registry"],
        identity_field="target_field_registry_id",
        expected_id=EXPECTED_SEMANTIC_IDS["target_field_registry_id"],
        label="target field registry",
    )
    _validate_standalone_identity(
        inventory["operation_counter_schema"],
        identity_field="counter_schema_id",
        expected_id=EXPECTED_SEMANTIC_IDS["operation_counter_schema_id"],
        label="operation counter schema",
    )
    _validate_standalone_identity(
        inventory["marker_contract"],
        identity_field="marker_contract_id",
        expected_id=EXPECTED_SEMANTIC_IDS["marker_contract_id"],
        label="marker contract",
    )
    oracle_catalog = inventory["ingress_logical_oracle_profile_catalog"]
    _require(
        type(oracle_catalog) is list and len(oracle_catalog) == 1,
        "ingress logical oracle profile catalog differs",
    )
    _validate_standalone_identity(
        oracle_catalog[0],
        identity_field="logical_oracle_profile_id",
        expected_id=EXPECTED_SEMANTIC_IDS["logical_oracle_profile_id"],
        label="ingress logical oracle profile",
    )

    fixtures = _validate_exact_keys(
        inventory["fixture_records"],
        FIXTURE_RECORD_KEYS,
        label="fixture_records",
    )
    specs = fixtures.get("operation_specs")
    _require(
        type(specs) is dict and tuple(sorted(specs)) == tuple(sorted(OPERATION_KINDS)),
        "fixture operation-spec universe differs",
    )
    for operation_kind in OPERATION_KINDS:
        spec = specs[operation_kind]
        _require(
            type(spec) is dict and spec.get("operation_kind") == operation_kind,
            f"fixture operation spec {operation_kind} operation differs",
        )
        _validate_standalone_identity(
            spec,
            identity_field="operation_spec_id",
            expected_id=OPERATION_SPEC_IDS[operation_kind],
            label=f"fixture operation spec {operation_kind}",
        )


def _maximum_root_family(
    *,
    root_family_kind: str,
    mode_attempt_pairs: tuple[tuple[str, str], ...],
    selector_catalog_position: int | None,
    selector_catalog_name: str | None,
    checkpoint_selector_id: str | None,
    selector_length: int,
    observation_count: int,
    role_sequence_formula: str,
    measured_roles: tuple[str, ...],
    selector_present: bool,
) -> dict[str, Any]:
    return {
        "root_family_kind": root_family_kind,
        "ordered_instrumentation_mode_attempt_presence_pairs": [
            list(pair) for pair in mode_attempt_pairs
        ],
        "selector_catalog_position": selector_catalog_position,
        "selector_catalog_name": selector_catalog_name,
        "checkpoint_selector_id": checkpoint_selector_id,
        "selector_length": selector_length,
        "observation_count": observation_count,
        "role_sequence_formula": role_sequence_formula,
        "ordered_measured_observation_roles": list(measured_roles),
        "selector_present": selector_present,
    }


def _profile(
    *,
    position: int,
    profile_kind: str,
    constraint_scope: str,
    measured_type_name: str,
    operation_kind: str,
    source_pointers: list[str],
    source_ids: list[str],
    selector_catalog_position: int | None,
    selector_catalog_name: str | None,
    checkpoint_selector_id: str | None,
    checkpoint_selector_entry_id: str | None,
    expected_checkpoint_marker_kind: str | None,
    expected_occurrence_index_within_kind: int | None,
    selector_position: int | None,
    checkpoint_outcome: str | None,
    checkpoint_binding_status: str | None,
    checkpoint_binding_unavailable_reason: str | None,
    checkpoint_field_unavailable_reason: str | None,
    root_families: list[dict[str, Any]],
    schedule_formula: str,
) -> dict[str, Any]:
    payload = {
        "profile_position": position,
        "profile_kind": profile_kind,
        "constraint_scope": constraint_scope,
        "measured_type_name": measured_type_name,
        "operation_kind": operation_kind,
        "ordered_source_authority_pointers": source_pointers,
        "ordered_source_authority_ids": source_ids,
        "selector_catalog_position": selector_catalog_position,
        "selector_catalog_name": selector_catalog_name,
        "checkpoint_selector_id": checkpoint_selector_id,
        "checkpoint_selector_entry_id": checkpoint_selector_entry_id,
        "expected_checkpoint_marker_kind": expected_checkpoint_marker_kind,
        "expected_occurrence_index_within_kind": (
            expected_occurrence_index_within_kind
        ),
        "selector_position": selector_position,
        "checkpoint_outcome": checkpoint_outcome,
        "checkpoint_binding_status": checkpoint_binding_status,
        "checkpoint_binding_unavailable_reason": (
            checkpoint_binding_unavailable_reason
        ),
        "checkpoint_field_unavailable_reason": checkpoint_field_unavailable_reason,
        "ordered_admissible_root_families": root_families,
        "application_schedule_formula": schedule_formula,
    }
    _require(
        tuple(payload) == PROFILE_ID_PAYLOAD_MEMBERS,
        "independent profile payload order drifted",
    )
    return {
        **payload,
        "maximum_constraint_scope_profile_id": _semantic_id(
            MAXIMUM_SCOPE_PROFILE_DOMAIN,
            payload,
        ),
    }


def _build_expected_profiles(inventory: dict[str, Any]) -> list[dict[str, Any]]:
    """Build the frozen catalog independently from its pointed authorities."""

    selectors = inventory["checkpoint_selector_catalog"]
    specs = inventory["fixture_records"]["operation_specs"]
    target_registry_id = inventory["target_field_registry"]["target_field_registry_id"]
    marker_contract_id = inventory["marker_contract"]["marker_contract_id"]
    profiles: list[dict[str, Any]] = []

    for operation_kind in OPERATION_KINDS:
        profiles.append(
            _profile(
                position=len(profiles) + 1,
                profile_kind="OUTER_RESULT_BOUNDARY_FIXTURE",
                constraint_scope="FROZEN_FIXTURE",
                measured_type_name="CapacityMeasurementOperationResultEvidence",
                operation_kind=operation_kind,
                source_pointers=[f"/fixture_records/operation_specs/{operation_kind}"],
                source_ids=[specs[operation_kind]["operation_spec_id"]],
                selector_catalog_position=None,
                selector_catalog_name=None,
                checkpoint_selector_id=None,
                checkpoint_selector_entry_id=None,
                expected_checkpoint_marker_kind=None,
                expected_occurrence_index_within_kind=None,
                selector_position=None,
                checkpoint_outcome=None,
                checkpoint_binding_status=None,
                checkpoint_binding_unavailable_reason=None,
                checkpoint_field_unavailable_reason=None,
                root_families=[],
                schedule_formula="OUTER_RESULT_SIGNED_SPEC_SINGLE_APPLICATION_V1",
            )
        )

    startup_family = _maximum_root_family(
        root_family_kind="STARTUP_RECOVERY_ONE",
        mode_attempt_pairs=(("OFF", "NULL"), ("ON", "NULL")),
        selector_catalog_position=None,
        selector_catalog_name=None,
        checkpoint_selector_id=None,
        selector_length=0,
        observation_count=1,
        role_sequence_formula="STARTUP_RECOVERY_ONE_V1",
        measured_roles=("STARTUP_RECOVERY",),
        selector_present=False,
    )
    selector_free_family = _maximum_root_family(
        root_family_kind="ORDINARY_SELECTOR_FREE_THREE",
        mode_attempt_pairs=(
            ("OFF", "NULL"),
            ("OFF", "NON_NULL"),
            ("ON", "NULL"),
        ),
        selector_catalog_position=None,
        selector_catalog_name=None,
        checkpoint_selector_id=None,
        selector_length=0,
        observation_count=3,
        role_sequence_formula="ORDINARY_BEFORE_CHECKPOINTS_AFTER_AGGREGATE_V1",
        measured_roles=(
            "BEFORE_OPERATION",
            "AFTER_OPERATION",
            "OPERATION_AGGREGATE",
        ),
        selector_present=False,
    )
    selectors_by_operation: dict[str, list[tuple[int, dict[str, Any]]]] = {
        operation_kind: [] for operation_kind in OPERATION_KINDS
    }
    for catalog_position, catalog_record in enumerate(selectors, 1):
        selector = catalog_record["selector"]
        selectors_by_operation[selector["operation_kind"]].append(
            (catalog_position, catalog_record)
        )

    for operation_kind in OPERATION_KINDS:
        source_pointers = ["/target_field_registry", "/marker_contract"]
        source_ids = [target_registry_id, marker_contract_id]
        families = [dict(startup_family), dict(selector_free_family)]
        for catalog_position, catalog_record in selectors_by_operation[operation_kind]:
            selector = catalog_record["selector"]
            source_pointers.append(
                f"/checkpoint_selector_catalog/{catalog_position - 1}/selector"
            )
            source_ids.append(selector["checkpoint_selector_id"])
            families.append(
                _maximum_root_family(
                    root_family_kind="ORDINARY_SELECTOR_BOUND",
                    mode_attempt_pairs=(("ON", "NON_NULL"),),
                    selector_catalog_position=catalog_position,
                    selector_catalog_name=catalog_record["catalog_name"],
                    checkpoint_selector_id=selector["checkpoint_selector_id"],
                    selector_length=selector["selector_length"],
                    observation_count=selector["selector_length"] + 3,
                    role_sequence_formula=(
                        "ORDINARY_BEFORE_CHECKPOINTS_AFTER_AGGREGATE_V1"
                    ),
                    measured_roles=(
                        "BEFORE_OPERATION",
                        "AFTER_OPERATION",
                        "OPERATION_AGGREGATE",
                    ),
                    selector_present=True,
                )
            )
        profiles.append(
            _profile(
                position=len(profiles) + 1,
                profile_kind="NON_CHECKPOINT_ROOT_FAMILY",
                constraint_scope="FROZEN_ROOT_APPLICATION",
                measured_type_name="TargetObservationV2",
                operation_kind=operation_kind,
                source_pointers=source_pointers,
                source_ids=source_ids,
                selector_catalog_position=None,
                selector_catalog_name=None,
                checkpoint_selector_id=None,
                checkpoint_selector_entry_id=None,
                expected_checkpoint_marker_kind=None,
                expected_occurrence_index_within_kind=None,
                selector_position=None,
                checkpoint_outcome=None,
                checkpoint_binding_status=None,
                checkpoint_binding_unavailable_reason=None,
                checkpoint_field_unavailable_reason=None,
                root_families=families,
                schedule_formula=("FINITE_UNION_OF_LISTED_ROOT_FAMILY_SCHEDULES_V1"),
            )
        )

    for catalog_position, catalog_record in enumerate(selectors, 1):
        selector = catalog_record["selector"]
        for entry in selector["ordered_entries"]:
            family = _maximum_root_family(
                root_family_kind="ORDINARY_SELECTOR_BOUND",
                mode_attempt_pairs=(("ON", "NON_NULL"),),
                selector_catalog_position=catalog_position,
                selector_catalog_name=catalog_record["catalog_name"],
                checkpoint_selector_id=selector["checkpoint_selector_id"],
                selector_length=selector["selector_length"],
                observation_count=selector["selector_length"] + 3,
                role_sequence_formula=(
                    "ORDINARY_BEFORE_CHECKPOINTS_AFTER_AGGREGATE_V1"
                ),
                measured_roles=("STABLE_CHECKPOINT",),
                selector_present=True,
            )
            for outcome in MAXIMUM_CHECKPOINT_OUTCOMES:
                binding_status, binding_reason, field_reason = (
                    MAXIMUM_CHECKPOINT_OUTCOME_BINDINGS[outcome]
                )
                profiles.append(
                    _profile(
                        position=len(profiles) + 1,
                        profile_kind="CHECKPOINT_ROOT_COORDINATE",
                        constraint_scope="FROZEN_ROOT_APPLICATION",
                        measured_type_name="TargetObservationV2",
                        operation_kind=selector["operation_kind"],
                        source_pointers=[
                            "/target_field_registry",
                            "/marker_contract",
                            (
                                "/checkpoint_selector_catalog/"
                                f"{catalog_position - 1}/selector"
                            ),
                        ],
                        source_ids=[
                            target_registry_id,
                            marker_contract_id,
                            selector["checkpoint_selector_id"],
                        ],
                        selector_catalog_position=catalog_position,
                        selector_catalog_name=catalog_record["catalog_name"],
                        checkpoint_selector_id=selector["checkpoint_selector_id"],
                        checkpoint_selector_entry_id=entry[
                            "checkpoint_selector_entry_id"
                        ],
                        expected_checkpoint_marker_kind=entry["checkpoint_marker_kind"],
                        expected_occurrence_index_within_kind=entry[
                            "occurrence_index_within_kind"
                        ],
                        selector_position=entry["selector_position"],
                        checkpoint_outcome=outcome,
                        checkpoint_binding_status=binding_status,
                        checkpoint_binding_unavailable_reason=binding_reason,
                        checkpoint_field_unavailable_reason=field_reason,
                        root_families=[family],
                        schedule_formula=(
                            "SELECTOR_PRESENT_2N_PLUS_3_CALLS_187N_PLUS_2_"
                            "EVALS_1872N_PLUS_7_NODES_V1"
                        ),
                    )
                )

    _require(
        len(profiles) == MAXIMUM_SCOPE_PROFILE_COUNT,
        "independently reconstructed profile count differs",
    )
    return profiles


def _resolve_json_pointer(root: Any, pointer: str) -> Any:
    _require(
        type(pointer) is str and pointer.startswith("/") and pointer != "/",
        f"source authority pointer is not absolute: {pointer!r}",
    )
    current = root
    for raw_token in pointer[1:].split("/"):
        escape_position = 0
        while escape_position < len(raw_token):
            if raw_token[escape_position] == "~":
                _require(
                    escape_position + 1 < len(raw_token)
                    and raw_token[escape_position + 1] in {"0", "1"},
                    f"source authority pointer contains an invalid escape: {pointer}",
                )
                escape_position += 2
            else:
                escape_position += 1
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if type(current) is dict:
            _require(
                token in current, f"source authority pointer is unresolved: {pointer}"
            )
            current = current[token]
        elif type(current) is list:
            _require(
                token == "0" or (token.isdigit() and not token.startswith("0")),
                f"source authority pointer array index is not canonical: {pointer}",
            )
            index = int(token, 10)
            _require(
                index < len(current),
                f"source authority pointer is outside its array: {pointer}",
            )
            current = current[index]
        else:
            raise InventoryValidationError(
                f"source authority pointer crosses a scalar: {pointer}"
            )
    return current


def _pointed_authority_identity(value: Any, *, pointer: str) -> str:
    if pointer == "/target_field_registry":
        field = "target_field_registry_id"
    elif pointer == "/marker_contract":
        field = "marker_contract_id"
    elif pointer.startswith("/checkpoint_selector_catalog/"):
        return _validate_selector_identity(
            value,
            label=f"pointed source authority {pointer}",
        )
    elif pointer.startswith("/fixture_records/operation_specs/"):
        field = "operation_spec_id"
    else:
        raise InventoryValidationError(
            f"source authority pointer is outside the frozen domains: {pointer}"
        )
    return _validate_standalone_identity(
        value,
        identity_field=field,
        label=f"pointed source authority {pointer}",
    )


def _validate_profile_catalog(
    actual: Any, *, inventory: dict[str, Any]
) -> list[dict[str, Any]]:
    _require(type(actual) is list, "maximum scope-profile catalog must be an array")
    _require(
        len(actual) == MAXIMUM_SCOPE_PROFILE_COUNT,
        "maximum scope-profile catalog count differs from 408",
    )
    expected = _build_expected_profiles(inventory)
    seen_ids: set[str] = set()
    kind_counts: Counter[str] = Counter()
    for position, profile in enumerate(actual, 1):
        _validate_exact_keys(
            profile,
            PROFILE_KEYS,
            label=f"maximum scope profile {position}",
        )
        _require(
            profile["profile_position"] == position,
            "maximum scope-profile positions are not contiguous one-based",
        )
        payload = {member: profile[member] for member in PROFILE_ID_PAYLOAD_MEMBERS}
        recomputed = _semantic_id(MAXIMUM_SCOPE_PROFILE_DOMAIN, payload)
        profile_id = profile["maximum_constraint_scope_profile_id"]
        _require(_is_sha256(profile_id), f"maximum scope profile {position} ID differs")
        _require(
            recomputed == profile_id,
            f"maximum scope profile {position} semantic ID differs",
        )
        _require(
            profile_id not in seen_ids,
            "maximum scope-profile IDs are not unique",
        )
        seen_ids.add(profile_id)
        pointers = profile["ordered_source_authority_pointers"]
        authority_ids = profile["ordered_source_authority_ids"]
        _require(
            type(pointers) is list
            and type(authority_ids) is list
            and len(pointers) == len(authority_ids),
            f"maximum scope profile {position} source cardinality differs",
        )
        for pointer, authority_id in zip(pointers, authority_ids, strict=True):
            pointed = _resolve_json_pointer(inventory, pointer)
            recomputed_authority_id = _pointed_authority_identity(
                pointed,
                pointer=pointer,
            )
            _require(
                authority_id == recomputed_authority_id,
                f"maximum scope profile {position} pointed authority ID differs",
            )
        families = profile["ordered_admissible_root_families"]
        _require(
            type(families) is list, f"maximum scope profile {position} families differ"
        )
        for family_position, family in enumerate(families, 1):
            _validate_exact_keys(
                family,
                ROOT_FAMILY_KEYS,
                label=f"maximum scope profile {position} family {family_position}",
            )
            _require(
                type(family["selector_present"]) is bool,
                f"maximum scope profile {position} selector_present differs",
            )
            _exact_nonnegative_integer(
                family["selector_length"],
                field=f"maximum scope profile {position} selector_length",
            )
            _exact_nonnegative_integer(
                family["observation_count"],
                field=f"maximum scope profile {position} observation_count",
            )
        kind_counts[profile["profile_kind"]] += 1
    _require(
        kind_counts
        == Counter(
            {
                "OUTER_RESULT_BOUNDARY_FIXTURE": 4,
                "NON_CHECKPOINT_ROOT_FAMILY": 4,
                "CHECKPOINT_ROOT_COORDINATE": 400,
            }
        ),
        "maximum scope-profile kind counts differ",
    )
    _require(
        actual == expected,
        "maximum scope-profile catalog differs from the independent exact catalog",
    )
    return actual


def _validate_operation_contracts(
    actual: Any, *, inventory: dict[str, Any]
) -> list[dict[str, Any]]:
    contracts = _validate_exact_keys(
        actual,
        OPERATION_CONTRACT_KEYS,
        label="operation_contracts",
    )
    _require(
        contracts["checkpoint_binding_statuses"]
        == [
            "EXACT_MARKER",
            "UNAVAILABLE_MARKER_OBSERVER_FAILURE",
            "UNAVAILABLE_TARGET_BOUNDARY_NOT_REACHED",
        ],
        "checkpoint binding-status order differs",
    )
    expected_reason_map = {
        outcome: binding[2]
        for outcome, binding in MAXIMUM_CHECKPOINT_OUTCOME_BINDINGS.items()
        if binding[2] is not None
    }
    _require(
        contracts["checkpoint_context_to_field_reason"] == expected_reason_map,
        "checkpoint context-to-field-reason mapping differs",
    )
    _require(
        contracts["checkpoint_placeholder_context_predicate_by_field_reason"]
        == {
            "CHECKPOINT_PLACEHOLDER_ARTIFACT_BOUND_EXCEEDED": (
                "V2_CHECKPOINT_PLACEHOLDER_ARTIFACT_BOUND"
            ),
            "CHECKPOINT_PLACEHOLDER_OBSERVER_INTERNAL_ERROR": (
                "V2_CHECKPOINT_PLACEHOLDER_OBSERVER_INTERNAL_ERROR"
            ),
            "CHECKPOINT_PLACEHOLDER_SOURCE_CLOCK_UNAVAILABLE": (
                "V2_CHECKPOINT_PLACEHOLDER_SOURCE_CLOCK_UNAVAILABLE"
            ),
            "CHECKPOINT_PLACEHOLDER_TARGET_BOUNDARY_NOT_REACHED": (
                "V2_CHECKPOINT_PLACEHOLDER_TARGET_BOUNDARY_NOT_REACHED"
            ),
        },
        "checkpoint field-reason predicate mapping differs",
    )
    expected_scalar_domains = [
        {
            "member_name": member_name,
            "integer_minimum": minimum,
            "integer_maximum": maximum,
        }
        for member_name, minimum, maximum in LOCAL_SHUTDOWN_SCALAR_LIMIT_DOMAINS
    ]
    _require(
        contracts["local_shutdown_scalar_limit_domains"] == expected_scalar_domains,
        "local-shutdown scalar limit domains differ",
    )
    _require(
        contracts["local_shutdown_intrinsic_limit_relations"]
        == list(LOCAL_SHUTDOWN_INTRINSIC_LIMIT_RELATIONS),
        "local-shutdown intrinsic limit relations differ",
    )
    _require(
        contracts["local_shutdown_operational_result_relations"]
        == list(LOCAL_SHUTDOWN_OPERATIONAL_RESULT_RELATIONS),
        "local-shutdown operational result relations differ",
    )
    _require(
        contracts["operation_result_canonical_byte_ceiling"] == 524_288,
        "operation-result canonical-byte ceiling differs",
    )
    return _validate_profile_catalog(
        contracts["maximum_constraint_scope_profile_catalog"],
        inventory=inventory,
    )


def _walk_keys(value: Any) -> set[str]:
    found: set[str] = set()
    stack = [value]
    while stack:
        current = stack.pop()
        if type(current) is dict:
            found.update(current)
            stack.extend(current.values())
        elif type(current) is list:
            stack.extend(current)
    return found


def _validate_invariants(
    actual: Any,
    *,
    normative_documents: list[dict[str, Any]],
    profiles: list[dict[str, Any]],
) -> None:
    invariants = _validate_exact_keys(actual, INVARIANT_KEYS, label="invariants")
    _require(
        invariants["canonicalization_version"] == CANONICALIZATION_VERSION,
        "invariants canonicalization_version differs",
    )
    _require(
        invariants["measurement_schema_version"] == MEASUREMENT_SCHEMA_VERSION,
        "invariants measurement_schema_version differs",
    )
    _require(
        invariants["inventory_schema_version"] == INVENTORY_SCHEMA_VERSION,
        "invariants inventory_schema_version differs",
    )
    _require(
        invariants["exact_semantic_ids"] == EXPECTED_SEMANTIC_IDS,
        "invariants exact_semantic_ids differ",
    )
    _require(
        invariants["target_field_registry_id"]
        == EXPECTED_SEMANTIC_IDS["target_field_registry_id"],
        "invariants target_field_registry_id differs",
    )
    _require(
        invariants["operation_counter_schema_id"]
        == EXPECTED_SEMANTIC_IDS["operation_counter_schema_id"],
        "invariants operation_counter_schema_id differs",
    )
    document_hashes = {
        item["document_role"]: item["raw_sha256"] for item in normative_documents
    }
    _require(
        invariants["normative_document_sha256_by_role"] == document_hashes,
        "invariants normative document hash map differs",
    )
    _require(
        invariants["protocol_sha256"]
        == document_hashes["PARENT_MARKER_OPERATION_TARGET_PROTOCOL"],
        "invariants protocol_sha256 differs",
    )
    profile_id_digest = _sha256(
        _canonical_bytes(
            [profile["maximum_constraint_scope_profile_id"] for profile in profiles]
        )
    )
    _require(
        invariants["maximum_constraint_scope_profile_ids_canonical_json_sha256"]
        == profile_id_digest,
        "invariants maximum profile-ID sequence digest differs",
    )
    counts = invariants["counts"]
    _require(type(counts) is dict, "invariants counts must be an exact object")
    expected_counts = {
        "normative_document_input_count": 4,
        "external_type_descriptor_count": 52,
        "checkpoint_selector_catalog_count": 9,
        "maximum_constraint_scope_profile_count": 408,
        "maximum_result_scope_profile_count": 4,
        "maximum_non_checkpoint_scope_profile_count": 4,
        "maximum_checkpoint_scope_profile_count": 400,
        "operation_kind_count": 4,
        "target_field_count": 185,
        "counter_field_count": 66,
    }
    for key, expected_value in expected_counts.items():
        _require(
            counts.get(key) == expected_value,
            f"invariants count differs: {key}",
        )
    _require(
        invariants["constructive_maxima_external_artifact_contract"]
        == {
            "intrinsic_byte_maximum_row_count": 66,
            "outer_result_byte_maximum_row_count": 4,
            "root_application_byte_maximum_row_count": 404,
            "total_byte_maximum_row_count": 474,
            "local_shutdown_counterexample_count": 1,
            "maximum_rows_embedded_in_inventory": False,
            "heuristic_bound_proofs_are_authority": False,
        },
        "constructive-maxima external-artifact contract differs",
    )
    _require(
        invariants["frozen_byte_maxima"]
        == {
            "target_observation_strict_ceiling": 262_144,
            "operation_result_strict_ceiling": 524_288,
            "selector_length_maximum": 64,
            "target_observation_root_count_maximum": 67,
            "subscription_kernel_pair_count_maximum": 256,
        },
        "frozen codec ceilings differ",
    )
    generated = invariants["generated_boundary_proofs"]
    _validate_exact_keys(
        generated,
        frozenset(
            {
                "standalone_envelope_collision_guard",
                "ingress_counts",
                "selector_lengths",
                "root_counts",
                "subscription_kernel_pair_cardinalities",
                "local_shutdown_limit_relation_cases",
                "checkpoint_binding_state_count",
            }
        ),
        label="generated_boundary_proofs",
    )
    _require(
        generated["checkpoint_binding_state_count"] == 3,
        "generated checkpoint binding-state count differs",
    )
    forbidden_found = sorted(LEGACY_HEURISTIC_KEYS & _walk_keys(invariants))
    _require(
        not forbidden_found,
        f"legacy heuristic proof keys are forbidden: {forbidden_found}",
    )


def _validate_inventory_semantic_identity(inventory: dict[str, Any]) -> str:
    identity = inventory["inventory_sha256"]
    _require(_is_sha256(identity), "inventory_sha256 is not one lowercase SHA-256")
    unsigned = dict(inventory)
    unsigned.pop("inventory_sha256")
    recomputed = _sha256(_canonical_bytes(unsigned))
    _require(recomputed == identity, "V3 semantic inventory_sha256 differs")
    return identity


def _revalidate_source_snapshot(
    *, repository_root: Path, expected_source_bytes: dict[str, bytes]
) -> None:
    """Re-read every physical authority immediately before gate acceptance."""

    expected_paths = {
        *(relative_path for _, relative_path, _, _ in NORMATIVE_DOCUMENTS),
        STRUCTURAL_REGISTRY_RELATIVE_PATH,
    }
    _require(
        set(expected_source_bytes) == expected_paths,
        "source snapshot does not contain the exact five authorities",
    )
    for relative_path in sorted(expected_paths):
        raw = _secure_bounded_read(
            _repository_relative_path(relative_path),
            base=repository_root,
            maximum_octets=SOURCE_EXCLUSIVE_OCTET_LIMIT,
            exclusive=True,
        )
        _require(
            raw == expected_source_bytes[relative_path],
            f"source authority changed before acceptance: {relative_path}",
        )


def validate_inventory_file(
    *, repository_root: Path, inventory_path: Path
) -> dict[str, Any]:
    """Validate one V3 inventory and return a deterministic evidence report."""

    repository_root = repository_root.resolve(strict=True)
    _require(repository_root.is_dir(), "repository root is not a directory")
    inventory_path = _inventory_path_below_repository(
        inventory_path,
        repository_root=repository_root,
    )

    normative_documents, expected_source_bytes = _load_normative_documents(
        repository_root=repository_root
    )
    structural_registry, structural_raw = _load_structural_registry(
        repository_root=repository_root
    )
    expected_source_bytes[STRUCTURAL_REGISTRY_RELATIVE_PATH] = structural_raw

    inventory_raw = _secure_bounded_read(
        inventory_path,
        maximum_octets=INVENTORY_EXCLUSIVE_OCTET_LIMIT,
        exclusive=True,
    )
    inventory = _decode_pretty_json(inventory_raw, label="V3 inventory")
    _validate_exact_keys(inventory, INVENTORY_ROOT_KEYS, label="V3 inventory root")
    _require(
        inventory["schema_version"] == INVENTORY_SCHEMA_VERSION,
        "V3 inventory schema_version differs",
    )
    _require(
        "external_type_registry" not in inventory
        and "external_schema_registry_id" not in inventory,
        "V3 inventory contains a legacy or duplicated root registry member",
    )
    forbidden_found = sorted(LEGACY_HEURISTIC_KEYS & _walk_keys(inventory))
    _require(
        not forbidden_found,
        f"V3 inventory contains legacy heuristic proof keys: {forbidden_found}",
    )
    _validate_normative_document_records(
        inventory["normative_document_inputs"],
        expected=normative_documents,
    )
    _validate_embedded_structural_registry(
        inventory["external_schema_registry_v2"],
        standalone=structural_registry,
    )
    _validate_frozen_authority_records(inventory)
    selectors = _validate_selector_catalog(inventory["checkpoint_selector_catalog"])
    profiles = _validate_operation_contracts(
        inventory["operation_contracts"],
        inventory=inventory,
    )
    _validate_invariants(
        inventory["invariants"],
        normative_documents=normative_documents,
        profiles=profiles,
    )
    inventory_semantic_id = _validate_inventory_semantic_identity(inventory)

    # The schedule formula is structural, not a runtime-work-maximum claim.
    maximum_selector_length = max(
        record["selector"]["selector_length"] for record in selectors
    )
    maximum_observation_count = maximum_selector_length + 3
    maximum_application_calls = 2 * maximum_observation_count + 3
    maximum_charged_evaluations = 187 * maximum_observation_count + 2
    maximum_direct_nodes = 1_872 * maximum_observation_count + 7
    _require(
        (
            maximum_selector_length,
            maximum_observation_count,
            maximum_application_calls,
            maximum_charged_evaluations,
            maximum_direct_nodes,
        )
        == (64, 67, 137, 12_531, 125_431),
        "maximum selector schedule formula evaluation differs",
    )

    _revalidate_source_snapshot(
        repository_root=repository_root,
        expected_source_bytes=expected_source_bytes,
    )
    return {
        "checkpoint_scope_profile_count": MAXIMUM_CHECKPOINT_SCOPE_PROFILE_COUNT,
        "checkpoint_selector_entry_count": sum(
            record["selector"]["selector_length"] for record in selectors
        ),
        "component_status": COMPONENT_STATUS,
        "external_schema_registry_id": structural_registry[
            "external_schema_registry_id"
        ],
        "external_type_descriptor_count": structural_registry[
            "external_type_descriptor_count"
        ],
        "inventory_octets": len(inventory_raw),
        "inventory_raw_sha256": _sha256(inventory_raw),
        "inventory_sha256": inventory_semantic_id,
        "maximum_constraint_scope_profile_count": len(profiles),
        "maximum_selector_application_calls": maximum_application_calls,
        "maximum_selector_charged_rule_evaluations": (maximum_charged_evaluations),
        "maximum_selector_direct_expression_nodes": maximum_direct_nodes,
        "maximum_selector_length": maximum_selector_length,
        "maximum_selector_observation_count": maximum_observation_count,
        "non_checkpoint_scope_profile_count": (
            MAXIMUM_NON_CHECKPOINT_SCOPE_PROFILE_COUNT
        ),
        "normative_document_input_count": len(normative_documents),
        "result_scope_profile_count": MAXIMUM_RESULT_SCOPE_PROFILE_COUNT,
        "schema_graph_node_count": structural_registry["schema_graph_node_count"],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--inventory", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        repository_root = arguments.repository_root.resolve(strict=True)
        inventory_path = (
            arguments.inventory
            if arguments.inventory is not None
            else repository_root / INVENTORY_RELATIVE_PATH
        )
        report = validate_inventory_file(
            repository_root=repository_root,
            inventory_path=inventory_path,
        )
    except (
        AssertionError,
        AttributeError,
        IndexError,
        InventoryValidationError,
        KeyError,
        OSError,
        RuntimeError,
        TypeError,
        UnicodeError,
        ValueError,
    ) as exc:
        print(
            f"Raw-V8 Step-2 External Schema V2 V3 inventory error: {exc}",
            file=sys.stderr,
        )
        return 1
    print(
        json.dumps(
            report,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
